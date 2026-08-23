"""Propose D5 program-ontology candidate rows for human review. Never writes
the canonical artifact and never mints `review_coverage[]` rows (freeze
SS3.2/SS3.1c -- curate is the ONLY producer of those).

Usage::

    python -m scripts.propose_government_program_ontology \
      --input raw_candidates.json --out-dir research/government_revenue/candidates/

Input is a JSON object whose keys are the same row-kind collections the
canonical contract carries (``programs``, ``capabilities``, ``platforms``,
``role_assertions``, ``milestones``, ``program_capability_links``,
``program_event_links``). Every admitted row is stamped ``verification_state:
proposed`` regardless of what the input claims; rows carrying forbidden
provenance (LLM/fuzzy/ticker-discovery, per the A7 LLM boundary, freeze
SS3.2) are rejected at the door with a ledger entry, never silently dropped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(_ROOT))

from engine.government_revenue import program_ontology as po  # noqa: E402
from scripts.curate_government_program_ontology import DEFAULT_TARGET  # noqa: E402


CANDIDATE_FILENAME = "program_ontology_candidate.json"

_CANDIDATE_COLLECTIONS = (
    "programs", "capabilities", "platforms", "role_assertions", "milestones",
    "program_capability_links", "program_event_links",
)

#: Collections a discovery-only proposal is structurally forbidden to emit
#: (freeze SS3.1c: curate is the only producer; freeze SS3.2: proposed rows
#: are never canonical audit facts).
_FORBIDDEN_OUTPUT_COLLECTIONS = ("review_coverage", "conflicts", "overrides")


class ProposalAuthorityError(RuntimeError):
    """Raised when a proposal input claims authority it can never hold."""


def guard_output_path(path: Path) -> Path:
    """Refuse any destination that is, or could be mistaken for, the
    canonical ontology artifact (mirrors the recipient-graph propose
    script's guard, freeze SS3.2's two-script pattern)."""
    resolved = path.resolve()
    if resolved == DEFAULT_TARGET.resolve() or resolved.name == DEFAULT_TARGET.name:
        raise ValueError(
            "this proposal tool never writes the canonical program ontology; "
            f"refusing {path}. Publish with "
            "scripts/curate_government_program_ontology.py instead."
        )
    return resolved


def _forbidden_keys(row: dict[str, Any]) -> set[str]:
    return set(row) & po.FORBIDDEN_INPUT_KEYS


def _forbidden_method(row: dict[str, Any]) -> bool:
    method = row.get("association_method")
    return isinstance(method, str) and method.casefold() in po.FORBIDDEN_ASSOCIATION_METHODS


def propose_candidates(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Stamp every row `proposed`, refuse forbidden provenance at the door,
    and refuse outright any attempt to emit an audit-only collection."""
    for forbidden_collection in _FORBIDDEN_OUTPUT_COLLECTIONS:
        value = raw_input.get(forbidden_collection)
        if value:
            raise ProposalAuthorityError(
                f"the propose script may never emit `{forbidden_collection}` rows; "
                "curate is the only producer of audit/coverage state"
            )

    candidate: dict[str, list[dict[str, Any]]] = {name: [] for name in _CANDIDATE_COLLECTIONS}
    rejection_ledger: list[dict[str, Any]] = []

    for collection in _CANDIDATE_COLLECTIONS:
        for row in raw_input.get(collection) or []:
            if not isinstance(row, dict):
                rejection_ledger.append({"collection": collection, "row": row, "reason": "malformed_row"})
                continue
            forbidden = _forbidden_keys(row)
            if forbidden:
                rejection_ledger.append({
                    "collection": collection, "row": row,
                    "reason": "forbidden_provenance_key_present",
                    "forbidden_keys": sorted(forbidden),
                })
                continue
            if _forbidden_method(row):
                rejection_ledger.append({
                    "collection": collection, "row": row, "reason": "forbidden_provenance_key_present",
                })
                continue
            proposed_row = dict(row)
            proposed_row["verification_state"] = po.PROPOSED_STATE
            candidate[collection].append(proposed_row)

    return {
        "contract": "government_program_ontology_candidate.v1",
        "schema_version": "1.0.0",
        "candidates": candidate,
        "rejection_ledger": rejection_ledger,
    }


def write_proposal(proposal: dict[str, Any], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    path = guard_output_path(out_dir / CANDIDATE_FILENAME)
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(proposal, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propose D5 program-ontology candidate rows. Never writes the canonical artifact."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    raw_input = json.loads(args.input.read_text(encoding="utf-8"))
    proposal = propose_candidates(raw_input)
    path = write_proposal(proposal, args.out_dir)
    print(
        f"proposed {sum(len(v) for v in proposal['candidates'].values())} candidate row(s), "
        f"{len(proposal['rejection_ledger'])} rejected -> {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
