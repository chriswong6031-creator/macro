# XPV2-SC-R3B — Accessible-alternative contract (Deliverable 6)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md`
§21 deliverable 6, and its mandatory-equivalent clauses at §9 (Map),
§11 (Money), §17 ("Chart accessibility" — accessible name, textual
takeaway, data/list/table equivalent for every customer-relevant chart).
Written for Sol's four fresh independent critics and a future R3C session.
Cold-stranger rule: every claim cites its source file/line. Sources: the
six `build/views/*.html` partials (read/grepped directly),
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/DESIGN_SYSTEM_SPEC.md`
§12, `build/QA_ATTACK_REPORT.md` §4/§5, and
`research/reference_integrity/mastermind-xpv2-sector-r3b/capability_crosscheck.md`
rows #36-42, #45, #48-53.

---

## 1. The three mandatory chart equivalents

Commission §9: "Add a table/list projection of the same
`window.SECTOR_CYCLES` fields used by the sector-cycle chart. No new
rank/state calculation." Commission §11: "The market-heat treemap gets a
table/text equivalent driven from the same `marketdata/sp500_heatmap.json`
fields. No alternate scoring." Commission §17: every customer-relevant
chart needs an accessible name, a concise textual takeaway, and a
data/list/table equivalent. The reference implements exactly three chart
mounts that qualify, each satisfied by one embedded, same-source equivalent
(spec §12: *"a table/list equivalent driven from the *same producer
fields* — no alternate scoring, no new rank"*).

### 1.1 Rotation-map ranked list (Map view, `svg#rvx-rmap` → `table#rvx-board`)

- **Fields consumed** — same fixture fields the chart plots, no
  recomputation: Rank, Group name, Where it sits (quadrant), strength
  score, 20-day move vs S&P, 5-day rank move, and the `reco` "Noted" tag.
  Table caption states this explicitly: *"Text equivalent of the rotation
  map — every group, where it sits, its strength score, its 20-day move
  against the S&P and its rank move this week"* / 轮动图的文字等价表...
  (`map.html:73`). Column headers, verbatim: Rank/排名, Group/板块 (implied,
  not independently re-grepped by this session — **verify at freeze**),
  Where it sits/所处位置, Strength/强度 (implied from cross-check row #37;
  not independently re-grepped), 20d vs S&P/20日相对标普, Rank move
  5d/5日排名变化, Noted/备注 (`map.html:75-81`).
- **Where it lives** — `table.r3-tbl.r3-rmap-tbl#rvx-board`, inside its own
  `overflow-x:auto` panel, immediately after the chart figure in the
  desktop grid and (per `responsive_contract.md` §2) reordered ahead of the
  chart on phone. Default 10 rows (adjudications §5: "approved — observed
  production behavior outranks a composition guideline," i.e. production's
  own `slice(0,10)` over the design spec's suggested ≤8), with a "Show all
  N" reveal control that expands to the full set (cross-check row #37:
  probed 10→38 rows on the Themes tab, 10→11 on Sectors).
