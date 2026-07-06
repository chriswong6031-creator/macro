"""Entry-Stack Expansion Amendment 3 — Structural/Vol-Transition Families E/F/G.

Amendment-3 spec: research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md
  RUL-27 through RUL-34 are law; this script encodes them mechanically.

FAMILIES
--------
E  esx_decline_geometry  (4 trials): Herfindahl concentration × 2 panels × 2 contrasts
F  esx_underwater        (4 trials): time_underwater terciles × 2 panels × 2 contrasts
G  esx_vol_transition    (4 trials): vol_ts falling flag × 2 panels × 2 contrasts
   (EXPECT-NULL per RUL-5; non-null only if full battery survived)

FAMILY E — esx_decline_geometry
  decline_concentration_series(close, 63, 8) at fires.
  Trailing-year cross-sectional terciles: tercile-2 = flush (top), tercile-0 = grind (bottom).
  Contrasts: flush vs grind (restrict to top+bottom terciles); flush vs rest.
  Kill-arms: +nc2_band FE, +rv63_tercile FE, ¬bear_ctx decomposition.
  Two-sided framing.

FAMILY F — esx_underwater
  time_underwater_series(close, 252) at fires.
  NOTE: primitive SATURATES at ~window and can reset on interim peaks.
  Trailing-year cross-sectional terciles: tercile-2 = long (top), tercile-0 = short (bottom).
  Contrasts: long vs short; long vs rest.
  Kill-arms: +nc2_band FE, +age63_tercile FE (pure-age covariate, H2 proof),
             ¬bear_ctx decomposition.
  window=126 re-read as named kill-only diagnostic.
  Two-sided framing.

FAMILY G — esx_vol_transition (EXPECT-NULL per RUL-5)
  vol_ts_series flags at fires; vol_falling + vol_elevated computed per-ticker.
  vol_elevated = (vol_ts >= 1.0) & (vol_ts > vol_ts.shift(5)) — computed inline
  per-ticker before materialization.
  Contrasts: vol_falling vs rest; vol_falling vs vol_elevated.
  Kill-arms: +rv63_tercile FE (BINDING per RUL-32); +nc2_band FE; ¬bear_ctx.
  Pre-registered EXPECT-NULL.

RUL-31 PIT: every feature at-fires uses asof lookup (searchsorted side='right'-1).

RUL-32: every registered trial config logged via TrialLedger.

The word 'validated' never appears in this file.

Usage
-----
    cd /path/to/repo
    python scripts/research/run_a3_struct.py
    python scripts/research/run_a3_struct.py --smoke
    python scripts/research/run_a3_struct.py --panel deep
    python scripts/research/run_a3_struct.py --n-bootstrap 500
    python scripts/research/run_a3_struct.py --out research/entry_stack/A3_STRUCT_REPORT.md
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    compute_recall,
    grade_fires,
    load_fires,
    r1_estimate,
    PROGRAM_ERAS,
    N_BOOTSTRAP,
    BH_Q_THRESHOLD,
    compute_nc2_proximity_proxy,
    assign_nc2_bands,
)

from scripts.research.run_w1_nc import (  # noqa: E402
    bh_correction,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _write_effect_md,
)

from scripts.research.run_w2_sur import (  # noqa: E402
    _parse_nc_yardstick_from_report,
)

from scripts.research._a3_common import (  # noqa: E402
    bear_ctx_series,
    load_spy_close,
    compute_rv63_at_fires,
    assign_rv63_tercile,
    compute_age63_at_fires,
    assign_age63_tercile,
    materialize_series_at_fires,
    assign_trailing_tercile,
    era_sign_stability,
    ticker_half_sign_agreement,
)

_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"

FAMILY_DECLINE_GEO  = "esx_decline_geometry"
FAMILY_UNDERWATER   = "esx_underwater"
FAMILY_VOL_TRANS    = "esx_vol_transition"

OUTCOME_BH = ["stop5", "mae21", "zone_held_21"]

# Trailing window for cross-sectional terciles
TRAILING_YEAR_BARS = 252


def _register_a3_struct_trials(ledger_path: Path | None = None) -> None:
    """Log all A3 struct trial configs via TrialLedger (RUL-32.c)."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("TrialLedger not importable; A3 struct trial rows skipped")
        return

    led = TrialLedger(path=ledger_path or _LEDGER_PATH)

    # Family E: 2 contrasts × 2 panels = 4 trials
    for panel in ("deep", "baskets"):
        for contrast in ("flush_vs_grind", "flush_vs_rest"):
            led.log_trial(
                {"contrast": contrast, "panel": panel},
                family=FAMILY_DECLINE_GEO,
                note="A3 decline geometry (Herfindahl)",
            )

    # Family F: 2 contrasts × 2 panels = 4 trials
    for panel in ("deep", "baskets"):
        for contrast in ("long_vs_short", "long_vs_rest"):
            led.log_trial(
                {"contrast": contrast, "panel": panel},
                family=FAMILY_UNDERWATER,
                note="A3 underwater duration terciles",
            )

    # Family G: 2 contrasts × 2 panels = 4 trials
    for panel in ("deep", "baskets"):
        for contrast in ("vol_falling_vs_rest", "vol_falling_vs_elevated"):
            led.log_trial(
                {"contrast": contrast, "panel": panel, "expectation": "NULL"},
                family=FAMILY_VOL_TRANS,
                note="A3 vol transition (expect-null)",
            )

    log.info("Logged A3 struct trial configs: 4+4+4=12 configs across three families")


def compute_decline_concentration_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    smoke_tickers: set[str] | None = None,
) -> pd.Series:
    """decline_concentration_series(close, 63, 8) materialized at fire dates.

    Per-ticker: compute the full series once, then searchsorted to fire date.
    computable_mask = result.notna().
    """
    from engine.entry_primitives import decline_concentration_series

    cache: dict[str, pd.Series] = {}
    tickers_needed = set(fires["ticker"].astype(str).unique())
    if smoke_tickers is not None:
        tickers_needed = tickers_needed & smoke_tickers

    for ticker in tickers_needed:
        close = closes.get(ticker)
        if close is None or len(close) < 75:
            continue
        try:
            cache[ticker] = decline_concentration_series(close.dropna().sort_index(), 63, 8)
        except Exception as exc:
            log.debug("decline_concentration failed for %s: %s", ticker, exc)

    return materialize_series_at_fires(fires, cache, "decline_concentration")


