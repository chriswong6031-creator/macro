# CN limit-move ONSET Wave-1 — O1 core and O3 challenger

**Date:** 2026-08-08
**Authority:** context / display / audit only — no rank, sizing, gate, or trade recommendation
**Receipt hash:** `39546d7a48cd68bf333126677bdee8db885d15cecf3e3bd9dde64d123422186e`

## Verdict

### O1_five_axis

- **Verdict:** `NO_GO_FOR_THIS_FIXED_L2_FILLABLE_TRADE_RULE_CONTEXT_MODEL_RETAINED`
- **Measured construction:** fixed-L2 logistic over five D-1 name-local axes; tolerant D first-board; exact-calendar missing as competing zero; D-open queue rule; forced-daily top-K; H1/H3/H5 exact opens
- This verdict closes only the measured construction; its remaining variants are preserved below.

- **Adjudication rule:** positive Brier improvement in main replay+vendor and positive lower 2.5% month-block bound for top20 H1/60bp in main replay, main vendor, and ChiNext-20 transport
- `chinext20_replay_top20_H1_60bp_max_drawdown`: **-74.656%**
- `chinext20_replay_top20_H1_60bp_mean`: **0.568%**
- `chinext20_replay_top20_H1_60bp_month_block_p2_5`: **-0.402%**
- `chinext20_replay_top20_H1_60bp_month_block_p97_5`: **2.291%**
- `main_replay_top20_H1_60bp_max_drawdown`: **-83.526%**
- `main_replay_top20_H1_60bp_mean`: **-0.288%**
- `main_replay_top20_H1_60bp_month_block_p2_5`: **-0.412%**
- `main_replay_top20_H1_60bp_month_block_p97_5`: **-0.164%**
- `main_vendor_top20_H1_60bp_max_drawdown`: **-54.628%**
- `main_vendor_top20_H1_60bp_mean`: **-1.115%**
- `main_vendor_top20_H1_60bp_month_block_p2_5`: **-3.000%**
- `main_vendor_top20_H1_60bp_month_block_p97_5`: **2.815%**

### O1_fixed_equal_rank_blend

- **Verdict:** `KILL_THIS_FIXED_EQUAL_RANK_H1_BOOK_ONLY_H5_EVENT_SEAM_NONPORTFOLIO_AND_VENDOR_UNSTABLE`
- **Measured construction:** equal 20% train-frozen percentile ranks for the five O1 axes, main-calibration probability map, sequential fixed-20-sleeve H1 book; H5 is event-cohort diagnostic only
- This verdict closes only the measured construction; its remaining variants are preserved below.

- **Adjudication rule:** strategy verdict uses sequential no-duplicate fixed-sleeve H1 only; H5 cannot support a portfolio claim
- `main_replay_EVENT_COHORT_top20_H5_30bp_max_drawdown`: **-84.604%**
- `main_replay_EVENT_COHORT_top20_H5_30bp_mean`: **0.111%**
- `main_replay_EVENT_COHORT_top20_H5_30bp_month_block_p2_5`: **-0.635%**
- `main_replay_EVENT_COHORT_top20_H5_30bp_month_block_p97_5`: **0.880%**
- `main_replay_top20_H1_60bp_max_drawdown`: **-73.230%**
- `main_replay_top20_H1_60bp_mean`: **-0.220%**
- `main_replay_top20_H1_60bp_month_block_p2_5`: **-0.349%**
- `main_replay_top20_H1_60bp_month_block_p97_5`: **-0.104%**
- `main_vendor_EVENT_COHORT_top20_H5_30bp_max_drawdown`: **-79.148%**
- `main_vendor_EVENT_COHORT_top20_H5_30bp_mean`: **-2.695%**
- `main_vendor_EVENT_COHORT_top20_H5_30bp_month_block_p2_5`: **-5.178%**
- `main_vendor_EVENT_COHORT_top20_H5_30bp_month_block_p97_5`: **1.272%**
- `main_vendor_top20_H1_60bp_max_drawdown`: **-33.228%**
- `main_vendor_top20_H1_60bp_mean`: **-0.462%**
- `main_vendor_top20_H1_60bp_month_block_p2_5`: **-1.555%**
- `main_vendor_top20_H1_60bp_month_block_p97_5`: **1.202%**

### O1_univariate_U_shape_ore

