"""tests/test_cycle_pattern_ix1.py — guards for the §17 IX-1 index-transfer runner.

Covers:
  (a) frozen constants match §17 (AST guard — parse SOURCE, not import): budget 4, family
      rf.cycle_pattern.ix_v0, cells {up,down}×{1m,3m}, the 8-entity universe, panel paths,
      KM min-rows 30, embargo, epoch pin;
  (b) machinery delegation — gate math (month_block_brier_gap_ci/_boot_pvalue/bh_fdr),
      the W4.2 logistic + design objects, the engine/index_km baseline, the PAV objects,
      and the §12 embargo objects are the SAME objects, never forked;
  (c) KM fallback-chain unit test — entity ≥30 train rows → own rate; <30 → family pool;
      empty family → global pool (through the runner's wrapper);
  (d) transfer-standardization test — index rows are scored with MEMBER train-fold mu/sd,
      never their own (fold-matrix exactness + end-to-end fold check);
  (e) PAV application correctness — the fold calibration maps index scores through the
      isotonic fit on member train predictions (step-function exactness; leak-free:
      changing index-row labels changes nothing about the map);
  (f) sanity-gate abort positive control — an index panel with up-leg y3 rate ≥ down-leg
      y3 rate must FAIL the gate (and a census-shaped panel must pass);
  (g) --smoke completes on the real panels (data-guarded skipif), writes nothing real.

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

_RUNNER = _ROOT / "scripts" / "build_cycle_pattern_ix1.py"

import scripts.build_cycle_pattern_ix1 as IX  # noqa: E402
import scripts.build_cycle_pattern_ft_phase0 as FT  # noqa: E402
import scripts.fit_cycle_hazard as HZ  # noqa: E402
import engine.index_km as IKM  # noqa: E402
import engine.validation as EV  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# (a) Frozen constants match §17 (AST guard — parse SOURCE)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_module_const(name: str):
    tree = ast.parse(_RUNNER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"module-level constant {name!r} not found in {_RUNNER}")


def test_frozen_budget_family_cells():
    """§17: 4 cells = 2 directions × 2 horizons, family rf.cycle_pattern.ix_v0."""
    assert _parse_module_const("N_TRIALS") == 4
    assert _parse_module_const("FAMILY") == "rf.cycle_pattern.ix_v0"
    assert _parse_module_const("TRIAL_FAMILY_SUFFIX") == "ix_v0"
    assert _parse_module_const("IX_HORIZONS") == [1, 3]
    assert _parse_module_const("IX_DIRECTIONS") == ["up", "down"]
    assert len(_parse_module_const("IX_HORIZONS")) * len(_parse_module_const("IX_DIRECTIONS")) == 4
    assert IX.IX_DIRECTIONS == HZ.DIRECTIONS


def test_frozen_entities_and_panels():
    """§17: 8 index entities (SPY = us_market + 7 blocs), frozen panel paths, epoch pin."""
    assert _parse_module_const("IX_ENTITIES") == [
        "AAXJ", "EEM", "EFA", "ILF", "SPY", "VGK", "VPL", "VXUS"]
    assert len(_parse_module_const("IX_ENTITIES")) == 8
    assert _parse_module_const("IX_EPOCH") == "price_c4414dcb"
    src = _RUNNER.read_text()
    assert "panel_price_c4414dcb.parquet" in src      # member (model-arm training) panel
    assert "panel_index_v0.parquet" in src            # index (evaluation) panel
    assert "ix1_transfer.json" in src                 # §17 judged-by artifact


def test_frozen_km_and_fold_guards():
    """§17 baseline: engine/index_km conventions with the 30-row entity threshold; W4.2
    fold guard 400 min-train rows."""
    assert _parse_module_const("KM_MIN_ROWS") == 30 == IKM.KM_MIN_ROWS_DEFAULT
    assert _parse_module_const("MIN_TRAIN_ROWS") == 400


def test_reserved_covariates_not_in_model_design():
    """§17: the index FT-4 covariates (sync_family, phase_breadth_*, pos_dispersion) are
    NOT used by the model arm — reserved for a future stacking trial."""
    assert _parse_module_const("IX_RESERVED_COVARIATES") == [
        "sync_family", "phase_breadth_late", "phase_breadth_early", "pos_dispersion"]
    for c in IX.IX_RESERVED_COVARIATES:
        assert c not in IX.DESIGN
        assert c not in IX.CONT_FEATURES


def test_embargo_and_gate_objects_are_the_house_ones():
    """§17 embargo (rows ≥ 2024-01-01 excluded from ALL fitting and the gate) reuses the
    §12 objects; fold geometry and stability bars are the W4.2/§12 constants; bootstrap
    constants are the engine/grading_stats house defaults."""
    assert IX.EMBARGO_DATE is FT.EMBARGO_DATE
    assert IX.EMBARGO_DATE == pd.Timestamp("2024-01-01")
    assert IX.truncate_embargo is FT.truncate_embargo
    assert IX.FIRST_TEST_YEAR == 2010 and IX.EMBARGO_M == 6
    assert IX.SIGN_STABILITY_MIN == 9 and IX.N_TEST_YEARS == 14
    assert IX.FDR_Q == 0.10
    assert IX.BOOT_DRAWS == 800 and IX.BOOT_SEED == 7
    from engine.grading_stats import BOOT_DRAWS as GD, BOOT_SEED as GS
    assert IX.BOOT_DRAWS == GD and IX.BOOT_SEED == GS


# ══════════════════════════════════════════════════════════════════════════════
# (b) Machinery delegation — same objects, never forked
# ══════════════════════════════════════════════════════════════════════════════

def test_gate_and_model_math_is_imported_not_forked():
    assert IX.month_block_brier_gap_ci is HZ.month_block_brier_gap_ci
    assert IX._boot_pvalue is HZ._boot_pvalue
    assert IX.bh_fdr is HZ.bh_fdr
    assert IX._brier is HZ._brier
    assert IX.build_design is HZ.build_design
    assert IX.fit_logistic_l2 is HZ.fit_logistic_l2
    assert IX._sigmoid is HZ._sigmoid
    assert IX.DESIGN is HZ.DESIGN
    assert IX.CONT_FEATURES is HZ.CONT_FEATURES
    assert IX.L2_MASK_EXEMPT is HZ.L2_MASK_EXEMPT


def test_km_baseline_is_engine_index_km():
    assert IX.index_km_table is IKM.index_km_table
    assert IX.km_predict_index is IKM.km_predict_index


def test_pav_is_engine_validation():
    assert IX.isotonic_calibration is EV.isotonic_calibration
    assert IX.apply_calibration is EV.apply_calibration


# ══════════════════════════════════════════════════════════════════════════════
# (c) KM fallback-chain unit test (through the runner's wrapper)
# ══════════════════════════════════════════════════════════════════════════════

def _km_frame(ent: str, fam: str, direction: str, n: int, y3_rate: float,
              y1_rate: float = 0.2) -> pd.DataFrame:
    n1 = int(round(n * y1_rate))
    n3 = int(round(n * y3_rate))
    return pd.DataFrame({
        "id": [ent] * n,
        "family": [fam] * n,
        "direction": [direction] * n,
        "y1": [1] * n1 + [0] * (n - n1),
        "y3": [1] * n3 + [0] * (n - n3),
        "y6": [0] * n,
    })


def test_km_fallback_chain_entity_family_global():
    """Entity ≥30 train rows → its OWN pooled rate; <30 → the family pool; a family with
    no rows → the global per-direction pool (engine/index_km chain, §17)."""
    train = pd.concat([
        _km_frame("SPY", "us_market", "up", 40, y3_rate=0.30),   # entity-level (n>=30)
        _km_frame("EEM", "bloc", "up", 10, y3_rate=0.90),        # thin → family pool
        _km_frame("VGK", "bloc", "up", 50, y3_rate=0.50),        # feeds the bloc pool
    ], ignore_index=True)
    test = pd.DataFrame({
        "id": ["SPY", "EEM", "VXUS"],
        "family": ["us_market", "bloc", "bloc"],
        "direction": ["up", "up", "up"],
    })
    km = IX.km_baseline_predict(train, test, [1, 3])
    # SPY: own entity rate (40 rows ≥ 30)
    assert np.isclose(km[3][0], 0.30)
    # EEM: 10 rows < 30 → bloc family pool = (9 + 25) / 60
    assert np.isclose(km[3][1], (9 + 25) / 60)
    # VXUS: zero rows → family pool covers it (bloc has rows), same value
    assert np.isclose(km[3][2], (9 + 25) / 60)
    # Global fallback: a test row whose family has NO train rows → global up-pool.
    test_g = pd.DataFrame({"id": ["ZZZ"], "family": ["nofam"], "direction": ["up"]})
    km_g = IX.km_baseline_predict(train, test_g, [1, 3])
    glob = float(train["y3"].mean())
    assert np.isclose(km_g[3][0], glob)


def test_km_min_rows_boundary():
    """Exactly 30 rows → entity-level estimate (the >= convention of index_km_table)."""
    train = pd.concat([
        _km_frame("SPY", "us_market", "up", 30, y3_rate=0.40),
        _km_frame("VGK", "bloc", "up", 100, y3_rate=0.80),
    ], ignore_index=True)
    test = pd.DataFrame({"id": ["SPY"], "family": ["us_market"], "direction": ["up"]})
    km = IX.km_baseline_predict(train, test, [1, 3])
    assert np.isclose(km[3][0], 0.40)     # own rate, NOT polluted by the bloc pool


# ══════════════════════════════════════════════════════════════════════════════
# (d) Transfer standardization — member params, never the index rows' own
# ══════════════════════════════════════════════════════════════════════════════

def _synth_panel(ids, family, n_months=48, start="2005-01-31", direction="up",
                 shift=0.0, seed=7, y_fn=None):
    """Minimal panel with every column build_design/DESIGN needs."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n_months, freq="ME")
    rows = []
    for iid in ids:
        for j, dt in enumerate(dates):
            pos = float(np.clip(50 + 30 * np.sin(j / 5) + rng.normal(0, 5), 0, 100))
            rows.append({
                "id": iid, "family": family, "direction": direction, "date": dt,
                "age_bucket": ["b1", "b2", "b3", "b4", "b5"][j % 5],
                "log_age_ratio": rng.normal(shift, 1.0),
                "amp_proxy": rng.normal(shift, 1.0),
                "pos_osc": pos, "osc_slope": rng.normal(0, 3),
                "trend_pass": float(j % 2),
                "mom_score": rng.normal(shift, 1.0), "rs_63d": rng.normal(0, 1),
                "vol_pctile": rng.uniform(0, 1),
                "quad": "Q1", "liquidity": "neutral",
                "turn_def_version": "price_c4414dcb",
            })
    d = pd.DataFrame(rows)
    if y_fn is None:
        d["y1"] = (rng.random(len(d)) < 0.2).astype(int)
    else:
        d["y1"] = y_fn(d)
    d["y3"] = np.maximum(d["y1"], (rng.random(len(d)) < 0.3).astype(int))
    d["y6"] = d["y3"]
    return d


