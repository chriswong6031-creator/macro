"""engine/nasdaq_internals.py — Nasdaq-100 archetype-group internals.

Descriptive rotation-state artifact over the 7 tech-archetype groups defined in
data/baskets_nasdaq/membership.json (archetype_groups partition). Pure deterministic
computation; no LLM involvement; display-only.

DISPLAY-ONLY. No field names or strings imply a forecast. States are descriptive
(leading / improving / weakening / lagging) following the RRG quadrant convention
applied to (rs_60d sign, accel sign). Rulings: TI-R1..R7 (adjudication PR #1805).

COMPUTATION DEFINITIONS (all documented per TI-R3):

  Group composite:
    Equal-weight of distinct member daily log-returns. Each member's daily return is
    computed from its close price series (loaded via basket_index._load_member_ohlcv).
    Deduplication is applied to the member list before any arithmetic.

  rs_20d / rs_60d:
    Group composite total-return (geometric) over the last 20 or 60 trading days,
    minus the QQQ total-return over the same window. Expressed in percentage points.
    Requires >=21 (rs_20d) or >=61 (rs_60d) bars in BOTH the group series and QQQ.

  accel:
    rs_20d minus the rs over the *prior* 20d window (bars -41..-21 relative to today).
    Measures pace-of-RS-change. Requires >=41 bars for each constituent plus QQQ.

  breadth_above_50dma:
    Fraction of group members (with >=51 bars of price data) whose latest close is
    above their 50-day simple moving average. Range [0, 1]; null if no member has
    enough history.

  dispersion_20d:
    Cross-member standard deviation of 20d total returns (same window as rs_20d).
    Null if fewer than 2 members have >=21 bars.

  state (RRG-style):
    (sign of rs_60d, sign of accel):
      (+, +) → leading
      (-, +) → improving
      (+, -) → weakening
      (-, -) → lagging
    Null when rs_60d or accel is null.

  2-day hysteresis:
    State flips only after the candidate state holds for 2 consecutive runs.
    Prior state is read from the existing site/marketdata/nasdaq_internals.json
    (field groups[].state and groups[].state_days). On day 1 of a new candidate
    the prior state is preserved and state_days increments by 0 (stays at prior
    count). On day 2+ (candidate matches the candidate from the prior run, stored
    as state_candidate) the state commits. state_days counts how many consecutive
    runs the current published state has been active.

  ew_vs_qqq:
    Equal-weight composite of ALL distinct tickers across all 7 groups (union), vs
    QQQ. spread_20d / spread_60d are the corresponding RS values in pp.
    pctile_1y: percentile rank of today's spread_20d vs its trailing-252-bar daily
    distribution computed from the composite level series (null if <252 bars of
    composite history are computable).

  gap_accel_z (divergences):
    For a pair (A, B): (accel_A - accel_B) z-scored against the trailing 252-bar
    distribution of the same gap. Null with reason when accel values are unavailable
    or history is shorter than 62 bars (need 20+20+20+1 for prior window + enough
    for any distribution).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import basket_index
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BENCHMARK = "QQQ"
_OUT_PATH_REL = "site/marketdata/nasdaq_internals.json"
_MEMBERSHIP_REL = "data/baskets_nasdaq/membership.json"

# Minimum bars needed for each metric
_MIN_RS20 = 21
_MIN_RS60 = 61
_MIN_ACCEL = 41   # 20 (current window) + 21 (prior window base)
_MIN_50DMA = 51

# Divergence pairs as (group_id_A, group_id_B)
_DIVERGENCE_PAIRS: list[tuple[str, str]] = [
    ("ai_compute_supply", "edge_device"),
    ("ai_compute_supply", "megacap_quality"),
    ("software_enterprise", "cyber"),
]

# Minimum bars for pctile_1y and gap_accel_z distribution
_PCTILE_MIN_BARS = 62   # must have enough history for 1 full prior window + distribution

# ---------------------------------------------------------------------------
# Banned substring guard (TI-R1) — enforced at test time; documented here
# ---------------------------------------------------------------------------
# Field names and user-facing strings MUST NOT contain:
#   shelter, beneficiary, casualty, front_run, predict, will_, validated


# ---------------------------------------------------------------------------
# Price loading helpers (reuses basket_index._load_member_ohlcv — same source)
# ---------------------------------------------------------------------------

def _load_close(ticker: str) -> pd.Series | None:
    """Load close price series for a ticker via the basket-index OHLCV store.

    Returns a sorted DatetimeIndex Series (name=ticker) or None if unavailable.
    """
    df = basket_index._load_member_ohlcv(ticker)
    if df is None or "close" not in df.columns:
        return None
    s = df["close"].dropna()
    if len(s) == 0:
        return None
    s.name = ticker
    return s


def _equal_weight_composite(tickers: list[str]) -> pd.Series | None:
    """Compute an equal-weight composite daily-return series from distinct tickers.

    Each member contributes 1/N weight. The composite is a level series starting at
    1.0 on the first date ALL members have data (or the first date any member has
    data, with available-member averaging on early dates).

    Returns a Series indexed by date, or None if no ticker has price data.
    """
    unique_tickers = list(dict.fromkeys(tickers))  # preserve order, dedupe
    closes: dict[str, pd.Series] = {}
    for t in unique_tickers:
        s = _load_close(t)
        if s is not None:
            closes[t] = s

    if not closes:
        return None

    # Align all series on a common date index (union)
    df = pd.DataFrame(closes)
    df = df.sort_index()

    # Daily returns per member (fill with NaN so absent members don't contribute)
    rets = df.pct_change(fill_method=None)

    # Equal-weight average of available members each day (at least 1 member needed)
    composite_rets = rets.mean(axis=1, skipna=True)  # skips NaN columns each row

    # Convert to level series starting at 1.0
    level = (1 + composite_rets).cumprod()
    level.iloc[0] = 1.0  # anchor first bar
    return level.dropna()


# ---------------------------------------------------------------------------
# Return computation helpers
# ---------------------------------------------------------------------------

def _total_return_20d(level: pd.Series) -> float | None:
    """20-trading-day total return from a level series (percentage points)."""
    if level is None or len(level) < _MIN_RS20:
        return None
    base, last = level.iloc[-_MIN_RS20], level.iloc[-1]
    if pd.isna(base) or pd.isna(last) or base == 0:
        return None
    return float(last / base - 1.0) * 100.0


def _total_return_60d(level: pd.Series) -> float | None:
    """60-trading-day total return from a level series (percentage points)."""
    if level is None or len(level) < _MIN_RS60:
        return None
    base, last = level.iloc[-_MIN_RS60], level.iloc[-1]
    if pd.isna(base) or pd.isna(last) or base == 0:
        return None
    return float(last / base - 1.0) * 100.0


def _total_return_prior_20d(level: pd.Series) -> float | None:
    """Total return over the PRIOR 20d window (bars -41..-21) for accel computation."""
    if level is None or len(level) < _MIN_ACCEL:
        return None
    # Prior window: from bar [-41] to bar [-21] (both inclusive at ends)
    base = level.iloc[-_MIN_ACCEL]     # index -41
    end  = level.iloc[-_MIN_RS20]      # index -21 (= start of current 20d window)
    if pd.isna(base) or pd.isna(end) or base == 0:
        return None
    return float(end / base - 1.0) * 100.0


def _rs(group_level: pd.Series | None, bench_level: pd.Series | None,
        window: int) -> float | None:
    """RS = group total return over window minus bench total return over window (pp).

    Both series must have >= window+1 bars. Series are aligned by trimming to the
    intersection of their date indices before slicing the tail.
    """
    if group_level is None or bench_level is None:
        return None
    # Align on shared dates
    shared = group_level.index.intersection(bench_level.index)
    if len(shared) < window + 1:
        return None
    g = group_level.loc[shared].iloc[-(window + 1):]
    b = bench_level.loc[shared].iloc[-(window + 1):]
    if len(g) < window + 1 or len(b) < window + 1:
        return None
    g_base, g_last = g.iloc[0], g.iloc[-1]
    b_base, b_last = b.iloc[0], b.iloc[-1]
    if any(pd.isna(x) or x == 0 for x in [g_base, g_last, b_base, b_last]):
        return None
    g_ret = float(g_last / g_base - 1.0) * 100.0
    b_ret = float(b_last / b_base - 1.0) * 100.0
    return round(g_ret - b_ret, 4)


def _accel(group_level: pd.Series | None, bench_level: pd.Series | None) -> float | None:
    """Accel = rs_20d (current) minus rs over the prior 20d window.

    Prior window = bars [-41..-21] relative to today (on shared index).
    """
    if group_level is None or bench_level is None:
        return None
    shared = group_level.index.intersection(bench_level.index)
    if len(shared) < _MIN_ACCEL + 1:
        return None
    g = group_level.loc[shared]
    b = bench_level.loc[shared]

    # Current 20d RS
    g_cur = g.iloc[-(20 + 1):]
    b_cur = b.iloc[-(20 + 1):]
    g_ret_cur = float(g_cur.iloc[-1] / g_cur.iloc[0] - 1.0) * 100.0 if g_cur.iloc[0] != 0 else None
    b_ret_cur = float(b_cur.iloc[-1] / b_cur.iloc[0] - 1.0) * 100.0 if b_cur.iloc[0] != 0 else None
    if g_ret_cur is None or b_ret_cur is None:
        return None
    rs_cur = g_ret_cur - b_ret_cur

    # Prior 20d RS (window -41 to -21)
    g_pri = g.iloc[-(40 + 1):-(20)]    # bars -41 to -21 inclusive (21 bars)
    b_pri = b.iloc[-(40 + 1):-(20)]
    if len(g_pri) < 2 or len(b_pri) < 2:
        return None
    if g_pri.iloc[0] == 0 or b_pri.iloc[0] == 0:
        return None
    g_ret_pri = float(g_pri.iloc[-1] / g_pri.iloc[0] - 1.0) * 100.0
    b_ret_pri = float(b_pri.iloc[-1] / b_pri.iloc[0] - 1.0) * 100.0
    rs_pri = g_ret_pri - b_ret_pri

    return round(rs_cur - rs_pri, 4)


# ---------------------------------------------------------------------------
# State machine helpers (RRG-style with hysteresis)
# ---------------------------------------------------------------------------

_STATE_MAP: dict[tuple[bool, bool], str] = {
    (True,  True):  "leading",
    (False, True):  "improving",
    (True,  False): "weakening",
    (False, False): "lagging",
}


def _raw_state(rs_60d: float | None, accel: float | None) -> str | None:
    """Candidate state from (sign of rs_60d, sign of accel). Null if either is null."""
    if rs_60d is None or accel is None:
        return None
    return _STATE_MAP[(rs_60d >= 0, accel >= 0)]


def _apply_hysteresis(
    candidate: str | None,
    prior_state: str | None,
    prior_candidate: str | None,
    prior_state_days: int,
) -> tuple[str | None, str | None, int]:
    """Apply 2-day hysteresis to the candidate state.

    Returns (published_state, pending_candidate, new_state_days).

    Logic (mirrors engine/regime_vector.py _apply_hysteresis):
      - If candidate matches prior_state: no transition; state_days += 1.
      - If candidate matches prior_candidate (second consecutive day): commit.
      - Otherwise (first day of a new candidate): hold prior_state; store candidate.
    """
    if candidate is None:
        return (prior_state, prior_candidate, prior_state_days)

    if candidate == prior_state:
        # Stable — no transition needed
        return (candidate, candidate, prior_state_days + 1)

    if prior_candidate is not None and candidate == prior_candidate:
        # Second consecutive day with this candidate — commit
        return (candidate, candidate, 1)

    # First day of a new candidate — hold prior state, record pending candidate
    return (prior_state, candidate, prior_state_days)


# ---------------------------------------------------------------------------
# Breadth / dispersion helpers
# ---------------------------------------------------------------------------

def _breadth_above_50dma(tickers: list[str]) -> float | None:
    """Fraction of group members whose latest close >= 50d SMA.

    Only members with >=51 bars contribute. Returns null if no member qualifies.
    """
    unique = list(dict.fromkeys(tickers))
    above, total = 0, 0
    for t in unique:
        s = _load_close(t)
        if s is None or len(s) < _MIN_50DMA:
            continue
        sma50 = s.iloc[-_MIN_50DMA:].mean()
        if s.iloc[-1] >= sma50:
            above += 1
        total += 1
    if total == 0:
        return None
    return round(above / total, 4)


def _dispersion_20d(tickers: list[str]) -> float | None:
    """Cross-member std of 20d total returns (percentage points).

    Requires >=2 members with >=21 bars each.
    """
    unique = list(dict.fromkeys(tickers))
    rets_20d: list[float] = []
    for t in unique:
        s = _load_close(t)
        if s is None or len(s) < _MIN_RS20:
            continue
        base, last = s.iloc[-_MIN_RS20], s.iloc[-1]
        if pd.isna(base) or pd.isna(last) or base == 0:
            continue
        rets_20d.append(float(last / base - 1.0) * 100.0)
    if len(rets_20d) < 2:
        return None
    return round(float(np.std(rets_20d, ddof=1)), 4)


# ---------------------------------------------------------------------------
# pctile_1y helper for ew_vs_qqq
# ---------------------------------------------------------------------------

def _pctile_1y(current_val: float, level_series: pd.Series,
               bench_level: pd.Series, window: int = 20) -> float | None:
    """Percentile rank of today's RS spread vs its trailing 252-bar daily distribution.

    Requires level_series and bench_level to share enough history. Returns null if
    insufficient history (<= 252 + window bars on the shared index).
    """
    shared = level_series.index.intersection(bench_level.index)
    if len(shared) < _PCTILE_MIN_BARS + 252:
        return None
    g = level_series.loc[shared]
    b = bench_level.loc[shared]

    # Compute rolling 20d RS at each of the last 252 bars
    spreads: list[float] = []
    tail_len = 252 + window + 1
    if len(g) < tail_len:
        return None
    g_tail = g.iloc[-tail_len:]
    b_tail = b.iloc[-tail_len:]
    for i in range(window, len(g_tail)):
        g_sl = g_tail.iloc[i - window: i + 1]
        b_sl = b_tail.iloc[i - window: i + 1]
        if len(g_sl) < window + 1 or g_sl.iloc[0] == 0 or b_sl.iloc[0] == 0:
            continue
        g_r = float(g_sl.iloc[-1] / g_sl.iloc[0] - 1.0) * 100.0
        b_r = float(b_sl.iloc[-1] / b_sl.iloc[0] - 1.0) * 100.0
        spreads.append(g_r - b_r)

    if len(spreads) < 2:
        return None
    arr = np.array(spreads)
    pct = float(np.mean(arr <= current_val))
    return round(pct, 4)


# ---------------------------------------------------------------------------
# gap_accel_z helper for divergences
# ---------------------------------------------------------------------------

def _gap_accel_z(
    accel_a: float | None, accel_b: float | None,
    level_a: pd.Series | None, level_b: pd.Series | None,
    bench_level: pd.Series | None,
) -> tuple[float | None, str | None]:
    """Compute (accel_A - accel_B) z-scored against its trailing 252-bar distribution.

    Returns (z_score, reason_or_None). Returns (None, reason) when not computable.
    The distribution is built by computing the gap for each of the trailing 252 bars
    (on shared dates) using the same accel formula.
    """
    if accel_a is None or accel_b is None:
        return (None, "accel_unavailable")
    if level_a is None or level_b is None or bench_level is None:
        return (None, "price_unavailable")

    # We need a rolling accel series for both groups
    shared_a = level_a.index.intersection(bench_level.index)
    shared_b = level_b.index.intersection(bench_level.index)
    shared = shared_a.intersection(shared_b)

    # Need at least 252 + 41 bars to compute 252 history points of accel
    min_needed = 252 + 42
    if len(shared) < min_needed:
        return (None, f"insufficient_history_n={len(shared)}")

    ga = level_a.loc[shared]
    gb = level_b.loc[shared]
    bn = bench_level.loc[shared]

    def _accel_at(series_g: pd.Series, series_b: pd.Series, idx: int) -> float | None:
        """Compute accel at position idx (0-indexed from tail of sliced series)."""
        # We need 42 bars ending at idx
        if idx < 41:
            return None
        g_sl = series_g.iloc[idx - 41: idx + 1]  # 42 bars
        b_sl = series_b.iloc[idx - 41: idx + 1]
        if len(g_sl) < 42:
            return None
        # current 20d
        g_c = g_sl.iloc[-21:]
        b_c = b_sl.iloc[-21:]
        if g_c.iloc[0] == 0 or b_c.iloc[0] == 0:
            return None
        rs_c = (g_c.iloc[-1] / g_c.iloc[0] - 1.0) * 100.0 - (b_c.iloc[-1] / b_c.iloc[0] - 1.0) * 100.0
        # prior 20d
        g_p = g_sl.iloc[-42:-21] if len(g_sl) >= 42 else None
        b_p = b_sl.iloc[-42:-21] if len(b_sl) >= 42 else None
        if g_p is None or b_p is None or len(g_p) < 2 or len(b_p) < 2:
            return None
        if g_p.iloc[0] == 0 or b_p.iloc[0] == 0:
            return None
        rs_p = (g_p.iloc[-1] / g_p.iloc[0] - 1.0) * 100.0 - (b_p.iloc[-1] / b_p.iloc[0] - 1.0) * 100.0
        return rs_c - rs_p

    # Build historical gap series over the last 252 positions
    n = len(ga)
    gaps: list[float] = []
    for i in range(n - 252, n):
        aa = _accel_at(ga, bn, i)
        ab = _accel_at(gb, bn, i)
        if aa is not None and ab is not None:
            gaps.append(aa - ab)

    if len(gaps) < 10:
        return (None, f"insufficient_gap_history_n={len(gaps)}")

    arr = np.array(gaps)
    mu = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1))
    if sigma == 0:
        return (None, "zero_gap_std")

    current_gap = accel_a - accel_b
    z = round((current_gap - mu) / sigma, 4)
    return (z, None)


# ---------------------------------------------------------------------------
# Prior state reader (hysteresis seed)
# ---------------------------------------------------------------------------

def _load_prior(out_path: Path) -> dict[str, dict]:
    """Read prior nasdaq_internals.json to seed hysteresis.

    Returns a mapping of group_id -> {state, state_candidate, state_days}.
    Empty dict on any read failure (no crash).
    """
    if not out_path.exists():
        return {}
    try:
        data = json.loads(out_path.read_text())
        result: dict[str, dict] = {}
        for g in data.get("groups", []):
            gid = g.get("id")
            if gid:
                result[gid] = {
                    "state": g.get("state"),
                    "state_candidate": g.get("state_candidate"),
                    "state_days": g.get("state_days", 0),
                }
        return result
    except Exception as e:  # noqa: BLE001
        log.warning("nasdaq_internals: could not load prior artifact for hysteresis (%s)", e)
        return {}


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build(root: Path | None = None) -> dict[str, Any]:
    """Build the nasdaq_internals artifact.

    Returns the artifact dict. Writes nothing — caller writes to disk.

    On any price-loading failure: emits a valid all-null artifact with null_reasons.
    Never raises.
    """
    repo_root = root or config.data_dir().parent
    membership_path = repo_root / _MEMBERSHIP_REL
    out_path = repo_root / _OUT_PATH_REL

    asof = datetime.now(timezone.utc).isoformat()
    null_reasons: list[str] = []

    # --- Load membership ---
    if not membership_path.exists():
        null_reasons.append(f"membership_missing:{membership_path}")
        return _null_artifact(asof, null_reasons, membership_as_of=None)

    try:
        mem = json.loads(membership_path.read_text())
    except Exception as e:  # noqa: BLE001
        null_reasons.append(f"membership_parse_error:{e}")
        return _null_artifact(asof, null_reasons, membership_as_of=None)

    membership_as_of = mem.get("as_of", "unknown")
    ag = mem.get("archetype_groups", {})
    groups_spec = ag.get("groups", {})

    if not groups_spec:
        null_reasons.append("archetype_groups_missing_from_membership")
        return _null_artifact(asof, null_reasons, membership_as_of=membership_as_of)

    # --- Load benchmark ---
    bench_close = _load_close(_BENCHMARK)
    bench_level: pd.Series | None = None
    if bench_close is not None and len(bench_close) > 1:
        bench_level = (1 + bench_close.pct_change(fill_method=None)).cumprod()
        bench_level.iloc[0] = 1.0
        bench_level = bench_level.dropna()
    else:
        null_reasons.append(f"benchmark_{_BENCHMARK}_unavailable")

    # --- Prior state for hysteresis ---
    prior = _load_prior(out_path)

    # --- Build per-group metrics ---
    group_levels: dict[str, pd.Series | None] = {}
    group_results: list[dict] = []

    # Union of all tickers for ew_vs_qqq
    all_tickers_union: list[str] = []

    for gid, gspec in groups_spec.items():
        members: list[str] = gspec.get("members", [])
        unique_members = list(dict.fromkeys(members))  # dedupe preserving order

        all_tickers_union.extend(unique_members)

        level = _equal_weight_composite(unique_members)
        group_levels[gid] = level

        if level is None or bench_level is None:
            reason = "group_price_unavailable" if level is None else "benchmark_unavailable"
            null_reasons.append(f"{gid}:{reason}")
            g_prior = prior.get(gid, {})
            group_results.append({
                "id": gid,
                "label_en": gspec.get("label_en", gid),
                "label_zh": gspec.get("label_zh", gid),
                "n": len(unique_members),
                "rs_20d": None, "rs_60d": None, "accel": None,
                "breadth_above_50dma": None, "dispersion_20d": None,
                "state": g_prior.get("state"),
                "state_candidate": g_prior.get("state_candidate"),
                "state_days": g_prior.get("state_days", 0),
            })
            continue

        rs_20d = _rs(level, bench_level, 20)
        rs_60d = _rs(level, bench_level, 60)
        accel_val = _accel(level, bench_level)
        breadth = _breadth_above_50dma(unique_members)
        disp = _dispersion_20d(unique_members)

        # Hysteresis
        g_prior = prior.get(gid, {})
        candidate = _raw_state(rs_60d, accel_val)
        published_state, pending_candidate, new_state_days = _apply_hysteresis(
            candidate=candidate,
            prior_state=g_prior.get("state"),
            prior_candidate=g_prior.get("state_candidate"),
            prior_state_days=g_prior.get("state_days", 0),
        )

        group_results.append({
            "id": gid,
            "label_en": gspec.get("label_en", gid),
            "label_zh": gspec.get("label_zh", gid),
            "n": len(unique_members),
            "rs_20d": rs_20d,
            "rs_60d": rs_60d,
            "accel": accel_val,
            "breadth_above_50dma": breadth,
            "dispersion_20d": disp,
            "state": published_state,
            "state_candidate": pending_candidate,
            "state_days": new_state_days,
        })

    # --- ew_vs_qqq (union of all groups) ---
    unique_union = list(dict.fromkeys(all_tickers_union))
    ew_level = _equal_weight_composite(unique_union)
    ew_spread_20d: float | None = None
    ew_spread_60d: float | None = None
    ew_pctile_1y: float | None = None

    if ew_level is not None and bench_level is not None:
        ew_spread_20d = _rs(ew_level, bench_level, 20)
        ew_spread_60d = _rs(ew_level, bench_level, 60)
        if ew_spread_20d is not None:
            ew_pctile_1y = _pctile_1y(ew_spread_20d, ew_level, bench_level, window=20)

    ew_vs_qqq = {
        "spread_20d": ew_spread_20d,
        "spread_60d": ew_spread_60d,
        "pctile_1y": ew_pctile_1y,
        "n_members": len(unique_union),
    }

    # --- Divergences ---
    divergences: list[dict] = []
    group_levels_by_id: dict[str, pd.Series | None] = group_levels

    for (id_a, id_b) in _DIVERGENCE_PAIRS:
        g_a = next((g for g in group_results if g["id"] == id_a), None)
        g_b = next((g for g in group_results if g["id"] == id_b), None)
        accel_a = g_a["accel"] if g_a else None
        accel_b = g_b["accel"] if g_b else None

        gap_z, reason = _gap_accel_z(
            accel_a, accel_b,
            group_levels_by_id.get(id_a),
            group_levels_by_id.get(id_b),
            bench_level,
        )
        if reason:
            null_reasons.append(f"divergence_{id_a}_vs_{id_b}:{reason}")

        divergences.append({
            "pair": [id_a, id_b],
            "gap_accel_z": gap_z,
            "note_en": "Descriptive gap between group RS accelerations; no forward claim.",
            "note_zh": "两组RS加速度之间的描述性差距；不构成前瞻性判断。",
        })

    # --- Assemble output ---
    watermark_en = (
        f"Current Nasdaq-100 membership (as of {membership_as_of}); "
        "historical composition approximated. Descriptive, display-only."
    )
    watermark_zh = (
        f"当前纳斯达克100成分股（截至 {membership_as_of}）；"
        "历史成分经近似处理。描述性展示，仅供参考。"
    )

    artifact = {
        "schema": "nasdaq_internals.v1",
        "asof": asof,
        "benchmark": _BENCHMARK,
        "watermark_en": watermark_en,
        "watermark_zh": watermark_zh,
        "ew_vs_qqq": ew_vs_qqq,
        "groups": group_results,
        "divergences": divergences,
        "null_reasons": null_reasons,
    }

    return artifact


# ---------------------------------------------------------------------------
# Null artifact (degraded path)
# ---------------------------------------------------------------------------

_GROUP_IDS = [
    "ai_compute_supply", "ai_capex_spenders", "edge_device",
    "software_enterprise", "cyber", "digital_services_media", "megacap_quality",
]

_GROUP_LABELS: dict[str, tuple[str, str]] = {
    "ai_compute_supply":    ("AI Compute Supply Chain", "AI 算力供应链"),
    "ai_capex_spenders":    ("AI Capex Spenders",       "AI 资本支出方"),
    "edge_device":          ("Edge & Device Ecosystem", "终端设备生态"),
    "software_enterprise":  ("Enterprise Software",     "企业软件"),
    "cyber":                ("Cybersecurity",            "网络安全"),
    "digital_services_media": ("Digital Services & Media", "数字服务���媒体"),
    "megacap_quality":      ("Mega-cap Quality",        "超大盘优质股"),
}


def _null_artifact(asof: str, null_reasons: list[str],
                   membership_as_of: str | None) -> dict[str, Any]:
    """Return a valid all-null artifact per TI-R5 null-honest requirement."""
    mas = membership_as_of or "unknown"
    return {
        "schema": "nasdaq_internals.v1",
        "asof": asof,
        "benchmark": _BENCHMARK,
        "watermark_en": (
            f"Current Nasdaq-100 membership (as of {mas}); "
            "historical composition approximated. Descriptive, display-only."
        ),
        "watermark_zh": (
            f"当前纳斯达克100成分股（截至 {mas}）；"
            "历史成分经近似处理。描述性展示，仅供参考。"
        ),
        "ew_vs_qqq": {"spread_20d": None, "spread_60d": None, "pctile_1y": None, "n_members": 0},
        "groups": [
            {
                "id": gid,
                "label_en": _GROUP_LABELS[gid][0],
                "label_zh": _GROUP_LABELS[gid][1],
                "n": 0,
                "rs_20d": None, "rs_60d": None, "accel": None,
                "breadth_above_50dma": None, "dispersion_20d": None,
                "state": None, "state_candidate": None, "state_days": 0,
            }
            for gid in _GROUP_IDS
        ],
        "divergences": [
            {
                "pair": list(pair),
                "gap_accel_z": None,
                "note_en": "Descriptive gap between group RS accelerations; no forward claim.",
                "note_zh": "两组RS加速度之间的描述性差距；不构成前瞻性判断。",
            }
            for pair in _DIVERGENCE_PAIRS
        ],
        "null_reasons": null_reasons,
    }
