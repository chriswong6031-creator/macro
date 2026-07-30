"""Fail the build when a shipped page links a file that isn't in the tree.

A page that links `assets/css/<hash>.css` or `../basket/<id>.html` and ships
without that file is a silent 404: the browser drops the stylesheet (half the
page loses its styling) or the reader clicks a dead link. Nothing else in CI
notices — the HTML is well-formed, the render succeeds, and the break only
surfaces in production.

This has now bitten three times, twice in the same month:

  * `site/us_stocks.html` -> `assets/css/21f5c251.css` (#3988) — pruned while a
    sibling page still linked it; fixed by restoring the asset.
  * the start-page intelligence panel stylesheet (#4042) — same shape.
  * `site/stocks/*.html` -> `../baskets/<id>.html` (605 pages, 909 links) —
    `templates/ticker.html.j2` emitted a PLURAL directory for pages that ship
    under the SINGULAR `site/basket/`. Every themes-and-baskets link on every
    US ticker page 404'd, and had since the directory was named.

The first two are the prune race that `scripts/externalize_css.py` now guards
against directly (see `_committed_refs_for_absent_pages` there). The third is a
plain typo no amount of prune-hardening would have caught — which is the point
of checking the shipped bytes instead of the process that produced them.

What counts as a reference: `href=`/`src=` values that look like real paths.
Values carrying `${`, `{{`, `<`, `}` or whitespace are template/JS fragments
rather than URLs (a `<script>` building `${SB}${sym}`, or an i18n macro that
split an `<a href="` across two language spans) and are skipped — this checker
proves file existence, not markup validity.

Run standalone:  python3 scripts/check_site_asset_refs.py [site_dir]
Selftest:        python3 scripts/check_site_asset_refs.py --selftest
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

# href="..." / src="..." — single or double quoted. The lookbehind rejects
# `data-src=` / `data-href=`: a plain \b matches at the `-`, and the alerts feed
# tags every card `data-src="macro"`, which would read as a link to a file named
# `macro` and fail this checker on markup that is doing nothing wrong.
_ATTR_RE = re.compile(r"""(?<![\w-])(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)

# Schemes and anchors that never resolve to a file in this tree.
_SKIP_PREFIX = (
    "http://", "https://", "//", "data:", "mailto:", "tel:",
    "javascript:", "#", "?",
)

# Characters that mark a value as a template/JS fragment, not a URL.
_NOT_A_URL = ("${", "{{", "{%", "<", ">", "}", " ", "\t", "\n")

# Path prefixes Caddy hands to the FastAPI app instead of the file tree
# (app/deploy/Caddyfile: `reverse_proxy /api/* 127.0.0.1:8000`, `/ws/tape`).
# A link to /api/status is a live endpoint, not a missing file.
_RUNTIME_PREFIXES = ("api/", "ws/")

# ── Two classes of breakage, two severities ──────────────────────────────────
# HARD (fails): a link whose target is decided by a TEMPLATE — a directory name,
# an asset hash, a page path. These are deterministic: the emitter is wrong, it
# is wrong for every render, and it stays wrong until someone edits it. All
# three incidents above are this class.
#
# SOFT (warns): a link to `stocks/<TICKER>.html`. Which ticker pages exist is
# decided nightly by data — the peer graph, the movers table and the crypto
# board can all name a symbol the page universe does not render that day
# (delisted, renamed, or below the coverage cut). Hard-gating that would wedge
# the nightly render on ordinary universe churn, so it is counted and reported
# instead. The fix is builder-side: filter these link sources to the universe
# that actually ships.
_TICKER_PAGE_RE = re.compile(r"^stocks/[A-Za-z0-9.\-]+\.html$")

# HARD gaps pinned as pre-existing, kept as an EMPTY escape hatch: the set is
# closed, so anything dangling fails immediately. The six pins this guard landed
# with were each a live 404 and each got its own emitter fix (#4056 -> follow-up):
#
#   * `heatmap.html`, `sectors.html` — the HK dashboard's footer strip was ported
#     from China's in #2650 without market-prefixing the paths. Neither page has
#     ever existed in repo history. `heatmap.html` -> `hk_heatmap.html`; the
#     Sector Desk link went away, because HK's sector pages (`sectors/hk-*.html`)
#     are indexed by `hk_stocks.html`, already the first link in that same strip.
#   * `basket/ai_capex.html` — a category error, not a retired basket: `ai_capex`
#     is a COMPLEX id (an aggregate over engine.demand_capex.AI_CAPEX_THEMES),
#     never a basket id, so no page is built for it by design. The complex row on
#     baskets.html + us_stocks.html is now a static readout instead of a link.
#   * the three `research/SIGNAL_LAB_FRONTIER_WAVE*_FABLE_ADJUDICATION_*.md`
#     links on signal_lab.html — publishing them under site/research/ would have
#     put internal screening documents on the PUBLIC side of the Caddy boundary
#     while signal_lab.html itself is `@never_site`, so the wave labels are plain
#     text carrying the repo path as provenance.
#
# Shrink this list; never extend it without the matching emitter fix.
_KNOWN_GAPS: frozenset[str] = frozenset()


def _iter_refs(text: str):
    """Yield each href/src value in `text` that looks like a real path."""
    for m in _ATTR_RE.finditer(text):
        raw = m.group(1).strip()
        if not raw or raw.startswith(_SKIP_PREFIX):
            continue
        if any(tok in raw for tok in _NOT_A_URL):
            continue
        ref = raw.split("?", 1)[0].split("#", 1)[0]  # drop ?v= stamp + fragment
        if ref:
            yield unquote(ref)


