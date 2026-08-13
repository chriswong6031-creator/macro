#!/usr/bin/env python3
"""Static guard: every page carrying the shared dropdown nav must carry the Research mega-menu.

The site navigation is a single shared partial (`_navlinks.html.j2`, included directly
or via `_site_nav.html.j2`). Its Research entry is a grouped, multi-column frosted-glass
panel — the `nav-mega` dropdown. Because the partial is shared, editing it propagates the
mega-menu to every page the routine render pipeline (render.yml) rebuilds.

The failure this guard catches: a page that renders the shared nav (marked by the
`nav-dd-menu` dropdown class) but is MISSING `nav-mega`. That means a FROZEN nav — the
page was produced OUTSIDE the routine render loop and never picked up the mega-menu:

  • an out-of-loop page builder (build_cycle, build_btc_strategy, build_subsector_confluence
    — none were in render.yml, so shared-partial changes never reached them), or
  • a hand-committed static page whose nav was last synced by hand before the mega-menu
    shipped (markets.html froze at #617's "menu-bar parity" pass).

Every one of those was fixed by rebuilding the page THROUGH the shared partial. This guard
turns that whole class of drift into a pre-merge / pre-deploy failure instead of something a
human notices weeks later. It is the mega-menu analogue of check_nav_gap.py and is meant to
run in the same ci.yml / pages.yml gates.

Usage:
    python -m scripts.check_nav_mega [SITE_DIR]   # default: site/
Exit codes: 0 = all clean · 1 = stale nav(s) found.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.sparse_guard import refuse_if_vacuous, trees_for  # noqa: E402

# A page carrying this dropdown class renders the shared _navlinks nav — it is in scope.
# Pages with no site nav at all (the globe landing page, diagnostic pages) lack it and are
# correctly ignored.
_NAV_MARKER = "nav-dd-menu"

# The Research mega-menu marker. Present on every freshly rendered shared nav; absent only
# on a frozen/stale nav that predates the mega-menu.
_MEGA_MARKER = "nav-mega"


def find_pages(site_dir: str = "site"):
    """Return every HTML page under `site_dir` — the set this guard walks.

    Split out from `find_stale` so `main` can tell "no nav is frozen" (the normal
    green) from "no page was read at all" (a tree that isn't there)."""
    pages = []
    for root, _dirs, names in os.walk(site_dir):
        for n in names:
            if n.endswith(".html"):
                pages.append(os.path.join(root, n))
    pages.sort()
    return pages


def find_stale(site_dir: str = "site"):
    """Return [file] for every page that renders the shared dropdown nav but is missing
    the Research mega-menu."""
    stale = []
    for path in find_pages(site_dir):
        html = open(path, encoding="utf-8", errors="replace").read()
        if _NAV_MARKER not in html:      # no shared dropdown nav -> out of scope
            continue
        if _MEGA_MARKER not in html:     # shared nav present but mega-menu missing -> stale
            stale.append(path)
    stale.sort()
    return stale


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site_dir = argv[0] if argv else "site"

    # A sparse session worktree omits site/, so the walk reads zero pages and the
    # OK below certifies the mega-menu on a set that is empty — a vacuous pass.
    # "No frozen nav" is only a green when pages were actually opened.
    pages = find_pages(site_dir)
    refusal = refuse_if_vacuous(len(pages), trees_for(site_dir), "check-nav-mega-vacuous")
    if refusal:
        print(f"check_nav_mega: REFUSED — {refusal}", file=sys.stderr)
        return 1

    stale = find_stale(site_dir)
    if stale:
        print(
            f"check_nav_mega: FAIL — {len(stale)} page(s) render the shared nav but are MISSING "
            f"the Research mega-menu (frozen/stale nav):\n",
            file=sys.stderr,
        )
        for path in stale:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nThese pages are built OUTSIDE the routine render loop (an out-of-loop page builder,"
            "\nor a hand-static page). Rebuild each THROUGH the shared _navlinks partial — e.g. run"
            "\nits builder (build_cycle / build_markets / build_btc_strategy / build_subsector_confluence"
            "\n--china) — so the mega-menu propagates, then re-run this check.",
            file=sys.stderr,
        )
        return 1
    print(f"check_nav_mega: OK — every shared-nav page under {site_dir}/ carries the Research mega-menu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
