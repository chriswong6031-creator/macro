---
key: LER-W5-PROSPECTIVE-CONSUMER-DISCONNECTED
claim: >
  Live Entry Radar's historical W4.1 / Prophet Lab warm `live_forward` commissioning does
  not mean the canonical W5 prospective Evaluation OS consumer is connected. On current
  Macro main `2299cbafe42568ef3b088911fc80d6373e5e270d`, the nightly-owned
  `data/entry_radar/ledger_state.json` for market session 2026-08-27 reports
  `state=WAITING_FOR_LIVE_SOURCE`, `spool_dir=null`, `observed_spool_events=0`,
  `live_forward_rows=0`, `forward_rows_total=0`, and qledger
  `registered=0/rejected=0/failed=0`. Therefore genuine Radar live events are not currently
  evidenced as flowing through the existing W5 sole durable reconciler into the canonical
  prospective forward ledger/qledger path.
falsifier: >
  A natural current-session production receipt from the existing W5 nightly owner showing
  the canonical private Radar event spool as its resolved intake, at least one genuine
  `entry_radar.events/v1` event validated through the existing reconciler, a nonzero
  LIVE_FORWARD `data/entry_radar/forward.parquet` row, and the corresponding existing
  qledger registration outcome; the resulting canonical ledger state must name nonzero
  observed/live-forward totals and no longer depend on a null spool path.
so_what: >
  W5 historical/replay machinery may remain `done`, but the production prospective evidence
  capability is `DARK_OR_DISCONNECTED` until the falsifier is met. W6 production acceptance,
  W7 sample accrual and final Radar research acceptance must not use the Prophet Lab board or
  the 2026-08-20 warm-loop receipt as a substitute for the canonical W5/Evaluation OS path.
  Repair must extend `scripts/reconcile_entry_radar.py` and its existing spool/qledger owners;
  no second forward store, qledger, R2 client, nightly writer or scheduler is authorized.
kind: runtime
confidence: verified
verified_at: 2026-08-28
verified_by: "GitHub read of data/entry_radar/ledger_state.json on Macro main 2299cbafe42568ef3b088911fc80d6373e5e270d"
scope:
  - "macro"
related:
  - "WS:LIVE-ENTRY-RADAR"
  - "DEC:LER-END-TO-END-COMPLETION-ARCHITECTURE-FREEZE"
  - "DSC:RADAR-SPOOL-PUBLIC-R2"
---

This discovery separates two different prospective consumers that historical handoffs had
allowed to blur in human discussion: the read-only Prophet Operator Lab and W5's canonical
durable Evaluation OS/qledger lane. The first was genuinely commissioned; current durable
truth shows the second is not currently receiving Radar live source events.
