# CELH Cycle Autopsy 2018–2026
## IMCE wave A1 (IMCE-CELH-1) — records-only source chronology, three-clock timeline, mechanism epochs, and fixed recognition telemetry

**Wave:** A1, authorized by `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §13.
**Parent freeze:** merged as `ec44ae7d1659` (PR #6127, merged 2026-08-21T03:55:28Z) and confirmed as the tip of `origin/main` before this wave began.
**Date:** 2026-08-21. **Evidence cutoff:** filings through 2026-08-06; canonical price plane through 2026-08-12.
**Status:** **RECORDS ONLY.** No model, no score, no probability, no forward return, no Radar/Prophet path, no runtime, no `data/` write, no new canonical owner/store/ID, no trial family registration.
**Authority:** rank / gate / size / escalate / trade / originate / display — **all FALSE**. CELH is `DESCRIPTIVE` forever and may never be cited as evidence of issuer-specific forecast skill (freeze D9).

**Zero outcome computation.** This packet contains no forward return, no +21d/+63d/+126d field, no win rate, hit rate, p-value, success rate, or forecast-accuracy measure. The reproduction script asserts the absence programmatically. Outcome fields may attach to the recognition events only after the A4 criteria commit (two-commit discipline, G8-B1). The G2 census tape — which *did* carry path fields — is quarantined design-context evidence and is cited nowhere in this packet.

### Artifacts in this wave

| # | Artifact | Path |
|---|---|---|
| 1 | This autopsy | `research/imce/CELH_CYCLE_AUTOPSY_2018_2026.md` |
| 2 | Chronological evidence table (52 rows, full provenance) | `research/imce/celh/celh_evidence_chronology.csv` |
| 3 | Mechanism-epoch table | `research/imce/celh/celh_mechanism_epochs.csv` |
| 4 | Three-clock state table (18 quarters) | `research/imce/celh/celh_three_clock_state.csv` |
| 5 | Fixed recognition-event table — **no outcome columns** | `research/imce/celh/celh_recognition_events.csv` (+ full state `celh_2w_state_full.csv`) |
| 6 | Source / rights / missingness ledger (20 rows) | `research/imce/celh/celh_source_rights_missingness.csv` |
| 7 | Falsifier and unresolved-question list | `research/imce/celh/celh_falsifiers_open_questions.md` |
| 8 | Proposed prospective observation registration (**not activated**) | `research/imce/celh/celh_prospective_observation_registration.yaml` |
| — | Reproduction receipt for artifact 5 (not runtime; nothing imports it) | `research/imce/celh/celh_recognition_tape_2w.py` |

---

# 0. The autopsy in one paragraph

Between 2018 and 2026 Celsius Holdings ran one genuine demand S-curve and at least three *translation* cycles laid on top of it. The demand curve is visible on the operating clock: a small brand acquiring distribution points one region at a time, then a national inflection, then saturation at 98.5% ACV, then share loss. The translation cycles are visible only on the accounting clock, and they are much larger in amplitude than the demand cycle: the 2022 replacement of ~300 independent distributors with a single dominant counterparty, the 2023 channel build that flattered reported growth, the 2024 destock that turned +7.1% end-demand growth into −30.9% reported revenue, the 2025 re-load onto an easy base, and the 2026 assortment-and-trade reset. **The reported revenue line is not a demand series.** Its largest swings are produced by the gap between what CELH shipped and what consumers bought — a gap opened and closed by one customer's working-capital policy and by CELH's own trade investment. The single most important epistemic fact in the whole window is that the market could not see this at decision time: the pipeline fill that flattered Q1 2023 was disclosed **364 days after** the quarter was originally reported.

---

# 1. Evidence discipline

## 1.1 The three clocks, never collapsed

| Clock | What it measures | Primary sources in this packet |
|---|---|---|
| **Operating** | retail sell-through, distribution points, ACV, productivity per point, channel inventory, product mix, per-brand share | issuer-cited Circana aggregates in 8-K EX-99.1 releases; 10-K/10-Q narrative |
| **Accounting-translation** | revenue, sell-in vs sell-through, gross margin, inventory, receivables, accrued promotional allowance, acquisition effects | SEC XBRL `companyfacts`; filed statements |
| **Market-recognition** | completed-bar 2W state, cross events, histogram sign and first difference | canonical price plane `data/yahoo/CELH.parquet` |

No field in this packet mixes clocks, and **no cycle score exists**. `celh_three_clock_state.csv` keeps the three as separate column families for all 18 quarters.

## 1.2 Temporal law

Every row carries `event_time` / `measurement_start` / `measurement_end` / `available_at`, and where a fact was disclosed late, `retro_disclosure_lag_days`. The `available_at` backbone is exact: 41 periodic filings (10-K/10-Q) and 22 Item-2.02 earnings 8-Ks since 2018, each with its accession number and filing date, read from `https://data.sec.gov/submissions/CIK0001341766.json`.

