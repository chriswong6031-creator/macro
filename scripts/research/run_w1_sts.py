"""Entry-Stack Expansion W1 — S-TS ADX Residual Study (F6).

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md
  §3 F6 (S-TS candidate), §2 R1/R2 laws, §5 trial protocol, §10 RUL-2/5.
W0 baselines frozen in: research/entry_stack/W0_BASELINES.md (RUL-7 gate).

ADJACENT PRIORS (R2 — RUL-2):
  - Trend/location guards (rising MAs, ATR-contraction, higher-low) FALSIFIED as
    exposure artifacts (DURABLE_BOTTOM_FRAMEWORK.md:606, §2 §3).
  - CT-LANE not-worse: counter-trend buyable fires showed no degradation vs aligned
    fires (n=7,392, −0.16/−0.6pp; §2 §3 masterplan).
  - ADX measures trend *strength* directionlessly — mechanically distinct from the
    falsified direction/location guards, which required directional alignment.
    Never studied in this repo (census 3A). We run ONE date-matched stratification
    to close the question the external doc keeps reopening.

PRE-REGISTERED EXPECT-NULL PROTOCOL (RUL-5):
  The registered expectation IS a null. Non-null means ONLY the pooled R1
  FE coefficient with BH-adjusted CI excluding 0. Single-era excursions are
  noise by pre-registration. Any non-null additionally requires baskets OOS
  replication before a chip is even discussed (not this script's call).

STRATUM DEFINITION (frozen at W1 build — §3 F6 + RUL-F6-OPDEF):
  The masterplan §3 F6 pre-registered "ADX14 rising-vs-low at fire." The full
  operationalization was chosen by the W1 builder and frozen in masterplan
  RUL-F6-OPDEF (ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md, appended to §3 F6):
  Stratum A (ADX-rising): adx14 > 20 AND adx14 > adx14.shift(5) at the fire bar.
    level_threshold=20.0 (conventional trending floor; no alternative tested pre-read)
    lookback=5 bars (one trading week; no alternative tested pre-read)
  Stratum B: complement (ADX low, or ADX not-rising, or close-only fires excluded).
  ADX14 via engine.stock_technicals.adx_dmi(high, low, close, n=14).
  Close-only fires (no H/L): EXCLUDED with counts printed (not silently zero-filled).

FREE CONTEXT COLUMNS (no-inference banner — no family, no promotion path):
  - dist_52w_high terciles: distance from 52-week high in tercile bands (0/1/2).
    Proxy for overhead supply context (S-OH, §3 D3). Cross-sectional terciles from
    full panel.
  - VIX regime: trailing-10-year-percentile bands (below-33 / 33-67 / above-67).
    Data: data/fred/VIXCLS.parquet (37y depth per census §1). Index-level vol-state,
    not per-name. Context only; NO inference, NO CI, NO promotion path.
    (RUL note: vol_regime overlay already failed additive-value vs vol-target per §3.)

TRIAL REGISTRATION:
  Family: esx_ts_adx (budget=4, pre-registered at W0).
  4 trials: 1 def × 2 panels × 2 era-splits.
  Registration is idempotent (appended to data/trial_ledger.jsonl).

Usage:
    cd /path/to/repo
    python scripts/research/run_w1_sts.py
    python scripts/research/run_w1_sts.py --smoke   # 50 boot, deep only
    python scripts/research/run_w1_sts.py --n-bootstrap 500
    python scripts/research/run_w1_sts.py --panel deep
    python scripts/research/run_w1_sts.py --out research/entry_stack/W1_STS_REPORT.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Imports from W0/W1 harness (entry_strata_phase0 + run_w1_nc)
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    PROGRAM_ERAS,
    N_BOOTSTRAP,
)

from scripts.research.run_w1_nc import (  # noqa: E402
    fast_effect_table,
    fast_era_table,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _write_effect_md,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA           = _REPO_ROOT / "data"
_RESEARCH_DIR   = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP     = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS  = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH    = _DATA / "trial_ledger.jsonl"
_DEEP_STORE     = _DATA / "stocks"
_BASKETS_OHLCV  = _DATA / "baskets" / "ohlcv"
_VIXCLS_PATH    = _DATA / "fred" / "VIXCLS.parquet"

# VIX percentile band thresholds (trailing-10-year)
VIX_BAND_LO = 33   # below-33pctile = low-vol
VIX_BAND_HI = 67   # above-67pctile = high-vol

# ADX stratum operationalization — frozen at W1 build via RUL-F6-OPDEF
# (masterplan §3 F6 pre-registered "rising-vs-low"; the specific numbers below
# were chosen by the W1 builder and frozen in the masterplan RUL-F6-OPDEF block.
# No alternative was tested before reading results.)
ADX_LEVEL_THRESHOLD = 20.0   # adx14 > 20 (conventional "trending" floor)
ADX_LOOKBACK        = 5      # adx14 > adx14.shift(5) (1-week lookback)

# 52-week high window
DIST_52W_WINDOW = 252  # bars


# ---------------------------------------------------------------------------
# Trial-ledger registration for this study
# ---------------------------------------------------------------------------

def _register_sts_trials(ledger_path: Path | None = None) -> None:
    """Log each S-TS test as a trial in the esx_ts_adx family."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; S-TS trial rows skipped")
        return
    led = TrialLedger(path=ledger_path or _LEDGER_PATH)
    configs = [
        {"study": "S-TS-ADX", "panel": "deep",    "era": "all"},
        {"study": "S-TS-ADX", "panel": "deep",    "era": "era-split"},
        {"study": "S-TS-ADX", "panel": "baskets", "era": "all"},
        {"study": "S-TS-ADX", "panel": "baskets", "era": "era-split"},
    ]
    for cfg in configs:
        led.log_trial(cfg, family="esx_ts_adx", note="W1 S-TS ADX residual study")
    log.info("Logged %d S-TS trial configs in esx_ts_adx", len(configs))


