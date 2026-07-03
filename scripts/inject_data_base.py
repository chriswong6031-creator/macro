"""Inject the data-base fetch shim (templates/data_base.js) into every page's <head>.

The shim (templates/data_base.js) reroutes the heavy per-ticker OHLC + search-library
fetches to R2 when window.DATA_BASE is set; empty -> no-op. It must load FIRST, before
any page runs a data fetch, so — unlike the wh_banner (deferred, before </body>) — it
goes at the TOP of <head>, non-deferred. Depth-aware (prefix so sub-dir pages resolve
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
        if _MARKER in text:
            continue
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
    log.info("data_base shim injected into %d page(s)", n)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config
    return 0 if inject(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
