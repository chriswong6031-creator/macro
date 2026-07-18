# MSX-2 — macro_signals.html revamp spec (build contract)

Companion to `research/MACRO_SIGNALS_FX_CONTEXT_MASTERPLAN_BY_FABLE.md` §3.
This is the exact build contract: structure, idioms, copy, and stance mappings.
Builders implement it verbatim; deviations need a stated reason in the report.

## 0. Page frame

- Template stays self-contained (own `<style>` block; no dashboard.html.j2 CSS
  dependency). Keep theme.css include + nav include + search + lang/theme toggles.
- DROP `{% include '_plotly_head.html.j2' %}` — all three charts become
  server-side inline SVG (§5). macro_signals is the last Plotly page; retiring it
  saves 1.15 MB gz (same rationale as #2823).
- Define locally in :root scope of the page style block:
  `--num: ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;`
  (today `var(--num)` silently falls back — token exists only inside
  body.page-macro on dashboard pages).
- Ambient aurora: add a local fixed 3-blob backdrop `.msx-aurora` (blur 90px,
  pointer-events none, z-index 0; blobs: `--info`-blue at 8%/-6%, violet #8b5cf6
  at 92%/4%, green var(--up) at 50%/110%), tinted by market state: when
  `market_state.color == 'yellow'` add `.au-yellow` (green blob → amber), `'red'`
  → `.au-red` (→ red). Light theme: 45% opacity. Content wraps in a z-index:1
  container.
- Panels: frosted glass — `background:color-mix(in srgb, var(--panel) 82%, transparent);
  backdrop-filter:blur(14px); border:1px solid var(--line); border-radius:14px;`
  plus the 3px h2 gradient rail idiom (`h2::before` vertical gradient bar using a
  per-section `--rail` color).
- Section rails: growth/cycle `#5b9bf0`, money `#20c0a0`, mood `#e0a030`,
  currencies `#a070e8`, commodities `#8b93a1`.
- `.sig` atom (from dashboard idiom): 3px state rail | label (10px mono caps) |
  value (17px, 800, var(--num)) | meaning line (12px muted). States map to
  `--sc`: good=var(--up), warn=var(--warn), bad=var(--down), flat=var(--muted).
- Keep `.help` hover-tip mechanism (existing, works) for Tier-2 receipts.
- One `<details class="deep">` idiom for full technical tables (styled summary
  row: "Full breakdown ▸ / 完整拆解 ▸").
- Live-feel touches (taste bar, keep subtle): needle gauges get
  `transition: transform .8s cubic-bezier(.22,.9,.3,1)` (they animate on load via
  a tiny inline script setting final rotation after DOMContentLoaded); state dots
  on ACTIVE stress chips pulse (2.2s opacity keyframe); panels get a 320ms
  fade-up entrance stagger via `animation-delay` classes (respect
  `prefers-reduced-motion: reduce` — disable all three).
- Title (RCDATA law — plain text only): `Macro Signals — the full signal board`.
- Lead rewrite (bilingual):
  EN: "Every gauge behind the macro dashboard — the cycle, real-time conditions,
  liquidity, sentiment, positioning and the dollar — each with what it means
  right now. These readings feed the system's context layer; none of them alone
  drives a buy or sell call. Machine-readable copy: macro_signals.json."
  ZH: "宏观仪表盘背后的全部量表 — 周期、实时状况、流动性、情绪、持仓与美元 —
  每一项都附有当下含义。这些读数进入系统的背景层；任何单项都不会直接触发买卖
  决定。机器可读版本见 macro_signals.json。"
- Cross-links: lead keeps "← Back to Macro Dashboard"; ADD sibling link
  "Macro Weather (labels & history) → macro_context.html" /「宏观气象台（标签与
  历史）」 in the lead line and footer. (Today the two pages are mutually
  undiscoverable.)

## 1. Hero — "Right now" strip (span12)

Grid: [stance block | 4 gauges | market-state pill].
- Stance block: h1 + ONE stance sentence from `market_state.color`
  (vm.market_state may be absent → fall back to neutral wording):
  - green: "Conditions support staying invested — watch the usual risks." /
    「环境支持持仓 — 留意常规风险。」
  - yellow: "Mixed signals — hold what works, add slowly." /
    「信号混杂 — 持有有效仓位，谨慎加仓。」
  - red: "Defensive tape — protect first; opportunities can wait." /
    「防御行情 — 先保护本金，机会可以等。」
  - absent: "A mixed picture — read the boards below." / 「情况混杂 — 请看下方各板。」
- 4 needle gauges (semicircle SVG, viewBox "0 -4 140 101", needle rotate
  score*1.8-90 around 60 68, tip drop-shadow glow keyed to state):
  1. Growth (growth_score −1..+1 → 0..100): label RISING/FALLING → 上行/下行.
  2. Inflation (same mapping).
  3. Fear/Greed (fear_greed.dial 0..100, band label translated via existing map).
  4. VIX percentile (vix.pctile 0..100; label = vix.regime word).
  Under each: value + plain word. Each gauge's technical detail (agree %,
  n legs) → .help tip.
