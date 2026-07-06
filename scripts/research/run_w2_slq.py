"""Entry-Stack Expansion W2 — S-LQ Liquidity Hygiene Band Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §3 F4, §5, §10.
Amendment 1 ref: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md
  RUL-13: primary horizons = 21d (stop5, fwd_mdd_21/mae21, clean8_21, zone_held_21,
           days_to_10). 63d+ NEVER decides an entry verdict.
  RUL-14: co-primaries zone_held_21, stop_vol_21 (stop_vol_21 excluded from BH pool).

FAMILY: esx_lq_bands (budget=12 — already pre-registered at W0).
Budget itemisation: 2 proxies x 3 fixed-tercile bands x 2 panels.

TASK S-LQ: Liquidity / tradability hygiene bands.
Mechanism: entering a name whose effective spread is widening / depth thinning
raises realized MAE mechanically (fills degrade, stops slip). Not alpha — cost physics.
Adjacency (R2): none. Census: zero EOD spread proxies repo-wide prior to W0.

PROXIES:
  1. Amihud ILLIQ — engine/entry_primitives.amihud_series (all panels incl. deep).
  2. Corwin-Schultz HL-spread — engine/entry_primitives.corwin_schultz_spread_series
     (H/L panels only: deep + baskets).

BAND RULE (FIXED, NEVER FITTED):
  Cross-sectional terciles computed on the trailing year (252 bars) at each fire date.
  band 0 = bottom tercile (LEAST liquid / WIDEST spread — worst)
  band 1 = middle tercile
  band 2 = top tercile (MOST liquid / NARROWEST spread — best)

DETERIORATION METRIC (fixed window = 20 bars):
  Sign of the 20d slope of the proxy series at fire date.
  +1 = proxy INCREASING (liquidity DETERIORATING — worse for Amihud, wider spread for CS)
  -1 = proxy DECREASING (liquidity IMPROVING)

ENDPOINTS (RUL-13 21d primaries):
  stop5, fwd_mdd_21 (mae21), rotational_liftoff (clean8_21),
  zone_held_21 (RUL-14 co-primary), days_to_10.
  Also: dead_money, cushion_rot, stop_vol_21 (context; excluded from BH pool).

HYGIENE BAR (masterplan §5):
  A. CI-excluding-0 degradation on stop5 OR fwd_mdd_21 for the WORST band.
     "Degradation" = stop5 CI_lo > 0 (more adverse stops, CI entirely positive)
     OR fwd_mdd_21 CI_hi < 0 (more negative MDD, CI entirely below zero).
     Note: fwd_mdd_21 <=0, more-negative = worse; CI_hi < 0 means significantly
     more adverse MDD (worse).
  B. Affected volume <= 10% of fires (a hygiene rule that eats recall is a gate in
     disguise).
  Verdict: BOTH A and B must be met for "HYGIENE BAR MET".

NC-2 PROXIMITY MARGINALITY (insurance):
  For any band showing stop5 OR fwd_mdd_21 improvement (not degradation), run the
  both-arm NC-2 proximity-band FE test. Reuses _run_nc2_band_fe from S-UR machinery.
  Purpose: ensure a spuriously-low-liquidity band is not confounded with proximity
  to a gate fire (stale-fire bias).

DESIGN CONTROLS:
  - R1 date-FE estimator (RUL-12); FE granularity frozen at W0 sign-off.
  - Episode-clustered block bootstrap CI.
  - Era splits {2012-2015, 2016-2019, 2020-2022, 2023-2026} on deep panel.
  - Survivor bias stamped on every absolute rate.
  - Family-wide BH q<=0.10 over esx_lq_bands (stop_vol_21 and days_to_10 excluded).
  - NC yardstick preamble from W1_NC_REPORT.md (RUL-3).
  - Report only — no promotion decisions (RUL-5); no 'validated' wording (CI-enforced).

VERDICT LOGIC (pre-registered, no adjudication in report):
  If NO band clears the hygiene bar: verdict = SHIP NOTHING. Primitives remain
  kernel-context; no invented liquidity tilt. Print this plainly.
  If worst band clears hygiene bar with affected volume <=10%: HYGIENE BAR MET.
  Adjudication belongs to the orchestrator, not this study.

SIGN CONVENTION:
  stop5 is ADVERSE. CI_lo > 0 = significantly MORE stops (WORSE — degradation direction).
  fwd_mdd_21 values are <=0. CI_hi < 0 = more-negative MDD (WORSE — degradation direction).
  zone_held_21 is BENEFICIAL. CI_hi > 0 = better zone-holding (note: hygiene uses degradation,
    so look for CI_lo < 0 for significant impairment).

PANELS:
  - deep:    data/stocks/ (close + high + low + volume)
  - baskets: data/baskets/ohlcv/ (close + high + low + volume)
  Both panels have H/L → both proxies available on both panels.

Usage:
    cd /path/to/repo
    python scripts/research/run_w2_slq.py
    python scripts/research/run_w2_slq.py --smoke
    python scripts/research/run_w2_slq.py --n-bootstrap 500 --panel deep baskets
    python scripts/research/run_w2_slq.py --out research/entry_stack/W2_SLQ_REPORT.md
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
# Import harness primitives from W0 PR-C — REUSE (L1)
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
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
)

# Import fast R1 estimator and formatting helpers from NC runner — REUSE (L1)
from scripts.research.run_w1_nc import (  # noqa: E402
    fast_r1_estimate,
    fast_effect_table,
    fast_era_table,
    bh_correction,
    _fast_make_blocks,
    _empty_r1,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
    compute_nc2_proximity_proxy,
    assign_nc2_bands,
    _eq_proximity_long,
)

# NC-2 band FE and family-wide BH from S-UR — REUSE (L1)
from scripts.research.run_w2_sur import (  # noqa: E402
    _run_nc2_band_fe,
    _parse_nc_yardstick_from_report,
    ADVERSE_METRICS,
    BENEFICIAL_METRICS,
    NONINFERIORITY_MARGIN,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"
_DEEP_STORE    = _DATA / "stocks"
_BASKETS_OHLCV = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Study-level constants
# ---------------------------------------------------------------------------
FAMILY_NAME = "esx_lq_bands"
FAMILY_BUDGET = 12  # pre-registered at W0; verify no duplicate (RUL-11)

# Proxy names
PROXY_AMIHUD = "amihud"
PROXY_CS = "corwin_schultz"
PROXIES = [PROXY_AMIHUD, PROXY_CS]

# Band labels (0=worst/least-liquid, 2=best/most-liquid)
BAND_LABELS = {0: "bottom_tercile (worst)", 1: "mid_tercile", 2: "top_tercile (best)"}
N_BANDS = 3

# Trailing year for cross-sectional tercile computation (fixed rule, never fitted)
TRAILING_YEAR_BARS = 252

# Deterioration: sign of 20d slope of proxy series at fire date
DETERIORATION_WINDOW = 20

# Hygiene bar affected-volume threshold: <= 10% of fires (masterplan §5)
HYGIENE_VOLUME_THRESHOLD = 0.10

# Outcome columns — RUL-13 corrected (21d primaries)
OUTCOME_COLS = [
    "stop5",              # immediate stop-out (primary, ADVERSE)
    "fwd_mdd_21",         # mae21: max adverse excursion 21d (RUL-13 primary, ADVERSE in direction)
    "rotational_liftoff", # clean8_21 terminal state (BENEFICIAL)
    "dead_money",         # dead-money rate (ADVERSE)
    "cushion_rot",        # cushion incidence (BENEFICIAL)
    "zone_held_21",       # RUL-14 co-primary: vol-scaled zone held 21d (BENEFICIAL)
    "stop_vol_21",        # RUL-14: adjudication context; EXCLUDED from BH pool (mirror)
    "days_to_10",         # descriptive only; EXCLUDED from BH pool (collider)
]

# BH pool excludes mirrors and colliders
OUTCOME_COLS_BH = [c for c in OUTCOME_COLS if c not in ("stop_vol_21", "days_to_10")]

# ADVERSE_METRICS and BENEFICIAL_METRICS imported from run_w2_sur (L1 reuse)
# Override to add fwd_mdd_21 correctly:
#   fwd_mdd_21 values are <=0. More negative = worse. The R1 coefficient for
#   the worst band will be NEGATIVE (more negative MDD). For degradation:
#   CI_hi < 0 means significantly more-negative (worse). In ADVERSE_METRICS
#   the convention is "higher = worse"; but fwd_mdd_21's raw values are <=0
#   and more-negative = worse. So the R1 coef: negative coef on worst band
#   means more adverse. For hygiene bar: we want CI_hi < 0 for degradation.
# The BENEFICIAL_METRICS set covers fwd_mdd_21 from run_w2_sur, meaning the
# SUR machinery treats a positive coef as "better MDD" (less negative = good).
# For SLQ hygiene: worst band degradation = negative coef on fwd_mdd_21,
# so CI_hi < 0 is the degradation condition. This is consistent.

# ---------------------------------------------------------------------------
# OHLCV loaders
# ---------------------------------------------------------------------------

def _load_deep_ohlcv() -> dict[str, pd.DataFrame]:
    """Load deep panel OHLCV (close + high + low + volume)."""
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            required = ["close"]
            if not all(c in df.columns for c in required):
                continue
            cols = [c for c in ("close", "high", "low", "volume") if c in df.columns]
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("deep: failed to load %s: %s", path.name, exc)
    log.info("Loaded %d deep OHLCV records", len(store))
    return store


def _load_baskets_ohlcv() -> dict[str, pd.DataFrame]:
    """Load baskets panel OHLCV (close + high + low + volume)."""
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                continue
            cols = [c for c in ("close", "high", "low", "volume") if c in df.columns]
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("baskets: failed to load %s: %s", path.name, exc)
    log.info("Loaded %d basket OHLCV records", len(store))
    return store


# ---------------------------------------------------------------------------
# Proxy computation per ticker at a fire date
# ---------------------------------------------------------------------------

def _compute_proxy_at_fire(
    df: pd.DataFrame,
    fire_date: pd.Timestamp,
    proxy: str,
    trailing_bars: int = TRAILING_YEAR_BARS,
) -> float | None:
    """Compute proxy value at fire_date using trailing_bars of history.

    For Amihud: requires close + volume columns.
    For Corwin-Schultz: requires high + low columns.

    Returns the proxy value at fire_date (last bar of the trailing window),
    or None if data is insufficient or columns are missing.
    """
    from engine.entry_primitives import amihud_series, corwin_schultz_spread_series

    # Truncate to fire_date (strictly prior — causal)
    sub = df[df.index <= fire_date].copy()
    if len(sub) < trailing_bars:
        return None

    # Take trailing_bars history ending at fire_date
    sub = sub.iloc[-trailing_bars:]

    try:
        if proxy == PROXY_AMIHUD:
            if "volume" not in sub.columns or "close" not in sub.columns:
                return None
            vol = sub["volume"].replace(0, np.nan)
            if vol.isna().all():
                return None
            s = amihud_series(sub["close"], vol, win=20)
        elif proxy == PROXY_CS:
            if "high" not in sub.columns or "low" not in sub.columns:
                return None
            s = corwin_schultz_spread_series(sub["high"], sub["low"])
        else:
            return None

        if s.empty or s.isna().all():
            return None

        # Return the value at or nearest to fire_date
        val = s.iloc[-1]
        return float(val) if pd.notna(val) else None

    except TypeError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_proxy_at_fire: %s %s: %s", proxy, fire_date, exc)
        return None


def _compute_deterioration_sign(
    df: pd.DataFrame,
    fire_date: pd.Timestamp,
    proxy: str,
    window: int = DETERIORATION_WINDOW,
) -> int | None:
    """Compute sign of 20d slope of proxy at fire_date.

    Returns +1 if proxy increasing (deteriorating liquidity),
    -1 if proxy decreasing (improving liquidity),
    None if insufficient data.
    """
    from engine.entry_primitives import amihud_series, corwin_schultz_spread_series

    sub = df[df.index <= fire_date].copy()
    min_bars = window + 20  # need the series to have settled
    if len(sub) < min_bars:
        return None

    try:
        if proxy == PROXY_AMIHUD:
            if "volume" not in sub.columns or "close" not in sub.columns:
                return None
            vol = sub["volume"].replace(0, np.nan)
            if vol.isna().all():
                return None
            s = amihud_series(sub["close"], vol, win=20)
        elif proxy == PROXY_CS:
            if "high" not in sub.columns or "low" not in sub.columns:
                return None
            s = corwin_schultz_spread_series(sub["high"], sub["low"])
        else:
            return None

        if s.empty:
            return None

        # Take last window+1 bars to compute slope
        s_tail = s.dropna().iloc[-(window + 1):]
        if len(s_tail) < window:
            return None

        slope = float(s_tail.iloc[-1] - s_tail.iloc[0])
        if slope > 0:
            return 1   # deteriorating
        elif slope < 0:
            return -1  # improving
        else:
            return 0

    except TypeError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_deterioration_sign: %s %s: %s", proxy, fire_date, exc)
        return None


# ---------------------------------------------------------------------------
# Band assignment: cross-sectional terciles at each fire date
# ---------------------------------------------------------------------------

def assign_lq_bands(
    fires: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
    proxy: str,
    trailing_bars: int = TRAILING_YEAR_BARS,
) -> pd.DataFrame:
    """Assign cross-sectional liquidity tercile bands to gate fires.

    BAND RULE (FIXED, NEVER FITTED):
    For each fire date, compute the proxy value for every ticker with sufficient
    history (trailing_bars). Assign tercile bands cross-sectionally (0=worst,
    2=best). The tercile thresholds are determined only from the trailing-year
    data at that date — never from forward data.

    Also computes deterioration sign (20d slope) for each fire.

    Parameters
    ----------
    fires : gate-fire DataFrame with 'ticker', 'date' columns.
    ohlcv_store : {ticker: OHLCV DataFrame}.
    proxy : PROXY_AMIHUD or PROXY_CS.
    trailing_bars : history window for proxy computation (default 252 = 1 year).

    Returns
    -------
    fires DataFrame with added columns: lq_proxy_val, lq_band, lq_det_sign.
    lq_band: 0 (worst/least liquid) to 2 (best/most liquid); NaN if not computable.
    lq_det_sign: +1 (deteriorating), -1 (improving), 0 (flat), NaN if not computable.
    """
    fires = fires.copy()
    fires["date"] = pd.to_datetime(fires["date"])

    # Batch by unique fire date to reduce redundant computations.
    # For each unique fire date, compute proxy cross-section for all tickers
    # with sufficient history.
    unique_dates = sorted(fires["date"].unique())
    log.info("assign_lq_bands: proxy=%s, %d unique fire dates", proxy, len(unique_dates))

    # Pre-compute proxy values per (ticker, fire_date)
    # To avoid O(n_tickers × n_dates) computation, compute the full proxy series
    # per ticker ONCE, then use searchsorted to look up values at each fire date.
    # This is the same vectorized approach as label_coiled_context in run_w2_sur.

    from engine.entry_primitives import amihud_series, corwin_schultz_spread_series

    # Step 1: compute full proxy series per ticker (no truncation — causal lookup handled below)
    ticker_proxy_series: dict[str, pd.Series] = {}
    for ticker, df in ohlcv_store.items():
        if "close" not in df.columns:
            continue
        try:
            if proxy == PROXY_AMIHUD:
                if "volume" not in df.columns:
                    continue
                vol = df["volume"].replace(0, np.nan)
                if vol.isna().all():
                    continue
                s = amihud_series(df["close"], vol, win=20)
            elif proxy == PROXY_CS:
                if "high" not in df.columns or "low" not in df.columns:
                    continue
                s = corwin_schultz_spread_series(df["high"], df["low"])
            else:
                continue
            if not s.empty:
                ticker_proxy_series[ticker] = s.sort_index()
        except TypeError:
            raise
        except Exception:  # noqa: BLE001
            pass

    log.info("assign_lq_bands: proxy series built for %d/%d tickers",
             len(ticker_proxy_series), len(ohlcv_store))

    # Step 2: for each fire date, get cross-sectional proxy values from trailing window
    # then compute tercile thresholds on that cross-section.
    # For each ticker fire, look up the value at fire_date from its full series.
    proxy_vals: list[float | None] = []
    det_signs:  list[int | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])

        s = ticker_proxy_series.get(ticker)
        if s is None or s.empty:
            proxy_vals.append(None)
            det_signs.append(None)
            continue

        # Get value at or before fire_date (causal)
        s_prior = s[s.index <= fire_date]
        if len(s_prior) < trailing_bars:
            proxy_vals.append(None)
            det_signs.append(None)
            continue

        val = s_prior.iloc[-1]
        proxy_vals.append(float(val) if pd.notna(val) else None)

        # Deterioration: sign of slope over last DETERIORATION_WINDOW bars
        s_tail = s_prior.dropna().iloc[-DETERIORATION_WINDOW - 1:]
        if len(s_tail) >= DETERIORATION_WINDOW:
            slope = float(s_tail.iloc[-1] - s_tail.iloc[0])
            det_signs.append(1 if slope > 0 else (-1 if slope < 0 else 0))
        else:
            det_signs.append(None)

    fires["lq_proxy_val"] = proxy_vals
    fires["lq_det_sign"] = det_signs

    # Step 3: cross-sectional tercile bands, computed per fire date.
    # Tercile thresholds are based ONLY on the cross-section at each fire date —
    # never on all-time data (which would leak future information).
    # Approach: for each unique fire date, compute cross-sectional thresholds
    # from the proxy values of ALL tickers at that date (trailing-year lookback).
    # This mirrors what an investor would see: all tickers' liquidity at today.
    fires["lq_band"] = np.nan

    for fire_date in unique_dates:
        date_mask = fires["date"] == fire_date
        date_rows = fires[date_mask].copy()
        valid_vals = date_rows["lq_proxy_val"].dropna()

        if len(valid_vals) < 3:
            # Fewer than 3 values — cannot form terciles; leave as NaN
            continue

        # Compute cross-sectional tercile thresholds at this fire date.
        # For Amihud (higher = less liquid = worse): band 0 = lowest values = BEST
        # Wait — we define band 0 = WORST (least liquid).
        # Amihud: HIGHER value = MORE illiquid = WORSE → band 0 = top third of Amihud
        # CS spread: HIGHER value = WIDER spread = WORSE → band 0 = top third of CS
        # In both cases: band 0 = highest proxy values (worst liquidity).
        # So we invert: band = 2 - pd.qcut tercile (0=lowest values → 2=best liquid).
        p33 = float(np.nanpercentile(valid_vals, 33.33))
        p67 = float(np.nanpercentile(valid_vals, 66.67))

        # Guard degenerate cross-section: if all values are identical (p33 == p67),
        # tercile thresholds collapse and every name would land in band 0 (worst).
        # In this case leave bands NaN for the date — cannot form 3 distinct terciles.
        if p33 >= p67:
            log.warning(
                "assign_lq_bands: proxy=%s date=%s has degenerate cross-section "
                "(p33=%.6g >= p67=%.6g, n=%d) — bands left NaN for this date.",
                proxy, date, p33, p67, len(valid_vals),
            )
            continue

        n_in_band_counts: dict[float, int] = {}

        def _assign_band(v: float | None) -> float:
            if v is None or np.isnan(v):
                return np.nan
            # Higher proxy = worse liquidity → raw_tercile 0 = lowest (best), 2 = highest (worst)
            # Invert so band 0 = worst (highest proxy), band 2 = best (lowest proxy)
            if v >= p67:
                return 0.0   # top third of proxy values = worst liquidity = band 0
            elif v >= p33:
                return 1.0   # middle third = band 1
            else:
                return 2.0   # bottom third = lowest proxy = best liquidity = band 2

        assigned = date_rows["lq_proxy_val"].apply(_assign_band)
        fires.loc[date_mask, "lq_band"] = assigned

        # Warn if a single band captures >50% of fires (e.g. near-degenerate cross-section)
        for band_val in [0.0, 1.0, 2.0]:
            n_band = int((assigned == band_val).sum())
            if n_band > 0.5 * len(valid_vals):
                log.warning(
                    "assign_lq_bands: proxy=%s date=%s band=%.0f captures %d/%d fires "
                    "(>50%%) — near-degenerate cross-section.",
                    proxy, date, band_val, n_band, len(valid_vals),
                )

    n_assigned = int(fires["lq_band"].notna().sum())
    n_total = len(fires)
    log.info(
        "assign_lq_bands: proxy=%s — %d/%d fires with computable band (%.1f%%)",
        proxy, n_assigned, n_total, 100 * n_assigned / max(n_total, 1),
    )

    return fires


# ---------------------------------------------------------------------------
# Band analysis: run R1 estimate for each band vs rest
# Per-form clause evaluation on the same form (L1 requirement)
# ---------------------------------------------------------------------------

def run_band_analysis(
    graded_with_bands: pd.DataFrame,
    proxy: str,
    panel: str,
    sector_col: str = "sector",
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
    closes: dict[str, pd.Series] | None = None,
) -> dict[int, dict[str, Any]]:
    """Run R1 date-FE estimate for each liquidity band vs the rest.

    For each band b in {0, 1, 2}:
      stratum = 1 if lq_band == b else 0 (for fires with a valid band).

    Per RUL-12: FE granularity = date (frozen).
    Per L1: era table via fast_era_table with correct signature.
    Per task: also run NC-2 proximity FE for bands showing improvement
    (cheap insurance against proximity confounding).

    Returns dict: {band_int: analysis_results_dict}
    """
    results_by_band: dict[int, dict[str, Any]] = {}

    # Only use rows with a valid band assignment
    has_band = graded_with_bands["lq_band"].notna() & graded_with_bands["gradable"].fillna(False)
    df_valid = graded_with_bands[has_band].copy()

    # Single gradable-fire denominator for affected_volume_pct — used in both branches
    # to ensure consistency regardless of how many rows have a valid band.
    n_gradable_total = int(graded_with_bands["gradable"].fillna(False).sum())

    if df_valid.empty:
        log.warning("run_band_analysis: no gradable fires with valid band for proxy=%s", proxy)
        return results_by_band

    # FE column: date (frozen per RUL-12)
    df_valid["_fe"] = df_valid["date"].astype(str)
    sector_col_eff = sector_col if (sector_col in df_valid.columns and
                                    df_valid[sector_col].notna().any()) else None

    for band in range(N_BANDS):
        stratum_col = f"band_{band}"
        df_valid[stratum_col] = (df_valid["lq_band"] == band).astype(int)

        n_treatment = int((df_valid[stratum_col] == 1).sum())
        n_control = int((df_valid[stratum_col] == 0).sum())

        if n_treatment < 10:
            log.warning(
                "run_band_analysis: band=%d proxy=%s panel=%s: only %d treatment fires, skipping",
                band, proxy, panel, n_treatment,
            )
            results_by_band[band] = {
                "n_treatment": n_treatment,
                "n_control": n_control,
                "effects": [],
                "era_table": None,
                "era_sign_stable": None,
                "nc2_marginality": None,
                "affected_volume_pct": n_treatment / max(n_gradable_total, 1),
                "skipped": True,
            }
            continue

        effects = []
        for outcome in OUTCOME_COLS:
            if outcome not in df_valid.columns:
                continue
            if df_valid[outcome].notna().sum() < 10:
                continue

            res = fast_r1_estimate(
                df_valid,
                outcome_col=outcome,
                stratum_col=stratum_col,
                fe_col="_fe",
                sector_col=sector_col_eff,
                n_bootstrap=n_bootstrap,
                rng_seed=rng_seed,
            )
            res["panel"] = panel
            res["proxy"] = proxy
            res["band"] = band
            res["form_key"] = f"{proxy}_band{band}_{panel}"
            # recall = fraction of fires in this band out of all valid fires
            res["recall"] = n_treatment / max(len(df_valid), 1)
            effects.append(res)

        # Era table per band — correct fast_era_table signature (L1: per-form, same form)
        era_tbl = None
        era_sign_stable = None
        try:
            era_tbl = fast_era_table(df_valid, stratum_col, panel_label=panel)
        except TypeError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("era_table error band=%d proxy=%s: %s", band, proxy, exc)

        if era_tbl is not None and not era_tbl.empty and "stop5_rate" in era_tbl.columns:
            era_sign_stable = _check_era_sign_stability(era_tbl, stratum_col)

        # NC-2 proximity marginality: run for bands showing improvement on stop5 or fwd_mdd_21.
        # "Improvement" for stop5: coef < 0 (fewer adverse stops).
        # "Improvement" for fwd_mdd_21: coef > 0 (less negative MDD = better).
        nc2_marginality = None
        if closes is not None:
            stop5_fx = [e for e in effects if e.get("outcome") == "stop5"]
            mdd21_fx = [e for e in effects if e.get("outcome") == "fwd_mdd_21"]
            shows_improvement = False
            if stop5_fx and stop5_fx[0].get("ci_hi", 1.0) < 0.0:
                shows_improvement = True  # stop5 CI_hi < 0 = significantly fewer stops
            if mdd21_fx and mdd21_fx[0].get("ci_lo", -1.0) > 0.0:
                shows_improvement = True  # fwd_mdd_21 CI_lo > 0 = less negative (better MDD)

            if shows_improvement:
                log.info(
                    "Band %d proxy=%s shows improvement — running NC-2 proximity FE",
                    band, proxy,
                )
                nc2_marginality = _run_nc2_band_fe(
                    df_valid, stratum_col, closes,
                    n_bootstrap, rng_seed, panel, sector_col_eff,
                )

        # Affected volume percentage: fraction of all gradable fires in this band
        # Uses n_gradable_total (computed once above) for consistency across both branches.
        affected_volume_pct = n_treatment / max(n_gradable_total, 1)

        results_by_band[band] = {
            "n_treatment": n_treatment,
            "n_control": n_control,
            "effects": effects,
            "era_table": era_tbl,
            "era_sign_stable": era_sign_stable,
            "nc2_marginality": nc2_marginality,
            "affected_volume_pct": affected_volume_pct,
            "skipped": False,
        }

    return results_by_band


def _check_era_sign_stability(
    era_tbl: pd.DataFrame,
    stratum_col: str,
) -> bool | None:
    """Check whether stop5 coefficient is sign-stable in >=3/4 program eras.

    Same logic as run_w2_sur._check_era_sign_stability — per-form, on same form's data.
    """
    program_eras = ["2012-2015", "2016-2019", "2020-2022", "2023-2026"]
    if "era" not in era_tbl.columns or "stop5_rate" not in era_tbl.columns:
        return None

    era_signs: list[int] = []
    for era in program_eras:
        sub = era_tbl[era_tbl["era"] == era]
        if stratum_col not in sub.columns:
            continue
        treat = sub[sub[stratum_col] == 1]["stop5_rate"]
        ctrl  = sub[sub[stratum_col] == 0]["stop5_rate"]
        if treat.empty or ctrl.empty:
            continue
        diff = float(treat.mean()) - float(ctrl.mean())
        era_signs.append(1 if diff > 0 else -1)

    if len(era_signs) < 2:
        return None
    pos_count = sum(1 for s in era_signs if s > 0)
    neg_count = sum(1 for s in era_signs if s < 0)
    return max(pos_count, neg_count) >= 3


# ---------------------------------------------------------------------------
# Hygiene bar evaluation (per masterplan §5)
# ---------------------------------------------------------------------------

def evaluate_hygiene_bar(
    band_results: dict[int, dict[str, Any]],
    proxy: str,
    panel: str,
) -> dict[str, Any]:
    """Evaluate the two-clause hygiene bar for the WORST band (band 0).

    Clause A: CI-excluding-0 degradation on stop5 OR fwd_mdd_21 for the worst band.
      Degradation on stop5: CI_lo > 0 (more stops, CI entirely positive).
      Degradation on fwd_mdd_21: CI_hi < 0 (more negative MDD, CI entirely below zero).
    Clause B: Affected volume <= 10% of fires.

    Returns dict with per-clause verdicts and combined HYGIENE_BAR_MET bool.
    No adjudication — report only.
    """
    worst_band = 0  # band 0 = least liquid = worst

    if worst_band not in band_results or band_results[worst_band].get("skipped"):
        return {
            "proxy": proxy,
            "panel": panel,
            "worst_band": worst_band,
            "clause_a_stop5_degradation": None,
            "clause_a_mdd21_degradation": None,
            "clause_a_met": None,
            "clause_b_affected_volume_pct": None,
            "clause_b_met": None,
            "hygiene_bar_met": None,
            "note": "Worst band skipped (insufficient fires).",
        }

    band_res = band_results[worst_band]
    effects = band_res.get("effects", [])
    affected_vol = band_res.get("affected_volume_pct")

    # Clause A: degradation on stop5 or fwd_mdd_21
    stop5_fx = [e for e in effects if e.get("outcome") == "stop5"]
    mdd21_fx = [e for e in effects if e.get("outcome") == "fwd_mdd_21"]

    stop5_degradation = None
    mdd21_degradation = None

    if stop5_fx:
        ci_lo = stop5_fx[0].get("ci_lo")
        ci_hi = stop5_fx[0].get("ci_hi")
        if ci_lo is not None and ci_hi is not None:
            # Degradation = CI_lo > 0 (significantly MORE stops)
            stop5_degradation = bool(ci_lo > 0.0)

    if mdd21_fx:
        ci_lo = mdd21_fx[0].get("ci_lo")
        ci_hi = mdd21_fx[0].get("ci_hi")
        if ci_lo is not None and ci_hi is not None:
            # fwd_mdd_21 <=0; more negative = worse.
            # Coef for worst band: negative means MORE adverse (worse MDD).
            # Degradation = CI_hi < 0 (significantly more-negative MDD)
            mdd21_degradation = bool(ci_hi < 0.0)

    clause_a_met = bool(stop5_degradation) or bool(mdd21_degradation)

    # Clause B: affected volume <= 10%
    clause_b_met = None
    if affected_vol is not None:
        clause_b_met = bool(affected_vol <= HYGIENE_VOLUME_THRESHOLD)

    hygiene_bar_met = bool(clause_a_met) and (clause_b_met is True)

    return {
        "proxy": proxy,
        "panel": panel,
        "worst_band": worst_band,
        "worst_band_n": band_res.get("n_treatment"),
        "clause_a_stop5_degradation": stop5_degradation,
        "clause_a_mdd21_degradation": mdd21_degradation,
        "clause_a_met": clause_a_met,
        "clause_b_affected_volume_pct": affected_vol,
        "clause_b_met": clause_b_met,
        "hygiene_bar_met": hygiene_bar_met,
        "stop5_coef": stop5_fx[0].get("coef") if stop5_fx else None,
        "stop5_ci_lo": stop5_fx[0].get("ci_lo") if stop5_fx else None,
        "stop5_ci_hi": stop5_fx[0].get("ci_hi") if stop5_fx else None,
        "mdd21_coef": mdd21_fx[0].get("coef") if mdd21_fx else None,
        "mdd21_ci_lo": mdd21_fx[0].get("ci_lo") if mdd21_fx else None,
        "mdd21_ci_hi": mdd21_fx[0].get("ci_hi") if mdd21_fx else None,
    }


# ---------------------------------------------------------------------------
# Family-wide BH correction (per L1: reuse from run_w2_sur)
# Scope: all proxy x band x outcome cells, excluding stop_vol_21, days_to_10
# ---------------------------------------------------------------------------

def apply_slq_family_bh(
    all_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply one BH pass pooling all proxy x band x outcome cells of esx_lq_bands.

    Excludes stop_vol_21 (mirror of zone_held_21) and days_to_10 (collider).
    Mutates each effect dict in-place. Returns the input list.
    """
    pool_effects = [e for e in all_effects
                    if e.get("outcome") not in ("stop_vol_21", "days_to_10")]

    p_values = [e.get("p_value") for e in pool_effects]
    labels = [f"{e.get('form_key','?')}_{e.get('outcome','?')}" for e in pool_effects]

    bh_results = bh_correction(p_values, labels, BH_Q_THRESHOLD)
    bh_map = {r["label"]: r for r in bh_results}

    for e in pool_effects:
        label = f"{e.get('form_key','?')}_{e.get('outcome','?')}"
        bh = bh_map.get(label, {})
        e["bh_q_family"] = bh.get("q_value")
        e["bh_rejected_family"] = bh.get("rejected")

    for e in all_effects:
        if e.get("outcome") in ("stop_vol_21", "days_to_10"):
            e["bh_q_family"] = None
            e["bh_rejected_family"] = None
            e["bh_excluded_from_pool"] = True

    return all_effects


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(
    lines: list[str],
    *,
    panel_results: dict[str, Any],
    all_effects: list[dict[str, Any]],
    hygiene_results: list[dict[str, Any]],
    nc_yardstick_rows: list[dict[str, str]],
    n_bootstrap: int,
    smoke: bool,
) -> None:
    """Write all report sections to the lines buffer."""

    # --- Survivor stamp ---
    lines.append("**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names "
                 "only. Comparisons within-era are directionally valid.")
    lines.append("")

    # --- NC Yardstick (RUL-3 mandatory preamble) ---
    lines.append("## NC Yardstick (RUL-3 mandatory preamble)")
    lines.append("")
    lines.append("**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).")
    lines.append("Numbers below are parsed from that file at runtime — NOT hardcoded.")
    lines.append("Per masterplan §10 RUL-3: null-competitors appear as the first table.")
    lines.append("Direction note: stop5 is ADVERSE — a BETTER signal has a MORE NEGATIVE "
                 "coefficient. Degradation (hygiene bar) = CI_lo > 0 (significantly more stops).")
    lines.append("")
    if nc_yardstick_rows:
        lines.append("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |")
        lines.append("|---|---|---|---|---|---|")
        for row in nc_yardstick_rows:
            lines.append(
                f"| {row.get('panel','')} | {row.get('nc','')} | {row.get('coef','')} "
                f"| {row.get('ci','')} | {row.get('excl0','')} | {row.get('recall','')} |"
            )
    else:
        lines.append("*NC yardstick not available (W1_NC_REPORT.md not found or unparseable).*")
    lines.append("")

    # --- Per-panel results ---
    for panel, panel_data in panel_results.items():
        lines.append(f"## Panel: {panel}")
        lines.append("")
        lines.append(f"**Total fires loaded:** {panel_data.get('n_fires_total', 'N/A')}")
        lines.append(f"**Gradable fires:** {panel_data.get('n_gradable', 'N/A')}")
        lines.append(f"**FE granularity:** `date` (frozen per RUL-12)")
        lines.append("")

        for proxy in PROXIES:
            proxy_data = panel_data.get("proxies", {}).get(proxy, {})
            if not proxy_data:
                lines.append(f"### Proxy: {proxy}")
                lines.append("")
                lines.append(f"*{proxy} not available for panel {panel}.*")
                lines.append("")
                continue

            n_with_band = proxy_data.get("n_with_band", 0)
            n_total = panel_data.get("n_gradable", 1)

            lines.append(f"### Proxy: {proxy}")
            lines.append("")
            lines.append(f"**Fires with computable band:** {n_with_band} of {n_total} "
                         f"({100*n_with_band/max(n_total,1):.1f}%)")
            lines.append("")

            # Band distribution table
            band_results = proxy_data.get("band_results", {})
            lines.append("#### Band Distribution")
            lines.append("")
            lines.append("| Band | Label | N fires | % of total |")
            lines.append("|---|---|---|---|")
            for b in range(N_BANDS):
                br = band_results.get(b, {})
                n_b = br.get("n_treatment", 0)
                pct = 100 * n_b / max(n_total, 1)
                lines.append(f"| {b} | {BAND_LABELS[b]} | {n_b} | {pct:.1f}% |")
            lines.append("")

            # Per-band effect tables
            for b in range(N_BANDS):
                br = band_results.get(b, {})
                if br.get("skipped"):
                    lines.append(f"#### Band {b} — {BAND_LABELS[b]} (SKIPPED: insufficient fires)")
                    lines.append("")
                    continue

                lines.append(f"#### Band {b} — {BAND_LABELS[b]}")
                lines.append("")
                lines.append(f"N treatment: {br.get('n_treatment','N/A')} | "
                              f"N control: {br.get('n_control','N/A')} | "
                              f"Affected volume: {100*br.get('affected_volume_pct',0):.1f}% of fires")
                lines.append("")

                effects = br.get("effects", [])
                if effects:
                    # Effect table header
                    lines.append("| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |")
                    lines.append("|---|---|---|---|---|---|")
                    for e in effects:
                        outcome = e.get("outcome", "")
                        coef = e.get("coef")
                        ci_lo = e.get("ci_lo")
                        ci_hi = e.get("ci_hi")
                        p = e.get("p_value")
                        bh_q = e.get("bh_q_family")
                        bh_rej = e.get("bh_rejected_family")
                        excluded = e.get("bh_excluded_from_pool", False)

                        coef_s = _fmt_f(coef, 4)
                        ci_s = f"[{_fmt_f(ci_lo, 4)}, {_fmt_f(ci_hi, 4)}]"
                        excl = _excl_zero(e)
                        if excl == "YES *":
                            ci_s += " *"
                        p_s = f"{p:.4f}" if p is not None else "N/A"
                        bh_q_s = f"{bh_q:.4f}" if bh_q is not None else ("excl" if excluded else "N/A")
                        bh_rej_s = ("YES" if bh_rej else "no") if bh_rej is not None else ("excl" if excluded else "N/A")
                        lines.append(
                            f"| {outcome} | {coef_s} | {ci_s} | {p_s} | {bh_q_s} | {bh_rej_s} |"
                        )
                    lines.append("")

                    # Deterioration sign breakdown
                    det_dist = proxy_data.get("det_sign_dist", {})
                    if det_dist:
                        lines.append("**Deterioration sign distribution (band 0 fires):**")
                        lines.append("")
                        lines.append("| Deterioration sign | N fires |")
                        lines.append("|---|---|")
                        for sign, n_s in det_dist.items():
                            label = {1: "+1 (deteriorating)", -1: "-1 (improving)", 0: "0 (flat)"}.get(sign, str(sign))
                            lines.append(f"| {label} | {n_s} |")
                        lines.append("")
                else:
                    lines.append("*No effects computed.*")
                    lines.append("")

                # Era table
                era_tbl = br.get("era_table")
                if era_tbl is not None and not era_tbl.empty:
                    lines.append(f"**Era table (band {b} vs rest):**")
                    lines.append("")
                    stratum_col = f"band_{b}"
                    # Summarize era table: stop5 rate per era × stratum
                    # mae63_mean = 63d MAE context (per RUL-13, NOT a verdict metric —
                    # 63d+ NEVER decides an entry verdict; shown here for holdability context only).
                    lines.append("| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |")
                    lines.append("|---|---|---|---|---|")
                    for _, erow in era_tbl.iterrows():
                        strat = int(erow.get(stratum_col, -1)) if stratum_col in erow else "all"
                        era_label = erow.get("era", "?")
                        n_fires = int(erow.get("n_fires", 0))
                        s5 = erow.get("stop5_rate")
                        m63 = erow.get("mae63_mean")  # fast_era_table emits mae63_mean only (63d MAE)
                        lines.append(
                            f"| {era_label} | {strat} | {n_fires} | "
                            f"{_fmt_pct(s5)} | {_fmt_f(m63, 4)} |"
                        )
                    lines.append("")
                    era_stable = br.get("era_sign_stable")
                    lines.append(f"**Era sign-stability (stop5, >=3/4 eras):** "
                                 f"{'YES' if era_stable else ('NO' if era_stable is False else 'N/A')}")
                    lines.append("")

                # NC-2 marginality (if computed)
                nc2 = br.get("nc2_marginality")
                if nc2 is not None:
                    lines.append(f"**NC-2 proximity marginality test (band {b}):**")
                    lines.append("")
                    if nc2.get("band_computed"):
                        coef = nc2.get("coef")
                        ci_lo = nc2.get("ci_lo")
                        ci_hi = nc2.get("ci_hi")
                        excl = nc2.get("ci_excl_zero", False)
                        lines.append(
                            f"stop5 after NC-2 band FE: coef={_fmt_f(coef,4)} "
                            f"CI=[{_fmt_f(ci_lo,4)}, {_fmt_f(ci_hi,4)}] "
                            f"CI_excl_0={'YES' if excl else 'no'}"
                        )
                        lines.append(f"Note: {nc2.get('note','')}")
                    else:
                        lines.append(f"Not computed: {nc2.get('note','')}")
                    lines.append("")

    # --- Hygiene bar summary ---
    lines.append("## Hygiene Bar Summary (masterplan §5)")
    lines.append("")
    lines.append("**Pre-registered clauses:**")
    lines.append("- Clause A: CI-excluding-0 degradation on stop5 (CI_lo > 0) OR "
                 "fwd_mdd_21 (CI_hi < 0) for the WORST band (band 0 = least liquid).")
    lines.append("- Clause B: Affected volume of worst band <= 10% of fires "
                 "(hygiene rule that eats recall = gate in disguise).")
    lines.append("- Both clauses must be met for HYGIENE BAR MET.")
    lines.append("")
    lines.append("| Proxy | Panel | Worst band N | Clause A (degradation excl-0)? | "
                 "stop5 CI_lo>0 | fwd_mdd_21 CI_hi<0 | Clause B (vol<=10%)? | "
                 "Affected vol | HYGIENE BAR MET? |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for hr in hygiene_results:
        proxy = hr.get("proxy", "?")
        panel = hr.get("panel", "?")
        wn = hr.get("worst_band_n", "N/A")
        ca = hr.get("clause_a_met")
        s5d = hr.get("clause_a_stop5_degradation")
        m21d = hr.get("clause_a_mdd21_degradation")
        cb = hr.get("clause_b_met")
        vol = hr.get("clause_b_affected_volume_pct")
        hbm = hr.get("hygiene_bar_met")
        ca_s = "YES" if ca else ("NO" if ca is False else "N/A")
        s5d_s = "YES" if s5d else ("NO" if s5d is False else "N/A")
        m21d_s = "YES" if m21d else ("NO" if m21d is False else "N/A")
        cb_s = "YES" if cb else ("NO" if cb is False else "N/A")
        vol_s = f"{100*vol:.1f}%" if vol is not None else "N/A"
        hbm_s = "**MET**" if hbm else ("NOT MET" if hbm is False else "N/A")
        note = hr.get("note", "")
        if note:
            hbm_s += f" ({note})"
        lines.append(
            f"| {proxy} | {panel} | {wn} | {ca_s} | {s5d_s} | {m21d_s} | {cb_s} | {vol_s} | {hbm_s} |"
        )
    lines.append("")

    # --- Overall verdict ---
    lines.append("## Overall Verdict (pre-registered, no adjudication here)")
    lines.append("")
    any_met = any(hr.get("hygiene_bar_met") for hr in hygiene_results)
    if not any_met:
        lines.append(
            "**VERDICT: SHIP NOTHING.** No band cleared the pre-registered hygiene bar "
            "(CI-excluding-0 degradation of the worst band on stop5 OR fwd_mdd_21, "
            "with affected volume <= 10%). The Amihud and Corwin-Schultz primitives "
            "remain available as kernel context (as planned in masterplan §3 F4). "
            "No liquidity tilt is introduced. This is the honest null — printed, not hidden."
        )
    else:
        met_cases = [hr for hr in hygiene_results if hr.get("hygiene_bar_met")]
        lines.append("**HYGIENE BAR MET** for the following proxy/panel combinations:")
        for hr in met_cases:
            lines.append(
                f"- {hr['proxy']} / {hr['panel']}: worst-band stop5 delta "
                f"coef={_fmt_f(hr.get('stop5_coef'), 4)} "
                f"CI=[{_fmt_f(hr.get('stop5_ci_lo'), 4)}, {_fmt_f(hr.get('stop5_ci_hi'), 4)}], "
                f"affected volume={100*hr.get('clause_b_affected_volume_pct',0):.1f}%."
            )
        lines.append("")
        lines.append("**Adjudication of deployment form** (no gate in disguise) belongs "
                     "to the orchestrator, not this study.")
    lines.append("")

    # --- BH correction scope ---
    lines.append("## BH Correction Scope")
    lines.append("")
    lines.append(
        f"Family-wide BH: one BH pass pooling ALL proxy x band x outcome cells of "
        f"{FAMILY_NAME} (budget={FAMILY_BUDGET}).\n"
        "Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and "
        "days_to_10 (collider). BH q <= 0.10."
    )
    pool_size = sum(1 for e in all_effects if e.get("outcome") not in ("stop_vol_21", "days_to_10"))
    bh_rej_count = sum(1 for e in all_effects if e.get("bh_rejected_family"))
    lines.append(f"Pool size: {pool_size} cells. BH-rejected: {bh_rej_count}.")
    lines.append("")

    if smoke:
        lines.append("")
        lines.append("> **SMOKE RUN STAMP**: Bootstrap n=200, first 50 unique fire dates only. "
                     "Numbers are NOT production quality.")
        lines.append("")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

    smoke = args.smoke
    n_bootstrap = 200 if smoke else args.n_bootstrap
    panels = args.panel or ["deep", "baskets"]
    out_path = Path(args.out)

    log.info(
        "S-LQ run started: panels=%s n_bootstrap=%d smoke=%s",
        panels, n_bootstrap, smoke,
    )

    # --- Verify family registration (no duplicate) ---
    if _LEDGER_PATH.exists():
        import json
        with open(_LEDGER_PATH, "r") as f:
            ledger_entries = [json.loads(line) for line in f if line.strip()]
        family_entries = [e for e in ledger_entries
                         if e.get("family") == FAMILY_NAME and e.get("kind") == "declared_budget"]
        if family_entries:
            log.info(
                "Family %s already registered (budget=%s). No duplicate write needed.",
                FAMILY_NAME, family_entries[0].get("n"),
            )
        else:
            log.warning(
                "Family %s NOT found in trial ledger — W0 registration may have been skipped.",
                FAMILY_NAME,
            )
    else:
        log.warning("Trial ledger not found at %s", _LEDGER_PATH)

    # --- Load NC yardstick from W1 artifact (RUL-3, not hardcoded) ---
    nc_report_path = _RESEARCH_DIR / "W1_NC_REPORT.md"
    nc_yardstick_rows = _parse_nc_yardstick_from_report(nc_report_path)
    log.info("NC yardstick: %d rows parsed from W1_NC_REPORT.md", len(nc_yardstick_rows))

    # --- Build sector map ---
    sector_map = _build_sector_map()

    # --- Run per-panel ---
    panel_results: dict[str, Any] = {}
    all_effects: list[dict[str, Any]] = []
    hygiene_results: list[dict[str, Any]] = []

    for panel in panels:
        log.info("=== Processing panel: %s ===", panel)

        # Load fires
        fires_path = _FIRES_DEEP if panel == "deep" else _FIRES_BASKETS
        fires = load_fires(fires_path)
        if fires is None or fires.empty:
            log.warning("No fires found for panel=%s — skipping", panel)
            continue

        # Load OHLCV
        if panel == "deep":
            ohlcv_store = _load_deep_ohlcv()
        elif panel == "baskets":
            ohlcv_store = _load_baskets_ohlcv()
        else:
            log.warning("Unknown panel: %s", panel)
            continue

        # Build closes dict for NC-2 proximity proxy
        closes_dict = {t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns}

        # Grade fires via program harness
        graded = grade_fires(fires, {t: df["close"] for t, df in ohlcv_store.items()
                                     if "close" in df.columns})
        graded = _prepare_binary_outcomes(graded)
        graded["_date_ts"] = pd.to_datetime(graded["date"]).astype(np.int64)
        graded["era"] = graded["date"].apply(_assign_era)
        graded["sector"] = graded["ticker"].map(sector_map)

        n_fires_total = len(fires)
        n_gradable = int(graded["gradable"].fillna(False).sum())
        log.info("Panel %s: %d fires, %d gradable", panel, n_fires_total, n_gradable)

        panel_data: dict[str, Any] = {
            "n_fires_total": n_fires_total,
            "n_gradable": n_gradable,
            "proxies": {},
        }

        for proxy in PROXIES:
            log.info("--- Proxy: %s ---", proxy)

            # Check H/L availability for Corwin-Schultz
            if proxy == PROXY_CS:
                n_hl = sum(
                    1 for df in ohlcv_store.values()
                    if "high" in df.columns and "low" in df.columns
                )
                if n_hl == 0:
                    log.warning("No H/L data for panel=%s — skipping Corwin-Schultz", panel)
                    panel_data["proxies"][proxy] = {"skipped": True, "reason": "No H/L data"}
                    continue

            # Assign bands to gradable fires
            gradable_fires = graded[graded["gradable"].fillna(False)].copy()
            if smoke:
                # In smoke mode, limit to a representative cross-section.
                # We sample across dates rather than taking head(N) so each date
                # still has multiple tickers for tercile formation.
                all_dates = sorted(gradable_fires["date"].unique())
                smoke_dates = all_dates[:50]  # first 50 unique dates
                gradable_fires = gradable_fires[gradable_fires["date"].isin(smoke_dates)]
                log.info("SMOKE mode: processing %d gradable fires across %d dates",
                         len(gradable_fires), len(smoke_dates))

            fires_for_bands = pd.DataFrame({
                "ticker": gradable_fires["ticker"],
                "date": gradable_fires["date"],
            })

            graded_with_bands = assign_lq_bands(
                fires_for_bands,
                ohlcv_store,
                proxy,
                trailing_bars=TRAILING_YEAR_BARS,
            )

            # Merge band assignments back to graded
            merge_cols = ["ticker", "date", "lq_proxy_val", "lq_band", "lq_det_sign"]
            graded_banded = gradable_fires.merge(
                graded_with_bands[merge_cols], on=["ticker", "date"], how="left"
            )

            n_with_band = int(graded_banded["lq_band"].notna().sum())
            log.info(
                "Panel=%s proxy=%s: %d/%d gradable fires have computable band",
                panel, proxy, n_with_band, n_gradable,
            )

            # Compute deterioration sign distribution for band 0 (worst)
            band0_mask = graded_banded["lq_band"] == 0
            det_dist: dict[int | None, int] = {}
            if band0_mask.any():
                det_series = graded_banded.loc[band0_mask, "lq_det_sign"]
                for sign_val, cnt in det_series.value_counts(dropna=False).items():
                    key = int(sign_val) if pd.notna(sign_val) else None
                    det_dist[key] = int(cnt)

            # Run band analysis
            band_results = run_band_analysis(
                graded_banded,
                proxy=proxy,
                panel=panel,
                sector_col="sector",
                n_bootstrap=n_bootstrap,
                rng_seed=RNG_SEED,
                closes=closes_dict,
            )

            # Collect all effects for family-wide BH
            for band, br in band_results.items():
                for e in br.get("effects", []):
                    e["proxy"] = proxy
                    e["band"] = band
                    e["panel"] = panel
                    all_effects.append(e)

            # Hygiene bar
            hr = evaluate_hygiene_bar(band_results, proxy, panel)
            hygiene_results.append(hr)

            panel_data["proxies"][proxy] = {
                "n_with_band": n_with_band,
                "band_results": band_results,
                "det_sign_dist": det_dist,
            }

        panel_results[panel] = panel_data

    # --- Family-wide BH correction (L1 reuse: apply_slq_family_bh) ---
    log.info("Applying family-wide BH correction over %d effects", len(all_effects))
    apply_slq_family_bh(all_effects)

    # --- Write report ---
    lines: list[str] = []
    lines.append("# W2 S-LQ Liquidity Hygiene Band Study — Entry-Stack Expansion")
    lines.append("")
    lines.append("**Status:** W2 study report only — no promotion decision (RUL-3).")
    lines.append(f"**Date:** 2026-07-05")
    lines.append("**Family:** esx_lq_bands (budget=12 — pre-registered at W0).")
    lines.append("")
    lines.append("## Study Design")
    lines.append("")
    lines.append("**Lane:** S-LQ (§3 F4). HYGIENE STUDY.")
    lines.append("**Horizon doctrine (RUL-13):** 21d primaries. 63d+ NOT used for entry verdicts.")
    lines.append("")
    lines.append("**Proxies:**")
    lines.append("- Amihud ILLIQ: |ret| / (close × volume), smoothed 20d rolling mean (all panels).")
    lines.append("- Corwin-Schultz HL-spread: two-day HL estimator (panels with H/L).")
    lines.append("")
    lines.append("**Band rule (FIXED, NEVER FITTED):** Cross-sectional terciles on trailing "
                 "252-bar (1-year) proxy values at each fire date.")
    lines.append("- Band 0 = top third of proxy values = worst liquidity (least liquid / widest spread).")
    lines.append("- Band 1 = middle third.")
    lines.append("- Band 2 = bottom third of proxy values = best liquidity.")
    lines.append("")
    lines.append("**Deterioration metric (fixed window = 20 bars):** Sign of 20d slope of proxy "
                 "series at fire date. +1 = deteriorating (proxy rising), -1 = improving.")
    lines.append("")
    lines.append("**Adjacency (R2 per RUL-2):** None. Census: zero EOD spread proxies repo-wide "
                 "prior to W0 (masterplan §3 F4). No falsified relative.")
    lines.append("")
    lines.append("**Hygiene bar (§5 pre-registered):**")
    lines.append("- Clause A: CI-excluding-0 degradation on stop5 (CI_lo > 0) OR fwd_mdd_21 "
                 "(CI_hi < 0) for the worst band (band 0).")
    lines.append("- Clause B: Affected volume of worst band <= 10% of fires.")
    lines.append("")
    lines.append("**Sign convention:**")
    lines.append("- stop5 is ADVERSE. CI_lo > 0 means significantly MORE stops (degradation).")
    lines.append("- fwd_mdd_21 values are <=0. CI_hi < 0 means more-negative MDD (degradation).")
    lines.append("- zone_held_21 is BENEFICIAL. CI_lo > 0 means better zone-holding (improvement).")
    lines.append("")

    _write_report(
        lines,
        panel_results=panel_results,
        all_effects=all_effects,
        hygiene_results=hygiene_results,
        nc_yardstick_rows=nc_yardstick_rows,
        n_bootstrap=n_bootstrap,
        smoke=smoke,
    )

    # Headline numbers for orchestrator
    lines.append("## Headline Numbers (orchestrator summary)")
    lines.append("")
    lines.append("**Worst-band deltas and affected-volume percentages:**")
    lines.append("")
    lines.append("| Proxy | Panel | Band 0 stop5 coef | Band 0 stop5 CI | "
                 "Band 0 fwd_mdd_21 coef | Band 0 fwd_mdd_21 CI | "
                 "Affected vol | Hygiene bar met? |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for hr in hygiene_results:
        proxy = hr.get("proxy", "?")
        panel = hr.get("panel", "?")
        s5c = _fmt_f(hr.get("stop5_coef"), 4)
        s5ci = f"[{_fmt_f(hr.get('stop5_ci_lo'), 4)}, {_fmt_f(hr.get('stop5_ci_hi'), 4)}]"
        m21c = _fmt_f(hr.get("mdd21_coef"), 4)
        m21ci = f"[{_fmt_f(hr.get('mdd21_ci_lo'), 4)}, {_fmt_f(hr.get('mdd21_ci_hi'), 4)}]"
        vol_s = f"{100*hr.get('clause_b_affected_volume_pct', 0):.1f}%" if hr.get("clause_b_affected_volume_pct") is not None else "N/A"
        hbm = "**MET**" if hr.get("hygiene_bar_met") else ("NOT MET" if hr.get("hygiene_bar_met") is False else "N/A")
        note = hr.get("note", "")
        if note:
            hbm += f" ({note})"
        lines.append(f"| {proxy} | {panel} | {s5c} | {s5ci} | {m21c} | {m21ci} | {vol_s} | {hbm} |")
    lines.append("")
    lines.append("*Generated by `scripts/research/run_w2_slq.py`*")
    lines.append("*Grader: engine/grading.py (program barriers, RUL-9).*")
    lines.append("*'validated' word deliberately absent (CI-enforced).*")
    lines.append("*No promotion language. Hygiene study only.*")

    # --- Write to file ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines) + "\n"
    out_path.write_text(report_text, encoding="utf-8")
    log.info("Report written to %s", out_path)

    # --- Console summary ---
    print(f"\n{'='*60}")
    print("S-LQ HYGIENE BAR SUMMARY")
    print(f"{'='*60}")
    for hr in hygiene_results:
        met = hr.get("hygiene_bar_met")
        vol_pct = hr.get("clause_b_affected_volume_pct")
        vol_str = f"{100*vol_pct:.1f}%" if vol_pct is not None else "N/A"
        ca = hr.get("clause_a_met")
        cb = hr.get("clause_b_met")
        print(f"  {hr['proxy']}/{hr['panel']}: "
              f"Clause A={'MET' if ca else ('NOT MET' if ca is False else 'N/A')}, "
              f"Clause B={'MET' if cb else ('NOT MET' if cb is False else 'N/A')}, "
              f"stop5 coef={_fmt_f(hr.get('stop5_coef'),4)}, "
              f"affected vol={vol_str}, "
              f"HYGIENE BAR={'MET' if met else ('NOT MET' if met is False else 'N/A')}")

    if not any(hr.get("hygiene_bar_met") for hr in hygiene_results):
        print("\nVERDICT: SHIP NOTHING. No band cleared the hygiene bar.")
        print("Primitives remain kernel-context only. No liquidity tilt introduced.")
    else:
        print("\nHYGIENE BAR MET for at least one proxy/panel.")
        print("Adjudication of deployment form belongs to the orchestrator.")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Entry-Stack Expansion W2 S-LQ: Liquidity Hygiene Band Study",
    )
    p.add_argument(
        "--smoke", action="store_true",
        help="Run a fast smoke test: first 50 unique fire dates, n_bootstrap=200.",
    )
    p.add_argument(
        "--n-bootstrap", type=int, default=N_BOOTSTRAP,
        help=f"Bootstrap iterations (default {N_BOOTSTRAP}; must be >=1000 for production).",
    )
    p.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Panels to run (default: deep baskets).",
    )
    p.add_argument(
        "--out", default=str(_RESEARCH_DIR / "W2_SLQ_REPORT.md"),
        help="Output report path.",
    )
    return p


if __name__ == "__main__":
    main(_build_parser().parse_args())
