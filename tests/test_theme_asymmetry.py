"""tests/test_theme_asymmetry.py — TIL W3 per-leg asymmetry panel tests.

Tests:
  1. Each leg computes standalone on synthetic fixtures (no I/O).
  2. NO-COMPOSITE regression guard: emitted artifact must not contain
     score/composite/rank/total/overall keys at theme level.
  3. Tolerant-read: missing source files → null leg + stale flag, no crash.
  4. Absent thesis ledger → falsifier_clarity is null + stale.
  5. Band edge cases.
  6. Authority block present and correctly populated.
  7. Banned words ('validated') absent from user-facing text.
  8. EN/ZH notes present on every non-null leg.
  9. hard_caveat present in artifact.
 10. run_stage writes both data + site files without crash (tmp root, no real data).
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from engine.neuralweb.theme_asymmetry import (
    AUTHORITY_BLOCK,
    HARD_CAVEAT,
    SCHEMA,
    _leg_bottleneck_tightness,
    _leg_crowding_hazard,
    _leg_cyclical_dislocation,
    _leg_entry_cleanliness,
    _leg_falsifier_clarity,
    _leg_orthogonality,
    _leg_stale_consensus_gap,
    _null_leg,
    compose_asymmetry,
    run_stage,
)


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _foresight_rec(
    *,
    bottleneck_band: str | None = "TIGHT (FRED)",
    tightness: float | None = 0.8,
    demand_band: str | None = "ACCELERATING",
    broadening_state: str | None = "RISING",
    revision_level: str | None = "POSITIVE",
    revision_breadth: float | None = 0.6,
    est_drift_90d: float | None = 5.0,
) -> dict:
    return {
        "bottleneck_band": bottleneck_band,
        "tightness": tightness,
        "demand_band": demand_band,
        "broadening_state": broadening_state,
        "revision_level": revision_level,
        "revision_breadth": revision_breadth,
        "est_drift_90d": est_drift_90d,
    }


def _ti_rec(
    *,
    crowding: float = 0.3,
    drawdown_from_peak: float = -0.15,
    accel_z: float = 1.2,
    rs_pctile: float = 0.7,
    clean_quality: float = 0.75,
    overbought_value: float = 0.3,
    ext_abs: float | None = None,
    perf_60d_rel: float | None = 0.05,
) -> dict:
    return {
        "id": "test_basket",
        "components": {"crowding": crowding},
        "accel_z": accel_z,
        "rs_pctile": rs_pctile,
        "ext_abs": ext_abs,
        "perf": {"60d": {"rel": perf_60d_rel}},
        "textures": {
            "bull_age": {"drawdown_from_peak": drawdown_from_peak},
            "clean_entry": {"quality": clean_quality, "reasons": ["test"]},
            "overbought": {"value": overbought_value},
            "rollover_risk": {"risk": 0.0},
            "breadth_divergence": {"risk": 0.0},
        },
    }


def _radar_flag(accel: float = 1.5, dir_: int = 1) -> dict:
    return {"basket": "test_basket", "observable": {"accel": accel, "dir": dir_}}


def _narrative_data(stretched_share: float = 0.1, ipo_wave: bool = False) -> dict:
    return {"_universe": {"max_stretched_share": stretched_share, "ipo_wave": ipo_wave}}


def _div_log_rec(quadrant: str = "hidden-opportunity", money_pct: float = 0.5) -> dict:
    return {"quadrant": quadrant, "money_pct": money_pct, "asof": "2026-07-09"}


def _cov_data(avg_corr: float = 0.07) -> dict:
    return {"blocks": {"dispersion": {"avg_corr": avg_corr}}}


# ---------------------------------------------------------------------------
# Helper: assert leg structure
# ---------------------------------------------------------------------------

def _assert_leg(leg: dict, label: str) -> None:
    """A leg must have value, band, inputs, stale, note_en, note_zh."""
    assert "value" in leg, f"{label}: missing 'value'"
    assert "band" in leg, f"{label}: missing 'band'"
    assert "inputs" in leg, f"{label}: missing 'inputs'"
    assert "stale" in leg, f"{label}: missing 'stale'"
    assert "note_en" in leg, f"{label}: missing 'note_en'"
    assert "note_zh" in leg, f"{label}: missing 'note_zh'"
    assert isinstance(leg["inputs"], list), f"{label}: 'inputs' must be a list"
    assert isinstance(leg["stale"], bool), f"{label}: 'stale' must be bool"
    # band must be low|med|high|null
    assert leg["band"] in ("low", "med", "high", None), (
        f"{label}: band={leg['band']!r} not in (low, med, high, None)"
    )
    # value must be float or None
    if leg["value"] is not None:
        assert isinstance(leg["value"], float), f"{label}: value must be float or None"
        assert 0.0 <= leg["value"] <= 1.0, f"{label}: value {leg['value']} out of [0, 1]"


# ---------------------------------------------------------------------------
# NO-COMPOSITE REGRESSION GUARD
# ---------------------------------------------------------------------------

_BANNED_SCORE_KEYS = re.compile(
    r"\b(score|composite|rank|total|overall)\b",
    re.IGNORECASE,
)


def _scan_theme_keys(theme_block: dict) -> list[str]:
    """Return list of banned key names found at theme level (not inside legs)."""
    violations: list[str] = []
    for k in theme_block:
        if k == "legs":
            continue  # legs are allowed to have 'value'
        if _BANNED_SCORE_KEYS.search(k):
            violations.append(f"theme_level key: {k!r}")
    return violations


# ---------------------------------------------------------------------------
# 1. Leg a — bottleneck_tightness
# ---------------------------------------------------------------------------

class TestLegBottleneckTightness:
    def test_basic_tight(self):
        leg = _leg_bottleneck_tightness(
            _foresight_rec(bottleneck_band="TIGHT (FRED)", tightness=0.9),
            {"test_basket": _radar_flag(accel=1.5)},
            basket_ids=["test_basket"],
            theme_id="test",
        )
        _assert_leg(leg, "bottleneck_tightness.basic_tight")
        assert leg["stale"] is False
        assert leg["value"] is not None
        assert leg["band"] in ("med", "high")

    def test_null_when_no_foresight(self):
        leg = _leg_bottleneck_tightness(
            None,
            {},
            basket_ids=[],
            theme_id="test",
        )
        _assert_leg(leg, "bottleneck_tightness.null_foresight")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_no_radar_still_works(self):
        leg = _leg_bottleneck_tightness(
            _foresight_rec(),
            {},   # no radar flags
            basket_ids=[],
            theme_id="test",
        )
        _assert_leg(leg, "bottleneck_tightness.no_radar")
        assert leg["value"] is not None   # foresight alone is enough

    def test_loosening_gives_low_band(self):
        leg = _leg_bottleneck_tightness(
            _foresight_rec(bottleneck_band="LOOSENING", tightness=0.1),
            {"test_basket": _radar_flag(accel=0.3)},
            basket_ids=["test_basket"],
            theme_id="test",
        )
        _assert_leg(leg, "bottleneck_tightness.loosening")
        assert leg["band"] == "low"

    def test_none_band_uses_accel_only(self):
        leg = _leg_bottleneck_tightness(
            _foresight_rec(bottleneck_band=None, tightness=None),
            {"test_basket": _radar_flag(accel=2.5)},
            basket_ids=["test_basket"],
            theme_id="test",
        )
        _assert_leg(leg, "bottleneck_tightness.none_band_accel_only")
        assert leg["value"] is not None  # accel alone provides value


# ---------------------------------------------------------------------------
# 2. Leg b — stale_consensus_gap
# ---------------------------------------------------------------------------

class TestLegStaleConsensusGap:
    def test_activity_up_revisions_lagging(self):
        """Classic stale-consensus setup → high band."""
        leg = _leg_stale_consensus_gap(
            _foresight_rec(
                demand_band="ACCELERATING",
                revision_level="NEGATIVE",
                revision_breadth=-0.2,
                est_drift_90d=-3.0,
            ),
            basket_ids=[],
            revision_map={},
            membership_by_basket={},
        )
        _assert_leg(leg, "stale_consensus_gap.classic_setup")
        assert leg["band"] == "high"
        assert leg["stale"] is False

    def test_activity_up_revisions_following(self):
        """Activity and revisions both up → medium (gap narrowing)."""
        leg = _leg_stale_consensus_gap(
            _foresight_rec(
                demand_band="ACCELERATING",
                revision_level="POSITIVE",
                revision_breadth=0.7,
                est_drift_90d=8.0,
            ),
            basket_ids=[],
            revision_map={},
            membership_by_basket={},
        )
        _assert_leg(leg, "stale_consensus_gap.activity_up_revisions_following")
        assert leg["band"] == "med"

    def test_null_when_no_foresight(self):
        leg = _leg_stale_consensus_gap(
            None, basket_ids=[], revision_map={}, membership_by_basket={},
        )
        _assert_leg(leg, "stale_consensus_gap.null_foresight")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_member_downgrade_triggers_lagging(self):
        """Member-level downgrades push revisions_lagging even if breadth positive."""
        leg = _leg_stale_consensus_gap(
            _foresight_rec(
                demand_band="ACCELERATING",
                revision_level="POSITIVE",
                revision_breadth=0.05,  # barely positive
                est_drift_90d=0.5,
            ),
            basket_ids=["test_basket"],
            revision_map={
                "TICKER1": {"direction": "downgrading"},
                "TICKER2": {"direction": "downgrading"},
                "TICKER3": {"direction": "stable"},
            },
            membership_by_basket={"test_basket": ["TICKER1", "TICKER2", "TICKER3"]},
        )
        _assert_leg(leg, "stale_consensus_gap.member_downgrade")
        assert leg["band"] == "high"

    def test_no_activity_no_revisions_lagging(self):
        leg = _leg_stale_consensus_gap(
            _foresight_rec(
                demand_band=None,
                broadening_state="ROLLING",
                revision_level="POSITIVE",
                revision_breadth=0.4,
            ),
            basket_ids=[],
            revision_map={},
            membership_by_basket={},
        )
        _assert_leg(leg, "stale_consensus_gap.no_gap")
        assert leg["band"] == "low"


# ---------------------------------------------------------------------------
# 3. Leg c — cyclical_dislocation
# ---------------------------------------------------------------------------

class TestLegCyclicalDislocation:
    def test_deep_drawdown_positive_rs(self):
        """Deep drawdown + positive RS/accel → high dislocation."""
        ti_rec = _ti_rec(drawdown_from_peak=-0.35, accel_z=2.0, rs_pctile=0.75)
        leg = _leg_cyclical_dislocation([ti_rec], basket_ids=["test"])
        _assert_leg(leg, "cyclical_dislocation.deep_drawdown_positive_rs")
        assert leg["band"] in ("med", "high")

    def test_shallow_drawdown_low_rs(self):
        """Shallow drawdown + weak RS → low."""
        ti_rec = _ti_rec(drawdown_from_peak=-0.03, accel_z=-1.0, rs_pctile=0.2)
        leg = _leg_cyclical_dislocation([ti_rec], basket_ids=["test"])
        _assert_leg(leg, "cyclical_dislocation.shallow_drawdown")
        assert leg["band"] == "low"

    def test_null_when_no_ti_recs(self):
        leg = _leg_cyclical_dislocation([], basket_ids=[])
        _assert_leg(leg, "cyclical_dislocation.null_no_ti")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_multiple_baskets_uses_worst_drawdown(self):
        recs = [
            _ti_rec(drawdown_from_peak=-0.10, accel_z=1.0, rs_pctile=0.6),
            _ti_rec(drawdown_from_peak=-0.40, accel_z=1.5, rs_pctile=0.8),
        ]
        leg = _leg_cyclical_dislocation(recs, basket_ids=["b1", "b2"])
        _assert_leg(leg, "cyclical_dislocation.multi_basket")
        # worst drawdown (0.40) should push value high
        assert leg["value"] is not None
        assert leg["value"] > 0.5


# ---------------------------------------------------------------------------
# 4. Leg d — entry_cleanliness
# ---------------------------------------------------------------------------

class TestLegEntryCleanliness:
    def test_clean_entry(self):
        ti_rec = _ti_rec(clean_quality=0.85, overbought_value=0.2, ext_abs=0.0)
        leg = _leg_entry_cleanliness(
            [ti_rec], _narrative_data(stretched_share=0.0)
        )
        _assert_leg(leg, "entry_cleanliness.clean")
        assert leg["band"] in ("med", "high")

    def test_extended_entry(self):
        ti_rec = _ti_rec(clean_quality=0.3, overbought_value=0.9, ext_abs=2.5)
        leg = _leg_entry_cleanliness(
            [ti_rec], _narrative_data(stretched_share=0.8, ipo_wave=True)
        )
        _assert_leg(leg, "entry_cleanliness.extended")
        assert leg["band"] == "low"

    def test_null_when_no_ti(self):
        leg = _leg_entry_cleanliness([], _narrative_data())
        _assert_leg(leg, "entry_cleanliness.null_no_ti")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_value_clamped_to_unit_interval(self):
        ti_rec = _ti_rec(clean_quality=1.0, overbought_value=0.0, ext_abs=0.0)
        leg = _leg_entry_cleanliness([ti_rec], _narrative_data(stretched_share=0.0))
        _assert_leg(leg, "entry_cleanliness.clamp_upper")
        assert 0.0 <= leg["value"] <= 1.0

    def test_ipo_wave_penalizes(self):
        ti_rec_no_ipo = _ti_rec(clean_quality=0.7, overbought_value=0.3)
        ti_rec_ipo = _ti_rec(clean_quality=0.7, overbought_value=0.3)
        leg_no_ipo = _leg_entry_cleanliness([ti_rec_no_ipo], _narrative_data(ipo_wave=False))
        leg_ipo = _leg_entry_cleanliness([ti_rec_ipo], _narrative_data(ipo_wave=True))
        assert leg_no_ipo["value"] > leg_ipo["value"]


# ---------------------------------------------------------------------------
# 5. Leg e — crowding_hazard
# ---------------------------------------------------------------------------

class TestLegCrowdingHazard:
    def test_high_crowding_hype_risk(self):
        ti_rec = _ti_rec(crowding=0.8)
        leg = _leg_crowding_hazard(
            [ti_rec], _div_log_rec(quadrant="hype-risk")
        )
        _assert_leg(leg, "crowding_hazard.high")
        assert leg["band"] == "high"

    def test_low_crowding_hidden_opportunity(self):
        ti_rec = _ti_rec(crowding=0.1)
        leg = _leg_crowding_hazard(
            [ti_rec], _div_log_rec(quadrant="hidden-opportunity")
        )
        _assert_leg(leg, "crowding_hazard.low")
        assert leg["band"] == "low"

    def test_null_when_no_ti(self):
        leg = _leg_crowding_hazard([], None)
        _assert_leg(leg, "crowding_hazard.null_no_ti")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_no_div_log(self):
        ti_rec = _ti_rec(crowding=0.5)
        leg = _leg_crowding_hazard([ti_rec], None)
        _assert_leg(leg, "crowding_hazard.no_div_log")
        assert leg["value"] == pytest.approx(0.5)

    def test_hype_risk_boost(self):
        ti_rec = _ti_rec(crowding=0.5)
        leg_hype = _leg_crowding_hazard([ti_rec], _div_log_rec(quadrant="hype-risk"))
        leg_normal = _leg_crowding_hazard([ti_rec], None)
        assert leg_hype["value"] > leg_normal["value"]

    def test_hazard_note_contains_warning(self):
        ti_rec = _ti_rec(crowding=0.3)
        leg = _leg_crowding_hazard([ti_rec], None)
        assert "HAZARD" in leg["note_en"].upper() or "hazard" in leg["note_en"].lower()

    def test_crowding_capped_at_1(self):
        ti_rec = _ti_rec(crowding=0.9)
        leg = _leg_crowding_hazard([ti_rec], _div_log_rec(quadrant="hype-risk"))
        assert leg["value"] <= 1.0


# ---------------------------------------------------------------------------
# 6. Leg f — falsifier_clarity
# ---------------------------------------------------------------------------

class TestLegFalsifierClarity:
    def test_absent_ledger_gives_null_stale(self):
        """No thesis rows + stale note → null leg."""
        leg = _leg_falsifier_clarity(
            thesis_rows=[],
            thesis_stale=["thesis_ledger: pending W1 build"],
            theme_id="ai_semiconductors",
        )
        _assert_leg(leg, "falsifier_clarity.absent_ledger")
        assert leg["value"] is None
        assert leg["stale"] is True
        assert "W1" in leg["note_en"] or "pending" in leg["note_en"]

    def test_all_machine_checkable_armed(self):
        rows = [{
            "theme_id": "ai_semiconductors",
            "falsifiers": [
                {"machine_checkable": True, "check": {"kind": "price"}, "status": "ARMED"},
                {"machine_checkable": True, "check": {"kind": "macro"}, "status": "WATCHING"},
                {"machine_checkable": True, "check": {"kind": "rev"}, "status": "ARMED"},
            ],
        }]
        leg = _leg_falsifier_clarity(rows, thesis_stale=[], theme_id="ai_semiconductors")
        _assert_leg(leg, "falsifier_clarity.all_armed")
        assert leg["stale"] is False
        assert leg["band"] == "high"

    def test_no_machine_checkable(self):
        rows = [{
            "theme_id": "test",
            "falsifiers": [
                {"machine_checkable": False, "check": None, "status": "ARMED"},
                {"machine_checkable": False, "check": None, "status": "ARMED"},
            ],
        }]
        leg = _leg_falsifier_clarity(rows, thesis_stale=[], theme_id="test")
        _assert_leg(leg, "falsifier_clarity.no_machine_checkable")
        assert leg["band"] == "low"

    def test_fired_falsifiers_not_armed(self):
        rows = [{
            "theme_id": "test",
            "falsifiers": [
                {"machine_checkable": True, "check": {"kind": "x"}, "status": "FIRED"},
                {"machine_checkable": True, "check": {"kind": "y"}, "status": "ARMED"},
                {"machine_checkable": False, "check": None, "status": "ARMED"},
                {"machine_checkable": False, "check": None, "status": "ARMED"},
            ],
        }]
        leg = _leg_falsifier_clarity(rows, thesis_stale=[], theme_id="test")
        _assert_leg(leg, "falsifier_clarity.fired_not_armed")
        assert leg["value"] is not None
        # 2 of 4 machine-checkable → share_checkable=0.5
        # 1 of 2 machine-checkable is armed (not FIRED) → share_armed=0.5
        # value = 0.6*0.5 + 0.4*0.5 = 0.5 → med
        assert leg["band"] in ("low", "med")

    def test_wrong_theme_gives_null(self):
        rows = [{"theme_id": "other_theme", "falsifiers": [{"machine_checkable": True}]}]
        leg = _leg_falsifier_clarity(rows, thesis_stale=[], theme_id="nonexistent")
        _assert_leg(leg, "falsifier_clarity.wrong_theme")
        assert leg["value"] is None
        assert leg["stale"] is True


# ---------------------------------------------------------------------------
# 7. Leg g — orthogonality
# ---------------------------------------------------------------------------

class TestLegOrthogonality:
    def test_high_relative_return_high_orthogonality(self):
        ti_rec = _ti_rec(perf_60d_rel=0.35, accel_z=1.0)
        leg = _leg_orthogonality([ti_rec], _cov_data(avg_corr=0.05))
        _assert_leg(leg, "orthogonality.high_rel")
        assert leg["band"] in ("med", "high")

    def test_zero_relative_return_medium(self):
        ti_rec = _ti_rec(perf_60d_rel=0.0, accel_z=0.0)
        leg = _leg_orthogonality([ti_rec], _cov_data(avg_corr=0.1))
        _assert_leg(leg, "orthogonality.zero_rel")
        assert leg["band"] == "med"

    def test_negative_relative_return_low(self):
        ti_rec = _ti_rec(perf_60d_rel=-0.25, accel_z=-1.5)
        leg = _leg_orthogonality([ti_rec], _cov_data(avg_corr=0.3))
        _assert_leg(leg, "orthogonality.negative_rel")
        assert leg["band"] == "low"

    def test_no_ti_falls_back_to_universe_corr(self):
        """No theme_intel records → falls back to universe avg_corr."""
        leg = _leg_orthogonality([], _cov_data(avg_corr=0.07))
        _assert_leg(leg, "orthogonality.fallback_universe_corr")
        assert leg["value"] is not None
        assert "universe" in leg["note_en"].lower() or "proxy" in leg["note_en"].lower()

    def test_no_data_at_all_gives_null(self):
        leg = _leg_orthogonality([], {})
        _assert_leg(leg, "orthogonality.null_no_data")
        assert leg["value"] is None
        assert leg["stale"] is True

    def test_value_clamped(self):
        ti_rec = _ti_rec(perf_60d_rel=1.0)  # extreme
        leg = _leg_orthogonality([ti_rec], _cov_data(avg_corr=0.0))
        assert 0.0 <= leg["value"] <= 1.0


# ---------------------------------------------------------------------------
# 8. Null-leg helper
# ---------------------------------------------------------------------------

def test_null_leg_structure():
    leg = _null_leg(inputs=["source:field"], note_en="test", note_zh="测试")
    _assert_leg(leg, "_null_leg")
    assert leg["value"] is None
    assert leg["band"] is None
    assert leg["stale"] is True
    assert leg["note_en"] == "test"


# ---------------------------------------------------------------------------
# 9. Authority block
# ---------------------------------------------------------------------------

def test_authority_block():
    assert AUTHORITY_BLOCK["is_context_only"] is True
    assert AUTHORITY_BLOCK["may_rank"] is False
    assert AUTHORITY_BLOCK["may_gate"] is False
    assert AUTHORITY_BLOCK["may_size"] is False
    assert AUTHORITY_BLOCK["may_escalate"] is False


# ---------------------------------------------------------------------------
# 10. NO-COMPOSITE REGRESSION GUARD
# ---------------------------------------------------------------------------

class TestNoCompositeGuard:
    def _make_artifact_in_tmp(self, tmp_path: Path) -> dict:
        """Run compose_asymmetry against a minimal synthetic root."""
        # Create minimal source files
        _make_minimal_root(tmp_path)
        return compose_asymmetry(tmp_path)

    def test_no_banned_theme_level_keys(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        for theme in artifact.get("themes", []):
            violations = _scan_theme_keys(theme)
            assert not violations, (
                f"NO-COMPOSITE guard: banned keys found in theme "
                f"{theme.get('theme_id')!r}: {violations}"
            )

    def test_artifact_schema_correct(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        assert artifact.get("schema") == SCHEMA

    def test_hard_caveat_present(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        assert "hard_caveat" in artifact
        assert "not a buy score" in artifact["hard_caveat"].lower()

    def test_authority_block_in_artifact(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        auth = artifact.get("authority", {})
        assert auth.get("is_context_only") is True
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False

    def test_all_themes_present(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        themes = artifact.get("themes", [])
        assert len(themes) == 18, (
            f"Expected 18 canonical themes, got {len(themes)}"
        )

    def test_each_theme_has_7_legs(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        for theme in artifact.get("themes", []):
            legs = theme.get("legs", {})
            assert len(legs) == 7, (
                f"Theme {theme.get('theme_id')!r} has {len(legs)} legs, expected 7"
            )
            expected = {
                "bottleneck_tightness", "stale_consensus_gap", "cyclical_dislocation",
                "entry_cleanliness", "crowding_hazard", "falsifier_clarity", "orthogonality",
            }
            assert set(legs.keys()) == expected, (
                f"Theme {theme.get('theme_id')!r} unexpected leg keys: "
                f"{set(legs.keys()) - expected}"
            )

    def test_all_legs_have_required_structure(self, tmp_path):
        artifact = self._make_artifact_in_tmp(tmp_path)
        for theme in artifact.get("themes", []):
            for leg_name, leg in theme.get("legs", {}).items():
                _assert_leg(leg, f"{theme.get('theme_id')}.{leg_name}")


# ---------------------------------------------------------------------------
# 11. Tolerant-read: absent sources → no crash, null legs + stale flags
# ---------------------------------------------------------------------------

class TestTolerantRead:
    def test_empty_root_no_crash(self, tmp_path):
        """Completely empty root → artifact with stale_legs, no exception."""
        # Create just the crosswalk so themes are composed
        _make_minimal_crosswalk(tmp_path)
        artifact = compose_asymmetry(tmp_path)
        assert artifact.get("schema") == SCHEMA
        stale = artifact.get("stale_legs", [])
        assert len(stale) > 0, "Expected stale_legs when sources are absent"

    def test_thesis_ledger_absent(self, tmp_path):
        """Absent thesis_ledger → falsifier_clarity null + stale note."""
        _make_minimal_root(tmp_path)
        # Remove thesis ledger if it exists
        ledger_path = tmp_path / "data/neuralweb/theme_thesis_ledger.jsonl"
        if ledger_path.exists():
            ledger_path.unlink()
        artifact = compose_asymmetry(tmp_path)
        themes = artifact.get("themes", [])
        assert themes, "Expected at least one theme"
        for theme in themes:
            leg_f = theme["legs"]["falsifier_clarity"]
            _assert_leg(leg_f, f"{theme['theme_id']}.falsifier_clarity")
            assert leg_f["value"] is None
            assert leg_f["stale"] is True
            assert "W1" in leg_f["note_en"] or "pending" in leg_f["note_en"]

    def test_finnhub_absent_not_crash(self, tmp_path):
        """Absent Finnhub parquet → stale leg note but no crash."""
        _make_minimal_root(tmp_path)
        finnhub_path = tmp_path / "data/finnhub/recommendation.parquet"
        if finnhub_path.exists():
            finnhub_path.unlink()
        artifact = compose_asymmetry(tmp_path)
        # Just check it doesn't crash and stale_legs mentions finnhub
        stale = artifact.get("stale_legs", [])
        assert any("finnhub" in s.lower() for s in stale), (
            f"Expected finnhub stale leg, got: {stale}"
        )

    def test_missing_foresight_all_legs_null(self, tmp_path):
        """No foresight_cascade → bottleneck + consensus gap legs null."""
        _make_minimal_crosswalk(tmp_path)
        # Only create baskets (no foresight)
        _write_json(tmp_path / "site/basketdata/baskets.json", _minimal_baskets())
        _write_json(tmp_path / "site/basketdata/radar.json", _minimal_radar())
        _write_json(tmp_path / "site/basketdata/narrative_emergence.json", _minimal_narrative())
        _write_json(tmp_path / "site/neuralwebdata/covariance_spine.json", _minimal_cov())
        _write_jsonl(tmp_path / "data/foresight/divergence_log.jsonl", [])
        artifact = compose_asymmetry(tmp_path)
        for theme in artifact.get("themes", []):
            leg_a = theme["legs"]["bottleneck_tightness"]
            leg_b = theme["legs"]["stale_consensus_gap"]
            assert leg_a["value"] is None
            assert leg_b["value"] is None


# ---------------------------------------------------------------------------
# 12. Banned words — 'validated' must not appear in user-facing strings
# ---------------------------------------------------------------------------

def test_no_validated_word_in_notes(tmp_path):
    _make_minimal_root(tmp_path)
    artifact = compose_asymmetry(tmp_path)
    _check_no_validated(artifact)


def _check_no_validated(obj: Any, path: str = "") -> None:
    if isinstance(obj, str):
        assert "validated" not in obj.lower(), (
            f"Banned word 'validated' found at {path!r}: {obj!r}"
        )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_no_validated(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_no_validated(item, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# 13. EN/ZH notes on every non-null leg
# ---------------------------------------------------------------------------

def test_non_null_legs_have_notes(tmp_path):
    _make_minimal_root(tmp_path)
    artifact = compose_asymmetry(tmp_path)
    for theme in artifact.get("themes", []):
        for leg_name, leg in theme.get("legs", {}).items():
            label = f"{theme.get('theme_id')}.{leg_name}"
            if leg["value"] is not None:
                assert leg.get("note_en"), f"{label}: non-null leg missing note_en"
                assert leg.get("note_zh"), f"{label}: non-null leg missing note_zh"


# ---------------------------------------------------------------------------
# 14. run_stage writes both files without crash
# ---------------------------------------------------------------------------

def test_run_stage_writes_files(tmp_path):
    _make_minimal_root(tmp_path)
    # Should not raise
    run_stage(tmp_path)

    data_path = tmp_path / "data/neuralweb/theme_asymmetry.json"
    site_path = tmp_path / "site/neuralwebdata/theme_asymmetry.json"
    assert data_path.exists(), "data artifact not written"
    assert site_path.exists(), "site artifact not written"

    # Both should be parseable JSON with correct schema
    d = json.loads(data_path.read_text())
    s = json.loads(site_path.read_text())
    assert d.get("schema") == SCHEMA
    assert s.get("schema") == SCHEMA


def test_run_stage_empty_root_no_crash(tmp_path):
    """Completely empty root: run_stage must not raise."""
    _make_minimal_crosswalk(tmp_path)
    run_stage(tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# Fixture builder helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _make_minimal_crosswalk(root: Path) -> None:
    import yaml
    crosswalk = {
        "version": 1,
        "date": "2026-07-09",
        "themes": [
            {
                "id": f"theme_{i:02d}",
                "name_en": f"Theme {i}",
                "name_zh": f"主题{i}",
                "foresight_id": f"theme_{i:02d}",
                "basket_ids": [f"basket_{i:02d}"],
                "subsector_keys": [],
                "citrini_basket_ids": [],
            }
            for i in range(18)
        ],
    }
    p = root / "config/theme_crosswalk.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(crosswalk), encoding="utf-8")


def _minimal_baskets() -> dict:
    """Minimal baskets.json with theme_intel for 18 synthetic baskets."""
    ti_themes = []
    for i in range(18):
        ti_themes.append({
            "id": f"basket_{i:02d}",
            "name": f"Basket {i}",
            "name_zh": f"篮子{i}",
            "score": 50,
            "label": "neutral",
            "label_en": "NEUTRAL",
            "label_zh": "中性",
            "components": {"crowding": 0.3, "trend": 0.5},
            "accel_z": 0.5,
            "rs_pctile": 0.5,
            "ext_abs": None,
            "perf": {"5d": {"rel": 0.01}, "20d": {"rel": 0.02},
                     "60d": {"rel": 0.05}, "ytd": {"rel": 0.1}},
            "textures": {
                "bull_age": {"drawdown_from_peak": -0.10, "in_bull": True},
                "clean_entry": {"flag": True, "quality": 0.7, "reasons": ["test"]},
                "overbought": {"value": 0.4, "band": "normal"},
                "rollover_risk": {"risk": 0.0},
                "breadth_divergence": {"risk": 0.0},
            },
        })
    return {
        "as_of": "2026-07-09",
        "baskets": [],
        "theme_intel": {
            "as_of": "2026-07-09",
            "themes": ti_themes,
        },
    }


def _minimal_foresight(n: int = 18) -> dict:
    themes = []
    for i in range(n):
        themes.append({
            "theme": f"theme_{i:02d}",
            "name": f"Theme {i}",
            "stage": "BROADENING",
            "bottleneck_band": "TIGHT (FRED)",
            "tightness": 0.7,
            "demand_band": "ACCELERATING",
            "broadening_state": "RISING",
            "revision_level": "POSITIVE",
            "revision_breadth": 0.5,
            "est_drift_90d": 3.0,
            "language_accel": 1.2,
        })
    return {"asof": "2026-07-09", "n_themes": n, "themes": themes}


def _minimal_radar(n: int = 18) -> dict:
    flags = [
        {
            "id": f"flag_{i}",
            "basket": f"basket_{i:02d}",
            "state": "POSITIVE_DIVERGENCE",
            "observable": {"accel": 1.2, "dir": 1, "z": 0.8},
        }
        for i in range(n)
    ]
    return {
        "schema": "neuralweb.radar.v1",
        "is_context_only": True,
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T00:00:00Z",
        "flags": flags,
        "hypotheses": [],
        "coverage": {},
    }


def _minimal_narrative() -> dict:
    return {
        "schema": "neuralweb.narrative_emergence.v1",
        "is_context_only": True,
        "as_of": "2026-07-09",
        "narratives": [],
    }


def _minimal_cov() -> dict:
    return {
        "schema": "neuralweb.covariance_spine.v1",
        "as_of": "2026-07-09",
        "blocks": {
            "dispersion": {"avg_corr": 0.07, "state": "lean_in"},
            "factors": {"dominant_factor_pc_share": 0.5},
            "rates": {},
            "lobes": {"effective_independent_lobes": 1.0, "clusters": [], "highest_overlap_pairs": []},
        },
        "authority": AUTHORITY_BLOCK,
    }


def _make_minimal_root(root: Path) -> None:
    """Create minimal synthetic sources for compose_asymmetry."""
    _make_minimal_crosswalk(root)
    _write_json(root / "site/basketdata/baskets.json", _minimal_baskets())
    _write_json(root / "site/basketdata/foresight_cascade.json", _minimal_foresight())
    _write_json(root / "site/basketdata/radar.json", _minimal_radar())
    _write_json(root / "site/basketdata/narrative_emergence.json", _minimal_narrative())
    _write_json(root / "site/neuralwebdata/covariance_spine.json", _minimal_cov())
    _write_jsonl(root / "data/foresight/divergence_log.jsonl", [])
    # Thesis ledger absent (W1 pending) — intentional