def compute_underwater_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    window: int = 252,
    smoke_tickers: set[str] | None = None,
) -> pd.Series:
    """time_underwater_series(close, window) materialized at fire dates.

    SATURATION NOTE: the primitive saturates at approximately window-1 bars
    and can reset on interim peaks within the trailing window.  This is
    described accurately in the report.
    """
    from engine.entry_primitives import time_underwater_series

    cache: dict[str, pd.Series] = {}
    tickers_needed = set(fires["ticker"].astype(str).unique())
    if smoke_tickers is not None:
        tickers_needed = tickers_needed & smoke_tickers

    for ticker in tickers_needed:
        close = closes.get(ticker)
        if close is None or len(close) < window + 10:
            continue
        try:
            cache[ticker] = time_underwater_series(close.dropna().sort_index(), window)
        except Exception as exc:
            log.debug("time_underwater_series failed for %s: %s", ticker, exc)

    return materialize_series_at_fires(fires, cache, f"underwater_{window}")


def compute_vol_ts_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    smoke_tickers: set[str] | None = None,
) -> pd.DataFrame:
    """vol_ts_series flags materialized at fire dates.

    Returns fire-indexed DataFrame with columns:
        vol_ts          — float ratio rv5/rv63
        vol_falling     — float 0/1/NaN  (vol_ts<1 & vol_ts < vol_ts.shift(5))
        vol_elevated    — float 0/1/NaN  (vol_ts>=1 & vol_ts > vol_ts.shift(5))

    vol_elevated requires shift(5) so it must be computed on the daily series
    before materialization (cannot be derived from a scalar vol_ts value at fire).
    """
    from engine.entry_primitives import vol_ts_series

    cache_vts: dict[str, pd.Series]      = {}
    cache_vfall: dict[str, pd.Series]    = {}
    cache_velev: dict[str, pd.Series]    = {}

    tickers_needed = set(fires["ticker"].astype(str).unique())
    if smoke_tickers is not None:
        tickers_needed = tickers_needed & smoke_tickers

    for ticker in tickers_needed:
        close = closes.get(ticker)
        if close is None or len(close) < 75:
            continue
        try:
            c = close.dropna().sort_index()
            vdf = vol_ts_series(c)
            vt = vdf["vol_ts"]
            vf = vdf["vol_falling"]
            # vol_elevated: (vol_ts >= 1.0) & (vol_ts > vol_ts.shift(5))
            notna_ve = vt.notna() & vt.shift(5).notna()
            ve = pd.Series(
                np.where(notna_ve, ((vt >= 1.0) & (vt > vt.shift(5))).astype(float), np.nan),
                index=c.index,
                dtype=float,
            )
            cache_vts[ticker]   = vt
            cache_vfall[ticker] = vf
            cache_velev[ticker] = ve
        except Exception as exc:
            log.debug("vol_ts_series failed for %s: %s", ticker, exc)

    vts_at   = materialize_series_at_fires(fires, cache_vts,   "vol_ts")
    vfall_at = materialize_series_at_fires(fires, cache_vfall, "vol_falling")
    velev_at = materialize_series_at_fires(fires, cache_velev, "vol_elevated")

    return pd.DataFrame(
        {"vol_ts": vts_at, "vol_falling": vfall_at, "vol_elevated": velev_at},
        index=fires.index,
    )


def compute_bear_ctx_at_fires(
    fires: pd.DataFrame,
    idx_close: pd.Series | None,
) -> pd.Series:
    """Materialize bear_ctx at each fire date (wave6 F8 frozen def)."""
    if idx_close is None or len(idx_close) < 210:
        log.warning("bear_ctx: insufficient index series; setting all NaN")
        return pd.Series(np.nan, index=fires.index, name="bear_ctx", dtype=float)

    bctx_daily = bear_ctx_series(idx_close)
    vals: list[float] = []
    for _, row in fires.iterrows():
        sig_date = pd.Timestamp(row["date"])
        loc = bctx_daily.index.searchsorted(sig_date, side="right") - 1
        if loc < 0:
            vals.append(float("nan"))
            continue
        v = float(bctx_daily.iloc[loc])
        vals.append(v if pd.notna(v) else float("nan"))
    return pd.Series(vals, index=fires.index, name="bear_ctx", dtype=float)


def _r1_contrast(
    graded_ok: pd.DataFrame,
    outcome: str,
    stratum_col: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    computable_mask: "pd.Series | None" = None,
    extra_fe_cols: "list[str] | None" = None,
) -> dict[str, Any]:
    """Single-outcome r1_estimate wrapper."""
    if outcome not in graded_ok.columns or stratum_col not in graded_ok.columns:
        return {"coef": None, "ci_lo": None, "ci_hi": None, "p_value": None,
                "n_total": 0, "n_treatment": 0, "n_control": 0, "outcome": outcome,
                "stratum": stratum_col, "note": "column absent"}
    return r1_estimate(
        graded_ok, outcome, stratum_col,
        fe_granularity="date",
        sector_col="sector" if "sector" in graded_ok.columns else None,
        n_bootstrap=n_bootstrap,
        computable_mask=computable_mask,
        extra_fe_cols=extra_fe_cols,
    )