- **How it stays in sync** — one shared render function binds both the SVG
  and the table from the same in-memory array (`map.html`'s Themes/Sectors
  tab re-bind, cross-check row #37: "the Sectors tab re-binds the same pair
  (SVG children 41 to 14, table 'Show all 11' to 38 rows), so table and
  chart read one array"). There is no second fetch, no second sort, and no
  independent state for the table.
- **The `reco` "Noted" tag stays tertiary here too** — `.r3-tag`, last
  column, no hue (spec §6), with its own footnote directly under the
  table: *"Noted tags come from the rotation board and carry no graded
  call — only the Overview lanes do"* / 「备注」标签来自轮动看板，不构成分级判断 —
  仅总览清单具此权重。(`map.html:97-98`).

### 1.2 Sector cycle clock (Map view, `svg#r3-cyc-svg` → `table.r3-cyc-tbl`)

- **Fields consumed** — same `window.SECTOR_CYCLES` fields the chart draws,
  no new calculation (commission §9's exact requirement). Table columns,
  verbatim (`map.html:164-169`): Sector/板块, Where in its cycle/周期所处阶段,
  Position (num)/位置, Last confirmed turn (num)/最近确认拐点, Next window/
  下一窗口.
- **Where it lives** — `table.r3-tbl.r3-cyc-tbl` inside `.r3-panel.r3-tblbox`,
  directly beside the chart figure in the same `.r3-cyc` grid
  (`map.html:145-177`); on phone the figure collapses behind a disclosure
  while the table stays visible (`responsive_contract.md` §2, Map row).
- **How it stays in sync** — both are painted from one `window.SECTOR_CYCLES`
  read (`map.html:688`, "embedded verbatim"); the table caption states the
  binding directly: *"Text equivalent of the sector cycle clock — each
  sector's phase, cycle position, last confirmed turn and next projected
  turn window, from the same fields the chart draws"* / 行业周期时钟的文字等价表
  — 各板块的阶段、周期位置、最近确认拐点与下一次预计拐点窗口，字段与图表一致。(`map.html:163`).
- **Projection-register closing line** — the mandatory "windows, not
  certainties" disclosure (house law: no falsifier/refutation vocabulary,
  `CLAUDE.md` §Design; the sanctioned register instead): *"Projections here
  are windows, not certainties — re-drawn nightly as new data lands."* /
  这里的预测是时间窗口，而非确定性结论——每晚随新数据重新计算。(`map.html:173-176`,
  `id="r3-cyc-note"`). This is the same register the R3 design spec cites
  elsewhere as "the sanctioned 'read being updated' register (#3821)"
  (spec §5.1) applied to a projection-window rather than a null-read
  context.

### 1.3 Market-heat treemap (Money view, `div#heatmap-scorecard[role=img]` → table)

- **Fields consumed** — same `marketdata/sp500_heatmap.json` fields the
  treemap tiles are sized/shaded from, "no alternate scoring" (commission
  §11). Table columns, verbatim (`money.html:857-863`): Sector/板块, Share
  of map (num)/图面占比, Move today (num)/当日涨跌, Up / down (num)/上涨 / 下跌,
  Names (num)/只数, Largest name/最大成分.
- **Where it lives** — inside a `<details class="r3-disc mny-alt"
  id="hm-alt">` disclosure directly under the treemap mount and its
  takeaway/scale lines (`money.html:518-520` opening tag, table body id
  `hm-alt-tbl`, count line `hm-alt-count` at `money.html:876-878`).
- **How it stays in sync** — the code comment states the invariant
  directly: *"Same producer fields, same layout order. `squarify()` sorts
  descending by value, so listing the sectors by that same value IS the
  order the map draws them in — no new rank is minted, and no alternate
  score exists anywhere in this table"* (`money.html:849-852`). Both read
  from one `HM` object (`hierarchy(HM)`, `secLabels(HM)`) populated by the
  single `marketdata/sp500_heatmap.json` fetch (`money.html:1074`).
- **The treemap's own accessible name and takeaway** (chart accessibility,
  §2 below) sit above this table on the same mount, not duplicated inside
  it.

## 2. Chart accessibility — accessible names and textual takeaways

