#!/usr/bin/env python3
"""scripts/check_append_only_assertions.py — the append-only assertion law.

THE LAW
-------
    A historical assertion over an append-only store must not become false
    merely because a VALID NEW ROW was appended.

THE DEFECT THIS EXISTS TO STOP
------------------------------
A test or gate pins the CONTENT of a store that a nightly lane appends to. It is
green the day it is written and it reds main days or weeks later with no PR
author involved, so it gets routed around rather than obeyed. It has now shipped
FOUR times, each time by a different builder that had been warned about it in
prose in its own brief:

  1. scripts/check_intelligence_registry.py pinned a generated doc by equality
     while the registry derived from data/qledger/claims.jsonl.
  2. The same pin was RELOCATED to config/synapse.yml instead of removed.
  3. tests/test_prophet_plan_grades.py:376 asserts ``ledger_ids <= graded_ids``
     over the live data/prophet/ledger.jsonl against a frozen committed sidecar.
  4. A gate was promoted to HARD whose EXIT CODE is a function of
     data/qledger/claims.jsonl content — and the law shipped in the same commit
     was structurally blind to it, because it only ever examined ``ast.Assert``
     nodes containing an ``ast.Compare``.

Prose did not prevent any of them. This is the mechanical form, and it is built
to see #4 as readily as #3.

WHAT COUNTS AS AN APPEND-ONLY STORE (derived, never hand-listed)
---------------------------------------------------------------
A ``data/**`` JSONL artifact in ``config/synapse.yml`` with ``format: jsonl`` and
``storage: git``, plus either:

  SIGNAL A — a ``cadence`` naming a nightly/daily lane. NOTE that neither
     motivating store's cadence contains the word "nightly": data/qledger/
     claims.jsonl and data/prophet/ledger.jsonl are both ``daily-engine``. A rule
     grepping for "nightly" would classify ZERO of the four defects.
  SIGNAL B — the entry's own prose declaring the property ("append-only",
     "never truncate/overwrite", "sole future advancer"). This catches a store
     whose cadence is odd but which the registry itself says only ever grows.

Measured on this tree: 108 stores classified, 93 by Signal A and 15 by Signal B
(``--list-stores``). Nothing here reads a store's CONTENT — the guard is a pure
source scanner, so it behaves identically in a sparse worktree where ``data/``
is not checked out.

WHAT COUNTS AS AN ILLEGAL CONSTRUCTION
--------------------------------------
Not "an equality" — the rule is MONOTONICITY: illegal iff APPENDING A ROW can
falsify it. That is what separates the four real defects from the many
lexically-similar legal assertions in the tree:

    len(rows) == 28              FRAGILE  (defect 4, verbatim)
    ledger_ids <= graded_ids     FRAGILE  (defect 3, verbatim — an upper bound)
    len(rows) >= 28              SAFE     (a floor only ever grows)
    "HEADER" in body             SAFE     (a row cannot un-appear)
    set(row.keys()) == FIELDS    SAFE     (schema; the row count is irrelevant)
    row["kind"] == "event"       SAFE     (per-row contract; a VALID row satisfies it)
    raw[:50_790]                 SAFE     (a constant-bounded prefix cannot move)
    after == before              SAFE     (two reads of the SAME store, one run)

Two families are reported:

  ASSERTION — an ``assert``/``self.assertX`` comparison over store content.
  EXIT_CODE — a GATE whose failing exit is control-dependent on store content,
     or whose exit code is computed from it. Scoped to ``scripts/check_*.py``
     plus every ``check_script`` in config/house_law_checks.yml: a build script
     that exits 1 is one job's problem, a gate that exits 1 is the whole fleet's,
     with no PR author to fix it.

FALSE-POSITIVE MODES — OBSERVED, not assumed (each was opened and read)
-----------------------------------------------------------------------
* PRODUCER SIBLING. Comparing a store to a receipt written by the SAME producer
  run is safe: both move in lockstep. tests/test_chronicle.py:2294 asserts
  ``receipt.get("rows") == rows`` against data/chronicle/manifest.json, and is
  reported. Verified from the git objects: the manifest records rows=5051 and
  events.jsonl is 5051 lines. Closing this needs a ``producer:`` sibling lookup.
* WITHIN-RUN VIA AN INTERMEDIARY. One side reaches the store through a call the
  scanner cannot see into. tests/test_personality_relief_hazard.py:400 asserts
  ``state["ledger"]["events"] == len(events)`` where ``state`` comes back from
  ``prh.update(...)`` over the same ledger, so both sides move together; only
  ``events`` carries taint, so it is reported.
* FROZEN FIRST ROW. ``registration, *events = rows`` makes ``registration`` row
  0, which an append cannot change; the pin at
  tests/test_personality_relief_hazard.py:357 is reported anyway. (The BYTE
  form of this — ``raw[:50_790]`` — IS recognised and is not reported; see
  _is_bounded_prefix.)
* EXECUTION ORDER. Taint is a fixpoint over each scope and ignores statement
  order, so a name reassigned after the assert can back-taint it.

FALSE-NEGATIVE MODES — OBSERVED
-------------------------------
* UNREGISTERED STORE. A live append-only store missing from config/synapse.yml
  is invisible. Verified example: data/basket_turn/ledger.jsonl is tracked in
  git and read by tests/test_basket_membership_stamps.py:44, which pins
  ``assert len(live) == 8`` at line 259 — and this guard reports ZERO findings
  in that file, because synapse.yml registers data/us_basket_turn/ledger.jsonl
  and data/china_basket_turn/ledger.jsonl but not that path.
* ROW-GRAIN MEMBERSHIP. The per-row carve-out cannot tell a schema contract
  (``row["kind"] == "event"``, legal) from an enumeration of existing ids
  (``row["id"] in FROZEN_IDS``, fragile) — they are lexically identical. The
  carve-out wins, so the second is missed. Chosen deliberately: all four
  motivating defects are whole-store, and without it the guard reports ~5x the
  findings it can justify.
* INDIRECTION. A path arriving via a fixture, another module's constant, or
  ``getattr`` is not resolved. Resolution needs the store's own tail segments to
  appear as string constants in the expression.
* NON-JSONL. parquet/csv/json append-only artifacts are out of scope; all four
  real defects were JSONL and widening costs precision.
* A PARAMETER-ROOTED PATH is vetoed as a store base, so a helper that takes the
  live store as an argument is not judged at its own assert sites.

SEVERITY: discipline, ci_wiring [] — ON PURPOSE
-----------------------------------------------
It fires on pre-existing code that no PR author wrote (47 findings on this tree
at the time of writing), so wiring it as a gate on day one is how a guard gets
disabled instead of obeyed. CI proves the guard WORKS — its ``--selftest``
carries 7 known-bad constructions that must be caught and 13 legal ones that
must stay clean, and tests/test_append_only_assertions.py mutates the detector
and the fixtures to prove each rule is load-bearing. It does not yet judge the
tree. The promotion plan is in the registry entry.

Annotations use a bare ``print`` with ``flush=True`` per CLAUDE.md §"GitHub
annotations must START the line" — a logger would prefix the line and GitHub
would silently drop it.

Usage
-----
  python3 scripts/check_append_only_assertions.py [--root PATH] [--strict] [--json]
  python3 scripts/check_append_only_assertions.py --list-stores
  python3 scripts/check_append_only_assertions.py --selftest
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a hard dep of every CI lane
    yaml = None  # type: ignore[assignment]

SYNAPSE_REL = ("config", "synapse.yml")
REGISTRY_REL = ("config", "house_law_checks.yml")
SCAN_DIRS = ("tests", "scripts")
SKIP_PARTS = ("/fixtures/", "/golden/", "/goldens/")

# Cadence values that name a nightly / daily engine lane. NEITHER motivating
# defect's store says "nightly": data/qledger/claims.jsonl and
# data/prophet/ledger.jsonl are both 'daily-engine'. A rule that grepped for
# the word "nightly" would classify ZERO of the four known defects.
NIGHTLY_CADENCES = frozenset(
    {
        "daily-engine",
        "nightly-cortex",
        "nightly-factor-panel",
        "nightly-sec",
        "theta-ops-nightly",
        "asia-close",
    }
)

# Signal B: the registry's own prose declaring the property.
APPEND_ONLY_PROSE = re.compile(
    r"append[-\s]only|appended only|never truncat|never overwrit|sole (?:future )?advancer",
    re.IGNORECASE,
)

# pytest / unittest sandbox roots. A path hung off one of these is a temporary
# directory, so no amount of nightly appending can reach it.
SANDBOX_ROOTS = frozenset(
    {"tmp_path", "tmpdir", "tmp_path_factory", "tmpdir_factory", "tmp_dir", "tmpdir_path"}
)

# The stdlib spelling of the same thing. tests/test_whitehouse_w5.py builds its
# sandbox as `d = Path(tempfile.mkdtemp())`, which is a temp dir by construction
# and carries none of the fixture names above.
SANDBOX_CALLS = frozenset({"mkdtemp", "mkstemp", "TemporaryDirectory", "NamedTemporaryFile"})

# Calls that turn a path into CONTENT.
READ_CALLS = frozenset(
    {
        "read_text", "read_bytes", "readlines", "read", "open", "load", "loads",
        "read_jsonl", "load_jsonl", "read_json", "read_csv", "read_parquet",
        "iter_rows", "iter_jsonl", "readline",
    }
)

# Path algebra: the result is still a PATH, never content.
PATH_METHODS = frozenset(
    {"resolve", "absolute", "joinpath", "with_suffix", "with_name", "expanduser",
     "relative_to", "as_posix", "__truediv__"}
)

# Metadata about a path. Appending a row cannot falsify `.exists()`, and a
# directory listing is not the content of a file, so both drop the taint.
STAT_METHODS = frozenset(
    {"exists", "is_file", "is_dir", "is_symlink", "stat", "glob", "rglob",
     "iterdir", "mkdir", "unlink", "touch"}
)

# unittest-style assertions mapped onto the ast operator they mean, so the
# monotonicity rule judges them identically to a bare `assert a == b`.
ASSERT_METHODS: dict[str, type] = {
    "assertEqual": ast.Eq,
    "assertEquals": ast.Eq,
    "assertSetEqual": ast.Eq,
    "assertListEqual": ast.Eq,
    "assertDictEqual": ast.Eq,
    "assertCountEqual": ast.Eq,
    "assertLess": ast.Lt,
    "assertLessEqual": ast.LtE,
    "assertGreater": ast.Gt,
    "assertGreaterEqual": ast.GtE,
    "assertIn": ast.In,
    "assertNotIn": ast.NotIn,
}

KIND_ASSERT = "assertion"
KIND_EXIT = "exit_code"


@dataclass(frozen=True)
class Store:
    path: str
    signal: str
    why: str


@dataclass(frozen=True)
class Hit:
    file: str
    line: int
    kind: str
    store: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "kind": self.kind,
            "store": self.store,
            "detail": self.detail,
        }


@dataclass
class Scope:
    """Everything the resolver and the taint fixpoint need for one function body."""

    stores: dict[str, Store]
    consts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sandbox: set[str] = field(default_factory=set)
    # Function parameters. Vetoed as a store BASE (a caller chose that path), but
    # deliberately NOT a propagation seed: `args = parser.parse_args(argv)` must
    # not make `args.root` invisible, which is how this guard first passed its
    # own law for the wrong reason.
    params: set[str] = field(default_factory=set)
    path_taint: dict[str, set[str]] = field(default_factory=dict)
    content_taint: dict[str, set[str]] = field(default_factory=dict)
    # Names bound by `for row in <store content>`: their value is ONE ROW, not
    # the store. See operand_is_growth_immune.
    row_names: set[str] = field(default_factory=set)
    # Names bound to a constant-bounded PREFIX of store content (`raw[:50_790]`).
    # Appending cannot change the first N bytes/rows, so a pin on one is legal.
    prefix_names: set[str] = field(default_factory=set)


# --------------------------------------------------------------------------- #
# Store classification (Signal A = nightly-lane cadence, Signal B = own prose)
# --------------------------------------------------------------------------- #
def load_stores(root: Path) -> dict[str, Store]:
    """Return {repo-relative path -> Store} for every append-only JSONL artifact."""
    if yaml is None:
        return {}
    synapse = root.joinpath(*SYNAPSE_REL)
    if not synapse.exists():
        return {}
    try:
        doc = yaml.safe_load(synapse.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    out: dict[str, Store] = {}
    for name, entry in (doc.get("artifacts") or {}).items():
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if not path.startswith("data/") or not path.endswith(".jsonl"):
            continue
        if entry.get("format") != "jsonl" or entry.get("storage") != "git":
            continue
        cadence = str(entry.get("cadence") or "")
        if cadence in NIGHTLY_CADENCES:
            out[path] = Store(path, "A", f"synapse.yml[{name}] cadence={cadence}")
            continue
        prose = " ".join(
            str(entry.get(k) or "") for k in ("notes", "known_extra_writers", "summary")
        )
        if APPEND_ONLY_PROSE.search(prose):
            out[path] = Store(path, "B", f"synapse.yml[{name}] declares append-only in prose")
    return out


def load_gate_scripts(root: Path) -> set[str]:
    """Repo-relative paths of scripts that are CI gates (their exit code is law).

    Every ``scripts/check_*.py`` plus every ``check_script`` registered in
    config/house_law_checks.yml. The exit-code rule applies only to these: a
    build script that exits 1 is one job's problem, a gate that exits 1 is the
    whole fleet's, with no PR author to fix it.
    """
    gates = {
        p.relative_to(root).as_posix()
        for p in sorted((root / "scripts").glob("check_*.py"))
    }
    registry = root.joinpath(*REGISTRY_REL)
    if yaml is not None and registry.exists():
        try:
            doc = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            doc = {}
        for entry in doc.get("checks") or []:
            if isinstance(entry, dict) and entry.get("check_script"):
                gates.add(str(entry["check_script"]))
    return gates


# --------------------------------------------------------------------------- #
# Path resolution — tail segments + a sandbox veto on the base
# --------------------------------------------------------------------------- #
def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_seq(node: ast.AST, consts: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    """A tuple/list of string constants, or a name bound to one."""
    if isinstance(node, (ast.Tuple, ast.List)):
        parts = [_const_str(e) for e in node.elts]
        if all(p is not None for p in parts):
            return tuple(p for p in parts if p is not None)
        return None
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _split(segments: list[str]) -> list[str]:
    out: list[str] = []
    for seg in segments:
        out.extend(p for p in seg.replace("\\", "/").split("/") if p and p != ".")
    return out


def _path_parts(
    node: ast.AST, consts: dict[str, tuple[str, ...]]
) -> tuple[list[str], ast.AST | None] | None:
    """Split a Path expression into (constant tail segments, base expression).

    ``REPO / "data" / "prophet" / "ledger.jsonl"``  -> (["data","prophet","ledger.jsonl"], REPO)
    ``args.root.joinpath(*CLAIMS_REL)``             -> (["data","qledger","claims.jsonl"], args.root)
    ``tmp_path / "data" / "prophet" / "ledger.jsonl"`` -> (same tail, tmp_path)
    ``Path("data/qledger/claims.jsonl")``           -> (same tail, None)

    The tail is what identifies the store; the base is what the sandbox veto
    judges. Splitting them this way is why ``Path(__file__).resolve().parents[1]``
    and ``Path(__file__).resolve().parent.parent`` are both handled without the
    resolver ever having to recognise either shape.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _const_str(node.right)
        if right is None:
            return None
        left = _path_parts(node.left, consts)
        if left is None:
            return None
        return left[0] + _split([right]), left[1]
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "joinpath":
            base = _path_parts(func.value, consts)
            if base is None:
                return None
            tail: list[str] = list(base[0])
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    seq = _const_seq(arg.value, consts)
                    if seq is None:
                        return None
                    tail += _split(list(seq))
                    continue
                literal = _const_str(arg)
                if literal is None:
                    return None
                tail += _split([literal])
            return tail, base[1]
        if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
            literal = _const_str(node.args[0])
            if literal is not None:
                return _split([literal]), None
            inner = _path_parts(node.args[0], consts)
            if inner is not None:
                return inner
            return [], node.args[0]
        return None
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return [], node
    return None


