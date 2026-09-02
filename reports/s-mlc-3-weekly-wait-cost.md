# S-MLC-3 — Weekly-Wait Entry Cost on Leaders · Phase-0 Results

**Pre-registration:** `research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md` (frozen 2026-07-16)
**Harness:** `scripts/s_mlc_3_weekly_wait_cost.py`

## VERDICT: Outcome A — COST-IS-REAL

Mean 21d SPY-excess cost of the wait construction vs. immediate entry (pooled, δ=0 primary): **0.309%** (HAC t=6.256, month-block permutation p=0.0000, n=617).

> **CAUTION — verdict is NOT robust to a genuine pre-reg ambiguity.** Prereg SS1.5's raw formula compares the Friday close to close[s,t] (event day); the freeze record (Ruling 3) and the machine-checkable frontmatter both instead say 'weekly close >= entry close' (t+1). This harness uses entry_close (t+1) as PRIMARY; event_close (t) is reported here for transparency because it moves the pooled 21d mean cost across the 0.3% magnitude floor. Primary (entry_close, t+1) mean = 0.309%; alternate (event_close, t, literal SS1.5 formula) mean = 0.296%. The alternate reading does NOT clear the 0.3% magnitude floor. This fork should be adjudicated before any Outcome-A leaders-exception pre-reg is authored on this result.

## Sample

- Raw non-overlapping leader-at-high events (all horizons/deltas): 620
- Effective-N floor (>=100): MET
- Primary cell (21d, δ=0) usable N after right-censoring: 617

## Gates table (§2.2)

| Gate | Result | Pass? |
|---|---|---|
| Permutation p (within-month, two-sided) | 0.0000 | YES |
| HAC \|t\| >= 2.0 | 6.256 | YES |
| Era-split same sign | pre2010=0.0022256108582080847, post2010=0.0034415245721372708 | YES |
| Episode-first-month blocking, same sign as pooled | block=0.0025874233650362084 | YES |
| BH-FDR (12-cell matrix, alpha=0.10), primary cell survives | q=0.0 | YES |
| Split-half sign-stability | half1=0.0029860356081435383, half2=0.0031957890162758033 | YES |
| Magnitude floor (>= 0.3% at 21d) | 0.309% | YES |
| Confirm-miss rate (context, not a gate) | 0.465 | n/a |

## Era split (§2.2 DT-R16 mandatory)

| Era | n | mean cost | HAC t |
|---|---|---|---|
| pre2010 | 178 | 0.0022256108582080847 | 2.153 |
| post2010 | 439 | 0.0034415245721372708 | 6.018 |

## Descriptive horizon ladder (10d/21d/40d/63d, pooled, δ=0)

**Verdicts at non-declared horizons are forbidden (§2.3, DO_NOT_REBUILD.md §3) — descriptive only.**

| Horizon | n | mean cost | HAC t |
|---|---|---|---|
| 10d | 619 | 0.0030424661044673143 | 6.797 |
| 21d | 617 | 0.0030907423337589966 | 6.256 |
| 40d | 615 | 0.0027336675642454364 | 3.997 |
| 63d | 612 | 0.0037004178631609326 | 4.218 |

## Robustness / sensitivities (§5 — NON-PROMOTABLE, cannot override the primary verdict)

- **rs_window_20d_sensitivity_21d_delta0**: n=690, mean=0.0029674541477473187, HAC t=4.971
- **delta_0_01_sensitivity_21d**: n=617, mean=0.0033923809480176964, HAC t=7.234
- **xlre_xlc_only_21d_delta0**: n=47, mean=0.0023728527718064473, HAC t=1.136
- **cyclicals_21d_delta0**: n=341, mean=0.0028404211993632057, HAC t=4.64
- **defensives_21d_delta0**: n=229, mean=0.0036108310509674435, HAC t=3.398
- **nonconfirm_cash_instead_of_spy_21d_delta0**: n=617, mean=0.001301950414010403, HAC t=1.624

## What this does NOT show (§6)

- Does not claim the leader-at-high filter itself generates alpha.
- Does not test RS-leadership continuation (S-MLC-1) or suction conditionality (S-MLC-2).
- A null does not validate the half-size/weekly-wait construct as optimal on other grounds (risk, psychology, drawdown-minimization).
- Uses no LLM-originated signals or verdicts at any step.
- Closes only the specific half-size/weekly-wait construction at the RS #1-2 + 52wh filter on SPDR sector ETFs — no broader entry-timing family.

