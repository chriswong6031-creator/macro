# Bonds & Bond Health — Research + Build Plan

**Status:** ✅ BUILT + CALIBRATED (Phases 0–4) + verified + COMMITTED (face1f3 + c3c92fc, bonds-only). Date: 2026-06-14. Health-first framing (per user). Daily sovereign spreads (Phase 5) is the remaining fast-follow.

**Phase 4 (calibration) — DONE + hardened.** `scripts/calibrate_bonds.py` discriminatively validates each leg + the composite (as STRESS) vs strictly-forward S&P 63-day drawdown + NBER 252-day recession, split-half (2013), **with a forward-window embargo around the split and CONFIRMED requiring BOTH halves meaningful (|IC|≥0.05), not just sign-stable.** Verdicts: **drawdown_risk / rates_vol CONFIRMED; recession_risk / credit DIRECTIONAL** (both strong pre-2013/2008, faded through QE — recession's post-2013 dd-IC ~0.01); **plumbing CONTEXT.** Composite CONFIRMED (high-stress tercile → ~23.7% forward-drawdown vs ~12.3% base, +11.4pp; recession-IC 0.53) **but ≈ the drawdown-risk leg alone** — an explainable synthesis, surfaced honestly in the UI (measured-edge box + ✓/~/· glyphs). NY-Fed probit Brier 0.165 vs 0.181 (skill +0.086). **Weights = the MEASURED (verdict-scaled) weights, adopted live + auto-refreshed weekly** (config prior fallback); health 86. `data/bonds/calibration.json`; weekly.yml calibrates before build.

**Phase 6 (adversarial-review hardening) — DONE.** A 3-agent review (correctness/no-look-ahead, calibration validity, collector/build robustness) found NO look-ahead but several real bugs, all fixed on the PR branch: a CRITICAL template build-crash (`None >= 0` on a null edge, outside the never-crash guard); `_debounce` always hiding the latest genuine flip (+ calendar-days on a business-day index); the calibration over-claiming CONFIRMED (→ the post-half-magnitude + embargo fixes above); unguarded charts/`as_of` in `main()`; ECB single-empty-series sinking the others. + a debounce regression test.
**Goal:** A "Bonds & bond health" section on the front page that reads economic health, market health, regime, and cycle position *from the bond market* — and exports a structured **bond-health signal vector** for the cross-asset AI synthesis brain (alongside equities / macro / BTC / forex / commodities).

## BUILD STATUS (what shipped, uncommitted)
- **Data (Phase 0):** added FRED `DGS1/3/7` (curve fill + NTFS), `DBAA`/`DAAA` (Moody's deep-history credit, 1986→), `BAMLH0A3HYC` (CCC), `IORB`/`SOFR99` (plumbing) → `config.yml` `fred.series.bonds_extra`; `bond_etfs: [TLT,IEF,TIP,EMB]` (collect in CI — yfinance absent locally). All FRED series fetched + on disk.
- **Engine (Phase 1):** `engine/bonds.py` (frame + snapshot + 5 pillars + cycle clock + health composite + the `_drivers_for` AI hand-off; reuses `engine.conditions` recession/drawdown/corr) + `engine/bonds_alerts.py` (debounced state-change events). `engine/inputs.py` got `us1y/us3y/us7y` (additive). Config block `bonds:` (bands/thresholds/weights — documented priors).
- **Dashboard (Phase 2):** `templates/bonds.html.j2` + `scripts/build_bonds.py` → `site/bonds.html` (7 Plotly charts, bilingual, theme/lang toggles). Health-first layout: hero score+phase+verdict, then the 5 pillars + the cross-asset hand-off + alert timeline + methodology.
- **Contract + integration (Phase 3):** writes `data/bonds/latest.json` (hub) + **`data/bonds/bond_health.json`** (the AI signal vector). Hub card in `build_vector` (`_bonds_state` + `_hub_html`); bonds nav-link in 10 page templates; `engine/i18n.py` LEX; `daily.yml` + `weekly.yml` build steps (after build_forex, before build_vector).
- **Tests:** `tests/test_bonds.py` — 13 pass (probit orientation, NTFS sign, curve taxonomy, un-inversion transient, bands, cycle mapping, health bounds, **no-look-ahead**, snapshot/contract structure, alert debounce/idempotency, real-data smoke). Scipy-free (uses `math.erf`). No macro-engine regressions.
- **Live read (2026-06-12):** health **88/100 (healthy)**, cycle **late**, NY-Fed recession prob 15.9%, HY OAS 2.78% (tight), MOVE 69 (calm), TP +0.80 (repriced positive), **stock-bond corr +0.69 → "breakdown" (bonds not hedging)** — the standout signal. Matches the brief's mid-2026 read.
- **Remaining:** Phase 4 calibration (split-half IC of the health composite vs forward recession/drawdown — the health weighting is currently a stated prior); Phase 5 daily Bundesbank/ECB sovereign spreads (BTP-Bund, JGB). UI + doc label these honestly.

> **The one-line reframe.** We already store ~90% of the data and `engine/conditions.py` already computes ~half the engine (term-premium-adjusted recession composite, stock-bond correlation regime, RORO, drawdown-risk). This project is **(a) surfacing existing bond intelligence into a dedicated, explainable dashboard, and (b) adding the bond-specific signal families that aren't computed yet** (curve-move taxonomy, near-term forward spread, credit distress bands, MOVE stress bands, the cycle clock, daily sovereign spreads), then **(c) emitting a clean machine-readable contract for the AI brain.**

---

## 1. Why bonds are the highest-signal macro asset

Bonds price the **discount rate** (real yields + term premium) and **default risk** (credit spreads) *before* equity earnings deteriorate, so the bond market leads the cycle. The four things bonds tell us:

1. **Growth / recession** — the yield curve is the market's forecast of the Fed's path; it only inverts when the market expects cuts, which only happens when growth is breaking. Best single recession instrument available from free daily data.
2. **Risk appetite ("smart money")** — credit spreads widen before equities fall, because the same deterioration hits bondholders (downside/default) first.
3. **Inflation regime** — breakevens and real yields separate nominal moves into "growth vs. inflation," which is the master switch for the stock-bond correlation and for gold/BTC.
4. **Systemic stress / plumbing** — rates volatility (MOVE) and funding spreads (SOFR) are the "is the pipe blocked?" gauges that front-run forced de-risking across all assets.

---

## 2. Signal families — what each tells us, thresholds, computability

Each family below is flagged: **[HAVE]** data already on disk · **[ADD]** free series to collect · **[ENGINE]** already computed in `conditions.py`.

### 2.1 Curve & growth (the recession read)

| Signal | Source | What it signals | Key levels |
|---|---|---|---|
| **3m10y** spread `T10Y3M` **[HAVE]** | FRED | NY Fed's chosen recession spread; inverted before every US recession since ~1968 | NY Fed probit: `P = Φ(−0.5333 − 0.6629·spread)`; >30% caution, >50% recession base-case in 12mo |
| **2s10s** `T10Y2Y` **[HAVE]** | FRED | Most-quoted; strong record but statistically *dominated* by the front-end spread | <0 = inversion |
| **Near-term forward spread (NTFS)** **[ADD-compute]** | bootstrap from `DGS*` | Engstrom-Sharpe (Fed, 2018): implied 3m rate 18mo ahead − current 3m. **Beats 2s10s** — a −80bp move raises recession prob ~35pp (p<0.01); 2s10s sensitivity 0.06, p=0.43 (not different from zero) | falling/negative = cuts priced = growth breaking |
| **Term-premium-adjusted curve** `spread_2s10s + term_premium_10y` **[ENGINE]** | conditions.py | Strips *false* inversions (2022–24, when TP was deeply negative). Already has a `curve_note` | adjusted < 0 = "real" inversion |
| **Curve-move taxonomy** **[ADD-compute]** | DGS2/DGS10 | bull/bear × steepener/flattener — classifies the *daily* move | bear-flattener = late-cycle hawkish (bearish); bull-steepener = cuts coming |
| **Un-inversion alarm** **[ADD-compute]** | T10Y3M history | The dangerous part: curve **dis-inverts just before** the recession. First-inversion→recession ≈ 334d; **dis-inversion→recession ≈ 66d**. A *bull-steepening* un-inversion (short rates collapsing) is the ominous one | flag when curve crosses back >0 after a prior inversion |

### 2.2 Credit & risk appetite (smart money)

| Signal | Source | What it signals | Key levels |
|---|---|---|---|
| **HY OAS** `BAMLH0A0HYM2` **[HAVE]** | FRED (⚠ ~3y rolling history) | The core risk/recession gauge; leads equities ~1–3mo, economy ~6–12mo | ~500bp = "halfway to distress"; ~1000bp = distress (hit in 2000/2008/2020 bears) |
| **IG OAS** `BAMLC0A0CM` **[HAVE]** | FRED (⚠ ~3y) | Investment-grade stress | |
| **HY−IG ratio** **[ADD-compute]** | derived | Risk-appetite / quality-rotation; turns *independent* of absolute level | rising = risk-off |
| **EM corp OAS** `BAMLEMCBPIOAS` **[HAVE]** | FRED | Global risk-off (already a Forex Vector RORO leg) | |
| **Excess Bond Premium (EBP)** **[HAVE]** | Fed Board CSV, monthly, `data/fedboard/ebp.parquet` | **The cleanest signal.** Gilchrist-Zakrajšek: strips default-risk from spreads → the credit-supply/risk-appetite residual. The recession-forecasting power of credit spreads over 40y is due *entirely* to EBP. +1pp EBP ⇒ ~−2.7% payrolls, +1.8pp unemployment (3mo) | already feeds `recession_risk` |
| **Moody's Baa−Aaa** `DBAA`−`DAAA` **[ADD]** | FRED, **daily, back to 1986** | Deep-history credit gauge — the workaround for the **FRED BAML ~3y truncation** | widening = stress |
| **HY by rating** `BAMLH0A1HYBB`, `BAMLH0A3HYC` (CCC) **[ADD]** | FRED | Credit-quality ladder; CCC = the distress tail | |

> ⚠ **Critical data finding:** As of 2026 FRED distributes only a **~3-year rolling window** of every ICE BofA `BAML*` series (licensing change). They still update daily, but deep history is gone. **Mitigation:** (1) we already **archived** the full pre-2026 HY/IG history in `data/archive/BAMLH0A0HYM2.parquet` + `BAMLC0A0CM.parquet` — keep caching forever; (2) add **Moody's `DBAA`/`DAAA` (daily, 1986)** as the deep-history credit backbone; (3) use **`HYG`/`JNK` ETF prices** for HY price/momentum signals that sidestep the truncation.

### 2.3 Inflation & real rates (the discount rate)

| Signal | Source | What it signals |
|---|---|---|
| **10y/5y real yield** `DFII10`/`DFII5` **[HAVE]** | FRED | The discount rate for *all* risk assets. Gold's opportunity cost (historically ~−0.45 corr; **caveat:** decoupled 2024–26 on CB buying / fiscal-dominance — treat as a strong prior that a flows story can override). BTC = long-duration, real-rate-sensitive |
| **Breakevens** `T10YIE`/`T5YIE`/**`T5YIFR`** (5y5y fwd) **[HAVE]** | FRED | Market inflation expectations; 5y5y forward = the Fed's preferred anchor (strips near-term noise) |
| **Term premium** `THREEFYTP10` **[HAVE]** | FRED, Kim-Wright, daily 1990 | Compensation for duration risk. The **2023–25 repricing positive** (ACM ~+0.55% mid-2025) is structural — more of any long-yield move is now supply/fiscal-driven (a bear-steepening force; part of *why* stock-bond corr flipped). ACM family is NY Fed CSV only (not FRED), correlates ~0.86 — optional Tier-2 add |

### 2.4 Stress & plumbing (the thermometer)

| Signal | Source | What it signals | Key levels |
|---|---|---|---|
| **MOVE index** `_MOVE` **[HAVE]** | Yahoo `^MOVE`, `data/yahoo/_MOVE.parquet` | The "VIX of bonds" — rates-vol systemic-stress gauge | normal 55–130; <60 calm, >120 extreme, >150 crisis |
| **MOVE-leads-VIX** **[ADD-compute]** | _MOVE vs _VIX | A MOVE spike typically *precedes/transmits* to VIX — cleaner systemic tell than VIX alone | MOVE rising while VIX flat = brewing |
| **SOFR plumbing** `SOFR`−`IORB`, `SOFR99` **[ADD]** (`SOFR` HAVE, `IORB`/`SOFR99` ADD) | FRED daily | Funding/repo stress — early warning. 2025 saw genuine repo stress (record SRF draw, SOFR-IORB drifting up) | SOFR-IORB drifting up = reserve scarcity; SOFR99 spike = repo stress |
| **NFCI family** `NFCI/ANFCI/NFCIRISK/NFCICREDIT/NFCILEVERAGE` **[HAVE/ENGINE]** | FRED weekly | Broad financial conditions; already z-scored + trended in conditions.py | +z = tightening |
| Swap spreads | — | **Genuine gap, skip.** LIBOR `DSWP*` discontinued; no free daily SOFR swap rate. Approximate direction with credit OAS | |

### 2.5 Cross-country & sovereign (global risk regime)

| Signal | Source | What it signals |
|---|---|---|
| **BTP−Bund** (IT−DE 10y) **[ADD-Tier2]** | needs *daily* foreign 10y (Bundesbank API for Bund, ECB Data Portal for euro curves; OECD `IRLTLT01*` we have is **monthly — too slow**) | Euro-periphery fragmentation; >200bp = risk-off, ~60bp in 2026 (calm) |
| **JGB 2s10s** **[ADD-Tier2]** | foreign curve | Post-YCC normalization; a steep JGB long-end can repatriate Japanese capital → global duration supply |
| **EM sovereign** | `EMB` ETF (Yahoo) **[ADD]** — EMBI index is licensed | +100bp EMBI move = EM drawdown; ETF is the free proxy |
| Gilt/LDI (2022) | — | Keep as the canonical "bond plumbing breaks the real economy" tail-scenario template |

### 2.6 Stock-bond correlation regime **[ENGINE]**

`conditions.py` already computes `stock_bond_corr` (rolling SPY vs bond returns). The story: negative ~2000–2021 (bonds hedged equities → 60/40 worked) → **flipped positive in 2022** (both fell; 60/40 −16.7%). **Driver (AQR):** not the *level* of inflation but the **volatility of inflation news relative to growth news** — equities/bonds have opposite-sign growth sensitivity but same-sign inflation sensitivity, so high inflation-vol ⇒ positive corr. Durable (~70% of long-run variation). **Dashboard use:** show 21d + 126d rolling corr with zero-line + ±0.2 bands, annotated by inflation-vol regime → directly answers "is the bond hedge working right now?"

### 2.7 Cycle position — the clock

The **credit × curve loop** traces a counter-clockwise rotation (documented by CME / Gilchrist-Zakrajšek):

| Phase | Curve | HY OAS | Real yields / TP | Equity regime |
|---|---|---|---|---|
| **Recession** | flat→bull-steepening (Fed cutting hard) | very wide (>1000bp), peaking | real yields falling fast | trough, max pessimism |
| **Early recovery** | steep | tightening fast off wides | low/negative | strong risk-on, cyclicals lead |
| **Mid cycle** | steep→flattening | tight & stable | normalizing up | grind-up, broad |
| **Late cycle** | flat→inverted (bear-flattener) | tight but dispersion rising | elevated, TP rising | topping, narrow leadership |

The **specific "late→recession transition" alarm**: bull-steepening un-inversion **+** EBP/HY-OAS turning up from tight **+** MOVE rising.

---

## 3. Cross-asset mechanics (the end-goal wiring)

The bond layer is the hub that the AI brain uses to reason across the other dashboards. Mechanism map:

- **Bonds ↔ rates/Fed:** front end (`DGS2`) vs Fed funds = easing/tightening priced; long end = expectations + term premium. The curve *is* the Fed-path forecast.
- **Bonds ↔ currencies (→ Forex Vector):** FX follows **rate differentials** — `DGS2 − Bund2y` drives EUR/USD; `DGS10 − JGB10y` is the canonical USD/JPY engine; real-rate gap = `DFII10 − foreign real 10y`. *This is why daily foreign yields (Tier 2) matter — monthly OECD can't track an FX signal.*
- **Bonds ↔ commodities (→ Commodity Vector):** `DFII10` = gold's discount rate (inverse); breakevens (`T10YIE`) co-move with oil/energy; curve slope proxies growth → copper/oil. The Commodity Vector *already* reads `DFII10`/`T10YIE`/`T5YIFR` as drivers — bonds are upstream.
- **Bonds ↔ bitcoin (→ BTC Vector):** BTC = long-duration risk asset → real yields (inverse) + dollar liquidity (RRP drawdown + reserves) + risk-on/off via HY OAS / MOVE. Pairs with existing BTC liquidity inputs.
- **Bonds ↔ equities:** discount-rate channel (higher `DGS10` compresses multiples, hits long-duration/growth hardest); **credit-as-canary** (OAS/`HYG` lead drawdowns); **rate-of-change > level** — the *speed* of a yield move (and a MOVE spike) breaks equities, not the level.

---

## 4. Data inventory — have / add

### Already on disk (no work)
- **Curve:** `DGS3MO, DGS6MO, DGS2, DGS5, DGS10, DGS30` + `T10Y2Y, T10Y3M`
- **Real/inflation:** `DFII5, DFII10, T5YIE, T10YIE, T5YIFR`
- **Term premium:** `THREEFYTP10`
- **Credit:** `BAMLH0A0HYM2` (HY), `BAMLC0A0CM` (IG), `BAMLEMCBPIOAS` (EM) + **full archived history** in `data/archive/`
- **EBP:** `data/fedboard/ebp.parquet` (monthly, 1973)
- **Conditions:** NFCI family, STLFSI, Sahm, recession prob
- **Stress:** `_MOVE`, `_VIX`, `_VIX3M`, `_VVIX` (Yahoo), CBOE SKEW
- **Plumbing:** `SOFR` (FRED), `EFFR` + `RRP` (NY Fed), `WALCL`, TGA, net issuance
- **Bond ETFs:** `HYG`, `LQD`
- **Foreign 10y (monthly):** EZ/JP/GB/AU/CA/CH
- **Engine:** `recession_risk` (term-premium-adjusted), `stock_bond_corr`, `roro`, `drawdown_risk`, `capitulation`

### Phase-0 adds (all free, daily, reuse `collectors/fred.py` + `collectors/yahoo.py`)
| Add | ID / ticker | Why |
|---|---|---|
| Moody's Baa/Aaa | `DBAA`, `DAAA` (FRED, daily 1986) | deep-history credit (BAML truncation workaround) |
| Funding plumbing | `IORB`, `EFFR` (FRED), `SOFR1/25/75/99` | SOFR-IORB spread + repo-stress percentile |
| Curve fill | `DGS3`, `DGS7` | complete the tenor grid (butterfly/NTFS) |
| Credit ladder | `BAMLH0A1HYBB`, `BAMLH0A3HYC` (CCC) | quality ladder / distress tail |
| Reserves | `WRESBAL` | liquidity tide for BTC/risk leg |
| ETF proxies | `TLT, IEF, SHY, JNK, EMB, TIP, AGG` (Yahoo) | price/flow signals; synthetic curve; free EM-sov read |

### Tier-2 (harder, deferrable)
- **Daily foreign 10y** via **Bundesbank API** (Bund) + **ECB Data Portal API** (euro curves) → enables BTP-Bund + the FX rate-differential leg properly.
- **NY Fed ACM** term premium CSV (longer history / more-cited than `THREEFYTP10`).
- **Pre-2023 BAML history** from ICE Data Indices (only if deeper credit history than our archive matters).

### Skip
- Swap spreads (no free daily SOFR swap), JPM EMBI levels (use `EMB`), MOVE history older than Yahoo.

---

## 5. Build plan — architecture & phasing

Follows the established `{asset}_*` Vector pattern (forex/commodity/btc), but the **headline output is a "bond health" read**, not a trade-conviction LONG/SHORT — matching the brief ("focus on bond data and bond health and how these signals tell us about economic health").

### Files (clone forex/commodity conventions)
```
engine/bonds_inputs.py     # load curve, credit, real/infl, MOVE, plumbing, foreign → feature frame
engine/bonds_signals.py    # the 7 families: curve taxonomy, NTFS, credit bands, MOVE bands, plumbing, sovereign
engine/bonds_health.py     # composite 0-100 score + cycle-clock phase + the transition alarm
engine/bonds_alerts.py     # state flips: inversion/un-inversion, OAS band cross, MOVE>120, repo stress, corr-regime flip
scripts/build_bonds.py     # render → site/bonds.html + data/bonds/latest.json + data/bonds/bond_health.json
scripts/calibrate_bonds.py # measure each leg's edge vs forward outcomes (IC), no look-ahead
templates/bonds.html.j2    # Jinja2; reuse theme.css, .af-* feed, verdict hero, hover-charts, t()/tr()/td() i18n
tests/test_bonds.py        # sign/causality/no-look-ahead invariants + real-data cross-check
config.yml  → bonds:       # active series, factor weights, thresholds, bands
engine/i18n.py → LEX       # bond glossary (中文)
scripts/build_site.py      # orchestrate build_bonds(); read latest.json for hub card
site/index.html            # hub card 🏛️ + feed items
```

### Phasing
- **Phase 0 — Data completeness** *(small; reuse existing collectors)*: add the Phase-0 series above; verify on disk.
- **Phase 1 — Health engine + validation harness FIRST** *(the core)*: build `bonds_signals.py` + `bonds_health.py`; **before weighting anything, measure each leg's edge** vs forward recession dating + forward equity drawdowns (this is the house style — cf. `drawdown_risk`'s MEASURED ">=80 ⇒ ~45% prob of ≥10% drawdown in 63d", DSR/AQR-null gates). Reuse `conditions.py` for recession/corr/RORO rather than re-derive. The composite must be *validated, not hardcoded*.
- **Phase 2 — Dashboard**: `bonds.html.j2` + `build_bonds.py`. Explainability-first (the macro-explainability house style): hover-charts, threshold bands drawn on, plain-English "what this means," jargon behind reveals. Bilingual via `t()/tr()/td()` + LEX.
- **Phase 3 — Integration**: hub card + nav links across pages; write `data/bonds/latest.json` (hub) **and `data/bonds/bond_health.json` (the AI contract, §6)**.
- **Phase 4 — Calibration**: `calibrate_bonds.py` → `data/bonds/conviction_calibration.json`; IC per leg, costs, split-half, no look-ahead.

### Dashboard layout (proposed)
1. **Hero: Bond Health Score (0–100) + cycle-clock phase** + one-line verdict (e.g. "Late-cycle, low-stress, tight-credit — watch for bull-steepening un-inversion").
2. **Curve & growth** — live curve chart, 3m10y + NTFS + TP-adjusted, NY Fed probit %, move-taxonomy chip, un-inversion alarm.
3. **Credit & risk appetite** — HY/IG OAS with 500/1000bp bands, HY-IG ratio, EBP overlay, Moody's deep-history.
4. **Inflation & real rates** — DFII10, T5YIFR, term-premium attribution.
5. **Stress & plumbing** — MOVE gauge with bands, MOVE-vs-VIX, SOFR-IORB / repo stress.
6. **Cross-asset / regime** — stock-bond corr regime, BTP-Bund / JGB (Tier 2), the cycle clock visual.
7. **Alert timeline** — `.af-*` feed of bond state-changes.

---

## 6. The AI-synthesis contract (the end goal)

The dashboard's real payload is **`data/bonds/bond_health.json`** — a structured, machine-readable state the cross-asset master brain consumes alongside the equity/macro/BTC/forex/commodity states (per the LLM-layer decision: DeepSeek digest → Claude Opus master brain feeding `conditions.py`/`dislocation.py` Gate-1). Proposed shape:

```jsonc
{
  "as_of": "2026-06-14",
  "health_score": 0,            // 0-100 synthesized bond-health, validated vs forward outcomes
  "cycle_phase": "late",        // recession|early|mid|late, from curve×credit clock
  "verdict_en": "...", "verdict_zh": "...",
  "pillars": {
    "curve":   { "state": "...", "t10y3m": 0.0, "ntfs": 0.0, "tp_adjusted": 0.0,
                 "ny_fed_recession_prob": 0.0, "move_taxonomy": "bear_flattener",
                 "uninversion_alarm": false },
    "credit":  { "state": "...", "hy_oas": 0, "ig_oas": 0, "hy_ig_ratio": 0.0,
                 "ebp": 0.0, "distress_band": "tight" },
    "real_inflation": { "state": "...", "real_10y": 0.0, "breakeven_5y5y": 0.0, "term_premium": 0.0 },
    "stress":  { "state": "...", "move": 0, "move_band": "calm", "move_leads_vix": false,
                 "sofr_iorb": 0.0, "repo_stress": false },
    "sovereign": { "state": "...", "btp_bund": null, "jgb_2s10s": null },
    "cross_asset": { "stock_bond_corr": 0.0, "regime": "positive" }
  },
  "alarms": [ /* the transition triggers that fired */ ],
  "drivers_for": { "forex": "...", "commodities": "...", "btc": "...", "equities": "..." }
}
```

`drivers_for` is the explicit hand-off: the bond layer tells each other dashboard what bonds imply for it (rate differentials for forex, real-yield/breakeven for commodities, real-yield+liquidity for BTC, discount-rate+credit-canary for equities). That's what turns five separate dashboards into one reasoned cross-asset view.

---

## 7. Open decisions (for the user)

1. **Framing** — recommended: **"bond health / economic-signal" first** (regime/cycle/recession/stress read), with a *light* directional layer (duration & credit positioning) rather than a full per-instrument trade-conviction Vector. Matches the brief + the end goal.
2. **Tier-2 daily foreign yields now or later** — needed for BTP-Bund + the proper FX rate-differential leg, but adds two new collectors (Bundesbank + ECB). Recommend **defer to a Phase-5** so the US-centric core ships first.
3. **Scope of first build** — recommend Phases 0–3 (data + validated engine + dashboard + AI contract), with calibration (Phase 4) and sovereign (Phase 5) as fast-follows.

---

## Appendix — computability cheat-sheet (free daily unless noted)

| Signal | ID | Status |
|---|---|---|
| 3m10y / 2s10s | `T10Y3M` / `T10Y2Y` | HAVE |
| Curve tenors | `DGS3MO,6MO,2,5,10,30` (+ add `DGS3,DGS7`) | HAVE/ADD |
| NTFS | bootstrap from `DGS*` | compute |
| HY/IG/EM OAS | `BAMLH0A0HYM2`/`BAMLC0A0CM`/`BAMLEMCBPIOAS` | HAVE (⚠3y) + archive |
| Moody's credit | `DBAA`,`DAAA`,`BAA10Y` | ADD (daily 1986) |
| EBP | Fed CSV | HAVE (monthly) |
| Real / breakeven | `DFII10,DFII5` / `T10YIE,T5YIE,T5YIFR` | HAVE |
| Term premium | `THREEFYTP10` (ACM=NY Fed CSV) | HAVE |
| MOVE | Yahoo `^MOVE` | HAVE |
| Plumbing | `SOFR`(+`IORB`,`EFFR`,`SOFR99`) | HAVE/ADD |
| Reserves/liquidity | `RRPONTSYD`,`WALCL`,`WRESBAL` | HAVE/ADD |
| ETF proxies | `HYG,LQD`(+`TLT,IEF,SHY,JNK,EMB,TIP,AGG`) | HAVE/ADD |
| Foreign daily 10y | Bundesbank + ECB API | Tier-2 |
| Stock-bond corr | compute SPY vs `DGS10`/TLT | ENGINE |
