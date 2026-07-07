"""Run the expanded Signal Lab frontier Phase-0 admission screen.

This screen does not promote any signal. It decides which hypotheses have
enough data path, PIT treatment, sample, baseline, evidence, and incremental
intent to deserve a real empirical harness and Fable review.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.signal_frontier_docket import phase0_summary, screen_candidates
from lib import config


OUT_JSON = config.ROOT / "research" / "signal_lab_frontier_phase0_2026-07-06.json"
OUT_MD = config.ROOT / "research" / "SIGNAL_LAB_FRONTIER_PHASE0_2026-07-06.md"


VERDICT_LABELS = {
    "advance_to_fable": "ADVANCE TO FABLE",
    "local_phase0_ready": "LOCAL PHASE-0 READY",
    "data_contract_first": "DATA CONTRACT FIRST",
    "watchlist_or_reject": "WATCHLIST / REJECT",
    "graveyard_now": "GRAVEYARD NOW",
}


def _table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    lines = []
    lines.append("| " + " | ".join(label for label, _ in cols) + " |")
    lines.append("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        vals = []
        for _, key in cols:
            val = r.get(key, "")
            if isinstance(val, list):
                val = ", ".join(val)
            vals.append(str(val).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _write_markdown(rows: list[dict], summary: dict) -> None:
    fable = [r for r in rows if r["phase0_verdict"] == "advance_to_fable"]
    local = [r for r in rows if r["phase0_verdict"] == "local_phase0_ready"]
    data = [r for r in rows if r["phase0_verdict"] == "data_contract_first"]
    reject = [r for r in rows if r["phase0_verdict"] in {"watchlist_or_reject", "graveyard_now"}]

    lines = [
        "# Signal Lab expanded frontier Phase-0 - 2026-07-06",
        "",
        "This is the expanded docket behind `signal_lab.html`. It extends the initial",
        "10 frontier rows to 60 total candidates and runs the same admission screen",
        "over every candidate. The screen is intentionally pre-empirical: it does not",
        "claim rank-IC, HAC t-stat, FDR q, or Deflated Sharpe unless a real harness",
        "exists. Instead it decides which candidates deserve that expensive harness.",
        "",
        "No candidate below is promoted into Signal Lab. `ADVANCE TO FABLE` means the",
        "candidate survived the Phase-0 admission gates and is ready for Fable to",
        "challenge, confirm the data contract, and authorize a real validation run.",
        "",
        "## Verdict counts",
        "",
        f"- Total candidates screened: {summary['total']}",
        f"- Advance to Fable: {summary['advance_to_fable']}",
        f"- Local Phase-0 ready but not Fable-priority: {summary['local_phase0_ready']}",
        f"- Data contract first: {summary['data_contract_first']}",
        f"- Watchlist/reject: {summary['watchlist_or_reject']}",
        f"- Graveyard now: {summary['graveyard_now']}",
        "",
        "## Fable-ready survivors",
        "",
        _table(fable, [
            ("ID", "id"), ("Candidate", "name"), ("Market", "market"),
            ("Feature", "feature"), ("First empirical gate", "first_gate"),
            ("Baseline", "baseline"), ("Score", "score"),
        ]),
        "",
        "## Local Phase-0 queue",
        "",
        _table(local, [
            ("ID", "id"), ("Candidate", "name"), ("Why not Fable yet", "blockers"),
            ("First empirical gate", "first_gate"), ("Score", "score"),
        ]),
        "",
        "## Data-contract queue",
        "",
        _table(data, [
            ("ID", "id"), ("Candidate", "name"), ("Data path", "data_path"),
            ("Blockers", "blockers"), ("Source", "source"), ("Score", "score"),
        ]),
        "",
        "## Rejected / graveyard-now queue",
        "",
        _table(reject, [
            ("ID", "id"), ("Candidate", "name"), ("Verdict", "phase0_verdict"),
            ("Blockers", "blockers"), ("Reason note", "note"),
        ]),
        "",
        "## Full 60-candidate docket",
        "",
        _table(rows, [
            ("ID", "id"), ("Candidate", "name"), ("Family", "family"),
            ("Market", "market"), ("Data", "data_state"), ("PIT", "pit"),
            ("Years", "history_years"), ("Verdict", "phase0_verdict"),
            ("Source", "source"),
        ]),
        "",
        "## Source anchors",
        "",
    ]
    seen = set()
    for r in rows:
        url = r.get("source_url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        lines.append(f"- {r['source']}: {url}")
    lines.append("")
    OUT_MD.write_text("\n".join(lines))


def main() -> int:
    rows = screen_candidates()
    summary = phase0_summary(rows)
    # Timestamp goes ONLY in research/ outputs, never in build_scorecard/page JSON
    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload = {"generated_utc": generated_utc, "summary": summary, "candidates": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _write_markdown(rows, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
