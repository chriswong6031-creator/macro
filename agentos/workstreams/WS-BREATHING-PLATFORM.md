---
key: BREATHING-PLATFORM
title: Breathing Platform — live, continuously refreshed US signal platform
objective: >
  The US product behaves as a live signal platform, not a batch nightly website:
  market state refreshes intraday from the live plane; a same-session provisional
  Prophet board is user-visible within minutes of the close (product SLO 16:15 ET,
  first-usable target ~16:05-16:10); post-close inputs revise it in place; the
  nightly settles the canonical record; no unrelated collector failure can dark
  today's board; stale state never masquerades as current. Done = replay + chaos
  acceptance passed AND three consecutive real sessions measured green on the
  close→candidate→visible ruler.
status: active
program: prophet-us
p0: PROPHET_FRESHNESS
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: specified
next_action: >
  Recover and grade the 2026-08-26 close-pass ruler from the immutable host +
  reader receipts; absence is NOT a pass. Then hold consecutive genuine NYSE
  sessions until three real close_observed_at → first_candidate_at →
  first_user_visible_at rows are green. Do not modify Breathing code unless a
  new ruler row identifies a Breathing-owned causal failure. D12 armed-pack
  source-tip correctness stays with PROPHET-US-AVAILABILITY; Live Entry Radar
  keeps tactical alert ownership.
owns_paths:
  - scripts/close_pass_publish.py
  - scripts/close_pass_mirror.py
  - scripts/close_pass_host_runner.py
  - scripts/close_pass_slo_report.py
  - scripts/measure_massive_close_parity.py
  - scripts/install_closepass_launchd.sh
  - ops/launchd/com.macro.closepass.plist
  - engine/close_pass/
  - .github/workflows/close-pass.yml
  - tests/test_close_pass_lane.py
  - tests/test_close_pass_massive_close.py
  - tests/test_close_pass_host_runner.py
waves:
  - id: W-L0
    title: Truth fixes (append semantics, fade hysteresis, price basis, sentinel surface, dormant honesty)
    status: done
    next_action: "Shipped 2026-08-08..09 (#4978 #4982 #5088 #5089, sentinel b278a3f9b)."
  - id: W-L1
    title: Evening SLA — close-pass provisional board, cards, receipt, reader-measured sentinel
    status: done
    next_action: >
      Shipped #5148 #5154 #5217 #5220 #5222 #5223; lane first green 2026-08-13 after
      #5495. Historical pre-revival green rows do not satisfy the commissioned
      post-2026-08-17 three-session acceptance ruler.
  - id: W-L1R
    title: Revival wave — coverage + latency + ruler (Chairman directive 2026-08-15)
    status: done
    next_action: >
      ALL MERGED + DEPLOYED 2026-08-16: #5746 (coverage 253→1,684 measured),
      #5760 (com.macro.closepass installed, kickstart rc=0 with receipt),
      #5761 (armed-pack watchdog live-verified on production staleness.json).
      Replay acceptance is complete; production acceptance remains W-ACCEPT.
  - id: W-L2
    title: Arming breadth + alert outcome reconciliation
    status: todo
    depends_on: [W-L1R]
    next_action: >
      RE-CUT BEFORE BUILD. The 2026-08-15 instruction to simply
      raise/parallelize the nightly arming budget is stale: the current builder
      already uses process fan-out and explicitly treats the wall-clock budget as
      safety law; Prophet Live liveness/dead-man alerting is now PROVEN_LIVE; and
      tactical entry alerting belongs LIVE-ENTRY-RADAR. The remaining Breathing
      question is narrower: measure current valid armed-level breadth after D12
      source-tip correctness, identify whether missing breadth actually prevents
      same-session user/machine value, and commission only that causal residual.
      Do not pursue literal 100% threshold probing by timeout/resource inflation.
  - id: W-ACCEPT
    title: Live-session acceptance — three consecutive green sessions on the ruler
    status: in_progress
    depends_on: [W-L1R]
    next_action: >
      Proven consecutive green count is ZERO as of the 2026-08-27 forensic
      reconciliation. 2026-08-17 failed in the host lane; 2026-08-18..25 cannot
      pass first_user_visible_at because the required Prophet-Live carrier was
      not publishing/served; 2026-08-26 Prophet Live was restored before RTH but
      no durable close→candidate→reader ruler row was found in current GitHub /
      Agent OS / Slack evidence. Recover that exact row if it exists; never infer
      it from the earlier intraday Prophet-Live proof.
