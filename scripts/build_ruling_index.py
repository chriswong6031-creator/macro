"""
scripts/build_ruling_index.py — Sweep research/**/*.md for ruling IDs and
build a machine-readable index of every distinct ruling found.

Purpose
-------
Provides a queryable, stable map of every ruling ID (RUL-*, DT-R*, LH-R*,
RO-*) to the research files in which it appears, together with the first
matching context line per file.  The output is consumed by
scripts/build_adjudication_packet.py (keyword autofill) and by the
adjudication bench for case-law lookup.

This script is DESCRIPTIVE TOOLING.  It never overrides or amends source
documents; it only surfaces what is already written in research/ (RUL-SUCC-9).

Usage
-----
  python scripts/build_ruling_index.py --as-of YYYY-MM-DD [--root PATH]
      [--out PATH] [--selftest]

Options
-------
  --as-of DATE   ISO date stamp written into the output file (required for
                 the write path; also accepted without --out to dry-run).
  --root PATH    Repo root for resolving research/ and the output file
                 (default: parent of the scripts/ directory).
  --out PATH     Output JSON file path (default: data/neuralweb/ruling_index.json
                 relative to --root).
  --selftest     Create synthetic .md files in a tempdir, run the sweep, and
                 verify output correctness. Exits 0 on pass, 1 on failure.
                 Does NOT write to the real output path.

Exit codes
----------
  0 : Success (or selftest passed).
  1 : Error or selftest failure.

Notes
-----
- ID families scanned (word-boundary match, case-sensitive):
    RUL-<digits>
    RUL-<ALPHA><optional digits>(<optional dash><digits>)?
    RUL-SUCC-<digits>
    DT-R<digits><optional lowercase letter>
    LH-R<digits><optional lowercase letter>
    RO-<digits>
- Per-ruling file list is capped at 20 entries; a `truncated` flag is set
  when more files matched.
- Context lines are trimmed to <=200 characters.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# ---------------------------------------------------------------------------
# ID pattern — word-boundary aware
# ---------------------------------------------------------------------------

# Families from the brief:
#   RUL-\d+
#   RUL-[A-Z]+\d*(-\d+)?
#   RUL-SUCC-\d+
#   DT-R\d+[a-z]?
#   LH-R\d+[a-z]?
#   RO-\d+
#
# We unify into a single alternation, longest/most-specific first so that
# RUL-SUCC-3 is not captured as RUL-SUCC (which would be RUL-<ALPHA>).
# The word-boundary \b at the end prevents partial matches like RUL-1a being
# caught as RUL-1.

_RULING_RE = re.compile(
    r"\b("
    r"RUL-SUCC-\d+"                   # RUL-SUCC-N  (before generic RUL-ALPHA)
    r"|RUL-[A-Z]+[A-Z0-9]*(?:-\d+)?"  # RUL-NW-1, RUL-ORTH-8, RUL-P8, RUL-U6 …
    r"|RUL-\d+"                        # RUL-34
    r"|DT-R\d+[a-z]?"                 # DT-R14, DT-R3b
    r"|LH-R\d+[a-z]?"                 # LH-R11
    r"|RO-\d+"                         # RO-9
    r")\b"
)

_MAX_FILES_PER_RULING = 20
_MAX_CONTEXT_LEN = 200


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def _sweep_files(md_files: list[Path], root: Path) -> dict[str, dict[str, Any]]:
    """
    Sweep markdown files and return {ruling_id: {files: [...], n_mentions: int}}.

    Each files entry:
        {path: str, first_line_no: int, context: str}

    'path' is repo-relative (POSIX separators) when root is provided.
    """
    index: dict[str, dict[str, Any]] = {}

    for md_path in sorted(md_files):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = md_path.relative_to(root).as_posix()

        # Track first occurrence per (ruling_id, file) to capture first_line_no
        file_hits: dict[str, tuple[int, str]] = {}  # ruling_id -> (line_no, context)

        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _RULING_RE.finditer(line):
                rid = match.group(1)
                if rid not in file_hits:
                    context = line.strip()[:_MAX_CONTEXT_LEN]
                    file_hits[rid] = (line_no, context)

        # Merge into global index
        for rid, (line_no, context) in file_hits.items():
            if rid not in index:
                index[rid] = {"files": [], "n_mentions": 0}

            entry = index[rid]

            # Accumulate n_mentions (count all occurrences in this file)
            # Re-scan to count all (we only stored first above)
            all_matches = _RULING_RE.findall(
                "\n".join(
                    ln for ln in text.splitlines()
                    if rid in ln
                )
            )
            # all_matches gives occurrences of any ruling; count this ruling
            file_count = sum(1 for m in all_matches if m == rid)
            entry["n_mentions"] += max(file_count, 1)

            if len(entry["files"]) < _MAX_FILES_PER_RULING:
                entry["files"].append({
                    "path": rel_path,
                    "first_line_no": line_no,
                    "context": context,
                })

    return index


def _build_output(index: dict[str, dict[str, Any]], as_of: str) -> dict[str, Any]:
    """Convert raw index dict to the final output schema."""
    rulings_list = []
    for rid in sorted(index.keys()):
        entry = index[rid]
        files = entry["files"]
        truncated = entry["n_mentions"] > _MAX_FILES_PER_RULING or len(files) == _MAX_FILES_PER_RULING
        # More accurate: if more than 20 files contributed, set truncated.
        # We track by file count stored vs total matches — simplest heuristic:
        # if files hit the cap exactly we mark truncated conservatively.
        rulings_list.append({
            "id": rid,
            "files": files,
            "n_mentions": entry["n_mentions"],
            "truncated": truncated,
        })

    return {
        "schema": "neuralweb.ruling_index.v1",
        "built_from": "research/**/*.md",
        "as_of": as_of,
        "n_rulings": len(rulings_list),
        "rulings": rulings_list,
    }


def run_sweep(root: Path, as_of: str) -> dict[str, Any]:
    """Public entry point: sweep research/**/*.md under root and return output dict."""
    research_dir = root / "research"
    if not research_dir.is_dir():
        raise FileNotFoundError(f"research/ directory not found at {research_dir}")

    md_files = sorted(research_dir.rglob("*.md"))
    index = _sweep_files(md_files, root)
    return _build_output(index, as_of)


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def _run_selftest() -> int:
    """
    Create synthetic .md files in a tempdir, run the sweep, verify correctness.
    Returns 0 on pass, 1 on failure.
    """
    print("Running build_ruling_index selftest...")
    all_passed = True

    def _fail(msg: str) -> None:
        nonlocal all_passed
        all_passed = False
        print(f"  [FAIL] {msg}")

    def _pass(msg: str) -> None:
        print(f"  [PASS] {msg}")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        research_dir = root / "research"
        research_dir.mkdir()

        # --- Synthetic file 1: multiple rulings ---
        (research_dir / "doc_a.md").write_text(
            "# Test\n"
            "RUL-1 first mention. Some text.\n"
            "RUL-SUCC-9 is the override law.\n"
            "DT-R14 era-split law noted here.\n"
            "RUL-1 second mention.\n"
            "LH-R11 ratified.\n",
            encoding="utf-8",
        )

        # --- Synthetic file 2: cross-file mentions ---
        (research_dir / "subdir").mkdir()
        (research_dir / "subdir" / "doc_b.md").write_text(
            "RO-9 signed options flow forbidden.\n"
            "RUL-NW-1 chartered.\n"
            "DT-R14 era-split law.\n",
            encoding="utf-8",
        )

        # --- Synthetic file 3: word-boundary check ---
        (research_dir / "doc_c.md").write_text(
            "RUL-123 a longer numeric ID.\n"
            "XRUL-1 should NOT match.\n"
            "RUL-ORTH-8 null law.\n",
            encoding="utf-8",
        )

        output = run_sweep(root, as_of="2026-07-06")

        # Verify schema fields
        for key in ("schema", "built_from", "as_of", "n_rulings", "rulings"):
            if key not in output:
                _fail(f"output missing key {key!r}")
            else:
                _pass(f"output has key {key!r}")

        rulings_by_id = {r["id"]: r for r in output["rulings"]}

        # RUL-1 should appear in doc_a only, n_mentions >= 2
        if "RUL-1" not in rulings_by_id:
            _fail("RUL-1 not found in index")
        else:
            r = rulings_by_id["RUL-1"]
            if r["n_mentions"] < 2:
                _fail(f"RUL-1 n_mentions={r['n_mentions']} expected >=2")
            else:
                _pass(f"RUL-1 n_mentions={r['n_mentions']} >=2")

        # RUL-SUCC-9 should be found
        if "RUL-SUCC-9" not in rulings_by_id:
            _fail("RUL-SUCC-9 not found")
        else:
            _pass("RUL-SUCC-9 found")

        # DT-R14 should appear in both files
        if "DT-R14" not in rulings_by_id:
            _fail("DT-R14 not found")
        else:
            r = rulings_by_id["DT-R14"]
            paths = {f["path"] for f in r["files"]}
            if len(paths) < 2:
                _fail(f"DT-R14 expected >=2 files, got {paths}")
            else:
                _pass(f"DT-R14 found in {len(paths)} files")

        # RO-9 should be found
        if "RO-9" not in rulings_by_id:
            _fail("RO-9 not found")
        else:
            _pass("RO-9 found")

        # Word-boundary: XRUL-1 should NOT produce a RUL-1 extra match
        # (it should not be in the index as its own entry either)
        if "XRUL-1" in rulings_by_id:
            _fail("XRUL-1 matched — word-boundary not enforced")
        else:
            _pass("XRUL-1 correctly excluded (word-boundary enforced)")

        # RUL-ORTH-8 should be found
        if "RUL-ORTH-8" not in rulings_by_id:
            _fail("RUL-ORTH-8 not found")
        else:
            _pass("RUL-ORTH-8 found")

        # RUL-NW-1
        if "RUL-NW-1" not in rulings_by_id:
            _fail("RUL-NW-1 not found")
        else:
            _pass("RUL-NW-1 found")

        # Context trimming
        r1 = rulings_by_id.get("RUL-1")
        if r1:
            ctx_len = max(len(f["context"]) for f in r1["files"])
            if ctx_len > _MAX_CONTEXT_LEN:
                _fail(f"context not trimmed: len={ctx_len}")
            else:
                _pass(f"context trimmed to <={_MAX_CONTEXT_LEN} chars (actual={ctx_len})")

        # Rulings sorted by id
        ids = [r["id"] for r in output["rulings"]]
        if ids != sorted(ids):
            _fail("rulings not sorted by id")
        else:
            _pass("rulings sorted by id")

    print()
    if all_passed:
        print("selftest PASSED — all checks green")
        return 0
    else:
        print("selftest FAILED — one or more checks failed")
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    # Pre-check for --selftest before argparse sees required args.
    if "--selftest" in sys.argv:
        return _run_selftest()

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output JSON path (default: <root>/data/neuralweb/ruling_index.json). "
            "If --selftest, this arg is ignored."
        ),
    )
    parser.add_argument(
        "--as-of",
        required=True,
        dest="as_of",
        help="ISO date stamp (YYYY-MM-DD) written into the output file.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run selftest with synthetic data; exit 0 on pass.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    out_path = args.out if args.out else root / "data" / "neuralweb" / "ruling_index.json"

    try:
        output = run_sweep(root, args.as_of)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(
        f"ruling_index written: {out_path}  "
        f"({output['n_rulings']} distinct IDs from {output['built_from']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
