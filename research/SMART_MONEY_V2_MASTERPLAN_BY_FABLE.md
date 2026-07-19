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

---

## 9. SM3 Amendment — operator-ordered ranked Follow Desk (2026-07-18, appended by Fable)

**Trigger.** Operator order 2026-07-18 ("identify the best funds to follow… pinpoint the best
possible stocks to buy… ranked, concrete, actionable boards; surface asymmetric small/mid-cap
high-conviction buys by proven managers; sector rotation by proven rotators; ignore consistent
losers") + NEW evidence: the Grade-A Q1-2026 60D assessment
(`SMART_MONEY_GRADE_A_MANAGERS_2026Q1_60D_ASSESSMENT.md`, artifacts under
`research/artifacts/SMART_MONEY_GRADE_A_2026Q1/`) — position-level demonstration that
within-cohort outcomes diverge massively by manager (Casdin +41.7pp vs Corvex −10.5pp at 60D)
and by sleeve (New vs Add: Altimeter +35.5% / −8.0%). This is exactly the "NEW evidence + explicit
operator ruling" the DO_NOT_REBUILD preamble requires to touch a settled boundary.

**SM3-R1 (scope of supersession).** SM2-R2's *display boundary* (no ranked-conviction default, no
consensus best-ideas view) is SUPERSEDED for the new Follow Desk boards (Best Buys, Small/Mid
Asymmetric, Sector Rotation Consensus) and the Follow Score leaderboard. The *authority-tier* law
is NOT touched: WA-R2 / NEXTL-U13 stand — 13F remains struck as a positive signal for any
detector, fingerprint, NW organ, calibrated key, allocation, gate, or escalation. The Follow Desk
is a display-tier research surface: ranked ordering is an attention allocator with printed
receipts, never a promoted signal. Nothing here may ever be cited as gauntlet evidence.

**SM3-R2 (axis purity retained).** SM2-R3 stands in full. Follow Score, Rotation IQ, Front-Run
rate and every board rank derive from the 13F axis alone. Insider / 13D-G / short data appear only
as separate context columns, never inside a score.

**SM3-R3 (fade tier).** Funds with ≥3 consecutive negative quarters (or follow_score < 35) are
tiered `fade` and EXCLUDED from consensus/best-buys math (excluded counts printed). This is the
operator's "ignore consistent losers" — a descriptive screen on a display surface, n's printed,
survivor-cohort caveat retained from SM2-R6.

**SM3-R4 (honesty form).** Every board carries: filing-lag stamp (~45d), per-score n, the
plain-word null ("13F crowding historically warns more than it confirms; ranked order is where to
research first, not a buy list"), and the frozen-study framing on the Grade-A report card (one
quarter, one cohort — an anecdote with receipts, not a base rate).

**SM3-R5 (classification).** `Unclassified` sector fallthrough (18.4% of book value at ruling
time) is fixed via two appended fallback sources (curated override map + theme→sector inference,
inference-flagged). Display-tier metadata; no epistemic weight.

---

## 10. SM4 Amendment — UX consolidation + 4-quarter fund memory (2026-07-19, appended by Fable)

**Trigger.** Operator order 2026-07-19: "you legit made 11 different sections in this page and I
don't know which one is actually useful… be brutal and trim down the excess"; normalize fonts off
the terminal look; cap long lists at ~20 rows with See more; make Grade-A fund names clickable;
give the lobe "total memory over funds' performances" — full reads of the last 4 quarters of 13F
filings consolidated into a strongest-institutions view that recommends which managers are most
worth following.

**Evidence base (2026-07-19 census).** The baked page is 24,791px (~30 screens), 15 h2 sections.
Fault line: only 3 lenses are fresh (Wire / Insider / Activists, 07-17); EIGHT sections re-sort
the same 2026-03-31 Q1 13F snapshot (Manager Desk, Per-fund Rotation, Follow Desk, Best Buys,
Consensus Flow, Models, Grand Portfolio, Crowding, Initiations — different grains of one dataset).
Models panels expose raw slugs (`n_funds/gw_breadth/d_funds_qoq`) + the composite formula at rest
(Doctrine Law 2/3 violations) and are stamped off-clock. Activists = 357 rows, 355 undifferentiated
microcap dashes. Follow Desk = 117 rows of which the LOW-DATA tail is all-dash filler. Forward
ledger = zero rows until 2026-10-15. Best & Worst Buys is a fourth duplicate of the buy ranking.

### SM4-R1 — Information architecture (kill/merge/demote map; display-only, no engine deletion)

Engines and JSON artifacts are UNTOUCHED — display-tier accrual continues for every computed
lane (a cut section is a display cut, never an accrual cut). New page order:

