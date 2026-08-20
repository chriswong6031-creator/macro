---
key: MARKET-MEMORY-W2C
title: Market Memory W2C prospective activation recovery
objective: >
  Keep the first honest W2C prospective opportunity on a live, exact activation
  chain. M0A is complete: production executed all three registered windows
  2026-08-17/18/19 inside 04:30–04:45 UTC and sealed lawful abstained rows.
  Later waves start from the remaining path to admitted, not from activation.
status: active
program: market-memory
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - engine/neuralweb/market_memory_technical_observation.py
  - engine/neuralweb/market_memory_technical_store.py
waves:
  - id: M0A
    title: First-cause repair and three-window prospective proof
    status: done
    pr: 5805
    next_action: >
      Proven. Do not reopen the nested __case_v1 intake repair unless the live
      technicals journal reproduces the noncanonical-filename exception.
  - id: M0B
    title: Exact-same-session technical capture by the registered 04:30 window
    status: todo
    depends_on: [M0A]
    next_action: >
      One causal PR for why the technical owner still lacks the opportunity
      session's SPY actual-output capture at 04:30 UTC (pinned session lagged
      at 2026-08-14 then 2026-08-18). Include the distinct 2026-08-19
      ticker-count and publish-last failures. Do not start in the proof session.
next_action: >
  Start M0B as one causal PR for the exact-same-session technical capture
  missing at 04:30 UTC. Do not backfill, do not treat in-window abstained as
  missed, and do not reopen #5805 without live reproduction.
do_not_redo:
  - Do not treat a lawful in-window abstained row as missed, absent, or an M0A failure.
  - Do not reopen #5805 or the nested __case_v1 filename admit without a live journal reproducing the noncanonical-filename exception.
  - Do not backfill a missed W2C row or fabricate an admitted opportunity.
  - Do not weaken PIT, authority, or freshness validators to manufacture admission.
  - Do not assume the old weekend context-freshness failure remains causal; diagnose from the live journal.
  - Do not reject leftover mixed-case root names in the same PR as admitting canonical nested __case_v1 paths.
  - Do not edit app/deploy/update.sh or deploy tests that #5804 already merged.
landmines:
  - Nested-path admission must round-trip artifact_relative_path. Any slash, mixed-case nested name, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - Experience timer enabled-but-inactive is not armed. Armed means enabled plus active/waiting with a future NextElapse.
  - technical_session_absent is a lawful same-session evidence miss, not a missed window. The writer did run.
  - Technicals Result=success with a lagged session is a different defect from technicals failing closed.
  - Session 2026-08-18 also lacked a trusted same-session pin; that is concurrent with, not a substitute for, the technical lag.
artifacts:
  - agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md
---

M0A first-cause repair: PR #5805, merged as `e1ec8865ac92`.
M0A three-window proof: `agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md`.
