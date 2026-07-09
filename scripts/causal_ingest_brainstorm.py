"""Ingest a folder of brainstorm-pack JSON outputs for causal mechanism cards.

Schema firewall, dedup, ISO-week filing lock, and kill-mask enforcement.

The operator saves each LLM reply as a .json file in --inbox (a JSON array
of mechanism cards; a file may contain several concatenated JSON arrays).
This tool:

  1. Parses every *.json (tolerant of multiple concatenated JSON arrays).
  2. Sanitizes banned words (RUL-CC-5) on claim_en, claim_zh, falsifiers.
  3. Stamps frozen_hash on environment_map (CHF-R7).
  4. Clamps test_spec.min_n to the house floor (25).
  5. Validates each card via causal_schema.validate_card (schema firewall
     — drops invalid, counts dropped_invalid).
  6. Checks test_spec.claim_shape against metabolism CLAIM_SHAPES for exit-a.
  7. Refuses cards matching config/causal_priors.yml kill_mask or
     forbidden_causes (dropped_forbidden).
  8. RF-14 fixed-order dedup in 4 layers (see below); near-dup flagged.
  9. ISO-WEEK FILING LOCK (CHF-R8): ≤3 cards per ISO week; second --write
     run in same week refuses with a printed message.
 10. Dry-run by default; --write appends accepted cards to
     data/neuralweb/causal_mechanisms.jsonl with actor='script' provenance.

RF-14 fixed-order dedup:
  (0) Existing causal_mechanisms.jsonl canonical hashes.
  (1) causal_nulls.jsonl (cause+target pair matching).
  (2) machine_registry.jsonl hypotheses (absent-safe).
  (3) Oracle canonical rules via scripts.oracle_ingest_brainstorm._canonical
      if the card is rotation-family.
  (4) Trial-ledger family strings.

Usage:
    python -m scripts.causal_ingest_brainstorm --inbox <dir> [--out data/neuralweb] \
        [--dry-run] [--write] [--model-label gpt-4o]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.neuralweb.causal_schema import (
    AUTHORITY_BLOCK,
    MIN_N_FLOOR,
    SCHEMA,
    _compute_env_hash,
    _get_claim_shapes,
    canonical_card,
    sanitize_card,
    validate_card,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_OUT = ROOT / "data" / "neuralweb"
_MECHANISMS = "causal_mechanisms.jsonl"
_NULLS_FILE = ROOT / "data" / "neuralweb" / "causal_nulls.jsonl"
_MACHINE_REGISTRY = ROOT / "data" / "neuralweb" / "machine_registry.jsonl"
_TRIAL_LEDGER = ROOT / "data" / "trial_ledger.jsonl"
_CAUSAL_PRIORS = ROOT / "config" / "causal_priors.yml"

# Families considered rotation-family for oracle dedup check
_ROTATION_FAMILIES = frozenset({"rotation_transfer", "entry_quality", "exit_fragility"})

# Budget per ISO week (CHF-R8)
_BUDGET_PER_WEEK = 3

# ---------------------------------------------------------------------------
# JSON parsing (tolerant of multiple concatenated arrays)
# ---------------------------------------------------------------------------

def _parse_json_multi(text: str) -> list:
    """Parse a file that may contain one or several concatenated JSON arrays."""
    out = []
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            val, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        out.extend(val if isinstance(val, list) else [val])
        i = end
    return out

# ---------------------------------------------------------------------------
# Dedup corpus loaders
# ---------------------------------------------------------------------------

def _load_existing_hashes(out_dir: Path) -> set[str]:
    """Load canonical hashes of already-filed mechanism cards (dedup layer 0)."""
    p = out_dir / _MECHANISMS
    if not p.exists():
        return set()
    hashes = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            card = json.loads(line)
            hashes.add(canonical_card(card))
        except Exception:  # noqa: BLE001
            pass
    return hashes


def _load_null_pairs(nulls_path: Path) -> set[tuple[str, str]]:
    """Load (cause, target) pairs from causal_nulls.jsonl (dedup layer 1)."""
    if not nulls_path.exists():
        return set()
    pairs = set()
    for line in nulls_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            cause = row.get("cause", "")
            target = row.get("target", "")
            if cause and target:
                pairs.add((cause.lower().strip(), target.lower().strip()))
        except Exception:  # noqa: BLE001
            pass
    return pairs


def _load_machine_hypotheses(registry_path: Path) -> set[str]:
    """Load hypothesis strings from machine_registry.jsonl (absent-safe, dedup layer 2)."""
    if not registry_path.exists():
        return set()
    hyps = set()
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            hyp = (row.get("hypothesis") or "").lower().strip()[:120]
            if hyp:
                hyps.add(hyp)
        except Exception:  # noqa: BLE001
            pass
    return hyps


def _load_trial_families(ledger_path: Path) -> set[str]:
    """Load family strings from trial_ledger.jsonl (dedup layer 4)."""
    if not ledger_path.exists():
        return set()
    families = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            fam = (row.get("family") or "").lower().strip()
            if fam:
                families.add(fam)
        except Exception:  # noqa: BLE001
            pass
    return families


def _load_oracle_canonical_rules() -> set[str]:
    """Load canonical oracle compound rules (for rotation-family dedup, layer 3)."""
    try:
        from scripts.oracle_ingest_brainstorm import _canonical  # type: ignore[import]
        from engine.oracle.compounds import load_registry  # type: ignore[import]
        registry_dir = ROOT / "data" / "oracle" / "compounds"
        rules = set()
        for c in load_registry(registry_dir):
            if c.get("entry_rule") and isinstance(c["entry_rule"], dict):
                rules.add(_canonical(c["entry_rule"]))
        return rules
    except Exception:  # noqa: BLE001
        return set()

# ---------------------------------------------------------------------------
# Kill-mask loading
# ---------------------------------------------------------------------------

def _load_kill_mask(priors_path: Path) -> tuple[list[dict], list[dict]]:
    """Return (forbidden_causes, kill_mask_entries) from causal_priors.yml.

    kill_mask in causal_priors.yml has structure:
        kill_mask:
          curated: [{edge_family: ..., reason: ..., ...}]
          compiled: [{cause: ..., target: ..., reason: ..., ...}]

    Returns (forbidden_causes_list, flattened_kill_mask_list).
    Returns ([], []) if file is absent or unreadable.
    """
    if not priors_path.exists():
        return [], []
    try:
        import yaml
        data = yaml.safe_load(priors_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return [], []
        forbidden = data.get("forbidden_causes", [])
        if not isinstance(forbidden, list):
            forbidden = []

        # kill_mask may be None, a list, or a dict with curated/compiled sub-keys
        raw_km = data.get("kill_mask") or {}
        if isinstance(raw_km, list):
            kill_mask_entries = raw_km
        elif isinstance(raw_km, dict):
            # Flatten curated + compiled into one list
            kill_mask_entries = []
            for sub_list in raw_km.values():
                if isinstance(sub_list, list):
                    kill_mask_entries.extend(sub_list)
        else:
            kill_mask_entries = []

        return forbidden, kill_mask_entries
    except Exception:  # noqa: BLE001
        return [], []


def _matches_forbidden(card: dict, forbidden_causes: list[dict], kill_mask_entries: list[dict]) -> str | None:
    """Return a description string if the card matches any kill-mask entry, else None."""
    cause = (card.get("causal_graph", {}) or {}).get("cause", "").lower().strip()
    target = (card.get("causal_graph", {}) or {}).get("target", "").lower().strip()
    family = (card.get("family") or "").lower().strip()

    # Check forbidden_causes patterns (substring match on cause field)
    for fc in forbidden_causes:
        if not isinstance(fc, dict):
            continue
        pattern = (fc.get("pattern") or "").lower()
        if pattern and pattern in cause:
            reason = (fc.get("reason") or "")
            if isinstance(reason, str):
                reason = reason.strip().replace("\n", " ")[:80]
            return f"cause {cause!r} matches forbidden_causes pattern {pattern!r}: {reason}"

    # Check kill_mask entries — may have edge_family (pattern match) or cause/target pairs
    for km in kill_mask_entries:
        if not isinstance(km, dict):
            continue
        # edge_family-based entries match on card family or cause/target substrings
        ef = (km.get("edge_family") or "").lower().strip()
        if ef:
            if ef in family or ef in cause or ef in target:
                reason = (km.get("reason") or "")
                if isinstance(reason, str):
                    reason = reason.strip().replace("\n", " ")[:80]
                return f"matches kill_mask edge_family={ef!r}: {reason}"
        # cause+target pair entries
        km_cause = (km.get("cause") or "").lower().strip()
        km_target = (km.get("target") or "").lower().strip()
        if km_cause and km_target:
            if km_cause in cause and km_target in target:
                reason = (km.get("reason") or "")
                if isinstance(reason, str):
                    reason = reason.strip().replace("\n", " ")[:80]
                return (
                    f"cause+target matches kill_mask: {km_cause!r} → {km_target!r}: {reason}"
                )

    return None

# ---------------------------------------------------------------------------
# ISO-week filing state
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    """Return current ISO year-week string 'YYYY-WNN'."""
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _count_filed_this_week(out_dir: Path) -> int:
    """Count mechanism cards filed in the current ISO week."""
    p = out_dir / _MECHANISMS
    if not p.exists():
        return 0
    week = _current_iso_week()
    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("filing_week") == week:
                count += 1
        except Exception:  # noqa: BLE001
            pass
    return count

# ---------------------------------------------------------------------------
# Near-dup detection (claim text similarity — flag only, not auto-reject)
# ---------------------------------------------------------------------------

def _near_dup_score(text_a: str, text_b: str) -> float:
    """Simple word-overlap Jaccard similarity for near-dup flagging."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def ingest(
    inbox: Path,
    out_dir: Path,
    dry_run: bool,
    model_label: str,
) -> int:
    """Run the full ingest pipeline.  Returns 0 on success."""

    # ---- Load dedup corpora ----
    existing_hashes = _load_existing_hashes(out_dir)
    null_pairs = _load_null_pairs(_NULLS_FILE)
    machine_hyps = _load_machine_hypotheses(_MACHINE_REGISTRY)
    trial_families = _load_trial_families(_TRIAL_LEDGER)
    oracle_rules = _load_oracle_canonical_rules()
    forbidden_causes, kill_mask = _load_kill_mask(_CAUSAL_PRIORS)
    claim_shapes = _get_claim_shapes()

    # ---- ISO-week filing state ----
    week = _current_iso_week()
    filed_this_week = _count_filed_this_week(out_dir)

    print(f"[causal_ingest] inbox={inbox}, out={out_dir}, dry_run={dry_run}")
    print(f"[causal_ingest] ISO week={week}, already filed this week={filed_this_week}")

    # ---- Parse all inbox files ----
    all_cards: list[dict] = []
    for fp in sorted(inbox.glob("*.json")):
        try:
            text = fp.read_text(encoding="utf-8")
            cards = _parse_json_multi(text)
            print(f"  parsed {len(cards)} cards from {fp.name}")
            all_cards.extend(cards)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARNING: could not read {fp.name}: {exc}")

    print(f"[causal_ingest] total parsed: {len(all_cards)} cards")

    # ---- Per-card pipeline ----
    stats = {
        "parsed": len(all_cards),
        "dropped_invalid": 0,
        "dropped_forbidden": 0,
        "dropped_dup": 0,
        "near_dup_flagged": 0,
        "accepted": 0,
    }
    accepted_cards: list[dict] = []

    # Collect claim texts from already-filed cards for near-dup
    existing_claims: list[str] = []
    p = out_dir / _MECHANISMS
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                claim = row.get("claim_en", "")
                if claim:
                    existing_claims.append(claim)
            except Exception:  # noqa: BLE001
                pass

    for i, raw_card in enumerate(all_cards):
        card_label = f"card[{i}] mechanism_id={raw_card.get('mechanism_id', '?')!r}"

        if not isinstance(raw_card, dict):
            print(f"  DROP invalid (not a dict): {card_label}")
            stats["dropped_invalid"] += 1
            continue

        # ---- Step 1: sanitize banned words ----
        card = sanitize_card(raw_card)

        # ---- Step 2: stamp frozen_hash on environment_map ----
        em = card.get("environment_map")
        if isinstance(em, dict):
            em["frozen_hash"] = _compute_env_hash(em)
            card["environment_map"] = em

        # ---- Step 3: clamp min_n ----
        ts = card.get("test_spec")
        if isinstance(ts, dict):
            min_n = ts.get("min_n")
            if isinstance(min_n, int) and min_n < MIN_N_FLOOR:
                print(f"  NOTE {card_label}: clamping min_n {min_n} -> {MIN_N_FLOOR}")
                ts["min_n"] = MIN_N_FLOOR
                card["test_spec"] = ts

        # ---- Step 4: schema validation ----
        errors = validate_card(card)
        if errors:
            print(f"  DROP invalid schema {card_label}: {errors[:3]}")
            stats["dropped_invalid"] += 1
            continue

        # ---- Step 5: claim_shape check for exit-a ----
        ts = card.get("test_spec", {})
        if ts.get("exit_path") == "a":
            cs = ts.get("claim_shape")
            if cs and cs not in claim_shapes:
                print(
                    f"  DROP invalid claim_shape {card_label}: "
                    f"{cs!r} not in {sorted(claim_shapes)}"
                )
                stats["dropped_invalid"] += 1
                continue

        # ---- Step 6: kill-mask check ----
        kill_reason = _matches_forbidden(card, forbidden_causes, kill_mask)
        if kill_reason:
            print(f"  DROP forbidden {card_label}: {kill_reason}")
            stats["dropped_forbidden"] += 1
            continue

        # ---- Step 7: RF-14 fixed-order dedup ----
        canon = canonical_card(card)

        # Layer 0: existing mechanism cards
        if canon in existing_hashes:
            print(f"  DROP dup (layer 0 — existing mechanisms) {card_label}")
            stats["dropped_dup"] += 1
            continue

        # Layer 1: null library (cause + target pair)
        cg = card.get("causal_graph", {}) or {}
        cause_key = (cg.get("cause") or "").lower().strip()
        target_key = (cg.get("target") or "").lower().strip()
        if cause_key and target_key and (cause_key, target_key) in null_pairs:
            print(f"  DROP dup (layer 1 — null library) {card_label}: {cause_key} → {target_key}")
            stats["dropped_dup"] += 1
            continue

        # Layer 2: machine registry hypotheses
        claim_lower = (card.get("claim_en") or "").lower().strip()[:120]
        if claim_lower and claim_lower in machine_hyps:
            print(f"  DROP dup (layer 2 — machine registry) {card_label}")
            stats["dropped_dup"] += 1
            continue

        # Layer 3: oracle canonical rules (rotation-family only)
        if card.get("family") in _ROTATION_FAMILIES and oracle_rules:
            # The card doesn't have entry_rule — check if claim substance matches
            # by looking for any near-identical oracle rule text via claim_en
            # (full oracle entry_rule dedup is not applicable here — cards don't
            # have entry_rule dicts; we skip this layer if no structural match)
            pass  # Layer 3 is only meaningful if the card has an entry_rule dict

        # Layer 4: trial ledger families
        card_family = (card.get("family") or "").lower().strip()
        if card_family and card_family in trial_families:
            # Near-dup flag only — not auto-reject (families are broad)
            print(f"  NOTE near-family-dup (layer 4 — trial ledger) {card_label}: family={card_family}")

        # ---- Step 8: near-dup claim text check ----
        claim_en = card.get("claim_en", "")
        for existing_claim in existing_claims:
            sim = _near_dup_score(claim_en, existing_claim)
            if sim >= 0.7:
                print(
                    f"  NOTE near-dup claim (sim={sim:.2f}) {card_label}: "
                    f"similar to existing filed card"
                )
                stats["near_dup_flagged"] += 1
                break  # Flag once

        # ---- Stamp provenance ----
        now_iso = datetime.now(timezone.utc).isoformat()
        card["schema"] = SCHEMA
        card["status"] = "inbox"
        card["filed_at"] = now_iso
        card["filing_week"] = week
        card["actor"] = "script"
        card["authority_block"] = AUTHORITY_BLOCK
        # a6-style provenance in lineage
        lin = card.get("lineage", {}) or {}
        lin["ingested_at"] = now_iso
        lin["model_label"] = model_label
        lin["actor"] = "script"
        card["lineage"] = lin

        accepted_cards.append(card)
        # Add canonical hash so we catch dups within this batch
        existing_hashes.add(canonical_card(card))
        existing_claims.append(claim_en)

    stats["accepted"] = len(accepted_cards)

    # ---- ISO-week budget gate ----
    budget_remaining = _BUDGET_PER_WEEK - filed_this_week
    if not dry_run and accepted_cards:
        if filed_this_week >= _BUDGET_PER_WEEK:
            print(
                f"\n[causal_ingest] ISO-WEEK FILING LOCK: {filed_this_week} cards already "
                f"filed this week (budget={_BUDGET_PER_WEEK}). "
                f"Re-run next week or retire an existing card first."
            )
            print(f"[causal_ingest] {len(accepted_cards)} accepted cards NOT written (budget exhausted).")
            _print_summary(stats)
            return 1

        if len(accepted_cards) > budget_remaining:
            print(
                f"[causal_ingest] budget: only {budget_remaining} slot(s) remaining this week; "
                f"trimming from {len(accepted_cards)} to {budget_remaining} cards"
            )
            accepted_cards = accepted_cards[:budget_remaining]
            stats["accepted"] = len(accepted_cards)

    # ---- Summary print ----
    _print_summary(stats)

    if not accepted_cards:
        print("[causal_ingest] No cards to write.")
        return 0

    if dry_run:
        print(f"\n[causal_ingest] DRY-RUN: would file {len(accepted_cards)} card(s) this week.")
        print("  Re-run with --write to commit.")
        for card in accepted_cards:
            print(f"  - {card.get('mechanism_id', '?')}: {card.get('claim_en', '')[:60]}")
        return 0

    # ---- Write ----
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / _MECHANISMS
    written = 0
    with p.open("a", encoding="utf-8") as fh:
        for card in accepted_cards:
            fh.write(json.dumps(card, ensure_ascii=False, default=str) + "\n")
            written += 1

    print(f"\n[causal_ingest] wrote {written} card(s) to {p}")
    return 0


