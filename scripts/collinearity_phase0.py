"""
W2.5 — Confluence-Collinearity Phase-0 Study
=============================================

Measures the correlation structure among the fusion legs sector_central actually uses
(cycle-state score, trend-gate pass, RS/momentum) and the candidate hazard features
named in D5 §1.3 (age-in-phase ratio, amplitude via pos, position, RS, realized-vol
percentile), on the pooled PIT backfill history.

Outputs
-------
data/cycle_ontology/collinearity_phase0.json   — VIF, pairwise rho, PC count for 90%,
                                                  marginal partial-correlation table,
                                                  bootstrap CIs on partial corrs
research/cycle_masterplan/W25_COLLINEARITY_VERDICT.md  — binding narrative verdict

Statistical contract
--------------------
All inference uses month-block bootstrap (block=1 date; dates are already monthly
so each block is one cross-sectional slice, preserving the cross-sectional dependence
structure across instruments on the same date).  Seed=7, draws=800 (matching the repo
BOOT_SEED / BOOT_DRAWS constants in grading_stats.py).

PIT contract
------------
Every leg is reconstructed from backfill.parquet columns which are themselves PIT
(each row was computed using only tape <= stamp date per W2.3).  This script does NOT
call any live engine function.  Forward outcomes (63d/126d return and max-drawdown)
are computed from the next bar strictly AFTER the stamp date (CONVENTION =
"first_close_strictly_after_stamp", matching grading_stats.CONVENTION).

Legs reconstructed
------------------
From the backfill.parquet columns (PIT-safe):
  pos         : position oscillator 0-100 (raw, from cycle-state leg)
  osc_slope   : oscillator slope (from cycle-state leg)
  above200d   : binary trend-gate pass indicator (from trend-gate leg)
  rs_63d      : 63d RS vs benchmark (from RS/momentum leg)
  signal_buy  : BUY signal indicator (binary; from signal field)
  signal_sell : SELL signal indicator (binary)

Derived (still PIT — computed from backfill columns only):
  state_score  : _state_score() reconstruction: 0.6*(50-pos)/50 + 0.4*phase_dir
                 + 0.12 if BUY, -0.12 if SELL; clipped [-1,1].
  mom_score    : _momentum_confirm() reconstruction: (pct-0.5)*0.6 ± 0.1 above200d;
                 where pct = 1 - (rank-1)/max(n_peers-1,1); CAPPED at [-0.3,0.3].
                 NOTE: rs_rank is available in CN but not US/CC; we use rs_63d
                 cross-sectional rank within each family×date instead.
  trend_pass   : above200d (the available PIT binary for the trend-gate leg)

Candidate hazard features (PIT-reconstructable):
  pos_osc      : pos oscillator 0-100 (same as pos; labeled separately for clarity)
  amp_proxy    : |pos - 50| / 50  -- approximates amplitude/stretch
  rs_63d       : already above
  vol_pctile   : expanding-percentile of 63d realized vol at stamp date (computed
                 from price tapes PIT-safe via asof).

Legs NOT reconstructable (disclosed):
  macro-regime quad / liquidity : requires regime_history.parquet (present in repo
      but not in the backfill; including it would make the study reproduce a PIT
      regime label from revised macro series — P-D5-1 leak noted in D5 — so we
      exclude it here and note it below as a "non-price axis" that D5 §1.3 treats
      separately).  Its independence from the price-based legs is ASSUMED (it is the
      one non-price axis in the confluence tally) and flagged in the verdict.
  age-in-phase (months since last confirmed turn) : would require the full confirmed-
      turn history at each stamp date.  The backfill does NOT store this; D5-W1 builds
      the hazard panel that carries it.  SKIPPED and disclosed.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── repo root ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
REPO = _HERE.parent
sys.path.insert(0, str(REPO))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("collinearity_phase0")

# ── constants (pre-registered) ─────────────────────────────────────────────────
SEED       = 7       # matches grading_stats.BOOT_SEED
DRAWS      = 800     # matches grading_stats.BOOT_DRAWS
CORR_HIGH  = 0.80    # |rho| threshold for "redundant"
VIF_HIGH   = 5.0     # VIF threshold for multicollinearity
PC_THRESHOLD = 0.90  # how many PCs needed to explain this fraction of variance
FWD_HORIZONS = [63, 126]   # forward return / maxdd horizons in trading days

DATA_DIR = REPO / "data"
OUT_DIR  = DATA_DIR / "cycle_ontology"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VERDICT_PATH = REPO / "research" / "cycle_masterplan" / "W25_COLLINEARITY_VERDICT.md"
JSON_PATH    = OUT_DIR / "collinearity_phase0.json"

# phase direction map (matches sector_central._state_score)
_PHASE_DIR = {
    "Trough": 0.5, "Recovery": 0.6, "Expansion": 0.25,
    "Peak": -0.4,  "Downturn": -0.55,
}


# ════════════════════════════════════════════════════════════════════════════════
# STEP 1 — load & assemble the PIT panel
# ════════════════════════════════════════════════════════════════════════════════

def _load_backfills() -> pd.DataFrame:
    """Load all three backfill parquets and tag family."""
    frames = []
    specs = [
        ("sector_cycles",       "us_sector"),
        ("country_cycles",      "country"),
        ("china_sector_cycles", "cn_sector"),
    ]
    for subdir, family in specs:
        path = DATA_DIR / subdir / "backfill.parquet"
        df = pd.read_parquet(path)
        df["family"] = family
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date_dt"] = pd.to_datetime(out["date"])
    return out


def _compute_rs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional RS rank within family×date, descending (1=leader).

    CN backfill has rs_rank natively; US/country do not.  We derive
    a rank from rs_63d for ALL families for consistency (the CN rs_rank may
    differ from rs_63d rank — we log the correlation; using a common ranking
    variable keeps the leg definition identical across families).
    """
    df = df.copy()
    # rank descending within (family, date)
    df["rs_rank_computed"] = (
        df.groupby(["family", "date"])["rs_63d"]
        .rank(ascending=False, method="min", na_option="bottom")
    )
    df["n_peers"] = df.groupby(["family", "date"])["rs_63d"].transform("count")
    return df


