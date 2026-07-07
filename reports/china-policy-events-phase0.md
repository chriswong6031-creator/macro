# China Policy Events — Phase-0 Report

**Pre-registration:** `research/CHINA_POLICY_EVENTS_PREREG.md` (committed before any outcome computation — git timestamp is proof)
**Study date:** 2026-07-06
**Script:** `scripts/china_policy_events_phase0.py`
**Results JSON:** `data/experiments/china_policy_events_results.json`

---

## DATE SEMANTICS — Read This First

Before any outcome was computed, the REPORT_DATE column in `data/china_macro/rrr.parquet` was verified against known PBoC announcements.

**Finding: REPORT_DATE = ANNOUNCE DATE (not effective date).**

Evidence:
- 2008-10-08: PBoC announced; effective 2008-10-15. REPORT_DATE = announcement.
- 2020-01-01 (New Year holiday, non-trading day): REPORT_DATE matches the announcement.
- 2018-10-07 (Sunday, non-trading): REPORT_DATE is the weekend announcement day.
- 2012-02-18, 2015-04-19, 2018-06-24: all weekends, all announcement days.

Announcement precedes effective date by 1–10 business days. Measuring from the first close **after the announcement** captures the market's immediate reaction to the policy signal — the economically appropriate anchor. Effective-date entry would understate the announcement-day drift.

Verified and cached: `data/experiments/rrr_date_semantics_check.json`

> **In plain English:** PBoC typically says "we're cutting the reserve ratio" on a Monday, and the cut takes effect the following weekend or week later. We use the announcement date because that's when the market hears the news. Using the effective date would be like measuring a stock's reaction to an earnings release starting a week after it came out.

---

## Events

| Family | Description | Episodes | Coverage |
|---|---|---|---|
| F-A RRR ease | rrr_change < 0 | **26** | 2008-10-08 → 2025-05-07 |
| F-B LPR cut | 1y or 5y diff < 0 | **15** | 2019-08-20 → 2025-05-20 |
| F-X RRR hike | rrr_change > 0 | 27 | 2006–2011 era (exploratory only) |
| F-C MPC communiques | communiques.parquet (68 docs, post-fix) | **39** | 2009 Q1 → 2026 Q1 |

Event counts match prereg (26/15). Same-date merge applied within each family.

F-C was BLOCKED-DATA when phase-0 first ran: `data/china_official/communiques.parquet` was absent. The W1.1 backfill collector (`scripts/backfill_china_communiques.py --family pboc_mpc`) was run on the manual Mac lane on 2026-07-06. Two collector bugs (null publish_date for 47/48 rows; missing 2011–2015 listing pages) were identified and fixed the same day; the re-collect yielded 68 docs with publish_date non-null for all 68. F-C was re-run the same day as a pre-registered exploratory leg under the existing budget headroom. The first (buggy) run produced n_usable=1; the post-fix run produced n_usable=39. Both are documented in the run_history field of the results JSON and in the "Run history / data honesty" paragraph of the F-C section below.

---

## Results

### Gated Trials — Verdict at H=20

Six pre-registered trials. BH-FDR applied across all six H=20 p-values.

| Trial | K usable | Mean CAR | HAC-t | BH-q | DSR | Split-half | **Verdict** |
|---|---|---|---|---|---|---|---|
| T1: F-A → SHCOMP abs | 26 | −0.12% | −0.089 | 0.78 | — | — | **NO-GO** |
| T2: F-A → banks rel | 20 | +0.39% | 0.554 | 0.78 | 0.11 | inconsistent | **ACCRUE** |
| T3: F-A → real estate rel | 26 | −1.21% | −1.441 | 0.93 | — | — | **NO-GO** |
| T4: F-B → SHCOMP abs | 15 | −0.25% | −0.392 | 0.78 | — | — | **NO-GO** |
| T5: F-B → banks rel | 15 | +0.53% | 1.007 | 0.78 | 0.12 | **consistent** | **ACCRUE** |
| T6: F-B → real estate rel | 15 | +0.08% | 0.145 | 0.78 | 0.06 | inconsistent | **ACCRUE** |

No trial clears the full gate cascade. No verdict of GO.

Note on T2 (K=20 vs 26 events): The Shenwan banks sector panel starts 2014-02-21. Six RRR eases before that date (2008, 2011, 2012) have no usable window. K=20 is the honest usable count.

