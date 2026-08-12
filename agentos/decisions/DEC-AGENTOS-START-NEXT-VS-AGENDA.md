---
key: AGENTOS-START-NEXT-VS-AGENDA
question: >
  The CEO brief's START NEXT section is a deterministic ranked list of next work.
  Mastermind config/strategic_state.yml:16 assigns that concept to
  brain/improvement_agenda.py ("owns the ranked work queue"). Is START NEXT a second
  ranked work queue, and if not, what exactly is it?
answer: >
  START NEXT is a READINESS view, not a priority queue, and the brief says so in prose
  on every render. It answers "which waves CAN start" — dependencies satisfied — and
  never "which work matters most", which remains the improvement agenda's answer. The
  brief carries a fixed scope line above the section so the CEO can never be left
  holding two ranked lists without being told which question each one answers.
rationale: >
  Charter P7 is one source of truth per CONCEPT, not one list per screen. Readiness and
  priority are different concepts with different inputs: readiness is computed from the
  workstream dependency graph, which only Agent OS holds; priority is computed from
  accountability-fused evidence, which only the improvement agenda holds. A wave can be
  perfectly ready and correctly last in line, and the agenda cannot tell you the first
  thing while Agent OS cannot tell you the second. The failure P7 actually guards
  against is two lists that both claim to answer the same question and disagree — so
  the fix is not to delete one list, it is to make each one state its question. That
  statement is not a comment in the source: START_NEXT_SCOPE renders inside the brief,
  above the items, in both the text and JSON forms.
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
  - "scripts/agentos.py rank_start_next + START_NEXT_SCOPE — the scope line is rendered, not merely commented"
affects: [WS:AGENT-OS]
confidence: medium
reversibility: easy
decided_by: opus-agentos-phase2-session
decided_at: 2026-08-12
review_by: 2026-09-12
---

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