def find_dangling(site_dir: Path) -> dict[str, list[str]]:
    """Map each missing target (site-relative) -> sorted pages that link it."""
    site_dir = Path(site_dir).resolve()
    dangling: dict[str, set[str]] = defaultdict(set)
    for html in sorted(site_dir.rglob("*.html")):
        try:
            text = html.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        page = html.relative_to(site_dir).as_posix()
        for ref in _iter_refs(text):
            target = site_dir / ref.lstrip("/") if ref.startswith("/") else html.parent / ref
            try:
                if target.exists():
                    continue
                rel = target.resolve().relative_to(site_dir).as_posix()
            except (OSError, ValueError):
                continue  # escapes site/ — not ours to police
            if rel.startswith(_RUNTIME_PREFIXES):
                continue  # served by the app, not the file tree
            if rel not in _KNOWN_GAPS:
                dangling[rel].add(page)
    return {k: sorted(v) for k, v in sorted(dangling.items())}


def _selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        site = Path(td)
        (site / "assets" / "css").mkdir(parents=True)
        (site / "basket").mkdir()
        (site / "stocks").mkdir()
        (site / "assets" / "css" / "abc123.css").write_text("a{}", encoding="utf-8")
        # Each fixture page is bound to a name BEFORE its write. That is not style:
        # tests/test_site_shim.py line-scans for a page-suffixed literal written
        # directly (site pages must go through lib.pages.write_page), and its AST
        # layer exempts a throwaway-tempdir target only when it can see the binding
        # — the shape scripts/check_ruling_conflicts.py uses for its own fixtures.
        # Keep that forbidden form out of these comments too: the scanner reads raw
        # lines, so quoting it here would flag this file as an offender.
        member = site / "basket" / "ai_infra.html"
        member.write_text("<html></html>", encoding="utf-8")
        # good refs + one dead stylesheet + one plural-directory typo
        ok_page = site / "stocks" / "OK.html"
        ok_page.write_text(
            '<link href="../assets/css/abc123.css?v=abc123">'
            '<a href="../basket/ai_infra.html">x</a>'
            '<a href="https://example.com/x.html">ext</a>'
            '<a href="${SB}${sym}">js</a>'
            '<div data-src="macro" data-href="themes"></div>',
            encoding="utf-8",
        )
        bad_page = site / "stocks" / "BAD.html"
        bad_page.write_text(
            '<link href="../assets/css/deadbe.css?v=deadbe">'
            '<a href="../baskets/ai_infra.html">typo</a>',
            encoding="utf-8",
        )
        got = find_dangling(site)
        want = {"assets/css/deadbe.css": ["stocks/BAD.html"],
                "baskets/ai_infra.html": ["stocks/BAD.html"]}
        if got != want:
            print(f"check_site_asset_refs: SELFTEST FAIL\n  got  {got}\n  want {want}", file=sys.stderr)
            return 1
        print("check_site_asset_refs: selftest OK")
        return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "--selftest":
        return _selftest()

    site_dir = Path(argv[0]) if argv else Path("site")
    if not site_dir.is_dir():
        print(f"check_site_asset_refs: ERROR — {site_dir} is not a directory.", file=sys.stderr)
        return 2

    dangling = find_dangling(site_dir)
    hard = {t: p for t, p in dangling.items() if not _TICKER_PAGE_RE.match(t)}
    soft = {t: p for t, p in dangling.items() if _TICKER_PAGE_RE.match(t)}

    def _dump(items: dict[str, list[str]]) -> None:
        for target, pages in items.items():
            shown = ", ".join(pages[:4]) + (f", +{len(pages) - 4} more" if len(pages) > 4 else "")
            print(f"  {target}\n      linked by: {shown}", file=sys.stderr)

    if soft:
        links = sum(len(v) for v in soft.values())
        print(f"\ncheck_site_asset_refs: {len(soft)} ticker page(s) linked but not "
              f"rendered, across {links} page(s):", file=sys.stderr)
        _dump(soft)
        print("  (not fatal — the ticker universe is decided nightly by data; "
              "fix = filter peer/movers/crypto links to the rendered universe)",
              file=sys.stderr)
        # GitHub annotation: bare print, line-start, flushed (see CLAUDE.md).
        print(f"::warning title=unrendered-ticker-links::{len(soft)} ticker page(s) "
              f"linked but never rendered — see job log", flush=True)

    if hard:
        links = sum(len(v) for v in hard.values())
        print(f"\ncheck_site_asset_refs: FAIL — {len(hard)} missing target(s) "
              f"linked by {links} page(s):\n", file=sys.stderr)
        _dump(hard)
        print("\nEach line is a live 404 on a shipping page. Fix the EMITTER "
              "(templates/*.j2 or the builder), then re-render or patch site/ so "
              "the committed bytes match. A missing assets/css/<hash>.css means a "
              "stylesheet was pruned while a page still linked it.", file=sys.stderr)
        print(f"::error title=dead-site-refs::{len(hard)} missing link target(s) "
              f"across {links} page(s) — see job log", flush=True)
        return 1

    print(f"check_site_asset_refs: OK — every template-decided href/src under "
          f"{site_dir} resolves ({len(_KNOWN_GAPS)} pre-existing gap(s) pinned, "
          f"{len(soft)} unrendered ticker link(s) reported).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
