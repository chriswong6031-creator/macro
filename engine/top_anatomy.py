"""TOP ANATOMY — extended-move maturation truth engine (RESEARCH / DISPLAY TIER).

WHAT THIS IS. The pure computational core of the TOP ANATOMY program
(`research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md`), implementing the frozen Phase-0
construction in `research/top_anatomy/TOPA_PHASE0_PREREG.md` §4. It answers one
question about an already-extended winner: *has this move changed character?* —
by contrasting extended days that went on to top against extended days that kept
going. Never "collapsed names vs average names".

TIER AND AUTHORITY. Everything here is **research / display tier with ZERO scored
authority**. Nothing in this module ranks, gates, sizes, or escalates anything;
no output is a probability, a score, or a call. This is the **AVOID-not-SHORT**
lobe: its product is entry-side avoidance and trim-conviction *context* for a
position already owned. There are no directional bear positions and no exit rules
anywhere in this program (`DNR:KILL-DIRECTIONAL-SHORTING`; short-side L1 §7
graveyard: "drawdown control is an ENTRY problem"). Promotion of anything here to
authority requires its own gauntlet prereg.

LABELS ARE HINDSIGHT-LEGAL; FEATURES ARE POINT-IN-TIME. Episode discovery, peaks,
race labels and outcomes deliberately use the full forward record — that is what
makes them ground truth. Every FEATURE value at day d uses only bars at or before
d inside d's identity segment. The separation is enforced by
`tests/test_top_anatomy.py::test_features_are_point_in_time` (mutate every bar
after d, recompute, demand bit-identical values).

INSTRUMENT VERDICTS ARE NOT MARKET VERDICTS. A `TOPPED` race label states that a
specific declared race (−20% from the post-entry running peak before +15% from
the entry close, inside 250 sessions) resolved one way. It is not a claim that a
move "is over", and no copy derived from it may say so.

Purity: pandas/numpy only. No repo config, no `lib.config`, no `engine.run`, no
I/O — every entry point takes explicit frames, paths, and parameters, so the
module imports and runs against synthetic bars with no data store present.

--------------------------------------------------------------------------------
IDENTITY SEGMENTS (data-defect rule, recorded in the prereg ratification log
2026-08-10, before outcomes were read)
--------------------------------------------------------------------------------
`data/massive_stock_day` keys by TICKER, and tickers get REUSED. Verified live:
`BBBY.parquet` carries old Bed Bath & Beyond through ~2023, then an ~850-session
hole, then a DIFFERENT company's bars from 2025-08-29. Unhandled, a forward race
walk stitches two companies into one path and fabricates events. So before any
computation every ticker's bar series is split at interior gaps of more than
`IDENTITY_GAP_MAX_SESSIONS` (60) sessions into independent identity segments
named `TICK#0`, `TICK#1`, … (a ticker with a single segment keeps its bare name).
A segment is a **name** for every purpose here: its own history requirement, its
own episodes, labels and features; no window, lag, or forward walk ever crosses a
segment boundary.

--------------------------------------------------------------------------------
INTERPRETATIONS (judgment calls made against the frozen prereg text; every one is
conservative, documented here, and reported upward rather than re-pinned)
--------------------------------------------------------------------------------
1.  "Session" means **the name's own trading bar inside its identity segment**
    everywhere: history requirements, rolling windows, episode gap merges, the
    race horizon, `days_to_peak`, and every lag. The single exception is
    identity-gap detection itself, which is measured on the shared market
    calendar because its job is to see a stretch MISSING from the tape.
2.  Trailing windows are **inclusive of d** (`max(close over trailing 252
    sessions)` is over the 252 bars ending at d, so it is always ≥ close_d).
3.  "≥ 260 prior sessions" is implemented as bar position ≥ 260 inside the
    segment, i.e. 260 bars strictly before d.
4.  Episode gap merge: the merged quantity is the count of NON-EXT sessions
    between two EXT days (`pos_next − pos_prev − 1`). 21 merges, 22 splits.
5.  Race horizon: the forward walk covers offsets 1..250 from d. Offset 0 can
    never fire either barrier by construction.
6.  Race censoring distinguishes `horizon` (250 sessions elapsed, no barrier)
    from `data_end` (segment ran out first, incl. delisting) — both are CENSORED
    per §4.3; the reason is carried so delisting can be audited separately.
7.  Episode peak ties (equal closes) resolve to the **earliest** occurrence.
    "Sessions since a rolling max" ties resolve to the **most recent** occurrence
    (a lag of 0 when today equals the max).
8.  Episode outcome at the data edge: §4.4's "else SURVIVED" is implemented
    literally, with a `peak_window_censored` flag set when [peak, peak+126] is
    truncated, so censored SURVIVED episodes are never silently pooled with
    sealed ones.
9.  RS cross-sections follow the two distinct frozen formulas literally:
    `E1f`/`E2f` subtract the same-day cross-sectional median of individual r63/r21
    values, while `E3f`–`E5f` use `rs_line = c / eqw_index`. The index compounds
    the per-day cross-sectional median DAILY RETURN of that day's PIT-eligible
    names and is rebased to 1.0 at the panel's first session. `rs_line` is rebased
    at each segment's first bar; every downstream RS feature is invariant to that
    constant.
10. `feature_library` returns one row per requested (segment, day) with one
    column per feature — long over observations, wide over the 36 features.
    Coverage nulls are preserved as NaN and never imputed.
11. Matching buckets (quintile of r126, terciles of rv63 and 21d dollar volume)
    are cut **within calendar quarter over the union of cases and the control
    candidate pool** — the natural "within-track, within-quarter" cross-section —
    and the same edges label both arms.
12. "Controls from other names" excludes any candidate whose BASE TICKER matches
    the case's, not merely its identity segment.
13. `matched_delta_stats` p-values are two-sided bootstrap p-values from the
    episode-peak-month block resample (`2·min(P(median ≤ 0), P(median ≥ 0))`,
    floored at 1/(B+1)) and feed BH-FDR within family. §4.5's aggregation is
    EPISODE-FIRST: `episode_deltas` collapses an episode's {21,10,5} snapshots to
    their MEDIAN before anything is pooled, so N is distinct episodes. A Δ exists
    only where the case and ≥2 controls are finite. A direction-declared feature
    must show the declared sign; a direction-0 field can only ever be graded
    `EXPLORATORY-DISCOVERY`, never DETECTION.
14. `top_ruler` computes each metric per BASE TICKER first and then takes the
    median across tickers (per-name-first, then pooled), so one heavily-fired
    name cannot carry a ruler number.
15. D5's `v_z` is volume z-scored against its own trailing 252-session
    distribution (PIT rolling), correlated over 21 sessions with |daily return|.
16. Where a rung carries no `high`/`low`, true range degrades to
    |c_t − c_{t−1}| rather than dropping the name; where it carries no `open`,
    C5 (`gap_freq21`) is null and counted in coverage.
17. §3 RAW-LEVEL ELIGIBILITY. The $3 price floor and the $2M median-21d
    dollar-volume floor read the **raw as-printed** close and close×volume; every
    window, trigger and feature reads the **repaired** frame. This is not a
    nicety: `split_adjust` recovers the factor from the FULL series, so a 2025
    split rescales every 2022 repaired close, and an adjusted-price floor would
    evict 2022 days on 2025 information. The split-factor STEP DAY is ineligible;
    the days before it are never retro-removed. Because the repair divides
    open/high/low/close by the factor and multiplies volume by it, repaired
    close×volume is invariant, so the liquidity floor reads the same either way —
    the price floor is where the leak lived.
18. Every frozen feature is a ratio, a log-difference, an ordinal lag, or a
    standardized quantity over a window in which the split factor is CONSTANT, so
    a future split cannot move a past feature value. That is an argument, not a
    proof, so it is enforced as a hard gate: `tests/test_top_anatomy.py`'s
    full-series-vs-prefix parity test runs a mid-series split through the real
    repair path and demands bit-level agreement at d for a feature from every
    family, and the harness re-checks 3 sampled names per track before any
    experiment runs.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "IDENTITY_GAP_MAX_SESSIONS", "MIN_CLOSE", "MIN_MEDIAN_DVOL21", "MIN_PRIOR_SESSIONS",
    "EXT_R126_MIN", "EXT_R63_MIN", "EXT_ATRZ_MIN", "NEAR_HIGH_FRAC", "NEAR_HIGH_LOOKBACK",
    "EPISODE_GAP_MAX", "EPISODE_MIN_EXT_DAYS", "RACE_HORIZON", "RACE_DD_FRAC",
    "RACE_UP_FRAC", "PEAK_BUFFER", "PEAK_SEAL_WINDOW", "CASE_OFFSETS", "MAX_CONTROLS",
    "MIN_FINITE_CONTROLS", "MIN_EPISODE_MONTHS", "E1B_EMBARGO_SESSIONS",
    "BOOTSTRAP_B", "FDR_Q", "FEATURES", "FEATURE_FAMILY", "FEATURE_DIRECTION",
    "FAMILY_NAMES", "segment_ticker", "identity_segment_bounds", "split_identity_segments",
    "eligibility_mask", "equal_weight_median_index", "cross_sectional_median_returns",
    "extended_mask", "extract_episodes",
    "race_labels", "episode_peaks", "feature_library", "matched_controls",
    "matched_deltas", "episode_deltas", "matched_delta_stats", "direction_tail",
    "top_ruler", "bh_fdr",
]

# ── frozen construction constants (prereg §3–§5; changing one is a new arm) ───
IDENTITY_GAP_MAX_SESSIONS = 60   # interior tape gap that means "different company"
MIN_CLOSE = 3.0                  # §3 eligibility floor
MIN_MEDIAN_DVOL21 = 2e6          # §3 eligibility floor (median 21d dollar volume)
MIN_PRIOR_SESSIONS = 260         # §3 history floor, inside the identity segment
EXT_R126_MIN = 0.50              # §4.1 primary
EXT_R63_MIN = 0.35               # §4.1 sensitivity arm (a)
EXT_ATRZ_MIN = 6.0               # §4.1 sensitivity arm (b): (c-MA200)/ATR63
NEAR_HIGH_FRAC = 0.90            # §4.1 "still extended, not already broken"
NEAR_HIGH_LOOKBACK = 252
EPISODE_GAP_MAX = 21             # §4.2
EPISODE_MIN_EXT_DAYS = 5         # §4.2 (micro-spells kept in the tape, out of E1)
RACE_HORIZON = 250               # §4.3
RACE_DD_FRAC = 0.80              # §4.3 TOPPED barrier: close <= 0.80 x running peak
RACE_UP_FRAC = 1.15              # §4.3 CONTINUED barrier: close >= 1.15 x entry
PEAK_BUFFER = 63                 # §4.4 peak search runs to episode_end + 63
PEAK_SEAL_WINDOW = 126           # §4.4 sealing window after the peak
CASE_OFFSETS = (21, 10, 5)       # §4.5 days_to_peak snapshots
MAX_CONTROLS = 4                 # §4.5
MIN_FINITE_CONTROLS = 2          # §4.5 a Δ needs the case + >=2 finite controls
MIN_EPISODE_MONTHS = 12          # §4.5 registered separation needs >=12 peak-months
BOOTSTRAP_B = 2000               # §4.5
FDR_Q = 0.10                     # §0 trial budget
E1B_EMBARGO_SESSIONS = 250       # §4.7 walk-forward purge = the full label horizon
AUX_FWD_HORIZONS = (21, 63, 126)  # §4.3 display-grade auxiliaries
AUX_DD_LEVELS = (0.10, 0.15, 0.30)

#: The 36 frozen features, in prereg §4.6 order. `A1..A8 B1..B6 C1..C6 D1..D6
#: E1f..E5f F1..F5`. The leading token is the prereg's own label, so a table row
#: can always be traced back to the frozen text.
FEATURES: tuple[str, ...] = (
    "A1_r21", "A2_r63", "A3_r126", "A4_r252", "A5_ext_ma50_atr21",
    "A6_ext_ma200_atr21", "A7_late_gain_share", "A8_trend_r2_63",
    "B1_accel_r21", "B2_rsi14", "B3_rsi14_chg10", "B4_newhigh63_rate21",
    "B5_upday_rate21", "B6_max_up_streak21",
    "C1_rv21", "C2_rv21_over_rv63", "C3_semivol_ratio63", "C4_atr21_pct_chg21",
    "C5_gap_freq21", "C6_tr5_over_tr63",
    "D1_dvol_z", "D2_slope21_ln_vol", "D3_updown_dvol_ratio21", "D4_ppe_chg21",
    "D5_corr21_volz_absret", "D6_churn21",
    "E1f_xr63", "E2f_xr21", "E3f_rs_peak_lag", "E4f_price_rs_gap", "E5f_rs_decel",
    "F1_episode_age", "F2_drawdown_in_episode", "F3_days_since_63d_high",
    "F4_deepest_dip21_vs_max63", "F5_reclaim_speed",
)

#: Auxiliary column carried beside the 36 (printed, never tested): the F5 dip is
#: open right now rather than reclaimed.
F5_UNRECLAIMED_COL = "F5x_dip_unreclaimed"

FAMILY_NAMES = {
    "A": "extension & geometry", "B": "momentum & acceleration",
    "C": "volatility structure", "D": "volume & effort",
    "E": "relative strength", "F": "maturation & structure",
}

FEATURE_FAMILY: dict[str, str] = {f: f[0] for f in FEATURES}

#: Pre-declared direction per §4.6. +1 = higher value expected on TOPPED days,
#: −1 = lower, 0 = exploratory (sign not pre-committed; two-sided).
FEATURE_DIRECTION: dict[str, int] = {
    "A1_r21": 0, "A2_r63": 0, "A3_r126": 0, "A4_r252": 0,
    "A5_ext_ma50_atr21": 1, "A6_ext_ma200_atr21": 1, "A7_late_gain_share": 1,
    "A8_trend_r2_63": 0,
    "B1_accel_r21": -1, "B2_rsi14": 0, "B3_rsi14_chg10": -1,
    "B4_newhigh63_rate21": 0, "B5_upday_rate21": 0, "B6_max_up_streak21": 0,
    "C1_rv21": 0, "C2_rv21_over_rv63": 1, "C3_semivol_ratio63": 1,
    "C4_atr21_pct_chg21": 1, "C5_gap_freq21": 0, "C6_tr5_over_tr63": 0,
    "D1_dvol_z": 0, "D2_slope21_ln_vol": 0, "D3_updown_dvol_ratio21": -1,
    "D4_ppe_chg21": -1, "D5_corr21_volz_absret": -1, "D6_churn21": 1,
    "E1f_xr63": 0, "E2f_xr21": 0, "E3f_rs_peak_lag": 1, "E4f_price_rs_gap": 1,
    "E5f_rs_decel": -1,
    "F1_episode_age": 1, "F2_drawdown_in_episode": -1, "F3_days_since_63d_high": 1,
    "F4_deepest_dip21_vs_max63": -1, "F5_reclaim_speed": 1,
}


# ══════════════════════════════════════════════════════════════════════════════
# identity segments
# ══════════════════════════════════════════════════════════════════════════════
def segment_ticker(name: str) -> str:
    """Base ticker of an identity-segment name (`BBBY#1` -> `BBBY`).

    Every clustering unit that must be a COMPANY rather than a series — the
    ticker-cluster bootstrap, grouped CV folds, the "controls from other names"
    exclusion — keys on this, never on the segment name.
    """
    return str(name).split("#", 1)[0]


def identity_segment_bounds(
    index: pd.DatetimeIndex,
    calendar: pd.DatetimeIndex | None = None,
    *,
    max_gap_sessions: int = IDENTITY_GAP_MAX_SESSIONS,
) -> list[tuple[int, int]]:
    """Positional `[(start, end), ...]` spans of one ticker's bars, split at reused-ticker gaps.

    A gap is the number of MARKET SESSIONS with no bar between two consecutive
    bars, counted on ``calendar`` (the union trading calendar of the panel). More
    than ``max_gap_sessions`` of silence means the tape stopped carrying this
    company; whatever resumes afterwards is treated as a different name.

    With no ``calendar`` the gap is counted in NumPy business days between the two
    dates — the honest fallback when the caller has only one series, slightly
    conservative (holidays inflate it) and used only in tests and one-off reads.
    Bounds are inclusive on both ends.
    """
    idx = pd.DatetimeIndex(index)
    n = len(idx)
    if n == 0:
        return []
    if n == 1:
        return [(0, 0)]
    if calendar is not None:
        cal = pd.DatetimeIndex(calendar)
        pos = pd.Series(np.arange(len(cal)), index=cal).reindex(idx).to_numpy(dtype=float)
        if np.isnan(pos).any():          # a bar off the calendar: fall back per-pair
            gaps = _busday_gaps(idx)
        else:
            gaps = np.diff(pos) - 1.0
    else:
        gaps = _busday_gaps(idx)
    cuts = np.flatnonzero(gaps > float(max_gap_sessions)) + 1
    starts = [0, *cuts.tolist()]
    ends = [*(c - 1 for c in cuts), n - 1]
    return list(zip(starts, ends))


def _busday_gaps(idx: pd.DatetimeIndex) -> np.ndarray:
    """Business-day sessions strictly between consecutive dates (fallback measure)."""
    d = idx.values.astype("datetime64[D]")
    return np.busday_count(d[:-1], d[1:]).astype(float) - 1.0


def split_identity_segments(
    bars_by_ticker: Mapping[str, pd.DataFrame],
    calendar: pd.DatetimeIndex | None = None,
    *,
    max_gap_sessions: int = IDENTITY_GAP_MAX_SESSIONS,
) -> dict[str, pd.DataFrame]:
    """Split every ticker's bars into identity segments keyed `TICK` or `TICK#k`.

    A ticker whose tape is continuous keeps its bare name (so ordinary reports
    read `NVDA`, not `NVDA#0`); a reused ticker yields `TICK#0`, `TICK#1`, … in
    chronological order. `segment_ticker` recovers the base ticker either way.
    """
    out: dict[str, pd.DataFrame] = {}
    for tk, bars in bars_by_ticker.items():
        if bars is None or len(bars) == 0:
            continue
        b = bars.sort_index()
        spans = identity_segment_bounds(b.index, calendar, max_gap_sessions=max_gap_sessions)
        if len(spans) == 1:
            out[str(tk)] = b
            continue
        for k, (s, e) in enumerate(spans):
            out[f"{tk}#{k}"] = b.iloc[s:e + 1]
    return out


# ══════════════════════════════════════════════════════════════════════════════
# small numeric helpers (all trailing-window, all inclusive of the current bar)
# ══════════════════════════════════════════════════════════════════════════════
def _bars(frame: pd.DataFrame | None, col: str) -> pd.Series | None:
    """One panel column compacted to its own bars (NaN rows dropped)."""
    if frame is None or col not in frame.columns:
        return None
    s = pd.to_numeric(frame[col], errors="coerce")
    s = s[s.notna()]
    return s if len(s) else None


def _win(a: np.ndarray, w: int) -> np.ndarray:
    """Trailing windows of width `w` ending at each position >= w-1 (a view)."""
    return np.lib.stride_tricks.sliding_window_view(a, w)


def _lag_since_max(a: np.ndarray, w: int) -> np.ndarray:
    """Sessions since the trailing-`w` maximum; ties resolve to the MOST RECENT.

    A window holding any NaN answers NaN — `argmax` would otherwise report the
    NaN's own position as the maximum, which reads as a fresh high.
    """
    out = np.full(len(a), np.nan)
    if len(a) >= w:
        rev = _win(a, w)[:, ::-1]
        lag = np.argmax(rev, axis=1).astype(float)
        out[w - 1:] = np.where(np.isnan(rev).any(axis=1), np.nan, lag)
    return out


def _rolling_ols_slope(y: np.ndarray, w: int) -> np.ndarray:
    """OLS slope of `y` on t (unit steps) over trailing windows of width `w`.

    Closed form via one convolution: the design is fixed, so Sxx is a constant and
    Sxy is a weighted trailing sum. NaN inside a window propagates to NaN, which
    is the honest answer when the input has a hole.
    """
    n = len(y)
    out = np.full(n, np.nan)
    if n < w or w < 2:
        return out
    x = np.arange(w, dtype=float)
    xc = x - x.mean()
    sxx = float((xc ** 2).sum())
    sxy = np.convolve(y, xc[::-1], mode="valid")
    out[w - 1:] = sxy / sxx
    return out


def _rolling_r2_on_t(y: np.ndarray, w: int) -> np.ndarray:
    """R-squared of an OLS fit of `y` on t over trailing windows of width `w`."""
    n = len(y)
    out = np.full(n, np.nan)
    if n < w or w < 3:
        return out
    x = np.arange(w, dtype=float)
    xc = x - x.mean()
    sxx = float((xc ** 2).sum())
    sxy = np.convolve(y, xc[::-1], mode="valid")
    win = _win(y, w)
    syy = ((win - win.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[w - 1:] = np.where(syy > 0, (sxy ** 2) / (sxx * syy), np.nan)
    return out


def _rolling_max_true_run(a: np.ndarray, w: int) -> np.ndarray:
    """Longest consecutive ``True`` run wholly inside each trailing window.

    A cumulative streak cannot be rolled directly: when a 30-session up streak
    enters a 21-session window, its global counter reads 30 even though the
    longest run *inside that window* is 21.  This vectorized window scan keeps the
    frozen B6 feature bounded by its declared 21-session lookback.
    """
    a = np.asarray(a, dtype=bool)
    out = np.full(len(a), np.nan)
    if len(a) < w:
        return out
    win = _win(a, w)
    cur = np.zeros(len(win), dtype=np.int16)
    best = np.zeros(len(win), dtype=np.int16)
    for j in range(w):
        cur = np.where(win[:, j], cur + 1, 0)
        best = np.maximum(best, cur)
    out[w - 1:] = best
    return out


def _true_range(c: pd.Series, h: pd.Series | None, lo: pd.Series | None) -> pd.Series:
    """True range, degrading to |Δclose| when the rung carries no high/low."""
    prev = c.shift(1)
    if h is None or lo is None:
        return (c - prev).abs()
    hh = h.reindex(c.index)
    ll = lo.reindex(c.index)
    tr = pd.concat([(hh - ll).abs(), (hh - prev).abs(), (ll - prev).abs()], axis=1).max(axis=1)
    return tr.where(hh.notna() & ll.notna(), (c - prev).abs())


def _rsi_wilder(c: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI: alpha = 1/n exponential smoothing of gains and losses."""
    d = c.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rsi = pd.Series(np.where(ad > 0, 100.0 - 100.0 / (1.0 + au / ad.replace(0.0, np.nan)), 100.0),
                    index=c.index)
    return rsi.where(au.notna() & ad.notna())


