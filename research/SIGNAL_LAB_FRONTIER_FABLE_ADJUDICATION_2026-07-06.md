# Signal Lab frontier — Fable adjudication of the 23 `advance_to_fable` candidates — 2026-07-06

Codex's Phase-0 admission screen (research/SIGNAL_LAB_FRONTIER_PHASE0_2026-07-06.md)
advanced 23 of 60 candidates "to Fable". This document is that review. Every candidate
was checked on three axes before any build was authorized:

1. **Data truth** — does the claimed in-repo data path actually exist, with real history?
   (5 census lanes; verdicts below cite exact stores.)
2. **Duplication** — is the idea already built, already tested, already killed, or already
   owned by a program ruling? (2 census lanes over engines, registries, phase-0 reports,
   program masterplans.)
3. **External contract** — does the outside feed still exist as described? (Adversarial
   fact-check against primary sources.)

Headline: the docket's self-assessed `data_state` tags had a ~30–40% error rate on the
checkable subset, and 11 of 23 candidates are duplicates, prior kills, dead feeds, or
ruling-blocked. This is not a criticism of the funnel — it is what the funnel is for.
The admission screen's own text says these are hypotheses awaiting challenge; this is
the challenge.

**Scoreboard: 11 KILL · 1 ROUTE · 1 ACCRUE · 1 QUEUED · 9 AUTHORIZED (7 build/test lanes + 1 data probe + 1 feasibility pilot).**

None of the authorizations below create a scored signal. Every harness is display-only
until it clears its pre-registered gates, and every verdict — including nulls — gets
printed in `reports/`.

---

## KILLED (11)