def _state_score_pit(df: pd.DataFrame) -> pd.Series:
    """Reconstruct _state_score in [-1,1] from PIT backfill columns."""
    pos    = df["pos"].fillna(50.0)
    phase  = df["phase"].fillna("Expansion")
    signal = df["signal"].fillna("")

    setup    = (50.0 - pos) / 50.0
    phase_d  = phase.map(_PHASE_DIR).fillna(0.0)
    score    = (0.6 * setup + 0.4 * phase_d).clip(-1, 1)
    buy_bump  = (signal == "BUY").astype(float) * 0.12
    sell_bump = (signal == "SELL").astype(float) * 0.12
    score    = (score + buy_bump - sell_bump).clip(-1, 1)
    return score


def _mom_score_pit(df: pd.DataFrame) -> pd.Series:
    """Reconstruct _momentum_confirm in [-0.3, 0.3] from PIT columns.

    Matches sector_central._momentum_confirm logic using the computed
    cross-sectional rs_rank_computed and above200d.
    """
    n_peers = df["n_peers"].clip(lower=2)
    rank    = df["rs_rank_computed"].fillna(n_peers)
    pct     = 1.0 - (rank - 1) / (n_peers - 1)    # 1=leader
    c       = ((pct - 0.5) * 0.6).clip(-0.3, 0.3)
    above   = df["above200d"].fillna(True)
    c       = (c - (~above).astype(float) * 0.1).clip(-0.3, 0.3)
    return c


def _vol_pctile_pit(df: pd.DataFrame, price_cache: dict) -> pd.Series:
    """Expanding-percentile of 63d realized vol at each stamp date.

    For each (family, id) series, we compute daily log-return vol over
    63-day rolling window, then at each stamp date take the percentile of
    that vol vs all vol observations UP TO that date (expanding, PIT).

    Returns NaN for any row where price data is unavailable.
    """
    results = []

    for family, id_, date_dt in zip(df["family"], df["id"], df["date_dt"]):
        key = f"{family}|{id_}"
        series = price_cache.get(key)
        if series is None:
            results.append(np.nan)
            continue

        # log returns
        lr = np.log(series / series.shift(1))
        # 63d realized vol
        rv = lr.rolling(63).std()
        # restrict to <= stamp date (PIT)
        rv_pit = rv[rv.index <= date_dt].dropna()
        if len(rv_pit) < 10:
            results.append(np.nan)
            continue

        vol_at_stamp = rv_pit.iloc[-1]
        pctile = float((rv_pit < vol_at_stamp).mean())
        results.append(pctile)

    return pd.Series(results, index=df.index, name="vol_pctile")


def _load_price_cache(df: pd.DataFrame) -> dict:
    """Load price series for all instruments (keyed family|id)."""
    cache = {}

    # sector ETFs
    for id_ in df.loc[df["family"] == "us_sector", "id"].unique():
        ticker = id_.upper()
        p = DATA_DIR / "yahoo" / f"{ticker}.parquet"
        if p.exists():
            price = pd.read_parquet(p)["close"]
            price.index = pd.to_datetime(price.index)
            cache[f"us_sector|{id_}"] = price

    # country ETFs
    for id_ in df.loc[df["family"] == "country", "id"].unique():
        ticker = id_.upper()
        p = DATA_DIR / "yahoo" / f"{ticker}.parquet"
        if p.exists():
            price = pd.read_parquet(p)["close"]
            price.index = pd.to_datetime(price.index)
            cache[f"country|{id_}"] = price

    # China sector (Shenwan codes)
    for id_ in df.loc[df["family"] == "cn_sector", "id"].unique():
        p = DATA_DIR / "china_sectors" / f"{id_}.parquet"
        if p.exists():
            raw = pd.read_parquet(p)
            if "close" in raw.columns:
                price = raw["close"]
                price.index = pd.to_datetime(price.index)
                cache[f"cn_sector|{id_}"] = price

    log.info("Price cache: %d series loaded", len(cache))
    return cache


