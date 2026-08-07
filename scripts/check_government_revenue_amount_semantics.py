#!/usr/bin/env python3
"""Guard: Government Revenue dollar figures of different CLASSES never become one number.

The rule this enforces is the lobe's central financial-honesty claim, written twice as
prose and, until this file, enforced by nothing:

    "obligation, outlay, ceiling, bookings, backlog, funded backlog, and GAAP revenue
     are never conflated"      — GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md
    "funded obligations are never conflated with ceilings, appropriations,
     announcements, or GAAP revenue"  — GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md

The classes, and which pairs are dangerous, live in ONE place —
``engine/government_revenue/amount_semantics.py`` — whose coverage is DERIVED from the
collector's own canonical number-column declarations, so a field cannot join a ledger
without a class.  This file is the reader that holds the source tree to it.

WHAT IS A VIOLATION

  mixed_class_sum       ``+`` (or ``sum()``/``fsum``) across two classes.  Adding a
                        transaction delta to an award cumulative double-counts; adding a
                        ceiling to an obligation reports authorised capacity as activity;
                        adding an outlay to an obligation counts the committed dollar
                        again when it is paid.
  mixed_class_fallback  A fallback LADDER whose rungs are different classes —
                        ``("total_obligated", "award_amount", "current_award_amount")``
                        yields an obligation on most rows and a CEILING on the rows where
                        only the last rung survives, under one output name, with no trace
                        of which happened.  The quietest of the four mixes.
  mixed_class_default   ``row.get("a", row.get("b"))`` / ``a or b`` across classes — a
                        two-rung ladder wearing different syntax.
  unlabelled_figure     A published amount fact that carries the number but not the class:
                        no ``semantic``/``label_code``, or one belonging to another class.
                        The v2 contract types ``semantic`` as a free string, so this is
                        the only place the label is held to the field it describes.

WHAT IS DELIBERATELY *NOT* A VIOLATION

  SUBTRACTION across classes.  ``potential_award_amount - total_obligated`` is the
  lobe's defined headroom ("observed potential capacity"), and
  ``obligation - outlay`` is the unliquidated balance.  Both are real quantities with
  published basis copy.  It is ADDITION that has no definition — you cannot total two
  measurements of different things.  A guard that flagged subtraction would be wrong
  about finance, and a guard that is wrong gets switched off.

  Unknown names.  A name with no declared class contributes NOTHING; silence is
  "unknown", not "compatible".  Guessing would manufacture findings, and the point of
  this file is that its findings are real.

  Two figures of different classes rendered SIDE BY SIDE.  The dossier's
  Obligated / Current value / Potential ceiling row is the honest presentation, not the
  defect.  Only a single figure built from more than one class is a finding, which is why
  the template rule is scoped to one ``money(...)`` call's own argument.

Run:
    python3 scripts/check_government_revenue_amount_semantics.py            # gate, exit 1
    python3 scripts/check_government_revenue_amount_semantics.py --report   # census, exit 0
    python3 scripts/check_government_revenue_amount_semantics.py --selftest # prove it fires
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.government_revenue.amount_semantics import (  # noqa: E402
    AMOUNT_CLASSES,
    AmountClass,
    classify,
    classify_semantic,
    conflict_reason,
)

# Every first-party surface that builds or renders a Government Revenue dollar figure.
# Globs, not a hand-list: a new module in the lobe is scanned the day it lands.
PYTHON_GLOBS: tuple[str, ...] = (
    "engine/government_revenue/*.py",
    "scripts/build_government_revenue*.py",
    "scripts/check_government_revenue_projection.py",
    "scripts/curate_government_revenue_recipient_graph.py",
    "scripts/propose_government_revenue_recipient_graph.py",
    "app/government_revenue.py",
)
# The rendered surfaces.  ``site/`` copies are byte-paired with ``templates/`` by
# scripts/check_template_site_sync.py; both are scanned so a hand-edited site copy
# cannot carry a conflation the template does not.
SURFACE_GLOBS: tuple[str, ...] = (
    "templates/government_revenue.html.j2",
    "templates/government-revenue-*.js",
    "site/government_revenue.html",
    "site/government-revenue-*.js",
)

# Calls whose single collection argument becomes ONE number.
_TOTALLING_CALLS = {"sum", "fsum", "nansum"}
# Keys that make a dict literal an amountFact (v2 contract ``$defs/amountFact``).
_AMOUNT_FACT_KEYS = {"value", "currency"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  [{self.rule}] {self.detail}"


# --------------------------------------------------------------------------- Python


_LADDER_NAME_HINT = re.compile(r"(^_?first_|_first_|fallback|coalesce)", re.IGNORECASE)


def _first_wins_readers(tree: ast.Module) -> frozenset[str]:
    """Functions in THIS module that read a names sequence first-present-wins.

    DERIVED, not hand-listed.  A reader is a function whose body loops over one of its
    own parameters and returns from inside that loop — the shape of ``_first_number`` /
    ``_first_text`` / ``_first_date``, each of which every module here defines privately.
    Deriving it means a newly added coalescing helper is covered on the day it lands,
    which is the failure this lobe keeps repeating in the other direction (a column
    joins a canonical list and a downstream reader never follows).

    Union'd with a NAME hint (``_first_*`` / ``*fallback*`` / ``*coalesce*``) so a
    reader written with a while-loop or a helper call still counts.  Both halves are
    supersets of the obvious case and are cheap; a missed reader is a blind guard.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _LADDER_NAME_HINT.search(node.name):
            found.add(node.name)
            continue
        params = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
        for inner in ast.walk(node):
            if isinstance(inner, ast.For) and isinstance(inner.iter, ast.Name) and inner.iter.id in params:
                if any(isinstance(child, ast.Return) for child in ast.walk(inner)):
                    found.add(node.name)
                    break
    return frozenset(found)


