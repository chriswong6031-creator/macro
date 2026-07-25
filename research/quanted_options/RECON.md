# quantedoptions.com — full-platform recon (2026-07-24/25 session)

Interactive teardown via authenticated browser session (operator's Lite-tier account) + front-end bundle extraction.
This is the **binding context document** for the Terminal options build waves. Companion docs: `MASTERPLAN.md` (build plan),
`api_samples/` (payload schemas), `js_extracts/` (their minified renderer chunk + beautified copy).

Sources: live app at /quantedgamma, /quantedticker, /quantedflow; marketing pages /, /learn, /compare;
Next.js chunks (esp. `1736.e6cc7aedd44e67b2.js` = surface renderer); network + in-page API sampling.

---

## 1. Product architecture + business model

Three surfaces, one Next.js app (Vercel, app-router, `[locale]` i18n scaffold but EN-only today; Shopify for billing):

| Surface | URL | Data | Cadence | What it is |
|---|---|---|---|---|
| quantedFlow (SPX/VIX GEX) | /quantedgamma | **Licensed CBOE signed market-maker positioning** ("no open-interest assumptions") | 1-min (Classic $299) / 10-min (Lite $149) | 3-pane workspace: strike ladders + gamma/vanna/charm surfaces + price/gamma chart, full-day replay |
| quantedTrader | /quantedticker | OPRA cross-exchange tape, OI-based | 1-min, 600+ tickers | Per-ticker strike profile / net delta / premium flow / per-strike session gamma; Quad index mode |
| quantedFlow scanner | /quantedflow | OPRA tape scans | periodic scans (~live) | Ranked unusual-contracts scanner + sector/index belts + contract drill (chart + tape) |

Pricing = **cadence + coverage laddering** of the same product: Lite $149 (10-min, SPX only, MM view only) → Classic $299
(1-min, +VIX, +participant views, +historical replay, +MM counterparty premium flow) → Ultra $399 (+7,500 API credits/mo).
quantedTrader from $79 standalone, included in all tiers. $29 3-day trial on Lite. "Elsewhere this cadence is $299 — here it's $149" anchoring.

**Moat claim**: exchange-tagged *signed* MM positioning for SPX/VIX (Cboe license), vs everyone else's OI-sign assumptions.
Their Learn page weaponizes this ("Open Interest Lies: same OI, 200% discrepancy").
**Participant exposure views** (Classic+): MM · Firm · Broker-Dealer · Customer buckets.

## 2. Data plane (the architecture to copy)

All app APIs are session-gated (401 anonymous). Static chunks public.

### quantedgamma endpoints
- `GET /api/gex/dates?product=SPX|VIX` → `["2026-06-01",...]` (~38 trading days retained = replayable history window)
- `GET /api/gex/client-timeline?product=SPX` → `{date, rfr, source:"lite", expiries[], timestamps[74], timeline[{ts,spx,gex,call_gex,put_gex,dex,vix,net_gex}], walls:{gex_flip,put_wall,call_wall}, v:"2026-07-27_18-00", lite}`
  - Lite tier: 74 stamps/day, 10-min cadence 04:01→16:15 ET (incl. premarket)
- `GET /api/cgif/watchlist` → live CBOE Global Index Feed values for ~dozens of indices `{indices:{SPX:{value,ts,bid,ask},...}, uncategorized:{...}}`
- `GET /api/cgif/timeline?date=` · `GET /api/cgif/stream-token` (405 on GET; token mint for live stream) · `GET /api/polygon/spot` · `GET /api/candles?date=YYYY-MM-DD` · `GET /api/data-urls?types=...`

### quantedticker endpoints (the blueprint)
- `GET /api/quantedticker/data-urls?keys=client/{TICKER}/dates.json | client/{TICKER}/{DATE}/index.json | client/{TICKER}/{DATE}/{HHMMSS}.json`
  → `{urls:{key: signedUrl}, expiresIn:300}` — signed **DigitalOcean Spaces** URLs (`quantedptions-data.nyc3.digitaloceanspaces.com`), 1-12 keys per call
- Blob layout per ticker/day: `index.json` = `{date, ts:["040012","040211",...~735 one-min stamps], latest, oiFresh}`; one immutable JSON per snapshot
- Snapshot file (~97KB QQQ): `{ticker, spot, sessionDate, expiries[33], views:{zero,all,allx0}, source, date, ts, capturedAtCt, oiFresh, contractCount, fetchSeconds}`
  - each view: `{strikes:[[strike + 12 numeric cols]], totals, flip, callWall, putWall}`
- `GET /api/quantedticker/strike-timeline?ticker=QQQ&view=zero|all[&date=]` → `{ticker,date,view,rows:[["HHMMSS",[[strike,a,b],...]],...]}` — per-minute per-strike series powering Strike Gamma — Session + evolution popups

**Why this matters**: replay & live share one path — client polls `index.json` for new stamps, fetches immutable per-minute
snapshot blobs from CDN, scrubbing = re-fetch by stamp. Server does all math; client only shades cells. Cheap, cacheable, perfectly
suited to our existing R2 + nightly/poller split. `oiFresh` flags T+1 OI refresh state.

### quantedflow endpoints
- `GET /api/quantedflow/signals` → `{ts, sort:"premium", scan_id, scan_started_at, scan_date, fallback_used, count:50, signals:[{contract:"O:SNDK260731C01000000", ticker, expiry, strike, side, day_vol, oi, vol_oi, premium_dollars, mid, iv, delta, gamma, spot, day_change_pct, delta_vol}]}`
- `index-complex`, `sectors`, `watchlist`, `scans/latest-date`, `scans`, `contract-bars`, `contract-trades` (per-contract candles + prints)

## 3. The "paint" surfaces — exact rendering algorithm (fully decoded)

TradingView **Lightweight Charts** everywhere (lwc attribution links). Surfaces = LWC *custom series plugin*
(chunk `1736.e6cc7aedd44e67b2.js`, 21KB — beautified copy committed alongside). No WebGL, no CSS blur.

1. Payload per surface: `{spot, time_steps[], price_levels[], grid[levelIdx][timeIdx], min_val, max_val}`.
   Bars built as `{time, cells:[{low: level-step/2, high: level+step/2, amount: grid[l][t]}]}`.
2. Renderer collects unique cell boundaries → **offscreen canvas at native grid resolution** (width = #time columns,
   height = #strike levels; 1 cell = 1 px) → `createImageData` → per-pixel `cellShader(amount)` → `putImageData`.
3. Blit: `ctx.imageSmoothingEnabled=true; ctx.imageSmoothingQuality='high'; ctx.drawImage(offscreen, gridRect → plotRect)`.
   **The browser's high-quality upscale of a tiny grid IS the watercolor/paint aesthetic.**
4. Candles drawn by normal LWC series on top (up `#22c55e`/down `#ef4444`, or greyscale `#a0a0a0`/`#606060` mono-candle mode).
5. Contour/线 overlays drawn with Catmull-Rom→cubic-bezier smoothing (`(next-prev)/6` control points).

### Exact cellShader (verbatim semantics)
```js
// amount, maxAbs = max(|min_val|,|max_val|), pos/neg = theme RGB triplets, W = opacity slider 0..1
if (maxAbs === 0) return `rgba(30,30,35,${0.2*W})`;
const o = Math.min(1, Math.abs(amount)/maxAbs);
const c = amount >= 0 ? pos : neg;
let r,g,b;
if (o <= 0.6) {            // body: sqrt-eased blend from panel base (30,30,35) to full hue
  const e = Math.sqrt(o/0.6);
  r = 30 + e*(c[0]-30); g = 30 + e*(c[1]-30); b = 35 + e*(c[2]-35);
} else {                   // hot core: overexpose toward white by up to 35%
  const e = (o-0.6)/0.4 * 0.35;
  r = c[0]+(255-c[0])*e; g = c[1]+(255-c[1])*e; b = c[2]+(255-c[2])*e;
}
const alpha = (0.2 + 0.68 * Math.pow(o, 0.6)) * W;
return `rgba(${r|0},${g|0},${b|0},${alpha.toFixed(3)})`;
```
Two-band design = the signature: fast sqrt ramp to hue, then white-hot cores where |exposure| > 60% of day-max.
Range slider (±150 etc.) just filters `price_levels` to `spot±q` (and grid rows with them) before setData.
Zero-line: dashed white contour at sign flips. Per-greek color pairs from Style menu (see §4.6).

## 4. /quantedgamma UI census

Top bar: logo · View · Style · [quantedFlow | quantedTrader] pills · date+`SPX 7,411.98 +0.00` · local clock (ET) · GEX-Activity bell ("N snapshots / No activity yet") · avatar.

Workspace: labeled panes A/B/C (+ bottom drawer). Each pane header: **widget selector dropdown** (grouped: LADDERS → SPX Strike Profile; SPX SURFACES → SPX Surface; PRICE/GAMMA → SPX Price/Gamma) + **pop-out to new window** icon.

### 4.1 View menu = workspace manager
LAYOUT: 8 grid presets (1/2/3 col, 2+1, 1+2, mixed) · ADD ROW: same presets · **+ Add Page** (multi-page workspaces).

### 4.2 SPX Strike Profile (ladder pane)
- Toolbar: `Chart` toggle · metric dropdown **GEX / DEX / VEX / CEX** · **Net | Call/Put** · `0DTE only` · gear · **Σ 0DTE** · **6 expiries** picker.
- Body: horizontal ± bars per strike (pos/neg colored, glow), current-price line + yellow spot chip, bottom scale `NOW -$6B..+$6B / PEAK -$10B..+$10B` (dual normalization: bars vs today's peak), right columns = per-expiry $ values (3 DTE Jul 27 · 4 DTE · 5 DTE · 7 DTE...), col-header shows date, per-column footer totals ($240M, $299.3M, $1.2B), cells heat-tinted (teal +, red −) with strongest cells saturated.
- Gear popover: STRIKE Range slider ±200 · Step ±$5 · DISPLAY: Scaled / Uniform toggles · IV (Off/IV) · **Glow** toggle.
- **Σ 0DTE menu** ("Sum into primary bar"): scope tabs `0DTE | Wk | 2W | Mth | All` + per-expiry checkbox list grouped THIS WEEK / NEXT WEEK / AUG 2026... each with net GEX badge ($240M, -$1.8B...).
- **Hover a strike row → rich popover**: `7,470 Strike · +0.8% ATM` · Gamma total + Call/Put split + Vanna + Charm rows · mini intraday sparkline of that strike's gamma with price overlay + ◀NOW marker · "Top Expiries" ranked list w/ % shares · footer `SPX 7,412 · VIX 0.0 · 16:15` · `Click for evolution` hint · **Send to chart** button.
- **Click strike → "Intraday Evolution" modal**: large line chart (strike's gamma through the day, price line overlay, NOW marker), "Expiry Breakdown at Current Time (Gamma)" horizontal bar list ($491.5M 61% / $135.3M 17% / ... incl. negative red bars), footer `Spot 7,412 · 41 snapshots · Send to chart · Press Esc to close`.

### 4.3 SPX Surface pane (×2 shown: Gamma + Charm by default)
Toolbar: greek tabs `Gamma | Vanna | Charm` · scope `0DTE | All` · agg `1m 5m 10m 15m 30m` · Opacity slider (80%/100%) · Range slider ±150 · legend `● Gamma ● −Gamma — Zero` · as-of stamp.
- Crosshair readout pill top-left: `Strike 7411 · GAMMA · -$14.8K` (live tracks mouse; dashed crosshair lines).
- Candles overlay on the field; y-axis = strike ladder; x = session time.
- **Replay semantics**: left of NOW = realized surface evolution; right of NOW = *current snapshot's field projected forward* with white zero-contour outlines. (At EOD the whole day is realized.)

### 4.4 SPX Price / Gamma pane
1m/5m/10m/15m candles with **horizontal GEX bands** painted behind price (row tint by strike-level exposure), crosshair readout `Strike 7,450 · GEX +$334.8M`, GEX toggle + opacity. ("Send to chart" from the strike popover pins into this pane's context.)

### 4.5 Exposure-by-Expiry drawer (bottom)
Accordion `EXPOSURE BY EXPIRY · 69 exp`. Full-width **bubble chart**: x = every listed expiry (Jul 24 · 0d → Sep 18 '26 56d → LEAPs), y = net GEX, bubble size ∝ |GEX|, teal/pink by sign, $-labels on every bubble. Toggles: **Bubbles | Bars** · **Call/Put | Net**. Replays with the scrubber (69 exp @EOD → 59 exp @10:10).

### 4.6 Style menu (global)
- THEME: Dark · Midnight · Terminal · **Amber** · Light · Lavender · Breeze · Rose · Mono (9 presets).
- Per-greek color-pair grids (GAMMA / VANNA / CHARM): ~13 two-dot combos each (teal/red, green/pink, blue/yellow, purple/orange, white/grey…) + **Custom** (full picker). Defaults: gamma teal/red, vanna purple/orange, charm indigo/yellow.

### 4.7 Replay bar (bottom, global)
`⏮ ◀ ▶(Space) ▶ ⏭` · speed radios `1x 2x 4x 8x` · time label · scrubber with frame count `74/74`.
**Scrubbing time-travels EVERYTHING**: header quote, ladders, surfaces, drawer, per-pane as-of stamps. Keyboard: Home/End/Space.
Historical dates via `/api/gex/dates` (Classic tier unlocks past sessions; Lite = today only).

## 5. /quantedticker (quantedTrader) UI census

Top bar: date picker (historical) · **Ticker** menu (search + curated hot list: QQQ SPY IWM DIA NDX MU SNDK GLD META AMD GS ASML TSLA LITE STX GOOGL BKNG GEV LLY WDC CAT SPCX…) · **Expiry** menu: `0DTE (today only) / All expiries / All − 0DTE` + SPECIFIC EXPIRY list (every listed date w/ DTE tag) · View · Style · **Quad** menu (`QUAD · SPY/QQQ/IWM/DIA` → Chart "front-month ladders" | Table "all tenors") · quantedFlow link · stats strip `0DTE NET GEX -6.76B · ALL EXPIRY NET GEX -13.04B · QQQ 684.48` · `● CLOSED` market-state chip.

Default layout: A = Strike Profile (tall left), B = Net Delta — Session, C = Premium Flow — Session, D = Strike Gamma — Session.
Widget selector per pane: Strike Profile · Premium Flow · Premium Flow — Session · Net Delta — Session · Strike Gamma — Session.

- **Strike Profile**: `Chart | Table` · `0DTE only` · chips `NET GEX -6.76B · FLIP — · C WALL 685 · P WALL 685` · range presets `±2% ±5% ±10% All` · giant ticker watermark · expiry columns w/ heat cells like SPX ladder.
  - **Table mode**: strike × expiry matrix (ODTE + each expiry column), heat-tinted cells, Net GEX totals footer row — a full exposure matrix.
- **Net Delta — Session**: chips `0DTE -$4.41B · ALL EXPIRY − 0DTE -$15.03B`; scope tabs `0DTE / All Expiry / All Expiry − 0DTE`; `Fill` checkbox; `off open` (rebase to 9:30 open); `absolute`; two intraday lines (purple all-exp, orange 0DTE) w/ negative fill shading; footnote "net delta Δ off 9:30 ET open · 390 pts".
- **Premium Flow — Session**: `CALLS $376.6M · PUTS $521.4M` chips; `C+P | Calls | Puts`; `Fill`; `cumulative | per-min`; stacked cumulative area (calls teal vs puts orange); footnote "RTH premium since 9:30 ET · calls vs puts · 390 pts".
- **Strike Gamma — Session**: `GEX | DEX` · `Labels` · `Auto`; multi-line per-strike intraday exposure; right rail "Strikes +" list with color-dot rows `690 A +$42.3M` (A = auto-tracked top strikes; + to pin custom; trash to clear); on-chart floating strike badges.
- **Quad mode**: 4 synchronized front-month ladders (SPY/QQQ/IWM/DIA), each with its own NET GEX/FLIP/C WALL/P WALL chips + range presets + watermark; replay bar spans all.
- **Replay**: 735/735 1-min frames 04:00→16:15 ET, `LIVE` badge when at head; CT/ET label quirk.

## 6. /quantedflow scanner UI census

- Top: date picker (past scan days) · `Flow | Ticker` view switch · Style · **Gamma** (green → /quantedgamma).
- **INDEX belt**: SPY/QQQ/IWM/NDX/RUT/VIX chips — day premium total + `P 72%`/`C 71%` skew tag + red/green split bar.
- **SECTOR FLOW belt**: 11 sector chips (`$2649.5M · P 55%` style), *click to filter* the table; METRIC switch `$ PREMIUM | VOLUME | UNUSUAL`.
- **Feed modes**: `LIVE` (ranked current scan, `50` count badge, "AS OF · JUL 24") | `★ HIGHLIGHTS` ("biggest bursts today": WINDOW `ALL DAY / 9:30-10:30 / 3-4 PM` · SORT `ΔVOL | PREMIUM`; rows timestamped w/ ΔVOL green/red bars).
- **Ranked table** (LIVE): RANK BY `PREMIUM | UNUSUAL VOLUME | ΔVOL` · DTE chips `ALL/0DTE/1-7/8-30/31-90/90+` · SECTOR dropdown; columns TICKER/STRIKE/C-P/EXP/VOL(bar)/OI/V-OI(amber flag)/PREMIUM.
- **Contract detail pane**: header `SNDK $1,000 CALL JUL 31, 2026` + mark `$443.14 ↓ −$176.64 (−28.50%)`; stat row VOL/OI/PREMIUM/V-OI/OTM-ITM%; **CONTRACT CHART** (option-price candles, 42 bars, volume); **TRADE TAPE** `1,168 prints · 1,953 contracts` — TIME/PX/SIZE/NOTIONAL/TAG rows, tag dots `● Block ≥500 · ● Sweep · ● Single`, block rows highlighted (`$26.00M · BLOCK`).
- **Ticker view**: per-name **TOP STRIKES** table — `spot $333.78` · All/Calls/Puts · HORIZON 6M · WINDOW ±15% · EXPIRY All · summary chips `Today Calls 305.5K · Puts 254.6K · C/P 1.20 · 0DTE 0% of vol` · columns Exp/Strike(+moneyness chip, ATM tag)/C-P/Vol(bar,sorted)/OI/V-OI/IV/Δ/Mid, green-red row tints.
- Replay scrubber + `● LIVE` badge at bottom (scan history through the day).

## 7. /learn — "Now You Know What Market Makers Hold."

Single scroll-pinned page (Lenis-style smooth scroll + letter-split animations), green-on-black editorial. "Eight concepts. Zero fluff."
Concepts (full copy extracted; each has an animated primitive diagram):
1. **Options Move Markets Now** — 0DTE volume exploded; the chain moves the underlying. (bar diagram)
2. **The Middleman** — MM takes other side of every trade, stays neutral; "that neutrality has consequences." (You→CALL→MM + hedge arrows)
3. **Open Interest Lies** — OI=5 but MM could hold 0/+5/−5; "Same OI, 200% discrepancy. You need exchange-tagged positional data." (3-card comparison)
4. **Why MMs Move Markets** — continuous rehedge = real buy/sell pressure. (BUY/SELL + "delta shifts → rehedge")
5. **Gamma Is Gravity** — +gamma: buy dips/sell rips, mountain peak; −gamma: cliff, avalanches. (mountain/cliff with flip marker)
6. **Charm Is Wind** — positive charm suppresses (headwind), negative lifts (tailwind); "drift over time."
7. **The Flip Changes Everything** — regime change; "brakes become a gas pedal"; "Where the flip is — that's the edge." (FLIP split diagram)
8. (CTA) **A Tour of the Platform** — "Theory is great. Data is better."

Porting rule: rewrite in our voice EN/ZH, redraw as our own SVG/lib.illus diagrams (metaphors are ideas — fine; no verbatim copy).
DNR guard: charm narratives are a KILLED signal family for *authority* on our side — educational treatment must stay display/educational tier, no signal claims.

## 7.5 /api-access — their developer API product

Ultra-only ($399/mo): 7,500 credits/mo included, $0.05/call after. Terms: internal use only, no redistribution/public display.
- `GET /api/v1/strikes` (1 credit) — one metric × one expiry × one participant: `{metric:"gex", expiry:"0dte", customer_type:"mm", total, data:[[strike, gex, call_gex, put_gex, call_mid, put_mid]], fields}`; metrics GEX/DEX/VEX/CEX; participants MM/Firm/BD/Cust/PCust; per-minute historical 04:00–16:15 ET, any past date.
- `GET /api/v1/timeline` (1 credit) — full-day intraday series `[{ts,gex,call_gex,put_gex,dex}]`.
Wave-2+ note for us: a credit-metered read API over our R2 snapshot store is nearly free to add once the store exists (mint from macro-api entitlements), and is a clean Ultra-tier analog for Terminal Pro.

## 8. UI patterns worth stealing (catalog)

1. Global replay bar time-traveling the entire workspace (frames = snapshot stamps; Space/Home/End; speeds; LIVE badge at head).
2. Hover-popover → click-modal → "Send to chart" three-depth drill on any strike.
3. Widget-per-pane workspaces w/ grouped selector, pop-out windows, layout presets, multi-page.
4. Σ-expiry checkbox aggregation ("sum into primary bar") with per-expiry $ badges.
5. Expiry lens as a global top-bar filter (0DTE / All / All−0DTE / specific).
6. Exposure-by-expiry bubble term-structure drawer.
7. Per-greek user-pickable diverging color pairs + 9 theme presets; mono-candle option so field colors pop.
8. Dual normalization scale (NOW vs PEAK) on ladder bars.
9. Crosshair readout pills (top-left of each chart) instead of tooltips chasing the mouse.
10. Sector/index belts with premium + P/C% split bars as click-filters above a scanner.
11. Burst-detection Highlights mode with time-of-day windows (open hour / power hour).
12. Contract-native drill: option-price candles + print tape with Block/Sweep/Single tags.
13. Auto-tracked top-N strike lines w/ pinnable custom strikes (Strike Gamma session).
14. Off-open rebasing + absolute toggles on session lines; cumulative vs per-min premium.
15. `● CLOSED / ● LIVE` market-state chip; as-of stamps on every pane.
16. Data honesty in marketing: cadence tiers priced openly; "no OI assumptions" as differentiator.

## 9. What they DON'T have (our openings)

- No alerts anywhere visible (no threshold/level-cross alerts on flip/walls/flow).
- No bilingual UI (EN only; `[locale]` scaffold unused). We ship EN/ZH day one.
- No mobile-responsive trading view (desktop-only grid).
- No cross-asset context (no VIX term structure vis on Lite, no macro regime, no breadth) — our macro estate is unmatched.
- No education→tool deep links (Learn is marketing, not in-app glossary/tooltips).
- No watchlist/portfolio integration in the options views; no per-user saved scans visible.
- Scanner lacks composite scoring (rank = raw premium/vol only; no flowScore-style calibration, no OI-confirmation lane like ours).
- No EOD research estate (multi-day accumulation, OPEX studies, track records) — Macro Dashboard territory.
- Replay limited to snapshot cadence; no bar-level scrub inside a snapshot; no event annotations on the timeline.
- No options strategy tooling (spreads, expected move cones, P/L overlays).
