"""Render the Capital Structure observed-filing-state desk.

The browser receives its issuer rows and filing evidence only through the
authenticated Capital Structure API. This builder deliberately writes no data
projection: it emits the premium desk shell and its paired assets so an
ordinary full-site render cannot leave the page stale. The one exception is a
read-only Policy watch chip (B-F09-6, MO-PAID-067), which cites a single
dated policy_calendar step — display-only, no score/rank/direction.

Usage:
    python -m scripts.build_capital_structure_page
    python -m scripts.build_capital_structure_page --root /path/to/repo
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
_ASSETS = ("capital_structure_boot.js", "capital_structure.css", "capital_structure.js")


# ── policy-watch:start (B-F09-6, MO-PAID-067) ──
CAPITAL_MARKETS_THEMES = ("capital_markets", "capital_formation")  # first match wins


def _policy_watch(today=None) -> dict:
    """Cite ONE dated policy step for this desk. No score, no rank, no direction.

    Reuses engine.policy_calendar.compute_policy_calendar + format_policy_reg_chip
    (the one existing formatter) — never a second formatter, never a new signal.
    Three states, all rendered (nulls printed, UNKNOWN != EMPTY):
      unavailable — documents.parquet absent for this build
      empty       — calendar present, no capital-markets-scoped dated step
      present     — a dated step, expressed only through typed chip fields
    """
    unavailable = {
        "state": "unavailable",
        "headline_en": "Policy calendar not in this build",
        "headline_zh": "本次构建未包含政策日历",
        "detail_en": "Nothing is hidden — the source record was not present when this page was built.",
        "detail_zh": "没有隐藏内容——本页构建时未取到来源记录。",
    }
    empty = {
        "state": "empty",
        "headline_en": "No dated policy step ahead",
        "headline_zh": "前方没有已定日期的政策节点",
        "detail_en": "We watch SEC, Treasury, Fed, CFTC and FinCEN rule dates. None is pending.",
        "detail_zh": "我们关注 SEC、财政部、美联储、CFTC 与 FinCEN 的规则日期，目前没有待办节点。",
    }
    try:
        from engine.policy_calendar import compute_policy_calendar, format_policy_reg_chip
    except Exception:  # noqa: BLE001 — a chip must never crash the desk build
        return unavailable

    try:
        cal = compute_policy_calendar(today=today)
    except Exception:  # noqa: BLE001
        return unavailable
    if cal is None:
        return unavailable

    themes = cal.get("themes") or {}
    theme_key = None
    row = None
    for key in CAPITAL_MARKETS_THEMES:
        if key in themes:
            theme_key = key
            row = themes[key]
            break

    if row is None:
        # No capital-markets theme row in this build's data. Note (DEVIATION from
        # the frozen spec's agency_slug fallback): upcoming_events rows do not
        # carry agency_slug (only basket_id/reg_stage/title/date) — filtering by
        # agency there is not possible without fabricating a field, so the
        # fallback checks the same CAPITAL_MARKETS_THEMES basket ids instead.
        upcoming = [e for e in (cal.get("upcoming_events") or [])
                    if e.get("basket_id") in CAPITAL_MARKETS_THEMES]
        if not upcoming:
            return empty
        theme_key = upcoming[0]["basket_id"]
        row = themes.get(theme_key) or {}

    try:
        chip = format_policy_reg_chip(row, theme_key)
    except Exception:  # noqa: BLE001
        return empty
    if chip is None:
        return empty

    dtcc = chip.get("days_to_comment_close")
    dtrf = chip.get("days_to_rule_effective")
    pr60 = chip.get("prorule_inflow_60d") or 0
    fr60 = chip.get("rule_finalization_60d") or 0

    if dtcc is not None:
        d = int(dtcc)
        if d <= 0:
            headline_en, headline_zh = "Comment window closes today", "征询意见期今天截止"
        elif d == 1:
            headline_en, headline_zh = "Comment window closes in 1 day", "征询意见期 1 天后截止"
        else:
            headline_en = f"Comment window closes in {d} days"
            headline_zh = f"征询意见期 {d} 天后截止"
    elif dtrf is not None:
        d = int(dtrf)
        headline_en = f"A final rule takes effect in {d} days"
        headline_zh = f"最终规则 {d} 天后生效"
    else:
        n = pr60 + fr60
        headline_en = f"{n} new rule steps in the last 60 days"
        headline_zh = f"过去 60 天有 {n} 项新规则动作"

    return {
        "state": "present",
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "detail_en": "Dated steps already on the public record. Not a rating and not a trade call.",
        "detail_zh": "均为已进入公开记录的既定日期节点。不是评级，也不是交易建议。",
    }
# ── policy-watch:end ──


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(destination)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def render(root: Path) -> Path:
    """Write a data-free desk shell plus exact CSS/JS companions."""
    root = root.resolve()
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
        undefined=StrictUndefined,
    )
    html = env.get_template("capital_structure.html.j2").render(
        active_section="research",
        active_page="capital_structure",
        policy_watch=_policy_watch(),
    )
    # Shared navigation templates intentionally contain indentation around
    # conditional blocks. Normalize generated-only blank-line whitespace so the
    # committed shell remains diff-clean without modifying global nav output.
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    # write_page owns the depth-aware data-base shim. Use its result through a
    # temporary file so even a standalone builder cannot expose a partial page.
    from lib.pages import write_page  # noqa: PLC0415

    page = site / "capital_structure.html"
    temp = _temp_sibling(page)
    try:
        write_page(temp, html)
        os.replace(temp, page)
    finally:
        temp.unlink(missing_ok=True)
    for asset in _ASSETS:
        _atomic_copy(root / "templates" / asset, site / asset)
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        page = render(args.root)
    except Exception as exc:  # noqa: BLE001 — precise non-zero helps shared render diagnose a missing desk asset
        print(f"::error title=capital_structure_page::build failed ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