- Market-state pill: Green/Yellow/Red translated ("Market state: Green" /
  「市场状态：绿灯」), links to macro.html. Absent-safe.
- ONE as-of stamp for the whole hero (latest.date).

## 2. Growth & the cycle (span12, two sub-cards)

Sub-card A — Business cycle:
- BIG phase label (td(BC.phase.label)) + plain sentence per phase key (map at
  render, fallback = label itself):
  expansion: "The economy is growing — the cycle backdrop is a tailwind." /
  「经济扩张 — 周期背景为顺风。」; slowdown: "Growth is cooling — late-cycle;
  gains get choppier." / 「增长降温 — 周期后段，行情更颠簸。」; contraction:
  "The economy is shrinking — defensive backdrop." / 「经济收缩 — 防御背景。」;
  recovery: "Growth is turning back up — early-cycle tailwind." /
  「增长回升 — 周期初段顺风。」
- Recession signal chip: OFF → "No recession signal" / 「无衰退信号」(green);
  ON → "Recession signal ON — N months" / 「衰退信号已触发 — N个月」(red).
  Depth/breadth ✓✗ + shadow phase + the whole OOS/LORO receipt → ONE .help tip
  (verbatim technical text welcome there).
- Tier momentum: three rows (Leading 领先 / Coincident 同步 / Lagging 滞后), each
  an arrow ▲▼ + plain word ("turning up" 转强 / "turning down" 转弱 by mom6 sign)
  + a small strength bar (|mom6| clipped). diffusion/n_legs → .help tip.

Sub-card B — Conditions grid (2×4 .sig tiles, each: value, state word, ONE
meaning line; ALL member statistics → per-tile .help receipts):
1. Recession risk — score/100 + label; meaning "odds the economy tips over the
   next year" / 「未来一年经济衰退的可能性」. Receipt: Sahm, NY Fed prob, EBP.
2. Drawdown risk — score/100 + band; meaning "odds of a ≥10% index drop in ~3
   months vs normal" / 「约3个月内指数回撤≥10%的相对概率」. Receipt: P(dd10),
   base rate.
3. Financial conditions — state word; meaning "how easy money is to get" /
   「资金松紧程度」. Receipt: NFCI, %ile, trend.
4. System stress — state; meaning "stress inside the financial system (OFR)" /
   「金融体系内部压力(OFR)」. Receipt: FSI, top channel, CP funding.
5. Growth right now — GDPNow % as value; meaning "live estimate of this
   quarter's growth" / 「本季度增长的实时估计」. Receipt: WEI.
6. Inflation right now — sticky CPI ann. as value; meaning "slow-moving prices
   are still rising at this pace" / 「粘性物价仍以此速度上涨」. Receipt: flexible.
7. Jobs & activity — read word; meaning from claims direction ("layoffs steady" /
   「裁员平稳」 vs "layoffs rising" / 「裁员上升」 by claims_yoy sign). Receipt:
   claims YoY, Indeed, withheld taxes.
8. Risk appetite — RORO word; meaning "how much risk investors are reaching for"
   / 「投资者的冒险意愿」. Receipt: RORO, VRP, VIX term, stock-bond corr.
Capitulation tile only when score is not none (9th tile, span-flexible).

## 3. Money & liquidity (span6 + span6)

- Fed liquidity: SVG chart (§5.1) + headline state: rising →
  "The money tide is rising — historically the most reliable tailwind." /
  「资金潮上涨 — 历史上最可靠的顺风。」; falling → "The money tide is going out —
  a headwind." / 「资金潮退去 — 逆风。」 4-week change as chip (+$XXbn / 4wk).
  Mechanism note (WALCL−RRP−TGA) → .help tip.
