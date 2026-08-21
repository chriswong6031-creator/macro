"""Build the Stage Analysis hub -> site/stage_analysis.html.

The page is a client-rendered hub: the template ships the shell (hero stage arc,
tab bar, controls) plus the fully-built Screener surface, and fetches its data
lazily per-tab from `site/stagedata/*.json`. This builder:

  1. Loads the committed context artifact (`data/stage_analysis/context/latest.json`,
     schema stage_context.v1) and passes its counts/market/asof to the template as
     `sga` — so the hero has real numbers on first paint, before any fetch.
  2. Copies the per-surface data artifacts into `site/stagedata/` so the page can
     fetch them client-side (lazy; we do NOT inline 1 MB+ into the HTML).
  3. Renders templates/stage_analysis.html.j2 via lib.pages.write_page.

Fail-open throughout: any missing artifact -> the corresponding surface renders
an explicit ingestion-health state, never a misleading scheduled "warm-up",
never a blank page, and never a build crash.
The stage classification is display_only / context-only (SGA-R4/R5) — never an
authority signal or a sizing input.

Usage:
    python -m scripts.build_stage_analysis_page               # repo-root auto-detect
    python -m scripts.build_stage_analysis_page --root /path/to/repo
    python -m scripts.build_stage_analysis_page --fixture tests/fixtures/stage_page_demo.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

log = logging.getLogger("build_stage_analysis_page")

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# The committed context artifact (drives the warm-up hero counts/stance).
_CONTEXT_REL = Path("stage_analysis") / "context" / "latest.json"

# Per-surface artifacts copied into site/stagedata/ for client-side lazy fetch.
# Phase 1 ships the Screener (screener.json); the rest are copied so phase-2
# surfaces can slot in without touching this builder. Absent files are skipped
# silently (fail-open) — the surface shows a warm-up state.
_STAGEDATA_FILES = [
    "screener.json",
    "stage_board_daily.json",
    "stage_board_weekly.json",
    "industry_flows.json",
    "industry_ranks.json",
    "industry_heatmap.json",
    "industry_name_pctile.json",
    "ec_industry.json",
    "ec_industry_heatmap.json",
    "earnings_table.json",
    "earnings_season.json",
    "earnings_compare.json",
    "altdata_trending.json",
    "research_index.json",
]


def _data_dir(root: Path) -> Path:
    """Resolve the data dir the same way the engines do (lib.config), else fall
    back to <root>/data — never crash on the import."""
    try:
        sys.path.insert(0, str(root))
        from lib import config as _cfg  # noqa: PLC0415

        return _cfg.data_dir()
    except Exception:  # noqa: BLE001
        return root / "data"


def _load_context(data_dir: Path, fixture: Path | None = None) -> dict | None:
    """Load the stage-context artifact for the warm-up hero. None on any failure."""
    path = fixture.resolve() if fixture is not None else (data_dir / _CONTEXT_REL)
    if not path.exists():
        log.info("stage context artifact not found at %s — warm-up hero", path)
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            log.warning("stage context artifact is not a dict; warm-up hero")
            return None
        return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load stage context artifact: %s; warm-up hero", exc)
        return None


def _is_stale_artifact(payload: dict) -> bool:
    """Wave 8 §8 — an artifact discloses its own staleness via any of these.

    Valid last-known data may be RETAINED only when the artifact itself
    discloses that it is stale; this is what makes the retention honest
    rather than a silent "still current" default.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("status") == "stale":
        return True
    if payload.get("stage_current") is False:
        return True
    population = payload.get("population")
    if isinstance(population, dict) and population.get("status") == "no_target_week":
        return True
    return False


