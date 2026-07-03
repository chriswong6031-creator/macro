# HK & Canada Stock + Basket Desks — Problem Audit for Fable

**Scope:** `hk_stocks.html`, `baskets_hk.html`, `canada_stocks.html`, `baskets_canada.html`
**Reference (gold standard to measure against):** `us_stocks.html`, `baskets.html`
**Author:** Opus (audit pass) · **Date:** 2026-07-03
**Purpose:** Hand this to Fable. Fable reasons over it, designs novel + market-specific solutions, then delegates Opus/Sonnet to execute a phased fix plan. This document is *problems + evidence + suggested directions*, not the fix.

---

## 0. Epistemic status — read before trusting any claim

- **VERIFIED = read in code this session** (file:line cited). Most engine/wiring claims are VERIFIED.
- **UNVERIFIED** = requires production data, R2 stores, or forward-return validation to confirm. Flagged inline.
- **Worktree caveat:** heavy per-ticker stores moved to Cloudflare R2 (not git) since 2026-07-01. Some data absences below (e.g. Canada `_closes_cache.parquet`) may be **R2-by-design, not broken** — flagged as "verify against production," never asserted as a bug.
- **Prior I had to update mid-audit:** I opened expecting "these pages mislead users with fake buy lists." That is **largely wrong.** The engines carry strong, explicit honesty infrastructure (per-market trust tiers, "no selection alpha" language). The real problem is subtler and is the centerpiece below.

### Severity legend
`CRITICAL` product-integrity / user-trust · `HIGH` blocks the stated use or misleads · `MEDIUM` real gap, non-blocking · `LOW` polish
Categories: `promise-gap` · `honesty` · `no-validation` · `data-quality` · `engine-gap` · `ux` · `contradiction` · `dead-code`

---

## 1. THE CENTERPIECE — the promise vs the honest engine verdict

**The stated use (your words):** *"a powerful signals detection system that surfaces stocks that are both great picks in about-to-lead sectors where the stock is just about to run up — using thematic baskets coupled with confluence gates and other engines."*

**What the code actually believes about HK and Canada** (VERIFIED, `engine/stock_score.py:159-185`, `trust_tier()`):

| Market | Engine's own honesty badge | Meaning |
|---|---|---|
| **US** | `event-edge` → `validated` (gated) | Insider Form-4 (lone FDR survivor) + earnings SUE + analyst revisions. A real, measured selection edge. |
| **HK** | `screen` — *"No selection alpha — southbound-flow + A/H-value + global-exposure screen"* | HK has **no idiosyncratic stock-selection alpha** — residual momentum is dead on a 40-yr panel. Only structural edges survive. |
| **CA** | `context` — *"Residual-momentum prior — unvalidated, not a standalone edge"* | TSX momentum prior, never validated forward. |

**The tension, stated plainly:** The product promises *"surface great about-to-run stock picks."* The HK engine's own honest verdict is *"we cannot pick in HK — we can only screen for positioning."* Canada's is *"our pick list is an unvalidated momentum guess."* These are not bugs — they are the honest output of a system that (correctly) refuses to fake a US-grade buy list where the US-grade edge feeds don't exist.

> **In plain English:** The US desk works because the US gives us three things that predict which stock runs next — insider buying, earnings surprises, analyst upgrades. HK and Canada don't hand us those (or they don't work there). So the same machine, pointed at HK/Canada, honestly shrugs and says "I can screen, I can't pick." The pages are honest about this — sometimes to the point of talking themselves out of their own value.

**This forks Fable's whole solution:**
- **Path A — Reframe (cheap, honest, low ceiling):** accept HK/CA as *positioning screens*, and make the UI stop implying they're buy boards. Delivers trust, not the stated use.
- **Path B — Build market-specific edges (expensive, high ceiling):** the US edges are the wrong edges for these markets. Build + *validate* the edges these markets actually have: HK = southbound-flow accumulation, A/H mean-reversion, global-beta timing; Canada = commodity/CAD beta, SEDI insider (already collected — see HKCA-6), TSX earnings. **Different markets need different weights, models, and engines** — exactly your intuition. This is the Fable-worthy work.
- The two are not exclusive: reframe now (Path A) *and* build (Path B), with each new edge promoted from "screen" to "validated" only after it clears a forward-return gate (the house `gate_go` discipline already exists in `trust_tier`).