class _PythonScanner(ast.NodeVisitor):
    """Flag expressions that fold more than one amount class into ONE figure.

    Every rule is scoped to its own claim.  The first draft of this file flagged any
    all-string collection containing two classes, which made six of its seven findings
    inventory lists (``SNAPSHOT_STATE_FIELDS``, ``RECOMPETE_KEYS``, the projector
    allow-lists in build_government_revenue.py) — lists whose members are carried
    SEPARATELY and never totalled.  A guard that reports those buries the one real
    finding under noise and teaches the next reader to ignore it, so each rule below
    now requires the syntactic shape that actually merges values:

      * ``+`` where BOTH sides carry a class, and the two sides disagree;
      * a totalling call over a collection literal spanning classes;
      * a ladder handed to a first-present-wins READER, or a ``for … break`` loop;
      * ``get(k, default)`` / ``a or b`` where both rungs carry a class and disagree.

    Local names are tracked when an assignment's right-hand side mentions exactly ONE
    declared amount field (``obligated = pd.to_numeric(active.get("total_obligated"))``);
    all-string collections are tracked by their member list so a ladder hoisted to a
    constant is still resolved at its call site.
    """

    def __init__(self, path: str, readers: frozenset[str]) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._readers = readers
        self._name_class: dict[str, AmountClass] = {}
        self._name_ladder: dict[str, list[str]] = {}

    # -- helpers ----------------------------------------------------------------
    def _literal_fields(self, node: ast.AST) -> list[str]:
        """Declared amount field names appearing as string literals in a subtree."""
        return [
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and classify(child.value) is not None
        ]

    def _name_fields(self, node: ast.AST) -> list[str]:
        """Amount fields reached through locals bound to exactly one class."""
        representative = {cls: field for field, cls in reversed(list(AMOUNT_CLASSES.items()))}
        return [
            representative[self._name_class[child.id]]
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and child.id in self._name_class
        ]

    def _fields(self, node: ast.AST) -> list[str]:
        return self._literal_fields(node) + self._name_fields(node)

    def _classes(self, node: ast.AST) -> frozenset[AmountClass]:
        return frozenset(c for c in (classify(f) for f in self._fields(node)) if c is not None)

    def _report(self, node: ast.AST, rule: str, fields: Sequence[str], extra: str = "") -> None:
        reason = conflict_reason(fields)
        if reason is None:
            return
        detail = reason if not extra else f"{extra} {reason}"
        self.findings.append(Finding(self.path, getattr(node, "lineno", 0), rule, detail))

    @staticmethod
    def _string_members(node: ast.AST) -> list[str] | None:
        """Members of an all-string collection literal, else None."""
        if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return None
        elements = list(node.elts)
        if len(elements) < 2:
            return None
        if not all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elements):
            return None
        return [e.value for e in elements]

    def _ladder_members(self, node: ast.AST) -> list[str] | None:
        members = self._string_members(node)
        if members is not None:
            return members
        if isinstance(node, ast.Name):
            return self._name_ladder.get(node.id)
        return None

    # -- name tracking ----------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        classes = self._classes(node.value)
        members = self._string_members(node.value)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if len(classes) == 1:
                self._name_class[target.id] = next(iter(classes))
            else:
                self._name_class.pop(target.id, None)
            if members is not None:
                self._name_ladder[target.id] = members
            else:
                self._name_ladder.pop(target.id, None)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            members = self._string_members(node.value)
            if members is not None:
                self._name_ladder[node.target.id] = members
        self.generic_visit(node)

    # -- rules ------------------------------------------------------------------
    def visit_BinOp(self, node: ast.BinOp) -> None:
        # SUBTRACTION is deliberately untouched: ceiling - obligated is the lobe's
        # published headroom and obligation - outlay the unliquidated balance.
        if isinstance(node.op, ast.Add):
            left, right = self._classes(node.left), self._classes(node.right)
            if left and right and len(left | right) > 1:
                self._report(node, "mixed_class_sum", self._fields(node))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.op, ast.Add):
            target, value = self._classes(node.target), self._classes(node.value)
            if target and value and len(target | value) > 1:
                self._report(
                    node,
                    "mixed_class_sum",
                    self._fields(node.target) + self._fields(node.value),
                )
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            # Only a VALUE fallback conflates.  ``a.get("field") != "total_obligation" or
            # b.get("field") != "federal_action_obligation"`` is build_government_revenue's
            # rail VALIDATION — it exists to keep the two classes apart — and
            # ``_present_fields(...) or None`` is a nullability idiom.  A single
            # predicate-shaped operand makes the whole expression a boolean, so the
            # rule steps aside rather than reporting the guard that guards the rule.
            predicate = any(
                isinstance(value, (ast.Compare, ast.BoolOp))
                or (isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not))
                or (isinstance(value, ast.Constant) and isinstance(value.value, bool))
                for value in node.values
            )
            if not predicate:
                rungs = [self._classes(value) for value in node.values]
                single = [next(iter(rung)) for rung in rungs if len(rung) == 1]
                if len(set(single)) > 1:
                    self._report(node, "mixed_class_default", self._fields(node))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name in _TOTALLING_CALLS and node.args:
            argument = node.args[0]
            if isinstance(argument, (ast.List, ast.Tuple, ast.Set, ast.GeneratorExp)):
                self._report(node, "mixed_class_sum", self._fields(argument))
        if name == "get" and len(node.args) == 2:
            key, default = self._classes(node.args[0]), self._classes(node.args[1])
            if len(key) == 1 and len(default) == 1 and key != default:
                self._report(node, "mixed_class_default", self._fields(node))
        # A reader may be defined here (derived) or imported from a sibling module, so
        # the name hint is applied at the CALL site too — otherwise a module that
        # imports ``_first_number`` instead of defining it is silently unscanned.
        if name in self._readers or _LADDER_NAME_HINT.search(name):
            for argument in (*node.args, *(kw.value for kw in node.keywords)):
                members = self._ladder_members(argument)
                if members:
                    self._report(node, "mixed_class_fallback", members)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        # ``for col in (a, b, c): … break`` is a ladder wearing loop syntax — the very
        # shape that made metrics._concentration weight a CEILING and publish it as
        # ``covered_obligations``.  ``break``/``return`` is what makes it a SELECTION;
        # a loop that just visits every member (per-column coercion) is an inventory
        # iteration and is left alone.  A last-wins selection loop with neither is a
        # known blind spot, documented rather than papered over.
        members = self._ladder_members(node.iter)
        if members and any(isinstance(child, (ast.Break, ast.Return)) for child in ast.walk(node)):
            self._report(node, "mixed_class_fallback", members)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self._check_amount_fact(node)
        self.generic_visit(node)

    def _check_amount_fact(self, node: ast.Dict) -> None:
        keys = {
            k.value: v
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if not _AMOUNT_FACT_KEYS <= set(keys):
            return
        identifier = keys.get("id")
        field = identifier.value if isinstance(identifier, ast.Constant) and isinstance(identifier.value, str) else None
        field_class = classify(field)
        if field_class is None:
            return
        labels: list[str] = []
        for key in ("semantic", "label_code", "amount_class"):
            value = keys.get(key)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                labels.append(value.value)
        declared = [
            (label, classify_semantic(label) or (AmountClass(label) if label in {c.value for c in AmountClass} else None))
            for label in labels
        ]
        if not any(cls is not None for _, cls in declared):
            self.findings.append(Finding(
                self.path,
                node.lineno,
                "unlabelled_figure",
                f"amount fact id={field!r} publishes a {field_class.value} figure with no "
                f"class label travelling with it (labels seen: {labels or 'none'})",
            ))
            return
        for label, cls in declared:
            if cls is not None and cls is not field_class:
                self.findings.append(Finding(
                    self.path,
                    node.lineno,
                    "unlabelled_figure",
                    f"amount fact id={field!r} is {field_class.value} but is labelled "
                    f"{label!r} ({cls.value})",
                ))


def scan_python(path: str, source: str) -> list[Finding]:
    """Findings for one Python source. Unparseable source FAILS CLOSED."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Finding(path, exc.lineno or 0, "unparseable", f"cannot parse: {exc.msg}")]
    scanner = _PythonScanner(path, _first_wins_readers(tree))
    scanner.visit(tree)
    return scanner.findings


# ---------------------------------------------------------------- rendered surfaces

_ARRAY_RE = re.compile(r"\[((?:\s*(['\"])[A-Za-z0-9_]+\2\s*,)+\s*(['\"])[A-Za-z0-9_]+\3\s*)\]")
_STRING_RE = re.compile(r"(['\"])([A-Za-z0-9_]+)\1")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _balanced_call_args(text: str, name: str) -> Iterator[tuple[int, str]]:
    """Yield ``(start_index, argument_text)`` for every ``name(...)`` call.

    Quote- and depth-aware, so an HTML fragment containing ``)`` inside a string
    literal cannot truncate the argument and hide a conflation behind it.
    """
    pattern = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    for match in pattern.finditer(text):
        i = match.end()
        depth = 1
        quote: str | None = None
        start = i
        while i < len(text):
            ch = text[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    yield match.start(), text[start:i]
                    break
            i += 1


def _preceding_char(text: str, index: int) -> str:
    while index > 0:
        index -= 1
        if not text[index].isspace():
            return text[index]
    return ""


def scan_surface(path: str, text: str) -> list[Finding]:
    """Findings for one rendered surface (template ``.js`` / ``.html.j2`` / ``.html``).

    Two rules, both precise:

      * an array HANDED TO A CALL whose rungs span classes — ``label(a, ['x','y'], null)``
        and ``field(a, ['x','y'])`` are this lobe's first-present-wins readers, so an
        array in argument position is the JS twin of the Python ladder.  An array that
        is ASSIGNED (``var RECOMPETE_KEYS = [...]``) is an inventory whose members are
        carried separately and never totalled; flagging it was the first draft's
        loudest false positive.
      * one ``money(...)`` call whose own argument names more than one class, i.e. a
        single displayed figure built from two different measurements.

    String concatenation between separate ``money()`` calls is NOT examined: two
    figures side by side is the honest presentation, and flagging it would bury the
    real findings in HTML assembly noise.
    """
    findings: list[Finding] = []
    for match in _ARRAY_RE.finditer(text):
        if _preceding_char(text, match.start()) not in {",", "("}:
            continue
        fields = [m.group(2) for m in _STRING_RE.finditer(match.group(1))]
        reason = conflict_reason(fields)
        if reason is not None:
            findings.append(Finding(path, _line_of(text, match.start()), "mixed_class_fallback", reason))
    for start, argument in _balanced_call_args(text, "money"):
        fields = [m.group(2) for m in _STRING_RE.finditer(argument)]
        fields += re.findall(r"\.([A-Za-z0-9_]+)", argument)
        reason = conflict_reason(fields)
        if reason is not None:
            findings.append(Finding(
                path,
                _line_of(text, start),
                "unlabelled_figure",
                f"one displayed figure is built from more than one class — {reason}",
            ))
    return findings


# ------------------------------------------------------------------------ payloads


def scan_payload(path: str, payload: object) -> list[Finding]:
    """Findings for a BUILT payload: every published amount fact must carry its class.

    Static rules read literals; a payload assembled at runtime is where a figure
    actually crosses the publish boundary, so the same rule is applied to the artifact.
    """
    findings: list[Finding] = []

    def walk(node: object, trail: str) -> None:
        if isinstance(node, dict):
            if _AMOUNT_FACT_KEYS <= set(node):
                field_class = classify(node.get("id"))
                if field_class is not None:
                    labels = [node.get("semantic"), node.get("label_code")]
                    declared = node.get("amount_class")
                    resolved = [classify_semantic(label) for label in labels]
                    if declared is not None and declared != field_class.value:
                        findings.append(Finding(path, 0, "unlabelled_figure", (
                            f"{trail}: amount fact id={node.get('id')!r} is {field_class.value} "
                            f"but declares amount_class={declared!r}"
                        )))
                    elif declared is None and not any(cls is not None for cls in resolved):
                        findings.append(Finding(path, 0, "unlabelled_figure", (
                            f"{trail}: amount fact id={node.get('id')!r} publishes a "
                            f"{field_class.value} figure with no class label travelling with it"
                        )))
                    for label, cls in zip(labels, resolved):
                        if cls is not None and cls is not field_class:
                            findings.append(Finding(path, 0, "unlabelled_figure", (
                                f"{trail}: amount fact id={node.get('id')!r} is "
                                f"{field_class.value} but is labelled {label!r} ({cls.value})"
                            )))
            for key, value in node.items():
                walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")

    walk(payload, "$")
    return findings


# ----------------------------------------------------------------------------- run


def subject_paths(root: Path = ROOT) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in (*PYTHON_GLOBS, *SURFACE_GLOBS):
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen.setdefault(path, None)
    return list(seen)


def scan_tree(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in subject_paths(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            findings.extend(scan_python(rel, text))
        else:
            findings.extend(scan_surface(rel, text))
    return findings


_SELFTEST_CASES: tuple[tuple[str, bool, str, str], ...] = (
    (
        "mix 1 — award cumulative + transaction delta",
        True,
        "engine/government_revenue/_selftest.py",
        'total = row["total_obligated"] + row["federal_action_obligation"]\n',
    ),
    (
        "mix 2 — obligation + ceiling",
        True,
        "engine/government_revenue/_selftest.py",
        'exposure = sum([row["total_obligated"], row["potential_award_amount"]])\n',
    ),
    (
        "mix 3 — obligation + outlay",
        True,
        "engine/government_revenue/_selftest.py",
        'spend = row["total_obligation"] + row["total_outlay"]\n',
    ),
    (
        "mix 4 — figure published without its class label",
        True,
        "engine/government_revenue/_selftest.py",
        'fact = {"id": "total_obligated", "value": v, "currency": "USD"}\n',
    ),
    (
        "mixed-class ladder in a for/break selection loop",
        True,
        "engine/government_revenue/_selftest.py",
        'for col in ("total_obligated", "current_award_amount"):\n'
        '    if col in frame:\n        w = frame[col]\n        break\n',
    ),
    (
        "mixed-class ladder handed to a first-present-wins reader",
        True,
        "engine/government_revenue/_selftest.py",
        'v = _first_number(row, ("total_obligated", "potential_award_amount"))\n',
    ),
    (
        "mixed-class ladder hoisted to a constant, resolved at the call site",
        True,
        "engine/government_revenue/_selftest.py",
        'LADDER = ("total_obligated", "current_award_amount")\n'
        'v = _first_number(row, LADDER)\n',
    ),
    (
        "mixed-class .get() default chain",
        True,
        "engine/government_revenue/_selftest.py",
        'v = row.get("total_obligated", row.get("potential_award_amount"))\n',
    ),
    (
        "same-class ladder is fine",
        False,
        "engine/government_revenue/_selftest.py",
        'v = _first_number(row, ("total_obligated", "award_amount"))\n',
    ),
    (
        "an INVENTORY list of amount columns is not a ladder",
        False,
        "engine/government_revenue/_selftest.py",
        'SNAPSHOT_STATE_FIELDS = ("total_obligation", "current_award_amount", "potential_award_amount")\n',
    ),
    (
        "a per-column coercion loop is not a selection",
        False,
        "engine/government_revenue/_selftest.py",
        'for col in ("total_obligated", "current_award_amount"):\n    frame[col] = coerce(frame[col])\n',
    ),
    (
        "validating that two rails carry the RIGHT fields is not a conflation",
        False,
        "engine/government_revenue/_selftest.py",
        'if a.get("field") != "total_obligation" or b.get("field") != "federal_action_obligation":\n'
        '    raise ValueError("wrong rails")\n',
    ),
    (
        "ceiling MINUS obligation is the defined headroom, never a finding",
        False,
        "engine/government_revenue/_selftest.py",
        'headroom = row["potential_award_amount"] - row["total_obligated"]\n',
    ),
    (
        "unparseable source FAILS CLOSED",
        True,
        "engine/government_revenue/_selftest.py",
        "def broken(:\n",
    ),
)

_SELFTEST_SURFACES: tuple[tuple[str, bool, str, str], ...] = (
    (
        "template ladder mixing obligation and ceiling",
        True,
        "templates/government-revenue-_selftest.js",
        "var v=money(label(a,['total_obligated','current_award_amount'],null));",
    ),
    (
        "one money() figure built from two classes",
        True,
        "templates/government-revenue-_selftest.js",
        "html+='<b>'+money(a.total_obligated+a.potential_award_amount)+'</b>';",
    ),
    (
        "two figures side by side is the honest presentation",
        False,
        "templates/government-revenue-_selftest.js",
        "html+='<b>'+money(a.total_obligated)+'</b><b>'+money(a.potential_award_amount)+'</b>';",
    ),
    (
        "an ASSIGNED key inventory is not a ladder",
        False,
        "templates/government-revenue-_selftest.js",
        "var RECOMPETE_KEYS = ['total_obligated','current_award_amount','potential_award_amount'];",
    ),
)


def selftest() -> int:
    ok = True
    for name, should_fire, rel, source in _SELFTEST_CASES:
        fired = bool(scan_python(rel, source))
        status = "PASS" if fired == should_fire else "FAIL"
        ok = ok and fired == should_fire
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")
    for name, should_fire, rel, source in _SELFTEST_SURFACES:
        fired = bool(scan_surface(rel, source))
        status = "PASS" if fired == should_fire else "FAIL"
        ok = ok and fired == should_fire
        print(f"  [{status}] {name}: fired={fired} expected={should_fire}")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true", help="print the census and exit 0")
    parser.add_argument("--selftest", action="store_true", help="prove the guard fires on each mix")
    parser.add_argument("--payload", type=Path, help="also scan a built payload JSON")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    findings = scan_tree()
    if args.payload:
        findings.extend(scan_payload(
            args.payload.as_posix(),
            json.loads(args.payload.read_text(encoding="utf-8")),
        ))

    if args.report:
        print(f"subjects scanned: {len(subject_paths())}")
        for finding in findings:
            print(f"  {finding}")
        print(f"findings: {len(findings)}")
        sys.exit(0)

    if findings:
        print(
            f"::error title=govrev-amount-semantics::{len(findings)} Government Revenue "
            f"figure(s) combine amount classes that are not addable",
            flush=True,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        sys.exit(1)
    print("check_government_revenue_amount_semantics: OK — no figure mixes amount classes.")


if __name__ == "__main__":
    main()
