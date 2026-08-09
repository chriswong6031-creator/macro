# EARNINGS IGNITION — measurement receipt (ANTICIPATION §6.8(e))

**v0.1 — 2026-08-09 amendment. Supersedes v0 (2026-08-08).** Same window, same data
vintage, **corrected instrument**. Every headline that moved is named in §Before/after.

RESEARCH TIER. This receipt MEASURES. No gate, rank, size, lane, surface or config changes;
nothing here is a promotion and no cell below licenses one. Instrument (purely mechanical —
makes no LLM call of any kind, per A7): `research/prophet_us_audit/earnings_ignition_measurement.py`; data: `EARNINGS_IGNITION_MEASUREMENT_2026-08-08.json`.

## What v0.1 is

An adversarial re-read re-ran v0 and it **reproduced exactly** — same four cohorts
(726 / 9,497 / 720 / 6,048), same adverse tail (358), only last-digit rounding moving. The
receipt was not wrong about its data. It was wrong about its own arithmetic in four places,
and thin about its uncertainty in a fifth. Those are fixed here.

The **data vintage is deliberately frozen** at what v0 read (`site/signals` at
2026-08-08, EDGAR through 2026-07-02, prices through 2026-08-07, the same hardcoded
`today = 2026-08-08` cutoff), so every delta below is attributable to the **code** and not
to drift. The base is now pinned in the JSON (`base.repo_commit_at_run`
`e9f32de5b39`, plus store vintages) so no currency claim here can rot silently again —
which is exactly how v0's did.

| id | defect | effect |
|---|---|---|
| **F1** | the derived announcement window governed `reaction_pct` but was **dropped for the forward excess** — after-close reports anchored at close(T), *before* the print | H=5/H=10 excess swallowed the reaction jump on ~39% of report-anchored rows in **both** A and C |
| **F2** | cohort B (the control) counted markers in name-years the earnings store **never observed** | 1,462 of 6,048 control rows (24.2%) were coverage holes, not controls |
| **F4** | EDGAR **already rolls** `filing_date` past a post-close acceptance; v0 rolled a second time | 796 of 16,720 rows got their reaction one session late |
| **F3** | point estimates only — a null could not be told from an underpowered cell | every cell now carries SE + 95%; every contrast a t, an interval and an MDE |
| **F5/F7/F8/F10/F11/F12/F13** | fixed-offset ET honesty; a "nearest report" loop that took the **latest**; a no-op `TZ` line; no prereg disclosure; same-session confluences seated in the base rate; a self-restricted universe; **a test file CI never ran** | corrected or disclosed below |

## Verdict on the corrected instrument

**The hypothesis does not reproduce, the null is now stated with an interval, and the
adverse tail is not empty.** A fresh buy-confluence knowable in the five sessions before a
report does not predict a better reaction than the base rate: cohort A reaction mean
**+0.05%** (n=726, SE 0.19, 95% CI −0.32…+0.42) against cohort C's **+0.35%** (n=9,497,
SE 0.05).

The difference is **indistinguishable from zero**: diff **−0.31pp, SE 0.196, t = −1.56,
95% CI −0.69…+0.08**. v0 called this "the pre-report cohort reads slightly *worse*"; that
was a point estimate wearing a finding's clothes and it is withdrawn. **What can be said
is bounded, not absent:** this n could have detected a true difference of **0.55pp** 80% of
the time, so the honest reading is *no effect larger than about half a percentage point*.
An effect smaller than that is unmeasured here, not disproven.

Everything else that stood in v0 still stands, and the corrections **strengthen** it:

- **A's apparent forward-excess advantage was the anchoring bug.** v0 read A H=5 excess
  +0.32 vs C +0.21. Correctly anchored, that is **+0.13 vs +0.04** (diff +0.09, t = 0.55,
  MDE 0.45) — indistinguishable. A's H=5 excess **median flipped sign**, +0.078 → **−0.045**,
  landing on top of C's −0.046; H=10 median +0.132 → **−0.008**. Those medians were positive
  only because they contained the reaction jump.
