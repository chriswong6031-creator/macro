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


# ===========================================================================
# R-V9-2 — effective_allocation: stage-local heal (agenda artifacts never
# reach main; downstream stages rebuild structural-only in their workspace)
# ===========================================================================

class TestEffectiveAllocation:

    def test_absent_file_rebuilds_structural(self, tmp_path: Path) -> None:
        """No allocation in the workspace → structural-only rebuild, written
        to disk, no LLM (providers=None path)."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import ALLOCATION_PATH, effective_allocation
        assert not (root / ALLOCATION_PATH).exists()
        alloc = effective_allocation(cycle_id="cycle-test-heal", root=root)
        assert alloc.get("allocations"), "structural rebuild must populate allocations"
        assert alloc.get("cycle_id") == "cycle-test-heal"
        assert (root / ALLOCATION_PATH).exists(), "heal must persist the artifact"
        # No provider was available → honest degraded marker, bands structural
        assert alloc.get("provider") is None

    def test_present_file_passthrough(self, tmp_path: Path) -> None:
        """Existing allocation is returned verbatim — no rebuild, no overwrite."""
        root = _make_repo(tmp_path)
        from engine.metabolism.attention import ALLOCATION_PATH, effective_allocation
        marker = {
            "schema": "metabolism.attention.v1",
            "cycle_id": "cycle-agenda-built",
            "provider": "marker-test",
            "allocations": {"til": {"band": "FOCUS", "weight": 1.0,
                                    "structural_band": "STANDARD", "llm_band": "FOCUS",
                                    "floored": False, "rationale": "x"}},
            "focus_lobes": ["til"],
        }
        p = root / ALLOCATION_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(marker), encoding="utf-8")
        alloc = effective_allocation(cycle_id="cycle-other", root=root)
        assert alloc.get("provider") == "marker-test"
        assert alloc.get("cycle_id") == "cycle-agenda-built"

    def test_never_raises_on_broken_root(self, tmp_path: Path) -> None:
        from engine.metabolism.attention import effective_allocation
        out = effective_allocation(root=tmp_path / "nonexistent")
        assert isinstance(out, dict)  # {} or degraded artifact — never raises


# ===========================================================================
# CADENCE — propose_skip cadence gate (operator-ratified 2026-07-13)
# ===========================================================================

import hashlib as _hashlib


def _make_band_alloc(lobe_id: str, band: str, cycle_id: str | None = None) -> dict:
    """Build a minimal allocation dict for propose_skip tests."""
    alloc: dict = {
        "allocations": {
            lobe_id: {
                "band": band,
                "weight": 1.0 if band == "FOCUS" else 0.6,
                "structural_band": "STANDARD",
                "llm_band": None,
                "floored": False,
                "rationale": "",
            }
        }
    }
    if cycle_id is not None:
        alloc["cycle_id"] = cycle_id
    return alloc


def _hash_skip(cycle_id: str, lobe_id: str, cadence: int) -> bool:
    """Mirror of _cadence_hash_skip for test fixtures."""
    digest = _hashlib.sha256(f"{cycle_id}:{lobe_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % cadence != 0


def _find_skip_cycle(lobe_id: str, cadence: int, prefix: str = "cycle-cadence-test") -> str:
    """Return the first synthetic cycle_id where hash says SKIP for this lobe/cadence."""
    for i in range(500):
        cid = f"{prefix}-{i:04d}"
        if _hash_skip(cid, lobe_id, cadence):
            return cid
    raise RuntimeError(f"Could not find a skip cycle for {lobe_id} cadence={cadence} in 500 attempts")


def _find_propose_cycle(lobe_id: str, cadence: int, prefix: str = "cycle-cadence-test") -> str:
    """Return the first synthetic cycle_id where hash says PROPOSE for this lobe/cadence."""
    for i in range(500):
        cid = f"{prefix}-{i:04d}"
        if not _hash_skip(cid, lobe_id, cadence):
            return cid
    raise RuntimeError(f"Could not find a propose cycle for {lobe_id} cadence={cadence} in 500 attempts")


class TestProposeCadenceGate:
    """Tests for the operator-ratified cadence gate in propose_skip."""

    # ── FOCUS always proposes ────────────────────────────────────────────────

    def test_focus_never_cadence_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """FOCUS lobe never cadence-skipped across 50 synthetic cycle ids."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "focus-lobe"
        for i in range(50):
            cycle_id = f"cycle-focus-test-{i:04d}"
            alloc = _make_band_alloc(lobe_id, "FOCUS")
            skip, reason = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
            assert skip is False, f"FOCUS skipped at cycle {cycle_id}"

    # ── Determinism ──────────────────────────────────────────────────────────

    def test_determinism_same_inputs_same_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same (cycle_id, lobe_id) → identical result on repeated calls."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "standard-det-lobe"
        cycle_id = "cycle-determinism-test-0001"
        alloc = _make_band_alloc(lobe_id, "STANDARD", cycle_id=cycle_id)
        results = [
            propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
            for _ in range(10)
        ]
        assert all(r == results[0] for r in results), "Results differed across repeated calls"

    # ── Distribution for STANDARD ─────────────────────────────────────────────

    def test_standard_distribution_400_cycles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STANDARD proposes in [30%, 70%] of 400 synthetic cycles."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "dist-standard-lobe"
        proposes = 0
        for i in range(400):
            cycle_id = f"cycle-synth-{i:04d}"
            alloc = _make_band_alloc(lobe_id, "STANDARD", cycle_id=cycle_id)
            skip, _ = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
            if not skip:
                proposes += 1
        rate = proposes / 400
        assert 0.30 <= rate <= 0.70, f"STANDARD propose rate {rate:.2%} outside [30%, 70%]"

    # ── Distribution for MAINTENANCE ──────────────────────────────────────────

    def test_maintenance_distribution_400_cycles(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MAINTENANCE proposes in [12.5%, 40%] of 400 synthetic cycles."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "dist-maint-lobe"
        proposes = 0
        for i in range(400):
            cycle_id = f"cycle-synth-{i:04d}"
            alloc = _make_band_alloc(lobe_id, "MAINTENANCE", cycle_id=cycle_id)
            skip, _ = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
            if not skip:
                proposes += 1
        rate = proposes / 400
        assert 0.125 <= rate <= 0.40, f"MAINTENANCE propose rate {rate:.2%} outside [12.5%, 40%]"

    # ── Coverage across lobes for one fixed cycle ─────────────────────────────

    def test_standard_coverage_200_lobes_fixed_cycle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """For one fixed cycle_id, ~half of 200 STANDARD lobes propose ([30%, 70%])."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        cycle_id = "cycle-fixed-test-0001"
        proposes = 0
        for i in range(200):
            lobe_id = f"lobe-{i:04d}"
            alloc = _make_band_alloc(lobe_id, "STANDARD", cycle_id=cycle_id)
            skip, _ = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
            if not skip:
                proposes += 1
        rate = proposes / 200
        assert 0.30 <= rate <= 0.70, f"Cross-lobe coverage {rate:.2%} outside [30%, 70%]"

    # ── DORMANT unchanged ─────────────────────────────────────────────────────

    def test_dormant_still_skipped_with_cadence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DORMANT lobe: cadence gate is not applied; existing skip reason unchanged."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "dormant-lobe"
        cycle_id = "cycle-dormant-test-0001"
        alloc = _make_band_alloc(lobe_id, "DORMANT", cycle_id=cycle_id)
        skip, reason = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
        assert skip is True
        assert reason == "attention_dormant"

    def test_dormant_g3_exemption_still_overrides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DORMANT lobe with high-severity row: G3 exemption still overrides cadence."""
        root = _make_repo(tmp_path)
        open_rows = [
            {"insight_id": "ins-dormant-g3", "severity": "high",
             "entities": ["dormant-cadence-lobe"], "handled": False}
        ]
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: open_rows,
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "dormant-cadence-lobe"
        cycle_id = "cycle-dormant-g3-test-0001"
        alloc = _make_band_alloc(lobe_id, "DORMANT", cycle_id=cycle_id)
        skip, reason = propose_skip(lobe_id, root=root, allocation=alloc, cycle_id=cycle_id)
        assert skip is False
        assert reason == "urgent_fix_exemption"

    # ── G3 overrides a cadence skip ───────────────────────────────────────────

    def test_g3_overrides_cadence_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A (cycle_id, lobe) that hash-skips: high/critical insight row forces propose."""
        root = _make_repo(tmp_path)
        lobe_id = "standard-g3-override-lobe"
        # Find a cycle_id where STANDARD (cadence=2) hash says SKIP
        skip_cycle_id = _find_skip_cycle(lobe_id, cadence=2, prefix="cycle-g3-override")

        open_rows = [
            {"insight_id": "ins-g3-override", "severity": "critical",
             "entities": [lobe_id], "handled": False}
        ]
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: open_rows,
        )
        from engine.metabolism.attention import propose_skip
        alloc = _make_band_alloc(lobe_id, "STANDARD", cycle_id=skip_cycle_id)
        skip, reason = propose_skip(
            lobe_id, root=root, allocation=alloc, cycle_id=skip_cycle_id,
        )
        assert skip is False, f"G3 should override cadence skip; got skip={skip}, reason={reason}"
        assert reason == "urgent_fix_exemption"

    # ── cycle_id unresolvable → fail open ────────────────────────────────────

    def test_cycle_id_unresolvable_fails_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No cycle_id param, allocation without cycle_id → fail open → (False, '')."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "standard-no-cycle-lobe"
        # No cycle_id in allocation, no explicit param
        alloc = _make_band_alloc(lobe_id, "STANDARD")  # no cycle_id key
        skip, reason = propose_skip(lobe_id, root=root, allocation=alloc)  # no cycle_id param
        assert skip is False
        assert reason == ""

    # ── Config: propose_cadence absent → defaults apply ──────────────────────

    def test_propose_cadence_absent_uses_defaults(self, tmp_path: Path) -> None:
        """propose_cadence absent from yml → defaults apply."""
        root = tmp_path / "no-cadence-repo"
        (root / "config").mkdir(parents=True)
        # Write config WITHOUT propose_cadence block
        (root / "config" / "metabolism_attention.yml").write_text(
            "schema: metabolism_attention.v1\nmax_focus_lobes: 8\n"
            "docket_share:\n  FOCUS: 1.0\n  STANDARD: 0.6\n  MAINTENANCE: 0.2\n  DORMANT: 0.0\n"
            "dispatch_priority:\n  FOCUS: 0\n  STANDARD: 1\n  MAINTENANCE: 2\n  DORMANT: 3\n",
            encoding="utf-8",
        )
        from engine.metabolism.attention import load_attention_config
        cfg = load_attention_config(root=root)
        cadence = cfg["propose_cadence"]
        assert cadence["FOCUS"] == 1
        assert cadence["STANDARD"] == 2
        assert cadence["MAINTENANCE"] == 4

    def test_propose_cadence_zero_clamped_to_one(self, tmp_path: Path) -> None:
        """propose_cadence STANDARD: 0 → clamped to 1 (no zero-division)."""
        root = tmp_path / "zero-cadence-repo"
        (root / "config").mkdir(parents=True)
        (root / "config" / "metabolism_attention.yml").write_text(
            "schema: metabolism_attention.v1\nmax_focus_lobes: 8\n"
            "docket_share:\n  FOCUS: 1.0\n  STANDARD: 0.6\n  MAINTENANCE: 0.2\n  DORMANT: 0.0\n"
            "dispatch_priority:\n  FOCUS: 0\n  STANDARD: 1\n  MAINTENANCE: 2\n  DORMANT: 3\n"
            "propose_cadence:\n  FOCUS: 1\n  STANDARD: 0\n  MAINTENANCE: 4\n",
            encoding="utf-8",
        )
        from engine.metabolism.attention import load_attention_config
        cfg = load_attention_config(root=root)
        assert cfg["propose_cadence"]["STANDARD"] == 1, "0 must be clamped to >= 1"

    def test_propose_cadence_invalid_string_uses_default(self, tmp_path: Path) -> None:
        """propose_cadence STANDARD: 'x' → falls back to default without raising."""
        root = tmp_path / "bad-cadence-repo"
        (root / "config").mkdir(parents=True)
        (root / "config" / "metabolism_attention.yml").write_text(
            "schema: metabolism_attention.v1\nmax_focus_lobes: 8\n"
            "docket_share:\n  FOCUS: 1.0\n  STANDARD: 0.6\n  MAINTENANCE: 0.2\n  DORMANT: 0.0\n"
            "dispatch_priority:\n  FOCUS: 0\n  STANDARD: 1\n  MAINTENANCE: 2\n  DORMANT: 3\n"
            "propose_cadence:\n  FOCUS: 1\n  STANDARD: 'x'\n  MAINTENANCE: 4\n",
            encoding="utf-8",
        )
        from engine.metabolism.attention import load_attention_config
        cfg = load_attention_config(root=root)
        # 'x' can't be cast to int → falls back to default (2)
        assert cfg["propose_cadence"]["STANDARD"] == 2

    # ── Skip reason format ────────────────────────────────────────────────────

    def test_skip_reason_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Skip reason is 'cadence:STANDARD:1/2' for STANDARD cadence=2."""
        root = _make_repo(tmp_path)
        monkeypatch.setattr(
            "engine.metabolism.insight_bus.get_open_rows",
            lambda root=None: [],
        )
        from engine.metabolism.attention import propose_skip
        lobe_id = "standard-reason-test-lobe"
        # Find a cycle_id that hashes to SKIP for STANDARD (cadence=2)
        skip_cycle_id = _find_skip_cycle(lobe_id, cadence=2, prefix="cycle-reason-test")
        alloc = _make_band_alloc(lobe_id, "STANDARD", cycle_id=skip_cycle_id)
        skip, reason = propose_skip(
            lobe_id, root=root, allocation=alloc, cycle_id=skip_cycle_id,
        )
        assert skip is True
        assert reason == "cadence:STANDARD:1/2", f"Expected 'cadence:STANDARD:1/2', got {reason!r}"
