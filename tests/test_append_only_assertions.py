"""tests/test_append_only_assertions.py — the append-only law's own proof.

A guard printing "0 violations" without demonstrated power to fail is not
evidence. Everything here is a NEGATIVE CONTROL: each test either mutates the
detector and proves --selftest goes red, or mutates a legal fixture into the
known-bad construction and proves it is caught. A rule that survives its
mutation is dead code, and this file says so by name.

The two motivating defects are pinned verbatim as source fixtures (defect 3's
`ledger_ids <= graded_ids` and defect 4's gate whose exit code is a function of
store content), so a regression that stops seeing either fails here.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = ROOT / "scripts" / "check_append_only_assertions.py"


def _load(source_path: Path, name: str = "aoa_guard"):
    spec = importlib.util.spec_from_file_location(name, source_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load(GUARD_PATH)

STORES = guard.SELFTEST_STORES


# --------------------------------------------------------------------------- #
# The selftest itself, run as a subprocess with a REAL exit code
# --------------------------------------------------------------------------- #
def test_selftest_passes_with_a_real_exit_code():
    proc = subprocess.run(
        [sys.executable, str(GUARD_PATH), "--selftest"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "known-bad constructions caught" in proc.stdout


def test_the_selftest_carries_enough_adversarial_material():
    assert len(guard.BAD_FIXTURES) >= 4, "fewer than 4 known-bad constructions"
    assert len(guard.GOOD_FIXTURES) >= 4, "fewer than 4 legal constructions"
    kinds = {kind for _, _, kind in guard.BAD_FIXTURES.values()}
    assert guard.KIND_EXIT in kinds, (
        "no known-bad fixture exercises the exit-code family — that is the exact "
        "shape the prior implementation was blind to"
    )
    assert guard.KIND_ASSERT in kinds


# --------------------------------------------------------------------------- #
# The two motivating defects, pinned verbatim
# --------------------------------------------------------------------------- #
DEFECT_3 = '''
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "data" / "prophet" / "ledger.jsonl"
SIDECAR = REPO / "docs" / "plan_grades.jsonl"

def test_every_closed_plan_is_accounted_for():
    ledger_ids = {str(r["id"]) for r in read_jsonl(LEDGER)}
    graded_ids = {str(r["id"]) for r in read_jsonl(SIDECAR)}
    assert ledger_ids and ledger_ids <= graded_ids, sorted(ledger_ids - graded_ids)
'''

DEFECT_4 = '''
import argparse, sys
from pathlib import Path
CLAIMS_REL = ("data", "qledger", "claims.jsonl")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    claims = _read_jsonl(args.root.joinpath(*CLAIMS_REL))
    findings = audit(claims)
    invalid = [f for f in findings if f.severity == "invalid"]
    if args.strict and invalid:
        return 1
    return 0
'''


def test_defect_3_the_upper_bound_over_a_live_ledger_is_caught():
    hits = guard.scan_source(DEFECT_3, "tests/x.py", STORES, False)
    assert hits, "the ledger_ids <= graded_ids defect was not caught"
    assert any(h.kind == guard.KIND_ASSERT and "LtE" in h.detail for h in hits)


def test_defect_4_a_gate_whose_exit_code_reads_the_store_is_caught():
    hits = guard.scan_source(DEFECT_4, "scripts/check_x.py", STORES, True)
    assert hits, (
        "a gate whose exit code is a function of append-only store content was "
        "NOT caught — this is the shape the prior implementation could not see"
    )
    assert any(h.kind == guard.KIND_EXIT for h in hits)


def test_defect_4_is_invisible_when_the_same_file_is_not_a_gate():
    """The exit-code family is scoped to gates ON PURPOSE. Pin the scoping."""
    assert not guard.scan_source(DEFECT_4, "scripts/build_x.py", STORES, False)


# --------------------------------------------------------------------------- #
# Path-shape coverage: both repo-root spellings, and the sandbox veto
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "root_expr",
    [
        'Path(__file__).resolve().parents[1]',
        'Path(__file__).resolve().parent.parent',
        'Path(__file__).parent.parent.resolve()',
    ],
)
def test_every_repo_root_spelling_resolves(root_expr):
    """The prior implementation only recognised the `parents[N]` shape."""
    source = f'''
from pathlib import Path
ROOT = {root_expr}

def test_x():
    rows = read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl")
    assert len(rows) == 28
'''
    assert guard.scan_source(source, "tests/x.py", STORES, False), (
        f"a repo root written as {root_expr} was not resolved"
    )


@pytest.mark.parametrize(
    "sandbox_expr",
    [
        "tmp_path",
        "Path(tempfile.mkdtemp())",
        "_make_fixture_root(tmp_path)",
        "tmp_path_factory.mktemp('x')",
    ],
)
def test_a_sandbox_root_is_never_reported(sandbox_expr):
    """The docstring's guarantee. The prior implementation broke its own here."""
    source = f'''
import tempfile
from pathlib import Path

def test_x(tmp_path, tmp_path_factory):
    root = {sandbox_expr}
    rows = read_jsonl(root / "data" / "prophet" / "ledger.jsonl")
    assert len(rows) == 28
'''
    hits = guard.scan_source(source, "tests/x.py", STORES, False)
    assert not hits, f"a {sandbox_expr} sandbox was reported: {[h.detail for h in hits]}"


