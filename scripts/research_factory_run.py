"""Research Factory Domain Runner (W3, RF-2/RF-6/RF-13).

Orchestrates:
  1. Load candidates from data/research_factory/candidates.jsonl
  2. Filter to 'registered' state
  3. Route each candidate to its domain adapter based on source/candidate_type
  4. Attach artifact refs returned by the adapter
  5. Transition via state.py (screened / numeric_rejected / awaiting_data)
     — only transitions that are legal per the state machine

Modes
-----
--dry-run (DEFAULT)
    Lists exactly what would run per candidate.  Writes NOTHING to disk.

--execute
    Performs transitions via ledger.py.  Writes transition rows.

--count
    Additionally allows counted 63d oracle screens (off by default per RF-13).
    Implies --execute.

Usage
-----
  python scripts/research_factory_run.py --dry-run
  python scripts/research_factory_run.py --execute
  python scripts/research_factory_run.py --execute --count

House laws:
  - Default is --dry-run; --execute must be explicit.
  - --count additionally arms 63d oracle screens; off by default (RF-13).
  - The runner NEVER advances forward ledgers (paper_monitor, health) —
    those are nightly-only (RF-8).
  - Every transition row carries authority='display_only' (RF-11).
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("research_factory_run")


# ---------------------------------------------------------------------------
# Candidate loader
# ---------------------------------------------------------------------------

def load_candidates(rf_dir: Path) -> list[dict]:
    """Load data/research_factory/candidates.jsonl absent-safely."""
    from engine.research_factory.ledger import load_jsonl
    return load_jsonl(rf_dir / "candidates.jsonl")


def filter_registered(candidates: list[dict]) -> list[dict]:
    """Return only candidates in 'registered' state."""
    return [c for c in candidates if c.get("status") == "registered"]


# ---------------------------------------------------------------------------
# Domain router
# ---------------------------------------------------------------------------

def _route_candidate(
    candidate: dict,
    *,
    data_dir: Path,
    count: bool,
) -> dict:
    """Route one registered candidate to its domain adapter.

    Returns a routing result dict with keys:
      candidate_id, source, domain, adapter_result, action, reason
    where action ∈ {'transition_screened', 'transition_numeric_rejected',
                    'transition_awaiting_data', 'no_action', 'error'}
    """
    cid = candidate.get("candidate_id", "?")
    source = candidate.get("source", "")
    domain = candidate.get("domain", "")
    ctype = candidate.get("candidate_type", "")

    result: dict[str, Any] = {
        "candidate_id": cid,
        "source": source,
        "domain": domain,
        "candidate_type": ctype,
        "adapter_result": None,
        "action": "no_action",
        "reason": "",
    }

    # --- Oracle domain ---
    if source == "oracle_brainstorm" or domain == "oracle" or ctype == "oracle_compound":
        from engine.research_factory.adapter_oracle import (
            load_oracle_registry,
            route_compound,
        )
        spec_ref = candidate.get("spec_ref")
        if not spec_ref:
            result["action"] = "error"
            result["reason"] = "oracle candidate missing spec_ref (compound_id)"
            return result

        # Find the compound in the registry
        registry = load_oracle_registry(data_dir)
        compound = next((c for c in registry if c.get("id") == spec_ref), None)
        if compound is None:
            result["action"] = "awaiting_data"
            result["reason"] = (
                f"oracle compound {spec_ref!r} not found in registry "
                f"— awaiting data"
            )
            result["adapter_result"] = {"spec_ref": spec_ref, "found": False}
            return result

        adapter_result = route_compound(compound, data_dir=data_dir, count=count)
        result["adapter_result"] = adapter_result
        projected = adapter_result.get("projected_state", "registered")
        re_refused = adapter_result.get("re_screen_refused", False)

        if re_refused:
            result["action"] = "no_action"
            result["reason"] = (
                f"oracle 63d re-screen refused (compound already screened per RF-13); "
                f"projected={projected!r}"
            )
        elif projected == "screened":
            result["action"] = "transition_screened"
            result["reason"] = (
                f"oracle compound {spec_ref!r} projected as screened "
                f"(domain_status={adapter_result.get('domain_status')!r})"
            )
        elif projected == "numeric_rejected":
            result["action"] = "transition_numeric_rejected"
            result["reason"] = (
                f"oracle compound {spec_ref!r} projected as numeric_rejected "
                f"(domain_status={adapter_result.get('domain_status')!r})"
            )
        elif projected == "awaiting_data":
            result["action"] = "transition_awaiting_data"
            result["reason"] = (
                f"oracle compound {spec_ref!r} has blocked_missing_column "
                f"— awaiting data"
            )
        elif projected == "paper":
            result["action"] = "no_action"
            result["reason"] = (
                f"oracle compound {spec_ref!r} projected as paper (accruing) "
                f"— paper transition requires human actor (RF-5); no auto-action"
            )
        elif projected == "promote_eligible":
            result["action"] = "no_action"
            result["reason"] = (
                f"oracle compound {spec_ref!r} projected as promote_eligible "
                f"(promoted) — requires human gate decision (RF-5)"
            )
        else:
            result["action"] = "no_action"
            result["reason"] = f"projected state {projected!r} requires no auto-action"
        return result

    # --- Cortex domain ---
    if source == "cortex" or domain == "neuralweb" or ctype == "cortex_hypothesis":
        from engine.research_factory.adapter_cortex import route_hypothesis
        spec_ref = candidate.get("spec_ref")
        if not spec_ref:
            result["action"] = "error"
            result["reason"] = "cortex candidate missing spec_ref (metabolism id)"
            return result

        # Build a minimal hypothesis dict from candidate fields for routing
        hyp = {
            "id": spec_ref,
            "registered_at": candidate.get("created_at"),
            "status": candidate.get("status"),
            "spine_query": candidate.get("artifacts", {}).get("spine_query"),
            "pre_committed_gate": candidate.get("artifacts", {}).get("pre_committed_gate"),
        }
        adapter_result = route_hypothesis(hyp, data_dir=data_dir)
        result["adapter_result"] = adapter_result
        result["action"] = "no_action"
        result["reason"] = (
            "cortex adapter: pointer/projection only; no auto-transition "
            f"(self_ref_excluded={adapter_result.get('self_ref_excluded')})"
        )
        return result

    # --- Alpha grammar domain ---
    if source == "alpha_grammar" or ctype == "alpha_family":
        from engine.research_factory.adapter_alpha_grammar import route_all
        family_results = route_all(data_dir)
        spec_ref = candidate.get("spec_ref") or candidate.get("candidate_id")
        # Find matching family
        fam_result = next(
            (r for r in family_results if r.get("family") == spec_ref
             or r.get("spec_ref") == spec_ref),
            None,
        )
        result["adapter_result"] = fam_result or {
            "note": "family not found in alpha_candidates.parquet survivors"
        }
        result["action"] = "no_action"
        result["reason"] = (
            "alpha_grammar adapter: read-only; no auto-transition "
            f"(n_survivors={fam_result.get('n_survivors') if fam_result else 0})"
        )
        return result

    # Unrecognised domain/source
    result["action"] = "no_action"
    result["reason"] = (
        f"unrecognised domain/source combination: "
        f"source={source!r}, domain={domain!r}, candidate_type={ctype!r}"
    )
    return result


# ---------------------------------------------------------------------------
# Transition performer
# ---------------------------------------------------------------------------

def _build_transition_row(
    candidate: dict,
    to_state: str,
    routing: dict,
    *,
    as_of: str,
) -> dict:
    """Build a transition.v1 row for ledger.append_row."""
    cid = candidate.get("candidate_id", "?")
    from_state = candidate.get("status", "registered")
    adapter_result = routing.get("adapter_result") or {}

    row: dict[str, Any] = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "from": from_state,
        "to": to_state,
        "reason_code": routing.get("action", "no_action"),
        "reason_text": routing.get("reason", ""),
        "actor": "script",
        "actor_ref": None,
        "as_of": as_of,
        "artifact_refs": [],
        "kill_evidence": None,
        "come_back_on": None,
    }

    # Attach artifact_refs from adapter
    art = adapter_result.get("artifact")
    if art:
        row["artifact_refs"] = [art]

    # For numeric_rejected: attach kill_evidence (RF-10)
    if to_state == "numeric_rejected":
        ke = adapter_result.get("kill_evidence")
        if ke:
            row["kill_evidence"] = ke
        else:
            # Provide minimal kill_evidence if adapter did not
            row["kill_evidence"] = {
                "n_at_kill": 0,
                "kill_class": "falsified",
                "mde_at_n": None,
                "regime_split": None,
            }

    # For awaiting_data: require come_back_on (RF-4)
    if to_state == "awaiting_data":
        # Default come_back_on = 90 days from now
        import datetime as _dt
        come_back = _dt.date.today() + _dt.timedelta(days=90)
        row["come_back_on"] = come_back.isoformat()

    return row


def _perform_transition(
    candidate: dict,
    to_state: str,
    routing: dict,
    *,
    rf_dir: Path,
    as_of: str,
    dry_run: bool,
) -> bool:
    """Validate and optionally write a transition row.

    Returns True on success (or dry-run), False on validation error.
    """
    from engine.research_factory.state import transition, IllegalTransition
    from engine.research_factory.ledger import append_row
    from engine.research_factory.schema import validate_transition

    from_state = candidate.get("status", "registered")
    transition_row = _build_transition_row(
        candidate, to_state, routing, as_of=as_of
    )

    # Validate state machine
    try:
        transition(
            from_state=from_state,
            to_state=to_state,
            actor="script",
            transition_row=transition_row,
            candidate=candidate,
        )
    except IllegalTransition as exc:
        log.error(
            "_perform_transition: illegal transition %s→%s for %s: %s",
            from_state, to_state, candidate.get("candidate_id"), exc,
        )
        return False

    if dry_run:
        log.info(
            "[DRY-RUN] would transition %s: %s → %s",
            candidate.get("candidate_id"), from_state, to_state,
        )
        return True

    try:
        append_row(
            rf_dir / "transitions.jsonl",
            transition_row,
            validate_fn=validate_transition,
        )
        log.info(
            "Transitioned %s: %s → %s",
            candidate.get("candidate_id"), from_state, to_state,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.error(
            "_perform_transition: append_row failed for %s: %s",
            candidate.get("candidate_id"), exc,
        )
        return False


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    *,
    rf_dir: Path,
    data_dir: Path,
    dry_run: bool = True,
    count: bool = False,
) -> dict:
    """Main runner.  Returns a summary dict."""
    as_of = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    candidates = load_candidates(rf_dir)
    registered = filter_registered(candidates)
    log.info(
        "Loaded %d candidates; %d in 'registered' state",
        len(candidates), len(registered),
    )

    if dry_run:
        log.info("Mode: DRY-RUN — no writes to disk")
    else:
        log.info("Mode: EXECUTE%s", " + COUNT (63d oracle screens allowed)" if count else "")

    summary: dict[str, Any] = {
        "n_candidates": len(candidates),
        "n_registered": len(registered),
        "dry_run": dry_run,
        "count": count,
        "as_of": as_of,
        "routes": [],
        "transitions_attempted": 0,
        "transitions_ok": 0,
    }

    for candidate in registered:
        cid = candidate.get("candidate_id", "?")
        log.info("Processing candidate: %s (source=%s)", cid, candidate.get("source"))

        routing = _route_candidate(candidate, data_dir=data_dir, count=count)
        action = routing.get("action", "no_action")
        reason = routing.get("reason", "")
        adapter_result = routing.get("adapter_result")

        route_entry: dict[str, Any] = {
            "candidate_id": cid,
            "source": routing.get("source"),
            "domain": routing.get("domain"),
            "action": action,
            "reason": reason,
            "track": (
                adapter_result.get("track") if adapter_result else None
            ),
            "projected_state": (
                adapter_result.get("projected_state") if adapter_result else None
            ),
            "transition_ok": None,
        }

        # Determine target state from action
        to_state_map = {
            "transition_screened": "screened",
            "transition_numeric_rejected": "numeric_rejected",
            "transition_awaiting_data": "awaiting_data",
        }
        to_state = to_state_map.get(action)

        if dry_run:
            # Just describe what would happen
            print(
                f"  [{cid}] source={routing.get('source')!r} "
                f"domain={routing.get('domain')!r} "
                f"action={action!r} "
                f"would_transition_to={to_state!r} "
                f"track={route_entry.get('track')!r}"
            )
            print(f"    reason: {reason}")
        else:
            if to_state:
                summary["transitions_attempted"] += 1
                ok = _perform_transition(
                    candidate, to_state, routing,
                    rf_dir=rf_dir,
                    as_of=as_of,
                    dry_run=False,
                )
                route_entry["transition_ok"] = ok
                if ok:
                    summary["transitions_ok"] += 1
            else:
                log.info("  [%s] no-action: %s", cid, reason)

        summary["routes"].append(route_entry)

    log.info(
        "Done. %d registered candidates processed. "
        "transitions_attempted=%d transitions_ok=%d",
        len(registered),
        summary["transitions_attempted"],
        summary["transitions_ok"],
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Research Factory domain runner (W3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="List what would run per candidate without writing (DEFAULT)",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Perform transitions (write to disk). Overrides --dry-run.",
    )
    ap.add_argument(
        "--count",
        action="store_true",
        default=False,
        help=(
            "Allow counted 63d oracle screens (off by default per RF-13). "
            "Implies --execute."
        ),
    )
    ap.add_argument(
        "--data-dir",
        default="data",
        help="Root data directory (default: data/)",
    )
    ap.add_argument(
        "--rf-dir",
        default=None,
        help="Research factory data dir (default: <data-dir>/research_factory/)",
    )
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    rf_dir = Path(args.rf_dir) if args.rf_dir else data_dir / "research_factory"

    # --count implies --execute
    dry_run = not (args.execute or args.count)

    summary = run(
        rf_dir=rf_dir,
        data_dir=data_dir,
        dry_run=dry_run,
        count=args.count,
    )

    if dry_run:
        print("\n[DRY-RUN] No writes performed.")
    else:
        print(
            f"\nDone. transitions_ok={summary['transitions_ok']} / "
            f"transitions_attempted={summary['transitions_attempted']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