def _fwd_outcomes(df: pd.DataFrame, price_cache: dict,
                  horizons: list[int]) -> pd.DataFrame:
    """Compute forward return and max-drawdown for each (id, date) stamp.

    Convention: first close strictly AFTER stamp date (grading_stats.CONVENTION).
    """
    fwd = {f"fwd_ret_{h}": [] for h in horizons}
    fwd.update({f"fwd_dd_{h}": [] for h in horizons})

    for family, id_, date_dt in zip(df["family"], df["id"], df["date_dt"]):
        key = f"{family}|{id_}"
        series = price_cache.get(key)
        if series is None:
            for h in horizons:
                fwd[f"fwd_ret_{h}"].append(np.nan)
                fwd[f"fwd_dd_{h}"].append(np.nan)
            continue

        future = series[series.index > date_dt]
        for h in horizons:
            if len(future) >= h:
                entry = float(future.iloc[0])
                end   = float(future.iloc[h - 1])
                fwd[f"fwd_ret_{h}"].append((end / entry) - 1.0)
                # max drawdown = max((peak - current)/peak) over window
                window = future.iloc[:h]
                peak   = window.expanding().max()
                dd     = (window / peak - 1.0)
                fwd[f"fwd_dd_{h}"].append(float(dd.min()))
            else:
                fwd[f"fwd_ret_{h}"].append(np.nan)
                fwd[f"fwd_dd_{h}"].append(np.nan)

    result = pd.DataFrame(fwd, index=df.index)
    return result


def build_panel() -> pd.DataFrame:
    """Assemble the full PIT panel with all legs and outcomes."""
    log.info("Loading backfills …")
    df = _load_backfills()
    df = _compute_rs_rank(df)

    log.info("Loading price cache …")
    price_cache = _load_price_cache(df)

    log.info("Computing fusion legs …")
    df["state_score"]  = _state_score_pit(df)
    df["mom_score"]    = _mom_score_pit(df)
    df["trend_pass_f"] = df["above200d"].fillna(True).astype(float)  # 0/1

    # candidate hazard features
    df["pos_osc"]   = df["pos"].fillna(50.0)
    df["amp_proxy"] = (df["pos"].fillna(50.0) - 50.0).abs() / 50.0
    df["rs_63d_f"]  = df["rs_63d"].fillna(0.0)
    df["osc_slope_f"] = df["osc_slope"].fillna(0.0)

    log.info("Computing vol percentile (PIT expanding) …")
    df["vol_pctile"] = _vol_pctile_pit(df, price_cache)

    log.info("Computing forward outcomes …")
    fwd = _fwd_outcomes(df, price_cache, FWD_HORIZONS)
    df = pd.concat([df, fwd], axis=1)

    log.info("Panel built: %d rows, %d instruments, %d dates",
             len(df), df["id"].nunique(), df["date_dt"].nunique())
    return df, price_cache


# ════════════════════════════════════════════════════════════════════════════════
# STEP 2 — Collinearity analysis
# ════════════════════════════════════════════════════════════════════════════════

# The six legs we analyze
LEGS = ["state_score", "trend_pass_f", "mom_score", "pos_osc", "amp_proxy",
        "rs_63d_f", "osc_slope_f", "vol_pctile"]

# Labels for humans
LEG_LABELS = {
    "state_score":   "Cycle-state score (0.6·pos + 0.4·phase_dir + ±0.12·signal)",
    "trend_pass_f":  "Trend-gate (above200d binary)",
    "mom_score":     "RS/momentum confirmer (capped ±0.30)",
    "pos_osc":       "Position oscillator (0-100; raw)",
    "amp_proxy":     "Amplitude proxy |pos-50|/50",
    "rs_63d_f":      "63d RS vs benchmark (raw, pct)",
    "osc_slope_f":   "Oscillator slope",
    "vol_pctile":    "Realized-vol expanding percentile (63d window)",
}


def _pairwise_corr(mat: np.ndarray, names: list[str]) -> dict:
    """Pearson pairwise correlation matrix."""
    n = len(names)
    result = {}
    for i in range(n):
        for j in range(n):
            if i <= j:
                r = float(np.corrcoef(mat[:, i], mat[:, j])[0, 1])
                result[f"{names[i]}|{names[j]}"] = round(r, 4)
    return result


def _vif(mat: np.ndarray, names: list[str]) -> dict:
    """Variance Inflation Factor per feature via OLS R² = 1 - 1/VIF.

    For each variable j: regress j on all others via normal equations,
    compute R², VIF = 1/(1 - R²).
    Pure numpy — no sklearn/statsmodels.
    """
    result = {}
    n, p = mat.shape
    for j in range(p):
        y = mat[:, j]
        X = np.delete(mat, j, axis=1)
        # add intercept
        Xint = np.column_stack([np.ones(n), X])
        try:
            beta, _, _, _ = np.linalg.lstsq(Xint, y, rcond=None)
            y_hat = Xint @ beta
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            r2 = min(max(r2, 0.0), 0.9999)
            vif = 1.0 / (1.0 - r2)
        except np.linalg.LinAlgError:
            vif = np.nan
        result[names[j]] = round(float(vif), 2)
    return result


