---
key: LER-EXPERT-EVENT-FAMILIES-PRESERVED
question: >
  Does Live Entry Radar treat Terminal's entry grammar as one incumbent signal (grey dot)
  versus challengers, or as multiple distinct event families — and who owns learning which
  family works for which security?
answer: >
  Terminal's mechanistically distinct entry-event families — raw grey/early-dot
  anticipation, washout-promoted amber EARLY, STARTER awaiting-confirmation, STARTER
  confirmation-failed, RE-ENTRY trend-reclaim, RE-ENTRY block-repair, classic confirmed
  BUY/REBUY (the STARTER/RE-ENTRY/BUY names are operator-observed UI labels — only
  early_dot and blocked_trigger have emitter receipts today; exact enums are minted at
  PR-2 from receipts), plus Radar's own C1-C5 — are CANDIDATE EXPERTS, not synonyms. Radar preserves
  event-level identity and provenance for every one of them (producer, detector_id, family,
  subtype, quality/stage, context, signal ts, known_ts, source/spec identity, scored
  authority, promotion relationship) and never flattens them into one entry_signal boolean
  or a generic category. Radar does NOT own per-security expert selection: a separate,
  future Stock Identity / Expert Routing program will test which families localize
  opportunities per security and identity epoch. Radar discovers and records experts; a
  separate system later learns which experts to trust for whom. G0 remains the exact raw
  grey-dot emitter; the recorded families are ledger/display tier and join the graded
  arena only via a further registered amendment.
rationale: >
  CEO amendment 2026-08-13 (delivered in-session at PR-0, recorded verbatim as contract
  §18 A1): operator visual review across KRUS, MCK, NVDA, REGN and YELP suggests different
  securities respond to different entry mechanisms. Preserving distinctions now costs a
  field block on an unimplemented schema; reconstructing them later from flattened events
  would be impossible (the ephemeral-producer lesson of Track F B2 applied to Radar's own
  output). The Terminal artifact already carries these fields (Track A §4:
  mastermind.indicator/v1 type/subtype/quality/scored + known_ts) — the decision obligates
  the adapter to not drop them.
alternatives:
  - option: Grey-vs-challengers only (collapse Terminal grammar into G0)
    why_not: Rejected by the CEO amendment; destroys exactly the distinctions the downstream routing program needs.
  - option: Radar also builds the per-security expert-routing research now
    why_not: >
      Explicit scope boundary in the amendment — no stock classification, personality
      modeling, per-stock optimization, or adaptive routing inside Radar; the PR-1..PR-9
      sequence continues as commissioned.
  - option: Mint the Stock Identity / Expert Routing workstream now
    why_not: >
      Not commissioned; no such program exists in config/mastermind_programs.yml or
      agentos (collision-checked 2026-08-13). More importantly, the adversarial pass
      surfaced DNR:KILL-OUTCOME-AUDITION (research/DO_NOT_REBUILD.md §2): per-name
      timing-tool selection by in-sample outcome audition is killed two-ruler at n=1,300
      with zero OOS persistence — the future program is put on notice by name in contract
      §18 A1.5 and must route through the row's live carve-out (structure-measurement
      tailoring), never in-sample best-of-grid per name. The contract records it as a
      future dependency only.
evidence:
  - "research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §18 A1 (normative text) + §13 event-store reference + §3.3 G0-VIS closure"
  - "research/DO_NOT_REBUILD.md §2 row DNR:KILL-OUTCOME-AUDITION — the standing kill the downstream program must clear"
  - "research/live_entry_radar/TRACK_A_GREY_DOT_FORENSICS.md §4 — the artifact schema already carries type/subtype/quality/scored + known_ts"
  - "Operator/CEO amendment message, 2026-08-13, in-session (G0-VIS confirmation + Expert Preservation ruling)"
affects: ["research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md", "engine/entry_radar/", "data/entry_radar/"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-13
---

## Grounds

Delivered as a CEO amendment while PR #5578 (PR-0) was open and armed; applied pre-freeze
with the normative text in §18 A1 and pointer edits at §3.3/§4/§13. G0-VIS closed in the
same message: the operator confirmed the raw grey anticipation-dot family against the
Track A fired-date evidence.

## What would reopen this

The Stock Identity / Expert Routing program being commissioned (it would then own expert
selection and may request schema extensions via §18); or PR-2 archaeology finding a
Terminal family the enumeration missed (added by amendment, never silently).
