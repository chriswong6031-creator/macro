# call_skew_rich construction reassessment — measurement of record (2026-07-29)

**Question.** `call_skew_rich` (chip 6 of the 7-chip CROWDED k-of-n state gate,
`CROWDED_K_OF_N=3`, `engine/leader_lifecycle.py`) fires when the latest 25Δ rr proxy
(`atm_call_iv − otm_put_iv`) is ≥ the name's own 80th percentile — computed by
`scripts/build_leader_radar.py:_load_options_skew` as `daily.quantile(0.80)` over the
name's **entire accrued history including today** (self-inclusive), gated on ≥21
observations. PR #3977's adversarial review measured 62 TRUE / 350 evaluated (17.7%) on
the weekend-padded store — indistinguishable from the mechanical base rate — and #3977's
session-true counting puts ~343 names one session from activation (n=21 real sessions
~2026-07-30). Should the construction change before mass activation, and does the chip
stay in the gate?

**Verdict (construction amendment; membership unchanged — ruling LRV-R6).** The chip
stays a CROWDED confluence input. Its construction changes before mass activation:
threshold becomes the 80th percentile of **prior history excluding the 5-session
evaluation window** (≥21 real prior sessions), and the chip fires only when **≥3 of the
last 5 observed sessions** clear that frozen threshold. First possible non-null moves
from n=21 (~2026-07-30) to n=26 (~2026-08-06). Parameters are pre-registered from null
math and state semantics — **not** tuned on outcomes (no outcome data exists).

Reproduction: `python3 research/leader_radar_skew_chip/measure_call_skew_chip.py`
(seeded, no network; writes `measurement_results.json`). All numbers below re-derived
from the raw parquet, not quoted from the review.

---

## 1. What was measured

Store: `data/options_skew/snapshots.parquet` as of 2026-07-29 — 28 distinct dates,
8 non-session (verified), 20 real sessions 2026-06-22 → 2026-07-29; 343 of 401 names
have all 20. The #3977 review number replicates **exactly: 62/350 = 17.71%** under the
padded production construction.

**Constructions compared** (evaluated day-by-day, expanding history, session-true rows;
measurement-lane relaxation `min_obs=10`, labeled — production stays 21):

- `SELF` — today ≥ Q80(history incl. today) — the shipped construction;
- `LOO` — today ≥ Q80(history excl. today);
- `PERSIST` — ≥3 of last 5 sessions ≥ Q80(history excl. those 5).

**Mechanical null rates** (iid simulation, N=200k, pandas linear-interp quantile — at
n=21 the Q80 of 21 points is exactly the 17th order statistic, so SELF's null is
P(rank ≥ 17) = 5/21):

| n_total | SELF | LOO | PERSIST 3-of-5 |
|---|---|---|---|
| 21 | 23.8% | 22.8% | 11.4% |
| 26 | 23.1% | 22.2% | 10.2% |
| 40 | 20.0% | 21.4% | 8.3% |

Note the honest wrinkle: PERSIST's null is ~11%, not the naive Bin(5, 0.2)≥3 = 5.8% —
a noisy young-n threshold moves all five window comparisons together. It converges
toward ~6–8% as history accrues; the daily constructions stay at 20–24% forever.

**Observed vs within-name permutation null** (200 reps; permutation kills temporal
order and cross-name day alignment, preserves each name's marginal distribution):

| statistic | SELF obs | SELF null (sd) | LOO obs | LOO null (sd) | PERSIST obs | PERSIST null (sd) |
|---|---|---|---|---|---|---|
| fire rate | 0.211 | 0.229 (.008) | 0.219 | 0.238 (.007) | 0.138 | 0.126 (.012) |
| P(TRUE\|TRUE yesterday) | 0.283 | 0.224 (.016) | 0.288 | 0.235 (.015) | 0.613 | 0.573 (.032) |
| mean TRUE-run (sessions) | 1.35 | 1.26 (.02) | 1.35 | 1.27 (.02) | 2.19 | 1.95 (.10) |
| breadth SD across days | 0.057 | 0.030 (.006) | 0.062 | 0.022 (.005) | 0.038 | 0.016 (.006) |

**Underlying series:** per-name lag-1 autocorrelation of daily rr — **median −0.01**
(IQR −0.14…+0.17, 350 names). Day-factor share of rr variance: 3.9%. Q80 threshold
instability: median |Q80(first 10) − Q80(all 20)| = 0.19 of the name's rr IQR (p90 =
0.58); 6.4% of names would flip today's decision purely by which window defines the
threshold.

**Day-1 forecast:** 17.5% of the 343-name cohort (~60 names; ~20 inside the radar's
116 covered rows) would fire TRUE on activation day under SELF. Radar boundary today:
11 rows carry exactly 2 TRUE non-skew chips; 8 of them have no skew coverage and the
3 covered ones (PYPL, ROST, WDAY) fire under **no** construction — **zero state flips
today under any option**. The exposure is steady-state, not day-1.

---

## 2. What the numbers mean (measurement-lens taxonomy)

1. **The daily chip is a mechanical coin at the name level.** Fire rate 21.1% vs null
   22.9%; next-day persistence 28.3% vs null 22.4%; mean run 1.35 vs 1.26. Detectably
   ≠ null in aggregate, but the margin is thin: a TRUE today tells you almost nothing
   about tomorrow, and ~23% of covered name-days would display a TRUE forever.
