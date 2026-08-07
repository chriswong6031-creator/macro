# PSI — Market Books & Position Assessment: pinned design spec (by Fable, 2026-08-07)

Status: **DESIGN SPEC OF RECORD**, v1.1 (census-corrected) for the watchlist.html
rebuild (PSI Amendment A3 + operator round-4 directive). The builder implements THIS —
palette, structure, class names, copy, and states are decided here; deviations need a
main-loop ruling. Doctrine (`docs/DESIGN_DOCTRINE.md`) wins on any conflict. Everything
stays inside the page's existing WRI design language — a deepening, not a new identity.

**v1.1 census corrections (2026-08-07, supersede anything below that conflicts):**
1. Per-ticker stores exist for ALL markets: `stockdata/` (US+crypto+commodities),
   `chinastockdata/`, `hkstockdata/`, `canadastockdata/`, `intlstockdata/` — same rich
   schema (identical `tech` 37 keys, `mtf`, `ladder` incl. `ladder.state` signal enum +
   `ladder.alignment.overextended` bool, bilingual `entry_signal`), each with its own
   `index.json {t,n,s,st,a}`. Production rewrites all `*stockdata/` fetches to the
   public R2 CDN via `templates/data_base.js` — per-ticker reads work for ANON too.
   So cn/hk/ca/intl books are FULLY LIT: signal pill, entry headline, stretch, lanes
   (lanes degrade per-block to 'na' where a market's JSON lacks a source block — that
   fail-open behavior is already correct). The "at cost" degrade applies ONLY to names
   absent from every index.
