# CONTINUATION-SIDE REGIME MERGE v1 — CN LIMIT-MOVE ALPHA, Wave 3 lane W3-B

**Tier: DISPLAY / AUDIT. Measurement only.** Nothing here promotes, ranks, sizes, gates or
admits. No LLM is involved at any point. The gauntlet applies at authority promotion, which
this artifact does not seek.

Instrument `research/cn_prophet_audit/continuation_regime_merge_v1.py` ·
frozen numbers `CONTINUATION_REGIME_MERGE_V1_2026-08-09.json` (this MD is hand-written from
that file and is not emitted by the script) ·
`TZ=UTC python3 research/cn_prophet_audit/continuation_regime_merge_v1.py`, ~20 s.

> **AMENDED AFTER ADVERSARIAL REVIEW (7 amendments, §11).** The review found the primary null
> reproduced exactly and untouched, and **every defect in the AFFIRMATIVE framing**: a
> one-draw permutation control quoted to two decimals, IID error bands on the only
> unclustered quantities in the receipt, a lookahead predicate that could not fail, and three
> prose claims contradicted by this file's own tables. All are fixed below and the affirmative
> section has been requalified — **direction survives, magnitude largely does not.**

---

## 0. THE VERDICT IN ONE PARAGRAPH

W2-A named this the program's largest measured remaining effect: the regime dial is strongest
on the N=1 rung, and the N=1 rung is where L1's continuation rider lives. The merge is now
measured, and **the answer is a clean null with an unusually sharp shape**. Across 78
pre-registered (board × rung × dial-tercile × exit-rule) cells, **0 clear the decision bar**.
Restricted to the 21 cells in families that clear the pre-registered 150-fit-core-positive
floor, **the maximum date-clustered t in either window is −0.17** — not one non-thin cell is
even weakly positive. **All 21 are net-negative in BOTH windows, and 14 of 21 are
date-clustered-significant at t ≤ −2 in both.** The declared headline cell (main · N=1 ·
top tercile · E3) prints **−0.601 % date-equal-weighted net, dc-t −3.18 in fit** and
**−0.961 %, dc-t −2.54 in holdout**.

Underneath the null, the probability structure the dial promises is REAL and reproduces:
P(next board) on main N=1 runs 12.31 % → 14.49 % → **21.81 %** cold→mid→hot in fit and
13.56 % → 15.20 % → **22.33 %** in holdout, and that hot-minus-cold spread survives both an
era-preserving permutation null and session clustering in **both** windows (fit +9.50 pp,
p 0.015, clustered t 2.61; holdout +8.76 pp, p 0.010, clustered t 2.62). The auction takes it
back at the door: only **25.3 %** of the holdout spread survives conditioning on a buyable
open, and **entry availability falls monotonically as the dial rises on 6 of 6 main
(rung × window) cells — an ordering a shuffled dial reproduces essentially never under either
null (0/200 global, 1/200 era-preserving; null mean 3.3–5.0 violations against the true 0).**
**The dial is a correct probability instrument pointed at a wrong-signed payoff.** Wave 1's
anti-monotone finding, reproduced on the regime axis.

**What is NOT supported is the SIZE of the availability effect.** Only **3 of 12** affirmative
magnitudes clear both the era-preserving null and session clustering. The first draft of this
receipt led with a −16.74 pp holdout availability spread; against an era-preserving
permutation null that spread has p ≈ 0.07 and a session-clustered t of −1.64, so **most of it
is era composition and thin-holdout noise, not regime.** It is reported here as
direction-only. The ordering and the probability spread are the affirmative findings; every
magnitude is banded.

The honest prior stated in the pre-registration — *the dial is public information, so the
likely outcome is that the auction prices it* — is what happened. This was written down before
the first number was computed.

---

## 1. PRE-REGISTRATION (fixed before the first run; §PREREGISTRATION in the JSON)

**Primary question.** Does any (board × ladder-rung × dial-tercile) cell make the FILLABLE
next-open rider net-positive with a date-clustered t ≥ 2 in BOTH the fit and the holdout window?

**Headline cell, declared in advance:** main-board · N=1 rung · top dial tercile (`T3_hot`) ·
E3 (the unconditional T+4 time stop — the only exit rule whose horizon does not depend on the
outcome, so the only one that compares like-for-like across strata and cohorts).

**Decision bar.** A cell CLEARS only if its date-equal-weighted NET expectancy (after a 15 bp
round trip) is positive AND its date-clustered t is ≥ 2.0, **in both windows**, with n_dates ≥
30 in each, inside a family carrying ≥ 150 fit-core continuation positives. Anything else is a
null **for that construction and for no other**.

