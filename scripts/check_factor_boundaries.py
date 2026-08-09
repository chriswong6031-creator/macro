"""scripts/check_factor_boundaries.py — Factor boundary static guard.

LANE: §D PR-5, RUL-NW9 / RUL-NW11 (NW_INTEGRATION_ADJUDICATION_BY_FABLE.md)

PURPOSE
-------
Static guard that enforces three boundary rules for factor-module files.
Modelled on check_synapse_reads.py and check_research_factory_authority.py
conventions; checks (a)/(c) and the default check-(b) path are literal scans.

THREE CHECKS
------------
(a) Article-2 write guard (RUL-NW9/NW11):
    FAIL if any factor-module file contains a code-level write reference to
    Article-2 surfaces/artifacts:
      - alert_triage
      - board_ordering/us_standouts writes (board_ordering path fragment)
      - top_setups
      - push_floor
      - attention_queue
    Factor modules scanned:
      scripts/build_factor_panel.py
      scripts/build_factor_intelligence_state.py
      scripts/build_factor_deescalation_shadow.py
      engine/neuralweb/factor_contradictions.py
      engine/neuralweb/kernel_style.py  (if present)
    Note: comment lines and docstring lines are skipped (the guard forbids code
    references, not documentation notes that enumerate forbidden surfaces).

(b) allowed_actions read guard (RUL-NW9):
    FAIL if 'allowed_actions' is READ anywhere outside an explicit allowlist.
    The state builder may emit the field (it's the producer); display surfaces
    and admin may read it; everything else must not touch it.
    Allowlisted paths (may read 'allowed_actions'):
      scripts/build_factor_intelligence_state.py    (producer — emits the block)
      scripts/build_factor_deescalation_shadow.py   (internal guard check)
      tests/                                         (test files; prefix match)
      admin/neural_web.py
      admin/static/app.js
      templates/factors.html.j2
      scripts/build_site.py
      engine/neuralweb/cortex.py
      engine/neuralweb/ask_brain.py
      engine/sector_intelligence/contracts.py      (enforcement-only validator)
      engine/biocatalyst/sector_packet.py          (facts-only packet state builder)
      docs/research/                                 (research docs; prefix match)
      scripts/check_factor_boundaries.py             (this file — for selftest)
    Two inflation producers have occurrence-only AST warrants for their exact
    six-key all-False emissions; they are not allowlisted to read the field.

(c) Forbidden field name guard (rank/score/recommendation):
    FAIL if the state builder or shadow script emit fields named
    'rank', 'score', or 'recommendation' as dictionary key literals.
    Detects patterns like: "rank":  'score':  ["recommendation"]
    in those two specific files.  This is a belt-and-suspenders guard
    against accidentally introducing origination-adjacent field names.
    Comment and docstring lines are skipped.

SCAN SCOPE
----------
  engine/*.py, scripts/*.py, collectors/*.py
  Plus factor-module-specific files listed above.

Exit codes
----------
  0 : No violations found (or selftest passed).
  1 : One or more HARD violations found.

Usage
-----
  python scripts/check_factor_boundaries.py [--root PATH] [--selftest]

Pattern note
------------
Checks (a) and (c) are literal scans. Check (b) uses a narrow AST exception for
fixed all-false authority-mirror emissions in two named inflation producers;
all other paths retain the literal scan. Dynamic path construction without the
matching literal is NOT detected.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Factor modules subject to the Article-2 write guard (check-a)
# These are the canonical base names (repo-relative posix paths).
# ---------------------------------------------------------------------------

_FACTOR_MODULES = [
    "scripts/build_factor_panel.py",
    "scripts/build_factor_intelligence_state.py",
    "scripts/build_factor_deescalation_shadow.py",
    "engine/neuralweb/factor_contradictions.py",
    "engine/neuralweb/kernel_style.py",        # optional — checked if present
]

# Set of base names for fast membership testing in synthetic mode
_FACTOR_MODULE_SET: frozenset[str] = frozenset(_FACTOR_MODULES)

# ---------------------------------------------------------------------------
# Article-2 write-forbidden path fragments (check-a)
# Each entry is a substring that must NOT appear in code lines of factor-module
# source (comment and docstring lines are excluded from the scan).
# ---------------------------------------------------------------------------

_ARTICLE2_WRITE_PATTERNS = [
    "alert_triage",
    "board_ordering",
    "top_setups",
    "push_floor",
    "attention_queue",
]

# ---------------------------------------------------------------------------
# allowed_actions read — allowlisted paths (check-b)
# A file is "allowlisted" if its repo-relative path starts with any of these
# prefixes (case-sensitive, forward-slash normalised).
# ---------------------------------------------------------------------------

_ALLOWED_ACTIONS_ALLOWLIST_PREFIXES = [
    "scripts/build_factor_intelligence_state.py",
    "scripts/build_factor_deescalation_shadow.py",
    "scripts/check_factor_boundaries.py",
    "tests/",
    "admin/neural_web.py",
    "admin/static/app.js",
    "templates/factors.html.j2",
    "scripts/build_site.py",
    "engine/neuralweb/cortex.py",
    "engine/neuralweb/ask_brain.py",
    # Sector-intelligence contract enforcement may inspect allowed_actions only
    # to reject grants above the declared authority cap. It never uses the field
    # as a runtime behavior switch.
    "engine/sector_intelligence/contracts.py",
    # BC-N0a facts-only sector-packet compiler: validates the closed governance
    # action vocabulary and emits the same values as a descriptive authority
    # mirror. It cannot originate, rank, gate, size, or execute behavior.
    "engine/biocatalyst/sector_packet.py",
    # W7-A/W7-B operating packet producer + reader (#4822), same RUL-NW9 category
    # and the same two uses as sector_packet.py above, which #4822 split them out
    # beside without extending this list — so main has been red on check-b ever
    # since. Both are ENFORCEMENT-ONLY:
    #   producer:436  — rejects a packet whose allowed_actions is not a duplicate-free
    #                   non-empty subset of _ALLOWED_ACTIONS containing "observe"
    #   producer:677  — re-emits the same values into the descriptive authority mirror
    #   reader:376    — rejects a packet whose allowed_actions escapes _ALLOWED_ACTIONS
    # Nothing branches on WHICH action is present, so the field never becomes a
    # behavior wire; it is read only to REFUSE, which is the same warrant
    # engine/sector_intelligence/contracts.py carries.
    "engine/biocatalyst/packet_producer.py",
    "engine/biocatalyst/packet_reader.py",
    # R-ORTH rail state builder: emits allowed_actions/forbidden_actions as a
    # descriptive mirror only (RUL-ORTH-11; same RUL-NW9 category as the factor
    # state builder). It never reads the field to switch behavior.
    "engine/neuralweb/covariance_spine.py",
    # Evidence Clock (EC-R4): display-only aggregator emits allowed_actions/
    # forbidden_actions as descriptive packet fields; the checker verifies every
    # row carries promote/mutate_source_state in forbidden_actions. Neither
    # reads the field to switch behavior (same RUL-NW9 category as above).
    "engine/neuralweb/evidence_clock.py",
    "scripts/check_evidence_clock.py",
    # ETM registry (#1794): emits allowed_actions as a descriptive authority
    # mirror on registry rows (ETM-C2 display_only law); never a behavior wire.
    "engine/neuralweb/entity_thesis_mechanism_registry.py",
    # CN cycle phase state builder (CN-SYS-R1): emits allowed_actions as a
    # context_only display-framing map (phase → monitor_only/no_new_positions);
    # never reads the field to switch behavior. Same RUL-NW9 category.
    "engine/china_cycle_phase.py",
    "docs/research/",
]

# Release Radar inflation state builders (#5153) may *emit* one exact,
# descriptive authority mirror. These are deliberately not whole-file
# allowlist entries: any read, branch, or non-fixed emission in either producer
# remains a check-b violation. World State shares the exact module-level mirror
# below between its null and bounded lobe emissions; the AST check rejects any
# mutation, alias, or non-emission use of that binding.
_ALLOWED_ACTIONS_FIXED_EMISSION_PATHS = frozenset(
    {
        "engine/inflation_intelligence.py",
        "engine/neuralweb/world_state.py",
    }
)

_ALLOWED_ACTIONS_FIXED_KEYS = frozenset(
    {
        "may_rank",
        "may_score",
        "may_size",
        "may_gate",
        "may_escalate",
        "may_trade",
    }
)

_ALLOWED_ACTIONS_FIXED_CONSTANTS = {
    "engine/neuralweb/world_state.py": frozenset(
        {"_INFLATION_INTELLIGENCE_ALLOWED_ACTIONS"}
    ),
}

_ALLOWED_ACTIONS_FIXED_DICT_EMITTERS = {
    "engine/inflation_intelligence.py": frozenset(
        {"build_inflation_intelligence"}
    ),
    "engine/neuralweb/world_state.py": frozenset(
        {"_inflation_intelligence_null"}
    ),
}

_ALLOWED_ACTIONS_FIXED_KEYWORD_EMITTERS = {
    "engine/neuralweb/world_state.py": frozenset(
        {"_compose_inflation_intelligence"}
    ),
}

# ---------------------------------------------------------------------------
# Forbidden field names in state-builder and shadow script (check-c)
# ---------------------------------------------------------------------------

_STATE_BUILDER_FILES = [
    "scripts/build_factor_intelligence_state.py",
    "scripts/build_factor_deescalation_shadow.py",
]

_FORBIDDEN_FIELDS = ["rank", "score", "recommendation"]

# Matches forbidden field names as dict keys in various Python styles:
#   "rank": ...        → colon-suffix key form
#   'rank': ...        → single-quoted colon-suffix key form
#   ["rank"]           → bracket-subscript form
#   ['score']          → single-quoted bracket-subscript form
_FORBIDDEN_FIELD_RE = re.compile(
    r"""(?:"""
    r"""(?:['"]{1,3})(?:""" + "|".join(re.escape(f) for f in _FORBIDDEN_FIELDS) + r""")(?:['"]{1,3})\s*:"""  # "key": form
    r"""|"""
    r"""\[(?:['"]{1,3})(?:""" + "|".join(re.escape(f) for f in _FORBIDDEN_FIELDS) + r""")(?:['"]{1,3})\]"""   # ["key"] form
    r""")"""
)

# ---------------------------------------------------------------------------
# Line-level comment/docstring detection helpers
# ---------------------------------------------------------------------------

_TRIPLE_DOUBLE = '"""'
_TRIPLE_SINGLE = "'''"


def _is_code_line(line: str) -> bool:
    """Return True if the line is a code line (not a pure comment line).

    A pure comment line is one where the first non-whitespace character is '#'.
    Note: this does NOT detect docstring content — use _iter_code_lines() for
    full docstring-aware scanning.
    """
    stripped = line.lstrip()
    return bool(stripped) and stripped[0] != "#"


def _iter_code_lines(source: str) -> list[tuple[int, str]]:
    """Return (line_no, line) pairs for lines that are NOT in comment or docstring context.

    Simple state-machine: tracks whether we are inside a triple-quoted string.
    Rules:
      - Lines where the first non-whitespace char is '#' are comment lines — skipped.
      - Lines that contain a triple-quote delimiter where the delimiter count is ODD
        transition into/out of docstring mode — the transition line is itself treated
        as a docstring/non-code line and skipped.
      - Lines where a triple-quote opens AND closes on the same line (even count ≥ 2,
        two occurrences means a complete inline docstring) are treated as docstring
        lines and skipped.
      - Lines inside a docstring are skipped.
    Limitations (acceptable for a static guard):
      - Does not handle triple-quotes inside single-line strings.
      - Assumes well-formed Python.
    """
    result: list[tuple[int, str]] = []
    in_docstring = False
    docstring_delim: str = ""

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()

        if in_docstring:
            # Look for the closing delimiter
            if docstring_delim in line:
                # Count closings — if the line closes the docstring (odd total including
                # the already-entered count), exit docstring mode
                in_docstring = False
                docstring_delim = ""
                # The closing line itself is docstring — skip as code
            continue

        # Pure comment line — skip
        if stripped and stripped[0] == "#":
            continue

        # Blank line — skip (no pattern can match)
        if not stripped:
            continue

        # Check if this line contains a triple-quote
        is_docstring_line = False
        for delim in (_TRIPLE_DOUBLE, _TRIPLE_SINGLE):
            if delim not in stripped:
                continue
            count = stripped.count(delim)
            if count >= 2:
                # Delimiter appears 2+ times on same line — complete inline docstring.
                # Treat entire line as docstring; don't enter multi-line mode.
                is_docstring_line = True
                break
            if count == 1:
                # Odd occurrence — opens a multi-line docstring.
                in_docstring = True
                docstring_delim = delim
                is_docstring_line = True
                break

        if is_docstring_line:
            continue

        result.append((i, line))

    return result


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------

_THIS_SCRIPT = Path(__file__).name


def _scan_dirs(root: Path) -> list[Path]:
    """Return all .py files in engine/, scripts/, collectors/ (no __pycache__)."""
    files: list[Path] = []
    for subdir in ("engine", "scripts", "collectors"):
        d = root / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.py")):
            # Relative to the scan root `d`: an absolute-parts prune also matches
            # anything ABOVE the root, which silently skips every file when the
            # checkout path happens to contain the token (#3802).
            if "__pycache__" in f.relative_to(d).parts:
                continue
            if f.name == _THIS_SCRIPT:
                continue
            files.append(f)
    return files


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_factor_module(rel_path: str) -> bool:
    """Return True if the rel_path matches any entry in _FACTOR_MODULE_SET."""
    for fm in _FACTOR_MODULE_SET:
        if rel_path == fm or rel_path.endswith("/" + fm):
            return True
    return False


def _is_state_builder(rel_path: str) -> bool:
    """Return True if the rel_path matches a state-builder file."""
    for sb in _STATE_BUILDER_FILES:
        if rel_path == sb or rel_path.endswith("/" + sb):
            return True
    return False


def _is_allowlisted_for_allowed_actions(rel_path: str) -> bool:
    """Return True if the file is allowed to reference 'allowed_actions'."""
    for prefix in _ALLOWED_ACTIONS_ALLOWLIST_PREFIXES:
        if prefix.endswith("/") and rel_path.startswith(prefix):
            return True
        if not prefix.endswith("/") and rel_path == prefix:
            return True
    return False


def _is_fixed_false_actions_dict(node: ast.AST) -> bool:
    """Return whether *node* is the exact six-key, all-False authority mirror."""
    if (
        not isinstance(node, ast.Dict)
        or len(node.keys) != len(_ALLOWED_ACTIONS_FIXED_KEYS)
    ):
        return False

    keys: list[str] = []
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return False
        if not isinstance(value, ast.Constant) or value.value is not False:
            return False
        keys.append(key.value)
    return (
        len(set(keys)) == len(keys)
        and frozenset(keys) == _ALLOWED_ACTIONS_FIXED_KEYS
    )


def _binds_dict_name(node: ast.AST) -> bool:
    """Return whether an AST node can shadow the builtin ``dict`` name."""
    if (
        isinstance(node, ast.Name)
        and node.id == "dict"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ):
        return True
    if isinstance(node, ast.arg) and node.arg == "dict":
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == "dict"
    if isinstance(node, ast.alias):
        return (node.asname or node.name.split(".", maxsplit=1)[0]) == "dict"
    if isinstance(node, ast.ExceptHandler):
        return node.name == "dict"
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return "dict" in node.names
    if isinstance(node, (ast.MatchAs, ast.MatchStar)):
        return node.name == "dict"
    if isinstance(node, ast.MatchMapping):
        return node.rest == "dict"
    return False


def _enclosing_function_name(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> str | None:
    """Return the nearest enclosing function without relying on source lines."""
    parent = parents.get(id(node))
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent.name
        parent = parents.get(id(parent))
    return None


def _is_allowed_actions_value_position(
    value: ast.AST,
    rel_path: str,
    parents: dict[int, ast.AST],
) -> bool:
    """Return whether *value* is directly assigned to an allowed_actions emission."""
    parent = parents.get(id(value))
    if isinstance(parent, ast.keyword):
        call = parents.get(id(parent))
        return (
            parent.arg == "allowed_actions"
            and isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "update"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "out"
            and _enclosing_function_name(call, parents)
            in _ALLOWED_ACTIONS_FIXED_KEYWORD_EMITTERS.get(
                rel_path, frozenset()
            )
        )
    if isinstance(parent, ast.Dict):
        for key, candidate in zip(parent.keys, parent.values):
            if candidate is value:
                return (
                    isinstance(key, ast.Constant)
                    and key.value == "allowed_actions"
                    and _enclosing_function_name(parent, parents)
                    in _ALLOWED_ACTIONS_FIXED_DICT_EMITTERS.get(
                        rel_path, frozenset()
                    )
                )
    return False


def _sealed_fixed_constants(
    tree: ast.Module,
    rel_path: str,
    parents: dict[int, ast.AST],
) -> frozenset[str]:
    """Return configured fixed mirrors whose only loads are approved emissions.

    This is intentionally stricter than recognizing an all-False assignment:
    mutation, aliasing, helper reads, or using a shadowed ``dict`` constructor
    invalidates the constant and makes every emission site fail closed.
    """
    configured = _ALLOWED_ACTIONS_FIXED_CONSTANTS.get(rel_path, frozenset())
    if not configured:
        return frozenset()

    # A local binding could make dict(NAME) execute arbitrary code.
    if any(_binds_dict_name(node) for node in ast.walk(tree)):
        return frozenset()

    declarations: dict[str, ast.Name] = {}
    for statement in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        if (
            isinstance(target, ast.Name)
            and target.id in configured
            and value is not None
            and _is_fixed_false_actions_dict(value)
        ):
            declarations[target.id] = target

    sealed: set[str] = set()
    for name, declaration in declarations.items():
        valid = True
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or node.id != name:
                continue
            if node is declaration:
                continue
            parent = parents.get(id(node))
            if not (
                isinstance(node.ctx, ast.Load)
                and isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "dict"
                and parent.args == [node]
                and not parent.keywords
                and _is_allowed_actions_value_position(parent, rel_path, parents)
            ):
                valid = False
                break
        if valid:
            sealed.add(name)
    return frozenset(sealed)


def _is_fixed_actions_emission_value(
    node: ast.AST,
    sealed_constants: frozenset[str],
) -> bool:
    """Recognize only a literal mirror or a sealed ``dict(CONSTANT)`` copy."""
    if _is_fixed_false_actions_dict(node):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in sealed_constants
        and not node.keywords
    )


def _non_emission_allowed_actions_lines(rel_path: str, source: str) -> list[int]:
    """Return semantic allowed_actions references other than fixed emissions.

    Exemptions are AST-node identities, never line numbers. Consequently a
    legitimate emission and a read on the same source line still fail check-b.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fail closed for malformed source rather than accidentally granting a
        # whole-file exemption when the AST cannot prove an emission is inert.
        return [
            line_no
            for line_no, line in enumerate(source.splitlines(), start=1)
            if "allowed_actions" in line
        ]

    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    sealed_constants = _sealed_fixed_constants(tree, rel_path, parents)
    permitted_nodes: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "allowed_actions"
                    and _is_fixed_actions_emission_value(value, sealed_constants)
                    and _is_allowed_actions_value_position(
                        value, rel_path, parents
                    )
                ):
                    permitted_nodes.add(id(key))
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (
                    keyword.arg == "allowed_actions"
                    and _is_fixed_actions_emission_value(
                        keyword.value, sealed_constants
                    )
                    and _is_allowed_actions_value_position(
                        keyword.value, rel_path, parents
                    )
                ):
                    permitted_nodes.add(id(keyword))

    lines: set[int] = set()
    for node in ast.walk(tree):
        references_token = (
            isinstance(node, ast.Constant)
            and node.value == "allowed_actions"
        ) or (
            isinstance(node, ast.Name)
            and node.id == "allowed_actions"
        ) or (
            isinstance(node, ast.Attribute)
            and node.attr == "allowed_actions"
        ) or (
            isinstance(node, ast.arg)
            and node.arg == "allowed_actions"
        ) or (
            isinstance(node, ast.keyword)
            and node.arg == "allowed_actions"
        ) or (
            isinstance(node, (ast.Global, ast.Nonlocal))
            and "allowed_actions" in node.names
        )
        if references_token and id(node) not in permitted_nodes:
            lines.add(getattr(node, "lineno", 1))

    return sorted(lines)


# ---------------------------------------------------------------------------
# Violation data structure
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check: str       # "a", "b", or "c"
    module: str      # repo-relative path
    line_no: int
    pattern: str     # the pattern that triggered
    message: str


# ---------------------------------------------------------------------------
# Check (a): Article-2 write guard on factor-module files
# ---------------------------------------------------------------------------


def _check_a(root: Path, extra_files: dict[str, str] | None = None) -> list[Violation]:
    """FAIL if any factor-module contains an Article-2 path/surface code reference.

    Comment and docstring lines are excluded — documentation that enumerates
    the forbidden surfaces (to say 'we DON'T write here') must not trigger the guard.
    """
    violations: list[Violation] = []

    if extra_files is not None:
        # Synthetic mode — only scan files that match the factor-module filter
        file_iter: list[tuple[str, str]] = [
            (rel, src)
            for rel, src in extra_files.items()
            if _is_factor_module(rel)
        ]
    else:
        file_iter = []
        for rel_path in _FACTOR_MODULES:
            fp = root / rel_path
            if not fp.exists():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                file_iter.append((rel_path, text))
            except OSError:
                continue

    for rel_path, source in file_iter:
        for line_no, line in _iter_code_lines(source):
            for pat in _ARTICLE2_WRITE_PATTERNS:
                if pat in line:
                    violations.append(Violation(
                        check="a",
                        module=rel_path,
                        line_no=line_no,
                        pattern=pat,
                        message=(
                            f"FACTOR BOUNDARY VIOLATION (a): {rel_path}:{line_no} — "
                            f"factor module references Article-2 surface '{pat}' in code. "
                            "Factor modules must NEVER write to Article-2 surfaces "
                            "(alert_triage, board_ordering, top_setups, push_floor, "
                            "attention_queue). RUL-NW9/NW11."
                        ),
                    ))

    return violations


# ---------------------------------------------------------------------------
# Check (b): allowed_actions read guard (all engine/scripts/collectors files)
# ---------------------------------------------------------------------------


def _check_b(root: Path, extra_files: dict[str, str] | None = None) -> list[Violation]:
    """FAIL if 'allowed_actions' appears outside the allowlist."""
    violations: list[Violation] = []
    _TOKEN = "allowed_actions"

    if extra_files is not None:
        file_iter: list[tuple[str, str]] = list(extra_files.items())
    else:
        file_iter = []
        for fp in _scan_dirs(root):
            rel_path = _rel(fp, root)
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                file_iter.append((rel_path, text))
            except OSError:
                continue

    for rel_path, source in file_iter:
        if _TOKEN not in source:
            continue
        if rel_path in _ALLOWED_ACTIONS_FIXED_EMISSION_PATHS:
            violation_lines = _non_emission_allowed_actions_lines(rel_path, source)
        elif _is_allowlisted_for_allowed_actions(rel_path):
            continue
        else:
            violation_lines = [
                line_no
                for line_no, line in enumerate(source.splitlines(), start=1)
                if _TOKEN in line
            ]
        for line_no in violation_lines:
            violations.append(Violation(
                check="b",
                module=rel_path,
                line_no=line_no,
                pattern=_TOKEN,
                message=(
                    f"FACTOR BOUNDARY VIOLATION (b): {rel_path}:{line_no} — "
                    f"'allowed_actions' is read/referenced outside the allowlist. "
                    "This field is DESCRIPTIVE ONLY (RUL-NW9): it must never become "
                    "a behavior wire. Only the state builder, display/admin surfaces, "
                    "and tests may reference it."
                ),
            ))

    return violations


# ---------------------------------------------------------------------------
# Check (c): Forbidden field names in state-builder and shadow script
# ---------------------------------------------------------------------------


def _check_c(root: Path, extra_files: dict[str, str] | None = None) -> list[Violation]:
    """FAIL if state-builder or shadow script emit 'rank', 'score', 'recommendation'.

    Comment and docstring lines are excluded.
    Only scans _STATE_BUILDER_FILES (in both real and synthetic mode).
    """
    violations: list[Violation] = []

    if extra_files is not None:
        # Synthetic mode — only scan files that match the state-builder filter
        file_iter: list[tuple[str, str]] = [
            (rel, src)
            for rel, src in extra_files.items()
            if _is_state_builder(rel)
        ]
    else:
        file_iter = []
        for rel_path in _STATE_BUILDER_FILES:
            fp = root / rel_path
            if not fp.exists():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                file_iter.append((rel_path, text))
            except OSError:
                continue

    for rel_path, source in file_iter:
        for line_no, line in _iter_code_lines(source):
            m = _FORBIDDEN_FIELD_RE.search(line)
            if m:
                violations.append(Violation(
                    check="c",
                    module=rel_path,
                    line_no=line_no,
                    pattern=m.group(0),
                    message=(
                        f"FACTOR BOUNDARY VIOLATION (c): {rel_path}:{line_no} — "
                        f"state-builder/shadow script emits a forbidden field name: "
                        f"'{m.group(0)}'. Fields named rank/score/recommendation are "
                        "banned in factor artifacts (display-only law, RUL-NW9/NW11)."
                    ),
                ))

    return violations


# ---------------------------------------------------------------------------
# Selftest — planted violation round-trip
# ---------------------------------------------------------------------------


def _run_selftest(root: Path) -> int:
    """Plant synthetic violations for all three checks and verify detection.

    Returns 0 on pass, 1 on fail.
    """
    print("[selftest] check_factor_boundaries selftest — planting violations...")
    errors: list[str] = []

    # --- (a): Article-2 write in a factor-module file (code line) --
    synthetic_a = {
        "scripts/build_factor_panel.py": (
            "# This module does not write to alert_triage\n"   # comment — skip
            "output_path = 'data/alert_triage/foo.json'\n"    # code — catch
        ),
    }
    viols_a = _check_a(root, extra_files=synthetic_a)
    if not any(v.check == "a" and "alert_triage" in v.pattern for v in viols_a):
        errors.append("SELFTEST FAIL (a): planted alert_triage reference NOT detected in factor module")
    else:
        print("  [OK] check-a: Article-2 write in factor module detected")

    # --- (a-comment-skip): docstring/comment reference should NOT trigger --
    synthetic_a_comment = {
        "scripts/build_factor_panel.py": (
            "# NO write to alert_triage\n"
            '"""NO write to top_setups or board_ordering."""\n'
        ),
    }
    viols_a_comment = _check_a(root, extra_files=synthetic_a_comment)
    if viols_a_comment:
        errors.append(
            f"SELFTEST FAIL (a-comment): comment/docstring reference triggered violation "
            f"(should be skipped). Violations: {[v.message for v in viols_a_comment]}"
        )
    else:
        print("  [OK] check-a-comment: comment/docstring lines correctly skipped")

    # --- (a2): top_setups --
    synthetic_a2 = {
        "scripts/build_factor_intelligence_state.py": (
            "top_setups_path = 'data/top_setups/list.json'\n"
        ),
    }
    viols_a2 = _check_a(root, extra_files=synthetic_a2)
    if not any(v.check == "a" and "top_setups" in v.pattern for v in viols_a2):
        errors.append("SELFTEST FAIL (a2): planted top_setups reference NOT detected in factor module")
    else:
        print("  [OK] check-a2: top_setups write in factor module detected")

    # --- (a3): non-factor-module file should NOT be checked by check-a --
    synthetic_a3 = {
        "scripts/some_other_script.py": "path = 'data/alert_triage/foo.json'\n",
    }
    viols_a3 = _check_a(root, extra_files=synthetic_a3)
    if any(v.check == "a" for v in viols_a3):
        errors.append("SELFTEST FAIL (a3): non-factor-module file incorrectly flagged by check-a")
    else:
        print("  [OK] check-a3: non-factor-module file correctly ignored by check-a")

    # --- (b): allowed_actions outside allowlist --
    synthetic_b = {
        "engine/alert_triage.py": (
            "if state['allowed_actions']['may_deescalate']:\n"
            "    do_something()\n"
        ),
    }
    viols_b = _check_b(root, extra_files=synthetic_b)
    if not any(v.check == "b" and "alert_triage" in v.module for v in viols_b):
        errors.append("SELFTEST FAIL (b): allowed_actions read outside allowlist NOT detected")
    else:
        print("  [OK] check-b: allowed_actions outside allowlist detected")

    # --- (b clean): allowlisted file should not produce violation --
    synthetic_b_clean = {
        "scripts/build_factor_intelligence_state.py": (
            "def _build_allowed_actions():\n"
            "    return {'allowed_actions': {'may_rank': False}}\n"
        ),
    }
    viols_b_clean = _check_b(root, extra_files=synthetic_b_clean)
    if viols_b_clean:
        errors.append("SELFTEST FAIL (b-clean): allowlisted file produced spurious violation")
    else:
        print("  [OK] check-b-clean: allowlisted file produces no violation")

    # --- (b fixed emission): same World State line also contains a forbidden read --
    synthetic_b_fixed_emission = {
        "engine/neuralweb/world_state.py": (
            "_INFLATION_INTELLIGENCE_ALLOWED_ACTIONS = {\n"
            "    'may_rank': False, 'may_score': False, 'may_size': False,\n"
            "    'may_gate': False, 'may_escalate': False, 'may_trade': False,\n"
            "}\n"
            "def _inflation_intelligence_null():\n"
            "    payload = {'allowed_actions': "
            "dict(_INFLATION_INTELLIGENCE_ALLOWED_ACTIONS)}; "
            "observed = state.get('allowed_actions')\n"
            "    return payload\n"
        ),
    }
    viols_b_fixed_emission = _check_b(
        root, extra_files=synthetic_b_fixed_emission
    )
    if len(viols_b_fixed_emission) != 1:
        errors.append(
            "SELFTEST FAIL (b-fixed-emission): fixed World State emission must be "
            "ignored while a same-line allowed_actions read is detected"
        )
    else:
        print(
            "  [OK] check-b-fixed-emission: same-line World State read detected "
            "without rejecting fixed emission"
        )

    # --- (b enforcement): contract validator may reject, never drive behavior --
    synthetic_b_enforcement = {
        "engine/sector_intelligence/contracts.py": (
            "actions = document.get('allowed_actions')\n"
        ),
    }
    viols_b_enforcement = _check_b(root, extra_files=synthetic_b_enforcement)
    if viols_b_enforcement:
        errors.append(
            "SELFTEST FAIL (b-enforcement): contract validator produced spurious violation"
        )
    else:
        print("  [OK] check-b-enforcement: contract validator is enforcement-only")

    # --- (c): forbidden field in state builder (colon form) --
    synthetic_c = {
        "scripts/build_factor_intelligence_state.py": (
            'result = {"rank": 1, "ticker": "AAPL"}\n'
        ),
    }
    viols_c = _check_c(root, extra_files=synthetic_c)
    if not any(v.check == "c" and "rank" in v.pattern for v in viols_c):
        errors.append("SELFTEST FAIL (c): forbidden 'rank' field NOT detected in state builder")
    else:
        print("  [OK] check-c: forbidden field 'rank' in state builder detected (colon form)")

    # --- (c2): 'score' bracket form --
    synthetic_c2 = {
        "scripts/build_factor_deescalation_shadow.py": (
            '    row["score"] = 0.9\n'
        ),
    }
    viols_c2 = _check_c(root, extra_files=synthetic_c2)
    if not any(v.check == "c" and "score" in v.pattern for v in viols_c2):
        errors.append("SELFTEST FAIL (c2): forbidden 'score' field NOT detected in shadow script (bracket form)")
    else:
        print("  [OK] check-c2: forbidden field 'score' in shadow script detected (bracket form)")

    # --- (c3): 'recommendation' bracket form --
    synthetic_c3 = {
        "scripts/build_factor_intelligence_state.py": (
            '    payload["recommendation"] = "buy"\n'
        ),
    }
    viols_c3 = _check_c(root, extra_files=synthetic_c3)
    if not any(v.check == "c" and "recommendation" in v.pattern for v in viols_c3):
        errors.append("SELFTEST FAIL (c3): forbidden 'recommendation' field NOT detected")
    else:
        print("  [OK] check-c3: forbidden field 'recommendation' detected (bracket form)")

    # --- (c-non-target): non-state-builder file should NOT be checked --
    synthetic_c_nontarget = {
        "engine/neuralweb/cortex.py": '    result = {"score": 0.5}\n',
    }
    viols_c_nontarget = _check_c(root, extra_files=synthetic_c_nontarget)
    if any(v.check == "c" for v in viols_c_nontarget):
        errors.append("SELFTEST FAIL (c-non-target): non-state-builder file incorrectly flagged by check-c")
    else:
        print("  [OK] check-c-non-target: non-state-builder file correctly ignored by check-c")

    if errors:
        print("\n[selftest] FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1
    print("[selftest] ALL PASSED")
    return 0


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------


def scan(root: Path) -> list[Violation]:
    """Run all three checks and return combined violations list."""
    violations: list[Violation] = []
    violations.extend(_check_a(root))
    violations.extend(_check_b(root))
    violations.extend(_check_c(root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Factor boundary static guard (RUL-NW9/NW11).
            Checks three boundary rules for factor-module files.
            Exit 0 = clean. Exit 1 = violations found.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=None, help="Repo root path")
    parser.add_argument("--selftest", action="store_true",
                        help="Inject synthetic violations and verify detection; exit 0 on pass")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent

    if args.selftest:
        return _run_selftest(root)

    violations = scan(root)
    if not violations:
        print("check_factor_boundaries: CLEAN — no factor boundary violations found.")
        return 0

    print(f"check_factor_boundaries: {len(violations)} VIOLATION(S) FOUND:\n")
    for v in violations:
        print(f"  [{v.check.upper()}] {v.message}")
    print(
        "\nFix: ensure factor modules do not write to Article-2 surfaces in code, "
        "that 'allowed_actions' is read only by allowlisted files, "
        "and that state builders emit no rank/score/recommendation fields."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
