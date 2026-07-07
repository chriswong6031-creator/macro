#!/usr/bin/env python3
"""Static guard: every site/ copy of a templates/ asset must byte-match its source.

2026-07-07 incident (root-caused — NOT a stale runner): the scope=all engine-render
run 28835838497 checked out main at 9208ef4920 (01:50Z), where templates/
sector_cycles.js already carried the UI-HZ-1 hazard block (old "validated"
wording, #1773) but site/sector_cycles.js did not yet — so the builders' copy
step staged a REAL diff (site := checkout-time template). While the 110-minute
render ran, #1793 merged and reworded BOTH files ("validated" → "passed the
W4.2 calibration gate" / "calibration-gated"). At push time the lane's
`git pull --rebase --autostash -X theirs origin main` hit a conflict on exactly
those hunks and -X theirs silently resolved in favor of the render's stale
copy: commit 2ae709f9f0 shipped site/sector_cycles.js byte-identical to the
checkout-time TEMPLATE blob (ca354e1c42), reverting #1793's site-side reword
and reddening the validated-claims gate on main. Fixed manually in #1799.

The law this enforces (ui.template_site_sync): for every plain-copy page asset
(templates/<name> that also exists at site/<name>), the committed site copy must
equal the committed template at every commit on main. Enforcement points:

  * pr_ci (ci.yml): a PR may not land a one-sided edit — rewording a template
    without its site copy (or vice versa) creates the divergence window the
    render lanes then propagate at an unpredictable later time (#1773's
    template-only edit is what armed this incident).
  * render lanes (render.yml / engine-render.yml / daily.yml): `--fix` runs
    AFTER each `git pull --rebase -X theirs` succeeds and BEFORE `git push`,
    re-copying every pair from the now-fresh post-rebase templates/ — so a
    reword that merged mid-render can never be clobbered by checkout-time
    content again.
  * publish (pages.yml): backstop — refuse to deploy a diverged tree.

theme.js legitimately differs from its template by the baked-in public Supabase
config (lib.site_assets.bake_theme_js, deterministic from committed config.yml).
Where PyYAML is available the comparison is exact against the baked output;
in stdlib-only contexts (pages.yml publish) it degrades to a token-split check
(prefix/suffix around the placeholder must match byte-for-byte).

Usage:
    python -m scripts.check_template_site_sync             # report + exit 1 on divergence
    python -m scripts.check_template_site_sync --fix       # rewrite site copies from templates/
    python -m scripts.check_template_site_sync --selftest  # gate fires on synthetic divergence
Exit codes: 0 = in sync / fixed / selftest passed · 1 = divergence found / selftest failed.

Known limits: direct children of templates/ only (the .j2 files are render
inputs, not shipped bytes; templates/fonts/ is a binary copytree); pairs where
the site copy does not exist yet are skipped (new asset not yet wired/shipped).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SKIP_SUFFIXES = (".j2",)
# Keep in sync with lib/site_assets.SUPABASE_TOKEN (asserted when lib is importable).
_THEME_TOKEN = "/*__SUPABASE_CFG__*/null"


def _bake_theme(tpl_text: str) -> str | None:
    """Baked theme.js content, or None when the bake is unavailable (no PyYAML)."""
    try:
        from lib import site_assets
        assert site_assets.SUPABASE_TOKEN == _THEME_TOKEN, "SUPABASE_TOKEN drifted"
        return site_assets.bake_theme_js(tpl_text)
    except AssertionError:
        raise
    except Exception as e:  # noqa: BLE001 — stdlib-only context (pages.yml publish)
        print(f"WARNING: theme.js bake unavailable ({e}) — using token-split compare")
        return None


def find_pairs(root: Path):
    """Yield (name, template_path, site_path) for every checkable pair."""
    tdir, sdir = root / "templates", root / "site"
    if not tdir.is_dir() or not sdir.is_dir():
        return
    for entry in sorted(tdir.iterdir()):
        if not entry.is_file() or entry.name.endswith(_SKIP_SUFFIXES):
            continue
        site_copy = sdir / entry.name
        if site_copy.is_file():
            yield entry.name, entry, site_copy


def check(root: Path, fix: bool = False) -> list[str]:
    """Return the names of diverged pairs (after fixing them when fix=True).

    In fix mode, pairs that could NOT be fixed (bake unavailable) are recorded
    in ``check.unfixed`` so main() can report honestly and exit nonzero.
    """
    diverged = []
    check.unfixed = []
    for name, tpl, site_copy in find_pairs(root):
        tpl_bytes, site_bytes = tpl.read_bytes(), site_copy.read_bytes()
        expected: bytes | None = tpl_bytes  # what --fix would write
        if name == "theme.js":
            tpl_text = tpl_bytes.decode("utf-8")
            baked = _bake_theme(tpl_text)
            if baked is not None:
                expected = baked.encode("utf-8")
                ok = site_bytes == expected
            else:
                # stdlib fallback: everything around the baked token must match.
                expected = None  # cannot reproduce the bake here — report-only
                site_text = site_bytes.decode("utf-8", errors="replace")
                head, sep, tail = tpl_text.partition(_THEME_TOKEN)
                ok = (site_text == tpl_text) if not sep else (
                    site_text.startswith(head) and site_text.endswith(tail)
                    and len(site_text) >= len(head) + len(tail))
        else:
            ok = site_bytes == tpl_bytes
        if ok:
            continue
        diverged.append(name)
        if fix:
            if expected is None:
                check.unfixed.append(name)
                print(f"WARNING: site/{name} diverged but the bake is unavailable — NOT fixed")
            else:
                site_copy.write_bytes(expected)
                print(f"FIXED: site/{name} restored from templates/{name}")
        else:
            print(f"DIVERGED: site/{name} != templates/{name} "
                  f"(site copies are derived — edit templates/{name} and re-copy, "
                  f"or run: python -m scripts.check_template_site_sync --fix)")
    return diverged


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="check_template_site_sync_selftest_"))
    try:
        (tmp / "templates").mkdir()
        (tmp / "site").mkdir()
        # PASS: identical pair
        (tmp / "templates" / "same.js").write_text("var a = 1;\n")
        (tmp / "site" / "same.js").write_text("var a = 1;\n")
        # FAIL: diverged pair (the incident shape — site copy carries older text)
        (tmp / "templates" / "diverged.js").write_text("tip = 'calibration-gated';\n")
        (tmp / "site" / "diverged.js").write_text("tip = 'validated';\n")
        # SKIPPED: render input, not a shipped byte-copy
        (tmp / "templates" / "page.html.j2").write_text("{{ x }}")
        # SKIPPED: template-only asset (no site copy yet)
        (tmp / "templates" / "unshipped.js").write_text("var b = 2;\n")

        bad = check(tmp)
        if bad != ["diverged.js"]:
            print(f"selftest FAIL: expected ['diverged.js'], got {bad}")
            return 1
        bad = check(tmp, fix=True)
        if bad != ["diverged.js"] or check(tmp):
            print("selftest FAIL: --fix did not restore the site copy to the template")
            return 1
        print("selftest PASS: divergence detected and --fix restores from templates/")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    fix = "--fix" in argv
    root = Path(__file__).resolve().parent.parent
    diverged = check(root, fix=fix)
    n_pairs = sum(1 for _ in find_pairs(root))
    if not diverged:
        print(f"template↔site sync OK ({n_pairs} pairs checked)")
        return 0
    if fix:
        unfixed = getattr(check, "unfixed", [])
        n_fixed = len(diverged) - len(unfixed)
        print(f"template↔site sync: {n_fixed} site cop{'y' if n_fixed == 1 else 'ies'} "
              f"restored from templates/ ({n_pairs} pairs checked)")
        if unfixed:
            print(f"template↔site sync: {len(unfixed)} diverged pair(s) NOT fixable here: {unfixed}")
            return 1
        return 0
    print(f"template↔site sync FAILED: {len(diverged)} of {n_pairs} pairs diverged")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
