# CCW Study S1 — Results (against the frozen prereg)

**Run date:** 2026-07-15. **Ruler:** `CCW_STUDY_S1_PREREG.md` (frozen 2026-07-15 before
any edge was computed — unchanged; this doc reports against it and never rewrites it).
**Artifact:** `data/corp_bonds/study_s1.json` (`scripts/ccw_study_s1.py`, seed 20260715).
**Review:** Opus adversarial stats review (2026-07-15) — verdict defensible, three honesty
obligations enforced below. **Authority:** display/context. Nothing here promotes, ranks,
gates, or sizes.

---

## Verdict (per the frozen §8 rubric): **LEADS — with material caveats**

The frozen rubric passes: H1's effect is negative (deeper forward drawdowns after
velocity spikes) and sign-stable across all three eras. But the honest reading is narrower
than the word "leads" suggests, and the three disclosures below are part of the verdict,
not footnotes.

### The frozen H1 result (as-run, preserved verbatim)

> On broad HY OAS, 1996-2026: trading days with 21-day spread-velocity in the **top 15%
> of the trailing decade** were followed by a mean **63-day S&P 500 drawdown of −7.6%**,
> vs a **−5.2%** unconditional base rate — **2.5 percentage points deeper**
> (n = 1,076 flagged days; one-sided permutation p = **0.0145**).

The effect direction matches the field-guide prior (credit stress leads equity drawdowns;
GZ 2012, Blanco et al 2005). Now the three things that make "leads" an overstatement if
read alone:

## Disclosure 1 — significance is real but marginal under the strictest honest null

The frozen run's permutation null was implemented as a **whole-series circular shift** of
the condition labels, not the block permutation the prereg §5 named (an implementation
bug, caught in review). This matters for provenance but **not for the conclusion**, because
the shift null was the *more conservative* of the family — every correctly-specified null
gives an equal-or-smaller p:

| Null (all time-preserving, house-law compliant) | H1 p |
|---|---|
| Whole-series shift (as-run, frozen headline) | **0.0145** |
| True circular block permutation, block=63 | 0.014 |
| …block=126 | 0.014 |
| …block=252 | 0.030 |
| **Episode-label permutation (gap>90d; the strictest, house-preferred)** | **0.0505** |

Under episode permutation — which treats each of the **~26 distinct macro episodes** as
the unit, the correct effective sample size — the result sits **right at the 0.05 line**.
The headline p=0.0145 is preserved as the frozen as-run number (per no-goalpost-moving
law); the honest summary is: *significant under block nulls, borderline under the
episode null, and everything rests on ~26 episodes, not 1,076 independent days.*

## Disclosure 2 — the edge is crisis-weighted and fades to ~zero in the modern era

Δ (conditional-minus-base 63-day drawdown), by pre-declared era:

| Era | Δ (drawdown gap) | flagged n | per-era p |
|---|---|---|---|
| pre-2010 (dot-com + GFC) | **−3.3pp** | 570 | 0.092 |
| 2010-2020 (QE + COVID) | −1.5pp | 318 | 0.164 |
| 2021→ (hiking + AI cycle) | **−0.9pp** | 188 | 0.145 |

Sign-stable (so the frozen rubric passes), but **monotonically attenuating**, and **no
single era is independently significant** — full-sample significance is assembled from
era-insignificant pieces. It is not *solely* a 2008/2020 artifact — with GFC **and** COVID
windows removed the effect survives (Δ −1.6pp, p 0.020) — but it roughly **halves**, and
the 2021→ leg (−0.9pp) is not distinguishable from zero. A user should not expect the
2008-magnitude version of this signal in today's regime.

## Disclosure 3 — it confirms stress usually already visible; it is not a clean early lead

At the moment the signal fires, equity stress is overwhelmingly **already underway**:

- **84.9%** of flagged days are already falling over the trailing 21 days (base rate 37%).
- Mean trailing-21-day SPX return on flagged days: **−4.9%** (vs +0.7% unconditional).
- Skip the first 21 forward days (measure drawdown over [t+22, t+63]): Δ still −1.8pp
  (p 0.026) — so it is not *only* immediate continuation, but a meaningful part of the
  raw edge is the selloff already in progress.

The decisive test that it is **not pure continuation**: restrict to flagged days where SPX
was **still rising** over the trailing 21 days (n = 162 — cases where continuation is
definitionally impossible). Those days were followed by a 63-day SPX **return of −1.6%**
vs a **+2.2%** unconditional base. When the velocity signal fires *before* price turns,
genuine forward underperformance follows. So the signal carries real forward content — it
just usually arrives after the market has started moving.

## Secondary cells (exploratory — not the gate)

Directionally consistent with H1: on IG OAS, velocity spikes precede deeper SPX drawdowns
at h=21 (Δ −1.6pp, p 0.007) and h=126 (Δ −4.0pp, p 0.024). Rising velocity percentile
also precedes **further spread widening** (positive rank-IC on the widening-continuation
cells, once the tail direction is read correctly). Moody's Baa−Aaa (deep 1986→) is
directionally aligned but weaker (marginal). All exploratory, no multiple-testing
correction claimed, reported for completeness.

## What this sets on the desk (the honest caveat copy)

The credit desk's velocity-read caveat is set from this study (fields
`desk_caveat_en`/`desk_caveat_zh` in `study_s1.json`; a W-later surface hook consumes them):

> **EN:** "When company-bond stress velocity spikes, deeper stock drawdowns have usually
> followed — but on most past spikes the sell-off was already underway. Treat it as
> confirmation, not an early all-clear."
> **ZH:** 当公司债压力的变化速度骤升时，股市随后往往出现更深的回撤——但历史上多数此类骤升发生时抛售已经开始。视其为确认信号，而非提前预警。

## Method-of-record notes (for the next prereg, not a goalpost move)

- The frozen rubric's **sign-stability** era bar was too weak — it passed a signal that is
  individually insignificant in every era and ~0 in the modern one. A future prereg should
  require either per-era significance or a minimum modern-era effect size.
- The frozen headline used the whole-series-shift null by implementation accident. Fixed in
  the script (`_perm_true_circular_block`); the whole-series function is retained so the
  frozen H1 stays reproducible. Future studies use the true block/episode null by default.
- Effective N ≈ 26 episodes should have been the pre-registered sample-size framing from
  the start; `cond_n=1076` overstates independence.

## Deferred (unchanged from prereg §10)

S1b (rating-ladder CCC−BB lead/lag) — ladder history ~2023→ only; gated on TRACE backfill
(not free-tier) or ~2028-H1 accrual. S2 (theme dispersion → widening) and S3 (issuer
momentum vs equity drawdown) — accrual-gated; theme series began 2026-07.

### Status log

- 2026-07-15 — S1 run against the frozen prereg. Verdict LEADS (frozen rubric) with the
  three disclosures above enforced as part of the verdict. Opus stats review: no
  look-ahead (independently verified); null bug caught (conservative, disclosed);
  continuation confound quantified (real forward content in the clean-lead subset).