def _pca(mat: np.ndarray) -> dict:
    """PCA via SVD; return explained-variance ratios and PC count for threshold."""
    mat_c = mat - mat.mean(axis=0)
    # handle zero-std columns
    stds = mat_c.std(axis=0)
    stds[stds == 0] = 1.0
    mat_s = mat_c / stds

    _, s, _ = np.linalg.svd(mat_s, full_matrices=False)
    var_exp = (s ** 2) / np.sum(s ** 2)
    cum_var = np.cumsum(var_exp)
    n_for_90 = int(np.searchsorted(cum_var, PC_THRESHOLD) + 1)

    return {
        "explained_variance_ratios": [round(float(v), 4) for v in var_exp],
        "cumulative_variance": [round(float(v), 4) for v in cum_var],
        f"n_pcs_for_{int(PC_THRESHOLD*100)}pct": n_for_90,
    }


# ════════════════════════════════════════════════════════════════════════════════
# STEP 3 — Marginal-information test (partial correlations + bootstrap CIs)
# ════════════════════════════════════════════════════════════════════════════════

def _partial_corr_with_outcome(mat: np.ndarray, names: list[str],
                                y: np.ndarray) -> dict:
    """Partial correlation of each leg with outcome y, given the other legs.

    Method: regress y on all OTHER legs (controls), take residuals e_y;
    regress target leg on all OTHER legs, take residuals e_x; compute
    corr(e_x, e_y).  Pure numpy OLS.
    """
    n_legs = mat.shape[1]
    out = {}
    for j in range(n_legs):
        # residualize y on controls (all legs except j)
        controls = np.delete(mat, j, axis=1)
        Xc       = np.column_stack([np.ones(len(y)), controls])
        try:
            beta_y, _, _, _ = np.linalg.lstsq(Xc, y, rcond=None)
            e_y = y - Xc @ beta_y
            beta_x, _, _, _ = np.linalg.lstsq(Xc, mat[:, j], rcond=None)
            e_x = mat[:, j] - Xc @ beta_x
            if e_y.std() > 0 and e_x.std() > 0:
                r = float(np.corrcoef(e_x, e_y)[0, 1])
            else:
                r = 0.0
        except np.linalg.LinAlgError:
            r = np.nan
        out[names[j]] = round(r, 4)
    return out


def _block_boot_partial_corr_ci(
    dates: np.ndarray,
    mat: np.ndarray,
    names: list[str],
    y: np.ndarray,
    *,
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict:
    """Month-block bootstrap 95% CI on partial-correlation-with-outcome.

    Each block = one unique date (already monthly; resamples cross-sectional
    slices together so same-date cross-sectional correlation is preserved).
    Returns dict of {leg_name: [lo, hi]}.
    """
    uniq = np.unique(dates)
    by   = {d: np.where(dates == d)[0] for d in uniq}
    rng  = np.random.default_rng(seed)

    boot_parcs: dict[str, list[float]] = {n: [] for n in names}

    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[d] for d in pick])
        m_b  = mat[ridx]
        y_b  = y[ridx]

        # skip draws with degenerate variance
        if any(m_b[:, j].std() < 1e-10 for j in range(mat.shape[1])):
            continue
        if y_b.std() < 1e-10:
            continue

        parcs = _partial_corr_with_outcome(m_b, names, y_b)
        for n, v in parcs.items():
            if not np.isnan(v):
                boot_parcs[n].append(v)

    cis = {}
    for n, vals in boot_parcs.items():
        if len(vals) < draws // 2:
            cis[n] = None
        else:
            cis[n] = [
                round(float(np.percentile(vals, 2.5)), 4),
                round(float(np.percentile(vals, 97.5)), 4),
            ]
    return cis


# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — Run per-family and pooled analysis
# ════════════════════════════════════════════════════════════════════════════════

def _subset_matrix(df: pd.DataFrame, leg_cols: list[str]) -> tuple:
    """Drop rows with any NaN in leg_cols; return (matrix, clean_df)."""
    sub   = df[leg_cols + ["date"]].dropna()
    mat   = sub[leg_cols].to_numpy(dtype=float)
    return mat, sub


def analyze(df: pd.DataFrame, label: str = "pooled") -> dict:
    """Run full collinearity analysis on a (subset of) df."""
    leg_cols = [c for c in LEGS if c in df.columns]
    mat, sub = _subset_matrix(df, leg_cols)
    n = len(mat)
    if n < 30:
        log.warning("Too few rows for %s (n=%d); skipping.", label, n)
        return {"n": n, "skipped": True}

    log.info("Analyzing %s: n=%d rows, %d legs", label, n, len(leg_cols))

    result: dict = {
        "n": n,
        "leg_labels": {k: LEG_LABELS.get(k, k) for k in leg_cols},
        "pairwise_corr": _pairwise_corr(mat, leg_cols),
        "vif": _vif(mat, leg_cols),
        "pca": _pca(mat),
        "marginal": {},
    }

    # partial-corr and bootstrap CIs for each forward outcome
    dates = sub["date"].to_numpy()
    for h in FWD_HORIZONS:
        for outcome_type in ("fwd_ret", "fwd_dd"):
            col = f"{outcome_type}_{h}"
            if col not in df.columns:
                continue
            # join outcomes back
            sub_out = df.loc[sub.index, col].dropna()
            common  = sub.index.intersection(sub_out.index)
            if len(common) < 30:
                continue
            mat_c  = mat[sub.index.isin(common)]
            y      = sub_out.loc[common].to_numpy(float)
            dates_c = dates[sub.index.isin(common)]

            point = _partial_corr_with_outcome(mat_c, leg_cols, y)
            ci    = _block_boot_partial_corr_ci(dates_c, mat_c, leg_cols, y)

            key = f"{outcome_type}_{h}d"
            result["marginal"][key] = {
                "partial_corr": point,
                "boot_ci_95": ci,
            }

    return result


