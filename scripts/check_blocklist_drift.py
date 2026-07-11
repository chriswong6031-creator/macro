"""scripts/check_blocklist_drift.py — R-V4-5 blocklist drift detector.

Recompiles config/compiled_kill_registry.yml from research/DO_NOT_REBUILD.md
into a temporary location, then byte-diffs it against the committed file.
Exits non-zero if they differ — meaning DO_NOT_REBUILD.md was edited without
regenerating the compiled registry.

Usage:
    python3 scripts/check_blocklist_drift.py [--repo-root PATH]

Exit codes:
    0   no drift — committed registry matches current DO_NOT_REBUILD.md
    1   drift detected or I/O error — regenerate with compile_loop_blocklists.py
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

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


def check_drift(repo_root: Path) -> int:
    """Run the drift check.  Returns 0 = clean, 1 = drift or error."""
    committed_path = repo_root / "config" / "compiled_kill_registry.yml"

    if not committed_path.exists():
        print(
            "DRIFT: config/compiled_kill_registry.yml does not exist.\n"
            "Regenerate with: python3 scripts/compile_loop_blocklists.py",
            file=sys.stderr,
        )
        return 1

    # Recompile into a temp dir
    try:
        compiler = _import_compiler(repo_root)
    except Exception as exc:
        print(f"ERROR: could not load compiler: {exc}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        # Symlink or copy the source files the compiler needs
        # We only need DO_NOT_REBUILD.md; the compiler writes only to config/
        import shutil  # noqa: PLC0415

        (tmp_root / "research").mkdir()
        (tmp_root / "config").mkdir()
        (tmp_root / "scripts").mkdir()

        src_md = repo_root / "research" / "DO_NOT_REBUILD.md"
        if not src_md.exists():
            print(
                "ERROR: research/DO_NOT_REBUILD.md not found",
                file=sys.stderr,
            )
            return 1
        shutil.copy2(src_md, tmp_root / "research" / "DO_NOT_REBUILD.md")

        # Copy existing signal_foundry_blocklist.yml so the diff only touches
        # the compiled part (avoid noise from the hand-curated section)
        sf_src = repo_root / "config" / "signal_foundry_blocklist.yml"
        if sf_src.exists():
            shutil.copy2(sf_src, tmp_root / "config" / "signal_foundry_blocklist.yml")

        # Run compiler on the temp root
        try:
            rc = compiler.compile_blocklists(tmp_root)
        except Exception as exc:
            print(f"ERROR: compiler failed: {exc}", file=sys.stderr)
            return 1

        if rc != 0:
            print("ERROR: compiler exited non-zero", file=sys.stderr)
            return 1

        regen_path = tmp_root / "config" / "compiled_kill_registry.yml"
        if not regen_path.exists():
            print("ERROR: compiler did not produce compiled_kill_registry.yml", file=sys.stderr)
            return 1

        committed_bytes = committed_path.read_bytes()
        regen_bytes = regen_path.read_bytes()

        if committed_bytes == regen_bytes:
            print("check_blocklist_drift: OK — no drift detected.")
            return 0

        # Show a diff for diagnostics
        print(
            "DRIFT DETECTED: config/compiled_kill_registry.yml is out of sync with "
            "research/DO_NOT_REBUILD.md.\n"
            "Regenerate with: python3 scripts/compile_loop_blocklists.py\n",
            file=sys.stderr,
        )
        _print_diff(committed_bytes, regen_bytes)
        return 1


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="R-V4-5 blocklist drift detector — exits 1 if compiled registry is stale."
    )
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args(argv)

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent

    return check_drift(repo_root)


if __name__ == "__main__":
    sys.exit(main())