def _base_root_name(node: ast.AST | None) -> str | None:
    """The leftmost Name of a base expression: args.root -> 'args', tmp_path -> 'tmp_path'."""
    cur = node
    while cur is not None:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.BinOp):
            cur = cur.left
        else:
            return None
    return None


def resolve_store(node: ast.AST, scope: Scope) -> str | None:
    """The append-only store this Path expression names, or None.

    A sandbox base (``tmp_path``, a function parameter, or a name derived from
    either) vetoes the match, so a fixture assertion cannot be reported. That is
    a structural guarantee, not a heuristic: the guarantee the prior
    implementation stated in its docstring and then violated.
    """
    parts = _path_parts(node, scope.consts)
    if parts is None:
        return None
    tail, base = parts
    if not tail:
        return None
    candidate = "/".join(tail)
    if candidate not in scope.stores:
        return None
    root_name = _base_root_name(base)
    if root_name is not None and (
        root_name in SANDBOX_ROOTS or root_name in scope.sandbox or root_name in scope.params
    ):
        return None
    return candidate


# --------------------------------------------------------------------------- #
# Taint
# --------------------------------------------------------------------------- #
def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _bears_path(node: ast.AST, scope: Scope) -> bool:
    """True when this expression is (or was derived from) a live store PATH."""
    for sub in ast.walk(node):
        if resolve_store(sub, scope):
            return True
    return any(scope.path_taint.get(n) for n in _names_in(node))


