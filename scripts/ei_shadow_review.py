#!/usr/bin/env python3
"""Shadow flip-accounting review job for the F3 Anti-Chase Gate (P2.1a).

Reads the shadow ledger at data/signal_archive/antichase_shadow_ledger.parquet,
joins forward stop-out outcomes from the price store (same sources used by
replay_standout_pipeline.py), and computes the flip-accounting scoreboard
against the pre-registered C1/C2/C3 criteria and rollback triggers RB1/RB2/RB3.

Spec reference: research/entry_intel/P2_1A_ANTICHASE_GATE_PREREG.md §2.2
Species registry: data/species/registry.json (entry: F3_ANTICHASE)

Usage:
    python scripts/ei_shadow_review.py [--out PATH] [--n-bootstrap N]

Output:
    Console report + research/entry_intel/p2_reviews/shadow_review_latest.json

READ-ONLY against all price/ledger stores. The script never writes to
data/signal_archive/ or any other data store — only the JSON report output.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Path bootstrap (mirrors replay_standout_pipeline.py convention) ───────────
SCRIPTS_DIR = Path(__file__).parent
WORKTREE_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(WORKTREE_ROOT))

# ── Import price-store helpers from the replay pipeline ───────────────────────
# These imports are intentionally explicit so the reader can trace exactly which
# functions and constants are borrowed (per species law: entries strictly-after
# asof; split_adjust for raw Massive series).
from scripts.replay_standout_pipeline import (  # noqa: E402
    split_adjust,
    _read_close,
    CANONICAL_DATA,
    MASSIVE_DIR,
)
from engine.grading import (  # noqa: E402
    forward_metrics,
    fill_index,
    STOP_BARRIER,
)

# ── Canonical ledger path (written by build_stock_library Step H) ─────────────
LEDGER_PATH = CANONICAL_DATA / "signal_archive" / "antichase_shadow_ledger.parquet"

# ── Expected ledger schema (per P2.1a Step H) ────────────────────────────────
REQUIRED_COLUMNS = {
    "asof", "ticker", "lane", "ext_z",
    "antichase_shadow_blocked", "flip_eligible", "flip_criteria_met",
    "gate_state", "logged_at",
}

# ── Study horizons (21d and 63d; 63d is the C2 primary criterion) ─────────────
HORIZONS = (21, 63)

# ── Pre-registered flip criteria (P2.1a §2.2) ────────────────────────────────
C1_MIN_CLUSTERS = 100          # minimum independent episode clusters (calendar-week)
C1_MIN_QUARTERS = 2            # minimum calendar quarters elapsed since first ledger row
C2_WILSON_ALPHA = 0.95         # Wilson confidence level
C2_PRIMARY_HORIZON = 63        # 63d is the primary C2 criterion
N_BOOTSTRAP = 1_000            # cluster bootstrap resamples for Wilson bounds

# ── Rollback thresholds (P2.1a §5) ───────────────────────────────────────────
RB1_MIN_CLUSTERS_POSTFLIP = 200   # post-flip clusters needed to trigger RB1
RB2_WEEKLY_FIRE_RATE_PCT = 15.0   # gate blocks > 15% of weekly fires over 4 weeks
RB3_DURABLE_OUTCOME_GAP_PP = 15.0 # blocked durable-60D rate ≥ 15pp above main board

log = logging.getLogger("ei_shadow_review")


# ─────────────────────────────────────────────────────────────────────────────
# 1.  LEDGER LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_and_validate_ledger() -> pd.DataFrame | None:
    """Load the antichase shadow ledger; return None with a clear message if absent/empty.

    Exits with code 0 (not an error — accrual simply hasn't started yet).
    Schema is verified defensively: missing required columns produce a clear message.
    """
    if not LEDGER_PATH.exists():
        _print_banner()
        print("LEDGER STATUS: ABSENT")
        print()
        print(f"Path:    {LEDGER_PATH}")
        print("Reason:  Accrual not started — the shadow ledger is written by")
        print("         build_stock_library Step H on the first nightly build")
        print("         after the P2.1a PR is merged to main.")
        print()
        print("Action:  No action required. Re-run this script after the next")
        print("         nightly build completes (Asia close or US close pipeline).")
        print()
        print("C1 status: 0 / 100 clusters  |  0 / 2 quarters")
        print("C2 status: N/A (no data)")
        print("C3 status: N/A (no data)")
        print()
        print("FLIP ELIGIBLE: NO (ledger absent)")
        return None

    try:
        df = pd.read_parquet(LEDGER_PATH)
    except Exception as exc:
        _print_banner()
        print(f"LEDGER STATUS: READ ERROR — {exc}")
        print(f"Path:    {LEDGER_PATH}")
        print("Action:  Check file integrity; the nightly writer may have crashed.")
        return None

    if df.empty:
        _print_banner()
        print("LEDGER STATUS: EMPTY")
        print()
        print(f"Path:    {LEDGER_PATH}")
        print("Reason:  Accrual not started — ledger file exists but contains no rows.")
        print("         This typically means the file was pre-created by the schema")
        print("         bootstrap but the nightly collector has not yet written data.")
        print()
        print("C1 status: 0 / 100 clusters  |  0 / 2 quarters")
        print("C2 status: N/A (no data)")
        print("C3 status: N/A (no data)")
        print()
        print("FLIP ELIGIBLE: NO (ledger empty)")
        return None

    # Schema validation — defensive per task spec.
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        _print_banner()
        print("LEDGER STATUS: SCHEMA MISMATCH")
        print()
        print(f"Missing columns: {sorted(missing)}")
        print(f"Present columns: {sorted(df.columns.tolist())}")
        print()
        print("Action:  The ledger writer (build_stock_library Step H) may have")
        print("         changed its schema. Update REQUIRED_COLUMNS in this script")
        print("         or investigate the writer.")
        return None

    # Coerce types.
    if not pd.api.types.is_datetime64_any_dtype(df["asof"]):
        df["asof"] = pd.to_datetime(df["asof"])

    log.info("Ledger loaded: %d rows, %d tickers, date range %s to %s",
             len(df), df["ticker"].nunique(),
             df["asof"].min().date(), df["asof"].max().date())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2.  FORWARD OUTCOME JOIN
# ─────────────────────────────────────────────────────────────────────────────

def _load_close_for_ticker(ticker: str) -> pd.Series | None:
    """Load split-adjusted close for a ticker from the Massive store.

    Mirrors the replay pipeline's verdict-grade source (ERA-LAW: Massive for
    the 2021+ primary window; delisted names visible). Falls back to yahoo on
    missing Massive files (for names that were never in the whole-market store).
    Returns None if neither source has the ticker.
    """
    massive_path = MASSIVE_DIR / f"{ticker}.parquet"
    if massive_path.exists():
        c = _read_close(massive_path)
        if c is not None and len(c) >= 60:
            return split_adjust(c)

    # Fallback: yahoo (dividend-adjusted; acceptable for ratio-based stop-out check).
    from scripts.replay_standout_pipeline import YAHOO_DIR  # noqa: E402 (already imported)
    yahoo_path = YAHOO_DIR / f"{ticker}.parquet"
    if yahoo_path.exists():
        c = _read_close(yahoo_path)
        if c is not None and len(c) >= 60:
            return c

    return None


def join_forward_outcomes(df: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Join forward stop-out outcomes to ledger rows.

    For each row in df, looks up the close series for its ticker and computes
    forward_metrics at each horizon. A row is marked:
      - stopped_{H}d = True  iff  fwd_mdd_{H} <= STOP_BARRIER − 1  (i.e. mdd ≤ −5%)
      - matured_{H}d = True  iff  forward_metrics returned a non-None fwd_mdd_{H}

    Rows whose horizon has not matured yet (insufficient forward data) are kept
    in the dataframe but excluded from the statistical computation downstream
    (they are NOT dropped here to preserve the full episode ledger for C1 counting).

    STRICTLY-AFTER convention (species law): forward_metrics uses fill_index which
    finds the first bar STRICTLY AFTER signal_date — PIT-safe, no look-ahead.
    """
    ticker_cache: dict[str, pd.Series | None] = {}
    records = df.to_dict("records")

    for h in horizons:
        df[f"stopped_{h}d"] = False
        df[f"matured_{h}d"] = False

    new_records = []
    for row in records:
        ticker = row["ticker"]
        asof_ts = pd.Timestamp(row["asof"])

        if ticker not in ticker_cache:
            ticker_cache[ticker] = _load_close_for_ticker(ticker)

        close = ticker_cache[ticker]
        row_out = dict(row)

        if close is None:
            for h in horizons:
                row_out[f"stopped_{h}d"] = False
                row_out[f"matured_{h}d"] = False
            new_records.append(row_out)
            continue

        # forward_metrics returns None for unmatured horizons (fills strictly after asof)
        fwd = forward_metrics(close, asof_ts, horizons=horizons)
        for h in horizons:
            mdd = fwd.get(f"fwd_mdd_{h}")
            if mdd is None:
                row_out[f"stopped_{h}d"] = False
                row_out[f"matured_{h}d"] = False
            else:
                row_out[f"matured_{h}d"] = True
                # stop-out: mdd crosses the −5% STOP_BARRIER (STOP_BARRIER = 0.95,
                # so mdd = min_close/entry − 1 ≤ −0.05)
                row_out[f"stopped_{h}d"] = bool(mdd <= (STOP_BARRIER - 1.0))

        new_records.append(row_out)

    return pd.DataFrame(new_records)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  EPISODE CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def assign_episode_clusters(df: pd.DataFrame) -> pd.DataFrame:
    """Assign a cluster label = ISO calendar week of asof.

    Per the species law, independent episode clusters are calendar weeks of
    asof. This bounds the effective-N inflation that would arise from counting
    multiple same-ticker same-week rows as independent episodes.

    Column added: ``cluster`` = string like "2024-W42".
    """
    df = df.copy()
    df["cluster"] = df["asof"].dt.to_period("W").astype(str)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 4.  WILSON LOWER BOUND (episode-cluster bootstrap)
