"""CLI: emit / ingest challenge packets for the research factory (W4, RF-7/RF-16).

Two modes:
  --candidate <id>           : Emit the challenge input packet (stdout + file).
  --ingest-response <path>   : Validate + write + transition a reviewer response.

IMPORTANT — RF-16: This script NEVER invokes an LLM itself.  The operator or
Fable runs the Opus reviewer agent out-of-band; the response JSON is then fed
back via --ingest-response.

A governance event 'research_factory_challenge' (article: null) is emitted on
a successful challenge write per RF-12.

Usage:
  python -m scripts.research_factory_challenge_pack --candidate rf-20260706-abc \\
      [--data-dir /path/to/data] [--out-dir /path/to/challenges]

  python -m scripts.research_factory_challenge_pack \\
      --ingest-response /tmp/reviewer_response.json \\
      [--data-dir /path/to/data]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory.challenge import (
    build_challenge_input,
    validate_reviewer_response,
    write_challenge,
    apply_challenge_transitions,
)
from engine.research_factory.ledger import load_jsonl, DEFAULT_RF_DIR


# ---------------------------------------------------------------------------
# Candidate lookup
# ---------------------------------------------------------------------------

def _load_candidate(candidate_id: str, data_dir: Path) -> dict | None:
    """Load a candidate row from candidates.jsonl by candidate_id."""
    candidates_path = data_dir / "research_factory" / "candidates.jsonl"
    rows = load_jsonl(candidates_path)
    for row in rows:
        if row.get("candidate_id") == candidate_id:
            return row
    return None


# ---------------------------------------------------------------------------
# Mode 1: --candidate
# ---------------------------------------------------------------------------

def _cmd_candidate(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir) if args.data_dir else Path("data")
    root = data_dir.parent

    candidate_id = args.candidate
    candidate = _load_candidate(candidate_id, data_dir)
    if candidate is None:
        print(
            f"ERROR: candidate_id {candidate_id!r} not found in "
            f"{data_dir / 'research_factory' / 'candidates.jsonl'}",
            file=sys.stderr,
        )
        return 1

    packet = build_challenge_input(candidate, root=root)

    # Stdout
    print(json.dumps(packet, indent=2, default=str))

    # File output
    out_dir = Path(args.out_dir) if args.out_dir else (
        data_dir / "research_factory" / "challenges"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{candidate_id}.challenge_input.json"
    out_path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    print(f"\n# Challenge input written to: {out_path}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Mode 2: --ingest-response
# ---------------------------------------------------------------------------

def _cmd_ingest_response(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir) if args.data_dir else Path("data")
    root = data_dir.parent
    response_path = Path(args.ingest_response)

    # Load the reviewer response JSON
    try:
        raw = response_path.read_text(encoding="utf-8")
        reviewer_response = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read/parse {response_path}: {exc}", file=sys.stderr)
        return 1

    # Validate FIRST — no transition on malformed JSON
    errs = validate_reviewer_response(reviewer_response)
    if errs:
        print("ERROR: reviewer response FAILED validation (no transition performed):",
              file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    candidate_id = reviewer_response.get("candidate_id")
    if not candidate_id:
        print("ERROR: reviewer response missing 'candidate_id' field", file=sys.stderr)
        return 1

    # Load the candidate to build the packet
    candidate = _load_candidate(candidate_id, data_dir)
    if candidate is None:
        print(
            f"ERROR: candidate_id {candidate_id!r} not found in candidates.jsonl; "
            f"cannot build challenge packet",
            file=sys.stderr,
        )
        return 1

    # Build the full challenge packet (mechanical probes)
    packet = build_challenge_input(candidate, root=root)

    # Write the challenge JSON (assembles mechanical_probes + reviewer block)
    try:
        challenge_path = write_challenge(
            candidate_id, packet,
            reviewer_response=reviewer_response,
            root=root,
        )
    except ValueError as exc:
        print(f"ERROR: write_challenge failed: {exc}", file=sys.stderr)
        return 1

    print(f"Challenge written: {challenge_path}", file=sys.stderr)

    # State transitions (both mechanical per RF-5/§4)
    apply_challenge_transitions(candidate_id, challenge_path, root=root)

    # Governance event (RF-12 — article: null)
    _emit_governance_event(candidate_id, str(challenge_path), root=root)

    print(f"SUCCESS: {candidate_id} → challenged → human_review", file=sys.stderr)
    return 0


def _emit_governance_event(candidate_id: str, challenge_ref: str, *, root: Path) -> None:
    """Emit research_factory_challenge governance event (RF-12, article: null)."""
    try:
        from engine.neuralweb.governance import append_event
        ok = append_event(
            event_type="research_factory_challenge",
            target=f"research_factory/challenges/{candidate_id}",
            article=None,   # RF-12: factory events never claim Article authority
            authored_by="research_factory_challenge_pack",
            evidence={"challenge_ref": challenge_ref},
            note=f"Challenger packet complete; candidate {candidate_id!r} entering human_review.",
            root=root,
        )
        if ok:
            print(
                f"Governance event 'research_factory_challenge' appended for {candidate_id}",
                file=sys.stderr,
            )
        else:
            print(
                f"WARNING: governance.append_event returned False for {candidate_id}",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: governance event failed (non-fatal): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--candidate", metavar="ID",
        help="Emit the challenge input packet for this candidate_id.",
    )
    group.add_argument(
        "--ingest-response", metavar="PATH",
        help="Path to reviewer response JSON. Validates, writes, transitions.",
    )
    ap.add_argument(
        "--data-dir", metavar="DIR", default=None,
        help="Root data directory (default: ./data).",
    )
    ap.add_argument(
        "--out-dir", metavar="DIR", default=None,
        help="Output directory for challenge packets (--candidate mode only).",
    )
    args = ap.parse_args()

    if args.candidate:
        return _cmd_candidate(args)
    else:
        return _cmd_ingest_response(args)


if __name__ == "__main__":
    raise SystemExit(main())
