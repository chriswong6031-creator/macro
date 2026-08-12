---
key: GMI-THEME-GRAPH
title: Global Market Intelligence theme graph
objective: >
  Connect global themes, evidence, transmission, and contagion into a governed graph.
  Done = the graph answers transmission questions with cited evidence at display tier.
status: blocked
program: gmi-theme-graph
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
blocked_by:
  - "Waiting on the scheduled Saturday 2026-08-15 scrape. External dependency, on time — not stalled."
waves:
  - id: W0
    title: Graph scaffolding
    status: done
  - id: W1
    title: Evidence ingestion
    status: done
  - id: W2
    title: "R1 answered (#5402)"
    status: done
    pr: 5402
  - id: W3
    title: Transmission/contagion layer
    status: todo
    depends_on: [W2]
    next_action: Start after the 2026-08-15 scrape lands.
next_action: Wait for the 2026-08-15 scrape; then start W3.
created: 2026-07-28
updated: 2026-08-11
---

## Context

W0–W2 are complete through 2026-08-11, with R1 answered in #5402. W3 needs the Saturday
scrape as input. This is a healthy external wait, not a stall — the distinction matters
because the CEO brief separates "blocked and on time" from "blocked and rotting".
