"""The unrun-test census: it must see suites wherever they live, and only suites.

WHAT THIS PINS.  `scripts/audit_unrun_tests.py` owns test discovery for all three
darkness guards (`check_skip_only_suites.py` and `check_ci_trigger_closure.py` both
import from it rather than re-implementing the repo layout).  Until 2026-08-06 that
discovery was `TESTS.glob("test_*.py")` — hard-scoped to `tests/` — so a suite
written anywhere else was invisible to every census at once.

WHY THAT SCOPE WAS EXACTLY BACKWARDS.  Research packets here are routinely fenced to
files-only, so a packet's guard suite gets written NEXT TO its instrument under
`research/` instead of in `tests/`.  Those are the suites most likely to be dark, and
they were the ones no census could see: measured in #4693,
`research/prophet_us_audit/test_label_grading_battery.py` (16 tests) and
`research/signal_engine/test_buy_filters.py` (6 tests) had been named by no `run:`
step since they landed, while every census reported the repo covered.

THE OTHER HALF, AND WHY IT IS A TEST AND NOT A COMMENT.  Widening by FILENAME would
have replaced a blind census with a noisy one: three `test_`-shaped files under
`research/` are CLI measurement instruments that collect zero tests, and `pytest`
exits 5 on each.  Reporting those as unrun work items is how a census stops being
read — the failure mode `check_ci_trigger_closure.py`'s docstring says these guards
exist to end.  So classification asks pytest's question (does the file define a
`test*` function, or a `Test*` class holding one), and the tests below pin BOTH
directions against real collection.

Run: python3 -m pytest tests/test_audit_unrun_tests.py -q
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CENSUS = ROOT / "scripts" / "audit_unrun_tests.py"
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"

_SPEC = importlib.util.spec_from_file_location("audit_unrun_tests", CENSUS)
assert _SPEC and _SPEC.loader
GUARD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = GUARD
_SPEC.loader.exec_module(GUARD)

# The three CLI measurement instruments. Each has a `def main()` behind an
# `if __name__ == "__main__"` and no test functions; `pytest` exits 5 on each.
INSTRUMENTS = (
    "research/cn_prophet_audit/sector_intel_exante_test.py",
    "research/signal_engine/test_breadth_consume.py",
    "research/signal_engine/test_buyfilter.py",
)

# The real suites that live outside tests/ — the reason the widening exists.
OUTSIDE_TESTS = (
    "research/prophet_us_audit/test_label_grading_battery.py",
    "research/signal_engine/test_buy_filters.py",
    "scripts/research/test_run_w4_controls_fingerprints.py",
)

_SUITE = "def test_thing():\n    assert True\n"
_CLASS_SUITE = "class TestBattery:\n    def test_case(self):\n        assert True\n"
_INSTRUMENT = (
    "import sys\n\n\n"
    "def main(argv=None):\n"
    "    return 0\n\n\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main(sys.argv[1:]))\n"
)


# ── 1. classification agrees with pytest, in both directions ─────────────────

@pytest.mark.parametrize("rel", INSTRUMENTS)
def test_a_test_shaped_cli_instrument_is_not_a_suite(rel: str) -> None:
    """Ground truth, not a heuristic: `pytest` exits 5 (no tests collected) here.

    A filename heuristic would report all three as unrun work items every run.
    """
    path = ROOT / rel
    assert path.is_file(), f"{rel} moved; re-derive the classification it pins"
    assert GUARD.defines_tests(path) is False

    result = subprocess.run(
        [sys.executable, "-m", "pytest", rel, "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    # rc 0 means pytest collected at least one item — the one outcome that would
    # falsify the classification above. rc 5 is "no tests collected" (the local,
    # full-dependency answer); rc 4 is a collection error, which these three can
    # reach in a thin CI lane because they import pandas/engine at module scope.
    # Both still collect zero tests, so the assertion is on the falsifier, not on a
    # specific code — a ground-truth check that reds on a missing dependency would
    # be a spurious gate, not a stronger one.
    assert result.returncode != 0, (
        f"pytest collected tests from {rel}, so it IS a suite and defines_tests() "
        f"must say so:\n{result.stdout}"
    )
    if result.returncode == 5:
        assert "no tests collected" in result.stdout


@pytest.mark.parametrize("rel", OUTSIDE_TESTS)
def test_a_real_suite_outside_tests_is_a_suite(rel: str) -> None:
    path = ROOT / rel
    assert path.is_file(), f"{rel} moved; update OUTSIDE_TESTS"
    assert GUARD.defines_tests(path) is True
    assert rel in GUARD.discover_suites()


def test_class_based_and_async_suites_count(tmp_path: Path) -> None:
    """pytest's defaults are `python_classes = Test*` / `python_functions = test*`.

    The battery suite that motivated this work is class-based
    (`TestStatsGuards::test_stats_block_handles_an_empty_cell`), so a
    module-level-functions-only classifier would have called it an instrument.
    """
    for name, body in (
        ("test_class.py", _CLASS_SUITE),
        ("test_async.py", "async def test_thing():\n    assert True\n"),
        ("test_camel.py", "def testCamelCase():\n    assert True\n"),
    ):
        assert GUARD.defines_tests(_write(tmp_path / name, body)) is True

    # A Test* class with no test methods collects nothing, and neither does a
    # helper that merely IMPORTS pytest.
    assert GUARD.defines_tests(
        _write(tmp_path / "test_empty_class.py",
               "class TestHelpers:\n    def build(self):\n        return 1\n")
    ) is False
    assert GUARD.defines_tests(
        _write(tmp_path / "test_helper.py", "import pytest\n\nX = 1\n")
    ) is False


def test_an_unparseable_file_is_treated_as_a_suite(tmp_path: Path) -> None:
    """pytest ERRORS at collection on it — louder than a miscounted census row.

    Over-including is the safe direction: two consumers only report, and the third
    fails only on a suite some job actually names.
    """
    assert GUARD.defines_tests(
        _write(tmp_path / "test_broken.py", "def test_x(:\n")
    ) is True


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


# ── 2. discovery reaches the whole tree, and stops at its edges ──────────────

@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """A synthetic checkout, discovered through the WALK branch.

    `_tracked_candidates` is forced to None so this exercises the fallback; the
    git branch is covered against the real repo by the tests below.
    """
    for rel, body in (
        ("tests/test_in_tests.py", _SUITE),
        ("research/packet/test_beside_the_instrument.py", _SUITE),
        ("research/packet/test_class_based.py", _CLASS_SUITE),
        ("research/packet/test_instrument.py", _INSTRUMENT),
        ("research/packet/sector_exante_test.py", _INSTRUMENT),
        ("research/packet/helper.py", _SUITE),
        ("scripts/research/test_nested.py", _SUITE),
        (".claude/worktrees/other/tests/test_someone_elses.py", _SUITE),
        (".codex-worktrees/x/tests/test_other_fleet.py", _SUITE),
        ("node_modules/pkg/test_vendored.py", _SUITE),
        (".venv/lib/site-packages/dep/test_dependency.py", _SUITE),
    ):
        _write(tmp_path / rel, body)
    monkeypatch.setattr(GUARD, "_tracked_candidates", lambda root: None)
    monkeypatch.setattr(GUARD, "ROOT", tmp_path)
    return set(GUARD.discover_suites())


@pytest.mark.parametrize(
    "rel",
    [
        "tests/test_in_tests.py",
        "research/packet/test_beside_the_instrument.py",   # the #4693 shape
        "research/packet/test_class_based.py",
        "scripts/research/test_nested.py",                 # nested, not just top level
    ],
)
def test_a_seeded_suite_outside_tests_is_discovered(seeded: set[str], rel: str) -> None:
    """The mutation, as a test: seed a suite outside tests/, the census must see it."""
    assert rel in seeded


@pytest.mark.parametrize(
    "rel,why",
    [
        ("research/packet/test_instrument.py", "a CLI instrument collects nothing"),
        ("research/packet/sector_exante_test.py", "…including the *_test.py spelling"),
        ("research/packet/helper.py", "not a pytest filename shape"),
        (".claude/worktrees/other/tests/test_someone_elses.py",
         "another session's worktree is not this repo's source"),
        (".codex-worktrees/x/tests/test_other_fleet.py", "nor another fleet's"),
        ("node_modules/pkg/test_vendored.py", "nor vendored code"),
        (".venv/lib/site-packages/dep/test_dependency.py", "nor an installed dependency"),
    ],
)
def test_discovery_stops_at_the_repo_edge(seeded: set[str], rel: str, why: str) -> None:
    assert rel not in seeded, why


def test_a_pruned_walk_is_not_a_bare_rglob() -> None:
    """The single most expensive way to get this wrong.

    The primary checkout carries ~357k test-shaped files under `.claude/worktrees/`;
    an unpruned walk turns a 2,017-row census into a 368,938-row one, and a census
    that large is noise. The exclusion list is load-bearing, not decorative.
    """
    for name in (".claude", ".codex-worktrees", "node_modules", "site-packages",
                 ".venv", "__pycache__"):
        assert name in GUARD.EXCLUDED_DIRS


def test_the_non_suites_are_reported_not_silently_dropped() -> None:
    """No silent caps: a reader grepping for one of these must find out WHY."""
    reported = set(GUARD.not_a_suite())
    for rel in INSTRUMENTS:
        assert rel in reported
    assert reported.isdisjoint(set(GUARD.discover_suites()))


# ── 3. the two discovery branches agree on the real repo ─────────────────────

def test_git_and_walk_discovery_agree_on_the_real_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`git ls-files` is the inventory; the walk is the fallback for a tree git
    cannot read. If they disagree, one of them is lying about what is in the repo.
    """
    GUARD._classify.cache_clear()
    via_git = set(GUARD.discover_suites())
    monkeypatch.setattr(GUARD, "_tracked_candidates", lambda root: None)
    GUARD._classify.cache_clear()
    via_walk = set(GUARD.discover_suites())
    GUARD._classify.cache_clear()

    assert via_git, "git ls-files returned no suites at all"
    # The walk additionally sees untracked-but-unignored files; anything git knows
    # about must be in the walk's answer.
    assert via_git <= via_walk, sorted(via_git - via_walk)[:10]


