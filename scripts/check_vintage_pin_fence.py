#!/usr/bin/env python3
"""Fail-closed fence: tests must not equality-pin a live nightly store.

A hand-typed ``== N`` / ``<= N`` against a store the nightly advances is how a
single data-plane commit reddens main and then, through merge-on-green, every
armed PR.  Measured 2026-08-13: government_revenue latest/candidates ``assert 23
== 8``, options ``episodes.jsonl`` 384→1206 used as a closed replay, prophet
open-keys ratchet 10→11.

Legal (this fence does not red):

  * freeze a WATERMARKED PREFIX (``rows[:N]`` / ``splitlines()[:N]``) and pin
    that slice, not the live tail;
  * derive the census from a committed receipt written by a different path
    (``canonical_*census()``, a ``*_receipt*.json`` load);
  * compare against a named disclosure SET of keys, not a count;
  * bind ``config.data_dir()`` to an empty tmp tree (the #5547 cold-test
    pattern) before pinning a census of a default-root reader.

Fail-closed: a test file that does not parse is a finding, not a skip.  The
live scan is a targeted ratchet over tests that read the stores named below;
it is not a general AST linter of every ``== 8`` in the tree.

Usage:
    python3 scripts/check_vintage_pin_fence.py            # gate (exit 1 on new pins)
    python3 scripts/check_vintage_pin_fence.py --selftest
    python3 scripts/check_vintage_pin_fence.py --dump-baseline
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Live stores the nightly advances.  A test that equality-pins a census of
# these is a time bomb; adding a store here is how the ratchet grows.
# 2026-08-13 after #5515: spine parquet (pack-7 / #5547) and Release Radar
# inflation-truth artifacts (unrun-release-forecast) detonated the same way
# as the original govrev/options/prophet trio.  Sibling jsonl/parquet logs
# and the tripwire latch are the same class: nightly-advanced, equality-pinned.
# Directory prefixes cover the whole tree; more specific rows listed first
# keep a distinct label (cpi_truth → inflation-truth).
LIVE_STORES: tuple[tuple[str, str], ...] = (
    ("data/government_revenue/latest.json", "govrev-latest"),
    ("data/government_revenue/candidate_queue.json", "govrev-candidates"),
    ("data/government_revenue/candidate_ledger.jsonl", "govrev-candidates"),
    ("data/options_signal_episode/episodes.jsonl", "options-episodes"),
    ("site/prophet/plans", "prophet-plans"),
    ("data/spine/predictions.parquet", "spine-predictions"),
    ("data/release_forecast/cpi_truth", "inflation-truth"),
    ("data/release_forecast", "release-forecast"),
    ("data/fred_vintage/release_targets", "release-targets"),
    ("data/vector/alerts.jsonl", "vector-alerts"),
    ("data/commodity/alerts.jsonl", "commodity-alerts"),
    ("data/alerts/alerts_log.parquet", "alerts-log"),
    ("data/cycle_ontology/tripwire_state.json", "tripwire-state"),
)

# Engine calls that read config.data_dir() by default (no root=).  A census pin
# against their return is the #5547 hole: the test never names the parquet path,
# so a LIVE_STORES-only scan misses it.  Explicit ``root=`` or a data_dir bind
# to tmp (fixture or monkeypatch) is legal.
_DEFAULT_ROOT_READERS: dict[str, str] = {
    "convergence_tier": "spine-predictions",
    "measured_ic": "spine-predictions",
}

# Shrink-only.  Fingerprints leave when the pin is gone.  Do not add a row to
# ship a new pin — that is the jam this fence exists to stop.  The three
# 2026-08-13 detonations (govrev ``== 8``, options whole-ledger ``== 384``,
# prophet ``<= 10``) were healed by #5524; these leftovers still equality-pin
# a live store and will warn-then-drop when a later PR converts them.  Stale
# rows warn; they never red.
BASELINE_FINGERPRINTS: frozenset[str] = frozenset(
    (
        'tests/test_government_revenue_candidates.py|govrev-latest|eq-literal|21|assert queue["counts"]["mapping_needed"] == 21',
        'tests/test_government_revenue_candidates.py|govrev-latest|eq-literal|21|assert len(queue["mapping_backlog"]) == 21',
        'tests/test_government_revenue_candidates.py|govrev-latest|eq-literal|19|assert queue["coverage"]["reviewed_issuer_company_count"] == 19',
        'tests/test_government_revenue_issuer_graph_expansion.py|govrev-latest|eq-literal|21|assert len(latest["companies"]) == 21',
        'tests/test_market_memory_production_records.py|options-episodes|eq-literal|384|assert len(stored.generation["records"]) == 384',
        'tests/test_market_memory_production_records.py|options-episodes|eq-literal|384|assert len(initial.generation["records"]) == 384',
        'tests/test_market_memory_production_records.py|options-episodes|eq-literal|385|assert len(forward.generation["records"]) == 385',
        'tests/test_market_memory_production_records.py|options-episodes|eq-literal|1|assert len(second.generation["captures"]) == 1',
    )
)

_LEGAL_CALL = ("census", "receipt")
_NUMERIC_OPS = (ast.Eq, ast.LtE, ast.Lt)


@dataclass(frozen=True)
class Finding:
    rel: str
    store: str
    kind: str
    literal: str
    lineno: int
    line: str

    @property
    def fingerprint(self) -> str:
        compact = " ".join(self.line.split())
        return f"{self.rel}|{self.store}|{self.kind}|{self.literal}|{compact}"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/")
    return None


def _const_int(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(
        node.value, bool
    ):
        return node.value
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _mentions_file(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


def _div_parts(node: ast.AST) -> list[ast.AST]:
    parts: list[ast.AST] = []
    cur: ast.AST = node
    while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
        parts.append(cur.right)
        cur = cur.left
    parts.append(cur)
    parts.reverse()
    return parts


def _store_for_suffix(suffix: str) -> str | None:
    normalized = suffix.replace("\\", "/").lstrip("./")
    for path, store in LIVE_STORES:
        if normalized == path or normalized.startswith(path.rstrip("/") + "/"):
            return store
        if path.startswith(normalized.rstrip("/") + "/") and normalized:
            # ROOT / "site/prophet/plans" matches the plans store exactly;
            # ROOT / "site/prophet" is too wide and is ignored.
            continue
    return None


def _joined_strings(parts: list[ast.AST]) -> str | None:
    bits: list[str] = []
    for part in parts:
        text = _const_str(part)
        if text is None:
            return None
        bits.append(text.strip("/"))
    return "/".join(bits)


def _is_slice_sub(node: ast.AST) -> bool:
    return isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice)


def _is_legal_call(name: str) -> bool:
    lowered = name.lower()
    return "census" in lowered or "receipt" in lowered


def _is_data_dir_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == "data_dir"


def _default_reader_store(node: ast.Call) -> str | None:
    """Store label for a default-root engine call, or None if root= was passed."""
    store = _DEFAULT_ROOT_READERS.get(_call_name(node))
    if not store:
        return None
    if any(kw.arg == "root" for kw in node.keywords):
        return None
    return store


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _is_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_decorator_name(dec) == "fixture" for dec in fn.decorator_list)


def _isolates_data_dir(fn: ast.AST) -> bool:
    """True when ``fn`` binds ``config.data_dir`` to a tmp tree (#5547)."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "setattr" and len(node.args) >= 2:
            attr = _const_str(node.args[1])
            if attr == "data_dir":
                return True
        if name in {"patch", "object"}:
            for arg in node.args:
                text = _const_str(arg)
                if text == "data_dir" or (text is not None and text.endswith(".data_dir")):
                    return True
            if any(
                kw.arg in {"attribute", "target"} and _const_str(kw.value) == "data_dir"
                for kw in node.keywords
            ):
                return True
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "object"
                and any(_const_str(arg) == "data_dir" for arg in node.args)
            ):
                return True
    return False


