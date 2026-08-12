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
    next_action: Work the red gates in research/context_index/BENCHMARK_RESULTS.md.
  - id: W2
    title: "Add agentos/** as a corpus (Agent OS Phase 3 dependency)"
    status: todo
    depends_on: [W1]
landmines:
  - "Advisory status is load-bearing: cited sources must be opened before acting on them, per CXI-R19."
next_action: Drive the benchmark gates green (W1).
created: 2026-07-15
updated: 2026-08-12
---

## Context

The context compiler the Agent OS builds on already exists here and already emits a cited
`context_packet.v1` with an adjudication mode. Agent OS Phase 3 extends it with the
`agentos/**` corpus rather than building a second retrieval system.