- **Verdict:** `ORE_SEAM_RETAINED_NOT_A_TRADE_RULE_TWO_ARCHETYPE_MIXTURE_UNTESTED`
- **Measured construction:** train-frozen single-feature deciles; both runup_5 and gap_pct have elevated lowest and highest locked-replay deciles
- This verdict closes only the measured construction; its remaining variants are preserved below.

- `gap_pct_bin0_lift`: **2.235×**
- `gap_pct_bin9_lift`: **2.369×**
- `runup_5_bin0_lift`: **1.413×**
- `runup_5_bin9_lift`: **3.294×**

### O3_washout_transition

- **Verdict:** `KILL_THIS_FIXED_O3_CHALLENGER_ONLY`
- **Measured construction:** O1 plus frozen drawdown/MA200/reversal bases and runup/volume interactions under the same forced-daily top-K ruler
- This verdict closes only the measured construction; its remaining variants are preserved below.

- **Adjudication rule:** lower Brier than O1 plus positive lower 2.5% month-block bound for top20 H1/60bp in main replay, main vendor, and ChiNext-20 transport
- `chinext20_replay_top20_H1_60bp_max_drawdown`: **-83.823%**
- `chinext20_replay_top20_H1_60bp_mean`: **-0.266%**
- `chinext20_replay_top20_H1_60bp_month_block_p2_5`: **-0.457%**
- `chinext20_replay_top20_H1_60bp_month_block_p97_5`: **-0.055%**
- `main_replay_top20_H1_60bp_max_drawdown`: **-77.905%**
- `main_replay_top20_H1_60bp_mean`: **-0.240%**
- `main_replay_top20_H1_60bp_month_block_p2_5`: **-0.408%**
- `main_replay_top20_H1_60bp_month_block_p97_5`: **-0.084%**
- `main_vendor_top20_H1_60bp_max_drawdown`: **-52.594%**
- `main_vendor_top20_H1_60bp_mean`: **-0.978%**
- `main_vendor_top20_H1_60bp_month_block_p2_5`: **-2.863%**
- `main_vendor_top20_H1_60bp_month_block_p97_5`: **3.511%**

## Frozen clock and denominator

- Every candidate is frozen after the exact common-calendar D−1 close.
- D is the exact next observed market session from the completeness-pinned `600519.SS` index. The clock must include 2014-12-25 and the other frozen anchors; the incomplete Shanghai Composite file is not used.
- A missing/halted or zero-volume D bar remains in the primary denominator as event=0, no fill, and cash return=0; it never jumps to a later ticker resumption.
- D open at/within 0.2% of the reconstructed upper limit is queue-required and receives no fill.
- A D purchase exits no earlier than exact D+1/D+3/D+5 open. A missing intervening or scheduled session is cash=0 and never jumps to a resumption; only an observed lower-limit-locked scheduled open may carry one exact session at a time.
- Sector heat is excluded from the core because current sector membership applied backward is historical lookahead.

## Source and universe receipt

- Discovered **1,842** parquet paths. Before opening, excluded **1** current-ST overlap and **0** BSE paths; then opened/read **1,841** with **0** processing errors. Accounting balance: **true**.
- Observed clock: `data/china_stocks_raw/600519.SS.parquet` with **3,786** sessions from 2011 through 2026-08-07; completeness anchors present: **true**.
- Clock consensus: the >=50-name raw-index support set has **3,786** sessions and is set-identical to 600519 (**0** missing / **0** extra). 600519 itself has positive volume on **3,780** sessions and zero/missing volume on **6** genuine sessions; reference volume is explicitly not a market-clock filter.
- Volume census across **1,842** discovered files: the frozen 2011+ analysis window contains **4,985,020** raw rows, including **133,854** exact zero-volume rows and **133,854** nonpositive/missing-volume rows. The lifetime files contain **6,767,465** rows / **277,152** zero-volume placeholders; that pre-2011 tail is outside this analysis. Zero-volume D−1 signal rows excluded: **242,323**; zero-volume D targets retained as missing/no-fill: **11,553**.
- The current-ST snapshot contains **100** names, but only **1** exists in nominal raw. Former-ST history remains unavailable.
- Full candidate denominator: **4,555,042** rows; panel footprint **321.5 MiB**.
- D−1 session rows lacking at least one frozen feature: **669,058**; they are excluded by the predeclared complete-case eligibility rule, not by a future outcome.
- D states: observed positive-volume **4,543,387**; missing/halted/zero-volume **11,554** (absent **1**, zero-volume **11,553**, invalid-price **0**); invalid corporate-action proxy **101**.
- Quantified universe limit: zt_pool has **1,770** distinct names; only **514** overlap nominal OHLCV (**29.04%**); **1,256** are missing OHLCV.
- Source manifest hash: `cbdc15461d0f5c93ddda27af876f7c6bc60e28deeeb0be6dbf5195b498016b9d`.