**Secondary (a).** Does W2-B's broken-board T+1-open lead over the sealed cohort concentrate in
dial-high states?
**Secondary (b).** Does the dial level shift the FILLABLE SHARE itself — is the auction pricing
the regime by rationing access?

**Honest prior, verbatim from the script header:** *"The dial is PUBLIC INFORMATION… THE LIKELY
OUTCOME OF THIS LANE IS THAT THE AUCTION PRICES THE REGIME TOO. A clean, well-measured null IS
the deliverable. Nothing here is tortured until a cell turns positive: the t-census across ALL
cells is the headline statement, not the best surviving cell."*

---

## 2. GATES — all four PASS before any finding is read

| Gate | Result |
|---|---|
| **v0 ladder parity** | PASS — every published Stage-2 cell reproduced exactly on n and to published precision on rate; unconditional next-bar rates 1.27 / 1.14 / 0.32 % (main/chinext/star) reproduce v0 exactly |
| **L1 panel + published book parity** | PASS — L1's `process_ticker` is RUN here, not paraphrased. 60,298 limit-up days · 59,657 with a usable next bar · 51,486 fillable entries, all exact; all six published main book cells (fit/holdout × E1/E2/E3) reproduce to ≤ 0.0005 pp |
| **Splits** | PASS — W2-A's frozen boundaries re-derived from this lane's own panel date set land exactly: global 2021-11-26 (2,646 / 1,135), chinext 2024-10-25 (1,007 / 433), star 2024-07-01 (1,190 / 510) — every published count reproduced |
| **Lookahead (G1–G4)** | PASS on every leg, at **full coverage** (amendment A6) — G1 join alignment over **9,274** board-sessions and G3 backward-window arithmetic over **9,277**, 0 mismatches, plus an independent re-derivation of the dial from THIS lane's panel (max abs rate diff and max abs pair-count diff both 0) |

**A6.** The first draft sampled G1 over the last 60 sessions per board (177 of 9,277) and G3
over the last 200 (600 of 9,277) while claiming the legs "PASSED" outright. Both now run over
every session; both still pass. G2 (does the check have power?) is printed per board rather
than pooled, because main's dial moves nearly every session while chinext and star print long
runs of the same value.

### Two disclosed amendments to L1's book, both with measured footprints

**(1) Closure-tolerant forward chain.** L1 and W3-A reuse v0's 10-calendar-day PAIR rule as the
forward-chain STEP rule, so a CNY or National-Day closure truncates every open position
market-wide at once — W3-A receipted that as the root cause of its first-draft flagship
illusion. Here the step is admissible if the calendar gap is ≤ 10 days **or no market session
fell between the two bars**, read off the exchange calendar. Footprint: **1,385 steps admitted
only because the exchange was shut** (longest gap 11 days, CNY 2020), 3 steps refused as
name-specific suspensions. Against L1's book: 154,458 trades matched one-for-one on
(date, ticker, rule), entry price identical on all of them, **812 returns moved (0.53 %) — and
all 812 are trades L1 force-closed at a mark-to-market close that this lane carries to a real
open.** The T→T+1 PAIRING that defines an event is left at the 10-day rule untouched, which is
why the v0 parity gate still reproduces exactly.

**(2) Complete-window book.** Trades whose chain cannot reach a real exit bar are EXCLUDED
from the priced book and reported in their own block (W3-A amendment A1, adopted here from the
first run rather than after review): **1,955 sealed + 1,639 broken = 3,594 total.** Only the
sealed count is commensurable with the L1 comparison above; the first draft printed the
both-cohort total inside the sealed-only parity block, inviting the wrong denominator
(amendment A7).

---

## 3. THE DIAL, ITS CUTS, AND WHERE THEY ARE MEANINGFUL

Dial = `i5_realized_continuation_ma5` at the FEATURE date T, per board, from
`board_ecology_series_v1.parquet` **as committed** (never recomputed — that would fork the
definition under test — but independently re-derived as gate G4). Terciles cut on the board's
own **fit-window SESSIONS** (dates, not rows), applied unchanged to the holdout.

Main edges: **0.1648 / 0.2883**. Two masses are printed because they are different objects:

| main | T1_cold | T2_mid | T3_hot | UNKNOWN |
|---|---|---|---|---|
| fit, % of SESSIONS | 33.17 | 33.21 | 33.21 | 0.42 |
| holdout, % of SESSIONS | 37.49 | 48.03 | **14.49** | 0.00 |
| fit, % of board-day ROWS | 20.23 | 34.54 | 45.14 | 0.09 |
| holdout, % of board-day ROWS | 29.96 | 49.80 | 20.25 | 0.00 |

