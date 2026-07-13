"""tests/test_metabolism_attention.py — Hermetic tests for Metabolism V9 Attention Economy.

COVERAGE:
  CRIT  structural band ladder: nw_core→CRITICAL, mastermind:context→HIGH, fanout>=4→HIGH,
        daily active→STANDARD, weekly no-tags→ANCILLARY
  CRIT2 build_criticality never raises on missing synapse/charters
  G4    build_attention with providers=None → pure structural mapping + degraded_reason
  G1    monkeypatched LLM deviation CRITICAL→DORMANT lands STANDARD floored=True
        monkeypatched LLM deviation HIGH→DORMANT lands MAINTENANCE floored=True
  G2    more than max_focus_lobes deviations to FOCUS → deterministic demotion
  DOCKET effective_docket_size: FOCUS 5→5, STANDARD 5→3, MAINTENANCE 5→1, DORMANT→0
  SKIP  propose_skip: DORMANT no rows → (True,"attention_dormant")
        DORMANT + high-severity row with entity match → (False,"urgent_fix_exemption")
        non-DORMANT → (False,"")
  DFLT  band_for/weight_for defaults on empty allocation ("STANDARD"/0.6)
  HIST  history line appended on build_attention

All tests are HERMETIC (tmp dirs, in-process, no real data / network / subprocess).
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

_MINIMAL_CHARTERS_YML = textwrap.dedent("""\
schema: lobe_charters.v1
generated_at: '2026-07-12'
charters:
  world-state:
    lobe_id: world-state
    tier: display
    lifecycle_state: active
    information_domain: context
    fitness_sensors:
      - id: freshness_sla
        store: data/metabolism/fitness/world-state.json
  context-feeder:
    lobe_id: context-feeder
    tier: display
    lifecycle_state: active
    information_domain: context
    fitness_sensors:
      - id: freshness_sla
        store: data/metabolism/fitness/context-feeder.json
  high-fanout-lobe:
    lobe_id: high-fanout-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
  daily-active-lobe:
    lobe_id: daily-active-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
  weekly-ancillary-lobe:
    lobe_id: weekly-ancillary-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
  scored-lobe:
    lobe_id: scored-lobe
    tier: scored
    lifecycle_state: active
    information_domain: context
  critical-anchor-lobe:
    lobe_id: critical-anchor-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
""")

# Synapse with:
#   world-state → nw_anchor (mastermind:anchor)
#   context-feeder → mastermind:context
#   high-fanout-lobe → 4 consumers, no tags
#   daily-active-lobe → daily cadence, no tags, 2 consumers
#   weekly-ancillary-lobe → weekly cadence, no tags
#   scored-lobe → 2 consumers, no tags (tier=scored in charter)
#   critical-anchor-lobe → mastermind:anchor
_MINIMAL_SYNAPSE_YML = textwrap.dedent("""\
meta:
  schema_version: 1
artifacts:
  world-state:
    path: data/neuralweb/world_state.json
    format: json
    producer: engine/neuralweb/world_state.py
    owner_program: neural-web
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/master_brain.py
    external_consumers:
      - mastermind:anchor
      - mastermind:vendored
  context-feeder:
    path: data/context/feeder.json
    format: json
    producer: scripts/build_context.py
    owner_program: context
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/master_brain.py
    external_consumers:
      - mastermind:context
  high-fanout-lobe:
    path: data/fanout/data.json
    format: json
    producer: scripts/build_fanout.py
    owner_program: fanout
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
      - engine/b.py
      - engine/c.py
      - engine/d.py
    external_consumers: []
  daily-active-lobe:
    path: data/daily/data.json
    format: json
    producer: scripts/build_daily.py
    owner_program: daily
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
      - engine/b.py
    external_consumers: []
  weekly-ancillary-lobe:
    path: data/weekly/data.json
    format: json
    producer: scripts/build_weekly.py
    owner_program: weekly
    cadence: weekly
    storage: git
    freshness_sla_hours: 192
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
    external_consumers: []
  scored-lobe:
    path: data/scored/data.json
    format: json
    producer: scripts/build_scored.py
    owner_program: scored
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: scored
    horizon_role: context
    consumers:
      - engine/a.py
      - engine/b.py
    external_consumers: []
  critical-anchor-lobe:
    path: data/critical/data.json
    format: json
    producer: scripts/build_critical.py
    owner_program: critical
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
    external_consumers:
      - mastermind:anchor