## Board / era base ladder

| Board era | Block | N | Tolerant rate | Strict rate | Missing/halted D |
|---|---|---:|---:|---:|---:|
| chinext_10 | calibration_2020_2023 | 33,556 | 2.009% | 1.094% | 0.027% |
| chinext_10 | train_2011_2019 | 242,392 | 1.338% | 0.727% | 0.397% |
| chinext_20 | calibration_2020_2023 | 213,544 | 0.240% | 0.126% | 0.019% |
| chinext_20 | historical_replay_after_common_prior | 189,731 | 0.376% | 0.194% | 0.053% |
| chinext_20 | vendor_audit | 13,465 | 0.438% | 0.260% | 0.007% |
| main_10 | calibration_2020_2023 | 1,098,095 | 1.052% | 0.570% | 0.034% |
| main_10 | historical_replay_after_common_prior | 691,536 | 1.089% | 0.569% | 0.126% |
| main_10 | train_2011_2019 | 1,743,707 | 0.775% | 0.401% | 0.504% |
| main_10 | vendor_audit | 46,952 | 2.038% | 1.063% | 0.004% |
| star_20 | calibration_2020_2023 | 99,836 | 0.157% | 0.074% | 0.007% |
| star_20 | historical_replay_after_common_prior | 125,386 | 0.346% | 0.178% | 0.299% |
| star_20 | vendor_audit | 9,003 | 0.666% | 0.333% | 0.033% |

## Main-board probability results

The replay block is explicitly `historical_replay_after_common_prior`, never an unseen test.

| Block | Comparator | N | Brier Δ vs base | Log-loss Δ vs base | ECE | Cal. intercept | Cal. slope |
|---|---|---:|---:|---:|---:|---:|---:|
| Locked replay | O1 fixed equal-rank blend | 691,536 | 0.000076 | 0.002374 | 0.000108 | 1.3142 | 1.2995 |
| Locked replay | O1 fixed-L2 logistic | 691,536 | 0.000050 | 0.002270 | 0.000688 | 1.2392 | 1.2700 |
| Locked replay | O3 fixed-L2 washout challenger | 691,536 | 0.000096 | 0.003591 | 0.000731 | 0.7927 | 1.1712 |
| Vendor audit | O1 fixed equal-rank blend | 46,952 | 0.000091 | 0.001531 | 0.010661 | 0.4377 | 0.9302 |
| Vendor audit | O1 fixed-L2 logistic | 46,952 | 0.000024 | 0.004057 | 0.010085 | -0.3159 | 0.7931 |
| Vendor audit | O3 fixed-L2 washout challenger | 46,952 | -0.000172 | 0.006463 | 0.007579 | -1.0312 | 0.6723 |

Calibration slope/intercept uses damped Newton with a logaddexp objective and backtracking line search; degenerate outcomes are labelled instead of reported as a trusted zero slope.

## Date-block probability uncertainty

Ten-session common-date blocks are resampled with replacement; intervals are day-weighted, never name-row IID.

| Block | Model | Brier Δ point | Bootstrap 2.5% | Bootstrap 97.5% |
|---|---|---:|---:|---:|
| Locked replay | O1 fixed equal-rank blend | 0.000077 | 0.000049 | 0.000122 |
| Locked replay | O1 fixed-L2 logistic | 0.000050 | 0.000039 | 0.000061 |
| Locked replay | O3 fixed-L2 washout challenger | 0.000097 | 0.000073 | 0.000126 |
| Vendor audit | O1 fixed equal-rank blend | 0.000092 | 0.000010 | 0.000225 |
| Vendor audit | O1 fixed-L2 logistic | 0.000024 | -0.000265 | 0.000255 |
| Vendor audit | O3 fixed-L2 washout challenger | -0.000173 | -0.000415 | 0.000056 |

## Frozen fixed-L2 coefficients

Both fits use L2=0.001; the O1 probability map is calibrated only on 2020–23 main-board rows.