> **In plain English:** We asked six questions: Do RRR cuts lift the market? Do they lift banks? Do they lift real estate? Same three questions for LPR cuts. None of the answers are strong enough to act on yet. Three families returned negative mean returns (wrong sign = NO-GO). Three returned positive mean returns but the signal is too weak to clear our statistical bars (ACCRUE = "promising but unproven — let more events accumulate").

### BH-FDR Summary

No trial has q ≤ 0.10. The smallest q is 0.78 (applied uniformly after BH monotone enforcement). The six H=20 p-values:

| Trial | one-sided p | BH-q | Reject? |
|---|---|---|---|
| T5 FB banks rel | 0.157 | 0.78 | No |
| T2 FA banks rel | 0.290 | 0.78 | No |
| T6 FB restate rel | 0.442 | 0.78 | No |
| T4 FB SHCOMP | 0.652 | 0.78 | No |
| T1 FA SHCOMP | 0.535 | 0.78 | No |
| T3 FA restate rel | 0.925 | 0.93 | No |

---

## Horizon Curves (Descriptive)

Verdict is AT H=20 only. The curves below are descriptive — not a menu for fishing.

### F-A RRR Ease → SHCOMP (absolute)

| H | K | Mean CAR | HAC-t |
|---|---|---|---|
| 5 | 26 | −0.20% | −0.258 |
| 10 | 26 | +0.33% | 0.364 |
| **20** | 26 | **−0.12%** | **−0.089** |
| 40 | 26 | +3.39% | 2.348 |
| 60 | 26 | +1.23% | 0.769 |

The H=40 result (t=2.35) is a descriptive observation only — it was not pre-registered and cannot be used as a verdict. It will be noted in the come-back review for potential pre-registration of an H=40 study.

### F-B LPR Cut → Banks rel (strongest accruing trial)

| H | K | Mean CAR | HAC-t |
|---|---|---|---|
| 5 | 15 | +0.14% | 0.393 |
| 10 | 15 | −0.18% | −0.251 |
| **20** | 15 | **+0.53%** | **1.007** |
| 40 | 15 | +0.48% | 0.707 |
| 60 | 15 | +0.09% | 0.130 |

---

## Exploratory Legs (NOT gated, NOT in FDR family)

### F-X RRR Hikes (exploratory, labeled)

K=27 | Mean CAR = −1.32% | HAC-t = not computed (exploratory)

