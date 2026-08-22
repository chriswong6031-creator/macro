# XPV2-SC-R3B — Capability cross-check (Deliverable 8)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md` §21 deliverable 8.
Review standard: `research/reference_integrity/mastermind-xpv2-sector-r3/capability_disposition_ledger.md` (92 rows).
Adjudication record consulted FIRST: `research/reference_integrity/mastermind-xpv2-sector-r3b/ORCHESTRATOR_ADJUDICATIONS.md`.

Artifact under test:
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
(5,431,707 bytes; served at `http://127.0.0.1:8991/` for live probing; view partials
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/views/*.html`,
runtime shim `build/runtime_shim.js`, shell `build/shell.html`).

Probe method: headless Chromium (playwright-core) against the served artifact; small
inline `page.evaluate` probes. Static rows verified by exact quote from the candidate
HTML or its source partial (byte-identical — the candidate is assembled verbatim from
the partials by `build/build_reference.py`).

Verdict vocabulary:
- **VERIFIED** — journey demonstrated present against the rendered candidate.
- **VERIFIED-AS-ADJUDICATED** — divergence from the R3A row exists and is recorded and
  approved in `ORCHESTRATOR_ADJUDICATIONS.md` (§ cited).
- **FINDING (MISSING / PARTIAL / DIVERGENT)** — divergence NOT recorded in the
  adjudication record. Detail + reproduction in §FINDINGS.

---

## Overview (#1-35)

Probe harness: served candidate at 127.0.0.1:8991, headless Chromium 1440x1000;
harness drawer `#ref-access` drives gated / hydrated / ungated.

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 1 | VERIFIED | `build/views/overview.html:434-456` LANES = 5 entries; `:463` stand_aside = `(AB.hold).concat(AB.avoid)`. Live: `#ov-panel .actbody` = 5 bodies (ab-buy-fold, ab-soon-fold, ab-run-fold, ab-trim-fold, dash-hold-fold); six producer keys present in the embedded `basketdata/action_board.json` with lengths 4/5/5/3/13/14. |
| 2 | VERIFIED | Live ledge text: `Buy now立即买入`, `Almost ready接近就绪`, `In favour — don't chase看好 — 勿追高`, `Take profits止盈`, `Stand aside观望`. Live `#ov-foot` subcopy `Entry confirmed today今日已确认入场`. Per-lane subcopy/empty strings at `overview.html:436-455`, each carrying its `_us_act_now_board.html.j2` line cite. |
| 3 | VERIFIED | Gated state: ledge counts 4 / 5 / 5 / 3 / 27 while each lane body holds only 3 rows. `laneCount()` (`overview.html:466-471`) reads the FULL list, never the slice. 27 = hold 13 + avoid 14. |
| 4 | VERIFIED | Ungated row dump: buy_now = 3 theme rows then 1 sector row; on_the_run = 4 theme then 1 sector; take_profits = 2 theme then 1 sector. Producer order; `laneRows()` returns `AB[key]` unmodified, no client re-sort exists. |
| 5 | VERIFIED (fixture-limited) | buy_soon rendered in producer order (Cons Staples, Materials, Communications, Financials, Industrials) = `action_board.json` order exactly. GAP carried: only one fixture row carries `days` (Consumer Staples days=5), so the ascending sort is producer-side and not re-exercisable from this fixture. |
| 6 | VERIFIED | Theme rows render score + perf_20d_rel: live `.r3-fig` = `76+27.2%` (Gold Miners), `71+20.3%`, and the negative arm `55-7.0%` (Crypto & Digital Assets). |
| 7 | VERIFIED | Sector rows render `.r3-fig` = empty and `.r3-why` = `clean entry · 3d ago入场干净 · 3天前` / `trigger ~5d触发约5日`. No blended score/perf pair on any `sector fund` row: `overview.html:478-493` gates `fig` on `isTheme`. |
| 8 | VERIFIED | Trace card reads `sectordata/sector_central.json` (`SCD`, `overview.html:376`). Live trace open on Gold Miners: `Conviction信心 75 Accumulate积极配置`, `Confluence共振 3/3`, `Cycle position周期位置 22` — a distinct artifact from `action_board.json`. |
| 9 | VERIFIED | Sector row href consumed verbatim and RECORDED on click: `REF.log` nav `basket/us_sector_discretionary.html`. Ledger-text note: the R3A row describes the producer's `US_SECTOR_PAGE` to `sectors/<TICKER>.html` construction, but the frozen fixture's own `action_board.json` emits `basket/us_sector_*.html`; the candidate is faithful to the producer BYTES, which is what row #11 mandates. |
| 10 | VERIFIED | Theme rows record `basket/gold_miners.html`, `basket/ai_agents.html`, `basket/big_pharma.html` etc. on click — byte-identical to `action_board.json` `href`. |
| 11 | FINDING (MISSING) | Bottoming-watch rows carry NO destination. Live: `#ov-watch` children = `DIV.r3-watch-cell` x3; `#ov-watch a` count = 0; `#ov-watch-foot a` count = 0. The fixture rows DO carry href (`basket/power_grid.html`, `basket/nuclear_power.html`, `basket/data_center_power.html`) and production renders `<a class="actitem" data-rpop href="{{ x.href }}">` at `templates/_us_bottoming_watch.html.j2:95`. Not recorded in ORCHESTRATOR_ADJUDICATIONS.md. See F-2. |
| 12 | VERIFIED | `abPlus()` (`overview.html:629-633`) emits `<a href="#actnow-section">`; live gated `#actnow .pg-more a` hrefs include `#actnow-section`, and `document.getElementById('actnow-section')` resolves (target is real, not a dangling anchor). The fixture carries `more` only for hold/avoid, so exactly one `+5 more — full list on Sector Intelligence` renders; `plusCount()` is lane-generic so the all-five-lane mechanism is present but only one lane is exercised by this fixture. |
| 13 | VERIFIED | `overview.html:256`: `<a class="r3-more" href="#confluence">Drill to stocks / 下钻到个股</a>`, in the `#actnow-section` foot — the same DOM home as production's `div.rvx-sec-sub.si-lane-foot` (`templates/sector_central.html.j2:2204-2205`). The trailing arrow glyph is dropped under adjudication §4 (CSS-drawn marks, wording verbatim). Observation only (not a ledger row): production's companion sentence `Lanes are the only gated, graded calls on this page…` is not reproduced anywhere on the candidate. |
| 14 | VERIFIED | Preview is read from the payload, never hardcoded: `overview.html:662-664` reads `PG.panels.actnow.preview`. Embedded `premiumdata/sector_central.json` gives `panels.actnow = {preview:3, locked:29, total:44}`; gated render shows exactly 3 rows per lane plus a locked disclosure. |
| 15 | VERIFIED (structural, not further demonstrable) | Server-side invariant (Python payload and Jinja shell computed from one source list). A single-file client reference has only one code path and so cannot disagree with itself; the candidate consumes the payload's own `preview` rather than a second literal, which is the faithful client-side analogue. No harness control can falsify this row. |
| 16 | VERIFIED | Embedded `premiumdata/sector_central.json` parses with `schema="tier_payload.v1"`, `page="sector_central"`, `panels.actnow={preview:3,locked:29,total:44}`, `actnow_html` = 110,466 bytes. Matches the ledger note preview=3 / locked=29 / total=44. |
| 17 | VERIFIED | `Object.keys(REF.registry)` filtered on `premium` returns exactly one path: `premiumdata/sector_central.json`. No `us_stocks.json` entry exists in the registry at all, so no shared-file overwrite is representable. |
| 18 | VERIFIED-AS-ADJUDICATED (§8) | URL-level `/premiumdata/` enforcement is a server property no quarantined artifact can execute. ORCHESTRATOR_ADJUDICATIONS.md §8 records the live-capture blocker, resolves the R3A open GAP (config grep, not live curl) in the direction of a site-wide anonymous regwall in FRONT of the tier gate, and keeps the receipt `production/prod-live-anon-overview.png`. |
| 19 | FINDING (PARTIAL) | Steps 3-6 demonstrated end-to-end; steps 1-2 are NOT. Live hydrate via `#ref-access`=hydrated: lane rows 3/3/3/3/3 to 4/5/5/3/27; `#actnow .pg-more` 5 to 0 (disclosure removal); `restoreFolds()` mints `Show more (1) / (2) / (2) / (24)` on the four over-threshold lanes; all 29 inserted `a.actitem` carry `data-ref-nav` (`#actnow a.actitem:not([data-ref-nav])` = 0); insert is by `data-ab-lane` (ab-buy-fold, ab-soon-fold, ab-run-fold, dash-hold-fold x2). BUT `whenAuthSettled` has no representation, and the payload is read SYNCHRONOUSLY from the registry (`overview.html:375` `PG = reg('premiumdata/sector_central.json')`), never through `REF.fetchJSON`: the recorder log for a full page load holds 9 entries and ZERO mention of `premiumdata/sector_central.json`. Consequence: the schema/page validation at `overview.html:692` is unreachable from any harness control, and the Simulate-fetch-fail toggle does not touch the hydrate path (probed: fail=on plus hydrated still hydrates 4/5/5/3/27 with 0 disclosures). See F-3. |
| 20 | VERIFIED | `#si-read-overview` live text: `Memory, HBM & Storage is handing leadership to Big Pharma. 4 names sit in the Buy lane.` / `内存、HBM 与存储正把领先交给大型药企。4 个标的在「立即买入」清单。`; attributes `data-from-en/zh` and `data-to-en/zh` are set from `theme_intel` hero fields (`overview.html:1004-1014`) and composed by the verbatim si_workspace.js `readOverview()`. The 4 equals `buy_now.length`. |
| 21 | VERIFIED | `overview.html:866` comment `signal and timing_state are NEVER read here`; live `#ov-watch` text contains neither `BUY` nor `COUNTERTREND BOUNCE`, although both fields are present on all three fixture rows. |
| 22 | VERIFIED | Title `Bottoming watch筑底观察`; subcopy `cycle lows forming — watch, don't chase周期底部形成中——观察，勿追`; per-row chip `position in cycle range 4/100周期区间位置 4/100`; gate-conflict chip `below 200-day trend — gate shut低于200日趋势——闸门关闭` on Nuclear & SMR only; dual-read chip `may be bottoming或正筑底`; null disclosure `This is what the cycle read says tonight, shown as-is. A forming low on its own has not been shown to predict what comes next — watch, don't chase.` Empty state probed by emptying `theme_intel.act_now.bottoming_watch`: renders `no basing candidates tonight今晚无筑底候选`. Constant-chip dedup to the strip foot as `All 3 rows: / 3 行均为：` is adjudicated §4. |
| 23 | VERIFIED | `section[data-view=overview]` child order = `#regime`, `#actnow-section`, `#ov-watch-band`, `#grader`; watch-band index 4 vs board index 3, and `#ov-ledge .r3-ledge-cell` count = 5 (the watch strip is not a ledge cell). |
| 24 | VERIFIED | Live `#ov-ctx-body`: `Losing the lead失去领先 Memory, HBM & Storage 内存、HBM 与存储 was #1原第一`, `Taking the lead接过领先 Big Pharma · Health Care`, `Money is rotating资金正在轮动`, `2 days in2 天`, `Aug: seasonally friendly for hot stocks (rose in 8/10) · context only` — sourced from `si_handoff.json` theme_context and factor_season (`overview.html:800-849`). |
| 25 | VERIFIED | Probe: deleted `basketdata/si_handoff.json` from `REF.registry` at DOMContentLoaded before the view reads it. `#ov-ctx-body` renders the verbatim fallback `Thematic baskets主题篮子 / Equal-weight US theme baskets measured against the S&P 500. Use them to see which themes are leading or fading.` |
| 26 | VERIFIED | `paintContext()` writes only `#ov-ctx-body` and `#ov-ctx-asof`; `HND` is never referenced by `laneRows()`, `laneCount()`, `fillLane()` or `REF.renderActNow()`. Probed structurally: with si_handoff.json deleted the five lanes render unchanged (counts 4/5/5/3/27 intact). Section subcopy states the invariant to the reader: `Display only — it does not set a lane below.仅供展示 — 不决定下方分组归属。` |
| 27 | VERIFIED | `overview.html:960` `(Date.now() - ms) > 12 * 3600e3`. Live on the frozen fixture (as_of 2026-08-19): `#ov-asof` class becomes `r3-asof r3-stale`, `#ov-staleline` hidden=false, text `This board's clock is more than 12 hours old.本看板的时间戳已超过 12 小时。` The A6 fail-open-on-malformed defect is carried unrepaired (bare `isFinite(ms)` guard), matching the ledger note. |
| 28 | VERIFIED | Probe: forced `buy_now[0].score=0, perf_20d_rel=0` and `buy_now[1].score=null, perf_20d_rel=null`. Row 1 `.r3-fig` = `0+0.0%`; row 2 `.r3-fig` = empty string. Zero renders, missing disappears. |
| 29 | VERIFIED | Probe: emptied `action_board.buy_now`. Ledge count becomes 0 and `#ab-buy-fold` renders `<p class="r3-lane-empty">None today — nothing has fully confirmed a fresh cycle low.今日无 — 尚无标的完全确认新的周期低点。</p>`. The guard is a genuine length test (`overview.html:642`), not a string check. |
| 30 | VERIFIED | Probe: forced `REF.simulateFetchFail=true` before boot. All 8 registry fetches log `simulated-fail`, `#actnow` collapses to the single failure string, and the two server-baked organs survive independently: `#ov-watch-band.hidden=false` and `#ov-ctx-body` still renders the leadership hero. |
| 31 | VERIFIED | Same probe: `#actnow` innerHTML = `<div class="r3-empty"><p class="r3-empty-line"><span class="l-en">Data failed to load — please refresh.</span><span class="l-zh">数据加载失败 — 请刷新。</span></p></div>` — one fixed string, cause-indistinguishable. |
| 32 | FINDING (PARTIAL) | The gated state IS the 401/403 shape and is correct: server-baked preview of 3 rows per lane plus `N more here — sign in to see the full lane / 此处还有 N 个 — 登录后查看完整分组`, and no separate access-denied banner anywhere (`#actnow` contains no `denied` and no `403` string). But because the premium payload never goes through fetch (see #19 / F-3), a 401/403/offline DURING hydration cannot be produced by any harness control; the collapse-to-no-op path is asserted in a comment (`overview.html:705-706`) and never executed. |
| 33 | VERIFIED | `overview.html:356-357` ABBR table verbatim. Live rows read `Cons Disc可选消费` and `Cons Staples必需消费`. Long unlisted names are not ellipsized (`Critical Minerals & Rare Earth…` wraps) — the names-never-ellipsize law of adjudication §3. |
| 34 | VERIFIED | `FOLD_CAP = 3` (`overview.html:457`). Live hydrated: the 4/5/5/27-row lanes each get a `Show more (n-3)` control reading `(1)`, `(2)`, `(2)`, `(24)`, and every one of those bodies carries `is-collapsed`; the 3-row take_profits lane gets NO control and `is-collapsed=false`. `restoreFolds()` (`:617`) is the DOM-side twin invoked on every access-state change. Mechanism note (not a finding): below threshold the control is REMOVED from the DOM rather than CSS-suppressed — same reader-visible outcome. |
| 35 | VERIFIED | `#grader` DOM home is Overview (child index 5 of `section[data-view=overview]`). Live: `21d · n=187 19% hit命中 rank-IC秩相关 -0.1587 · excess超额 -0.5%`, `63d accruing累积中 (n=0)`, `126d accruing累积中 (n=0)`, plus the pre-freeze note `Basket grading accruing from 2026-07-02 (W3.8 freeze date)…`. The sub-line carries the verbatim `never fed back into the live score / 绝不回灌入实时评分` clause. |

## The Map view (#36-42)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 36 | VERIFIED | `#rvx-rmap` is an `svg` with 41 child nodes (39 plotted marks) inside `#rotmap-section`; section head reads `Where everything stands全景位置 / Right = strong vs the S&P. Up = gaining speed this week.右 = 相对标普强。上 = 本周加速。` No gated call is rendered on the surface (the RVX_Q stance halves stay unrendered — see #38/§5). |
| 37 | VERIFIED-AS-ADJUDICATED (§5) | `#rvx-board` is a real `TABLE.r3-tbl.r3-rmap-tbl` with a caption `Text equivalent of the rotation map…轮动图的文字等价表…` and columns `Rank排名 / Group板块 / Where it sits所处位置 / Strength强度 / 20d vs S&P20日相对 / Rank move 5d5日排名变化 / Noted备注`. Default 10 rows (adjudication §5 approves production's `slice(0,10)`), and the `Show all 38显示全部 38` control expands to 38 rows — probed: tbody rows 10 to 38. The Sectors tab re-binds the same pair (SVG children 41 to 14, table `Show all 11显示全部 11`), so table and chart read one array. |
| 38 | VERIFIED | `map.html:499-500` `RECO={enter:['Buy','买入'], accumulate:['Add','加仓'], hold:['Hold','持有'], trim:['Trim','减仓'], avoid:['Avoid','回避']}` — all five mapped, bilingual. Live `.r3-tag` values present in the first 10 rows: `Add加仓`, `Hold持有`, `Trim减仓`. Rendered as the tertiary `.r3-tag` device per adjudication §3 (A3 CONFLICT carried, not amplified). |
| 39 | VERIFIED (R3A GAP repaired) | `#sc-cyclemap` contains the chart `#sc-chart.r3-cyc-plot` PLUS one `<table>` accessible equivalent, introduced by this candidate; the chart caption states `The table beneath this chart lists every sector's current position, its phase, its last confirmed turn and its next projected turn window`, bilingual (`行业周期时钟 — 各板块过去七年的 0 至 100 周期位置，每个板块一条曲线。`). This is the accessible equivalent the R3A design brief required be added in R3. |
| 40 | FINDING (DIVERGENT) | The board itself is present and correct in structure: `#board` holds exactly 11 `<details>` — XLC/XLE/XLY/XLP/XLB/XLI/XLF/XLV/XLK/XLU/XLRE — with the conviction chain, and XLV reads `Reduce减配 23`, matching the R3A note. BUT the candidate renders the producer's `reasoning[]` chain inline, and does so with UNTRANSLATED raw producer strings. Probed under `data-lang=zh`: 114 leaf nodes with no ZH twin — `span.r3-chaintier` `validated` x33, `display` x13, `confirmer` x11; `span.r3-chainlay` `Cycle state` x11, `Trend gate` x11, `Regime gate` x11, `Momentum` x11, `Heat` x11, `Fragility` x2. See F-4. |
| 41 | VERIFIED | `#si-read-map` (`P.si-view-read`) live: `14 groups sit top-right — strong and still rising. Big Pharma is furthest along.` / `14 个板块位于右上 — 强势且仍在上行。大型药企走得最远。` — composed by the verbatim si_workspace.js `readMap()` off the same `theme_intel.themes` array the board reads. |
| 42 | VERIFIED | Map-view disclaimer rendered under the quadrant legend: `Leading/Improving/Weakening/Lagging describe where a group sits vs the market right now (strength × direction). Bottoming/Prime entry/Trending/Topping/Rolling over describe where it sits in its own multi-year cycle. Only the lanes above carry a gated, graded call…` — present, and the `.r3-tag` reco chips render beneath it exactly as the ledger's A3 note describes. Additional §5 check: the RVX_Q stance halves (`Hold / add`, `Take profits`) appear ONLY inside a `<script>` body, never in a rendered node (probe: 1 hit, tagName SCRIPT) — the de-amplification approved in adjudication §5 holds. |

## The Moving view (#43-47)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 43 | VERIFIED | `#si-read-moving` live: `23 groups moved up the ranking this week, 24 slipped.` / `本周 23 个板块排名上升，24 个下滑。` — a pure sign count. The receipt text `Context only — it ranks nothing…` is present in the same view. |
| 44 | VERIFIED (R3A GAP carried) | `#rc-events-mount` renders the rotation-events board: `Semicap equipment半导体设备 / Memory & storage存储芯片 / Technology科技 / Day 1第 1 天` plus the producer's own prose leg (`Semicap equipment sits 13% below its peak. Memory & storage is 21.7% up off its low…`), and `#si-movement` heads it `Where money moved资金的去向 / Out of one leg, turning up in another自一处撤出，在另一处转强 / 2 active活跃`. Table count inside the mount = 0, which carries the R3A GAP verbatim (`no table alternative confirmed beyond the rendered board itself`) rather than resolving it. |
| 45 | FINDING (PARTIAL) | Whole-market map present and correct: `#rotation-app` holds 1 `svg` with `role="img"` and `aria-labelledby="r3-wm-name r3-wm-desc"`, coverage line `65 leading · 91 improving · 58 weakening · 55 lagging, across 269 subsectors and the Mag-7 composite.` / `领先 65 · 改善 91 · 走弱 58 · 落后 55，覆盖 269 个子行业与七巨头组合。` (65+91+58+55 = 269), and the `drawStrip()` analogue is a real text list (`.r3-strip` / `.r3-striplist` Emerging新兴 / Fading消退 with per-group links). BUT the `drawTrackRecord()` half of the named accessible pair is ABSENT: `grep -c "track_record|Track record|跟踪记录|Clears the bar" build/views/moving.html` = 0, and no track-record table, verdict chip or `n_days`/`n_snapshots` line renders anywhere in the Moving view — although the fixture's `marketdata/subsector_rotation.json` carries a full `track_record` block (`schema subsector_rotation.track_record.v1`, `n_snapshots 6716`, `n_days 25`, horizons 5/10/21). See F-5. GAP carried from R3A: Finviz snapshot cadence still unconfirmed. |
| 46 | VERIFIED-AS-ADJUDICATED (§5) | `#desk-watch-mount` renders both halves: turn desk (`Armed windows已武装窗口` with the quiet-tape sentence `No sectors armed right now — a quiet desk is a valid read.当前无板块处于入场窗口——安静的值守台也是有效读数。`) and tape-onset (`Earliest flow signs最早期资金迹象 · 2`, Energy/Health Care with `5d onset rate 75.4% / noise 24.6% / 10d confirmed —` and `measured 1998-12-22 → 2026-08-19 · 1004 flags`). The DISPLAY-ONLY docstring is surfaced verbatim to the reader: `Watch material, not calls — display only, and nothing here ranks, gates or sizes anything.仅供观察，并非操作判断——仅展示，此处不排名、不门控、不调仓。` The absent-vs-empty distinction is adjudication §5. |
| 47 | VERIFIED | Recorder log on a `#moving` load shows the five canonical artifacts fetched and HIT, in order: `marketdata/rotation_events.json`, `marketdata/sector_fragmentation.json`, `marketdata/subsector_rotation.json`, `basketdata/oracle_turn_desk.json`, `basketdata/oracle_tape_onset.json`. `basketdata/si_handoff.json` does NOT appear in the Moving fetch set — the A2 handoff-presupposition stays refuted by the artifact's own binding. |

## The Money view (#48-53)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 48 | VERIFIED | `#si-read-money` is a `P.si-view-read` carrying `data-regime="broad"` baked server-side; composed line `Money is spread across many groups — a broad tide, not a narrow few.` / `资金广泛分布于多个板块 — 全面上涨，而非少数领涨。` The attribute is the one in-scope field bound to `si_handoff.json` `flow.cluster.regime`, per A2. |
| 49 | VERIFIED-AS-ADJUDICATED (§6) | Verdict card renders the server regime headline plus the client chips: `Money flow资金流向 / Spread across many广泛分布`, `RISK-ON风险偏好` (from `basketdata/etf_pulse.json`, recorder: hit) and `Volatility: calm波动率：平静` (from `basketdata/vol_sentiment.json`, recorder: hit). Production's tinted verdict bars are replaced by achromatic measures with printed thresholds — adjudication §6. R3A GAP carried: chip renderers still not traced field-by-field. |
| 50 | VERIFIED | `#mkt-breadth` renders `Broad广泛` inside `#internals-section`, headed `Under the hood市场内部 — is the whole market participating?— 整个市场都在参与吗？` with the plain-word so-what `Breadth tells you whether the rotation is a broad tide or a narrow few. Be selective when it is narrow.广度告诉你这是全面上涨还是少数领涨。领涨面窄时应精挑细选。` Fed from `theme_intel.market_concentration`. R3A GAP carried: exact `engine.*` module still not isolated. |
| 51 | VERIFIED | `#sc-flows` renders the server fragment head `Where sector-ETF money is flowing板块 ETF 资金流向何处 / Multi-day creation/redemption flow across the 11 sector SPDRs — read the rotation, not the daily noise` with 3 tables in the Money view (13 / 12 / 5 rows). Omission probed: deleting the flows fragment from `REF.fragments` at DOMContentLoaded leaves `#sc-flows` MISSING entirely (no placeholder, no empty shell) and drops the Money view to 2 tables — the `flows_html is None` behavior reproduced exactly. |
| 52 | VERIFIED-AS-ADJUDICATED (§6) | `#heatmap-scorecard` renders the treemap with real constituents (`Technology信息技术 −0.64% NVDA −0.99% AAPL …`), and `generated_utc` is present in the view's script as the freshness key. The production polling loop is deliberately replaced by refetch-on-activation-only-after-failure plus sync registry reads (adjudication §6, matching production boot semantics); no `setInterval` exists in the artifact. The absolute-stamp comparison (not a baked delta) is preserved. |
| 53 | VERIFIED (with a disclosed sub-defect) | `#scc-leadership` renders `Index leadership rotation指数领导轮动 / which index family is pulling ahead / as of 2026-08-19截至 2026-08-19`, the `Rising star上升之星 Nasdaq-100纳斯达克100 LAS +1.06`, the four-universe LAS table (S&P 500 / Nasdaq-100 / Russell-2000 / Thematic Baskets with LAS, RS level, RS mom, Breadth thrust, Particip., Quadrant), and the self-graded sub-line `Validated前瞻战绩：已验证 345 calls logged over 11 days` — the Validated / Measuring / Accruing ladder is in code (`money.html` `['Validated','已验证'] : tr … ['Measuring','测量中'] : ['Accruing','积累中']`). Sub-defect folded into F-4: the three rising-star driver legs render UNTRANSLATED inside the ZH half (`领导加速最快——breadth thrust · broad participation · return acceleration`); the producer emits `rising_star.why[].leg` EN-only, and the lane's own §4 precedent was to author a ZH twin in exactly this situation. R3A GAP carried: writer cadence still not independently confirmed. |

## The Explore view (#54-62)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 54 | VERIFIED | Mode tabs `Raw原始 / vs S&P对标普 / σσ` (with `aria-pressed`), a labelled `<details>` category filter whose summary names the active state (`Category分类 All全部`) over 20+ chips, sortable column heads, and a chart range picker `3M 6M YTD 1Y All`. Persistence probed: after clicking a mode and a column head, `Object.keys(localStorage)` = `["fw-btbl-sort","fw-btbl-mode"]`. No server round-trip: `REF.log` length delta across those interactions = 0. Free-text search box confirmed absent (`input[type=search]` and `input[type=text]` both 0) — the R3A "confirmed absent, not a gap" note holds. Category filter placement in a `<details>` is adjudication §6. |
| 55 | VERIFIED | `#btable` heads: `Basket篮子 / 60d trend60日走势 / 1d / 5d / 20d / 60d / MTD / YTD` — name, sparkline column, and the six windows. Synthetic benchmark row reproduced with production's own mode condition (`templates/sector_central.html.j2:2686` `if(btblMode==='raw')`): probed by clicking `Raw原始`, the table gains row `S&P 500标普 500 1d +0.2% 5d −0.4% 20d +2.9% 60d +3.4% MTD +2.9% YTD +13.1%` (row count 17 to 18). Group-pulse column is the ledger's own "optional" leg and is not emitted by this fixture. |
| 56 | VERIFIED | Default sort is 20d descending (first rows `Non-AI Software +29.6%`, `Gold Miners +26.4%`, `Silver Miners +23.4%`; last rows `Semiconductor Equipment (WFE) −13.0%`, `AI Neoclouds & HPC Hosting −15.2%`), rendered as top-8 + bottom-8 = 16 data rows plus a reveal row `Show all显示全部 (49)`. Clicking it yields exactly 49 tbody rows. The table reads `basketdata/baskets.json` from the client fetch only; `window.SECTOR_CENTRAL` is not consulted. |
| 57 | VERIFIED-AS-ADJUDICATED (§6) | `#chart-section` renders the rebase-to-0% performance chart as inline SVG (adjudication §6 chose inline SVG over embedding `lightweight-charts.js`; production's own rebase transform is cited on the surface: `Lines are rebased to 0% at the start of the window.曲线在窗口起点重设为 0%。`). The R3A "no table-only fallback / aria summary found — design brief requires one" GAP is repaired by the legend doubling as the chart's text equivalent (adjudication §6): `曲线列表 — 每个篮子、其线型，以及所选窗口内的回报` plus the honest provenance line `35 of the 49 baskets are back-projected over their current roster, so the line before a member joined is context, never a track record.` |
| 58 | VERIFIED-AS-ADJUDICATED (§2) | `#tm-mount` is closed at rest with the honest label `Rotation Time Machine — replay 25 years of rotation轮动时光机 — 回放25年轮动史 / nothing loads until you open it打开后才会载入`. On open, the recorder shows the deferred-fetch contract exactly as adjudicated: `fetch oracledata/tm_manifest.json => hit` (fixture-real) then `fetch oracledata/tm_episodes.json => recorded-not-executed`. Unit/year/preset controls present (`Sectors板块 1998–2026`, `Subsectors + Themes子行业与主题`, `Factors因子 2013–2026`, year buttons 1998…), and the non-predictive claim is on the surface. |
| 59 | VERIFIED | `.ne-legs` renders the fixed 5-leg breakdown per cluster, bilingual and numeric: `Tightening收紧 100% / Co-movement共动 30% / Momentum动能 0% / Novelty新颖 100% / Size规模 …`, with the composite score printed beside it (e.g. `67.1 Forming fast快速成形`). No LLM path feeds the score. |
| 60 | VERIFIED-AS-ADJUDICATED (§6) | The A8 `Model analysis / 模型分析` branch is live code in the candidate (string present in the view scripts), but `ai_watch` is `null` in the frozen fixture so production's absence path renders — disclosed in adjudication §6 as the reason the labelled branch cannot be shown visually on this fixture. |
| 61 | VERIFIED | Standing caveats render verbatim: `Emerging clusters not yet in a basket. Use as a watchlist, not a buy list.尚未纳入篮子的成形集群。用于观察清单，并非买入清单。`, `Scanned 1476 names as of 2026-08-19. Scores rank narrative formation, not expected return.`, `Noisy signal; many clusters fade. Watchlist only, not a buy signal. Ticker order favors cleaner entries, not higher expected return.` plus the conditional caveat `60% of the group is already stretched.60% 的组合已经拉伸。` |
| 62 | VERIFIED (mechanism present, dead on this fixture) | Candidate lines 5307-5308: `function watchEn(s){ return (s==null?'':String(s)).replace(WATCH_LABEL,'Watching for: ').replace(WATCH_NOUN,'watch condition'); }` and `function watchZh(s){ return watchEn(s).replace(/Watching for:\s*/g,'关注条件：'); }` — the 2026-07-27 #3821 rewrite, with a ZH twin. GAP: the frozen `basketdata/narrative_emergence.json` carries no falsifier/kill field at all (`falsif`, `kill`, `watch_for`, `invalidat` all absent), so the rewrite never fires on this fixture and the rendered surface contains zero `Kill criterion` and zero `Watching for` strings. Front-facing falsifier language is therefore correctly absent (house law satisfied). |

## The Confluence view (#63-79)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 63 | VERIFIED | Four independent artifacts embedded verbatim and read by ONE render engine: `marketdata/subsector_confluence.json` (`universe="sp500_subsectors"`, 65 rows), `..._nasdaq.json` (`nasdaq_subsectors`, 12), `..._russell.json` (`russell_subsectors`, 93), `marketdata/basket_confluence.json` (49 baskets). Switching universes re-binds the same `#sc-app` / `#cf-table` components. No mixing: each universe's rows resolve only to its own directory — `subsector/auto-manufacturers.html`, `subsector_nasdaq/computer-hardware.html`, `subsector_russell/real-estate-services.html`, `subsector/b-memory-storage.html`. Counts match the commission's expected 65 / 12 / 93 / 49 exactly. |
| 64 | VERIFIED | Hard-coded DOM order inside `DIV#cf-uni[role=tablist]`: `BUTTON#cf-uni-subsectors` (S&P 500标普500 65), `#cf-uni-nasdaq` (Nasdaq-100纳斯达克100 12), `#cf-uni-russell` (Russell-2000罗素2000 93), `#cf-uni-baskets` (Thematic Baskets主题篮子 49). `aria-selected` moves correctly on selection (probed: subsectors true to false, nasdaq false to true). DAC-005's drift claim stays refuted. |
| 65 | VERIFIED (known defect carried) | S&P foot renders `65 of 113 subsectors have enough live data to time · 48 thin (listed in the table, not timed)` / `65/113 个子行业有足够实时数据可计时 · 48 个数据稀疏（列于表内，不计时）` — the exact `n_gateable` / `n_subsectors` / `n_thin` triple (payload coverage: `n_subsectors 113, n_gateable 65, n_thin 48`). The A5 semantic inaccuracy (the 48 are NOT in the table — the table holds 65) is carried unrepaired, as the ledger requires. |
| 66 | BLOCKED_DATA — VERIFIED ABSENT | Probe: with the Baskets universe selected, `#cf-foot` reads ONLY `How timing support is graded时机支持的评分方式` — no gateable/thin sentence, no invented substitute. Payload probe: `basket_confluence.json` `coverage` = `{n_baskets:49, n_high:33, n_med:14, n_low_conf:2, thin_share:0.041}` — no `n_gateable`, no `n_thin`. Note the candidate also does NOT synthesise a disclosure from the adjacent `thin_share` field, which would have been the tempting invention. Absence demonstrated, not merely claimed. |
| 67 | VERIFIED | Code-shared wording, silent at `n_thin=0`: Nasdaq foot `12 of 12 subsectors have enough live data to time12/12 个子行业有足够实时数据可计时`; Russell foot `93 of 93 subsectors have enough live data to time93/93 个子行业有足够实时数据可计时` — neither prints a thin clause. Payload coverage confirms `n_thin: 0` for both. R3A GAP carried: the nonzero-`n_thin` branch is still unobserved for these two universes. |
| 68 | VERIFIED | Producer state vocabulary rendered verbatim and bilingually, shared by all four universes. Distinct `regime.state` values on the frozen fixture: `EXTENDED, BUY, BUY_PARTIAL, SETUP_BUY, NEUTRAL, BELOW_TREND, TOPPING`; rendered label pairs `EXTENDED / 过热`, `BUY / 买入`, `SETUP / 预备`, `NEUTRAL / 中性`, `BELOW TREND / 趋势下方`, `RIDING / 顺势`, `TOPPING / 见顶`. 7 of the 9 states are exercised by this fixture (fixture-coverage GAP, not an artifact defect). |
| 69 | VERIFIED | `confluence.html:466-474` `CLASS_META` = `entry_now / tailwind / neutral / late / headwind` with `ORDER = ['entry_now','tailwind','neutral','late','headwind']`; `rowsOf()` folds anything else into `neutral` (`return (CLASS_META[k] ? k : 'neutral') === bucket;`) — exactly the `forming` fold. `forming` keeps its own honest disclosure line (`Also forming (T4 — earliest, weakest)构筑中（T4 — 最早、最弱）`) capped at `FORMING_CAP=4`. Live ledge for S&P: `Entry now现可入场1 / Tailwind顺风16 / Neutral中性21 / Late偏晚18 / Headwind逆风9`. |
| 70 | VERIFIED | Producer sort order preserved: `confluence.html` `rowsOf()` carries the in-code invariant `producer order, never re-sorted`, and the S&P payload is embedded verbatim with `universe="sp500_subsectors"`, all 65 rows `kind="subsector"`, `key` = `_slug(sub_industry_name)` values (`auto-manufacturers`, `oil-gas-midstream`, `computer-hardware`, …). |
| 71 | VERIFIED | `confluence.html:757` `var s = SORT[TAB] || {col:'tier', dir:1};` — default tier-ascending, per-tab; `:1088-1089` column heads carry `data-col` and toggle direction on click. The re-sort is client-side only and independent of the producer's class/weight/rs60 order, exactly as the ledger describes. |
| 72 | VERIFIED | Basket rows are stamped `kind="basket"` with a `basket_id` on all 49 payload rows (probe: `bKinds = ["basket"]`, `bHasBasketId = 49`), and render into the SAME `subsector/` directory with a `b-` filename prefix: `subsector/b-memory-storage.html`, `subsector/b-housing.html`, `subsector/b-insurance.html`, `subsector/b-ai-infra.html`. |
| 73 | VERIFIED | Amalgamation rows present and rendered. Nasdaq payload `sectors[]` = 8 rows, all `kind="sector"`, keys `amalg-defensives-extech`, `amalg-semis-silicon`, `amalg-ai-power-neoclouds`, `amalg-internet-platforms`, … Live: all eight render with destinations `subsector_nasdaq/amalg-*.html` (in the sector-backdrop rollup organ approved by adjudication §7). |
| 74 | VERIFIED | Per-universe detail directories are distinct and recorded: `subsector/` (S&P + baskets with the `b-` prefix), `subsector_nasdaq/`, `subsector_russell/` — every row's `detailHref(key)` is `ds().dir + ds().prefix + key + '.html'` (`confluence.html:490`). |
| 75 | VERIFIED (destination proof only — detail-page scope) | The members-listing sort lives on `subsector_detail.html.j2`, which is outside the six-view reference. The reference proves the route: clicking any group row records the exact production destination (e.g. `subsector/b-memory-storage.html`). Carried into GAPS: this row cannot be journey-demonstrated by a single-page artifact. |
| 76 | VERIFIED | `confluence.html:491` `function stockHref(tk){ return 'stock.html#' + encodeURIComponent(tk); }` — one function, all universes. Live: S&P picks render `stock.html#COIN`, `stock.html#NSC`; Baskets picks render `stock.html#JNJ`, `stock.html#NVR`, `stock.html#BG`. |
| 77 | VERIFIED | Coverage template with the per-universe noun swap, verbatim EN/ZH: `All subsectors全部子行业 65` / `All subsectors全部子行业 12` / `All subsectors全部子行业 93` / `All baskets全部篮子 49`; reveal control swaps the same noun: `Show all 65 subsectors展开全部 65 个子行业` vs `Show all 49 baskets展开全部 49 个篮子`. |
| 78 | VERIFIED | The five-part detector's attack surface is PRODUCER-side (rule 5), and the reference embeds those bytes verbatim: `subsector_confluence.json` has `universe == "sp500_subsectors"`, all 65 rows `kind == "subsector"`, and ZERO rows carrying `basket_id` (probe: `anyBasketId = 0`); the basket payload is the mirror (`kind == "basket"` and `basket_id` on all 49). The `_industry_map()`-traceable `key` set renders 1:1 into 65 table rows with no foreign row. The R3A attack suite (`tests/test_xpv2_sector_r3_fixture.py:383-455`) asserts on exactly these payload fields, so the reference preserves the detector's whole surface. |
| 79 | VERIFIED | Probe: typed `zzzznotarealthing` into `#cf-q`. Result: `#cf-cnt` = `0 / 65`, `#cf-table tbody` rows = 0, tbody innerHTML empty, and a regex sweep of the whole Confluence view for `no results|no match|未找到|无结果` returns false. The production absence is preserved; no placeholder was invented (PRC-007 stays refuted in the correct direction). |