2. Index field `a` = **alpha-z, not day change** (question answered — cite
   `build_stock_library.py`'s index emit in the PR anyway). There is NO day-change field
   in any store ⇒ Day column, movers chip, and plate day-% are OMITTED in this wave.
3. `SD` becomes store-aware (see §3.1) — mirror the proven suffix→store router
   `templates/mm_brain.js chartStore()` and the store registry
   `templates/theme.js STOCK_MARKETS`; search merges per-market indexes (§5.6).
4. **FX-corruption guard (binding)**: non-USD prices now resolve, so
   `pushFxWeights()` and EVERY WRI/risk_core book-math input filters to the modeled
   us+crypto subset (membership test: name is in `stockdata/`'s store per §3.1 — i.e.
   `storeOf(t)==='stockdata'` — and resolves in `factor_betas` as today). An
   HKD/CNY/CAD dollar value must never enter a USD weight sum. Add a node test.
5. Stage row stays US-only (ctx; the engine classifies US only). Non-US extension
   wording comes from `ladder.alignment.overextended` + `tech.pct_vs_200dma` (§7 v1.1
   wording); the precise 4-grade `ext` block stays US-only.
6. Verify `window.STATE_DISPLAY` covers every state the five indexes emit (incl. HK's
   `CONFIRMING TURN`); unknown states fall back to the ticker-page-safe rendering
   (verbatim label, neutral tint) — never a crash, never invented copy.

## 0. Acceptance gates (not done unless — inline per spawn-handoff law)

1. Fresh happy path on production-shaped data, zero manual workarounds: signed-in user
   adds US positions (e.g. NVDA/AAPL/MSFT with shares+entry) and one `.HK` + one `.TO`
   name → books strip appears with per-book native-currency subtotals; US book shows the
   full assessment table + WRI hero scoped "US & crypto"; HK book shows at-cost rows +
   ONE quiet coverage line; switching books filters cards AND table; signed-out visitor
   gets the local book (localStorage), can CRUD positions, sees the value-framed sign-in
   line; signing in folds local rows once (no dupes on re-login).
2. Visual crops committed in the PR body: light + dark + zh, desktop (1280) + mobile
   (390), for (a) books strip + hero, (b) assessment table with an open drawer, (c) HK
   book coverage state, (d) signed-out local mode. Crops to `mockups/refs/psi/books/`.
   No self-merge: PR + crops return to the commissioning session for review.
3. Tier-1 copy passes the doctrine: no internal vocab (no "WRI", "ENB", "ext_z", lane
   slugs), numbers arrive with meaning, one as-of + one footnote per panel, zh parity
   (no EN enums inside zh prose), no zh in `title=` attributes.
4. The cross-tab invariant holds: `mergeInto` stays idempotent (no re-persist on no-op
   merge — the #storage ping-pong regression test must still pass), and the new local
   portfolio store obeys the same rule.
5. All touched paired template/site plain-copy assets ship byte-identical in the same PR
   (`python -m scripts.check_template_site_sync --fix`), `?v=` bumps on every changed JS
   file referenced by the page.
6. Node-shelled tests green: marketOf derivation table (every suffix class), book
   aggregation (never sums across currencies), local-portfolio CRUD + one-shot fold
   idempotence, laneRead behavior unchanged on existing fixtures.
7. No new network dependencies: page works from baked JSON exactly as today; anon
   degrade never breaks render (401 fetches resolve null → honest lines).

## 1. What this build is

The watchlist page becomes the **Portfolio Command Center**: one page, partitioned into
per-market **books** (US · CN · HK · CA · Crypto · Intl · Macro), where every position
row carries the desk's read — signal state, stage of rise, extension, role ladder — and
opens into a full per-name drawer. Anonymous visitors get a real local book (funnel
primitive); signed-in users get sync (unchanged store).

## 2. Files

| File | Change |
|---|---|
| `templates/market_books.js` (**new**, + site copy) | pure module: `marketOf()`, book partition/aggregation, books-strip + today-strip render, active-book state (localStorage `mdash.book.v1`), event `bk-change` |
| `templates/watchlist.js` (v bump) | card grid filters by active book; snapshot/diff for "changed since last visit" (localStorage `mdash.wl.seen.v1` = {t: st}); no other behavior change |
| `templates/portfolio.js` (v bump) | table rebuild (columns, assessment cell, drawer), book filtering + subtotals, local-mode rendering, per-row lazy stockdata joins (existing pattern), ctx join for stage |
| `templates/watchstore.js` (v bump) | local portfolio store (`mdash.pf.v1`) behind the SAME `WatchStore.portfolio.*` API when signed out; one-shot fold on sign-in (`mdash.watchstore.pf_folded.v1` marker, the existing fold pattern); `wl-auth` behavior unchanged |
| `templates/watchlist_risk.js` (v bump) | hero scoping to active book (us+crypto members only), condition-counts line, drawer engine reused for table rows (export the laneRead/decorate seam), coverage note for cn/hk/ca books |
| `templates/watchlist.html.j2` | DOM order (portfolio above cards), books strip + today strip mounts, CSS additions (§5), script tags + `?v=` bumps |
| `tests/` | node-shelled tests per gate 6 (follow `tests/test_risk_core*` node-shell pattern) |
| `research/PSI_MARKET_BOOKS_DESIGN_SPEC.md` + masterplan §20 | committed in the same PR (copy from the commissioning worktree paths given in the task) |

## 3. Market derivation (the ONE function — mirror of terminal/lib/markets.ts)

```js
// market_books.js — pure; test table in tests. Vocabulary of record:
// us | cn | hk | ca | crypto | intl | macro   (macro = indexes/commodities/FX bucket)
function marketOf(sym) {
  var s = String(sym || '').toUpperCase();
  if (!s) return 'us';
  if (s === 'DX-Y.NYB') return 'macro';
  if (/^\^/.test(s) || /=F$/.test(s) || /=X$/.test(s)) return 'macro';
  if (/-USDT?$/.test(s)) return 'crypto';
  var m = s.match(/\.([A-Z]{1,3})$/);
  if (m) {
    var suf = m[1];
    if (suf === 'SS' || suf === 'SZ' || suf === 'BJ') return 'cn';
    if (suf === 'HK') return 'hk';
    if (suf === 'TO' || suf === 'V' || suf === 'NE') return 'ca';
    return 'intl';
  }
  return 'us';
}
```

### 3.1 Store routing (v1.1)

```js
// suffix → store dir (mirror mm_brain.js chartStore, *stockdata edition)
function storeOf(sym) {
  var m = marketOf(sym);
  return { us:'stockdata', crypto:'stockdata', macro:'stockdata',
           cn:'chinastockdata', hk:'hkstockdata', ca:'canadastockdata',
           intl:'intlstockdata' }[m];
}
```

`stockdata.js` extension (backward-compatible): `SD.loadTicker(t)` fetches
`storeOf(t)+'/'+safeTicker(t)+'.json'` (US callers see no change); `SD.loadIndex()`
keeps returning the US index; new `SD.loadIndexes(markets)` fetches+merges the named
markets' `index.json`s (memoized per market; each entry tagged with its market;
`byTicker` merged). Missing store index (404) → that market contributes nothing
(fail-open). `market_books.js` may define `marketOf/storeOf` and `stockdata.js` consume
via `window` seam — keep load order: market_books.js BEFORE stockdata.js consumers.

Book metadata table (module-level const):

| id | glyph | name en | name zh | currency prefix | modeled (WRI/factor) |
|---|---|---|---|---|---|
| us | US | US stocks | 美股 | $ | yes |
| cn | CN | China A-shares | A股 | ¥ | no |
| hk | HK | Hong Kong | 港股 | HK$ | no |
| ca | CA | Canada | 加股 | C$ | no |
| crypto | CR | Crypto | 加密 | $ | yes |
| intl | IN | International | 国际 | — (no ccy assumed; show plain numbers with a "local currency" tag) | no |
| macro | MX | Indexes & commodities | 指数与商品 | $ | partial (whatever factor model covers) |

Rules: the strip shows only books with ≥1 member (watchlist ∪ open positions), plus
**All** first. Strip hidden entirely when only one market present. Active book persists
per device (`mdash.book.v1`); default = All. `macro` and `intl` books appear in the strip
like any other when present.

## 4. Page structure (DOM order in watchlist.html.j2)

```
[_site_nav]
[title panel — subtitle updated, see §7 copy]
[#wri_rail]                       (unchanged markup; when >1 book present, watchlist_risk
                                   prepends the scope word — see §7 rail line)
[#bk_strip]  ← NEW books strip    (hidden single-market; see §5.1)
[#tod_strip] ← NEW today strip    (hidden when zero facts; see §5.2)
[#wri_hero]                       (unchanged shell; content scoped to active book)
[#wl_auth sync bar]               (unchanged)
[#pf_section PORTFOLIO]           (MOVED above the cards; rebuilt table §5.3)
[#wl_controls + #wl_list cards]   (filtered by active book)
[#wl_empty, modal, export/import, toast]  (unchanged)
```

## 5. Components (exact)

### 5.1 Books strip `#bk_strip` — the signature

A horizontal row of hairline "ledger plates" in the `.wri` idiom. One plate per book +
All. The active plate carries a quiet ring (the house featured-ring idiom, NOT a filled
container). A single 1px baseline runs under the strip (static; echoes the patch-bay
rail — same family, new meaning: books are partitions on one rail).

Markup (rendered by market_books.js into `#bk_strip`):

```html
<div class="bk-strip wri" role="tablist" aria-label="Books">
  <button class="bk-plate" role="tab" aria-selected="true" data-bk="all">
    <span class="bk-glyph">ALL</span>
    <span class="bk-line1">All books</span>
    <span class="bk-line2 num">7 names</span>
  </button>
  <button class="bk-plate" role="tab" aria-selected="false" data-bk="us">
    <span class="bk-glyph">US</span>
    <span class="bk-line1 num">$12,480</span>
    <span class="bk-line2"><span class="bk-day num up">+1.2%</span> · 5</span>
  </button>
  <!-- … one per present book … -->
</div>
```

CSS (add to the page `<style>`, `.wri` token scope):

```css
.bk-strip { display:flex; gap:8px; overflow-x:auto; padding:2px 2px 10px; margin:0 0 14px;
  position:relative; scrollbar-width:none; }
.bk-strip::-webkit-scrollbar { display:none; }
.bk-strip::after { content:""; position:absolute; left:2px; right:2px; bottom:4px;
  height:1px; background:color-mix(in srgb, var(--line) 85%, var(--muted)); }
.bk-plate { flex:0 0 auto; min-width:118px; text-align:left; cursor:pointer;
  background:color-mix(in srgb, var(--panel) 88%, transparent);
  border:1px solid color-mix(in srgb, var(--line) 80%, transparent); border-radius:10px;
  padding:9px 12px 8px; color:var(--text); font:inherit; display:flex;
  flex-direction:column; gap:2px; }
.bk-plate:hover { border-color:color-mix(in srgb, var(--link) 45%, var(--line)); }
.bk-plate[aria-selected="true"] { border-color:color-mix(in srgb, var(--link) 55%, var(--line));
  box-shadow:0 0 0 1px color-mix(in srgb, var(--link) 45%, transparent),
             0 0 14px color-mix(in srgb, var(--link) 18%, transparent); }
.bk-plate:focus-visible { outline:2px solid var(--link); outline-offset:2px; }
.bk-glyph { font-family:var(--wri-mono); font-size:9.5px; font-weight:700;
  letter-spacing:.16em; color:var(--muted); }
.bk-line1 { font-size:13.5px; font-weight:700; letter-spacing:-.01em; }
.bk-line2 { font-size:11px; color:var(--muted); }
.bk-day.up { color:var(--up); } .bk-day.down { color:var(--down); }
@media (max-width:560px){ .bk-plate { min-width:104px; padding:8px 10px 7px; } }
```

Plate content rules: line1 = native-ccy total of OPEN positions in that book when ≥1
position has a resolvable price; if some/all values are entry-price-only, show the total
with a trailing `.bk-atcost` tag "at cost"/"按成本" (11px muted); if the book has
watchlist names but zero positions, line1 = the book name and line2 = "N names". Day %
renders ONLY when a verified day-change field exists for every priced member (see §6
day-change verification); otherwise omit the day span (no fabrication). All plate never
shows a summed value (currencies differ) — it shows "All books" + total name count.
Directional tint via `--up/--down` ONLY (zh flip law).

Behavior: click → set active book, `aria-selected` swap, persist, dispatch
`document` CustomEvent `bk-change` {book}. watchlist.js and portfolio.js listen and
re-render their sections filtered. NO page scroll on switch.

### 5.2 Today strip `#tod_strip`

One quiet line of fact chips — the daily-return hook. Chips (each only when its fact is
non-zero, strip hidden when all zero):

- `N reporting this week` / `本周N家发布财报` — from already-fetched per-ticker
  `earnings.next_date` (≤7 days ahead) across watchlist ∪ positions.
- `N signals changed since your last visit` / `自上次访问N个信号变化` — diff of
  `{t: st}` vs `mdash.wl.seen.v1` snapshot (write the new snapshot AFTER computing the
  diff, on each load).
- (only if §6 verifies a day-change field) `N moved >2% today` / `N只今日波动超2%`.

Markup/CSS: reuse `.wri-rail` visual grammar but its own class `.tod-strip` (same
hairline pill row, dot in `--info`); each chip is a `<button>` that scrolls to and
briefly highlights the relevant section (`.bk-flash` 1.2s outline pulse, gated by
`prefers-reduced-motion`). ≤1 line; no wrap spam (`overflow-x:auto` like the strip).

### 5.3 The assessment table (`#pf_section` rebuild)

Desktop ≥880px — columns:

| # | Header en/zh | Content |
|---|---|---|
| 1 | Position / 持仓 | bold ticker (link `stock.html#T`) + muted name beneath (11px, ellipsis) |
| 2 | Value / 市值 | native-ccy value (`shares×price`, else `shares×entry` + "at cost" tag); under it a `.wri-rsbar` weight bar = share of BOOK value (only when book has ≥2 priced positions) |
| 3 | Day / 当日 | verified day-change % (±, `--up/--down`), else "—" |
| 4 | Since entry / 入场以来 | existing calc (±%, `--up/--down`) |
| 5 | Assessment / 系统评估 | see below |
| 6 | (chevron) | `.pfx-tgl` expands the drawer row |

Assessment cell (Tier-1, hard budget — AT MOST: 1 pill + 2 chips + 1 badge):

1. Signal state pill — existing `.state st-*` from index `st` (house vocabulary, already
   bilingual via STATE_DISPLAY).
2. Stage chip (only when ctx stage present): `.wri-chip info` — "Stage 2 · rising" /
   "第2阶段 · 上行" (mapping table §7).
3. Stretch chip (only when `ext.grade` ∈ {stretched, parabolic}): `.wri-chip` (hot when
   parabolic) — "Stretched"/"过度拉伸", "Parabolic"/"抛物线拉伸".
4. Role badge (only ≥ review): existing `.wri-role*` (Review / Take-profit review /
   Exit review — review language, exact existing labels).

Row click (anywhere non-link) toggles the drawer. Edit moves INTO the drawer footer
(button `.wl-btn` "Edit position"/"编辑持仓") — the column-9 Edit button is removed.

Drawer row (a `<tr class="pfx-drawer"><td colspan=6>` using the existing `.wri-drawer`
inner idiom — `.wri-lrow` rows):

1. **Lead line**: `entry_signal.headline` / `headline_zh` VERBATIM (it is already the
   plain-word read, e.g. "Extended — wait for a pullback"). When absent → the honest
   line "No entry read tonight" / "今晚无入场读数".
2. `Stage` — "Rising — stage 2 of 4 · 8 wks in" (ctx `stage {n,label,weeks}`; mapping
   §7; absent → row omitted).
3. `Extension` — from `ext`: grade word + one number with meaning: "about 12% above its
   200-day line" (use `tech.pct_vs_200dma`; builder MUST verify the exact semantic of
   `ext.ext` against `engine/extension.py` before labeling it — if it is not %-vs-200dma,
   use `tech.pct_vs_200dma` for the sentence and keep `ext.grade` for the word).