The holdout session masses are the **realised** out-of-sample masses of a frozen cut: the hot
tercile shrinks 33.2 % → 14.5 %. That is W3-A's lesson printed rather than assumed — a frozen
quantile cut is not its nominal quantile out of sample, and the cause is distribution shift.
The ROW skew toward hot is separate and expected: a hot session simply carries more board-days.

**ChiNext and STAR are coverage nulls and are printed as such.** Their fit-window `T1_cold`
stratum is **EMPTY** — those boards sit at exactly 0.0 on a third to 90 % of sessions (no
continuation pairs at all), so the lowest quantile edge lands on the point mass and every zero
session sorts upward. Dial coverage: main 99.71 % of sessions non-null, chinext 66.67 %, star
20.29 %. No chinext or STAR family clears the fit-core floor in any case.

**Cell-family floor: 150 fit-core continuation positives, W2-A's number and W2-A's fit_core
slice, NOT lowered after seeing data** (W2-A held this exact line against STAR at 137). Seven
families clear it, all on main:

| family | fit-core board-days | fit-core positives |
|---|---|---|
| main · N1 · T1_cold | 4,147 | 489 |
| main · N1 · T2_mid | 5,931 | 833 |
| main · N1 · T3_hot | 8,284 | 1,874 |
| main · N2 · T2_mid | 807 | 298 |
| main · N2 · T3_hot | 1,962 | 946 |
| main · N3+ · T2_mid | 586 | 356 |
| main · N3+ · T3_hot | 2,687 | 1,689 |

---

## 4. PRIMARY RESULT

### 4.1 The headline cell — main · N=1 · T3_hot · E3

| | n | n_dates | date-eq net | **dc-t** | per-trade t | median | win rate |
|---|---|---|---|---|---|---|---|
| fit | 8,522 | 832 | **−0.601 %** | **−3.18** | −2.17 | −0.652 % | 45.93 % |
| holdout | 1,940 | 163 | **−0.961 %** | **−2.54** | −4.55 | −1.444 % | 40.98 % |

Negative, significantly so, in both windows. Roll rate 0.38 / 0.41 %.

### 4.2 The t-census — the headline statement

| census | cells | max fit dc-t | max holdout dc-t | ≥ bar in fit | ≥ bar in holdout | ≥ bar in BOTH |
|---|---|---|---|---|---|---|
| **non-thin families only** | **21** | **−0.26** | **−0.17** | 0 | 0 | **0** |
| all cells (incl. THIN-SKIP) | 78 | 2.07 | 1.10 | 1 | 0 | **0** |

**Cells clearing the FULL decision bar: 0.** Read the non-thin census: the all-cells maximum of
2.07 belongs to a star · N3+ · UNKNOWN cell in a family declared THIN-SKIP before the data was
seen, where a two-session cell can print any t at all. It is printed beside the real number so
the skip is auditable rather than invisible.

**The negative-side census** — because "no edge found" and "significantly negative in both
windows" are different findings:

- non-thin cells: **21**
- net-negative in BOTH windows: **21 / 21**
- date-clustered t ≤ −2.0 in BOTH windows: **14 / 21**

### 4.3 Every non-thin cell (date-eq-weighted NET %, date-clustered t)

| rung | tercile | rule | fit net | fit t | holdout net | holdout t |
|---|---|---|---|---|---|---|
| N1 | T1_cold | E1 | −0.437 | −3.75 | −0.588 | −3.76 |
| N1 | T1_cold | E2 | −0.531 | −3.78 | −0.690 | −3.69 |
| N1 | T1_cold | E3 | −0.389 | −2.25 | −0.578 | −2.73 |
| N1 | T2_mid | E1 | −0.707 | −5.91 | −0.635 | −4.14 |
| N1 | T2_mid | E2 | −0.772 | −5.22 | −0.706 | −3.98 |
| N1 | T2_mid | E3 | −0.647 | −3.71 | −0.750 | −3.55 |
| **N1** | **T3_hot** | **E1** | −0.757 | −5.75 | −1.045 | −3.93 |
| **N1** | **T3_hot** | **E2** | −0.982 | −6.61 | −1.360 | −4.72 |
| **N1** | **T3_hot** | **E3** | **−0.601** | **−3.18** | **−0.961** | **−2.54** |
| N2 | T2_mid | E1 | −0.688 | −1.90 | −1.155 | −2.92 |
| N2 | T2_mid | E2 | −0.877 | −2.13 | −1.166 | −2.41 |
| N2 | T2_mid | E3 | −0.516 | −1.06 | −0.841 | −1.57 |
| N2 | T3_hot | E1 | −1.517 | −4.55 | −2.866 | −3.90 |
| N2 | T3_hot | E2 | −1.981 | −5.37 | −3.491 | −4.81 |
| N2 | T3_hot | E3 | −1.757 | −3.67 | −3.369 | −3.62 |
| N3+ | T2_mid | E1 | −1.152 | −2.19 | −1.287 | −2.07 |
| N3+ | T2_mid | E2 | −1.891 | −3.44 | −1.247 | −1.73 |
| N3+ | T2_mid | E3 | −0.191 | −0.26 | −0.137 | −0.17 |
| N3+ | T3_hot | E1 | −0.826 | −1.49 | −3.535 | −3.70 |
| N3+ | T3_hot | E2 | −0.796 | −1.26 | −3.332 | −2.72 |
| N3+ | T3_hot | E3 | −0.759 | −1.33 | −2.668 | −1.87 |

