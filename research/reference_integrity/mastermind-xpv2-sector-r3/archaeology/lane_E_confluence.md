# Lane E — Sector Central (US) Confluence: four-universe archaeology

XPV2-SC-R3A sub-lane E. Scope: `templates/sector_central.html.j2` (Confluence view mount only),
`templates/subsectors.js` (the shared render engine for all four tabs), `templates/subsector_detail.html.j2`,
`scripts/build_subsector_confluence.py`, `engine/subsector_confluence.py`, `engine/sector_signals.py`
(state vocabulary), and the four production JSON payloads under `site/marketdata/`. Authority =
production code + committed payload bytes (read via `git show HEAD:<path>` where the sparse
worktree lacked the file on disk); the R2 review (`research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/data_authority.md`)
is treated as a lead, checked against these primaries.

## 0. Are the four universes independent artifacts?

**Yes — four separate JSON files, four separate compute functions, one shared render/template
path.** `templates/subsectors.js:39-44` (`var DS = {...}`) maps each tab to its own fetch URL,
output directory, and payload key:

```
subsectors: { url: 'marketdata/subsector_confluence.json',          dir: 'subsector/',         prefix: '',   groupsKey: 'subsectors' }
baskets:    { url: 'marketdata/basket_confluence.json',              dir: 'subsector/',         prefix: 'b-', groupsKey: 'baskets' }
nasdaq:     { url: 'marketdata/subsector_confluence_nasdaq.json',    dir: 'subsector_nasdaq/',  prefix: '',   groupsKey: 'subsectors' }
russell:    { url: 'marketdata/subsector_confluence_russell.json',   dir: 'subsector_russell/', prefix: '',   groupsKey: 'subsectors' }
```

`groupsOf(ds)` (`templates/subsectors.js:67`) reads `(DATA[ds]||{})[DS[ds].groupsKey]` — there is
no code path anywhere in `subsectors.js` that merges, concatenates, or falls through between the
four `DATA[ds]` objects. Each is `fetch()`-ed independently (`templates/subsectors.js:559-562`,
`Promise.all` over `Object.keys(DS)`) and stored under its own tab key. Client-side mixing across
universes is structurally impossible in the current code; the only way a foreign row enters a
universe is if the PRODUCER wrote it into the wrong JSON file (see §7 for the detector).

Producers (all in `engine/subsector_confluence.py`):
- S&P: `compute_subsector_confluence()` (line 364) — Finviz sub-industry map, `subsector_scan._industry_map()`.
- Baskets: `compute_basket_confluence()` (line 428) — curated `data/baskets/membership.json`.
- Nasdaq: `compute_nasdaq_confluence()` (line 618) → `_compute_index_desk("nasdaq", "QQQ", ...)` (line 590) → `_compute_partition()` (line 536) over `data/baskets_nasdaq/membership.json`.
- Russell: `compute_russell_confluence()` (line 623) → `_compute_index_desk("russell", "IWM", ...)` over `data/baskets_russell/membership.json`.

Build entrypoints, `scripts/build_subsector_confluence.py`:
- `main()` (line 174) writes S&P → `BOARD_JSON = "marketdata/subsector_confluence.json"` and baskets → `BASKET_JSON = "marketdata/basket_confluence.json"` in one nightly call (`_build_payloads`, line 149).
- `main_index(ns)` (line 377) writes Nasdaq/Russell → `marketdata/subsector_confluence_{ns}.json` via `_index_dirs(ns)["board"]` (line 372).

## 1–11. Per-universe comparison

