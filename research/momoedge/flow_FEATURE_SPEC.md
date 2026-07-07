# MomoEdge Terminal — FLOW Surface: Canonical Build Specification

> Faithful reconstruction of the competitor's "Flow — live options flow feed" surface (momoedge.ai //
> LIVE ORACLE TERMINAL). Source: screenshot-analysis notes `/tmp/momoedge_specs/raw/flow_1.md`,
> `/tmp/momoedge_specs/raw/flow_2.md`, cross-referenced with
> `research/MOMOEDGE_ORACLE_COMPETITIVE_FEATURE_STUDY_FOR_FABLE.md` §§10–18, 26.
> **This spec describes the competitor product only** — no MomoEdge/our-stack implementation mapping.
>
> **Evidence caveat — two UI generations observed.** The screenshots capture two distinct Flow
> lineages. Where they conflict, this spec treats the **conviction-score generation** (flow_1) as the
> canonical target and records the **legacy "TTY SIGNALS" generation** (flow_2) as an alternate for
> completeness. Conflicts are flagged inline and consolidated in §7.

---

## 1. Surface Overview & Layout

The FLOW tab is one of five terminal views (nav: **ORACLE · FLOW · HEATMAP · GEX · PRISM**; the
legacy shot mislabels the last tab "PRISON" — OCR error, read as PRISM). FLOW is a live options-flow
feed: it "tracks live options-flow trades as they print through the trading day, scored by Oracle for
conviction." (guide, verbatim)

### Global chrome
- **Top bar:** Brand "MOMOEDGE // LIVE ORACLE TERMINAL" (far left) · center nav tabs · right-side
  session status badge (**ENGAGED**, green) + a running P&L / gains figure (e.g. "$1,109 GAINS") +
  user icon(s) · **FLOW GUIDE** button (far right).
- **Bottom status bar (footer telemetry):** `ORACLE ONLINE` · `UPTIME: 00:02:08` (session timer) ·
  `SIGNALS: 5 ACTIVE` (live active-alert count) · `STALE — 11M ago` (data-freshness indicator) ·
  `MARKET CLOSED` / market-session state · `ENGINE: SKYNET v2.0` (engine version string; legacy shot
  shows `ENERGY/ENGINE: v1.3`). One shot shows `OPTIONS: $8-98.85` (unresolved — possibly feed
  price/range).

### Three-column body (desktop)
The guide names the columns explicitly ("It has three columns"):

| Column | Width (approx) | Contents |
|---|---|---|
| **Left — Watchlist rail** | ~15–25% | `MARKET OVERVIEW` panel (top) → `TOTAL OPTION PREMIUM` panel (mid) → `WATCHLIST` panel (bottom) |
| **Center — Live Flow Feed** | ~40–55% | Filter/search bar → `NNN SIGNALS` count → scrollable feed of flow cards/rows |
| **Right — Inspector** | ~30–35% | Detail card for the selected trade + price sparkline + `FLOW BREAKDOWN` sub-panel |

- **Left / MARKET OVERVIEW:** per-index mini sparklines with bull/bear premium split, e.g.
  `SPY: Last $472.2M · Bull $221.5M · Bear $228.1M · Net: -$23.4M`; `QQQ: Bull $337.7M · Bear
  $201.0M · Net: +$136.7M`. (Note: OCR "Bet"/"Bad Bull" = "Bull"/"Bear" mis-reads.) The legacy shot
  shows **three** mini-charts, current shots show two named (SPY, QQQ).
- **Left / TOTAL OPTION PREMIUM:** aggregate premium block — e.g. call premium `$317M`, put premium
  `PC $1653M`, `PC Ratio: 0.46`. (Maps to the study's "Flow Gauge": total premium, call vs put
  premium, P/C ratio, sentiment.)
- **Left / WATCHLIST:** empty-state placeholder "Star a ticker to add it here"; when populated, one
  row per followed ticker showing that ticker's **best live flow score for the day**.
- **Center / Feed:** header `NNN SIGNALS` (live count of signals passing current filters; observed
  "771 SIGNALS"). Rows are **per-trade, not per-ticker** (duplicate tickers appear — AMD ×2, NVDA ×2).
