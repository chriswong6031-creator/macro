"""Build the Stage Analysis page -> site/stage_analysis.html.

Reads  data/stage_analysis/context/latest.json  (schema stage_context.v1)
and renders templates/stage_analysis.html.j2.

The artifact is display_only / context-only — stage classification display,
never an authority signal or a sizing input (SGA-R4/R5).  This builder is
intentionally thin, mirroring scripts/build_market_structure_page.py: the
engine that writes latest.json lives in engine/stage_analysis.py (W1 lane).
For Wave 3 the builder loads whatever latest.json exists, passes it to the
Jinja template as `sga`, and renders.  Absent artifact -> sga=None -> the
template shows warm-up placeholders ("first classification runs tonight") for
every section, so the page never crashes a build.

Usage:
    python -m scripts.build_stage_analysis_page               # repo-root auto-detect
    python -m scripts.build_stage_analysis_page --root /path/to/repo
    python -m scripts.build_stage_analysis_page --fixture tests/fixtures/stage_page_demo.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

log = logging.getLogger("build_stage_analysis_page")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Relative path inside the data dir where the engine writes the artifact.
_ARTIFACT_REL = Path("stage_analysis") / "context" / "latest.json"

# Earnings-call tag taxonomy (pinned in masterplan §2) → plain-English label.
# The template bilingualises these via td() (ZH twins live in engine/i18n.LEX);
# raw slugs never reach a Tier-1 surface (DESIGN_DOCTRINE Law 2).
TAG_LABEL: dict[str, str] = {
    "guidance_raised": "Raised guidance",
    "guidance_lowered": "Cut guidance",
    "beat_and_raise": "Beat and raised",
    "miss_and_cut": "Missed and cut",
    "margin_expansion": "Margins expanding",
    "margin_contraction": "Margins shrinking",
    "demand_acceleration": "Demand picking up",
    "demand_slowdown": "Demand slowing",
    "supply_constraint": "Supply tight",
    "new_product": "New product",
    "buyback_or_dividend": "Buyback / dividend",
    "regulatory_headwind": "Regulatory headwind",
    "competitor_threat": "Competitive threat",
    "macro_sensitivity": "Macro-sensitive",
}


def _load_sga(root: Path, fixture: Path | None = None) -> dict | None:
    """Load the stage-analysis artifact.  Returns None on any failure."""
    if fixture is not None:
        path = fixture.resolve()
    else:
        try:
            sys.path.insert(0, str(root))
            from lib import config as _cfg  # noqa: PLC0415
            path = _cfg.data_dir() / _ARTIFACT_REL
        except Exception:  # noqa: BLE001
            path = root / "data" / _ARTIFACT_REL

    if not path.exists():
        log.info("stage_analysis artifact not found at %s — warm-up state", path)
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            log.warning("stage_analysis artifact is not a dict; warm-up state")
            return None
        return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load stage_analysis artifact: %s; warm-up state", exc)
        return None


def render(root: Path, fixture: Path | None = None) -> str:
    """Render stage_analysis.html.j2 and return the HTML string."""
    sga = _load_sga(root, fixture)

    templates_dir = root / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
        undefined=Undefined,
    )

    # Wire bilingual helpers so templates that use td() / tr() don't crash.
    # This template uses td() for dynamic labels (sectors, tone words, tags), so
    # provide a plain-EN fallback if the engine import ever fails — the page must
    # still render (fail-open) rather than crash a build.
    try:
        sys.path.insert(0, str(root))
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        from markupsafe import Markup  # noqa: PLC0415

        def _td(en):  # bilingual span, ZH falls back to EN
            return Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(en, en)

        env.globals.update(td=_td, tr=lambda en: en)

    tpl = env.get_template("stage_analysis.html.j2")
    return tpl.render(sga=sga, TAG_LABEL=TAG_LABEL)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Render stage_analysis.html")
    parser.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    parser.add_argument(
        "--fixture",
        default=None,
        help="Load this JSON file instead of the live artifact",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    fixture = Path(args.fixture).resolve() if args.fixture else None

    out_path = root / "site" / "stage_analysis.html"

    try:
        html = render(root, fixture=fixture)
    except Exception as exc:  # noqa: BLE001
        log.error("render failed: %s", exc, exc_info=True)
        return 1

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from lib.pages import write_page  # noqa: PLC0415
        write_page(out_path, html)
    except Exception:  # noqa: BLE001
        # Fallback: plain write (for use outside the site pipeline)
        out_path.write_text(html, encoding="utf-8")

    kb = len(html) // 1024
    log.info("wrote %s (%d KB)", out_path, kb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