## Cross-cutting: routing contract (#80-86)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 80 | VERIFIED | Verbatim `si_workspace.js` embedded: `VIEWS=['overview','map','moving','money','explore','confluence']`. Live exact-match dispatch probed for all six hashes; each activates exactly one section and re-titles the document: `#overview` to `Sector Central — R3 reference · Overview`, `#map` to `· The Map`, `#moving` to `· What's Moving`, `#money` to `· Money & Breadth`, `#explore` to `· Explore`, `#confluence` to `· Confluence`. |
| 81 | VERIFIED (20/21) + VERIFIED-AS-ADJUDICATED (§4) for the 21st | The embedded `LEGACY_ANCHORS` map holds exactly 21 entries. Target-existence probe: 20 resolve to a real element in the correct view (`actnow-section`/`regime`/`grader` to overview; `si-map`/`rotmap-section`/`sc-cyclemap`/`board` to map; `si-movement`/`rc-events-mount`/`rotation-app` to moving; `si-money`/`internals-section`/`scc-leadership` to money; `explore-section`/`table-section`/`chart-section`/`forming-narratives`/`tm-mount` to explore; `si-confluence`/`sc-app` to confluence). `sc-top` returns MISSING — it exists only as a CLASS on `DIV#cf-uni.r3-uni.sc-top`, never as an id. That is the A7 seam (c) explicitly recorded and NOT repaired in adjudication §4 ("`sc-top` id NOT minted"). PRC-003's collapse/drop claim stays refuted for the other 20. |
| 82 | VERIFIED | Boot-time-only redirect proven: loading `…CANDIDATE.html#theme-gold_miners` produces recorder lines `boot basketdata/baskets.json => hit (sync boot parse)` then `nav basket/gold_miners.html => recorded (would navigate to basket/gold_miners.html)` — the exact production destination. The seam is preserved, not repaired: setting `location.hash = '#theme-ai_agents'` AFTER boot leaves the Overview visible and records ZERO navigations. |
| 83 | FINDING (DIVERGENT) | `#read-<id>` does NOT leave a trace open. Probe: load `…#read-gold_miners`, MutationObserver on the document records `ADD si-trace` then `REMOVE si-trace`; final state `document.querySelector('.si-trace')` = null, `aria-expanded` row = none, and `REF.log` holds TWO nav entries `basket/gold_miners.html`. Manual click works (trace opens with `Gold Miners黄金矿业 GDX · Materials & Mining Cycle周期 Prime entry Conviction信心 75 Accumulate积极配置 Confluence共振 3/3 Cycle position周期位置 22`), so the defer/retry machinery is fine — the deep-link path double-fires. See F-1. Second defect in the same path: every trace-open ALSO records a spurious navigation, so the route recorder's own evidence is polluted. |
| 84 | VERIFIED | Unknown hash: `…#totally-unknown-hash` renders Overview only. Empty hash: loading with no hash leaves `location.hash === '#overview'` (the `history.replaceState(null,'','#overview')` arm) with Overview visible. |
| 85 | FINDING (PARTIAL) | Mechanics half is correct: the embedded verbatim `si_workspace.js` calls `el.scrollIntoView({block:'start'})` with no `behavior` key (instant), so the smooth-scroll automation trap does not apply. Landing half FAILS. Measured: `…#tm-mount` settles at `scrollY 2613` with the target `846px` BELOW the viewport top; `…#grader` settles at `scrollY 452` with the target `737px` below the top. Re-invoking `__siRoute()` does not correct it. Related smaller mismatch: the shim measures the sticky bar at 40px and writes `--ref-sticky-offset: 40px`, but the computed `scroll-margin-top` on `#tm-mount` is `56px` (the static fallback), so the var the commission §14 wiring exists to supply is not the value actually consumed. See F-6. |
| 86 | VERIFIED | Per-view destination inventory probed with all runtime content rendered. Anchor counts / bare-`#` counts / recorded-route counts: overview 25 / 0 / 23 (`basket/*`, `plans.html`, in-page hashes); map 23 / 0 / 23 (`sector_cycles.html#xlc`…`#xlre`, `sector_cycles.html`, `basket/*`); moving 25 / 0 / 25 (`rotation/*`, `subsector_rotation.html`); money 1 / 0 / 0 (one in-page hash — the Money view is link-free in production too); explore 17 / 0 / 16 (`basket/*`, in-page hashes); confluence (all four universes) `subsector/*`, `subsector_nasdaq/*`, `subsector_russell/*`, `subsector/b-*`, `stock.html#<TICKER>`. ZERO `href="#"` and zero empty hrefs anywhere — commission §19 satisfied. |