# --------------------------------------------------------------------------- #
# MUTATION CONTROL 1 — mutate the detector, --selftest must go RED
# --------------------------------------------------------------------------- #
DETECTOR_MUTATIONS = {
    "nothing_is_ever_fragile": (
        "    if left and right and left == right:",
        "    if True:",
    ),
    "blind_to_exit_codes": (
        "    if isinstance(payload, ast.Constant):",
        "    if True:\n        return False, False\n    if isinstance(payload, ast.Constant):",
    ),
    "no_path_ever_resolves": (
        "    if candidate not in scope.stores:",
        "    if True:",
    ),
    "sandbox_veto_removed": (
        "        root_name in SANDBOX_ROOTS or root_name in scope.sandbox "
        "or root_name in scope.params",
        "        False",
    ),
    "schema_shape_unrecognised": (
        "def is_schema_shape(node: ast.AST) -> bool:",
        "def is_schema_shape(node: ast.AST) -> bool:\n    return False",
    ),
    "growth_immune_removed": (
        "def operand_is_growth_immune(node: ast.AST, scope: Scope) -> bool:",
        "def operand_is_growth_immune(node: ast.AST, scope: Scope) -> bool:\n    return False",
    ),
    "bounded_prefix_unrecognised": (
        "def _is_bounded_prefix(node: ast.AST) -> bool:",
        "def _is_bounded_prefix(node: ast.AST) -> bool:\n    return False",
    ),
    "a_path_never_becomes_content": (
        "    if paths and _performs_read(node, scope):",
        "    if False:",
    ),
    # The regression this guard found by running against ITSELF: seeding the
    # sandbox set with parameters made `args = parser.parse_args(argv)` a
    # sandbox, so `args.root.joinpath(...)` was invisible and a real gate passed.
    "parameters_seed_the_sandbox_again": (
        "        if _calls_sandbox(value) or (used & (SANDBOX_ROOTS | scope.sandbox)):",
        "        if _calls_sandbox(value) or "
        "(used & (SANDBOX_ROOTS | scope.sandbox | scope.params)):",
    ),
    "sandbox_stops_travelling_through_a_call": (
        "        if _calls_sandbox(value) or (used & (SANDBOX_ROOTS | scope.sandbox)):",
        "        if _is_path_algebra(value) and (used & (SANDBOX_ROOTS | scope.sandbox)):",
    ),
}


@pytest.mark.parametrize("name", sorted(DETECTOR_MUTATIONS))
def test_mutating_the_detector_makes_the_selftest_fail(name, tmp_path):
    old, new = DETECTOR_MUTATIONS[name]
    text = GUARD_PATH.read_text(encoding="utf-8")
    assert old in text, (
        f"mutation anchor for '{name}' is stale. An unapplied mutation leaves the "
        f"file clean, the selftest passes, and the rule reads as dead code — fix "
        f"the anchor rather than the assertion."
    )
    mutant = tmp_path / "mutant_guard.py"
    mutant.write_text(text.replace(old, new, 1), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(mutant), "--selftest"], capture_output=True, text=True
    )
    assert proc.returncode == 1, (
        f"mutation '{name}' SURVIVED the selftest (exit {proc.returncode}) — the rule "
        f"it disables is not covered by any fixture, i.e. it is dead code.\n"
        f"{proc.stdout}{proc.stderr}"
    )
    assert "::error" in proc.stdout


# --------------------------------------------------------------------------- #
# MUTATION CONTROL 2 — bend a LEGAL fixture into the known-bad construction
# --------------------------------------------------------------------------- #
FIXTURE_MUTATIONS = [
    ("floor", "assert len(rows) >= 28", "assert len(rows) == 28"),
    ("floor", "assert 28 <= len(rows)", "assert 28 >= len(rows)"),
    ("schema_keys_store_grain",
     "assert set(rows[0].keys()) == FIELDS", "assert len(rows) == 3"),
    ("within_run_byte_identity",
     "assert after == before", 'assert after == b"frozen"'),
    ("bounded_prefix", "incident_prefix = raw[:50_790]", "incident_prefix = raw"),
    ("per_row_schema", 'assert event["kind"] == "event"', "assert len(list(event)) == 41"),
    ("membership_in_store", 'assert "# ledger" in body', "assert body in FROZEN_BODIES"),
    ("gate_exit_on_config",
     'registry = load_yaml(ROOT / "config" / "house_law_checks.yml")',
     'registry = load_yaml(ROOT / "data" / "qledger" / "claims.jsonl")'),
    ("gate_reports_only",
     '            print("::warning title=qledger::row without an id", flush=True)',
     "            return 1"),
]


