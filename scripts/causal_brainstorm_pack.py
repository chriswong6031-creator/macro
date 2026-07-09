"""Emit the copy-paste BRAINSTORM PACK for causal mechanism proposal.

The operator pastes the output of this script into an LLM to solicit candidate
mechanism cards for the Causal Hypothesis Factory.  The pack is self-contained:
role + authority boundary, feature inventory summary, target families, current
candidate edges, frontier cells, surprise tickets, null library + kill mask,
already-registered hypotheses, collider/confounder warnings, forbidden outputs,
and the EXACT JSON output schema.

All sections are generated live from committed artifacts — an absent file yields
an honest '(absent — 0 rows)' line; nothing is fabricated.

Kill-mask rendering (B1 ruling):
  config/causal_priors.yml ships kill_mask as a dict with two sub-sections:
    curated  — construction-level kills; rendered verbatim as DO-NOT-PROPOSE lines
               with their edge_family and source_ruling fields.
    compiled — edge-level kills; not rendered in the pack (they appear in the NULL
               LIBRARY section via causal_nulls.jsonl which is the source of truth).
  flatten_kill_mask() from causal_schema extracts both sub-lists for iteration.

No LLM calls; pure stdout; NO file writes (CHF-R8 — the LLM runner is W5).

Usage:
    python -m scripts.causal_brainstorm_pack [--n N] [--focus FAMILY] > pack.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.neuralweb.causal_schema import flatten_kill_mask  # noqa: E402

# ---------------------------------------------------------------------------
# File paths (all relative to ROOT)
# ---------------------------------------------------------------------------

_FEATURE_INVENTORY = ROOT / "data" / "neuralweb" / "causal_feature_inventory.json"
_CAUSAL_EDGES = ROOT / "data" / "neuralweb" / "causal_edges.jsonl"
_CAUSAL_FRONTIER = ROOT / "data" / "neuralweb" / "causal_frontier.json"
_SURPRISE_QUEUE = ROOT / "data" / "neuralweb" / "causal_surprise_queue.jsonl"
_CAUSAL_NULLS = ROOT / "data" / "neuralweb" / "causal_nulls.jsonl"
_CAUSAL_PRIORS = ROOT / "config" / "causal_priors.yml"
_MACHINE_REGISTRY = ROOT / "data" / "neuralweb" / "machine_registry.jsonl"
_MECHANISMS = ROOT / "data" / "neuralweb" / "causal_mechanisms.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _absent(label: str) -> str:
    return f"  {label}: (absent — 0 rows)"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_role_boundary() -> str:
    return """\
=== ROLE & AUTHORITY BOUNDARY ===

You propose candidate mechanisms and test specs. You do not score, rank, trade,
or claim proof. Everything you propose is a draft for pre-registered testing.

Your outputs are INERT PROPOSALS until a human (operator or Fable) reviews them.
Your outputs NEVER move a card's status — that is done only by scripts or humans.
You do NOT assign numeric confidence scores to any proposal (RF-16/CHF-R14).
You do NOT select exits, rank the frontier, edit the kill mask, or touch any
calibrated keys.

Banned words in any output text: caused, proved, proof, validated.
Use instead: co-moved with, is consistent with, evidence, tested.

