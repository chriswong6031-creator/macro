# Smart Money v2 — Ownership Intelligence Desk (masterplan + adjudication)

**Adjudicated by Fable, 2026-07-10.** Program: rebuild `smart_money.html` from a single-purpose
13F trade-tracker into a multi-axis, lag-honest **Ownership Intelligence Desk**, and expand the
data/engine substrate beneath it. Design inputs: 3-lane web research (cloning literature,
competitor surfaces, manager-universe roster) → 3 independent design proposals (practitioner /
quant-rigor / product-UX lenses) → adversarial house-law red-team on each. All three verdicts:
sound-with-fixes. This document merges the designs, adopts every red-team fix, and freezes the
interfaces. Display/context tier throughout — no gauntlet required to build (gauntlet = promotion
gate, not a build gate).

## 0. The lag thesis (why 13F is still worth a desk)

13F is quarterly with a ~45-day filing lag. The literature says the lag is fatal only for
high-turnover books: Martin & Puthenpurackal's Buffett-clone (+10.75%/yr vs SPX copying filings
one month AFTER release), Cohen–Polk–Silli "Best Ideas" (top-conviction positions outperform by
1–2.5%/qtr), and the confidential-treatment studies (informed positions outperform up to 12
months post-disclosure) are existence proofs that **low-turnover, concentrated managers' filings
retain information for quarters**. Institutional practice (GS Hedge Fund Trend Monitor, MSCI
crowding) additionally reads 13F in the **crowding-hazard** direction — which happens to be the
only signal direction house law permits for ownership data. So the desk is built on four legs:

1. **Lag-robust manager selection** — turnover/holding-period/concentration diagnostics per fund;
   whose filings survive the lag (descriptive tiers, survivor-cohort caveat printed).
2. **Consensus & conviction context** — share-class-correct most-held / new-money / within-fund
   rank boards (context-only, neutral default sorts).
3. **Crowding-hazard lens** — days-to-exit / HHI / holder-breadth read as unwind risk
   (de-escalation direction; the one legal signal direction).
4. **Timelier companion axes** — 13D/G activist stream (~5–10d lag), Form 4 insider clusters
   (~2d), FINRA short volume (daily) + short interest (bi-monthly) — each a physically separate,
   separately-stamped axis. The lag is never hidden: staleness is the hero of the UX.

## 1. Standing-law digest (what constrains this build)

- **NEXTL-U13 (killed, nondelegable):** 13F/ownership may never be a positive/bullish signal.
  Permitted signal direction: de-escalation / crowding-hazard only. Context/display: legal, encouraged.
- **Signal Commons R3:** positioning fusion illegal. No composite across 13F/insider/short/options
  axes, at any grain. Side-by-side separately-stamped columns; the USER sorts, we never blend.
- **WA-R2:** ownership fields ship as context columns, `context_only: true`.
- **RUL-N3:** sponsorship vocabulary locked to the neutral set; the four supportive mechanism
  labels are forbidden. No bullish/bearish framing on ownership reads.
- **DT-R15/DT-U1:** whale-directional claims closed; descriptive readouts only.
- **FR-8 + render budget:** EDGAR crawling off the render path; on-render compute seconds-to-~2min.
- **LLM law:** zero LLM calls in this build; all deterministic.
- **PIT law:** `filing_date` is the only look-ahead-free anchor; every surface stamps its as-of.
- **Prior nulls that bound claims here:** `engine/crowding.py` Phase-0 (crowded+extended shows NO
  forward underperformance; only marginal non-robust drawdown effect) — any crowding accrual is
  continuation against that prior, not discovery. FINRA short **interest** store is latest-snapshot
  only (no PIT history) → SI may be a live context column but never a ledger/backtest anchor
  (restates the WA-R "no PIT short-interest history" deferral). esx_insider_sponsor null is not
  re-litigated — insider is a display axis here, never a detector input.

## 2. Rulings (SM2-R1 … SM2-R12)

- **SM2-R1 (tier).** The desk ships display/context tier. The only directional element anywhere
  is the crowding-hazard read (de-escalation direction). Every 13F-derived block carries context
  framing and honest as-of stamps.