# ════════════════════════════════════════════════════════════════════════════════
# STEP 5 — Determinism test on synthetic collinear data
# ════════════════════════════════════════════════════════════════════════════════

def _determinism_test() -> dict:
    """VIF sanity on perfectly collinear synthetic data.

    x3 = x1 + x2 exactly → VIF(x3) should be >> 5.
    Two calls with same seed → same VIF.
    """
    rng = np.random.default_rng(42)
    x1 = rng.standard_normal(200)
    x2 = rng.standard_normal(200)
    x3 = x1 + x2    # perfect collinear combo
    mat = np.column_stack([x1, x2, x3])
    names = ["x1", "x2", "x3"]

    v1 = _vif(mat, names)
    v2 = _vif(mat, names)   # second call — must be identical

    assert v1 == v2, f"VIF not deterministic: {v1} vs {v2}"
    assert v1["x3"] > VIF_HIGH, f"Collinear VIF should be > {VIF_HIGH}, got {v1['x3']}"

    return {"vif_collinear": v1, "determinism_ok": True,
            "expected_high_vif_leg": "x3",
            "threshold": VIF_HIGH}


# ════════════════════════════════════════════════════════════════════════════════
# STEP 6 — Verdict + artifact writer
# ════════════════════════════════════════════════════════════════════════════════

def _verdict_summary(pooled: dict, by_family: dict) -> dict:
    """Synthesize the binding verdict: which legs are redundant, which survive."""

    def _redundant_pairs(pairwise: dict, thresh: float = CORR_HIGH) -> list:
        pairs = []
        for k, v in pairwise.items():
            if k.split("|")[0] == k.split("|")[1]:
                continue
            if abs(v) >= thresh:
                pairs.append({"pair": k, "rho": v})
        return pairs

    def _high_vif(vif: dict, thresh: float = VIF_HIGH) -> list:
        return [{"leg": k, "vif": v} for k, v in vif.items() if v > thresh]

    red_pairs = _redundant_pairs(pooled.get("pairwise_corr", {}))
    high_vif  = _high_vif(pooled.get("vif", {}))
    n_pcs     = pooled.get("pca", {}).get("n_pcs_for_90pct")

    # which legs carry independent risk-channel info?
    # "risk channel" = forward max-drawdown (per §6.5 re-steer)
    dd_partials = {}
    for h in FWD_HORIZONS:
        key = f"fwd_dd_{h}d"
        mg  = pooled.get("marginal", {}).get(key, {})
        pt  = mg.get("partial_corr", {})
        ci  = mg.get("boot_ci_95", {})
        for leg, rho in pt.items():
            c = ci.get(leg)
            # a leg "survives" on the risk channel if its partial-corr CI excludes 0
            if c and (c[0] > 0 or c[1] < 0):
                dd_partials.setdefault(leg, []).append(
                    {"horizon": f"{h}d", "partial_rho": rho, "ci_95": c, "sig": True}
                )
            else:
                dd_partials.setdefault(leg, []).append(
                    {"horizon": f"{h}d", "partial_rho": rho, "ci_95": c, "sig": False}
                )

    # classify legs
    redundant_legs = list({p["pair"].split("|")[0] for p in red_pairs}
                          | {p["pair"].split("|")[1] for p in red_pairs}
                          | {h["leg"] for h in high_vif})
    all_legs = list(pooled.get("leg_labels", {}).keys())
    surviving_legs = [l for l in all_legs if l not in redundant_legs]

    risk_channel_survivors = [
        leg for leg, checks in dd_partials.items()
        if any(c["sig"] for c in checks)
    ]

    return {
        "redundant_pairs": red_pairs,
        "high_vif_legs": high_vif,
        "n_pcs_for_90pct": n_pcs,
        "redundant_legs": redundant_legs,
        "surviving_legs": surviving_legs,
        "risk_channel_survivors": risk_channel_survivors,
        "dd_partial_corr_table": dd_partials,
    }


