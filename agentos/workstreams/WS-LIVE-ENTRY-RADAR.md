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
  - research/LIVE_ENTRY_RADAR_
  - templates/entry_radar.html.j2
  - site/entry_radar.html
  - data/entry_radar/
  - research/live_entry_radar/
  - mockups/refs/entry_radar/
waves:
  - id: W0
    title: PR-0 archaeology + frozen research contract (Tracks A–E, kill-registry compliance)
    status: done
    pr: 5578
  - id: W1
    title: PR-1 probe universe + candidate enlistment bus
    status: done
    pr: 5625
    depends_on: [W0]
    # Reconciled 2026-08-14 by the W2 session from merged evidence: PR #5625 MERGED
    # 2026-08-14T17:31:07Z, merge commit 000732bd80d594a62f9923466e5be1cbe9b86ec7
    # (gh pr view 5625 --json state,mergeCommit,mergedAt). Historical in_progress row
    # predated the merge; no other state transition manufactured.
  - id: W2
    title: PR-2 detector framework + G0 Grey Dot exact + parity fixtures
    status: in_progress
    depends_on: [W0]
    next_action: >
      G0-VIS is CLOSED (operator confirmed the raw grey family 2026-08-13, contract §18
      A1) — the parity freeze is unblocked. PR-2 additionally owns the A1 adapter
      obligation: ingest the unified indicator/v1 signals stream preserving emitter
      type/subtype/quality/stage verbatim, and mint expert-family keys from emitter
      receipts (STARTER/RE-ENTRY enumerations are PR-2 archaeology). PR number added
      at ship.
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
  - "Expert Preservation ruling (contract §18 A1, DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED): Terminal's entry-event families are candidate experts — never flatten them into one entry_signal boolean or a generic category; preserve identity in the mastermind.entry_event.v1 store with typed promotion/de-dup edges and per-field field_origin. STARTER/RE-ENTRY names are operator-observed UI labels until PR-2 mints emitter-receipted enums. Radar records experts; the future Stock Identity / Expert Routing program (not created here) owns per-security selection AND must clear DNR:KILL-OUTCOME-AUDITION (per-name outcome audition is killed; structure-measurement tailoring is the open lane)."
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