- **SM2-R2 (initiations board — the NEXTL-U13 knife-edge; adjudicated here, nondelegable).**
  The Initiations board ships ONLY in neutralized form: default sort = `filing_date` descending
  (neutral chronology); within-fund rank/tilt/`pct_portfolio`/`n_funds_initiating` are
  shown-but-not-default-sorted columns the user may sort; NO curated "consensus best-ideas" view;
  the lag-durable filter is a user toggle, default off; a permanent banner reads "research queue,
  not a buy list — ownership is context-only under standing law." A ranked-by-conviction default
  ordering would BE the struck positive signal; this form is the adjudicated boundary.
- **SM2-R3 (no fusion).** No blended field across positioning axes anywhere in engine or template.
  Crowding tier derives from days-to-exit alone. A unit test asserts the desk payload contains no
  composite across axes. Short-volume (daily) and short-interest (bi-monthly) are distinct
  constructs with distinct stamps and must never share a column or an as-of.
- **SM2-R4 (short interest).** Live context column only, stamped `settlement_date`. No SI-anchored
  ledger cohort, no SI trend claims beyond the single stored delta. ADV for days-to-exit comes from
  `data/finra/short_interest.parquet.avg_daily_vol` (stamped accordingly), falling back to yahoo
  `volume` where present; absent → null-honest "—", never imputed.
- **SM2-R5 (ledgers).** Four pre-registered display-only cohorts (§5), entry = anchor date + 1
  trading day, graded via `engine/grading.py forward_metrics` vs SPY, advanced by nightly only,
  nulls printed, frozen-until-matured. L1 is framed as manager-skill-through-lag measurement (NOT
  an ownership signal; both directions printed; banner states NEXTL-U13 forbids positive-direction
  promotion). L2 explicitly cites the crowding Phase-0 null as its prior (continuation-of-accrual).
  126/252d legs are labeled accrual-only until ~2027-28; the first read is at the 63d leg.
- **SM2-R6 (roster).** Universe expands 17 → ~54 curated funds (§6) with per-fund metadata. A
  deterministic verification gate (`scripts/verify_13f_ciks.py`: name match + 13F-HR within 18
  months against `data.sec.gov`) blocks any unverified CIK from entering config. Quant/market-maker
  books (RenTech, Citadel, Millennium, Two Sigma, DE Shaw, Jane Street, SIG) are excluded BY LAW
  from consensus/crowding math — documented in config. Avenue and Silver Point are dropped (stale
  filers). Scion: `status: closed`, history retained, ingestion stops. Manager grades print a
  survivor-cohort caveat (roster curated in 2026 = survivors; grades are descriptive, not a
  manager-selection edge).
- **SM2-R7 (amendments).** Collector additionally ingests 13F-HR/A as separate PIT snapshots
  (own `filing_date`, suffixed files). Originals remain the scoring anchors; amendment deltas are
  display-only (the confidential-position-reveal tell). Engine default paths read originals only.
- **SM2-R8 (manager_quality.py).** Deprecation DEFERRED — it feeds per-stock quality badges
  site-wide; swapping graders is a separate scoped PR with a byte-diff audit. The redundancy is
  documented here as a known follow-up.
- **SM2-R9 (naming/reuse).** The new crowding module is `engine/ownership_crowding.py` —
  `engine/crowding.py` already exists (per-stock fragility flag with a filed Phase-0). Reuse the
  existing days-to-exit semantics (`days_to_exit_at_10pct_adv` lineage in build_stock_library);
  do not mint a divergent second definition of the same metric.
