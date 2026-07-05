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
  them at most as a secondary filter behind a genuine flow/washout trigger.
  (Caveat: these used 2021+-only columns, so the sample is 2021-2026, not
  all-history — negative on available data, but that is NOT cross-era death;
  and being 2021+-only they are un-promotable regardless. See HISTORY COVERAGE.)
- cohesion_rebuild as the PRIMARY trigger: weak/dead on tier-s (round-3 A10
  n=80 & A11 n=77 both era 1; F3 +0.29% era 1; F4 -0.17%). The rebuild flag
  fires too sparsely and doesn't hold across eras — do NOT use it as the
  trigger; at most a secondary filter behind washout/flow.
- Benign-macro conditioners on washout DILUTE the edge: washout x rate-relief
  (round-3 D5) collapsed to +0.13% at n=3790. The STRESS is the edge — do not
  filter washout down to calm-macro states."""

# The positive counterpart to the nulls: where screened effect has ACTUALLY
# appeared. Rounds 1-2 (20 specs) found nothing in participation state; round-3
# (10 washout/rebuild specs) CONFIRMED the washout basin is live and era-
# consistent. CONCENTRATE here and try to BEAT the current best (A9).
_LIVE_REGIONS = """\
CONFIRMED (round-3): the washout_w basin is LIVE and era-consistent, unlike
participation state. The edge is capitulation + ACTIVE FLOW STRESS:
- washout_w>0 x SAME-COMPLEX dense outflow (A9: out/onset/same, min_count>=2)
  SCREENED +1.06% / 55.0% hit / n=438 / era 3/4 — CLEARS the promotion floor.
  This is the current best; your job is to BEAT it or find an independent one.
- washout_w>0 x opposite-complex outflow (A8) +0.82% / 54.5% / era 3 — a hair
  under the floor. washout_w>0 x turnover stress (E3) +0.96% / era 2.
- the whole washout family screens directionally positive at large n; benign-
  macro filters (rate-relief) DILUTE it — the stress is the edge.
UNDEREXPLORED — try to BEAT A9 (keep COVERAGE FLOOR >=100x; aim era 3-4/4,
hit>=55% OR |effect63|>=1%):
- vary the outflow conditioner on washout: tier (onset vs confirmed),
  min_count (2 vs 3), within_sessions (10/15/20), scope (same/opposite/any);
- washout x a velocity/positioning stress OTHER than turnover_z (e.g. vel_1w
  deeply negative, accel_z low) — a different read on "stress being processed";
- washout x cohesion_chg>0 (rebuilding) at a LOOSER threshold than C4's 0.056
  to lift n while keeping the rebuild signal.
AVOID (screened dead): cohesion_rebuild as the primary trigger; benign-macro-
only filters on washout; anything in the participation-state basin."""

# --explore mode: maximise mechanism DIVERSITY instead of drilling one basin.
# The goal is a wide, cheap net (200-500 specs accumulated over several runs)
# that the screen then sorts. This is the OPPOSITE pressure from the focus pack.
_FOCUS_SLICES = [
    ("velocity/acceleration microstructure", "vel_1w/vel_1m/vel_3m/accel/accel_z "
     "crossings, curve relationships (value_col comparisons), turning points"),
    ("breadth & cohesion structure", "breadth_50/cohesion/cohesion_chg/"
     "cohesion_rebuild DYNAMICS (changes/crossings), not static-level gates"),
    ("relative-strength regime & turns", "rs crossings, rs vs velocity, rs "
     "acceleration/deceleration turning points"),
    ("turnover & positioning", "turnover_z spikes/cooling/crossings, persistence "
     "regimes, positioning-stress reads"),
    ("macro-regime conditioning", "vix_pctile bands, tlt_ret_10d sign/turns, "
     "spy_above_200d — as GATES on a non-participation trigger, not the trigger"),
    ("episode-flow routing", "episode_event in/out x onset/confirmed/undeniable x "
     "same/opposite/any x min_count 1-3 x within 5-20 — the conservation family"),
    ("oscillator / mean-reversion", "stochrsi_w_k/stochrsi_w_d turns & crossings, "
     "washout_w used SPARINGLY (basin mapped), oscillator exhaustion"),
    ("cross-column & multi-leg composites", "column-vs-column value_col rules; "
     "3-leg rules pairing one novel trigger + a macro gate + a micro filter"),
]

_DIVERSITY_MANDATE = """\
MISSION: cast a WIDE net. Across several runs of this prompt the operator wants
200-500 DIVERSE specs; the mechanical screen then sorts them. Your job this run
is BREADTH, not depth on any one idea. Do NOT converge on the washout basin
(already mapped) — spend <=10% of proposals there.

