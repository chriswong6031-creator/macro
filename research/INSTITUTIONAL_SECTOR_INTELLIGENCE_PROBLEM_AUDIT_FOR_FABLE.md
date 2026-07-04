# Institutional Sector Rotation Intelligence — Problem Audit for Fable

## Source

A ChatGPT-authored one-pager (pasted into chat 2026-07-03, not a file — no external doc to link) proposing a "capital migration detector": a 7-layer causal chain (think-tank/policy narrative → government policy/public capital → institutional flow/ownership → private capex → corporate fundamentals → technical confirmation → alt-data) that scores sectors/themes on where capital is *about to* go, plus ~13 "novel signal" formulas (Narrative-to-Money Divergence, Funding-to-Market-Cap Ratio, Elite Consensus Delta, Capex Receiver/Payer Matrix, etc.) and a page-by-page UI spec (Institutional Sector Rotation Radar, per-theme cards, per-stock Theme Exposure Panel).

This doc is the ground-truth pass before handing to Fable, per the established pattern ([[foresight-desk-problem-audit-for-fable]], [[hk-canada-stocks-audit-for-fable]], [[cycle-intelligence-problem-audit-for-fable]]): verify what the proposal assumes is missing against the actual repo, so the phased masterplan builds only the real gap instead of re-deriving shipped work.

## Core verdict

This is **not** a green-field build. `engine/` already runs a more rigorous, differently-framed version of ~75-80% of this thesis under the **Thematic Foresight Desk** program ([[thematic-foresight-desk]], `site/foresight.html`, 21 PRs, program COMPLETE 2026-07-03): physical bottleneck (`bottleneck.py`, `power_scarcity.py`) → demand/capex pool (`demand_chain.py`) → policy-adjacent guidance language (`guidance_gap.py`) → earnings/backlog confirmation (`theme_revisions.py`, `theme_fingerprint.py`) → institutional/gov confirmers (`altdata_confirmers.py`) → cross-surface convergence (`foresight_convergence.py`) → LLM synthesis (`foresight_analyst.py`) → posture sizing (`foresight_sizing.py`) → forward-graded ledger (`foresight_grader.py`, first grades ~2026-08-01).

It is **more disciplined** than the ChatGPT spec on the exact failure mode the doc is trying to avoid ("narrative without money"): the shipped **evidence hierarchy** — text ≤50 < member-XBRL fingerprint ≤60 < FRED real-time uncapped, each tier separately labeled and gradeable — is a stricter, code-enforced version of the doc's "Buzzword Tourist Detector." Nothing here can launder a hot narrative into a fabricated physical-tightness read.

The real gap is narrower than the doc implies: **one clean missing data layer** (elite policy-narrative sourcing) plus **several missing named-metric conveniences** that are directionally covered by existing mechanics but not surfaced under the doc's specific labels/formulas.

## Layer-by-layer mapping (verified against code, not memory)

### Layer 1 — Think-tank / policy narrative ("early warning")
**STATUS: GENUINE GAP.** The cleanest, narrowest hole in the whole doc.
- What exists: `engine/macro_news.py` `OFFICIAL_FEEDS` (BEA/BLS/Census/Fed/Treasury/SEC RSS — statistical *releases*, not policy-elite narrative) + `NEWS_FEEDS` (CNBC/WSJ/MarketWatch/NPR/Economist — general financial media, tiered by `_source_weight`) + GDELT wire. China side has an analogous tiering (`china_news_intel.py` `_TIER1` = state media).
- What's missing: **zero** ingestion of CSIS / RAND / Brookings / Atlantic Council / CNAS / IMF-OECD-BIS research / Federal Register / congressional-hearing transcripts. No "Policy Narrative Heatmap," no "Elite Consensus Delta" (cross-institution convergence on a theme), no urgency-language scoring on *policy* documents (urgency/scarcity NLP exists only for 8-K/10-K text via EDGAR and for general news via `macro_news` tiering).
- Existing plumbing that generalizes cleanly: `_source_weight()` in `macro_news.py` (official > tier1 > general) is the exact pattern a `tier: think_tank` bucket would reuse. `data/policy/intel.json` (Fed & Policy Watch, [[policy-watch-and-reports-pipeline]]) is a curated structured-field extraction (thesis/regime_read/rotation.targeted/starved) — the closest existing template for a multi-institution, sector-tagged version.
- Free-source reality for Fable to weigh: CSIS/RAND/Brookings/CNAS mostly don't publish full-report RSS (some have article-level feeds only). **Federal Register DOES** have a free, keyless, full bulk API + RSS (federalregister.gov) and is the single highest-leverage new source here — a proposed rule is literally "official priority becoming binding," which is exactly the doc's own framing. IEA/EIA *data* is already collected (`strategic_reserves.py`, `commodity_supply_context.py`, `collectors/eia.py`); it's the narrative/report layer that's missing, not the underlying series.