# ─────────────────────────────────────────────────────────────────────────────

def _wilson_cluster_bootstrap(
    blocked_labels: np.ndarray,   # per-row: True if stopped
    blocked_clusters: np.ndarray,  # per-row: cluster label
    unblocked_labels: np.ndarray,
    unblocked_clusters: np.ndarray,
    alpha: float = 0.05,
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = 42,
) -> dict[str, float]:
    """Episode-clustered bootstrap Wilson bounds on D = rate_blocked − rate_unblocked.

    Method:
      1. Build a cluster-level rate for each group (blocked / unblocked) by
         resampling clusters (not rows) with replacement N_BOOTSTRAP times.
      2. Each bootstrap replicate gives a D_b = mean_blocked − mean_unblocked.
      3. The (alpha/2, 1−alpha/2) quantiles of the D_b distribution give the
         lower and upper bootstrap bounds on D.
      4. Point estimate = mean_blocked − mean_unblocked on the original sample.

    Returns dict with keys: D_point, D_lower, D_upper, rate_blocked, rate_unblocked,
    n_blocked_clusters, n_unblocked_clusters, n_blocked_rows, n_unblocked_rows.
    """
    rng = np.random.default_rng(rng_seed)

    def _cluster_mean(labels: np.ndarray, clusters: np.ndarray) -> tuple[float, np.ndarray]:
        """Cluster-level mean stop-out rate and per-cluster means array."""
        unique_clusters = np.unique(clusters)
        if len(unique_clusters) == 0:
            return float("nan"), np.array([])
        cluster_rates = np.array([
            labels[clusters == c].mean() for c in unique_clusters
        ])
        return float(cluster_rates.mean()), cluster_rates

    blocked_rate, blocked_cluster_rates = _cluster_mean(blocked_labels, blocked_clusters)
    unblocked_rate, unblocked_cluster_rates = _cluster_mean(unblocked_labels, unblocked_clusters)

    if len(blocked_cluster_rates) == 0 or len(unblocked_cluster_rates) == 0:
        return {
            "D_point": float("nan"), "D_lower": float("nan"), "D_upper": float("nan"),
            "rate_blocked": blocked_rate, "rate_unblocked": unblocked_rate,
            "n_blocked_clusters": len(blocked_cluster_rates),
            "n_unblocked_clusters": len(unblocked_cluster_rates),
            "n_blocked_rows": len(blocked_labels),
            "n_unblocked_rows": len(unblocked_labels),
        }

    D_point = blocked_rate - unblocked_rate

    # Bootstrap: resample clusters independently for each group.
    n_bl = len(blocked_cluster_rates)
    n_un = len(unblocked_cluster_rates)
    D_boot = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx_bl = rng.integers(0, n_bl, size=n_bl)
        idx_un = rng.integers(0, n_un, size=n_un)
        D_boot[i] = blocked_cluster_rates[idx_bl].mean() - unblocked_cluster_rates[idx_un].mean()

    lo = float(np.percentile(D_boot, 100 * (alpha / 2)))
    hi = float(np.percentile(D_boot, 100 * (1 - alpha / 2)))

    return {
        "D_point": D_point,
        "D_lower": lo,
        "D_upper": hi,
        "rate_blocked": blocked_rate,
        "rate_unblocked": unblocked_rate,
        "n_blocked_clusters": n_bl,
        "n_unblocked_clusters": n_un,
        "n_blocked_rows": len(blocked_labels),
        "n_unblocked_rows": len(unblocked_labels),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5.  FLIP CRITERIA EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_flip_criteria(df: pd.DataFrame, n_bootstrap: int = N_BOOTSTRAP) -> dict[str, Any]:
    """Evaluate C1/C2/C3 and rollback triggers against the joined ledger.

    Returns a structured result dict that is written to shadow_review_latest.json.
    """
    result: dict[str, Any] = {
        "generated_at": date.today().isoformat(),
        "ledger_rows_total": len(df),
        "ledger_date_min": df["asof"].min().date().isoformat() if not df.empty else None,
        "ledger_date_max": df["asof"].max().date().isoformat() if not df.empty else None,
        "horizons": list(HORIZONS),
    }

    # ── C1: episode-cluster count and quarters elapsed ────────────────────────
    df = assign_episode_clusters(df)

    blocked_df = df[df["antichase_shadow_blocked"].astype(bool)]
    n_blocked_clusters = blocked_df["cluster"].nunique()

    first_date = df["asof"].min().date()
    last_date = df["asof"].max().date()
    quarters_elapsed = _quarters_between(first_date, last_date)

    c1_clusters_pass = n_blocked_clusters >= C1_MIN_CLUSTERS
    c1_quarters_pass = quarters_elapsed >= C1_MIN_QUARTERS
    c1_pass = c1_clusters_pass and c1_quarters_pass

    result["C1"] = {
        "n_blocked_clusters": n_blocked_clusters,
        "n_blocked_clusters_threshold": C1_MIN_CLUSTERS,
        "n_blocked_clusters_pass": c1_clusters_pass,
        "quarters_elapsed": quarters_elapsed,
        "quarters_threshold": C1_MIN_QUARTERS,
        "quarters_pass": c1_quarters_pass,
        "pass": c1_pass,
    }

    # ── Per-horizon stats: C2 and RB1 ─────────────────────────────────────────
    horizon_results: dict[str, Any] = {}
    for h in HORIZONS:
        matured_mask = df[f"matured_{h}d"].astype(bool)
        matured_df = df[matured_mask]

        blocked_mat = matured_df[matured_df["antichase_shadow_blocked"].astype(bool)]
        unblocked_mat = matured_df[~matured_df["antichase_shadow_blocked"].astype(bool)]

        n_matured = len(matured_df)
        n_blocked_mat = len(blocked_mat)
        n_unblocked_mat = len(unblocked_mat)

        if n_blocked_mat == 0 or n_unblocked_mat == 0:
            horizon_results[f"h{h}"] = {
                "n_matured": n_matured,
                "n_blocked_matured": n_blocked_mat,
                "n_unblocked_matured": n_unblocked_mat,
                "wilson": None,
                "C2_primary": h == C2_PRIMARY_HORIZON,
                "C2_pass": False,
                "C2_note": "insufficient matured rows in one or both groups",
                "RB1_upper_bound_negative": False,
                "RB1_note": "insufficient data",
            }
            continue

        bl_labels = blocked_mat[f"stopped_{h}d"].astype(float).to_numpy()
        bl_clusters = blocked_mat["cluster"].to_numpy()
        unbl_labels = unblocked_mat[f"stopped_{h}d"].astype(float).to_numpy()
        unbl_clusters = unblocked_mat["cluster"].to_numpy()

        wilson = _wilson_cluster_bootstrap(
            bl_labels, bl_clusters,
            unbl_labels, unbl_clusters,
            alpha=1.0 - C2_WILSON_ALPHA,
            n_bootstrap=n_bootstrap,
        )

        c2_pass = (h == C2_PRIMARY_HORIZON) and (wilson["D_lower"] > 0)
        # RB1: upper bound < 0 (gate would be blocking better outcomes)
        rb1_trigger = wilson["D_upper"] < 0

        horizon_results[f"h{h}"] = {
            "n_matured": n_matured,
            "n_blocked_matured": n_blocked_mat,
            "n_unblocked_matured": n_unblocked_mat,
            "wilson": wilson,
            "C2_primary": h == C2_PRIMARY_HORIZON,
            "C2_pass": c2_pass,
            "C2_note": (
                f"D_lower={wilson['D_lower']:+.4f} {'> 0 PASS' if c2_pass else '<= 0 FAIL'}"
                if h == C2_PRIMARY_HORIZON else "secondary horizon (not primary C2 criterion)"
            ),
            "RB1_upper_bound_negative": rb1_trigger,
            "RB1_note": (
                f"D_upper={wilson['D_upper']:+.4f} {'< 0 ROLLBACK TRIGGER' if rb1_trigger else '>= 0 OK'}"
            ),
        }

    result["horizons_detail"] = horizon_results
    c2_primary_result = horizon_results.get(f"h{C2_PRIMARY_HORIZON}", {})
    c2_pass = c2_primary_result.get("C2_pass", False)
    result["C2"] = {
        "primary_horizon": C2_PRIMARY_HORIZON,
        "pass": c2_pass,
        "D_point": (c2_primary_result.get("wilson") or {}).get("D_point"),
        "D_lower": (c2_primary_result.get("wilson") or {}).get("D_lower"),
        "D_upper": (c2_primary_result.get("wilson") or {}).get("D_upper"),
    }

    # ── C3: sign consistency in both temporal halves ──────────────────────────
    midpoint = df["asof"].quantile(0.5, interpolation="lower")
    h1_df = df[df["asof"] <= midpoint]
    h2_df = df[df["asof"] > midpoint]

    c3_pass = False
    c3_detail: dict[str, Any] = {}

    for half_label, half_df in [("H1", h1_df), ("H2", h2_df)]:
        for h in [C2_PRIMARY_HORIZON]:  # C3 evaluated on primary horizon
            mat_mask = half_df[f"matured_{h}d"].astype(bool)
            mat = half_df[mat_mask]
            bl = mat[mat["antichase_shadow_blocked"].astype(bool)]
            unbl = mat[~mat["antichase_shadow_blocked"].astype(bool)]
            if len(bl) > 0 and len(unbl) > 0:
                D_half = bl[f"stopped_{h}d"].mean() - unbl[f"stopped_{h}d"].mean()
                c3_detail[f"{half_label}_D_{h}d"] = float(D_half)
                c3_detail[f"{half_label}_n_blocked"] = len(bl)
                c3_detail[f"{half_label}_n_unblocked"] = len(unbl)
                c3_detail[f"{half_label}_sign_positive"] = D_half > 0
            else:
                c3_detail[f"{half_label}_D_{h}d"] = None
                c3_detail[f"{half_label}_n_blocked"] = len(bl)
                c3_detail[f"{half_label}_n_unblocked"] = len(unbl)
                c3_detail[f"{half_label}_sign_positive"] = None

    h1_sign = c3_detail.get("H1_sign_positive")
    h2_sign = c3_detail.get("H2_sign_positive")
    if h1_sign is not None and h2_sign is not None:
        c3_pass = bool(h1_sign and h2_sign)

    result["C3"] = {
        "pass": c3_pass,
        "detail": c3_detail,
        "note": "sign-positive means blocked had higher stop-out rate than unblocked in that half",
    }

    # ── Rollback triggers ─────────────────────────────────────────────────────
    rb1_h21 = horizon_results.get("h21", {}).get("RB1_upper_bound_negative", False)
    rb1_h63 = horizon_results.get("h63", {}).get("RB1_upper_bound_negative", False)

    result["rollback_triggers"] = {
        "RB1_stop_reversal": {
            "triggered": rb1_h21 or rb1_h63,
            "h21": rb1_h21,
            "h63": rb1_h63,
            "note": "RB1 requires ≥200 post-flip clusters; pre-flip shadow data shown here for reference",
        },
        "RB2_fire_rate_breach": {
            "triggered": False,  # computed from weekly fires — not available without live board data
            "note": (
                "RB2 requires live board weekly-fire counts (>15% of fires blocked over 4 consecutive "
                "weeks). Not computable from ledger alone — requires live board telemetry."
            ),
        },
        "RB3_recall_failure": {
            "triggered": False,
            "note": (
                "RB3 requires P1.4 per-rejection-reason durable-60D outcome rate column "
                "(PENDING per PREREG §5). Not operational until P1.4 is extended."
            ),
        },
    }

    # ── Overall flip eligibility ──────────────────────────────────────────────
    flip_eligible = c1_pass and c2_pass and c3_pass
    result["flip_eligible"] = flip_eligible
    result["flip_verdict"] = (
        "FLIP ELIGIBLE — all C1/C2/C3 met; Fable ruling required to authorize enforcing gate"
        if flip_eligible
        else "NOT FLIP ELIGIBLE — criteria not yet met (see C1/C2/C3 detail)"
    )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 6.  REPORTING
# ─────────────────────────────────────────────────────────────────────────────

def _quarters_between(d1: date, d2: date) -> float:
    """Approximate calendar quarters between two dates (91.25 days per quarter)."""
    return max(0.0, (d2 - d1).days / 91.25)


def _print_banner() -> None:
    print()
    print("=" * 68)
    print("  EI P2.1a — F3 ANTI-CHASE SHADOW FLIP-ACCOUNTING REVIEW")
    print("  Spec: P2_1A_ANTICHASE_GATE_PREREG.md §2.2")
    print("=" * 68)
    print()


def print_report(result: dict[str, Any]) -> None:
    """Print a human-readable scoreboard to stdout."""
    _print_banner()
    print(f"Generated:   {result.get('generated_at', 'N/A')}")
    print(f"Ledger rows: {result.get('ledger_rows_total', 'N/A')}")
    date_min = result.get("ledger_date_min", "N/A")
    date_max = result.get("ledger_date_max", "N/A")
    print(f"Date range:  {date_min}  →  {date_max}")
    print()

    # C1
    c1 = result.get("C1", {})
    c1_pass = c1.get("pass", False)
    c1_clusters_pass = c1.get("n_blocked_clusters_pass", False)
    c1_quarters_pass = c1.get("quarters_pass", False)
    print(f"{'[PASS]' if c1_clusters_pass else '[FAIL]'}"
          f"  C1a — blocked episode clusters:  "
          f"{c1.get('n_blocked_clusters', 0)} / {C1_MIN_CLUSTERS} required")
    print(f"{'[PASS]' if c1_quarters_pass else '[FAIL]'}"
          f"  C1b — quarters elapsed:          "
          f"{c1.get('quarters_elapsed', 0.0):.2f} / {C1_MIN_QUARTERS} required")
    print(f"{'[PASS]' if c1_pass else '[FAIL]'}"
          f"  C1 OVERALL (both a+b required)")
    print()

    # C2 per horizon
    hd = result.get("horizons_detail", {})
    for h in HORIZONS:
        h_res = hd.get(f"h{h}", {})
        w = h_res.get("wilson") or {}
        is_primary = h == C2_PRIMARY_HORIZON
        label = f"C2 ({h}d PRIMARY)" if is_primary else f"    ({h}d secondary)"
        c2_h_pass = h_res.get("C2_pass", False)
        if w:
            print(f"{'[PASS]' if c2_h_pass else '[FAIL]'}  {label}:  "
                  f"D={w.get('D_point', float('nan')):+.4f}  "
                  f"[{w.get('D_lower', float('nan')):+.4f}, {w.get('D_upper', float('nan')):+.4f}]  "
                  f"blocked_rate={w.get('rate_blocked', float('nan')):.4f}  "
                  f"unblocked_rate={w.get('rate_unblocked', float('nan')):.4f}  "
                  f"n_bl_clust={w.get('n_blocked_clusters', 0)}  "
                  f"n_unbl_clust={w.get('n_unblocked_clusters', 0)}")
        else:
            note = h_res.get("C2_note", "no data")
            print(f"[N/A ]  {label}:  {note}")
    print()

    # C3
    c3 = result.get("C3", {})
    c3_pass = c3.get("pass", False)
    det = c3.get("detail", {})
    h1_d = det.get(f"H1_D_{C2_PRIMARY_HORIZON}d")
    h2_d = det.get(f"H2_D_{C2_PRIMARY_HORIZON}d")
    h1_str = f"{h1_d:+.4f}" if h1_d is not None else "N/A"
    h2_str = f"{h2_d:+.4f}" if h2_d is not None else "N/A"
    print(f"{'[PASS]' if c3_pass else '[FAIL]'}  C3 — sign consistency:  "
          f"H1_D={h1_str}  H2_D={h2_str}  "
          f"(both must be > 0)")
    print()

    # Rollback status
    rb = result.get("rollback_triggers", {})
    rb1 = rb.get("RB1_stop_reversal", {})
    print(f"{'[WARN]' if rb1.get('triggered') else '[OK  ]'}  "
          f"RB1 stop-reversal: h21={rb1.get('h21')}  h63={rb1.get('h63')}")
    print(f"[N/A ]  RB2 fire-rate breach: requires live board telemetry (not computable here)")
    print(f"[N/A ]  RB3 recall failure:   requires P1.4 per-reason column (PENDING)")
    print()

    # Overall
    flip = result.get("flip_eligible", False)
    print("─" * 68)
    print(f"FLIP ELIGIBLE:  {'YES' if flip else 'NO'}")
    print(result.get("flip_verdict", ""))
    print("─" * 68)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 7.  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def _write_json(result: dict[str, Any], out_path: Path) -> None:
    """Write result dict to JSON, converting non-serializable types."""
    def _serialize(obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Not serializable: {type(obj)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=_serialize)
    log.info("Written: %s", out_path)


# ─────────────────────────────────────────────────────────────────────────────
# 8.  EI-F1D-RW SHADOW SECTION
# ─────────────────────────────────────────────────────────────────────────────
#
# Spec:   research/entry_intel/P2_5_INTERACTION_PREREG.md
# Study:  research/entry_intel/p1_runs/P2_5_STUDY/RESULTS.md
# Registry: data/species/registry.json (entry: EI-F1D-RW)
#
# Reads the F1D shadow ledger and computes:
#   - D_f per config (six columns): stop_out(moved_up) - stop_out(not_moved_up)
#     where moved_up = row had f1d_shadow_bonus > 0 for that config
#   - C1/C2/C3-style scoreboard against the registry entry
#   - Absent-ledger graceful path (exits 0 with clear message)
#
# The anti-chase section above is untouched.
# ─────────────────────────────────────────────────────────────────────────────

# Canonical F1D ledger path
F1D_LEDGER_PATH = CANONICAL_DATA / "signal_archive" / "f1d_shadow_ledger.parquet"

# Pre-registered config names and their ledger boolean column
F1D_CONFIGS: dict[str, str] = {
    "C1": "c1_qual",
    "C3": "c3_qual",
    "C5": "c5_qual",
    "C6": "c6_qual",  # primary
    "C7": "c7_qual",
    "C8": "c8_qual",
}

# Required ledger columns for the F1D section
F1D_REQUIRED_COLUMNS = {
    "asof", "ticker", "board_name",
    "washout_active", "dd_pct", "ext_z", "rs_sector_quartile",
    "above_200", "blend_sorted", "f1d_shadow_bonus", "f1d_shadow_rank",
    "c1_qual", "c3_qual", "c5_qual", "c6_qual", "c7_qual", "c8_qual",
    "gate_state", "logged_at",
}

# Flip criterion constants (registry entry EI-F1D-RW)
F1D_MIN_CLUSTERS = 25          # minimum independent episode clusters
F1D_MIN_QUARTERS = 2           # minimum calendar quarters elapsed
F1D_FALSIFICATION_DF = 3.34    # D_f >= +3.34pp at 63d = flat-binary reprobe tripwire
F1D_PRIMARY_CONFIG = "C6"
F1D_A1_WATCHLIST = {"C5", "C7"}  # half-concentrated; monitor for instability


def load_f1d_ledger() -> "pd.DataFrame | None":
    """Load the F1D shadow ledger; return None with a clear message if absent/empty.

    Mirrors the anti-chase load_and_validate_ledger() pattern exactly.
    Exits cleanly (code 0) when ledger is absent — accrual not started.
    """
    _f1d_banner()
    if not F1D_LEDGER_PATH.exists():
        print("LEDGER STATUS: ABSENT")
        print()
        print(f"Path:    {F1D_LEDGER_PATH}")
        print("Reason:  Accrual not started — the F1D shadow ledger is written by")
        print("         build_stock_library Step I on the first nightly build")
        print("         after the P2.5 PR is merged to main.")
        print()
        print("Action:  No action required. Re-run after the next nightly build.")
        print()
        print(f"Cluster floor: 0 / {F1D_MIN_CLUSTERS} clusters  |  0 / {F1D_MIN_QUARTERS} quarters")
        print("D_f status:    N/A (no data)")
        print()
        print("FLIP ELIGIBLE: NO (ledger absent)")
        return None

    try:
        df = pd.read_parquet(F1D_LEDGER_PATH)
    except Exception as exc:
        print(f"LEDGER STATUS: READ ERROR — {exc}")
        print(f"Path:    {F1D_LEDGER_PATH}")
        print("Action:  Check file integrity; the nightly writer may have crashed.")
        return None

    if df.empty:
        print("LEDGER STATUS: EMPTY")
        print()
        print(f"Path:    {F1D_LEDGER_PATH}")
        print("Reason:  File exists but contains no rows.")
        print()
        print(f"Cluster floor: 0 / {F1D_MIN_CLUSTERS} clusters  |  0 / {F1D_MIN_QUARTERS} quarters")
        print("FLIP ELIGIBLE: NO (ledger empty)")
        return None

    missing = F1D_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        print("LEDGER STATUS: SCHEMA MISMATCH")
        print()
        print(f"Missing columns: {sorted(missing)}")
        print(f"Present columns: {sorted(df.columns.tolist())}")
        print()
        print("Action:  The ledger writer (build_stock_library Step I) may have")
        print("         changed its schema. Update F1D_REQUIRED_COLUMNS in this script.")
        return None

    if not pd.api.types.is_datetime64_any_dtype(df["asof"]):
        df["asof"] = pd.to_datetime(df["asof"])

    log.info("F1D ledger loaded: %d rows, %d tickers, %s to %s",
             len(df), df["ticker"].nunique(),
             df["asof"].min().date(), df["asof"].max().date())
    return df


def _f1d_banner() -> None:
    print()
    print("=" * 68)
    print("  EI P2.5 — F1D-RW SHADOW REVIEW (Washout Depth × Interaction)")
    print("  Primary: C6 (deep_trio = dd>25% × ac × rs)")
    print("  Spec: P2_5_INTERACTION_PREREG.md | Registry: EI-F1D-RW")
    print("=" * 68)
    print()


def evaluate_f1d_shadow(df: pd.DataFrame) -> "dict[str, Any]":
    """Compute D_f per config and scoreboard against registry flip criterion.

    D_f = stop_out_rate(moved_up) - stop_out_rate(not_moved_up) at 63d horizon
    where moved_up means c{N}_qual == True (bonus > 0) for that config row.

    The flip criterion (corrected D_f machinery):
      Wilson_upper(D_f) < 0 at z=1.645 (one-sided 95% on the improvement)
      => D_f < 0 (stop-out lower for moved-up) AND Wilson upper bound < 0.

    Falsification tripwire: D_f >= +3.34pp at 63d (flat-binary reprobe T09).
    """
    result: "dict[str, Any]" = {
        "generated_at": date.today().isoformat(),
        "ledger_rows_total": len(df),
        "ledger_date_min": df["asof"].min().date().isoformat() if not df.empty else None,
        "ledger_date_max": df["asof"].max().date().isoformat() if not df.empty else None,
        "primary_config": F1D_PRIMARY_CONFIG,
        "a1_watchlist_configs": sorted(F1D_A1_WATCHLIST),
    }

    # Cluster count for C1 (using asof ISO week, same as anti-chase C1)
    df = df.copy()
    df["cluster"] = df["asof"].dt.to_period("W").astype(str)

    # Overall cluster stats
    first_date = df["asof"].min().date()
    last_date = df["asof"].max().date()
    quarters_elapsed = max(0.0, (last_date - first_date).days / 91.25)
    n_total_clusters = df["cluster"].nunique()

    result["accrual"] = {
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "quarters_elapsed": round(quarters_elapsed, 2),
        "total_clusters": n_total_clusters,
        "min_clusters_threshold": F1D_MIN_CLUSTERS,
        "min_quarters_threshold": F1D_MIN_QUARTERS,
        "clusters_pass": n_total_clusters >= F1D_MIN_CLUSTERS,
        "quarters_pass": quarters_elapsed >= F1D_MIN_QUARTERS,
    }

    # Forward outcome join: mirrors anti-chase join but uses f1d_shadow_rank as
    # the "moved_up" indicator per config. For each row, moved_up for config CN
    # = c{N}_qual is True. The forward outcomes (stopped_21d, stopped_63d) are
    # loaded from price stores exactly as in the anti-chase section.
    # For now: if no matured rows exist, report absent-data gracefully.
    # (Full forward join happens once horizons have matured.)

    config_results: "dict[str, Any]" = {}

    for cid, qual_col in F1D_CONFIGS.items():
        qual_mask = df[qual_col].astype(bool)
        n_qual = int(qual_mask.sum())
        n_total = len(df)
        n_clusters_qual = df.loc[qual_mask, "cluster"].nunique()
        qual_pct = round(100.0 * n_qual / n_total, 2) if n_total > 0 else 0.0

        # Forward stop-out computation: requires matured rows
        # Maturation happens at 21d and 63d horizons.
        # Until then, report counts only (graceful absent-data path).
        has_matured_21 = "stopped_21d" in df.columns and df["stopped_21d"].notna().any()
        has_matured_63 = "stopped_63d" in df.columns and df["stopped_63d"].notna().any()

        d_f_21: "float | None" = None
        d_f_63: "float | None" = None
        wilson_upper_63: "float | None" = None
        falsification_tripped = False
        flip_eligible_this_config = False

        if has_matured_63:
            mat63 = df["matured_63d"].astype(bool) if "matured_63d" in df.columns else df["stopped_63d"].notna()
            qual_mat63 = df[qual_mask & mat63]
            notqual_mat63 = df[(~qual_mask) & mat63]

            if len(qual_mat63) > 0 and len(notqual_mat63) > 0:
                rate_qual = qual_mat63["stopped_63d"].astype(float).mean()
                rate_notqual = notqual_mat63["stopped_63d"].astype(float).mean()
                d_f_63 = float((rate_qual - rate_notqual) * 100.0)

                # Wilson upper bound on D_f (episode-clustered bootstrap, 1000 resamples)
                # Mirrors _wilson_cluster_bootstrap but for moved_up vs not_moved_up.
                try:
                    _q_labels = qual_mat63["stopped_63d"].astype(float).to_numpy()
                    _q_clusters = qual_mat63["cluster"].to_numpy()
                    _nq_labels = notqual_mat63["stopped_63d"].astype(float).to_numpy()
                    _nq_clusters = notqual_mat63["cluster"].to_numpy()
                    # A1b fix: the registered flip criterion (registry EI-F1D-RW
                    # flip_criterion + P2_5_INTERACTION_PREREG.md §6.3) specifies
                    # one-sided 95% (z=1.645). _wilson_cluster_bootstrap uses
                    # two-sided idiom (alpha/2, 1-alpha/2 quantiles), so the
                    # one-sided 95th percentile requires alpha=0.10 here, which
                    # returns the 5th and 95th percentiles. D_upper is the
                    # relevant bound for the flip criterion (Wilson_upper < 0).
                    # NOTE: the anti-chase sibling uses alpha=0.05 (two-sided 95%,
                    # z≈1.96) per its own registered convention — do not touch it.
                    _w = _wilson_cluster_bootstrap(
                        _q_labels, _q_clusters,
                        _nq_labels, _nq_clusters,
                        alpha=0.10,  # one-sided 95th percentile (z=1.645) per §6.3
                        n_bootstrap=N_BOOTSTRAP,
                    )
                    wilson_upper_63 = _w.get("D_upper")
                except Exception as _exc:
                    log.debug("F1D Wilson bootstrap failed for %s: %s", cid, _exc)

                falsification_tripped = bool(d_f_63 >= F1D_FALSIFICATION_DF)
                # Flip eligible: D_f < 0 AND Wilson upper < 0
                # AND cluster floor AND quarter floor
                flip_eligible_this_config = bool(
                    d_f_63 is not None and d_f_63 < 0
                    and wilson_upper_63 is not None and wilson_upper_63 < 0
                    and n_clusters_qual >= F1D_MIN_CLUSTERS
                    and quarters_elapsed >= F1D_MIN_QUARTERS
                    and not falsification_tripped
                )

        if has_matured_21:
            mat21 = df["matured_21d"].astype(bool) if "matured_21d" in df.columns else df["stopped_21d"].notna()
            qual_mat21 = df[qual_mask & mat21]
            notqual_mat21 = df[(~qual_mask) & mat21]
            if len(qual_mat21) > 0 and len(notqual_mat21) > 0:
                rate_q21 = qual_mat21["stopped_21d"].astype(float).mean()
                rate_nq21 = notqual_mat21["stopped_21d"].astype(float).mean()
                d_f_21 = float((rate_q21 - rate_nq21) * 100.0)

        config_results[cid] = {
            "config": cid,
            "qual_col": qual_col,
            "is_primary": cid == F1D_PRIMARY_CONFIG,
            "a1_watchlist": cid in F1D_A1_WATCHLIST,
            "n_qualified_rows": n_qual,
            "n_total_rows": n_total,
            "qual_pct": qual_pct,
            "n_clusters_qualified": n_clusters_qual,
            "D_f_21d_pp": d_f_21,
            "D_f_63d_pp": d_f_63,
            "wilson_upper_63d": wilson_upper_63,
            "falsification_tripped": falsification_tripped,
            "falsification_threshold_pp": F1D_FALSIFICATION_DF,
            "flip_eligible": flip_eligible_this_config,
            "data_note": (
                "matured forward outcomes available" if has_matured_63
                else "no matured 63d outcomes yet — counts only"
            ),
        }

    result["configs"] = config_results

    # Overall flip eligibility: primary config C6 must meet criterion
    primary = config_results.get(F1D_PRIMARY_CONFIG, {})
    result["flip_eligible"] = primary.get("flip_eligible", False)
    result["falsification_tripped"] = primary.get("falsification_tripped", False)
    result["flip_verdict"] = (
        "FLIP ELIGIBLE — C6 Wilson_upper(D_f) < 0 AND n_floor AND quarter_floor met; Fable ruling required"
        if result["flip_eligible"]
        else "NOT FLIP ELIGIBLE — forward ledger criteria not yet met (see config detail)"
    )
    if result["falsification_tripped"]:
        result["flip_verdict"] = (
            "FALSIFICATION TRIGGERED — C6 D_f >= +3.34pp (flat-binary reprobe tripwire); "
            "shadow must be reviewed for withdrawal"
        )

    return result


def print_f1d_report(result: "dict[str, Any]") -> None:
    """Print human-readable F1D scoreboard to stdout."""
    print(f"Generated:   {result.get('generated_at', 'N/A')}")
    print(f"Ledger rows: {result.get('ledger_rows_total', 'N/A')}")
    print(f"Date range:  {result.get('ledger_date_min', 'N/A')}  →  {result.get('ledger_date_max', 'N/A')}")
    print()

    acc = result.get("accrual", {})
    c_pass = acc.get("clusters_pass", False)
    q_pass = acc.get("quarters_pass", False)
    print(f"{'[PASS]' if c_pass else '[FAIL]'}  Cluster floor: "
          f"{acc.get('total_clusters', 0)} / {F1D_MIN_CLUSTERS} required")
    print(f"{'[PASS]' if q_pass else '[FAIL]'}  Quarter floor: "
          f"{acc.get('quarters_elapsed', 0.0):.2f} / {F1D_MIN_QUARTERS} required")
    print()

    print("Per-config D_f scoreboard (D_f = stop_rate(qualified) - stop_rate(not-qualified)):")
    print(f"  {'Config':<6} {'%board':>7} {'n_clust':>8} {'D_f@21d':>9} {'D_f@63d':>9} "
          f"{'W_upper63':>10} {'Flip?':>7} {'Falsif?':>8} {'Note'}")
    print("  " + "-" * 78)
    for cid, cr in result.get("configs", {}).items():
        is_primary = "* " if cr.get("is_primary") else "  "
        a1 = "[A1]" if cr.get("a1_watchlist") else "    "
        d21_str = f"{cr['D_f_21d_pp']:+.2f}pp" if cr.get("D_f_21d_pp") is not None else "N/A"
        d63_str = f"{cr['D_f_63d_pp']:+.2f}pp" if cr.get("D_f_63d_pp") is not None else "N/A"
        wu_str = f"{cr['wilson_upper_63d']:+.4f}" if cr.get("wilson_upper_63d") is not None else "N/A"
        flip_str = "YES" if cr.get("flip_eligible") else "no"
        fals_str = "TRIP!" if cr.get("falsification_tripped") else "ok"
        print(f"  {is_primary}{cid:<4} {a1} "
              f"{cr.get('qual_pct', 0):6.1f}% "
              f"{cr.get('n_clusters_qualified', 0):7d} "
              f"{d21_str:>9} {d63_str:>9} {wu_str:>10} "
              f"{flip_str:>7} {fals_str:>8}  {cr.get('data_note', '')}")
    print()
    print("  * = primary config (C6 deep_trio). [A1] = watchlist (half-concentrated)")
    print()

    # Overall
    flip = result.get("flip_eligible", False)
    fals = result.get("falsification_tripped", False)
    print("─" * 68)
    if fals:
        print("FALSIFICATION TRIPPED — review required")
    else:
        print(f"FLIP ELIGIBLE:  {'YES' if flip else 'NO'}")
    print(result.get("flip_verdict", ""))
    print("─" * 68)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=WORKTREE_ROOT / "research" / "entry_intel" / "p2_reviews" / "shadow_review_latest.json",
        help="Output JSON path (default: research/entry_intel/p2_reviews/shadow_review_latest.json)",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=N_BOOTSTRAP,
        help=f"Number of cluster bootstrap resamples for Wilson bounds (default: {N_BOOTSTRAP})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    # ── Step 1: load and validate ledger (anti-chase) ─────────────────────────
    df = load_and_validate_ledger()
    if df is None:
        # Absent/empty ledger: clean exit with code 0 (accrual not started).
        result = {
            "generated_at": date.today().isoformat(),
            "ledger_status": "absent_or_empty",
            "flip_eligible": False,
            "flip_verdict": "NOT FLIP ELIGIBLE — ledger absent or empty; accrual not started",
        }
        _write_json(result, args.out)
        # Still run F1D section even if anti-chase ledger is absent
    else:
        # ── Step 2: join forward outcomes ─────────────────────────────────────
        log.info("Joining forward outcomes (horizons=%s)...", HORIZONS)
        df = join_forward_outcomes(df, horizons=HORIZONS)

        # ── Step 3: evaluate flip criteria ────────────────────────────────────
        log.info("Evaluating flip criteria...")
        result = evaluate_flip_criteria(df, n_bootstrap=args.n_bootstrap)

        # ── Step 4: print report ──────────────────────────────────────────────
        print_report(result)

        # ── Step 5: write JSON ────────────────────────────────────────────────
        _write_json(result, args.out)
        print(f"JSON written: {args.out}")

    # ── Step 6: EI-F1D-RW section (independent of anti-chase; always runs) ───
    f1d_df = load_f1d_ledger()
    if f1d_df is None:
        f1d_result: "dict[str, Any]" = {
            "generated_at": date.today().isoformat(),
            "ledger_status": "absent_or_empty",
            "flip_eligible": False,
            "flip_verdict": "NOT FLIP ELIGIBLE — F1D ledger absent or empty; accrual not started",
        }
    else:
        # A1 fix: join forward outcomes to the F1D ledger before evaluating.
        # Without this join, stopped_63d/matured_63d columns never exist on the
        # F1D frame, so D_f, Wilson bounds, the +3.34pp falsification tripwire,
        # and flip_eligible are permanently None/False. Mirror the anti-chase
        # call exactly — same horizons, same join helper.
        log.info("Joining forward outcomes for F1D ledger (horizons=%s)...", HORIZONS)
        f1d_df = join_forward_outcomes(f1d_df, horizons=HORIZONS)
        log.info("Evaluating F1D shadow criteria...")
        f1d_result = evaluate_f1d_shadow(f1d_df)
        print_f1d_report(f1d_result)

    # Write F1D result to a separate JSON sidecar
    _f1d_out = args.out.parent / "f1d_shadow_review_latest.json"
    _write_json(f1d_result, _f1d_out)
    print(f"F1D JSON written: {_f1d_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
