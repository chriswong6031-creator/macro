---
key: LIVE-ENTRY-RADAR
title: Live Entry Radar — real-time tactical entry discovery/ranking for U.S. equities
objective: >
  Build a new, separate real-time U.S. tactical entry system (washout→turn detection inside
  structurally strong names, ranked by forward asymmetry) as a champion/challenger research
  product with a forward ledger. Prophet's selection/gating stays byte-identical. Done =
  entry_radar.html live on the VPS plane with the G0/C1..C5 arena accruing evidence under the
  frozen PR-0 contract, and every promotion claim gated by Evaluation OS law.
status: active
program: market-timing-intelligence
p0: US_PROPHET_ENTRY_TIMING
repos: [macro, terminal]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: open
owns_paths:
  - engine/entry_radar/
  - scripts/entry_radar_
  - templates/entry_radar.html.j2
  - site/entry_radar.html
  - data/entry_radar/
  - research/live_entry_radar/
  - mockups/refs/entry_radar/
waves:
  - id: W0
    title: PR-0 archaeology + frozen research contract (Tracks A–E, kill-registry compliance)
    status: in_progress
    pr: 5578
    next_action: >
      Merge the PR-0 contract (research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md) with all
      PENDING slots resolved except the operator-facing G0-VIS glyph gate.
  - id: W1
    title: PR-1 probe universe + candidate enlistment bus
    status: todo
    depends_on: [W0]
    next_action: >
      Build funnel layers A–D + mastermind.entry_probe_nomination.v1 per contract §6 and the
      Track C producer census. Acceptance: a lobe-nominated small cap outside the hot universe
      lands in the Probe Set with provenance intact.
  - id: W2
    title: PR-2 detector framework + G0 Grey Dot exact + parity fixtures
    status: todo
    depends_on: [W0]
  - id: W3
    title: PR-3 1D/4H challenger family + PIT mutation tests
    status: todo
    depends_on: [W2]
  - id: W4
    title: PR-4 live evaluator on the VPS plane (5-min RTH)
    status: todo
    depends_on: [W1, W3]
  - id: W5
    title: PR-5 forward evidence + replay under Evaluation OS
    status: todo
    depends_on: [W3]
  - id: W6
    title: PR-6 deterministic Research Priority (ACCRUING)
    status: todo
    depends_on: [W5]
  - id: W7
    title: PR-7 outcome-calibrated Opportunity model (gated on honest sample)
    status: todo
    depends_on: [W6]
  - id: W8
    title: PR-8 UI reference + RIG (Prophet Board sister language, operator directive 2026-08-13)
    status: todo
    depends_on: [W0]
  - id: W9
    title: PR-9 production UI + live RTH verification
    status: todo
    depends_on: [W4, W6, W8]
landmines:
  - "Session worktrees are sparse: data/, site/, mockups/ are absent locally — artifact-existence checks must use git ls-files / git show or the primary checkout (read-only), never a bare ls."
  - "DNR:KILL-WASHOUT-TURN (entry-stack Amendment-3, #1747) is adjacent: any promotion of a Radar detector must confront that kill by name; display/accruing tier is free, authority is not."
  - "Prophet is untouchable: engine/entry_signal.py and engine/prophet_*.py belong to WS:PROPHET-US-ENTRY-TIMING; every Radar engine PR shows a clean diff on those paths."
  - "One stock WebSocket owner estate-wide; no second market-data plane; GitHub cron is never product cadence (VPS-primary per prophet-live pattern)."
  - "1D LIVE replay requires minute-level reconstruction; backfilling intraday observations from EOD closes is forbidden and mutation-tested (contract §5)."
  - "Depth is context, never authority (entry-stack expansion finding); no detector may require a StochRSI zero print."
next_action: Land PR-0 (W0); then W1 (universe/bus) and W2 (G0 parity) can start in parallel sessions off the frozen contract.
---

## Context

Operator/CEO execution handoff (2026-08-13) commissioned a real-time entry discovery,
comparison and ranking engine — archetype: structural strength → temporary weakness → selling
exhaustion → observable turn → renewed demand — explicitly separate from Prophet conviction
and from the existing validated entry gauge. Same-day operator design directive: the new
Prophet Board is the direct design reference; Radar is a sister product in that exact
card/layout language with only the information architecture changed.

Governing document: `research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` (frozen at PR-0
merge; §18 append-only amendments). Archaeology evidence: `research/live_entry_radar/TRACK_[A-E]_*.md`.
Champion G0 is the Terminal repo's early anticipation dot (`charting-app/signal_layer/confluence_v2.py`);
cross-repo parity is fixture-enforced, never copy-paste drift. Evaluation reuses the
Evaluation OS + the PSS §7 timing-ruler discipline; ranking ships as ACCRUING Research
Priority until house promotion gates clear.
