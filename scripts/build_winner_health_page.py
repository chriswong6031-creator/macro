#!/usr/bin/env python3
"""Build the Winner Health board -> site/winner_health.html (TOP ANATOMY W1).

Pure SSR, the `stage_analysis` page-builder pattern: load the committed context
artifact, render one template, write through `lib.pages.write_page`. The page
ships NO fetch, NO chart library and NO page JS of its own — the sparklines are
inline SSR SVG and every Tier-2 card is a static LENS block — so there is no
per-surface JSON to copy into `site/` and no lazy-load step.

Fail-open, and this builder NEVER raises: a missing, stale or malformed artifact
renders the designed "warming up" null state (spec §4.6 `warm`), which is an
honest reading rather than a gap. `main()` returns 0 in every case a page was
written.

Design contract: research/top_anatomy/W1_SURFACE_DESIGN_SPEC.md (visual law) +
docs/DESIGN_DOCTRINE.md (content law, wins on conflict). Display tier, zero
authority.

Usage:
    python -m scripts.build_winner_health_page
    python -m scripts.build_winner_health_page --root /path/to/repo
    python -m scripts.build_winner_health_page --fixture tests/fixtures/winner_health_demo.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

log = logging.getLogger("build_winner_health_page")

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_CONTEXT_REL = Path("top_maturation") / "latest.json"
#: Sessions after which the read is treated as not landed. The page's own as-of
#: stamp is the last PRICED bar, so a stale artifact would otherwise print an old
#: date beside a live-looking board.
_MAX_AGE_DAYS = 6


def _data_dir(root: Path) -> Path:
    """Resolve the data dir the way the engines do, else `<root>/data`."""
    try:
        sys.path.insert(0, str(root))
        from lib import config as _cfg  # noqa: PLC0415
        return Path(_cfg.data_dir())
    except Exception:  # noqa: BLE001
        return root / "data"


def _load_context(data_dir: Path, fixture: Path | None = None) -> dict | None:
    """Load the winner-health artifact. None on ANY failure -> the `warm` null."""
    path = fixture.resolve() if fixture is not None else (data_dir / _CONTEXT_REL)
    if not path.exists():
        log.info("winner health artifact not found at %s — warm null", path)
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("winner health artifact unreadable (%s) — warm null", exc)
        return None
    if not isinstance(raw, dict):
        log.warning("winner health artifact is not a dict — warm null")
        return None
    if fixture is None and _is_stale(raw):
        log.warning("winner health artifact is stale (asof=%s) — warm null", raw.get("asof"))
        return None
    return raw


def _is_stale(ctx: dict) -> bool:
    """True when the read is old enough that showing it would misdate the board."""
    from datetime import date  # noqa: PLC0415
    try:
        y, m, d = (int(x) for x in str(ctx.get("asof", ""))[:10].split("-"))
    except Exception:  # noqa: BLE001
        return True
    return (date.today() - date(y, m, d)).days > _MAX_AGE_DAYS


def render(root: Path, fixture: Path | None = None) -> str:
    """Render winner_health.html.j2 and return the HTML string."""
    wh = _load_context(_data_dir(root), fixture)

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
        undefined=Undefined,
    )
    # The included partials (_site_nav / _seo_head) call td()/tr(); a missing
    # global is a hard build crash, so they are wired with the same try/except
    # fallback the stage-analysis builder uses.
    try:
        sys.path.insert(0, str(root))
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        from markupsafe import Markup  # noqa: PLC0415

        def _td(en):  # bilingual span, ZH falls back to EN
            return Markup('<span class="l-en">{}</span>'
                          '<span class="l-zh">{}</span>').format(en, en)

        env.globals.update(td=_td, tr=lambda en: en)

    return env.get_template("winner_health.html.j2").render(wh=wh)


def build(root: Path, fixture: Path | None = None) -> Path:
    """Render the page and write it through the ONLY sanctioned write path."""
    html = render(root, fixture=fixture)
    out_path = root / "site" / "winner_health.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # write_page injects the depth-aware data-base shim. A raw write_text ships
    # the page without it and points every shared fetch at Pages instead of R2 —
    # the regression called out in the stage-analysis builder.
    from lib.pages import write_page  # noqa: PLC0415
    write_page(out_path, html)
    log.info("wrote %s (%d KB)", out_path, len(html) // 1024)
    return out_path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Render winner_health.html")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    ap.add_argument("--fixture", default=None,
                    help="Load this JSON as the context instead of the live artifact")
    a = ap.parse_args(argv)

    root = Path(a.root).resolve() if a.root else _REPO_ROOT
    fixture = Path(a.fixture).resolve() if a.fixture else None
    try:
        build(root, fixture=fixture)
    except Exception as exc:  # noqa: BLE001 — a page builder never takes the lane down
        print(f"::warning title=winner-health-page::render failed ({exc})", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