## Cross-cutting: access/hydration contract (#87-92)

| # | Verdict | Probe / grep evidence |
|---|---|---|
| 87 | VERIFIED | Access-state flip probed with a whitespace-stripped character census per view. gated to ungated: map 42,060 to 42,060 (delta 0), moving 30,757 to 30,757 (0), money 58,264 to 58,264 (0), explore 72,818 to 72,818 (0), confluence 55,731 to 55,731 (0); `#actnow` 1,815 to 4,433 (delta +2,618). The wall moves exactly one surface. |
| 88 | VERIFIED | Same census: all five non-Overview views render byte-identical content in the gated state, and their payloads resolve from the registry with no gate check anywhere (`REF.registry` holds one premium path only). This upgrades the R3A row's "inference from `config/site_access.yml`, not a live curl" to a rendered demonstration, and is consistent with the anonymous-regwall finding recorded in adjudication §8 (which sits in FRONT of the tier gate and is a different mechanism). |
| 89 | VERIFIED | Nightly-sole-advancer is stated on the surface it governs, verbatim and bilingual: the `#grader` sub-line ends `Sparse until it accrues; never fed back into the live score.` / `数据累积前较稀疏；绝不回灌入实时评分。` No client code path writes the ledger; the grader block reads `SCD.grader` only. |
| 90 | VERIFIED | Skeleton census across the whole artifact: `document.querySelectorAll('.skeleton,.shimmer,[class*=skeleton],[class*=shimmer]')` = 0 nodes. Overview arrives as baked HTML (the gated preview is present in the first paint), and Confluence's `#sc-app` is a static shell (`DIV#cf-ledge`, `DIV#cf-spread`, `P#cf-foot`, `DIV#cf-panel`) before `render()` fills it. Skeleton-free loading with reserved geometry is adjudication §3. |
| 91 | VERIFIED | Caps read from code and demonstrated live. Overview: `FOLD_CAP = 3` (`overview.html:457`), controls read `Show more显示更多 (1)/(2)/(2)/(24)` — count-labeled. Confluence (`confluence.html:479-486`): `FORMING_CAP = 4`, `LANE_CAP = 8`, `PICKS_CAP = 12`, plus the adjudicated `TBL_CAP = 8` for the full table. Live count-labeled reveals: `Also forming (T4 — earliest, weakest)构筑中（T4 — 最早、最弱）` with its own tnum count, `Show all 65 subsectors展开全部 65 个子行业` / `Show all 12 subsectors` / `Show all 93 subsectors` / `Show all 49 baskets展开全部 49 个篮子`, and Explore's `Show all显示全部 (49)`. Every cap's residual is printed, never silently dropped. |
| 92 | BLOCKED_DATA — VERIFIED ABSENT | Rendered-text sweep (TreeWalker over each view section, SCRIPT/STYLE excluded, harness drawer excluded) against `correct(ed|ion)|restate[ds]?|revis(ed|ion)|amend(ed|ment)?|更正|修正|订正|勘误`: overview 278 text nodes / 0 hits, map 740 / 0, moving 442 / 0, money 630 / 0, explore 829 / 0, confluence 482 / 0. No correction/revision marker, badge, tooltip or footnote was invented anywhere. Absence demonstrated. |


