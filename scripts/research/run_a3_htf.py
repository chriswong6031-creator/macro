"""Entry-Stack Expansion Amendment 3 — HTF Oscillator Motion Families A/B/C/D.

Amendment-3 spec: research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md
  RUL-27 through RUL-34 are law; this script encodes them mechanically.

FAMILIES
--------
A  esx_htf_turn        (12 trials): 3 rungs × 2 panels × 2 reads
B  esx_htf_turn_dose   ( 2 trials): ordinal dose × 2 panels (LOCKED behind A)
C  esx_washout_x_turn  ( 8 trials): 2 forms × 2 panels × 2 contrasts
D  esx_sub_x_turn      ( 2 trials): sub×A1 interaction × 2 panels (LOCKED behind A)

FAMILY A — esx_htf_turn
  Rungs: A1 w_hist_rising, A2 w2_stoch_turn, A3m m_stoch_turn.
  Read-1 (pooled): r1_estimate(stratum=rung).
    For A1 ONLY: extra_fe_cols=['wbull_flag'] per RUL-29.
  Read-2 (notwbull-subset): r1_estimate(stratum=rung, computable_mask=(wbull==0)).
    This is the OPERATIVE read for A1 (RUL-29); robustness read for A2/A3m.
  Kill-arm battery: +nc2_band FE (RUL-30).
  Admission-leg decomposition table: fire counts + stop5/mae21 means by wbull in {0,1}.

FAMILY B — esx_htf_turn_dose
  n_turn_legs = sum(w_hist_rising, w2_stoch_turn, m_stoch_turn) per fire.
  Ordinal coefficient: r1_estimate treating n_turn_legs as numeric stratum.
  Per-level descriptive table: {0,1,2,3} × stop5/mae21 means.
  LOCKED banner: printed only if >=1 A-rung operative read has CI-excluding-0.

FAMILY C — esx_washout_x_turn
  washout_deep = (w2_d_min6 < 25).
  Forms: C1 = deep×A1, C2 = deep×A2.
  Contrasts: (i) within-deep turn-vs-not; (ii) deep&turn vs rest.
  Kill-arms: +nc2_band FE; r1_interaction_estimate marginality; +rv63_tercile FE;
             ¬bear_ctx decomposition.
  Thin-cell law: n_treat < 400 → DESCRIPTIVE stamp.

FAMILY D — esx_sub_x_turn
  sub_deep = (sub == 'deep') as binary 0/1.
  r1_interaction_estimate(stop5, sub_deep, w_hist_rising) per panel.
  LOCKED banner like B.

RUL-31 PIT: every HTF feature uses the last COMPLETED HTF bar whose known-date <=
fire date; computed via engine.entry_primitives.htf_turn_flags per-ticker, then
asof-joined to fire dates.

RUL-32: every registered trial config logged via TrialLedger.

The word 'validated' never appears in this file.

Usage
-----
    cd /path/to/repo
    python scripts/research/run_a3_htf.py
    python scripts/research/run_a3_htf.py --smoke
    python scripts/research/run_a3_htf.py --panel deep
    python scripts/research/run_a3_htf.py --n-bootstrap 500
    python scripts/research/run_a3_htf.py --out research/entry_stack/A3_HTF_REPORT.md
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
    _assign_era,
    _prepare_binary_outcomes,
    compute_recall,
    grade_fires,
    load_fires,
    r1_estimate,
    r1_interaction_estimate,
    PROGRAM_ERAS,
    N_BOOTSTRAP,
    BH_Q_THRESHOLD,
    compute_nc2_proximity_proxy,
    assign_nc2_bands,
)

from scripts.research.run_w1_nc import (  # noqa: E402
    fast_effect_table,
    bh_correction,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
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
    materialize_df_col_at_fires,
    materialize_series_at_fires,
    era_sign_stability,
    ticker_half_sign_agreement,
)

_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"

FAMILY_HTF_TURN      = "esx_htf_turn"
FAMILY_HTF_DOSE      = "esx_htf_turn_dose"
FAMILY_WASHOUT_XTURN = "esx_washout_x_turn"
FAMILY_SUB_XTURN     = "esx_sub_x_turn"

OUTCOME_PRIMARIES = ["stop5", "mae21", "zone_held_21", "stop_vol_21"]
OUTCOME_BH        = ["stop5", "mae21", "zone_held_21"]

WASHOUT_DEEP_THRESHOLD = 25.0   # w2_d_min6 < 25 → washout_deep


def _register_a3_htf_trials(ledger_path: Path | None = None) -> None:
    """Log all A3 HTF trial configs via TrialLedger (RUL-32.c)."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("TrialLedger not importable; A3 HTF trial rows skipped")
        return

    led = TrialLedger(path=ledger_path or _LEDGER_PATH)

    # Family A: 3 rungs × 2 panels × 2 reads = 12 trials
    for rung in ("A1_w_hist_rising", "A2_w2_stoch_turn", "A3m_m_stoch_turn"):
        for panel in ("deep", "baskets"):
            for read in ("pooled", "notwbull_subset"):
                led.log_trial(
                    {"rung": rung, "panel": panel, "read": read},
                    family=FAMILY_HTF_TURN,
                    note="A3 HTF turn flags",
                )

    # Family B: ordinal dose × 2 panels = 2 trials
    for panel in ("deep", "baskets"):
        led.log_trial(
            {"form": "ordinal_n_turn_legs", "panel": panel},
            family=FAMILY_HTF_DOSE,
            note="A3 HTF turn dose (ordinal)",
        )

    # Family C: 2 forms × 2 panels × 2 contrasts = 8 trials
    for form in ("C1_deep_x_A1", "C2_deep_x_A2"):
        for panel in ("deep", "baskets"):
            for contrast in ("within_deep_turn_vs_not", "deep_and_turn_vs_rest"):
                led.log_trial(
                    {"form": form, "panel": panel, "contrast": contrast},
                    family=FAMILY_WASHOUT_XTURN,
                    note="A3 washout x turn",
                )

    # Family D: sub × A1 × 2 panels = 2 trials
    for panel in ("deep", "baskets"):
        led.log_trial(
            {"form": "sub_deep_x_A1", "panel": panel},
            family=FAMILY_SUB_XTURN,
            note="A3 sub x turn interaction",
        )

    log.info(
        "Logged A3 HTF trial configs: 12+2+8+2=24 configs across four families",
    )