Per-trade t travels beside every clustered t in the JSON. **Amendment A5:** the first draft
claimed it was "uniformly the more flattering of the two" — false, and contradicted by this
table. Per-trade t is in fact the **more negative** of the two in **32 of the 42** non-thin
rows, including the headline holdout cell (dc-t −2.54 vs per-trade −4.55). It is nonetheless
never quoted alone, for the reason that has nothing to do with which direction it errs in: it
treats a theme wave's dozens of same-session trades as independent observations, so its
magnitude is not interpretable in either direction.

### 4.4 THE STRUCTURAL FINDING — the dial orders probability UP and payoff DOWN

main · N=1, P(next board) with Wilson 95 %, and its fillable-conditional twin:

| window | | T1_cold | T2_mid | T3_hot |
|---|---|---|---|---|
| fit | board-days | 5,907 | 9,056 | 9,565 |
| fit | **P(next board)** | 12.31 % [11.49, 13.17] | 14.49 % [13.78, 15.23] | **21.81 % [20.99, 22.65]** |
| fit | P given a FILLABLE open | 9.27 % [8.54, 10.06] | 10.51 % [9.88, 11.18] | 15.72 % [14.97, 16.50] |
| fit | fillability tax | 28.20 % | 31.40 % | 34.52 % |
| holdout | board-days | 4,438 | 6,847 | 2,450 |
| holdout | **P(next board)** | 13.56 % [12.59, 14.60] | 15.20 % [14.37, 16.07] | **22.33 % [20.72, 24.02]** |
| holdout | P given a FILLABLE open | 11.19 % [10.28, 12.18] | 12.15 % [11.38, 12.97] | 13.41 % [11.96, 14.99] |
| holdout | fillability tax | 20.60 % | 23.63 % | **52.29 %** |

- P(next board) **rises with the dial in 2 of 2** (window) cells. This is the affirmative claim
  in the receipt with the strongest support: the hot-minus-cold spread is **+9.50 pp in fit
  (era-preserving permutation p 0.015, session-clustered t 2.61)** and **+8.76 pp in holdout
  (p 0.010, clustered t 2.62)** — it clears both nulls and clustering in both windows. The
  dial's probability claim is confirmed on the continuation side.
- Conditional on a buyable open the spread is **+6.45 pp fit / +2.22 pp holdout** — **67.9 %
  survives in fit, 25.3 % in holdout**.
- E3 net expectancy cold→mid→hot: fit −0.389 / −0.647 / −0.601 (not strictly monotone),
  holdout −0.578 / −0.750 / **−0.961** (monotone down). Expectancy falls as the dial rises in
  1 of 2 windows and is negative in all six.

Higher rungs are worse, not better: main N2 · T3_hot · E3 prints −1.757 % fit / **−3.369 %
holdout** (dc-t −3.67 / −3.62), and N3+ · T3_hot · E1 −3.535 % holdout. The most impressive
published ladder cells are the least buyable and the most expensive.

### 4.5 Era tables (yearly, mandatory)

The headline family (main · N=1 · T3_hot · E3) is net-positive in **4 of 16 years** — 2014,
2015, 2023, 2025 — and negative in the other 12, including −2.287 % (2018), −2.161 % (2022),
−2.039 % (2024) and −2.518 % (2026 partial). Across all 21 non-thin cells the years-positive
share runs 6.25 % – 43.75 %; **no non-thin cell is positive in even half its years.** Full
per-year table in `era_tables.headline_family_by_year`, sign summary for every cell in
`era_tables.sign_summary_all_cells`.

---

## 5. SECONDARY (a) — the broken-board lead by dial state

Sealed = closed at the tolerant limit at T. Broken = TOUCHED the limit intraday at T and closed
below it (35,901 board-days), derived from THIS panel on the tolerant basis so both arms share
one definition — the house tape's `lianban_count` is hardcoded 0 on failed_up_seal rows and
strict/tolerant overlap is only 42.7 % of the union, so a tape-sourced cohort would mix bases
with the arm it is compared to. Matched on PRIOR rung, same board, same tercile, same rule,
same split, and **paired on the session**. 167 cells, 78 above the 30-paired-session floor.

