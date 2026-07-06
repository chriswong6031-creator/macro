"""patch_defer_plotly.py — idempotent one-shot script that rewrites the
synchronous <script src="plotly-2.32.0.min.js"> tag in rendered site/*.html to
the deferred stub-queue pattern so Plotly no longer blocks HTML parse.

Pattern applied:
  BEFORE (render-blocking):
    <script src="plotly-2.32.0.min.js"></script>

  AFTER (non-blocking):
    <script>window.__plotlyQ=[];window.Plotly={stub};</script>
    <script defer src="plotly-2.32.0.min.js"></script>
    <script>document.addEventListener('DOMContentLoaded',function(){drain});</script>

How it works:
  1. The stub captures newPlot/react/relayout calls made by inline chart blocks
     during HTML parse (before the deferred lib has executed).
  2. The lib loads with `defer` — browser continues parsing HTML in parallel.
  3. At DOMContentLoaded, deferred scripts have already run (per HTML spec:
     deferred external scripts execute before DOMContentLoaded fires), so
     window.Plotly is the real library. The drain replays the captured queue.
  4. themeCharts() in theme.js already guards with `if (!window.Plotly) return`
     and runs on window.load — by that point Plotly is real and charts are drawn.

Idempotent: files that already use `defer` on the plotly tag are left untouched.

The template-level fix (dashboard.html.j2, china.html.j2, canada.html.j2) already
applies this pattern to future nightly renders. This script patches currently
rendered pages for immediate effect.

Usage:
    python scripts/patch_defer_plotly.py [--site-dir path/to/site] [--dry-run]

Exit code 0 always (patching failures are logged but non-fatal).
"""
import argparse
import logging
import pathlib
import re

log = logging.getLogger(__name__)

SYNC_PLOTLY_RE = re.compile(
    r'<script src="plotly-2\.32\.0\.min\.js"></script>',
    re.IGNORECASE,
)

STUB = (
    '<script>'
    'window.__plotlyQ=[];'
    'window.Plotly={'
    'newPlot:function(){window.__plotlyQ.push([\'newPlot\',[].slice.call(arguments)]);return Promise.resolve();},'
    'react:function(){window.__plotlyQ.push([\'react\',[].slice.call(arguments)]);return Promise.resolve();},'
    'relayout:function(){window.__plotlyQ.push([\'relayout\',[].slice.call(arguments)]);}'
    '};'
    '</script>'
    '<script defer src="plotly-2.32.0.min.js"></script>'
    '<script>document.addEventListener(\'DOMContentLoaded\',function(){'
    'var q=window.__plotlyQ||[];window.__plotlyQ=null;'
    'q.forEach(function(c){try{window.Plotly[c[0]].apply(window.Plotly,c[1]);}catch(e){}});'
    '});</script>'
)


def patch_file(path: pathlib.Path, dry_run: bool = False) -> bool:
    """Apply deferred plotly pattern to path. Returns True if a change was made."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("cannot read %s: %s", path, exc)
        return False

    # Skip already-patched files (defer already present)
    if 'defer src="plotly-2.32.0.min.js"' in text or "defer src='plotly-2.32.0.min.js'" in text:
        log.info("already deferred: %s", path.name)
        return False

    new_text, n = SYNC_PLOTLY_RE.subn(STUB, text)
    if n == 0:
        log.info("no plotly tag found, skipping: %s", path.name)
        return False

    if dry_run:
        log.info("[dry-run] would patch %s (%d replacement(s))", path.name, n)
        return True

    try:
        path.write_text(new_text, encoding="utf-8")
        log.info("patched %s — deferred plotly (%d tag(s))", path.name, n)
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be changed without writing files",
    )
    args = parser.parse_args()

    site_dir = pathlib.Path(args.site_dir).resolve()
    if not site_dir.is_dir():
        log.error("site directory not found: %s", site_dir)
        return

    html_files = sorted(site_dir.glob("*.html"))
    changed = 0
    for path in html_files:
        if patch_file(path, dry_run=args.dry_run):
            changed += 1

    action = "would patch" if args.dry_run else "patched"
    log.info("done — %s %d / %d page(s)", action, changed, len(html_files))


if __name__ == "__main__":
    main()
