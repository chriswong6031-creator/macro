"""Post-render asset optimization: content-hash cache-busting + defer + CSS preload.

Rewrites every local ``.js``/``.css`` reference across ``site/**/*.html`` to
carry a ``?v=<content-hash>`` query and marks non-critical ``<script>`` tags
``defer``. Paired with the edge cache rule in ``app/deploy/Caddyfile`` (versioned
requests → ``Cache-Control: immutable, max-age=1y``), this stops the shared
bundle (theme.js, heatmap.js, theme.css, …) from being re-validated on every
page navigation — the dominant mobile cost when browsing macro → country pages —
while ``defer`` keeps synchronous script execution off the first-paint path.

It then adds ``<link rel=preload as=style>`` to ``<head>`` for the stylesheets the
parser would otherwise discover LATE — the ones externalize_css left in the body
(macro.html's biggest sit ~48KB into a 582KB document) and the one theme.css
reaches by ``@import``, which is strictly serialized behind theme.css's own
download. Every stylesheet here is render-blocking, so late discovery delays first
paint by whole round-trips; the hints move only discovery, never the ``<link>``
itself, so the cascade is untouched. See lib.pages.preload_css_text.

Runs after all builders have copied their assets into site/ (so the files exist
to hash), mirroring scripts/inject_data_base.py. Idempotent + never raises: a
ref that already carries a query is left as-is, so re-runs are no-ops. The core
rewrites live in lib.pages.optimize_assets_text / preload_css_text (kept beside
the shim logic). Stamping must precede the preload pass — a hint whose URL differs
from the stylesheet's by a query string is a second cache key, not a warm hit.

It also stamps the ``templates/`` side of every plain-copy HTML pair (index.html,
chat.html — see paired_html_templates). Those site copies are written by NOTHING
but ``check_template_site_sync --fix``, which the lanes run AFTER this step and
which rewrites site/<name> from templates/<name> — so a stamp written only
site-side is reverted before it ever reaches main. Stamping both sides keeps the
pair byte-identical (the sync law) with a FRESH stamp, and makes this script a
true fixed point: a second run over a healed tree modifies nothing.

Because a lane pushes its POST-rebase tree, the lanes run this step again inside
the push loop: a page un-stamped by a sibling lane that merged mid-render arrives
only at `git pull --rebase`, long after the pre-commit pass (2026-07-26: render
6260e5ac8c0 shipped site/us_track_record.html un-stamped for exactly this reason —
standout-audit-us landed it 14 min after that render's checkout).

Run standalone: python -m scripts.optimize_assets
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import css_imports, optimize_assets_text, preload_css_text, write_page  # noqa: E402

log = logging.getLogger("optimize_assets")


def _hash_bytes(p: Path) -> Optional[str]:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:8]
    except Exception:  # noqa: BLE001
        return None


def paired_html_pages(site_dir: Path):
    """Yield ``(template, site_copy)`` for every plain-copy HTML pair.

    A pair is a ``templates/<name>.html`` that also ships as ``site/<name>.html``
    (``index.html``, ``chat.html``; the ``.html.j2`` render inputs are excluded).
    Their site copy is built by NO builder, so ``check_template_site_sync --fix``
    re-copying it from ``templates/`` is the only thing that writes it.

    The pair definition is imported from the guard that enforces it so the two
    cannot drift, with a local glob fallback — mirroring
    ``scripts.inject_data_base._inject_paired_templates`` (#3625), which sweeps the
    same two pages for the data-base shim and hit the same freeze.
    """
    root = site_dir.parent
    try:
        from scripts.check_template_site_sync import find_pairs
        pairs = [(t, s) for _name, t, s in find_pairs(root)]
    except Exception:  # noqa: BLE001 — mirror the guard's rule: direct children, no .j2
        tdir = root / "templates"
        pairs = [(p, site_dir / p.name) for p in sorted(tdir.glob("*.html"))
                 if p.is_file() and (site_dir / p.name).is_file()] if tdir.is_dir() else []
    for tpl, site_copy in pairs:
        if tpl.suffix.lower() == ".html":   # .js/.css pairs carry no asset refs to stamp
            yield tpl, site_copy


def make_optimizer(site_root: Path):
    """The two rewrite passes (?v= stamping, then CSS preload hints) closed over
    one shared hash/@import cache: returns ``optimized(text, page_dir) -> str``,
    refs resolved from ``page_dir`` and never reaching outside ``site_root``.

    Factored out of ``optimize()`` so a builder whose lane runs NO site-wide
    sweep can emit already-stamped pages: the hourly whitehouse sentinel commits
    site/whitehouse.html straight to main, and an unstamped render there
    regressed the page to bare refs on every alert update
    (scripts.build_whitehouse._render_page is the consumer)."""
    root = Path(site_root).resolve()
    cache: Dict[Path, Optional[str]] = {}  # resolved asset path -> hash (once per process)
    imports: Dict[Path, list] = {}         # resolved css path -> its @import urls

    def optimized(text: str, page_dir: Path) -> str:
        """`text` with assets stamped + preloaded, resolving refs from page_dir."""
        def _resolve(url: str) -> Optional[Path]:
            rel = url.split("?", 1)[0].split("#", 1)[0]
            try:
                target = (page_dir / rel).resolve()
                target.relative_to(root)  # never reach outside the site tree
            except Exception:  # noqa: BLE001
                return None
            return target

        def hash_for(url: str) -> Optional[str]:
            target = _resolve(url)
            if target is None:
                return None
            if target not in cache:
                cache[target] = _hash_bytes(target) if target.is_file() else None
            return cache[target]

        def imports_for(url: str) -> list:
            """@import urls inside a linked stylesheet — read once per file."""
            target = _resolve(url)
            if target is None:
                return []
            if target not in imports:
                try:
                    imports[target] = css_imports(target.read_text(encoding="utf-8")) if target.is_file() else []
                except Exception:  # noqa: BLE001
                    imports[target] = []
            return imports[target]

        # ?v= stamping FIRST: preload hints must carry the same final URL as the
        # stylesheet they warm, or the two are separate cache keys and double-fetch.
        return preload_css_text(optimize_assets_text(text, hash_for), imports_for)

    return optimized


def optimize(site_dir: Path) -> int:
    """Version + defer local assets in every page under site_dir, plus the
    templates/ side of every plain-copy HTML pair. Returns the number of files
    modified. Never raises."""
    site_dir = Path(site_dir)
    if not site_dir.is_dir():
        return 0
    root = site_dir.resolve()
    optimized = make_optimizer(root)

    n = 0
    # Plain-copy HTML pairs FIRST — this ordering is load-bearing, not cosmetic.
    #
    # Stamp the TEMPLATE, not just the site copy: the lanes run
    # `check_template_site_sync --fix` after this step (they must, so a cancellation can
    # never ship a diverged pair — see render.yml), and --fix rewrites site/<name> FROM
    # templates/<name>, reverting a stamp written only site-side. That made the stamp
    # structurally unreachable for these pages: #3617's onboard.css fix was live at the
    # origin while every returning browser kept the pre-#3617 stylesheet, because
    # site/index.html still linked onboard.css?v=cfdca9e2 and the edge serves versioned
    # assets `immutable, max-age=1y` (#3624 hand-bumped that one page).
    #
    # WHY BEFORE the site walk: a render is cancelled far more often than it completes on
    # a merge-spree day, and the commit step is `if: always()` — so this process can be
    # SIGTERMed part-way through and the half-done tree still gets committed. With the
    # site walk first, a kill during it left site/chat.html re-stamped (it sorts early)
    # while templates/chat.html was never reached, and since --fix resolves toward
    # templates/ it could not repair the pair either — main landed DIVERGED and the
    # pages.yml publish gate went red (2026-07-26, cancelled run 30203476381 -> commit
    # 886fe25d89e). Doing the pair first makes every interruption point safe: --fix always
    # resolves toward templates/, so if we got here at all the template is already fresh
    # and --fix carries that freshness into site/. Refs resolve against site/ because that
    # is where the page ships from, and the write is a plain write_text — write_page would
    # inline the data-base shim into a SOURCE file.
    for tpl, site_copy in paired_html_pages(site_dir):
        try:
            text = tpl.read_text()
        except Exception:  # noqa: BLE001
            continue
        try:
            new = optimized(text, root)   # refs resolve from site/, where the page ships
        except Exception as e:  # noqa: BLE001
            log.warning("optimize failed for templates/%s (%s)", tpl.name, e)
            continue
        if new == text:
            continue
        try:
            tpl.write_text(new)
            n += 1
            log.info("re-stamped templates/%s (plain-copy pair)", tpl.name)
            # keep the pair byte-identical in the same pass, so the sync guard is green
            # whether or not --fix runs afterwards (mirrors #3625's shim sweep)
            if site_copy.is_file() and site_copy.read_text() != new:
                site_copy.write_text(new)
        except Exception as e:  # noqa: BLE001
            log.warning("write failed for templates/%s (%s)", tpl.name, e)

    for html in site_dir.rglob("*.html"):
        try:
            text = html.read_text()
        except Exception:  # noqa: BLE001
            continue
        try:
            new = optimized(text, html.parent)
        except Exception as e:  # noqa: BLE001
            log.warning("optimize failed for %s (%s)", html.name, e)
            continue
        if new != text:
            try:
                write_page(html, new)  # keeps the data-base shim; avoids raw write_text
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("write failed for %s (%s)", html.name, e)
    log.info("asset-optimized %d file(s)", n)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config

    return 0 if optimize(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
