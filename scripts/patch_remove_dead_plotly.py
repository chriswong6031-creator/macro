"""patch_remove_dead_plotly.py — idempotent one-shot script that strips dead
Plotly loading from already-rendered pages that have no Plotly charts.

Two classes of dead weight:

1. Stock-mode pages rendered before the template was gated carry a bare
   `<script src="plotly-2.32.0.min.js"></script>` tag.

2. macro.html and commodities.html carry the full `_plotly_head.html.j2`
   block (the `window.__plotlyQ` queue shim + a deferred plotly tag + the
   DOMContentLoaded flush) even though neither page renders a single Plotly
   chart anymore — macro's charts moved to macro_signals.html and its
   sparklines are inline SVG; commodities' board/heat grid are pure HTML/SVG.
   That block made the browser download + parse a 3.5MB (1.15MB gzipped)
   library for nothing — ~79% of macro.html's total transfer — and delayed
   DOMContentLoaded (deferred scripts run before DCL) on the flagship page.

Pages that genuinely use Plotly charts (macro_signals.html, china.html,
canada.html, and all strategy/history/commodity-strategy pages — anything with
a real `Plotly.newPlot` call) are left untouched.

The template fixes (dashboard.html.j2, commodities.html.j2, china.html.j2,
canada.html.j2) already prevent future nightly renders from emitting the dead
tags. This script patches already-rendered pages in site/ for immediate effect
without a full 67-minute rebuild.

Idempotent: if the tags are already absent the script is a no-op. Safety: it
refuses to touch any page that contains a real `Plotly.newPlot(` call outside
the queue shim.

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

# Pages carrying the full _plotly_head block (shim + defer tag + DCL flush)
# with zero Plotly charts on the page.
DEAD_HEAD_PAGES = [
    "macro.html",
    "commodities.html",
]

PLOTLY_SCRIPT_RE = re.compile(
    r'<script (?:defer )?src="plotly-2\.32\.0\.min\.js"></script>\n?',
    re.IGNORECASE,
)

# The three-script block emitted by templates/_plotly_head.html.j2: the
# __plotlyQ queue shim, the deferred library tag, and the DOMContentLoaded
# flush. Matched as one unit so a partial strip can never leave a dangling
# shim that would mask a future real chart regression.
PLOTLY_HEAD_BLOCK_RE = re.compile(
    r'<script>window\.__plotlyQ=\[\];.*?</script>'
    r'<script defer src="plotly-2\.32\.0\.min\.js"></script>'
    r"<script>document\.addEventListener\('DOMContentLoaded'.*?</script>\n?",
    re.DOTALL,
)

# A real chart call (not the shim's own `newPlot:function` member).
REAL_NEWPLOT_RE = re.compile(r"Plotly\.newPlot\s*\(")


def patch_file(path: pathlib.Path, block: bool) -> bool:
    """Strip dead plotly loading from path. Returns True if a change was made.

    block=True removes the full _plotly_head block; block=False removes just
    the bare script tag (legacy stocks-page form).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("cannot read %s: %s", path, exc)
        return False

    if REAL_NEWPLOT_RE.search(text):
        log.warning("REFUSING %s — page contains a real Plotly.newPlot call", path.name)
        return False

    regex = PLOTLY_HEAD_BLOCK_RE if block else PLOTLY_SCRIPT_RE
    new_text, n = regex.subn("", text)
    if n == 0:
        log.info("already clean (no plotly tag): %s", path.name)
        return False

    try:
        path.write_text(new_text, encoding="utf-8")
        log.info("patched %s — removed %d plotly block(s)/tag(s)", path.name, n)
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
    targets = [(name, False) for name in STOCKS_PAGES] + [
        (name, True) for name in DEAD_HEAD_PAGES
    ]
    for name, block in targets:
        p = site_dir / name
        if not p.exists():
            log.warning("page not found, skipping: %s", p)
            continue
        if patch_file(p, block):
            changed += 1

    log.info("done — patched %d / %d page(s)", changed, len(targets))


if __name__ == "__main__":
    main()