- **No lead-time gradient inside the window** (lead 1→5 reaction means +0.54, −0.17,
  +0.40, −0.51, +0.16 — noise, not structure; unchanged in shape from v0).
- **A's half-split is still not sign-stable** (early −0.05, late +0.14); C's still is.
- **The adverse tail is still ~half.** n=**357**, 49.2% of cohort A.

Nothing flipped in a direction favourable to the hypothesis. The two sign flips (A's H=5
and H=10 excess medians) both moved **against** it.

## Before / after — every headline cell that moved

v0 committed values vs v0.1, same data. Cells not listed are unchanged.

**Event-anchored (anchor = report date T)**

| Cell | v0 | v0.1 | driver |
|---|---|---|---|
| A reaction mean | +0.027% | **+0.047%** | F4 |
| A reaction median | +0.049 | +0.059 | F4 |
| A reaction win | 50.4% | 50.6% | F4 |
| A H=5 excess mean | +0.32 | **+0.127** | **F1** |
| A H=5 excess **median** | +0.078 | **−0.045** *(sign flip)* | **F1** |
| A H=5 loser ≤−3pp | 19.8% | **15.6%** | F1 |
| A H=10 excess mean | +0.422 | **+0.232** | **F1** |
| A H=10 excess **median** | +0.132 | **−0.008** *(sign flip)* | **F1** |
| A H=10 loser | 27.8% | 25.2% | F1 |
| C reaction mean | +0.351% | +0.352% | F4 |
| C H=5 excess mean | +0.21 | **+0.038** | **F1** |
| C H=10 excess mean | +0.231 | **+0.055** | **F1** |
| C H=5 loser | 21.5% | 18.2% | F1 |
| A `take` H=5 excess | +1.133 (n=277) | **+0.523** | F1 |
| A `block` H=5 excess | −0.187 (n=448) | −0.123 | F1 |
| Adverse tail | 358 (49.3%) | **357 (49.2%)** | F4 |
| Worst-6 list | VRT, TGT, WBD, AMD, SBUX | **SRE enters at #4** (−18.97%) | F4 |

**Entry-anchored (anchor = knowability date K).** F1 does not touch these rows — they are
anchored on the entry, which no announcement window governs — so cohort A is **unchanged**
(H=5 −0.045, loser 25.7%). The control moved because of F2:

| Cell | v0 (unfloored) | v0.1 (floored) |
|---|---|---|
| B n (names) | 6,048 (239) | **4,586 (226)** |
| B H=5 excess mean | −0.013 | −0.010 |
| B H=5 loser ≤−3pp | 14.6% | **14.7%** |
| B H=10 excess mean | −0.027 | −0.022 |
| B `take` H=5 / loser | +1.631 (n=2,133) / 3.0% | **+1.571 (n=1,639) / 3.3%** |
| B `block` H=5 / loser | −0.910 (n=3,912) / 20.9% | **−0.891 (n=2,944) / 21.1%** |
| B half-split H=5 sign-stable | **yes** | **no** (early +0.011, late −0.032) |

The floor removed a quarter of the control and moved essentially nothing — which is itself
the finding: the holes were **not** biased, so v0's A-vs-B comparison was lucky rather than
sound. v0's unfloored cell is retained in the JSON
(`cohort_b_entry_control_unfloored_v0`) so the correction stays inspectable. **B's
half-split sign-stability is now `false`** — v0 said "B and C both are", which no longer
holds; both halves sit within ±0.04 of zero, so this is a sign flip around nothing rather
than an unstable effect, and it is reported because a half-split that is only quoted when
it agrees is not a guard.

## Coverage and frame — what could and could not be measured