# ── 4. the census is armed, wired, and still tree-wide ───────────────────────

@pytest.fixture(scope="module")
def census_rows() -> list[dict]:
    """One census for the whole module — a full run parses every suite in the tree."""
    return GUARD.census()


def test_census_rows_are_repo_relative_paths(census_rows: list[dict]) -> None:
    """Basenames were ambiguous the moment scope left tests/."""
    assert census_rows
    assert all("/" in row["test"] for row in census_rows)
    assert all((ROOT / row["test"]).is_file() for row in census_rows)


def test_the_census_reports_the_suites_outside_tests(census_rows: list[dict]) -> None:
    """The regression this whole change exists to prevent."""
    rows = {row["test"] for row in census_rows}
    discovered = set(GUARD.discover_suites())
    for rel in OUTSIDE_TESTS:
        assert rel in discovered
    assert rows & set(OUTSIDE_TESTS), (
        "no research/-resident suite reads as UNRUN; if they were all wired, drop "
        "this assertion — but verify the wiring first, do not weaken the census"
    )


def test_census_selftest_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CENSUS), "--selftest"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_census_runs_in_a_ci_job() -> None:
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
        "python scripts/audit_unrun_tests.py --selftest",
        # The BARE run — the armed gate, not the selftest and not the unit tests.
        # Matched by content and never by line number: the three steps sit next to
        # each other and a positional assertion would pass on the wrong one.
        "python scripts/audit_unrun_tests.py",
        "python -m pytest tests/test_audit_unrun_tests.py -q",
    ):
        assert required in commands, f"no CI step runs `{required}`"


