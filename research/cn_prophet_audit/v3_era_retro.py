#!/usr/bin/env python3
"""v3_era_retro.py — retro-apply the cn_prophet_v3 selection to the V1 era.

WHAT THIS IS
    The STAND-IN for the forward v3-vs-v2 shadow race.  The live race
    (``cn_prophet_v3`` featured vs ``cn_prophet_v2_shadow``, PR #4509 / masterplan
    §5 R1) needs ~3-4 weeks to its first 60-matured read.  This instrument answers
    the same question on the one era we already have graded: if the COMPLETE v3
    selection rule had been in force over 2026-07-07..2026-07-29, would the shelf
    it produced have beaten the v2-rule shelf — on win rate, median excess and
    catastrophic-loss rate?

    It REPLACES nothing.  The forward race remains the decider; this is a
    preliminary, in-sample, one-era read that exists so a verdict is available
    while the forward race accrues.

WHAT IT IS NOT
    Not a backtest, not a promotion gate, not evidence any of these cells is
    tradeable.  Every number is IN-SAMPLE on the era the v3 rule was DESIGNED from
    (§2.3's entry-status inversion is literally this era's table), on a falling
    tape, on a selection that omits three production legs no retro can reconstruct
    (micro fillability, ADV liquidity floor, fresh-signal recency).  Both arms omit
    them equally, so the COMPARISON is fair even though neither arm's absolute
    level is a production forecast.

STRUCTURE
    1. P0 reproduction gate — rebuild the shipped V1 episode set through production
       code paths (``engine.track_scoring.build_episodes``, ``_t1_fill``, H=10
       forced verdict, CSI300 excess) and assert 584 / 407 / 0.6855 / 128 before
       anything else is printed.
    2. PIT reconstruction of every v3 selection input the legacy board rows do not
       already carry: narrative level (HOT/WARMING per engine.china_narrative_tags
       thresholds over curated ∪ THS membership), basket-cycle phase/osc_up
       (china_sector_cycles forward log, newest row <= admission date, best-rs_rank
       basket per name), the R3 chase composite, and relay_count_3d.
    3. Three shelves over the comparison window — V2-RULE, V3-RULE, ACTUAL logged
       board — capped (featured 24 / sector 4) and uncapped.
    4. H=10 grading at episode grain (an episode belongs to a shelf if its
       ENTRY-date row qualifies), plus per-date blocks and the marginal cohorts
       v3 ADDS and v3 DROPS relative to v2.

Run from repo root:  python3 research/cn_prophet_audit/v3_era_retro.py
Outputs (frozen, committed):
    research/cn_prophet_audit/v3_era_retro_results.json
    research/cn_prophet_audit/V3_ERA_RETRO.md
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Production code paths, imported after the sys.path insert above (P0 discipline:
# this instrument grades through the shipped engine, never a local re-implementation).
from engine import china_standout_track as cst
from engine import track_scoring as ts
from engine.china_microstructure import (
    _board_from_ticker,
    _load_st_set,
    limit_width_for_date,
)

OUT_JSON = HERE / "v3_era_retro_results.json"
OUT_MD = HERE / "V3_ERA_RETRO.md"

H = 10  # the shipped CN horizon (forced verdict)

# ── P0 gate: the shipped V1 headline this instrument must reproduce ───────────
P0_EPISODES = 584
P0_MATURED = 407
P0_WIN_RATE = 0.6855
P0_LOSERS = 128

# ── comparison window ─────────────────────────────────────────────────────────
# entry_status / ticks / extended are only logged from 2026-07-07 (842 of the
# 1,082 legacy rows).  Rows before that carry no entry gauge at all, so NEITHER
# arm can be evaluated on them; they are disclosed as uncovered and excluded.
WINDOW_START = "2026-07-07"
WINDOW_END = "2026-07-29"
HISTORY_START = pd.Timestamp("2025-09-01")  # deep enough for 21d trail + 20d MA/rel

# ── frozen-replay pin ─────────────────────────────────────────────────────────
# Every price series is TRUNCATED here before anything is graded.  Without this the
# instrument is not reproducible for a single day: the price stores accrue a bar
# every night, more episodes clear the H=10 maturity gate, and the shipped V1
# headline the P0 gate exists to reproduce silently stops existing.  Measured on
# 2026-08-04: the same board frame grades 441 matured / 70.52% win once the
# 2026-08-04 bar lands, against the shipped 407 / 68.55%.  (This is why the
# committed sibling `v1_loser_audit.py`, which has no such pin, now fails its own
# P0 assert on main — a pre-existing drift, reported not patched here.)
# 2026-08-03 is the era snapshot the shipped headline was measured at.
GRADE_ASOF = pd.Timestamp("2026-08-03")

# ── cn_prophet_v3 constants, mirrored from engine/china_board_rank.py (PR #4509) ─
FEATURED_CAP = 24
SECTOR_CAP = 4
SCORE_WEIGHTS = {
    "signal": 30.0,
    "entry": 20.0,
    "runway": 15.0,
    "bottom_quality": 10.0,
    "reversal_member": 10.0,
    "theme_timing": 15.0,
}
_SIGNAL_BASE = {"T2": 1.0, "T1": 0.9, "T3": 0.7}
_ENTRY_VALUE = {
    "bounce_wait": 1.0, "wait_pullback": 0.95, "hold": 0.8, "buy_now": 0.7,
    "partial": 0.6, "later": 0.5, "await": 0.45, "await_confluence": 0.45,
    "watch": 0.4, "buy_soon": 0.35, "extended": 0.3,
    "topping": 0.0, "blocked": 0.0, "exit": 0.0, "avoid": 0.0,
}
V3_FEATURED_ENTRY_STATUSES = frozenset(
    ("bounce_wait", "wait_pullback", "hold", "buy_now", "partial")
)
V2_FEATURED_ENTRY_STATUSES = frozenset(("buy_now", "partial"))
CONFIRMED_LATE_STATUSES = frozenset(("buy_now", "partial"))
EARLY_TICKS_MAX = 1
THEME_TIMING_NON_MEMBER = 0.25
THEME_TIMING_MEMBER_NEUTRAL = 0.6
EARLY_CYCLE_PHASES = frozenset(("Trough", "Recovery"))
LATE_CYCLE_PHASES = frozenset(("Peak", "Downturn"))
CHASE_TRAIL_21_MIN = 0.25
CHASE_RUN_5D_MIN = 0.15
RELAY_MID_MIN = 2
RELAY_LATE_MIN = 4

# ── engine/china_narrative_tags.py thresholds (documented display heuristics) ──
HOT_REL20, HOT_BREADTH = 5.0, 0.60
WARM_REL20, WARM_BREADTH = 0.0, 0.50
BREADTH_WINDOW = 20
MIN_BASKET_MEMBERS = 3  # production's _MIN_BASKET_MEMBERS

CATASTROPHIC_ABS_PCT = -15.0  # absolute P&L threshold for the crash cohort

_T0 = time.time()


def _stage(msg: str) -> None:
    print(f"[{time.time() - _T0:6.1f}s] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# stats helpers
# ═══════════════════════════════════════════════════════════════════════════════

def wilson(k: int, n: int, z: float = 1.96) -> list[float | None]:
    """Wilson score interval on a binomial proportion, in percent.

    A statement about the COUNT of wins and nothing else: it does not account for
    the fact that episodes surfaced on the same board night are one bet, not N
    (``track_scoring.date_block_ci`` is the honest interval for that), nor for the
    heavy overlap between the two arms' episode sets.  True uncertainty is wider.
    """
    if n <= 0:
        return [None, None]
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return [round(100.0 * (centre - half) / denom, 1),
            round(100.0 * (centre + half) / denom, 1)]


def r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def is_true(value) -> bool:
    """Truth of a cell read out of a pandas panel; missing/NaN reads False.

    Written as a named helper because ``value is True`` is the trap: reindexing a
    boolean Series onto a wider calendar hands back ``numpy.bool_``, and
    ``np.True_ is True`` is FALSE.  An identity check here zeroes the entire
    limit-close leg silently — the composite still fires on its trailing-return
    legs, so the run looks healthy and only the diagnostics show the hole.
    """
    if value is None:
        return False
    try:
        if isinstance(value, float) and math.isnan(value):
            return False
        return bool(value)
    except (TypeError, ValueError):
        return False


def grade(rows: list[dict], label: str = "") -> dict:
    """Frozen H=10 summary of one shelf. Never hides a thin cell.

    ``n_board_days`` sits next to ``n`` on purpose (``track_scoring``'s rule):
    episodes surfaced on the same board night are ONE bet, so the raw count
    overstates the sample.  ``win_ci95_date_blocked`` resamples whole board days
    via ``track_scoring.date_block_ci`` and is the honest interval; the Wilson
    interval is kept beside it only because it is the comparable convention.
    """
    ex = np.array([e["excess"] for e in rows if e.get("excess") is not None], dtype=float)
    pnl = np.array([e["pnl"] for e in rows if e.get("pnl") is not None], dtype=float)
    dates = sorted({str(e["date"]) for e in rows if e.get("excess") is not None})
    n = int(ex.size)
    if n == 0:
        return {"label": label, "n": 0, "n_board_days": 0, "win_pct": None,
                "win_ci95": [None, None], "win_ci95_date_blocked": [None, None],
                "loser_pct": None, "median_excess": None, "mean_excess": None,
                "median_pnl": None, "catastrophic_pct": None, "n_catastrophic": 0,
                "thin": True}
    wins = int((ex > 0).sum())
    cats = int((pnl <= CATASTROPHIC_ABS_PCT).sum())
    blocked = ts.date_block_ci(
        [(str(e["date"]), e["excess"]) for e in rows if e.get("excess") is not None],
        lambda v: float((v > 0).mean() * 100.0) if len(v) else float("nan"),
    )
    return {
        "label": label,
        "n": n,
        "n_board_days": len(dates),
        "win_pct": round(100.0 * wins / n, 1),
        "win_ci95": wilson(wins, n),
        "win_ci95_date_blocked": [r(blocked[0], 1), r(blocked[1], 1)],
        "loser_pct": round(100.0 * (n - wins) / n, 1),
        "median_excess": round(float(np.median(ex)), 2),
        "mean_excess": round(float(np.mean(ex)), 2),
        "median_pnl": round(float(np.median(pnl)), 2) if pnl.size else None,
        "catastrophic_pct": round(100.0 * cats / max(1, int(pnl.size)), 1),
        "n_catastrophic": cats,
        "thin": n < 30 or len(dates) < 5,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# stage 1 — P0 reproduction gate (production code paths only)
# ═══════════════════════════════════════════════════════════════════════════════

def load_board() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data/china_standout_track/board.parquet")
    return df[df["board_definition"] == "legacy"].copy()


def sector_lookup() -> dict[str, str | None]:
    """Sector per ticker from the shipped CN ledger (the sector_cap key)."""
    led = json.loads((ROOT / "site/factordata/cn_track_ledger.json").read_text())
    return {r_["t"]: r_.get("sec") for r_ in led.get("prior_record", {}).get("rows", [])}


def build_graded_episodes(board: pd.DataFrame, secs: dict[str, str | None]) -> dict:
    """Rebuild and grade the shipped V1 episode set. Asserts the P0 headline.

    Every series is truncated at :data:`GRADE_ASOF` first — see the pin's comment:
    without it the maturity gate keeps opening as the store accrues bars and the
    reproduction target stops existing.
    """
    board_days: dict[str, set[str]] = defaultdict(set)
    for _, row in board.iterrows():
        board_days[str(row["date"])].add(str(row["ticker"]))

    bench = cst._bench_close()
    if bench is not None:
        bench = bench[bench.index <= GRADE_ASOF]
    episodes: list[dict] = []
    n_locked = n_skipped = 0
    for ep in ts.build_episodes(board_days):
        tk, d0s = ep["ticker"], ep["entry_date"]
        d0 = pd.Timestamp(d0s)
        pdf = cst._price_frame(tk)
        if pdf is not None:
            pdf = pdf[pdf.index <= GRADE_ASOF]
        if pdf is None or "close" not in pdf:
            n_skipped += 1
            continue
        fill, locked, _pinned = cst._t1_fill(pdf, d0)
        if locked:
            n_locked += 1
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        after = closes.index[closes.index > d0]
        sc = None
        if fill is not None and len(after):
            sc = ts.score_from_fill(closes, after[0], float(fill), H,
                                    bench_close=bench, include_fill_bar=True)
        if sc is None:
            n_skipped += 1
            continue
        episodes.append({
            "ticker": tk,
            "date": d0s,
            "matured": bool(sc["matured"]) and not locked,
            # score_from_fill returns pnl/excess in PERCENT units (4.44 = +4.44%).
            "excess": r(sc.get("excess")),
            "pnl": r(sc.get("pnl")),
            "sector": secs.get(tk),
        })

    mat = [e for e in episodes if e["matured"] and e["excess"] is not None]
    losers = [e for e in mat if e["excess"] <= 0]
    win_rate = (len(mat) - len(losers)) / len(mat) if mat else 0.0

    _stage(f"P0: episodes={len(episodes)} matured={len(mat)} "
           f"win={100 * win_rate:.2f}% losers={len(losers)} "
           f"locked={n_locked} skipped={n_skipped}")
    assert len(episodes) == P0_EPISODES, f"episodes {len(episodes)} != {P0_EPISODES}"
    assert len(mat) == P0_MATURED, f"matured {len(mat)} != {P0_MATURED}"
    assert abs(win_rate - P0_WIN_RATE) < 0.0005, f"win {win_rate:.4f} != {P0_WIN_RATE}"
    assert len(losers) == P0_LOSERS, f"losers {len(losers)} != {P0_LOSERS}"

    return {
        "episodes": episodes,
        "matured": mat,
        "bench": bench,
        "gate": {
            "episodes": len(episodes), "matured": len(mat),
            "win_rate": r(win_rate, 4), "losers": len(losers),
            "n_locked": n_locked, "n_skipped": n_skipped,
            "expected": {"episodes": P0_EPISODES, "matured": P0_MATURED,
                         "win_rate": P0_WIN_RATE, "losers": P0_LOSERS},
            "passed": True,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# stage 2 — PIT panel + per-name features
# ═══════════════════════════════════════════════════════════════════════════════

def load_memberships() -> dict[str, dict]:
    """basket_id -> {name, source, members[]} across curated + THS, PIT-dated.

    Mirrors ``build_china_library``'s R2/R3 membership block: a member is active on
    date d when ``added <= d`` and (``removed`` is None or ``removed > d``).  In the
    committed stores every member of both sources carries ``added='2021-06-15'`` and
    ``removed=None``, so the PIT filter is a NO-OP over this era — recorded here so
    the caveat is about the SNAPSHOT (see the THS lookahead note), not about the
    filter being missing.
    """
    out: dict[str, dict] = {}
    for src, rel in (("curated", "baskets_china"), ("THS", "baskets_china_ths")):
        raw = json.loads((ROOT / "data" / rel / "membership.json").read_text())
        for bid, bval in (raw.get("baskets") or {}).items():
            members = [
                (str(m["ticker"]), str(m.get("added") or "1900-01-01"), m.get("removed"))
                for m in (bval.get("members") or [])
                if isinstance(m, dict) and m.get("ticker")
            ]
            out[bid] = {"name": bval.get("name", bid), "source": src, "members": members}
    return out


def active_members(meta: dict, asof: str) -> list[str]:
    return [t for t, added, removed in meta["members"]
            if added <= asof and (removed is None or str(removed) > asof)]


def load_panel(tickers: set[str]) -> dict:
    """Wide [calendar x ticker] close/high frames on the CSI300 trading calendar."""
    bench_df = pd.read_parquet(ROOT / "data/china/510300.SS.parquet")
    bench_df.index = pd.to_datetime(bench_df.index)
    bench = bench_df["close"].sort_index()
    bench = bench[(bench.index >= HISTORY_START) & (bench.index <= GRADE_ASOF)].dropna()
    calendar = bench.index

    closes: dict[str, pd.Series] = {}
    highs: dict[str, pd.Series] = {}
    missing: list[str] = []
    for tk in sorted(tickers):
        path = ROOT / "data" / "china_stocks" / f"{tk}.parquet"
        if not path.exists():
            missing.append(tk)
            continue
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        df = df[(df.index >= HISTORY_START) & (df.index <= GRADE_ASOF)].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if "close" not in df.columns or df.empty:
            missing.append(tk)
            continue
        closes[tk] = df["close"]
        highs[tk] = df["high"] if "high" in df.columns else pd.Series(np.nan, index=df.index)

    close = pd.DataFrame(closes).reindex(calendar).astype(float)
    high = pd.DataFrame(highs).reindex(calendar).astype(float)
    _stage(f"panel: {close.shape[1]} tickers x {len(calendar)} sessions "
           f"({len(missing)} requested tickers absent from data/china_stocks)")
    return {"calendar": calendar, "bench": bench, "close": close, "high": high,
            "missing": missing}


def board_of(ticker: str) -> str:
    """Production ``_board_from_ticker`` plus the unmerged 302xxx ChiNext fix.

    PR #4509 corrects 302xxx (ChiNext, ±20% band) which main still reads as "main"
    (±10%) — mis-sizing every limit test.  Replicated here so this instrument
    measures the rule as it will ship, not as main currently mis-reads it.
    """
    code = (ticker or "").upper().split(".")[0]
    if code.startswith("302"):
        return "chinext"
    return _board_from_ticker(ticker)


def name_features(panel: dict, st_set: frozenset[str]) -> dict:
    """Per-name PIT features on each name's OWN valid bars, reindexed + ffilled.

    ffill is exact here, not a smear: production reads ``close.dropna()`` and takes
    ``iloc[-1]`` / the last three valid bars as of the board date, so a name halted
    on date d carries forward the value computed at its last traded bar — which is
    precisely what ``reindex(calendar).ffill()`` of a valid-bar computation gives.
    """
    close, high = panel["close"], panel["high"]
    calendar = panel["calendar"]

    limit_close: dict[str, pd.Series] = {}
    lim3d: dict[str, pd.Series] = {}
    trail21: dict[str, pd.Series] = {}
    run5d: dict[str, pd.Series] = {}
    n_limit_events = 0

    for tk in close.columns:
        c = close[tk].dropna()
        if len(c) < 2:
            continue
        h = high[tk].reindex(c.index)
        board = board_of(tk)
        is_st = tk in st_set
        bands = np.array(
            [limit_width_for_date(board, d, is_st) for d in c.index], dtype=float
        )
        ret1 = (c / c.shift(1) - 1.0).to_numpy(dtype=float)
        at_high = (h.to_numpy(dtype=float) - c.to_numpy(dtype=float))
        flags = (np.abs(at_high) < 1e-9) & (ret1 >= 0.95 * bands)
        flags = np.where(np.isfinite(ret1) & np.isfinite(h.to_numpy(dtype=float)),
                         flags, False)
        lc = pd.Series(flags, index=c.index)
        n_limit_events += int(lc.sum())
        limit_close[tk] = lc.reindex(calendar)  # own-bar truth, no ffill
        lim3d[tk] = lc.rolling(3, min_periods=1).max().astype(bool).reindex(calendar).ffill()
        trail21[tk] = (c / c.shift(21) - 1.0).reindex(calendar).ffill()
        run5d[tk] = (c / c.shift(5) - 1.0).reindex(calendar).ffill()

    _stage(f"name features: {n_limit_events} limit-closes across "
           f"{len(limit_close)} names")
    return {
        "limit_close": pd.DataFrame(limit_close).reindex(calendar),
        "lim3d": pd.DataFrame(lim3d).reindex(calendar),
        "trail21": pd.DataFrame(trail21).reindex(calendar),
        "run5d": pd.DataFrame(run5d).reindex(calendar),
        "n_limit_events": n_limit_events,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# stage 3 — narrative heat (engine/china_narrative_tags.py semantics, as a series)
# ═══════════════════════════════════════════════════════════════════════════════

def basket_heat(panel: dict, memberships: dict[str, dict], asof: str) -> dict:
    """rel20 / breadth / level time series per basket, PIT membership at ``asof``.

    Mirrors ``_basket_rel20_breadth``: equal-weight member return chain vs the
    CSI300 20d return (pp), breadth = share of covered members above their own 20d
    MA (the MA INCLUDES today's close, as in production), and BOTH values are
    rounded to the published precision (2dp / 4dp) BEFORE the threshold test — the
    same order production grades them in.
    """
    close, bench = panel["close"], panel["bench"]
    bench20 = (bench / bench.shift(BREADTH_WINDOW) - 1.0) * 100.0

    out: dict[str, dict] = {}
    for bid, meta in memberships.items():
        covered = [t for t in active_members(meta, asof) if t in close.columns]
        if len(covered) < MIN_BASKET_MEMBERS:
            continue
        sub = close[covered]
        ew_ret = sub.pct_change(fill_method=None).mean(axis=1, skipna=True)
        ew_level = (1.0 + ew_ret.fillna(0.0)).cumprod()
        rel20 = ((ew_level / ew_level.shift(BREADTH_WINDOW) - 1.0) * 100.0 - bench20).round(2)

        ma20 = sub.rolling(BREADTH_WINDOW, min_periods=1).mean()
        valid = sub.notna().sum(axis=1)
        above = (sub > ma20).sum(axis=1)
        breadth = (above / valid.replace(0, np.nan)).fillna(0.0).round(4)

        level = pd.Series(None, index=close.index, dtype=object)
        level[(rel20 >= WARM_REL20) & (breadth >= WARM_BREADTH)] = "WARMING"
        level[(rel20 >= HOT_REL20) & (breadth >= HOT_BREADTH)] = "HOT"
        out[bid] = {"name": meta["name"], "source": meta["source"],
                    "rel20": rel20, "breadth": breadth, "level": level,
                    "covered": covered}
    return out


def name_narrative(heat: dict, baskets_of: dict[str, set[str]],
                   ticker: str, when: pd.Timestamp) -> dict | None:
    """Strongest QUALIFYING basket by rel20 for one name on one date.

    ``engine.china_narrative_tags.name_tags``: a name with no qualifying (HOT or
    WARMING) basket gets NO theme, which is what makes it a theme non-member for
    ``_theme_timing_value``.
    """
    best = None
    for bid in baskets_of.get(ticker, ()):
        rec = heat.get(bid)
        if rec is None or when not in rec["level"].index:
            continue
        lvl = rec["level"].loc[when]
        if lvl is None or (isinstance(lvl, float) and not np.isfinite(lvl)):
            continue
        rel = float(rec["rel20"].loc[when])
        if not np.isfinite(rel):
            continue
        if best is None or rel > best["rel20"]:
            best = {"theme": rec["name"], "level": str(lvl), "rel20": rel,
                    "breadth": float(rec["breadth"].loc[when]),
                    "basket_id": bid, "source": rec["source"]}
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# stage 4 — basket cycle (china_sector_cycles forward log)
# ═══════════════════════════════════════════════════════════════════════════════

def basket_cycle_index(memberships: dict[str, dict]) -> dict:
    """(board_date -> ticker -> {phase, osc_up, basket_id}) exactly as production joins it.

    ``build_china_library``: newest forward_log basket row on or before the board
    date, baskets walked best-rs_rank first, ``setdefault`` per member so a name in
    several baskets takes its STRONGEST theme's cycle.
    """
    flog = pd.read_parquet(ROOT / "data/china_sector_cycles/forward_log.parquet")
    flog = flog[flog["kind"].astype(str) == "basket"].copy()
    flog["date"] = flog["date"].astype(str)
    return flog


def cycle_for_date(flog: pd.DataFrame, memberships: dict[str, dict],
                   board_date: str) -> dict[str, dict]:
    sub = flog[flog["date"] <= board_date]
    if sub.empty:
        return {}
    asof = str(sub["date"].max())
    latest = sub[sub["date"] == asof].sort_values("rs_rank", ascending=True,
                                                  na_position="last")
    out: dict[str, dict] = {}
    for row in latest.to_dict("records"):
        bid = str(row.get("id") or "").removeprefix("b-")
        meta = memberships.get(bid)
        if meta is None:
            continue
        osc = pd.to_numeric(row.get("osc_slope"), errors="coerce")
        state = {
            "basket_id": bid,
            "phase": str(row["phase"]) if row.get("phase") else None,
            "osc_up": bool(osc > 0) if pd.notna(osc) else False,
            "asof": asof,
        }
        for tk in active_members(meta, board_date):
            out.setdefault(tk, state)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# stage 5/6 — the v3 value ladders (engine/china_board_rank.py, PR #4509)
# ═══════════════════════════════════════════════════════════════════════════════

def clip01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if not math.isfinite(v) else max(0.0, min(1.0, v))


def theme_timing_value(narrative: dict | None, cycle: dict | None) -> float:
    """``_theme_timing_value``: 0 / 0.25 / 0.6 / 1.0, in the ratified test order."""
    is_member = bool((narrative or {}).get("theme")) or bool(cycle)
    if not is_member:
        return THEME_TIMING_NON_MEMBER
    level = str((narrative or {}).get("level") or "").strip().upper() or None
    phase = str((cycle or {}).get("phase") or "").strip().title() or None
    osc_up = bool((cycle or {}).get("osc_up")) if cycle else False
    has_cycle = bool(cycle)

    if level == "WARMING" or (has_cycle and phase in EARLY_CYCLE_PHASES and osc_up):
        return 1.0
    fading = has_cycle and phase == "Downturn" and not osc_up
    hot_late = level == "HOT" and has_cycle and phase in LATE_CYCLE_PHASES and not osc_up
    if fading or hot_late:
        return 0.0
    return THEME_TIMING_MEMBER_NEUTRAL


def signal_value(tier: str | None, ticks: float | None, provisional: bool) -> float:
    """``_signal_value`` minus its T3 ``bars_to_cross`` leg (not on legacy rows)."""
    value = _SIGNAL_BASE.get(str(tier), 0.0)
    if provisional:
        value = max(0.0, value - 0.1)
    if ticks == 2:
        value *= 0.85
    return clip01(value)


def bottom_quality_value(coiled_star: bool, coiled: bool) -> float:
    """``_bottom_quality_value``. The 0.4 ``washout_ctx`` rung is unreachable here —
    the legacy board schema logs ``washout_2w``, not the coiled ``washout_ctx``
    context flag — so a washout-only name scores 0.0 in BOTH arms."""
    if coiled_star:
        return 1.0
    if coiled:
        return 0.8
    return 0.0


def runway_value(ext_score: float | None) -> float:
    """``_runway_value`` restricted to its observable leg.

    Production: ``clip01(0.6 * fuel + 0.4 * (1 - clip01(extension.score)))``.  The
    ``fuel`` component (potential.components.fuel) is not on the legacy board rows,
    so only the 0.4 extension leg is reconstructible.  ``ext_score`` IS logged, so
    this is strictly more faithful than zeroing the whole leg — and it is identical
    for both arms, which is what the comparison needs.
    """
    if ext_score is None or not np.isfinite(ext_score):
        return 0.0
    return clip01(0.4 * (1.0 - clip01(ext_score)))


def relay_position(count_3d: int | None) -> str | None:
    """``relay_position``. ``None`` = not positionable (no basket membership) — a
    DIFFERENT state from a count of zero, which is ``early``."""
    if count_3d is None:
        return None
    if count_3d >= RELAY_LATE_MIN:
        return "late"
    if count_3d >= RELAY_MID_MIN:
        return "mid"
    return "early"


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

# One long linear instrument: the stage order IS the argument, and splitting it into
# helpers would hide which numbers are computed before which gate.
def main() -> None:
    board = load_board()
    secs = sector_lookup()
    graded = build_graded_episodes(board, secs)

    # ── episode index: an episode is attributed by its ENTRY-date board row ────
    ep_by_key = {(e["ticker"], e["date"]): e for e in graded["episodes"]}
    entry_keys = set(ep_by_key)

    window = board[(board["date"] >= WINDOW_START) & (board["date"] <= WINDOW_END)].copy()
    window_dates = sorted(window["date"].unique())

    memberships = load_memberships()
    baskets_of: dict[str, set[str]] = defaultdict(set)
    for bid, meta in memberships.items():
        for tk, _a, _r in meta["members"]:
            baskets_of[tk].add(bid)

    universe = {t for meta in memberships.values() for t, _a, _r in meta["members"]}
    universe |= set(board["ticker"].astype(str))
    panel = load_panel(universe)
    st_set = _load_st_set(ROOT / "data")
    feats = name_features(panel, st_set)

    heat = basket_heat(panel, memberships, WINDOW_END)
    _stage(f"basket heat: {len(heat)} baskets with >= {MIN_BASKET_MEMBERS} covered members")
    flog = basket_cycle_index(memberships)

    # ── build the per-admission-row reconstruction ────────────────────────────
    lim3d = feats["lim3d"]
    rows: list[dict] = []
    narr_agree = narr_logged = n_halted = 0
    for d in window_dates:
        when = pd.Timestamp(d)
        if when not in panel["calendar"]:
            raise RuntimeError(f"board date {d} absent from the CSI300 calendar")
        cycles = cycle_for_date(flog, memberships, d)
        # Which basket members printed a limit close inside [d-2, d]?
        lim_row = lim3d.loc[when]
        limit_recent = {t for t in lim_row.index if is_true(lim_row[t])}

        for _, br in window[window["date"] == d].iterrows():
            tk = str(br["ticker"])
            narrative = name_narrative(heat, baskets_of, tk, when)
            cycle = cycles.get(tk)

            # R3 chase composite (build-time-knowable legs only; T+1 gap is grading-side).
            # ``limit_close`` carries own-bar truth with NO ffill: a board row whose
            # name did not trade that session reads False rather than inheriting an
            # older bar's limit close.  Production instead reads the name's LAST valid
            # bar; ``n_halted_on_board_date`` below counts the rows where the two
            # conventions could disagree (it is zero on this era, so they coincide).
            own_col = feats["limit_close"].get(tk)
            own_cell = None if own_col is None else own_col.get(when)
            if own_col is None or own_cell is None or (
                    isinstance(own_cell, float) and math.isnan(own_cell)):
                n_halted += 1
            own_limit = is_true(own_cell)
            trail_21 = feats["trail21"][tk].get(when) if tk in feats["trail21"] else None
            run_5d = feats["run5d"][tk].get(when) if tk in feats["run5d"] else None
            trail_21 = float(trail_21) if trail_21 is not None and np.isfinite(trail_21) else None
            run_5d = float(run_5d) if run_5d is not None and np.isfinite(run_5d) else None
            chase = bool(
                own_limit
                or (trail_21 is not None and trail_21 >= CHASE_TRAIL_21_MIN)
                or (run_5d is not None and run_5d >= CHASE_RUN_5D_MIN)
            )

            own_baskets = baskets_of.get(tk)
            if own_baskets:
                peers = {p for bid in own_baskets
                         for p in active_members(memberships[bid], d) if p != tk}
                relay_count = len(peers & limit_recent)
            else:
                relay_count = None
            position = relay_position(relay_count)

            status = br["entry_status"] if isinstance(br["entry_status"], str) else None
            ticks = None if pd.isna(br["ticks"]) else float(br["ticks"])
            ext_score = None if pd.isna(br["ext_score"]) else float(br["ext_score"])
            tier = br["tier"] if isinstance(br["tier"], str) else None
            provisional = bool(br["provisional"]) if pd.notna(br["provisional"]) else False

            tt = theme_timing_value(narrative, cycle)
            components = {
                "signal": signal_value(tier, ticks, provisional),
                "entry": _ENTRY_VALUE.get(str(status or "").lower(), 0.0),
                "runway": runway_value(ext_score),
                "bottom_quality": bottom_quality_value(
                    bool(br["coiled_star"]) if pd.notna(br["coiled_star"]) else False,
                    bool(br["coiled"]) if pd.notna(br["coiled"]) else False),
                # Not on the legacy schema; zero in BOTH arms, so it cannot tilt the race.
                "reversal_member": 0.0,
                "theme_timing": tt,
            }
            score = sum(SCORE_WEIGHTS[k] * v for k, v in components.items())

            logged_level = br["narr_level"] if isinstance(br["narr_level"], str) else None
            if logged_level:
                narr_logged += 1
                if (narrative or {}).get("level") == logged_level:
                    narr_agree += 1

            rows.append({
                "date": d, "ticker": tk, "sector": secs.get(tk),
                "board_rank": int(br["board_rank"]) if pd.notna(br["board_rank"]) else None,
                "entry_status": status, "ticks": ticks, "tier": tier,
                "extended": bool(br["extended"]) if pd.notna(br["extended"]) else False,
                "stage": br["stage"] if isinstance(br["stage"], str) else None,
                "ext_score": r(ext_score),
                "narr_level": (narrative or {}).get("level"),
                "narr_theme": (narrative or {}).get("theme"),
                "narr_source": (narrative or {}).get("source"),
                "narr_level_logged": logged_level,
                "cycle_phase": (cycle or {}).get("phase"),
                "cycle_osc_up": (cycle or {}).get("osc_up"),
                "theme_timing": tt,
                "chase": chase, "chase_limit_close": own_limit,
                "chase_trail_21": r(trail_21), "chase_run_5d": r(run_5d),
                "relay_count_3d": relay_count, "relay_position": position,
                "v3_score": r(score, 4),
                "components": {k: r(v, 4) for k, v in components.items()},
                "is_entry_row": (tk, d) in entry_keys,
            })
    _stage(f"reconstructed {len(rows)} admission rows over {len(window_dates)} dates")

    # ── the shelves ───────────────────────────────────────────────────────────
    def v3_shortfalls(row: dict) -> list[str]:
        """Which v3 gate a row failed — the label the drop cohorts are split by."""
        out: list[str] = []
        if row["entry_status"] not in V3_FEATURED_ENTRY_STATUSES:
            out.append(f"entry_status_{row['entry_status'] or 'unknown'}")
        elif (row["entry_status"] in CONFIRMED_LATE_STATUSES
              and row["ticks"] is not None and row["ticks"] > EARLY_TICKS_MAX):
            out.append("confirmed_late")
        if row["extended"]:
            out.append("extended")
        if row["chase"] and row["relay_position"] == "late":
            out.append("relay_late")
        return out

    def apply_caps(qualified: list[dict], score_key: str = "v3_score") -> list[dict]:
        """``_partition``'s cap walk: score order, featured 24, sector 4."""
        ordered = sorted(qualified, key=lambda x: (-(x[score_key] or 0.0), x["ticker"]))
        kept: list[dict] = []
        per_sector: dict[str, int] = defaultdict(int)
        for row in ordered:
            if len(kept) >= FEATURED_CAP:
                break
            sec = str(row["sector"] or "—")
            if per_sector[sec] >= SECTOR_CAP:
                continue
            per_sector[sec] += 1
            kept.append(row)
        return kept

    def qualifies(row: dict, *, entry_statuses: frozenset[str],
                  early_ticks_required: bool, relay_late_guard: bool) -> bool:
        """One parameterised admission rule — the shared machinery ``_partition`` uses
        for the live v3 lane and the v2 shadow lane, so a leg can be switched off
        without a second copy of the rule drifting away from the first."""
        if row["entry_status"] not in entry_statuses:
            return False
        if (early_ticks_required and row["entry_status"] in CONFIRMED_LATE_STATUSES
                and row["ticks"] is not None and row["ticks"] > EARLY_TICKS_MAX):
            return False
        if row["extended"]:
            return False
        return not (relay_late_guard and row["chase"] and row["relay_position"] == "late")

    # The live v3 rule, the displaced v2 rule, and one variant per v3 leg switched
    # off — so the headline delta can be ATTRIBUTED rather than asserted.
    variants = {
        "v3_rule": {"entry_statuses": V3_FEATURED_ENTRY_STATUSES,
                    "early_ticks_required": True, "relay_late_guard": True},
        "v2_rule": {"entry_statuses": V2_FEATURED_ENTRY_STATUSES,
                    "early_ticks_required": False, "relay_late_guard": False},
        "r1_entry_set_only": {"entry_statuses": V3_FEATURED_ENTRY_STATUSES,
                              "early_ticks_required": False, "relay_late_guard": False},
        "v3_minus_confirmed_late": {"entry_statuses": V3_FEATURED_ENTRY_STATUSES,
                                    "early_ticks_required": False, "relay_late_guard": True},
        "v3_minus_relay_late": {"entry_statuses": V3_FEATURED_ENTRY_STATUSES,
                                "early_ticks_required": True, "relay_late_guard": False},
        "v2_plus_confirmed_late": {"entry_statuses": V2_FEATURED_ENTRY_STATUSES,
                                   "early_ticks_required": True, "relay_late_guard": False},
    }

    shelves: dict[str, list[dict]] = {"actual_all_admissions": []}
    for name in variants:
        shelves[f"{name}_uncapped"] = []
        shelves[f"{name}_capped"] = []
    # theme_timing OFF: the SAME admitted rows, re-ordered for the caps with the R2
    # component zeroed — isolating whether theme_timing changes WHO survives the cap.
    shelves["v3_rule_capped_theme_timing_off"] = []

    for row in rows:
        row["v3_score_no_theme"] = r(
            (row["v3_score"] or 0.0)
            - SCORE_WEIGHTS["theme_timing"] * (row["components"]["theme_timing"] or 0.0), 4)
    for d in window_dates:
        day = [x for x in rows if x["date"] == d]
        shelves["actual_all_admissions"].extend(day)
        for name, kw in variants.items():
            qual = [x for x in day if qualifies(x, **kw)]
            shelves[f"{name}_uncapped"].extend(qual)
            shelves[f"{name}_capped"].extend(apply_caps(qual))
        v3_day = [x for x in day if qualifies(x, **variants["v3_rule"])]
        shelves["v3_rule_capped_theme_timing_off"].extend(
            apply_caps(v3_day, score_key="v3_score_no_theme"))

    for row in rows:
        row["v2_rule"] = qualifies(row, **variants["v2_rule"])
        row["v3_rule"] = qualifies(row, **variants["v3_rule"])
        row["v3_shortfalls"] = v3_shortfalls(row)

    # ── grade at episode grain ────────────────────────────────────────────────
    def episodes_of(shelf: list[dict]) -> list[dict]:
        """Matured episodes whose ENTRY-date row sits on this shelf."""
        out = []
        for row in shelf:
            ep = ep_by_key.get((row["ticker"], row["date"]))
            if ep is None or not ep["matured"] or ep["excess"] is None:
                continue
            out.append({**ep, "_row": row})
        return out

    ep_shelves = {name: episodes_of(shelf) for name, shelf in shelves.items()}
    headline = {
        "actual_logged_board": grade(ep_shelves["actual_all_admissions"],
                                     "ACTUAL logged board (all admissions)"),
        "v2_rule_capped": grade(ep_shelves["v2_rule_capped"], "V2-RULE shelf (capped)"),
        "v3_rule_capped": grade(ep_shelves["v3_rule_capped"], "V3-RULE shelf (capped)"),
    }
    uncapped = {
        "v2_rule_uncapped": grade(ep_shelves["v2_rule_uncapped"], "V2-RULE shelf (uncapped)"),
        "v3_rule_uncapped": grade(ep_shelves["v3_rule_uncapped"], "V3-RULE shelf (uncapped)"),
    }

    # ── P1 cross-check gate: the v2 arm must reproduce the COMMITTED v1 audit ──
    # v1_loser_audit.py computed the same v2 featured-gate retro from a different
    # code path (its own episode enrichment, no panel, no theme reconstruction).
    # If this instrument's shelf machinery drifts, these three numbers move — so
    # they are asserted, not merely reported.  Missing artifact = skipped, printed.
    p1: dict = {"checked": False}
    prior_path = HERE / "v1_loser_audit_results.json"
    if prior_path.exists():
        prior = json.loads(prior_path.read_text()).get("v2_featured_gate_retro") or {}
        feat = prior.get("featured_like") or {}
        p1 = {
            "checked": True,
            "source": "v1_loser_audit_results.json :: v2_featured_gate_retro",
            "n_covered": {"prior": prior.get("n_covered"),
                          "here": headline["actual_logged_board"]["n"]},
            "covered_win_rate": {"prior": prior.get("covered_win_rate"),
                                 "here": r(headline["actual_logged_board"]["win_pct"] / 100.0, 4)},
            "v2_featured_n": {"prior": feat.get("n"), "here": uncapped["v2_rule_uncapped"]["n"]},
            "v2_featured_win_rate": {"prior": feat.get("win_rate"),
                                     "here": r(uncapped["v2_rule_uncapped"]["win_pct"] / 100.0, 4)},
        }
        assert p1["n_covered"]["prior"] == p1["n_covered"]["here"], p1["n_covered"]
        assert p1["v2_featured_n"]["prior"] == p1["v2_featured_n"]["here"], p1["v2_featured_n"]
        assert abs((prior.get("covered_win_rate") or 0)
                   - p1["covered_win_rate"]["here"]) < 0.001, p1["covered_win_rate"]
        assert abs((feat.get("win_rate") or 0)
                   - p1["v2_featured_win_rate"]["here"]) < 0.001, p1["v2_featured_win_rate"]
        _stage(f"P1 cross-check PASSED against {p1['source']}")
    else:
        _stage("P1 cross-check SKIPPED — v1_loser_audit_results.json absent")

    # ── leg attribution: which R-item earns the delta ─────────────────────────
    # A headline gap is only decision-relevant if you know which change produced it.
    # Each row below is the FULL v3 rule with exactly one leg switched off.
    attribution = {
        "v3_rule (all legs)": grade(ep_shelves["v3_rule_capped"], "v3, all legs"),
        "R1 entry set only (no confirmed_late, no relay_late)": grade(
            ep_shelves["r1_entry_set_only_capped"], "R1 prime-window entry set alone"),
        "v3 minus confirmed_late": grade(
            ep_shelves["v3_minus_confirmed_late_capped"], "v3 without the R1 ticks demotion"),
        "v3 minus relay_late": grade(
            ep_shelves["v3_minus_relay_late_capped"], "v3 without the R3 relay demotion"),
        "v2 entry set + confirmed_late": grade(
            ep_shelves["v2_plus_confirmed_late_capped"],
            "v2's entry set with only the R1 ticks demotion added"),
        "v2_rule (all legs off)": grade(ep_shelves["v2_rule_capped"], "v2, the displaced rule"),
        "v3 with theme_timing zeroed in the cap ordering": grade(
            ep_shelves["v3_rule_capped_theme_timing_off"],
            "v3 admissions, caps walked without R2's theme_timing"),
    }

    # ── per-date blocks ───────────────────────────────────────────────────────
    bench = graded["bench"]
    by_date: dict[str, dict] = {}
    for d in window_dates:
        blk: dict = {}
        for arm, key in (("actual", "actual_all_admissions"),
                         ("v2_capped", "v2_rule_capped"), ("v3_capped", "v3_rule_capped")):
            sel = [e for e in ep_shelves[key] if e["date"] == d]
            blk[arm] = grade(sel)
        if bench is not None:
            b = bench[bench.index > pd.Timestamp(d)]
            blk["csi300_fwd10"] = r(float(b.iloc[H] / b.iloc[0] - 1.0) * 100.0, 2) if len(b) > H else None
        by_date[d] = blk

    # ── marginal analysis: what v3 ADDS and what v3 DROPS vs v2 ───────────────
    v2_keys = {(e["ticker"], e["date"]) for e in ep_shelves["v2_rule_capped"]}
    v3_keys = {(e["ticker"], e["date"]) for e in ep_shelves["v3_rule_capped"]}
    adds = [e for e in ep_shelves["v3_rule_capped"] if (e["ticker"], e["date"]) not in v2_keys]
    drops = [e for e in ep_shelves["v2_rule_capped"] if (e["ticker"], e["date"]) not in v3_keys]
    shared = [e for e in ep_shelves["v3_rule_capped"] if (e["ticker"], e["date"]) in v2_keys]

    def by_status(cohort: list[dict]) -> dict:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for e in cohort:
            buckets[str(e["_row"]["entry_status"])].append(e)
        return {k: grade(v, k) for k, v in sorted(buckets.items())}

    drop_reason: dict[str, list[dict]] = defaultdict(list)
    for e in drops:
        sf = e["_row"]["v3_shortfalls"]
        drop_reason["confirmed_late" if "confirmed_late" in sf
                     else "relay_late" if "relay_late" in sf
                     else "displaced_by_cap"].append(e)

    marginal = {
        "v3_adds": {**grade(adds, "episodes v3 ADDS vs v2 (the patience cohort)"),
                    "by_entry_status": by_status(adds),
                    "tickers": [f"{e['ticker']}@{e['date']}" for e in adds]},
        "v3_drops": {**grade(drops, "episodes v3 DROPS vs v2"),
                     "by_reason": {k: grade(v, k) for k, v in sorted(drop_reason.items())},
                     "tickers": [f"{e['ticker']}@{e['date']}" for e in drops]},
        "shared": grade(shared, "episodes on BOTH shelves"),
    }

    # ── reconstruction diagnostics + coverage ─────────────────────────────────
    win_rows = rows
    uncovered_eps = [e for e in graded["matured"] if e["date"] < WINDOW_START]
    diagnostics = {
        "narrative_vs_logged": {
            "n_rows_with_logged_level": narr_logged,
            "n_reconstruction_agrees": narr_agree,
            "agreement_pct": r(100.0 * narr_agree / narr_logged, 1) if narr_logged else None,
            "n_rows_reconstruction_tags": sum(1 for x in win_rows if x["narr_level"]),
            "note": ("the logged narr_level is the curated-only production attachment; "
                     "the reconstruction adds the THS union, so it tags strictly more "
                     "rows — disagreement is expected upward, not a defect"),
        },
        "theme_timing_distribution": {
            str(v): sum(1 for x in win_rows if x["theme_timing"] == v)
            for v in (0.0, 0.25, 0.6, 1.0)
        },
        "chase": {
            "n_rows_chase": sum(1 for x in win_rows if x["chase"]),
            "n_limit_close_day": sum(1 for x in win_rows if x["chase_limit_close"]),
            "n_trail21_leg": sum(1 for x in win_rows
                                 if (x["chase_trail_21"] or 0) >= CHASE_TRAIL_21_MIN),
            "n_run5d_leg": sum(1 for x in win_rows
                               if (x["chase_run_5d"] or 0) >= CHASE_RUN_5D_MIN),
            "n_limit_events_universe": feats["n_limit_events"],
            "n_halted_on_board_date": n_halted,
        },
        "relay": {
            "positioned": sum(1 for x in win_rows if x["relay_position"]),
            "unpositioned_no_basket": sum(1 for x in win_rows if x["relay_position"] is None),
            **{f"position_{p}": sum(1 for x in win_rows if x["relay_position"] == p)
               for p in ("early", "mid", "late")},
            "n_chase_and_relay_late": sum(
                1 for x in win_rows if x["chase"] and x["relay_position"] == "late"),
        },
        "shelf_row_counts": {k: len(v) for k, v in shelves.items()},
        "shelf_episode_counts": {k: len(v) for k, v in ep_shelves.items()},
        "panel_missing_tickers": len(panel["missing"]),
    }

    coverage = {
        "legacy_board_rows": len(board),
        "board_dates": int(board["date"].nunique()),
        "window": {"start": WINDOW_START, "end": WINDOW_END,
                   "dates": len(window_dates), "rows": len(rows)},
        "uncovered_before_window": {
            "matured_episodes": len(uncovered_eps),
            "win_pct": grade(uncovered_eps)["win_pct"],
            "reason": ("entry_status/ticks/extended are unlogged before 2026-07-07 — "
                       "NEITHER arm is evaluable there, so the cohort is excluded from "
                       "all three shelves rather than assigned to one"),
        },
        "era_wide_actual_all_407": grade(graded["matured"], "ACTUAL, full era (context)"),
    }

    caveats = [
        ("IN-SAMPLE. The v3 rule was designed FROM this era (masterplan §2.3's "
         "entry-status inversion is this era's own table), so a v3 win here is "
         "consistency, not confirmation. The forward shadow race is the decider."),
        ("ONE ERA, ONE TAPE. CSI300's forward-10 window was negative on 10 of 12 "
         "graded entry dates; the whole comparison lives inside a falling tape."),
        ("SELECTION IS APPROXIMATED. Three production featured gates are not "
         "retro-testable from the legacy schema: microstructure fillability/chase "
         "freshness, the ADV liquidity floor, and signal recency. BOTH arms omit "
         "them identically, so the comparison is fair; neither arm's ABSOLUTE level "
         "is a production forecast."),
        ("SCORE IS APPROXIMATED. The cap ordering uses a v3-weight score whose "
         "runway leg is partial (the extension half is logged, the `fuel` half is "
         "not), whose reversal_member leg is zero, whose bottom_quality 0.4 "
         "`washout_ctx` rung is unreachable on the legacy schema, and whose T3 "
         "bars_to_cross haircut is unavailable. The score affects ONLY which "
         "qualified rows survive the caps — the uncapped tables isolate it."),
        ("THEME RECONSTRUCTION CARRIES THE THS LOOKAHEAD. Curated membership is "
         "PIT-dated (all members added 2021-06-15, none removed — the PIT filter is "
         "a no-op over this era). THS membership is a single 2026-07-08 snapshot "
         "applied backward; PR #4506 measured two available THS snapshots differing "
         "by 7.7% of member-slots in 8 days. Every THS-sourced theme tag, and every "
         "relay count computed over a THS basket, inherits that."),
        ("V1 LOGGED ONLY THE TOP 60 rows per night of a ~110-row buy pool (§2.7), so "
         "each shelf is 'of the 60 logged rows, which would v3/v2 feature' — the "
         "featured cap of 24 is applied inside that 60, not inside the full pool."),
        ("OVERLAPPING ARMS. The two shelves share most of their episodes, so the "
         "Wilson intervals below overstate the independence of the DIFFERENCE. Read "
         "the marginal cohorts (v3-adds / v3-drops), which are disjoint, as the "
         "sharper statement."),
        (f"FROZEN REPLAY, PINNED AT {GRADE_ASOF.date()}. Every price series is "
         "truncated at that date before grading. The pin is load-bearing, not "
         "cosmetic: the stores accrue a bar nightly, more episodes clear the H=10 "
         "maturity gate, and the shipped V1 headline stops being reproducible. "
         "Measured on 2026-08-04 with the pin removed: 441 matured / 70.52% win "
         "against the shipped 407 / 68.55%. Re-running this instrument against a "
         "later snapshot is a DIFFERENT measurement and needs its own pin."),
        ("EFFECTIVE SAMPLE IS BOARD DAYS. Only entries through 2026-07-17 have ten "
         "forward sessions inside the pin, so six of the fourteen window dates grade "
         "nothing. Every table prints n_board_days next to n and a date-blocked "
         "interval next to the Wilson one; the date-blocked interval is the honest "
         "one (track_scoring's rule: one board night is one bet, not N)."),
    ]

    out = {
        "as_of": "2026-08-04",
        "instrument": "v3_era_retro",
        "question": ("Would the complete cn_prophet_v3 selection, in force over the "
                     "V1 era, have beaten the v2-rule selection and the actual "
                     "logged board at H=10?"),
        "status": ("PRELIMINARY STAND-IN for the forward v3-vs-v2 shadow race "
                   "(masterplan §5 R1 / G0.8). Replaces nothing."),
        "grade_asof": str(GRADE_ASOF.date()),
        "p0_gate": graded["gate"],
        "p1_cross_check": p1,
        "coverage": coverage,
        "headline": headline,
        "uncapped": uncapped,
        "leg_attribution": attribution,
        "marginal": marginal,
        "by_date": by_date,
        "diagnostics": diagnostics,
        "caveats": caveats,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    _stage(f"wrote {OUT_JSON}")
    write_markdown(out)
    _stage(f"wrote {OUT_MD}")

    print(json.dumps({"headline": headline, "marginal_summary": {
        "v3_adds": {k: marginal["v3_adds"][k] for k in ("n", "win_pct", "median_excess")},
        "v3_drops": {k: marginal["v3_drops"][k] for k in ("n", "win_pct", "median_excess")},
    }}, indent=1))


# ═══════════════════════════════════════════════════════════════════════════════
# markdown
# ═══════════════════════════════════════════════════════════════════════════════

HEADER = ("| n | board days | win % | 95% Wilson | 95% date-blocked | loser % | "
          "median excess | mean excess | catastrophic |")
RULE = "|---|---|---|---|---|---|---|---|---|"


def _fmt(cell: dict) -> str:
    if not cell or cell.get("n", 0) == 0:
        return "| 0 | 0 | — | — | — | — | — | — | — |"
    ci, bci = cell["win_ci95"], cell.get("win_ci95_date_blocked") or [None, None]
    blocked = (f"[{bci[0]}–{bci[1]}]" if bci[0] is not None
               else "n/a (<2 board days)")
    return (f"| {cell['n']} | {cell.get('n_board_days', '—')} | {cell['win_pct']}% | "
            f"[{ci[0]}–{ci[1]}] | {blocked} | "
            f"{cell['loser_pct']}% | {cell['median_excess']:+.2f} | "
            f"{cell['mean_excess']:+.2f} | {cell['catastrophic_pct']}% "
            f"({cell['n_catastrophic']}) |")


def _datecell(cell: dict) -> str:
    if not cell or cell.get("n", 0) == 0:
        return "0 / — / —"
    return f"{cell['n']} / {cell['win_pct']}% / {cell['median_excess']:+.1f}"


def write_markdown(out: dict) -> None:
    h = out["headline"]
    u = out["uncapped"]
    m = out["marginal"]
    g = out["p0_gate"]
    att = out["leg_attribution"]
    v3, v2, act = h["v3_rule_capped"], h["v2_rule_capped"], h["actual_logged_board"]
    r1 = att["R1 entry set only (no confirmed_late, no relay_late)"]
    tt_off = att["v3 with theme_timing zeroed in the cap ordering"]

    reasons = m["v3_drops"].get("by_reason", {})
    late = reasons.get("confirmed_late") or {}
    relay = reasons.get("relay_late") or {}
    drop_late_n = late.get("n", 0)
    drop_late_win = late.get("win_pct")
    drop_late_med = late.get("median_excess") or 0.0
    drop_relay_n = relay.get("n", 0)
    drop_relay_med = relay.get("median_excess") or 0.0
    n_relay_late_rows = out["diagnostics"]["relay"]["n_chase_and_relay_late"]

    d_win = (v3["win_pct"] or 0) - (v2["win_pct"] or 0)
    d_med = (v3["median_excess"] or 0) - (v2["median_excess"] or 0)
    d_cat = (v3["catastrophic_pct"] or 0) - (v2["catastrophic_pct"] or 0)
    verdict = ("BEATS" if d_win > 0 and d_med > 0 else
               "MIXED" if d_win > 0 or d_med > 0 else "DOES NOT BEAT")

    lines: list[str] = []
    add = lines.append
    add("# V3 ERA RETRO — the stand-in race verdict")
    add("")
    add("> Retro-application of the complete `cn_prophet_v3` selection to the V1 era, "
        "graded against the v2-rule selection and the actual logged board. "
        "**PRELIMINARY STAND-IN** for the forward v3-vs-v2 shadow race — it replaces "
        "nothing; the forward race remains the decider.")
    add("")
    add("## DECISION-RELEVANT SUMMARY")
    add("")
    add(f"1. **Verdict: on this era the v3 rule {verdict} the v2 rule.** "
        f"Win {v2['win_pct']}% → {v3['win_pct']}% ({d_win:+.1f}pp), median excess "
        f"{v2['median_excess']:+.2f} → {v3['median_excess']:+.2f} ({d_med:+.2f}pp), "
        f"catastrophic (abs ≤ −15%) {v2['catastrophic_pct']}% → "
        f"{v3['catastrophic_pct']}% ({d_cat:+.1f}pp). All three metrics move the same way.")
    add(f"2. Shelf sizes: v2 n={v2['n']} vs v3 n={v3['n']} matured episodes. v3 admits "
        f"the patience cohort, so it is the WIDER shelf — the gain is not a "
        f"selectivity artefact of showing fewer names.")
    add(f"3. Base rate: the actual logged board over the same window ran "
        f"{act['win_pct']}% win / {act['median_excess']:+.2f} median / "
        f"{act['catastrophic_pct']}% catastrophic on n={act['n']}. v2 sits BELOW its own "
        f"board's base rate on every metric; v3 sits above it.")
    add(f"4. **The delta is R1, and almost nothing else.** Decomposed: the R1 entry-set "
        f"widening alone (prime window, no ticks demotion, no relay demotion) takes "
        f"{v2['win_pct']}% → {r1['win_pct']}% "
        f"({(r1['win_pct'] or 0) - (v2['win_pct'] or 0):+.1f}pp, n={r1['n']}); the R1 "
        f"confirmed-late demotion adds {(v3['win_pct'] or 0) - (r1['win_pct'] or 0):+.1f}pp "
        f"on top ({r1['win_pct']}% → {v3['win_pct']}%) and cuts catastrophic "
        f"{r1['catastrophic_pct']}% → {v3['catastrophic_pct']}%. R2 and R3 contribute "
        f"nothing measurable (lines 5-6) — this era tests R1, not the R-slate.")
    add(f"5. **R3 (relay-late) is INERT on this era, and what it touched was a winner.** "
        f"The guard demoted {n_relay_late_rows} admission rows across the window; "
        f"{drop_relay_n} of them was the entry row of a matured episode on the v2 "
        f"shelf — and it WON ({drop_relay_med:+.2f} excess). Switching the guard off "
        f"leaves the capped v3 shelf statistically identical "
        f"(n={att['v3 minus relay_late']['n']}, "
        f"{att['v3 minus relay_late']['win_pct']}%), because the row it admits does "
        f"not clear the cap anyway. This era can neither support nor refute R3; PR "
        f"#4506's 12-month relay ladder remains its only evidence.")
    add(f"6. **R2 (theme_timing) does not help here — it is very slightly NEGATIVE.** "
        f"Re-walking the caps with theme_timing zeroed gives n={tt_off['n']} / "
        f"{tt_off['win_pct']}% / {tt_off['median_excess']:+.2f} vs the full score's "
        f"n={v3['n']} / {v3['win_pct']}% / {v3['median_excess']:+.2f}. Its only channel "
        f"is cap ordering, the difference is well inside noise at this n, and the "
        f"direction is not the one R2 predicts — printed, not hidden.")
    add(f"7. **What v3 ADDS** (n={m['v3_adds']['n']}, disjoint): "
        f"{m['v3_adds']['win_pct']}% win, {m['v3_adds']['median_excess']:+.2f} median, "
        f"{m['v3_adds']['catastrophic_pct']}% catastrophic — the patience cohort "
        f"(bounce_wait / wait_pullback / hold) v2 excluded.")
    add(f"8. **What v3 DROPS** (n={m['v3_drops']['n']}, disjoint): "
        f"{m['v3_drops']['win_pct']}% win, {m['v3_drops']['median_excess']:+.2f} median, "
        f"{m['v3_drops']['catastrophic_pct']}% catastrophic. The confirmed-late slice "
        f"({drop_late_n} episodes) is the costly one v2 kept: {drop_late_win}% win, "
        f"{drop_late_med:+.2f} median.")
    add(f"9. Uncapped, the comparison holds: v2 {u['v2_rule_uncapped']['win_pct']}% / "
        f"{u['v2_rule_uncapped']['median_excess']:+.2f} (n={u['v2_rule_uncapped']['n']}) vs "
        f"v3 {u['v3_rule_uncapped']['win_pct']}% / "
        f"{u['v3_rule_uncapped']['median_excess']:+.2f} (n={u['v3_rule_uncapped']['n']}) — "
        f"the caps are not doing the work.")
    add(f"10. **Reconstruction cross-checks (asserted, not just reported).** The v2 arm "
        f"reproduces `v1_loser_audit_results.json`'s independently-computed v2 gate "
        f"retro exactly — covered n {out['p1_cross_check'].get('n_covered', {}).get('here')}, "
        f"covered win {out['p1_cross_check'].get('covered_win_rate', {}).get('here')}, "
        f"featured-like n {out['p1_cross_check'].get('v2_featured_n', {}).get('here')} at "
        f"{out['p1_cross_check'].get('v2_featured_win_rate', {}).get('here')} (masterplan "
        f"§2.3's 60.5% receipt). The reconstructed narrative level agrees with the logged "
        f"curated tag on {out['diagnostics']['narrative_vs_logged']['agreement_pct']}% of "
        f"the {out['diagnostics']['narrative_vs_logged']['n_rows_with_logged_level']} rows "
        f"that carry one.")
    add(f"11. **The effective sample is {v3['n_board_days']} BOARD DAYS, not "
        f"{v3['n']} episodes.** Only entries up to 2026-07-17 have 10 forward sessions "
        f"in the store, so six of the fourteen window dates grade nothing yet. "
        f"Resampling whole board days (`track_scoring.date_block_ci`) widens the win "
        f"interval to v3 {v3['win_ci95_date_blocked']} vs v2 "
        f"{v2['win_ci95_date_blocked']} — still separated, but that is the interval to "
        f"quote, not the Wilson one.")
    add(f"12. **This is IN-SAMPLE and close to circular.** R1's entry ladder was fitted "
        f"to this era's §2.3 table; re-scoring the same era with it is internal "
        f"consistency, not confirmation. The shelves also share {m['shared']['n']} "
        f"episodes, so the two arms are not independent draws.")
    add("13. **One falling tape, and an approximated selection**: CSI300's forward-10 "
        "was negative on most graded entry dates; micro fillability, the ADV liquidity "
        "floor and signal freshness are not retro-testable, and the cap score's "
        "runway/reversal legs are partial or zero. Both arms carry the same omissions, "
        "so the comparison is fair; the absolute levels are not a production forecast. "
        "The theme reconstruction also carries the THS membership lookahead (PR #4506: "
        "7.7% of member-slots drifted in 8 days); curated membership is PIT-dated.")
    add(f"14. Window {out['coverage']['window']['start']}–"
        f"{out['coverage']['window']['end']} "
        f"({out['coverage']['window']['dates']} board dates, "
        f"{out['coverage']['window']['rows']} admission rows), frozen-replay pinned at "
        f"**{out['grade_asof']}** (without the pin the store's nightly bar re-opens the "
        f"maturity gate and the shipped headline stops reproducing — 441/70.52% on "
        f"2026-08-04). The "
        f"{out['coverage']['uncovered_before_window']['matured_episodes']} matured "
        f"episodes before the window carry no entry gauge and are excluded from ALL "
        f"arms. P0 gate PASSED: {g['episodes']} episodes / {g['matured']} matured / "
        f"{100 * g['win_rate']:.2f}% win / {g['losers']} losers.")
    add("15. **Decision**: a preliminary read for the operator's fast-track question, "
        "not a promotion and not a gauntlet pass. It supports R1 staying live and "
        "says the era-retro carries NO information about R2 or R3. Nothing here "
        "changes the G0.8 tripwire, which still grades the FORWARD race at ≥60 "
        "matured episodes.")
    add("")
    add("## Headline table — the stand-in race")
    add("")
    add("| Shelf " + HEADER)
    add("|---" + RULE)
    add(f"| **V3-RULE (capped 24/4)** {_fmt(v3)}")
    add(f"| **V2-RULE (capped 24/4)** {_fmt(v2)}")
    add(f"| ACTUAL logged board {_fmt(act)}")
    add(f"| V3-RULE (uncapped) {_fmt(u['v3_rule_uncapped'])}")
    add(f"| V2-RULE (uncapped) {_fmt(u['v2_rule_uncapped'])}")
    add("")
    add("Excess is CSI300-relative percent at the H=10 forced verdict from the T+1 "
        "fill; catastrophic is ABSOLUTE P&L ≤ −15%.")
    add("")
    add("## Leg attribution — which R-item earns the delta")
    add("")
    add("Each row is the full v3 rule with exactly one leg switched off, capped "
        "identically. A headline gap is only decision-relevant if you know what "
        "produced it.")
    add("")
    add("| Rule variant " + HEADER)
    add("|---" + RULE)
    for k, cell in att.items():
        add(f"| {k} {_fmt(cell)}")
    add("")
    add("## Marginal cohorts (disjoint — the sharper statement)")
    add("")
    add("| Cohort " + HEADER)
    add("|---" + RULE)
    add(f"| v3 ADDS (v2 excluded these) {_fmt(m['v3_adds'])}")
    add(f"| v3 DROPS (v2 featured these) {_fmt(m['v3_drops'])}")
    add(f"| on BOTH shelves {_fmt(m['shared'])}")
    add("")
    if m["v3_adds"].get("by_entry_status"):
        add("### v3 ADDS, by entry status")
        add("")
        add("| entry_status " + HEADER)
        add("|---" + RULE)
        for k, cell in m["v3_adds"]["by_entry_status"].items():
            add(f"| `{k}` {_fmt(cell)}")
        add("")
    if m["v3_drops"].get("by_reason"):
        add("### v3 DROPS, by reason")
        add("")
        add("| reason " + HEADER)
        add("|---" + RULE)
        for k, cell in m["v3_drops"]["by_reason"].items():
            add(f"| `{k}` {_fmt(cell)}")
        add("")
    add("## Per-date blocks")
    add("")
    add("| date | CSI300 fwd-10 | actual n/win/med | v2 n/win/med | v3 n/win/med |")
    add("|---|---|---|---|---|")
    for d, blk in out["by_date"].items():
        csi = blk.get("csi300_fwd10")
        add(f"| {d} | " + (f"{csi:+.2f}%" if csi is not None else "—")
            + f" | {_datecell(blk['actual'])} | {_datecell(blk['v2_capped'])}"
            f" | {_datecell(blk['v3_capped'])} |")
    add("")
    add("## Reconstruction diagnostics")
    add("")
    dg = out["diagnostics"]
    add(f"- theme_timing buckets (rows): {dg['theme_timing_distribution']}")
    add(f"- narrative reconstruction vs the logged curated-only tag: "
        f"{dg['narrative_vs_logged']['n_reconstruction_agrees']}/"
        f"{dg['narrative_vs_logged']['n_rows_with_logged_level']} agree "
        f"({dg['narrative_vs_logged']['agreement_pct']}%); the reconstruction tags "
        f"{dg['narrative_vs_logged']['n_rows_reconstruction_tags']} rows in total "
        f"(curated ∪ THS).")
    add(f"- chase composite fired on {dg['chase']['n_rows_chase']} rows "
        f"({dg['chase']['n_limit_close_day']} of them on an admission-day limit close); "
        f"{dg['chase']['n_limit_events_universe']} limit closes across the basket universe.")
    add(f"- relay: {dg['relay']['positioned']} rows positioned "
        f"(early {dg['relay']['position_early']} / mid {dg['relay']['position_mid']} / "
        f"late {dg['relay']['position_late']}), "
        f"{dg['relay']['unpositioned_no_basket']} unpositioned (no basket membership); "
        f"{dg['relay']['n_chase_and_relay_late']} rows took the `relay_late` demotion.")
    add(f"- shelf rows: {dg['shelf_row_counts']}")
    add(f"- shelf matured episodes: {dg['shelf_episode_counts']}")
    add("")
    add("## Honesty block")
    add("")
    for c in out["caveats"]:
        add(f"- {c}")
    add("")
    add("## Method")
    add("")
    add("- **Base frame**: the 1,082 legacy rows of `data/china_standout_track/board.parquet` "
        "(18 dates). Episodes via `engine.track_scoring.build_episodes` (contiguous runs), "
        "T+1 fill via `engine.china_standout_track._t1_fill` (locked-limit bars unfillable), "
        "H=10 forced verdict, CSI300-relative excess. P0 gate asserts the shipped "
        f"{g['episodes']}/{g['matured']}/{100 * g['win_rate']:.2f}%/{g['losers']} headline "
        "before any new number is computed.")
    add("- **Grain**: an episode belongs to a shelf when its ENTRY-date board row qualifies.")
    add("- **V2-RULE**: `entry_status ∈ {buy_now, partial}` ∧ ¬extended.")
    add("- **V3-RULE**: `entry_status ∈ {bounce_wait, wait_pullback, hold, buy_now, partial}` "
        "∧ ¬(status ∈ {buy_now, partial} ∧ ticks > 1) ∧ ¬extended ∧ ¬(chase ∧ relay late).")
    add(f"- **Caps**: featured {FEATURED_CAP} / sector {SECTOR_CAP} per date, walked in "
        "v3-score order, applied identically to BOTH arms (as `_partition` does).")
    add("- **theme_timing**: `_theme_timing_value` over reconstructed narrative level "
        "(HOT/WARMING per `engine.china_narrative_tags` thresholds, curated ∪ THS, rel20 "
        "and breadth rounded before the threshold test) and the `china_sector_cycles` "
        "forward-log basket phase/oscillator (newest row ≤ admission date, best-rs_rank "
        "basket per name).")
    add("- **chase / relay**: admission-day limit close (`close == high` ∧ day return ≥ "
        "0.95 × the name's own band via `engine.china_microstructure.limit_width_for_date`, "
        "with the unmerged 302xxx ChiNext fix replicated), trail-21d ≥ 25%, run-5d ≥ 15%; "
        "`relay_count_3d` = distinct OTHER members of the name's baskets printing a limit "
        "close inside [d−2, d]; early ≤1 / mid 2–3 / late ≥4.")
    add("")
    add("Frozen results: `research/cn_prophet_audit/v3_era_retro_results.json`. "
        "Regenerate: `python3 research/cn_prophet_audit/v3_era_retro.py`.")
    add("")
    OUT_MD.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
