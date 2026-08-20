---
key: INTRADAY-FLOW-AGE-HEALTH-CAN-HIDE-EMPTY-BOARD
claim: >
  Intraday Flow can be age-fresh and still functionally empty at three independent
  seams: the public display quote snapshot covered only 3 of its 116 leaders; the
  pulse producer stamped mode=no_data after rejecting a DatetimeIndex named ts; and
  the options-flow poller process remained running from an obsolete deploy tree while
  its public source asof stayed eight days old. HTTP status, file mtime, and a running
  PID therefore do not establish a live desk.
falsifier: >
  Reproduce against the 2026-08-20 production artifacts and show either that
  live/quotes.json contained at least 105 of the 116 base leaders, that the current
  intraday parquet index was already normalized into a recognized timestamp column,
  or that the running M1 checkout had the current origin/main poller code and emitted
  a current live_flow.meta/v2 asof before recovery.
so_what: >
  Intraday Flow health and UI labels must gate on board coverage plus payload semantics:
  at least 90 percent priced leaders, at least 80 percent with current-session bars,
  mode=fastpath, and a source-fresh options meta stamp during RTH. Operations must also
  compare the running checkout SHA/code with origin/main and inspect the public source
  clock, not stop at launchd/systemd state.
kind: runtime
verified_at: 2026-08-20
verified_by: >
  Intersected production live/quotes.json with site/flowtracker/base.json (3/116);
  inspected VPS quotes_full.json (116/116), flow_pulse.json (mode=no_data), and AAPL
  parquet (DatetimeIndex name ts with current rows); called _today_bars (zero before
  normalization); inspected M1 launchd state, checkout, stderr, and R2 meta.asof.
scope: [macro, intraday-flow, vps-live, m1]
confidence: verified
---

## Recovery consequence

The fix is deliberately transport- and truth-layer only. It filters the already-fetched
VPS full snapshot into a board-scoped public artifact, normalizes datetime index labels,
refuses to publish semantically empty pulses, exposes pulse coverage through `/api/status`,
and refuses stale options-flow “live” labels during RTH. It does not change stance logic,
create a second quote engine, or synthesize missing data.