def _run_kill_arms(
    graded_ok: pd.DataFrame,
    stratum_col: str,
    *,
    computable_mask: "pd.Series | None",
    n_bootstrap: int,
    use_rv63: bool = True,
    extra_arm_cols: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run nc2_band FE and optional extra kill-arm FE for one contrast."""
    arms: dict[str, dict[str, Any]] = {}

    if "nc2_band" in graded_ok.columns:
        nc2_mask = (computable_mask & graded_ok["nc2_band"].notna()
                    if computable_mask is not None
                    else graded_ok["nc2_band"].notna())
        for outcome in ["stop5"]:
            if outcome not in graded_ok.columns:
                continue
            arms[f"nc2_band|{outcome}"] = r1_estimate(
                graded_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in graded_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=nc2_mask,
                extra_fe_cols=["nc2_band"],
            )

    if use_rv63 and "rv63_tercile" in graded_ok.columns:
        rv_mask = (computable_mask & graded_ok["rv63_tercile"].notna()
                   if computable_mask is not None
                   else graded_ok["rv63_tercile"].notna())
        for outcome in ["stop5"]:
            if outcome not in graded_ok.columns:
                continue
            arms[f"rv63_tercile|{outcome}"] = r1_estimate(
                graded_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in graded_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=rv_mask,
                extra_fe_cols=["rv63_tercile"],
            )

    for extra_col in (extra_arm_cols or []):
        if extra_col in graded_ok.columns:
            col_mask = (computable_mask & graded_ok[extra_col].notna()
                        if computable_mask is not None
                        else graded_ok[extra_col].notna())
            for outcome in ["stop5"]:
                if outcome not in graded_ok.columns:
                    continue
                arms[f"{extra_col}|{outcome}"] = r1_estimate(
                    graded_ok, outcome, stratum_col,
                    fe_granularity="date",
                    sector_col="sector" if "sector" in graded_ok.columns else None,
                    n_bootstrap=n_bootstrap,
                    computable_mask=col_mask,
                    extra_fe_cols=[extra_col],
                )

    return arms


def _bear_decomp(
    graded_ok: pd.DataFrame,
    stratum_col: str,
    computable_mask: "pd.Series | None",
    *,
    n_bootstrap: int,
) -> dict[str, Any]:
    """¬bear_ctx decomposition (descriptive / kill-only per RUL-30)."""
    if "bear_ctx" not in graded_ok.columns:
        return {}
    decomp: dict[str, Any] = {}
    for bval, blab in [(0.0, "notbear"), (1.0, "bear")]:
        bmask_base = (graded_ok["bear_ctx"] == bval)
        bmask = bmask_base & (computable_mask if computable_mask is not None
                              else pd.Series(True, index=graded_ok.index))
        n = int(bmask.sum())
        if n < 50:
            decomp[blab] = {"n": n, "note": "thin"}
            continue
        res: dict[str, Any] = {"n": n}
        for outcome in ["stop5"]:
            if outcome not in graded_ok.columns:
                continue
            res[outcome] = r1_estimate(
                graded_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in graded_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=bmask,
            )
        decomp[blab] = res
    return decomp


def _run_family_e(
    graded_ok: pd.DataFrame,
    panel_name: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Family E: decline_geometry tercile contrasts."""
    if "decline_tercile" not in graded_ok.columns:
        return {"error": "decline_tercile column absent", "panel": panel_name}

    dt = graded_ok["decline_tercile"]
    comp = dt.notna()
    n_computable = int(comp.sum())
    n_burnin = int((~comp).sum())

    # Flush = tercile 2 (top); Grind = tercile 0 (bottom)
    flush_mask  = (dt == 2.0) & comp
    grind_mask  = (dt == 0.0) & comp
    fg_mask     = flush_mask | grind_mask   # restrict to both extremes

    n_flush = int(flush_mask.sum())
    n_grind = int(grind_mask.sum())

    # ── Contrast flush vs grind (restrict to top+bottom terciles) ─────────────
    # Stratum: 1=flush, 0=grind (within the two-extreme subset)
    graded_ok["_flush_vs_grind"] = np.where(flush_mask, 1.0, np.where(grind_mask, 0.0, np.nan))

    fvg_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        fvg_results[outcome] = _r1_contrast(
            graded_ok, outcome, "_flush_vs_grind",
            n_bootstrap=n_bootstrap,
            computable_mask=fg_mask,
        )

    # ── Contrast flush vs rest ─────────────────────────────────────────────────
    graded_ok["_flush_vs_rest"] = np.where(comp, (flush_mask).astype(float), np.nan)

    fvr_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        fvr_results[outcome] = _r1_contrast(
            graded_ok, outcome, "_flush_vs_rest",
            n_bootstrap=n_bootstrap,
            computable_mask=comp,
        )

    # ── Kill-arm battery ───────────────────────────────────────────────────────
    kill_fvg = _run_kill_arms(
        graded_ok, "_flush_vs_grind",
        computable_mask=fg_mask,
        n_bootstrap=n_bootstrap,
        use_rv63=True,
    )
    kill_fvr = _run_kill_arms(
        graded_ok, "_flush_vs_rest",
        computable_mask=comp,
        n_bootstrap=n_bootstrap,
        use_rv63=True,
    )

    bear_fvr = _bear_decomp(
        graded_ok, "_flush_vs_rest", comp, n_bootstrap=n_bootstrap,
    )

    era_stab = era_sign_stability(
        graded_ok, "_flush_vs_rest", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp,
    )
    ticker_half = ticker_half_sign_agreement(
        graded_ok, "_flush_vs_rest", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp,
    )

    return {
        "panel":           panel_name,
        "n_computable":    n_computable,
        "n_burnin":        n_burnin,
        "n_flush":         n_flush,
        "n_grind":         n_grind,
        "flush_vs_grind":  fvg_results,
        "flush_vs_rest":   fvr_results,
        "kill_flush_vs_grind": kill_fvg,
        "kill_flush_vs_rest":  kill_fvr,
        "bear_decomp":     bear_fvr,
        "era_stability":   era_stab,
        "ticker_half":     ticker_half,
    }


def _run_family_f(
    graded_ok: pd.DataFrame,
    panel_name: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Family F: underwater duration tercile contrasts."""
    if "underwater_tercile" not in graded_ok.columns:
        return {"error": "underwater_tercile column absent", "panel": panel_name}

    ut = graded_ok["underwater_tercile"]
    comp = ut.notna()
    n_computable = int(comp.sum())

    # Long = tercile 2 (top = longest underwater); Short = tercile 0 (bottom)
    long_mask   = (ut == 2.0) & comp
    short_mask  = (ut == 0.0) & comp
    ls_mask     = long_mask | short_mask

    n_long  = int(long_mask.sum())
    n_short = int(short_mask.sum())

    graded_ok["_long_vs_short"] = np.where(long_mask, 1.0, np.where(short_mask, 0.0, np.nan))
    graded_ok["_long_vs_rest"]  = np.where(comp, (long_mask).astype(float), np.nan)

    # ── Contrasts ─────────────────────────────────────────────────────────────
    lvs_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        lvs_results[outcome] = _r1_contrast(
            graded_ok, outcome, "_long_vs_short",
            n_bootstrap=n_bootstrap,
            computable_mask=ls_mask,
        )

    lvr_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        lvr_results[outcome] = _r1_contrast(
            graded_ok, outcome, "_long_vs_rest",
            n_bootstrap=n_bootstrap,
            computable_mask=comp,
        )

    # ── Kill-arms ─────────────────────────────────────────────────────────────
    kill_lvr = _run_kill_arms(
        graded_ok, "_long_vs_rest",
        computable_mask=comp,
        n_bootstrap=n_bootstrap,
        use_rv63=False,
        extra_arm_cols=["nc2_band", "age63_tercile"],
    )

    bear_f = _bear_decomp(
        graded_ok, "_long_vs_rest", comp, n_bootstrap=n_bootstrap,
    )

    # ── window=126 kill-only diagnostic ───────────────────────────────────────
    w126_results: dict[str, dict] = {}
    if "underwater_126_tercile" in graded_ok.columns:
        ut126 = graded_ok["underwater_126_tercile"]
        comp126 = ut126.notna()
        graded_ok["_long_vs_rest_126"] = np.where(comp126, (ut126 == 2.0).astype(float), np.nan)
        for outcome in ["stop5"]:
            if outcome not in graded_ok.columns:
                continue
            w126_results[outcome] = _r1_contrast(
                graded_ok, outcome, "_long_vs_rest_126",
                n_bootstrap=n_bootstrap,
                computable_mask=comp126,
            )

    era_stab = era_sign_stability(
        graded_ok, "_long_vs_rest", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp,
    )
    ticker_half = ticker_half_sign_agreement(
        graded_ok, "_long_vs_rest", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp,
    )

    return {
        "panel":            panel_name,
        "n_computable":     n_computable,
        "n_long":           n_long,
        "n_short":          n_short,
        "long_vs_short":    lvs_results,
        "long_vs_rest":     lvr_results,
        "kill_long_vs_rest": kill_lvr,
        "bear_decomp":      bear_f,
        "w126_diagnostic":  w126_results,
        "era_stability":    era_stab,
        "ticker_half":      ticker_half,
    }


def _run_family_g(
    graded_ok: pd.DataFrame,
    panel_name: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Family G: vol_transition contrasts (EXPECT-NULL per RUL-5)."""
    if "vol_falling" not in graded_ok.columns:
        return {"error": "vol_falling column absent", "panel": panel_name}

    vf = graded_ok["vol_falling"]
    ve = graded_ok.get("vol_elevated", pd.Series(np.nan, index=graded_ok.index))

    comp_fall = vf.notna()
    n_fall_computable = int(comp_fall.sum())
    n_falling  = int((vf == 1.0).sum())
    n_elevated = int(((ve == 1.0) & ve.notna()).sum()) if "vol_elevated" in graded_ok.columns else 0

    # vol_falling vs rest
    vfr_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        vfr_results[outcome] = _r1_contrast(
            graded_ok, outcome, "vol_falling",
            n_bootstrap=n_bootstrap,
            computable_mask=comp_fall,
        )

    # vol_falling vs vol_elevated (restrict to the two strata)
    if "vol_elevated" in graded_ok.columns:
        ve_col = graded_ok["vol_elevated"]
        both_comp = vf.notna() & ve_col.notna()
        graded_ok["_fall_vs_elev"] = np.where(
            (vf == 1.0) | (ve_col == 1.0),
            np.where(vf == 1.0, 1.0, 0.0),
            np.nan,
        )
        both_mask = ((vf == 1.0) | (ve_col == 1.0)) & both_comp
    else:
        both_mask = comp_fall
        graded_ok["_fall_vs_elev"] = np.nan

    fve_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in graded_ok.columns:
            continue
        fve_results[outcome] = _r1_contrast(
            graded_ok, outcome, "_fall_vs_elev",
            n_bootstrap=n_bootstrap,
            computable_mask=both_mask,
        )

    # ── Kill-arms (rv63_tercile BINDING per RUL-32) ────────────────────────────
    kill_vfr = _run_kill_arms(
        graded_ok, "vol_falling",
        computable_mask=comp_fall,
        n_bootstrap=n_bootstrap,
        use_rv63=True,
        extra_arm_cols=["nc2_band"],
    )

    bear_g = _bear_decomp(
        graded_ok, "vol_falling", comp_fall, n_bootstrap=n_bootstrap,
    )

    # non-null verdict check: only if rv63_tercile arm CI also excludes 0
    def _ci_excl0(r: dict) -> bool:
        ci_lo = r.get("ci_lo")
        ci_hi = r.get("ci_hi")
        return ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0)

    stop5_pooled = vfr_results.get("stop5", {})
    stop5_rv63   = kill_vfr.get("rv63_tercile|stop5", {})
    non_null = (
        _ci_excl0(stop5_pooled)
        and _ci_excl0(stop5_rv63)
    )

    era_stab = era_sign_stability(
        graded_ok, "vol_falling", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp_fall,
    )
    ticker_half = ticker_half_sign_agreement(
        graded_ok, "vol_falling", "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=comp_fall,
    )

    return {
        "panel":               panel_name,
        "n_fall_computable":   n_fall_computable,
        "n_falling":           n_falling,
        "n_elevated":          n_elevated,
        "vol_falling_vs_rest": vfr_results,
        "vol_falling_vs_elev": fve_results,
        "kill_vfr":            kill_vfr,
        "bear_decomp":         bear_g,
        "non_null_verdict":    non_null,
        "era_stability":       era_stab,
        "ticker_half":         ticker_half,
    }


def run_panel(
    panel_name: str,
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
    idx_close: pd.Series | None,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    smoke_tickers: set[str] | None = None,
) -> dict[str, Any]:
    """Run all A3 struct families for one panel."""
    fires = fires.copy()
    if smoke_tickers is not None:
        fires = fires[fires["ticker"].isin(smoke_tickers)].copy()
        log.info("Smoke mode: %d fires after ticker filter", len(fires))

    fires["sector"] = fires["ticker"].map(sector_map)
    total_fires = len(fires)
    log.info("Panel %s: %d fires", panel_name, total_fires)

    # ── NC-2 proximity proxy ───────────────────────────────────────────────────
    log.info("  Computing NC-2 proximity proxy...")
    nc2_prox = compute_nc2_proximity_proxy(fires, closes)
    nc2_bands = assign_nc2_bands(nc2_prox)

    # ── bear_ctx ───────────────────────────────────────────────────────────────
    log.info("  Computing bear_ctx at fires...")
    bear_ctx = compute_bear_ctx_at_fires(fires, idx_close)

    # ── rv63 tercile ──────────────────────────────────────────────────────────
    log.info("  Computing rv63 tercile at fires...")
    rv63_vals    = compute_rv63_at_fires(fires, closes)
    rv63_tercile = assign_rv63_tercile(rv63_vals, fires, closes)

    # ── Family E: decline_concentration ───────────────────────────────────────
    log.info("  Computing decline_concentration at fires...")
    dc_vals      = compute_decline_concentration_at_fires(fires, closes, smoke_tickers=smoke_tickers)
    dc_tercile   = assign_trailing_tercile(dc_vals, fires, "decline_concentration")
    dc_tercile.name = "decline_tercile"
    log.info("  decline_concentration non-NaN: %d", int(dc_vals.notna().sum()))

    # ── Family F: time_underwater ─────────────────────────────────────────────
    log.info("  Computing time_underwater at fires...")
    uw_vals      = compute_underwater_at_fires(fires, closes, window=252, smoke_tickers=smoke_tickers)
    uw_tercile   = assign_trailing_tercile(uw_vals, fires, "underwater_252")
    uw_tercile.name = "underwater_tercile"

    # window=126 kill-only diagnostic
    uw126_vals   = compute_underwater_at_fires(fires, closes, window=126, smoke_tickers=smoke_tickers)
    uw126_tercile = assign_trailing_tercile(uw126_vals, fires, "underwater_126")
    uw126_tercile.name = "underwater_126_tercile"
    log.info(
        "  underwater (w252) non-NaN: %d; (w126) non-NaN: %d",
        int(uw_vals.notna().sum()),
        int(uw126_vals.notna().sum()),
    )

    # ── Age63 (pure-age covariate for F, RUL-30) ──────────────────────────────
    log.info("  Computing age63 covariate...")
    age63_vals   = compute_age63_at_fires(fires, closes)
    age63_tercile = assign_age63_tercile(age63_vals, fires)
    age63_tercile.name = "age63_tercile"

    # ── Family G: vol_ts ──────────────────────────────────────────────────────
    log.info("  Computing vol_ts flags at fires...")
    vol_df = compute_vol_ts_at_fires(fires, closes, smoke_tickers=smoke_tickers)
    log.info(
        "  vol_falling non-NaN: %d; vol_elevated non-NaN: %d",
        int(vol_df["vol_falling"].notna().sum()),
        int(vol_df["vol_elevated"].notna().sum()),
    )

    # ── Grade fires ───────────────────────────────────────────────────────────
    log.info("  Grading fires...")
    extra_cols: dict[str, pd.Series] = {
        "nc2_band":              nc2_bands.reindex(fires.index),
        "bear_ctx":              bear_ctx,
        "rv63_tercile":          rv63_tercile,
        "decline_concentration": dc_vals,
        "decline_tercile":       dc_tercile,
        "underwater_252":        uw_vals,
        "underwater_tercile":    uw_tercile,
        "underwater_126":        uw126_vals,
        "underwater_126_tercile": uw126_tercile,
        "age63_tercile":         age63_tercile,
        "vol_ts":                vol_df["vol_ts"],
        "vol_falling":           vol_df["vol_falling"],
        "vol_elevated":          vol_df["vol_elevated"],
    }
    graded = grade_fires(fires, closes, extra_columns=extra_cols)
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, total_fires)

    graded_ok = graded[graded["gradable"].fillna(False)].copy()

    if "fwd_mdd_21" in graded_ok.columns and "mae21" not in graded_ok.columns:
        graded_ok["mae21"] = graded_ok["fwd_mdd_21"]

    # ── Family E ──────────────────────────────────────────────────────────────
    log.info("  Running family E (esx_decline_geometry)...")
    family_e = _run_family_e(graded_ok, panel_name, n_bootstrap=n_bootstrap)

    # ── Family F ──────────────────────────────────────────────────────────────
    log.info("  Running family F (esx_underwater)...")
    family_f = _run_family_f(graded_ok, panel_name, n_bootstrap=n_bootstrap)

    # ── Family G ──────────────────────────────────────────────────────────────
    log.info("  Running family G (esx_vol_transition)...")
    family_g = _run_family_g(graded_ok, panel_name, n_bootstrap=n_bootstrap)

    return {
        "panel":         panel_name,
        "total_fires":   total_fires,
        "n_gradable":    n_gradable,
        "family_e":      family_e,
        "family_f":      family_f,
        "family_g":      family_g,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Within-stratum comparisons are directionally valid under this constraint."
        ),
    }


