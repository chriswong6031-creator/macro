"""engine.foresight_sizing — W4a tests.

Required test targets from spec:
  (e) [in test_foresight_enb.py] ENB math on synthetic 3-theme correlation fixture
  (f) sizing factors multiply and surface (stage_cap × earliness_tilt × cluster_dilution)
  (g) de-risk fires on synthetic glut+crowding

Plus regression tests from original test file.
"""
from __future__ import annotations

from unittest import mock

import pytest

from engine import foresight_sizing as fz


def _row(**kw):
    base = {"stage": "WATCH", "bottleneck_band": "AWAITING_DATA", "score": 40,
            "revision_breadth": 0.0, "entry_ready": False, "glut_band": None,
            "demand_band": None}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# (f) Sizing factors multiply and are surfaced in size_detail
# ---------------------------------------------------------------------------

def test_size_mult_three_factors_multiply():
    """size_mult = stage_cap × earliness_tilt × cluster_dilution (all surfaced)."""
    r = _row(stage="PRECIPICE", bottleneck_band="TIGHT", score=80, revision_breadth=0.05)
    p = fz._posture(r)
    # No cluster dilution (factor=1.0), no earliness (absent → tilt=1.0)
    mult = fz._size_mult(r, p, earliness=None, cluster_dilution=1.0)
    assert mult == pytest.approx(0.45, abs=0.01)   # stage cap: PRECIPICE=0.45

    # With earliness=1.0 (earliest) → tilt=1.25 → mult = 0.45 × 1.25 × 1.0 = 0.5625 → capped at 1.0
    mult_early = fz._size_mult(r, p, earliness=1.0, cluster_dilution=1.0)
    assert mult_early > mult   # earlier → larger multiplier

    # With earliness=0.0 (latest) → tilt=0.75 → mult = 0.45 × 0.75 × 1.0 = 0.3375
    mult_late = fz._size_mult(r, p, earliness=0.0, cluster_dilution=1.0)
    assert mult_late < mult   # later → smaller multiplier

    # With cluster_dilution=0.2 (5 themes, ENB≈1) → mult × 0.2
    mult_diluted = fz._size_mult(r, p, earliness=None, cluster_dilution=0.2)
    assert mult_diluted == pytest.approx(0.45 * 1.0 * 0.2, abs=0.01)


def test_size_detail_exposes_all_factors():
    """annotate_sizing should populate size_detail with earliness_tilt and cluster_dilution."""
    r = _row(stage="PRECIPICE", bottleneck_band="TIGHT", score=70, revision_breadth=0.05)
    cas = {"themes": [r]}
    # Mock ENB and earliness to known values
    with mock.patch("engine.foresight_sizing._load_enb_data", return_value=({}, {})), \
         mock.patch("engine.foresight_sizing._load_earliness_map", return_value={}):
        out = fz.annotate_sizing(cas)
    r2 = out["themes"][0]
    assert "size_detail" in r2
    detail = r2["size_detail"]
    assert "earliness_tilt" in detail
    assert "cluster_dilution" in detail
    assert "size_mult_breakdown" in detail
    breakdown = detail["size_mult_breakdown"]
    assert "stage_cap" in breakdown
    assert "earliness_tilt" in breakdown
    assert "cluster_dilution" in breakdown
    assert "product" in breakdown


def test_earliness_tilt_neutral_when_absent():
    """When earliness is None, tilt should be 1.0 (neutral — no information removed)."""
    assert fz._earliness_tilt(None) == pytest.approx(1.0)


def test_earliness_tilt_max_when_earliest():
    assert fz._earliness_tilt(1.0) == pytest.approx(1.25)


def test_earliness_tilt_min_when_latest():
    assert fz._earliness_tilt(0.0) == pytest.approx(0.75)


def test_cluster_dilution_singleton_no_dilution():
    """A theme in a cluster of size 1 (or not in clusters) → factor=1.0."""
    factor, detail = fz._cluster_dilution_factor("theme_a", {}, {})
    assert factor == 1.0

    # Explicitly in a singleton cluster
    factor2, _ = fz._cluster_dilution_factor("theme_a", {"theme_a": "c0"}, {"c0": 1.0})
    assert factor2 == 1.0


def test_cluster_dilution_five_themes_enb1():
    """5 themes in one cluster with ENB=1.0 → dilution = min(1, 1/5) = 0.2."""
    clusters = {f"t{i}": "c0" for i in range(5)}
    enb_by_cluster = {"c0": 1.0}
    factor, detail = fz._cluster_dilution_factor("t0", clusters, enb_by_cluster)
    assert factor == pytest.approx(0.2, abs=0.01)
    assert detail["cluster_size"] == 5
    assert detail["enb_cluster"] == pytest.approx(1.0, abs=0.1)


def test_cluster_dilution_five_themes_enb3():
    """5 themes in one cluster with ENB=3.0 → dilution = min(1, 3/5) = 0.6."""
    clusters = {f"t{i}": "c0" for i in range(5)}
    enb_by_cluster = {"c0": 3.0}
    factor, _ = fz._cluster_dilution_factor("t0", clusters, enb_by_cluster)
    assert factor == pytest.approx(0.6, abs=0.01)


# ---------------------------------------------------------------------------
# (g) De-risk fires on synthetic glut + crowding
# ---------------------------------------------------------------------------

def test_derisk_fires_on_glut_forming_plus_crowded():
    """TRIM fires when glut_band=GLUT_FORMING AND revision_breadth > HIGH_ATTENTION."""
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=65,
             glut_band="GLUT_FORMING", revision_breadth=0.8)
    p = fz._posture(r)
    assert p["band"] == "TRIM" and p["derisk"] is True


