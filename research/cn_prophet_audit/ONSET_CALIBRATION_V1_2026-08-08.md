# CN ONSET MODEL v1 — calibrated P(limit-up close) + the program's forward-ledger seed

**Program:** CN LIMIT-MOVE ALPHA, Wave 1 / lane L3 (the calibrated onset model).
**Predecessor:** `research/cn_prophet_audit/limit_move_footprint_v0.py` (PR #4999) ·
**Instrument:** `research/cn_prophet_audit/onset_calibration_v1.py` ·
**Frozen numbers:** `ONSET_CALIBRATION_V1_2026-08-08.json` · **Ledger:** `onset_forward_ledger.jsonl` ·
**Runtime:** ~20s · **Window:** 2011-01-04 → 2026-08-07 · **Basis:** `data/china_stocks_raw` (nominal OHLCV).

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks for size, gates, admits, promotes,
or reaches a live surface. No LLM is involved at any point. **No number is pooled across board
types.** The holdout was scored exactly once; nothing was refit, retuned, or re-split after seeing it.

---

## DECISION SUMMARY

**1. NO. B1 does not clear the pre-registered bar.** The criterion was a positive holdout Brier
skill against the 连板 base-rate ladder. It is **negative on both modelled boards**:

| Board | holdout rows | base | **B1 Brier skill vs ladder** | log-loss skill | **AUC (B1 / ladder)** |
|---|---|---|---|---|---|
| main | 1,283,376 | 1.204% | **−0.17%** | **+4.61%** | **0.775 / 0.592** |
| chinext | 135,753 | 0.357% | **−11.69%** | −11.68% | **0.726 / 0.540** |
| star | — | — | **THIN-SKIP** (40 fit-core positives vs a floor of 150) | — | — |

**2. The failure is CALIBRATION, not discrimination — measured, not pleaded.** The exact Murphy
decomposition of that same holdout Brier (`BS = RELIABILITY − RESOLUTION + UNCERTAINTY`, identity
residual 0.0) splits it cleanly. On main, B1's RELIABILITY term is **0.0241 vs the ladder's 0.0108**
— it is **2.2× worse calibrated** — while RESOLUTION is a dead heat (**0.4792 vs 0.4850**). B1 knows
the order far better than the ladder does and states the wrong level.

**3. Brier and AUC disagree here, and the reason decides how to read every table below.** Brier's
resolution term is **quadratic** in a group's deviation from the base rate, so it pays enormously
for isolating a tiny group at an extreme rate — precisely what the ladder does (main N≥3: 1,035
holdout rows at 45.80% against a 1.204% base) — and pays almost nothing for correctly ordering the
1.27M-row N=0 bulk from 0.21% to 5.22%, which is what B1 does. Neither metric is wrong. **The
pre-registered bar was Brier and B1 misses it.** That is the ruling; the rest is why.

**4. The calibration failure has one measured cause, and no feature can fix it.** A frozen isotonic
map inherits the base rate of the slice it was fitted on.

| Board | fit-core base | **isotonic slice base** | holdout base | **slice ÷ holdout** | B1 mean P̂ ÷ realized |
|---|---|---|---|---|---|
| main | 1.073% | **1.563%** | 1.204% | **1.30×** | 1.06× |
| chinext | 0.254% | **0.735%** | 0.357% | **2.06×** | **2.58×** |

ChiNext's calibration slice ran **2.06× hotter** than its holdout, and B1 over-predicts it by
**2.58×**. That is essentially the whole miscalibration, arriving from the *design of the
calibration step*, not from the features. This is exactly the regime problem lane L2's instruments
exist for, and it is the single highest-value Wave-2 merge.

**5. Where the curve bends — main: everywhere, as a slope error.** B1 over-predicts below ~1.5% and
under-predicts above it. **0 of 9 bins** fall inside the realized Wilson 95%; ECE **0.214pp** on a
1.204% base (18% of base). The realized curve is **steeper** (25.5× bottom-to-top) than the
predicted one (15.1×) — the model is *under*-confident about its own discrimination.

**6. Where the curve bends — ChiNext: only in the tail, and violently.** The bottom **6 of 8** bins
sit inside their Wilson intervals. The entire failure is the top two: bin 7 predicts 1.480% and
realizes 0.681%; bin 8 predicts **8.586%** and realizes **1.535%**. ECE 0.574pp on a 0.357% base —
a 161%-of-base error, concentrated exactly in the part of the book a desk would trade.

**7. A hand-built lookup table beats the model on main.** B2 — fit-window rates in
(f3 quintile × f6 quintile × N) cells — is the only six-feature model with **positive** Brier skill
(**+0.32%**), the best ECE (**0.130pp**), 5 of 10 bins inside CI, and the best top-10 realized rate
(**17.84%**). **The parametric machinery bought nothing over a lookup table.** That is the B2 sanity
check firing as designed, and it is a finding, not a fluke: B2's RESOLUTION (0.548) beats B1's
(0.479) outright.

**8. The parsimony probe is blunt.** P2 (f3 + N dummies, five features deleted) posts the **best
Brier skill on main at +0.71%** — better than B1, B2 and the ladder — and is **positive in all 6
holdout years** where B1 is positive in 2. The other five features cost Brier skill and buy ranking
*depth*: at K=50 the full model captures **27.18%** of the board's limit-ups against P1's 24.73%.
f3 **alone** (P1) is the worst model tested: **−1.65%**.

**9. f3's coefficient flips sign once the ladder is in the model.** Same board, same fit window:

| Main-board model | f3 coefficient |
|---|---|
| P1 — f3 alone | **+0.473** |
| P2 — f3 + N dummies | **+0.076** (−84%) |
| B1 — f3 + N + the other five | **−0.087** (sign flip) |

v0's 3.93× marginal top-decile lift on f3 is, on the main board, **substantially the 连板 ladder
wearing a feature's clothes**: a name with a big 5-session run-up is disproportionately a name
already mid-ladder. **Nothing in v0 is overturned** — a marginal decile lift and a partial
coefficient are different objects and v0 claimed only the former — but anyone reading 3.93× as
"run-up is the signal" is reading it wrong on main. On ChiNext f3 survives conditioning and stays
positive (+0.601 → +0.444 → +0.230).

**10. Top-K: the ladder is unbeatable at the head of the book and loses from K≈20 out.** Main, 1,135
holdout dates: at K=10 B1 realizes **16.58% vs the ladder's 16.85%** (the ladder wins); at K=50 B1
realizes **7.40% vs 5.49%** and captures **27.18% vs 20.18%**. The reason is structural — on a given
date only a handful of names carry N≥2, so past its top tie group the ladder is choosing
*arbitrarily* (ties broken by ticker) while B1 keeps ranking. **The model's value is the DEPTH of the
daily book, not its head.**

**11. On ChiNext the model is a far better ranker and a far worse probability.** Top-10 realized
**2.356% vs the ladder's 1.062%** (2.2×); K=50 capture **46.4% vs 22.5%**. And its top-10 mean P̂ is
**10.198%** against that 2.356% realized — **4.33× too high**. Rank with it; do not quote it.

**12. The live book saturates at the isotonic ceiling.** Six main-board names all price at exactly
**27.03%** — the isotonic's last block value — so **the head of the published book is unordered by
construction**, and the "top 5" below is 5 of 6 tied names in ticker order. Worse: the ladder's own
holdout-verified **45.80%** for N≥3 is a *better* probability for those names than B1's 27.03%. At
the extreme top of the book the benchmark should be quoted, not the model.

**13. STAR is a printed THIN-SKIP, and the cause is the split as much as the rarity.** 40 fit-core
positives against the pre-registered floor of 150 — but **612 holdout positives**. STAR listed in
2019, so v0's global 70/30 *date* split hands it 565 fit dates and 1,135 holdout dates: a 33/67
split. A STAR-era re-split (what ChiNext already gets) is the named unblock in the ORE LEDGER and is
**deliberately not applied here** — changing a split after watching a gate fail is the exact move
this design exists to block.

**14. The panel is v0's — verified, not assumed.** This file re-derives v0's panel from scratch
(v0 lives on a sibling branch). **10 of 10** published v0 numbers reproduce exactly, including the
split date, both date counts, the main holdout base rate and row count, the ChiNext era row count
and era split date, and all three boards' limit-up event counts.

**15. Ledger seeded: 2,100 rows.** 2,000 retro (last 20 holdout dates × top-50 × 2 modelled boards)
and **100 live** at feature date **2026-08-07** → predict date **2026-08-10**.

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw` — nominal/unadjusted. The adjusted twin would fabricate limit misses. |
| Names | 1,842 files · 1,836 kept · main 1,243 · chinext 351 · star 242 · bse 0 |
| Ticker-days | 4,981,168 · live after exclusions 4,843,576 · usable pairs 4,821,371 |
| **Modelled rows (complete-case)** | **4,406,515 — 91.4% of usable.** NOT imputed. |
| Complete-case drops | f4 sector heat **305,372** · f7 52w-low 118,042 · f1 vol-z 13,007 · f3 1,880 · f6/f8 0 |
| Complete-case bias | The dominant cause is f4 being null wherever the name has no row in the CURRENT sector map — a **universe property, not a random one**, so the modelled row set is mildly non-random in sector coverage. Stated, not corrected: imputing sector heat for a name with no sector is inventing the feature. |
| Excluded bars | zero-volume/suspension 133,781 · IPO window 2,793 · ex-div suspect 621 |
| Sector coverage | 93.68% of ticker-days (`data/china_search/members.parquet`) |
| **Sector map caveat** | **CURRENT membership applied to 15y of history.** f4 measures heat within *today's* sector definition and within *this curated* universe — not within the sector as constituted in 2013. |
| **Universe is curated** | The binding fact, inherited from v0: ~1,836 names against a listed A-share market of roughly 5,400, with only **514 of 1,770 (29%)** of `china_zt_pool`'s limit-up names present. **Every probability here is calibrated ON and FOR that curated universe.** The 打板 game is densest in the small-cap and ST names it omits. |
| Survivorship | The store holds the CURRENT listed universe. Milder for the limit-UP question than for limit-down, but not zero: a name that ran, collapsed and delisted contributes neither its run-ups nor its failures. |
| Resolution-conditioned denominator | Usability at the next bar is a property of the *next* bar, so conditioning on it is a filter a trader at the feature close could not apply. Applied uniformly to numerator and denominator; **these are rates among USABLE next bars**, not among all next bars. |
| Clock | `TZ=UTC` throughout. The receipt is dated 2026-08-08 (local); the stamp reads `2026-08-09T00:13Z`. Feature date 2026-08-07, predict date 2026-08-10. |

---

## DEFINITIONS (inline, as required)

- **Target `y`** — the name closes at the limit (PRIMARY definition) on its **next usable bar**. One
  bar, H=1.
- **Naming** — v0 calls the feature bar `T−1` and the graded bar `T`; the ledger schema calls them
  `feature_date_T` and `predict_date`. **Same two bars, different labels.**
- **`limit_up_close` (PRIMARY)** — `close ≥ round(prev_close×(1+w), 2) × (1 − 0.002)`. v0's
  adjudicated primary: 43.4% of the marginal events moved strictly *more* than the full band —
  impossible for a real limit-up, therefore feed price noise — and the independent `china_zt_pool`
  vendor scrape agrees with the tolerant 连板 reconstruction on 99.8% of matched rows vs 91.1% for
  strict.
- **`w`** — `engine.china_microstructure.limit_width_for_date` (imported, era-aware): STAR 20%,
  ChiNext 20% on/after 2020-08-24 else 10%, main 10%, BSE 30%.
- **`连板 N`** — consecutive limit-up closes ending on the feature bar; any non-limit bar, including
  an excluded one, resets it to 0. Modelled as a categorical **0 / 1 / 2 / 3+**, N=0 the reference.
- **Usable pair** — the two bars ≤ 10 calendar days apart and the next bar not itself excluded.
- **Exclusions** — ST cohort (all dates), STAR/ChiNext first 5 sessions, pre-2014 listings' first
  session, ex-dividend suspects (`|open − prev_close|/prev_close > 1.5w`), zero-volume bars.
- **Brier skill** — `1 − Brier(model)/Brier(B0)`. Positive beats the ladder.
- **Reliability** — holdout rows binned into deciles **of the predicted probability**; each bin
  reports mean P̂ against the realized rate with a Wilson 95% interval on the realized side. A model
  with fewer distinct predictions than requested bins is binned on its distinct values instead
  (without this, B0's four numbers collapse into one bin and its ladder structure disappears).
- **ECE** — `Σ (n_bin/N) × |mean P̂ − realized|`.
- **Capture share** — the share of a date's realized limit-ups contained in the top-K selection,
  pooled over holdout dates.
- **AUC** — rank concordance, invariant to any monotone recalibration: the discrimination number.
- **Murphy decomposition** — grouped on *distinct predicted values*, so `BS = REL − RES + UNC` holds
  exactly. RES is what a perfect recalibration would keep; REL is what it would delete.

### The models

| | Definition |
|---|---|
| **B0** | Fit-window base rate per 连板 bucket. Calibrated by construction. **Fitted on the WHOLE fit window — deliberately more data than B1 gets, so the comparison is conservative in the benchmark's favour.** |
| **B1** | Six features + N dummies. Winsorised (1/99) and standardised **on the fit CORE only**. Logistic on the fit core (first 85% of fit dates); isotonic on the fit CALIBRATION slice (last 15% of fit dates — out-of-sample for the logistic, **never the holdout**); frozen. |
| **B2** | Fit-window rate in (f3 quintile × f6 quintile × N) cells, shrunk toward the N-marginal with a pseudo-count of 20; cells thinner than 20 fall back to the N-marginal entirely. A plain Laplace `(k+1)/(n+2)` would read 3.7% for an empty n=25 cell at a ~1% base, so the prior is the N-marginal, not a uniform one. |
| **P1 / P2** | Parsimony probes: f3 alone, and f3 + N dummies. Same calibration treatment. |

### The features — six, and why not eight

The set is v0's pre-registered eight **minus the two v0's own holdout retired**. No new feature is
introduced. The one addition is 连板 N, which is not a new feature — it is benchmark B0 itself, and
B1 must beat B0 while containing it.

| # | Feature | Status |
|---|---|---|
| f1 | volume z-score of the feature bar vs its own prior 20 bars | in |
| f2 | turnover ratio | **NULL — not measurable.** No CN store carries per-date shares outstanding. No proxy substituted. |
| f3 | 5-session run-up, `close[T−1]/close[T−6] − 1` | in |
| f4 | same-day sector limit-up count, **leave-one-out** | in |
| f5 | prior-session near-limit flag | **RETIRED — UNSTABLE in v0** (per-name median lift 0.00, sign flip on STAR, 65.2×→0.00× collapse in the ChiNext era control). Re-admitting it into a probability model would launder the exact false discovery v0's pre-registration caught. |
| f6 | gap at the feature bar's open | in |
| f7 | distance from the 52w low | in |
| f8 | consecutive up-close days | in |

### Splits — FROZEN, and ChiNext's is deliberately different

| Board | rule | fit core | isotonic slice | holdout |
|---|---|---|---|---|
| main | v0 global 70/30 | 2011-01-04 → 2020-04-08 | 2020-04-09 → 2021-11-25 | **2021-11-26 → 2026-08-06** |
| star | v0 global 70/30 | 2011-01-04 → 2021-07-20 | 2021-07-21 → 2021-11-25 | 2021-11-26 → 2026-08-06 |
| chinext | **±20% band era, re-split within it** | 2020-08-24 → 2024-03-07 | 2024-03-08 → 2024-10-24 | **2024-10-25 → 2026-08-06** |

ChiNext is restricted to the ±20% era because the global split lands *after* the 2020-08-24 band
change: a globally-split ChiNext model would be fitted mostly on a 10%-band market and evaluated
entirely on a 20%-band one — a rule change, not a signal. This is v0's own era control, adopted
unchanged.

### Grading spec (the ledger's contract)

- **Binary outcome** = a limit-up **close** under the PRIMARY definition on the row's `predict_date`
  usable bar. That is the whole grade.
- **Recorded alongside, NEVER blended into the grade**: realized next-close return, and the
  near-limit flag (`return ≥ 0.95w` and not a limit close).
- **Ungradeable ≠ 0.** A row whose `predict_date` bar is missing, excluded, or more than 10 calendar
  days later grades **UNGRADEABLE**. Scoring a suspension as a miss would manufacture skill.
- **Re-resolve `predict_date` against the store at grading time.** Rows carry
  `predict_date_source`; the 100 live rows are stamped `next_weekday_calendar_estimate` and have
  **no holiday calendar applied**.
- **Append-only, nightly is the sole advancer.** This script writes the SEED whole (idempotent
  re-run, no duplicate appends); from the Wave-2 wiring onward the file is append-only.
- The ledger deliberately carries **no outcome column**. Grading reads the store, not our copy.

---

## HOLDOUT — HEADLINE (one evaluation pass)

### Main board — 1,283,376 rows, 15,455 positives, base 1.204%

| Model | Brier ×1000 | **Brier skill** | log-loss skill | **AUC** | REL ×1000 | RES ×1000 | ECE | bins in CI |
|---|---|---|---|---|---|---|---|---|
| **B0** ladder | 11.4232 | — | — | 0.5921 | 0.0108 | 0.4850 | 0.069pp | 2/4 |
| **B1** 6 feat + N | 11.4423 | **−0.17%** | **+4.61%** | **0.7753** | 0.0241 | 0.4792 | 0.214pp | **0/9** |
| B1 uncalibrated | 11.5461 | −1.08% | +3.56% | 0.7758 | *degenerate* | *degenerate* | — | — |
| **B2** buckets | 11.3866 | **+0.32%** | +3.50% | 0.7426 | 0.0371 | **0.5479** | **0.130pp** | 5/10 |
| P1 f3 alone | 11.6116 | −1.65% | −0.23% | 0.6777 | 0.0128 | 0.2987 | — | — |
| **P2** f3 + N | 11.3425 | **+0.71%** | +2.66% | 0.6886 | 0.0158 | **0.5708** | 0.267pp | 0/3 |

UNCERTAINTY = 11.8974 ×1000 for every model. *B1 uncalibrated's Murphy terms are degenerate — its
predictions are near-unique, so each group holds one row and RES collapses onto UNC. Flagged in the
JSON, not readable.*

### ChiNext (±20% era) — 135,753 rows, 485 positives, base 0.357%

| Model | Brier ×1000 | **Brier skill** | log-loss skill | **AUC** | REL ×1000 | RES ×1000 | ECE | bins in CI |
|---|---|---|---|---|---|---|---|---|
| **B0** ladder | 3.5490 | — | — | 0.5396 | 0.0145 | 0.0255 | 0.065pp | 2/4 |
| **B1** 6 feat + N | 3.9637 | **−11.69%** | −11.68% | **0.7259** | **0.4381** | 0.0343 | 0.574pp | 6/8 |
| B2 buckets | 3.5502 | −0.03% | +2.04% | 0.6908 | 0.0252 | 0.0350 | **0.093pp** | 6/10 |
| P1 f3 alone | 3.7322 | −5.16% | −4.02% | 0.6658 | 0.1881 | 0.0159 | — | — |
| P2 f3 + N | 3.6932 | −4.06% | −2.12% | 0.6672 | 0.1642 | 0.0309 | 0.275pp | 3/5 |

B1's RELIABILITY is **30× the ladder's**. Its RESOLUTION is the best of the four. Good ranker,
broken level.

---

## RELIABILITY — THE PRODUCT SPINE

### Main board, B1 (9 realized bins; ECE 0.214pp; **0 of 9 inside CI**)

| bin | n | predicted | realized | Wilson 95% | calibrated |
|---|---|---|---|---|---|
| 1 | 151,926 | 0.302% | 0.205% | 0.184 – 0.229 | no (over) |
| 2 | 189,710 | 0.460% | 0.298% | 0.274 – 0.323 | no (over) |
| 3 | 209,794 | 0.659% | 0.457% | 0.429 – 0.487 | no (over) |
| 4 | 160,024 | 0.881% | 0.646% | 0.608 – 0.686 | no (over) |
| 5 | 134,563 | 1.101% | 0.898% | 0.849 – 0.950 | no (over) |
| 6 | 73,401 | 1.220% | 1.089% | 1.016 – 1.166 | no (over) |
| 7 | 112,340 | 1.514% | 1.361% | 1.295 – 1.431 | no (over) |
| 8 | 124,230 | 1.851% | 1.928% | 1.853 – 2.006 | **no — by 0.002pp** |
| **9** | 127,388 | **4.560%** | **5.224%** | 5.103 – 5.348 | **no (UNDER)** |

**The bend is a slope, not an offset.** Realized spans 25.5× bottom-to-top; predicted spans 15.1×.
Bin 8 misses by 0.002pp and is calibrated in every practical sense. The two ends are the problem.

### ChiNext, B1 (8 realized bins; ECE 0.574pp; 6 of 8 inside CI)

| bin | n | predicted | realized | Wilson 95% | calibrated |
|---|---|---|---|---|---|
| 1 | 50,573 | 0.119% | 0.125% | 0.097 – 0.159 | **yes** |
| 2 | 5,529 | 0.170% | 0.181% | 0.098 – 0.333 | **yes** |
| 3 | 15,686 | 0.178% | 0.204% | 0.145 – 0.288 | **yes** |
| 4 | 18,140 | 0.323% | 0.259% | 0.195 – 0.344 | **yes** |
| 5 | 17,526 | 0.452% | 0.411% | 0.326 – 0.517 | **yes** |
| 6 | 2,678 | 0.551% | 0.448% | 0.257 – 0.782 | **yes** |
| 7 | 16,890 | 1.480% | 0.681% | 0.568 – 0.817 | **no — 2.2× over** |
| **8** | 8,731 | **8.586%** | **1.535%** | 1.297 – 1.815 | **no — 5.6× over** |

**Six of eight bins are calibrated. The model is broken exactly where it matters.**

### The benchmark is not perfect either — B0, both boards

| Board | N | n | predicted (fit) | realized (holdout) | calibrated |
|---|---|---|---|---|---|
| main | 0 | 1,267,878 | 0.932% | 0.983% | no (under) |
| main | 1 | 12,506 | 15.039% | 15.593% | **yes** |
| main | 2 | 1,957 | 37.194% | **29.024%** | **no — 1.28× over** |
| main | 3+ | 1,035 | 45.331% | 45.797% | **yes** |
| chinext | 0 | 135,259 | 0.286% | 0.329% | no (under) |
| chinext | 1 | 454 | 13.038% | **7.269%** | **no — 1.79× over** |
| chinext | 2 | 33 | 22.680% | 15.152% | yes (thin) |
| chinext | 3+ | 7 | 47.500% | 28.571% | yes (**THIN, n=7**) |

The ladder drifts too. Its main-board N=2 cell over-states by 28%, and ChiNext's N=1 cell by 79%.
Its advantage is that it is *only* four numbers, so it has little room to be wrong.

---

## TOP-K DAILY BOOK (the operator's spreading math)

Per holdout feature-date, rank by P̂ and take the top K. Ties broken by ticker ascending —
**deterministic, and load-bearing for B0**, which has four distinct values and therefore selects an
essentially arbitrary K names from inside its top tie group. That is not a measurement defect; it is
the statement that a ladder is a calibration benchmark, not a ranker.

### Main board — 1,135 dates, 15,455 positives available, base 1.204%

| Ranker | K | rows | hits | **realized** | lift | mean P̂ | P̂ ÷ realized | **capture** |
|---|---|---|---|---|---|---|---|---|
| **B1** | 10 | 11,350 | 1,882 | 16.581% | 13.8× | 14.377% | 0.87 | 12.18% |
| **B0** | 10 | 11,350 | 1,912 | **16.846%** | 14.0× | 18.265% | 1.08 | **12.37%** |
| B2 | 10 | 11,350 | 2,025 | **17.841%** | 14.8× | 18.042% | **1.01** | **13.10%** |
| P1 | 10 | 11,350 | 1,491 | 13.137% | 10.9× | 10.959% | 0.83 | 9.65% |
| **B1** | 20 | 22,700 | 2,796 | **12.317%** | 10.2× | 10.504% | 0.85 | **18.09%** |
| B0 | 20 | 22,700 | 2,532 | 11.154% | 9.3× | 12.058% | 1.08 | 16.38% |
| B2 | 20 | 22,700 | 2,846 | **12.537%** | 10.4× | 12.084% | 0.96 | **18.41%** |
| P1 | 20 | 22,700 | 2,319 | 10.216% | 8.5× | 8.805% | 0.86 | 15.01% |
| **B1** | 50 | 56,750 | 4,201 | **7.403%** | 6.2× | 6.399% | 0.86 | **27.18%** |
| B0 | 50 | 56,750 | 3,118 | 5.494% | 4.6× | 5.894% | 1.07 | 20.18% |
| B2 | 50 | 56,750 | 4,041 | 7.121% | 5.9× | 6.540% | 0.92 | 26.15% |
| P1 | 50 | 56,750 | 3,822 | 6.735% | 5.6× | 5.874% | 0.87 | 24.73% |

**Read the K column, not the row.** At K=10 the ladder wins outright. At K=20 B1 pulls ahead by
1.2pp of realized rate and 1.7pp of capture. At K=50 it is 7.40% vs 5.49% — **+35% relative** — and
27.2% vs 20.2% capture. Calibration-in-the-tail: B1 **under**-states by ~15% at every K, the ladder
**over**-states by ~8%, and B2 is nearest to honest (1.01 at K=10).

### ChiNext — 433 dates, 485 positives available, base 0.357%

| Ranker | K | rows | hits | **realized** | lift | mean P̂ | **P̂ ÷ realized** | **capture** |
|---|---|---|---|---|---|---|---|---|
| **B1** | 10 | 4,330 | 102 | **2.356%** | 6.6× | 10.198% | **4.33** | **21.03%** |
| B0 | 10 | 4,330 | 46 | 1.062% | 3.0× | 1.864% | 1.76 | 9.48% |
| B2 | 10 | 4,330 | 91 | 2.102% | 5.9× | 2.741% | **1.30** | 18.76% |
| P1 | 10 | 4,330 | 90 | 2.079% | 5.8× | 7.432% | 3.58 | 18.56% |
| **B1** | 20 | 8,660 | 132 | 1.524% | 4.3× | 7.428% | **4.87** | **27.22%** |
| B0 | 20 | 8,660 | 56 | 0.647% | 1.8× | 1.078% | 1.67 | 11.55% |
| B2 | 20 | 8,660 | 126 | 1.455% | 4.1× | 1.879% | 1.29 | 25.98% |
| P1 | 20 | 8,660 | 140 | 1.617% | 4.5× | 4.916% | 3.04 | 28.87% |
| **B1** | 50 | 21,650 | 225 | 1.039% | 2.9× | 4.188% | **4.03** | **46.39%** |
| B0 | 50 | 21,650 | 109 | 0.503% | 1.4× | 0.603% | 1.20 | 22.47% |
| B2 | 50 | 21,650 | 197 | 0.910% | 2.6× | 1.154% | 1.27 | 40.62% |
| P1 | 50 | 21,650 | 214 | 0.989% | 2.8× | 2.474% | 2.50 | 44.12% |

**The clearest split in the study.** B1 doubles the ladder's hit rate at every K and captures more
than twice as many boards at K=50 — while quoting probabilities **4–5× too high**. B2 achieves 87%
of B1's capture with a P̂ ratio of 1.27–1.30. **On ChiNext today, B2 is the shippable object and B1
is not.**

---

## PER-YEAR SKILL STABILITY (Brier skill vs the ladder, %)

### Main

| Year | n | base | **B1** | B2 | P1 | **P2** |
|---|---|---|---|---|---|---|
| 2021 (part) | 28,530 | 1.546% | −1.04 | +0.40 | −2.32 | +0.26 |
| 2022 | 268,910 | 1.164% | −0.79 | −0.21 | −2.50 | +0.14 |
| 2023 | 271,381 | 0.675% | **+0.24** | +0.50 | −0.88 | +0.49 |
| 2024 | 272,674 | 1.291% | −0.39 | +0.54 | −2.53 | +1.06 |
| 2025 | 277,913 | 1.225% | −0.08 | +0.40 | −1.46 | +0.68 |
| 2026 (part) | 163,968 | 1.908% | **+0.48** | +0.42 | −0.42 | +1.11 |

**B1 positive in 2 of 6 years; B2 in 5 of 6; P2 in 6 of 6.** Note the base rate swings 0.675% →
1.908% across the holdout — a 2.8× regime range inside the *evaluation* window alone. That range is
the direct evidence for ORE item #1.

### ChiNext (±20% era)

| Year | n | base | **B1** | B2 | P1 | P2 |
|---|---|---|---|---|---|---|
| 2024 (part) | 14,471 | 0.553% | −4.22 | **+0.25** | −2.56 | −2.14 |
| 2025 | 75,580 | 0.327% | −11.58 | −0.05 | −5.01 | −4.02 |
| 2026 (part) | 45,702 | 0.346% | **−15.57** | −0.16 | −6.69 | −5.09 |

B1's ChiNext skill gets **monotonically worse** as the holdout ages away from the calibration slice
— the regime signature, arriving on schedule.

---

## THE FORWARD LEDGER

`research/cn_prophet_audit/onset_forward_ledger.jsonl` — **2,100 rows**, one per
name-date-prediction, deterministically ordered by (era, feature_date_T, board, −P̂, ticker).

| | |
|---|---|
| retro | **2,000** — last 20 holdout feature-dates (2026-07-10 → 2026-08-06) × top-50 × {main, chinext} |
| live | **100** — feature date **2026-08-07**, predict date **2026-08-10**, top-50 × {main, chinext} |
| star | **0 rows** — THIN-SKIP, no model, so nothing is stamped. A printed null, not an omission. |
| P̂ source | calibrated B1. `p_b0` carries the ladder benchmark on every row so the ledger grades both. |

### Live stamp, 2026-08-07 → 2026-08-10

**Read the ties.** Six main-board names share the isotonic ceiling of 27.03%, so the five below are
5 of 6 tied names in ticker order — **not a ranking**. And for the N≥3 names the ladder's
holdout-verified 45.80% is the better number.

| Board | Ticker | N | **B1 P̂** | ladder P̂ | f3 5d run-up | f1 vol-z | f4 sector heat |
|---|---|---|---|---|---|---|---|
| main | 001267.SZ | 4 | 27.03% *(tied)* | **45.33%** | +43.2% | +3.16 | 0 |
| main | 002194.SZ | 2 | 27.03% *(tied)* | 37.19% | +26.6% | +6.75 | 9 |
| main | 002428.SZ | 4 | 27.03% *(tied)* | **45.33%** | +49.5% | +4.19 | 7 |
| main | 002827.SZ | 2 | 27.03% *(tied)* | 37.19% | +56.5% | +0.79 | 7 |
| main | 600206.SS | 3 | 27.03% *(tied)* | **45.33%** | +36.1% | −0.79 | 9 |
| chinext | 300363.SZ | 1 | 25.53% *(tied)* | 13.04% | +31.5% | +3.31 | 7 |
| chinext | 301047.SZ | 1 | 25.53% *(tied)* | 13.04% | +59.8% | +3.02 | 7 |
| chinext | 300209.SZ | **0** | 13.24% | 0.29% | +33.3% | +1.96 | 10 |
| chinext | 300489.SZ | **0** | 13.24% | 0.29% | +70.8% | +2.20 | 8 |
| chinext | 300620.SZ | **0** | 13.24% | 0.29% | +40.3% | +1.72 | 10 |

The three ChiNext N=0 names are the onset lane doing its actual job — flagging names that have **not
yet** limit-upped, at 46× the ladder's number. **Apply the measured haircut before believing any of
it**: ChiNext's B1 quotes run 4.03–4.87× hot in the top-K buckets, so 13.24% reads as roughly 3%.

### The nightly hook point — PROPOSAL ONLY, nothing wired

- **Workflow:** `.github/workflows/asia-close.yml`, immediately after the
  **"CN Pick Lab — fire books + grade + render (CNPL-R8 asia lane, ≤2 min)"** step.
- **Why there:** asia-close is the CN lane and the sole owner of the CN data plane —
  `data/china_stocks_raw` is written by its *collect China/HK data* step
  (`collectors/china_stock_raw.py` via `scripts/collect.py`) **before** the builder bands, so
  tonight's feature bar is on disk by the time the Pick Lab step runs. The CN Pick Lab is the exact
  structural analogue (a fire book plus a grade pass over an append-only jsonl), so the ledger
  inherits a proven pattern instead of inventing one.
- **Gate:** reuse the `CN_LANE=asia` environment gate. The asia lane is the ONLY lane permitted to
  advance the ledger; render and intraday lanes leave `CN_LANE` unset and the writer must refuse.
  That is the house law "nightly is the sole advancer of forward ledgers", made executable.
- **Commit path — a real Wave-2 decision, flagged not taken.** The existing *commit engine outputs*
  step git-adds `data/` and `site/`. It does **not** add `research/`. Wave 2 must either relocate
  the ledger to `data/cn_limit_onset/` (recommended — it is an operational ledger, not a research
  document) or extend the add.
- **Never-break contract:** wrap in the same `exit 0` + `::error` annotation shape the Pick Lab
  steps use, so a ledger failure never reds the CN lane.
- **Budget:** one panel build ~9s plus inference — the whole instrument runs in ~20s, comfortably
  inside the asia lane.

---

## WHAT THIS DOES *NOT* ESTABLISH

- **No significance claim.** Limit-ups cluster hard in time and cross-section, so the Wilson
  intervals on the reliability bins are understated as a test of the *model*. The evidence offered
  is skill and calibration on a frozen holdout plus per-year stability — never a p-value.
- **Lift is not probability.** The best top-K bucket on the main board realizes 16.6%: the modelled
  event still does not happen ~83% of the time where the model is most confident, and ~95% of the
  time in the top decile of the population.
- **Calibration is IN-UNIVERSE.** These probabilities are calibrated for the curated ~1,836-name
  store, not for the A-share market, and the 打板 game is denser in the names the store omits.
- **Nothing here is about FILLABILITY.** P is for a limit-up *close*; a name that gaps straight to
  the limit at the open is unfillable and still scores as a hit. That is the rider lane's question
  and it is deliberately not smuggled in.
- **Nothing here is about CONTINUATION.** N is an input, not the subject. `P(next board | already N
  boards)` empirics belong to lane L1.
- **A negative Brier skill is not "the features are worthless".** It is "this construction, with
  this calibration step, on this split, does not beat a four-number lookup on this scoring rule".
  Under THE ORE LAW that closes one construction, not the search space.
- **Survivorship and the current-membership sector map are unfixed** with the stores we hold. Both
  are stated rather than patched.
- **Nothing is promoted.** The gauntlet is a promotion gate; this is display tier and no key is
  being escalated.

---

## ORE LEDGER (constructions NOT tested — the map, not the graveyard)

| # | Ore | Status | Why it could matter | Next construction |
|---|---|---|---|---|
| 1 | **Regime / market-state features** (breadth, index trend, market-wide limit-up level, vol state) | **UNTESTED — lane L2 owns the instruments** | The single highest-value item. The holdout's own base rate swings 0.675%→1.908% year to year, and the *measured* cause of B1's failure is a calibration slice 1.30×/2.06× off the holdout's regime. A model that cannot see the regime spends its capacity re-learning it. | Wave-2 merge of L2's instruments as B1 covariates **and** as calibration-map conditioners |
| 2 | **Regime-robust calibration** (time-series-CV isotonic across the whole fit window, or Platt/beta on the same slice) | **UNTESTED — and NOT attempted after seeing the holdout, by discipline** | A single contiguous calibration slice imports that slice's base rate as a frozen level error. This is the direct fix for the whole ChiNext result and most of main's bend. | Pre-register the calibration design, re-run once |
| 3 | **STAR-era re-split** | **UNTESTED — the THIN-SKIP is a split artifact as much as a rarity one** | STAR has 612 holdout positives and 40 fit-core ones purely because the global date split predates its 2019 listing. ChiNext already gets an era split; STAR has the same claim. | Same era treatment as ChiNext, pre-registered before running |
| 4 | **Gradient boosting / learned interactions** | UNTESTED — deliberately | B2 is a 2-way interaction *by hand* and it beats B1 on main Brier skill and resolution. That is direct evidence the linear form leaves structure on the table. | Only after the linear baseline has a graded forward record — a boosted tree on a 1% event with no forward ledger is unauditable |
| 5 | **f3 × f4 crosses** (run-up conditioned on cohort heat) | UNTESTED | The practitioner reading is that a run-up *inside a hot sector* is a different object from a lone run-up. The linear model cannot express it, and B2's f3×f6 cross already outperforms. | Explicit cross terms, pre-registered, same frozen split |
| 6 | **Non-linear f3** (splines / decile dummies instead of a winsorised linear term) | **UNTESTED — and newly implicated** | v0's f3 decile curve is monotone but sharply convex; a linear-in-logit term on a 1/99-winsorised f3 cannot represent it, and f3's coefficient sign flip (#9) may be partly a functional-form artifact rather than pure collinearity. | Decile dummies for f3, which also decouples the flip from the winsorisation |
| 7 | **Per-name effects** (shrunk per-name intercept) | UNTESTED — v0 measured that per-name estimation is starved at this base rate | Onset propensity is plainly not uniform across names. | Partial pooling, never per-name fits |
| 8 | **Continuation-side model** | OUT OF SCOPE — lane L1 | The ladder is the strongest single conditioner in the data and appears here only as a benchmark input. | L1's results merge as a sibling model, never a pooled one |
| 9 | **zt_pool-universe scoring** (the ~1,256 limit-up names the store lacks) | UNTESTED — blocked on coverage, not method | The omitted names are where the game is densest; every number here may be a large-cap special case. | Extend `china_stocks_raw` coverage, re-fit, compare |
| 10 | **Near-limit as a SOFT label** | UNTESTED | The binary target discards the difference between a miss at +2% and a miss at +9.8% — most of the information in a near-miss. | Ordinal or two-stage target; keep grading the binary in parallel so the ledger stays comparable |
| 11 | **Longer horizons H > 1** (a board within 3 / 5 sessions) | UNTESTED | H=1 is the hardest possible framing and may be why the absolute probabilities stay small. | Same features, H ∈ {2,3,5}; overlapping windows worsen the dependence — state it before measuring |
| 12 | **Isotonic tail flattening** | **MEASURED HERE** | The live book's head is 6 names at one identical value, and the top reliability bin under-predicts by 0.66pp. The model cannot order the part of the book a desk cares most about. | Monotone spline or a parametric tail above the last knot; or quote B0 above N≥3 |
| 13 | **Complete-case vs sector-imputation** | UNTESTED | 305,372 rows drop for a null f4 — a *universe* property, so the modelled set is mildly non-random. | A sector-missing indicator + f4 set to the marginal, compared against complete-case |

---

## DEVIATIONS AND CORRECTIONS

1. **The headline result is a NULL and is reported as one.** B1 misses the pre-registered bar on
   both boards. Nothing was re-split, re-fit, re-calibrated or re-scored after that was known — the
   fixes are in the ORE LEDGER, not in the numbers above.
2. **Three reporting diagnostics were added that the brief did not name**: AUC, the exact Murphy
   decomposition, and the per-slice base rates. All three read the *same single holdout pass*; none
   is a model change. They exist because "Brier skill is negative" and "the model cannot rank" are
   different claims and the brief's metric set could not separate them.
3. **`predict_date_source` was added to the ledger schema** (one field beyond the specified schema).
   Without it a grader cannot tell an observed next bar from the live rows' calendar estimate, and a
   silent holiday-shifted `predict_date` would corrupt the grade.
4. **ChiNext uses its own era split** (2024-10-25), not the global one — v0's era control, adopted
   because pooling across the 2020-08-24 band change models two different games.
5. **Complete-case, not imputed** — 91.4% of usable rows. A joint model needs all six columns on the
   same row; v0's per-feature decile tables did not.
6. **Reliability binning falls back to distinct values** when a model has ≤10 of them. Without this,
   B0's four numbers qcut into a single bin and the benchmark appears to have no resolution at all.
7. **The seed file is written WHOLE**, so re-running is idempotent. Append-only semantics begin with
   the Wave-2 nightly wiring.
8. **STAR modelled nothing.** Printed THIN-SKIP with its measured counts rather than fitted at a
   lower standard.
9. **Side finding, flagged not acted on — a stale prose block in v0's committed JSON.**
   `LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json` `definitions.limit_up_close` reads *"PRIMARY (strict):
   close >= round(prev_close*(1+w), 2)"*, and `definitions.why_strict_is_primary` argues for it. Both
   survive from **before** v0's own mid-build reversal and contradict v0's code (which computes the
   tolerant test as the primary `limit_up` column), v0's own
   `definition_adjudication.verdict` (*"the charter's tolerance is adopted as PRIMARY"*), and v0's MD
   receipt (§DEVIATIONS #1, which records the reversal). **The MD is right and the JSON's prose block
   is wrong.** A downstream consumer reading the JSON's definitions at face value would build against
   the wrong primary definition. This file uses the tolerant/PRIMARY rule and reproduces v0's
   published numbers exactly, which is the independent confirmation. Belongs to PR #4999's lane.

---

## REPRODUCE

```
cd <repo root>
TZ=UTC python3 research/cn_prophet_audit/onset_calibration_v1.py
```

Deterministic — verified by re-running and diffing: the ledger is byte-identical modulo
`stamped_at_utc`, and the JSON modulo `generated_utc` / `runtime_sec`. Runtime ~20s. sklearn 1.9.0
was used (`LogisticRegression(C=inf, lbfgs)` unpenalised, `IsotonicRegression`); the file carries a
numpy IRLS + PAVA fallback and prints which path ran. Writes
`ONSET_CALIBRATION_V1_2026-08-08.json` (every cell above plus full bucket tables, coefficients,
scaler parameters, B2 cells, and the v0 parity gate) and `onset_forward_ledger.jsonl`.
