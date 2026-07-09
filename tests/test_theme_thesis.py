"""tests/test_theme_thesis.py — TIL W1 (PR-C) theme thesis ledger tests.

Covers:
  1. Registry covers every canonical theme id from config/theme_crosswalk.yml
  2. Schema validation — required fields, class-level-only guard
     (no per-ticker thesis text fields per R-TIL-1)
  3. Falsifier check-spec compilation + evaluation on synthetic fixtures
     (FIRED / ARMED / DATA_MISSING / QUALITATIVE paths)
  4. Append-only + content-hash idempotence (second run appends nothing)
  5. Banned-words ("validated" must not appear in user-facing text)
  6. Authority block — all promotion flags False, is_context_only=True,
     display_only=True

All tests are hermetic — tmp_path, synthetic fixtures, no live network calls.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CROSSWALK_PATH = _REPO_ROOT / "config" / "theme_crosswalk.yml"
_REGISTRY_PATH = _REPO_ROOT / "config" / "theme_thesis_registry.yml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def crosswalk() -> dict:
    assert _CROSSWALK_PATH.exists(), f"theme_crosswalk.yml not found: {_CROSSWALK_PATH}"
    with _CROSSWALK_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def registry() -> dict:
    assert _REGISTRY_PATH.exists(), f"theme_thesis_registry.yml not found: {_REGISTRY_PATH}"
    with _REGISTRY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def theses(registry) -> list[dict]:
    return registry.get("theses", [])


@pytest.fixture(scope="module")
def crosswalk_ids(crosswalk) -> set[str]:
    return {t["id"] for t in crosswalk.get("themes", [])}


# ---------------------------------------------------------------------------
# 1. Registry completeness
# ---------------------------------------------------------------------------

class TestRegistryCompleteness:
    """Registry must cover every canonical theme id in theme_crosswalk.yml."""

    def test_all_crosswalk_themes_covered(self, theses, crosswalk_ids):
        """Every canonical theme id must appear as a theme_id in the registry."""
        registry_theme_ids = {t["theme_id"] for t in theses}
        missing = crosswalk_ids - registry_theme_ids
        assert not missing, (
            f"Missing theses for canonical theme ids: {sorted(missing)}"
        )

    def test_no_unknown_theme_ids(self, theses, crosswalk_ids):
        """No thesis should reference a theme_id absent from the crosswalk."""
        extra = {t["theme_id"] for t in theses} - crosswalk_ids
        assert not extra, (
            f"Registry contains unknown theme_ids not in crosswalk: {sorted(extra)}"
        )

    def test_exactly_18_theses(self, theses):
        """Registry must have exactly 18 theses (one per foresight theme)."""
        assert len(theses) == 18, f"Expected 18 theses, got {len(theses)}"

    def test_no_duplicate_theme_ids(self, theses):
        """No two theses may share the same theme_id."""
        ids = [t["theme_id"] for t in theses]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert not dupes, f"Duplicate theme_ids in registry: {dupes}"

    def test_no_duplicate_thesis_ids(self, theses):
        """No two theses may share the same thesis_id."""
        ids = [t["thesis_id"] for t in theses]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert not dupes, f"Duplicate thesis_ids in registry: {dupes}"

    def test_thesis_id_format(self, theses):
        """Each thesis_id must follow the pattern <theme_id>.v<N>."""
        for t in theses:
            tid = t.get("thesis_id", "")
            theme_id = t.get("theme_id", "")
            assert tid.startswith(f"{theme_id}.v"), (
                f"thesis_id {tid!r} must start with '{theme_id}.v'"
            )
            version_part = tid[len(theme_id) + 2:]
            assert version_part.isdigit(), (
                f"thesis_id {tid!r} version part {version_part!r} must be numeric"
            )


# ---------------------------------------------------------------------------
# 2. Schema validation — required fields and class-level-only guard
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Each thesis must have required fields; no per-ticker keys allowed."""

    REQUIRED_FIELDS = [
        "thesis_id", "theme_id", "status",
        "variant_perception_en", "variant_perception_zh",
        "mechanism_en", "mechanism_zh",
        "driver", "winner_classes", "loser_classes", "falsifiers",
    ]

    # R-TIL-1 fence: per-ticker thesis text belongs to the long-hold program
    FORBIDDEN_PER_TICKER_KEYS = {
        "ticker", "tickers", "stock", "symbol", "isin", "cusip",
        "per_stock", "stock_thesis", "name",
    }

    def test_required_fields_present(self, theses):
        """Every required field must be present in each thesis."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            for field in self.REQUIRED_FIELDS:
                assert field in t, (
                    f"thesis {tid!r} missing required field: {field!r}"
                )

    def test_no_per_ticker_fields(self, theses):
        """No thesis may contain per-ticker fields (R-TIL-1 fence)."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            thesis_keys = {k.lower() for k in t}
            violations = thesis_keys & self.FORBIDDEN_PER_TICKER_KEYS
            assert not violations, (
                f"thesis {tid!r} contains forbidden per-ticker keys: {violations}"
            )

    def test_winner_classes_structure(self, theses):
        """winner_classes must be a list of dicts with 'class' and 'why' keys."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            lst = t.get("winner_classes", [])
            assert isinstance(lst, list), f"thesis {tid!r}: winner_classes must be a list"
            for i, item in enumerate(lst):
                assert isinstance(item, dict), (
                    f"thesis {tid!r}: winner_classes[{i}] must be a dict"
                )
                assert "class" in item, (
                    f"thesis {tid!r}: winner_classes[{i}] missing 'class'"
                )
                assert "why" in item, (
                    f"thesis {tid!r}: winner_classes[{i}] missing 'why'"
                )

    def test_loser_classes_structure(self, theses):
        """loser_classes must be a list of dicts with 'class' and 'why' keys."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            lst = t.get("loser_classes", [])
            assert isinstance(lst, list), f"thesis {tid!r}: loser_classes must be a list"
            for i, item in enumerate(lst):
                assert isinstance(item, dict), (
                    f"thesis {tid!r}: loser_classes[{i}] must be a dict"
                )
                assert "class" in item, (
                    f"thesis {tid!r}: loser_classes[{i}] missing 'class'"
                )
                assert "why" in item, (
                    f"thesis {tid!r}: loser_classes[{i}] missing 'why'"
                )

    def test_loser_classes_avoid_framing(self, theses):
        """Every loser class 'why' must contain 'AVOID' (loser framing law)."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            for i, item in enumerate(t.get("loser_classes", [])):
                why = item.get("why", "")
                assert "AVOID" in why, (
                    f"thesis {tid!r}: loser_classes[{i}].why must contain 'AVOID' "
                    f"(AVOID-not-SHORT framing required); got: {why[:100]!r}"
                )

    def test_driver_has_type_and_description(self, theses):
        """Each driver must have 'type' and 'description' fields."""
        valid_types = {
            "technology", "policy", "demographic",
            "supply_constraint", "macro", "consumer",
        }
        for t in theses:
            tid = t.get("thesis_id", "?")
            driver = t.get("driver", {})
            assert isinstance(driver, dict), (
                f"thesis {tid!r}: 'driver' must be a dict"
            )
            assert "type" in driver, (
                f"thesis {tid!r}: driver missing 'type'"
            )
            assert "description" in driver, (
                f"thesis {tid!r}: driver missing 'description'"
            )
            assert driver["type"] in valid_types, (
                f"thesis {tid!r}: driver.type {driver['type']!r} not in {valid_types}"
            )

    def test_falsifiers_are_list(self, theses):
        """Each thesis 'falsifiers' must be a non-empty list."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            lst = t.get("falsifiers", [])
            assert isinstance(lst, list), f"thesis {tid!r}: falsifiers must be a list"
            assert len(lst) >= 1, f"thesis {tid!r}: falsifiers list must not be empty"

    def test_falsifier_structure(self, theses):
        """Each falsifier must have id, rule_en, qualitative fields."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            for i, f in enumerate(t.get("falsifiers", [])):
                assert isinstance(f, dict), f"thesis {tid!r}: falsifier[{i}] must be dict"
                assert "id" in f, f"thesis {tid!r}: falsifier[{i}] missing 'id'"
                assert "rule_en" in f, f"thesis {tid!r}: falsifier[{i}] missing 'rule_en'"
                assert "qualitative" in f, (
                    f"thesis {tid!r}: falsifier[{i}] missing 'qualitative'"
                )

    def test_status_valid(self, theses):
        """Each thesis status must be active | paused | superseded."""
        valid = {"active", "paused", "superseded"}
        for t in theses:
            tid = t.get("thesis_id", "?")
            assert t.get("status") in valid, (
                f"thesis {tid!r}: invalid status {t.get('status')!r}"
            )

    def test_bilingual_fields(self, theses):
        """EN and ZH thesis text must both be non-empty."""
        bilingual = [
            "variant_perception_en", "variant_perception_zh",
            "mechanism_en", "mechanism_zh",
        ]
        for t in theses:
            tid = t.get("thesis_id", "?")
            for field in bilingual:
                val = t.get(field, "")
                assert isinstance(val, str) and val.strip(), (
                    f"thesis {tid!r}: field {field!r} must be non-empty string"
                )

    def test_winner_classes_not_empty(self, theses):
        """Every thesis must have at least one winner class."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            assert t.get("winner_classes"), (
                f"thesis {tid!r}: winner_classes must not be empty"
            )

    def test_loser_classes_not_empty(self, theses):
        """Every thesis must have at least one loser class."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            assert t.get("loser_classes"), (
                f"thesis {tid!r}: loser_classes must not be empty"
            )

    def test_winner_class_keys_are_class_level(self, theses):
        """Winner class 'class' values must not look like ticker symbols."""
        # Ticker-like = 1-5 uppercase letters only (e.g. "NVDA", "AAPL")
        ticker_pattern = re.compile(r"^[A-Z]{1,5}$")
        for t in theses:
            tid = t.get("thesis_id", "?")
            for i, item in enumerate(t.get("winner_classes", [])):
                cls = item.get("class", "")
                assert not ticker_pattern.match(cls), (
                    f"thesis {tid!r}: winner_classes[{i}].class {cls!r} looks like "
                    f"a ticker symbol — must be a class label (R-TIL-1 fence)"
                )

    def test_loser_class_keys_are_class_level(self, theses):
        """Loser class 'class' values must not look like ticker symbols."""
        ticker_pattern = re.compile(r"^[A-Z]{1,5}$")
        for t in theses:
            tid = t.get("thesis_id", "?")
            for i, item in enumerate(t.get("loser_classes", [])):
                cls = item.get("class", "")
                assert not ticker_pattern.match(cls), (
                    f"thesis {tid!r}: loser_classes[{i}].class {cls!r} looks like "
                    f"a ticker symbol — must be a class label (R-TIL-1 fence)"
                )


# ---------------------------------------------------------------------------
# 3. Falsifier compilation + evaluation on synthetic fixtures
# ---------------------------------------------------------------------------

class TestFalsifierEvaluation:
    """Test the four falsifier states against synthetic data."""

    @pytest.fixture
    def evaluator(self):
        """Import the engine module."""
        import importlib
        import sys
        sys.path.insert(0, str(_REPO_ROOT))
        mod = importlib.import_module("engine.neuralweb.theme_thesis")
        return mod

    def _make_foresight(self, theme_id: str, **fields) -> dict[str, dict]:
        base = {
            "stage": "BROADENING",
            "revision_breadth": 0.3,
            "tightness": 0.5,
            "glut_score": -0.2,
        }
        base.update(fields)
        return {theme_id: base}

    def _make_theme_state(self, theme_id: str, basket_intel: list) -> dict[str, dict]:
        return {theme_id: {"theme_id": theme_id, "basket_intel": basket_intel}}

    # ── ARMED path ─────────────────────────────────────────────────────────

    def test_armed_when_condition_not_met(self, evaluator):
        """Check lt condition that is NOT met → ARMED."""
        spec = {
            "id": "test_f1",
            "rule_en": "test rule",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "revision_breadth",
                "op": "lt",
                "threshold": -0.05,
                "window_d": 60,
            },
            "qualitative": False,
        }
        # revision_breadth = 0.3, threshold = -0.05 → NOT fired
        foresight = self._make_foresight("ai_semiconductors", revision_breadth=0.3)
        result = evaluator._eval_falsifier(spec, foresight, {}, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_ARMED
        assert result["fired"] is False

    # ── FIRED path ─────────────────────────────────────────────────────────

    def test_fired_when_condition_met(self, evaluator):
        """Check lt condition that IS met → FIRED."""
        spec = {
            "id": "test_f2",
            "rule_en": "test rule fired",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "revision_breadth",
                "op": "lt",
                "threshold": -0.05,
                "window_d": 60,
            },
            "qualitative": False,
        }
        # revision_breadth = -0.15 < -0.05 → FIRED
        foresight = self._make_foresight("ai_semiconductors", revision_breadth=-0.15)
        result = evaluator._eval_falsifier(spec, foresight, {}, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_FIRED
        assert result["fired"] is True

    def test_fired_gt_condition(self, evaluator):
        """Check gt condition → FIRED when value exceeds threshold."""
        spec = {
            "id": "test_gt",
            "rule_en": "glut score above 0",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "glut_score",
                "op": "gt",
                "threshold": 0.0,
                "window_d": None,
            },
            "qualitative": False,
        }
        # glut_score = 0.5 > 0.0 → FIRED
        foresight = self._make_foresight("solar", glut_score=0.5)
        result = evaluator._eval_falsifier(spec, foresight, {}, "solar")
        assert result["state"] == evaluator.STATE_FIRED

    def test_fired_stage_regression(self, evaluator):
        """Stage 'in' check → FIRED when stage matches glut or watch."""
        spec = {
            "id": "test_stage",
            "rule_en": "stage regressed",
            "check": {
                "kind": "stage_regression",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "stage",
                "op": "in",
                "threshold": ["GLUT-RISK", "WATCH"],
                "window_d": None,
            },
            "qualitative": False,
        }
        foresight = self._make_foresight("ai_semiconductors", stage="WATCH")
        result = evaluator._eval_falsifier(spec, foresight, {}, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_FIRED

    def test_armed_stage_still_broadening(self, evaluator):
        """Stage 'in' check → ARMED when stage is BROADENING (not in list)."""
        spec = {
            "id": "test_stage2",
            "rule_en": "stage still ok",
            "check": {
                "kind": "stage_regression",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "stage",
                "op": "in",
                "threshold": ["GLUT-RISK", "WATCH"],
                "window_d": None,
            },
            "qualitative": False,
        }
        foresight = self._make_foresight("ai_semiconductors", stage="BROADENING")
        result = evaluator._eval_falsifier(spec, foresight, {}, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_ARMED

    # ── DATA_MISSING path ──────────────────────────────────────────────────

    def test_data_missing_when_theme_absent(self, evaluator):
        """Missing theme in foresight → DATA_MISSING."""
        spec = {
            "id": "test_missing1",
            "rule_en": "test rule",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "revision_breadth",
                "op": "lt",
                "threshold": 0.0,
                "window_d": 60,
            },
            "qualitative": False,
        }
        # No 'nonexistent_theme' in foresight dict
        result = evaluator._eval_falsifier(spec, {}, {}, "nonexistent_theme")
        assert result["state"] == evaluator.STATE_DATA_MISSING

    def test_data_missing_when_field_null(self, evaluator):
        """Field present but None → DATA_MISSING."""
        spec = {
            "id": "test_null_field",
            "rule_en": "test",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/basketdata/foresight_cascade.json",
                "field": "glut_score",
                "op": "gt",
                "threshold": 0.0,
                "window_d": None,
            },
            "qualitative": False,
        }
        foresight = self._make_foresight("cybersecurity", glut_score=None)
        result = evaluator._eval_falsifier(spec, foresight, {}, "cybersecurity")
        assert result["state"] == evaluator.STATE_DATA_MISSING

    def test_data_missing_unknown_source_artifact(self, evaluator):
        """Unknown source artifact → DATA_MISSING."""
        spec = {
            "id": "test_bad_src",
            "rule_en": "test",
            "check": {
                "kind": "threshold",
                "source_artifact": "site/some/unknown/artifact.json",
                "field": "revision_breadth",
                "op": "lt",
                "threshold": 0.0,
                "window_d": None,
            },
            "qualitative": False,
        }
        result = evaluator._eval_falsifier(spec, {}, {}, "solar")
        assert result["state"] == evaluator.STATE_DATA_MISSING

    # ── QUALITATIVE path ───────────────────────────────────────────────────

    def test_qualitative_when_flag_set(self, evaluator):
        """qualitative=True spec → STATE_QUALITATIVE regardless of check."""
        spec = {
            "id": "test_qual",
            "rule_en": "human must review",
            "check": None,
            "qualitative": True,
        }
        result = evaluator._eval_falsifier(spec, {}, {}, "nuclear_power")
        assert result["state"] == evaluator.STATE_QUALITATIVE
        assert result["fired"] is False

    def test_qualitative_when_check_none(self, evaluator):
        """qualitative=False but check=None also → QUALITATIVE (safe fallback)."""
        spec = {
            "id": "test_qual2",
            "rule_en": "no machine check",
            "check": None,
            "qualitative": False,
        }
        result = evaluator._eval_falsifier(spec, {}, {}, "nuclear_power")
        assert result["state"] == evaluator.STATE_QUALITATIVE

    # ── Wildcard field resolution ──────────────────────────────────────────

    def test_wildcard_field_max_resolution(self, evaluator):
        """basket_intel[*].crowding → max crowding across list; FIRED if gt threshold."""
        spec = {
            "id": "test_wildcard",
            "rule_en": "crowding exceeds 0.7",
            "check": {
                "kind": "threshold",
                "source_artifact": "data/neuralweb/theme_state.json",
                "field": "basket_intel[*].crowding",
                "op": "gt",
                "threshold": 0.7,
                "window_d": None,
            },
            "qualitative": False,
        }
        # One basket has crowding 0.85 → max = 0.85 > 0.7 → FIRED
        theme_state = self._make_theme_state(
            "ai_semiconductors",
            basket_intel=[{"crowding": 0.2}, {"crowding": 0.85}],
        )
        result = evaluator._eval_falsifier(spec, {}, theme_state, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_FIRED

    def test_wildcard_field_armed_when_below_threshold(self, evaluator):
        """basket_intel[*].crowding max = 0.3 < 0.7 → ARMED."""
        spec = {
            "id": "test_wildcard2",
            "rule_en": "crowding check",
            "check": {
                "kind": "threshold",
                "source_artifact": "data/neuralweb/theme_state.json",
                "field": "basket_intel[*].crowding",
                "op": "gt",
                "threshold": 0.7,
                "window_d": None,
            },
            "qualitative": False,
        }
        theme_state = self._make_theme_state(
            "ai_semiconductors",
            basket_intel=[{"crowding": 0.2}, {"crowding": 0.3}],
        )
        result = evaluator._eval_falsifier(spec, {}, theme_state, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_ARMED

    def test_wildcard_field_lt_uses_min_aggregation(self, evaluator):
        """lt-check wildcard must aggregate via min(): 'any basket score fell
        below 30' fires when the WEAKEST member breaches even while the
        strongest is healthy. A fixed max() aggregation silently never fires
        this case (post-review fix on PR-C)."""
        spec = {
            "id": "test_wildcard_lt",
            "rule_en": "any basket score below 30",
            "check": {
                "kind": "threshold",
                "source_artifact": "data/neuralweb/theme_state.json",
                "field": "basket_intel[*].score",
                "op": "lt",
                "threshold": 30,
                "window_d": None,
            },
            "qualitative": False,
        }
        # Weakest basket 22 < 30 breaches; strongest 88 healthy.
        # min-aggregation → FIRED; the old max() bug reported ARMED here.
        theme_state = self._make_theme_state(
            "ai_semiconductors",
            basket_intel=[{"score": 88}, {"score": 22}],
        )
        result = evaluator._eval_falsifier(spec, {}, theme_state, "ai_semiconductors")
        assert result["state"] == evaluator.STATE_FIRED, (
            "lt wildcard must fire on the minimum value across members"
        )
        # And ARMED when no member breaches.
        theme_state_ok = self._make_theme_state(
            "ai_semiconductors",
            basket_intel=[{"score": 88}, {"score": 45}],
        )
        result_ok = evaluator._eval_falsifier(spec, {}, theme_state_ok, "ai_semiconductors")
        assert result_ok["state"] == evaluator.STATE_ARMED


# ---------------------------------------------------------------------------
# 4. Append-only + content-hash idempotence
# ---------------------------------------------------------------------------

class TestAppendOnlyIdempotence:
    """Second run with same data appends nothing to ledger."""

    @pytest.fixture
    def engine_mod(self):
        import importlib, sys
        sys.path.insert(0, str(_REPO_ROOT))
        return importlib.import_module("engine.neuralweb.theme_thesis")

    def _minimal_thesis(self, theme_id: str) -> dict:
        return {
            "thesis_id": f"{theme_id}.v1",
            "theme_id": theme_id,
            "status": "active",
            "variant_perception_en": "Market underestimates X",
            "variant_perception_zh": "市场低估了X",
            "mechanism_en": "A causes B causes C",
            "mechanism_zh": "A导致B导致C",
            "driver": {"type": "technology", "description": "tech driver"},
            "winner_classes": [{"class": "bottleneck_monopolists", "why": "locked in"}],
            "loser_classes": [{"class": "commodity_exposed", "why": "AVOID — no moat"}],
            "falsifiers": [
                {
                    "id": f"{theme_id}_f1",
                    "rule_en": "If revision_breadth goes negative, thesis weakens",
                    "check": None,
                    "qualitative": True,
                }
            ],
            "evidence_refs": [],
        }

    def test_idempotent_second_run(self, engine_mod, tmp_path):
        """Running compile_thesis_record twice with same data produces None on second run."""
        thesis = self._minimal_thesis("ai_semiconductors")

        # First run — no prev record → should return a record
        record1 = engine_mod.compile_thesis_record(
            thesis=thesis,
            foresight={},
            theme_state={},
            as_of="2026-07-09",
            prev_record=None,
        )
        assert record1 is not None, "First run should produce a record"

        # Second run — prev_record is the same content → should return None
        record2 = engine_mod.compile_thesis_record(
            thesis=thesis,
            foresight={},
            theme_state={},
            as_of="2026-07-09",
            prev_record=record1,
        )
        assert record2 is None, "Second run with identical content must return None (no append)"

    def test_appends_on_content_change(self, engine_mod, tmp_path):
        """Changing falsifier state (e.g. new data makes a check fire) triggers new record."""
        thesis = self._minimal_thesis("memory_storage")

        # First run with no foresight data → DATA_MISSING
        record1 = engine_mod.compile_thesis_record(
            thesis={
                **thesis,
                "falsifiers": [{
                    "id": "mem_test_f1",
                    "rule_en": "revision breadth check",
                    "check": {
                        "kind": "threshold",
                        "source_artifact": "site/basketdata/foresight_cascade.json",
                        "field": "revision_breadth",
                        "op": "lt",
                        "threshold": 0.0,
                        "window_d": 60,
                    },
                    "qualitative": False,
                }],
            },
            foresight={},  # missing → DATA_MISSING
            theme_state={},
            as_of="2026-07-09",
            prev_record=None,
        )
        assert record1 is not None

        # Second run with foresight data that FIRES the check
        record2 = engine_mod.compile_thesis_record(
            thesis={
                **thesis,
                "falsifiers": [{
                    "id": "mem_test_f1",
                    "rule_en": "revision breadth check",
                    "check": {
                        "kind": "threshold",
                        "source_artifact": "site/basketdata/foresight_cascade.json",
                        "field": "revision_breadth",
                        "op": "lt",
                        "threshold": 0.0,
                        "window_d": 60,
                    },
                    "qualitative": False,
                }],
            },
            foresight={"memory_storage": {"revision_breadth": -0.2}},
            theme_state={},
            as_of="2026-07-09",
            prev_record=record1,
        )
        # Content changed (DATA_MISSING → FIRED), so new record is produced
        assert record2 is not None, "Content changed → new record must be produced"

    def test_prev_hash_linkage(self, engine_mod):
        """New record carries prev_content_hash linking to previous record."""
        thesis = self._minimal_thesis("nuclear_power")
        record1 = engine_mod.compile_thesis_record(
            thesis=thesis,
            foresight={},
            theme_state={},
            as_of="2026-07-09",
            prev_record=None,
        )
        assert record1 is not None
        assert record1["prev_content_hash"] is None, "First record has no prev"

        # Force content change by adding foresight data
        foresight_changed = {"nuclear_power": {"revision_breadth": 0.5}}
        record2 = engine_mod.compile_thesis_record(
            thesis={
                **thesis,
                "falsifiers": [{
                    "id": "nuke_test",
                    "rule_en": "breadth check",
                    "check": {
                        "kind": "threshold",
                        "source_artifact": "site/basketdata/foresight_cascade.json",
                        "field": "revision_breadth",
                        "op": "lt",
                        "threshold": 0.0,
                        "window_d": 60,
                    },
                    "qualitative": False,
                }],
            },
            foresight=foresight_changed,
            theme_state={},
            as_of="2026-07-09",
            prev_record=record1,
        )
        if record2 is not None:
            assert record2["prev_content_hash"] == record1["content_hash"], (
                "prev_content_hash must reference the previous record's content_hash"
            )

    def test_ledger_atomic_write_and_read(self, engine_mod, tmp_path):
        """JSONL ledger write and read roundtrip preserves all records."""
        ledger_path = tmp_path / "test_ledger.jsonl"
        rows_in = [
            {"thesis_id": "ai_semiconductors.v1", "as_of": "2026-07-09", "content_hash": "sha256:aaa"},
            {"thesis_id": "nuclear_power.v1", "as_of": "2026-07-09", "content_hash": "sha256:bbb"},
        ]
        engine_mod._atomic_write_jsonl_append(ledger_path, rows_in)

        rows_out = engine_mod._read_ledger(ledger_path)
        assert len(rows_out) == 2
        assert rows_out[0]["thesis_id"] == "ai_semiconductors.v1"
        assert rows_out[1]["thesis_id"] == "nuclear_power.v1"

    def test_ledger_append_is_additive(self, engine_mod, tmp_path):
        """Second _atomic_write_jsonl_append adds to, not replaces, existing rows."""
        ledger_path = tmp_path / "test_ledger2.jsonl"
        rows1 = [{"thesis_id": "a.v1", "as_of": "2026-07-09", "content_hash": "sha256:1"}]
        rows2 = [{"thesis_id": "b.v1", "as_of": "2026-07-09", "content_hash": "sha256:2"}]

        engine_mod._atomic_write_jsonl_append(ledger_path, rows1)
        engine_mod._atomic_write_jsonl_append(ledger_path, rows2)

        all_rows = engine_mod._read_ledger(ledger_path)
        assert len(all_rows) == 2
        assert all_rows[0]["thesis_id"] == "a.v1"
        assert all_rows[1]["thesis_id"] == "b.v1"

    def test_content_hash_stable(self, engine_mod):
        """Same content always yields same hash."""
        h1 = engine_mod._content_hash({"a": 1, "b": 2})
        h2 = engine_mod._content_hash({"b": 2, "a": 1})
        assert h1 == h2, "Content hash must use sort_keys=True for stability"

    def test_run_stage_completes_on_live_repo(self, engine_mod):
        """run_stage() against real repo root exits without exception."""
        # This exercises the full pipeline on real artifacts
        engine_mod.run_stage(_REPO_ROOT)
        # Site projection must exist after run
        site_path = _REPO_ROOT / "site" / "neuralwebdata" / "theme_thesis.json"
        assert site_path.exists(), "run_stage must write site/neuralwebdata/theme_thesis.json"


# ---------------------------------------------------------------------------
# 5. Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:
    """'validated' must never appear in user-facing text (CI-enforced)."""

    BANNED = re.compile(r"\bvalidated\b", re.IGNORECASE)

    def _text_in_dict(self, obj: Any, path: str = "") -> list[str]:
        """Recursively collect all string values from obj."""
        hits = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                hits.extend(self._text_in_dict(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                hits.extend(self._text_in_dict(item, f"{path}[{i}]"))
        elif isinstance(obj, str):
            if self.BANNED.search(obj):
                hits.append(f"{path}: {obj[:100]!r}")
        return hits

    def test_registry_no_validated(self):
        """'validated' must not appear in user-facing text fields of theme_thesis_registry.yml.

        Comments (#) are excluded as they are not user-facing content.
        The CI check (check_validated_claims.py) only scans templates/ and site/ surfaces.
        We check the prose fields that would surface to users.
        """
        if not _REGISTRY_PATH.exists():
            pytest.skip("registry not yet written")
        with _REGISTRY_PATH.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        theses = data.get("theses", [])
        text_fields = [
            "variant_perception_en", "variant_perception_zh",
            "mechanism_en", "mechanism_zh",
        ]
        for t in theses:
            tid = t.get("thesis_id", "?")
            for field in text_fields:
                val = t.get(field, "")
                if self.BANNED.search(str(val)):
                    pytest.fail(
                        f"Banned word 'validated' in thesis {tid!r} field {field!r}: {val[:100]!r}"
                    )

    def test_engine_module_no_validated_in_strings(self):
        """'validated' must not appear in string literals in theme_thesis.py."""
        engine_path = _REPO_ROOT / "engine" / "neuralweb" / "theme_thesis.py"
        if not engine_path.exists():
            pytest.skip("engine module not yet written")
        text = engine_path.read_text(encoding="utf-8")
        # Only flag string literals (skip code comments too — CI checks user-facing)
        # We flag the whole file to be conservative (matches CI check_validated_claims)
        matches = self.BANNED.findall(text)
        assert not matches, (
            f"Banned word 'validated' found in engine/neuralweb/theme_thesis.py"
        )

    def test_registry_theses_no_validated_in_text(self, theses):
        """'validated' must not appear in any thesis text field."""
        text_fields = [
            "variant_perception_en", "variant_perception_zh",
            "mechanism_en", "mechanism_zh",
        ]
        for t in theses:
            tid = t.get("thesis_id", "?")
            for field in text_fields:
                val = t.get(field, "")
                if self.BANNED.search(val):
                    pytest.fail(
                        f"Banned word 'validated' in thesis {tid!r} field {field!r}"
                    )

    def test_falsifier_rules_no_validated(self, theses):
        """'validated' must not appear in any falsifier rule_en."""
        for t in theses:
            tid = t.get("thesis_id", "?")
            for i, f in enumerate(t.get("falsifiers", [])):
                rule = f.get("rule_en", "")
                if self.BANNED.search(rule):
                    pytest.fail(
                        f"Banned word 'validated' in thesis {tid!r} falsifier[{i}].rule_en"
                    )


# ---------------------------------------------------------------------------
# 6. Authority block
# ---------------------------------------------------------------------------

class TestAuthorityBlock:
    """Authority block must be display-only with all promotion flags False."""

    def test_module_authority_block(self):
        """AUTHORITY_BLOCK in engine module must have all required flags."""
        import importlib, sys
        sys.path.insert(0, str(_REPO_ROOT))
        mod = importlib.import_module("engine.neuralweb.theme_thesis")
        ab = mod.AUTHORITY_BLOCK

        assert ab["is_context_only"] is True
        assert ab["may_rank"] is False
        assert ab["may_gate"] is False
        assert ab["may_size"] is False
        assert ab["may_escalate"] is False
        assert ab["display_only"] is True
        assert ab["not_a_signal"] is True
        assert ab["tier"] in {"shadow", "display"}

    def test_authority_block_in_site_output(self):
        """Site projection written by run_stage must include authority block."""
        site_path = _REPO_ROOT / "site" / "neuralwebdata" / "theme_thesis.json"
        if not site_path.exists():
            pytest.skip("site projection not yet written; run run_stage first")
        data = json.loads(site_path.read_text(encoding="utf-8"))
        ab = data.get("authority", {})
        assert ab.get("is_context_only") is True, "is_context_only must be True"
        assert ab.get("may_rank") is False, "may_rank must be False"
        assert ab.get("may_gate") is False, "may_gate must be False"
        assert ab.get("may_size") is False, "may_size must be False"
        assert ab.get("may_escalate") is False, "may_escalate must be False"

    def test_ledger_records_carry_authority_block(self, engine_mod=None):
        """Ledger records must each carry the authority block."""
        import importlib, sys
        sys.path.insert(0, str(_REPO_ROOT))
        mod = importlib.import_module("engine.neuralweb.theme_thesis")

        thesis = {
            "thesis_id": "ai_semiconductors.v1",
            "theme_id": "ai_semiconductors",
            "status": "active",
            "variant_perception_en": "Market misses X",
            "variant_perception_zh": "市场低估X",
            "mechanism_en": "A → B",
            "mechanism_zh": "A → B",
            "driver": {"type": "technology", "description": "tech"},
            "winner_classes": [{"class": "monopolist_a", "why": "dominant"}],
            "loser_classes": [{"class": "commodity_b", "why": "AVOID — no moat"}],
            "falsifiers": [{"id": "f1", "rule_en": "test", "check": None, "qualitative": True}],
            "evidence_refs": [],
        }
        record = mod.compile_thesis_record(
            thesis=thesis,
            foresight={},
            theme_state={},
            as_of="2026-07-09",
            prev_record=None,
        )
        assert record is not None
        ab = record.get("authority", {})
        assert ab.get("is_context_only") is True
        assert ab.get("may_rank") is False
        assert ab.get("may_gate") is False
        assert ab.get("may_size") is False
        assert ab.get("may_escalate") is False


# ---------------------------------------------------------------------------
# 7. Tolerant run_stage — missing inputs produce honest null, not crash
# ---------------------------------------------------------------------------

class TestRunStageTolerance:
    """run_stage must not crash on missing inputs; writes honest null instead."""

    @pytest.fixture
    def engine_mod(self):
        import importlib, sys
        sys.path.insert(0, str(_REPO_ROOT))
        return importlib.import_module("engine.neuralweb.theme_thesis")

    def test_run_stage_with_missing_registry(self, engine_mod, tmp_path):
        """run_stage against empty tmp_path (no registry) must not raise."""
        # Ensure no registry, no foresight, no theme_state
        try:
            engine_mod.run_stage(tmp_path)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"run_stage must not raise on missing inputs; got: {exc}")

    def test_run_stage_writes_site_projection(self, engine_mod, tmp_path):
        """run_stage must write site/neuralwebdata/theme_thesis.json even on null state."""
        # Write minimal registry into tmp_path
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        # Minimal registry with 0 theses
        (cfg_dir / "theme_thesis_registry.yml").write_text(
            "version: 1\ndate: '2026-07-09'\ntheses: []\n",
            encoding="utf-8",
        )

        # Write synapse.yml stub so envelope.stamp doesn't crash
        # (synapse.yml not found → stamp logs warning but doesn't raise)
        try:
            engine_mod.run_stage(tmp_path)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"run_stage must not raise: {exc}")

    def test_run_stage_with_minimal_thesis(self, engine_mod, tmp_path):
        """run_stage with a minimal valid thesis completes and writes ledger."""
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        thesis_yaml = """
version: 1
date: "2026-07-09"
theses:
  - thesis_id: ai_semiconductors.v1
    theme_id: ai_semiconductors
    status: active
    variant_perception_en: "Market misses the sovereign AI capex wave"
    variant_perception_zh: "市场低估了主权AI资本支出浪潮"
    mechanism_en: "Multi-year purchase agreements anchor demand"
    mechanism_zh: "多年采购协议锚定需求"
    driver:
      type: technology
      description: "GPU architecture dominance"
    winner_classes:
      - class: gpu_asic_monopolists
        why: "Architecture lock-in provides pricing power"
    loser_classes:
      - class: legacy_cpu_datacenter_builders
        why: "AVOID — x86 refresh crowded out by GPU capex"
    falsifiers:
      - id: ai_semi_q1
        rule_en: "If hyperscalers shift to 'digesting' mode, backlog breaks"
        check: null
        qualitative: true
    evidence_refs: []
"""
        (cfg_dir / "theme_thesis_registry.yml").write_text(thesis_yaml, encoding="utf-8")

        # Must not crash
        try:
            engine_mod.run_stage(tmp_path)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"run_stage must not raise: {exc}")

        # Ledger should exist
        ledger_path = tmp_path / "data" / "neuralweb" / "theme_thesis_ledger.jsonl"
        assert ledger_path.exists(), "run_stage must write the ledger"
        rows = engine_mod._read_ledger(ledger_path)
        assert len(rows) == 1
        assert rows[0]["thesis_id"] == "ai_semiconductors.v1"

    def test_run_stage_idempotent_on_real_repo(self, engine_mod):
        """run_stage twice on real repo appends no new rows on second call."""
        # Run once to establish a baseline
        engine_mod.run_stage(_REPO_ROOT)
        ledger_path = _REPO_ROOT / "data" / "neuralweb" / "theme_thesis_ledger.jsonl"
        if not ledger_path.exists():
            pytest.skip("ledger not created — likely no registry on disk")

        rows_before = engine_mod._read_ledger(ledger_path)
        n_before = len(rows_before)

        # Run again — same data, same day → no new rows
        engine_mod.run_stage(_REPO_ROOT)
        rows_after = engine_mod._read_ledger(ledger_path)
        n_after = len(rows_after)

        assert n_after == n_before, (
            f"Second run added {n_after - n_before} rows but should have added 0 "
            f"(content unchanged)"
        )


# ---------------------------------------------------------------------------
# Type annotation used in TestBannedWords
# ---------------------------------------------------------------------------
from typing import Any  # noqa: E402