def _copy_stagedata(data_dir: Path, site_dir: Path) -> tuple[int, int, int]:
    """Copy the per-surface JSON artifacts into site/stagedata/.

    Wave 8 §8 publication integrity — required behavior per artifact:
      - source present and valid (parses as JSON into a NON-EMPTY object) ->
        copy it atomically (temp + os.replace).
      - source ABSENT -> remove the public destination (if any) and disclose
        the revocation via `::warning title=stagedata-revoked::`. A missing
        current source must never preserve yesterday's destination as though
        it were current.
      - source present but carrying explicit stale provenance (`status` of
        "stale", `stage_current is false`, or
        `population.status == "no_target_week"`) -> copy it anyway and let
        the client render it as stale. Valid last-known data is retained
        ONLY when the artifact itself discloses that it is stale.

    Returns (copied, revoked, stale) — the counts of each outcome.

    Validation stays narrow and per-artifact — parses as JSON into a non-empty
    object — and is deliberately NOT a `schema`-key check. An earlier draft
    required `"schema" in payload`, which silently stopped publishing FIVE live
    surfaces (`ec_industry`, `ec_industry_heatmap`, `earnings_table`,
    `earnings_season`, `earnings_compare`): their producer `engine/earnings_qual.py`
    stamps `"surface"`, not `"schema"`. A publication guard that quietly freezes
    healthy surfaces is the very failure mode §8 exists to prevent, so the check
    tests only what it is actually for — that the bytes are a usable JSON object
    rather than a truncated or corrupt file. This is not a global data-health
    database.
    """
    src_dir = data_dir / "stage_analysis"
    out_dir = site_dir / "stagedata"
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    revoked = 0
    stale = 0
    for name in _STAGEDATA_FILES:
        src = src_dir / name
        dest = out_dir / name
        if not src.exists():
            if dest.exists():
                try:
                    dest.unlink()
                    revoked += 1
                    print(f"::warning title=stagedata-revoked::{name} source "
                          "absent — public copy revoked", flush=True)
                except Exception as exc:  # noqa: BLE001
                    log.warning("stagedata: failed to revoke %s: %s", name, exc)
            else:
                log.info("stagedata: %s absent — surface shows unavailable state", name)
            continue
        try:
            raw = src.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning("stagedata: %s unreadable/invalid JSON, skipping copy: %s",
                        name, exc)
            continue
        if not isinstance(payload, dict) or not payload:
            log.warning("stagedata: %s is not a non-empty JSON object, skipping copy",
                        name)
            continue
        try:
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_text(raw, encoding="utf-8")
            os.replace(tmp, dest)
            copied += 1
            if _is_stale_artifact(payload):
                stale += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("stagedata: failed to copy %s: %s", name, exc)
    return copied, revoked, stale


def render(root: Path, fixture: Path | None = None) -> str:
    """Render stage_analysis.html.j2 and return the HTML string (hero only)."""
    data_dir = _data_dir(root)
    sga = _load_context(data_dir, fixture)

    templates_dir = root / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
        undefined=Undefined,
    )

    # Wire bilingual helpers so td()/tr() in the template never crash a build.
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
    return tpl.render(sga=sga)


def build(root: Path, fixture: Path | None = None) -> Path:
    """Render the page AND copy the lazy-load data into site/stagedata/."""
    data_dir = _data_dir(root)
    site_dir = root / "site"

    copied, revoked, stale = _copy_stagedata(data_dir, site_dir)
    log.info("stagedata: copied=%d revoked=%d stale=%d -> %s",
             copied, revoked, stale, site_dir / "stagedata")

    html = render(root, fixture=fixture)

    out_path = site_dir / "stage_analysis.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # write_page is the ONLY write path — the raw-write fallback that used to sit
    # here swallowed every exception and shipped the page without the data-base
    # shim (fetches pointed at Pages instead of R2), a regression the render
    # lane's inject_data_base sweep then hid on the committed copy.
    from lib.pages import write_page  # noqa: PLC0415

    write_page(out_path, html)

    log.info("wrote %s (%d KB)", out_path, len(html) // 1024)
    return out_path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Render stage_analysis.html")
    parser.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    parser.add_argument(
        "--fixture",
        default=None,
        help="Load this JSON file as the stage-context (hero) instead of the live artifact",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    fixture = Path(args.fixture).resolve() if args.fixture else None

    try:
        build(root, fixture=fixture)
    except Exception as exc:  # noqa: BLE001
        log.error("build failed: %s", exc, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
