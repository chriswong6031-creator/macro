"""Entry-Stack Expansion W0 PR-C — stratum-effects harness with R1 estimator.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §2 (R1/R2),
§5 (full protocol), §6 W0 PR-C, §10 RUL-3/RUL-9/RUL-12.

This is the BASELINE RECOMPUTE mode (RUL-9) only — W0 runs NO candidate study.
Candidate families (esx_ev_blackout, esx_ur_phase0, …) are registered at run
time but no study fires are loaded for them in this PR.

Core function: grade_fires()
  - load a fire parquet
  - for each fire, compute forward_metrics + terminal_state via engine.grading
    (T+1 fill, marker-date ban, BOTH horizon classes: rotational 1.08/21 and
     positional 1.15/126)
  - attach caller-provided stratum label columns
  - estimate stratum effects with the R1 estimator (RUL-12, non-negotiable):
      date-fixed-effects stratified difference, FE granularity fixed once per
      family at W0 sign-off; fallback to era×sector-week FE as per-family
      explicit choice (fe_granularity arg)
  - SEs clustered by episode block = fire-date ±10 bars within sector cohort
  - block-bootstrap 95% CIs
  - BH q≤0.10 panel across p-values of the registered family
  - recall beside precision, survivor stamp on every absolute rate

Sector mapping: US Sectors (EW) baskets from data/baskets/membership.json.
  Coverage: ~99.5% of deep-panel tickers, ~20% of basket tickers.
  Basket panel falls back to date-only blocks; fallback is STAMPED in output.

NC-2 support (RUL-3): optional entry_quality band FE — requires a full
  cycles.py call chain per fire so it is DEFERRED in W0. The hook and loader
  interface are present; the deferral is stamped in W0_BASELINES.md.

Trial registration: every family is registered via @register_trials before
  any run. W0 runs ONLY baseline mode (no esx_* candidate study).

Usage:
    python scripts/research/entry_strata_phase0.py --baselines
    python scripts/research/entry_strata_phase0.py --baselines --out research/entry_stack/W0_BASELINES.md
    python scripts/research/entry_strata_phase0.py --family esx_ts_adx --fires data/research/gate_fires_deep.parquet
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root onto sys.path so `engine.*` imports work when the
# script is executed directly from the repo root or a worktree.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Stdlib logging — never module-level logging.disable
# ---------------------------------------------------------------------------
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = _REPO_ROOT
_DATA = _ROOT / "data"
_RESEARCH_DIR = _ROOT / "research" / "entry_stack"
_BASKETS_MEMBERSHIP = _DATA / "baskets" / "membership.json"
_DEEP_STORE = _DATA / "stocks"
_BASKETS_OHLCV = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Program constants (masterplan §5, RUL-9)
# ---------------------------------------------------------------------------

# The ONE grader (RUL-9): grading.py barrier constants
LIFTOFF_ROT    = 1.08   # rotational liftoff (clean8_21)
HORIZON_ROT    = 21     # rotational window (trading days)
LIFTOFF_POS    = 1.15   # positional liftoff (clean15_126)
HORIZON_POS    = 126    # positional window (trading days)
STOP_MULT      = 0.95   # -5% stop
CUSHION_MULT   = 1.05   # +5% cushion

# Era definitions (masterplan §5)
ERAS = [
    ("pre_2012",   "1900-01-01", "2011-12-31"),
    ("2012-2015",  "2012-01-01", "2015-12-31"),
    ("2016-2019",  "2016-01-01", "2019-12-31"),
    ("2020-2022",  "2020-01-01", "2022-12-31"),
    ("2023-2026",  "2023-01-01", "2026-12-31"),
]
PROGRAM_ERAS = ["2012-2015", "2016-2019", "2020-2022", "2023-2026"]  # primary

# Block-bootstrap parameters (RUL-12)
BLOCK_RADIUS   = 10    # bars: episode block = fire-date ±10 within sector cohort
N_BOOTSTRAP    = 1000  # block-bootstrap resamples for 95% CI
RNG_SEED       = 42

# BH FDR threshold (masterplan §5)
BH_Q_THRESHOLD = 0.10

# Family trial budgets (masterplan §5, pre-registered)
FAMILY_BUDGETS: dict[str, dict[str, Any]] = {
    "esx_null_competitors": {
        "budget": 6,
        "reason": "2 NC x 3 panels",
    },
    "esx_ev_blackout": {
        "budget": 9,
        "reason": "k in {1,2,3} x 3 panels (k=3 primary)",
    },
    "esx_ur_phase0": {
        "budget": 36,
        "reason": "2 lows x 3 reclaim windows x 2 depth-arms x 3 forms; ATR mult frozen 1.0",
    },
    "esx_sq_phase0": {
        "budget": 12,
        "reason": "frozen state grid x 2 panels x 3 forms + 3 named sensitivities",
    },
    "esx_lq_bands": {
        "budget": 12,
        "reason": "2 proxies x 3 fixed-tercile bands x 2 panels",
    },
    "esx_ql_overlay": {
        "budget": 12,
        "reason": "3 quality defs (Piotroski, Altman, Sloan-tercile) x 2 horizons x 2 forms",
    },
    "esx_ts_adx": {
        "budget": 4,
        "reason": "1 def x 2 panels x 2 era-splits",
    },
    "esx_appendix": {
        "budget": 24,
        "reason": "capped; unlocked only after F-tier verdicts filed",
    },
}

# ---------------------------------------------------------------------------
# Trial ledger registration — all families registered at import/run time
# ---------------------------------------------------------------------------

def _register_all_families(ledger_path: Path | None = None) -> None:
    """Register declared trial budgets for all program families. Idempotent."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; skipping budget registration")
        return
    led = TrialLedger(path=ledger_path) if ledger_path else TrialLedger()
    for fam, info in FAMILY_BUDGETS.items():
        led.log_declared_budget(info["budget"], family=fam, reason=info["reason"])
    log.info("Registered %d trial families", len(FAMILY_BUDGETS))


# ---------------------------------------------------------------------------
# Sector mapping
# ---------------------------------------------------------------------------