---

## Verdict summary

**92 of 92 ledger rows carry an explicit verdict. No sampling, no assumed rows.**

Counted directly from this file's verdict column:

- **VERIFIED** — 75 rows.
- **VERIFIED-AS-ADJUDICATED** — 8 rows, each citing a section of
  `ORCHESTRATOR_ADJUDICATIONS.md`: #18 (§8), #37 (§5), #46 (§5), #49 (§6),
  #52 (§6), #57 (§6), #58 (§2), #60 (§6). Two further rows carry an adjudication
  cite inside a VERIFIED verdict: #81's 21st entry `sc-top` (§4) and #90 (§3).
- **FINDING** — 7 rows: #11 MISSING, #19 PARTIAL, #32 PARTIAL, #40 DIVERGENT,
  #45 PARTIAL, #83 DIVERGENT, #85 PARTIAL.
  Seven finding-labels over six distinct defects: #19 and #32 share root cause F-3.
- **BLOCKED_DATA — VERIFIED ABSENT** — 2 rows: #66 (Baskets thin/gateable
  disclosure) and #92 (correction/revision representation). Both demonstrated
  absent by probe, not assumed.

Finding-to-defect map: F-1 = #83, F-2 = #11, F-3 = #19 + #32, F-4 = #40 (+ a smaller
second instance on #53, which is otherwise VERIFIED), F-5 = #45, F-6 = #85.

