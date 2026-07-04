"""Hermetic tests for engine.oracle.contract — validate_payload + stamp_payload.

All tests are synthetic (no network, no real data reads).
Design targets per task W-B2:
  - Validator passes the current real oracle_state shape (fixture with unknown
    additive fields → PASS).
  - Missing core field → FAIL.
  - Banned-implication key without validated lineage → FAIL.
  - Stale asof → FAIL.
  - Nightly refuses to overwrite the prior payload on validation failure.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.oracle.contract import (
    BANNED_IMPLICATION_KEYS,
    CONFIDENCE_CLASSES,
    MAX_AGE_HOURS,
    PAYLOAD_VERSION,
    classify_lineage,
    stamp_payload,
    validate_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRESH_ASOF = datetime.now(timezone.utc).strftime("%Y-%m-%d")

_STALE_ASOF = (datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS + 1)).strftime(
    "%Y-%m-%d"
)


def _valid_payload(**overrides) -> dict:
    """Minimal valid oracle_state payload."""
    base = {
        "schema": "oracle_state.v1",
        "payload_version": "1.0.0",
        "asof": _FRESH_ASOF,
        "regime": {"n_active_complexes": 2, "breadth": 0.61, "vix_regime": 0.38},
        "complexes": [],
        "active_episodes": [
            {
                "node": "XLK",
                "direction": "out",
                "tier": "onset",
                "onset_date": _FRESH_ASOF,
                "confirmed_date": None,
                "two_sided": False,
                "pair": None,
                "survivorship_flagged": False,
                "base_rate_context": None,
                "analogues": None,
            }
        ],
        "onset_watchlist": [],
        "disclaimers": {
            "display_only": True,
            "error_rates": {
                "onset_to_confirmed_conversion": 0.997,
                "false_start_rate": 0.38,
            },
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Happy path — current oracle_state shape passes
# ---------------------------------------------------------------------------

def test_valid_minimal_payload_passes():
    """Minimal valid payload must pass the validator."""
    ok, errs = validate_payload(_valid_payload())
    assert ok, f"Expected pass, got errors: {errs}"
    assert errs == []


def test_valid_payload_with_unknown_additive_fields_passes():
    """Tolerant-reader: unknown fields from parallel waves must NOT cause errors."""
    payload = _valid_payload()
    # Simulate A3 regime_tag wave (additive)
    payload["regime_tag"] = "rotation"
    # Simulate B1 personality wave (additive on episodes)
    payload["active_episodes"][0]["personality_class"] = "mean_reverter"
    payload["active_episodes"][0]["personality_source"] = "B1-wave"
    ok, errs = validate_payload(payload)
    assert ok, f"Unknown additive fields should not fail; errors: {errs}"


def test_real_oracle_state_shape_passes(tmp_path):
    """Fixture matching the real oracle_state.json top-level structure passes."""
    # Build a fixture that mirrors the actual shape from the live file
    payload = {
        "schema": "oracle_state.v1",
        "asof": _FRESH_ASOF,
        "regime": {"n_active_complexes": 7, "breadth": 0.6107, "vix_regime": 0.377},
        "complexes": [
            {
                "id": "ai_compute",
                "name": "AI Compute Complex",
                "name_zh": "AI算力复合体",
                "state": "active_out",
                "tier": "undeniable",
                "direction": "out",
                "n_members_active": 6,
            }
        ],
        "active_episodes": [
            {
                "node": "Aging Population & Longevity",
                "direction": "in",
                "tier": "confirmed",
                "onset_date": "2026-06-26",
                "confirmed_date": "2026-07-02",
                "two_sided": False,
                "pair": None,
                "survivorship_flagged": True,
                "base_rate_context": None,
                "analogues": None,
            }
        ],
        "onset_watchlist": [],
        "disclaimers": {
            "display_only": True,
            "error_rates": {
                "onset_to_confirmed_conversion": 0.9974,
                "false_start_rate": 0.381,
            },
        },
    }
    ok, errs = validate_payload(payload)
    assert ok, f"Real oracle_state shape should pass; errors: {errs}"


# ---------------------------------------------------------------------------
# 2. Missing required fields → FAIL
# ---------------------------------------------------------------------------

def test_missing_asof_fails():
    payload = _valid_payload()
    del payload["asof"]
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("asof" in e for e in errs)


def test_missing_disclaimers_fails():
    payload = _valid_payload()
    del payload["disclaimers"]
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("disclaimers" in e for e in errs)


def test_missing_active_episodes_fails():
    payload = _valid_payload()
    del payload["active_episodes"]
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("active_episodes" in e for e in errs)


def test_display_only_false_fails():
    payload = _valid_payload()
    payload["disclaimers"]["display_only"] = False
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("display_only" in e for e in errs)


def test_display_only_missing_fails():
    payload = _valid_payload()
    del payload["disclaimers"]["display_only"]
    ok, errs = validate_payload(payload)
    assert not ok


def test_error_rates_not_dict_fails():
    payload = _valid_payload()
    payload["disclaimers"]["error_rates"] = "not a dict"
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("error_rates" in e for e in errs)


def test_error_rates_non_numeric_fails():
    payload = _valid_payload()
    payload["disclaimers"]["error_rates"]["false_start_rate"] = "high"
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("numeric" in e for e in errs)


def test_episode_missing_node_fails():
    payload = _valid_payload()
    payload["active_episodes"][0]["node"] = None
    ok, errs = validate_payload(payload)
    assert not ok


def test_episode_missing_onset_date_fails():
    payload = _valid_payload()
    del payload["active_episodes"][0]["onset_date"]
    ok, errs = validate_payload(payload)
    assert not ok


def test_active_episodes_not_list_fails():
    payload = _valid_payload()
    payload["active_episodes"] = "not a list"
    ok, errs = validate_payload(payload)
    assert not ok


# ---------------------------------------------------------------------------
# 3. Banned-implication keys without validated lineage → FAIL
# ---------------------------------------------------------------------------

def test_banned_key_forecast_at_top_level_fails():
    payload = _valid_payload()
    payload["forecast_return"] = 0.05
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("forecast" in e for e in errs)


def test_banned_key_predicted_in_episode_fails():
    payload = _valid_payload()
    payload["active_episodes"][0]["predicted_gain"] = 0.02
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("predicted" in e for e in errs)


def test_banned_key_target_in_nested_dict_fails():
    payload = _valid_payload()
    payload["regime"]["price_target"] = 5000
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("target" in e for e in errs)


def test_banned_key_expected_return_fails():
    payload = _valid_payload()
    payload["active_episodes"][0]["expected_return"] = 0.03
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("expected_return" in e for e in errs)


def test_banned_key_with_validated_lineage_passes():
    """A banned-implication key IS allowed when confidence_class == 'validated'."""
    payload = _valid_payload()
    # Inject into an item that claims validated lineage
    payload["active_episodes"][0]["confidence_class"] = "validated"
    payload["active_episodes"][0]["expected_return"] = 0.05
    ok, errs = validate_payload(payload)
    assert ok, f"Validated lineage should allow banned key; errors: {errs}"


# ---------------------------------------------------------------------------
# 4. Stale asof → FAIL
# ---------------------------------------------------------------------------

def test_stale_asof_fails():
    payload = _valid_payload(asof=_STALE_ASOF)
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("STALE" in e or "stale" in e.lower() for e in errs)


def test_fresh_asof_passes():
    payload = _valid_payload(asof=_FRESH_ASOF)
    ok, errs = validate_payload(payload)
    assert ok, f"Fresh asof should pass; errors: {errs}"


def test_stale_check_uses_provided_now():
    """validate_payload's as_of_now parameter overrides wall-clock."""
    # Use an asof 24h ago — this would pass normally (< 48h)
    past_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d")
    payload = _valid_payload(asof=past_24h)
    # But supply a "now" that is 30h after that, making it stale relative to our clock
    fake_now = datetime.now(timezone.utc) + timedelta(hours=30)
    ok, errs = validate_payload(payload, as_of_now=fake_now)
    # 24h past asof + 30h advance = 54h > 48h → stale
    assert not ok
    assert any("STALE" in e or "stale" in e.lower() for e in errs)