""")

_MINIMAL_ATTENTION_YML = textwrap.dedent("""\
schema: metabolism_attention.v1
generated_at: "2026-07-12"
owner_program: metabolism-v9
max_focus_lobes: 8
docket_share:
  FOCUS: 1.0
  STANDARD: 0.6
  MAINTENANCE: 0.2
  DORMANT: 0.0
dispatch_priority:
  FOCUS: 0
  STANDARD: 1
  MAINTENANCE: 2
  DORMANT: 3
""")


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo root with config + data dirs."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data" / "metabolism").mkdir(parents=True)
    (root / "config" / "lobe_charters.yml").write_text(_MINIMAL_CHARTERS_YML, encoding="utf-8")
    (root / "config" / "synapse.yml").write_text(_MINIMAL_SYNAPSE_YML, encoding="utf-8")
    (root / "config" / "metabolism_attention.yml").write_text(_MINIMAL_ATTENTION_YML, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Helper: fake mastermind constants (world-state is the nw_core artifact)
# ---------------------------------------------------------------------------

_FAKE_LOBE_TO_ARTIFACT_IDS: dict[str, list[str]] = {
    "market": ["world-state"],  # world-state is backed by "market" summarizer
}
_FAKE_MARKET_DATA_LOBES: tuple[str, ...] = ("market",)


def _patch_mastermind(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch mastermind_context import to return controlled constants."""
    import engine.metabolism.criticality as crit_mod
    monkeypatch.setattr(
        crit_mod,
        "_load_mastermind_constants",
        lambda: (_FAKE_LOBE_TO_ARTIFACT_IDS, _FAKE_MARKET_DATA_LOBES),
    )


# ===========================================================================
# CRIT — Structural band ladder
# ===========================================================================

