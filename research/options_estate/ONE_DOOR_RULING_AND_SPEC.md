# One Door — the options-estate consolidation ruling + build spec (OIP W1.6)

Authored by the Fable main loop, 2026-08-01, under operator authorization of the same day
("SUPER CONFUSING. i don't know why we need five pages for options… you are authorized to
consolidate, merge, group, create, remove, upgrade any features, texts"). Registered as
OIP Amendment 4 (`OIP_MASTERPLAN.md`). Census provenance: three lanes 2026-08-01 (six-page
feature census; workspace architecture deep-dive; Terminal suite + cross-link census) — all
claims re-verified against code at `origin/main` 39abc375c1f.

Binding inputs: `docs/DESIGN_DOCTRINE.md` (wins on conflict), the frontend-design skill,
`WORKSPACE_DESIGN_SPEC.md` (the `.oew` system this extends), `W1_DESIGN_SPEC.md`.

---

## §1 THE RULING

**One door.** `options.html` — the workspace — becomes the estate's only per-name-options
destination. It grows from four modes to five: **Daily Brief · Flow · Scanner · Ticker ·
Leaders** — the five evening questions in reading order (what kind of day → where did the
money go → what screens rich/cheap → the name in front of me → who earned attention).

**Four pages retire into it** (their remaining unique value folds in first — nothing a user
has today is deleted, it moves):

| Page | Folds in (W1.6-A) | Then becomes (W1.6-B) |
|---|---|---|
| `gex.html` "Options Desk" | raw-structure shelf (6 hand-SVG charts: gamma-by-strike, net-gamma profile, strike×expiry heatmap, vol smile, IV term, expiry ladder + greeks) → Ticker mode's "Under the hood" shelf; options primer → Ticker mode footer | redirect stub → `options.html#ticker` (hash `#SYM` → `?t=SYM#ticker`) |
| `options_screener.html` | Scanner uncapped (all rows, declared); 12 numeric range filters + sector dropdown + text filter in a collapsed "More filters" disclosure; per-column sort; CSV export; 7th preset "Put-heavy OI" | redirect stub → `options.html#scanner` |
| `flow_desk.html` "US Options Flow" | new **Flow mode**: full sector list with ⚑ deviation flags · theme-group tiles · sector-ETF money grid · the tide (30-session arc + today's unfolded curve) | redirect stub → `options.html#flow` |
| `flow_leaders.html` | Leaders payload uncapped at the builder (`_BOARD_CAP`); mode keeps top-12 + "Show all N" expander per board; caution tags + ladders already ported by OEU/W1 | redirect stub → `options.html#leaders` |

**Three pages stay real — they were never options pages.** `darkpool.html` (FINRA
off-exchange equity record), `market_structure.html` (index regime & vol), and
`intraday_flow.html` (live equity-continuation board) keep their own URLs and content
untouched. What changes is *presentation*: the nav stops rendering them as five
interchangeable options siblings (§4). intraday_flow's long-term macro-vs-Terminal home
stays deferred exactly as OEU/OIP left it — W1.6 moves only its nav row.

**Terminal: complement, never merge — "one subscription, two clocks."** Census-verified:
`terminal_live_options` ships bundled with `site_full` on both paid tiers
(`config/plans.yml`), so there is no upsell ladder between the estates — the Terminal is
the **live** desk (minute tape, surface replay, alerts, 12 tabs) and this workspace is the
**settled record** (history, calibration, briefs, breadth). The workspace's existing
handoff panels state this; W1.6-A fixes the handoff itself — the Ticker CTA builds
`?symbol=` against the bare origin, but the Terminal reads `sym` (its readers:
`EmbeddedTerminalBridge.tsx:42`, `api/intraday/route.ts:60`); route it through the house
helper `MDXTerminal.url()` (`templates/theme.js:255-273`) like `gex.js` already does.

**Redirect mechanics = existing house pattern** (`templates/vector_allocation.html.j2`,
#4037, Crypto Cockpit precedent): `_seo_head` + `noindex,follow` + meta-refresh 0 + styled
fallback link + `location.replace`. Old URLs never 404; bookmarks land on the right mode;
gating is unchanged by construction (whole family already shares the identical
regwall + Insider-default gate — census §5).

**Accepted deltas** (named, deliberate — record here so no future session "heals" them):
1. gex.html's 701-name sortable board does not get a second home. Scanner covers the 403
   screened names; all 701 remain reachable through Ticker search (same manifest). The
   long tail beyond the screener universe was mostly-null board rows.
2. flow_desk's hero tape-intensity gauge is not ported. The persistent posture console
   ("Today's tape — Heavy · $24.6B traded") already carries that reading on every mode;
   a second intensity meter would violate the one-as-of/no-duplicate-chrome discipline.
3. gex.html's Market Weather card is not ported. The posture console's "Whole market" cell
   (with the ✓ track-record glyph) is its compressed form; the full instrument already
   lives on `market_structure.html` ("Vol weather" panel — same engine read).
4. flow_leaders' ticker links pointed at `us_stocks.html#T`; workspace Leaders rows
   deep-link to Ticker mode instead (strictly better inside an options workspace).

---

## §2 W1.6-A — CAPABILITY (PR 1). The workspace absorbs; legacy pages untouched.

Files: `templates/options.html.j2`, `scripts/build_options_command.py` (context additions
only), `scripts/build_flow_leaders.py` (`_BOARD_CAP`), tests. **No nav change, no stub,
no banner change in this PR** — ship A, prove it, then flip.

### 2.0 Builder must not decide (inherits WORKSPACE_DESIGN_SPEC §0 wholesale, plus)

1. Tab order is pinned: `brief · flow · scanner · ticker · leaders`. Hash `#flow`.
   Tab label EN **Flow** / ZH **资金流**. Tab `.cnt` figure: the covered-sector count.
2. Flow mode carries **zero stance chips** (verdict law: Ticker's name-header keeps the
   page's only `data-verdict-surface`). Panels end in caveat sentences, not chips.
3. All new JS lives **inside the existing single IIFE** (`tests/test_build_options_command.py::_extract_workspace_script`
   contract). No new `<script>` tags, no external mode files.
4. All new fetches are lazy on first mode activation via the existing `getJSON` helper;
   the chrome stays fetch-free. No new embeds — the manifest-weight regression class
   (`options.html.j2:883-895`) is a standing veto on inlining row data.
5. Raw-shelf charts draw lazily on first `<details>` open, reusing the already-fetched
   `gex/<T>.json` — zero additional network for the shelf.
6. New classes are `.oew-fl-*` (Flow mode) and `.oew-raw-*` (shelf). Do not touch
   `.oew-seg`/`.oew-lseg` (collision case law, spec §3).
7. Spacing/type/color tokens: only the §2 scales of WORKSPACE_DESIGN_SPEC. The ported
   canvas charts recolor through CSS vars (`--up/--down/--line/--muted`) — no hardcoded
   hexes, and the tide curves are direction-encoding so the zh flip must keep working.
8. Reduced motion: no new animation anywhere (canvas draws once, static).
9. Every new string lands as an EN/ZH pair from §5's tables — no builder-authored copy.

### 2.1 Flow mode (`#mode-flow`, lazy)

Section (empty shell like Scanner/Leaders) + `MODES` gains `'flow'` second; `SKEL` gains
its loading copy; `loadMode()` gains the branch.

Data: `fetch('flow_desk.json')` + `fetch('flowdata/cohorts.json')` (session-cached, both
exist today — flow_desk.json is the same store the Brief bake reads; cohorts.json is
written by `build_flow_desk.py`). The tide panel's intraday overlay reuses flow_desk.html's
existing `DATA_BASE`/`r2Url('live_flow/tide_current.json')` pattern — factual, already
shipped on the page being retired; honest empty state when absent/closed.

Panel order (each `.oew-panel`, eyebrow question-framed):
1. **WHERE THE MONEY WENT — panel "Premium by sector, the full desk"**: every sector row
   (not Brief's condensed cut), shared-scale bars, value in its own right-aligned mono
   column, tone chip (`buying ~ / selling ~ / mixed`), ⚑ flag chip where the desk's
   z-deviation marks an unusual day (hover = the plain-word receipt). Footer sentence
   (no chip): copy §5.
2. **WHO MOVED TOGETHER — panel "Theme groups"**: the 4 cohort tiles (Mag 7, Memory,
   AI chips, AI software) — tile = name, net premium (mono, tinted), one-line read.
3. **THE PASSIVE TAPE — panel "Sector ETF money"**: the 11-ETF creation/redemption grid,
   5D/21D columns in mono, `~` estimate mark preserved. Footer keeps flow_desk's honesty
   sentence (share-count estimates, background check).
4. **THE DAY'S ARC — panel "The tide"**: 30-session cumulative-tide sparkline + today's
   minute-by-minute unfolded curve (both canvas ports from `flow_desk.html.j2`'s inline
   script, recolored via tokens). When the intraday archive is absent: the flat labeled
   track + "no intraday record for this session" idiom.

### 2.2 Ticker mode folds

- **Raw-structure shelf**: inside the existing "Under the hood — the raw options
  structure" `<details>`, port from `site/gex.js`: dealer-gamma-by-strike bars,
  net-gamma profile, strike×expiry surface heatmap, vol smile, IV term structure, expiry
  ladder table, positioning-greeks row. Hand-SVG, drawn on first open, `.oew-raw-*`
  prefixed, each sub-chart with its own honest empty slot when the payload lacks the
  block. The shelf summary line gains the pinned subtitle (§5).
- **Primer**: gex.html's "New to options? Read this first" `<details>` ports beneath the
  raw shelf, collapsed, copy verbatim (it is already bilingual + compliant).
- **Terminal CTA fix**: build the href via `window.MDXTerminal && MDXTerminal.url(tk)`
  (theme.js is already the last body script), falling back to the current literal only if
  the helper is absent. Same fix for Brief's handoff CTA (bare origin →
  `MDXTerminal.url('')`-shaped `/terminal?from=macro&ret=` link). Copy unchanged except
  the one new positioning sentence (§5).

### 2.3 Scanner folds

- Remove `.slice(0, 200)`; subtitle becomes the "All N screened names" form (§5) — the
  conditional-cap wording and its two tests retire.
- **"More filters" disclosure** (collapsed by default, `.oew-sc-more`): text filter
  (ticker/sector), sector dropdown, and the 12 numeric ranges ported from
  `options_screener.html.j2:222-397`, operating on the already-fetched rows. Preset chips
  and filters compose (preset first, then ranges).
- **Per-column sort** on the table headers (port the screener's comparator, `aria-sort`).
- **CSV export** button in the panel header right (port `:1001-1006` Blob pattern,
  filename `options_scanner_<date>.csv`).
- **7th preset** "Put-heavy OI / 认沽持仓偏重" with the screener's exact predicate.

### 2.4 Leaders folds

- `scripts/build_flow_leaders.py`: `_BOARD_CAP = 25` → emit **all** qualifying rows
  (`board_a_total`/`board_b_total` already in the payload; verify JSON stays < ~250KB —
  it will, rows are small dicts).
- Mode renders top-12 as today, then a **"Show all N / 显示全部 N 项"** expander per board
  (plain button, no fetch — rows already client-side). Ladders, caution tags, ETF strip
  unchanged (already ported by OEU/W1).

### 2.5 Test deltas (A)

Update in the same PR: `test_all_four_mode_containers_render` (== 5, rename),
`tests/test_build_options_command.py::MODES` tuple, `test_scanner_declares_its_cap_*` /
`test_scanner_subtitle_only_claims_*` (→ "All N" form), `test_leaders_declares_both_board_caps_*`
(expander form), `test_leaders_denominator_equals_the_row_count_flow_leaders_html_renders`
(repoint denominator to payload totals). New tests: flow-mode container + lazy fetch +
zero-stance-chip sweep; raw-shelf lazy-draw + empty slots; CSV button; sort; range-filter
compose; `_BOARD_CAP` removal emits totals-consistent arrays; Terminal href uses
`MDXTerminal.url`. Banned-vocab + bilingual-parity sweeps re-run over the new surface
(§0.5/§0.6 of OIP apply verbatim).

## §3 W1.6-B — THE FLIP (PR 2, lands only after A is live-verified)

- **Stubs**: replace the four templates' bodies with the `vector_allocation` pattern.
  gex stub maps `location.hash` → a symbol becomes `options.html?t=<SYM>#ticker`, empty
  or non-symbol → `options.html#ticker`. Screener → `#scanner`; flow_desk → `#flow`;
  flow_leaders → `#leaders`. Each stub keeps `_seo_head`, `noindex,follow`, bilingual
  fallback copy (§5), zero shared-asset loads. Builders keep every JSON output;
  their HTML step now renders the stub (delete the dead render context where trivial,
  keep where not — builder's call, outputs are law: JSON unchanged, HTML = stub).
- **`site/gex.js`**: no longer loaded by anything → delete file + its direct test
  (`test_gex_js_iv_rank_color.py` repoints to the workspace's copied `IVRANK` map).
  `build_gex_board.py` keeps writing `site/gex/*.json` + `index.json` (workspace inputs).
- **Banner partial retires**: delete `_options_workspace_banner.html.j2` + its includes
  (now inside stubs anyway) + `test_absorbed_pages_*` banner tests.
- **Nav** (`templates/_navlinks.html.j2` + `templates/nav_market.js` mirror):
  - Group label: **Options & Market Structure / 期权与市场结构**, desc
    "Workspace · dark pool · index regime / 工作台 · 暗池 · 指数结构".
  - Three rows only: the workspace (desc updates to the five modes, §5), Dark Pool Desk
    (row + desc verbatim from today), Market Structure (verbatim).
  - `intraday_flow.html` row moves to the US group, directly after Daily Movers, with the
    plain-word desc from §5 (the old RVOL/VWAP/K-7 jargon desc retires; the page itself
    is untouched).
  - `gex.html` row deleted (workspace absorbs the "Options Desk" identity).
- **Tests**: rewrite `tests/test_oip_w1_nav_regroup.py` to pin the 3-entry flyout +
  intraday relocation + submenu-icon count; `tests/test_flow_leaders_render_markers.py`
  retires with the template (replace with a stub-shape test: refresh target + fallback
  link + noindex, parametrized over all four stubs); exclude the four stub pages from
  `test_builder_shim_writes` parametrization (stubs are self-contained, no data-base
  shim); `check_template_site_sync` — stubs are `.j2`, not plain-copy pairs, so no pairing
  duty (verify with `python -m scripts.check_template_site_sync`).
- **Express-lane coverage** (§0.14): confirm `render.yml region_of()` still maps each
  stubbed template to a live scope so the stub HTML actually bakes on merge (they map to
  their builders' existing scopes today — verify, don't assume).
- **Docs**: `docs/site_semantics/` untouched (no stat semantics changed); this file +
  masterplan Amendment 4 are the record. `docs/ACTIVE_BUILD_MAP.md` regenerates itself.

## §4 The estate after W1.6 (the user's view)

```
Nav · United States
├── … Daily Movers
├── Intraday Flow Tracker        (live session board — clearly not an options page)
├── Options & Market Structure ▸
│   ├── Options — the workspace  options.html   Brief · Flow · Scanner · Ticker · Leaders
│   ├── Dark Pool Desk           darkpool.html  (off-exchange record)
│   └── Market Structure         market_structure.html (index regime & vol)
```
One options door. Two honestly-different neighbors. The Terminal is the live desk the
workspace hands off to, per-name, with a working `sym` param. Legacy URLs glide in.

## §5 Pinned copy (EN / ZH)

| Slot | EN | ZH |
|---|---|---|
| Tab | Flow | 资金流 |
| Flow skeleton | Loading the flow desk for this close… | 正在加载本次收盘的资金流台… |
| Flow p1 title | Premium by sector — the full desk | 按板块的权利金 — 完整视图 |
| Flow p1 subtitle | every covered sector, shared scale, unusual days flagged | 覆盖的全部板块，同一比例，异常日标旗 |
| Flow p1 footer | A record of where options money went today — not a forecast of where it goes next. | 这是今日期权资金去向的记录，而非对后续走向的预测。 |
| Flow p2 title | Theme groups | 主题组合 |
| Flow p2 subtitle | how the big themes traded as groups | 大主题作为整体的交易情况 |
| Flow p3 title | Sector ETF money | 板块ETF资金 |
| Flow p3 footer | Estimates from share-count changes, not reported fund flows — a background check, not a signal. | 根据份额变动推算的估算值，而非公布的基金流量 — 可作背景参考，不构成信号。 |
| Flow p4 title | The tide | 资金潮汐 |
| Flow p4 subtitle | thirty sessions of net premium, and how today unfolded | 三十个交易日的净权利金，以及今日的展开过程 |
| Flow p4 empty (intraday) | No intraday record for this session. | 本场次暂无盘中记录。 |
| Scanner subtitle (uncapped) | All **N** screened names — sort any column, filter below. | 全部 **N** 个筛选标的 — 可按列排序、下方筛选。 |
| Scanner filters summary | More filters — ranges, sector, text | 更多筛选 — 数值区间、板块、文本 |
| Preset 7 | Put-heavy OI | 认沽持仓偏重 |
| CSV button | Export CSV | 导出CSV |
| Leaders expander | Show all N · fold back | 显示全部 N 项 · 收起 |
| Raw-shelf subtitle | charts and the full strike record — for readers who want the plumbing | 图表与完整行权价记录 — 供想看底层结构的读者 |
| Positioning sentence (handoffs) | Same subscription, two clocks — the Terminal is the live desk (tape, replay, alerts); this workspace is the settled record. | 同一订阅，两种时钟 — 交易终端是盘中实时台（逐笔、回放、警报）；本工作台是收盘后的定格记录。 |
| Stub h1 (pattern) | This desk moved into the Options workspace | 本面板已并入期权工作台 |
| Stub body | It now lives as the {mode} view of one consolidated page. You are being taken there. | 它现在是统一页面中的「{mode}」视图。正在为你跳转。 |
| Stub link | Open the workspace → | 打开期权工作台 → |
| Nav: workspace desc | Daily Brief · Flow · Scanner · Ticker · Leaders | 每日简报 · 资金流 · 筛选 · 个股 · 领头股 |
| Nav: intraday desc | Live session board — volume, tape and stance lanes · ≈15-min delayed | 盘中实时看板 — 量能、盘面与操作分级 · 约延迟15分钟 |

## §6 Gates

OIP §0 applies verbatim to both PRs (crops committed under `mockups/refs/oip/w16a/` and
`w16b/`; 5-second transcripts; banned-vocab sweep run over rendered output; bilingual
parity counts; no child self-merge — the commissioning session reviews and merges).
Specific to W1.6: the verdict-surface grep stays at exactly 1; the single-IIFE extraction
test passes; `site/options.html` weight is REPORTED, not silently grown (the original
"45KB gzip" gate here was written against a stale 33KB baseline — the branch base already
gzipped to ~46KB; W1.6-A measured ~66–77KB gzip depending on the session's data volume,
accepted at adjudication because every fold is lazy client code, no embeds grew, and the
estate retires four pages weighing 103–420KB each; a post-render JS externalizer mirroring
`externalize_css` is chipped as the follow-up that would recover most of it); every legacy
URL responds 200 with a working refresh target in the live verify; and the gex `#SYM` hash
mapping is click-verified against production after B merges.
