"""CPI feature-trial runner — family ``cycle_pattern_ft`` (PREREGISTRATION.md §12).

RESEARCH TRACK (masterplan §4 — the information program). FROZEN by §12: this runner
tests whether two NEW orthogonal covariate blocks add out-of-sample turn-hazard skill
BEYOND the currently-shipped W2.5-bound feature set. Nothing here touches a page; the
deliverable is an honest verdict against the pre-registered gates.

WHAT THIS DOES (all parameters frozen in §12; none tuned here)
  1. Loads the price-basis person-period panel ``data/hazard/panel_price_c4414dcb.parquet``
     and TRUNCATES to rows dated BEFORE 2024-01-01 (holdout embargo, §12 — stricter than
     W4.2's own span; preserves the untouched confirmatory window; test years 2010–2023).

  2. Builds two FROZEN feature blocks EXACTLY as §12 defines:
       FT-1 breadth  (PIT-pure from the instrument's own panel-family member price tapes):
         fam_pct_above_200d, fam_pct_above_50d, breadth_div_own, breadth_thrust_3m
       FT-4 structure (PIT-pure from the panel cross-section at t):
         sync_family, phase_breadth_late, phase_breadth_early, pos_dispersion

  3. For each direction {up, down}: fits BASE (the exact W4.2 DESIGN) and BASE+FT1 and
     BASE+FT4 under IDENTICAL expanding-annual walk-forward folds — by reusing
     ``fit_cycle_hazard.walk_forward`` with an injected feature list (no math is forked).
     Leak-free out-of-fold PAV calibration is the W4.2 harness's own (``p{h}_caloof``).

  4. GATE per cell (block × direction × horizon), all reusing fit_cycle_hazard functions:
       paired ΔBrier(base − base+block) month-block bootstrap 90% CI (800 draws, seed 7,
       ``month_block_brier_gap_ci``) must exclude 0 on the POSITIVE side (block lowers
       Brier), sign-stability ≥ 9 of 14 test years, then BH-FDR q=0.10 across ALL 12 cells
       jointly (both blocks are ONE family; ``bh_fdr``).

  5. Writes data/cycle_pattern/ft_trials/{ft1_breadth,ft4_structure}.json. Prints the
     candidate count (12) BEFORE any evaluation (anti-mining law, §12).

Trial budget: family ``rf.cycle_pattern.ft_v0``, n=12, declared to data/trial_ledger.jsonl
at criteria-commit run time (house convention: a runtime log_declared_budget before any
p-value; --smoke isolates this to a scratch path and writes NO real artifacts).

Pure numpy/pandas/pyarrow. NO sklearn / statsmodels / scipy.stats. Deterministic (seed 7).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Reuse the W4.2 harness math verbatim — import, never fork (§12 "the W4.2 harness verbatim").
from scripts.fit_cycle_hazard import (  # noqa: E402
    BOOT_DRAWS,
    BOOT_SEED,
    CONT_FEATURES,
    DESIGN,
    EMBARGO_M,
    FDR_Q,
    FIRST_TEST_YEAR,
    HORIZONS,
    L2_MASK_EXEMPT,
    _boot_pvalue,
    _brier,
    bh_fdr,
    build_design,
    compound_model,
    month_block_brier_gap_ci,
    walk_forward,
)
# ── FROZEN constants (PREREGISTRATION.md §12; not tuned) ────────────────────────
EMBARGO_DATE = pd.Timestamp("2024-01-01")   # rows with date >= this are excluded (fit AND gate)
SIGN_STABILITY_MIN = 9                       # ΔBrier > 0 in ≥ 9 of 14 test years
N_TEST_YEARS = 14                            # 2010..2023 inclusive
FAMILY = "rf.cycle_pattern.ft_v0"            # trial-budget family (§12)
N_TRIALS = 12                                # 2 blocks × 2 directions × 3 horizons

# FROZEN feature blocks — NO per-feature selection permitted after the criteria commit.
# These lists are the guarded spec (tests parse them and assert against §12).
FT1_BREADTH_BLOCK = [
    "fam_pct_above_200d",
    "fam_pct_above_50d",
    "breadth_div_own",
    "breadth_thrust_3m",
]
FT4_STRUCTURE_BLOCK = [
    "sync_family",
    "phase_breadth_late",
    "phase_breadth_early",
    "pos_dispersion",
]

# Panel-family member universes (verbatim from scripts/build_hazard_panel.py:73-91).
US_SECTOR_IDS = [
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
]
COUNTRY_IDS = [
    "AAXJ", "ECH", "EEM", "EFA", "EIDO", "EPOL", "EWA", "EWC", "EWD", "EWG",
    "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP", "EWQ", "EWS", "EWT", "EWU",
    "EWW", "EWY", "EWZ", "EZA", "FXI", "ILF", "INDA", "TUR", "VGK", "VPL", "VXUS",
]
CN_SECTOR_IDS = [
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
]
FAMILY_MEMBERS = {
    "us_sector": US_SECTOR_IDS,
    "country": COUNTRY_IDS,
    "cn_sector": CN_SECTOR_IDS,
}

SMA_200 = 200
SMA_50 = 50
SMA_200_MIN = 100   # min_periods mirrors build_hazard_panel._trend_pass (rolling(200, min_periods=100))
SMA_50_MIN = 25     # half-window min, mirroring the 200d convention proportionally


# ═══════════════════════════════════════════════════════════════════════════════
# Price-tape loaders — MIRROR build_hazard_panel.py exactly (same basis, same cols)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_yahoo_price(ticker: str, yahoo_dir: Path) -> pd.Series | None:
    """Price close (split-adjusted, dividend-UNadjusted). STRUCTURE-MATH basis — verbatim
    mirror of build_hazard_panel._load_yahoo_price (D4_SUBSTRATE §1: never TR)."""
    path = yahoo_dir / f"{ticker.upper()}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close_price" in df.columns:
        s = df["close_price"].dropna().sort_index()
    elif "close" in df.columns:
        s = df["close"].dropna().sort_index()   # pre-T5 fallback (wrong basis; warned upstream)
    else:
        return None
    s.index = pd.to_datetime(s.index)
    return s


def _load_cn_sector_close(code: str, cn_dir: Path) -> pd.Series | None:
    """Shenwan custodian close (IS the price basis, D4_SUBSTRATE §1.54) — verbatim mirror."""
    path = cn_dir / f"{code}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        return None
    s = df["close"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def _load_family_tapes(family: str, yahoo_dir: Path, cn_dir: Path) -> dict[str, pd.Series]:
    """Load every member's daily price series for a family. Missing tapes are skipped
    (breadth is a fraction over the members that HAVE data at t)."""
    out: dict[str, pd.Series] = {}
    for mid in FAMILY_MEMBERS[family]:
        if family == "cn_sector":
            s = _load_cn_sector_close(mid, cn_dir)
        else:
            s = _load_yahoo_price(mid, yahoo_dir)
        if s is not None and len(s) > 0:
            out[mid] = s
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# FT-1 breadth block — fraction of family members above their own SMA at t (PIT)
# ═══════════════════════════════════════════════════════════════════════════════

def _above_sma_flag(close: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Daily 0/1: close > its own rolling SMA(window). Causal — mirrors
    build_hazard_panel._trend_pass (rolling(window, min_periods).mean())."""
    sma = close.rolling(window, min_periods=min_periods).mean()
    return (close > sma).astype(float)   # NaN SMA → comparison False → 0.0