| ID | Candidate | Ruling |
|---|---|---|
| SLF-005 | Overnight/intraday tug-of-war | **KILL (ruling-blocked + data).** Signal Commons placed price-memory work behind Entry Intelligence P1.3; a standalone overnight/intraday factor is exactly the shape that ruling forbids. Data also fails as claimed: the massive_stock_day store is a rolling 5y window (not 10y) with **unadjusted** opens — overnight gaps across splits are spurious. Revisit only as an EI P1.3 extension study with a split-factor source. |
| SLF-007 | COT exhaustion matrix | **KILL (illegal shape + owned elsewhere).** A cross-asset crowding *matrix* is the fused escalating composite Signal Commons R3 explicitly rules illegal. The legal single-ingredient form (COT ES/NDX washout-then-rising) is already pre-registered as `esx_pos_reset` (ESX A2, 8 trials, authorized under RUL-P8) — that program owns it. The capitulation gauge already carries a COT washout leg (CONFIRMER, DSR 0.74). Also: our COT store is legacy non-commercial only; the "matrix" would need a disaggregated re-ingest for a construct we're not allowed to build. |
| SLF-010 | Lottery/MAX anti-chase | **KILL (prior kill + already live).** China MAX phase-0 was a full NO-GO (t_HAC −1.12, perm_p 0.28). The US lottery penalty (`_lottery_penalty`, Bali-Cakici-Whitelaw) is **already live** in `engine/stock_score.py`, and F3 anti-chase is the production entry gate. Data claim also wrong: 5y on disk, not 15y. Nothing left for this candidate to be. |
| SLF-012 | FINRA short-volume stress | **KILL as family.** A FINRA short-volume confirmer is already live (`engine/short_volume.py`) and its own docstring disclaims standalone edge. Red-team adds: the feed is off-exchange-only with a non-stationary denominator (off-exchange share drifted up over the sample) — a raw short-ratio backtest is structurally biased. The 2018+ backfill IS authorized — as control data for SLF-001, not as a signal. |
| SLF-025 | Opportunistic insider cluster | **KILL (hypothesis already exhausted, 24h ago).** ESX Amendment 2 ran exactly this — I1/I2/I3 including the opportunistic net_usd_mcap≥p80 filter — completing 2026-07-05: unconditional strata ADVERSE, opportunistic filter null/adverse, no chip. The docket's proposed first gate ("incremental IC over current insider factor") has already been run and failed. |
| SLF-027 | Net issuance / dilution shock | **KILL as family.** `net_issuance` is an existing signal_factory leg; `edgar_dilution` tripwires are live; the adjacent investment factor (asset growth) was FDR-tested and failed. Any residual idea is a conditional pairlet on the existing leg under the factor-family trial budget — queued behind SLF-038's pairlet, not a frontier family. |
| SLF-034 | 8-K item taxonomy surprise | **KILL (duplicate).** `eightk_velocity` (material-8K Poisson surprise z) is an existing factor leg, and the Special Situations desk runs a 16-category 8-K item taxonomy in nightly production. The candidate re-describes built infrastructure. |
| SLF-035 | Guidance revision language | **KILL (duplicate + empty store).** `engine/guidance_gap.py` (Foresight T3) already computes RAISING/CUTTING bands from 8-K guidance language. The store has **9 rows across 7 tickers** — there is nothing to backtest; forward accrual is owned by the foresight desk. |
| SLF-039 | Inventory build vs sales slowdown | **KILL (data can't carry the construct).** Inventory exists only in *annual* statements at 55% coverage (~751 tickers) — the quarterly construction the thesis needs is impossible from our EDGAR crawl, and the adjacent Sloan accruals factor was FDR-killed. The existing inv-vs-sales display sensor in stock_fundamentals stays as-is. |
| SLF-050 | China northbound impulse | **KILL (feed is dead; we already buried it).** HKEX ended daily northbound net-buy disclosure effective 2024-08 (net columns null since 2024-08-19 in our own store; `NORTHBOUND_FROZEN='2024-08-16'` in engine/flow_velocity.py). The china reassessment already measured aggregate northbound timing IC ≈ dead and ranked replacements — deep-discount blocks, already wired. Docket `data_state` corrected ready→blocked. |
| SLF-059 | EIA petroleum inventory surprise | **KILL (surprise not buildable free + prior rulings).** No free PIT consensus exists (API bulletin is paywalled); a model-based surprise is a different, weaker construct. OIL_PHYSICAL_TIGHTNESS already ruled EIA inventory display-only (seasonal-z shipped), and the 38y carry phase-0 killed curve-structure timing wrong-signed. |

## ROUTED (1)

- **SLF-026 Insider sponsorship after solvency repair** → **ESX Amendment 2 reserve docket.**
  Distinct conditioning from SLF-025 and genuinely untested, but ESX A2's 2-trial reserve
  is the only legal entry point for new insider strata. Registered there for that program
  to spend (or decline) its reserve; Altman-Z solvency axis already computed in
  `engine/stock_fundamentals.py`.

## ACCRUING (1)

- **SLF-036 Analyst revision breadth** → **ACCRUE, come back ≥2027-01-15.**
  The equity_revisions store began accumulating 2026-06-16; there are 12 daily snapshots.
  No PIT history exists to backtest (yfinance serves snapshots only). The forward store
  captures the right fields (net_up_30d, breadth, n_analysts). Baseline at test time:
  `engine/analyst_revisions.py` delta already in stock_score.

## QUEUED (1)

- **SLF-038 Gross-margin inflection** → **QUEUED pairlet, factor-family budget.**
  `gross_margin_trend` is an existing signal_factory leg; the inflection variant is a
  legitimate small pre-registered pairlet (per the standing factor-kill-interaction
  feedback), on statements_quarterly (2009+, PIT via filed date, ~750–850 non-financial
  tickers). Not a frontier family; runs when the factor-family budget next opens.

## AUTHORIZED (9)

Seven build/test lanes dispatched 2026-07-06, plus one data probe and one feasibility pilot.
Trial families are logged in `data/trial_ledger.jsonl` at generation. Pre-registered gates
live in each harness script header; summarized here.

| Lane | ID | What was authorized | Expected home |
|---|---|---|---|
| L1 | SLF-053 | **Execute H3 as pre-registered** (research/HK_CANADA_H3_PREREG.md; merged into HK/Canada program — not a new family). 25-pair A/H panel, 2001→2026, own-history percentile tilt. | per prereg |
| L2 | SLF-006 | **Event-study of the existing `treasury_supply.absorption_z`** (681 auctions, 2016→2026). Quintile forward TLT/IEF 1/5/21d, HAC t + bootstrap, duration-trend baseline, split-half. Tail leg struck (needs paid when-issued data). No new engine. | display-confirmer or null |
| L3 | SLF-056 | **AUC/event phase-0 of the existing `funding_stress` composite** (OFR SOFR series 2018→2026; honest small-n: ~3 stress episodes, leave-one-episode-out). Tests whether the CONTEXT ruling should upgrade to de-escalation-gate input. | context confirmation or de-esc input |
| L4 | SLF-051 | **Market-level China margin ROC impulse** on 16y aggregate balance (2010→2026). De-escalation/conditioning framing only (Signal Commons R3-legal); name-level variant stays dead (measured wrong-sign). Baselines: CSI300 trend, margin_froth alert. Leave-one-cycle-out incl. 2015 deleveraging. | conditioning gate candidate |
| L5 | SLF-001 | **New SEC FTD collector** (2004→, semi-monthly, symbol column included) + panel (FTD/float, FTD$/ADV, rising-z) + 21/63d rank-IC phase-0 with pre-registered confounds: net-CNS semantics, ETF exclusion, T+35 cyclicality, 30-day publication lag. Controls: size, momentum, FINRA short_ratio (2018+ backfill authorized as control store). ≤6 variants, BH-FDR q≤0.10. | short-side confirmer |
| L6 | SLF-055 | **New NY Fed primary-dealer collector** (1998→, weekly, era-aware splice pre-registered as a confound) + inventory/fails z confirmer study vs MOVE/term-slope/absorption_z baselines. | funding-stress confirmer (display) |
| L7 | SLF-048 | **Wikipedia attention backfill 2015-07→now** (existing collector, keyless, throttled) + the phase-0 the collector docstring already promises (`wiki_attention_phase0`): attention z-shock → 5/21d forward, pre-registered direction = fade in small-cap no-news shocks. | fade-risk confirmer for existing chip |
| L8 | SLF-052 | **Data probe only:** attempt akshare historical zt_pool backfill; harden store to append-only. NO signal test — display-only ruling stands until PIT history exists (store currently holds ~5 dates). | accrual registration |
| L9 | SLF-031 | **Feasibility pilot only:** 20-ticker lazy-prices spike (EDGAR full text, 10 req/s law, similarity metrics, cost model) + design doc + draft pre-registration. No signal claims; text evidence-class ≤50 cap acknowledged. | design doc |

## Docket corrections (written back into `engine/signal_frontier_docket.py`)

- SLF-050: `data_state` ready→blocked (feed dead 2024-08); verdict advance→graveyard_now, note cites regulator cessation + in-repo replacement.
- SLF-059: first_gate rewritten — "surprise" requires paid consensus; free construction is seasonal-model error only.
- SLF-012: note added — off-exchange-only coverage, non-stationary denominator; duplicate of live confirmer.
- SLF-006: tail leg struck from feature list (paid when-issued required).
- History-depth corrections: SLF-005/010 (5y rolling, unadjusted), SLF-036 (PIT starts 2026-06-16), SLF-048 (126d on disk, API serves 2015-07→), SLF-052 (~5 dates on disk), SLF-001 (22y, understated), SLF-012 (16y, understated), SLF-055 (28y, understated).

## Rubric ruling (for the next docket)

The admission screen's four largest-weighted inputs (literature, orthogonality, complexity,
prior) are self-assessed by the model that proposed the candidates, while the two
objectively checkable inputs (data_state, PIT) are the ones this audit found wrong.
Standing rule for future dockets: **`data_state` must be earned by a fetch receipt**
(URL + first/last date + field list + lag) before a candidate may carry `ready`, and any
candidate whose family already appears in the signal-lab registry, a phase-0 report, or a
program masterplan must cite it or be auto-demoted. LLM screens may rank the queue; they
may not originate "ready" claims.

*In plain English: Codex proposed 60 ideas and 23 looked ready to test. We checked every
one against what's already built, what's already been killed, and whether the data really
exists. Eleven were mirages — already done, already dead, or built on feeds that no longer
publish. Nine survived with real work attached, and those are now being built and tested
with the gates written down before the results are seen.*
