"""Market-aware self-grader for the per-name POTENTIAL score — the piece that makes the
buy-readiness score EARN trust per market instead of asserting it.

  • append_name_calls(calls, market, asof) — append today's per-name POTENTIAL calls
    (ticker, score, tier, fuel, trigger + the as-of close `level`) to an append-only,
    point-in-time store, keep-FIRST per (date, ticker) so a stamped score is never
    overwritten / leaked. CN keeps its legacy path (data/china_name_score/calls.parquet);
    every other market is data/name_score/<market>_calls.parquet.
  • grade(market) — for every matured call, join the name's forward return (the market's
    close store) and score: buy-tier (primed/setting_up) hit-rate, cross-sectional rank-IC
    (score vs forward return), per-tier forward, by horizon. "accruing" until enough.

Until a market's scorecard shows a positive, stable rank-IC, that market's score is framed
as an EXPERIMENTAL timing/edge screen, never a validated probability — mirroring the honesty
gates in [[stock-conviction-profile]] and [[china-name-potential-score]].
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import grading  # W1c: shared next-bar/survivorship-aware grader
from lib import config, store

log = logging.getLogger(__name__)

_HORIZONS_D = (21, 63)                    # ~1 / 3 months
_BUY_TIERS = ("primed", "setting_up")    # the tiers the user would actually act on
# per-market per-name close store group. CN board tickers are per-name A-shares (.SS/.SZ)
# in data/china_stocks; data/china holds only the ~30 index/ETF parquets. The original
# mapping "CN" → "china" caused 0/N forward returns to resolve (all board tickers live in
# china_stocks, not china) — n_graded stayed 0 forever (same root cause as the #791
# china_standout_track bug, fixed W6-CN CN-1). CN now uses a tuple: read china_stocks
# first (per-name OHLC), fall back to china (ETFs / bench). All other markets use a single
# group string; _fwd_return handles both tuple and str via the resolution loop below.
_FWD_GROUP: dict[str, str | tuple[str, ...]] = {
    "US": "stocks",
    "CN": ("china_stocks", "china"),    # W0.3 fix: per-name A-shares live in china_stocks
    "HK": "hk",
    "CA": "canada",
    "INTL": "intl",
}


def _store_path(market: str):
    m = (market or "CN").upper()
    d = config.data_dir()
    if m == "CN":                       # legacy path — preserves the existing CN ledger
        return d / "china_name_score" / "calls.parquet"
    return d / "name_score" / f"{m.lower()}_calls.parquet"


_MAX_BAR_LAG_DAYS = 7  # calendar days a name's own last bar may lag the ledger stamp.
# The worst structural lag on the real NYSE calendar 2000-2026 is exactly 7 (the
# post-9/11-class 4-session closure: reopen stamp ← last bar one week back), which
# passes only because the test below is strict `>`; since 2015 the max is 4. Beyond 7
# the "call" is an echo of a dead or stale feed (store stopped / halt / delisting),
# not a market observation. Eleven US names were frozen this way when the gate
# shipped — SATS dead since 2026-06-18 (33 echo rows), QCOM stamped `setting_up`
# score-63 off a 24-day-stale store — see
# research/ADJUDICATION_20260803_ORCL_NAME_SCORE_FLATLINE.md. Accepted residual: a
# future market-wide closure that beats 7 calendar days would refuse one reopen-day
# stamp universe-wide (warned loudly below, self-heals the next session).


def append_name_calls(calls: list[dict], market: str = "CN", asof: str | None = None) -> int:
    """Append today's POTENTIAL calls for one market. Each call carries {ticker, score,
    tier, fuel, trigger} plus an as-of `level` (the day's close). Keep-FIRST per
    (date, ticker). Returns the ledger row count after the merge.

    A call may also carry `bar_asof` — the date of the name's OWN last price bar.
    When it lags `asof` by more than _MAX_BAR_LAG_DAYS the feed is dead and the call
    is refused (a frozen series re-stamped daily is a fabricated observation, and via
    the dead-name resolve path it could even be graded). `bar_asof` is admission-gate
    input only, never persisted; callers that don't pass it are un-gated (unchanged)."""
    if not calls or not asof:
        return 0
    rows = []
    stale: list[str] = []
    ungated: list[str] = []   # bar_asof present but unusable (NaT / unparseable / clock
    for c in calls:           # anomaly) — kept fail-open, but NEVER silently: a format
        tk = c.get("ticker")  # drift that darkened the gate must surface in the log.
        if not tk:
            continue
        ba = c.get("bar_asof")
        if ba is not None:
            lag = None
            try:
                ts = pd.Timestamp(ba)
                if not pd.isna(ts):
                    lag = (pd.Timestamp(asof) - ts).days
            except (TypeError, ValueError):
                pass
            if lag is None or lag < -1:      # -1 tolerates a tz-vs-UTC stamp slop
                ungated.append(str(tk))
            elif lag > _MAX_BAR_LAG_DAYS:
                stale.append(str(tk))
                continue
        rows.append({"date": str(asof), "ticker": str(tk), "score": c.get("score"),
                     "tier": c.get("tier"), "fuel": c.get("fuel"),
                     "trigger": c.get("trigger"), "level": c.get("level")})
    if stale:
        log.warning("name-score grader (%s): refused %d frozen-feed call(s) — last bar "
                    ">%dd behind %s: %s", market, len(stale), _MAX_BAR_LAG_DAYS, asof,
                    ", ".join(sorted(stale)[:12]))
    if ungated:
        log.warning("name-score grader (%s): staleness gate DARK for %d call(s) — "
                    "bar_asof unusable (NaT/unparseable/future): %s", market,
                    len(ungated), ", ".join(sorted(ungated)[:12]))
    if not rows:
        return 0
    try:
        new = pd.DataFrame(rows)
        p = _store_path(market)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True).drop_duplicates(
                subset=["date", "ticker"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("name-score grader (%s): append failed: %s", market, e)
        return 0


def _drop_frozen_echoes(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Quarantine pre-gate frozen-feed echoes from MEASUREMENT (the ledger itself is
    append-only PIT and is never mutated). A row is an echo iff it sits deeper than
    the closure-safe window inside a consecutive run of byte-identical `level` values
    for one ticker: weekend/holiday stamps legitimately repeat a close for ≤ ~4
    calendar days, so a run older than _MAX_BAR_LAG_DAYS from its own start can only
    be a feed that stopped printing while the scan kept stamping (98 such rows —
    18 of them buy-tier, e.g. QCOM `setting_up` score-63 — predate the admission
    gate; a store that later heals/backfills would otherwise grade those fabricated
    calls with real forward returns). Rows with no level are never quarantined.
    Returns (kept_rows, n_excluded); the caller PRINTS the count (disclosure, not
    fail-dark)."""
    if df.empty or "level" not in df.columns or "date" not in df.columns:
        return df, 0
    d = df.sort_values(["ticker", "date"], kind="stable")
    lv = d["level"]
    new_run = (d["ticker"].ne(d["ticker"].shift()) | lv.ne(lv.shift()) | lv.isna())
    run_start = pd.to_datetime(d["date"]).groupby(new_run.cumsum()).transform("first")
    age_d = (pd.to_datetime(d["date"]) - run_start).dt.days
    echo = (age_d > _MAX_BAR_LAG_DAYS) & lv.notna()
    return d.loc[~echo], int(echo.sum())


def _fwd_return(market: str, ticker: str, d0: pd.Timestamp, h: int) -> float | None:
    """Forward return of a call, NEXT-BAR filled + survivorship-aware (W1c, audit #15).

    Pre-W1c this did ``s.iloc[h] / s.iloc[0]`` — a SAME-BAR fill (the score's own as-of
    close is the denominator) and it silently dropped a name that delisted (``store.read``
    returns None → survivorship in the accountability loop). Now it routes through
    engine.grading: the call fires on d0's close but is FILLED on the next bar, the forward
    return is measured to h bars past that fill, and a delisted name is extended by its
    dead-name terminal close (US only for now — the dead-name store is US-side) so its loss
    is graded instead of vanishing."""
    try:
        # _FWD_GROUP may be a str (single group) or a tuple (ordered fallback list, first hit wins).
        # CN uses ("china_stocks", "china") so per-name A-shares resolve before the ETF store.
        _grp = _FWD_GROUP.get((market or "CN").upper(), "china")
        _groups = (_grp,) if isinstance(_grp, str) else _grp
        df = None
        for _g in _groups:
            df = store.read(_g, str(ticker))
            if df is not None and "close" in df:
                break
        s = pd.to_numeric(df["close"], errors="coerce").dropna() if (
            df is not None and "close" in df) else None
    except Exception:  # noqa: BLE001
        s = None
    # US has the 8-K bankruptcy dead-name store; other markets have none → resolve_series
    # simply returns the live series unchanged there.
    if (market or "").upper() == "US":
        try:
            s = grading.resolve_series(str(ticker), s)
        except Exception:  # noqa: BLE001
            pass
    if s is None or s.empty:
        return None
    s = s.sort_index()
    # Snap to the call bar (nearest bar <= d0), fill next bar, measure h bars past the fill.
    # NOTE: this credits the call to the score's OWN as-of bar even if the price series
    # begins after d0-slicing would; grading._snap_loc handles the nearest-prior mapping.
    return grading.grade_next_bar_return(s, str(pd.Timestamp(d0).date()), h)


def grade(market: str = "CN") -> dict | None:
    """Score every matured call for one market. {available, n_calls, n_graded, dates,
    by_horizon} where each horizon carries the buy-tier hit-rate, the cross-sectional
    rank-IC, and a per-tier forward breakdown."""
    m = (market or "CN").upper()
    p = _store_path(m)
    if not p.exists():
        return {"available": False, "market": m, "note": "no calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "market": m, "note": f"unreadable: {e}"}
    if df.empty:
        return {"available": False, "market": m, "note": "empty"}
    # frozen-feed echoes are excluded from measurement and the count is printed —
    # never silently absorbed into hit-rates (see _drop_frozen_echoes).
    df, n_frozen = _drop_frozen_echoes(df)
    if df.empty:
        return {"available": False, "market": m, "note": "all rows frozen-feed echoes",
                "n_frozen_excluded": n_frozen}

    out = {"available": True, "market": m, "n_calls": int(len(df)),
           "n_frozen_excluded": n_frozen,
           "dates": sorted(df["date"].dropna().unique().tolist()),
           "horizons_d": list(_HORIZONS_D), "by_horizon": {}}
    for h in _HORIZONS_D:
        recs = []
        for _i, row in df.iterrows():
            fr = _fwd_return(m, row["ticker"], pd.Timestamp(row["date"]), h)
            if fr is None:
                continue
            recs.append({"date": row["date"], "ticker": row["ticker"],
                         "score": row.get("score"), "tier": row.get("tier"), "fwd": fr})
        if len(recs) < 5:
            out["by_horizon"][f"{h}d"] = {"n": len(recs), "note": "accruing"}
            continue
        g = pd.DataFrame(recs)
        ics = []
        for _d, sub in g.groupby("date"):
            if sub["score"].nunique() >= 5:
                ics.append(float(sub["score"].rank().corr(sub["fwd"].rank())))
        buys = g[g["tier"].isin(_BUY_TIERS)]
        hit = float((buys["fwd"] > 0).mean()) if len(buys) else None
        by_tier = {}
        for lab, sub in g.groupby("tier"):
            if len(sub) >= 5:
                by_tier[lab] = {"n": int(len(sub)),
                                "mean_fwd": round(float(sub["fwd"].mean()), 4),
                                "pos_rate": round(float((sub["fwd"] > 0).mean()), 3)}
        out["by_horizon"][f"{h}d"] = {
            "n": int(len(g)),
            "buy_tier_hit_rate": round(hit, 3) if hit is not None else None,
            "rank_ic": round(float(np.mean(ics)), 4) if ics else None, "n_ic_dates": len(ics),
            "by_tier": by_tier,
        }
    out["n_graded"] = max((v.get("n", 0) for v in out["by_horizon"].values()), default=0)
    return out