landmines:
  - "The board universe store lacks most today-bars at close time — the keyless Yahoo heal refreshes the INDEX group only; without the Massive fill the evening board is a ~14% sample (measured 2026-08-14: 253/1,763 evaluated, 1,508 no_todays_bar)."
  - "The last durable post-#5746 same-session coverage proof is replay, not a current production census: 1,684/1,763 evaluated (95.5%) on 2026-08-14. Never relabel that as 2026-08-26/27 live coverage."
  - "The client paints board_state ONLY off the real evaluator document — a bare {board_state: ...} artifact is refused upstream of the qualify chain. Any replay/rescue writer must annotate the evaluator doc the way close_pass_mirror does, never mint a shell."
  - "Board freshness and Prophet-Live carrier freshness are separate clocks: a fresh close-pass board_state may be CAS-annotated into any parseable existing Prophet-Live document. That does not make stale close data current, but browser acceptance must prove the independent Prophet strip is visibly/dead-man degraded rather than silently reading fresh."
  - "2026-08-17..25 US Prophet Live publication failure is an acceptance dependency, not permission to create a third writer: the served evaluator document did not exist until the 2026-08-26 restoration, and close_pass_mirror correctly refuses to create it."
  - "D12 armed-pack as_of/source-tip correctness is an unresolved PROPHET-US-AVAILABILITY owner defect. Do not repair it in Breathing by changing Prophet ranking/gating or by manufacturing a fresher tip."
  - "The vendor ticker space is case-sensitive (TPC≠TpC, BCPC≠BCpC) — upper-casing before a join is last-row-wins across two different securities (DSC:MASSIVE-TICKER-CASE-IS-IDENTITY); massive_close matches case-exact, the corp-action guard darks both spellings by design."
  - "GitHub cron is not a product clock: close-pass cron drift measured 27-45 min, queue waits to 95 min, board landed 19:20 ET (2026-08-14); estate-wide 90min-3h12m gaps (DEC:LER-LIVE-LANE-VPS-5MIN-REST)."
  - "Two writers share live/prophet_live.json via CAS (mirror annotates board_state into the evaluator's artifact) — every failure direction must stay dark, never wrong; do not add a third writer."
  - "Never splice a raw same-day close onto a store series that had a same-session split/dividend — dark the name (skipped.corp_action_today); the nightly settles it. BYND 30:1 on 2026-08-14 is the live exemplar."
  - "The provisional board carries 40/100 score weight (signal+runway) BY RULING — never renormalise, never impute the omitted legs (board.py header)."
  - "close_pass_publish session guard uses is_session(), NOT expected_last_session() (fires before the 17:00 ET settle buffer)."
do_not_redo:
  - "Do not move the board onto closing-bell.yml's render spine — measured 109 min behind an 81-min spine; close-pass.yml's header carries the full reasoning."
  - "Do not resurrect the workflow_run reconcile job — the receipt is computed inside the nightly build that renders it (close-pass.yml header, 'no receipt is better than a wrong one')."
  - "Do not open a Massive WebSocket for this lane — single-slot evict-oldest hazard; TP-1 owns any future socket (DEC:LER-LIVE-LANE-VPS-5MIN-REST, Massive masterplan §3.1b)."
  - "Do not build a VPS-side board compute tier — the canonical store + canonical gate live on the Mac; the VPS is transport/serving (DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK)."
  - "Do not weaken the client identity guard (_bsQualify) to make anything paint — fix payloads, not the guard."
  - "Do not reconstruct a missing first_user_visible_at from candidate/R2 timestamps; the ruler is intentionally reader-measured and missing sessions remain failures."
---

## State — 2026-08-27 forensic acceptance reconciliation

Procedural pin: protected Sol Skillpack
`mastermindx-market-intelligence/Mastermind@cef4332d3682991e3e1c3d6160da17cd0a3a8f63`
(`mastermind.sol_skillpack.v1`, 1.0.0, bootstrap major 1 compatible). Reconciliation
base: Macro `92555b55f1c6194c8d325eff0c6066a12b4f940e`.