| Term | O1 fixed-L2 beta | O3 fixed-L2 beta |
|---|---:|---:|
| intercept | -5.000249 | -4.898704 |
| vol_z20 | 0.267893 | 0.265771 |
| runup_5 | -0.052036 | 0.023448 |
| gap_pct | -0.192115 | -0.075346 |
| dist_52w_low | 0.305712 | 0.163466 |
| consec_up_days | 0.100420 | -0.000474 |
| drawdown_20 | — | -0.516162 |
| ma200_dist | — | 0.143050 |
| reversal_3 | — | 0.258956 |
| washout_x_runup | — | 0.161328 |
| below_ma200_x_vol | — | -0.038569 |
| reversal_x_vol | — | -0.036162 |

## Five-axis univariate ore

All ten train-frozen bins are printed below so a multivariate headline cannot hide a reversal-shaped seam.

| Feature | Locked-replay bin lifts 0→9 | Bin counts 0→9 |
|---|---|---|
| vol_z20 | 0:0.569×, 1:0.528×, 2:0.518×, 3:0.631×, 4:0.714×, 5:0.809×, 6:0.934×, 7:1.165×, 8:1.564×, 9:2.433× | 0:68,020, 1:67,466, 2:67,178, 3:67,333, 4:67,777, 5:69,892, 6:69,761, 7:70,291, 8:71,266, 9:72,552 |
| runup_5 | 0:1.413×, 1:0.694×, 2:0.532×, 3:0.506×, 4:0.543×, 5:0.514×, 6:0.608×, 7:0.847×, 8:1.303×, 9:3.294× | 0:58,127, 1:67,942, 2:74,329, 3:77,034, 4:72,531, 5:77,839, 6:69,760, 7:63,818, 8:60,773, 9:69,383 |
| gap_pct | 0:2.235×, 1:1.127×, 2:0.748×, 3:0.572×, 4:0.572×, 5:—×, 6:0.601×, 7:0.634×, 8:0.948×, 9:2.369× | 0:53,598, 1:62,145, 2:73,383, 3:80,413, 4:67,692, 5:0, 6:159,404, 7:64,698, 8:58,473, 9:71,730 |
| dist_52w_low | 0:0.524×, 1:0.370×, 2:0.387×, 3:0.424×, 4:0.508×, 5:0.703×, 6:0.895×, 7:1.144×, 8:1.572×, 9:2.962× | 0:49,437, 1:50,661, 2:57,158, 3:69,337, 4:77,401, 5:82,916, 6:81,309, 7:76,315, 8:70,285, 9:76,717 |
| consec_up_days | 0:—×, 1:—×, 2:—×, 3:—×, 4:—×, 5:0.813×, 6:—×, 7:0.936×, 8:1.245×, 9:1.867× | 0:0, 1:0, 2:0, 3:0, 4:0, 5:367,256, 6:0, 7:174,184, 8:80,938, 9:69,158 |

## H1 sequential fixed-sleeve book ruler

The H1 book uses K fixed capital sleeves, exits before optional same-open re-entry, forbids duplicate held tickers, and keeps unavailable, queue, no-fill, missing, and unresolved sleeves as cash=0. Filled-only means are diagnostics, not the expectancy headline.

This ruler forces K names on every eligible date. Probability/expected-edge thresholds with cash/no-trade days and point-in-time regime-conditioned exposure remain untested constructions.

| Model | Block | Sleeves | Orders | Order fill rate | H1 gross fixed-sleeve | H1 net 60bp fixed-sleeve | Month-block 95% CI | H1 max DD @60bp | Held-duplicate rows skipped | Unavailable sleeve-days |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| O1 fixed equal-rank | Locked replay | 20 | 4,323 | 99.514% | 0.002% | -0.220% | [-0.349%, -0.104%] | -73.230% | 51 | 7,277 |
| O1 fixed equal-rank | Vendor audit | 20 | 777 | 98.970% | 0.115% | -0.462% | [-1.555%, 1.202%] | -33.228% | 0 | 3 |
| O1 fixed-L2 | Locked replay | 20 | 5,685 | 99.648% | 0.004% | -0.288% | [-0.412%, -0.164%] | -83.526% | 178 | 5,915 |
| O1 fixed-L2 | Vendor audit | 20 | 771 | 98.703% | -0.545% | -1.115% | [-3.000%, 2.815%] | -54.628% | 7 | 9 |
| O3 fixed-L2 | Locked replay | 20 | 4,312 | 99.652% | -0.018% | -0.240% | [-0.408%, -0.084%] | -77.905% | 228 | 7,288 |
| O3 fixed-L2 | Vendor audit | 20 | 775 | 98.839% | -0.404% | -0.978% | [-2.863%, 3.511%] | -52.594% | 2 | 5 |

