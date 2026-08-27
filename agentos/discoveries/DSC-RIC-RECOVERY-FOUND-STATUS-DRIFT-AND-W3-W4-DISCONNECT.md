---
key: RIC-RECOVERY-FOUND-STATUS-DRIFT-AND-W3-W4-DISCONNECT
claim: >
  The July RIC completion map is no longer reliable as current-state truth: later systems supersede
  some planned ownership, while current main still leaves W3 OPEX risk disconnected from merged W4
  event-window context and contains other material semantic-staleness/evidence-epoch gaps.
falsifier: >
  Re-read current protected/master and macro/main, then show all of the following false: (1)
  engine/opex_risk.py no longer hard-codes event_collision=None / 'W4 not yet built'; (2) a current
  RIC yield-momentum organ exists; (3) data/release_forecast/latest.json no longer withholds accuracy
  under an experimental target epoch; (4) data/rates_command/latest.json carries fresh component
  policy intelligence; and (5) a canonical later Transmission organ does not already own calibrated
  rates/inflation pass-through.
so_what: >
  Future sessions must recover by capability and canonical owner rather than by old W-number labels.
  Repair the W3/W4 seam, build only the genuinely missing yield/cohort composition, respect MRI's
  current evidence epoch, and reject any PR that recreates release/calendar/options/transmission
  ownership or calls file freshness production/semantic freshness.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  Protected Mastermind master 6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182; macro main recovery reads of
  engine/opex_risk.py, engine/event_window.py, engine/event_calendar.py,
  engine/rate_inflation_transmission.py, data/release_forecast/latest.json,
  data/rates_command/latest.json, data/options_surface/_backfill_state.json and the current RIC/MRI/TXI
  masterplans; direct open-PR and Slack #agent-dispatch reconciliation on 2026-08-27.
scope:
  - WS:RATES-INFLATION-COMMAND
  - rates-inflation-command
  - macro-release-intel
confidence: verified
---

## Evidence that changes continuation behavior

- `engine/opex_risk.py` still labels `event_collision` as a null W4 slot and never consumes the
  already-merged event-window result.
- `engine/yield_momentum.py` and `engine/ric_scorecard.py` are absent on the recovered main lineage.
- Macro Release Intelligence's current artifact calls present forecast points experimental and
  withholds accuracy until clean aligned forward evidence accrues.
- The current Forward Path artifact is fresh at the file level while one policy-intelligence input is
  44 days stale, proving file timestamp is not sufficient health evidence.
- The broad options-surface backfill exists, but committed parquet/history does not prove the current
  production collector/build lane is advancing.
- Later Transmission Intelligence explicitly says not to build a new causal brain and names the
  existing rate/inflation map and per-stock sensitivity substrate as organs to compose.

## Continuation consequence

The correct remaining program is not 'resume W5 then W6'. It is the F0-F7 capability graph frozen in
`research/RATES_INFLATION_COMMAND_RECOVERY_AND_COMPLETION_FREEZE_2026-08-27.md`.