Output: JSON array of mechanism cards only. No prose wrapper, no markdown, no
explanations outside the JSON fields."""


def _section_feature_inventory(focus: str | None) -> str:
    parts = ["=== FEATURE INVENTORY ==="]
    data = _load_json(_FEATURE_INVENTORY)
    if data is None:
        parts.append(_absent("causal_feature_inventory.json"))
        return "\n".join(parts)

    features = data.get("features", []) if isinstance(data, dict) else []
    if not features:
        parts.append(_absent("features"))
        return "\n".join(parts)

    # Filter by focus family if specified
    if focus:
        features = [f for f in features if focus in (f.get("allowed_roles") or [])]

    parts.append(f"  Total features: {len(features)}")
    parts.append("  feature_id | family | allowed_roles | era_coverage | min_lag_days")
    for feat in features[:60]:  # Cap at 60 to keep pack size manageable
        fid = feat.get("feature_id", "?")
        fam = feat.get("family", "?")
        roles = ",".join(feat.get("allowed_roles", []))
        era = feat.get("era_coverage", "?")
        lag = feat.get("min_lag_days", "?")
        parts.append(f"  {fid} | {fam} | {roles} | {era} | {lag}")

    if len(features) > 60:
        parts.append(f"  ... ({len(features) - 60} more features truncated)")

    # Collider/confounder warnings
    risky = [f for f in features if f.get("collider_risk")]
    if risky:
        parts.append("\n  COLLIDER / CONFOUNDER WARNINGS (do not condition on these):")
        for feat in risky:
            parts.append(
                f"  - {feat.get('feature_id', '?')}: {feat.get('collider_risk', '?')}"
            )

    return "\n".join(parts)


def _section_target_families() -> str:
    parts = ["=== TARGET FAMILIES & AVAILABLE TARGETS ==="]
    data = _load_json(_FEATURE_INVENTORY)
    if data is None:
        parts.append(_absent("causal_feature_inventory.json"))
        return "\n".join(parts)

    features = data.get("features", []) if isinstance(data, dict) else []
    targets = [f for f in features if "target" in (f.get("allowed_roles") or [])]
    if not targets:
        parts.append("  (no target-role features found in inventory)")
        return "\n".join(parts)

    for t in targets:
        parts.append(
            f"  {t.get('feature_id', '?')} — {t.get('description', '')} "
            f"[lag={t.get('min_lag_days', '?')}d, era={t.get('era_coverage', '?')}]"
        )
    return "\n".join(parts)


def _section_candidate_edges() -> str:
    parts = ["=== CURRENT CANDIDATE EDGES ==="]
    rows = _load_jsonl(_CAUSAL_EDGES)
    if not rows:
        parts.append(_absent("causal_edges.jsonl"))
        return "\n".join(parts)

    parts.append(f"  {len(rows)} edges on file")
    for row in rows[:20]:
        cause = row.get("cause", "?")
        target = row.get("target", "?")
        env = row.get("environment", "?")
        verdict = row.get("verdict", "?")
        parts.append(f"  {cause} → {target} [{env}] verdict={verdict}")
    if len(rows) > 20:
        parts.append(f"  ... ({len(rows) - 20} more edges truncated)")
    return "\n".join(parts)


def _section_frontier(focus: str | None) -> str:
    parts = ["=== FRONTIER CELLS (unexplored / highest priority) ==="]
    data = _load_json(_CAUSAL_FRONTIER)
    if data is None:
        parts.append(_absent("causal_frontier.json"))
        return "\n".join(parts)

    cells = data.get("frontier_cells", []) if isinstance(data, dict) else []
    if focus:
        cells = [c for c in cells if focus in (c.get("cause_family", "") + c.get("target_family", ""))]

    if not cells:
        parts.append("  (no frontier cells)")
        return "\n".join(parts)

    parts.append("  cause_family | target_family | environment | state | value_heuristic")
    for cell in cells[:15]:
        parts.append(
            f"  {cell.get('cause_family','?')} | {cell.get('target_family','?')} | "
            f"{cell.get('environment','?')} | {cell.get('state','?')} | "
            f"{cell.get('value_heuristic','?')}"
        )
    if len(cells) > 15:
        parts.append(f"  ... ({len(cells) - 15} more frontier cells)")
    return "\n".join(parts)


def _section_surprise_tickets() -> str:
    parts = ["=== SURPRISE TICKETS (unexplained-variance queue) ==="]
    rows = _load_jsonl(_SURPRISE_QUEUE)
    if not rows:
        parts.append(_absent("causal_surprise_queue.jsonl"))
        return "\n".join(parts)

    parts.append(f"  {len(rows)} tickets")
    for row in rows[:10]:
        src = row.get("source_artifact", "?")
        desc = row.get("description", "?")
        asof = row.get("asof", "?")
        stale = row.get("stale", False)
        stale_str = " [STALE]" if stale else ""
        parts.append(f"  [{asof}]{stale_str} {src}: {desc}")
    if len(rows) > 10:
        parts.append(f"  ... ({len(rows) - 10} more tickets)")
    return "\n".join(parts)


def _section_null_library_and_kill_mask() -> str:
    parts = ["=== NULL LIBRARY + KILL MASK (DO NOT RE-PROPOSE) ==="]

    # Null library from causal_nulls.jsonl
    nulls = _load_jsonl(_CAUSAL_NULLS)
    parts.append(f"\n  NULL LIBRARY ({len(nulls)} entries):")
    if not nulls:
        parts.append(_absent("causal_nulls.jsonl"))
    else:
        for n in nulls[:20]:
            cause = n.get("cause", "?")
            target = n.get("target", "?")
            env = n.get("environment", "?")
            reason = n.get("null_reason", "?")
            parts.append(f"  - {cause} → {target} [{env}]: {reason}")
        if len(nulls) > 20:
            parts.append(f"  ... ({len(nulls) - 20} more nulls)")

    # Kill mask from causal_priors.yml
    # config/causal_priors.yml ships kill_mask as {curated: [...], compiled: []}
    # Use flatten_kill_mask to handle both list and dict formats (B1 fix).
    # Only the CURATED entries are rendered verbatim here — compiled entries are
    # edge-level and appear above in the null library section.
    priors = _load_yaml(_CAUSAL_PRIORS)
    parts.append("\n  FORBIDDEN CAUSES (config/causal_priors.yml — Article-2 / fence patterns):")
    if priors is None:
        parts.append(_absent("config/causal_priors.yml"))
    else:
        forbidden = priors.get("forbidden_causes", [])
        if not isinstance(forbidden, list):
            forbidden = []
        if not forbidden:
            parts.append("  (no forbidden_causes in config)")
        else:
            for fc in forbidden:
                if not isinstance(fc, dict):
                    continue
                pattern = fc.get("pattern", "?")
                reason = fc.get("reason", "?")
                ruling = fc.get("source_ruling", "")
                if isinstance(reason, str):
                    reason = reason.strip().replace("\n", " ")[:100]
                ruling_str = f" [{ruling}]" if ruling else ""
                parts.append(f"  - pattern={pattern!r}{ruling_str}: {reason}")

        # Curated kill-mask entries: construction-level kills rendered verbatim
        # as DO-NOT-PROPOSE lines with their actual fields (edge_family, reason,
        # source_ruling).  These are PACK-advisory: the LLM must not propose
        # cards in these construction families (B1 fix).
        raw_km = priors.get("kill_mask") or {}
        curated: list[dict] = []
        if isinstance(raw_km, list):
            curated = [e for e in raw_km if isinstance(e, dict)]
        elif isinstance(raw_km, dict):
            curated_raw = raw_km.get("curated") or []
            if isinstance(curated_raw, list):
                curated = [e for e in curated_raw if isinstance(e, dict)]

        if curated:
            parts.append(
                "\n  CURATED KILL MASK — CONSTRUCTION-LEVEL KILLS (DO NOT PROPOSE):"
            )
            for km in curated:
                ef = km.get("edge_family", "?")
                reason = km.get("reason", "?")
                ruling = km.get("source_ruling", "")
                if isinstance(reason, str):
                    reason = reason.strip().replace("\n", " ")[:120]
                ruling_str = f" [{ruling}]" if ruling else ""
                clock = km.get("come_back_clock")
                clock_str = f" (come_back: {clock})" if clock else ""
                parts.append(
                    f"  - edge_family={ef!r}{ruling_str}{clock_str}: {reason}"
                )
        else:
            parts.append("  (no curated kill-mask entries)")

    return "\n".join(parts)


def _section_registered_hypotheses() -> str:
    parts = ["=== ALREADY-REGISTERED HYPOTHESES (do not duplicate) ==="]
    rows = _load_jsonl(_MACHINE_REGISTRY)
    if not rows:
        parts.append(_absent("machine_registry.jsonl"))
        return "\n".join(parts)

    cortex_hyps = [r for r in rows if r.get("kind") == "cortex_hypothesis"]
    parts.append(f"  {len(cortex_hyps)} registered hypotheses")
    for h in cortex_hyps[:20]:
        hid = h.get("id", "?")
        hyp = (h.get("hypothesis") or "?")[:80]
        parts.append(f"  [{hid}] {hyp}")
    if len(cortex_hyps) > 20:
        parts.append(f"  ... ({len(cortex_hyps) - 20} more)")

    # Also include already-filed mechanism cards
    mechanisms = _load_jsonl(_MECHANISMS)
    filed = [m for m in mechanisms if m.get("status") in ("filed", "skeptic_passed")]
    if filed:
        parts.append(f"\n  FILED MECHANISM CARDS ({len(filed)} already filed):")
        for m in filed[:15]:
            mid = m.get("mechanism_id", "?")
            claim = (m.get("claim_en") or "?")[:80]
            parts.append(f"  [{mid}] {claim}")
        if len(filed) > 15:
            parts.append(f"  ... ({len(filed) - 15} more)")

    return "\n".join(parts)


def _section_collider_warnings() -> str:
    parts = ["=== COLLIDER / CONFOUNDER WARNINGS ==="]
    data = _load_json(_FEATURE_INVENTORY)
    if data is None:
        parts.append("  (feature inventory absent — no warnings available)")
        return "\n".join(parts)

    features = data.get("features", []) if isinstance(data, dict) else []
    colliders = [f for f in features if "collider" in (f.get("allowed_roles") or [])]
    confounders = [f for f in features if "confounder" in (f.get("allowed_roles") or [])]

    if not colliders and not confounders:
        parts.append("  (no collider or confounder-role features in inventory)")
        return "\n".join(parts)

    if colliders:
        parts.append("  COLLIDERS (conditioning on these opens a back-door path):")
        for c in colliders:
            parts.append(
                f"  - {c.get('feature_id', '?')}: {c.get('collider_risk', 'collider')} "
                f"— add to causal_graph.colliders_to_avoid"
            )

    if confounders:
        parts.append("  CONFOUNDERS (must be in causal_graph.confounders or controlled):")
        for c in confounders:
            parts.append(f"  - {c.get('feature_id', '?')}: {c.get('description', '?')[:60]}")

    return "\n".join(parts)


def _section_forbidden_outputs() -> str:
    return """\