def _performs_read(node: ast.AST, scope: Scope) -> bool:
    """True when the expression turns a store path into that store's CONTENT."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Attribute):
            if func.attr in STAT_METHODS or func.attr in PATH_METHODS:
                continue
            if _bears_path(func.value, scope):
                # read_text() reads; an unknown method on a store path is
                # assumed to read it — conservative in the direction of seeing
                # the defect rather than missing it.
                return True
            if any(_bears_path(a, scope) for a in sub.args):
                return True
            continue
        name = getattr(func, "id", "")
        if name == "Path":
            continue
        if any(_bears_path(a, scope) for a in sub.args):
            return True
        if name in READ_CALLS and _bears_path(sub, scope):
            return True
    return False


def value_taint(node: ast.AST | None, scope: Scope) -> tuple[set[str], set[str]]:
    """(paths, content) — the stores this expression's VALUE derives from.

    ``paths`` is a Path object pointing at a store; ``content`` is what a row
    append actually changes. Only ``content`` can make an assertion fragile,
    which is why ``assert LEDGER.name == "ledger.jsonl"`` is not a finding.
    """
    paths: set[str] = set()
    content: set[str] = set()
    if node is None:
        return paths, content
    for sub in ast.walk(node):
        resolved = resolve_store(sub, scope)
        if resolved:
            paths.add(resolved)
    for name in _names_in(node):
        paths |= scope.path_taint.get(name, set())
        content |= scope.content_taint.get(name, set())
    if paths and _performs_read(node, scope):
        content |= paths
    return paths, content


def _assign_targets(node: ast.AST) -> list[str]:
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.append(sub.id)
    return out


def _binding_pairs(stmt: ast.stmt) -> list[tuple[list[str], ast.AST | None]]:
    """(target names, value expression) for every binding form that carries taint."""
    if isinstance(stmt, ast.Assign):
        names: list[str] = []
        for target in stmt.targets:
            names += _assign_targets(target)
        return [(names, stmt.value)]
    if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)) and stmt.value is not None:
        return [(_assign_targets(stmt.target), stmt.value)]
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        return [(_assign_targets(stmt.target), stmt.iter)]
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        pairs: list[tuple[list[str], ast.AST | None]] = []
        for item in stmt.items:
            if item.optional_vars is not None:
                pairs.append((_assign_targets(item.optional_vars), item.context_expr))
        return pairs
    return []


def collect_taint(body: list[ast.stmt], scope: Scope) -> None:
    """Fixpoint over the scope's bindings, mutating scope.path_taint/content_taint.

    Order-insensitive on purpose (a helper defined below its caller still
    propagates); see the EXECUTION ORDER false-positive mode.
    """
    statements = [s for stmt in body for s in _walk_scope(stmt)]
    for _ in range(8):
        changed = False
        for stmt in statements:
            if not isinstance(stmt, ast.stmt):
                continue
            for names, value in _binding_pairs(stmt):
                if not names or value is None:
                    continue
                paths, content = value_taint(value, scope)
                is_loop = isinstance(stmt, (ast.For, ast.AsyncFor))
                if is_loop and content:
                    # `for row in read_jsonl(LEDGER):` — the loop variable is a ROW,
                    # i.e. content, not the iterable's path.
                    paths = set()
                bounded = _is_bounded_prefix(value)
                for name in names:
                    if content:
                        # Grain is sticky in the STORE direction: a name bound to a
                        # row here and to the whole store elsewhere is judged as
                        # the store, which is the fail-closed side.
                        if is_loop and name not in scope.content_taint:
                            scope.row_names.add(name)
                        elif not is_loop:
                            scope.row_names.discard(name)
                        if bounded and name not in scope.content_taint:
                            scope.prefix_names.add(name)
                        elif not bounded:
                            scope.prefix_names.discard(name)
                    if paths - scope.path_taint.get(name, set()):
                        scope.path_taint.setdefault(name, set()).update(paths)
                        changed = True
                    if content - scope.content_taint.get(name, set()):
                        scope.content_taint.setdefault(name, set()).update(content)
                        changed = True
        if not changed:
            break


def _calls_sandbox(node: ast.AST) -> bool:
    """True when the expression manufactures a temp dir (tempfile.mkdtemp() & co)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in SANDBOX_CALLS:
                return True
    return False