**The lead is real and reproduces.** main · prior-rung P0 · E3:

| window | T3_hot lead | t | (broken net / sealed net) | T1_cold lead | t | hot − cold |
|---|---|---|---|---|---|---|
| fit | +0.521 pp | 2.84 | (−0.031 % / −0.552 %) | +0.447 pp | 2.36 | **+0.074 pp** |
| holdout | +0.999 pp | 2.70 | (+0.030 % / −0.969 %) | +0.365 pp | 1.49 | **+0.634 pp** |

**Answer: yes at P0 on E3 only, and the lead is a smaller loss, not a gain.** **Amendment A5:**
the first draft claimed the hot−cold difference was "the same sign in both windows on all three
exit rules" and then contradicted itself in its own parenthetical. The correct statement is
that **E3 is the only exit rule whose hot−cold difference is sign-stable across windows**
(+0.074 / +0.634); **E1 (−0.064 / +0.649) and E2 (−0.015 / +0.855) both flip sign** between fit
and holdout. The concentration is unambiguous only in the holdout, and only E3 carries it in
both. The broken arm's own absolute date-clustered net in the hot cell is **−0.031 % (fit) and
+0.030 % (holdout)**: essentially zero. Every number in this section is RELATIVE, and both
arms' absolute levels travel beside every lead precisely so it cannot be misread.

**The broken arm's own book, tested against the same decision bar** (descriptive, NOT
pre-registered — reported because a receipt that says "the broken arm is net-positive in 40
cells" and never says whether any survives a two-window t bar is burying its own most
interesting number): maximum dc-t in either window **2.65**, **0 cells clear in both windows**.
Carrying the full multiplicity of the cell grid with no pre-registered hypothesis behind any
single cell, this is not a finding. It is the number a reader would otherwise have to guess at.

---

## 6. SECONDARY (b) — the ORDERING is the finding; the magnitudes are not

**Entry availability falls monotonically as the dial rises on 6 of 6 main (rung × window)
cells; the mean open gap rises monotonically with it on 5 of 6.**

| rung | window | availability cold → mid → hot | mean gap cold → mid → hot |
|---|---|---|---|
| N1 | fit | 95.33 → 94.55 → 90.85 % | +1.60 → +1.83 → +2.41 % |
| N1 | holdout | 96.21 → 95.55 → 79.47 % | +1.56 → +1.76 → +3.33 % |
| N2 | fit | 81.22 → 77.23 → 72.86 % | +3.09 → +3.52 → +4.60 % |
| N2 | holdout | 88.02 → 84.50 → 74.87 % | +2.77 → +2.72 → +3.00 % ‡ |
| N3+ | fit | 63.91 → 52.92 → 44.04 % | +4.66 → +5.51 → +6.29 % |
| N3+ | holdout | 77.02 → 74.46 → 60.93 % | +3.52 → +3.95 → +4.31 % |

‡ the one non-monotone gap row (2.772 → 2.717 → 3.000).

**THE ROBUST RESULT IS THE ORDERING, and it is strong.** A dial shuffled across sessions
reproduces a clean 6/6 monotone availability ordering essentially never: **0 of 200** draws
under the global null (null mean 5.04 violations) and **1 of 200** under the era-preserving
within-year null (null mean 3.33 violations), against the true dial's **zero** violations —
one-sided permutation p **0.005 / 0.010**. Both orderings say the same thing from opposite
sides: **the hotter the regime, the more of the next-day supply is locked away at the open, and
the more you pay for what is left.** That is the mechanism behind §4 — the paper edge is
auctioned away before a single return is measured.

### The MAGNITUDES are a different matter (amendments A1, A2, A4)

The first draft of this receipt led with "the hot-minus-cold availability gap is −4.48 pp in fit
and **−16.74 pp in holdout**". Under proper inference that headline does not hold. Only **3 of
12** affirmative magnitudes clear both the era-preserving permutation null (p ≤ 0.05) and
session clustering (|t| ≥ 2):

