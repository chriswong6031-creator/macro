# Crypto Master Cockpit — Masterplan (vector.html rebuild + crypto asset-class platform)

> **Produced:** 2026-07-29 by Fable 5 (main loop) from: operator brief ("vector.html is one of the worst-designed pages on the site — toy-story look, data/number/alert spam everywhere; rebuild it, upgrade the engine, plan the full crypto cockpit + dedicated crypto section; assess vector_allocation.html and btc_strategy.html") → 7-lane census/research fan-out (page census, engine census, design-system census, neural-web census, 3 competitor/data-source web lanes, all sonnet) → Fable synthesis → Opus adversarial review.
> **Status: PLAN ONLY — nothing here is built.** This is the commissioning document for the build sessions. Per the spawn-handoff law, §0 is the acceptance-gate contract that every build prompt must inline.
> **Standing law honored throughout:** the Override-Registry program ([BTC_VECTOR_FIX_MASTERPLAN.md](BTC_VECTOR_FIX_MASTERPLAN.md)) is **closed** — owner decisions D1–D5 are recorded and no sizing-authority change is proposed here. The factor roadmap ([VECTOR_FACTOR_ROADMAP_2026.md](VECTOR_FACTOR_ROADMAP_2026.md)) remains the adjudicated calibration backlog — this plan sequences it, it does not re-adjudicate it. DO_NOT_REBUILD kills honored: no new override gates laundered into `allocation()`, no parallel shock-vector classifier, no composite regime scorecard fusing positioning into a regime verdict.

---

## §0 ACCEPTANCE GATES (inline these in every build-wave spawn prompt)

A wave is **not done unless**:

1. **Fresh end-to-end happy path, zero manual workarounds** — the page renders from a clean `python -m scripts.build_vector` (or the wave's builder) on production-shaped data; a race you reload around is a bug you own.
2. **Visual proof in the PR body** — full-page screenshots (light + dark + zh) at desktop 1280px and mobile 375px, plus per-shelf crops vs the reference mockups committed under `mockups/refs/crypto_cockpit/`. Computed-style verification for any token/palette claims (the house `visual-orders-computed-style-verification` standard).
3. **The 5-second test transcript** — the PR body states what a cold reader would say the page means and what to do, per shelf. If a shelf can't pass, it doesn't ship on Tier 1.
4. **Word budgets enforced** — Tier-1 shelf: title ≤ 4 words, subtitle ≤ 14 words, row ≤ 1 line, ONE as-of stamp per shelf, ONE footnote per shelf. Decorative/pictographic emoji banned from panel chrome (🧠🌊🔥🔋📊🏛⏳🔔-class); the ratified action-lane glyph set (#2206), directional glyphs ▲▼, and state dots remain sanctioned.
5. **No banned vocabulary on Tier 1** (DESIGN_DOCTRINE Law 2): no internal state enums, no `n=`/z-scores/percentile jargon untranslated, no raw slugs, no "falsifier/refuted/证伪" anywhere front-facing (windows + "what we're watching" framing only), no "validated" (CI-enforced).
6. **Alert demotion holds** — the flagship page carries at most ONE quiet "what changed" line above the fold and zero always-visible warning boxes; staleness renders as calm `.dtp`-style honesty chips, never red banners. The full alert stream lives in the Alert Center / Tier-3 shelf only.
7. **Bilingual parity** — every new string dual-emitted via the page `t()` macro; zh copy equally plain; no translated text in `title=` attributes (CI-guarded); zh directional color flip (红涨绿跌) respected by every new colored element; Plotly→ilx conversions keep theme + zh recolor working (ilx does this via CSS vars — one reason Plotly must go).
8. **Nightly budget accounting in the PR body** — measured wall-clock delta of the render step and any new collector, against the ~67-min render budget; heavy compute proven off the render path (R2 artifacts or one-time backfill scripts).
9. **Ledger discipline** — nightly remains the sole advancer of any forward ledger this plan creates (cockpit state history, breadth/dominance accrual); intraday lanes discard `data/` writes.
10. **Engine honesty** — every new engine surface ships display-tier (no gauntlet needed to SHOW it, per the accrual law) with plain-word null/coverage disclosure on Tier 1 + receipt on Tier 2; nothing new ranks, sizes, or gates money without the promotion gauntlet; LLM layers may only de-escalate calibrated keys, never originate signals.
11. **No child self-merge on first-pass flagship UI** — build agents return PR + visual artifact to the commissioning session, which reviews against this section before the normal same-day squash-merge chain.
12. **Old URLs keep working** — any page merged/renamed ships a redirect stub (the house has no server rewrites on Pages/VPS static: stub HTML with `<link rel=canonical>` + meta refresh), and the nav/SEO heads update in the same PR.

---

## §1 The verdict & the thesis (read this first)

**Verdict on today's estate:** the Bitcoin Vector's *engine* is genuinely deep — 20 `engine/btc_*` modules, a calibrated allocation stack with an override registry, an impulse radar, a cycle-thesis monitor, options/leverage/miner/attention data, an intraday flash-crash sentinel and a live-quote lane — but the *page* buries that quality under a spine with no hierarchy and a skin with no discipline. At rest: four-plus stacked verdict layers (needle dial → stance chip + grade badge → full recommendation card → four more force pills → two conviction-card risk words), three separate "what might happen next" surfaces, two interactive time toys, an 11-strip fold-teaser wall, a visible alert timeline, and a consumer-app identity layer (animated gauge, gradient wordmark, ~19 emoji glyphs, 9 keyframe systems) on a hand-forked stylesheet that never links `theme.css`. Three design PRs in the last four days (#3550, #3610, #3755) each improved a region and none fixed the disease, because the disease is structural: **the page has no governor — every new engine buys a new section.** A prior "radical simplification" (#1597, 25→14 sections) regressed to ~24 mapped blocks (28 headed panels) within weeks. Patching is proven not to hold; this plan rebuilds the page architecture with a hard structural cap and moves the engine's depth behind it.

**The thesis:** rebuild the crypto estate as a three-surface platform on the house design system —

1. **`vector.html` — the Bitcoin command deck** (the flagship; polish priority #1). One decision surface, six fixed shelves, everything else demoted to hovers and folds. The signature element is the **Regime Tape** — a full-width SSR chart of BTC price over regime-shaded bands with the model's allocation ribbon underneath: the page's thesis ("Bitcoin's regime on one page") drawn as one picture.
2. **`crypto.html` — the Crypto Cockpit hub** (new; the asset-class dashboard that earns the crypto crowd). Market-state hero (total mcap tape, BTC dominance, breadth, altseason gauge), a signal-first complex board (BTC/ETH/SOL + top-N), flows (ETF/stablecoin), derivatives state, the crypto-equities bridge (COIN/MSTR/miners from existing coverage), and the catalyst calendar. CoinMarketCap shows ten thousand rows of data; we show the read. That asymmetry — **stance, not supermarket** — is the entire competitive position, and it is the one thing the incumbents structurally cannot copy (their business is the supermarket).
3. **A top-level `Crypto` nav group** promoting the family out of "Other Assets", mirroring the market-group anatomy users already know (US/China/HK/Canada/International): Cockpit hub · Bitcoin Vector · strategies · crypto equities.

**Satellite verdicts (detail in §6):** `btc_strategy.html` — **merge into vector.html** as the Strategy & Track Record fold (spvector-style scorecard), kill the standalone page with a redirect stub. `vector_allocation.html` — **rebuild as the hub's allocation panel** (`crypto.html#allocation`), redirect the old URL; its multi-asset sleeves (BTC·ETH·alts·cash) are the natural bridge content for the new hub, not a standalone page. `strategy_btc_trend.html` — fold its scorecard row into the same Strategy fold.

**Engine verdict (detail in §7):** the BTC single-asset engine needs *sequencing, not reinvention* — the adjudicated factor roadmap already names the highest-leverage work (methodology gates first: purged CV, orthogonalization, probability calibration; then the near-zero-pipe factors: RV cones, gamma-flip, LTH/STH spread, stablecoin tide, Wikipedia attention, peg veto). What is genuinely *missing* is the **asset-class layer**: there is no universe ingestion (top-N coins), no dominance/breadth/altseason engines, no ETH/SOL first-class series (yahoo close-only today), no cross-crypto relative-strength — and therefore nothing for a hub page to stand on. This plan adds that layer display-tier-first (accrual law: display ships freely; authority needs the gauntlet), on keyless free sources verified in the 2026-06 data audit.

---

## §2 Diagnosis — why the current page fails (first-hand autopsy)

### 2.1 Design autopsy (the "toy story" complaint, made precise)

Verified against `templates/vector.html.j2` at HEAD (2,008 lines / 16,330 words; renders to 376 KB), full section-by-section census on file. Two partial cures have **already been applied** — 11 of ~24 sections sit in closed `<details class="sec-fold">` accordions (60 of the 63 `.mini` stat-rows are inside folds), and a 2026-07-22 "vec-revamp" style layer flattened the old glass cards (18px→14px, hover-lift removed, its own comment: the glass "read as visually noisy beside the crisp macro dashboard"). The page still fails, which localizes the disease precisely — it lives in the **visible spine** and the **identity layer**, not in the fold contents:

| Symptom | Evidence (at rest) | Root cause |
|---|---|---|
| **Verdict fatigue — ≥4 stacked verdict layers before the fold stack** | needle dial (score + band + bull/bear tally) → composite stance chip ("Buy carefully…") + optional grade badge + optional crowding/froth pill → full Recommendation card (action, conviction, exposure, levels, key-risk banner) → Four-Forces rail (4 more stance pills) → two conviction cards (risk-word headlines) | Each shipped in its own PR as "the answer"; nothing was demoted when the next arrived. The reader is told what to do 7+ times in slightly different vocabularies |
| **Three probabilistic-outcome surfaces at rest** | forward cones card (7d/30d/90d whisker rows) + mid-term conviction card + short-term conviction card — three different renderings of "what might happen next" | Same content class, never merged |
| **Two interactive time toys at rest** | Cycle Time Machine (canvas scrubber, play button, 5 presets, ~13 live readout fields) + the strategy chart (Lightweight Charts, 3 panes, 4 variants × 4 timeframes × log toggle, in a fold teaser) | Feature accretion; each is individually good, together they make the spine a playground |
| **The fold-teaser wall** | 11 consecutive eyebrow strips, each with 2 teaser stats ("Macro backdrop · NEUTRAL · 52/100…") | Progressive disclosure done as a wall of label+number strips still *reads* as 11 more signal rows |
| **Consumer-app identity layer** | animated SVG needle gauge with sweep-in + glowing pulse trail + breathing hub; gradient-filled "Vector" wordmark (`--btc→--btc-2` text clip); hero radial glow; **9 custom `@keyframes`**; 17 linear-gradients; **~19 distinct emoji glyphs / ~30 occurrences** (₿🧠⚠🔴🟢🔥🌊⚡🔋📊🏛⛔⏳🔔…) as inline icons | No iconography system, so emoji filled the gap; the dial/glow/gradient register is fitness-app, not instrument |
| **A forked skin, maintained by hand** | `build_vector.py:34-47` palette is commented "Glassnode/Swissblock light palette" (VECTOR_SKELETON.md reverse-engineering); the page never links `theme.css`, re-declaring every token from a Python dict, with the light/dark default inverted vs the house convention, hardcoded pastel badges (`.v-conf #E3F5E9` etc.) bypassing the house `color-mix()` badge formula, and a `_vector_polish` shim re-implementing nav CSS that `theme.css` would provide for free. (History note: theme.css's *light* palette was later tuned to match vector — the colors partially converged; the fork itself is the defect, as every site-chrome upgrade now misses this page. `btc_strategy.html.j2` already proves the family can link `theme.css` directly) |
| **Alert estate on the flagship** | ~11 distinct conditional alert constructs; at rest: What-Changed chip row + the visible Recent-Alerts timeline section (6 filter buttons, day-grouped events) + key-risk red-tinted banner + optional amber gate box + crowding/froth pills; inside folds: red-tinted STALE banners (impulse radar, CVD) | Alerts were designed page-local (2026-06, pre-Alert-Center); the falsifiers-to-background ruling (#3821) and the Alert Center shipped later and this page was never ported |
| **Narrow rail** | `.wrap{max-width:1180px}` vs the shared ~1500px flagship rail (the `_vector_polish` shim even force-widens the nav bar to 1500px while the content stays at 1180 — the page is visibly narrower than its own nav) | Pre-dates the shared design rail |
| **Plotly (narrow, real)** | `_plotly_head` + server-rendered Plotly for the small static charts (Momentum/Structure/BFI, etc.); strategy chart is Lightweight Charts (fine — sanctioned real-chart stack); Time Machine is raw canvas (fine) | Predates the ilx ruling (2026-07-20: illustrative charting on dashboards = `lib/illus.py` SSR SVG). Baked Plotly traces also freeze EN blue/red at build time, so **zh 红涨绿跌 silently breaks inside those charts** — the exact defect ilx's CSS-var recolor exists to fix |
| **Weight** | 376 KB HTML (siblings: 144 KB, 65 KB) | Inline chart JSON + the full fold stack shipped to every visitor |

What is **not** broken: the bilingual apparatus is excellent (552 `t()` sites, 46 `qmark()` receipts, `td()` glossary, zh color-pole inversion in page CSS); the live BTC price lane works; tabular-numeral discipline exists on this page (though not on `vector_allocation`); most fold *content* is well-tiered; much of the copy already speaks doctrine ("Watch — don't chase"). The raw material is good. **The spine, the skin, and the alert estate are the failures — plus the structural fact that none of the three prior design PRs could hold the line (§2.3).**

### 2.2 Content autopsy (the "random data everywhere" complaint)

The deeper failure mode, judged panel-by-panel: **the page shows the engine's inputs as if they were the user's outputs.** CME COT percentiles, 25Δ skew, OKX long/short accounts, hashprice, holder spread, Wikipedia pageviews, taker CVD — every one of these is a *driver* that should move exactly one visible thing (its axis's state word) and otherwise live behind a hover. Today each is its own titled card with its own chart, so the user is asked to run the fusion the engine already ran. The doctrine's demotion rule ("when in doubt, demote — nothing is lost by moving detail to a hover; attention is lost by not moving it") indicts roughly 20 of the ~24 mapped blocks. The full disposition table (Appendix A) sends each to its new home: a shelf row, a hover receipt, a fold, or a Tier-3 page.

### 2.3 Process autopsy (why three redesigns in four days didn't hold)

#1597 cut 25→14 sections; the count is back to 28. #3550/#3610/#3755 restyled regions. The regression mechanism is that **section count is unpriced**: any engine PR can append a `<section>` for free. The rebuild therefore ships a structural governor, not a style pass: the template's Tier-1 body is a fixed six-shelf skeleton (§4.1) whose shelves are *closed* — a new signal must claim a row inside an existing axis (or displace one), or it lands in a fold/Tier-3 page. CI enforcement: a template lint asserting the Tier-1 shelf count and banning new top-level sections on this page (cheap grep-level check, same family as the vocabulary lint), so the governor survives future engine PRs the way the render budget survives feature PRs — by being enforced, not remembered.

---

## §3 Design language — the Cockpit idiom

Design authority: DESIGN_DOCTRINE.md (content law, wins conflicts) + frontend-design skill (visual bar). Choices below are deliberate, made for this brief; the build implements them exactly (Opus `designer`/`builder` per the routing law — design choices do not reopen downstream).

### 3.1 Identity: "instrument, not app"

The subject is a **flight instrument for a volatile asset**. The register is a professional terminal: calm surfaces, hairline structure, disciplined numerals, one accent. Nothing bounces, nothing lifts on hover, nothing is glass. The page should feel closer to `macro.html`/`canada.html` than to a crypto-consumer app — that contrast with the whole crypto-web aesthetic (neon gradients, mascots, confetti) IS the brand risk we take: **the only calm page in crypto.**

- **Surfaces:** flat cards, 10–12px radius, 1px `var(--line)` hairline borders, no shadows at rest, no hover transforms, no gradient sheens. Section eyebrows in the house `.section-title` uppercase-tracked form. (Deliberate deviation, stated: the house *does* sanction a glass-hero idiom — `--mx5-glass-*` on dashboard/canada heroes. This page declines it: the Regime Tape IS the hero, and an instrument reads flat. If review overrules, the sanctioned glass tokens are the only permitted fallback — never a page-local variant.)
- **Palette:** the house theme tokens, unmodified, plus ONE page accent: `--btc: #F7931A` (Bitcoin orange; dark-mode twin ~`#F2A93B`). The accent is **identity-only** — eyebrow ticks, the Regime Tape's price line, the active-shelf marker, small rules. It never encodes direction, risk, or state (bull/bear stay house blue/red with the zh 红涨绿跌 flip; amber stays caution). One accent, strictly rationed, is what makes the page read as designed rather than themed.
- **Iconography:** zero pictographic emoji in page chrome. State is carried by typography, color, and three glyph families only: direction (▲▼), state dots (●), and the `?` help affordance. (The ₿ glyph survives in exactly one place: the hero wordmark.)
- **Type:** house stacks only — Inter UI + system mono for every numeral (`tabular-nums` everywhere a number can change width). Scale discipline: one display size (the hero stance word), one panel-title size, one row size, one caption size. The "weird fonts" complaint dies by subtraction, not by a new font: no third face, no decorative weights, no italic states.
- **Density:** the cockpit is *quiet-dense* — many numbers, all subordinated: every row is `label · state word · small numeral · spark`, never a paragraph. Prose exists in exactly two places on Tier 1: the hero read (≤ 2 sentences) and one footer line per shelf.
- **Motion:** one page-load reveal (ilx draw-on-reveal for the Regime Tape, the house ink idiom) and nothing else. `prefers-reduced-motion` kills it.

### 3.2 The signature element: the Regime Tape

Every remembered page in this house owns one element. The cockpit's is the **Regime Tape**: a full-width, ~220px-tall SSR SVG spanning the hero —

- BTC price (log, 2y window default; the accent-orange line) over **regime-shaded vertical bands** (the engine's regime history: accumulate/bull/distribute/bear as quiet tinted spans),
- a thin **allocation ribbon** underneath (the model's 0–100% BTC line as a filled step series — the honest "what the model actually did", gate-labeled spans included per the Override-Registry contract),
- **event ticks** on the baseline (halvings, cycle top/bottom marks from the ledger — small, labeled on hover),
- the **projection window**, when one exists, drawn as a hatched forward span with the house "windows, not certainties — re-drawn nightly" footnote form.

One picture answers "where are we in the cycle, what has the model done about it, what is it watching next" — the page's entire thesis, drawn. It is also the *reusable* signature: the hub renders mini-tapes (60–90px) of the same form per asset (total-mcap, ETH, SOL…), so the visual language scales into the crypto section and becomes recognizably ours across surfaces. Implementation: extend `lib/illus.py` with a `regime_tape()` form (line + band-spans + step-ribbon + tick marks are all existing ilx primitives or trivial compositions; CSS-var colors give theme + zh flips for free — the thing Plotly structurally cannot do here).

### 3.3 The verdict law: one page, one verdict surface

The stacked verdict layers collapse into **one hero read** (state word + one plain sentence + the model's exposure) and **one "what to do" shelf** (the recommendation, exposure band, levels). The dial dies; the band/score moves into the hero read as a small annotated meter on the tape's edge. The composite chip, verdict badge, and regime scorecard become internal inputs — surfaced only as driver rows in the Why shelf (§4.1 S3). Rule going forward, CI-lintable: **at most one element on the page may tell the user what to do; everything else may only tell them why.**

### 3.4 Alert policy (the operator's sorest point)

Per the falsifiers-background ruling (#3821) and the Alert Center's existence:

- Tier 1 keeps **one** quiet "What changed" line under the hero: calm dot-chips, max 3 + overflow link, ZH-paired, no red, no ⚠. Nothing else on the flagship interrupts.
- The alert **timeline section leaves the page** → Alert Center (`alerts.html`, which already ranks/triages) + the Tier-3 history fold. The vector build keeps *emitting* alerts (engine unchanged); the flagship just stops being the inbox.
- **Staleness/degradation** renders as the `.dtp` self-labeling honesty chip form (calm "hourly feed behind · as of HH:MM" tokens), never a filled red box. The information survives; the alarm styling does not — a stale feed is a data-quality fact, not an emergency the user must triage.
- Watch-conditions ("what would change this read") get a dedicated quiet shelf row (§4.1 S4) in projection-window language — never "falsifier fired/refuted/证伪" (CI-guarded vocabulary).

### 3.5 ZH parity as a design feature

The cockpit treats zh as a first-class rendering, not a translation pass: 红涨绿跌 flips must reach **inside the charts** (ilx CSS-var recolor — the structural fix Plotly blocks), state words get zh-native phrasing (the existing `t()` corpus is good), and the hub's complex board uses the same zh-flip discipline per cell. The crypto crowd this section targets is disproportionately zh-reading; parity is a growth feature, not compliance.

---

## §4 Information architecture — `vector.html`, the Bitcoin command deck

### 4.1 The six-shelf skeleton (Tier-1 body; closed set, CI-enforced)

```
┌─ NAV (shared _site_nav) ─────────────────────────────────────────────┐
│ S1 HERO — THE READ                                                   │
│   ₿ Bitcoin Vector        $price ·24h (live)     as-of chip          │
│   STANCE WORD (display size) + one-sentence read (plain words)       │
│   [ REGIME TAPE — full width: price/regime bands/alloc ribbon/       │
│     event ticks/forward window ]                                     │
│   what-changed line: ● chip ● chip ● chip  · all alerts →            │
│ S2 WHAT TO DO — the single verdict shelf                             │
│   action word · conviction in plain words · target exposure band     │
│   accumulate zone · invalidation level · 90d typical range           │
│   (under gate: the D2-scrubbed one-liner, unchanged by this plan)    │
│ S3 WHY — six driver rows (the entire signal estate, fused)           │
│   Trend & Momentum        │ state word │ spark │ n-of-axes │ ?       │
│   Cycle & Valuation       │ state word │ spark │ …         │ ?       │
│   Liquidity & Flows       │ state word │ spark │ …         │ ?       │
│   Leverage & Derivatives  │ state word │ spark │ …         │ ?       │
│   Network & Miners        │ state word │ spark │ …         │ ?       │
│   Macro Backdrop          │ state word │ spark │ …         │ ?       │
│ S4 WHAT WE'RE WATCHING — projection window + 2-3 watch conditions    │
│   (windows-not-certainties form; quiet "read being updated" chips)   │
│ S5 THE COMPLEX — BTC in context                                      │
│   ETH · SOL · dominance · total-mcap mini-tapes + vs-BTC strength    │
│   → crypto.html (the hub owns depth here)                            │
│ S6 STUDY SHELF — folds (closed by default, macro.html fold idiom)    │
│   Cycle Lab · Derivatives Desk · On-chain Lab · Strategy & Track     │
│   Record · Signal Health → measurement.html receipts                 │
└──────────────────────────────────────────────────────────────────────┘
```

Shelf budgets (hard): S1 ≤ 2 sentences of prose; S2 exactly one action; S3 exactly six rows (a new factor joins an axis's hover receipt or displaces something inside its row — it cannot add a row); S4 ≤ 3 conditions; S5 ≤ 5 tiles; S6 folds unlimited *inside* (Tier-3 territory) but closed at rest.

### 4.2 Tiering contract per element

- **Tier 1 (at rest):** state words, the six axis rows, the tape, one action, watch conditions, mini-tapes. Numbers allowed at rest: price/24h, exposure band, invalidation level, axis micro-numerals (one per row).
- **Tier 2 (hover `?` / popover, ≤80 words, structured):** per-axis receipts — the actual driver list with values (e.g. Leverage row hover: funding percentile, OI/mcap, OKX L/S, basis, liq-cluster distance), base rates in "about X in 10" form, as-of + source + coverage honesty, the D2-compliant gate receipt on S2.
- **Tier 3 (folds + pages):** every current chart section, full histories, methodology, the alert history, strategy backtests, calibration receipts (→ `measurement.html`), the owner-only surfaces (unchanged).

### 4.3 The six axes absorb the ~24 sections (summary; full table in Appendix A)

- **Trend & Momentum** ← momentum card, structure shift, MTF technicals, short-cycle (~8wk) read, impulse sign.
- **Cycle & Valuation** ← cycle clock, valuation anchors (MVRV-Z, Mayer…), cycle-thesis monitor (window language on S4), days-like-today conditioning, halving clock.
- **Liquidity & Flows** ← ETF net flows, stablecoin tide, net-liquidity/BFI liquidity leg, Coinbase premium, taker flow, dry powder.
- **Leverage & Derivatives** ← leverage state, funding/OI, IV (DVOL), skew, CME positioning, impulse-radar pressure states.
- **Network & Miners** ← BFI network leg, hashprice/miner economics, miner cycle & cost basis, holder spread, attention (Wikipedia).
- **Macro Backdrop** ← macro backdrop section, conditional NDX beta, correlation regime, breadth (equity), DXY/real-yield context.

Each axis row shows: axis name (plain words) · state word (shared stance vocabulary) · 90d sparkline of the axis composite · a single micro-numeral where one is meaningful · `?` receipt. The engine already computes per-signal states; the axis fusion layer is presentation-tier composition (§7 E0) — a *display* grouping with printed member lists on hover, NOT a new scored composite (no new authority, no positioning-fusion: the DO_NOT_REBUILD scorecard kill stays honored — nothing here re-scores or re-gates; the existing `master`/`composite_state`/`risk_index` objects remain the only scored things, re-homed visually).

### 4.4 What visibly dies

The dial. The verdict badge. The macro-regime scorecard card. The alert timeline section. The red staleness boxes. The 🔔/🌊/🔥/⚠ emoji register. Standalone chart sections for every driver (→ hovers/folds). Plotly (→ ilx SSR; the two genuinely interactive tools — Time Machine scrubber, price/risk overlay — either re-land inside the Strategy fold via lightweight ilx+JS or move to the charting stack, decided at build by measured weight). Page-local nav/token mirrors (→ shared includes; one `vector.css` page asset replaces the 700-line inline style block — a new public asset is a 3-file change, budgeted in §11).

---

## §5 `crypto.html` — the Crypto Cockpit hub (new flagship #2)

The asset-class dashboard: what a serious investor checks in 90 seconds to know what crypto as a whole is doing and whether anything deserves attention. Same design language as §3 (flat instrument idiom, mini Regime Tapes as the recurring signature, one accent). It is a **Tier-1 primary dashboard** under the doctrine — every panel passes the 5-second test or moves down a tier.

### 5.1 Shelf plan (seven shelves, closed set)

**H1 · Market State hero.** Total-crypto-mcap mini-tape (regime-shaded, 2y) + the asset-class read in one sentence + three stat chips with meaning attached: total mcap (with 30d direction word), BTC dominance % (with "BTC-led / broadening" state word), Fear & Greed (with the house translation, e.g. "crowd is fearful — historically a patient-buyer zone", receipts on hover). One as-of stamp. The hero states the *class* read the way vector.html states the BTC read.

**H2 · The Complex board.** Signal-first table, **top ~20 rows at rest** (expand to ~50 on demand), columns: asset · price · 24h/7d (zh-flip colors) · 90d sparkline · **regime state word** (the per-asset state machine, display-tier) · **vs-BTC strength** (leader/laggard word + small ratio spark) · one-line "why it matters" only when a state changed recently (else blank — silence is a design feature). No supply/FDV/vol columns at rest (hover receipts). This is CMC's table re-imagined as a signal surface: fewer rows, more meaning, zero ads.

**H3 · Money Flows.** The demand side, three tiles: **ETF flows** (BTC + ETH US spot: daily bars + 20d cumulative line, state word "institutions adding / distributing / flat"); **Stablecoin tide** (aggregate stablecoin mcap growth impulse — the roadmap's Tier-1 factor, surfaced here as the class's dry-powder gauge); **Exchange volume regime** (spot volume percentile band — "quiet / normal / frenzied tape"). Each: mini viz + state word + hover receipt.

**H4 · Leverage & Heat.** The risk side, three tiles: aggregate **funding** state (crowded-long / balanced / crowded-short, OKX+bgeo-sourced), **open interest** vs mcap band, **volatility regime** (DVOL percentile + RV cone position — calm / normal / storm). Plus the **altseason gauge** as a labeled dial-free meter: share of top-50 outperforming BTC over 90d, translated ("BTC leads — alt strength narrow" / "broadening — alt season conditions forming"). Display-tier, accrue-forward from day one.

**H5 · Bitcoin & Ethereum lanes.** Two flagship tiles that are *doors*, not dashboards: BTC tile = stance word + exposure line + mini-tape → `vector.html`; ETH tile = the ETH state machine lite (trend/valuation/flows states only, no allocation authority) → future `eth` deep page (Phase E4; until then the tile links to the complex-board row's expanded hover). The hub never re-states more than the flagship pages' hero lines — one source of truth per read.

**H6 · Crypto Equities bridge.** The house's unfair advantage: we already run full equity coverage of the crypto complex (COIN, MSTR, miners, exchanges — prophet states, flow, options structure exist today for several names). A row-tile strip: ticker · prophet/lane state word · 1-line read · link into the existing stock pages. No other crypto site connects coin regimes to the listed-equity complex with real signal machinery behind both. (Exact ticker set from the basket estate at build: `site/basket/crypto.html` + `b-crypto`/`b-crypto-rails` subsector membership.)

**H7 · Catalysts & Calendar.** Messari-pattern, curated-materiality: halving clock (exists), next FOMC/CPI (exists in the macro estate), ETF decision dates, major protocol events (ETH upgrades), large scheduled unlocks for complex-board members only. ≤6 rows visible, each: date · event · one-line "why it matters". No feed-scroll, no news firehose — the News page and Alert Center keep those jobs; the hub links out.

### 5.2 What the hub is NOT (governor, same CI lint as §4)

No per-coin deep pages in v1 (BTC has vector.html; others earn pages by traffic evidence). No news timeline. No portfolio. No 100-row default table. No second verdict about BTC anywhere (H5 quotes vector's hero line verbatim from the shared artifact).

### 5.3 Freshness contract

Nightly full rebuild (universe, regimes, flows, calendar) + the existing live-quotes lane (VPS 60s/5-min timers with the hourly Action as fallback) patches prices/24h client-side. Wiring is free by construction: `build_live_quotes.py` auto-discovers every `data-sym="X-USD"` attribute the built site emits, so the complex board's rows join the live set just by rendering; `CORE_CRYPTO` gains ETH-USD/SOL-USD only if weekend-always coverage is wanted independent of page markup. Every shelf carries exactly one honesty chip when its data is older than its cadence promise (the `.dtp` idiom — never a red box, per §3.4).

## §6 Satellite pages — verdicts

Census facts: `vector_allocation.html` is not even a separate builder — it is `build_allocation_page()` inside `scripts/build_vector.py:2899-2966` (144 KB rendered, 295-line template). `btc_strategy.html` has its own builder (`scripts/build_btc_strategy.py`, 65 KB rendered) and — alone in the family — already links `theme.css` correctly. `strategy_btc_trend.html` is an unrelated page from the generic `strategy_detail.html.j2` family, linked only from the Strategies hub.

### 6.1 `btc_strategy.html` — MERGE into vector.html, then retire the URL

- **What it uniquely owns (all worth keeping):** the tabbed Cycle-Timer vs Risk-Allocation strategy comparison; **dual with/without-gate metrics** (the W1 N7 honesty contract — gate-baked marketing numbers were a named defect of the old world); the **leverage honest-outcomes table** (including blown-account rows — rare, genuinely trust-building content); projected cycle-pivots table; self-contained inline-SVG equity curves (no chart-lib dependency — ideal for a fold).
- **Verdict:** all of it becomes the **Strategy & Track Record fold** (S6) on vector.html, presented spvector-style (scorecard tiles → equity curves → rule-book → honest caveats). The page's phase banner dies (S1's tape already shows cycle position). `build_btc_strategy.py`'s computation moves to a module the vector build calls (one process, one as-of). The URL ships a redirect stub; nav entry removed (§10.1).
- **Why merge rather than keep:** it is a descriptive page with no decision surface (census: "no decision card at all — purely backtest"), 65 KB of content that is exactly what the doctrine calls Tier-3 depth for the flagship. Two pages splitting the same story ("what does the model do" / "how has it done") is the fragmentation the operator is complaining about.

### 6.2 `vector_allocation.html` — CONTENT PROMOTED to the hub, page retired

- **What it uniquely owns:** the **BTC · ETH · alts · cash split** (reconciled so total crypto exposure = `alloc_optimal` — that reconciliation logic must survive the move verbatim); the **alt-season gauge** (ETH/BTC cycle read); the ETH/BTC ratio chart; the 3×3 cycle-regime × alt-season **allocation grid**; the risk-budgeted Kelly card. What it duplicates: the entire recommendation card (verbatim the same `rec` object as vector.html) and the blackout banner.
- **Verdict:** the unique content is precisely the **embryo of crypto.html** — it becomes the hub's **Allocation shelf** (slotting after H4: the class-level "how the model splits BTC/ETH/alts/cash", plus the alt-season gauge merging into H4's meter). The duplicated recommendation dies (one-verdict law, §3.3: BTC's verdict lives on vector.html; the hub's H5 BTC tile quotes it). The page retires with a redirect stub → `crypto.html#allocation`. Drift bugs die with it (no tabular-nums, dead topbar CSS, one lonely `qmark`).
- **Sequencing note:** this retirement happens in the wave that ships the hub, not before — the redirect must have a live target.

### 6.3 `strategy_btc_trend.html` — leave in place, cross-link

Different template family (`strategy_detail.html.j2`), different funnel (the Strategies scorecard hub owns it), not in the global nav. Out of scope for this program except: the new Strategy fold links to it as the "trend strategy detail" receipt, and its own header gets a link back to vector.html. Revisit dedup only if the Strategies-hub family itself is ever reworked.

### 6.4 `spvector.html` — untouched (S&P product, already clean, 264-line template). It is also the proof-of-form for §6.1's merged fold: recommendation → why → chart → scorecard → rule-book → honest notes, in ~260 lines.

## §7 Engine program — data layer, new engines, sequencing

### 7.1 What exists (census-verified, 2026-07-29)

The BTC vertical is deep and healthy: `btc_signals.compute_all()` emits a **197-column daily matrix** (4,334 rows, 2014-09→today, `data/vector/signals.parquet`) fed by 15+ live collectors; a fan of display-only context legs (regime scorecard, net-liquidity, leverage cascade, impulse radar, intraday CVD, DAT chip, correlation lean) each carries its own falsifier/ledger; the Override-Registry apply layer governs allocation; weekly `calibrate_vector` is the house-rule gatekeeper (DSR, purged folds, block-bootstrap, Brier — via `engine.validation` + trial ledger). The intraday estate: a */30-min flash-crash sentinel (state-diff → Telegram + rebuild on change only), hourly/VPS live quotes, OKX hourly taker-CVD accrual. **What does not exist:** any live non-BTC engine ("There is NO live ETH engine" — `eth_vector_phase0.py` docstring), any universe/dominance/breadth machinery beyond one `alt_cycle` try/except card (ETH/BTC + SOL beta + CoinGecko dominance) inside `build_vector.py:3446-3459`, and any published BTC-options artifact despite `collectors/deribit.py` already computing ATM IV term structure, 25Δ skew/RR, put/call OI, max pain, and a GEX estimate over the ~950-instrument chain every night.

Three data-quality repairs surfaced by the census (fold into W4; none blocks design work):

1. **`checkonchain` series are ~6.5 weeks stale** (`reserve_risk`, `vdd_multiple` end 2026-06-13 — one-time backfill, no daily adapter). Fix: daily append from bgeo (`reserve-risk` endpoint exists in its 614-endpoint catalog) within the 15/day budget, or an explicit "backfill-vintage" honesty chip on any surface that shows them.
2. **`data/dat_holdings.json` is absent and never git-tracked** — `btc_dat.py` degrades cleanly, so the MSTR/DAT chip has silently been in its `ok:false` state. Operator decision: wire a maintained source for it or retire the chip (it is one of the §4.3 Macro-axis hover receipts either way, not a shelf).
3. **`research/BTC_REGIME_FRAMEWORK.md` is cited by `btc_regime.py` but does not exist** — repair the docstring pointer to the surviving docs (BTC_VECTOR_FIX_MASTERPLAN / PROBLEM_AUDIT).

### 7.2 Data layer — the production stack (repo-verified ∪ 2026-07 web census)

**Standing exclusions (verified twice, do not revisit):** Binance (HTTP 451) and Bybit (403) are US-geo-blocked including public market data and GitHub runners; Glassnode free tier has no API; Coinglass/Laevitas are paid-only; CryptoCompare and CoinCap **retired their free tiers in May/July 2026** — both are dead as fallbacks; pytrends is an archived corpse (Wikipedia pageviews is the house attention source, already live).

| Family | Primary (status) | Notes & fallback |
|---|---|---|
| BTC OHLC | `collectors/coinbase.py` daily+hourly (live, 2015→) + Yahoo tail to 2014 | unchanged; Kraken public as researched cold-spare (720-candle cap) |
| Deep on-chain (MVRV, active addresses, hashrate, supply) | CoinMetrics Community (live, 2010→, keyless) | ⚠ **licensing check required**: 2026-07 census reads Community data as CC BY-NC — see §12.2 risk 8. bgeo carries same-family metrics if displayed series must re-home |
| SOPR-class / cohort / ETF / funding / OI | bgeo aka bitcoin-data.com (live; 10/hr, 15/day quota, 12 used; 4y rolling window, archived-forever parquet) | quota discipline unchanged; new cockpit adds **zero** bgeo calls; possible +1–2 for repair #1 |
| On-chain backfills | checkonchain chart-JSON (one-time, 2011→) | repair #1 above |
| Derivatives | OKX (funding, OI, L/S ratio, taker CVD — live, US-OK) + Deribit (DVOL, full chain — live) | the entire §5 H4 shelf runs on these two, already collected |
| ETF flows | `collectors/farside.py` (live since 2024-01) + bgeo `etf-flow-btc` cross-check | ⚠ scrape-shaped: fresh census hit 403 bot-protection on farside.co.uk — treat as fragile-by-nature; SoSoValue's ETF API is the researched replacement candidate; degrade path = bgeo BTC-unit series + honesty chip. Never block a shelf on it |
| Stablecoins / peg | DefiLlama (live, keyless, no rate limit, clean ToS) | best-in-class; also the peg-veto source for the roadmap item |
| Sentiment | alternative.me F&G (live, 2018→, explicitly commercial-OK) | — |
| Macro context | FRED/Yahoo/Treasury/COT stack via `btc_inputs.load_all()` | **zero new fetcher work** — already merged onto BTC's calendar |
| **Universe (NEW)** | CoinGecko free: `/coins/markets` top-250 (1 call/day), `/global` (1 call/day), `/coins/categories` (optional 1/day) | free tier now 365-day history + ~30 req/min + attribution — fine for a *snapshot* universe; depth comes from our own accrual (repo-is-the-database law: archive every snapshot to `data/coingecko/*.parquet` from day one). Fallback: CoinPaprika keyless (the last clean free backup standing) |
| **ETH/SOL real OHLC (NEW)** | extend `collectors/coinbase.py` to ETH-USD/SOL-USD daily candles (same venue, same adapter, listing-date depth) | replaces the yahoo close-only series that today forces the brain to synthesize wickless candles (#3722); also feeds vs-BTC ratio series. charting-app's `refresh_crypto_ohlc.py` (#3869) already proves the Coinbase-candle path nightly on the VPS |

**The depth honesty rule** for everything new: free aggregator history is shallow (CoinGecko 365d) and derivatives history starts ~2021 — so every new class-level series follows the accrue-forward pattern (display now, archive daily, calibration eligibility only when depth exists). This is already the house's stated law; the cockpit just inherits it.

### 7.3 New engines (all display-tier at birth; promotion only via gauntlet)

- **E0 · Cockpit contract** — `build_vector.py` emits `site/crypto_cockpit.json`: the shared read consumed by the hub's H5 BTC tile, the landing card, and (later) the brain lens — hero stance line, exposure, axis states, as-ofs. One process, one as-of (kills re-derivation drift by construction). Also the §4.3 axis-fusion *presentation* map (six axes → member signals) lives here as data, so page and hovers render from one source.
- **E1 · `engine/crypto_universe.py`** — nightly CoinGecko snapshot → top-N table rows (price, mcap, 24h/7d, 90d spark from accrued history), archived parquet. Includes the CMC-pattern *category* tags only if the categories call proves stable; otherwise skip (governor: no taxonomy empire).
- **E2 · `engine/crypto_market_state.py`** — class-level reads: total-mcap regime bands (same band vocabulary as BTC's tape, computed by the same primitives), **BTC dominance** series + state word, **breadth** (% of accrued top-50 above their own 200d — starts publishing when ≥200d of universe accrual exists; until then the shelf shows the honest "building history since <date>" chip), **altseason meter** (share of top-50 outperforming BTC over 90d — same accrual caveat).
- **E3 · `engine/eth_state.py` (+ SOL)** — the "vector lite" per-asset state machine: trend votes + drawdown/risk band + vs-BTC relative strength, reusing `btc_signals`' price-only builders exactly as `eth_vector_phase0.py` prototyped. **States and words only — no allocation, no recommendation** (authority stays BTC-only until a gauntlet says otherwise). Feeds H2 state words and H5's ETH lane.
- **E4 · BTC options artifact** — publish the already-computed Deribit options structure as `site/btc_options.json` (IV term structure, 25Δ skew, put/call, max pain, GEX estimate + the gamma-flip level once the roadmap item lands). Fold-level surface (S6 Derivatives Desk) + H4 volatility tile input. Zero new collection.
- **E5 · Alt-season/allocation carry-over** — port `build_allocation_page()`'s unique computations (BTC/ETH/alts/cash reconciliation, alt-season gauge, regime×season grid) into the hub build (§6.2).
- **E6 · Crypto-equities bridge data** — no new engine: H6 reads existing basket membership (`b-crypto`, `b-crypto_rails`), rotation ranks, and prophet/gex artifacts for those tickers (§8).

### 7.4 The calibration backlog is already adjudicated — sequence it, don't reinvent it

[VECTOR_FACTOR_ROADMAP_2026.md](VECTOR_FACTOR_ROADMAP_2026.md) stands as the signal-quality program of record: **methodology gates first** (purged/embargoed CV replacing the leaky split; orthogonalization+VIF into composite_state; probability-calibrated conviction; block-bootstrap+DSR on the backtest), then the near-zero-pipe Tier-1 factors (RV cones + vol-of-vol; gamma-flip distance; LTH/STH spread; stablecoin growth-rate tide; Wikipedia attention factor; peg-deviation veto; hashprice anchor; taker-CVD divergence when the feed matures). Its Tier-3 blocked list (exchange netflow et al.) remains binding. This masterplan adds exactly one scheduling opinion: the **methodology-gate wave runs concurrently with the UI waves** (different files, different reviewers — zero collision), because §4's six-axis rows get *stronger receipts* the moment conviction is probability-calibrated. Nothing in the UI program waits on it.

### 7.5 Budget & ledger accounting

- **Nightly delta:** E1+E2+E3 are ~3 HTTP calls + pandas over a 250×730 frame — seconds. E4 is a JSON emit of computed data. ilx SSR tapes are template-time SVG (the house already renders 7+ ilx charts on canada.html inside budget). Measured-delta reporting per wave is §0.8; the expected total is **< 2 minutes added** to a 135-190-minute engine job, none of it on the render-lane path.
- **Ledgers:** cockpit state history (`data/crypto/universe/*.parquet`, class-state ledger) advances **only** in nightly; sentinel/intraday lanes stay price-only and discard data writes (standing law). New forward surfaces (altseason meter, breadth) get ledger rows from day one so future promotion has a record to argue from.
- **R2:** universe accrual parquets stay small (KB/day); no R2 need in v1. If per-coin history ever fattens (50 coins × minutes bars), that lives in R2 per the render-budget law — pre-declared here so nobody "temporarily" commits it to the repo.

## §8 Neural-web integration — what feeds the cockpit, what the cockpit feeds

Census-verified integration contracts. One governing constraint up front: **the lobe roster is FULL (66/66, operator-capped 2026-07-17)** — the cockpit mints no lobe; it *reads* existing artifacts and registers its own artifacts in `config/synapse.yml` with honest `tier: display` entries, inheriting the site's authority vocabulary (display → shadow → confirmer → scored) without asking for authority.

### 8.1 Inbound — what feeds the cockpit (all existing, zero new fetchers)

| System | Artifact / API | Cockpit use |
|---|---|---|
| BTC engine estate | `signals.parquet`, `regime_latest.json`, ledgers, `gate_state()` | everything on vector.html (§4); the hub's H5 BTC tile via E0's shared contract |
| Macro inputs | `btc_inputs.load_all()` (DXY, real yields, credit, VIX, gold, SPX/NDX, M2, net-liq, COT — already index-aligned to BTC's calendar) | S3 Macro-axis row + receipts; zero new work |
| `engine/market_drivers.py` | `snapshot()` → `latest.json["market_drivers"]` + `site/live/market_drivers.json` (has a native `crypto_liquidity` driver with bilingual labels) | S1/H1 "what's moving the tape" hover receipt: when primary=`crypto_liquidity` the read is BTC-led; otherwise it names the macro force leaning on crypto |
| `engine/cross_asset.py` | absorption ratio + lead/lag across 6 legs (Crypto/BTC-USD already one of them) | the "is BTC its own trade or one global bet right now" receipt on the Macro axis — a read no competitor has |
| Options estate | `collectors/deribit.py` structure (computed nightly, unpublished) + equity `gex_state/{COIN,MSTR}.json` | E4 publishes the BTC artifact; H6 reuses the equity options reads as-is |
| Prophet | `site/prophet/plans|states/*` (COIN-BULL-20260702 precedent) | H6 shows prophet states for crypto-complex equities verbatim; **native-coin prophet coverage is a pre-scoped follow-on**: a crypto conviction lane emitting the same `buy[]` contract as `us_standouts_buy_lane` plugs into `prophet_bridge.originate_plans()` unmodified (BULL-only filter noted) — display-tier, own adjudication, not in v1 |
| Live quotes | `site/live/quotes.json` (VPS 60s/5min lanes; `CORE_CRYPTO=[BTC-USD]`; **symbols auto-discovered from any `data-sym="X-USD"` markup in the built site**) | the hub's H2 top rows and H5 tiles emit `data-sym` attributes and get live patching for free; extend `CORE_CRYPTO` only if weekend coverage for ETH/SOL is wanted before the pages exist |
| charting-app (Terminal) | Coinbase-ws primary + OKX-fallback live crypto feed; `refresh_crypto_ohlc.py` nightly Coinbase candles; ~26-symbol crypto catalog with zh names | cross-product consistency: the cockpit's universe naming/zh labels should match `ingest/macro_catalog.py`'s crypto rows; Terminal remains the intraday charting home the cockpit links into for real candles |
| Alert estate | Alert Center (`alerts.html`) + `data/vector/alerts.jsonl` + sentinel | §3.4: the flagship demotes, the Center absorbs; sentinel pattern (state-diff, quiet-when-unchanged) is the template if a class-level tripwire is ever commissioned (own adjudication) |
| Neural web | `site/neuralwebdata/*.json`; `brief_context.btc_slice()` (capped 4KB context packet, purpose-built) | the AI-lens path below; optionally the hub's H1 hover can cite the NW liquidity-plumbing read as a receipt |

### 8.2 Outbound — what the cockpit feeds back

- **`site/crypto_cockpit.json` (E0)** registered in synapse as `tier: display`, consumed by: landing/product cards, the hub, and later lenses. The contract is the *only* way other surfaces quote crypto reads (no re-derivation).
- **AI narration:** extend the existing **`btc` lens** in `master_brain.LENSES` to include the class-level state (universe/dominance/flows states from E2) in `gather_btc_state()` — NOT a fourth lens in v1 (cheaper, and `site/btc_brief.json` already renders on-site via aibrief.js). Constitution honored as-is: Articles 1–3 (no origination; scored-path perimeter; evidence floor) — the lens narrates calibrated keys and may only de-escalate.
- **Confluence graph:** if cockpit artifacts appear as nodes, every edge carries `display_only=True` per the standing law; promotion needs its own `qual_ladder.yml` gauntlet entry. Not in v1.
- **WRI / book model:** crypto positions already exist in the watchlist-risk world (per #3538); the cockpit links out rather than duplicating — a "your crypto exposure" personal shelf is explicitly deferred to the WRI program's own roadmap (§9.3).

## §9 Competitor read — adopt / adapt / skip

Fresh 4-competitor census (2026-07-29, web-verified where fetchable) + the standing recon ([VECTOR_PROVIDER_RECON.md](VECTOR_PROVIDER_RECON.md)). The strategic finding, confirmed independently by both lanes: **no incumbent ships interpretation.** CMC is the data supermarket; Blockchain.com ships literal cycle signals (Pi Cycle, MVRV, NVT — metrics *built* to call tops/bottoms) as bare, unannotated line charts; Messari **retired its free/Pro self-serve tiers in 2026** (enterprise sales-gated, ≈$5k+/yr); CryptoQuant owns the best interpretive pattern in the field (the Bull-Bear cycle composite) and buries it in a several-hundred-chart library behind a jargon wall. "State + stance + plain words with the receipt one hover away" — the house doctrine — has **no direct precedent in any of the four**. That is the entire positioning: we do not out-supermarket CMC; we ship the read.

### 9.1 Per-competitor verdicts

| Competitor | What they own | What we take | What we refuse |
|---|---|---|---|
| **CoinMarketCap** | Universe breadth (rankings, 206 categories, ETF tracker, heatmap, F&G), 30+ languages incl. zh | **Adapt:** sparkline-in-row tables (signal-first, top-N not 10k rows); ETF-flow tracker as a first-class shelf; a treemap-style breadth read (ilx, not a widget farm); their *demote-TA-to-dedicated-pages* pattern (validates our tiering); zh as growth surface | The supermarket itself; ads/affiliate clutter; community vote sentiment (unweighted crowd noise); CMC-AI-style "LLM narrates anything" (violates the de-escalation-only law) |
| **Blockchain.com** | On-chain telemetry commoditized (~35 charts, 5 sane categories; free Charts API `api.blockchain.info/charts/*` JSON/CSV) | **Adopt:** their taxonomy (Popular/Cycle/Mining/Network/Signals) as the On-chain Lab fold's internal order; their one-metric-one-URL linkability idea → our Tier-3 folds get stable anchors; the Charts API as a *backup* on-chain source | Bare-chart presentation (the anti-pattern this whole plan exists to beat); explorer-level tx/address tooling (not our job; link out) |
| **Messari** | Standardized cross-asset taxonomy; token-unlock schedules; curated "Key Developments" event feed; Copilot (RAG, citations) | **Adapt:** unlock/catalyst calendar as a hub shelf (BTC halving clock exists; add ETH/major-unlock + macro events from our own calendar estate); "consistent anatomy across assets" — our hub tiles and future per-asset pages share one template; their *human-curated materiality filter* for events is our editorial bar for the What-Changed line | Enterprise gating (our free tier is the funnel); research-report business; building our own fundraising/governance DB (no edge, huge upkeep) |
| **CryptoQuant** | Labeled exchange/miner/whale flows (the true moat — proprietary entity tagging); Bull-Bear P&L composite; alert thresholds; QuickTake community | **Adopt the pattern, rebuild from free parts:** their P&L-Index-vs-365dMA mechanical regime flip is the best one-number state in the field — our own valuation axis (MVRV-Z + NUPL + SOPR, all free via CoinMetrics/bgeo/checkonchain) already computes the ingredients; surface OUR cycle state with a mechanical, hover-documented rule. Threshold alerts → we already have the Alert Center + sentinel | Chasing labeled exchange-flow fidelity (DO_NOT_REBUILD-adjacent: the factor roadmap marks exchange netflow BLOCKED on free paths — do not promise that panel; if ever shown, it is bgeo-sourced, "directional, best-effort" honesty-chipped, display-only); a 500-chart library; per-exchange breakdowns |

### 9.2 Feature-gap scoreboard (what the cockpit ships that no competitor has)

1. **A stance on load** — one plain-words read + action posture above the fold (nobody does this; CryptoQuant's composite is the closest and it's buried).
2. **Fused market + on-chain + derivatives + macro** in one six-axis read (CMC has no on-chain; Blockchain.com has no market structure; CryptoQuant has no macro backdrop; none fuse).
3. **Honest windows, receipts, and track record** — projection windows re-drawn nightly, calibration receipts on measurement.html, a strategy scorecard with both-sides framing (competitors publish predictions never graded, or grade nothing).
4. **Bilingual parity with zh-native color/stance conventions** (CMC translates strings; nobody flips 红涨绿跌 inside charts).
5. **Quiet-by-design** — alert demotion, one verdict surface, no ads. The "only calm page in crypto" position (§3.1) is a *structural* moat: every incumbent's business model (ads, upsell, chart-count-as-value) forbids calm.

### 9.3 What we deliberately do NOT build (standing, to kill scope creep)

- No explorer (tx/address lookup) — link to mempool.space/blockchain.com.
- No 10,000-coin universe — top ~50 by mcap + watch-worthy adds, curated; the long tail is CMC's business, not a signal surface.
- No portfolio tracker in v1 (WRI already models crypto in the book; revisit only as a WRI surface, not a cockpit clone of CMC portfolio).
- No community/UGC layer (QuickTake-style) — curation cost, liability, off-doctrine.
- No fee-estimator utility widget (mempool.space owns it; a cockpit is for investors, not transactors — at most a Network-axis hover stat).
- No paid data vendors (CryptoQuant/Glassnode/CoinGlass) — the free-source stack (§7) covers every shelf we commit to; anything only purchasable stays unpromised.

## §10 Bilingual reach, SEO & the crypto-crowd funnel

### 10.1 Nav promotion (the structural move)

Today: `Other Assets ▾ → Bitcoin Vector ▸ (Overview / Allocation Strategy / BTC Strategy)` — two levels deep, invisible to a crypto-first visitor. Ship a **top-level `Crypto` group** in `_navlinks.html.j2`, mirroring the market-group anatomy users already know from US/China/HK/Canada/International:

```
Crypto ▾
  Crypto Cockpit        crypto.html        Market state · flows · leverage · complex
  Bitcoin Vector        vector.html        Regime · cycle · what to do
  Strategies            (Strategy fold anchor / strategies row)   Backtested · graded
  Crypto Equities       (link into existing basket/sector estate) COIN · MSTR · miners
```

"Other Assets" keeps Commodities/Forex/Bonds; the Bitcoin Vector submenu there is removed (single nav home). All old URLs live forever (§0 gate 12).

### 10.2 SEO & entry surfaces

- Each page keeps a hand-tuned `_seo_head` pair (EN/ZH): vector.html already carries "Bitcoin's regime on one page — plain-word stance, updated daily"; crypto.html ships the class equivalent ("Crypto market state — dominance, flows, leverage and what to do about it"). Honest descriptions, no "validated" (CI), no yield-y hype vocabulary.
- The redirect stubs from merged pages (btc_strategy, vector_allocation) carry `rel=canonical` to their new anchors so accrued link equity transfers instead of 404ing.
- The landing page's product grid and the products pages get a Crypto Cockpit card in the same PR wave that ships the hub (funnel law: the build surface follows the funnel — entry points wired is an acceptance gate, §0.1/§0.12).
- zh positioning is a feature, not a translation: the zh crypto audience is underserved by exactly the incumbents censused (Blockchain.com has no zh at all; CMC translates strings but keeps Western color conventions). We ship 红涨绿跌 *inside* charts (ilx), zh-native stance vocabulary (the existing corpus), and zh SEO descriptions written as copy, not output.

### 10.3 Tiering (free vs Pro)

The cockpit family launches **fully free** — it is an acquisition surface, and the house free-tier program already prices the funnel this way (free tier drives registration; Pro sells depth elsewhere: Mastermind, Terminal, screeners). Two pre-committed Pro hooks for later, both additive: (a) per-asset expanded histories/labs beyond BTC, (b) cockpit signals inside Mastermind/Terminal (brain narration, watchlist risk). Nothing in v1 is gated — a gated flagship cannot recruit the crowd it exists to recruit.

## §11 Build phasing — waves, model routing, budget

Every wave: fresh branch off `origin/main` → PR with the §0 gates inlined in the build prompt → visual proof in the PR body → `merge-on-green` label → live verification. Design *choices* at Opus+ (`designer`) or the main loop; implementation by Opus `builder`; adversarial review by Opus `reviewer`; commissioning session merges (no child self-merge on first-pass flagship UI). Sonnet appears nowhere in the build path (census work is done).

| Wave | Ships | Notes & gates beyond §0 |
|---|---|---|
| **W0 · Design pinning** (1 PR, small) | Static HTML mockups of vector.html's six shelves + the hub's seven, light+dark+zh screenshots committed to `mockups/refs/crypto_cockpit/`; the E0 `crypto_cockpit.json` contract stub; the shelf-count CI lint (warn-only); repair #3 (dead docstring pointer) | Mockups-first is the standing quality-bar law; a build wave may not start until its mockups are committed and approved against §3/§4 in the commissioning session. The `regime_tape()` ilx form is prototyped here on real data (the one technically-risky visual) |
| **W1 · vector.html rebuild** (the flagship) | theme.css linkage (kill the local token fork + `_vector_polish` dependency for this page); six-shelf skeleton + verdict collapse + alert demotion per §4; Regime Tape hero; Plotly→ilx for the static charts; Strategy & Track Record fold absorbing `build_btc_strategy.py`'s computations (module-ized, dual-gate metrics + leverage table intact); 1500px rail; shelf lint armed (fail) | Extra gates: rendered weight target **< 180 KB** (from 376) measured in the PR; zh flip verified *inside* charts (computed-style + screenshot); Time Machine + strategy chart stay functional inside folds (regression screenshots); `btc_strategy.html` continues rendering unchanged this wave (no URL dies before its replacement is live) |
| **W2 · Hub + promotion** | `crypto.html` v1 (H1–H7; breadth/altseason ship with honest "building history since <date>" chips); E0/E1/E2 engines + universe accrual parquets; allocation-shelf migration from `vector_allocation` (§6.2); **redirect stubs** for `btc_strategy.html` + `vector_allocation.html`; nav promotion (§10.1); landing/products cards; SEO heads; `data-sym` live wiring | Extra gates: CoinGecko attribution rendered where universe data shows; measured nightly delta reported (§7.5 expects < 2 min); redirect stubs verified live (curl + browser) before the old nav entries disappear |
| **W3 · Engines deepen** | E3 (ETH/SOL state machines, states-only); E4 (`site/btc_options.json` + Derivatives Desk fold); ETH/SOL Coinbase OHLC collector; repairs #1 (checkonchain daily append or vintage chips) and #2 (DAT source decision → operator); brain-lens extension (§8.2, `btc` lens gains class-state) | Extra gates: every new state machine's coverage disclosure passes the plain-word-null form; brain-lens diff shows *narration-only* changes (Article 1 lint clean) |
| **W4 · Polish & proof** | Mobile pass (375px crops for every shelf), zh copy QA sweep (native-plain, not translated-plain), measurement.html receipt links wired from S6, before/after page-weight + Lighthouse numbers in the PR, the "stance on load" 5-second test recorded with a fresh reader | Also the retrospective: does any shelf violate its budget in practice? The governor lint gets its final thresholds here |
| **Concurrent lane · signal quality** (separate cadence, separate reviewers) | The FACTOR_ROADMAP program: methodology gates first (CPCV, orthogonalization+VIF, probability calibration, bootstrap+DSR), then Tier-1 factors, each its own PR with pre-registered gates | Zero file collision with W0–W4 (engine/calibration files vs templates/builders). UI never waits on it; §4's receipts strengthen as it lands |

**Not scheduled (pre-scoped, needs its own adjudication):** native-coin Prophet lane (§8.1), class-level intraday tripwire sentinel, per-coin detail pages (traffic-gated, §5.2), WRI personal-exposure shelf (§8.2), SoSoValue ETF-flow migration (only if farside degrades, §7.2).

**Sizing honesty:** W1 and W2 are each a full flagship build — expect each to be a multi-PR session with mockup-diff iterations, not a one-shot. W0 exists precisely so that iteration happens on cheap mockups instead of on the live template.

## §12 Risks & standing-kill compliance

### 12.1 Standing kills and rulings this plan is built around (verified against the registry)

| Standing rule | How this plan complies |
|---|---|
| **Override-Registry program closed (D1–D5)** — no sizing-authority changes without a new recorded owner decision | Pure presentation + additive display-tier engines. S2 renders the *existing* `rec`/gate objects; the D2 scrub (subscriber-facing "proprietary cycle timer" wording) is preserved verbatim; owner-only surfaces untouched |
| **No new override gates laundered into `allocation()`** (DO_NOT_REBUILD) | No allocation-code changes anywhere in the plan |
| **No composite regime scorecard fusing positioning into a verdict; positioning-fusion ILLEGAL** (MSP-R2) | §4.3 axis rows are display *groupings* of already-scored objects with printed member lists — no new scored composite, no positioning keys fused into any regime score; the hub's state words are per-metric bands, not a fused super-score |
| **Falsifier language never front-facing (#3821)** | §3.4/§4.1-S4: windows + watch-conditions vocabulary; verdict-grade material stays on measurement.html below the fold |
| **Gauntlet = promotion gate, not build gate** | Every new engine (universe, breadth, dominance, altseason, ETH states) ships display-tier with plain-word coverage disclosure; nothing new ranks/sizes/gates money; roadmap Tier-1 calibration work stays under its own pre-registered gates |
| **LLM de-escalation only** | No new LLM surface; master-brain narration keeps reading stamped engine keys (both raw + final alloc per the contamination-map contract) |
| **"validated" CI ban · zh title-attr ban · annotation line-start law · template/site pairing** | Inherited as build-wave gates (§0.5/§0.7; CI-guarded already) |
| **Debrand law (#663)** | Competitor names stay out of user-facing copy; cockpit copy names no vendor |
| **Scrape kills stand** | §7 data stack is API-JSON only; the one scrape-shaped source family (ETF flow aggregator pages) is explicitly resolved onto bgeo's tested `etf-flow-btc` endpoint instead |

### 12.2 Top risks, ranked, with mitigations

1. **Section-creep regression (the proven failure mode — happened after #1597).** Mitigation: the CI shelf-count lint (§2.3) ships in W1 *with* the redesign, not after; the disposition table (Appendix A) leaves no orphan section to "temporarily keep".
2. **bgeo free-tier fragility (15 req/day, 4y rolling window, per-IP).** Already-managed pattern (archive-forever parquet; 429 soft-fail; budget of 12/15 calls). New cockpit adds ZERO bgeo calls (universe comes from CoinGecko/CoinMetrics; ETF flow already in the budget). If bgeo dies, panels degrade to honest "source paused" chips — display-tier surfaces are allowed to go quiet, never to lie.
3. **Render-budget breach.** All new nightly compute is O(seconds-to-a-minute) pandas on small frames (top-50 universe × 2y daily). The heavy items (checkonchain backfills, ilx tape rendering across pages) are one-time scripts or per-page SSR already priced like existing pages. §11 carries a measured-delta gate per wave (§0.8).
4. **Plotly→ilx conversion breaking a chart the strategy fold genuinely needs interactive.** Pre-decided escape hatch (§4.4): Time Machine + price/risk overlay may stay JS-interactive within the fold using the existing lightweight pattern (vector_chart.js) or move to the charting stack — decided by measured weight at build, never by reverting to Plotly page-wide.
5. **CoinGecko free-tier throttling** (universe source). One call/day for top-250 markets + one for global stats is far inside the public free tier; failover to CoinCap/CoinPaprika shapes is specced in §7; and the complex board's row count (20–50) means even a cached-yesterday universe stays honest with an as-of chip.
6. **Scope-bleed into a per-coin empire.** §5.2/§9.3 governors + the nav ships exactly two new destinations (hub; strategies anchor). Any per-coin page proposal returns to adjudication with traffic evidence.
7. **The redesign shipping beautiful-but-stale reads** (the classic decoupled-artifact trap). The cockpit JSON contract (§7 E0) is emitted by the same build_vector run that renders the page — one process, one as-of; the hub's BTC tile quotes the same artifact (no re-derivation drift, the `rec.suppressed_by_blackout` single-stamp pattern generalized).
8. **Coin Metrics Community licensing.** The 2026-07 source census reads CM Community data as CC BY-NC 4.0 (non-commercial) — and CM series (MVRV lineage) sit under displayed valuation reads today. Unverified against CM's current terms; W2 carries a one-hour verification task. If NC binds: displayed valuation series re-home to the bgeo/checkonchain lineage (already spliced to 2011 on disk), CM demotes to internal cross-check — a data-plumbing swap, not a design change. Until verified, no NEW surface may make CM its sole displayed source.
9. **Farside ETF-flow scrape fragility.** The live collector works today; the fresh census hit bot-protection on a direct fetch — assume it can break any week. Degrade path pre-declared (§7.2): bgeo BTC-unit series + honesty chip; SoSoValue researched as the structural replacement. A broken ETF panel shows "source paused", never a blank or a lie.

## Appendix A — current-section disposition table (census-complete; no orphans)

Every content block of today's `vector.html.j2` (line refs at HEAD) mapped to exactly one new home. "Receipt" = a Tier-2 hover on the named S3 axis row; folds are the S6 Tier-3 shelves. Nothing may survive "temporarily" outside this table — that is how 14 sections became 24.

| # | Today (lines) | Disposition |
|---|---|---|
| 1 | Nav (hand-styled via `_vector_polish`) 538–557 | Markup stays (`_navlinks` + standard chrome); styling source becomes `theme.css` (kill the shim dependency for this page) |
| 2 | Hero: ₿ Vector brand + tagline + as-of 705–709 | → **S1** rebuilt: wordmark (only ₿ survives; gradient text-clip dies), stance word, one-sentence read, as-of chip |
| 3 | Command Center 711–773: needle dial · price/24h · composite stance · grade badge · crowding/froth pills · headline · driver chips · 3 stat tiles | Dial **killed** (band+score become a small annotated meter on the tape edge). Price/24h → S1. Composite stance + grade badge → absorbed into S1's read (words, not chips). Crowding/froth → Leverage-axis receipt (+S4 watch condition when extreme). Driver chips → S3 rows' receipts. Risk-level tile → Leverage/Cycle micro-numerals; expected-dip tile → S4 outcomes module; allocation tile → **S2** |
| 4 | Recommendation card 774–817 | → **S2** intact (the single verdict surface); key-risk ⚠ banner restyled to a quiet risk line inside S2 (one per panel) |
| 5 | What-changed chips 819–829 | → **S1** quiet line, ≤3 chips + overflow link to Alert Center |
| 6 | Macro-regime scorecard fold 831–949 (gauge, tiers, factor chips, STAY-AWAY/DOUBLE-DOWN, context legs) | Fold **killed**. Band → S3 Macro-axis state input; cluster flags → S4 watch conditions when active (quiet vocabulary); context legs (netliq/leverage/mNAV/IBIT) → axis receipts; full scorecard + ledger → measurement.html receipt link |
| 7 | Allocation + gate banner + sizing minis + catalyst + forward-cones card 951–1051 | Allocation bar + sizing → **S2**. Gate banner → S2's D2-scrubbed single line (amber box dies). Catalyst note → S4 hover + hub H7. Cones → merged into the **single S4 outcomes module** |
| 8 | Four Forces rail 1053–1127 | Superseded by **S3's six axes** (Trend & Momentum · Cycle & Valuation · Liquidity & Flows · Leverage & Derivatives · Network & Miners · Macro Backdrop); each force's facts land in its axis receipt |
| 9 | Impulse radar fold 1129–1181 (+STALE banners, CVD line) | Radar state → Leverage-axis input + S4 watch condition when armed; STALE banners → `.dtp` honesty chips; full panel → **Derivatives Desk fold**; CVD line → same fold + receipt |
| 10 | AI Daily Brief card 1231–1240 | One quiet door: an S6 row linking `aibrief.html` (🧠 emoji dies) |
| 11 | Mid-term + short-term conviction cards 1242–1267 | Merged with cones into the **S4 outcomes module**: one window, typical dip, worst case, scenario levels — receipts carry the per-horizon detail |
| 12 | Risk-vs-strategy fold 1269–1291 (LWC chart, 4 variants, scorecards) | → **Strategy & Track Record fold** (S6), merged with `btc_strategy.html` content (§6.1); Lightweight Charts stays (sanctioned stack) |
| 13 | Cycle Time Machine 1293–1340 | → **Cycle Lab fold** (S6) as-is — genuinely good Tier-3; loses its top-level spine slot |
| 14 | Short-cycle ladder + MTF table 1342–1373 | Trend-axis state + spark on **S3**; the 5-row timeframe table → Trend receipt (structured) or Cycle Lab fold |
| 15 | Core-signals fold 1383–1412 (momentum/structure/impulse/BFI Plotly) | States feed S3 rows; charts re-render as **ilx** inside Cycle Lab / On-chain Lab folds |
| 16 | Cycle & valuation fold 1416–1515 (anchors, miner cost basis, cycle clock, thesis monitor, CME) | Valuation anchors + clock → Cycle-axis row + receipts; thesis monitor → **S4** (window language); miner cost basis → Network-axis receipt; CME positioning → Leverage receipt; charts → Cycle Lab fold |
| 17 | Options & leverage fold 1522–1587 (IV, skew, leverage minis) | States → Leverage-axis row; full cards → **Derivatives Desk fold** (fed by E4's published artifact) |
| 18 | Liquidity & breadth fold 1592–1641 | Net-liq/BFI-liquidity → Liquidity-axis row; equity-breadth → Macro receipt (breadth is an equity read; the crypto-native breadth lives on the hub) |
| 19 | On-chain & ETF fold 1648–1723 (Coinbase premium, dry powder, ETF flows + issuer table) | ETF flow state + premium → Liquidity-axis row + receipts; issuer table + charts → **On-chain Lab fold**; the hub's H3 owns the class-level ETF read |
| 20 | Advanced-factors fold 1727–1804 (hashprice, conditional beta, holder spread, Wikipedia, taker flow) | Hashprice/holder spread → Network-axis row + receipts; conditional beta → Macro receipt; Wikipedia attention → Network receipt; taker flow → Derivatives Desk fold |
| 21 | Markets-at-a-glance fold 1806–1828 | Crypto rows → **S5** mini-tapes (and the hub's H2 owns depth); cross-asset equity/commodity rows → Macro receipt (the macro dashboard already owns that job) |
| 22 | Recent-alerts timeline 1830–1868 | **Leaves the page**: Alert Center owns the stream; S6 gets one "alert history" link row; engine emission unchanged |
| 23 | Signal-verdicts + blending fold 1871–1913 | → **Signal Health fold** (S6): one-line calibration summary + link to measurement.html receipts (grade vocabulary stays off Tier 1) |
| 24 | Footer 1915–1918 | House `site-footer` untouched |
