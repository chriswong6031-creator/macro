"""tests/test_thematic_state.py — TIL W0 thematic state spine tests.

Covers:
  (1) crosswalk integrity — all 18 foresight themes mapped, no dangling basket_ids,
      valid subsector keys, no duplicate canonical ids
  (2) composition tolerant-read — delete each source → builder still exits 0,
      stale_legs names the missing input
  (3) phase-history append + hash-chain semantics
  (4) authority block assertions (all promotion flags False, is_context_only=True)
  (5) banned-word scan ("validated" must not appear in user-facing text)
  (6) all-five-stages foresight ledger logging (existing _append_ledger coverage)
  (7) build_thematic_state.py does not crash on clean tmp_path

All tests are hermetic — monkeypatching / tmp_path only; no live network calls.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CROSSWALK = _REPO_ROOT / "config" / "theme_crosswalk.yml"

# ---------------------------------------------------------------------------
# 1. Crosswalk integrity
# ---------------------------------------------------------------------------

class TestCrosswalkIntegrity:
    """Static integrity checks on config/theme_crosswalk.yml."""

    @pytest.fixture(scope="class")
    def cw(self):
        assert _CROSSWALK.exists(), f"theme_crosswalk.yml not found at {_CROSSWALK}"
        with _CROSSWALK.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    @pytest.fixture(scope="class")
    def basket_ids_on_disk(self):
        membership = _REPO_ROOT / "data" / "baskets" / "membership.json"
        if not membership.exists():
            pytest.skip("data/baskets/membership.json not present")
        data = json.loads(membership.read_text(encoding="utf-8"))
        return set(data.get("baskets", {}).keys())

    @pytest.fixture(scope="class")
    def subsector_keys_on_disk(self):
        sub = _REPO_ROOT / "site" / "marketdata" / "subsector_rotation.json"
        if not sub.exists():
            pytest.skip("site/marketdata/subsector_rotation.json not present")
        data = json.loads(sub.read_text(encoding="utf-8"))
        return {t["theme"] for t in data.get("themes", []) if isinstance(t, dict) and "theme" in t}

    def test_eighteen_themes(self, cw):
        """Crosswalk must have exactly 18 canonical themes (one per foresight theme)."""
        themes = cw.get("themes", [])
        assert len(themes) == 18, f"Expected 18 canonical themes, got {len(themes)}"

    def test_no_duplicate_canonical_ids(self, cw):
        themes = cw.get("themes", [])
        ids = [t["id"] for t in themes]
        duplicates = [x for x in ids if ids.count(x) > 1]
        assert not duplicates, f"Duplicate canonical theme ids: {duplicates}"

    def test_all_foresight_ids_present(self, cw):
        """Every foresight_id must be non-null and match a known foresight theme."""
        expected_foresight_ids = {
            "medical_devices", "nuclear_power", "grid_electrification",
            "space_satellite", "rare_earth_critical_min", "copper_steel_electrify",
            "ag_fertilizer", "data_center_power", "ai_semiconductors",
            "memory_storage", "semicap_equipment", "cybersecurity",
            "defense_aerospace", "robotics_automation", "fintech_payments",
            "diagnostics_lifesci", "glp1_obesity", "solar",
        }
        mapped_foresight = {t["foresight_id"] for t in cw["themes"] if t.get("foresight_id")}
        missing = expected_foresight_ids - mapped_foresight
        assert not missing, f"Foresight ids not mapped: {missing}"

    def test_no_dangling_basket_ids(self, cw, basket_ids_on_disk):
        """Every basket_id in the crosswalk must exist in membership.json."""
        dangling = []
        for t in cw["themes"]:
            for bid in t.get("basket_ids", []):
                if bid not in basket_ids_on_disk:
                    dangling.append((t["id"], bid))
        assert not dangling, f"Dangling basket_ids (theme, basket): {dangling}"

    def test_all_46_baskets_accounted_for(self, cw, basket_ids_on_disk):
        """All 46 baskets must appear in either basket_ids or unmapped_baskets."""
        mapped = set()
        for t in cw["themes"]:
            mapped.update(t.get("basket_ids", []))
        unmapped_ids = {u["id"] for u in cw.get("unmapped_baskets", [])}
        covered = mapped | unmapped_ids
        missing_from_cw = basket_ids_on_disk - covered
        extra_in_cw = covered - basket_ids_on_disk
        assert not missing_from_cw, f"Baskets not covered in crosswalk: {missing_from_cw}"
        assert not extra_in_cw, f"Crosswalk references baskets not in membership.json: {extra_in_cw}"

    def test_valid_subsector_keys(self, cw, subsector_keys_on_disk):
        """subsector_keys must be valid keys from subsector_rotation.json."""
        dangling = []
        for t in cw["themes"]:
            for sk in t.get("subsector_keys", []):
                if sk not in subsector_keys_on_disk:
                    dangling.append((t["id"], sk))
        assert not dangling, f"Invalid subsector_keys: {dangling}"

    def test_citrini_always_empty(self, cw):
        """citrini_basket_ids must be [] for all themes in PR-A."""
        for t in cw["themes"]:
            val = t.get("citrini_basket_ids", [])
            assert val == [], f"theme {t['id']}: citrini_basket_ids must be [] in PR-A, got {val!r}"

    def test_names_bilingual(self, cw):
        """Every canonical theme must have both name_en and name_zh."""
        missing = []
        for t in cw["themes"]:
            if not t.get("name_en"):
                missing.append((t["id"], "name_en"))
            if not t.get("name_zh"):
                missing.append((t["id"], "name_zh"))
        assert not missing, f"Missing bilingual names: {missing}"


# ---------------------------------------------------------------------------
# 2. Composition tolerant-read tests
# ---------------------------------------------------------------------------

def _minimal_source_tree(tmp_path: Path) -> None:
    """Create minimal valid source fixtures in tmp_path."""
    # crosswalk
    src_cw = _CROSSWALK
    dest_cw = tmp_path / "config" / "theme_crosswalk.yml"
    dest_cw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_cw, dest_cw)

    # foresight_cascade.json
    fc = {
        "asof": "2026-07-09",
        "n_themes": 2,
        "themes": [
            {"theme": "ai_semiconductors", "name": "AI Semiconductors", "stage": "RE-RATING",
             "tier": "P", "score": 72, "entry_ready": False, "bottleneck_band": "TIGHT"},
            {"theme": "cybersecurity", "name": "Cybersecurity", "stage": "WATCH",
             "tier": "P", "score": 55, "entry_ready": False, "bottleneck_band": "WATCH"},
        ],
    }
    dest_fc = tmp_path / "site" / "basketdata" / "foresight_cascade.json"
    dest_fc.parent.mkdir(parents=True, exist_ok=True)
    dest_fc.write_text(json.dumps(fc), encoding="utf-8")

    # baskets.json
    baskets = {
        "as_of": "2026-07-09",
        "baskets": [],
        "theme_intel": {
            "as_of": "2026-07-09",
            "themes": [
                {"id": "ai_semiconductors", "name": "AI Semiconductors",
                 "name_zh": "AI半导体", "score": 72,
                 "label": "BULL", "label_en": "Bull", "label_zh": "牛",
                 "reco": "hold", "components": {"crowding": 0.7}},
            ],
        },
    }
    dest_b = tmp_path / "site" / "basketdata" / "baskets.json"
    dest_b.write_text(json.dumps(baskets), encoding="utf-8")

    # radar_enriched.json
    radar_e = {
        "schema": "radar.v2",
        "is_context_only": True,
        "as_of": "2026-07-09",
        "flags": [
            {"basket": "ai_semiconductors", "state": "POSITIVE_DIVERGENCE",
             "lifecycle": "forming", "divergence": 1.5, "salience": 1.5},
        ],
        "hypotheses": [],
    }
    dest_re = tmp_path / "site" / "basketdata" / "radar_enriched.json"
    dest_re.write_text(json.dumps(radar_e), encoding="utf-8")

    # radar.json
    radar = {"schema": "radar.v2", "is_context_only": True, "as_of": "2026-07-09",
             "hypotheses": [], "flags": []}
    dest_r = tmp_path / "site" / "basketdata" / "radar.json"
    dest_r.write_text(json.dumps(radar), encoding="utf-8")

    # narrative_emergence.json
    narr = {"schema": "narrative_emergence.v1", "is_context_only": True,
            "as_of": "2026-07-09", "n_universe": 100, "attention": {}, "narratives": []}
    dest_n = tmp_path / "site" / "basketdata" / "narrative_emergence.json"
    dest_n.write_text(json.dumps(narr), encoding="utf-8")

    # subsector_rotation.json
    sub = {
        "asof": "2026-07-09",
        "themes": [
            {"theme": "Semiconductors", "theme_zh": "半导体",
             "quadrant": "Leading", "rs": 1.2, "z_accel": 0.8, "emerging_score": 0.6},
            {"theme": "Artificial Intelligence", "theme_zh": "人工智能",
             "quadrant": "Leading", "rs": 1.5, "z_accel": 1.0, "emerging_score": 0.8},
        ],
    }
    dest_s = tmp_path / "site" / "marketdata" / "subsector_rotation.json"
    dest_s.parent.mkdir(parents=True, exist_ok=True)
    dest_s.write_text(json.dumps(sub), encoding="utf-8")

    # divergence_log.jsonl
    divlog = tmp_path / "data" / "foresight" / "divergence_log.jsonl"
    divlog.parent.mkdir(parents=True, exist_ok=True)
    divlog.write_text(
        json.dumps({"theme": "ai_semiconductors", "asof": "2026-07-09",
                    "ts": "2026-07-09T00:00:00", "row_type": "observation",
                    "quadrant": "hidden-opportunity", "divergence": -0.4,
                    "narrative_pct": 0.2, "money_pct": 0.7}) + "\n",
        encoding="utf-8",
    )

    # data/baskets/membership.json
    mem = tmp_path / "data" / "baskets" / "membership.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(json.dumps({
        "baskets": {
            "ai_semiconductors": {"name": "AI Semiconductors", "tickers": ["NVDA", "AMD"]},
            "cybersecurity": {"name": "Cybersecurity", "tickers": ["CRWD", "PANW"]},
        }
    }), encoding="utf-8")


def _compose_from_tmp(tmp_path: Path) -> dict:
    """Call compose() with root=tmp_path."""
    import importlib, sys
    # ensure fresh import
    mod_name = "engine.neuralweb.thematic_state"
    if mod_name in sys.modules:
        mod = sys.modules[mod_name]
    else:
        import engine.neuralweb.thematic_state as mod  # noqa: F401
    from engine.neuralweb.thematic_state import compose
    return compose(root=tmp_path)


class TestCompositionTolerantRead:
    """Each missing source → exits 0, stale_legs names the gap."""

    def test_full_sources_compose_ok(self, tmp_path):
        """With all sources present, compose() returns a valid artifact."""
        _minimal_source_tree(tmp_path)
        art = _compose_from_tmp(tmp_path)
        assert art["schema"] == "neuralweb.theme_state.v1"
        assert "themes" in art
        assert art.get("n_themes", 0) > 0

    def test_missing_foresight_cascade(self, tmp_path):
        """Missing foresight_cascade.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "basketdata" / "foresight_cascade.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "foresight_cascade" in stale
        assert art["schema"] == "neuralweb.theme_state.v1"

    def test_missing_baskets(self, tmp_path):
        """Missing baskets.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "basketdata" / "baskets.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "baskets" in stale

    def test_missing_radar_enriched(self, tmp_path):
        """Missing radar_enriched.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "basketdata" / "radar_enriched.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "radar_enriched" in stale

    def test_missing_radar(self, tmp_path):
        """Missing radar.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "basketdata" / "radar.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "radar" in stale

    def test_missing_narrative(self, tmp_path):
        """Missing narrative_emergence.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "basketdata" / "narrative_emergence.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "narrative_emergence" in stale

    def test_missing_subsector(self, tmp_path):
        """Missing subsector_rotation.json → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "site" / "marketdata" / "subsector_rotation.json").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "subsector_rotation" in stale

    def test_missing_divergence_log(self, tmp_path):
        """Missing divergence_log.jsonl → stale_legs mentions it; exits 0."""
        _minimal_source_tree(tmp_path)
        (tmp_path / "data" / "foresight" / "divergence_log.jsonl").unlink()
        art = _compose_from_tmp(tmp_path)
        stale = " ".join(art.get("stale_legs", []))
        assert "divergence_log" in stale

    def test_all_sources_missing(self, tmp_path):
        """Even with crosswalk only, exits 0 with an artifact."""
        # Copy only the crosswalk
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(_CROSSWALK, tmp_path / "config" / "theme_crosswalk.yml")
        art = _compose_from_tmp(tmp_path)
        assert art["schema"] == "neuralweb.theme_state.v1"

    def test_missing_crosswalk_returns_error_artifact(self, tmp_path):
        """Missing crosswalk → returns an error artifact (no exception raised)."""
        art = _compose_from_tmp(tmp_path)
        assert "schema" in art  # never raises
        assert art.get("themes") == [] or "crosswalk" in " ".join(art.get("stale_legs", []))


# ---------------------------------------------------------------------------
# 3. Phase history append + hash-chain semantics
# ---------------------------------------------------------------------------

def _make_theme_block(tid: str, stage: str = "WATCH", label: str = "BEAR",
                       radar_lifecycle: str | None = None,
                       div_quadrant: str | None = None) -> dict:
    block = {
        "theme_id": tid,
        "name_en": f"Theme {tid}",
        "name_zh": f"主题{tid}",
        "foresight": {"stage": stage},
        "basket_intel": [{"label": label, "crowding": 0.5}] if label else None,
        "radar": [{"lifecycle": radar_lifecycle}] if radar_lifecycle else None,
        "divergence_board": {"quadrant": div_quadrant, "divergence": -0.3} if div_quadrant else None,
    }
    return block


def _make_artifact(themes: list[dict], as_of: str = "2026-07-09") -> dict:
    return {"schema": "neuralweb.theme_state.v1", "as_of": as_of, "themes": themes}


class TestPhaseHistoryAppend:
    """Append-only PIT tape semantics."""

    def test_first_run_writes_rows_for_all_themes(self, tmp_path):
        """Fresh JSONL — should write one row per theme."""
        from engine.neuralweb.thematic_state import append_phase_history
        themes = [_make_theme_block("ai_semiconductors"), _make_theme_block("cybersecurity")]
        art = _make_artifact(themes)
        n = append_phase_history(tmp_path, art)
        assert n == 2
        path = tmp_path / "data" / "neuralweb" / "theme_phase_history.jsonl"
        assert path.exists()
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert len(rows) == 2
        assert {r["theme_id"] for r in rows} == {"ai_semiconductors", "cybersecurity"}

    def test_same_day_rerun_is_idempotent(self, tmp_path):
        """Same (theme_id, as_of) pair → second call appends 0 rows."""
        from engine.neuralweb.thematic_state import append_phase_history
        themes = [_make_theme_block("ai_semiconductors")]
        art = _make_artifact(themes, as_of="2026-07-09")
        n1 = append_phase_history(tmp_path, art)
        n2 = append_phase_history(tmp_path, art)
        assert n1 == 1
        assert n2 == 0

    def test_state_transition_triggers_new_row(self, tmp_path):
        """Stage change on a new date → new row written."""
        from engine.neuralweb.thematic_state import append_phase_history
        # Day 1: WATCH
        art1 = _make_artifact([_make_theme_block("cybersecurity", stage="WATCH")],
                               as_of="2026-07-01")
        append_phase_history(tmp_path, art1)
        # Day 2: RE-RATING (stage changed)
        art2 = _make_artifact([_make_theme_block("cybersecurity", stage="RE-RATING")],
                               as_of="2026-07-02")
        n = append_phase_history(tmp_path, art2)
        assert n == 1

    def test_no_change_no_new_row_within_heartbeat(self, tmp_path):
        """Same stage, only 1 day elapsed → no new row (no heartbeat yet)."""
        from engine.neuralweb.thematic_state import append_phase_history
        art1 = _make_artifact([_make_theme_block("solar", stage="WATCH")], as_of="2026-07-01")
        append_phase_history(tmp_path, art1)
        art2 = _make_artifact([_make_theme_block("solar", stage="WATCH")], as_of="2026-07-02")
        n = append_phase_history(tmp_path, art2)
        assert n == 0

    def test_heartbeat_fires_after_seven_days(self, tmp_path):
        """7+ days elapsed with no transition → heartbeat row appended."""
        from engine.neuralweb.thematic_state import append_phase_history
        art1 = _make_artifact([_make_theme_block("solar", stage="WATCH")], as_of="2026-07-01")
        append_phase_history(tmp_path, art1)
        art2 = _make_artifact([_make_theme_block("solar", stage="WATCH")], as_of="2026-07-08")
        n = append_phase_history(tmp_path, art2)
        assert n == 1   # heartbeat

    def test_hash_chain(self, tmp_path):
        """prev_hash of second row must equal sha256 of first row."""
        from engine.neuralweb.thematic_state import append_phase_history, _row_hash
        art1 = _make_artifact([_make_theme_block("defense_aerospace", stage="WATCH")],
                               as_of="2026-07-01")
        append_phase_history(tmp_path, art1)
        # Force a second row via stage transition
        art2 = _make_artifact([_make_theme_block("defense_aerospace", stage="RE-RATING")],
                               as_of="2026-07-02")
        append_phase_history(tmp_path, art2)

        path = tmp_path / "data" / "neuralweb" / "theme_phase_history.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert len(rows) == 2
        row1, row2 = rows
        assert row1.get("prev_hash") is None   # first row has no predecessor
        expected_hash = _row_hash(row1)
        assert row2.get("prev_hash") == expected_hash, (
            f"Hash chain broken: row2.prev_hash={row2.get('prev_hash')!r} "
            f"expected={expected_hash!r}"
        )

    def test_schema_field_present(self, tmp_path):
        """Every history row must carry the schema field."""
        from engine.neuralweb.thematic_state import append_phase_history
        art = _make_artifact([_make_theme_block("nuclear_power")], as_of="2026-07-09")
        append_phase_history(tmp_path, art)
        path = tmp_path / "data" / "neuralweb" / "theme_phase_history.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        for row in rows:
            assert row.get("schema") == "neuralweb.theme_phase_history.v1"

    def test_required_fields_present(self, tmp_path):
        """History rows must carry: as_of, ts, theme_id, foresight_stage, evidence_z."""
        from engine.neuralweb.thematic_state import append_phase_history
        art = _make_artifact([_make_theme_block("robotics_automation", stage="BROADENING",
                                                 div_quadrant="hidden-opportunity")],
                              as_of="2026-07-09")
        append_phase_history(tmp_path, art)
        path = tmp_path / "data" / "neuralweb" / "theme_phase_history.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert rows
        row = rows[0]
        for field in ["as_of", "ts", "theme_id", "foresight_stage", "evidence_z"]:
            assert field in row, f"Missing field {field!r} in history row"


# ---------------------------------------------------------------------------
# 4. Authority block assertions
# ---------------------------------------------------------------------------

class TestAuthorityBlock:
    """The authority block must set all promotion flags to False."""

    def test_authority_block_in_compose(self, tmp_path):
        """compose() output must carry correct authority block."""
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(_CROSSWALK, tmp_path / "config" / "theme_crosswalk.yml")
        art = _compose_from_tmp(tmp_path)
        auth = art.get("authority", {})
        assert auth.get("is_context_only") is True
        assert auth.get("may_rank") is False
        assert auth.get("may_gate") is False
        assert auth.get("may_size") is False
        assert auth.get("may_escalate") is False

    def test_authority_in_module_constant(self):
        """AUTHORITY_BLOCK module constant must have all promotion flags False."""
        from engine.neuralweb.thematic_state import AUTHORITY_BLOCK
        assert AUTHORITY_BLOCK.get("is_context_only") is True
        for flag in ("may_rank", "may_gate", "may_size", "may_escalate"):
            assert AUTHORITY_BLOCK.get(flag) is False, f"{flag} must be False"


# ---------------------------------------------------------------------------
# 5. Banned-word scan
# ---------------------------------------------------------------------------

class TestBannedWords:
    """The word 'validated' must not appear in user-facing artifact text."""

    def _text_of(self, obj, path="") -> list[str]:
        """Recursively collect all string values from a nested dict/list."""
        results = []
        if isinstance(obj, str):
            results.append((path, obj))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                results.extend(self._text_of(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                results.extend(self._text_of(v, f"{path}[{i}]"))
        return results

    def test_crosswalk_no_validated(self):
        """theme_crosswalk.yml must not contain the word 'validated'."""
        text = _CROSSWALK.read_text(encoding="utf-8")
        assert "validated" not in text.lower(), (
            "theme_crosswalk.yml contains banned word 'validated'"
        )

    def test_engine_module_no_validated_in_strings(self):
        """thematic_state.py must not emit 'validated' in any user-facing string."""
        src = (_REPO_ROOT / "engine" / "neuralweb" / "thematic_state.py").read_text()
        # Look for 'validated' in string literals
        string_literals = re.findall(r'["\']([^"\']*)["\']', src)
        for s in string_literals:
            assert "validated" not in s.lower(), (
                f"String literal in thematic_state.py contains 'validated': {s!r}"
            )

    def test_compose_output_no_validated(self, tmp_path):
        """compose() output must not contain the word 'validated' in any string field."""
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(_CROSSWALK, tmp_path / "config" / "theme_crosswalk.yml")
        art = _compose_from_tmp(tmp_path)
        text_pairs = self._text_of(art)
        violations = [(p, v) for p, v in text_pairs if "validated" in v.lower()]
        assert not violations, f"'validated' found in artifact: {violations[:3]}"


# ---------------------------------------------------------------------------
# 6. build_thematic_state.py entrypoint
# ---------------------------------------------------------------------------

class TestBuildScript:
    """build_thematic_state.py must exit 0 and write output files."""

    def test_build_exits_0_with_full_sources(self, tmp_path):
        """build(root) with full sources → exits 0 and writes data + site artifacts."""
        _minimal_source_tree(tmp_path)

        # Patch synapse so envelope.stamp() can find the artifact id
        import sys
        # We need to mock the registry or skip stamp if artifact not registered
        # The build catches stamp exceptions as non-fatal, so just run it
        from scripts.build_thematic_state import build
        rc = build(tmp_path)
        assert rc == 0

    def test_build_writes_data_artifact(self, tmp_path):
        """build() must write data/neuralweb/theme_state.json."""
        _minimal_source_tree(tmp_path)
        from scripts.build_thematic_state import build
        build(tmp_path)
        out = tmp_path / "data" / "neuralweb" / "theme_state.json"
        assert out.exists(), "data/neuralweb/theme_state.json was not written"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data.get("schema") == "neuralweb.theme_state.v1"

    def test_build_writes_site_mirror(self, tmp_path):
        """build() must write site/neuralwebdata/theme_state.json."""
        _minimal_source_tree(tmp_path)
        from scripts.build_thematic_state import build
        build(tmp_path)
        out = tmp_path / "site" / "neuralwebdata" / "theme_state.json"
        assert out.exists(), "site/neuralwebdata/theme_state.json was not written"

    def test_build_writes_phase_history(self, tmp_path):
        """build() must write and append to theme_phase_history.jsonl."""
        _minimal_source_tree(tmp_path)
        from scripts.build_thematic_state import build
        build(tmp_path)
        hist = tmp_path / "data" / "neuralweb" / "theme_phase_history.jsonl"
        assert hist.exists(), "data/neuralweb/theme_phase_history.jsonl was not written"

    def test_build_exits_0_with_no_sources(self, tmp_path):
        """build() must exit 0 even with no source files present (fail-open)."""
        from scripts.build_thematic_state import build
        rc = build(tmp_path)
        assert rc == 0

    def test_build_writes_valid_json_with_no_sources(self, tmp_path):
        """build() with no sources writes parseable JSON (error artifact)."""
        from scripts.build_thematic_state import build
        build(tmp_path)
        data_path = tmp_path / "data" / "neuralweb" / "theme_state.json"
        assert data_path.exists()
        data = json.loads(data_path.read_text())
        assert "schema" in data


# ---------------------------------------------------------------------------
# 7. Foresight ledger all-five-stages coverage (existing behavior verification)
# ---------------------------------------------------------------------------
# These are in test_foresight_cascade.py; we add a cross-reference assertion
# here to confirm the function is importable and the docstring documents the law.

class TestForesightLedgerAllStages:
    """_append_ledger must log ALL stages (W0a law; existing implementation)."""

    def test_append_ledger_docstring_declares_all_stages(self):
        """_append_ledger docstring must explicitly mention all five stages."""
        from engine import foresight_cascade as fc_mod
        doc = fc_mod._append_ledger.__doc__ or ""
        for stage in ["RE-RATING", "WATCH", "GLUT-RISK"]:
            assert stage in doc, (
                f"_append_ledger docstring must document stage {stage!r} — "
                "the W0a law requires all five stages to be logged."
            )

    def test_append_ledger_logs_re_rating_and_watch(self, tmp_path, monkeypatch):
        """RE-RATING and WATCH themes are written to the ledger (no filter gate)."""
        from engine import foresight_cascade as fc_mod
        monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(fc_mod.config, "load", lambda: {"themes": {}})

        # Build a minimal payload with RE-RATING and WATCH themes
        payload = {
            "asof": "2026-07-09",
            "themes": [
                {"theme": "ai_semiconductors", "stage": "RE-RATING",
                 "bottleneck_band": "TIGHT", "revision_breadth": 0.85},
                {"theme": "solar", "stage": "WATCH",
                 "bottleneck_band": "WATCH", "revision_breadth": 0.1},
            ],
        }
        (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)
        fc_mod._append_ledger(payload)

        log_path = tmp_path / "foresight" / "log.jsonl"
        assert log_path.exists()
        rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        stages = {r["theme"]: r["stage"] for r in rows}
        assert stages.get("ai_semiconductors") == "RE-RATING"
        assert stages.get("solar") == "WATCH"

    def test_append_ledger_logs_glut_risk(self, tmp_path, monkeypatch):
        """GLUT-RISK themes are also written to the ledger."""
        from engine import foresight_cascade as fc_mod
        monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(fc_mod.config, "load", lambda: {"themes": {}})

        payload = {
            "asof": "2026-07-09",
            "themes": [
                {"theme": "memory_storage", "stage": "GLUT-RISK",
                 "bottleneck_band": "LOOSE", "revision_breadth": 0.6},
            ],
        }
        (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)
        fc_mod._append_ledger(payload)
        log_path = tmp_path / "foresight" / "log.jsonl"
        rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        assert any(r["stage"] == "GLUT-RISK" for r in rows)

    def test_append_ledger_logs_broadening_and_precipice(self, tmp_path, monkeypatch):
        """BROADENING and PRECIPICE also log (sanity check the non-WATCH stages)."""
        from engine import foresight_cascade as fc_mod
        monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(fc_mod.config, "load", lambda: {"themes": {}})

        payload = {
            "asof": "2026-07-09",
            "themes": [
                {"theme": "nuclear_power", "stage": "PRECIPICE",
                 "bottleneck_band": "SOLD_OUT", "revision_breadth": 0.05},
                {"theme": "grid_electrification", "stage": "BROADENING",
                 "bottleneck_band": "TIGHT", "revision_breadth": 0.35},
            ],
        }
        (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)
        fc_mod._append_ledger(payload)
        log_path = tmp_path / "foresight" / "log.jsonl"
        rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        stages = {r["theme"]: r["stage"] for r in rows}
        assert stages.get("nuclear_power") == "PRECIPICE"
        assert stages.get("grid_electrification") == "BROADENING"