**Original disclosure vs restatement is resolved mechanically.** For every XBRL concept/period, the packet keeps the *earliest filed* value and flags any later filing whose value differs. That is what makes `available_at` a real decision-time stamp rather than a label.

**An issuer statement that later explains an earlier period is never projected backward.** Such rows are typed `reconstructed_not_operational_pit` and carry the lag.

## 1.3 Evidence classes

`deterministic_fact` · `observed_numeric` · `issuer_claim_numeric` · `issuer_claim_directional` · `accounting_identity` · `derived_deterministic` · `mechanism_hypothesis` · `missing` · `not_reconstructable` · `not_applicable`.

Every causal attribution in this packet is `mechanism_hypothesis` class with a **mandatory named falsifier and a competing explanation** (freeze G8-M8) — see artifact 7. The issuer's own causal narratives stay `issuer_claim_directional` and are never silently upgraded.

## 1.4 Missingness

`present` · `not_available_for_date` · `rights_blocked` · `not_yet_built` · `not_applicable` · `unresolved_identity` · `reconstructed_not_operational_pit` · `superseded_by_recompute`.

**No missing observation is replaced with zero or "no change" anywhere in this packet.**

---

# 2. Mechanism epochs

Epoch names are **research labels only**. No Stock Identity behavioral epoch is claimed; `identity_epoch` is typed `not_yet_built` (Stock Identity W4 is `todo`). Mechanism epochs are a distinct record class from identity epochs and are never substituted for them (freeze D2 / G8-M5).

Boundaries are **clock-stamped**. A boundary drawn on the operating clock is valid for describing the business; it is *look-ahead* if used to partition a recognition statistic, because the market could not know it on that date. Both dates are carried.

| Epoch | Label | Boundary class | Operating-clock start | Recognition-clock (`available_at`) | Lag | Anchor receipt |
|---|---|---|---|---|---|---|
| **M0** | Fragmented DSD + direct, pre-Pepsi | corporate_state | 2018-01-01 (window start, not an event) | 2018-03-08 | n/a | FY2017/FY2020 10-K; Pepsi deck "300+ unique distribution partners" |
| **M0a** | Func Food international arm | corporate_event | 2019-10-25 | 2019-10-29 | 4d | 8-K 2.01 `0001213900-19-021402` |
| **M1** | PepsiCo distribution transition | corporate_event | 2022-08-01 | 2022-08-01 | 0d | 8-K `0001829126-22-014925`; agreements 8-K `0001829126-22-015110` |
| **M2** | Distributor inventory optimization / destock | operating_action | 2024-01-01 | **2024-05-07** | **127d** | 10-Q `0001341766-24-000029`; release `0001341766-24-000031` |
| **M3** | Demand normalization + portfolio pivot | operating_action | 2025-01-01 | 2025-05-06 | 125d | release `0001341766-25-000081` |
| **M4** | Alani Nu portfolio expansion | corporate_event | 2025-04-01 | 2025-04-01 | 0d | 8-K 2.01 `0001341766-25-000069` |
| **M5** | Rockstar + amended-and-restated PepsiCo relationship | corporate_event | 2025-08-28 | 2025-08-29 | 1d | 8-K `0001193125-25-192888` |
| **M6** | Assortment / promotional / inventory reset | operating_action | 2026-04-01 | 2026-08-06 | 127d | release `0001341766-26-000047` |

M1's end is dated 2023-12-31 and M2's start 2024-01-01 on the operating clock, per the freeze's §7.1 boundary amendments. **M6 overlaps M5** — it is an operating-action phase inside a corporate-structure epoch. They sit on different axes and must not be read as sequential; that ambiguity is carried openly as open question U7 rather than resolved by fiat.

