# Stock Dashboard V3.6 / V3.6.1 — Canada production acceptance record (2026-08-25)

Session: Fable COO, `WS:PROPHET-HK-CA-REVAMP` presentation lane continuation
(commission: resume Stock Dashboard V3.6 regional rollout; Sol Skillpack pin
`mastermindx-market-intelligence/Mastermind@4d323d03e4151449a4b76abfdfefca1d56825fde`,
re-pinned and verified equal at session start).

## What this record is

The Canada V3.6 pilot was left `BUILT_NOT_PROVEN` by
`agentos/handoffs/PROPHET-HK-CA-REVAMP-2026-08-23.md` with two proof legs owed:

1. **Release identity** — the production VPS serves a main descendant containing
   the Canada V3.6 merge (and, after #6327, the V3.6.1 hierarchy correction).
2. **Signed-in browser matrix** — the entitled Canada production journey
   (dark/light · EN/ZH · desktop/390px · hierarchy · filters · live quotes ·
   clocks · Terminal routing · no duplicate board · no console errors).

This record settles leg 1 with receipts, records the lawful anonymous-state
observations, and states the exact remaining gate for leg 2.

## Leg 1 — release identity: **PASS (2026-08-25T0Z probe)**

Probe path: `config/production_topology.yml` (`repositories[id=macro]`):
`deployed_probe` = git HEAD of `/opt/macro`; `runtime_probe` =
`http://127.0.0.1:8000/api/health` `.commit`/`.checkout`.

| Check | Result |
|---|---|
| `/opt/macro` HEAD (ssh, deploy key) | `ce4a33aeeed779530942560c5b05f4df8ab0306c` |
| `origin/main` at probe time | `ce4a33aeeed779530942560c5b05f4df8ab0306c` (identical) |
| `api/health` | `{"status":"ok","commit":"2cfc5c73bd0","checkout":"ce4a33aeeed"}` — checkout matches deployed HEAD |
| #6315 merge `b14f1f4186a84e8dead509692934aed38c0dab0e` ancestor of deployed HEAD | `git merge-base --is-ancestor` → **yes** |
| #6327 merge `5a8f6a5aa98b0bb25110aec35e3c45aa80f9e42a` ancestor of deployed HEAD | `git merge-base --is-ancestor` → **yes** |
| Served page → loader chain (bytes on VPS) | `site/canada_stocks.html` references `dashboard-icons.js?v=d72d8b14`; `site/dashboard-icons.js` contains the strict Canada-only loader for `canada-stock-v36.js?v=20260823` |
| V3.6.1 hierarchy in deployed composer bytes | `buildShell` order = header → `#ca-v36-leading` → `#ca-v36-prophet` → Theme & Sector Leadership → Research tools (Prophet-first, per #6327) |
| Zero-state copy demotion in deployed bytes | `if (fresh)` — fresh-signal sentence renders only when count > 0 |

The running API process (`commit 2cfc5c73bd0`) also contains #6315/#6327
ancestry; static assets are in any case served from the checkout, so page/JS
delivery rides the checkout identity, which is exact.

## Access-boundary facts established (load-bearing for any regional follower)

- `canada-stock-v36.js` → **401 anonymous** (default-deny registered asset;
  entitlement = Supabase account via `/api/regwall/check`, plus `site_full`
  via `/api/paywall/check` when `PAYWALL_ENABLED=1`). This is the reviewed
  boundary the 08-23 handoff ordered preserved; it is intact.
- `dashboard-icons.js` → **public + `@public_versioned` immutable** (Caddyfile
  public allowlist). Correct: the loader carries no data; the composer does.
- Every `*.html` shell is public (operator 2026-08-04 ruling), so the V3.6
  experience is an **entitled-session progressive enhancement**: anonymous
  visitors get the legacy page by design. The same split will apply to a future
  `hk-stock-v36.js` automatically (unlisted JS is default-deny).

## Anonymous-state observations (in-app browser, 2026-08-25)

- Legacy Canada page fully functional anonymously: Act-Now sector lanes
  populated (data through 2026-08-21, built 2026-08-24 13:12Z per header),
  10 `.pvcard` Prophet cards, no horizontal overflow, no duplicate board.
- V3.6 composer correctly did **not** engage (script 401 → progressive
  fallback held). This is the designed degraded journey and it is healthy.
- Nonblocking observation: the anonymous console shows the 401 plus a
  strict-MIME refusal line for the gated script (the 401 body is JSON).
  Every anonymous visitor logs these. Harmless, but if a quieter anonymous
  console is ever wanted, the loader would need an entitlement-aware guard —
  **do not** solve it by making the composer public (standing do_not_redo).

## Leg 2 — signed-in browser matrix: **NOT YET RUN (blocked on entitled session)**

An entitled session cannot be lawfully created by an autonomous agent session:
credential entry is prohibited, the Claude-in-Chrome extension (the house
pattern used for the BioCatalyst P1-1 entitled acceptance, 2026-08-22) was not
connected at any point in this session (`list_connected_browsers` → `[]`,
retried across several hours), and no reviewed non-credential probe path for
entitled assets exists (correctly — the boundary is the product).

**Operator lever (either):**
1. Open Chrome, sign into the Claude-in-Chrome extension side panel, and start
   (or resume) a session commissioned to run the matrix below; or
2. Run the matrix manually and hand the session dated screenshots.

**The owed matrix (unchanged from the 08-23 handoff, now against V3.6.1):**
entitled `canada_stocks.html` → exactly one board (no legacy duplicate);
hierarchy Header → Leading Now → Prophet → Theme & Sector Leadership →
Research tools; Top Picks (first five, halo) / All Candidates; Grid/Table;
theme + sector filter and Expand leadership modal; live quote/change patching
(green-up/red-down under EN **and** ZH); `Board <date>` chip distinct from
`LIVE · <today>` chip; StockTable controls intact; Terminal routing intact;
dark + light; desktop + 390 px; leadership empty states degrade quietly;
no console errors; no horizontal overflow; no official-pick implication in
the Top Picks treatment.

## Leg 2 — EXECUTED 2026-08-25 (entitled Claude-in-Chrome session, demo@mastermind.test)

The operator connected the Claude-in-Chrome extension 2026-08-25 ~17:00Z and
the full matrix ran against production (`www.mastermind-x.com`). First pass
surfaced **two real defects**; both were repaired, the first re-verified on
production, the second armed to merge behind the fleet CI heal.

### Defect 1 — [hidden] hiding visually inert on the grid (FIXED + LIVE)

The composer hides grid cards (`card.hidden = !show`) and the grid pane with
the HTML `hidden` attribute; the UA `[hidden]{display:none}` loses to the
page's `.pvcard{display:flex}` and the composer's own
`.ca-v36-card-grid{display:grid}`. Observed on production: Top Picks showed
all 6 cards under a "5 shown" counter; the leadership filter painted
"0 shown" + the empty-state message over six visible cards; Table view kept
the grid rendered underneath. State/counter/aria and the table rows'
class-based hiding were correct throughout. Repair: scoped
`[hidden]{display:none!important}` overrides in the composer style —
PR #6406, merged `505efbc1a4bf`, byte-verified on the VPS, then **re-run on
production entitled: Top Picks 5/5, All 6/6, Table view grid display:none,
filter 0-state + empty message only, clear 6/6, one board
(#standouts display:none/empty, grid owns all 6), zero overflow.**
Pinned by `tests/test_canada_v36_composer.py`.

### Defect 2 — loader stranded entitled visitors on transient auth hiccups (FIX ARMED)

`dashboard-icons.js`'s composer loader was fire-and-forget (no `onerror`).
The entitled asset's gate consults the auth backend per request;
`/api/regwall/check` intermittently answered **503** during the acceptance,
and on two of ~7 entitled loads the composer script fetch failed the same
way — tag injected, body never executed, visitor silently on legacy until a
manual reload. Repair: bounded onerror retry (3 attempts, 1.5s/3s backoff,
mount-guarded) — PR #6409, armed `merge-on-green` behind the fleet ci-pack
heal (another session owns that heal; per operator, not chased here).
Residual until the next render re-stamp: warm caches keep the old loader
(dashboard-icons.js is `@public_versioned` immutable).

### Matrix results (production, entitled)

| Cell | Result |
|---|---|
| Exactly one board | **PASS** (legacy `#standouts` display:none + 0 cards; grid owns 6) |
| Hierarchy Header → Leading Now → Prophet → Leadership → Tools | **PASS** (DOM order verified) |
| Top Picks (first 5, halo) / All Candidates | **PASS** after #6406 (5/5 ↔ 6/6; halo, copy "Top Picks/首选" only — no official-pick implication) |
| Grid / Table | **PASS** after #6406 (table=StockTable pane, 21 controls; grid display:none under Table) |
| Leadership filter + Expand modal | **PASS** (modal flex, 28 rows, row-click sets filter + auto-switch to All + closes; pill clears; 0-state quiet) |
| Live quote/change patching | **MECHANISM PROVEN** — `live/quotes.json` fresh (all 6 .TO tickers, changePct, age ≈1 min), `.nb-px/.nb-chg[data-sym]` targets present in moved DOM, live.js re-queries per tick + ticks on visibilitychange (deployed bytes). Final paint requires a humanly-visible tab; the automation window stayed on a hidden Space all session (screen-control was declined — operator's call). 10-second confirm: view the page during TSX hours, change chips populate green/red. |
| Green-up/red-down under EN **and** ZH | **PASS** (in-card computed: up rgb(47,138,82), down rgb(196,61,61) under ZH — composer's Western pin `.ca-v36 .nb-chg.up{--ok}` active) |
| `Board Aug 24, 2026` vs `● LIVE · Aug 25, 2026` chips | **PASS** (distinct, both rendered) |
| StockTable controls | **PASS** (21 controls intact in Table pane) |
| Terminal routing | **PASS** (nav Terminal → app.mastermind-x.com; cards → canada_stock.html#TICKER) |
| Dark + Light | **PASS** (screenshots both themes; nav keeps dark chrome by design) |
| EN + ZH | **PASS** (full bilingual copy, no raw slugs; settings popover ZH; prefs persist across reloads) |
| Desktop + 390px | Desktop **PASS** (0 overflow). 390: **bytes-proven** — single `@media(max-width:680px)` fluid single-column block governs 680→390, no fixed-width child; exact-390 pixel pass not executable (OS ignores resize on hidden Space, self-framing denied by security headers, extension blocks zoom keys) — carried as residual. |
| Leadership empty states | **PASS** (0-count rows quiet; grid empty-state message correct) |
| No console errors | **PASS** (entitled load: zero errors) |
| No horizontal overflow | **PASS** (scrollWidth == clientWidth throughout) |

Observations (nonblocking): legacy pvcard sparkline strokes ride the
site-wide ZH `--up/--down` swap (owner-card behavior predating V3.6);
`/api/regwall/check` 503s are an auth-backend availability issue worth its
own lane; the anonymous 401+MIME console noise noted above is unchanged.

## Classification

**Canada V3.6.1 is `PROVEN_LIVE` as of 2026-08-25** — release identity
proven (leg 1), the entitled production matrix executed and passing on
production bytes after repair #6406 (leg 2), with two enumerated residuals:
the final live-paint observation (mechanism fully proven; awaits any human
view of the page during market hours) and the exact-390 pixel pass
(bytes-proven responsive block). Repair #6409 (loader retry hardening) is
armed and merges behind the fleet CI heal.

Per Sol's 2026-08-25 rulings (`DEC:V36-REGIONAL-PILOT-RATIFIED-US-DECOUPLED`),
this promotion releases the HK V3.6 follower wave (convergence packet §4).

Nothing in this session moved ranking, signal, lifecycle, availability,
entitlement, quote, or persistence semantics anywhere.