| statistic | rung | window | true | global-null p | **era-preserving p** | **clustered t** | verdict |
|---|---|---|---|---|---|---|---|
| availability hot−cold | N1 | fit | −4.48 pp | 0.005 | **0.005** | **−4.57** | **SUPPORTED** |
| P(next board) hot−cold | N1 | fit | +9.50 pp | 0.005 | **0.015** | **2.61** | **SUPPORTED** |
| P(next board) hot−cold | N1 | holdout | +8.76 pp | 0.005 | **0.010** | **2.62** | **SUPPORTED** |
| availability hot−cold | N1 | holdout | **−16.74 pp** | 0.005 | 0.070 | −1.64 | direction-only |
| availability hot−cold | N2 | fit | −8.36 pp | 0.005 | 0.144 | −3.30 | direction-only |
| availability hot−cold | N2 | holdout | −13.15 pp | 0.005 | 0.100 | −1.75 | direction-only |
| availability hot−cold | N3+ | fit | −19.87 pp | 0.005 | 0.085 | −3.00 | direction-only |
| availability hot−cold | N3+ | holdout | −16.09 pp | 0.005 | 0.060 | −2.97 | direction-only |
| P(next board) hot−cold | N2 | fit | +18.41 pp | 0.055 | 0.114 | 2.34 | direction-only |
| P(next board) hot−cold | N2 | holdout | −1.40 pp | 0.816 | 0.871 | −0.17 | direction-only |
| P(next board) hot−cold | N3+ | fit | +9.14 pp | 0.393 | 0.159 | 1.40 | direction-only |
| P(next board) hot−cold | N3+ | holdout | +0.84 pp | 0.906 | 0.876 | 0.14 | direction-only |

**Read the era-preserving column, not the global one.** Global shuffling destroys the era
structure as well as the date correspondence, so it flatters any statistic that is partly era
composition — which is why almost every row shows p = 0.005 there. The within-year block
permutation keeps each year's dial distribution and each stratum's year composition intact, so
only within-year signal survives it. On that yardstick **the flagship −16.74 pp spread is
p ≈ 0.07 with a session-clustered t of −1.64: most of it is era composition and thin-holdout
noise, not regime.**

**A4 — why the clustered column matters so much here.** Availability, the fillability tax and
the mean gap were the only affirmative quantities in the receipt not clustered; they carried
IID Wilson bands while the permutation null for the same statistic has an SD of 5–8 pp. The
correction is large. main · N=1 · T3_hot holdout availability:

| basis | interval | SE |
|---|---|---|
| IID Wilson 95 % (first draft) | [77.82, 81.02] | ~0.8 pp |
| **session cluster bootstrap 95 %** (1,000 resamples) | **[61.38, 93.23]** | **10.36 pp** |

A **6× understatement**, on the exact cell the flagship claim rested on. The dial is constant
within a date, so hot and cold sessions are **disjoint session sets** and the whole comparison
lives between sessions — no amount of within-date data narrows it.

---

## 7. CORRUPTION / CONTROL EXPERIMENTS (amendments A1, A3)

### 7.1 Permutation nulls — 200 draws, two schemes (replaces the one-draw arm)

The first draft's destruction control was **one** global permutation draw, and its headline —
"permuting the dial collapses the availability spread from 16.74 pp to 0.40 pp" — was a single
sample from a distribution quoted to two decimals. Redrawn 20 times by the review, the null was
−0.12 ± 5.06 pp: **0.40 pp was a coin flip, not a collapse.** It is replaced by 200 draws under
two schemes, publishing null mean, SD and a two-sided p for every affirmative statistic (§6
table, and `permutation_nulls` in the JSON).

| null | what it destroys | what it is good for |
|---|---|---|
| **global** | date correspondence **and** era structure | "is the date correspondence load-bearing at all" — nothing more |
| **within-year (era-preserving)** | date correspondence only, within each calendar year | the honest yardstick for a **magnitude** claim |

For the flagship, main · N=1 holdout availability spread: true −16.745 pp; global null
−0.85 ± 5.36 (p 0.005); **era-preserving null −4.18 ± 8.34 (p 0.070).**

### 7.2 Shifted-dial arms

| arm | non-thin max dc-t | cells clearing bar | availability spread \|hot−cold\| max | broken-lead max t |
|---|---|---|---|---|
| **true** | −0.17 | 0 | 16.74 pp | 6.14 |
| `corrupt_lag1` (dial +1 session) | −0.65 | 0 | 17.09 pp | 6.34 |
| `corrupt_lead1` (dial −1 session, real lookahead) | −0.10 | 0 | **19.25 pp** | **9.68** |

**A3 — the lookahead leg was a check that could not fail, and is now a positive control.** The
first draft's verdict keyed only on `max_date_clustered_t_non_thin_families` — a maximum over
21 uniformly *negative* cells, which a lookahead cannot push upward under any circumstances. Its
"PASS" therefore carried no information (the S7 class W3-A named: verify that a check can SEE
failure). The predicate now keys on the two series that actually move, and the arm is correctly
classed:

