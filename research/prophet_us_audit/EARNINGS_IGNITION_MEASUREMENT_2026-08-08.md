# EARNINGS IGNITION — measurement receipt (ANTICIPATION §6.8(e), 2026-08-08)

RESEARCH TIER. This receipt MEASURES. No gate, rank, size, lane, surface or config changes;
nothing here is a promotion and no cell below licenses one. Instrument (purely mechanical —
makes no LLM call of any kind, per A7): `research/prophet_us_audit/earnings_ignition_measurement.py`; data: `EARNINGS_IGNITION_MEASUREMENT_2026-08-08.json`.

## Verdict

**The hypothesis does not reproduce, and the adverse tail is not empty.** A fresh
buy-confluence knowable in the five sessions before a report does NOT predict a better
reaction than the base rate: cohort A reaction mean **+0.03%** / median +0.05% / win 50.4%
(n=726) against cohort C's **+0.35%** / +0.21% / 52.4% (n=9,497). The pre-report cohort reads
slightly *worse* than reports with no confluence at all, its half-split sign is **not stable**
(early −0.08, late +0.14) while the base rate's is, and there is no lead-time gradient inside
the window (lead 1→5 reaction means +0.55, −0.19, +0.37, −0.59, +0.18 — noise, not structure).

**The one directionally consistent finding is a RISK finding, not an edge finding.** Holding
the engine's own entry quality fixed, a pre-earnings entry carries a materially fatter
downside tail than the same-quality entry away from earnings, at an indistinguishable mean:
`take` losers 10.2% vs 3.0%, `block` losers 35.4% vs 20.9% (H=5, loser := excess ≤ −3pp).
Earnings proximity added variance, not return, in both quality classes.

**Read this against the confound the operator flagged:** the quarter that motivated the
question (2026Q1 n=14, reaction mean +4.30, win 85.7%) is one of the *best* cells in the whole
series, and it sits beside 2025Q3 (n=9, −2.92, win 11.1%) and 2025Q4 (n=14, −1.42, win 35.7%).
All are thin. A broad-beat quarter is what this cohort looks like when it is working, and what
a single quarter cannot distinguish from luck.

## Coverage and frame — what could and could not be measured

