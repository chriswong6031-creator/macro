<!-- GENERATED — DO NOT EDIT BY HAND. Regenerate with `python3 scripts/agentos.py status`. Authored truth lives in agentos/; this file is derived (invariant I3). Advisory only: it reports state and gates nothing (invariant I1). -->

# Agent OS state

Generated: 2026-08-19T15:02:31Z  |  28 workstreams (23 active · 1 awaiting_ci · 1 awaiting_review · 3 blocked)

| Input | Value |
|---|---|
| active_builds | data/governance/active_builds.json@2026-08-19T15:02:31.031579+00:00 |
| active_builds age | 0.0h |
| worktrees | 1 |
| records | 28 WS · 87 DEC · 71 DSC · 82 handoffs |

## Degraded inputs

- active_builds.v1 merged window is TRUNCATED — a merged PR may read 'unknown'
- Mastermind checkout not found — p0 ids unvalidated, p0_active unknown
- uncommitted-work scan skipped over 1 worktrees (one `git status` each) — re-run with --scan-uncommitted for stranded work

## Workstreams

| Key | Status | Owner | Program | Waves | PRs | Next action |
|---|---|---|---|---|---|---|
| [`WS:ADVANCED-DATA-OPTIONS`](../agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md) | awaiting_review | coo-fable | options-intelligence | awaiting_ci:1 done:2 | #5830(merged) #5838(merged) #5849(merged) #5860(merged) #5872(merged) | Sol adversarial review of the AD-1 implementation PR; on PASS, run the production-acceptance continuation (merge, nightly advance, served-page proof, acceptance record). AD-2 stays closed. |
| [`WS:AGENT-OS`](../agentos/workstreams/WS-AGENT-OS.md) | active | chairman | project-active-build-control | done:5 todo:1 | #5472(merged) #5556(merged) #5472(merged) #5649(merged) #5561(merged) | Phase 4 is eligible but not started. Commission it as a separate high-blast-radius, report-only hook wave; keep the readiness envelope graph-only and Mastermind's improvement agenda as the sole ranked queue. |
| [`WS:ALPHA-INTELLIGENCE-INTEGRATION`](../agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md) | active | fable | mastermind-semantic-system-map | done:1 todo:8 | — | Operator dispatches the six read-only Grok censuses (pack files GROK-A0/B0/D0/ E0/F0/G0) with the riders in PASS-0 §6; FABLE-A dispatches only after GROK-A0 returns, under the PASS-0 §7 conditions. |
| [`WS:BREATHING-PLATFORM`](../agentos/workstreams/WS-BREATHING-PLATFORM.md) | active | coo-fable | prophet-us | done:3 todo:2 | — | Land the revival wave (PR-A Massive close truth, PR-B launchd primary clock, PR-C liveness ruler), deploy the launchd agent on the Mac Studio, run replay acceptance, then hold for Monday's live session measurement. |
| [`WS:CALCBENCH-FILING-FORENSICS-PARITY`](../agentos/workstreams/WS-CALCBENCH-FILING-FORENSICS-PARITY.md) | blocked | coo-fable | fundamental-forensics | done:1 in_progress:1 todo:8 | — | Check whether R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID has an updated_at later than 2026-08-11T03:27:33Z; if so, dispatch attested-history-aapl-seed.yml from main, approve the protected environment, and independently admit the four downloaded artifacts with verify_fundamental_forensics_attested_history_seed_bundle.py. |
| [`WS:CI-MERGE-CONTROL-PLANE`](../agentos/workstreams/WS-CI-MERGE-CONTROL-PLANE.md) | active | coo-fable | project-active-build-control | awaiting_ci:1 done:1 in_progress:2 | — | W-GATE-SPLIT: PR 5969 merged; qledger clock heal PR 5972 merged (the nightly had committed a registrar-local write-once clock; now gitignored). Proof runs dispatched 11:01Z: main baseline 32245502253 on the code-only gate, and a hand-dispatched data-health.yml run 32245526648 to prove the issue plumbing. Then W3 to prove the issue plumbing, verify the first post-nightly firing, then W3 at >=72h - trailing-100 green rate above 90% via scripts/ci_gate_reliability_report.py plus two consecutive ordinary PRs merged with no main-red-repair. W-SEMANTIC-PROOF remains stopped; W-REWRITE remains separately commissioned. |
| [`WS:CN-LIMIT-ALPHA`](../agentos/workstreams/WS-CN-LIMIT-ALPHA.md) | active | chairman | china-system | done:6 todo:3 | — | P-B3 shipped on PR #5729: NULL=12, UNINFORMATIVE=8; P-D not opened. Parallel only: (1) P-B2-ACCRUAL live min(first_seen) after the first asia-close write; (2) P-C when its data gates open; (3) full-A exact-plane re-measurement. P-D stays last and currently has no P-B3 input. No production scoring change. |
| [`WS:COMMERCIAL-PATH-ALERTING`](../agentos/workstreams/WS-COMMERCIAL-PATH-ALERTING.md) | active | ops | shared-auth-entitlements | awaiting_ci:1 | #5734(merged) | Stay on PR #5734 (armed merge-on-green). After merge, confirm /etc/macro-sentinel.env has a human-watched channel if DELIVER was SKIP. |
| [`WS:CUSTOMER-DATA-BACKUP`](../agentos/workstreams/WS-CUSTOMER-DATA-BACKUP.md) | blocked | ops | shared-auth-entitlements | awaiting_ci:1 todo:1 | #5733(merged) | Operator fills docs/RESTORE_RUNBOOK.md §Vendor backup/PITR and §Scratch-Supabase restore receipt by creating mmx-restore-scratch-YYYYMMDD and running `python -m scripts.backup_user_tables restore --backup-id <id> --dest-db-url "$SCRATCH_DB_URL" --i-am-restoring-into-scratch`. |
| [`WS:DEFENSE-PROCUREMENT-V3`](../agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md) | active | coo-fable | government-revenue-foresight | done:3 in_progress:1 todo:3 | #5814(merged) #5819(merged) #5836(merged) #5885(merged) #5882(merged) #5856(merged) #5856(merged) #5932(merged) | Sol D1 acceptance review. Do not start Atlas/D2. Do not merge #5424. Do not re-baseline. |
| [`WS:EARNINGS-INTELLIGENCE-OS`](../agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md) | active | coo-fable | earnings-intelligence | done:3 in_progress:1 todo:1 | #5817(merged) #5841(merged) | Implement E2-D only: render the live AAPL FY2026 Q3 event_workspace.v1 (generation f709a0a6ec514282d5769e7d, event_id evt_cik0000320193_2026q3_results) in the existing Macro dossier Company Intelligence glance with the same stance and event id as Terminal Brief. Do not reopen E2-T1. Do not re-read the v1 score overlay. Do not start E3+. |
| [`WS:EVAL-OS-MEASUREMENT-LAW`](../agentos/workstreams/WS-EVAL-OS-MEASUREMENT-LAW.md) | active | Eval-OS session (COO Fable lane) | qualitative-intelligence | done:3 in_progress:1 todo:1 | — | Merge #5534, #5577 and the P0c-2 PR; then confirm the first nightly writes data/qledger/evidence_clock_start/<family>.json for stock_desk, thematic_desk and demand_chain, and record those three timestamps as the real evidence-clock start. |
| [`WS:EVAL-OS-OUTPUT-HEALTH`](../agentos/workstreams/WS-EVAL-OS-OUTPUT-HEALTH.md) | active | Eval-OS T4 session (COO Fable lane) | qualitative-intelligence | in_progress:1 | — | W1 in flight: core + admin built on claude/eval-os-t4-output-health; adversarial review, Agent OS handoff, PR → merge → live verify. |
| [`WS:EVAL-OS-T1-ENGINE-REGISTRY`](../agentos/workstreams/WS-EVAL-OS-T1-ENGINE-REGISTRY.md) | active | Eval-OS session (COO Fable lane) | qualitative-intelligence | done:3 | #5620(merged) | W3 shipped. Next decision is the CEO's at the next checkpoint: T4 output-health, T12 Agent OS tier interface, or let prospective evidence accrue; T7/T8 stay calendar-bound. Standing residue: 2 deliberate output_class nulls (cortex — needs a CEO ruling on the two-species cell, and its attention grader coerces direction 0 to a long bet, repair before evaluating that half; options_structure — curate when the Package D producer ships), plus the desk hit-rate metric-binding warning (hit is a non-refutation endpoint, no-skill null far above 0.5 — T7 must bind dir_accuracy or placebo-netted rates). |
| [`WS:FINANCIAL-INTELLIGENCE-FABRIC`](../agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md) | active | coo-fable | fundamental-forensics | done:2 todo:10 | #5889(merged) | FIF-1 is DONE and financial_intelligence_packet.v1 is FROZEN on main (PR #5889, f4183edade53603fad7a97f702eb4c6e5eabff5d). FIF-2 is UNLOCKED and NOT_STARTED. Do not reopen accepted packet semantics. Do not create FIF-1R4. A later session may start FIF-2 from the masterplan. |
| [`WS:FUNDAMENTAL-FORENSICS`](../agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md) | blocked | coo-fable | fundamental-forensics | done:1 in_progress:1 todo:1 | #5794(merged) #5820(merged) | Sol accepted MAX_UNIVERSE_ISSUERS=4000. Squash-merge |
| [`WS:GMI-THEME-GRAPH`](../agentos/workstreams/WS-GMI-THEME-GRAPH.md) | active | coo-fable | gmi-theme-graph | done:3 todo:1 | #5402(merged) #5718(merged) | Wait for the 2026-08-15 scrape; then start the transmission layer. |
| [`WS:GREY-DEER-RISK-INTELLIGENCE`](../agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md) | active | coo-fable | market-regime-risk | awaiting_ci:2 done:1 todo:16 | #5963(merged) #5961(merged) #5961(merged) | Merge #5961 (GD-1 artifacts + canonical-identity reconciliation); then run the GD-1B adversarial acceptance review (independent reviewer + Fable final, Sol on architecture implications); author the GD-2 build packet from the 2026-08-19 archaeology (settled-envelope seam, live seam, CN/HK ledger root cause) reconciled against the freeze. |
| [`WS:LIVE-ENTRY-RADAR`](../agentos/workstreams/WS-LIVE-ENTRY-RADAR.md) | active | coo-fable | market-timing-intelligence | done:7 in_progress:1 todo:4 | #5578(merged) #5625(merged) #5698(merged) #5724(merged) #5768(merged) #5825(merged) #5833(merged) #5834(merged) #5845(merged) | #5845 MERGED 2026-08-18T12:40:51Z (squash 8552db805ea6) — Sol's post-merge acceptance of its bounded follow-up is the remaining W6 item; do not redesign the score, do not mark W6 done, do not start W7 or W9. W8 UI reference remains #5737. NEW: W4.1 live transport correction commissioned 2026-08-18 (Chairman Prophet Operator Lab program, V4-B5A) — see the W4.1 wave row for frozen scope/receipts; do not merge it against a knowingly red W4 baseline (#5897 open, test-only). |
| [`WS:MACRO-CONTEXT-INDEX`](../agentos/workstreams/WS-MACRO-CONTEXT-INDEX.md) | active | coo-fable | macro-context-index | done:1 in_progress:1 todo:1 | — | Drive the benchmark gates green (W1). |
| [`WS:MARKET-MEMORY-W2C`](../agentos/workstreams/WS-MARKET-MEMORY-W2C.md) | awaiting_ci | coo-fable | market-memory | awaiting_ci:1 todo:1 | — | Own the M0A PR through merge and production technicals verification, then stop. Do not repair context freshness, API restart, or mixed-root residue in M0A. |
| [`WS:PROPHET-CONDITIONAL-FUSION`](../agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md) | active | fable | prophet-us | done:6 todo:4 | — | Automatic W3 accrual on the natural us_prophet_ledgers lane. Do not start PR-3E. Do not start C2/C3/C4/C5 or Prophet V4. Do not read C1-vs-shadow outcomes. Durable paired-race N=2 unmatured (stamps 2026-08-17 and 2026-08-18); matured H=10 N=0. First lawful comparison remains PENDING until 20 matured H=10 sessions. Leave the frozen 2026-08-17 W3 parts byte-identical. |
| [`WS:PROPHET-HK-CA-REVAMP`](../agentos/workstreams/WS-PROPHET-HK-CA-REVAMP.md) | active | fable | prophet | in_progress:1 todo:9 | — | Merge the CA-TRUTH PR (canonical Canada board, branch claude/ca-truth-canonical-board) and verify the first owed TSX session's artifact/page/ledger parity receipt on the production reader. |
| [`WS:PROPHET-US-AVAILABILITY`](../agentos/workstreams/WS-PROPHET-US-AVAILABILITY.md) | active | coo-fable | prophet-us | in_progress:2 todo:2 | — | W3 (2026-08-17 outage hardening) is the live wave: land its PR, verify all five boards fresh, then fold the wedge/hostage classes into the W2 fire-drill list. W1 operator items stand: launchd installer; plus the new W3 operator asks on issue #5742 (cancel debris run 32077948964 post-recovery; census-lane cadence ruling; M1 host revival owns the collect_tail re-pin). |
| [`WS:PROPHET-US-ENTRY-TIMING`](../agentos/workstreams/WS-PROPHET-US-ENTRY-TIMING.md) | active | coo-fable | prophet-us | done:1 in_progress:1 todo:1 | #5370(unknown) | Verify the 22:30Z bake (W1). |
| [`WS:PROPHET-US-V4-RECOVERY`](../agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md) | active | fable | prophet-us | done:3 in_progress:2 todo:25 | #5832(merged) #5847(merged) #5859(merged) | V4-D1 complete. Route to Sol for three adjudications: (1) commission d2 with GMI per research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md; (2) ratify the D3/W3B merge-order recommendation with GMI; (3) optionally commission the d5 contract-only lane in parallel (D1_D5_READINESS_RULING.md). Rights decisions routed in the census §7 await Chairman/Sol. A-lane unchanged: DO NOT SPAWN A1 — sibling-owned, acceptance-by-adoption (#5742); a2/a3 adopt-first. B5A LAB lane (Chairman 2026-08-18): day-1 wave COMPLETE 2026-08-19 — W4.1 #5929 + P-LAB-API #5928 built, twice-reviewed MERGE-SAFE, armed (merge gated on the house-law-registry VMRK self-heal at the next nightly snapshot); R5 RIG cycle verdict REVISE recorded on #5931 (armed); R5.1+R5.2 revision built on #5940 at frozen SHA f40ae70ac989 with its two-pass critic cycle + verdict OWED. Next session: execute agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-19-lab-day1.md §1 in order. |
| [`WS:STOCK-IDENTITY`](../agentos/workstreams/WS-STOCK-IDENTITY.md) | active | coo-fable | market-timing-intelligence | done:2 in_progress:1 todo:5 | #5583(merged) #5612(merged) #5643(merged) | Land the #5643 heal: W2 expert replay onto merged W1-A1, without duplicating B onto the program OHLCV plane or rewriting sealed GOLD. W3 still needs its own operator go — no auto-roll. |
| [`WS:WATCHLIST-PORTFOLIO-CEO`](../agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md) | active | coo-fable | terminal-user-services | done:2 todo:1 | #5457(merged) #5463(merged) | Obtain the persistence-model ruling, then start W1. |

