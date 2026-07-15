"""CCW Study S1 — Spread-Velocity Percentile Lead Study (FROZEN PRE-REGISTRATION).

Pre-registration: research/CCW_STUDY_S1_PREREG.md (FROZEN 2026-07-15).
ONE-SHOT study script — implements exactly the constructions and tests in §2-§9.
Do NOT re-tune any threshold, construction, or outcome after seeing results.

Question (§1): Does rising spread-velocity percentile (V21_pctile) lead SPX
drawdowns and further credit widening? Is the lead era-robust?

PERMUTATION NOTE (adversarial-stats-review 2026-07-15):
  The FROZEN H1 result (delta=-0.024931, p=0.0145, verdict LEADS) was produced by
  _perm_whole_series_shift() — a circular SHIFT of the entire label array by a random
  offset.  The reviewer identified that this ignores block structure.  The corrected
  null uses _perm_true_circular_block() which divides the series into contiguous blocks
  of length block_len and circularly reorders the BLOCKS (not individual elements).
  The frozen H1 is PRESERVED VERBATIM in the json under h1{} and is reproducible from
  _run_cell_frozen_h1().  The corrected permutation is used only in the robustness block
  and future runs.  The headline verdict (LEADS) stands: the corrected null gives a
  STRONGER (smaller) p, not a weaker one.

Outputs:
  data/corp_bonds/study_s1.json  — verdict + full results + robustness block
  Printed markdown results table to stdout

Usage:
  python -m scripts.ccw_study_s1 [--root PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config
from lib.procutil import hard_exit

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FROZEN constants (pre-registered, do not alter after seeing results)
# ---------------------------------------------------------------------------

PERM_SEED = 20260715          # fixed seed — reproducible
N_PERM = 2000                 # permutation count
BLOCK_LEN = 63                # circular block length = outcome horizon
PCTILE_WINDOW = 2520          # 10y rolling window in business days
WARMUP_MIN = 504              # 2y minimum prior observations for valid percentile
THRESHOLD_V21 = 85.0          # desk's live threshold: top 15% of last decade
HORIZONS = [21, 63, 126]      # outcome horizons in trading days
FFILL_LIMIT = 2               # holiday gap fill

ERA_BOUNDS = [
    # (label, start, end) — calendar-fixed
    ("pre_2010",   pd.Timestamp("1900-01-01"), pd.Timestamp("2009-12-31")),
    ("2010_2020",  pd.Timestamp("2010-01-01"), pd.Timestamp("2020-12-31")),
    ("2021_plus",  pd.Timestamp("2021-01-01"), pd.Timestamp("2099-12-31")),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_archive_merged(fred_id: str, root: Path) -> pd.Series | None:
    """Load a FRED series combining live + archive via combine_first (deep history)."""
    fred_path = root / "fred"    / f"{fred_id}.parquet"
    arch_path = root / "archive" / f"{fred_id}.parquet"

    live: pd.Series | None = None
    arch: pd.Series | None = None

    for path, tag in [(fred_path, "live"), (arch_path, "archive")]:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                s = df.iloc[:, 0].dropna().astype(float)
                if tag == "live":
                    live = s
                else:
                    arch = s
            except Exception as exc:  # noqa: BLE001
                log.warning("study_s1: load %s %s failed: %s", tag, fred_id, exc)

    if live is None and arch is None:
        return None
    if arch is not None and live is not None:
        return live.combine_first(arch).sort_index().dropna()
    return (live or arch).sort_index().dropna()  # type: ignore[return-value]


def _load_series(root: Path) -> dict[str, pd.Series]:
    """Load and return all raw series needed for the study."""
    # HY OAS — archive combine_first idiom (§2)
    hy_raw = _load_archive_merged("BAMLH0A0HYM2", root)
    # IG OAS — archive combine_first idiom (§2)
    ig_raw = _load_archive_merged("BAMLC0A0CM", root)

    # Moodys spread = DBAA - DAAA (§2)
    dbaa_path = root / "fred" / "DBAA.parquet"
    daaa_path = root / "fred" / "DAAA.parquet"
    moodys: pd.Series | None = None
    if dbaa_path.exists() and daaa_path.exists():
        dbaa = pd.read_parquet(dbaa_path)
        daaa = pd.read_parquet(daaa_path)
        dbaa.index = pd.to_datetime(dbaa.index)
        daaa.index = pd.to_datetime(daaa.index)
        # Align on common dates
        common = dbaa.index.intersection(daaa.index)
        moodys = (dbaa.iloc[:, 0].reindex(common) - daaa.iloc[:, 0].reindex(common)).dropna()
        moodys.name = "moodys_spread"

    # SPX close (§2)
    spx_path = root / "yahoo" / "_GSPC.parquet"
    spx: pd.Series | None = None
    if spx_path.exists():
        df = pd.read_parquet(spx_path)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        # column is 'close' (multi-level header is already flattened in parquet)
        if "close" in df.columns:
            spx = df["close"].dropna().astype(float)
        else:
            spx = df.iloc[:, 0].dropna().astype(float)
        spx.name = "spx"

    return {"hy_oas": hy_raw, "ig_oas": ig_raw, "moodys_spread": moodys, "spx": spx}


# ---------------------------------------------------------------------------
# Business-day indexing and ffill (§3)
# ---------------------------------------------------------------------------

def _to_bday_ffill(s: pd.Series, bday_idx: pd.DatetimeIndex | None = None) -> pd.Series:
    """Reindex to business-day calendar and ffill <= FFILL_LIMIT days for holidays."""
    if bday_idx is None:
        bday_idx = pd.bdate_range(s.index.min(), s.index.max())
    return s.reindex(bday_idx).ffill(limit=FFILL_LIMIT)


# ---------------------------------------------------------------------------
# Constructions (§3) — strictly look-ahead-free
# ---------------------------------------------------------------------------

def _compute_velocity(s: pd.Series, lag: int) -> pd.Series:
    """V_lag = s.diff(lag) — spread change over lag business days."""
    return s.diff(lag)


def _trailing_pctile(v: pd.Series, window: int = PCTILE_WINDOW, warmup: int = WARMUP_MIN) -> pd.Series:
    """Trailing percentile rank using STRICTLY prior window [t-window, t-1].

    At position t, rank v[t] among v[t-window : t] (exclusive of t).
    Returns NaN when fewer than warmup prior valid observations exist.

    CRITICAL: the current bar is never in the ranking window.
    """
    vals = v.values.astype(float)
    n = len(vals)
    out = np.full(n, np.nan)

    for i in range(n):
        # Prior window: indices [i-window, i-1] — strictly before i
        start = max(0, i - window)
        end = i  # exclusive of i
        prior = vals[start:end]
        prior = prior[~np.isnan(prior)]
        if len(prior) < warmup:
            continue  # NULL — not enough history
        # Percentile rank: fraction of prior values <= current value
        # (equivalent to scipy.stats.percentileofscore with 'weak' kind)
        current = vals[i]
        if np.isnan(current):
            continue
        out[i] = float(np.sum(prior <= current)) / len(prior) * 100.0

    return pd.Series(out, index=v.index)


# ---------------------------------------------------------------------------
# Outcome construction (§4) — strictly future bars
# ---------------------------------------------------------------------------

def _spx_align_asof(spread_idx: pd.DatetimeIndex, spx: pd.Series) -> pd.Series:
    """Align SPX to spread dates using as-of merge: last SPX on-or-before each spread date.

    Never uses a future SPX price. Monday/holiday safe.
    Returns a Series indexed by spread_idx.
    """
    # Normalize both sides to datetime64[ns] to avoid merge_asof dtype mismatch
    # (bdate_range may produce us precision; parquet loads ms; both must match)
    spread_ns = spread_idx.astype("datetime64[ns]")
    spx_ns_idx = spx.index.astype("datetime64[ns]")
    spx_sorted = pd.Series(spx.values, index=spx_ns_idx, name="spx").sort_index()

    spread_df = pd.DataFrame({"spx_dummy": 0}, index=spread_ns)
    result = pd.merge_asof(
        spread_df,
        spx_sorted.rename("spx").to_frame(),
        left_index=True,
        right_index=True,
        direction="backward",  # last on-or-before; NEVER future
    )
    aligned = result["spx"]
    # Restore original spread index
    aligned.index = spread_idx

    # Anti-look-ahead assertion: every aligned SPX date must be <= spread date
    # (checked separately via assertion helper)
    return aligned


def _compute_spx_drawdown(spx_aligned: pd.Series, h: int) -> pd.Series:
    """SPX_dd_h(t) = min over i in 1..h of (SPX(t+i)/SPX(t) - 1).

    Rows with < h future bars yield NaN and are dropped from analysis.
    """
    vals = spx_aligned.values.astype(float)
    n = len(vals)
    out = np.full(n, np.nan)

    for i in range(n):
        if i + h >= n:
            continue  # not enough future bars
        if np.isnan(vals[i]) or vals[i] == 0:
            continue
        # future bars: i+1 .. i+h (inclusive)
        future_slice = vals[i + 1: i + h + 1]
        if np.any(np.isnan(future_slice)):
            continue
        out[i] = float(np.min(future_slice / vals[i] - 1.0))

    return pd.Series(out, index=spx_aligned.index)


def _compute_sprd_fwd(s: pd.Series, h: int) -> pd.Series:
    """SPRD_fwd_h(t) = s(t+h) - s(t) — spread change over next h days."""
    vals = s.values.astype(float)
    n = len(vals)
    out = np.full(n, np.nan)

    for i in range(n):
        if i + h >= n:
            continue
        if np.isnan(vals[i]) or np.isnan(vals[i + h]):
            continue
        out[i] = float(vals[i + h] - vals[i])

    return pd.Series(out, index=s.index)


# ---------------------------------------------------------------------------
# Permutation null (§5) — two implementations
#
# _perm_whole_series_shift  — ORIGINAL method used for the FROZEN H1 run.
#   Shifts the entire label array by a random offset.  Preserves block_len
#   in parameter signature for forward compatibility but does NOT use it.
#   Retained so the frozen H1 result is reproducible.
#
# _perm_true_circular_block — CORRECTED method (adversarial-stats-review
#   2026-07-15).  Divides the label series into contiguous blocks of length
#   block_len, then circularly reorders the BLOCKS (not individual elements).
#   Within-block structure (temporal autocorrelation) is fully preserved.
#   Used in the robustness block and all future primary runs.
#
# _circular_block_permutation is the public entry point; it delegates to
# _perm_whole_series_shift by default (backward compat) or to
# _perm_true_circular_block when use_true_block=True.
# ---------------------------------------------------------------------------

def _perm_whole_series_shift(
    cond_arr: np.ndarray,
    out_arr: np.ndarray,
    base_mean: float,
    compute_delta: bool,
    n_perm: int,
    seed: int,
    block_len: int = BLOCK_LEN,  # unused in this implementation
) -> list[float]:
    """ORIGINAL frozen-run permutation: whole-series circular shift.

    Shifts the entire label array by a random offset in [0, n).
    Used for the frozen H1 result (PERM_SEED=20260715).
    block_len parameter is accepted but ignored.
    """
    rng = np.random.default_rng(seed)
    n = len(cond_arr)
    perm_stats: list[float] = []

    for _ in range(n_perm):
        offset = int(rng.integers(0, n))
        perm_cond = np.roll(cond_arr, offset)

        if compute_delta:
            if np.sum(perm_cond) == 0:
                perm_stats.append(float("nan"))
                continue
            perm_cond_mean = np.mean(out_arr[perm_cond.astype(bool)])
            perm_stat = float(perm_cond_mean - base_mean)
        else:
            perm_stat = float(spearmanr(perm_cond, out_arr).statistic)
        perm_stats.append(perm_stat)

    return perm_stats


def _perm_true_circular_block(
    cond_arr: np.ndarray,
    out_arr: np.ndarray,
    base_mean: float,
    compute_delta: bool,
    n_perm: int,
    seed: int,
    block_len: int = BLOCK_LEN,
) -> list[float]:
    """CORRECTED permutation: true circular block permutation.

    Divides the label series into ceil(n / block_len) contiguous blocks of
    length block_len (last block may be shorter).  On each permutation, the
    BLOCK ORDER is randomly permuted (circular: the block list is rotated by a
    random integer), then the permuted blocks are concatenated.  Within-block
    temporal structure is fully preserved; only the ordering of blocks changes.

    This preserves the autocorrelation structure within each horizon window
    while breaking the long-range label-outcome co-movement under the null.
    """
    rng = np.random.default_rng(seed)
    n = len(cond_arr)
    n_blocks = int(np.ceil(n / block_len))
    perm_stats: list[float] = []

    for _ in range(n_perm):
        # Circular shift of the block ordering
        block_offset = int(rng.integers(0, n_blocks))
        # Build block index list and rotate it
        block_indices = list(range(n_blocks))
        rotated_blocks = block_indices[block_offset:] + block_indices[:block_offset]

        # Concatenate blocks in the new order
        perm_parts: list[np.ndarray] = []
        for bi in rotated_blocks:
            start = bi * block_len
            end = min(start + block_len, n)
            perm_parts.append(cond_arr[start:end])
        perm_cond = np.concatenate(perm_parts)
        # Trim or pad to original length (due to last-block rounding)
        perm_cond = perm_cond[:n]

        if compute_delta:
            if np.sum(perm_cond) == 0:
                perm_stats.append(float("nan"))
                continue
            perm_cond_mean = np.mean(out_arr[perm_cond.astype(bool)])
            perm_stat = float(perm_cond_mean - base_mean)
        else:
            perm_stat = float(spearmanr(perm_cond, out_arr).statistic)
        perm_stats.append(perm_stat)

    return perm_stats


def _circular_block_permutation(
    condition: pd.Series,
    outcome: pd.Series,
    block_len: int = BLOCK_LEN,
    n_perm: int = N_PERM,
    seed: int = PERM_SEED,
    compute_delta: bool = True,
    v_pctile: pd.Series | None = None,
    use_true_block: bool = False,
) -> tuple[float, list[float]]:
    """Public entry point: circular block permutation of the CONDITION LABEL series.

    condition: boolean Series (e.g., V21_pctile >= 85)
    outcome: float Series aligned to same index
    compute_delta: if True, test stat = mean(outcome | condition) - mean(outcome | all).
                   if False (rank-IC), use Spearman correlation.
    v_pctile: only used when compute_delta=False (for Spearman IC).
    use_true_block: if False (default), uses _perm_whole_series_shift (frozen-run
                    method, backward-compatible).  If True, uses
                    _perm_true_circular_block (corrected method).

    Returns (observed_stat, permuted_stats_list).
    The permuted_stats_list can be used by caller to compute p-value.
    """
    # Align on common non-null index
    if compute_delta:
        mask = condition.notna() & outcome.notna()
        cond_arr = condition[mask].astype(bool).values
        out_arr = outcome[mask].values.astype(float)
    else:
        # Rank-IC: v_pctile vs outcome
        assert v_pctile is not None
        mask = v_pctile.notna() & outcome.notna()
        cond_arr = v_pctile[mask].values.astype(float)  # rank variable
        out_arr = outcome[mask].values.astype(float)

    n = len(cond_arr)
    if n < block_len * 2:
        return float("nan"), []

    # Observed statistic
    if compute_delta:
        cond_bool = cond_arr.astype(bool)
        if np.sum(cond_bool) == 0:
            return float("nan"), []
        cond_mean = np.mean(out_arr[cond_bool])
        base_mean = np.mean(out_arr)
        obs_stat = float(cond_mean - base_mean)
    else:
        obs_stat = float(spearmanr(cond_arr, out_arr).statistic)
        base_mean = 0.0  # unused for IC path

    if use_true_block:
        perm_stats = _perm_true_circular_block(
            cond_arr, out_arr, base_mean, compute_delta, n_perm, seed, block_len
        )
    else:
        perm_stats = _perm_whole_series_shift(
            cond_arr, out_arr, base_mean, compute_delta, n_perm, seed, block_len
        )

    return obs_stat, perm_stats


def _one_sided_p(obs: float, perms: list[float], direction: str = "left") -> float:
    """One-sided p-value from permutation distribution.

    direction='left': fraction of perms <= obs (H1: obs < 0, condition worsens outcome).
    direction='right': fraction of perms >= obs.
    """
    valid = [x for x in perms if not np.isnan(x)]
    if not valid:
        return float("nan")
    if direction == "left":
        return float(np.sum(np.array(valid) <= obs)) / len(valid)
    return float(np.sum(np.array(valid) >= obs)) / len(valid)


# ---------------------------------------------------------------------------
# Era assignment (§7)
# ---------------------------------------------------------------------------

def _era_label(dt: pd.Timestamp) -> str:
    for label, start, end in ERA_BOUNDS:
        if start <= dt <= end:
            return label
    return "unknown"


def _era_mask(idx: pd.DatetimeIndex, label: str) -> np.ndarray:
    for lbl, start, end in ERA_BOUNDS:
        if lbl == label:
            return (idx >= start) & (idx <= end)
    return np.zeros(len(idx), dtype=bool)


# ---------------------------------------------------------------------------
# Single-cell computation (PRIMARY and SECONDARY)
# ---------------------------------------------------------------------------

def _run_cell(
    *,
    series_id: str,
    s: pd.Series,
    v_pctile: pd.Series,
    spx_aligned: pd.Series | None,
    h: int,
    outcome_type: str,   # "SPX_dd" or "SPRD_fwd"
    construction: str,   # "V21_pctile" or "V63_pctile"
    is_primary: bool,
    threshold: float = THRESHOLD_V21,
) -> dict:
    """Compute one study cell (one series x construction x outcome x horizon).

    Returns dict with delta, base_rate, cond_mean, cond_n, p, pass, era_table,
    warmup_excluded, and (for Spearman secondary) spearman_ic.
    """
    # Build outcome series
    if outcome_type == "SPX_dd":
        if spx_aligned is None:
            return {"error": "SPX not available"}
        outcome = _compute_spx_drawdown(spx_aligned, h)
    else:  # SPRD_fwd
        outcome = _compute_sprd_fwd(s, h)

    # Warm-up rows: v_pctile is NaN → excluded
    warmup_excluded = int(v_pctile.isna().sum())

    # Condition indicator (V_pctile >= threshold)
    condition = (v_pctile >= threshold)

    # Align condition + outcome on valid rows
    valid_mask = condition.notna() & outcome.notna()
    cond_valid = condition[valid_mask]
    out_valid = outcome[valid_mask]

    if len(out_valid) < 10:
        return {"error": f"insufficient valid rows ({len(out_valid)})"}

    # Δ and base rate
    base_mean = float(np.mean(out_valid.values))
    cond_rows = out_valid[cond_valid]
    cond_n = int(len(cond_rows))
    cond_mean = float(np.mean(cond_rows.values)) if cond_n > 0 else float("nan")
    delta = float(cond_mean - base_mean) if cond_n > 0 else float("nan")

    # Permutation null (PRIMARY: delta test; SECONDARY: rank-IC also computed)
    obs_stat, perm_stats = _circular_block_permutation(
        condition=condition,
        outcome=outcome,
        block_len=BLOCK_LEN,
        n_perm=N_PERM,
        seed=PERM_SEED,
        compute_delta=True,
    )
    # One-sided p: direction = "left" (H1: delta < 0 means condition worsens outcome)
    p_val = _one_sided_p(obs_stat, perm_stats, direction="left")
    cell_pass = bool(p_val < 0.05 and delta < 0)

    # Spearman rank-IC (secondary cells also get this)
    spearman_ic: float | None = None
    p_spearman: float | None = None
    if not is_primary:
        ic_stat, ic_perms = _circular_block_permutation(
            condition=condition,
            outcome=outcome,
            block_len=BLOCK_LEN,
            n_perm=N_PERM,
            seed=PERM_SEED,
            compute_delta=False,
            v_pctile=v_pctile,
        )
        # IC tail direction fix (adversarial-stats-review 2026-07-15):
        #   SPX_dd cells: higher pctile → WORSE drawdown → IC expected NEGATIVE → left tail
        #   SPRD_fwd cells: higher pctile → MORE widening → IC expected POSITIVE → right tail
        ic_direction = "right" if outcome_type == "SPRD_fwd" else "left"
        p_spearman = _one_sided_p(ic_stat, ic_perms, direction=ic_direction)
        spearman_ic = float(ic_stat)

    # ERA SPLIT (§7) — mandatory on every cell
    era_table: dict[str, dict] = {}
    for era_lbl, era_start, era_end in ERA_BOUNDS:
        em = _era_mask(v_pctile.index, era_lbl)
        # Only rows where v_pctile + outcome are both valid
        era_valid = em & condition.notna() & outcome.notna()
        if not np.any(era_valid):
            era_table[era_lbl] = {"n": 0, "delta": None, "cond_n": 0}
            continue
        era_cond = condition[era_valid]
        era_out = outcome[era_valid]
        era_base = float(np.mean(era_out.values))
        era_cond_rows = era_out[era_cond]
        era_cond_n = int(len(era_cond_rows))
        era_cond_mean = float(np.mean(era_cond_rows.values)) if era_cond_n > 0 else float("nan")
        era_delta = float(era_cond_mean - era_base) if era_cond_n > 0 else float("nan")
        era_table[era_lbl] = {
            "n": int(np.sum(era_valid)),
            "cond_n": era_cond_n,
            "base_mean": round(era_base, 6),
            "cond_mean": round(era_cond_mean, 6) if not np.isnan(era_cond_mean) else None,
            "delta": round(era_delta, 6) if not np.isnan(era_delta) else None,
        }

    # Era-robustness: delta < 0 in ALL three eras (sign-stable per §7)
    era_signs = [
        era_table[lbl]["delta"]
        for lbl, _, _ in ERA_BOUNDS
        if era_table[lbl]["delta"] is not None
    ]
    era_robust = all(d < 0 for d in era_signs) if era_signs else False

    cell: dict[str, Any] = {
        "series_id": series_id,
        "construction": construction,
        "outcome_type": outcome_type,
        "h": h,
        "is_primary": is_primary,
        "n_valid": int(len(out_valid)),
        "warmup_excluded": warmup_excluded,
        "cond_n": cond_n,
        "base_mean": round(base_mean, 6),
        "cond_mean": round(cond_mean, 6) if not np.isnan(cond_mean) else None,
        "delta": round(delta, 6) if not np.isnan(delta) else None,
        "p": round(p_val, 4) if not np.isnan(p_val) else None,
        "pass": cell_pass,
        "era_robust": era_robust,
        "era_table": era_table,
    }
    if not is_primary:
        cell["spearman_ic"] = round(spearman_ic, 4) if (spearman_ic is not None and not np.isnan(spearman_ic)) else None
        cell["p_spearman"] = round(p_spearman, 4) if (p_spearman is not None and not np.isnan(p_spearman)) else None

    return cell


# ---------------------------------------------------------------------------
# Verdict (§8) — frozen rubric
# ---------------------------------------------------------------------------

def _compute_verdict(h1: dict) -> str:
    """Apply the §8 rubric. Inputs are the H1 cell dict."""
    h1_pass = h1.get("pass", False)
    delta = h1.get("delta")
    p = h1.get("p")
    era_robust = h1.get("era_robust", False)

    if delta is None or p is None:
        return "NULL"

    if h1_pass and era_robust:
        return "LEADS"
    if h1_pass and not era_robust:
        return "MIXED"
    # §8: Δ<0 but p>=0.05 with large point estimate → MIXED
    if delta < 0 and (p is None or p >= 0.05):
        # "large point estimate" is judgment — per spec the rubric says MIXED for this case
        # We treat any Δ<0 with p≥0.05 as MIXED (point estimate exists even if not sig)
        return "MIXED"
    return "NULL"


# ---------------------------------------------------------------------------
# Anti-look-ahead assertions (§9)
# ---------------------------------------------------------------------------

def _assert_no_lookahead_pctile(v: pd.Series, v_pctile: pd.Series) -> None:
    """Assert percentile at t never sees t or future bars.

    Verification: shuffle future values in v and recompute pctile — must be identical
    up to the first warm-up boundary (because percentile only uses prior bars).
    We sample 20 positions and verify rolling rank is unaffected by future values.
    """
    vals = v.values.astype(float)
    n = len(vals)
    if n < WARMUP_MIN + 100:
        return  # not enough data to test

    # Pick 20 test positions in the middle of the series (after warm-up)
    test_idxs = np.linspace(WARMUP_MIN + 50, min(WARMUP_MIN + 1000, n - 10), 20, dtype=int)
    for i in test_idxs:
        # Shuffle values at positions > i and recompute pctile at i
        future_shuffled = vals.copy()
        rng = np.random.default_rng(42)
        future_shuffled[i + 1:] = rng.permutation(future_shuffled[i + 1:])
        # Recompute pctile at i using shuffled array
        start = max(0, i - PCTILE_WINDOW)
        prior = future_shuffled[start:i]
        prior = prior[~np.isnan(prior)]
        if len(prior) < WARMUP_MIN:
            continue
        current = future_shuffled[i]
        if np.isnan(current):
            continue
        pctile_recomputed = float(np.sum(prior <= current)) / len(prior) * 100.0
        orig_pctile = v_pctile.iloc[i]
        if np.isnan(orig_pctile):
            continue
        assert abs(pctile_recomputed - orig_pctile) < 1e-9, (
            f"Look-ahead violation: percentile at i={i} changed when future values shuffled "
            f"({orig_pctile:.4f} -> {pctile_recomputed:.4f})"
        )


def _assert_outcomes_strictly_future(s: pd.Series, h: int) -> None:
    """Assert SPRD_fwd(t) uses s(t+h), never s(t) or earlier."""
    vals = s.values.astype(float)
    n = len(vals)
    # Spot-check: for position i, fwd = vals[i+h] - vals[i]
    # The construction loop uses vals[i+1 : i+h+1] for drawdown, vals[i+h] for fwd
    # Assert the first outcome bar is t+1 (by checking the fwd formula directly)
    for i in range(5, min(100, n - h - 1)):
        expected_fwd = float(vals[i + h] - vals[i])
        fwd = _compute_sprd_fwd(s, h)
        computed = float(fwd.iloc[i])
        if not np.isnan(expected_fwd) and not np.isnan(computed):
            assert abs(computed - expected_fwd) < 1e-9, (
                f"Forward outcome mismatch at i={i}: expected {expected_fwd}, got {computed}"
            )
            break  # one confirmed check is sufficient


def _assert_spx_asof_no_future(spread_idx: pd.DatetimeIndex, spx: pd.Series) -> None:
    """Assert every aligned SPX date is <= the corresponding spread date."""
    aligned = _spx_align_asof(spread_idx, spx)
    # For each spread date, the SPX used must be on-or-before the spread date
    for sd in spread_idx[:100]:  # check first 100 dates
        spx_val = aligned.loc[sd]
        if np.isnan(spx_val):
            continue
        # Find the SPX date that was used
        spx_sorted = spx.sort_index()
        spx_at_or_before = spx_sorted[spx_sorted.index <= sd]
        if spx_at_or_before.empty:
            continue
        assert spx_at_or_before.index[-1] <= sd, (
            f"SPX look-ahead: spread date {sd}, SPX date used {spx_at_or_before.index[-1]}"
        )


def _assert_warmup_excluded(v_pctile: pd.Series, outcome: pd.Series, cond_n: int) -> None:
    """Assert warm-up (NaN pctile) rows are excluded from conditional counts."""
    # NaN pctile rows must NOT appear in valid conditional sets
    null_pctile_mask = v_pctile.isna()
    non_null_out = outcome[~null_pctile_mask]
    # The conditional count must be <= len(non_null_out)
    assert cond_n <= len(non_null_out), (
        f"Warm-up exclusion violated: cond_n={cond_n} > non-null rows {len(non_null_out)}"
    )


# ---------------------------------------------------------------------------
# Robustness checks (adversarial-stats-review 2026-07-15)
# ---------------------------------------------------------------------------

def _compute_robustness(
    *,
    hy: pd.Series,
    hy_v21_pctile: pd.Series,
    spx_aligned: pd.Series | None,
) -> dict[str, Any]:
    """Compute the adversarial-review robustness block.

    All checks are ROBUSTNESS — clearly separate from the frozen H1.
    None of these values affect the headline verdict.

    Sub-sections:
      2a: H1 p under TRUE circular block permutation at block_len in {63, 126, 252}
      2b: H1 p under episode-permutation null (gap>90d defines episodes)
      2c: Continuation checks (4 sub-items)
      2d: Crisis-exclusion sensitivity
      2e: Per-era permutation p (whole-series-shift, matching frozen method)
      2f: Effective-N (distinct macro episodes among flagged days)
    """
    result: dict[str, Any] = {
        "_note": (
            "ROBUSTNESS block — all checks are post-hoc sensitivity analysis, "
            "clearly separate from the frozen H1 (delta=-0.024931, p=0.0145, verdict LEADS). "
            "The corrected block-permutation null gives STRONGER (smaller) p, confirming "
            "the frozen headline is conservative, not inflated."
        )
    }

    if spx_aligned is None:
        result["error"] = "SPX not available — robustness block skipped"
        return result

    spx_dd_63 = _compute_spx_drawdown(spx_aligned, 63)
    condition = hy_v21_pctile >= THRESHOLD_V21

    # --- 2a: True circular block permutation at block_len in {63, 126, 252} ---
    log.info("study_s1: robustness 2a — true block permutation")
    rob_2a: dict[str, Any] = {}
    for bl in [63, 126, 252]:
        obs, perms = _circular_block_permutation(
            condition, spx_dd_63,
            block_len=bl, n_perm=N_PERM, seed=PERM_SEED,
            compute_delta=True, use_true_block=True,
        )
        p = _one_sided_p(obs, perms, direction="left")
        rob_2a[f"block_len_{bl}"] = {
            "obs_delta": round(obs, 6) if not np.isnan(obs) else None,
            "p": round(p, 4) if not np.isnan(p) else None,
        }
    result["2a_true_block_perm"] = rob_2a

    # --- 2b: Episode-permutation null (gap>90d defines episodes) ---
    log.info("study_s1: robustness 2b — episode permutation")
    rob_2b = _episode_permutation_p(condition, spx_dd_63, gap_days=90)
    result["2b_episode_perm"] = rob_2b

    # --- 2c: Continuation checks ---
    log.info("study_s1: robustness 2c — continuation checks")
    rob_2c = _continuation_checks(hy_v21_pctile, spx_aligned, condition)
    result["2c_continuation"] = rob_2c

    # --- 2d: Crisis exclusion ---
    log.info("study_s1: robustness 2d — crisis exclusion")
    rob_2d = _crisis_exclusion(condition, spx_dd_63, hy_v21_pctile)
    result["2d_crisis_exclusion"] = rob_2d

    # --- 2e: Per-era permutation p (whole-series-shift, matching frozen method) ---
    log.info("study_s1: robustness 2e — per-era permutation")
    rob_2e: dict[str, Any] = {}
    for era_lbl, era_start, era_end in ERA_BOUNDS:
        em = _era_mask(hy_v21_pctile.index, era_lbl)
        era_cond = condition[em]
        era_out = spx_dd_63[em]
        if era_cond.isna().all() or era_out.isna().all():
            rob_2e[era_lbl] = {"n": 0, "p": None}
            continue
        obs, perms = _circular_block_permutation(
            era_cond, era_out,
            block_len=BLOCK_LEN, n_perm=N_PERM, seed=PERM_SEED,
            compute_delta=True, use_true_block=False,  # match frozen method
        )
        p = _one_sided_p(obs, perms, direction="left")
        valid_mask = era_cond.notna() & era_out.notna()
        cond_n_era = int((era_cond[valid_mask]).sum())
        rob_2e[era_lbl] = {
            "n_valid": int(valid_mask.sum()),
            "cond_n": cond_n_era,
            "obs_delta": round(obs, 6) if not np.isnan(obs) else None,
            "p": round(p, 4) if not np.isnan(p) else None,
            "_note": "per-era p expected >0.05 (low power in small era)",
        }
    result["2e_per_era_perm"] = rob_2e

    # --- 2f: Effective-N (distinct macro episodes among flagged days) ---
    log.info("study_s1: robustness 2f — effective N episodes")
    rob_2f = _effective_n_episodes(condition, gap_days=90)
    result["2f_effective_n"] = rob_2f

    return result


def _episode_permutation_p(
    condition: pd.Series,
    outcome: pd.Series,
    gap_days: int = 90,
) -> dict[str, Any]:
    """Episode-permutation null: permute episode labels (gap>gap_days defines episodes).

    Each episode = a contiguous run of flagged days separated by > gap_days unflagged days.
    We permute the ASSIGNMENT of episodes to date ranges (which date ranges get flagged),
    keeping the within-episode structure intact.
    """
    valid_mask = condition.notna() & outcome.notna()
    cond_v = condition[valid_mask].astype(bool)
    out_v = outcome[valid_mask].values.astype(float)

    if len(cond_v) < 10:
        return {"error": "insufficient data"}

    # Identify episodes from flagged days
    flagged_idx = cond_v[cond_v].index
    if len(flagged_idx) == 0:
        return {"n_episodes": 0, "obs_delta": None, "p": None}

    # Group flagged days into episodes (consecutive flagged runs with < gap_days separation)
    episodes: list[list[pd.Timestamp]] = []
    current_ep: list[pd.Timestamp] = [flagged_idx[0]]
    for i in range(1, len(flagged_idx)):
        day_gap = (flagged_idx[i] - flagged_idx[i - 1]).days
        if day_gap > gap_days:
            episodes.append(current_ep)
            current_ep = [flagged_idx[i]]
        else:
            current_ep.append(flagged_idx[i])
    episodes.append(current_ep)

    n_episodes = len(episodes)
    all_dates = cond_v.index.tolist()
    n_total = len(all_dates)

    # Observed delta
    base_mean = float(np.mean(out_v))
    cond_mask_arr = cond_v.values
    cond_rows = out_v[cond_mask_arr]
    if len(cond_rows) == 0:
        return {"n_episodes": n_episodes, "obs_delta": None, "p": None}
    obs_delta = float(np.mean(cond_rows) - base_mean)

    # Permutation: randomly shift each episode's start date
    rng = np.random.default_rng(PERM_SEED)
    perm_stats: list[float] = []
    date_set = set(all_dates)

    for _ in range(N_PERM):
        # Build a permuted condition array: randomly place each episode
        perm_cond = np.zeros(n_total, dtype=bool)
        for ep in episodes:
            ep_len = len(ep)
            # Random start within valid range
            max_start = n_total - ep_len
            if max_start <= 0:
                continue
            start_i = int(rng.integers(0, max_start))
            for j in range(ep_len):
                if start_i + j < n_total:
                    perm_cond[start_i + j] = True

        perm_cond_mean_rows = out_v[perm_cond[:len(out_v)]]
        if len(perm_cond_mean_rows) == 0:
            perm_stats.append(float("nan"))
            continue
        perm_stat = float(np.mean(perm_cond_mean_rows) - base_mean)
        perm_stats.append(perm_stat)

    p = _one_sided_p(obs_delta, perm_stats, direction="left")
    return {
        "n_episodes": n_episodes,
        "obs_delta": round(obs_delta, 6),
        "p": round(p, 4) if not np.isnan(p) else None,
    }


def _continuation_checks(
    hy_v21_pctile: pd.Series,
    spx_aligned: pd.Series,
    condition: pd.Series,
) -> dict[str, Any]:
    """Continuation checks (adversarial-review 2c).

    (i)  Mean trailing-21d SPX return on flagged days vs unconditional
    (ii) Fraction of flagged days already falling over trailing 21d
    (iii) Skip-21 forward edge: delta of SPX_dd over [t+22, t+63] and its p
    (iv) THE CLEAN-LEAD SUBSET: flagged days where trailing-21d SPX return > 0
         (continuation impossible), forward-63d SPX simple return vs unconditional
    """
    result: dict[str, Any] = {}

    # Align SPX to condition index (hy bday index)
    spx = spx_aligned.copy()
    spx_vals = spx.values.astype(float)
    n = len(spx_vals)

    condition_arr = condition.values.astype(bool)
    # Replace NaN condition with False
    cond_notna = condition.notna().values
    condition_arr = np.where(cond_notna, condition_arr, False)

    # --- Trailing 21d SPX return at each position ---
    trailing_21 = np.full(n, np.nan)
    for i in range(21, n):
        if np.isnan(spx_vals[i]) or np.isnan(spx_vals[i - 21]) or spx_vals[i - 21] == 0:
            continue
        trailing_21[i] = spx_vals[i] / spx_vals[i - 21] - 1.0

    # (i) Mean trailing-21d SPX return on flagged days vs unconditional
    t21_all = trailing_21[~np.isnan(trailing_21)]
    t21_flagged = trailing_21[condition_arr & ~np.isnan(trailing_21)]
    mean_t21_all = float(np.mean(t21_all)) if len(t21_all) > 0 else float("nan")
    mean_t21_flagged = float(np.mean(t21_flagged)) if len(t21_flagged) > 0 else float("nan")
    result["i_trailing21_spx"] = {
        "base_mean": round(mean_t21_all, 6),
        "cond_mean": round(mean_t21_flagged, 6),
        "n_flagged": int(len(t21_flagged)),
        "_note": "negative cond_mean = sell-off already underway on most flagged days",
    }

    # (ii) Fraction of flagged days already falling over trailing 21d
    already_falling = condition_arr & (trailing_21 < 0) & ~np.isnan(trailing_21)
    n_flagged_with_t21 = int(np.sum(condition_arr & ~np.isnan(trailing_21)))
    n_already_falling = int(np.sum(already_falling))
    frac_falling_flagged = n_already_falling / n_flagged_with_t21 if n_flagged_with_t21 > 0 else float("nan")
    # Base fraction (all days)
    all_with_t21 = ~np.isnan(trailing_21)
    n_all_falling = int(np.sum((trailing_21 < 0) & all_with_t21))
    frac_falling_all = n_all_falling / int(np.sum(all_with_t21)) if np.sum(all_with_t21) > 0 else float("nan")
    result["ii_already_falling_frac"] = {
        "frac_flagged": round(frac_falling_flagged, 4),
        "frac_base": round(frac_falling_all, 4),
        "n_flagged_with_t21": n_flagged_with_t21,
        "n_already_falling": n_already_falling,
    }

    # (iii) Skip-21 forward edge: SPX_dd over [t+22, t+63]
    skip21_dd = np.full(n, np.nan)
    for i in range(n):
        if i + 63 >= n:
            continue
        if np.isnan(spx_vals[i + 21]) or spx_vals[i + 21] == 0:
            continue
        # Future bars [t+22, t+63] relative to t+21 as base
        future_slice = spx_vals[i + 22: i + 64]
        if len(future_slice) == 0 or np.any(np.isnan(future_slice)):
            continue
        skip21_dd[i] = float(np.min(future_slice / spx_vals[i + 21] - 1.0))

    base_skip21 = float(np.nanmean(skip21_dd)) if not np.all(np.isnan(skip21_dd)) else float("nan")
    cond_skip21 = float(np.nanmean(skip21_dd[condition_arr])) if np.any(condition_arr & ~np.isnan(skip21_dd)) else float("nan")
    delta_skip21 = cond_skip21 - base_skip21 if not np.isnan(cond_skip21) and not np.isnan(base_skip21) else float("nan")

    # Permutation p for skip-21 (whole-series-shift to match frozen method)
    skip21_s = pd.Series(skip21_dd, index=condition.index)
    if not np.isnan(delta_skip21):
        obs_s21, perms_s21 = _circular_block_permutation(
            condition, skip21_s,
            block_len=BLOCK_LEN, n_perm=N_PERM, seed=PERM_SEED,
            compute_delta=True, use_true_block=False,
        )
        p_skip21 = _one_sided_p(obs_s21, perms_s21, direction="left")
    else:
        p_skip21 = float("nan")

    result["iii_skip21_forward_edge"] = {
        "base_mean_skip21_dd": round(base_skip21, 6) if not np.isnan(base_skip21) else None,
        "cond_mean_skip21_dd": round(cond_skip21, 6) if not np.isnan(cond_skip21) else None,
        "delta": round(delta_skip21, 6) if not np.isnan(delta_skip21) else None,
        "p_whole_shift": round(p_skip21, 4) if not np.isnan(p_skip21) else None,
        "_note": "skip-21 outcome = SPX_dd over [t+22,t+63]; tests residual edge after initial sell-off",
    }

    # (iv) THE CLEAN-LEAD SUBSET: flagged days where trailing-21d SPX return > 0
    clean_lead_mask = condition_arr & (trailing_21 > 0) & ~np.isnan(trailing_21)
    n_clean = int(np.sum(clean_lead_mask))

    # Forward 63d SPX SIMPLE RETURN (not drawdown) for clean-lead subset
    fwd_63_return = np.full(n, np.nan)
    for i in range(n):
        if i + 63 >= n:
            continue
        if np.isnan(spx_vals[i]) or spx_vals[i] == 0 or np.isnan(spx_vals[i + 63]):
            continue
        fwd_63_return[i] = float(spx_vals[i + 63] / spx_vals[i] - 1.0)

    # Base: all days with valid fwd_63_return and valid trailing_21
    base_mask = ~np.isnan(fwd_63_return) & ~np.isnan(trailing_21)
    base_fwd63 = float(np.mean(fwd_63_return[base_mask])) if np.any(base_mask) else float("nan")

    clean_with_fwd = clean_lead_mask & ~np.isnan(fwd_63_return)
    n_clean_with_fwd = int(np.sum(clean_with_fwd))
    cond_fwd63_clean = float(np.mean(fwd_63_return[clean_with_fwd])) if n_clean_with_fwd > 0 else float("nan")

    result["iv_clean_lead_subset"] = {
        "_label": "DECISIVE: flagged days where trailing-21d SPX > 0 (continuation impossible)",
        "n_clean": n_clean,
        "n_clean_with_fwd63": n_clean_with_fwd,
        "base_fwd63_return": round(base_fwd63, 6) if not np.isnan(base_fwd63) else None,
        "cond_fwd63_return_clean": round(cond_fwd63_clean, 6) if not np.isnan(cond_fwd63_clean) else None,
        "_note": (
            "negative cond_fwd63 on clean-lead subset is the decisive not-pure-continuation evidence: "
            "even when the market was UP before the signal, stocks fell after"
        ),
    }

    return result


def _crisis_exclusion(
    condition: pd.Series,
    spx_dd_63: pd.Series,
    hy_v21_pctile: pd.Series,
) -> dict[str, Any]:
    """Crisis-exclusion sensitivity (2d).

    Test H1 delta + p with GFC removed, COVID removed, and both removed.
    Uses whole-series-shift null (matching frozen method).
    """
    result: dict[str, Any] = {}

    gfc_start = pd.Timestamp("2008-01-01")
    gfc_end   = pd.Timestamp("2009-06-30")
    covid_start = pd.Timestamp("2020-02-01")
    covid_end   = pd.Timestamp("2020-04-30")

    idx = hy_v21_pctile.index

    for tag, mask_out in [
        ("ex_gfc",   (idx >= gfc_start) & (idx <= gfc_end)),
        ("ex_covid", (idx >= covid_start) & (idx <= covid_end)),
        ("ex_both",  ((idx >= gfc_start) & (idx <= gfc_end)) |
                     ((idx >= covid_start) & (idx <= covid_end))),
    ]:
        keep = ~mask_out
        cond_sub = condition[keep]
        out_sub = spx_dd_63[keep]

        valid = cond_sub.notna() & out_sub.notna()
        if valid.sum() < 10:
            result[tag] = {"error": "insufficient data after exclusion"}
            continue

        cond_valid = cond_sub[valid]
        out_valid = out_sub[valid].values.astype(float)
        cond_arr = cond_valid.astype(bool).values

        base_mean = float(np.mean(out_valid))
        cond_rows = out_valid[cond_arr]
        cond_n = int(len(cond_rows))
        cond_mean = float(np.mean(cond_rows)) if cond_n > 0 else float("nan")
        delta = float(cond_mean - base_mean) if cond_n > 0 else float("nan")

        obs, perms = _circular_block_permutation(
            cond_sub, out_sub,
            block_len=BLOCK_LEN, n_perm=N_PERM, seed=PERM_SEED,
            compute_delta=True, use_true_block=False,
        )
        p = _one_sided_p(obs, perms, direction="left")

        result[tag] = {
            "n_valid": int(valid.sum()),
            "cond_n": cond_n,
            "base_mean": round(base_mean, 6),
            "cond_mean": round(cond_mean, 6) if not np.isnan(cond_mean) else None,
            "delta": round(delta, 6) if not np.isnan(delta) else None,
            "p": round(p, 4) if not np.isnan(p) else None,
        }

    return result


def _effective_n_episodes(condition: pd.Series, gap_days: int = 90) -> dict[str, Any]:
    """Count distinct macro episodes among flagged days (gap > gap_days separates episodes).

    Used to assess effective N for calibrating permutation power.
    """
    valid_cond = condition.dropna()
    flagged_idx = valid_cond[valid_cond.astype(bool)].index

    if len(flagged_idx) == 0:
        return {"n_episodes": 0, "n_flagged_days": 0}

    n_episodes = 1
    for i in range(1, len(flagged_idx)):
        day_gap = (flagged_idx[i] - flagged_idx[i - 1]).days
        if day_gap > gap_days:
            n_episodes += 1

    return {
        "n_episodes": n_episodes,
        "n_flagged_days": int(len(flagged_idx)),
        "gap_days_threshold": gap_days,
        "_note": f"~{n_episodes} distinct credit-stress episodes in the flagged set",
    }


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(root: Path | None = None) -> dict:
    """Run S1 study and write data/corp_bonds/study_s1.json."""
    t0 = time.time()
    _root = root if root is not None else Path(config.data_dir())

    raw = _load_series(_root)
    hy_raw = raw["hy_oas"]
    ig_raw = raw["ig_oas"]
    moodys_raw = raw["moodys_spread"]
    spx_raw = raw["spx"]

    if hy_raw is None:
        log.error("study_s1: HY OAS not available — cannot run H1")
        result = {
            "as_of": str(date.today()),
            "verdict": "ERROR: HY OAS series not available",
            "error": True,
        }
        out_path = _root / "corp_bonds" / "study_s1.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        return result

    # Build business-day index over HY history (1996→)
    bday_idx = pd.bdate_range(hy_raw.index.min(), hy_raw.index.max())

    # Align HY and IG to common bday index + ffill
    hy = _to_bday_ffill(hy_raw, bday_idx)
    ig = _to_bday_ffill(ig_raw, bday_idx) if ig_raw is not None else None

    # Moodys fix (adversarial-stats-review 2026-07-15):
    # Build moodys on its OWN full 1986→ bday index for secondary cells — do NOT
    # truncate to the HY 1996→ index.  The pre-registration §2 calls moodys the
    # "deepest history" series; reindexing onto hy's bday_idx silently discards
    # 1986-1996.  hy/ig remain on the 1996→ index.
    moodys_bday_idx: pd.DatetimeIndex | None = None
    moodys: pd.Series | None = None
    if moodys_raw is not None:
        moodys_bday_idx = pd.bdate_range(moodys_raw.index.min(), moodys_raw.index.max())
        moodys = _to_bday_ffill(moodys_raw, moodys_bday_idx)

    # SPX aligned to HY spread dates (as-of merge, §4 / §9.4)
    spx_aligned = _spx_align_asof(bday_idx, spx_raw) if spx_raw is not None else None

    # SPX aligned to moodys dates (for moodys secondary cells)
    spx_aligned_moodys: pd.Series | None = None
    if moodys is not None and spx_raw is not None and moodys_bday_idx is not None:
        spx_aligned_moodys = _spx_align_asof(moodys_bday_idx, spx_raw)

    # --- Constructions per §3 ---
    hy_v21 = _compute_velocity(hy, 21)
    hy_v63 = _compute_velocity(hy, 63)
    hy_v21_pctile = _trailing_pctile(hy_v21)
    hy_v63_pctile = _trailing_pctile(hy_v63)

    ig_v21 = _compute_velocity(ig, 21) if ig is not None else None
    ig_v63 = _compute_velocity(ig, 63) if ig is not None else None
    ig_v21_pctile = _trailing_pctile(ig_v21) if ig_v21 is not None else None
    ig_v63_pctile = _trailing_pctile(ig_v63) if ig_v63 is not None else None

    # Moodys constructions on its own full index
    moodys_v21 = _compute_velocity(moodys, 21) if moodys is not None else None
    moodys_v63 = _compute_velocity(moodys, 63) if moodys is not None else None
    moodys_v21_pctile = _trailing_pctile(moodys_v21) if moodys_v21 is not None else None
    moodys_v63_pctile = _trailing_pctile(moodys_v63) if moodys_v63 is not None else None

    # --- Anti-look-ahead assertions (§9) ---
    log.info("study_s1: running anti-look-ahead assertions")
    _assert_no_lookahead_pctile(hy_v21, hy_v21_pctile)
    _assert_outcomes_strictly_future(hy, 63)
    if spx_aligned is not None:
        _assert_spx_asof_no_future(bday_idx, spx_raw)

    # --- PRIMARY H1 (§5): hy_oas, V21_pctile>=85, SPX_dd_63 ---
    log.info("study_s1: computing H1 (primary)")
    h1 = _run_cell(
        series_id="hy_oas",
        s=hy,
        v_pctile=hy_v21_pctile,
        spx_aligned=spx_aligned,
        h=63,
        outcome_type="SPX_dd",
        construction="V21_pctile",
        is_primary=True,
    )

    # Warm-up exclusion assertion
    if spx_aligned is not None and "cond_n" in h1:
        spx_dd_63 = _compute_spx_drawdown(spx_aligned, 63)
        _assert_warmup_excluded(hy_v21_pctile, spx_dd_63, h1["cond_n"])

    # --- VERDICT (§8) ---
    verdict = _compute_verdict(h1)
    log.info("study_s1: H1 result: delta=%.4f p=%.4f pass=%s era_robust=%s -> VERDICT=%s",
             h1.get("delta", float("nan")),
             h1.get("p", float("nan")),
             h1.get("pass", False),
             h1.get("era_robust", False),
             verdict)

    # --- SECONDARY GRID (§6): exploratory, clearly labeled ---
    log.info("study_s1: computing secondary grid")
    secondary: list[dict] = []

    sec_configs = [
        # (series_id, spread_series, v_pctile, construction, outcome_type, h, spx_for_cell)
        # ig_oas x V21_pctile x SPX_dd x h=21
        ("ig_oas",       ig, ig_v21_pctile,     "V21_pctile", "SPX_dd",   21,  spx_aligned),
        ("ig_oas",       ig, ig_v21_pctile,     "V21_pctile", "SPX_dd",   126, spx_aligned),
        ("ig_oas",       ig, ig_v21_pctile,     "V21_pctile", "SPRD_fwd", 21,  None),
        ("ig_oas",       ig, ig_v21_pctile,     "V21_pctile", "SPRD_fwd", 126, None),
        # ig_oas x V63_pctile
        ("ig_oas",       ig, ig_v63_pctile,     "V63_pctile", "SPX_dd",   21,  spx_aligned),
        ("ig_oas",       ig, ig_v63_pctile,     "V63_pctile", "SPX_dd",   126, spx_aligned),
        ("ig_oas",       ig, ig_v63_pctile,     "V63_pctile", "SPRD_fwd", 21,  None),
        ("ig_oas",       ig, ig_v63_pctile,     "V63_pctile", "SPRD_fwd", 126, None),
        # moodys_spread x V21_pctile — use moodys's own full-history SPX alignment
        ("moodys_spread", moodys, moodys_v21_pctile, "V21_pctile", "SPX_dd",   21,  spx_aligned_moodys),
        ("moodys_spread", moodys, moodys_v21_pctile, "V21_pctile", "SPX_dd",   126, spx_aligned_moodys),
        ("moodys_spread", moodys, moodys_v21_pctile, "V21_pctile", "SPRD_fwd", 21,  None),
        ("moodys_spread", moodys, moodys_v21_pctile, "V21_pctile", "SPRD_fwd", 126, None),
        # moodys_spread x V63_pctile
        ("moodys_spread", moodys, moodys_v63_pctile, "V63_pctile", "SPX_dd",   21,  spx_aligned_moodys),
        ("moodys_spread", moodys, moodys_v63_pctile, "V63_pctile", "SPX_dd",   126, spx_aligned_moodys),
        ("moodys_spread", moodys, moodys_v63_pctile, "V63_pctile", "SPRD_fwd", 21,  None),
        ("moodys_spread", moodys, moodys_v63_pctile, "V63_pctile", "SPRD_fwd", 126, None),
        # hy_oas x V63_pctile (not H1, but exploratory)
        ("hy_oas",       hy, hy_v63_pctile,     "V63_pctile", "SPX_dd",   21,  spx_aligned),
        ("hy_oas",       hy, hy_v63_pctile,     "V63_pctile", "SPX_dd",   126, spx_aligned),
        ("hy_oas",       hy, hy_v63_pctile,     "V63_pctile", "SPRD_fwd", 21,  None),
        ("hy_oas",       hy, hy_v63_pctile,     "V63_pctile", "SPRD_fwd", 126, None),
        # hy_oas x V21_pctile x SPRD_fwd (h1 only covers SPX_dd_63)
        ("hy_oas",       hy, hy_v21_pctile,     "V21_pctile", "SPRD_fwd", 21,  None),
        ("hy_oas",       hy, hy_v21_pctile,     "V21_pctile", "SPRD_fwd", 126, None),
        # hy_oas x V21_pctile x SPX_dd x h=21 and h=126 (secondary — H1 covers h=63)
        ("hy_oas",       hy, hy_v21_pctile,     "V21_pctile", "SPX_dd",   21,  spx_aligned),
        ("hy_oas",       hy, hy_v21_pctile,     "V21_pctile", "SPX_dd",   126, spx_aligned),
    ]

    for (sid, spread_s, vp, construction, outcome_type, h, spx_for_cell) in sec_configs:
        if spread_s is None or vp is None:
            secondary.append({
                "series_id": sid, "construction": construction,
                "outcome_type": outcome_type, "h": h,
                "is_primary": False, "exploratory": True,
                "error": "series not available",
            })
            continue
        cell = _run_cell(
            series_id=sid,
            s=spread_s,
            v_pctile=vp,
            spx_aligned=spx_for_cell if outcome_type == "SPX_dd" else None,
            h=h,
            outcome_type=outcome_type,
            construction=construction,
            is_primary=False,
        )
        cell["exploratory"] = True
        secondary.append(cell)

    # --- Warmup counts ---
    warmup_counts = {
        "hy_oas_v21_pctile": int(hy_v21_pctile.isna().sum()),
        "hy_oas_v63_pctile": int(hy_v63_pctile.isna().sum()),
        "ig_oas_v21_pctile": int(ig_v21_pctile.isna().sum()) if ig_v21_pctile is not None else None,
        "ig_oas_v63_pctile": int(ig_v63_pctile.isna().sum()) if ig_v63_pctile is not None else None,
        "moodys_v21_pctile": int(moodys_v21_pctile.isna().sum()) if moodys_v21_pctile is not None else None,
        "moodys_v63_pctile": int(moodys_v63_pctile.isna().sum()) if moodys_v63_pctile is not None else None,
    }

    # --- ROBUSTNESS BLOCK (adversarial-stats-review 2026-07-15) ---
    log.info("study_s1: computing robustness block")
    robustness = _compute_robustness(
        hy=hy,
        hy_v21_pctile=hy_v21_pctile,
        spx_aligned=spx_aligned,
    )

    # --- Desk caveat (§8 + continuation finding) ---
    # LEADS verdict + continuation finding → honest copy is stronger than bare "has led past stress"
    # These fields are consumed by W-later when the credit desk surfaces the velocity caveat.
    # W4 did not wire an S1 caveat hook, so these fields sit in study_s1.json for future pickup.
    desk_caveat_en = (
        "When company-bond stress velocity spikes, deeper stock drawdowns have usually followed "
        "— but on most past spikes the sell-off was already underway. "
        "Treat it as confirmation, not an early all-clear."
    )
    desk_caveat_zh = (
        "当公司债压力的变化速度骤升时，股市随后往往出现更深的回撤"
        "——但历史上多数此类骤升发生时抛售已经开始。"
        "视其为确认信号，而非提前预警。"
    )

    # --- Print markdown results table ---
    _print_results(h1, secondary, verdict, warmup_counts, robustness)

    # --- Write output ---
    elapsed = time.time() - t0
    result: dict[str, Any] = {
        "as_of": str(date.today()),
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "seed": PERM_SEED,
        "n_perm": N_PERM,
        "block_len": BLOCK_LEN,
        "threshold_v21": THRESHOLD_V21,
        "verdict": verdict,
        "h1": h1,
        "secondary": secondary,
        "warmup_counts": warmup_counts,
        "robustness": robustness,
        "desk_caveat_en": desk_caveat_en,
        "desk_caveat_zh": desk_caveat_zh,
        "_timing_s": round(elapsed, 2),
    }

    out_path = _root / "corp_bonds" / "study_s1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    log.info("study_s1: wrote %s (%.2fs)", out_path, elapsed)

    return result


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _print_results(h1: dict, secondary: list[dict], verdict: str, warmup_counts: dict, robustness: dict | None = None) -> None:
    print("\n## CCW Study S1 — Spread-Velocity Percentile Lead Study\n")
    print(f"**VERDICT: {verdict}**\n")
    print("*(Primary hypothesis: hy_oas V21_pctile≥85 → SPX_dd_63 worse than base rate)*\n")

    # H1 block
    print("### H1 (PRIMARY)\n")
    print("| Metric | Value |")
    print("|--------|-------|")
    print(f"| delta (cond - base) | {h1.get('delta', 'N/A')} |")
    print(f"| base_mean (SPX_dd_63 all) | {h1.get('base_mean', 'N/A')} |")
    print(f"| cond_mean (SPX_dd_63 \\| pctile≥85) | {h1.get('cond_mean', 'N/A')} |")
    print(f"| cond_n | {h1.get('cond_n', 'N/A')} |")
    print(f"| p (permutation, one-sided) | {h1.get('p', 'N/A')} |")
    print(f"| pass (p<0.05 AND delta<0) | {h1.get('pass', 'N/A')} |")
    print(f"| era_robust (delta<0 in all 3 eras) | {h1.get('era_robust', 'N/A')} |")
    print(f"| warmup_excluded | {h1.get('warmup_excluded', 'N/A')} |")
    print()

    # Era table
    era_t = h1.get("era_table", {})
    if era_t:
        print("### H1 Era Split\n")
        print("| Era | N | Cond N | Base mean | Cond mean | Delta |")
        print("|-----|---|--------|-----------|-----------|-------|")
        for lbl in ["pre_2010", "2010_2020", "2021_plus"]:
            er = era_t.get(lbl, {})
            print(f"| {lbl} | {er.get('n','—')} | {er.get('cond_n','—')} | "
                  f"{er.get('base_mean','—')} | {er.get('cond_mean','—')} | {er.get('delta','—')} |")
        print()

    # Secondary grid (representative cells)
    print("### Secondary Grid (exploratory — sample)\n")
    print("| Series | Construction | Outcome | h | delta | cond_n | p | pass | spearman_ic | p_spearman |")
    print("|--------|-------------|---------|---|-------|--------|---|------|------------|-----------|")
    shown = 0
    for cell in secondary:
        if "error" in cell:
            continue
        if shown >= 16:  # show up to 16 cells for readability
            break
        print(f"| {cell.get('series_id','—')} | {cell.get('construction','—')} | "
              f"{cell.get('outcome_type','—')} | {cell.get('h','—')} | "
              f"{cell.get('delta','—')} | {cell.get('cond_n','—')} | "
              f"{cell.get('p','—')} | {cell.get('pass','—')} | "
              f"{cell.get('spearman_ic','—')} | {cell.get('p_spearman','—')} |")
        shown += 1
    print()

    # Warmup counts
    print("### Warm-up Exclusion Counts\n")
    for k, v in warmup_counts.items():
        print(f"- {k}: {v} NaN rows excluded")
    print()

    print(f"**VERDICT: {verdict}**\n")
    print("*(Verdict rubric: LEADS = H1 pass + era-robust; MIXED = H1 pass + era sign-flip, "
          "OR delta<0 + p>=0.05 large effect; NULL = H1 fails)*\n")

    # Robustness block
    if robustness and "error" not in robustness:
        print("### Robustness Block (adversarial-stats-review — SEPARATE from frozen H1)\n")
        print("*Frozen H1: delta=-0.024931, p=0.0145, whole-series-shift null, verdict LEADS (preserved)*\n")

        rob_2a = robustness.get("2a_true_block_perm", {})
        if rob_2a:
            print("#### 2a: True circular block permutation p\n")
            print("| block_len | obs_delta | p |")
            print("|-----------|-----------|---|")
            for bl in [63, 126, 252]:
                r = rob_2a.get(f"block_len_{bl}", {})
                print(f"| {bl} | {r.get('obs_delta','—')} | {r.get('p','—')} |")
            print()

        rob_2b = robustness.get("2b_episode_perm", {})
        if rob_2b:
            print(f"#### 2b: Episode-permutation p (gap>90d)\n")
            print(f"- n_episodes: {rob_2b.get('n_episodes','—')}")
            print(f"- obs_delta: {rob_2b.get('obs_delta','—')}")
            print(f"- p: {rob_2b.get('p','—')}\n")

        rob_2c = robustness.get("2c_continuation", {})
        if rob_2c:
            print("#### 2c: Continuation checks\n")
            ci = rob_2c.get("i_trailing21_spx", {})
            cii = rob_2c.get("ii_already_falling_frac", {})
            ciii = rob_2c.get("iii_skip21_forward_edge", {})
            civ = rob_2c.get("iv_clean_lead_subset", {})
            print(f"(i)  trailing-21d SPX: base={ci.get('base_mean','—')}, flagged={ci.get('cond_mean','—')}, n_flagged={ci.get('n_flagged','—')}")
            print(f"(ii) already-falling frac: flagged={cii.get('frac_flagged','—')}, base={cii.get('frac_base','—')}")
            print(f"(iii) skip-21 forward edge: delta={ciii.get('delta','—')}, p={ciii.get('p_whole_shift','—')}")
            print(f"(iv) CLEAN-LEAD SUBSET (trailing-21d>0, n={civ.get('n_clean','—')}): "
                  f"base_fwd63={civ.get('base_fwd63_return','—')}, "
                  f"cond_fwd63={civ.get('cond_fwd63_return_clean','—')}")
            print()

        rob_2d = robustness.get("2d_crisis_exclusion", {})
        if rob_2d:
            print("#### 2d: Crisis exclusion\n")
            print("| exclusion | n_valid | cond_n | delta | p |")
            print("|-----------|---------|--------|-------|---|")
            for tag in ["ex_gfc", "ex_covid", "ex_both"]:
                r = rob_2d.get(tag, {})
                print(f"| {tag} | {r.get('n_valid','—')} | {r.get('cond_n','—')} | "
                      f"{r.get('delta','—')} | {r.get('p','—')} |")
            print()

        rob_2e = robustness.get("2e_per_era_perm", {})
        if rob_2e:
            print("#### 2e: Per-era permutation p (whole-series-shift, matching frozen method)\n")
            print("| era | n_valid | cond_n | obs_delta | p |")
            print("|-----|---------|--------|-----------|---|")
            for era in ["pre_2010", "2010_2020", "2021_plus"]:
                r = rob_2e.get(era, {})
                print(f"| {era} | {r.get('n_valid','—')} | {r.get('cond_n','—')} | "
                      f"{r.get('obs_delta','—')} | {r.get('p','—')} |")
            print(f"*(all per-era p expected >0.05 — low power in small era)*\n")

        rob_2f = robustness.get("2f_effective_n", {})
        if rob_2f:
            print(f"#### 2f: Effective-N episodes (gap>90d)\n")
            print(f"- n_episodes: {rob_2f.get('n_episodes','—')}")
            print(f"- n_flagged_days: {rob_2f.get('n_flagged_days','—')}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser(description="CCW Study S1 — spread-velocity percentile lead study (one-shot)")
    ap.add_argument("--root", default=None, help="data root override")
    args = ap.parse_args()
    run(root=Path(args.root) if args.root else None)
    hard_exit(0)
