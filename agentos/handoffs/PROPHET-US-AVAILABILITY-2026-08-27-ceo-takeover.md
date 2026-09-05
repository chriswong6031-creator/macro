---
workstream: WS:PROPHET-US-AVAILABILITY
session: claude/prophet-us-ceo-takeover-20260827
model: fable
ended_because: complete
mission: >
  Chairman full-authority mandate 2026-08-27 after a month of force-majeure
  reports: restore both Prophet US mechanisms, root-cause every staleness
  sighting, backfill honestly, and make silent freezes structurally impossible.
state_before: >
  Live lane restored the previous morning (#6464/#6470) but unproven in a real
  session; Chairman reporting "no Aug 24/25/26 updates" off a board whose ZONE
  chips read Aug 21; rescue issue #6495 open on a STRAND (no nightly for session
  2026-08-26 until 03:29Z); prophet-outage issues from 08-14/18/20/21 still open;
  no instrument grading board semantics; watchdog pages routed to a dedup-gated
  webhook nobody read.
changed:
  - path: research/PROPHET_US_AVAILABILITY_LEDGER_2026-08.md
    what: >
      The definitive 18-session August availability record: 14/18 fresh at
      standard time; Aug 6/12/17 stale-at-open; one true mint hole
      (asof-08-11); live lane 1/18 with 7 sessions of journal-recovered events.
  - path: agentos/decisions/DEC-PROPHET-US-BACKFILL-IS-TWO-TIER.md
    what: >
      The backfill honesty ruling under Chairman authority: published-only
      grading, journal-verbatim recovery legitimate (#6484 ratified), labeled
      reconstruction never graded; live lane accrues from 2026-08-26.
  - path: agentos/workstreams/WS-PROPHET-US-AVAILABILITY.md
    what: next_action re-pinned to this wave's verification steps.
verified:
  - claim: "The live lane ran the full 2026-08-26 session in production."
    command: "ssh root@146.190.142.17 journalctl -u macro-live-prophet.service --since '2026-08-26 13:20' --until '2026-08-26 20:30' | grep 'published live_flow/prophet_live.json' + authenticated R2 GET"
    result: "84 publishes, first 13:28:09Z last 20:23:08Z; pass_ts=2026-08-26T20:23:01Z; session_et=2026-08-26; 180 states; R2==served True."
  - claim: "No cohort freeze existed for sessions 2026-08-24/25 — the commissioned symptom was a misread."
    command: "git show origin/main:data/prophet/origination_receipts/{32786919396,32908543584}-1-*.json + recorded_at histogram of site/prophet/index.json"
    result: "originated_count 11 and 9; histogram 08-21:27, 08-24:11, 08-25:9; intake lossless with unaccounted=0. The rescue's cohort-0 line in #6495 was session 2026-08-26 pre-run (STRAND), not Aug-24/25."
  - claim: "The Chairman's 'Aug 21' sighting was signal.asof — a 3-session bucket OPEN-date label, board-wide constant — over a fresh board."
    command: "pv_card 'date' arg trace (templates/_us_board_cards.html.j2) + signal.asof histograms across five committed us_standouts vintages + buy_zone join Aug-24 vs Aug-25"
    result: "asof steps 08-18→08-21 and holds across 24/25 (133/133 rows identical); buy_zone MOVED for 101/115 common tickers night-over-night while the date held."
  - claim: "PR #6484's event recovery is grounded in real contemporaneous output."
    command: "ssh journalctl --since '2026-08-25 13:00' | grep -o 'events=[0-9]*' | sort | uniq -c; git ls-tree origin/main data/prophet_live/ data/pit_replay/prophet_live_recovery/"
    result: "84 per-pass events= declarations on 08-25; journal archive + sha256 receipt committed; data/prophet_live/forward.parquet exists on main."
  - claim: "The dead-man stayed green through the era because semantics were invisible to it."
    command: "gh run list --workflow nightly-liveness.yml --created 2026-08-22..2026-08-27"
    result: "15 consecutive success Aug 22-26; first failure 2026-08-26T22:35Z (the strand)."
unverified:
  - claim: "Tonight's B1-carrying nightly (run 33036497832) yields a fresh session-2026-08-26 board live with the chip flipped to Aug 26."
    what_would_verify: "Run concludes (~12:30Z); us_standouts as_of=2026-08-26 on served page; signal.asof steps to 2026-08-26; origination receipt for the run; VPS page re-rendered."
  - claim: "PR #6534's two §0 production proofs (first acceptance-step pass on a scheduled nightly; first live Check E heartbeat grade)."
    what_would_verify: "Observation on natural runs after merge — never dispatch daily.yml or the VPS timer to force them."
unresolved:
  - "Four chip follow-ups filed: dashboard render suite unrun in CI (task_7df1337c); CN board date-chip twin (task_b0e6bfee); [DAY N] rescue-issue escalation within stdlib-only design (task_a194ca27); premium payload freshness grader (task_0c033ef2)."
  - "prophet-outage issues #5920/#6145/#6366/#6495 close only after tonight's fresh-board verification."
next_actions:
  - "Verify tonight's board (run 33036497832) live, then close the open prophet-outage issues with receipts."
  - "Observe #6534's §0 proofs on natural runs; then the WS W2 fire-drill week remains the program done-bar."
do_not_redo:
  - "Do NOT re-diagnose 'cohort 0 for Aug-24/25' — falsified by origination receipts; the sensor line in #6495 referred to the not-yet-run session 2026-08-26."
  - "Do NOT change engine/signal_quality.py:938's asof stamp to fix display dates — it is a measurement clock consumed by ranking and ledgers; display was fixed in PR #6532."
  - "Do NOT add any cancel code path to scripts/prophet_rescue.py — the self-withdraw idea was adjudicated REJECTED; test_no_cancel_code_path_exists is law, and never-cancel outranks runner efficiency."
  - "Do NOT re-propose a runtime JSON surface registry for the monitors — killed by adversarial review (fail-open rot, two sources of truth); the template-dereference coverage TEST in tests/test_prophet_surface_net.py is the mechanism-agnostic contract."
  - "Do NOT dispatch daily.yml or VPS timers to force the §0 production proofs."
danger_areas:
  - "/live/staleness.json is multi-writer — the sentinel heartbeat extends its idiom; never clobber other writers' keys."
  - "The acceptance step's continue-on-error is load-bearing: it protects the checkpoint/commit/publish band; its page path is push_ops_alert from inside the script, not job redness."
  - "The queued rescue dispatch 33032483296 will start a duplicate ~9h nightly when the runner frees — expected, harmless (push steps race-safe), and the never-cancel law applies to it."
discoveries:
  - "DSC:LIVE-LANE-LIVENESS-IS-THE-ARTIFACT-CLOCK"
  - "DSC:ADJACENT-ARTIFACT-MONITORING-GREENLIGHTS-A-DEAD-LANE"
prs: [6532, 6534]
---

## Shape of the month, in one paragraph

Three real failure families produced every sighting: the live lane was never
provisioned (born 2026-07-30, dark 27 days, restored + production-proven
2026-08-26); the nightly's delivery path failed four ways that each left the
board stale-at-open or late (Aug 6 unclassified, Aug 12 force-cancels, Aug 15-17
ruleset freeze, Aug 26 schedule strand) while the mints themselves stayed
healthy on all but one build; and the UI rendered a bucket label that reads as a
freshness date, converting a fresh board into a stale-looking one at a glance.
Each family now has a named instrument: artifact-clock + intake-identity
grading in three watchdogs and an in-job acceptance alarm (#6534), honest
vintage display + machine-readable page clock (#6532), and the availability
ledger + two-tier backfill ruling (this PR) keeping the record straight.
