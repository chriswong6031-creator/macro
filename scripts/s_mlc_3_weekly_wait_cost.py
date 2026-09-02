#!/usr/bin/env python3
"""S-MLC-3 — Weekly-Wait Entry Cost on Leaders · phase-0 backtest harness.

PRE-REGISTRATION (LAW, frozen 2026-07-16, adjudicated):
    research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md

Question (verbatim, §0): for SPDR sector ETFs at RS rank #1-2 (of the
time-varying universe) AND within 2% of their 52-week high, what is the
average cost of a half-size-now / half-on-weekly-confirm entry construction
vs. full immediate entry, measured over the forward SPY-excess horizon?

This harness is display-tier phase-0 measurement ONLY (MLC-R2; house law
§Epistemics). NO engine wiring. NO promotion. The verdict decides which of
two pre-committed outcomes applies (§3 of the prereg):
    A — COST-IS-REAL:  leaders-exception pre-reg authorized (separate doc).
    B — NULL:           close the question, print the null honestly.
    C — negative cost:  weekly-wait is protective (no wiring action either way).

Every frozen constant below is named to match the prereg's own §-numbering
and frontmatter/freeze-record so a reviewer can diff constant-for-constant.
Do not edit a frozen constant without a dated APPEND to the prereg document.

Run:
    python3 scripts/s_mlc_3_weekly_wait_cost.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402

DATA_DIR = ROOT / "data" / "yahoo"
# OWNED FILES contract (ROUTE:build commission): prereg §7 names
# reports/s-mlc-3-weekly-wait-cost.md as the narrative deliverable; the
# commission's fallback path for a machine-readable "results artifact" is
# used verbatim since the prereg does not itself name a JSON path. Both are
# written — see DEVIATIONS in the worker's final report.
OUT_JSON = ROOT / "data" / "mlc" / "s_mlc_3_weekly_wait_cost_results.json"
OUT_REPORT = ROOT / "reports" / "s-mlc-3-weekly-wait-cost.md"
PREREG_PATH = "research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md"

# ============================================================================
# FROZEN PARAMETERS (research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md, frozen 2026-07-16)
# ============================================================================
CORE9 = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLU", "XLI", "XLB", "XLP"]  # 1998-12-22-> (§1.1)
XLRE_INCEPTION = pd.Timestamp("2015-10-08")   # Ruling 2 (§1.1, freeze record #2)
XLC_INCEPTION = pd.Timestamp("2018-06-19")    # Ruling 2 (§1.1, freeze record #2)
SECTOR_TICKERS = CORE9 + ["XLRE", "XLC"]
BENCHMARK = "SPY"

RS_WINDOW_PRIMARY = 60      # 60-session RS, Ruling 1 (§1.2, freeze record #1)
RS_WINDOW_SENSITIVITY = 20  # §5.1 sensitivity, NON-PROMOTABLE
HIGH_WINDOW = 252           # trading days (§1.3, freeze record: "trading days confirmed")
HIGH_THRESHOLD = -0.02      # within 2% of 52wk high, §1.3
MIN_SEPARATION = 21         # L3 event-recycling exclusion (trading days), §1.4

ENTRY_LAG = 1               # entry fill = t+1 close for BOTH legs, Ruling 5 (§1.5)
CONFIRM_ANCHOR_OFFSET = 5   # "first Friday >= day t+5" (t = event day), §1.5

DELTA_PRIMARY = 0.0         # Ruling 3: delta=0 PRIMARY, freeze record #3 (§1.5)
DELTA_SENSITIVITY = 0.01    # Ruling 3: NON-PROMOTABLE sensitivity only

HORIZONS = {"10d": 10, "21d": 21, "40d": 40, "63d": 63}  # §2.3 descriptive ladder
PRIMARY_HORIZON = "21d"     # horizon_role, §2.3 FROZEN

MAGNITUDE_FLOOR = 0.003     # 0.3% at 21d, §2.2 / freeze record #6
ERA_SPLIT_DATE = pd.Timestamp("2010-01-01")  # DT-R16 era-split law, §2.2
EFFECTIVE_N_FLOOR = 100     # §2.1

N_PERM = 10000              # §2.2 primary test draw count
PERM_SEED = 20260716        # reproducible; = prereg freeze date (YYYYMMDD)

HAC_T_GATE = 2.0            # §2.2
PERM_P_GATE = 0.05          # §2.2 (two-sided)
BH_ALPHA = 0.10             # §2.2

CYCLICALS = ["XLY", "XLF", "XLI", "XLK", "XLB"]  # §5.4, literal prereg grouping
DEFENSIVES = ["XLU", "XLV", "XLP", "XLE"]        # §5.4, literal prereg grouping (XLE as written)


# ============================================================================
# Pure functions — unit-tested in tests/test_s_mlc_3_weekly_wait_cost.py
# (no I/O, no network; safe to import and call in isolation)
# ============================================================================

def universe_for_date(date: pd.Timestamp) -> list[str]:
    """Time-varying SPDR universe per Ruling 2: 9->10->11 across XLRE/XLC inceptions.

    Absolute rank #1-2 among the SPDRs LISTED at each date — no fixed-panel
    exclusion (§1.1, Ruling 2)."""
    u = list(CORE9)
    if date >= XLRE_INCEPTION:
        u.append("XLRE")
    if date >= XLC_INCEPTION:
        u.append("XLC")
    return u


def next_friday_on_or_after(date: pd.Timestamp) -> pd.Timestamp:
    """First CALENDAR Friday >= `date` (§1.5: "the first Friday >= day t+5").

    Trading-day snapping (for a Friday that falls on a market holiday, e.g.
    Good Friday) is done by the caller against the real trading calendar —
    this function is pure calendar arithmetic only."""
    days_ahead = (4 - date.weekday()) % 7  # Monday=0 ... Friday=4
    return date + pd.Timedelta(days=days_ahead)


def confirm_fires(ref_close: float, entry_close: float, delta: float) -> bool:
    """Weekly-confirm rule (§1.5): Friday close >= entry close * (1 - delta).

    delta=0 PRIMARY is strict: the confirm Friday close must be AT OR ABOVE
    the reference close (Ruling 3)."""
    if ref_close is None or entry_close is None:
        return False
    if pd.isna(ref_close) or pd.isna(entry_close):
        return False
    return ref_close >= entry_close * (1.0 - delta)


def rank_descending(values: dict) -> dict:
    """Cross-sectional rank (1 = highest), min-tie method, over supplied
    values only (NaN/None entries are dropped, not ranked)."""
    clean = {k: v for k, v in values.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    if not clean:
        return {}
    s = pd.Series(clean)
    ranks = s.rank(method="min", ascending=False)
    return {k: int(v) for k, v in ranks.items()}


# ============================================================================
# Data loading
# ============================================================================

def load_prices() -> pd.DataFrame:
    """Wide dividend-adjusted close frame, union trading calendar, columns =
    sector tickers + SPY. Repo-relative path only (data/yahoo/*.parquet)."""
    cols = {}
    for t in SECTOR_TICKERS + [BENCHMARK]:
        df = pd.read_parquet(DATA_DIR / f"{t}.parquet")
        s = df["close"].sort_index()  # dividend-adjusted close (§0 "Data verified")
        s = s[~s.index.duplicated(keep="last")]
        cols[t] = s
    wide = pd.DataFrame(cols).sort_index()
    return wide


# ============================================================================
# RS-rank / 52wh-proximity / event extraction (§1.2-1.4)
# ============================================================================

def compute_rs_ratio(wide: pd.DataFrame, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """RS_window[s,t] = (close[t-1]/close[t-1-window] - 1) / SPY's same-window
    return (§1.2, literal ratio-of-returns formula)."""
    close_tm1 = wide.shift(1)
    close_tmw1 = wide.shift(window + 1)
    ret = close_tm1 / close_tmw1 - 1
    rs = ret.div(ret[BENCHMARK], axis=0)
    return rs, ret


def compute_near_high(wide: pd.DataFrame) -> pd.DataFrame:
    """near_high[s,t] = close[s,t-1] / rolling-252-trading-day-max[s,t-1] - 1 (§1.3)."""
    rolling_max = wide.rolling(HIGH_WINDOW, min_periods=HIGH_WINDOW).max()
    raw = wide / rolling_max - 1
    return raw.shift(1)


def compute_universe_mask(wide: pd.DataFrame) -> pd.DataFrame:
    idx = wide.index
    mask = pd.DataFrame(False, index=idx, columns=SECTOR_TICKERS)
    for t in CORE9:
        mask[t] = wide[t].notna()
    mask["XLRE"] = (idx >= XLRE_INCEPTION) & wide["XLRE"].notna()
    mask["XLC"] = (idx >= XLC_INCEPTION) & wide["XLC"].notna()
    return mask


def compute_candidates(wide: pd.DataFrame, rs_window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """L1 (RS top-2) & L2 (within 2% of 52wh) candidate mask, per ticker per date.

    Ranking universe on a given date = tickers in the frozen inception schedule
    AND with a computable RS_window (i.e. >= window+1 trading days of own
    history) — a newly-inducted ETF is not "available" to be ranked until it
    has enough history to produce an RS number, matching §1.1's "the universe
    that was actually available to the operator on each date"."""
    rs, ret = compute_rs_ratio(wide, rs_window)
    near_high = compute_near_high(wide)
    universe_mask = compute_universe_mask(wide)
    eligible = universe_mask & ret[SECTOR_TICKERS].notna()
    rs_masked = rs[SECTOR_TICKERS].where(eligible)
    ranks = rs_masked.rank(axis=1, method="min", ascending=False)
    l1 = ranks <= 2
    l2 = near_high[SECTOR_TICKERS] >= HIGH_THRESHOLD
    candidate = l1.fillna(False) & l2.fillna(False)
    return candidate, ranks


def extract_events(candidate: pd.DataFrame, min_sep: int = MIN_SEPARATION) -> list[tuple[str, int]]:
    """L3: minimum `min_sep` trading-day gap between fires for the SAME ticker
    (event-recycling exclusion, §1.4). Greedy, chronological."""
    events: list[tuple[str, int]] = []
    cols = candidate.columns.tolist()
    last_fired = {t: -(10 ** 9) for t in cols}
    values = candidate.values
    n = len(candidate.index)
    for i in range(n):
        row = values[i]
        for j, t in enumerate(cols):
            if row[j] and (i - last_fired[t] >= min_sep):
                events.append((t, i))
                last_fired[t] = i
    return events


# ============================================================================
# Entry construction (§1.5) — event record + per-horizon/delta cost (§1.6)
# ============================================================================

def build_event_records(wide: pd.DataFrame, events: list[tuple[str, int]]) -> list[dict]:
    idx = wide.index
    n = len(idx)
    records = []
    for ticker, i in events:
        entry_i = i + ENTRY_LAG
        if entry_i >= n:
            continue  # right-censored: no entry-day data
        entry_close = wide[ticker].iloc[entry_i]
        entry_spy = wide[BENCHMARK].iloc[entry_i]
        if pd.isna(entry_close) or pd.isna(entry_spy):
            continue
        event_close = wide[ticker].iloc[i]  # close[s,t] — see CONFIRM_REFERENCE note below
        anchor_i = i + CONFIRM_ANCHOR_OFFSET
        friday_i = None
        if anchor_i < n:
            anchor_date = idx[anchor_i]
            friday_target = next_friday_on_or_after(anchor_date)
            pos = idx.searchsorted(friday_target, side="right") - 1
            if 0 <= pos < n:
                friday_i = int(pos)
        friday_close = wide[ticker].iloc[friday_i] if friday_i is not None else np.nan
        records.append({
            "ticker": ticker,
            "event_i": i,
            "event_date": idx[i],
            "entry_i": entry_i,
            "entry_date": idx[entry_i],
            "entry_close": float(entry_close),
            "entry_spy": float(entry_spy),
            "event_close": float(event_close) if not pd.isna(event_close) else None,
            "friday_i": friday_i,
            "friday_date": idx[friday_i] if friday_i is not None else None,
            "friday_close": (float(friday_close) if not pd.isna(friday_close) else None),
        })
    return records


def compute_costs(wide: pd.DataFrame, records: list[dict], nonconfirm_mode: str = "spy",
                   confirm_reference: str = "entry_close") -> pd.DataFrame:
    """Per (event, horizon, delta) cost row (§1.6):
        cost = r_full_immediate_excess - r_half_weekly_wait_excess

    nonconfirm_mode="spy" (PRIMARY, Ruling 4): non-confirmed half parks in SPY,
    excess contribution = 0 by construction.
    nonconfirm_mode="cash" (§5.5 sensitivity, diagnostic only): non-confirmed
    half earns 0% (idle cash) instead.

    confirm_reference — GENUINE PREREG AMBIGUITY (see DEVIATIONS in the worker
    report for scripts/s_mlc_3_weekly_wait_cost.py): §1.5's raw formula
    compares the Friday close to `close[s,t]` (the EVENT day, t) — "close[s]
    on the next Friday ... is >= close[s,t] x (1-delta)". But the freeze
    record (Ruling 3 gloss) and the machine-checkable YAML frontmatter BOTH
    independently say "strict weekly close >= entry close", and Ruling 5
    anchors "entry" unambiguously at t+1. These two statements of the SAME
    frozen rule disagree by one trading day. confirm_reference="entry_close"
    (t+1, PRIMARY per this harness — chosen because the frontmatter is
    labeled "machine-checkable" and the entry-close language appears twice)
    vs "event_close" (t, literal §1.5 formula) are BOTH computed and reported
    — this is not merely a robustness nicety: it moves the pooled 21d mean
    cost across the 0.3% magnitude floor (0.309% vs 0.296%), which flips
    whether the primary cell clears Outcome A's magnitude gate. See the
    `confirm_reference_ambiguity` block in the results JSON.
    """
    idx = wide.index
    n = len(idx)
    rows = []
    for rec in records:
        ticker = rec["ticker"]
        entry_i = rec["entry_i"]
        entry_close = rec["entry_close"]
        entry_spy = rec["entry_spy"]
        friday_i = rec["friday_i"]
        friday_close = rec["friday_close"]
        ref_close = entry_close if confirm_reference == "entry_close" else rec["event_close"]
        for hname, h in HORIZONS.items():
            end_i = entry_i + h
            if end_i >= n:
                continue  # right-censored at this horizon
            end_close = wide[ticker].iloc[end_i]
            end_spy = wide[BENCHMARK].iloc[end_i]
            if pd.isna(end_close) or pd.isna(end_spy):
                continue
            r_full = end_close / entry_close - 1
            spy_full = end_spy / entry_spy - 1
            excess_full = (1 + r_full) / (1 + spy_full) - 1
            confirm_available = (
                friday_i is not None and friday_i <= end_i and friday_close is not None
                and ref_close is not None
            )
            if not confirm_available:
                continue  # cannot resolve the confirm decision — drop, don't guess
            for delta_name, delta in (("primary", DELTA_PRIMARY), ("sensitivity", DELTA_SENSITIVITY)):
                fires = confirm_fires(friday_close, ref_close, delta)
                if fires:
                    r_leg2 = end_close / friday_close - 1  # r_from_friday
                elif nonconfirm_mode == "spy":
                    r_leg2 = spy_full  # Ruling 4: r_SPY_from_t+1
                else:
                    r_leg2 = 0.0  # §5.5 cash sensitivity
                blended_raw = 0.5 * r_full + 0.5 * r_leg2
                excess_half = (1 + blended_raw) / (1 + spy_full) - 1
                cost = excess_full - excess_half
                rows.append({
                    "ticker": ticker,
                    "event_date": rec["event_date"],
                    "horizon": hname,
                    "delta": delta_name,
                    "confirm_fires": fires,
                    "excess_full": excess_full,
                    "excess_half": excess_half,
                    "cost": cost,
                })
    return pd.DataFrame(rows)


# ============================================================================
# Statistics (§2.2)
# ============================================================================

def month_block_permutation_test(cost: np.ndarray, dates, n_perm: int = N_PERM,
                                  seed: int = PERM_SEED) -> dict:
    """PRIMARY test (§2.2, DT-R14 within-month event-label permutation).

    Interpretation note (see DEVIATIONS): this is a single-arm cost measure
    (one number per event, not a treatment/control label pair), so "permuting
    the event labels" is operationalized as a month-block SIGN-FLIP test —
    the null hypothesis is that cost is symmetric around zero (no systematic
    wait cost), and the resampling UNIT is the calendar month (not the
    individual event, and not merely the date): every event sharing a
    calendar month receives the SAME random +1/-1 draw per permutation, which
    also preserves the finer date-level clustering §2.2 requires (same-date
    events are always same-month events). 10,000 draws, two-sided p-value.
    """
    dates = pd.DatetimeIndex(dates)
    months = dates.to_period("M").astype(str).values
    codes, uniq = pd.factorize(months)
    m = len(uniq)
    observed_mean = float(np.mean(cost))
    rng = np.random.default_rng(seed)
    null_means = np.empty(n_perm)
    for k in range(n_perm):
        month_signs = rng.choice(np.array([-1.0, 1.0]), size=m)
        signs = month_signs[codes]
        null_means[k] = float(np.mean(cost * signs))
    p = float(np.mean(np.abs(null_means) >= abs(observed_mean)))
    return {
        "observed_mean": observed_mean,
        "p_value": p,
        "n_perm": n_perm,
        "n_months": int(m),
        "n_events": int(len(cost)),
    }


def summarize_cell(cost_array: np.ndarray) -> dict:
    """Mean + HAC (Newey-West) t-stat, lags = floor(n^(1/3)) per §2.2 gate table.

    This is also the "standard Hodrick/Newey-West overlap correction" §2.2
    calls for at the 40d/63d horizons — one HAC formula, scaled by sample
    size, applied uniformly across all horizons (see DEVIATIONS)."""
    n = len(cost_array)
    if n == 0:
        return {"n": 0, "mean": None, "hac": None, "lags": None}
    lags = int(math.floor(n ** (1.0 / 3.0)))
    hac = newey_west_tstat(cost_array, lags=lags)
    return {"n": n, "mean": float(np.mean(cost_array)), "hac": hac, "lags": lags}


def era_of(date: pd.Timestamp) -> str:
    return "pre2010" if date < ERA_SPLIT_DATE else "post2010"


# ============================================================================
# Verdict (§3, pre-committed)
# ============================================================================

def determine_verdict(gates: dict) -> dict:
    """Apply the pre-committed §3 outcome mapping. Returns {"outcome": "A"|"B"|"C", ...}."""
    pooled_mean = gates["pooled"]["mean"]
    pooled_hac_t = gates["pooled"]["hac"]["t"]
    perm_p = gates["permutation"]["p_value"]
    era_signs_agree = gates["era_signs_agree"]
    split_half_agree = gates["split_half_agree"]
    episode_block_agrees = gates["episode_block_agrees"]
    bh_reject_primary = gates["bh_reject_primary"]
    magnitude_ok = pooled_mean is not None and pooled_mean >= MAGNITUDE_FLOOR

    if pooled_mean is None or pooled_hac_t is None:
        return {"outcome": "B", "reason": "insufficient data to compute the primary cell"}

    cost_is_real = (
        pooled_mean > 0
        and perm_p < PERM_P_GATE
        and abs(pooled_hac_t) >= HAC_T_GATE
        and era_signs_agree
        and episode_block_agrees
        and bh_reject_primary
        and split_half_agree
        and magnitude_ok
    )
    if cost_is_real:
        return {"outcome": "A", "label": "COST-IS-REAL"}

    is_protective = (
        pooled_mean < 0
        and abs(pooled_hac_t) >= HAC_T_GATE
        and era_signs_agree
        and split_half_agree
    )
    if is_protective:
        return {"outcome": "C", "label": "weekly-wait is protective (negative, significant cost)"}

    reasons = []
    if pooled_mean is None or abs(pooled_hac_t) < HAC_T_GATE:
        reasons.append(f"|HAC t|={pooled_hac_t} < {HAC_T_GATE}")
    if perm_p >= PERM_P_GATE:
        reasons.append(f"permutation p={perm_p} >= {PERM_P_GATE}")
    if not bh_reject_primary:
        reasons.append("primary cell fails BH-FDR")
    if not era_signs_agree:
        reasons.append("era signs disagree")
    if not split_half_agree:
        reasons.append("split-half signs disagree")
    if not episode_block_agrees:
        reasons.append("episode-block sign disagrees with pooled")
    if not magnitude_ok:
        reasons.append(f"mean cost {pooled_mean} below magnitude floor {MAGNITUDE_FLOOR}")
    return {"outcome": "B", "label": "NULL", "reasons": reasons}


# ============================================================================
# Orchestration
# ============================================================================

def _json_default(obj):
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    raise TypeError(f"not JSON serializable: {type(obj)}")


def run() -> dict:
    wide = load_prices()

    # --- primary population: 60d RS, time-varying universe ---
    candidate60, ranks60 = compute_candidates(wide, RS_WINDOW_PRIMARY)
    events60 = extract_events(candidate60)
    records60 = build_event_records(wide, events60)
    costs = compute_costs(wide, records60, nonconfirm_mode="spy", confirm_reference="entry_close")
    costs["era"] = costs["event_date"].map(era_of)

    # Confirm-reference ambiguity check (see compute_costs docstring): the raw
    # §1.5 formula and the freeze-record/frontmatter gloss disagree by one
    # trading day on the confirm reference price. Compute the literal-§1.5
    # alternate (event-day close, t) at the primary cell ONLY, to report how
    # much the verdict-relevant number moves.
    costs_event_ref = compute_costs(wide, records60, nonconfirm_mode="spy", confirm_reference="event_close")
    alt_primary_cell = costs_event_ref[
        (costs_event_ref["horizon"] == PRIMARY_HORIZON) & (costs_event_ref["delta"] == "primary")
    ]
    alt_pooled = summarize_cell(alt_primary_cell["cost"].values)
    confirm_reference_ambiguity = {
        "note": (
            "Prereg SS1.5's raw formula compares the Friday close to close[s,t] "
            "(event day); the freeze record (Ruling 3) and the machine-checkable "
            "frontmatter both instead say 'weekly close >= entry close' (t+1). "
            "This harness uses entry_close (t+1) as PRIMARY; event_close (t) is "
            "reported here for transparency because it moves the pooled 21d mean "
            "cost across the 0.3% magnitude floor."
        ),
        "primary_reference": "entry_close (t+1)",
        "primary_reference_mean_cost_21d": None,  # filled below once `pooled` exists
        "alternate_reference": "event_close (t), literal SS1.5 formula",
        "alternate_reference_mean_cost_21d": alt_pooled["mean"],
        "alternate_reference_hac": alt_pooled["hac"],
        "alternate_clears_magnitude_floor": (
            alt_pooled["mean"] is not None and alt_pooled["mean"] >= MAGNITUDE_FLOOR
        ),
    }

    n_raw_events = len(records60)

    primary = costs[(costs["horizon"] == PRIMARY_HORIZON) & (costs["delta"] == "primary")].copy()
    pooled = summarize_cell(primary["cost"].values)
    perm = month_block_permutation_test(primary["cost"].values, primary["event_date"].values)
    confirm_reference_ambiguity["primary_reference_mean_cost_21d"] = pooled["mean"]
    confirm_reference_ambiguity["verdict_sensitive_to_choice"] = (
        pooled["mean"] is not None and alt_pooled["mean"] is not None
        and (pooled["mean"] >= MAGNITUDE_FLOOR) != (alt_pooled["mean"] >= MAGNITUDE_FLOOR)
    )

    era_cells = {}
    for era in ("pre2010", "post2010"):
        sub = primary[primary["era"] == era]
        era_cells[era] = summarize_cell(sub["cost"].values)
    era_signs_agree = (
        era_cells["pre2010"]["mean"] is not None
        and era_cells["post2010"]["mean"] is not None
        and (era_cells["pre2010"]["mean"] > 0) == (era_cells["post2010"]["mean"] > 0)
    )

    # split-half by calendar median date
    sorted_dates = primary["event_date"].sort_values()
    median_date = sorted_dates.median() if len(sorted_dates) else None
    if median_date is not None:
        half1 = primary[primary["event_date"] <= median_date]
        half2 = primary[primary["event_date"] > median_date]
        half1_mean = float(half1["cost"].mean()) if len(half1) else None
        half2_mean = float(half2["cost"].mean()) if len(half2) else None
        split_half_agree = (
            half1_mean is not None and half2_mean is not None
            and (half1_mean > 0) == (half2_mean > 0)
        )
    else:
        half1_mean = half2_mean = None
        split_half_agree = False

    # episode-first-month blocking
    primary["month"] = primary["event_date"].dt.to_period("M").astype(str)
    monthly_means = primary.groupby("month")["cost"].mean()
    episode_block_mean = float(monthly_means.mean()) if len(monthly_means) else None
    episode_block_agrees = (
        episode_block_mean is not None and pooled["mean"] is not None
        and (episode_block_mean > 0) == (pooled["mean"] > 0)
    )

    # confirm-miss rate (primary delta, 21d cell — decision is horizon-independent
    # per event but computed once per event so we read it off this cell)
    confirm_miss_rate = float((~primary["confirm_fires"]).mean()) if len(primary) else None

    # BH-FDR matrix: 4 horizons x 3 cells (pooled/pre2010/post2010), delta=primary
    pvals = {}
    matrix_cells = {}
    for hname in HORIZONS:
        cell_h = costs[(costs["horizon"] == hname) & (costs["delta"] == "primary")]
        for era_name, sub in (
            ("pooled", cell_h),
            ("pre2010", cell_h[cell_h["era"] == "pre2010"]),
            ("post2010", cell_h[cell_h["era"] == "post2010"]),
        ):
            key = f"{hname}_{era_name}"
            summ = summarize_cell(sub["cost"].values)
            matrix_cells[key] = summ
            p = summ["hac"]["p"] if summ["hac"] else None
            if p is not None:
                pvals[key] = p
    bh = benjamini_hochberg(pvals, alpha=BH_ALPHA)
    primary_key = f"{PRIMARY_HORIZON}_pooled"
    bh_reject_primary = bool(bh.get(primary_key, {}).get("reject", False))

    gates = {
        "pooled": pooled,
        "permutation": perm,
        "era_cells": era_cells,
        "era_signs_agree": era_signs_agree,
        "split_half": {"half1_mean": half1_mean, "half2_mean": half2_mean, "median_date": median_date},
        "split_half_agree": split_half_agree,
        "episode_block_mean": episode_block_mean,
        "episode_block_agrees": episode_block_agrees,
        "bh_matrix": bh,
        "bh_reject_primary": bh_reject_primary,
        "confirm_miss_rate": confirm_miss_rate,
    }
    verdict = determine_verdict(gates)

    # descriptive ladder — all horizons, pooled, primary delta
    ladder = {}
    for hname in HORIZONS:
        sub = costs[(costs["horizon"] == hname) & (costs["delta"] == "primary")]
        ladder[hname] = summarize_cell(sub["cost"].values)

    # ---- §5 robustness / sensitivities (diagnostic, NON-PROMOTABLE) ----
    # 5.1: 20d RS rank sensitivity
    candidate20, _ = compute_candidates(wide, RS_WINDOW_SENSITIVITY)
    events20 = extract_events(candidate20)
    records20 = build_event_records(wide, events20)
    costs20 = compute_costs(wide, records20, nonconfirm_mode="spy")
    sens_20d_rs = summarize_cell(
        costs20[(costs20["horizon"] == PRIMARY_HORIZON) & (costs20["delta"] == "primary")]["cost"].values
    )

    # 5.2: delta=0.01 sensitivity (same event population, alternate confirm rule)
    sens_delta = summarize_cell(
        costs[(costs["horizon"] == PRIMARY_HORIZON) & (costs["delta"] == "sensitivity")]["cost"].values
    )

    # 5.3: XLRE/XLC post-inception diagnostic
    sens_xlre_xlc = summarize_cell(
        primary[primary["ticker"].isin(["XLRE", "XLC"])]["cost"].values
    )

    # 5.4: sector subgroup (cyclicals vs defensives), primary population
    sens_cyclicals = summarize_cell(primary[primary["ticker"].isin(CYCLICALS)]["cost"].values)
    sens_defensives = summarize_cell(primary[primary["ticker"].isin(DEFENSIVES)]["cost"].values)

    # 5.5: non-confirm parks in cash instead of SPY
    costs_cash = compute_costs(wide, records60, nonconfirm_mode="cash")
    sens_cash = summarize_cell(
        costs_cash[(costs_cash["horizon"] == PRIMARY_HORIZON) & (costs_cash["delta"] == "primary")]["cost"].values
    )

    result = {
        "study_id": "s-mlc-3-weekly-wait-cost",
        "prereg": PREREG_PATH,
        "generated_by": "scripts/s_mlc_3_weekly_wait_cost.py",
        "frozen_params": {
            "rs_window_primary": RS_WINDOW_PRIMARY,
            "high_window": HIGH_WINDOW,
            "high_threshold": HIGH_THRESHOLD,
            "min_separation": MIN_SEPARATION,
            "entry_lag": ENTRY_LAG,
            "confirm_anchor_offset": CONFIRM_ANCHOR_OFFSET,
            "delta_primary": DELTA_PRIMARY,
            "delta_sensitivity": DELTA_SENSITIVITY,
            "primary_horizon": PRIMARY_HORIZON,
            "magnitude_floor": MAGNITUDE_FLOOR,
            "era_split_date": ERA_SPLIT_DATE,
            "effective_n_floor": EFFECTIVE_N_FLOOR,
            "n_perm": N_PERM,
            "hac_t_gate": HAC_T_GATE,
            "perm_p_gate": PERM_P_GATE,
            "bh_alpha": BH_ALPHA,
        },
        "sample": {
            "n_raw_events": n_raw_events,
            "n_primary_cell": pooled["n"],
            "effective_n_floor_met": n_raw_events >= EFFECTIVE_N_FLOOR,
        },
        "primary_cell_21d_delta0": {
            "mean_cost": pooled["mean"],
            "hac": pooled["hac"],
            "permutation": perm,
        },
        "era_split": era_cells,
        "era_signs_agree": era_signs_agree,
        "split_half": {"half1_mean": half1_mean, "half2_mean": half2_mean, "median_date": median_date},
        "split_half_agree": split_half_agree,
        "episode_first_month_block": {
            "block_mean_of_monthly_means": episode_block_mean,
            "n_months": int(len(monthly_means)),
            "agrees_with_pooled": episode_block_agrees,
        },
        "bh_fdr_matrix": bh,
        "bh_reject_primary": bh_reject_primary,
        "confirm_miss_rate": confirm_miss_rate,
        "magnitude_floor_met": (pooled["mean"] is not None and pooled["mean"] >= MAGNITUDE_FLOOR),
        "descriptive_horizon_ladder": ladder,
        "verdict": verdict,
        "confirm_reference_ambiguity": confirm_reference_ambiguity,
        "robustness_non_promotable": {
            "rs_window_20d_sensitivity_21d_delta0": sens_20d_rs,
            "delta_0_01_sensitivity_21d": sens_delta,
            "xlre_xlc_only_21d_delta0": sens_xlre_xlc,
            "cyclicals_21d_delta0": sens_cyclicals,
            "defensives_21d_delta0": sens_defensives,
            "nonconfirm_cash_instead_of_spy_21d_delta0": sens_cash,
        },
    }
    return result


def write_report(result: dict) -> None:
    v = result["verdict"]
    outcome = v.get("outcome")
    label = v.get("label", "")
    pooled = result["primary_cell_21d_delta0"]
    lines = []
    lines.append("# S-MLC-3 — Weekly-Wait Entry Cost on Leaders · Phase-0 Results")
    lines.append("")
    lines.append(f"**Pre-registration:** `{PREREG_PATH}` (frozen 2026-07-16)")
    lines.append(f"**Harness:** `scripts/s_mlc_3_weekly_wait_cost.py`")
    lines.append("")
    lines.append(f"## VERDICT: Outcome {outcome} — {label}")
    lines.append("")
    mean_pct = pooled["mean_cost"] * 100 if pooled["mean_cost"] is not None else None
    t = pooled["hac"]["t"] if pooled["hac"] else None
    p_perm = pooled["permutation"]["p_value"]
    lines.append(
        f"Mean 21d SPY-excess cost of the wait construction vs. immediate entry "
        f"(pooled, δ=0 primary): **{mean_pct:.3f}%** "
        f"(HAC t={t}, month-block permutation p={p_perm:.4f}, "
        f"n={result['sample']['n_primary_cell']})."
    )
    if v.get("reasons"):
        lines.append("")
        lines.append("Gates not cleared: " + "; ".join(v["reasons"]))
    lines.append("")
    amb = result["confirm_reference_ambiguity"]
    if amb.get("verdict_sensitive_to_choice"):
        lines.append(
            "> **CAUTION — verdict is NOT robust to a genuine pre-reg ambiguity.** "
            f"{amb['note']} Primary (entry_close, t+1) mean = "
            f"{amb['primary_reference_mean_cost_21d']*100:.3f}%; alternate (event_close, t, "
            f"literal SS1.5 formula) mean = {amb['alternate_reference_mean_cost_21d']*100:.3f}%. "
            f"The alternate reading {'DOES' if amb['alternate_clears_magnitude_floor'] else 'does NOT'} "
            "clear the 0.3% magnitude floor. This fork should be adjudicated before any Outcome-A "
            "leaders-exception pre-reg is authored on this result."
        )
        lines.append("")
    lines.append("## Sample")
    lines.append("")
    lines.append(f"- Raw non-overlapping leader-at-high events (all horizons/deltas): {result['sample']['n_raw_events']}")
    lines.append(f"- Effective-N floor (>=100): {'MET' if result['sample']['effective_n_floor_met'] else 'NOT MET'}")
    lines.append(f"- Primary cell (21d, δ=0) usable N after right-censoring: {result['sample']['n_primary_cell']}")
    lines.append("")
    lines.append("## Gates table (§2.2)")
    lines.append("")
    lines.append("| Gate | Result | Pass? |")
    lines.append("|---|---|---|")
    lines.append(f"| Permutation p (within-month, two-sided) | {p_perm:.4f} | {'YES' if p_perm < PERM_P_GATE else 'no'} |")
    lines.append(f"| HAC \\|t\\| >= 2.0 | {abs(t) if t is not None else None} | {'YES' if (t is not None and abs(t) >= HAC_T_GATE) else 'no'} |")
    lines.append(f"| Era-split same sign | pre2010={result['era_split']['pre2010']['mean']}, post2010={result['era_split']['post2010']['mean']} | {'YES' if result['era_signs_agree'] else 'no'} |")
    lines.append(f"| Episode-first-month blocking, same sign as pooled | block={result['episode_first_month_block']['block_mean_of_monthly_means']} | {'YES' if result['episode_first_month_block']['agrees_with_pooled'] else 'no'} |")
    lines.append(f"| BH-FDR (12-cell matrix, alpha=0.10), primary cell survives | q={result['bh_fdr_matrix'].get(PRIMARY_HORIZON+'_pooled', {}).get('q')} | {'YES' if result['bh_reject_primary'] else 'no'} |")
    lines.append(f"| Split-half sign-stability | half1={result['split_half']['half1_mean']}, half2={result['split_half']['half2_mean']} | {'YES' if result['split_half_agree'] else 'no'} |")
    lines.append(f"| Magnitude floor (>= 0.3% at 21d) | {mean_pct:.3f}% | {'YES' if result['magnitude_floor_met'] else 'no'} |")
    lines.append(f"| Confirm-miss rate (context, not a gate) | {result['confirm_miss_rate']:.3f} | n/a |")
    lines.append("")
    lines.append("## Era split (§2.2 DT-R16 mandatory)")
    lines.append("")
    lines.append("| Era | n | mean cost | HAC t |")
    lines.append("|---|---|---|---|")
    for era in ("pre2010", "post2010"):
        c = result["era_split"][era]
        lines.append(f"| {era} | {c['n']} | {c['mean']} | {c['hac']['t'] if c['hac'] else None} |")
    lines.append("")
    lines.append("## Descriptive horizon ladder (10d/21d/40d/63d, pooled, δ=0)")
    lines.append("")
    lines.append("**Verdicts at non-declared horizons are forbidden (§2.3, DO_NOT_REBUILD.md §3) — descriptive only.**")
    lines.append("")
    lines.append("| Horizon | n | mean cost | HAC t |")
    lines.append("|---|---|---|---|")
    for hname, c in result["descriptive_horizon_ladder"].items():
        lines.append(f"| {hname} | {c['n']} | {c['mean']} | {c['hac']['t'] if c['hac'] else None} |")
    lines.append("")
    lines.append("## Robustness / sensitivities (§5 — NON-PROMOTABLE, cannot override the primary verdict)")
    lines.append("")
    for name, c in result["robustness_non_promotable"].items():
        lines.append(f"- **{name}**: n={c['n']}, mean={c['mean']}, HAC t={c['hac']['t'] if c['hac'] else None}")
    lines.append("")
    lines.append("## What this does NOT show (§6)")
    lines.append("")
    lines.append("- Does not claim the leader-at-high filter itself generates alpha.")
    lines.append("- Does not test RS-leadership continuation (S-MLC-1) or suction conditionality (S-MLC-2).")
    lines.append("- A null does not validate the half-size/weekly-wait construct as optimal on other grounds (risk, psychology, drawdown-minimization).")
    lines.append("- Uses no LLM-originated signals or verdicts at any step.")
    lines.append("- Closes only the specific half-size/weekly-wait construction at the RS #1-2 + 52wh filter on SPDR sector ETFs — no broader entry-timing family.")
    lines.append("")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=_json_default)
    write_report(result)

    v = result["verdict"]
    print(json.dumps({
        "study_id": result["study_id"],
        "verdict": v,
        "n_raw_events": result["sample"]["n_raw_events"],
        "n_primary_cell": result["sample"]["n_primary_cell"],
        "mean_cost_21d_pooled": result["primary_cell_21d_delta0"]["mean_cost"],
        "hac_t": result["primary_cell_21d_delta0"]["hac"]["t"] if result["primary_cell_21d_delta0"]["hac"] else None,
        "permutation_p": result["primary_cell_21d_delta0"]["permutation"]["p_value"],
        "era_signs_agree": result["era_signs_agree"],
        "split_half_agree": result["split_half_agree"],
        "bh_reject_primary": result["bh_reject_primary"],
        "confirm_miss_rate": result["confirm_miss_rate"],
        "out_json": str(OUT_JSON.relative_to(ROOT)),
        "out_report": str(OUT_REPORT.relative_to(ROOT)),
    }, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
