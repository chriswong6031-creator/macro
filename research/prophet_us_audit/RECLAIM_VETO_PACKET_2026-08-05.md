# US 200-day reclaim-veto — DECISION PACKET

**Date:** 2026-08-05 · **Wave:** W-F of `PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md`
· **Tier:** research — **decision input, NOT a change**
· **Instrument:** `research/prophet_us_audit/reclaim_veto_packet.py`
· **Frozen receipts:** `reclaim_veto_packet_results_2026-08-05.json`

> **THIS DOCUMENT CHANGES NOTHING.** No code path moved. `reclaim_veto` remains `True` at
> every entry point (`_buy_filter`, `analyze`, `signal_gate.gate`), pinned by
> `tests/test_hk_reclaim_veto_policy.py::test_every_entry_point_defaults_to_the_validated_policy`
> and re-pinned by this wave's
> `tests/test_us_reclaim_veto_packet.py::test_the_packet_does_not_change_the_shipped_policy`.
> An era-stamped `us_prophet_v1 → v2` is the operator's call, exactly as HK's was. This file
> assembles the evidence for that call and stops there. It carries **no recommendation.**

---

## §1 What the leg is, and why anyone is asking

`engine/signal_quality._buy_filter` applies one extra condition to a name that is BOTH below
its 200-day average AND weekly-down: it must close back above the 200-day line within 2 bars
(`reclaim`), on top of the next-bar follow-through (`held`) that every other name gets.

The argument **against** the leg is that it is unsatisfiable by construction: a name 17%
below its 200-day line cannot travel 17% in two sessions, so every buy it fires while washed
out is auto-blocked until the bounce being signalled is already over. HK measured exactly
that and took the era stamp — `hk_prophet_v2`, #4470, 12 refused names that ran +8.7%..+44%
(`engine/signal_quality.py:188-196`).

The argument **for** the leg is that it is part of a buy-filter with a measured drawdown
benefit: reclaim-and-hold + bearish-divergence veto + the 200-day bar-raiser together cut
average max drawdown **−23.7% → −15.5% across 110 held-out US names (84% improved)** —
`engine/signal_quality.py:7`. That validation was measured **with the leg on**. So the leg
is not free to drop on the strength of HK's tape; the US needs its own ledger.

This packet is the other side of that ledger. Both columns are printed below.

---

## §2 How the refusal set was built (and why it is exactly one leg)

`analyze()` takes `reclaim_veto` as a keyword and `signal_frame()` does not depend on it, so
the **same production function is called twice on the same series** and every other leg — the
CB/revBuy confluence, the bearish-divergence veto, the weekly gate, the 200-day gate itself —
is re-evaluated identically under both settings. The refusal set is the marker diff:

```
on  = analyze(t, close, reclaim_veto=True)     # what the board does today
off = analyze(t, close, reclaim_veto=False)    # same engine, that one leg dropped
refused = dates where on == "block" with reason "counter-trend, no 200-reclaim/hold"
                  AND off == "take"
```

Both halves are load-bearing. **When these figures were measured, a name that failed the
next-bar HOLD returned the identical block string** (the branch was `ok = held and reclaim`,
so either failure collapsed to one reason). Filtering on the reason alone would sweep
failed-hold bars into a packet claiming the reclaim leg refused them; the `off == "take"`
half is what excluded them.
`tests/test_us_reclaim_veto_packet.py::test_a_failed_hold_is_excluded_twice_over_by_reason_and_by_the_veto_off_half`
is the test that makes that half load-bearing, and both halves were mutation-checked
(dropping either turns the suite red).

