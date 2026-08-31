---
key: QUOTE-HUB-CHG-IS-PERCENT-AND-TS-IS-A-PRINT-CLOCK
claim: >
  Two fields in the Terminal Quote Hub `/quotes?syms=` row are named in a way that invites
  the exact wrong reading, and both mis-readings ship a plausible number rather than an
  error. (1) `chg` is a PERCENT, not the dollar move: measured live on 2026-08-27 23:22Z,
  NVDA returned `{"last":227.98,"prevClose":209.66,"chg":8.7379566917867}` — 227.98-209.66
  is 18.32 dollars, and 8.7379% is that move as a percentage. A consumer rendering `chg` as
  the absolute move prints "+$8.74" beside a correct price and nothing raises. (2) `ts` is
  epoch SECONDS taken from the VENDOR's print/bar clock, NOT the hub's fetch clock, so it
  STOPS ADVANCING once the regular session closes: the same NVDA row held `ts:1787871758`
  unchanged across probes 16 minutes apart while `/health.snapshotFeed.lastOkAt` kept
  moving. A consumer applying one flat `now - ts` staleness bound therefore declares every
  CORRECT settled after-hours close "stale" a few minutes after the bell. Separately, the
  row carries the regular session (`last`/`close`/`prevClose`/`chg`) and the extended
  session (`extPrice`/`extChg`/`extTs`) side by side, and on that same row they had
  OPPOSITE signs — regular +8.74%, extended -0.76%.
falsifier: >
  A `/quotes?syms=NVDA` row where `chg` equals `last - prevClose` rather than
  `(last - prevClose) / prevClose * 100`; or a row whose `ts` advances during a closed US
  session while the regular-session `last` is unchanged; or
  `python3 -m pytest tests/test_dossier_quote_api.py::test_change_abs_is_derived_not_read_from_the_percent_field
  tests/test_dossier_quote_api.py::test_a_settled_after_hours_close_is_not_called_stale`
  passing against a consumer that reads `chg` as dollars or applies a session-blind bound.
so_what: >
  Derive the dollar move as `last - prevClose` and treat `chg` as the percent; never read
  one from the other's name. Make any staleness bound SESSION-AWARE (`marketSession`:
  pre/rth/post/overnight) — tight during RTH where a gap means a broken feed, wide outside
  it where a final print legitimately stops advancing — or the honest fallback fires
  against correct data and reverts the surface to its baked value. Never render `extChg`
  as the day move; check `regularSessionDate` before calling a move "today", because the
  hub can also hand back the LAST COMPLETED session's move before an open. Also: the hub
  has a DNS-rebind Host guard that returns the bare body `forbidden` (not JSON, not a
  JSON error) to any request whose Host header does not match its own host:port — an SSH
  tunnel on a different local port is rejected until you send `Host: 127.0.0.1:3100`, so
  a tunnel probe failing is not evidence the hub is down.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  live probes of the production hub on the VPS (`curl 127.0.0.1:3100/quotes?syms=NVDA` and
  `/health`, 23:22Z and 23:38Z) plus an end-to-end run of app/dossier_quote.py against the
  real hub over an SSH tunnel returning NVDA 227.98 / +18.32 / +8.7379566917867 and AAPL
  314.58 / +1.13 / +0.3605; tests/test_dossier_quote_api.py (21 cases); PR #6572
scope:
  - mastermindx-market-intelligence/macro
  - app/dossier_quote.py
  - charting-app hub/lib/store.js
confidence: verified
---

A note on where the contract can be read. The `charting-app` checkout on the fleet host
sat on `claude/terminal-audit-fixes-20260713` (2026-07-13) during this work, and that tree
does NOT contain the code production runs: it has no `HUB_REALTIME_QUOTES`, no snapshot
leg, and its US rows carry `source:"polygon-delayed"`, while the live hub returns
`source:"polygon-snapshot"` with `anchor_source:"snapshot"`. Reading the contract out of
that checkout produces a confident, cited, and WRONG answer. Probe the running service for
anything freshness-related; use the repo only for intent.

Related: `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md` — display rights are open, but
the debrand law means `source`/`basis`/`anchor_source` must never reach a public surface.