@pytest.mark.parametrize("name,old,new", FIXTURE_MUTATIONS)
def test_bending_a_legal_fixture_into_the_defect_is_caught(name, old, new):
    source, is_gate = guard.GOOD_FIXTURES[name]
    assert not guard.scan_source(source, f"tests/{name}.py", STORES, is_gate), (
        f"legal fixture '{name}' is not clean to begin with"
    )
    assert old in source, f"fixture-mutation anchor for '{name}' is stale: {old!r}"
    hits = guard.scan_source(source.replace(old, new, 1), f"tests/{name}.py", STORES, is_gate)
    assert hits, (
        f"bending '{name}' into the known-bad construction was NOT caught — the "
        f"detector is blind to that shape"
    )


# --------------------------------------------------------------------------- #
# The guard must not violate its own law, and must be POWERFUL over itself
# --------------------------------------------------------------------------- #
def test_the_guard_does_not_violate_its_own_law():
    stores = guard.load_stores(ROOT)
    if not stores:
        pytest.skip("config/synapse.yml unreadable in this checkout")
    rel = "scripts/check_append_only_assertions.py"
    hits = guard.scan_source(GUARD_PATH.read_text(encoding="utf-8"), rel, stores, True)
    assert not hits, f"the guard breaks its own law: {[(h.line, h.detail) for h in hits]}"


def test_that_clean_result_is_not_a_silent_skip():
    """A guard that cannot see itself would also report zero. Prove it can."""
    stores = guard.load_stores(ROOT)
    if not stores:
        pytest.skip("config/synapse.yml unreadable in this checkout")
    text = GUARD_PATH.read_text(encoding="utf-8")
    anchor = "    if args.selftest:\n        return selftest()\n"
    assert anchor in text
    planted = text.replace(
        anchor,
        anchor
        + '\n    _rows = (args.root / "data" / "qledger" / "claims.jsonl")'
        ".read_text().splitlines()\n    if len(_rows) != 28:\n        return 1\n",
        1,
    )
    hits = guard.scan_source(planted, "scripts/check_append_only_assertions.py", stores, True)
    assert any(h.kind == guard.KIND_EXIT for h in hits), (
        "a violation planted in the guard itself was not caught, so the guard's own "
        "clean result is a silent skip rather than a pass"
    )


# --------------------------------------------------------------------------- #
# Hygiene the prior implementation failed
# --------------------------------------------------------------------------- #
def test_no_dead_code():
    """Every helper defined is called. The prior version shipped two that were not."""
    tree = ast.parse(GUARD_PATH.read_text(encoding="utf-8"))
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    upper = {
        t.id
        for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()
    }
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            used.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    assert not (defined - used - {"main"}), f"dead functions: {defined - used - {'main'}}"
    assert not (upper - used), f"dead constants: {upper - used}"


def test_annotations_start_the_line_and_flush():
    """CLAUDE.md §GitHub annotations must START the line — never via a logger."""
    text = GUARD_PATH.read_text(encoding="utf-8")
    assert "logging" not in text and "log." not in text
    tree = ast.parse(text)
    emitted = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"):
            continue
        if not node.args:
            continue
        rendered = ast.unparse(node.args[0])
        if "::error" in rendered or "::warning" in rendered or "::notice" in rendered:
            emitted += 1
            assert rendered.lstrip("f'\"").startswith("::"), (
                f"annotation does not start the line: {rendered[:70]}"
            )
            assert any(
                kw.arg == "flush" and kw.value.value is True for kw in node.keywords
            ), f"annotation is not flushed (stdout is block-buffered in CI): {rendered[:70]}"
    assert emitted >= 3


def test_cadence_rule_does_not_regress_to_the_word_nightly():
    """Both motivating stores are 'daily-engine'. A "nightly" grep catches ZERO."""
    assert "daily-engine" in guard.NIGHTLY_CADENCES
    stores = guard.load_stores(ROOT)
    if not stores:
        pytest.skip("config/synapse.yml unreadable in this checkout")
    assert "data/qledger/claims.jsonl" in stores
    assert "data/prophet/ledger.jsonl" in stores
    assert not any("nightly" in s.why for s in (
        stores["data/qledger/claims.jsonl"], stores["data/prophet/ledger.jsonl"]
    ))


def test_json_output_is_parseable_and_names_the_kind():
    proc = subprocess.run(
        [sys.executable, str(GUARD_PATH), "--json", "--root", str(ROOT)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    import json

    payload = json.loads(proc.stdout)
    assert payload["stores"] > 0
    for finding in payload["findings"]:
        assert finding["kind"] in {guard.KIND_ASSERT, guard.KIND_EXIT}
        assert finding["store"].startswith("data/")
