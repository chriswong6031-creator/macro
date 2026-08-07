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

  A name proved inside ANOTHER function.  ``metrics._backlog``'s ``current_total`` really
  is a ceiling total — and it is a local of ``_backlog``.  An expression a thousand lines
  later that happens to use the same word names nothing, so bindings are SCOPED
  (``_Scope`` / ``_PythonScanner._binding_scope``): an inner scope may read an enclosing
  binding, it may only write its own, and a class does not leave the function that proved
  it.  The flat tracker this replaced reported ``float(current_total) + float(denom)``
  inside ``_catalysts``, where neither name exists.

  A count, a label, or a container.  ``len(value_items) + len(changes)`` adds two
  cardinalities, and ``verb = "deobligation" if amount < 0 else "positive contract
  action"`` is a WORD that a delta merely chose.  A class is read only from an
  expression's VALUE positions (``_PythonScanner._value_fields``) — never from the
  condition that picks the value, and never past a call whose result is a different KIND
  of thing.  A container's own NAME is likewise not a figure — but its members' classes
  are kept against that name (``_member_fields``) and recovered the moment the collection
  is folded back into one number, by a total or by an element read, so hoisting a list out
  of ``sum(...)`` no longer hides the mix.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.government_revenue.amount_semantics import (  # noqa: E402
    AMOUNT_CLASSES,
    AmountClass,
    classes_of,
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

# Calls whose RESULT is a different KIND of thing from whatever it was derived from: a
# count, a string, a boolean, a container.  A class describes a dollar figure, so it
# stops at these — ``len(obligations) + len(ceilings)`` adds two counts, and a count is
# dimensionless.  Deliberately a list of KIND-CHANGERS, never a list of amount-preserving
# calls: the whitelist reading would drop the class at every helper this lobe has not
# heard of, and the binding the whole fix rests on is a call
# (``pd.to_numeric(active.get("total_obligated"), errors="coerce")``).
_KIND_CHANGING_CALLS = frozenset({
    "len", "str", "repr", "bool", "format", "join", "split", "splitlines",
    "sorted", "list", "set", "dict", "tuple", "frozenset",
    "any", "all", "keys", "values", "items",
    "isoformat", "strftime", "strip", "lower", "upper",
})


# One field name per class, used to say "this local is an X" in a finding's wording.
# First declaration wins, matching the order of ``AMOUNT_CLASSES``.
_REPRESENTATIVE_FIELD: dict[AmountClass, str] = {
    cls: name for name, cls in reversed(list(AMOUNT_CLASSES.items()))
}


def _callee_name(node: ast.Call) -> str:
    """``f(...)`` -> ``f``; ``a.b.f(...)`` -> ``f``; anything else -> ``""``."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


@dataclass
class _Scope:
    """One Python name-binding scope: a module, function, class body, or comprehension.

    ``classes`` maps a name to its class, or to ``None`` meaning "bound HERE and carrying
    no class" — an explicit shadow, so a local that re-measures or loses the class does
    not fall through to an enclosing binding of the same name.

    ``ladders`` holds a name bound to an all-string collection (a FIELD-NAME ladder);
    ``containers`` holds a name bound to a collection of amount VALUES, as the declared
    fields its members came from.  Both are properties of the collection, not of one
    figure, which is why neither is a class: they are read where the collection is folded
    into a number (a total, an element read, a first-present-wins rung), never where the
    collection's own name is used.
    """

    kind: str
    classes: dict[str, AmountClass | None] = field(default_factory=dict)
    ladders: dict[str, list[str] | None] = field(default_factory=dict)
    containers: dict[str, list[str] | None] = field(default_factory=dict)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)


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
    constant is still resolved at its call site, and a collection of amount VALUES is
    tracked by the fields its members measure (``_member_fields``) so a list hoisted out
    of ``sum(...)`` is resolved at ITS call site too.  Four shapes that hid real mixes are
    tracked as well, each stated as a rule where it is implemented: a class-neutral
    RE-BIND does not clobber a class the name already proved (``_bind_class``), a LOOP
    VARIABLE walking a known field ladder carries that ladder's class (``visit_For``), an
    ELEMENT taken out of a single-class container carries its members' class
    (``_value_fields``), and every binding is SCOPED to the function that made it
    (``_Scope``/``_binding_scope``) so a name proved inside one function does not stay
    classed for the rest of the module.

    What a tracked class means is PROVENANCE — which declared field this value came from —
    read only through the expression's own VALUE positions (``_value_fields``), never
    through a position that merely decides the value.  Both halves are load-bearing and
    both are stated where they are implemented.
    """

    def __init__(self, path: str, readers: frozenset[str]) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._readers = readers
        self._scopes: list[_Scope] = [_Scope("module")]

    # -- scopes -----------------------------------------------------------------
    #
    # THE SCOPING RULE, stated once:
    #
    #   A name proved inside a function does not carry its class out of that function.
    #   An inner scope may READ an enclosing binding; it may only WRITE into its own,
    #   unless it declares ``global``/``nonlocal``, which this lobe really does use
    #   (metrics.py:535).
    #
    # Before this, ``_name_class`` was ONE FLAT DICT for the whole module, and the
    # never-clobber-on-class-neutral-rebind rule above made that permanent: ``_backlog``'s
    # ``current_total``/``funded_total`` floats (metrics.py:1264-1265) stayed classed for
    # ~1,000 further lines, so injecting ``float(current_total) + float(denom)`` a thousand
    # lines away — in a different function, where neither name exists — was REPORTED as a
    # ceiling added to a transaction delta.  Neither expression touches a ceiling or a
    # delta; the guard was inventing the mix out of two names it could not see.
    #
    # THE PRICE, measured rather than assumed.  Injecting ``<name> + row["total_outlay"]``
    # after every assignment in all 33 subjects: 24 sites are reported by the flat tracker
    # and by this one, 0 by this one alone, and 35 by the flat tracker alone.  Thirty-two
    # of those 35 are names that hold no dollar figure at all — string labels, booleans,
    # dicts, lists, and the 0.8/0.6/0.35 weight in workspace.py — i.e. the same noise the
    # value-position rule below removes.  The other three are ``_impact``'s
    # ``source_amount``/``attributable_amount``/``ratio``, whose class the flat tracker
    # borrowed from a DIFFERENT function's local through the parameter ``amount``.  That
    # is the known limit and it is stated rather than papered over: this file does no
    # interprocedural analysis, so a PARAMETER carries no class, and recovering those
    # three would mean restoring exactly the leak that produced the false positives.
    #
    # WHERE THE RULE BITES, counted rather than remembered: SIX functions across THREE
    # modules hold per-function amount state — ``metrics._backlog``, ``_catalysts``,
    # ``_concentration`` and ``_modification_metrics``; ``award_events._action_classification``;
    # and ``workspace._recompete_workspace_event`` (``obligated``/``ratio``), which a build
    # report for this round left out of the count.  Pinned by
    # ``test_the_scoping_rule_bites_in_three_modules_not_one`` so it cannot drift back into
    # prose.
    def _visible_scopes(self) -> Iterator[_Scope]:
        """Scopes a name READ may reach, innermost first.

        Python's own chain: the innermost scope, then every enclosing FUNCTION (and the
        module), skipping enclosing CLASS bodies — a class body's names are not visible to
        code nested inside it, which is why only the innermost scope may be a class one.
        """
        scopes = list(reversed(self._scopes))
        yield scopes[0]
        for scope in scopes[1:]:
            if scope.kind != "class":
                yield scope

    def _binding_scope(self, name: str) -> _Scope:
        """The scope a WRITE to ``name`` lands in — its own, unless declared otherwise."""
        current = self._scopes[-1]
        if name in current.global_names:
            return self._scopes[0]
        if name in current.nonlocal_names:
            for scope in reversed(self._scopes[:-1]):
                if scope.kind == "function":
                    return scope
        return current

    def _lookup_class(self, name: str) -> AmountClass | None:
        for scope in self._visible_scopes():
            if name in scope.classes:
                return scope.classes[name]
        return None

    def _lookup_ladder(self, name: str) -> list[str] | None:
        for scope in self._visible_scopes():
            if name in scope.ladders:
                return scope.ladders[name]
        return None

    def _lookup_container(self, name: str) -> list[str] | None:
        for scope in self._visible_scopes():
            if name in scope.containers:
                return scope.containers[name]
        return None

    def _scoped(self, kind: str, node: ast.AST) -> None:
        self._scopes.append(_Scope(kind))
        try:
            self.generic_visit(node)
        finally:
            self._scopes.pop()

    # A function/lambda body, a class body, and a comprehension each own their bindings.
    # (Decorators and parameter defaults are evaluated in the ENCLOSING scope; they are
    # visited inside the new one here because neither can contain a binding, so the only
    # thing it could affect is a read, and a mis-scoped read of a decorator argument
    # cannot produce a figure.)
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scoped("function", node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scoped("function", node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._scoped("function", node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scoped("class", node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._scoped("comprehension", node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._scoped("comprehension", node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._scoped("comprehension", node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._scoped("comprehension", node)

    def visit_Global(self, node: ast.Global) -> None:
        self._scopes[-1].global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._scopes[-1].nonlocal_names.update(node.names)

    # -- helpers ----------------------------------------------------------------
    def _value_fields(self, node: ast.AST) -> list[str]:
        """Declared amount fields reachable through this expression's VALUE positions.

        THE VALUE-POSITION RULE, stated once:

          A class describes what a figure IS a measurement of, so it is read only from
          the parts of an expression that can BE the value — never from a part that
          merely decides which value is taken, and never past a call whose result is a
          different KIND of thing.

        Two pruned positions, each measured on real source:

          * the TEST of a conditional, a comparison, and ``not``.  ``verb =
            "deobligation" if amount < 0 else "positive contract action"`` is a WORD;
            ``amount`` chooses between two words, it is not the word.  Reading the test
            is how ``event_type``, ``kind``, ``verb`` and ``amount_type`` — string
            labels, every one — came to be classed ``transaction_delta``.
          * a call in ``_KIND_CHANGING_CALLS``.  ``len(value_items) + len(changes)``
            adds two counts; a count carries no class no matter what was counted.

        Everything else propagates, INCLUDING an opaque helper call
        (``_changed_fields(prior, current, ...)``).  That is deliberate and is the
        residual this rule accepts: the result KIND of a call this file has never heard
        of is unknown, and the module's own law is that an unknown is not reclassified —
        so refusing there would also refuse ``pd.to_numeric(active.get("total_obligated"))``,
        the binding both mutation tests rest on.  What survives is a name whose
        PROVENANCE is right and whose runtime type is unknown; it can only produce a
        finding by being ADDED to a differently-classed name, and for a non-number that
        means string or list concatenation between two such names — which fails toward a
        report a reader can dismiss, not toward the blindness that shipped.
        """
        found: list[str] = []
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and classify(node.value) is not None:
                found.append(node.value)
            return found
        if isinstance(node, ast.Name):
            cls = self._lookup_class(node.id)
            if cls is not None:
                found.append(_REPRESENTATIVE_FIELD[cls])
            return found
        if isinstance(node, (ast.Compare, ast.JoinedStr)):
            return found
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return found
        if isinstance(node, ast.IfExp):
            return self._value_fields(node.body) + self._value_fields(node.orelse)
        if isinstance(node, ast.Attribute):
            if classify(node.attr) is not None:
                found.append(node.attr)
            return found + self._value_fields(node.value)
        if isinstance(node, ast.Call):
            name = _callee_name(node)
            if name in _KIND_CHANGING_CALLS:
                return found
            if name in _TOTALLING_CALLS:
                # A total over a collection IS one figure built from every member, so this
                # one call reads INSIDE the container it is handed — whether that container
                # is a LITERAL (``sum([a, b])``) or a NAME bound to one (``vals = [a, b]``
                # … ``sum(vals)``), which ``_collection_fields`` resolves through
                # ``_lookup_container``/``_lookup_ladder``.  Reading only the literal is
                # what made hoisting the list out of the call site a blind spot.
                # ``series.sum()`` takes no argument at all — its collection is the
                # RECEIVER, which is how ``float(weights.sum())`` reaches the class
                # ``weights`` carries.
                found = [f for child in node.args for f in self._collection_fields(child)]
                if isinstance(node.func, ast.Attribute):
                    found.extend(self._value_fields(node.func.value))
                return found
            if name in self._readers or _LADDER_NAME_HINT.search(name):
                # A first-present-wins reader RETURNS one rung of the ladder it is handed,
                # so its value carries that ladder's class — the exact twin of the loop
                # variable rule in ``visit_For``, and stated the same way: a single-class
                # ladder yields that class, a ladder spanning classes yields none, because
                # the call is ALREADY a mixed_class_fallback finding and giving its result
                # one of the two classes would be a coin-flip dressed as knowledge.
                for argument in (*node.args, *(kw.value for kw in node.keywords)):
                    members = self._ladder_members(argument)
                    if not members:
                        continue
                    rung_classes = classes_of(members)
                    if len(rung_classes) == 1:
                        return [_REPRESENTATIVE_FIELD[next(iter(rung_classes))]]
                    return found
            if isinstance(node.func, ast.Attribute):
                found.extend(self._value_fields(node.func.value))
            for argument in (*node.args, *(kw.value for kw in node.keywords)):
                found.extend(self._value_fields(argument))
            return found
        if isinstance(node, ast.Subscript):
            # AN ELEMENT TAKEN OUT of a tracked container IS one of its members, so it
            # carries the members' class — ``pair = (a, b)`` … ``pair[0]``.  Stated on
            # exactly the terms of the loop-variable and reader-result rules: a
            # single-class container yields that class; a container spanning classes
            # yields NONE, because which member an index picks is not knowable here and
            # attributing one of the two would be a coin-flip dressed as knowledge (the
            # mix such a container makes is reported where it is TOTALLED, not here).
            found.extend(self._value_fields(node.slice))
            if isinstance(node.value, ast.Name):
                members = classes_of(self._lookup_container(node.value.id) or ())
                if len(members) == 1:
                    found.append(_REPRESENTATIVE_FIELD[next(iter(members))])
            found.extend(self._value_fields(node.value))
            return found
        for child in ast.iter_child_nodes(node):
            found.extend(self._value_fields(child))
        return found

    def _collection_fields(self, node: ast.AST) -> list[str]:
        """Every declared field in a subtree — the reading for a container being TOTALLED.

        A NAME is resolved three ways, in order: its own class, the field-name ladder it
        is bound to (``sum(frame[c] for c in COLS)``), and the amount container it is
        bound to (``vals = [...]`` … ``sum(vals)``).  Only a totalling call reads this,
        which is what keeps a container's own name from behaving like a dollar figure.
        """
        found: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Constant):
                if isinstance(child.value, str) and classify(child.value) is not None:
                    found.append(child.value)
            elif isinstance(child, ast.Name):
                cls = self._lookup_class(child.id)
                if cls is not None:
                    found.append(_REPRESENTATIVE_FIELD[cls])
                    continue
                members = self._lookup_ladder(child.id) or self._lookup_container(child.id)
                if members:
                    found.extend(members)
        return found

    def _fields(self, node: ast.AST) -> list[str]:
        return self._value_fields(node)

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
            return self._lookup_ladder(node.id)
        return None

    def _member_fields(self, node: ast.AST) -> list[str]:
        """Declared fields the MEMBERS of a sequence literal are measurements of.

        THE CONTAINER-MEMBER RULE, stated once:

          A name bound to a collection of amounts is not itself a figure, but it is a
          collection OF figures — so the members' classes are kept against the name and
          recovered wherever the collection is folded back into one number.

        Read from the MEMBER positions only — a list's elements, a comprehension's
        element expression — never from the iteration domain, so
        ``[by_name[n] for n in ("current_award_amount", "potential_award_amount")]``
        stays a list of unknown things rather than borrowing a class from the names it
        looks up by.  Each member is read through ``_value_fields``, so the
        value-position rule applies inside a container exactly as it does outside one:
        a list of string labels or of counts carries nothing.

        A DICT is deliberately not tracked.  It is a RECORD keyed by name and
        heterogeneous by design — an amount fact is itself ``{"id": …, "value": …,
        "currency": …}`` — so a union over its values would put a class on
        ``fact["currency"]``.  Per-key modelling is analysis this file does not do, and
        the rule that cannot invent a mix wins.
        """
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [f for element in node.elts for f in self._value_fields(element)]
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            # The element expression is evaluated in the comprehension's OWN scope, so its
            # targets are pushed as explicit shadows before it is read: in
            # ``[obligated for obligated in raw]`` the element is the comprehension's
            # ``obligated``, not an enclosing local that happens to share the word.
            shadow = _Scope("comprehension")
            for generator in node.generators:
                for name in ast.walk(generator.target):
                    if isinstance(name, ast.Name):
                        shadow.classes[name.id] = None
                        shadow.ladders[name.id] = None
                        shadow.containers[name.id] = None
            self._scopes.append(shadow)
            try:
                element = node.value if isinstance(node, ast.DictComp) else node.elt
                return self._value_fields(element)
            finally:
                self._scopes.pop()
        return []

    # -- name tracking ----------------------------------------------------------
    def _bind_class(self, name: str, classes: frozenset[AmountClass]) -> None:
        """Re-bind ``name``'s tracked class.  A CLASS-NEUTRAL re-bind does not clobber.

        THE RULE, stated once:

          * one class on the right-hand side  -> that class, overwriting any earlier one;
          * two or more                       -> no class (the value's own measurement is
                                                 ambiguous, and whatever mixed them is
                                                 reported by its own rule);
          * none                              -> LEAVE the existing class in place.

        The third line is the fix.  This lobe writes every amount local with a defensive
        rebind, so ``pop on silence`` made the guard blind to the function that most needed
        it — ``metrics._backlog`` uses the idiom on all three of its amount locals::

            obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")
            if obligated is None:
                obligated = pd.Series(float("nan"), index=active.index)   # popped the class

        and with the class popped, flipping the genuine ``current - obligated`` headroom to
        ``current + obligated`` — a CEILING added to an OBLIGATION, the exact mix this file
        exists to refuse — scanned clean.  A placeholder is the ABSENCE of the quantity, not
        a different quantity: the branch runs only because the real value was missing, so it
        cannot be a second measurement.  The module's own law for combining says silence is
        "unknown", not "compatible"; the same law read for TRACKING says silence is
        "unknown", not "reclassified".  A re-bind that carries a DIFFERENT class is real
        counter-evidence and still overwrites, so Python's last-wins semantics survive.

        The other honest option — union the classes and report an ambiguous union — is
        deliberately NOT taken.  A local genuinely reused for two measurements would then be
        reported at every downstream USE, blaming expressions that mixed nothing, and the
        union would be manufactured by the tracker rather than found in the code.  This
        file's precision is the reason it is allowed to exist (its first draft's six
        findings were inventory lists), so the rule that cannot invent a mix wins.  The
        residual cost of preserving is a stale class on a local silently repurposed for
        something else — which fails toward a REPORT a reader can dismiss, not toward the
        blindness that shipped.

        The ladder map below keeps last-wins on purpose: a ladder's members are a property
        of the VALUE, and a re-bind to a non-literal leaves genuinely unknown members, so
        there is nothing to preserve.

        SCOPING closes the third gap.  "Existing" is now read from the scope the write
        lands in, and every outcome WRITES there — ``None`` meaning "bound here, carrying
        no class".  That explicit shadow is what stops a local from silently inheriting an
        enclosing binding of the same name: in Python a name a function assigns is that
        function's own from its first line, so a re-measured or class-less local must not
        fall through to the module.  Preservation therefore stays what it always was — a
        property of ONE name in ONE scope — instead of a property of the whole file.
        """
        scope = self._binding_scope(name)
        if len(classes) == 1:
            scope.classes[name] = next(iter(classes))
        elif classes:
            scope.classes[name] = None
        else:
            scope.classes.setdefault(name, None)

    def visit_Assign(self, node: ast.Assign) -> None:
        # A CONTAINER is not one figure.  ``value_items = [by_name[n] for n in
        # ("current_award_amount", "potential_award_amount") if n in by_name]`` is a LIST
        # of facts, and ``impacts = {i["ticker"]: i for i in ...}`` is a dict; classing
        # either says a collection is a dollar amount.  The members' classes are still
        # read wherever the collection is TOTALLED, INDEXED, or used as a ladder — those
        # rules look inside a collection on purpose — so nothing is lost by refusing to
        # put a class on the container's own name.
        #
        # What WAS lost, until the members were kept against the name, is every one of
        # those rules the moment the container stopped being a literal at the call site::
        #
        #     vals = [row["total_obligated"], row["total_obligation"]]
        #     return sum(vals) + row["total_outlays"]        # obligations + an OUTLAY
        #
        # scanned clean while the identical list written INSIDE ``sum()`` went red.  A
        # blind spot a reader closes by hoisting one line is not a rule.  ``containers``
        # holds the members' fields (``_member_fields``); nothing is reported HERE, not
        # even for a container spanning classes — building a list of an obligation and a
        # ceiling is how the dossier renders them side by side, which is the honest
        # presentation.  It is TOTALLING one that mixes, and that is reported where it
        # happens.
        container = isinstance(node.value, (
            ast.Dict, ast.List, ast.Tuple, ast.Set,
            ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
        ))
        classes = frozenset() if container else self._classes(node.value)
        members = self._string_members(node.value)
        contents = self._member_fields(node.value) or None
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            self._bind_class(target.id, classes)
            scope = self._binding_scope(target.id)
            scope.ladders[target.id] = members
            scope.containers[target.id] = contents
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            members = self._string_members(node.value)
            if members is not None:
                self._binding_scope(node.target.id).ladders[node.target.id] = members
            contents = self._member_fields(node.value)
            if contents:
                self._binding_scope(node.target.id).containers[node.target.id] = contents
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
            elif isinstance(argument, ast.Name):
                # The same rule where the collection was hoisted to a name — the members
                # are read from the binding rather than from the call site.  A name with
                # no tracked members resolves to nothing and reports nothing.
                self._report(node, "mixed_class_sum", self._collection_fields(argument))
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
        # The loop VARIABLE carries the class of the domain it walks, when that domain is
        # statically knowable — a field-ladder literal, or a name bound to one.  Without
        # this, ``for col in _CONCENTRATION_WEIGHT_FIELDS: weights = frame[col]`` left
        # ``weights`` unclassed, and the ``+`` rule needs BOTH operands classed, so an
        # obligation-weighted total added to an outlay total inside _concentration —
        # published under the word ``covered_obligations`` — scanned clean.  A single-class
        # ladder (which is what _CONCENTRATION_WEIGHT_FIELDS became when this PR removed
        # its ceiling rung) yields exactly that class; a ladder spanning classes yields
        # none, because the loop is ALREADY a mixed_class_fallback finding and giving the
        # variable one of the two classes would be a coin-flip dressed as knowledge.
        # A domain that is not statically knowable (``for col in frame.columns``, a
        # parameter, a call result) binds nothing: an unread domain is unknown, and this
        # file does not guess — an invented class would manufacture findings, which is the
        # one failure it cannot afford.
        if members is not None and isinstance(node.target, ast.Name):
            self._bind_class(node.target.id, classes_of(members))
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
        "a class-neutral defensive rebind does not erase the class",
        True,
        "engine/government_revenue/_selftest.py",
        'obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")\n'
        "if obligated is None:\n"
        '    obligated = pd.Series(float("nan"), index=active.index)\n'
        'exposure = obligated + row["potential_award_amount"]\n',
    ),
    (
        "a rebind carrying a DIFFERENT class still overwrites, so this is same-class",
        False,
        "engine/government_revenue/_selftest.py",
        'x = row["total_obligated"]\n'
        'x = row["current_award_amount"]\n'
        'total = x + row["potential_award_amount"]\n',
    ),
    (
        "a loop variable over a single-class ladder carries that class",
        True,
        "engine/government_revenue/_selftest.py",
        'WEIGHTS = ("total_obligated", "award_amount")\n'
        "for col in WEIGHTS:\n"
        "    if col in frame.columns:\n"
        "        weights = frame[col]\n"
        "        break\n"
        'total = float(weights.sum()) + float(frame["total_outlays"].sum())\n',
    ),
    (
        "a list hoisted out of sum() is still totalled",
        True,
        "engine/government_revenue/_selftest.py",
        'vals = [row["total_obligated"], row["total_obligation"]]\n'
        'total = sum(vals) + row["total_outlays"]\n',
    ),
    (
        "a comprehension bound to a name is a collection of amounts",
        True,
        "engine/government_revenue/_selftest.py",
        'vals = [r["total_obligated"] for r in rows]\n'
        'total = sum(vals) + rows[0]["total_outlays"]\n',
    ),
    (
        "an element taken out of a single-class container carries its class",
        True,
        "engine/government_revenue/_selftest.py",
        'pair = (row["total_obligated"], row["total_obligation"])\n'
        'total = pair[0] + row["total_outlays"]\n',
    ),
    (
        "BUILDING a container of two classes is the side-by-side presentation",
        False,
        "engine/government_revenue/_selftest.py",
        'both = [row["total_obligated"], row["potential_award_amount"]]\n',
    ),
    (
        "an element read from a MIXED container is a coin flip, so it carries no class",
        False,
        "engine/government_revenue/_selftest.py",
        'both = [row["total_obligated"], row["potential_award_amount"]]\n'
        'total = both[0] + row["total_outlays"]\n',
    ),
    (
        "a container of non-amounts stays unclassed",
        False,
        "engine/government_revenue/_selftest.py",
        'labels = ["deobligation", "positive contract action"]\n'
        'total = labels[0] + row["total_obligated"]\n',
    ),
    (
        "a loop over an unknowable domain binds nothing",
        False,
        "engine/government_revenue/_selftest.py",
        "for col in frame.columns:\n"
        "    weights = frame[col]\n"
        'total = float(weights.sum()) + float(frame["total_outlays"].sum())\n',
    ),
    (
        "a class proved in one function does not leak into the next",
        False,
        "engine/government_revenue/_selftest.py",
        "def backlog():\n"
        '    current_total = float(active["current_award_amount"].sum())\n'
        "def catalysts():\n"
        '    return float(current_total) + float(row["federal_action_obligation"])\n',
    ),
    (
        "the same two names ADDED where they were both proved is still a finding",
        True,
        "engine/government_revenue/_selftest.py",
        "def backlog():\n"
        '    current_total = float(active["current_award_amount"].sum())\n'
        '    funded_total = float(active["total_obligated"].sum())\n'
        "    return float(current_total) + float(funded_total)\n",
    ),
    (
        "an inner scope still READS an enclosing binding",
        True,
        "engine/government_revenue/_selftest.py",
        "def outer():\n"
        '    obligated = row["total_obligated"]\n'
        "    def inner():\n"
        '        return obligated + row["potential_award_amount"]\n',
    ),
    (
        "two counts are not two amounts",
        False,
        "engine/government_revenue/_selftest.py",
        'ceilings = row["current_award_amount"]\n'
        'deltas = row["federal_action_obligation"]\n'
        "n = len(ceilings) + len(deltas)\n",
    ),
    (
        "the same two names added WITHOUT len() still fires",
        True,
        "engine/government_revenue/_selftest.py",
        'ceilings = row["current_award_amount"]\n'
        'deltas = row["federal_action_obligation"]\n'
        "n = ceilings + deltas\n",
    ),
    (
        "a condition's class does not become the chosen WORD's class",
        False,
        "engine/government_revenue/_selftest.py",
        'amount = row["federal_action_obligation"]\n'
        'verb = "deobligation" if amount < 0 else "positive contract action"\n'
        'label = verb + str(row["potential_award_amount"])\n',
    ),
    (
        "a conditional still carries the class of the VALUE it chooses",
        True,
        "engine/government_revenue/_selftest.py",
        'amount = row["current_award_amount"] if flag else row["potential_award_amount"]\n'
        'total = amount + row["total_obligated"]\n',
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
