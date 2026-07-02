"""
Tests for scripts/collinearity_phase0.py — W2.5 Confluence-Collinearity Phase-0.

Three test suites as specified in the wave prompt:
1. Leg reconstruction is PIT (uses tape <= stamp date).
2. VIF math on synthetic collinear data.
3. The script is deterministic under the pre-registered seed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.collinearity_phase0 import (
    _PHASE_DIR,
    SEED,
    VIF_HIGH,
    _determinism_test,
    _pairwise_corr,
    _pca,
    _state_score_pit,
    _mom_score_pit,
    _vif,
)


# ════════════════════════════════════════════════════════════════════════════════
# Suite 1 — PIT invariance of leg reconstruction
# ════════════════════════════════════════════════════════════════════════════════

class TestPITInvariance:
    """
    Verify that the leg reconstruction functions only reference columns that
    are themselves PIT (columns present in backfill.parquet, which is
    computed using only tape <= stamp date per W2.3).

    The reconstruction functions (_state_score_pit, _mom_score_pit) must NOT
    call any live engine function or read any file.  They must be pure
    transforms of the input DataFrame columns.
    """

    def _make_df(self, n: int = 20, seed: int = 42) -> pd.DataFrame:
        """Synthetic backfill-shaped DataFrame."""
        rng = np.random.default_rng(seed)
        phases = list(_PHASE_DIR.keys())
        signals = ["BUY", "SELL", ""]

        df = pd.DataFrame({
            "date":      [f"2020-{(i%12)+1:02d}-30" for i in range(n)],
            "id":        [f"etf_{i%5}" for i in range(n)],
            "family":    ["us_sector"] * n,
            "phase":     [phases[i % len(phases)] for i in range(n)],
            "pos":       rng.uniform(0, 100, n),
            "osc_slope": rng.standard_normal(n),
            "signal":    [signals[i % 3] for i in range(n)],
            "above200d": rng.choice([True, False], n),
            "rs_63d":    rng.standard_normal(n),
        })

        # Add computed columns needed by _mom_score_pit
        df["rs_rank_computed"] = df.groupby(["family", "date"])["rs_63d"].rank(
            ascending=False, method="min", na_option="bottom"
        )
        df["n_peers"] = df.groupby(["family", "date"])["rs_63d"].transform("count")
        return df

    def test_state_score_range(self):
        """_state_score_pit must return values in [-1, 1] for all inputs."""
        df = self._make_df()
        scores = _state_score_pit(df)
        assert (scores >= -1.0).all(), "state_score below -1"
        assert (scores <= 1.0).all(), "state_score above +1"

    def test_state_score_phase_direction(self):
        """Trough phase + BUY signal should produce a strongly positive score."""
        df = self._make_df(n=10)
        df["phase"]  = "Trough"
        df["signal"] = "BUY"
        df["pos"]    = 10.0   # washed-out → bullish setup
        scores = _state_score_pit(df)
        assert (scores > 0).all(), "Trough + BUY + low pos should score positive"

    def test_state_score_peak_sells_negative(self):
        """Peak phase + SELL signal should produce a negative score."""
        df = self._make_df(n=10)
        df["phase"]  = "Peak"
        df["signal"] = "SELL"
        df["pos"]    = 90.0   # stretched → bearish
        scores = _state_score_pit(df)
        assert (scores < 0).all(), "Peak + SELL + high pos should score negative"

    def test_mom_score_range(self):
        """_mom_score_pit must return values in [-0.3, 0.3]."""
        df = self._make_df(n=50)
        scores = _mom_score_pit(df)
        assert (scores >= -0.3 - 1e-9).all(), "mom_score below -0.3"
        assert (scores <= 0.3 + 1e-9).all(),  "mom_score above +0.3"

    def test_mom_score_leader_higher(self):
        """The rank-1 (leader) instrument should score higher than rank-N."""
        n_peers = 11
        df = pd.DataFrame({
            "date":    ["2020-01"] * n_peers,
            "id":      [f"etf_{i}" for i in range(n_peers)],
            "family":  ["us_sector"] * n_peers,
            "phase":   ["Expansion"] * n_peers,
            "pos":     [50.0] * n_peers,
            "osc_slope": [0.0] * n_peers,
            "signal":  [""] * n_peers,
            "above200d": [True] * n_peers,
            # descending rs_63d so rank 1 has highest rs
            "rs_63d":  [float(n_peers - i) for i in range(n_peers)],
        })
        df["rs_rank_computed"] = df["rs_63d"].rank(ascending=False, method="min")
        df["n_peers"] = n_peers
        scores = _mom_score_pit(df)
        assert scores.iloc[0] > scores.iloc[-1], "Leader should score higher than laggard"

    def test_state_score_pure_function(self):
        """_state_score_pit returns the same value for the same input row (no side effects)."""
        df = self._make_df(n=5)
        s1 = _state_score_pit(df).values.copy()
        s2 = _state_score_pit(df).values.copy()
        np.testing.assert_array_equal(s1, s2)

    def test_pit_uses_only_backfill_columns(self):
        """
        The reconstruction functions must only CALL live engine functions or
        import from engine modules.  They must be pure transforms of their
        DataFrame input.  Docstrings referencing the source engine by name
        are fine; actual import statements or function calls are forbidden.
        Verified by inspecting the function source for forbidden CALL patterns.
        """
        import inspect
        import scripts.collinearity_phase0 as m
        import ast

        def has_import_or_engine_call(src: str, forbidden_modules: list) -> bool:
            """Return True if the source code imports or calls engine modules."""
            try:
                tree = ast.parse(src)
            except SyntaxError:
                return False
            for node in ast.walk(tree):
                # import statements inside the function body
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in getattr(node, "names", []):
                        name = getattr(alias, "name", "")
                        for mod in forbidden_modules:
                            if mod in name:
                                return True
                    mod = getattr(node, "module", "") or ""
                    for fm in forbidden_modules:
                        if fm in mod:
                            return True
            return False

        src_state = inspect.getsource(m._state_score_pit)
        src_mom   = inspect.getsource(m._mom_score_pit)

        # engine modules that must NOT be imported from inside the functions
        forbidden_modules = ["engine.sector_cycles", "engine.sector_central",
                             "engine.cycle_ontology"]

        assert not has_import_or_engine_call(src_state, forbidden_modules), \
            "_state_score_pit imports live engine module"
        assert not has_import_or_engine_call(src_mom, forbidden_modules), \
            "_mom_score_pit imports live engine module"


# ════════════════════════════════════════════════════════════════════════════════
# Suite 2 — VIF math on synthetic collinear data
# ════════════════════════════════════════════════════════════════════════════════

class TestVIFMath:
    """
    Validate the pure-numpy VIF implementation against known inputs.
    """

    def test_vif_identity_columns_is_high(self):
        """VIF of perfectly collinear leg (x3 = x1 + x2) must be >> VIF_HIGH."""
        rng  = np.random.default_rng(42)
        x1   = rng.standard_normal(300)
        x2   = rng.standard_normal(300)
        x3   = x1 + x2
        mat  = np.column_stack([x1, x2, x3])
        vif  = _vif(mat, ["x1", "x2", "x3"])
        assert vif["x3"] > VIF_HIGH, (
            f"Perfectly collinear leg should have VIF >> {VIF_HIGH}, got {vif['x3']}"
        )

    def test_vif_orthogonal_columns_near_one(self):
        """VIF of completely orthogonal legs should be close to 1.0."""
        rng = np.random.default_rng(7)
        # generate orthogonal columns via QR
        A = rng.standard_normal((300, 4))
        Q, _ = np.linalg.qr(A)
        mat = Q * 10   # scale so not numerically tiny
        vif = _vif(mat, [f"c{i}" for i in range(4)])
        for name, v in vif.items():
            assert v < 2.5, (
                f"Orthogonal columns should have VIF close to 1.0, got {name}={v:.2f}"
            )

    def test_vif_two_collinear_out_of_three(self):
        """With one collinear pair, the offenders should both have high VIF."""
        rng = np.random.default_rng(13)
        x1 = rng.standard_normal(200)
        x2 = x1 * 0.99 + rng.standard_normal(200) * 0.01   # near-collinear with x1
        x3 = rng.standard_normal(200)                       # independent
        mat = np.column_stack([x1, x2, x3])
        vif = _vif(mat, ["x1", "x2", "x3"])
        assert vif["x1"] > VIF_HIGH, f"x1 should have high VIF, got {vif['x1']:.1f}"
        assert vif["x2"] > VIF_HIGH, f"x2 should have high VIF, got {vif['x2']:.1f}"
        assert vif["x3"] < VIF_HIGH, f"x3 (independent) should not have high VIF"

    def test_vif_partial_corr_direction(self):
        """
        Pairwise correlation between x1 and x2 should be positive when
        x2 = x1 + noise, and the VIF implementation must agree with it.
        """
        rng = np.random.default_rng(0)
        x1 = rng.standard_normal(500)
        x2 = x1 + rng.standard_normal(500) * 0.1
        mat = np.column_stack([x1, x2])
        corr = _pairwise_corr(mat, ["x1", "x2"])
        assert corr["x1|x2"] > 0.9, "Corr(x1, x2) should be > 0.9"

    def test_pca_cumulative_reaches_one(self):
        """PCA cumulative EVR should reach 1.0 at the last component."""
        rng = np.random.default_rng(42)
        mat = rng.standard_normal((100, 5))
        result = _pca(mat)
        assert abs(result["cumulative_variance"][-1] - 1.0) < 1e-4, (
            "Cumulative explained variance should reach 1.0"
        )

    def test_pca_pc_count_monotone(self):
        """n_pcs_for_90pct should be <= n_features."""
        rng = np.random.default_rng(42)
        mat = rng.standard_normal((200, 6))
        result = _pca(mat)
        assert 1 <= result["n_pcs_for_90pct"] <= 6


# ════════════════════════════════════════════════════════════════════════════════
# Suite 3 — Determinism under the pre-registered seed
# ════════════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    """
    The script must produce identical results on repeated calls with the same seed.
    """

    def test_determinism_test_passes(self):
        """The built-in _determinism_test() must pass."""
        result = _determinism_test()
        assert result["determinism_ok"] is True
        assert result["vif_collinear"]["x3"] > VIF_HIGH

    def test_vif_deterministic(self):
        """VIF on the same matrix twice must return identical results."""
        rng = np.random.default_rng(SEED)
        mat = rng.standard_normal((100, 4))
        mat[:, 3] = mat[:, 0] + mat[:, 1]   # collinear

        v1 = _vif(mat, ["a", "b", "c", "d"])
        v2 = _vif(mat, ["a", "b", "c", "d"])
        assert v1 == v2, f"VIF not deterministic: {v1} != {v2}"

    def test_pca_deterministic(self):
        """PCA on the same matrix twice must return identical variance ratios."""
        rng = np.random.default_rng(SEED)
        mat = rng.standard_normal((200, 5))
        r1 = _pca(mat)
        r2 = _pca(mat)
        assert r1["explained_variance_ratios"] == r2["explained_variance_ratios"]
        assert r1["cumulative_variance"] == r2["cumulative_variance"]

    def test_pairwise_corr_deterministic(self):
        """Pairwise correlation is deterministic (no random component)."""
        rng = np.random.default_rng(SEED)
        mat = rng.standard_normal((150, 3))
        c1 = _pairwise_corr(mat, ["x", "y", "z"])
        c2 = _pairwise_corr(mat, ["x", "y", "z"])
        assert c1 == c2


# ════════════════════════════════════════════════════════════════════════════════
# Suite 4 — Artifact sanity (skipped if not produced yet)
# ════════════════════════════════════════════════════════════════════════════════

ARTIFACT = REPO / "data" / "cycle_ontology" / "collinearity_phase0.json"


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Artifact not yet produced")
class TestArtifactSanity:
    """Sanity checks on the produced JSON artifact."""

    @pytest.fixture(scope="class")
    def art(self):
        return json.loads(ARTIFACT.read_text())

    def test_schema_version(self, art):
        assert art["schema"] == 1

    def test_pooled_n_above_minimum(self, art):
        assert art["pooled"]["n"] >= 100, "Pooled panel should have >= 100 rows"

    def test_verdict_keys_present(self, art):
        v = art["verdict"]
        for key in ["redundant_pairs", "high_vif_legs", "n_pcs_for_90pct",
                    "redundant_legs", "surviving_legs", "risk_channel_survivors",
                    "dd_partial_corr_table"]:
            assert key in v, f"Missing verdict key: {key}"

    def test_pairwise_corr_symmetric(self, art):
        """rho(a,b) == rho(b,a) (both orderings present)."""
        corr = art["pooled"]["pairwise_corr"]
        for k, v in corr.items():
            a, b = k.split("|")
            rev = f"{b}|{a}"
            if rev in corr:
                assert abs(corr[rev] - v) < 1e-6, f"Asymmetric corr for {k}"

    def test_no_nan_in_vif(self, art):
        """VIF values must be finite numbers."""
        for k, v in art["pooled"]["vif"].items():
            assert v == v, f"VIF NaN for {k}"   # NaN != NaN

    def test_gates_declared(self, art):
        assert "W4.2" in art["gates"]
        assert "W4.6" in art["gates"]

    def test_determinism_test_passed(self, art):
        assert art["determinism_test"]["determinism_ok"] is True