| # | Item | **S&P 500** | **Thematic baskets** | **Nasdaq-100** | **Russell-2000** |
|---|---|---|---|---|---|
| 1 | Payload + producer | `site/marketdata/subsector_confluence.json` ← `engine.subsector_confluence.compute_subsector_confluence()` (`engine/subsector_confluence.py:364`), written by `scripts/build_subsector_confluence.py:main()` (`BOARD_JSON`, line 46) | `site/marketdata/basket_confluence.json` ← `compute_basket_confluence()` (`engine/subsector_confluence.py:428`) over `data/baskets/membership.json` (read at `build_subsector_confluence.py:161-163`), written by same `main()` (`BASKET_JSON`, line 47) | `site/marketdata/subsector_confluence_nasdaq.json` ← `compute_nasdaq_confluence()`→`_compute_index_desk("nasdaq","QQQ",…)` over `data/baskets_nasdaq/membership.json`, written by `scripts/build_subsector_confluence.py:main_index("nasdaq")` (line 377) | `site/marketdata/subsector_confluence_russell.json` ← `compute_russell_confluence()`→`_compute_index_desk("russell","IWM",…)` over `data/baskets_russell/membership.json`, written by `main_index("russell")` |
| — | `universe` field (verbatim) | `"sp500_subsectors"` (`engine/subsector_confluence.py:403`) — confirmed live: `git show HEAD:site/marketdata/subsector_confluence.json` → `universe: sp500_subsectors` | `"curated_baskets"` (line 468) — confirmed live | `"nasdaq_subsectors"` (via `_compute_index_desk` param, line 620) — confirmed live | `"russell_subsectors"` — confirmed live |
| 2 | Universe count (computed where) | `n_subsectors` = `len(groups_map)` = ALL Finviz sub-industries BEFORE the `MIN_MEMBERS`/history filter (`engine/subsector_confluence.py:376`). Live payload: **113** | `n_baskets` = `len(baskets)` = count AFTER the per-basket `MIN_MEMBERS<3` skip and successful `score_group` (there is no raw pre-filter total kept — see GAP) (line 471). Live: **49** | `n_subsectors` = `len(subsectors)` = raw dict size of the curated Nasdaq membership file, BEFORE filtering (`_compute_partition`, line 573). Live: **12**, `n_gateable`=**12** (nothing dropped) | Same mechanism. Live: `n_subsectors`=**93**, `n_gateable`=**93** (nothing dropped) |
| 3 | Gateable/timed count | `n_gateable = len(subs)` — groups that passed `MIN_MEMBERS>=3` AND `score_group` returning non-`None` (needs ≥220 close bars post-index-build, `engine/subsector_confluence.py:228`). Live: **65** | Same `score_group` gate, no separate `n_gateable` field is emitted for baskets — coverage dict only carries `n_baskets` (§4) | **12** (all raw entries gated) | **93** (all raw entries gated) |
| 4 | Thin count + exact wording | `n_thin = n_total - len(subs)` = **48** — groups that FAILED the gate and are **NOT present anywhere in the `subsectors` array**. Coverage dict: `_breadth_coverage(subs, {"n_subsectors":113,"n_gateable":65,"n_thin":48,...})` (`engine/subsector_confluence.py:405-408`). UI wording, `templates/subsectors.js:221-222`: `"<n_gateable> of <n_subsectors> subsectors have enough live data to time · <n_thin> thin (listed in the table, not timed)"` / ZH `"…个数据稀疏（列于表内，不计时）"`. **DEFECT (confirmed by code trace, not the review):** the wording asserts the 48 thin groups are "listed in the table" — they are not. `fullTableSection()` (`templates/subsectors.js:465`) renders `groupsOf(ds).slice()`, i.e. exactly the 65-row `subs` array; the 48 dropped groups never enter `DATA[ds].subsectors`, so they cannot appear in any table row. The wording describes a DIFFERENT dropout concept — the `reliability:"low"` flag (`n_low_conf`=31 of the 65, engine `reliability()` line 73, `<6` priced members) — which genuinely IS listed with a "thin" dot (`relDot()`, line 58, "Thin data — read with caution"). The header text conflates "gate-dropped" (48, invisible) with "reliability-thin" (31, visible) under one word "thin". | Coverage = `_breadth_coverage(baskets, {"n_baskets":49})` (line 471) — **no `n_gateable`/`n_thin`/`n_subsectors` keys at all**. Consequence: `templates/subsectors.js:220` guards on `cov.n_gateable != null`, which is `false` for the baskets tab, so **the entire honesty/thin-but-listed line never renders on the Thematic Baskets tab** — this is a genuine per-universe absence, not a bug in the wording (there is nothing to word). | Same shape as S&P: `n_thin=0` in the live payload (nothing dropped this cycle) so the "· N thin" clause is currently suppressed by the `(cov.n_thin ? … : '')` ternary (`templates/subsectors.js:221`) — the wording code is present but silent because the count is 0, which is the honest state (never observed a nonzero Nasdaq `n_thin` in this file, so the "0 vs missing" branch cannot be distinguished from real data here — see GAPS). | Same as Nasdaq: `n_thin=0`, clause currently suppressed. |
| 5 | State distribution (labels EN/ZH, computed where) | Two orthogonal state layers, shared by all four universes (same engine code): **(a) entry tier** T1–T4 from `signal_gate` (cascade freshness, badges rendered by `tierBadge()`, no EN/ZH pair — numeric/letter code only). **(b) regime state**, `engine/sector_signals.py:_STATE_META` (lines 86-114): `BUY`→EN`"BUY"`/ZH`"买入"`; `BUY_PARTIAL`→`"BUY"`/`"买入"`; `SETUP_BUY`→`"SETUP"`/`"预备"`; `NEUTRAL`→`"NEUTRAL"`/`"中性"`; `EXTENDED`→`"EXTENDED"`/`"过热"`; `TOPPING`→`"TOPPING"`/`"见顶"`; `SELL`→`"SELL"`/`"卖出"`; `BELOW_TREND`→`"BELOW TREND"`/`"趋势下方"`; `OVERSOLD_BOUNCE`→`"OVERSOLD BOUNCE"`/`"超卖反弹"`. **(c) coarse `class`** (sort/ribbon bucket), `engine/subsector_confluence.py:_classify` (line 185): `entry_now | forming | tailwind | neutral | late | headwind`, UI labels `CLASS_META` (`templates/subsectors.js:81-87`): `entry_now`→`"Entry now"`/`"现可入场"`; `tailwind`→`"Tailwind"`/`"顺风"`; `neutral`→`"Neutral"`/`"中性"`; `late`→`"Late"`/`"偏晚"`; `headwind`→`"Headwind"`/`"逆风"`. **`forming` has NO ribbon bucket** — `RIBBON_ORDER` (line 88) omits it, and `universeStats()` (`templates/subsectors.js:93`) increments `counts.neutral++` for any class not already a key in `counts`, so forming groups are silently folded into the "Neutral" ribbon segment. Live class spread for S&P (65 rows): `neutral 21, late 18, tailwind 16, headwind 9, entry_now 1` (`Counter` over the live payload) — matches DAC-005/DAC-003's cited `1/16/21/18/9`. | Identical state machinery (same `sector_signals`/`_classify` code, only the tickers differ) | Identical machinery, `benchmark="QQQ"` changes `rs_60d` input, not the label vocabulary | Identical machinery, `benchmark="IWM"` |
| 6 | Row identity + order | **Identity**: `key = _slug(sub_industry_name)` (`engine/subsector_confluence.py:379,382`, `_slug` at line 101) — one row per Finviz sub-industry name; `kind` is ALWAYS `"subsector"` for this payload's `subsectors[]` array (never `"basket"`/`"concept"`), and rows carry NO `basket_id` field. **Order**: producer-fixed. `subs.sort(key=lambda g: (_CLASS_ORDER.get(g["class"],9), -g["entry"]["weight"], -(g["regime"]["rs_60d"] or 0)))` (line 398-399) — `_CLASS_ORDER = {entry_now:0, forming:1, tailwind:2, neutral:3, late:4, headwind:5}` (line 208). Group cards (`boardSection`, `templates/subsectors.js:289-296`) render this producer order verbatim via `.filter()` (order-preserving); only the "Avoid" column additionally stable-partitions headwind-before-late (line 295). The **"All subsectors" full table is CLIENT re-sorted**: default `SORT[ds] = {col:'tier', dir:1}` (`templates/subsectors.js:467`, applied at 471-478) — i.e. the table's default view is NOT the producer class/weight/rs60 order, it's ascending entry-tier string sort (missing tier → `'Z'`, sorts last), and any column click re-sorts client-side without touching `DATA[ds]`. | **Identity**: `key = _slug(bid)` where `bid` is the curated basket id (`engine/subsector_confluence.py:446`), PLUS `g["basket_id"]=bid` is explicitly stamped on every row (line 451) — the field the S&P/Nasdaq/Russell payloads never carry. `kind="basket"` (default arg, line 429). Live: `kinds={'basket'}` across all 49 rows. | Producer order and sort key IDENTICAL formula (`subs.sort(...)`, line 569-570, same `_CLASS_ORDER`/entry-weight/rs60 tuple) but computed on the Nasdaq partition. **Identity**: `key=_slug(key)` from the curated membership dict key, `kind="subsector"` (line 550). Amalgamations get `kind="sector"`, `key="amalg-"+_slug(key)` (line 563) — a DIFFERENT id prefix namespace, so amalgamation rows are never mistakable for subsector rows even within the same `sectors[]` array. | Same identity/order formula over the Russell partition; `kind="subsector"` for the 93 rows. |
| 7 | Group detail behavior | `templates/subsector_detail.html.j2` renders one page per group from the COMMITTED JSON (no recompute), `render_pages()` (`scripts/build_subsector_confluence.py:203-236`). `back="../subsectors.html"`, `stock_base="../stock.html#"` (line 214-215). Detail file path: `_detail_key(g)` (line 96-98) = `g["key"]` unprefixed for `kind!="basket"` → written to `site/subsector/<key>.html`. Page shows: label/label_zh, sector, `kindLabel` (derived from `DETAIL.kind`: `"basket"`→"thematic basket"/"主题篮子", `"sector"`→"amalgamated complex"/"汇聚综合体", `"concept"`→THS, else default subsector wording — `templates/subsector_detail.html.j2:79-82`), a low-reliability warning banner if `reliability==="low"` (line 78, exact EN: `"⚠ thin · <n> names"`, title `"fewer than 6 priced members — an equal-weight index this thin is driven by 1–2 names"`), the index chart, and the member table. | Same template, but `_detail_key` PREPENDS `"b-"` (`scripts/build_subsector_confluence.py:97-98`) → written to the SAME `site/subsector/` directory as S&P subsectors, disambiguated only by the `b-` filename prefix. `back="../subsectors.html"`, `stock_base="../stock.html#"` (both same as S&P — set at `render_pages()` line 215-216, shared code path). | `_detail_key` unprefixed, written to a SEPARATE directory `site/subsector_nasdaq/` (`render_index_pages`, `scripts/build_subsector_confluence.py:410-412`, `_index_dirs("nasdaq")["detail"]="subsector_nasdaq"`), `back="../subsectors.html"`, `stock_base="../stock.html#"` (line 424). Amalgamation detail pages get `kind_label_en = "<Nasdaq-100> complex"` (line 418) instead of the generic subsector label. | Same as Nasdaq but directory `site/subsector_russell/` and label `"Russell-2000 complex"`. |
| 8 | Members listing | `g["members"]` populated when `with_members=True` (default for subsector/basket groups; `False` for the 11-sector S&P rollup, line 394). Producer-sorted: `members_detail.sort(key=lambda m: (-(m["stock_weight"] or 0.0), -(m["vs_basket"] if m["vs_basket"] is not None else -999)))` (`engine/subsector_confluence.py:270-271`) — own-cascade weight descending, tie-broken by 20d return vs the basket descending. Detail template renders this array in payload order (no client re-sort), `templates/subsector_detail.html.j2:100-109`. | Same `members_detail` sort formula (shared `score_group`, same lines). Amalgamation rows in Nasdaq/Russell ALSO carry members (`with_members=True`, line 565) even though S&P's own `sectors[]` rollup does not. | Subsector rows: full members. Amalgamation rows: full members (`with_members=True`, line 561-565) — unlike the S&P sector rollup which has none. | Same as Nasdaq. |
| 9 | Stock detail behavior/destination | `stockHref(tk)` (`templates/subsectors.js:66`) = `'stock.html#' + encodeURIComponent(tk)` — used in the full members table, the double-gated picks table (`templates/subsectors.js:325`), and `templates/subsector_detail.html.j2:104` via `DETAIL.stock_base` (`'../stock.html#'`, one `../` deeper because detail pages live one directory down). Identical mechanism for all four universes — no per-universe stock destination variance found. | Same | Same | Same |
| 10 | Coverage wording (verbatim) | EN: `"<n_gateable> of <n_subsectors> subsectors have enough live data to time"` + (if `n_thin`) `" · <n_thin> thin (listed in the table, not timed)"`. ZH: `"<n_gateable>/<n_subsectors> 个子行业有足够实时数据可计时"` + `" · <n_thin> 个数据稀疏（列于表内，不计时）"` (`templates/subsectors.js:221-222`, `DS[ds].noun` swaps the noun per tab). | Noun = `['baskets','篮子']` but the line **never renders** (§4 — `cov.n_gateable` is `undefined` for this payload). | EN noun `['subsectors','子行业']`, same template; currently silent (`n_thin=0`). | Same as Nasdaq, currently silent (`n_thin=0`). |
| 11 | Row/detail destinations (href patterns) | Group card / full-table row → `detailHref('subsectors', key)` = `'subsector/' + '' + key + '.html'`. Member row → `stockHref(ticker)` = `'stock.html#TICKER'`. | Group → `detailHref('baskets', key)` = `'subsector/' + 'b-' + key + '.html'` (SAME dir, `b-` prefix). Member → identical `stockHref`. | Group → `detailHref('nasdaq', key)` = `'subsector_nasdaq/' + key + '.html'`. Member → identical `stockHref`. | Group → `detailHref('russell', key)` = `'subsector_russell/' + key + '.html'`. Member → identical `stockHref`. |

