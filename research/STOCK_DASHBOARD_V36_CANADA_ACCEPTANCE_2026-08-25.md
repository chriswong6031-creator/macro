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

## Classification

**Canada V3.6.1 remains `BUILT_NOT_PROVEN`** — leg 1 (release identity) is now
PROVEN with the receipts above; leg 2 (entitled browser matrix) is the sole
remaining gate. Per the standing pilot law, the HK V3.6 presentation coding
wave stays **unreleased** until leg 2 passes and Canada is promoted to
`PROVEN_LIVE` in a dated durable receipt.

Nothing in this session moved ranking, signal, lifecycle, availability,
entitlement, quote, or persistence semantics anywhere.