**i5 dated T+1 is computed FROM the T→T+1 continuation outcomes** — it literally counts how
many of T's boarders boarded again at T+1, which is the outcome this book trades. A T+1-dated
dial therefore **must strengthen** anything that can move, and it does: the availability spread
rises 16.74 → **19.25 pp** and the broken-lead max t rises 6.14 → **9.68**. That is the expected
benign signature, not a warning. **An arm that changed nothing would be the alarm**, because it
would mean the join is not reading dates at all. Verdict: the positive control fires on 2 of 2
movable series, and the true alignment is measurably distinguishable from it.

**Power caveat on the pre-registered lag-1 arm, stated rather than implied.** It is weak by
construction: the dial is a 5-session backward mean, so consecutive values share four of five
inputs and the measured lag-1 autocorrelation is **0.9255 (main), 0.9229 (chinext), 0.9179
(star)**. Attenuation, not death, is the honest expectation, and a surviving effect under lag-1
is not evidence of a broken index. The permutation nulls in §7.1 are the load-bearing control.

`max_date_clustered_t_all_cells` is not comparable across arms (re-cutting the dial re-populates
the THIN families, where a two-session cell prints any t at all).

---

## 8. COVERAGE RECEIPT AND STORE VINTAGE

- **Universe: the 1,842-name pre-expansion curated slice** (`data/china_stocks_raw`, HEAD
  `8ecfab906b9`), 1,836 tickers kept, 1 ST name skipped wholesale, 5 thin/unreadable.
  Survivors-only. **Vintage stamp verified in-run** (`vintage_matches_stamp: true`).
