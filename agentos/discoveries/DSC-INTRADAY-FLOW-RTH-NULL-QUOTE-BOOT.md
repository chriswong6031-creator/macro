---
key: INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT
claim: >
  During RTH (09:25–16:05 ET), templates/intraday_flow.html.j2 used to call render()
  before any quote existed; computeStance's pin-watch branch read quote.price on a
  null quote whenever a leader had opex_days<=5 and dealer.regime==='long' (AAPL on
  2026-08-19), throwing TypeError and skipping startPolling(), which froze the
  server-rendered "Reading the tape…" placeholders. Off-hours the livePresent guard
  returned before that branch, so the crash was RTH-gated. PR #6014 landed quotePx,
  polling-before-render, and board-coverage feed stamps.
falsifier: >
  Opening production /intraday_flow.html during RTH with empty quoteState and a
  long-regime near-OPEX leader throws TypeError on quote.price, or the template
  pin-watch block again reads quote.price without quotePx.
so_what: >
  A fully blank Intraday Flow desk during RTH is a boot exception until proven
  otherwise — do not open a Theta/R2 incident from that screenshot. Restore the
  template, not generated HTML alone. Keep L5 null when flow is missing.
kind: runtime
verified_at: 2026-08-19
verified_by: >
  jsdom reproduction on production bytes md5 ece5ee414b007db29088f72bdcc1ef89
  (PR #6014 / merge d5de4e62779436f1551ce177b7506ffe468e2884);
  templates/intraday_flow.html.j2 quotePx + pin-watch px != null;
  tests/test_intraday_flow_ncp_js.py test_boot_empty_state_rth_no_throw.
scope:
  - macro
  - options-intelligence
  - templates/intraday_flow.html.j2
confidence: verified
---