- **SM2-R10 (feeds).** `smartmoney.json` (by_ticker/most_held/overlap/trend) is produced by
  `build_site.py`; the desk build calls `compute_smart_money()` itself and writes both
  `smartmoney.json` and the new `smartmoney_desk.json` (build_site's later overwrite is idempotent).
  Cost-basis band is labeled "implied avg entry (quarter-end proxy)" — never "cost basis".
- **SM2-R11 (freshness UX).** The filing-season clock (next deadline countdown, quarter state),
  the filed-vs-pending grid, and the per-axis as-of stamp rail are REQUIRED page elements. Every
  table row carries its axis's timeliness chip. Staleness is a first-class element, not fine print.
- **SM2-R12 (verification bar).** Terminal-UI quality bar applies: the page builder works
  mockup-first, renders with prod-shaped data, and ships Playwright screenshots (desktop + mobile
  + dark + zh) for review. Runtime of the desk build is benchmarked at the full roster and must
  stay in the seconds-to-~2min envelope. CI locals before push: `check_validated_claims`,
  inline-js on rendered page, no ZH in `title=`.

## 3. Page specification (single scroll, command-deck; extends report_base)

S0 **Freshness header** — filing-season clock (days to next 45-day deadline, quarter state ring),
filed-vs-pending dot grid (fund × latest quarter, filing_date on fill), per-axis as-of rail:
13F (red/amber tier) · 13D/G · Form 4 · short volume · short interest — five stamps, five dates.
S1 **Ownership event wire** — reverse-chron merged feed (13F deltas, 13D/G events, Form 4 clusters
on roster names), each row typed + natively stamped; 13F-HR/A amendment lane (Δ>±20% flags).
Filters: type, window, magnitude, roster-ticker. Strictly concatenation, never blending.
S2 **Manager desk** — upgraded leaderboard: existing grades/median-excess/hit/63d + NEW sell-skill,
turnover tier, effective holding period, concentration (top-10 %), #holdings, style tag, status;
lag-durability tag (heuristic label, descriptive); featured head-to-head demoted to a card;
survivor-cohort caveat in the footnote. Per-fund accordion retained + enhanced (turnover chip,
filing freshness, window-dressing micro-flags on single-quarter sub-1% "new" rows).
S3 **Grand portfolio** — share-class-collapsed consensus board: #funds holding, Δholders QoQ,
holders sparkline, aggregate $, max single-book %, HHI, #funds-top10, since-filing excess.
Default sort: aggregate tracked $ (size fact). Counts language only ("holders 7 → 9"), no
direction words, no "most-loved" hero framing.
S4 **Crowding & unwind radar** — days-to-exit (agg tracked shares ÷ ADV), crowding tier
(elevated/moderate/low from days-to-exit quintile alone), HHI, holder count, max book %, implied
avg entry band (P25/50/75, quarter-end proxy) + n-underwater; then SEPARATE short-volume columns
(daily stamp) and SEPARATE short-interest columns (settlement stamp). Banner: "hazard readout,
not a buy or sell." Methodology footnote cites the Phase-0 prior.
S5 **Initiations (research queue)** — per SM2-R2 neutralized form. Columns: ticker, issuer,
filer(s), action, within-fund rank, tilt, % book, n_funds_initiating, fund turnover tier, filing
date, since-filing move, persistence flag (pending for latest quarter).
S6 **Activist situation monitor** — 13D/G stream from `beneficial_ownership.regime_for`
(activist/flip/passive/custodial + high/low/noise), flips-and-fresh-activism lane on top,
custodial rows collapsed as labeled noise, "also held by N tracked funds" cross-chip,
since-filing move, 5-business-day deadline footnote (post-Feb-2024 regime).
S7 **Ticker dossier** — client-side search; per-name card stacking the axes as separate stamped
blocks: 13F holders/trend/crowding · 13D/G state · insider power · short volume · short interest.
No composite header number. Caption: "independent lenses, independent as-of dates."
S8 **Forward ledger strip** — the four cohorts, each: entry rule, #entered, entry as-of,
since-entry excess once matured, "accruing" chip. Banner: pre-registered, display-only, no
authority; nulls printed.

Bilingual EN/ZH throughout via the existing `t()` pattern; no ZH inside `title=`; `.sm` token
system extended with freshness-tier dots (green ≤11d / amber ≤45d / red >45d); tables sortable
via small vanilla JS; mobile = stacked cards per existing breakpoints.

## 4. Engine plan (all deterministic, zero LLM)

- `engine/manager_lag.py` (NEW): `quarterly_turnover` (issuer-level, Σ|Δvalue|/(2·avg book)),
  `effective_holding_period` (median position survival in quarters), `lag_tier`
  (low<25% / med / high>75% + config hint fallback when <3 snapshots), `concentration_top10`,
  `n_holdings`. All per-fund descriptive; n printed everywhere.
- `engine/ownership_crowding.py` (NEW): `days_to_exit` (aggregate tracked shares ÷ ADV per
  SM2-R4), `crowding_tier` (quintile of days-to-exit only), `implied_entry_band`
  (value_usd÷shares P25/50/75 + n_underwater vs latest close), HHI/holder stats reused from
  `overlap_stats`. Display path uses current ADV; any ledger path uses anchor-dated ADV
  (unit-tested: no bar after anchor is read).
- `engine/smart_money.py` (EXTEND): share-class collapse via `config/share_class_equiv.yml`
  (GOOG/GOOGL, BRK.A/B, FOX/FOXA, UA/UAA, …) + 6-char CUSIP-stem fallback, applied to consensus
  counts everywhere; per-fund position rank + within-fund tilt; window-dressing persistence flag;
  amendment-delta detector (same period_end, original vs /A). OpenFIGI degradation: WARN log +
  per-fund resolution coverage % in payload.
- `engine/manager_trades.py` (EXTEND): surface `sell_skill` and `n_buys_h` into leaderboard rows
  (already computed); add manager_lag/concentration fields to scorecards; horizon ladder for the
  decay chips {21,63,126}d median since-filing excess with per-horizon n (252d frozen-until-matured).
- `engine/ownership_event_wire.py` (NEW): non-fusing chronological merge of 13F deltas + 13D/G +
  Form 4 on roster names; filing-season clock + next-deadline date math; filed-vs-pending grid.
- `engine/ownership_ledger.py` (NEW): cohort writer/grader per §5, nightly-only advancer (copy the
  guard pattern from an existing forward ledger), append-only parquets under
  `data/smart_money/ledgers/`.
- `scripts/build_smart_money.py` (EXTEND): call `compute_tracker()` + `compute_smart_money()` +
  the new engines; write `smartmoney_tracker.json` (unchanged schema, plus additive manager
  fields), `smartmoney.json`, and `smartmoney_desk.json`; render the rebuilt template; log a
  runtime benchmark line.

**Desk payload (frozen interface, `site/factordata/smartmoney_desk.json`):**
`built`, `freshness` {axes:[{key,label,asof,lag_note,tier}], next_deadline, days_to_deadline,
quarter_state, filed_pending:[{slug,name,period_end,filing_date,status}]},
`wire` [{date,axis,type,slug,fund,ticker,issuer,action,magnitude,unit,asof_note}],
`initiations` [{ticker,issuer,funds:[{slug,name,action,rank,tilt,pct_book,turnover_tier}],
n_funds_initiating,filing_date,since_excess,persistence}],
`grand_portfolio` [{ticker,issuer,n_funds,d_funds_qoq,holders_series,agg_value_usd,max_book_pct,
hhi,n_top10,since_excess,asof}],
`crowding` [{ticker,issuer,n_funds,agg_value_usd,hhi,max_book_pct,days_to_exit,crowding_tier,
entry_band:{p25,p50,p75,n_underwater},short_volume:{ratio,trend_pp,ratio_z,asof},
short_interest:{days_to_cover,si_change_pct,settlement_date}}],
`activists` [{date_filed,filer,ticker,issuer,form,state,signal,n_tracked_holders,since_excess}],
`managers` {slug:{turnover_pct,turnover_tier,holding_period_q,concentration_pct,n_holdings,
style,status,coverage_pct,sell_skill,n_buys_h,decay:{h21:{med,n},h63:{med,n},h126:{med,n}}}},
`ledger` {cohort:{rule,entered_this_cycle,entry_asof,legs:{h21,h63,h126,h252},status}}.

## 5. Pre-registered forward-ledger cohorts (frozen 2026-07-10)

Grader: `engine/grading.py forward_metrics`, benchmark SPY, entry = anchor + 1 trading day
(next-bar fill), horizons 21/63/126/252d, append-only, nightly-advanced, nulls printed.
- **L1 manager-skill-through-lag:** every new/add ≥1% of book filed by a fund with computed
  `turnover_tier == low`; anchor = that fund's `filing_date`. Question: does low-turnover managers'
  disclosed conviction retain excess through the lag (manager-skill measurement, both directions
  printed; NOT an ownership signal; positive-direction promotion barred by NEXTL-U13).
- **L2 crowding-hazard (continuation):** tickers entering the top days-to-exit quintile at a
  filing cycle; anchor = the filing_date completing the read, anchor-dated ADV. Metrics: forward
  max-adverse-excursion + downside semi-deviation vs roster, alongside mean excess. Prior:
  the filed Phase-0 weak/non-robust drawdown result — this accrues against that prior.
- **L3 activist events:** `state ∈ {activist, flip}` with `signal == high`; anchor = `date_filed`.
  Question: does the classified feed reproduce announcement + drift on live data.
- **L4 consensus control:** top-20 by #funds holding at each cycle; baseline the others read against.
No short-interest-anchored cohort (SM2-R4). First read: 63d legs ≈ 2026-10-15; 126/252d legs
mature 2027+. A null on any cohort blocks nothing and is retained as confluence context.

## 6. Roster (17 → ~54; every new CIK gated by verify_13f_ciks.py)

Existing 17 kept (scion → `status: closed`). New, by style (slug / CIK-unverified / turnover hint):
- superinvestor_value: giverny 1641864, aquamarine 1404599, punchcard 1631664, altarock 1631014,
  dorsey 1671657, greenlea 1766504, ensemble 1387366 (all low).
- quality_growth: tci 1647251 (low), egerton 1581811 (low-med), ako 1376879 (low, verify recency),
  polen 1034524 (low), durable 1798849 (med).
- tiger_crossover: coatue 1135730 (high), d1capital 1747057 (med), altimeter 1541617 (low-med),
  whalerock 1387322 (high), dragoneer 1602189 (med), lightstreet 1569049 (high).
- activist: elliott 1791786, starboard 1517137, trian 1345471 (low), jana 1159159,
  engaged 1560327 (priority-verify), sachem 1582090, corvex 1535472, effissimo 1570005
  (`coverage: us_slice_only`) (med unless noted).
- event_distressed (signal_quality: low): oaktree 949509 (high), mudrick 1655183 (high).
- sector_healthcare: bakerbros 1263508 (low), racapital 1346824 (med), perceptive 1224962 (high),
  rtw 1493215 (med), casdin 1534261 (med).
- sector_other: kimmeridge 1706220 (energy, med), basswood 1085393 (financials, med).
- macro_satellite (signal_quality: low): soros 1029160 (high).
Dropped at adjudication: avenue, silverpoint (stale filers), fundsmith (no 13F), tudor/moore,
melvin (closed), and the Category-8 quant/market-maker excludes (documented in config comment).
Config metadata schema per fund: `{cik, name, style, turnover_hint, signal_quality?, status?,
coverage?}`. `history_quarters: 12`, `backfill_quarters: 13`.

## 7. Build waves (same-day PRs)

- **PR-1 (data substrate):** this masterplan; config roster + metadata + history depth;
  `scripts/verify_13f_ciks.py` (blocking gate, report committed under reports/); collector: 13F-HR/A
  ingestion (SM2-R7) + OpenFIGI degradation warning; local off-render backfill run (54 funds × 13
  quarters) committed; collector tests extended.
- **PR-2 (engines + desk payload + page):** the four new engine modules + extensions; share-class
  equiv config; `build_smart_money.py` desk assembly; rebuilt `templates/smart_money.html.j2` +
  regenerated `site/smart_money.html`; ledger bootstrap; unit tests incl. the no-fusion assert and
  the anchor-dated-ADV PIT test; runtime benchmark; Playwright screenshots (SM2-R12).
- Reviews: opus red-team per PR; Fable merges same-day; nightly cycle verifies live accrual.

## 8. Clocks & come-backs

- 2026-08-14: Q2 filing window closes — first live filing-season-clock cycle; check filed-vs-pending
  grid + wire during the window.
- 2026-10-15: first ledger read (63d legs of L1–L4). Display read only; any promotion requires the
  full gauntlet with time-preserving nulls.
- 2027-01: program review — 126d legs, roster pruning (funds failing verification/filing lapses),
  manager_quality.py deprecation decision (SM2-R8), optional options-flow axis on the dossier.
