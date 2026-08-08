"""US entry-status re-measurement — the one-shot receipt instrument (ANTICIPATION §6.6).

Frozen instrument, in the shape of its CN sibling
(``research/cn_prophet_audit/v1_loser_audit.py``): it RECOMPUTES NOTHING.  Every number it
prints comes out of :mod:`engine.us_entry_status_remeasure`, which is the same code the
nightly miss-audit publishes as its ``entry_status_scorecard`` block — so the committed
receipt and the nightly table can never disagree about what a loser rate is.

The marks themselves are read from ``data/us_board_ledger/retro_grades.parquet`` exactly as
``scripts/grade_us_board.py`` wrote them (``engine.grading.forward_metrics``: next-bar fill,
positional session horizons, excess vs SPY).  Nothing here grades anything.

Run from the repo root:
    python3 research/prophet_us_audit/status_remeasurement.py

Writes ``research/prophet_us_audit/status_remeasurement_results.json`` (the frozen block) and
prints the markdown tables that ``US_STATUS_REMEASUREMENT_2026-08-08.md`` narrates, so no
figure in that receipt is ever hand-transcribed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import us_entry_status_remeasure as uesr  # noqa: E402

OUT = Path(__file__).parent / "status_remeasurement_results.json"

#: Print order — the ladder debate's own vocabulary first (CN's measured ordering, best to
#: worst), then everything else alphabetically. Fixed BEFORE the numbers were read.
STATUS_ORDER = ("bounce_wait", "wait_pullback", "hold", "extended", "buy_now", "partial",
                "buy_soon")


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100.0 * value:.1f}%"


def _xs(value: float | None) -> str:
    """Excess in percent. The block keeps the ledger's fraction; only display rescales."""
    return "—" if value is None else f"{100.0 * value:+.2f}%"


def _ordered(statuses) -> list[str]:
    known = [s for s in STATUS_ORDER if s in statuses]
    return known + sorted(s for s in statuses if s not in STATUS_ORDER)


def render_cohort(block: dict, cohort: str) -> list[str]:
    """One cohort's status x horizon table, thin cells labelled inline."""
    legs = (block.get("by_cohort") or {}).get(cohort) or {}
    horizons = sorted(legs, key=uesr.cell_sort_key)
    if not horizons:
        return [f"_no {cohort}-lane episodes in the ledger._"]
    statuses = _ordered({s for h in horizons
                         for s in (legs[h].get("by_entry_status") or {})})
    out = ["| entry status | " + " | ".join(f"H={h.rstrip('d')} n" for h in horizons)
           + " | " + " | ".join(f"H={h.rstrip('d')} loser" for h in horizons)
           + " | " + " | ".join(f"H={h.rstrip('d')} med excess" for h in horizons) + " |",
           "|---" * (1 + 3 * len(horizons)) + "|"]
    for status in statuses:
        cells = [(legs[h].get("by_entry_status") or {}).get(status) or {} for h in horizons]
        ns = " | ".join(
            (f"{c['n_excess']}{'*' if c.get('thin') else ''}" if c.get("n_excess") is not None
             else "—") for c in cells)
        losers = " | ".join(_pct(c.get("loser_rate")) for c in cells)
        meds = " | ".join(_xs(c.get("median_excess")) for c in cells)
        out.append(f"| `{status}` | {ns} | {losers} | {meds} |")
    out.append("")
    out.append(f"`*` = thin, fewer than {uesr.THIN_MIN_N} graded marks — DIRECTIONAL ONLY.")
    return out


def main() -> None:
    degraded: list[dict] = []
    block = uesr.scorecard(ROOT, degraded)
    OUT.write_text(json.dumps({"block": block, "degraded": degraded},
                              indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"# wrote {OUT.relative_to(ROOT)}")
    if not block.get("available"):
        print(f"\nNULL — {block.get('null_reason')}")
        for row in degraded:
            print(f"  degraded: {row.get('input')} — {row.get('reason')}")
        return
    cov, split = block["coverage"], block["cohort_split"]
    print(f"\ncoverage: {cov['n_episodes']} episodes, {cov['n_with_status']} with a status "
          f"({cov['status_coverage_pct']}%), {cov['n_dates']} dates "
          f"{cov['as_of']['first']} -> {cov['as_of']['last']}")
    print(f"lanes: {split['n_by_cohort']}  horizons: {block['horizons_present']}")
    print(f"statuses: {cov['n_by_status']}")
    for cohort in sorted(block.get("by_cohort") or {}):
        print(f"\n### {cohort} lane\n")
        print("\n".join(render_cohort(block, cohort)))
    print("\n### CN reference (NOT a US measurement)\n")
    ref = block["cn_reference"]["cn_loser_rate_by_status"]
    print("| entry status | CN loser rate | US buy-lane loser rate (H=5) |")
    print("|---|---|---|")
    buy5 = ((block["by_cohort"].get("buy") or {}).get("5d") or {}).get("by_entry_status") or {}
    for status in _ordered(set(ref)):
        cell = buy5.get(status) or {}
        mark = "*" if cell.get("thin") else ""
        print(f"| `{status}` | {_pct(ref[status])} | {_pct(cell.get('loser_rate'))}"
              f" (n={cell.get('n_excess', '—')}{mark}) |")


if __name__ == "__main__":
    main()