**Corporate-event boundaries have ~0-day recognition lag; operating-action boundaries have ~127 days.** That asymmetry is itself a finding: structural changes are announced, behavioural changes are discovered a quarter later.

---

# 3. The operating clock — what the business actually did

## 3.1 M0 (2018 – mid-2022): distribution-point acquisition

CELH distributed "through a hybrid of direct-store delivery (DSD) distributors and as well as sales direct" (FY2020 10-K). At the moment of the Pepsi deal the issuer described its own network as **"Fragmented distribution network across regions"** with **"300+ unique distribution partners and points of contact"** (investor deck, 2022-08-01). Revenue compounded $52.6M (FY2018) → $75.1M (FY2019) → $130.7M (FY2020) → $314.3M (FY2021).

There is **no sell-through leg in this era**. The issuer cited no retail-scan figure the packet could recover, so the sell-in/sell-through wedge is `not_reconstructable` for M0 and M1 — typed absence, not zero (S011). This confirms the freeze's finding that wedge legs exist only from E2 onward.

One unexplained operating fact sits at the end of M0: **inventory reached $191.2M at FY2021 close — 10.4× the FY2019 level on 4.2× the revenue.** No mechanism for that build is disclosed. It is recorded as an observation without an attribution.

## 3.2 M1 (2022-08-01 – 2023-12-31): route-to-market replacement

Three hundred-plus independent relationships were replaced with one. The sell-in counterparty changed *identity*, not merely *size* — and by Q1 2024 that single customer was **62% of North American sales**.

## 3.3 M2–M3 (2024 – early 2025): demand decelerates while the channel drains

Issuer-cited CELSIUS retail sell-through, quarter by quarter: **+72.1% → +36.5% → +7.1% → +2.0% → −3.0%**. This is a clean, monotone demand deceleration ending in outright decline — and it is a *different* event from the destock happening simultaneously on the translation clock.

## 3.4 M4–M6 (2025 – 2026): portfolio substitution and the productivity turn

FY2025 distribution: portfolio points **+15%**; CELSIUS **+20% at 98.5% ACV**; Alani **+39% at 92.6% ACV**; Rockstar **−17% at 85.4% ACV**. CELSIUS at 98.5% ACV means distribution-point growth is **nearly exhausted as a demand lever for the core brand** — from here, growth must come from velocity, not availability.

In 2026Q2 the issuer accepted **fewer** points of distribution and reported **dollars per point of distribution +16% QoQ** — the first productivity-over-breadth trade in the window, and the first time the metric is quantified at all.

Meanwhile the core brand's share fell **year over year in every quarter for which the issuer disclosed a YoY comparison** — 2024Q4 −0.5pt, 2025Q1 −140bps, 2025Q2 −1.3pt, 2025Q3 −0.5pt. The *level* is not monotone (10.9% → 11.0% → 11.2% across 2025Q1–Q3) but ends far lower: **9.9% (2026Q1), 9.5% (2026Q2)**, while Alani rose to **8.7%** — within 0.8pt of CELSIUS.

---

# 4. The accounting-translation clock — how the business was reported

## 4.1 The transition cost sat below gross profit

In **Q3 2022**, selling and marketing expense was **$198.8M — 105.6% of that quarter's revenue** (legacy distributor termination charges). Gross margin that quarter was **41.8%**, materially unchanged from its neighbours. A gross-margin-only read of the largest structural change in the company's history sees **nothing**.

The terminations were financed by the incoming distributor: Pepsi upfront payments were held as **restricted cash**, usable only for termination payments to former distributors or repayable to Pepsi (Q1 2023 10-Q).

**Concept-continuity break:** `us-gaap:SellingAndMarketingExpense` is tagged for exactly three quarters (2022 Q1–Q3) and never again — later trade spend sits inside SG&A. A same-name time series across that boundary would be a fabrication (S006).

## 4.2 The wedge — where sell-in and sell-through diverge

The core measurement of the autopsy. Reported revenue growth minus issuer-cited retail sell-through growth, in percentage points, **only where both legs exist on a comparable denominator**:

| Quarter | Scope | Sell-in (revenue YoY) | Sell-through (Circana YoY) | Wedge | Reading |
|---|---|---|---|---|---|
| 2024-03-31 | consolidated vs CELSIUS | +36.9% | +72.1% | **−35.2pp** | destock opens |
| 2024-06-30 | consolidated vs CELSIUS | +23.4% | +36.5% | **−13.1pp** | destock continues |
| 2024-09-30 | consolidated vs CELSIUS | −30.9% | +7.1% | **−38.0pp** | **sign flip** |
| 2024-12-31 | consolidated vs CELSIUS | −4.4% | +2.0% | **−6.4pp** | closing |
| 2025-03-31 | consolidated vs CELSIUS | −7.4% | −3.0% | **−4.4pp** | wedge closed; both legs negative |
| 2025-09-30 | CELSIUS brand | +44% | +13% | **+31.0pp** | **inverse — re-load** |
| 2026-03-31 | CELSIUS brand | +6% | +6% | **0.0pp** | converged |
| 2026-06-30 | CELSIUS brand | −11.7% | −2% | **−9.7pp** | reset reopens the wedge |

**Comparability warnings that bind this table:**
- 2024Q1/Q2 use `MULOC`; 2024Q3 onward use `MULO+ w/C`. The denominator changed *inside* the destock episode.
- 2025Q2 and 2025Q4 are **absent by design**: consolidated revenue became a multi-brand aggregate on 2025-04-01, and per-brand revenue was not disclosed for those quarters. The wedge there is `not_applicable`, not zero.
- 2023 and earlier have no comparable sell-through leg at all (§3.1).

Read as a sequence, the wedge tells the whole mechanism story: **drain (2024) → close (early 2025) → re-load onto an easy base (2025Q3) → converge (2026Q1) → drain again (2026Q2).**

## 4.3 Trade investment is building on the balance sheet

Accrued promotional allowance, from filed balance sheets:

| Date | $M | % of that quarter's revenue |
|---|---|---|
| 2023-12-31 | 99.8 | 28.7% |
| 2024-09-30 | 158.8 | 59.8% |
| 2024-12-31 | 135.9 | 40.9% |
| 2025-06-30 | 200.2 | 27.1% |
| 2025-12-31 | 307.9 | 42.7% |
| 2026-03-31 | 401.1 | 51.2% |
| 2026-06-30 | **453.0** | **55.4%** |

**4.5× over the span while quarterly revenue rose 2.35×.** Gross margin fell from 52.0% (2024Q2) to 48.1% (2026Q2), attributed by the issuer to "higher promotional and incentive activity".

**This field is not in the SEC XBRL `companyfacts` API** — CELH publishes no custom namespace (observed: `dei`, `us-gaap`, `srt`, `ecd`). It is visible only by parsing the filed statements. It is the most under-instrumented translation field found in the window (S005).

## 4.4 Where accounting made the business look different from end demand

| Period | Direction | Mechanism |
|---|---|---|
| Q1 2023 | **stronger** | ~$25M channel build recognized as revenue — disclosed 364 days later |
| Q1–Q2 2024 | **weaker** | distributor days-on-hand reduction; ~−$20M in Q1 alone |
| Q3 2024 | **much weaker** | −$123.9M distributor revenue + retailer promotional allowances that "would have otherwise been offset by proportional distributor sell-in" |
| Q4 2024 | **weaker** | "higher domestic allowances… including our distributor incentive program" |
| Q2 2025 – Q1 2026 | **stronger** | acquisition arithmetic: consolidated growth of +84% to +173% while the core brand lost share year over year in every quarter with a disclosed YoY comparison |
| Q3 2025 | **stronger** | +44% brand revenue against a base quarter the destock had cut 31% |
| Q2 2026 | **weaker** | trade investment, shipment timing on inventory rebalancing, club-channel softness |

---

# 5. The market-recognition clock — fixed telemetry, dates and states only

## 5.1 The named construction

Exactly one construction is used, composed from two **existing** house functions — no third MACD is minted, per the construction-naming law (freeze D3.1):