MECHANISM COVERAGE GRID — sample widely across all of it:
- TRIGGER (the event that fires the entry): use MANY different primitives —
  every panel column should appear as a trigger somewhere in the batch, via
  crossings (crossed_above/below a level OR another column) or regime turns;
  AND episode_event triggers (in/out x tiers x scopes x min_count).
- CONDITIONER (0-2 secondary filters): macro regime (vix/tlt/spy), microstructure
  (turnover_z/persistence/accel_z), or a cross-column comparison.
- Use ALL SIX ops. Use BOTH episode-event and panel-condition triggers. Use BOTH
  in and out episode directions. Propose genuinely NEW families (NEW:<name>).

DIVERSITY RULES (enforced by review — near-duplicates are wasted volume):
- <=3 specs may share the same TRIGGER primitive; vary the conditioner/threshold.
- Each spec must tell a DISTINCT money-flow story (mechanism_en must differ).
- Mix leg-counts: some 1-leg triggers, many 2-3 leg conditioned rules.
- Span the grid; do not cluster on the two or three most obvious ideas."""


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


def build_pack(n_requested: int = 10, mode: str = "focus",
               focus: int | None = None) -> str:
    compounds = _jsonl(REG)
    trials = _jsonl(LEDGER)
    eff_by_id: dict[str, str] = {}
    eff_num: dict[str, float] = {}
    for t in trials:
        cid = t.get("compound_id")
        e63, h63 = t.get("effect_63d"), t.get("hit_63d")
        if cid and e63 is not None:
            eff_by_id[cid] = (f"screened: effect63={e63*100:+.2f}% "
                              f"hit63={(h63 or 0)*100:.1f}% n={t.get('n')}")
            eff_num[cid] = e63

    # Compaction: as the registry grows past ~40, listing every dead compound
    # bloats the prompt.  The ingest (oracle_ingest_brainstorm) hard-dedups exact
    # repeats regardless, so the prompt only needs the NOTABLE results verbatim
    # (|effect63| >= 0.7% either sign, or not-yet-screened) plus a count of the
    # rest.  Dead SHAPES are already fenced in the screen priors below.
    _NOTABLE = 0.007
    tested_lines, noise_n = [], 0
    for c in compounds:
        cid = c.get("id", "?")
        e = eff_num.get(cid)
        if e is None or abs(e) >= _NOTABLE:
            tested_lines.append(
                f"- [{cid}] {c.get('name','')}: rule={json.dumps(c.get('entry_rule'))} "
                f"({eff_by_id.get(cid, 'not yet screened')})")
        else:
            noise_n += 1
    if noise_n:
        tested_lines.append(
            f"- (+ {noise_n} more screened as NOISE, |effect63|<0.7% — already "
            "tested, do not re-propose; the ingest hard-dedups exact repeats.)")

    episode_fields = ("direction(in|out), tier(onset|confirmed|undeniable), "
                      "complex_scope(same|opposite|any), within_sessions, min_count "
                      "(min_count = DISTINCT nodes)")

    # Mode-dependent sections -------------------------------------------------
    if mode == "explore":
        role_ask = (
            f"MAXIMISE mechanism DIVERSITY — propose {n_requested} DISTINCT "
            "compounds spanning as much of the mechanism space as you can.")
        if focus is not None and 1 <= focus <= len(_FOCUS_SLICES):
            name, detail = _FOCUS_SLICES[focus - 1]
            focus_line = (f"\nFOCUS THIS RUN — slice {focus}/{len(_FOCUS_SLICES)}: "
                          f"{name}.\n  {detail}\n  Spend the majority of this "
                          "batch here; the operator re-runs other slices separately.")
        else:
            slices = "\n".join(f"  {i+1}. {n} — {d}"
                               for i, (n, d) in enumerate(_FOCUS_SLICES))
            focus_line = ("\nSLICES (the operator re-runs this prompt with "
                          "--focus K to cover each; with none set, span them all):\n"
                          + slices)
        steer_title = "=== DIVERSITY MANDATE — SPAN THE WHOLE MECHANISM SPACE ==="
        steer_body = _DIVERSITY_MANDATE + focus_line
        extra_rules = (
            "\n\nEXPLORE MODE: breadth beats depth this run. Return as MANY unique "
            "specs as you can (do not stop at a token few); each must be a "
            "different mechanism. The screen sorts them — false starts are cheap, "
            "missed diversity is not.")
    else:  # focus mode (default): drill the current live basin
        role_ask = (
            "Volume and mechanism diversity are what you are good for — propose "
            f"{n_requested} NEW compounds.")
        steer_title = ("=== WHERE STRUCTURE HAS ACTUALLY APPEARED — "
                       "CONCENTRATE PROPOSALS HERE ===")
        steer_body = _LIVE_REGIONS
        extra_rules = ""

    return f"""\