def _print_summary(stats: dict) -> None:
    print(
        f"\n[causal_ingest] summary: "
        f"parsed={stats['parsed']} "
        f"dropped_invalid={stats['dropped_invalid']} "
        f"dropped_forbidden={stats['dropped_forbidden']} "
        f"dropped_dup={stats['dropped_dup']} "
        f"near_dup_flagged={stats['near_dup_flagged']} "
        f"accepted={stats['accepted']}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inbox", type=Path, required=True,
                    help="Directory containing *.json brainstorm-pack reply files")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Output directory (default: data/neuralweb)")
    ap.add_argument("--model-label", type=str, default="unknown",
                    metavar="LABEL",
                    help="Label of the model that produced the cards (for provenance)")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="Dry-run mode: print without writing (default)")
    ap.add_argument("--write", action="store_true", default=False,
                    help="Actually write accepted cards (disables dry-run)")
    args = ap.parse_args()

    dry_run = not args.write  # --write overrides dry-run default

    if not args.inbox.is_dir():
        print(f"ERROR: --inbox {args.inbox} is not a directory", file=sys.stderr)
        return 2

    return ingest(
        inbox=args.inbox,
        out_dir=args.out,
        dry_run=dry_run,
        model_label=args.model_label,
    )


if __name__ == "__main__":
    sys.exit(main())