```
bars   = engine.canon._resample_weekly(daily_close, "2W-FRI")     # engine/canon.py:505, as called at :492
macd   = engine.technicals.macd_hist semantics — classic 12-26-9  # engine/technicals.py:34-38
         ema12 = close.ewm(span=12, min_periods=12).mean()
         ema26 = close.ewm(span=26, min_periods=26).mean()
         macd  = ema12 - ema26 ; signal = macd.ewm(span=9, min_periods=9).mean()
         hist  = macd - signal        (asserted equal to macd_hist(w2) at runtime)
completed-bar semantics = canon's .shift(1) idiom
```

**Construction name carried on every telemetry record:** `canon._resample_weekly(2W-FRI) + technicals.macd_hist(12-26-9), completed-bar shift(1)`.

**Input plane is load-bearing:** the full `data/yahoo/CELH.parquet` `close` series, 4,921 daily bars 2007-01-22 → 2026-08-12. `resample("2W-FRI")` bin edges depend on the series start, so **truncating the input changes every bar**. The first defined histogram bar is 2008-05-02 — that is the 26+9-bar warm-up, not a data gap. One price plane, no splice.

## 5.2 Recognition events in the autopsy window

16 completed-bar 2W cross events, 2018-01-01 onward (33 across full history: 16 bullish, 17 bearish). Three crosses are reversed on the very next completed bar — 2013-02-01 and 2013-02-15 (outside the window) and **2021-08-20 (inside the window)**, whose bearish cross is undone by the 2021-09-03 bullish cross 14 days later.

| Bar close (state measured) | Actionable from | Event | Histogram | Sign / first difference |
|---|---|---|---|---|
| 2019-03-22 | 2019-04-05 | bullish_cross | +0.0115 | positive / expanding |
| 2019-09-20 | 2019-10-04 | bearish_cross | −0.0110 | negative / contracting |
| 2019-11-29 | 2019-12-13 | bullish_cross | +0.0130 | positive / expanding |
| 2020-04-03 | 2020-04-17 | bearish_cross | −0.0024 | negative / contracting |
| 2020-05-15 | 2020-05-29 | bullish_cross | +0.0250 | positive / expanding |
| 2021-08-20 | 2021-09-03 | bearish_cross | −0.0552 | negative / contracting |
| 2021-09-03 | 2021-09-17 | bullish_cross | +0.2397 | positive / expanding |
| 2021-11-26 | 2021-12-10 | bearish_cross | −0.3152 | negative / contracting |
| 2022-07-08 | 2022-07-22 | bullish_cross | +0.2591 | positive / expanding |
| 2023-02-03 | 2023-02-17 | bearish_cross | −0.1037 | negative / contracting |
| 2023-05-12 | 2023-05-26 | bullish_cross | +0.1473 | positive / expanding |
| 2023-11-24 | 2023-12-08 | bearish_cross | −0.0580 | negative / contracting |
| 2024-03-01 | 2024-03-15 | bullish_cross | +0.9206 | positive / expanding |
| 2024-06-21 | 2024-07-05 | bearish_cross | −0.6421 | negative / contracting |
| 2025-03-28 | 2025-04-11 | bullish_cross | +0.3074 | positive / expanding |
| 2025-12-05 | 2025-12-19 | bearish_cross | −0.4860 | negative / contracting |

**No outcome column exists in this table or its CSV.** The reproduction script asserts that no column name contains a forward/return/win/hit/skill token, and fails loudly if one appears.

## 5.3 Current state at the evidence cutoff

The 2W state has been **`bear` continuously since the 2025-12-05 bearish cross**, through the last completed bar (2026-08-14, built from data through 2026-08-12) — 252 days and still open. For scale, the window's longest *closed* bear stretch was 2024-06-21 → 2025-03-28 (280 days); this one is the second-longest so far and is not yet resolved.

The histogram is negative throughout, reached its most negative value of **−2.45 at the 2026-06-05 bar**, and has risen toward zero on every completed bar since 2026-06-19 (`hist_d1` positive; state label `expanding`, meaning the first difference is positive and the magnitude is shrinking). **No statement is made here about what that implies** — that is an outcome question (U1).

**Telemetry for 2026-08-13 → 2026-08-21 is `not_available_for_date`:** the committed canonical store's last CELH write was 2026-08-12. Nine calendar days at the right edge are absent — not carried forward, not filled with "no change" (S020).

---

# 6. The three clocks at each phase transition

