# Mastermind Watchlist + Portfolio — W0 Commissioning Packet (by Fable)

Date: 2026-08-12
Status: W0 census + commissioning output. Product authority: `research/MASTERMIND_PORTFOLIO_WATCHLIST_CEO_REVAMP_HANDOFF_2026-08-12.md` (CEO handoff, committed alongside this packet).
Repos: `mastermindx-market-intelligence/macro` (this repo) + `mastermindx-market-intelligence/mastermind-terminal` (local checkout `/Users/chriswong/Documents/Cluade/charting-app`, default branch `master`).
Predecessor charters amended by this packet: `research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md` (UWP), `research/WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (WRI), `research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md` (PSI), `research/PSI_MARKET_BOOKS_DESIGN_SPEC.md`.
Governance: display-tier Portfolio Health Score remains lawful per `DNR:KILL-FUSED-COMPOSITE` Amendment 2 (2026-08-03) under PSI §3.1.2 conditions; it is NOT a blocker for this program (handoff §7.3). The `MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md` §10 open decision on watchlist identity is RESOLVED by the CEO handoff: **Watchlist ≠ Portfolio; two concepts, one canonical relational store each** (see §14).

---

## §0 ACCEPTANCE GATES (program-wide; every wave PR cites the rows it proves)

**Semantic invariants (non-negotiable, tested in W1 and never regressed):**
- A. Add AAPL to Watchlist `AI` → `portfolio_positions` unchanged.
- B. Add NVDA to Portfolio → no watchlist row changes.
- C. NVDA in both; remove from Watchlist → Portfolio position remains.
- D. Close Portfolio NVDA → Watchlist membership remains.

**Cross-product sync (W1 exit):**
- Create `Gold Miners` (NEM/AEM/GOLD) in Macro → identical list + membership in Terminal.
- Create `Space` (RKLB/ASTS) in Terminal → appears in Macro.
- Add a portfolio position in Macro → Terminal `/portfolio` shows it; and the reverse.
- Migration is additive, idempotent (run-twice test yields identical state), conflict-safe (same name → merge symbols, dedupe), owner-scoped; never mass-deletes cloud state; records a migration marker only on success.

**Anonymous funnel (W2 exit):**
- Precondition (P0 defect §2.7): the watchlist UI bundle is anonymously loadable — the regwall 401s on pure-UI JS are cured (graded data artifacts stay walled) and verified with a cookie-free fetch.
- Clean browser, no login: enter 8 tickers → real risk + per-ticker analysis renders; refresh → session persists locally; Save → signup → local state folds ONCE into the account (no duplicate rows).

**Large-list law (W2 exit; regression-tested thereafter):**
- 55 and 100 names: all rows present (DOM count == list count), no cap, no horizontal page scroll at 390px, search/filter responsive, per-name details hydrate progressively, one failed ticker degrades one row — never the table or page.

**Risk correctness fixture (W3 exit):**
- 8 correlated tech names + GLD + TLT: tech concentration visible; effective bets materially below ticker count; GLD/TLT read as diversifiers where the model says so; stress lens can show convergence; no unmodeled ticker silently enters factor math.

**Coverage honesty (W3/W4 exit):**
- US + crypto modeled names, HK/CN/CA positions, one unsupported symbol: never fabricate a cross-currency total; per-market signals work where a store exists; factor model states its market coverage; unsupported rows stay visible with an honest state.

**Visual gate (every UI wave; commissioning review, no self-merge):**
- Crops: desktop dark EN, desktop light EN, desktop ZH, 390px dark EN, 390px ZH.
- States: anonymous empty, anonymous analyzed, signed-in Portfolio, 55-name Watchlist, per-ticker drawer, Risk Center, Scenario Lab, offline/local.
- Real data, browser-driven interactions (not staged HTML). Terminal waves additionally verify 1440×900 / 820×1180 / 390×844 and run `npm run test:e2e:responsive`.

**Performance/resilience (every wave):**
- Shell paints before ticker hydration; quote calls batched; polling pauses when tab hidden; nightly artifacts cached; no per-user holdings in repo artifacts; never log shares/cost basis; owner-scoped RLS preserved.

**Copy/design law (every UI wave):**
- `docs/DESIGN_DOCTRINE.md` + frontend-design skill before surface work; no new token system, header family, or card grammar; no unexplained ENB/MCTR/WRI/lane vocabulary at glance tier; technical names live in tooltips/method detail; descriptive language only — no buy/sell/add/hedge imperatives; "validated" banned (CI-enforced); bilingual EN/ZH with zh copy in templates AND builders; no translated text in `title=` attributes.

---

## §1 Current-state truth table

All rows verified 2026-08-12 against macro `origin/main` (8e90bc669ed) and terminal `origin/master` (c1abc9a0, read via `git show` — the shared checkout is dirty with a sibling's live work and was never trusted).

### 1a. Persistent stores

| Store | Kind | Schema/RLS source of record | Writers | Readers | Notes |
|---|---|---|---|---|---|
| `watchlists` | Supabase (shared project `fsldfzlxyavsuwqbceod`) | Terminal `supabase/migrations/0001_init.sql` (owner policy `watchlists_owner`; unique `(user_id,name)`) | Macro `watchstore.js:125` auto-creates ONE list `'Watchlist'`; Terminal `terminal/page.tsx:61` seed-upserts `'Default'`. **No rename/delete path exists in either product** — Terminal list rename/delete/copy are localStorage-only (`TerminalShell.tsx:2234-2270`) | Macro `watchstore.js:113` (`.limit(1)` — first list only), macro brief fallback `app/main.py:1556` (service-role), Terminal `/terminal` + `/portfolio` pages, brain `get_watchlist` | Registered multi-list exists in schema, is unreachable from Macro, and is only half-reachable from Terminal (server lists render; only `Default` syncs) |
| `watchlist_symbols` | Supabase | Terminal `0001_init.sql` (`wls_via_parent` policy) | Macro `watchstore.js` fold `:222` / full-membership diff push `:277,:288` (insert+delete, single resolved list, debounced 600ms); Terminal seed + `POST /api/watchlist` add/remove/move (**first list only**, `route.ts:31`; remove/move batched ≤500 since #405) | Same set as above | `section`,`position` columns exist; **no note column** — Macro notes can never sync without a schema change |
| `portfolio_positions` | Supabase | **CREATE TABLE never version-controlled anywhere** (live since ≤2026-07-18); RLS only, in Macro `templates/uwp_supabase.sql` (4 own-row policies) | Macro `watchstore.js` full CRUD `:480-581` (client-direct under RLS, double `user_id` filter) | Macro brief positions-mode `app/main.py:1544` (service-role), brain tools | **Zero references in the entire Terminal tree** (`git grep portfolio_positions` = 0 hits) |
| `user_entitlements` | Supabase | Macro `scripts/deploy/0005_user_entitlements.sql` | billing | `_resolve_tier` → Pro gate on brief | Terminal `profiles.is_pro` is explicitly a UI hint only, trigger-locked |
| `mdash.watchlist.v1` | localStorage (macro origin) | shape `{v,updated,items:[{t,added,note}],order,settings}` | `watchlist.js:118` | `watchlist.js:112` | The anonymous/local watchlist AND the signed-in mirror; notes/order/settings live only here |
| `mdash.pf.v1` | localStorage (macro) | `{v,rows:[position-shaped]}` | `watchstore.js:353` | `:336` | Anonymous/local-mode portfolio; one-shot fold marker `mdash.watchstore.pf_folded.v1` |
| `mdash.book.v1` | localStorage (macro) | active book id | `market_books.js:182` | `:177` | Persisted market filter — silently shortens the rendered list (root cause §2.6b) |
| `mdash.fx_weights.v1`, `mdash.wl.seen.v1`, `mdash.watchstore.folded.v1` | localStorage (macro) | — | `factor_exposure.js:37` / `market_books.js:308` / `watchstore.js:237` | — | Manual factor weights fallback; seen-state snapshot; watchlist fold marker |
| `mm.wls` | localStorage (terminal origin) | `{lists:Record<name,{symbol,section}[]>, active, meta}` | `TerminalShell.tsx:1278` (sole writer) | Shell restore `:1215`, `PortfolioView.tsx:44,47` (read-only + storage event) | Named lists; **non-Default lists never touch Supabase**; guest seed = 6 hard-coded symbols |
| `mm.set`/`mm.setVersion`, `mm.flags`, `mm.railW`, `mm.devTier`, `mm.lastFlagColor` | localStorage (terminal) | — | `TerminalShell.tsx` | — | Watchlist display prefs / flags / rail width |
| `flowdesk.watchlist` | localStorage (terminal) | flat `string[]` | `FlowDeskView.tsx:112` | `:105` | **A second, unrelated watchlist system** (options-flow desk only). Out of scope — named here so nobody "unifies" it by accident |

Both products point at the same Supabase project (terminal-minted user JWTs authenticate against Macro's `/api/portfolio/brief` — same GoTrue issuer; UWP §2 records the shared `.mastermind-x.com` SSO cookie).

### 1b. Renderers

| Surface | Source | Population rendered |
|---|---|---|
| Macro `watchlist.html` | `templates/watchlist.html.j2` → `scripts/build_site.py:6337`; sole embedder of `wl_*`/`pf_*`/`bk_*`; 8 JS modules with hand-written `?v=N` (`:867-878`); nav entry = "Mastermind Portfolio" (`_navlinks.html.j2:228`) | Local blob (+ cloud-merged single list when signed in); portfolio section from `portfolio_positions`/`mdash.pf.v1`; WRI hero tile + always-open PRE-TRADE row (≥1 modeled holding); Account Sync bar `#wl_auth` |
| Terminal `/terminal` rail | `TerminalShell.tsx` | `mm.wls` named lists; `Default` reconciled with server (local order wins, server-only appended, local-only healed via idempotent add) |
| Terminal `/portfolio` | `app/(shell)/portfolio/page.tsx` + `PortfolioView.tsx` (`data-portfolio-watchlists="r5-v1"`, PR #386) | Sign-in-gated; server `watchlists`+`watchlist_symbols` merged display-only with `mm.wls`; ONE selected list → "Conviction Book" table ∩ `/data/manifest.json`; `PortfolioBriefPanel` above it fetches an unrelated population (§1c) |
| `committee.html.j2` | loads `watchstore.js?v=2` (stale stamp vs `v=3`) | Inert there (`watchstore.js:645` bails without host ids) — globals only |

### 1c. API / server surface

| Endpoint | Auth | Population | Notes |
|---|---|---|---|
| Macro `GET /api/portfolio/brief` (`app/main.py:1573`) | bearer → Supabase user; Pro gate (`pro|unlimited` + `active|trialing`) | Open `portfolio_positions` if any (real shares/entry), **else union of ALL the user's watchlists, equal-weight nulls** (`:1556-1569`) | GET-only, no parameters — caller cannot name a population; service-role reads bypass RLS with hand-written `user_id=eq.` filters; 300s per-user cache; composes nightly `site/data/portfolio_ctx.json` via `engine/portfolio_brief.compose_brief` |
| Terminal `GET /api/portfolio-brief` (proxy) | server-verified session; mints bearer server-side | forwards verbatim — no list identifier exists to forward | 5-min token-keyed cache; 401 handled locally; 403 `pro_required` → teaser state; upstream default `https://mastermind-x.com` |
| Terminal `POST /api/watchlist` | Supabase user | **first watchlist only** (`.order("position").limit(1).single()`) | actions add (single) / remove / move (batched ≤500) |
| Brain tools `get_watchlist` / `get_portfolio_brief` (`brain_gateway.py:2785,2887`) | user id / + Pro gate | duplicate the same positions-else-watchlist-union load logic | `get_watchlist` is NOT Pro-gated (own data — fine, noted) |
| Nightly `scripts/run_watchlist_sentinel.py` | operator only (`SUPABASE_OPERATOR_USER_ID`) | operator's own watchlist → `data/alerts/watchlist_alerts.jsonl` | **Per-user alerts do not exist yet** (W6 material) |
| Sync | — | — | No sync endpoints exist; Macro syncs client-direct via PostgREST under RLS, Terminal via its own route/server components |

### 1d. The population mismatch, stated once

On Terminal `/portfolio` today: the **brief** describes `portfolio_positions` if any exist, else ALL-lists-union equal-weight; the **table** describes ONE selected list (possibly a local-only list the server has never seen) filtered by the Terminal manifest. Four independent divergence mechanisms plus undisclosed weighting divergence — see §2.2. The handoff's question ("do `/api/portfolio/brief` and `PortfolioView` describe the same population?") is answered: **no, not even usually.**

### 1e. Live production reproduction (2026-08-12; page stamp "Generated 2026-08-12 06:37 UTC")

- **Section order (anonymous, DOM order):** aurora decor → site nav → panel [h1 "Watchlist & Portfolio" + search + count] → `#wri_rail` regime rail (hidden) → `#bk_strip` books → `#tod_strip` → `#wri_hero` **BOOK RISK** (braid + analytic cards + PRE-TRADE CHECK live inside it) → `#wl_auth` **ACCOUNT SYNC** → banner → `#pf_section` **Portfolio** → `#fx_panel` → controls → `#wl_list` **watchlist cards (dead last)** → empty-state → export/import. Matches `templates/watchlist.html.j2` exactly (prod is current). Signed-in: cards start ~1,206 px down, under a ~700 px risk hero — the CEO's screenshot hierarchy confirmed.
- **Anonymous = dead husk (root cause §2.7):** ten scripts 401 (`x-regwall: deny`, `{"locked":true,…,"signin_url":"/?signin=1"}`); `window.SD/WL/MB/FX` undefined; visible text is just the heading, "Portfolio ?", a nightly-close line, and Export/import. No empty state (should be `block`), no sign-in CTA. The shell itself is `cache-control: public, max-age=60`.
- **55/100-name run (production HTML + current templates + real R2 data):** 55/55 and 100/100 cards in DOM and visible; 0 dropped, 0 `wl-gone`, 0 console errors, 0 failed requests; `#wl_list` has no max-height/overflow clip. Payload measured: 5.65 MB (55) / ~10 MB (100) of per-ticker JSON on one load. The "cutoff" is §2.6(a)+(b): headline printed "YOUR 45 NAMES" over the 55-name book (10 unmodeled names silently absent from the headline; braid plots 45/55), and at 55+ names every braid axis label overlaps its neighbour (53/54 pairs, min gap −17.6 units; at 100: 97/98, −32.5).
- **PRE-TRADE CHECK:** absent for anonymous (JS never runs); signed-in shows an empty ticker box beside a hardcoded **$10,000** (`W4_DEFAULT_DOLLARS`, `watchlist_risk.js:940`) — the contextless default the handoff flags.
- **Terminal contrast:** anonymous `app.mastermind-x.com/portfolio` renders a proper benefits regwall ("FREE ACCOUNT — … Watchlists synced across your devices …" + create/sign-in CTAs). The Terminal already does what the Macro page fails to do pre-signup.
- **Freshness/caching:** the eight watchlist-bundle scripts carry hand-written `?v=N` stamps while the rest of the estate uses content hashes (`theme.js?v=e07e6c36`) — confirms §2.9. Caveat: harness used the repo's `factor_betas.json` (2026-07-09) because the live one is regwalled — coverage *set* may differ nightly; the headline/braid *mechanisms* are code-pinned and not affected.

## §2 Root-cause list (ranked; every item verified against origin/main + origin/master 2026-08-12)

1. **Terminal `/portfolio` has the wrong semantic source — confirmed, total.** `terminal/app/(shell)/portfolio/page.tsx:40-53` reads only `watchlists` + `watchlist_symbols`; `PortfolioView.tsx:90` titles it "Conviction Book"; `git grep portfolio_positions origin/master -- terminal/` returns **zero hits** across the entire Terminal tree. PSI §20 itself documents "Terminal has NO portfolio_positions awareness." UWP W3 (Terminal parity) was chartered optional and never shipped.
2. **The Portfolio Brief and the table under it can describe different populations — four independent mechanisms.** `/api/portfolio/brief` (`app/main.py:1573`, GET-only, no parameters) returns open `portfolio_positions` if any exist, else the **union of ALL the user's watchlists** equal-weight (`main.py:1556-1569`). The Terminal table renders **one selected list** — which can be a local-only `mm.wls` list invisible to the brief — then drops symbols missing from `/data/manifest.json` (`PortfolioView.tsx:75`). Weighting also diverges silently (real shares vs equal-weight nulls). Nothing on the page discloses which population either panel describes.
3. **Macro registered sync is single-list by construction.** `watchstore.js:112-133` resolves ONE list (`.limit(1)`, auto-created) and every downstream op targets that `wlId`; header comment pins "W1 scope: ticker sync only — notes/order/settings remain localStorage-only." Multi-list was deferred (UWP W2.5) with named preconditions and never resumed.
4. **Terminal watchlist truth is fragmented.** Server tables + `mm.wls` named lists (`TerminalShell.tsx:1216,1278`) reconcile **display-only** (`portfolioWatchlists.ts`), while `app/api/watchlist/route.ts:31` still targets the user's FIRST list (`.order("position").limit(1).single()`). Three partial authorities (Macro primary-list, Terminal locals, Supabase) reconcile forever — exactly what the handoff forbids.
5. **Page hierarchy is inverted and the identity is mashed.** The WRI hero tile (`watchlist.html.j2:686` `#wri_hero`) mounts book-risk + always-open PRE-TRADE CHECK row (once ≥1 modeled holding) above the user's names; the Account Sync bar `#wl_auth` was frozen "(unchanged)" by the Books spec §4; the nav already sells the page as "Mastermind Portfolio" while the page h1 says "Watchlist & Portfolio". Holdings read as bolted underneath the risk architecture.
6. **The 55-name "cutoff" is the risk hero misrepresenting the list — MEASURED, not the table dropping rows.** Live reproduction (production HTML + real R2 data): at 55 and at 100 names, **every card renders** — DOM count == blob count, zero console errors, zero failed fetches, no CSS clipping, no cap. What a user actually experiences:
   - **(a) The hero headline prints the factor-modeled subset as the user's list.** `watchlist_risk.js:762-767` renders `held.length` — `cvg.modeled` after `MB.modeledOnly()` + coverage stripping — as "YOUR **45** NAMES MOVE AS ABOUT 2 BETS" over a 55-name mixed book (10 names silently absent: GLD/EEM/ARKK, crypto, foreign). The card-level "not in the risk model" chip is honest; the largest type on the page is not.
   - **(b) The braid axis mathematically collides beyond ~37 names.** `paintBraid` (`watchlist_risk.js:1249`) spaces labels in a fixed 1000-unit viewBox: at 55 names, 53 of 54 adjacent labels overlap (min gap −17.6 units); at 100, 97 of 98 — an unreadable band that reads as "cut off". Legibility bound ≈ n ≤ 37.
7. **Anonymous production is a dead husk — P0 acquisition defect.** All ten watchlist-page scripts (`watchlist.js`, `watchstore.js`, `risk_core.js`, …) return **HTTP 401** from the regwall (`app/deploy/Caddyfile` `@reg_asset` default-deny; the allowlist names `theme.js account.js …` but none of the watchlist bundle; `tier_preview.js` — the promised locked-slot painter — is never loaded by this page). Anonymous visitors get a publicly-cached (`max-age=60`) shell with a heading, a "?" and an export widget: **no cards, no empty state, no sign-in CTA, zero console errors because nothing runs**. The walled files are pure UI; the graded data (`stockdata/*.json`) is walled separately — so the wall buys nothing and costs the entire pre-signup funnel the handoff §6 wants. Terminal's anonymous `/portfolio`, by contrast, renders a proper benefits regwall.
8. **Latent large-list fragilities (code-verified; not the live trigger at 55/100 on a healthy network — all fixed in W2 regardless):**
   - `watchlist_risk.js:1353-1364` `decorateCards()` fires `SD.loadTicker(t)` for every card at once (5.65 MB at 55 names, ~10 MB at 100 — measured); `stockdata.js:132-140` caches failures as `null` **permanently** (no retry/TTL) and caches values, not in-flight promises (double-fetch race).
   - `market_books.js:195` persisted active-book filter silently shortens the list with no partial-filter disclosure (`watchlist.js:190,202`).
   - `viewItems()` sort is O(n²) (`watchlist.js:214`); order-missing tickers silently sort first.
   - `watchstore.js:146-149` selects with no `.range()` → silent PostgREST row-cap + corrupt `maxPos` watermark (`:156`) at scale.
   - localStorage quota failure (`watchlist.js:116-122`) keeps the in-memory blob → list vanishes on reload.
   - `scheduleDecorate()` rAF latch (`watchlist_risk.js:1529`) never fires in hidden tabs — background-tab loads render undecorated until focus.
   - (No deliberate cap exists: the only `.slice(0,12)` is the search dropdown.)
9. **Deploy split-brain trap for every JS wave.** The six page JS files are plain-copy template/site pairs (live in ~3 min via VPS pull, CI-guarded) but their `?v=N` stamps are **hand-written** in `watchlist.html.j2:867-878` and only reach production via a render — so a JS body can go live minutes-to-hours before its stamp, and `site/watchlist.html` itself can lag the `.j2`.
10. **Governance drift froze the wrong identity.** Three charters pinned watchlist-page primacy (UWP-R1 "evolution of watchlist.html", PSI §13.1 "stays watchlist.html — NO new page", Books §4 `#wl_auth` "(unchanged)") while `MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md` §10.4 held the page's identity OPEN for Sol/Chairman. Nobody owned the product story; every program added a correct layer to an incoherent whole — precisely the failure mode the CEO handoff names.
11. **Quality-tier debt on the honest-null path.** `portfolio.js:387-392` drawer swallows lane-render throws (`catch(e){}` → empty section, no honesty line); `risk_core.js` `factorBets()` uses diagonal-only variance (acknowledged approximation) so the patch-bay and the book read can name different dominant factors for the same ticker.

## §3 Final state architecture

```
                       CANONICAL USER STATE (Supabase fsldfzlxyavsuwqbceod, owner-scoped RLS)
        ┌──────────────────────────────────────────────────────────────────────┐
        │ watchlists          (id, user_id, name, position, created_at)        │
        │ watchlist_symbols   (id, watchlist_id, symbol, section, position,…)  │
        │ portfolio_positions (id, user_id, ticker, shares, entry_price,       │
        │                      entry_date, notes, status, created_at, updated_at)│
        └───────────────┬──────────────────────────────┬───────────────────────┘
                        │                              │
              MACRO RENDERER                   TERMINAL RENDERER
       deep intelligence / acquisition          live operational UX
       watchlist.html ("Portfolio               /portfolio (positions only)
       Intelligence" + Watchlists mode)         watchlist contexts (rail, add-to)
                        │                              │
   local: per-list anonymous store +        local: mm.wls demoted to anonymous/
   offline cache + one-time fold-in         offline cache + one-time migration
```

- One Portfolio (`portfolio_positions`); US/CN/HK/CA/Crypto market books are **derived views**, never separate portfolios or rows (handoff §1.2). A `portfolios`/`portfolio_id` schema is explicitly out of scope.
- Registered watchlists: full multi-list CRUD against `watchlists`/`watchlist_symbols` from BOTH products through one service contract per repo; no `.limit(1)`/first-list behavior anywhere.
- Local stores are demoted to: anonymous persistence, offline cache, optimistic UI, one-time migration source (handoff §13). They are never a peer authority for registered users.
- Watchlist and Portfolio operations never implicitly mutate each other (gates A–D).
- UWP-R2 (two-organisms) stands: user holdings never feed the signal path, boards, rankers, Neural Web, or alerts-authority; all joins are client-side display tier.
- UWP-R5 stands: any RLS/policy change ships as SQL in the same PR (`templates/uwp_supabase.sql` lineage).
- UWP-R6 stands: page never breaks logged-out or with Supabase unreachable; sync state disclosed quietly ("Saved / Saving… / Local to this browser / Offline").
- **Schema authority ruling (new):** the Terminal repo's `supabase/migrations/` chain becomes the single schema+RLS source of record for all three user-state tables. W1b adds an idempotent migration recording the already-live `portfolio_positions` DDL+RLS (column types verified against live PostgREST introspection first — never inferred); Macro `templates/uwp_supabase.sql` gains a pointer header and stops being an independent authority. Fixes the current split where `watchlists` DDL lives in Terminal, `portfolio_positions` RLS lives in Macro, and no repo holds the CREATE TABLEs.
- **Six-job nav reconciliation (new):** the IA doc's six-job model keeps Monitor (watchlist) and Portfolio as separate jobs. One page serves both jobs via its two modes: nav "Portfolio" → `watchlist.html` (Portfolio mode default), nav Monitor's watchlist entry → `watchlist.html#watchlists` (Watchlists mode deep link). No URL changes (N0-compatible); the two jobs stay distinct in nav while sharing one workspace shell. Flagged to Sol in §11 since this supersedes IA §10.4's two-option framing.
- **Drawer vs canonical-page law (new, per design packet):** the per-ticker drawer is an in-workspace composition of already-baked artifacts and ALWAYS links out to the canonical detail pages (`stocks/<T>.html`, Terminal chart deep link). It never becomes a second competing ticker-detail page, and its anonymous tier must not leak board-tier Prophet signal (design packet red-team BLOCKER #1 class) — locked slices reuse the `.mx-tier-gate` shell.
- **Notes/order sync decision (new):** `watchlist_symbols` has no note column; W1 adopts the `position` column as cross-product order authority, and notes remain a Macro-local feature disclosed as "this device" until a deliberate schema wave adds a note column. No silent schema additions ride this program.

## §4 Supabase / local-state migration plan

Principles (handoff §13): additive, idempotent, conflict-safe, owner-scoped; same name → merge symbols; local-only list → create server list; server-only list → keep; dedupe symbols; preserve order best-effort; migration marker only on success; run-twice test required.

**Phase 0 — verification before any migration code (W1 preflight):**
1. Confirm both products' runtime envs point at project `fsldfzlxyavsuwqbceod` (Macro `theme.js` sb-config ref; Terminal `NEXT_PUBLIC_SUPABASE_URL`).
2. Introspect live column types of `portfolio_positions` via PostgREST (the DDL was never committed; §1a) — the recorded migration must match reality byte-for-byte, not the UWP doc's memory of it.
3. Confirm live RLS on all three tables matches `0001_init.sql` + `uwp_supabase.sql` (owner-scoped, via-parent).

**Schema acts (Terminal repo, per §3 schema-authority ruling):**
- New migration `supabase/migrations/000X_portfolio_positions.sql`: `CREATE TABLE IF NOT EXISTS public.portfolio_positions (...verified live shape...)`, `ENABLE ROW LEVEL SECURITY`, and the four own-row policies copied verbatim from `templates/uwp_supabase.sql` (wrapped idempotently) — a no-op against live prod, but the schema finally has a home. Macro's `uwp_supabase.sql` gets a pointer header in the same program (W1a).
- No new tables, no `portfolios`/`portfolio_id`, no note column, no `watchlists.updated_at` — zero schema drift beyond recording reality.

**Macro local → server (W1a, evolving the shipped fold):**
- `mdash.watchlist.v1` fold (marker `mdash.watchstore.folded.v1`, skip-marking-on-empty — both behaviors kept) retargets from "the first list" to "the list named `'Watchlist'`" (created if absent). Same one-shot semantics; existing folded users are unaffected.
- Registered mode becomes per-list: cache keys `mdash.wl.<listId>.v1`; `mdash.watchlist.v1` remains the anonymous store unchanged (zero risk to signed-out users). `listId` enters `stateSig` and storage-event scoping per the UWP W2.5 checklist.
- The push diff (insert missing / delete absent) becomes strictly list-scoped: a delete may only ever target rows of the list currently being pushed — the full-membership diff must never see another list's rows. (Regression risk named in §11.)
- `mdash.pf.v1` → `portfolio_positions` fold: already shipped (`pf_folded.v1`); unchanged.

**Terminal local → server (W1b):**
- One-time additive migration on signed-in mount when `mm.wls.migrated.v1` marker is absent. For each non-`Default` local list: find server list by exact name → create if absent (`position` = max+1) → insert missing symbols preserving `section` and local order into `position`; dedupe by symbol. Never delete or rename server rows. Server-only lists are kept. `Default` keeps its existing reconcile semantics exactly (TRAP-1 mount-side and guest→signed-in transitions preserved as-is).
- Marker is a per-list success map; a partially-failed migration retries only the failed lists on next mount (idempotent by construction — merge-by-name + insert-missing).
- After migration, signed-in named lists are server-backed with `mm.wls` demoted to optimistic cache + guest store; `resolvePortfolioWatchlists`'s local-wins merge logic is retired from `/portfolio` (the page stops rendering watchlists at all in W5) and survives only as the guest-mode shell reconciler.
- Anonymous Terminal users keep `mm.wls` exactly as today.

**Collision rules (both repos, tested):** same name → merge symbols (dedupe; server `position` wins for existing rows, local-only rows append in local order); local-only list → create; server-only list → keep. Name comparison is exact (the schema's unique `(user_id,name)` is case-sensitive); no fuzzy matching.

**Tests:** run-twice-same-result (both repos); interleaved-writer test (Macro fold + Terminal migration on the same account converge without dupes); the §0 semantic invariants A–D run against the migrated state.

## §5 Macro IA wireframe (target)

```
[shared _site_nav header — unchanged family]

PORTFOLIO INTELLIGENCE                    state chip: Saved | Saving… | Local to this browser | Offline
[ Portfolio ] [ Watchlists ]              anonymous CTA: “Save + get alerts — Free” (after analysis)

— Anonymous default: ANALYZE A PORTFOLIO —
  paste/multi-add entry: “AAPL, MSFT, NVDA, GLD, TLT” or “AAPL 20% …”
  weighting mode stated explicitly: equal | % | $ | shares  →  [Analyze]

— PORTFOLIO mode (signed-in default with holdings) —
  BOOK READ (one card): N positions · $tracked (only when real sizes) · effective ~K bets
    · biggest modeled risk driver (plain words) · market state · coverage disclosure
  WHAT NEEDS ATTENTION (deterministic stack, ≤5 rows, precedence:
    1 high risk-contribution + elevated checks · 2 event in critical window
    · 3 elevated check on material position · 4 major status transition · 5 context)
  HOLDINGS TABLE (main work surface, dense, virtualize only if needed):
    Symbol/Name | Value/Weight | Day | Since entry | Signal/Stage | Risk contrib | Attention | Next event | ⌄
    row ⌄ → PER-TICKER INTELLIGENCE DRAWER (Tier 1 instant read; Tier 2 structured:
      price/technical · portfolio role · events · estimates · fundamentals/balance-sheet
      · ownership/selling · options/positioning · macro sensitivity · sector/theme
      · news/company intelligence · links: dossier / open in Terminal)
  RISK CENTER (tabs, one dominant idea per tab):
    Concentration | Correlation | Factors & Macro | Stress | Events | Weak links & Strengths
    └ Scenario Lab (collapsed; “What happens if I add this?”; explains its default sizing)
  MARKET BOOKS: US/CN/HK/CA/Crypto chips = derived views of the ONE portfolio; never mixed-currency totals

— WATCHLISTS mode —
  [ AI Infrastructure ▾ ] [+ New list]   ·  32 names · 4 changed since last visit · 3 earnings this week
  WATCHLIST TABLE: Symbol | Last/Day | Signal/Stage | Risk flags | Next event | Sector/Theme | Δ since visit | ⌄
  [Analyze this Watchlist] → labeled “Watchlist structure — equal weighted” (Risk Center reuse; explicit label;
    optional explicit action: Convert selected names to Portfolio)
```

Deleted/demoted from the current page: see §12.

## §6 Terminal IA wireframe (target)

```
/portfolio  — REAL portfolio (portfolio_positions), no watchlist pills:
  KPI strip: value · day P&L · since-entry · effective bets (from brief where covered)
  PortfolioBriefPanel — MUST describe the same holdings as the table below
  POSITIONS TABLE: live quotes · day/since-entry · chart deep links · edit/close · add-position
  Add Position modal: ticker (+ optional shares/entry price/date/notes); unsized position allowed and labeled

Rail (charting):  [ Portfolio ] [ Watchlists ] toggle — separate sources, never serialized into mm.wls
  MY PORTFOLIO: AAPL / NVDA / GLD …          (fast chart navigation)
  WATCHLISTS: Default / AI Infra / …          (watchlist selection lives HERE, not on /portfolio)

Add to… (search / chart / context menu):
  Portfolio            ← visually separated; opens compact position modal
  ────────────
  Default / AI Infra / Gold Miners / Earnings / + New Watchlist   ← no position fields
```

## §7 PR / wave sequence

| Wave | Repo | Scope | Depends on |
|---|---|---|---|
| W0 (this PR) | macro | Census + commissioning packet + handoff committed; no production UI | — |
| W1a | macro | Canonical multi-watchlist registered store (`watchstore.js` seam, no first-list-only), per-list local keys, fold-in migration + run-twice tests; portfolio service seam exported cleanly | W0 |
| W1b | terminal | Canonical registered watchlist adapter; `mm.wls` custom-list migration (additive/idempotent); anonymous local preserved; drop first-list server behavior | W0 (parallel with W1a; contract agreed in W0) |
| W2 | macro | Flagship workspace shell: Portfolio ǀ Watchlists switch, holdings/watchlist dense tables, Account-Sync panel deleted → header save state, anonymous bulk-entry funnel. MOCKUP GATE before build; commissioning review before merge | W1a |
| W5 | terminal | `/portfolio` → `portfolio_positions` consumer; watchlist switcher removed from the page; live values; portfolio CRUD; Add-to split (Portfolio vs Watchlist); rail toggle | W1b (parallel with W2 — different repo/lane) |
| W3 | macro | Risk Center reorganization over existing engines (risk_core, factor model, stress lens, market books); Scenario Lab rehomed collapsed | W2 |
| W4 | macro | Per-ticker Intelligence Drawer composing portfolio_ctx v2 + stockdata + WRI + options + news + Company Intelligence + transmission + themes; honest tier degradation | W2 (enriched by W3) |
| W6 | both | Retention: change history, change-triggered digest, status alerts, “since your last visit”, Portfolio Brief v2; optional Health Score per DNR amendment | W2–W5 |

Discipline: one wave = one session = one reviewable PR per repo (macro PRs armed `merge-on-green`; terminal PRs follow that repo's delivery chain). No 10,000-line PR. Flagship UI waves return crops to the commissioning session before merge.

## §8 Files expected to change per wave

**W1a (macro):** `templates/watchstore.js` (multi-list CRUD, list-scoped push, per-list caches, fold retarget); `templates/watchlist.js` (parameterization seams only — `listId` in `stateSig`, storage-event scoping; no UI change); `templates/uwp_supabase.sql` (pointer header); `scripts/build_site.py` (add `watchstore.js`/`portfolio.js`/`market_books.js` to the asset-copy loop `:4744-4770`; fix stale `watchlist_supabase.sql` ref `:4735`); `config.yml:2828` (same stale ref); `WATCHLIST.md` (rewrite to current truth); node-shelled tests (multi-list CRUD isolation, fold idempotency ×2, list-scoped delete); paired `site/` copies via `python -m scripts.check_template_site_sync --fix`.

**W1b (terminal):** `supabase/migrations/000X_portfolio_positions.sql` (recorded DDL+RLS); new `terminal/lib/watchlists.ts` (canonical service: list CRUD incl. create/rename/delete server rows, symbol ops by list id); `terminal/app/api/watchlist/route.ts` (list-targeted actions; batched add parity; list CRUD); `terminal/components/TerminalShell.tsx` (server-backed signed-in lists + `mm.wls` migration + marker); `terminal/lib/portfolioWatchlists.ts` (reduce to guest shell reconciler); e2e: extend `watchlist-bulk-actions.spec.ts` coverage + new sync/migration spec; `terminal/lib/i18n.tsx` (new LEX keys).

**W2 (macro flagship shell):** `templates/watchlist.html.j2` (IA rebuild: two modes, header state chip, `#wl_auth` panel removed, dense tables markup, anonymous bulk entry); `templates/watchlist.js` (table renderer, modes, O(n²) sort fix, bulk-entry parser); `templates/stockdata.js` (bounded-concurrency fan-out + TTL'd negative cache — required for the W2 large-list gate); `templates/watchlist_risk.js` (`decorateCards` batching); `templates/portfolio.js` (cockpit composition + drawer honesty line on lane failure); `templates/watchstore.js` (save-state chip events); `templates/market_books.js` (book chips row); `?v=` bumps in the `.j2` for every touched JS; `app/deploy/Caddyfile` `@reg_asset` allowlist + `app/regwall.py` (cure the anonymous 401 husk — UI JS only, graded data stays walled; §2.7 — an operator-approvable slice of this may ship earlier as a hotfix); `mockups/refs/psi/workspace/` (mockup-gate crops committed BEFORE builder spawn); paired `site/` copies; zh copy in template and any builder-injected strings.

**W5 (terminal portfolio correction):** `terminal/app/(shell)/portfolio/page.tsx` (reads `portfolio_positions`); `terminal/components/PortfolioView.tsx` (positions table; watchlist switcher removed); new `terminal/app/api/portfolio/route.ts` (position CRUD) or direct RLS'd server-client writes matching the watchlist pattern; `terminal/components/PortfolioBriefPanel.tsx` (same-population binding note + disclosure line); `terminal/components/SearchModal.tsx` + `TerminalShell.tsx` ("Add to…" split: Portfolio modal vs watchlist picker; rail `[Portfolio|Watchlists]` toggle); e2e: new portfolio spec + `test:e2e:responsive`; LEX keys.

**W3 (macro risk center):** `templates/watchlist_risk.js` (tabbed Risk Center presentation; Scenario Lab rehome collapsed); `templates/risk_core.js` (no math changes; `factorBets` diagonal-only caveat surfaced or upgraded); `templates/watchlist.html.j2` (risk-center section swap); `templates/factor_exposure.js` (panel rehome).

**W4 (macro drawer):** `templates/portfolio.js` + `templates/watchlist_risk.js` (drawer shell composing ctx v2/stockdata/WRI/options-when-wired/news/CI/transmission/themes; tier degradation; canonical-page links; Terminal deep-link route verified, never guessed); `scripts/build_portfolio_ctx.py` only if a cheap missing field is required (default: no).

**W6 (retention):** `engine/portfolio_brief.py` (v2 fields per PSI §5.2); digest/alerts surfaces (`app/mailer.py` path per PSI §19.5); per-user sentinel decision (today operator-only); optional Health Score behind PSI §12 prereg.

## §9 New vs reused engines

**REUSED AS-IS (inventory verified against code, not doc claims):**
- `templates/risk_core.js` — all ten claimed capabilities confirmed present (factor betas, book variance, factor variance shares, idio risk, ENB, pairwise implied ρ, twin clusters at 0.70, per-position MCTR, calm/stress lens, coverage abstention >40% unmodeled) plus `whatIf` and `factorBets`.
- `templates/watchlist_risk.js` — nine per-name lanes (price/trend, stretch, events, estimates, balance sheet, selling/ownership, rate sensitivity, transmission chains, role ladder), `laneRows`/`chainRows`/`roleBadge` drawer helpers.
- `templates/portfolio.js` position drawer + CRUD UI; `templates/market_books.js` `marketOf()` derived views (already exactly the CEO's "books are views" law); `templates/factor_exposure.js` + `engine/factor_exposure.py` (`factor_betas.json`, `factor_cov_stress`); `scripts/build_portfolio_ctx.py` (ctx v1 live, v2 per PSI §5.1); `engine/portfolio_brief.py`; five per-market stock stores + `data_base.js` CDN rewrite; options plane, ticker news, Company Intelligence, transmission chains (drawer sources).
- Terminal: `TerminalShell` watchlist model + `SearchModal` add-to picker + `watchlistSelection.ts` bulk helpers (#405); `portfolioWatchlists.ts` merge logic (as the migration's reference semantics); `PortfolioBriefPanel` (rebound, not rebuilt); `SignupGate`; quote hub for live values; e2e responsive suite.
- Supabase substrate: `watchlists`/`watchlist_symbols` schema + RLS (`supabase/migrations/0001_init.sql`: owner policy + via-parent policy), `portfolio_positions` schema + RLS (`templates/uwp_supabase.sql`).

**MODIFIED (the seams — this is where W1 lives):**
- `templates/watchstore.js`: registered **multi-list** CRUD (retire `resolvePrimaryList()` soloism); widen sync beyond ticker-only (notes/order round-trip decision recorded in W1); clean exported portfolio service seam.
- `templates/watchlist.js`: UWP W2.5 parameterization checklist (per-list local keys, `listId` in `stateSig` + storage-event scoping, share-hash scoping); O(n²) sort fix; dense-table rendering.
- `templates/stockdata.js`: bounded-concurrency batched fan-out + TTL'd negative cache (kills root-cause 6a).
- Terminal `app/api/watchlist/route.ts`: named-list targeting (list id), batched `add` parity, server-side list create/rename/delete (today: none exists).
- Terminal `TerminalShell.tsx`: signed-in named lists become server-backed with `mm.wls` as optimistic cache + one-time additive migration; guest behavior unchanged.
- Terminal `/portfolio` page + `PortfolioView.tsx`: `portfolio_positions` consumer via the same RLS'd server-client pattern the page already uses for watchlists; watchlist switcher removed; plus a small positions CRUD route.
- Macro `/api/portfolio/brief`: adds explicit population disclosure (`mode: positions | watchlist_union`) so no consumer can ever silently mix populations again.

**NEW (small, composed — no new estimators):**
- Cross-repo watchlist/portfolio service contract doc + a Terminal migration recording the already-live `portfolio_positions` DDL idempotently (fixes the split schema authority; one source of truth going forward).
- Deterministic "What needs attention" stack (precedence rules over existing lane/risk outputs; no weights, no composite).
- Scenario Lab shell (rehomes existing `whatIf`); anonymous bulk-entry parser (paste list, optional weights); per-ticker Intelligence Drawer shell (composes existing artifacts; always links out to canonical detail pages).

**FORBIDDEN NEW:** optimizer/recommended sizing (WRI-R3 stands); new estimators (WRI-R2); `portfolios` table / `portfolio_id` (handoff §1.2); new token/header/card systems; LLM legs in any score (PSI §3.1.2); engine reads of user holdings (UWP-R2).

## §10 Acceptance matrix

§0 gates mapped per wave (W1: semantic invariants + sync + migration idempotency; W2: funnel + large-list + visual; W3: risk fixture + coverage; W4: drawer + tier degradation; W5: terminal population correction + CRUD isolation re-run; W6: retention flows). Full state table lives in §0.

## §11 Risks / collision check

**Collisions (checked 2026-08-12):**
- Macro: no open PRs and no sibling worktrees on this estate; ACTIVE_BUILD_MAP shows the two adjacent PSI lanes (#4897 market books, #4887 ctx v2) SHIPPED. CXI adjudication search: no conflicting rulings.
- Terminal: zero open PRs right now, but the estate is HOT — 15 watchlist PRs merged in ~5 weeks, two TODAY (#404 ext %, #405 bulk actions), and an uncommitted mobile-responsive overhaul is live in the shared checkout. Terminal waves MUST branch from fresh `origin/master` in an isolated `.claude/worktrees/` worktree (`claude/*` branch) and re-census `TerminalShell.tsx` at wave start.
- Operation Institutionalize: Sol is reconciling handoffs A–D into a Wave-1 decision packet. This program **supersedes IA §10.4** (watchlist identity) by direct CEO ruling and builds the Macro portfolio surface the IA doc deferred ("until a Macro-side portfolio surface earns its place"). The W0 PR body flags both so Sol's Wave-1 reconciliation ingests this resolution instead of colliding with it. If institutionalize PR-0 foundations (type ramp, `.empty-why`, display-tier stage field) have not landed when W2 starts, W2 composes existing `theme.css`/`.mx-tier-*` primitives and does NOT mint parallel ones.

**Product/design risks:**
- **P0 live defect found in W0 (§2.7):** anonymous `watchlist.html` is a dead husk — the regwall 401s the page's own UI bundle. Any fix touches entitlement policy (`Caddyfile` §"HTML documents are OPEN", operator 2026-08-04), so the cure is an operator-visible change: allowlist the pure-UI files (or load `tier_preview.js` on this page) while graded data stays walled. Chipped for an out-of-band hotfix decision; otherwise it lands with W2's funnel work. Until cured, every anonymous visitor sees a blank product.
- Drawer leak class (design packet red-team BLOCKER #1): anonymous drawer tiers must not expose board-tier Prophet signal; reuse `.mx-tier-gate` lock shells. Count-ladder signature is reserved to the Board archetype — the holdings tables must NOT borrow it.
- Day-change columns: Books spec v1.1 correctly omitted day % (index field `a` is alpha-z, not day change) and the `macro-quotes` Worker is dormant (billing decision). W2 ships Day columns as honest "—"/absent until a quotes decision; never fake it from stale fields.
- Terminal symbol aliasing gap: futures aliases (`GC=F` → `GC_F`) unsupported in the Terminal resolver; Macro syncs verbatim tickers → Terminal dash rows. Cross-product acceptance includes one such symbol.
- Supabase CN reachability (UWP §3 watch item): degrade-to-local must be genuinely silent in CN; the save-state chip is the only disclosure.
- Free-tier coherence: the brief is Pro-gated (matches handoff §19 paid tier), so free/anonymous KPIs on both surfaces must be computable client-side (risk_core over positions) — the page must feel real for free users without the brief.

**Engineering traps (named so wave builders inherit them):**
- Deploy split-brain: JS bodies are plain-copy pairs (live in ~3 min) but `?v=` stamps are hand-written in the `.j2` and wait for a render — every JS wave bumps stamps in the same PR and expects the two-speed window; `committee.html.j2` carries a stale `watchstore.js?v=2` to align or scope.
- `build_site.py` asset-copy loop omits `watchstore.js`/`portfolio.js`/`market_books.js` (they ship only as committed pairs) — W1a adds them for render self-heal consistency.
- Macro push is a full-membership diff that DELETES cloud rows absent locally — under multi-list it must be strictly list-scoped or a stale cache can wipe a sibling list (named regression test in W1a).
- Permanent negative ticker cache (`stockdata.js:132-140`) + unbatched 55–100-way fan-out is the load-dependent row-killer; fix ships in W2 with the large-list gate.
- Persisted `mdash.book.v1` filter silently shortens lists — W2 adds the partial-filter disclosure line ("Showing 12 of 55 — US book").
- `mm.wls` TRAP-1 semantics (mount-side reconcile + guest→signed-in overwrite) are load-bearing; the W1b migration preserves them exactly for `Default`.
- Terminal `watchlists` rows have no rename/delete anywhere → local renames have already diverged names from server rows; migration merges by exact name and never auto-deletes.
- `TERMINAL_E2E_FIXTURE` env flag drives deterministic e2e — new specs use it rather than live Supabase.
- Stale schema references (`config.yml:2828`, `build_site.py:4735`, `WATCHLIST.md:58` → nonexistent `watchlist_supabase.sql`) get fixed in W1a before they mislead a builder.
- "Portfolio" naming collision across the estate: Terminal Conviction Book (dies in W5), Macro `portfolio_brief.v1`, and the separate paper-trading Mastermind repo — copy and docs must never conflate them (cross-repo boundary audit 2026-08-11).

## §12 Explicit deletions / demotions from the current page

| Current element | Ruling |
|---|---|
| ACCOUNT SYNC panel | DELETED as a first-level panel → quiet header state chip + anonymous save CTA (handoff §3.8/§14) |
| PRE-TRADE CHECK in hero | DEMOTED → “Scenario Lab”, collapsed, inside Risk Center; engine (RiskCore.whatIf) retained; default sizing explained (§3.7/§15) |
| Giant factor/correlation patch-bay as page hero | DEMOTED → secondary visualization inside Risk Center Correlation tab, only if it aids comprehension (§8B) |
| Watchlist card wall as default layout | REPLACED → dense table default at 55–100 names; cards possible later as optional view (§9) |
| “Watchlist & Portfolio” mashed single-scroll identity | REPLACED → Portfolio ǀ Watchlists workspace switch; no duplicate content in one scroll (§5.1, §17.7) |
| Methodology-first hierarchy | INVERTED → holdings lead; diagnostics explain; no always-open methodology (§4, §17) |
| Raw internal vocabulary at glance tier (ENB/MCTR/WRI/lane) | DEMOTED → tooltips/method detail only (§17.8–9) |

## §13 Wave spawn prompts (commissioning template — gates travel INLINE, never by pointer)

Each wave session receives: (1) this packet's path + the CEO handoff path; (2) the §0 gate rows it must prove, restated inline; (3) the §8 file list; (4) the §11 traps for its repo; (5) the §14 amendments it implements. Builds route per Macro CLAUDE.md §Model routing (Opus `builder` builds; `designer` designs; commissioning session reviews — no self-merge on flagship UI).

**W1a prompt core (macro, Opus builder):** "Implement registered multi-watchlist in `templates/watchstore.js` + parameterization seams in `templates/watchlist.js` per packet §4/§8. NOT DONE UNLESS: semantic invariants A–D pass as node-shelled tests; fold retarget is idempotent (run-twice test); push deletes are provably list-scoped (test: two lists, stale cache of list A cannot delete rows of list B); anonymous behavior byte-identical (no UI change); `build_site.py` copy-loop + stale-ref fixes land; paired site/ copies ship byte-identical; zh untouched. Traps: full-diff delete (§11), fold markers skip-on-empty, `?v=` bump discipline."
**W1b prompt core (terminal, Opus builder):** "Create `terminal/lib/watchlists.ts` canonical service + list-targeted `/api/watchlist` + `mm.wls` one-time additive migration per packet §4. NOT DONE UNLESS: migration run-twice test yields identical server state; TRAP-1 Default semantics preserved (existing e2e green); server list create/rename/delete exists and is owner-scoped; guest mode untouched; `npm run test:e2e:responsive` green at 1440/820/390; migration marker is a per-list success map. Traps: never delete/rename server rows during migration; exact-name merge; `TERMINAL_E2E_FIXTURE` for determinism; branch fresh off `origin/master` in an isolated worktree."
**W2 (macro, designer → builder):** commissioned only after the MOCKUP GATE — the commissioning session produces light+dark+zh, desktop+390 mockups committed under `mockups/refs/psi/workspace/` and the design is pinned in the spawn prompt as exact markup/CSS. Gate rows: anonymous funnel, large-list 55/100 (incl. the §2.6 fan-out fix), visual matrix, save-state chip, Account-Sync deletion.
**W5 (terminal, Opus builder):** drafted at wave start against a fresh Terminal census; gate rows: `/portfolio` renders `portfolio_positions` only; switcher removed; brief panel population disclosure; CRUD isolation invariants re-run; responsive matrix.
**W3/W4/W6:** drafted at their wave starts from this packet's §7/§8 scope lines (W3 risk-center presentation over unchanged math; W4 drawer composition with tier honesty; W6 retention per PSI §19 seams).

## §14 Amendments to prior rulings (of record; predecessor docs stay in place with this packet as the newer authority)

- **A1 — UWP-R1 (placement) amended:** the URL stays `watchlist.html` (compatibility) and per-user state stays Supabase+RLS (unchanged), but the page identity becomes the two-mode "Portfolio Intelligence / Watchlists" workspace with holdings-first hierarchy. The one-scroll "unified dashboard" composition is superseded.
- **A2 — UWP W2.5 ("multi-list UI deferred") superseded:** multi-list registered watchlists are W1a scope; UWP's own preconditions (per-list localStorage keys, `listId` in `stateSig` + storage-event scoping, share-hash scoping) become the implementation checklist.
- **A3 — UWP W3 ("optional Terminal portfolio parity") superseded:** Terminal `/portfolio` reading `portfolio_positions` is REQUIRED (handoff §12.1) — W5.
- **A4 — WRI-R3 substance stands, placement superseded:** the what-if diagnostic stays descriptive-only (no optimizer, no sizing advice; the 2026-07-24 operator sign-off remains its display authorization), but it rehomes as "Scenario Lab", collapsed, inside the Risk Center (handoff §15). WRI's page-primacy premise ("revamp watchlist.html" as risk-first) is superseded by holdings-first IA.
- **A5 — PSI §13.1 ("stays watchlist.html — NO new page"):** survives as a no-new-URL rule; the page composition it froze is superseded. PSI §2's claims table is corrected of record: the "Terminal Portfolio page ✅ live" row described a watchlist-derived Conviction Book, not a portfolio; `portfolio_positions` has zero Terminal references (§1a).
- **A6 — PSI Books spec §4 `#wl_auth "(unchanged)"` superseded:** the Account Sync panel is deleted; the UWP-R6 disclosure obligation moves to the header save-state chip (Saved / Saving… / Local to this browser / Offline). The Books derived-view model itself (marketOf, FX-corruption guard, no cross-currency totals) is REAFFIRMED — it is the CEO's §1.2 law already implemented.
- **A7 — `MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md` §10.4 (watchlist identity, reserved to Sol/Chairman) resolved by the CEO handoff:** Watchlist = attention set, Portfolio = held positions, separate concepts, one canonical relational store each; the Macro page is authorized as the deep-analysis portfolio surface the IA doc had deferred. The six-job nav is honored via two nav entries → two modes of one URL (§3). PRODUCT_EXPERIENCE_CENSUS §1.4 "watchlist duality" closes the same way: Macro = deep analysis + acquisition, Terminal = live operations, one state.
- **A8 — Population disclosure law (new):** any surface composing the portfolio brief must state the population mode it received (`positions` vs `watchlist_union`), and equal-weight watchlist analysis is always labeled "Watchlist structure — equal weighted" (handoff §11.2). No consumer may silently mix populations again.
