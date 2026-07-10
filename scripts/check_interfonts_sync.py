#!/usr/bin/env python3
"""Static guard: the Inter @font-face blocks in templates/_interfonts.html.j2
must be byte-identical, in order, to the ones in templates/theme.css.

PR #2119 introduced templates/_interfonts.html.j2 — the six self-hosted Inter
@font-face rules copied verbatim from the top of templates/theme.css — and
included it in the <head> of the 16 standalone templates that do not link
theme.css. The partial's own comment says "keep the two in sync", but nothing
enforced it: an edit to the @font-face lines in theme.css (a new weight, a
renamed font file) would silently drift past the partial and the standalone
pages would lose the self-hosted font again — the exact regression #2119 fixed.

The law this enforces (ui.interfonts_theme_sync): every line starting with
"@font-face" in the partial must equal, byte-for-byte and in the same order,
the lines starting with "@font-face" in templates/theme.css, and there must be
exactly EXPECTED_COUNT of them. The count assertion is load-bearing: if both
files were reformatted so no line *starts with* "@font-face" (indented or
multi-line rules), plain list equality would pass vacuously on two empty
lists. Adding or removing a weight in BOTH files is a conscious act — bump
EXPECTED_COUNT here in the same PR.

Usage:
    python -m scripts.check_interfonts_sync             # report; exit 1 on drift
    python -m scripts.check_interfonts_sync --selftest  # gate fires on synthetic drift
Exit codes: 0 = in sync / selftest passed · 1 = drift found / selftest failed.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PARTIAL = "templates/_interfonts.html.j2"
THEME = "templates/theme.css"
EXPECTED_COUNT = 6  # bump only when adding/removing a weight in BOTH files


def _fontface_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [l for l in text.splitlines(keepends=True) if l.startswith("@font-face")]


def check(root: Path) -> list[str]:
    """Return human-readable findings; empty list means in sync."""
    partial_path, theme_path = root / PARTIAL, root / THEME
    missing = [str(p.relative_to(root)) for p in (partial_path, theme_path)
               if not p.is_file()]
    if missing:
        return [f"MISSING: {name} not found" for name in missing]

    partial = _fontface_lines(partial_path)
    theme = _fontface_lines(theme_path)
    findings: list[str] = []
    if partial != theme:
        findings.append(
            f"DRIFT: {PARTIAL} @font-face blocks drifted from {THEME} — "
            f"copy the {EXPECTED_COUNT} blocks verbatim (order included) "
            f"from the top of {THEME} into the partial's <style> block")
        for i, (got, want) in enumerate(zip(partial, theme)):
            if got != want:
                findings.append(f"  first mismatch at @font-face block {i + 1}:")
                findings.append(f"    partial: {got.rstrip()}")
                findings.append(f"    theme:   {want.rstrip()}")
                break
        else:
            findings.append(
                f"  block count differs: partial has {len(partial)}, "
                f"theme.css has {len(theme)}")
    if len(partial) != EXPECTED_COUNT:
        findings.append(
            f"COUNT: expected exactly {EXPECTED_COUNT} @font-face lines in "
            f"{PARTIAL}, found {len(partial)} — if a weight was intentionally "
            f"added/removed in BOTH files, bump EXPECTED_COUNT in "
            f"scripts/check_interfonts_sync.py in the same PR")
    return findings


def selftest() -> int:
    blocks = [
        f'@font-face{{font-family:Inter;font-weight:{w};'
        f'src:url("fonts/Inter-{w}.woff2") format("woff2");}}\n'
        for w in (400, 500, 600, 700, 800, 900)
    ]
    tmp = Path(tempfile.mkdtemp(prefix="check_interfonts_sync_selftest_"))
    try:
        (tmp / "templates").mkdir()
        partial_path, theme_path = tmp / PARTIAL, tmp / THEME

        # PASS: identical blocks (partial wrapped in <style>, theme with prose)
        partial_path.write_text("{#- partial -#}\n<style>\n" + "".join(blocks)
                                + "</style>\n")
        theme_path.write_text("/* theme */\n" + "".join(blocks) + "body{margin:0}\n")
        if check(tmp):
            print(f"selftest FAIL: in-sync pair reported findings: {check(tmp)}")
            return 1

        # FAIL: one edited line in theme.css (the drift shape — renamed file)
        theme_path.write_text(
            "/* theme */\n"
            + "".join(blocks).replace("Inter-700.woff2", "Inter-Bold.woff2")
            + "body{margin:0}\n")
        if not any(f.startswith("DRIFT") for f in check(tmp)):
            print("selftest FAIL: edited theme.css @font-face line not detected")
            return 1

        # FAIL: both files reformatted so no line starts with @font-face —
        # equality passes vacuously, the count assertion must fire.
        partial_path.write_text("<style>\n  @font-face{...}\n</style>\n")
        theme_path.write_text("  @font-face{...}\n")
        if not any(f.startswith("COUNT") for f in check(tmp)):
            print("selftest FAIL: vacuously-equal empty lists not caught by count")
            return 1

        print("selftest PASS: drift detected, vacuous-equality hole covered")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    root = Path(__file__).resolve().parent.parent
    findings = check(root)
    if not findings:
        print(f"interfonts sync OK ({EXPECTED_COUNT} @font-face blocks match "
              f"{THEME})")
        return 0
    for line in findings:
        print(line)
    print("interfonts sync FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