def _build_sector_map() -> dict[str, str]:
    """ticker -> basket_key for US Sectors (EW) baskets.

    Returns empty dict if membership.json is absent.
    """
    if not _BASKETS_MEMBERSHIP.exists():
        log.warning("baskets/membership.json not found; sector map unavailable")
        return {}
    try:
        bm = json.loads(_BASKETS_MEMBERSHIP.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load baskets/membership.json: %s", exc)
        return {}

    baskets = bm.get("baskets", {})
    sector_map: dict[str, str] = {}
    for key, val in baskets.items():
        if not isinstance(val, dict):
            continue
        if val.get("category", "") != "US Sectors (EW)":
            continue
        for m in val.get("members", []):
            if isinstance(m, dict):
                ticker = m.get("ticker", "")
            else:
                ticker = str(m)
            if ticker:
                sector_map[ticker] = key
    return sector_map


# ---------------------------------------------------------------------------
# Price store loaders
# ---------------------------------------------------------------------------

def _load_deep_closes() -> dict[str, pd.Series]:
    """Load all deep-panel closes into memory (224 names)."""
    closes: dict[str, pd.Series] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load %s: %s", path, exc)
    log.info("Loaded %d deep closes", len(closes))
    return closes


def _load_baskets_closes() -> dict[str, pd.Series]:
    """Load all baskets-panel closes (2519 names). Close column from ohlcv."""
    closes: dict[str, pd.Series] = {}
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load %s: %s", path, exc)
    log.info("Loaded %d basket closes", len(closes))
    return closes


def _get_closes(panel: str) -> dict[str, pd.Series]:
    if panel == "deep":
        return _load_deep_closes()
    if panel == "baskets":
        return _load_baskets_closes()
    raise ValueError(f"Unknown panel: {panel!r}. Use 'deep' or 'baskets'.")


# ---------------------------------------------------------------------------
# Outcome grading (RUL-9: one grader, recomputed baselines)
# ---------------------------------------------------------------------------

def grade_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    extra_columns: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Grade every fire row for all outcome metrics under the program grader.

    Parameters
    ----------
    fires:
        DataFrame with columns: ticker, date, tier, [sub, ticks, ...].
        The 'date' is the SIGNAL date (fire-date); grading uses T+1 fill.
    closes:
        {ticker: close Series} price store.
    extra_columns:
        Optional dict of {col_name: Series indexed by fire index} with
        caller-provided stratum labels to attach to the output.

    Returns
    -------
    DataFrame with all input columns plus:
        fwd_ret_5, fwd_ret_21, fwd_ret_63, fwd_ret_126,
        fwd_mdd_5, fwd_mdd_21, fwd_mdd_63, fwd_mdd_126,
        fwd_mfe_63, fwd_mfe_126,
        fill_date, entry_price,
        state_rot  (clean8_21 terminal state),
        state_pos  (clean15_126 terminal state),
        stop5      (bool: stopped within 5 days — fill+1..fill+5 touched stop),
        mae63, mfe63 (max adverse / favorable excursion at 63d),
        days_to_10 (first bar where fwd_ret ≥ 10%, or NaN),
        cushion_rot, cushion_pos (bool: cushion hit in rotational/positional window),
        gradable   (bool: fill bar exists and matured for both horizons).
    """
    from engine.grading import forward_metrics, terminal_state

    HORIZONS = (5, 21, 63, 126)
    results = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        close = closes.get(ticker)
        rec: dict[str, Any] = dict(row)
        rec["gradable"] = False
        rec.update({
            "fwd_ret_5": None, "fwd_ret_21": None,
            "fwd_ret_63": None, "fwd_ret_126": None,
            "fwd_mdd_5": None, "fwd_mdd_21": None,
            "fwd_mdd_63": None, "fwd_mdd_126": None,
            "fwd_mfe_63": None, "fwd_mfe_126": None,
            "fill_date": None, "entry_price": None,
            "state_rot": None, "state_pos": None,
            "stop5": None, "mae63": None, "mfe63": None,
            "days_to_10": None, "cushion_rot": None, "cushion_pos": None,
        })

        if close is None or close.empty:
            results.append(rec)
            continue

        fm = forward_metrics(close, sig_date, horizons=HORIZONS)
        if fm["fill_date"] is None:
            results.append(rec)
            continue

        rec["fill_date"]   = fm["fill_date"]
        rec["entry_price"] = fm["entry_price"]
        for h in HORIZONS:
            rec[f"fwd_ret_{h}"] = fm[f"fwd_ret_{h}"]
            rec[f"fwd_mdd_{h}"] = fm[f"fwd_mdd_{h}"]
            if h in (63, 126):
                rec[f"fwd_mfe_{h}"] = fm[f"fwd_mfe_{h}"]

        # stop5: did close touch stop barrier within 5 bars of fill?
        fwd_5_ret = fm.get("fwd_mdd_5")
        rec["stop5"] = (fwd_5_ret is not None and fwd_5_ret <= (STOP_MULT - 1.0))

        # mae63 / mfe63
        rec["mae63"] = fm["fwd_mdd_63"]
        rec["mfe63"] = fm["fwd_mfe_63"]

        # days_to_10: first bar where cumulative fwd_ret >= 10%
        entry = fm["entry_price"]
        if entry is not None and entry > 0:
            from engine.grading import fill_index
            fi = fill_index(close, sig_date)
            if fi is not None:
                fwd_arr = close.iloc[fi + 1:fi + 127]
                ratios = fwd_arr.values / entry - 1.0
                crosses = np.where(ratios >= 0.10)[0]
                rec["days_to_10"] = float(crosses[0] + 1) if len(crosses) else None

        # terminal states (both horizon classes)
        ts_rot = terminal_state(
            close, sig_date,
            liftoff_mult=LIFTOFF_ROT, liftoff_horizon=HORIZON_ROT,
            stop_mult=STOP_MULT, cushion_mult=CUSHION_MULT,
        )
        ts_pos = terminal_state(
            close, sig_date,
            liftoff_mult=LIFTOFF_POS, liftoff_horizon=HORIZON_POS,
            stop_mult=STOP_MULT, cushion_mult=CUSHION_MULT,
        )
        rec["state_rot"] = ts_rot["state"]
        rec["state_pos"] = ts_pos["state"]
        rec["cushion_rot"] = ts_rot.get("cushion_at_bar") is not None
        rec["cushion_pos"] = ts_pos.get("cushion_at_bar") is not None

        # gradable iff both horizons matured
        rec["gradable"] = (ts_rot["state"] is not None and ts_pos["state"] is not None)
        results.append(rec)

    out = pd.DataFrame(results)

    # Attach extra stratum columns
    if extra_columns:
        for col, series in extra_columns.items():
            out[col] = series.reindex(out.index).values

    return out


# ---------------------------------------------------------------------------
# R1 estimator — date-fixed-effects stratified difference (RUL-12)
# ---------------------------------------------------------------------------

def _assign_era(date: pd.Timestamp) -> str:
    y = date.year
    if y <= 2011:
        return "pre_2012"
    if y <= 2015:
        return "2012-2015"
    if y <= 2019:
        return "2016-2019"
    if y <= 2022:
        return "2020-2022"
    return "2023-2026"


def _within_date_demean(
    df: pd.DataFrame,
    outcome_col: str,
    stratum_col: str,
    fe_col: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Within-date (or era×sector-week) demeaning for the R1 FE regression.

    For each FE cell (unique value of fe_col), demean both outcome and stratum
    indicator.  Returns (y_demeaned, x_demeaned) as 1-D arrays.
    """
    y_vals = df[outcome_col].to_numpy(dtype=float)
    x_vals = df[stratum_col].to_numpy(dtype=float)
    fe_vals = df[fe_col].to_numpy()

    y_dm = np.empty_like(y_vals)
    x_dm = np.empty_like(x_vals)

    for cell in np.unique(fe_vals):
        mask = fe_vals == cell
        y_dm[mask] = y_vals[mask] - y_vals[mask].mean()
        x_dm[mask] = x_vals[mask] - x_vals[mask].mean()

    return y_dm, x_dm


def _ols_coef(y: np.ndarray, x: np.ndarray) -> float:
    """OLS coefficient of y on x (no intercept after demeaning)."""
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(x, y) / denom)