- Credit & breadth: SVG chart (§5.2) + state line derived: hy_oas last vs 1y
  median AND pct_above_50: both fine → "Credit calm, participation healthy —
  no smoke." / 「信用平稳，参与度健康 — 无警讯。」; spread widening →
  "Credit spreads widening — the market's smoke detector is warming." /
  「信用利差走阔 — 市场烟雾探测器升温。」; breadth < 40 with spreads calm →
  "Narrow participation — strength is thin." / 「参与面收窄 — 涨势偏窄。」

## 4. Mood & positioning (span6 + span6, then VIX span6 + commodities span6)

- Fear/Greed card: dial gauge + band chip + "what's driving it": top 3 legs by
  |z| as bars with plain names; full legs/excluded/young tables inside ONE
  `<details class="deep">`. Composite mechanics → .help. One merged footer
  (existing disclaimer text, once).
- Fear↔Euphoria row (inside same card, secondary): score + band + positioning
  chip (confirms 一致 / diverges 背离 / mixed 混杂) + .help receipt with the 7
  legs. (Two composites exist deliberately — FG is the wide composite, FE the
  RORO-side read; say so in the .help.)
- Positioning ("Who's positioned how" 谁在如何持仓): keep rows; gauge + existing
  plain label/verdict; per-row source detail → .help.
- VIX monitor: value + change + regime chip + term-structure word; SVG (§5.3).
- Commodities tape: rows with name, trend words replace ✓✗ ("above trend" /
  「趋势上方」, "below trend" / 「趋势下方」 from above200), 3-mo % with color,
  off-52w-high %. RSI → .help. DXY row present in this table already via
  playbook; fine (it cross-links §Currencies).

## 5. SVG charts (build_site.py — replace the three Plotly builders in place;
vm key names unchanged: chart_liquidity, chart_credit_breadth, chart_vix)

Common: pure-python SVG strings (no JS dependency), width 100% via
viewBox="0 0 640 220", background transparent, axis text 10px var(--muted),
gridlines var(--line) at 25/50/75%, series stroke-width 1.6, `vector-effect:
non-scaling-stroke`, CSS-variable stroke colors ONLY (`stroke="var(--info)"`
etc — hardcoded hexes break zh red/green swap and themes), area fills via
`fill="var(--info)" fill-opacity=".08"`, latest-value dot + right-edge label.
5.1 Net liquidity: 2y window line (var(--info)); zero-change months shaded? no —
   keep one line + last 4wk change annotated; recession-free window so no bands.
5.2 Credit & breadth: dual series — hy_oas (var(--down)) left scale, pct_above_50
   (var(--up)) right scale 0..100; two right/left edge labels; legend as two
   inline chips above the SVG (not inside it, so text stays bilingual spans).
5.3 VIX: 90d line (var(--warn)); horizontal regime band separators at 16/20/28
   as faint dashed lines with tiny labels (calm/normal/stressed/crisis words
   already exist — put words in HTML legend, not SVG text, for bilingual spans).
All three: `{% if chart_x %}` guards stay; absent → panel hides (existing).

## 6. Currencies & the dollar (span12; NEW — reads vm.fx_context; ENTIRE section
inside `{% if fx_context %}`; every sub-block presence-guarded)

vm addition (build_site.py): `fx_context` dict loaded via lib/forex_link (new
helpers from MSX-1) + data/forex/latest.json: {asof, dollar_desk, strength,
regime_radar, transmission, state_changes, pairs(USDCNH only), recent_events}.
`recent_events`: last ≤5 desk-level events from data/forex/alerts.jsonl
(types: smile_regime/triple_red/scenario/dollar desk families), fail-open [].
Also append `fx` block to macro_signals.json sidecar (compact mirror of the
above minus events).

