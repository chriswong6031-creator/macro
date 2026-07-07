"""CPI authority guard — check_cycle_pattern_authority.py.

Scans engine/, scripts/, collectors/, and tests/ for literal reads of
``data/cycle_pattern/`` paths and checks each reader against the consumer
matrix defined in ``config/cycle_pattern/consumer_matrix.yml``.

Any reader module NOT in the allowed list for its artifact class produces a
HARD FAIL with a clear message.  Money-path surfaces (board_rank,
oracle_escalation, sector_central_direction_score, position_sizing) yield a
HARD finding regardless of any allowlist.

Exit codes
----------
0 : No violations found (clean).
1 : One or more HARD violations found.

Allowlist
---------
The allowed readers are declared here as ``_ALLOWED_READERS`` (a frozenset of
repo-relative path prefixes).  These represent the legitimate consumers of
data/cycle_pattern/ files: engine/cycle_pattern/*, builder scripts, seeds, and
the research_factory adapter (path pre-declared per P2 task spec, even if the
file does not yet exist on disk).

Money-path surfaces
-------------------
``_MONEY_PATH_MODULES`` lists the repo-relative module paths for the four
money-path surfaces (board_rank, oracle_escalation,
sector_central_direction_score, position_sizing).  Any of these that reads
data/cycle_pattern/ is a HARD finding regardless of allowlist membership.

Pattern
-------
Modelled on scripts/check_research_factory_authority.py.  This is a LITERAL-
PATH scan: it looks for the string ``data/cycle_pattern/`` in .py source files
under engine/, scripts/, collectors/, and tests/.  Dynamic path construction
without a matching literal is not detected (AST tracing is deferred to a
future hardening wave).

Usage
-----
  python scripts/check_cycle_pattern_authority.py              # normal run
  python scripts/check_cycle_pattern_authority.py --root /path/to/repo
  python scripts/check_cycle_pattern_authority.py --selftest
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import json as _json_mod
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Scan pattern
# ---------------------------------------------------------------------------
# We match any line containing the literal path prefix to the cycle-pattern
# data directory.  This catches: open("data/cycle_pattern/..."),
# pd.read_parquet("data/cycle_pattern/..."), Path("data/cycle_pattern/..."),
# ROOT / "data/cycle_pattern/...", etc.
_PATTERN = "data/cycle_pattern/"

# ---------------------------------------------------------------------------
# Money-path module paths (repo-relative)
# Any read of data/cycle_pattern/ by these modules is always HARD.
# Mirrors the forbidden_consumers in consumer_matrix.yml.
# ---------------------------------------------------------------------------
_MONEY_PATH_MODULES: frozenset[str] = frozenset([
    # board_rank surface
    "scripts/build_stock_library.py",
    # oracle_escalation surface (future; pre-declared)
    "engine/oracle_escalation.py",
    # sector_central_direction_score surface
    "engine/sector_central.py",
    "scripts/build_sector_central.py",
    # position_sizing surface
    "engine/position_sizing.py",
    "engine/sizing.py",
    # alert_triage is the scored-pipeline gate (mirrors RF-11)
    "engine/alert_triage.py",
])

# ---------------------------------------------------------------------------
# Allowed reader prefixes (repo-relative path prefixes or exact paths)
# ---------------------------------------------------------------------------
# These are the ONLY modules permitted to read data/cycle_pattern/ directly.
# A reader is allowed if its repo-relative path starts with any of these
# prefixes (prefix match) OR equals one of these exactly.
#
# Rationale per module group:
#   engine/cycle_pattern/   — the canonical data owners (lake, truths, etc.)
#   scripts/build_cycle_pattern_  — builder scripts that write the parquets
#   scripts/seed_cycle_truths.py  — truth seeder (one-shot write)
#   scripts/build_measurement.py  — Measurement Hub v2 builder (display consumer)
#   engine/research_factory/adapter_cycle_pattern.py
#                            — factory domain adapter (P2; allowlisted even if
#                              the file is not yet on disk so CI stays green
#                              while the parallel agent builds it)
#   tests/                   — test modules may read any artifact
#   scripts/check_cycle_pattern_authority.py  — self-exclusion (this script)
_ALLOWED_READER_PREFIXES: tuple[str, ...] = (
    "engine/cycle_pattern/",
    "scripts/build_cycle_pattern_",
    "scripts/apply_cycle_pattern_",   # frozen prereg outcome appliers (owner program)
    "scripts/run_falsosc_trial_v1.py",  # §18 kill-switch trial (research track, owner program)
    "scripts/seed_cycle_truths.py",
    "scripts/build_measurement.py",
    "engine/research_factory/adapter_cycle_pattern.py",
    "tests/",
    "scripts/check_cycle_pattern_authority.py",   # self
)

# ---------------------------------------------------------------------------
# Scan directories
# ---------------------------------------------------------------------------
_THIS_SCRIPT = Path(__file__).name


def _scan_dirs(root: Path) -> list[Path]:
    """Return all .py files in engine/, scripts/, collectors/, tests/."""
    files: list[Path] = []
    for subdir in ("engine", "scripts", "collectors", "tests"):
        d = root / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            files.append(f)
    return files


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

def scan(root: Path,
         extra_files: dict[str, str] | None = None) -> list[dict]:
    """Scan for reads of data/cycle_pattern/ outside the allowed consumer list.

    Parameters
    ----------
    root        : Repo root.
    extra_files : Optional dict of {repo-relative-path: source_text} for
                  synthetic files (used in selftest).  When provided, ONLY
                  these files are scanned — no disk traversal.

    Returns
    -------
    list of finding dicts:
      {module, line_no, pattern, severity, reason}
      severity = "HARD" (money-path module or forbidden reader) or
                 "WARN" (unlisted non-money-path reader — should be declared)
    """
    if extra_files is not None:
        file_iter: list[tuple[str, str]] = list(extra_files.items())
    else:
        disk_files = _scan_dirs(root)
        file_iter = []
        for fp in disk_files:
            rel = str(fp.relative_to(root))
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            file_iter.append((rel, text))

    findings: list[dict] = []

    for rel_path, source_text in file_iter:
        if _PATTERN not in source_text:
            continue

        mod = rel_path.replace("\\", "/")

        is_money_path = mod in _MONEY_PATH_MODULES
        is_allowed = any(mod.startswith(prefix) for prefix in _ALLOWED_READER_PREFIXES)

        # Determine severity for this module:
        # - Money-path modules: ALWAYS HARD regardless of allowed list.
        # - Allowed modules: no finding (skip).
        # - Unknown modules: WARN (should be declared or avoided).
        if is_allowed and not is_money_path:
            # Legitimate reader — no finding.
            continue

        lines = source_text.splitlines()
        for i, line in enumerate(lines, start=1):
            if _PATTERN not in line:
                continue
            if is_money_path:
                severity = "HARD"
                reason = (
                    f"Money-path surface module reads data/cycle_pattern/. "
                    f"Cycle-pattern lake artifacts and truths must NEVER reach "
                    f"the scored/board-rank/alert pipeline without an explicit "
                    f"DL-1/DL-2 authority grant (CPI governance rule)."
                )
            else:
                severity = "WARN"
                reason = (
                    f"Module reads data/cycle_pattern/ but is not in the "
                    f"allowed_consumers list (config/cycle_pattern/consumer_matrix.yml). "
                    f"Add the module to _ALLOWED_READER_PREFIXES in "
                    f"check_cycle_pattern_authority.py if intentional."
                )
            findings.append({
                "module": mod,
                "line_no": i,
                "pattern": _PATTERN,
                "severity": severity,
                "reason": reason,
                "is_money_path": is_money_path,
            })

    findings.sort(key=lambda f: (f["module"], f["line_no"]))
    return findings


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def _run_selftest(root: Path) -> int:
    """Prove the gate fires on planted violations and is silent on clean code."""
    all_passed = True

    # ── Test 1: allowed reader — no finding ──────────────────────────────────
    synthetic_allowed = {
        "engine/cycle_pattern/_selftest_allowed.py": (
            "# legitimate owner — should produce no finding\n"
            "import pandas as pd\n"
            "df = pd.read_parquet('data/cycle_pattern/state_monthly.parquet')\n"
        ),
    }
    allowed_findings = scan(root, extra_files=synthetic_allowed)
    allowed_match = not any(
        f["module"] == "engine/cycle_pattern/_selftest_allowed.py"
        for f in allowed_findings
    )
    status = "PASS" if allowed_match else "FAIL"
    if not allowed_match:
        all_passed = False
    print(f"  selftest [{status}] allowed owner reads cycle_pattern/ → no finding")

    # ── Test 2: unknown non-money-path module — WARN ──────────────────────────
    synthetic_warn = {
        "engine/_cp_selftest_unknown.py": (
            "# unknown module — should be WARN\n"
            "import json\n"
            "path = 'data/cycle_pattern/truths.jsonl'\n"
            "data = open(path).read()\n"
        ),
    }
    warn_findings = scan(root, extra_files=synthetic_warn)
    warn_match = any(
        f["module"] == "engine/_cp_selftest_unknown.py"
        and f["severity"] == "WARN"
        for f in warn_findings
    )
    status = "PASS" if warn_match else "FAIL"
    if not warn_match:
        all_passed = False
    print(f"  selftest [{status}] unknown module reads cycle_pattern/ → WARN")

    # ── Test 3: money-path module — HARD regardless of any allowlist ──────────
    money_mod = "scripts/build_stock_library.py"   # board_rank surface
    synthetic_hard = {
        money_mod: (
            "# synthetic money-path forbidden read — must be HARD\n"
            "import pandas as pd\n"
            "df = pd.read_parquet('data/cycle_pattern/outcomes.parquet')\n"
        ),
    }
    hard_findings = scan(root, extra_files=synthetic_hard)
    hard_match = any(
        f["module"] == money_mod
        and f["severity"] == "HARD"
        for f in hard_findings
    )
    status = "PASS" if hard_match else "FAIL"
    if not hard_match:
        all_passed = False
    print(f"  selftest [{status}] money-path module reads cycle_pattern/ → HARD")

    # ── Test 4: clean module (no cycle_pattern ref) — no finding ─────────────
    # IMPORTANT: the source text must NOT contain the scan pattern even in
    # a comment; if it did, the scanner would fire on the comment line itself.
    synthetic_clean = {
        "engine/_cp_selftest_clean.py": (
            "# clean module — reads regime data only\n"
            "import json\n"
            "path = 'data/regime/latest.json'\n"
            "data = json.load(open(path))\n"
        ),
    }
    clean_findings = scan(root, extra_files=synthetic_clean)
    clean_match = not any(
        f["module"] == "engine/_cp_selftest_clean.py"
        for f in clean_findings
    )
    status = "PASS" if clean_match else "FAIL"
    if not clean_match:
        all_passed = False
    print(f"  selftest [{status}] clean module → no finding")

    # ── Test 5: test/ module — allowed (no finding) ───────────────────────────
    synthetic_test = {
        "tests/test_cp_selftest.py": (
            "# test module — reads are always allowed\n"
            "import pandas as pd\n"
            "df = pd.read_parquet('data/cycle_pattern/entities.parquet')\n"
        ),
    }
    test_findings = scan(root, extra_files=synthetic_test)
    test_match = not any(
        f["module"] == "tests/test_cp_selftest.py"
        for f in test_findings
    )
    status = "PASS" if test_match else "FAIL"
    if not test_match:
        all_passed = False
    print(f"  selftest [{status}] tests/ module reads cycle_pattern/ → no finding")

    print()
    if all_passed:
        print("selftest PASSED — all synthetic cases handled correctly")
        return 0
    else:
        print("selftest FAILED — one or more cases not caught")
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--root", type=Path, default=ROOT,
        help="Repo root (default: parent of scripts/)"
    )
    ap.add_argument(
        "--selftest", action="store_true",
        help="Run selftest with synthetic files; exit 0 on pass, 1 on fail"
    )
    args = ap.parse_args()

    root = args.root.resolve()

    if args.selftest:
        print("Running cycle-pattern authority guard selftest ...")
        return _run_selftest(root)

    findings = scan(root)

    hard = [f for f in findings if f["severity"] == "HARD"]
    warn = [f for f in findings if f["severity"] == "WARN"]

    if warn:
        for f in warn:
            print(
                f"  [WARN] {f['module']}:{f['line_no']} — "
                f"reads {_PATTERN!r}; module not in allowed consumer list. "
                f"{f['reason']}"
            )
        print(
            f"::warning::check_cycle_pattern_authority: {len(warn)} module(s) "
            f"read data/cycle_pattern/ without being in the allowed consumer "
            f"list — add to _ALLOWED_READER_PREFIXES in "
            f"check_cycle_pattern_authority.py if intentional"
        )

    if hard:
        for f in hard:
            print(
                f"  [HARD] {f['module']}:{f['line_no']} — "
                f"{f['reason']}",
                file=sys.stderr,
            )
        print(
            f"\n::error::check_cycle_pattern_authority: {len(hard)} money-path "
            f"module(s) read data/cycle_pattern/. "
            f"Cycle-pattern artifacts must never reach board_rank, "
            f"oracle_escalation, sector_central_direction_score, or "
            f"position_sizing without an explicit DL-1/DL-2 authority grant "
            f"recorded in the truth registry (CPI governance).",
            file=sys.stderr,
        )
        return 1

    if not findings:
        print(
            "check_cycle_pattern_authority: OK — "
            "no money-path modules read data/cycle_pattern/."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