| Item | State |
|---|---|
| Signals universe | 240 published `site/signals/*.json`; 239 priced (SATS unpriced) |
| Deep earnings history | `data/edgar/earnings_8k_dates.parquet`, SEC 8-K Item 2.02 — 16,720 rows / **204 of 240 names**, and it **ENDS 2026-07-02, before all three operator receipts** |
| Recent-window bridge | `data/earnings/earnings.parquet` `next_date` now past — 212 rows / 212 names, 2026-06-23→08-07. These are **forecasts**: stamped `as_of` 2026-06-19 and never refreshed, which is the only reason July dates survive at all |
| Prices | `data/baskets/ohlcv` (primary) → `data/yahoo` (fallback), SPY benchmark; window **2014-01-02 → 2026-08-07** — the binding constraint, tighter than earnings coverage |
| Knowability | `signal_date` **does not exist on this base** (it ships in unmerged PR #4987; `OUTAGE_WINDOW_STAMP_AUDIT_2026-08-08.md` is not on main either), so knowability is **DERIVED and disclosed**: a marker's `date` is its 3D bucket's OPEN label (`engine/signal_quality` docstring), so the earliest actionable moment is that bucket's LAST session. Every cohort test uses the derived date, never the open label |
| Announcement window | Derived per row, not assumed: EDGAR `acceptance_datetime` (UTC→ET) and bridge `next_time`. After-close ⇒ reaction is T+1; pre-open/intraday ⇒ session T. 9 of 726 cohort-A rows are `window_unknown`; every headline reprinted without them moves by ≤0.01pp |
| DLB, SPCX | **ABSENT from the signals universe entirely** — no `site/signals/DLB.json` or `SPCX.json` is published, so no marker for either can exist. Neither carries an earnings row in the joined frame either |

Definitions, stated: **loser := excess vs SPY ≤ −3pp** (excess ≤ 0 also printed in the JSON,
for parity with masterplan §6.6's first run); **win := excess > 0**; reaction :=
close(reaction session)/close(prior session) − 1; H=5 and H=10 are registered rungs of
`scripts/grade_us_board.HORIZONS`. Survivorship: a name whose series ends before a horizon is
liquidated at its last print and kept in the cell (`n_truncated`: 10/143/9/11 in A/C/A-entry/B),
never dropped. Cells with n < 20 carry `thin` and are not verdicts.

## The three cohorts

Anchors are never mixed: A-vs-C is anchored on the report date, A-vs-B on the entry, and there
is deliberately **no pooled top-line** averaging cohorts against each other.

**Event-anchored (anchor = report date T) — does a pre-report confluence improve the reaction?**

| Cohort | n (names) | reaction mean / median | win | fwd H=5 excess mean / med | H=5 loser | H=10 excess mean | H=10 loser |
|---|---|---|---|---|---|---|---|
| **A** confluence knowable in [T−5, T−1] | 726 (198) | **+0.027% / +0.049%** | 50.4% | +0.32 / +0.08 | 19.8% | +0.42 | 27.8% |
| **C** report, no pre-confluence (base rate) | 9,497 (228) | **+0.351% / +0.212%** | 52.4% | +0.21 / −0.02 | 21.5% | +0.23 | 26.5% |

**Entry-anchored (anchor = knowability date K) — is a pre-earnings entry better than one away from earnings?**

| Cohort | n (names) | H=5 excess mean / median | win | **H=5 loser (≤−3pp)** | H=10 excess mean | H=10 loser |
|---|---|---|---|---|---|---|
| **A** entry into a report within 5 sessions | 720 (198) | −0.045 / −0.067 | 49.3% | **25.7%** | +0.31 | 27.6% |
| **B** entry with no report within ±10 sessions | 6,048 (239) | −0.013 / −0.034 | 49.5% | **14.6%** | −0.03 | 22.6% |

Half-split by date: cohort A's reaction and its H=5 excess are **not** sign-stable across halves;
B and C both are. The A-vs-B mean gap (−0.03pp at H=5) is nothing — the loser gap (25.7% vs
14.6%) carries the whole result.

**Quality is the discriminator that earnings proximity is not.** `quality` is stamped by the
engine's existing buy-filter (`engine/signal_quality.py:604` — `take` passed, `block` vetoed):

| | A reaction mean | A win | A H=5 excess | A H=5 loser | B H=5 excess | B H=5 loser |
|---|---|---|---|---|---|---|
| `take` | +1.83% (n=277) | 64.6% | +2.86 (n=275) | **10.2%** | +1.63 (n=2,133) | **3.0%** |
| `block` | −1.10% (n=448) | 41.5% | −1.86 (n=444) | **35.4%** | −0.91 (n=3,912) | **20.9%** |

The filter separates in both cohorts, so this is the filter working — not an earnings effect.
Logged as a **lead, not a finding**: it was built on this same panel and calibrated for
drawdown, never for earnings reaction. Any claim on it needs its own prereg.

## The adverse tail — the load-bearing cell

**It is not empty. n=358, which is 49.3% of cohort A** — a fresh pre-report confluence preceded
a negative reaction almost exactly half the time. "Does a confluence ever precede a miss?" is
answered emphatically yes, at coin-flip frequency, across 12 years.

Worst six, all with the derived knowability date preceding the report:

| Name | marker | knowable | report | lead | quality | reaction | H=5 excess |
|---|---|---|---|---|---|---|---|
| VRT | 2022-02-11 | 2022-02-15 | 2022-02-23 | 5 | block | **−36.7%** | −6.8 |
| TGT | 2024-11-14 | 2024-11-18 | 2024-11-20 | 2 | block | **−21.4%** | +5.5 |
| WBD | 2023-11-01 | 2023-11-03 | 2023-11-08 | 3 | block | −19.0% | +9.5 |
| AMD | 2014-07-09 | 2014-07-11 | 2014-07-17 | 4 | **take** | −16.2% | −19.9 |
| SBUX | 2024-04-25 | 2024-04-29 | 2024-04-30 | 1 | block | −15.9% | −21.1 |

18 of the worst 20 are `block`-quality and two (AMD, SBUX) are not, so the filter is no complete
defence. The charter's conditional "no adverse case in this window" does **not** apply here.

## Case receipts — the 2026 names, against the frame that exists

The 2026 report dates here are bridge **forecasts** stamped 2026-06-19, not confirmed filings;
every statement below is checked to survive a ±1-session error in that forecast.

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
pre-earnings confluences are in the JSON (`case_receipts`): AMZN 3 (2015-01 +13.7%, 2019-10
−1.1%, 2025-04 −0.1%), MSFT 4 — both split positive and negative, at n supporting no claim.

## What this receipt does NOT license

`DNR:KILL-CALENDAR-GATED-RISK` forbids calendar/event-window-gated risk legs at any tier,
because a state-advancing leg sets gross. The fatter pre-earnings tail measured above is
exactly the number that invites that construction. **It is not licensed here.** This
instrument advances no state, sets no gross, emits no leg; turning these cells into an
event-window risk or sizing channel needs its own adjudication, not this receipt.

Also honored: `DNR:KILL-OFFHORIZON-VERDICTS` (H=5/H=10 are registered rungs; the day-0 reaction
is labelled an event reaction, not a horizon verdict); `DNR:KILL-OUTCOME-AUDITION` (every
cohort label is fixed before the outcome is observable); `DNR:KILL-PROPHET-POP-MERGE` (the
graded-board population is untouched). `HOLD-IGNITION-SURFACES` is a **name collision only** —
it suspends the sector/theme Ignition Radar's user-facing surfaces; this study builds no
surface and shares no code, input or output with it.

**Group/peer-reaction inputs are deliberately absent.** The active 'Earnings Intelligence'
session (Struct/Jodie-clone group-reaction system) owns that construction; nothing of theirs was
committed at the time of this run — no PR, no research doc, no claim on these three paths. Group
reaction is the natural extension of the A-vs-C contrast: cite them, do not rebuild.

## Reproduce, and what stays open

`TZ=UTC python3 research/prophet_us_audit/earnings_ignition_measurement.py` — deterministic,
~26 s, no network; emits the JSON beside this file. Cohort-logic tests (derived knowability,
loser/win arithmetic, announcement window) — `research/prophet_us_audit/test_earnings_ignition_measurement.py`,
11 passing, mutation-checked: flipping knowability to the bucket OPEN label reds the bucket test.

1. **The claim remains unmeasured across regimes at usable n.** Every per-quarter cell in the
   receipt era is thin (n 9–29); the 12-year pooled read is the only non-thin evidence, and it
   is null.
2. **The two 2026 receipts are not adjudicable from the published marker stream** — the
   confirming EDGAR source stops 2026-07-02 and the bridge is a forecast. Re-running after the
   8-K store advances past July is the cheap decisive follow-up.
3. **Lead-window sensitivity beyond T−5** — needs a prereg with the window fixed first.
   Likewise `signal_date` (PR #4987), which replaces the derived knowability with a stamped
   one: re-run and diff when it lands — if the cohorts move, the derivation was load-bearing.
