"""tests/test_cycle_pattern_tr1.py — guards for the §16 TR-1 transition-model runner.

Covers:
  (a) frozen constants match §16 (AST guard — parse SOURCE, not import): budget 6, family
      rf.cycle_pattern.tr_v0, horizons {1m,3m}, families, lr/iters/l2, Laplace α, the frozen
      feature list (NO trend_pass, NO quad/liquidity, NO new covariates), embargo;
  (b) machinery delegation — gate math (month_block_brier_gap_ci/_boot_pvalue/bh_fdr),
      embargo objects, derive_phase, and W4.2 constants are the SAME objects, never forked;
  (c) label positive control — a calendar gap BREAKS the chain → NaN (the §14 convention),
      while intact chains yield the correct next phase;
  (d) softmax correctness — on a synthetic separable 3-class problem the fitted model beats
      the uniform baseline on multiclass Brier (and is numerically stable at huge logits);
  (e) baseline transition matrix — Laplace α=1 exactness + the KM fallback chain
      (cell → family-pooled row → global row);
  (f) sanity-gate abort positive control — a sample violating Peak > Recovery
      self-persistence must FAIL the gate (and a §15-shaped sample must pass);
  (g) --smoke completes on the real panel (data-guarded skipif), writes nothing real.

Pure numpy/pandas. Deterministic (seed 7). NO sklearn / statsmodels / scipy.stats.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_RUNNER = _ROOT / "scripts" / "build_cycle_pattern_tr1.py"

import scripts.build_cycle_pattern_tr1 as TR  # noqa: E402
import scripts.build_cycle_pattern_ft_phase0 as FT  # noqa: E402
import scripts.fit_cycle_hazard as HZ  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# (a) Frozen constants match §16 (AST guard — parse SOURCE)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_module_const(name: str):
    tree = ast.parse(_RUNNER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"module-level constant {name!r} not found in {_RUNNER}")


def test_frozen_budget_family_horizons_families():
    """§16: 6 cells = 2 horizons × 3 families, family rf.cycle_pattern.tr_v0."""
    assert _parse_module_const("N_TRIALS") == 6
    assert _parse_module_const("FAMILY") == "rf.cycle_pattern.tr_v0"
    assert _parse_module_const("TRIAL_FAMILY_SUFFIX") == "tr_v0"
    assert _parse_module_const("TR_HORIZONS") == [1, 3]
    assert _parse_module_const("TR_FAMILIES") == ["us_sector", "country", "cn_sector"]
    assert len(_parse_module_const("TR_HORIZONS")) * len(_parse_module_const("TR_FAMILIES")) == 6


def test_frozen_model_hyperparams_match_w42_conventions():
    """§16: lr=0.15, iters=600, l2=1.0 — the W4.2 hand-rolled logistic conventions,
    cross-pinned to fit_cycle_hazard's own constants."""
    assert _parse_module_const("TR_LR") == 0.15 == HZ.LR
    assert _parse_module_const("TR_ITERS") == 600 == HZ.ITERS
    assert _parse_module_const("TR_L2") == 1.0 == HZ.L2
    assert _parse_module_const("MIN_TRAIN_ROWS") == 400   # W4.2 walk_forward fold guard
    assert _parse_module_const("LAPLACE_ALPHA") == 1.0    # §16 Laplace α=1
    assert _parse_module_const("N_CLASSES") == 5


def test_frozen_feature_list_matches_prereg16():
    """§16 feature list: phase one-hot (5) + log_age_ratio, amp_proxy, pos_osc_s,
    osc_slope_s, mom_score, rs_63d, vol_pctile, age dummies, family dummies, direction —
    and NOTHING else (no trend_pass, no quad/liquidity regime dummies, no new covariates)."""
    cont = _parse_module_const("TR_CONT_FEATURES")
    assert cont == ["log_age_ratio", "amp_proxy", "pos_osc_s", "osc_slope_s",
                    "mom_score", "rs_63d", "vol_pctile"]
    assert cont == HZ.CONT_FEATURES            # exactly the shipped W2.5-bound continuous set
    assert _parse_module_const("TR_AGE_DUMMIES") == HZ.AGE_DUMMIES
    assert _parse_module_const("TR_FAMILY_DUMMIES") == HZ.FAMILY_DUMMIES
    assert _parse_module_const("PHASE_ONEHOT") == [
        "ph_Trough", "ph_Recovery", "ph_Expansion", "ph_Peak", "ph_Downturn"]
    assert _parse_module_const("DIRECTION_FEATURE") == ["dir_up"]
    # The composed design: 5 + 5 + 7 + 2 + 1 = 20 columns, no leakage of banned features.
    design = TR.TR_DESIGN
    assert len(design) == 20
    assert "trend_pass" not in design
    assert not any(c.startswith("quad_") for c in design)
    assert "liq_expanding" not in design
    assert design == (TR.PHASE_ONEHOT + TR.TR_AGE_DUMMIES + TR.TR_CONT_FEATURES
                      + TR.TR_FAMILY_DUMMIES + TR.DIRECTION_FEATURE)
    # L2-exempt = age dummies (the W4.2 L2_MASK_EXEMPT convention).
    assert TR.TR_L2_EXEMPT == set(HZ.AGE_DUMMIES)