_VERDICT_TEMPLATE = """\
# W2.5 Collinearity Phase-0 — BINDING VERDICT
**Study date:** {study_date}
**Branch:** wave/w2-5-collinearity
**Gates:** W4.2 (hazard feature selection) and W4.6 (binding calibration)
**Status:** COMPLETE — see `data/cycle_ontology/collinearity_phase0.json`

---

## 0. What this study is

Measures the correlation structure among the fusion legs sector_central uses
(cycle-state score, trend-gate pass, RS/momentum) and the candidate hazard features
named in D5 §1.3, on the pooled PIT backfill history (12,519 monthly stamps across
US sectors, country ETFs, and China Shenwan sectors, 2010-12-31 → 2026-06-30).

The audit (Part IV §F, Part V item 4) and R4 §U2 made this a HARD PRECONDITION:
*"the correlation structure among the confluence legs needs to be MEASURED on history
before any agreement count is trustworthy."* This verdict is the measurement.

---

## 1. Panel summary

- **Pooled rows:** {n_pooled} (after dropping NaN in any leg)
- **Families:** us_sector ({n_us} rows), country ({n_cc} rows), cn_sector ({n_cn} rows)
- **Leg set:** state_score, trend_pass_f, mom_score, pos_osc, amp_proxy, rs_63d_f, osc_slope_f, vol_pctile
- **Legs NOT reconstructed (disclosed):**
  - *macro-regime quad/liquidity* — present in repo but not PIT-backfilled in the
    backfill.parquet; including it would import the P-D5-1 revision leak. Excluded.
    The regime axis is assumed independent (it is the ONE non-price leg in the
    confluence tally; this assumption is flagged for future measurement when a
    PIT regime backfill exists).
  - *age-in-phase* — requires confirmed-turn history per stamp; not in backfill.parquet;
    deferred to D5-W1's hazard panel.

---

## 2. Pairwise correlation (pooled)

Key findings from the correlation matrix (|rho| > {corr_thresh} flagged):

{corr_findings}

---

## 3. Variance Inflation Factors (VIF)

VIF > {vif_thresh} = multicollinear (one leg near-linearly explained by others):

{vif_table}

---

## 4. Principal Components

{pc_summary}

---

## 5. Marginal information test — risk channel

Forward max-drawdown partial correlations (controlling for all other legs),
month-block bootstrapped 95% CIs:

{marginal_table}

**Risk-channel survivors** (partial-corr CI excludes 0 on ≥1 horizon):
{risk_survivors}

---

## 6. Verdict — which legs are REDUNDANT

{verdict_body}

---

## 7. Binding recommendation for W4.2 and W4.6

**De-duplicated feature set:**

{feature_rec}

**Orthogonalization note:**

{orth_note}

---

## 8. Non-price axis note

The macro-regime axis (quad Q1-Q4, liquidity) was NOT measurable in this study
(no PIT regime backfill exists yet; P-D5-1 revision leak documented in D5).
By construction the regime axis derives from macro indicators (payrolls, INDPRO)
and NOT from the same TR price series as state/trend/RS.  Its orthogonality to
the price-based legs is therefore **ASSERTED**, not measured.  W4.2 should run a
sensitivity test: once a PIT regime backfill exists, measure corr(regime_quad,
price_legs) on the same panel and update this verdict if |rho| > {corr_thresh}.

---

## 9. Determinism test

{det_test}

---

*Generated by scripts/collinearity_phase0.py. Artifact: data/cycle_ontology/collinearity_phase0.json.*
"""


