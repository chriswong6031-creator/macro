"""Post-render inline-CSS externalization: lift big <style> blocks to cached files.

macro.html + the country dashboards carry ~440KB of inline `<style>` (45% of the
page) that re-ships inside the HTML on every daily re-render — it can't be cached
because it rides in the 60s-TTL document. This sweep replaces each inline block
(>= MIN_BYTES) IN PLACE with a `<link>` to a content-hashed stylesheet under
`site/assets/css/<hash>.css`, tagged `?v=<hash>` so the existing Caddy
`@versioned` rule serves it `immutable` (no Caddy change). Returning daily
visitors then cache the stable CSS instead of re-downloading it, and the HTML
drops ~45%. In-place linking preserves the cascade and first-paint profile
(verified byte-identical rendering on macro/china/canada).

Cross-page dedup is real but small here (~6% — the CSS is mostly page-specific),
so identical blocks still share one file via the content hash. Tiny blocks stay
inline (a round-trip isn't worth a few hundred bytes). Orphaned hash files (from
a CSS change) are pruned each run — scoped strictly to site/assets/css/*.css.

Runs after all builders + inject_data_base, before optimize_assets. Idempotent +
never raises. Core rewrite: lib.pages.externalize_css_text.

Run standalone: python -m scripts.externalize_css
"""
from __future__ import annotations

import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import dbase_prefix, externalize_css_text, write_page  # noqa: E402

log = logging.getLogger("externalize_css")

MIN_BYTES = 1024  # below this, an inline block is cheaper than a request
_CSS_SUBDIR = ("assets", "css")
_REF_RE = re.compile(r"assets/css/([0-9a-f]{6,64})\.css")  # hash refs in final pages


def externalize(site_dir: Path) -> int:
    """Externalize inline CSS across every page under site_dir; prune orphaned
    hash files. Returns the number of pages modified. Never raises."""
    site_dir = Path(site_dir)
    if not site_dir.is_dir():
        return 0
    css_root = site_dir.joinpath(*_CSS_SUBDIR)
    referenced: Set[str] = set()  # hashes still linked by some page
    pages_changed = 0

    for html in sorted(site_dir.rglob("*.html")):
        try:
            text = html.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        prefix = dbase_prefix(html)  # "" at root, "../" per sub-dir (matches the shim)

        def make_href(css: str, index: int, media: Optional[str], _prefix: str = prefix) -> Optional[str]:
            data = css.encode("utf-8")
            if len(data) < MIN_BYTES:
                return None
            h = hashlib.sha256(data).hexdigest()[:8]
            dst = css_root / f"{h}.css"
            if not dst.exists():
                try:
                    css_root.mkdir(parents=True, exist_ok=True)
                    dst.write_text(css, encoding="utf-8")
                except OSError as e:
                    log.warning("write css %s failed: %s", dst.name, e)
                    return None
            return f"{_prefix}assets/css/{h}.css?v={h}"

        try:
            new = externalize_css_text(text, make_href)
        except Exception as e:  # noqa: BLE001
            log.warning("externalize failed for %s (%s)", html.name, e)
            new = text
        # record every css hash the FINAL page links (new links + any from a prior run)
        referenced.update(_REF_RE.findall(new))
        if new != text:
            try:
                write_page(html, new)  # keeps the data-base shim; avoids raw write_text
                pages_changed += 1
            except Exception as e:  # noqa: BLE001
                log.warning("write page %s failed: %s", html.name, e)

    pruned = _prune_orphans(css_root, referenced)
    log.info("externalized CSS on %d page(s); pruned %d orphan file(s)", pages_changed, pruned)
    return pages_changed


def _prune_orphans(css_root: Path, referenced: Set[str]) -> int:
    """Delete hash files under css_root that no page links anymore. Strictly
    scoped to css_root/*.css so a bug can never reach real content."""
    if not css_root.is_dir():
        return 0
    pruned = 0
    for f in css_root.glob("*.css"):
        if f.stem not in referenced:
            try:
                f.unlink()
                pruned += 1
            except OSError as e:  # noqa: BLE001
                log.warning("prune %s failed: %s", f.name, e)
    return pruned


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from lib import config

    return 0 if externalize(config.ROOT / "site") >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
