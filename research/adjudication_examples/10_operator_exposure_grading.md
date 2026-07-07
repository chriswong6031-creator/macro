# Operator Exposure Grading — Measurement Substrate Without Promotion

**Source:** PRs #1702 (W-EX exposure log, Next-3 program), #1669 (DQ-2 operator-action grading harness, Next-Five-Lobes program). Primary docs: `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` (RUL-U6), `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md` (RUL-N8). **Status:** canonical (RUL-SUCC-8).

## What was asked

The Decision-Quality / Operator Self-Model program proposed grading operator actions against machine claims and measuring what the operator was shown (exposure denominator) vs what they acted on. Two complementary builds were proposed: (a) DQ-2 grading harness (grades past actions against qledger outcomes), and (b) operator exposure log (records what was shown). The question was how to build both without creating a scoring engine, granting authority, or opening new trial families prematurely.

## What was decided (the holding)

- **RUL-N8 (DQ-2 shape — measurement-substrate-only):** the grading harness is pure after-the-fact measurement. No summary statistic publishes below n>=25 graded operator actions per contrast (the cortex A2 Wilson floor). Below floor: `{state:'accruing', n_actions, n_matched, n_graded}` only. Operator overrides are graded, never treated as authority. Output artifact is git-committed small JSON with a named single writer.
- **Three frozen contrasts pre-outcome:** the family `fdr_family='operator'` declares budget 3 BEFORE any run: (1) `overrode` — operator direction vs machine-claim graded outcome; (2) `dismissed`-then-worked rate vs matched acted base rate; (3) `acted`-then-failed rate vs matched dismissed base rate. These contrasts are registered before data is examined (BH imported verbatim from btc_override_ledger precedent, q=0.10).
- **No LLM scoring:** categorical findings only from graded claim outcomes; LLM-authored confidence scores are forbidden (RF-16 / house law). The grader joins `action_ledger.jsonl` to `data/qledger/grades.jsonl` on `claim_id` and uses measured forward outcomes, never LLM-assessed quality.
- **Accruing state (n<25):** the DQ-2 artifact carries `state='accruing'` until the Wilson floor is met. No chip, no site surface, no display until floor. The artifact is consumable later by the evidence panel as an accrual clock row.
- **RUL-U6 (W-EX exposure log — measurement-substrate-only):** the exposure log computes NO statistics, NO contrasts, registers NO trials. It records what the operator was shown. Storage: row log gitignored host-local (`data/operator/exposure_log.jsonl`, append-only, deduped on (surface, surface_id, as_of)); committed summary `data/governance/operator_exposure_summary.json` (bounded 90 days, single-writer).
- **Exposure date = artifact `as_of`, never run date:** verified against daily.yml job split — the artifact's `as_of` is the business date of the data, not the wall-clock time the script ran.
- **Deterministic joins only:** exposure rows are deterministic joins of committed site artifacts; no LLM calls, no scoring, no contrasts at build time.
- **Any exposure-conditioned contrast is a future prereg:** come-back 2026-09-15 registered for lobe impact attribution. RUL-U6 explicitly defers all statistical analysis to a future prereg citing this artifact.
- **No promotion from DQ-2 alone:** #1669's three contrasts stay frozen; any exposure-conditioned contrast is a future prereg. DQ-2 reaching floor (n>=25) allows Wilson intervals to publish; it does not trigger any authority or board change.
- **Flat row schema (no DecisionPacket cross-lobe fields):** the Codex proposal included a canonical cross-lobe DecisionPacket schema (routing short-side -> options -> DQ evidence). This was rejected as a prohibited fused-escalation shape (RUL-N2). The useful residue — stable ids, as_of, surface, artifact refs on every exposure row — folds into the W-EX row schema flat, with no cross-lobe conditioning fields.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Create DQ-2 grading harness (accruing, n<25 floor) | new measurement artifact | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| Pre-register 3 frozen contrasts (family 'operator') | new FDR family registration | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| Create W-EX exposure log (no stats, no contrasts) | new measurement substrate | **T0** (ROUTINE) | Opus alone |
| Kill DecisionPacket cross-lobe schema | reject prohibited fused-escalation shape | **T0** (ROUTINE) | Opus alone |
| Future exposure-conditioned contrast | new study requiring prereg | **T1** (CONSEQUENTIAL) when proposed | Opus + packet at that time |
| DQ-2 stats publish (when n>=25 floor met) | descriptor-only publication | **T0** (ROUTINE when floor met) | Opus alone |

The DQ-2 harness is T1 at creation because it registers a new FDR family (`operator`) with declared budget 3; this is a CONSEQUENTIAL decision that reserves trial budget. The exposure log (W-EX) is T0 because it computes no statistics and registers no trials — pure measurement substrate.

## Lenses that did the work

- **Statistics:** the Wilson floor (n>=25) before any statistic publishes is the core discipline. The DQ-2 family inherits the btc_override_ledger precedent verbatim (budget 3, BH q=0.10, Wilson intervals); importing verbatim rather than re-implementing avoids subtle differences in the BH correction. Pre-registering the three contrasts before data is examined prevents forking paths on what "grading operator actions" means.
- **Authority:** DQ-2 grades operator actions against machine claims, but the operator's override is never treated as an authority grant. The output artifact is display-only governance measurement; it carries no promotion path and no board consumer.
- **Privacy:** the exposure log is gitignored host-local (the operator's decision log contains potentially sensitive trading context); only the bounded summary is committed. Exposure date = artifact `as_of` ensures no temporal leakage from run timing into the denominator.
- **Collision:** RUL-U2 (ownership seniority) fences #1669's frozen contrasts — any exposure-conditioned contrast is a future prereg, not a modification of the existing three. The lobe impact attribution come-back (2026-09-15) is registered to prevent the collision from happening implicitly.
- **Build feasibility:** the action ledger is gitignored server-local; the grader runs on the host that has it (Mac ops lane, manual/ops cadence). Synthetic fixtures only in tests (no dependence on real ledger data in CI).

## Citable holding

Measuring operator behavior against machine outcomes requires pre-registering the contrasts before any data is examined, enforcing a Wilson-floor (n>=25) before any statistic publishes, and treating the exposure log as a pure measurement substrate with no statistics, contrasts, or trials — any analysis of the denominator is a future prereg, not a feature of the substrate build.

## Ruling IDs

RUL-U6 (exposure log measurement-substrate-only), RUL-N8 (DQ-2 accruing shape), RUL-N2 (fused-escalation prohibited), RUL-N4 (qledger substrate); also RUL-SUCC-4 (LLM-scored operator actions are never-approvable)
