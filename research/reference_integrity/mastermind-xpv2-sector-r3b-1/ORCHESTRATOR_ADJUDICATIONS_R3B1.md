# XPV2-SC-R3B.1 — Orchestrator adjudications

Running record of every ruling the R3B.1 orchestrator (returning R3B Fable session) takes
executing Sol's surgical-fix commission (`COMMISSION.md` in this directory). Same convention
as the predecessor's `ORCHESTRATOR_ADJUDICATIONS.md`: rulings here are the cycle's audit
trail, not authority — Sol's commission and the RIG govern.

## §0 Pre-start sequence — receipts

1. **Critic integration (commission step 1-2).** The four review-only critic PRs were
   verified review/evidence-only by file list (every path under
   `research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/`), their recorded
   HOLD-FOR-SOL holds released by comment naming the R3B.1 commission as the Sol release
   condition, and squash-merged: #6228 (Data/Authority, BLOCK, DAC-101..108), #6231
   (Visual/Taste, BLOCK, VTC-001..014), #6233 (Product Regression, PASS_WITH_CONDITIONS,
   PRC-001..003), #6234 (Mobile/Accessibility, BLOCK, MAC-001..006). Check state at merge:
   every check concluded, sole red = the by-design `ci-authority/codex/merge-queue-pilot`.
2. **Predecessor verdict (step 3-4).** Sol's REVISE transcribed into
   `mastermind-xpv2-sector-r3b/verdict.yml` (schema `mastermind.rig_verdict.v1`, eight-answer
   packet complete); manifest flipped `in_review -> revise` anchored on the newline-bounded
   field (the freeze's comment-collision trap avoided). No `approval.yml` exists or will.
   PR #6239.
3. **Mandate tool (step 5).** `python3 scripts/check_reference_integrity.py --mandate`
   run against both sets; the successor derivation returned **29 open items** (15
   `upheld_revise` findings + 14 `R3B1-*` conditions) — continuity.yml was generated from
   that output, not hand-enumerated.
4. **Successor ID (step 6).** `mastermind-xpv2-sector-r3b-1` accepted by current tooling
   (RIG scan exit 0 with the new set admitted at draft).
5. **Frozen predecessor untouched (step 7).** All fixes land in
   `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/`; the R3B tree keeps its
   frozen bytes.

## §1 Verdict transcription rulings (what was adjudicated, not merely copied)

- **15 upheld_revise**: VTC-003, VTC-006, MAC-001, MAC-002, MAC-003, MAC-005, MAC-006,
  DAC-101..108 — each mapped to its owning R3B1-* fix item in the note, so the successor
  closure is mechanical (id-for-id).
- **6 overridden, with permanent authority records**:
  - `mastermind-xpv2-sector-r3b::visual_taste::VTC-001` / `::VTC-002` — the critic's own
    second pass downgraded both to minor (dead-token sub-claim withdrawn as factually
    wrong; composition meets its stated budget). Deferred to R3C input per the commission's
    do-not-reopen list (Map reserved-hue law; Explore task architecture).
  - `mastermind-xpv2-sector-r3b::mobile_accessibility::MAC-004` — an authority CONFLICT,
    not a defect: the critic commission said 3×2, the responsive contract said 2×3 at
    ≤359. Sol resolved it in the R3B.1 commission do-not-reopen list: **2 columns × 3 rows
    at ≤359 is RATIFIED**. The frozen candidate already renders exactly that (critic's own
    measurement: unclipped, ≥53px targets at 320). Consequence: **no artifact change is
    owed for MAC-004**; the reconciliation IS this record plus the verdict override row.
  - `mastermind-xpv2-sector-r3b::product_regression::PRC-001/002/003` — all three are
    live-integration properties a frozen reference cannot execute (Time Machine episode
    fetch, optional pulse.json column, first-viewport composition); recorded for the R3C
    draft's live-integration conditions, not R3B.1 fixes.
- **Scope guard**: upheld VTC minors with no R3B1-* item (VTC-011 universe-tab selected
  state at 320, VTC-013 empty grid cell) are NOT successor obligations — Sol's commission
  is the authority on the surgical scope ("fixes only what the fresh four-critic cycle
  proved defective", enumerated as R3B1-01..14). They remain in the critic receipts for the
  R3C record. VTC-014 (px-only type ramp) is the commission's own R3C-only list item
  ("site-wide relative-unit typography debt").

## §2 Cycle-start integrity proof

The successor build tree began as a byte-identical copy: before any fix landed,
`build_reference.py` in the copied tree rebuilt the candidate to sha256
`19553267d3f51659503fc836da6b6bdaa06afc9cdd607aafb1bb795e46c47dca` — exactly the frozen
R3B candidate hash. Every diff between the successor candidate and the frozen predecessor
is therefore attributable to an R3B1-* fix by construction.

## §3 Lane decomposition (commission "Operator decomposition")

- Lane A — authority hero repair (R3B1-01..07, R3B1-13 investigation): Opus `designer`.
- Lane B — accessibility + token repair (R3B1-08..12): Opus `designer`, sequential after A
  (shared view files).
- Lane C — verification hardening (R3B1-14 + acceptance gates): Sonnet `builder`, after A/B
  (the restored features must exist before bidirectional inventory can pin them).
- Lane D — evidence recapture: Sonnet `builder`, after A/B/C converge.
- Orchestrator: adjudication, scope-creep prevention, continuity closure, freeze, PR/merge.

(Sections §4+ appended as lane returns are adjudicated.)
