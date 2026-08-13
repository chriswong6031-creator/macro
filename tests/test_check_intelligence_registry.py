"""tests/test_check_intelligence_registry.py — the gate must work in BOTH directions.

A validator that flags everything is as useless as one that flags nothing, so this suite
pins the guard's own selftest AND mutation-tests it: with the validator stubbed out, the
selftest must FAIL. Without that, the selftest is a receipt written from the same variable
it checks and cannot fail.

It also pins the two CI-observable behaviours the house laws depend on: annotations START
the line (a logger-prefixed one is dropped silently by GitHub), and the guard FAILS CLOSED
— a run that could not read an input says so on its summary line and exits non-zero under
--strict, instead of printing a zero-violation count it did not earn.

NOTHING HERE ASSERTS ON LIVE CONTENT. There is no committed registry to compare against,
and no count from config/synapse.yml or data/qledger/ is pinned — both move without any PR
on this lane.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_intelligence_registry as guard
from engine.intelligence_registry import validate_overlay, validate_structure

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_intelligence_registry.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or REPO),
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
    assert result.stdout.count("[PASS]") >= 60
    assert "[FAIL]" not in result.stdout


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
        ("resolve_qual_ladder_ref always resolves", ("resolve_qual_ladder_ref", lambda r, **k: "repo_path")),
    ],
)
def test_selftest_fails_when_the_validator_is_broken(monkeypatch, name, stub):
    """If any of these mutations still passes, the selftest is decorative."""
    attr, replacement = stub
    monkeypatch.setattr(guard, attr, replacement)
    assert _selftest_rc() == 1, f"selftest survived a broken validator: {name}"


def test_selftest_fails_when_the_C1_DERIVATION_ITSELF_IS_DELETED(monkeypatch):
    """THE NEGATIVE CONTROL THAT MATTERS. The other mutations stub the VALIDATORS; this one
    deletes the COMPUTATION the C-1 finding is made of — `unevidenced_artifacts` — inside
    the real build_registry, and the selftest must still fail.

    Without this, the selftest could be passing because its fixtures already contain the
    answer ("a receipt derived from what it checks cannot fail").
    """
    import engine.intelligence_registry as mod

    real_build = mod.build_registry

    def gutted(**kwargs):
        registry = real_build(**kwargs)
        for row in registry["engines"]:
            row["authority_evidence"]["unevidenced_artifacts"] = []
        return registry

    monkeypatch.setattr(guard, "build_registry", gutted)
    assert _selftest_rc() == 1, "the C-1 derivation is not covered by a negative control"


def test_selftest_fails_when_the_species_null_is_collapsed_to_an_empty_store(monkeypatch):
    """The 2026-08-12 failure, pinned. Substituting an EMPTY species list for the NULL is
    exactly 'could not look' rendered as 'looked and found nothing'; the selftest must see
    it."""
    import engine.intelligence_registry as mod

    real_build = mod.build_registry

    def collapsed(**kwargs):
        if kwargs.get("species") is None:
            kwargs["species"] = []
        return real_build(**kwargs)

    monkeypatch.setattr(guard, "build_registry", collapsed)
    assert _selftest_rc() == 1


def test_selftest_passes_again_once_restored():
    assert _selftest_rc() == 0


# ---------------------------------------------------------------------------
# Severity split — structural violations hard, content findings warn
# ---------------------------------------------------------------------------

def test_default_run_is_advisory_for_content_findings():
    """The content law fires on PRE-EXISTING corpus conditions no PR author caused. Wiring
    it hard on arrival would red main fleet-wide, which is how a gate gets routed around."""
    result = _run()
    assert result.returncode == 0, result.stdout[-2000:]


def test_strict_escalates_content_findings():
    result = _run("--strict")
    payload = json.loads(_run("--json").stdout)
    expected = 1 if (payload["violations"] or payload["findings"] or payload["unreadable_inputs"]) else 0
    assert result.returncode == expected


def test_structural_violations_exit_non_zero():
    """Proven on a synthetic bad view, not by hoping the live one is broken."""
    assert validate_structure({"schema": "wrong", "meta": {}, "engines": [], "excluded": []}) != []


# ---------------------------------------------------------------------------
# Annotation contract (CLAUDE.md §"GitHub annotations must START the line")
# ---------------------------------------------------------------------------

def test_annotations_start_the_line_and_are_never_logged():
    result = _run()
    annotated = [
        line for line in result.stdout.splitlines()
        if "::warning" in line or "::error" in line or "::notice" in line
    ]
    assert annotated, "the guard emitted no annotation at all"
    for line in annotated:
        assert line.startswith("::"), (
            f"annotation does not start the line — GitHub drops it silently: {line!r}"
        )


def test_guard_source_never_routes_an_annotation_through_a_logger():
    source = SCRIPT.read_text(encoding="utf-8")
    for bad in ('log.warning("::', 'log.error("::', 'logger.warning("::', 'logging.warning("::'):
        assert bad not in source


def test_annotation_volume_is_budgeted():
    """One annotation per finding would bury the actionable C-1 rows, so every non-C-1 code
    is aggregated to a single annotation with a count and full detail goes to stdout.

    ONE SUBPROCESS. Comparing counts across TWO independent guard invocations was a
    cross-invocation equality assertion over a shared checkout — a racy structure, observed
    failing once in 8 runs. Reading both halves out of the SAME stdout removes the race by
    construction.
    """
    result = _run()
    lines = result.stdout.splitlines()
    warnings = [line for line in lines if line.startswith("::warning")]
    per_engine = [w for w in warnings if "[AUTHORITY_WITHOUT_EVIDENCE]" in w]
    aggregated = [w for w in warnings if "engine(s) — detail on stdout" in w]
    assert warnings, result.stdout[-2000:]
    assert len(warnings) == len(per_engine) + len(aggregated), (
        "every annotation is either one C-1 row or one aggregated count"
    )
    detail_lines = [
        line for line in lines
        if line.startswith("  [") and "AUTHORITY_WITHOUT_EVIDENCE" not in line
    ]
    assert len(aggregated) < len(detail_lines), (
        "aggregation must actually compress — otherwise the budget is decorative"
    )


# ---------------------------------------------------------------------------
# FAIL CLOSED — "could not look" is never "looked and found nothing"
# ---------------------------------------------------------------------------

def test_an_unreadable_synapse_is_NOT_CHECKED_never_a_clean_count(tmp_path):
    """A previous round printed '0 integrity violation(s)' when it could not read its
    inputs. The SUMMARY LINE — the one line a CI reader sees — must say it could not look,
    and the run must exit non-zero."""
    result = _run("--root", str(tmp_path))
    assert result.returncode != 0, result.stdout
    summary = next(
        line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")
    )
    assert "NOT CHECKED" in summary
    assert "inputs=INCOMPLETE" in summary
    # The normal-run summary shape must NOT appear: that is the sentence a CI reader skims
    # for, and printing it while blind is the whole defect.
    assert "structural violation(s)" not in summary
    assert "engines," not in summary
    assert any(line.startswith("::error") for line in result.stdout.splitlines())


def test_an_unreadable_synapse_in_json_mode_reports_absence_not_emptiness(tmp_path):
    result = _run("--root", str(tmp_path), "--json")
    payload = json.loads(result.stdout)
    assert payload["inputs_complete"] is False
    assert payload["violations"] is None and payload["findings"] is None, (
        "an empty list would render 'could not look' as 'looked and clean'"
    )
    assert payload["unreadable_inputs"] == ["config/synapse.yml"]
    assert result.returncode != 0


def test_a_PARTIALLY_unreadable_input_set_names_what_it_missed_and_strict_reds(monkeypatch):
    """The other half of fail-closed: synapse READS but a downstream store does not. The
    summary must carry `inputs=INCOMPLETE (...)` naming the store, and --strict must exit
    non-zero on that alone — an absence of findings is not a pass when the inputs are
    partial."""
    import scripts.build_intelligence_registry as builder

    real_build = builder.build

    def blinded(root):
        registry, report = real_build(root)
        report = dict(report)
        report["unreadable_inputs"] = list(report["unreadable_inputs"]) + [
            str(builder.SPECIES_REL)
        ]
        report["inputs_complete"] = False
        return registry, report

    monkeypatch.setattr(guard, "build", blinded)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = guard.main(["--strict"])
    out = buf.getvalue()
    assert "inputs=INCOMPLETE" in out
    assert "data/species/registry.json" in out.split("intelligence registry:")[-1]
    assert rc != 0, "a blind run must not exit 0 under --strict"


def test_the_summary_line_always_carries_an_inputs_clause():
    result = _run()
    summary = [line for line in result.stdout.splitlines() if line.startswith("intelligence registry:")]
    assert len(summary) == 1, summary
    assert "inputs=" in summary[0]


def test_json_mode_always_emits_an_object():
    payload = json.loads(_run("--json").stdout)
    assert isinstance(payload, dict)
    assert "inputs_complete" in payload and "unreadable_inputs" in payload


# ---------------------------------------------------------------------------
# The C-1 backlog is VISIBLE and every row names its heal
# ---------------------------------------------------------------------------

def test_the_C1_backlog_is_reported_and_every_finding_names_its_heal():
    payload = json.loads(_run("--json").stdout)
    c1 = [f for f in payload["findings"] if f["code"] == "AUTHORITY_WITHOUT_EVIDENCE"]
    assert c1, "the C-1 backlog must be reported, not hidden"
    for finding in c1:
        assert "qual_ladder_ref" in finding["detail"], "every finding names its heal"


def test_the_derived_view_has_zero_structural_violations():
    """Structural violations are properties of the DERIVATION and of the hand-edited
    overlay — green by construction on arrival, so they can be hard without firing
    fleet-wide for nobody's fault."""
    payload = json.loads(_run("--json").stdout)
    assert payload["violations"] == [], payload["violations"]


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