# ── 5. the gate: reds the new, grandfathers the backlog, honours the waivers ──
#
# Armed 2026-08-09. The census reported for three weeks and the backlog did not move
# (969 unrun of 2,146), while six PRs each un-darkened ONE suite by hand. These pin
# the ratchet in both directions: a suite in neither file must RED, and a suite in
# either file must not — including on the branch that wires or deletes it, which is
# why every stale row warns instead.

NEW = "research/packet/test_newly_dark.py"
OLD = "tests/test_grandfathered.py"


def _lines(capsys) -> list[str]:
    out = capsys.readouterr()
    return (out.out + out.err).splitlines()


def _starts(lines: list[str], prefix: str) -> bool:
    """House law: an annotation with ANYTHING in front of it is silently dropped."""
    return any(line.startswith(prefix) for line in lines)


def test_gate_reds_a_suite_in_neither_file(capsys: pytest.CaptureFixture) -> None:
    """The whole point: the 970th dark suite cannot ship silently."""
    assert GUARD.gate([NEW], set(), {}, {NEW}) == 1
    assert _starts(_lines(capsys), "::error title=unrun-suite::")


@pytest.mark.parametrize(
    "baseline,waivers,why",
    [
        ({NEW}, {}, "grandfathered: the backlog is triage input, not a to-do list"),
        (set(), {NEW: "owner + argument"}, "waived with a reason"),
    ],
)
def test_gate_clears_a_known_unrun_suite(baseline, waivers, why: str) -> None:
    assert GUARD.gate([NEW], baseline, waivers, {NEW}) == 0, why


