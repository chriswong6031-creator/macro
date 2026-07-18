"""Tests for engine.ledger_lane — canonical forward-ledger advance gate.

Covers:
- env-matrix unit tests for nightly_advance_enabled() and asia_advance_enabled()
- alias-integrity assertions: engine.<module>._ledger_advance_enabled IS
  engine.ledger_lane.{nightly,asia}_advance_enabled
"""

import importlib
import os

import pytest

import engine.ledger_lane as ll


# ---------------------------------------------------------------------------
# nightly_advance_enabled — env-matrix
# ---------------------------------------------------------------------------

class TestNightlyAdvanceEnabled:
    def test_disabled_without_env_var(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert ll.nightly_advance_enabled() is False

    def test_enabled_with_collect_lane_nightly(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.delenv("US_LANE", raising=False)
        assert ll.nightly_advance_enabled() is True

    def test_case_insensitive_collect_lane(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "NIGHTLY")
        monkeypatch.delenv("US_LANE", raising=False)
        assert ll.nightly_advance_enabled() is True

    def test_collect_lane_mixed_case(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "Nightly")
        monkeypatch.delenv("US_LANE", raising=False)
        assert ll.nightly_advance_enabled() is True

    def test_collect_lane_other_value_disabled(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        monkeypatch.delenv("US_LANE", raising=False)
        assert ll.nightly_advance_enabled() is False

    def test_us_lane_legacy_alias(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "nightly")
        assert ll.nightly_advance_enabled() is True

    def test_us_lane_case_insensitive(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "NIGHTLY")
        assert ll.nightly_advance_enabled() is True

    def test_collect_lane_takes_precedence_over_us_lane(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        monkeypatch.setenv("US_LANE", "nightly")
        # COLLECT_LANE non-empty and != nightly → False; US_LANE is shadowed
        assert ll.nightly_advance_enabled() is False

    def test_collect_lane_nightly_with_us_lane_ignored(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.setenv("US_LANE", "intraday")
        assert ll.nightly_advance_enabled() is True

    def test_cn_lane_does_not_activate_nightly(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        monkeypatch.setenv("CN_LANE", "asia")
        assert ll.nightly_advance_enabled() is False


# ---------------------------------------------------------------------------
# asia_advance_enabled — env-matrix
# ---------------------------------------------------------------------------

class TestAsiaAdvanceEnabled:
    def test_disabled_without_env_var(self, monkeypatch):
        monkeypatch.delenv("CN_LANE", raising=False)
        assert ll.asia_advance_enabled() is False

    def test_enabled_with_cn_lane_asia(self, monkeypatch):
        monkeypatch.setenv("CN_LANE", "asia")
        assert ll.asia_advance_enabled() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("CN_LANE", "ASIA")
        assert ll.asia_advance_enabled() is True

    def test_cn_lane_mixed_case(self, monkeypatch):
        monkeypatch.setenv("CN_LANE", "Asia")
        assert ll.asia_advance_enabled() is True

    def test_cn_lane_other_value_disabled(self, monkeypatch):
        monkeypatch.setenv("CN_LANE", "nightly")
        assert ll.asia_advance_enabled() is False

    def test_collect_lane_does_not_activate_asia(self, monkeypatch):
        monkeypatch.delenv("CN_LANE", raising=False)
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert ll.asia_advance_enabled() is False


# ---------------------------------------------------------------------------
# Alias integrity — confirm module attributes ARE the canonical functions
# ---------------------------------------------------------------------------

class TestAliasIntegrity:
    def test_track_record_alias_is_nightly(self):
        import engine.track_record as tr
        assert tr._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_hk_leadership_alias_is_asia(self):
        import engine.hk_leadership as hkl
        assert hkl._ledger_advance_enabled is ll.asia_advance_enabled

    def test_flare_persistence_alias_is_nightly(self):
        import engine.flare_persistence as fp
        assert fp._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_source_registry_alias_is_nightly(self):
        import engine.source_registry as sr
        assert sr._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_hk_cbbc_alias_is_asia(self):
        import engine.hk_cbbc as hkc
        assert hkc._ledger_advance_enabled is ll.asia_advance_enabled

    def test_mtf_upturn_alias_is_nightly(self):
        import engine.mtf_upturn as mu
        assert mu._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_ownership_ledger_alias_is_nightly(self):
        import engine.ownership_ledger as ol
        assert ol._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_narrative_flare_alias_is_nightly(self):
        import engine.narrative_flare as nf
        assert nf._ledger_advance_enabled is ll.nightly_advance_enabled

    def test_hk_adr_bridge_alias_is_asia(self):
        import engine.hk_adr_bridge as hkab
        assert hkab._ledger_advance_enabled is ll.asia_advance_enabled

    def test_hk_washout_watch_alias_is_asia(self):
        import engine.hk_washout_watch as hkw
        assert hkw._ledger_advance_enabled is ll.asia_advance_enabled
