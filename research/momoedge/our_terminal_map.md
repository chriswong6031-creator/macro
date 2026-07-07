# Mastermind Terminal — Options/Flow Integration Map
*Generated 2026-07-06 from source audit of /Users/chriswong/Documents/Cluade/charting-app*

---

## 1. Live Options Flow Page(s)

### Current entry point
- **Route:** `/flow` (Next.js App Router page)
- **File:** `terminal/app/flow/page.tsx` — trivial wrapper; renders `<FlowPageRoot />`
- **Client wrapper:** `terminal/components/FlowPageRoot.tsx` — mounts `<LangProvider>` + locale-init script, then renders `<OptionsHubView />`
- **Main component:** `terminal/components/OptionsHubView.tsx` (2,536 lines) — the full 6-tab Options Hub
- **Legacy component:** `terminal/components/FlowView.tsx` (683 lines) — older 2-pane feed+heat view, NOT currently mounted; `FlowPageRoot` replaced it with `OptionsHubView`

### Why the page may show empty
The API route (`terminal/app/api/flow/route.ts`) has a 3-tier fallback chain:
1. Try `FLOW_API_BASE` (default `http://127.0.0.1:8000`) — a local Python server that is NOT running in normal dev/prod use
2. Try R2 CDN: `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/<r2key>`
3. Fall back to local fixture files in `terminal/public/data/*_fixture.json`

**Empty = the Python backend at 127.0.0.1:8000 is down AND R2 keys are absent/wrong AND fixture mode is off (`FLOW_FIXTURE != "1"`).** In dev, set `FLOW_FIXTURE=1` in `terminal/.env.local` to serve the fixture JSONs. In prod, R2 must have the files.

---

## 2. Data Contracts and URLs

### API route: `terminal/app/api/flow/route.ts`
- **Internal Next.js endpoint:** `/api/flow?f=<param>`
- **Valid `f` params:** `feed`, `heat`, `meta`, `tide`, `dte`, `oi`, `hot`, `ctx`, `oiconf`, `ticker:<ROOT>`, `vol:<ROOT>`, `gex:<ROOT>`, `tctx:<ROOT>`
- **TTL:** 30s in-memory cache

### R2 key map (what the UI reads from R2)
| f param | R2 key |
|---|---|
| `feed` | `live_flow/feed_current.json` |
| `heat` | `live_flow/heat_current.json` |
| `meta` | `live_flow/meta.json` |
| `tide` | `live_flow/tide_current.json` |
| `dte` | `live_flow/dte_tide_current.json` |
| `ticker:<ROOT>` | `live_flow/tickers/<ROOT>.json` |
| `vol:<ROOT>` | `options_hub/vol/<ROOT>.json` |
| `gex:<ROOT>` | `options_hub/gex/<ROOT>.json` |
| `oi` | `options_hub/oi_movers.json` |
| `hot` | `options_hub/hot_contracts.json` |
| `ctx` | `options_hub/context.json` |
| `oiconf` | `options_hub/oi_confirmed.json` |
| `tctx:<ROOT>` | `options_hub/tickers_ctx/<ROOT>.json` |

**R2 bucket base:** `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev`

### Local fixture files (dev/fallback)
All in `terminal/public/data/`:
`flow_fixture.json`, `tide_fixture.json`, `ticker_fixture.json`, `dte_fixture.json`, `vol_fixture.json`, `gex_fixture.json`, `screener_fixture.json` (contains `oi` + `hot` sub-keys), `ctx_fixture.json`, `tctx_fixture.json`, `oiconf_fixture.json`

### TypeScript contracts (defined inline in OptionsHubView.tsx)
Key types: `FlowEvent`, `FeedPayload`, `HeatPayload`, `TidePayload`, `DteTidePayload`, `TickerPayload`, `OiMoversPayload`, `HotPayload`, `VolPayload`, `GexPayload`, `CtxPayload`, `TctxPayload`, `OiConfPayload`

---

## 3. Where a New Tab (Flow / Heatmap / GEX / PRISM) Plugs In

### Tab system (OptionsHubView.tsx lines 13-24)
```typescript
type TabKey = "tape" | "tide" | "tickers" | "screener" | "vol" | "gex";
const TABS: { key: TabKey; enKey: string; zhKey: string }[] = [...]
```
To add a new tab (e.g. "prism"):
1. Add `"prism"` to the `TabKey` union
2. Push `{ key: "prism", enKey: "tabPrism", zhKey: "tabPrism" }` to `TABS`
3. Add the tab's i18n strings to `terminal/lib/i18n.ts`
4. Add a `case "prism":` render block inside the `activeTab` switch in the JSX (around line 1,100+)

### Routing
- The tab state lives in `?tab=<key>` query param (URL replaceState), NOT a separate Next.js route
- Adding a wholly new page (e.g. `/heatmap`) means: create `terminal/app/heatmap/page.tsx`, add nav entry in `terminal/components/AppNav.tsx` (the `TOP` array, lines 54-63), add icon glyph to `ICON` map