- **Right / Inspector:** populates on card selection; shows the full trade breakdown, a **flow drift
  chart** (5-day directional trend, per guide), and market context.

### Mobile evidence
No mobile screenshots in this set. The competitive study (§ Mobile Layout) records that the mobile
Flow pane exists with: watchlist chips, flow gauge, total-premium/call-put/P-C summary, symbol
search, saved views, dense filters, and mobile flow cards. Treat mobile as a stacked single-column
adaptation of the three panels with the watchlist rendered as horizontally-scrolling chips.

---

## 2. Complete Control Inventory

### 2.1 Navigation & global
| Control | Type | Behavior |
|---|---|---|
| ORACLE / FLOW / HEATMAP / GEX / PRISM | Nav tabs | Switch terminal view; FLOW active state = teal highlight |
| FLOW GUIDE | Button (top-right) | Opens right-side Flow Guide drawer (see §5) |
| Status badge (ENGAGED / ORACLE ONLINE) | Indicator | Live connection state; green = live |

### 2.2 Feed toolbar (above the feed)
| Control | Type | Options / Placeholder | Behavior |
|---|---|---|---|
| **Search ticker** | Text input (magnifier icon, left-anchored) | "Search ticker…" | Free-text filter of feed by ticker symbol |
| **Views** | Button (secondary) | — | Opens saved-view presets (saved filter combinations); study confirms "saved views" |
| **Filters ▾** | Button w/ caret (active/open state) | — | Toggles the filter panel open/closed |
| **Sort toggle** | Toggle | `Newest` \| `By score` | Ranks feed. Guide: "the sort toggle to rank by newest or by score." Study adds broader implied sort keys: newest, score, premium, size, size/OI, move, DTE, IV |

### 2.3 Filter panel (expanded state) — canonical (flow_1)
Labeled filter groups, top→bottom:

| Group | Control type | Options | Default | Behavior |
|---|---|---|---|---|
| **TYPE** | Segmented pills (single-select) | **All** · Calls · Puts | All | Filter by contract type |
| **DIR** | Segmented pills (single-select) | **All** · Bull · Bear | All | Filter by derived directional bias (not raw call/put) |
| **SCORE** | Segmented pills (single-select) | **50+** · 60+ · 70+ · 80+ · 90+ | 50+ shown selected in filter UI; **feed default display = 60+** (guide: "Only trades scoring 60 and above show by default") | Minimum conviction-score band |
| **PREM ≥** | Numeric text input | placeholder "e.g. 500K" (accepts K/M shorthand) | empty | Minimum premium in dollars |
| **FLAGS** | Chip toggles (multi-select) | Sweeps · Whale | none | Isolate flagged footprints; multiple can be active |
| **Reset** | Button | — | — | Clears all filters back to defaults |

Study §10 records a broader latent filter set (from source hints) not all surfaced in these
screenshots: call/put, sentiment, score band, DTE, moneyness, expiry, premium min/max, execution
label, grade tier, side, badges, size/OI, size/volume, volume, OI, IV, underlying move, saved views.
Treat the six visible groups as confirmed; the rest as candidate/advanced filters (§7 gap).

### 2.4 Inspector controls — legacy generation (flow_2)
The legacy Inspector shows a side/sentiment tab strip on the detail panel:
| Control | Type | Options | Behavior |
|---|---|---|---|
| Side tabs | Tab strip | **BUY** · SELL · BEAR · OTHER | Filters the ticker's flow breakdown by trade side/sentiment; BUY default active |

This tab strip is **not present** in the canonical (conviction-score) Inspector, which instead shows
CALL badge + tier badges + score. Flagged as a generation difference in §7.

### 2.5 Row / card actions
| Control | Type | Behavior |
|---|---|---|
| **Score badge** | Clickable chip on each row | Selects the trade → loads Inspector |
| **Card body** | Click | Selects/expands → full detail in Inspector |
| **Star icon** | Toggle on each flow card | Follow/unfollow ticker → adds to Watchlist (syncs to account) |
| **Watchlist row** | Click (toggle) | Tap once = filter feed to that ticker; tap again = clear filter |

