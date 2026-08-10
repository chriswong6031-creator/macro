"""R2 replay receipt — stage-gate ordering fix + reversal-cohort channel.

Reproduces every number in PR "R2 stage-gate ordering + US reversal_member cohort"
from artifacts that are COMMITTED, so a reader can re-derive them without a nightly:

  site/factordata/us_standouts.json    the buy lane the board ranks
  site/factordata/signal_gate.json     the confluence verdicts
  site/basketdata/us_basket_turn.json  the washout-lifecycle organ's states
  data/baskets/membership.json         the curated basket membership

BASE is ``origin/main`` at the time of the run; HEAD is the working tree.  Both are
loaded as standalone modules, so the two eras of the ranker score the SAME rows.

Run from the repo root:  python3 research/prophet_us_audit/r2_stage_cohort_replay.py
Writes: research/prophet_us_audit/r2_stage_cohort_replay_results.json
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "r2_stage_cohort_replay_results.json"


def _load(name: str, source: str):
    """Import a module from source text under its own name."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        path.unlink(missing_ok=True)


def main() -> dict:
    # The base SHA is recorded with the numbers.  `origin/main` moves, so a reader
    # re-running this later compares against a different base unless they can see which
    # one produced the committed results.
    base_sha = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "origin/main"],
        capture_output=True, text=True, check=True).stdout.strip()
    base_src = subprocess.run(
        ["git", "-C", str(REPO), "show", "origin/main:engine/us_board_rank.py"],
        capture_output=True, text=True, check=True).stdout
    base = _load("_ubr_base", base_src)
    head = _load("_ubr_head", (REPO / "engine/us_board_rank.py").read_text())

    board = json.loads((REPO / "site/factordata/us_standouts.json").read_text())
    verdicts = json.loads(
        (REPO / "site/factordata/signal_gate.json").read_text()).get("verdicts") or {}

    before = base.score_rows([dict(r) for r in board["buy"]],
                             verdict_by=verdicts, board_asof=board["as_of"])
    cohort = head.load_reversal_cohort(site_root=REPO / "site", data_dir=REPO / "data")
    after = head.score_rows([dict(r) for r in board["buy"]],
                            verdict_by=verdicts, board_asof=board["as_of"],
                            reversal_cohort=cohort)

    by_before = {r["ticker"]: r for r in before}
    by_after = {r["ticker"]: r for r in after}
    order_before = [r["ticker"] for r in before]
    order_after = [r["ticker"] for r in after]

    featured_before = [r["ticker"] for r in before if r["featured"]]
    featured_after = [r["ticker"] for r in after if r["featured"]]

    reason_changes = []
    for ticker, lhs in by_before.items():
        old = list(lhs.get("featured_blocked_by") or [])
        new = list(by_after[ticker].get("featured_blocked_by") or [])
        if old != new:
            reason_changes.append({
                "ticker": ticker,
                "stage": by_after[ticker]["stage"],
                "base": old,
                "head": new,
            })

    def _within_stage_monotone(rows, mod) -> bool:
        for stage in mod.STAGE_ORDER:
            scores = [r["prophet"]["score"] for r in rows if r["stage"] == stage]
            if scores != sorted(scores, reverse=True):
                return False
        return True

    ran = [r for r in after if r["stage"] == "ran"]
    live = [r for r in after if r["stage"] == "live"]

    results = {
        "base_sha": base_sha,
        "board_asof": board["as_of"],
        "rows": len(after),
        "membership_identical": sorted(order_before) == sorted(order_after),
        "board_order_identical": order_before == order_after,
        "featured": {
            "base_n": len(featured_before),
            "head_n": len(featured_after),
            "gained": [
                {"ticker": t,
                 "stage": by_after[t]["stage"],
                 "score": by_after[t]["prophet"]["score"],
                 "status": (by_after[t].get("entry_signal") or {}).get("status")}
                for t in featured_after if t not in featured_before
            ],
            "lost": [t for t in featured_before if t not in featured_after],
        },
        "veto_reason_changes": {
            "n": len(reason_changes),
            "of": len(after),
            "sample": reason_changes[:10],
        },
        "ordering_law": {
            "base_stage_sequence_monotone":
                [base.stage_rank(r["stage"]) for r in before]
                == sorted(base.stage_rank(r["stage"]) for r in before),
            "head_stage_sequence_monotone":
                [head.stage_rank(r["stage"]) for r in after]
                == sorted(head.stage_rank(r["stage"]) for r in after),
            "base_score_non_increasing_within_stage":
                _within_stage_monotone(before, base),
            "head_score_non_increasing_within_stage":
                _within_stage_monotone(after, head),
        },
        "reversal_cohort": {
            "input": cohort["input"],
            "as_of": cohort["as_of"],
            "baskets_in_cohort": cohort["baskets_in_cohort"],
            "baskets_read": cohort["baskets_read"],
            "universe_members": len(cohort["members"]),
            "coverage": head.reversal_cohort_coverage(after),
            "board_members": sorted(r["ticker"] for r in after
                                    if r["reversal_member"]),
            "scores_unchanged_by_membership": all(
                by_before[t]["prophet"]["score"] == by_after[t]["prophet"]["score"]
                for t in by_before),
        },
        "dont_chase_deviation": {
            "best_ran_score": max((r["prophet"]["score"] for r in ran), default=None),
            "worst_live_score": min((r["prophet"]["score"] for r in live), default=None),
            "a_ran_row_outscores_a_live_row": bool(
                ran and live
                and max(r["prophet"]["score"] for r in ran)
                > min(r["prophet"]["score"] for r in live)),
            "every_ran_row_still_sorts_below_every_live_row": bool(
                not ran or not live
                or min(i for i, r in enumerate(after) if r["stage"] == "ran")
                > max(i for i, r in enumerate(after) if r["stage"] == "live")),
        },
        "stage_census": {
            stage: {
                "n": sum(1 for r in after if r["stage"] == stage),
                "featured": sum(1 for r in after
                                if r["stage"] == stage and r["featured"]),
            }
            for stage in head.STAGE_ORDER
            if any(r["stage"] == stage for r in after)
        },
    }

    OUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(json.dumps(results, indent=2, sort_keys=True))
    return results


if __name__ == "__main__":
    main()
