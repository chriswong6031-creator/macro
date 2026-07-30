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
    # When the market is CLOSED (weekend), no session has traded since the plan
    # was built off the last close, so the wall-clock staleness skip is a false
    # positive — the last close IS the current price. In that mode level-claim
    # kinds (signal/chart/watchlist/receipt) verify against the last close and
    # post instead of skipping. Set false to force the strict every-day gate.
    "market_closed_mode": True,
}

_SNAPSHOT_REL = Path("data") / "marketing" / "live_quotes_snapshot.json"
_DISPLAY_REL = Path("site") / "live" / "quotes.json"
_HEATMAP_REL = Path("site") / "marketdata" / "sp500_heatmap.json"
_EARNINGS_REL = Path("data") / "earnings" / "earnings.parquet"

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Kinds that carry a single-name live-price claim worth gating.
_PRICE_KINDS = frozenset({"signal", "chart", "watchlist", "receipt", "mover", "theme_list"})

# Level/technical/retrospective kinds whose claim is valid against the LAST
# CLOSE, so they may post on a closed (weekend) day. Same-day MOVE claims
# (mover / theme_list — "today's biggest mover", "the group moving today")
# are deliberately excluded: those need a live session and are correctly held
# on a non-trading day.
_CLOSED_LEVEL_KINDS = frozenset({"signal", "chart", "watchlist", "receipt"})

try:
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - tzdata missing
    _ET = None


def _market_is_closed(now: datetime) -> bool:
    """True when the US equity market holds NO session on *now*'s date — a weekend.

    The whole gate exists to catch price action BETWEEN plan-build and post. On a
    weekend no session trades, so a signal written off the prior close cannot have
    been invalidated by intervening tape — the last close is the current price.

    Deliberately scoped to weekends only. Weekday pre-/post-market is NOT treated
    as closed: a full session trades on a weekday, so a stale pre-open quote
    genuinely cannot verify today's tape. Full-day holidays are also not covered
    here — on a holiday the gate simply stays strict (the pre-fix behaviour),
    which is the safe direction (never wrongly open). Fail-soft: any timezone
    error returns False, keeping the strict weekday gate.
    """
    try:
        et = now.astimezone(_ET) if _ET is not None else now
    except Exception:  # noqa: BLE001
        return False
    return et.weekday() >= 5  # Saturday=5, Sunday=6


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


def _feed_delay_min(obj: dict | None) -> float:
    """The delay a quote artifact DECLARES for itself, in minutes (0 when silent).

    ``build_live_quotes`` stamps ``meta.delayed_min`` from config.yml's
    ``live.delayed_min`` because the feed underneath is contractually delayed:
    Yahoo's ``regularMarketTime`` — the field that becomes each quote's ``ts`` —
    is the timestamp of a price we are only allowed to see ~15 minutes late.
    Measured 2026-07-30T03:46Z against symbols that were ACTIVELY TRADING at the
    time: 0700.HK 15.0m, 0005.HK 15.1m, 1299.HK 15.0m, 9988.HK 15.1m behind wall
    clock, futures ~10m, and BTC-USD/EURUSD=X real-time at 0.6-0.9m.

    That number is a property of the DATA PLAN, not of our lane's health, and the
    two must not be conflated: a quote's age is (how long since we looked) PLUS
    (how far behind real-time the tape is), and a freshness budget written to
    bound the first is unsatisfiable when the second alone exceeds it.

    REPORTED, NEVER APPLIED HERE. This module's own live gate deliberately keeps
    measuring absolute market time against its own ceiling — nothing about this
    helper loosens it. A consumer whose budget means observation lag adds this to
    its ceiling; a consumer that means market time ignores it. Which one a caller
    is, is the caller's business.

    Silent artifacts (the heatmap's pct-only tiles, every test fixture) return
    0.0, so a caller's ceiling is unchanged unless a feed actually declares a lag.
    """
    try:
        meta = (obj or {}).get("meta")
        if not isinstance(meta, dict):
            return 0.0
        return max(0.0, float(meta.get("delayed_min") or 0))
    except Exception:  # noqa: BLE001
        return 0.0


