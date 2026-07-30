# call_skew_rich construction reassessment — measurement of record (2026-07-29/30)

**Question.** `call_skew_rich` (chip 6 of the 7-chip CROWDED k-of-n state gate,
`CROWDED_K_OF_N=3`, `engine/leader_lifecycle.py`) fires when the latest 25Δ rr proxy
(`atm_call_iv − otm_put_iv`) is ≥ the name's own 80th percentile — computed by
`scripts/build_leader_radar.py:_load_options_skew` as `daily.quantile(0.80)` over the
name's **entire accrued history including today** (self-inclusive), gated on ≥21
observations. PR #3977's adversarial review measured 62 TRUE / 350 evaluated (17.7%) on
the weekend-padded store, and #3977's session-true counting puts ~343 names one session
from activation (n=21 real sessions ~2026-07-30). Should the construction change before
mass activation, and does the chip stay in the gate?

**Verdict (LRV-R6): retained in the set, construction replaced, and the VOTE IS HELD.**
The chip keeps its membership in the CROWDED 7-chip set; the daily self-inclusive form
is replaced by a persistence construction (≥3 of the last 5 observed sessions above the
Q80 of ≥21 prior real *readings*, evaluation window excluded); and the chip is
**pinned to `None` — it does not vote** — until a pre-registered re-benchmark at n≥60
real sessions (~mid-Oct 2026) shows the construction separating from its within-name
permutation null. Engine constant `CROWDED_SKEW_CHIP_ARMED = False` carries the hold;
the count accrues in the row context meanwhile, and `n_avail` handles the null natively.

Reproduction: `python3 research/leader_radar_skew_chip/measure_call_skew_chip.py`
(seeded, no network; writes `measurement_results.json`). Every number below is emitted
by that script from the raw parquet; an independent Opus reviewer re-derived the
headline figures with its own code (agreement noted per row in §4).

---

## 1. What was measured

Store: `data/options_skew/snapshots.parquet` as of 2026-07-29 — 28 distinct dates,
8 non-session (verified), 20 real sessions 2026-06-22 → 07-29; 343 of 401 names have
all 20. The #3977 review number replicates **exactly: 62/350 = 17.71%**.

**Constructions compared** (day-by-day, expanding history, session-true rows;
measurement-lane relaxation `min_obs=10`, labeled — production stays 21):
`SELF` (today ≥ Q80 incl. today — the shipped form), `LOO` (excl. today),
`PERSIST` (≥3 of last 5 ≥ Q80 of history excl. those 5).

