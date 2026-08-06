"""The trigger-closure guard: a suite's path filter must reach what the suite reads.

WHAT THIS PINS.  `scripts/check_ci_trigger_closure.py` fails a PR when a module in a
guarded suite's read-closure is matched by no `on.pull_request.paths` entry of any
workflow that runs it.  That is the #3488 lesson ("a guard whose own edit cannot
start the workflow is only half wired") turned from a comment into a check.

WHY THE TESTS BELOW LOOK LIKE THEY DO.  Three of them exist because writing this
guard produced three near-misses that a green suite would not have caught:

  * `fnmatch` is NOT GitHub's glob.  A single `*` crosses `/` in fnmatch and does
    not on GitHub, so a filter of `scripts/*.py` reads as covering
    `scripts/ci/deep.py`.  A guard built on fnmatch silently blesses exactly the
    nested modules most likely to be missing an entry.  `scripts/audit_unrun_tests.py`
    still uses fnmatch — it is a reporting tool and over-reporting coverage there is
    survivable; here it would be a hole in a merge gate.
  * PROSE IS NOT A READ.  A path named in a docstring, a comment, or inside an
    assertion sentence is a claim about a subject, not a read of one.  The census
    already learned this once from the other side (OIP E8: a suite named in a YAML
    comment counted as "run by CI").
  * A JOIN'S BASE DECIDES WHAT IT NAMES.  `tmp_path / "config" / "brain.yml"` has the
    same segments as `ROOT / "config" / "brain.yml"` and is a file the suite WRITES.

Run: python3 -m pytest tests/test_ci_trigger_closure.py -q
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKER = ROOT / "scripts" / "check_ci_trigger_closure.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"

_SPEC = importlib.util.spec_from_file_location("check_ci_trigger_closure", CHECKER)
assert _SPEC and _SPEC.loader
GUARD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = GUARD
_SPEC.loader.exec_module(GUARD)


def _ci_paths() -> list[str]:
    payload = yaml.safe_load(CI.read_text())
    block = payload[True] if True in payload else payload["on"]
    return list(block["pull_request"]["paths"])


# ── 1. glob semantics: GitHub's, not fnmatch's ───────────────────────────────

@pytest.mark.parametrize(
    "rel,patterns,expected",
    [
        # `**` crosses directories — this is what makes engine/** cover the tree.
        ("engine/signal_quality.py", ["engine/**"], True),
        ("engine/deep/nested/thing.py", ["engine/**"], True),
        # A bare `*` does NOT cross `/`. fnmatch says True here; GitHub says False.
        ("scripts/ci/strip.py", ["scripts/*.py"], False),
        ("scripts/strip.py", ["scripts/*.py"], True),
        # A prefix must be a real path segment, not a string prefix.
        ("engineering/thing.py", ["engine/**"], False),
        # Exact entries, and the miss. Deliberately names files that are NOT in
        # the tree: a real path here would be a whole-string literal in a suite the
        # workflow-yaml job runs, and the guard would demand a trigger entry for a
        # file this test only ever passes to a matcher.
        ("config/no_such_file.yml", ["config/no_such_file.yml"], True),
        ("config/no_such_file.yml", ["config/some_other_file.yml"], False),
        # No `paths:` key at all → the workflow starts on every PR.
        ("literally/anything.py", None, True),
    ],
)
def test_glob_semantics_match_github_not_fnmatch(rel, patterns, expected) -> None:
    assert GUARD.matched(rel, patterns) is expected


def test_single_star_does_not_cross_a_slash() -> None:
    """The specific fnmatch divergence, pinned on its own so a revert is unmistakable.

    `fnmatch.fnmatch("scripts/ci/x.py", "scripts/*.py")` is True. If this guard ever
    goes back to fnmatch, every nested module under a `dir/*.ext` entry silently
    becomes "covered" and the gate stops seeing the class it exists for.
    """
    import fnmatch

    assert fnmatch.fnmatch("scripts/ci/x.py", "scripts/*.py") is True
    assert GUARD.matched("scripts/ci/x.py", ["scripts/*.py"]) is False


# ── 2. what counts as a read ─────────────────────────────────────────────────

_FIXTURE = '''
"""Docstring names config/reflexes.yml."""
import importlib
from pathlib import Path

from engine import market_state

REPO = Path(__file__).resolve().parents[1]
PACKET = REPO / "research" / "prophet_us_audit" / "reclaim_veto_packet.py"
LISTED = ["scripts/audit_unrun_tests.py"]
GONE = "engine/no_such_module_exists_here.py"
LAZY = importlib.import_module("collectors.fred")
POINTER = "roster lives in config/seasonality_universe.yml, see there"

# Comment names config/trade_flow_codes.yml.


def test_writes(tmp_path, root):
    """Docstring names config/clinical_modalities.yml."""
    (tmp_path / "config" / "brain.yml").write_text("x")
    (root / "config" / "evidence_clock.yml").write_text("y")
'''


@pytest.fixture(scope="module")
def fixture_reads(tmp_path_factory) -> dict[str, str]:
    suite = tmp_path_factory.mktemp("closure") / "test_fixture.py"
    suite.write_text(_FIXTURE)
    return GUARD.direct_reads(suite)


@pytest.mark.parametrize(
    "rel",
    [
        "engine/market_state.py",                              # from-import
        "research/prophet_us_audit/reclaim_veto_packet.py",    # __file__-rooted join
        "scripts/audit_unrun_tests.py",                        # whole-string literal
        "collectors/fred.py",                                  # import_module()
    ],
)
def test_a_real_read_is_found(fixture_reads, rel) -> None:
    assert rel in fixture_reads


# Written as SEGMENTS, not as whole-string paths, and not by accident: a bare
# "config/reflexes.yml" here is itself a whole-string path literal in a suite the
# workflow-yaml job runs, so the guard would (correctly) demand a trigger entry for
# a file this test never opens. Dogfooding — the guard flagged this file first.
@pytest.mark.parametrize(
    "segments,why",
    [
        (("config", "reflexes.yml"), "module docstring"),
        (("config", "clinical_modalities.yml"), "function docstring"),
        (("config", "trade_flow_codes.yml"), "comment"),
        (("config", "seasonality_universe.yml"), "path inside a sentence"),
        (("config", "brain.yml"), "tmp_path write"),
        (("config", "evidence_clock.yml"), "synthetic `root` base"),
    ],
)
def test_prose_and_synthetic_paths_are_not_reads(fixture_reads, segments, why) -> None:
    rel = "/".join(segments)
    assert (ROOT / rel).is_file(), f"{rel} must exist, or the trap it models cannot"
    assert rel not in fixture_reads, f"{why} must not count as a read of {rel}"


def test_a_path_that_is_not_in_the_tree_is_never_a_subject(fixture_reads) -> None:
    """It cannot be edited, so it can never be the module a PR touches."""
    assert not any("no_such_module_exists_here" in rel for rel in fixture_reads)


def test_reads_carry_provenance(fixture_reads) -> None:
    """A finding must say WHERE, or verifying one costs a grep per finding."""
    assert "line" in fixture_reads["engine/market_state.py"]


# ── 3. the incident shape ────────────────────────────────────────────────────

def test_the_reclaim_veto_suite_reads_the_engine_module_it_pins() -> None:
    """#4583/#4645: the packet pinned a copy of a constant this module owns.

    The closure has to SEE engine/signal_quality.py for the gate to have any
    opinion about it. If this resolution ever breaks, the gate goes quiet on the
    whole class rather than going red.
    """
    reads = GUARD.direct_reads(ROOT / "tests" / "test_us_reclaim_veto_packet.py")
    assert "engine/signal_quality.py" in reads
    assert "research/prophet_us_audit/reclaim_veto_packet.py" in reads


def test_dropping_a_subject_from_the_filter_is_a_gap_the_test_half_hides() -> None:
    """The trap, in one assertion.

    With the subject unlisted the suite is STILL reachable through its own file, so
    `audit_unrun_tests.py`'s any()-over-the-closure calls it triggerable and every
    census stays green — while a PR touching only the engine module never runs it.
    """
    suite = "tests/test_us_reclaim_veto_packet.py"
    subject = "engine/signal_quality.py"
    without = ["tests/**", "research/prophet_us_audit/reclaim_veto_packet.py"]

    assert GUARD.matched(suite, without) is True        # the suite looks covered …
    assert GUARD.matched(subject, without) is False     # … and its subject is not
    assert GUARD.matched(subject, [*without, "engine/**"]) is True


# ── 4. the guard is armed, wired, and currently clean ────────────────────────

def test_main_has_no_trigger_gap() -> None:
    """The gate, run for real. A new unreachable subject fails HERE, pre-merge."""
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        "scripts/check_ci_trigger_closure.py found a suite whose subject no path "
        "filter reaches:\n" + result.stdout + result.stderr
    )


def test_guard_selftest_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--selftest"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_guard_runs_in_a_ci_job() -> None:
    """An unrun guard is a comment with a shebang."""
    manifest = yaml.safe_load(MANIFEST.read_text())
    commands = {
        " ".join(str(step.get("run", "")).split())
        for job in manifest["jobs"].values()
        if isinstance(job, dict)
        for step in job.get("steps") or []
        if isinstance(step, dict)
    }
    for required in (
        "python scripts/check_ci_trigger_closure.py --selftest",
        "python scripts/check_ci_trigger_closure.py",          # the gate itself
        "python -m pytest tests/test_ci_trigger_closure.py -q",
    ):
        assert required in commands, f"no CI step runs `{required}`"


def test_both_halves_of_this_guard_can_start_ci() -> None:
    """The guard obeys its own rule — otherwise it is the thing it forbids.

    `scripts/*.py` already reaches the checker; the test half needs its own entry.
    """
    paths = _ci_paths()
    assert GUARD.matched("scripts/check_ci_trigger_closure.py", paths)
    assert GUARD.matched("tests/test_ci_trigger_closure.py", paths)


def test_annotations_start_the_line_and_flush() -> None:
    """A `::error` behind a logger's level prefix is silently dropped by GitHub.

    Five PRs shipped that defect here before tests/test_gh_annotation_line_start.py
    existed (#3487, #3515, #3562, #3563, #3570 → swept in #3587). This guard emits
    annotations on its failure path, so it re-pins the rule at the source.
    """
    tree = ast.parse(CHECKER.read_text())
    annotating = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and node.args
        and "::" in ast.dump(node.args[0])
    ]
    assert annotating, "the guard must emit GitHub annotations on its failure path"
    for node in annotating:
        assert any(kw.arg == "flush" for kw in node.keywords), (
            f"print() at line {node.lineno} emits an annotation without flush=True; "
            "stdout is block-buffered when piped in CI"
        )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"warning", "error", "info", "notice"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith("::")
        ):
            pytest.fail(
                f"line {node.lineno}: an annotation emitted through a logger is "
                "prefixed with the level and never parses"
            )