Easing events (F-A) did not produce positive SHCOMP drift at H=20 (mean = −0.12%). Hiking events show −1.32%. The asymmetry is directionally consistent with the hypothesis (hikes drag, eases don't lift) but the null result for eases means the mechanism claim is not confirmed.

### 510300 ETF (descriptive repeat)

F-A: 12 events with ETF coverage (2012+), mean = not the verdict instrument.
F-B: all 15 events have ETF coverage. Qualitatively similar to SHCOMP results.

### F-C MPC Communiqués (exploratory / unsigned / descriptive)

**Script:** `scripts/china_policy_events_fc.py` | **Run date:** 2026-07-06 (post-fix re-run)

**Event definition:** Consecutive pboc_mpc communiqués (sorted by meeting_year, meeting_quarter) are diffed against the 46-formula phrase book (`data/china_official/phrase_book.yml`). An event fires when ≥1 formula appeared or dropped between a previous and current quarter's readout. The first document is baseline only (cold-start rule: cannot distinguish "appeared" from "always present"). Same-date episodes merge to one (union of changes).

**Anchor:** publish_date (prereg primary); fallback to meeting_date if publish_date is null; drop the pair if both are null (per prereg spec).

**Coverage:** 68 docs, 2009 Q1 → 2026 Q1. One article (`/3871092/index.html`) had an empty body and was legitimately skipped (empty body → no row emitted). All 68 collected rows have non-null publish_date from the PBoC listing-page CMS stamps.

**Document and pair counts:**

| Metric | Count |
|---|---|
| pboc_mpc docs (after dedup) | 68 |
| Explicit-gap rows dropped | 0 |
| Consecutive pairs diffed | 67 |
| Pairs with ≥1 phrase change | 39 |
| Pairs dropped (anchor null) | 0 |
| Anchor fallbacks (meeting_date) | 0 |
| Final episodes (CAR-ready) | **39** |

**Per-Horizon Descriptive CARs — SHCOMP absolute log (n=39)**

No t-statistics, no p-values, no FDR — unsigned, descriptive only per RUL-5.

| H | n_usable | Mean CAR | Median CAR |
|---|---|---|---|
| 5 | 39 | +0.46% | +0.34% |
| 10 | 39 | +0.34% | −0.08% |
| **20** | 39 | **+0.30%** | **+0.92%** |
| 40 | 39 | +0.85% | +0.27% |
| 60 | 39 | +0.20% | −0.63% |

**Conditioning tables (quad / liquidity / cycle) — cells n<5 show n only per prereg rule:**

| Dimension | Label | n | Mean CAR@H20 | Median CAR@H20 |
|---|---|---|---|---|
| quad | Q1 (goldilocks) | 17 | +1.13% | +1.52% |
| quad | Q2 (reflationary) | 12 | −1.12% | −0.84% |
| quad | Q3 (stagflation) | 5 | +0.82% | +2.50% |
| quad | Q4 (recessionary) | 5 | +0.38% | −1.16% |
| liquidity | contracting | 19 | +0.49% | +0.92% |
| liquidity | expanding | 12 | +1.38% | +1.95% |
| liquidity | neutral | 8 | −1.76% | −1.53% |
| cycle | mid | 33 | +0.64% | +0.92% |
| cycle | late | 6 | −1.55% | +0.19% |

All conditioning observations are descriptive only. No t-stats, no verdict language.

**Run history / data honesty:**

The first F-C computation ran on the pre-fix parquet (48 docs, 47 of 48 null anchor dates) and yielded n_usable=1: only the 2019-Q4 document carried a parseable anchor (2019-12-27), giving a single-observation CAR@H20 of approximately −7.58%. This was observed before any collector fix and is documented in the run_history field of the results JSON.

Two collector bugs were then identified and fixed on the same day (2026-07-06):
- Bug 1 (publish_date null): `_pboc_fetch_article` was trying to extract the publish date from body text (which fails for most MPC readouts). The fix reads the CMS publish stamp directly from the `<span class="hui12">YYYY-MM-DD</span>` adjacent to each article link on the listing page — the reliable source shown in the live HTML.
- Bug 2 (years 2011–2015 missing): The pagination harvester only read the page-1 footer, which linked pages 2 and 4 but not 3. The fix synthesises the full page range (pages 2 through maxN, filling gaps), so all 4 listing pages are now fetched.

This was a data-completeness repair: no event definition, no threshold, no horizon, and no gate was changed. The leg is descriptive/unsigned and carries no verdict in any case.

> **In plain English:** We measured whether MPC quarterly readout communiqués, when their policy-language formula set changes (a phrase appears or disappears), are followed by predictable moves in the Shanghai Composite index. After fixing two bugs in the date-extraction and pagination logic of the collector, all 68 documents have publish dates and 39 of the 67 consecutive quarterly pairs show at least one formula change — all 39 have usable anchor dates. The overall average forward return is near-zero (mean +0.30% at 20 trading days, median +0.92%). By quad: goldilocks-regime events show the largest positive tilt (+1.13% mean), reflationary events are mildly negative (−1.12%). By liquidity: expanding-liquidity events are higher (+1.38%), neutral-liquidity events drag (−1.76%). These are purely descriptive patterns in a small, unsigned sample. No conclusion is drawn. The leg is exploratory only.

---

## Conditioning Tables (Descriptive Only — No t-stats, No Verdict Language)

Regime at event date (last known quad/liquidity/cycle). Cells with n < 5 show n only.

### F-A RRR Ease → SHCOMP abs CAR@H20 by Quad

Regime quad labels: Q1=goldilocks (GG), Q2=reflationary, Q3=stagflation, Q4=recessionary.

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 11 | +0.64% | +3.24% |
| Q2 | 4 | n=4 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 8 | −0.79% | −0.77% |

### F-A RRR Ease → SHCOMP by Liquidity Regime

| Liquidity | n | Mean CAR | Median CAR |
|---|---|---|---|
| contracting | 8 | −3.44% | −2.69% |
| expanding | 11 | +1.59% | +0.99% |
| neutral | 7 | +1.00% | +0.01% |

### F-A RRR Ease → Banks rel CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 8 | +0.16% | −0.15% |
| Q2 | 4 | n=4 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | +2.35% | +2.90% |

### F-A RRR Ease → Banks rel by Sector Phase (partial 2014+)

| Phase | n | Mean CAR | Median CAR |
|---|---|---|---|
| Downturn | 7 | +0.22% | +0.04% |
| Trough | 10 | +0.51% | +0.19% |
| Expansion | 1 | n=1 | — |
| Peak | 1 | n=1 | — |
| Recovery | 1 | n=1 | — |

### F-B LPR Cut → SHCOMP abs CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 6 | −1.24% | −1.17% |
| Q2 | 1 | n=1 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | +2.23% | +3.83% |

### F-B LPR Cut → Banks rel CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 6 | +2.47% | +2.54% |
| Q2 | 1 | n=1 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | −0.74% | −1.21% |

### F-B LPR Cut → Banks rel by Liquidity Regime

| Liquidity | n | Mean CAR | Median CAR |
|---|---|---|---|
| contracting | 5 | −1.32% | −1.21% |
| expanding | 8 | +1.10% | +0.19% |
| neutral | 2 | n=2 | — |

(Full conditioning tables in `data/experiments/china_policy_events_results.json`.)

> No t-stats. No verdict language. Descriptive only. Cells n<5 print n only.

### Sector Cycle Phase (2010 → partial coverage)

Banks sector (801780) phase at F-A event date — see table above. Banks backfill starts 2014-05-30, so most cells are thin. Many F-A events (2008–2013) have no phase data.

(See JSON for full breakdown — many cells n<5 and show n only.)

> **In plain English:** We looked at whether the results change depending on the macro regime at the time of the policy announcement (growth/inflation quad, liquidity regime, cycle phase). The conditioning tables are purely descriptive — no conclusions. With small sample sizes, patterns are unreliable noise. A future amendment with its own pre-registered budget would be required before any conditioning cell could graduate to a formal claim.

---

## Forward Accrual Registry

Three ACCRUE families registered in `data/experiments/registry_seed.json`:

| ID | Come-back | Rationale |
|---|---|---|
| `china-policy-events-fa-banks-rel` | 2028-07-01 | Need ~6 more RRR events for power |
| `china-policy-events-fb-banks-rel` | 2027-07-01 | Need ~3-4 more LPR cuts (T5 strongest) |
| `china-policy-events-fb-restate-rel` | 2029-01-01 | Very weak signal (HAC_t=0.145), low priority |

No-go families (T1 F-A SHCOMP, T3 F-A real estate, T4 F-B SHCOMP) are not registered.

---

## Summary Scorecard

| Family | Sign correct? | HAC-t | Gates passed | Verdict |
|---|---|---|---|---|
| F-A → SHCOMP | No | −0.089 | 0/5 | **NO-GO** |
| F-A → banks | Yes | 0.554 | 0/5 | **ACCRUE** |
| F-A → real estate | No | −1.441 | 0/5 | **NO-GO** |
| F-B → SHCOMP | No | −0.392 | 0/5 | **NO-GO** |
| F-B → banks | Yes | 1.007 | 1/5 (split-half) | **ACCRUE** |
| F-B → real estate | Yes (barely) | 0.145 | 0/5 | **ACCRUE** |
| F-C communiques | — (unsigned) | — (no FDR) | — | **EXPLORATORY-DESCRIPTIVE** (n=39, mean@H20 +0.30%) |

> **In plain English, the full summary:** PBoC rate cuts (RRR and LPR) do not reliably move the A-share market over a 4-week horizon. The broad market results are null-to-negative. Banks show the most consistent positive tilt — LPR cuts in particular produce a modest positive spread vs the market that almost survives our stats bar — but we don't have enough events yet to be confident. Real estate, despite being the sector most directly affected by rate cuts, shows no consistent positive response after netting out the market.
>
> The honest answer is: we measured 15–26 events depending on the series. That's a thin dataset for a high-volatility daily return. We need more events. Come back in 2027–2028.

---

## What Is NOT Shown Here

- No "validated" claims. The word "validated" requires the BC-2 allowlist process.
- No wiring: nothing here feeds any engine, board, or score.
- No post-outcome threshold edits. The prereg is law.
- No p-hacking: 6 gated trials were declared, all 6 are reported including nulls.
