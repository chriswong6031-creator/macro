# Transmission Intelligence (TXI) — masterplan (by Fable)

Date: 2026-07-24
Status: CHARTER + adjudication of record. Operator-directed (2026-07-24 session): make the
system "aware of risks and correlations, market turmoil, risks brewing in themes/sectors/
names"; generalize transmission chains (oil→inflation→yields→duration derating) into a
permanent, self-improving causal knowledge store feeding watchlist risk, Terminal research
desk, Prophet context, rotation/WTBN, Neural Web lobes, and portfolio bots.
Registries consulted: `docs/ACTIVE_BUILD_MAP.md` (no colliding open lane),
`research/DO_NOT_REBUILD.md` rows 44/45/104/106, `CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md`
(CHF-R1..R17 — TXI RIDES this case law, §4), `PORTFOLIO_RISK_DESK_MASTERPLAN_BY_FABLE.md`,
`WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (WRI), transmission engine suite (§2).

## 0. One-line verdict

Do NOT build a new causal brain — **compose the three organs that already exist** (the
calibrated transmission engines, CHF's hypothesis metabolism, the per-ticker fundamental/
sensitivity substrate) into the one thing none of them does alone: **staged cascade
tracking with per-name blast-radius resolution** — a versioned chain library whose every
hop is an observable detector, whose activations accrue a forward calibration ledger
autonomously, and whose current state reaches every consumer surface as display-tier
context (authority only ever via the gauntlet).

## 1. Honest framing (the "superintelligent" ask)

No system becomes "superintelligent." What IS buildable — and is a real moat — is a
**compounding, self-auditing causal-context organ**: hypothesis generation is cheap (LLMs
make narratives for free); the moat is the **verification economy** — a machine that
generates chains cheaply, kills them honestly, and retains survivors with *calibrated,
regime-conditional* evidence nobody else maintains. The house epistemics (prereg, forward
ledgers, null libraries, kill registries) are exactly this economy; TXI industrializes it
for multi-hop macro→micro cascades. Accuracy comes from three compounding stores: chains
that survived falsification, per-hop conditional base rates from 25y+ of collected data,
and an episode library of past activations with outcomes. That is the whole trick; there
is no fourth ingredient.

## 2. What ALREADY exists (inventory of record — do not rebuild)

| Organ | Where | What it does today |
|---|---|---|
| Rate/inflation transmission map | `engine/rate_inflation_transmission.py` → `data/transmission/latest.json` (+`transmission.html`) | 1st/2nd/3rd-order pass-through of rate/inflation state into per-asset headwind/tailwind, with MEASURED split-half Spearman-IC coefficients (`calibration.json: transmission_matrix, scenario_betas`), conditional scenarios, inflation decomposition, `chains`+`scenarios` blocks, change feed. Display/LLM-context only — its own scored-gate honestly found NO leg robust enough to score. |
| Dollar/FX channel | `engine/forex_transmission.py`, `engine/transmission_context.py` | Dollar-channel composer + hero + diff-changes; NW fx_dollar lobe (#2845). |
| China policy channel | `engine/china_policy_transmission.py` | Policy → sector pass-through, CN lane. |
| Per-stock rate channel | `engine/stock_macro_sensitivity.py` → per-ticker `macro_sensitivity` block | Calibrated per-name rate beta, duration tier, regime headwind/tailwind — the oil-example's LAST hop, for the rates channel, per name, already shipped. |
| Causal Hypothesis Factory (CHF) | `data/neuralweb/causal_{edges,mechanisms,nulls,frontier,brainstorm_runs,surprise_queue}.jsonl/json`, `mechanism_pathways.json(+history)`, `scripts/run_causal_brainstorm.py` + ingest/pack/handoff | The idea immune system: deterministic edge scout, LLM mechanism-card factory behind a schema firewall, null/frontier memory, brainstorm runner (autonomy behind the CHF-R8/R17 operator gate). Display-tier by charter; never originates authority. |
| Book-structure risk | WRI (PR #3405): `risk_core.js` + factor model (`factor_betas.json` betas+cov+stress cov+idio, 1,529 names) | Per-book ENB/MCTR/implied-ρ + stress lens + per-name lanes on the watchlist. |
| Fundamental substrate | per-ticker `stockdata/<T>.json` | `financials` (debt, FCF, margins, multiyear), `valuation` (fwd PE tiers), `factors.radar` (investment/profitability z), `earnings`+`revisions`, `positioning`, `smart_money`, `ladder` stage, `personality` — the raw material of blast-radius screens. |
| Consumer seams | `world_state` composer + `synapse` + `mastermind _summarize` (darkpool_context wiring pattern, #3314); `portfolio_ctx.v1` + brief composer (#3306/#3313/#3323); Terminal via macro brain gateway (#3379) | Proven pattern for feeding a new context organ to the chatbot, portfolio bots, and Terminal. |

**The gap in one sentence:** the transmission map knows the *current* pressure per asset
class; CHF knows *candidate mechanisms*; the substrate knows *per-name vulnerability* —
but nothing tracks a cascade as a **staged episode over time** ("hop 2 of 4 confirmed,
hop 3 pending, historical P(hop3|hop2) = X in this regime") and nothing resolves an armed
chain to **which tickers are in the blast radius via which named channel**.

## 3. Operator coverage questions — audited answers (as of 2026-07-24)

| Question | Today | Path (wave) |
|---|---|---|
| HK / China / Canada equities in book-risk math | ❌ factor model is deliberately US-clock (onshore proxies timezone-contaminated — `factor_exposure.py` docstring); HK/CN/CA names read "unmodeled" in WRI; they DO have their own desks/universes (hk_stocks, china flow 1,554 names, canada_standouts) | parallel clock-safe factor models: `factor_betas_hk.json` (HSI/HSTECH/CGB/USDCNH factor set), CA via TSX composite (W6) |
| Crypto positions | ❌ BTC is a FACTOR but BTC-USD/ETH/crypto-ETFs aren't in the beta universe → unmodeled | add cached crypto tickers + IBIT-class ETFs to the universe — small W6 item |
| Small caps | ✅ in the ~1,529-name universe; factor model honestly reads them idio-heavy (own bets — correct, not a gap) | — |
| Stage analysis / qualitative | ⚠ partial: `ladder` stage + `entry_signal` + `personality` feed WRI L1 lanes; `view.falsifiers`/moat blocks not yet surfaced | join L1 drawer in WRI iteration (W5) |
| Options data (EOD/intraday) | ❌ per-ticker `gex`, `iv_spread`, `vol_squeeze` + GEX desk exist but no WRI lane (Risk Desk §3 deferred the dealer lane pending #1845) | options/dealer lane joins L1 when #1845 stabilizes (existing come-back, ~08) |
| Cross-asset / economic / transmission.html | ⚠ exists and is calibrated (§2 row 1) and feeds NW — but is NOT composed into per-name risk anywhere | **this program's core: P1+P2** |
| The oil→yields→derating chain specifically | ⚠ hops exist separately TODAY: oil trend (26y series), breakevens/real-10y state (in `latest.json` now: real 10y 2.35% restrictive-rising), per-name duration tier (`macro_sensitivity`), refinancing/capex/FCF screens (`financials`, `factors.radar.investment`) | worked spec §6 = wire them into ONE staged chain + name resolver (W1–W2) |

## 4. Law compliance (the spine that keeps this buildable)

- **CHF-R1/R2 (ride, don't re-register):** TXI is a PROGRAM composing existing organs. New
  chain proposals ride CHF's already-adjudicated brainstorm/proposal lane and its
  autonomy gate (CHF-R8/R17) — TXI builds NO second LLM loop, no new registration family.
- **DNR row 45 (CHF Article 1/2):** no causal graph ever emits an alpha score, gates a
  trade, or sizes anything. Chain states are display/context tier; any single chain's
  promotion to authority (rank/gate/alert escalation) requires its own pre-registered
  gauntlet, entering as a CONFLUENCE INPUT, never standalone (confluence law).
- **LLM de-escalation law:** LLMs propose/narrate/critique/de-escalate. Only compiled
  deterministic detectors (observable thresholds on collected series) can raise a chain
  stage. A chain with any hop that cannot be compiled to observables stays `hypothesis`
  tier and never arms.
- **PRD-R2/WRI-R2 (no fused score):** no "transmission risk score." Surfaces show named
  chains, staged states, printed hop base-rates, and per-name channel flags + counts.
- **DNR row 106 (forced-call law):** an armed chain is a WATCH item with printed
  conditional base rates — never a directional call pinned to a signal surface.
- **Nulls first-class:** hop calibrations that come back null print as null (the
  rate/inflation engine's own scored-gate honesty is the template); a chain that fails
  its falsifiers is killed into the null library (CHF `causal_nulls`) with the kill class.
- **Render budget:** all mining/backtesting off the render path (background lanes,
  artifacts to R2 if heavy); nightly adds only cheap state evaluation of compiled chains.

## 5. Rulings

- **TXI-R1 (chain ledger is law-shaped knowledge):** chains live in
  `knowledge/transmission/*.yaml` — versioned, PR-reviewed, human-auditable. Schema:
  nodes (observable, source artifact + threshold), directed hops (sign, lag window,
  regime conditions, mechanism prose, provenance: theory + episodes), falsifiers, null
  model (what naive baseline the chain must beat), exposure screens (per-name fields).
  A CI validator rejects chains whose nodes don't resolve to collected artifacts.
- **TXI-R2 (staged state machine):** the compiler turns each chain into a deterministic
  episode tracker: `dormant → arming → propagating(hop k) → expressed | failed | expired`,
  evaluated nightly from existing artifacts; every transition appends to
  `data/transmission/chain_episodes.jsonl` (forward ledger, nightly-advanced only).
- **TXI-R3 (blast radius = named channels, per name):** an armed chain resolves downstream
  exposure via its screens over the per-ticker substrate → per-name flags like
  `refinancing_channel` / `capex_borrower` / `long_duration_valuation` / `fcf_burner`,
  each with the field receipt. Flags are display-tier context; they may join WRI L1 as a
  lane and Risk Desk-style ladders only as WATCH-grade inputs.
- **TXI-R4 (calibration is the product):** every hop carries measured conditional forward
  stats (P(hop_{k+1} within lag | hop_k, regime), effect sizes on the downstream cohort)
  from BOTH the historical episode miner and the forward ledger — printed with n and
  windows, Brier-tracked as forward episodes resolve. Hypothesis-tier hops print
  "untested" honestly.
- **TXI-R5 (three loops, autonomy honestly scoped):** Loop A (forward accrual +
  calibration update) fully autonomous. Loop B (historical episode mining + event
  studies) autonomous batch. Loop C (new-chain proposal: tape anomalies via CHF
  surprise_queue, literature/theory corpus, lessons-ledger postmortems) runs through
  CHF's brainstorm lane under ITS autonomy gate — proposals auto-compile + auto-backtest
  where fields exist, land as hypothesis-tier. Promotion of anything to authority
  remains gauntlet-gated. "Self-improving without human intervention" = A+B+C accrual;
  humans stay at exactly two points: chain-library PR review and promotion rulings.
- **TXI-R6 (regime conditionality first-class):** every hop declares the regimes where it
  should and should NOT work (the operator's own example needs the supply-vs-demand oil
  distinction); calibration is computed per declared regime cell, never pooled-only.
- **TXI-R7 (one artifact, many consumers):** one canonical emit
  `data/transmission/chain_state.json` (`transmission_chains.v1`: active episodes, hop
  states, base rates, per-name blast lists, receipts) distributed via the proven
  darkpool_context pattern: world_state composer + synapse + mastermind `_summarize` +
  `portfolio_ctx` merge + baked display JSON. Consumers (watchlist WRI lane, Terminal
  research desk context field, Prophet/WTBN/rotation CONTEXT chips, portfolio bots) read
  the artifact — no consumer computes its own chain state.
- **TXI-R8 (transmission engines are hop libraries, not rivals):** the calibrated
  rate/inflation matrix and dollar/china channels become measured EDGES inside chains
  (their ICs are hop-strength priors); TXI never recomputes what they measure.
- **TXI-R9 (coverage extensions ride WRI):** crypto/HK-CN/CA factor models and the
  options lane extend WRI's book math under WRI rulings; TXI consumes whatever coverage
  exists and prints coverage honestly (PRD-R6 pattern).
- **TXI-R10 (naming/versioning):** chain ids are stable slugs; edits bump `rev` with a
  changelog line; kills move the file to `knowledge/transmission/killed/` with the kill
  record — the library IS the permanent knowledge store the operator asked for.

## 6. Worked spec v0 — the operator's oil chain (every hop maps to shipped artifacts)

```yaml
chain: oil_inflation_duration_derate       # knowledge/transmission/oil_inflation_duration_derate.yaml
rev: 0                                      # tier: hypothesis (until Loop B backfills)
nodes:
  oil_shock:        {src: commodity/signals_oil,     test: "ret_60d > +25% AND MA50 slope up"}
  breakeven_rise:   {src: transmission latest.state, test: "T10YIE Δ30d > +15bp"}
  yield_rise:       {src: transmission latest.state, test: "real_10y direction=rising AND Δ63d > +30bp"}   # today: +43bp ✓
  duration_derate:  {src: factor model + cohorts,    test: "long-duration cohort RS_63d < 0 vs SPY"}
hops:
  - {from: oil_shock, to: breakeven_rise, sign: +, lag_d: [5,60],
     condition: "supply-driven shock (global PMI not accelerating); demand-driven oil = different chain",
     mechanism: "energy passthrough into headline, then expectations",
     prior: transmission_matrix[oil→breakevens] IC if present, else theory}
  - {from: breakeven_rise, to: yield_rise, sign: +, lag_d: [0,90], condition: "Fed not capping (no YCC/QE regime)"}
  - {from: yield_rise, to: duration_derate, sign: +, lag_d: [0,120],
     prior: stock_macro_sensitivity calibration (shipped)}
falsifiers: ["oil +25% with breakevens flat 60d in a non-QE regime", "yield_rise with long-duration cohort RS>0 for 120d"]
null_model: "does chain-conditioning beat unconditional yields-momentum on the same cohort?"
exposure_screens:                            # per-ticker, all fields SHIPPED today
  long_duration_valuation: "macro_sensitivity.duration==long OR valuation.forward_pe tier rich"
  refinancing_channel:     "financials.raw.debt_lt/assets high AND earnings weak (interest-cost proxy)"
  capex_borrower:          "factors.radar.investment z < -1.5 AND fcf_margin < 0"
  fcf_burner:              "financials.fcf_margin < 0 AND multiyear cash trend down"
provenance: {theory: [cost-push passthrough, duration math], episodes: [1973-74, 1990, 2021-22], added_by: operator 2026-07-24}
```

Nightly: the tracker reads three existing artifacts, stamps the episode at
`propagating(hop 2→3)` (real-10y leg is ALREADY confirming on today's data), resolves the
four screens over the book/universe, and every consumer surface shows: *"Oil→rates chain
propagating (2 of 3 hops confirmed). In your book: NVDA (long-duration), PLTR-class names
(FCF burner). Historical: hop-3 followed within 120d in N of M past episodes (untested
regime cells printed)."* Review language; no calls.

## 7. Seed library v0 (chains whose every node is already collected; one line each)

oil→breakevens→yields→duration derate (§6) · dollar spike→EM/commodity/multinational-EPS
headwind (forex_transmission edges) · credit spreads widen→refinancing-dependent smallcaps
(HYG/LQD collected) · china credit impulse→industrial metals→miners (china engines + gold/
copper series) · vol-regime shift→systematic deleveraging→high-beta unwind (vol_regime +
positioning) · curve bear-steepening→banks NIM tailwind (curve state shipped) · liquidity
drain (TGA/RRP rebuild)→beta compression (liquidity_overlay shipped) · policy/tariff→
sector passthrough (china_policy_transmission) · crowding/positioning extreme→unwind risk
(positioning + smart_money HHI) · earnings-revision breadth rollover→theme derating
(revisions universe-wide) · freight/PMI inventory cycle→cyclicals (business_cycle block) ·
wage stickiness→margin compression→low-margin retail (ECI in transmission state).

## 8. Waves + routing (per CLAUDE.md model routing; all off render path except cheap nightly eval)

- **W0 (this PR, docs-only):** charter. Registry rows: none killed; ACTIVE_BUILD_MAP picks
  up the PR automatically.
- **W1 — chain ledger + compiler (builder/opus):** schema validator, YAML loader, episode
  state machine, `chain_episodes.jsonl` + `chain_state.json` emits; §6 chain + 3 more
  seeds compiled; unit tests with synthetic series (arm/propagate/fail/expire paths).
- **W2 — blast-radius resolver (builder/opus):** screens→per-name flags with receipts;
  universe sweep + book intersection; coverage honesty; tests over fixture tickers.
- **W3 — episode miner + hop calibration (builder/opus, background lane):** historical
  activation scan over collected series (25y oil, rates, dollar…), per-hop conditional
  stats per regime cell, event-study cohort outcomes, calibration written back into
  `chain_state.json`; nulls printed; heavy compute → background schedule + R2 artifacts.
- **W4 — distribution (builder/opus):** world_state/synapse/mastermind wiring (darkpool
  pattern), portfolio_ctx merge, transmission.html "Cascade Monitor" section (designer/
  opus for the surface), WRI watchlist lane (chain flags join L1), Terminal context field.
- **W5 — Loop C closure (builder/opus + CHF lane):** surprise_queue → chain-proposal packs
  through `run_causal_brainstorm.py`; lessons-ledger postmortem intake; auto-compile +
  auto-backtest of proposals; weekly cadence under the EXISTING CHF autonomy gate.
- **W6 — WRI coverage extensions (builder/opus):** crypto tickers into the beta universe;
  `factor_betas_hk.json` clock-safe HK/CN model; CA; options/dealer lane when #1845
  stabilizes. (Rides WRI rulings, listed here for one-roadmap visibility.)
- Fable main loop: adjudication, chain-library review, promotion rulings, W4 surface
  design direction. Sonnet: census/mining sweeps only. Haiku: extraction only.

## 9. Non-goals

No alpha scores from graphs (Article 1/2); no autonomous trading/sizing; no new NW lobe
(two-lobe cap; TXI is a program); no second LLM brainstorm loop (CHF's); no full-graph
learners; no intraday chain evaluation v1 (nightly + existing live overlays); no
"superintelligence" claims in any user-facing copy (banned-vocab discipline applies).

## 10. Come-backs

Options/dealer lane join (#1845, ~2026-08); stock-top-hazard arm interaction review
(2026-10-07 window per its own ruling); HK/CN factor model calibration study; chain
promotion candidates' first gauntlet reads (≥1 quarter of forward episodes, per TXI-R4);
industry-factor extension for WRI implied-ρ (recorded in WRI §5-A).
