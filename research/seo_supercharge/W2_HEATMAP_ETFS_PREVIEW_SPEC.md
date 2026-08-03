# W2 — `china_heatmap.html` + `etfs.html` anonymous tier-previews: design spec

*Design-spec-first deliverable for SEO Supercharge W2 (`research/SEO_SUPERCHARGE_MASTERPLAN_BY_FABLE.md`,
adjudications A1 + A4 + A5). Pinned 2026-08-03 by `designer` (opus). The builder implements this
without design judgment: palette, type, layout, copy and the free/walled line are all decided here.
Follows the W1b pattern-setter (`research/seo_supercharge/W1B_BASKETS_CHINA_PREVIEW_SPEC.md`) and
its §8 commissioner rulings — the neutral-slice rule, "graded output is never free", and the
T5 breadth-only stance line are applied here as standing recipe, not re-litigated.*

**Binding inputs:** `docs/DESIGN_DOCTRINE.md` (house law — wins on conflict),
`docs/TIER_PREVIEW_PATTERN.md` (the ratified mechanism), the shipped reference
`templates/special_situations.html.j2`, and the W1b spec above.

**Reference images (LOOK AT THESE FIRST):**

| File | What it shows |
|---|---|
| `mockups/refs/seo_supercharge/china_heatmap_preview.html` | the open state, interactive, EN/中文 toggle (`?lang=zh`) |
| `mockups/refs/seo_supercharge/china_heatmap_preview.png` | anonymous state, dark, EN |
| `mockups/refs/seo_supercharge/china_heatmap_preview_zh.png` | anonymous state, dark, ZH — **the 红涨绿跌 flip is the point of this shot** |
| `mockups/refs/seo_supercharge/etfs_preview.html` | the walled state, interactive, EN/中文 toggle |
| `mockups/refs/seo_supercharge/etfs_preview.png` | anonymous state, dark, EN |
| `mockups/refs/seo_supercharge/etfs_preview_zh.png` | anonymous state, dark, ZH |

---

## §0 READ THIS FIRST — the two findings that reshape the brief

### F1 — `china_heatmap.html` ships **zero content**. It is a 51 KB empty shell.

`templates/market_heatmap.html.j2` is 76 lines: a header, `<div id="heatmap-full">`, a footer.
Every tile, every stat, the market-pulse read, the movers and the sector ladder are built at
runtime by `templates/heatmap.js` from `marketdata/<market>_heatmap.json`. Loaded without that
fetch, the page renders one sentence: *"Could not load heatmap data."* (verified —
`templates/heatmap.js:2168`).

Consequence: **flipping the boundary alone converts a 302-to-signin into a 200 that is thin
content.** That is the same soft-404 shape the program exists to undo, with a worse failure mode
(Google keeps it, and rates it thin). Masterplan gate §0.1 demands *"real above-the-fold content"*
— a client-fetched treemap does not satisfy it, and cannot be argued into satisfying it.

**Therefore the heatmap conversion is a CONTENT build, not a boundary flip.** §2.3 specifies the
server-rendered summary layer that must ship in the same PR. This is a larger build than the
brief anticipated; it is also the only version of this work that produces the SEO outcome.

### F2 — the heatmap's one walled asset is **already public on R2, today**.

The per-tile hover card's conviction read is fetched from `chinastockdata/<ticker>.json`. Every
page carries an inline shim (`site/etfs.html:18-44`, injected estate-wide) that rewrites any
same-origin fetch matching `^(…|stockdata|chinastockdata|hkstockdata|canadastockdata|…)/` to
`https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/…` — **a public R2 bucket outside Caddy's
auth boundary entirely.** Caddy's default-deny never sees the request.

Verified anonymously, 2026-08-03:

```
GET https://pub-…r2.dev/chinastockdata/601398.SS.json   → 200, 36,915 B
     conviction.band_en "Watch" · conviction.band_zh "观察" · conviction.score 36
     conviction.verdict "Buy zone — cycle turning up" / "买入区 — 周期上行"
     …plus entry_signal, signal, hold, view, alpha, ladder, risk_sizing, anticipation, mtf, cycle
GET https://pub-…r2.dev/stockdata/AAPL.json             → 200, 85,788 B   (US, same shape)
GET https://pub-…r2.dev/marketdata/china_heatmap.json   → 404             (tile map is NOT on R2)
```

This leak **pre-exists W2** — it is not created by the conversion. But the conversion makes it
materially worse: today an anonymous visitor cannot discover the ticker list without signing in;
after conversion the full 1,519-name list is public and the graded read is one predictable URL
away. **Walling the hover card while that bucket answers 200 is theatre** — the same finding
class as W1b's note N1 and the China desk's `/chinaspecialdata/special.json` precedent.

Blast radius is the whole per-ticker store family across all five markets, so this is **not a W2
fix** — it needs its own adjudication and its own PR (R2 bucket policy, or signed URLs, or moving
the graded block out of the per-ticker file). §5.1 gates W2 on that decision, it does not
silently absorb it. **Flagged for the orchestrator, not decided here.**

---

## §1 Collisions (checked 2026-08-03 against `docs/ACTIVE_BUILD_MAP.md` @ base `a3e6bd38`, 20 open PRs)

