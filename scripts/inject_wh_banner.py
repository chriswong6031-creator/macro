"""Inject the White House alert ticker into every generated page.

The banner is one self-contained script (templates/wh_banner.js, copied to
site/wh_banner.js by build_site) that renders client-side from site/wh_banner.json.
Because the dashboard has many template families (no single shared <head>), the
robust way to make the ticker appear EVERYWHERE is a post-build pass that inserts
the <script> tag into each site/*.html — depth-aware (so the fetch + links resolve
from sub-directory pages) and idempotent (the `data-whb` marker means a re-run, or
a page that already carries it, is skipped).

This only changes pages when a NEW html file is added, so it is safe to run on
every full build. The hourly sentinel does NOT run it — the banner is client-side,
so refreshing site/wh_banner.json is enough for already-injected pages.

Run standalone:  python -m scripts.inject_wh_banner
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("inject_wh_banner")

_MARKER = "data-whb"


def _tag(prefix: str) -> str:
    return (f'<script defer {_MARKER} data-root="{prefix}" '
            f'src="{prefix}wh_banner.js"></script>')


def inject_text(text: str, prefix: str = "") -> str:
    """Return `text` with the banner <script> inserted before </body>. Idempotent —
    text that already carries the marker is returned unchanged. Used both by the
    dir-walk below and by build_whitehouse (so the report page self-includes it)."""
    if _MARKER in text:
        return text
    tag = _tag(prefix)
    idx = text.lower().rfind("</body>")
    if idx != -1:
        return text[:idx] + tag + "\n" + text[idx:]
    return text + "\n" + tag + "\n"


def inject(site_dir: Path) -> int:
    """Insert the banner script before </body> in every html under site_dir.
    Returns the number of files modified. Never raises."""
    site_dir = Path(site_dir)
    if not site_dir.is_dir():
        return 0
    n = 0
    for html in site_dir.rglob("*.html"):
        try:
            text = html.read_text()
        except Exception:  # noqa: BLE001
            continue
        if _MARKER in text:
            continue  # already injected
        # site-root-relative prefix from this file's depth (… site/sectors/x.html → "../")
        try:
            depth = len(html.relative_to(site_dir).parts) - 1
        except ValueError:
            depth = 0
        prefix = "../" * depth
        new = inject_text(text, prefix)
        try:
            html.write_text(new)
            n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("inject failed for %s (%s)", html.name, e)
    log.info("wh_banner injected into %d page(s)", n)
    return n


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config
    return 0 if inject(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