def test_derisk_does_not_fire_glut_without_crowding():
    """GLUT_FORMING alone (not crowded) should NOT trigger TRIM."""
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=65,
             glut_band="GLUT_FORMING", revision_breadth=0.2)  # below HIGH_ATTENTION
    p = fz._posture(r)
    assert p["band"] != "TRIM" and p["derisk"] is False


def test_derisk_does_not_fire_crowded_without_glut():
    """Crowding alone (no glut) should NOT trigger TRIM."""
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=65,
             glut_band=None, revision_breadth=0.9)
    p = fz._posture(r)
    assert p["band"] != "TRIM" and p["derisk"] is False


def test_exit_fires_on_glut_risk_stage():
    """EXIT fires on GLUT-RISK stage regardless of crowding."""
    r = _row(stage="GLUT-RISK", bottleneck_band="LOOSE", score=40, revision_breadth=0.1)
    p = fz._posture(r)
    assert p["band"] == "EXIT" and p["derisk"] is True


def test_annotate_sizing_size_mult_zero_on_derisk():
    """size_mult must be 0.0 when derisk=True."""
    r = _row(stage="GLUT-RISK", bottleneck_band="LOOSE", score=40, revision_breadth=0.6)
    cas = {"themes": [r]}
    with mock.patch("engine.foresight_sizing._load_enb_data", return_value=({}, {})), \
         mock.patch("engine.foresight_sizing._load_earliness_map", return_value={}):
        out = fz.annotate_sizing(cas)
    assert out["themes"][0]["size_mult"] == 0.0
    assert out["themes"][0]["derisk"] is True


# ---------------------------------------------------------------------------
# Regression: original posture tests
# ---------------------------------------------------------------------------

def test_precipice_physical_is_a_small_starter():
    r = _row(stage="PRECIPICE", bottleneck_band="TIGHT", score=80, revision_breadth=0.05)
    p = fz._posture(r)
    assert p["band"] == "STARTER" and p["derisk"] is False
    # Base mult without earliness/dilution should be capped at 0.45
    assert fz._size_mult(r, p) == pytest.approx(0.45, abs=0.01)


def test_entry_ready_is_the_add_full_size():
    r = _row(stage="BROADENING", bottleneck_band="TIGHT", score=70, entry_ready=True)
    p = fz._posture(r)
    assert p["band"] == "ADD"
    assert fz._size_mult(r, p) == pytest.approx(0.70, abs=0.01)


def test_glut_risk_forces_exit():
    r = _row(stage="GLUT-RISK", bottleneck_band="LOOSE", score=40, revision_breadth=0.6)
    p = fz._posture(r)
    assert p["band"] == "EXIT" and p["derisk"] is True
    assert fz._size_mult(r, p) == 0.0


def test_rerating_holds_no_add():
    r = _row(stage="RE-RATING", bottleneck_band="TIGHT", score=60, revision_breadth=0.8)
    p = fz._posture(r)
    assert p["band"] == "HOLD" and p["derisk"] is False


def test_text_only_precipice_is_watch_capped():
    r = _row(stage="PRECIPICE", bottleneck_band="AWAITING_DATA", score=50,
             score_detail={"physical_confirmed": False})
    p = fz._posture(r)
    assert p["band"] == "WATCH"
    assert fz._size_mult(r, p) <= fz.TEXT_ONLY_SIZE_CAP


def test_annotate_adds_fields_and_is_none_safe():
    assert fz.annotate_sizing(None) is None
    assert fz.annotate_sizing({"themes": []}) == {"themes": []}
    cas = {"themes": [_row(stage="PRECIPICE", bottleneck_band="TIGHT",
                           score=80, revision_breadth=0.05)]}
    with mock.patch("engine.foresight_sizing._load_enb_data", return_value=({}, {})), \
         mock.patch("engine.foresight_sizing._load_earliness_map", return_value={}):
        out = fz.annotate_sizing(cas)
    r = out["themes"][0]
    assert r["size_band"] == "STARTER" and r["derisk"] is False and "size_mult" in r
    assert out["sizing"]["n_constructive"] == 1


def test_variant_thesis_stages_count_constructive_but_do_not_size():
    """Integration regression: PRECIPICE (fingerprint)/(text) variants must count in
    the CONSTRUCTIVE set (the ENB concentration line renders) while their posture
    stays WATCH with the honest unconfirmed-evidence note (never STARTER/CORE)."""
    from engine.foresight_sizing import _is_thesis_stage, _posture
    assert _is_thesis_stage("PRECIPICE (fingerprint)")
    assert _is_thesis_stage("BROADENING (text)")
    assert not _is_thesis_stage("RE-RATING")
    p = _posture({"stage": "PRECIPICE (fingerprint)", "glut_band": None,
                  "revision_breadth": 0.1, "entry_ready": False,
                  "bottleneck_band": "TIGHTENING (fingerprint)"})
    assert p["band"] == "WATCH"
    assert "unconfirmed" in p["note"]
    c = _posture({"stage": "BROADENING (text)", "glut_band": None,
                  "revision_breadth": 0.2, "entry_ready": False,
                  "bottleneck_band": "TIGHT (text)"})
    assert c["band"] == "WATCH"


def test_load_enb_data_unpacks_corr_matrix_3tuple():
    """Signature-drift regression: _build_corr_matrix returns a 3-tuple (W4a F3);
    _load_enb_data must not silently lose every per-cluster ENB to an unpack error."""
    from engine.foresight_sizing import _load_enb_data
    rows = [{"theme": "memory_storage", "stage": "PRECIPICE (fingerprint)", "score": 50}]
    clusters, enb_by_cluster = _load_enb_data(rows)
    if clusters:  # live data present in this checkout
        assert enb_by_cluster, "per-cluster ENB silently empty — unpack drift regressed"
