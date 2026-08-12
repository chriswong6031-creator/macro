# Watchlist

A holdings watchlist plus a portfolio book (`site/watchlist.html`). The user assembles
a set of tickers — equities, ETFs, commodities, crypto — and sees each one's live
signal from the analyzer engine (bottoming / buy-zone / uptrend / avoid), plus momentum
across timeframes, book structure and risk diagnostics. Add via the analyzer-style
search; remove per row.

**Watchlist and Portfolio are two concepts, not one.** A watchlist is an *attention
set* (membership only). A portfolio is *held positions* (shares, entry price, entry
date, status). They have one canonical relational store each and never write to each
other — see "Semantic invariants" below.

## How it works

- **Persist the selection, not the data.** Only the ticker symbols are stored. Every
  name/state/signal is re-resolved live from the nightly `stockdata/index.json` (+
  optional per-ticker JSON) on each load, so a saved list never goes stale across the
  nightly rebuild.
- **Index-first render.** Each row's state badge comes from `index.json`'s `st` field
  with zero extra fetches; richer detail (entry cue + momentum strip) is lazy-loaded
  per card as it scrolls into view.
- **Zero infra by default.** Signed out, the page makes no third-party network calls.
  Cross-device works account-free via an export code / `#wl=` share link.

## Stores

| What | Signed out | Signed in |
|---|---|---|
| Watchlist membership | `localStorage` blob `mdash.watchlist.v1` | Supabase `watchlists` + `watchlist_symbols`, mirrored per list in `mdash.wl.<listId>.v1` |
| Portfolio positions | `localStorage` blob `mdash.pf.v1` | Supabase `portfolio_positions` |
| Notes, sort, filters | `localStorage` only | `localStorage` only |

Notes are local **by ruling**: `watchlist_symbols` has no note column, and this program
does not add one. Server `position` is the order authority.

### Registered multi-list

`templates/watchstore.js` is the relational store. Since W1a it is multi-list:

- `WatchStore.lists.{refresh,create,rename,remove,setActive}` — owner-scoped list CRUD.
  The schema carries a unique `(user_id, name)` index, so a racing create adopts the
  existing row rather than failing.
- `WatchStore.symbols.{list,add,remove,push}` — every symbol op names its list.
- **Which list the page is bound to, and where the fold delivers, are two separate
  questions** (commissioning ruling R1, 2026-08-12):
  - *Binding* — a list named exactly `Watchlist` if one exists; else the **first list
    by `(position, created_at)`, creating nothing**; else (no lists at all) create
    `Watchlist` and bind it. Branch 2 is a deliberate non-creation: a Terminal-native
    account's only list is `Default`, and minting an empty `Watchlist` for it would
    both show this page an empty list and leave a spurious row in the list picker.
  - *Folding* — always the list named `Watchlist`, created if absent. That resolution
    runs only **after** the one-shot marker and empty-book checks, so it fires only
    when there is content to deliver; creation there is on-demand, never spurious.
- Lists created elsewhere (the Terminal seeds one called `Default`) are kept, never
  renamed and never deleted.
- `push` is a full-membership diff that deletes cloud rows absent locally, so it is
  **strictly list-scoped**: the target is captured at enqueue time, debounce timers are
  per list, delete candidates come only from that list's *server* read, and every
  delete carries `.eq('watchlist_id', <list>)`. A localStorage cache is a render hint
  and is never a delete authority. Pinned by
  `tests/test_watchstore_multilist_js.py::test_stale_cache_of_one_list_can_never_delete_another_lists_rows`.

The multi-list *UI* is a later wave. `templates/watchlist.js` carries the binding seams
(`WL.bindList`, per-list storage key, `listId` in `stateSig`, storage-event and
share-fragment scoping); nothing sets a non-null binding yet, so the page runs against
the list the store binds and signed-out behaviour is unchanged.

### One-shot folds (anonymous → account)

On the first successful sign-in, the local books fold into the user's own rows:
`mdash.watchlist.v1` → the `Watchlist` list (marker `mdash.watchstore.folded.v1`), and
`mdash.pf.v1` → `portfolio_positions` (marker `mdash.watchstore.pf_folded.v1`). Both
markers are written **only on success**, and **never on an empty local book** — either
mistake silently discards the visitor's work. Re-running a fold plans nothing.

### Semantic invariants (tested, never regressed)

- Add a ticker to a watchlist → `portfolio_positions` unchanged.
- Add a portfolio position → no watchlist row changes.
- Remove from a watchlist → the portfolio position remains.
- Close a portfolio position → watchlist membership remains.

## Schema authority

The Supabase schema lives in the **mastermind-terminal** repo under
`supabase/migrations/` — `watchlists`, `watchlist_symbols` and their owner /
via-parent RLS policies in `0001_init.sql`, and the recorded `portfolio_positions`
DDL alongside it. This repo owns only `templates/uwp_supabase.sql`, the four own-row
RLS policies for `portfolio_positions`, applied by hand in the Supabase SQL editor.
There is no `templates/watchlist_supabase.sql`; older docs that pointed at one were
wrong.

## Files

`templates/watchlist.html.j2` (page), `templates/watchlist.js` (app),
`templates/watchstore.js` (relational store + folds), `templates/portfolio.js`
(portfolio cockpit), `templates/market_books.js` (per-market derived view),
`templates/risk_core.js` + `templates/watchlist_risk.js` (book structure + risk),
`templates/stockdata.js` (shared signal helpers). Built by `scripts/build_site.py`
(in the `stock_search` block); the hub card is added by `scripts/build_vector.py`.
Config: `watchlist:` in `config.yml`.

Every one of those `.js` files is a **paired plain-copy asset**: `templates/<name>` and
`site/<name>` must be byte-identical in the same commit
(`python -m scripts.check_template_site_sync --fix`). The pair goes live on the VPS's
3-minute pull; the `?v=` cache-buster in the `.j2` is hand-written and only re-stamps on
a render, so bump it in the same PR whenever a body changes.

## Accounts (cross-device sync) — PROVISIONED

Project `MarketIntelligence` (`fsldfzlxyavsuwqbceod`), shared with the Terminal:

- `config.yml → watchlist.supabase` holds the project URL + **publishable** key. It is
  public by design — per-user isolation is enforced by RLS, never by secrecy. The
  `service_role` key is never in this repo. The config is baked into `theme.js` at copy
  time, so accounts work on every page.
- Sign-in is the shared global modal (`window.MDXAuth`, owned by `theme.js`):
  email + password, or an OAuth provider enabled in the Supabase dashboard. The SDK is
  self-hosted (`templates/supabase.js`) and lazy-loaded, so anonymous visitors stay
  zero-third-party and the page still loads behind the GFW.
- Redirect allowlist + Site URL are configured in Supabase → Authentication → URL
  Configuration. OAuth returns to the page the user started on, not a fixed host, so a
  new origin needs to be added there.
- `templates/auth.js` is the retired magic-link predecessor. The watchlist page no
  longer loads it; `watchstore.js` owns the sync seams it used to.

### Optional: keep-alive

Free projects pause after ~7 days idle. If that becomes a problem, add a scheduled
anon-key REST ping to `.github/workflows/daily.yml` (needs `SUPABASE_URL` +
`SUPABASE_ANON_KEY` repo secrets).

### Verifying RLS (do this — most Supabase leaks are RLS misconfig)

Sign in as two different accounts and confirm neither can read or write the other's
rows in `watchlists`, `watchlist_symbols` or `portfolio_positions`, and that a query
with only the anon key (no signed-in JWT) returns nothing.
