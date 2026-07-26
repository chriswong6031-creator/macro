# W4 — Outcome Spine, partial pooling, arm-by-evidence

Phase 3 of the Engine Fix Masterplan. Closes the loop that audit #13 named: *"a suite full
of accountability ledgers where measurement never touches the arithmetic that trades"*. Grades
now move deterministic weights — safely, gated behind an arming predicate, never an env flag.

## What shipped

| Piece | Module | Audit |
|-------|--------|-------|
| The Spine contract | `engine/spine.py` + `data/spine/predictions.parquet` | #13 |
| Partial pooling (3 safety properties + arming) | `engine/pooling.py` | #13 #19 |
| SHADOW deterministic desk weights | `engine/desk_scorer.py::desk_weights` | #13 #19 |
| IC-aware alert severity | `engine/alert_triage.py::ic_severity_cap` | #42 |
| Convergence honesty (co-firing + accrual) | `engine/altdata_signals.py` | #23 |
| Badge passport (shared helper + build check) | `engine/passport.py`, `scripts/check_badge_passport.py` | #41 |

## The Spine contract

Every decision-facing signal writes a prediction row
`{signal_id, engine@version, family, as_of, symbol/universe, horizon, score, size_binding,
direction, event_key}`. Rows do **not** carry an outcome at emission — they MATURE through
`engine/grading.py` conventions (next-bar fill, survivorship-aware, delisting terminals), so
the spine never re-derives a second (flattering) fill/return convention.