| Item | State |
|---|---|
| Signals universe | 240 published `site/signals/*.json`; 239 priced (SATS unpriced). **Self-restricted, not data-limited** (F12): the same price store carries **2,768** US tickers and the sibling `ignition_standins.py` runs on all of them. Every thin per-quarter cell below is therefore partly a chosen frame |
| Deep earnings history | `data/edgar/earnings_8k_dates.parquet`, SEC 8-K Item 2.02 — 16,720 rows / **204 of 240 names**, and it **ENDS 2026-07-02, before all three operator receipts** |
| Earnings coverage holes | **36 of 240 names hold ZERO 8-K rows** across the whole span (ABNB, AMAT, APD, BNY, BRK-B, CASY, COF, COST, CRH, CSCO, DD, DVN, ECHO, FOX, GE, GOOG, IBM, LLY, LOW, MAR, MCD, MRVL, ORLY, PGR, QCOM, RCL, SCHW, SLB, TTWO, UBER, V, VLO, VRTX, VZ, WFC, XOM); 8 hold none from either source. v0 called price history "the binding constraint, tighter than earnings coverage" — **false for these 36**, where earnings coverage binds at zero |
| Recent-window bridge | `data/earnings/earnings.parquet` `next_date` now past — 212 rows / 212 names, **2026-07-09→08-07** (v0 printed the range as 2026-06-23→08-07; measured, the earliest is 2026-07-09). v0 also said these rows "were never refreshed after 2026-06-19"; measured, that holds for **152 of 212** — 60 carry a later `as_of` (2026-07-28…08-07). Histogram in the JSON |
| Prices | `data/baskets/ohlcv` (primary) → `data/yahoo` (fallback), SPY benchmark; window **2014-01-02 → 2026-08-07** |
| Knowability | **DERIVED, and as of v0.1 that is a choice.** At the 2026-08-08 vintage this run holds, markers carry no `signal_date`. v0 attributed that to "unmerged PR #4987" — that PR was **closed unmerged**; the field landed on main in **#5071**, whose re-render stamps `signal_date` on **56,181 of 56,293** markers. **The follow-up is CLOSED, not open**: derived vs stamped agree on **26,763 of 26,788** comparable markers (99.91%), every disagreement pre-1995 and outside this study's 2014+ window. The derivation was **not** load-bearing |
| Announcement window | Derived per row. **EDGAR-roll-aware (F4):** 796 rows arrive already dated to the session that reads them and are no longer rolled twice; the roll is one-directional (796 with acceptance earlier than `filing_date`, **zero** the other way). **Fixed −4 ET offset (F5):** v0's docstring claimed it never crosses the 16:00 edge — false. **48 of 16,720 rows (0.29%)** land on the wrong side against true `America/New_York` and carry the wrong reaction session; 473 more move only between `pre_open` and `intraday`, which are the same session T. Both counts are recomputed every run |
| `window_unknown` | 9 of 726 cohort-A rows. v0 said excluding them moves every headline "by ≤0.01pp" — **wrong**: the real maximum is **0.025pp** (H=10 excess 0.232 → 0.257; H=5 0.127 → 0.144; reaction 0.047 → 0.046) |
| Same-session confluences | **154** cohort-C rows carry a marker knowable *on* the report session. The window is [T−5, T−1] and is not moved, so they are not cohort A — but they sit inside the "no confluence at all" base rate. C without them: reaction **+0.320** (vs +0.352), H=5 +0.046, H=10 +0.063. The A-vs-C reading is unchanged |
| DLB, SPCX | **ABSENT from the signals universe entirely** — no `site/signals/DLB.json` or `SPCX.json` is published, so no marker for either can exist. Neither carries an earnings row in the joined frame either |

