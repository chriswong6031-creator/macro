"""Emit the copy-paste BRAINSTORM PACK for cheap-LLM compound generation.

The operator pastes the output of this script into ChatGPT (or any model)
to solicit NEW compound specs for the Oracle research factory. The pack is
self-contained: rule grammar, available columns/events, mechanism families,
output format — and, critically, the ALREADY-EXPLORED section is read LIVE
from the committed registry + trial ledger + the adjudicated nulls, so the
external model cannot waste tokens re-proposing tested ground and the
dedup context can never go stale (it is generated, not maintained).

Nothing the external model returns is executed: it returns compound-spec
JSON only; the grammar firewall (engine/oracle/compounds.py) is the sole
evaluator. Paste returned specs into data/oracle/compounds/registry.jsonl
(or hand them to any Claude session) and run:

    python -m scripts.oracle_screen --all-pending --data-dir <MAIN>/data

Usage:  python -m scripts.oracle_brainstorm_pack [--n 10] > /tmp/pack.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.compounds import GRAMMAR_VERSION, VALID_OPS  # noqa: E402
from engine.oracle.panel import COLUMN_SCHEMA  # noqa: E402

REG = ROOT / "data" / "oracle" / "compounds" / "registry.jsonl"
LEDGER = ROOT / "data" / "oracle" / "compounds" / "trial_ledger.jsonl"

# The adjudicated nulls — the ground an external model must NOT re-till.
# Source: ORACLE_GAUNTLET_P3_ADJUDICATION.md (+P8/P3b). Keep in sync on
# any new adjudication (the sentinel of this file is the adjudicator).
_KNOWN_NULLS = """\
- RS-acceleration CONTINUATION at confirmed tier: NULL both directions (P3).
- Plain cross-sectional sector momentum ranking: rank-IC ≈ 0 (repo canon).
- Standalone 2W StochRSI washout-turn on sector ETFs, POOLED: NULL — loses
  to the existing validated BUY state (P8). Per-sector variants are OPEN but
  need registration; do not propose the pooled version again.
- Entry AFTER acceleration has begun (washout x accel-already-positive):
  significantly NEGATIVE — late entries are anti-edge (P8 cond_a).
- Defensive-rotation -> vol-shock prediction: falsified (DEFENSIVE_ROTATION.md).
- 28 of 34 high-VIX routing cells: small-n bootstrap artifacts (P3b placebo)."""

# Tier-1 screen priors from external-brainstorm rounds 1-2 (2026-07-04). NOT
# gauntleted — treat as strong priors, not proofs. The individual compounds and
# their numbers appear live in the "Specced/screened" section above; these are
# the GENERALISED shape-lessons so the model does not re-propose a trivially
# different variant of a screened-dead family.
_SCREEN_PRIORS = """\
- Leadership CONTINUATION (rs>0 + persistence/breadth/cohesion, NO flow-event
  trigger): flat-to-negative on tier-s (round-1 B1 -1.5%, B2 -3.3%, D2 -0.9%,
  C1 -0.5%). "Quiet leadership" / "group-confirmed RS turn" variants are the
  dead unconditioned-momentum null wearing conditioners. Do not re-propose.
- A high hit-rate at tiny n is NOISE, not edge (round-1 A4: +5.5% / 86% hit at
  n=21; round-2 F2: +3.3% / 71% at n=50, era 2/4; E2: +2.8% but 43% hit at
  n=68 — all sampling/skew mirages that fail the floor). See COVERAGE FLOOR.
- Participation-STATE gating (breadth_50>=~0.5 / rs>=0 / cohesion>=x as the
  PRIMARY entry condition, no flow-event or washout trigger): flat-to-negative
  across EVERY family on tier-s (round-2 B3 -1.2%, A6 -1.3%, C3 -1.3%, C5 -1.7%,
  B4 -1.2%, all n>=290). Buying "healthy participation" is not an edge — that
  participation is already priced. Do not gate on breadth/cohesion state; use
  them at most as a secondary filter behind a genuine flow/washout trigger."""


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_pack(n_requested: int = 10) -> str:
    compounds = _jsonl(REG)
    trials = _jsonl(LEDGER)
    eff_by_id: dict[str, str] = {}
    for t in trials:
        cid = t.get("compound_id")
        e63, h63 = t.get("effect_63d"), t.get("hit_63d")
        if cid and e63 is not None:
            eff_by_id[cid] = (f"screened: effect63={e63*100:+.2f}% "
                              f"hit63={(h63 or 0)*100:.1f}% n={t.get('n')}")

    tested_lines = []
    for c in compounds:
        cid = c.get("id", "?")
        tested_lines.append(
            f"- [{cid}] {c.get('name','')}: rule={json.dumps(c.get('entry_rule'))} "
            f"({eff_by_id.get(cid, 'not yet screened')})")

    episode_fields = ("direction(in|out), tier(onset|confirmed|undeniable), "
                      "complex_scope(same|opposite|any), within_sessions, min_count "
                      "(min_count = DISTINCT nodes)")

    return f"""\