def compute_family_breadth(family: str, month_ends: list[pd.Timestamp],
                           yahoo_dir: Path, cn_dir: Path) -> pd.DataFrame:
    """Per family per month-end t: fraction of members whose close > own 200d / 50d SMA,
    using ONLY closes <= t (PIT). Returns a frame indexed by (date) with
    [fam_pct_above_200d, fam_pct_above_50d, n_members_200d, n_members_50d].

    The last-observation-carried extraction (closes <= t) is the same _at(...) contract
    build_hazard_panel uses; the SMA and the > comparison at t see closes <= t only, so
    there is no look-ahead.
    """
    tapes = _load_family_tapes(family, yahoo_dir, cn_dir)
    # Precompute daily SMAs + above-SMA flags per member ONCE (no per-t recompute).
    # A member enters the breadth denominator at t only if its SMA is DEFINED at the last
    # close <= t (enough history); NaN-SMA members are absent, not counted as "below".
    sma200 = {mid: s.rolling(SMA_200, min_periods=SMA_200_MIN).mean() for mid, s in tapes.items()}
    sma50 = {mid: s.rolling(SMA_50, min_periods=SMA_50_MIN).mean() for mid, s in tapes.items()}
    flags200 = {mid: _above_sma_flag(s, SMA_200, SMA_200_MIN) for mid, s in tapes.items()}
    flags50 = {mid: _above_sma_flag(s, SMA_50, SMA_50_MIN) for mid, s in tapes.items()}

    rows = []
    for t in month_ends:
        vals200, vals50 = [], []
        for mid, s in tapes.items():
            pos = s.index.searchsorted(t, side="right")   # count of closes <= t
            if pos == 0:
                continue
            j = pos - 1   # last index position with close <= t (PIT last-obs-carried)
            if pd.notna(sma200[mid].iloc[j]):
                vals200.append(float(flags200[mid].iloc[j]))
            if pd.notna(sma50[mid].iloc[j]):
                vals50.append(float(flags50[mid].iloc[j]))
        rows.append({
            "date": t,
            "fam_pct_above_200d": float(np.mean(vals200)) if vals200 else np.nan,
            "fam_pct_above_50d": float(np.mean(vals50)) if vals50 else np.nan,
            "n_members_200d": len(vals200),
            "n_members_50d": len(vals50),
        })
    return pd.DataFrame(rows).set_index("date")


def attach_ft1_breadth(panel: pd.DataFrame, yahoo_dir: Path, cn_dir: Path) -> pd.DataFrame:
    """Add the FT-1 breadth block to the panel (per family, per month-end, PIT).

    fam_pct_above_200d / fam_pct_above_50d : family breadth from member tapes at t.
    breadth_div_own    = fam_pct_above_200d − own trend_pass  (panel 0/1 above-200d column).
    breadth_thrust_3m  = fam_pct_above_50d(t) − fam_pct_above_50d(3 month-ends prior).
    """
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    for c in FT1_BREADTH_BLOCK:
        d[c] = np.nan
    for family in sorted(d["family"].unique()):
        fam_dates = sorted(pd.to_datetime(d.loc[d["family"] == family, "date"].unique()))
        bf = compute_family_breadth(family, fam_dates, yahoo_dir, cn_dir)
        bf = bf.sort_index()
        # 3-month-end-prior thrust on the FAMILY breadth series (shift by 3 month-ends).
        bf["breadth_thrust_3m"] = bf["fam_pct_above_50d"] - bf["fam_pct_above_50d"].shift(3)
        mask = d["family"] == family
        idx = d.loc[mask, "date"]
        d.loc[mask, "fam_pct_above_200d"] = idx.map(bf["fam_pct_above_200d"]).to_numpy()
        d.loc[mask, "fam_pct_above_50d"] = idx.map(bf["fam_pct_above_50d"]).to_numpy()
        d.loc[mask, "breadth_thrust_3m"] = idx.map(bf["breadth_thrust_3m"]).to_numpy()
    # breadth_div_own needs the panel's own above-200d indicator (trend_pass, 0/1).
    own = pd.to_numeric(d["trend_pass"], errors="coerce")
    d["breadth_div_own"] = d["fam_pct_above_200d"] - own
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# FT-4 structure block — from the panel cross-section of pos_osc at each (family, date)
# ═══════════════════════════════════════════════════════════════════════════════

