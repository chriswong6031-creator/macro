"""scripts/causal_factory_handoff.py — CHF W5 exit-b factory handoff.

Reads skeptic_passed/filed mechanism cards from data/neuralweb/causal_mechanisms.jsonl
and builds Research Factory candidate proposals, then routes them through the factory
ingest pipeline for review-queue visibility.

This gives the human review queue visibility of cards that have survived the skeptic
pass and are ready for consideration as pre-registered study candidates.

Factory enrollment:
  source='external_report'    — per CHF-R2: factory enum semantics preserved
  candidate_type='external_idea' — inert display-tier proposal (no scoring)
  trial_accounting.mode='read_only' — passive tracking only (RF-6 minimal footprint)
  spec_ref=mechanism_id       — trace back to the card
  hypothesis, mechanism from the card's claim_en / causal_graph

CHF-R17 operator law: this script is invoked only by the operator (manual or via
--write); it is NOT in the nightly job (factory writes are operator-only from CHF).
Dry-run by default.

Usage:
    python -m scripts.causal_factory_handoff [--root PATH] [--dry-run] [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_MECHANISMS_FILE = ROOT / "data" / "neuralweb" / "causal_mechanisms.jsonl"


# ---------------------------------------------------------------------------
# Card loader
# ---------------------------------------------------------------------------

def _load_handoff_cards(root: Path) -> list[dict]:
    """Load mechanism cards eligible for factory handoff.

    Eligible statuses: skeptic_passed, filed (both represent cards that have
    survived the ingest pipeline and are ready for display-tier factory tracking).
    """
    cards_path = root / "data" / "neuralweb" / "causal_mechanisms.jsonl"
    if not cards_path.exists():
        print(f"[causal_factory_handoff] {cards_path} not found — no cards to hand off")
        return []

    eligible: list[dict] = []
    for line in cards_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            card = json.loads(line)
            # Eligible: skeptic_passed (explicitly reviewed) or inbox (newly filed)
            # The task spec says "skeptic_passed/filed cards" — we treat inbox
            # cards as filed (status inbox = accepted by ingest, awaiting further action)
            if card.get("status") in ("skeptic_passed", "inbox"):
                eligible.append(card)
        except json.JSONDecodeError:
            pass

    return eligible


# ---------------------------------------------------------------------------
# Candidate builder
# ---------------------------------------------------------------------------

def _build_candidate_proposal(card: dict) -> dict:
    """Convert a mechanism card to a Research Factory candidate proposal dict.

    Schema: research_factory.candidate.v1
    See engine/research_factory/schema.py for field constraints.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cg = card.get("causal_graph") or {}
    cause = cg.get("cause", "")
    target = cg.get("target", "")

    claim_en = card.get("claim_en") or ""
    mechanism_id = card.get("mechanism_id") or ""
    family = card.get("family") or "context_organ"
    test_spec = card.get("test_spec") or {}

    # Build mechanism string from causal_graph (mediators + confounders)
    mech_parts: list[str] = []
    if cause and target:
        mech_parts.append(f"{cause} → {target}")
    mediators = cg.get("mediators") or []
    if mediators:
        mech_parts.append(f"via {', '.join(mediators)}")
    confounders = cg.get("confounders") or []
    if confounders:
        mech_parts.append(f"controlling for {', '.join(confounders)}")
    mechanism_str = "; ".join(mech_parts) if mech_parts else claim_en[:120]

    # trial_accounting.mode='read_only' — minimal footprint, passive tracking only (RF-6)
    trial_accounting = {
        "mode": "read_only",
    }

    # Candidate ID: derived from mechanism_id for stable dedup
    candidate_id = f"chf-{mechanism_id}" if mechanism_id else f"chf-handoff-{now_iso}"

    # domain: 'neuralweb' (CHF is a Neural Web program per CHF-R1)
    domain = "neuralweb"

    proposal: dict = {
        "schema": "research_factory.candidate.v1",
        "candidate_id": candidate_id,
        "created_at": now_iso,
        "source": "external_report",         # CHF-R2: existing factory enum
        "candidate_type": "external_idea",   # CHF-R2: existing factory enum
        "domain": domain,
        "hypothesis": claim_en,
        "mechanism": mechanism_str,
        "status": "proposed",
        "authority": "display_only",          # RF-11: required field
        "trial_accounting": trial_accounting,
        "spec_ref": mechanism_id,             # trace back to the card
        "lineage": {
            "refinement_generation": 0,
            "source_card": {
                "mechanism_id": mechanism_id,
                "family": family,
                "status": card.get("status"),
                "filed_at": card.get("filed_at"),
                "filing_week": card.get("filing_week"),
            },
        },
        # Extra context from card (not required by factory schema but useful for review)
        "causal_graph": cg,
        "falsifiers": card.get("falsifiers") or [],
        "test_spec": test_spec,
    }

    return proposal


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None,
                    help="Repo root (default: inferred from script location)")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Dry-run mode: print without writing (default)")
    ap.add_argument("--write", action="store_true", default=False,
                    help="Actually write to factory ledger (disables dry-run)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    dry_run = not args.write  # --write overrides dry-run default

    print(f"[causal_factory_handoff] root={root}, dry_run={dry_run}")

    # Load eligible cards
    cards = _load_handoff_cards(root)
    if not cards:
        print("[causal_factory_handoff] No eligible cards found; nothing to hand off")
        return 0

    print(f"[causal_factory_handoff] {len(cards)} eligible card(s) for handoff")

    # Build proposals
    proposals: list[dict] = []
    for card in cards:
        try:
            prop = _build_candidate_proposal(card)
            proposals.append(prop)
        except Exception as exc:  # noqa: BLE001
            print(f"[causal_factory_handoff] WARNING: could not build proposal for "
                  f"{card.get('mechanism_id','?')}: {exc}")

    if not proposals:
        print("[causal_factory_handoff] No proposals built; nothing to hand off")
        return 0

    # Validate proposals via factory schema
    from engine.research_factory.schema import validate_candidate  # noqa: PLC0415
    valid_proposals: list[dict] = []
    for prop in proposals:
        errs = validate_candidate(prop)
        if errs:
            cid = prop.get("candidate_id", "?")
            print(f"[causal_factory_handoff] WARNING: candidate {cid!r} failed validation:")
            for err in errs:
                print(f"  - {err}")
        else:
            valid_proposals.append(prop)

    print(f"[causal_factory_handoff] {len(valid_proposals)}/{len(proposals)} proposals passed validation")

    if not valid_proposals:
        print("[causal_factory_handoff] No valid proposals to hand off")
        return 0

    # Route through factory ingest
    try:
        from scripts.research_factory_ingest import run_ingest  # noqa: PLC0415
        result = run_ingest(
            proposals=valid_proposals,
            dry_run=dry_run,
        )
        # Print summary (IngestResult has .registered and .dropped lists)
        n_registered = len(result.registered)
        n_dropped = len(result.dropped)
        print(f"[causal_factory_handoff] ingest result: registered={n_registered}, dropped={n_dropped}")
        for cand, rc, rt in result.dropped[:10]:
            cid = cand.get("candidate_id", "?")
            print(f"  DROP [{rc}] {cid}: {rt}")
        if dry_run:
            print("[causal_factory_handoff] DRY-RUN: no factory records written. Re-run with --write to commit.")
    except Exception as exc:  # noqa: BLE001
        print(f"[causal_factory_handoff] ERROR: factory ingest failed ({exc})")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