def test_fold_matrix_uses_supplied_params_exactly():
    """_fold_matrix must standardize with the SUPPLIED mu/sd — the exact member
    train-fold values — not statistics of the frame it is given."""
    idx = IX.build_design(_synth_panel(["SPY"], "us_market", shift=5.0))
    mu = pd.Series({c: 1.0 for c in IX.CONT_FEATURES})
    sd = pd.Series({c: 2.0 for c in IX.CONT_FEATURES})
    M = IX._fold_matrix(idx, mu, sd)
    j = IX.DESIGN.index("mom_score")
    expect = (idx["mom_score"].to_numpy(float) - 1.0) / 2.0
    assert np.allclose(M[:, j], expect)
    # Own-standardization would give ~zero mean; the transfer matrix must NOT (shift=5).
    assert abs(float(M[:, j].mean())) > 0.5


def test_walk_forward_transfer_standardizes_index_with_member_params():
    """End-to-end fold check: scoring is invariant to an index-only covariate rescale
    ONLY IF the runner (wrongly) standardized with index stats; with member-param
    transfer, shifting the INDEX feature distribution must CHANGE the scores."""
    member = IX.build_design(_synth_panel(
        ["m1", "m2", "m3", "m4"], "us_sector", n_months=120, start="2000-01-31",
        y_fn=lambda d: (d["mom_score"] > 0).astype(int)))
    idx_a = _synth_panel(["SPY"], "us_market", n_months=120, start="2000-01-31", shift=0.0)
    idx_b = idx_a.copy()
    idx_b["mom_score"] = idx_b["mom_score"] + 3.0        # index-only distribution shift
    da, db = IX.build_design(idx_a), IX.build_design(idx_b)
    for f in (member, da, db):
        f["date"] = pd.to_datetime(f["date"])
    oos_a, meta_a = IX.walk_forward_transfer(member, da, "up", first_test_year=2005,
                                             min_train=100)
    oos_b, meta_b = IX.walk_forward_transfer(member, db, "up", first_test_year=2005,
                                             min_train=100)
    assert not oos_a.empty and not oos_b.empty
    assert [m["test_year"] for m in meta_a] == [m["test_year"] for m in meta_b]
    # Same member fit both times; if index rows were self-standardized, the +3 shift
    # would wash out and scores would match. Under member-param transfer they must not.
    assert not np.allclose(oos_a["p1_model"].to_numpy(), oos_b["p1_model"].to_numpy())
    # And the shifted panel must score strictly higher raw hazard on average
    # (mom_score enters positively by construction of the member labels).
    assert float(oos_b["p1_model"].mean()) > float(oos_a["p1_model"].mean())
    # KM baseline is fit on INDEX rows and identical in both runs (labels unchanged).
    assert np.allclose(oos_a["km1"].to_numpy(), oos_b["km1"].to_numpy())