Everything in Part 2–6 is either evidence for this tension or a concrete, separable problem to fix along the way.

---

## 2. ENGINE / MODEL COVERAGE — what powers each page, and the gaps

### 2.1 Build topology (VERIFIED)

| Page | Builder | Per-stock/basket engine | Template |
|---|---|---|---|
| `us_stocks.html` | `scripts/build_stock_library.py` (1938 LOC) → `setups.json`, `us_standouts.json` | `stock_score` + `signal_gate` + 27 others | `templates/us_stocks_v2.html.j2` |
| `hk_stocks.html` | `scripts/build_hk.py:811` (`mode="stocks"`) + `scripts/build_hk_library.py` (997) | shared `stock_score`/`signal_gate` + HK-native feeds | `templates/hk.html.j2` (rendered twice, macro/stocks) |
| `canada_stocks.html` | `scripts/build_canada.py:491` (`mode="stocks"`) + `scripts/build_canada_library.py` (703) | shared `stock_score`/`signal_gate` + CA feeds | `templates/canada.html.j2` (rendered twice) |
| `baskets_hk.html` | `scripts/build_baskets_hk.py` (120) | `engine/baskets_hk.py` → `engine/baskets_region.py` (shared) | `templates/baskets_hk.html.j2` |
| `baskets_canada.html` | `scripts/build_baskets_canada.py` (102) | `engine/baskets_canada.py` → `engine/baskets_region.py` | `templates/baskets_canada.html.j2` |

**Good news the audit confirmed:** the two mechanisms you named — **thematic-basket tailwind** and the **confluence gate** — *are* wired in all three markets:
- Basket tailwind: `_basket_tailwind_map()` in each library (US `build_stock_library.py:585`, HK `build_hk_library.py:462`, CA `build_canada_library.py:117`) → feeds the Conviction "tailwind" axis in `stock_score.normalize_rec`.
- Confluence gate: `signal_gate.gate/is_buyable/compact` (the MACD-2D × StochRSI-3D T1→T4 cascade) is called in all three (US `:1210`, HK `:676`, CA `:455`).

So the *spine* exists. The problem is the spine is **thinner and less validated** on the flanks (HK/CA), detailed next.

### 2.2 Engine coverage matrix (VERIFIED via import diff)

US `build_stock_library.py` imports **29** engine modules; HK imports ~15; CA ~15. Modules present in US and **absent in both HK & CA libraries**:

| US engine (absent in HK & CA) | Portable to HK/CA? | Value for "about-to-run" |
|---|---|---|
| `coiled` (durable-bottom COILED state) | **YES — close-only** | **HIGH** — this is literally the "about to run up off a base" detector |
| `hold` (basing/HOLD tracker, W6-C) | **YES — close-only** | HIGH — holds a name through a base until it breaks |
| `extension` (`extension_signals`) | **YES — close-only** | HIGH — flags over-extension so you don't chase |
| `pullback_zone` | **YES — close-only** | HIGH — the "buy-the-pullback" entry price |
| `demand_chain` | partial (needs mapping data) | MED |
| `dannytrades_chip` (gamma/vol-hole) | **YES — close-only** | MED — the "volatility hole" compression setup |
| `stock_macro_sensitivity` / `conditions.sector_macro_beta` | **YES — with regional macro** | MED — rate/inflation head/tailwind per name |
| `ticker_alerts` | **YES** | MED — the alert layer HK/CA stock cards lack |
| `stock_fundamentals.panels` | **YES — HK/CA fundamentals engines already exist** | MED |
| `gex_confirm`, `options_ivspread` | **NO — needs options chains** | US-only (no free HK/CA options) |

Additional **HK-only** gaps (Canada *has* these, HK does not — VERIFIED import diff):
- `entry_signal`, `risk_sizing`, `dispersion` — market-agnostic entry/sizing/dispersion engines. **HK is thinner than Canada on the entry side.** Straight port.

