---
key: AGENTOS-START-NEXT-VS-AGENDA
question: >
  The CEO brief's START NEXT section is a deterministic ranked list of next work.
  Mastermind config/strategic_state.yml:16 assigns that concept to
  brain/improvement_agenda.py ("owns the ranked work queue"). Is START NEXT a second
  ranked work queue, and if not, what exactly is it?
answer: >
  HISTORICAL DESIGN, NOW RETIRED: START NEXT was a READINESS view, not a priority queue,
  and the brief said so in prose on every render. It answered "which waves CAN start" —
  dependencies satisfied — and never "which work matters most", which remained the
  improvement agenda's answer. Phase 2b removed this independent human list.
rationale: >
  Historical rationale: Charter P7 is one source of truth per CONCEPT, not one list per screen. Readiness and
  priority are different concepts with different inputs: readiness is computed from the
  workstream dependency graph, which only Agent OS holds; priority is computed from
  accountability-fused evidence, which only the improvement agenda holds. A wave can be
  perfectly ready and correctly last in line, and the agenda cannot tell you the first
  thing while Agent OS cannot tell you the second. The failure P7 actually guards
  against is two lists that both claim to answer the same question and disagree — so
  the fix is not to delete one list, it is to make each one state its question. That
  statement was not a comment in the source: START_NEXT_SCOPE (historical; retired)
  rendered inside the brief, above the items, in both the text and JSON forms.
  Deriving START NEXT from the agenda instead was considered and rejected on evidence,
  not preference. The agenda's artifacts live at data/agenda/, which is gitignored and
  VPS-authoritative; the local checkout of it here is absent entirely. Reading a
  ~3.5-week-stale or missing local copy would make the brief's freshest section its
  least trustworthy one, and reading the live VPS path would put a network dependency
  into a command whose entire §1 contract is zero network calls.
alternatives:
  - option: START NEXT consumes data/agenda/<date>.json and Agent OS contributes only join keys
    why_not: >
      data/agenda/ is gitignored and VPS-authoritative; the local copy is absent in this
      checkout and measured ~3.5 weeks stale where it exists. The alternative reading
      path is the live VPS API, which violates the brief's zero-network contract
      (CEO_BRIEF_SPEC §1) and puts CEO-facing output behind a shared quota bucket that
      ship_loop_guard.py fails CLOSED on.
  - option: Drop START NEXT entirely and let the agenda answer everything
    why_not: >
      The agenda has no workstream/wave dependency graph, so it cannot answer "is this
      unblocked". That is the one question the Agent OS record set uniquely can answer,
      and dropping it forfeits the reason waves carry depends_on at all.
  - option: Ship both lists ranked, unlabelled, and let the CEO reconcile them
    why_not: >
      This is the exact P7 failure — two ranked lists that disagree with no stated
      direction of truth. It is also the cheapest thing to do, which is why it needs an
      explicit refusal on the record.
evidence:
  - "Mastermind config/strategic_state.yml:16 — 'brain/improvement_agenda.py owns the ranked work queue.'"
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §5.3 — improvement_agenda is the only ranked, evidence-cited priority engine in the org"
  - "research/MASTERMIND_CEO_BRIEF_SPEC.md §3 — START NEXT ranking rule (deps satisfied, P0 alignment, unblock count, unclaimed)"
  - "research/MASTERMIND_CEO_BRIEF_SPEC.md §1 and §6 — zero network calls is a stated contract of this command"
  - "Historical implementation (retired): scripts/agentos.py rank_start_next + START_NEXT_SCOPE rendered the scope line"
affects: [WS:AGENT-OS]
confidence: medium
reversibility: easy
decided_by: opus-agentos-phase2-session
decided_at: 2026-08-12
superseded_by: DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA
review_by: 2026-09-12
---

**Historical record.** This decision is superseded. Every reference below to `START NEXT`,
`rank_start_next`, or `START_NEXT_SCOPE` describes the retired Phase 2 implementation and is
preserved only to show the reasoning that preceded Chairman ruling C3. None names a current
symbol or output surface.

## Grounds

The reviewer's finding was precise and correct: a design whose central claim is "we
censused everything, these six gaps are what remain" that never once mentions the org's
only existing ranked queue has not done the P7 check. This record does that check.

The check's outcome is that the two lists are different concepts, not that the conflict
was imaginary. Readiness ranking still USES a priority input — `p0_active` is the first
sort key — and that input comes from the strategic state, not from Agent OS. So the
direction of truth is stated: **strategic state and the improvement agenda supply
priority; Agent OS supplies readiness; where they appear to disagree, priority wins and
Agent OS is telling you only that the work is technically startable.**

## What would reverse this

If the Chairman wants one list, it should be the agenda's, extended with a readiness
column fed by `agent_os_state.v1` — one generator, many renderers, in the direction that
keeps priority where P7 already put it. That is a Mastermind-side change and would
retire START NEXT here rather than duplicating it.

## Escalated

Recorded as conflict C3 in `research/MASTERMIND_AGENT_OS_ARCHITECTURE.md` §13 and in
`WS:AGENT-OS` `needs_ceo`, alongside C1 and C2. It is the same class of call: a
Chairman-level judgment about which seat owns a concept.

## SUPERSEDED 2026-08-12 by Chairman ruling C3

This record proposed keeping both lists and distinguishing them by prose. The Chairman
ruled further: `brain/improvement_agenda.py` is the SOLE canonical queue, and Agent OS owns
readiness computation only. Phase 2b now feeds the machine readiness envelope to the agenda
and has retired the independent human list. Retained for provenance — the reasoning here is
still the reasoning that framed the question. See
`DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA`.
