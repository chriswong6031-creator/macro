---
key: OPUS-FABLE-MODE-ORCHESTRATOR
question: >
  Must every orchestrator-seat invocation spend Fable, or may a cheaper tier
  hold the seat for easier orchestration?
answer: >
  For easier tasks that do not need frontier judgment, Opus may take the Fable
  orchestrator role by running the `fable-mode` skill
  (`.claude/skills/fable-mode`), at roughly half Fable's price. Two forms:
  (1) an Opus MAIN session loads the skill and orchestrates directly;
  (2) a `ROUTE: orchestration` spawn runs explicit `model: 'opus'` and its
  commission directs the worker to load the skill — hook-enforced via the
  registry's `opus_alternative` key. No FABLE-WHY is required in the Opus form
  because FABLE-WHY audits fable SPEND and none occurs. The Fable form
  (explicit `model: 'fable'` + FABLE-WHY, reserved for work failing the
  draft-and-review test) is unchanged, as are all other tier assignments.
rationale: >
  Direct operator instruction, 2026-08-17, in the same message that
  commissioned the routing-control implementation: "For easier tasks, when
  Fable is not necessary, Opus can take on the Fable orchestrator role by
  running fable-mode skill, giving it better orchestration powers while also
  creating cost efficiency in token burn since Opus is half of Fable's price."
  The fable-mode skill (already on main) exists precisely to transfer the
  Fable working doctrine to prior-generation models as checkable output
  criteria.
alternatives:
  - option: Allow Opus orchestrator spawns unconditionally (no skill directive)
    why_not: >
      The instruction ties the seat to the skill — "by running fable-mode
      skill" — and the deterministic skill-directive check is what keeps the
      seat doctrine-bound rather than a silent tier downgrade.
  - option: Require FABLE-WHY on the Opus form too
    why_not: >
      FABLE-WHY is the fable-spend audit line; requiring it where no fable is
      spent dilutes the audit trail it exists to provide.
  - option: Main-loop-only (no spawn form)
    why_not: >
      The registry/guard already govern the spawn path; leaving the Opus seat
      unreachable there would push easier orchestration back to Fable spend,
      against the instruction's cost purpose.
evidence:
  - "Operator chat instruction 2026-08-17 (verbatim quoted in rationale)"
  - "PR #5823 (merge 7a6a6656e289): registry opus_alternative key, guard branch, orchestrator.md doctrine, agent_routing_context.py, positive/negative tests (test_opus_orchestration_* in tests/test_agent_routing_control.py; test_orchestrator_without_explicit_fable_denied in tests/test_model_routing_guard.py)"
  - ".claude/skills/fable-mode/SKILL.md present on main; drift test asserts the named skill exists"
affects: [".claude/agent-routing.json", ".claude/hooks/model_routing_guard.py", ".claude/agents/orchestrator.md", "CLAUDE.md", "AGENTS.md"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-17
---

## Grounds

Explicit operator instruction; implemented in the same PR as the routing
control plane it amends ([[DEC:AGENT-ROUTING-CONTROL]]). The guard denies an
Opus orchestration spawn whose commission lacks the fable-mode directive, and
denies any other non-fable model on the route, so the seat cannot silently
degrade below Opus-with-doctrine.

## What would reopen this

Operator instruction, or evidence that Opus-seat orchestration measurably
degrades outcomes on tasks that were classified as "easier" — which would
tighten the classification guidance, not necessarily remove the seat.
