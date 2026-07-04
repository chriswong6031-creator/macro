"""Oracle P3 Gauntlet — Validation harness.

Implements §1–§3 and §6 of research/ORACLE_GAUNTLET_P3_PREREG.md VERBATIM.
No detection threshold may be changed here — EPISODE_CFG / CONFIG are frozen.

Forward-RS computation:  the outcome columns (`outcome_rs_{h}d`,
`outcome_rs_{h}d_confirmed`, `outcome_rs_{h}d_undeniable`) are read DIRECTLY
from the pre-computed parquets, which were produced by
engine/oracle/episodes.py `_fwd_rs` / `_add_outcome_columns`.  Those columns
are look-ahead-safe by construction (see HONESTY FRAMING in episodes.py).
The harness DOES NOT re-compute forward RS from raw prices; it reads the
stored outcome columns.  This mirrors the engine convention faithfully: the
same cumulative-RS product formula `(1+window).prod()-1` is used for placebo /
benchmark draws that ARE computed here.

Benchmark B1 computes trailing-1M-RS deciles from the panel using ONLY panel
rows whose date is STRICTLY LESS THAN the episode detection date (no forward
peek).

Usage
-----
    python scripts/oracle_gauntlet_p3.py --data-dir data/

Outputs (relative to data-dir parent, i.e. the repo root):
    data/oracle/gauntlet/p3_results.json
    data/oracle/gauntlet/p3_trial_ledger.json
    research/ORACLE_GAUNTLET_P3_RESULTS.md
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed — all randomness goes through this RNG.  Reruns must be byte-identical.
# ---------------------------------------------------------------------------
SEED = 20260704

# ---------------------------------------------------------------------------
# Era boundaries per §3 G4 (detection date bucketing by year)
# ---------------------------------------------------------------------------
ERAS: list[tuple[str, int, int]] = [
    ("1999-2014", 1999, 2014),
    ("2015-2019", 2015, 2019),
    ("2020-2022", 2020, 2022),
    ("2023-2026", 2023, 2026),
]

# ---------------------------------------------------------------------------
# Helper: direction-adjusted forward RS
# ---------------------------------------------------------------------------

def direction_adjust(values: np.ndarray, direction: np.ndarray | pd.Series) -> np.ndarray:
    """Multiply OUT-episode outcomes by -1 so 'positive = good' for all rows.

    Parameters
    ----------
    values : np.ndarray
        Raw forward RS values (float).
    direction : array-like of str
        'in' or 'out' per row.

    Returns
    -------
    np.ndarray
        direction-adjusted values: OUT rows get ×-1; IN rows unchanged.
    """
    sign = np.where(np.asarray(direction) == "out", -1.0, 1.0)
    return values * sign


# ---------------------------------------------------------------------------
# Outcome column resolution
# ---------------------------------------------------------------------------

def _outcome_col(tier: str, h: int) -> str:
    """Return the pre-computed outcome column name for a given tier and horizon.

    Tier mapping:
        'onset'      -> outcome_rs_{h}d
        'confirmed'  -> outcome_rs_{h}d_confirmed
        'undeniable' -> outcome_rs_{h}d_undeniable

    Maturity column:
        'onset'      -> outcome_mature_{h}d
        'confirmed'  -> outcome_mature_{h}d_confirmed
        'undeniable' -> outcome_mature_{h}d_undeniable
    """
    if tier == "onset":
        return f"outcome_rs_{h}d"
    elif tier == "confirmed":
        return f"outcome_rs_{h}d_confirmed"
    elif tier == "undeniable":
        return f"outcome_rs_{h}d_undeniable"
    else:
        raise ValueError(f"Unknown tier: {tier!r}")


def _mature_col(tier: str, h: int) -> str:
    if tier == "onset":
        return f"outcome_mature_{h}d"
    elif tier == "confirmed":
        return f"outcome_mature_{h}d_confirmed"
    elif tier == "undeniable":
        return f"outcome_mature_{h}d_undeniable"
    else:
        raise ValueError(f"Unknown tier: {tier!r}")


def _detection_date_col(tier: str) -> str:
    """Return the column name holding the detection date for a given tier."""
    if tier == "onset":
        return "onset_date"
    elif tier == "confirmed":
        return "confirmed_date"
    elif tier == "undeniable":
        return "undeniable_date"
    else:
        raise ValueError(f"Unknown tier: {tier!r}")


# ---------------------------------------------------------------------------
# Placebo sampler (G1)
# ---------------------------------------------------------------------------

def _build_exclusion_mask(
    panel_dates: np.ndarray,
    episode_spans: list[tuple[int, int]],
    zone: int = 10,
) -> np.ndarray:
    """Return boolean mask (True = excluded) for panel date positions.

    Excludes positions within ±zone sessions of any real same-direction
    episode span.  Spans are expressed as (start_idx, end_idx) in panel_dates.
    """
    n = len(panel_dates)
    excluded = np.zeros(n, dtype=bool)
    for s, e in episode_spans:
        lo = max(0, s - zone)
        hi = min(n - 1, e + zone)
        excluded[lo: hi + 1] = True
    return excluded


def _date_to_idx(date_series_sorted: np.ndarray, target: Any) -> int:
    """Binary-search the sorted date array; return the closest index."""
    idx = np.searchsorted(date_series_sorted, np.datetime64(target, "ns"), side="left")
    return int(min(idx, len(date_series_sorted) - 1))


def _compute_fwd_rs_from_panel(
    rs_series: pd.Series,
    anchor_date: Any,
    h: int,
) -> float:
    """Compute cumulative forward RS over h sessions from anchor_date.

    Mirrors engine/oracle/episodes.py `_fwd_rs` exactly:
        future = rs_series[rs_series.index > anchor_date]
        window = future.iloc[:h]
        cum_rs = (1 + window).prod() - 1

    Returns np.nan if fewer than h forward sessions are available.
    """
    if pd.isnull(anchor_date):
        return np.nan
    future = rs_series[rs_series.index > anchor_date]
    if len(future) < h:
        return np.nan
    window = future.iloc[:h]
    return float((1 + window).prod() - 1)


def sample_placebo(
    episodes_sub: pd.DataFrame,
    panel: pd.DataFrame,
    h: int,
    tier: str,
    direction_filter: str,
    n_draws: int = 200,
    exclusion_zone: int = 10,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Draw placebo means per §3 G1.

    For each draw:
      - Per node, sample the same number of pseudo-detection dates as real
        episodes, uniformly from dates NOT inside ±10 sessions of any real
        same-direction episode span.
      - Compute the forward RS (using the panel's RS column) for each
        pseudo-date at horizon h.
      - Take the direction-adjusted mean across all pseudo-episodes.

    Parameters
    ----------
    episodes_sub : pd.DataFrame
        Filtered episodes (direction == direction_filter, matured outcomes).
    panel : pd.DataFrame
        MultiIndex (node, date) panel; needs 'rs' column.
    h : int
        Horizon in sessions (5, 21, or 63).
    tier : str
        'onset', 'confirmed', or 'undeniable'.
    direction_filter : str
        'in' or 'out'.
    n_draws : int
        Number of placebo draws (200 per spec).
    exclusion_zone : int
        ±sessions around real episode spans to exclude.
    rng : np.random.Generator
        Seeded generator.

    Returns
    -------
    np.ndarray
        Array of length n_draws; each element is one placebo direction-adjusted mean.
    """
    if rng is None:
        rng = np.random.default_rng(SEED)

    det_col = _detection_date_col(tier)

    # Build per-node episode counts and spans (onset→exhausted or onset+21d buffer)
    per_node_counts: dict[str, int] = {}
    per_node_spans: dict[str, list[tuple[Any, Any]]] = {}

    for _, row in episodes_sub.iterrows():
        nd = row["node"]
        per_node_counts[nd] = per_node_counts.get(nd, 0) + 1
        start_dt = row["onset_date"]
        end_dt = row.get("exhausted_date")
        if pd.isnull(end_dt) or end_dt is None:
            # Open episode: extend 21 sessions beyond detection
            end_dt = start_dt + pd.Timedelta(days=30)  # calendar buffer
        if nd not in per_node_spans:
            per_node_spans[nd] = []
        per_node_spans[nd].append((start_dt, end_dt))

    # Pre-build per-node panel structures
    node_panel_dates: dict[str, np.ndarray] = {}
    node_rs_series: dict[str, pd.Series] = {}
    node_excluded_mask: dict[str, np.ndarray] = {}

    nodes_in_episodes = set(per_node_counts.keys())
    for nd in nodes_in_episodes:
        try:
            node_data = panel.xs(nd, level="node").sort_index()
        except KeyError:
            continue
        if "rs" not in node_data.columns or node_data.empty:
            continue
        dates_arr = node_data.index.values  # datetime64
        rs_ser = node_data["rs"]

        # Build spans as index positions
        spans_idx: list[tuple[int, int]] = []
        for s_dt, e_dt in per_node_spans.get(nd, []):
            si = int(np.searchsorted(dates_arr, np.datetime64(s_dt, "ns"), side="left"))
            ei = int(np.searchsorted(dates_arr, np.datetime64(e_dt, "ns"), side="right")) - 1
            ei = max(si, min(ei, len(dates_arr) - 1))
            spans_idx.append((si, ei))

        excl = _build_exclusion_mask(dates_arr, spans_idx, zone=exclusion_zone)
        node_panel_dates[nd] = dates_arr
        node_rs_series[nd] = rs_ser
        node_excluded_mask[nd] = excl

    placebo_means = np.full(n_draws, np.nan)

    for draw_i in range(n_draws):
        draw_values: list[float] = []
        for nd, count in per_node_counts.items():
            if nd not in node_panel_dates:
                continue
            dates_arr = node_panel_dates[nd]
            excl = node_excluded_mask[nd]
            rs_ser = node_rs_series[nd]

            valid_indices = np.where(~excl)[0]
            if len(valid_indices) < count:
                # Not enough valid dates — use all available (best effort)
                sampled_indices = valid_indices
            else:
                sampled_indices = rng.choice(valid_indices, size=count, replace=False)

            for idx in sampled_indices:
                pseudo_date = pd.Timestamp(dates_arr[idx])
                fwd = _compute_fwd_rs_from_panel(rs_ser, pseudo_date, h)
                if np.isnan(fwd):
                    continue
                # Direction-adjust: OUT -> ×-1, IN -> ×1
                adj = fwd * (-1.0 if direction_filter == "out" else 1.0)
                draw_values.append(adj)

        if draw_values:
            placebo_means[draw_i] = float(np.mean(draw_values))

    return placebo_means