# ---------------------------------------------------------------------------
# 5. Onset alert with null false_start_rate → FAIL (NEVER guarantee b)
# ---------------------------------------------------------------------------

def test_onset_alert_null_false_start_rate_fails():
    """Active onset episode with null false_start_rate violates NEVER guarantee b."""
    payload = _valid_payload()
    # onset episode is already in the fixture; null out the error rate
    payload["disclaimers"]["error_rates"]["false_start_rate"] = None
    ok, errs = validate_payload(payload)
    assert not ok
    assert any("false_start_rate" in e for e in errs)


def test_confirmed_episode_null_false_start_rate_passes():
    """A payload with only confirmed episodes (no onset) does not require
    a numeric false_start_rate."""
    payload = _valid_payload()
    payload["active_episodes"][0]["tier"] = "confirmed"
    payload["disclaimers"]["error_rates"]["false_start_rate"] = None
    ok, errs = validate_payload(payload)
    assert ok, f"No onset episode; null false_start_rate should pass. Errors: {errs}"


# ---------------------------------------------------------------------------
# 6. classify_lineage helpers
# ---------------------------------------------------------------------------

def test_classify_onset_in_is_display_with_edge():
    result = classify_lineage("ep_in_onset_21d")
    assert result["confidence_class"] == "display_with_edge"
    assert "P3" in result["lineage"]


def test_classify_onset_out_is_display_with_edge():
    result = classify_lineage("ep_out_onset_5d")
    assert result["confidence_class"] == "display_with_edge"


def test_classify_routing_survivor_is_display_with_edge():
    result = classify_lineage("software__ai_compute__5d")
    assert result["confidence_class"] == "display_with_edge"
    assert "P3b" in result["lineage"]