Severity roll-up: **3 major** (F-1, F-4, F-5), **3 minor** (F-2, F-3, F-6),
**0 blocker**. No finding falsifies the existence of a RETAIN capability in a way
that makes the reference unusable as an R3C migration source, and all six are
repairable inside the reference without touching production.

## FINDINGS detail

All reproduction steps assume the candidate served from its own directory
(`python3 -m http.server 8991` in
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/`) and a
headless Chromium page at `http://127.0.0.1:8991/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`.

### F-1 - MAJOR - `#read-<id>` deep link opens the trace, then immediately closes it (ledger #83)

**Symptom.** A `#read-*` deep link - the whole point of ledger row #83 - renders
nothing. The trace card is inserted and removed within the same boot.

**Reproduction.**
1. Load `.../MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html#read-gold_miners`.
2. Attach a MutationObserver before load; it records, in order, `ADD si-trace`,
   `REMOVE si-trace`.
3. After settle: `document.querySelector('#actnow .si-trace')` is `null`;
   `#actnow a[aria-expanded=true]` is `null`;
   `REF.log.filter(e => e.type === 'nav')` has TWO entries, both
   `basket/gold_miners.html`.
4. Control: a manual `row.click()` on the same row DOES open the card
   (`Gold Miners黄金矿业 GDX · Materials & Mining · Cycle周期 Prime entry ·
   Conviction信心 75 Accumulate积极配置 · Confluence共振 3/3 · Cycle position周期位置 22`),
   proving `window.__siTrace` and the capture-phase handler are both healthy.

**Root cause (traced with an instrumented `REF.nav` stack capture).** Both nav
records come from `openTrace` called by `reads` - i.e. `openTrace()` runs TWICE.
The Overview boot handler ends with

    if(window.__siViewReads) window.__siViewReads();
    if(window.__siRoute) window.__siRoute();     // build/views/overview.html:1018

Production does NOT do this. `templates/sector_central.html.j2:3088` is the only
production call site and it invokes `window.__siViewReads(BASKETS)` alone. The
extra `__siRoute()` re-dispatches the still-present `#read-` hash, re-sets
`pendingTrace`, and calls `openTrace()` a second time; the second `row.click()`
hits the toggle arm (`var was = open && row.nextElementSibling === open;`) and
removes the card. This is a reference-introduced deviation from the verbatim
router contract, not a carried production seam - and it is not recorded in
`ORCHESTRATOR_ADJUDICATIONS.md`.

**Second, independent defect on the same path.** The Overview trace handler ends
its guarded arm with `ev.preventDefault(); ev.stopPropagation();`
(candidate line 1394). Both that handler and the runtime shim's `data-ref-nav`
handler (candidate line 7029) are attached to `document` in the CAPTURE phase, and
`stopPropagation()` does not suppress a sibling listener on the SAME node -
`stopImmediatePropagation()` would. Consequence: every trace-open also emits a
false `nav` recorder line for the row's href. Since the route recorder is the
commission's destination-proof instrument (§19), this silently corrupts the
evidence for #83 and #86.

**Suggested repair (reference-side only):** drop the extra `__siRoute()` call, and
switch the trace handler to `stopImmediatePropagation()`.

### F-2 - MINOR - Bottoming-watch rows lost their producer destination (ledger #11)

**Symptom.** Ledger row #11 is "Bottoming-watch row click destination (href set by
producer, consumed verbatim)". The candidate renders the rows as inert `div`s.

