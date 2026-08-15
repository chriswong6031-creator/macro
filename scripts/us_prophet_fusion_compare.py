#!/usr/bin/env python3
"""Before/after board comparison for the 2026-08-15 fusion override — the ACCEPTANCE surface.

WHAT THIS IS FOR.  The Chairman override replaced the US board's rank authority without
waiting for forward outcomes, so the immediate acceptance question is not "does it
predict" — no H10/H21/H63 evidence exists yet and none is claimed — but "is this a
materially more compelling list of stocks".  Answering that needs the two orders side by
side over the SAME board, with the reason each name moved written out.  This produces
exactly that, deterministically, from the committed artifact.

WHAT IT IS NOT.  Not a backtest, not a promotion gate, and not evidence of forward alpha.
It re-ranks ONE frozen board.  A name that rises here rose because the evidence families
voted for it, which is a statement about breadth of present evidence and nothing else.

IT ALSO PROVES THE FREEZE.  The retired v2 scorer is re-run through
``us_board_rank.legacy_v2_values`` over the same rows and checked against the score the
artifact PUBLISHED.  A byte-exact reproduction is what makes the shadow a shadow: if the
frozen scorer did not reproduce what shipped, the "old" column of this comparison would
be a comparison against nothing (the same failure mode ``prophet_fusion_race``'s replay
gate exists to catch).  A mismatch is a hard failure, not a warning.

    python3 scripts/us_prophet_fusion_compare.py
    python3 scripts/us_prophet_fusion_compare.py --top 30 --out research/prophet_fusion
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

_REPO = Path(__file__).resolve().parent.parent   # scripts/* -> parents[1]
sys.path.insert(0, str(_REPO))

from engine import us_board_rank as ubr           # noqa: E402

BOARD = _REPO / "site" / "factordata" / "us_standouts.json"
GATE = _REPO / "site" / "factordata" / "signal_gate.json"
DEFAULT_OUT = _REPO / "research" / "prophet_fusion"


class ReplayMismatch(RuntimeError):
    """The frozen v2 scorer did not reproduce the score the artifact published."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _entry_status(row: Mapping[str, Any]) -> str:
    return str((row.get("entry_signal") or {}).get("status") or "—")


def _why(new_row: Mapping[str, Any], old_rank: int, new_rank: int,
         old_score: float, families: Mapping[str, float]) -> str:
    """One plain-English sentence for why this name moved.

    Written from the RECEIPT, never from a narrative: the families that voted, the ones
    that carried it, and the retired legs it used to be carried by.  A reader who does
    not trust the sentence can check every number in it in the row beside it.
    """
    delta = old_rank - new_rank
    if not families:
        return ("no evidence family could speak to this name tonight — it is unscored "
                "and sits after every scored row in its stage bucket")
    top = sorted(families.items(), key=lambda kv: -kv[1])[:2]
    carried = ", ".join(f"{_short(f)} {v:.0f}" for f, v in top)
    stage = str(new_row.get("stage") or "")
    if delta > 0:
        return (f"up {delta} — broad evidence: {len(families)} families voted, led by "
                f"{carried}; the retired score had it at {old_score:.1f}")
    if delta < 0:
        return (f"down {-delta} — thinner evidence than the pool: {len(families)} "
                f"families voted ({carried}); the retired score had it at "
                f"{old_score:.1f} on its five legs")
    return (f"unchanged — {len(families)} families voted ({carried}); stage {stage}")


def _short(family: str) -> str:
    return family.split("_", 1)[1].replace("_", " ").lower() if "_" in family else family


