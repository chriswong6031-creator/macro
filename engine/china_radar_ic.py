"""CN Radar IC (Information Coefficient) grader — CN mirror of engine/radar_ic.py.

Grades the China divergence-radar signal (sector-ETF events in
data/china_radar/ledger.parquet) against realized CSI300-relative forward returns,
so the CN signal governor can read a CN radar track record.

How it works
------------
The CN radar fires SECTOR-LEVEL events (subject = sector_etf like '512200.SS'), NOT
per-ticker edge scores.  Each event has a ``sign`` ('positive'/'negative') and a
``signal_value``.  We grade the sector ETF's CSI300-relative forward return after
the event's ``fired_date``, signed by ``sign``:

    signed_score = signal_value × dir(sign)   (dir: positive→+1, negative→−1)

The rigorous path is the same daily-HAC signed-IC used by radar_ic: per-DATE
cross-sectional Spearman IC of (signed_score) vs fwd_rel_return, summarized by
engine.validation.ic_summary with periods_per_year=2*horizon (Newey-West lag=horizon).
The governor gates de-escalation on this — never the pooled Spearman.

HONESTY / DORMANCY
------------------
The CN ledger is sparse (~16 sector events across ~7 dates as of 2026-07-22).  The
daily-HAC needs ≥6 dated cross-sections EACH with ≥10 names for rank_ic to be
non-NaN — that bar will not be met for a long time.  ``ic_daily_hac`` legitimately
returns {n_days: <k>} and the governor stays dormant (trust=1.0).  This is correct
and expected.  We label pooled stats clearly "provisional / accruing" and never
pretend significance we haven't earned.

Output
------
``compute_ic`` writes ``data/china_hub/radar_ic.json`` and returns the same dict.
Schema "china_radar_ic.v1".  ``by_horizon`` map mirrors radar_ic.json so
_signal_governor._radar_reading('cn') can parse it without changes.

CONTEXT-ONLY — the output feeds the de-escalation-only governor.  It never sizes a
position, originates a signal, or escalates a score.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine import validation as V
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_radar_ic.v1"

# CSI300 ETF benchmark — same symbol used by china_radar.BENCH and china_radar_ledger
_BENCH = "510300.SS"

# Default horizons (calendar days).  Kept short since the ledger is daily-resolution.
_DEFAULT_HORIZONS = (5, 10, 21)

# Direction multiplier for sign field
_SIGN_DIR: dict[str, int] = {"positive": 1, "negative": -1}

# Output path (governor reads here via _REGIONS["cn"]["radar"])
_OUT_PATH = ("data", "china_hub", "radar_ic.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_ledger(root: Path) -> pd.DataFrame:
    """Load data/china_radar/ledger.parquet.  Returns empty DataFrame on error."""
    try:
        p = root / "data" / "china_radar" / "ledger.parquet"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_parquet(p)
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar_ic: ledger load failed (%s)", e)
        return pd.DataFrame()


def _close_series(ticker: str, root: Path) -> pd.Series | None:
    """Load close series for a CN ticker (sector ETF or 510300.SS benchmark).

    Tries data/china/<ticker>.parquet via lib.store, then
    data/china_hub/closes.parquet (china_search closes layer), then
    data/china_stocks/<ticker>.parquet as a final fallback.
    Returns a DatetimeIndex-sorted Series of close prices, or None.
    """
    try:
        from lib import store
        df = store.read("china", ticker)
        if df is not None and "close" in df.columns:
            s = df["close"].dropna().sort_index()
            if len(s) >= 2:
                return s
    except Exception:  # noqa: BLE001
        pass

    # Fallback: china_search closes.parquet (multi-column, one col per ticker)
    try:
        p = root / "data" / "china_search" / "closes.parquet"
        if p.exists():
            closes = pd.read_parquet(p)
            if ticker in closes.columns:
                s = closes[ticker].dropna()
                if not isinstance(s.index, pd.DatetimeIndex):
                    s.index = pd.to_datetime(s.index, errors="coerce")
                    s = s[s.index.notna()].sort_index()
                if len(s) >= 2:
                    return s
    except Exception:  # noqa: BLE001
        pass

    # Final fallback: per-stock parquet
    try:
        p = root / "data" / "china_stocks" / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["close"])
            s = df["close"].dropna()
            if not isinstance(s.index, pd.DatetimeIndex):
                s.index = pd.to_datetime(s.index, errors="coerce")
                s = s[s.index.notna()].sort_index()
            if len(s) >= 2:
                return s
    except Exception:  # noqa: BLE001
        pass

    return None


def _asof(series: "pd.Series", d: str) -> float | None:
    """Last close on or before date d."""
    try:
        sub = series[series.index <= pd.Timestamp(d)]
        return float(sub.iloc[-1]) if len(sub) else None
    except Exception:  # noqa: BLE001
        return None


def _fwd_rel_return(
    etf: str, root: Path, start_date: str, horizon_d: int,
    _bench_cache: dict | None = None,
) -> float | None:
    """CSI300-relative forward return of sector ETF from start_date over horizon_d calendar days.

    Returns None when price data does not cover the full horizon (event not matured) or on
    any price error.  Sign is positive when the ETF outperforms CSI300.
    """
    try:
        end_ts = (pd.Timestamp(start_date) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        etf_s = _close_series(etf, root)
        if _bench_cache is not None and "bench" in _bench_cache:
            bench_s = _bench_cache["bench"]
        else:
            bench_s = _close_series(_BENCH, root)
            if _bench_cache is not None:
                _bench_cache["bench"] = bench_s

        if etf_s is None or bench_s is None:
            return None
        # Coverage check — must have a close on or after end_ts
        if etf_s.index.max() < pd.Timestamp(end_ts):
            return None
        if bench_s.index.max() < pd.Timestamp(end_ts):
            return None

        e0 = _asof(etf_s, start_date)
        e1 = _asof(etf_s, end_ts)
        b0 = _asof(bench_s, start_date)
        b1 = _asof(bench_s, end_ts)
        if None in (e0, e1, b0, b1) or e0 <= 0 or b0 <= 0:
            return None
        return round((e1 / e0 - 1.0) - (b1 / b0 - 1.0), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("china_radar_ic: _fwd_rel_return(%s, %s): %s", etf, start_date, e)
        return None


def _daily_hac_signed_ic(enriched: list[dict], horizon_d: int) -> dict:
    """Daily-HAC signed IC for the CN radar — per-DATE cross-sectional Spearman IC of
    (signed_score) vs fwd_rel_return, Newey-West HAC t-stat at lag=horizon.

    The CN ledger is sector-level (typically 1-5 events per date), so V.rank_ic's ≥10
    names/date filter will block most cross-sections.  Returns {"n_days": k} when fewer
    than 6 dated ICs are available — the governor stays dormant in this regime.

    periods_per_year=2*horizon so ic_summary sets NW lag=horizon (its lag=ppy//2).
    """
    by_date: dict[str, list] = {}
    for r in enriched:
        d = _SIGN_DIR.get(r.get("sign", ""), 0)
        if not d:
            continue
        signed = r["signal_value"] * d
        by_date.setdefault(r["fired_date"], []).append((signed, r["fwd_rel_return"]))

    ics: list[float] = []
    for _, pairs in sorted(by_date.items()):
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        # rank_ic internally requires ≥10 names; we call it directly — NaN ⇒ skip
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(ys)) < 2:
            continue
        ic = V.rank_ic(xs, ys)
        if ic == ic:  # not NaN
            ics.append(ic)

    return V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6 else {"n_days": len(ics)}


def _pooled_dir_accuracy(enriched: list[dict]) -> dict:
    """Directional accuracy by sign: fraction of events where the signed relative return
    confirmed the bullish/bearish claim.  Clearly labelled provisional (accruing context).

    Returns {"positive": {...}, "negative": {...}} — the CN analog of radar_ic's by_state.
    """
    by_sign: dict[str, dict] = {}
    for sign_label in ("positive", "negative"):
        rows = [r for r in enriched if r.get("sign") == sign_label]
        n = len(rows)
        if n == 0:
            continue
        d = _SIGN_DIR[sign_label]
        correct = sum(1 for r in rows if r["fwd_rel_return"] * d > 0)
        mean_rel = sum(r["fwd_rel_return"] * d for r in rows) / n  # sign-adjusted
        by_sign[sign_label] = {
            "n": n,
            "dir_accuracy": round(correct / n, 3),
            "mean_signed_fwd_ret": round(mean_rel, 4),
        }
    return by_sign


# ---------------------------------------------------------------------------
# per-horizon computation
# ---------------------------------------------------------------------------

def _compute_ic_for_horizon(
    df: pd.DataFrame, root: Path, horizon_d: int, today_dt: date,
    bench_cache: dict,
) -> dict:
    """Compute IC stats for a single horizon over the CN sector-event ledger.

    Each row in df is a fired sector event.  We:
      1. Filter to events where fired_date is at least horizon_d calendar days before today.
      2. Compute CSI300-relative forward return (coverage check inside _fwd_rel_return).
      3. Assemble signed_score = signal_value * dir(sign).
      4. Report pooled IC (descriptive/provisional) + daily-HAC IC (the governor-facing stat).
      5. by_sign: directional accuracy by positive vs negative events.

    Never raises.  Returns the standard by_horizon block shape.
    """
    try:
        if df.empty:
            return _empty_horizon_block(horizon_d, f"Accruing — no events in ledger yet (horizon={horizon_d}d).")

        # Maturity: fired_date must be ≥ horizon_d calendar days before today
        today_ts = pd.Timestamp(today_dt)
        eligible = df[
            (today_ts - pd.to_datetime(df["fired_date"])).dt.days >= horizon_d
        ].copy()

        # Skip venue pairs (sector_etf is NaN) — no ETF-vs-benchmark path for them
        eligible = eligible[eligible["sector_etf"].notna()].copy()

        enriched: list[dict] = []
        for _, row in eligible.iterrows():
            etf = str(row["sector_etf"])
            fwd = _fwd_rel_return(etf, root, str(row["fired_date"]), horizon_d, bench_cache)
            if fwd is None:
                continue
            enriched.append({
                "fired_date": str(row["fired_date"]),
                "sector_etf": etf,
                "sign": str(row.get("sign", "")),
                "signal_value": float(row.get("signal_value") or 0.0),
                "fwd_rel_return": fwd,
            })

        n_matured = len(enriched)
        note_pfx = f"horizon={horizon_d}d, {n_matured} matured sector events"

        if n_matured < 3:
            return {
                "n_matured": n_matured,
                "ic_all": None,
                "ic_daily_hac": {"n_days": 0},
                "by_sign": {},
                "note": (
                    f"Accruing / dormant — {note_pfx}. "
                    f"Daily-HAC needs ≥6 dated cross-sections each with ≥10 names; "
                    f"CN radar is sector-level (~1-5 events/date) and sparse. "
                    f"Governor stays at trust=1.0 (identity) until far more events accrue."
                ),
            }

        # Pooled Spearman IC (signed score vs fwd_rel_return) — descriptive/provisional
        signed_scores = [r["signal_value"] * _SIGN_DIR.get(r["sign"], 0) for r in enriched]
        rets = [r["fwd_rel_return"] for r in enriched]
        # Remove rows with zero direction (unknown sign)
        pairs = [(s, ret) for s, ret in zip(signed_scores, rets) if s != 0]
        if len(pairs) >= 3:
            xs, ys = zip(*pairs)
            ic_all = _spearman_ic(list(xs), list(ys))
        else:
            ic_all = None

        # Rigorous daily-HAC — will be {n_days: k} with k < 6 for sparse CN data
        ic_daily_hac = _daily_hac_signed_ic(enriched, horizon_d)

        by_sign = _pooled_dir_accuracy(enriched)

        hac_dormant = "n_days" in ic_daily_hac  # True = not yet gradeable
        if hac_dormant:
            n_days_so_far = ic_daily_hac.get("n_days", 0)
            status = (
                f"ACCRUING / DORMANT — {note_pfx}. "
                f"Daily-HAC: {n_days_so_far} dated cross-sections so far (need ≥6 each with ≥10 events). "
                f"Pooled IC={ic_all} is PROVISIONAL (overlap-inflated; not used by governor). "
                f"Governor stays at trust=1.0 until the HAC gate clears. "
                f"CONTEXT-ONLY — never a trade signal."
            )
        else:
            mean_ic = ic_daily_hac.get("mean_ic")
            t_hac = ic_daily_hac.get("t_hac")
            status = (
                f"{note_pfx}. Daily-HAC IC={mean_ic} (t={t_hac}). "
                f"CONTEXT-ONLY — never a trade signal."
            )

        return {
            "n_matured": n_matured,
            "ic_all": ic_all,
            "ic_daily_hac": ic_daily_hac,
            "by_sign": by_sign,
            "note": status,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("china_radar_ic: _compute_ic_for_horizon(%d) failed: %s", horizon_d, e)
        return _empty_horizon_block(horizon_d, f"error ({e}) — accruing, degrade-safe.")


def _spearman_ic(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation. Returns None if n < 3."""
    n = len(xs)
    if n < 3:
        return None
    try:
        def ranks(v: list[float]) -> list[float]:
            indexed = sorted(enumerate(v), key=lambda t: t[1])
            r: list[float] = [0.0] * n
            i = 0
            while i < len(indexed):
                j = i
                while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
                    j += 1
                avg = (i + j) / 2 + 1
                for k in range(i, j + 1):
                    r[indexed[k][0]] = avg
                i = j + 1
            return r

        rx, ry = ranks(xs), ranks(ys)
        mx, my = sum(rx) / n, sum(ry) / n
        num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
        den = math.sqrt(
            sum((rx[i] - mx) ** 2 for i in range(n))
            * sum((ry[i] - my) ** 2 for i in range(n))
        )
        return round(num / den, 4) if den > 0 else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# empty result helpers
# ---------------------------------------------------------------------------

def _empty_horizon_block(horizon_d: int, note: str) -> dict:
    return {
        "n_matured": 0,
        "ic_all": None,
        "ic_daily_hac": {"n_days": 0},
        "by_sign": {},
        "note": note,
    }


def _empty_result(as_of: str, n_events: int, note: str) -> dict:
    horizons = list(_DEFAULT_HORIZONS)
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_at": _now_iso(),
        "n_events": n_events,
        "n_matured": 0,
        "ic_all": None,
        "note": note,
        "by_horizon": {str(h): _empty_horizon_block(h, note) for h in horizons},
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def compute_ic(
    today: date | str | None = None,
    horizons: tuple[int, ...] = _DEFAULT_HORIZONS,
    root: Path | None = None,
) -> dict:
    """Grade the CN divergence-radar sector-event ledger against CSI300-relative
    forward returns. Writes data/china_hub/radar_ic.json and returns the dict.

    Schema "china_radar_ic.v1" — ``by_horizon`` map is the same shape as radar_ic.json
    so signal_governor._radar_reading('cn') can parse it without changes.  Each
    horizon block carries:
      * n_matured: count of events that have reached the horizon AND have price coverage.
      * ic_all: pooled Spearman IC (signed_score vs fwd_rel_return) — PROVISIONAL.
      * ic_daily_hac: ic_summary output {mean_ic, t_hac, n, ...} when ≥6 dated
        cross-sections each with ≥10 names; else {"n_days": k} (dormant path).
      * by_sign: directional accuracy for positive and negative events.
      * note: honest status string.

    DEGRADE-NEVER-RAISE: no ledger / empty ledger / missing price data → valid dict
    with n_matured=0, ic_daily_hac={"n_days":0}, never raises.

    CONTEXT-ONLY: output feeds the de-escalation-only CN governor.
    Nothing here sizes a position or escalates a signal.
    """
    try:
        root = Path(root) if root else config.ROOT
        today_dt = pd.Timestamp(today).date() if today else date.today()
        today_str = today_dt.isoformat()

        df = _load_ledger(root)
        n_events = len(df)

        bench_cache: dict = {}  # shared CSI300 series cache across horizon calls

        by_horizon: dict[str, dict] = {}
        for h in horizons:
            by_horizon[str(h)] = _compute_ic_for_horizon(df, root, h, today_dt, bench_cache)

        # Top-level summary uses the shortest horizon block (most events matured)
        primary_h = min(horizons)
        primary = by_horizon[str(primary_h)]
        n_matured = primary["n_matured"]
        ic_all = primary["ic_all"]
        note = primary["note"]

        result: dict = {
            "schema": SCHEMA,
            "as_of": today_str,
            "generated_at": _now_iso(),
            "n_events": n_events,
            "n_matured": n_matured,  # top-level = shortest-horizon matured count
            "ic_all": ic_all,
            "note": note,
            "by_horizon": by_horizon,
        }

        # Persist to data/china_hub/radar_ic.json
        try:
            out_p = root.joinpath(*_OUT_PATH)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            log.info(
                "china_radar_ic: wrote %s — n_events=%d n_matured=%d",
                out_p, n_events, n_matured,
            )
        except Exception as we:  # noqa: BLE001
            log.warning("china_radar_ic: write failed: %s", we)

        return result

    except Exception as e:  # noqa: BLE001
        log.warning("china_radar_ic: compute_ic failed: %s", e)
        as_of = (today.isoformat() if hasattr(today, "isoformat") else str(today or date.today()))
        return _empty_result(as_of, 0, f"compute_ic error ({e}) — accruing, degrade-safe.")


# ---------------------------------------------------------------------------
# __main__ convenience (mirrors radar_ic pattern)
# ---------------------------------------------------------------------------

def main() -> None:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")
    result = compute_ic()
    print(json.dumps({
        k: result[k]
        for k in ("schema", "as_of", "n_events", "n_matured", "ic_all", "note")
    }, indent=2, default=str))
    for h, blk in sorted(result.get("by_horizon", {}).items()):
        hac = blk.get("ic_daily_hac", {})
        n_days = hac.get("n", hac.get("n_days", 0))
        print(f"  h={h}d: n_matured={blk['n_matured']} ic_all={blk['ic_all']} "
              f"hac_n_days={n_days} dormant={'n_days' in hac}")


if __name__ == "__main__":
    main()
