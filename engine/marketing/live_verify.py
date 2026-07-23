"""engine.marketing.live_verify — post-time tape check against delayed live quotes.

The content plan is generated nightly (~23:45 ET) from that day's EOD data; the
outbox posts the NEXT trading day at 10:00 / 13:30 / 16:15 ET. Between
generation and posting the tape moves: a signal written off yesterday's close
can be underwater, run away, or sitting on an earnings print by the time its
slot arrives (the "engine said buy, it's down 7% on earnings" case). This
module is the last-line freshness gate the publisher runs per item, per slot.

Data sources (all repo-local files, fail-soft):
  * data/marketing/live_quotes_snapshot.json — full-universe quotes the publish
    workflow fetches from the live-data branch just before running (5-min
    cadence artifact, ~2k symbols, 15-min-delayed prices).
  * site/live/quotes.json — display-subset fallback (~30 symbols, 30-min cadence).
  * site/marketdata/sp500_heatmap.json — 1D pct fallback (30-min cadence in RTH).
  * data/earnings/earnings.parquet — next_date / next_time per ticker (nightly).

Verdict per item: {"action": "post" | "skip" | "quarantine", "reasons": [...]}
  * quarantine — the copy is WRONG on today's tape (adverse move, underwater,
    runaway). Never post it; tomorrow's plan regenerates from fresh data.
  * skip — cannot verify right now, or a same-day caution (ticker reports
    today). The item stays approved; the next slot re-checks.
  * post — verified against the tape, or the kind carries no live price claim.

Fail direction: an unverifiable SIGNAL never posts (skip); kinds without a
single-name price claim (education/macro/event) fail open. Display-tier ops
gate — no signal authority, no ledger writes; the publisher owns transitions.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Defaults (overridable via config/marketing.yml publish.live_gate)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # A quote older than this (minutes) counts as missing during a posting slot.
    # Slots run in RTH; the live lanes refresh every 5-30 min, so 45 covers a
    # missed tick without accepting yesterday's tape.
    "max_quote_age_min": 45,
    # Same-day adverse move (pct vs prior close) that kills a post outright.
    "signal_adverse_pct": -4.0,
    "chart_adverse_pct": -7.0,
    "receipt_adverse_pct": -5.0,
    # Live entry-distance gates for signal posts. Mirrors copywriter's plan-time
    # constants (2% underwater / 12% runaway) but measured against the LIVE
    # price at posting time instead of the prior EOD close.
    "underwater_pct": 0.02,
    "runaway_pct": 0.12,
    # Same-day move claims (mover/theme_list): live move must keep the sign and
    # at least this fraction of the baseline magnitude, else the claim is stale.
    "move_claim_min_ratio": 0.3,
    # Skip signal posts when the ticker reports earnings today (any session) or
    # tomorrow pre-market. Posting a technical entry into a binary print is how
    # the desk ends up wearing the gap.
    "earnings_guard": True,
}

_SNAPSHOT_REL = Path("data") / "marketing" / "live_quotes_snapshot.json"
_DISPLAY_REL = Path("site") / "live" / "quotes.json"
_HEATMAP_REL = Path("site") / "marketdata" / "sp500_heatmap.json"
_EARNINGS_REL = Path("data") / "earnings" / "earnings.parquet"

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Kinds that carry a single-name live-price claim worth gating.
_PRICE_KINDS = frozenset({"signal", "chart", "watchlist", "receipt", "mover", "theme_list"})


def gate_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve the live-gate config: publish.live_gate over in-code defaults."""
    out = dict(_DEFAULTS)
    try:
        block = ((cfg or {}).get("publish") or {}).get("live_gate") or {}
        for k, dv in _DEFAULTS.items():
            if k in block:
                out[k] = type(dv)(block[k]) if not isinstance(dv, bool) else bool(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("live_verify: bad publish.live_gate config (%s) — using defaults", exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Quote loading
# ─────────────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("live_verify: unreadable %s: %s", path, exc)
        return None


def _quotes_from_snapshot(obj: dict) -> dict[str, dict]:
    """Normalize a build_live_quotes artifact into {ticker: quote}."""
    out: dict[str, dict] = {}
    for tkr, q in (obj.get("quotes") or {}).items():
        if not isinstance(q, dict):
            continue
        out[str(tkr).upper()] = {
            "price": q.get("price"),
            "prev_close": q.get("prevClose"),
            "change_pct": q.get("changePct"),
            "ts_ms": q.get("ts"),
            "source": "quotes",
        }
    return out


def _quotes_from_heatmap(obj: dict) -> dict[str, dict]:
    """Extract {ticker: {change_pct}} from the sp500 heatmap tiles (pct-only)."""
    out: dict[str, dict] = {}
    try:
        for tile in obj.get("tiles") or obj.get("data") or []:
            tkr = str(tile.get("ticker") or tile.get("t") or "").upper()
            pct = tile.get("pct")
            if pct is None:
                perf = tile.get("perf") or {}
                pct = perf.get("1D") if isinstance(perf, dict) else None
            if tkr and pct is not None:
                out[tkr] = {
                    "price": None,
                    "prev_close": None,
                    "change_pct": pct,
                    "ts_ms": None,
                    "source": "heatmap",
                }
    except Exception:  # noqa: BLE001
        return {}
    return out


def load_live_quotes(root: Path | str | None = None) -> dict[str, Any]:
    """Load the freshest available quote view.

    Returns {"quotes": {ticker: {price, prev_close, change_pct, ts_ms, source}},
             "asof": iso-str | None, "source": str}.
    Precedence per ticker: full snapshot > display quotes > heatmap pct.
    Never raises; empty quotes dict when nothing is readable.
    """
    r = Path(root) if root is not None else Path(".")
    quotes: dict[str, dict] = {}
    asof: str | None = None
    src_used: list[str] = []

    heat = _read_json(r / _HEATMAP_REL)
    if heat:
        hq = _quotes_from_heatmap(heat)
        if hq:
            quotes.update(hq)
            src_used.append("heatmap")

    for rel, label in ((_DISPLAY_REL, "display"), (_SNAPSHOT_REL, "snapshot")):
        obj = _read_json(r / rel)
        if obj:
            q = _quotes_from_snapshot(obj)
            if q:
                quotes.update(q)  # later (fuller/fresher) sources win
                src_used.append(label)
                asof = obj.get("asof") or asof

    return {"quotes": quotes, "asof": asof, "source": "+".join(src_used) or "none"}


def _quote_age_min(quote: dict, asof: str | None, now: datetime) -> float | None:
    """Age of a quote in minutes, from its own ts, else the artifact asof."""
    ts_ms = quote.get("ts_ms")
    if ts_ms:
        try:
            dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
            return (now - dt).total_seconds() / 60.0
        except Exception:  # noqa: BLE001
            pass
    if asof:
        try:
            dt = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).total_seconds() / 60.0
        except Exception:  # noqa: BLE001
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Earnings calendar
# ─────────────────────────────────────────────────────────────────────────────

def load_earnings_guard_set(
    root: Path | str | None = None,
    *,
    now: datetime | None = None,
) -> frozenset[str]:
    """Tickers reporting today (any session) or tomorrow pre-market.

    Reads data/earnings/earnings.parquet (nightly Nasdaq sweep). Empty set on
    any failure — the guard degrades to open, the price gates still stand.
    """
    r = Path(root) if root is not None else Path(".")
    nd = (now or datetime.now(timezone.utc)).date()
    today = nd.strftime("%Y-%m-%d")
    tomorrow = (nd + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(r / _EARNINGS_REL)
        if "next_date" not in df.columns:
            return frozenset()
        tickers: set[str] = set()
        tcol = df["next_time"] if "next_time" in df.columns else None
        idx = df.index.astype(str)
        for i, nd_val in enumerate(df["next_date"].astype(str)):
            if nd_val == today:
                tickers.add(idx[i].upper())
            elif nd_val == tomorrow and tcol is not None:
                if "pre-market" in str(tcol.iloc[i]):
                    tickers.add(idx[i].upper())
        return frozenset(tickers)
    except Exception as exc:  # noqa: BLE001
        log.warning("live_verify: earnings calendar unavailable (%s) — guard open", exc)
        return frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Item field extraction
# ─────────────────────────────────────────────────────────────────────────────

def _item_ticker(item: dict) -> str:
    """Best-effort ticker for an outbox item: source stamp > media > cashtag."""
    src = item.get("source") or {}
    t = str(src.get("ticker") or "").upper()
    if t:
        return t
    for m in item.get("media") or []:
        t = str((m or {}).get("ticker") or "").upper()
        if t:
            return t
    m2 = _CASHTAG_RE.search(item.get("text") or "")
    return m2.group(1) if m2 else ""


def _f(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────────────

def verify_item(
    item: dict,
    *,
    live: dict[str, Any],
    earnings: frozenset[str] = frozenset(),
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Verdict for one outbox item against the live tape.

    live: output of load_live_quotes(). Never raises; on internal error the
    verdict fails toward "skip" for signals and "post" otherwise.
    """
    nowdt = now or datetime.now(timezone.utc)
    g = gate_cfg(cfg)
    kind = str(item.get("kind") or "")
    if not g.get("enabled", True) or kind not in _PRICE_KINDS:
        return {"action": "post", "reasons": []}

    try:
        ticker = _item_ticker(item)
        if not ticker:
            return {"action": "post", "reasons": ["no ticker claim"]}

        src = item.get("source") or {}
        direction = str(src.get("direction") or "BULL").upper()
        is_bull = direction != "BEAR"
        sign = 1.0 if is_bull else -1.0

        if kind == "signal" and g["earnings_guard"] and ticker in earnings:
            return {"action": "skip", "reasons": [f"{ticker} reports earnings today/tomorrow AM — not posting a signal into the print"]}

        quote = (live.get("quotes") or {}).get(ticker)
        age = _quote_age_min(quote, live.get("asof"), nowdt) if quote else None
        stale = age is None or age > g["max_quote_age_min"]
        change_pct = _f(quote.get("change_pct")) if quote else None
        price = _f(quote.get("price")) if quote else None

        if quote is None or (stale and change_pct is None):
            if kind in ("signal", "mover", "theme_list"):
                return {"action": "skip", "reasons": [f"no fresh quote for {ticker} — cannot verify against today's tape"]}
            return {"action": "post", "reasons": [f"no fresh quote for {ticker}; kind={kind} carries no hard same-day claim"]}
        if stale:
            # We have a pct but it is old (e.g. pre-open leftover). Signals and
            # same-day move claims still need fresh tape; softer kinds pass.
            if kind in ("signal", "mover", "theme_list"):
                return {"action": "skip", "reasons": [f"quote for {ticker} is {age:.0f}m old (max {g['max_quote_age_min']}m)"]}
            return {"action": "post", "reasons": [f"quote {age:.0f}m old; kind={kind} passes"]}

        reasons: list[str] = []

        if kind == "signal":
            if change_pct is not None and (change_pct * sign) <= g["signal_adverse_pct"]:
                return {"action": "quarantine", "reasons": [
                    f"{ticker} {change_pct:+.1f}% today against a {direction} signal written off yesterday's close"]}
            entry = _f(src.get("entry"))
            if entry and price:
                edge = (price - entry) / entry * sign  # >0 = in favor
                if edge < -g["underwater_pct"]:
                    return {"action": "quarantine", "reasons": [
                        f"live price {price:.2f} is {edge * 100:.1f}% through entry {entry:.2f} — signal underwater at post time"]}
                if edge > g["runaway_pct"]:
                    return {"action": "quarantine", "reasons": [
                        f"live price {price:.2f} is +{edge * 100:.1f}% past entry {entry:.2f} — entry no longer actionable"]}
            reasons.append(f"{ticker} verified vs live tape ({change_pct:+.1f}% today)" if change_pct is not None else f"{ticker} quote present")
            return {"action": "post", "reasons": reasons}

        if kind in ("mover", "theme_list"):
            baseline = _f(src.get("baseline_pct"))
            if change_pct is None:
                return {"action": "skip", "reasons": [f"no live pct for {ticker} — same-day move claim unverifiable"]}
            if baseline is not None:
                same_sign = (baseline >= 0) == (change_pct >= 0)
                holds = same_sign and abs(change_pct) >= abs(baseline) * g["move_claim_min_ratio"]
                if not holds:
                    return {"action": "quarantine", "reasons": [
                        f"move claim stale: copy says {baseline:+.1f}%, tape says {change_pct:+.1f}%"]}
            return {"action": "post", "reasons": [f"move claim holds ({change_pct:+.1f}% live)"]}

        if kind == "receipt":
            if change_pct is not None and change_pct <= g["receipt_adverse_pct"]:
                return {"action": "skip", "reasons": [
                    f"{ticker} {change_pct:+.1f}% today — not posting a report card while the name bleeds"]}
            return {"action": "post", "reasons": []}

        # chart / watchlist
        if change_pct is not None and change_pct <= g["chart_adverse_pct"]:
            return {"action": "skip", "reasons": [
                f"{ticker} {change_pct:+.1f}% today — chart talk can wait for the dust"]}
        return {"action": "post", "reasons": []}

    except Exception as exc:  # noqa: BLE001
        log.warning("live_verify.verify_item: %s — failing %s", exc,
                    "closed (skip)" if kind == "signal" else "open (post)")
        if kind == "signal":
            return {"action": "skip", "reasons": [f"gate error: {exc}"]}
        return {"action": "post", "reasons": [f"gate error (open): {exc}"]}