### Layer 2 — Government policy / public capital
**STATUS: MOSTLY BUILT** — deeper than the doc assumes.
- `collectors/usaspending.py` + `engine/theme_activity.py`: federal contract **obligations** and **grants_loans** (CHIPS/DOE/IRA-style assistance), YoY seasonality-adjusted, rolled up per theme/basket, weighted 1.0/0.85 into a fused real-activity z-score. This alone covers most of the doc's "award growth by sector" + "Government Money Heatmap."
- `collectors/sam_gov.py`: pre-award opportunities (`sam_presolicitation`, opp_velocity, gated on `SAM_API_KEY`) — covers "opportunity/pipeline growth."
- `collectors/grants_gov.py`: pre-award FOA velocity (gated) — partial "new program detection."
- Quiver `govcontracts` + `lobbying` + `corpdonors` (`engine/altdata.py` `gov_contract_leaders()`, lobbying spike detection) — this **already ships** the doc's "Lobbying Pressure Index" ask, not a gap.
- Missing vs the doc: (a) **Pipeline-to-award conversion rate** (SAM $ opportunities → USAspending $ awards by keyword cluster) isn't computed — `theme_activity` treats these as separate legs, never a ratio. (b) **Funding-to-Market-Cap Ratio** — not computed anywhere; genuinely cheap to add (award $ already on disk ÷ market cap already on disk via EDGAR facts). (c) **Contract Momentum Surprise** (current 30d vs *trailing-12mo average run-rate*) — `theme_activity` only does YoY, not this run-rate variant. (d) Federal Register regulatory-demand tracking — tied to Layer 1's gap.
- The doc's headline "Policy-to-Money Conversion Score" composite doesn't exist under that name, but 4 of its 6 weighted inputs are already separate legs in `theme_activity.py` — assembling the composite is a wiring job, not new data collection.

