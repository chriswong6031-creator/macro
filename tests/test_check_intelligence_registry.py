"""tests/test_check_intelligence_registry.py — the gate must work in BOTH directions.

A validator that flags everything is as useless as one that flags nothing, so this suite
pins the guard's own selftest AND mutation-tests it: with the validator stubbed out, the
selftest must FAIL. Without that, the selftest is a receipt written from the same variable
it checks and cannot fail.

Also pins the CI-observable behaviour the house laws depend on: annotations start the
line, an absent registry exits 0 with a notice rather than a false green, and the
warn-tier law stays advisory unless --strict.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_intelligence_registry as guard
from engine.intelligence_registry import audit_content, validate_overlay, validate_structure

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_intelligence_registry.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _selftest_rc() -> int:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return guard._selftest()


# ---------------------------------------------------------------------------
# The selftest itself
# ---------------------------------------------------------------------------

def test_selftest_passes_as_shipped():
    result = _run("--selftest")
    assert result.returncode == 0, result.stdout
    assert "selftest: PASS" in result.stdout


def test_selftest_covers_both_directions():
    result = _run("--selftest")
    assert "POSITIVE CONTROL" in result.stdout
    assert "NEGATIVE" in result.stdout
    assert result.stdout.count("[PASS]") >= 30


# ---------------------------------------------------------------------------
# MUTATION CONTROLS — the selftest must be able to fail
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,stub",
    [
        ("validate_structure accepts everything", ("validate_structure", lambda *a, **k: [])),
        ("validate_structure rejects everything", ("validate_structure", lambda *a, **k: ["x"])),
        ("validate_overlay accepts everything", ("validate_overlay", lambda *a, **k: [])),
        ("validate_overlay rejects everything", ("validate_overlay", lambda *a, **k: ["x"])),
        ("audit_content finds nothing", ("audit_content", lambda *a, **k: [])),
        ("structural_projection strips nothing", ("structural_projection", lambda r: dict(r))),
    ],
)
def test_selftest_fails_when_the_validator_is_broken(monkeypatch, name, stub):
    """If any of these mutations still passes, the selftest is decorative."""
    attr, replacement = stub
    monkeypatch.setattr(guard, attr, replacement)
    assert _selftest_rc() == 1, f"selftest survived a broken validator: {name}"


def test_selftest_passes_again_once_restored():
    assert _selftest_rc() == 0


# ---------------------------------------------------------------------------
# Severity split — law A hard, law B warn
# ---------------------------------------------------------------------------

def test_default_run_is_advisory_for_content_findings():
    """Law B fires on PRE-EXISTING corpus conditions no PR author caused. Wiring it hard
    on arrival would red main fleet-wide, which is how a gate gets routed around."""
    result = _run()
    if "registry absent" in result.stdout:
        pytest.skip("registry absent in this checkout")
    assert result.returncode == 0, result.stdout[-2000:]


def test_strict_escalates_content_findings():
    result = _run("--strict")
    if "registry absent" in result.stdout:
        pytest.skip("registry absent in this checkout")
    payload = json.loads(_run("--json").stdout)
    expected = 1 if (payload["integrity"] or payload["content"]) else 0
    assert result.returncode == expected


def test_integrity_violations_would_fail_hard():
    """Law A must exit non-zero — proven on a synthetic bad registry, not by hoping the
    live one is broken."""
    bad = {"schema": "wrong", "meta": {}, "engines": [], "excluded": []}
    assert validate_structure(bad) != []


# ---------------------------------------------------------------------------
# Annotation contract (CLAUDE.md §"GitHub annotations must START the line")
# ---------------------------------------------------------------------------

def test_annotations_start_the_line_and_are_never_logged():
    result = _run()
    annotated = [
        line for line in result.stdout.splitlines()
        if "::warning" in line or "::error" in line or "::notice" in line
    ]
    for line in annotated:
        assert line.startswith("::"), (
            f"annotation does not start the line — GitHub drops it silently: {line!r}"
        )


def test_guard_source_never_routes_an_annotation_through_a_logger():
    source = SCRIPT.read_text(encoding="utf-8")
    for bad in ("log.warning(\"::", "log.error(\"::", "logger.warning(\"::", "logging.warning(\"::"):
        assert bad not in source


def test_annotation_volume_is_budgeted():
    """154 findings on the 2026-08-12 corpus. One annotation each would bury the
    actionable C-1 rows; every non-C-1 code is aggregated to a single annotation."""
    result = _run()
    if "registry absent" in result.stdout:
        pytest.skip("registry absent in this checkout")
    payload = json.loads(_run("--json").stdout)
    non_c1_codes = {
        f["code"] for f in payload["content"] if f["code"] != "AUTHORITY_WITHOUT_EVIDENCE"
    }
    warnings = [line for line in result.stdout.splitlines() if line.startswith("::warning")]
    c1 = sum(1 for f in payload["content"] if f["code"] == "AUTHORITY_WITHOUT_EVIDENCE")
    assert len(warnings) == c1 + len(non_c1_codes)


# ---------------------------------------------------------------------------
# "Could not look" is never "looked and found nothing"
# ---------------------------------------------------------------------------

def test_absent_registry_exits_zero_with_a_notice(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "::notice" in result.stdout
    assert "registry absent" in result.stdout


def test_absent_registry_json_mode_reports_absence_not_emptiness(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--json"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    payload = json.loads(result.stdout)
    assert payload["registry_absent"] is True
    assert payload["integrity"] is None and payload["content"] is None, (
        "an empty list would render 'could not look' as 'looked and clean'"
    )


def test_json_mode_always_emits_an_object():
    payload = json.loads(_run("--json").stdout)
    assert isinstance(payload, dict)
    assert "registry_absent" in payload


# ---------------------------------------------------------------------------
# The live registry is green on law A
# ---------------------------------------------------------------------------

def test_live_registry_has_zero_integrity_violations():
    payload = json.loads(_run("--json").stdout)
    if payload["registry_absent"]:
        pytest.skip("registry absent in this checkout")
    assert payload["integrity"] == [], payload["integrity"]


def test_live_registry_reports_the_C1_backlog():
    """C-1 must be VISIBLE, not silently null."""
    payload = json.loads(_run("--json").stdout)
    if payload["registry_absent"]:
        pytest.skip("registry absent in this checkout")
    c1 = [f for f in payload["content"] if f["code"] == "AUTHORITY_WITHOUT_EVIDENCE"]
    assert c1, "the C-1 backlog must be reported, not hidden"
    for finding in c1:
        assert "qual_ladder_ref" in finding["detail"], "every finding names its heal"


# ---------------------------------------------------------------------------
# Overlay orphan rule
# ---------------------------------------------------------------------------

def test_orphan_overlay_row_is_a_hard_error_not_a_warning():
    violations = validate_overlay(
        {"schema_version": 1, "engines": {"gone/away.py::prog": {"not_an_engine": {"reason": "r"}}}},
        ["engine/a.py::prog"],
    )
    assert any("orphan" in v for v in violations)


def test_overlay_forbidden_key_names_the_dnr_row():
    violations = validate_overlay(
        {"schema_version": 1, "engines": {"engine/a.py::prog": {"authority": "gate_size"}}},
        ["engine/a.py::prog"],
    )
    assert any("KILL-PARALLEL-KNOWLEDGE-BASE" in v for v in violations)


# ---------------------------------------------------------------------------
# Drift + idempotence (law A)
# ---------------------------------------------------------------------------

def test_builder_check_mode_reports_no_drift():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_intelligence_registry.py"), "--check"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:]


def test_regeneration_is_idempotent():
    from scripts.build_intelligence_registry import build
    from engine.intelligence_registry import serialise

    first, _ = build(REPO)
    second, _ = build(REPO)
    assert serialise(first) == serialise(second)


def test_a_stale_committed_copy_cannot_pass():
    """The drift law must actually see a mutated committed file."""
    from engine.intelligence_registry import structural_projection
    from scripts.build_intelligence_registry import build

    fresh, _ = build(REPO)
    stale = copy.deepcopy(fresh)
    if not stale["engines"]:
        pytest.skip("no engines")
    stale["engines"][0]["authority"] = "gate_size"
    assert structural_projection(stale) != structural_projection(fresh)


def test_content_audit_is_pure_over_a_loaded_registry():
    from scripts.build_intelligence_registry import build

    registry, _ = build(REPO)
    assert audit_content(registry) == audit_content(registry)
