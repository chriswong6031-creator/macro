#!/usr/bin/env python3
"""Static guard: templates/chat.html's header must equal the canonical partial.

WHY THIS EXISTS (follow-up to #4228, measured 2026-08-01):

templates/chat.html is a PLAIN-COPY page — scripts/check_template_site_sync.py
requires it to byte-match site/chat.html, so a Jinja ``{% include %}`` cannot run
there and #4228's sweep (113 of 114 product templates → ``_site_nav.html.j2``)
had to skip it. Its header was therefore still the hand-copied block someone
pasted in when the page was built, frozen at that date. By 2026-08-01 it had
drifted badly enough to be a navigation bug, not a cosmetic one:

  * 12 current pages were MISSING from the menu entirely (confluence_screener,
    euro_area, fundamental_forensics, government_revenue, india, japan,
    neural_web, research_vault, sector_cycles_china, south_korea, stage_analysis,
    united_kingdom);
  * 17 REMOVED pages were still advertised (anticipation, btc_strategy,
    committee, congress_trades, crossasset, demand, factors, impulse, ipo,
    macro_signals, measurement, signal_lab, tech_lab, transmission, vector,
    vector_allocation, whitehouse) — dead links in a shipped menu;
  * it linked a bespoke ``chat_nav.css`` instead of ``navigation-refresh.css``,
    the stylesheet CLAUDE.md's Navigation source-of-truth law puts in charge of
    nav appearance, because its markup was the SUPERSEDED mega structure
    (.nav-mega-grid/.nav-mega-col) that the current partial no longer emits.

Hand-copying is what produced all three. So the block is no longer hand-copied:
this script RENDERS ``_site_nav.html.j2`` and splices the result into the page,
and CI runs the same render and refuses a page that disagrees with it. A future
edit to the partial that forgets chat.html now fails a check instead of shipping
a menu that silently lies about which pages exist.

BOUNDARY — the splice is keyed on the structural ``<nav class="site-nav"> …
</nav>`` element, NOT on sentinel comments. A comment marker is deletable, and a
guard whose marker went missing reads as green forever (tests/
test_renamed_sentinel* documents that shape). A missing/duplicated wrapper is a
hard error here, never a skip.

STAMPS — ``scripts/optimize_assets.py`` decorates the shipped bytes after this
runs: ``?v=<8hex>`` on local assets and ``defer`` on scripts. Those are the
optimizer's to own and they change whenever an asset's content changes, so the
comparison normalizes exactly those two decorations and nothing else. Anything
else that differs is real drift and fails.

…AND ``--fix`` CARRIES THEM ACROSS THE SPLICE. A freshly rendered partial is
undecorated, so a naive splice would silently strip every ``?v=`` and ``defer``
inside the header — and ``normalize()`` ignores exactly those two things, so the
gate would read GREEN over the damage. That is not cosmetic here: chat.html is a
plain-copy page with no render lane to re-stamp it, and its nav assets
(navigation-refresh.css, logo_config.js, stock-logos.js, live_config.js,
live.js) sit on the Caddyfile ``immutable, max-age=1y`` list — a dropped stamp
pins every warm browser to the old bytes indefinitely, and four dropped
``defer``s turn a live page's scripts render-blocking. So ``--fix`` harvests the
OUTGOING header's decorations, keyed by asset, and re-applies them to the newly
rendered one in the optimizer's own byte placement. An asset the outgoing page
did not decorate simply gets nothing; the next optimizer run owns it either way.
The comparison stays exactly as narrow as it was — widening ``normalize()`` would
be fixing the wrong half, since the splice is what loses the data.

Usage:
    python -m scripts.sync_chat_nav              # report + exit 1 on drift
    python -m scripts.sync_chat_nav --fix        # re-splice from the partial
    python -m scripts.sync_chat_nav --selftest   # gate fires on synthetic drift
Exit codes: 0 = in sync / fixed / selftest passed · 1 = drift found / selftest
failed / the page's <nav class="site-nav"> boundary could not be located.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CANONICAL = "_site_nav.html.j2"
PAGE = "chat.html"

# The one <nav class="site-nav"> element on the page, non-greedy to its </nav>.
_NAV_RE = re.compile(r'<nav class="site-nav">.*?</nav>', re.DOTALL)

# Exactly what scripts/optimize_assets.py adds, and nothing else:
#   lib.pages.optimize_assets_text -> ?v=<8 hex> on local .js/.css refs
#   lib.pages.optimize_assets_text -> defer on non-async, non-module scripts
_STAMP_RE = re.compile(r"\?v=[0-9a-f]{8}")
_DEFER_RE = re.compile(r"(<script\b[^>]*?)\s+defer(\s*/?>)", re.IGNORECASE)

# Tag/attribute shapes mirrored from lib.pages.optimize_assets_text so that what
# --fix re-applies is byte-identical to what the optimizer would have written.
# Deliberately COPIES rather than imports: the no-fix live check must stay a
# pure jinja2+stdlib run (CI packs install minimal deps, and lib.pages pulls
# lib.config with it), and these four patterns are pinned by
# tests/test_chat_nav_sync.py against the optimizer's real output.
_OPEN_TAG_RE = re.compile(r"<(script|link)\b([^>]*)>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(r'\b(src|href)\s*=\s*"([^"]*)"', re.IGNORECASE)
_HAS_DEFER_ASYNC_RE = re.compile(r"\b(defer|async)\b", re.IGNORECASE)
# The optimizer's own stamp, and only it: `?v=<8 hex>` as the whole query.
_URL_STAMP_RE = re.compile(r"^([^?#]+)\?v=([0-9a-f]{8})$")


def _loaded_asset(kind: str, attrs: str):
    """``(url, attr_match)`` for the asset this tag LOADS, else ``None``.

    Same discrimination as the optimizer: ``src`` on ``<script>``, ``href`` on
    ``<link>``, and nothing for an inline script or a mismatched pair.
    """
    am = _SRC_ATTR_RE.search(attrs)
    if not am:
        return None
    if (kind == "script") != (am.group(1).lower() == "src"):
        return None
    return am.group(2), am


def harvest_decorations(block: str) -> tuple[dict[str, str], set[str]]:
    """``({asset: 8hex stamp}, {scripts wearing defer})`` as worn by `block`.

    Assets are keyed BOTH by their URL as written and by bare filename, so a
    header whose ``nav_prefix`` changed still carries its stamps across. A
    filename that appeared with two DIFFERENT hashes is ambiguous — re-applying
    either would pin the edge to the wrong bytes for a year — so it is dropped
    and that ref ships unstamped for the optimizer to fix.
    """
    seen: dict[str, set[str]] = {}
    defers: set[str] = set()
    for m in _OPEN_TAG_RE.finditer(block):
        kind, attrs = m.group(1).lower(), m.group(2)
        ref = _loaded_asset(kind, attrs)
        if ref is None:
            continue
        url = ref[0]
        stamped = _URL_STAMP_RE.match(url)
        bare = stamped.group(1) if stamped else url
        keys = {bare, PurePosixPath(bare).name}
        if stamped:
            for key in keys:
                seen.setdefault(key, set()).add(stamped.group(2))
        if kind == "script" and _HAS_DEFER_ASYNC_RE.search(attrs):
            defers |= keys
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}, defers


def redecorate(fresh: str, outgoing: str) -> str:
    """`fresh` wearing the ``?v=``/``defer`` decorations `outgoing` wore.

    Adds ONLY the two things ``normalize()`` ignores, so the result still
    compares equal to the undecorated render — this restores data the splice
    would drop, it can never mask drift.
    """
    stamps, defers = harvest_decorations(outgoing)

    def _redecorate(m: "re.Match[str]") -> str:
        kind, attrs = m.group(1).lower(), m.group(2)
        ref = _loaded_asset(kind, attrs)
        if ref is None:
            return m.group(0)
        url, am = ref
        if "?" in url or "#" in url:
            return m.group(0)  # already stamped, or an authored query — leave it
        name = PurePosixPath(url).name
        new_attrs = attrs
        stamp = stamps.get(url) or stamps.get(name)
        if stamp:
            new_attrs = (
                attrs[: am.start()]
                + f'{am.group(1)}="{url}?v={stamp}"'
                + attrs[am.end():]
            )
        if (kind == "script" and (url in defers or name in defers)
                and not _HAS_DEFER_ASYNC_RE.search(new_attrs)):
            new_attrs = new_attrs.rstrip() + " defer"
        return f"<{m.group(1)}{new_attrs}>"

    return _OPEN_TAG_RE.sub(_redecorate, fresh)


def render_canonical(templates: Path) -> str:
    """The canonical header, rendered exactly as the site builders render it.

    Matches scripts/build_site.py: ``autoescape=True`` (which is why the search
    placeholder ships ``&amp;``), and a bilingual ``t()`` that emits the same
    ``.l-en``/``.l-zh`` span pair ``_navlinks.html.j2``'s own macro does — the
    partial's wrapper reads ``t`` from the page context, so supplying the
    English-only stub used by unit tests here would ship a page with no Chinese.
    """
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup, escape

    def t(en: str, zh: str = "") -> Markup:
        return Markup(
            f'<span class="l-en">{escape(en)}</span>'
            f'<span class="l-zh">{escape(zh or en)}</span>'
        )

    env = Environment(loader=FileSystemLoader(str(templates)), autoescape=True)
    return env.get_template(CANONICAL).render(t=t).strip()


def normalize(block: str) -> str:
    """`block` with the optimizer's stamps/defer removed, for comparison only."""
    block = _STAMP_RE.sub("", block)
    block = _DEFER_RE.sub(r"\1\2", block)
    return block.strip()


