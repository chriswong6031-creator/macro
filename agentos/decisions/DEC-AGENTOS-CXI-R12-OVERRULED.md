---
key: AGENTOS-CXI-R12-OVERRULED
question: >
  Does DNR:KILL-PARALLEL-KNOWLEDGE-BASE (CXI-R12, 2026-07-18) forbid the Agent OS
  knowledge records — authored decisions, discoveries and handoffs under agentos/?
answer: >
  No. The Chairman overruled CXI-R12 on 2026-08-12: "override CXI-R12, this is an old law
  and we overrule it." The kill is lifted as a whole, not narrowed to this program.
  Authored knowledge records are permitted, and Phase 1 may require sessions to write them.
rationale: >
  The row forbade "a second hand-maintained knowledge base / wiki / RAG memory service
  parallel to canonical sources (agents required to write session knowledge into a separate
  database)". Read honestly that is the closest existing description of DSC-* records, which
  is why this was escalated as conflict C5 rather than self-certified — the DNR preamble is
  explicit that a killed topic needs new evidence AND an explicit operator/Fable ruling, and
  a worker cannot supply the second. The Chairman supplied it. The lifting is recorded as
  given: the instruction overruled the law, not merely its application here, so this record
  does not narrow it back to Agent OS on the author's own initiative.
alternatives:
  - option: Narrow CXI-R12 to permit only agentos/ records, leaving the kill standing elsewhere
    why_not: >
      Not what was ruled. The instruction was to overrule the law; silently converting that
      into a program-scoped exemption would be the author substituting a preferred, smaller
      version of the operator's decision. Flagged here instead so the narrower reading can be
      adopted deliberately if that was the intent.
  - option: Uphold the kill and retire DSC-*, keeping only DEC-* and handoffs
    why_not: >
      This was the live alternative while C5 was open, and it was a real option — DEC-* and
      handoffs carry most of the value. Overruled.
  - option: Leave C5 unresolved and ship Phase 0 with the restriction standing
    why_not: >
      Was the pre-ruling state. It made Phase 1 unbuildable as specified, since Phase 1's
      whole content is adoption — sessions writing records.
evidence:
  - "Chairman ruling, 2026-08-12: 'override CXI-R12, this is an old law and we overrule it.'"
  - "research/DO_NOT_REBUILD.md §1 KILL-PARALLEL-KNOWLEDGE-BASE — row amended in this PR, key retained"
  - "config/compiled_kill_registry.yml regenerated via scripts/check_blocklist_drift.py --fix; drift check exits 0"
  - "DNR preamble: a killed topic needs NEW evidence and an explicit Fable/operator ruling"
affects: ["WS:AGENT-OS", "research/DO_NOT_REBUILD.md", "agentos/**"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-12
---

## What this does and does not settle

**Settled.** `agentos/decisions/`, `agentos/discoveries/` and `agentos/handoffs/` are permitted.
Phase 1 may mandate that sessions write them; the restriction that previously blocked that is
removed from the implementation plan. Conflict C5 is closed.

**Not settled, and deliberately left open.** CXI-R12's *ground* — that retrieval belongs to the
Macro Context Index, which is derived, rebuildable, and leaves truth in canonical sources — still
describes a real failure mode. Lifting the kill removes a pre-refusal; it does not pre-approve a
future parallel **retrieval/RAG service**. Such a proposal is now adjudicated on its merits rather
than rejected by citing this row. The Agent OS itself continues to build no retriever: Phase 3
registers `agentos/**` as a corpus for `scripts/context_index_query.py`.

## A gap in the DNR convention, worth noting

The registry documents how to **add** a kill (append a row in the same PR, mint a stable key,
commit the regenerated blocklists) but has **no documented path for clearing one**. This ruling
was therefore recorded by amending the existing row's verdict in place — keeping the key, since
keys are never reused or renumbered — and pointing it at this record for the grounds. If
clearings become common, the registry should state that convention explicitly rather than
leaving each session to invent it.

## What would reverse this

A ruling that the Context Index corpus plus masterplan prose is sufficient for cross-account
knowledge. That would retire `DSC-*` while leaving `DEC-*` and handoffs intact, since neither of
those was ever what CXI-R12 described.
