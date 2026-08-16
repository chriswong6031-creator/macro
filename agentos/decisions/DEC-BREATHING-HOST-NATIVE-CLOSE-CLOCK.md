---
key: BREATHING-HOST-NATIVE-CLOSE-CLOCK
question: >
  Where does the same-session Prophet board's primary product clock live, where does
  its compute run, and what is its same-day close source?
answer: >
  Primary clock = Mac Studio launchd (StartCalendarInterval 13:00 PT weekdays = 16:00
  ET year-round), driving a host runner that refreshes a dedicated locked worktree to
  origin/main and runs the canonical scripts.close_pass_publish. Compute stays on the
  Mac because the canonical price store and canonical gate functions live there. The
  same-day close source is Massive REST — grouped daily (finalized) with full-market
  snapshot day-bar fallback in the first minutes, RTH-close basis, same-session
  corp-action names darked. The GitHub close-pass.yml lane is DEMOTED to a bounded
  backstop (fast-exits when the primary already published; annotates loudly when it
  actually publishes). The VPS keeps transport/serving only (5-min R2 mirror,
  board_state CAS annotation) — no board compute tier on the VPS.
rationale: >
  Measured 2026-08-14: GitHub cron drift 27-45 min on this workflow, queue waits to 95
  min on the shared macstudio pool, board delivered ~19:20 ET; estate-wide GH-cron gaps
  90min-3h12m already ruled it un-purchasable as a product clock
  (DEC:LER-LIVE-LANE-VPS-5MIN-REST). The coverage defect (253/1,763 evaluated; 1,508
  no_todays_bar) is a source problem, not a clock problem: the keyless Yahoo heal
  refreshes only the index group. Massive grouped daily returned 12,424 tickers for
  2026-08-14 with closes matching the snapshot day-bar to the cent
  (DSC:MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE). The Mac host .env already carries
  MASSIVE_API_KEY + the full R2 write set, so no new credential provisioning is
  required. launchd precedent is established house practice (prophet-rescue host half,
  chainheat close-timed schedule, worktree-GC).
alternatives:
  - option: Keep GitHub cron as the primary clock (tighten the schedule)
    why_not: "Measured drift + pool contention are structural; no schedule edit buys a 16:15 ET SLO on a 90min-3h12m-gap scheduler."
  - option: VPS systemd compute tier joining the nightly armed pack with snapshot closes
    why_not: >
      A third compute path with its own math-parity burden; tonight's armed pack covers
      only 91/1,761 names with levels (probe_cap_cross budget cut 1,535), so the join
      cannot produce a full board today. Revisit only as a degraded-rescue tier after
      the W-L2 arming-budget work raises pack coverage — and then only reusing pack
      semantics, never approximating the gate.
  - option: Massive WebSocket for close observation
    why_not: "Single-slot evict-oldest hazard; TP-1 owns any future socket; REST answers a once-daily close question."
  - option: Move the board into closing-bell.yml's render
    why_not: "Measured 109 min behind an 81-min spine; already rejected in close-pass.yml's header."
evidence:
  - "close-pass run receipts 2026-08-14: cron 20:25Z created 20:52Z; sibling created 21:47Z ran 23:22Z (95-min queue); board summary line printed 23:20Z (~19:20 ET)."
  - "close-pass 2026-08-14 telemetry: 22 admitted of 253 evaluated (universe 1763); skipped no_todays_bar=1508."
  - "Massive probes 2026-08-15 (Sat): grouped 08-14 = 12,424 tickers, AAPL c=305.93 == snapshot day.c; AAPL snapshot updated stamp = exactly 2026-08-14T20:00:00.000Z; splits execution_date=08-14: IDTIF 200:1, HAO 20:1, BYND 30:1; dividends ex 08-14: 450 rows."
  - "Host .env key names (values unread): MASSIVE_API_KEY, MASSIVE_S3_*, R2_ENDPOINT/ACCESS/SECRET/BUCKET, FRED, THETA, TUSHARE."
  - "agentos/decisions/DEC-LER-LIVE-LANE-VPS-5MIN-REST.md — GH cron 90min-3h12m measured gaps."
affects: ["scripts/close_pass_host_runner.py", "ops/launchd/com.macro.closepass.plist", "scripts/install_closepass_launchd.sh", ".github/workflows/close-pass.yml", "engine/close_pass/massive_close.py"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-15
---

## Grounds

Chairman directive 2026-08-15 (Breathing Platform revival) ordered a host-native
primary scheduler and Massive as primary same-day source; this record pins the
specific shape after the collision audit and live measurement. The choice keys on
"where is the minimum required data/runtime": the full board needs the canonical
adjusted price store and the canonical `signal_gate`/`us_board_rank` functions —
both Mac-resident — so the compact-pack VPS tier cannot produce a full board
today and the Mac hosts the clock.

## What would reopen this

W-L2 raising armed-pack coverage to ~full universe would make a VPS degraded-rescue
tier viable (pack × snapshot join, pack semantics only). TP-1 shipping changes the
intraday transport, not this close clock. A measured failure of launchd delivery
(TCC/FDA regression, host loss) escalates the GitHub backstop back to primary until
healed.
