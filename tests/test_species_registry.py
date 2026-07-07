"""tests/test_species_registry.py — species registry schema, lifecycle, and mirror tests.

Covers:
  1. Schema validation: missing required field → SpeciesSchemaError
  2. horizon_class enum enforcement (no 'both', no unknown values)
  3. Lifecycle transitions: only via transition_validation_status(); terminal states block further moves
  4. Version bump required for horizon_class change (enforced in bump_version())
  5. Mirror idempotency: running mirror_to_experiments twice adds nothing new
  6. Curated-entry preservation: mirror never touches non-species entries
  7. Registry I/O round-trip
  8. Full registry.json seed loads without errors
"""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from engine.species_registry import (
    REGISTRY_PATH,
    EXPERIMENTS_SEED_PATH,
    VALID_HORIZON_CLASSES,
    VALID_VALIDATION_STATUSES,
    TERMINAL_VALIDATION_STATUSES,
    SpeciesSchemaError,
    SpeciesLifecycleError,
    validate_entry,
    transition_validation_status,
    bump_version,
    load,
    save,
    upsert_species,
    mirror_to_experiments,
    sync,
)


# ---------------------------------------------------------------------------
# Helpers: minimal valid entry factory
# ---------------------------------------------------------------------------

def _min_entry(**overrides) -> dict:
    """Return the smallest valid species entry."""
    base = {
        "species_id": "TEST1",
        "version": "1.0",
        "name": "Test Species",
        "validation_status": "phase0",
        "deployment_status": "unshipped",
        "mechanism": "Sellers exhaust when the widget supply is gone.",
        "horizon_class": "positional",
        "evidence_stack": [{"condition": "widget_washout >= 0.5", "tag": "arming"}],
        "rejection_rules": [{"rule": "extension_demote", "prevents": "chasing"}],
        "archetype_scope": {"applies": ["all"], "hostile": [], "note": "test"},
        "regime_scope": {
            "hypothesized_supportive": [],
            "hypothesized_hostile": [],
            "learnable_projection": {
                "axes": ["vol_regime"],
                "cells": ["low-vol", "high-vol"],
                "note": "test",
            },
        },
        "market_scope": ["US"],
        "adjacent_falsified": [],
        "fixtures": [],
        "ledger_binding": {
            "ledger": "us_board_ledger",
            "since": "2026-07-03",
            "flip_criteria": "§1.3 template",
        },
        "gating": {
            "come_back_on": None,
            "cadence": "monthly",
            "maturation": "n_matured >= 40",
        },
        "trial_count": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Schema validation — missing required field
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_valid_entry_passes(self):
        validate_entry(_min_entry())

    def test_missing_species_id(self):
        e = _min_entry()
        del e["species_id"]
        with pytest.raises(SpeciesSchemaError, match="missing required fields"):
            validate_entry(e)

    def test_missing_mechanism(self):
        e = _min_entry()
        del e["mechanism"]
        with pytest.raises(SpeciesSchemaError, match="missing required fields"):
            validate_entry(e)

    def test_missing_gating(self):
        e = _min_entry()
        del e["gating"]
        with pytest.raises(SpeciesSchemaError, match="missing required fields"):
            validate_entry(e)

    def test_missing_ledger_binding(self):
        e = _min_entry()
        del e["ledger_binding"]
        with pytest.raises(SpeciesSchemaError, match="missing required fields"):
            validate_entry(e)

    def test_missing_trial_count(self):
        e = _min_entry()
        del e["trial_count"]
        with pytest.raises(SpeciesSchemaError, match="missing required fields"):
            validate_entry(e)

    def test_all_required_fields_present(self):
        """Enumerate every required field and ensure each alone causes rejection."""
        required = [
            "species_id", "version", "name", "validation_status", "deployment_status",
            "mechanism", "horizon_class", "evidence_stack", "rejection_rules",
            "archetype_scope", "regime_scope", "market_scope", "adjacent_falsified",
            "fixtures", "ledger_binding", "gating", "trial_count",
        ]
        for field in required:
            e = _min_entry()
            del e[field]
            with pytest.raises(SpeciesSchemaError):
                validate_entry(e)

    def test_trial_count_negative(self):
        e = _min_entry(trial_count=-1)
        with pytest.raises(SpeciesSchemaError, match="trial_count"):
            validate_entry(e)

    def test_trial_count_float(self):
        e = _min_entry(trial_count=1.5)
        with pytest.raises(SpeciesSchemaError, match="trial_count"):
            validate_entry(e)

    def test_ledger_binding_missing_flip_criteria(self):
        e = _min_entry()
        e["ledger_binding"] = {"ledger": "x", "since": "2026-01-01"}
        with pytest.raises(SpeciesSchemaError, match="flip_criteria"):
            validate_entry(e)

    def test_gating_missing_maturation(self):
        e = _min_entry()
        e["gating"] = {"come_back_on": None, "cadence": "monthly"}
        with pytest.raises(SpeciesSchemaError, match="maturation"):
            validate_entry(e)

    def test_regime_scope_missing_learnable_projection(self):
        e = _min_entry()
        e["regime_scope"] = {"hypothesized_supportive": [], "hypothesized_hostile": []}
        with pytest.raises(SpeciesSchemaError, match="learnable_projection"):
            validate_entry(e)


# ---------------------------------------------------------------------------
# 2. horizon_class enforcement
# ---------------------------------------------------------------------------

class TestHorizonClass:
    def test_both_rejected(self):
        e = _min_entry(horizon_class="both")
        with pytest.raises(SpeciesSchemaError, match="both.*disallowed|not one of"):
            validate_entry(e)

    def test_unknown_string_rejected(self):
        e = _min_entry(horizon_class="tactical")
        with pytest.raises(SpeciesSchemaError):
            validate_entry(e)

    def test_positional_valid(self):
        validate_entry(_min_entry(horizon_class="positional"))

    def test_rotational_valid(self):
        validate_entry(_min_entry(horizon_class="rotational"))

    def test_all_valid_classes(self):
        for hc in VALID_HORIZON_CLASSES:
            validate_entry(_min_entry(horizon_class=hc))


# ---------------------------------------------------------------------------
# 3. Lifecycle enforcement
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_phase0_to_accruing(self):
        e = _min_entry(validation_status="phase0")
        updated = transition_validation_status(e, "accruing", reviewer="test", reason="enough data")
        assert updated["validation_status"] == "accruing"

    def test_phase0_to_falsified(self):
        e = _min_entry(validation_status="phase0")
        updated = transition_validation_status(e, "falsified", reviewer="test", reason="failed gates")
        assert updated["validation_status"] == "falsified"

    def test_accruing_to_validated(self):
        e = _min_entry(validation_status="accruing")
        updated = transition_validation_status(e, "validated", reviewer="test", reason="passed")
        assert updated["validation_status"] == "validated"

    def test_phase0_cannot_jump_to_validated_directly(self):
        e = _min_entry(validation_status="phase0")
        with pytest.raises(SpeciesLifecycleError):
            transition_validation_status(e, "validated", reviewer="test", reason="skip")

    def test_falsified_is_terminal(self):
        e = _min_entry(validation_status="falsified")
        with pytest.raises(SpeciesLifecycleError, match="terminal"):
            transition_validation_status(e, "retired", reviewer="test", reason="re-trying")

    def test_retired_is_terminal(self):
        e = _min_entry(validation_status="retired")
        with pytest.raises(SpeciesLifecycleError, match="terminal"):
            transition_validation_status(e, "phase0", reviewer="test", reason="reopen")

    def test_lifecycle_log_appended(self):
        e = _min_entry(validation_status="phase0")
        updated = transition_validation_status(e, "accruing", reviewer="alice", reason="data ready")
        log = updated.get("_lifecycle_log", [])
        assert len(log) == 1
        assert log[0]["from"] == "phase0"
        assert log[0]["to"] == "accruing"
        assert log[0]["reviewer"] == "alice"

    def test_original_entry_not_mutated(self):
        e = _min_entry(validation_status="phase0")
        original_status = e["validation_status"]
        transition_validation_status(e, "accruing", reviewer="test", reason="x")
        assert e["validation_status"] == original_status  # original unchanged

    def test_invalid_target_status_rejected(self):
        e = _min_entry(validation_status="phase0")
        with pytest.raises(SpeciesLifecycleError):
            transition_validation_status(e, "unknown_state", reviewer="test", reason="x")


# ---------------------------------------------------------------------------
# 4. Version bump required for horizon_class change
# ---------------------------------------------------------------------------

class TestVersionBump:
    def test_bump_version_changes_version(self):
        e = _min_entry(version="1.0", horizon_class="positional")
        bumped = bump_version(e, "2.0", new_horizon_class="rotational")
        assert bumped["version"] == "2.0"
        assert bumped["horizon_class"] == "rotational"

    def test_bump_resets_status_to_phase0(self):
        e = _min_entry(validation_status="accruing")
        bumped = bump_version(e, "2.0")
        assert bumped["validation_status"] == "phase0"
        assert bumped["deployment_status"] == "unshipped"

    def test_bump_with_invalid_horizon_class_rejected(self):
        e = _min_entry()
        with pytest.raises(SpeciesLifecycleError):
            bump_version(e, "2.0", new_horizon_class="both")

    def test_bump_appends_lifecycle_log(self):
        e = _min_entry(version="1.0")
        bumped = bump_version(e, "2.0", reviewer="bob", reason="horizon change")
        log = bumped.get("_lifecycle_log", [])
        assert any(entry.get("event") == "version_bump" for entry in log)

    def test_bump_without_horizon_change_preserves_class(self):
        e = _min_entry(horizon_class="positional")
        bumped = bump_version(e, "1.1")
        assert bumped["horizon_class"] == "positional"


# ---------------------------------------------------------------------------
# 5 + 6. Mirror idempotency and curated-entry preservation
# ---------------------------------------------------------------------------

class TestMirrorIdempotency:
    def _make_seed(self, extra_experiments: list[dict] | None = None) -> dict:
        """Minimal experiments seed with curated entries."""
        seed = {
            "schema": "experiments_registry_seed.v1",
            "experiments": [
                {
                    "id": "curated-entry-1",
                    "name": "A curated experiment",
                    "kind": "track_record",
                    "status": "accruing",
                    "what": "Something curated",
                    "source": "engine/some_module.py",
                },
            ],
        }
        if extra_experiments:
            seed["experiments"].extend(extra_experiments)
        return seed

    def _registry_with_one_species(self) -> dict:
        return {
            "schema": "species_registry.v1",
            "species": [_min_entry()],
        }

    def test_first_mirror_adds_entry(self):
        registry = self._registry_with_one_species()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self._make_seed(), f, indent=2)
            seed_path = pathlib.Path(f.name)
        try:
            n = mirror_to_experiments(registry, seed_path)
            assert n == 1
            seed = json.loads(seed_path.read_text())
            ids = [e["id"] for e in seed["experiments"]]
            assert "species-TEST1" in ids
        finally:
            seed_path.unlink(missing_ok=True)

    def test_second_mirror_adds_nothing(self):
        registry = self._registry_with_one_species()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self._make_seed(), f, indent=2)
            seed_path = pathlib.Path(f.name)
        try:
            mirror_to_experiments(registry, seed_path)
            n2 = mirror_to_experiments(registry, seed_path)
            # Second run: status/phase_hint didn't change → 0 changed
            assert n2 == 0
            seed = json.loads(seed_path.read_text())
            species_entries = [e for e in seed["experiments"] if e["id"].startswith("species-")]
            assert len(species_entries) == 1
        finally:
            seed_path.unlink(missing_ok=True)

    def test_curated_entry_preserved(self):
        registry = self._registry_with_one_species()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self._make_seed(), f, indent=2)
            seed_path = pathlib.Path(f.name)
        try:
            mirror_to_experiments(registry, seed_path)
            seed = json.loads(seed_path.read_text())
            curated = [e for e in seed["experiments"] if e["id"] == "curated-entry-1"]
            assert len(curated) == 1
            assert curated[0]["kind"] == "track_record"  # unchanged
            assert curated[0]["name"] == "A curated experiment"  # unchanged
        finally:
            seed_path.unlink(missing_ok=True)

    def test_curated_entry_not_overwritten_by_mirror(self):
        """Mirror MUST NOT touch non-species entries, even if they have overlapping keys."""
        registry = self._registry_with_one_species()
        seed = self._make_seed()
        # Add a curated entry with a key that resembles a species entry but isn't one
        seed["experiments"].append({
            "id": "not-a-species-entry",
            "name": "Manual curated thing",
            "kind": "phase0",
            "status": "accruing",
            "custom_field": "should survive",
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(seed, f, indent=2)
            seed_path = pathlib.Path(f.name)
        try:
            mirror_to_experiments(registry, seed_path)
            result = json.loads(seed_path.read_text())
            manual = [e for e in result["experiments"] if e["id"] == "not-a-species-entry"]
            assert len(manual) == 1
            assert manual[0]["custom_field"] == "should survive"
        finally:
            seed_path.unlink(missing_ok=True)

    def test_status_update_triggers_rewrite(self):
        """If validation_status changes on the species, mirror should update the exp entry."""
        entry = _min_entry(validation_status="phase0")
        registry = {"schema": "species_registry.v1", "species": [entry]}

        # Pre-seed with the mirror entry already at 'registered'
        existing_exp = {
            "id": "species-TEST1",
            "name": "Setup Species TEST1 — Test Species",
            "kind": "species_phase0",
            "status": "registered",
            "phase_hint": "horizon=positional deployment=unshipped",
        }
        seed = self._make_seed(extra_experiments=[existing_exp])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(seed, f, indent=2)
            seed_path = pathlib.Path(f.name)
        try:
            # Now update the registry entry to accruing
            entry2 = dict(entry)
            entry2["validation_status"] = "accruing"
            entry2["deployment_status"] = "chip"
            registry2 = {"schema": "species_registry.v1", "species": [entry2]}
            n = mirror_to_experiments(registry2, seed_path)
            assert n == 1  # one changed
            result = json.loads(seed_path.read_text())
            sp_entry = next(e for e in result["experiments"] if e["id"] == "species-TEST1")
            assert sp_entry["status"] == "accruing"
        finally:
            seed_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 7. Registry I/O round-trip
# ---------------------------------------------------------------------------

class TestRegistryIO:
    def test_load_save_round_trip(self):
        registry = {"schema": "species_registry.v1", "species": [_min_entry()]}
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "species" / "registry.json"
            save(registry, p)
            loaded = load(p)
        assert loaded["schema"] == "species_registry.v1"
        assert len(loaded["species"]) == 1
        assert loaded["species"][0]["species_id"] == "TEST1"

    def test_load_absent_returns_empty(self):
        result = load(pathlib.Path("/nonexistent/registry.json"))
        assert result == {"schema": "species_registry.v1", "species": []}

    def test_upsert_new_entry(self):
        reg = {"schema": "species_registry.v1", "species": []}
        e = _min_entry()
        reg = upsert_species(reg, e)
        assert len(reg["species"]) == 1

    def test_upsert_replaces_existing(self):
        e1 = _min_entry(name="Original")
        reg = {"schema": "species_registry.v1", "species": [e1]}
        e2 = _min_entry(name="Updated")
        reg = upsert_species(reg, e2)
        assert len(reg["species"]) == 1
        assert reg["species"][0]["name"] == "Updated"

    def test_upsert_rejects_invalid_entry(self):
        reg = {"schema": "species_registry.v1", "species": []}
        e = _min_entry()
        del e["mechanism"]
        with pytest.raises(SpeciesSchemaError):
            upsert_species(reg, e)


# ---------------------------------------------------------------------------
# 8. Full seed registry.json validates without errors
# ---------------------------------------------------------------------------

class TestSeedRegistryValid:
    def test_registry_json_exists(self):
        assert REGISTRY_PATH.exists(), f"data/species/registry.json not found at {REGISTRY_PATH}"

    def test_all_seed_entries_valid(self):
        """Every entry in data/species/registry.json must pass schema validation."""
        registry = load(REGISTRY_PATH)
        species = registry.get("species", [])
        assert len(species) > 0, "registry.json has no species entries"
        errors = []
        for e in species:
            try:
                validate_entry(e)
            except SpeciesSchemaError as exc:
                errors.append(str(exc))
        assert not errors, f"Schema errors in seed:\n" + "\n".join(errors)

    def test_all_horizon_classes_are_valid(self):
        registry = load(REGISTRY_PATH)
        for e in registry.get("species", []):
            assert e.get("horizon_class") in VALID_HORIZON_CLASSES, (
                f"species {e.get('species_id')}: invalid horizon_class {e.get('horizon_class')!r}"
            )

    def test_no_both_horizon_class(self):
        registry = load(REGISTRY_PATH)
        for e in registry.get("species", []):
            assert e.get("horizon_class") != "both", (
                f"species {e.get('species_id')}: 'both' horizon_class is disallowed (§1.1)"
            )

    def test_all_validation_statuses_valid(self):
        registry = load(REGISTRY_PATH)
        for e in registry.get("species", []):
            assert e.get("validation_status") in VALID_VALIDATION_STATUSES

    def test_tier_a_species_present(self):
        """S1, S2, T1-T4, CN-WASHOUT, CN-REVERSAL, DISLOC must be in the seed."""
        registry = load(REGISTRY_PATH)
        ids = {e["species_id"] for e in registry.get("species", [])}
        required = {"S1", "S2", "T1-T4", "CN-WASHOUT", "CN-REVERSAL", "DISLOC"}
        missing = required - ids
        assert not missing, f"Missing Tier-A validated species: {missing}"

    def test_phase0_species_present(self):
        """S3-S13 must be in the seed."""
        registry = load(REGISTRY_PATH)
        ids = {e["species_id"] for e in registry.get("species", [])}
        required = {"S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"}
        missing = required - ids
        assert not missing, f"Missing phase-0 species: {missing}"

    def test_s6_mechanism_contains_in_sample_honesty(self):
        """S6 mechanism must contain the 'in-sample only' honesty qualifier from §4."""
        registry = load(REGISTRY_PATH)
        s6 = next((e for e in registry.get("species", []) if e["species_id"] == "S6"), None)
        assert s6 is not None
        mech = s6.get("mechanism", "").lower()
        assert "in-sample only" in mech or "in-sample" in mech, (
            "S6 mechanism must contain 'in-sample only' qualifier per §4 honesty requirement"
        )

    def test_data_gated_species_have_come_back_on(self):
        """Pending data-gated species (S8, S10, S11, S12) must have gating.come_back_on
        set — unless they have reached a terminal status (falsified/retired), which has
        no come-back (S11 was falsified at W5 phase-0, 2026-07-06)."""
        registry = load(REGISTRY_PATH)
        gated = {"S8", "S10", "S11", "S12"}
        terminal = {"falsified", "retired"}
        for e in registry.get("species", []):
            if e["species_id"] in gated and e.get("validation_status") not in terminal:
                come_back = e.get("gating", {}).get("come_back_on")
                assert come_back is not None, (
                    f"Species {e['species_id']} is data-gated but has no gating.come_back_on"
                )

    def test_experiments_seed_exists(self):
        assert EXPERIMENTS_SEED_PATH.exists(), (
            f"data/experiments/registry_seed.json not found at {EXPERIMENTS_SEED_PATH}"
        )

    def test_sync_produces_no_schema_errors(self):
        """sync() on the real registry must return no errors."""
        result = sync()
        assert result["errors"] == [], (
            f"sync() found schema errors:\n" + "\n".join(result["errors"])
        )

    def test_sync_counts_species(self):
        result = sync()
        assert result["n_species"] >= 13, (
            f"Expected ≥13 species in the seed, found {result['n_species']}"
        )


# ---------------------------------------------------------------------------
# W1 regime-directive display wiring (§7)
# ---------------------------------------------------------------------------
class TestRegimeContextWiring:

    def test_mirror_carries_live_regime_context(self, tmp_path, monkeypatch):
        import engine.species_registry as sr
        seed = {"experiments": []}
        ep = tmp_path / "registry_seed.json"
        ep.write_text(json.dumps(seed))
        monkeypatch.setattr(
            sr, "_live_regime_context",
            lambda: "rate_pressure=neutral · favor_entries=True (vector asof 2026-07-04)")
        reg = {"species": [{"species_id": "S1", "name": "X",
                            "validation_status": "phase0",
                            "deployment_status": "unshipped",
                            "horizon_class": "positional",
                            "mechanism": "m", "gating": {}, "ledger_binding": {}}]}
        n = sr.mirror_to_experiments(reg, experiments_path=ep)
        assert n == 1
        out = json.loads(ep.read_text())
        assert out["experiments"][0]["regime_context"].startswith("rate_pressure=neutral")

    def test_context_change_triggers_update(self, tmp_path, monkeypatch):
        import engine.species_registry as sr
        ep = tmp_path / "registry_seed.json"
        ep.write_text(json.dumps({"experiments": []}))
        reg = {"species": [{"species_id": "S1", "name": "X",
                            "validation_status": "phase0",
                            "deployment_status": "unshipped",
                            "horizon_class": "positional",
                            "mechanism": "m", "gating": {}, "ledger_binding": {}}]}
        monkeypatch.setattr(sr, "_live_regime_context", lambda: "A (vector asof d1)")
        sr.mirror_to_experiments(reg, experiments_path=ep)
        monkeypatch.setattr(sr, "_live_regime_context", lambda: "B (vector asof d2)")
        n = sr.mirror_to_experiments(reg, experiments_path=ep)
        assert n == 1   # context change alone must refresh the mirror row
        out = json.loads(ep.read_text())
        assert out["experiments"][0]["regime_context"].startswith("B")

    def test_absent_vector_omits_field(self, tmp_path, monkeypatch):
        import engine.species_registry as sr
        ep = tmp_path / "registry_seed.json"
        ep.write_text(json.dumps({"experiments": []}))
        monkeypatch.setattr(sr, "_live_regime_context", lambda: None)
        reg = {"species": [{"species_id": "S1", "name": "X",
                            "validation_status": "phase0",
                            "deployment_status": "unshipped",
                            "horizon_class": "positional",
                            "mechanism": "m", "gating": {}, "ledger_binding": {}}]}
        sr.mirror_to_experiments(reg, experiments_path=ep)
        out = json.loads(ep.read_text())
        assert "regime_context" not in out["experiments"][0]