def extract_nav(text: str, label: str) -> str:
    """The page's single header element, or SystemExit with a real diagnosis."""
    found = _NAV_RE.findall(text)
    if len(found) != 1:
        print(
            f"::error title=chat-nav-sync boundary lost::{label} has {len(found)} "
            f'<nav class="site-nav">…</nav> elements, expected exactly 1. This '
            f"guard splices on that element; it cannot run against a page whose "
            f"header wrapper was renamed, removed or duplicated. Restore the "
            f"wrapper (or update {Path(__file__).name} deliberately) — do not "
            f"leave this unresolved, it is the page's whole navigation."
        )
        raise SystemExit(1)
    return found[0]


def check(root: Path, fix: bool = False) -> bool:
    """True when the page's header matches the partial (after fixing, if asked)."""
    templates, site = root / "templates", root / "site"
    tpl_path, site_path = templates / PAGE, site / PAGE
    canonical = render_canonical(templates)
    page_text = tpl_path.read_text(encoding="utf-8")
    current = extract_nav(page_text, f"templates/{PAGE}")

    if normalize(current) == normalize(canonical):
        print(f"chat nav sync OK (templates/{PAGE} header == {CANONICAL})")
        return True

    if not fix:
        print(
            f"::error title=chat-nav-sync drift::templates/{PAGE}'s header no "
            f"longer matches {CANONICAL}. The header is GENERATED — do not hand-"
            f"edit it; edit {CANONICAL} / _navlinks.html.j2 and re-run: "
            f"python -m scripts.sync_chat_nav --fix"
        )
        return False

    # Splice, preserving everything outside the wrapper byte-for-byte — and the
    # optimizer's decorations INSIDE it, which the fresh render does not carry
    # and normalize() would not have missed. See the STAMPS note in the module
    # docstring: these assets are served `immutable, max-age=1y` and this page
    # has no render lane to re-stamp them.
    updated = page_text.replace(current, redecorate(canonical, current), 1)

    # These writes are raw write_text, not lib.pages.write_page, and are listed in
    # tests/test_site_shim._ALLOW for it. That is deliberate and it is the same
    # call scripts/optimize_assets.py makes on this exact pair: write_page INJECTS
    # the data-base shim, which would (a) write generated markup into a SOURCE file
    # and (b) make templates/chat.html differ from site/chat.html, breaking the
    # byte-match law that makes this a plain-copy page at all.
    #
    # An allowlist entry is a hole unless something still checks the thing it
    # excuses, so check it here: the splice replaces only the <nav> element, so the
    # shim (which lives in <head>) must survive untouched. If it ever does not,
    # this refuses to write rather than shipping a page whose per-ticker fetches
    # silently miss the R2 reroute.
    from lib.pages import DBASE_MARKER

    if page_text.count(DBASE_MARKER) != updated.count(DBASE_MARKER):
        print(
            f"::error title=chat-nav-sync shim lost::splicing the header changed the "
            f"number of {DBASE_MARKER!r} shim tags in {PAGE} "
            f"({page_text.count(DBASE_MARKER)} -> {updated.count(DBASE_MARKER)}). "
            f"Refusing to write. The header splice must not touch <head>."
        )
        raise SystemExit(1)

    tpl_path.write_text(updated, encoding="utf-8")
    print(f"FIXED: templates/{PAGE} header re-rendered from {CANONICAL}")
    # Mirror to the site copy so the pair stays byte-identical (the sync law).
    # check_template_site_sync --fix would also do it; doing it here keeps this
    # script a fixed point on its own.
    if site_path.is_file():
        site_path.write_text(updated, encoding="utf-8")
        print(f"FIXED: site/{PAGE} mirrored from templates/{PAGE}")
    return True


