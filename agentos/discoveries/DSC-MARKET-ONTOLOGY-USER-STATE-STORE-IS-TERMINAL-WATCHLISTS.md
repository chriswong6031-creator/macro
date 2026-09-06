---
key: MARKET-ONTOLOGY-USER-STATE-STORE-IS-TERMINAL-WATCHLISTS
claim: >
  The user-scoped watchlist store for the product is already implemented in the
  Terminal repository at origin/master e89ebda4 (terminal/lib/watchlists.ts,
  terminal/app/api/watchlist/route.ts) over the shared Supabase tables
  `public.watchlists` / `public.watchlist_symbols` created with row-level security in
  supabase/migrations/0001_init.sql, and Macro's templates/watchstore.js writes the
  same tables with the same double `user_id` filter; there is no user-scoped
  holdings/watchlist object in Macro engine/ and none is needed.
falsifier: >
  In /Users/chriswong/Documents/Cluade/charting-app run
  `git cat-file -e e89ebda4:terminal/lib/watchlists.ts && git show e89ebda4:supabase/migrations/0001_init.sql | grep -n "watchlists.*enable row level security"`;
  an absent file, a missing RLS line, or a Macro engine module that owns per-user
  watchlist rows would disprove this.
so_what: >
  S4 (analysis → thesis/holdings/watchlist) is NOT an unowned seam. Sessions must
  route user-state work to the existing Terminal owner and Macro watchstore.js
  binding, never commission a replacement store from an engine-only census, and
  must not record "Terminal presumed, no implementation verified". The remaining
  gap is authenticated LIVE proof of the journey and tenant scoping evidence, which
  are separate proof tasks, not build tasks. House thesis (engine/macro_thesis.py)
  and house portfolio (engine/portfolio.py) stay house-level by design.
kind: architecture
verified_at: 2026-09-05
verified_by: >
  charting-app: `git cat-file -e e89ebda4:<path>` for the three paths (all present);
  `git show e89ebda4:supabase/migrations/0001_init.sql` lines 28-48 (tables) and
  97-99 (RLS); `git show e89ebda4:terminal/lib/watchlists.ts` lines 14-18, 106-109
  (owner scoping via `.eq("user_id", userId)`). Macro origin/main a232b1743e54
  templates/watchstore.js lines 4-32 (same tables, anonymous store `mdash.watchlist.v1`).
  Sol correction 1788599922.022699 on Slack root C0BSBM78V1N/1788510607.305039.
scope:
  - mastermindx-market-intelligence/charting-app
  - mastermindx-market-intelligence/macro
  - terminal/lib/watchlists.ts
  - templates/watchstore.js
  - WS:MARKET-OS
confidence: verified
---

# Where user state lives

Terminal owns the authenticated watchlist CRUD (`lib/watchlists.ts`, API route
`app/api/watchlist/route.ts`); RLS policies on `public.watchlists` and
`public.watchlist_symbols` are the authority for owner scoping, and both products
add a belt-and-braces `user_id` filter on top. Macro's `watchstore.js` is the
cloud binding for the anonymous local store `mdash.watchlist.v1` and never touches
the watchlist DOM.

# What is still unproven

No census or Sol read has yet executed the authenticated journey live in
production, and no evidence either way exists for multi-tenant scoping beyond the
single-user RLS. Those are V-type proof tasks for the F11/F12 owners, not reasons
to build.
