"""CPI TR-1 next-phase transition-model runner — family ``cycle_pattern_tr`` (PREREGISTRATION.md §16).

RESEARCH TRACK (masterplan §5, capability C4 "what comes next"). FROZEN by §16: a
multinomial (softmax) model of the NEXT phase, gated against a family-stratified empirical
transition matrix. NEW TARGET and NEW capacity — NOT an additive-feature trial on the pooled
hazard logistic (the CPI-018 suspension does not apply). Nothing here touches a page; the
deliverable is an honest verdict against the pre-registered gates.

WHAT THIS DOES (all parameters frozen in §16; none tuned here)
  1. Loads the price-basis person-period panel ``data/hazard/panel_price_c4414dcb.parquet``
     and TRUNCATES to rows dated BEFORE 2024-01-01 (holdout embargo, §16 — reusing the §12
     ``truncate_embargo`` object). Labels are derived AFTER truncation, so boundary rows
     lose their forward chain and drop out via the NaN convention (the §14 order of
     operations — the confirmatory window stays untouched).

  2. Substrate: ``phase_v2`` per (id, month-end) via the W4.4 ``derive_phase`` verbatim
     (NaN pos_osc → NaN phase → row excluded, §16). Labels:
       next_phase_1m = phase_v2 at the NEXT consecutive month-end;
       next_phase_3m = phase_v2 at the 3rd consecutive month-end;
     a calendar gap (missing month-end row for the instrument) BREAKS the chain → NaN
     (the §14 ``phase_persist_3m`` convention). Rows with NaN current phase or NaN label
     are excluded per horizon.

  3. Baseline (frozen): family-stratified empirical transition matrix on each TRAIN fold:
     P(next_phase_h = k | phase_v2_t = j, family), Laplace α=1 across the 5 classes;
     fallback for an unseen (j, family) row = the family-pooled row, then the global row
     (the KM fallback-chain convention of ``fit_cycle_hazard.km_predict``).

  4. Model (frozen): multinomial L2 softmax regression, pure numpy, extending the W4.2
     hand-rolled logistic conventions — train-fold standardization of continuous features,
     lr=0.15, iters=600, l2=1.0 (values cross-pinned to fit_cycle_hazard's LR/ITERS/L2),
     L2-exempt = age-bucket dummies (the W4.2 L2_MASK_EXEMPT convention), deterministic
     full-batch gradient descent (no stochasticity). Features = current-phase one-hot (5)
     + the §16-enumerated shipped W2.5-bound set (log_age_ratio, amp_proxy, pos_osc_s,
     osc_slope_s, mom_score, rs_63d, vol_pctile, age-bucket dummies, family dummies,
     direction) — NO new covariates, NO trend_pass, NO quad/liquidity regime dummies.
     NO calibration layer in v0 (raw softmax probabilities are gated; disclosed).

  5. Walk-forward: the W4.2 expanding-origin ANNUAL date-block geometry verbatim (first
     test year 2010, 6-month embargo between train end and test start, min-train 400 rows,
     test years 2010–2023 = 14 blocks). ONE pooled fit per fold per horizon (family
     dummies); evaluation per family cell.

  6. GATE per cell (horizon {1m,3m} × family {us_sector,country,cn_sector} = 6):
     multiclass Brier = (1/5)·Σ_k (p_k − y_k)² per row; paired ΔBrier(baseline − model)
     month-block bootstrap 90% CI (800 draws, seed 7; ``month_block_brier_gap_ci`` /
     ``_boot_pvalue`` reused verbatim) must exclude 0 on the POSITIVE side, sign-stability
     ≥ 9 of 14 test years, then BH-FDR q=0.10 across the 6 cells (``bh_fdr``).

  7. SANITY GATE (pipeline, printed, not a claim): the full-pre-embargo-sample baseline
     diagonal must show Peak self-persistence > Recovery self-persistence in every family
     (the §15 batch-2 structure), else abort sys.exit(2). Frozen interpretation: the gate
     is evaluated on the 3m transition diagonal — the §15 structure it cites is a 3-month
     persistence statement (phase_persist_3m); the 1m diagonal is printed as disclosure
     with no gate role.

  8. Prints the candidate count (6) BEFORE any evaluation (anti-mining law). Declares the
     trial budget as family ``rf.cycle_pattern.tr_v0`` at run time BEFORE any p-value
     (production ledger on the real run; scratch under --smoke). Writes
     data/cycle_pattern/tr_trials/tr1_transition.json → ``ledger.<fam>.<h>`` (§16 judged-by),
     carrying the full-sample baseline transition matrices as the exploration tables.

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

# House bootstrap constants (§16 names engine/grading_stats as the source).
from engine.grading_stats import BOOT_DRAWS, BOOT_SEED  # noqa: E402  (re-exported for tests)

# Reuse the W4.2 harness math verbatim — import, never fork (§16 "harness verbatim").
# (The TR_* hyperparameter literals below are cross-pinned to fit_cycle_hazard's own
# LR/ITERS/L2 and CONT_FEATURES/AGE_DUMMIES/FAMILY_DUMMIES by the AST test suite.)
from scripts.fit_cycle_hazard import (  # noqa: E402
    EMBARGO_M,
    FDR_Q,
    FIRST_TEST_YEAR,
    _boot_pvalue,
    bh_fdr,
    build_design,
    month_block_brier_gap_ci,
)

# Reuse the §12 embargo objects verbatim (same holdout convention).
from scripts.build_cycle_pattern_ft_phase0 import (  # noqa: E402
    EMBARGO_DATE,
    N_TEST_YEARS,
    SIGN_STABILITY_MIN,
    truncate_embargo,
)

# W4.4 phase derivation + the canonical class order — verbatim.
from scripts.build_conditional_cells import PHASES, derive_phase  # noqa: E402

# ── FROZEN constants (§16; not tuned). Tests parse these via AST and assert vs §16. ──
FAMILY = "rf.cycle_pattern.tr_v0"            # trial-budget family (§16)
TRIAL_FAMILY_SUFFIX = "tr_v0"                # bare suffix for factory candidates
N_TRIALS = 6                                 # 2 horizons × 3 families

TR_HORIZONS = [1, 3]                         # months → next_phase_1m / next_phase_3m
TR_FAMILIES = ["us_sector", "country", "cn_sector"]   # == build_conditional_cells.FAMILIES
N_CLASSES = 5                                # the 5 D1 phases (== len(PHASES))
LAPLACE_ALPHA = 1.0                          # α = 1 across the 5 classes (§16)

TR_LR = 0.15                                 # == fit_cycle_hazard.LR   (W4.2 convention)
TR_ITERS = 600                               # == fit_cycle_hazard.ITERS
TR_L2 = 1.0                                  # == fit_cycle_hazard.L2
MIN_TRAIN_ROWS = 400                         # W4.2 walk_forward fold guard, verbatim

# §16 frozen feature list — the shipped W2.5-bound set EXACTLY as enumerated in §16
# (NO trend_pass, NO quad/liquidity regime dummies, NO new covariates).
TR_CONT_FEATURES = ["log_age_ratio", "amp_proxy", "pos_osc_s", "osc_slope_s",
                    "mom_score", "rs_63d", "vol_pctile"]     # == fit_cycle_hazard.CONT_FEATURES
TR_AGE_DUMMIES = ["age_b1", "age_b2", "age_b3", "age_b4", "age_b5"]  # == AGE_DUMMIES
TR_FAMILY_DUMMIES = ["fam_country", "fam_cn"]                        # == FAMILY_DUMMIES
PHASE_ONEHOT = ["ph_Trough", "ph_Recovery", "ph_Expansion", "ph_Peak", "ph_Downturn"]
DIRECTION_FEATURE = ["dir_up"]               # direction dummy (up=1), the §16 "direction"

TR_DESIGN = PHASE_ONEHOT + TR_AGE_DUMMIES + TR_CONT_FEATURES + TR_FAMILY_DUMMIES \
    + DIRECTION_FEATURE
TR_L2_EXEMPT = set(TR_AGE_DUMMIES)           # W4.2 L2_MASK_EXEMPT convention (age buckets)

_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
_OUT_DIR = _REPO / "data" / "cycle_pattern" / "tr_trials"


# ═══════════════════════════════════════════════════════════════════════════════
# Substrate: phase_v2 + next-phase labels (§16 / §14 conventions)
# ═══════════════════════════════════════════════════════════════════════════════

def attach_phase_v2(panel: pd.DataFrame) -> pd.DataFrame:
    """phase_v2 per (id, month-end) via the W4.4 ``derive_phase`` verbatim; NaN pos_osc →
    NaN phase (§16 excludes those rows — derive_phase would silently bucket a NaN into
    Expansion/Downturn, so the guard lives here, not in the W4.4 function)."""
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.to_period("M").dt.to_timestamp("M")
    pos = pd.to_numeric(d["pos_osc"], errors="coerce")
    d["phase_v2"] = [
        derive_phase(p, direction) if pd.notna(p) else None
        for p, direction in zip(pos, d["direction"])
    ]
    return d


def attach_next_phase_labels(d: pd.DataFrame, horizons: list[int] | None = None) -> pd.DataFrame:
    """next_phase_h per (id, t): phase_v2 at the h-th CONSECUTIVE month-end (§16).

    Convention (the §14 ``phase_persist_3m`` self-join, applied to labels):
      * self-join on CONSECUTIVE month-ends per instrument;
      * a calendar gap (missing month-end row between t and t+h) BREAKS the chain → NaN;
      * the label is phase_v2(t+h); a NaN phase at t+h → NaN label;
      * the last <=h month-ends of every instrument (no full forward chain) → NaN.
    """
    horizons = TR_HORIZONS if horizons is None else horizons
    out = {h: pd.Series(np.nan, index=d.index, dtype=object) for h in horizons}
    dt = pd.to_datetime(d["date"])
    month_idx = dt.dt.year * 12 + (dt.dt.month - 1)
    work = pd.DataFrame({
        "_ridx": d.index.to_numpy(),
        "id": d["id"].to_numpy(),
        "midx": month_idx.to_numpy(),
        "phase": d["phase_v2"].to_numpy(object),
    })
    for _iid, grp in work.groupby("id", sort=False):
        g = grp.sort_values("midx")
        midx = g["midx"].to_numpy()
        ridx = g["_ridx"].to_numpy()
        # month-index → (present, phase) for O(1) lookahead within this instrument.
        by_month = {int(m): p for m, p in zip(midx, g["phase"].to_numpy(object))}
        for i in range(len(g)):
            m0 = int(midx[i])
            for h in horizons:
                # chain months t+1..t+h must ALL be present (gap breaks the chain)
                if any((m0 + k) not in by_month for k in range(1, h + 1)):
                    continue
                ph = by_month[m0 + h]
                if ph is not None:
                    out[h].loc[ridx[i]] = ph
    r = d.copy()
    for h in horizons:
        r[f"next_phase_{h}m"] = out[h]
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# Baseline: family-stratified Laplace transition matrix + KM fallback chain (§16)
# ═══════════════════════════════════════════════════════════════════════════════

def _laplace_row(labels, alpha: float = LAPLACE_ALPHA) -> np.ndarray:
    """Laplace-smoothed class distribution over PHASES (α across the 5 classes)."""
    counts = np.zeros(len(PHASES))
    vc = pd.Series(list(labels)).value_counts()
    for v, c in vc.items():
        counts[PHASES.index(v)] += int(c)
    return (counts + alpha) / (counts.sum() + alpha * len(PHASES))


def fit_transition_matrix(train: pd.DataFrame, label_col: str) -> dict:
    """Family-stratified empirical transition matrix on TRAIN rows (§16 baseline).

    Returns {(family, phase_j): probs(5,)} plus the fallback chain
    {("_family", family): probs} (family-pooled row) and {"_global": probs}
    (the KM fallback-chain convention). Every row Laplace-smoothed (α=1)."""
    tbl: dict = {"_global": _laplace_row(train[label_col])}
    for fam, g in train.groupby("family"):
        tbl[("_family", fam)] = _laplace_row(g[label_col])
        for ph, gg in g.groupby("phase_v2"):
            tbl[(fam, ph)] = _laplace_row(gg[label_col])
    return tbl


def baseline_predict(tbl: dict, test: pd.DataFrame) -> np.ndarray:
    """Predict P(next_phase = k) per test row from the train-fold transition matrix,
    walking the fallback chain (fam, phase) → family-pooled row → global row."""
    fams = test["family"].to_numpy()
    phs = test["phase_v2"].to_numpy(object)
    out = np.empty((len(test), len(PHASES)))
    for i in range(len(test)):
        row = tbl.get((fams[i], phs[i]))
        if row is None:
            row = tbl.get(("_family", fams[i]))
        if row is None:
            row = tbl["_global"]
        out[i] = row
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Model: hand-rolled numpy L2 multinomial softmax (extends fit_logistic_l2, §16)
# ═══════════════════════════════════════════════════════════════════════════════

def _softmax(Z: np.ndarray) -> np.ndarray:
    """Numerically stable softmax (subtract rowmax; clip mirrors _sigmoid's guard)."""
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(np.clip(Z, -35.0, 35.0))
    return E / E.sum(axis=1, keepdims=True)


def fit_softmax_l2(X: np.ndarray, Y: np.ndarray, l2_mask: np.ndarray,
                   l2: float = TR_L2, iters: int = TR_ITERS, lr: float = TR_LR):
    """Pure-numpy L2 multinomial softmax by deterministic full-batch gradient descent.

    Extends ``fit_cycle_hazard.fit_logistic_l2`` to K classes: shrinks toward 0,
    L2 applied only where l2_mask is True (never the intercept), same lr/iters/l2.
    Returns (W, b): (p, K) coefficient matrix and (K,) intercept vector. No sklearn.
    """
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    n, p = X.shape
    k = Y.shape[1]
    W = np.zeros((p, k))
    b = np.zeros(k)
    pen = (l2 * l2_mask.astype(float))[:, None]
    for _ in range(iters):
        P = _softmax(X @ W + b)
        G = P - Y
        W -= lr * (X.T @ G / n + pen * W / n)
        b -= lr * G.mean(axis=0)
    return W, b


def one_hot_labels(labels, classes: list[str] | None = None) -> np.ndarray:
    classes = PHASES if classes is None else classes
    idx = {c: i for i, c in enumerate(classes)}
    Y = np.zeros((len(labels), len(classes)))
    for r, v in enumerate(labels):
        Y[r, idx[v]] = 1.0
    return Y


def multiclass_brier(P: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Per-row multiclass Brier = (1/K)·Σ_k (p_k − y_k)² (§16, K=5)."""
    return np.mean((np.asarray(P, float) - np.asarray(Y, float)) ** 2, axis=1)


# ═══════════════════════════════════════════════════════════════════════════════
# Design matrix (§16 feature list over the W4.2 build_design columns)
# ═══════════════════════════════════════════════════════════════════════════════

def build_tr_design(panel: pd.DataFrame) -> pd.DataFrame:
    """W4.2 ``build_design`` (age dummies, scaled oscillators, family dummies,
    median-impute) + the TR-1 phase one-hots and direction dummy."""
    d = build_design(panel)
    for ph, col in zip(PHASES, PHASE_ONEHOT):
        d[col] = (d["phase_v2"] == ph).astype(float)
    d["dir_up"] = (d["direction"] == "up").astype(float)
    return d


def _fold_matrix(df: pd.DataFrame, mu: pd.Series, sd: pd.Series) -> np.ndarray:
    m = df[TR_DESIGN].copy()
    for c in TR_CONT_FEATURES:
        m[c] = (df[c] - mu[c]) / sd[c]
    return m[TR_DESIGN].to_numpy(dtype=float)


# ═══════════════════════════════════════════════════════════════════════════════
# Walk-forward (W4.2 expanding-origin annual date-block geometry, verbatim)
# ═══════════════════════════════════════════════════════════════════════════════

def walk_forward_tr(df_h: pd.DataFrame, label_col: str, *,
                    first_test_year: int = FIRST_TEST_YEAR,
                    embargo_m: int = EMBARGO_M,
                    min_train: int = MIN_TRAIN_ROWS):
    """Expanding-origin annual walk-forward for one horizon (§16).

    For each test year Y ≥ first_test_year: fit on rows with date ≤ Dec(Y-1) − embargo,
    predict rows dated within year Y. Blocks are by DATE, never by instrument. ONE pooled
    softmax fit per fold (family dummies); the baseline transition matrix is fitted on the
    SAME train fold. Returns (oos_frame, P_model, P_base, Y_onehot, fold_meta)."""
    sub = df_h.sort_values("date").reset_index(drop=True)
    years = sorted(sub["date"].dt.year.unique())
    last_year = years[-1]
    l2_mask = np.array([c not in TR_L2_EXEMPT for c in TR_DESIGN])

    metas, frames, pm_list, pb_list, y_list = [], [], [], [], []
    for Y in range(first_test_year, last_year + 1):
        train_cutoff = pd.Timestamp(year=Y - 1, month=12, day=31) - pd.DateOffset(months=embargo_m)
        train = sub[sub["date"] <= train_cutoff]
        test = sub[sub["date"].dt.year == Y]
        if len(train) < min_train or len(test) == 0:
            continue

        mu = train[TR_CONT_FEATURES].mean()
        sd = train[TR_CONT_FEATURES].replace(0, np.nan).std(ddof=0).fillna(1.0)
        sd = sd.replace(0, 1.0)

        Xtr = _fold_matrix(train, mu, sd)
        Xte = _fold_matrix(test, mu, sd)
        Ytr = one_hot_labels(train[label_col].to_numpy(object))
        W, b = fit_softmax_l2(Xtr, Ytr, l2_mask)
        P_model = _softmax(Xte @ W + b)

        tbl = fit_transition_matrix(train, label_col)
        P_base = baseline_predict(tbl, test)
        Yte = one_hot_labels(test[label_col].to_numpy(object))

        frames.append(pd.DataFrame({
            "date": test["date"].to_numpy(),
            "id": test["id"].to_numpy(),
            "family": test["family"].to_numpy(),
            "test_year": Y,
        }))
        pm_list.append(P_model)
        pb_list.append(P_base)
        y_list.append(Yte)
        metas.append({"test_year": Y, "n_train": int(len(train)), "n_test": int(len(test))})

    if not frames:
        return pd.DataFrame(), np.empty((0, len(PHASES))), np.empty((0, len(PHASES))), \
            np.empty((0, len(PHASES))), []
    return (pd.concat(frames, ignore_index=True), np.vstack(pm_list), np.vstack(pb_list),
            np.vstack(y_list), metas)


# ═══════════════════════════════════════════════════════════════════════════════
# Gate math per cell (reusing the house CI / p-value / BH verbatim)
# ═══════════════════════════════════════════════════════════════════════════════

def _cell_gate(dates, br_base: np.ndarray, br_model: np.ndarray, years) -> dict:
    """Paired ΔBrier(baseline − model) gate for one (family, horizon) cell. Positive gap =
    model has LOWER multiclass Brier. Reuses month_block_brier_gap_ci / _boot_pvalue
    verbatim (model plays the 'model' role, baseline plays the 'km' role)."""
    gap, lo, hi = month_block_brier_gap_ci(dates, br_base, br_model)
    pval = _boot_pvalue(dates, br_base, br_model)
    gap_arr = br_base - br_model
    yr_means = pd.Series(gap_arr).groupby(years).mean()
    n_pos, n_yr = int((yr_means > 0).sum()), int(len(yr_means))
    return {
        "delta_brier": round(float(gap), 6),
        "brier_baseline": round(float(np.mean(br_base)), 6),
        "brier_model": round(float(np.mean(br_model)), 6),
        "ci90": [round(lo, 6) if lo is not None else None,
                 round(hi, 6) if hi is not None else None],
        "boot_p": round(float(pval), 4),
        "ci_excludes_zero": bool(lo is not None and lo > 0),
        "years_positive": n_pos,
        "n_years": n_yr,
        "sign_stable": bool(n_pos >= SIGN_STABILITY_MIN),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Sanity gate (§16: pipeline check, printed, not a claim)
# ═══════════════════════════════════════════════════════════════════════════════

def sanity_gate_diagonal(labeled_3m: pd.DataFrame, label_col: str = "next_phase_3m") -> dict:
    """§16 sanity gate on the FULL pre-embargo labeled sample: the baseline diagonal must
    show Peak self-persistence > Recovery self-persistence in every family (the §15
    batch-2 structure). Evaluated on the 3m transition diagonal (the §15 structure is a
    3-month persistence statement); the caller prints the 1m diagonal as disclosure."""
    tbl = fit_transition_matrix(labeled_3m, label_col)
    table, ok_all = [], True
    for fam in TR_FAMILIES:
        peak = tbl.get((fam, "Peak"))
        reco = tbl.get((fam, "Recovery"))
        p_peak = float(peak[PHASES.index("Peak")]) if peak is not None else float("nan")
        p_reco = float(reco[PHASES.index("Recovery")]) if reco is not None else float("nan")
        ok = bool(p_peak > p_reco)
        ok_all &= ok
        table.append({"family": fam, "peak_self_3m": round(p_peak, 4),
                      "recovery_self_3m": round(p_reco, 4), "ok": ok})
    return {
        "passed": bool(ok_all),
        "table": table,
        "reason": ("Peak self-persistence > Recovery self-persistence in every family "
                   "(3m baseline diagonal)" if ok_all else
                   "FAILED: Recovery self-persistence >= Peak in at least one family — "
                   "pipeline error, not a finding"),
    }


def full_sample_diagonal(labeled: pd.DataFrame, label_col: str) -> dict:
    """Full-sample baseline transition matrices per family (the exploration tables)."""
    tbl = fit_transition_matrix(labeled, label_col)
    out: dict = {}
    for fam in TR_FAMILIES:
        out[fam] = {}
        for ph in PHASES:
            row = tbl.get((fam, ph))
            if row is not None:
                out[fam][ph] = [round(float(x), 4) for x in row]
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Trial budget
# ═══════════════════════════════════════════════════════════════════════════════

def declare_trial_budget(ledger_path: Path, *, run_at: str) -> None:
    """log_declared_budget BEFORE any p-value (house convention; scratch under --smoke)."""
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(path=ledger_path, family=FAMILY)
    led.log_declared_budget(
        N_TRIALS, family=FAMILY,
        reason=(f"PREREGISTRATION.md §16 cycle_pattern_tr: 2 horizons × 3 families = 6 "
                f"pre-registered cells; run_at={run_at}"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def _run(panel_path: Path, out_dir: Path, *, smoke: bool = False,
         ledger_path: Path | None = None, write: bool = True) -> dict:
    panel = pd.read_parquet(panel_path)
    epoch = str(panel["turn_def_version"].iloc[0]) if "turn_def_version" in panel.columns \
        else panel_path.stem.replace("panel_", "")
    panel = truncate_embargo(panel)              # EMBARGO before ANY label/estimate (§16)
    run_at = datetime.now(timezone.utc).isoformat()

    print("[substrate] phase_v2 (W4.4 derive_phase) + next-phase labels (§14 chain) ...")
    d = attach_phase_v2(panel)
    d = attach_next_phase_labels(d, TR_HORIZONS)
    n_rows = len(d)

    # ── ANTI-MINING LAW (§16): print the candidate count BEFORE any evaluation ──────
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS} "
          f"cells = 2 horizons × 3 families  [family={FAMILY}]")

    # ── Trial-budget declaration (runtime log_declared_budget, before any p-value) ──
    if ledger_path is None:
        ledger_path = (Path(tempfile.gettempdir()) / "cpi_tr1_smoke_trial_ledger.jsonl"
                       if smoke else _REPO / "data" / "trial_ledger.jsonl")
    declare_trial_budget(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY} n={N_TRIALS} → {ledger_path}")

    # Per-horizon labeled frames (rows with NaN current phase or NaN label excluded, §16).
    labeled: dict[int, pd.DataFrame] = {}
    for h in TR_HORIZONS:
        lab = f"next_phase_{h}m"
        sub = d[d["phase_v2"].notna() & d[lab].notna()].reset_index(drop=True)
        labeled[h] = sub
        print(f"[labels] {lab}: {len(sub)} labeled rows (of {n_rows} pre-embargo)")

    # ── SANITY GATE (full pre-embargo sample, 3m diagonal; 1m printed as disclosure) ─
    sanity = sanity_gate_diagonal(labeled[3])
    print("\n[SANITY GATE] 3m baseline diagonal (Peak vs Recovery self-persistence):")
    for row in sanity["table"]:
        print(f"    {row['family']:10s} Peak={row['peak_self_3m']:.4f}  "
              f"Recovery={row['recovery_self_3m']:.4f}  "
              f"{'ok' if row['ok'] else 'VIOLATION'}")
    print(f"  → {sanity['reason']}")
    diag_1m = full_sample_diagonal(labeled[1], "next_phase_1m")
    print("[disclosure] 1m diagonal (no gate role): " + ", ".join(
        f"{fam}: Peak={diag_1m[fam]['Peak'][PHASES.index('Peak')]:.3f}/"
        f"Rec={diag_1m[fam]['Recovery'][PHASES.index('Recovery')]:.3f}"
        for fam in TR_FAMILIES if "Peak" in diag_1m.get(fam, {})
    ))
    if not sanity["passed"]:
        print("\n[ABORT] Sanity gate FAILED — this is a PIPELINE ERROR, not a finding.",
              file=sys.stderr)
        sys.exit(2)

    horizons = [1] if smoke else TR_HORIZONS
    if smoke:
        for h in horizons:
            labeled[h] = labeled[h][labeled[h]["date"] < pd.Timestamp("2013-01-01")] \
                .reset_index(drop=True)
        print(f"[SMOKE] horizon 1m only, first 3 test years, {len(labeled[1])} truncated rows")

    # ── Walk-forward per horizon; cell gates per family ──────────────────────────────
    ledger: dict = {fam: {} for fam in TR_FAMILIES}
    per_fold: dict = {}
    cell_pvals: list[tuple[str, int, float]] = []
    exploration: dict = {}
    for h in horizons:
        lab = f"next_phase_{h}m"
        df_h = build_tr_design(labeled[h])
        df_h["date"] = pd.to_datetime(df_h["date"])
        oos, P_model, P_base, Yte, metas = walk_forward_tr(df_h, lab)
        if oos.empty:
            for fam in TR_FAMILIES:
                ledger[fam][f"{h}m"] = {"verdict": "FAIL", "reason": "no_oos"}
                cell_pvals.append((fam, h, 1.0))
            continue
        per_fold[f"{h}m"] = {
            "n_folds": len(metas),
            "test_years": [m["test_year"] for m in metas],
            "n_train_per_fold": [m["n_train"] for m in metas],
            "n_test_per_fold": [m["n_test"] for m in metas],
        }
        br_model = multiclass_brier(P_model, Yte)
        br_base = multiclass_brier(P_base, Yte)
        fams_arr = oos["family"].to_numpy()
        dates_arr = oos["date"].to_numpy()
        years_arr = oos["test_year"].to_numpy()
        for fam in TR_FAMILIES:
            m = fams_arr == fam
            if m.sum() == 0:
                ledger[fam][f"{h}m"] = {"verdict": "FAIL", "reason": "no_oos_rows_for_family"}
                cell_pvals.append((fam, h, 1.0))
                continue
            cell = _cell_gate(dates_arr[m], br_base[m], br_model[m], years_arr[m])
            cell["n_oos"] = int(m.sum())
            cell["n_months"] = int(len(np.unique(
                [pd.Timestamp(x).strftime("%Y-%m") for x in dates_arr[m]])))
            ledger[fam][f"{h}m"] = cell
            cell_pvals.append((fam, h, cell["boot_p"]))
        # Exploration tables (full-sample baseline transition matrices per family).
        exploration[f"{h}m"] = full_sample_diagonal(labeled[h], lab)

    # ── BH-FDR q=0.10 across the 6 cells (§16 family cycle_pattern_tr) ───────────────
    pvals = [p for (_, _, p) in cell_pvals]
    rejects = bh_fdr(pvals, q=FDR_Q)
    for (fam, h, _), rej in zip(cell_pvals, rejects):
        cell = ledger[fam][f"{h}m"]
        cell["bh_pass"] = bool(rej)
        cell["verdict"] = "PASS" if (
            cell.get("ci_excludes_zero", False)
            and cell.get("sign_stable", False)
            and rej
        ) else "FAIL"
    n_pass = sum(1 for fam in TR_FAMILIES for h in horizons
                 if ledger[fam].get(f"{h}m", {}).get("verdict") == "PASS")

    artifact = {
        "schema": "cycle_pattern_tr_trial.v1",
        "registered_ref": "PREREGISTRATION.md §16",
        "run_at": run_at,
        "embargo": "date<2024-01-01",
        "panel_epoch": epoch,
        "n_rows_pre_embargo": int(n_rows),
        "n_labeled": {f"{h}m": int(len(labeled[h])) for h in horizons},
        "candidate_count_printed": N_TRIALS,
        "trial_family": FAMILY,
        "config": {
            "first_test_year": FIRST_TEST_YEAR, "embargo_m": EMBARGO_M,
            "min_train_rows": MIN_TRAIN_ROWS,
            "boot_draws": BOOT_DRAWS, "boot_seed": BOOT_SEED, "fdr_q": FDR_Q,
            "sign_stability_min": SIGN_STABILITY_MIN, "n_cells_family": N_TRIALS,
            "lr": TR_LR, "iters": TR_ITERS, "l2": TR_L2,
            "laplace_alpha": LAPLACE_ALPHA,
            "classes": list(PHASES),
            "design": list(TR_DESIGN),
            "l2_exempt": sorted(TR_L2_EXEMPT),
            "calibration": "none (raw softmax probabilities gated; disclosed, §16)",
        },
        "sanity_gate": sanity,
        "baseline_transition_matrices": exploration,
        "per_fold": per_fold,
        "ledger": ledger,
        "n_cells_pass": int(n_pass),
    }

    if smoke:
        print(f"\n[SMOKE] ledger (1m only): ")
        for fam in TR_FAMILIES:
            c = ledger[fam].get("1m", {})
            print(f"  {fam}/1m: verdict={c.get('verdict')} dBrier={c.get('delta_brier')} "
                  f"ci90={c.get('ci90')} years+={c.get('years_positive')}/{c.get('n_years')}")
        print("[SMOKE] No real artifacts written.")
        return {"smoke": True, "ledger": ledger, "sanity_gate": sanity}

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        art_path = out_dir / "tr1_transition.json"
        art_path.write_text(json.dumps(artifact, indent=2, default=str))
        print(f"Wrote {art_path}")

    # ── Honest run-log summary ──────────────────────────────────────────────────────
    print(f"\nRESULT (panel_epoch={epoch}, embargo<{EMBARGO_DATE.date()}): "
          f"{n_pass} PASS / {N_TRIALS}")
    for fam in TR_FAMILIES:
        for h in horizons:
            c = ledger[fam].get(f"{h}m", {})
            print(f"  TR1 {fam}/{h}m: {c.get('verdict','?'):4s}  "
                  f"dBrier={c.get('delta_brier')}  ci90={c.get('ci90')}  "
                  f"years+={c.get('years_positive')}/{c.get('n_years')}  "
                  f"bh={c.get('bh_pass')}  "
                  f"[baseline Brier {c.get('brier_baseline')} vs model {c.get('brier_model')}]")
    return {"artifact": artifact, "n_cells_pass": n_pass}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CPI TR-1 transition-model runner (PREREG §16)")
    ap.add_argument("--panel", default=str(_PANEL_PATH))
    ap.add_argument("--out-dir", default=str(_OUT_DIR))
    ap.add_argument("--smoke", action="store_true",
                    help="horizon 1m only, first 3 test years, scratch ledger; "
                         "writes NO real artifacts")
    args = ap.parse_args(argv)
    _run(Path(args.panel), Path(args.out_dir), smoke=args.smoke, write=not args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