**Takeaway for Fable:** at least six US engines (`coiled`, `hold`, `extension`, `pullback_zone`, `dannytrades_chip`, `pullback`/entry trio) are **close-only and market-agnostic** — they need no US-specific data and are the exact engines that answer *"is this stock about to run up off a base?"* Porting them is the cheapest, highest-leverage lift. This is Path-B groundwork that doesn't need new data.

---

## 3. PROBLEM LEDGER

### HKCA-1 — The confluence gate is US-calibrated and applied to HK/CA on faith *(HIGH · no-validation)*
`signal_gate.gate()` (the MACD-2D × StochRSI-3D T1→T4 cascade) is imported and applied identically in all three markets (`build_hk_library.py:676`, `build_canada_library.py:455`). Its thresholds/tiers were tuned on **US daily** behavior. HK (T+2, different tick dynamics, southbound-driven) and TSX (thin, commodity-levered) have different daily-cross statistics. **No evidence the gate's buyable-tier hit-rate was measured on HK or CA forward returns.** Same root cause as `INTL-16`/`INTL-27` in the intl audit (params tuned on US, ported on faith).
→ *Direction:* per-market gate calibration, or an explicit "gate is US-tuned, treat as heuristic" honesty flag until an HK/CA forward-log validates it.

### HKCA-2 — Thematic baskets are **hindsight-curated**, yet feed an "about-to-lead" claim *(HIGH · no-validation / honesty)*
`data/baskets_hk/membership.json` note (VERIFIED): *"Curated HK thematic baskets — **hindsight-curated and descriptive, not an out-of-sample backtest and not a buy list.**"* Same for Canada. The basket tailwind axis and the leader/laggard "rotation story" (`baskets_region.py:146`) are built from **members chosen with hindsight** about what worked. Using a hindsight-curated basket's 20d relative strength to argue a sector is "about to lead" is circular. This is the *first half* of your value prop ("about-to-lead sectors") resting on look-ahead-biased inputs.
→ *Direction:* systematic, rules-based membership (liquidity + sector map, reconstructed point-in-time) so the basket read is out-of-sample; OR down-weight the tailwind axis for curated baskets and label it "descriptive." Shares root cause with `INTL-8`, `INTL-13`, `INTL-28`.

### HKCA-3 — HK basket prices are ~15 days stale while the HK stock desk is fresh *(HIGH · data-quality / contradiction)*
`data/hk_search/closes_deep.parquet` last price date = **2026-06-18** (VERIFIED), but `data/hk_stocks/*.parquet` are current to **2026-07-02**. The HK basket compute (`baskets_hk._closes()` reads `closes_deep.parquet`) and therefore the **basket tailwind axis on the HK stock cards** run on 2-week-old prices, while the same cards' cycle/entry run on fresh prices. A card can show a "theme tailwind" that is two weeks out of date next to a live cycle state. No freshness guard. (Compare `INTL-29`: intl_search 13 days stale — same failure family.)
→ *Direction:* refresh `closes_deep` on the nightly cadence (decouple it from the manual curation date), or stamp+gate the tailwind axis on basket-price age.

### HKCA-4 — `baskets_canada` desk lacks the `basket_freeze` churn-guard US and HK have *(MEDIUM · data-quality)*
`build_baskets.py` (US) and `build_baskets_hk.py` both call `engine.basket_freeze.freeze_domain` (`:231`, `:102`). `build_baskets_canada.py` (102 LOC) has **no basket_freeze call** (VERIFIED grep). The freeze/churn-guard prevents membership flip-flop across renders. Canada baskets are unguarded → susceptible to the ratchet/flip-flop class of bug (cf. `membership-cache-reconciler`, `badge-passport-ratchet`).
→ *Direction:* add `basket_freeze` parity to the Canada desk builder.