# ---------------------------------------------------------------------------
# H/L panel loaders (returns dict: ticker -> DataFrame with high, low, close)
# ---------------------------------------------------------------------------

def _load_deep_hl() -> dict[str, pd.DataFrame]:
    """Load high/low/close from deep panel (data/stocks/*.parquet)."""
    panels: dict[str, pd.DataFrame] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            required = {"high", "low", "close"}
            if not required.issubset(df.columns):
                log.debug("%s: missing H/L — close-only, excluded from ADX", ticker)
                continue
            df = df[["high", "low", "close"]].dropna(how="all").sort_index()
            if len(df) >= 50:
                panels[ticker] = df
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load %s: %s", path, exc)
    log.info("Loaded %d deep H/L panels", len(panels))
    return panels


def _load_baskets_hl() -> dict[str, pd.DataFrame]:
    """Load high/low/close from baskets panel (data/baskets/ohlcv/*.parquet)."""
    panels: dict[str, pd.DataFrame] = {}
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            required = {"high", "low", "close"}
            if not required.issubset(df.columns):
                log.debug("%s: missing H/L — close-only, excluded from ADX", ticker)
                continue
            df = df[["high", "low", "close"]].dropna(how="all").sort_index()
            if len(df) >= 50:
                panels[ticker] = df
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load %s: %s", path, exc)
    log.info("Loaded %d basket H/L panels", len(panels))
    return panels


def _get_hl_panels(panel: str) -> dict[str, pd.DataFrame]:
    if panel == "deep":
        return _load_deep_hl()
    if panel == "baskets":
        return _load_baskets_hl()
    raise ValueError(f"Unknown panel: {panel!r}")


# ---------------------------------------------------------------------------
# ADX14 at fire bar — vectorized per-ticker computation
# ---------------------------------------------------------------------------

def compute_adx_at_fires(
    fires: pd.DataFrame,
    hl_panels: dict[str, pd.DataFrame],
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """Compute adx14 at each fire date from H/L panel.

    Vectorized per-ticker: compute the full ADX14 series once per ticker (on the
    full panel, no per-fire slicing), then join fire dates via searchsorted.
    This is ~50-100x faster than the naive per-fire loop.

    Returns
    -------
    adx14_series : pd.Series indexed by fires.index
        ADX14 value at the fire bar (NaN if H/L unavailable or insufficient history).
    adx14_lag5_series : pd.Series indexed by fires.index
        ADX14 value 5 bars prior (NaN if not enough history).
    exclusion_counts : dict
        {reason: count} of fires that could not be graded for ADX.
        Printed in the report (not silently zeroed).
    """
    from engine.stock_technicals import adx_dmi

    exclusion_counts: dict[str, int] = {
        "no_hl_panel": 0,
        "insufficient_history": 0,
        "date_not_in_panel": 0,
        "adx_nan": 0,
        "insufficient_lag5_history": 0,
    }

    # Precompute full ADX14 series per ticker (vectorized — one pass per ticker).
    # Track tickers skipped for <28 bars so fires from those tickers are correctly
    # attributed to "insufficient_history" (not "adx_nan") in the fire loop below.
    adx_cache: dict[str, pd.Series] = {}
    short_history_tickers: set[str] = set()
    for ticker, df in hl_panels.items():
        if len(df) < 28:
            short_history_tickers.add(ticker)
            continue
        try:
            adx_full, _, _ = adx_dmi(df["high"], df["low"], df["close"], 14)
            adx_cache[ticker] = adx_full
        except Exception:  # noqa: BLE001
            pass

    log.info("  ADX14 series precomputed for %d tickers", len(adx_cache))

    # Now look up per fire date using searchsorted (fast)
    adx_vals: list[float | None] = []
    adx_lag5_vals: list[float | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])

        if ticker not in hl_panels:
            exclusion_counts["no_hl_panel"] += 1
            adx_vals.append(None)
            adx_lag5_vals.append(None)
            continue

        adx_series = adx_cache.get(ticker)
        if adx_series is None:
            # Ticker in hl_panels but not in adx_cache: either <28 bars or compute error.
            if ticker in short_history_tickers:
                exclusion_counts["insufficient_history"] += 1
            else:
                exclusion_counts["adx_nan"] += 1
            adx_vals.append(None)
            adx_lag5_vals.append(None)
            continue

        # Find the position of the fire date in the panel index
        # Use side="right" - 1 to get the last bar on or before sig_date
        loc = adx_series.index.searchsorted(sig_date, side="right") - 1
        if loc < 0:
            exclusion_counts["date_not_in_panel"] += 1
            adx_vals.append(None)
            adx_lag5_vals.append(None)
            continue

        adx_at_bar = float(adx_series.iloc[loc])
        if np.isnan(adx_at_bar):
            exclusion_counts["adx_nan"] += 1
            adx_vals.append(None)
            adx_lag5_vals.append(None)
            continue

        # ADX 5 bars ago (strictly prior to fire bar)
        lag5_loc = loc - ADX_LOOKBACK
        if lag5_loc < 0:
            # Fire has valid ADX at bar but <5 bars of prior ADX history.
            # No rising condition possible; fire will be NaN in stratum → excluded.
            exclusion_counts["insufficient_lag5_history"] += 1
            adx_vals.append(adx_at_bar)
            adx_lag5_vals.append(None)
        else:
            adx_lag5 = float(adx_series.iloc[lag5_loc])
            adx_vals.append(adx_at_bar)
            if np.isnan(adx_lag5):
                adx_lag5_vals.append(None)
            else:
                adx_lag5_vals.append(adx_lag5)

    adx14_series = pd.Series(adx_vals, index=fires.index, name="adx14")
    adx14_lag5_series = pd.Series(adx_lag5_vals, index=fires.index, name="adx14_lag5")

    return adx14_series, adx14_lag5_series, exclusion_counts