def test_a_live_waiver_reprints_its_reason(capsys: pytest.CaptureFixture) -> None:
    """A waiver only stays honest while its argument is in front of the reader."""
    assert GUARD.gate([NEW], set(), {NEW: "the engine constant is stale"}, {NEW}) == 0
    assert any("the engine constant is stale" in line for line in _lines(capsys))


@pytest.mark.parametrize(
    "baseline,waivers,prefix",
    [
        ({OLD}, {}, "::warning title=stale-unrun-baseline::"),
        (set(), {OLD: "why"}, "::warning title=stale-unrun-waiver::"),
    ],
)
def test_a_stale_row_warns_and_never_reds(
    capsys: pytest.CaptureFixture, baseline, waivers, prefix: str
) -> None:
    """The suite got WIRED. Reding here would punish the branch that fixed it."""
    assert GUARD.gate([], baseline, waivers, {OLD}) == 0
    assert _starts(_lines(capsys), prefix)


def test_a_suite_in_both_files_warns_about_the_duplication(
    capsys: pytest.CaptureFixture,
) -> None:
    """The waiver carries the reason, so it wins and the baseline row is the dupe."""
    assert GUARD.gate([NEW], {NEW}, {NEW: "why"}, {NEW}) == 0
    assert _starts(_lines(capsys), "::warning title=stale-unrun-baseline::")


@pytest.mark.parametrize(
    "waivers,why",
    [
        (["not", "a", "mapping"], "a list is not a suite path -> reason mapping"),
        ({NEW: ""}, "an empty reason is a baseline row wearing a disguise"),
        ({NEW: 232}, "a non-string reason carries no argument"),
        ({NEW: "   "}, "nor does whitespace"),
    ],
)
def test_malformed_waivers_are_a_hard_red(
    capsys: pytest.CaptureFixture, waivers, why: str
) -> None:
    """Fail-closed, and fail LOUD: silently ignoring the file would red every waived
    suite at once and bury the actual complaint under the noise."""
    assert GUARD.gate([NEW], {NEW}, waivers, {NEW}) == 1, why
    assert _starts(_lines(capsys), "::error title=unrun-waivers-malformed::")


