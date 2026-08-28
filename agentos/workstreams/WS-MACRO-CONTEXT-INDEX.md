---
key: MACRO-CONTEXT-INDEX
title: Macro context index (CXI) — governed project-context retrieval
objective: >
  Retrieve governed project context from Macro and the two sibling repositories with cited
  packets. Done = benchmark gates green, so the index can move from advisory to relied-upon.
status: active
program: macro-context-index
repos: [macro, terminal, mastermind]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - scripts/context_index_query.py
  - config/context_index.yml
  - research/context_index/**
waves:
  - id: W0
    title: "CXI-2 CLI live (search/open/recent/explain/status, context_packet.v1)"
    status: done
  - id: W1
    title: Benchmark gates to green so the index stops being advisory
    status: in_progress
    next_action: >
      Superseded in structure by the Sol C0->C8 completion program
      (research/MACRO_CONTEXT_INDEX_COMPLETION_MASTERPLAN_BY_SOL.md); gate-green
      work now lands as waves C1-C3 under Sol operation keys.
  - id: W2
    title: "Add agentos/** as a corpus (Agent OS Phase 3 dependency)"
    status: done
    next_action: >
      CORRECTED 2026-08-28 (was a stale todo): the agentos/** corpus already
      landed via Agent OS Phase 3 / PR #5561 (Sol capability ledger:
      BUILT_NOT_PROVEN). Integration PROOF is wave C4 of the completion program.
  - id: C0
    title: "Benchmark Truth Recovery (Sol op macro-context-index-completion-20260828-sol-001)"
    status: done
    next_action: >
      Sol adversarial review of the C0 head (PR held HOLD-FOR-SOL). Evidence:
      agentos/handoffs/WS-MACRO-CONTEXT-INDEX-2026-08-28.md; baselines v6/v7 in
      research/context_index/BENCHMARK_RESULTS.md.
landmines:
  - "Advisory status is load-bearing: cited sources must be opened before acting on them, per CXI-R19."
  - "Retrieval ranking frozen under the C0 carrier; C1 begins only on explicit Sol CONTINUE."
next_action: Await Sol review of C0; then C1 deterministic relevance + abstention on frozen v1.6 gold.
---

## Context

The context compiler the Agent OS builds on already exists here and already emits a cited
`context_packet.v1` with an adjudication mode. Agent OS Phase 3 extends it with the
`agentos/**` corpus rather than building a second retrieval system.