## 7. The S&P row-identity rule that detects a foreign theme row (pinned)

A row in `site/marketdata/subsector_confluence.json`'s `subsectors[]` array is **genuine S&P
sub-industry** iff ALL of the following hold (any violation = a foreign/theme row that must never
appear here):

1. `kind == "subsector"` — never `"basket"` or `"concept"`. Basket rows are stamped `kind="basket"`
   at `engine/subsector_confluence.py:429` (default arg of `compute_basket_confluence`); S&P rows
   are stamped `kind="subsector"` at line 382 (`_safe_score(..., kind="subsector")`).
2. The row has **no `basket_id` key**. Only `compute_basket_confluence` stamps `g["basket_id"]=bid`
   (`engine/subsector_confluence.py:451`); `compute_subsector_confluence`'s S&P path never sets it.
3. `label` (and `sector`) resolve to an entry produced by `subsector_scan._industry_map()`
   (`engine/subsector_confluence.py:369`, the Finviz S&P-500 sub-industry taxonomy) — i.e. the row's
   `key = _slug(label)` must be traceable to a `(sector, sub)` tuple in that map, not to
   `data/baskets/membership.json`'s basket ids.
4. Top-level payload `universe == "sp500_subsectors"` (line 403) — a whole-file-level guard: this
   string is unique to `compute_subsector_confluence()`; every other producer emits a different
   `universe` value (`curated_baskets` / `nasdaq_subsectors` / `russell_subsectors` / `ths_concepts`).
