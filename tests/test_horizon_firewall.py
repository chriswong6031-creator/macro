"""
tests/test_horizon_firewall.py — Unit tests for the horizon firewall (LH-R1).

Three test groups:

  A. Gate catches synthetic violations in both directions.
     Feeds a doctored registry fixture to check_horizon_firewall(); does NOT
     mutate the real registry.

  B. Entry-stack research harnesses contain no read of data/research/long_hold_*
     paths (static grep-style assertion over source files on disk).

  C. Current real registry state passes the firewall with zero violations.

All tests are deterministic and self-contained; group A uses synthetic dicts
injected directly into check_horizon_firewall(), group B and C use the real
filesystem but only for read-only assertions.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_synapse_reads import (  # noqa: E402
    HorizonViolation,
    _ARTICLE2_MAP,
    _ENTRY_ARTICLE2_SURFACES,
    _HOLD_SURFACE_MAP,
    _HOLD_SURFACE_MODULES,
    _HOLD_SURFACE_NAMES,
    check_horizon_firewall,
)
from engine.neuralweb.synapse import load_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — synthetic registry builders
# ---------------------------------------------------------------------------


def _make_firewall_reg(
    artifact_id: str,
    horizon_role: str,
    scored_path_surfaces: list[str] | None = None,
    consumers: list[str] | None = None,
    extra_artifacts: dict | None = None,
    article2_surfaces: list[str] | None = None,
) -> dict:
    """Build a minimal registry dict for firewall testing."""
    base_surfaces = article2_surfaces if article2_surfaces is not None else list(_ENTRY_ARTICLE2_SURFACES)
    artifacts: dict = {
        artifact_id: {
            "path": f"data/fake/{artifact_id}.json",
            "format": "json",
            "producer": "engine/producer.py",
            "known_extra_writers": [],
            "owner_program": "test",
            "cadence": "daily-engine",
            "storage": "git",
            "asof_field": "asof",
            "freshness_sla_hours": 30,
            "schema": "none",
            "tier": "infrastructure",
            "horizon_role": horizon_role,
            "weights": "none",
            "scored_path_surfaces": scored_path_surfaces or [],
            "consumers": consumers or [],
            "external_consumers": [],
        }
    }
    if extra_artifacts:
        artifacts.update(extra_artifacts)
    return {
        "meta": {
            "schema_version": 1,
            "description": "synthetic firewall test registry",
            "tier_vocabulary": ["display", "infrastructure"],
            "article2_surfaces": base_surfaces,
            "horizon_role_vocabulary": ["tactical_entry", "hold_thesis", "dual", "context"],
        },
        "artifacts": artifacts,
    }


# ===========================================================================
# Group A — Synthetic violation detection
# ===========================================================================


class TestSyntheticViolations:
    """Firewall catches synthetic violations; legitimate roles pass clean."""

    # --- Direction A: hold_thesis bleeding into entry surfaces ---

    def test_hold_thesis_scored_surface_fires_violation(self) -> None:
        """hold_thesis artifact with an entry surface in scored_path_surfaces → violation."""
        # alert_triage is a real Article-2 entry surface
        reg = _make_firewall_reg(
            artifact_id="test-hold-artifact",
            horizon_role="hold_thesis",
            scored_path_surfaces=["alert_triage"],
        )
        violations = check_horizon_firewall(reg)
        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        v = violations[0]
        assert v.artifact_id == "test-hold-artifact"
        assert v.artifact_role == "hold_thesis"
        assert v.direction == "hold_into_entry"
        assert v.channel == "scored_path_surfaces"
        assert v.surface_or_module == "alert_triage"

    def test_hold_thesis_consumer_entry_module_fires_violation(self) -> None:
        """hold_thesis artifact with an entry Article-2 module in consumers → violation."""
        # engine/alert_triage.py is the canonical Article-2 entry module
        reg = _make_firewall_reg(
            artifact_id="test-hold-artifact",
            horizon_role="hold_thesis",
            consumers=["engine/alert_triage.py"],
        )
        violations = check_horizon_firewall(reg)
        assert any(
            v.direction == "hold_into_entry"
            and v.channel == "consumers"
            and v.surface_or_module == "engine/alert_triage.py"
            for v in violations
        ), f"Expected hold_into_entry/consumers violation, got: {violations}"

    def test_hold_thesis_consumer_board_ordering_module_fires_violation(self) -> None:
        """hold_thesis artifact in board_ordering consumer (scripts/build_stock_library.py) → violation."""
        reg = _make_firewall_reg(
            artifact_id="test-hold-artifact",
            horizon_role="hold_thesis",
            consumers=["scripts/build_stock_library.py"],
        )
        violations = check_horizon_firewall(reg)
        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        assert violations[0].direction == "hold_into_entry"

    def test_hold_thesis_consumer_top_setups_module_fires_violation(self) -> None:
        """hold_thesis artifact in top_setups consumer (scripts/build_site.py) → violation."""
        reg = _make_firewall_reg(
            artifact_id="test-hold-artifact",
            horizon_role="hold_thesis",
            consumers=["scripts/build_site.py"],
        )
        violations = check_horizon_firewall(reg)
        assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
        assert violations[0].direction == "hold_into_entry"

    # --- Direction B: tactical_entry bleeding into hold surfaces ---

    def test_entry_into_hold_scored_surface_fires_when_hold_surface_registered(self) -> None:
        """
        tactical_entry artifact with a hold surface in scored_path_surfaces → violation.
        This uses a synthetic hold-surface map injected via monkeypatching.
        """
        # Temporarily inject a synthetic hold surface into the module-level sets
        # (the real map is empty in W0; this simulates a future W3 hold surface).
        import scripts.check_synapse_reads as csr

        original_names = csr._HOLD_SURFACE_NAMES
        original_modules = csr._HOLD_SURFACE_MODULES

        try:
            csr._HOLD_SURFACE_NAMES = frozenset({"long_hold_committee"})
            csr._HOLD_SURFACE_MODULES = frozenset({"scripts/build_long_hold.py"})

            reg = _make_firewall_reg(
                artifact_id="test-entry-artifact",
                horizon_role="tactical_entry",
                scored_path_surfaces=["long_hold_committee"],
            )
            violations = check_horizon_firewall(reg)
            assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
            v = violations[0]
            assert v.artifact_id == "test-entry-artifact"
            assert v.artifact_role == "tactical_entry"
            assert v.direction == "entry_into_hold"
            assert v.channel == "scored_path_surfaces"
            assert v.surface_or_module == "long_hold_committee"
        finally:
            csr._HOLD_SURFACE_NAMES = original_names
            csr._HOLD_SURFACE_MODULES = original_modules

    def test_entry_into_hold_consumer_fires_when_hold_module_registered(self) -> None:
        """
        tactical_entry artifact with a hold module in consumers → violation.
        Synthetic hold-surface monkeypatch.
        """
        import scripts.check_synapse_reads as csr

        original_names = csr._HOLD_SURFACE_NAMES
        original_modules = csr._HOLD_SURFACE_MODULES

        try:
            csr._HOLD_SURFACE_NAMES = frozenset({"long_hold_committee"})
            csr._HOLD_SURFACE_MODULES = frozenset({"scripts/build_long_hold.py"})

            reg = _make_firewall_reg(
                artifact_id="test-entry-artifact",
                horizon_role="tactical_entry",
                consumers=["scripts/build_long_hold.py"],
            )
            violations = check_horizon_firewall(reg)
            assert len(violations) == 1, f"Expected 1 violation, got: {violations}"
            v = violations[0]
            assert v.artifact_role == "tactical_entry"
            assert v.direction == "entry_into_hold"
            assert v.channel == "consumers"
            assert v.surface_or_module == "scripts/build_long_hold.py"
        finally:
            csr._HOLD_SURFACE_NAMES = original_names
            csr._HOLD_SURFACE_MODULES = original_modules

    # --- Exempt roles: dual and context must pass both directions ---

    def test_dual_artifact_passes_entry_surface(self) -> None:
        """dual artifact in an entry surface scored_path_surfaces → no violation."""
        reg = _make_firewall_reg(
            artifact_id="test-dual-artifact",
            horizon_role="dual",
            scored_path_surfaces=["alert_triage", "board_ordering"],
            consumers=["engine/alert_triage.py", "scripts/build_site.py"],
        )
        violations = check_horizon_firewall(reg)
        assert violations == [], f"dual artifact must not trigger firewall, got: {violations}"

    def test_context_artifact_passes_entry_surface(self) -> None:
        """context artifact in an entry surface scored_path_surfaces → no violation."""
        reg = _make_firewall_reg(
            artifact_id="test-context-artifact",
            horizon_role="context",
            scored_path_surfaces=["alert_triage", "board_ordering", "top_setups"],
            consumers=["engine/alert_triage.py"],
        )
        violations = check_horizon_firewall(reg)
        assert violations == [], f"context artifact must not trigger firewall, got: {violations}"

    def test_tactical_entry_in_entry_surfaces_is_clean(self) -> None:
        """tactical_entry in entry scored_path_surfaces is normal and clean."""
        reg = _make_firewall_reg(
            artifact_id="test-entry-artifact",
            horizon_role="tactical_entry",
            scored_path_surfaces=["alert_triage", "board_ordering"],
            consumers=["engine/alert_triage.py", "scripts/build_stock_library.py"],
        )
        violations = check_horizon_firewall(reg)
        assert violations == [], f"tactical_entry in entry surfaces must be clean, got: {violations}"

    def test_hold_thesis_with_non_entry_consumers_is_clean(self) -> None:
        """hold_thesis artifact with only non-entry consumers → no violation."""
        reg = _make_firewall_reg(
            artifact_id="test-hold-artifact",
            horizon_role="hold_thesis",
            scored_path_surfaces=[],
            consumers=["engine/fundamentals.py", "scripts/build_long_hold_report.py"],
        )
        violations = check_horizon_firewall(reg)
        assert violations == [], f"hold_thesis with non-entry consumers must be clean, got: {violations}"

    def test_multiple_violations_reported(self) -> None:
        """Multiple violations in a single artifact are all returned."""
        reg = _make_firewall_reg(
            artifact_id="test-hold-multi",
            horizon_role="hold_thesis",
            scored_path_surfaces=["alert_triage", "board_ordering"],
            consumers=["engine/alert_triage.py", "scripts/build_stock_library.py"],
        )
        violations = check_horizon_firewall(reg)
        # Expect 4: 2 from scored_path_surfaces + 2 from consumers
        assert len(violations) == 4, f"Expected 4 violations, got: {violations}"
        directions = {v.direction for v in violations}
        assert directions == {"hold_into_entry"}

    def test_violation_label_contains_key_fields(self) -> None:
        """HorizonViolation.label() must include artifact_id, direction, and channel."""
        v = HorizonViolation(
            artifact_id="my-hold-art",
            artifact_role="hold_thesis",
            direction="hold_into_entry",
            channel="scored_path_surfaces",
            surface_or_module="alert_triage",
        )
        label = v.label()
        assert "my-hold-art" in label
        assert "hold_thesis" in label
        assert "hold_into_entry" in label
        assert "scored_path_surfaces" in label
        assert "alert_triage" in label

    def test_as_dict_roundtrip(self) -> None:
        """HorizonViolation.as_dict() must be JSON-serialisable and cover all fields."""
        v = HorizonViolation(
            artifact_id="x",
            artifact_role="tactical_entry",
            direction="entry_into_hold",
            channel="consumers",
            surface_or_module="scripts/build_long_hold.py",
        )
        d = v.as_dict()
        assert d["artifact_id"] == "x"
        assert d["artifact_role"] == "tactical_entry"
        assert d["direction"] == "entry_into_hold"
        assert d["channel"] == "consumers"
        assert d["surface_or_module"] == "scripts/build_long_hold.py"


# ===========================================================================
# Group B — Static grep: entry harnesses must not read long_hold_* paths
# ===========================================================================

# The paths the task explicitly names as entry harnesses.
_ENTRY_HARNESS_FILES = [
    REPO_ROOT / "scripts" / "research" / "entry_strata_phase0.py",
]

# Keystone backfill scripts: any scripts/research/run_w*.py (the keystone
# harness pattern used by the entry-stack program).  If none exist yet,
# the test is vacuous-pass — fine, as no violation can occur.
_KEYSTONE_PATTERN = re.compile(r"run_w\d+.*\.py$")
_KEYSTONE_FILES = sorted(
    f
    for f in (REPO_ROOT / "scripts" / "research").glob("run_w*.py")
    if _KEYSTONE_PATTERN.search(f.name)
)

# Pattern that would indicate reading a long_hold data path.
# NOTE — known blind spots (acceptable for v1, per check_synapse_reads.py lines 44-47):
#   os.path.join('data/research', 'long_hold_...')  →  NOT matched (path split across args)
#   'data/research/' + 'long_hold_...'              →  NOT matched (string concatenation)
# The check catches plain literals, f-strings with the full path in one quoted segment,
# and aliased-def literals.  Do not assume it provides exhaustive coverage of all
# possible path constructions.
_LONG_HOLD_PATH_RE = re.compile(r"""['"](data/research/long_hold[^\'"]*)['""]""")


class TestEntryHarnessNoLongHoldReads:
    """Entry-stack research harnesses must contain no literal read of long_hold paths."""

    @pytest.mark.parametrize(
        "script_path",
        [REPO_ROOT / "scripts" / "research" / "entry_strata_phase0.py"],
        ids=["entry_strata_phase0"],
    )
    def test_entry_strata_no_long_hold_path(self, script_path: Path) -> None:
        """entry_strata_phase0.py must not contain any data/research/long_hold_* literal."""
        assert script_path.exists(), f"Entry harness missing: {script_path}"
        source = script_path.read_text(encoding="utf-8", errors="replace")
        matches = _LONG_HOLD_PATH_RE.findall(source)
        assert matches == [], (
            f"{script_path.name} contains literal long_hold path(s): {matches!r}. "
            "Entry harnesses must not read hold-thesis data paths (LH-R1)."
        )

    @pytest.mark.parametrize(
        "script_path",
        _KEYSTONE_FILES if _KEYSTONE_FILES else [None],
        ids=[f.name for f in _KEYSTONE_FILES] if _KEYSTONE_FILES else ["no_keystone_scripts"],
    )
    def test_keystone_no_long_hold_path(self, script_path: Path | None) -> None:
        """Keystone backfill scripts must not contain any data/research/long_hold_* literal."""
        if script_path is None:
            pytest.skip("No keystone backfill scripts found (W1 not yet built)")
        source = script_path.read_text(encoding="utf-8", errors="replace")
        matches = _LONG_HOLD_PATH_RE.findall(source)
        assert matches == [], (
            f"{script_path.name} contains literal long_hold path(s): {matches!r}. "
            "Entry harnesses must not read hold-thesis data paths (LH-R1)."
        )


# ===========================================================================
# Group C — Real registry passes the firewall clean
# ===========================================================================


class TestRealRegistryFirewallClean:
    """The production synapse.yml must pass the horizon firewall with zero violations."""

    def test_real_registry_horizon_firewall_clean(self) -> None:
        """check_horizon_firewall() against the real registry must return no violations."""
        reg = load_registry(REPO_ROOT)
        violations = check_horizon_firewall(reg)
        if violations:
            msgs = [v.label() for v in violations]
            pytest.fail(
                f"Real registry has {len(violations)} horizon firewall violation(s):\n"
                + "\n".join(msgs)
            )

    def test_real_registry_hold_thesis_artifacts_are_only_long_hold(self) -> None:
        """
        W1 PR-E: the ONLY hold_thesis artifacts are the long-hold labels and manifest.
        Any additional hold_thesis artifact must be explicitly added to this allowlist.
        All hold_thesis artifacts must have no scored_path_surfaces (LH-R1 / LH-R7).

        This test replaced the W0 assertion 'no hold_thesis artifacts exist yet'.
        When W3 PR-L adds long_thesis_registry.jsonl, update the allowlist below.
        """
        _EXPECTED_HOLD_THESIS_ARTIFACTS = {
            "long-hold-labels",
            "long-hold-labels-manifest",
            # W1 PR-F kill-test results (#1544, G1-DEFERRED ruling) — hold_thesis by design
            "long-hold-killtest-results",
            # W2 PR-I compounder annotation columns — hold_thesis by design; display-only
            "long-hold-compounder-features",
            # W2 PR-J two display clocks — hold_thesis by design; display-only
            "long-hold-clocks",
            # W2 PR-K moat falsifier sensors and great-company-trap overlay
            "moat-falsifier-sensors",
            "great-company-trap",
            # LT-2a expect_drift feature panel — hold_thesis by design; display-only
            "long-hold-expect-drift-manifest",
            "long-hold-expect-drift-panel",
            # LT-3b insider_sponsor_lh family F4 artifacts — display/research tier only
            "insider-lh-panel",
            "insider-lh-panel-manifest",
            "insider-lh-ruler-p-results",
            # LT-3a capital allocation display block — hold_thesis by design; display-only
            "capital-allocation-delta",
            # LT-2b expect_drift Ruler-P study results — hold_thesis by design; research-only
            "expect-drift-ruler-p-results",
            # LT-2c per-stock expectation-state display block — hold_thesis by design; display-only
            "long-hold-expectation-state",
            # LT-4 thesis funnel shadow — hold_thesis by design; display/research tier only
            "long-hold-thesis-funnel-states",
            "long-hold-thesis-funnel-states-manifest",
            "long-hold-thesis-funnel-panel",
            # LT-4 thesis funnel forward history — hold_thesis by design; display tier only
            "long-hold-thesis-funnel-history",
            # A1 per-fire sector benchmark (#1694) — hold_thesis by design; display tier only
            "per-fire-sector-benchmark",
            # Winner Autopsy Lab (WA-R1..R10) — top-down long-hold department; all display-only
            "winner-episodes",
            "winner-episodes-manifest",
            "breakaway-watch-states",
            "breakaway-watch-history",
            "winner-autopsy-panel",
            "winner-autopsy-manifest",
            # Pick Lab LH grid site artifact (PL-R6 firewall) — display-only, horizon_role=hold_thesis
            "pick-lab-longhold-ledger",
            # LHB-W1 A3 Delivery Waterfall (LHB-R4) — display-only, horizon_role=hold_thesis
            "long-hold-delivery-waterfall",
            "long-hold-delivery-waterfall-panel",
        }
        reg = load_registry(REPO_ROOT)
        hold_arts = {
            art_id
            for art_id, v in (reg.get("artifacts") or {}).items()
            if isinstance(v, dict) and v.get("horizon_role") == "hold_thesis"
        }
        unexpected = hold_arts - _EXPECTED_HOLD_THESIS_ARTIFACTS
        assert not unexpected, (
            f"Unexpected hold_thesis artifacts found: {unexpected}. "
            "If W3+ has landed new hold_thesis artifacts, add them to "
            "_EXPECTED_HOLD_THESIS_ARTIFACTS in this test."
        )
        missing = _EXPECTED_HOLD_THESIS_ARTIFACTS - hold_arts
        assert not missing, (
            f"Expected hold_thesis artifacts are missing from registry: {missing}. "
            "Ensure long-hold-labels and long-hold-labels-manifest are registered "
            "in config/synapse.yml with horizon_role: hold_thesis."
        )
        # All hold_thesis artifacts must have no scored_path_surfaces (LH-R1 / LH-R7)
        artifacts = reg.get("artifacts") or {}
        with_surfaces = [
            art_id
            for art_id in hold_arts
            if list(artifacts.get(art_id, {}).get("scored_path_surfaces") or [])
        ]
        assert not with_surfaces, (
            f"hold_thesis artifact(s) have scored_path_surfaces (LH-R1 violation): "
            f"{with_surfaces}. hold_thesis artifacts must NEVER route to entry surfaces."
        )

    def test_real_registry_tactical_entry_artifacts_present(self) -> None:
        """Sanity: at least some tactical_entry artifacts must be stamped."""
        reg = load_registry(REPO_ROOT)
        entry_arts = [
            art_id
            for art_id, v in (reg.get("artifacts") or {}).items()
            if isinstance(v, dict) and v.get("horizon_role") == "tactical_entry"
        ]
        assert len(entry_arts) >= 1, (
            "No tactical_entry artifacts found in registry — PR-C stamps may not be present."
        )

    def test_article2_map_in_sync_with_registry_meta(self) -> None:
        """
        _ARTICLE2_MAP.keys() must stay in sync with meta.article2_surfaces in
        config/synapse.yml.

        If a future agent charters a new Article-2 entry surface by adding it to
        meta.article2_surfaces without also editing _ARTICLE2_MAP, the Direction-A
        firewall check (_ENTRY_ARTICLE2_SURFACES = frozenset(_ARTICLE2_MAP.keys()))
        would silently fail to catch hold_thesis artifacts routing to that surface.
        This test hard-fails if the two sets diverge (LH-R1 bypass vector).
        """
        reg = load_registry(REPO_ROOT)
        registry_surfaces = set(reg.get("meta", {}).get("article2_surfaces") or [])
        hardcoded_surfaces = set(_ARTICLE2_MAP.keys())
        missing_in_map = registry_surfaces - hardcoded_surfaces
        extra_in_map = hardcoded_surfaces - registry_surfaces
        assert not missing_in_map, (
            f"meta.article2_surfaces in synapse.yml has surfaces not in _ARTICLE2_MAP: "
            f"{missing_in_map!r}. Add them to _ARTICLE2_MAP in scripts/check_synapse_reads.py "
            f"so the Direction-A horizon firewall covers them (LH-R1)."
        )
        assert not extra_in_map, (
            f"_ARTICLE2_MAP in scripts/check_synapse_reads.py has surfaces not in "
            f"meta.article2_surfaces: {extra_in_map!r}. Either add them to synapse.yml or "
            f"remove them from _ARTICLE2_MAP (LH-R1)."
        )

    def test_no_hold_thesis_artifacts_with_scored_path_surfaces_while_hold_map_empty(
        self,
    ) -> None:
        """
        Direction B activation guard: if _HOLD_SURFACE_MAP is still empty (W0/W1/W2)
        but a hold_thesis artifact has declared scored_path_surfaces, the firewall
        has no teeth for that artifact.  Hard-fail here so the W3 author cannot forget
        to populate _HOLD_SURFACE_MAP.

        Once hold surfaces are chartered (W3 PR-L/M), _HOLD_SURFACE_MAP must be
        populated before registering hold_thesis artifacts with scored_path_surfaces.
        """
        if _HOLD_SURFACE_MAP:
            # Direction B is active — this guard is no longer needed.
            return
        reg = load_registry(REPO_ROOT)
        offenders = [
            art_id
            for art_id, v in (reg.get("artifacts") or {}).items()
            if (
                isinstance(v, dict)
                and v.get("horizon_role") == "hold_thesis"
                and list(v.get("scored_path_surfaces") or [])
            )
        ]
        assert offenders == [], (
            f"hold_thesis artifact(s) declare scored_path_surfaces but _HOLD_SURFACE_MAP "
            f"is empty: {offenders!r}. Populate _HOLD_SURFACE_MAP in "
            f"scripts/check_synapse_reads.py before adding hold_thesis scored_path_surfaces "
            f"(LH-R1 Direction-B activation, W3)."
        )
