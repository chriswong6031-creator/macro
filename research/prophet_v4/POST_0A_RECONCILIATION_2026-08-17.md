# PROPHET US V4 — POST-0A RECONCILIATION (V4-0B)

**Wave class:** records/architecture reconciliation only. Runtime authority: NONE. This document is the evidence ledger behind the 0B record edits; `CURRENT_STATE_2026-08-17.md` remains the untouched 0A snapshot at its own pin (historical-snapshot law — later facts live here, never repainted there).

## 1. Identity

| Clock | Value |
|---|---|
| 0A execution pin | `fc0557bb0873` (2026-08-17T06:04:45-05:00) |
| 0A merge | PR #5832 → squash `ebce73b97288ec687759178d3af24ed63eb9efbf`, merged 2026-08-17T13:18:55Z (verified ancestor of main same session) |
| 0B fresh-start pin | `1c00a59f92a5` (fetched 2026-08-18T00:09:46Z; tip is an automated render-sync commit — repo moves through bot commits) |
| 0B head/end SHA | <!-- FILL:at-PR-open --> |

## 2. Post-0A delta ledger

All merges ancestry-confirmed at the 0B pin (`git merge-base --is-ancestor <sha> HEAD` → ancestor, per the 0B census receipts).

| Delta | Owner | Capability gained | What did NOT ship | V4 consequence |
|---|---|---|---|---|
| **#5832** merged 13:18:55Z → `ebce73b97288` | V4 (this program) | the 0A freeze packet (docs/records/test-fixture only) | zero runtime implementation | wave `0a` = done |
| **#5842** merged 16:15:02Z → `ea7e63ccb0c9` | EIOS | **E1P**: `event_workspace.v1` golden-event publication LIVE for AAPL FY2026 Q3 (public marker 200, generation `f709a0a6ec514282d5769e7d`); E2 unblocked | broad issuer coverage — ONE golden production event exists | D6's "EIOS is only E0" premise retired; D6 still waits on D5 and must not infer coverage from one event |
| **#5839** merged 18:41:06Z → `65af95d360fc` | Conditional Fusion | **PR-3C**: durable prospective W3 paired/family/coverage ledger via the shared grader; pending H=10 stays pending (never zero); zero rank/gate/featured/plan authority | PR-3D; any comparative C1-vs-shadow read | E1's upstream boundary = PR-3D acceptance; 0A-era "PR-3B next" references superseded (3B and 3C are both merged) |
| **#5840** merged 19:56:57Z → `2cd0534421c4`; render receipt `5232c4c4159e` (21:23:33Z) | platform/product (sibling session) | ranked-board server-side paid split: free shell + premium remainder on the premiumdata plane, both stocks-mode render sites, honest full counts. **PROVEN_LIVE** at the 0B pin: VPS `premiumdata/us_stocks.json` → 401 anonymous; anonymous `us_stocks.html` carries 3 ticker rows vs disclosed larger counts; both served copies postdate the render receipt (Pages LM 22:51:26Z, VPS LM 00:06:19Z). Pages' static 200 on the premium file is expected (no auth layer) — the load-bearing gate is the VPS | per #5840's own scope: **Act-Now, `.topsetups`, `ran`, theme-tape member names remain DOM-gated** | 0A's blanket "full board ships anonymously" landmine is superseded by a SCOPED one; residual surfaces stay commercial-boundary debt (E2 acceptance at the latest). V4 makes no claim on the operator's chip status — the residual DOM-gated surfaces remain open work |
| **#5834** merged 20:56:50Z → `39985e144036` | Live Entry Radar | **W6 code**: `mastermind.research_priority.v1` — deterministic, decomposable, ACCRUING research-attention ordering on the live-evaluator projection | per its own PR: not Prophet, not W7, not production UI; **live-payload commissioning still owed before W6 is done** | V4 consumes Research Priority later rather than inventing a competing early-priority field; B7/W-graph references updated; zero Prophet rank authority |
| **#5737** still OPEN | Live Entry Radar | — (W8 reference UX/RIG only; explicitly does not create production templates and says not to start W9) | production `entry_radar.html` | W8 remains SPEC_ONLY; W9/B7 unchanged |
| **#5843** still OPEN | CI control plane | — (proposed: retry transient GitHub API failures in `ci-authority` instead of failing closed; bounded, GET-only, still fail-closed) | — | not V4's lane; do not help/widen/weaken; if CI blocks the 0B PR, wait or return blocked with run IDs |
| **#5742** OPEN, 2 comments, newest 23:56:23Z (operator) | Availability/outage sessions + operator | triage advanced far beyond 0A: push-freeze ruleset `ci-recovery-bootstrap-freeze-2026-08-15` GH013 rejections; `collect_tail` pinned to unregistered `theta-m1` label holding the concurrency group; rescue correctly refused while a run looked alive; `macstudio` runner saturation. Operator restored runner labels; at 23:56Z **two candidate bakes overlap** (run 31977372592 in_progress on mac-builder-3; scheduled 32077948964 imminent; dispatch 32081969617 mid-bake on mac-builder-4) with duplicate-bake/forward-ledger-append risk named until session dedup exists | the outage is NOT resolved: served board still `source_asof=2026-08-13`, 206 plans, LM Aug-14 (recurled at the 0B pin) | **V4 must not spawn A1** — implementation is sibling-owned; A1 = acceptance contract; nothing here is frozen as a timeless root cause |
| GMI ThemeState search | GMI | none found: no `data/theme_graph/state/`, no GMI-lineage `theme_state` module (`thematic_state.py` is the older, different lineage), no W3B PR in search | ThemeState v1 | D3 gate unchanged: GMI owns; merge-order ruling mandatory before any ThemeState work |