def _make_blocks(
    df: pd.DataFrame,
    sector_col: str,
    date_col: str,
) -> list[np.ndarray]:
    """Episode blocks for clustered SE: fire-date ±BLOCK_RADIUS bars within sector.

    Groups fires into overlapping blocks: same sector + dates within BLOCK_RADIUS
    business-day radius. Returns list of index arrays (iloc positions).

    This implementation uses a simple approach: sort by (sector, date), then
    group consecutive rows within the same sector whose dates are within
    2*BLOCK_RADIUS calendar days. Each group is one block.

    If sector is all-NaN (date-only fallback), groups by date only within radius.
    """
    df = df.reset_index(drop=True)
    has_sector = sector_col in df.columns and df[sector_col].notna().any()

    if has_sector:
        group_keys = df[sector_col].fillna("__none__")
    else:
        group_keys = pd.Series(["__all__"] * len(df), index=df.index)

    dates = pd.to_datetime(df[date_col])
    order = df.index.to_numpy()

    blocks: list[np.ndarray] = []
    for _, grp_idx in df.groupby(group_keys).groups.items():
        grp_idx = np.asarray(grp_idx)
        grp_dates = dates.iloc[grp_idx].sort_values()
        sorted_idx = grp_dates.index.to_numpy()

        # sliding window: gather consecutive dates within 2*BLOCK_RADIUS calendar days
        used = np.zeros(len(sorted_idx), dtype=bool)
        for i in range(len(sorted_idx)):
            if used[i]:
                continue
            anchor = grp_dates.iloc[i]
            window_mask = np.array([
                abs((grp_dates.iloc[j] - anchor).days) <= 2 * BLOCK_RADIUS * 1.5
                for j in range(len(sorted_idx))
            ])
            block_positions = sorted_idx[window_mask]
            if len(block_positions) > 0:
                blocks.append(block_positions)
            used |= window_mask

    return blocks