def test_walk_forward_transfer_never_fits_on_index_rows():
    """The member fit is byte-identical whatever the index panel's LABELS are — no index
    label may leak into the model arm (fit, standardization, or calibration)."""
    member = IX.build_design(_synth_panel(
        ["m1", "m2", "m3"], "us_sector", n_months=100, start="2000-01-31"))
    idx1 = _synth_panel(["SPY"], "us_market", n_months=100, start="2000-01-31", seed=11)
    idx2 = idx1.copy()
    idx2["y1"] = 1 - idx2["y1"]                          # flip every index label
    idx2["y3"] = 1 - idx2["y3"]
    d1, d2 = IX.build_design(idx1), IX.build_design(idx2)
    for f in (member, d1, d2):
        f["date"] = pd.to_datetime(f["date"])
    oos1, _ = IX.walk_forward_transfer(member, d1, "up", first_test_year=2005,
                                       min_train=100)
    oos2, _ = IX.walk_forward_transfer(member, d2, "up", first_test_year=2005,
                                       min_train=100)
    assert np.array_equal(oos1["p1_model"].to_numpy(), oos2["p1_model"].to_numpy())
    assert np.array_equal(oos1["p3_model"].to_numpy(), oos2["p3_model"].to_numpy())
    # The KM baseline (fit on index train rows) legitimately DOES change:
    assert not np.allclose(oos1["km1"].to_numpy(), oos2["km1"].to_numpy())


