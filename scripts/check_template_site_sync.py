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
config and bundled Terminal overlay (lib.site_assets.emit_theme_js, deterministic
from committed sources/config.yml). Where PyYAML is available the comparison is
exact against the emitted output; in stdlib-only contexts (pages.yml publish) it
degrades to a token-split check (the prefix/suffix around the placeholder plus
the overlay suffix must match byte-for-byte).

Usage:
    python -m scripts.check_template_site_sync             # report + exit 1 on divergence
    python -m scripts.check_template_site_sync --fix       # rewrite site copies from templates/
    python -m scripts.check_template_site_sync --selftest  # gate fires on synthetic divergence
Exit codes: 0 = in sync / fixed / selftest passed · 1 = divergence found / selftest failed
/ --fix refused a wrong-direction copy (see template_is_the_stale_side).

`--fix` heals in ONE direction (templates/ -> site/) and cannot heal the other:
when a render-lane push advances the site copy without its template, that copy is
the fresher side and --fix would clobber it. Since 2026-07-26 the fix refuses
exactly that case instead of reporting the clobber as a heal; the pair stays
diverged and loud until a human heals templates/ from site/.

Known limits: direct children of templates/ only (the .j2 files are render
inputs, not shipped bytes; templates/fonts/ is a binary copytree); pairs where
the site copy does not exist yet are skipped (new asset not yet wired/shipped).
"""
from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SKIP_SUFFIXES = (".j2",)
# Keep in sync with lib/site_assets (asserted when lib is importable). EVERY bake
# token theme.js carries must be listed: the stdlib fallback below compares the
# INVARIANT text around them, so a token this list does not know about reads as a
# real divergence and refuses the publish (pages.yml) on a perfectly healthy tree.
_THEME_TOKEN = "/*__SUPABASE_CFG__*/null"
_MM_BRAIN_VER_TOKEN = "/*__MM_BRAIN_VER__*/''"
_THEME_TOKENS = (_THEME_TOKEN, _MM_BRAIN_VER_TOKEN)
# OUR ?v= stamp shape, as written by lib.pages.optimize_assets_text: an 8-hex
# sha256 prefix and nothing else. A hand-written query (?v=3, ?foo=bar) is not
# ours and is deliberately not audited here — same rule the stamper applies.
_STAMP_RE = re.compile(r"""(?:href|src)=["']([^"'?#>]+)\?v=([0-9a-f]{8})["']""")


def _bake_theme(tpl: Path) -> str | None:
    """Emitted theme.js content, or None when the bake is unavailable (no PyYAML)."""
    try:
        from lib import site_assets
        assert site_assets.SUPABASE_TOKEN == _THEME_TOKEN, "SUPABASE_TOKEN drifted"
        assert site_assets.MM_BRAIN_VER_TOKEN == _MM_BRAIN_VER_TOKEN, "MM_BRAIN_VER_TOKEN drifted"
        return site_assets.emit_theme_js(tpl)
    except AssertionError:
        raise
    except Exception as e:  # noqa: BLE001 — stdlib-only context (pages.yml publish)
        print(f"WARNING: theme.js bake unavailable ({e}) — using token-split compare")
        return None


def _token_segments(text: str, tokens: tuple[str, ...]) -> list[str]:
    """``text`` split on every bake token, in the order the tokens appear.

    The result is the INVARIANT text: the parts the bake never rewrites. N tokens
    yield N+1 segments (any of them possibly empty).
    """
    segs: list[str] = []
    rest = text
    while True:
        hits = [(rest.find(t), t) for t in tokens]
        hits = [(i, t) for i, t in hits if i >= 0]
        if not hits:
            segs.append(rest)
            return segs
        i, tok = min(hits)
        segs.append(rest[:i])
        rest = rest[i + len(tok):]


def _matches_around_tokens(site_text: str, segs: list[str]) -> bool:
    """Whether ``site_text`` is ``segs`` in order with anything at the token slots.

    The stdlib-only stand-in for a real bake comparison (pages.yml publish has no
    PyYAML, so ``emit_theme_js`` cannot run there). Deliberately weaker than the
    byte compare it replaces — it cannot know what the bake WOULD have produced,
    only that everything the bake does not touch is untouched. It is a publish
    backstop, never the PR gate; ci.yml runs the exact compare.
    """
    if len(segs) == 1:
        return site_text == segs[0]
    if not site_text.startswith(segs[0]):
        return False
    pos = len(segs[0])
    for seg in segs[1:-1]:
        if seg:
            j = site_text.find(seg, pos)
            if j < 0:
                return False
            pos = j + len(seg)
    return site_text.endswith(segs[-1]) and len(site_text) >= pos + len(segs[-1])


def _stamp_audit(text: str, site_dir: Path) -> tuple[int, int]:
    """(current, stale) counts of OUR ?v= stamps that resolve inside ``site_dir``.

    Refs resolve against site/ for BOTH sides of a pair, because that is where the
    page ships from and it is exactly how scripts.optimize_assets hashes the
    templates/ side (``optimized(text, root)``). Refs that leave the tree, are
    cross-origin, or name a file that does not exist are not evidence either way
    and are skipped.
    """
    current = stale = 0
    for url, stamp in _STAMP_RE.findall(text):
        if url.startswith(("http://", "https://", "//", "data:", "mailto:")):
            continue
        try:
            target = (site_dir / url).resolve()
            target.relative_to(site_dir.resolve())
        except (ValueError, OSError):
            continue
        if not target.is_file():
            continue
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()[:8]
        except OSError:
            continue
        if actual == stamp:
            current += 1
        else:
            stale += 1
    return current, stale


def template_is_the_stale_side(tpl_bytes: bytes, site_bytes: bytes, site_dir: Path) -> bool:
    """True when a DIVERGED pair's evidence says templates/ — not site/ — is behind.

    `--fix` only ever copies templates/ -> site/. That direction is right when a PR
    edits a template one-sidedly, and wrong whenever the SITE copy is the fresher
    one — which a render-lane push can produce with no PR in between. 2026-07-26
    render 886fe25d89e advanced site/chat.html (theme.js?v=c094a665 plus the
    product-nav-icons preload) and left templates/chat.html at ?v=16dc65dc; running
    `--fix` there would have re-pinned every returning browser to bytes theme.js no
    longer had, under `immutable, max-age=1y` at the edge — the #3617/#3624 failure
    the ui.asset_stamp law exists to prevent, and silent, because --fix reports a
    clobber and a heal identically. #3676 healed it by hand in the other direction.

    The test is deliberately narrow and asymmetric: refuse only when the template
    carries a stamp that PROVABLY disagrees with the bytes on disk while every
    stamp on the site copy agrees. A template that is legitimately ahead (a reword,
    a deleted <link>) keeps correct stamps and is unaffected, so the ordinary
    one-sided-PR heal still runs. Absence of a ref is never evidence of staleness —
    only a stamp that contradicts the file it names.
    """
    _, tpl_stale = _stamp_audit(tpl_bytes.decode("utf-8", "replace"), site_dir)
    site_current, site_stale = _stamp_audit(site_bytes.decode("utf-8", "replace"), site_dir)
    return bool(tpl_stale and not site_stale and site_current)


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
    in ``check.unfixed``, and pairs whose site copy --fix REFUSED to clobber
    (see template_is_the_stale_side) in ``check.refused`` — so main() can report
    honestly and exit nonzero rather than reporting a clobber as a heal.
    """
    diverged = []
    check.unfixed = []
    check.refused = []
    site_dir = root / "site"
    for name, tpl, site_copy in find_pairs(root):
        tpl_bytes, site_bytes = tpl.read_bytes(), site_copy.read_bytes()
        expected: bytes | None = tpl_bytes  # what --fix would write
        if name == "theme.js":
            tpl_text = tpl_bytes.decode("utf-8")
            baked = _bake_theme(tpl)
            if baked is not None:
                expected = baked.encode("utf-8")
                ok = site_bytes == expected
            else:
                # stdlib fallback: everything around the baked tokens must match.
                expected = None  # cannot reproduce the bake here — report-only
                site_text = site_bytes.decode("utf-8", errors="replace")
                segs = _token_segments(tpl_text, _THEME_TOKENS)
                overlay = tpl.with_name("terminal_overlay.js")
                if overlay.is_file():
                    segs[-1] = f"{segs[-1].rstrip()}\n\n{overlay.read_text().lstrip()}"
                ok = _matches_around_tokens(site_text, segs)
        else:
            ok = site_bytes == tpl_bytes
        if ok:
            continue
        diverged.append(name)
        stale_template = template_is_the_stale_side(tpl_bytes, site_bytes, site_dir)
        if fix:
            if expected is None:
                check.unfixed.append(name)
                print(f"WARNING: site/{name} diverged but the bake is unavailable — NOT fixed")
            elif stale_template:
                check.refused.append(name)
                print(f"::error title=template-site-sync wrong-direction fix refused::"
                      f"REFUSED: templates/{name} carries a ?v= stamp that disagrees with the "
                      f"file on disk while every stamp in site/{name} is current — templates/ is "
                      f"the stale side here, so copying it over site/ would ship bytes the edge "
                      f"caches `immutable, max-age=1y`. Heal templates/{name} FROM site/{name} "
                      f"instead (see #3676), then re-run.")
            else:
                site_copy.write_bytes(expected)
                print(f"FIXED: site/{name} restored from templates/{name}")
        else:
            hint = (f"templates/{name} is the STALE side (its ?v= stamp disagrees with the file "
                    f"on disk; site/{name}'s stamps are all current) — heal templates/{name} FROM "
                    f"site/{name}; --fix would clobber the correct bytes and is refused"
                    if stale_template else
                    f"site copies are derived — edit templates/{name} and re-copy, "
                    f"or run: python -m scripts.check_template_site_sync --fix")
            print(f"DIVERGED: site/{name} != templates/{name} ({hint})")
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
        # REFUSED: the render-lane shape (2026-07-26 chat.html) — the SITE copy is the
        # fresh one and the template's ?v= stamp contradicts the file on disk, so the
        # templates/ -> site/ copy would ship bytes the edge pins for a year.
        (tmp / "site" / "app.js").write_text("var live = 1;\n")
        live = hashlib.sha256((tmp / "site" / "app.js").read_bytes()).hexdigest()[:8]
        # Bound to names first: a *.html written under mkdtemp is a selftest fixture,
        # never a shipped page, which is exactly the tmp-factory exemption
        # tests/test_site_shim.py documents — its layer-3a regex only reads the
        # literal-on-the-write-line shape, so keep the two apart.
        tpl_page = tmp / "templates" / "wrongway.html"
        site_page = tmp / "site" / "wrongway.html"
        tpl_page.write_text('<script src="app.js?v=deadbeef" defer></script>\n')
        site_page.write_text(
            f'<script src="app.js?v={live}" defer></script>\n<link href="extra.css">\n')

        bad = check(tmp)
        if bad != ["diverged.js", "wrongway.html"]:
            print(f"selftest FAIL: expected ['diverged.js', 'wrongway.html'], got {bad}")
            return 1
        site_before = site_page.read_bytes()
        bad = check(tmp, fix=True)
        if bad != ["diverged.js", "wrongway.html"]:
            print(f"selftest FAIL: --fix changed which pairs are diverged: {bad}")
            return 1
        if (tmp / "site" / "diverged.js").read_text() != "tip = 'calibration-gated';\n":
            print("selftest FAIL: --fix did not restore the site copy to the template")
            return 1
        if getattr(check, "refused", []) != ["wrongway.html"]:
            print(f"selftest FAIL: expected wrongway.html refused, got {check.refused}")
            return 1
        if site_page.read_bytes() != site_before:
            print("selftest FAIL: --fix clobbered a site copy whose stamps were current")
            return 1
        if check(tmp) != ["wrongway.html"]:
            print("selftest FAIL: the refused pair must stay reported as diverged")
            return 1
        print("selftest PASS: divergence detected, --fix restores from templates/, "
              "and refuses the pair whose site copy is the fresher side")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _sparse_refusal(root: Path) -> str | None:
    """The remedy line when this checkout cannot see the trees the law covers.

    ``find_pairs`` enumerates the pair list by walking BOTH templates/ and site/.
    A sparse session worktree (policy R8, .claude/hooks/worktree_create_sparse.py)
    omits site/, so the walk yields nothing and this guard would print
    "template↔site sync OK (0 pairs checked)" and exit 0 — a vacuous pass on the
    exact law that protects the render lanes from a truncated publish. Refuse
    instead, and name the one command that fixes it. Full checkouts (every CI
    lane that runs this guard, and the render lanes, which explicitly clear any
    inherited sparse state) are unaffected: missing_dirs() returns [].
    """
    try:
        from scripts.worktree_sparse import missing_dirs, remedy_line
    except Exception:  # noqa: BLE001 — never let the detector break the guard
        return None
    try:
        absent = [d for d in missing_dirs(root) if d in {"site", "templates"}]
    except Exception:  # noqa: BLE001
        return None
    return remedy_line(absent) if absent else None


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    fix = "--fix" in argv
    root = Path(__file__).resolve().parent.parent
    refusal = _sparse_refusal(root)
    if refusal:
        print(f"template↔site sync REFUSED: {refusal}")
        return 1
    diverged = check(root, fix=fix)
    n_pairs = sum(1 for _ in find_pairs(root))
    if not diverged:
        print(f"template↔site sync OK ({n_pairs} pairs checked)")
        return 0
    if fix:
        unfixed = getattr(check, "unfixed", [])
        refused = getattr(check, "refused", [])
        n_fixed = len(diverged) - len(unfixed) - len(refused)
        print(f"template↔site sync: {n_fixed} site cop{'y' if n_fixed == 1 else 'ies'} "
              f"restored from templates/ ({n_pairs} pairs checked)")
        if refused:
            print(f"template↔site sync: {len(refused)} diverged pair(s) REFUSED — templates/ is "
                  f"the stale side, heal it FROM site/: {refused}")
        if unfixed:
            print(f"template↔site sync: {len(unfixed)} diverged pair(s) NOT fixable here: {unfixed}")
        if refused or unfixed:
            return 1
        return 0
    print(f"template↔site sync FAILED: {len(diverged)} of {n_pairs} pairs diverged")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