def r1_estimate(
    graded: pd.DataFrame,
    outcome_col: str,
    stratum_col: str,
    *,
    fe_granularity: str = "date",
    sector_col: str | None = None,
    era_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
    entry_quality_bands: bool = False,
) -> dict[str, Any]:
    """R1 estimator: date-FE stratified difference with block-bootstrap CIs.

    RUL-12: FE granularity fixed once per family at W0 sign-off.
    Post-hoc switching between FE granularities is banned.

    Parameters
    ----------
    graded:
        Graded fire DataFrame (output of grade_fires or similar).
        Must contain outcome_col, stratum_col, and 'date' column.
    outcome_col:
        Outcome variable name (e.g. 'stop5', 'mae63').
    stratum_col:
        Binary stratum indicator (1 = treatment, 0 = control).
    fe_granularity:
        'date'          — fire-date fixed effects (default; one FE per unique date)
        'era_sector_wk' — era×sector-week fixed effects (fallback for thin cells)
    sector_col:
        Name of sector column in graded (used for block construction and era×sector FE).
        None → date-only blocks (automatically set when sector coverage is low).
    era_col:
        Pre-computed era column (if None, derived from 'date').
    entry_quality_bands:
        If True, add entry_quality-band FE to the model (NC-2 marginality test).
        DEFERRED in W0: column 'eq_band' must be present in graded, else raises.
    n_bootstrap:
        Number of block-bootstrap resamples for 95% CI.
    rng_seed:
        Random seed for reproducibility.

    Returns
    -------
    dict with keys:
        coef         — R1 FE coefficient (stratum effect)
        ci_lo, ci_hi — block-bootstrap 95% CI
        n_total      — total gradable rows in the pool
        n_treatment  — treatment arm count
        n_control    — control arm count
        n_blocks     — number of episode blocks
        fe_granularity — as passed (frozen, for audit)
        sector_fallback — bool: True if date-only blocks used due to low coverage
        naive_diff   — naive (un-matched) stratum difference (for comparison)
        p_value      — bootstrap p-value (fraction of bootstrap coefs ≤ 0, two-sided)
        outcome      — outcome_col
        stratum      — stratum_col
    """
    required = {"date", outcome_col, stratum_col}
    if entry_quality_bands:
        required.add("eq_band")
    missing = required - set(graded.columns)
    if missing:
        raise ValueError(f"r1_estimate: missing columns {missing}")

    if entry_quality_bands and "eq_band" not in graded.columns:
        raise ValueError(
            "entry_quality_bands=True but 'eq_band' column not in graded. "
            "NC-2 marginality is DEFERRED in W0 — see W0_BASELINES.md DEFERRALS."
        )

    # --- subset to gradable rows with valid outcome + stratum -----------------
    df = graded.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df[outcome_col].notna() & df[stratum_col].notna()].copy()
    df[outcome_col] = df[outcome_col].astype(float)
    df[stratum_col] = df[stratum_col].astype(float)
    df = df.reset_index(drop=True)

    if len(df) < 10:
        return _empty_r1_result(outcome_col, stratum_col, fe_granularity,
                                 "insufficient rows after filtering")

    # --- era column -----------------------------------------------------------
    if era_col and era_col in df.columns:
        df["_era"] = df[era_col]
    else:
        df["_era"] = df["date"].apply(_assign_era)

    # --- sector coverage check (sector_fallback) ------------------------------
    sector_fallback = False
    if sector_col and sector_col in df.columns:
        covered = df[sector_col].notna().mean()
        if covered < 0.50:
            sector_fallback = True
            log.warning(
                "r1_estimate: sector column '%s' coverage=%.0f%% < 50%%; "
                "falling back to date-only episode blocks. STAMPED.",
                sector_col, covered * 100,
            )
        _eff_sector = None if sector_fallback else sector_col
    else:
        sector_fallback = (sector_col is not None)
        _eff_sector = None

    # --- build FE column (frozen granularity) ---------------------------------
    if fe_granularity == "date":
        # one FE per unique fire-date
        df["_fe"] = df["date"].astype(str)
    elif fe_granularity == "era_sector_wk":
        # era × sector × ISO-week
        df["_week"] = df["date"].dt.isocalendar().week.astype(str)
        df["_sector_fe"] = df[sector_col].fillna("none") if sector_col and sector_col in df.columns else "none"
        df["_fe"] = df["_era"] + "|" + df["_sector_fe"] + "|" + df["_week"]
    else:
        raise ValueError(f"Unknown fe_granularity: {fe_granularity!r}. Use 'date' or 'era_sector_wk'.")

    # Optional NC-2: add entry_quality band as additional FE dimension
    if entry_quality_bands:
        df["_fe"] = df["_fe"] + "|eq" + df["eq_band"].astype(str)

    # --- drop singleton FE cells (no variation within cell) -------------------
    cell_counts = df["_fe"].value_counts()
    multi_cells = cell_counts[cell_counts > 1].index
    df_fe = df[df["_fe"].isin(multi_cells)].copy()
    if len(df_fe) < 10:
        return _empty_r1_result(outcome_col, stratum_col, fe_granularity,
                                 f"too few rows after dropping singleton FE cells ({len(df_fe)})")

    # --- within-FE demeaning --------------------------------------------------
    y_dm, x_dm = _within_date_demean(df_fe, outcome_col, stratum_col, "_fe")

    # --- OLS coefficient ------------------------------------------------------
    coef = _ols_coef(y_dm, x_dm)

    # --- naive (unmatched) difference -----------------------------------------
    treat = df[df[stratum_col] == 1][outcome_col].dropna()
    ctrl  = df[df[stratum_col] == 0][outcome_col].dropna()
    naive_diff = (float(treat.mean()) - float(ctrl.mean())) if (len(treat) > 0 and len(ctrl) > 0) else np.nan

    # --- episode blocks for bootstrap -----------------------------------------
    blocks = _make_blocks(df_fe, _eff_sector or "__none__", "date")
    if len(blocks) == 0:
        blocks = [df_fe.index.to_numpy()]

    # --- block-bootstrap 95% CI -----------------------------------------------
    rng = np.random.default_rng(rng_seed)
    boot_coefs: list[float] = []
    fe_vals = df_fe["_fe"].to_numpy()
    y_arr = df_fe[outcome_col].to_numpy(dtype=float)
    x_arr = df_fe[stratum_col].to_numpy(dtype=float)

    n_blocks = len(blocks)
    for _ in range(n_bootstrap):
        # resample blocks with replacement to the same block count
        chosen = rng.integers(0, n_blocks, size=n_blocks)
        boot_idx = np.concatenate([blocks[i] for i in chosen])
        # within-FE demean on bootstrap sample
        boot_y = y_arr[boot_idx]
        boot_x = x_arr[boot_idx]
        boot_fe = fe_vals[boot_idx]

        # fast demeaning in bootstrap
        boot_y_dm = np.empty_like(boot_y)
        boot_x_dm = np.empty_like(boot_x)
        for cell in np.unique(boot_fe):
            m = boot_fe == cell
            boot_y_dm[m] = boot_y[m] - boot_y[m].mean()
            boot_x_dm[m] = boot_x[m] - boot_x[m].mean()

        boot_coefs.append(_ols_coef(boot_y_dm, boot_x_dm))

    boot_arr = np.array(boot_coefs)
    ci_lo = float(np.percentile(boot_arr, 2.5))
    ci_hi = float(np.percentile(boot_arr, 97.5))

    # bootstrap p-value (two-sided: fraction as extreme as observed)
    p_value = float(2.0 * min(
        (boot_arr <= 0).mean(),
        (boot_arr >= 0).mean(),
    ))

    n_treatment = int((df[stratum_col] == 1).sum())
    n_control   = int((df[stratum_col] == 0).sum())

    return {
        "coef":             round(coef, 6),
        "ci_lo":            round(ci_lo, 6),
        "ci_hi":            round(ci_hi, 6),
        "n_total":          len(df),
        "n_treatment":      n_treatment,
        "n_control":        n_control,
        "n_blocks":         n_blocks,
        "fe_granularity":   fe_granularity,
        "sector_fallback":  sector_fallback,
        "naive_diff":       round(naive_diff, 6) if np.isfinite(naive_diff) else None,
        "p_value":          round(p_value, 6),
        "outcome":          outcome_col,
        "stratum":          stratum_col,
    }


def _empty_r1_result(outcome: str, stratum: str, fe_gran: str, reason: str) -> dict[str, Any]:
    return {
        "coef": None, "ci_lo": None, "ci_hi": None,
        "n_total": 0, "n_treatment": 0, "n_control": 0,
        "n_blocks": 0, "fe_granularity": fe_gran,
        "sector_fallback": False,
        "naive_diff": None, "p_value": None,
        "outcome": outcome, "stratum": stratum,
        "note": reason,
    }


# ---------------------------------------------------------------------------
# BH FDR correction (masterplan §5)
# ---------------------------------------------------------------------------