def build_adx_stratum(
    adx14: pd.Series,
    adx14_lag5: pd.Series,
) -> pd.Series:
    """Build frozen stratum A indicator from ADX14 series.

    Stratum A (adx_rising=1): adx14 > 20 AND adx14 > adx14_lag5
    Stratum B (adx_rising=0): complement (including NaN → excluded from model)

    Returns pd.Series of {0.0, 1.0, NaN}.
      NaN = fire excluded (no H/L panel, insufficient history, or no lag5 value).
    """
    level_ok = adx14 > ADX_LEVEL_THRESHOLD          # > 20
    rising_ok = adx14 > adx14_lag5                  # rising vs 5 bars ago
    both_ok = level_ok & rising_ok

    # If adx14 is NaN or lag5 is NaN, the result is NaN (excluded)
    stratum = pd.Series(np.where(
        adx14.isna() | adx14_lag5.isna(),
        np.nan,
        np.where(both_ok, 1.0, 0.0),
    ), index=adx14.index, name="adx_rising")

    return stratum


# ---------------------------------------------------------------------------
# Free context columns: dist_52w_high terciles + VIX regime bands
# ---------------------------------------------------------------------------

def compute_dist_52w_high_tercile(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
) -> pd.Series:
    """Distance from 52-week high at fire date, assigned to tercile band.

    dist_52w_high = close / rolling_252d_high - 1 (strictly prior bars).
    Negative = below the 52w high; 0.0 = AT the 52w high (new high).
    Tercile bands: 0 = most beaten-down (furthest below 52w high),
                   1 = mid, 2 = closest to or at 52w high.
    Cross-sectional terciles computed on the full (pooled) distribution.

    NO-INFERENCE BANNER: context column only; no family; no promotion path.
    52w-high BREAKOUT ALPHA is falsified (§2/§3 masterplan). This is
    overhead-supply CONTEXT (S-OH, D3), display-only in this report.
    """
    dist_vals: list[float | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        close = closes.get(ticker)

        if close is None or close.empty:
            dist_vals.append(None)
            continue

        c = close.dropna().sort_index()
        loc = c.index.searchsorted(sig_date, side="left")
        if loc <= 0 or loc >= len(c):
            dist_vals.append(None)
            continue

        if loc < DIST_52W_WINDOW:
            dist_vals.append(None)
            continue

        prior = c.iloc[loc - DIST_52W_WINDOW:loc]
        if len(prior) == 0:
            dist_vals.append(None)
            continue

        high_52w = float(prior.max())
        price = float(c.iloc[loc])
        if high_52w <= 0:
            dist_vals.append(None)
            continue

        dist_vals.append(price / high_52w - 1.0)

    dist_series = pd.Series(dist_vals, index=fires.index, name="dist_52w_high")

    # Cross-sectional tercile assignment
    valid = dist_series.dropna()
    if len(valid) < 30:
        return pd.Series(np.nan, index=fires.index, name="dist_52w_tercile")

    q33 = float(valid.quantile(1 / 3))
    q67 = float(valid.quantile(2 / 3))
    tercile = np.where(
        dist_series.isna(),
        np.nan,
        np.where(dist_series <= q33, 0.0,
                 np.where(dist_series <= q67, 1.0, 2.0))
    )
    return pd.Series(tercile, index=fires.index, name="dist_52w_tercile")


def load_vix_series() -> pd.Series | None:
    """Load VIXCLS from data/fred/VIXCLS.parquet.

    Returns pd.Series (date index, float values) or None if file absent.
    """
    if not _VIXCLS_PATH.exists():
        log.warning("VIXCLS.parquet not found at %s", _VIXCLS_PATH)
        return None
    try:
        df = pd.read_parquet(_VIXCLS_PATH)
        if "vix_close" in df.columns:
            s = df["vix_close"].dropna().sort_index()
        elif df.shape[1] == 1:
            s = df.iloc[:, 0].dropna().sort_index()
        else:
            log.warning("VIXCLS.parquet: unexpected columns %s", df.columns.tolist())
            return None
        log.info("VIX loaded: %d rows, %s → %s", len(s), s.index.min(), s.index.max())
        return s
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load VIXCLS.parquet: %s", exc)
        return None


def assign_vix_regime(
    fire_dates: pd.Series,
    vix: pd.Series,
    *,
    trailing_years: int = 10,
) -> pd.Series:
    """VIX trailing-10y percentile band at each fire date.

    Band 0: VIX at fire below 33rd pctile of trailing 10y window.
    Band 1: 33rd..67th pctile.
    Band 2: above 67th pctile.
    NaN: insufficient history or VIX date not available.

    NO-INFERENCE BANNER: context column only. No family, no promotion path.
    vol_regime overlay already failed additive-value vs vol-target (§3, §2 masterplan).
    """
    trailing_bars = trailing_years * 252
    bands: list[float | None] = []

    for sig_date in fire_dates:
        sig_date = pd.Timestamp(sig_date)
        # Find prior VIX series up to (not including) fire date
        prior = vix[vix.index < sig_date]
        if len(prior) < trailing_bars:
            bands.append(None)
            continue

        # Take trailing 10y window
        window = prior.iloc[-trailing_bars:]
        lo33 = float(window.quantile(VIX_BAND_LO / 100.0))
        hi67 = float(window.quantile(VIX_BAND_HI / 100.0))

        # VIX at/just before fire date
        vix_at_fire_idx = prior.index.searchsorted(sig_date, side="left") - 1
        if vix_at_fire_idx < 0:
            bands.append(None)
            continue
        vix_val = float(prior.iloc[vix_at_fire_idx])

        if vix_val < lo33:
            bands.append(0.0)   # low-vol
        elif vix_val <= hi67:
            bands.append(1.0)   # mid-vol
        else:
            bands.append(2.0)   # high-vol

    return pd.Series(bands, index=fire_dates.index, name="vix_regime_band")


# ---------------------------------------------------------------------------
# Descriptive context table (no BH, no CI — pure display)
# ---------------------------------------------------------------------------

def build_context_table(
    graded: pd.DataFrame,
    context_col: str,
    outcome_cols: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Descriptive rate table by context-column value. No inference; no CI."""
    if outcome_cols is None:
        outcome_cols = ["stop5", "rotational_liftoff", "positional_liftoff",
                        "dead_money", "mae63", "mfe63"]

    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    rows = []
    for band_val in sorted(df_ok[context_col].dropna().unique()):
        g = df_ok[df_ok[context_col] == band_val]
        rec: dict[str, Any] = {context_col: band_val, "n_fires": len(g)}
        for oc in outcome_cols:
            if oc in g.columns:
                vals = g[oc].dropna()
                rec[oc] = round(float(vals.mean()), 4) if len(vals) > 0 else None
            else:
                rec[oc] = None
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# Main study runner for one panel
# ---------------------------------------------------------------------------

def run_sts_study(
    panel_name: str,
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    hl_panels: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    vix: pd.Series | None,
    *,
    fe_granularity: str = "date",
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run S-TS ADX residual study for one panel."""
    fires = fires.copy()
    fires["sector"] = fires["ticker"].map(sector_map)

    total_fires = len(fires)
    log.info("Panel %s: %d fires", panel_name, total_fires)

    # ----- Compute ADX14 at fire bars ----------------------------------------
    log.info("  Computing ADX14 at fire bars...")
    adx14_series, adx14_lag5_series, excl_counts = compute_adx_at_fires(fires, hl_panels)
    log.info("  ADX exclusion counts: %s", excl_counts)

    stratum = build_adx_stratum(adx14_series, adx14_lag5_series)

    n_stratum_a = int((stratum == 1.0).sum())
    n_stratum_b = int((stratum == 0.0).sum())
    n_excluded   = int(stratum.isna().sum())
    log.info("  Stratum A (adx_rising=1): %d fires", n_stratum_a)
    log.info("  Stratum B (adx_rising=0): %d fires", n_stratum_b)
    log.info("  Excluded (no H/L or insufficient history): %d fires", n_excluded)

    # Exclusion-accounting reconciliation: the printed bucket counts must sum to the
    # number of NaN-stratum fires.  A mismatch means a code path is dropping fires
    # silently into the wrong bucket (or no bucket at all).
    _buckets_sum = sum(excl_counts.values())
    if _buckets_sum != n_excluded:
        log.error(
            "Exclusion-count mismatch: buckets sum to %d but stratum.isna()=%d "
            "(counts=%s). Report totals will be inconsistent.",
            _buckets_sum, n_excluded, excl_counts,
        )

    # ----- Grade fires with ADX stratum column --------------------------------
    log.info("  Grading fires...")
    graded = grade_fires(fires, closes, extra_columns={"adx_rising": stratum})
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, total_fires)

    # Gradable fires in each stratum
    graded_ok = graded[graded["gradable"].fillna(False)]
    n_grad_a = int((graded_ok["adx_rising"] == 1.0).sum())
    n_grad_b = int((graded_ok["adx_rising"] == 0.0).sum())
    n_grad_excl = int(graded_ok["adx_rising"].isna().sum())

    # ----- Free context columns -----------------------------------------------
    log.info("  Computing dist_52w_high context column...")
    dist_tercile = compute_dist_52w_high_tercile(fires, closes)
    graded["dist_52w_tercile"] = dist_tercile.reindex(graded.index).values
    log.info("  dist_52w_tercile non-null: %d", graded["dist_52w_tercile"].notna().sum())

    if vix is not None:
        log.info("  Computing VIX regime bands...")
        vix_band = assign_vix_regime(pd.Series(graded["date"].values, index=graded.index), vix)
        graded["vix_regime_band"] = vix_band.values
        log.info("  vix_regime_band non-null: %d", graded["vix_regime_band"].notna().sum())
    else:
        graded["vix_regime_band"] = np.nan
        log.warning("  VIX data unavailable; vix_regime_band set to NaN")

    # Refresh graded_ok AFTER context columns are attached (so they're present in build_context_table)
    graded_ok = graded[graded["gradable"].fillna(False)]

    # ----- R1 effect table (only on fires with valid ADX stratum) ------------
    log.info("  Computing R1 effect table (n_bootstrap=%d)...", n_bootstrap)
    graded_adx = graded[graded["adx_rising"].notna()].copy()
    recall = compute_recall(graded_adx, "adx_rising")
    eff = fast_effect_table(
        graded_adx, "adx_rising",
        fe_granularity=fe_granularity,
        sector_col="sector",
        n_bootstrap=n_bootstrap,
        family_label=f"STS_adx_{panel_name}",
    )
    log.info("  Effect table done.")

    # ----- Era table ----------------------------------------------------------
    era_tbl = fast_era_table(graded_adx, "adx_rising", panel_label=panel_name)

    # ----- Era-split by the 4 program eras (2012-2015, 2016-2019, 2020-2022, 2023-2026) ------
    graded_adx["_era"] = pd.to_datetime(graded_adx["date"]).apply(_assign_era)
    era_results: dict[str, Any] = {}
    for era_name in PROGRAM_ERAS:
        era_sub = graded_adx[graded_adx["_era"] == era_name].copy()
        if len(era_sub) < 100:
            era_results[era_name] = {"n": len(era_sub), "note": "insufficient n for FE"}
            continue
        eff_era = fast_effect_table(
            era_sub, "adx_rising",
            fe_granularity=fe_granularity,
            sector_col="sector",
            n_bootstrap=min(n_bootstrap, 200),  # faster for sub-eras
            family_label=f"STS_adx_{panel_name}_{era_name}",
        )
        era_effects = {e["label"]: e for e in eff_era.get("effects", [])}
        stop5_era = era_effects.get("stop5", {})
        era_results[era_name] = {
            "n_total": eff_era.get("n_total", 0),
            "n_treat": eff_era.get("n_treatment", 0),
            "n_ctrl":  eff_era.get("n_control", 0),
            "stop5_coef": stop5_era.get("coef"),
            "stop5_ci_lo": stop5_era.get("ci_lo"),
            "stop5_ci_hi": stop5_era.get("ci_hi"),
            "stop5_p": stop5_era.get("p_value"),
        }

    # ----- Context descriptive tables (NO inference) -------------------------
    dist_ctx_tbl = build_context_table(graded_ok, "dist_52w_tercile")
    vix_ctx_tbl  = build_context_table(graded_ok, "vix_regime_band")

    # ----- ADX descriptive stats at fire bars --------------------------------
    adx_valid = adx14_series.dropna()
    adx_stats: dict[str, Any] = {}
    if len(adx_valid) > 0:
        adx_stats = {
            "mean":  round(float(adx_valid.mean()), 2),
            "p25":   round(float(adx_valid.quantile(0.25)), 2),
            "p50":   round(float(adx_valid.quantile(0.50)), 2),
            "p75":   round(float(adx_valid.quantile(0.75)), 2),
            "pct_above_20": round(float((adx_valid > 20).mean()), 4),
        }

    return {
        "panel":               panel_name,
        "total_fires":         total_fires,
        "n_gradable":          n_gradable,
        "n_stratum_a":         n_stratum_a,
        "n_stratum_b":         n_stratum_b,
        "n_excluded_adx":      n_excluded,
        "exclusion_counts":    excl_counts,
        "n_grad_a":            n_grad_a,
        "n_grad_b":            n_grad_b,
        "n_grad_excl":         n_grad_excl,
        "adx_stats":           adx_stats,
        "recall":              recall,
        "effect_table":        eff,
        "era_table":           era_tbl.to_dict(orient="records"),
        "era_split_effects":   era_results,
        "dist_ctx_table":      dist_ctx_tbl,
        "vix_ctx_table":       vix_ctx_tbl,
        "fe_granularity":      fe_granularity,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Comparisons between strata are directionally valid within this constraint."
        ),
    }