**Emitters wired (adapters, not duplicate loggers):**
- `us_board` — the US Buy Board ledger (`data/us_board_ledger/retro_grades.parquet`,
  macro#812). BOTH lanes: `buy` (size-binding, direction +1), `watch` (context +1),
  `laggards` (direction −1, a short-lean lane graded sign-inverted).
- `altdata_conv` — the alt-data convergence ledger (`engine/altdata_ledger`), carrying the
  co-firing channel set per thesis (`event_key` = the thesis id).
- `desk:{name}` — every Phase-C desk's `scored.jsonl` (`engine/desk_scorer`), a `miss`
  encoded as a NEGATIVE signed outcome so a wrong desk's pooled weight can go negative.

Verified live against real committed ledgers: **651 spine rows** (529 us_board, 120
altdata_conv, 2 desk), **531 graded**. `us_board:buy` measured IC **+0.021** (hit-rate 65.7%,
n=437). `altdata:convergence` **n=0 matured** — correctly accruing (63d horizon, confirms #23).

## Partial pooling — the three hard safety properties

`engine/pooling.py`, hierarchical empirical-Bayes shrinkage. Constants mirror the
`risk_radar_intl` bounded-tuner (the reference closed loop).

**(a) Shrink toward ZERO, not optimism.** Global prior is 0 (no edge). `pooled_weight` is a
shrunken *signed* mean; a reliably-wrong leg keeps a NEGATIVE pooled edge and lands BELOW
equal-weight. (China reassessment Q6: two proposed confirmer legs measured wrong-sign;
shrinking toward a "weakly positive" prior would institutionalize a drain.)

**(b) Hierarchical.** Per-member weights shrink toward the precision-weighted family mean,
which itself shrinks toward the global 0. n=5 in a family of 6 borrows strength from its
siblings and moves a little — killing the `min_n=20 else 1.0` cliff (#19).

**(c) Trust-region + capability gates.** `trust_region_step` moves at most `MAX_STEP=0.10`
(L1, mass-conserving — the largest move is scaled to the cap, no renorm blow-up). Nothing
arms until the arming predicate holds. Never free-fits on tiny n.

Measurement-error inflation from leakage-tax flip rates (Q6) enters as an optional per-member
`noise` that reduces reliability — a replay-fragile leg is trusted less.

## The arming predicates (arm-by-evidence, no env flags)

All conditions required; `engine/pooling.arming` computes the status + distance-to-arming.

1. **≥ `MIN_FAMILY_N` (=12) effective graded events** in the family. *Effective* = co-firing
   collapsed: rows sharing an `event_key` count as ONE observation, so 20 channels firing on
   one 8-K = 1 event, not 20.
2. **A held-out tail that can decide.** ≥ `ARM_MIN_HELDOUT_N` (=8) distinct events in the
   chronological tail (`HELDOUT_FRAC=0.3`), carrying ≥ `ARM_MIN_MEMBERS` (=2) contributing
   members. With one member the pooled and equal-weight vectors are the SAME allocation, so
   the comparison is vacuous — arithmetic, not evidence.
3. **Pooled weights WIN out-of-sample.** The pooled vector's realized held-out edge must be
   POSITIVE (`ARM_REQUIRE_POSITIVE_EDGE`). `pooled_weights` yields a convex allocation and
   cannot go short, so a negative held-out edge means every allocation over this family loses
   — "loses less than equal-weight" is not an edge.
4. **…by a pre-registered MARGIN.** The edge must clear equal-weight by
   `max(ARM_MIN_MARGIN=0.0005, ARM_MIN_MARGIN_REL=0.03 × the tail's mean |outcome|)`.
   Pooling must EARN the flip; it is never armed on in-sample fit, on a hair's-breadth lift,
   or on float dust.

**Why 3 and 4 exist (added 2026-07-25).** Conditions 1-2 originally read as a bare
`heldout_edge_pooled > heldout_edge_equal` float comparison with no floor. Measured on the
live spine, that armed the live weight path on margins down to **3e-18** — machine epsilon —
and at every armed point BOTH held-out edges were NEGATIVE (the family lost out-of-sample
either way; pooled just lost ~3bp less). The margins that provoked the change measured
**1.2% of the held-out outcome scale**, which simulation puts *inside* the pure-noise band
(p99 ≤ 1.5%, max 2.4% over 2500 noise draws at every permitted tail size), while a genuinely
separated family delivers 2.3-5.9%. The 3% bar therefore sits above the noise and below the
`tanh`-bounded mechanism's own ceiling, so a real edge can still arm. Arming is a PROMOTION
to authority, so it now carries the same class of bar as
`calibration_hub._PROMOTE_MARGIN = 0.05`; full reasoning in the `engine/pooling` module
docstring, pinned by `tests/test_pooling.py`.

**First live client — `desk_scorer.desk_weights` (SHADOW-FIRST).** It computes the pooled
weights, emits them alongside the equal-weight baseline, logs the L1 divergence, and writes
`data/desk_weights/shadow.json`. `live_weights == equal_weight` until the family arms; once
armed, `live_weights` becomes the trust-region-stepped pooled vector and the loop is closed.
Current state (real data): **not armed** — 17 effective desk events, but only `ai_desk`
contributes, so the held-out tail is 5/8 and no pooled-vs-equal test can run yet. `ai_desk`
(all-miss) already shows a negative pooled edge and a shadow weight nudged below equal-weight.
The mechanism is proven; the flip waits on evidence.

## IC-aware alert severity (#42 durable form)

`ic_severity_cap` makes the hardcoded per-event severity a PRIOR that measured performance
overrides (bounded):
- a spine-governed emitter with measured IC > 0 keeps its band (earned);
- a spine-governed emitter measured null / wrong-sign → capped to `minor`;
- a spine-governed emitter still cold (n<12) → band unchanged (honest accrual);
- a **documented-null** emitter (narrative-rotation `entered_book`/`left_book`, rank-IC≈0 per
  `baskets_calibration`) → capped to `minor` NOW, upgrading to spine governance the moment a
  rotation spine emitter accrues n>0.

Net: a null-edge display event can never outrank a validated risk-off signal in the Alert
Center — exactly #42's requirement.

## Convergence tier honesty (#23)

`altdata_signals.convergence_tier`:
- **Co-firing penalty** — the tier is built on the CO-FIRING-ADJUSTED independent-event count
  (`cofiring_adjusted_score`), not the raw channel count. One 8-K lighting 3 channels is
  cof=1 and can no longer mint a `high`.
- **Accrual-aware** — `basis` is `prior` (n=0) until the spine's convergence ledger matures,
  then `measured` with the real hit-rate. A measured null/negative edge demotes `high`→`medium`.
- **Honest caveat** — the "weight by track record" language only renders once n_scored>0;
  until then the chip says *"TRACK RECORD ACCRUING (n=0 matured): this tier is a PRIOR, not an
  earned weight."*

## Badge passport (#41)

`engine/passport.py` — one place decision provenance becomes a badge. States: `measured`
(spine n>0, earned), `accruing` (n=0, a prior), `unfitted` (hardcoded table), `stale` (a
frozen self-certifying gate past its cadence), `prior` (deliberate hand-set). Desk cards call
`passport_from_spine(f"desk:{name}")`; a cold desk renders `accruing · n=0` instead of a bare
conviction word. `scripts/check_badge_passport.py` is the ratchet: a desk brief that renders a
conviction badge with no valid passport fails the build (legacy allowlist only shrinks).

## Tests

`tests/test_pooling.py` (16) + `tests/test_spine.py` (19): sign-safety (a wrong-sign leg goes
negative and under equal-weight), trust-region bound (no key moves > MAX_STEP), cold-start
(n=0 → equal weights, empty members no crash), the arming predicate (blocks below MIN_FAMILY_N,
collapses co-firing to one event, requires pooled-beats-equal out-of-sample, holds when there's
no separable edge), sign-inversion for veto seats, the IC severity cap, convergence co-firing +
accrual honesty, and the passport states. All green; no regressions in the 5 adjacent suites.