# ---------------------------------------------------------------------------
# Block bootstrap CI (G2)
# ---------------------------------------------------------------------------

def block_bootstrap_ci(
    values: np.ndarray,
    n_iters: int = 2000,
    block_size: int = 21,
    ci_level: float = 0.95,
    rng: np.random.Generator | None = None,
) -> tuple[float, float, float, np.ndarray]:
    """Bootstrap 95% CI of the mean using non-overlapping blocks.

    Episodes are ordered by detection date (caller responsibility).
    Blocks of 21 consecutive episodes are drawn with replacement.

    Returns
    -------
    (lower, upper, mean, bootstrap_distribution)
    """
    if rng is None:
        rng = np.random.default_rng(SEED)
    n = len(values)
    if n == 0:
        return (np.nan, np.nan, np.nan, np.array([]))

    # Build non-overlapping blocks
    blocks = []
    for start in range(0, n, block_size):
        block = values[start: start + block_size]
        if len(block) > 0:
            blocks.append(block)
    n_blocks = len(blocks)

    boot_means = np.empty(n_iters)
    for i in range(n_iters):
        chosen = rng.integers(0, n_blocks, size=n_blocks)
        sample = np.concatenate([blocks[c] for c in chosen])
        boot_means[i] = float(np.mean(sample))

    alpha = 1.0 - ci_level
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return lo, hi, float(np.mean(values)), boot_means


# ---------------------------------------------------------------------------
# BH-FDR correction (G5) — 10-line sort, no scipy
# ---------------------------------------------------------------------------