## 3. Active-owner table

| Lane | Owner at 0B | State |
|---|---|---|
| Outage/availability implementation | active sibling session(s) + operator (receipts in #5742) | recovery bakes in flight; durable-fix charter (runner-presence gating, ET-session dedup, rescue zombie policy, label-pin tests, docs) claimed by a sibling per the issue |
| CI control plane | #5843 owner session | PR open |
| Radar | `WS:LIVE-ENTRY-RADAR` | W6 merged (commissioning owed); W8 #5737 open reference-only; its WS record does not yet note #5834's merge — **discrepancy routed to owner** (that record is being edited in #5737's own diff), not edited by 0B |
| Fusion | `WS:PROPHET-CONDITIONAL-FUSION` | PR-3C merged; PR-3D next |
| Earnings | `WS:EARNINGS-INTELLIGENCE-OS` | E1P live (golden event); E2 unblocked |
| GMI | `WS:GMI-THEME-GRAPH` | W3A done; no ThemeState |

## 4. A-lane adoption matrix

States restricted to: `UNKNOWN_PENDING_RETURN` · `CANDIDATE_ADOPTION` · `ACCEPTED_BY_SOL` · `NOT_EQUIVALENT`. Only Sol/Chairman promotes to `ACCEPTED_BY_SOL`.

| V4 gate | Sibling work | State |
|---|---|---|
| A1 (owed-session settlement recovery) | in-flight recovery bakes + operator runner restores (#5742) | `UNKNOWN_PENDING_RETURN` — no sibling return yet; board still stale at the pin; Sol reviews the return against `V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md` |
| A2 (settlement manifest) | sibling durable-fix charter (#5742: runner-presence gating, dedup, zombie policy) may cover parts | `UNKNOWN_PENDING_RETURN` — map on return; only the unresolved delta may become a V4 wave |
| A3 (atomic publication/split-brain fence) | same sibling charter; #5840 also touched the publication plane's premium split | `UNKNOWN_PENDING_RETURN` — same adopt-first rule |

**Superseded instructions register:** `agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-17.md` `next_actions` item "Spawn V4-A1 per research/prophet_v4/V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md" is SUPERSEDED by wave-graph §4.11 (the 0A handoff itself is a historical record and stays unedited; the handoff protocol's latest-record-wins rule is made explicit here). The A1 document itself now carries a DO-NOT-LAUNCH banner and is retitled an acceptance contract.

**Dating note:** the two 0B files carry the program-day `2026-08-17` in their names for continuity with the 0A packet; every receipt and the execution pin are stamped `2026-08-18T00Z` — the clocks in §1 are authoritative, not the filenames.

## 5. Residual defects (unchanged by any post-0A merge)

Four-way lifecycle split (CURRENT_STATE §8) · late-entry/buyability authority (B3/B4 territory) · TURN WATCH orphan surface · Radar W4 full-RTH activation proof · Radar W6 live-payload commissioning · Radar production UI (W9) · Fusion PR-3D acceptance · GMI ThemeState (not built; merge-order ruling mandatory) · broad earnings issuer coverage (one golden event ≠ coverage) · residual DOM-gated paid surfaces excluded by #5840's split · the active availability incident itself (#5742, sibling-owned).