# ══════════════════════════════════════════════════════════════════════════════
# (e) PAV application correctness (leak-free, step-function exactness)
# ══════════════════════════════════════════════════════════════════════════════

def test_pav_applied_as_fit_step_function():
    """apply_calibration maps a new score to the fitted value of the last train score
    ≤ it (right-continuous step function) — the exact object the runner applies to
    index test predictions."""
    p_tr = np.linspace(0.05, 0.95, 60)
    y_tr = (p_tr > 0.5).astype(float)          # perfectly monotone labels
    iso = IX.isotonic_calibration(p_tr, y_tr)
    assert iso, "isotonic fit must succeed at n=60"
    p_te = np.array([0.04, 0.30, 0.70, 0.99])
    out = IX.apply_calibration(iso, p_te)
    # Below/above the boundary the fitted map is ~0 / ~1.
    assert out[0] < 0.05 and out[1] < 0.05
    assert out[2] > 0.95 and out[3] > 0.95
    # Exactness: each mapped value equals the fitted y_cal at searchsorted position.
    x = np.array(iso["x"]); yc = np.array(iso["y_cal"])
    idx = np.clip(np.searchsorted(x, p_te, side="right") - 1, 0, len(yc) - 1)
    assert np.array_equal(out, yc[idx])


def test_pav_thin_train_falls_back_to_raw():
    """Below the n=30 isotonic floor the runner must pass raw compounded predictions
    through unchanged (iso == {} → apply skipped)."""
    iso = IX.isotonic_calibration(np.array([0.2, 0.8]), np.array([0.0, 1.0]))
    assert iso == {}