class TestStructuralBandLadder:

    def test_nw_anchor_is_critical(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobes = art["lobes"]
        # world-state has mastermind:anchor → CRITICAL (nw_anchor=True)
        assert lobes["world-state"]["structural_band"] == "CRITICAL"
        assert lobes["world-state"]["nw_anchor"] is True

    def test_nw_core_is_critical(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """world-state artifact id appears in _LOBE_TO_ARTIFACT_IDS values → nw_core=True."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        # world-state is in _FAKE_LOBE_TO_ARTIFACT_IDS["market"] → nw_core
        assert art["lobes"]["world-state"]["nw_core"] is True
        assert art["lobes"]["world-state"]["structural_band"] == "CRITICAL"

    def test_mastermind_context_tag_is_high(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobe = art["lobes"]["context-feeder"]
        assert lobe["nw_context"] is True
        assert lobe["structural_band"] == "HIGH"

    def test_fanout_4_is_high(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobe = art["lobes"]["high-fanout-lobe"]
        assert lobe["consumer_fanout"] >= 4
        assert lobe["structural_band"] == "HIGH"

    def test_daily_active_is_standard(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobe = art["lobes"]["daily-active-lobe"]
        assert lobe["cadence"] == "daily"
        assert lobe["lifecycle_state"] == "active"
        assert lobe["structural_band"] == "STANDARD"

    def test_weekly_no_tags_is_ancillary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobe = art["lobes"]["weekly-ancillary-lobe"]
        assert lobe["structural_band"] == "ANCILLARY"

    def test_scored_tier_is_high(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        lobe = art["lobes"]["scored-lobe"]
        assert lobe["tier"] == "scored"
        assert lobe["structural_band"] == "HIGH"

    def test_market_data_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """world-state is backed by 'market' summarizer which is in _MARKET_DATA_LOBES."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        assert art["lobes"]["world-state"]["market_data"] is True


# ===========================================================================
# CRIT2 — build_criticality resilience
# ===========================================================================

class TestCriticalityResilience:

    def test_never_raises_on_missing_files(self, tmp_path: Path) -> None:
        """No lobe_charters.yml or synapse.yml → returns artifact with empty lobes."""
        empty_root = tmp_path / "empty"
        empty_root.mkdir()
        (empty_root / "config").mkdir()
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=empty_root, write=False)
        assert art["schema"] == "metabolism.criticality.v1"
        assert isinstance(art["lobes"], dict)
        # No crash, empty lobes is fine

    def test_never_raises_on_bad_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML → returns artifact safely."""
        bad_root = tmp_path / "bad"
        bad_root.mkdir()
        (bad_root / "config").mkdir()
        (bad_root / "config" / "lobe_charters.yml").write_text(
            "THIS IS NOT: VALID: YAML: [{", encoding="utf-8"
        )
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=bad_root, write=False)
        assert art["schema"] == "metabolism.criticality.v1"

    def test_mastermind_import_failure_degrades_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mastermind import failure → nw_core=False for all lobes, no crash."""
        root = _make_repo(tmp_path)
        import engine.metabolism.criticality as crit_mod
        monkeypatch.setattr(
            crit_mod,
            "_load_mastermind_constants",
            lambda: ({}, ()),
        )
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        assert art["schema"] == "metabolism.criticality.v1"
        for lobe_id, profile in art["lobes"].items():
            assert profile["nw_core"] is False

    def test_write_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality, CRITICALITY_PATH
        art = build_criticality(root=root, write=True)
        out = root / CRITICALITY_PATH
        assert out.exists()
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        assert on_disk["schema"] == "metabolism.criticality.v1"

    def test_counts_sum_to_total_lobes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.criticality import build_criticality
        art = build_criticality(root=root, write=False)
        total_counts = sum(art["counts"].values())
        assert total_counts == len(art["lobes"])


# ===========================================================================
# G4 — No provider → pure structural mapping + degraded_reason
# ===========================================================================

class TestG4NoDegradedMapping:

    def test_no_provider_produces_structural_mapping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.attention import build_attention, STRUCTURAL_TO_BAND
        art = build_attention(cycle_id="test-cycle", root=root, providers=None)
        assert art["schema"] == "metabolism.attention.v1"
        assert art["degraded_reason"] == "no_provider"
        assert art["provider"] is None

        # Each lobe should have the structural default band
        from engine.metabolism.criticality import build_criticality
        crit = build_criticality(root=root, write=False)
        for lobe_id, profile in crit["lobes"].items():
            sband = profile["structural_band"]
            expected = STRUCTURAL_TO_BAND[sband]
            alloc = art["allocations"][lobe_id]
            assert alloc["band"] == expected, f"{lobe_id}: expected {expected}, got {alloc['band']}"
            assert alloc["llm_band"] is None
            assert alloc["floored"] is False

    def test_no_provider_sets_degraded_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.attention import build_attention
        art = build_attention(cycle_id="test-cycle", root=root, providers=None)
        assert art["degraded_reason"] == "no_provider"

    def test_never_raises_on_empty_root(self, tmp_path: Path) -> None:
        """build_attention on an empty root never raises."""
        empty = tmp_path / "empty"
        empty.mkdir()
        (empty / "config").mkdir()
        (empty / "data" / "metabolism").mkdir(parents=True)
        from engine.metabolism.attention import build_attention
        art = build_attention(cycle_id="test-cycle", root=empty, providers=None)
        assert art["schema"] == "metabolism.attention.v1"


# ===========================================================================
# G1 — Criticality floors
# ===========================================================================

class TestG1Floors:

    def _fake_llm_response(self, deviations: dict) -> str:
        return json.dumps({"deviations": deviations})

    def test_critical_to_dormant_floors_to_standard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM tries to set world-state (CRITICAL anchor) to DORMANT → lands STANDARD, floored=True."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)

        # world-state is nw_anchor → CRITICAL
        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                self._fake_llm_response({"world-state": {"band": "DORMANT", "rationale": "test"}}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        alloc = art["allocations"]["world-state"]
        assert alloc["band"] == "STANDARD", f"Expected STANDARD, got {alloc['band']}"
        assert alloc["floored"] is True

    def test_critical_to_maintenance_floors_to_standard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM tries to set CRITICAL lobe to MAINTENANCE → lands STANDARD, floored=True."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)

        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                self._fake_llm_response({"world-state": {"band": "MAINTENANCE", "rationale": "test"}}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        alloc = art["allocations"]["world-state"]
        assert alloc["band"] == "STANDARD"
        assert alloc["floored"] is True

    def test_high_to_dormant_floors_to_maintenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM tries to set HIGH lobe (context-feeder) to DORMANT → lands MAINTENANCE, floored=True."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)

        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                self._fake_llm_response({"context-feeder": {"band": "DORMANT", "rationale": "test"}}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        alloc = art["allocations"]["context-feeder"]
        assert alloc["band"] == "MAINTENANCE"
        assert alloc["floored"] is True

    def test_critical_focus_not_floored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CRITICAL lobe set to FOCUS by LLM is allowed (no floor)."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)

        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                self._fake_llm_response({"world-state": {"band": "FOCUS", "rationale": "test"}}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        alloc = art["allocations"]["world-state"]
        assert alloc["band"] == "FOCUS"
        assert alloc["floored"] is False


# ===========================================================================
# G2 — Focus cap
# ===========================================================================

class TestG2FocusCap:

    def test_focus_cap_demotes_excess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """More than max_focus_lobes deviations to FOCUS → deterministic demotion."""
        # Create a config with max_focus_lobes=2
        root = _make_repo(tmp_path)
        attention_yml = _MINIMAL_ATTENTION_YML.replace("max_focus_lobes: 8", "max_focus_lobes: 2")
        (root / "config" / "metabolism_attention.yml").write_text(attention_yml, encoding="utf-8")
        _patch_mastermind(monkeypatch)

        # Try to set all 7 lobes to FOCUS
        all_lobes = [
            "world-state", "context-feeder", "high-fanout-lobe",
            "daily-active-lobe", "weekly-ancillary-lobe", "scored-lobe",
            "critical-anchor-lobe",
        ]
        devs = {lid: {"band": "FOCUS", "rationale": "test"} for lid in all_lobes}

        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                json.dumps({"deviations": devs}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        focus_lobes = art["focus_lobes"]
        assert len(focus_lobes) <= 2, f"Expected <=2 focus lobes, got {len(focus_lobes)}"

    def test_focus_cap_deterministic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Demotion order is deterministic: structural band priority then alpha."""
        root = _make_repo(tmp_path)
        attention_yml = _MINIMAL_ATTENTION_YML.replace("max_focus_lobes: 8", "max_focus_lobes: 1")
        (root / "config" / "metabolism_attention.yml").write_text(attention_yml, encoding="utf-8")
        _patch_mastermind(monkeypatch)

        # Set CRITICAL lobes and STANDARD lobes all to FOCUS
        devs = {
            "world-state": {"band": "FOCUS", "rationale": "test"},         # CRITICAL
            "critical-anchor-lobe": {"band": "FOCUS", "rationale": "test"}, # CRITICAL (anchor)
            "daily-active-lobe": {"band": "FOCUS", "rationale": "test"},    # STANDARD
        }
        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                json.dumps({"deviations": devs}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        focus_lobes = art["focus_lobes"]
        assert len(focus_lobes) == 1
        # The kept FOCUS lobe must be a CRITICAL one (higher priority)
        kept = focus_lobes[0]
        assert art["allocations"][kept]["structural_band"] == "CRITICAL"

    def test_floored_demoted_lobes_have_floored_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        attention_yml = _MINIMAL_ATTENTION_YML.replace("max_focus_lobes: 8", "max_focus_lobes: 1")
        (root / "config" / "metabolism_attention.yml").write_text(attention_yml, encoding="utf-8")
        _patch_mastermind(monkeypatch)

        devs = {
            "world-state": {"band": "FOCUS", "rationale": "important"},
            "daily-active-lobe": {"band": "FOCUS", "rationale": "also important"},
        }
        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            att_mod,
            "_call_llm",
            lambda providers, system_prompt, user_prompt, max_tokens=4000: (
                json.dumps({"deviations": devs}),
                None,
                "mock",
            ),
        )
        from engine.metabolism.attention import build_attention
        art = build_attention(
            cycle_id="test-cycle", root=root,
            providers=[{"type": "mock"}], model=None
        )
        # At least one lobe should be floored (demoted from FOCUS to STANDARD)
        floored = [lid for lid, alloc in art["allocations"].items() if alloc.get("floored")]
        assert len(floored) >= 1


# ===========================================================================
# DOCKET — effective_docket_size
# ===========================================================================

class TestEffectiveDocketSize:

    def _make_allocation(self, band: str) -> dict:
        return {
            "allocations": {
                "test-lobe": {
                    "band": band,
                    "weight": 1.0 if band == "FOCUS" else 0.6,
                    "structural_band": "STANDARD",
                    "llm_band": None,
                    "floored": False,
                    "rationale": "",
                }
            }
        }

    def test_focus_full_docket(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        alloc = self._make_allocation("FOCUS")
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 5

    def test_standard_scaled_docket(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        alloc = self._make_allocation("STANDARD")
        # floor(5 * 0.6) = 3
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 3

    def test_maintenance_minimal_docket(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        alloc = self._make_allocation("MAINTENANCE")
        # floor(5 * 0.2) = 1
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 1

    def test_dormant_zero(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        alloc = self._make_allocation("DORMANT")
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 0

    def test_never_exceeds_base(self, tmp_path: Path) -> None:
        """G5: effective docket never exceeds base_size."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        alloc = self._make_allocation("FOCUS")
        base = 3
        result = effective_docket_size("test-lobe", base, root=root, allocation=alloc)
        assert result <= base

    def test_unknown_lobe_defaults_to_standard(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import effective_docket_size
        # Empty allocation → band_for returns "STANDARD" → 0.6 scale
        result = effective_docket_size("nonexistent-lobe", 5, root=root, allocation={})
        assert result == 3  # floor(5 * 0.6) = 3


# ===========================================================================
# SKIP — propose_skip
# ===========================================================================

class TestProposeSkip:

    def _make_dormant_allocation(self, lobe_id: str) -> dict:
        return {
            "allocations": {
                lobe_id: {
                    "band": "DORMANT",
                    "weight": 0.0,
                    "structural_band": "ANCILLARY",
                    "llm_band": None,
                    "floored": False,
                    "rationale": "",
                }
            }
        }

    def _make_active_allocation(self, lobe_id: str, band: str = "STANDARD") -> dict:
        return {
            "allocations": {
                lobe_id: {
                    "band": band,
                    "weight": 0.6,
                    "structural_band": "STANDARD",
                    "llm_band": None,
                    "floored": False,
                    "rationale": "",
                }
            }
        }

    def test_dormant_no_rows_returns_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        alloc = self._make_dormant_allocation("test-lobe")

        import engine.metabolism.attention as att_mod
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
        assert skip is True
        assert reason == "attention_dormant"

    def test_dormant_with_high_severity_row_exempted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DORMANT lobe with high-severity insight row targeting it → exemption (False)."""
        root = _make_repo(tmp_path)
        alloc = self._make_dormant_allocation("test-lobe")

        open_rows = [
            {
                "insight_id": "ins-001",
                "severity": "high",
                "entities": ["test-lobe", "other-lobe"],
                "handled": False,
            }
        ]
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: open_rows,
        )
        from engine.metabolism.attention import propose_skip
        skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
        assert skip is False
        assert reason == "urgent_fix_exemption"

    def test_dormant_with_critical_severity_row_exempted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DORMANT lobe with critical-severity insight row → exemption."""
        root = _make_repo(tmp_path)
        alloc = self._make_dormant_allocation("test-lobe")

        open_rows = [
            {
                "insight_id": "ins-002",
                "severity": "critical",
                "entities": ["test-lobe"],
                "handled": False,
            }
        ]
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: open_rows,
        )
        from engine.metabolism.attention import propose_skip
        skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
        assert skip is False
        assert reason == "urgent_fix_exemption"

    def test_dormant_high_row_different_lobe_no_exemption(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """High-severity row exists but targets a DIFFERENT lobe → skip applies."""
        root = _make_repo(tmp_path)
        alloc = self._make_dormant_allocation("test-lobe")

        open_rows = [
            {
                "insight_id": "ins-003",
                "severity": "high",
                "entities": ["other-lobe"],  # NOT test-lobe
                "handled": False,
            }
        ]
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: open_rows,
        )
        from engine.metabolism.attention import propose_skip
        skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
        assert skip is True
        assert reason == "attention_dormant"

    def test_non_dormant_never_skipped(self, tmp_path: Path) -> None:
        """Non-DORMANT lobe is never skipped (FOCUS, STANDARD, MAINTENANCE)."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import propose_skip
        for band in ("FOCUS", "STANDARD", "MAINTENANCE"):
            alloc = self._make_active_allocation("test-lobe", band=band)
            skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
            assert skip is False, f"band={band}: expected skip=False"
            assert reason == "", f"band={band}: expected empty reason"

    def test_insight_bus_error_fails_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """insight_bus error → fail open (False, 'attention_error')."""
        root = _make_repo(tmp_path)
        alloc = self._make_dormant_allocation("test-lobe")

        def _raise(root=None):
            raise RuntimeError("bus error")

        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            _raise,
        )
        from engine.metabolism.attention import propose_skip
        skip, reason = propose_skip("test-lobe", root=root, allocation=alloc)
        assert skip is False
        assert reason == "attention_error"


# ===========================================================================
# DFLT — band_for / weight_for defaults on empty allocation
# ===========================================================================

class TestDefaultsOnEmptyAllocation:

    def test_band_for_empty_allocation(self) -> None:
        from engine.metabolism.attention import band_for
        assert band_for("nonexistent-lobe", allocation={}) == "STANDARD"

    def test_band_for_none_allocation_falls_back(self, tmp_path: Path) -> None:
        """When allocation is None and file absent, loads empty → returns STANDARD."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import band_for
        result = band_for("nonexistent-lobe", root=root)
        assert result == "STANDARD"

    def test_weight_for_empty_allocation(self) -> None:
        from engine.metabolism.attention import weight_for
        assert weight_for("nonexistent-lobe", allocation={}) == 0.6

    def test_band_for_known_lobe_in_allocation(self) -> None:
        from engine.metabolism.attention import band_for
        alloc = {
            "allocations": {
                "my-lobe": {"band": "FOCUS", "weight": 1.0, "structural_band": "CRITICAL",
                            "llm_band": None, "floored": False, "rationale": ""}
            }
        }
        assert band_for("my-lobe", allocation=alloc) == "FOCUS"

    def test_weight_for_focus_band(self) -> None:
        from engine.metabolism.attention import weight_for
        alloc = {
            "allocations": {
                "my-lobe": {"band": "FOCUS", "weight": 1.0, "structural_band": "CRITICAL",
                            "llm_band": None, "floored": False, "rationale": ""}
            }
        }
        assert weight_for("my-lobe", allocation=alloc) == 1.0


# ===========================================================================
# HIST — history appended on build_attention
# ===========================================================================

class TestHistoryAppend:

    def test_history_line_appended(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_attention appends one JSON line to attention_history.jsonl."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.attention import build_attention, HISTORY_PATH
        hist_path = root / HISTORY_PATH

        assert not hist_path.exists()
        build_attention(cycle_id="cycle-hist-01", root=root, providers=None)
        assert hist_path.exists()
        lines = [l for l in hist_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["cycle_id"] == "cycle-hist-01"
        assert "focus_lobes" in record
        assert "counts_by_band" in record

    def test_history_appends_multiple_cycles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple calls each append one line."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.attention import build_attention, HISTORY_PATH

        for i in range(3):
            build_attention(cycle_id=f"cycle-{i:02d}", root=root, providers=None)

        hist_path = root / HISTORY_PATH
        lines = [l for l in hist_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3
        cycle_ids = [json.loads(l)["cycle_id"] for l in lines]
        assert cycle_ids == ["cycle-00", "cycle-01", "cycle-02"]

    def test_allocation_file_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_attention writes allocation_allocation.json."""
        root = _make_repo(tmp_path)
        _patch_mastermind(monkeypatch)
        from engine.metabolism.attention import build_attention, ALLOCATION_PATH
        build_attention(cycle_id="cycle-write-test", root=root, providers=None)
        out = root / ALLOCATION_PATH
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "metabolism.attention.v1"
        assert data["cycle_id"] == "cycle-write-test"


# ===========================================================================
# Misc — dispatch_priority
# ===========================================================================

class TestDispatchPriority:

    def test_priority_by_band(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import dispatch_priority

        cases = [
            ("FOCUS", 0),
            ("STANDARD", 1),
            ("MAINTENANCE", 2),
            ("DORMANT", 3),
        ]
        for band, expected_priority in cases:
            alloc = {
                "allocations": {
                    "test-lobe": {"band": band, "weight": 0.0,
                                  "structural_band": "STANDARD", "llm_band": None,
                                  "floored": False, "rationale": ""}
                }
            }
            result = dispatch_priority("test-lobe", allocation=alloc, root=root)
            assert result == expected_priority, f"band={band}: expected {expected_priority}"

    def test_default_priority_for_unknown_lobe(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import dispatch_priority
        # Empty allocation → band_for returns STANDARD → priority 1
        result = dispatch_priority("unknown-lobe", allocation={}, root=root)
        assert result == 1


# ===========================================================================
# ROLES — attention role appended to metabolism_roles.yml
# ===========================================================================

class TestRolesFile:

    def test_attention_role_present(self) -> None:
        """config/metabolism_roles.yml must have an 'attention' role key."""
        import yaml  # noqa: PLC0415
        roles_path = _ROOT / "config" / "metabolism_roles.yml"
        data = yaml.safe_load(roles_path.read_text(encoding="utf-8"))
        assert "attention" in data.get("roles", {}), "attention role missing from metabolism_roles.yml"

    def test_attention_role_mentions_key_rulings(self) -> None:
        import yaml  # noqa: PLC0415
        roles_path = _ROOT / "config" / "metabolism_roles.yml"
        data = yaml.safe_load(roles_path.read_text(encoding="utf-8"))
        text = data["roles"]["attention"]
        assert "R-V9-1" in text
        assert "AUTONOMY_PAUSED" in text


# ===========================================================================
# CONFIG — metabolism_attention.yml
# ===========================================================================

class TestAttentionConfig:

    def test_config_loads(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import load_attention_config
        cfg = load_attention_config(root=root)
        assert cfg["max_focus_lobes"] == 8
        assert cfg["docket_share"]["FOCUS"] == 1.0
        assert cfg["docket_share"]["DORMANT"] == 0.0
        assert cfg["dispatch_priority"]["FOCUS"] == 0
        assert cfg["dispatch_priority"]["DORMANT"] == 3

    def test_config_defaults_on_missing_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        (empty / "config").mkdir()
        from engine.metabolism.attention import load_attention_config
        cfg = load_attention_config(root=empty)
        assert cfg["max_focus_lobes"] == 8  # default


# ===========================================================================
# R-V9-9 — rank_cycle_ids: attention-aware BUILD cycle selection
# ===========================================================================

def _alloc_with_bands(bands: dict[str, str]) -> dict:
    return {
        "allocations": {
            lobe: {"band": band, "weight": 0.0, "structural_band": "STANDARD",
                   "llm_band": None, "floored": False, "rationale": ""}
            for lobe, band in bands.items()
        }
    }


class TestRankCycleIds:

    def test_attention_priority_within_same_date(self, tmp_path: Path) -> None:
        """Within the newest date cohort, the FOCUS lobe's docket ranks first —
        beating the pre-V9 lexicographic-last pick.  (context-feeder is a
        charter lobe in the fixture, so the -context-feeder suffix resolves;
        the bare base id resolves to til.)"""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import rank_cycle_ids
        alloc = _alloc_with_bands({"til": "FOCUS", "context-feeder": "MAINTENANCE"})
        ids = [
            "cycle-2026-07-12-a3f2",                 # bare base → til (FOCUS)
            "cycle-2026-07-12-a3f2-context-feeder",  # lexicographic winner pre-V9
        ]
        ranked = rank_cycle_ids(ids, root=root, allocation=alloc)
        assert ranked[0] == "cycle-2026-07-12-a3f2"
        assert sorted(ranked) == sorted(ids)  # no candidate dropped

    def test_newest_date_beats_attention(self, tmp_path: Path) -> None:
        """A stale FOCUS docket never shadows today's work (date dominates)."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import rank_cycle_ids
        alloc = _alloc_with_bands({"til": "FOCUS", "context-feeder": "MAINTENANCE"})
        ids = [
            "cycle-2026-07-10-b1c2",                 # stale, FOCUS lobe
            "cycle-2026-07-12-a3f2-context-feeder",  # today, MAINTENANCE lobe
        ]
        ranked = rank_cycle_ids(ids, root=root, allocation=alloc)
        assert ranked[0] == "cycle-2026-07-12-a3f2-context-feeder"

    def test_empty_allocation_matches_pre_v9_pick(self, tmp_path: Path) -> None:
        """No allocation → all lobes STANDARD → first element equals the old
        `sort | tail -1` choice."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import rank_cycle_ids
        ids = ["cycle-2026-07-12-a3f2", "cycle-2026-07-12-a3f2-context-feeder"]
        ranked = rank_cycle_ids(ids, root=root, allocation={})
        assert ranked[0] == sorted(ids)[-1]

    def test_never_raises_on_junk(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import rank_cycle_ids
        assert rank_cycle_ids([], root=root) == []
        assert rank_cycle_ids(["", "  "], root=root) == []
        out = rank_cycle_ids(["no-date-here", "cycle-2026-07-12-a3f2"], root=root,
                             allocation={"allocations": "junk"})
        assert len(out) == 2  # nothing dropped, nothing raised