def scan_text(source: str, *, rel: str) -> list[Finding]:
    """Return vintage-pin findings in ``source`` (a single test module)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Finding(
                rel=rel,
                store="parse",
                kind="syntax-error",
                literal="",
                lineno=exc.lineno or 1,
                line=source.splitlines()[(exc.lineno or 1) - 1] if source else "",
            )
        ]

    lines = source.splitlines()
    root_names: set[str] = set()
    int_names: dict[str, int] = {}
    prefix_names: set[str] = set()
    source_names: set[str] = set()
    tainted_names: set[str] = set()
    tainted_funcs: set[str] = set()
    legal_names: set[str] = set()
    name_stores: dict[str, str] = {}
    func_stores: dict[str, str] = {}
    file_stores: set[str] = set()
    isolated_fixtures: set[str] = set()
    isolated_here = [False]
    data_dir_names: set[str] = set()

    def _line(lineno: int) -> str:
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1]
        return ""

    def _bind_targets(target: ast.AST, names: set[str]) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _bind_targets(elt, names)

    def _unbind_targets(target: ast.AST, names: set[str]) -> None:
        if isinstance(target, ast.Name):
            names.discard(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _unbind_targets(elt, names)

    # Repo-root names: anything assigned from a Path(__file__) chain.
    for node in tree.body:
        if isinstance(node, ast.Assign) and _mentions_file(node.value):
            _bind_targets(node.targets[0], root_names)

    def _collect_isolated_fixtures(fns: list[ast.AST]) -> None:
        for fn in fns:
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_fixture(fn):
                if _isolates_data_dir(fn):
                    isolated_fixtures.add(fn.name)

    _collect_isolated_fixtures(list(tree.body))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _collect_isolated_fixtures(list(node.body))

    def _fn_isolated(fn: ast.AST) -> bool:
        if _isolates_data_dir(fn):
            return True
        args = getattr(fn, "args", None)
        if args is None:
            return False
        names = [arg.arg for arg in list(args.args) + list(args.kwonlyargs)]
        if args.vararg is not None:
            names.append(args.vararg.arg)
        if args.kwarg is not None:
            names.append(args.kwarg.arg)
        return any(name in isolated_fixtures for name in names)

    def _store_of(node: ast.AST) -> str | None:
        parts = _div_parts(node)
        if not parts:
            return None
        head = parts[0]
        if _is_data_dir_call(head) and not isolated_here[0]:
            suffix = _joined_strings(parts[1:])
            if suffix:
                return _store_for_suffix("data/" + suffix)
            return None
        if isinstance(head, ast.Name) and head.id in data_dir_names and not isolated_here[0]:
            suffix = _joined_strings(parts[1:])
            if suffix:
                return _store_for_suffix("data/" + suffix)
            return None
        if isinstance(head, ast.Name) and head.id in root_names:
            suffix = _joined_strings(parts[1:])
            if suffix:
                return _store_for_suffix(suffix)
            # ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
            bits: list[str] = []
            for part in parts[1:]:
                text = _const_str(part)
                if text is None:
                    return None
                bits.append(text.strip("/"))
            return _store_for_suffix("/".join(bits))
        if isinstance(head, ast.Name) and head.id in source_names:
            return name_stores.get(head.id, "via-source-name")
        return None

    def _record_store(target: ast.AST, store: str | None) -> None:
        if not store or store == "via-source-name":
            return
        file_stores.add(store)
        if isinstance(target, ast.Name):
            name_stores[target.id] = store
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _record_store(elt, store)

    def _expr_store(node: ast.AST) -> str | None:
        direct = _store_of(node)
        if direct and direct != "via-source-name":
            return direct
        if isinstance(node, ast.Name):
            if node.id in name_stores:
                return name_stores[node.id]
            if node.id in source_names:
                return "via-source-name"
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if not isolated_here[0]:
                reader = _default_reader_store(node)
                if reader:
                    return reader
            if name in func_stores:
                return func_stores[name]
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                inner = _expr_store(arg)
                if inner and inner != "via-source-name":
                    return inner
            if isinstance(node.func, ast.Attribute):
                return _expr_store(node.func.value)
            return None
        if isinstance(node, ast.Attribute):
            return _expr_store(node.value)
        if isinstance(node, ast.Subscript):
            return _expr_store(node.value)
        return direct

    def _ingest_assign(node: ast.Assign) -> bool:
        grew = False
        store = _store_of(node.value) or _expr_store(node.value)
        if store or _tainted(node.value):
            before = set(tainted_names)
            _bind_targets(node.targets[0], tainted_names)
            if store:
                _bind_targets(node.targets[0], source_names)
                _record_store(node.targets[0], store)
            else:
                _record_store(node.targets[0], _expr_store(node.value))
            if _is_slice_sub(node.value):
                _bind_targets(node.targets[0], prefix_names)
            if tainted_names != before:
                grew = True
        if _is_slice_sub(node.value):
            _bind_targets(node.targets[0], prefix_names)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            number = _const_int(node.value)
            if number is not None:
                int_names[node.targets[0].id] = number
            if isinstance(node.value, ast.Call) and _is_legal_call(_call_name(node.value)):
                legal_names.add(node.targets[0].id)
        if (
            _is_data_dir_call(node.value)
            or (isinstance(node.value, ast.Name) and node.value.id in data_dir_names)
        ):
            _bind_targets(node.targets[0], data_dir_names)
        return grew

    for node in ast.walk(tree):
        store = _store_of(node)
        if store and store != "via-source-name":
            file_stores.add(store)

    def _fn_reads_store(fn: ast.AST) -> str | None:
        for child in ast.walk(fn):
            store = _store_of(child)
            if store and store != "via-source-name":
                return store
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id in source_names
                and child.func.attr in {
                    "read_text", "read_bytes", "glob", "iterdir", "open",
                    "read_parquet",
                }
            ):
                return name_stores.get(child.func.value.id, "via-source-name")
            if isinstance(child, ast.Call) and _call_name(child) == "read_parquet":
                for arg in list(child.args) + [kw.value for kw in child.keywords]:
                    store = _store_of(arg) or _expr_store(arg)
                    if store and store != "via-source-name":
                        return store
            if isinstance(child, ast.Call):
                name = _call_name(child)
                if name in func_stores:
                    return func_stores[name]
                if name in tainted_funcs:
                    return "via-source-name"
        return None

    def _is_prefix(node: ast.AST) -> bool:
        if _is_slice_sub(node):
            return True
        if isinstance(node, ast.Name) and node.id in prefix_names:
            return True
        if isinstance(node, ast.Call) and _call_name(node) == "len" and node.args:
            return _is_prefix(node.args[0])
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "splitlines"
        ):
            return _is_prefix(node.func.value)
        return False

    def _tainted(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in tainted_names
        if isinstance(node, ast.Call):
            return _taint_call(node)
        store = _expr_store(node)
        if store:
            return True
        if isinstance(node, ast.Attribute):
            return _tainted(node.value)
        if isinstance(node, ast.Subscript):
            return _tainted(node.value)
        if isinstance(node, ast.BinOp):
            return _tainted(node.left) or _tainted(node.right)
        if isinstance(node, ast.UnaryOp):
            return _tainted(node.operand)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return any(_tainted(elt) for elt in node.elts)
        if isinstance(node, ast.Dict):
            return any(_tainted(v) for v in node.values if v is not None)
        if isinstance(node, ast.ListComp):
            return _tainted(node.elt) or any(
                _tainted(gen.iter) for gen in node.generators
            )
        if isinstance(node, ast.DictComp):
            return (
                _tainted(node.key)
                or _tainted(node.value)
                or any(_tainted(gen.iter) for gen in node.generators)
            )
        if isinstance(node, ast.SetComp):
            return _tainted(node.elt) or any(
                _tainted(gen.iter) for gen in node.generators
            )
        if isinstance(node, ast.GeneratorExp):
            return _tainted(node.elt) or any(
                _tainted(gen.iter) for gen in node.generators
            )
        if isinstance(node, ast.IfExp):
            return _tainted(node.body) or _tainted(node.orelse)
        return False

    def _taint_call(node: ast.Call) -> bool:
        """Spread taint only through reads, json loads, and census builders.

        Arbitrary ``fn(live_row)`` must NOT taint: that is how a single
        ``BASE_EPISODE = first_row(live_ledger)`` hostage every synthetic
        ``== 2`` in the file.
        """
        name = _call_name(node)
        if not isolated_here[0]:
            reader = _default_reader_store(node)
            if reader:
                return True
        if name in tainted_funcs:
            return True
        lowered = name.lower()
        if name in {
            "loads", "load", "len", "list", "dict", "set", "tuple", "sorted",
            "read_parquet",
        }:
            return any(_tainted(arg) for arg in node.args)
        if "queue" in lowered or "census" in lowered:
            return any(_tainted(arg) for arg in node.args) or any(
                _tainted(kw.value) for kw in node.keywords
            )
        if isinstance(node.func, ast.Attribute) and _tainted(node.func.value):
            if name in {
                "write_text", "write_bytes", "unlink", "mkdir", "exists",
                "rename", "replace", "touch",
            }:
                return False
            return True
        return False

    # Module-level sources only.  A local `rows = json.loads(live)` must not
    # taint every other `rows` in the file.
    for node in tree.body:
        if isinstance(node, ast.Assign):
            _ingest_assign(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.Assign):
                    _ingest_assign(child)
        label = _store_of(node) if isinstance(node, ast.BinOp) else None
        if label and label != "via-source-name":
            file_stores.add(label)
    for node in ast.walk(tree):
        store = _store_of(node)
        if store and store != "via-source-name":
            file_stores.add(store)

    grew_funcs = True
    while grew_funcs:
        grew_funcs = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("test"):
                continue
            store = _fn_reads_store(node)
            if not store or node.name in tainted_funcs:
                continue
            tainted_funcs.add(node.name)
            if store != "via-source-name":
                func_stores[node.name] = store
            grew_funcs = True

    module_tainted = set(tainted_names)
    module_prefix = set(prefix_names)
    module_sources = set(source_names)
    module_name_stores = dict(name_stores)
    module_int_names = dict(int_names)
    module_legal = set(legal_names)
    module_file_stores = set(file_stores)
    module_data_dir_names = set(data_dir_names)

    # Per-function taint so one test's `rows = live_ledger` cannot pin another.
    def _spread_in(fn: ast.AST) -> None:
        changed = True
        while changed:
            changed = False
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign) and _ingest_assign(node):
                    changed = True
                elif isinstance(node, ast.AnnAssign) and node.value is not None and _tainted(
                    node.value
                ):
                    if isinstance(node.target, ast.Name) and node.target.id not in tainted_names:
                        tainted_names.add(node.target.id)
                        changed = True
                elif isinstance(node, ast.AugAssign) and _tainted(node.value):
                    if isinstance(node.target, ast.Name) and node.target.id not in tainted_names:
                        tainted_names.add(node.target.id)
                        changed = True

    def _scan_compares(fn: ast.AST) -> None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare):
                _consider(node)

    def _reset_locals() -> None:
        tainted_names.clear()
        tainted_names.update(module_tainted)
        prefix_names.clear()
        prefix_names.update(module_prefix)
        source_names.clear()
        source_names.update(module_sources)
        name_stores.clear()
        name_stores.update(module_name_stores)
        int_names.clear()
        int_names.update(module_int_names)
        legal_names.clear()
        legal_names.update(module_legal)
        file_stores.clear()
        file_stores.update(module_file_stores)
        data_dir_names.clear()
        data_dir_names.update(module_data_dir_names)

    # Fixpoint: assignments and same-file returns spread taint.
    def _bound_int(node: ast.AST) -> int | None:
        direct = _const_int(node)
        if direct is not None:
            return direct
        if isinstance(node, ast.Name) and node.id in int_names:
            if node.id in legal_names:
                return None
            return int_names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = _bound_int(node.operand)
            return None if inner is None else -inner
        return None

    def _kind_for(op: ast.cmpop) -> str | None:
        if isinstance(op, ast.Eq):
            return "eq-literal"
        if isinstance(op, (ast.LtE, ast.Lt)):
            return "upper-bound-literal"
        return None

    def _store_label(node: ast.AST) -> str:
        store = _expr_store(node)
        if store and store != "via-source-name":
            return store
        for child in ast.walk(node):
            inner = _expr_store(child)
            if inner and inner != "via-source-name":
                return inner
        if len(file_stores) == 1:
            return next(iter(file_stores))
        for preferred in (
            "govrev-latest",
            "govrev-candidates",
            "options-episodes",
            "prophet-plans",
            "spine-predictions",
            "release-forecast",
            "inflation-truth",
            "vector-alerts",
            "commodity-alerts",
            "alerts-log",
            "tripwire-state",
        ):
            if preferred in file_stores:
                return preferred
        return "live-store"

    findings: list[Finding] = []

    def _consider(cmp: ast.Compare) -> None:
        # Python chains `a >= b == c` as (a >= b) and (b == c). Only the
        # comparison whose left side is the live census is a pin; pinning
        # ACTIVATION_PREFIX_ROWS == 384 while flooring len(live) >= PREFIX
        # is legal.
        left: ast.AST = cmp.left
        for op, rhs in zip(cmp.ops, cmp.comparators):
            if (
                _tainted(left)
                and not _is_prefix(left)
                and not (isinstance(left, ast.Name) and left.id in legal_names)
                and not (isinstance(left, ast.Call) and _is_legal_call(_call_name(left)))
            ):
                kind = _kind_for(op)
                if (
                    kind is not None
                    and not (isinstance(rhs, ast.Call) and _is_legal_call(_call_name(rhs)))
                    and not (isinstance(rhs, ast.Name) and rhs.id in legal_names)
                ):
                    bound = _bound_int(rhs)
                    if bound is not None:
                        findings.append(
                            Finding(
                                rel=rel,
                                store=_store_label(left),
                                kind=kind,
                                literal=str(bound),
                                lineno=cmp.lineno,
                                line=_line(cmp.lineno),
                            )
                        )
            left = rhs

    def _scan_fn(fn: ast.AST) -> None:
        isolated_here[0] = _fn_isolated(fn)
        _spread_in(fn)
        _scan_compares(fn)
        isolated_here[0] = False
        _reset_locals()

    # Module-level compares are rare; most pins live inside test functions.
    # Do not walk into functions here — that would mix every test's locals.
    for node in tree.body:
        if isinstance(node, ast.Compare):
            _consider(node)
        elif isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            _consider(node.test)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Compare):
            _consider(node.value)
        elif isinstance(node, ast.Assign):
            for child in ast.walk(node):
                if isinstance(child, ast.Compare):
                    _consider(child)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_fn(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _scan_fn(child)

    # Dedup identical fingerprints (chained compares can emit twice).
    seen_fp: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        fp = finding.fingerprint
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        unique.append(finding)
    return unique


def _text_names_store(text: str) -> bool:
    """Cheap prefilter so we AST-parse only tests that name a live store."""
    normalized = text.replace("\\", "/")
    for path, _store in LIVE_STORES:
        if path in normalized:
            return True
        parts = path.split("/")
        if parts and all(
            (f'"{part}"' in text) or (f"'{part}'" in text) for part in parts
        ):
            return True
    if "data_dir" in text:
        return True
    return any(reader in text for reader in _DEFAULT_ROOT_READERS)


def scan_path(path: Path, *, root: Path = ROOT) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    if not _text_names_store(text):
        return []
    return scan_text(text, rel=_rel(path, root))


def iter_test_files(root: Path = ROOT) -> list[Path]:
    """Yield pytest modules under tests/.  The rglob is load-bearing for CI scope."""
    tests_root = root / "tests"
    return sorted(tests_root.rglob("test_*.py"))


def scan_tree(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_test_files(root):
        findings.extend(scan_path(path, root=root))
    return findings


def _emit(findings: list[Finding], *, stale: list[str]) -> int:
    if stale:
        for fp in stale:
            print(
                f"::warning title=vintage-pin-stale::baseline row no longer matches "
                f"a pin (prune it): {fp}",
                flush=True,
            )
    if not findings:
        print("OK — no new live-store equality pins.")
        return 0
    for finding in findings:
        print(
            f"::error title=vintage-pin::{finding.rel}:{finding.lineno}: "
            f"{finding.kind} {finding.literal} against {finding.store} — "
            f"freeze a watermarked prefix, derive the census from a committed "
            f"receipt, or use a named disclosure set.  {finding.line.strip()}",
            flush=True,
        )
    print(
        f"{len(findings)} new vintage-pin(s). A hand-typed == N / <= N against a "
        "nightly-advanced store will hostage the armed queue the next time the "
        "store grows."
    )
    return 1


def _selftest() -> int:
    failures: list[str] = []

    govrev_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_current_source_truth_is_eight_candidates():
    latest = json.loads((ROOT / "data/government_revenue/latest.json").read_text())
    queue = build_candidate_queue(latest)
    assert queue["counts"]["total"] == 8
'''
    found = scan_text(govrev_bad, rel="tests/test_govrev_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "8" and f.store == "govrev-latest" for f in found):
        failures.append(f"govrev assert 23==8 / ==8 against latest not caught: {found}")

    options_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_live_ledger_as_closed_replay():
    body = SOURCE.read_text()
    assert len(body.splitlines()) == 384
'''
    found = scan_text(options_bad, rel="tests/test_options_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "384" and f.store == "options-episodes" for f in found):
        failures.append(f"options 384→1206 live-ledger pin not caught: {found}")

    prophet_bad = '''
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
REAL_PLANS_DIR = _REPO / "site/prophet/plans"
_LEGACY_DOUBLED_KEYS = 10
def _open_keys():
    keys = {}
    for path in REAL_PLANS_DIR.glob("*.json"):
        keys.setdefault(path.stem, []).append(path)
    return keys
def test_the_legacy_duplicate_open_keys_do_not_grow():
    doubled = {k: v for k, v in _open_keys().items() if len(v) > 1}
    assert len(doubled) <= _LEGACY_DOUBLED_KEYS
    assert len(doubled) == 10
'''
    found = scan_text(prophet_bad, rel="tests/test_prophet_pin.py")
    if not any(f.kind == "upper-bound-literal" and f.literal == "10" for f in found):
        failures.append(f"prophet open-keys <=10 ratchet not caught: {found}")
    if not any(f.kind == "eq-literal" and f.literal == "10" for f in found):
        failures.append(f"prophet open-keys ==10 pin not caught: {found}")

    prophet_helper_chain = '''
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
REAL_PLANS_DIR = _REPO / "site" / "prophet" / "plans"
_LEGACY_DOUBLED_KEYS = 10
def _real_plans():
    return {p.stem: {} for p in REAL_PLANS_DIR.glob("*.json")}
class TestOnePlanPerEpisodeOnTheShippedTree:
    @staticmethod
    def _open_keys():
        keys = {}
        for plan in _real_plans().values():
            keys.setdefault("k", []).append(plan)
        return keys
    def test_the_legacy_duplicate_open_keys_do_not_grow(self):
        doubled = {k: v for k, v in self._open_keys().items() if len(v) > 1}
        assert len(doubled) <= _LEGACY_DOUBLED_KEYS
'''
    found = scan_text(prophet_helper_chain, rel="tests/test_prophet_helper_chain.py")
    if not any(f.kind == "upper-bound-literal" and f.literal == "10" for f in found):
        failures.append(f"prophet helper-chain <=10 ratchet not caught: {found}")

    prefix_ok = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
ACTIVATION_PREFIX_ROWS = 384
def test_frozen_prefix():
    lines = SOURCE.read_text().splitlines()[:ACTIVATION_PREFIX_ROWS]
    assert len(lines) == ACTIVATION_PREFIX_ROWS
'''
    found = scan_text(prefix_ok, rel="tests/test_options_prefix.py")
    if found:
        failures.append(f"watermarked prefix was flagged: {found}")

    floor_chain_ok = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
ACTIVATION_PREFIX_ROWS = 384
def test_live_is_at_least_the_frozen_prefix():
    live = SOURCE.read_text().splitlines()
    assert len(live) >= ACTIVATION_PREFIX_ROWS == 384
'''
    found = scan_text(floor_chain_ok, rel="tests/test_options_floor_chain.py")
    if found:
        failures.append(f"live >= PREFIX == N floor chain was flagged: {found}")

    census_ok = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def canonical_candidate_census():
    return json.loads((ROOT / "research" / "govrev_receipt.json").read_text())["n"]
def test_derived_census():
    latest = json.loads((ROOT / "data/government_revenue/latest.json").read_text())
    assert len(latest["candidates"]) == canonical_candidate_census()
'''
    found = scan_text(census_ok, rel="tests/test_govrev_census.py")
    if found:
        failures.append(f"canonical census derivation was flagged: {found}")

    disclosure_ok = '''
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
REAL_PLANS_DIR = _REPO / "site/prophet/plans"
DISCLOSED_DUPLICATE_KEYS = frozenset({"FCX-BULL-20260731", "MDB-BULL-20260731"})
def _open_keys():
    return {p.stem: [p] for p in REAL_PLANS_DIR.glob("*.json")}
def test_named_disclosure_set():
    doubled = {k for k, v in _open_keys().items() if len(v) > 1}
    assert doubled <= DISCLOSED_DUPLICATE_KEYS
'''
    found = scan_text(disclosure_ok, rel="tests/test_prophet_disclosure.py")
    if found:
        failures.append(f"named disclosure set was flagged: {found}")

    # A PREFIX in the function NAME is not a watermarked slice. This is the
    # 384→1206 bomb wearing a PREFIX label.
    prefix_name_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_frozen_owner_prefix_matches_the_reviewed_384_rows():
    body = SOURCE.read_text()
    assert len(body.splitlines()) == 384
'''
    found = scan_text(prefix_name_bad, rel="tests/test_options_named_prefix.py")
    if not any(f.kind == "eq-literal" and f.literal == "384" for f in found):
        failures.append(f"whole-ledger pin wearing a PREFIX name was missed: {found}")

    isolated_ok = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
def test_reads_the_live_ledger():
    rows = SOURCE.read_text().splitlines()
    assert len(rows) == 384
def test_synthetic_pair_has_two_rows():
    rows = [{"id": 1}, {"id": 2}]
    assert len(rows) == 2
'''
    found = scan_text(isolated_ok, rel="tests/test_options_isolate.py")
    if any(f.literal == "2" for f in found):
        failures.append(f"synthetic ==2 was hostage by another test's rows: {found}")
    if not any(f.literal == "384" for f in found):
        failures.append(f"live-ledger ==384 in the sibling test was missed: {found}")

    spine_named_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_pins_live_parquet_len():
    df = pd.read_parquet(ROOT / "data" / "spine" / "predictions.parquet")
    assert len(df) == 58
'''
    found = scan_text(spine_named_bad, rel="tests/test_spine_named_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "58" and f.store == "spine-predictions" for f in found):
        failures.append(f"spine parquet 58-row pin not caught: {found}")

    spine_reader_bad = '''
from engine import altdata_signals as a
def test_convergence_tier_accrual_aware_basis():
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    assert t["n_scored"] == 0
'''
    found = scan_text(spine_reader_bad, rel="tests/test_spine_reader_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "0" and f.store == "spine-predictions" for f in found):
        failures.append(f"spine default-root n_scored==0 pin not caught: {found}")

    spine_cold_ok = '''
import pytest
from lib import config
from engine import altdata_signals as a
@pytest.fixture()
def spine_root(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    return tmp_path
def test_convergence_tier_accrual_aware_basis(spine_root):
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    assert t["n_scored"] == 0
'''
    found = scan_text(spine_cold_ok, rel="tests/test_spine_cold_ok.py")
    if found:
        failures.append(f"#5547 cold data_dir bind was flagged: {found}")

    spine_inline_ok = '''
from lib import config
from engine import altdata_signals as a
def test_chip_shaping(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    t = a.convergence_tier(["material_8k"], trump=False)
    assert t["n_scored"] == 0
'''
    found = scan_text(spine_inline_ok, rel="tests/test_spine_inline_ok.py")
    if found:
        failures.append(f"inline data_dir monkeypatch was flagged: {found}")

    spine_root_kw_ok = '''
from engine import spine
def test_measured_ic_with_explicit_root(root):
    m = spine.measured_ic(root=root, engine="e")
    assert m["n_scored"] == 0
'''
    found = scan_text(spine_root_kw_ok, rel="tests/test_spine_root_kw.py")
    if found:
        failures.append(f"explicit root= cold-test was flagged: {found}")

    release_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_latest_release_count():
    latest = json.loads((ROOT / "data/release_forecast/latest.json").read_text())
    assert len(latest["releases"]) == 12
'''
    found = scan_text(release_bad, rel="tests/test_release_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "12" and f.store == "release-forecast" for f in found):
        failures.append(f"release-forecast latest.json ==12 pin not caught: {found}")

    inflation_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_cpi_truth_files():
    files = list((ROOT / "data/release_forecast/cpi_truth").glob("*.json"))
    assert len(files) == 4
'''
    found = scan_text(inflation_bad, rel="tests/test_inflation_truth_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "4" and f.store == "inflation-truth" for f in found):
        failures.append(f"inflation-truth cpi_truth ==4 pin not caught: {found}")

    spine_data_dir_join_bad = '''
from lib import config
def test_pins_via_data_dir_join():
    df = pd.read_parquet(config.data_dir() / "spine" / "predictions.parquet")
    assert len(df) == 58
'''
    found = scan_text(spine_data_dir_join_bad, rel="tests/test_spine_data_dir_join.py")
    if not any(f.kind == "eq-literal" and f.literal == "58" and f.store == "spine-predictions" for f in found):
        failures.append(f"data_dir()/spine/predictions.parquet ==58 pin not caught: {found}")

    spine_parquet_loader_bad = '''
from lib import config
def test_pins_via_assigned_parquet_loader():
    d = config.data_dir()
    path = d / "spine" / "predictions.parquet"
    df = pd.read_parquet(path)
    assert len(df) == 58
'''
    found = scan_text(spine_parquet_loader_bad, rel="tests/test_spine_parquet_loader.py")
    if not any(f.kind == "eq-literal" and f.literal == "58" and f.store == "spine-predictions" for f in found):
        failures.append(f"assigned data_dir parquet loader ==58 pin not caught: {found}")

    release_tree_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_snapshot_count():
    files = list((ROOT / "data/release_forecast/input_snapshots").glob("*.json"))
    assert len(files) == 40
'''
    found = scan_text(release_tree_bad, rel="tests/test_release_tree_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "40" and f.store == "release-forecast" for f in found):
        failures.append(f"release_forecast/input_snapshots ==40 pin not caught: {found}")

    release_targets_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_release_target_files():
    files = list((ROOT / "data/fred_vintage/release_targets").glob("*.parquet"))
    assert len(files) == 3
'''
    found = scan_text(release_targets_bad, rel="tests/test_release_targets_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "3" and f.store == "release-targets" for f in found):
        failures.append(f"fred_vintage/release_targets ==3 pin not caught: {found}")

    alerts_log_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_live_alerts_log_len():
    df = pd.read_parquet(ROOT / "data" / "alerts" / "alerts_log.parquet")
    assert len(df) == 12
'''
    found = scan_text(alerts_log_bad, rel="tests/test_alerts_log_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "12" and f.store == "alerts-log" for f in found):
        failures.append(f"alerts_log.parquet ==12 pin not caught: {found}")

    alerts_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_hub_feed_macro_count():
    rows = (ROOT / "data/vector/alerts.jsonl").read_text().splitlines()
    assert len(rows) == 12
'''
    found = scan_text(alerts_bad, rel="tests/test_vector_alerts_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "12" and f.store == "vector-alerts" for f in found):
        failures.append(f"vector alerts jsonl ==12 pin not caught: {found}")

    tripwire_bad = '''
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_latched_tripwire_count():
    state = json.loads((ROOT / "data/cycle_ontology/tripwire_state.json").read_text())
    assert len(state) == 24
'''
    found = scan_text(tripwire_bad, rel="tests/test_tripwire_pin.py")
    if not any(f.kind == "eq-literal" and f.literal == "24" and f.store == "tripwire-state" for f in found):
        failures.append(f"tripwire_state ==24 pin not caught: {found}")

    if failures:
        for item in failures:
            print(f"::error title=vintage-pin-selftest::{item}", flush=True)
        return 1
    print("selftest OK — post-5515 detonation classes red, legal patterns green")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--dump-baseline",
        action="store_true",
        help="print current fingerprints (for freezing a shrink-only baseline)",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    root = args.root
    findings = scan_tree(root)
    if args.dump_baseline:
        for finding in findings:
            print(finding.fingerprint)
        return 0
    current = {f.fingerprint for f in findings}
    new = [f for f in findings if f.fingerprint not in BASELINE_FINGERPRINTS]
    stale = sorted(BASELINE_FINGERPRINTS - current)
    return _emit(new, stale=stale)


if __name__ == "__main__":
    sys.exit(main())