5. Physically, a theme row can only enter this file if a producer bug writes basket-shaped dicts
   into `BOARD_JSON` instead of `BASKET_JSON` in `scripts/build_subsector_confluence.py:main()`
   (lines 174-186) — the client (`subsectors.js`) has no code path that merges `DATA.baskets` into
   `DATA.subsectors` (§0), so client-side mixing is not a viable attack surface; the detector must
   run against the JSON file bytes / the producer, not the renderer.

## Confirmed vs refuted critic claims (`data_authority.md`)

**Confirmed (numeric/mechanical), verified against live `git show HEAD:site/marketdata/*.json`:**
- DAC-003/005: S&P coverage `65 gateable / 113 total / 48 thin`, class spread `1 entry_now / 16 tailwind / 21 neutral / 18 late / 9 headwind`. Exact match.
- DAC-005: Nasdaq 12, Russell 93, baskets 49. Exact match.
- DAC-005: canonical `CLASS_META` labels `Entry now/现可入场`, `Tailwind/顺风`, `Neutral/中性`, `Late/偏晚`, `Headwind/逆风` — verbatim in `templates/subsectors.js:81-87`.
- DAC-005: canonical thin-but-listed wording exists in code (`templates/subsectors.js:221-222`) — though see §4 above: the wording is present but semantically inaccurate for the 48 gate-dropped groups, and absent entirely on the baskets tab. The review did not catch this deeper defect; it only checked that the STRING exists.
- Auto Manufacturers is the sole live `entry_now` S&P row — confirmed (`entry_now: ['auto-manufacturers']`).
- DAC-004: `subsector_confluence.json` S&P `tailwind`-class rows begin Computer Hardware, Insurance - Brokers, Packaged Foods, Railroads, Insurance - Property & Casualty, Capital Markets, Industrial Distribution — confirmed by direct payload read (first tailwind rows in producer order).

