"""scripts/check_factor_boundaries.py — Factor boundary static guard.

LANE: §D PR-5, RUL-NW9 / RUL-NW11 (NW_INTEGRATION_ADJUDICATION_BY_FABLE.md)

PURPOSE
-------
Literal-scan static guard that enforces three boundary rules for factor-module
files.  Modelled on check_synapse_reads.py and check_research_factory_authority.py
conventions; literal-path scan (no AST tracing — dynamic constructions not detected).

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
      engine/neuralweb/entity_thesis_mechanism_registry.py  (ETM state builder — emits AUTHORITY_BLOCK; PR #1794)
      docs/research/                                 (research docs; prefix match)
      scripts/check_factor_boundaries.py             (this file — for selftest)

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
This is a LITERAL-SCAN script (string pattern in source text).
Dynamic path construction without matching literals is NOT detected.
AST data-flow tracing is deferred to a later wave.
"""
from __future__ import annotations

import argparse
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
    # R-ORTH rail state builder: emits allowed_actions/forbidden_actions as a
    # descriptive mirror only (RUL-ORTH-11; same RUL-NW9 category as the factor
    # state builder). It never reads the field to switch behavior.
    "engine/neuralweb/covariance_spine.py",
    # ETM state builder (PR #1794): defines AUTHORITY_BLOCK constant which
    # declares allowed_actions as a display-only descriptor — this is the
    # *producer* of the field (emitting it into the artifact schema), never
    # a behavior wire. Same RUL-NW9 category as the factor state builder.
    "engine/neuralweb/entity_thesis_mechanism_registry.py",
    "docs/research/",
]

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
            if "__pycache__" in f.parts:
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
        if rel_path.startswith(prefix) or rel_path == prefix.rstrip("/"):
            return True
    return False


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
        if _is_allowlisted_for_allowed_actions(rel_path):
            continue
        # Found the token in a non-allowlisted file — find line numbers
        lines = source.splitlines()
        for i, line in enumerate(lines, start=1):
            if _TOKEN in line:
                violations.append(Violation(
                    check="b",
                    module=rel_path,
                    line_no=i,
                    pattern=_TOKEN,
                    message=(
                        f"FACTOR BOUNDARY VIOLATION (b): {rel_path}:{i} — "
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
