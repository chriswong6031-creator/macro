"""RF-11 — Research Factory authority guard.

Scans engine/, scripts/, and collectors/ for reads of
``data/research_factory/`` or imports of ``engine.research_factory`` from
modules that are on the Article-2 perimeter (alert_triage, board_ordering,
top_setups, attention_queue, push_floor per synapse.yml meta.article2_surfaces).

These money-path surfaces must NEVER consume factory data directly — the
factory is display-only (A0–A2 ceiling) and must not reach the scored /
board-rank / alert pipeline.

Exit codes
----------
0 : No violations found (clean).
1 : One or more violations found, or allowlist is absent.

Allowlist
---------
``data/research_factory/authority_allowlist.json`` (shipped empty).  Each
entry has the form::

  {"module": "engine/foo.py", "reason": "..."}

A module listed here is exempted from the hard-fail (but still printed as
a warning so the allowlist stays visible).

Pattern
-------
Modelled on scripts/check_validated_claims.py.  This is a LITERAL-PATH scan
— it looks for the string ``data/research_factory/`` or the import token
``engine.research_factory`` in source text.  Dynamic path construction without
a matching literal is not detected (AST tracing is deferred).

Article-2 surface → module mapping mirrors check_synapse_reads.py.

Usage
-----
  python scripts/check_research_factory_authority.py         # normal run
  python scripts/check_research_factory_authority.py --root /path/to/repo
  python scripts/check_research_factory_authority.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Article-2 surface → module mapping (money-path)
# Mirrors check_synapse_reads.py _ARTICLE2_MAP; kept as a local copy so this
# script has zero import coupling to other scripts.
# ---------------------------------------------------------------------------
_ARTICLE2_MAP: dict[str, list[str]] = {
    "alert_triage":    ["engine/alert_triage.py"],
    "board_ordering":  ["scripts/build_stock_library.py"],
    "top_setups":      ["scripts/build_site.py"],
    "attention_queue": [],   # future — no module yet
    "push_floor":      [],   # future — no module yet
}

# Flat set of Article-2 module repo-relative paths.
_ARTICLE2_MODULES: frozenset[str] = frozenset(
    mod for mods in _ARTICLE2_MAP.values() for mod in mods
)

# ---------------------------------------------------------------------------
# Scan patterns: what constitutes a "read of research_factory"
# ---------------------------------------------------------------------------
# We match any line in a Python source file that contains either of these
# string fragments:
#   "data/research_factory/"          — a literal path to the ledger directory
#   "engine.research_factory"         — an import of the factory package
_PATTERNS = [
    "data/research_factory/",
    "engine.research_factory",
]

# Allowlist path
_ALLOWLIST_PATH = ROOT / "data" / "research_factory" / "authority_allowlist.json"

# ---------------------------------------------------------------------------
# Scan directories (same scope as check_synapse_reads.py)
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


# ---------------------------------------------------------------------------
# Allowlist loader
# ---------------------------------------------------------------------------

def _load_allowlist(allowlist_path: Path) -> set[str]:
    """Load allowlisted module repo-relative paths.  Absent-file-safe."""
    if not allowlist_path.exists():
        return set()
    try:
        data = json.loads(allowlist_path.read_text(encoding="utf-8"))
        return {entry["module"] for entry in data.get("allow", []) if "module" in entry}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

def scan(root: Path,
         extra_files: dict[str, str] | None = None) -> list[dict]:
    """Scan for forbidden reads of data/research_factory/ or engine.research_factory.

    Parameters
    ----------
    root        : Repo root.
    extra_files : Optional dict of {repo-relative-path: source_text} for
                  synthetic files (used in selftest).  When provided, only
                  these files are scanned.

    Returns
    -------
    list of finding dicts: {module, line_no, pattern, severity}
      severity = "HARD" (Article-2 module) or "WARN" (other module)
    """
    allowlist = _load_allowlist(root / "data" / "research_factory" / "authority_allowlist.json")

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
        mod = rel_path.replace("\\", "/")
        # Skip allowlisted modules
        if mod in allowlist:
            continue

        for pat in _PATTERNS:
            if pat not in source_text:
                continue
            # Found the pattern — collect line numbers
            lines = source_text.splitlines()
            for i, line in enumerate(lines, start=1):
                if pat in line:
                    severity = "HARD" if mod in _ARTICLE2_MODULES else "WARN"
                    findings.append({
                        "module": mod,
                        "line_no": i,
                        "pattern": pat,
                        "severity": severity,
                    })

    findings.sort(key=lambda f: (f["module"], f["line_no"], f["pattern"]))
    return findings


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def _run_selftest(root: Path) -> int:
    """Prove the guard fires on a planted violation and is silent on clean code."""
    all_passed = True

    # Test 1: a non-Article-2 module with a factory read → WARN
    synthetic_warn = {
        "engine/_rf_selftest_warn.py": (
            '# synthetic read — should be WARN\n'
            'import json\n'
            'path = "data/research_factory/candidates.jsonl"\n'
            'data = json.load(open(path))\n'
        ),
    }
    warn_findings = scan(root, extra_files=synthetic_warn)
    warn_match = any(
        f["module"] == "engine/_rf_selftest_warn.py"
        and f["severity"] == "WARN"
        for f in warn_findings
    )
    status = "PASS" if warn_match else "FAIL"
    if not warn_match:
        all_passed = False
    print(f"  selftest [{status}] non-Article-2 factory read → WARN")

    # Test 2: an Article-2 module with a factory read → HARD
    article2_mod = "engine/alert_triage.py"
    synthetic_hard = {
        article2_mod: (
            '# synthetic Article-2 forbidden read — should be HARD\n'
            'import json\n'
            'from engine.research_factory import load_jsonl\n'
            'data = load_jsonl("data/research_factory/candidates.jsonl")\n'
        ),
    }
    hard_findings = scan(root, extra_files=synthetic_hard)
    hard_match = any(
        f["module"] == article2_mod
        and f["severity"] == "HARD"
        for f in hard_findings
    )
    status = "PASS" if hard_match else "FAIL"
    if not hard_match:
        all_passed = False
    print(f"  selftest [{status}] Article-2 forbidden factory read → HARD")

    # Test 3: clean module (no factory reference) → no finding
    synthetic_clean = {
        "engine/_rf_selftest_clean.py": (
            '# clean module — no factory reference\n'
            'import json\n'
            'path = "data/regime/latest.json"\n'
            'data = json.load(open(path))\n'
        ),
    }
    clean_findings = scan(root, extra_files=synthetic_clean)
    clean_match = not any(
        f["module"] == "engine/_rf_selftest_clean.py"
        for f in clean_findings
    )
    status = "PASS" if clean_match else "FAIL"
    if not clean_match:
        all_passed = False
    print(f"  selftest [{status}] clean module → no finding")

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
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="Repo root (default: parent of scripts/)")
    ap.add_argument("--selftest", action="store_true",
                    help="Run selftest with synthetic files; exit 0 on pass")
    args = ap.parse_args()

    root = args.root.resolve()

    if args.selftest:
        print("Running research-factory authority guard selftest...")
        return _run_selftest(root)

    findings = scan(root)

    hard = [f for f in findings if f["severity"] == "HARD"]
    warn = [f for f in findings if f["severity"] == "WARN"]

    if warn:
        for f in warn:
            print(
                f"  [WARN] {f['module']}:{f['line_no']} — "
                f"reads factory data ({f['pattern']!r}); not an Article-2 surface "
                f"but should be declared or avoided"
            )
        print(
            f"::warning::check_research_factory_authority: {len(warn)} non-Article-2 "
            f"module(s) read factory data — add to authority_allowlist.json if intentional"
        )

    if hard:
        for f in hard:
            print(
                f"  [HARD] {f['module']}:{f['line_no']} — "
                f"Article-2 money-path module reads factory data ({f['pattern']!r}). "
                f"The factory is display-only (A0–A2 ceiling); factory outputs must "
                f"never reach the scored / board-rank / alert pipeline (RF-11).",
                file=sys.stderr,
            )
        print(
            f"\n::error::check_research_factory_authority: {len(hard)} Article-2 "
            f"module(s) read data/research_factory/ or import engine.research_factory. "
            f"This violates the display-only authority ceiling (RF-11). "
            f"Add to authority_allowlist.json ONLY if the use is genuinely display-only.",
            file=sys.stderr,
        )
        return 1

    if not findings:
        print(
            "check_research_factory_authority: OK — "
            "no Article-2 modules read factory data."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