Definitions, stated: **loser := excess vs SPY ≤ −3pp** (excess ≤ 0 also printed in the JSON,
for parity with masterplan §6.6's first run); **win := excess > 0**; reaction :=
close(reaction session)/close(prior session) − 1; H=5 and H=10 are registered rungs of
`scripts/grade_us_board.HORIZONS`, and both are now anchored on the **reaction session**
for report-anchored rows (F1). Survivorship: a name whose series ends before a horizon is
liquidated at its last print and kept in the cell (`n_truncated`: 10/143/9/8 in
A/C/A-entry/B), never dropped. Cells with n < 20 carry `thin` and are not verdicts.

**No preregistration and no multiplicity correction** (F10). This instrument was written
after the operator's question, not before, and it prints many cells without controlling the
family-wise error rate. That is house-legal at research tier and it is precisely why nothing
here may be promoted — sibling preregs in this same directory
(`FRESH_TICKS_EXTENSION_PREREG.md`, `INTAKE_FILTER_PREREG.md`) are what promotion looks
like. The direction helps: an uncorrected search returning a **null** is not made more null
by correction. Any future claim that a cell here is **positive** needs its own prereg.

## The three cohorts

Anchors are never mixed: A-vs-C is anchored on the report date, A-vs-B on the entry, and there
is deliberately **no pooled top-line** averaging cohorts against each other.

**Event-anchored (anchor = report date T) — does a pre-report confluence improve the reaction?**

| Cohort | n (names) | reaction mean [95% CI] / median | win | fwd H=5 excess mean / med | H=5 loser | H=10 excess mean | H=10 loser |
|---|---|---|---|---|---|---|---|
| **A** confluence knowable in [T−5, T−1] | 726 (198) | **+0.047%** [−0.32, +0.42] / +0.059 | 50.6% | +0.127 / −0.045 | 15.6% | +0.232 | 25.2% |
| **C** report, no pre-confluence (base rate) | 9,497 (228) | **+0.352%** [+0.25, +0.46] / +0.220 | 52.5% | +0.038 / −0.046 | 18.2% | +0.055 | 24.4% |

| Contrast (A − C) | diff | SE | t | 95% CI | MDE (80%) | reading |
|---|---|---|---|---|---|---|
| reaction | −0.305 | 0.196 | −1.56 | −0.690 … +0.079 | 0.550 | indistinguishable |
| H=5 excess | +0.089 | 0.161 | +0.55 | −0.227 … +0.406 | 0.452 | indistinguishable |
| H=10 excess | +0.176 | 0.226 | +0.78 | −0.267 … +0.619 | 0.633 | indistinguishable |

**Entry-anchored (anchor = knowability date K) — is a pre-earnings entry better than one away from earnings?**

| Cohort | n (names) | H=5 excess mean / median | win | **H=5 loser (≤−3pp)** | H=10 excess mean | H=10 loser |
|---|---|---|---|---|---|---|
| **A** entry into a report within 5 sessions | 720 (198) | −0.045 / −0.067 | 49.3% | **25.7%** | +0.307 | 27.6% |
| **B** entry with no report within ±10 sessions, **name-year observed** | 4,586 (226) | −0.010 / −0.028 | 49.5% | **14.7%** | −0.022 | 22.3% |

A−B at H=5: diff −0.035, SE 0.235, t = −0.15, 95% CI −0.50…+0.43, MDE 0.658 —
**indistinguishable**, and the same on the unfloored control (diff −0.032). The A-vs-B mean
gap is nothing; **the loser gap (25.7% vs 14.7%) carries the whole result.**

**Quality is the discriminator that earnings proximity is not.** `quality` is stamped by the
engine's existing buy-filter (`engine/signal_quality.py:604` — `take` passed, `block` vetoed):

| | A reaction mean | A win | A H=5 excess | A H=5 loser | B H=5 excess | B H=5 loser |
|---|---|---|---|---|---|---|
| `take` | +1.87% (n=277) | 65.0% | +2.86 (n=275) | **10.2%** | +1.57 (n=1,639) | **3.3%** |
| `block` | −1.09% (n=448) | 41.5% | −1.86 (n=444) | **35.4%** | −0.89 (n=2,944) | **21.1%** |

(The H=5 columns are entry-anchored on both sides, so the comparison is like-for-like; the
event-anchored `take` cell fell from +1.13 to +0.52 under F1 and is in the JSON.)
The filter separates in both cohorts, so this is the filter working — not an earnings effect.
Logged as a **lead, not a finding**: it was built on this same panel and calibrated for
drawdown, never for earnings reaction. Any claim on it needs its own prereg.

**The one directionally consistent finding is a RISK finding, not an edge finding**, and it
survives every correction. Holding the engine's own entry quality fixed, a pre-earnings entry
carries a materially fatter downside tail than the same-quality entry away from earnings, at
an indistinguishable mean: `take` losers 10.2% vs 3.3%, `block` losers 35.4% vs 21.1%
(H=5, loser := excess ≤ −3pp). Earnings proximity added variance, not return.

**Read this against the confound the operator flagged:** the quarter that motivated the
question (2026Q1 n=14, reaction mean +4.50, win 85.7%) is one of the *best* cells in the whole
series, and it sits beside 2025Q3 (n=9, −2.92, win 11.1%) and 2025Q4 (n=14, −1.42, win 35.7%).
All are thin. A broad-beat quarter is what this cohort looks like when it is working, and what
a single quarter cannot distinguish from luck.

## The adverse tail — the load-bearing cell

**It is not empty. n=357, which is 49.2% of cohort A** — a fresh pre-report confluence preceded
a negative reaction almost exactly half the time. "Does a confluence ever precede a miss?" is
answered emphatically yes, at coin-flip frequency, across 12 years.

Worst six, all with the derived knowability date preceding the report:

| Name | marker | knowable | report | window | lead | quality | reaction | H=5 excess |
|---|---|---|---|---|---|---|---|---|
| VRT | 2022-02-11 | 2022-02-15 | 2022-02-23 | pre_open | 5 | block | **−36.7%** | −6.8 |
| TGT | 2024-11-14 | 2024-11-18 | 2024-11-20 | pre_open | 2 | block | **−21.4%** | +5.5 |
| WBD | 2023-11-01 | 2023-11-03 | 2023-11-08 | pre_open | 3 | block | −19.0% | +9.5 |
| SRE | 2025-02-19 | 2025-02-21 | 2025-02-25 | intraday | 2 | block | −19.0% | +2.9 |
| AMD | 2014-07-09 | 2014-07-11 | 2014-07-17 | after_close | 4 | **take** | −16.2% | −1.8 |
| SBUX | 2024-04-25 | 2024-04-29 | 2024-04-30 | after_close | 1 | block | −15.9% | −4.6 |

18 of the worst 20 are `block`-quality and two (AMD, SBUX) are not, so the filter is no complete
defence. The charter's conditional "no adverse case in this window" does **not** apply here.
(v0 listed five rows under a "worst six" heading; SRE is the row F4's reaction-session fix
brings into the top six, and the sixth slot is now filled.)

## Case receipts — the 2026 names, against the frame that exists

The 2026 report dates here are bridge **forecasts**, not confirmed filings; every statement
below is checked to survive a ±1-session error in that forecast. The "nearest 2026 report"
is now the true nearest — v0's loop overwrote its candidate on every match and so returned
the **latest** (F7). Both rows below are unchanged by that fix; each name has one 2026 report
in range, which is why the defect was invisible in v0's output and needed the code read.

| Name | marker | quality | knowable | nearest 2026 report | lead | in cohort A? |
|---|---|---|---|---|---|---|
| AMZN | 2026-07-31 buy | block | **2026-08-04** | 2026-07-30 | **−3** | No — knowable AFTER the report |
| MSFT | 2026-07-15 buy | block | 2026-07-17 | 2026-07-29 | **8** | No — lead exceeds the chartered 5 |
| DLB | — | — | — | — | — | No signal artifact exists |
| SPCX | — | — | — | — | — | No signal artifact exists |

**Neither 2026 receipt is a member of the cohort the hypothesis describes**, and both facts
survive the forecast-date ambiguity: AMZN's marker is knowable three sessions *after* the
report (a ±1-day shift leaves it post-report either way), and MSFT's lead of 8 sessions clears
the chartered [T−5, T−1] window by three. Both are `block`-quality. This does not make the
operator's observation wrong — it means the published marker stream on this base does not
encode those two entries as pre-earnings confluences, so the receipts cannot be adjudicated
from it. Widening the window to capture MSFT after seeing it fall outside is precisely
`DNR:KILL-OUTCOME-AUDITION`'s construction, so it was not done. Their genuine historical
pre-earnings confluences are in the JSON (`case_receipts`): AMZN 3, MSFT 4 — both split
positive and negative, at n supporting no claim.

## What this receipt does NOT license

`DNR:KILL-CALENDAR-GATED-RISK` forbids calendar/event-window-gated risk legs at any tier,
because a state-advancing leg sets gross. The fatter pre-earnings tail measured above is
exactly the number that invites that construction. **It is not licensed here.** This
instrument advances no state, sets no gross, emits no leg; turning these cells into an
event-window risk or sizing channel needs its own adjudication, not this receipt.

Also honored: `DNR:KILL-OFFHORIZON-VERDICTS` (H=5/H=10 are registered rungs; the day-0 reaction
is labelled an event reaction, not a horizon verdict); `DNR:KILL-OUTCOME-AUDITION` (every
cohort label is fixed before the outcome is observable — including the F2 coverage floor,
which is a property of the *store*, never of an outcome); `DNR:KILL-PROPHET-POP-MERGE` (the
graded-board population is untouched). `HOLD-IGNITION-SURFACES` is a **name collision only** —
it suspends the sector/theme Ignition Radar's user-facing surfaces; this study builds no
surface and shares no code, input or output with it.

**Group/peer-reaction inputs are deliberately absent.** The 'Earnings Intelligence' /
Group Reads work (basket participation + earnings co-movement) owns that construction.
v0 wrote that "nothing of theirs was committed at the time of this run" — **that was wrong**:
`research/GROUP_READS_MASTERPLAN_BY_FABLE.md` landed on main in `d1b115804b5` (#4991) about
thirteen minutes *before* v0's `generated_utc`. The substantive point is unchanged and is
what matters: it is a **different construction**, group reaction is the natural extension of
the A-vs-C contrast, and the instruction stands — **cite them, do not rebuild**.

## Reproduce, and what stays open

`python3 research/prophet_us_audit/earnings_ignition_measurement.py` — deterministic, ~15 s,
no network; emits the JSON beside this file. (v0's run line prefixed `TZ=UTC`; that is
unnecessary — the instrument reads no local time, and v0's `os.environ.setdefault("TZ",…)`
was a no-op that read as a guarantee, so it is gone.) Cohort-logic tests —
`research/prophet_us_audit/test_earnings_ignition_measurement.py`, **22 passing**,
mutation-checked: flipping knowability to the bucket OPEN label reds the bucket test;
re-anchoring the forward excess at the report session reds
`test_after_close_forward_excess_is_anchored_after_the_print`; removing the EDGAR-roll check
reds `test_edgar_roll_is_not_applied_twice`.

**That suite had never run in CI** (F13). It was triggerable but no `run:` step executed it —
the same trap `.github/ci/legacy-jobs.yml` documents for its two siblings. It is now wired
into the `signal-contract` job's *research-resident label-grading + buy-filter guards* step,
with both the instrument and the test added to `ci.yml`'s path filters.

1. **The claim remains unmeasured across regimes at usable n.** Every per-quarter cell in the
   receipt era is thin (n 9–29); the 12-year pooled read is the only non-thin evidence, and it
   is null — with an MDE of ~0.55pp on the headline contrast, so "null" means *no effect
   larger than that*, not *no effect*.
2. **The two 2026 receipts are not adjudicable from the published marker stream** — the
   confirming EDGAR source stops 2026-07-02 and the bridge is a forecast. Re-running after the
   8-K store advances past July is the cheap decisive follow-up.
3. **The universe, not the window, is the honest widening.** 240 of 2,768 priced names is a
   chosen frame; re-running on the full price universe would raise every thin cell and selects
   on nothing. Widening the **lead window** past T−5 still needs a prereg with the window fixed
   first.
4. **Closed since v0:** the `signal_date` follow-up. It landed (#5071), the derived-vs-stamped
   diff was run, and they agree on 99.91% of comparable markers with every disagreement outside
   this window. The derivation was not load-bearing and re-running on it would change nothing.
5. **Still open in the instrument:** the ET offset is fixed at −4, which mis-assigns the
   reaction session on 48 of 16,720 rows (0.29%). Left in deliberately so this amendment's
   before/after stays attributable to F1/F4; the count is emitted every run.