### API wiring for a new tab
- Add a new `f` param string to `isValidF()` and `backendPath()` and `r2Key()` in `terminal/app/api/flow/route.ts`
- Add a fixture file to `terminal/public/data/<name>_fixture.json`
- The fetch pattern is already established: call `fetch("/api/flow?f=<param>")` from the component

### Component structure
All chart primitives are self-contained inline sub-components in OptionsHubView.tsx:
`TideChart` (LWC Area/Line), `Sparkline` (SVG), `StrikeLadder` (SVG), `ExpiryBars`, `MinuteNetChart`, `TermStructureChart`, `SmileChart`, `IvRankHistory`, `GexHistSparkline`, `GexStrikeLadder`, `GexExpiryBars`
A new tab can reuse any of these or add new ones.

---

## 4. Auth / Entitlement

- **Auth system:** Supabase (Postgres + Auth + RLS), project ref `fsldfzlxyavsuwqbceod`
- **Auth guard:** `terminal/proxy.ts` calls `lib/supabase/middleware.ts` `updateSession()`; matcher covers all routes EXCEPT `_next/static`, `_next/image`, `favicon.ico`, `/data/`, and static asset extensions
- **The `/flow` route IS auth-gated** (falls under the proxy matcher)
- **Pro gate:** `is_pro` boolean on the `profiles` table; checked server-side in `/api/scripts/save`. Options hub (`/flow`) is NOT currently gated by `is_pro` — it is available to all authenticated users
- **Demo credentials:** `demo@mastermind.test` / `mastermind123` (is_pro=true)
- **Env secrets:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` in `terminal/.env.local`

---

## 5. Build + Deploy Path

### Local dev
```bash
cd /Users/chriswong/Documents/Cluade/charting-app/terminal
npm run dev    # port 3002
```
Set `FLOW_FIXTURE=1` in `terminal/.env.local` to serve fixture data without a live Python backend.

### Production build
```bash
cd terminal && npm run build && npm run start
```
`next.config.ts` sets `typescript.ignoreBuildErrors: true` and `eslint.ignoreDuringBuilds: true` to prevent cosmetic strictness from blocking deploys.

### Deploy to VPS
- **VPS:** `root@146.190.142.17` (DigitalOcean, confirmed in TERMINAL-ASSESSMENT.md)
- **App root on VPS:** `/opt/terminal`
- **Deploy method:** local build → rsync → `systemctl restart terminal`
- **Nightly data refresh:** `/usr/local/bin/terminal-data` (script at `ingest/terminal-refresh.sh`), cron `30 21 * * *`
- **Public data dir (R2-analogous on VPS):** `/opt/terminal/terminal/public/data/`; files placed here are served immediately without restart (Caddy serves `/data/*` as static; the proxy.ts matcher excludes `/data/` from auth so they are public)
- **Caddy:** sits in front; the TERMINAL-ASSESSMENT.md notes `/data/*.json` has no `Cache-Control` header (a known gap — short `max-age` should be added)

### Flow/options data pipeline
The Python backend (`api/main.py`, FastAPI on port 8000/8800) is a Phase-0 stub; it is NOT running in prod. The live flow data must come from:
1. A running Python hub service writing R2 keys (the Macro Dashboard's `live-options-flow` pipeline, running via launchd on the Mac Studio)
2. Direct R2 reads via the Next.js `/api/flow` proxy
The `terminal-refresh.sh` nightly script does NOT generate options/flow data — it only builds OHLC + signal slices.

---

## 6. Key File Index

| File | Purpose |
|---|---|
| `terminal/app/flow/page.tsx` | Route entry for `/flow` |
| `terminal/components/FlowPageRoot.tsx` | Lang+locale wrapper |
| `terminal/components/OptionsHubView.tsx` | Full 6-tab hub (2,536 lines) |
| `terminal/components/FlowView.tsx` | Legacy 2-pane view (not mounted) |
| `terminal/app/api/flow/route.ts` | Next.js API: backend → R2 → fixture fallback |
| `terminal/components/AppNav.tsx` | Nav rail; add tabs here |
| `terminal/app/globals.css` | Design tokens (CSS vars: `--up`, `--down`, `--brand`, `--panel-*`, etc.) |
| `terminal/app/fin.css` | Financial UI components (`.chip`, `.pill`, `.scr`, `.flow-*` classes) |
| `terminal/lib/i18n.ts` | Bilingual string map; add new tab labels here |
| `terminal/proxy.ts` | Auth middleware |
| `terminal/public/data/*_fixture.json` | Static fixtures for dev/fallback |
| `ingest/terminal-refresh.sh` | Nightly VPS data refresh (OHLC/signals only) |
| `HANDOFF.md` | Full session context |
| `TERMINAL-ASSESSMENT.md` | Deep ops/architecture assessment |
