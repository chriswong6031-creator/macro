"""Inject the data-base fetch shim (templates/data_base.js) into every page's <head>.

The shim (templates/data_base.js) reroutes the heavy per-ticker OHLC + search-library
fetches to R2 when window.DATA_BASE is set; empty -> no-op. It must load FIRST, before
any page runs a data fetch, so — unlike the wh_banner (deferred, before </body>) — it
goes at the TOP of <head>, non-deferred (after an early <meta charset>, which must
stay inside the browser's 1024-byte pre-scan window and can never run a fetch —
see lib.pages). Depth-aware (prefix so sub-dir pages resolve
data_base.js) + idempotent (the data-dbase marker skips already-injected / re-run
pages). Also guarantees site/data_base.js exists (copied from the template) so the tag
never 404s. Modeled on scripts/inject_wh_banner.py; never raises.

Builders inject at write time via lib.pages.write_page (canonical home of the shim
logic) — this post-render sweep is the idempotent safety net for anything else.

Run standalone: python -m scripts.inject_data_base
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import DBASE_MARKER as _MARKER, inject_text  # noqa: E402,F401 — re-exported

log = logging.getLogger("inject_data_base")


def inject(site_dir: Path) -> int:
    """Insert the shim into every html under site_dir. Returns files modified. Never raises."""
    site_dir = Path(site_dir)
    if not site_dir.is_dir():
        return 0
    # ensure the shim file is present so the injected tag never 404s
    src = site_dir.parent / "templates" / "data_base.js"
    try:
        if src.exists():
            shutil.copyfile(src, site_dir / "data_base.js")
    except Exception as e:  # noqa: BLE001
        log.warning("copy data_base.js -> site failed: %s", e)
    n = 0
    for html in site_dir.rglob("*.html"):
        try:
            text = html.read_text()
        except Exception:  # noqa: BLE001
            continue
        # No `if _MARKER in text: continue` here: a page can carry the marker and
        # still hold the OLD external <script src="data_base.js"> tag, which
        # inject_text upgrades to the inline shim in place. Short-circuiting on the
        # marker would freeze every already-rendered page on the external ref
        # forever. inject_text is idempotent, and the `new != text` guard below
        # still keeps an already-inline page from being rewritten.
        try:
            depth = len(html.relative_to(site_dir).parts) - 1
        except ValueError:
            depth = 0
        new = inject_text(text, "../" * depth)
        if new != text:
            try:
                html.write_text(new)
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("inject failed for %s (%s)", html.name, e)
    n += _inject_paired_templates(site_dir)
    log.info("data_base shim injected into %d page(s)", n)
    return n


def _inject_paired_templates(site_dir: Path) -> int:
    """Sweep the templates/ side of every plain-copy PAIR (templates/<name>.html that
    also ships as site/<name>.html). Returns files modified. Never raises.

    Without this the two paired pages can NEVER be healed. The render lanes run
    `check_template_site_sync --fix` after the sweeps and before `git add site/`, and
    that fix copies templates/ -> site/ (the site copy is the derived one). So the
    sweep would upgrade site/index.html, the sync would immediately overwrite it from
    the un-swept templates/index.html, and the staged result is the ORIGINAL tag —
    silently, every render, forever. index.html is the landing page, so that stranded
    the single most-hit page in the site on the blocking external ref while all 3195
    unpaired pages moved to the inline shim (observed 2026-07-26, post #3558).

    Pair definition is imported from the guard that enforces it, so the two can't
    drift; falls back to a local glob when the guard isn't importable.
    """
    root = site_dir.parent
    try:
        from scripts.check_template_site_sync import find_pairs
        pairs = [(t, s) for _name, t, s in find_pairs(root)]
    except Exception:  # noqa: BLE001 — mirror the guard's own rule: direct children, no .j2
        tdir = root / "templates"
        pairs = [(p, site_dir / p.name) for p in sorted(tdir.glob("*.html"))
                 if p.is_file() and (site_dir / p.name).is_file()] if tdir.is_dir() else []
    n = 0
    for tpl, site_copy in pairs:
        if tpl.suffix.lower() != ".html":
            continue                      # .js/.css pairs carry no shim tag
        try:
            text = tpl.read_text()
        except Exception:  # noqa: BLE001
            continue
        # depth "" — a paired template always ships at the site ROOT (site/<name>.html)
        new = inject_text(text, "")
        if new == text:
            continue
        try:
            tpl.write_text(new)
            n += 1
            # keep the pair byte-identical in the same pass, so the sync guard is
            # green whether or not --fix runs afterwards
            if site_copy.is_file() and site_copy.read_text() != new:
                site_copy.write_text(new)
        except Exception as e:  # noqa: BLE001
            log.warning("inject failed for template %s (%s)", tpl.name, e)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config
    return 0 if inject(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
