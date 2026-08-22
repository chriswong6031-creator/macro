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
  bump to event_workspace.v2. source_available_at is the earliest verifiable
  availability of the exact document revision being extracted (SEC acceptance
  for a filing/release; issuer/provider transcript publication for transcript
  bytes). Conference/call time is an event-occurrence clock and must never
  stand in for transcript-document availability. generated_at is never
  source_available_at. Local Qwen is the intended first rung if it clears a
  usefulness bar frozen before E3-A inference (or a later Sol grant); a
  stronger model is an independent comparator with no production authority
  and must not see gold labels. No durable candidate store in E3-A/B.
  exchange_id is document-revision scoped. Respondents are ordered and
  multi-speaker. Identity absence reuses speaker_unresolvable.
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
  already shipped. Sol review 4998678880 accepted this thesis and required
  the bounded contract closures recorded in freeze §16; Fable authored the
  packet and remains workstream owner, but architecture authority is Sol.
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
  - option: Record this decision as decided_by coo-fable
    why_not: >
      Fable proposed and operates the workstream. Sol is the architecture
      ratification seat (review 4998678880). Merging as coo-fable would mint
      false durable authority.
evidence:
  - "engine/company_intelligence/event_workspace.py WORKSPACE_KEYS + validate_event_workspace list-only sources/qa_exchanges"
  - "engine/company_intelligence/event_workspace_build.py qa_exchanges=[] and sources[] without clocks"
  - "engine/company_intelligence/documents.py SourceDocument fetched_at/published_at/available_at; ABSENCE_REASONS includes speaker_unresolvable, not identity_not_in_source"
  - "app/company_intelligence.py _glance_source_states emits {kind, status} only"
  - "charting-app origin/master 89391806 terminal/lib/eventWorkspace.ts normalizeSource strips unknown nested keys; exactKeys on WORKSPACE_KEYS; qa_exchanges unknown[]"
  - "engine/earnings_qual.py score_text / _STORE_COLUMNS / _bounded_transcript_text; config/earnings_qual.yml provider_order"
  - "engine/llm_auth.py make_call; lib/ai_costs.py record_usage"
  - "research/earnings_intelligence/g0/G0_EVENT_CLOCK_AND_CONTRACT_CENSUS.md collapsed clocks"
  - "DNR:KILL-LLM-ORIGINATION DNR:KILL-LLM-FRAME-TAGS"
  - "PR #6157 merged 56d1a36caa43 FIF-2B ACCEPTED / FIXTURE_PROVEN / ON_MAIN; WS:FINANCIAL-INTELLIGENCE-FABRIC FIF-7 still todo"
  - "PR #6161 review 4998678880 Sol thesis pass / freeze ratification blocked for this amendment"
affects:
  - WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER
  - WS:EARNINGS-INTELLIGENCE-OS
  - earnings-intelligence
  - engine/company_intelligence/**
  - engine/earnings_qual.py
  - terminal/lib/eventWorkspace.ts
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-22
review_by: 2026-08-23
---

Sol accepted the compiler thesis in PR #6161 review 4998678880
(submitted 2026-08-22T02:22:12Z). `decided_at` is that thesis-acceptance
date. Freeze ratification (merge of #6161) remains HOLD-FOR-SOL until Sol
accepts this amendment packet. Fable remains `owner` on
`WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER` (execution), not architecture
authority.

E3-0 specifies this decision; it does not implement it. Runtime work
starts at E3-A only after Sol's freeze ratification.
