---
key: SONNET-BUILDS-AGAIN
question: >
  Does the 2026-07-21 "Opus builds, Sonnet does not" order still hold, or does Sonnet
  resume building shipping code via the `builder` agent type?
answer: >
  Reversed. Sonnet builds shipping code again — writing code, PRs, refactors, tests —
  via the `builder` agent type (re-pinned `model: sonnet`). Opus continues to review
  (`reviewer`) and continues to own user-facing design (`designer`), hard debugging,
  judge/red-team critics, and stats/math review. The 2026-07-18 design-lane order
  (design is judgment work, never routed to a sonnet builder) is untouched — this
  reversal is scoped to the build lane only. Fable (main loop) still plans, adjudicates,
  and merges under the same orchestrator+FABLE-WHY gate. The autonomous metabolism
  build loop (`scripts/metabolism_build.py`, R-V4-2) is a separate system and stays
  Opus-pinned — this decision does not reach it.
rationale: >
  Direct operator instruction, 2026-08-17, given in an interactive chat session:
  "Change the agents.md file so that the ban on Sonnet being used as a worker is
  removed." The superseded decision (DEC:OPUS-BUILDS-SONNET-EXPLORES-FABLE-GATED)
  explicitly named reversal as "an operator call, not a session call" — this
  instruction is treated as exactly that call: it arrived as an explicit chat
  instruction rather than being inferred or self-initiated by a session. No new
  measured quality evidence is claimed in either direction here; this is a policy
  instruction, not a re-litigation of the 2026-07-21 quality complaint that motivated
  the original order.
alternatives:
  - option: Keep Opus-only for builds, edit only AGENTS.md prose
    why_not: >
      The literal request named AGENTS.md, but that file carried no build-lane content
      to remove — the operative ban lived in CLAUDE.md's §Model routing, the `builder`
      agent's frontmatter pin, the routing-guard hook's RULE text, and this decision
      record. A docs-only edit to the one file with nothing to remove would leave every
      actual enforcement point contradicting the new instruction.
  - option: Both Opus and Sonnet build, no dedicated tier
    why_not: >
      Not what was asked, and it blurs the routing table's one clean signal (which tier
      is the default `builder`). Restoring the pre-2026-07-21 arrangement (Sonnet
      builds, Opus reviews) returns to a known-good prior state rather than inventing a
      new hybrid.
  - option: Also flip the autonomous metabolism build loop back to Sonnet
    why_not: >
      Out of scope. The instruction was about "Sonnet being used as a worker" and named
      AGENTS.md; it did not mention the unattended nightly build loop, a materially
      higher-stakes system (ships code with no per-cycle human review) governed by its
      own ruling (R-V4-2). Left untouched pending a separate, explicit instruction.
evidence:
  - "Chat instruction, this session, 2026-08-17: \"Change the agents.md file so that the ban on Sonnet being used as a worker is removed.\""
  - "Scope confirmed via an explicit follow-up question before any file was edited: user selected \"Full reversal\" (CLAUDE.md + AGENTS.md + builder.md pin + routing-guard hook text + ruling_graph.yml HOUSE-U2), not a docs-only edit"
  - "config/ruling_graph.yml HOUSE-U2 updated + site/neuralwebdata/ruling_graph.json and docs/NEURAL_WEB_CASE_LAW.md regenerated via scripts/build_ruling_graph.py in the same PR"
affects: [".claude/agents/builder.md", ".claude/hooks/model_routing_guard.py", "CLAUDE.md", "AGENTS.md", "config/ruling_graph.yml"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-17
supersedes: [DEC:OPUS-BUILDS-SONNET-EXPLORES-FABLE-GATED]
---

## Grounds

Direct chat instruction in an interactive session, confirmed for full functional
scope (not a docs-only edit) via an explicit follow-up question before any file was
touched — the superseded decision's own "what would reopen this" clause required an
operator call rather than session-initiated drift, so scope was confirmed rather than
assumed before executing.

## What would reopen this

Renewed, measured build-quality complaints against Sonnet (mirroring the evidence
behind the 2026-07-21 order this reverses), or a further explicit operator
instruction. Reversing this decision is, by the same standard applied to its
predecessor, an operator call rather than a session's own initiative.