def _is_path_algebra(node: ast.AST) -> bool:
    """True when the expression BUILDS a path: `a / "b"`, `a.joinpath(...)`, `Path(x)`."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("joinpath", "with_name",
                                                             "with_suffix", "resolve"):
            return True
        if isinstance(func, ast.Name) and func.id == "Path":
            return True
    return False


def collect_sandbox(body: list[ast.stmt], scope: Scope) -> None:
    """Names that are (or derive from) a pytest tmp dir, so a store tail off them is fake."""
    for _ in range(4):
        changed = False
        for stmt in [s for st in body for s in _walk_scope(st)]:
            if not isinstance(stmt, ast.stmt):
                continue
            for names, value in _binding_pairs(stmt):
                if value is None:
                    continue
                used = _names_in(value)
                # A TRUE sandbox root travels through anything: whatever
                # `_make_fixture_root(tmp_path)` returns is still under a temp dir.
                if _calls_sandbox(value) or (used & (SANDBOX_ROOTS | scope.sandbox)):
                    for name in names:
                        if name not in scope.sandbox:
                            scope.sandbox.add(name)
                            changed = True
                # A PARAMETER travels through path algebra only. `p = root / "data"`
                # keeps the caller's choice of root; `args = parser.parse_args(argv)`
                # does not, and treating it as one made this guard blind to the very
                # gate shape it exists to catch (see gate_exit_with_argv_param).
                elif _is_path_algebra(value) and (used & scope.params):
                    for name in names:
                        if name not in scope.params:
                            scope.params.add(name)
                            changed = True
        if not changed:
            break


# --------------------------------------------------------------------------- #
# The monotonicity rule
# --------------------------------------------------------------------------- #
def is_schema_shape(node: ast.AST) -> bool:
    """A key-set / type / validator check: appending a row cannot falsify it."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"keys", "isinstance", "type"} or name.startswith("validate"):
                return True
    return False


