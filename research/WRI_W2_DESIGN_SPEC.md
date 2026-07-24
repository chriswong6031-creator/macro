# WRI W2 — design spec of record (pinned)

Date: 2026-07-24. Parent: `WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (§0 gates bind).
Pinned artifact: **`mockups/wri/watchlist_risk_mockup.html`** — the exact markup/CSS W3 copies.
Reference crops: `mockups/refs/wri/01–05` (dark stress/calm, zh, light, mobile).
Verified live in preview 2026-07-24 (all five variants). Design decided per DESIGN_DOCTRINE +
frontend-design skill in the Fable main loop; W3 is implementation only — deviations from this
spec come back here first.

## 1. The design in one line

The page's thesis is a verdict — "Your 8 names move as 2 bets" — proven by the **bets braid**
(signature element): one thread per holding, threads of the same bet merging into strands whose
thickness is risk contribution; a two-lens toggle re-braids it for calm tape vs selloffs.

## 2. Page order (top → bottom)

1. Header panel (existing) — subtitle gains "…and what your book really is / 以及你的组合到底押了什么".
2. **L3 regime rail** — one line: market read (baked `risk_radar.dominant_label_*` + state tint)
   · book beta sentence (client) · "market state →" link. Tint = state ramp, NOT --up/--down.
3. **L2 Book Risk hero** — eyebrow (BOOK RISK · as-of) → verdict h2 + state chip → one so-what
   sentence → lens toggle → braid (≥561px) / bucket list (≤560px) → three sub-cards →
   one merged footnote with `?` method receipt.
4. Sync/account bar, controls, **watchlist card grid** (existing cards + L1 additions).
5. **Portfolio table** + two new columns (Share of book risk w/ mini-bar · Risk read).
6. Export/import details (unchanged).
`#fx_panel` is **absorbed**: sub-card 1 replaces its top block; its full beta table, shock
scenarios, and weight editor move into a `<details>` drawer inside sub-card 1 (Tier-2 home).
Weight plumbing (`FX.setAutoWeights` / `mdash.fx_weights.v1` fallback) is reused as-is.

## 3. Tokens (scoped under `.wri` / `.wri-rail`; theme.css untouched)

- Risk-state ramp (never --up/--down — zh-flip trap): `--wri-ok #3fb98d · --wri-tilt #d9a13c ·
  --wri-conc #e2703a · --wri-one #e05252`.
- Factor hues: mkt #8fa4b8 · growth #9a7bff · size #4fc3d9 · rates #5f8dff · usd #7fae72 ·
  oil #d9903c · china #e0645c · btc #f0a13c · gold #d4b23c · idio #66788c.
- Numerals: `--wri-mono: ui-monospace, "SF Mono", …` (ui-monospace leads — Chrome serif trap).
- All tints via `color-mix` over theme tokens → light/dark for free (verified crops 01/04).

## 4. Verdict + states (L2)

- **Lens-aware verdict** (decided in critique): stress lens is the DEFAULT (WRI-R7); flipping
  to "All days" re-words the verdict line, e.g. "On calm days: 6 groups. In selloffs: 2."
  The braid cluster count drives the sentence (picture-true); measured ENB prints only in
  sub-card 1 ("effective bets ≈ 2.1 of 8 names").
- State chip from ENB (stress lens): ≥4 "Spread out / 分散", 2.5–4 "Leaning one way / 偏向一侧",
  1.5–2.5 "Mostly one bet / 高度集中", <1.5 "Effectively one bet / 实为单一押注". Chip color =
  ramp. Thresholds print in the `?` receipt as heuristic v0.
- So-what sentence formula: top factor + its share + consequence + what moves independently.
  Review language only; no advice verbs; ≤ 2 lines at 760px.
- **Abstain state:** >40% of book dollars unmodeled → verdict = "Not enough modeled names to
  read the book / 可建模持仓不足，暂不给出组合判读" + chip listing unmodeled tickers. No state chip.
- **Empty/thin:** <2 weighted names → hero collapses to one invitation line (empty state is
  an invitation, not a mood).

## 5. Braid spec (signature)

- SVG viewBox `0 0 1000 208`; top ticks y=14; threads cubic `M x,26 C x,97 cx,97 cx,168`;
  strand bars y=170 h=7; labels y=186 (stagger +13 when strand <96px and odd index).
- Thread width `clamp(2, 34·√|share|, 15)` where share = position risk contribution;
  **negative contributors** (hedges) render dashed + `⇄` suffix on tick and label.