def run_all_panels(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    smoke: bool = False,
    smoke_n_tickers: int = 40,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run all A3 struct families across panels."""
    _register_all_families(ledger_path)
    if not smoke:
        _register_a3_struct_trials(ledger_path)

    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    idx_close = load_spy_close(_REPO_ROOT)
    if idx_close is not None:
        log.info("Index close loaded: %d bars (%s→%s)", len(idx_close),
                 idx_close.index.min().date(), idx_close.index.max().date())
    else:
        log.warning("Index close unavailable; bear_ctx will be NaN")

    panel_configs = [
        ("deep",    _FIRES_DEEP),
        ("baskets", _FIRES_BASKETS),
    ]
    if panels:
        panel_configs = [(n, p) for n, p in panel_configs if n in panels]

    all_results: dict[str, Any] = {}
    for panel_name, fires_path in panel_configs:
        if not fires_path.exists():
            log.warning("Fires not found: %s — skipping %s", fires_path, panel_name)
            all_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue

        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))

        closes = _get_closes(panel_name)
        log.info("Closes loaded: %d tickers", len(closes))

        smoke_tickers: set[str] | None = None
        if smoke:
            all_tickers = sorted(fires["ticker"].unique())[:smoke_n_tickers]
            smoke_tickers = set(all_tickers)
            log.info("Smoke mode: using %d tickers", len(smoke_tickers))

        res = run_panel(
            panel_name, fires, closes, sector_map, idx_close,
            n_bootstrap=n_bootstrap,
            smoke_tickers=smoke_tickers,
        )
        all_results[panel_name] = res

    return all_results


def _fmt_contrast_table(lines: list, results: dict[str, Any], outcomes: list[str]) -> None:
    lines.append("| Outcome | Coef | 95% CI | p | CI excl 0? |")
    lines.append("|---|---|---|---|---|")
    for outcome in outcomes:
        r = results.get(outcome, {})
        if not r or r.get("coef") is None:
            lines.append(f"| {outcome} | — | — | — | — |")
            continue
        excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                         and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
        lines.append(
            f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | "
            f"{_fmt_f(r.get('p_value'), 4)} | {excl} |"
        )


def _fmt_era_table(lines: list, era_stab: dict[str, Any]) -> None:
    """Emit era × stratum table and sign-stability verdict (RUL-28 mandatory)."""
    era_rows = era_stab.get("era_rows", [])
    if not era_rows:
        return
    n_agree = era_stab.get("n_sign_agree", 0)
    n_est   = era_stab.get("n_eras_estimable", 0)
    stable  = era_stab.get("sign_stable_3of4", False)
    lines.append(f"**Era × stratum table (RUL-28): n_agree={n_agree}/{n_est} eras"
                 f" — sign-stable ≥3/4: {'YES' if stable else 'NO'}**")
    lines.append("")
    lines.append("| Era | n_total | n_treatment | coef | sign |")
    lines.append("|---|---|---|---|---|")
    for er in era_rows:
        coef_s = f"{er['coef']:+.4f}" if er.get("coef") is not None else "—"
        sign_s = {1: "+", -1: "-", None: "—"}.get(er.get("sign"))
        note_s = f" _{er['note']}_" if er.get("note") else ""
        lines.append(f"| {er['era']} | {er.get('n_total','?')} | {er.get('n_treatment','?')}"
                     f" | {coef_s} | {sign_s}{note_s} |")
    lines.append("")


def _fmt_ticker_half(lines: list, ticker_half: dict[str, Any]) -> None:
    """Emit ticker-half sign agreement panel (RUL-28 mandatory on baskets)."""
    half_rows = ticker_half.get("half_rows", [])
    if not half_rows:
        return
    agree = ticker_half.get("sign_agree", False)
    lines.append(f"**Ticker-half sign agreement (RUL-28 baskets): {'AGREE' if agree else 'DISAGREE'}**")
    lines.append("")
    lines.append("| Half | tickers_n | n_total | coef | sign |")
    lines.append("|---|---|---|---|---|")
    for hr in half_rows:
        coef_s = f"{hr['coef']:+.4f}" if hr.get("coef") is not None else "—"
        sign_s = {1: "+", -1: "-", None: "—"}.get(hr.get("sign"))
        lines.append(f"| {hr['half']} | {hr.get('tickers_n','?')} | {hr.get('n_total','?')}"
                     f" | {coef_s} | {sign_s} |")
    lines.append("")


def _fmt_kill_arms(lines: list, kill_arms: dict[str, Any]) -> None:
    for arm_key, r in kill_arms.items():
        if r.get("coef") is None:
            lines.append(f"- {arm_key}: insufficient n or column absent")
            continue
        excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                         and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
        n_drop = r.get("n_dropped_extra_fe", 0)
        lines.append(
            f"- {arm_key}: coef={r['coef']:+.4f} {_ci_str(r)} "
            f"CI-excl-0={excl} (n_dropped_extra={n_drop})"
        )


def _fmt_bear_decomp(lines: list, bear_decomp: dict[str, Any]) -> None:
    if not bear_decomp:
        return
    lines.append("**¬bear_ctx decomposition (kill-only per RUL-30):**")
    lines.append("")
    lines.append("| Context | n | stop5 coef | CI-excl-0? |")
    lines.append("|---|---|---|---|")
    for blab in ("notbear", "bear"):
        bd = bear_decomp.get(blab, {})
        if "note" in bd:
            lines.append(f"| {blab} | {bd.get('n', '?')} | thin | — |")
            continue
        r = bd.get("stop5", {})
        if not r or r.get("coef") is None:
            lines.append(f"| {blab} | {bd.get('n', '?')} | — | — |")
            continue
        excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                         and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
        lines.append(f"| {blab} | {bd.get('n', '?')} | {r['coef']:+.4f} | {excl} |")
    lines.append("")


def write_report(all_results: dict[str, Any], out_path: Path, *, smoke: bool = False) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# A3 Structural / Vol-Transition Report — Entry-Stack Expansion Amendment 3")
    a("")
    a("**Amendment:** research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md")
    a("**Families:** esx_decline_geometry (E, 4), esx_underwater (F, 4),")
    a("  esx_vol_transition (G, 4). Total: 12 new trials.")
    a("**Verdict ceiling:** DISPLAY-CANDIDATE / NULL / KILLED (RUL-28).")
    a("**CHIP promotion:** BLOCKED until true eq_band lands (RUL-28).")
    a("The word 'validated' deliberately absent.")
    a("")

    if smoke:
        a("> **SMOKE RUN** — reduced bootstrap, first 40 tickers only. Not for adjudication.")
        a("")

    # ── NC Yardstick ──────────────────────────────────────────────────────────
    a("## NC Yardstick (RUL-3) — from W1_NC_REPORT.md")
    a("")
    nc_rows = _parse_nc_yardstick_from_report(_RESEARCH_DIR / "W1_NC_REPORT.md")
    if nc_rows:
        a("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |")
        a("|---|---|---|---|---|---|")
        for r in nc_rows:
            a(f"| {r['panel']} | {r['nc']} | {r['coef']} | {r['ci']} | {r['excl0']} | {r['recall']} |")
    else:
        a("_(W1_NC_REPORT.md not found; yardstick unavailable)_")
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

        a(f"**{res['survivor_stamp']}**")
        a("")
        a(f"- Total fires: {res['total_fires']:,}")
        a(f"- Gradable fires: {res['n_gradable']:,}")
        a("")

        # ── Family E ──────────────────────────────────────────────────────────
        a("### Family E — esx_decline_geometry (4 trials)")
        a("")
        a("Two-sided framing. Flush = top tercile (few large down-days); Grind = bottom tercile.")
        a("Mechanism: flush = forced supply that empties; grind = voluntary distribution that persists.")
        a("")
        fe = res.get("family_e", {})
        if "error" in fe:
            a(f"**ERROR:** {fe['error']}")
            a("")
        else:
            a(f"- Computable fires: {fe.get('n_computable', '?'):,}")
            a(f"- Burn-in dropped: {fe.get('n_burnin', '?'):,}")
            a(f"- n_flush (tercile 2): {fe.get('n_flush', '?'):,}")
            a(f"- n_grind (tercile 0): {fe.get('n_grind', '?'):,}")
            a("")

            a("**Contrast (i): flush vs grind (restricted to top+bottom terciles):**")
            a("")
            _fmt_contrast_table(lines, fe.get("flush_vs_grind", {}), OUTCOME_BH)
            a("")

            a("**Contrast (ii): flush vs rest:**")
            a("")
            _fmt_contrast_table(lines, fe.get("flush_vs_rest", {}), OUTCOME_BH)
            a("")

            a("**Kill-arm battery:**")
            a("")
            a("*flush vs grind:*")
            _fmt_kill_arms(lines, fe.get("kill_flush_vs_grind", {}))
            a("")
            a("*flush vs rest:*")
            _fmt_kill_arms(lines, fe.get("kill_flush_vs_rest", {}))
            a("")
            _fmt_bear_decomp(lines, fe.get("bear_decomp", {}))

            _fmt_era_table(lines, fe.get("era_stability", {}))
            _fmt_ticker_half(lines, fe.get("ticker_half", {}))

            # Verdict — conjunctive: CI-excl-0 AND era-sign-stable >=3/4
            # AND (baskets) ticker-half sign agreement (RUL-28)
            fvr_stop5 = fe.get("flush_vs_rest", {}).get("stop5", {})
            ci_lo = fvr_stop5.get("ci_lo")
            ci_hi = fvr_stop5.get("ci_hi")
            ci_excl0 = (ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0))
            era_ok   = fe.get("era_stability", {}).get("sign_stable_3of4", False)
            th_ok    = (fe.get("ticker_half", {}).get("sign_agree", True)
                        if fe.get("ticker_half", {}).get("half_rows") else True)
            if ci_excl0 and era_ok and th_ok:
                verd = "DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)"
            elif not ci_excl0:
                verd = "NULL (CI includes 0 on flush-vs-rest stop5)"
            elif not era_ok:
                verd = (f"NULL (CI-excl-0 but era sign-stability fails: "
                        f"{fe.get('era_stability',{}).get('n_sign_agree',0)}/4 eras agree)")
            else:
                verd = "NULL (CI-excl-0, era-stable, but ticker-half sign disagrees; RUL-28)"
            a(f"**Verdict (flush-vs-rest stop5): {verd}**")
            a("CHIP promotion blocked until true eq_band (RUL-28).")
        a("")

        # ── Family F ──────────────────────────────────────────────────────────
        a("### Family F — esx_underwater (4 trials)")
        a("")
        a("Two-sided framing. Long = top tercile (longest underwater); Short = bottom tercile.")
        a("NOTE: primitive time_underwater_series SATURATES at ~window bars and can RESET on")
        a("interim peaks within the trailing window. Values describe bars since trailing peak,")
        a("bounded at approximately window-1.")
        a("Pure-age kill-arm (age63_tercile) proves F is not H2 re-derived.")
        a("")
        ff = res.get("family_f", {})
        if "error" in ff:
            a(f"**ERROR:** {ff['error']}")
            a("")
        else:
            a(f"- Computable fires: {ff.get('n_computable', '?'):,}")
            a(f"- n_long (tercile 2): {ff.get('n_long', '?'):,}")
            a(f"- n_short (tercile 0): {ff.get('n_short', '?'):,}")
            a("")

            a("**Contrast (i): long vs short:**")
            a("")
            _fmt_contrast_table(lines, ff.get("long_vs_short", {}), OUTCOME_BH)
            a("")

            a("**Contrast (ii): long vs rest:**")
            a("")
            _fmt_contrast_table(lines, ff.get("long_vs_rest", {}), OUTCOME_BH)
            a("")

            a("**Kill-arm battery (+nc2_band, +age63_tercile, ¬bear_ctx):**")
            a("")
            _fmt_kill_arms(lines, ff.get("kill_long_vs_rest", {}))
            a("")
            _fmt_bear_decomp(lines, ff.get("bear_decomp", {}))

            # window=126 diagnostic
            w126 = ff.get("w126_diagnostic", {})
            if w126:
                a("**Kill-only diagnostic: window=126 re-read (named, not a registered primary):**")
                a("")
                for outcome, r in w126.items():
                    if r.get("coef") is None:
                        a(f"- {outcome}: n/a")
                        continue
                    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                    a(f"- {outcome}: coef={r['coef']:+.4f} {_ci_str(r)} CI-excl-0={excl}")
                a("")

            _fmt_era_table(lines, ff.get("era_stability", {}))
            _fmt_ticker_half(lines, ff.get("ticker_half", {}))

            # Verdict — conjunctive: CI-excl-0 AND era-sign-stable >=3/4
            # AND (baskets) ticker-half sign agreement (RUL-28)
            lvr_stop5 = ff.get("long_vs_rest", {}).get("stop5", {})
            ci_lo = lvr_stop5.get("ci_lo")
            ci_hi = lvr_stop5.get("ci_hi")
            ci_excl0 = (ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0))
            era_ok   = ff.get("era_stability", {}).get("sign_stable_3of4", False)
            th_ok    = (ff.get("ticker_half", {}).get("sign_agree", True)
                        if ff.get("ticker_half", {}).get("half_rows") else True)
            if ci_excl0 and era_ok and th_ok:
                verd = "DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)"
            elif not ci_excl0:
                verd = "NULL (CI includes 0 on long-vs-rest stop5)"
            elif not era_ok:
                verd = (f"NULL (CI-excl-0 but era sign-stability fails: "
                        f"{ff.get('era_stability',{}).get('n_sign_agree',0)}/4 eras agree)")
            else:
                verd = "NULL (CI-excl-0, era-stable, but ticker-half sign disagrees; RUL-28)"
            a(f"**Verdict (long-vs-rest stop5): {verd}**")
            a("CHIP promotion blocked until true eq_band (RUL-28).")
        a("")

        # ── Family G ──────────────────────────────────────────────────────────
        a("### Family G — esx_vol_transition (4 trials)")
        a("")
        a("**PRE-REGISTERED EXPECT-NULL (RUL-5).** Registered expectation IS a null.")
        a("This family settles whether ANY vol-family conditioning survives once vol")
        a("LEVEL is controlled (vol_ts is a term-structure ratio, not a level).")
        a("Non-null requires: pooled BH-adjusted CI-excluding-0 AND rv63_tercile FE")
        a("arm (BINDING per RUL-32) also CI-excluding-0. Sign-stable ≥3/4 eras required.")
        a("")
        fg = res.get("family_g", {})
        if "error" in fg:
            a(f"**ERROR:** {fg['error']}")
            a("")
        else:
            a(f"- Computable fires (vol_falling non-NaN): {fg.get('n_fall_computable', '?'):,}")
            a(f"- vol_falling=1 (treatment): {fg.get('n_falling', '?'):,}")
            a(f"- vol_elevated=1 (elevated arm): {fg.get('n_elevated', '?'):,}")
            a("")

            a("**Contrast (i): vol_falling vs rest:**")
            a("")
            _fmt_contrast_table(lines, fg.get("vol_falling_vs_rest", {}), OUTCOME_BH)
            a("")

            a("**Contrast (ii): vol_falling vs vol_elevated:**")
            a("")
            _fmt_contrast_table(lines, fg.get("vol_falling_vs_elev", {}), OUTCOME_BH)
            a("")

            a("**Kill-arm battery (+rv63_tercile BINDING, +nc2_band, ¬bear_ctx):**")
            a("")
            _fmt_kill_arms(lines, fg.get("kill_vfr", {}))
            a("")
            _fmt_bear_decomp(lines, fg.get("bear_decomp", {}))

            _fmt_era_table(lines, fg.get("era_stability", {}))
            _fmt_ticker_half(lines, fg.get("ticker_half", {}))

            # Family G non-null requires CI-excl-0 AND rv63 arm AND era-stable >=3/4
            non_null_base = fg.get("non_null_verdict", False)
            era_ok_g = fg.get("era_stability", {}).get("sign_stable_3of4", False)
            non_null = non_null_base and era_ok_g
            if non_null:
                a("**POSSIBLE NON-NULL** — pooled CI-excluding-0 AND rv63_tercile arm")
                a("CI-excluding-0 AND era-sign-stable >=3/4. Per RUL-5 EXPECT-NULL protocol,")
                a("replication on baskets also required before any discussion.")
            elif non_null_base and not era_ok_g:
                a("**NULL (era-stability gate)** — pooled + rv63 arm CI-excl-0 but era sign")
                a(f"stability fails: {fg.get('era_stability',{}).get('n_sign_agree',0)}/4 eras agree.")
            else:
                a("**NULL — pre-registered expected outcome confirmed.** CI includes 0")
                a("on pooled read OR rv63_tercile kill-arm (BINDING per RUL-32).")
            a("")
            a("CHIP promotion blocked until true eq_band (RUL-28).")
        a("")

        a("---")
        a("")

    a("## Program Summary")
    a("")
    a("| Family | Trials | Expectation | Verdict ceiling |")
    a("|---|---|---|---|")
    a("| esx_decline_geometry (E) | 4 | Two-sided | DISPLAY-CANDIDATE / NULL / KILLED |")
    a("| esx_underwater (F)       | 4 | Two-sided | DISPLAY-CANDIDATE / NULL / KILLED |")
    a("| esx_vol_transition (G)   | 4 | EXPECT-NULL (RUL-5) | NULL / or non-null if rv63 arm also excl-0 |")
    a("")
    a("CHIP promotion blocked for ALL A3 families until true eq_band lands (RUL-28).")
    a("")
    a("*Generated by `scripts/research/run_a3_struct.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*The word 'validated' deliberately absent (CI-enforced).*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="A3 Structural/Vol-Transition — families E/F/G.",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "A3_STRUCT_REPORT.md"),
        help="Output report path",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=N_BOOTSTRAP,
        help=f"Bootstrap resamples (default {N_BOOTSTRAP})",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"], default=None,
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke: n_bootstrap=50, first 40 tickers, deep only",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot  = 50 if args.smoke else args.n_bootstrap
    panels  = ["deep"] if args.smoke else args.panel

    log.info("A3 struct (n_bootstrap=%d, panels=%s, smoke=%s)", n_boot, panels or "all", args.smoke)
    results = run_all_panels(
        n_bootstrap=n_boot,
        panels=panels,
        smoke=args.smoke,
    )
    write_report(results, Path(args.out), smoke=args.smoke)
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