def bh_fdr(pvals: Sequence[float]) -> np.ndarray:
    """Benjamini-Hochberg step-up q-values. NaN p-values return NaN q-values."""
    p = np.asarray(list(pvals), dtype=float)
    q = np.full(p.shape, np.nan)
    ok = np.flatnonzero(np.isfinite(p))
    if ok.size == 0:
        return q
    m = ok.size
    order = ok[np.argsort(p[ok], kind="mergesort")]
    ranked = p[order] * m / np.arange(1, m + 1)
    q[order] = np.minimum.accumulate(ranked[::-1])[::-1].clip(0.0, 1.0)
    return q


# ══════════════════════════════════════════════════════════════════════════════
# §3 eligibility · §4.1 extended day
# ══════════════════════════════════════════════════════════════════════════════
def _raw_floor_inputs(
    col: str,
    c: pd.Series,
    dollar_vol_df: pd.DataFrame,
    raw_close_df: pd.DataFrame | None,
    raw_dollar_vol_df: pd.DataFrame | None,
    split_day_df: pd.DataFrame | None,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """The three RAW-level §3 floor inputs for one segment: price, $vol, split-step flag.

    §3 pins the price and liquidity floors to the **raw as-printed** prints, not the
    split-repaired ones. This is the whole point: a 10:1 split in 2025 divides every
    2022 repaired close by ten, so an adjusted-price floor would retroactively evict
    2022 days on 2025 information. The repaired frame still drives every window and
    every feature. When a caller supplies no raw frames (a synthetic panel with no
    repair applied) the repaired frames stand in — stated, never silent.
    """
    def _col(frame: pd.DataFrame | None, default: pd.Series) -> pd.Series:
        if frame is None or col not in getattr(frame, "columns", ()):
            return default
        return pd.to_numeric(frame[col], errors="coerce").reindex(c.index)

    dv_default = (pd.to_numeric(dollar_vol_df[col], errors="coerce").reindex(c.index)
                  if col in dollar_vol_df.columns else pd.Series(np.nan, index=c.index))
    raw_c = _col(raw_close_df, c)
    raw_dv = _col(raw_dollar_vol_df, dv_default)
    if split_day_df is not None and col in getattr(split_day_df, "columns", ()):
        step = split_day_df[col].reindex(c.index).fillna(False).astype(bool)
    else:
        step = pd.Series(False, index=c.index)
    return raw_c, raw_dv, step


def eligibility_mask(
    close_df: pd.DataFrame,
    dollar_vol_df: pd.DataFrame,
    *,
    raw_close_df: pd.DataFrame | None = None,
    raw_dollar_vol_df: pd.DataFrame | None = None,
    split_day_df: pd.DataFrame | None = None,
    min_close: float = MIN_CLOSE,
    min_dollar_vol: float = MIN_MEDIAN_DVOL21,
    min_prior_sessions: int = MIN_PRIOR_SESSIONS,
) -> pd.DataFrame:
    """§3 tradeability floors per (identity segment, day): price, liquidity, history.

    The price and liquidity floors read the **RAW as-printed** close and raw
    close×volume (§3); the ≥260-prior-session history floor is counted on the
    segment's own bars. A **split-factor step day is ineligible** — the repair snaps
    a real price discontinuity and that one bar is not tradeable evidence — while
    the days BEFORE it are left alone, because removing them would be using a future
    split to edit the past.

    Columns of every frame are IDENTITY SEGMENTS, not raw tickers: each column is
    compacted to its own bars before any window is taken, so a halted stretch costs
    sessions rather than silently borrowing a neighbour's.
    """
    out = pd.DataFrame(False, index=close_df.index, columns=close_df.columns)
    for col in close_df.columns:
        c = _bars(close_df, col)
        if c is None or len(c) <= min_prior_sessions:
            continue
        raw_c, raw_dv, step = _raw_floor_inputs(col, c, dollar_vol_df, raw_close_df,
                                                raw_dollar_vol_df, split_day_df)
        med_dv = raw_dv.rolling(21, min_periods=21).median()
        pos = np.arange(len(c))
        ok = ((raw_c >= min_close) & (med_dv >= min_dollar_vol)
              & (pos >= min_prior_sessions) & (~step))
        out.loc[c.index[ok.fillna(False).to_numpy()], col] = True
    return out


def extended_mask(
    close_df: pd.DataFrame,
    dollar_vol_df: pd.DataFrame,
    *,
    variant: str = "primary",
    high_df: pd.DataFrame | None = None,
    low_df: pd.DataFrame | None = None,
    raw_close_df: pd.DataFrame | None = None,
    raw_dollar_vol_df: pd.DataFrame | None = None,
    split_day_df: pd.DataFrame | None = None,
    min_close: float = MIN_CLOSE,
    min_dollar_vol: float = MIN_MEDIAN_DVOL21,
    min_prior_sessions: int = MIN_PRIOR_SESSIONS,
    near_high_frac: float = NEAR_HIGH_FRAC,
    near_high_lookback: int = NEAR_HIGH_LOOKBACK,
) -> pd.DataFrame:
    """§4.1 EXTENDED days per identity segment — the population everything conditions on.

    Primary: ``r126 >= +0.50`` AND ``close >= 0.90 x max(close, trailing 252)`` AND
    the §3 floors. The trigger and near-high terms read the **repaired** close (they
    are ratios, so the split factor cancels); the price and liquidity floors read the
    **raw as-printed** prints and a split-factor step day is ineligible (see
    `eligibility_mask`). The near-high term is the inherited `sector_signals`
    invariant — "still extended, not already broken" — and it is what keeps this from
    becoming a breakdown screen.

    Report-only sensitivity arms (no registration claims ride on them):
      ``variant="r63"``  -> ``r63 >= +0.35`` with the same near-high term.
      ``variant="atrz"`` -> ``(close − MA200)/ATR63 >= 6`` with the same term.
    """
    if variant not in ("primary", "r63", "atrz"):
        raise ValueError(f"unknown extension variant {variant!r}")
    out = pd.DataFrame(False, index=close_df.index, columns=close_df.columns)
    for col in close_df.columns:
        c = _bars(close_df, col)
        if c is None or len(c) <= min_prior_sessions:
            continue
        raw_c, raw_dv, step = _raw_floor_inputs(col, c, dollar_vol_df, raw_close_df,
                                                raw_dollar_vol_df, split_day_df)
        med_dv = raw_dv.rolling(21, min_periods=21).median()
        near_high = c >= near_high_frac * c.rolling(near_high_lookback,
                                                    min_periods=near_high_lookback).max()
        if variant == "primary":
            trig = (c / c.shift(126) - 1.0) >= EXT_R126_MIN
        elif variant == "r63":
            trig = (c / c.shift(63) - 1.0) >= EXT_R63_MIN
        else:
            tr = _true_range(c, _bars(high_df, col), _bars(low_df, col))
            atr63 = tr.rolling(63, min_periods=63).mean()
            ma200 = c.rolling(200, min_periods=200).mean()
            trig = ((c - ma200) / atr63.replace(0.0, np.nan)) >= EXT_ATRZ_MIN
        pos = np.arange(len(c))
        ok = (trig.fillna(False) & near_high.fillna(False) & (raw_c >= min_close)
              & (med_dv >= min_dollar_vol) & (pos >= min_prior_sessions) & (~step))
        out.loc[c.index[ok.fillna(False).to_numpy()], col] = True
    return out


# ══════════════════════════════════════════════════════════════════════════════
# §4.2 episodes
# ══════════════════════════════════════════════════════════════════════════════
def extract_episodes(
    ext_mask: pd.DataFrame,
    close_df: pd.DataFrame | None = None,
    *,
    max_gap_sessions: int = EPISODE_GAP_MAX,
) -> pd.DataFrame:
    """§4.2 episodes: runs of EXT days per segment, merging gaps of <= 21 sessions.

    The merged quantity is the count of NON-EXT sessions between two EXT days, so
    21 intervening quiet sessions merge and 22 split. Sessions are counted on the
    segment's own bars: pass ``close_df`` (the same panel the mask came from) so a
    halted stretch is not counted as if the name had traded. Episodes with fewer
    than `EPISODE_MIN_EXT_DAYS` EXT days are RETURNED (they belong to the tape and
    to base rates) and flagged `micro`, which is what excludes them from E1.

    Returns one row per episode: segment, ticker, episode_id, start, end,
    n_ext_days, span_sessions, micro.
    """
    rows = []
    for col in ext_mask.columns:
        m = ext_mask[col].fillna(False).to_numpy(dtype=bool)
        if not m.any():
            continue
        if close_df is not None and col in close_df.columns:
            bars = close_df[col].notna().to_numpy(dtype=bool)
        else:
            bars = np.ones(len(m), dtype=bool)
        bar_pos = np.full(len(m), -1)
        bar_pos[bars] = np.arange(int(bars.sum()))
        hit = np.flatnonzero(m & bars)
        if hit.size == 0:
            continue
        p = bar_pos[hit]                              # positions on the segment's own bars
        brk = np.flatnonzero((p[1:] - p[:-1] - 1) > max_gap_sessions) + 1
        for s, e in zip([0, *brk.tolist()], [*(b - 1 for b in brk), len(p) - 1]):
            start_d = ext_mask.index[hit[s]]
            end_d = ext_mask.index[hit[e]]
            n_ext = int(e - s + 1)
            rows.append({
                "segment": col, "ticker": segment_ticker(col),
                "episode_id": f"{col}|{pd.Timestamp(start_d).date()}",
                "start": start_d, "end": end_d, "n_ext_days": n_ext,
                "span_sessions": int(p[e] - p[s] + 1),
                "micro": n_ext < EPISODE_MIN_EXT_DAYS,
            })
    cols = ["segment", "ticker", "episode_id", "start", "end", "n_ext_days",
            "span_sessions", "micro"]
    return pd.DataFrame(rows, columns=cols)


# ══════════════════════════════════════════════════════════════════════════════
# §4.3 day-level race labels
# ══════════════════════════════════════════════════════════════════════════════
def race_labels(
    close_df: pd.DataFrame,
    ext_mask: pd.DataFrame,
    *,
    horizon: int = RACE_HORIZON,
    dd_frac: float = RACE_DD_FRAC,
    up_frac: float = RACE_UP_FRAC,
) -> pd.DataFrame:
    """§4.3 TOPPED / CONTINUED / CENSORED for every EXT day (hindsight-legal).

    From EXT day d at entry close c_d, walk forward at most ``horizon`` of the
    segment's own bars while tracking the running peak from d onward. TOPPED fires
    the first bar whose close is <= ``dd_frac`` x running peak; CONTINUED fires the
    first bar whose close is >= ``up_frac`` x c_d; whichever fires first wins and a
    same-bar tie resolves TOPPED (conservative, per §4.3). Neither firing leaves
    CENSORED, with `censor_reason` separating a spent horizon from a spent tape
    (delisting): a delisting that collapses fires TOPPED on its own bars, a
    delisting that simply stops is CENSORED.

    Also carries the §4.3 display-grade auxiliaries — forward returns and maximum
    forward drawdown from the post-d peak at 21/63/126 sessions, plus >=10/15/30%
    drawdown event flags — as descriptive columns; nothing here is tested.

    One row per EXT day. The forward walk is a single strided window per segment,
    so a ~20k-name panel resolves in minutes, not hours.
    """
    frames = []
    h = int(horizon)
    for col in close_df.columns:
        c = _bars(close_df, col)
        if c is None:
            continue
        if col not in ext_mask.columns:
            continue
        ext = ext_mask[col].fillna(False).reindex(c.index).fillna(False).to_numpy(dtype=bool)
        idx = np.flatnonzero(ext)
        if idx.size == 0:
            continue
        v = c.to_numpy(dtype=float)
        n = len(v)
        pad = np.concatenate([v, np.full(h, np.nan)])
        w = _win(pad, h + 1)[idx]                       # (m, h+1); offset 0 == entry bar
        peak = np.fmax.accumulate(np.where(np.isnan(w), -np.inf, w), axis=1)
        peak = np.where(np.isfinite(peak), peak, np.nan)
        entry = w[:, 0][:, None]
        with np.errstate(invalid="ignore"):
            hit_top = w <= dd_frac * peak
            hit_up = w >= up_frac * entry
        hit_top[:, 0] = False
        hit_up[:, 0] = False
        any_top, any_up = hit_top.any(axis=1), hit_up.any(axis=1)
        t_top = np.where(any_top, hit_top.argmax(axis=1), h + 1)
        t_up = np.where(any_up, hit_up.argmax(axis=1), h + 1)
        label = np.where(t_top <= t_up, "TOPPED", "CONTINUED").astype(object)
        resolve = np.minimum(t_top, t_up).astype(float)
        censored = ~(any_top | any_up)
        label[censored] = "CENSORED"
        resolve[censored] = np.nan
        avail = (n - 1) - idx                            # bars of tape left after d
        reason = np.where(censored, np.where(avail >= h, "horizon", "data_end"), "")

        rec = {
            "segment": col, "ticker": segment_ticker(col), "date": c.index[idx],
            "entry_close": v[idx], "label": label, "sessions_to_resolve": resolve,
            "censor_reason": reason, "sessions_available": avail,
        }
        rec["resolve_date"] = [
            c.index[min(i + int(t), n - 1)] if np.isfinite(t) else pd.NaT
            for i, t in zip(idx, resolve)
        ]
        for k in AUX_FWD_HORIZONS:
            if h < k:
                rec[f"fwd_ret_{k}"] = np.nan
                rec[f"max_dd_{k}"] = np.nan
                continue
            rec[f"fwd_ret_{k}"] = w[:, k] / w[:, 0] - 1.0
            with np.errstate(invalid="ignore"):
                dd = w[:, 1:k + 1] / peak[:, 1:k + 1] - 1.0
            allnan = np.isnan(dd).all(axis=1)
            rec[f"max_dd_{k}"] = np.where(allnan, np.nan,
                                          np.nanmin(np.where(allnan[:, None], 0.0, dd), axis=1))
        for lvl in AUX_DD_LEVELS:
            with np.errstate(invalid="ignore"):
                rec[f"dd_ge_{int(lvl * 100)}"] = ((w[:, 1:] / peak[:, 1:] - 1.0)
                                                  <= -lvl).any(axis=1)
        frames.append(pd.DataFrame(rec))
    if not frames:
        return pd.DataFrame(columns=["segment", "ticker", "date", "entry_close", "label"])
    return pd.concat(frames, ignore_index=True).sort_values(["segment", "date"],
                                                            ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# §4.4 episode peak and terminal top
# ══════════════════════════════════════════════════════════════════════════════
def episode_peaks(
    close_df: pd.DataFrame,
    episodes: pd.DataFrame,
    ext_mask: pd.DataFrame | None = None,
    *,
    peak_buffer: int = PEAK_BUFFER,
    seal_window: int = PEAK_SEAL_WINDOW,
    dd_frac: float = RACE_DD_FRAC,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """§4.4 episode peak, terminal-top outcome, and the `days_to_peak` anchor.

    ``peak(e)`` is the argmax close over [episode_start, episode_end + 63] (ties to
    the earliest bar). The episode is TOPPED when close falls to <= 0.80 x the peak
    close somewhere in [peak, peak + 126] **with no intervening close above the
    peak** before that print; otherwise SURVIVED. `peak_window_censored` marks the
    SURVIVED episodes whose sealing window ran off the end of the tape — they are
    not evidence of survival, and must never be pooled with sealed ones silently.

    Returns ``(episodes_out, dtp)``: the episode table with peak columns, and one
    row per EXT day inside an episode carrying ``days_to_peak`` (positive = the day
    precedes the peak) — the anchor for every lead-time read.
    """
    if episodes.empty:
        return episodes.copy(), pd.DataFrame(
            columns=["segment", "ticker", "episode_id", "date", "days_to_peak"])
    out_rows, dtp_rows = [], []
    for col, grp in episodes.groupby("segment", sort=False):
        c = _bars(close_df, col)
        if c is None:
            continue
        v = c.to_numpy(dtype=float)
        n = len(v)
        pos = pd.Series(np.arange(n), index=c.index)
        if ext_mask is not None and col in ext_mask.columns:
            ext = ext_mask[col].fillna(False).reindex(c.index).fillna(False).to_numpy(dtype=bool)
        else:
            ext = np.ones(n, dtype=bool)
        for _, ep in grp.iterrows():
            if ep["start"] not in pos.index or ep["end"] not in pos.index:
                continue
            s, e = int(pos[ep["start"]]), int(pos[ep["end"]])
            hi = min(n - 1, e + peak_buffer)
            pk = s + int(np.argmax(v[s:hi + 1]))
            pk_c = float(v[pk])
            seal_hi = min(n - 1, pk + seal_window)
            fwd = v[pk + 1:seal_hi + 1]
            dd_hits = np.flatnonzero(fwd <= dd_frac * pk_c)
            new_high = np.flatnonzero(fwd > pk_c)
            topped = False
            dd_date = pd.NaT
            if dd_hits.size:
                first_dd = int(dd_hits[0])
                if new_high.size == 0 or int(new_high[0]) > first_dd:
                    topped = True
                    dd_date = c.index[pk + 1 + first_dd]
            row = ep.to_dict()
            row.update({
                "peak_date": c.index[pk], "peak_close": pk_c,
                "outcome": "TOPPED" if topped else "SURVIVED",
                "seal_date": dd_date,
                "peak_window_truncated": bool(e + peak_buffer > n - 1),
                "peak_window_censored": bool((not topped) and pk + seal_window > n - 1),
            })
            out_rows.append(row)
            span = np.arange(s, min(n - 1, e) + 1)
            span = span[ext[span]]
            for j in span:
                dtp_rows.append({
                    "segment": col, "ticker": segment_ticker(col),
                    "episode_id": ep["episode_id"], "date": c.index[j],
                    "days_to_peak": int(pk - j),
                })
    eo = pd.DataFrame(out_rows)
    dtp = pd.DataFrame(dtp_rows,
                       columns=["segment", "ticker", "episode_id", "date", "days_to_peak"])
    return eo, dtp


# ══════════════════════════════════════════════════════════════════════════════
# §4.6 feature library (36 features, all PIT)
# ══════════════════════════════════════════════════════════════════════════════
def equal_weight_median_index(
    close_df: pd.DataFrame,
    eligible: pd.DataFrame | None = None,
    *,
    min_names: int = 1,
) -> pd.Series:
    """The track's PIT equal-weight median return index (§4.6 `eqw index`).

    Built by COMPOUNDING the per-day cross-sectional MEDIAN DAILY RETURN of that
    day's eligible names, rebased to 1.0 at the first session. Compounding the
    median return rather than taking the median of cumulative levels is what makes
    the series immune to composition changes — a name entering or leaving the
    eligible set moves the level of a "median of levels" index by construction,
    which would show up in every RS feature as a fake cross-sectional move. Days
    with fewer than ``min_names`` eligible names take a flat step (and are
    reported by the caller's coverage counts). Strictly PIT: day t uses day-t and
    prior bars only.
    """
    r = close_df / close_df.shift(1) - 1.0
    if eligible is not None:
        r = r.where(eligible.reindex_like(r).fillna(False))
    n = r.notna().sum(axis=1)
    med = r.median(axis=1, skipna=True).where(n >= min_names)
    return (1.0 + med.fillna(0.0)).cumprod().rename("eqw_median_index")


def cross_sectional_median_returns(
    close_df: pd.DataFrame,
    eligible: pd.DataFrame | None = None,
    *,
    windows: Sequence[int] = (21, 63),
    min_names: int = 1,
) -> pd.DataFrame:
    """Same-day PIT medians of individual trailing returns for E1f/E2f.

    The prereg distinguishes ``xr63 = r63 - median universe r63`` from the
    equal-weight median *index* used to build ``rs_line``.  A return of that index
    is generally not the median of individual multi-session returns, so callers
    must carry both cross-sections.  Only names eligible on day ``d`` enter day
    ``d``'s median; no future membership or bar is consulted.
    """
    out = pd.DataFrame(index=close_df.index)
    mask = eligible.reindex_like(close_df).fillna(False) if eligible is not None else None
    for w in windows:
        r = close_df / close_df.shift(int(w)) - 1.0
        if mask is not None:
            r = r.where(mask)
        n = r.notna().sum(axis=1)
        out[f"r{int(w)}"] = r.median(axis=1, skipna=True).where(n >= min_names)
    return out


def _feature_frame(
    bars: pd.DataFrame,
    eqw: pd.Series | None,
    cross_sectional_returns: pd.DataFrame | None,
    episodes: pd.DataFrame | None,
) -> pd.DataFrame:
    """Every §4.6 feature for ONE identity segment, at every bar it can be computed."""
    c = pd.to_numeric(bars["close"], errors="coerce")
    c = c[c.notna()]
    idx = c.index
    n = len(idx)
    o = pd.to_numeric(bars["open"], errors="coerce").reindex(idx) if "open" in bars else None
    h = pd.to_numeric(bars["high"], errors="coerce").reindex(idx) if "high" in bars else None
    lo = pd.to_numeric(bars["low"], errors="coerce").reindex(idx) if "low" in bars else None
    v = pd.to_numeric(bars["volume"], errors="coerce").reindex(idx) if "volume" in bars else None
    if v is not None:
        v = v.where(v > 0)
    cv = c.to_numpy(dtype=float)
    lnc = pd.Series(np.log(cv), index=idx)
    ret = c / c.shift(1) - 1.0
    lret = lnc.diff()
    f = pd.DataFrame(index=idx)

    tr = _true_range(c, h, lo)
    atr21 = tr.rolling(21, min_periods=21).mean()
    max63 = c.rolling(63, min_periods=63).max()

    # A. extension & geometry
    f["A1_r21"] = c / c.shift(21) - 1.0
    f["A2_r63"] = c / c.shift(63) - 1.0
    f["A3_r126"] = c / c.shift(126) - 1.0
    f["A4_r252"] = c / c.shift(252) - 1.0
    f["A5_ext_ma50_atr21"] = (c - c.rolling(50, min_periods=50).mean()) / atr21.replace(0.0, np.nan)
    f["A6_ext_ma200_atr21"] = ((c - c.rolling(200, min_periods=200).mean())
                               / atr21.replace(0.0, np.nan))
    den = lnc - lnc.shift(126)
    f["A7_late_gain_share"] = ((lnc - lnc.shift(21)) / den).where(den > 0.05)
    f["A8_trend_r2_63"] = pd.Series(_rolling_r2_on_t(lnc.to_numpy(dtype=float), 63), index=idx)

    # B. momentum & acceleration
    f["B1_accel_r21"] = f["A1_r21"] - f["A1_r21"].shift(21)
    f["B2_rsi14"] = _rsi_wilder(c, 14)
    f["B3_rsi14_chg10"] = f["B2_rsi14"] - f["B2_rsi14"].shift(10)
    f["B4_newhigh63_rate21"] = (c >= max63).where(max63.notna()) \
        .astype(float).rolling(21, min_periods=21).mean()
    f["B5_upday_rate21"] = (ret > 0).astype(float).where(ret.notna()) \
        .rolling(21, min_periods=21).mean()
    up = (ret > 0).to_numpy(dtype=bool)
    f["B6_max_up_streak21"] = pd.Series(_rolling_max_true_run(up, 21), index=idx)

    # C. volatility structure
    ann = float(np.sqrt(252.0))
    rv21 = lret.rolling(21, min_periods=21).std() * ann
    rv63 = lret.rolling(63, min_periods=63).std() * ann
    f["C1_rv21"] = rv21
    f["C2_rv21_over_rv63"] = rv21 / rv63.replace(0.0, np.nan)
    down = ret.where(ret < 0)
    upr = ret.where(ret > 0)
    f["C3_semivol_ratio63"] = (down.rolling(63, min_periods=5).std()
                               / upr.rolling(63, min_periods=5).std().replace(0.0, np.nan))
    atr_pct = atr21 / c
    f["C4_atr21_pct_chg21"] = atr_pct - atr_pct.shift(21)
    if o is not None:
        gap = (o / c.shift(1) - 1.0).abs()
        f["C5_gap_freq21"] = (gap > 0.02).astype(float).where(gap.notna()) \
            .rolling(21, min_periods=21).mean()
    else:
        f["C5_gap_freq21"] = np.nan
    f["C6_tr5_over_tr63"] = (tr.rolling(5, min_periods=5).mean()
                             / tr.rolling(63, min_periods=63).mean().replace(0.0, np.nan))

    # D. volume & effort
    if v is not None:
        dv = c * v
        x = np.log(dv.rolling(21, min_periods=21).mean())
        f["D1_dvol_z"] = ((x - x.rolling(252, min_periods=252).mean())
                          / x.rolling(252, min_periods=252).std().replace(0.0, np.nan))
        f["D2_slope21_ln_vol"] = pd.Series(
            _rolling_ols_slope(np.log(v.to_numpy(dtype=float)), 21), index=idx)
        up_dv = dv.where(ret > 0, 0.0).where(ret.notna())
        dn_dv = dv.where(ret < 0, 0.0).where(ret.notna())
        su = up_dv.rolling(21, min_periods=21).sum()
        sd = dn_dv.rolling(21, min_periods=21).sum()
        f["D3_updown_dvol_ratio21"] = su / sd.replace(0.0, np.nan)
        vbase = v.rolling(252, min_periods=252).mean()
        effort = (v / vbase.replace(0.0, np.nan)).rolling(21, min_periods=21).mean()
        ppe = f["A1_r21"] / effort.replace(0.0, np.nan)
        f["D4_ppe_chg21"] = ppe - ppe.shift(21)
        vz = ((v - vbase) / v.rolling(252, min_periods=252).std().replace(0.0, np.nan))
        f["D5_corr21_volz_absret"] = vz.rolling(21, min_periods=21).corr(ret.abs())
        churn = ((v > 1.5 * vbase)
                 & (ret.abs() < 0.5 * ret.rolling(63, min_periods=63).std()))
        f["D6_churn21"] = churn.astype(float).where(vbase.notna()) \
            .rolling(21, min_periods=21).mean()
    else:
        for k in ("D1_dvol_z", "D2_slope21_ln_vol", "D3_updown_dvol_ratio21",
                  "D4_ppe_chg21", "D5_corr21_volz_absret", "D6_churn21"):
            f[k] = np.nan

    # E. relative strength (against the supplied PIT equal-weight median index)
    if eqw is not None and len(eqw):
        ew = pd.to_numeric(eqw, errors="coerce").reindex(idx)
        rs = c / ew.replace(0.0, np.nan)
        first = rs.dropna()
        rs = rs / float(first.iloc[0]) if len(first) else rs   # rebased per name (cancels)
        xret = cross_sectional_returns.reindex(idx) if cross_sectional_returns is not None \
            else None
        # Backward-compatible fallback is intentionally explicit: synthetic callers
        # that supply only an index still get a PIT value, while the research harness
        # always supplies the literal same-day medians pinned by §4.6.
        med63 = (pd.to_numeric(xret["r63"], errors="coerce")
                 if xret is not None and "r63" in xret else (ew / ew.shift(63) - 1.0))
        med21 = (pd.to_numeric(xret["r21"], errors="coerce")
                 if xret is not None and "r21" in xret else (ew / ew.shift(21) - 1.0))
        f["E1f_xr63"] = f["A2_r63"] - med63
        f["E2f_xr21"] = f["A1_r21"] - med21
        rs_lag = pd.Series(_lag_since_max(rs.to_numpy(dtype=float), 63), index=idx)
        f["E3f_rs_peak_lag"] = rs_lag
        c_lag = pd.Series(_lag_since_max(cv, 63), index=idx)
        f["E4f_price_rs_gap"] = rs_lag - c_lag
        lnrs = np.log(rs.to_numpy(dtype=float))
        sl = pd.Series(_rolling_ols_slope(lnrs, 21), index=idx)
        f["E5f_rs_decel"] = sl - sl.shift(21)
    else:
        for k in ("E1f_xr63", "E2f_xr21", "E3f_rs_peak_lag", "E4f_price_rs_gap",
                  "E5f_rs_decel"):
            f[k] = np.nan

    # F. maturation & structure
    f["F3_days_since_63d_high"] = pd.Series(_lag_since_max(cv, 63), index=idx)
    f["F4_deepest_dip21_vs_max63"] = (c / max63.replace(0.0, np.nan) - 1.0) \
        .rolling(21, min_periods=21).min()
    age = pd.Series(np.nan, index=idx)
    epmax = pd.Series(np.nan, index=idx)
    reclaim = pd.Series(np.nan, index=idx)
    unrec = pd.Series(False, index=idx)
    if episodes is not None and not episodes.empty:
        posmap = pd.Series(np.arange(n), index=idx)
        for _, ep in episodes.iterrows():
            if ep["start"] not in posmap.index:
                continue
            s = int(posmap[ep["start"]])
            e = int(posmap[ep["end"]]) if ep["end"] in posmap.index else n - 1
            e = min(e, n - 1)
            seg = cv[s:e + 1]
            run_max = np.maximum.accumulate(seg)
            age.iloc[s:e + 1] = np.arange(len(seg), dtype=float)
            epmax.iloc[s:e + 1] = seg / run_max - 1.0
            # F5: most recent COMPLETED >=5% intra-episode dip, high -> reclaim, in sessions
            last_speed = np.nan
            peak_i, in_dip, open_dip = 0, False, False
            speeds = np.full(len(seg), np.nan)
            openf = np.zeros(len(seg), dtype=bool)
            for i in range(len(seg)):
                if seg[i] >= seg[peak_i]:
                    if in_dip:
                        last_speed = float(i - peak_i)
                        in_dip = False
                    peak_i = i
                    open_dip = False
                elif seg[i] <= 0.95 * seg[peak_i]:
                    in_dip = True
                    open_dip = True
                speeds[i] = last_speed
                openf[i] = open_dip
            reclaim.iloc[s:e + 1] = speeds
            unrec.iloc[s:e + 1] = openf
    f["F1_episode_age"] = age
    f["F2_drawdown_in_episode"] = epmax
    f["F5_reclaim_speed"] = reclaim
    f[F5_UNRECLAIMED_COL] = unrec
    return f[[*FEATURES, F5_UNRECLAIMED_COL]]


def feature_library(
    ohlcv_by_ticker: Mapping[str, pd.DataFrame],
    universe_median_index: pd.Series | None,
    asof_days: Mapping[str, Sequence] | pd.DataFrame,
    *,
    episodes: pd.DataFrame | None = None,
    cross_sectional_returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """§4.6 — the 36 frozen features at exactly the requested (segment, day) points.

    ``ohlcv_by_ticker`` maps IDENTITY SEGMENT -> that segment's own bar frame
    (columns among open/high/low/close/volume). ``universe_median_index`` is the
    track's PIT equal-weight median index (see `equal_weight_median_index`);
    ``cross_sectional_returns`` carries the same-day universe medians of r21/r63
    used by E1f/E2f (from `cross_sectional_median_returns`); ``asof_days`` is
    either a mapping segment -> dates or a frame with
    ``segment``/``date`` columns. ``episodes`` supplies the F-family's episode
    context; without it F1/F2/F5 are null rather than wrong.

    STRICTLY POINT-IN-TIME: every value at d is a function of bars at or before d
    inside d's own identity segment. Nothing after d — and nothing from a
    neighbouring segment of the same ticker — can touch it. Coverage nulls are
    preserved (a rung with no volume yields a null D-family, counted, never
    imputed).

    Returns one row per requested (segment, day): ``segment``, ``ticker``,
    ``date``, the 36 feature columns in prereg order, plus the auxiliary
    ``F5x_dip_unreclaimed`` flag.
    """
    if isinstance(asof_days, pd.DataFrame):
        want = {str(seg): pd.DatetimeIndex(sorted(set(g["date"])))
                for seg, g in asof_days.groupby("segment", sort=False)}
    else:
        want = {str(k): pd.DatetimeIndex(sorted(set(pd.to_datetime(list(vv)))))
                for k, vv in asof_days.items()}
    eps_by_seg = (dict(tuple(episodes.groupby("segment", sort=False)))
                  if episodes is not None and not episodes.empty else {})
    frames = []
    for seg, days in want.items():
        bars = ohlcv_by_ticker.get(seg)
        if bars is None or len(bars) == 0 or len(days) == 0:
            continue
        f = _feature_frame(bars.sort_index(), universe_median_index,
                           cross_sectional_returns, eps_by_seg.get(seg))
        sel = f.reindex(days)
        sel.insert(0, "date", sel.index)
        sel.insert(0, "ticker", segment_ticker(seg))
        sel.insert(0, "segment", seg)
        frames.append(sel.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=["segment", "ticker", "date", *FEATURES,
                                     F5_UNRECLAIMED_COL])
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# §4.5 matched controls and the matched-set estimator
# ══════════════════════════════════════════════════════════════════════════════
def _bucket(frame: pd.DataFrame, col: str, q: int, out: str) -> pd.Series:
    """Within-quarter quantile bucket; a degenerate quarter collapses to one bin."""
    def cut(s: pd.Series) -> pd.Series:
        ans = pd.Series(np.nan, index=s.index, dtype=float)
        finite = pd.to_numeric(s, errors="coerce").dropna()
        if finite.empty:
            return ans
        if finite.nunique() == 1:
            ans.loc[finite.index] = 0.0
            return ans
        try:
            # Cut the values themselves. Ranking with method="first" would split
            # identical observations across bins based only on row/arm order, so a
            # case and an economically identical control could become unmatchable.
            ans.loc[finite.index] = pd.qcut(
                finite, q, labels=False, duplicates="drop").astype(float)
            return ans
        except ValueError:
            ans.loc[finite.index] = 0.0
            return ans
    return frame.groupby("quarter", sort=False)[col].transform(cut).rename(out)


def matched_controls(
    cases: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    *,
    max_controls: int = MAX_CONTROLS,
    n_r126_bins: int = 5,
    n_rv63_bins: int = 3,
    n_dvol_bins: int = 3,
) -> tuple[pd.DataFrame, dict]:
    """§4.5 matched-control assembly — the contrast that matches extension away.

    Both frames need ``case_id``/``segment``/``ticker``/``date``/``r126``/``rv63``/
    ``dvol21``. Buckets (r126 quintile, rv63 tercile, 21d-dollar-volume tercile)
    are cut WITHIN CALENDAR QUARTER over the union of the two arms, so a case and
    its controls are always compared on one set of edges. Inside a bucket the up-to
    -four nearest neighbours are taken by |Δr126| then |Δrv63|, without replacement
    within a case, never from the case's own base ticker. Cases with zero eligible
    controls are DROPPED AND COUNTED — a matched design that silently keeps
    unmatched cases is not a matched design.

    Returns ``(pairs, diag)``: one row per (case, control) pair, and the counts
    that have to appear in the report (cases in, matched, dropped, controls/case).
    """
    need = {"case_id", "segment", "ticker", "date", "r126", "rv63", "dvol21"}
    for nm, fr in (("cases", cases), ("candidate_pool", candidate_pool)):
        missing = need - set(fr.columns)
        if missing:
            raise ValueError(f"{nm} is missing columns: {sorted(missing)}")
    if cases.empty or candidate_pool.empty:
        return (pd.DataFrame(columns=["case_id", "segment", "ticker", "date",
                                      "control_segment", "control_ticker", "control_date"]),
                {"n_cases": int(len(cases)), "n_matched": 0,
                 "n_dropped_no_control": int(len(cases)), "n_pairs": 0})

    ca = cases.copy()
    co = candidate_pool.copy()
    ca["_arm"], co["_arm"] = "case", "control"
    both = pd.concat([ca, co], ignore_index=True)
    both["quarter"] = pd.PeriodIndex(pd.to_datetime(both["date"]), freq="Q").astype(str)
    both["b_r126"] = _bucket(both, "r126", n_r126_bins, "b_r126")
    both["b_rv63"] = _bucket(both, "rv63", n_rv63_bins, "b_rv63")
    both["b_dvol"] = _bucket(both, "dvol21", n_dvol_bins, "b_dvol")
    key = ["quarter", "b_r126", "b_rv63", "b_dvol"]
    ca = both[both["_arm"] == "case"]
    co = both[both["_arm"] == "control"]
    pools = {k: g for k, g in co.groupby(key, sort=False)}

    rows, dropped = [], []
    for _, case in ca.iterrows():
        pool = pools.get(tuple(case[k] for k in key))
        if pool is None or pool.empty:
            dropped.append(case["case_id"])
            continue
        pool = pool[pool["ticker"] != case["ticker"]]
        if pool.empty:
            dropped.append(case["case_id"])
            continue
        d1 = (pool["r126"] - case["r126"]).abs().to_numpy(dtype=float)
        d2 = (pool["rv63"] - case["rv63"]).abs().to_numpy(dtype=float)
        order = np.lexsort((d2, d1))[:max_controls]
        for j in order:
            ctrl = pool.iloc[int(j)]
            rows.append({
                "case_id": case["case_id"], "segment": case["segment"],
                "ticker": case["ticker"], "date": case["date"],
                "control_segment": ctrl["segment"], "control_ticker": ctrl["ticker"],
                "control_date": ctrl["date"],
                "d_r126": float(ctrl["r126"] - case["r126"]),
                "d_rv63": float(ctrl["rv63"] - case["rv63"]),
                "quarter": case["quarter"], "b_r126": case["b_r126"],
                "b_rv63": case["b_rv63"], "b_dvol": case["b_dvol"],
            })
    pairs = pd.DataFrame(rows)
    n_matched = int(pairs["case_id"].nunique()) if not pairs.empty else 0
    diag = {
        "n_cases": int(len(ca)), "n_matched": n_matched,
        "n_dropped_no_control": int(len(dropped)),
        "dropped_case_ids": [str(x) for x in dropped[:50]],
        "n_pairs": int(len(pairs)),
        "controls_per_case_mean": (float(len(pairs) / n_matched) if n_matched else 0.0),
    }
    return pairs, diag


def matched_deltas(
    pairs: pd.DataFrame,
    feature_panel: pd.DataFrame,
    feature_cols: Sequence[str] = FEATURES,
    *,
    min_finite_controls: int = MIN_FINITE_CONTROLS,
) -> pd.DataFrame:
    """Per-CASE matched-set Δ = case value − mean of its FINITE controls (§4.5).

    §4.5 defines the Δ "only when the case and at least two controls are finite for
    that feature", so a matched set that survives on a single control is a null, not
    a thin estimate: one control is a comparison, not a matched set, and averaging
    it would smuggle a coverage hole in as a measurement. ``feature_panel`` is a
    `feature_library` output keyed by (segment, date).

    One row per matched case. Episode-first aggregation happens in `episode_deltas`
    — this frame is the snapshot-level input to it, never the headline.
    """
    if pairs.empty:
        return pd.DataFrame(columns=["case_id", "ticker", "date", *feature_cols])
    fp = feature_panel.copy()
    fp["date"] = pd.to_datetime(fp["date"])
    fp = fp.set_index(["segment", "date"])
    fp = fp[~fp.index.duplicated(keep="first")]
    cols = [c for c in feature_cols if c in fp.columns]
    p = pairs.copy()
    p["date"] = pd.to_datetime(p["date"])
    p["control_date"] = pd.to_datetime(p["control_date"])

    case_key = pd.MultiIndex.from_arrays([p["segment"], p["date"]])
    ctrl_key = pd.MultiIndex.from_arrays([p["control_segment"], p["control_date"]])
    cv = fp[cols].reindex(case_key).to_numpy(dtype=float)
    kv = fp[cols].reindex(ctrl_key).to_numpy(dtype=float)
    ctrl = pd.DataFrame(kv, columns=cols)
    ctrl["case_id"] = p["case_id"].to_numpy()
    grp = ctrl.groupby("case_id", sort=False)[cols]
    ctrl_mean, ctrl_n = grp.mean(), grp.count()

    case_vals = pd.DataFrame(cv, columns=cols)
    case_vals["case_id"] = p["case_id"].to_numpy()
    case_vals["ticker"] = p["ticker"].to_numpy()
    case_vals["date"] = p["date"].to_numpy()
    first = case_vals.groupby("case_id", sort=False).first()
    out = first[cols] - ctrl_mean.reindex(first.index)
    out = out.where(ctrl_n.reindex(first.index) >= min_finite_controls)
    out.insert(0, "date", first["date"])
    out.insert(0, "ticker", first["ticker"])
    return out.reset_index()


def episode_deltas(
    case_deltas: pd.DataFrame,
    cases: pd.DataFrame,
    episodes: pd.DataFrame | None = None,
    feature_cols: Sequence[str] = FEATURES,
) -> pd.DataFrame:
    """§4.5 EPISODE-FIRST aggregation — the headline unit is the episode, not the snapshot.

    Each TOPPED episode contributes up to three snapshots (`days_to_peak ∈ {21,10,5}`),
    and those three are three looks at ONE event. Pooling them as independent cases
    would inflate N roughly threefold and let a single well-covered episode outvote
    three thin ones. So the episode's snapshots collapse to their MEDIAN Δ first
    (§4.5's literal word), and every downstream statistic — median, CI, N — is taken
    across DISTINCT EPISODES.

    ``cases`` supplies `case_id` → `episode_id`/`ticker`; ``episodes`` supplies each
    episode's `peak_date`, which becomes the month-block key (§4.5: the primary CI
    resamples episode-peak calendar-month blocks). Returns one row per episode with
    `episode_id`, `ticker`, `peak_date`, `n_snapshots`, and the feature Δs.
    """
    cols = [c for c in feature_cols if c in case_deltas.columns]
    empty = pd.DataFrame(columns=["episode_id", "ticker", "peak_date", "date",
                                  "n_snapshots", *cols])
    if case_deltas.empty or cases.empty or "episode_id" not in cases.columns:
        return empty
    link = cases[["case_id", "episode_id"]].drop_duplicates("case_id")
    d = case_deltas.merge(link, on="case_id", how="inner")
    if d.empty:
        return empty
    agg = d.groupby("episode_id", sort=False)[cols].median()
    meta = d.groupby("episode_id", sort=False).agg(ticker=("ticker", "first"),
                                                   n_snapshots=("case_id", "nunique"),
                                                   date=("date", "min"))
    out = meta.join(agg).reset_index()
    if episodes is not None and not episodes.empty and "peak_date" in episodes.columns:
        pk = episodes[["episode_id", "peak_date"]].drop_duplicates("episode_id")
        out = out.merge(pk, on="episode_id", how="left")
    else:
        out["peak_date"] = out["date"]
    return out[["episode_id", "ticker", "peak_date", "date", "n_snapshots", *cols]]


def _median_ci(
    values: np.ndarray,
    blocks: np.ndarray,
    *,
    b: int,
    rng: np.random.Generator,
    min_n: int = 5,
) -> tuple[float, float, float, int]:
    """95% percentile bootstrap of a MEDIAN, resampling whole BLOCKS with replacement.

    The resampling unit is the block (a calendar month of case dates, or a base
    ticker), never the case: extended-move tops arrive in market-wide bunches, so a
    per-case interval overstates precision by roughly the cluster size. Returns
    ``(lo, hi, two-sided p, n)``; the p-value is
    ``2·min(P(median <= 0), P(median >= 0))`` floored at ``1/(B+1)``.
    """
    ok = np.isfinite(values)
    values = values[ok]
    blocks = np.asarray(blocks)[ok]
    if values.size < min_n:
        return (float("nan"), float("nan"), float("nan"), int(values.size))
    keys, inv = np.unique(blocks, return_inverse=True)
    by_block = [values[inv == i] for i in range(len(keys))]
    k = len(by_block)
    draws = np.empty(b, dtype=float)
    picks = rng.integers(0, k, size=(b, k))
    for i in range(b):
        draws[i] = np.median(np.concatenate([by_block[j] for j in picks[i]]))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    p = 2.0 * min(float((draws <= 0).mean()), float((draws >= 0).mean()))
    return (float(lo), float(hi), float(max(min(p, 1.0), 1.0 / (b + 1.0))),
            int(values.size))


def matched_delta_stats(
    deltas: pd.DataFrame,
    feature_cols: Sequence[str] = FEATURES,
    *,
    b: int = BOOTSTRAP_B,
    seed: int = 20260810,
    q_threshold: float = FDR_Q,
    directions: Mapping[str, int] | None = None,
    coverage_floor: float = 0.60,
    min_blocks: int = MIN_EPISODE_MONTHS,
) -> pd.DataFrame:
    """§4.5 estimator: median Δ across EPISODES, episode-peak-month CI, BH-FDR.

    Feed this `episode_deltas` output — the unit is the distinct episode. The 95%
    interval resamples **episode-peak CALENDAR-MONTH blocks** (B=2000), because
    extended-move tops arrive in market-wide bunches and a per-episode interval
    would overstate precision by roughly the cluster size. The ticker-cluster
    interval is the report-only robustness arm. All 36 tests are two-sided; the
    block-bootstrap sign-tail p-values feed BH-FDR WITHIN FAMILY (six families).

    A registered separation (§4.5) needs ALL of: ≥``min_blocks`` distinct
    episode-peak months, the 95% block CI excluding 0, BH q ≤ 0.10, coverage at or
    above the floor, and — where a direction was declared — the observed sign
    matching it. A direction-0 field can only ever be ``EXPLORATORY-DISCOVERY``: it
    may be flagged as a discovery-only separator in either direction but can never
    reach DETECTION grade or carry authority without a fresh confirmatory prereg.

    Deterministic in ``seed``. Every row carries its own honest N.
    """
    dirs = dict(FEATURE_DIRECTION if directions is None else directions)
    if deltas.empty:
        return pd.DataFrame(columns=["feature", "family", "direction", "n_episodes",
                                     "n_blocks", "coverage", "median_delta", "ci_lo",
                                     "ci_hi", "p_value", "q_value", "separates", "grade"])
    d = deltas.copy()
    d["date"] = pd.to_datetime(d["date"]) if "date" in d.columns else pd.NaT
    # §4.5: blocks are EPISODE-PEAK months. Falling back to the snapshot date keeps a
    # caller that hands over raw case-level deltas honest rather than silently wrong.
    block_src = "peak_date" if "peak_date" in d.columns and d["peak_date"].notna().any() \
        else "date"
    month = pd.to_datetime(d[block_src]).dt.to_period("M").astype(str).to_numpy()
    tick = d["ticker"].astype(str).to_numpy()
    rows = []
    n_all = len(d)
    for k_feat, feat in enumerate(feature_cols):
        if feat not in d.columns:
            continue
        vals = pd.to_numeric(d[feat], errors="coerce").to_numpy(dtype=float)
        cov = float(np.isfinite(vals).mean()) if n_all else 0.0
        # seeds are derived from the feature's ORDINAL, never from hash() — string
        # hashing is per-process randomized and would make a run irreproducible.
        rng = np.random.default_rng(seed + 1000 * k_feat)
        lo, hi, p, n = _median_ci(vals, month, b=b, rng=rng)
        rng2 = np.random.default_rng(seed + 1000 * k_feat + 500_000)
        tlo, thi, tp, _ = _median_ci(vals, tick, b=b, rng=rng2)
        med = float(np.nanmedian(vals)) if np.isfinite(vals).any() else float("nan")
        n_blocks = int(len(np.unique(month[np.isfinite(vals)])))
        rows.append({
            "feature": feat, "family": FEATURE_FAMILY.get(feat, feat[0]),
            "direction": int(dirs.get(feat, 0)), "n_episodes": n, "n_blocks": n_blocks,
            "coverage": cov, "median_delta": med, "ci_lo": lo, "ci_hi": hi,
            "p_value": p, "ticker_ci_lo": tlo, "ticker_ci_hi": thi,
            "ticker_p_value": tp, "interpretable": bool(cov >= coverage_floor),
            "block_key": block_src,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q_value"] = np.nan
    for fam, g in out.groupby("family", sort=False):
        out.loc[g.index, "q_value"] = bh_fdr(g["p_value"].to_numpy(dtype=float))
    ci_excludes_zero = (out["ci_lo"] > 0) | (out["ci_hi"] < 0)
    sign_ok = np.where(out["direction"] > 0, out["median_delta"] > 0,
                       np.where(out["direction"] < 0, out["median_delta"] < 0, True))
    out["separates"] = (ci_excludes_zero
                        & pd.Series(sign_ok, index=out.index)
                        & (out["q_value"] <= q_threshold)
                        & out["interpretable"]
                        & (out["n_blocks"] >= min_blocks)).astype(bool)
    out["grade"] = np.where(~out["separates"], "",
                            np.where(out["direction"] != 0, "REGISTERED",
                                     "EXPLORATORY-DISCOVERY"))
    out["ticker_ci_agrees"] = np.where(
        out["median_delta"] > 0, out["ticker_ci_lo"] > 0, out["ticker_ci_hi"] < 0)
    return out.sort_values(["family", "feature"], ignore_index=True)


def direction_tail(direction: int, observed_median: float = float("nan")) -> float:
    """The direction-aligned control-tail quantile (§2, §4.8).

    P90 when a higher value is the risk side, P10 when a lower value is. A direction
    -0 (exploratory) field has no declared risk side, so the OBSERVED sign of its
    matched Δ picks the tail — printed, and discovery-only either way.
    """
    if direction > 0:
        return 0.90
    if direction < 0:
        return 0.10
    return 0.10 if (np.isfinite(observed_median) and observed_median < 0) else 0.90


# ══════════════════════════════════════════════════════════════════════════════
# §2 the top ruler — is a fire a GOOD warning, not just an eventually-right one?
# ══════════════════════════════════════════════════════════════════════════════
def top_ruler(
    fires: pd.DataFrame,
    episodes: pd.DataFrame,
    close_df: pd.DataFrame,
    *,
    ext_mask: pd.DataFrame | None = None,
    fwd_horizon: int = 63,
    peak_proximity: float = 0.05,
    time_proximity: int = 10,
    b: int = BOOTSTRAP_B,
    seed: int = 20260810,
) -> dict:
    """§2 wrong-ruler check: measure a fire set as a WARNING, not as a return.

    The bottom-side PSS §7 lesson, mirrored: an eventually-right warning with a
    large remaining run to the peak is a bad warning. For a boolean ``fires``
    frame (aligned like ``ext_mask``) inside episodes carrying peaks
    (`episode_peaks` output), this reports median REMAINING UPSIDE to the episode
    peak, the share of fires within ``peak_proximity`` of the peak PRICE, the share
    within +/-``time_proximity`` sessions of the peak, and forward-``fwd_horizon``
    return against the all-EXT-days null.

    Every metric is computed PER BASE TICKER first and then pooled by median, so a
    single heavily-fired name cannot carry the number. Shares use the within-name
    mean of their boolean indicator (not its median) before the across-name median.
    The reported intervals resample episode-peak calendar-month blocks, preserving
    the prereg's per-name-first ruler. Report metrics only — no test, no rank, no
    authority.
    """
    def _measure(mask: pd.DataFrame) -> pd.DataFrame:
        recs = []
        eps = episodes[episodes["segment"].isin(mask.columns)] if not episodes.empty else episodes
        by_seg = dict(tuple(eps.groupby("segment", sort=False))) if not eps.empty else {}
        for col in mask.columns:
            m = mask[col].fillna(False).to_numpy(dtype=bool)
            if not m.any():
                continue
            c = _bars(close_df, col)
            if c is None:
                continue
            pos = pd.Series(np.arange(len(c)), index=c.index)
            v = c.to_numpy(dtype=float)
            hits = [d for d in mask.index[m] if d in pos.index]
            for ep in by_seg.get(col, pd.DataFrame()).to_dict("records"):
                pk_d, pk_c = ep.get("peak_date"), ep.get("peak_close")
                if pk_d is None or pd.isna(pk_c) or pk_d not in pos.index:
                    continue
                pk = int(pos[pk_d])
                for d in hits:
                    if not (ep["start"] <= d <= ep["end"]):
                        continue
                    i = int(pos[d])
                    fwd = (v[i + fwd_horizon] / v[i] - 1.0
                           if i + fwd_horizon < len(v) else np.nan)
                    recs.append({
                        "ticker": segment_ticker(col), "segment": col, "date": d,
                        "episode_id": ep["episode_id"],
                        "peak_month": str(pd.Timestamp(pk_d).to_period("M")),
                        "remaining_upside": float(pk_c) / v[i] - 1.0,
                        "near_peak_price": bool(v[i] >= (1.0 - peak_proximity) * float(pk_c)),
                        "near_peak_time": bool(abs(pk - i) <= time_proximity),
                        "fwd_ret": fwd,
                    })
        return pd.DataFrame(recs)

    def _pooled(fr: pd.DataFrame, col: str, *, share: bool = False) -> float:
        if fr.empty or col not in fr.columns:
            return float("nan")
        per = (fr.groupby("ticker")[col].mean() if share
               else fr.groupby("ticker")[col].median())
        return float(per.median()) if len(per) else float("nan")

    def _month_bootstrap(hit_fr: pd.DataFrame, null_fr: pd.DataFrame) -> dict:
        """Paired episode-peak-month bootstrap of the four frozen ruler metrics."""
        if b <= 0 or hit_fr.empty:
            return {}
        months = sorted(set(hit_fr.get("peak_month", ())) | set(null_fr.get("peak_month", ())))
        if not months:
            return {}
        hit_by = {m: hit_fr[hit_fr["peak_month"] == m] for m in months}
        null_by = ({m: null_fr[null_fr["peak_month"] == m] for m in months}
                   if "peak_month" in null_fr else {m: pd.DataFrame() for m in months})
        rng = np.random.default_rng(seed)
        draws = {k: [] for k in (
            "median_remaining_upside", "share_within_peak_price",
            "share_within_peak_time", f"fwd_{fwd_horizon}_excess")}
        for _ in range(int(b)):
            pick = rng.choice(months, size=len(months), replace=True)
            hs = pd.concat([hit_by[m] for m in pick], ignore_index=True)
            ns = pd.concat([null_by[m] for m in pick], ignore_index=True) \
                if not null_fr.empty else pd.DataFrame()
            draws["median_remaining_upside"].append(_pooled(hs, "remaining_upside"))
            draws["share_within_peak_price"].append(_pooled(hs, "near_peak_price", share=True))
            draws["share_within_peak_time"].append(_pooled(hs, "near_peak_time", share=True))
            fh, fn = _pooled(hs, "fwd_ret"), _pooled(ns, "fwd_ret")
            draws[f"fwd_{fwd_horizon}_excess"].append(
                fh - fn if np.isfinite(fh) and np.isfinite(fn) else np.nan)
        out = {}
        for key, vals in draws.items():
            a = np.asarray(vals, dtype=float)
            a = a[np.isfinite(a)]
            out[f"{key}_ci"] = ([float(x) for x in np.percentile(a, [2.5, 97.5])]
                                  if len(a) else [None, None])
        return out

    hit = _measure(fires)
    null = _measure(ext_mask) if ext_mask is not None else pd.DataFrame()
    fwd_hit, fwd_null = _pooled(hit, "fwd_ret"), _pooled(null, "fwd_ret")
    result = {
        "n_fires": int(len(hit)),
        "n_fire_episodes": int(hit["episode_id"].nunique()) if not hit.empty else 0,
        "n_fire_names": int(hit["ticker"].nunique()) if not hit.empty else 0,
        "median_remaining_upside": _pooled(hit, "remaining_upside"),
        "share_within_peak_price": _pooled(hit, "near_peak_price", share=True),
        "share_within_peak_time": _pooled(hit, "near_peak_time", share=True),
        f"fwd_{fwd_horizon}_fires": fwd_hit,
        f"fwd_{fwd_horizon}_all_ext_null": fwd_null,
        f"fwd_{fwd_horizon}_excess": (fwd_hit - fwd_null
                                      if np.isfinite(fwd_hit) and np.isfinite(fwd_null)
                                      else float("nan")),
        "n_null_days": int(len(null)),
        "null_median_remaining_upside": _pooled(null, "remaining_upside"),
        "bootstrap_unit": "episode_peak_month",
        "bootstrap_b": int(b),
    }
    result.update(_month_bootstrap(hit, null))
    return result