def append_fragile(op: ast.cmpop, left: set[str], right: set[str]) -> bool:
    """Can APPENDING A ROW to the tainted side falsify this comparison?

    That question — not "is this an equality" — is the whole law:

        len(rows) == 28              FRAGILE  (defect 4, verbatim)
        ledger_ids <= graded_ids     FRAGILE  (defect 3, verbatim — an upper bound)
        len(rows) >= 28              SAFE     (a floor only ever grows)
        28 <= len(rows)              SAFE     (the same floor, written the other way)
        "HEADER" in body             SAFE     (a row cannot un-appear)
        set(row.keys()) == FIELDS    SAFE     (schema; row count is irrelevant)
        after == before              SAFE     (two reads of the SAME store, one run)
        a != b                       SAFE     (pinning "not this" is not the class)
    """
    if left and right and left == right:
        # Both sides read the same store in the same run: a within-run mutation
        # guard, not a pin against a frozen expectation. Both sides move together.
        return False
    if isinstance(op, ast.Eq):
        return bool(left or right)
    if isinstance(op, (ast.Lt, ast.LtE)):
        return bool(left)          # tainted <= frozen is a CEILING on a growing side
    if isinstance(op, (ast.Gt, ast.GtE)):
        return bool(right)         # frozen >= tainted is the same ceiling, mirrored
    if isinstance(op, ast.In):
        return bool(left) and not right   # a store-derived value pinned into a frozen set
    if isinstance(op, ast.NotIn):
        return bool(right)         # an append can introduce the excluded value
    return False


# Calls that collapse many rows into one value. Their presence is what turns a
# row-grain expression back into a statement about the WHOLE store.
AGGREGATE_CALLS = frozenset(
    {"len", "sum", "set", "frozenset", "sorted", "list", "tuple", "dict", "count",
     "min", "max", "any", "all", "Counter", "mean", "median"}
)


def _is_bounded_prefix(node: ast.AST) -> bool:
    """True when the expression slices a constant-bounded PREFIX: ``raw[:50_790]``.

    Observed at tests/test_government_revenue_candidate_grader.py:2302, which
    takes ``incident_prefix = raw[:50_790]`` and then pins its row count and
    sha256. Appending cannot change the first N bytes, so that pin is legal —
    and it is legal for a reason a scanner can actually see.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Subscript) or not isinstance(sub.slice, ast.Slice):
            continue
        sl = sub.slice
        lower_ok = sl.lower is None or (
            isinstance(sl.lower, ast.Constant) and sl.lower.value == 0
        )
        upper_ok = isinstance(sl.upper, ast.Constant) and isinstance(sl.upper.value, int)
        if lower_ok and upper_ok:
            return True
    return False


def operand_is_growth_immune(node: ast.AST, scope: Scope) -> bool:
    """True when appending a VALID row cannot change this operand's value.

    Two shapes, both observed in the tree:

    ROW GRAIN — the law's own wording is the reason this matters: an assertion is
    illegal when appending a **valid** new row falsifies it. ``row["kind"] ==
    "event"`` inside ``for row in rows:`` is a per-row schema contract, which a
    valid appended row satisfies; ``len(rows) == 28`` is a statement about the
    whole store, which it does not.

    BOUNDED PREFIX — a constant-bounded slice of the store cannot move.
    """
    tainted = {n for n in _names_in(node) if scope.content_taint.get(n)}
    if not tainted:
        return False
    if not (tainted <= scope.row_names or tainted <= scope.prefix_names):
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            # An aggregate over row-grain names re-collapses them into a
            # statement about the store; over a bounded prefix it stays bounded.
            if name in AGGREGATE_CALLS and not tainted <= scope.prefix_names:
                return False
        if resolve_store(sub, scope):
            return False
    return True


def classify_compare(node: ast.Compare, scope: Scope) -> tuple[str, str] | None:
    """(store, detail) when this comparison is append-fragile, else None."""
    if is_schema_shape(node):
        return None
    if all(
        operand_is_growth_immune(operand, scope) or not value_taint(operand, scope)[1]
        for operand in [node.left, *node.comparators]
    ):
        return None
    _, left = value_taint(node.left, scope)
    right: set[str] = set()
    for comparator in node.comparators:
        right |= value_taint(comparator, scope)[1]
    if not (left or right):
        return None
    for op in node.ops:
        if append_fragile(op, left, right):
            store = sorted(left | right)[0]
            return store, f"{type(op).__name__} against the content of {store}"
    return None


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def _walk_scope(node: ast.AST):
    """ast.walk that does NOT descend into a nested function or class body."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_scope(child)


def scan_assertions(body: list[ast.stmt], rel: str, scope: Scope) -> list[Hit]:
    hits: list[Hit] = []
    for stmt in body:
        for sub in _walk_scope(stmt):
            if isinstance(sub, ast.Assert):
                for cmp_node in ast.walk(sub.test):
                    if not isinstance(cmp_node, ast.Compare):
                        continue
                    verdict = classify_compare(cmp_node, scope)
                    if verdict is not None:
                        store, detail = verdict
                        hits.append(Hit(rel, sub.lineno, KIND_ASSERT, store, detail))
            elif (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr in ASSERT_METHODS
                and len(sub.args) >= 2
            ):
                left = value_taint(sub.args[0], scope)[1]
                right = value_taint(sub.args[1], scope)[1]
                if (left or right) and append_fragile(
                    ASSERT_METHODS[sub.func.attr](), left, right
                ):
                    store = sorted(left | right)[0]
                    hits.append(
                        Hit(
                            rel,
                            sub.lineno,
                            KIND_ASSERT,
                            store,
                            f"{sub.func.attr} against the content of {store}",
                        )
                    )
    return hits


def _exit_payload(stmt: ast.stmt) -> ast.AST | None | bool:
    """The exit-code expression of a failing-exit statement, or False if not one."""
    if isinstance(stmt, ast.Return):
        return stmt.value
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        if (
            isinstance(exc, ast.Call)
            and getattr(exc.func, "id", "") == "SystemExit"
            and exc.args
        ):
            return exc.args[0]
        return False
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "exit" and call.args:
            return call.args[0]
    return False