def test_embargo_and_gate_objects_are_the_house_ones():
    """§16 embargo (rows ≥ 2024-01-01 excluded fit AND gate) reuses the §12 objects;
    fold geometry and stability bars are the W4.2/§12 constants; bootstrap constants are
    the engine/grading_stats house defaults."""
    assert TR.EMBARGO_DATE is FT.EMBARGO_DATE
    assert TR.EMBARGO_DATE == pd.Timestamp("2024-01-01")
    assert TR.truncate_embargo is FT.truncate_embargo
    assert TR.FIRST_TEST_YEAR == 2010 and TR.EMBARGO_M == 6
    assert TR.SIGN_STABILITY_MIN == 9 and TR.N_TEST_YEARS == 14
    assert TR.FDR_Q == 0.10
    assert TR.BOOT_DRAWS == 800 and TR.BOOT_SEED == 7
    from engine.grading_stats import BOOT_DRAWS as GD, BOOT_SEED as GS
    assert TR.BOOT_DRAWS == GD and TR.BOOT_SEED == GS


# ══════════════════════════════════════════════════════════════════════════════
# (b) Machinery delegation — same objects, never forked
# ══════════════════════════════════════════════════════════════════════════════

def test_gate_math_is_imported_not_forked():
    assert TR.month_block_brier_gap_ci is HZ.month_block_brier_gap_ci
    assert TR._boot_pvalue is HZ._boot_pvalue
    assert TR.bh_fdr is HZ.bh_fdr
    assert TR.build_design is HZ.build_design
    import scripts.build_conditional_cells as W44
    assert TR.derive_phase is W44.derive_phase
    assert TR.PHASES is W44.PHASES
    assert TR.TR_FAMILIES == list(W44.FAMILIES)


# ══════════════════════════════════════════════════════════════════════════════
# (c) Label positive control — gap breaks the chain (§14 convention)
# ══════════════════════════════════════════════════════════════════════════════

def _me(y, m):
    return pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)


def test_labels_gap_breaks_chain_and_intact_chain_is_correct():
    """Instrument A: Jan..Jun 2015 with FEB MISSING. Then:
      * Jan: next month-end (Feb) missing → next_phase_1m NaN; 3m chain broken → NaN.
      * Mar: Apr/May/Jun present → 1m = phase(Apr), 3m = phase(Jun).
      * May: 1m = phase(Jun); 3m → NaN (no Jul/Aug).
      * Jun: both NaN (end of series)."""
    months = [(2015, 1), (2015, 3), (2015, 4), (2015, 5), (2015, 6)]  # Feb missing
    phases = ["Trough", "Recovery", "Expansion", "Expansion", "Peak"]
    df = pd.DataFrame({
        "date": [_me(y, m) for (y, m) in months],
        "id": "A",
        "phase_v2": phases,
    })
    out = TR.attach_next_phase_labels(df, [1, 3])
    by = {d.month: r for d, r in zip(out["date"], out.to_dict("records"))}
    # Jan: Feb missing → both labels NaN (gap breaks the chain)
    assert pd.isna(by[1]["next_phase_1m"]) and pd.isna(by[1]["next_phase_3m"])
    # Mar: intact chain → 1m = Apr phase, 3m = Jun phase
    assert by[3]["next_phase_1m"] == "Expansion"
    assert by[3]["next_phase_3m"] == "Peak"
    # Apr: 1m = May; 3m broken (needs Jul) → NaN
    assert by[4]["next_phase_1m"] == "Expansion"
    assert pd.isna(by[4]["next_phase_3m"])
    # May: 1m = Jun; Jun: end of series → NaN
    assert by[5]["next_phase_1m"] == "Peak"
    assert pd.isna(by[6]["next_phase_1m"]) and pd.isna(by[6]["next_phase_3m"])


