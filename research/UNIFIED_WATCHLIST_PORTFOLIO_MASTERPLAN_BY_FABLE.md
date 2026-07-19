# Unified Watchlist & Portfolio (UWP) — masterplan (by Fable)

Date: 2026-07-18
Status: CHARTER + W0 verification record. Operator-directed (2026-07-18 session): one
centralized, per-user watchlist + portfolio dashboard on the macro site, sharing canonical
state with the Mastermind Terminal (app.mastermind-x.com) so edits update everywhere.
Governance: PRD Amendment 1 (operator override, same PR) struck the PRD-R1 placement
exclusivity; see `PORTFOLIO_RISK_DESK_MASTERPLAN_BY_FABLE.md` §12 for what remains in force.
Registries consulted: `docs/ACTIVE_BUILD_MAP.md`, `research/DO_NOT_REBUILD.md`,
`config/ruling_graph.yml` (NWC-U4, NWP-U18, RUL-F3.2 — none struck; narrowed per Amendment 1).

## 1. One-line verdict

Evolve `watchlist.html` into a unified, per-user watchlist + portfolio dashboard: static
nightly-baked page + client-side supabase-js CRUD against the **already-live** Terminal
relational schema (`watchlists`/`watchlist_symbols`) plus the **already-live**
`portfolio_positions` table, joining holdings against baked signal JSON entirely client-side
— **no live-web-app rewrite, no per-user server rendering, no new auth stack**.

## 2. W0 verified facts (probed live via PostgREST anon key, 2026-07-18)

- The live Supabase project (`fsldfzlxyavsuwqbceod`) has the **relational** schema:
  - `watchlists` (id, user_id, name, position, created_at — no updated_at)
  - `watchlist_symbols` (id, watchlist_id, symbol, section, position, created_at — no note col)
  - `portfolio_positions` (id, user_id, ticker, shares, entry_price, entry_date, notes,
    status, created_at, updated_at) — full PRD §5 shape, live today.
- `watchlists.doc` **does not exist** (42703): `templates/watchlist_supabase.sql` (doc-blob
  schema) was never applied. Therefore the macro site's `templates/auth.js` cloud sync
  (`select('doc')` / `upsert({doc})`) has been **silently broken in production** — every
  pull/push 400s. All macro watchlist state is localStorage-only (`mdash.watchlist.v1`,
  factor weights `mdash.fx_weights.v1`).
- Consequence: there is **no server-side blob data to migrate**. Migration = one-time
  client-side fold of the localStorage blob into the relational schema on first
  authenticated visit.
- Auth/SSO already unified: Supabase GoTrue (email+password, Google OAuth PKCE), session
  cookie scoped to `.mastermind-x.com` — macro site and Terminal share login today.
- RLS: anon probes return `[]` (deny-consistent). W1 must verify owner-scoped policies exist
  on all three tables for `authenticated` (Terminal presumably has them; confirm + add
  `portfolio_positions` policies if missing) — operator action in Supabase dashboard, SQL
  shipped in-repo as the source of record.

## 3. Supabase adequacy verdict (operator question, adjudicated)

**Keep Supabase. It is decisively good enough; a "more complex" user-management system would
add cost and ops burden with zero capability gain at this scale.**

- Already provides everything UWP + MNZ need: GoTrue auth (email/password, OAuth, PKCE,
  email-confirm toggle), cross-subdomain SSO cookie, Postgres + RLS (per-user data auth
  fused with storage — the pattern `watchlists` already proves), PostgREST instant CRUD (no
  backend code), realtime channels (optional "updates everywhere" push), and room for the
  MNZ entitlement/token-metering tables already designed on it.
- Scale: user base is 10²–10⁴; Supabase Pro comfortably serves 10⁵+ MAU. The genuine
  reasons to graduate (SAML/enterprise SSO, org/team hierarchies, SCIM provisioning,
  multi-region auth latency) do not exist in this product.
- Alternatives lose on every axis: Auth0/Clerk = per-MAU pricing + still need a DB for state
  + no RLS integration; Keycloak/custom = self-hosted ops burden on a one-operator project.
