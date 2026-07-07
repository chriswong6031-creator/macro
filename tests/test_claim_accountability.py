"""Tests for scripts/audit_claim_accountability.py — claim accountability audit.

NW Codex Three Lobes W-A (PR-B).  Uses synthetic temp-dir fixtures to verify:
  - per-desk and per-family breakdown computation
  - falsifier_coverage arithmetic
  - hit_gradeable_share (direction=0 excluded from hit-gradeability)
  - maturity_mix counts at 5d / 21d / 63d
  - fill_convention_split (asof_legacy vs next_bar)
  - source_ontology_fill rates
  - empty desks/families appear with zeros, not dropped
  - JSON + markdown output writing
  - check mode (no writes)
  - run_as_collect_step never raises

All assertions are on observable outputs — not on internal implementation details.
Zero dependence on real data files.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.audit_claim_accountability as aca


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows))


def _make_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _minimal_claim(
    *,
    desk: str = "test_desk",
    family: str = "test_family",
    claim_id: str = "abc123",
    direction: int = 1,
    falsifier: dict | None = None,
    source_tier: str | None = None,
    channels: list | None = None,
    source_id: str | None = None,
    horizon_d: int = 5,
) -> dict:
    return {
        "desk": desk,
        "claim_family": family,
        "claim_id": claim_id,
        "direction": direction,
        "horizon_d": horizon_d,
        "falsifier": falsifier,
        "source_tier": source_tier,
        "channels": channels,
        "source_id": source_id,
    }


def _minimal_grade(
    *,
    claim_id: str = "abc123",
    horizon_d: int = 5,
    fill_convention: str | None = None,
) -> dict:
    return {
        "claim_id": claim_id,
        "horizon_d": horizon_d,
        "graded_at": "2026-07-01T00:00:00+00:00",
        "excess": 0.01,
        "hit": True,
        "fill_convention": fill_convention,
    }


def _build_root(
    tmp_path: Path,
    claims: list[dict],
    grades: list[dict],
    track_record: dict | None = None,
) -> Path:
    """Populate tmp_path with synthetic qledger files and return it as root."""
    _make_jsonl(tmp_path / "data" / "qledger" / "claims.jsonl", claims)
    _make_jsonl(tmp_path / "data" / "qledger" / "grades.jsonl", grades)
    if track_record is not None:
        _make_json(tmp_path / "site" / "qledger" / "track_record.json", track_record)
    return tmp_path


# ---------------------------------------------------------------------------
# GLOBAL SUMMARY
# ---------------------------------------------------------------------------

class TestGlobalSummary:
    def test_n_claims_and_grades(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1", falsifier={"text": "test"}),
            _minimal_claim(claim_id="c2"),
            _minimal_claim(claim_id="c3"),
        ]
        grades = [
            _minimal_grade(claim_id="c1"),
            _minimal_grade(claim_id="c2"),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        g = payload["global"]
        assert g["n_claims"] == 3
        assert g["n_grades"] == 2
        assert g["n_with_falsifier"] == 1

    def test_falsifier_coverage_fraction(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="f1", falsifier={"text": "x"}),
            _minimal_claim(claim_id="f2", falsifier={"text": "y"}),
            _minimal_claim(claim_id="f3"),
            _minimal_claim(claim_id="f4"),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        g = payload["global"]
        assert g["n_with_falsifier"] == 2
        assert abs(g["falsifier_coverage"] - 0.5) < 1e-6

    def test_zero_claims_no_crash(self, tmp_path: Path) -> None:
        root = _build_root(tmp_path, [], [])
        payload = aca.run(root=root, write=False)
        g = payload["global"]
        assert g["n_claims"] == 0
        assert g["falsifier_coverage"] is None


# ---------------------------------------------------------------------------
# HIT-GRADEABILITY
# ---------------------------------------------------------------------------

class TestHitGradeability:
    def test_direction_0_not_hit_gradeable(self, tmp_path: Path) -> None:
        """direction=0 claims must reduce hit_gradeable_share."""
        claims = [
            _minimal_claim(claim_id="d0a", direction=0),
            _minimal_claim(claim_id="d0b", direction=0),
            _minimal_claim(claim_id="d1a", direction=1),
            _minimal_claim(claim_id="dm1", direction=-1),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        desk = payload["by_desk"]["test_desk"]
        # 2 hit-gradeable out of 4
        assert desk["n_hit_gradeable"] == 2
        assert abs(desk["hit_gradeable_share"] - 0.5) < 1e-6

    def test_all_direction_0_gives_zero_share(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="d0a", direction=0),
            _minimal_claim(claim_id="d0b", direction=0),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        desk = payload["by_desk"]["test_desk"]
        assert desk["hit_gradeable_share"] == 0.0
        assert desk["n_hit_gradeable"] == 0

    def test_hit_gradeable_note_present(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="x1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        note = payload["by_desk"]["test_desk"]["hit_gradeable_note"]
        assert "direction=0" in note
        assert "not hit-gradeable" in note

    def test_direction_1_and_neg1_both_count(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1", direction=1),
            _minimal_claim(claim_id="c2", direction=-1),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        desk = payload["by_desk"]["test_desk"]
        assert desk["n_hit_gradeable"] == 2
        assert desk["hit_gradeable_share"] == 1.0


# ---------------------------------------------------------------------------
# MATURITY MIX
# ---------------------------------------------------------------------------

class TestMaturityMix:
    def test_5d_graded_count(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1"), _minimal_claim(claim_id="c2")]
        grades = [
            _minimal_grade(claim_id="c1", horizon_d=5),
            _minimal_grade(claim_id="c2", horizon_d=5),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        mm = payload["by_desk"]["test_desk"]["maturity_mix"]
        assert mm["graded_5d_count"] == 2
        assert mm["matured_21d_count"] == 0
        assert mm["matured_63d_count"] == 0

    def test_21d_graded_counted_separately(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        grades = [
            _minimal_grade(claim_id="c1", horizon_d=5),
            _minimal_grade(claim_id="c1", horizon_d=21),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        mm = payload["by_desk"]["test_desk"]["maturity_mix"]
        assert mm["graded_5d_count"] == 1
        assert mm["matured_21d_count"] == 1
        assert mm["matured_63d_count"] == 0

    def test_maturity_note_present(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        note = payload["by_desk"]["test_desk"]["maturity_mix"]["note"]
        assert "calendar-gated" in note


# ---------------------------------------------------------------------------
# FILL_CONVENTION SPLIT
# ---------------------------------------------------------------------------

class TestFillConventionSplit:
    def test_asof_legacy_none_fill(self, tmp_path: Path) -> None:
        """Grades with fill_convention=None count as asof_legacy."""
        claims = [_minimal_claim(claim_id="c1")]
        grades = [
            _minimal_grade(claim_id="c1", fill_convention=None),
            _minimal_grade(claim_id="c1", fill_convention=None),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        fcs = payload["by_desk"]["test_desk"]["fill_convention_split"]
        assert fcs["asof_legacy_count"] == 2
        assert fcs["next_bar_count"] == 0

    def test_next_bar_fill(self, tmp_path: Path) -> None:
        """Grades with fill_convention='next_bar' count as next_bar."""
        claims = [_minimal_claim(claim_id="c1")]
        grades = [
            _minimal_grade(claim_id="c1", fill_convention="next_bar"),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        fcs = payload["by_desk"]["test_desk"]["fill_convention_split"]
        assert fcs["next_bar_count"] == 1
        assert fcs["asof_legacy_count"] == 0

    def test_mixed_split(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1"),
            _minimal_claim(claim_id="c2"),
        ]
        grades = [
            _minimal_grade(claim_id="c1", fill_convention=None),
            _minimal_grade(claim_id="c1", fill_convention=None),
            _minimal_grade(claim_id="c2", fill_convention="next_bar"),
        ]
        root = _build_root(tmp_path, claims, grades)
        payload = aca.run(root=root, write=False)
        fcs = payload["by_desk"]["test_desk"]["fill_convention_split"]
        assert fcs["asof_legacy_count"] == 2
        assert fcs["next_bar_count"] == 1

    def test_note_mentions_1180(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        note = payload["by_desk"]["test_desk"]["fill_convention_split"]["note"]
        assert "1180" in note


# ---------------------------------------------------------------------------
# SOURCE ONTOLOGY FILL
# ---------------------------------------------------------------------------

class TestSourceOntologyFill:
    def test_zero_fill_when_absent(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1", source_tier=None, channels=None, source_id=None),
            _minimal_claim(claim_id="c2", source_tier=None, channels=None, source_id=None),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        sof = payload["by_desk"]["test_desk"]["source_ontology_fill"]
        assert sof["source_tier_fill_rate"] == 0.0
        assert sof["channels_fill_rate"] == 0.0
        assert sof["source_id_fill_rate"] == 0.0

    def test_partial_fill_rate(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1", source_tier="tier2", channels=["ch1"], source_id="s1"),
            _minimal_claim(claim_id="c2", source_tier=None, channels=None, source_id=None),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        sof = payload["by_desk"]["test_desk"]["source_ontology_fill"]
        assert abs(sof["source_tier_fill_rate"] - 0.5) < 1e-6
        assert abs(sof["channels_fill_rate"] - 0.5) < 1e-6
        assert abs(sof["source_id_fill_rate"] - 0.5) < 1e-6

    def test_note_mentions_500_label_gate(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        note = payload["by_desk"]["test_desk"]["source_ontology_fill"]["note"]
        assert "500" in note


# ---------------------------------------------------------------------------
# PER-FAMILY BREAKDOWN
# ---------------------------------------------------------------------------

class TestPerFamily:
    def test_family_buckets_separate_from_desk(self, tmp_path: Path) -> None:
        claims = [
            _minimal_claim(claim_id="c1", desk="desk_a", family="fam_x"),
            _minimal_claim(claim_id="c2", desk="desk_b", family="fam_x"),
            _minimal_claim(claim_id="c3", desk="desk_a", family="fam_y"),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        # fam_x has 2 claims across 2 desks
        assert payload["by_family"]["fam_x"]["n_claims"] == 2
        # fam_y has 1 claim
        assert payload["by_family"]["fam_y"]["n_claims"] == 1
        # desk_a has 2 claims
        assert payload["by_desk"]["desk_a"]["n_claims"] == 2

    def test_all_families_present(self, tmp_path: Path) -> None:
        families = ["fam_alpha", "fam_beta", "fam_gamma"]
        claims = [
            _minimal_claim(claim_id=f"c{i}", family=fam)
            for i, fam in enumerate(families)
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        for fam in families:
            assert fam in payload["by_family"], f"Family {fam!r} missing from by_family"


# ---------------------------------------------------------------------------
# EMPTY DESK / FAMILY — zeros not dropped
# ---------------------------------------------------------------------------

class TestNullsNotDropped:
    def test_empty_claims_file_gives_empty_dicts(self, tmp_path: Path) -> None:
        """With no claims, by_desk and by_family are empty (no crashes)."""
        root = _build_root(tmp_path, [], [])
        payload = aca.run(root=root, write=False)
        assert payload["by_desk"] == {}
        assert payload["by_family"] == {}
        assert payload["global"]["n_claims"] == 0

    def test_multi_desk_all_appear(self, tmp_path: Path) -> None:
        """All desks in the claim file appear in the output."""
        claims = [
            _minimal_claim(claim_id="c1", desk="alpha"),
            _minimal_claim(claim_id="c2", desk="beta"),
            _minimal_claim(claim_id="c3", desk="gamma"),
        ]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        assert set(payload["by_desk"].keys()) == {"alpha", "beta", "gamma"}


# ---------------------------------------------------------------------------
# JSON + MARKDOWN OUTPUT WRITING
# ---------------------------------------------------------------------------

class TestOutputWriting:
    def _build_simple_root(self, tmp_path: Path) -> Path:
        claims = [
            _minimal_claim(claim_id="c1", falsifier={"text": "falsifier text"}),
            _minimal_claim(claim_id="c2", direction=0),
        ]
        grades = [_minimal_grade(claim_id="c1")]
        return _build_root(tmp_path, claims, grades)

    def test_json_written(self, tmp_path: Path) -> None:
        root = self._build_simple_root(tmp_path)
        aca.run(root=root, write=True)
        json_path = root / "data" / "governance" / "claim_accountability.json"
        assert json_path.exists(), "claim_accountability.json was not written"
        loaded = json.loads(json_path.read_text())
        assert loaded["schema"] == "claim_accountability.v1"
        assert "global" in loaded
        assert "by_desk" in loaded
        assert "by_family" in loaded

    def test_markdown_written(self, tmp_path: Path) -> None:
        root = self._build_simple_root(tmp_path)
        aca.run(root=root, write=True)
        md_path = root / "docs" / "CLAIM_ACCOUNTABILITY.md"
        assert md_path.exists(), "CLAIM_ACCOUNTABILITY.md was not written"
        md = md_path.read_text()
        assert "# Claim Accountability" in md
        assert "falsifier" in md.lower()
        assert "direction=0" in md

    def test_markdown_does_not_touch_grading_closure(self, tmp_path: Path) -> None:
        """Writer must never write docs/GRADING_CLOSURE.md."""
        root = self._build_simple_root(tmp_path)
        aca.run(root=root, write=True)
        gc_path = root / "docs" / "GRADING_CLOSURE.md"
        assert not gc_path.exists(), (
            "audit_claim_accountability must never write docs/GRADING_CLOSURE.md "
            "(single-writer invariant — owned by audit_grading_closure)"
        )

    def test_check_mode_no_writes(self, tmp_path: Path) -> None:
        root = self._build_simple_root(tmp_path)
        payload = aca.run(root=root, write=False)
        json_path = root / "data" / "governance" / "claim_accountability.json"
        md_path = root / "docs" / "CLAIM_ACCOUNTABILITY.md"
        assert not json_path.exists(), "json should not be written in check mode"
        assert not md_path.exists(), "md should not be written in check mode"
        assert isinstance(payload, dict)

    def test_json_idempotent(self, tmp_path: Path) -> None:
        """Two runs write identical JSON content."""
        root = self._build_simple_root(tmp_path)
        p1 = aca.run(root=root, write=False)
        p2 = aca.run(root=root, write=False)
        # Strip generated_at (timestamp) for comparison
        for p in (p1, p2):
            p["generated_at"] = "STRIPPED"
        assert p1 == p2

    def test_markdown_no_validated_word(self, tmp_path: Path) -> None:
        """The word 'validated' must not appear in the generated markdown."""
        root = self._build_simple_root(tmp_path)
        aca.run(root=root, write=True)
        md = (root / "docs" / "CLAIM_ACCOUNTABILITY.md").read_text()
        # CI-guarded in user-facing text
        assert "validated" not in md.lower(), (
            "The word 'validated' must not appear in CLAIM_ACCOUNTABILITY.md"
        )


# ---------------------------------------------------------------------------
# SCHEMA VALIDATION
# ---------------------------------------------------------------------------

class TestPayloadSchema:
    def test_required_top_level_keys(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        for key in ("schema", "generated_at", "global", "by_desk", "by_family"):
            assert key in payload, f"Missing top-level key: {key!r}"

    def test_schema_version(self, tmp_path: Path) -> None:
        root = _build_root(tmp_path, [], [])
        payload = aca.run(root=root, write=False)
        assert payload["schema"] == "claim_accountability.v1"

    def test_desk_entry_has_required_fields(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        desk = payload["by_desk"]["test_desk"]
        for field in (
            "n_claims", "falsifier_coverage", "hit_gradeable_share",
            "hit_gradeable_note", "maturity_mix", "fill_convention_split",
            "source_ontology_fill",
        ):
            assert field in desk, f"Missing desk field: {field!r}"

    def test_maturity_mix_has_all_counts(self, tmp_path: Path) -> None:
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [])
        payload = aca.run(root=root, write=False)
        mm = payload["by_desk"]["test_desk"]["maturity_mix"]
        for k in ("graded_5d_count", "matured_21d_count", "matured_63d_count"):
            assert k in mm, f"Missing maturity_mix key: {k!r}"


# ---------------------------------------------------------------------------
# TRACK_RECORD REFERENCE (fail-open)
# ---------------------------------------------------------------------------

class TestTrackRecordReference:
    def test_absent_track_record_no_crash(self, tmp_path: Path) -> None:
        """If track_record.json is absent, audit must still complete."""
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [], track_record=None)
        # site/qledger/track_record.json not created — should not crash
        payload = aca.run(root=root, write=False)
        assert "track_record_ref" in payload

    def test_present_track_record_included(self, tmp_path: Path) -> None:
        tr = {"generated_at": "2026-07-06T00:00:00+00:00", "by_desk": {"altdata": {}}}
        claims = [_minimal_claim(claim_id="c1")]
        root = _build_root(tmp_path, claims, [], track_record=tr)
        payload = aca.run(root=root, write=False)
        ref = payload["track_record_ref"]
        assert ref.get("generated_at") == "2026-07-06T00:00:00+00:00"


# ---------------------------------------------------------------------------
# COLLECT-STEP RESILIENCE
# ---------------------------------------------------------------------------

class TestCollectStepResilience:
    def test_never_raises_on_broken_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _broken_run(*args, **kwargs):
            raise RuntimeError("simulated audit crash")
        monkeypatch.setattr(aca, "run", _broken_run)
        aca.run_as_collect_step()  # must not raise

    def test_never_raises_on_empty_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scripts.audit_claim_accountability as _aca
        original_run = _aca.run

        def _patched_run(*args, **kwargs):
            return original_run(root=tmp_path, write=False)

        monkeypatch.setattr(_aca, "run", _patched_run)
        _aca.run_as_collect_step()  # must not raise