### Retrospective ruler ledger

| Session | Acceptance | Causal evidence |
|---|---|---|
| 2026-08-17 | FAIL | Host lane timed out preparing the lane and refused stale/unknown code (`lane_unprepared`); no board. #5862/#5866 preserve the causal repair/receipt law. Prophet Live was also D-class stale-pack/dark. |
| 2026-08-18 | FAIL | Prophet Live D-class stale-pack and no published/served evaluator document; required reader carrier unavailable. |
| 2026-08-19 | FAIL | Prophet Live D-class stale-pack and no published/served evaluator document; required reader carrier unavailable. |
| 2026-08-20 | FAIL | Valid R-class live evaluation existed, but publication was lost; served evaluator document still absent, so reader visibility cannot pass. |
| 2026-08-21 | FAIL | Valid R-class live evaluation existed, but publication was lost; served evaluator document still absent. |
| 2026-08-24 | FAIL | Prophet Live D-class stale-pack plus no publication/served evaluator document. |
| 2026-08-25 | FAIL | Valid R-class live evaluation existed, but publication was lost; served evaluator document still absent. |
| 2026-08-26 | UNVERIFIED / NOT ACCEPTED | #6483 proves Prophet Live publishing and dead-man health during RTH, before the close. It does NOT contain the evening close_observed_at→candidate→reader row. No durable ruler row was found in current GitHub/Agent OS/Slack evidence. |

Verdict: the three-session ruler has **not passed**. Proven consecutive green
count is **0**. 2026-08-27 has not yet opened as a market session at this
reconciliation time and is not a ledger row.

### Coverage truth

The last durable exact close-pass breadth proof is the post-#5746 replay:
`1,684 / 1,763 = 95.5%` same-session evaluable coverage on 2026-08-14, with 58
same-session corporate-action names darked and 19 barless. No current real
2026-08-26 session denominator/coverage receipt is durable in the evidence read by
this reconciliation. Prophet Live `/api/status n_names=180` is an evaluator output,
not a universe coverage denominator, and must not be relabelled as coverage.

### W-L2 ruling

The original W-L2 is **partially superseded and must be re-cut before any build**:
process parallelization already exists in `build_prophet_live_pack.py`; liveness /
publication alerts are now owned and PROVEN_LIVE by the Prophet-Live availability
plane (#6464/#6470/#6482/#6483); tactical alerting belongs Live Entry Radar. A
real residual remains only if current valid armed-level breadth, after the D12
source-tip defect is corrected by its owner, prevents the Breathing user/machine
experience. Literal full-universe probing is not an authorization to inflate
timeouts/resources or weaken edge verification.

### Collision fence

- `WS:PROPHET-US-AVAILABILITY` owns Prophet-Live publication, dead-man/availability,
  and the unresolved D12 armed-pack source-tip correctness defect.
- `WS:PROPHET-US-V4-RECOVERY` owns V4 product/research architecture and deterministic
  Availability integration; Breathing does not create another ranker/store/publisher.
- `WS:PROPHET-US-ENTRY-TIMING` owns held-out entry-timing research; Breathing does not
  retune Prophet selection/gating or entry semantics.
- `WS:LIVE-ENTRY-RADAR` owns the separate 5-minute tactical entry detector/evidence/
  alert product; Breathing does not duplicate it under W-L2.
- `WS:MASSIVE-STOCK-DAY-R2-COHERENCE` owns stock-day collector/R2 atomicity. Breathing
  may continue its existing same-session Massive close read/fill, but must not fix
  that workstream by editing its collector/publisher plane.

### Commission state

No new Fable implementation commission was issued by this reconciliation. The
observed unresolved code defect (D12) is already owned outside Breathing, and no
new Breathing-owned causal code failure is established after the 2026-08-26
Prophet-Live restoration. Current Slack transport law also freezes new
DELIVERY_ONLY Fable pickup posts without a known active receiver; delivery is not
ACK. Do not manufacture an ACK. The next Breathing action is forensic/production
acceptance, not speculative code.