def compare(*, top: int = 30) -> dict[str, Any]:
    board = _load(BOARD)
    gate = _load(GATE) if GATE.exists() else {}
    verdicts = gate.get("verdicts") or {}
    buy = list(board.get("buy") or [])
    if not buy:
        raise SystemExit("the committed board carries no buy lane — nothing to compare")

    # The published order, exactly as it shipped, before anything is recomputed.
    old = {}
    for row in buy:
        published = (row.get("prophet") or {})
        old[str(row.get("ticker"))] = {
            "rank": int(row.get("display_rank") or 0),
            "score": float(published.get("score") or 0.0),
            "version": str(published.get("version") or ""),
            "stage": str(row.get("stage") or ""),
            "entry_status": _entry_status(row),
            "featured": bool(row.get("featured")),
        }

    rows = [dict(r) for r in buy]
    for r in rows:                     # the published stamps are what we re-derive
        for key in ("prophet", "prophet_shadow", "score_rank", "display_rank",
                    "featured", "featured_blocked_by", "stage"):
            r.pop(key, None)

    floors: dict[str, Any] = {}
    scored = ubr.score_rows(
        rows,
        verdict_by=verdicts,
        board_asof=board.get("as_of"),
        bottom_watch_stage=ubr.STAGE_BASING,
        fusion_floors=floors,
    )

    # THE FREEZE CHECK.  The shadow must reproduce what shipped, name for name.
    drift = []
    for row in scored:
        ticker = str(row.get("ticker"))
        was = old.get(ticker, {}).get("score")
        now = (row.get("prophet_shadow") or {}).get("score")
        if was is None or now is None or abs(float(was) - float(now)) > 1e-9:
            drift.append({"ticker": ticker, "published": was, "replayed": now})
    if drift:
        raise ReplayMismatch(
            f"the frozen v2 scorer did not reproduce {len(drift)} of {len(scored)} "
            f"published scores — the 'old' column would be a comparison against "
            f"nothing. First 5: {drift[:5]}")

    definition = ubr.published_definition(scored)
    ranking = ubr.ranking_block(scored, theme_asof=(board.get("ranking") or {})
                                .get("theme_asof"), fusion_floors=floors)

    table = []
    for row in scored:
        ticker = str(row.get("ticker"))
        prior = old.get(ticker, {})
        block = row.get("prophet") or {}
        fam = (block.get("fusion") or {}).get("family_contribution") or {}
        new_rank = int(row.get("display_rank") or 0)
        old_rank = int(prior.get("rank") or 0)
        table.append({
            "ticker": ticker,
            "name": row.get("name"),
            "sector": row.get("sector"),
            "new_rank": new_rank,
            "old_rank": old_rank,
            "rank_change": old_rank - new_rank,
            "fusion_score": block.get("score"),
            "v2_score": prior.get("score"),
            "v2_rank": old_rank,
            "shadow_rank": (row.get("prophet_shadow") or {}).get("score_rank"),
            "stage": row.get("stage"),
            "entry_status": _entry_status(row),
            "featured_new": bool(row.get("featured")),
            "featured_old": bool(prior.get("featured")),
            "n_families": len(fam),
            "family_contribution": fam,
            "families_abstaining": (block.get("fusion") or {}).get(
                "families_abstaining") or [],
            "member_percentiles": (block.get("fusion") or {}).get(
                "member_percentiles") or {},
            "why": _why(row, old_rank, new_rank, float(prior.get("score") or 0.0), fam),
        })

    # WHICH FAMILIES ACTUALLY SEPARATED NAMES.  A family can clear both floors and
    # still hand nearly every row the same number — `news_burst` firing on 1 of 69 rows
    # gives 68 of them the identical tied percentile.  That is the REGISTERED behaviour
    # (a sparse-but-variable event flag is meant to pass; the floor is not re-tuned
    # here, and never against outcomes), but a reader comparing two orders has to be
    # able to see that a listed family did almost no ordering work.  Measured, printed,
    # not acted on.
    concentration = []
    for family in sorted({f for r in table for f in r["family_contribution"]}):
        values = [r["family_contribution"][family] for r in table
                  if family in r["family_contribution"]]
        if not values:
            continue
        modal = max(set(values), key=values.count)
        share = values.count(modal) / len(values)
        concentration.append({
            "family": family, "rows": len(values),
            "modal_contribution": modal, "modal_share": round(share, 4),
            "distinct_values": len(set(values)),
        })

    by_new = sorted(table, key=lambda r: r["new_rank"])
    by_old = sorted(table, key=lambda r: r["old_rank"])
    new_top = {r["ticker"] for r in by_new[:top]}
    old_top = {r["ticker"] for r in by_old[:top]}

    return {
        "as_of": board.get("as_of"),
        "source_artifact": str(BOARD.relative_to(_REPO)),
        "old_definition": board.get("rank_by"),
        "new_definition": definition,
        "n_buy": len(scored),
        "top_n": top,
        "acceptance_note": (
            "This compares two ORDERS over one frozen board. It is not a backtest and "
            "carries no claim of forward predictive alpha — no graded outcome exists "
            "for a fusion-ranked night, and the C1 construction was raced "
            "non-promotion-bearing (#5667) with the C2 fit REFUSED for want of lawful "
            "folds (#5700). The acceptance question it answers is whether the new list "
            "is a more compelling set of names to a reader."),
        "fusion_receipt": ranking.get("fusion"),
        "family_separation": concentration,
        "promoted_into_top": sorted(new_top - old_top),
        "demoted_out_of_top": sorted(old_top - new_top),
        "held_top": sorted(new_top & old_top),
        "biggest_gains": [r["ticker"] for r in
                          sorted(table, key=lambda r: -r["rank_change"])[:10]],
        "biggest_losses": [r["ticker"] for r in
                           sorted(table, key=lambda r: r["rank_change"])[:10]],
        "featured_changed": sorted(r["ticker"] for r in table
                                   if r["featured_new"] != r["featured_old"]),
        "new_top": by_new[:top],
        "old_top": by_old[:top],
        "all_rows": by_new,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    out: list[str] = []
    add = out.append
    add(f"# US Prophet — fusion override before/after ({report['as_of']})\n")
    add(f"`{report['old_definition']}` → `{report['new_definition']}` over "
        f"{report['n_buy']} buy rows of `{report['source_artifact']}`.\n")
    add(f"> {report['acceptance_note']}\n")

    receipt = report.get("fusion_receipt") or {}
    add("## What voted\n")
    add(f"- **Families active**: {', '.join(receipt.get('families_active') or []) or '—'}")
    add(f"- **Families abstaining**: "
        f"{', '.join(receipt.get('families_abstaining') or []) or '—'}")
    add(f"- **Members voting**: "
        f"{', '.join(m['column'] for m in receipt.get('members_voting') or []) or '—'}")
    stood = (receipt.get("floors") or {}).get("members_stood_down") or []
    if stood:
        add("- **Members stood down by a floor**:")
        for d in stood:
            detail = (f"presence {d['coverage']:.3f} < {d['presence_floor']}"
                      if d["reason"] == "below_presence_floor" else
                      f"vote-inert (variation share {d.get('variation_share')})")
            add(f"  - `{d['column']}` ({d['family']}) — {detail}")
    else:
        add("- **Members stood down by a floor**: none")
    add(f"- **Rows scored / unscored**: {receipt.get('rows_scored')} / "
        f"{receipt.get('rows_unscored')}\n")

    add("### How much each family actually SEPARATED names\n")
    add("A family can clear both floors and still hand nearly every row the same "
        "number. That is registered behaviour for a sparse-but-variable event flag — "
        "printed here rather than acted on, so the ordering work each family did is "
        "visible instead of assumed.\n")
    add("| family | rows | distinct values | modal contribution | share of rows at it |")
    add("|---|--:|--:|--:|--:|")
    for c in report.get("family_separation") or []:
        add(f"| {c['family']} | {c['rows']} | {c['distinct_values']} | "
            f"{c['modal_contribution']:.2f} | {c['modal_share']:.0%} |")
    add("")

    add(f"## New top {report['top_n']}\n")
    add("| # | was | Δ | ticker | fusion | v2 | stage | entry | fams | why |")
    add("|--:|--:|--:|---|--:|--:|---|---|--:|---|")
    for r in report["new_top"]:
        score = "—" if r["fusion_score"] is None else f"{r['fusion_score']:.1f}"
        add(f"| {r['new_rank']} | {r['old_rank']} | {r['rank_change']:+d} | "
            f"**{r['ticker']}** | {score} | {r['v2_score']:.1f} | {r['stage']} | "
            f"{r['entry_status']} | {r['n_families']} | {r['why']} |")

    add(f"\n## Names promoted INTO the top {report['top_n']}\n")
    add(", ".join(f"`{t}`" for t in report["promoted_into_top"]) or "_none_")
    add(f"\n## Names demoted OUT of the top {report['top_n']}\n")
    add(", ".join(f"`{t}`" for t in report["demoted_out_of_top"]) or "_none_")
    add(f"\n## Old top {report['top_n']} (retired us_prophet_v2 order)\n")
    add("| # | now | ticker | v2 | fusion | stage | entry |")
    add("|--:|--:|---|--:|--:|---|---|")
    for r in report["old_top"]:
        score = "—" if r["fusion_score"] is None else f"{r['fusion_score']:.1f}"
        add(f"| {r['old_rank']} | {r['new_rank']} | `{r['ticker']}` | "
            f"{r['v2_score']:.1f} | {score} | {r['stage']} | {r['entry_status']} |")

    if report["featured_changed"]:
        add("\n## Featured set changed\n")
        add(", ".join(f"`{t}`" for t in report["featured_changed"]))
    else:
        add("\n## Featured set changed\n\n_no change_")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--print", action="store_true", help="markdown to stdout only")
    args = ap.parse_args(argv)

    report = compare(top=args.top)
    markdown = render_markdown(report)
    if args.print:
        print(markdown)
        return 0
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "FUSION_BOARD_COMPARISON.md").write_text(markdown)
    (out_dir / "fusion_board_comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {out_dir / 'FUSION_BOARD_COMPARISON.md'}")
    print(f"wrote {out_dir / 'fusion_board_comparison.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
