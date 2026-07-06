"""scripts/build_research_factory_health.py — W2 health telemetry.

Computes research_factory.health.v1 rows (charter §5.5) from:
  data/research_factory/candidates.jsonl
  data/research_factory/transitions.jsonl
  data/research_factory/challenges/<candidate_id>.json  (absent-safe)
  data/research_factory/review/<candidate_id>.json|.md  (absent-safe)

Metrics:
  - funnel_counts: candidate count per state
  - kill_reason_histogram: {reason_code: n, kill_class: n}
  - challenger_divergence: advisory-vs-human-decision disagreement rate
    (rubber-stamp detector, §5.5)
  - median_dwell_days: median days spent in each state
  - respin_generation_histogram: {0: n, 1: n, 2: n}
  - source_acceptance_rates: per-source registered/(registered+deduped+schema_rejected)

Forward-ledger law (RF-8):
  Manual invocations default to --dry-run (print without writing).
  Only --write appends to data/research_factory/health.jsonl.
  Keep-first per (as_of) via ledger.py.

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §5.5, §6 W2.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory import ledger as rf_ledger
from engine.research_factory.schema import validate_health

DEFAULT_RF_DIR = ROOT / "data" / "research_factory"

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Strip trailing Z and parse
        s2 = s.rstrip("Z").split("+")[0]
        return datetime.fromisoformat(s2)
    except Exception:
        return None


def _days_between(a: str | None, b: str | None) -> float | None:
    da = _parse_iso(a)
    db = _parse_iso(b)
    if da is None or db is None:
        return None
    delta = abs((db - da).total_seconds()) / 86400.0
    return delta


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sv = sorted(values)
    n = len(sv)
    mid = n // 2
    if n % 2 == 0:
        return (sv[mid - 1] + sv[mid]) / 2.0
    return sv[mid]


# ---------------------------------------------------------------------------
# Challenger advisory vs human decision loader
# ---------------------------------------------------------------------------


def _load_challenges(challenges_dir: Path) -> dict[str, dict]:
    """Load challenge packets keyed by candidate_id.  Absent-safe."""
    result: dict[str, dict] = {}
    if not challenges_dir.exists():
        return result
    for fp in challenges_dir.glob("*.json"):
        try:
            row = json.loads(fp.read_text(encoding="utf-8"))
            cid = row.get("candidate_id")
            if cid:
                result[cid] = row
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_health(
    candidates: list[dict],
    transitions: list[dict],
    challenges: dict[str, dict] | None = None,
    as_of: str | None = None,
) -> dict:
    """Compute a research_factory.health.v1 dict from candidates + transitions.

    Parameters
    ----------
    candidates  : rows from candidates.jsonl (all, not keep-first'd; use latest status)
    transitions : rows from transitions.jsonl (append-only audit log)
    challenges  : mapping candidate_id -> challenge packet (absent-safe)
    as_of       : ISO timestamp for this health row (defaults to now)

    Returns
    -------
    dict  — health.v1 row ready for append_row()
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat()
    if challenges is None:
        challenges = {}

    # Resolve latest state per candidate_id from candidates.jsonl
    # (keep-first semantics: first occurrence in candidates.jsonl is canonical
    #  for the initial candidate; status field reflects current state)
    # We trust the candidates.jsonl status field as ground truth.
    latest_by_id: dict[str, dict] = {}
    for c in candidates:
        cid = c.get("candidate_id")
        if cid and cid not in latest_by_id:
            latest_by_id[cid] = c
    # Override status with most recent transition destination
    # (transitions are the ground truth for state)
    last_to_by_id: dict[str, str] = {}
    for t in transitions:
        cid = t.get("candidate_id")
        if cid:
            last_to_by_id[cid] = t.get("to", "")
    for cid, c in latest_by_id.items():
        if cid in last_to_by_id:
            c = dict(c)
            c["status"] = last_to_by_id[cid]
            latest_by_id[cid] = c

    all_candidates = list(latest_by_id.values())

    # ----------------------------------------------------------------
    # 1. Funnel counts per state
    # ----------------------------------------------------------------
    funnel_counts: dict[str, int] = defaultdict(int)
    for c in all_candidates:
        state = c.get("status") or "unknown"
        funnel_counts[state] += 1

    # ----------------------------------------------------------------
    # 2. Kill-reason histogram (reason_code + kill_class)
    # ----------------------------------------------------------------
    reason_code_hist: dict[str, int] = defaultdict(int)
    kill_class_hist: dict[str, int] = defaultdict(int)

    terminal_kill_states = {"schema_rejected", "deduped", "numeric_rejected", "rejected", "retired"}
    for t in transitions:
        if t.get("to") in terminal_kill_states:
            rc = t.get("reason_code") or "unknown"
            reason_code_hist[rc] += 1
            ke = t.get("kill_evidence")
            if isinstance(ke, dict):
                kc = ke.get("kill_class")
                if kc:
                    kill_class_hist[kc] += 1

    # ----------------------------------------------------------------
    # 3. Challenger advisory vs human decision divergence
    # ----------------------------------------------------------------
    # For candidates that went through challenged -> human_review -> {paper/rejected/...}
    # we compare the reviewer's ADVISORY_* recommendation with the human decision.
    total_adjudicated = 0
    advisor_human_diverge = 0

    # Build: candidate_id -> set of human decisions (transitions from human_review)
    human_decisions: dict[str, list[str]] = defaultdict(list)
    for t in transitions:
        if t.get("from") == "human_review":
            cid = t.get("candidate_id", "")
            human_decisions[cid].append(t.get("to", ""))

    for cid, challenge_packet in challenges.items():
        reviewer = challenge_packet.get("reviewer") or {}
        advisory = reviewer.get("recommendation", "")
        decisions = human_decisions.get(cid, [])
        if not advisory or not decisions:
            continue
        total_adjudicated += 1
        # ADVISORY_REJECT -> expected human decision: 'rejected'
        # ADVISORY_PASS / ADVISORY_REVIEW -> expected: paper/deferred/scoped_build
        human_reject = any(d == "rejected" for d in decisions)
        if advisory == "ADVISORY_REJECT" and not human_reject:
            advisor_human_diverge += 1
        elif advisory in ("ADVISORY_PASS", "ADVISORY_REVIEW") and human_reject:
            advisor_human_diverge += 1

    divergence_rate = (
        advisor_human_diverge / total_adjudicated if total_adjudicated > 0 else None
    )

    # ----------------------------------------------------------------
    # 4. Median dwell days per state
    # ----------------------------------------------------------------
    # Group transitions by candidate; for each (from_state), measure time to next transition.
    # Build per-candidate ordered transitions.
    by_candidate: dict[str, list[dict]] = defaultdict(list)
    for t in transitions:
        cid = t.get("candidate_id", "")
        if cid:
            by_candidate[cid].append(t)

    state_dwells: dict[str, list[float]] = defaultdict(list)
    for cid, ts_list in by_candidate.items():
        # Sort by as_of
        ts_sorted = sorted(ts_list, key=lambda x: x.get("as_of", ""))
        for i in range(len(ts_sorted) - 1):
            curr = ts_sorted[i]
            nxt = ts_sorted[i + 1]
            state = curr.get("to", "")
            if not state:
                continue
            dwell = _days_between(curr.get("as_of"), nxt.get("as_of"))
            if dwell is not None:
                state_dwells[state].append(dwell)

    median_dwell_days: dict[str, float | None] = {
        state: _median(dwells) for state, dwells in state_dwells.items()
    }

    # ----------------------------------------------------------------
    # 5. Respin-generation histogram
    # ----------------------------------------------------------------
    gen_hist: dict[str, int] = defaultdict(int)
    for c in all_candidates:
        lineage = c.get("lineage") or {}
        gen = lineage.get("refinement_generation", 0)
        gen_hist[str(gen)] += 1

    # ----------------------------------------------------------------
    # 6. Per-source acceptance rates
    # ----------------------------------------------------------------
    # accepted = reached 'registered' or beyond (not deduped / schema_rejected)
    # total = all candidates from that source
    source_total: dict[str, int] = defaultdict(int)
    source_accepted: dict[str, int] = defaultdict(int)
    rejected_states = {"schema_rejected", "deduped"}
    for c in all_candidates:
        src = c.get("source") or "unknown"
        source_total[src] += 1
        state = c.get("status") or ""
        if state not in rejected_states:
            source_accepted[src] += 1

    source_acceptance_rates: dict[str, dict] = {}
    for src, total in source_total.items():
        accepted = source_accepted.get(src, 0)
        source_acceptance_rates[src] = {
            "total": total,
            "accepted": accepted,
            "rate": round(accepted / total, 4) if total > 0 else None,
        }

    # ----------------------------------------------------------------
    # Build health row
    # ----------------------------------------------------------------
    health_row: dict = {
        "schema": "research_factory.health.v1",
        "authority": "display_only",
        "as_of": as_of,
        "total_candidates": len(all_candidates),
        "funnel_counts": dict(funnel_counts),
        "kill_reason_histogram": {
            "by_reason_code": dict(reason_code_hist),
            "by_kill_class": dict(kill_class_hist),
        },
        "challenger_divergence": {
            "total_adjudicated": total_adjudicated,
            "advisor_human_diverge": advisor_human_diverge,
            "divergence_rate": divergence_rate,
            "note": (
                "advisory-vs-human mismatch rate (rubber-stamp detector); "
                "None if no adjudicated candidates yet"
            ),
        },
        "median_dwell_days_by_state": {
            k: (round(v, 2) if v is not None else None)
            for k, v in median_dwell_days.items()
        },
        "respin_generation_histogram": dict(gen_hist),
        "source_acceptance_rates": source_acceptance_rates,
    }

    return health_row


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--rf-dir", type=Path, default=None,
                    help="Override data/research_factory/ dir")
    ap.add_argument("--as-of", default=None,
                    help="ISO timestamp override for this health row")
    # Forward-ledger law: default is --dry-run; --write appends
    ap.add_argument("--write", action="store_true", default=False,
                    help="Append to health.jsonl (default: dry-run only)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Print without writing (default behavior; explicit flag for clarity)")
    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()
    dry_run = not args.write

    rf_dir = args.rf_dir or DEFAULT_RF_DIR

    candidates_path = rf_dir / "candidates.jsonl"
    transitions_path = rf_dir / "transitions.jsonl"
    challenges_dir = rf_dir / "challenges"
    health_path = rf_dir / "health.jsonl"

    # Load inputs (all absent-safe)
    candidates = rf_ledger.load_jsonl(candidates_path)
    transitions = rf_ledger.load_jsonl(transitions_path)
    challenges = _load_challenges(challenges_dir)

    print(f"Loaded: {len(candidates)} candidates, {len(transitions)} transitions, "
          f"{len(challenges)} challenge packets")

    as_of = args.as_of or datetime.now(timezone.utc).isoformat()
    health_row = compute_health(
        candidates=candidates,
        transitions=transitions,
        challenges=challenges,
        as_of=as_of,
    )

    # Validate
    errs = validate_health(health_row)
    if errs:
        print(f"[ERROR] health row failed validation: {errs}", file=sys.stderr)
        return 1

    # Print
    print(f"\nresearch_factory.health.v1 as_of={as_of}")
    print(f"  total_candidates: {health_row['total_candidates']}")
    print(f"  funnel_counts: {json.dumps(health_row['funnel_counts'], sort_keys=True)}")
    print(f"  kill_reason_histogram: {json.dumps(health_row['kill_reason_histogram'])}")
    chd = health_row["challenger_divergence"]
    print(f"  challenger_divergence: adjudicated={chd['total_adjudicated']} "
          f"diverged={chd['advisor_human_diverge']} "
          f"rate={chd['divergence_rate']}")
    print(f"  respin_generation_histogram: {json.dumps(health_row['respin_generation_histogram'])}")
    print(f"  source_acceptance_rates: {json.dumps(health_row['source_acceptance_rates'])}")

    if dry_run:
        print("\n[DRY-RUN] Not writing to disk. Use --write to append.")
        return 0

    # Keep-first per as_of (RF-8)
    existing = rf_ledger.load_forward_ledger(health_path, key_fields=("as_of",))
    existing_as_ofs = {r.get("as_of") for r in existing}
    if as_of in existing_as_ofs:
        print(f"[SKIP] as_of={as_of!r} already in health.jsonl (keep-first). Nothing written.")
        return 0

    rf_ledger.append_row(health_path, health_row, validate_fn=validate_health)
    print(f"Appended health row to {health_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
