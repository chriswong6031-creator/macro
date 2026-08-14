---
key: AGENTOS-DECISION-MEMORY-STAYS-SEPARATE
question: >
  Should agentos/decisions/ and Mastermind's governance.jsonl eventually be merged into one
  store, given that the census specified adding event types to governance.jsonl rather than
  creating a new store?
answer: >
  No. The separation is PERMANENT BY DEFAULT. agentos/decisions/ is git-tracked
  organizational decision memory; governance.jsonl is runtime authority and audit history.
  They are not to be merged merely because governance might become git-tracked later.
rationale: >
  Chairman ruling C4, 2026-08-12: "APPROVE, AND MAKE THE SEPARATION PERMANENT BY DEFAULT."
  This deliberately REVERSES the reversal condition the original override recorded. The
  architecture had said the override would be undone if governance.jsonl became git-tracked —
  the ruling rejects that, and correctly: git-tracking was only ever the mechanical objection,
  not the reason. The real reason is that these are two different KINDS of record. A
  governance event is a runtime fact ("this flag flipped at this time, under this authority").
  A decision record is deliberation ("we chose X over Y because Z, here is what would reverse
  it"). Merging them would put an append-only machine audit trail and a human-authored,
  supersedable argument in one store, and the merged thing would serve neither well.
alternatives:
  - option: Merge once governance.jsonl becomes git-tracked (the previously recorded condition)
    why_not: >
      Explicitly rejected by the ruling. Transport was the mechanical objection; record KIND
      is the durable one. Making them shared-transport does not make them the same concept.
  - option: Merge now, writing decisions as governance events
    why_not: >
      governance.jsonl is not git-tracked (control_plane/governance.py:70 → data/governance/),
      so it is single-machine runtime state and cannot carry cross-machine memory at all.
  - option: Leave the relationship unstated
    why_not: >
      The prior record named an explicit reversal condition. Leaving it standing would have a
      future session dutifully merging the two stores the first time governance.jsonl moves
      into git — doing damage while following the record correctly.
evidence:
  - "Chairman ruling C4, 2026-08-12"
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §5.4 — 'Explicit non-goal: a new unified store'"
  - "control_plane/governance.py:70 — resolves data/governance/governance.jsonl; git ls-files returns nothing"
  - "research/MASTERMIND_CHARTER_V2.md P7 — one source of truth per CONCEPT; these are two concepts"
affects: ["WS:AGENT-OS", "agentos/decisions/**", "research/MASTERMIND_AGENT_OS_ARCHITECTURE.md"]
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-12
---

## Direction of truth (unchanged, restated)

An `executive_decision` event stays in `governance.jsonl` as the local audit row; `DEC:<KEY>`
is the durable record; the event cites the key. One direction, no fork.

## Why `reversibility: costly`

Once decisions are cited by key across PRs, masterplans and memory, unifying the stores means
rewriting citations. That is mechanical rather than lossy — plain text in git — but it is not
free, which is exactly why the default is now permanence rather than a standing intention to
merge.
