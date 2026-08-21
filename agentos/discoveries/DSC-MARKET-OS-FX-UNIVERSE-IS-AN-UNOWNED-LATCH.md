---
key: MARKET-OS-FX-UNIVERSE-IS-AN-UNOWNED-LATCH
workstream: "WS:MARKET-OS"
date: 2026-08-21
session: market-os-macro-merge-1bc993
falsifier: >
  Show a code path on current main where, with the mode gates and boundary
  resets removed, a surface can NOT end up rendering another surface's (or
  another user's) universe from the retained FX/RISK/BOOK state — i.e., show
  the latch has since gained a single owner that invalidates it at every
  boundary, making the defense layers redundant.
so_what: >
  Any new producer or consumer on the watchlist-page risk chain
  (factor_exposure.js FX -> watchlist_risk.js -> watchlist.js RISK /
  portfolio.js BOOK) must (1) never use null-push as "empty" (null means "fall
  back to whatever universe was last fed"), (2) invalidate retained payloads at
  every mode AND auth-identity boundary, and (3) validate cross-module payloads
  against the consumer's own universe before repainting. Skipping any of the
  three reintroduces cross-surface or cross-user reads.
---

The watchlist page's risk chain holds derived state in module-level latches that
no single component owns: `factor_exposure.js` keeps `LAST` (last-fed universe)
and `AUTO_W`; `watchlist_risk.js` keeps `LAST_READ`; `watchlist.js` keeps
`RISK`; `portfolio.js` keeps `BOOK`/`RISK_SHARES`. Nothing at the mode boundary
or the auth boundary invalidated any of them, and `setAutoWeights(null)` means
"revert to the LAST universe" — so a zero-position Portfolio rendered the
Watchlist's concentration read (three independent sessions hit this in one day:
PR #6098's review, the A1A closure debugger, and sibling fix #6102), and user
A's book could repaint under user B after a same-page sign-in.

Fixed 2026-08-20/21 by defense in depth (#6102 + #6136): a `data-ws-mode` choke
point in factor_exposure render, honest-empty `{}` pushes (never null) from
portfolio.js, RISK/BOOK resets at `setMode` and `wl-auth` identity changes, and
consumer-side payload validation in `PF.setBookRisk`. The layers are
individually load-bearing (reviewer proofs E/F/H); see
[[MARKET-OS-2026-08-21]] and PR #6136.