def test_labels_nan_phase_at_target_month_yields_nan_label():
    """A month-end ROW that exists (no calendar gap) but with NaN phase at t+h → the label
    is NaN (§16 'rows with NaN label are excluded'), while the chain itself is intact."""
    df = pd.DataFrame({
        "date": [_me(2015, m) for m in (1, 2, 3, 4)],
        "id": "A",
        "phase_v2": ["Trough", None, "Expansion", "Peak"],
    })
    out = TR.attach_next_phase_labels(df, [1, 3])
    recs = {d.month: r for d, r in zip(out["date"], out.to_dict("records"))}
    assert pd.isna(recs[1]["next_phase_1m"])          # t+1 phase is NaN
    assert recs[1]["next_phase_3m"] == "Peak"          # chain intact; t+3 phase valid
    assert recs[2]["next_phase_1m"] == "Expansion"     # NaN CURRENT phase still labels; the
    #                                                    row is excluded later by phase_v2 NaN


# ══════════════════════════════════════════════════════════════════════════════
# (d) Softmax correctness + numerical stability
# ══════════════════════════════════════════════════════════════════════════════

def test_softmax_beats_uniform_on_separable_3class():
    rng = np.random.default_rng(7)
    n = 300
    centers = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 4.0]])
    X = np.vstack([rng.normal(c, 0.5, size=(n, 2)) for c in centers])
    Y = np.zeros((3 * n, 3))
    for k in range(3):
        Y[k * n:(k + 1) * n, k] = 1.0
    W, b = TR.fit_softmax_l2(X, Y, l2_mask=np.array([True, True]))
    P = TR._softmax(X @ W + b)
    acc = float(np.mean(P.argmax(axis=1) == Y.argmax(axis=1)))
    assert acc > 0.95
    br_model = float(np.mean(TR.multiclass_brier(P, Y)))
    br_uniform = float(np.mean(TR.multiclass_brier(np.full_like(Y, 1.0 / 3.0), Y)))
    assert br_model < br_uniform * 0.25, (br_model, br_uniform)


def test_softmax_numerically_stable_at_huge_logits():
    Z = np.array([[1e4, -1e4, 0.0], [500.0, 500.0, 500.0]])
    P = TR._softmax(Z)
    assert np.all(np.isfinite(P))
    assert np.allclose(P.sum(axis=1), 1.0)
    assert np.allclose(P[1], [1 / 3, 1 / 3, 1 / 3])


def test_softmax_is_deterministic():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(50, 3))
    Y = np.zeros((50, 5))
    Y[np.arange(50), rng.integers(0, 5, 50)] = 1.0
    m = np.array([True, True, False])
    W1, b1 = TR.fit_softmax_l2(X, Y, m)
    W2, b2 = TR.fit_softmax_l2(X, Y, m)
    assert np.array_equal(W1, W2) and np.array_equal(b1, b2)


def test_multiclass_brier_known_values():
    P = np.array([[1.0, 0.0, 0.0, 0.0, 0.0],
                  [0.2, 0.2, 0.2, 0.2, 0.2]])
    Y = np.array([[1.0, 0.0, 0.0, 0.0, 0.0],
                  [1.0, 0.0, 0.0, 0.0, 0.0]])
    br = TR.multiclass_brier(P, Y)
    assert br[0] == 0.0
    assert np.isclose(br[1], (0.8 ** 2 + 4 * 0.2 ** 2) / 5.0)


# ══════════════════════════════════════════════════════════════════════════════
# (e) Baseline transition matrix — Laplace exactness + KM fallback chain
# ══════════════════════════════════════════════════════════════════════════════

def test_baseline_laplace_alpha1_exact():
    """3 Trough→Recovery + 1 Trough→Trough in us_sector: the (us_sector, Trough) row must
    be (counts + 1) / (4 + 5) exactly."""
    train = pd.DataFrame({
        "family": ["us_sector"] * 4,
        "phase_v2": ["Trough"] * 4,
        "next_phase_1m": ["Recovery", "Recovery", "Recovery", "Trough"],
    })
    tbl = TR.fit_transition_matrix(train, "next_phase_1m")
    row = tbl[("us_sector", "Trough")]
    assert np.isclose(row[TR.PHASES.index("Recovery")], (3 + 1) / (4 + 5))
    assert np.isclose(row[TR.PHASES.index("Trough")], (1 + 1) / (4 + 5))
    assert np.isclose(row[TR.PHASES.index("Peak")], 1 / (4 + 5))
    assert np.isclose(row.sum(), 1.0)