def test_an_unparseable_waivers_file_is_a_hard_red(
    capsys: pytest.CaptureFixture,
) -> None:
    assert GUARD.gate([NEW], {NEW}, GUARD._Unparseable("boom"), {NEW}) == 1
    assert _starts(_lines(capsys), "::error title=unrun-waivers-malformed::")


def test_a_shared_basename_does_not_cover_a_sibling_suite() -> None:
    """Measured 2026-08-09, and the reason this matcher is path-first.

    `test_price_ladder.py` exists twice — in `tests/` and in
    `research/prophet_us_audit/`. Both were unrun, so the collision was inert until
    the research one was wired into signal-contract; the basename fallback then
    reported the `tests/` one as COVERED with nothing running it, which is this
    census's own failure mode. An ambiguous basename demands the full path.
    """
    blob = "python -m pytest research/prophet_us_audit/test_price_ladder.py -q"
    ambiguous = frozenset({"test_price_ladder.py"})
    assert GUARD._named_by_a_run_step(
        "research/prophet_us_audit/test_price_ladder.py", blob, ambiguous) is True
    assert GUARD._named_by_a_run_step(
        "tests/test_price_ladder.py", blob, ambiguous) is False
    # …and an UNambiguous basename still matches, so a `cd`-then-bare-name step
    # does not start reporting false darkness.
    assert GUARD._named_by_a_run_step(
        "tests/test_solo.py", "pytest test_solo.py", frozenset()) is True


# ── 6. both files parse, and mean what the gate reads ────────────────────────

def test_the_baseline_is_a_sorted_unique_list_of_repo_relative_paths() -> None:
    """Deterministic output is what makes `--write-baseline` reviewable in a diff."""
    doc = json.loads((ROOT / "config/unrun_test_baseline.json").read_text())
    rows = doc["grandfathered"]
    assert isinstance(rows, list) and rows
    assert all(isinstance(r, str) and "/" in r for r in rows)
    assert rows == sorted(rows), "regenerate with --write-baseline; do not hand-edit"
    assert len(set(rows)) == len(rows)
    assert doc["_frozen"] and doc["_note"], "the shrink-only policy must travel with it"


def test_the_waivers_file_maps_paths_to_nonempty_reasons() -> None:
    """The schema the gate enforces at runtime, pinned as a file-shape too."""
    raw = yaml.safe_load((ROOT / "config/unrun_test_waivers.yml").read_text()) or {}
    assert isinstance(raw, dict)
    normalized, problems = GUARD._validate_waivers(raw)
    assert not problems, problems
    assert normalized == raw or all(normalized[k] == v.strip() for k, v in raw.items())


def test_the_two_exception_files_do_not_overlap() -> None:
    """A waived suite is excluded from the baseline by --write-baseline; if both
    name it, one of them is a leftover and the gate is warning about it."""
    baseline = set(json.loads(
        (ROOT / "config/unrun_test_baseline.json").read_text())["grandfathered"])
    waived = set(yaml.safe_load(
        (ROOT / "config/unrun_test_waivers.yml").read_text()) or {})
    assert not (baseline & waived), sorted(baseline & waived)


def test_annotations_start_the_line_and_flush() -> None:
    """House law: `::error` behind a logger's level prefix is silently dropped.

    Five PRs shipped that defect here (#3487, #3515, #3562, #3563, #3570 → swept in
    #3587). This census emits annotations from its selftest, so it re-pins the rule.
    """
    tree = ast.parse(CENSUS.read_text())
    annotating = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and node.args
        and "::" in ast.dump(node.args[0])
    ]
    assert annotating, "the selftest must emit GitHub annotations on its failure path"
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
