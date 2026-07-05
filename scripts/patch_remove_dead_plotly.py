"""patch_remove_dead_plotly.py — idempotent one-shot script that strips the
dead Plotly <script> tag from stock-mode pages that were rendered before the
template was gated.

Pages that genuinely use Plotly charts (macro.html, china.html, canada.html,
and all strategy/history/commodity pages) are left untouched.

The template fix in dashboard.html.j2, china.html.j2, canada.html.j2 already
prevents future nightly renders from emitting the tag for stocks-mode pages.
This script patches already-rendered pages in site/ for immediate effect
without a full 67-minute rebuild.

Idempotent: if the tag is already absent the script is a no-op.

Usage:
    python scripts/patch_remove_dead_plotly.py [--site-dir path/to/site]

Exit code 0 always (patching failures are logged but non-fatal).
"""
import argparse
import logging
import pathlib
import re

log = logging.getLogger(__name__)

# Stock-mode pages that have NO Plotly charts and should not load the lib.
STOCKS_PAGES = [
    "us_stocks.html",
    "china_stocks.html",
    "canada_stocks.html",
]

PLOTLY_SCRIPT_RE = re.compile(
    r'<script src="plotly-2\.32\.0\.min\.js"></script>\n?',
    re.IGNORECASE,
)


def patch_file(path: pathlib.Path) -> bool:
    """Remove the plotly script tag from path. Returns True if a change was made."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("cannot read %s: %s", path, exc)
        return False

    new_text, n = PLOTLY_SCRIPT_RE.subn("", text)
    if n == 0:
        log.info("already clean (no plotly tag): %s", path.name)
        return False

    try:
        path.write_text(new_text, encoding="utf-8")
        log.info("patched %s — removed %d plotly script tag(s)", path.name, n)
        return True
    except Exception as exc:
        log.warning("cannot write %s: %s", path, exc)
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-dir",
        default=str(pathlib.Path(__file__).parent.parent / "site"),
        help="Path to the site/ output directory (default: ../site relative to this script)",
    )
    args = parser.parse_args()

    site_dir = pathlib.Path(args.site_dir).resolve()
    if not site_dir.is_dir():
        log.error("site directory not found: %s", site_dir)
        return

    changed = 0
    for name in STOCKS_PAGES:
        p = site_dir / name
        if not p.exists():
            log.warning("page not found, skipping: %s", p)
            continue
        if patch_file(p):
            changed += 1

    log.info("done — patched %d / %d page(s)", changed, len(STOCKS_PAGES))


if __name__ == "__main__":
    main()