=== ORACLE COMPOUND BRAINSTORM PACK (grammar v{GRAMMAR_VERSION}; mode={mode}; generated live) ===

ROLE: You are a quantitative idea generator for a sector-rotation research
factory. You produce COMPOUND SPECS (JSON) — declarative entry rules over a
daily panel of US sector/subsector rotation features. You NEVER write code,
never claim validation, and never re-propose tested ground (listed below).
Your specs are screened mechanically by a causality-safe evaluator; effects
are measured, counted, and only survivors are promoted. {role_ask}

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

COLUMN SCALES (wrong scale = a rule that never fires — respect these):
- 0-100: stochrsi_w_k, stochrsi_w_d (median ~56; use 20/50/80, NOT 0.2/0.8).
- 0-1: vix_pctile, breadth_50, persistence (~0.23-0.75), cohesion (~0.09-0.78).
- 0/1 flags: washout_w, spy_above_200d, cohesion_rebuild (use ">value":0 or ge 1).
- small decimals (daily/rolling returns): ret, vel_1w, vel_1m, vel_3m, accel,
  tlt_ret_10d, oil_ret_10d, dollar_chg_10d.  z-scores (~ -3..+3, tails to +-8):
  accel_z, turnover_z.
- macro spreads/levels (%pts or index units, NOT 0-1): yc_slope (~-1..+3;
  <0 = curve inverted), hy_oas_chg_10d (~-4..+5, 10d change in HY credit
  spread; >0 = credit stress rising), fin_conditions (NFCI ~-1..+3; >0 = tight).
- Do NOT value_col-compare columns of DIFFERENT scales (e.g. stochrsi vs rs,
  vix_pctile vs turnover_z) — the comparison is degenerate/always-true.

NEW cross-asset regime columns (full-history, just added — the FRESHEST,
least-explored mechanism space): hy_oas_chg_10d (credit stress), yc_slope
(yield curve), oil_ret_10d (energy), dollar_chg_10d (USD), fin_conditions
(NFCI).  Sector rotation is DRIVEN by these — energy<->oil, financials<->curve,
tech/materials<->dollar+credit.  PRIORITISE this run: novel triggers on them
(e.g. hy_oas_chg_10d crossed_above 0 = credit stress onset; yc_slope
crossed_below 0 = inversion) and conditioning the washout/flow edge on these
regimes.  All clear the era gate.

HISTORY COVERAGE (HARD promotability constraint):
- FULL history 1998->: ret, rs, vel_*, accel, accel_z, persistence, vix_pctile,
  tlt_ret_10d, spy_above_200d, washout_w, stochrsi_w_k/d, hy_oas_chg_10d (1999+),
  yc_slope (1998+), oil_ret_10d (1999+), fin_conditions (1999+),
  dollar_chg_10d (2006+ — 20y, still clears the gate).
- 2021+ ONLY (~5yr, ~13.5k rows): breadth_50, cohesion, cohesion_chg,
  turnover_z, cohesion_rebuild.  A rule CONDITIONED on any of these fires only
  post-2021, so it CANNOT clear the era-consistency gate (3 of 4 eras) and is
  NOT promotable.  Use them at most as an optional probe leg, NEVER as the edge.
  Prefer full-history columns for anything you want promotable.

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

Tier-1 screen priors (rounds 1-2 brainstorm; strong priors, NOT gauntleted):
{_SCREEN_PRIORS}

{steer_title}
{steer_body}

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
variants of one idea.{extra_rules}

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
    ap.add_argument("--explore", action="store_true",
                    help="diversity mode: cast a wide net across the whole "
                         "mechanism space (default is focus mode: drill the live basin)")
    ap.add_argument("--focus", type=int, default=None,
                    help=f"explore mode: pin this run to slice 1-{len(_FOCUS_SLICES)} "
                         "for systematic coverage across re-runs")
    args = ap.parse_args()
    mode = "explore" if args.explore else "focus"
    n_default = 60 if (args.explore and args.n == 10) else args.n
    print(build_pack(n_default, mode=mode, focus=args.focus))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