def _is_failing_exit(payload: ast.AST | None, scope: Scope) -> tuple[bool, bool]:
    """(is a nonzero exit, the exit code itself is a function of store content)."""
    if payload is None:
        return False, False
    if isinstance(payload, ast.Constant):
        return bool(payload.value not in (0, None, False)), False
    if value_taint(payload, scope)[1]:
        return True, True
    return False, False


def scan_exit_codes(
    body: list[ast.stmt], rel: str, scope: Scope, controls: tuple[ast.AST, ...] = ()
) -> list[Hit]:
    """A gate whose EXIT CODE is a function of append-only store content.

    This is defect 4 — the shape the prior implementation could not see, because
    it only ever looked at ``ast.Assert`` nodes containing an ``ast.Compare``.
    """
    hits: list[Hit] = []
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        payload = _exit_payload(stmt)
        if payload is not False:
            failing, self_tainted = _is_failing_exit(payload, scope)  # type: ignore[arg-type]
            tainted: set[str] = set()
            if self_tainted and payload is not None:
                tainted = value_taint(payload, scope)[1]  # type: ignore[arg-type]
            if failing and not tainted:
                for control in controls:
                    tainted |= value_taint(control, scope)[1]
            if failing and tainted:
                store = sorted(tainted)[0]
                hits.append(
                    Hit(
                        rel,
                        stmt.lineno,
                        KIND_EXIT,
                        store,
                        f"failing exit is a function of the content of {store}",
                    )
                )
        if isinstance(stmt, ast.If):
            hits += scan_exit_codes(stmt.body, rel, scope, controls + (stmt.test,))
            hits += scan_exit_codes(stmt.orelse, rel, scope, controls + (stmt.test,))
        elif isinstance(stmt, ast.While):
            hits += scan_exit_codes(
                stmt.body + stmt.orelse, rel, scope, controls + (stmt.test,)
            )
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            hits += scan_exit_codes(
                stmt.body + stmt.orelse, rel, scope, controls + (stmt.iter,)
            )
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            hits += scan_exit_codes(stmt.body, rel, scope, controls)
        elif isinstance(stmt, ast.Try):
            hits += scan_exit_codes(stmt.body, rel, scope, controls)
            for handler in stmt.handlers:
                hits += scan_exit_codes(handler.body, rel, scope, controls)
            hits += scan_exit_codes(stmt.orelse + stmt.finalbody, rel, scope, controls)
    return hits