---

## 3. Data Model

### 3.1 Flow event / card record (one options trade)
| Field | Displayed as | Inferred type / units | Semantics |
|---|---|---|---|
| `ticker` / `symbol` | "SEDG", "MU" | string | Underlying symbol |
| `type` | "CALL" / "PUT" badge | enum {CALL, PUT} | Contract type |
| `direction` | BULL / BEAR badge | enum {BULL, BEAR} | Derived bias: bought call OR sold put → BULL; bought put OR sold call → BEAR. Accounts for buy/sell × call/put, not raw type. Server `trade_dir` authoritative when present (study §11) |
| `premium` | "$505K", "$8.2M" | USD, K/M-abbreviated | Total dollars spent on the trade |
| `strike` | "$58", "$130", "$700" | USD | Option strike price |
| `expiry` / DTE | "JUL", "JUL 31", "AUG 7", "Jul 17" | date | Expiration; also expressible as DTE (days-to-expiry) |
| `otm` / strike distance | "1.9% OTM", "5% OTM", "134.8%" | percent (can exceed 100%) | How far strike sits ITM/OTM; deep-OTM tracked |
| `time` | "11:55AM ET", "PM" | time (ET) | Print timestamp; "PM" = afternoon-session marker |
| `score` | "97", "94", "73" | integer 0–100 | Oracle **conviction score** (see §4) |
| `size` | "58", "25" | integer contracts | Trade size in contracts |
| `oi` | "250", "100" | integer | Open interest on the contract |
| `s_oi` / size-to-OI | derived (e.g. 58/250) | ratio | Size vs existing OI; ≫1 ⇒ likely new position not a close |
| `iv` | "1.8%", "5.9%" | percent | Implied volatility |
| `spot` | "$7.00", "~$22" | USD | Underlying price at print time |
| `contract_price` | "$6.30" | USD | Option contract fill price |
| `entry` / execution | "Near Ask" / "Near Bid" | enum | Fill side: near ask = aggressive/buyer-led; near bid = passive |
| `flow_dir_sd` | "FLOW DIR SD" | numeric (unresolved) | Directional standard-deviation / drift metric |
| `badges[]` | UNUSUAL · SWEEP · BLOCK · WHALE · CLUSTER | multi-flag set | Footprint flags (see §4.3) |

### 3.2 Inspector — FLOW BREAKDOWN sub-panel
| Field | Displayed as | Type | Semantics |
|---|---|---|---|
| `TOTAL PREMIUM` | "$505K" | USD | Aggregate premium for the trade/campaign |
| `# CONTRACTS` | "1840" | integer | Contract count (distinct from card SIZE — may aggregate) |
| `AVG PREMIUM` | "$630", "$900" | USD | Premium per contract |
| `DIRECTION` | "BULLISH" | enum {BULLISH, BEARISH} | Directional classification |
| `ORDER TYPE` | "Sweeps" | enum {Sweeps, Block, …} | Execution class |
| `OTM%` | "104%", "134.8%" | percent | Strike distance |
| `DIRECTIONAL` | label/value | enum/score | Distinct labeled field beyond DIRECTION (unresolved) |

### 3.3 Inspector — legacy FLOW BREAKDOWN (flow_2 only)
Additional/alternate metrics observed only in the legacy generation:
| Field | Displayed as | Semantics (inferred) |
|---|---|---|
| `CONTINUITY` | percent | Flow persistence/consistency across prints |
| `ORACLE TYPE` | "DIRECTIONAL" | Flow-pattern classification enum (implies others: CONTRARIAN/ACCUMULATION/…) |
| `BIAS INTEREST` | value | Directional bias / weighted-interest metric |
| `RV/OI` | ratio | Relative volume to open interest (liquidity/conviction) |
| `ENTRY RATIO` | "43.3%" | Ratio of aggressive entries vs total flow events |
| `SCOUT` | "$1.02" / "$1.5M" | Unresolved per-contract / scan sub-metric |
| `CONTINUITY / BULL / BEAR` counts | "1,348", "38" | Bull/bear split counts (likely OI or contract counts) |
| `FLOAT` / `Flow Next` | "24" | Unresolved (float coverage / next-event count) |