- Dollar regime card: smile regime plain-word map:
  'US growth premium' → "Dollar strong — the US is out-earning the world." /
  「美元走强 — 美国增长领先全球。」
  'Risk-off haven bid' → "Dollar strong — investors hiding in it." /
  「美元走强 — 避险资金涌入。」
  'Global reflation' → "Dollar soft — growth is broadening beyond the US." /
  「美元走软 — 增长扩散至美国以外。」
  'US-specific stress' → "Dollar weak while stress rises — a US-specific worry."
  / 「压力上升而美元走弱 — 美国自身问题。」
  'Neutral' → "Dollar drifting — no clear regime." / 「美元方向不明。」
  Plus: lean word row ("Desk read: dollar-supportive backdrop · 3 of 4 legs
  agree" — from lean + lean_n/lean_net, translated), days-in-regime chip from
  state_changes.smile_regime.days_in_state ("held N days" / 「已持续N天」,
  hidden when null). All desk leg values (real_rate_z, fed_path_bps, REER gap,
  COT pctile…) → ONE structured .help receipt.
- TRIPLE-RED banner (only when dollar_desk.triple_red): full-width red row:
  "⚠ Dollar, stocks and bonds are falling together — the dollar is not acting
  as a safe haven right now." / 「⚠ 美元、股票与债券同跌 — 美元当前未起到避险
  作用。」
- Strength meter: per-currency horizontal bars at default horizon (strength
  −1..+1 from center), ccy code + zh name, EM tinted amber; "trailing move, not
  a forecast" one-liner footer / 「仅为近端走势，非预测」.
- Stress radar chips: one chip per scenario with intensity>0 OR active:
  name (bilingual from scenarios receipts) + intensity/100; active → red border
  + pulsing dot; dominant → "dominant" tag. Wilson/base-rate receipt + ⚑
  illustrative note → per-chip .help. When nothing ≥ intensity 5: single quiet
  line "No known stress pattern is configured today." / 「当前无已知压力形态。」
- CNH row (pairs.USDCNH present): state words: neutral → "Offshore yuan: no
  unusual pressure" / 「离岸人民币：无异常压力」; outflow_stress → "Offshore
  yuan under outflow pressure" / 「离岸人民币承受外流压力」; inflow → "Offshore
  yuan: inflow bid" / 「离岸人民币：资金流入」. Basis bps → .help.
- Transmission chips: "A stronger dollar is pressing on:" / 「美元走强正压制：」
  headwind_for list as chips; tailwind_for as green chips ("helping" /
  「助力」); correlations → .help.
- What changed: recent_events rows (date + bilingual headline, severity dot);
  empty → hide block.
- Footer: "Full currency board → forex.html" / 「完整货币面板 →」.
- Come-back honesty: sub-blocks absent until first nightly (strength,
  state_changes, scenarios) simply don't render — never show empty shells.

## 6b. Critic deltas (census 2026-07-18 — bind on the builder)

- vm ALREADY has `cross_asset` (engine/cross_asset_confirm.py snapshot) with
  bilingual FX caution flags (`caution_flags` filtered `owner=='fx'`:
  triple_red, usd_positioning, usd_transmission_unstable, em_carry) — REUSE
  these strings for the caution rows in §6 rather than re-deriving copy; the
  fx_context vm key supplies the deeper blocks (strength, scenarios,
  state_changes) that cross_asset lacks.
- site/macro_signals.html is NOT a template-site paired asset
  (check_template_site_sync skips .j2) — source-only PR confirmed; live page
  heals on first nightly.
- docs/SIGNAL_BUS.md row for site-macro-signals: update the entry note when the
  sidecar gains the fx block.
- The template's inline `t()`/`td()` macros are the bilingual mechanism — keep
  them (no imports).
- Render budget: SVG conversion REDUCES build cost vs Plotly; no budget concern.

## 7. macro_signals.json sidecar additions (build_site.py)

Additive: `fx` (compact §6 mirror), `market_state_color`, `stances` (the
computed hero/section stance words — machine-readable so the Brain reads the
same words users see). Keep existing keys byte-compatible.

## 8. Checklist deltas (verify before ship)

- 5-second test per panel; stance present on every panel (Law 1).
- Banned words absent at glance tier: z-score, diffusion, LORO, OOS, n=, %ile,
  composite/leg jargon, raw state enums (outflow_stress etc must never render
  raw). "validated" never appears anywhere (CI).
- One as-of per panel max; one footnote per panel.
- l-en/l-zh dual spans everywhere incl. SVG-adjacent legends (no text inside
  <svg> that needs translation — legends live in HTML).
- prefers-reduced-motion honored; no Plotly include; page weight target < 300KB.
- Fast-harness verify: MACRO_DUMP_VM=1 full build once → render_macro_fast per
  iteration; browser-verify EN/ZH × dark/light; screenshots as proof.