4. `Trend` / `Momentum` / `Events` / `Estimates` / `Balance sheet` / `Who's selling` /
   `Rate sensitivity` — the EXISTING seven `laneRead` rows (reuse watchlist_risk.js's
   engine — export it on a shared namespace rather than duplicating).
5. `Chains` — existing TXI info row when present.
6. Footer: as-of stamp (per-name `asof`) + links: "Full dossier →" (`stock.html#T`) ·
   "Chart in Terminal →" (the Terminal symbol URL — builder verifies the exact route
   from charting-app origin/master, read-only, e.g. `git -C /Users/chriswong/Documents/Cluade/charting-app
   show origin/master:terminal/...`; if no clean symbol deep-link exists, ship the
   dossier link only — never guess a URL) · "Edit position".

Uncovered names (no stockdata file — every cn/hk/ca name today): NO lane rows, ONE line
"Signals for this market aren't wired into this desk yet" / "该市场的信号尚未接入" +
links row. Books-level note already covers the class (§5.4); the drawer line is the
per-name receipt.

Mobile <880px: CSS-only re-layout (same DOM): each `<tr>` becomes a stacked card
(`display:block` rows, `td` grid 2-col: label/value via `data-th` attributes), assessment
cell wraps, drawer full-width. Table min-width rule (`.ts table{min-width:560px}`) is
REPLACED by the stacked layout (no horizontal page scroll on 390px — hard gate).