def _module_consts(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    consts: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            seq = _const_seq(node.value, {})
            if seq is not None:
                consts[target.id] = seq
    return consts


def scan_source(text: str, rel: str, stores: dict[str, Store], is_gate: bool) -> list[Hit]:
    """Scan one module's SOURCE. Shared by the tree scan and by --selftest."""
    if not stores:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    consts = _module_consts(tree)

    # Outer scope = module body + every class body. A module-level
    # `LEDGER = REPO / "data" / …` and a class-level `SIDECAR = …` are both
    # constants the methods below inherit.
    outer_body: list[ast.stmt] = list(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            outer_body.extend(node.body)

    outer = Scope(stores=stores, consts=consts)
    collect_sandbox(outer_body, outer)
    collect_taint(outer_body, outer)

    hits = list(scan_assertions(outer_body, rel, outer))
    if is_gate:
        hits += scan_exit_codes(tree.body, rel, outer)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {
            a.arg
            for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            if a.arg not in ("self", "cls")
        }
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        local = Scope(
            stores=stores,
            consts=consts,
            sandbox=set(outer.sandbox),
            # A parameter is an INPUT (tmp_path, a target path a caller chose),
            # never the live store: veto any store tail hung off one.
            params=params,
            path_taint={k: set(v) for k, v in outer.path_taint.items() if k not in params},
            content_taint={
                k: set(v) for k, v in outer.content_taint.items() if k not in params
            },
        )
        collect_sandbox(node.body, local)
        collect_taint(node.body, local)
        hits += scan_assertions(node.body, rel, local)
        if is_gate:
            hits += scan_exit_codes(node.body, rel, local)

    deduped: dict[tuple[int, str, str], Hit] = {}
    for hit in hits:
        deduped.setdefault((hit.line, hit.kind, hit.detail), hit)
    return sorted(deduped.values(), key=lambda h: (h.line, h.kind, h.detail))


def scan_tree(root: Path, stores: dict[str, Store], gates: set[str]) -> list[Hit]:
    hits: list[Hit] = []
    for rel_dir in SCAN_DIRS:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if any(part in f"/{rel}" for part in SKIP_PARTS):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Cheap prefilter: no store's file name in the text means no path
            # expression in it can resolve to one.
            if not any(Path(p).name in text for p in stores):
                continue
            hits.extend(scan_source(text, rel, stores, rel in gates))
    return sorted(hits, key=lambda h: (h.file, h.line, h.kind))


# --------------------------------------------------------------------------- #
# Selftest — adversarial fixtures, both directions
# --------------------------------------------------------------------------- #
SELFTEST_STORES = {
    "data/prophet/ledger.jsonl": Store("data/prophet/ledger.jsonl", "A", "selftest"),
    "data/qledger/claims.jsonl": Store("data/qledger/claims.jsonl", "A", "selftest"),
    "data/seasonality/nw_forward_ledger.jsonl": Store(
        "data/seasonality/nw_forward_ledger.jsonl", "A", "selftest"
    ),
}

# ── known-bad constructions: every one MUST be caught ────────────────────────
BAD_FIXTURES: dict[str, tuple[str, bool, str]] = {
    # defect 3, verbatim shape: an upper bound over the live ledger.
    "upper_bound_subset": (
        '''
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "data" / "prophet" / "ledger.jsonl"
SIDECAR = REPO / "docs" / "plan_grades.jsonl"

def test_every_closed_plan_is_accounted_for():
    ledger_ids = {str(r["id"]) for r in read_jsonl(LEDGER)}
    graded_ids = {str(r["id"]) for r in read_jsonl(SIDECAR)}
    assert ledger_ids and ledger_ids <= graded_ids
''',
        False,
        KIND_ASSERT,
    ),
    # defect 4 (the seasonality pin), verbatim shape: an equality on row count.
    "row_count_equality": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FORWARD = ROOT / "data" / "seasonality" / "nw_forward_ledger.jsonl"

def test_forward_ledger_has_the_expected_rows():
    rows = read_jsonl(FORWARD)
    assert len(rows) == 28
''',
        False,
        KIND_ASSERT,
    ),
    # defects 1/2: a generated doc pinned by equality while it derives from the store.
    "generated_doc_pin": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def test_registry_doc_is_current():
    claims = load_jsonl(ROOT / "data" / "qledger" / "claims.jsonl")
    rendered = render_registry(claims)
    committed = (ROOT / "docs" / "INTELLIGENCE_REGISTRY.md").read_text()
    assert rendered == committed
''',
        False,
        KIND_ASSERT,
    ),
    # unittest spelling of the same defect.
    "unittest_assert_equal": (
        '''
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class T(unittest.TestCase):
    def test_rows(self):
        rows = read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl")
        self.assertEqual(len(rows), 41)
''',
        False,
        KIND_ASSERT,
    ),
    # DEFECT 4 IN THE LIST: a GATE whose exit code is a function of store content.
    # This is the shape that was invisible to the prior implementation, and it is
    # written here exactly as check_qledger_metric_validity.py wrote it — the
    # repo root arrives via an argparse default, the store path via a tuple
    # constant splatted into joinpath, and no `assert` appears anywhere.
    "gate_exit_on_store_content": (
        '''
import argparse, sys
from pathlib import Path
CLAIMS_REL = ("data", "qledger", "claims.jsonl")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    claims_path = args.root.joinpath(*CLAIMS_REL)
    claims = _read_jsonl(claims_path)
    findings = audit(claims)
    invalid = [f for f in findings if f.severity == "invalid"]
    if args.strict and invalid:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        True,
        KIND_EXIT,
    ),
    # The same gate, but `main` takes an argv PARAMETER. Found by running this
    # guard against itself (acceptance 6): parameters used to seed the sandbox
    # set and propagate through any call, so `args = parser.parse_args(argv)`
    # made `args.root` invisible and this guard passed its own law for the wrong
    # reason. A parameter is now a base veto only, never a propagation seed.
    "gate_exit_with_argv_param": (
        '''
import argparse, sys
from pathlib import Path
CLAIMS_REL = ("data", "qledger", "claims.jsonl")

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    rows = (args.root.joinpath(*CLAIMS_REL)).read_text().splitlines()
    if len(rows) != 28:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        True,
        KIND_EXIT,
    ),
    # The same class with the exit CODE itself computed from store content.
    "gate_exit_code_is_the_count": (
        '''
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    rows = read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl")
    bad = [r for r in rows if not r.get("id")]
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
''',
        True,
        KIND_EXIT,
    ),
}

# ── legal constructions: every one MUST stay clean ───────────────────────────
GOOD_FIXTURES: dict[str, tuple[str, bool]] = {
    # A tmp_path sandbox writes the same tail; nothing nightly can reach it.
    "tmp_path_sandbox": (
        '''
from pathlib import Path

def test_writer_appends(tmp_path):
    ledger = tmp_path / "data" / "prophet" / "ledger.jsonl"
    write_rows(ledger, THREE_ROWS)
    rows = read_jsonl(ledger)
    assert len(rows) == 3
    assert {r["id"] for r in rows} <= {"a", "b", "c"}
''',
        False,
    ),
    # The sandbox arrives through a HELPER CALL, not path algebra. Shape observed
    # verbatim at tests/test_chronicle.py:262 (`root = _make_fixture_root(tmp_path)`).
    "sandbox_via_helper": (
        '''
from pathlib import Path

def test_the_fixture_tree_builds(tmp_path):
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)
    events = load_events_jsonl(root / "data" / "prophet" / "ledger.jsonl")
    assert len(events) == 5
''',
        False,
    ),
    # The stdlib sandbox spelling. Shape observed verbatim at
    # tests/test_whitehouse_w5.py:186 (`d = Path(tempfile.mkdtemp())`).
    "sandbox_via_mkdtemp": (
        '''
import tempfile
from pathlib import Path

def test_the_adapter_writes_claims():
    d = Path(tempfile.mkdtemp())
    register_claims(d)
    claims_path = d / "data" / "qledger" / "claims.jsonl"
    claims = [json.loads(l) for l in claims_path.read_text().splitlines() if l.strip()]
    assert len(claims) == 3
''',
        False,
    ),
    # A FLOOR: appending only ever makes it truer. This is the fix for defect 4.
    "floor": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FORWARD = ROOT / "data" / "seasonality" / "nw_forward_ledger.jsonl"

def test_forward_ledger_keeps_its_history():
    rows = read_jsonl(FORWARD)
    assert len(rows) >= 28
    assert 28 <= len(rows)
''',
        False,
    ),
    # Schema: the row count is irrelevant to a key-set contract.
    "schema_keys": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"id", "asof", "value"}

def test_every_row_carries_the_contract():
    for row in read_jsonl(ROOT / "data" / "qledger" / "claims.jsonl"):
        assert set(row.keys()) == FIELDS
''',
        False,
    ),
    # Schema at STORE grain: `rows` is the whole store, so the row-grain carve-out
    # cannot reach this one — only is_schema_shape keeps it clean.
    "schema_keys_store_grain": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"id", "asof", "value"}

def test_the_schema_is_stable():
    rows = read_jsonl(ROOT / "data" / "qledger" / "claims.jsonl")
    assert set(rows[0].keys()) == FIELDS
