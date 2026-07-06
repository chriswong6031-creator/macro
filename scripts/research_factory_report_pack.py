"""External-report intake pack generator for the Research Factory (W4, RF-13).

Modeled on scripts/oracle_brainstorm_pack.py.  Emits an extraction prompt pack
with dedup context BAKED IN — the operator pastes the output into a cheap LLM
(or any model) to extract candidate JSON proposals for research_factory_ingest.

Dedup context baked in (RF-14, absent-safe):
  1. Species registry names (engine/species_registry)
  2. Machine-registry hypotheses (data/neuralweb/machine_registry.jsonl)
  3. Trial-ledger family list (data/trial_ledger.jsonl)
  4. NW_QUANT_SYNTHESIS §3 duplicate table (verbatim text)

OPERATOR-INVOKED ONLY — this script NEVER calls an LLM (RF-16).
The extractor LLM output is candidate JSON proposals; the operator then runs:
    python -m scripts.research_factory_ingest --manual <path>

Usage:
  python -m scripts.research_factory_report_pack --report /path/to/report.md \\
      [--data-dir /path/to/data] > /tmp/extraction_pack.txt
  python -m scripts.research_factory_report_pack --report "paste of note text"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the dedup context loader from challenge.py (single source of truth)
from engine.research_factory.challenge import _load_dedup_context, _NW_QUANT_S3_TEXT


# ---------------------------------------------------------------------------
# Report loader
# ---------------------------------------------------------------------------

def _load_report_text(report_arg: str) -> str:
    """Load report text from a file path or treat as inline text."""
    p = Path(report_arg)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"WARNING: could not read {p}: {exc}", file=sys.stderr)
            return report_arg
    # Treat as inline text (note / paste)
    return report_arg


# ---------------------------------------------------------------------------
# Pack builder
# ---------------------------------------------------------------------------

def build_report_pack(report_text: str, data_dir: Path | None = None) -> str:
    """Build the extraction prompt pack with dedup context baked in."""
    root = (data_dir.parent if data_dir else Path("."))
    dedup = _load_dedup_context(root)

    species_names = dedup.get("species_names") or []
    machine_hyps = dedup.get("machine_registry_hypotheses") or []
    families = dedup.get("trial_ledger_families") or []
    nw_s3 = dedup.get("nw_quant_synthesis_s3_text") or _NW_QUANT_S3_TEXT

    # Format species names
    species_block = "\n".join(f"  - {n}" for n in species_names) or "  (none — registry absent)"

    # Format machine registry hypotheses (cap at 40 for readability)
    if machine_hyps:
        shown = machine_hyps[:40]
        tail = f"\n  (+ {len(machine_hyps) - 40} more)" if len(machine_hyps) > 40 else ""
        mr_block = "\n".join(f"  - {h}" for h in shown) + tail
    else:
        mr_block = "  (none — machine_registry.jsonl absent)"

    # Format trial families (all shown; this is the search-width evidence)
    if families:
        fam_block = "\n".join(f"  - {f}" for f in families)
    else:
        fam_block = "  (none — trial_ledger.jsonl absent)"

    return f"""\
=== RESEARCH FACTORY — EXTERNAL REPORT EXTRACTION PACK ===
=== Generated live; dedup context is current-state-of-repo ===

ROLE: You are an adversarial, SKEPTICAL extractor for a quantitative research
factory. You read an external report (pasted below) and extract ONLY genuine
net-new hypotheses as candidate JSON proposals for the factory ingest pipeline.

MISSION: extract signal, not noise. Your extraction quality is judged by how
many of the proposals are NOT killed by the dedup layer below. Re-proposing
existing work is wasted volume.

---

=== DEDUP CONTEXT — CHECK BEFORE PROPOSING ===

You MUST check each candidate against all four layers below before proposing.
If the proposed hypothesis substantially duplicates an existing entry, DO NOT
propose it — note the duplicate in your reasoning instead.