**Mechanical null rates** (iid, N=200k, pandas linear-interp quantile; at n=21 the Q80
of 21 points is exactly the 17th order statistic, so SELF's null is P(rank ≥ 17) = 5/21):

| n_total | SELF | LOO | PERSIST 3-of-5 |
|---|---|---|---|
| 21 | 23.8% | 22.8% | 11.4% |
| **26 (production activation)** | **23.1%** | **22.2%** | **10.2%** |
| 40 | 20.0% | 21.4% | 8.3% |

PERSIST's null is far above the naive Bin(5, 0.2)≥3 = 5.8%: a noisy young-n threshold
moves all five window comparisons together, and a single new observation re-judges the
whole window. It decays toward ~6–8% only as history matures well past n=40.

**Observed vs within-name permutation null** (200 reps; permutation kills temporal order
and cross-name day alignment, preserves each name's marginal distribution):

| statistic | SELF obs | SELF null (sd) | LOO obs | LOO null (sd) | PERSIST obs | PERSIST null (sd) |
|---|---|---|---|---|---|---|
| fire rate | 0.211 | 0.229 (.008) | 0.219 | 0.238 (.007) | 0.138 | 0.126 (.012) |
| P(TRUE\|TRUE yesterday) | 0.283 | 0.224 (.016) | 0.288 | 0.235 (.015) | 0.613 | 0.573 (.032) |
| mean TRUE-run (sessions) | 1.35 | 1.26 (.02) | 1.35 | 1.27 (.02) | 2.19 | 1.95 (.10) |
| breadth SD across days | 0.057 | 0.030 (.006) | 0.062 | 0.022 (.005) | 0.038 | 0.016 (.006) |

Observed/null breadth-SD ratios: **SELF 1.88×, LOO 2.79×, PERSIST 2.41×** — supra-null,
and the largest departure of any statistic here, but the two rows are on **different eval
grids** and are not comparable to each other (see §2.3).

**Run statistics with honest denominators** (the hysteresis pathways —
`HYSTERESIS_ENTER_N=2`, `HYSTERESIS_EXIT_N=3`):

| | SELF | PERSIST | change |
|---|---|---|---|
| P(2 consecutive TRUE), per adjacent pair | 6.08% | 9.03% | **+49%** |
| P(3 consecutive TRUE), per adjacent triple | 2.19% | 5.76% | **+163%** |
| share of TRUE runs lasting ≥3 sessions | 8.0% | 32.6% | **+308%** |

**Underlying series:** per-name lag-1 autocorrelation of daily rr — **median −0.01**
(IQR −0.14…+0.17, 350 names). Day-factor share of rr variance: 3.9%. Q80 instability:
median |Q80(first 10) − Q80(all 20)| = 0.19 of the name's rr IQR (p90 0.58); 6.4% of
names would flip today's decision on the window choice alone.

**(k, m) grid** (context; the pair considered was (3,5) — recorded so the record shows
the neighbourhood rather than a single point): null@n26 / observed —
(2,3) 13.8/16.1 · (3,3) 1.4/3.7 · (2,5) 32.2/31.5 · **(3,5) 10.1/13.8** · (4,5) 2.0/4.7.
Every cell sits at or near its own null; none of them is an information finding.

**Day-1 forecast:** 17.5% of the 343-name cohort (~60 names) would fire TRUE on
activation day under SELF. Radar boundary: 11 rows carry exactly 2 TRUE non-skew chips;
8 have no skew coverage and the 3 covered ones (PYPL, ROST, WDAY) fire under **no**
construction — **zero state flips today under any option**, and zero CROWDED rows exist
on the current artifact.

---

## 2. What the numbers mean

1. **The daily chip is a mechanical coin at the name level.** Fire 21.1% vs null 22.9%;
   next-day persistence 28.3% vs 22.4%; run 1.35 vs 1.26. Detectably ≠ null in aggregate,
   but ~23% of covered name-days would carry a standing TRUE forever.
2. **No construction extracts name-level information from this store today.** Daily rr is
   ~memoryless (median lag-1 AC −0.01). This is an **estimator-quality** finding about the
   store — the 25Δ snapshot as collected (tenor-mean over a varying tenor set, young
   strike grids) is noise-dominated at daily frequency. The skew-richness ↔ crowding
   *mechanism* remains untested: neither supported nor killed.
3. **The one decisively supra-null structure is cross-name co-firing, and the persistence
   form does not damp it — it stretches it.** On the common eval grid (t=14–19) PERSIST's
   breadth SD is **0.0380 vs SELF's 0.0144** — 2.6× *larger*, the opposite of the naive
   read off the §1 table (whose rows sit on different grids: SELF's includes the
   2026-07-14 market-wide spike, PERSIST's does not — a grid confound, corrected here).
   With PERSIST's history floor relaxed to 8 so the spike day is evaluable:

   | session index | 12 (07-14) | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
   |---|---|---|---|---|---|---|---|---|
   | SELF breadth | **0.371** | 0.209 | 0.157 | 0.197 | 0.171 | 0.193 | 0.193 | 0.175 |
   | PERSIST breadth | 0.231 | 0.220 | 0.180 | 0.186 | 0.160 | 0.101 | 0.107 | 0.096 |

   PERSIST cuts the peak (37%→23%) but holds the board elevated for five sessions,
   collapsing at t=17 exactly when 07-14 leaves the window. A one-day spike cannot
   satisfy `ENTER_N=2`; a five-session plateau supplies four consecutive confirmation
   windows at 16–23% board-wide. That is worse, not better.
4. **The persistence form makes noise more state-effective on both hysteresis paths.**
   Pairs +49%, triples +163%, long runs +308% (table above). CROWDED becomes easier to
   enter *and* materially harder to exit (`EXIT_N=3`). The lower daily marginal rate
   (21.1%→13.8%, and the observed 13.8% is above its own 12.6% permutation null and its
   10.2% iid null) is the wrong quantity to reassure with: a fixed-k gate behind 2-of-2
   entry and 3-of-3 exit integrates multi-session co-occurrence, and every multi-session
   statistic moved the wrong way.
5. **Therefore the construction change alone does not make the chip safe to vote.**
   PERSIST is the better *shape* (rarer, coherent episodes; a single market spike can't
   flip it), and it is the right thing to have in place when evidence arrives — but on
   this store it converts a scattered coin into a sticky one, and stickiness is what a
   state gate integrates.
6. **LOO alone is immaterial** (22.8% vs 23.8% null; all observed stats within noise of
   SELF). Self-inclusion is a hygiene defect worth removing in passing, not the story.
7. **Cross-chip lift is unmeasurable at this n** (radar 2026-07-29: P(skew TRUE | ≥1 other
   chip TRUE) = 3/15 vs 11/89 unconditional — direction up, n hopeless). Recorded for the
   re-benchmark, not leaned on.

## 3. Ruling LRV-R6

**(a) Membership: retained.** House law keeps a non-standalone factor as a confluence
input; the mechanism is untested, not refuted, and the store is 20 sessions old with a
credible extraction defect behind the AC≈0.

**(b) Vote: HELD at `None`.** Retention does not compel a vote, and the two are separate
decisions. On this store the chip's only supra-null structure is a *market-wide* factor —
a market dummy inside a per-name k-of-n does not "confirm other signals when they align";
it aligns with the tape — and §2.3–2.4 show the persistence form amplifies exactly the
multi-session co-firing a state gate integrates. Holding costs nothing: `_is_null` drops
the chip from `n_avail` (verified sane in #3977's review), the count keeps accruing in the
row context, and every downstream surface already reads correctly under a null chip.
`CROWDED_SKEW_CHIP_ARMED = False` (engine, frozen) carries the hold.

**(c) Construction, in place and tested behind the hold:**

- Session-true daily series (requires #3977's `session_rows` filter — carried in this PR).
- Series is `dropna()`'d **before** the gate and the quantile: `min_obs` counts real
  readings, not frame rows (a NaN-bearing history otherwise passes a gate reporting 21 on
  a benchmark estimated from a handful of points — the vacuous-N-gate class).
- Benchmark: Q80 of prior history excluding the last 5 observed sessions, ≥21 readings →
  first eligibility at n≥26.
- Count: `skew_rich_last5` = sessions in that window ≥ benchmark; the engine's fire rule
  is `≥ CROWDED_SKEW_PERSIST_MIN (3)` of `CROWDED_SKEW_PERSIST_WINDOW (5)`, gated by
  `CROWDED_SKEW_CHIP_ARMED`.
- `rr_25d` (latest reading) and `rr_80th_pctile` (window-excluded benchmark) ship as row
  context receipts. They are **not** a pairwise chip read — the chip is the count.

**(d) Arming condition, pre-registered now.** At **n≥60 real sessions (~mid-Oct 2026)**
rerun this battery. Arm only if, at that n: (i) PERSIST's fire rate separates from its
within-name permutation null beyond ±2sd; (ii) the common-grid breadth SD is no larger
than SELF's — i.e. the co-firing amplification in §2.3 has not persisted; and (iii) the
cross-chip lift is estimable and non-negative. Otherwise extend the hold or retire the
construction. Arming is a one-line constant flip plus a masterplan ruling row.

**On parameters:** (3,5) was chosen from state semantics (5 sessions = one trading week;
k = its majority) and null math, and nothing here was fit to outcomes — no outcome data
exists (`validation_gate.json` is `insufficient_history`) and zero states flip at land
time. The §1 (k,m) grid is published so the record shows the neighbourhood; every cell
sits at its own null, which is the point — no (k,m) rescues this store, which is why the
vote is held rather than re-parameterized.

**Open, not scheduled:** the loader's tenor-mean mixes a varying tenor set day to day — a
credible driver of the AC≈0 and the first thing to fix if a future upgrade is to be
*measurable*. Also noted: the 5-session window is positional (last 5 *observed* rows), so
for a sparsely covered name it can span more calendar sessions than a week (today: 2 of
375 names; WBS spans 13) — acceptable while the chip is held, revisit at arming.

**Registry:** membership unchanged → no DO_NOT_REBUILD row. Recorded as LRV-R6 in
`research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md` §7; the stale "display-only" claim in
`config/synapse.yml`'s LRV-W1 note is corrected (the chip is a state-gate input — #3977's
review established this, and the hold is what keeps that authority unexercised); the OIP
masterplan §5.5 line is updated.

## 4. Review record (2026-07-30)

An independent Opus reviewer re-derived from the raw parquet and matched exactly: the
padded replication (62/350 = 17.71%), the store shape (28 dates / 8 non-session / 20
sessions / 343 names at 20), the median lag-1 AC (−0.0105, IQR [−0.1424, +0.1739]), the
padded-store LRV-R6 counterfactual (344 non-null, 49 TRUE), the day-1 forecast (60/343),
the iid nulls (own RNG, within MC error), the exact 5/21 order-statistic argument, and the
radar boundary census (11 rows, none skew-TRUE; 0 CROWDED rows).

Three findings from that review changed this document and the ruling, and all three
reproduce in the amended battery:

1. **Grid confound in the breadth comparison** — v1 read PERSIST's 0.038 against SELF's
   0.057 across different eval grids and concluded "damped co-firing". On the common grid
   the comparison **reverses** (0.0380 vs 0.0144). §2.3 now carries the corrected result
   and the footprint table. This retired the "damped co-firing" claim.
2. **"breadth SD 2–7× null" was unbacked** — the actual observed/null ratios are
   1.88 / 2.79 / 2.41. Corrected in §1.
3. **The `EXIT_N=3` pathway was never computed** — v1 reported only the ≥2-consecutive
   move. Triples rise +163% and long runs +308% (§1, §2.4). This is what turned the
   verdict from "ship the construction" into "ship it held".

Also fixed from that review: the `min_obs`-counts-rows-not-readings defect (§3c, a live
vacuous-gate bug that would also have written a bare `NaN` token into `radar.json`), a
missing builder→engine wire test, a missing fail-open tripwire on the session filter, and
the duty-cycle figures (§1 now quotes nulls as nulls and the observed 13.8% as observed).
The reviewer's remaining note — that retention law and voting are separate decisions and
the hold option was never priced — is the substance of §3(b).