### HKCA-5 — Region basket compute is materially thinner than the US basket engine *(MEDIUM · engine-gap)*
`engine/baskets_region.py` (shared by HK+CA) computes EW level/return/perf and a leader/laggard "story" (`:146-151`). The US path (`engine/baskets.py` 283 LOC + `basket_breadth_divergence`, `basket_mtf`, `basket_tape`, `basket_score` engines) adds breadth-divergence, MTF confluence, and tape context per basket. So the HK/CA basket **desk pages** deliver a simpler rotation read than `baskets.html`. The "about-to-lead" signal is a bare 20d-relative rank, not a confluence-confirmed one.
→ *Direction:* route HK/CA baskets through `basket_mtf` + `basket_breadth_divergence` so a "leading" basket must be confirmed by breadth and multi-timeframe, not just trailing 20d relative strength.

### HKCA-6 — Canada collects SEDI insider data, displays it, but **does not score it** (dead edge) *(HIGH · dead-code / honesty)*
`build_canada_library.py:413-598` fetches SEDI insider transactions (`canada_insider.fetch_insider`, `insider_map()`) and attaches `patch["insider"]` to records for display. But the CA selection axis uses **only `alpha`** (VERIFIED `stock_score._edge_basis:287-288` → CA adds only `"alpha"`; `_axis_selection` docstring: "CA — residual-momentum prior"). Meanwhile `trust_tier("CA")` still says *"no event feeds on the TSX"* (`stock_score.py:169`) — **stale/contradicted by the pipeline that now fetches insider.** So: we pay the API cost, we render insider chips (implying they matter), but the ranking ignores them, and the honesty badge denies they exist. Three-way inconsistency.
→ *Direction:* either (a) validate SEDI insider net-buying as a CA selection leg and wire it in (this is the single most promising *validated* CA edge, mirroring the US insider FDR survivor), or (b) stop fetching+displaying it. Update the trust-tier text either way.

### HKCA-7 — Canada tooltip calls the same leg both "VALIDATED" and "an unvalidated prior" *(HIGH · contradiction / honesty)*
`templates/canada.html.j2:380` help text (VERIFIED) says the board is *"ranked by the **VALIDATED** sector-neutral residual-momentum leg (α, the positive-IC selection leg)"* and then in the same tooltip: *"the selection leg is weak positive-IC **CONTEXT** and the axis weights are an **unvalidated prior**."* A single tooltip asserts the leg is validated and unvalidated. `trust_tier("CA")` sides with "unvalidated." Users reading carefully will (rightly) distrust the whole card.
→ *Direction:* one consistent claim — Canada α is a weak positive-IC *context* prior, not validated. Purge "VALIDATED" from the CA copy.

### HKCA-8 — Every builder is fail-open (`except: return 0`), so degradation is silent *(HIGH · data-quality)*
`build_canada.py` (whole `main` wrapped, `:371`, `:434`, `:452`, `:462`, `:470`, `:511`, `:525` → `return 0`) and `build_hk.py` follow the same pattern; the library sub-builds (`compute_canada_alpha`, `build_canada_library.main`, standouts enrich) each swallow exceptions and continue. If the alpha build, basket tailwind, or insider fetch fails, **the page still renders — with empty/stale setups — and nothing tells the user or the operator.** This is the same fail-open class as the Mastermind stockdata bug (`mastermind-problem-audit-for-fable`). A page that silently shows yesterday's (or nothing's) picks as if fresh is the *actual* "misleading users" vector here — more than any copy problem.
→ *Direction:* fail-open is fine for *never break the site*, but must emit a visible staleness/health banner + a `run_status` breaker (cf. `data-health-circuit-breaker`) when a leg is degraded, so a silent empty board can't masquerade as a live one.

