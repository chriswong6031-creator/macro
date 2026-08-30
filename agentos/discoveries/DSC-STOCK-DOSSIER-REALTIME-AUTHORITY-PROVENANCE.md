---
key: STOCK-DOSSIER-REALTIME-AUTHORITY-PROVENANCE
claim: >
  The 2026-08-28 runtime effect that set `HUB_REALTIME_QUOTES=1` in
  `/opt/terminal/.env` and restarted quote-hub is strongly evidenced and later
  production proof shows that it worked, but the historical MODIFYING AUTHORITY
  for that runtime change is not independently recoverable from the current
  canonical company records. The original Stock Dossier P0 carrier
  `stock-dossier-live-quote-p0-20260827-sol-001` conditionally permitted the
  switch in its initial commission, but the same carrier later issued an
  explicit Sol ruling at Slack ts `1787879051.870039`: DO NOT set
  `HUB_REALTIME_QUOTES=1` in P0; any realtime/access-policy change requires a
  separate future operation/carrier. Sol reiterated that boundary at ts
  `1787901611.674119`. The later 2026-08-28 Agent OS handoff/workstream records
  quote an operator directive — "Need to fix the delayed thing, so that its live.
  you are authorized to conduct any changes needed." — and use it as the
  authority for setting the flag, but those records cite no Slack message,
  GitHub comment, Linear comment, Executive admission, operation key, or other
  independently recoverable source for that directive. Macro PR #6619, which
  landed those records, has no PR discussion establishing the missing authority
  edge. Runtime success therefore proves EFFECT, not the historical authority
  chain that produced it.
falsifier: >
  Recover an independent pre-mutation authority receipt that post-dates the P0
  DO-NOT-SET ruling and clearly authorizes the shared Terminal runtime change as
  a new modifying operation — for example the original Chairman outer directive
  with recoverable timestamp/session context plus the resulting stable
  operation/carrier, or a canonical Executive/Slack/GitHub admission/receipt
  proving that authorization before the env write. A later handoff restating
  the same sentence, a successful quote-hub restart, a realtime health verdict,
  or a merged records PR does NOT falsify this discovery because those prove
  effect/state rather than authorization provenance.
so_what: >
  Preserve two facts separately. Product/runtime truth: the realtime snapshot
  leg was enabled, quote-hub restarted, the hub self-graded realtime during open
  RTH, and the dossier route/page consumed that measured state. Governance
  truth: do not retroactively call the runtime mutation P0-authorized or
  Chairman-authorized unless the independent authority receipt is recovered.
  Do not roll back a known-good runtime merely to make the historical record
  cleaner; rollback would be another modifying operation requiring current
  authority and current Terminal evidence. Future changes to
  `HUB_REALTIME_QUOTES`, `HUB_POLYGON_CLUSTER`, quote-hub service state, or the
  Terminal access policy require a fresh explicit operation/carrier and current
  source/entitlement checks. P0 product acceptance and historical authority
  provenance are different gates.
kind: landmine
verified_at: 2026-08-29
verified_by: >
  Canonical #agent-dispatch carrier `C0BSBM78V1N/1787871577.020189`, including
  Sol DO-NOT-SET ruling `1787879051.870039` and Sol REQUEST_REPAIR
  `1787901611.674119`; current Macro Agent OS handoffs
  `WS-STOCK-DOSSIER-LIVE-QUOTE-2026-08-27.md` and
  `WS-STOCK-DOSSIER-LIVE-QUOTE-2026-08-28.md`; current workstream
  `WS-STOCK-DOSSIER-LIVE-QUOTE.md`; Macro PR #6619 body and empty discussion;
  Linear MAS-186 and its empty comment history; repository/Slack searches for
  the quoted directive and `HUB_REALTIME_QUOTES` authority edges.
scope:
  - mastermindx-market-intelligence/macro
  - WS:STOCK-DOSSIER-LIVE-QUOTE
  - Terminal quote-hub runtime configuration
confidence: verified
---

This discovery is a provenance correction, not a rollback order and not a new
Terminal policy. Historical Agent OS handoffs remain evidence of what the
operator observed and did; they are not silently rewritten to manufacture an
authority receipt that the current estate cannot recover.
