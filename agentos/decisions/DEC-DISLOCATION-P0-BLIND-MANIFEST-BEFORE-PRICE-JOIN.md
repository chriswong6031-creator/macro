---
key: DISLOCATION-P0-BLIND-MANIFEST-BEFORE-PRICE-JOIN
question: >
  After the EXK Turn-4 canonical replay produced no untouched confirmation-arm
  entries, should Mastermind retune EXK or move to a cross-issuer panel; and how
  must that panel prevent event-selection leakage?
answer: >
  Stop EXK rule search. The next proof object is Cross-Issuer Dislocation P0,
  selected and classified by a price-blind extractor seat. The event manifest,
  source hashes, episode identities, trial budget, arms and endpoints must be
  frozen before any price or outcome join. A separate runner executes the sealed
  manifest and a separate adjudicator reviews it. EXK/Endeavour and every
  design-used issuer are excluded from P0 proof; miners are held as later external
  validation. P0 begins with zero ranking, gating, sizing, candidate, Prophet,
  Radar, Fusion or execution authority.
rationale: >
  The canonical EXK/SIL common tape is only 2023-01-03 through 2026-08-05.
  Nine older episode origins are before store birth and the live August 2026 case
  is after store end. Of six measurable origins, five are design-touched; the one
  untouched origin produced H0/H1 but no H2/H3/H4 signal within the frozen
  60-session wait. Positive confirmation medians therefore have zero untouched
  entered N. Further EXK tuning would optimize on the design set and destroy the
  research value. A blind cross-issuer manifest preserves the hypothesis while
  protecting it from event selection, classification and timing leakage.
alternatives:
  - option: Retune EXK confirmation length, wait or hold period
    why_not: Outcome-driven optimization on six origins, five design-touched.
  - option: Backfill SIL or substitute an external ETF inside the EXK replay
    why_not: Changes the canonical substrate after results and mixes vintages.
  - option: Promote the descriptive H3/H4 medians
    why_not: Untouched entered N is zero; authority would precede evidence.
  - option: Build a master Dislocation Score first
    why_not: Violates the two-object statistical/economic split and fused-score law.
evidence:
  - "research/dislocation_intelligence/EXK_TURN4_CANONICAL_REPLAY_ADJUDICATION_2026-08-20.md"
  - "research/dislocation_intelligence/DISLOCATION_CROSS_ISSUER_P0_PREREG_2026-08-20.md"
  - "PR #6057, canonical replay v1.2, output sha256 aa2a11691be2f982f368a17562fd4dcf81397cc1072dfbbf3abd68e0479eb9ff"
affects:
  - research/dislocation_intelligence/
  - research/opportunity_evidence/
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
  - engine/synthetic_control.py
  - scripts/backtest_event_priors.py
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-20
---

## What would reopen EXK tuning

A genuinely new, preregistered hypothesis based on new evidence rather than the
Turn-1–4 outcomes, with its own untouched panel and explicit Sol/operator ruling.
A longer or externally rebuilt EXK benchmark by itself does not reopen tuning; it
may complete the frozen descriptive replay only.