### HKCA-9 — Composite conviction weights are an "uncalibrated PRIOR" for HK/CA, shown with equal visual weight to US *(MEDIUM · honesty)*
`stock_score._WEIGHT_PRIOR` (`:192-198`) is explicitly *"labeled uncalibrated PRIOR"* — HK `{sel .35/entry .25/tailwind .20/quality .20}`, CA `{.45/.18/.12/.25}` — never fit to HK/CA outcomes. The resulting 0-100 composite score renders in the same big band-colored chip as the US score (`hk.html.j2:564`, CA card). The engine hedges correctly in tooltips, but the **visual hierarchy** presents an uncalibrated number as if it were the validated US one. (Same UX pattern as `INTL-32`: page looks actionable while text says display-only.)
→ *Direction:* calibrate `_WEIGHT_PRIOR` per market once a forward-log exists; until then, visually de-emphasize the composite for `screen`/`context`-tier markets (the trust tier is already computed — let it drive the card's visual weight).

### HKCA-10 — HK is thinner than Canada on entry/sizing (no `entry_signal`/`risk_sizing`/`dispersion`) *(MEDIUM · engine-gap)*
VERIFIED import diff: Canada imports `entry_signal`, `risk_sizing`, `dispersion`; HK does not. These are market-agnostic. So HK cards get the confluence gate but not the same entry-timing/position-sizing/dispersion context Canada cards get. Inconsistent depth between two "screen"-tier desks.
→ *Direction:* straight port of the entry/sizing trio into `build_hk_library.py`.

### HKCA-11 — "Standout" card visual language mirrors the US buy board across all markets *(MEDIUM · ux / honesty)*
The HK/CA templates self-describe as *"standout-stock cards (mirror of the US dashboard)"* (`hk.html.j2:214`, `canada.html.j2:52`). They reuse the US card chrome — score chip, entry gauge, "Buy zone" price, ✅/⏳ action buckets (`_action_board`, `canada.html.j2:362`). The copy says "screen, not a buy list," but the *layout* is a buy board. Careful readers get the caveat; skimmers get a buy board. The honest text and the actionable layout pull in opposite directions.
→ *Direction:* let trust tier drive card *chrome*, not just a footnote — `screen`/`context` cards should look like a screen (ranked exposure list) not like the US validated buy board.

### HKCA-12 — No forward validation / track record on either HK or CA stock board *(HIGH · no-validation)*
Neither `build_hk_library` nor `build_canada_library` writes a forward-outcome log for its standout picks (the US side has the setups→forward grading; HK/CA have `name_score_grader` for the *name-potential* score only, not the standout ranking). So there is **no measured evidence** the HK screen or CA prior actually precede runs. You are trading (per your profile) on mechanism theses with no scoreboard here. Mirrors `INTL-7`/`INTL-34`.
→ *Direction:* a forward-return ledger per market (same pattern as the US board and the risk-radar audit logs already in `build_canada.py:427`), so each market's edge can graduate from `screen`→`validated` on its own evidence.

### HKCA-13 — Canada sector drill-down holdings depend on a cache that's absent in-tree *(MEDIUM · data-quality · UNVERIFIED)*
`build_canada.py:319` reads `data/canada_breadth/_closes_cache.parquet`; it does not exist in this worktree (VERIFIED absent), so `_build_sector_pages` constituent analysis and `_sector_cards` fall back to empty holdings. **This may be R2-by-design** (per `r2-data-plane` — heavy stores off-git since 2026-07-01). Flagged, not asserted.
→ *Direction:* verify against production/R2 that the Canada breadth close cache is actually populated at build time; if it's genuinely sparse, the Canada sector pages ship empty drill-downs.

### HKCA-14 — Canada `latest.json` is 3 days stale vs today *(LOW · data-quality · UNVERIFIED)*
`data/canada_stocks/latest.json` date = `2026-06-30`; US = `2026-07-01`; today `2026-07-03`. Could be weekend/holiday cadence or worktree lag. Verify the Canada pipeline runs on the same nightly cadence as US; if it lags, the landing-hub card advertises a stale count.

---

## 4. ARE WE MISLEADING USERS? — verdict

**Verdict: Not in the way I expected, and the honesty infrastructure is genuinely strong — but three real misleads remain.**

What's *good* (do not "fix" these — they're the model to extend):
- Per-market trust tiers are computed **and rendered** (`hk.html.j2:634`, `canada.html.j2:458`).
- HK copy is relentlessly honest: *"HK has NO idiosyncratic stock-selection alpha… never a buy list… trust tier: screen"* (`hk.html.j2:490, 537, 547, 659`).
- The cycle state is a **hard cap** on the verdict — a downtrending name can never read "Buy" (`stock_score._CYCLE_BLOCK_STATES`).

