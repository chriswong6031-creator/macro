# Stock Identity W3AR — Replay Eligibility + P2 Recovery Charter

**Date:** 2026-08-29  
**CEO owner:** Sol  
**Parent:** `WS:STOCK-IDENTITY` / `SI-FABLE-COO-PROGRAM-20260828`  
**Recovery operation:** `SI-W3AR-REPLAY-ELIGIBILITY-P2-V1`  
**Protected Skillpack basis:** `mastermindx-market-intelligence/Mastermind@e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5`, v1.0.1  
**Macro base:** `07e63c5877c1638ee533843d4f2b477c9a148176`  
**Status:** SOL RECOVERY CHARTER / RECORDS ONLY. No P2 draw, calibration read, new constant, Q1 outcome, Prophet authority, replay store, availability store, or production mutation is authorized by this file.

## 1. Why recovery is necessary

W3A Attempt-1 on PR #6638 reached a full 759-name read of `SI-SEALED-CAL-P1`, but Sol rejected the milestone after discovering that the availability population was not lawful: generic family `spec_hash` existence had been allowed to stand in for the date-specific source/era eligibility required by the then-current Sol ruling. The implementation was repaired fail-closed, but that repair changed population-determining code after P1 values were observed. Under the accepted one-time-law, P1 cannot be read again for this constant family. PR #6638 is closed unmerged at exact head `f0b265f82cc7066a4e8d0b87a8fd62a64dd10177`; Attempt-1 remains immutable rejected evidence.

The program itself is not killed by that implementation failure. The original frozen research contract still licenses a historical evidence program built from stored ledgers and **era-pinned, leak-tested replay**, including Class-B locked-spec backcasts, while Class-P families remain prospective-only. Recovery must therefore resolve whether the later availability ruling accidentally conflated two different clocks before any new calibration population is drawn.

## 2. The recovery question

The next scientific question is deliberately upstream of calibration:

> Can Stock Identity define an outcome-independent **historical replay-eligibility** contract, distinct from **live/prospective availability**, that is faithful to the original W2 replay registration and `DNR:KILL-OUTCOME-AUDITION`, and does that contract leave enough untouched clean names/episodes to support a fresh one-look PR-3 calibration epoch without touching P1 or the blind arm?

No P2 membership may be drawn until this question is answered and Sol accepts the feasibility packet.

## 3. Two-clock architecture to investigate and either prove or reject

Recovery begins from a strict separation; it is a hypothesis to validate against current source law, not a license to widen history:

### 3.1 Historical replay eligibility

`replay_eligible(family, instrument, date, grain)` answers only whether the **already-registered W2 historical research construction** could lawfully be evaluated at that date from PIT inputs without reading outcomes.

Candidate rules to validate per family:

- **Class R — ledger-only:** eligible only where the registered canonical ledger actually supplies lawful history, unless W2 already registered a separate recompute arm.
- **Class R — registered recompute:** may be historically replay-eligible where the exact W2-registered producer/recompute method is frozen, causality/leak fixtures hold, and all required PIT price/context/identity inputs exist. `spec_postdates_history` remains explicit where applicable.
- **Class B — locked-spec backcast:** may be historically replay-eligible only through the exact locked-spec W2 construction and only where its required PIT inputs exist. Its backcast status must remain visible; this is research replay, never a claim that the live detector existed then.
- **Class P / structurally non-reconstructable:** never historically replay-eligible; zero rows/backfill remains binding.
- If required replay method, source era, price/context input, identity, or grain support cannot be proven without using fire occurrence or outcome information, eligibility is typed unavailable/`UNESTIMABLE`.

Fire occurrence, realized localization, composite score, per-name expert rank, and outcome columns are forbidden inputs to eligibility.

### 3.2 Live/prospective availability

`live_available(family, date)` remains the production/forward clock: when the real family/source became knowable/usable in live operation. `family_first_available`, Radar known-at law, stored source vintages, and Class-P forward-only constraints govern this clock.

Historical replay eligibility may never be exported as a claim of historical live availability. W7 prospective evaluation uses live availability only.

### 3.3 Why the separation matters

The original W2 registration explicitly distinguishes ledger extraction, registered historical recomputation and Class-B locked-spec backcast, while reserving Class-P for prospective-only accrual. If those semantics are upheld, requiring every historical backcast to prove that its software/source was literally deployed on each historical date would erase the research construction W2 intentionally registered. If current authoritative source law instead proves that such backcast eligibility is not permitted, recovery must report that and stop; this charter does not prejudge the answer.

## 4. Clean-pool feasibility before P2