- **Healed event tape vintage: 71,463 rows** (`data/china_microstructure/limit_events.parquet`,
  L0 heal PR #5059) — sealed_up 31,906 · failed_up_seal 16,366 · sealed_down 13,315 ·
  failed_down_seal 9,876. This lane's own tolerant touch-and-fail count is 35,901; the two are
  printed side by side and deliberately NOT reconciled (different bases — see §5).
- **Vendor pool:** 1,770 names over 36 dates, **29.0 %** present in the raw store.
- **Trading calendar:** 3,786 sessions 2011-01-04 → 2026-08-07, cross-checked against the
  independent house daily tape (3,768 sessions, all 3,768 present in the ecology calendar).
- **Price basis:** the store is BACK-ADJUSTED, not nominal (L1's measurement). Adjustment
  preserves returns, so every gap, open-to-close and trade return here is unaffected.
- **Determinism:** two runs produce byte-identical JSON except **three** stamp fields —
  `generated_utc`, `runtime_sec`, and `coverage_receipt.store_vintage.checkout_head_sha`
  (amendment A5: the first draft said "two" and omitted the HEAD sha, which is stable across
  two runs in one checkout but moves with the checkout and is a stamp, not a finding). All
  randomness is seeded: permutation nulls at 20260811, session bootstrap at 20260810. Verified
  after the amendments.

**Falsifier F3 hangs over every number in this file.** A post-expansion re-run on the full
~5,400-name universe including ST and delisted names is not a refinement of these numbers — it
is a different universe, and the two receipts must be compared as such.

---

## 9. ORE LEDGER — what a null here closes, and what it does not

**A null closes ONLY the construction tested. "Not found yet" is not "does not exist."**

**Closed by this lane:** the fillable next-open rider under E1/E2/E3, conditioned on the i5
dial LEVEL in fit-window terciles, on the {1, 2, 3+} rungs, per board, in the two-window
pre-registered form above — and the broken-vs-sealed T+1-open lead as a dial-tercile-conditioned,
prior-rung-matched, session-paired quantity on the same three rules. Nothing else.

**Explicitly NOT closed — 15 untested neighbouring constructions** (full text in
`ore_ledger.untested_variants`):

| id | construction |
|---|---|
| OM1 | the dial as a CONTINUOUS covariate rather than a tercile cut |
| OM2 | the dial's SLOPE / derivative — is the regime warming or cooling (退潮 is a transition, not a state) |
| OM3 | CROSS-BOARD dial spillover — main's dial conditioning ChiNext entries and vice versa |
| OM4 | dial × ENTRY-FAMILY interactions: 回封 re-entries, 龙回头 pullbacks, 半路 half-way entries |
| OM5 | rungs N ≥ 2 as separate strata, and the N ≥ 4 ladder where published rates are highest |
| OM6 | the other five L2 ecology instruments (i1, i3, i4, i6) alone or in confluence with i5 |
| OM7 | within-series RANKS of the dial rather than its level (L2's own prescription for breadth) |
| OM8 | horizons beyond E1/E2/E3 — H ∈ {5, 10} and W3-A's peak/window targets, none dial-conditioned |
| OM9 | intraday entry moments — first-seal time, the 9:25 auction snapshot, pullback entries |
| OM10 | the dial computed on the VENDOR pool universe rather than the curated slice |
| OM11 | the full-universe (F3) re-run of everything here |
| OM12 | DOW / fermentation × dial crosses |
| OM13 | size / float / turnover normalisation of the cohort |
| OM14 | a dial-conditioned SIZING rule rather than a dial-conditioned ENTRY filter |
| OM15 | the ST cohort and its 5 % band |

**Defects inherited and disclosed, not repaired here:** the T→T+1 PAIRING rule remains v0's
10-calendar-day rule (only the forward EXIT chain was made closure-tolerant — repairing the
pairing rule would move every outcome denominator the v0 parity gate verifies as exact);
roll-cap exhaustion still prices an exit at a CLOSE, with the roll rate, mean extra loss and a
drop-those-trades sensitivity printed on every cell; slippage is not modelled.

**What this does NOT establish.** That the dial is useless — W2-A's 1.670× N=1 continuation
multiplier is a fact about PROBABILITY and is untouched here; §4.4 reproduces it. This lane asks
only whether that probability structure survives being paid for at the T+1 auction. It
establishes nothing about the full universe, nothing about intraday entries, and nothing
tradeable: no cell here ranks, sizes, gates or admits, and no forward-ledger row is emitted.

---

## 10. AMENDMENTS AFTER THE FIRST RUN (commissioned adversarial review)

The review reproduced the primary null exactly and found **every defect in the affirmative
framing**. All seven are applied above and recorded in `amendments_after_first_run` in the JSON.

| id | defect | fix | moved the verdict? |
|---|---|---|---|
| **A1** | destruction control was ONE permutation draw; "0.40 pp collapse" was a coin flip (review's 20 draws: −0.12 ± 5.06 pp) | 200 draws × 2 schemes (global + era-preserving), with null mean/SD and a two-sided p per statistic | **Yes — weakens this receipt's own flagship magnitude** |
| **A2** | receipt led with the −16.74 pp magnitude, the weakest number in it | leads with the ORDERING (robust under both nulls); every magnitude banded with its p | Yes, in framing |
| **A3** | lookahead predicate keyed on a max over 21 uniformly negative cells — a check that could not fail (S7 class) | keyed on the two movable series; arm re-classed as a POSITIVE control that must strengthen | No, but the old PASS was uninformative |
| **A4** | availability / tax / gap were the only unclustered quantities — IID Wilson ±~0.8–1.7 pp against a null SD of 5–8 pp | session cluster bootstrap (1,000 resamples) on every share, two-sample on every spread | **Yes — flagship clustered t is −1.64, not significant** |
| **A5** | three prose claims contradicted by this file's own tables + a false docstring | corrected in §4.3, §5, §8, and the script header | No |
| **A6** | G1/G3 sampled 177/600 of 9,277 sessions while claiming "PASS on every leg" | full coverage, 9,274 / 9,277 sessions; both still pass | No |
| **A7** | both-cohort incomplete count printed inside a sealed-only parity block | split 1,955 sealed / 1,639 broken / 3,594 total | No |

**Net effect: the null is unchanged and the affirmative section is smaller and better
supported.** Three magnitudes survive proper inference where the first draft asserted twelve;
the ordering result, which the first draft under-sold, is the finding that actually holds.

---

## 11. WHERE THIS LEAVES THE PROGRAM

Five entry families are now measured and priced at daily resolution on this universe —
next-open strength (L1), break-day weakness and pullback weakness (W2-B), window targets (W3-A),
and now **the regime-conditioned next-open rider**. All five are null for the taker, and the
probability structure is real, well-ordered and reproducible in every one of them. The
consistent mechanism, now measured from a fourth independent direction, is that **the T+1
auction prices whatever public conditioner you bring to it, and prices it by rationing the
fillable supply in exactly the states the conditioner likes** — an ordering that survives an
era-preserving permutation null at p ≈ 0.01, even though its size does not.

**A methodological note the program should keep.** Every defect the review found was on the
affirmative side of a receipt whose headline was a null. The null had a pre-registered decision
bar, date-clustered inference, a THIN floor fixed in advance and a two-window requirement; the
affirmative statements beside it had none of that until they were amended. **A receipt that
reports a null still has to hold its affirmative asides to the same standard** — an
era-preserving null for magnitudes, clustering at the real sampling unit, and controls whose
predicates can fail. That is now demonstrated in this file rather than asserted.

What remains, per the ore law and unchanged by this receipt: the intraday battery (W3-A's
foresight premium is its sized target), the F3 full-universe re-run, the forward ledger's live
grading, and the collectors.