> **Amended 2026-08-05 (#4583).** That PR split the collapsed reason into
> `CT_BOTH_FAIL` (both legs failed) and `CT_RECLAIM_FAIL` (held, but no reclaim), so the
> two cases no longer share a string and the reason now excludes a failed hold on its own —
> the `off == "take"` half is a second, independent guard rather than the only one. The
> packet's `BLOCK_REASON` is now BOUND to `sq.CT_RECLAIM_FAIL` instead of copying the
> literal; the pre-split copy silently became the OTHER case's label and emptied the
> refusal set. **The figures below are unaffected** — they were measured before the split,
> while the copied literal still named the intended branch.

**No look-ahead.** The refusal needs `reclaim` to have failed at BOTH i+1 and i+2, so it is
first knowable at the close of 3D bar i+2. Marker-date grading is forbidden here — a marker
carries +5.7pp/10d of look-ahead (`analyze` docstring). Every forward return below is
therefore anchored on **the last daily close inside 3D bar i+2**, the confirmation close.
That concedes the first two 3D bars of any move to the veto's side of the ledger: it is the
conservative anchor, and it makes the cost column an **understatement**, not an overstatement.

**Panel:** the curated stock universe caches (breadth / midcap / smallcap `_closes_cache`),
1,540 tickers, last bar **2026-07-31**. **Window:** the trailing 126 sessions — first refusal
date **2026-01-30**. Runtime 68s.

---

## §3 The headline

| | |
|---|---|
| Refused fires | **353** |
| Distinct names | **315** |
| Distinct refusal **dates** | **41** (see §5 — this is the number that governs) |
| Median forward **excess** vs SPY @21 | **−4.54pp** (n=305) |
| Mean forward excess @21 | −3.37pp |
| Median excess @10 / @63 | −0.87pp (n=341) / −5.61pp (n=223) |
| Loser rate (excess @21 < −3pp) | **56.7%** (173 / 305) |
| Winner rate (excess @21 > +3pp) | **29.8%** (91 / 305) |
| Median MAE within 21 | **−5.85%** |

**On the pooled window the refused cohort underperformed.** That is the opposite of HK's
result, and it is the first thing an operator should know. It is also not the whole story —
§5 and §6 are the reasons it must not be read as a verdict.

---

## §4 Both sides, printed

### The COST side — what the veto refused that then ran
91 of 305 graded fires (29.8%) went on to beat SPY by more than 3pp within 21 sessions;
their median excess was **+9.17pp** (mean +11.98pp). The largest:

| Name | Refused | Excess @21 | Raw @21 |
|---|---|---|---|
| DDOG | 2026-04-13 | +68.9pp | +73.9% |
| PI | 2026-03-31 | +42.6pp | +51.4% |
| QCOM | 2026-04-08 | +39.0pp | +42.2% |
| PGNY | 2026-04-13 | +35.8pp | +40.8% |
| FTRE | 2026-04-13 | +32.3pp | +37.3% |
| TECH | 2026-05-28 | +28.4pp | +31.0% |

This tail is real and it is the HK-shaped complaint: these are washed-out names the board
could not admit while the bounce was happening.

### The SAVED side — what it refused that then fell
173 of 305 (56.7%) lost to SPY by more than 3pp, median **−11.08pp** (mean −12.24pp). Across
all 353 fires the median MAE within 21 sessions was **−5.85%**; **33.7%** drew down 10% or
worse and **5.7%** drew down 20% or worse. The largest:

| Name | Refused | Excess @21 | MAE @21 |
|---|---|---|---|
| FWRD | 2026-04-13 | −66.3pp | −63.5% |
| AZTA | 2026-04-08 | −36.4pp | −39.3% |
| AXON | 2026-02-25 | −29.9pp | −33.3% |
| PLNT | 2026-04-13 | −29.7pp | −36.3% |
| INSP | 2026-04-08 | −28.6pp | −29.7% |
| CTSH | 2026-05-20 | −26.7pp | −32.2% |

The drawdown column is the one the leg was shipped for. On this window the saved side is both
**more frequent** (56.7% vs 29.8%) and **larger in the tail** than the cost side.

### Stratified by drawdown from the 252-day high

| Band | Fires | Names | Median excess @10 | @21 | @63 | Median MAE @21 | Loser rate |
|---|---|---|---|---|---|---|---|
| 0–20% | 74 | 70 | −1.65pp | −6.11pp | −6.00pp | −4.26% | 66.2% |
| 20–35% | 155 | 147 | −0.37pp | −2.75pp | −1.86pp | −5.37% | 49.3% |
| **>35%** | **124** | **107** | −1.16pp | **−5.78pp** | **−10.33pp** | **−8.04%** | **60.8%** |

**No band shows a positive median at any horizon.** Note the deepest band specifically: >35%
below the 252-day high is precisely where the "unsatisfiable by construction" argument is
strongest — a name that far down genuinely cannot reclaim in two bars — and on this window it
is the band with the **worst** 63-session median (−10.33pp) and the deepest MAE (−8.04%). The
mechanism argument for dropping the leg is at its most compelling exactly where the outcome
data is least supportive of it.

---

## §5 The sample-size disclosure — read this before §3

**353 fires are not 353 independent observations.** Markers live on a 3D grid, so refusal
dates are at best 3 business days apart, and a market-wide washout fires dozens of names on a
single date whose forward returns then share almost all of their variance.

- 353 fires sit on **41 distinct dates**.
- The **top 5 dates carry 43.9%** of the sample (2026-04-13 alone: 50 fires, 14.2%).
- Monthly: Jan 2 · Feb 35 · Mar 60 · **Apr 132** · May 41 · Jun 56 · Jul 27.

Weighting each date once instead of each fire once:

| View | Median excess @21 |
|---|---|
| Pooled (n=353 fires) | −4.54pp |
| **Per-date (n=34 graded dates)** | **−1.87pp** |
| Share of dates with a negative median | 61.8% |

The headline more than halves under the conservative weighting, and nearly 4 dates in 10 are
positive. Nothing here supports a strong claim in either direction from n=34 clustered dates.

---

## §6 The finding that actually governs — the sign flips with the tape

The month-by-month decomposition is frozen in the JSON under `aggregate.by_month` (a
calendar cut carries no selection). Collapsing it at the turn of the leg — **a post-hoc split
point, chosen after seeing these rows, and to be quoted as such** — gives:

| Cohort | Fires | Median @10 *(graded)* | Median @21 *(graded)* | Median @63 *(graded)* | Median MAE | Loser % | Winner % |
|---|---|---|---|---|---|---|---|
| **Jan–Apr** (drawdown leg) | 229 | −2.18pp *(229/229)* | **−6.96pp** *(229/229)* | −5.61pp *(223/229)* | −7.90% | 68.1% | 20.1% |
| **May–Jul** (recovery leg) | 124 | +2.28pp *(112/124)* | **+4.67pp** *(**76**/124)* | — *(**0**/124)* | −3.73% | 22.4% | 59.2% |

**The veto saved money in the drawdown leg and cost money in the recovery leg.** The pooled
−4.54pp is a weighted average of two opposite regimes in which the drawdown leg simply
contributed more fires (229 vs 124) — largely because one April washout fired 132 in a month.

**Two things this split cannot settle, stated plainly:**

1. **The recovery cohort is barely graded.** Because the panel ends 2026-07-31, **none** of
   its 124 fires has a 63-session outcome and only **76 of 124 (61%)** have a 21-session one —
   the whole of July contributes **zero** graded rows at 21. Its +4.67pp therefore rests on
   May–June alone, on horizons the drawdown cohort is fully graded at. The two rows are not
   measured on the same ruler, and comparing them across horizons would manufacture a result.
2. **Excess is not the same as raw.** SPY rose **+8.25%** over the window while the refused
   cohort is below-200 **and** weekly-down by construction. Raw medians are near flat
   (@21 −1.085%, @63 +1.515%; mean @63 +4.152%). A large part of the negative excess is
   benchmark drift against a cohort defined by weakness — not evidence the leg has skill.

---

## §7 What this packet supports, and what it does not

**Supports:** the US tape over this window does **not** reproduce HK's one-directional
finding. HK saw a leg whose cost was visible and whose benefit was not; the US window shows a
genuinely two-sided ledger whose sign flips with the regime, on a sample of 34 clustered
dates, against a validated drawdown benefit measured with the leg on.

**Does not support:** any confident claim that the leg should be dropped, kept permanently, or
made conditional. In particular the deepest-drawdown band — the mechanism argument's strongest
ground — is the band where the outcome data is least favourable to dropping it, and the one
cohort that favours dropping it (May–Jul) is graded on 76 of its 124 fires at 21 sessions and
none at all at 63.

**Open questions this packet deliberately leaves open** (each would need its own pre-registered
instrument, not a re-read of these numbers):

- Does the regime split survive on a longer panel, i.e. is "drop the leg only in a recovery
  tape" a real conditional or an artifact of one 126-session window containing one washout?
- Would a *relaxed* leg (reclaim within N>2 bars, or a proximity band instead of a hard
  reclaim) keep the drawdown benefit while recovering the cost tail? This packet measured
  on/off only — it says nothing about the middle.
- Re-run after 63 more sessions, when the May–Jul cohort is gradeable at every horizon. That
  single re-run would settle §6's censoring caveat and is the cheapest next step.

**If an era stamp is ever taken**, it needs the `us_prophet_v1 → v2` `BOARD_DEFINITION` fence
that HK used (`engine/hk_board_rank.BOARD_DEFINITION == "hk_prophet_v2"`), because an
admission change makes the old and new boards different products and the forward ledger must
not pool them.

---

## §8 Reproduce

```
python3 research/prophet_us_audit/reclaim_veto_packet.py     # ~68s, writes the frozen JSON
python3 -m pytest tests/test_us_reclaim_veto_packet.py -q    # the isolation construction
python3 -m pytest tests/test_hk_reclaim_veto_policy.py -q    # the flag + its defaults
```

Every number in this document comes from
`research/prophet_us_audit/reclaim_veto_packet_results_2026-08-05.json`; the per-fire rows are
committed in that file under `fires`, and the clustering block under
`aggregate.episode_clustering`.
