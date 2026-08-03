# W1b — `baskets_china.html` anonymous tier-preview: design spec

*Design-spec-first deliverable for SEO Supercharge W1 (`research/SEO_SUPERCHARGE_MASTERPLAN_BY_FABLE.md`,
adjudications A1 + A4 + A5). Pinned 2026-08-02 by `designer` (opus). The builder implements
this without design judgment: palette, type, layout, copy and the free/walled line are all
decided here.*

**Why this page:** 63 GSC impressions — the highest-demand page we own, and currently
302 → `/?signin=1` + noindex to Googlebot (Google's soft-404 shape). It is the W1
pattern-setter; `hk.html`, `etfs.html` and `china_heatmap.html` follow it.

**Binding inputs:** `docs/DESIGN_DOCTRINE.md` (house law — wins on conflict),
`docs/TIER_PREVIEW_PATTERN.md` (the ratified mechanism), the shipped reference
`templates/special_situations.html.j2`.

**Reference images (LOOK AT THESE FIRST):**

| File | What it shows |
|---|---|
| `mockups/refs/seo_supercharge/baskets_china_preview.html` | the walled state, interactive, EN/中文 toggle |
| `mockups/refs/seo_supercharge/baskets_china_preview.png` | anonymous state, dark, EN |
| `mockups/refs/seo_supercharge/baskets_china_preview_zh.png` | anonymous state, dark, ZH (note the 红涨绿跌 flip) |

---

## §0 ACCEPTANCE GATES — "not done unless"

Adapted from masterplan §0 gates 1–7. The build PR is not done unless:

1. **Anonymous `curl https://www.mastermind-x.com/baskets_china.html` → 200**, self-canonical,
   no `noindex` (header or meta), with real above-the-fold content: the header, the free
   market-context strip, the 14-basket performance table and the chart — and the wall
   visible for the premium modules. Controls INERT, not hidden (`.gated`,
   `pointer-events:none`). Bilingual EN/ZH copy on the wall and on both gate notes.
2. **`/premiumdata/baskets_china.json` → 403 anonymous**, proven with
   `curl -H 'X-Original-Uri: /premiumdata/baskets_china.json' https://www.mastermind-x.com/api/paywall/check`
   (and 204 for the shell path). The server decides; no client tier check is load-bearing.
   **Also 403:** `/chinabasketdata/narrative_emergence.json` (see §2 note N1 — gating the
   page while that file stays readable is theatre).
3. **Boundary edited in ALL THREE mirrors in one PR** — `app/regwall.py` +
   `app/deploy/Caddyfile` (every matcher list) + `config/site_access.yml`. Run
   `tests/test_site_access_boundary.py` and the `tier-gate` suite LOCALLY and paste the
   output in the PR (ci.yml may not run them on this PR's paths).
4. **`baskets_china.html` added to `sitemap.xml`** in the same PR (verify the builder picks
   it up). The 22 per-theme detail pages `basket_china/*.html` are NOT added — they stay
   Insider+ (see §6 anti-goal 7).
5. **Live verification post-merge:** anonymous curl 200 + the paywall-check probe + a
   Googlebot-UA fetch byte-comparable to a normal UA.
6. **Render-lane law:** never hand-bake locally. Dispatch the scoped render and let
   `render.yml` bake it.
7. **NO edits to the tier catalog** (collision: PRs #4176/#4185 in flight). Use existing
   classes only: shell → `free_registered` list *and* the anonymous-public mirrors;
   payload → `premium.enforced_early`.

Plus, specific to this page:

8. **Shipped-byte leak test.** A hermetic test proves `site/baskets_china.html` contains
   **zero** member `symbol` values, zero `score`/`reco`/`turn_state`/`clean_entry_q` values,
   and no `theme_intel.themes` entry. Key the check on the ROW identity (basket `id` +
   member `symbol`), not on a bare selector substring — the page's own JS mentions every
   class name, so `"gh" in html` is vacuously true. Pair it with a coverage assertion
   (`len(keyed) == payload["locked"]`) and a hermetic control that proves a duplicated row
   IS still caught.
9. **Page weight.** The anonymous shell must be **< 250 KB** (today: 850 KB). This is a
   Core Web Vitals gate, not a nicety — see §2's weight table. Assert it in the test.
10. **Entitled parity.** A hydrated (entitled) viewer ends up with the SAME page as today:
    22 baskets, the Score column, all 285 holdings, the full desk, full chart history.
    Screenshot the hydrated state and paste it in the PR next to the anonymous one.
11. **Visual artifact in the PR body:** anonymous EN + anonymous ZH + hydrated, all dark,
    cropped to the table and the wall. Compare against the reference PNGs above.

---

## §1 Module inventory

Every visible module on `templates/baskets_china.html.j2` (non-`lite` build). Data reaches
the page through **three** inlined blobs and **one** client fetch:

| Source | Where | Size today |
|---|---|---|
| `const BASKETS = {{ baskets_json }}` | `baskets_china.html.j2:474` | 519 KB |
| `const CHART = {{ chart_json }}` | `baskets_china.html.j2:475` | 236 KB |
| `THEME = BASKETS.theme_intel` | `:476` (a view onto the same blob) | (236 KB of the 519) |
| `fetch('chinabasketdata/narrative_emergence.json')` | `forming_narratives.js` | separate file |

| # | Module | DOM id / container | Rendered by | Shows names? | Graded/ranked? |
|---|---|---|---|---|---|
| M1 | Theme-context hero *or* plain header (h1, as-of, tagline) | `header` / `.tc-inner` | Jinja | no | hero carries a trailing-momentum read |
| M2 | Sleeve chip — drawdown radar state + driver | `#sleeve-chip` | `baskets_desk.js` | no | severity tint only |
| M3 | Macro backdrop strip — quad / cycle / PBoC / NFCI / USD / bonds | `#macro-ctx` | `baskets_desk.js` | no | no |
| M4 | **What to act on now** — 4 columns (buy now / wait for a pullback / reduce-avoid / conflicted) | `#actnow-section` | `baskets_desk.js` | basket names | yes — verb chip + 0–100 score + tape state |
| M5 | **Theme Rotation Desk** — one card per theme | `#theme-desk-section`, `#theme-desk` | `baskets_desk.js` | basket names + a `leaders` ticker line | yes — rank #, 0–100 score, trend label, reco verb, heat pill, tape state |
| M6 | Market concentration — breadth summary card | `#concentration-section` (summary half) | `baskets_desk.js` | no | no — A/D, %>50d, %>200d, new hi/lo |
| M7 | Market concentration — 4 named lists (owns the advance / in the decline / clean entries / roll-over watch) | `#concentration` (lists half) | `baskets_desk.js` | basket names | yes — clean-entry quality % |
| M8 | 5-Day Theme Rotation — weekly climbers & fallers | `#rotation-section`, `#rotation` | `baskets_desk.js` | basket names | yes — ranked by 5d rank delta |
| M9 | Impulse & Extremes — ±3% impulse card, 52-week extremes card | `#impulse-section` (2 of 3 cards) | `baskets_desk.js` | counts on the face; **member names in the modal** | no (counts are market facts) |
| M10 | Impulse & Extremes — recommendation tally card | `#impulse-section` (3rd card) | `baskets_desk.js` | theme names in the modal | yes — a tally of OUR reco verbs |
| M11 | **Entry Radar** — washout→confirmed lifecycle board | `#entry-radar` | `baskets_china.html.j2:897` | basket names | yes — this IS the lifecycle ranking surface |
| M12 | **Forming Narratives** — emerging themes + per-ticker entry grades | `#forming-narratives` | `forming_narratives.js` | **per-stock names with an entry grade** | yes — 0–100 score + intrend/stretched/parabolic grade |
| M13 | Finder — search box + result count | `.finder`, `#basket-search` | Jinja + JS | — | — |
| M14 | **§01 Performance table** — sortable, 22 rows, `TABLE_LIMIT=12` | `#table-section`, `#btable` | `renderBTable()` | basket names | **Score column** is graded; 1d/5d/20d/60d/MTD/YTD are market data |
| M15 | §01 mode tabs — Return / vs CSI 300 / σ | `#btbl-mode` | JS | — | σ (z-score) is a derived signal view |
| M16 | §01 category filter chips | `#tbl-cat-filter` | JS | — | — |
| M17 | **§02 Performance chart** — rebased lines, 22 series × 1245 sessions | `#chart-section`, `#chart` | JS + `CHART` | basket names in the legend | no — price history |
| M18 | §02 controls — scope (Baskets/Categories), mode, range, category bar | `#chart-scope` `#chart-modes` `#chart-ranges` `#chart-cats` | JS | — | — |
| M19 | **§03 Baskets by category** — cards, default sort = `score` desc | `#categories`, `#cards` | `sortedCards()` | basket names | yes — default sort IS our score |
| M20 | **Per-basket detail + member table** — 285 holdings, cols Symbol/Rationale/Added/5d/20d/YTD | `#details`, `.detail` | `detailSection()` | **every constituent ticker + name + rationale** | yes — score badge, reco chip, turn chip, `sig_tier` per member |
| M21 | Basket overlap chips | `.overlap-row` | JS | basket names | no |
| M22 | Reversal Sleeve strategy card | `#reversal-sleeve-card` | Jinja | no | yes — carries the `VALIDATED EDGE` tag (see §7 T3) |
| M23 | Construction / history / disclaimer notes | `.tagline`, footer notes | Jinja | no | no |

---

## §2 FREE vs WALLED adjudication (policy A4)

**The line, in one sentence:** *how the market has traded is free; what we think about it is
paid.* Price history, breadth and macro state are market context (A4 → free). Scores, ranks,
stances, lifecycle stages, entry grades and the constituent lists are signal authority
(A4 → walled). This is the same cut the China Special Situations desk already ships —
"state and totals are free, names are paid" (`docs/TIER_PREVIEW_PATTERN.md`).

### The table

| # | Module | Verdict | Exactly what ships free |
|---|---|---|---|
| M1 | Header / hero | **FREE** | h1, as-of, tagline. On the gated build use the **plain header**, not the theme-context hero — the hero carries a trailing-momentum read (signal authority). |
| M2 | Sleeve chip | **FREE** | state word + driver + the "not a return forecast" caption. No names, no score. |
| M3 | Macro backdrop | **FREE** | whole strip. Pure macro state. |
| M4 | What to act on now | **WALLED** | nothing. Heading + sub-tag stay as text; body = `.gh` skeletons. |
| M5 | Theme Rotation Desk | **WALLED** | nothing. Heading + sub-tag + `.gate-pill` stay; body = 3 `.tcard-ghost`. |
| M6 | Breadth summary | **FREE** | A/D ratio, % above 50d, % above 200d, new highs / new lows. Real numbers. |
| M7 | The 4 named lists | **WALLED** | list headings stay as text; bodies = `.listghost` skeletons. |
| M8 | 5-Day Rotation | **WALLED** | nothing — a ranked best/worst board. Section omitted entirely on the gated build (no skeleton: it would be a third stack of grey bars in a row). |
| M9 | ±3% impulse + 52-wk extremes | **FREE at count level** | the counts on both card faces. **Modals disabled** (`.gated`) — the name lists are paid. |
| M10 | Recommendation tally | **WALLED** | omitted. It is a summary of our own graded output. |
| M11 | Entry Radar | **WALLED** | omitted entirely (heading included). It is the lifecycle ranking surface; a heading with nothing under it teaches nothing. |
| M12 | Forming Narratives | **WALLED** | omitted. Per-ticker entry grades — the most valuable thing on the page. **See note N1.** |
| M13 | Finder | **BAKED INERT** | see §4. |
| M14 | §01 Performance table | **FREE, 14 of 22 rows** | see "the 14" below. Columns 1d / 5d / 20d / 60d / MTD / YTD + the benchmark row. **The `Score` column is NOT rendered on the gated build** (not a lock icon per row — Law 4 bans per-row repetition of a constant). The 60d sparkline column is dropped with it (it is drawn from the withheld level series' tail). |
| M15 | Mode tabs | **FREE for Return + vs CSI 300; σ WALLED** | bake two tabs. Hydration adds the third. |
| M16 | Category filter | **BAKED INERT** | see §4. |
| M17 | §02 chart | **FREE, 14 series × last 252 sessions** | rebased lines for the same 14 baskets + the CSI 300 benchmark. |
| M18 | §02 controls | **partly inert** | scope: "Baskets" only ("Categories" averages need all 22 — a category mean computed from 2 of 4 members is a WRONG NUMBER, never ship it). Ranges 60d / 120d / 1Y; "All" walled. |
| M19 | §03 category cards | **WALLED** | heading + sub-tag + `.gate-pill` stay; body = the `.tier-wall`. |
| M20 | Member tables | **WALLED** | nothing. All 285 holdings are paid, for all 22 baskets — including the 14 whose returns are free. |
| M21 | Overlap chips | **WALLED** | rides with M20. |
| M22 | Reversal Sleeve card | **WALLED** | omitted (see §7 T3). |
| M23 | Construction / disclaimer notes | **FREE** | always. Honesty is never behind a wall. |

### "The 14" — the preview slice rule

> **The first two baskets in each category, ordered by category, alphabetical by
> English name within a category. 7 categories × 2 = 14 free, 8 walled.**

Deterministic, testable, and — the load-bearing part — **neutral**. It is NOT best-first.
`docs/TIER_PREVIEW_PATTERN.md` is explicit: *"the ranked 'top N by magnitude' boards get no
preview at all, because previewing a best-first board hands over its head, which is the part
people pay for."* The page's own default sorts are best-first (`btblSort` defaults to
`20d` desc; `cardSort` defaults to `score` desc), so **do not use them for the slice** —
see §7 T1, where this diverges from the commissioning brief.

Two-per-category also buys what a flat top-N cannot: every one of the 7 categories is
represented, so the crawlable page shows the desk's full scope, and no category renders as
an empty shell.

The resulting slice, from the 2026-07-31 build:

| Category | Free | Walled |
|---|---|---|
| Advanced Manufacturing | Defense & Aerospace · Robotics & Automation | — |
| Consumer & Brands | Baijiu / Liquor · Food & Beverage | Home Appliances |
| Cyclicals & Resources | Coal · Gold Miners | Industrial Metals · Rare Earth & Magnets |
| Financials & Value | Banks · Brokers & Securities | Insurers · SOE Blue Chips (中特估) |
| Healthcare | Innovative Pharma & CXO · Medical Devices & TCM | — |
| New Energy & Autos | Autos & NEV Makers · Battery & Lithium | Solar / Photovoltaics |
| Technology & AI | AI Compute & Optics · Consumer Electronics | Semiconductors · Software & AI Apps |

Counts are computed, never hardcoded — categories and membership change nightly.
Advanced Manufacturing and Healthcare hold exactly 2 baskets today, so they are fully free
at the returns level; their holdings, scores and stances are still paid, so nothing leaks.

### Field-level split of the inlined payload

The free build strips fields, not just rows. Per basket object in the shell:

| Keep (free) | Drop (paid) |
|---|---|
| `id` `name` `name_zh` `category` `category_zh` `thesis` `thesis_zh` `weighting` `created` `n_members` `perf` `reference` `partial` `missing` | `members` `cycle` `changelog` `score` `label` `label_zh` `reco` `reco_zh` `clean_entry_q` `turn_state` `turn_dd_252` `turn_hist_d` `turn_slope_20d` `turn_evidence` `top_overlaps` |

`theme_intel`: keep `as_of`, `bench_label(_zh)`, `disclaimer`, `macro_context`,
`market_concentration` (summary keys only), `impulse_scorecard` (counts only — drop
`up_names` / `down_names` / `nh_names` / `nl_names`), `n_themes`. Drop `themes`,
`act_now`, `entries`, `rollover`, `rotation_5d`, `breadth_leaders`, `breadth_laggards`,
`recommendations`, `weights`, `signal_calibration`, `regime_sizing`.

`chart`: keep `dates[-252:]`, `bench[-252:]`, and `baskets[id][-252:]` for the 14 only.

**Weight budget** (measured on the 2026-07-31 build — this is the SEO prize):

| Blob | Today | Free shell | Saved |
|---|---|---|---|
| `baskets[].cycle` | 228 KB | 0 | −228 KB |
| `baskets[].members` | 78 KB | 0 | −78 KB |
| `theme_intel.themes` | 146 KB | 0 | −146 KB |
| `theme_intel.rotation_5d` | 66 KB | 0 | −66 KB |
| `theme_intel.impulse_scorecard` | 10 KB | ~1 KB | −9 KB |
| `chart` | 236 KB | ~27 KB | −209 KB |
| everything else | ~86 KB | ~12 KB | — |
| **page total** | **850 KB** | **~140 KB** | **−710 KB** |

Gate at **< 250 KB** (§0.9) to leave the builder headroom.

### Note N1 — the second door

`forming_narratives.js` fetches `chinabasketdata/narrative_emergence.json` **directly from
the browser**. Withholding M12 from the page while that URL stays open is theatre — it is
the same per-ticker entry grades in machine form. Add
`/chinabasketdata/narrative_emergence.json` to `premium.enforced_early.exact` in the same
PR, and confirm nothing server-side reads it over HTTP (the China desk precedent:
`/chinaspecialdata/special.json`). On the gated build, do not emit the fetch at all.

---

## §3 The wall design

### 3.1 One wall, two notes

The reference page ships **one** `.tier-wall` CTA card plus **one** `.gate-note` strip. Keep
that discipline: five walls on a page this long is nagging, and Doctrine Law 4 bans stacked
disclaimers. This page gets:

- **one `.tier-wall`** (`#bcn-tier-wall`), at §03 — *after* the reader has had the table and
  the chart. This placement is deliberate: the desk region sits above the free content in
  DOM order, so putting the ask there would paywall the visitor before they see anything.
  Do **not** reorder the DOM between builds; instead the desk region gets only skeletons +
  a note, and the single CTA lands at §03. Value first, ask second.
- **two `.gate-note` strips** — one above the desk skeletons, one above the §01 table.
  Different sections, not stacked. No CTA button on either; they explain, they do not sell.
- `.gh` skeletons everywhere a paid panel would be, and a `.gate-pill` on the two walled
  section headings (`Theme Rotation Desk`, `Baskets by category`).

### 3.2 Component names — copy the idiom, swap the tokens

Reuse the class names from `templates/special_situations.html.j2` verbatim: `.gh`,
`.gate-pill`, `.gate-note`, `.gated`, `.tier-wall`, `.tw-ghosts`, `.tw-ghost`, `.tw-card`,
`.tw-lock`, `.tw-h`, `.tw-p`, `.tw-acts`, `.tw-btn`, `.tw-note`, `.tw-signed`. One idiom,
one name.

**The CSS cannot be lifted verbatim.** The two pages use different colour-token
vocabularies, and `theme.css` says so at line 1402. `special_situations.html.j2` defines
`--blue --ink --faint --grid --card --surface --surface-brd --surface-shadow` **locally, in
its own `<style>` block** (lines 19–37) — none of them exist on `baskets_china.html`. Lifting
the wall CSS unchanged yields `var(--card)` → unset → transparent and `var(--ink)` → unset →
inherited: a wall that looks broken but still "works", which review will miss. Transliterate:

| special_situations | baskets_china | dark value |
|---|---|---|
| `--card` | `--panel` | `#181b21` — identical |
| `--grid` | `--line` | `#2a2f3a` — identical |
| `--ink` | `--text` | `#d7dce3` |
| `--faint` | `color-mix(in srgb, var(--muted) 78%, transparent)` | — |
| `--blue` | `--link` | `#7aa7e0` dark / `#285fff` light |
| `--surface` | `color-mix(in srgb, var(--panel) 80%, transparent)` | — |
| `--surface-brd` | `color-mix(in srgb, var(--text) 13%, transparent)` | — |
| `--surface-shadow` | the literal from `special_situations.html.j2:37` | — |

`#8b5cf6` (the lock violet) is a hard-coded hex on the reference page too — keep it hard-coded,
identical, in both. The CTA gradient stays `linear-gradient(135deg, var(--link), #8b5cf6)`:
brand blue → violet, **never signal amber** (masterplan W1, terminal paywall lesson). Do not
introduce any other new colour.

The exact, ready-to-paste CSS block is the `/* ── tier gate ── */` section of
`mockups/refs/seo_supercharge/baskets_china_preview.html`. Copy it.

### 3.3 Markup

The `.tier-wall` at §03 — structurally identical to `special_situations.html.j2:542–574`:

```jinja
{% if gate %}
<div class="tier-wall" id="bcn-tier-wall">
  <div class="tw-ghosts" aria-hidden="true">
    {% for _ in range(3) %}
    <div class="tw-ghost"><div class="gh gh-tkr"></div><div class="gh gh-line"></div><div class="gh gh-line short"></div></div>
    {% endfor %}
  </div>
  <div class="tw-card">
    <svg class="tw-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
    <div class="tw-h">
      <span class="l-en">{{ gate.locked }} more baskets, and {{ gate.n_members }} holdings, are open to members</span>
      <span class="l-zh">另有 {{ gate.locked }} 个篮子、{{ gate.n_members }} 只成分股向会员开放</span>
    </div>
    <div class="tw-p">
      <span class="l-en">You’re reading {{ gate.preview }} of {{ total }} baskets and how each one has traded.
        Members also get every basket’s holdings, our score and stance for each one, the rotation desk,
        and the entry radar.</span>
      <span class="l-zh">你正在查看 {{ total }} 个篮子中的 {{ gate.preview }} 个及其走势。会员还可看到每个篮子的成分股、
        我们给出的评分与操作倾向、主题轮动台，以及入场雷达。</span>
    </div>
    <div class="tw-acts">
      <a class="tw-btn" href="plans.html">{{ t('See plans', '查看方案') }}</a>
      <span class="tw-note">{{ t('7-day Pro trial · cancel anytime', 'Pro 7 天试用 · 随时取消') }}</span>
    </div>
    <div class="tw-signed" id="bcn-tw-signin" hidden>
      <a href="#" data-act="signin">{{ t('Already a member? Sign in', '已是会员？登录') }}</a>
    </div>
  </div>
</div>
{% endif %}
```

Every count (`gate.locked`, `gate.preview`, `gate.n_members`, `total`) is computed by the
builder from the real board. **Never hardcode 8 / 14 / 285 / 22** — membership changes nightly,
and a stale honest-total is a dishonest total.

### 3.4 Wall copy — verbatim, EN + ZH

Glance tier throughout: plain words, no internal vocabulary, no untranslated statistics,
no raw slugs. `.tw-h` is 11 words; `.tw-p` is 40, matching the reference.

**`.tw-h`** (§03 wall headline)
- EN — `{locked} more baskets, and {n_members} holdings, are open to members`
- ZH — `另有 {locked} 个篮子、{n_members} 只成分股向会员开放`

**`.tw-p`** (§03 wall body)
- EN — `You’re reading {preview} of {total} baskets and how each one has traded. Members also get every basket’s holdings, our score and stance for each one, the rotation desk, and the entry radar.`
- ZH — `你正在查看 {total} 个篮子中的 {preview} 个及其走势。会员还可看到每个篮子的成分股、我们给出的评分与操作倾向、主题轮动台，以及入场雷达。`

**`.tw-btn`** — EN `See plans` · ZH `查看方案` → `href="plans.html"`
**`.tw-note`** — EN `7-day Pro trial · cancel anytime` · ZH `Pro 7 天试用 · 随时取消`
**`.tw-signed`** — EN `Already a member? Sign in` · ZH `已是会员？登录`

**`.gate-note` #1** (above the desk skeletons, `#bcn-desk-note`)
- EN — `The desk scores and ranks all {total} baskets and says what to do about each one. Members see it in full — the macro backdrop and market breadth stay open to everyone.`
- ZH — `交易台对全部 {total} 个篮子评分排名，并给出每个篮子的操作建议。会员可查看完整内容 —— 宏观背景与市场宽度对所有人开放。`

**`.gate-note` #2** (above the §01 table, `#bcn-table-note`)
- EN — `Showing {preview} of {total} baskets — the first two in each category. Members see all {total}, each basket’s score and stance, and search, sorting and filters across every name.`
- ZH — `显示 {total} 个篮子中的 {preview} 个 —— 每个类别的前两个。会员可查看全部 {total} 个篮子、每个篮子的评分与操作倾向，以及覆盖全部标的的搜索、排序与筛选。`

**§02 chart note** (one clause appended to the existing `#chart-note`, not a third gate-note)
- EN — `Showing the last year for the {preview} baskets above. Members get the full history back to {first_year} and the category-average view.`
- ZH — `显示上述 {preview} 个篮子的近一年走势。会员可查看回溯至 {first_year} 年的完整历史与类别均值视图。`

**Doctrine check.** No banned Tier-1 vocabulary: no `IGNITION` / `WATCH` / `UPTURN_CONFIRMED`
/ `turn_state` / `clean_entry_q` / `sig_tier` / `slow reco` / `z-score` / `n=` / raw slugs.
"score and stance" is the plain-word pair for what is withheld. The free page keeps its
stance line in the tagline ("Use them to see which China themes are leading or fading"),
so the page is not stance-less for an anonymous reader (Law 1). One as-of, one footnote.
No falsifier/refutation language anywhere (operator 2026-07-27).

### 3.5 Payload shape

`site/premiumdata/baskets_china.json`, `schema: tier_payload.v1`.

**Deviation from the reference, and why.** `special_situations` ships `rows_html` because its
rows are server-rendered from a Jinja partial. This page has no server-rendered rows: every
module is drawn by client JS from `BASKETS` / `CHART`. So the payload ships **data, not
markup**. The pattern's "one source, rendered twice" requirement is still met — more
strongly, in fact: there is exactly **one** renderer (`renderBTable`, `detailSection`,
`baskets_desk.js`), and it consumes the inline preview and the hydrated remainder alike.
Do not introduce a second markup path.

```jsonc
{
  "schema": "tier_payload.v1",
  "page": "baskets_china",
  "gated": true,
  "required_tier": "essential",
  "built": "<same stamp as the shell>",
  "total": 22,          // every basket in this build
  "preview": 14,        // free slice size
  "locked": 8,          // total - preview
  "n_members": 285,     // holdings behind the wall, for the wall headline

  "baskets": [ /* the 8 withheld basket objects, COMPLETE */ ],
  "fields":  { /* per-basket-id: the fields stripped from the 14 free objects —
                  members, cycle, changelog, score, label(_zh), reco(_zh),
                  clean_entry_q, turn_state, turn_*, top_overlaps */ },
  "chart":   { "dates": [...], "bench": [...], "baskets": { /* full history, all 22 */ } },
  "theme_intel": { /* the withheld keys: themes, act_now, entries, rollover,
                      rotation_5d, breadth_leaders, breadth_laggards,
                      recommendations, weights, signal_calibration, regime_sizing,
                      and the *_names arrays of impulse_scorecard */ }
}
```

Write it on **every** build, including the ungated one (as an empty
`{"schema": "tier_payload.v1", "page": "baskets_china", "gated": false, ...}`), so flipping
`gated` off never strands a readable full board at a path the page stopped asking for.

### 3.6 Hydration

Port `special_situations.html.j2:802–882` unchanged in structure — including both traps it
already solves:

- **`whenAuthSettled()`** — `theme.js` is deferred, so `MDXAuth` does not exist while an
  inline script runs. Wait for the `mdx-auth` event with a 3s timeout fallback.
- **`freshSession()`** — the shared cookie carries a ~1h token, so a long-idle member can be
  signed in with a token the server rejects. Call `getSession()` before the fetch.

`hydrate(payload)` must, in this order: merge `payload.fields` back onto the 14 preview
baskets → append `payload.baskets` → replace `CHART` → merge `payload.theme_intel` into
`BASKETS.theme_intel` → remove `#bcn-tier-wall`, `#bcn-desk-note`, `#bcn-table-note` and
every `.gate-pill` → drop `.gated` from every inert container → **re-run the existing
renderers** (`renderBTable`, `renderCards`, `renderDetails`, `renderChart`,
`renderEntryRadar`, the `baskets_desk.js` entry point, `renderFormingNarratives`) → re-wire
tips → `relabelAll()`. On 403 the wall stays exactly as baked, and `#bcn-tw-signin`
un-hides when there is no session at all.

**Trap (the pattern names it, and it bites harder here).** Empty-state branches read the
sliced data. `renderEntryRadar()` prints *"None right now — most days none."* when its
candidate list is empty — on the gated build that would be a **lie over content that
exists**. Every such branch must be guarded by the gate state, and the honest empty state
must still be reachable for a genuinely empty plane. Same for the desk's own empty checks
(`baskets_desk.js:310` `const empty = ...`).

---

## §4 Inert controls

Per `docs/TIER_PREVIEW_PATTERN.md` §Controls: bake them, mark them inert, and **say why in
one plain line** — dead buttons with no explanation read as a bug. The `.gate-note` strips in
§3.4 are that line; no control needs its own micro-copy.

`.gated` → `opacity:.42; pointer-events:none; user-select:none`, and non-sticky on phones.

| Control | Gated build | On hydrate |
|---|---|---|
| `#basket-search` (M13) | `.gated`, `disabled` — it would search 14 baskets and 0 members | `.gated` removed, `disabled` cleared |
| `#tbl-cat-filter` (M16) | `.gated` — filtering to a category with 2 of 4 rows misleads | live |
| `#btbl-mode` (M15) | live, **two tabs baked** (Return · vs CSI 300) | third tab (σ) added by the renderer |
| `#btable` column headers (M14) | live — re-sorting 14 rows the reader already has leaks nothing, and dead headers read as broken | unchanged |
| `#table-more` ("See more N") | **not rendered** — it cannot expand | rendered by `renderBTable` |
| `#chart-scope` (M18) | `.gated`, "Baskets" only — the "Categories" average needs all 22 | both scopes, live |
| `#chart-modes` | live (rel · abs, both free) | unchanged |
| `#chart-ranges` | live, 60d · 120d · 1Y | "All" added |
| `#chart-cats` | `.gated` | live |
| `#card-sort-tabs`, `#hz-tabs` (M19) | **not rendered** — §03 is entirely behind the wall | rendered |
| M9 scorecard modals | `.gated` — faces show real counts, modals hold paid names | live |

**Why the column headers stay live while everything else goes inert:** the test is whether
the control *reaches content the free build does not have*. Sorting 14 rows does not; search,
category filter, chart scope and "See more" all do. Note this reasoning in a code comment —
it is the rule the next page (`hk.html`) will need.

Because every one of these controls is JS-generated from the payload at runtime, "bake them
fully" resolves here as: **the gated build renders the same containers, the renderers build
whatever the payload supports, and hydration re-runs the same renderers with the full
payload.** No control is ever *omitted for the entitled viewer* — which is the outcome the
pattern's rule actually protects against.

---

## §5 SEO head

Set before `{% include "_seo_head.html.j2" %}`. Today's `<title>` is not brand-suffixed and
differs from `seo_title`; unify them.

```jinja
<title>China Thematic Baskets vs CSI 300 — MastermindX</title>
{% set seo_title = "China Thematic Baskets vs CSI 300 — MastermindX" %}
{% set seo_desc  = "Track 22 equal-weight A-share theme baskets against the CSI 300 — returns for Chinese semiconductors, AI compute, baijiu, gold miners and banks, after each Asia close." %}
{% set seo_path  = "baskets_china.html" %}
```

Use those strings exactly. Measured: `<title>` **47 chars** (brand-suffixed, ≤ 70 ✅);
`seo_desc` **167 chars** (inside 50–170 ✅). The description leads with the entity-bearing
nouns the GSC pull showed demand for (A-share themes, CSI 300, semiconductors) rather than
with our product vocabulary.

- Canonical — `_seo_head.html.j2` emits `https://www.mastermind-x.com/baskets_china.html`
  from `seo_path`. Self-canonical. ✅ Verify it survives to the baked bytes.
- The `lite` variant (`baskets_china_ths.html`) keeps its own title and its own
  `seo_path`; it is **not** part of W1b and is not made public.
- No `noindex` meta, and confirm `app/regwall.py` stops injecting its
  `X-Robots-Tag: noindex, noarchive` header (`app/regwall.py:144`) for this path — that
  header is *the* reason the page currently reads as a soft 404 to Googlebot. Gate §0.1
  is not satisfied by a 200 alone; check the response headers.

---

## §6 ANTI-goals — do not do these

1. **No thinning for entitled users.** A hydrated viewer sees 22 baskets, 285 holdings, the
   Score column, full chart history, the whole desk — byte-identical in substance to today.
   The split adds a free tier; it removes nothing from the paid one. (§0.10 gates this.)
2. **No client-side-only hiding.** The paid rows must not be in the shipped document at all.
   `display:none`, `visibility:hidden`, a CSS blur, or a JS tier check over baked rows is a
   marketing wall, not a gate — one `view-source` away. Build split only. (§0.8 gates this.)
3. **No new palette, no new faces.** Reuse `theme.css` tokens and the page's existing type
   scale. The only new colour is `#8b5cf6`, already hard-coded on the reference page for
   exactly this component. No new webfont, no new weight.
4. **`红涨绿跌` holds.** `theme.css:138` flips `--up`/`--down` under `html[data-lang="zh"]`.
   Every directional number must paint from `--up`/`--down` (or `.pos`/`.neg` that resolve
   them) — never a hard-coded green/red. The wall, the skeletons and the gate notes carry
   **no directional colour at all**; do not tint them by state. Verify against
   `baskets_china_preview_zh.png`.
5. **No hardcoded counts.** Every "14 of 22", "8 more", "285 holdings" is computed. A stale
   honest-total is worse than no total.
6. **No category average from a partial membership.** The chart's "Categories" scope is
   walled precisely because a mean over 2 of 4 baskets is a wrong number wearing a right
   number's clothes.
7. **Do not make `basket_china/*.html` public.** The 22 per-theme detail pages hold full
   member lists. They stay Insider+ and stay out of `sitemap.xml`. Consequence: on the gated
   build, basket names in the §01 table are **plain text, not links** (`nameLink()` returns a
   bare span). A public page linking to 22 pages that 302 to a sign-in is exactly the
   soft-404 crawl shape this whole program exists to undo. Hydration restores the links.
8. **No `validated` in new copy** (CI-guarded), and no falsifier/refutation language on this
   surface (operator 2026-07-27).
9. **Do not reorder the DOM between the gated and ungated builds.** Placement is solved with
   skeletons and one well-placed CTA (§3.1), not with two layouts.

---

## §7 Doctrine tensions — flagged, not silently decided

**T1 — "the page's own default sort" would hand over the ranked head.** The commissioning
brief suggests the free slice be "top-N baskets by the page's own default sort". This page's
default sorts are `20d` return desc (table) and **`score` desc** (cards) — both best-first,
and the second is our own graded output. `docs/TIER_PREVIEW_PATTERN.md` forbids exactly this:
*"the ranked 'top N by magnitude' boards get no preview at all."* I have specified a neutral
slice instead (first two per category, alphabetical). **If the orchestrator prefers the
literal brief, that is a conscious override of the ratified pattern and should be recorded
as one** — but the neutral slice is also strictly better for SEO (all 7 categories crawlable
instead of whichever ones happened to rally).

**T2 — "full column set but truncated depth" cannot hold literally.** The brief asks for the
full column set. The table's `Score` column is our 0–100 graded output — signal authority
under A4, and the single most valuable cell in the row. Shipping it free would wall the
basket *names* while giving away the *scores*, which is backwards. I have walled the column
and dropped the sparkline with it (it is drawn from the withheld level-series tail). Free
columns are the six return windows + the benchmark row. **Flagging because it contradicts
the brief's parenthetical.**

**T3 — `VALIDATED EDGE` would become crawlable copy.** M22 (Reversal Sleeve card) ships
`{{ t('VALIDATED EDGE','已验证优势') }}` today (`baskets_china.html.j2:~430`). It survives
`scripts/check_validated_claims.py` as existing copy, but masterplan §0.13 says "validated"
never appears in **new** user-facing copy — and making this page anonymous-public puts that
chip in Google's index and in AI-overview extractions. I have walled M22, which resolves the
tension without a copy fight (it is signal-authority content anyway: a strategy card with
Sharpe and rebalance stats). **If a future wave un-walls it, the phrase needs an adjudication
first.** Flagging rather than quietly rewriting operator-adjacent copy.

**T4 — M9's split is the one genuinely arguable cell.** "±3% daily impulse" and "52-week
extremes" counts are market facts (free), but they are computed *over our basket universe*,
so the count is partly a statement about our coverage. I judged them free — they are the
same class of number as the breadth card, and a count without names cannot be traded on.
The "recommendation tally" card (M10) I walled, because a tally of our own reco verbs is a
summary of the graded output. **A reviewer could reasonably wall all three; the cost is
small.**

**T5 — the free page has no signal stance of its own.** Doctrine Law 1 wants every panel to
answer "so what do I do". Once every graded module is walled, the anonymous page's honest
answer is "here is how China themes have traded; what to do about it is the paid part." The
tagline carries that ("Use them to see which China themes are leading or fading"), and the
gate notes say plainly what is missing rather than implying the page is complete. This is
compliant, but it is worth naming: **a tier-preview page is structurally a Law-1 edge case**,
and the same question will recur on `hk.html` and `etfs.html`. If the orchestrator wants a
free stance, the cheapest honest one is a single plain sentence derived from breadth alone
(M6) — e.g. "More than half the market is above its 50-day line." That needs no graded input
and would give the free page a real read. **Not specified here; raising it as an option.**

## §8 Commissioner rulings (Fable, 2026-08-03) — binding on the build

- **T1 RULED — neutral slice stands.** The spec's first-two-per-category
  alphabetical slice is adopted; the commissioning brief's "top-N by default
  sort" is overruled (it would preview the ranked head, which the ratified
  pattern forbids).
- **T2 RULED — Score column dropped from the free build.** Never lock-iconed
  per row.
- **T3 RULED — the VALIDATED EDGE card stays walled.** Standing note: if any
  later wave un-walls it, the "validated" wording must first clear the
  check_validated_claims CI guard and the promotion-gauntlet law — expect a
  rename, not an exemption.
- **T4 RULED — impulse/extremes COUNTS stay free.** They are how-the-market-
  traded context, not graded output; consistent with the organizing principle.
- **T5 RULED — add the honest stance line.** The free page carries ONE
  plain-words sentence derived from breadth data alone (no graded inputs),
  bilingual, e.g. EN "Breadth is firming — more baskets rising than falling
  this week. The graded entry reads are member content." / zh equivalent in
  natural product Chinese. This satisfies Doctrine Law 1 without leaking
  signal authority, and is the standing recipe for hk.html/etfs.html
  conversions.