### 3.4 Left-rail aggregates
| Field | Displayed | Semantics |
|---|---|---|
| Index premium (SPY/QQQ) | "$472.2M", sparkline | Per-index total option premium + trend |
| Bull / Bear / Net premium | "Bull $221.5M · Bear $228.1M · Net -$23.4M" | Directional premium split + net |
| Call premium | "$317M" | Aggregate call premium |
| Put premium (PC) | "$1653M" | Aggregate put premium |
| PC Ratio | "0.46" | Put/call ratio |
| Watchlist best score | integer 0–100 | Per-ticker daily max conviction score |

---

## 4. Scoring / Legend / Tier Semantics (verbatim)

### 4.1 Conviction score
> "The big number on each card is Oracle's **conviction score** (0 to 100), a proprietary read on how
> meaningful the trade is. Only trades scoring 60 and above show by default." (guide, verbatim)

- Integer 0–100, Oracle-computed.
- Default feed display threshold = **60+** (note: filter UI shows a **50+** band option; 50–59 = LOW
  tier exists but hidden by default).
- Score **color encodes direction, not tier**: green = bullish, red = bearish.

### 4.2 Tiers (verbatim table)
> "The tiers:"

| Badge | Label | Description (verbatim) |
|---|---|---|
| **90+** | ELITE | top conviction, strongest historical edge |
| **80–89** | STRONG | institutional-grade conviction |
| **70–79** | HIGH | high-conviction directional flow |
| **60–69** | MED | moderate, context-dependent |
| **50–59** | LOW | weak standalone edge |

> "The score color matches direction: green for bullish, red for bearish. The bullish side is
> empirically predictive (average peak return rises with the tier). Bearish reads carry less edge in
> the current market regime, so treat them as a lean." (verbatim)

**Directional-edge asymmetry is a first-class product claim:** bullish tiers are backtested-predictive
(mean peak return rises with tier); bearish is a "lean" only. Implies per-tier historical return
tracking exists.

### 4.3 Badges (verbatim definitions)
> "Badges flag the trade's footprint:"

| Badge | Definition (verbatim) |
|---|---|
| **SWEEP** | "an order split across multiple exchanges and filled aggressively. It signals urgency, someone wanted in (or out) right now." |
| **WHALE** | "a trade large enough to clear Oracle's institutional-size gate. Whale prints tend to lead rather than chase." |
| **CLUSTER** | "several related trades grouped together (accumulation, distribution, or iceberg behavior)." |

Additional badge strings observed on cards/inspector: **UNUSUAL**, **BLOCK**. (Study source hints
also mention golden/floor/multileg.) Multiple badges co-occur on one trade (e.g. UNUSUAL + SWEEP +
BLOCK on SEDG). **Filterable badges** = Sweeps, Whale only; CLUSTER/UNUSUAL/BLOCK are display-only.

### 4.4 Reading-a-card field legend (verbatim)
> "**Symbol & type**: the ticker and whether it was a call or a put."
> "**Direction** [BULL][BEAR]: … A bought call or a sold put reads BULL; a bought put or a sold call
> reads BEAR."
> "**Premium**: total dollars spent on the trade. Bigger premium means more capital committed."
> "**S/OI**: trade size versus existing open interest. When size is well above OI it is likely a new
> position, not a close."
> "**Execution**: filled near the ask (aggressive, buyer-led) or near the bid (passive)."
> "**Spot**: the underlying's price at the moment the trade printed…"
> "**Strike distance**: how far the strike sits in-the-money (ITM) or out-of-the-money (OTM)."

### 4.5 Quick-tips heuristics (verbatim)
> "• Focus on scores above 75 for the strongest signals"
> "• A high S/OI ratio with a sweep badge is the highest-urgency footprint"
> "• Whale-gated bullish prints in a strong tier carry the best historical edge"
> "• Expand a card to check size versus open interest before acting"
> "• Check the flow drift chart in the Inspector to see the 5-day directional trend"
> "For questions, contact admin@momoedge.ai"