def bh_correction(
    p_values: list[float | None],
    labels: list[str],
    q_threshold: float = BH_Q_THRESHOLD,
) -> list[dict[str, Any]]:
    """Benjamini-Hochberg FDR correction over a family of p-values.

    Returns list of dicts with label, p_value, rank, q_value, rejected.
    None p-values are not ranked (not-gradable; excluded from correction).
    """
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None]
    if not valid:
        return [{"label": l, "p_value": None, "rank": None, "q_value": None,
                 "rejected": None} for l in labels]

    m = len(valid)
    sorted_valid = sorted(valid, key=lambda x: x[1])

    q_vals: dict[int, float] = {}
    for rank_1, (orig_i, p) in enumerate(sorted_valid, start=1):
        q_vals[orig_i] = float(p * m / rank_1)

    # enforce monotonicity: q[i] = min(q[i..m])
    running_min = 1.0
    for _, (orig_i, _) in reversed(list(enumerate(sorted_valid))):
        q_vals[orig_i] = min(q_vals[orig_i], running_min)
        running_min = q_vals[orig_i]

    results = []
    for i, label in enumerate(labels):
        p = p_values[i]
        if p is None:
            results.append({
                "label": label, "p_value": None, "rank": None,
                "q_value": None, "rejected": None,
            })
        else:
            rank = next(r for r, (oi, _) in enumerate(sorted_valid, start=1) if oi == i)
            q = q_vals[i]
            results.append({
                "label": label, "p_value": round(p, 6), "rank": rank,
                "q_value": round(q, 6), "rejected": q <= q_threshold,
            })
    return results


# ---------------------------------------------------------------------------
# Effect table builder (masterplan §5)
# ---------------------------------------------------------------------------

EFFECT_OUTCOMES = [
    ("stop5",       "stop5 rate",          "treatment stopped within 5d (bool)"),
    ("state_rot",   "rotational liftoff",  "state_rot == CLEAN_LIFTOFF (clean8_21)"),
    ("state_pos",   "positional liftoff",  "state_pos == CLEAN_LIFTOFF (clean15_126)"),
    ("dead_money",  "dead_money rate",     "state_pos == DEAD_MONEY (positional)"),
    ("cushion_rot", "cushion rate (rot)",  "cushion hit in 21d window"),
    ("mae63",       "MAE 63d",             "max adverse excursion at 63d"),
    ("mfe63",       "MFE 63d",             "max favorable excursion at 63d"),
    ("days_to_10",  "days to 10% gain",    "first bar at ≥10% from entry"),
]


def _prepare_binary_outcomes(graded: pd.DataFrame) -> pd.DataFrame:
    """Convert state columns to binary outcomes for the effect table."""
    df = graded.copy()
    from engine.grading import TerminalState
    df["rotational_liftoff"] = (df["state_rot"] == TerminalState.CLEAN_LIFTOFF).astype(float)
    df["positional_liftoff"] = (df["state_pos"] == TerminalState.CLEAN_LIFTOFF).astype(float)
    df["dead_money"] = (df["state_pos"] == TerminalState.DEAD_MONEY).astype(float)
    df["stop5"] = df["stop5"].astype(float) if "stop5" in df.columns else np.nan
    return df


def effect_table(
    graded: pd.DataFrame,
    stratum_col: str,
    *,
    fe_granularity: str = "date",
    sector_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    family_label: str = "study",
) -> dict[str, Any]:
    """Compute R1-estimated effects for all registered outcomes.

    Returns dict with:
        effects        — list of per-outcome R1 results
        bh_panel       — BH FDR panel over the family
        n_total        — total gradable rows
        n_treatment    — treatment arm
        n_control      — control arm
        fe_granularity — as used
        sector_fallback— bool
        survivor_stamp — disclaimer
        family_label   — as passed
    """
    df = _prepare_binary_outcomes(graded)

    # Only keep gradable rows
    df_gradable = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    outcomes_to_run = [
        ("stop5",             "stop5"),
        ("rotational_liftoff","rotational_liftoff"),
        ("positional_liftoff","positional_liftoff"),
        ("dead_money",        "dead_money"),
        ("cushion_rot",       "cushion_rot"),
        ("mae63",             "mae63"),
        ("mfe63",             "mfe63"),
        ("days_to_10",        "days_to_10"),
    ]

    effects = []
    p_values: list[float | None] = []
    labels: list[str] = []

    for label, col in outcomes_to_run:
        if col not in df_gradable.columns:
            continue
        result = r1_estimate(
            df_gradable, col, stratum_col,
            fe_granularity=fe_granularity,
            sector_col=sector_col,
            n_bootstrap=n_bootstrap,
        )
        result["label"] = label
        effects.append(result)
        p_values.append(result.get("p_value"))
        labels.append(label)

    bh = bh_correction(p_values, labels)

    # Precision and recall for each arm (masterplan §5: recall beside precision)
    if stratum_col in df_gradable.columns:
        n_total_gradable = len(df_gradable)
        n_treatment = int((df_gradable[stratum_col].fillna(0) == 1).sum())
        n_control   = int((df_gradable[stratum_col].fillna(0) == 0).sum())
    else:
        n_total_gradable = n_treatment = n_control = 0

    return {
        "effects":         effects,
        "bh_panel":        bh,
        "n_total":         n_total_gradable,
        "n_treatment":     n_treatment,
        "n_control":       n_control,
        "fe_granularity":  fe_granularity,
        "sector_fallback": effects[0].get("sector_fallback", False) if effects else False,
        "survivor_stamp":  (
            "SURVIVOR BIAS WARNING: absolute rates computed on surviving names only. "
            "Dead-name delisted panel not included in this run. "
            "Comparisons between strata are survivor-bias-neutral iff both arms have "
            "similar listing-survival distributions."
        ),
        "family_label": family_label,
    }


# ---------------------------------------------------------------------------
# Era table (masterplan §5)
# ---------------------------------------------------------------------------

