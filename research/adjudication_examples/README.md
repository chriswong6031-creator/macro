# Adjudication Examples — Canonical Case Law Corpus

**Status:** normative, ratified by RUL-SUCC-8 (see `research/FABLE_SUCCESSION_OPERATING_SYSTEM.md`).
**Purpose:** these files are training data for the bench. Future Opus adjudicators cite examples by file when pattern-matching decisions against case law. They are not constraints on outcomes — they are precedent.

---

## Index

| File | One-line holding | Tier the case maps to |
|---|---|---|
| `01_rf_batch_a_paper_and_duplicate_kills.md` | The RF challenger is advisory-only; kills at human-gate states are human-authored with kill_evidence; a duplicate kill at n_at_kill is equal scientific output to a promotion. | T0 (paper/reject are ROUTINE with packet_ref per RUL-SUCC-7) |
| `02_three_lobes_zero_charter.md` | When a lobe proposal decomposes entirely into existing-artifact waves and gated studies, the taxonomy verdict is zero charters; the two-lobe concurrency cap is case law that blocks T2 approval while consumed. | T0 denial; T1 for authorized waves; T2 would be required to charter any lobe |
| `03_final3_reshape_kill_defer.md` | Partial adoption is the expected outcome for a large multi-item docket; kill forbidden shapes (governor bypass, look-ahead labels), adopt clean items with scope fences, defer n-starved or cap-blocked work with named unblock conditions. | T0 for kills; T1 for authorized waves (TRIM-GRID-1, NET-REPLAY-1); T2 would be required for any lobe |
| `04_r_orth_rail_not_lobe.md` | When proposed lobe functionality decomposes into reading existing system outputs plus one new cross-system accounting artifact, the correct taxonomy is rail at infrastructure tier; any orthogonality metric must carry its within-window null distribution. | T0 for taxonomy call (clear precedent); T1 for null-calibration law; T2 would be required for lobe charter |
| `05_rf_cortex_batch_b.md` | Factory infrastructure for an LLM-adjacent pipeline requires mechanical enforcement at every boundary where double-counting, self-reference, or authority escalation could silently occur; ARMED with named ops action is correct when hardening is complete but an external block prevents triggering. | T0 for hardening; T1 for budget reaffirmation |
| `06_factor_dark_scaffold_activation_floor.md` | A de-escalation scaffold that reads only committed artifacts and refuses to fire clamp logic without a GATE-PASSED artifact, with a 25-event/3-month activation floor, is the legally sufficient form for shipping conditional authority features dark. | T0 for dark scaffold; T1 for activation floor rule; T2 if clamps ever proposed to fire without GATE-PASSED |
| `07_mastermind_bridge_context_only.md` | A cross-repo context bridge is born with all five authority booleans false and dark-ship default OFF; the five Mastermind authority booleans are the privacy floor (RUL-SUCC-11) required in any future packet touching the bridge. | T2 at birth (public/private boundary); T0 for additive display keys; RUL-SUCC-11 hard-block if authority booleans missing from packet |
| `08_cycle_pattern_truth_null_status.md` | A truth registry that treats promoted_null status as equal to a positive finding — actively blocking duplicate registration — is the correct architecture for preventing re-belief of buried nulls; deletion of null history is a never-approvable invariant (RUL-SUCC-4). | T1 for registry creation; T0 for seed migration; INV for any deletion of null history |
| `09_l6p0_macro_transmission_axes.md` | A gate-clearing study PASS (one of four axes) re-opens the charter question as a T0 decision; it does not auto-charter a new lobe, does not grant authority, and does not supersede the two-lobe cap; the charter itself is always T2. | T0 for recording PASS/FAIL; T2 for any subsequent charter attempt |
| `10_operator_exposure_grading.md` | Measuring operator behavior requires pre-registered contrasts before data is examined, a Wilson-floor (n>=25) before any statistic publishes, and the exposure log as pure measurement substrate with no statistics, contrasts, or trials at build time. | T1 for DQ-2 (new FDR family); T0 for exposure log (no trials); INV for any LLM-scored operator confidence numbers |

---

## How to use this corpus

1. When a new adjudication request arrives, scan this index for the closest matching case by topic.
2. Read the full case file to understand which lenses fired and which rulings governed.
3. Cite the example file in the packet's `case_law.ruling_hits` field (per RUL-SUCC-9: the ruling index at `data/neuralweb/ruling_index.json` provides ruling IDs; example files provide context and pattern).
4. If no example matches, the case is novel — escalate the tier, not reduce it (RUL-SUCC-2: when in doubt, classify up).

## Anti-patterns illustrated across this corpus

- **Misfiling waves as lobes:** cases 02, 03, 04, 05 all show cases where a proposed lobe decomposes into waves, rails, or infrastructure — zero charters is the correct verdict.
- **LLM origination / auto-promotion:** cases 01, 05, 10 all show the boundary between advisory-only Opus findings and human-gate authority. LLM findings never drive terminal kill or escalation without human authorship of the decision.
- **Statistics before registration:** cases 08, 09, 10 all illustrate pre-registration before any data is examined; the `promoted_null` and `derived_from_surface` mechanisms prevent re-belief and budget laundering.
- **Authority booleans as behavior wires:** cases 06 and 07 both illustrate the rule that a JSON boolean must never gate live behavior; authority is granted only by `constitution.grant_authority` after graded probation.
- **Deletion of null history:** case 08 illustrates directly — a `promoted_null` truth entry blocks future duplicates; it is never deleted. This is INV (RUL-SUCC-4 invariant 3).