--- Layer 1: Setup Species Registry (do not re-propose species already registered) ---
{species_block}

--- Layer 2: NeuralWeb Machine Registry (do not re-propose these hypotheses) ---
{mr_block}

--- Layer 3: Trial Ledger Families (active/registered trials — no re-testing) ---
{fam_block}

--- Layer 4: NW_QUANT_SYNTHESIS §3 Duplicate Table (do not re-propose) ---
{nw_s3}

=== END DEDUP CONTEXT ===

---

=== EXTRACTION RULES ===

1. SKEPTICISM FIRST: before proposing anything, confirm it is:
   (a) Falsifiable — has a specific measurable prediction that could fail.
   (b) Mechanism-grounded — not just "this might work"; why would money flow?
   (c) Net-new vs the dedup context above.
   (d) Compatible with the house authority model (display-only; no LLM-originated signals;
       no fused escalating composites; no utility router).

2. OUTCOME-BLIND: do not reference realized outcomes for specific tickers or periods
   as justification for the mechanism. The mechanism must be prospective.

3. AUTHORITY CONSTRAINTS (hard blockers — do not propose these shapes):
   - Fused composite scores that escalate positions (FR-1/RF-16).
   - LLM-generated trading signals or position sizes.
   - Utility routers / meta-routers with sizing output.
   - Anything requiring the word "validated" in user-facing output (CI-enforced).

4. candidate_type values: oracle_compound | cortex_hypothesis | alpha_family |
   species | external_idea

5. domain values: oracle | neuralweb | entry | factor | macro | options | china | us_stocks

6. source: use "external_report" for all proposals from this session.

7. Required fields:
   - candidate_id: a short slug like "rf-YYYYMMDD-<domain>-<short_name>-NNN"
   - hypothesis: a single falsifiable statement (what would need to be true for this to work?)
   - mechanism: WHY money-flow mechanics would produce this footprint
   - candidate_type, domain, source: as above
   - expected_failure_modes: list of 1-3 specific conditions under which this fails
   - decay_conditions: list of 1-2 observable events that would trigger a review

8. DO NOT set: status, trial_accounting, evaluation_plan, artifacts, transition_log,
   authority, schema — the ingest script sets these.

9. authority field: leave absent — the ingest script stamps "display_only".

10. If you find fewer than 2 genuinely net-new candidates, say so explicitly rather
    than padding with duplicates or weak variants.

---

=== OUTPUT FORMAT ===

Return a JSON list of candidate proposals:

[
  {{
    "candidate_id": "rf-YYYYMMDD-<domain>-<short_name>-001",
    "hypothesis": "<specific falsifiable statement>",
    "mechanism": "<why money-flow mechanics would produce this footprint>",
    "candidate_type": "<one of the enum values>",
    "domain": "<one of the enum values>",
    "source": "external_report",
    "expected_failure_modes": ["...", "..."],
    "decay_conditions": ["...", "..."],
    "falsifiers": ["<specific pre-registerable falsifier statement>"],
    "lineage": {{"respin_of": null, "superseded_by": null, "refinement_generation": 0}}
  }},
  ...
]

If no net-new proposals found: return [] and a brief explanation.
If partial duplicates: list the candidate but add "duplicate_context": "<what overlaps>"
  so the ingest dedup layer has evidence to work with.

---

=== EXTERNAL REPORT (to extract from) ===

{report_text}

=== END REPORT ===

Return ONLY the JSON list (or [] if nothing net-new found).  Do not return prose
before the JSON — the ingest pipeline reads the JSON directly.
=== END PACK ===
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--report", metavar="PATH_OR_TEXT", required=True,
        help="Path to the external report file, or a paste of its text.",
    )
    ap.add_argument(
        "--data-dir", metavar="DIR", default=None,
        help="Root data directory for dedup context (default: ./data).",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else Path("data")
    report_text = _load_report_text(args.report)
    pack = build_report_pack(report_text, data_dir=data_dir)
    print(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