2. **No construction can extract name-level crowding information from this store
   today.** Daily rr is ~memoryless (median lag-1 AC −0.01): the 25Δ snapshot as
   collected (tenor-mean across a varying tenor set, young strike grids) is noise-
   dominated at daily frequency. This is an **estimator-quality** finding about the
   store, not a mechanism finding: skew-richness ↔ crowding remains untested, neither
   supported nor killed here.
3. **The only decisively supra-null structure is cross-name co-firing.** Breadth SD
   runs 2–7× the independent-names null; on 2026-07-14 (day-mean rr +0.026) 37–40% of
   all names fired simultaneously. The chip as built responds to *market-wide* skew
   days, not name-level crowding — the wrong granularity for a per-name state gate,
   where it mass-injects same-day votes.
4. **PERSIST is a shape fix, not an information fix — stated plainly.** Its state-like
   behavior (P(T|T)=61%, runs 2.2 sessions) sits at the edge of its own mechanical
   null (57%, runs 1.95) — it manufactures coherent, rarer episodes from window
   overlap; it does not discover a regime the data can't yet show. What it buys, all
   mechanical but all real: duty cycle 23%→11% at activation (→6–8% mature vs 20–24%
   forever); single-day market spikes can't flip it (needs 3 of 5); episodes are
   coherent instead of scattered.
5. **What PERSIST does *not* buy — also stated plainly.** Under the state machine's
   ENTER_N=2 hysteresis, the rate of ≥2-consecutive-TRUE episodes *rises* slightly
   (SELF 6.0% vs PERSIST 8.5% of name-days, each ≈ its own null): longer runs offset
   the lower rate. The gate-level protection is the halved standing TRUE-vote mass in
   a fixed-k gate and the damped co-firing, not the hysteresis pathway.
6. **LOO alone is immaterial** (all stats within noise of SELF). Self-inclusion is a
   hygiene defect, worth removing in passing — it is not the story. The review's
   "exclude today" candidate is subsumed: the new benchmark excludes the entire
   evaluation window.
7. **One-day cross-chip lift is unmeasurable at this n** (radar 2026-07-29:
   P(skew TRUE | ≥1 other chip TRUE) = 3/15 vs 11/89 unconditional — direction up,
   n hopeless). Recorded for the re-benchmark, not leaned on.

## 3. Ruling LRV-R6 — construction amendment (pre-registered)

**The chip stays in the gate** (house law: a factor that is not standalone evidence is
retained as a confluence input; the k-of-n with `n_avail` null semantics is the
sanctioned confluence machine; removal would be a membership adjudication this
measurement does not justify — the mechanism is untested, not refuted).

**Construction, effective before mass activation:**

- Input series: session-true daily rr per name (requires #3977's `session_rows`
  filter — this amendment lands **on top of** #3977, never before it).
- Benchmark: `rr_80th_pctile` = Q80 of prior history **excluding the last 5 observed
  sessions**; non-null only when that prior history has **≥21 real sessions** (the
  LRV-R1(c) frozen floor, now applied to the benchmark sample alone — first possible
  non-null at n≥26, ~2026-08-06 for the 343-name cohort).
- Fire condition: `skew_rich_last5` = count of the last 5 observed sessions with
  rr ≥ benchmark; chip TRUE iff count ≥ 3 (`CROWDED_SKEW_PERSIST_MIN=3` of
  `CROWDED_SKEW_PERSIST_WINDOW=5`, frozen in the engine).
- Null semantics unchanged: ineligible → None → drops out of `n_avail` (the permitted
  de-escalation direction; verified sane in #3977's review).
- Display: `rr_25d` (latest) and `rr_80th_pctile` (frozen benchmark) move to the row
  context next to `skew_n_obs` and `skew_rich_last5`; the engine no longer carries
  fields nothing reads. Surface copy ("call-skew richness" / 看涨偏斜过高) already
  describes the meaning, not the formula — no copy change.

**Why 3-of-5, stated before outcomes exist:** 5 sessions = one trading week, the
smallest window that reads as "held", matching CROWDED's state semantics (a condition
that *holds*, like `basket_corr_rising`'s level-plus-change, not a day print); k=3 is
the majority of that week. Null math above; nothing was fit to observed flips (there
are none to fit — zero states change today under any construction).

**What stays open (accrual, not authority):** the information question — does
persistent skew-richness co-time with genuine crowding? — is unmeasurable until the
store matures. Re-benchmark clock: **n≥60 real sessions (~mid-Oct 2026)**, rerun this
script + the cross-chip lift with real n, alongside the store's existing
`validation_gate.json` (return-IC lane, separate question, still
`insufficient_history`). Follow-up worth its own lane: the loader's tenor-mean mixes a
varying tenor set day to day — a candidate driver of the AC≈0 measurement noise;
fixing extraction could make a future upgrade *measurable*.

**Registry note:** membership did not change; no DO_NOT_REBUILD row. The amendment is
recorded as LRV-R6 in `research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md` §7, the stale
"display-only" claim in `config/synapse.yml`'s LRV-W1 note is corrected (the chip is a
state-gate input — #3977's review established this), and the OIP masterplan's
"auto-activates" line is updated to the new construction and date.