Each row states what an observer standing at that quarter's `available_at` could see on each clock. The recognition state is the last **completed** 2W bar on or before that date.

| Quarter | Operating clock | Translation clock | Recognition clock at `available_at` |
|---|---|---|---|
| **2022-09-30** (av. 2022-11-09) | no sell-through leg | S&M 105.6% of revenue; GM 41.8% unaffected | **bull**, positive/contracting (bullish cross 2022-07-08) |
| **2023-03-31** (av. 2023-05-09) | no sell-through leg | revenue +94.8%; **no pipeline disclosure exists** | **bear**, negative/expanding (bearish cross 2023-02-03) |
| **2023-12-31** (av. 2024-02-29) | +126.6% on a custom segment | revenue +95.2%; inventory peaks $229.3M | **bear**, negative/expanding (bearish cross 2023-11-24) |
| **2024-03-31** (av. 2024-05-07) | **+72.1%** | **+36.9% — first destock disclosure; Q1-2023 retro-disclosed** | **bull**, positive/contracting (bullish cross 2024-03-01) |
| **2024-06-30** (av. 2024-08-06) | +36.5% | +23.4%; second destock quarter | **bear** — crossed 2024-06-21, *between* the two disclosures |
| **2024-09-30** (av. 2024-11-06) | **+7.1%** | **−30.9%**; −$123.9M distributor; GM −440bps | **bear**, negative/expanding |
| **2024-12-31** (av. 2025-02-20) | +2.0% | −4.4%; inventory drawn to $131.2M | **bear**, negative/expanding |
| **2025-03-31** (av. 2025-05-06) | **−3.0% — demand event** | −7.4%; wedge closed | **bull** — crossed 2025-03-28 |
| **2025-09-30** (av. 2025-11-06) | +13% brand | **+44% brand — inverse wedge** | **bull**, positive/contracting |
| **2025-12-31** (av. 2026-02-26) | portfolio +24.4% | consolidated +117%; promo accrual $307.9M | **bear** — crossed 2025-12-05 |
| **2026-06-30** (av. 2026-08-06) | **−2% brand**; points cut, $/point +16% | **−11.7% brand**; GM 48.1%; accrual $453.0M | **bear**, negative/expanding |

**The load-bearing row is 2024-06-30.** The recognition clock crossed bearish on 2024-06-21 — *after* the first destock disclosure (2024-05-07) and *before* its confirmation (2024-08-06). That is a description of sequence, not a claim about lead or lag: **U1 — whether recognition leads, lags, or tracks the mechanism at CELH — is an outcome question and is forbidden in A1.**

---

# 7. The ten questions, answered descriptively

**1. What mechanisms generated the large CELH waves?**
Distribution-point acquisition (M0, genuine demand), then route-to-market replacement (M1), then three successive *translation* mechanisms — channel build (2023), channel drain plus trade allowances (2024), acquisition arithmetic (2025) — and a deliberate assortment/trade reset (2026). The waves in *reported revenue* are dominated by the translation mechanisms; the waves in *end demand* are much smaller.

**2. What changed first before major accelerations and slowdowns?**
Before the 2024 slowdown, in order: (i) **2024-03-23** — Distribution Agreement Amendment No. 1 creating an incentive program to compensate Pepsi (available 2024-03-26); (ii) **2024-05-07** — first quantified destock disclosure and the retro-disclosure of the 2023 build; (iii) **2024-08-06** — confirmation; (iv) **2024-11-06** — the sign flip. The *contract change* preceded the first destock disclosure by **42 days measured recognition-clock to recognition-clock** (available 2024-03-26 → available 2024-05-07; 45 days from the 2024-03-23 execution date). Before the 2026 reset, the earliest visible change is the accrued-promotional-allowance step-up through 2025 (§4.3), which precedes the reported brand decline by several quarters. Before the 2025 "recovery", the earliest change was an acquisition close, not a demand inflection.

**3. Where did sell-through and sell-in materially diverge?**
2024Q1 (−35.2pp), 2024Q2 (−13.1pp), 2024Q3 (−38.0pp), 2024Q4 (−6.4pp), 2025Q3 (**+31.0pp, inverse**), 2026Q2 (−9.7pp). Full table with comparability warnings in §4.2.

