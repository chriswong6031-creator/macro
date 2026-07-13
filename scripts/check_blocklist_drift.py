"""scripts/check_blocklist_drift.py — R-V4-5 blocklist drift detector.

Three checks, all hard CI failures (capability-broker job, ci.yml):

  1. Registry drift — recompiles config/compiled_kill_registry.yml from
     research/DO_NOT_REBUILD.md into a temp dir and byte-diffs it against the
     committed file (an edit without regen, or a hand-edit of the compiled file).
  2. Signal-foundry drift — the same byte-diff for config/signal_foundry_blocklist.yml.
     The compiler only replaces its clearly-marked generated block, so hand-curated
     entries above the block never diff.
  3. Misplaced rows — pipe-table lines outside sections 1-4 of DO_NOT_REBUILD.md.
     The compiler parses ONLY sections 1-4; a row appended anywhere else (e.g.
     after §5) silently never reaches the compiled registry — an enforcement gap
     worse than drift (found live: the MRI-R38 CPI row, healed in the same PR
     that added this check).

Heal (same PR as the DO_NOT_REBUILD.md edit):
    python3 scripts/check_blocklist_drift.py --fix
    git add config/compiled_kill_registry.yml config/signal_foundry_blocklist.yml
A misplaced row is NOT auto-fixable — move it into the matching section 1-4
table, then re-run --fix.

Prevention: .claude/hooks/blocklist_regen_guard.py (PostToolUse) auto-runs the
regen on any harness Edit/Write to research/DO_NOT_REBUILD.md, so a red here
should only appear for edits made outside the harness (e.g. shell appends).

Usage:
    python3 scripts/check_blocklist_drift.py [--repo-root PATH] [--fix]

Exit codes:
    0   no drift — committed artifacts match current DO_NOT_REBUILD.md
    1   drift or misplaced rows detected, or I/O error
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

COMPILED_SECTIONS = (1, 2, 3, 4)

HEAL_RECIPE = """\
HEAL (same PR as the DO_NOT_REBUILD.md edit):
    python3 scripts/check_blocklist_drift.py --fix
    git add config/compiled_kill_registry.yml config/signal_foundry_blocklist.yml

