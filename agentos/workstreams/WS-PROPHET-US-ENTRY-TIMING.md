---
key: PROPHET-US-ENTRY-TIMING
title: US Prophet structural late-entry diagnosis and reduction
objective: >
  Diagnose and materially reduce structural late-entry behavior in US Prophet without
  unacceptable false-positive cost. Done = a measured entry-timing delta on held-out
  episodes with the false-positive cost printed alongside it.
status: active
program: prophet-us
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: open
owns_paths:
  - engine/prophet_*.py
  - engine/cn_prophet_audit.py
waves:
  - id: W0
    title: Queue drain + backfill
    status: done
    pr: 5370
  - id: W1
    title: Verify the 22:30Z bake lands clean after backfill
    status: in_progress
    depends_on: [W0]
    next_action: >
      Read the 22:30Z bake log for the first post-backfill run. First-run-bomb law applies:
      a first run after a backfill is not evidence of steady state.
  - id: W2
    title: Entry-timing delta measurement on held-out episodes
    status: todo
    depends_on: [W1]
landmines:
  - "A first bake after any backfill looks anomalous by construction — do not read run #1 as steady state."
do_not_redo:
  - "Queue drain was root-caused and fixed in #5370 — do not re-diagnose the queue."
next_action: Verify the 22:30Z bake (W1).
created: 2026-08-05
updated: 2026-08-12
---

## Context

One of five active company P0 objectives (`US_PROPHET_ENTRY_TIMING` in Mastermind
`config/strategic_state.yml`). The backfill completed and the queue drained on 2026-08-11;
the open question is whether the first post-backfill bake is clean.
