"""
scripts/check_append_only_assertions.py — the append-only assertion law.

THE DEFECT THIS EXISTS TO STOP
------------------------------
A test or drift guard asserts on the CONTENT of a store that a nightly lane
APPENDS to. It is green the day it is written and it reds main days or weeks
later with no PR author involved, so it gets routed around rather than obeyed.
It has now shipped four times, each time by a different builder that had been
warned about it in prose:

  1. scripts/check_intelligence_registry.py pinned a generated doc by equality
     while the registry derived from data/qledger/claims.jsonl (append-only).
  2. The same pin RELOCATED to config/synapse.yml instead of being removed.
  3. tests/test_prophet_plan_grades.py asserts `ledger_ids <= graded_ids` over
     the live data/prophet/ledger.jsonl against a frozen committed sidecar.
  4. tests/test_seasonality_calibration.py pinned `len(rows) == 28` over
     data/seasonality/nw_forward_ledger.jsonl; the ledger reached 43 rows on
     2026-08-08 and took main red. (Now a documented floor — the legal shape.)

Prose warnings did not prevent any of them. This is the mechanical form.

WHAT COUNTS AS AN APPEND-ONLY STORE (derived, not hand-listed)
--------------------------------------------------------------
A path is classified append-only when it is a ``data/**`` JSONL artifact
registered in ``config/synapse.yml`` with ``format: jsonl`` and ``storage: git``
AND either:

  SIGNAL A — its ``cadence`` names a nightly/daily lane
     (daily-engine, nightly-cortex, nightly-factor-panel, nightly-sec,
     theta-ops-nightly, asia-close). NOTE that neither motivating store's
     cadence contains the word "nightly": both data/qledger/claims.jsonl and
     data/prophet/ledger.jsonl are ``daily-engine``. A rule that grepped for
     "nightly" would miss the two defects that caused this guard to exist.
  SIGNAL B — its ``notes``/``known_extra_writers`` prose declares the property
     ("append-only", "appended only", "never truncate/overwrite", "sole future
     advancer"). This catches a store whose cadence is odd (weekly, on-demand,
     collect) but which the registry itself says only ever grows.

One yaml parse and one regex. Both signals are read off the registry rather
than off git history: history-walking is neither cheap nor reliable here (a
heal script that rewrites a field in place makes a genuinely append-only
ledger look non-monotone, and these worktrees are shallow clones so a `git log`
over them is silently truncated to ~3 days).

WHAT COUNTS AS AN ILLEGAL ASSERTION
-----------------------------------
Not "an equality" — the rule is MONOTONICITY: an assertion is illegal when
APPENDING A ROW can falsify it. That is the property that makes it red main with
no PR author involved, and it is what separates the four real defects from the
many lexically-similar legal assertions in the tree:

    len(rows) == 28              FRAGILE  (defect 4, verbatim)
    ledger_ids <= graded_ids     FRAGILE  (defect 3, verbatim — an upper bound)
    len(rows) >= 28              SAFE     (the fix applied to defect 4 — a floor)
    "HEADER" in body             SAFE     (a row cannot un-appear)
    set(row.keys()) == FIELDS    SAFE     (schema; row count is irrelevant)
    read_bytes() == read_bytes() SAFE     (two reads of the same store, same run)

FALSE-POSITIVE MODES (honest list — this is why the guard ships at discipline)
-----------------------------------------------------------------------------
* MANIFEST SIBLING. Comparing a live store to a receipt/manifest written by the
  SAME producer run is safe — the receipt moves in lockstep. tests/test_chronicle.py
  ties events.jsonl's row count and sha256 to its co-committed manifest.json and
  is flagged anyway; the guard cannot currently see that two artifacts share a
  producer. Closing this needs a `producer:` sibling lookup in synapse.yml.
* FROZEN PREFIX. A module contract may freeze a bounded slice of an otherwise
  growing store. tests/test_market_memory_production_records.py pins
  ACTIVATION_PREFIX_ROWS/ACTIVATION_PREFIX_SHA256 over rows 0..383 of
  data/options_signal_episode/episodes.jsonl; exact equality is CORRECT there
  and is flagged anyway.
* WITHIN-RUN VIA AN INTERMEDIARY. The same-store carve-out needs the taint on
  BOTH sides. `assert result["sha256"] == sha256(before).hexdigest()`, where
  `before` was read from the live store moments earlier in the same test, only
  carries taint on one side and is flagged (measured at
  tests/test_market_memory_production_records.py:563).
* EXECUTION ORDER. Taint is a fixpoint over each function body and ignores
  statement order, so a name reassigned after the assert can back-taint it.
* COMPREHENSION SCOPE. A comprehension-local target sharing a name with a
  tainted variable in the same function is conflated with it.

FALSE-NEGATIVE MODES (honest list)
----------------------------------
* UNREGISTERED STORE. A live append-only store missing from config/synapse.yml
  is invisible. data/basket_turn/ledger.jsonl is a measured example: written by
  the nightly lane, read by seven modules, wired into config/dag.yml and
  daily.yml, and absent from the registry — so the equality pin at
  tests/test_basket_membership_stamps.py is NOT reported here.
* INDIRECTION. A path handed in via a fixture, a config lookup, a constant in
  another module, or `getattr` is not resolved. Only a Path literal built from a
  ``Path(__file__).resolve().parents[N]``-derived name (or a bare relative
  ``Path("data/...")``) is traced.
* NON-JSONL. parquet/csv/json append-only artifacts are out of scope; the
  four real defects were all JSONL and widening costs precision.
* MORE THAN TWO HOPS. Taint propagates through assignments but not through a
  helper function's return value in another module.

SEVERITY: discipline, ci_wiring [] — ON PURPOSE
-----------------------------------------------
It fires on pre-existing code that no PR author wrote, so wiring it as a gate on
day one is how a guard gets disabled instead of obeyed. CI proves the guard
WORKS (its --selftest, with negative controls, plus tests/test_append_only_assertions.py);
it does not yet judge the tree. The promotion plan is in the registry entry.

Annotations are emitted with a bare ``print`` and ``flush=True`` per CLAUDE.md
§"GitHub annotations must START the line" — a logger would prefix the line and
GitHub would silently drop it.

Usage
-----
  python scripts/check_append_only_assertions.py [--root PATH] [--strict] [--json]
  python scripts/check_append_only_assertions.py --list-stores
  python scripts/check_append_only_assertions.py --selftest
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a hard dep of every CI lane
    yaml = None  # type: ignore[assignment]

SYNAPSE_REL = ("config", "synapse.yml")
SCAN_DIRS = ("tests", "scripts")

# Cadence values that name a nightly / daily engine lane. NEITHER motivating
# defect's store says "nightly" — both are 'daily-engine'.
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

# Names a repo-root Path is conventionally bound to. A binding only counts when
# its VALUE is a Path(__file__)…parents[N] expression, so the name list is a
# readability aid, not the rule.
_ROOT_VALUE = re.compile(r"Path\s*\(\s*__file__\s*\)")

# unittest-style assertions, mapped onto the ast operator they mean, so the
# monotonicity rule below judges them identically to a bare `assert a == b`.
_ASSERT_METHODS: dict[str, type] = {
    "assertEqual": ast.Eq,
    "assertSetEqual": ast.Eq,
    "assertListEqual": ast.Eq,
    "assertDictEqual": ast.Eq,
    "assertCountEqual": ast.Eq,
    "assertNotEqual": ast.NotEq,
    "assertLess": ast.Lt,
    "assertLessEqual": ast.LtE,
    "assertGreater": ast.Gt,
    "assertGreaterEqual": ast.GtE,
    "assertIn": ast.In,
    "assertNotIn": ast.NotIn,
}

# Reading a store's content. `.exists()` is deliberately absent.
_READ_CALLS = frozenset(
    {"read_text", "read_bytes", "open", "load", "loads", "read_jsonl",
     "load_jsonl", "readlines", "read_json", "read_csv", "read_parquet",
     "load_claims", "load_grades", "load_events_jsonl", "iter_rows"}
)


@dataclass(frozen=True)
class Store:
    path: str
    signal: str
    why: str


@dataclass(frozen=True)
class Hit:
    file: str
    line: int
    store: str
    detail: str


# --------------------------------------------------------------------------- #
# Store classification
# --------------------------------------------------------------------------- #
def classify_stores(root: Path) -> dict[str, Store]:
    """Return {relative path -> Store} for every append-only JSONL data artifact."""
    if yaml is None:
        return {}
    synapse = root.joinpath(*SYNAPSE_REL)
    if not synapse.exists():
        return {}
    doc = yaml.safe_load(synapse.read_text(encoding="utf-8")) or {}
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
        prose = f"{entry.get('notes') or ''} {entry.get('known_extra_writers') or ''}"
        if APPEND_ONLY_PROSE.search(prose):
            out[path] = Store(
                path, "B", f"synapse.yml[{name}] declares append-only in prose"
            )
    return out


# --------------------------------------------------------------------------- #
# Path-expression resolution
# --------------------------------------------------------------------------- #
def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _resolve_path(node: ast.AST, root_names: set[str]) -> str | None:
    """Resolve a Path expression to a repo-relative posix string, or None.

    Only two shapes resolve, and both are anchored: a chain rooted at a name
    bound to ``Path(__file__)…parents[N]``, or a bare ``Path("data/…")``. A
    tmp_path/tmpdir fixture can never be either, which is what keeps every
    fixture-rooted assertion out of the report by construction rather than by
    a name blocklist.
    """
    # base / "a" / "b"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _const_str(node.right)
        if right is None:
            return None
        left = _resolve_path(node.left, root_names)
        if left is None:
            return None
        return f"{left}/{right}".strip("/") if left else right
    # base.joinpath("a", "b") / Path("a/b")
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "joinpath":
            base = _resolve_path(func.value, root_names)
            if base is None:
                return None
            parts = [_const_str(a) for a in node.args]
            if any(p is None for p in parts):
                return None
            return "/".join([base, *parts]).strip("/") if base else "/".join(parts)  # type: ignore[misc]
        if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
            literal = _const_str(node.args[0])
            if literal and literal.startswith("data/"):
                return literal
        return None
    # A root name resolves to "" (the repo root itself).
    if isinstance(node, ast.Name) and node.id in root_names:
        return ""
    return None


def _root_names(tree: ast.Module) -> set[str]:
    """Names bound to a Path(__file__)…parents[N] expression anywhere in the file."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            try:
                src = ast.unparse(node.value)
            except Exception:  # noqa: BLE001 - unparse is best-effort
                continue
            if _ROOT_VALUE.search(src) and "parents" in src:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