## Event-cohort overlap diagnostics

H1/H3/H5 rows below are event cohorts. H3/H5 overlap capital and can reselect an already-held ticker, so they are not portfolio returns and never drive a strategy verdict.

| Model | Block | Horizon | Event rows | Overlapping reselections | Overlap rate | Dates with overlap | Max concurrent same-name lots |
|---|---|---|---:|---:|---:|---:|---:|
| O1 fixed equal-rank | Locked replay | H1 | 11,600 | 179 | 1.543% | 156 | 2 |
| O1 fixed equal-rank | Locked replay | H3 | 11,600 | 2,774 | 23.914% | 571 | 5 |
| O1 fixed equal-rank | Locked replay | H5 | 11,600 | 3,827 | 32.991% | 579 | 6 |
| O1 fixed equal-rank | Vendor audit | H1 | 780 | 1 | 0.128% | 1 | 2 |
| O1 fixed equal-rank | Vendor audit | H3 | 780 | 146 | 18.718% | 34 | 3 |
| O1 fixed equal-rank | Vendor audit | H5 | 780 | 207 | 26.538% | 37 | 4 |
| O1 fixed-L2 | Locked replay | H1 | 11,600 | 354 | 3.052% | 254 | 4 |
| O1 fixed-L2 | Locked replay | H3 | 11,600 | 5,675 | 48.922% | 576 | 7 |
| O1 fixed-L2 | Locked replay | H5 | 11,600 | 6,384 | 55.034% | 578 | 12 |
| O1 fixed-L2 | Vendor audit | H1 | 780 | 7 | 0.897% | 7 | 5 |
| O1 fixed-L2 | Vendor audit | H3 | 780 | 577 | 73.974% | 38 | 7 |
| O1 fixed-L2 | Vendor audit | H5 | 780 | 630 | 80.769% | 38 | 9 |
| O3 fixed-L2 | Locked replay | H1 | 11,600 | 630 | 5.431% | 380 | 4 |
| O3 fixed-L2 | Locked replay | H3 | 11,600 | 6,086 | 52.466% | 579 | 8 |
| O3 fixed-L2 | Locked replay | H5 | 11,600 | 6,956 | 59.966% | 579 | 12 |
| O3 fixed-L2 | Vendor audit | H1 | 780 | 3 | 0.385% | 3 | 4 |
| O3 fixed-L2 | Vendor audit | H3 | 780 | 526 | 67.436% | 38 | 6 |
| O3 fixed-L2 | Vendor audit | H5 | 780 | 590 | 75.641% | 38 | 8 |

The fixed equal-rank top-20 H5/30bp **event-cohort diagnostic** has a replay-only seam (0.111%) that reverses sharply in the vendor audit (-2.695%). Because cohorts overlap capital, this is not portfolio evidence; the cross-tail reversal also rejects promotion from the diagnostic seam.

## ChiNext and STAR honesty labels

- `historical_replay_after_common_prior:chinext_20` — **main_fit_main_calibration_transport_not_locally_calibrated**; N=189,731, event rate=0.376%, O1 Brier Δ=-0.000318.
- `historical_replay_after_common_prior:star_20` — **main_fit_main_calibration_transport_not_locally_calibrated:STAR_descriptive_only**; N=125,386, event rate=0.346%, O1 Brier Δ=-0.000328.
- `vendor_audit:chinext_20` — **main_fit_main_calibration_transport_not_locally_calibrated**; N=13,465, event rate=0.438%, O1 Brier Δ=-0.001102.
- `vendor_audit:star_20` — **main_fit_main_calibration_transport_not_locally_calibrated:STAR_descriptive_only**; N=9,003, event rate=0.666%, O1 Brier Δ=-0.001778.

## Forward ledger seed and contract

