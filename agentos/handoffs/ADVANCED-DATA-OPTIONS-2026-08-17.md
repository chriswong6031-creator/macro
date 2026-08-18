---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad0-options-recovery-archaeology
model: fable
ended_because: complete
mission: >
  AD-0 recovery archaeology: reconstruct current-main + production truth for the options
  EOD / off-exchange estate, adjudicate maturity and salvage, freeze the AD-1 slice, and
  open one docs-only PR. No runtime changes.
state_before: >
  No workstream record existed for the options program. Prior state was fragmented across
  ~30 research docs, the Options Confluence program of record (2026-07-16), the sparse-
  selector PR chain (#5747 et al.), and an accompanying machine-generated evidence bundle
  that had audited an EMPTY head (0 artifacts) and carried no usable evidence.
changed:
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
    what: NEW — full AD-0 ledger (maturity, production audit, UX audit, semantics, source/rights, salvage, no-rebuild, 25 answers).
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
    what: NEW — implementation-ready AD-1 handoff (outcome, exact allowed/forbidden files, source clocks, output contract, tests, production proof).
  - path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md
    what: NEW — workstream record (AD-0 awaiting review; AD-1 gated on review).
  - path: agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-17.md
    what: NEW — this handoff (updated in place by the same-day Sol-review amendment pass).
  - path: research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md
    what: NEW (amendment pass) — governing masterplan committed in-repo per Sol review amendment 1; AD-0…AD-15 architecture is now durable repo state.
  - path: agentos/decisions/DEC-AD-SIGNAL-VOCAB-RESTORES-SHORT.md
    what: NEW (amendment pass) — SHORT restored to the Advanced Data signal vocabulary; D-law replaces the vocabulary ban (Sol review amendment 2).
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
    what: AMENDED — direction enum includes SHORT under the D-law; new §5.3 freezes the complete deterministic display-tier scoring/ranking method (intel_brief_heuristic/v1) so the builder has zero product-design decisions; test 14 pins the frozen constants (Sol review amendments 2+3).
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
    what: AMENDED — masterplan cited at its in-repo path; RETIRE row carries the evidence-preservation law (runtime-only retirement); intraday fleet explicitly DISARMED BY DEFAULT pending AD-9.
  - path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md
    what: AMENDED — operator-held-masterplan landmine removed; fleet-disarmed + evidence-preservation landmines added; DEC linked; masterplan added to artifacts.
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
    what: AMENDED (data-feasibility pass, Sol delta review) — §5.3 refrozen as intel_brief_heuristic/v1.1 (H≥10 floor, min(W,H) windows, cross-sectional tier-peer + bounded longitudinal blend, contract-matched robust-z ΔOI, cross-sectional E family with self-activating historical upgrade, non-vacuity gate ≥60%, INSUFFICIENT_HISTORY distinct from NO_SIGNAL, research-hypothesis language law); §5.4 adds the real-data census, the read-only preflight report (95.7% eligible; LONG 69 / SHORT 46 / VOLATILITY 99 / RISK_ONLY 22 / NO_SIGNAL 120; 88 cards ≥ R_MIN), and the binding data-feasibility law; tests 15–16 added.
  - path: research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md
    what: >-
      AMENDED — §8.2 amendment block authorizes deterministic heuristic ranking as
      display-tier research-priority authority only (never probability/alpha/forecast/
      Prophet/gating/sizing/trade authority; AD-6/AD-7 own promotion) and binds the
      data-feasibility law. AD-1P0 (2026-08-18) adds the semantic-authority amendment
      (six evidence classes stay separate; the authority ladder binds; GEX/salience
      never originate direction; Prophet has zero AD-1 rank authority).
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
    what: "AMENDED (AD-1P0 semantic-authority freeze, Sol ruling 2026-08-18) — §5.3 refrozen as intel_brief_heuristic/v1.2: D_salience unsigned (0.65 d1 + 0.35 d3); direction requires Q_oi and Q_skew (skew-CHANGE robust z, floor 8) both at |0.50|+ same-sign plus D_salience >= 0.60; Q_flow structurally ABSENT while signing_gate direction_reliable=false; gex_confirm demoted to mechanics context (only effect M_gex=0.75 on qualified LONG under caution); evidence_strength/research_priority_score replace asymmetry (asymmetry_score null/UNCALIBRATED, probabilities/expected-edge null until AD-6); evidence-confidence ceiling 0.45 for directional cards; horizon/fresh_until (NYSE sessions)/trigger/invalidation/market-implied-move contracts frozen; event board history_mode contract (cross_sectional now, historical_conditioned at >=3 same-name events); Prophet display-only with zero rank authority (v1.1 prophet multiplier REMOVED); adversarial controls added as tests 17-22; runtime production proof amended with the 10 AD-1P0 items; primary references appended. v1.2 preflight recorded in §5.4."
  - path: agentos/decisions/DEC-AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION.md
    what: NEW (AD-1P0) — the semantic-authority ruling record (decided_by ceo-sol).
verified:
  - claim: main_at_start is 7a6a6656e289 and production checkout matches it
    command: "git log -1 origin/main; curl -s https://www.mastermind-x.com/api/health"
    result: checkout 7a6a6656e28 == origin/main tip; app-binary commit 16874921e63 (older; semantics inferred)
  - claim: EOD options source is Polygon snapshot in daily.yml, session-stamped
    command: "grep -n POLYGON_API_KEY .github/workflows/daily.yml collectors/polygon_options.py; sed -n 38,50p scripts/build_polygon_gex.py; grep -n accrue_polygon_gex scripts/collect.py"
    result: daily.yml:323 env; collect.py:841 invocation; _resolve_session stamps the described session
  - claim: no options launchd unit is loaded on the Mac Studio
    command: "launchctl list | grep -iE 'macro|mastermind'; launchctl print gui/501/<unit>; launchctl print system/<unit>; ls ~/Library/LaunchAgents"
    result: zero options units loaded; only optionsnbbocohort installed-not-loaded; liveflow present only as .bak; sparse-selector receipt roots absent under ~/.mastermind_private
  - claim: exactly one options-derived sign is in live Prophet rank
    command: "sed -n 200,278p engine/us_prophet_fusion.py; sed -n 1105,1200p engine/us_board_rank.py"
    result: gex_confirm_verdict in REGISTERED_SIGNS (F5_FLOW_POSITIONING); C1 fusion is canonical US rank authority (Chairman override 2026-08-15)
  - claim: production surfaces and sessions as recorded in the ledger §1
    command: "curl -sI/-s on options.html, darkpool.html, advanced.html, data JSONs; git show origin/main:site/{darkpool_eod,flow_desk,options_dislocation}.json; gh run list --workflow daily.yml/--workflow closing-bell.yml --limit 5"
    result: options LM 08-15 00:45Z (session 08-13 settled, positions 08-14); darkpool asof 08-13; JSON data planes 401 auth-gated; committed==served where comparable
  - claim: sparse-selector PR chain reconciled
    command: "gh pr view 5747|5694|5696|5708|5711|5790|5801 --json state,mergedAt,mergeCommit,files"
    result: six merged with SHAs recorded in ledger §2.3; #5711 closed unmerged duplicate of #5708; W1A modules imported only by their tests
  - claim: v1's 60/252-session prerequisites are impossible on the canonical estate; v1.1 is non-vacuous on it
    command: "read-only pandas census + preflight over data/polygon_gex/chains (28 sessions, 4.42M rows), summaries, site/gex, data/earnings at the amendment head (script methodology recorded in AD-1 handoff §5.4)"
    result: depth median 26 sessions (370/408 names >= 10); latest session 372 names, 356 eligible (95.7%) under v1.1; family availability V353/D356/P345/E56; states LONG 69 / SHORT 46 / VOL 99 / RISK 22 / NO_SIGNAL 120; 88 cards >= R_MIN; non-vacuity gate PASS
  - claim: the v1.2 semantic-authority method remains non-vacuous on real data and the directional collapse is the intended correction
    command: "read-only v1.2 preflight at audit head 6482f876ba7f, session 2026-08-13 (methodology = AD-1 handoff §5.3 v1.2; report in §5.4)"
    result: eligible 356/372 (95.7%); Q funnel 351 both-present -> 19 strong -> 10 same-sign -> 10 qualified; LONG 3 / SHORT 7 / VOLATILITY 152 / RISK_ONLY 29 / NO_SIGNAL 165; 64 cards >= R_MIN; Prophet census among ranked UNAVAILABLE 52 / OTHER 8 / NOT_READY 2 / ALREADY_OPEN 1 / READY 1; v1.1->v1.2 LONG 69->3, SHORT 46->7 with no threshold tuning
  - claim: the flow signing gate currently denies direction authority
    command: "cat data/options_flow/signing_gate.json"
    result: direction_reliable=false, magnitude_reliable=true, net_sign_recovery=0.4108 (asof 2026-06-21)
unverified:
  - claim: /api/health "commit" field means last app-binary restart build
    what_would_verify: a deploy-truth doc or reading app/deploy/update.sh restart semantics
  - claim: closing-bell.yml did or did not run after Friday 17:25 ET on 2026-08-14
    what_would_verify: one wider bounded `gh run list --workflow closing-bell.yml --limit 20 --created 2026-08-14..2026-08-16`
  - claim: redistribution/derived-display rights for Polygon/massive-derived surfaces
    what_would_verify: operator/vendor license confirmation (not in-repo)
unresolved:
  - Q3/D4 pair — options.prophet_shadow publishes nightly to R2 with zero consumers (its only coded consumer, the issue desk, is unscheduled); AD-5 must consume or retire it (masterplan §16.7).
  - UNKNOWN_PENDING_PROOF — whether the host intraday fleet ever returns under Macro, given Terminal owns intraday options-flow authority; Chairman ruling needed (framed for AD-9).
  - Library-imported dark builders (ledger §2.3 D6): function-level liveness inside live callers not adjudicated; check importer call graphs before any retirement action.
next_actions:
  - Chairman reviews the AD-0 PR (ledger + AD-1 handoff).
  - On approval, commission AD-1 exactly per research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md — one slice, stop after its production acceptance packet.
  - Ratify or amend the salvage matrix RETIRE row (ledger §8) — recommendations only until ratified.
do_not_redo:
  - The four census lanes of AD-0 (EOD product path, sparse-selector PR chain, consumer planes, production probes) — results are in the ledger with commands; re-running them re-discovers the same estate.
  - Any continuation of PR #5747 or re-arming of the sparse-selector canary — no consumer, proposal authority code-closed, activation window expiring 2026-08-21.
  - A second program registry or a Macro-side copy of strategic state — the registry row is config/mastermind_programs.yml `options-intelligence`; this WS record is the program state.
danger_areas:
  - DNR:KILL-POSITIONING-FUSION Amendment 1 scope — options positioning keys may earn authority ONLY inside the Prophet-US conditional-fusion arena.
  - Front-facing language law (operator 2026-07-27) — no falsifier/refuted vocabulary on any AD surface; invalidation renders as watch conditions.
  - Direction law — SHORT is in the Advanced Data vocabulary (DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT) but gated by the AD-1 §5.3 D-law; no insufficiently directional observation originates LONG or SHORT alone; zero SHORT emissions is a lawful output. Legacy confluence surfaces keep law 17 until their own docs are amended.
  - Sparse worktrees — AD-1 touches templates/site: opt in with `python3 scripts/worktree_sparse.py full` before render work.
---

## Summary

AD-0 is complete as commissioned: a ruthless maturity ledger over the whole options/
off-exchange estate (9 PROVEN_LIVE chains, 4 PARTIAL, a 15-unit dark host fleet, the
sparse-selector path fully reconciled and inert, Sector at zero, one lawful live Prophet
channel), a production audit anchored to /api/health and served-page evidence, a data-
semantics adjudication of every inference the estate currently makes, a salvage/retire
matrix, a no-rebuild plane map, and a frozen, implementation-ready AD-1 slice. The next
builder does not need to rediscover the project: read the two research artifacts in
`changed`, then the AD-1 handoff §0 gates. The AD-0 documentation PR opened from this
session carries the final verdict block in its body; its number is recorded in the
workstream wave entry once assigned.