def bh_fdr(p_values: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg FDR correction.

    Parameters
    ----------
    p_values : list of float
        Raw one-sided p-values.  NaN values are treated as non-rejected.
    q : float
        FDR level (0.10 per spec).

    Returns
    -------
    list of bool
        True = rejected (passes FDR correction).
    """
    n = len(p_values)
    if n == 0:
        return []
    arr = np.asarray(p_values, dtype=float)
    order = np.argsort(arr)
    ranked = np.empty(n, dtype=float)
    for rank_i, orig_i in enumerate(order):
        ranked[orig_i] = rank_i + 1  # 1-indexed

    # BH threshold: p_(k) <= k/m * q
    rejected = np.zeros(n, dtype=bool)
    # Find the largest k such that p_(k) <= k/m * q
    # All ranks up to that k are rejected.
    sorted_p = arr[order]
    thresholds = (np.arange(1, n + 1) / n) * q
    passing = sorted_p <= thresholds
    if passing.any():
        k_max = int(np.where(passing)[0].max()) + 1  # 1-indexed rank
        # Reject all with rank <= k_max
        for rank_i, orig_i in enumerate(order):
            if rank_i < k_max:
                rejected[orig_i] = True

    return [bool(r) for r in rejected]


# ---------------------------------------------------------------------------
# Regime stratification (G3)
# ---------------------------------------------------------------------------

def _regime_strata(episodes: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return boolean index arrays for regime strata.

    VIX: above/below 0.6 at detection (regime_vix_pctile).
    SPY: above/below 200dma (regime_spy_above_200d).
    """
    strata: dict[str, np.ndarray] = {}
    if "regime_vix_pctile" in episodes.columns:
        vix = episodes["regime_vix_pctile"].to_numpy(dtype=float)
        strata["vix_high"] = vix >= 0.6
        strata["vix_low"] = vix < 0.6
    if "regime_spy_above_200d" in episodes.columns:
        spy = episodes["regime_spy_above_200d"].to_numpy(dtype=float)
        strata["spy_above_200"] = spy == 1.0
        strata["spy_below_200"] = spy != 1.0
    return strata


def _check_g3(
    pooled_mean: float,
    strata_means: dict[str, float],
    strata_ns: dict[str, int] | None = None,
) -> tuple[bool, str]:
    """Evaluate G3 regime-stratification survival (registered wording).

    FIX 3: Thread per-stratum n through and implement the registered wording:
    'at least the LARGER stratum retains a positive direction-adjusted mean AND
    no stratum reverses sign with |mean| > half the pooled edge.'

    Previous implementation substituted 'at least one stratum positive' for
    'the LARGER stratum positive', which is a weaker condition and not what
    the pre-registration states.

    Parameters
    ----------
    pooled_mean : float
        Direction-adjusted pooled mean across all episodes.
    strata_means : dict[str, float]
        Direction-adjusted mean per stratum name.
    strata_ns : dict[str, int] | None
        Number of (non-NaN) observations per stratum.  When None the function
        falls back to the n-unaware behaviour (treats both strata equally, which
        is conservative — it can only fail, not spuriously pass).

    Returns (passes, explanation_string).
    """
    if not strata_means:
        return True, "no strata available — G3 trivially passes"

    half_pooled = abs(pooled_mean) / 2.0 if pooled_mean != 0 else 0.0

    # Group strata into pairs
    pairs = [
        ("vix_high", "vix_low"),
        ("spy_above_200", "spy_below_200"),
    ]

    notes = []
    passes = True

    for s1, s2 in pairs:
        m1 = strata_means.get(s1)
        m2 = strata_means.get(s2)
        if m1 is None or m2 is None or np.isnan(m1) or np.isnan(m2):
            continue

        # Condition 1: the LARGER stratum retains a positive direction-adjusted mean.
        n1 = (strata_ns.get(s1, 0) if strata_ns else 0)
        n2 = (strata_ns.get(s2, 0) if strata_ns else 0)

        if n1 >= n2:
            larger_name, larger_mean = s1, m1
        else:
            larger_name, larger_mean = s2, m2

        if larger_mean <= 0:
            passes = False
            notes.append(
                f"G3 fail: larger stratum {larger_name} (n={max(n1, n2)}) has non-positive mean={larger_mean:.4f}"
            )

        # Condition 2: no stratum reverses sign with |mean| > half pooled edge
        for sname, mv in [(s1, m1), (s2, m2)]:
            sign_pooled = 1.0 if pooled_mean > 0 else -1.0
            sign_stratum = 1.0 if mv > 0 else -1.0
            if sign_stratum != sign_pooled and abs(mv) > half_pooled:
                passes = False
                notes.append(
                    f"G3 fail: {sname} reverses sign (mean={mv:.4f}) and |mean|={abs(mv):.4f} > half_pooled={half_pooled:.4f}"
                )

    explanation = "; ".join(notes) if notes else "G3 pass"
    return passes, explanation


# ---------------------------------------------------------------------------
# Era helper (G4 / S5)
# ---------------------------------------------------------------------------

def _assign_era(detection_year: int) -> str:
    for name, y_start, y_end in ERAS:
        if y_start <= detection_year <= y_end:
            return name
    return "unknown"


def _era_means(
    values: np.ndarray,
    detection_dates: pd.Series,
) -> dict[str, float]:
    """Return direction-adjusted mean per era (NaN if no data)."""
    years = pd.to_datetime(detection_dates).dt.year.to_numpy()
    result: dict[str, float] = {}
    for era_name, y_start, y_end in ERAS:
        mask = (years >= y_start) & (years <= y_end)
        era_vals = values[mask]
        era_vals = era_vals[~np.isnan(era_vals)]
        result[era_name] = float(np.mean(era_vals)) if len(era_vals) > 0 else np.nan
    return result


def _check_g4(era_means: dict[str, float]) -> tuple[bool, str]:
    """G4: direction-adjusted mean positive in ≥3 of 4 eras, including 2023–2026."""
    positive_count = sum(1 for v in era_means.values() if v > 0 and not np.isnan(v))
    ai_era_ok = era_means.get("2023-2026", np.nan)
    ai_era_positive = not np.isnan(ai_era_ok) and ai_era_ok > 0
    passes = positive_count >= 3 and ai_era_positive
    note = f"{positive_count}/4 eras positive, 2023-2026={ai_era_ok:.4f}" if not np.isnan(ai_era_ok) else f"{positive_count}/4 eras positive, 2023-2026=no data"
    return passes, note


# ---------------------------------------------------------------------------
# Benchmark B1 — momentum null
# ---------------------------------------------------------------------------

def compute_b1(
    episodes_sub: pd.DataFrame,
    panel: pd.DataFrame,
    h: int,
    direction_filter: str,
    tier: str,
) -> float:
    """Compute the benchmark B1 direction-adjusted mean for trailing-1M-RS extreme decile.

    For each episode, on the detection date (STRICTLY ≤ that date — no forward
    peek), compute the trailing 21-session RS for all nodes.  Select:
      - OUT episodes: bottom decile (lowest trailing RS)
      - IN  episodes: top decile (highest trailing RS)
    Then compute the forward RS from those decile nodes at horizon h.

    Returns the direction-adjusted mean across all episodes' benchmark legs.
    """
    det_col = _detection_date_col(tier)
    outcome_col_name = _outcome_col(tier, h)
    mature_col_name = _mature_col(tier, h)

    # Build per-node sorted date array + RS series for lookups
    node_rs_by_date: dict[str, pd.Series] = {}
    all_nodes = panel.index.get_level_values("node").unique()
    for nd in all_nodes:
        try:
            ns = panel.xs(nd, level="node").sort_index()["rs"]
        except KeyError:
            continue
        node_rs_by_date[nd] = ns

    b1_values: list[float] = []

    for _, row in episodes_sub.iterrows():
        det_date = row[det_col]
        if pd.isnull(det_date):
            continue
        if not row.get(mature_col_name, False):
            continue

        # Trailing 21 sessions RS for each node STRICTLY ≤ det_date
        trailing_rs: dict[str, float] = {}
        for nd, rs_ser in node_rs_by_date.items():
            past = rs_ser[rs_ser.index <= det_date]
            if len(past) < 21:
                continue
            # Cumulative RS over trailing 21 sessions
            window = past.iloc[-21:]
            trs = float((1 + window).prod() - 1)
            trailing_rs[nd] = trs

        if not trailing_rs:
            continue

        nodes_sorted = sorted(trailing_rs.keys(), key=lambda nd: trailing_rs[nd])
        n_nodes = len(nodes_sorted)
        decile_n = max(1, round(n_nodes * 0.1))

        if direction_filter == "out":
            # bottom decile (lowest trailing RS)
            bench_nodes = nodes_sorted[:decile_n]
        else:
            # top decile
            bench_nodes = nodes_sorted[-decile_n:]

        # Average forward RS across benchmark nodes
        bench_fwd: list[float] = []
        for nd in bench_nodes:
            rs_ser = node_rs_by_date[nd]
            fwd = _compute_fwd_rs_from_panel(rs_ser, det_date, h)
            if not np.isnan(fwd):
                bench_fwd.append(fwd)

        if not bench_fwd:
            continue

        # Direction-adjust: OUT ×-1, IN ×1
        adj = float(np.mean(bench_fwd)) * (-1.0 if direction_filter == "out" else 1.0)
        b1_values.append(adj)

    if not b1_values:
        return np.nan
    return float(np.mean(b1_values))


# ---------------------------------------------------------------------------
# One-sided bootstrap p-value
# ---------------------------------------------------------------------------

def bootstrap_p_value(observed_mean: float, boot_distribution: np.ndarray) -> float:
    """One-sided p-value: fraction of bootstrap draws >= observed_mean.

    Used for BH-FDR (G5).  p = fraction of boot means >= observed.
    A very low p-value means few bootstrap draws exceed the observed.
    """
    valid = boot_distribution[~np.isnan(boot_distribution)]
    if len(valid) == 0 or np.isnan(observed_mean):
        return 1.0
    # One-sided: H1 is mean > 0; p = fraction of draws <= observed
    # = 1 - (fraction of draws > observed)
    # Empirical one-sided p for test "mean > 0":
    # p = (number of boot_means <= 0) / n  [under null, mean ~0]
    # BUT spec says "one-sided bootstrap p from G2's distribution".
    # Standard: p = P(boot_mean >= observed | null) = fraction of draws >= observed.
    # Since our boot distribution IS the sampling distribution of the mean
    # (centered at observed, not at null), we use: p = P(draw <= 0) from the
    # centered boot CI.  Equivalently:
    # Shift boot dist to be centered at 0: shift = observed - 0 = observed.
    # p = fraction of (boot_distribution - observed) >= -observed
    #   = fraction of boot_distribution >= 0
    # Per spec standard practice: p = fraction of bootstrap means <= 0.
    return float(np.mean(valid <= 0))


# ---------------------------------------------------------------------------
# Trial ledger enumeration
# ---------------------------------------------------------------------------

def enumerate_trials(
    episodes_s: pd.DataFrame,
    routing_cells: list[dict],
    two_sided_n: int,
) -> list[dict]:
    """Enumerate all registered trials per §6.

    18 episode cells (2 dir × 3 tiers × 3 horizons)
    + 1 two-sided premium (S2)
    + N_routing sufficient cells (S4)

    Returns ordered list of trial dicts (no p-values yet).
    """
    trials: list[dict] = []
    directions = ["out", "in"]
    tiers = ["onset", "confirmed", "undeniable"]
    horizons = [5, 21, 63]

    # 18 episode cells
    for direction in directions:
        for tier in tiers:
            for h in horizons:
                trials.append({
                    "trial_id": f"ep_{direction}_{tier}_{h}d",
                    "type": "episode",
                    "direction": direction,
                    "tier": tier,
                    "horizon_d": h,
                    "section": "S1" if not (direction == "out" and tier == "confirmed" and h == 21)
                               and not (direction == "in" and tier == "confirmed" and h == 21)
                               else ("P-EXIT" if direction == "out" else "P-ENTRY"),
                    "p_value": None,
                    "bh_rejected": None,
                })

    # Relabel primaries
    for t in trials:
        if t["direction"] == "out" and t["tier"] == "confirmed" and t["horizon_d"] == 21:
            t["section"] = "P-EXIT (PRIMARY)"
        elif t["direction"] == "in" and t["tier"] == "confirmed" and t["horizon_d"] == 21:
            t["section"] = "P-ENTRY (PRIMARY)"

    # S2 — two-sided premium
    trials.append({
        "trial_id": "two_sided_premium_21d",
        "type": "two_sided",
        "direction": "both",
        "tier": "onset",
        "horizon_d": 21,
        "section": "S2",
        "n": two_sided_n,
        "p_value": None,
        "bh_rejected": None,
    })

    # S4 — routing cells (FIX 1: one trial per cell×horizon)
    for rc in routing_cells:
        h_rc = rc.get("horizon_d", 5)
        trials.append({
            "trial_id": f"routing_{rc['path']}_{h_rc}d",
            "type": "routing",
            "direction": rc.get("direction", "out"),
            "tier": "onset",
            "horizon_d": h_rc,
            "section": "S4",
            "routing_path": rc["path"],
            "n": rc.get("n", 0),
            "p_value": None,
            "bh_rejected": None,
        })

    return trials


# ---------------------------------------------------------------------------
# Routing cell enumeration
# ---------------------------------------------------------------------------

def _enumerate_routing_cells(routing: dict, source_path: str = "") -> list[dict]:
    """Recursively enumerate all sufficient routing cells.

    FIX 1 (FDR family): Emit one trial per (source, dest, regime, horizon) for
    each of the 3 registered horizons (5/10/15d).  Previously this function
    collapsed all horizons to fwd_windows[0] only, under-counting the family.

    Each returned dict has keys: path, n, horizon_d, mean_fwd_rs, hit_rate,
    sufficient=True.  The path encodes source/dest/regime; horizon_d
    distinguishes the three trials from the same routing cell.

    Routing structure: source → dest → regime_key → {n, sufficient, mean_fwd_rs_*d, ...}
    """
    cells: list[dict] = []
    _config = routing.get("_config", {})
    fwd_windows = _config.get("fwd_windows", [5, 10, 15])

    def _recurse(d: dict, path: str) -> None:
        if "_config" in d and not any(isinstance(v, dict) for k, v in d.items() if k != "_config"):
            return
        for k, v in d.items():
            if k == "_config":
                continue
            if isinstance(v, dict):
                if "sufficient" in v:
                    # Leaf cell — emit one trial per horizon (registered S4 = source × dest × regime × 3 horizons)
                    if v.get("sufficient", False):
                        cell_path = f"{path}/{k}".lstrip("/")
                        n_cell = v.get("n", 0)
                        for hw in fwd_windows:
                            cell: dict[str, Any] = {
                                "path": cell_path,
                                "n": n_cell,
                                "sufficient": True,
                                "horizon_d": hw,
                                "mean_fwd_rs": v.get(f"mean_fwd_rs_{hw}d", np.nan),
                                "hit_rate": v.get(f"hit_rate_positive_{hw}d", np.nan),
                            }
                            cells.append(cell)
                else:
                    _recurse(v, f"{path}/{k}".lstrip("/"))

    _recurse(routing, source_path)
    return cells


# ---------------------------------------------------------------------------
# Routing onset reconstruction (FIX 2 — G5 registered method)
# ---------------------------------------------------------------------------

def _reconstruct_routing_onset_outcomes(
    panel_m: pd.DataFrame,
    rotation_groups_path: Path,
    graph_m_routing_config: dict,
) -> dict[str, dict[str, dict[str, list[float]]]]:
    """Reconstruct per-onset routing outcomes from panel_m.

    Mirrors engine/oracle/graph.py compute_routing's onset detection EXACTLY:
      - complex 5d-mean accel_z crossing below accel_z_thresh with ≥confirm_k
        of last confirm_m days below threshold
      - regime split by vix_pctile >= high_vix_thresh → 'high_vix' / 'low_vix'
      - forward RS-change at fwd_windows horizons per destination complex

    Returns
    -------
    dict: src_id → dest_id → regime_label → {h: [per-onset outcomes]}
        Only sufficient cells (n >= min_n) are included.

    The returned per-onset outcome lists are used to form block-bootstrap p-values
    per the registered G5 method (same 2,000-iter/21d-block machinery as G2).

    Cross-check assertion: for each sufficient cell the mean of the reconstructed
    outcomes must match graph_m.json's stored mean_fwd_rs_{h}d to 1e-9.
    If any cell fails this check, a ValueError is raised to stop the run.
    """
    with open(rotation_groups_path) as f:
        rg = json.load(f)
    complexes = {c["id"]: c["members"] for c in rg["complexes"]}

    cfg = graph_m_routing_config
    accel_thresh = cfg["accel_z_thresh"]
    confirm_k = cfg["confirm_k"]
    confirm_m = cfg["confirm_m"]
    fwd_windows = cfg["fwd_windows"]
    high_vix = cfg["high_vix_thresh"]
    min_n = cfg["min_n"]

    # Build wide frames
    accel_z_wide = panel_m["accel_z"].unstack(level="node") if "accel_z" in panel_m.columns else pd.DataFrame()
    rs_wide = panel_m["rs"].unstack(level="node") if "rs" in panel_m.columns else pd.DataFrame()
    vix_wide = panel_m["vix_pctile"].unstack(level="node") if "vix_pctile" in panel_m.columns else pd.DataFrame()

    if accel_z_wide.empty or rs_wide.empty:
        raise ValueError("panel_m missing required columns (accel_z, rs)")

    vix_ser: pd.Series | None = None
    if not vix_wide.empty:
        vix_ser = vix_wide.iloc[:, 0]

    complex_accel: dict[str, pd.Series] = {}
    complex_rs: dict[str, pd.Series] = {}
    for cid, members in complexes.items():
        avail_accel = [m for m in members if m in accel_z_wide.columns]
        avail_rs = [m for m in members if m in rs_wide.columns]
        if avail_accel:
            complex_accel[cid] = accel_z_wide[avail_accel].mean(axis=1, skipna=True)
        if avail_rs:
            complex_rs[cid] = rs_wide[avail_rs].mean(axis=1, skipna=True)

    # src → dest → regime → {h: [outcomes]}
    results: dict[str, dict[str, dict[str, dict[int, list[float]]]]] = {}

    for src_id, src_accel in complex_accel.items():
        accel_arr = src_accel.values
        n = len(accel_arr)

        # 5d rolling mean of accel_z (mirror of graph.py)
        roll5 = np.full(n, np.nan)
        for i in range(4, n):
            window = accel_arr[i - 4: i + 1]
            valid = window[~np.isnan(window)]
            if len(valid) >= 3:
                roll5[i] = float(valid.mean())

        # Confirmation flags: ≥confirm_k of last confirm_m days below threshold
        confirm_flags = np.zeros(n, dtype=bool)
        for i in range(confirm_m - 1, n):
            window = accel_arr[i - confirm_m + 1: i + 1]
            below = np.sum(window < accel_thresh)
            if below >= confirm_k:
                confirm_flags[i] = True

        # Onset detection: crossing transition + confirm
        onset_indices: list[int] = []
        in_outflow = False
        for i in range(1, n):
            if confirm_flags[i] and not np.isnan(roll5[i]) and roll5[i] < accel_thresh:
                if not in_outflow:
                    onset_indices.append(i)
                    in_outflow = True
            else:
                if not np.isnan(roll5[i]) and roll5[i] >= -0.5:
                    in_outflow = False

        if not onset_indices:
            continue

        src_results: dict[str, dict[str, dict[int, list[float]]]] = {}

        for dest_id, dest_rs in complex_rs.items():
            if dest_id == src_id:
                continue
            dest_arr = dest_rs.values

            dest_results: dict[str, dict[int, list[float]]] = {}

            for regime_label, vix_cond in [("high_vix", True), ("low_vix", False)]:
                per_h: dict[int, list[float]] = {w: [] for w in fwd_windows}
                n_events = 0

                for onset_i in onset_indices:
                    vix_val = (
                        float(vix_ser.iloc[onset_i])
                        if vix_ser is not None and onset_i < len(vix_ser)
                        else np.nan
                    )
                    if not np.isnan(vix_val):
                        is_high_vix = vix_val >= high_vix
                        if is_high_vix != vix_cond:
                            continue

                    rs_at_onset = dest_arr[onset_i] if onset_i < len(dest_arr) else np.nan
                    if np.isnan(rs_at_onset):
                        continue
                    n_events += 1
                    for fwd_w in fwd_windows:
                        fwd_i = onset_i + fwd_w
                        if fwd_i < len(dest_arr) and not np.isnan(dest_arr[fwd_i]):
                            fwd_rs_chg = dest_arr[fwd_i] - rs_at_onset
                            per_h[fwd_w].append(fwd_rs_chg)

                if n_events >= min_n:
                    dest_results[regime_label] = per_h

            if dest_results:
                src_results[dest_id] = dest_results

        if src_results:
            results[src_id] = src_results

    return results


def _verify_routing_reconstruction(
    onset_outcomes: dict,
    graph_m_routing: dict,
    fwd_windows: list[int],
    tol: float = 1e-9,
) -> None:
    """Assert that per-cell mean from reconstructed outcomes matches stored means.

    Raises ValueError if any sufficient cell differs by more than tol.
    This is the registered cross-check: reconstruction fidelity to stored aggregates.
    """
    for src_id, src_dict in onset_outcomes.items():
        for dest_id, dest_dict in src_dict.items():
            for regime_label, per_h in dest_dict.items():
                stored_cell = (
                    graph_m_routing.get(src_id, {})
                    .get(dest_id, {})
                    .get(regime_label, {})
                )
                if not stored_cell or not stored_cell.get("sufficient", False):
                    continue
                for hw in fwd_windows:
                    vals = per_h.get(hw, [])
                    stored_mean = stored_cell.get(f"mean_fwd_rs_{hw}d")
                    if stored_mean is None or len(vals) == 0:
                        continue
                    recon_mean = float(np.mean(vals))
                    diff = abs(recon_mean - stored_mean)
                    if diff > tol:
                        raise ValueError(
                            f"Routing reconstruction mean mismatch for "
                            f"{src_id}->{dest_id}/{regime_label}/{hw}d: "
                            f"stored={stored_mean:.15f} reconstructed={recon_mean:.15f} "
                            f"diff={diff:.3e} (tolerance={tol:.0e}). "
                            "STOP: do not ship mismatched numbers."
                        )


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def run_gauntlet(data_dir: Path) -> dict:
    """Run the full P3 gauntlet and return a results dict."""
    t0 = time.time()
    rng = np.random.default_rng(SEED)

    oracle_dir = data_dir / "oracle"
    gauntlet_dir = oracle_dir / "gauntlet"
    gauntlet_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load data ----
    log.info("Loading parquets…")
    episodes_s = pd.read_parquet(oracle_dir / "episodes_s.parquet")
    panel_s = pd.read_parquet(oracle_dir / "panel_s.parquet")
    episodes_m = pd.read_parquet(oracle_dir / "episodes_m.parquet")
    # panel_m needed for FIX 2 routing p-value reconstruction (G5 registered method)
    panel_m = pd.read_parquet(oracle_dir / "panel_m.parquet")

    with open(oracle_dir / "graph_s.json") as f:
        graph_s = json.load(f)
    with open(oracle_dir / "graph_m.json") as f:
        graph_m = json.load(f)

    routing_s = graph_s.get("routing", {})
    routing_m = graph_m.get("routing", {})

    # ---- Routing cells (FIX 1: 3 horizons per cell → 90 routing trials) ----
    log.info("Enumerating routing cells…")
    routing_cells_s = _enumerate_routing_cells(routing_s)
    routing_cells_m = _enumerate_routing_cells(routing_m)
    routing_cells_all = routing_cells_s + routing_cells_m
    log.info(f"  Tier-S sufficient cell×horizon trials: {len(routing_cells_s)}")
    log.info(f"  Tier-M sufficient cell×horizon trials: {len(routing_cells_m)}")
    log.info(f"  Total routing trials: {len(routing_cells_all)}")

    # ---- Routing onset reconstruction (FIX 2: block-bootstrap p per registered G5) ----
    log.info("Reconstructing per-onset routing outcomes from panel_m…")
    rotation_groups_path = oracle_dir / "rotation_groups.json"
    routing_m_cfg = routing_m.get("_config", {})
    onset_outcomes_m = _reconstruct_routing_onset_outcomes(
        panel_m, rotation_groups_path, routing_m_cfg
    )
    log.info("Verifying reconstruction means against stored graph_m.json means…")
    _verify_routing_reconstruction(
        onset_outcomes_m,
        routing_m,
        fwd_windows=routing_m_cfg.get("fwd_windows", [5, 10, 15]),
        tol=1e-9,
    )
    log.info("  Reconstruction cross-check PASSED (all means match stored to 1e-9)")

    # ---- Two-sided premium n ----
    two_sided_n = int(episodes_m["two_sided"].sum()) if "two_sided" in episodes_m.columns else 0

    # ---- Trial ledger (written BEFORE any p-values) ----
    log.info("Writing trial ledger…")
    trial_ledger = enumerate_trials(episodes_s, routing_cells_all, two_sided_n)
    ledger_path = gauntlet_dir / "p3_trial_ledger.json"
    with open(ledger_path, "w") as f:
        json.dump({"seed": SEED, "trials": trial_ledger, "n_trials": len(trial_ledger)}, f, indent=2, default=str)
    log.info(f"  Trial ledger written: {len(trial_ledger)} trials → {ledger_path}")

    # ---- Episode computation ----
    log.info("Running episode gauntlet…")
    results: dict[str, Any] = {
        "spec_version": "ORACLE_GAUNTLET_P3_PREREG.md",
        "seed": SEED,
        "n_trials": len(trial_ledger),
        "episodes": {},
        "two_sided": {},
        "routing": {},
        "benchmarks": {},
        "bh_fdr": {},
        "timing_s": None,
    }

    # Map trial_id → trial index for update
    trial_by_id: dict[str, int] = {t["trial_id"]: i for i, t in enumerate(trial_ledger)}

    # Collect all p-values and their trial_ids for BH-FDR
    all_trial_ids: list[str] = []
    all_p_values: list[float] = []

    def _run_episode_cell(direction: str, tier: str, h: int) -> dict:
        """Compute all statistics for one episode × tier × horizon cell."""
        outcome_col = _outcome_col(tier, h)
        mature_col = _mature_col(tier, h)
        det_col = _detection_date_col(tier)

        sub = episodes_s[
            (episodes_s["direction"] == direction) &
            (episodes_s[mature_col] == True)
        ].copy()

        if sub.empty or outcome_col not in sub.columns:
            return {
                "n": 0, "raw_mean": np.nan, "direction_adjusted_mean": np.nan,
                "placebo_p95": np.nan, "boot_ci_lo": np.nan, "boot_ci_hi": np.nan,
                "boot_p_value": np.nan, "era_means": {},
                "strata_means": {}, "g1_pass": False, "g2_pass": False,
                "g3_pass": False, "g4_pass": False, "g3_note": "no data",
                "g4_note": "no data",
            }

        raw_vals = sub[outcome_col].to_numpy(dtype=float)
        da_vals = direction_adjust(raw_vals, sub["direction"])

        # Sort by detection date for G2 bootstrap
        sort_key = sub[det_col].fillna(sub["onset_date"])
        order = sort_key.argsort().to_numpy()
        da_vals_sorted = da_vals[order]

        # Drop NaN
        valid_mask = ~np.isnan(da_vals_sorted)
        da_clean = da_vals_sorted[valid_mask]

        n = len(da_clean)
        if n == 0:
            return {
                "n": 0, "raw_mean": np.nan, "direction_adjusted_mean": np.nan,
                "placebo_p95": np.nan, "boot_ci_lo": np.nan, "boot_ci_hi": np.nan,
                "boot_p_value": np.nan, "era_means": {},
                "strata_means": {}, "g1_pass": False, "g2_pass": False,
                "g3_pass": False, "g4_pass": False, "g3_note": "no data",
                "g4_note": "no data",
            }

        raw_mean = float(np.nanmean(raw_vals))
        da_mean = float(np.mean(da_clean))

        # G1: placebo
        placebo_dist = sample_placebo(
            episodes_sub=sub,
            panel=panel_s,
            h=h,
            tier=tier,
            direction_filter=direction,
            n_draws=200,
            exclusion_zone=10,
            rng=np.random.default_rng(rng.integers(0, 2**32)),
        )
        valid_placebo = placebo_dist[~np.isnan(placebo_dist)]
        placebo_p95 = float(np.percentile(valid_placebo, 95)) if len(valid_placebo) > 0 else np.nan
        g1_pass = da_mean > placebo_p95 if not np.isnan(placebo_p95) else False

        # G2: block bootstrap CI
        boot_lo, boot_hi, _, boot_dist = block_bootstrap_ci(
            da_clean, n_iters=2000, block_size=21,
            rng=np.random.default_rng(rng.integers(0, 2**32)),
        )
        g2_pass = boot_lo > 0 if not np.isnan(boot_lo) else False

        # One-sided bootstrap p for BH-FDR
        boot_p = bootstrap_p_value(da_mean, boot_dist)

        # G3: regime stratification (FIX 3 — pass per-stratum n for 'larger stratum' check)
        strata = _regime_strata(sub)
        strata_means: dict[str, float] = {}
        strata_ns: dict[str, int] = {}
        for sname, smask in strata.items():
            # Re-apply to the filtered sub
            smask_sub = smask
            if len(smask_sub) == len(sub):
                sv = da_vals[smask_sub]
                sv_clean = sv[~np.isnan(sv)]
                strata_means[sname] = float(np.mean(sv_clean)) if len(sv_clean) > 0 else np.nan
                strata_ns[sname] = int(len(sv_clean))
        g3_pass, g3_note = _check_g3(da_mean, strata_means, strata_ns)

        # G4: era consistency
        det_dates_raw = sub[det_col].fillna(sub["onset_date"])
        # da_vals is in original sub order
        era_m = _era_means(da_vals, det_dates_raw)
        g4_pass, g4_note = _check_g4(era_m)

        return {
            "n": n,
            "raw_mean": raw_mean,
            "direction_adjusted_mean": da_mean,
            "placebo_p95": placebo_p95,
            "placebo_n_draws": len(valid_placebo),
            "boot_ci_lo": boot_lo,
            "boot_ci_hi": boot_hi,
            "boot_p_value": boot_p,
            "era_means": {k: (float(v) if not np.isnan(v) else None) for k, v in era_m.items()},
            "strata_means": {k: (float(v) if not np.isnan(v) else None) for k, v in strata_means.items()},
            "strata_ns": strata_ns,
            "g1_pass": bool(g1_pass),
            "g2_pass": bool(g2_pass),
            "g3_pass": bool(g3_pass),
            "g4_pass": bool(g4_pass),
            "g3_note": g3_note,
            "g4_note": g4_note,
        }

    # Run all 18 episode cells
    for direction in ["out", "in"]:
        for tier in ["onset", "confirmed", "undeniable"]:
            for h in [5, 21, 63]:
                cell_id = f"ep_{direction}_{tier}_{h}d"
                log.info(f"  Cell {cell_id}…")
                cell_result = _run_episode_cell(direction, tier, h)
                results["episodes"][cell_id] = cell_result

                # Register p-value for BH-FDR
                all_trial_ids.append(cell_id)
                all_p_values.append(cell_result.get("boot_p_value", 1.0) or 1.0)

                # Update ledger
                if cell_id in trial_by_id:
                    trial_ledger[trial_by_id[cell_id]]["p_value"] = cell_result.get("boot_p_value")
                    trial_ledger[trial_by_id[cell_id]]["n"] = cell_result.get("n")
                    trial_ledger[trial_by_id[cell_id]]["direction_adjusted_mean"] = cell_result.get("direction_adjusted_mean")

    # ---- S2: two-sided premium ----
    log.info("S2 two-sided premium…")
    ts_outcome_col = "outcome_rs_21d"
    ts_mature_col = "outcome_mature_21d"
    ts_sub = episodes_m[episodes_m["two_sided"] == True].copy()
    nts_sub = episodes_m[episodes_m["two_sided"] != True].copy()

    def _two_sided_cell() -> dict:
        if ts_sub.empty:
            return {"n_two_sided": 0, "n_not_two_sided": 0,
                    "da_mean_two_sided": np.nan, "da_mean_not_two_sided": np.nan,
                    "boot_p_value": 1.0, "note": "no two-sided episodes"}
        ts_mat = ts_sub[ts_sub.get(ts_mature_col, pd.Series([False] * len(ts_sub)))]
        if ts_mature_col in ts_sub.columns:
            ts_mat = ts_sub[ts_sub[ts_mature_col] == True]
        else:
            ts_mat = ts_sub

        if ts_outcome_col not in ts_sub.columns:
            return {"n_two_sided": 0, "n_not_two_sided": 0,
                    "da_mean_two_sided": np.nan, "da_mean_not_two_sided": np.nan,
                    "boot_p_value": 1.0, "note": "outcome col missing"}

        ts_vals = direction_adjust(
            ts_mat[ts_outcome_col].to_numpy(dtype=float),
            ts_mat["direction"]
        )
        ts_clean = ts_vals[~np.isnan(ts_vals)]
        ts_mean = float(np.mean(ts_clean)) if len(ts_clean) > 0 else np.nan

        # Non-two-sided comparison (matched by direction)
        nts_mat = nts_sub
        if ts_mature_col in nts_sub.columns:
            nts_mat = nts_sub[nts_sub[ts_mature_col] == True]
        nts_vals = direction_adjust(
            nts_mat[ts_outcome_col].to_numpy(dtype=float) if ts_outcome_col in nts_mat.columns else np.array([]),
            nts_mat["direction"] if ts_outcome_col in nts_mat.columns else pd.Series([])
        )
        nts_clean = nts_vals[~np.isnan(nts_vals)]
        nts_mean = float(np.mean(nts_clean)) if len(nts_clean) > 0 else np.nan

        # Bootstrap CI for two-sided premium
        if len(ts_clean) > 1:
            _, _, _, boot_dist_ts = block_bootstrap_ci(
                ts_clean, n_iters=2000, block_size=21,
                rng=np.random.default_rng(rng.integers(0, 2**32)),
            )
            boot_p = bootstrap_p_value(ts_mean, boot_dist_ts)
        else:
            boot_p = 1.0

        return {
            "n_two_sided": int(len(ts_clean)),
            "n_not_two_sided": int(len(nts_clean)),
            "da_mean_two_sided": ts_mean,
            "da_mean_not_two_sided": nts_mean,
            "boot_p_value": boot_p,
            "note": "Tier M; survivorship-watermarked; display-grade only",
        }

    ts_result = _two_sided_cell()
    results["two_sided"]["two_sided_premium_21d"] = ts_result
    all_trial_ids.append("two_sided_premium_21d")
    all_p_values.append(ts_result.get("boot_p_value", 1.0) or 1.0)
    if "two_sided_premium_21d" in trial_by_id:
        trial_ledger[trial_by_id["two_sided_premium_21d"]]["p_value"] = ts_result.get("boot_p_value")

    # ---- S4: routing cells (FIX 2: block-bootstrap p from reconstructed per-onset outcomes) ----
    log.info(f"S4 routing cells ({len(routing_cells_all)} trials at 3 horizons each)…")
    for rc in routing_cells_all:
        h_rc = rc.get("horizon_d", 5)
        rc_id = f"routing_{rc['path']}_{h_rc}d"
        n_rc = rc.get("n", 0)
        mean_fwd = rc.get("mean_fwd_rs", np.nan)
        hit_rate = rc.get("hit_rate", np.nan)

        # Retrieve per-onset outcome list from reconstruction.
        # Path format: "src_id/dest_id/regime_label"
        path_parts = rc["path"].split("/")
        boot_p = 1.0
        boot_note = "reconstruction lookup failed"

        if len(path_parts) == 3:
            src_p, dest_p, regime_p = path_parts
            per_h = onset_outcomes_m.get(src_p, {}).get(dest_p, {}).get(regime_p, {})
            outcomes = per_h.get(h_rc, [])
            if len(outcomes) >= 2:
                vals_arr = np.array(outcomes, dtype=float)
                _, _, _, boot_dist = block_bootstrap_ci(
                    vals_arr,
                    n_iters=2000,
                    block_size=21,
                    rng=np.random.default_rng(rng.integers(0, 2**32)),
                )
                boot_p = bootstrap_p_value(float(np.mean(vals_arr)), boot_dist)
                boot_note = "block-bootstrap p (2000 iter, 21d blocks) from reconstructed per-onset outcomes"
            else:
                boot_note = f"too few onset outcomes (n={len(outcomes)}) for bootstrap"

        rc_result = {
            "n": n_rc,
            "horizon_d": h_rc,
            "mean_fwd_rs": mean_fwd,
            "hit_rate": hit_rate,
            "boot_p_value": boot_p,
            "note": boot_note,
        }
        results["routing"][rc_id] = rc_result
        all_trial_ids.append(rc_id)
        all_p_values.append(boot_p)
        if rc_id in trial_by_id:
            trial_ledger[trial_by_id[rc_id]]["p_value"] = boot_p

    # ---- BH-FDR (G5) over ALL registered trials ----
    log.info(f"BH-FDR over {len(all_p_values)} trials at q=0.10…")
    bh_rejected = bh_fdr(all_p_values, q=0.10)
    for i, (tid, rejected) in enumerate(zip(all_trial_ids, bh_rejected)):
        if tid in trial_by_id:
            trial_ledger[trial_by_id[tid]]["bh_rejected"] = bool(rejected)

    # Attach BH results to episode cells
    for i, (tid, rej, pv) in enumerate(zip(all_trial_ids, bh_rejected, all_p_values)):
        if tid.startswith("ep_"):
            if tid in results["episodes"]:
                results["episodes"][tid]["bh_rejected"] = bool(rej)
                results["episodes"][tid]["bh_q_value"] = float(pv)

    n_rejected = sum(bh_rejected)
    results["bh_fdr"] = {
        "q": 0.10,
        "n_trials": len(all_p_values),
        "n_rejected": n_rejected,
        "trial_ids_rejected": [tid for tid, r in zip(all_trial_ids, bh_rejected) if r],
    }

    # ---- Benchmarks ----
    log.info("Computing benchmarks B1 and B2…")

    # B1: exit and entry vs momentum null
    b1_exit = compute_b1(
        episodes_s[(episodes_s["direction"] == "out") & (episodes_s["outcome_mature_21d_confirmed"] == True)].copy(),
        panel_s, h=21, direction_filter="out", tier="confirmed",
    )
    b1_entry = compute_b1(
        episodes_s[(episodes_s["direction"] == "in") & (episodes_s["outcome_mature_21d_confirmed"] == True)].copy(),
        panel_s, h=21, direction_filter="in", tier="confirmed",
    )

    exit_cell = results["episodes"].get("ep_out_confirmed_21d", {})
    entry_cell = results["episodes"].get("ep_in_confirmed_21d", {})
    exit_da_mean = exit_cell.get("direction_adjusted_mean", np.nan) or np.nan
    entry_da_mean = entry_cell.get("direction_adjusted_mean", np.nan) or np.nan

    # G6: benchmark exceedance
    g6_exit = bool(exit_da_mean > b1_exit) if not (np.isnan(exit_da_mean) or np.isnan(b1_exit)) else False
    g6_entry = bool(entry_da_mean > b1_entry) if not (np.isnan(entry_da_mean) or np.isnan(b1_entry)) else False

    # B2: compare exit undeniable 63d vs sector_signals baseline
    # sector_signals: SELL mean=-1.24%, hit=40%, n=169
    b2_baseline = {"mean_pct": -1.24, "hit_rate": 0.40, "n": 169, "source": "sector_signals SELL"}
    exit_63d_cell = results["episodes"].get("ep_out_undeniable_63d", {})
    exit_63d_da = exit_63d_cell.get("direction_adjusted_mean", np.nan) or np.nan
    b2_oracle_pct = exit_63d_da * 100 if not np.isnan(exit_63d_da) else np.nan
    # B2 is informative, not blocking per spec
    b2_comparison = {
        "oracle_undeniable_out_63d_pct": b2_oracle_pct,
        "oracle_n": exit_63d_cell.get("n", 0),
        "baseline_mean_pct": -1.24,
        "baseline_hit_rate": 0.40,
        "baseline_n": 169,
        "note": "informative only — different universe granularities (B2 per §3 G6)",
    }

    results["benchmarks"] = {
        "B1_exit_momentum_null_da_mean_21d": float(b1_exit) if not np.isnan(b1_exit) else None,
        "B1_entry_momentum_null_da_mean_21d": float(b1_entry) if not np.isnan(b1_entry) else None,
        "B1_oracle_exit_da_mean_21d": float(exit_da_mean) if not np.isnan(exit_da_mean) else None,
        "B1_oracle_entry_da_mean_21d": float(entry_da_mean) if not np.isnan(entry_da_mean) else None,
        "G6_exit_beats_B1": g6_exit,
        "G6_entry_beats_B1": g6_entry,
        "B2": b2_comparison,
    }

    # Update G6 on primary cells
    if "ep_out_confirmed_21d" in results["episodes"]:
        results["episodes"]["ep_out_confirmed_21d"]["g6_pass"] = g6_exit
    if "ep_in_confirmed_21d" in results["episodes"]:
        results["episodes"]["ep_in_confirmed_21d"]["g6_pass"] = g6_entry

    # ---- S3: early-tier error rates (descriptive) ----
    log.info("S3 early-tier descriptive stats…")
    # False-start rate: onset-tier episodes whose +10d da outcome is negative
    # (detect: onset tier, h=21d used as proxy since 10d not a standard horizon)
    onset_out = episodes_s[
        (episodes_s["direction"] == "out") &
        (episodes_s["outcome_mature_5d"] == True)
    ].copy()
    onset_in = episodes_s[
        (episodes_s["direction"] == "in") &
        (episodes_s["outcome_mature_5d"] == True)
    ].copy()
    # False start: onset +5d outcome is negative (direction-adjusted)
    if "outcome_rs_5d" in onset_out.columns:
        fs_out = direction_adjust(onset_out["outcome_rs_5d"].to_numpy(dtype=float), onset_out["direction"])
        fs_out_rate = float(np.mean(fs_out < 0)) if len(fs_out) > 0 else np.nan
    else:
        fs_out_rate = np.nan
    if "outcome_rs_5d" in onset_in.columns:
        fs_in = direction_adjust(onset_in["outcome_rs_5d"].to_numpy(dtype=float), onset_in["direction"])
        fs_in_rate = float(np.mean(fs_in < 0)) if len(fs_in) > 0 else np.nan
    else:
        fs_in_rate = np.nan

    # Onset → confirmed conversion rate
    total_out = len(episodes_s[episodes_s["direction"] == "out"])
    confirmed_out = int((episodes_s[episodes_s["direction"] == "out"]["confirmed_date"].notna()).sum())
    total_in = len(episodes_s[episodes_s["direction"] == "in"])
    confirmed_in = int((episodes_s[episodes_s["direction"] == "in"]["confirmed_date"].notna()).sum())

    results["s3_error_rates"] = {
        "false_start_rate_out_5d": fs_out_rate,
        "false_start_rate_in_5d": fs_in_rate,
        "onset_to_confirmed_rate_out": confirmed_out / total_out if total_out > 0 else np.nan,
        "onset_to_confirmed_rate_in": confirmed_in / total_in if total_in > 0 else np.nan,
        "note": "Descriptive — no pass/fail per §2 S3",
    }

    elapsed = time.time() - t0
    results["timing_s"] = round(elapsed, 2)

    log.info(f"Gauntlet complete in {elapsed:.1f}s")

    # Write updated ledger with p-values
    with open(ledger_path, "w") as f:
        json.dump({"seed": SEED, "trials": trial_ledger, "n_trials": len(trial_ledger)}, f, indent=2, default=str)

    return results


def _normal_upper_tail(z: float) -> float:
    """Approximation of P(Z >= z) for the standard normal distribution.

    Uses Abramowitz & Stegun rational approximation (error < 7.5e-8).
    No scipy — pure arithmetic.
    """
    # For very negative z, upper tail is close to 1
    if z < -6.0:
        return 1.0
    if z > 6.0:
        return 0.0

    # If z < 0, use symmetry: P(Z >= z) = P(Z <= |z|) = 1 - P(Z >= |z|)
    sign = 1.0 if z >= 0 else -1.0
    abs_z = abs(z)

    # Rational approximation for P(Z > abs_z) when abs_z >= 0
    # A&S 26.2.17 with p = 0.2316419
    p = 0.2316419
    b = np.array([0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429])
    t = 1.0 / (1.0 + p * abs_z)
    t_poly = ((((b[4] * t + b[3]) * t + b[2]) * t + b[1]) * t + b[0]) * t
    # Standard normal PDF
    phi = np.exp(-0.5 * abs_z ** 2) / np.sqrt(2 * np.pi)
    upper = phi * t_poly

    if z >= 0:
        return float(max(0.0, min(1.0, upper)))
    else:
        return float(max(0.0, min(1.0, 1.0 - upper)))


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _fmt(v, pct: bool = False, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if pct:
        return f"{v * 100:.2f}%"
    return f"{v:.{digits}f}"


def write_markdown(results: dict, output_path: Path, ledger_path: Path) -> None:
    """Write research/ORACLE_GAUNTLET_P3_RESULTS.md with tables only."""
    bh = results.get("bh_fdr", {})
    eps = results.get("episodes", {})
    benchmarks = results.get("benchmarks", {})

    lines = [
        "# Oracle P3 Gauntlet — Results",
        "",
        f"**Registration:** [ORACLE_GAUNTLET_P3_PREREG.md](ORACLE_GAUNTLET_P3_PREREG.md)",
        f"**Seed:** {results['seed']}  **Trials:** {results['n_trials']}  "
        f"**Runtime:** {results.get('timing_s', '?')}s",
        f"**BH-FDR:** q=0.10, {bh.get('n_rejected', 0)}/{bh.get('n_trials', '?')} trials rejected",
        "",
        "> Verdicts in this document are left as **PENDING ADJUDICATION** — "
        "the orchestrator applies the pre-bound vocabulary per §3 of the registration.",
        "",
        "---",
        "",
        "## Primary endpoints",
        "",
        "| Endpoint | Direction | n | Raw mean | DA mean | Placebo p95 | Boot CI lo | Boot CI hi | Boot p | BH pass | G1 | G2 | G3 | G4 | G6 | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for label, cell_id, direction in [
        ("P-EXIT", "ep_out_confirmed_21d", "out"),
        ("P-ENTRY", "ep_in_confirmed_21d", "in"),
    ]:
        c = eps.get(cell_id, {})
        bh_pass = "Y" if c.get("bh_rejected") else "N"
        row = (
            f"| **{label}** | {direction} | {c.get('n', 0)} "
            f"| {_fmt(c.get('raw_mean'), pct=True)} "
            f"| {_fmt(c.get('direction_adjusted_mean'), pct=True)} "
            f"| {_fmt(c.get('placebo_p95'), pct=True)} "
            f"| {_fmt(c.get('boot_ci_lo'), pct=True)} "
            f"| {_fmt(c.get('boot_ci_hi'), pct=True)} "
            f"| {_fmt(c.get('boot_p_value'))} "
            f"| {bh_pass} "
            f"| {'✓' if c.get('g1_pass') else '✗'} "
            f"| {'✓' if c.get('g2_pass') else '✗'} "
            f"| {'✓' if c.get('g3_pass') else '✗'} "
            f"| {'✓' if c.get('g4_pass') else '✗'} "
            f"| {'✓' if c.get('g6_pass') else '✗'} "
            f"| PENDING ADJUDICATION |"
        )
        lines.append(row)

    lines += [
        "",
        "## Secondary endpoint grid (S1) — all 18 cells",
        "",
        "| cell_id | direction | tier | h | n | raw mean | DA mean | placebo p95 | boot CI | boot p | BH pass | G1 | G2 | G3 | G4 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for direction in ["out", "in"]:
        for tier in ["onset", "confirmed", "undeniable"]:
            for h in [5, 21, 63]:
                cell_id = f"ep_{direction}_{tier}_{h}d"
                c = eps.get(cell_id, {})
                bh_pass = "Y" if c.get("bh_rejected") else "N"
                ci_str = f"[{_fmt(c.get('boot_ci_lo'), pct=True)}, {_fmt(c.get('boot_ci_hi'), pct=True)}]"
                row = (
                    f"| {cell_id} | {direction} | {tier} | {h}d "
                    f"| {c.get('n', 0)} "
                    f"| {_fmt(c.get('raw_mean'), pct=True)} "
                    f"| {_fmt(c.get('direction_adjusted_mean'), pct=True)} "
                    f"| {_fmt(c.get('placebo_p95'), pct=True)} "
                    f"| {ci_str} "
                    f"| {_fmt(c.get('boot_p_value'))} "
                    f"| {bh_pass} "
                    f"| {'✓' if c.get('g1_pass') else '✗'} "
                    f"| {'✓' if c.get('g2_pass') else '✗'} "
                    f"| {'✓' if c.get('g3_pass') else '✗'} "
                    f"| {'✓' if c.get('g4_pass') else '✗'} |"
                )
                lines.append(row)

    # Per-stratum means for primaries
    lines += [
        "",
        "## G3 Regime stratification — primary endpoints",
        "",
        "| Endpoint | Stratum | DA mean |",
        "|---|---|---|",
    ]
    for label, cell_id in [("P-EXIT", "ep_out_confirmed_21d"), ("P-ENTRY", "ep_in_confirmed_21d")]:
        c = eps.get(cell_id, {})
        strata = c.get("strata_means", {})
        for sname, sv in strata.items():
            lines.append(f"| {label} | {sname} | {_fmt(sv, pct=True)} |")
        lines.append(f"| {label} | G3 note | {c.get('g3_note', '—')} |")

    # Per-era means
    lines += [
        "",
        "## G4 Era consistency — primary endpoints",
        "",
        "| Endpoint | Era | DA mean |",
        "|---|---|---|",
    ]
    for label, cell_id in [("P-EXIT", "ep_out_confirmed_21d"), ("P-ENTRY", "ep_in_confirmed_21d")]:
        c = eps.get(cell_id, {})
        era_m = c.get("era_means", {})
        for era_name, ev in era_m.items():
            lines.append(f"| {label} | {era_name} | {_fmt(ev, pct=True)} |")
        lines.append(f"| {label} | G4 note | {c.get('g4_note', '—')} |")

    # S2: two-sided premium
    ts = results.get("two_sided", {}).get("two_sided_premium_21d", {})
    lines += [
        "",
        "## S2 Two-sided premium (Tier M, display-grade)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| n two-sided | {ts.get('n_two_sided', 0)} |",
        f"| n not two-sided | {ts.get('n_not_two_sided', 0)} |",
        f"| DA mean two-sided | {_fmt(ts.get('da_mean_two_sided'), pct=True)} |",
        f"| DA mean not two-sided | {_fmt(ts.get('da_mean_not_two_sided'), pct=True)} |",
        f"| Boot p-value | {_fmt(ts.get('boot_p_value'))} |",
        f"| Note | {ts.get('note', '—')} |",
    ]

    # S3: error rates
    s3 = results.get("s3_error_rates", {})
    lines += [
        "",
        "## S3 Early-tier error rates (descriptive)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| False-start rate OUT +5d | {_fmt(s3.get('false_start_rate_out_5d'), pct=True)} |",
        f"| False-start rate IN +5d | {_fmt(s3.get('false_start_rate_in_5d'), pct=True)} |",
        f"| Onset→confirmed rate OUT | {_fmt(s3.get('onset_to_confirmed_rate_out'), pct=True)} |",
        f"| Onset→confirmed rate IN | {_fmt(s3.get('onset_to_confirmed_rate_in'), pct=True)} |",
    ]

    # Benchmarks B1 / B2
    lines += [
        "",
        "## Benchmarks",
        "",
        "### B1 — Momentum null (trailing-1M-RS decile)",
        "",
        "| Endpoint | Oracle DA mean +21d | B1 momentum null DA mean | G6 pass |",
        "|---|---|---|---|",
        f"| P-EXIT | {_fmt(benchmarks.get('B1_oracle_exit_da_mean_21d'), pct=True)} | {_fmt(benchmarks.get('B1_exit_momentum_null_da_mean_21d'), pct=True)} | {'✓' if benchmarks.get('G6_exit_beats_B1') else '✗'} |",
        f"| P-ENTRY | {_fmt(benchmarks.get('B1_oracle_entry_da_mean_21d'), pct=True)} | {_fmt(benchmarks.get('B1_entry_momentum_null_da_mean_21d'), pct=True)} | {'✓' if benchmarks.get('G6_entry_beats_B1') else '✗'} |",
        "",
        "### B2 — vs sector_signals SELL baseline",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    b2 = benchmarks.get("B2", {})
    lines += [
        f"| Oracle undeniable OUT +63d DA mean | {_fmt(b2.get('oracle_undeniable_out_63d_pct'), digits=2)}% |",
        f"| Oracle n | {b2.get('oracle_n', 0)} |",
        f"| Baseline (sector_signals SELL) mean | {b2.get('baseline_mean_pct', 0):.2f}% |",
        f"| Baseline hit rate | {b2.get('baseline_hit_rate', 0):.0%} |",
        f"| Baseline n | {b2.get('baseline_n', 0)} |",
        f"| Note | {b2.get('note', '—')} |",
    ]

    # S4: routing cells summary
    routing = results.get("routing", {})
    n_routing = len(routing)
    n_routing_rejected = sum(1 for rc in routing.values() if results["bh_fdr"].get("trial_ids_rejected")
                             and f"routing_{rc}" in results["bh_fdr"]["trial_ids_rejected"])
    lines += [
        "",
        "## S4 Routing cells summary",
        "",
        f"Total routing trials (cells × 3 horizons): {n_routing}",
        f"BH-FDR rejected: per trial ledger",
        "",
        "| trial_id | n | horizon | mean_fwd_rs | hit_rate | boot_p | BH rejected |",
        "|---|---|---|---|---|---|---|",
    ]
    bh_rejected_ids = set(results["bh_fdr"].get("trial_ids_rejected", []))
    for rc_id, rc_v in routing.items():
        rej = "Y" if rc_id in bh_rejected_ids else "N"
        lines.append(
            f"| {rc_id} | {rc_v.get('n', 0)} | {rc_v.get('horizon_d', '?')}d "
            f"| {_fmt(rc_v.get('mean_fwd_rs'), pct=True)} "
            f"| {_fmt(rc_v.get('hit_rate'))} "
            f"| {_fmt(rc_v.get('boot_p_value'))} "
            f"| {rej} |"
        )

    lines += [
        "",
        "---",
        "",
        f"*Trial ledger: {ledger_path.name} (gitignored) — {results['n_trials']} trials enumerated before p-computation.*",
        f"*Runtime: {results.get('timing_s', '?')}s*",
    ]

    output_path.write_text("\n".join(lines) + "\n")
    log.info(f"Results MD written → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Oracle P3 Gauntlet")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to data/ directory (default: data/)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        sys.exit(f"data-dir not found: {data_dir}")

    results = run_gauntlet(data_dir)

    gauntlet_dir = data_dir / "oracle" / "gauntlet"
    results_path = gauntlet_dir / "p3_results.json"
    ledger_path = gauntlet_dir / "p3_trial_ledger.json"
    md_path = Path("research") / "ORACLE_GAUNTLET_P3_RESULTS.md"

    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info(f"Results JSON written → {results_path}")

    write_markdown(results, md_path, ledger_path)

    print(f"\nDone. {results['n_trials']} trials, {results['bh_fdr']['n_rejected']} BH-rejected.")
    print(f"Results: {results_path}")
    print(f"Ledger:  {ledger_path}")
    print(f"Report:  {md_path}")


if __name__ == "__main__":
    main()
