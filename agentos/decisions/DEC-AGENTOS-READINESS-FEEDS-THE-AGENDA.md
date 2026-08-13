---
key: AGENTOS-READINESS-FEEDS-THE-AGENDA
question: >
  The CEO brief computes a next-work list, and brain/improvement_agenda.py already produces
  a ranked weekly queue. Which is canonical, and should both exist?
answer: >
  improvement_agenda.py is the SOLE canonical answer to "what should we do next?". Agent OS
  owns dependency/readiness computation ONLY. Readiness is to be fed into the agenda as an
  input, and the independent list retired once that integration lands. Until then the section
  is renamed to mean UNBLOCKED/READY, never priority.
rationale: >
  Chairman ruling C3, 2026-08-12: "CHANGE". This supersedes DEC:AGENTOS-START-NEXT-VS-AGENDA,
  which proposed keeping both lists side by side and distinguishing them by prose. The ruling
  is stronger and is right: two lists that both look like "what to do next" is a Charter P7
  violation regardless of how carefully each is captioned, because readers do not read
  captions — they read the list. Agent OS has something the agenda genuinely lacks (a wave
  dependency graph), so the durable answer is to contribute that as an INPUT rather than to
  publish a rival ordering.
alternatives:
  - option: Keep both lists, distinguished by a prose scope note (the superseded design)
    why_not: >
      Two ranked-looking lists in one organization. The prose note is read once and the list
      is read every day.
  - option: Retire the readiness list immediately, before the integration exists
    why_not: >
      Would delete a working signal with nothing to receive it yet. The interim rename keeps
      the value while removing the priority connotation.
  - option: Make Agent OS the canonical queue and retire the agenda
    why_not: >
      The agenda fuses ten accountability sources (calibration deltas, journal clusters,
      shadow-vs-live gaps, benchmark ledgers). Readiness is one input to priority, not a
      substitute for it.
evidence:
  - "Chairman ruling C3, 2026-08-12"
  - "Mastermind config/strategic_state.yml:16 — 'brain/improvement_agenda.py owns the ranked work queue'"
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §5.3 — the only ranked, evidence-cited priority engine in the org"
  - "research/MASTERMIND_CHARTER_V2.md P7 — one source of truth per concept"
supersedes: [DEC:AGENTOS-START-NEXT-VS-AGENDA]
affects: ["WS:AGENT-OS", "scripts/agentos.py", "research/MASTERMIND_CEO_BRIEF_SPEC.md"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-12
---

## What changed in the artifact, now

- Section header `START NEXT` → `UNBLOCKED — READY TO START`.
- `ceo_brief.v1` / `agent_os_state.v1` key `start_next` → `unblocked`; `start_next_scope` →
  `unblocked_scope`. Renamed rather than aliased because the schema is not yet on main, so
  there is no reader to break.
- The scope text now states that the agenda is SOLE canonical, that Agent OS owns readiness
  only, and that this section is INTERIM pending integration.
- The test asserts that substance rather than a phrase, and asserts the retired label does
  not reappear.

## What still has to happen

The integration itself is not built. Agent OS must expose readiness in a form the agenda can
consume, and the agenda must render it as a column. When that lands, the UNBLOCKED section is
deleted — not deprecated. Tracked as a wave on `WS:AGENT-OS`.

**Read the agenda from its authoritative source, not a local checkout.** `data/agenda/` is
gitignored and VPS-authoritative; the copy in this repo measured ~3.5 weeks stale.
