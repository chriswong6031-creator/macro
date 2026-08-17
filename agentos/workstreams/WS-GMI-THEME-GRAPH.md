---
key: GMI-THEME-GRAPH
title: Global Market Intelligence theme graph
objective: >
  Connect global themes, evidence, transmission, and contagion into a governed graph.
  Done = the graph answers transmission questions with cited evidence at display tier.
status: active
program: gmi-theme-graph
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
waves:
  - id: W0
    title: Graph scaffolding
    status: done
  - id: R1
    title: "R1 answered (#5402)"
    status: done
    pr: 5402
  - id: W3A
    title: "Local theme plane — rights-gated Finviz/THS ltheme nodes (268+373), PIT
      MEMBER_OF memberships, capability sidecar, probation mapping; engine/theme_graph/*
      + data/theme_graph/*. No ThemeState, no ranking authority, no user surface."
    status: done
    pr: 5718
  - id: TRANSMISSION
    title: Transmission/contagion layer
    status: todo
    depends_on: [R1]
    next_action: >
      Reconcile with W3B ThemeState sequencing (Prophet V4 D-lane consumes it; see
      research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md §3 — a merge-order ruling is
      required before ThemeState work starts anywhere).
landmines:
  - >-
    Wave ids other than W0 were MINTED by the Phase 0 seeding session, not taken from
    research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md, which names only W0
    (verified: grep -noE '\bW[0-9]\b' over that file returns one hit, line 167). Do not
    cite them back to the masterplan; reconcile with the program owner before treating
    this decomposition as the program's own.
next_action: Wait for the 2026-08-15 scrape; then start the transmission layer.
---

## Context

Scaffolding is complete and R1 is answered in #5402. The transmission/contagion layer
needs the Saturday scrape as input. This is a healthy external wait, not a stall — the
distinction matters because the CEO brief separates "blocked and on time" from "blocked
and rotting".

## Provenance of this decomposition

Only `W0` is attested by the masterplan. `R1` and `TRANSMISSION` were minted here so the
work has ids at all; they are named descriptively rather than as `W1`/`W2`/`W3` precisely
so nobody reads them as the masterplan's own numbering. See the landmine above.