### 4.6 Colour semantics (global)
- Teal/cyan = active nav / selected filter chip / active guide section / selected feed row.
- Green = bullish / call / uptrend / positive premium arrow.
- Red/orange = bearish / put / negative.
- Yellow/orange premium value = unusually large premium (sweep/block magnitude).
- Badge colors: UNUSUAL ≈ yellow, SWEEP ≈ white, BLOCK ≈ purple/blue (approximate, from screenshots).

---

## 5. States & Interactions

### 5.1 Feed & cards
- **Row/card select:** click a card or its score badge → highlights the row (teal) → Inspector loads
  that trade. Selection is single-active.
- **Card expand:** guide references an "expand" action beyond select ("Expand a card to check size
  versus open interest") — expansion surfaces full detail in the Inspector.
- **Live update:** feed is newest-first, streams as trades print; `NNN SIGNALS` count reacts live to
  filter state; footer shows staleness ("STALE — 11M ago") and active-signal count.

### 5.2 Watchlist
- **Star toggle** on a card → follows ticker → appears in left Watchlist with best live daily score;
  **syncs to account** (server-side persistence).
- **Watchlist row tap** → filters feed to that ticker; **tap again** → clears filter.
- **Empty state:** "WATCHLIST" heading + placeholder "Star a ticker to add it here" (legacy variant:
  "Add to Your Watchlist" CTA).

### 5.3 Flow Guide drawer (tutorial overlay)
Full-height right-side drawer opened by FLOW GUIDE. Header "FLOW GUIDE" + **× CLOSE**. Accordion with
6 sections (single-expand; active section = teal left border + teal header/icon):

1. **WHAT THE FLOW TAB SHOWS** — three-column explanation (icon: waves ~)
2. **READING A FLOW CARD** — field legend §4.4 (icon: clipboard)
3. **CONVICTION SCORE & TIERS** — score + tier table §4.1–4.2 (icon: target/circle)
4. **SWEEPS, WHALES & BADGES** — badge defs §4.3 (icon: lightning)
5. **WATCHLIST (LEFT)** — watchlist mechanics §5.2 (icon: chart-up)
6. **QUICK TIPS** — heuristics §4.5 + contact (icon: lightbulb)

### 5.4 Filters
- Filters ▾ toggles the panel; segmented groups are single-select, FLAGS are multi-select, PREM ≥ is
  free numeric. Reset returns all to defaults. Views button applies saved filter presets.

### 5.5 Empty / edge states
- Watchlist empty state (above). Feed empty state (no trades pass filters) not captured — see §7.
- Market-session state drives footer copy: `MARKET CLOSED` vs `ENGAGED`/live.

### 5.6 Keyboard shortcuts
None observed. See §7.

---

## 6. Engine Inferences (thresholds / formulas / components)

- **Score band cutoffs:** 90 / 80 / 70 / 60 / 50 define ELITE/STRONG/HIGH/MED/LOW. Default hide < 60.
  Filter bands at 50/60/70/80/90.
- **Direction classifier:** `direction = f(buy_sell, call_put)` → {bought call, sold put}=BULL;
  {bought put, sold call}=BEAR. Server `trade_dir` authoritative; falls back to execution side +
  option type (study §11).
- **S/OI (size/OI):** `size ÷ open_interest`; ≫1 ⇒ new position. Counter-evidence that score ≠ pure
  S/OI: BE scored 94 with size 25 / OI 100 (S/OI 0.25).
- **Whale gate:** an institutional-size threshold (dollar/contract) that WHALE prints must clear
  (exact value unknown).
- **Cluster / Chain Heat:** groups related same-ticker/contract/time prints. Study §17 notes a
  contract-day accumulation threshold of **≥ $3M** and 2-minute polling for the chain-heat feed.
- **Score ingredients (study-inferred, not shown):** premium magnitude, size/OI, sweep/block/floor/
  multileg flags, moneyness, DTE, IV, execution side, direction, relative premium, possible MACD/
  technical context (`score_v2_macd`), historical score-expectation bands. Multiple score generations
  stored server-side (score, score_v2, score_v2_macd, score_v3_1, score_v4, score_v5…).
- **Per-tier historical return:** "average peak return rises with the tier" ⇒ tier→backtested-return
  mapping maintained, bullish-only edge.
- **Flow drift chart:** 5-day directional-trend series per ticker in Inspector.
- **Total premium / P-C:** call premium, put premium, P/C ratio, per-index bull/bear/net premium.

---

## 7. Gap List — Unknowns a Builder Must Decide or Confirm from Source

### Generation conflicts to resolve
1. **Two Inspector designs.** Canonical (flow_1): CALL badge + tier badges + score + FLOW BREAKDOWN
   {TOTAL PREMIUM, #CONTRACTS, AVG PREMIUM, DIRECTION, ORDER TYPE, OTM%, DIRECTIONAL}. Legacy (flow_2):
   BUY/SELL/BEAR/OTHER tabs + {CONTINUITY, ORACLE TYPE, BIAS INTEREST, RV/OI, ENTRY RATIO, SCOUT}.
   **Decide which is the target** (recommend flow_1) and whether legacy metrics carry over.
2. **Feed row column set differs by generation.** flow_1: TICKER|TYPE|PREMIUM|STRIKE|EXPIRY|OTM|TIME|
   SCORE|badges. flow_2: checkbox|Ticker|Premium|Shares|Contract|DTE|Strike|Type|Score. Confirm the
   authoritative column model (and whether a row-checkbox/multi-select exists — only in legacy).
3. **Score default: 50+ vs 60+.** Filter UI offers a 50+ band, but the guide states default display
   is 60+. Confirm whether 50–59 (LOW) is reachable only by explicitly selecting the 50+ band.

### Undefined / unresolved fields
4. **`FLOW DIR SD` / `DIRECTIONAL`** — exact definition and value range unknown.
5. **`ORACLE TYPE` enum** — only "DIRECTIONAL" observed; full enum (CONTRARIAN/ACCUMULATION/…?) unknown.
6. **`SCOUT`, `FLOAT`, `Flow Next`, `BIAS INTEREST`, `ENTRY RATIO`, `CONTINUITY`, `RV/OI`** — legacy
   metric formulas/units unconfirmed.
7. **Whale institutional-size gate value** and **Chain-Heat / Cluster grouping window** — thresholds
   not surfaced ($3M contract-day figure is study-inferred, needs source confirmation).

### Behaviors not captured in screenshots
8. **Full filter set.** Study lists DTE, moneyness, expiry, premium max, execution label, grade tier,
   side, size/OI, size/vol, volume, OI, IV, underlying-move filters + saved views — none seen in the
   6-group panel. Confirm which are shipped vs latent.
9. **Sort options beyond newest/score.** Study implies premium/size/S-OI/move/DTE/IV sorts; UI shows
   only a newest↔score toggle. Confirm sort surface.
10. **Saved "Views" mechanics** — how presets are created/named/edited/deleted; are they per-account.
11. **Card-expand vs card-select** — are these two distinct interactions or one? Guide mentions both.
12. **Empty feed state** and **loading/streaming state** copy — not captured.
13. **Smart Money Radar / Flow Gauge as distinct widgets.** Study §14–15 name a Smart Money Radar
    (front-of-flow high-score surface) and a Flow Gauge; screenshots only show TOTAL OPTION PREMIUM
    (gauge-equivalent) in the left rail. Confirm whether Radar is a separate panel/tab on this surface.
14. **Ask Oracle for Flow** (study §18) — a per-row "why is this flagged" explainer; not visible in
    these screenshots. Confirm presence/placement on the Flow surface.
15. **Keyboard shortcuts** — none observed; confirm none exist.
16. **Mobile layout specifics** — no mobile screenshots; the stacked/chip adaptation is study-inferred.
17. **Badge color mapping** (UNUSUAL/SWEEP/BLOCK) — approximate from OCR; confirm exact palette.
18. **`OPTIONS: $8-98.85` footer field** — meaning unresolved.