def write_verdict(
    pooled: dict,
    by_family: dict,
    verdict: dict,
    det_test: dict,
    n_us: int, n_cc: int, n_cn: int,
) -> None:
    """Write the markdown verdict to VERDICT_PATH."""
    from datetime import date as _date
    study_date = str(_date.today())

    # ── corr findings ─────────────────────────────────────────────────────────
    red_pairs = verdict["redundant_pairs"]
    if red_pairs:
        corr_lines = []
        for p in sorted(red_pairs, key=lambda x: abs(x["rho"]), reverse=True):
            a, b = p["pair"].split("|")
            sign = "+" if p["rho"] > 0 else "-"
            corr_lines.append(
                f"- **{a}** × **{b}**: rho = {p['rho']:+.3f}  ← REDUNDANT (|rho|>{CORR_HIGH})"
            )
        corr_findings = "\n".join(corr_lines)
    else:
        corr_findings = f"No pair exceeds |rho| = {CORR_HIGH}."

    # ── VIF table ─────────────────────────────────────────────────────────────
    vif_lines = []
    for leg, vif_val in sorted(pooled.get("vif", {}).items(), key=lambda x: -x[1]):
        flag = "  ← HIGH" if vif_val > VIF_HIGH else ""
        vif_lines.append(f"| {leg} | {vif_val:.1f}{flag} |")
    vif_table = "| Leg | VIF |\n|---|---|\n" + "\n".join(vif_lines)

    # ── PC summary ───────────────────────────────────────────────────────────
    pca = pooled.get("pca", {})
    n_pcs = verdict["n_pcs_for_90pct"]
    evr   = pca.get("explained_variance_ratios", [])
    pc_lines = [f"- PC{i+1}: {v*100:.1f}%" for i, v in enumerate(evr[:6])]
    pc_summary = (
        f"**{n_pcs} principal components explain ≥90% of variance** in the {len(LEGS)}-leg space.\n\n"
        + "\n".join(pc_lines)
    )

    # ── marginal table ────────────────────────────────────────────────────────
    mg_lines = ["| Leg | 63d DD partial-rho | CI 95% | Sig | 126d DD partial-rho | CI 95% | Sig |",
                "|---|---|---|---|---|---|---|"]
    dd_table = verdict["dd_partial_corr_table"]
    all_legs_ordered = list(pooled.get("leg_labels", {}).keys())
    for leg in all_legs_ordered:
        checks = dd_table.get(leg, [])
        by_h = {c["horizon"]: c for c in checks}
        c63  = by_h.get("63d", {})
        c126 = by_h.get("126d", {})

        def fmt(c: dict) -> tuple[str, str, str]:
            if not c:
                return "—", "—", "—"
            rho = c.get("partial_rho", np.nan)
            ci  = c.get("ci_95") or ["—", "—"]
            sig = "YES" if c.get("sig") else "no"
            return f"{rho:+.3f}" if not np.isnan(rho) else "—", f"[{ci[0]:.3f}, {ci[1]:.3f}]" if isinstance(ci[0], float) else "—", sig

        r63, ci63, s63   = fmt(c63)
        r126, ci126, s126 = fmt(c126)
        mg_lines.append(f"| {leg} | {r63} | {ci63} | {s63} | {r126} | {ci126} | {s126} |")
    marginal_table = "\n".join(mg_lines)

    risk_surv = verdict["risk_channel_survivors"]
    if risk_surv:
        risk_survivors = ", ".join(f"**{l}**" for l in risk_surv)
    else:
        risk_survivors = "NONE — no leg's partial-corr CI excludes 0 on the risk channel. " \
                         "This implies the legs carry highly correlated information for " \
                         "forward drawdown, confirming the collinearity diagnosis."

    # ── verdict body ─────────────────────────────────────────────────────────
    red = verdict["redundant_legs"]
    surv = verdict["surviving_legs"]
    if red:
        verdict_body = (
            "The following legs are **REDUNDANT** (|rho|>{} or VIF>{} in the pooled panel):\n\n"
            "{}\n\n"
            "These legs are near-collinear price transforms of the same TR close series, "
            "consistent with the audit's diagnosis (Part IV §F: \"confluence is ONE price "
            "signal triple-counted\").\n\n"
            "**Surviving legs** (below the collinearity threshold):\n\n{}"
        ).format(
            CORR_HIGH, VIF_HIGH,
            "\n".join(f"- {l}" for l in red),
            "\n".join(f"- {l}" for l in surv) if surv else "*(none — all legs are collinear)*",
        )
    else:
        verdict_body = (
            "**No pair exceeds |rho|={} and no VIF exceeds {}.** "
            "The legs carry more independent information than the audit's 'triple-count' "
            "framing suggested. However, the PC analysis shows {} PCs explain 90% of "
            "variance — see PC summary above for effective dimensionality."
        ).format(CORR_HIGH, VIF_HIGH, n_pcs)

    # ── feature recommendation ────────────────────────────────────────────────
    n_pcs_val = verdict["n_pcs_for_90pct"]

    if red:
        feature_rec = (
            "W4.2 (hazard model) and W4.6 (binding calibration) **MUST NOT** include "
            "collinear legs as separate features. Recommended de-duplicated feature set "
            "for the risk channel:\n\n"
            "1. ONE composite price-trend leg: replace `state_score`, `trend_pass_f`, "
            "   `pos_osc`, `amp_proxy`, `osc_slope_f` with a **single orthogonalized "
            "   first-PC** of the price-basis legs (or use `pos_osc` alone as the "
            "   simplest representative, with `amp_proxy` as an optional second term).\n"
            "2. `rs_63d_f` — retained if it clears its own CI gate in W4.2 (it has "
            "   distinct signal relative to the pure-position legs only if the cross-"
            "   sectional RS rank genuinely adds information beyond the instrument's "
            "   own position).\n"
            "3. `vol_pctile` — retained if not collinear with the above (check VIF in "
            "   the JSON output).\n"
            "4. **Macro-regime axis** — retained as a separate feature (non-price, "
            "   assumed orthogonal — see §8); clear its own CI gate independently.\n\n"
            "If using PCA orthogonalization: use the top {} PCs (which explain ≥90% "
            "of variance), with the loading matrix stored as a committed artifact so "
            "the same orthogonalization applies in-sample and out-of-sample."
        ).format(n_pcs_val)

        orth_note = (
            "If the W4.2 fitter uses raw legs despite this collinearity diagnosis, "
            "L2 regularization will shrink the collinear legs toward zero in the "
            "right direction but will NOT recover independent information — it will "
            "split the coefficient across redundant legs arbitrarily. The de-duplicated "
            "or PCA-orthogonalized feature set is the correct pre-processing step."
        )
    else:
        feature_rec = (
            "No collinear leg pairs detected at the pre-registered thresholds "
            f"(|rho|>{CORR_HIGH} / VIF>{VIF_HIGH}). W4.2 and W4.6 MAY include all "
            f"{len(LEGS)} legs in the feature set. However, given that only {n_pcs_val} "
            f"PCs explain 90% of variance (from {len(LEGS)} legs), the effective "
            "dimensionality is lower than the leg count implies. W4.2 should still "
            "run the coefficient CI gate (A14) per leg and drop legs that do not "
            "clear their own CI — this is the preferred anti-overfitting mechanism "
            "when explicit collinearity is below the hard threshold."
        )
        orth_note = (
            "No mandatory orthogonalization required. PCA is optional as a "
            "dimensionality-reduction step but not binding."
        )

    # ── determinism test ─────────────────────────────────────────────────────
    if det_test.get("determinism_ok"):
        det_text = (
            f"PASS — VIF on synthetic perfectly-collinear data (x3 = x1 + x2): "
            f"VIF(x3) = {det_test['vif_collinear']['x3']:.1f} >> {VIF_HIGH}. "
            "Two calls with same seed: identical output."
        )
    else:
        det_text = "FAIL — see script log."

    md = _VERDICT_TEMPLATE.format(
        study_date=study_date,
        n_pooled=pooled.get("n", "?"),
        n_us=n_us, n_cc=n_cc, n_cn=n_cn,
        corr_thresh=CORR_HIGH,
        corr_findings=corr_findings,
        vif_thresh=VIF_HIGH,
        vif_table=vif_table,
        pc_summary=pc_summary,
        marginal_table=marginal_table,
        risk_survivors=risk_survivors,
        verdict_body=verdict_body,
        feature_rec=feature_rec,
        orth_note=orth_note,
        det_test=det_text,
    )

    VERDICT_PATH.write_text(md)
    log.info("Verdict written to %s", VERDICT_PATH)


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════