The three **real** misleads (ranked):
1. **Silent fail-open (HKCA-8)** — the biggest one. An empty/stale board renders as if live. This is a *systemic* mislead, not a copy nit.
2. **Decorative-but-unscored insider on Canada (HKCA-6)** — showing insider chips the ranking ignores implies an edge that isn't there, and the trust badge denies data the pipeline fetches.
3. **Layout says "buy board," text says "screen" (HKCA-9/11)** — the visual hierarchy over-promises what the caveats retract.

Everything else ("about-to-lead sectors" from hindsight baskets, US-tuned gate) is a **validity** problem (the signal may be weak), not a **deception** problem (the pages mostly say so).

---

## 5. UX / UI PROBLEMS

- **HKCA-11 / HKCA-9** (above): buy-board chrome on screen-tier content; uncalibrated composite shown at US visual weight.
- **Caveat fatigue (HK):** `hk.html.j2` repeats "no selection alpha / not a buy list / this is a screen" ~6 times on one page (`:490, 501, 537, 547, 549, 564, 659`). Past a point, wall-to-wall hedging reads as *"why are you showing me this at all?"* and users tune out the one caveat that matters. Consolidate to one prominent, well-designed "what this desk is / isn't" header + per-card tier badge; cut the repetition.
- **Two pages, one template, `mode` flag:** `hk.html.j2` and `canada.html.j2` each render *both* the macro page and the stock page from one file with `mode in (macro, stocks)`. This is efficient but means a stock-desk redesign risks the macro page and vice-versa; and sections leak conceptually (macro caveats appear on stock cards). Note for Fable's execution plan: changes are coupled — the stock desk cannot be re-skinned in isolation without a regression pass on the macro page.
- **Contradiction surface (HKCA-7):** the self-contradicting Canada tooltip is a trust-killer for exactly the sophisticated user who reads tooltips.
- **No "why this name, now" narrative:** cards show axes + chips, but neither market has the US-style plain-English "here's the setup" synthesis. Given the plain-language mandate (`research-notes-plain-language`), each screen card should end in one honest sentence: *"Southbound crowd adding + H cheap vs A + weekly basing — a positioning candidate, not a validated buy."*

---

## 6. WHAT TO PORT vs BUILD (the "different markets, different engines" answer)

**Port straight over (market-agnostic, close-only — no new data):**
`coiled`, `hold`, `extension`, `pullback_zone`, `dannytrades_chip`, `ticker_alerts` → all four/both desks. HK additionally: `entry_signal`, `risk_sizing`, `dispersion`. These directly serve "about to run up off a base" and cost no new feeds. **Start here — cheapest, highest leverage.**

**Wire existing regional data that's collected but unused/underused:**
- Canada: **SEDI insider** (already fetched — HKCA-6) → validate as a CA selection leg. `canada_fundamentals`, `canada_earnings`, `canada_factor_beta` exist → wire a real quality/earnings axis instead of alpha-only.
- HK: `hk_fundamentals`, `hk_property`, `hk_ah` (A/H), `hk_southbound_stocks` exist → the A/H and southbound legs are the *validated-candidate* HK edges; put them through a forward gate.