=== FORBIDDEN OUTPUTS ===

Do NOT produce any of the following:
- Numeric confidence scores on any card or any field
- Status transitions or instructions to move a card to any status
- Kill-mask edits or proposals to retire any hypothesis
- Ranked lists of your own proposals (no ordering by confidence)
- Claims using the words: caused, proved, proof, validated
- Cards with fewer than 2 falsifiers
- Cards with test_spec.min_n below 25
- Cards that duplicate entries already listed in the null library or
  registered hypotheses above
- Cards using forbidden-cause patterns from the kill mask above
- Cards whose cause is an Article-2 surface (board_rank, final_verdict,
  top_setups, board_score, board_brief, board_ordering)"""


def _section_output_schema(n_requested: int) -> str:
    example = {
        "mechanism_id": "example-slug-here",
        "family": "one_of_the_valid_families",
        "claim_en": "When X co-moves with Y in environment Z, outcome W follows within H days.",
        "claim_zh": "当X在Z环境中与Y共同变动时，结果W在H天内出现。",
        "causal_graph": {
            "cause": "feature_id_of_cause",
            "target": "feature_id_of_target",
            "mediators": ["optional_mediator_1"],
            "confounders": ["known_confounder"],
            "colliders_to_avoid": ["collider_that_must_not_be_conditioned_on"]
        },
        "environment_map": {
            "should_hold": ["environment_condition_1", "environment_condition_2"],
            "should_break": ["environment_condition_where_it_should_fail"],
            "frozen_hash": "(leave blank — the ingest script computes this at mint time)"
        },
        "falsifiers": [
            "If X does not predict Y in regime R, the mechanism is refuted.",
            "If lagged-placebo Y_{t-H} predicts X, reverse causation is the explanation."
        ],
        "test_spec": {
            "exit_path": "a",
            "claim_shape": "lead_lag",
            "horizon_d": 21,
            "metric": "forward_return_21d",
            "threshold": 0.55,
            "min_n": 50,
            "environment": "risk_on"
        },
        "lineage": {
            "source": "llm_proposed",
            "pack_id": "(the pack will be stamped by the ingest script)",
            "model": "(the ingest script records this from --model-label)"
        },
        "status": "inbox"
    }

    return f"""\