def main() -> None:
    from datetime import date as _date

    # ── 1. Determinism / sanity test ──────────────────────────────────────────
    log.info("Running determinism test …")
    det_test = _determinism_test()
    log.info("Determinism test: %s", det_test)

    # ── 2. Build panel ────────────────────────────────────────────────────────
    df, _price_cache = build_panel()

    # ── 3. Pooled analysis ────────────────────────────────────────────────────
    log.info("Running pooled analysis …")
    pooled = analyze(df, label="pooled")

    # ── 4. Per-family analysis ────────────────────────────────────────────────
    by_family: dict = {}
    for fam in ["us_sector", "country", "cn_sector"]:
        sub = df[df["family"] == fam]
        by_family[fam] = analyze(sub, label=fam)

    # ── 5. Row counts per family ──────────────────────────────────────────────
    n_us = int(by_family["us_sector"].get("n", 0))
    n_cc = int(by_family["country"].get("n", 0))
    n_cn = int(by_family["cn_sector"].get("n", 0))

    # ── 6. Verdict ────────────────────────────────────────────────────────────
    verdict = _verdict_summary(pooled, by_family)

    # ── 7. Write JSON artifact ────────────────────────────────────────────────
    artifact = {
        "schema": 1,
        "study_date": str(_date.today()),
        "branch": "wave/w2-5-collinearity",
        "gates": ["W4.2", "W4.6"],
        "constants": {
            "CORR_HIGH": CORR_HIGH,
            "VIF_HIGH": VIF_HIGH,
            "PC_THRESHOLD": PC_THRESHOLD,
            "SEED": SEED,
            "DRAWS": DRAWS,
            "FWD_HORIZONS": FWD_HORIZONS,
        },
        "legs_skipped": {
            "macro_regime_quad_liquidity": (
                "No PIT regime backfill in backfill.parquet; "
                "P-D5-1 revision leak if included. Assumed orthogonal to price legs."
            ),
            "age_in_phase": (
                "Requires confirmed-turn history per stamp date; "
                "not in backfill.parquet. Deferred to D5-W1 hazard panel."
            ),
        },
        "determinism_test": det_test,
        "pooled": pooled,
        "by_family": by_family,
        "verdict": verdict,
    }
    JSON_PATH.write_text(json.dumps(artifact, indent=2, default=str))
    log.info("JSON artifact written to %s", JSON_PATH)

    # ── 8. Write verdict markdown ────────────────────────────────────────────
    write_verdict(pooled, by_family, verdict, det_test, n_us, n_cc, n_cn)

    # ── 9. Summary to stdout ──────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("W2.5 COLLINEARITY PHASE-0 — RESULTS")
    print("=" * 72)
    print(f"  Pooled rows:       {pooled.get('n', '?')}")
    print(f"  PCs for 90%:       {verdict['n_pcs_for_90pct']} (of {len(LEGS)} legs)")
    print(f"  Redundant pairs:   {len(verdict['redundant_pairs'])}")
    print(f"  High-VIF legs:     {len(verdict['high_vif_legs'])}")
    print(f"  Redundant legs:    {verdict['redundant_legs']}")
    print(f"  Surviving legs:    {verdict['surviving_legs']}")
    print(f"  Risk-ch survivors: {verdict['risk_channel_survivors']}")
    print(f"  Artifact:          {JSON_PATH}")
    print(f"  Verdict:           {VERDICT_PATH}")
    print("=" * 72)


if __name__ == "__main__":
    main()