def _load_closes_panel(panel: str) -> dict[str, pd.Series]:
    return _get_closes(panel)


def _load_ohlcv_panel(panel: str) -> dict[str, pd.DataFrame]:
    if panel == "deep":
        store = _DATA / "stocks"
    else:
        store = _DATA / "baskets" / "ohlcv"
    result: dict[str, pd.DataFrame] = {}
    for p in sorted(store.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
            if "close" in df.columns:
                result[p.stem] = df.sort_index()
        except Exception:
            pass
    return result


def compute_htf_flags_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    smoke_tickers: set[str] | None = None,
) -> pd.DataFrame:
    """Compute htf_turn_flags per ticker and materialize at fire dates.

    Returns a DataFrame indexed by fires.index with columns:
        w_hist_rising, wbull, w2_stoch_turn, w2_d_min6, m_stoch_turn
    All float 0/1/NaN.

    RUL-31 PIT: htf_turn_flags uses _completed_resample which excludes any
    in-progress bar.  The asof lookup below (searchsorted side='right'-1) finds
    the last daily bar on or before the fire date — this is always a completed
    bar by construction.

    computable_mask = flag.notna() everywhere (burn-in fires drop, printed).
    """
    from engine.entry_primitives import htf_turn_flags

    HTF_COLS = ["w_hist_rising", "wbull", "w2_stoch_turn", "w2_d_min6", "m_stoch_turn"]
    htf_cache: dict[str, pd.DataFrame] = {}

    tickers_needed = set(fires["ticker"].astype(str).unique())
    if smoke_tickers is not None:
        tickers_needed = tickers_needed & smoke_tickers

    for ticker in tickers_needed:
        close = closes.get(ticker)
        if close is None or len(close) < 80:
            continue
        try:
            htf_cache[ticker] = htf_turn_flags(close.dropna().sort_index())
        except Exception as exc:
            log.debug("htf_turn_flags failed for %s: %s", ticker, exc)

    log.info(
        "HTF flags computed for %d / %d tickers",
        len(htf_cache),
        len(tickers_needed),
    )

    result = {col: np.full(len(fires), np.nan) for col in HTF_COLS}
    for i, (_, row) in enumerate(fires.iterrows()):
        ticker = str(row["ticker"])
        if smoke_tickers is not None and ticker not in smoke_tickers:
            continue
        sig_date = pd.Timestamp(row["date"])
        df_htf = htf_cache.get(ticker)
        if df_htf is None:
            continue
        loc = df_htf.index.searchsorted(sig_date, side="right") - 1
        if loc < 0:
            continue
        for col in HTF_COLS:
            if col in df_htf.columns:
                v = float(df_htf[col].iloc[loc])
                result[col][i] = v if pd.notna(v) else np.nan

    return pd.DataFrame(result, index=fires.index, dtype=float)


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


def _r1_for_outcome(
    graded: pd.DataFrame,
    outcome: str,
    stratum_col: str,
    *,
    sector_col: str | None = "sector",
    n_bootstrap: int = N_BOOTSTRAP,
    computable_mask: "pd.Series | None" = None,
    extra_fe_cols: "list[str] | None" = None,
) -> dict[str, Any]:
    """Single-outcome r1_estimate wrapper with standard A3 parameters."""
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()
    if outcome not in df_ok.columns:
        return {"coef": None, "ci_lo": None, "ci_hi": None, "p_value": None,
                "n_total": 0, "n_treatment": 0, "n_control": 0, "outcome": outcome,
                "stratum": stratum_col, "note": "outcome column absent"}
    return r1_estimate(
        df_ok, outcome, stratum_col,
        fe_granularity="date",
        sector_col=sector_col if sector_col in df_ok.columns else None,
        n_bootstrap=n_bootstrap,
        computable_mask=computable_mask,
        extra_fe_cols=extra_fe_cols,
    )