| Target | Collision | Verdict |
|---|---|---|
| `templates/market_heatmap.html.j2` | none — no open PR touches it | **CLEAR** |
| `scripts/build_market_heatmap.py`, `engine/market_heatmap.py` | none | **CLEAR** |
| `templates/etfs.html.j2` | none | **CLEAR** |
| `scripts/build_site.py` (builds BOTH `etfs.html` and the heatmap loop) | **#4312** and **#4300** both edit it (they collide with each other on 5 files) | **SEQUENCE** — W2's builder edits are additive (`build_etf_page`, the heatmap market loop) and disjoint from the Sector-Intelligence deep-link work, but rebase onto whichever lands first rather than racing it |
| `config/site_access.yml` + `app/deploy/Caddyfile` | **#4330** and **#4236** both edit both mirrors | **SEQUENCE** — boundary edits must be rebased; never merge W2's boundary PR with a stale copy of either matcher list |
| China Sector Intelligence consolidation (**#4299**) | touches `templates/_navlinks.html.j2`, `templates/china.html.j2` — **not** the heatmap page or template | **CLEAR** — Market Heatmap survives the consolidation as its own nav row (`_navlinks.html.j2:115`), exactly as the brief states |
| `research/DO_NOT_REBUILD.md` | no kill covers a heatmap or ETF *page surface*. The two ETF hits are signal-construction kills (regime-scorecard fusion MSP-R2; residual-reset PSS-F3) and bind nothing here | **CLEAR** |

**Doc discrepancy to report:** the brief cites a **"W1b-REDUX" section** of the masterplan
declaring the China SI surface off-limits. **No such section exists on `main`** — the masterplan
is 121 lines, still at its charter commit (#4320 / `d481dc27581`), never amended. The constraint
has been honored as given (nothing in this spec touches `china.html`, `sector_central_china`, or
the SI consolidation), but the doc it was attributed to does not carry it. Either amend the
masterplan or drop the citation.

---

# PART A — `china_heatmap.html` (+ `canada_heatmap.html`, `hk_heatmap.html`)

One template, one builder, three markets: `scripts/build_site.py:5553-5568` loops
`engine/market_heatmap.py::PAGE_META` and renders `market_heatmap.html.j2` per market with a
single context var, `mk`. The body markup is 100% market-agnostic; the only per-market branch is
the SEO block. **Everything in Part A therefore applies to all three pages unchanged** — the spec
is written family-aware, and per-market values live in `PAGE_META`, never in the template.

## A§1 Module inventory

Modules M2–M10 do not exist in the shipped HTML today — `heatmap.js` builds them from the tile
JSON at runtime. The inventory is written against the **rendered** page (screenshotted at
`http://127.0.0.1:8731/china_heatmap.html`), because that is what the free/walled question is
actually about.

| # | Module | Where | Built by | Names? | Graded? |
|---|---|---|---|---|---|
| M1 | Header — h1, glance sentence, `?` methodology tip, delay badge | `market_heatmap.html.j2:50-59` | Jinja | no | no |
| M2 | **Market pulse** — state chip + plain read + as-of | `#hx-pulse` | `heatmap.js:1441 renderPulse` | no | no — breadth arithmetic |
| M3 | **Four stat cards** — breadth (adv/dec + bar + counts + scope), median move, strongest sector, weakest sector | `#hx-stats` | `heatmap.js:1470 renderStats` | sector names only | no |
| M4 | Timeframe bar — 16 windows (5M…1Y), `default_tf` `1D` | control row | `heatmap.js` | — | no |
| M5 | Sort control — Market cap · Biggest move · A–Z | control row | `heatmap.js` | — | no |
| M6 | **The treemap** — sector → stock tiles, 1,519 CN / 218 CA / 158 HK, sized by market cap (CN/CA) or avg dollar turnover (HK) | `#heatmap-full` | `heatmap.js` | every ticker + name | no — returns and size |
| M7 | Sector-header hover → member list | treemap | `heatmap.js` | ticker names | no |
| M8a | Tile hover card — **base**: symbol, name, sector, size, current %, timeframe strip, "View full analysis →" | `.hm-c` | `heatmap.js:466 cardBaseHtml` | yes | no |
| M8b | Tile hover card — **enriched**: `conviction.band` + `conviction.score` (0–100) + `conviction.verdict`, `tech.price`, `tech.pct_vs_200dma` | `.hm-c-body` | `heatmap.js:494 enrichCard`, fetches `chinastockdata/<T>.json` | yes | **YES — the only graded surface on this page** |
| M9 | Biggest gainers / Biggest losers — 5 + 5 | below treemap | `heatmap.js:1520` | yes | no |
| M10 | Sector leaders & laggards — 12 sectors, shared-scale bars | below treemap | `heatmap.js` | no | no |
| M11 | Footer disclaimer + `?` tip (binning, sizing, conviction caveat) | `market_heatmap.html.j2:63-65` | Jinja | no | no |
| M12 | "View full analysis →" → `https://app.mastermind-x.com/terminal?symbol=<T>` | hover card | `heatmap.js` | — | external app, own auth |

## A§2 FREE vs WALLED adjudication (policy A4)

**The line, in one sentence:** *the whole map is market context and opens; the one thing we
grade — our read on a single name — stays behind the wall.*

### A§2.1 The verdict: **no page-level wall.** The brief's invited outcome, with one exception.

A heatmap of market performance is almost entirely market context, and the honest module
inventory says so: **M1–M7 and M9–M11 are all free.** Returns, breadth, median move, sector
strength, market-cap sizing, movers — every one of these is *how the market traded*, which A4
puts on the free side without argument. There is no ranked best-first board to protect, no
constituent list that is ours rather than the exchange's, and no stance we compute.

The exception is **M8b**, and it is not a technicality: `conviction.band` / `score` / `verdict` is
a graded 0–100 call with a plain-word verdict string on a single name. That is signal authority
under A4, full stop. It is also — usefully — already isolated in a *separate fetched file*, so
the split needs no build-split work at all: the free card renders from the tile JSON the page
already holds, and the enriched block simply never arrives.

So this page gets **one `.gate-note`, one micro-wall inside the hover card, and one foot CTA row.
No `.tier-wall`, no skeletons, no inert controls.** Five walls on a page whose content is free
would be nagging (Doctrine Law 4), and a `.tier-wall` over a treemap that is free would be a lie.

### A§2.2 The table

| # | Module | Verdict | Exactly what ships free | A4 rationale |
|---|---|---|---|---|
| M1 | Header | **FREE** | all | page furniture; the glance sentence is the stance (Law 1) |
| M2 | Market pulse | **FREE** | state word + full read + as-of | breadth arithmetic over public closes — market context, and this is the page's T5 stance line (A§6) |
| M3 | Stat cards | **FREE** | all four, real numbers | adv/dec, median, sector extremes — market facts |
| M4 | Timeframe bar | **FREE, live** | all windows present in `data.timeframes` | re-slices data the visitor already holds; reaches nothing withheld |
| M5 | Sort control | **FREE, live** | all three | same test |
| M6 | Treemap | **FREE** | every tile, every sector | returns + market-cap sizing = market context. **This is the product; withholding it would leave nothing** |
| M7 | Sector-header hover | **FREE** | member lists | names are exchange facts, not our output |
| M8a | Hover card, base | **FREE** | symbol, name, sector, size, %, timeframe strip | facts already in the tile JSON |
| M8b | Hover card, enriched | **WALLED** | nothing — replaced by the locked slot (A§4.2) | 0–100 score + graded verdict = signal authority |
| M9 | Movers | **FREE** | both lists, 5 + 5 | biggest movers are a market fact, not a ranking of ours |
| M10 | Sector ladder | **FREE** | all 12 sectors | sector returns |
| M11 | Footer disclaimer | **FREE** | always | honesty is never behind a wall |
| M12 | Analyzer link | **FREE, unchanged** | the link | external host, its own auth — see A§7 T-A3 |

**Note on `tech.price` / `tech.pct_vs_200dma`.** Both are market facts, but they ride inside the
walled per-ticker file. The free card therefore shows market cap (from the tile JSON) rather than
last price, and drops the "vs 200d" tag. Flagged as **T-A2** — a reviewer could reasonably ask for
a slimmed public per-ticker file that keeps the facts and drops `conviction`; that is the cleaner
long-run answer and it is also the natural fix for F2.

### A§2.3 The SSR content layer — **the load-bearing addition** (see §0 F1)

The builder must server-render, into `market_heatmap.html.j2`, the summary that `heatmap.js`
computes client-side. Same numbers, same copy, computed in Python from the same JSON the builder
already writes (`scripts/build_market_heatmap.py:286` writes it; read it back, or return the
summary from `engine/market_heatmap.py::build_market_heatmap()`).

Ships as static HTML, in this order, immediately after M1 and **before** `#heatmap-full`:

| SSR block | Content | Est. bytes |
|---|---|---|
| M2 Market pulse | state word, breadth %, median, strength/weakness sector phrase, as-of | ~0.6 KB |
| M3 Stat cards | 4 cards, real values, the breadth bar + counts + scope line | ~1.4 KB |
| M10 Sector ladder | all 12 sectors, name + % + shared-scale bar | ~2.2 KB |
| M9 Movers | Biggest gainers 5 + Biggest losers 5, code + name + % | ~1.6 KB |
| **total** | | **~5.8 KB** |

`heatmap.js` then **replaces** these blocks on hydration (it already computes all four —
`renderPulse`, `renderStats`, and the movers/ladder renderers) so a live-feed refresh still
updates them. The SSR copy is the crawlable floor; the JS copy is the live truth. Mount points
keep their existing ids so no renderer changes.

**Why this and not `<noscript>`:** a `<noscript>` block is invisible to a JS-executing crawler and
duplicates content for the rest. Server-rendering the real thing is simpler and is what the other
desks already do.

**Why these four and not the treemap:** 1,519 SSR tiles would add ~180 KB for content Google
cannot read as prose anyway. The four summary blocks carry the entity-bearing nouns (sector names,
ticker codes, company names, "A-share", "Shanghai + Shenzhen") in crawlable text at 3% of the
cost. The treemap stays client-rendered.

### A§2.4 The tile JSON must become public

`marketdata/china_heatmap.json` (355 KB), `hk_heatmap.json` (36 KB), `canada_heatmap.json`
(43 KB) are today default-deny (absent from every allowlist). They carry only returns and sizing
— A4-free — and without them the treemap never draws for an anonymous visitor. **Add all three to
`public.exact`.** Flagged as **T-A1**: this hands a clean 1,519-row A-share returns dataset to any
scraper. It is the same data the page displays, on a daily-close cadence, with the delay disclosed
— so it is free by policy — but it is a deliberate give and the orchestrator should register it.

`marketdata/sp500_heatmap.json` is already handled separately (`Caddyfile:142`, `@vps_external`)
and is **out of scope** — do not touch it.

## A§3 Page weight

| | Today | After |
|---|---|---|
| `china_heatmap.html` | 51.2 KB (0 content) | ~57 KB (+5.8 KB SSR) |
| `canada_heatmap.html` | 51.2 KB | ~57 KB |
| `hk_heatmap.html` | 51.2 KB | ~57 KB |

**Gate at < 80 KB** per page (§A5.8). Generous headroom; the point of the gate is to stop anyone
"solving" F1 by SSR-ing the whole tile set.

## A§4 The gate design

### A§4.1 Component names and CSS transliteration

Reuse the idiom class names from `templates/special_situations.html.j2` verbatim: `.gate-note`,
`.gh`. This page needs **no** `.tier-wall`, `.tw-*`, `.gate-pill`, `.gated` or `.tw-ghost`.

**The CSS cannot be lifted verbatim.** `special_situations.html.j2` defines `--blue --ink --faint
--grid --card --surface --surface-brd --surface-shadow` locally in its own `<style>` block
(lines 19-37). `market_heatmap.html.j2` has its own token block; transliterate before pasting or
`var(--card)` resolves to nothing and the note renders transparent-but-working — the failure mode
review misses:

| special_situations | market_heatmap | dark value |
|---|---|---|
| `--card` | `--panel` | `#181b21` |
| `--grid` | `--line` | `#2a2f3a` |
| `--ink` | `--ink` | `#e8edf4` — same name, verify it is defined |
| `--faint` | `--faint` | `#6b7280` |
| `--blue` | `--link` | `#7aa7e0` dark |
| `--surface` / `--surface-brd` / `--surface-shadow` | needed only for the hover card, which already defines its own surface | — |

`#8b5cf6` (the lock violet) stays a hard-coded hex, identical to the reference. The CTA gradient
is `linear-gradient(135deg, var(--link), #8b5cf6)` — **brand blue → violet, never signal amber**
(terminal paywall lesson, masterplan W1). Introduce no other new colour.

Ready-to-paste CSS: the `/* ── gate note ── */`, `.hm-c-locked` and `.cta-row` blocks of
`mockups/refs/seo_supercharge/china_heatmap_preview.html`.

### A§4.2 The locked slot inside the hover card (the signature element)

`enrichCard()` already degrades gracefully on a missing per-ticker file — but its current stub
says *"No nightly read for this name yet — open the analyzer for the full breakdown."*
(`heatmap.js:499`). **On an anonymous build that sentence is a lie**: the read exists, it is paid.
Doctrine Law 5 (honesty survives translation) forbids shipping it as the walled state.

Two distinct empty states, both required:

```js
// heatmap.js — enrichCard(el, data, t, rec)
// rec === null has TWO causes and they are not the same sentence:
//   (a) genuinely no nightly read for this ticker  → the existing stub, unchanged
//   (b) the read exists but the viewer is not entitled (403 / gated build) → the locked slot
```

The builder passes the gate state into the mount (`data-hm-gated="1"` on `#heatmap-full`), and
`enrichCard` branches on it. Never infer the state from the fetch result alone — a network error
would then read as a paywall.

Locked-slot markup (replaces `.hm-c-body`'s contents):

```html
<div class="hm-c-locked">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
  </svg>
  <span>
    <span class="l-en">Our nightly read on this name — where it sits and what we'd do — is member content. <a href="plans.html">See plans</a></span>
    <span class="l-zh">我们对该股的每晚解读 —— 所处位置与应对方式 —— 为会员内容。<a href="plans.html">查看方案</a></span>
  </span>
</div>
```

The card keeps its header, its size/% and its full timeframe strip — the free card is a **useful
card**, not a teaser. That is the design decision worth defending: the hover is the heatmap's
entire interaction, so degrading it to an advertisement would degrade the free product itself.

### A§4.3 Copy — verbatim, EN + ZH

Glance tier throughout. No internal vocabulary, no untranslated statistics, no raw slugs, no
falsifier language. Counts are templated — **never hardcode 1,519 / 12**; membership changes
nightly and a stale honest-total is a dishonest total.

**`.gate-note`** (one only, below the treemap, `#hm-gate-note`)
- EN — `The whole map is open — every tile, every timeframe, every sector. What members add is our read on each name: where it sits and what we'd do about it.`
- ZH — `整张热力图完全开放 —— 每个方块、每个周期、每个板块。会员另可看到我们对每只个股的解读：所处位置与应对方式。`

**`.hm-c-locked`** (inside the hover card) — as in A§4.2.

**`.cta-row`** (foot, above the disclaimer, `#hm-cta`)
- EN — `**The map is free, and stays free.** Members get our nightly read on all {n_tiles} names here — plus the same maps for {sibling_markets}.`
- ZH — `**热力图免费，且将持续免费。**会员可获取我们对全部 {n_tiles} 只个股的每晚解读 —— 以及{sibling_markets_zh}的同款热力图。`
- button — EN `See plans` · ZH `查看方案` → `href="plans.html"`
- note — EN `7-day Pro trial · cancel anytime` · ZH `Pro 7 天试用 · 随时取消`

`{sibling_markets}` is computed from `PAGE_META` minus the current market — on `china_heatmap`
it renders "Hong Kong and Canada"; on `hk_heatmap`, "China and Canada". One string, three pages.

**Doctrine check.** No banned Tier-1 vocabulary anywhere: no `conviction.band` / `score` /
`turn_state` / `sig_tier` / `n=` / z-scores / raw slugs. "our read on each name" is the plain-word
pair for what is withheld. The page keeps a real stance for an anonymous reader in M2 (A§6), so it
is not stance-less (Law 1). One as-of (M2), one footnote (M11) — the CTA row carries no second
disclaimer.

## A§5 What this page does NOT need

No `/premiumdata/china_heatmap.json`. No `tier_payload.v1`. No hydration script. No inert
controls. No `.gated` containers. No skeletons.

The split is already physical: free content is in the tile JSON, paid content is in the per-ticker
files, and the server decides per-file. Adding a payload here would invent a second data path for
content that already has one — the anti-goal `docs/TIER_PREVIEW_PATTERN.md` §checklist-1 warns
about ("one source, rendered twice").

**Every control stays fully live.** The pattern's inert-controls rule exists for controls that
*reach content the free build does not have*; on this page none do. Timeframes and sort re-slice
data the visitor already holds. There is nothing to dim, and dimming it would read as a bug.

## A§6 T5 stance line — derived from non-graded data

The W1b §8 T5 ruling requires one plain-words stance sentence from non-graded inputs. **This page
already has one and it needs no invention:** M2's market-pulse read is computed from board breadth
alone (`board_breadth.pct_up`, `med_pct`, sector extremes) — zero graded inputs.

Shipped free, verbatim (values templated):

- EN — `**{pct_up}%** of names advancing · median **{median}**. Strength in {up_sectors} — weakness in {down_sectors}.`
- ZH — `**{pct_up}%** 个股上涨 · 中位数 **{median}**。资金流向：{up_sectors} 走强，{down_sectors} 走弱。`

preceded by the state chip (`Broad advance` / `普涨`, tone-tinted). This satisfies Doctrine Law 1
for an anonymous reader without leaking a gram of signal authority.

## A§7 zh 红涨绿跌 — where colour encodes direction

`theme.css:138` flips `--up`/`--down` under `html[data-lang="zh"]`. On this page **colour is the
primary encoding** — the treemap is nothing but colour — so this is the highest-stakes ZH surface
in the program.

**Every directional fill must paint from `--up` / `--down`, never a hard-coded green or red.**
That includes: treemap tile fills (bin them —
`color-mix(in srgb, var(--up) 92%|64%|38%, <tile-bg>)`, see the mockup's `.tile.u1/u2/u3` /
`.d1/d2/d3`), the breadth bar, the stat-card values, the movers percentages, the sector-ladder
bars, the hover card's `%` and timeframe strip, and the `▲`/`▼` glyphs.

**The gate elements carry no directional colour at all** — `.gate-note`, `.hm-c-locked` and the
CTA row are violet/neutral by construction. Do not tint them by state.

**Trap found while shooting the ZH reference, and it applies to both pages:** a *non-directional*
status must not ride `--up`/`--down`, or the flip inverts its meaning. Freshness dots, coverage
health, "live vs delayed" chips and any pass/fail tint are quality states, not market direction —
give them fixed semantic inks (`#1FA971` / `#f0b429` / `#e06464`) that are identical in both
languages. The first ZH render of the ETF mockup painted **"fresh" red and "stale" green**; the
committed mockup fixes it and comments why.

Verify against `china_heatmap_preview_zh.png`.

## A§8 SEO head

Today (`market_heatmap.html.j2:9-18`) the page carries **three different titles**: `<title>`
"China A-share Heatmap — Market Intelligence", `seo_title` "China A-Share Heatmap — Mastermind",
and a third description string. Unify them, brand-suffixed.

```jinja
<title>{{ mk.seo_title }}</title>
{% set seo_title = mk.seo_title %}
{% set seo_desc  = mk.seo_desc %}
{% set seo_path  = mk.key ~ "_heatmap.html" %}
```

Move the strings into `PAGE_META` (`engine/market_heatmap.py:203-234`) so the three markets stay
in sync and the template keeps no per-market `{% if %}`:

| market | `seo_title` (chars) | `seo_desc` (chars) |
|---|---|---|
| china | `China A-Share Heatmap — Live Sector Map — MastermindX` (53) | `Every liquid Shanghai and Shenzhen A-share as one sector treemap — today's winners, losers and sector breadth, sized by market cap, after each close.` (149) |
| hk | `Hong Kong Stock Heatmap — Sector Map — MastermindX` (50) | `Every liquid Hong Kong listing as one sector treemap — today's winners, losers and sector breadth, sized by average turnover, after each close.` (143) |
| canada | `Canada TSX Heatmap — Sector Map — MastermindX` (45) | `Every liquid TSX listing as one sector treemap — today's winners, losers and sector breadth, sized by market cap, updated nightly.` (130) |

All titles ≤ 70 ✅, brand-suffixed ✅. All descriptions inside 50–170 ✅. Each leads with the
entity-bearing nouns a searcher types ("A-share", "Hong Kong stock", "TSX", "heatmap", "sector")
rather than with product vocabulary.

- **Canonical** — `_seo_head.html.j2:22` emits `https://www.mastermind-x.com/<seo_path>` from
  `seo_path`. Self-canonical ✅. Verify it survives to the baked bytes.
- **No `noindex` meta** exists in the template today — but `app/deploy/Caddyfile:259` (`@reg_html`)
  sets `X-Robots-Tag: noindex, noarchive` on the served response. **That header is why the page
  reads as a soft 404 to Googlebot.** Gate §A9.1 is not satisfied by a 200 alone — check the
  response headers.
- **JSON-LD:** none today. Out of scope for W2; note it for W3.
- All three pages enter `sitemap.xml` (`lib/seo.py::is_public_path()` gates on
  `config/site_access.yml`, so they appear automatically once public — verify, don't assume).

## A§9 ACCEPTANCE GATES — "not done unless" (adapted from masterplan §0.1-7)

1. **Anonymous `curl https://www.mastermind-x.com/china_heatmap.html` → 200**, self-canonical, no
   `noindex` **in the response headers** (not just the markup), and the SSR summary layer present
   in the raw bytes — grep the response for the breadth %, the median, a sector name and a mover
   ticker **with JS disabled**. Same for `hk_` and `canada_`.
2. **`marketdata/{china,hk,canada}_heatmap.json` → 200 anonymous** (they must be public, A§2.4),
   proven with `curl -H 'X-Original-Uri: /marketdata/china_heatmap.json' …/api/paywall/check` → 204.
3. **`chinastockdata/<T>.json` → 403 anonymous *at the origin*** — and **§0 F2 resolved or
   explicitly deferred by the orchestrator in writing.** If the R2 bucket still answers 200 for
   `chinastockdata/601398.SS.json`, the M8b wall is decorative and this gate is NOT met by an
   origin-only 403. State the R2 status in the PR body either way.
4. **Boundary edited in ALL THREE mirrors in one PR** — `app/regwall.py` + `app/deploy/Caddyfile`
   (every matcher list) + `config/site_access.yml`. Run `tests/test_site_access_boundary.py` and
   the `tier-gate` suite LOCALLY and paste the output (ci.yml may not run them on these paths).
5. **All three pages added to `sitemap.xml`** in the same PR; verify the builder picks them up.
6. **Live verification post-merge:** anonymous curl 200 + the paywall-check probes + a Googlebot-UA
   fetch byte-comparable to a normal UA.
7. **Render-lane law:** never hand-bake locally. The heatmap loop rides `scripts/build_site.py` →
   `render.yml` scope `macro`; dispatch the scoped render.
8. **Page weight < 80 KB** for each of the three shells. Assert it in a test.
9. **Twin parity test:** a hermetic test renders all three markets and asserts the SSR block is
   present, non-empty and market-correct in each — the twins are the most likely silent casualty
   of a China-only fix.
10. **Two empty states proven** (A§4.2): a hermetic test that a gated build renders the locked slot,
    and an ungated build with a genuinely absent per-ticker file still renders the *"no nightly
    read yet"* stub. Shipping one sentence for both causes is the defect.
11. **NO edits to the tier catalog** (collision #4176/#4185). Existing classes only.
12. **Visual artifact in the PR body:** anonymous EN + anonymous ZH + entitled, all dark, cropped
    to the treemap and the hover card. Compare against the reference PNGs.

---

# PART B — `etfs.html`

Built by `scripts/build_site.py:2925 build_etf_page()`, rendered from `templates/etfs.html.j2`
(572 lines), 282,260 bytes shipped. **Fully server-rendered — every graded row is in the HTML
markup, and no browser-fetched JSON duplicates it.** That makes this the clean case for the
ratified build-split.

**The brief expected a "cross-asset ETF desk" with flows/performance context. It is not that.**
`etfs.html` is a **13F/fund-holdings conviction desk**: which stocks tracked fund managers are
accumulating, ranked by cross-fund agreement, with an explicit `what to do` stance column. The
free/walled split is correspondingly harsher than "flows free, calls walled" — most of this page
is our graded output.

## B§1 Module inventory

Byte shares measured directly off the built file.

| # | Module | Template | Rows | Bytes (share) | Graded? |
|---|---|---|---|---|---|
| M0 | `<head>` + shared nav | `:284` | — | 45,671 (16.2%) | — |
| M1 | Hero — h1, tagline, **verdict line**, as-of + universe tip, **3 tiles** | `:288-316` | 3 tiles | 3,279 (1.2%) | verdict line **yes**; tile 1 **yes** (top ticker + stance); tiles 2–3 no |
| M2 | **The consensus board** — rank, stock, funds-in dots + "who" popover, net conviction pp + bar, NEW/EXIT/SPLIT/ACTIVE MGR flags, **stance pill** | `:318-364` | 40 | 83,328 (**28.8%**) | **YES — the ranked headline board** |
| M3 | **Fresh conviction** — brand-new positions, fund chips, stance pill | `:366-391` | 8 cards | 10,349 (3.5%) | **YES** |
| M4 | **The market they're buying into** — risk backdrop (regime + 4 legs), sector leadership (11 GICS rows, 60d momentum), style rotation (5 pairs) | `:393-447` | 20 | 9,734 (3.2%) | no — descriptive momentum context |
| M5 | **Every add, by fund** — stock, fund·theme, conviction pp, sparkline, stance pill | `:449-491` | 40 | 63,127 (**21.7%**) | **YES** |
| M6a | Shelf — **Being trimmed** (collapsed `<details>`) | `:495-521` | 12 | part of 61,418 (21.4%) | **YES** |
| M6b | Shelf — **Coverage & freshness** (collapsed `<details>`) | `:523-555` | **77** | most of the 61,418 | no — operational transparency |
| M7 | Disclosure footer — "How to read this" + "Coverage" | `:558-563` | — | 1,728 (0.5%) | no |

## B§2 FREE vs WALLED adjudication (policy A4)

**The line, in one sentence:** *which funds we watch and the market they are buying into is free;
which names they are buying, and what we would do about them, is paid.*

This is the China Special Situations cut restated — *"state and totals are free, names are paid"*
(`docs/TIER_PREVIEW_PATTERN.md`).

### B§2.1 No preview slice on either board

M2 sorts by breadth-of-agreement then conviction; M5 sorts by conviction descending. Both are
**best-first**. `docs/TIER_PREVIEW_PATTERN.md` is explicit — *"the ranked 'top N by magnitude'
boards get no preview at all, because previewing a best-first board hands over its head, which is
the part people pay for"* — and W1b §8 T1 ruled the same way. **Zero rows preview from M2, M3, M5
or M6a.**

Unlike `baskets_china`, there is no neutral re-slice available here: the board has no categories
to take "first two of each" from, and its row identity *is* the rank. So the free tier's value
comes from the context modules and the honest totals, not from a row sample.

### B§2.2 The table

| # | Module | Verdict | Exactly what ships free | A4 rationale |
|---|---|---|---|---|
| M1 h1 + tagline + as-of | **FREE** | all, incl. `Tracking {n_funds} curated & active funds` and the universe `?` tip | page furniture + an honest total |
| M1 verdict line | **WALLED → REPLACED** | the T5 stance line (B§6) in its place | today's line names the sectors managers are building into — a summary of the graded board |
| M1 tile 1 "Strongest consensus" | **WALLED → REPLACED** | `On the board` / `上榜个股` = `{total}` names, sub "names at least two funds are building at once" | a ticker + stance pill is the board's head. The replacement is an honest total — see **T-B1** |
| M1 tile 2 "Fresh conviction" | **FREE** | the count `{n_fresh}` | a count without names |
| M1 tile 3 "Market backdrop" | **FREE** | regime label + read | rotation context, same class as M4 |
| M2 Consensus board | **WALLED** | h2 + lede + `.gate-pill` + `.gate-note` + 5 `.gh` skeleton rows | the ranked graded board |
| M3 Fresh conviction | **WALLED, OMITTED** | nothing, heading included | 8 graded cards; a second ghost stack directly under M2's would be nagging (Law 4) |
| M4 Rotation backdrop | **FREE, in full** | risk backdrop, all 11 sector rows, all 5 style pairs, the disclaimer | descriptive momentum over public ETF prices — market context, and the page's own subtitle already says "never a buy list" |
| M5 Every add, by fund | **WALLED** | h2 + lede + `.gate-pill` + the **one `.tier-wall`** | per-fund graded adds |
| M6a Being trimmed | **WALLED, OMITTED** | nothing | graded, and explicitly secondary |
| M6b Coverage & freshness | **FREE, in full, `<details open>`** | all {n_funds} rows: fund, name, theme, snapshots, latest, freshness | pure operational transparency — no score, no ranking, no call. **See B§2.3** |
| M7 Disclosure footer | **FREE** | both paragraphs | honesty is never behind a wall |

### B§2.3 Why Coverage & Freshness is the free tier's anchor — and opens by default

It is the single best free asset on this page and it is currently hidden in a collapsed
`<details>` at the bottom. It is 77 named funds — SPDR, Global X, VanEck, First Trust, Sprott,
Amplify, Defiance, Bitwise, ARK, Invesco, Roundhill — each with a theme, a snapshot count and a
freshness state. For a crawler that is a dense, entity-rich, wholly honest block naming the
institutions people actually search for. For a visitor it answers "do these people really track
this?" better than any marketing sentence.

**On the gated build it ships `<details open>`.** It stays a `<details>` (so the entitled page is
unchanged in structure) but the free build opens it, because it is the free tier's substance.

Flagged as **T-B3** — this is the one place where the gated and ungated builds differ in a way a
reader could notice beyond the wall itself. The alternative (leaving it collapsed) buries the free
tier's best content behind a click a crawler may not take.

### B§2.4 Field-level split

The free build must **not** render the withheld rows at all — no `display:none`, no CSS blur, no
JS tier check over baked rows. `docs/TIER_PREVIEW_PATTERN.md` anti-goal 2; one `view-source` away
otherwise.

`build_etf_page()` currently renders with `accumulation`, `trims`, `favored`, `coverage`, `pulse`,
`board`. On a gated build:

| Keep (free) | Drop (paid) |
|---|---|
| `coverage` (all rows) · `pulse` (whole object) · `board.regime` / `board.backdrop` · counts: `len(favored)`, `n_fresh`, `len(accumulation)`, `len(coverage)` | `favored` (all 40) · `accumulation` (all 40) · `trims` (all 12) · `board.verdict` · `board.tiles[0]` · the fresh-conviction card list |

### B§2.5 Weight budget

| Block | Today | Free shell |
|---|---|---|
| M2 consensus board | 83.3 KB | ~1.6 KB (skeletons) |
| M5 every-add table | 63.1 KB | ~1.4 KB (wall + ghosts) |
| M3 fresh conviction | 10.3 KB | 0 |
| M6a trims | ~10 KB | 0 |
| M6b coverage (77 rows) | ~51 KB | ~51 KB (kept) |
| M0 + M1 + M4 + M7 | ~60 KB | ~60 KB |
| **page total** | **282 KB** | **~116 KB** |

**Gate at < 140 KB** (§B9.8) to leave the builder headroom.

## B§3 The wall design

### B§3.1 One wall, one note, value first

Reference discipline: **one `.tier-wall` + one `.gate-note`** (W1b §3.1). Placement is the whole
design decision, because M2 (walled) sits above M4 (free) in DOM order:

- **`.gate-note`** above M2's skeletons — it explains, it does not sell. **No CTA button.**
- **the single `.tier-wall`** at **M5**, *after* the reader has had the full rotation backdrop.
- **Do not reorder the DOM between builds** (W1b anti-goal 9). The desk region gets skeletons and
  a note; the one ask lands later.
- `.gate-pill` on the two walled section headings (M2, M5).

### B§3.2 CSS transliteration

`templates/etfs.html.j2:56-280` is a 224-line inline `<style>` block (externalized post-render to
`site/assets/css/<hash>.css`). Its token vocabulary differs from `special_situations.html.j2`'s —
transliterate before pasting, same trap as A§4.1. Map `--card`→ the page's panel token,
`--grid`→ its line token, `--blue`→ its link token; keep `#8b5cf6` hard-coded; CTA gradient
`linear-gradient(135deg, var(--link), #8b5cf6)`, never amber.

Ready-to-paste: the skeleton / `.gate-note` / `.tier-wall` blocks of
`mockups/refs/seo_supercharge/etfs_preview.html`.

### B§3.3 Markup — the `.tier-wall` at M5

Structurally identical to `special_situations.html.j2:543-573`:

```jinja
{% if gate %}
<div class="tier-wall" id="etf-tier-wall">
  <div class="tw-ghosts" aria-hidden="true">
    {% for _ in range(4) %}
    <div class="tw-ghost"><div class="gh gh-tkr"></div><div class="gh gh-line"></div><div class="gh gh-line short"></div></div>
    {% endfor %}
  </div>
  <div class="tw-card">
    <svg class="tw-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
    <div class="tw-h">
      <span class="l-en">{{ gate.n_buys }} individual buys, across {{ gate.n_funds }} funds, are open to members</span>
      <span class="l-zh">来自 {{ gate.n_funds }} 只基金的 {{ gate.n_buys }} 笔买入向会员开放</span>
    </div>
    <div class="tw-p">
      <span class="l-en">You’re reading which funds we track and the market they’re buying into. Members also get
        every name on the consensus board, each fund’s strongest adds, what’s being trimmed, and what we’d do
        about each one.</span>
      <span class="l-zh">你正在查看我们追踪的基金以及它们所买入的市场。会员另可获取共识看板上的全部个股、
        每只基金的最强增持、正在减持的仓位，以及我们对每一项的应对建议。</span>
    </div>
    <div class="tw-acts">
      <a class="tw-btn" href="plans.html">{{ t('See plans', '查看方案') }}</a>
      <span class="tw-note">{{ t('7-day Pro trial · cancel anytime', 'Pro 7 天试用 · 随时取消') }}</span>
    </div>
    <div class="tw-signed" id="etf-tw-signin" hidden>
      <a href="#" data-act="signin">{{ t('Already a member? Sign in', '已是会员？登录') }}</a>
    </div>
  </div>
</div>
{% endif %}
```

**Four ghosts, not three** — with three, the absolutely-positioned `.tw-card` overflows the ghost
stack and overlaps the section lede above it. Verified in the mockup; the fix is the fourth ghost.

Every count (`gate.n_buys`, `gate.n_funds`, `total`, `n_fresh`) is computed by the builder from
the real board. **Never hardcode 40 / 77 / 92 / 17.**

### B§3.4 Copy — verbatim, EN + ZH

**`.gate-note`** (above M2's skeletons, `#etf-board-note`)
- EN — `{total} names sit on the board, ranked by how many funds are backing each one. Members see the names, the conviction behind them, and what we'd do about each. The rotation backdrop below is open to everyone.`
- ZH — `看板上共有 {total} 只个股，按增持基金数量排名。会员可查看个股名称、背后的信念规模，以及我们对每只个股的应对建议。下方的轮动背景对所有人开放。`

**`.tw-h` / `.tw-p` / `.tw-btn` / `.tw-note` / `.tw-signed`** — as in B§3.3.

**M1 tile 1 replacement** (`#etf-tile-total`)
- k — EN `On the board` · ZH `上榜个股`
- v — `{total}`
- m — EN `names at least two funds are building at once` · ZH `至少两只基金同时增持的个股`

**M6b lede addition** (the free build states the coverage count)
- EN — `Every tracked fund; any stale feed surfaces here. All {n_funds} shown.`
- ZH — `所有已追踪基金；任何陈旧数据源都会在此暴露。共显示 {n_funds} 只。`

**M4 disclaimer — REWRITE REQUIRED.** `etf_pulse.json` ships
`"Display-only rotation context — trailing ratio momentum across style, risk and sector ETFs."`
**"Display-only" / "display context only" is banned Tier-1 vocabulary** (Doctrine Law 2), and
making this page anonymous-public puts it in Google's index and in AI-overview extractions.
Replace, in `engine/etf_pulse.py` where `disclaimer_en`/`disclaimer_zh` are written:
- EN — `Rotation context — how style, risk and sector ETFs have been trading. Descriptive, never a buy list.`
- ZH — `轮动背景 —— 风格、风险与行业 ETF 的近期走势。描述性，非买入清单。`

Flagged as **T-B2**: this edits an engine-owned string consumed by other surfaces. Confirm no
other page depends on the exact wording before changing it.

**Doctrine check.** No banned Tier-1 vocabulary in new copy. No "validated" (CI-guarded). No
falsifier/refutation language. "conviction" survives — it is the page's own defined product term,
explained in a `?` tip, and it is not on the banned list. One as-of, one footnote.

### B§3.5 Payload shape

`site/premiumdata/etfs.json`, `schema: tier_payload.v1`.

Unlike `baskets_china` (which ships data because its modules are JS-rendered), this page is
server-rendered from Jinja partials — so it follows the **`special_situations` precedent and ships
markup**, rendered from the SAME partials as the entitled build. Extract the repeated row markup
into partials first (`docs/TIER_PREVIEW_PATTERN.md` §checklist-1): `_etf_board_rows.html.j2`,
`_etf_accumulation_rows.html.j2`, `_etf_fresh_cards.html.j2`, `_etf_trim_rows.html.j2` — each
rendering nothing but the rows it is handed, carrying no tier logic.

```jsonc
{
  "schema": "tier_payload.v1",
  "page": "etfs",
  "gated": true,
  "required_tier": "essential",
  "built": "<same stamp as the shell>",

  "total":    40,   // names on the consensus board
  "preview":  0,    // no preview slice — both boards are best-first (B§2.1)
  "locked":   40,
  "n_funds":  77,   // for the wall headline
  "n_buys":   92,   // individual adds behind the board
  "n_fresh":  17,

  "board_html":        "<!-- 40 consensus rows, from _etf_board_rows.html.j2 -->",
  "fresh_html":        "<!-- 8 fresh-conviction cards -->",
  "accumulation_html": "<!-- 40 per-fund add rows -->",
  "trims_html":        "<!-- 12 trim rows -->",
  "verdict": { "en": "…", "zh": "…" },      // the hero line the free build replaces
  "tile0":   { "…": "…" }                    // the "Strongest consensus" tile
}
```

Write it on **every** build, including the ungated one (as
`{"schema": "tier_payload.v1", "page": "etfs", "gated": false, …}`), so flipping `gated` off never
strands a readable full board at a path the page stopped asking for.

Confirm `/premiumdata/` is under `premium.enforced_early` in `config/site_access.yml` — it already
is; no Caddyfile change is needed for the prefix (`docs/TIER_PREVIEW_PATTERN.md` §Why `/premiumdata/`).

### B§3.6 Hydration

Port `special_situations.html.j2:802-882` unchanged in structure, including both traps it solves:

- **`whenAuthSettled()`** — `theme.js` is deferred, so `MDXAuth` does not exist while an inline
  script runs. Wait for the `mdx-auth` event with a 3s timeout fallback.
- **`freshSession()`** — the shared cookie carries a ~1h token, so a long-idle member can be signed
  in with a token the server rejects. Call `getSession()` before the fetch.

`hydrate(payload)` order: inject `board_html` into `#consensus-board` → inject `fresh_html` and
un-hide M3's heading → inject `accumulation_html` → inject `trims_html` → restore the hero verdict
line and tile 1 → remove `#etf-tier-wall`, `#etf-board-note` and every `.gate-pill` → re-wire the
`?` tips and the `.cb-who` popovers → `relabelAll()`. On 403 the wall stays exactly as baked, and
`#etf-tw-signin` un-hides when there is no session at all.

**Trap.** M2 and M5 both have empty-state branches (`"Building — cross-fund consensus appears once
at least two funds hold overlapping conviction…"`, `"Building — the collector writes one
full-holdings snapshot per fund per day…"`). On a gated build those would fire over content that
exists — a lie. Guard every such branch with the gate state, and keep the honest empty state
reachable for a genuinely empty board.

## B§4 Inert controls

This page has **no page-specific controls** — no filters, no search, no sort toggle, no
tablesort/stocktable/charts bundle. The only interactive elements are shared site chrome (nav
search, theme toggle, language toggle) and two pure-CSS mechanisms:

| Control | Gated build | On hydrate |
|---|---|---|
| `<details>` M6a "Being trimmed" | **not rendered** (M3/M6a omitted) | rendered, collapsed |
| `<details>` M6b "Coverage & freshness" | rendered **`open`** (B§2.3) | rendered, collapsed (entitled build unchanged) |
| `.cb-who` per-row popovers (M2) | **not rendered** — they live inside withheld rows | rendered |
| `.txq` help tooltips | live everywhere | unchanged |
| shared nav search / theme / lang | live | unchanged |

Nothing needs `.gated`. The pattern's inert-controls rule protects the entitled viewer from
ending up with no filters — there are none to lose here.

## B§5 Second doors

**None on this page.** Verified: `site/etfs.html` contains no inline `fetch(`, no
`XMLHttpRequest`, and no page-local JSON reference. Every graded row lives in the HTML markup, so
the build split alone is the gate.

Adjacent paths, named with their access class today:

| Path | Carries the walled content? | Access class today |
|---|---|---|
| `site/basketdata/etf_pulse.json` (M4 input) | no — it IS the free module's data | read **server-side only** by `_load_etf_pulse()` (`build_site.py:2913`); never browser-fetched from this page. Consider adding to `public.exact` only if a future build fetches it |
| `site/stockdata/fund_flows.json` (written by `build_etf_page`) | partially — per-stock fund-flow rows | consumed **server-side** by `engine/radar_plus.py:240` / `radar_ticker.py:152`; not fetched by this page. Rides the R2 shim's `stockdata/` prefix ⇒ **see §0 F2** |
| `stockdata/index.json` etc. (nav search, `theme.js:927`) | no — symbol/name lookup only | origin default-deny, but rewritten to public R2 by the shim ⇒ §0 F2 blast radius, not an `etfs` leak |
| `/premiumdata/etfs.json` (new) | **yes — by design** | must be `premium.enforced_early`; gate §B9.2 |

## B§6 T5 stance line — derived from non-graded data

The hero's verdict line is walled (B§2.2), so the free page needs its own Law-1 stance. Per the
W1b §8 T5 standing recipe it must come from non-graded inputs only. The rotation backdrop (M4,
free) is exactly that — trailing ratio momentum over public ETF prices, which the page's own
subtitle already calls descriptive.

Shipped free, verbatim (regime label and lead phrase templated from `pulse`):

- EN — `**{regime_phrase}** — {lead_clause}. Watch, don't chase.`
  → today: `**Risk-on tape** — credit and cyclicals lead. Watch, don't chase.`
- ZH — `**{regime_phrase_zh}** —— {lead_clause_zh}。观望，勿追。`
  → today: `**风险偏好行情** —— 信用与周期领先。观望，勿追。`

10 words EN, inside the Tier-1 one-line budget. `Watch — don't chase` is sanctioned stance
vocabulary (Doctrine Law 1) and is the *honest* stance for a rotation backdrop with no name-level
input: a supportive tape is a reason to look, not a reason to buy. It leaks no signal authority.

## B§7 zh 红涨绿跌

`--up`/`--down` flip under `html[data-lang="zh"]`. On the free half, colour encodes direction in:
the sector-leadership bars (11 rows), the risk-backdrop leg values, the style-rotation rails, and
the hero tile-3 accent. All must paint from `--up`/`--down` (or `.pos`/`.neg` resolving them) —
never a hard-coded green/red.

**The gate elements carry no directional colour** — `.gate-note`, `.gh` skeletons, `.tier-wall`
and `.gate-pill` are violet/neutral. Do not tint them by state.

**Non-directional statuses must NOT ride `--up`/`--down`** — see A§7. On this page that is the
**coverage freshness dots** (fresh / aging / stale). The first ZH render of the mockup painted
"fresh" red and "stale" green; the committed mockup pins fixed inks (`#1FA971` / `#f0b429` /
`#e06464`) and comments why. Apply the same to any pass/fail or health tint.

Verify against `etfs_preview_zh.png`.

## B§8 SEO head

Today `<title>` (`etfs.html.j2:51`) is `"Real fund moves — where managers are building conviction"`
— not brand-suffixed — while `seo_title` is `"Real Fund Moves — Mastermind"`. Unify them.

```jinja
<title>Which Stocks Fund Managers Are Buying — MastermindX</title>
{% set seo_title = "Which Stocks Fund Managers Are Buying — MastermindX" %}
{% set seo_desc  = "Track which stocks 77 thematic and active ETFs are accumulating — cross-fund consensus, brand-new positions and the sector rotation backdrop, updated each filing cycle." %}
{% set seo_path  = "etfs.html" %}
```

Measured: `<title>` **51 chars** (brand-suffixed, ≤ 70 ✅); `seo_desc` **168 chars** (inside
50–170 ✅).

The title change is deliberate: "Real fund moves" is a house phrase nobody searches. "Which stocks
fund managers are buying" is the question the page answers, in the words a searcher types, and it
keeps the h1's voice on the page itself (the h1 is unchanged — only `<title>`/`seo_title` move).
**Flagged as T-B4** — it trades brand voice for search intent in the SERP line only.

- **Canonical** — self-canonical via `seo_path` ✅.
- **No `noindex` meta** in the template — but `@reg_html` (`Caddyfile:259`) sets
  `X-Robots-Tag: noindex, noarchive`. Check response headers, not just markup.
- **Sitemap:** `grep -c "etfs.html" site/sitemap.xml` → **0** today, because `lib/seo.py::is_public_path()`
  gates on `config/site_access.yml`. It enters automatically once public — verify, don't assume.
- **JSON-LD:** none. Out of scope for W2.

## B§9 ACCEPTANCE GATES — "not done unless" (adapted from masterplan §0.1-7)

1. **Anonymous `curl https://www.mastermind-x.com/etfs.html` → 200**, self-canonical, no `noindex`
   **in the response headers**, with real above-the-fold content: hero, the T5 stance line, three
   honest tiles, the full rotation backdrop, the full coverage table — and the wall visible for
   M2/M5. Bilingual EN/ZH copy on the wall and the gate note.
2. **`/premiumdata/etfs.json` → 403 anonymous**, proven with
   `curl -H 'X-Original-Uri: /premiumdata/etfs.json' https://www.mastermind-x.com/api/paywall/check`
   (and 204 for the shell path). The server decides; no client tier check is load-bearing.
3. **Boundary edited in ALL THREE mirrors in one PR** — `app/regwall.py` + `app/deploy/Caddyfile`
   (every matcher list) + `config/site_access.yml`. Run `tests/test_site_access_boundary.py` and
   the `tier-gate` suite LOCALLY and paste the output.
4. **`etfs.html` added to `sitemap.xml`** in the same PR; verify the builder picks it up.
5. **Live verification post-merge:** anonymous curl 200 + the paywall-check probe + a Googlebot-UA
   fetch byte-comparable to a normal UA.
6. **Render-lane law:** never hand-bake locally. `build_etf_page` rides `scripts/build_site.py` →
   `render.yml` scope `macro`. **Note the cross-scope dependency:** M4's input
   `basketdata/etf_pulse.json` is written under scope `baskets` (`build_baskets.py:195` →
   `build_theme_addons`). A `scope=macro`-only render rebakes `etfs.html` off a possibly stale
   pulse file — dispatch both scopes, or verify the pulse `as_of`.
7. **NO edits to the tier catalog** (collision #4176/#4185). Existing classes only.
8. **Shipped-byte leak test.** A hermetic test proves `site/etfs.html` contains **zero** consensus
   `ticker` values, zero `conviction_pp` values, zero stance-pill strings from the withheld rows,
   and no `trims` row. **Key the check on the ROW, not the ticker** — one ticker legitimately
   appears on both the consensus board and a per-fund add row, and coverage-table fund tickers
   (XLK, QQQ, ARKK…) are free content that would false-positive a naive ticker scan. Compare
   rendered row identity. Pair with a coverage assertion (`len(keyed) == payload["locked"]`) and a
   hermetic control proving a duplicated row IS still caught.
9. **Page weight < 140 KB** for the anonymous shell (today 282 KB). Assert it in the test.
10. **Entitled parity.** A hydrated viewer sees the SAME page as today: 40 consensus rows, 8 fresh
    cards, 40 per-fund adds, 12 trims, the hero verdict line, tile 1, and the shelf collapsed as
    before. Screenshot the hydrated state next to the anonymous one.
11. **Empty-state guard test** (B§3.6): a gated build must not print either "Building — …" message
    over content that exists, and a genuinely empty board must still reach it.
12. **Visual artifact in the PR body:** anonymous EN + anonymous ZH + hydrated, all dark, cropped
    to the board skeletons and the wall. Compare against the reference PNGs.

---

## §7 Doctrine tensions — flagged, not silently decided

**T-A1 — opening the tile JSON is a real give.** A§2.4 makes `marketdata/*_heatmap.json` public.
That is 355 KB of structured A-share returns + market caps for China alone, trivially scrapable.
It is A4-free by policy (market context, daily close, delay disclosed) and the page cannot function
without it — but "the page displays it anyway" is a weaker argument for a machine-readable bulk
file than for rendered HTML. **Registering it rather than assuming it.**

**T-A2 — the free hover card loses two market facts.** `tech.price` and `tech.pct_vs_200dma` are
facts, not grades, but they ride inside the walled per-ticker file, so A§2.2 drops them from the
free card. The cleaner answer is a slimmed public per-ticker file (facts kept, `conviction` and the
other graded blocks removed) — which is *also* the natural fix for §0 F2. **If the orchestrator
takes the F2 fix in that direction, revisit this row.**

**T-A3 — every free tile links to a wall.** M12's "View full analysis →" points at
`app.mastermind-x.com/terminal?symbol=<T>`, a different host with its own auth. A public page whose
every tile links to a sign-in is the soft-404 crawl shape W1b anti-goal 7 warns about — though it
is mitigated here: the link is inside a hover card, not in the crawlable DOM, and it is
cross-origin so it does not dilute our own crawl budget. **Judged acceptable; naming it because the
reasoning is non-obvious.**

**T-A4 — the heatmap conversion is a content build, not a boundary flip.** §0 F1. This is a
materially larger scope than the brief's "convert to tier-preview" framing, and it is the whole
reason the page is worth converting. If the orchestrator wants a boundary-only PR first, **that PR
must not enter the page into `sitemap.xml`** — shipping an empty 200 to Google is worse than the
current 302.

**T-B1 — replacing the hero's graded tile changes what a tile means between builds.** B§2.2 swaps
"Strongest consensus / SPCX / Watch — don't chase" for "On the board / 40 / names at least two
funds are building". Both are true; only one is free. The alternative — a `.gh` skeleton in the
hero — opens the page on a grey box, which is the worst possible first impression for a conversion
surface. **Chose the honest total; flagging because it is the one place a module's identity, not
just its contents, differs between builds.**

**T-B2 — "Display-only" is banned Tier-1 vocabulary and it is engine-owned.** B§3.4. The string
lives in `engine/etf_pulse.py` and reaches other surfaces. Rewriting it is correct under Doctrine
Law 2 and urgent under anonymous-public (it would be indexed), but it is not this spec's file to
change unilaterally. **Confirm the blast radius before editing.**

**T-B3 — the free build opens a `<details>` the entitled build leaves collapsed.** B§2.3. A
deliberate, visible gated/ungated difference beyond the wall. Justified because Coverage is the
free tier's substance and a collapsed block may not be crawled — but it does bend "no structural
difference between builds". **A reviewer could reasonably ask for it open on both.**

**T-B4 — the `<title>` trades brand voice for search intent.** B§8 replaces "Real fund moves" with
"Which Stocks Fund Managers Are Buying" in `<title>`/`seo_title` only; the h1 is untouched. Correct
for a page whose entire purpose is now acquisition, but it is a voice decision on a surface the
operator has opinions about. **Flagging rather than assuming.**

**T-B5 — `etfs.html` is not the page the brief described.** The brief anticipated a cross-asset ETF
desk with a "flows/performance free, graded calls walled" split. It is a 13F fund-conviction desk,
so ~55% of its bytes are graded output and the free tier is context + totals + the coverage
directory rather than a data sample. The split is honest but **thinner than the brief implies**,
and if the orchestrator expected a flows/performance surface, that page does not exist here.

**T-B6 — no preview slice at all on either board.** B§2.1. Both boards are best-first and the
ratified pattern forbids previewing them; unlike `baskets_china` there is no category structure to
cut a neutral slice from. Free readers therefore see **zero** stock rows on this page. That is
consistent with the pattern and with W1b §8 T1, but it is the harshest free tier in the program so
far. **If the orchestrator wants rows, the only neutral cut available is alphabetical-by-ticker,
which would still hand over board membership — the thing being sold. Recommend against.**