=== OUTPUT FORMAT (strict) ===

Produce EXACTLY {n_requested} candidate mechanism cards.
Return a JSON ARRAY only — no prose, no markdown, no explanations outside the JSON.
Every element must conform to this schema (neuralweb.causal_mechanism_card.v1):

{json.dumps([example], indent=2, ensure_ascii=False)}

VALID families: liquidity_transmission, macro_transmission, rotation_transfer,
  entry_quality, exit_fragility, confluence_independence, factor_mirage,
  context_organ, null_mining

VALID claim_shapes (for exit_path='a'): lead_lag, conditional_regime,
  entry_quality, sector_conditional

For exit_path='b', replace claim_shape with domain_harness (a reference to the
test harness that will evaluate the card).

frozen_hash: leave as "(leave blank — the ingest script computes this at mint time)"
or omit — the ingest firewall computes and stamps it on accepted cards.

min_n must be >= 25 (house floor).  The ingest script will clamp lower values.

status MUST be "inbox" — the only legal status for a newly proposed card."""


# ---------------------------------------------------------------------------
# Main pack builder
# ---------------------------------------------------------------------------

def build_pack(n_requested: int = 30, focus: str | None = None) -> str:
    """Build and return the brainstorm pack as a string.

    All sections are generated live from committed artifacts.
    Absent files yield honest '(absent — 0 rows)' lines; nothing is fabricated.
    """
    sections = [
        "=" * 72,
        "CAUSAL HYPOTHESIS FACTORY — BRAINSTORM PACK",
        f"Requested cards: {n_requested}" + (f"  Focus family: {focus}" if focus else ""),
        "=" * 72,
        "",
        _section_role_boundary(),
        "",
        _section_feature_inventory(focus),
        "",
        _section_target_families(),
        "",
        _section_candidate_edges(),
        "",
        _section_frontier(focus),
        "",
        _section_surprise_tickets(),
        "",
        _section_null_library_and_kill_mask(),
        "",
        _section_registered_hypotheses(),
        "",
        _section_collider_warnings(),
        "",
        _section_forbidden_outputs(),
        "",
        _section_output_schema(n_requested),
        "",
        "=" * 72,
        "END OF PACK — paste above into your LLM session and return JSON array only.",
        "=" * 72,
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=30, metavar="N",
                    help="Number of cards to request (default: 30)")
    ap.add_argument("--focus", type=str, default=None, metavar="FAMILY",
                    help="Focus on a specific mechanism family")
    args = ap.parse_args()

    pack = build_pack(n_requested=args.n, focus=args.focus)
    sys.stdout.write(pack)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