**Reproduction.** Load the candidate (Overview is default). Then:
`document.getElementById('ov-watch').querySelectorAll('a').length` is `0`;
the three children are `DIV.r3-watch-cell` x3;
`document.getElementById('ov-watch-foot').querySelectorAll('a').length` is `0`.

**Evidence the destination exists and was dropped.** The frozen fixture's
`basketdata/baskets.json` `theme_intel.act_now.bottoming_watch` rows each carry an
`href`: `basket/power_grid.html`, `basket/nuclear_power.html`,
`basket/data_center_power.html`. Production renders them as links:
`templates/_us_bottoming_watch.html.j2:95`
`<a class="actitem" data-rpop href="{{ x.href }}">`. The R3B build reads the same
rows (`build/views/overview.html:857-883`) but emits `<div class="r3-watch-cell">`
with a `<strong>` name and no anchor.

`ORCHESTRATOR_ADJUDICATIONS.md` §4 records a Bottoming-Watch composition change
(constant-chip dedup to the strip foot) but says nothing about removing the row
link, so this is an undisclosed capability loss rather than an approved divergence.

### F-3 - MINOR - The hydration FETCH leg and its failure branch are unreachable (ledger #19, #32)

**Symptom.** The premium payload never travels through the intercepted fetch, so
two named legs of the access contract cannot be exercised at all.