Subtotal header (one line above the table, per active book — or per book-group in All
view): "US book · $12,480 · 5 positions" + day% when §6-verified. In **All** view the
table renders grouped: a `.pfx-bookhead` subtotal row per market (same line1 content as
the plate), rows beneath; group order: us, crypto, cn, hk, ca, intl, macro.

### 5.4 Hero scoping + condition counts (`watchlist_risk.js`)

- Active book ∈ {all, us, crypto}: hero runs exactly as today on the us+crypto modeled
  union (all=today's behavior). Its eyebrow gains the scope words when >1 book present:
  "BOOK STRUCTURE — US & CRYPTO" / "组合结构——美股与加密".
- Active book ∈ {cn, hk, ca, intl}: hero collapses to ONE `.panel` line (keep the
  `#wri_hero` mount, render the compact form): "Book-structure risk modeling covers US &
  crypto names for now — {HK} names shown with entry math only." / zh per §7. No
  patch-bay, no fabricated verdict (gate 6 / WRI-R6).
- Condition-counts line (NEW, inside the hero verdict block, all/us/crypto books): after
  the existing "so-what" sentence: "N of M names in review or worse · K lanes elevated."
  / "M只中N只处于复查或更高级别 · K条风险线升高。" Computed from the same laneRead
  results the cards already produce (no new fetches; counts update as cards hydrate).
  When every name is clean: "Nothing elevated across your names tonight." / "今晚你的
  名称无升高风险项。" (Law 1: the honest nothing.)

### 5.5 Anonymous local book (watchstore.js + portfolio.js)

- Signed out: `WatchStore.portfolio.list/upsert/remove` operate on localStorage
  `mdash.pf.v1` `{v:1, rows:[{id:'loc-'+epoch, ticker, shares, entry_price, entry_date,
  notes, status}]}`. portfolio.js renders EXACTLY the same UI (table, books, drawers).
  v1.1: per-ticker signals DO resolve for anon in production (the data_base.js R2
  rewrite is public) — only the ctx-fed stage rows are account-gated; when the ctx
  fetch 401s, stage rows omit silently. If `SD.loadTicker` still resolves null (local
  preview, outage), rows degrade to at-cost with the honest drawer line — degrade must
  never break render.
- The old full-block `#pf_signedout` gate is REMOVED. In its place, under the table, one
  quiet line + inline `.wl-btn` "Sign in" when signed out with ≥1 local row: "Sign in to
  keep this book tracked across devices — free." / "登录即可跨设备保存并追踪——免费。"
  Zero rows signed-out → the existing empty state with its Add button (works locally).
- On sign-in: one-shot fold — local rows insert to Supabase unless an existing row
  matches (ticker + entry_date + shares); marker `mdash.watchstore.pf_folded.v1`; on
  fold error do NOT mark (retry next session — the watchlist fold's exact pattern). After
  fold, local rows are cleared and the store reads from Supabase.
- Privacy: rows never leave localStorage except into the user's own Supabase rows
  (PRD-R7/UWP-R1); nothing position-derived in logs.

### 5.6 Cards grid filtering + multi-market search (watchlist.js)

`bk-change` → re-render the grid showing only `marketOf(t) === book` (All = all). The
buy-soon counter/pill counts the FILTERED set. Empty filtered state: one line "No {US}
names on your list yet — search above to add one." / "清单中还没有{美股}名称——在上方
搜索添加。" The seen-snapshot diff (§5.2) runs on the FULL set regardless of filter.

Search (v1.1): the `#wl_q` suggest and the position-modal suggest search a MERGED index
set: on first focus load US + every market present in the user's names; when a query
contains a `.` suffix or produces zero matches, lazily load the remaining markets'
indexes and retry once (indexes are small: ~15–155 KB). Suggest rows show a quiet
market glyph (`.bk-glyph` mini) for non-US rows. Adding a suggested name stores the
suffixed symbol verbatim. Prior art to follow (not copy blindly): the global nav
search merge in `templates/theme.js` (`STOCK_MARKETS`) — the watchlist keeps its OWN
suggest UI, only the index-merge idea is borrowed. The modal's "not in our coverage"
hint now fires only when the ticker misses EVERY loaded index.

## 6. Data joins & verification duties (builder MUST verify, never assume)

| Fact | Where to verify |
|---|---|
| `index.json` field `a` — census says **alpha-z (not day change)** ⇒ Day column/movers/plate-day% OMITTED this wave | confirm + cite the index emit in `scripts/build_stock_library.py` (~line 3772) in the PR body |
| `STATE_DISPLAY` covers all five indexes' `st` values (incl. `CONFIRMING TURN`) | `engine/cycles.py STATE_DISPLAY` vs each store's index; unknown → verbatim-label neutral fallback |
| `ext.ext` semantic | `engine/extension.py` docstrings/computation |
| ctx `stage` block shape `{n,label,weeks}` | `scripts/build_portfolio_ctx.py` `_stage_block` (already read: keys n/label/weeks) |
| Terminal symbol deep-link route | charting-app origin/master, read-only `git show` — never guess |
| stockdata per-ticker fetch path + safeTicker | existing `stockdata.js` (unchanged) |
| ctx fetch | `data/portfolio_ctx.json` same-origin; fetch lazily AFTER first paint (idle callback) and only when ≥1 US/crypto position exists; 401/absent → stage rows omit (anon degrade) |

Fetch budget: NO new per-row endpoints. Reuse per-ticker stockdata fetches portfolio.js
already performs; ONE optional ctx fetch; ONE index fetch (already loaded).

## 7. Copy tables (exact strings — dual-span `t()` in .j2, `T{en,zh}` in JS)

- Title subtitle (replaces current): en "Your book, by market — every position with the
  desk's read." zh "你的组合，按市场分列——每笔持仓都附系统解读。"
- Rail scope prefix (when >1 book present, prepended by watchlist_risk to the existing
  rail text): en "US tape · " zh "美股行情 · "
- Book-risk note (v1.1 — replaces the old "coverage note"; shown as the hero's compact
  form on cn/hk/ca/intl books, §5.4): en "Book-structure risk modeling covers US &
  crypto names for now — your {Hong Kong} names still carry tonight's signals below."
  zh "组合结构风险建模目前覆盖美股与加密——你的{港股}名称在下方仍有今晚信号。"
- Truly-uncovered name drawer line (name absent from every index): en "This name isn't
  in tonight's library — value shown at cost." zh "该名称不在今晚的库中——数值按成本
  显示。"
- Non-US extension wording (v1.1, from `ladder.alignment.overextended` +
  `tech.pct_vs_200dma`): overextended=true → the "stretched" sentence from the table
  below; else the "intrend" sentence. The 4-grade table applies to US names only.
- Stage mapping (ctx `stage.n`/`label` → chip + drawer words; fall back to verbatim
  `label` when n is outside 1–4):
  | n | chip en | chip zh | drawer en | drawer zh |
  |---|---|---|---|---|
  | 1 | Stage 1 · basing | 第1阶段 · 筑底 | Basing — stage 1 of 4 | 筑底——第1阶段（共4段） |
  | 2 | Stage 2 · rising | 第2阶段 · 上行 | Rising — stage 2 of 4 | 上行——第2阶段（共4段） |
  | 3 | Stage 3 · topping | 第3阶段 · 筑顶 | Topping — stage 3 of 4 | 筑顶——第3阶段（共4段） |
  | 4 | Stage 4 · declining | 第4阶段 · 下行 | Declining — stage 4 of 4 | 下行——第4阶段（共4段） |
  `weeks` suffix: "· 8 wks in" / "· 已8周".
- Extension drawer words (grade → sentence; the number from `tech.pct_vs_200dma`):
  intrend → "In trend — about {p}% above its 200-day line, not stretched." / "趋势内——
  高于200日线约{p}%，未过度拉伸。" ; steady → "Steady — about {p}% above its 200-day
  line." / "平稳——高于200日线约{p}%。" ; stretched → "Stretched — ran hard, about {p}%
  above its 200-day line. Entries here have chased before." / "过度拉伸——涨势过快，高于
  200日线约{p}%。此位追入历史上多为追高。" ; parabolic → "Parabolic — extreme extension,
  about {p}% above its 200-day line. Protect gains." / "抛物线拉伸——极端偏离，高于200日
  线约{p}%。注意保护利润。"
- Negative `pct_vs_200dma` variant: "about {|p|}% below its 200-day line" / "低于200日
  线约{|p|}%" (grade word still leads).
- All other copy: §5 inline strings above are exact.

Tier-2 receipts: the pf-help `?` tip gains one sentence: en "+ Books split your names by
market; each book's totals stay in its own currency." zh "+ 「账本」按市场拆分你的名称；
每个账本的合计使用其本币。"

## 8. What does NOT change

Search, add/remove flows, MTF strip, mx5 modal, export/import, factor panel internals,
risk_core math, WRI patch-bay rendering, sync pill, theme/i18n plumbing, nav. The page's
existing localStorage keys keep their shapes (`mdash.watchlist.v1` untouched).

## 9. Perf & quality floor

First paint unchanged (static shell); books strip renders from localStorage + index
synchronously after index load; per-ticker fetches stay lazy; ctx deferred to idle; all
new animation behind `prefers-reduced-motion`; keyboard: plates are buttons with
focus-visible, drawers toggle on Enter; light theme judged as a design (doctrine §5.8) —
plates/pills/bars carry explicit light-mode legibility (tokens + color-mix only, no raw
hex beyond the existing `.wri` locals).