def test_the_overlay_orphan_rule_reads_the_PARTITION_not_the_built_ids():
    """A `not_an_engine` row used to SELF-LEGITIMATE: it created the excluded row that
    proved it was not an orphan, so the orphan rule could never fire on it."""
    from scripts.build_intelligence_registry import build

    registry, report = build(REPO)
    excluded_ids = {r["engine_id"] for r in registry["excluded"]}
    assert excluded_ids, "the fixture needs at least one excluded cell"
    assert excluded_ids <= set(report["cell_ids"]), (
        "cell_ids is the PRE-EXCLUSION partition, so an excluded id is still a real cell"
    )
    assert validate_overlay(
        {"schema_version": 1, "engines": {"engine/ghost.py::nowhere": {"not_an_engine": {
            "reason": "x" * 50, "ratified_by": "y", "date": "2026-08-12"}}}},
        report["cell_ids"],
    ), "a row for a cell the partition does not contain must still be an orphan"


# ---------------------------------------------------------------------------
# There is no equality pin left to red the fleet
# ---------------------------------------------------------------------------

def test_the_guard_has_no_drift_or_equality_mode():
    """Rounds 1 and 2 both shipped an equality pin and both were scheduled fleet-wide
    reds. Their absence is the architecture, so it is asserted FUNCTIONALLY — the prose in
    both modules discusses the deleted pin by name, so a grep of the source text would
    match its own postmortem."""
    assert _run("--check").returncode == 2, "--check must be an unknown argument"

    # ...and nothing in the program OPENS a generated artifact.
    for module in (SCRIPT, REPO / "scripts" / "build_intelligence_registry.py",
                   REPO / "engine" / "intelligence_registry.py"):
        source = module.read_text(encoding="utf-8")
        for reader in ('read_text(', 'json.load(', 'open('):
            for line in source.splitlines():
                if reader in line and "intelligence_registry.json" in line:
                    raise AssertionError(f"{module.name}: reads a generated artifact: {line}")


def test_no_test_in_this_program_asserts_on_live_synapse_contents():
    """THE STANDING RULE, ENFORCED FROM INSIDE. A sibling PR adding a scored artifact to
    config/synapse.yml must never red this lane, so no test may READ that file directly and
    assert on what is in it. Live-input tests go through the builder and assert only shape.

    Matched on the READ EXPRESSION, not on the filename: both suites discuss synapse.yml in
    prose, and a filename grep would match the sentence explaining the rule.

    The needles are ASSEMBLED AT RUNTIME so this file does not contain them literally —
    a self-matching guard reports its own definition and can never be green.
    """
    corpus = "synapse.yml"
    needles = [
        corpus + '").read_text',
        corpus + "').read_text",
        "def " + "live_synapse",
        "live_" + "registry",
    ]
    for name in ("test_intelligence_registry.py", "test_check_intelligence_registry.py"):
        source = (REPO / "tests" / name).read_text(encoding="utf-8")
        for banned in needles:
            assert banned not in source, f"{name}: reads live corpus contents ({banned})"
