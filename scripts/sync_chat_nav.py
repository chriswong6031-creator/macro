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
from pathlib import Path

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

    # Splice, preserving everything outside the wrapper byte-for-byte.
    updated = page_text.replace(current, canonical, 1)
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

        stamped = healed.replace("navigation-refresh.css", "navigation-refresh.css?v=deadbeef", 1)
        page.write_text(stamped, encoding="utf-8")
        if not check(tmp):
            print("selftest FAIL: an optimizer ?v= stamp was reported as drift")
            return 1

        print("selftest PASS: drift detected, --fix heals both copies, and the "
              "optimizer's stamps are not mistaken for drift")
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