def _sync_R(pos_vals: np.ndarray) -> float:
    """Circular mean resultant length R = sync = 1 − circular variance. EXACT formula from
    scripts/append_sync_gauge._compute_sync / scripts/leadlag_phase0.compute_sync_gauge:
        ang = 2π·pos/100 ; R = sqrt(mean(cos)² + mean(sin)²)."""
    ang = 2.0 * np.pi * (pos_vals / 100.0)
    return float(np.sqrt(np.mean(np.cos(ang)) ** 2 + np.mean(np.sin(ang)) ** 2))


def attach_ft4_structure(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the FT-4 structure block from the panel cross-section at each (family, date).

    sync_family        = 1 − circular variance of family pos_osc (the W5.1 statistic, = R).
    phase_breadth_late = fraction of family members with pos_osc ≥ 70.
    phase_breadth_early= fraction with pos_osc ≤ 30.
    pos_dispersion     = cross-sectional std(pos_osc) / 100.

    Cross-section = the panel rows at (family, date) pooled over BOTH directions (the
    up/down rows carry the same per-instrument pos_osc; the structure statistic is a
    property of the instrument set at t, direction-invariant). Computed once per
    (family, date) and broadcast to every row of that cell — PIT-pure (pos_osc is already
    causal at t in the panel).
    """
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    pos = pd.to_numeric(d["pos_osc"], errors="coerce")
    d["_pos"] = pos
    # One row per instrument per (family, date): dedup on id so a member counted once even
    # though it appears in both up and down direction rows.
    uniq = d.drop_duplicates(subset=["family", "date", "id"])[["family", "date", "id", "_pos"]]
    recs = {}
    for (family, date), grp in uniq.groupby(["family", "date"]):
        vals = grp["_pos"].dropna().to_numpy(float)
        if len(vals) == 0:
            recs[(family, date)] = (np.nan, np.nan, np.nan, np.nan)
            continue
        recs[(family, date)] = (
            _sync_R(vals),
            float(np.mean(vals >= 70)),
            float(np.mean(vals <= 30)),
            float(np.std(vals)) / 100.0,
        )
    keys = list(zip(d["family"], d["date"]))
    d["sync_family"] = [recs[k][0] for k in keys]
    d["phase_breadth_late"] = [recs[k][1] for k in keys]
    d["phase_breadth_early"] = [recs[k][2] for k in keys]
    d["pos_dispersion"] = [recs[k][3] for k in keys]
    return d.drop(columns=["_pos"])


# ═══════════════════════════════════════════════════════════════════════════════
# Fit BASE and BASE+block under identical folds (reusing walk_forward)
# ═══════════════════════════════════════════════════════════════════════════════

def _fit_oos(panel_d: pd.DataFrame, direction: str, design: list[str],
             cont_features: list[str]):
    """Walk-forward fit for a given feature list, returning the compounded OOS frame with
    leak-free p{h}_caloof (the W4.2 harness's own out-of-fold PAV). No math forked."""
    oos, fits = walk_forward(
        panel_d, direction,
        design=design, cont_features=cont_features, l2_exempt=L2_MASK_EXEMPT,
    )
    if oos.empty:
        return oos, fits
    return compound_model(oos), fits


def _cell_gate(dates, y, p_base, p_block, years):
    """Paired ΔBrier(base − base+block) gate for one (direction, horizon) cell.

    Positive gap = base+block has LOWER Brier (adds skill). Reuses fit_cycle_hazard's
    month_block_brier_gap_ci / _boot_pvalue verbatim (block plays the 'model' role, base
    plays the 'km' role, so gap = Brier_base − Brier_block)."""
    br_base = _brier(p_base, y)
    br_block = _brier(p_block, y)
    gap, lo, hi = month_block_brier_gap_ci(dates, br_base, br_block)
    pval = _boot_pvalue(dates, br_base, br_block)
    gap_arr = br_base - br_block
    yr_means = pd.Series(gap_arr).groupby(years).mean()
    n_pos, n_yr = int((yr_means > 0).sum()), int(len(yr_means))
    return {
        "delta_brier": round(float(gap), 6),
        "brier_base": round(float(np.mean(br_base)), 6),
        "brier_block": round(float(np.mean(br_block)), 6),
        "ci90": [round(lo, 6) if lo is not None else None,
                 round(hi, 6) if hi is not None else None],
        "boot_p": round(float(pval), 4),
        "ci_excludes_zero": bool(lo is not None and lo > 0),
        "years_positive": n_pos,
        "n_years": n_yr,
        "sign_stable": bool(n_pos >= SIGN_STABILITY_MIN),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def run_block(panel_d: pd.DataFrame, block: list[str], *,
              directions=("up", "down"), horizons=HORIZONS) -> dict:
    """Fit BASE and BASE+block for each direction under identical folds, then compute the
    per-cell gate diagnostics (pre-BH; BH is applied jointly across both blocks later).

    Returns {ledger: {dir: {h: cell}}, per_fold: {...}, cell_pvals: [(dir,h,p)...]}."""
    base_design = list(DESIGN)
    base_cont = list(CONT_FEATURES)
    block_design = base_design + list(block)
    block_cont = base_cont + list(block)

    ledger = {d: {} for d in directions}
    per_fold = {d: {} for d in directions}
    cell_pvals = []   # (direction, horizon, pval) in the order they were appended
    for direction in directions:
        base_oos, base_fits = _fit_oos(panel_d, direction, base_design, base_cont)
        blk_oos, blk_fits = _fit_oos(panel_d, direction, block_design, block_cont)
        if base_oos.empty or blk_oos.empty:
            for h in horizons:
                ledger[direction][f"{h}m"] = {"verdict": "FAIL", "reason": "no_oos"}
                cell_pvals.append((direction, h, 1.0))
            continue
        # Fold geometry MUST be identical (same rows/folds) — assert alignment.
        assert (base_oos["date"].to_numpy() == blk_oos["date"].to_numpy()).all() and \
               (base_oos["id"].to_numpy() == blk_oos["id"].to_numpy()).all(), \
               "base and base+block folds diverged — feature injection must not drop rows"
        dates = base_oos["date"].to_numpy()
        years = pd.to_datetime(base_oos["date"]).dt.year.to_numpy()
        per_fold[direction] = {
            "n_folds": len(base_fits),
            "test_years": [f["test_year"] for f in base_fits],
            "n_train_per_fold": [f["n_train"] for f in base_fits],
            "n_test_per_fold": [f["n_test"] for f in base_fits],
        }
        for h in horizons:
            y = base_oos[f"y{h}"].to_numpy(float)
            p_base = base_oos[f"p{h}_caloof"].to_numpy(float)
            p_block = blk_oos[f"p{h}_caloof"].to_numpy(float)
            cell = _cell_gate(dates, y, p_base, p_block, years)
            cell["n_oos"] = int(len(base_oos))
            ledger[direction][f"{h}m"] = cell
            cell_pvals.append((direction, h, cell["boot_p"]))
    return {"ledger": ledger, "per_fold": per_fold, "cell_pvals": cell_pvals}


def build_ledgers(panel_d: pd.DataFrame, *, directions=("up", "down"),
                  horizons=HORIZONS) -> tuple[dict, dict]:
    """Run both blocks, apply BH-FDR q=0.10 JOINTLY across all 12 cells (one family), and
    stamp per-cell verdicts. Returns (ft1_result, ft4_result)."""
    ft1 = run_block(panel_d, FT1_BREADTH_BLOCK, directions=directions, horizons=horizons)
    ft4 = run_block(panel_d, FT4_STRUCTURE_BLOCK, directions=directions, horizons=horizons)

    # Joint BH-FDR across ALL cells of BOTH blocks (both blocks = one family, §12).
    combined = []  # (block_key, direction, horizon, pval)
    for direction, h, p in ft1["cell_pvals"]:
        combined.append(("ft1", direction, h, p))
    for direction, h, p in ft4["cell_pvals"]:
        combined.append(("ft4", direction, h, p))
    pvals = [p for (_, _, _, p) in combined]
    rejects = bh_fdr(pvals, q=FDR_Q)

    res = {"ft1": ft1, "ft4": ft4}
    for (bkey, direction, h, _), rej in zip(combined, rejects):
        cell = res[bkey]["ledger"][direction][f"{h}m"]
        cell["bh_pass"] = bool(rej)
        # PASS ⇔ CI excludes 0 (positive side) AND sign-stable ≥9/14 AND survives BH-FDR.
        cell["verdict"] = "PASS" if (
            cell.get("ci_excludes_zero", False)
            and cell.get("sign_stable", False)
            and rej
        ) else "FAIL"
    return ft1, ft4


def _restructure_ledger(block_result: dict) -> dict:
    """Reshape run_block output into the §12 ledger schema {up:{1m:{...}}, down:{...}}."""
    out = {}
    for direction, cells in block_result["ledger"].items():
        out[direction] = {}
        for hkey, cell in cells.items():
            out[direction][hkey] = {
                "delta_brier": cell.get("delta_brier"),
                "ci90": cell.get("ci90"),
                "boot_p": cell.get("boot_p"),
                "years_positive": cell.get("years_positive"),
                "n_years": cell.get("n_years"),
                "bh_pass": cell.get("bh_pass", False),
                "verdict": cell.get("verdict", "FAIL"),
                # diagnostics (not gate inputs, but honest to record)
                "brier_base": cell.get("brier_base"),
                "brier_block": cell.get("brier_block"),
                "ci_excludes_zero": cell.get("ci_excludes_zero"),
                "sign_stable": cell.get("sign_stable"),
                "n_oos": cell.get("n_oos"),
            }
    return out


FEATURE_BLOCK_DEFS = {
    "ft1_breadth": {
        "features": FT1_BREADTH_BLOCK,
        "fam_pct_above_200d": "fraction of family members with close > own 200d SMA at t (PIT, close_price/cn basis)",
        "fam_pct_above_50d": "fraction of family members with close > own 50d SMA at t (PIT)",
        "breadth_div_own": "fam_pct_above_200d − own trend_pass (panel 0/1 above-200d indicator)",
        "breadth_thrust_3m": "fam_pct_above_50d(t) − fam_pct_above_50d(3 month-ends prior)",
    },
    "ft4_structure": {
        "features": FT4_STRUCTURE_BLOCK,
        "sync_family": "1 − circular variance of family pos_osc, ang=2π·pos/100, R=sqrt(mean_cos²+mean_sin²)",
        "phase_breadth_late": "fraction of family members with pos_osc ≥ 70",
        "phase_breadth_early": "fraction of family members with pos_osc ≤ 30",
        "pos_dispersion": "cross-sectional std(pos_osc) / 100",
    },
}


def build_artifact(block_key: str, block_result: dict, *, panel_epoch: str, n_rows: int,
                   n_test_years: int) -> dict:
    """Assemble the §12 JSON artifact for one block."""
    return {
        "schema": "cycle_pattern_ft_trial.v1",
        "registered_ref": "PREREGISTRATION.md §12",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "embargo": "date<2024-01-01",
        "panel_epoch": panel_epoch,
        "n_rows": int(n_rows),
        "n_test_years": int(n_test_years),
        "candidate_count_printed": N_TRIALS,
        "trial_family": FAMILY,
        "config": {
            "first_test_year": FIRST_TEST_YEAR, "embargo_m": EMBARGO_M,
            "boot_draws": BOOT_DRAWS, "boot_seed": BOOT_SEED, "fdr_q": FDR_Q,
            "sign_stability_min": SIGN_STABILITY_MIN, "n_cells_family": N_TRIALS,
            "base_design": list(DESIGN),
        },
        "feature_block": FEATURE_BLOCK_DEFS[block_key],
        "per_fold": block_result["per_fold"],
        "ledger": _restructure_ledger(block_result),
    }


def _load_panel(panel_path: Path) -> tuple[pd.DataFrame, str]:
    panel = pd.read_parquet(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    epoch = str(panel["turn_def_version"].iloc[0]) if "turn_def_version" in panel.columns \
        else panel_path.stem.replace("panel_", "")
    return panel, epoch


def truncate_embargo(panel: pd.DataFrame) -> pd.DataFrame:
    """§12 holdout embargo: keep ONLY rows with date < 2024-01-01 (fit AND gate)."""
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    return d[d["date"] < EMBARGO_DATE].reset_index(drop=True)


def declare_trial_budget(ledger_path: Path, *, run_at: str) -> None:
    """House convention: register the multiple-testing budget as a runtime
    log_declared_budget BEFORE any p-value (mirrors run_kernel_decisions STEP 3). Idempotent
    (dedup on family+n+reason). Under --smoke the ledger_path is a scratch file, never
    data/trial_ledger.jsonl."""
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(path=ledger_path, family=FAMILY)
    led.log_declared_budget(
        N_TRIALS, family=FAMILY,
        reason=(f"PREREGISTRATION.md §12 cycle_pattern_ft: 2 blocks × 2 directions × "
                f"3 horizons = 12 pre-registered cells; run_at={run_at}"),
    )


def _run_batch1(panel_path: Path, out_dir: Path, *, smoke: bool = False,
                ledger_path: Path | None = None, write: bool = True) -> dict:
    panel, epoch = _load_panel(panel_path)
    panel = truncate_embargo(panel)
    n_rows = len(panel)
    run_at = datetime.now(timezone.utc).isoformat()

    if smoke:
        directions = ("up",)
        # first 3 test years only → cut fit to date < 2013 so folds 2010-2012 run
        panel = panel[panel["date"] < pd.Timestamp("2013-01-01")].reset_index(drop=True)
        print(f"[SMOKE] one direction (up), first 3 test years, {len(panel)} truncated rows")

    # ── ANTI-MINING LAW (§12): print the candidate count BEFORE any evaluation ──────
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS} "
          f"cells = 2 blocks × 2 directions × 3 horizons  [family={FAMILY}]")

    # ── Trial-budget declaration (runtime log_declared_budget, before any p-value) ──
    if ledger_path is None:
        if smoke:
            ledger_path = Path(tempfile.gettempdir()) / "cpi_ft_smoke_trial_ledger.jsonl"
        else:
            ledger_path = _REPO / "data" / "trial_ledger.jsonl"
    declare_trial_budget(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY} n={N_TRIALS} → {ledger_path}")

    # ── Feature blocks (frozen §12) ────────────────────────────────────────────────
    yahoo_dir = _REPO / "data" / "yahoo"
    cn_dir = _REPO / "data" / "china_sectors"
    panel = attach_ft1_breadth(panel, yahoo_dir, cn_dir)
    panel = attach_ft4_structure(panel)
    panel_d = build_design(panel)   # W4.2 design cols (median-imputes rare NaNs on its set)
    panel_d["date"] = pd.to_datetime(panel_d["date"])
    # Median-impute the FT feature NaNs on the SAME convention build_design uses for CONT.
    for c in FT1_BREADTH_BLOCK + FT4_STRUCTURE_BLOCK:
        panel_d[c] = pd.to_numeric(panel_d[c], errors="coerce")
        med = panel_d[c].median()
        panel_d[c] = panel_d[c].fillna(med if pd.notna(med) else 0.0)

    if smoke:
        # tiny slice: FT1 only, one direction — validates plumbing without real artifacts
        ft1 = run_block(panel_d, FT1_BREADTH_BLOCK, directions=directions,
                        horizons=HORIZONS)
        pvals = [p for (_, _, p) in ft1["cell_pvals"]]
        rej = bh_fdr(pvals, q=FDR_Q)
        for (direction, h, _), r in zip(ft1["cell_pvals"], rej):
            c = ft1["ledger"][direction][f"{h}m"]
            c["bh_pass"] = bool(r)
            c["verdict"] = "PASS" if (c.get("ci_excludes_zero") and c.get("sign_stable") and r) else "FAIL"
        print("[SMOKE] FT1 up ledger:")
        for h in HORIZONS:
            c = ft1["ledger"]["up"][f"{h}m"]
            print(f"  up/{h}m: verdict={c.get('verdict')} dBrier={c.get('delta_brier')} "
                  f"ci90={c.get('ci90')} years+={c.get('years_positive')}/{c.get('n_years')}")
        return {"smoke": True, "ft1_up": ft1["ledger"]["up"]}

    ft1, ft4 = build_ledgers(panel_d, directions=("up", "down"), horizons=HORIZONS)
    n_test_years = ft1["per_fold"].get("up", {}).get("n_folds", 0)

    art_ft1 = build_artifact("ft1_breadth", ft1, panel_epoch=epoch, n_rows=n_rows,
                             n_test_years=n_test_years)
    art_ft4 = build_artifact("ft4_structure", ft4, panel_epoch=epoch, n_rows=n_rows,
                             n_test_years=n_test_years)

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ft1_breadth.json").write_text(json.dumps(art_ft1, indent=2, default=str))
        (out_dir / "ft4_structure.json").write_text(json.dumps(art_ft4, indent=2, default=str))
        print(f"Wrote {out_dir/'ft1_breadth.json'} and {out_dir/'ft4_structure.json'}")

    # Honest run-log summary
    print(f"\nRESULT (panel_epoch={epoch}, n_rows={n_rows}, test_years={n_test_years}):")
    for bkey, art in [("FT1", art_ft1), ("FT4", art_ft4)]:
        for direction in ("up", "down"):
            for h in HORIZONS:
                c = art["ledger"][direction][f"{h}m"]
                print(f"  {bkey} {direction}/{h}m: {c['verdict']:4s}  "
                      f"dBrier={c['delta_brier']}  ci90={c['ci90']}  "
                      f"years+={c['years_positive']}/{c['n_years']}  bh={c['bh_pass']}")
    return {"ft1_breadth": art_ft1, "ft4_structure": art_ft4}


# ═══════════════════════════════════════════════════════════════════════════════
# Batch 2 — FT-2 credit/curve block (PREREGISTRATION.md §13; registered 2026-07-06)
# ═══════════════════════════════════════════════════════════════════════════════

# FROZEN constants (§13; not tuned).  These lists are the guarded spec — tests
# parse them via AST and assert against §13.
FT2_CREDIT_BLOCK = [
    "hy_oas_pctile",
    "hy_oas_d63",
    "curve_10y3m",
]

FAMILY_V1 = "rf.cycle_pattern.ft_v1"   # batch-2 trial-budget family (§13)
N_TRIALS_V1 = 6                         # 2 directions × 3 horizons

_FRED_DIR = _REPO / "data" / "fred"
_HY_OAS_PARQUET = _FRED_DIR / "BAMLH0A0HYM2.parquet"   # col: hy_oas
_CURVE_PARQUET = _FRED_DIR / "T10Y3M.parquet"           # col: spread_10y3m


def _load_fred_series(path: Path, col: str) -> pd.Series:
    """Load a FRED parquet and return the named column as a date-indexed Series (sorted).
    Rows with NaN in the column are dropped (FRED publishes NaN for non-trading days
    on some series; we want the last non-NaN obs <= t)."""
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    s = df[col].dropna().sort_index()
    return s


def _fred_pit(series: pd.Series, t: pd.Timestamp) -> float | None:
    """Point-in-time sampler: return the LAST observation of *series* with index <= *t*.
    Returns None when no such observation exists.  No lookahead by construction."""
    pos = series.index.searchsorted(t, side="right")   # number of entries with index <= t
    if pos == 0:
        return None
    return float(series.iloc[pos - 1])


def _expanding_percentile(series: pd.Series, t: pd.Timestamp) -> float | None:
    """Expanding-window percentile of *series*: fraction of observations (index <= t)
    that are STRICTLY less than the value at t (a.k.a. the empirical CDF at t, using
    observations up to and including t).  Returns None when no obs exist at/before t."""
    pos = series.index.searchsorted(t, side="right")   # entries with index <= t
    if pos == 0:
        return None
    window = series.iloc[:pos].to_numpy(float)
    val = window[-1]   # last obs at or before t
    return float(np.mean(window < val))   # fraction strictly less than val at t


def attach_ft2_credit(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the FT-2 credit/curve block to the panel (§13).

    All three features are TIME-ONLY covariates: they are computed from FRED series
    at each UNIQUE month-end date in the panel, then broadcast to all panel rows for
    that date (direction-invariant). Sampling is PIT-pure: each feature uses
    ``_fred_pit`` to take the last available observation <= t, with no lookahead.

    Features:
      hy_oas_pctile  expanding percentile of BofA HY OAS level at t.
      hy_oas_d63     63-trading-day change in HY OAS level at t.
      curve_10y3m    10y−3m Treasury spread level at t.
    """
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    for c in FT2_CREDIT_BLOCK:
        d[c] = np.nan

    # Load FRED series once — missing files → all NaN (median-imputed downstream).
    hy_oas: pd.Series | None = None
    curve: pd.Series | None = None
    if _HY_OAS_PARQUET.exists():
        try:
            hy_oas = _load_fred_series(_HY_OAS_PARQUET, "hy_oas")
        except Exception:
            pass
    if _CURVE_PARQUET.exists():
        try:
            curve = _load_fred_series(_CURVE_PARQUET, "spread_10y3m")
        except Exception:
            pass

    # Build a lookup from date -> feature values, sampling once per unique month-end.
    unique_dates = sorted(d["date"].unique())

    # Pre-sort hy_oas index once; searchsorted handles the rest.
    feat_rows: dict[pd.Timestamp, dict] = {}
    for t in unique_dates:
        row: dict[str, float | None] = {}

        # hy_oas_pctile — expanding percentile
        row["hy_oas_pctile"] = _expanding_percentile(hy_oas, t) if hy_oas is not None else None

        # hy_oas_d63 — 63-trading-day change
        if hy_oas is not None:
            val_t = _fred_pit(hy_oas, t)
            # 63-trading-day lag: walk backward through the hy_oas index by 63 positions.
            pos = hy_oas.index.searchsorted(t, side="right")   # entries <= t
            if pos >= 64 and val_t is not None:
                val_lag = float(hy_oas.iloc[pos - 64])
                row["hy_oas_d63"] = val_t - val_lag
            else:
                row["hy_oas_d63"] = None
        else:
            row["hy_oas_d63"] = None

        # curve_10y3m — PIT level
        row["curve_10y3m"] = _fred_pit(curve, t) if curve is not None else None

        feat_rows[t] = row

    # Broadcast to panel rows.
    for c in FT2_CREDIT_BLOCK:
        d[c] = d["date"].map(lambda t, _c=c: feat_rows.get(t, {}).get(_c))
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Batch-2 artifact builder and orchestration
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_BLOCK_DEFS_V1 = {
    "ft2_credit": {
        "features": FT2_CREDIT_BLOCK,
        "hy_oas_pctile": (
            "expanding percentile of BofA HY OAS level at t "
            "(data/fred/BAMLH0A0HYM2.parquet 'hy_oas', obs<=t only; PIT)"
        ),
        "hy_oas_d63": (
            "63-trading-day change in HY OAS level at t "
            "(last obs<=t minus obs 63 daily positions prior)"
        ),
        "curve_10y3m": (
            "10y-3m Treasury spread level at t "
            "(data/fred/T10Y3M.parquet 'spread_10y3m', last obs<=t; PIT)"
        ),
    },
}


def build_artifact_v1(block_key: str, block_result: dict, *, panel_epoch: str,
                      n_rows: int, n_test_years: int) -> dict:
    """Assemble the §13 JSON artifact for one FT-2 block."""
    return {
        "schema": "cycle_pattern_ft_trial.v1",
        "registered_ref": "PREREGISTRATION.md §13",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "embargo": "date<2024-01-01",
        "panel_epoch": panel_epoch,
        "n_rows": int(n_rows),
        "n_test_years": int(n_test_years),
        "candidate_count_printed": N_TRIALS_V1,
        "trial_family": FAMILY_V1,
        "config": {
            "first_test_year": FIRST_TEST_YEAR, "embargo_m": EMBARGO_M,
            "boot_draws": BOOT_DRAWS, "boot_seed": BOOT_SEED, "fdr_q": FDR_Q,
            "sign_stability_min": SIGN_STABILITY_MIN, "n_cells_family": N_TRIALS_V1,
            "base_design": list(DESIGN),
        },
        "feature_block": FEATURE_BLOCK_DEFS_V1[block_key],
        "per_fold": block_result["per_fold"],
        "ledger": _restructure_ledger(block_result),
    }


def declare_trial_budget_v1(ledger_path: Path, *, run_at: str) -> None:
    """Register the §13 multiple-testing budget before any p-value (same idiom as batch 1)."""
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(path=ledger_path, family=FAMILY_V1)
    led.log_declared_budget(
        N_TRIALS_V1, family=FAMILY_V1,
        reason=(f"PREREGISTRATION.md §13 cycle_pattern_ft batch 2: 1 block × 2 directions × "
                f"3 horizons = 6 pre-registered cells; run_at={run_at}"),
    )


def run_batch2(panel_path: Path, out_dir: Path, *, smoke: bool = False,
               ledger_path: Path | None = None, write: bool = True) -> dict:
    """Batch-2 runner for FT-2 credit/curve block (§13).  Evaluates 6 cells (2 directions ×
    3 horizons) against the SAME refit baseline under identical folds.  BH-FDR q=0.10
    applied across the 6 cells of THIS batch only.  Does NOT run the real study — call only
    after the pre-registered criteria are committed."""
    panel, epoch = _load_panel(panel_path)
    panel = truncate_embargo(panel)
    n_rows = len(panel)
    run_at = datetime.now(timezone.utc).isoformat()

    if smoke:
        directions: tuple[str, ...] = ("up",)
        panel = panel[panel["date"] < pd.Timestamp("2013-01-01")].reset_index(drop=True)
        print(f"[SMOKE batch2] one direction (up), first 3 test years, {len(panel)} truncated rows")
    else:
        directions = ("up", "down")

    # ANTI-MINING LAW (§13): print candidate count BEFORE any evaluation.
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS_V1} "
          f"cells = 1 block × 2 directions × 3 horizons  [family={FAMILY_V1}]")

    # Trial-budget declaration.
    if ledger_path is None:
        if smoke:
            ledger_path = Path(tempfile.gettempdir()) / "cpi_ft_smoke_trial_ledger_v1.jsonl"
        else:
            ledger_path = _REPO / "data" / "trial_ledger.jsonl"
    declare_trial_budget_v1(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY_V1} n={N_TRIALS_V1} → {ledger_path}")

    # Attach FT-2 credit/curve features (PIT, time-only covariates).
    panel = attach_ft2_credit(panel)
    panel_d = build_design(panel)
    panel_d["date"] = pd.to_datetime(panel_d["date"])

    # Median-impute FT-2 NaNs on the same convention as batch 1.
    for c in FT2_CREDIT_BLOCK:
        panel_d[c] = pd.to_numeric(panel_d[c], errors="coerce")
        med = panel_d[c].median()
        panel_d[c] = panel_d[c].fillna(med if pd.notna(med) else 0.0)

    if smoke:
        # Validates plumbing only — no real artifacts.
        ft2 = run_block(panel_d, FT2_CREDIT_BLOCK, directions=directions, horizons=HORIZONS)
        pvals = [p for (_, _, p) in ft2["cell_pvals"]]
        rej = bh_fdr(pvals, q=FDR_Q)
        for (direction, h, _), r in zip(ft2["cell_pvals"], rej):
            c = ft2["ledger"][direction][f"{h}m"]
            c["bh_pass"] = bool(r)
            c["verdict"] = "PASS" if (c.get("ci_excludes_zero") and c.get("sign_stable") and r) else "FAIL"
        print("[SMOKE batch2] FT2 up ledger:")
        for h in HORIZONS:
            c = ft2["ledger"]["up"][f"{h}m"]
            print(f"  up/{h}m: verdict={c.get('verdict')} dBrier={c.get('delta_brier')} "
                  f"ci90={c.get('ci90')} years+={c.get('years_positive')}/{c.get('n_years')}")
        return {"smoke": True, "ft2_up": ft2["ledger"]["up"]}

    # Full run — BH-FDR across the 6 cells of this batch only (§13).
    ft2 = run_block(panel_d, FT2_CREDIT_BLOCK, directions=directions, horizons=HORIZONS)
    pvals = [p for (_, _, p) in ft2["cell_pvals"]]
    rejects = bh_fdr(pvals, q=FDR_Q)
    for (direction, h, _), rej in zip(ft2["cell_pvals"], rejects):
        cell = ft2["ledger"][direction][f"{h}m"]
        cell["bh_pass"] = bool(rej)
        cell["verdict"] = "PASS" if (
            cell.get("ci_excludes_zero", False)
            and cell.get("sign_stable", False)
            and rej
        ) else "FAIL"

    n_test_years = ft2["per_fold"].get("up", {}).get("n_folds", 0)
    art_ft2 = build_artifact_v1("ft2_credit", ft2, panel_epoch=epoch,
                                n_rows=n_rows, n_test_years=n_test_years)

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ft2_credit.json").write_text(json.dumps(art_ft2, indent=2, default=str))
        print(f"Wrote {out_dir / 'ft2_credit.json'}")

    print(f"\nRESULT (panel_epoch={epoch}, n_rows={n_rows}, test_years={n_test_years}):")
    for direction in ("up", "down"):
        for h in HORIZONS:
            c = art_ft2["ledger"][direction][f"{h}m"]
            print(f"  FT2 {direction}/{h}m: {c['verdict']:4s}  "
                  f"dBrier={c['delta_brier']}  ci90={c['ci90']}  "
                  f"years+={c['years_positive']}/{c['n_years']}  bh={c['bh_pass']}")
    return {"ft2_credit": art_ft2}


def run(panel_path: Path, out_dir: Path, *, smoke: bool = False,
        ledger_path: Path | None = None, write: bool = True,
        batch: int = 1) -> dict:
    """Top-level run dispatcher.  batch=1 → exact batch-1 behaviour (default, unchanged).
    batch=2 → FT-2 credit/curve block only (§13)."""
    if batch == 2:
        return run_batch2(panel_path, out_dir, smoke=smoke,
                          ledger_path=ledger_path, write=write)
    # batch == 1: delegate to the original run logic (unchanged below).
    return _run_batch1(panel_path, out_dir, smoke=smoke,
                       ledger_path=ledger_path, write=write)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CPI feature-trial runner (PREREG §12/§13)")
    ap.add_argument("--panel", default=str(_REPO / "data/hazard/panel_price_c4414dcb.parquet"))
    ap.add_argument("--out-dir", default=str(_REPO / "data/cycle_pattern/ft_trials"))
    ap.add_argument("--smoke", action="store_true",
                    help="tiny slice (up direction, first 3 test years); writes NO real artifacts")
    ap.add_argument("--batch", type=int, choices=[1, 2], default=1,
                    help="1=batch-1 FT-1/FT-4 (§12, default); 2=batch-2 FT-2 credit/curve (§13)")
    args = ap.parse_args(argv)
    run(Path(args.panel), Path(args.out_dir), smoke=args.smoke, write=not args.smoke,
        batch=args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