### Layer 3 — Institutional flow / ownership
**STATUS: BUILT**, arguably deeper than the doc's ask.
- 13F: `engine/smart_money.py` — `accumulation_trend()` (6-quarter depth), `overlap_stats()` (VIP fund count + ownership HHI = crowding), `engine/manager_quality.py` (A-D fund grades from replay-graded filing-date forward returns).
- 13D/13G: `collectors/beneficial_ownership.py` + `engine/beneficial_ownership.py` — activist vs custodian-passive classification, 13G→13D flip detection (exactly the doc's "activist/concentrated ownership" ask).
- ETF flows: [[capital-flow-velocity-desk]] (CN/HK, deep, sector+per-name) + `engine/etf_perfund.py` (BTC-ETF per-fund flows). **Gap:** no equivalent **US equity sector-ETF** (XLK/XLE/XLU/XLI...) flow-velocity engine — CN/HK have this, US doesn't. This is the one real hole in this layer, and the doc calls US sector-ETF flow the "fastest public proxy for sector rotation."
- Crowding-adjusted scoring: `engine/crowding.py` (US fragility tag: crowded+shorted+extended) + `china_crowding.py` — covers the doc's "Crowding-Adjusted Flow" ask.
- "Institutional Rotation Phase" (0-4 ignored→distribution) — no module under that literal name, but `foresight_cascade.py`'s STAGE taxonomy (PRECIPICE/BROADENING/RE-RATING/GLUT-RISK/WATCH) is the same 5-phase idea, already shipped and forward-graded.
- Genuine gap: **N-PORT** (fund-level monthly holdings, distinct cadence from 13F) is not referenced anywhere — 13F is the only ownership cadence used.

### Layer 4 — Private capex (payer vs beneficiary)
**STATUS: BUILT** — this is close to verbatim what `engine/demand_chain.py` + `bottleneck.py` + `glut_watch.py` already do.
- `demand_chain.py` `CHAINS` (e.g. `ai_datacenter`: hyperscaler capex → tiered beneficiary baskets, leading-vs-coincident flagged per chain) **is** the doc's "Capex Beneficiary Chain" feature, already generalized past one theme.
- `bottleneck.py` / `power_scarcity.py`: supply-side physical scarcity (NAICS cap-util + EDGAR scarcity language + FRED electricity series) — covers "bottleneck supplier" identification.
- `glut_watch.py`: the inverse — oversupply/exit-risk flag.
- **Missing:** no "Capex Burden Score" for the *payer* side (hyperscaler FCF compression / debt issuance / margin pressure as its own score) — `demand_chain` only uses hyperscalers as the demand-pool source, never scores their own balance-sheet risk. Cheap gap: the inputs (capex growth, FCF, debt) are mostly already on disk via EDGAR facts; this is a new pure function, not new collection.
- The "Payer vs Beneficiary 2×2 Quadrant" visualization doesn't exist — a template/UI job over scores that mostly already exist.

### Layer 5 — Corporate fundamentals / earnings confirmation
**STATUS: BUILT**, and probably the most rigorously validated layer in the codebase.
- `engine/sue.py` — post-earnings-drift, FDR-survivor (deep-history q=0.072), per-stock chip + setups confirmer.
- `guidance_gap.py` + `collectors/edgar_guidance.py` — keyless 8-K RAISE/CUT extraction: the doc's "backlog rising / orders accelerating / pricing strong" ask, done as structured NLP rather than manual transcript reading.
- `theme_fingerprint.py` leg7 (inventory-days) + leg8 (RPO/backlog) — member-XBRL level, exactly the doc's "Backlog Acceleration" signal, evidence-tier capped so an annual read can't impersonate real-time data.
- `analyst_revisions.py` (consensus delta) + `theme_revisions.py` (theme-rolled net-up/breadth) — the doc's "estimate revisions" ask.
- "Words-to-Money" / Buzzword Tourist Detector — not built as a literal ratio, but `foresight_score.py`'s evidence hierarchy (TEXT-ONLY CAP 50) enforces the same discipline structurally: a theme that is all narrative and no physical/fingerprint/FRED confirmation cannot score above 50, full stop.

### Layer 6 — Technical / market confirmation
**STATUS: BUILT** — the deepest, most mature layer in the codebase ([[cycle-intelligence-program]], subsector_rotation, sector_cycles, gex_options_magnets, RRG, MACD/StochRSI stacks across every market). No meaningful gap; the ChatGPT doc undersells what's already shipped here.
- "Thesis-Timing Mismatch Detector" — no single named module, but `foresight_sizing.py`'s posture bands (STARTER for right-but-early / ADD for entry-ready / TRIM-EXIT for GLUT-RISK+crowded) already encode exactly this decision table.

### Layer 7 — Alt-data / novel layers
- Lobbying Pressure Index: **BUILT** (Quiver lobbying, `engine/altdata.py`).
- Patents: **BUILT** (Quiver allpatents → clusters, `altdata_models.py`).
- Job postings / hiring: **PARTIALLY BUILT, deliberately.** No live job-postings feed (documented decision in `collectors/edgar_headcount.py`: no free reliable per-company source exists; scraping is fragile/ToS-bound). Substitute: 10-K headcount disclosure as an annual, coincident hiring-confidence proxy (`demand_chain.hiring_read`). Considered tradeoff, not an oversight.
- Supply-chain choke-point tracker: **BUILT** (`bottleneck.py` LOOSE→SOLD_OUT bands by NAICS).
- Regulatory/Policy Latency Score: **GAP** — no "months-to-revenue" latency estimator; nuclear/defense/grid $ flow is tracked but not tagged with an expected realization lag.
- Narrative-to-Money Divergence: **GAP as a surfaced/named metric** (the evidence-hierarchy cap is a structural cousin — see Layer 5 — but there's no literal "narrative_z − money_z" board).
- Policy Surprise Monitor: **PARTIAL** — `theme_activity`'s YoY-acceleration legs are the closest analog; no "actual ÷ expected funding" ratio exists anywhere (expectations aren't modeled — consistent with the codebase's general refusal to fabricate an "expected" baseline it can't ground).

## Novel-signal scorecard (the doc's 13 "most important" formulas)

| # | Signal | Status |
|---|---|---|
| 1 | Narrative-to-Money Divergence | GAP (structural cousin exists via evidence-cap; not surfaced as its own board) |
| 2 | Capex Receiver vs Capex Payer | HALF-BUILT (receiver side done via `demand_chain`; payer/burden score missing) |
| 3 | Buzzword Tourist Detector | STRUCTURALLY ENFORCED (evidence hierarchy), not a literal ratio |
| 4 | Funding-to-Market-Cap Ratio | GAP — cheap, data already on disk |
| 5 | Policy Latency Score | GAP |
| 6 | Elite Consensus Delta | GAP — depends on Layer-1 sourcing landing first |
| 7 | Contract Momentum Surprise | GAP — `theme_activity` has YoY-accel; run-rate-surprise variant missing |
| 8 | Bottleneck Supplier Score | BUILT (`bottleneck.py` + `power_scarcity.py`) |
| 9 | Institutional Rotation Phase (0-4) | BUILT-EQUIVALENT (`foresight_cascade` STAGE taxonomy) |
| 10 | Thesis-Timing Mismatch Detector | BUILT-EQUIVALENT (`foresight_sizing` posture bands) |
| 11 | Lobbying Pressure Index | BUILT |
| 12 | Theme Hiring Acceleration | DELIBERATELY SUBSTITUTED (annual headcount, not live postings) |
| 13 | Policy Surprise Monitor | PARTIAL (accel legs exist; no expected-vs-actual model) |

## What's actually left for Fable to scope

Ranked by (verified-missing) × (cheap given existing plumbing):

1. **Federal Register ingestion** (free, keyless, bulk API) as the anchor for a real Layer-1 policy-narrative desk — the single highest-leverage new collector, because it's the one genuinely-missing *data source* in the entire proposal. Everything else in Layer 1 is either unavailable free (think-tank full-report RSS) or already covered (IEA/EIA data, Fed/Treasury official feeds).
2. **Funding-to-Market-Cap Ratio + Capex Burden Score** — both pure functions over data already on disk (USAspending/`theme_activity` $ + EDGAR facts market cap/FCF/debt). No new collectors.
3. **Contract Momentum Surprise (run-rate variant) + Pipeline-to-Award Conversion** — extend `theme_activity.py`'s existing `SOURCES` table; not a new engine.
4. **US sector-ETF flow-velocity engine** — port the CN/HK Flow Compass architecture ([[capital-flow-velocity-desk]]) to US sector ETFs. The one real gap in Layer 3.
5. **Elite Consensus Delta + Policy Narrative Heatmap UI** — depends on #1 landing; then reuses the `macro_news._source_weight` tiering pattern already proven out.
6. **Narrative-to-Money Divergence as a surfaced board** — a genuinely new, cheap visualization over legs (bottleneck/theme_activity/theme_revisions) that already exist; currently only implicit via the scoring cap.
7. **Policy Latency Score + Policy Surprise Monitor** — lowest priority, hardest to ground honestly (both require modeling an "expected" funding/timeline baseline the codebase has otherwise refused to fabricate).

**Not recommended:** building a second, parallel "Institutional Sector Rotation Radar" page from scratch. `site/foresight.html` already **is** this page, built more rigorously (forward-graded, evidence-capped, None-on-shortfall) than the ChatGPT spec describes. Re-skinning its UI toward the doc's exact column layout (Narrative / Public-Money / Private-Capex / Institutional-Flow / Earnings / Technicals) is a legitimate ask, but new engine work should **extend** `foresight_cascade.py`/`foresight_score.py`, not fork a second competing composite — this repo has been burned before by parallel scoring systems drifting apart (see the BTC-vector override-registry history).

## Process note

Six areas of the ChatGPT doc (Layers 4, 5, 6, and the bottleneck/backlog/technical novel signals) describe, sometimes formula-for-formula, systems that are already shipped and forward-graded under [[thematic-foresight-desk]]. The one clean net-new data source is Federal Register. Everything else on the "actually build" list above is a wiring/composite/UI job over data already sitting in `data/`, not a new collector or a new methodology.