Commission §17: every customer-relevant chart needs an accessible name, a
concise textual takeaway, and the table/list equivalent (§1 above). Three
charts qualify; a fourth mount (Money's `heatmap-scorecard`) uses
`role="img"` rather than an SVG `role="img"`/`aria-labelledby` pair because
it is a DOM treemap, not a single `<svg>` — same accessibility contract,
different host element.

| Chart | Accessible name (resolved) | Textual takeaway | Table/list equivalent | Citation |
|---|---|---|---|---|
| `svg#rvx-rmap` (Map, rotation map) | "Rotation map — strength against the S&P..." (`r3-rmap-name`) | Section-level composed read (`#si-read-map`, cross-check row #41: *"14 groups sit top-right — strong and still rising. Big Pharma is furthest along."* / composed by verbatim `si_workspace.js` `readMap()`) plus the chart's own `r3-rmap-desc` `.r3-vh` span: *"The same groups are listed as a ranked table above this chart, with every value it plots"* / 图中各板块已在上方排名表中逐一列出，包含所绘制的全部数值。(`map.html:122`) | `table#rvx-board`, §1.1 above | `map.html:119-120,122`; QA report §4 |
| `svg#r3-cyc-svg` (Map, cycle clock) | "Sector cycle clock — every sector's 0 to 100 cycle position over the last seven years, one line per sector." / 行业周期时钟 — 各板块过去七年的 0 至 100 周期位置，每个板块一条曲线。(`r3-cyc-name`) | *"The table beneath this chart lists every sector's current position, its phase, its last confirmed turn and its next projected turn window."* / 图表下方的表格列出每个板块的当前位置、所处阶段、最近一次确认拐点与下一次预计拐点窗口。(`r3-cyc-desc`) | `table.r3-cyc-tbl`, §1.2 above | `map.html:153-156` |
| `svg#r3-wm-svg` (Moving, whole-market rotation map) | "Whole-market rotation map — relative strength..." (per cross-check row #45) | Coverage line stated on-surface (cross-check row #45): *"65 leading · 91 improving · 58 weakening · 55 lagging, across 269 subsectors and the Mag-7 composite"* / 领先 65 · 改善 91 · 走弱 58 · 落后 55，覆盖 269 个子行业与七巨头组合。(sums exactly: 65+91+58+55=269) | Named list — `drawStrip()` equivalent (Emerging/新兴, Fading/消退 groups with per-group links) **and**, per the cross-check's own historical finding F-5, a `drawTrackRecord()` equivalent that was reported missing at cross-check time. **This session found `trackRecordHtml()`, the verdict ladder (`TR_V`, `moving.html:600-601`), and a "Track record / 跟踪记录" heading live in the current `moving.html` (lines 585, 601, 624)** — grep-confirmed present, not independently re-probed live (see `design_notes.md` §5) | `moving.html:585,593,600-645`; cross-check row #45 |
| `div#heatmap-scorecard[role=img]` (Money, market-heat treemap) | *"Market heat map: every S&P 500 name as a rectangle sized by market value and shaded by its one-day move. The same figures are listed as a table below."* / 市场热力图：标普500每只个股为一个矩形，面积按市值、底色按当日涨跌。相同数据在下方以表格列出。(`hm-a11y-name`, `money.html:514`) | `hm-takeaway`: *"**N** of M names rose today, **N** fell. Rectangle size is market value; shade is the one-day move."* / 今日 M 只中有 **N** 只上涨，**N** 只下跌... (`money.html:840-842`), plus a named colour-scale legend so "a figure channel may never be unlabelled" (doctrine Law 3 cited inline, `money.html:844-847`) | `<details id="hm-alt">` table, §1.3 above | `money.html:510-516,840-878` |

**Two-line accessible-name pattern.** All three SVG charts use the same
mechanism: `role="img"` on the `<svg>`, `aria-labelledby="<name-id>
<desc-id>"` pointing at two adjacent `.r3-vh` (visually-hidden) spans — one
for the short accessible name, one for the longer descriptive takeaway —
each carrying its own `.l-en`/`.l-zh` pair (spec §9 component vocabulary:
`.r3-vh` is "the bilingual home for an accessible name. Never `title=`
(CI-guarded), never a single-language `aria-label`"). This is a single
reusable pattern applied identically at all three SVG chart sites
(`map.html:119-120,122,153-156`; the Moving whole-market map per
cross-check row #45's citation of `aria-labelledby="r3-wm-name
r3-wm-desc"`).

## 3. ARIA inventory

### 3.1 Tablist patterns

Three `role=tablist` widgets exist in the artifact (QA report §4): Overview's
five action lanes, and Confluence's two tablists (four universe tabs, five
timing-state tabs). All three use real `role=tab`/`role=tabpanel`/
`aria-selected` semantics — QA report §4: *"Not faked... panels carry
`aria-labelledby` pointing at the selected tab."*

**Roving tabindex.** Grep-confirmed present on Confluence's two tablists:
`tabindex="' + (on ? '0' : '-1') + '"` on both the universe-tab and
timing-state-tab render functions (`confluence.html:546,558`), with an
inline comment citing the defect it repairs: *"QA2-12: roving tabindex"*
(`confluence.html:544`). Overview's own tablist carries the equivalent
comment at `overview.html:535,1044` ("QA2-12: Home/End join Left/Right —
the full APG tabs keyboard contract"). **This grep confirms the code
exists; it does not confirm live-measured correctness** — QA report §4's
own QA2-12 finding ("all 14 `role=tab` elements... carry `tabindex ===
null`") predates these comments and was not independently re-run by this
drafting session (`design_notes.md` §5).

**Arrow-key / Home / End behavior.** Confluence's keyboard handler,
grep-confirmed at `confluence.html:1080-1109`, listens for exactly
`['ArrowRight','ArrowLeft','Home','End']` and computes the next tab index
as `e.key==='Home' ? 0 : e.key==='End' ? tabs.length-1 : (i +
(e.key==='ArrowRight'?1:tabs.length-1)) % tabs.length` — a full wraparound
roving-tabindex implementation, present identically at both Confluence
tablist sites (`confluence.html:1080-1084` and `:1105-1109`). This directly
addresses two QA report findings by ID:
- **QA2-08** (Universe tablist: no arrow-key navigation at all, and
  `aria-controls="sc-app"` resolved to a non-tabpanel element) — the
  `aria-controls` half is separately grep-confirmed repaired:
  `confluence.html:542-544`'s comment states the tabs now point at the real
  `role=tabpanel` (`cf-panel`) rather than `sc-app`.
- **QA2-09** (Timing-states tablist: arrow-key selection worked but ejected
  focus to the shell root) — `confluence.html:1092,1101` carry an inline
  comment describing the fix: focus is moved to the *new* button before the
  re-render destroys the old one, rather than after.

Neither QA2-08 nor QA2-09's fix was independently re-run against the live
artifact by this session (`design_notes.md` §5) — treat as grep-confirmed
present, not measurement-confirmed correct.

### 3.2 Chart accessible names and textual takeaways

Covered fully in §2 above — the two-line `role=img` +
`aria-labelledby="<name> <desc>"` + `.r3-vh` bilingual pair pattern, applied
identically at all customer-relevant charts.

### 3.3 Decorative-arrow `aria-hidden` rule

The Moving view's source→destination connector glyph
(`.r3-arrow`) was previously promoted to `role="img"
aria-label="moved to"` — QA report QA2-11: "a decorative connector glyph is
promoted to `role='img'` with a two-word verb fragment as its accessible
name, so a nonvisual reader... hears 'moved to' nine times with no subject
and no object." **Grep-confirmed current state**: `moving.html:308` now
emits `<span class="r3-arrow" aria-hidden="true"></span>` — no `role`, no
`aria-label` at all. Inline comment at `moving.html:304-307` states the
rule directly: *"this CSS-drawn connector glyph is decorative — the
flanking names carry the meaning [so it should] skip it rather than
announce the content-free fragment 'moved to' nine times."* The general
rule this establishes for the artifact: **a CSS-drawn connector/arrow mark
that exists only to visually link two named things is `aria-hidden="true"`,
never a `role="img"` with its own (necessarily incomplete) label** — the
adjacent name spans already carry the semantic content. The Map/Moving
source→destination CSS-drawn marks referenced in adjudications §4 ("CSS-
drawn marks replacing production Unicode `▾ ▴ ↗ →`") follow the same
convention (spec's own note, `moving.html:98`: "The source→destination mark
is the shell's CSS-drawn `.r3-arrow`: no Unicode").

### 3.4 Language-aware `aria-label` mechanism

Four reference-authored `aria-label` pairs exist (full EN/ZH strings in
`copy_ledger.md` §3): Overview's "Action lanes"/"操作分组"
(`overview.html:261,530`), Map's "Show themes or sectors on the rotation
map"/"切换轮动图的主题或板块" (`map.html:871,876`), and Confluence's
"Universe"/"范围" and "Timing states"/"时机状态" (`confluence.html:330,334,
1034-1035`).

**Mechanism**: unlike the visible `.l-en`/`.l-zh` dual-emit pattern (which
renders both spans and hides one via CSS, spec §11), an `aria-label` is a
single string attribute — it cannot dual-emit. Each site instead
**writes the attribute at render/boot time from a language check**, grep-
confirmed at every site:
- `overview.html:530`: `el('ov-ledge').setAttribute('aria-label', isZh ?
  '操作分组' : 'Action lanes');`
- `map.html:876`: `... ? '切换轮动图的主题或板块' : 'Show themes or sectors on the
  rotation map');`
- `confluence.html:1034-1035`: `el('cf-uni').setAttribute('aria-label',
  isZh() ? '范围' : 'Universe'); el('cf-ledge').setAttribute('aria-label',
  isZh() ? '时机状态' : 'Timing states');`

This is the fix-site pattern for QA2-10 ("Reference-authored accessible
labels are English-only in ZH" — QA report §3, 13 `aria-label` values with
zero CJK measured under `data-lang=zh`). The mechanism is a
**language-gated single-write**, not a dual-emit — it must be re-invoked on
every `langchange` event for a label to track a runtime language toggle;
this session did not independently confirm each site is wired to
`langchange` (as opposed to only running once at boot/render) — **verify at
freeze**.

## 4. What this document does not claim

Per `design_notes.md` §5's governing caveat, every "grep-confirmed present"
statement above is exactly that — a citation that a code change exists at
a named line, not a re-run of the QA harness or the capability cross-check.
Five items in this document specifically should be re-measured by a fresh
critic before being treated as closed:
1. QA2-08/QA2-09/QA2-12 (Confluence tablist keyboard/focus/roving-tabindex).
2. QA2-10 (four `aria-label` pairs — and specifically whether each is
   re-invoked on `langchange`, not only at boot).
3. QA2-11 (Moving arrow `aria-hidden` — confirmed by direct read of the
   current line, higher confidence than the others in this list, but still
   not harness-re-run).
4. F-5 (Moving `drawTrackRecord()` equivalent) — this session found the
   verdict-ladder code (`TR_V`, `trackRecordHtml()`) present and did not
   independently render/probe it live.
5. The exact column-header wording for `table#rvx-board`'s "Group" and
   "Strength" columns (§1.1) — sourced from `capability_crosscheck.md` row
   #37's prose rather than an independent re-grep of `map.html:76,78` in
   this session; a fresh session should confirm these two header strings
   directly against the file before citing them as verified.