- Watch items (revisit triggers, not blockers):
  1. **Mainland-China reachability** of `*.supabase.co` (bilingual site, EdgeOne-fronted for
     CN). SDK is already self-hosted for GFW safety; if first-party analytics show CN auth
     failures, mitigate with a Caddy same-origin proxy (`/sb/*` → project URL) — config
     change, not a migration.
  2. **RLS discipline is the entire security boundary** (anon key is public by design):
     every new per-user table ships owner-scoped policies in the same PR, reviewer-checked
     (UWP-R5). Service keys never reach the client.
  3. Vendor exit exists (it's Postgres — `pg_dump`; GoTrue is OSS). Acceptable lock-in.

## 4. Architecture of record

```
Supabase (fsldfzlxyavsuwqbceod)                      ┌── Terminal (Next.js, separate repo)
  watchlists / watchlist_symbols  ◄── RLS owner ─────┤    already reads/writes these tables
  portfolio_positions             ◄── scoped CRUD ───┴── macro site watchlist.html (this repo)
        ▲                                                  supabase-js (self-hosted SDK)
        │ one-time client fold on first auth visit          │ client-side join, display-tier
  localStorage mdash.watchlist.v1 (legacy + logged-out mode)│
                                                            ▼
  nightly-baked JSON (unchanged): stockdata/index.json, stockdata/<T>.json,
  factor_betas.json, STATE_DISPLAY — signals/prices remain nightly; optional live
  quotes later via dormant macro-quotes Worker (W4, separate billing decision)
```

- The page stays static and render-budget-free; the per-user layer is purely client-side.
- Logged-out = current localStorage behavior, full-featured minus sync (UWP-R6).
- Terminal needs **zero watchlist-side changes** (it owns the canonical schema already);
  W3 is optional portfolio-UI parity in the Terminal repo.

## 5. Rulings

- **UWP-R1 (placement & state):** the unified dashboard lives on the macro site as an
  evolution of `watchlist.html`. Per-user state lives ONLY in Supabase under owner-scoped
  RLS (+ localStorage cache). Nothing position-derived is committed to any repo, logged
  with values, or written into macro artifacts (PRD-R7 verbatim).
- **UWP-R2 (two-organisms preserved):** user watchlists/holdings never feed the macro
  signal path, boards, rankers, Neural Web, alert triage, or any scored artifact. The
  signal join is client-side display only. (NWC-U4 restated for this program.)
- **UWP-R3 (canonical store):** the live relational schema is canon. The doc-blob schema
  (`templates/watchlist_supabase.sql`, `auth.js` pull/push) is retired in W1; the
  localStorage blob remains as offline cache/logged-out mode, folded (never forked) into
  canon on first authenticated visit.
- **UWP-R4 (no fused score, no advice):** no composite per-position or per-book risk
  number (PRD-R2). Copy uses review language, no imperative buy/sell/add/trim (PRD-R4/B6);
  "validated" banned (CI-enforced). Every panel passes DESIGN_DOCTRINE glance-tier rules.
- **UWP-R5 (RLS in the PR):** any new/altered per-user table ships its RLS policies as SQL
  in the same PR, applied to prod before the consuming UI merges; reviewer must check
  policies before approving.
- **UWP-R6 (progressive enhancement):** the page never breaks without auth or when
  Supabase is unreachable (GFW/outage) — degrade to localStorage silently, disclose sync
  state plainly ("Synced" / "Local only" chip).
- **UWP-R7 (portfolio display tier):** holdings views show user-entered facts + baked
  display-tier context (state badge, entry cue, factor exposure). No P&L-derived
  escalations, no engine writes keyed on holdings.

## 6. Waves

- **W0 (this PR, docs-only):** registry override + PRD Amendment 1 + this charter + live
  schema probes. DONE.
- **W1 — store layer:** verify/add RLS policies (SQL committed as
  `templates/uwp_supabase.sql`, applied to prod); new shared `templates/watchstore.js`
  module (supabase-js CRUD for lists/symbols/positions, localStorage cache, blob fold-in,
  cross-tab + refetch-on-focus); retire `auth.js` doc-blob sync; delete
  `watchlist_supabase.sql`. Tests for fold/merge logic. DONE.
- **W2 — unified dashboard UI:** DONE-pending-merge. Delivered scope:
  - `watchlist.html.j2` revamp: updated title/h1/subtitle (bilingual), new Portfolio
    section (`#pf_section`) after card grid and empty-state; section contains signed-out
    state, error state, empty state, open-positions table, closed-positions `<details>`,
    add button, as-of footnote; `#fx_panel` repositioned directly after portfolio section
    (getElementById consumers unaffected); `#dlg-holding` modal (mx5-dlg shell, narrow
    panel, all `pfm_*` field ids per `portfolio.js` DOM contract); inline mx5 CSS subset
    (canonical values from `dashboard.html.j2`); portfolio table + modal CSS scoped to
    `#pf_section`; script tags updated (`watchlist.js?v=2`, `factor_exposure.js?v=2`,
    `watchstore.js?v=2`, `portfolio.js?v=1` added after watchstore).
  - FX auto-weights: `portfolio.js` pushes `{ticker->dollarValue}` to
    `window.FX.setAutoWeights()` after every render (factor exposure panel reflects actual
    book).
  - `watchlist.js` stale `auth.js` comments updated to `watchstore.js` (4 occurrences,
    comment-only, no code changes).
  - `site/watchlist.html` re-bakes at first nightly render (render-owned artifact).
  - Multi-list UI (primary-list sync, named-list switcher) unchanged — deferred to W2.5.
- **W2.5 — multi-list UI (deferred):** multi-list switcher requires `watchlist.js`
  parameterization before any list switcher ships: per-list localStorage keys, `listId`
  in `stateSig` + `storage-event` scoping, share-hash scoping. No UI ships until those
  seams are in place.
- **W3 (optional, Terminal repo):** portfolio UI parity in Terminal reading the same
  `portfolio_positions` rows. Out-of-repo lane, tracked here.
  - Terminal-side symbol aliasing note: futures aliases (`GC=F` → `GC_F`) and caret
    indices are unsupported in the Terminal symbol resolver. The macro site syncs verbatim
    tickers; the Terminal shows dash rows for unresolved symbols. Requires Terminal-side
    alias table before cross-app parity is complete.
- **W4 (optional, gated on billing decision):** wake `macro-quotes` Worker
  (`LIVE_QUOTES_URL`) for live prices on the dashboard; MNZ decides tier gating.
- Come-backs: first nightly after W2 (page renders from template change); MNZ W1
  email-confirm interaction (sync works for unconfirmed users today — re-test after
  email-confirm flips ON); Supabase CN-reachability check once first-party analytics can
  segment CN auth failures.

## 7. Non-goals

No sizing/allocation/advice; no engine or NW reads of user holdings (two-organisms law);
no per-user server rendering or web-app rewrite; no new auth provider; no operator held-risk
desk changes (stays in Mastermind per PRD §5–§9); no "validated" claims.
