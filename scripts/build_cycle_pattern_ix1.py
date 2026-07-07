"""CPI IX-1 index-level TRANSFER trial runner — family ``cycle_pattern_ix`` (PREREGISTRATION.md §17).

RESEARCH TRACK (masterplan §5, capability C5). FROZEN by §17: does the MEMBER-trained
discrete-time hazard model TRANSFER to index-level entities (SPY + 7 blocs), beating each
index's own age-pooled KM? NEW UNIT OF ANALYSIS — the CPI-017 member-level FT-4 null left
the index-level target explicitly open; this is that trial. NOT an additive-feature trial
on the pooled member hazard (the CPI-018 suspension does not apply: different evaluation
unit, its own named baseline; the member model is used as-trained, unchanged). Nothing
here touches a page; the deliverable is an honest verdict against the pre-registered gates.

WHAT THIS DOES (all parameters frozen in §17; none tuned here)
  1. Loads the MEMBER person-period panel ``data/hazard/panel_price_c4414dcb.parquet``
     (the model arm's training substrate) and the INDEX panel
     ``data/hazard/panel_index_v0.parquet`` (8 entities: SPY = us_market + 7 blocs, epoch
     ``price_c4414dcb``, built by #1769 with schema parity — asserted at runtime). BOTH
     are TRUNCATED to rows dated BEFORE 2024-01-01 (holdout embargo, §17 — reusing the
     §12 ``truncate_embargo`` object; embargo applies to ALL fitting and the gate).

  2. Model arm (frozen): per direction, the W4.2 discrete-time L2 logistic with the
     shipped W2.5-bound feature set (``fit_cycle_hazard.DESIGN``), fit on MEMBER-panel
     train rows EXACTLY as the §12/§13 baseline arm does — same expanding-origin ANNUAL
     fold geometry (first test year 2010, 6-month embargo, min-train 400), train-fold
     standardization from MEMBER rows, and the W4.2 harness's own leak-free PAV
     convention (per-fold isotonic fit on the fold's member TRAIN in-sample compounded
     predictions, never any OOS/test label — the ``p{h}_caloof`` convention the §12/§13
     baseline arm gates on). The fitted fold model is then SCORED on the INDEX-panel rows
     of the fold's test window: index features standardized with the MEMBER train-fold
     mu/sd (transfer standardization — never the index rows' own), PAV applied as fit.
     No index-row fitting anywhere. The index FT-4 covariates present in panel_index_v0
     (sync_family, phase_breadth_*, pos_dispersion) are NOT used by the model arm.

  3. Baseline (frozen): age-POOLED per-entity KM P(y_h = 1 | entity, direction),
     estimated on INDEX-panel train rows (rows ≤ the fold's train cutoff) via
     ``engine.index_km.index_km_table`` / ``km_predict_index`` — imported verbatim, math
     never forked. Fallback chain per §17: entity below 30 train rows per (entity,
     direction) → the entity's family pool, then the global index pool (the census shows
     SPY-down and VXUS-down use fallback in early folds; disclosed, not tuned).

  4. Cells (4): direction {up, down} × horizon {1m, 3m}, each pooled across ALL 8 index
     entities' OOS test rows. GATE per cell: paired ΔBrier(KM − model) month-block
     bootstrap 90% CI (800 draws, seed 7; ``month_block_brier_gap_ci`` / ``_boot_pvalue``
     reused verbatim) must exclude 0 on the POSITIVE side, sign-stability ≥ 9 of 14 test
     years, then BH-FDR q=0.10 within `cycle_pattern_ix` (``bh_fdr``, 4 cells).

  5. SANITY GATE (pipeline, printed, not a claim): on the full pre-embargo index panel,
     the pooled down-leg y3 event rate must exceed the pooled up-leg y3 event rate (down
     legs turn faster — the substrate census structure), else abort sys.exit(2).

  6. Prints the candidate count (4) BEFORE any evaluation (anti-mining law). Declares the
     trial budget as family ``rf.cycle_pattern.ix_v0`` at run time BEFORE any p-value
     (production ledger on the real run; scratch under --smoke). Writes
     data/cycle_pattern/ix_trials/ix1_transfer.json → ``ledger.<dir>.<h>`` (§17 judged-by),
     carrying the full pre-embargo index KM table and the per-entity ΔBrier decomposition
     (disclosed diagnostics, no gate role) as the exploration tables.

FROZEN INTERPRETATIONS (declared at criteria time; mechanical readings of §17, no tuning):
  * "leak-free out-of-fold PAV calibration fit on member out-of-fold predictions" is
    implemented as the W4.2 harness's OWN leak-free PAV convention — the per-fold
    isotonic fit on the fold's member TRAIN in-sample compounded predictions (the
    ``p{h}_caloof`` object the §12/§13 baseline arm scores), which sees no test-window
    label of either panel. §17 pins the mechanism to "EXACTLY as the §12/§13 baseline arm
    does"; that arm's calibration is fold-train-fit, applied out-of-fold.
  * Index rows carry family values {us_market, bloc}, which are NOT member families, so
    ``build_design``'s member-family dummies (fam_country, fam_cn) are mechanically 0 —
    index entities are scored at the model's reference level (us_sector). Disclosed, not
    a choice: §17 freezes "the SAME feature columns" applied to the index panel as-is.
  * ``build_design``'s median-impute convention applies to each panel separately (member
    NaNs ← member medians as in §12/§13; the index panel's rare NaNs — ≤1.9% of rows on
    rs_63d, fewer elsewhere — ← index medians). Standardization (the fold-level transfer
    object) always comes from MEMBER train rows only.

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

# House bootstrap constants (§17 names the house month-block bootstrap: 800 / seed 7).
from engine.grading_stats import BOOT_DRAWS, BOOT_SEED  # noqa: E402  (re-exported for tests)

# Baseline: the #1769 index-KM utility — imported verbatim, wrapped, never forked (§17).
from engine.index_km import (  # noqa: E402
    KM_MIN_ROWS_DEFAULT,
    index_km_table,
    km_predict_index,
)

# Leak-free PAV calibration — the W4.2 harness's own objects (engine.validation).
from engine.validation import apply_calibration, isotonic_calibration  # noqa: E402

# Reuse the W4.2 harness math verbatim — import, never fork (§17 "harness verbatim";
# §17 explicitly names bh_fdr as imported from fit_cycle_hazard).
from scripts.fit_cycle_hazard import (  # noqa: E402
    CONT_FEATURES,
    DESIGN,
    EMBARGO_M,
    FDR_Q,
    FIRST_TEST_YEAR,
    L2_MASK_EXEMPT,
    _boot_pvalue,
    _brier,
    _sigmoid,
    bh_fdr,
    build_design,
    fit_logistic_l2,
    month_block_brier_gap_ci,
)

# Reuse the §12 embargo objects verbatim (same holdout convention, §17).
from scripts.build_cycle_pattern_ft_phase0 import (  # noqa: E402
    EMBARGO_DATE,
    N_TEST_YEARS,
    SIGN_STABILITY_MIN,
    truncate_embargo,
)

# ── FROZEN constants (§17; not tuned). Tests parse these via AST and assert vs §17. ──
FAMILY = "rf.cycle_pattern.ix_v0"            # trial-budget family (§17)
TRIAL_FAMILY_SUFFIX = "ix_v0"                # bare suffix for factory candidates
N_TRIALS = 4                                 # 2 directions × 2 horizons

IX_HORIZONS = [1, 3]                         # months → y1 / y3 (§17: 1m, 3m)
IX_DIRECTIONS = ["up", "down"]               # == fit_cycle_hazard.DIRECTIONS
IX_ENTITIES = ["AAXJ", "EEM", "EFA", "ILF", "SPY", "VGK", "VPL", "VXUS"]  # the 8 (§17)
KM_MIN_ROWS = 30                             # == engine.index_km.KM_MIN_ROWS_DEFAULT (§17)
MIN_TRAIN_ROWS = 400                         # W4.2 walk_forward fold guard, verbatim
IX_EPOCH = "price_c4414dcb"                  # frozen turn epoch, BOTH panels (§17)

_MEMBER_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
_INDEX_PANEL_PATH = _REPO / "data" / "hazard" / "panel_index_v0.parquet"
_OUT_DIR = _REPO / "data" / "cycle_pattern" / "ix_trials"

# Index-only FT-4 covariates — present in panel_index_v0, RESERVED (never model inputs
# here; §17 reserves them for a future stacking trial under a NEW registration).
IX_RESERVED_COVARIATES = ["sync_family", "phase_breadth_late", "phase_breadth_early",
                          "pos_dispersion"]


# ═══════════════════════════════════════════════════════════════════════════════
# Substrate loading + schema-parity assertion (§17: "assert it at runtime")
# ═══════════════════════════════════════════════════════════════════════════════

def _load_panel(panel_path: Path) -> tuple[pd.DataFrame, str]:
    panel = pd.read_parquet(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    epoch = str(panel["turn_def_version"].iloc[0]) if "turn_def_version" in panel.columns \
        else panel_path.stem.replace("panel_", "")
    return panel, epoch


def assert_schema_parity(member: pd.DataFrame, index: pd.DataFrame) -> None:
    """§17: the substrate (#1769) guarantees schema parity — every member-panel column
    exists in the index panel (the index panel may carry EXTRA reserved covariates).
    Also pins both panels to the frozen turn epoch and the frozen 8-entity universe."""
    missing = sorted(set(member.columns) - set(index.columns))
    if missing:
        raise AssertionError(f"index panel missing member-panel columns: {missing}")
    for col in ("id", "family", "direction", "date", "y1", "y3"):
        if col not in index.columns:
            raise AssertionError(f"index panel missing required column {col!r}")
    ep_m = str(member["turn_def_version"].iloc[0])
    ep_i = str(index["turn_def_version"].iloc[0])
    if not (ep_m == ep_i == IX_EPOCH):
        raise AssertionError(f"epoch mismatch: member={ep_m} index={ep_i} frozen={IX_EPOCH}")
    ents = sorted(index["id"].unique())
    if ents != IX_ENTITIES:
        raise AssertionError(f"index entities {ents} != frozen {IX_ENTITIES}")


# ═══════════════════════════════════════════════════════════════════════════════
# Design matrices — the W4.2 DESIGN columns; transfer standardization (§17)
# ═══════════════════════════════════════════════════════════════════════════════

def _fold_matrix(df: pd.DataFrame, mu: pd.Series, sd: pd.Series) -> np.ndarray:
    """Design matrix over the W4.2 DESIGN columns with continuous features standardized
    by the SUPPLIED (member train-fold) mu/sd — the §17 transfer-standardization object.
    The caller must never pass index-row-derived mu/sd (tests pin this)."""
    m = df[DESIGN].copy()
    for c in CONT_FEATURES:
        m[c] = (df[c] - mu[c]) / sd[c]
    return m[DESIGN].to_numpy(dtype=float)


def _train_mu_sd(train: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Train-fold standardization params — byte-for-byte the W4.2 walk_forward recipe."""
    mu = train[CONT_FEATURES].mean()
    sd = train[CONT_FEATURES].replace(0, np.nan).std(ddof=0).fillna(1.0)
    sd = sd.replace(0, 1.0)
    return mu, sd


# ═══════════════════════════════════════════════════════════════════════════════
# Baseline: age-pooled per-entity index KM (engine/index_km verbatim, wrapped)
# ═══════════════════════════════════════════════════════════════════════════════

def km_baseline_predict(index_train: pd.DataFrame, index_test: pd.DataFrame,
                        horizons: list[int] | None = None) -> dict[int, np.ndarray]:
    """Fit the age-pooled per-entity KM on INDEX-panel train rows and predict
    P(y_h = 1 | entity, direction) for each test row. Thin wrapper over
    ``index_km_table`` + ``km_predict_index`` (math never forked); the fallback chain
    (entity < 30 rows → family pool → global pool) is engine/index_km's own."""
    horizons = IX_HORIZONS if horizons is None else horizons
    tbl = index_km_table(index_train, min_rows=KM_MIN_ROWS, horizons=tuple(horizons))
    return km_predict_index(tbl, index_test)


# ═══════════════════════════════════════════════════════════════════════════════
# Walk-forward TRANSFER (W4.2 expanding-origin annual geometry; member fit → index score)
# ═══════════════════════════════════════════════════════════════════════════════

def walk_forward_transfer(member_d: pd.DataFrame, index_d: pd.DataFrame, direction: str, *,
                          first_test_year: int = FIRST_TEST_YEAR,
                          embargo_m: int = EMBARGO_M,
                          min_train: int = MIN_TRAIN_ROWS,
                          horizons: list[int] | None = None):
    """Expanding-origin annual walk-forward for one direction (§17).

    For each test year Y ≥ first_test_year: fit the W4.2 logistic on MEMBER rows with
    date ≤ Dec(Y-1) − embargo (min-train 400, the W4.2 guard), then score the INDEX rows
    dated within year Y. Blocks are by DATE, never by instrument. Per fold:
      * mu/sd from MEMBER train rows only; index test rows standardized with them;
      * per horizon h: compound 1m hazard to h (1−(1−p)^h, the W4.2 form), PAV isotonic
        fit on the fold's member TRAIN in-sample compounded predictions (leak-free —
        the p{h}_caloof convention), applied to the index test predictions;
      * KM baseline fit on INDEX rows (BOTH directions) with date ≤ the same cutoff,
        predicted for the fold's index test rows.
    Returns (oos_frame, fold_meta). oos_frame columns: date, id, family, direction,
    test_year, y{h}, p{h}_model, km{h}. No index-row fitting anywhere.
    """
    horizons = IX_HORIZONS if horizons is None else horizons
    sub_m = member_d[member_d["direction"] == direction].sort_values("date") \
        .reset_index(drop=True)
    sub_i = index_d[index_d["direction"] == direction].sort_values("date") \
        .reset_index(drop=True)
    if sub_i.empty:
        return pd.DataFrame(), []
    last_year = int(sub_i["date"].dt.year.max())
    l2_mask = np.array([c not in L2_MASK_EXEMPT for c in DESIGN])

    frames, metas = [], []
    for Y in range(first_test_year, last_year + 1):
        train_cutoff = pd.Timestamp(year=Y - 1, month=12, day=31) - pd.DateOffset(months=embargo_m)
        train = sub_m[sub_m["date"] <= train_cutoff]           # MEMBER rows only
        test = sub_i[sub_i["date"].dt.year == Y]               # INDEX rows only
        if len(train) < min_train or len(test) == 0:
            continue

        mu, sd = _train_mu_sd(train)                           # MEMBER params (§17)
        Xtr = _fold_matrix(train, mu, sd)
        Xte = _fold_matrix(test, mu, sd)                       # transfer standardization
        ytr = train["y1"].to_numpy(float)
        w, b = fit_logistic_l2(Xtr, ytr, l2_mask)

        p1_te = _sigmoid(Xte @ w + b)
        p1_tr = _sigmoid(Xtr @ w + b)                          # member in-sample (PAV fit)

        # KM baseline: INDEX train rows ≤ the SAME cutoff (both directions — the table
        # stratifies by direction internally; predictions read the row's direction).
        km_train = index_d[index_d["date"] <= train_cutoff]
        km = km_baseline_predict(km_train, test, horizons)

        cols = {
            "date": test["date"].to_numpy(),
            "id": test["id"].to_numpy(),
            "family": test["family"].to_numpy(),
            "direction": direction,
            "test_year": Y,
        }
        for h in horizons:
            # Compound + calibrate exactly as W4.2 walk_forward (p{h}_caloof convention).
            p_tr_h = 1.0 - (1.0 - np.clip(p1_tr, 1e-6, 1 - 1e-6)) ** h
            p_te_h = 1.0 - (1.0 - np.clip(p1_te, 1e-6, 1 - 1e-6)) ** h
            iso = isotonic_calibration(p_tr_h, train[f"y{h}"].to_numpy(float))
            cols[f"p{h}_model"] = apply_calibration(iso, p_te_h) if iso else p_te_h
            cols[f"km{h}"] = km[h]
            cols[f"y{h}"] = test[f"y{h}"].to_numpy(float)
            if not np.all(np.isfinite(km[h])):
                raise AssertionError(
                    f"non-finite KM baseline prediction (dir={direction}, Y={Y}, h={h}) — "
                    f"fallback chain must always resolve")
        frames.append(pd.DataFrame(cols))
        metas.append({"test_year": Y, "n_train_member": int(len(train)),
                      "n_test_index": int(len(test)),
                      "n_km_train_index": int(len(km_train))})

    if not frames:
        return pd.DataFrame(), []
    return pd.concat(frames, ignore_index=True), metas


# ═══════════════════════════════════════════════════════════════════════════════
# Gate math per cell (reusing the house CI / p-value / BH verbatim)
# ═══════════════════════════════════════════════════════════════════════════════

def _cell_gate(dates, br_km: np.ndarray, br_model: np.ndarray, years) -> dict:
    """Paired ΔBrier(KM − model) gate for one (direction, horizon) cell. Positive gap =
    the transferred model has LOWER Brier. Reuses month_block_brier_gap_ci /
    _boot_pvalue verbatim (model plays the 'model' role, the index KM plays the 'km'
    role)."""
    gap, lo, hi = month_block_brier_gap_ci(dates, br_km, br_model)
    pval = _boot_pvalue(dates, br_km, br_model)
    gap_arr = br_km - br_model
    yr_means = pd.Series(gap_arr).groupby(years).mean()
    n_pos, n_yr = int((yr_means > 0).sum()), int(len(yr_means))
    return {
        "delta_brier": round(float(gap), 6),
        "brier_km": round(float(np.mean(br_km)), 6),
        "brier_model": round(float(np.mean(br_model)), 6),
        "ci90": [round(lo, 6) if lo is not None else None,
                 round(hi, 6) if hi is not None else None],
        "boot_p": round(float(pval), 4),
        "ci_excludes_zero": bool(lo is not None and lo > 0),
        "years_positive": n_pos,
        "n_years": n_yr,
        "sign_stable": bool(n_pos >= SIGN_STABILITY_MIN),
    }


def per_entity_decomposition(oos: pd.DataFrame, h: int) -> dict:
    """Per-entity ΔBrier decomposition for one cell — DISCLOSED DIAGNOSTIC (§17: "is SPY
    driving or dragging?"), point estimates only, NO gate role, NO CI."""
    out: dict = {}
    br_km = _brier(oos[f"km{h}"].to_numpy(float), oos[f"y{h}"].to_numpy(float))
    br_md = _brier(oos[f"p{h}_model"].to_numpy(float), oos[f"y{h}"].to_numpy(float))
    ids = oos["id"].to_numpy()
    for ent in IX_ENTITIES:
        m = ids == ent
        if m.sum() == 0:
            continue
        out[ent] = {
            "n_oos": int(m.sum()),
            "delta_brier": round(float(np.mean(br_km[m] - br_md[m])), 6),
            "brier_km": round(float(np.mean(br_km[m])), 6),
            "brier_model": round(float(np.mean(br_md[m])), 6),
        }
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Sanity gate (§17: pipeline check, printed, not a claim)
# ═══════════════════════════════════════════════════════════════════════════════

def sanity_gate_event_rates(index_panel: pd.DataFrame) -> dict:
    """§17 sanity gate on the FULL pre-embargo index panel: the pooled down-leg y3 event
    rate must EXCEED the pooled up-leg y3 event rate (down legs turn faster — the
    substrate census structure), else the caller aborts sys.exit(2)."""
    up = index_panel[index_panel["direction"] == "up"]
    dn = index_panel[index_panel["direction"] == "down"]
    r_up = float(up["y3"].mean()) if len(up) else float("nan")
    r_dn = float(dn["y3"].mean()) if len(dn) else float("nan")
    ok = bool(np.isfinite(r_up) and np.isfinite(r_dn) and r_dn > r_up)
    return {
        "passed": ok,
        "pooled_y3_up": round(r_up, 4),
        "pooled_y3_down": round(r_dn, 4),
        "n_up": int(len(up)),
        "n_down": int(len(dn)),
        "reason": ("pooled down-leg y3 event rate exceeds the pooled up-leg y3 event rate "
                   "(the substrate census structure)" if ok else
                   "FAILED: pooled down-leg y3 event rate does NOT exceed the up-leg rate "
                   "— pipeline error, not a finding"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Exploration table: full pre-embargo index KM (per entity × direction, both horizons)
# ═══════════════════════════════════════════════════════════════════════════════

def full_sample_km_table(index_panel: pd.DataFrame) -> dict:
    """Full pre-embargo age-pooled index KM table (per entity × direction, h ∈ {1,3}) —
    the exploration table (§17: exploration tables ship either way)."""
    tbl = index_km_table(index_panel, min_rows=KM_MIN_ROWS, horizons=tuple(IX_HORIZONS))
    out: dict = {}
    for ent in IX_ENTITIES:
        ent_tbl = tbl["entities"].get(ent, {})
        out[ent] = {}
        for direction in IX_DIRECTIONS:
            dcell = ent_tbl.get(direction)
            if dcell is None:
                continue
            out[ent][direction] = {
                "n": dcell["n"],
                "family": dcell["family"],
                "horizons": {str(h): dcell["horizons"][h] for h in IX_HORIZONS},
            }
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
        reason=(f"PREREGISTRATION.md §17 cycle_pattern_ix: 2 directions × 2 horizons = 4 "
                f"pre-registered cells; run_at={run_at}"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def _run(member_path: Path, index_path: Path, out_dir: Path, *, smoke: bool = False,
         ledger_path: Path | None = None, write: bool = True) -> dict:
    member, epoch_m = _load_panel(member_path)
    index, epoch_i = _load_panel(index_path)
    assert_schema_parity(member, index)
    member = truncate_embargo(member)            # EMBARGO before ANY fit/estimate (§17)
    index = truncate_embargo(index)
    run_at = datetime.now(timezone.utc).isoformat()
    n_rows_m, n_rows_i = len(member), len(index)

    # ── ANTI-MINING LAW (§17): print the candidate count BEFORE any evaluation ──────
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS} "
          f"cells = 2 directions × 2 horizons  [family={FAMILY}]")

    # ── Trial-budget declaration (runtime log_declared_budget, before any p-value) ──
    if ledger_path is None:
        ledger_path = (Path(tempfile.gettempdir()) / "cpi_ix1_smoke_trial_ledger.jsonl"
                       if smoke else _REPO / "data" / "trial_ledger.jsonl")
    declare_trial_budget(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY} n={N_TRIALS} → {ledger_path}")

    # ── SANITY GATE (full pre-embargo index panel; §17 pipeline check) ───────────────
    sanity = sanity_gate_event_rates(index)
    print(f"\n[SANITY GATE] pooled index y3 event rates: "
          f"down={sanity['pooled_y3_down']:.4f} (n={sanity['n_down']})  vs  "
          f"up={sanity['pooled_y3_up']:.4f} (n={sanity['n_up']})")
    print(f"  → {sanity['reason']}")
    if not sanity["passed"]:
        print("\n[ABORT] Sanity gate FAILED — this is a PIPELINE ERROR, not a finding.",
              file=sys.stderr)
        sys.exit(2)

    # ── Design frames (W4.2 build_design verbatim, each panel separately) ────────────
    member_d = build_design(member)
    member_d["date"] = pd.to_datetime(member_d["date"])
    index_d = build_design(index)
    index_d["date"] = pd.to_datetime(index_d["date"])
    # Runtime column-parity check on the composed design (the §17 "assert it at runtime").
    for c in DESIGN:
        if c not in index_d.columns:
            raise AssertionError(f"index design frame missing DESIGN column {c!r}")

    directions = ["up"] if smoke else IX_DIRECTIONS
    if smoke:
        member_d = member_d[member_d["date"] < pd.Timestamp("2013-01-01")].reset_index(drop=True)
        index_d = index_d[index_d["date"] < pd.Timestamp("2013-01-01")].reset_index(drop=True)
        print(f"[SMOKE] direction up only, first 3 test years, "
              f"{len(member_d)} member / {len(index_d)} index truncated rows")

    # ── Walk-forward transfer per direction; cell gates per (direction, horizon) ─────
    ledger: dict = {d: {} for d in directions}
    per_fold: dict = {}
    per_entity: dict = {d: {} for d in directions}
    cell_pvals: list[tuple[str, int, float]] = []
    for direction in directions:
        oos, metas = walk_forward_transfer(member_d, index_d, direction)
        if oos.empty:
            for h in IX_HORIZONS:
                ledger[direction][f"{h}m"] = {"verdict": "FAIL", "reason": "no_oos"}
                cell_pvals.append((direction, h, 1.0))
            continue
        per_fold[direction] = {
            "n_folds": len(metas),
            "test_years": [m["test_year"] for m in metas],
            "n_train_member_per_fold": [m["n_train_member"] for m in metas],
            "n_test_index_per_fold": [m["n_test_index"] for m in metas],
            "n_km_train_index_per_fold": [m["n_km_train_index"] for m in metas],
        }
        dates_arr = oos["date"].to_numpy()
        years_arr = oos["test_year"].to_numpy()
        for h in IX_HORIZONS:
            y = oos[f"y{h}"].to_numpy(float)
            br_km = _brier(oos[f"km{h}"].to_numpy(float), y)
            br_md = _brier(oos[f"p{h}_model"].to_numpy(float), y)
            cell = _cell_gate(dates_arr, br_km, br_md, years_arr)
            cell["n_oos"] = int(len(oos))
            cell["n_months"] = int(len(np.unique(
                [pd.Timestamp(x).strftime("%Y-%m") for x in dates_arr])))
            ledger[direction][f"{h}m"] = cell
            cell_pvals.append((direction, h, cell["boot_p"]))
            per_entity[direction][f"{h}m"] = per_entity_decomposition(oos, h)

    # ── BH-FDR q=0.10 across the 4 cells (§17 family cycle_pattern_ix) ───────────────
    pvals = [p for (_, _, p) in cell_pvals]
    rejects = bh_fdr(pvals, q=FDR_Q)
    for (direction, h, _), rej in zip(cell_pvals, rejects):
        cell = ledger[direction][f"{h}m"]
        cell["bh_pass"] = bool(rej)
        cell["verdict"] = "PASS" if (
            cell.get("ci_excludes_zero", False)
            and cell.get("sign_stable", False)
            and rej
        ) else "FAIL"
    n_pass = sum(1 for d in directions for h in IX_HORIZONS
                 if ledger[d].get(f"{h}m", {}).get("verdict") == "PASS")

    artifact = {
        "schema": "cycle_pattern_ix_trial.v1",
        "registered_ref": "PREREGISTRATION.md §17",
        "run_at": run_at,
        "embargo": "date<2024-01-01",
        "panel_epoch": epoch_m,
        "member_panel": str(member_path.name),
        "index_panel": str(index_path.name),
        "n_rows_member_pre_embargo": int(n_rows_m),
        "n_rows_index_pre_embargo": int(n_rows_i),
        "entities": list(IX_ENTITIES),
        "candidate_count_printed": N_TRIALS,
        "trial_family": FAMILY,
        "config": {
            "first_test_year": FIRST_TEST_YEAR, "embargo_m": EMBARGO_M,
            "min_train_rows": MIN_TRAIN_ROWS,
            "boot_draws": BOOT_DRAWS, "boot_seed": BOOT_SEED, "fdr_q": FDR_Q,
            "sign_stability_min": SIGN_STABILITY_MIN, "n_cells_family": N_TRIALS,
            "km_min_rows": KM_MIN_ROWS,
            "design": list(DESIGN),
            "l2_exempt": sorted(L2_MASK_EXEMPT),
            "calibration": ("W4.2 leak-free per-fold PAV (p{h}_caloof convention): "
                            "isotonic fit on member TRAIN in-sample compounded "
                            "predictions, applied to index test predictions"),
            "standardization": "member train-fold mu/sd applied to index rows (transfer)",
            "reserved_covariates_not_used": list(IX_RESERVED_COVARIATES),
        },
        "sanity_gate": sanity,
        "full_sample_index_km": full_sample_km_table(index),
        "per_fold": per_fold,
        "per_entity_delta_brier": per_entity,
        "ledger": ledger,
        "n_cells_pass": int(n_pass),
    }

    if smoke:
        print("\n[SMOKE] ledger (up only):")
        for h in IX_HORIZONS:
            c = ledger["up"].get(f"{h}m", {})
            print(f"  up/{h}m: verdict={c.get('verdict')} dBrier={c.get('delta_brier')} "
                  f"ci90={c.get('ci90')} years+={c.get('years_positive')}/{c.get('n_years')}")
        print("[SMOKE] No real artifacts written.")
        return {"smoke": True, "ledger": ledger, "sanity_gate": sanity}

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        art_path = out_dir / "ix1_transfer.json"
        art_path.write_text(json.dumps(artifact, indent=2, default=str))
        print(f"Wrote {art_path}")

    # ── Honest run-log summary ──────────────────────────────────────────────────────
    print(f"\nRESULT (panel_epoch={epoch_m}, embargo<{EMBARGO_DATE.date()}): "
          f"{n_pass} PASS / {N_TRIALS}")
    for direction in directions:
        for h in IX_HORIZONS:
            c = ledger[direction].get(f"{h}m", {})
            print(f"  IX1 {direction}/{h}m: {c.get('verdict','?'):4s}  "
                  f"dBrier={c.get('delta_brier')}  ci90={c.get('ci90')}  "
                  f"years+={c.get('years_positive')}/{c.get('n_years')}  "
                  f"bh={c.get('bh_pass')}  "
                  f"[KM Brier {c.get('brier_km')} vs model {c.get('brier_model')}]")
        dec = per_entity.get(direction, {})
        for h in IX_HORIZONS:
            ents = dec.get(f"{h}m", {})
            if ents:
                print(f"    per-entity dBrier ({direction}/{h}m, diagnostic): " + ", ".join(
                    f"{e}={v['delta_brier']:+.4f}" for e, v in ents.items()))
    return {"artifact": artifact, "n_cells_pass": n_pass}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CPI IX-1 index-transfer runner (PREREG §17)")
    ap.add_argument("--member-panel", default=str(_MEMBER_PANEL_PATH))
    ap.add_argument("--index-panel", default=str(_INDEX_PANEL_PATH))
    ap.add_argument("--out-dir", default=str(_OUT_DIR))
    ap.add_argument("--smoke", action="store_true",
                    help="direction up only, first 3 test years, scratch ledger; "
                         "writes NO real artifacts")
    args = ap.parse_args(argv)
    _run(Path(args.member_panel), Path(args.index_panel), Path(args.out_dir),
         smoke=args.smoke, write=not args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