def test_baseline_fallback_chain_cell_then_family_then_global():
    """Unseen (phase, family) cell → the family-pooled row; unseen family → global row
    (the KM fallback-chain convention)."""
    train = pd.DataFrame({
        "family": ["us_sector", "us_sector", "country"],
        "phase_v2": ["Trough", "Peak", "Expansion"],
        "next_phase_1m": ["Recovery", "Downturn", "Peak"],
    })
    tbl = TR.fit_transition_matrix(train, "next_phase_1m")
    # (us_sector, Expansion) unseen → family-pooled us_sector row
    test = pd.DataFrame({"family": ["us_sector"], "phase_v2": ["Expansion"]})
    p = TR.baseline_predict(tbl, test)
    assert np.allclose(p[0], tbl[("_family", "us_sector")])
    # unseen family → global row
    test2 = pd.DataFrame({"family": ["cn_sector"], "phase_v2": ["Trough"]})
    p2 = TR.baseline_predict(tbl, test2)
    assert np.allclose(p2[0], tbl["_global"])
    # seen cell → its own row, not a fallback
    test3 = pd.DataFrame({"family": ["us_sector"], "phase_v2": ["Trough"]})
    p3 = TR.baseline_predict(tbl, test3)
    assert np.allclose(p3[0], tbl[("us_sector", "Trough")])
    assert not np.allclose(p3[0], tbl[("_family", "us_sector")])


# ══════════════════════════════════════════════════════════════════════════════
# (f) Sanity-gate abort positive control
# ══════════════════════════════════════════════════════════════════════════════

def _sanity_frame(peak_self: float, reco_self: float, n: int = 200,
                  seed: int = 7) -> pd.DataFrame:
    """Labeled 3m frame where P(next3=Peak|Peak) ≈ peak_self and
    P(next3=Recovery|Recovery) ≈ reco_self, in all 3 families."""
    rng = np.random.default_rng(seed)
    rows = []
    for fam in ["us_sector", "country", "cn_sector"]:
        for _ in range(n):
            rows.append({"family": fam, "phase_v2": "Peak",
                         "next_phase_3m": "Peak" if rng.random() < peak_self else "Downturn"})
            rows.append({"family": fam, "phase_v2": "Recovery",
                         "next_phase_3m": "Recovery" if rng.random() < reco_self else "Expansion"})
    return pd.DataFrame(rows)


def test_sanity_gate_fires_on_violation():
    """POSITIVE CONTROL: Recovery MORE self-persistent than Peak → the gate must FAIL."""
    bad = _sanity_frame(peak_self=0.3, reco_self=0.8)
    res = TR.sanity_gate_diagonal(bad)
    assert res["passed"] is False
    assert all(not r["ok"] for r in res["table"])


def test_sanity_gate_passes_on_batch2_structure():
    """The §15 structure (Peak persists, Recovery fragile) must PASS in every family."""
    good = _sanity_frame(peak_self=0.7, reco_self=0.3)
    res = TR.sanity_gate_diagonal(good)
    assert res["passed"] is True
    assert all(r["ok"] for r in res["table"])
    assert len(res["table"]) == 3


def test_sanity_gate_single_family_violation_aborts_all():
    """Peak > Recovery must hold in EVERY family — one violating family fails the gate."""
    good = _sanity_frame(peak_self=0.7, reco_self=0.3)
    bad_cn = _sanity_frame(peak_self=0.2, reco_self=0.9)
    mixed = pd.concat([good[good["family"] != "cn_sector"],
                       bad_cn[bad_cn["family"] == "cn_sector"]], ignore_index=True)
    res = TR.sanity_gate_diagonal(mixed)
    assert res["passed"] is False
    by_fam = {r["family"]: r["ok"] for r in res["table"]}
    assert by_fam["us_sector"] and by_fam["country"] and not by_fam["cn_sector"]


# ══════════════════════════════════════════════════════════════════════════════
# (g) --smoke completes on the real panel (data-guarded), writes nothing real
# ══════════════════════════════════════════════════════════════════════════════

_PANEL = _ROOT / "data" / "hazard" / "panel_price_c4414dcb.parquet"


@pytest.mark.skipif(not _PANEL.exists(), reason="hazard panel not present")
def test_smoke_completes_and_writes_nothing_real():
    real_artifact = _ROOT / "data" / "cycle_pattern" / "tr_trials" / "tr1_transition.json"
    real_ledger = _ROOT / "data" / "trial_ledger.jsonl"

    art_before = real_artifact.read_text() if real_artifact.exists() else None
    ledger_before = real_ledger.read_text() if real_ledger.exists() else None

    proc = subprocess.run(
        [sys.executable, str(_RUNNER), "--smoke"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"smoke failed:\nSTDOUT{proc.stdout}\nSTDERR{proc.stderr}"
    out = proc.stdout
    assert "CANDIDATE COUNT" in out and "6" in out
    assert "SANITY GATE" in out
    assert "No real artifacts written" in out

    art_after = real_artifact.read_text() if real_artifact.exists() else None
    assert art_after == art_before, "smoke must not create/modify the real artifact"
    ledger_after = real_ledger.read_text() if real_ledger.exists() else None
    assert ledger_after == ledger_before, "smoke must not touch the real trial ledger"