**4. Where did accounting translation make the business look stronger or weaker than end demand?**
§4.4. Stronger: Q1 2023, Q2 2025–Q1 2026, Q3 2025. Weaker: Q1–Q4 2024, Q2 2026.

**5. Which disclosures were only knowable retrospectively?**
The ~$25M Q1-2023 pipeline fill — **364 days** after the original filing, and ~13.2 months after measurement end. The Q1-2023 10-Q contains **zero** occurrences of "pipeline", "days on hand" or "inventory buildup"; that null is reproducible by full-text scan. Also retrospective, in the weaker sense of operating-action epochs: M2, M3 and M6 each became visible ~125–127 days after their operating-clock start.

**6. Which structural changes make old CELH episodes non-comparable to newer ones?**
Six hard breaks: (a) 2019-10-25 Func Food adds a non-US geography; (b) 2022-08-01 one counterparty replaces 300+; (c) 2025-04-01 Alani makes consolidated revenue multi-brand; (d) 2025-08-28 the 2022 agreement is *terminated* and replaced, and the counterparty becomes supplier + brand-seller + preferred holder + board-represented; (e) the Circana denominator changes **three times** (custom segment → MULOC → MULO+ w/C), once *inside* the destock episode; (f) `SellingAndMarketingExpense` is tagged for three quarters only.

**7. At each major phase transition, what did the three clocks each say?**
§6.

**8. What evidence would falsify the current mechanism interpretation?**
Artifact 7, §2. The decisive falsifier — actual channel-inventory levels showing the swings were too small to produce the observed revenue amplitude — is **`not_reconstructable` from public sources**. The core mechanism is therefore *consistent with* the evidence but **not identified by it**, and this packet says so rather than overclaiming.

**9. Which fields are reliably observable prospectively going forward?**
Tier 1 of artifact 8: accrued promotional allowance (with statement-level parsing), issuer-cited retail sell-through **with its verbatim denominator string**, per-brand revenue, distribution points and ACV, dollars per point of distribution, channel-inventory narrative and any quantification, distribution-agreement events (with `event_time` *and* filing date), and retro-disclosure events as first-class observations carrying their lag.

**10. Which apparently desirable fields are actually unavailable, rights-blocked or hindsight-only?**
Distributor channel inventory in units or weeks — **never disclosed, `not_reconstructable`**. Circana direct — `rights_blocked` (HOLD). Earnings-call transcripts — `rights_blocked` for this wave; no transcript is quoted anywhere in this packet. Household/buyer-panel data — `rights_blocked`; its absence leaves half of falsifier H6 open. Estimate revisions and borrow — `not_reconstructable` historically, prospective-from-capture only; a current-vintage history would be a forbidden backfill. Pre-2024Q1 wedge — `not_reconstructable`. Distribution points/ACV before FY2025 — `not_available_for_date`.

---

# 8. Executive note to Fable

## 8.1 Strongest mechanism discoveries

1. **The wedge is a readable, signed, repeating sequence** — drain → close → inverse re-load → converge → drain — and each leg has an independent operating-clock and translation-clock receipt. This is the mechanism grammar the program was looking for, expressed in two observable legs rather than one composite.
2. **Corporate-event boundaries carry ~0-day recognition lag; operating-action boundaries carry ~127 days.** Structural changes are announced; behavioural changes are discovered a quarter later. This is a general property of issuer-mechanism epochs, not a CELH quirk, and it is directly actionable for how future epochs are stamped.
3. **Accrued promotional allowance is the best-performing under-instrumented sensor found.** It rose 4.5× against 2.35× revenue and stepped up *before* the reported brand decline — and it is invisible to the XBRL `companyfacts` API that most automated pipelines would use.
4. **The contract amendment led the disclosure by 42 days** (available_at to available_at). 8-K Item 1.01 events on a distribution agreement are a cheap, dated, machine-readable early sensor for the mechanism class.
5. **ACV saturation is a hard ceiling that is visible before it binds** — CELSIUS at 98.5% ACV in FY2025 meant distribution-point growth was spent, one to two quarters before the productivity trade appeared.

## 8.2 Evidence that changed the original CELH thesis