| # | Section (id) | Verdict / content |
|---|---|---|
| 0 | `#sec-hero` compressed command deck | KEEP, compress ~520→~300px: h1 + plain thesis line + filing clock + filed/pending dot grid (signature) + ONE compact freshness chip row |
| 1 | `#sec-follow` **HERO: Managers worth following** | Follow Desk + NEW 4Q-memory hero cards (top 5, clickable) + NEW "Quarterly report card" table (live, all funds, cap 20 + fold) + trimmed follow table (cap 20 + fold, LOW-DATA all-dash tail CUT from display; count printed). Frozen Grade-A card DEMOTED to one receipt link line |
| 2 | `#sec-wire` What just moved | KEEP, existing 20-fold; ADD "followed fund" chip on rows whose slug is follow/watch tier (template-side join) |
| 3 | `#sec-ideas` Best ideas board | Best Buys (cap 20 + fold) + Small/Mid asymmetric side card (6 rows) + "Biggest exits" sell-side table (cap 10, from flow) + Initiations DEMOTED to collapsed research-queue details (cap 20 + fold). Models panels CUT from display (conviction signal already inside Best Buys scoring); adds-side flow table CUT (dupe of Best Buys) |
| 4 | `#sec-herd` Where the herd stands | Sector Rotation Consensus bars (KEEP as-is, already Tier-1-shaped) + Crowding radar top 8 (fold) + Grand Portfolio collapsed details top 10 (fold) |
| 5 | `#sec-insider` Insider intelligence | KEEP 2×2 cards (already 8-capped) |
| 6 | `#sec-managers` Manager desk | DEMOTE to compact: duel card + leaderboard cap 10 (fold to 51) + per-fund rotation accordions capped to top 10 by follow score (fold) + "All fund dossiers →" link to fund_index.html |
| 7 | `#sec-activists` Activist monitor | FILTER to rows with tracked-holder overlap > 0 or roster hit, cap 20 + fold; honest count line ("Showing N of 357 — the rest are names our tracked funds don't own") with full feed behind the fold |
| 8 | `#sec-dossier` Ticker dossier | KEEP (starts-empty search tool; verify wiring in browser) |
| 9 | Footer strip | Forward ledger → ONE line ("Pre-registered track record starts accruing 2026-10-15") + receipt links (frozen Grade-A artifact, methodology) |
| — | Best & Worst Buys section | CUT (4th duplicate; per-fund receipts live in fund dossiers) |

Sticky rail chips: Follow · Wire · Ideas · Herd · Insider · Managers · Activists · Dossier.

### SM4-R2 — 4-quarter fund memory (engine; display-tier, SM3-R1/R4 form binds)

New `engine/fund_memory.py`: generalize the Grade-A methodology (decision-weighted 60-calendar-day
excess vs SPY, `incremental_book_pct` weights, New/Add split) across the last 4 completed quarters
× ALL tracked funds (not just grade-A), priced from the LOCAL close panel already used by
`fund_followability` (zero network on the render path). Anchor = each quarter's common 45-day
deadline cluster date (2025-08-14 / 2025-11-14 / 2026-02-13 / 2026-05-15 for the current window);
all four 60d windows have settled as of 2026-07-19. Per (fund, quarter): `n_priced`,
`dw_excess_60d`, `new_dw_excess_60d`, `add_dw_excess_60d`, `hit_60d`, cohort `rank`, `beat`
(dw_excess_60d > 0). Consolidated per fund: `quarters_beat / quarters_scored`,
`avg_dw_excess_60d`, `memory_rank` (order: quarters_beat desc, then avg_dw_excess_60d desc;
floor: quarters_scored ≥ 3 to hold a rank — below-floor funds listed unranked, "not enough
data yet" printed, never hidden). Output under `smartmoney_follow.json["memory"]` inside the
Phase-4.5 fingerprint cache (recompute only on new filing / FOLLOW_VERSION bump — render budget
respected). WA-R2/NEXTL-U13 untouched: descriptive attention allocator with receipts; never
gauntlet evidence, never a promoted signal; "validated" never appears.

### SM4-R3 — Typography normalization (the de-terminal ruling)

The local `--numf` ("SF Mono…monospace") stack and the 9–10px uppercase-tracked-mono label idiom
are retired from this page. Numbers: `font-family:inherit` (Inter) + `font-variant-numeric:
tabular-nums`. Labels/th/chips/eyebrows: Inter 500–600, sentence case, 11px floor,
letter-spacing ≤ .06em (uppercase survives ONLY on the deck eyebrow + section eyebrows).
`.spark` braille bars keep `var(--font-mono)` (glyph alignment). Palette/tokens stay in the
theme.css family. Signature motif: the 4-quarter record dots (● beat green / ● missed red /
◌ hollow pending) on hero cards, report card, and follow table — data-true illustration, plus the
kept filed/pending dot grid.

### SM4-R4 — Plain-word surface (Doctrine Law 2/3 ports)

Column renames (precise defs move to `?`/data-tip hovers): Rotation IQ → "Sector timing" /
板块择时; Front-run → hover-only; Streak → "Cold quarters" / 连续落后季数; Median excess →
"Typical edge vs market"; Sell skill → "Sell timing"; Decay 21-1260 → hover-only; Top-10 % →
"Concentration"; raw `mchip` keys (grade_w, gw_breadth…) removed from display. Every board keeps
the SM3-R4 honesty form (lag stamp, n, plain-word null). Fold idiom: shared `smFold` controller
(cap 20, step 40, See more / Show all / Show fewer, bilingual) replacing per-section bespoke JS.

### SM4-R5 — Clickable funds everywhere

Every fund name on the page links to its dossier `fund_<slug>.html` via the existing
`.fund-link` pattern. The Grade-A card omission (template `:1234`, plain text) is fixed;
`_ga_r['fund']` is already the slug — no normalization needed. New memory cards/report-card rows
link the same way.