# --------------------------------------------------------------------------- #
# Taint
# --------------------------------------------------------------------------- #
def _walk_scope(node: ast.AST):
    """ast.walk, but it does NOT descend into a nested function or class body.

    Load-bearing: without it the module scope re-examines every assertion inside
    every function using module-level taint only, so a name the function itself
    bound (``before = SOURCE.read_bytes()``) reads as untainted and the
    within-run byte-identity carve-out never applies.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return  # its body is its own scope, visited separately with its own taint
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_scope(child)


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _reads_a_store(node: ast.AST) -> bool:
    """True when the expression calls something that reads a file's content."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in _READ_CALLS:
                return True
    return False


def _collect_taint(
    body: list[ast.stmt], root_names: set[str], stores: dict[str, Store],
    seed: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Fixpoint: name -> set of append-only store paths its value derives from.

    A name is seeded when it is bound to a resolved store path. It is tainted
    when its value expression mentions a seeded/tainted name AND that expression
    reads content (or derives from something that already did). Order-insensitive
    by design; see the FALSE-POSITIVE list.
    """
    taint: dict[str, set[str]] = {k: set(v) for k, v in seed.items()}
    for stmt in body:
        if not isinstance(stmt, ast.Assign):
            continue
        targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        if not targets:
            continue
        # Seed on ANY resolvable store path anywhere in the value: the binding is
        # as often `rows = read_jsonl(ROOT / "data" / …)` as it is a bare
        # `LEDGER = ROOT / "data" / …`.
        found = {
            r
            for sub in ast.walk(stmt.value)
            if (r := _resolve_path(sub, root_names)) and r in stores
        }
        for t in targets:
            if found:
                taint.setdefault(t, set()).update(found)

    changed = True
    rounds = 0
    while changed and rounds < 6:
        changed = False
        rounds += 1
        for stmt in body:
            if not isinstance(stmt, ast.Assign) or not stmt.targets:
                continue
            targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if not targets:
                continue
            src_names = _names_in(stmt.value)
            inherited: set[str] = set()
            for n in src_names:
                inherited |= taint.get(n, set())
            # A bare alias of a tainted path object carries the taint; a read of
            # one carries the CONTENT, which is what the invariant is about.
            if not inherited:
                continue
            for t in targets:
                before = len(taint.get(t, set()))
                taint.setdefault(t, set()).update(inherited)
                if len(taint[t]) != before:
                    changed = True
    return taint


# --------------------------------------------------------------------------- #
# Assertion classification
# --------------------------------------------------------------------------- #
def _operand_paths(node: ast.AST, taint: dict[str, set[str]], root_names: set[str],
                   stores: dict[str, Store]) -> set[str]:
    out: set[str] = set()
    for n in _names_in(node):
        out |= taint.get(n, set())
    resolved = _resolve_path(node, root_names)
    if resolved and resolved in stores:
        out.add(resolved)
    for sub in ast.walk(node):
        r = _resolve_path(sub, root_names)
        if r and r in stores:
            out.add(r)
    return out


def _is_schema_shape(cmp_node: ast.Compare) -> bool:
    """A key-set / type / validator check is growth-safe: appending rows cannot break it."""
    for sub in ast.walk(cmp_node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"keys", "isinstance", "type"} or name.startswith("validate"):
                return True
    return False


def _append_fragile(op: ast.cmpop, left_t: set[str], right_t: set[str]) -> bool:
    """Can APPENDING a row to the tainted side falsify this comparison?

    That question — not "is this an equality" — is the whole rule, and it is what
    separates the four real defects from the many lexically-similar legal
    assertions in the tree:

      ==            fragile either way            (`len(rows) == 28` — defect 4)
      tainted <=/<  fragile: an upper bound       (`ledger_ids <= graded_ids` — defect 3)
      tainted >=/>  SAFE: a floor only grows      (the fix applied to defect 4)
      x in tainted  SAFE: a row cannot un-appear
      tainted in y  fragile: the pinned side is the frozen one
      not in        fragile: a later append can introduce the value
      !=            SAFE enough to ignore; pinning "not this" is not the defect class
    """
    if left_t and right_t and left_t == right_t:
        # Two reads of the SAME store compared to each other: a within-run
        # mutation guard, not a pin against a frozen expectation.
        return False
    if isinstance(op, ast.Eq):
        return True
    if isinstance(op, (ast.Lt, ast.LtE)):
        return bool(left_t)
    if isinstance(op, (ast.Gt, ast.GtE)):
        return bool(right_t)
    if isinstance(op, ast.In):
        return bool(left_t) and not right_t
    if isinstance(op, ast.NotIn):
        return True
    return False


def _classify_compare(cmp_node: ast.Compare, taint, root_names, stores) -> tuple[bool, str]:
    if _is_schema_shape(cmp_node):
        return False, ""
    left_paths = _operand_paths(cmp_node.left, taint, root_names, stores)
    right_paths: set[str] = set()
    for c in cmp_node.comparators:
        right_paths |= _operand_paths(c, taint, root_names, stores)
    if not (left_paths or right_paths):
        return False, ""
    for op in cmp_node.ops:
        if _append_fragile(op, left_paths, right_paths):
            store = sorted(left_paths | right_paths)[0]
            return True, f"{type(op).__name__} against content of {store}"
    return False, ""


def scan_file(path: Path, rel: str, stores: dict[str, Store]) -> list[Hit]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # Cheap prefilter: the file must name at least one classified store's file
    # name, otherwise no anchored Path expression in it can resolve to one.
    if not any(Path(p).name in text for p in stores):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    root_names = _root_names(tree)
    if not root_names and "Path(" not in text:
        return []

    # Outer scope = module body plus every class body, minus the function bodies
    # nested inside them. A module-level `LEDGER = REPO / "data" / …` and a
    # class-level `SIDECAR = …` are both constants the methods below inherit.
    outer_body: list[ast.stmt] = list(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            outer_body.extend(node.body)
    outer_taint = _collect_taint(outer_body, root_names, stores, {})

    hits: list[Hit] = []
    scopes: list[tuple[list[ast.stmt], dict[str, set[str]]]] = [(outer_body, outer_taint)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Parameters are INPUTS (tmp_path, monkeypatch, …) — never a live store.
            local_seed = {k: v for k, v in outer_taint.items()}
            for arg in node.args.args + node.args.kwonlyargs:
                local_seed.pop(arg.arg, None)
            scopes.append((node.body, _collect_taint(node.body, root_names, stores, local_seed)))

    seen: set[tuple[int, str]] = set()
    for body, taint in scopes:
        for stmt in body:
            for sub in _walk_scope(stmt):
                if isinstance(sub, ast.Assert):
                    for cmp_node in ast.walk(sub.test):
                        if not isinstance(cmp_node, ast.Compare):
                            continue
                        flag, detail = _classify_compare(cmp_node, taint, root_names, stores)
                        if flag and (sub.lineno, detail) not in seen:
                            seen.add((sub.lineno, detail))
                            hits.append(Hit(rel, sub.lineno, detail.split()[-1], detail))
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr in _ASSERT_METHODS and len(sub.args) >= 2:
                    left = _operand_paths(sub.args[0], taint, root_names, stores)
                    right = _operand_paths(sub.args[1], taint, root_names, stores)
                    if (left or right) and _append_fragile(
                        _ASSERT_METHODS[sub.func.attr](), left, right
                    ):
                        store = sorted(left | right)[0]
                        detail = f"{sub.func.attr} against content of {store}"
                        if (sub.lineno, detail) not in seen:
                            seen.add((sub.lineno, detail))
                            hits.append(Hit(rel, sub.lineno, store, detail))
    return hits


def scan_tree(root: Path, stores: dict[str, Store]) -> list[Hit]:
    hits: list[Hit] = []
    for rel_dir in SCAN_DIRS:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if "/fixtures/" in rel or "/golden/" in rel:
                continue
            hits.extend(scan_file(path, rel, stores))
    return sorted(hits, key=lambda h: (h.file, h.line))


# --------------------------------------------------------------------------- #
# Selftest
# --------------------------------------------------------------------------- #
_SELFTEST_STORES = {
    "data/prophet/ledger.jsonl": Store("data/prophet/ledger.jsonl", "A", "selftest"),
}

_POSITIVE = '''
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "data" / "prophet" / "ledger.jsonl"
SIDECAR = REPO / "docs" / "frozen.jsonl"

def test_every_closed_plan_is_accounted_for():
    ledger_ids = {r["id"] for r in read_jsonl(LEDGER)}
    graded_ids = {r["id"] for r in read_jsonl(SIDECAR)}
    assert ledger_ids and ledger_ids <= graded_ids
'''

_NEGATIVE_FIXTURE = '''
from pathlib import Path

def test_writer_appends(tmp_path):
    LEDGER = tmp_path / "data" / "prophet" / "ledger.jsonl"
    LEDGER.write_text("{}")
    rows = read_jsonl(LEDGER)
    assert len(rows) == 1
    assert {r["id"] for r in rows} == {"a"}
'''

_NEGATIVE_FLOOR = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_ledger_has_a_floor():
    rows = read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl")
    assert len(rows) >= 28, "rows are append-only; assert a floor, never an equality"
'''

_NEGATIVE_SCHEMA = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_every_row_parses():
    for row in read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl"):
        assert set(row.keys()) == {"id", "asof"}
'''

_NEGATIVE_SAME_STORE = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "prophet" / "ledger.jsonl"

def test_reader_never_mutates():
    before = SOURCE.read_bytes()
    run_reader()
    assert SOURCE.read_bytes() == before
'''

_NEGATIVE_MEMBERSHIP = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_header_is_present():
    body = (ROOT / "data" / "prophet" / "ledger.jsonl").read_text()
    assert "NIGHTLY IS THE SOLE ADVANCER" in body
'''

_POSITIVE_EQUALITY = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_row_count():
    rows = read_jsonl(ROOT / "data" / "prophet" / "ledger.jsonl")
    assert len(rows) == 28
'''

_NEGATIVE_UNRELATED = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_unrelated():
    rows = read_jsonl(ROOT / "data" / "prophet" / "notes.md")
    assert len(rows) == 3
'''


def _scan_source(src: str, name: str) -> list[Hit]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / name
        p.write_text(src, encoding="utf-8")
        return scan_file(p, name, _SELFTEST_STORES)


def _selftest(root: Path) -> int:
    checks: list[tuple[str, bool]] = []

    checks.append((
        "POSITIVE: subset pin on a live append-only ledger fires",
        bool(_scan_source(_POSITIVE, "test_positive.py")),
    ))
    checks.append((
        "NEGATIVE: the same assertion on a tmp_path fixture store does NOT fire",
        not _scan_source(_NEGATIVE_FIXTURE, "test_fixture.py"),
    ))
    checks.append((
        "NEGATIVE: a documented `>= floor` does NOT fire",
        not _scan_source(_NEGATIVE_FLOOR, "test_floor.py"),
    ))
    checks.append((
        "NEGATIVE: a per-row key-set schema check does NOT fire",
        not _scan_source(_NEGATIVE_SCHEMA, "test_schema.py"),
    ))
    checks.append((
        "NEGATIVE: a within-run before/after byte guard does NOT fire",
        not _scan_source(_NEGATIVE_SAME_STORE, "test_same.py"),
    ))
    checks.append((
        "POSITIVE: `len(rows) == 28` on a live append-only ledger fires (defect 4)",
        bool(_scan_source(_POSITIVE_EQUALITY, "test_equality.py")),
    ))
    checks.append((
        "NEGATIVE: membership IN a live store does NOT fire (a row cannot un-appear)",
        not _scan_source(_NEGATIVE_MEMBERSHIP, "test_membership.py"),
    ))
    checks.append((
        "NEGATIVE: an equality pin on an UNCLASSIFIED path does NOT fire",
        not _scan_source(_NEGATIVE_UNRELATED, "test_unrelated.py"),
    ))

    stores = classify_stores(root)
    checks.append((
        "store classification finds data/qledger/claims.jsonl (motivating defect 1-2)",
        "data/qledger/claims.jsonl" in stores,
    ))
    checks.append((
        "store classification finds data/prophet/ledger.jsonl (motivating defect 3)",
        "data/prophet/ledger.jsonl" in stores,
    ))
    checks.append((
        "'daily-engine' is in the nightly-lane vocabulary (both defects live there)",
        "daily-engine" in NIGHTLY_CADENCES,
    ))
    checks.append((
        "prose signal B classifies at least one non-nightly-cadence store",
        any(s.signal == "B" for s in stores.values()),
    ))

    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}", flush=True)
        ok = ok and passed
    print(
        f"selftest: {'PASS' if ok else 'FAIL'} "
        f"({sum(1 for _, p in checks if p)}/{len(checks)})",
        flush=True,
    )
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when any assertion is flagged (not the CI default).")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list-stores", action="store_true",
                        help="Print the derived append-only store set and exit.")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()

    if args.selftest:
        return _selftest(root)

    stores = classify_stores(root)
    if not stores:
        print(
            "::notice title=append-only-assertions::config/synapse.yml absent or "
            f"unparseable under {root}; NOT scanned",
            flush=True,
        )
        return 0

    if args.list_stores:
        for path, store in sorted(stores.items()):
            print(f"{store.signal}  {path}  ({store.why})", flush=True)
        print(f"{len(stores)} append-only store(s)", flush=True)
        return 0

    hits = scan_tree(root, stores)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "n_stores": len(stores),
                    "findings": [
                        {"file": h.file, "line": h.line, "store": h.store, "detail": h.detail}
                        for h in hits
                    ],
                },
                indent=2,
            ),
            flush=True,
        )
    else:
        for hit in hits:
            # Bare print, line-start, flushed — see module docstring.
            print(
                f"::warning file={hit.file},line={hit.line},"
                f"title=append-only-assertion::{hit.file}:{hit.line}: {hit.detail}. "
                f"A nightly lane appends to this store, so the assertion reds main "
                f"later with no PR author involved. Assert a floor, a schema, or a "
                f"receipt written by the same producer run.",
                flush=True,
            )
        print(
            f"append-only assertions: {len(hits)} finding(s) over "
            f"{len(stores)} classified store(s) in {'/'.join(SCAN_DIRS)}",
            flush=True,
        )

    if args.strict and hits:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