# ---------------------------------------------------------------------------
# Panels runner
# ---------------------------------------------------------------------------

def run_all_panels(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run S-TS ADX study across deep + baskets panels."""
    _register_all_families(ledger_path)
    _register_sts_trials(ledger_path)

    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    vix = load_vix_series()

    panel_configs = [
        ("deep",    _FIRES_DEEP,    "date"),
        ("baskets", _FIRES_BASKETS, "date"),
    ]
    if panels:
        panel_configs = [(n, p, fe) for n, p, fe in panel_configs if n in panels]

    all_results: dict[str, Any] = {}
    for panel_name, fires_path, fe_gran in panel_configs:
        if not fires_path.exists():
            log.warning("Fire dump not found: %s — skipping", fires_path)
            all_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue

        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))

        closes = _get_closes(panel_name)
        hl_panels = _get_hl_panels(panel_name)

        res = run_sts_study(
            panel_name, fires, closes, hl_panels, sector_map, vix,
            fe_granularity=fe_gran,
            n_bootstrap=n_bootstrap,
        )
        all_results[panel_name] = res

    return all_results


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _write_context_table_md(
    lines: list[str],
    rows: list[dict[str, Any]],
    col_key: str,
    col_labels: dict[float, str],
    title: str,
) -> None:
    """Write descriptive context table. No inference, no CI."""
    lines.append(f"#### {title}")
    lines.append("")
    lines.append(
        "**NO-INFERENCE BANNER:** Descriptive only. No CI, no BH, no promotion path. "
        "Context column; not a registered candidate."
    )
    lines.append("")
    if not rows:
        lines.append("_(no data)_")
        lines.append("")
        return
    lines.append("| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        band = r.get(col_key)
        label = col_labels.get(float(band), str(band)) if band is not None else "—"
        lines.append(
            f"| {_fmt_f(band, 1)} | {label} | {r.get('n_fires', 0):,} | "
            f"{_fmt_pct(r.get('stop5'))} | {_fmt_pct(r.get('rotational_liftoff'))} | "
            f"{_fmt_pct(r.get('positional_liftoff'))} | {_fmt_pct(r.get('dead_money'))} | "
            f"{_fmt_f(r.get('mae63'))} | {_fmt_f(r.get('mfe63'))} |"
        )
    lines.append("")


def write_report(all_results: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# W1 S-TS ADX Residual Study — Entry-Stack Expansion")
    a("")
    a("**Status:** W1 report only — no promotion, no product change.")
    a("**Candidate:** S-TS (F6) — ADX trend-strength residual (STRATUM, expect-null).")
    a("**Date:** 2026-07-05")
    a("")
    a("---")
    a("")
    a("## NC Yardstick (RUL-3) — Reproduced from W1_NC_REPORT.md")
    a("")
    a("Per §10 RUL-3: null-competitors appear as the FIRST table. The S-TS coefficients")
    a("are shown after this yardstick for comparison.")
    a("")
    a("Direction note: stop5 is an ADVERSE outcome — a better stratum has a MORE NEGATIVE")
    a("stop5 coefficient. For liftoff the coefficient should be MORE POSITIVE.")
    a("")
    a("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall (treat arm) |")
    a("|---|---|---|---|---|---|")
    a("| deep    | NC-1A (T1-only)       | -0.0019 | [-0.016, +0.008] | no   | 89.1% |")
    a("| deep    | NC-1B (ticks=0)       |  0.0001 | [-0.015, +0.007] | no   | 90.8% |")
    a("| deep    | NC-2 (prox top-tercile)| -0.0427 | [-0.044, -0.031] | YES *| 33.4% |")
    a("| baskets | NC-1A (T1-only)       | -0.0036 | [-0.011, +0.006] | no   | 85.9% |")
    a("| baskets | NC-1B (ticks=0)       |  0.0099 | [+0.002, +0.015] | YES *| 90.9% |")
    a("| baskets | NC-2 (prox top-tercile)| -0.1012 | [-0.108, -0.096] | YES *| 34.0% |")
    a("")
    a("Source: research/entry_stack/W1_NC_REPORT.md (2026-07-05).")
    a("")
    a("---")
    a("")
    a("## Adjacency Citation (R2 — RUL-2)")
    a("")
    a("**Nearest falsified relatives:**")
    a("1. Trend/location guards (rising MAs, ATR-contraction, higher-low): **FALSIFIED** as")
    a("   exposure artifacts (DURABLE_BOTTOM_FRAMEWORK.md:606; masterplan §2/§3).")
    a("2. CT-LANE result: counter-trend buyable fires NOT-WORSE than aligned (n=7,392,")
    a("   −0.16/−0.6pp; masterplan §2/§3). Directional alignment hard-blocks unjustified.")
    a("")
    a("**Mechanical difference from falsified relatives:**")
    a("ADX14 measures trend *energy* directionlessly — it does NOT require alignment with")
    a("a moving average or a directional price structure. The falsified guards required")
    a("directional confirmation. ADX makes no directional claim; it asks only whether the")
    a("market is in a 'trending' state by volatility/momentum energy metrics.")
    a("This distinction is exactly why the question remains open (never studied in this")
    a("repo — census 3A); these priors make the prior hostile, not dispositive.")
    a("")
    a("---")
    a("")
    a("## Pre-Registered Expect-Null Declaration (RUL-5)")
    a("")
    a("The registered expectation is a NULL. Quoting masterplan §3 F6:")
    a("> \"Expectation: pre-registered expect-null. Value = a citable kill (or a surprise")
    a("> worth having).\"")
    a("")
    a("Non-null is defined ONLY as: **pooled FE coefficient with BH-adjusted CI excluding 0**.")
    a("Single-era excursions are NOISE by pre-registration — they are printed below but")
    a("cannot satisfy the non-null bar.")
    a("")
    a("If non-null is found, the next step is baskets OOS replication — that is not")
    a("decided by this script. The script prints the result; adjudication is upstream.")
    a("")
    a("---")
    a("")
    a("## Trial Registration")
    a("")
    a("Family: `esx_ts_adx` (budget=4, pre-registered at W0).")
    a("4 trial configs logged: 1 def × 2 panels × 2 era-splits.")
    a("")
    a("---")
    a("")
    a("## Frozen Stratum Definition")
    a("")
    a("Not tunable (masterplan §3 F6):")
    a("")
    a("- **Stratum A (adx_rising=1):** `adx14 > 20 AND adx14 > adx14_at_(bar−5)` at fire bar.")
    a("- **Stratum B (adx_rising=0):** complement.")
    a("- ADX14 via `engine.stock_technicals.adx_dmi(high, low, close, n=14)`.")
    a("- Close-only fires: EXCLUDED (printed below, not silently zeroed).")
    a("- Lookback for ADX: strictly prior bars including fire date. No lookahead.")
    a("")
    a("---")
    a("")
    a("## Free Context Columns — NO-INFERENCE BANNER")
    a("")
    a("The following columns are CONTEXT-ONLY. They carry:")
    a("- No registered family.")
    a("- No BH correction.")
    a("- No promotion path.")
    a("- No CI is reported.")
    a("- Breakout alpha (52w-high) is already FALSIFIED (masterplan §2). The dist_52w")
    a("  tercile here is OVERHEAD SUPPLY CONTEXT (S-OH candidate, §3 D3) — not breakout.")
    a("- Vol-regime overlay already FAILED additive-value vs vol-target (masterplan §3/§2).")
    a("  VIX bands here are index-level regime context only.")
    a("")
    a("---")
    a("")

    for panel_name, res in all_results.items():
        a(f"## Panel: {panel_name.upper()}")
        a("")
        if "error" in res:
            a(f"**ERROR:** {res['error']}")
            a("")
            continue

        a(f"**SURVIVOR BIAS STAMP:** {res.get('survivor_stamp', '')}")
        a("")
        a(f"- Total fires loaded: {res.get('total_fires', 0):,}")
        a(f"- Gradable fires: {res.get('n_gradable', 0):,}")
        a(f"- FE granularity: `{res.get('fe_granularity', 'date')}` (frozen per RUL-12)")
        a("")

        # ADX exclusion counts (printed, not hidden)
        excl = res.get("exclusion_counts", {})
        n_excl = res.get("n_excluded_adx", 0)
        a("### Close-Only Exclusion Report")
        a("")
        a("ADX14 requires H/L panels. Close-only fires (no H/L available) are")
        a("excluded from the ADX stratum and printed here (not silently zeroed).")
        a("")
        a(f"- Fires with no H/L panel: **{excl.get('no_hl_panel', 0):,}**")
        a(f"- Insufficient history (< 28 bars): **{excl.get('insufficient_history', 0):,}**")
        a(f"- Date not in panel: **{excl.get('date_not_in_panel', 0):,}**")
        a(f"- ADX NaN (computation failure): **{excl.get('adx_nan', 0):,}**")
        a(f"- Insufficient lag5 history (< 5 bars prior ADX): "
          f"**{excl.get('insufficient_lag5_history', 0):,}**")
        a(f"- **Total excluded: {n_excl:,}** of {res.get('total_fires', 0):,} fires "
          f"({n_excl / max(1, res.get('total_fires', 1)):.1%})")
        a("")

        # ADX descriptive stats
        adx_stats = res.get("adx_stats", {})
        if adx_stats:
            a("### ADX14 Distribution at Fire Bars")
            a("")
            a(f"- Mean: {adx_stats.get('mean', '—')}")
            a(f"- P25 / P50 / P75: {adx_stats.get('p25', '—')} / "
              f"{adx_stats.get('p50', '—')} / {adx_stats.get('p75', '—')}")
            a(f"- Pct ADX > 20 (level condition): {_fmt_pct(adx_stats.get('pct_above_20'))}")
            a("")

        # Stratum sizes
        a("### Stratum Sizes")
        a("")
        a(f"- Stratum A (adx_rising=1, all fires): {res.get('n_stratum_a', 0):,}")
        a(f"- Stratum B (adx_rising=0, all fires): {res.get('n_stratum_b', 0):,}")
        a(f"- Excluded (no valid ADX): {res.get('n_excluded_adx', 0):,}")
        a(f"- Gradable stratum A: {res.get('n_grad_a', 0):,}")
        a(f"- Gradable stratum B: {res.get('n_grad_b', 0):,}")
        a(f"- Gradable excluded: {res.get('n_grad_excl', 0):,}")
        a("")

        # Recall
        rc = res.get("recall", {})
        a("### Recall")
        a("")
        a(f"**Stratum A recall** (adx_rising fires as fraction of all gradable with valid ADX):")
        a(f"  {_fmt_pct(rc.get('recall'))} ({rc.get('n_treatment', 0):,} of "
          f"{rc.get('n_all', 0):,})")
        a(f"**Recall COST:** {_fmt_pct(1.0 - rc.get('recall', 1.0))} of fires are Stratum B")
        a("")

        # Main effect table
        eff = res.get("effect_table", {})
        _write_effect_md(lines, eff, "S-TS ADX Effect Table (R1 FE, block bootstrap)")

        # Era table
        era_recs = res.get("era_table", [])
        if era_recs:
            era_df = pd.DataFrame(era_recs)
            prog_era = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
            if not prog_era.empty:
                a("#### Era × Stratum Table (program eras)")
                a("")
                cols = [c for c in ["era", "adx_rising", "n_fires", "stop5_rate", "mae63_mean"]
                        if c in prog_era.columns]
                a("| " + " | ".join(cols) + " |")
                a("|" + "---|" * len(cols))
                for _, row in prog_era.iterrows():
                    cells = []
                    for c in cols:
                        v = row.get(c)
                        if c == "stop5_rate":
                            cells.append(_fmt_pct(v))
                        elif c == "mae63_mean":
                            cells.append(_fmt_f(v))
                        else:
                            cells.append(str(v) if v is not None else "—")
                    a("| " + " | ".join(cells) + " |")
                a("")

        # Era-split coefficients (show but note that single-era excursions are noise per RUL-5)
        era_split = res.get("era_split_effects", {})
        if era_split:
            a("#### Era-Split Stop5 Coefficients")
            a("")
            a("Per pre-registration (RUL-5): single-era excursions are NOISE. Printed for")
            a("completeness; they cannot satisfy the non-null bar.")
            a("")
            a("| Era | N total | N treat | N ctrl | Stop5 coef | 95% CI | CI excl 0? |")
            a("|---|---|---|---|---|---|---|")
            for era_name in PROGRAM_ERAS:
                er = era_split.get(era_name, {})
                if "note" in er:
                    a(f"| {era_name} | {er.get('n', '—')} | — | — | — | — | _{er['note']}_ |")
                    continue
                coef = er.get("stop5_coef")
                ci_lo = er.get("stop5_ci_lo")
                ci_hi = er.get("stop5_ci_hi")
                ci_str = f"[{ci_lo:+.3f}, {ci_hi:+.3f}]" if (ci_lo is not None and ci_hi is not None) else "—"
                excl_z = "YES *" if (ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0)) else "no"
                a(f"| {era_name} | {er.get('n_total', 0):,} | {er.get('n_treat', 0):,} | "
                  f"{er.get('n_ctrl', 0):,} | {_fmt_f(coef, 4)} | {ci_str} | {excl_z} |")
            a("")

        a("---")
        a("")

    # Context tables (combined across panels)
    a("## Free Context Columns (No Inference)")
    a("")
    a("These tables are descriptive rate summaries by context band. No CI is computed.")
    a("No promotion path. No registered family. See header for NO-INFERENCE BANNER.")
    a("")

    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        a(f"### Panel: {panel_name.upper()}")
        a("")

        dist_ctx = res.get("dist_ctx_table", [])
        _write_context_table_md(
            lines, dist_ctx,
            "dist_52w_tercile",
            {0.0: "deepest below 52w high", 1.0: "mid", 2.0: "closest to 52w high"},
            "S-OH Context: Distance from 52-Week High (tercile bands)",
        )

        vix_ctx = res.get("vix_ctx_table", [])
        _write_context_table_md(
            lines, vix_ctx,
            "vix_regime_band",
            {0.0: "low-vol (VIX < 33rd pctile trail-10y)",
             1.0: "mid-vol (33rd–67th pctile)",
             2.0: "high-vol (VIX > 67th pctile trail-10y)"},
            "VIX Regime Context: Trailing-10y Percentile Bands",
        )

    a("---")
    a("")
    a("## Verdict")
    a("")
    a("Per masterplan §3 F6 and RUL-5:")
    a("")
    a("The ADX-rising stratum is a **pre-registered expect-null study**.")
    a("The verdict is determined solely by: **pooled FE coefficient with BH-adjusted CI")
    a("excluding 0 on the primary endpoint (stop5)**.")
    a("")

    # Compute verdict across panels
    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        eff = res.get("effect_table", {})
        effects = {e["label"]: e for e in eff.get("effects", [])}
        stop5 = effects.get("stop5", {})
        bh = {b["label"]: b for b in eff.get("bh_panel", [])}
        stop5_bh = bh.get("stop5", {})
        coef = stop5.get("coef")
        ci_lo = stop5.get("ci_lo")
        ci_hi = stop5.get("ci_hi")
        bh_rej = stop5_bh.get("rejected")
        excl_z = ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0)

        a(f"**Panel {panel_name.upper()}:**")
        a(f"- stop5 coef = {_fmt_f(coef, 4)}, 95% CI = {_ci_str(stop5)}")
        a(f"- CI excludes 0: {'YES' if excl_z else 'NO'}")
        a(f"- BH q ≤ 0.10 rejected: {'YES' if bh_rej else 'NO'}")
        if excl_z and bh_rej:
            a("- **POSSIBLE NON-NULL** (both CI-excluding-0 AND BH-rejected). "
              "Per RUL-5: baskets OOS replication required before chip discussion. "
              "Adjudication is upstream of this script.")
            # §5 CHIP-path qualification check — print inline regardless of OOS outcome.
            # The coef sign and magnitude relative to the frozen 2pp CHIP floor (W0 RUL-7)
            # are load-bearing for adjudication framing.
            if coef is not None:
                chip_floor_pp = 2.0  # frozen 2pp floor, W0_BASELINES.md RUL-7
                coef_pp = abs(coef) * 100.0
                adverse_sign = coef > 0  # stop5 is adverse; a CHIP needs NEGATIVE coef
                if adverse_sign or coef_pp < chip_floor_pp:
                    reasons = []
                    if adverse_sign:
                        reasons.append("adverse sign (ADX-rising = MORE stops, not fewer)")
                    if coef_pp < chip_floor_pp:
                        reasons.append(
                            f"magnitude {coef_pp:.1f}pp < {chip_floor_pp:.0f}pp §5 CHIP floor"
                        )
                    a(f"- **CHIP PATH FORECLOSED** regardless of OOS outcome: "
                      f"{'; '.join(reasons)}. "
                      "A CHIP requires a beneficial (negative) stop5 coef ≥ 2pp CI-excluding-0. "
                      "The only live follow-up would be a HYGIENE/veto evaluation "
                      "under its own §5 bar — not a chip.")
        else:
            a("- **NULL** — CI includes 0 or BH not rejected. "
              "Pre-registered expected outcome confirmed.")
        a("")

    a("**Summary:** The pre-registered expectation was a null. See individual panel")
    a("verdicts above. Single-era excursions in the era table cannot satisfy the non-null")
    a("bar and are printed for completeness only (RUL-5).")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_w1_sts.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*'validated' word deliberately absent (CI-enforced).*")
    a("*No promotion language. Reports only.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion W1 — S-TS ADX Residual Study (F6).",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "W1_STS_REPORT.md"),
        help="Output path for W1_STS_REPORT.md",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=1000,
        help="Block-bootstrap resamples (default 1000; use --smoke for 50)",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke test: 50 bootstrap, deep panel only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot = 50 if args.smoke else args.n_bootstrap
    panels = ["deep"] if args.smoke else args.panel

    log.info("Starting W1 S-TS ADX study (n_bootstrap=%d, panels=%s)", n_boot, panels or "all")
    all_results = run_all_panels(n_bootstrap=n_boot, panels=panels)
    write_report(all_results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