# ══════════════════════════════════════════════════════════════════════════════
# (f) Sanity-gate abort positive control
# ══════════════════════════════════════════════════════════════════════════════

def _sanity_panel(up_y3: float, dn_y3: float, n: int = 400) -> pd.DataFrame:
    n_up, n_dn = n, n // 3
    return pd.DataFrame({
        "direction": ["up"] * n_up + ["down"] * n_dn,
        "y3": [1] * int(n_up * up_y3) + [0] * (n_up - int(n_up * up_y3))
              + [1] * int(n_dn * dn_y3) + [0] * (n_dn - int(n_dn * dn_y3)),
    })


def test_sanity_gate_fires_on_violation():
    """POSITIVE CONTROL: up-leg y3 rate ≥ down-leg y3 rate → the gate must FAIL."""
    res = IX.sanity_gate_event_rates(_sanity_panel(up_y3=0.80, dn_y3=0.40))
    assert res["passed"] is False
    res_eq = IX.sanity_gate_event_rates(_sanity_panel(up_y3=0.50, dn_y3=0.50))
    assert res_eq["passed"] is False           # strict inequality required


def test_sanity_gate_passes_on_census_structure():
    """The substrate-census structure (down ~0.85 > up ~0.44) must PASS."""
    res = IX.sanity_gate_event_rates(_sanity_panel(up_y3=0.44, dn_y3=0.85))
    assert res["passed"] is True
    assert res["pooled_y3_down"] > res["pooled_y3_up"]


def test_sanity_gate_empty_direction_fails():
    p = _sanity_panel(up_y3=0.44, dn_y3=0.85)
    res = IX.sanity_gate_event_rates(p[p["direction"] == "up"])
    assert res["passed"] is False              # NaN down rate → pipeline error, not pass


# ══════════════════════════════════════════════════════════════════════════════
# (g) --smoke completes on the real panels (data-guarded), writes nothing real
# ══════════════════════════════════════════════════════════════════════════════

_MEMBER_PANEL = _ROOT / "data" / "hazard" / "panel_price_c4414dcb.parquet"
_INDEX_PANEL = _ROOT / "data" / "hazard" / "panel_index_v0.parquet"


@pytest.mark.skipif(not (_MEMBER_PANEL.exists() and _INDEX_PANEL.exists()),
                    reason="hazard panels not present")
def test_smoke_completes_and_writes_nothing_real():
    real_artifact = _ROOT / "data" / "cycle_pattern" / "ix_trials" / "ix1_transfer.json"
    real_ledger = _ROOT / "data" / "trial_ledger.jsonl"

    art_before = real_artifact.read_text() if real_artifact.exists() else None
    ledger_before = real_ledger.read_text() if real_ledger.exists() else None

    proc = subprocess.run(
        [sys.executable, str(_RUNNER), "--smoke"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"smoke failed:\nSTDOUT{proc.stdout}\nSTDERR{proc.stderr}"
    out = proc.stdout
    assert "CANDIDATE COUNT" in out and "4" in out
    assert "SANITY GATE" in out
    assert "No real artifacts written" in out

    art_after = real_artifact.read_text() if real_artifact.exists() else None
    assert art_after == art_before, "smoke must not create/modify the real artifact"
    ledger_after = real_ledger.read_text() if real_ledger.exists() else None
    assert ledger_after == ledger_before, "smoke must not touch the real trial ledger"
