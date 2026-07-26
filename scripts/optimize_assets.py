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


def optimize(site_dir: Path) -> int:
    """Version + defer local assets in every page under site_dir. Returns the
    number of files modified. Never raises."""
    site_dir = Path(site_dir)
    if not site_dir.is_dir():
        return 0
    root = site_dir.resolve()
    cache: Dict[Path, Optional[str]] = {}  # resolved asset path -> hash (once per process)
    imports: Dict[Path, list] = {}         # resolved css path -> its @import urls
    n = 0
    for html in site_dir.rglob("*.html"):
        try:
            text = html.read_text()
        except Exception:  # noqa: BLE001
            continue
        page_dir = html.parent

        def _resolve(url: str, _page_dir: Path = page_dir) -> Optional[Path]:
            rel = url.split("?", 1)[0].split("#", 1)[0]
            try:
                target = (_page_dir / rel).resolve()
                target.relative_to(root)  # never reach outside the site tree
            except Exception:  # noqa: BLE001
                return None
            return target

        def hash_for(url: str, _resolve=_resolve) -> Optional[str]:
            target = _resolve(url)
            if target is None:
                return None
            if target not in cache:
                cache[target] = _hash_bytes(target) if target.is_file() else None
            return cache[target]

        def imports_for(url: str, _resolve=_resolve) -> list:
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

        try:
            # ?v= stamping FIRST: preload hints must carry the same final URL as the
            # stylesheet they warm, or the two are separate cache keys and double-fetch.
            new = optimize_assets_text(text, hash_for)
            new = preload_css_text(new, imports_for)
        except Exception as e:  # noqa: BLE001
            log.warning("optimize failed for %s (%s)", html.name, e)
            continue
        if new != text:
            try:
                write_page(html, new)  # keeps the data-base shim; avoids raw write_text
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("write failed for %s (%s)", html.name, e)
    log.info("asset-optimized %d page(s)", n)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config

    return 0 if optimize(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
