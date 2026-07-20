"""Post-render asset optimization: content-hash cache-busting + defer.

Rewrites every local ``.js``/``.css`` reference across ``site/**/*.html`` to
carry a ``?v=<content-hash>`` query and marks non-critical ``<script>`` tags
``defer``. Paired with the edge cache rule in ``app/deploy/Caddyfile`` (versioned
requests → ``Cache-Control: immutable, max-age=1y``), this stops the shared
bundle (theme.js, heatmap.js, theme.css, …) from being re-validated on every
page navigation — the dominant mobile cost when browsing macro → country pages —
while ``defer`` keeps synchronous script execution off the first-paint path.

Runs after all builders have copied their assets into site/ (so the files exist
to hash), mirroring scripts/inject_data_base.py. Idempotent + never raises: a
ref that already carries a query is left as-is, so re-runs are no-ops. The core
rewrite lives in lib.pages.optimize_assets_text (kept beside the shim logic).

Run standalone: python -m scripts.optimize_assets
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import optimize_assets_text, write_page  # noqa: E402

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
    n = 0
    for html in site_dir.rglob("*.html"):
        try:
            text = html.read_text()
        except Exception:  # noqa: BLE001
            continue
        page_dir = html.parent

        def hash_for(url: str, _page_dir: Path = page_dir) -> Optional[str]:
            rel = url.split("?", 1)[0].split("#", 1)[0]
            try:
                target = (_page_dir / rel).resolve()
                target.relative_to(root)  # never hash outside the site tree
            except Exception:  # noqa: BLE001
                return None
            if target not in cache:
                cache[target] = _hash_bytes(target) if target.is_file() else None
            return cache[target]

        try:
            new = optimize_assets_text(text, hash_for)
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