TRIAGE: if your PR does NOT touch research/DO_NOT_REBUILD.md or the two config
blocklists, this drift pre-exists on main — do not absorb the fix into your PR.
Branch off fresh origin/main, run --fix there, and open a standalone heal PR.
"""


# ---------------------------------------------------------------------------
# Import the compiler (it lives in the same scripts/ directory)
# ---------------------------------------------------------------------------

def _import_compiler(repo_root: Path):  # type: ignore[return]
    """Import compile_loop_blocklists from scripts/ without modifying sys.path permanently."""
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(
        "compile_loop_blocklists",
        repo_root / "scripts" / "compile_loop_blocklists.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("Could not load scripts/compile_loop_blocklists.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Check 3 — misplaced rows
# ---------------------------------------------------------------------------

def find_misplaced_rows(md_text: str) -> list[tuple[int, str]]:
    """Return (line_no, line) for pipe-table lines the compiler cannot see.

    Mirrors the compiler's section semantics exactly: a section starts at a
    numbered '## N.' header and runs to the next numbered header; only
    sections 1-4 are parsed.  Any '|'-line elsewhere (preamble, §5+) is a
    registry row that silently never reaches the compiled registry.
    Fenced code blocks are ignored.
    """
    flagged: list[tuple[int, str]] = []
    section: int | None = None
    in_fence = False
    header_re = re.compile(r"^##\s+(\d+)\.")
    for i, line in enumerate(md_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = header_re.match(line)
        if m:
            section = int(m.group(1))
            continue
        if stripped.startswith("|") and section not in COMPILED_SECTIONS:
            flagged.append((i, stripped))
    return flagged


# ---------------------------------------------------------------------------
# Checks 1+2 — recompile and byte-diff both committed artifacts
# ---------------------------------------------------------------------------

def check_drift(repo_root: Path) -> int:
    """Run all drift checks.  Returns 0 = clean, 1 = drift or error."""
    md_path = repo_root / "research" / "DO_NOT_REBUILD.md"
    if not md_path.exists():
        print("ERROR: research/DO_NOT_REBUILD.md not found", file=sys.stderr)
        return 1

    failures: list[str] = []

    misplaced = find_misplaced_rows(md_path.read_text(encoding="utf-8"))
    if misplaced:
        print(
            "MISPLACED ROWS: table rows found outside sections 1-4 of "
            "research/DO_NOT_REBUILD.md — the compiler parses ONLY sections 1-4, "
            "so these rows never reach config/compiled_kill_registry.yml and are "
            "invisible to every enforcement loop:",
            file=sys.stderr,
        )
        for line_no, line in misplaced:
            print(f"  research/DO_NOT_REBUILD.md:{line_no}: {line[:120]}", file=sys.stderr)
        print(
            "NOT auto-fixable — move each row into the matching section 1-4 table, "
            "then run: python3 scripts/check_blocklist_drift.py --fix",
            file=sys.stderr,
        )
        failures.append("misplaced-rows")

    committed_registry = repo_root / "config" / "compiled_kill_registry.yml"
    committed_sf = repo_root / "config" / "signal_foundry_blocklist.yml"

    if not committed_registry.exists():
        print(
            "DRIFT: config/compiled_kill_registry.yml does not exist.",
            file=sys.stderr,
        )
        failures.append("registry-missing")

    # Recompile into a temp dir
    try:
        compiler = _import_compiler(repo_root)
    except Exception as exc:
        print(f"ERROR: could not load compiler: {exc}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        import shutil  # noqa: PLC0415

        (tmp_root / "research").mkdir()
        (tmp_root / "config").mkdir()
        (tmp_root / "scripts").mkdir()

        shutil.copy2(md_path, tmp_root / "research" / "DO_NOT_REBUILD.md")

        # Copy the committed signal_foundry_blocklist.yml so the compiler only
        # replaces the generated block — hand-curated entries pass through and
        # any diff below is real generated-block drift.
        if committed_sf.exists():
            shutil.copy2(committed_sf, tmp_root / "config" / "signal_foundry_blocklist.yml")

        try:
            rc = compiler.compile_blocklists(tmp_root)
        except Exception as exc:
            print(f"ERROR: compiler failed: {exc}", file=sys.stderr)
            return 1

        if rc != 0:
            print("ERROR: compiler exited non-zero", file=sys.stderr)
            return 1

        for name, committed_path in (
            ("compiled_kill_registry.yml", committed_registry),
            ("signal_foundry_blocklist.yml", committed_sf),
        ):
            regen_path = tmp_root / "config" / name
            if not regen_path.exists():
                print(f"ERROR: compiler did not produce {name}", file=sys.stderr)
                return 1
            if not committed_path.exists():
                # registry-missing already reported above; SF missing is the same class
                if name == "signal_foundry_blocklist.yml":
                    print(
                        "DRIFT: config/signal_foundry_blocklist.yml does not exist.",
                        file=sys.stderr,
                    )
                    failures.append("sf-missing")
                continue
            committed_bytes = committed_path.read_bytes()
            regen_bytes = regen_path.read_bytes()
            if committed_bytes != regen_bytes:
                print(
                    f"DRIFT DETECTED: config/{name} is out of sync with "
                    "research/DO_NOT_REBUILD.md.",
                    file=sys.stderr,
                )
                _print_diff(committed_bytes, regen_bytes)
                failures.append(name)

    if failures:
        print(file=sys.stderr)
        print(HEAL_RECIPE, file=sys.stderr)
        return 1

    print("check_blocklist_drift: OK — no drift detected.")
    return 0


def _print_diff(old: bytes, new: bytes) -> None:
    """Print a compact diff to stderr."""
    import difflib  # noqa: PLC0415
    old_lines = old.decode("utf-8", errors="replace").splitlines(keepends=True)
    new_lines = new.decode("utf-8", errors="replace").splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines, fromfile="committed", tofile="regenerated", n=3
    ))
    if diff:
        sys.stderr.writelines(diff[:80])
        if len(diff) > 80:
            print(f"  ... ({len(diff) - 80} more lines)", file=sys.stderr)


# ---------------------------------------------------------------------------
# --fix — regenerate in place, then re-check
# ---------------------------------------------------------------------------

def fix_drift(repo_root: Path) -> int:
    """Regenerate both artifacts in the real repo, then re-run the checks.

    Misplaced rows survive a --fix on purpose (moving a row into the right
    section is an editorial decision) — the re-check reports them.
    """
    artifacts = (
        repo_root / "config" / "compiled_kill_registry.yml",
        repo_root / "config" / "signal_foundry_blocklist.yml",
    )
    before = {p: (p.read_bytes() if p.exists() else None) for p in artifacts}

    try:
        compiler = _import_compiler(repo_root)
        rc = compiler.compile_blocklists(repo_root)
    except Exception as exc:
        print(f"ERROR: compiler failed: {exc}", file=sys.stderr)
        return 1
    if rc != 0:
        print("ERROR: compiler exited non-zero", file=sys.stderr)
        return 1

    changed = [
        p.relative_to(repo_root)
        for p in artifacts
        if (p.read_bytes() if p.exists() else None) != before[p]
    ]
    if changed:
        print("--fix: regenerated " + ", ".join(str(p) for p in changed)
              + " — commit them in the same PR as the DO_NOT_REBUILD.md edit.")
    else:
        print("--fix: artifacts already in sync — nothing regenerated.")

    return check_drift(repo_root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="R-V4-5 blocklist drift detector — exits 1 if compiled registry is stale."
    )
    ap.add_argument("--repo-root", default=None)
    ap.add_argument(
        "--fix",
        action="store_true",
        help="Regenerate both compiled artifacts in place, then re-check.",
    )
    args = ap.parse_args(argv)

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent

    if args.fix:
        return fix_drift(repo_root)
    return check_drift(repo_root)


if __name__ == "__main__":
    sys.exit(main())