**Reproduction.**
1. Load the candidate; open the harness drawer; set Access state to `hydrated`.
   Hydration works (lane rows 3/3/3/3/3 to 4/5/5/3/27, `#actnow .pg-more` 5 to 0).
2. Read the recorder: `REF.log` has 9 entries and NONE mentions
   `premiumdata/sector_central.json`, although `Object.keys(REF.registry)` shows
   the path is embedded.
3. Turn "Simulate fetch fail" ON, then set Access state to `hydrated` again.
   Result: `REF.simulateFetchFail === true` but the board still hydrates to
   4/5/5/3/27 with 0 disclosure lines.

**Root cause.** `build/views/overview.html:375` reads the payload synchronously:
`PG = reg('premiumdata/sector_central.json')`, where `reg()` is a direct
`REF.parseJSON(REF.registry[path])`. Nothing routes it through `REF.fetchJSON`.

**Consequences for the ledger.** (a) #19's chain
`whenAuthSettled -> fetch -> hydrate() schema/page validation -> DOM insert ->
restoreFold -> disclosure removal` is demonstrated only from `hydrate()` onward;
the first two legs are absent and the third
(`PG.schema !== 'tier_payload.v1' || PG.page !== 'sector_central'` at
`overview.html:692`) is dead code no harness control can reach. (b) #32's
401/403/offline collapse-to-no-op is asserted in a comment
(`overview.html:705-706`) and never executed - the gated state proves the RESTING
shape but not the TRANSITION.