## Needs a CEO ruling

- **WS:WATCHLIST-PORTFOLIO-CEO** — Portfolio and Watchlist persistence: one table or two? (blocks 1 wave(s) · wanted by 2026-08-14) — `agentos/workstreams/WS-WATCHLIST-PORTFOLIO-CEO.md`

## Warnings

- WS:ADVANCED-DATA-OPTIONS — record_disagrees_with_execution: wave AD-1 is 'awaiting_ci' but PR #5872 is merged
- WS:COMMERCIAL-PATH-ALERTING — record_disagrees_with_execution: wave W1 is 'awaiting_ci' but PR #5734 is merged
- WS:CUSTOMER-DATA-BACKUP — record_disagrees_with_execution: wave W1 is 'awaiting_ci' but PR #5733 is merged
- WS:DEFENSE-PROCUREMENT-V3 — record_disagrees_with_execution: wave D1 is 'in_progress' but PR #5836 is merged
- WS:DEFENSE-PROCUREMENT-V3 — record_disagrees_with_execution: wave D1 is 'in_progress' but PR #5885 is merged
- WS:DEFENSE-PROCUREMENT-V3 — record_disagrees_with_execution: wave D1 is 'in_progress' but PR #5882 is merged
- WS:DEFENSE-PROCUREMENT-V3 — record_disagrees_with_execution: wave D1 is 'in_progress' but PR #5856 is merged
- WS:EVAL-OS-T1-ENGINE-REGISTRY — status is 'active' but every wave is done/dropped — roll the status forward
- WS:FUNDAMENTAL-FORENSICS — record_disagrees_with_execution: wave FF-1 is 'in_progress' but PR #5820 is merged
- WS:GREY-DEER-RISK-INTELLIGENCE — record_disagrees_with_execution: wave GD-1A is 'awaiting_ci' but PR #5961 is merged
- WS:GREY-DEER-RISK-INTELLIGENCE — record_disagrees_with_execution: wave GD-1B is 'awaiting_ci' but PR #5961 is merged
- WS:LIVE-ENTRY-RADAR — record_disagrees_with_execution: wave W6 is 'in_progress' but PR #5834 is merged
- WS:LIVE-ENTRY-RADAR — record_disagrees_with_execution: wave W6 is 'in_progress' but PR #5845 is merged
- WS:STOCK-IDENTITY — record_disagrees_with_execution: wave W2 is 'in_progress' but PR #5643 is merged
- agentos/workstreams/WS-EVAL-OS-T1-ENGINE-REGISTRY.md: [active-but-complete] status is 'active' but every wave is done/dropped
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'engine/risk_envelope.py' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'scripts/build_risk_envelope.py' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'scripts/build_live_risk_envelope.py' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'site/riskdata/risk_envelope.json' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'site/live/risk_envelope.json' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'templates/risk_envelope/' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'tests/test_risk_envelope' does not exist in repo 'macro'
- agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md: [phantom-owns-path] owns_paths entry 'agentos/handoffs/GREY-DEER-' does not exist in repo 'macro'
- agentos/workstreams/WS-LIVE-ENTRY-RADAR.md: [phantom-owns-path] owns_paths entry 'scripts/entry_radar_' does not exist in repo 'macro'
- agentos/workstreams/WS-LIVE-ENTRY-RADAR.md: [phantom-owns-path] owns_paths entry 'research/LIVE_ENTRY_RADAR_' does not exist in repo 'macro'
- agentos/workstreams/WS-LIVE-ENTRY-RADAR.md: [phantom-owns-path] owns_paths entry 'templates/entry_radar.html.j2' does not exist in repo 'macro'
- agentos/workstreams/WS-LIVE-ENTRY-RADAR.md: [phantom-owns-path] owns_paths entry 'site/entry_radar.html' does not exist in repo 'macro'
- agentos/workstreams/WS-LIVE-ENTRY-RADAR.md: [phantom-owns-path] owns_paths entry 'mockups/refs/entry_radar/' does not exist in repo 'macro'
- agentos/workstreams/WS-STOCK-IDENTITY.md: [phantom-owns-path] owns_paths entry 'scripts/stock_identity_' does not exist in repo 'macro'
- agentos/workstreams/WS-STOCK-IDENTITY.md: [phantom-owns-path] owns_paths entry 'research/STOCK_IDENTITY_' does not exist in repo 'macro'
- agentos/decisions/DEC-D0R-RED-TEAM-ADJUDICATION-2026-08-17.md: [review-overdue] review_by 2026-08-18 has passed
