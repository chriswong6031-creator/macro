---
key: AGENT-ROUTING-CONTROL
question: >
  How is the model-tier law enforced on direct Agent/Task spawns, given that the
  prior guard accepted any syntactically explicit non-fable model regardless of
  whether it fit the task's semantic class?
answer: >
  A deterministic execution-policy registry (`.claude/agent-routing.json`) plus
  hook enforcement. Fable classifies each bounded job with a `ROUTE: <class>`
  line; the registry maps each route to ONE canonical custom agent and model
  (extract→extractor/haiku, census→scout/sonnet, research→researcher/sonnet,
  draft→drafter/sonnet, analysis→analyst/opus, debug→debugger/opus,
  build→builder/sonnet, review→reviewer/opus, design→designer/opus,
  judgment→main loop only, orchestration→orchestrator).
  `.claude/hooks/model_routing_guard.py` (PreToolUse) denies missing/unknown
  routes, route↔agent/model mismatches, under-specified commissions (required
  SECTION: labels per route), and bypass via general-purpose/Explore/Plan/fork;
  `.claude/hooks/agent_return_guard.py` (SubagentStop) blocks a routed worker
  ONCE if its final message misses the STATUS/RESULT/EVIDENCE/GAPS/DEVIATIONS
  packet, then allows the second stop (no loops). The FABLE-WHY gate and
  Workflow script routing law are unchanged. Frontmatter pins remain the
  runtime model truth; tests/test_agent_routing_control.py pins
  registry↔frontmatter against drift.
rationale: >
  Chairman-supplied frozen architecture handoff, implemented 2026-08-17 as
  PR #5823. The failure class it closes: Fable identifies a mechanical job,
  explicitly chooses a model/agent, the choice is syntactically explicit so the
  old guard allows it — an expensive tier gets spent on the wrong semantic
  class, and weak worker prompts/returns force expensive executive repair
  turns. Separating classification (Fable) from routing policy (registry),
  enforcement (hooks), worker behavior (agent system prompts), and return
  validation (SubagentStop) makes the wrong spend hard to reach accidentally.
alternatives:
  - option: LLM-based semantic route classifier hook
    why_not: >
      On the handoff's explicit do-not-overbuild list for v1 — the gate must
      cost zero model tokens and stay deterministic/testable.
  - option: A second overlapping spawn-control hook
    why_not: >
      The existing model_routing_guard.py was already wired on
      Agent|Task|Workflow; extending it avoids two guards with divergent
      policy readings.
  - option: Registry as a second runtime source of model truth
    why_not: >
      Frontmatter stays the runtime pin; the registry is policy, and a drift
      test keeps the pair identical. Two runtime truths would eventually
      disagree in production.
evidence:
  - "PR #5823 (merge 7a6a6656e289, 2026-08-17): registry, five new agents + analyst, guard rewrite, SubagentStop guard, settings wiring, 46 focused tests"
  - "Handoff packet (chairman-supplied, frozen): 00_START_HERE / 01_MASTER_IMPLEMENTATION_HANDOFF / 02_ACCEPTANCE_TEST_MATRIX"
  - "tests/test_agent_routing_control.py + tests/test_model_routing_guard.py green on the merged head; ci-gate green (designed-red ci-authority/codex/merge-queue-pilot excluded per #5815)"
affects: [".claude/agent-routing.json", ".claude/hooks/model_routing_guard.py", ".claude/hooks/agent_return_guard.py", ".claude/settings.json", "CLAUDE.md", "AGENTS.md"]
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-17
---

## Grounds

The chairman supplied a frozen implementation handoff (deterministic v1, no LLM
classifier, extend the existing guard, one correction pass at SubagentStop) and
commissioned it end-to-end. The registry is an execution-policy artifact, NOT a
strategic control plane — it owns route→agent/model mapping and prompt/return
contracts only, per invariant I1.

## What would reopen this

Measured v1 friction (route counts, rejected-spawn reasons, repair rates — the
handoff's §18 observables) justifying taxonomy or contract changes; or an
operator order changing tier assignments, which edits the registry + frontmatter
pair, not the architecture. Related: [[DEC:SONNET-BUILDS-AGAIN]] (build tier),
[[DEC:OPUS-FABLE-MODE-ORCHESTRATOR]] (orchestrator seat).