**Refuted / needs correction — one item the review itself got backwards:**
- DAC-005 states "Candidate tab order is S&P 500, Nasdaq-100, Russell-2000, Thematic Baskets" as a
  DEVIATION from a "canonical" order it derives from "Source dataset order is S&P subsectors,
  baskets, Nasdaq, Russell" (i.e. `Object` key order of `var DS = {...}` in `templates/subsectors.js:39-43`).
  **This conflates two different orderings.** The actual PRODUCTION rendered tab strip —
  `templates/sector_central.html.j2:2499-2502` (hard-coded `<div class="sc-tab" data-tab="…">`
  markup, not derived from `DS` iteration at all) — is: **S&P 500 → Nasdaq-100 → Russell-2000 →
  Thematic Baskets**. That is exactly the order DAC-005 calls the candidate's (wrong) order. The
  `DS` object's JS source-declaration order (subsectors, baskets, nasdaq, russell) never drives DOM
  tab order anywhere in the codebase (`setTab`/`render` only toggle `.on` by `data-tab` match,
  `templates/subsectors.js:520-524`) — it only matters for the `Promise.all(Object.keys(DS)...)`
  fetch-kickoff order, which is invisible to the user. DAC-005's "canonical order" citation is not
  evidence of a UI/tab-order defect in the candidate.