def _run_family_a_rung(
    rung_name: str,
    stratum_col: str,
    graded: pd.DataFrame,
    panel_name: str,
    *,
    wbull_col: str = "wbull_flag",
    a1_pooled_extra_fe: bool = False,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run both reads (pooled + notwbull-subset) for one A-rung.

    For A1 (a1_pooled_extra_fe=True):
        read-1 pooled adds extra_fe_cols=['wbull_flag'] per RUL-29.
    For A2/A3m:
        read-1 pooled has no extra_fe_cols.
    Read-2 (notwbull-subset) is the OPERATIVE read for A1; robustness for A2/A3m.
    """
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()
    if stratum_col not in df_ok.columns:
        return {"error": f"{stratum_col} column absent", "rung": rung_name}

    computable = df_ok[stratum_col].notna()
    n_computable = int(computable.sum())
    n_burnin = int((~computable).sum())

    # ── read-1 pooled ──────────────────────────────────────────────────────────
    extra_fe = [wbull_col] if a1_pooled_extra_fe and wbull_col in df_ok.columns else None
    read1_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in df_ok.columns:
            continue
        read1_results[outcome] = r1_estimate(
            df_ok, outcome, stratum_col,
            fe_granularity="date",
            sector_col="sector" if "sector" in df_ok.columns else None,
            n_bootstrap=n_bootstrap,
            computable_mask=computable,
            extra_fe_cols=extra_fe,
        )

    # ── read-2 notwbull-subset (computable_mask = wbull==0 & stratum notna) ───
    if wbull_col in df_ok.columns:
        notwbull_mask = (df_ok[wbull_col] == 0.0) & computable
    else:
        notwbull_mask = computable
    n_notwbull = int(notwbull_mask.sum())

    read2_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in df_ok.columns:
            continue
        read2_results[outcome] = r1_estimate(
            df_ok, outcome, stratum_col,
            fe_granularity="date",
            sector_col="sector" if "sector" in df_ok.columns else None,
            n_bootstrap=n_bootstrap,
            computable_mask=notwbull_mask if n_notwbull >= 50 else computable,
        )

    # ── kill-arm: +nc2_band FE ─────────────────────────────────────────────────
    nc2_kill: dict[str, dict] = {}
    if "nc2_band" in df_ok.columns:
        for outcome in ["stop5"]:
            if outcome not in df_ok.columns:
                continue
            nc2_kill[outcome] = r1_estimate(
                df_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=computable,
                extra_fe_cols=["nc2_band"],
            )

    # ── admission-leg decomposition ────────────────────────────────────────────
    adm_table: list[dict] = []
    if wbull_col in df_ok.columns and "stop5" in df_ok.columns:
        for wbull_val in [0.0, 1.0]:
            sub = df_ok[(df_ok[wbull_col] == wbull_val) & computable]
            rec: dict[str, Any] = {
                "wbull": int(wbull_val),
                "n_fires": len(sub),
                "stop5_mean": round(float(sub["stop5"].dropna().mean()), 4) if len(sub) > 0 else None,
            }
            if "mae21" in sub.columns:
                rec["mae21_mean"] = round(float(sub["mae21"].dropna().mean()), 4) if len(sub) > 0 else None
            adm_table.append(rec)

    # ── BH within A-rung pool ──────────────────────────────────────────────────
    p_vals = [read2_results.get(o, {}).get("p_value") for o in OUTCOME_BH if o in read2_results]
    labs   = [o for o in OUTCOME_BH if o in read2_results]
    bh     = bh_correction(p_vals, labs)

    # ── Recall (RUL-28: actual compute_recall, not n_treat/n_total proxy) ─────
    recall_info = compute_recall(df_ok, stratum_col) if stratum_col in df_ok.columns else {}

    # ── Era sign-stability (RUL-28 mandatory clause) ───────────────────────────
    era_stab = era_sign_stability(
        df_ok, stratum_col, "stop5",
        n_bootstrap=n_bootstrap,
        computable_mask=notwbull_mask if n_notwbull >= 50 else computable,
    )

    # ── Ticker-half sign agreement (RUL-28 mandatory on baskets) ──────────────
    ticker_half: dict[str, Any] = {}
    if "ticker" in df_ok.columns:
        ticker_half = ticker_half_sign_agreement(
            df_ok, stratum_col, "stop5",
            n_bootstrap=n_bootstrap,
            computable_mask=notwbull_mask if n_notwbull >= 50 else computable,
        )

    return {
        "rung":               rung_name,
        "stratum_col":        stratum_col,
        "panel":              panel_name,
        "n_computable":       n_computable,
        "n_burnin_dropped":   n_burnin,
        "n_notwbull":         n_notwbull,
        "read1_pooled":       read1_results,
        "read2_notwbull":     read2_results,
        "nc2_kill":           nc2_kill,
        "bh_read2":           bh,
        "admission_leg_table": adm_table,
        "recall":             recall_info,
        "era_stability":      era_stab,
        "ticker_half":        ticker_half,
    }


def _run_family_b(
    graded: pd.DataFrame,
    panel_name: str,
    *,
    a_any_ci_excl0: bool,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Ordinal n_turn_legs dose estimator."""
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    rung_cols = ["w_hist_rising", "w2_stoch_turn", "m_stoch_turn"]
    present = [c for c in rung_cols if c in df_ok.columns]
    if not present:
        return {"error": "no rung columns present", "panel": panel_name}

    # Drop rows with any NaN in the rung columns (counts printed)
    mask_any_nan = df_ok[present].isna().any(axis=1)
    n_dropped_nan = int(mask_any_nan.sum())
    df_b = df_ok[~mask_any_nan].copy()
    df_b["n_turn_legs"] = df_b[present].sum(axis=1).astype(float)

    # Per-level descriptive table
    level_table: list[dict] = []
    for lv in [0.0, 1.0, 2.0, 3.0]:
        sub = df_b[df_b["n_turn_legs"] == lv]
        rec: dict[str, Any] = {"n_turn_legs": int(lv), "n_fires": len(sub)}
        for out in ["stop5", "mae21"]:
            if out in sub.columns:
                rec[out + "_mean"] = round(float(sub[out].dropna().mean()), 4) if len(sub) > 0 else None
        level_table.append(rec)

    # Ordinal coefficient: treat n_turn_legs as numeric stratum
    # Use r1_estimate with a numeric stratum column (each unit = one additional leg)
    ordinal_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in df_b.columns:
            continue
        ordinal_results[outcome] = r1_estimate(
            df_b, outcome, "n_turn_legs",
            fe_granularity="date",
            sector_col="sector" if "sector" in df_b.columns else None,
            n_bootstrap=n_bootstrap,
        )

    locked = not a_any_ci_excl0
    recall = compute_recall(df_b, "n_turn_legs") if "n_turn_legs" in df_b.columns else {}

    return {
        "panel":              panel_name,
        "n_dropped_nan":      n_dropped_nan,
        "n_estimable":        len(df_b),
        "level_table":        level_table,
        "ordinal_results":    ordinal_results,
        "locked":             locked,
        "recall":             recall,
    }


def _run_family_c_form(
    form_name: str,
    deep_col: str,
    turn_col: str,
    graded: pd.DataFrame,
    panel_name: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    bear_ctx_col: str = "bear_ctx",
    rv63_tercile_col: str = "rv63_tercile",
) -> dict[str, Any]:
    """One form of family C: two contrasts + kill-arms."""
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    if deep_col not in df_ok.columns or turn_col not in df_ok.columns:
        return {"error": f"missing columns {deep_col} or {turn_col}", "form": form_name}

    df_ok["_washout_deep"] = (df_ok[deep_col] < WASHOUT_DEEP_THRESHOLD).astype(float)
    df_ok.loc[df_ok[deep_col].isna(), "_washout_deep"] = np.nan

    deep_s = df_ok["_washout_deep"]
    turn_s = df_ok[turn_col]
    df_ok["_deep_and_turn"] = np.where(
        deep_s.notna() & turn_s.notna(),
        ((deep_s == 1.0) & (turn_s == 1.0)).astype(float),
        np.nan,
    )

    # ── Contrast (i): within-deep, turn-vs-not ─────────────────────────────────
    within_deep_mask = (deep_s == 1.0) & turn_s.notna()
    n_treat_i = int(((df_ok.loc[within_deep_mask, turn_col] == 1.0)).sum())
    thin_i = n_treat_i < 400

    contrast_i: dict[str, dict] = {}
    if not thin_i or True:  # always run, stamp if thin
        for outcome in OUTCOME_BH:
            if outcome not in df_ok.columns:
                continue
            contrast_i[outcome] = r1_estimate(
                df_ok, outcome, turn_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=within_deep_mask,
            )

    # ── Contrast (ii): deep&turn vs rest ──────────────────────────────────────
    comp_mask_ii = deep_s.notna() & turn_s.notna()
    n_treat_ii = int((df_ok.loc[comp_mask_ii, "_deep_and_turn"] == 1.0).sum())
    thin_ii = n_treat_ii < 400

    contrast_ii: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in df_ok.columns:
            continue
        contrast_ii[outcome] = r1_estimate(
            df_ok, outcome, "_deep_and_turn",
            fe_granularity="date",
            sector_col="sector" if "sector" in df_ok.columns else None,
            n_bootstrap=n_bootstrap,
            computable_mask=comp_mask_ii,
        )

    # ── Kill-arm battery ───────────────────────────────────────────────────────
    nc2_kill_i: dict[str, dict] = {}
    nc2_kill_ii: dict[str, dict] = {}
    if "nc2_band" in df_ok.columns:
        for outcome in ["stop5"]:
            if outcome not in df_ok.columns:
                continue
            nc2_kill_i[outcome] = r1_estimate(
                df_ok, outcome, turn_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=within_deep_mask,
                extra_fe_cols=["nc2_band"],
            )
            nc2_kill_ii[outcome] = r1_estimate(
                df_ok, outcome, "_deep_and_turn",
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=comp_mask_ii,
                extra_fe_cols=["nc2_band"],
            )

    # ── Marginality r1_interaction_estimate ───────────────────────────────────
    marginality_results: dict[str, dict] = {}
    for outcome in ["stop5"]:
        if outcome not in df_ok.columns:
            continue
        marginality_results[outcome] = r1_interaction_estimate(
            df_ok, outcome, "_washout_deep", turn_col,
            fe_granularity="date",
            sector_col="sector" if "sector" in df_ok.columns else None,
            n_bootstrap=n_bootstrap,
            computable_mask=comp_mask_ii if comp_mask_ii.sum() > 20 else None,
        )

    # ── rv63_tercile FE kill-arm (RUL-30: vol-adjacent) ───────────────────────
    rv63_kill_i: dict[str, dict] = {}
    rv63_kill_ii: dict[str, dict] = {}
    if rv63_tercile_col in df_ok.columns:
        for outcome in ["stop5"]:
            if outcome not in df_ok.columns:
                continue
            rv63_kill_i[outcome] = r1_estimate(
                df_ok, outcome, turn_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=within_deep_mask & df_ok[rv63_tercile_col].notna(),
                extra_fe_cols=[rv63_tercile_col],
            )
            rv63_kill_ii[outcome] = r1_estimate(
                df_ok, outcome, "_deep_and_turn",
                fe_granularity="date",
                sector_col="sector" if "sector" in df_ok.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=comp_mask_ii & df_ok[rv63_tercile_col].notna(),
                extra_fe_cols=[rv63_tercile_col],
            )

    # ── ¬bear_ctx decomposition ────────────────────────────────────────────────
    bear_decomp: dict[str, Any] = {}
    if bear_ctx_col in df_ok.columns:
        for bval, blab in [(0.0, "notbear"), (1.0, "bear")]:
            bmask = (df_ok[bear_ctx_col] == bval)
            sub = df_ok[bmask & comp_mask_ii]
            if len(sub) < 50:
                bear_decomp[blab] = {"n": len(sub), "note": "thin"}
                continue
            res: dict[str, Any] = {"n": len(sub)}
            for outcome in ["stop5"]:
                if outcome not in sub.columns:
                    continue
                res[outcome] = r1_estimate(
                    sub, outcome, "_deep_and_turn",
                    fe_granularity="date",
                    sector_col="sector" if "sector" in sub.columns else None,
                    n_bootstrap=n_bootstrap,
                )
            bear_decomp[blab] = res

    return {
        "form":              form_name,
        "panel":             panel_name,
        "n_treat_i":         n_treat_i,
        "thin_i":            thin_i,
        "n_treat_ii":        n_treat_ii,
        "thin_ii":           thin_ii,
        "contrast_i":        contrast_i,
        "contrast_ii":       contrast_ii,
        "nc2_kill_i":        nc2_kill_i,
        "nc2_kill_ii":       nc2_kill_ii,
        "marginality":       marginality_results,
        "rv63_kill_i":       rv63_kill_i,
        "rv63_kill_ii":      rv63_kill_ii,
        "bear_decomp":       bear_decomp,
    }


def _run_family_d(
    graded: pd.DataFrame,
    panel_name: str,
    *,
    a_any_ci_excl0: bool,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """r1_interaction_estimate(stop5, sub_deep, w_hist_rising) per panel."""
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    if "sub_deep" not in df_ok.columns or "w_hist_rising" not in df_ok.columns:
        return {"error": "sub_deep or w_hist_rising absent", "panel": panel_name}

    comp_mask = df_ok["sub_deep"].notna() & df_ok["w_hist_rising"].notna()
    n_estimable = int(comp_mask.sum())

    interaction_results: dict[str, dict] = {}
    for outcome in OUTCOME_BH:
        if outcome not in df_ok.columns:
            continue
        interaction_results[outcome] = r1_interaction_estimate(
            df_ok, outcome, "sub_deep", "w_hist_rising",
            fe_granularity="date",
            sector_col="sector" if "sector" in df_ok.columns else None,
            n_bootstrap=n_bootstrap,
            computable_mask=comp_mask,
        )

    locked = not a_any_ci_excl0

    return {
        "panel":               panel_name,
        "n_estimable":         n_estimable,
        "interaction_results": interaction_results,
        "locked":              locked,
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
    """Run all A3 HTF families for one panel."""
    fires = fires.copy()
    if smoke_tickers is not None:
        fires = fires[fires["ticker"].isin(smoke_tickers)].copy()
        log.info("Smoke mode: %d fires after ticker filter", len(fires))

    fires["sector"] = fires["ticker"].map(sector_map)
    total_fires = len(fires)
    log.info("Panel %s: %d fires", panel_name, total_fires)

    # ── HTF flags at fires (RUL-31 PIT materialization) ───────────────────────
    log.info("  Computing HTF flags at fires...")
    htf_flags = compute_htf_flags_at_fires(fires, closes, smoke_tickers=smoke_tickers)
    log.info(
        "  w_hist_rising non-NaN: %d; w2_stoch_turn: %d; m_stoch_turn: %d",
        int(htf_flags["w_hist_rising"].notna().sum()),
        int(htf_flags["w2_stoch_turn"].notna().sum()),
        int(htf_flags["m_stoch_turn"].notna().sum()),
    )

    # ── NC-2 proximity proxy (shared helper, RUL-30) ──────────────────────────
    log.info("  Computing NC-2 proximity proxy...")
    nc2_prox = compute_nc2_proximity_proxy(fires, closes)
    nc2_bands = assign_nc2_bands(nc2_prox)

    # ── bear_ctx at fires ──────────────────────────────────────────────────────
    log.info("  Computing bear_ctx at fires...")
    bear_ctx = compute_bear_ctx_at_fires(fires, idx_close)

    # ── rv63 tercile at fires ──────────────────────────────────────────────────
    log.info("  Computing rv63 tercile at fires...")
    rv63_vals = compute_rv63_at_fires(fires, closes)
    rv63_tercile = assign_rv63_tercile(rv63_vals, fires, closes)

    # ── sub_deep binary ───────────────────────────────────────────────────────
    sub_deep = (fires["sub"].astype(str) == "deep").astype(float)

    # ── Grade fires ───────────────────────────────────────────────────────────
    log.info("  Grading fires...")
    extra_cols: dict[str, pd.Series] = {
        "w_hist_rising":  htf_flags["w_hist_rising"],
        "wbull_flag":     htf_flags["wbull"],
        "w2_stoch_turn":  htf_flags["w2_stoch_turn"],
        "w2_d_min6":      htf_flags["w2_d_min6"],
        "m_stoch_turn":   htf_flags["m_stoch_turn"],
        "nc2_band":       nc2_bands.reindex(fires.index),
        "bear_ctx":       bear_ctx,
        "rv63_tercile":   rv63_tercile,
        "sub_deep":       sub_deep.reindex(fires.index),
    }
    graded = grade_fires(fires, closes, extra_columns=extra_cols)
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, total_fires)

    graded_ok = graded[graded["gradable"].fillna(False)].copy()

    # ── mae21 alias ───────────────────────────────────────────────────────────
    if "fwd_mdd_21" in graded_ok.columns and "mae21" not in graded_ok.columns:
        graded_ok["mae21"] = graded_ok["fwd_mdd_21"]

    # ── Family A ──────────────────────────────────────────────────────────────
    log.info("  Running family A (esx_htf_turn)...")
    family_a: dict[str, Any] = {}
    rung_configs = [
        ("A1_w_hist_rising",  "w_hist_rising",  True),
        ("A2_w2_stoch_turn",  "w2_stoch_turn",  False),
        ("A3m_m_stoch_turn",  "m_stoch_turn",   False),
    ]
    for rung_name, col, is_a1 in rung_configs:
        log.info("    Rung %s...", rung_name)
        family_a[rung_name] = _run_family_a_rung(
            rung_name, col, graded_ok, panel_name,
            wbull_col="wbull_flag",
            a1_pooled_extra_fe=is_a1,
            n_bootstrap=n_bootstrap,
        )

    # ── Determine if any A-rung operative read has CI-excluding-0 ─────────────
    a_any_ci_excl0 = False
    for rung_name, _, _ in rung_configs:
        r2 = family_a[rung_name].get("read2_notwbull", {})
        for outcome in OUTCOME_BH:
            res = r2.get(outcome, {})
            ci_lo = res.get("ci_lo")
            ci_hi = res.get("ci_hi")
            if ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0):
                a_any_ci_excl0 = True

    # ── Family B ──────────────────────────────────────────────────────────────
    log.info("  Running family B (esx_htf_turn_dose)...")
    family_b = _run_family_b(
        graded_ok, panel_name,
        a_any_ci_excl0=a_any_ci_excl0,
        n_bootstrap=n_bootstrap,
    )

    # ── Family C ──────────────────────────────────────────────────────────────
    log.info("  Running family C (esx_washout_x_turn)...")
    family_c: dict[str, Any] = {}
    c_forms = [
        ("C1_deep_x_A1", "w2_d_min6", "w_hist_rising"),
        ("C2_deep_x_A2", "w2_d_min6", "w2_stoch_turn"),
    ]
    for form_name, deep_col, turn_col in c_forms:
        log.info("    Form %s...", form_name)
        family_c[form_name] = _run_family_c_form(
            form_name, deep_col, turn_col, graded_ok, panel_name,
            n_bootstrap=n_bootstrap,
        )

    # ── Family D ──────────────────────────────────────────────────────────────
    log.info("  Running family D (esx_sub_x_turn)...")
    family_d = _run_family_d(
        graded_ok, panel_name,
        a_any_ci_excl0=a_any_ci_excl0,
        n_bootstrap=n_bootstrap,
    )

    return {
        "panel":         panel_name,
        "total_fires":   total_fires,
        "n_gradable":    n_gradable,
        "family_a":      family_a,
        "family_b":      family_b,
        "family_c":      family_c,
        "family_d":      family_d,
        "a_any_ci_excl0": a_any_ci_excl0,
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
    """Run all A3 HTF families across panels."""
    _register_all_families(ledger_path)
    if not smoke:
        _register_a3_htf_trials(ledger_path)

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


def _fmt_r1(res: dict[str, Any], outcome: str) -> str:
    """Format one R1 result row for markdown."""
    r = res.get(outcome, {})
    if not r or r.get("coef") is None:
        return "— | — | — | — | —"
    coef = r["coef"]
    ci = f"[{r.get('ci_lo', 0):+.4f}, {r.get('ci_hi', 0):+.4f}]"
    p = r.get("p_value")
    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
    n_treat = r.get("n_treatment", r.get("n_treat", "?"))
    return f"{coef:+.4f} | {ci} | {_fmt_f(p, 4)} | {excl} | n_treat={n_treat}"


def write_report(all_results: dict[str, Any], out_path: Path, *, smoke: bool = False) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# A3 HTF Oscillator Motion Report — Entry-Stack Expansion Amendment 3")
    a("")
    a("**Amendment:** research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md")
    a("**Families:** esx_htf_turn (A, 12 trials), esx_htf_turn_dose (B, 2),")
    a("  esx_washout_x_turn (C, 8), esx_sub_x_turn (D, 2). Total: 24 new trials.")
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

    # ── Per-panel results ─────────────────────────────────────────────────────
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
        a(f"- Any A-rung operative CI-excluding-0: {'YES' if res.get('a_any_ci_excl0') else 'NO'}")
        a("")

        # ── Family A ──────────────────────────────────────────────────────────
        a("### Family A — esx_htf_turn (12 trials)")
        a("")
        a("RUL-28: CHIP promotion BLOCKED until eq_band. Verdict: DISPLAY-CANDIDATE / NULL / KILLED.")
        a("RUL-29: Operative read for A1 = ¬wbull subset. Pooled read carries wbull FE covariate.")
        a("")
        for rung_name in ("A1_w_hist_rising", "A2_w2_stoch_turn", "A3m_m_stoch_turn"):
            rung = res["family_a"].get(rung_name, {})
            if "error" in rung:
                a(f"#### Rung {rung_name} — ERROR: {rung['error']}")
                a("")
                continue

            a(f"#### Rung {rung_name}")
            a("")
            a(f"- Computable fires (feature non-NaN): {rung.get('n_computable', '?'):,}")
            a(f"- Burn-in dropped: {rung.get('n_burnin_dropped', '?'):,}")
            a(f"- ¬wbull subset n: {rung.get('n_notwbull', '?'):,}")
            a("")

            # Admission-leg decomposition (mandatory per RUL-29)
            adm = rung.get("admission_leg_table", [])
            if adm:
                a("**Admission-leg decomposition (RUL-29 mandatory):**")
                a("")
                a("| wbull | n_fires | stop5_mean | mae21_mean |")
                a("|---|---|---|---|")
                for row in adm:
                    a(f"| {row['wbull']} | {row['n_fires']:,} | "
                      f"{_fmt_pct(row.get('stop5_mean'))} | "
                      f"{_fmt_f(row.get('mae21_mean'), 4)} |")
                a("")

            # Read-1 pooled
            a("**Read-1 (pooled)**"
              + (" — carries wbull FE covariate (RUL-29)" if rung_name == "A1_w_hist_rising" else "")
              + ":")
            a("")
            r1p = rung.get("read1_pooled", {})
            a("| Outcome | Coef | 95% CI | p | CI excl 0? |")
            a("|---|---|---|---|---|")
            for outcome in OUTCOME_BH:
                r = r1p.get(outcome, {})
                if not r or r.get("coef") is None:
                    a(f"| {outcome} | — | — | — | — |")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
            a("")

            # Recall for read-2 (compute_recall output — not n_treat/n_total proxy)
            is_a1 = rung_name == "A1_w_hist_rising"
            recall_info = rung.get("recall", {})
            recall_val = recall_info.get("recall")
            recall_n_treat = recall_info.get("n_treatment", "?")
            recall_n_all = recall_info.get("n_all", "?")
            recall_display = (f"{recall_val:.3f} ({recall_n_treat}/{recall_n_all})"
                              if recall_val is not None else "—")
            a(f"**Read-2 ({'OPERATIVE — ¬wbull subset' if is_a1 else 'robustness — ¬wbull subset'}):**")
            a(f"Recall (compute_recall): {recall_display}")
            a("")
            r2 = rung.get("read2_notwbull", {})
            a("| Outcome | Coef | 95% CI | p | CI excl 0? |")
            a("|---|---|---|---|---|")
            for outcome in OUTCOME_BH:
                r = r2.get(outcome, {})
                if not r or r.get("coef") is None:
                    a(f"| {outcome} | — | — | — | — |")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
            a("")

            # NC-2 kill-arm
            nc2_kill = rung.get("nc2_kill", {})
            if nc2_kill:
                a("**Kill-arm battery — +nc2_band FE (RUL-30):**")
                a("")
                for outcome, r in nc2_kill.items():
                    if r.get("coef") is None:
                        a(f"- {outcome}: insufficient n or nc2_band absent")
                        continue
                    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                    a(f"- {outcome}: coef={r['coef']:+.4f} {_ci_str(r)} CI-excl-0={excl} "
                      f"(n_dropped_extra_fe={r.get('n_dropped_extra_fe', 0)})")
                a("")

            # Era × stratum table (RUL-28 mandatory)
            era_stab = rung.get("era_stability", {})
            era_rows = era_stab.get("era_rows", [])
            if era_rows:
                n_agree = era_stab.get("n_sign_agree", 0)
                n_est   = era_stab.get("n_eras_estimable", 0)
                stable  = era_stab.get("sign_stable_3of4", False)
                a(f"**Era × stratum table (RUL-28): n_agree={n_agree}/{n_est} eras"
                  f" — sign-stable ≥3/4: {'YES' if stable else 'NO'}**")
                a("")
                a("| Era | n_total | n_treatment | coef | sign |")
                a("|---|---|---|---|---|")
                for er in era_rows:
                    coef_s = f"{er['coef']:+.4f}" if er.get("coef") is not None else "—"
                    sign_s = {1: "+", -1: "-", None: "—"}.get(er.get("sign"))
                    note_s = f" _{er['note']}_" if er.get("note") else ""
                    a(f"| {er['era']} | {er.get('n_total','?')} | {er.get('n_treatment','?')}"
                      f" | {coef_s} | {sign_s}{note_s} |")
                a("")

            # Ticker-half sign agreement (baskets mandatory per RUL-28)
            th = rung.get("ticker_half", {})
            if th.get("half_rows"):
                th_agree = th.get("sign_agree", False)
                a(f"**Ticker-half sign agreement (RUL-28 baskets): {'AGREE' if th_agree else 'DISAGREE'}**")
                a("")
                a("| Half | tickers_n | n_total | coef | sign |")
                a("|---|---|---|---|---|")
                for hr in th["half_rows"]:
                    coef_s = f"{hr['coef']:+.4f}" if hr.get("coef") is not None else "—"
                    sign_s = {1: "+", -1: "-", None: "—"}.get(hr.get("sign"))
                    a(f"| {hr['half']} | {hr.get('tickers_n','?')} | {hr.get('n_total','?')}"
                      f" | {coef_s} | {sign_s} |")
                a("")

            # Verdict — conjunctive: CI-excl-0 AND era-sign-stable >=3/4
            # AND (baskets) ticker-half sign agreement (RUL-28)
            op_read = rung.get("read2_notwbull", {})
            stop5_r = op_read.get("stop5", {})
            ci_lo = stop5_r.get("ci_lo")
            ci_hi = stop5_r.get("ci_hi")
            ci_excl0 = (ci_lo is not None and ci_hi is not None and (ci_lo > 0 or ci_hi < 0))
            era_ok   = era_stab.get("sign_stable_3of4", False)
            th_ok    = th.get("sign_agree", True) if th.get("half_rows") else True
            if ci_excl0 and era_ok and th_ok:
                verdict_str = "DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)"
            elif not ci_excl0:
                verdict_str = "NULL (CI includes 0 on operative read)"
            elif not era_ok:
                verdict_str = f"NULL (CI-excl-0 but era sign-stability fails: {era_stab.get('n_sign_agree',0)}/4 eras agree)"
            else:
                verdict_str = "NULL (CI-excl-0, era-stable, but ticker-half sign disagrees; RUL-28)"
            a(f"**Verdict (stop5 operative read): {verdict_str}**")
            a("CHIP promotion blocked until true eq_band (RUL-28).")
            a("")

        # ── Family B ──────────────────────────────────────────────────────────
        a("### Family B — esx_htf_turn_dose (2 trials)")
        a("")
        fb = res.get("family_b", {})
        if "error" in fb:
            a(f"**ERROR:** {fb['error']}")
        elif fb.get("locked"):
            a("**LOCKED (RUL-32): no A-rung operative read has CI-excluding-0. Descriptive only.**")
            a("")
        else:
            a("**UNLOCKED: >=1 A-rung operative read has CI-excluding-0.**")
            a("")

        a(f"- Dropped (NaN in any rung column): {fb.get('n_dropped_nan', '?'):,}")
        a(f"- Estimable fires: {fb.get('n_estimable', '?'):,}")
        a("")

        lvl_tbl = fb.get("level_table", [])
        if lvl_tbl:
            a("**Per-level descriptive table (no CI):**")
            a("")
            a("| n_turn_legs | n_fires | stop5_mean | mae21_mean |")
            a("|---|---|---|---|")
            for row in lvl_tbl:
                a(f"| {row['n_turn_legs']} | {row['n_fires']:,} | "
                  f"{_fmt_pct(row.get('stop5_mean'))} | {_fmt_f(row.get('mae21_mean'), 4)} |")
            a("")

        ord_res = fb.get("ordinal_results", {})
        if ord_res:
            a("**Ordinal per-unit coefficient (n_turn_legs as numeric stratum):**")
            a("")
            a("| Outcome | Coef | 95% CI | p | CI excl 0? |")
            a("|---|---|---|---|---|")
            for outcome in OUTCOME_BH:
                r = ord_res.get(outcome, {})
                if not r or r.get("coef") is None:
                    a(f"| {outcome} | — | — | — | — |")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
            a("")

        a("CHIP promotion blocked until true eq_band (RUL-28).")
        a("")

        # ── Family C ──────────────────────────────────────────────────────────
        a("### Family C — esx_washout_x_turn (8 trials)")
        a("")
        a("Pre-registered expectation: raw interaction most proximity-exposed; proxy-FE arm expected to bite. Thin-cell law: n_treat < 400 → DESCRIPTIVE stamp.")
        a("")
        fc = res.get("family_c", {})
        for form_name, form_res in fc.items():
            a(f"#### Form {form_name}")
            a("")
            if "error" in form_res:
                a(f"**ERROR:** {form_res['error']}")
                a("")
                continue

            a(f"- n_treat contrast-i (within-deep turn-vs-not): {form_res.get('n_treat_i', '?'):,}"
              + (" — **DESCRIPTIVE STAMP** (n<400)" if form_res.get('thin_i') else ""))
            a(f"- n_treat contrast-ii (deep&turn vs rest): {form_res.get('n_treat_ii', '?'):,}"
              + (" — **DESCRIPTIVE STAMP** (n<400)" if form_res.get('thin_ii') else ""))
            a("")

            a("**Contrast (i): within-deep turn-vs-not:**")
            a("")
            ci_res = form_res.get("contrast_i", {})
            a("| Outcome | Coef | 95% CI | p | CI excl 0? |")
            a("|---|---|---|---|---|")
            for outcome in OUTCOME_BH:
                r = ci_res.get(outcome, {})
                if not r or r.get("coef") is None:
                    a(f"| {outcome} | — | — | — | — |")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
            a("")

            a("**Contrast (ii): deep&turn vs rest:**")
            a("")
            cii_res = form_res.get("contrast_ii", {})
            a("| Outcome | Coef | 95% CI | p | CI excl 0? |")
            a("|---|---|---|---|---|")
            for outcome in OUTCOME_BH:
                r = cii_res.get(outcome, {})
                if not r or r.get("coef") is None:
                    a(f"| {outcome} | — | — | — | — |")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
            a("")

            a("**Kill-arm battery:**")
            a("")
            # +nc2_band FE
            for arm_label, arm_dict in [
                ("+nc2_band FE (contrast-i)", form_res.get("nc2_kill_i", {})),
                ("+nc2_band FE (contrast-ii)", form_res.get("nc2_kill_ii", {})),
                ("+rv63_tercile FE (contrast-i, RUL-30)", form_res.get("rv63_kill_i", {})),
                ("+rv63_tercile FE (contrast-ii, RUL-30)", form_res.get("rv63_kill_ii", {})),
            ]:
                for outcome, r in arm_dict.items():
                    if r.get("coef") is None:
                        a(f"- {arm_label} | {outcome}: insufficient n or column absent")
                        continue
                    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                    a(f"- {arm_label} | {outcome}: coef={r['coef']:+.4f} {_ci_str(r)} CI-excl-0={excl}")

            # Marginality
            for outcome, r in form_res.get("marginality", {}).items():
                if r.get("coef") is None:
                    a(f"- Marginality r1_interaction | {outcome}: insufficient n")
                    continue
                excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                 and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                a(f"- Marginality interaction | {outcome}: coef={r['coef']:+.4f} {_ci_str(r)} CI-excl-0={excl}")
            a("")

            # ¬bear_ctx decomposition
            bear_d = form_res.get("bear_decomp", {})
            if bear_d:
                a("**¬bear_ctx decomposition (descriptive — kill-only per RUL-30):**")
                a("")
                a("| Context | n | stop5 coef | CI-excl-0? |")
                a("|---|---|---|---|")
                for blab in ("notbear", "bear"):
                    bd = bear_d.get(blab, {})
                    if "note" in bd:
                        a(f"| {blab} | {bd.get('n', '?')} | thin | — |")
                        continue
                    r = bd.get("stop5", {})
                    if not r or r.get("coef") is None:
                        a(f"| {blab} | {bd.get('n', '?')} | — | — |")
                        continue
                    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                    a(f"| {blab} | {bd.get('n', '?')} | {r['coef']:+.4f} | {excl} |")
                a("")

            a("CHIP promotion blocked until true eq_band (RUL-28).")
            a("")

        # ── Family D ──────────────────────────────────────────────────────────
        a("### Family D — esx_sub_x_turn (2 trials)")
        a("")
        fd = res.get("family_d", {})
        if "error" in fd:
            a(f"**ERROR:** {fd['error']}")
            a("")
        else:
            if fd.get("locked"):
                a("**LOCKED (RUL-32): no A-rung operative read has CI-excluding-0. Descriptive only.**")
            else:
                a("**UNLOCKED.**")
            a("")
            a(f"- Estimable fires: {fd.get('n_estimable', '?'):,}")
            a("")

            int_res = fd.get("interaction_results", {})
            if int_res:
                a("**r1_interaction_estimate(outcome, sub_deep, w_hist_rising):**")
                a("")
                a("| Outcome | Interaction coef | 95% CI | p | CI excl 0? |")
                a("|---|---|---|---|---|")
                for outcome in OUTCOME_BH:
                    r = int_res.get(outcome, {})
                    if not r or r.get("coef") is None:
                        a(f"| {outcome} | — | — | — | — |")
                        continue
                    excl = "YES" if (r.get("ci_lo") is not None and r.get("ci_hi") is not None
                                     and (r["ci_lo"] > 0 or r["ci_hi"] < 0)) else "no"
                    a(f"| {outcome} | {r['coef']:+.4f} | {_ci_str(r)} | {_fmt_f(r.get('p_value'), 4)} | {excl} |")
                a("")

            a("CHIP promotion blocked until true eq_band (RUL-28).")
            a("")

        a("---")
        a("")

    a("## Program Summary")
    a("")
    a("| Family | Trials | Verdict ceiling |")
    a("|---|---|---|")
    a("| esx_htf_turn (A)       | 12 | DISPLAY-CANDIDATE / NULL / KILLED (RUL-28) |")
    a("| esx_htf_turn_dose (B)  |  2 | LOCKED behind A; DESCRIPTIVE if LOCKED |")
    a("| esx_washout_x_turn (C) |  8 | DISPLAY-CANDIDATE / NULL / KILLED (RUL-28) |")
    a("| esx_sub_x_turn (D)     |  2 | LOCKED behind A; DESCRIPTIVE if LOCKED |")
    a("")
    a("CHIP promotion blocked for ALL A3 families until true eq_band lands (RUL-28).")
    a("")
    a("*Generated by `scripts/research/run_a3_htf.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*The word 'validated' deliberately absent (CI-enforced).*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="A3 HTF Oscillator Motion — families A/B/C/D.",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "A3_HTF_REPORT.md"),
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

    log.info("A3 HTF (n_bootstrap=%d, panels=%s, smoke=%s)", n_boot, panels or "all", args.smoke)
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