The W1 universe was 2,781 instruments. The blind arm (229 names) was drawn first and remains untouched. P1 used 759 drawn names after pilot/blind exclusion. On documented counts, roughly 1.77k instruments remained outside pilot + blind + P1 before later design-touch exclusions, so a disjoint P2 is feasible by **headcount**. Headcount is not scientific feasibility.

W3AR must build an outcome-free census over the still-clean pool and report:

1. exact clean-pool membership count + hash after excluding pilot, W1-A1 `B`, blind arm, all P1 names, and every additionally design-touched name discovered in archaeology;
2. per-family historical replay-eligibility method and source-law citation;
3. replay-eligible instrument/date/grain coverage by declared era, without localization/outcome/composite values;
4. whether the fixed A2/B1 calibration rules can receive a nondegenerate lawful input population under the recovered eligibility semantics;
5. how many clean names would remain for later grading under candidate P2 sizes;
6. any family that collapses to ledger-only / prospective-only under the audit.

The audit may inspect metadata, source presence, required-input coverage, replay method and causal fixtures. It may not inspect P1 calibration outputs beyond immutable contamination receipts, blind-arm per-name evidence, Q1 outcomes, or per-name fit rankings.

## 5. P2 may exist only after a Sol GO

If the recovery census is scientifically viable, return a preregistration proposal for a **new calibration epoch**, tentatively `SI-SEALED-CAL-P2`, with all of these properties:

- membership drawn only from the untouched clean pool; P1, pilot, W1-A1 B, blind and all design-touched names are disjoint;
- deterministic seed/procedure and sample-size rule fixed **before** membership is revealed;
- no membership selection based on fires, localization, fit, expert rank or outcomes;
- A2 recall-floor and B1 `lambda_fs` rule forms remain exactly the already-ruled forms unless a separately declared scientific amendment is accepted before any P2 read;
- the repaired historical replay-eligibility implementation is independently reviewed before the P2 draw/read;
- P2 has one look for the PR-3 constant family. Failure/degeneracy blocks; no post-value fallback/rule switching;
- P1 remains permanently `REJECTED_ATTEMPT_1` and is never relabeled, overwritten, or pooled into P2;
- blind arm remains untouched and later confirmatory grading excludes both P1 and P2.

Sol must explicitly accept the W3AR feasibility/prereg packet before P2 is drawn. A worker may not mint P2 from this charter alone.

## 6. Salvaging useful W3A work without laundering Attempt-1

PR #6638 contains useful engine/null/control/test work, but its shipped `ruler_spec_v1.json` still mechanically says `pr3.status=sealed` with rejected constants. Therefore #6638 cannot be merged as a harmless foundation.

A later recovery implementation may selectively adopt/cherry-pick reviewed implementation concepts from the immutable #6638 head, but before any such code lands it must make rejected Attempt-1 constants **mechanically unusable**, not merely described as rejected. Prefer a separate superseding rejection/epoch contract over rewriting Attempt-1 bytes. No force-push/relabel of #6638; its exact head remains audit evidence.

## 7. Recovery outcomes

W3AR terminates in exactly one of:

- `GO_P2_PREREG`: replay-eligibility law is source-faithful, clean-pool support is adequate, and a P2 prereg is ready for Sol acceptance;
- `NO_GO_CALIBRATION_RECOVERY`: current lawful replay/support cannot supply a credible fresh calibration epoch; routing claim cannot proceed on historical PR-3 calibration under current data. Sol then adjudicates whether the program ends `NO_GO_KILL_ROUTING` or continues descriptive identity/epoch work only;
- `BLOCKED_NEW_SOURCE_LAW`: the question requires a new source/data authority rather than existing W2 owners; return to Sol before any collection.

No result in this wave grants W3A completion, W3B start, Q1 access, SIF authority or Prophet influence.

## 8. Parallel work

`SI-W3S-DEAD-CONTROL-V1` is independent of this scientific recovery and may restart in parallel after fresh changed-path/collision checks. It must follow the already-frozen bounded-source ruling: deterministic terminated-instrument sampling, reuse existing owner/Polygon dead-name collection surfaces, no second market-data plane, >=5 lawful full-adjusted terminated tapes or `BLOCKED_NO_LAWFUL_DATA`.

W3B remains held until an accepted W3A ruler/support schema exists.

## 9. Return packet

The W3AR principal returns one `DECISION_REQUEST` containing: current Skillpack/main pins; exact source-law reconciliation; per-family replay-eligibility table; clean-pool count/hash; outcome-free coverage census; candidate P2 sample-size/draw rule; grading-pool remainder; collision census; explicit no-P1/no-blind/no-outcome proofs; independent adversarial review; and one of the three recovery outcomes above. Then it waits for Sol. No P2 draw/read occurs before the Sol edge.