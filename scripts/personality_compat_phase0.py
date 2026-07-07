"""Setup-compatibility phase-0 harness — stock-personality W3.

Pre-registered study: does the personality cell of a ticker *as of the fire date*
shift the safety-net outcome (P(STOPPED)) of a board/gate fire vs. the corpus
baseline?

Faithful to §4 of research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md.

Modes
-----
--register   Count corpora, collapse archetypes by n only (BEFORE any outcome
             read), enumerate the cell family, write the registration JSON and
             register the trial budget in data/trial_ledger.jsonl.

--run        Grade fires, attach PIT labels, run primary P(STOPPED) test with
             two-way cluster-robust inference (ticker × quarter), BH-FDR,
             disguise regression for survivors.

--smoke N    Full pipeline on N tickers; SMOKE watermark; no ledger writes;
             outputs to /tmp.

House-law citations
-------------------
- R-SP11: one binary primary per cell (P(STOPPED)); BH-FDR; grading via
          engine/grading.py ONLY.
- R-SP12: PIT archetype join (greatest asof_date <= fire_date).
- §4:     Two-way cluster-robust (ticker × quarter); cells n<50 → insufficient_n.
- DT-R14 / #1841 time-confound law: two-way (ticker × quarter) clustering
          satisfies the calendar-time control requirement for ticker-cluster CIs.
          Do NOT weaken to one-way ticker-only clustering.

Bootstrap estimator (two-way Cameron-Gelbach-Miller style)
----------------------------------------------------------
Each iteration independently draws B_T tickers (with replacement from the set of
unique tickers) and B_Q quarters (with replacement from the set of unique quarters).
Row i is included in the bootstrap sample with multiplicity
    mult(i) = count(ticker_i in B_T) * count(quarter_i in B_Q)
i.e., rows are weighted by the product of both draw multiplicities.

WHY nested-within resampling is INVALID: the "resample tickers, then within each
selected ticker resample that ticker's quarters" scheme is one-way ticker clustering
in disguise.  Quarter-level common shocks appear in ALL tickers simultaneously, but
the nested scheme never resamples a quarter across multiple tickers — the calendar
axis is only resampled within each ticker's own set.  This leaves cross-sectional
correlations induced by common calendar shocks uncontrolled while the CI ostensibly
claims two-way validity.  The independent-draw scheme above treats tickers and
quarters symmetrically, giving each dimension its own resampling degree of freedom.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import sys
import time
import warnings
from datetime import date as _date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("personality_compat")

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from engine.grading import (  # noqa: E402
    terminal_state,
    TerminalState,
    LIFTOFF_15,
    LIFTOFF_8,
    LIFTOFF_HORIZON_126,
    LIFTOFF_HORIZON_21,
)
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (frozen — §4 pre-registered)
# ---------------------------------------------------------------------------
FDR_FAMILY = "stock_personality_compat"
FDR_Q = 0.05
MIN_CELL_N = 50           # §4: cells with n<50 → insufficient_n; not tested
ARCHETYPE_MIN_N = 400     # §4: merge archetypes with attachable-n < 400 into "other_archetype"
PRIMARY_RULER = "clean15_126"  # positional primary (R-SP11)
ALT_RULER = "clean8_21"        # rotational ruler (secondaries)

CHART_LABELS = [
    "smooth_compounder_grind", "stair_step_leader", "volatile_momentum_vehicle",
    "mean_reversion_rubber_band", "basing_accumulator", "event_gapper",
    "failed_breakout_trap", "defensive_range_stock", "mixed_chart",
]
MICRO_LABELS = [
    "tight_spread_absorber", "wide_spread_impact", "gap_discontinuity_risk",
    "slow_mean_reversion_liquidity", "mixed_microstructure",
]

# Corpus identifiers
CORPUS_TRACK_RECORD = "track_record"
CORPUS_GATE_FIRES   = "gate_fires"
CORPUS_REPLAY       = "replay"

# Paths
_DATA_DIR = _REPO_ROOT / "data"
_RESEARCH_DIR = _DATA_DIR / "research"
_TRACK_RECORD_PATH = _DATA_DIR / "signal_archive" / "track_record.parquet"
_GATE_FIRES_DEEP_PATH = _RESEARCH_DIR / "gate_fires_deep.parquet"
_GATE_FIRES_MANIFEST = _RESEARCH_DIR / "gate_fires_deep_manifest.json"
_ARCHETYPE_PATH = _DATA_DIR / "archetypes" / "history.parquet"
_PIT_LABELS_PATH = _RESEARCH_DIR / "personality_pit_labels.parquet"
_TICKER_SECTORS_PATH = _DATA_DIR / "breadth" / "ticker_sectors.parquet"
_LEDGER_PATH = _DATA_DIR / "trial_ledger.jsonl"
_REGISTRATION_PATH = _RESEARCH_DIR / "personality_compat_registration.json"
_OUT_PARQUET = _RESEARCH_DIR / "personality_compat_phase0.parquet"
_OUT_REPORT = _REPO_ROOT / "research" / "STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md"

_STOCKS_DEEP_DIR = _DATA_DIR / "stocks"


# ---------------------------------------------------------------------------
# Archetype PIT join helpers
# ---------------------------------------------------------------------------
def _load_archetype_history() -> dict[str, pd.DataFrame]:
    """Load archetype history, return per-ticker lookup dict (sorted by asof_date).

    N1: sort deterministically by ["ticker", "asof_date", "fy"] before groupby
    so that per-ticker slices are stable across pandas versions.
    """
    if not _ARCHETYPE_PATH.exists():
        return {}
    df = pd.read_parquet(_ARCHETYPE_PATH)
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    df = df.sort_values(["ticker", "asof_date", "fy"]).reset_index(drop=True)
    result: dict[str, pd.DataFrame] = {}
    for tk, g in df.groupby("ticker", sort=False):
        result[str(tk)] = g.reset_index(drop=True)
    return result


def _archetype_pit(ticker: str, fire_date: pd.Timestamp,
                   lookup: dict[str, pd.DataFrame]) -> str | None:
    """R-SP12: attach greatest asof_date <= fire_date; return None if none."""
    hist = lookup.get(ticker)
    if hist is None or hist.empty:
        return None
    mask = hist["asof_date"] <= fire_date
    if not mask.any():
        return None
    row = hist[mask].iloc[-1]
    return str(row["archetype"]) if pd.notna(row["archetype"]) else None


# ---------------------------------------------------------------------------
# Corpus loaders
# ---------------------------------------------------------------------------
def _load_track_record_corpus() -> pd.DataFrame:
    """Load buy/rebuy fires from track_record.parquet."""
    if not _TRACK_RECORD_PATH.exists():
        log.warning("track_record.parquet not found")
        return pd.DataFrame()
    df = pd.read_parquet(_TRACK_RECORD_PATH)
    fires = df[df["type"].isin(["buy", "rebuy"])].copy()
    fires["date"] = pd.to_datetime(fires["date"])
    fires["corpus"] = CORPUS_TRACK_RECORD
    return fires.reset_index(drop=True)


def _load_gate_fires_corpus(gate_fires_path: Path | None = None) -> pd.DataFrame:
    """Load gate-fires corpus; regenerate via dump_gate_fires.py if absent."""
    path = gate_fires_path or _GATE_FIRES_DEEP_PATH
    if not path.exists():
        # N3: log prominently when spawning the regeneration subprocess
        log.warning(
            "[REGISTER] gate_fires_deep.parquet absent — spawning subprocess: "
            "scripts/research/dump_gate_fires.py --panel deep  (this may take minutes)"
        )
        import subprocess
        dump = _REPO_ROOT / "scripts" / "research" / "dump_gate_fires.py"
        subprocess.run([sys.executable, str(dump), "--panel", "deep"], check=True)
        log.info("[REGISTER] gate_fires regeneration complete: %s", path)

    if not path.exists():
        log.warning("gate_fires_deep.parquet still absent after regeneration attempt")
        return pd.DataFrame()

    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df["type"] = "gate_fire"
    df["corpus"] = CORPUS_GATE_FIRES
    return df.reset_index(drop=True)


def _load_replay_corpus(replay_root: Path | None) -> pd.DataFrame:
    """Load replay fire-verdict subset. Returns empty with SKIP note when absent."""
    if replay_root is None:
        return pd.DataFrame()
    parquet_candidates = list(replay_root.glob("**/*.parquet"))
    if not parquet_candidates:
        return pd.DataFrame()
    frames = []
    for p in parquet_candidates:
        try:
            df = pd.read_parquet(p)
            if "date" in df.columns and "ticker" in df.columns:
                df = df.copy()
                df["date"] = pd.to_datetime(df["date"])
                df["corpus"] = CORPUS_REPLAY
                frames.append(df)
        except Exception as exc:
            log.debug("Skipping replay file %s: %s", p, exc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# PIT label attachment from personality_pit_labels.parquet
# ---------------------------------------------------------------------------
def _load_pit_labels() -> dict[str, pd.DataFrame]:
    """Load personality PIT labels, return per-ticker lookup dict."""
    if not _PIT_LABELS_PATH.exists():
        return {}
    df = pd.read_parquet(_PIT_LABELS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    result: dict[str, pd.DataFrame] = {}
    for tk, g in df.groupby("ticker"):
        result[str(tk)] = g.sort_values("date").reset_index(drop=True)
    return result


def _chart_micro_at(ticker: str, fire_date: pd.Timestamp,
                    pit_lookup: dict[str, pd.DataFrame]) -> dict[str, str | None]:
    """Get PIT chart+micro labels at fire_date (greatest date <= fire_date)."""
    null = {"chart_primary": None, "micro_primary": None}
    hist = pit_lookup.get(ticker)
    if hist is None or hist.empty:
        return null
    mask = hist["date"] <= fire_date
    if not mask.any():
        return null
    row = hist[mask].iloc[-1]
    return {
        "chart_primary": row.get("chart_primary") if pd.notna(row.get("chart_primary", None)) else None,
        "micro_primary": row.get("micro_primary") if pd.notna(row.get("micro_primary", None)) else None,
    }


# ---------------------------------------------------------------------------
# Grading helpers (routes through engine/grading.py ONLY — R-SP11)
# ---------------------------------------------------------------------------
def _load_close(ticker: str) -> pd.Series | None:
    """Load close series for a ticker from the deep stocks directory."""
    p = _STOCKS_DEEP_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    close = df["close"].sort_index().dropna()
    return close if len(close) > 0 else None


def _grade_fire(ticker: str, fire_date: pd.Timestamp,
                close_cache: dict[str, pd.Series | None],
                ruler: str = PRIMARY_RULER) -> str | None:
    """Grade one fire via engine/grading.terminal_state; return state string or None."""
    close = close_cache.get(ticker)
    if close is None and ticker not in close_cache:
        close = _load_close(ticker)
        close_cache[ticker] = close
    if close is None:
        return None

    if ruler == "clean15_126":
        result = terminal_state(
            close, fire_date,
            liftoff_mult=LIFTOFF_15,
            liftoff_horizon=LIFTOFF_HORIZON_126,
        )
    elif ruler == "clean8_21":
        result = terminal_state(
            close, fire_date,
            liftoff_mult=LIFTOFF_8,
            liftoff_horizon=LIFTOFF_HORIZON_21,
        )
    else:
        raise ValueError(f"Unknown ruler: {ruler}")

    return result.get("state")


# ---------------------------------------------------------------------------
# Corpora hash (used to lock --run to a matching --register file)
# ---------------------------------------------------------------------------
def _file_sig(path: Path) -> str:
    """Content hash (SHA-256 first 16KB) for small files; size+mtime for large ones."""
    if not path.exists():
        return "absent"
    stat = path.stat()
    # For small files (< 50MB) take a partial content hash; otherwise size+mtime
    if stat.st_size < 50 * 1024 * 1024:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            h.update(fh.read(16384))  # first 16KB is stable enough for drift detection
        return h.hexdigest()[:16]
    return f"size={stat.st_size}|mtime={int(stat.st_mtime)}"


def _corpora_hash(
    tr_n: int,
    gf_n: int,
    replay_n: int,
    collapse_map: dict | None = None,
) -> str:
    """Stable hash covering corpus sizes, collapse map, and store file signatures.

    Covering collapse_map and the parquet store signatures ensures that a store
    rebuild between --register and --run (e.g. after a data update) breaks the
    hash, forcing a fresh --register.
    """
    collapse_str = json.dumps(sorted((collapse_map or {}).items()), sort_keys=True)
    arch_sig = _file_sig(_ARCHETYPE_PATH)
    pit_sig = _file_sig(_PIT_LABELS_PATH)
    payload = (
        f"tr={tr_n}|gf={gf_n}|replay={replay_n}"
        f"|collapse={collapse_str}"
        f"|arch={arch_sig}"
        f"|pit={pit_sig}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Archetype collapse by n (§4: BEFORE any outcome read)
# ---------------------------------------------------------------------------
def _collapse_archetypes(fires: pd.DataFrame, col: str = "archetype",
                         min_n: int = ARCHETYPE_MIN_N) -> pd.DataFrame:
    """Merge archetypes with attachable-n < min_n into 'other_archetype'.

    The collapse is done by label count only, BEFORE any outcome column is read.
    This preserves the pre-registration epistemic wall.
    """
    fires = fires.copy()
    counts = fires[col].value_counts()
    rare = counts[counts < min_n].index.tolist()
    if rare:
        fires[col] = fires[col].replace(dict.fromkeys(rare, "other_archetype"))
    return fires


# ---------------------------------------------------------------------------
# Two-way cluster-robust bootstrap (ticker × quarter)
# §4 mandate: cite DT-R14 / #1841 time-confound law.
# "Do NOT weaken to one-way clustering" — two-way satisfies the law.
# ---------------------------------------------------------------------------
def _quarter(dates: pd.Series) -> pd.Series:
    """Return 'YYYY-QN' string per date."""
    return dates.dt.to_period("Q").astype(str)


def _build_cluster_index(ids: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """Precompute cluster membership for vectorized two-way bootstrap.

    Returns
    -------
    unique_ids  : sorted array of unique cluster identifiers
    idx_by_id   : list[array] — idx_by_id[k] = row indices belonging to unique_ids[k]

    Precomputing these once per bootstrap call eliminates the per-iteration np.where
    scans required by the nested scheme, cutting cost from O(n_iter * n_clusters * n_rows)
    to O(n_iter * n_clusters) + O(n_rows) precompute.
    """
    unique_ids, inverse = np.unique(ids, return_inverse=True)
    idx_by_id = [np.where(inverse == k)[0] for k in range(len(unique_ids))]
    return unique_ids, idx_by_id


def _two_way_cluster_se(
    outcome: np.ndarray,
    label: np.ndarray,
    ticker_ids: np.ndarray,
    quarter_ids: np.ndarray,
    n_boot: int = 2000,
    rng_seed: int = 42,
) -> dict[str, float]:
    """Genuine two-way cluster bootstrap (ticker × quarter) — DT-R14 / #1841 compliant.

    Estimand: P(STOPPED | label=1) − P(STOPPED | label=0).

    ESTIMATOR (independent-draw two-way scheme)
    --------------------------------------------
    Each bootstrap iteration:
      1. Draw B_T tickers with replacement from all unique tickers (size = n_unique_tickers).
      2. INDEPENDENTLY draw B_Q quarters with replacement from all unique quarters
         (size = n_unique_quarters).
      3. Row i is included with multiplicity mult(i) = count(ticker_i in B_T)
         × count(quarter_i in B_Q), i.e., weighted by the product of both
         draw multiplicities (Cameron, Gelbach, Miller 2011 two-way scheme).
      4. Compute weighted P(STOPPED|label=1) − P(STOPPED|label=0) on the
         resulting weighted sample.

    WHY NESTED-WITHIN IS INVALID: the "resample tickers, then within each selected
    ticker resample that ticker's quarters" scheme is one-way ticker clustering in
    disguise.  Cross-ticker calendar shocks live in the quarter dimension, but
    nested resampling only ever resamples quarters within each individual ticker —
    it never transfers a quarter across tickers.  This leaves the cross-sectional
    component of quarter-level common shocks uncontrolled while the CI ostensibly
    claims two-way validity.  The independent-draw scheme above treats tickers and
    quarters symmetrically.

    VECTORISED IMPLEMENTATION (F4)
    --------------------------------
    Ticker→row and quarter→row index arrays are precomputed ONCE via
    _build_cluster_index.  Per iteration: np.bincount over the drawn cluster
    indices produces a weight vector in O(n_clusters) time; the full row-weight
    array is assembled in O(n_rows) via array indexing — no per-cluster np.where.

    Parameters
    ----------
    outcome      : 0/1 binary outcome array (1 = STOPPED).
    label        : 0/1 binary label array (1 = this cell's personality label).
    ticker_ids   : string array of ticker identifiers.
    quarter_ids  : string array of quarter identifiers (e.g. '2022Q1').
    n_boot       : bootstrap resamples (2000 for registered family).
    rng_seed     : for reproducibility.

    Returns dict with keys:
        observed_delta    : P(STOPPED|label=1) - P(STOPPED|label=0)
        p_value           : two-sided p-value from bootstrap
        ci_lo, ci_hi      : 95% CI from bootstrap percentiles
        n_ticker_clusters : number of unique ticker clusters
        n_quarter_clusters: number of unique quarter clusters
        n_treated         : fires in label=1 group
        n_control         : fires in label=0 group
    """
    rng = np.random.default_rng(rng_seed)

    n1 = int(label.sum())
    n0 = int((1 - label).sum())
    if n1 == 0 or n0 == 0:
        return {
            "observed_delta": float("nan"), "p_value": float("nan"),
            "ci_lo": float("nan"), "ci_hi": float("nan"),
            "n_ticker_clusters": 0, "n_quarter_clusters": 0,
            "n_treated": n1, "n_control": n0,
        }

    # Observed delta
    p1 = float(np.average(outcome[label == 1]))
    p0 = float(np.average(outcome[label == 0]))
    observed_delta = p1 - p0

    # Precompute cluster index maps (F4: done ONCE, not per iteration)
    unique_tickers, t_idx_by_id = _build_cluster_index(ticker_ids)
    unique_quarters, q_idx_by_id = _build_cluster_index(quarter_ids)
    n_tickers = len(unique_tickers)
    n_quarters = len(unique_quarters)
    n_rows = len(outcome)

    # Precompute per-row cluster membership integers (for bincount weight lookup)
    # ticker_inv[i] = index into unique_tickers for row i
    _, ticker_inv = np.unique(ticker_ids, return_inverse=True)
    _, quarter_inv = np.unique(quarter_ids, return_inverse=True)

    boot_deltas: list[float] = []
    for _ in range(n_boot):
        # 1. Draw B_T ticker indices and B_Q quarter indices INDEPENDENTLY
        bt = rng.integers(0, n_tickers, size=n_tickers)   # indices into unique_tickers
        bq = rng.integers(0, n_quarters, size=n_quarters)  # indices into unique_quarters

        # 2. Row weight = count(ticker_i in B_T) * count(quarter_i in B_Q)
        #    via bincount — O(n_clusters) per iteration, no np.where
        t_counts = np.bincount(bt, minlength=n_tickers)   # shape (n_tickers,)
        q_counts = np.bincount(bq, minlength=n_quarters)  # shape (n_quarters,)

        # Row-level weights: product of ticker draw count × quarter draw count
        w = t_counts[ticker_inv].astype(np.float64) * q_counts[quarter_inv].astype(np.float64)

        total_w = w.sum()
        if total_w == 0:
            boot_deltas.append(float("nan"))
            continue

        # Weighted group means
        lbl1 = label == 1
        lbl0 = label == 0
        w1 = w[lbl1]; w0 = w[lbl0]
        sw1 = w1.sum(); sw0 = w0.sum()
        if sw1 == 0 or sw0 == 0:
            boot_deltas.append(float("nan"))
            continue

        bp1 = float(np.dot(outcome[lbl1].astype(np.float64), w1) / sw1)
        bp0 = float(np.dot(outcome[lbl0].astype(np.float64), w0) / sw0)
        boot_deltas.append(bp1 - bp0)

    deltas = np.array([d for d in boot_deltas if not np.isnan(d)])
    if len(deltas) < 100:
        return {
            "observed_delta": observed_delta, "p_value": float("nan"),
            "ci_lo": float("nan"), "ci_hi": float("nan"),
            "n_ticker_clusters": n_tickers, "n_quarter_clusters": n_quarters,
            "n_treated": n1, "n_control": n0,
        }

    # Two-sided p-value: fraction of bootstrap deltas where deviation from the
    # bootstrap mean >= |observed_delta|  (bootstrap pivot test)
    p_value = float(np.mean(np.abs(deltas - deltas.mean()) >= abs(observed_delta)))
    ci_lo = float(np.percentile(deltas, 2.5))
    ci_hi = float(np.percentile(deltas, 97.5))

    return {
        "observed_delta": observed_delta,
        "p_value": p_value,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_ticker_clusters": n_tickers,
        "n_quarter_clusters": n_quarters,
        "n_treated": n1,
        "n_control": n0,
    }


# ---------------------------------------------------------------------------
# BH-FDR correction (Benjamini-Hochberg)
# ---------------------------------------------------------------------------
def _bh_fdr(p_values: list[float], q: float = FDR_Q) -> list[bool]:
    """Benjamini-Hochberg FDR correction; returns per-hypothesis reject flags."""
    m = len(p_values)
    if m == 0:
        return []
    arr = np.array(p_values, dtype=float)
    order = np.argsort(arr)
    sorted_p = arr[order]
    reject = np.zeros(m, dtype=bool)
    for i in range(m - 1, -1, -1):
        if sorted_p[i] <= q * (i + 1) / m:
            reject[order[:i + 1]] = True
            break
    return reject.tolist()


# ---------------------------------------------------------------------------
# Disguise regression (§4: outcome ~ label + sector FE + log_mktcap + era FE)
# ---------------------------------------------------------------------------
def _load_ticker_sectors() -> dict[str, str]:
    """Load ticker → sector mapping."""
    if not _TICKER_SECTORS_PATH.exists():
        return {}
    df = pd.read_parquet(_TICKER_SECTORS_PATH)
    return dict(zip(df["ticker"].astype(str), df["sector"].astype(str)))


def _disguise_regression(
    outcome: np.ndarray,
    label: np.ndarray,
    tickers: np.ndarray,
    dates: pd.Series,
    archetype_mktcap: pd.Series | None,
    sector_map: dict[str, str],
    ticker_ids: np.ndarray,
    quarter_ids: np.ndarray,
    n_boot: int = 1000,
    rng_seed: int = 99,
) -> dict[str, Any]:
    """Cluster-robust OLS disguise regression: outcome ~ label + sector FE + log_mktcap + era FE.

    Controls:
    - sector FE: from ticker_sectors.parquet
    - log_mktcap: from archetype history if market_cap available, else treated as missing → None noted
    - era FE: decade (e.g. '2010s')

    Returns dict with:
        label_coef     : OLS label coefficient
        label_p        : cluster-robust p-value (bootstrap)
        ci_lo, ci_hi   : 95% CI on label coefficient
        n              : fires in regression
        survives_controls : bool (label_p < 0.05 with controls)
        mktcap_available  : bool
        n_sectors, n_eras : count of fixed-effect levels
    """
    try:
        return _disguise_regression_impl(
            outcome, label, tickers, dates, archetype_mktcap,
            sector_map, ticker_ids, quarter_ids, n_boot, rng_seed,
        )
    except Exception as exc:
        log.warning("Disguise regression failed: %s", exc)
        return {"label_coef": float("nan"), "label_p": float("nan"),
                "ci_lo": float("nan"), "ci_hi": float("nan"),
                "n": len(outcome), "survives_controls": False,
                "mktcap_available": False, "n_sectors": 0, "n_eras": 0,
                "error": str(exc)}


def _era_label(d: pd.Timestamp) -> str:
    return f"{(d.year // 10) * 10}s"


def _disguise_regression_impl(
    outcome, label, tickers, dates, archetype_mktcap,
    sector_map, ticker_ids, quarter_ids, n_boot, rng_seed,
) -> dict[str, Any]:
    """Inner implementation of disguise regression (OLS with cluster-robust SEs via bootstrap)."""
    n = len(outcome)
    df = pd.DataFrame({
        "y": outcome.astype(float),
        "label": label.astype(float),
        "ticker": tickers,
        "date": dates.reset_index(drop=True) if hasattr(dates, 'reset_index') else pd.Series(dates),
        "ticker_id": ticker_ids,
        "quarter_id": quarter_ids,
    })
    df["sector"] = df["ticker"].map(lambda t: sector_map.get(str(t), "Unknown"))
    df["era"] = df["date"].apply(_era_label)

    # log_mktcap: use market_cap from archetype history if present
    df["log_mktcap"] = float("nan")
    mktcap_available = False
    if archetype_mktcap is not None and len(archetype_mktcap) == n:
        vals = archetype_mktcap.values
        valid = vals > 0
        if valid.sum() > 0.5 * n:
            df["log_mktcap"] = np.where(valid, np.log(np.where(valid, vals, 1.0)), float("nan"))
            mktcap_available = True

    # Build OLS design matrix with sector + era FE (dummy encoding, drop first)
    sectors = df["sector"].unique().tolist()
    eras = df["era"].unique().tolist()
    n_sectors = len(sectors)
    n_eras = len(eras)

    # Feature columns: label, sector dummies (drop first), era dummies (drop first), log_mktcap
    X_parts = [df[["label"]].copy()]

    for i, s in enumerate(sorted(sectors)[1:]):  # drop first sector
        X_parts.append(pd.DataFrame({f"sec_{i}": (df["sector"] == s).astype(float)}))

    for i, e in enumerate(sorted(eras)[1:]):  # drop first era
        X_parts.append(pd.DataFrame({f"era_{i}": (df["era"] == e).astype(float)}))

    if mktcap_available:
        mc = df["log_mktcap"].fillna(df["log_mktcap"].median())
        X_parts.append(pd.DataFrame({"log_mktcap": mc}))

    X = pd.concat(X_parts, axis=1)
    X.insert(0, "intercept", 1.0)
    X_arr = X.values.astype(float)
    y_arr = df["y"].values.astype(float)

    # Remove rows with NaN in X
    valid_rows = np.isfinite(X_arr).all(axis=1) & np.isfinite(y_arr)
    X_arr = X_arr[valid_rows]
    y_arr = y_arr[valid_rows]
    t_ids = ticker_ids[valid_rows]
    q_ids = quarter_ids[valid_rows]

    if X_arr.shape[0] < X_arr.shape[1] + 5:
        raise ValueError(f"Too few valid rows ({X_arr.shape[0]}) for regression")

    # OLS: beta = (X'X)^-1 X'y
    try:
        XtX = X_arr.T @ X_arr
        Xty = X_arr.T @ y_arr
        beta = np.linalg.lstsq(XtX, Xty, rcond=None)[0]
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"OLS failed: {exc}") from exc

    label_idx = 1  # "label" is second column (after intercept)
    observed_coef = float(beta[label_idx])

    # Genuine two-way cluster bootstrap for the label coefficient (F1+F4).
    # Matches the estimator used in _two_way_cluster_se: independent draws of
    # tickers and quarters; row weight = count_ticker × count_quarter.
    rng = np.random.default_rng(rng_seed)

    # Precompute cluster index maps once
    _, t_inv = np.unique(t_ids, return_inverse=True)
    _, q_inv = np.unique(q_ids, return_inverse=True)
    n_tickers = int(t_inv.max()) + 1
    n_quarters = int(q_inv.max()) + 1

    boot_coefs: list[float] = []
    for _ in range(n_boot):
        # Independent draws for both dimensions
        bt = rng.integers(0, n_tickers, size=n_tickers)
        bq = rng.integers(0, n_quarters, size=n_quarters)

        t_counts = np.bincount(bt, minlength=n_tickers)
        q_counts = np.bincount(bq, minlength=n_quarters)
        w = (t_counts[t_inv] * q_counts[q_inv]).astype(np.float64)
        if w.sum() == 0:
            continue

        # Weighted OLS: (X'WX)^-1 X'Wy
        W = np.diag(w)
        bX = X_arr
        by = y_arr
        try:
            XtWX = bX.T @ (w[:, None] * bX)
            XtWy = bX.T @ (w * by)
            bbeta = np.linalg.lstsq(XtWX, XtWy, rcond=None)[0]
            boot_coefs.append(float(bbeta[label_idx]))
        except Exception:
            continue

    if len(boot_coefs) < 50:
        return {"label_coef": observed_coef, "label_p": float("nan"),
                "ci_lo": float("nan"), "ci_hi": float("nan"),
                "n": int(valid_rows.sum()), "survives_controls": False,
                "mktcap_available": mktcap_available, "n_sectors": n_sectors,
                "n_eras": n_eras}

    boot_arr = np.array(boot_coefs)
    p_value = float(np.mean(np.abs(boot_arr - boot_arr.mean()) >= abs(observed_coef)))
    ci_lo = float(np.percentile(boot_arr, 2.5))
    ci_hi = float(np.percentile(boot_arr, 97.5))

    return {
        "label_coef": observed_coef,
        "label_p": p_value,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n": int(valid_rows.sum()),
        "survives_controls": p_value < 0.05,
        "mktcap_available": mktcap_available,
        "n_sectors": n_sectors,
        "n_eras": n_eras,
    }


# ---------------------------------------------------------------------------
# --register mode
# ---------------------------------------------------------------------------
def cmd_register(args: argparse.Namespace, smoke: bool = False,
                 smoke_tickers: list[str] | None = None) -> dict[str, Any]:
    """Count corpora, collapse archetypes by n (BEFORE outcomes), write registration.

    F6: refuses to overwrite an existing registration file unless --force is given.
    """
    # F6: guard against silent overwrite of an existing non-smoke registration
    if not smoke:
        if _REGISTRATION_PATH.exists() and not getattr(args, "force", False):
            log.error(
                "Registration file already exists: %s. "
                "Pass --force to overwrite (this invalidates any previous --run).",
                _REGISTRATION_PATH,
            )
            sys.exit(1)

    log.info("[REGISTER] Loading corpora...")
    tr_fires = _load_track_record_corpus()
    gf_fires = _load_gate_fires_corpus()
    replay_fires = _load_replay_corpus(
        Path(args.replay_root) if getattr(args, "replay_root", None) else None
    )

    if smoke and smoke_tickers:
        st_set = set(smoke_tickers)
        tr_fires = tr_fires[tr_fires["ticker"].isin(st_set)] if "ticker" in tr_fires.columns else tr_fires
        gf_fires = gf_fires[gf_fires["ticker"].isin(st_set)] if "ticker" in gf_fires.columns else gf_fires
        replay_fires = replay_fires[replay_fires["ticker"].isin(st_set)] if "ticker" in replay_fires.columns else replay_fires

    tr_n = len(tr_fires)
    gf_n = len(gf_fires)
    replay_n = len(replay_fires)

    log.info("Corpus sizes: track_record=%d, gate_fires=%d, replay=%d",
             tr_n, gf_n, replay_n)

    # Attach archetype PIT labels (BEFORE outcome read, to count attachable n)
    arch_lookup = _load_archetype_history()
    log.info("Archetype history: %d tickers", len(arch_lookup))

    def _attach_archetype(fires: pd.DataFrame) -> pd.DataFrame:
        if fires.empty or "ticker" not in fires.columns:
            return fires
        fires = fires.copy()
        fires["archetype_pit"] = [
            _archetype_pit(str(r.ticker), r.date, arch_lookup)
            for r in fires.itertuples()
        ]
        return fires

    tr_fires = _attach_archetype(tr_fires)
    gf_fires = _attach_archetype(gf_fires)

    # Collapse by n ONLY (no outcome read yet)
    all_fires = pd.concat([
        df for df in [tr_fires, gf_fires, replay_fires] if not df.empty
    ], ignore_index=True)

    if not all_fires.empty and "archetype_pit" in all_fires.columns:
        all_fires = _collapse_archetypes(all_fires, col="archetype_pit",
                                         min_n=ARCHETYPE_MIN_N)
        collapsed_archetypes = sorted(all_fires["archetype_pit"].dropna().unique().tolist())
    else:
        collapsed_archetypes = ["other_archetype"]

    # F7: include collapse map in the hash so a different collapse (data update) breaks the hash
    # Build collapse_map: original_label -> post-collapse label
    if not all_fires.empty and "archetype_pit" in all_fires.columns:
        arch_counts_raw = all_fires["archetype_pit"].value_counts().to_dict()
    else:
        arch_counts_raw = {}
    collapse_map: dict[str, str] = {
        k: (k if k in collapsed_archetypes else "other_archetype")
        for k in arch_counts_raw
    }
    corpus_hash = _corpora_hash(tr_n, gf_n, replay_n, collapse_map=collapse_map)
    log.info("Corpus hash: %s", corpus_hash)

    # Enumerate cell family
    family_cells: list[dict[str, Any]] = []
    for label in CHART_LABELS:
        family_cells.append({"axis": "chart_personality", "label": label,
                              "primary": "P(STOPPED)", "ruler": PRIMARY_RULER})
    for label in MICRO_LABELS:
        family_cells.append({"axis": "microstructure", "label": label,
                              "primary": "P(STOPPED)", "ruler": PRIMARY_RULER})
    for label in collapsed_archetypes:
        if label:
            family_cells.append({"axis": "archetype", "label": label,
                                  "primary": "P(STOPPED)", "ruler": PRIMARY_RULER})

    n_cells = len(family_cells)
    # × corpora: track_record + gate_fires (+ replay if present)
    n_corpora = 2 + (1 if replay_n > 0 else 0)
    total_hypotheses = n_cells * n_corpora

    log.info("Cell family: %d cells × %d corpora = %d hypotheses total",
             n_cells, n_corpora, total_hypotheses)

    # Archetype coverage summary
    if "archetype_pit" in all_fires.columns:
        arch_counts = all_fires["archetype_pit"].value_counts().to_dict()
    else:
        arch_counts = {}

    registration: dict[str, Any] = {
        "study": "stock_personality_compat_phase0",
        "registered_at": str(_date.today()),
        "fdr_family": FDR_FAMILY,
        "fdr_q": FDR_Q,
        "min_cell_n": MIN_CELL_N,
        "archetype_collapse_min_n": ARCHETYPE_MIN_N,
        "primary_ruler": PRIMARY_RULER,
        "alt_ruler": ALT_RULER,
        "inference": "two_way_cluster_bootstrap (ticker x quarter) — satisfies DT-R14 / #1841 time-confound law",
        "corpus_sizes": {
            CORPUS_TRACK_RECORD: tr_n,
            CORPUS_GATE_FIRES: gf_n,
            CORPUS_REPLAY: replay_n,
        },
        "corpus_hash": corpus_hash,
        "collapsed_archetypes": collapsed_archetypes,
        "archetype_attachable_n_by_label": arch_counts,
        "cell_family": family_cells,
        "n_cells": n_cells,
        "n_corpora": n_corpora,
        "total_registered_hypotheses": total_hypotheses,
        "smoke": smoke,
        "watermarks": [
            "FY2009+ archetype PIT coverage only (R-SP12)",
            "Survivorship-flagged: data/stocks deep corpus is 220 names (survivors only)",
            "gap-features-unavailable: data/stocks has no open column",
        ],
    }

    out_path = (
        Path("/tmp/personality_compat_registration_smoke.json")
        if smoke else _REGISTRATION_PATH
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(registration, f, indent=2, default=str)
    log.info("Registration written: %s", out_path)

    # Register trial budget in trial_ledger (not in smoke mode)
    if not smoke:
        reason = (
            f"{total_hypotheses} = {n_cells} cells × {n_corpora} corpora; "
            f"chart({len(CHART_LABELS)}) + micro({len(MICRO_LABELS)}) + "
            f"archetype_collapsed({len(collapsed_archetypes)}); "
            f"fdr_family={FDR_FAMILY}"
        )
        led = TrialLedger(_LEDGER_PATH)
        with register_trials(
            FDR_FAMILY,
            budget=total_hypotheses,
            reason=reason,
            basis="itemized",
            ledger=led,
        ):
            pass
        log.info("Trial ledger updated: family=%s budget=%d", FDR_FAMILY, total_hypotheses)

    return registration


# ---------------------------------------------------------------------------
# --run mode
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace, smoke: bool = False,
            smoke_tickers: list[str] | None = None,
            n_boot: int = 2000) -> None:
    """Grade fires, attach PIT labels, primary test, BH-FDR, disguise regression."""

    # Verify registration file exists and matches corpora hash
    reg_path = (
        Path("/tmp/personality_compat_registration_smoke.json")
        if smoke else _REGISTRATION_PATH
    )
    if not reg_path.exists():
        log.error("No registration file found at %s. Run --register first.", reg_path)
        if not smoke:
            sys.exit(1)
        # In smoke mode, auto-register first
        log.info("[SMOKE] Auto-registering before run...")
        registration = cmd_register(args, smoke=True, smoke_tickers=smoke_tickers)
    else:
        with open(reg_path) as f:
            registration = json.load(f)

    log.info("[RUN] Loading corpora...")
    tr_fires = _load_track_record_corpus()
    gf_fires = _load_gate_fires_corpus()
    replay_fires = _load_replay_corpus(
        Path(args.replay_root) if getattr(args, "replay_root", None) else None
    )

    if smoke and smoke_tickers:
        st_set = set(smoke_tickers)
        tr_fires = tr_fires[tr_fires["ticker"].isin(st_set)] if "ticker" in tr_fires.columns else tr_fires
        gf_fires = gf_fires[gf_fires["ticker"].isin(st_set)] if "ticker" in gf_fires.columns else gf_fires
        replay_fires = replay_fires[replay_fires["ticker"].isin(st_set)] if "ticker" in replay_fires.columns else replay_fires

    # Verify corpus hash (only in non-smoke mode)
    if not smoke:
        tr_n = len(tr_fires)
        gf_n = len(gf_fires)
        replay_n = len(replay_fires)
        current_hash = _corpora_hash(tr_n, gf_n, replay_n)
        registered_hash = registration.get("corpus_hash", "")
        if current_hash != registered_hash:
            log.error(
                "Corpus hash mismatch: registered=%s current=%s. "
                "Re-run --register to refresh.",
                registered_hash, current_hash,
            )
            sys.exit(1)
        log.info("Corpus hash verified: %s", current_hash)

    # Load PIT labels
    pit_lookup = _load_pit_labels()
    pit_available = len(pit_lookup) > 0
    if not pit_available:
        log.warning(
            "personality_pit_labels.parquet not found; chart/micro labels will be null. "
            "Run scripts/build_stock_personality.py first."
        )

    # Load archetype history
    arch_lookup = _load_archetype_history()
    collapsed_archetypes = set(registration.get("collapsed_archetypes", []))

    # Load sector map and close cache
    sector_map = _load_ticker_sectors()
    close_cache: dict[str, pd.Series | None] = {}

    log.info("[RUN] Grading fires and attaching labels...")
    all_rows: list[dict[str, Any]] = []

    for corpus_name, corpus_fires in [
        (CORPUS_TRACK_RECORD, tr_fires),
        (CORPUS_GATE_FIRES, gf_fires),
        (CORPUS_REPLAY, replay_fires),
    ]:
        if corpus_fires.empty:
            log.info("Corpus %s: EMPTY (skip)", corpus_name)
            continue
        log.info("Corpus %s: %d fires", corpus_name, len(corpus_fires))

        for i, row in enumerate(corpus_fires.itertuples()):
            ticker = str(row.ticker)
            fire_date = pd.Timestamp(row.date)

            # Grade via engine/grading.py ONLY (R-SP11)
            # Try pre-graded state columns first; regrade if absent or null
            state_15_126 = getattr(row, "terminal_state_clean15_126", None)
            state_8_21 = getattr(row, "terminal_state_clean8_21", None)

            if not isinstance(state_15_126, str) or state_15_126 not in {
                TerminalState.STOPPED, TerminalState.DEAD_MONEY,
                TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF,
            }:
                state_15_126 = _grade_fire(ticker, fire_date, close_cache, "clean15_126")

            if not isinstance(state_8_21, str) or state_8_21 not in {
                TerminalState.STOPPED, TerminalState.DEAD_MONEY,
                TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF,
            }:
                state_8_21 = _grade_fire(ticker, fire_date, close_cache, "clean8_21")

            # Primary outcome (P(STOPPED) at clean15_126)
            if state_15_126 is None:
                stopped_primary = None
            else:
                stopped_primary = 1 if state_15_126 == TerminalState.STOPPED else 0

            # Archetype PIT label
            archetype = _archetype_pit(ticker, fire_date, arch_lookup)
            # Apply collapse
            if archetype is not None and archetype not in collapsed_archetypes and "other_archetype" in collapsed_archetypes:
                archetype = "other_archetype"

            # Chart + micro PIT labels
            labels = _chart_micro_at(ticker, fire_date, pit_lookup)

            # Secondaries
            dead_money = (1 if state_15_126 == TerminalState.DEAD_MONEY else 0) if state_15_126 else None
            clean_liftoff = (1 if state_15_126 == TerminalState.CLEAN_LIFTOFF else 0) if state_15_126 else None

            fwd_mfe_21 = getattr(row, "fwd_mfe_21", None)
            fwd_mdd_21 = getattr(row, "fwd_mdd_21", None)

            all_rows.append({
                "corpus": corpus_name,
                "ticker": ticker,
                "date": fire_date,
                "quarter": _quarter(pd.Series([fire_date])).iloc[0],
                "archetype_pit": archetype,
                "chart_primary": labels["chart_primary"],
                "micro_primary": labels["micro_primary"],
                "state_15_126": state_15_126,
                "state_8_21": state_8_21,
                "stopped_primary": stopped_primary,
                "dead_money": dead_money,
                "clean_liftoff": clean_liftoff,
                "fwd_mfe_21": fwd_mfe_21,
                "fwd_mdd_21": fwd_mdd_21,
            })

            if (i + 1) % 500 == 0:
                log.info("  %s: %d/%d graded", corpus_name, i + 1, len(corpus_fires))

    if not all_rows:
        log.error("No graded rows produced.")
        return

    graded = pd.DataFrame(all_rows)
    log.info("Graded %d fires total", len(graded))

    # --- Primary analysis: P(STOPPED) per cell ---
    log.info("[RUN] Running primary cell tests (two-way cluster-robust)...")

    axes_to_test = {
        "chart_personality": ("chart_primary", CHART_LABELS),
        "microstructure": ("micro_primary", MICRO_LABELS),
        "archetype": ("archetype_pit", list(collapsed_archetypes)),
    }

    cell_results: list[dict[str, Any]] = []
    for corpus_name in [CORPUS_TRACK_RECORD, CORPUS_GATE_FIRES]:
        c_data = graded[graded["corpus"] == corpus_name].copy()
        if c_data.empty:
            continue
        c_data_with_outcome = c_data[c_data["stopped_primary"].notna()].copy()
        baseline_p = c_data_with_outcome["stopped_primary"].mean() if len(c_data_with_outcome) > 0 else float("nan")
        n_corpus = len(c_data_with_outcome)
        log.info("Corpus %s: %d gradable fires, baseline P(STOPPED)=%.3f",
                 corpus_name, n_corpus, baseline_p)

        for axis, (col, labels) in axes_to_test.items():
            if col not in c_data_with_outcome.columns:
                continue
            for label_val in labels:
                cell_data = c_data_with_outcome[c_data_with_outcome[col] == label_val]
                n_cell = len(cell_data)
                if n_cell < MIN_CELL_N:
                    cell_results.append({
                        "corpus": corpus_name,
                        "axis": axis,
                        "label": label_val,
                        "n": n_cell,
                        "status": "insufficient_n",
                        "p_value": None, "observed_delta": None,
                        "ci_lo": None, "ci_hi": None,
                        "baseline_p_stopped": baseline_p,
                        "n_ticker_clusters": None, "n_quarter_clusters": None,
                    })
                    continue

                # Two-way cluster-robust bootstrap
                outcome = cell_data["stopped_primary"].values.astype(float)
                label_mask = np.ones(len(cell_data), dtype=float)  # all are this label
                # For delta: compare label vs rest of corpus
                rest = c_data_with_outcome[c_data_with_outcome[col] != label_val]
                if len(rest) == 0:
                    continue

                combined = pd.concat([cell_data, rest], ignore_index=True)
                combined_outcome = combined["stopped_primary"].values.astype(float)
                combined_label = np.array(
                    [1.0] * len(cell_data) + [0.0] * len(rest)
                )
                combined_tickers = combined["ticker"].values.astype(str)
                combined_quarters = combined["quarter"].values.astype(str)

                stats = _two_way_cluster_se(
                    combined_outcome, combined_label,
                    combined_tickers, combined_quarters,
                    n_boot=n_boot,
                )

                cell_results.append({
                    "corpus": corpus_name,
                    "axis": axis,
                    "label": label_val,
                    "n": n_cell,
                    "status": "tested",
                    "p_value": stats.get("p_value"),
                    "observed_delta": stats.get("observed_delta"),
                    "ci_lo": stats.get("ci_lo"),
                    "ci_hi": stats.get("ci_hi"),
                    "baseline_p_stopped": baseline_p,
                    "n_ticker_clusters": stats.get("n_ticker_clusters"),
                    "n_quarter_clusters": stats.get("n_quarter_clusters"),
                })

    # BH-FDR across all tested cells
    tested = [r for r in cell_results if r["status"] == "tested"
              and r.get("p_value") is not None and not math.isnan(r.get("p_value", float("nan")))]
    all_p = [r["p_value"] for r in tested]
    reject_flags = _bh_fdr(all_p, q=FDR_Q)
    for r, flag in zip(tested, reject_flags):
        r["fdr_reject"] = flag

    fdr_survivors = [r for r in tested if r.get("fdr_reject", False)]
    log.info("FDR survivors: %d / %d tested cells", len(fdr_survivors), len(tested))

    # Disguise regression for FDR survivors
    sector_map = _load_ticker_sectors()
    for r in fdr_survivors:
        corpus_name = r["corpus"]
        axis = r["axis"]
        label_val = r["label"]
        col = axes_to_test[axis][0]

        c_data = graded[(graded["corpus"] == corpus_name) & graded["stopped_primary"].notna()].copy()
        label_col_val = (c_data[col] == label_val).astype(int)
        outcome = c_data["stopped_primary"].values.astype(float)
        label_arr = label_col_val.values.astype(float)
        tickers = c_data["ticker"].values.astype(str)
        dates = c_data["date"]
        t_ids = tickers
        q_ids = c_data["quarter"].values.astype(str)

        disguise = _disguise_regression(
            outcome, label_arr, tickers, dates,
            None,  # mktcap: archetype history doesn't have market_cap column
            sector_map, t_ids, q_ids,
        )
        r["disguise"] = disguise
        if not disguise.get("survives_controls", False):
            r["verdict"] = "redundant_with_sector_size"
            log.info("Cell %s/%s/%s: REDUNDANT after disguise controls", corpus_name, axis, label_val)
        else:
            r["verdict"] = "survives_disguise"
            log.info("Cell %s/%s/%s: SURVIVES disguise controls", corpus_name, axis, label_val)

    # --- Write outputs ---
    out_path = Path("/tmp/personality_compat_phase0_smoke.parquet") if smoke else _OUT_PARQUET
    out_path.parent.mkdir(parents=True, exist_ok=True)
    graded.to_parquet(out_path, index=False)
    log.info("Output parquet: %s", out_path)

    # --- Generate report ---
    report_path = Path("/tmp/STOCK_PERSONALITY_SETUP_COMPAT_PHASE0_SMOKE.md") if smoke else _OUT_REPORT
    _write_report(report_path, registration, cell_results, graded, fdr_survivors, smoke)
    log.info("Report: %s", report_path)


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------
def _write_report(
    path: Path,
    registration: dict,
    cell_results: list[dict],
    graded: pd.DataFrame,
    fdr_survivors: list[dict],
    smoke: bool,
) -> None:
    """Write the Phase-0 report markdown with honest nulls, watermarks, limitations."""
    path.parent.mkdir(parents=True, exist_ok=True)

    smoke_tag = " — [SMOKE WATERMARK: not for publication]" if smoke else ""
    lines: list[str] = []

    lines += [
        f"# Stock-Personality Setup Compatibility — Phase 0{smoke_tag}",
        "",
        "> **Pre-registration note:** trial family registered under `stock_personality_compat`",
        "> in `data/trial_ledger.jsonl` BEFORE any outcome was read (R-SP11).",
        "> Every null result is printed; no cell is silently dropped.",
        "> FY2009+ archetype PIT coverage only (R-SP12).",
        "> Survivorship-flagged: deep corpus is 220-name survivor panel.",
        "",
        "## 1. Registration summary",
        "",
        f"- Registration date: {registration.get('registered_at', '?')}",
        f"- FDR family: `{registration.get('fdr_family', '?')}` | q={registration.get('fdr_q', 0.05)}",
        f"- Primary ruler: `{registration.get('primary_ruler', '?')}` (P(STOPPED) binary)",
        f"- Inference: {registration.get('inference', '?')}",
        f"- Minimum cell n: {registration.get('min_cell_n', 50)} (cells below this: insufficient_n, not tested)",
        f"- Archetype collapse min_n: {registration.get('archetype_collapse_min_n', 400)} (merged into 'other_archetype')",
        "",
        "**Corpus sizes (registered):**",
        "",
        f"| Corpus | n |",
        f"|--------|---|",
    ]
    for k, v in registration.get("corpus_sizes", {}).items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        f"Total registered hypotheses: **{registration.get('total_registered_hypotheses', '?')}**",
        "",
        "## 2. Analyzable-n per axis",
        "",
    ]

    # Analyzable n table from graded data
    if not graded.empty:
        for corpus_name in graded["corpus"].unique():
            c = graded[(graded["corpus"] == corpus_name) & graded["stopped_primary"].notna()]
            lines.append(f"### {corpus_name} (n_gradable={len(c)})")
            lines.append("")
            for axis, (col, _) in [
                ("chart_personality", ("chart_primary", None)),
                ("microstructure", ("micro_primary", None)),
                ("archetype", ("archetype_pit", None)),
            ]:
                if col in c.columns:
                    counts = c[col].value_counts()
                    lines.append(f"**{axis}** label distribution:")
                    lines.append("")
                    lines.append("| label | n | testable |")
                    lines.append("|-------|---|----------|")
                    for lbl, cnt in counts.items():
                        testable = "yes" if cnt >= MIN_CELL_N else "no (insufficient_n)"
                        lines.append(f"| {lbl} | {cnt} | {testable} |")
                    lines.append("")

    # F8: BH denominator note
    n_tested_cells = sum(1 for r in cell_results if r.get("status") == "tested")
    n_insuf_cells = sum(1 for r in cell_results if r.get("status") == "insufficient_n")
    lines += [
        "## 3. Primary results (P(STOPPED) delta, two-way cluster-robust)",
        "",
        "> **Time-confound citation (DT-R14 / #1841):** ticker-cluster CIs WITHOUT",
        "> time control are anti-conservative. The two-way (ticker × quarter) clustering",
        "> below satisfies the calendar-time control law. Do NOT interpret one-way",
        "> ticker-only CIs as the primary inference.",
        "",
        f"> **BH denominator = {n_tested_cells} tested cells** (insufficient_n cells are never",
        f"> tested per R-SP11 and excluded; {n_insuf_cells} cells excluded on this basis).",
        "> The registered budget is the conservative pre-declared upper bound covering all cells",
        "> including those that turn out to have insufficient n.",
        "",
        "| corpus | axis | label | n | delta | p_value | ci_lo | ci_hi | BH-reject | n_ticker_clust | n_quarter_clust | status |",
        "|--------|------|-------|---|-------|---------|-------|-------|-----------|----------------|-----------------|--------|",
    ]
    for r in cell_results:
        if r.get("status") == "insufficient_n":
            lines.append(
                f"| {r['corpus']} | {r['axis']} | {r['label']} | {r['n']} "
                f"| — | — | — | — | — | — | — | insufficient_n |"
            )
        else:
            delta = f"{r.get('observed_delta', float('nan')):.4f}" if r.get('observed_delta') is not None else "—"
            pv = f"{r.get('p_value', float('nan')):.4f}" if r.get('p_value') is not None else "—"
            cil = f"{r.get('ci_lo', float('nan')):.4f}" if r.get('ci_lo') is not None else "—"
            cih = f"{r.get('ci_hi', float('nan')):.4f}" if r.get('ci_hi') is not None else "—"
            bhr = "YES" if r.get("fdr_reject") else ("no" if "fdr_reject" in r else "—")
            ntc = str(r.get("n_ticker_clusters", "—"))
            nqc = str(r.get("n_quarter_clusters", "—"))
            lines.append(
                f"| {r['corpus']} | {r['axis']} | {r['label']} | {r['n']} "
                f"| {delta} | {pv} | {cil} | {cih} | {bhr} | {ntc} | {nqc} | tested |"
            )

    # F5: check if mktcap was available in any survivor's disguise run
    any_mktcap = any(r.get("disguise", {}).get("mktcap_available", False) for r in fdr_survivors)
    mktcap_note = (
        "> **log(mktcap) INCLUDED** in disguise regression (market_cap column present)."
        if any_mktcap else
        "> **log(mktcap) OMITTED** from disguise regression: `market_cap` column unavailable"
        " in archetype history for this run. Size confound is only partially controlled"
        " via sector fixed effects. Interpret disguise verdict with this caveat."
    )
    lines += [
        "",
        "## 4. Disguise verdict (FDR survivors only)",
        "",
        "Regression: `outcome ~ label + sector FE + log(mktcap) + era FE`, cluster-robust.",
        "A label stamped `redundant_with_sector_size` is barred from chips implying differentiation.",
        "",
        mktcap_note,
        "",
    ]
    if not fdr_survivors:
        lines.append("**No FDR survivors — all null (pre-committed expected outcome; descriptive card unchanged).**")
        lines.append("")
    else:
        for r in fdr_survivors:
            d = r.get("disguise", {})
            verdict = r.get("verdict", "?")
            # F5: per-survivor mktcap note
            mc_flag = "" if d.get("mktcap_available", False) else " [log(mktcap) OMITTED — size confound partial]"
            lines.append(
                f"- **{r['corpus']} / {r['axis']} / {r['label']}**: "
                f"label_coef={d.get('label_coef', float('nan')):.4f} "
                f"p={d.get('label_p', float('nan')):.4f} "
                f"CI=[{d.get('ci_lo', float('nan')):.4f}, {d.get('ci_hi', float('nan')):.4f}] "
                f"→ **{verdict}**{mc_flag}"
            )

    lines += [
        "",
        "## 5. Secondaries (descriptive)",
        "",
        "Secondaries P(DEAD_MONEY), P(CLEAN_LIFTOFF), MAE/MFE are descriptive;",
        "not tested for significance; not BH-corrected.",
        "",
    ]
    if not graded.empty:
        for col, name in [("dead_money", "P(DEAD_MONEY)"), ("clean_liftoff", "P(CLEAN_LIFTOFF)")]:
            if col in graded.columns:
                by_corpus = graded[graded[col].notna()].groupby("corpus")[col].mean()
                lines.append(f"**{name} by corpus:**")
                for cn, v in by_corpus.items():
                    lines.append(f"- {cn}: {v:.3f}")
                lines.append("")

    lines += [
        "## 6. Honest limitations",
        "",
        "- **gap-features-unavailable on deep corpus:** `data/stocks` has no `open` column.",
        "  Features `event_gap_contrib_252` and `gap_share_252` are NaN for the deep 220-name",
        "  panel; labels that depend on them (event_gapper) may be systematically unattached.",
        "- **Survivorship bias:** deep 220-name corpus is today's survivors; pre-2009 fires",
        "  are graded on survivor prices — counts are UPPER BOUNDS on favorable outcomes.",
        "  Watermark: FY2009+ archetype PIT coverage only.",
        "- **Two-way clustering (DT-R14 / #1841):** ticker × quarter clustering satisfies",
        "  the time-confound law (#1841, Phase A gate amendments). Weakening to one-way",
        "  ticker-only clustering is prohibited by house law.",
        "- **PIT archetype join:** FY2009+ only; ~57% of deep-history fires pre-date the",
        "  first attachable row and carry archetype_pit=null (printed per cell, never filled).",
        "- **chart/micro labels:** available only for tickers in personality_pit_labels.parquet.",
        "  If that file is absent, chart+micro axis cells will all be null.",
        "- **dna_class / ownership_habitat:** NOT retro-attachable (partition history 2025-06;",
        "  ownership stores snapshot-grade). Excluded from retro study; forward-ledger only.",
        "- **Replay corpus:** skipped when --replay-root absent (SKIP noted here).",
        "",
    ]
    if smoke:
        lines.append(
            "---\n\n**[SMOKE WATERMARK]** This report is a smoke-test output on a small"
        )
        lines.append("subset of tickers. Results are not valid for scientific conclusions.")

    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# --smoke mode
# ---------------------------------------------------------------------------
def cmd_smoke(args: argparse.Namespace, n_tickers: int) -> None:
    """Full pipeline on N tickers; SMOKE watermark; no ledger writes; outputs to /tmp.

    F2: builds per-ticker PIT labels via build_stock_personality.py FIRST so that
    chart/micro cells are populated end-to-end in the smoke run.  Without this step,
    personality_pit_labels.parquet is absent and all chart/micro cells return null.
    """
    log.info("[SMOKE] Pipeline on %d tickers", n_tickers)

    # Pick N tickers from deep panel
    stock_dir = _STOCKS_DEEP_DIR
    if not stock_dir.exists():
        log.error("data/stocks not found")
        return
    all_tickers = sorted(p.stem for p in stock_dir.glob("*.parquet"))[:n_tickers]
    log.info("[SMOKE] Tickers: %s", all_tickers)

    # F2: build PIT personality labels for the smoke tickers before running compat study
    pit_out = Path("/tmp/personality_pit_labels_smoke.parquet")
    tickers_csv = ",".join(all_tickers)
    log.info("[SMOKE] Building per-ticker PIT labels → %s ...", pit_out)
    import subprocess
    build_script = _REPO_ROOT / "scripts" / "build_stock_personality.py"
    result = subprocess.run(
        [
            sys.executable, str(build_script),
            "--tickers", tickers_csv,
            "--panel", "deep",
            "--out", str(pit_out),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning(
            "[SMOKE] build_stock_personality.py failed (chart/micro cells will be null):\n%s",
            result.stderr[-2000:] if result.stderr else "(no stderr)",
        )
    else:
        log.info("[SMOKE] PIT labels built: %s", pit_out)
        # Redirect the module-level path so _load_pit_labels() picks up the smoke file
        global _PIT_LABELS_PATH
        _PIT_LABELS_PATH = pit_out

    # Register (no ledger write)
    registration = cmd_register(args, smoke=True, smoke_tickers=all_tickers)

    # Run with reduced bootstrap iterations for speed in smoke mode
    cmd_run(args, smoke=True, smoke_tickers=all_tickers, n_boot=200)

    log.info("[SMOKE] Done. Outputs in /tmp/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stock-personality compatibility phase-0 harness (§4 pre-registration)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", action="store_true",
                       help="Count corpora, collapse archetypes, write registration + trial ledger")
    group.add_argument("--run", action="store_true",
                       help="Grade fires, run primary test, BH-FDR, disguise regression")
    group.add_argument("--smoke", type=int, metavar="N",
                       help="Smoke-test pipeline on N tickers (no ledger writes; /tmp output)")
    parser.add_argument("--replay-root", default=None,
                        help="Path to replay corpus (default: SKIP when absent)")
    parser.add_argument("--n-boot", type=int, default=2000,
                        help="Bootstrap resamples for cluster-robust SE (default 2000; "
                             "smoke mode uses 200 internally)")
    parser.add_argument("--force", action="store_true",
                        help="(--register only) overwrite an existing registration file")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)

    t0 = time.time()
    if args.register:
        cmd_register(args)
    elif args.run:
        cmd_run(args, n_boot=args.n_boot)
    elif args.smoke is not None:
        cmd_smoke(args, args.smoke)

    elapsed = time.time() - t0
    log.info("Done in %.1fs", elapsed)


if __name__ == "__main__":
    main()