=== ORACLE COMPOUND BRAINSTORM PACK (grammar v{GRAMMAR_VERSION}; generated live) ===

ROLE: You are a quantitative idea generator for a sector-rotation research
factory. You produce COMPOUND SPECS (JSON) — declarative entry rules over a
daily panel of US sector/subsector rotation features. You NEVER write code,
never claim validation, and never re-propose tested ground (listed below).
Your specs are screened mechanically by a causality-safe evaluator; effects
are measured, counted, and only survivors are promoted. Volume and mechanism
diversity are what you are good for — propose {n_requested} NEW compounds.

THE GRAMMAR (your entire vocabulary — specs outside it are rejected):
- Conditions: {{"col": <column>, "op": <one of {sorted(VALID_OPS)}>, "value": <number>}}
  or {{"col": a, "op": ..., "value_col": b}} (column-vs-column).
- Episode events: {{"episode_event": {{{episode_fields}}}}}.
- Combine with {{"all": [...]}} / {{"any": [...]}}. Entry = rule true as-of day t,
  executed next daily close. Everything is joined strictly as-of t (no lookahead
  is possible — the evaluator guarantees it).
- Universe: {{"tier": "s"}} (11 sector ETFs, 1998->, survivorship-clean — claims
  live here) or {{"tier": "m"}} (354 subsectors/themes/baskets, 2021->, watermarked).
- Horizons: [21, 63] sessions, excess vs benchmark.

AVAILABLE PANEL COLUMNS (per node per day, all causal):
{", ".join(COLUMN_SCHEMA)}

MECHANISM FAMILIES ALREADY MAPPED (extend them or propose NEW families —
say which): A conservation/routing (money must go somewhere), B sector
personality, C velocity-shift microstructure, D macro-regime conditioning,
E positioning (data still accruing), F information flow. Full prose:
research/ORACLE_COMPOUND_LIBRARY.md.

=== ALREADY EXPLORED — DO NOT RE-PROPOSE THESE OR TRIVIAL VARIANTS ===
Specced/screened compounds ({len(compounds)}):
{chr(10).join(tested_lines) if tested_lines else "(none yet)"}

Adjudicated dead ends (pre-registered tests; do not re-till):
{_KNOWN_NULLS}

Tier-1 screen priors (round-1 brainstorm; strong priors, NOT gauntleted):
{_SCREEN_PRIORS}

=== OUTPUT FORMAT (return ONLY a JSON list of specs) ===
[{{"id": "<SHORT_UNIQUE_ID>", "family": "<A-F or NEW:<name>>",
  "name": "<what the rule does — plain>",
  "mechanism_en": "<WHY money-flow mechanics make this footprint — must
    describe what the rule EXECUTES, no aspirational claims>",
  "entry_rule": {{...grammar...}}, "universe": {{"tier": "s"}},
  "horizons": [21, 63], "status": "exploratory",
  "lineage": "external-brainstorm <model> <date>"}}]

RULES: mechanism_en must match the rule (truth-in-labeling is enforced by
review); prefer tier "s" for anything you'd want promotable; conditioning
compounds (X only-when Y) beat raw signals here — the measured nulls above
show unconditioned signals are dead; diversity across families beats ten
variants of one idea.

COVERAGE FLOOR (hard): only propose rules you expect to TRIGGER >=100 times
across 11 ETFs over 1998-> (roughly 4+ entries/yr). Rules gated on rare
multi-node episode cascades, deep tier requirements, or narrow numeric bands
screen at n<30 and CANNOT be promoted — a strong hit-rate at n=20 is a
sampling mirage, not an edge (see screen priors). Favour conditioners that
fire often enough to measure: broad regime/flow states over rare coincidences.
=== END PACK ===
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10, help="compounds to request")
    args = ap.parse_args()
    print(build_pack(args.n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