- Honest prospective seed: **5,352** full-pop model/name rows from signal date **2026-08-07** for entry session **2026-08-10**.
- Every eligible name is emitted, including unselected/no-fire rows. Fillability is `unknown_pending` until the D auction.
- Terminal fillability is exactly three-way: `fillable_daily_proxy`, `queue_required_no_fill`, or `missing_halted_no_fill`.
- Probability identity is stable across calendar corrections: `signal_date+ticker+model_version+limit_definition+entry_rule`; `entry_session` is immutable payload. A corrected entry date therefore raises a keep-first mutation instead of appending a duplicate.
- Probability and grade helpers are separate and reject non-nightly caller labels, non-context authority, non-finite/boundary probabilities, an unexpected model family, malformed existing stores, or a non-recomputable universe ID.
- Event grades are full-population (`EVENT_D`, one per probability). Execution/return grades are separate per H1/H3/H5 and permitted only for selected orders; an unfilled order has `gross_return=null`, null conditional net returns, an explicit terminal no-fill state, and `book_contribution_return=0`—never a fabricated flat trade.
- The one Aug-10 entry session is frozen by the construction map. Recurring advancement fails closed until an authoritative annual SSE/SZSE calendar is wired; grading requires the exact observed market-session index.
- JSONL is a capped **10-session bridge**: this seed is **5.84 MiB**, implying about **58.44 MiB** at the cap. Normalized monthly Parquet probability/grade partitions remain unbuilt.
- **No recurring nightly advancer or grader is wired in this packet.** This is a contract plus one honest seed only; there are no fabricated grades and no claim of recurring advancement.
- A future production runner must load these frozen fitted parameters, discover a dynamic latest-complete observed session, and fail closed on future-calendar ambiguity. It must not import the analysis-end-pinned research builders or refit nightly.
- Retrospective rows seeded as prospective history: **0**.

## Limitations

- survivorship-biased curated raw store; delisted/missing small caps absent
- historical ST membership unavailable; current-ST exclusion cannot heal former-ST rows
- five-axis complete-case eligibility excludes early-history/incomplete feature rows; the source receipt quantifies those rows
- daily OHLC cannot observe auction queue, partial fill, first-touch, or intraday exit
- the observed-session clock is set-attested to a >=50-name raw-index consensus, but is not an official exchange master calendar
- missing or zero-volume exact sessions are primary event-zero/cash-zero competing states; observed-only is sensitivity
- 2015 stress is in-sample descriptive and is not an independent confirmation
- replay follows common-prior sign exposure and is never labelled unseen test
- strict definition is evaluated with tolerant-trained scores as sensitivity, not a second tuned model
- sector heat excluded because current sector membership applied historically leaks
- H3/H5 returns are overlapping event-cohort diagnostics, not capital books; a fixed-capital multi-session sleeve remains unbuilt
- H1 fixed-sleeve returns are attributed to entry cohorts; any lower-limit carry count must be read beside the compounding proxy
- forward seed is one honest ungraded snapshot, not prospective performance history
- recurring nightly probability advancement and grading are not wired; helpers only enforce the contract when called
- frozen research builders stop at 2026-08-07 and are forbidden as a recurring runner; a future runner must load frozen parameters against a dynamically discovered latest-complete observed session without refitting

## UNTESTED VARIANTS

- recurring nightly probability advancement and grading integration; only contract helpers and one honest seed are built
- probability or expected-edge thresholds that permit cash/no-trade days instead of forcing daily top-K names
- point-in-time regime-conditioned exposure or a lagged-ecology probability offset
- two-archetype washout-versus-momentum mixture for the observed run-up/gap U-shapes
- fixed-capital multi-session sleeve allocation for H3/H5 with exit-date PnL attribution
- authoritative annual SSE/SZSE future-session calendar for recurring ledger advancement
- normalized monthly Parquet probability/grade partitions beyond the capped ten-session JSONL bridge
- a production forward runner that loads frozen fitted parameters, discovers the dynamic latest-complete observed session, and never refits nightly or imports the frozen research panel/calendar path
- pre-close and intraday near-limit onset entries
- actual auction queue depth, order priority, partial fills, and first-5-minute execution
- historically complete ST membership, BSE, delisted names, and missing small-cap OHLCV
- point-in-time THS concept/sector heat and leader-follower relay
- news class, filing surprise, fair-value distance, and A/H/N uncapped rerating oracles
- free-float turnover, seal-wall normalization, first-touch time, and seal-break/reseal entries
- tree/boosting, survival/hazard, nested feature selection, and family-wise promotion tests
- live slippage, commissions, stamp duty, capacity, theme caps, and book-level dependence
- exit at close, trailing stops, close-seal state machines, and limit-down release reversal
- prospective calibration beyond the single honest seed; ten graded sessions are still required