def test_classify_confirmed_primary_is_descriptive():
    """P3 confirmed primaries are NULL → descriptive."""
    result = classify_lineage("ep_in_confirmed_21d")
    assert result["confidence_class"] == "descriptive"


def test_classify_unknown_compound_is_descriptive():
    result = classify_lineage("some_made_up_compound_X")
    assert result["confidence_class"] == "descriptive"


def test_classify_non_survivor_routing_cell_is_exploratory():
    """A routing cell in the right format but not in the survivor set → exploratory."""
    result = classify_lineage("energy_commodities__healthcare__5d")
    assert result["confidence_class"] == "exploratory"


# ---------------------------------------------------------------------------
# 7. stamp_payload
# ---------------------------------------------------------------------------

def test_stamp_payload_adds_version():
    payload = _valid_payload()
    del payload["payload_version"]
    stamp_payload(payload)
    assert payload["payload_version"] == PAYLOAD_VERSION


def test_stamp_payload_does_not_overwrite_existing_version():
    payload = _valid_payload()
    payload["payload_version"] = "9.9.9"
    stamp_payload(payload)
    assert payload["payload_version"] == "9.9.9"


def test_stamp_payload_adds_confidence_class_to_episodes():
    payload = _valid_payload()
    # episode has onset + out → ep_out_onset_5d → display_with_edge
    del payload["payload_version"]
    stamp_payload(payload)
    ep = payload["active_episodes"][0]
    assert ep["confidence_class"] == "display_with_edge"
    assert "lineage" in ep


def test_stamp_payload_does_not_overwrite_existing_confidence_class():
    """Parallel wave already stamped confidence_class → do not overwrite."""
    payload = _valid_payload()
    payload["active_episodes"][0]["confidence_class"] = "validated"
    stamp_payload(payload)
    assert payload["active_episodes"][0]["confidence_class"] == "validated"


def test_stamp_payload_onset_in_direction():
    payload = _valid_payload()
    payload["active_episodes"][0]["direction"] = "in"
    payload["active_episodes"][0]["tier"] = "onset"
    if "confidence_class" in payload["active_episodes"][0]:
        del payload["active_episodes"][0]["confidence_class"]
    stamp_payload(payload)
    assert payload["active_episodes"][0]["confidence_class"] == "display_with_edge"


def test_stamp_payload_confirmed_direction():
    """Confirmed tier maps to descriptive (primaries NULL per P3)."""
    payload = _valid_payload()
    payload["active_episodes"][0]["direction"] = "in"
    payload["active_episodes"][0]["tier"] = "confirmed"
    if "confidence_class" in payload["active_episodes"][0]:
        del payload["active_episodes"][0]["confidence_class"]
    stamp_payload(payload)
    assert payload["active_episodes"][0]["confidence_class"] == "descriptive"


# ---------------------------------------------------------------------------
# 8. Nightly refuses to overwrite prior payload on validation failure
# ---------------------------------------------------------------------------

def test_nightly_does_not_overwrite_on_validation_failure(tmp_path, monkeypatch):
    """_step_oracle_state must keep the prior file when validate_payload fails."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from scripts.oracle_nightly import _step_oracle_state

    # Write a sentinel prior oracle_state.json
    site_dir = tmp_path / "site"
    basketdata = site_dir / "basketdata"
    basketdata.mkdir(parents=True)
    prior_content = '{"schema":"oracle_state.v1","asof":"PRIOR","sentinel":true}'
    prior_path = basketdata / "oracle_state.json"
    prior_path.write_text(prior_content)

    # Patch build_oracle_state to return a payload that FAILS validation
    # (missing 'asof' will cause a validation error)
    def _bad_build(**kwargs):
        return {"schema": "oracle_state.v1"}  # missing asof, disclaimers, active_episodes

    monkeypatch.setattr("engine.oracle.live.build_oracle_state", _bad_build)

    result = _step_oracle_state(tmp_path, site_dir, dry_run=False)

    # Must return None (failure)
    assert result is None

    # Prior file must be untouched
    assert prior_path.read_text() == prior_content


def test_nightly_writes_on_valid_payload(tmp_path, monkeypatch):
    """_step_oracle_state writes the file when validate_payload passes."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from scripts.oracle_nightly import _step_oracle_state

    site_dir = tmp_path / "site"
    site_dir.mkdir(parents=True)

    good_payload = _valid_payload()

    def _good_build(**kwargs):
        return good_payload

    monkeypatch.setattr("engine.oracle.live.build_oracle_state", _good_build)
    # write_oracle_state delegates to the real implementation (writes to out_dir)

    result = _step_oracle_state(tmp_path, site_dir, dry_run=False)

    assert result is not None
    written = site_dir / "basketdata" / "oracle_state.json"
    assert written.exists()
    loaded = json.loads(written.read_text())
    assert loaded["asof"] == _FRESH_ASOF