def era_table(
    graded: pd.DataFrame,
    stratum_col: str | None = None,
    *,
    panel_label: str = "panel",
) -> pd.DataFrame:
    """Per-era × tier base-rate table.

    Returns DataFrame indexed by (era, tier) with columns:
        n_fires, stop5_rate, rot_liftoff_rate, pos_liftoff_rate,
        dead_money_rate, mae63_mean, days_to_10_median.

    stratum_col: if provided, adds stratum breakdown.
    """
    df = _prepare_binary_outcomes(graded)
    df["date"] = pd.to_datetime(df["date"])
    df["era"] = df["date"].apply(_assign_era)
    df_gradable = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    group_keys = ["era"]
    if "tier" in df_gradable.columns:
        group_keys.append("tier")

    rows = []
    for keys, g in df_gradable.groupby(group_keys):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec: dict[str, Any] = {}
        for k, v in zip(group_keys, keys):
            rec[k] = v
        rec["panel"] = panel_label
        rec["n_fires"] = len(g)
        rec["stop5_rate"]       = round(g["stop5"].mean(), 4) if "stop5" in g else None
        rec["rot_liftoff_rate"] = round(g["rotational_liftoff"].mean(), 4) if "rotational_liftoff" in g else None
        rec["pos_liftoff_rate"] = round(g["positional_liftoff"].mean(), 4) if "positional_liftoff" in g else None
        rec["dead_money_rate"]  = round(g["dead_money"].mean(), 4) if "dead_money" in g else None
        rec["mae63_mean"]       = round(g["mae63"].mean(), 4) if "mae63" in g and g["mae63"].notna().any() else None
        rec["mfe63_mean"]       = round(g["mfe63"].mean(), 4) if "mfe63" in g and g["mfe63"].notna().any() else None
        days = g["days_to_10"].dropna()
        rec["days_to_10_median"] = round(float(days.median()), 1) if len(days) > 0 else None
        rows.append(rec)

    result = pd.DataFrame(rows)
    if not result.empty and "era" in result.columns:
        era_order = ["pre_2012", "2012-2015", "2016-2019", "2020-2022", "2023-2026"]
        result["era"] = pd.Categorical(result["era"], categories=era_order, ordered=True)
        result = result.sort_values(group_keys).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# Recall computation (masterplan §5)
# ---------------------------------------------------------------------------

def compute_recall(
    graded: pd.DataFrame,
    stratum_col: str,
    reference_col: str = "gradable",
) -> dict[str, float | None]:
    """Recall of treatment arm relative to all gradable fires.

    recall = n_treatment_gradable / n_all_gradable
    Printed beside precision (hit rate) per masterplan §5.
    """
    df = graded[graded[reference_col].fillna(False)].copy() if reference_col in graded.columns else graded.copy()
    n_all = len(df)
    if n_all == 0:
        return {"recall": None, "n_treatment": 0, "n_all": 0}
    n_treatment = int((df[stratum_col].fillna(0) == 1).sum())
    return {
        "recall":      round(n_treatment / n_all, 4),
        "n_treatment": n_treatment,
        "n_all":       n_all,
    }


# ---------------------------------------------------------------------------
# Baseline recompute (RUL-9) — --baselines mode
# ---------------------------------------------------------------------------

