---
key: EXECUTIVE-ATTENTION-FRONTIER-ARCHITECTURE
question: >
  Should Mastermind allocate scarce Chairman/Sol cognition with one global priority score or
  flat needs-executive inbox, or with a source-attributed attention frontier that preserves
  authority, intentional waits, exact root-cause fan-in, anti-starvation and degraded truth?
answer: >
  Build a pure deterministic Executive Attention Frontier (EAF), not a persistent queue or
  universal score. First derive canonical authority independently from urgency. Then gate whether
  cognition is currently required, classify each demand into one closed attention disposition,
  bundle only on exact canonical roots, derive source-backed factor vectors, expose the non-
  dominated/Pareto frontier and use deterministic local service rules including an oldest-ready
  fairness sentinel. Chairman and Sol consume separate authority partitions. Models may explain
  the already-derived result but may not rank, suppress, authorize or mutate anything.
rationale: >
  The existing estate already separates Executive lifecycle, Agent OS organizational truth,
  Wake/Inbox attention, RuntimeBinding identity, Capacity/Model Router placement and Steward/
  Control Room composition. A new inbox/database would duplicate these owners. A single weighted
  score would collapse distinct objectives such as deadline pressure, active harm, reversibility,
  dependency unblock, autonomous progress, resource burn, information value and switching cost;
  it would also turn unknowns into false precision and invite priority inflation. SRE practice
  favors actionable human interruption plus dedup/fan-in; scheduling research shows narrow scalar
  order rules stop being generally optimal with precedence and mixed objectives; real-options/
  value-of-information work shows that waiting can be valuable when information is expected and
  actions are hard to reverse; interruption research supports context batching only as a local
  non-emergency optimization. A closed disposition + partial-order frontier preserves these truths
  and can remain correction-safe because it stores no mutable rank state.
alternatives:
  - option: One weighted priority score for every responsibility
    why_not: >
      Creates false precision across incomparable objectives, hides unknown input quality, invites
      projects to game weights/labels and makes a policy coefficient look like organizational truth.
  - option: Flat needs_sol / needs_chairman inbox ordered by recency
    why_not: >
      Recreates the human queue at company scale, does not preserve valid waits/autonomous progress,
      cannot collapse exact root causes and lets notification volume dominate executive cognition.
  - option: Earliest deadline first
    why_not: >
      Optimizes one timing objective only; many strategic obligations lack source-backed deadlines
      and old/non-deadline work can starve.
  - option: Rank by dependency descendant count / critical path
    why_not: >
      Descendant count is not CPM criticality. Without durations, network timing and float, calling
      a dependency root a critical path would overclaim precision.
  - option: LLM ranker / semantic dedup
    why_not: >
      Model output would become an opaque authority-adjacent suppressor. Semantic similarity cannot
      safely prove identity; exact receipts must survive fan-in.
  - option: Persistent attention queue with aging counters
    why_not: >
      Creates another durable truth/correction plane. Ready age can be derived from canonical source
      events when available; otherwise it must be unknown rather than manufactured locally.
evidence:
  - "Mastermind protected master 8f0babf473e6e4e8efce697014bd48c594227d94 — current Skillpack/source law and Workroom no-duplicate boundaries."
  - "Mastermind OCR-6 Executive Steward PR #228 head inspected during F0 — pure read-only source-attributed composition; currently open with a known canonical-grouping-before-filter correctness blocker."
  - "Macro agentos workstream/schema @ ca31568272d06f2472f65946d2435517611f31dc — Agent OS already owns responsibilities, dependencies, waits, next_action and optional needs_ceo."
  - "Macro WS-CHAIRMAN-CONTROL-ROOM @ ca31568272d06f2472f65946d2435517611f31dc — Control Room is a read composition and must not gain a second lifecycle/queue/inbox owner."
  - "Macro WS-EXECUTIVE-CAPACITY-FABRIC @ ca31568272d06f2472f65946d2435517611f31dc — Capacity/Model Router already own eligibility/placement and remain separate from cognition allocation."
  - "Google SRE Book, Introduction / Service Best Practices / On-Call — humans should be bothered for actionable work; page/ticket/log distinctions and high signal-to-noise reduce operational overload."
  - "Google SRE Practical Alerting — inhibition, deduplication and fan-in/fan-out are explicit alert-manager behaviors."
  - "Hall, Schulz, Shmoys & Wein (1999), Discrete Applied Mathematics 98 — precedence-constrained weighted completion scheduling is NP-hard, undermining a universal narrow-rule optimizer for this mixed organizational problem."
  - "PMI Critical Path Method calculations — criticality/float require explicit network schedule timing, not raw descendant counts."
  - "Bernanke, NBER w0502; McDonald & Siegel, NBER w1019 — irreversible decisions under uncertainty can have material option value from waiting for information."
  - "Microsoft Research Czerwinski/Horvitz/Wilhite CHI 2004 and Cutrell/Czerwinski/Horvitz CHI 2000 — task switching and irrelevant interruptions impose resumption/recovery cost."
affects:
  - WS:EXECUTIVE-ATTENTION-ECONOMICS
  - WS:CHAIRMAN-CONTROL-ROOM
  - mastermind/control_plane/**
  - mastermind/research/MASTERMIND_EXECUTIVE_ATTENTION_ECONOMICS_F0_ARCHITECTURE_2026-08-30.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-30
---

## Frozen mechanism

The architecture pipeline is:

```text
canonical source facts
-> authority partition
-> cognition admission
-> closed attention disposition
-> exact canonical-root bundling
-> source-backed factor vectors
-> Pareto/non-dominated frontier
-> deterministic local service + oldest-ready fairness sentinel
-> read-only Control Room / Chat-native CEO projection
```

Closed dispositions are:

- `INTERRUPT_NOW`
- `FOCUS_NOW`
- `BATCH_NEXT`
- `AUTONOMOUS_CONTINUE`
- `VALID_WAIT`
- `RECONCILE_FIRST`
- `COVERED_BY_BUNDLE`
- `NON_ACTIONABLE`

These are derived attention dispositions only. They grant no authority and never become Executive
or Agent OS lifecycle states.

## Authority law

Authority is resolved before any priority factor. A high-pressure Sol item remains Sol. A Chairman-
only item remains Chairman-only even when it is a valid wait. Unknown/conflicted authority degrades
to reconciliation instead of escalating upward. `needs_ceo`, urgency text, age, dependency fan-out,
resource burn and model output may never confer Chairman authority.

## Service law

All accepted `INTERRUPT_NOW` items remain visible and are not quota-suppressed. Among ordinary
backlog, context/exact-root batching reduces switching cost. At least one oldest source-backed ready
eligible item is kept visible as a fairness sentinel per active executive authority partition when
backlog exists; valid future waits do not age into false urgency. If ready age is not source-backed,
its fairness age is unknown rather than stored in a new allocator ledger.

## Promotion law

Initial implementation is report-only shadow. It may not mutate Wake delivery, Executive lifecycle,
placement or notification behavior. Promotion requires adversarial semantics review plus real multi-
program evidence showing no missed accepted interrupts, no priority-driven authority escalation,
truthful degraded states, preserved valid waits, exact suppression receipts and materially reduced
executive scanning/interruption.