''',
        False,
    ),
    # Per-row schema contract: a VALID appended row satisfies it.
    "per_row_schema": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_every_event_row_is_well_formed():
    for event in read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl"):
        assert event["kind"] == "event"
        assert event["schema"] == "prophet.ledger/v1"
''',
        False,
    ),
    # A constant-bounded PREFIX of the store, guarded by a floor. Appending
    # cannot change the first 50,790 bytes. Shape observed verbatim at
    # tests/test_government_revenue_candidate_grader.py:2301-2304.
    "bounded_prefix": (
        '''
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1]

def test_the_incident_prefix_is_frozen():
    raw = (ROOT / "data" / "qledger" / "claims.jsonl").read_bytes()
    assert len(raw) >= 50_790
    incident_prefix = raw[:50_790]
    assert len(incident_prefix.splitlines()) == 8
    assert hashlib.sha256(incident_prefix).hexdigest() == "920d840a"
''',
        False,
    ),
    # Two reads of the SAME store in one run: both sides move together.
    "within_run_byte_identity": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "prophet" / "ledger.jsonl"

def test_a_rerun_writes_nothing():
    before = LEDGER.read_bytes()
    rerun()
    after = LEDGER.read_bytes()
    assert after == before
''',
        False,
    ),
    # Membership in the growing side: a row cannot un-appear.
    "membership_in_store": (
        '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_the_header_survives():
    body = (ROOT / "data" / "prophet" / "ledger.jsonl").read_text()
    assert "# ledger" in body
''',
        False,
    ),
    # Parse-only well-formedness: every row must be a dict with a str id.
    "parse_only": (
        '''
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]

def test_every_line_parses():
    for line in (ROOT / "data" / "qledger" / "claims.jsonl").read_text().splitlines():
        row = json.loads(line)
        assert isinstance(row.get("id"), str)
''',
        False,
    ),
    # A gate that exits nonzero on COMMITTED config, not on the append-only store.
    "gate_exit_on_config": (
        '''
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    registry = load_yaml(ROOT / "config" / "house_law_checks.yml")
    findings = audit(registry)
    if findings:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        True,
    ),
    # A gate that reads the store but only ever REPORTS on it (exit 0 always).
    "gate_reports_only": (
        '''
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    rows = read_jsonl(ROOT / "data" / "qledger" / "claims.jsonl")
    for row in rows:
        if not row.get("id"):
            print("::warning title=qledger::row without an id", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
        True,
    ),
}


def selftest() -> int:
    failures: list[str] = []
    for name, (source, is_gate, kind) in BAD_FIXTURES.items():
        hits = scan_source(source, f"<bad:{name}>", SELFTEST_STORES, is_gate)
        if not hits:
            failures.append(f"FALSE NEGATIVE: known-bad fixture '{name}' was NOT caught")
        elif not any(h.kind == kind for h in hits):
            failures.append(
                f"WRONG KIND: fixture '{name}' expected a {kind} finding, got "
                f"{sorted({h.kind for h in hits})}"
            )
    for name, (source, is_gate) in GOOD_FIXTURES.items():
        hits = scan_source(source, f"<good:{name}>", SELFTEST_STORES, is_gate)
        if hits:
            failures.append(
                f"FALSE POSITIVE: legal fixture '{name}' was flagged: "
                + "; ".join(f"line {h.line}: {h.detail}" for h in hits)
            )
    for line in failures:
        print(f"::error title=append-only-selftest::{line}", flush=True)
    total = len(BAD_FIXTURES) + len(GOOD_FIXTURES)
    if failures:
        print(
            f"append-only assertion law selftest: FAILED — {len(failures)} of {total} "
            f"fixtures behaved wrongly",
            flush=True,
        )
        return 1
    print(
        f"append-only assertion law selftest: OK — {len(BAD_FIXTURES)} known-bad "
        f"constructions caught, {len(GOOD_FIXTURES)} legal constructions clean",
        flush=True,
    )
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The append-only assertion law.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on findings (severity is 'discipline' by default)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list-stores", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = args.root.resolve()
    stores = load_stores(root)

    if args.list_stores:
        if args.json:
            print(
                json.dumps(
                    {"root": str(root), "stores": [
                        {"path": s.path, "signal": s.signal, "why": s.why}
                        for s in sorted(stores.values(), key=lambda s: s.path)
                    ]},
                    indent=2,
                ),
                flush=True,
            )
        else:
            for store in sorted(stores.values(), key=lambda s: s.path):
                print(f"{store.signal}  {store.path}  ({store.why})", flush=True)
            print(f"{len(stores)} append-only store(s) classified", flush=True)
        return 0

    if not stores:
        # COULD NOT LOOK != LOOKED AND FOUND NOTHING.
        # `findings: null` (not []) is load-bearing: an empty list is indistinguishable
        # from a clean audit, which is the substitution
        # research/MASTERMIND_EVALUATION_STANDARDS.md §9.2 exists to forbid — and it would
        # be committed here by the very guard that polices honest absence.
        # --json emits ONLY JSON, never a ::notice line ahead of it, or a consumer piping
        # to jq breaks on the first byte.
        if args.json:
            print(
                json.dumps(
                    {
                        "root": str(root),
                        "store_set_absent": True,
                        "stores": 0,
                        "findings": None,
                    }
                ),
                flush=True,
            )
        else:
            print(
                "::notice title=append-only-assertions::config/synapse.yml absent or "
                "unreadable — NOT audited (could not look; this is not a clean result)",
                flush=True,
            )
        # Fail CLOSED under --strict: unable to classify is not a pass.
        return 1 if args.strict else 0

    gates = load_gate_scripts(root)
    hits = scan_tree(root, stores, gates)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "stores": len(stores),
                    "gate_scripts": len(gates),
                    "findings": [h.as_dict() for h in hits],
                },
                indent=2,
            ),
            flush=True,
        )
    else:
        for hit in hits:
            print(
                f"::warning file={hit.file},line={hit.line},"
                f"title=append-only-{hit.kind}::{hit.detail}",
                flush=True,
            )
        print(
            f"append-only assertion law: {len(hits)} finding(s) across "
            f"{len(stores)} classified store(s), {len(gates)} gate script(s)",
            flush=True,
        )
    return 1 if (args.strict and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
