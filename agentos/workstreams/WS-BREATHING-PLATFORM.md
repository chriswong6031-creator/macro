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
  Land the revival wave (PR-A Massive close truth, PR-B launchd primary clock,
  PR-C liveness ruler), deploy the launchd agent on the Mac Studio, run replay
  acceptance, then hold for Monday's live session measurement.
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
      #5495. The 5-consecutive-green-session SLA clock ACCRUES from 2026-08-13.
  - id: W-L1R
    title: Revival wave — coverage + latency + ruler (Chairman directive 2026-08-15)
    status: done
    next_action: >
      ALL MERGED + DEPLOYED 2026-08-16: #5746 (coverage 253→1,684 measured),
      #5760 (com.macro.closepass installed, kickstart rc=0 with receipt),
      #5761 (armed-pack watchdog live-verified on production staleness.json).
      Replay acceptance done on receipts. Program completion now rides
      W-ACCEPT alone.
  - id: W-L2
    title: Breathing board — full-universe arming coverage + alerts
    status: todo
    depends_on: [W-L1R]
    next_action: >
      Raise/parallelize the nightly arming budget: measured 2026-08-15, the armed pack
      covers 91 of 1,761 names with levels (probe_cap_cross cut 1,535). Masterplan
      W-L2 gates apply (precision floor before send-enable, 2-tick debounce).
  - id: W-ACCEPT
    title: Live-session acceptance — three consecutive green sessions on the ruler
    status: todo
    depends_on: [W-L1R]
    next_action: >
      Monday 2026-08-17 first live measurement: close_observed_at → first_candidate_at
      → first_user_visible_at via scripts/close_pass_slo_report.py; repeat 3 sessions.
landmines:
  - "The board universe store lacks most today-bars at close time — the keyless Yahoo heal refreshes the INDEX group only; without the Massive fill the evening board is a ~14% sample (measured 2026-08-14: 253/1,763 evaluated, 1,508 no_todays_bar)."
  - "The client paints board_state ONLY off the real evaluator document — a bare {board_state: ...} artifact is refused upstream of the qualify chain. Any replay/rescue writer must annotate the evaluator doc the way close_pass_mirror does, never mint a shell."
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
---

## State (2026-08-15, revival session)

The W-L1 machinery is real and merged end-to-end: publisher → R2 → VPS mirror
(5-min systemd) → `board_state` CAS-annotated onto `live/prophet_live.json` →
identity-guarded client card renderer → reader-measured 18:30 SLA in the
freshness sentinel. The lane went green for the first time 2026-08-13 (#5495)
and published Friday's board.

What the revival fixes is the two measured product defects: coverage (the store
has today's bar for ~14% of the universe at pass time) and clock (GitHub cron +
contended macstudio pool ⇒ ~19:20 ET delivery). Architecture ruling:
DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK. Close-semantics evidence:
DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE.

Real-session acceptance CANNOT begin before Monday 2026-08-17 (commissioned on a
Saturday); replay/chaos acceptance is this session's exit bar.