def selftest() -> int:
    """Guard the guard: a hand-edited header must go red, and --fix must heal it."""
    import shutil
    import tempfile

    root = Path(__file__).resolve().parent.parent
    tmp = Path(tempfile.mkdtemp(prefix="sync_chat_nav_selftest_"))
    try:
        shutil.copytree(root / "templates", tmp / "templates")
        (tmp / "site").mkdir()
        shutil.copy2(root / "site" / PAGE, tmp / "site" / PAGE)

        if not check(tmp, fix=True):
            print("selftest FAIL: --fix could not bring the fixture into sync")
            return 1
        if not check(tmp):
            print("selftest FAIL: a freshly fixed page still reports drift "
                  "(the check is not a fixed point)")
            return 1

        # The exact 2026-08-01 shape: a link the partial does not carry.
        page = tmp / "templates" / PAGE
        text = page.read_text(encoding="utf-8")
        before_stamps, before_defers = harvest_decorations(extract_nav(text, "fixture"))
        page.write_text(
            text.replace('<div class="nav-links">',
                         '<div class="nav-links">\n    <a href="whitehouse.html">X</a>', 1),
            encoding="utf-8",
        )
        if check(tmp):
            print("selftest FAIL: a hand-added menu link did NOT trip the gate")
            return 1

        # Stamps/defer are the optimizer's, not drift — normalizing them must not
        # blind the gate to the line above, which is why this is asserted after it.
        if not check(tmp, fix=True):
            print("selftest FAIL: --fix could not heal the drifted page")
            return 1
        healed = page.read_text(encoding="utf-8")
        if "whitehouse.html" in extract_nav(healed, "fixture"):
            print("selftest FAIL: --fix left the hand-added link in the header")
            return 1
        if (tmp / "site" / PAGE).read_text(encoding="utf-8") != healed:
            print("selftest FAIL: --fix did not mirror the site copy")
            return 1

        # The splice must not eat what normalize() is blind to. A fresh render
        # is undecorated, so a --fix that does not carry the outgoing stamps and
        # defers across strips them AND reports green — leaving warm browsers
        # pinned to `immutable, max-age=1y` copies of the old assets on a page
        # with no render lane to re-stamp it.
        after_stamps, after_defers = harvest_decorations(extract_nav(healed, "fixture"))
        lost_stamps = sorted(k for k, v in before_stamps.items() if after_stamps.get(k) != v)
        lost_defers = sorted(before_defers - after_defers)
        if lost_stamps or lost_defers:
            print(f"selftest FAIL: --fix stripped optimizer decorations the "
                  f"outgoing header carried — lost ?v= on {lost_stamps}, lost "
                  f"defer on {lost_defers}. normalize() ignores both, so the "
                  f"gate would report green over the damage.")
            return 1

        stamped = healed.replace("navigation-refresh.css", "navigation-refresh.css?v=deadbeef", 1)
        page.write_text(stamped, encoding="utf-8")
        if not check(tmp):
            print("selftest FAIL: an optimizer ?v= stamp was reported as drift")
            return 1

        print("selftest PASS: drift detected, --fix heals both copies and keeps "
              "the optimizer's stamps/defers, and those stamps are not mistaken "
              "for drift")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    root = Path(__file__).resolve().parent.parent
    return 0 if check(root, fix="--fix" in argv) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