- **The 2024 destock was not the start of the story — it was the *reversal* of a 2023 build that nobody could see.** The two are one mechanism observed twice, and the second half was only interpretable after 2024-05-07.
- **The 2025 "recovery" does not survive contact with the sell-through leg.** +44% brand revenue against +13% brand sell-through, on a base quarter the destock had cut 31%, with share still falling. The freeze recorded this as a "failed bounce"; the wedge sign makes the mechanism explicit — it was a re-load, and Q2 2026 unwound it.
- **A demand event and a channel event were running simultaneously through 2024 and are separable.** Sell-through decelerated monotonically (+72.1% → −3.0%) *while* the channel drained. Reading 2024 as purely a destock is wrong; so is reading it as purely a demand break.
- **The 2022 transition cost is invisible in gross margin.** Anything that screens issuer transitions on margin would have missed the largest structural change in the company's history.
- **CELH's own causal narrative moved from "consumer demand growth" (Q1 2024, alongside a −$20M destock note) to explicit channel language only once the sign flipped.** Issuer attribution timing is itself an observable.

## 8.3 Major missing / rights-blocked fields

`not_reconstructable`: distributor channel inventory levels (the decisive one), the pre-2024Q1 wedge, historical estimate revisions, historical borrow.
`rights_blocked`: Circana direct, earnings-call transcripts, household/buyer-panel data.
`not_available_for_date`: distribution points and ACV before FY2025, per-brand revenue before 2025Q2, accrued promotional allowance before 2023-12-31, recognition telemetry after 2026-08-12.
`not_yet_built` / `unresolved_identity`: Stock Identity `identity_epoch`, Data OS `security_id`.

## 8.4 Structural breaks that invalidate naive comparison

The six in §7 Q6. The two most likely to bite an automated successor: **the three-denominator Circana splice** (a wedge computed across it is not a measurement) and the **consolidated-vs-brand mismatch from 2025-04-01** (which silently converts a brand comparison into an acquisition comparison).

## 8.5 Exact next questions requiring A4 or later authority

| Q | Requires |
|---|---|
| Does recognition lead/lag/track the mechanism at CELH? | **A4 criteria commit.** Any answer is an outcome computation, forbidden in A1. |
| Is the wedge a generalizable sensor or a CELH artifact? | A second and third family (A3 homebuilder census onward). CELH can never supply the answer — `DESCRIPTIVE` by rule. |
| Can accrued promotional allowance be captured across a peer cohort? | A census wave; XBRL exposure is issuer-by-issuer and cannot be assumed. |
| May any of this reach the CPI truth registry? | **A2 vocabulary audit first** — no issuer truth before it lands. |
| Resolve `security_id` + `catalog_as_of` for CELH | Required before any Stock Identity Episode citation (freeze D2 / G8-M4). |
| M6: distinct epoch or phase inside M5? | Fable adjudication (U7). Recorded both ways rather than decided unilaterally. |

## 8.6 Honest posture

This packet describes a mechanism; it does not identify one. The decisive falsifier is unobtainable from public sources, the sell-through leg is issuer-curated and thrice-redefined, and every causal statement here is `mechanism_hypothesis` class with its competing explanation written down next to it. **CELH remains descriptive forever, 0 historical cells, barred by rule and not by count.** The value of this wave is the instrumentation design in artifact 8 and the epoch-stamping law in §2 — both of which transfer to families that *can* be measured.

---

# 9. Reproduction

```bash
# available_at backbone (SEC_EDGAR = GO; declared UA, <=10 req/s)
curl -H "User-Agent: <org> <contact>" https://data.sec.gov/submissions/CIK0001341766.json
curl -H "User-Agent: <org> <contact>" https://data.sec.gov/api/xbrl/companyfacts/CIK0001341766.json

# fixed recognition telemetry (regenerates artifact 5 byte-for-byte)
python3 research/imce/celh/celh_recognition_tape_2w.py
```

Every numeric claim in this packet resolves to one of: an accession number in `celh_evidence_chronology.csv`, a first-disclosure XBRL fact, or the named 2W construction over the canonical price plane. Every filing cited is public first-party (SEC EDGAR / CELH investor release). No paid source was purchased, no rights-blocked source was used, and no transcript text is reproduced.

**Stop.** This wave ends at the research packet. No implementation, ingestion, model fitting, trial registration, CPI truth append, or successor wave has started.
