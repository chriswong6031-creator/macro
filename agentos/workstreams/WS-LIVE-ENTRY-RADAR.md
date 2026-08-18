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
  - tests/fixtures/entry_radar/
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
    status: done
    pr: 5698
    depends_on: [W0]
    # Reconciled 2026-08-14 by the W3 session from merged evidence: PR #5698 MERGED
    # 2026-08-15T01:19:08Z, merge commit cf4134feaa99262cfd3bfa9b921d3444f48d5bf2
    # (gh pr view 5698; git merge-base --is-ancestor confirms it on origin/main).
    # Historical in_progress row predated the merge; no other state manufactured.
  - id: W3
    title: PR-3 1D/4H challenger family + PIT mutation tests
    status: done
    pr: 5724
    depends_on: [W2]
    # DONE at ACTUAL merge (never at armed): PR #5724 MERGED 2026-08-15T06:55:31Z,
    # squash commit 4b9706ef058eab3bccaa36966ca89ebd0c49936d; merged-main verified
    # (owned-path byte diff vs origin/main empty; registry probe on merged bytes:
    # C1 f0bbd6cf3a6e2339 · C2 d8ba60a25cfa7400 · C3 d54dc1e55c4261c8 ·
    # C4 dce21ac680233ee2 · C5 13dec66345a0376c · G0 9be89a8acc8b905c unchanged;
    # F1 still NotYetSpecified). Contract lock = §18 A5; review receipts =
    # research/live_entry_radar/W3_REVIEW_DISPOSITIONS.md; handoff =
    # agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-15.md.
  - id: W4
    title: PR-4 live evaluator on the VPS plane (5-min RTH)
    status: done
    pr: 5768
    depends_on: [W1, W3]
    # DONE at ACTUAL merge (never at armed): PR #5768 MERGED 2026-08-16T03:13:45Z,
    # squash commit 1a170f9ceba1005ca79af6a631cb02045bf62f36; merged-main verified
    # (owned-path byte diff head-vs-squash empty; six frozen detector hashes
    # asserted in-suite, F1 still NotYetSpecified; entry-radar CI step now the
    # W1..W5 union, 22 suites). Ships STAGED NOT ARMED behind
    # ENTRY_RADAR_LIVE_ENABLE per the commissioning's deployment boundary;
    # activation + the §15 full-RTH cadence measurement are the operator's per
    # research/live_entry_radar/W4_DEPLOY_PLAN.md. Adversarial receipts:
    # research/live_entry_radar/W4_REVIEW_DISPOSITIONS.md; real-data receipts
    # (incl. closing W3's vendor-minute unverified row): W4_REAL_DATA_SMOKE.md;
    # handoff: agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-15-w4.md. The parallel
    # W5 lane's code merged mid-session; #5768 reconciled the shared files
    # (producers-guard union, sentinel SURFACES union, update.sh sibling
    # blocks); W5's own row/handoff remain that session's to write.
  - id: W5
    title: PR-5 forward evidence + replay under Evaluation OS
    status: done
    pr: 5825
    depends_on: [W3]
    # Confirmatory receipts on main: #5825 squash 0394d6e16407 (2026-08-17T10:08:44Z).
    # Code path #5741/#5780. 0 control_match_unavailable on both panels.
  - id: W5.1
    title: Persist control-pool diagnostics on the existing W5 summary surface
    status: done
    pr: 5833
    depends_on: [W5]
    # DONE at ACTUAL merge: PR #5833 MERGED 2026-08-17T12:49:55Z (squash
    # 4cebae78d323326dac79aed14b951fc2cfe37740). Serialization-only n_cell /
    # k histograms / overlap_share on existing W5 summary tables. Matching,
    # CONTROL_K, M3, M14, NC-2, looks untouched. Restored here after the W6
    # #5834 squash clobbered this wave row; do not drop it again when editing
    # the shared workstream file. Handoff:
    # agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-17-w5.1.md (suffixed; the
    # dated 2026-08-17.md addendum is the compiler-visible continuation).
  - id: W6
    title: PR-6 deterministic Research Priority (ACCRUING)
    status: in_progress
    pr: [5834, 5845]
    depends_on: [W5]
    # In progress: RP1 shipped on main as #5834 squash 39985e14, then Sol
    # review blockers required a methodological correction (unit-invariant
    # submeasure percentiles, canonical priority_value, name-snapshot
    # population, real-input receipt, C3 seam + pinned hashes). Follow-up
    # PR #5845 is the Sol re-review head (ranking-law PASSES; bounded
    # snapshot_conflict / receipt-wording / W5.1-memory follow-up). NOT done.
    # Do not start W7.
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
next_action: Sol final-reviews PR #5845 bounded follow-up (snapshot_conflict firewall, real-substrate-smoke receipt wording, W5.1 memory). Ranking-law correction PASSES; do not redesign the score. W5.1 merged as #5833. Do not mark W6 done. Do not start W7 or W9. W8 UI reference remains #5737.
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