- Clusters = connected components of the twin graph (ρ ≥ 0.70) under the active lens;
  singleton labels = plain-word name (Gold/黄金) or ticker; multi-name strands get a bet name
  from the shared dominant factor ("Growth/Tech bet / 成长/科技押注").
- **No numbers on the braid** (decided in critique: strand % vs factor % were two different
  measures dressed alike — an honesty defect). Numbers live in sub-cards only.
- Draw-in animation 0.7s staggered 55ms, `prefers-reduced-motion` → static. Lens switch
  re-renders (paths transition). `role="img"` + aria-label summarising clusters; bucket-list
  fallback ≤560px (swatch + bet name + member tickers, singleton dedupe).

## 6. Sub-cards (L2)

1. **What drives your swings / 波动的来源** — factor variance-share bars (factor hue), idio row
   "Stock-specific / 个股特有", ENB line beneath; `?` = model receipt. Drawer (`<details>`):
   full per-name beta table + shocks + weight editor (absorbed FX panel).
2. **Move as one / 同涨同跌** — twin chip-groups; stress-only joins tagged "joins in selloffs /
   跌市中并入" + one-line why; calm lens dims stress-only rows (opacity .45).
3. **Biggest single risks / 最大单一风险** — top 3–4 positions by |MCTR share| with bars;
   negative rows green + "offsets the book / 对冲组合" note line.

## 7. L1 — cards + portfolio table

- Chips (max 3 at rest + `details` toggle; overflow lives in drawer). Vocabulary (EN/ZH),
  driven by lane states per masterplan §8 field mapping:
  Earnings in Nd/财报N天内 (hot ≤5d) · Stretched/过度拉伸 · Below trend/跌破趋势 ·
  Estimates falling/盈利预期下调 · Debt watch/债务关注 · Insiders selling/内部人卖出 ·
  Shorts rising/空头增加 · Rate-sensitive/利率敏感 · N% of book risk/占组合风险N% (info, from L2) ·
  moves with X/与X同步 (info twin) · price signals only — not in the risk model/仅价格信号——未纳入风险模型.
- Role badge top-right ONLY at ≥review: Review/复查 · Take-profit review/止盈复查 ·
  Exit review/离场复查 (ramp-tinted). Quiet (`ok`) names show nothing.
- Drawer rows: label (muted, 118px) + state token (OK/WATCH/plain-word elevated) + one plain
  reason ≤ 1 line + single as-of. Lane names are plain words (Price & trend / Stretch / Events /
  Estimates / Balance sheet / Who's selling — 价格与趋势/拉伸度/事件/盈利预期/资产负债/谁在卖出).
- Portfolio table: `Share of book risk` col (mono % + 44px mini-bar, negative → green
  "offsets") + `Risk read` col (role badge or —).

## 8. Compliance mapping (doctrine §5 checklist)

5-second test: verdict sentence IS the answer. Stance: so-what line + role badges (review
verbs). Banned vocab: none on Tier 1 (no ENB/MCTR/corr/z on glance — "corr ≥ .85" appears
only inside sub-card 2 body: **move it to the `?` tip in W3** — flagged). Numbers carry
meaning (Law 3): every % arrives inside a sentence or labeled bar. One as-of (eyebrow), one
merged footnote + method receipt. ZH parity verified (crop 03). No `title=` translated text —
mockup uses `title` on `?` glyphs: **W3 converts to `data-tip-en/zh`** (flagged). Nulls plain:
unmodeled chip + abstain state. honesty: "Measurement, not a forecast" footnote retained.

## 9. W3 builder checklist (hand this + mockup + crops)

1. Port mockup CSS into `templates/watchlist.html.j2` `<style>` (scoped `.wri*`); add rail +
   hero sections; absorb `#fx_panel`; extend cards/table per §7. `templates/risk_core.js`
   (pure math per masterplan §7) + `templates/watchlist_risk.js` (render; braid builder from
   mockup JS, data-driven). PAIRED site/ copies via `python -m scripts.check_template_site_sync --fix`.
2. Server inputs: build_site passes `window.WRI_REGIME` (risk_radar state + dominant_label_en/zh
   + vol_regime.regime + asof) into the template; everything else client-side from
   factor_betas.json (+W1 stress block) & stockdata JSONs.
3. Fix the two flagged items (§8): corr receipt → tip; `title=` → data-tip-en/zh.
4. Lens-aware verdict per §4; abstain/empty states; reduced-motion; keyboard focus on toggle
   (aria-pressed) + details; braid aria-label.
5. Verify against production-shaped data in preview (not curl); crops light+dark+zh in PR body;
   nav-gap + banned-vocab + template-site-sync CI green; **no self-merge** (masterplan §0.2).
