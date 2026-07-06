"""scripts/build_research_factory_review_queue.py — W5 queue builder CLI.

Emits:
  data/research_factory/review/queue.json   — machine-readable packet list
  data/research_factory/review/queue.md     — human-readable, one section per
                                              candidate, decision block template
                                              at the end of each section

Display-only wording throughout. Never emits the word 'validated' in any text.

Forward-ledger law (RF-8):
  Default: --dry-run (print without writing).
  Use --write to emit to disk.

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §6 W5,
rulings RF-5, RF-9, RF-12, RF-16.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory.review_queue import build_queue, DEFAULT_RF_DIR

# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

_DECISION_BLOCK_TEMPLATE = """\
### Decision block

**Candidate:** `{candidate_id}`
**Allowed decisions:** paper | deferred | rejected | scoped_build

**Decision question:**
> {decision_question}

**To record a decision, run:**
```
python scripts/research_factory_decide.py \\
  --candidate {candidate_id} \\
  --decision <paper|deferred|rejected|scoped_build> \\
  --actor <fable|operator> \\
  --actor-ref <session/PR ref> \\
  [--expected-half-life-d <N>]        # required for paper \\
  [--come-back-on YYYY-MM-DD]         # required for deferred \\
  [--kill-class <class>]              # required for rejected/retired \\
  [--program-doc research/<NAME>_BY_FABLE.md]  # required for scoped_build
```
"""


def _render_metric_line(k: str, v: object) -> str:
    if isinstance(v, float):
        return f"  - **{k}**: {v:.4f}"
    return f"  - **{k}**: {v}"


def _render_blocker(b: dict) -> str:
    sev = b.get("severity", "?")
    cat = b.get("category", "?")
    finding = b.get("finding", "")
    return f"  - [{sev}/{cat}] {finding}"


def render_markdown(packets: list[dict], generated_at: str) -> str:
    """Render the full queue.md document.

    Sections:
      1. Active Queue — human_review and paper-decay candidates (decidable or near-decidable)
      2. Blocked — awaiting_data candidates (blocked on data/label/grader availability)
    """
    # Split packets into active and blocked
    active_packets = [p for p in packets if not p.get("is_awaiting_data")]
    blocked_packets = [p for p in packets if p.get("is_awaiting_data")]

    lines: list[str] = []
    lines.append("# Research Factory — Human Review Queue")
    lines.append("")
    lines.append(f"*Generated: {generated_at}*")
    lines.append(f"*Candidates awaiting decision: {len(active_packets)}*")
    lines.append(f"*Blocked (awaiting_data): {len(blocked_packets)}*")
    lines.append("")
    lines.append(
        "> **Display-only context.** All metrics are aggregate, frozen-gate outputs "
        "from the domain evaluator. This queue provides context for the human decision "
        "only; it does not score, rank by merit, or originate any signal."
    )
    lines.append("")

    if not packets:
        lines.append("*No candidates currently in human_review, flagged for decay review, or blocked.*")
        lines.append("")
        return "\n".join(lines)

    # ---- Active Queue section ----
    lines.append("## Active Queue")
    lines.append("")
    if not active_packets:
        lines.append("*No candidates currently in human_review or flagged for decay review.*")
        lines.append("")
    else:
        for i, pkt in enumerate(active_packets, 1):
            _render_packet(lines, i, pkt)

    # ---- Blocked section ----
    lines.append("---")
    lines.append("")
    lines.append("## Blocked")
    lines.append("")
    lines.append(
        "> **Blocked candidates** are in `awaiting_data` state — blocked on data, label, or "
        "grader availability. No decide command is runnable. Each entry shows its "
        "`come_back_on` clock."
    )
    lines.append("")
    if not blocked_packets:
        lines.append("*No candidates currently blocked.*")
        lines.append("")
    else:
        for i, pkt in enumerate(blocked_packets, 1):
            _render_blocked_packet(lines, i, pkt)

    return "\n".join(lines)


def _render_packet(lines: list[str], i: int, pkt: dict) -> None:
    """Render one active-queue packet into lines (mutates lines in place)."""
    cid = pkt.get("candidate_id", "?")
    ctype = pkt.get("candidate_type", "?")
    domain = pkt.get("domain", "?")
    status = pkt.get("current_status", "?")
    source = pkt.get("source", "?")
    track = pkt.get("track") or "—"

    lines.append(f"---")
    lines.append("")
    lines.append(f"## {i}. {cid}")
    lines.append("")
    lines.append(f"**Type:** {ctype} | **Domain:** {domain} | "
                 f"**Status:** {status} | **Source:** {source} | **Track:** {track}")
    lines.append("")

    # Hypothesis + mechanism
    hyp = pkt.get("hypothesis") or "—"
    mech = pkt.get("mechanism") or "—"
    lines.append("### Hypothesis")
    lines.append(f"> {hyp}")
    lines.append("")
    lines.append("### Mechanism")
    lines.append(f"> {mech}")
    lines.append("")

    # Frozen-gate metrics
    metrics = pkt.get("frozen_gate_metrics") or {}
    if metrics:
        lines.append("### Frozen-gate metrics (display only)")
        for k, v in metrics.items():
            lines.append(_render_metric_line(k, v))
        lines.append("")

    # search_width_at_scan (oracle only — REQUIRED)
    sw = pkt.get("search_width_at_scan")
    if sw is not None:
        if sw == "MISSING":
            lines.append("### Search width at scan")
            lines.append("**WARNING: search_width_at_scan is MISSING — "
                          "required for oracle candidates (charter §6 W3/W5)**")
            lines.append("")
        else:
            lines.append("### Search width at scan")
            lines.append(f"  {sw}")
            lines.append("")

    # Probe flags
    flags = pkt.get("probe_flags") or {}
    if flags:
        lines.append("### Mechanical probe flags")
        for k, v in flags.items():
            lines.append(f"  - **{k}**: {v}")
        lines.append("")

    # Reviewer blockers
    blockers = pkt.get("reviewer_blockers") or []
    if blockers:
        lines.append("### Reviewer blockers (advisory only)")
        for b in blockers:
            lines.append(_render_blocker(b))
        lines.append("")

    # Best counterargument
    bca = pkt.get("best_counterargument")
    if bca:
        lines.append("### Best counterargument (advisory)")
        lines.append(f"> {bca}")
        lines.append("")

    # Crowding context (RF-16 — context only, no composite)
    crowds = pkt.get("crowds_with") or []
    if crowds:
        lines.append("### Crowding context (display only — not a rank)")
        lines.append(
            "*Other non-terminal candidates sharing entry-rule column overlap "
            "or same alpha cluster. Context only; RF-16 forbids composite ranking.*"
        )
        for c in crowds:
            other_id = c.get("candidate_id", "?")
            other_status = c.get("status", "?")
            overlap = c.get("overlap_columns") or []
            cluster_match = c.get("same_alpha_cluster", False)
            overlap_str = ", ".join(overlap) if overlap else "—"
            cluster_str = " (same alpha cluster)" if cluster_match else ""
            lines.append(
                f"  - `{other_id}` (status={other_status}) "
                f"overlap_cols=[{overlap_str}]{cluster_str}"
            )
        lines.append("")

    # Human review question
    hrq = pkt.get("human_review_question")
    if hrq:
        lines.append("### Human review question")
        lines.append(f"> {hrq}")
        lines.append("")

    # Decision block template
    dec_q = pkt.get("decision_question") or "See human_review_question above."
    lines.append(
        _DECISION_BLOCK_TEMPLATE.format(
            candidate_id=cid,
            decision_question=dec_q,
        )
    )
    lines.append("")


def _render_blocked_packet(lines: list[str], i: int, pkt: dict) -> None:
    """Render one blocked (awaiting_data) packet into lines (mutates lines in place)."""
    cid = pkt.get("candidate_id", "?")
    ctype = pkt.get("candidate_type", "?")
    domain = pkt.get("domain", "?")
    source = pkt.get("source", "?")
    come_back_on = pkt.get("come_back_on") or "not set"

    lines.append(f"---")
    lines.append("")
    lines.append(f"### B{i}. {cid}")
    lines.append("")
    lines.append(
        f"**Type:** {ctype} | **Domain:** {domain} | **Source:** {source} | "
        f"**Status:** awaiting_data | **come_back_on:** {come_back_on}"
    )
    lines.append("")

    hyp = pkt.get("hypothesis") or "—"
    mech = pkt.get("mechanism") or "—"
    lines.append("#### Hypothesis")
    lines.append(f"> {hyp}")
    lines.append("")
    lines.append("#### Mechanism")
    lines.append(f"> {mech}")
    lines.append("")

    note = pkt.get("note") or ""
    lines.append(f"*{note}*")
    lines.append("")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--rf-dir", type=Path, default=None,
        help="Override data/research_factory/ dir (default: data/research_factory/)",
    )
    ap.add_argument(
        "--write", action="store_true", default=False,
        help="Write queue.json + queue.md to disk (default: dry-run only)",
    )
    ap.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print summary without writing (default behaviour; explicit flag for clarity)",
    )
    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()
    dry_run = not args.write

    rf_dir = args.rf_dir or DEFAULT_RF_DIR

    packets = build_queue(rf_dir=rf_dir)

    generated_at = datetime.now(timezone.utc).isoformat()

    active_packets = [p for p in packets if not p.get("is_awaiting_data")]
    blocked_packets = [p for p in packets if p.get("is_awaiting_data")]

    # Build JSON payload
    queue_json: dict = {
        "schema": "research_factory.review_queue.v1",
        "authority": "display_only",
        "generated_at": generated_at,
        "n_candidates": len(active_packets),
        "n_blocked": len(blocked_packets),
        "candidates": packets,
        "note": (
            "Cross-domain review queue. Active = human_review + paper-decay; "
            "Blocked = awaiting_data (blocked on data/label/grader). "
            "Ordered by candidate_type bin then created_at. "
            "RF-16: crowds_with is context only — no composite ranking. "
            "All metrics are display-only."
        ),
    }

    # Build Markdown
    queue_md = render_markdown(packets, generated_at)

    # Print summary
    print(f"Review queue: {len(active_packets)} active, {len(blocked_packets)} blocked")
    for p in active_packets:
        sw = p.get("search_width_at_scan")
        sw_str = f" [search_width={sw}]" if sw is not None else ""
        print(
            f"  [active] {p.get('candidate_id','?')} "
            f"({p.get('candidate_type','?')}/{p.get('domain','?')}, "
            f"status={p.get('current_status','?')})"
            f"{sw_str}"
        )
    for p in blocked_packets:
        cbo = p.get("come_back_on") or "not set"
        print(
            f"  [blocked] {p.get('candidate_id','?')} "
            f"({p.get('candidate_type','?')}/{p.get('domain','?')}) "
            f"come_back_on={cbo}"
        )

    if dry_run:
        print(f"\n[DRY-RUN] Generated {len(active_packets)} active + "
              f"{len(blocked_packets)} blocked packet(s). Use --write to emit to disk.")
        return 0

    # Write outputs
    review_dir = rf_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    json_path = review_dir / "queue.json"
    md_path = review_dir / "queue.md"

    json_path.write_text(
        json.dumps(queue_json, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(queue_md, encoding="utf-8")

    print(f"\nWrote: {json_path}")
    print(f"Wrote: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
