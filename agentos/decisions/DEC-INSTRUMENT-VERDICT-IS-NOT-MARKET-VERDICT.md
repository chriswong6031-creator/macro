---
key: INSTRUMENT-VERDICT-IS-NOT-MARKET-VERDICT
question: >
  When an engine state machine — a transmission chain, cycle tripwire, or falsifier —
  reaches a terminal "failed" state, is that a verdict about the market thesis?
answer: >
  No. It is a verdict about the INSTRUMENT: its declared windows failed. Report the
  scope ("no 22d rolldown yet"), never the thesis ("no peak"). Relay a falsifier's prose
  note only as far as its receipt supports. When a display-tier state disagrees with the
  terminal asset's tape or a scored organ (Prophet, Sector Intelligence), the DUAL-READ
  leads the synthesis and the state verdict is the footnote.
rationale: >
  Operator ruling 2026-08-09, minted from a live miss: the engine narrated "no peak;
  restriction still building" nightly while the operator's real-rate-peak call (gold/PGM
  miners — the operator's best trade of 2026) was already +20%. The instrument was a
  trailing-63d window, blind by construction to a fresh peak for weeks; its terminal
  state was a fact about the window, and the nightly synthesis promoted it into a fact
  about the world. The cost of the conflation was the system arguing against a correct
  position for weeks. Receipts and the design seed for the fix are preserved in
  research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md.
alternatives:
  - option: Keep reporting terminal states as thesis verdicts (status quo ante)
    why_not: >
      The case study is the counterexample: confidently wrong for weeks on the
      operator's best trade, because window-blindness read as thesis refutation.
  - option: Suppress instrument verdicts from synthesis entirely
    why_not: >
      The windows are still information — the fix is scope-honest reporting and
      dual-read precedence, not silence. Tripwires keep evaluating in the background.
evidence:
  - "Macro CLAUDE.md §House laws — 'Instrument verdicts are NOT market verdicts (operator 2026-08-09)'"
  - "Macro AGENTS.md §Signal-state interpretation (operator 2026-08-09)"
  - "research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md — receipts of the miss and the +20% tape"
affects: ["engine/**", "research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-09
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). The ruling, its date, and the case-study
receipt are all in standing fleet law; the case study preserves the tape. Related
front-facing law: falsifier/refutation language never surfaces on user cycle pages
(operator 2026-07-27, #3821) — that decision governs COPY, this one governs
INTERPRETATION; they are deliberately separate.

## What would reopen this

An instrument whose window provably covers the thesis horizon (no blindness gap) could
carry more synthesis weight — but the ruling's default stands until a specific
instrument earns it with receipts.
