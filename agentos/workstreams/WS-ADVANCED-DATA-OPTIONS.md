---
key: ADVANCED-DATA-OPTIONS
title: Advanced Data — Options EOD + Off-Exchange Intelligence OS
objective: >
  Convert the options/off-exchange estate from an interpret-it-yourself dashboard into a
  standalone anticipation and risk intelligence lobe with bounded Prophet confluence.
  Done = ranked, falsifiable, receipt-backed EOD signals with explicit no-signal/degraded
  states, production-proven per slice (AD-0…AD-15 per the operator-held recovery masterplan).
status: awaiting_review
program: options-intelligence
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
waves:
  - id: AD-0
    title: Recovery archaeology + production truth + AD-1 freeze
    status: done
    pr: [5830, 5838, 5849]
  - id: AD-1P0
    title: Semantic-authority freeze (v1.2) before implementation
    status: awaiting_ci
    depends_on: [AD-0]
    next_action: Sol reviews the AD-1P0 amendment PR; on PASS the next decision is AD-1 GO.
  - id: AD-1
    title: Daily EOD Options Intelligence Brief
    status: todo
    depends_on: [AD-0]
    next_action: Do not start until AD-0 is reviewed; then execute research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md.
landmines:
  - >-
    The entire host-side intraday options launchd fleet (15 units incl. the sparse-selector
    canary) is NOT loaded on the Mac Studio as of 2026-08-17 (verified launchctl probes,
    AD-0 ledger §2.3). Do not treat in-repo plists under ops/launchd/ as running machinery.
  - >-
    Exactly one options-derived input reaches live Prophet rank: gex_confirm_verdict in C1
    fusion, lawful solely via DNR:KILL-POSITIONING-FUSION Amendment 1. Any wider fusion of
    positioning keys outside that arena remains ILLEGAL.
  - >-
    The Macro host intraday options fleet is DISARMED BY DEFAULT pending the AD-9 ruling
    (Sol review on #5830) — do not load, install, or re-arm any ops/launchd options unit.
  - >-
    Historical/preregistered campaign and episode evidence is preserved append-only even
    where its runtime is retired (Sol review on #5830) — retirement never deletes evidence.
decisions:
  - "DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT"
  - "DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION"
do_not_redo:
  - >-
    Do not re-audit the seven sparse-selector PRs (#5747 #5694 #5696 #5708 #5711 #5790
    #5801) — reconciled with merge SHAs in the AD-0 ledger; #5711 is a closed duplicate of
    #5708; W1A-A/B modules are test-only with zero consumers.
  - >-
    Do not re-derive the EOD source map: Polygon snapshot (POLYGON_API_KEY, ~18:30 ET,
    session-stamped) + massive.com OPRA aggs (NOT entitled to trades_v1/quotes_v1) +
    FINRA CNMS/ATS keyless. AD-0 ledger §4.
  - >-
    Do not resurrect darkpool direction labels (v2 null walk-forward + DNR:PSS-AF1) or the
    DOI/skew-decel families (killed).
next_action: Sol review of the AD-1P0 semantic-authority freeze; on PASS, commission AD-1 implementation per the amended handoff (v1.2).
artifacts:
  - research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
---

## Context

AD-0 (2026-08-17) reconstructed current truth from origin/main 7a6a6656 and production:
the EOD spine, darkpool desk, flow desk, GEX/gex_confirm chain, episode ledgers, NW
context, and Terminal export are PROVEN_LIVE; the host intraday fleet and sparse-selector
path are dark; Sector consumption is zero; the composed decision layer (horizon/asymmetry/
trigger/invalidation/Prophet-state cards, NO_SIGNAL law) is NOT_BUILT and is exactly the
AD-1 slice. Full maturity ledger, salvage matrix, no-rebuild matrix, and 25 adjudicated
questions live in the AD-0 ledger artifact.

## Provenance of this decomposition

The full AD-0…AD-15 decomposition is durable repo state in the committed masterplan
(research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md,
landed per the Sol review on #5830). AD-0 and AD-1 additionally carry their own in-repo
wave artifacts (ledger + implementation handoff).
