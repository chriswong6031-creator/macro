---
key: E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
question: >
  After E2, is the next earnings-intelligence wave a richer qualitative scorer
  (earnings_qual v3 / sentiment / 0–10 / tone), or a clock-safe Event
  Intelligence Compiler whose models only propose candidates?
answer: >
  Compiler, not scorer. Models propose candidates; a deterministic validator
  is the trust boundary; accepted objects extend existing event_workspace.v1
  (first vertical: structured Q&A into the existing qa_exchanges slot).
  earnings_qual remains a legacy descriptive plane. Source clocks are a
  versioned nested event_source_clock.v1 contract on sources[] items — not a
  silent additive event_workspace.v1 bag extension, and not a parent schema
  bump to event_workspace.v2. generated_at is never source_available_at.
  Local Qwen is the intended first rung if it clears E3-A gold; a stronger
  model may review gold for evaluation only and has no production authority.
rationale: >
  E2 proved the canonical event and its consumers (Terminal E2-T1, Macro
  E2-D). It left qa_exchanges empty, clocks collapsed, consensus unlicensed,
  reaction not_joined. G0 established that model-generated intelligence must
  not sit on that temporal ambiguity. Macro validate_event_workspace is
  list-only on nested sources (silent pass) while Terminal normalizeSource
  silently strips unknown nested keys and the public glance emits only
  {kind, status} — so "Python didn't reject extra source keys" is not
  backward-compatible publication. A parent v2 bump would fail Terminal
  exactKeys on schema. Reusing earnings_qual's score schema would mint
  sentiment/performance/tone as if they were event truth. Building a second
  model-routing plane would ignore llm_auth.make_call / ai_costs.record_usage
  that already exist. Filling a parallel Q&A store would ignore the slot E1
  already shipped.
alternatives:
  - option: Ship earnings_qual v3 as canonical event intelligence
    why_not: >
      Score fields are context-only by SGA-R5 (sentiment, performance 0–10,
      tone_word, highlights). Head/tail truncation is scorer law. The module
      is a parallel plane; company_intelligence does not import it.
  - option: Treat extra sources[] keys as additive event_workspace.v1
    why_not: >
      Terminal strips them; public glance does not emit them; Brain would see
      unversioned keys; lifecycle.source_available_at already means the
      collapsed generation clock. G0 forbade inferring compatibility from an
      open nested dict.
  - option: Bump parent schema to event_workspace.v2 for clocks and Q&A
    why_not: >
      Terminal normalizeEventWorkspace requires obj.schema === event_workspace.v1
      and exact top-level keys. A parent bump would fail live AAPL Intelligence.
      Nested versioned objects keep the parent contract.
  - option: Park structured Q&A until E6 as the E0 ledger row said
    why_not: >
      The qa_exchanges slot already exists on event_workspace.v1. E2 left it
      empty because the analyst role is blank, not because the slot is reserved
      for a later product. E3-B fills it; E6 keeps clustering, deflection
      method, and peer-topic work.
  - option: Freeze GOOGL now as the E3-C issuer
    why_not: >
      Current 8-K exhibit and transcript fixtures are not held. CI v1 HTTP 200
      is not an event_workspace package. The freeze pre-registers the walk
      (GOOGL if held, else CAT, BAC, SNOW) and forbids choosing from extraction
      quality.
evidence:
  - "engine/company_intelligence/event_workspace.py WORKSPACE_KEYS + validate_event_workspace list-only sources/qa_exchanges"
  - "engine/company_intelligence/event_workspace_build.py qa_exchanges=[] and sources[] without clocks"
  - "engine/company_intelligence/documents.py SourceDocument fetched_at/published_at/available_at"
  - "app/company_intelligence.py _glance_source_states emits {kind, status} only"
  - "charting-app origin/master 756332fa terminal/lib/eventWorkspace.ts normalizeSource strips unknown nested keys; exactKeys on WORKSPACE_KEYS"
  - "engine/earnings_qual.py score_text / _STORE_COLUMNS / _bounded_transcript_text; config/earnings_qual.yml provider_order"
  - "engine/llm_auth.py make_call; lib/ai_costs.py record_usage"
  - "research/earnings_intelligence/g0/G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md collapsed clocks"
  - "DNR:KILL-LLM-ORIGINATION DNR:KILL-LLM-FRAME-TAGS"
  - "WS:FINANCIAL-INTELLIGENCE-FABRIC FIF-7 todo; event_workspace.py basis_match/beat-miss guards"
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - WS:EARNINGS-INTELLIGENCE-OS
  - earnings-intelligence
  - engine/company_intelligence/**
  - engine/earnings_qual.py
  - terminal/lib/eventWorkspace.ts
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-20
review_by: 2026-08-22
---

E3-0 specifies this decision; it does not implement it. Sol review of the
draft architecture PR is the ratification gate. Runtime work starts at E3-A
only after that acceptance.