def run_baselines(
    out_path: Path | None = None,
    n_bootstrap: int = 500,  # reduced for baseline-only mode (faster)
) -> dict[str, Any]:
    """Recompute incumbent gate-fire baselines under the program grader (RUL-9).

    Baselines: gate-fire base rates by tier (T1/T2/T3) x panel (deep, baskets) x era
    for stop5, rotational liftoff, positional liftoff, dead_money, mae63, days_to_10.

    Returns a results dict. Also writes W0_BASELINES.md if out_path is provided.
    """
    log.info("Starting baseline recompute (RUL-9)...")
    _register_all_families()

    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers covered", len(sector_map))

    results: dict[str, Any] = {
        "grader": {
            "rotational": {"liftoff_mult": LIFTOFF_ROT, "horizon": HORIZON_ROT,
                           "stop_mult": STOP_MULT, "cushion_mult": CUSHION_MULT},
            "positional":  {"liftoff_mult": LIFTOFF_POS, "horizon": HORIZON_POS,
                            "stop_mult": STOP_MULT, "cushion_mult": CUSHION_MULT},
        },
        "panels": {},
    }

    panels = [
        ("deep",    _DATA / "research" / "gate_fires_deep.parquet"),
        ("baskets", _DATA / "research" / "gate_fires_baskets.parquet"),
    ]

    for panel_name, fires_path in panels:
        if not fires_path.exists():
            log.warning("Fire dump not found: %s — skipping panel %s", fires_path, panel_name)
            results["panels"][panel_name] = {"error": f"fires not found: {fires_path}"}
            continue

        log.info("Loading fires for panel=%s from %s", panel_name, fires_path)
        fires = pd.read_parquet(fires_path)
        log.info("  %d fire rows loaded", len(fires))

        log.info("Loading closes for panel=%s ...", panel_name)
        closes = _get_closes(panel_name)

        # Sector coverage
        tickers_in_fires = fires["ticker"].unique()
        covered = sum(1 for t in tickers_in_fires if t in sector_map)
        sector_coverage = covered / max(len(tickers_in_fires), 1)
        sector_fallback_flag = sector_coverage < 0.50

        log.info(
            "  Sector coverage: %d/%d = %.0f%% (fallback=%s)",
            covered, len(tickers_in_fires), sector_coverage * 100, sector_fallback_flag,
        )

        # Attach sector column
        fires = fires.copy()
        fires["sector"] = fires["ticker"].map(sector_map)

        # FE granularity: date for deep (high coverage), era_sector_wk for baskets (low)
        fe_granularity = "date" if not sector_fallback_flag else "date"
        # (for baskets, we still use date-FE but with date-only blocks since sector coverage is low)

        log.info("Grading %d fires...", len(fires))
        graded = grade_fires(fires, closes)
        n_gradable = int(graded["gradable"].fillna(False).sum())
        log.info(
            "  Graded: %d total, %d gradable (%.0f%%)",
            len(graded), n_gradable, n_gradable / max(len(graded), 1) * 100,
        )

        # Era table (main baseline output)
        era_tbl = era_table(graded, panel_label=panel_name)

        # Tier × panel × era summary (masterplan §5)
        graded_df = _prepare_binary_outcomes(graded)
        graded_df["date"] = pd.to_datetime(graded_df["date"])
        graded_df["era"] = graded_df["date"].apply(_assign_era)
        graded_df_ok = graded_df[graded_df["gradable"].fillna(False)].copy()

        # Overall stats per tier
        tier_stats: dict[str, Any] = {}
        for tier, g in graded_df_ok.groupby("tier"):
            tier_stats[str(tier)] = {
                "n_fires":          len(g),
                "stop5_rate":       round(float(g["stop5"].mean()), 4) if "stop5" in g.columns else None,
                "rot_liftoff_rate": round(float(g["rotational_liftoff"].mean()), 4),
                "pos_liftoff_rate": round(float(g["positional_liftoff"].mean()), 4),
                "dead_money_rate":  round(float(g["dead_money"].mean()), 4),
                "mae63_mean":       round(float(g["mae63"].mean()), 4) if g["mae63"].notna().any() else None,
                "mfe63_mean":       round(float(g["mfe63"].mean()), 4) if g["mfe63"].notna().any() else None,
            }

        results["panels"][panel_name] = {
            "n_fires_total":    len(fires),
            "n_gradable":       n_gradable,
            "sector_coverage":  round(sector_coverage, 4),
            "sector_fallback":  sector_fallback_flag,
            "fe_granularity":   fe_granularity,
            "survivor_stamp":   (
                "SURVIVOR BIAS: absolute rates on surviving names only. "
                "Comparisons within-era are directionally valid."
            ),
            "tier_stats":       tier_stats,
            "era_table":        era_tbl.to_dict(orient="records"),
        }
        log.info("  Panel %s done.", panel_name)

    if out_path:
        _write_baselines_md(results, out_path)
        log.info("Wrote %s", out_path)

    return results


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _write_baselines_md(results: dict[str, Any], out_path: Path) -> None:
    """Write research/entry_stack/W0_BASELINES.md."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# W0 Incumbent Baselines — Entry-Stack Expansion")
    a("")
    a("**Status:** W0 recompute under the program grader (RUL-9).")
    a("All numbers here use `engine.grading` barrier definitions:")
    a("- Rotational: liftoff 1.08×, horizon 21d, stop 0.95×, cushion 1.05×")
    a("- Positional:  liftoff 1.15×, horizon 126d, stop 0.95×, cushion 1.05×")
    a("")
    a("Wave1-era numbers (clean15=1.20+durable-hold) are historical context only")
    a("and may NOT satisfy any promotion bar (RUL-9).")
    a("")
    a("---")
    a("")
    a("## Trial Registration")
    a("")
    a("All program families registered at W0 run time (idempotent, appended to")
    a("`data/trial_ledger.jsonl`):")
    a("")
    a("| Family | Budget | Basis |")
    a("|---|---|---|")
    for fam, info in FAMILY_BUDGETS.items():
        a(f"| `{fam}` | {info['budget']} | {info['reason']} |")
    a("")
    a("---")
    a("")
    a("## FE Granularity Choices (Frozen per RUL-12)")
    a("")
    a("| Panel | fe_granularity | Sector coverage | Sector fallback? |")
    a("|---|---|---|---|")
    for panel_name, pd_info in results.get("panels", {}).items():
        if "error" in pd_info:
            a(f"| {panel_name} | N/A (panel missing) | N/A | N/A |")
            continue
        cov = pd_info.get("sector_coverage", 0)
        fe = pd_info.get("fe_granularity", "date")
        fb = "YES — date-only episode blocks" if pd_info.get("sector_fallback") else "No"
        a(f"| {panel_name} | `{fe}` | {cov:.0%} | {fb} |")
    a("")
    a("Post-hoc switching between FE granularities is banned (RUL-12).")
    a("")
    a("---")
    a("")

    for panel_name, pd_info in results.get("panels", {}).items():
        a(f"## Panel: {panel_name}")
        a("")
        if "error" in pd_info:
            a(f"**ERROR:** {pd_info['error']}")
            a("")
            continue

        a(f"**SURVIVOR BIAS STAMP:** {pd_info.get('survivor_stamp', '')}")
        a("")
        a(f"- Total fires loaded: {pd_info['n_fires_total']:,}")
        a(f"- Gradable (both horizons matured): {pd_info['n_gradable']:,}")
        a(f"- Sector coverage: {pd_info['sector_coverage']:.0%}")
        a(f"- FE granularity: `{pd_info['fe_granularity']}`")
        a("")

        # Tier stats
        tier_stats = pd_info.get("tier_stats", {})
        if tier_stats:
            a("### Tier Summary (all eras, gradable fires)")
            a("")
            a("| Tier | N fires | Stop5 rate | Rot liftoff | Pos liftoff | Dead money | MAE63 mean | MFE63 mean |")
            a("|---|---|---|---|---|---|---|---|")
            for tier in ("T1", "T2", "T3"):
                t = tier_stats.get(tier, {})
                if not t:
                    continue
                def _fmt(v):
                    return f"{v:.1%}" if v is not None else "—"
                def _fmt4(v):
                    return f"{v:.4f}" if v is not None else "—"
                a(f"| {tier} | {t.get('n_fires', 0):,} | {_fmt(t.get('stop5_rate'))} | "
                  f"{_fmt(t.get('rot_liftoff_rate'))} | {_fmt(t.get('pos_liftoff_rate'))} | "
                  f"{_fmt(t.get('dead_money_rate'))} | {_fmt4(t.get('mae63_mean'))} | "
                  f"{_fmt4(t.get('mfe63_mean'))} |")
            a("")

        # Era table
        era_records = pd_info.get("era_table", [])
        if era_records:
            era_df = pd.DataFrame(era_records)
            # Program eras only
            prog_eras = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df

            a("### Era × Tier Table (program eras: 2012-2026)")
            a("")
            cols_show = ["era", "tier", "n_fires", "stop5_rate",
                         "rot_liftoff_rate", "pos_liftoff_rate",
                         "dead_money_rate", "mae63_mean", "days_to_10_median"]
            cols_present = [c for c in cols_show if c in prog_eras.columns]
            if not prog_eras.empty:
                header = "| " + " | ".join(cols_present) + " |"
                a(header)
                a("|" + "---|" * len(cols_present))
                for _, row in prog_eras.iterrows():
                    def _fmtval(v, col):
                        if v is None or (isinstance(v, float) and np.isnan(v)):
                            return "—"
                        if col in ("stop5_rate", "rot_liftoff_rate", "pos_liftoff_rate", "dead_money_rate"):
                            return f"{v:.1%}"
                        if col in ("mae63_mean",):
                            return f"{v:.4f}"
                        if col == "days_to_10_median":
                            return f"{v:.0f}d"
                        return str(v)
                    cells = [_fmtval(row.get(c), c) for c in cols_present]
                    a("| " + " | ".join(cells) + " |")
                a("")

        a("")

    a("---")
    a("")
    a("## Deferrals")
    a("")
    a("### NC-2 Entry Quality Bands (RUL-3)")
    a("")
    a("**DEFERRED to W1/S-UR study PR.**")
    a("")
    a("`engine.cycles.entry_quality()` requires per-fire computation of cyc/mtf/early/regime")
    a("dicts — each a full cycles.py call chain — making per-fire band assignment too heavy")
    a("for W0 baseline computation (~224 tickers × ~38k fires on deep panel).")
    a("")
    a("The hook is present in `r1_estimate(entry_quality_bands=True)` and the loader")
    a("interface is defined (pass `eq_band` column in graded DataFrame). The NC-2")
    a("marginality test (coefficient survives eq-band FE) runs in W1 when the first")
    a("candidate study generates per-fire eq-band labels efficiently (e.g., as a")
    a("batch-computed lookup table per ticker×year-quarter).")
    a("")
    a("### COILED/COILED-FIRE Recall Recompute")
    a("")
    a("**DEFERRED to S-UR study PR.**")
    a("")
    a("The COILED state is computed via engine/cycles.py which requires the full")
    a("per-ticker cycle state stack. Recomputing recall under the program grader")
    a("requires running the full cycle pipeline over all fire dates — scoped to")
    a("the S-UR phase0 PR where the COILED∩S-UR intersection is the primary subject.")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/entry_strata_phase0.py --baselines`*")
    a("*Grader: engine/grading.py (barriers above). Wave1 numbers = historical context only.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API for study runners (W1+ lanes)
# ---------------------------------------------------------------------------

def load_fires(path: str | Path) -> pd.DataFrame:
    """Load a fire parquet and validate schema."""
    df = pd.read_parquet(path)
    required = {"ticker", "date", "tier"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Fire parquet missing columns: {missing}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def run_study(
    family: str,
    fires: pd.DataFrame,
    stratum_col: str,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
    *,
    fe_granularity: str = "date",
    n_bootstrap: int = N_BOOTSTRAP,
    extra_columns: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    """Run a full stratum study for a registered family.

    This is the main entry point for W1+ study PRs. It:
      1. Grades the fires under the program grader
      2. Computes effect table with R1 estimator
      3. Computes era table
      4. Computes recall

    Parameters
    ----------
    family:
        The registered trial family name (e.g. 'esx_ts_adx').
    fires:
        Fire DataFrame (from load_fires()).
    stratum_col:
        Binary stratum indicator column name in fires/extra_columns.
    closes:
        Price store dict (from _get_closes()).
    sector_map:
        Ticker→sector mapping (from _build_sector_map()).
    fe_granularity:
        Fixed per family at W0 sign-off (RUL-12).
    n_bootstrap:
        Block-bootstrap resamples.
    extra_columns:
        Additional columns to attach (stratum labels, etc.).

    Returns
    -------
    Full study results dict.
    """
    if family not in FAMILY_BUDGETS:
        raise ValueError(
            f"Family '{family}' not in FAMILY_BUDGETS. "
            f"Valid families: {list(FAMILY_BUDGETS.keys())}"
        )
    _register_all_families()

    fires = fires.copy()
    fires["sector"] = fires["ticker"].map(sector_map)

    graded = grade_fires(fires, closes, extra_columns=extra_columns)

    recall_info = compute_recall(graded, stratum_col)

    eff_table = effect_table(
        graded, stratum_col,
        fe_granularity=fe_granularity,
        sector_col="sector",
        n_bootstrap=n_bootstrap,
        family_label=family,
    )

    era_tbl = era_table(graded, stratum_col, panel_label=fires.get("panel", pd.Series("unknown")).iloc[0] if len(fires) else "unknown")

    return {
        "family":         family,
        "fe_granularity": fe_granularity,
        "n_fires":        len(fires),
        "n_gradable":     int(graded["gradable"].fillna(False).sum()),
        "recall":         recall_info,
        "effect_table":   eff_table,
        "era_table":      era_tbl.to_dict(orient="records"),
        "survivor_stamp": eff_table.get("survivor_stamp", ""),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion W0 — stratum harness + incumbent baselines.",
    )
    parser.add_argument(
        "--baselines", action="store_true",
        help="Recompute incumbent baselines under the program grader (RUL-9).",
    )
    parser.add_argument(
        "--out",
        default=str(_RESEARCH_DIR / "W0_BASELINES.md"),
        help="Output path for W0_BASELINES.md (used with --baselines).",
    )
    parser.add_argument(
        "--family", default=None,
        help="Study family name (for non-baseline study runs in W1+).",
    )
    parser.add_argument(
        "--fires", default=None,
        help="Path to fire parquet for study runs.",
    )
    parser.add_argument(
        "--fe-granularity", default="date",
        choices=["date", "era_sector_wk"],
        help="FE granularity (frozen per RUL-12 at W0 sign-off).",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=500,
        help="Bootstrap resamples (default 500 for baseline mode; use 1000 for final runs).",
    )
    parser.add_argument(
        "--register-only", action="store_true",
        help="Only register trial families and exit.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.register_only:
        _register_all_families()
        print("Registered all program trial families.")
        return 0

    if args.baselines:
        results = run_baselines(
            out_path=Path(args.out),
            n_bootstrap=args.n_bootstrap,
        )
        # Print headline numbers
        print("\n=== W0 INCUMBENT BASELINES (program grader, RUL-9) ===\n")
        for panel_name, pd_info in results.get("panels", {}).items():
            if "error" in pd_info:
                print(f"Panel {panel_name}: ERROR — {pd_info['error']}")
                continue
            print(f"Panel: {panel_name}")
            print(f"  Fires: {pd_info['n_fires_total']:,} total, "
                  f"{pd_info['n_gradable']:,} gradable")
            print(f"  Sector coverage: {pd_info['sector_coverage']:.0%} "
                  f"(fallback={pd_info['sector_fallback']})")
            ts = pd_info.get("tier_stats", {})
            for tier in ("T1", "T2", "T3"):
                t = ts.get(tier)
                if not t:
                    continue
                print(f"  {tier}: n={t['n_fires']:,} | "
                      f"stop5={t.get('stop5_rate', 0) or 0:.1%} | "
                      f"rot_liftoff={t.get('rot_liftoff_rate', 0) or 0:.1%} | "
                      f"pos_liftoff={t.get('pos_liftoff_rate', 0) or 0:.1%} | "
                      f"dead_money={t.get('dead_money_rate', 0) or 0:.1%}")
            print()
        print(f"Wrote {args.out}")
        return 0

    # Non-baseline study mode (W1+)
    if not args.family:
        parser.error("--family is required for study runs (or use --baselines)")
    if not args.fires:
        parser.error("--fires is required for study runs")

    fires = load_fires(args.fires)
    panel = fires["panel"].iloc[0] if "panel" in fires.columns else "unknown"
    closes = _get_closes(panel)
    sector_map = _build_sector_map()

    # Note: stratum_col must be injected by the caller for W1+ runs
    print(f"Study mode for family '{args.family}' — stratum column must be injected.")
    print("Use run_study() programmatically from W1+ scripts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