**Build market-specific (the Fable-novel work — different weights/models):**
- **HK:** southbound-flow accumulation edge (is HK's dominant marginal buyer adding?), A/H mean-reversion (H cheap vs A twin → convergence), global-beta *timing* (US→HK overnight transmission). These are HK's real edges; none are the US edges. Validate each; promote on evidence.
- **Canada:** commodity/CAD/BoC-vs-Fed beta is the *primary* TSX driver (the macro page already leads with it — `build_canada.py` docstring) but the **stock desk doesn't use it per-name.** A Canada name's edge is substantially "energy/materials beta in the right commodity regime." Build a commodity-regime-conditioned selection leg. Plus SEDI insider (above).
- **Recalibrate `_WEIGHT_PRIOR` per market** once each market has a forward-log — replace the uncalibrated equal-ish prior with fitted weights (HKCA-9).

**Do NOT port (US-data-specific):** `gex_confirm`, `options_ivspread` (no free HK/CA options), US insider Form-4/SUE/analyst-revision legs (use regional analogues above).

**Governing principle for Fable:** every ported or built edge stays `screen`/`context` tier until *its own* forward-return log validates it (the `gate_go` machinery in `trust_tier` already models this). The differentiator vs the current state is not more engines — it's **more validated** engines, per market, on their own evidence.

---

## 7. SUGGESTED PHASING (for Fable to reshape, not a mandate)

- **W0 — Truth & safety (no new alpha):** fix silent fail-open → health banner + breaker (HKCA-8); purge the CA "VALIDATED"/insider contradictions (HKCA-6/7); refresh HK basket prices (HKCA-3); add Canada `basket_freeze` (HKCA-4). *Ships trust immediately.*
- **W1 — Port the close-only engines:** `coiled`/`hold`/`extension`/`pullback_zone` + HK entry trio (HKCA-10, §6). *Ships the "about-to-run" detectors with no new data.*
- **W2 — De-bias the baskets:** rules-based point-in-time membership + `basket_mtf`/breadth confirmation (HKCA-2/HKCA-5). *Fixes the "about-to-lead" half.*
- **W3 — Wire regional edges:** SEDI insider (CA), southbound + A/H (HK), commodity-beta selection leg (CA) — each behind a forward gate (HKCA-6, §6, HKCA-12).
- **W4 — UX honesty pass:** trust-tier-driven card chrome, consolidate HK caveats, per-card plain-English verdict (HKCA-9/11, §5).
- **W5 — Validation & calibration:** forward-return ledgers per market; recalibrate `_WEIGHT_PRIOR`; per-market gate calibration (HKCA-1/9/12).

---

## Appendix A — Evidence table (VERIFIED this session)

| Claim | Evidence |
|---|---|
| HK/CA carry honest trust tiers | `engine/stock_score.py:159-185` |
| HK = "no selection alpha" screen | `stock_score.py:161-164`; `templates/hk.html.j2:490,537,547,659` |
| CA = "unvalidated residual-momentum prior" | `stock_score.py:168-171`; rendered `canada.html.j2:458` |
| Composite weights uncalibrated per-market prior | `stock_score.py:187-198` (`_WEIGHT_PRIOR`) |
| Basket tailwind + confluence gate wired in all 3 | US `build_stock_library.py:585,1210`; HK `build_hk_library.py:462,676`; CA `build_canada_library.py:117,455` |
| Engine coverage US 29 vs HK/CA ~15 | import diff, §2.2 |
| HK lacks entry_signal/risk_sizing/dispersion (CA has) | import diff `build_hk_library.py` vs `build_canada_library.py` |
| Baskets hindsight-curated, not a buy list | `data/baskets_hk/membership.json` `note` field |
| HK basket prices stale 2026-06-18 vs stocks 2026-07-02 | `data/hk_search/closes_deep.parquet` vs `data/hk_stocks/*.parquet` mtimes/last-date |
| Canada insider fetched+displayed, not scored | `build_canada_library.py:413-598`; `stock_score._edge_basis:287-288` |
| CA tooltip "VALIDATED" vs "unvalidated prior" | `templates/canada.html.j2:380` |
| Fail-open builders | `build_canada.py:371,434,452,462,470,511,525` |
| Canada basket desk lacks basket_freeze | `build_baskets_canada.py` (no `basket_freeze` import); cf. `build_baskets.py:231`, `build_baskets_hk.py:102` |
| Canada `_closes_cache` absent in-tree | `build_canada.py:319`; file not present (verify vs R2) |

## Appendix B — Related prior audits (shared root causes)
`research/INTL_ENGINE_PROBLEM_AUDIT_FOR_FABLE.md` (INTL-8/13/16/28/29/32 map directly onto HKCA-2/1/3/9), `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md`, `research/MASTERMIND_PROBLEM_AUDIT_FOR_FABLE.md` (fail-open class → HKCA-8). The HK/CA baskets share `engine/baskets_region.py` and the `seed_date: 2021-06-15` with the intl baskets — several intl basket findings are literally the same code.