**Suggested repair:** route the premium read through `REF.fetchJSON` (already
async-capable) and add a harness switch returning a 401-shaped result, so both the
schema-mismatch and the auth-failure branches render.

### F-4 - MAJOR - Untranslated raw producer strings leak into the ZH surface (ledger #40, #53)

**Symptom.** With `data-lang="zh"` the Map board prints English producer enums and
layer names with no ZH twin.

**Reproduction.** Load `...#map`, then
`document.documentElement.setAttribute('data-lang','zh')`, then walk `#board` for
leaf nodes whose text is pure ASCII and which sit in neither `.l-en` nor `.l-zh`.
Measured counts: `span.r3-chaintier` `validated` x33, `display` x13,
`confirmer` x11; `span.r3-chainlay` `Cycle state` x11, `Trend gate` x11,
`Regime gate` x11, `Momentum` x11, `Heat` x11, `Fragility` x2 - 114 nodes.

**Evidence these are raw producer values.** `build/views/map.html:771` emits
`'<span class="r3-chaintier">' + esc(r.tier ' + "|| ''" + ') + '</span>'`, and the
fixture's `sectordata/sector_central.json` `sectors[].reasoning[]` carries exactly
`{"layer":"Cycle state","tier":"validated", ...}`. The rows themselves DO carry
`en`/`zh` prose twins - only the `layer` and `tier` labels are passed through raw.

**Why this is a defect and not a faithful passthrough.**
1. The house bilingual rule and `docs/DESIGN_DOCTRINE.md`'s banned-vocab list
   (internal state/study names, untranslated stats, raw slugs) both bar it.
2. The sibling production page maintains a translation map for exactly this data:
   `templates/sector_central_china.html.j2:1425`
   `var LAYER_ZH={'Cycle state':'周期状态','Regime gate':'市况把关','Momentum':'动量', ...}`.
3. The word `validated` in user-facing text is CI-guarded
   (`scripts/check_validated_claims.py`), and here it renders 33 times.
4. The lane's own precedent, `ORCHESTRATOR_ADJUDICATIONS.md` §4, is to AUTHOR a ZH
   twin when production ships an EN-only string ("production's is an EN-only
   `title=`, which house law bans") - that remedy was applied to the thin-data dot
   and not here.
5. Also unrecorded: production's `#board` renders no reasoning chain at all - no
   `layer`/`tier` consumer exists in `templates/sector_central.html.j2` - so this is
   a NEW display surface, which makes it new display copy owing a copy-ledger entry.

**Smaller second instance (ledger #53).** In `#scc-leadership` the rising-star
driver legs render inside the ZH half untranslated:
`领导加速最快——breadth thrust · broad participation · return acceleration`. The
producer emits `rising_star.why[].leg` EN-only
(`marketdata/index_leadership.json`), so the same authored-ZH-twin remedy applies.

### F-5 - MAJOR - The whole-market map's `drawTrackRecord()` accessible equivalent is missing (ledger #45)

**Symptom.** Ledger row #45 names TWO text accessible equivalents for the
whole-market rotation map - `drawStrip()` and `drawTrackRecord()`. Only the first
is reproduced.

**Reproduction.** Load `...#moving`. A grep of `build/views/moving.html` for
`track_record`, `Track record`, `跟踪记录` and `Clears the bar` returns 0 matches.
In the rendered view, `#rotation-app` contains the strip lists (`.r3-strip` /
`.r3-striplist`, Emerging新兴 / Fading消退) but no track-record table, no verdict
chip, and no `days logged` / `calls logged` counts. A rendered-text regex for
`track record` over `section[data-view=moving]` returns false.

**Evidence the data is present and was simply not composed.** The frozen fixture's
`marketdata/subsector_rotation.json` carries a complete `track_record` block:
`{"schema":"subsector_rotation.track_record.v1","as_of":"2026-08-19",
"is_context_only":true,"n_snapshots":6716,"n_days":25,"horizons":{...}}`.
Production renders it at `templates/subsector_rotation.js:319-345`
(`drawTrackRecord`), including the verdict ladder
`{accruing:['Accruing','记录累积中'], measuring:['Still measuring','测量中'],
validated:['Clears the bar','已达标']}` and the recent-misses list.

**Why it matters beyond the ledger row.** This is the calibration/accountability
organ for the Moving view - the house "nulls printed, not hidden" surface. Dropping
it leaves the map's read unaccountable, and adjudication §7's own principle
("capability preservation outranks the L1 budget; un-composed RETAIN organs return
behind `.r3-disc` disclosures") was applied to three Confluence organs but not to
this one. Not recorded anywhere in `ORCHESTRATOR_ADJUDICATIONS.md` §5.

### F-6 - MINOR - Deep-link landings overshoot; the measured sticky offset is not the one consumed (ledger #85)

**Symptom.** Legacy/deep-link anchors activate the right view but leave the target
far below the fold.

**Reproduction (3.5s settle, 1440x1000).**
- `...#tm-mount` gives `window.scrollY = 2613` and
  `#tm-mount.getBoundingClientRect().top = 846`.
- `...#grader` gives `window.scrollY = 452` and
  `#grader.getBoundingClientRect().top = 737`.
- Re-invoking `window.__siRoute()` after settle corrects neither.

**Diagnosis.** The verbatim router's `scrollIntoView({block:'start'})` fires once,
before the view's async organs above the anchor have rendered; the later growth
pushes the anchor down and nothing re-scrolls. The MECHANICS half of ledger #85 -
no `behavior` key, therefore instant, therefore no smooth-scroll automation trap -
is correct and verified; only the LANDING fails.

**Related smaller mismatch.** The shim measures `.si-topbar` at 40px and writes
`--ref-sticky-offset: 40px` on `documentElement`, but
`getComputedStyle(document.getElementById('tm-mount')).scrollMarginTop` is `56px`
- the static fallback, not the measured value. So the commission §14 wiring that
adjudication §2 claims the router "honors" is not the value actually consumed by
the anchor.

**Suggested repair:** re-run the anchor scroll after the activated view's mounts
settle (a `requestAnimationFrame` chain or a post-render callback), and confirm the
`[id]{scroll-margin-top:var(--ref-sticky-offset)}` rule is not being outranked.

---

## GAPS carried (not findings - no artifact defect)

1. **#5** buy_soon `days`-ascending sort: only one fixture row carries `days`, so the
   producer-side sort cannot be re-exercised.
2. **#12** `+N more`: the fixture emits `more` only for `hold`/`avoid`, so only one of
   the five lanes renders the affordance (the code path is lane-generic).
3. **#15**, **#87-89** are server/producer invariants a quarantined client artifact
   cannot execute; **#18** is covered by adjudication §8, the rest are verified
   structurally or by absence-of-contradiction.
4. **#44** rotation-events table alternative: R3A GAP carried verbatim, not resolved.
5. **#60** `ai_watch` is `null` in the fixture, so the A8 "Model analysis / 模型分析"
   branch is live code that cannot be shown (adjudication §6).
6. **#62** falsifier rewrite: `narrative_emergence.json` carries no falsifier field,
   so `watchEn()/watchZh()` never fire on this fixture.
7. **#67** nonzero-`n_thin` branch for Nasdaq/Russell: still unobserved.
8. **#68** 7 of the 9 producer states appear on this fixture.
9. **#75** members-listing sort lives on `subsector_detail.html.j2`, outside the
   six-view reference; only the destination is provable.
10. Sibling R3B deliverables this cross-check would normally cite are not on disk:
    no copy ledger (deliverable 4), responsive contract (5), accessible-alternative
    contract (6), state-matrix evidence (7), hash/deep-link evidence (9),
    access/hydration evidence (10) or evidence crop index (12) exist under
    `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/` or
    `research/reference_integrity/mastermind-xpv2-sector-r3b/`. Several findings
    above (F-4's new display copy, F-6's §14 wiring) would ordinarily be adjudicated
    against those documents.