def _artifact_ms(obj: dict | None) -> float | None:
    """Epoch-ms of an artifact's `asof`, or None when absent/unparseable."""
    raw = str((obj or {}).get("asof") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000.0
    except Exception:  # noqa: BLE001
        return None


def _merge_quotes(dest: dict[str, dict], incoming: dict[str, dict],
                  incoming_ms: float | None) -> None:
    """Merge `incoming` into `dest`, keeping the FRESHER quote per ticker.

    NOT dict.update(). Source order used to decide the winner on the assumption
    that the fuller artifact is also the fresher one. On 2026-07-28 it was not:
    the VPS became the primary live-quote publisher (VPS_LIVE_PRIMARY=true), the
    GitHub live-quotes lane correctly stood down, and nothing repointed the
    `live-data` branch — so the tape gate kept loading a 2105-symbol snapshot
    that was SEVENTEEN HOURS old and let it overwrite the genuinely current
    heatmap and display quotes. Every signal then failed the 45-minute quote-age
    check ("quote for ROST is 452m old") and the desk network held everything it
    had. A stale source must never displace a fresh one, however complete it is.

    Freshness is the quote's own ts_ms when it carries one, else its artifact's
    asof. Unknown-vs-unknown keeps the incoming value, preserving the old
    source-order precedence exactly where no timestamp can decide it.
    """
    for tkr, q in incoming.items():
        prior = dest.get(tkr)
        if prior is None:
            dest[tkr] = q
            continue
        new_ms = q.get("ts_ms") or incoming_ms
        old_ms = prior.get("ts_ms") or prior.get("_artifact_ms")
        if new_ms is not None and old_ms is not None and float(new_ms) < float(old_ms):
            continue          # incoming is older — keep what we have
        dest[tkr] = q
    # Remember each entry's artifact time so a later merge can compare against a
    # quote that carries no ts_ms of its own (the heatmap tiles are pct-only).
    if incoming_ms is not None:
        for tkr in incoming:
            if dest.get(tkr) is not None and dest[tkr].get("ts_ms") is None:
                dest[tkr]["_artifact_ms"] = incoming_ms


def load_live_quotes(root: Path | str | None = None) -> dict[str, Any]:
    """Load the freshest available quote view.

    Returns {"quotes": {ticker: {price, prev_close, change_pct, ts_ms, source}},
             "asof": iso-str | None, "source": str, "feed_delay_min": float}.
    Per ticker the FRESHEST quote wins (see _merge_quotes); among equally-timed
    or untimed ones the old precedence holds: full snapshot > display > heatmap.

    ``feed_delay_min`` is the LARGEST delay any merged artifact declares for
    itself (0.0 when none does) — see :func:`_feed_delay_min`. It is reported,
    never applied here: a consumer decides whether its own freshness budget is
    measuring observation lag (and so must allow for the feed's delay) or
    absolute market time (and so must not).

    Never raises; empty quotes dict when nothing is readable.
    """
    r = Path(root) if root is not None else Path(".")
    quotes: dict[str, dict] = {}
    asof: str | None = None
    asof_ms: float | None = None
    src_used: list[str] = []
    feed_delay = 0.0

    heat = _read_json(r / _HEATMAP_REL)
    if heat:
        hq = _quotes_from_heatmap(heat)
        if hq:
            _merge_quotes(quotes, hq, _artifact_ms(heat))
            src_used.append("heatmap")
            feed_delay = max(feed_delay, _feed_delay_min(heat))

    for rel, label in ((_DISPLAY_REL, "display"), (_SNAPSHOT_REL, "snapshot")):
        obj = _read_json(r / rel)
        if obj:
            q = _quotes_from_snapshot(obj)
            if q:
                obj_ms = _artifact_ms(obj)
                _merge_quotes(quotes, q, obj_ms)
                src_used.append(label)
                feed_delay = max(feed_delay, _feed_delay_min(obj))
                # The reported `asof` is the NEWEST artifact seen, not the last
                # one read: it is the fallback age for every quote with no ts_ms
                # of its own, so taking a stale artifact's asof here would age
                # out fresh heatmap entries wholesale.
                if obj_ms is not None and (asof_ms is None or obj_ms > asof_ms):
                    asof, asof_ms = obj.get("asof"), obj_ms
                elif asof is None:
                    asof = obj.get("asof") or asof

    return {"quotes": quotes, "asof": asof, "source": "+".join(src_used) or "none",
            "feed_delay_min": feed_delay}


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

        # Market closed (weekend): no session has traded since the plan was built
        # off the last close, so a PRESENT quote (Friday's close) is not "stale" —
        # it is the last print. Neutralize the wall-clock staleness skip for
        # level-claim kinds so they verify against the last close instead of being
        # held. Everything else is deliberately unchanged: the adverse-move,
        # entry-distance and earnings checks below all still run (against the last
        # close), a MISSING quote still falls through to the normal hold (we won't
        # post a name we cannot verify at all), and same-day MOVE kinds
        # (mover/theme_list) are excluded so "today's mover" is never posted on a
        # non-trading day.
        if (
            quote is not None
            and stale
            and g.get("market_closed_mode", True)
            and kind in _CLOSED_LEVEL_KINDS
            and _market_is_closed(nowdt)
        ):
            stale = False

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