## GAPS

- `basket_confluence.json`'s coverage dict never records a pre-filter "raw basket count" (only
  `n_baskets` = post-filter). Could not establish a "universe count vs gateable count" distinction
  for baskets the way S&P/Nasdaq/Russell have one — GAP, not inferred as "no thin baskets exist."
- Nasdaq/Russell `n_thin` is 0 in the current live payload; could not observe the "0 vs missing"
  branch behaviour with real nonzero thin data for these two universes in this pass (no historical
  payload sampled). The suppression logic (`cov.n_thin ? … : ''`, `templates/subsectors.js:221`)
  is identical code to S&P's, so the same "listed in the table, not timed" inaccuracy (§4) would
  apply to Nasdaq/Russell too IF their `n_thin` were ever nonzero — not verified against a live
  nonzero sample, inferred from identical code path only.
- Did not open the FROZEN R2 candidate reference file itself (`Lines 700-721` cited in DAC-004) —
  out of scope per commission (production producers/payloads only); cited only as the review's own
  evidence, not independently re-verified here.
- Premiumdata/tier gating: no `premiumdata/` reference or tier check found for the Confluence
  section or `marketdata/subsector_confluence*.json`/`basket_confluence.json` fetch paths — grepped
  `templates/subsectors.html.j2` and `sector_central.html.j2`'s confluence block; treated as
  UNGATED (public `marketdata/` fetches, `cache:'no-cache'`), not exhaustively proven absent for
  every gating mechanism in the repo.
