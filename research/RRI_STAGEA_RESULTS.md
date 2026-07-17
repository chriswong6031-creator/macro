# RRI Stage-A Replay Results — reported against the frozen preregs (PR #2725)

**Run: 2026-07-17 · `scripts/rri_stage_a.py` · perms=2000 · seed=20260717 · artifact
`data/risk_radar_intl/rri_study_results.json`.** This doc reports against
[RRI_CRASH_ANTIFIRE_PROGRAM.md](RRI_CRASH_ANTIFIRE_PROGRAM.md) and the S1–S3 preregs without
rewriting them (dated-append idiom for any later restatement). Store data through 2026-07-16
(gb/ez 07-15) — **the motivating 07-17 crash contributes zero graded outcomes** (the 07-13→16
trigger days are h21-immature and excluded from both observed and null sides; they mature
~2026-08-14 in the shadow logs).

## Verdicts (family `rri_2026h2`, 8 cells)

**No cell earned GO. Three ACCRUE, five NO-GO, zero KILL** (no Wilson-UB-below-null anywhere,
so no DO_NOT_REBUILD rows are triggered).

| cell | clusters | rate | null mean | ratio | Wilson-LB (bar =1.25×null) | p | BH | era | split | breadth | budget | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s1_any88 (P1) | 354 | .427 | .409 | 1.04 | .384 (.512) | .233 | ✗ | ✗ (post16 0.99) | ✗ | ✓ | ✓ | **NO-GO** |
| s1_exfx88 | 293 | .451 | .418 | 1.08 | .403 (.522) | .131 | ✗ | ✓ | ✓ | ✗ | ✓ | **NO-GO** |
| s1_any95 | 243 | .449 | .382 | 1.18 | .397 (.477) | .011 | ✓ | ✓ | ✓ | ✓ | ✓ | **ACCRUE** |
| s1_exfx95 | 212 | .420 | .382 | 1.10 | .365 (.477) | .131 | ✗ | ✓ | ✓ | ✗ | ✓ | **NO-GO** |
| s2_gate_conditional (P1) | 90 | .333 | .328 | 1.02 | .258 (.410) | .492 | ✗ | ✓ | ✓ | ✗ | ✓ | **NO-GO** |
| s2_always | 74 | .324 | .320 | 1.01 | .242 (.400) | .520 | ✗ | ✗ | ✓ | ✗ | ✓ | **NO-GO** |
| s3_ret10 (P1) | 372 | .406 | .341 | 1.19 | .365 (.427) | .0125 | ✓ | ✓ | ✓ | ✓ | ✓ (1.76pp) | **ACCRUE** |
| s3_ret21 | 294 | .418 | .370 | 1.13 | .372 (.462) | .049 | ✗ | ✓ | ✗ | ✓ | ✓ | **ACCRUE** |

ACCRUE per grammar §6's letter: right sign with Wilson-LB in [1.0×, 1.25×) of the null mean —
real directional signal that did not clear the pre-committed lift bar.

## S1 — leg-floor escalation: the primary is dead; only the @0.95 variant survives as ACCRUE

The ratified primary (any leg ≥0.88) fails exactly where it matters: **post-2016 era ratio
0.99** — over the last decade the floor's added alert-days hit at chance. The quiet-legs veto
was information; flooring on the published leg band destroys it at 0.88. At 0.95 the picture
turns (ratio 1.18, p=0.011, era/split/breadth all pass, added days 5.97pp pooled) but the
Wilson-LB (.397) sits under the 1.25× bar (.477). Receipt: KR itself — the motivating
market — carries per-market ratio **0.87** at 0.95; the cell's lift lives in in/ez/jp/gb, not
Korea. Nulls printed, not hidden.
Episode receipt (reported, not gated): flooring captures far more R-B episodes than the
incumbent (554 vs 149 at 0.88; 394 vs 149 at 0.95; incumbent-only 0) with median latency
diff 0.0 — the floor buys episode *coverage*, and Stage-A prices that coverage: at 0.88 it
is chance; at 0.95 it carries the ACCRUE-level lift above.

## S2 — two-sided FX: an honest null; the anti-fire "fix" carries no information

Gained-alert days hit at **chance** (ratio 1.02 / 1.01), and the do-no-harm receipt is
damning in the right way: lost-alert clusters hit at .365 vs gained .333 — the variant trades
better alerts for worse ones. Episode capture rose (178 vs 149 of 1,037 R-B episodes) but the
additions are chance-level. Per prereg §5: **the incumbent one-sided depreciation leg
stands**; the two-sided read may ship as a Tier-2 display receipt only. Not a KILL (UB > null
mean): safe-haven FX dislocation is *uninformative* here, not anti-signal.

## S3 — drawdown velocity: the continuation claim is real-but-under-bar; the latency claim failed

s3_ret10 is the strongest cell in the family (ratio 1.19, p=0.0125, all robustness gates
pass, budget trivially cheap at 1.76pp added loud-days) yet stays honest ACCRUE: LB .365 vs
bar .427. Two pre-registered sub-results matter for any future promotion:

- **Redundancy vs extension** (the REJECT-REDUNDANT fence): right-signed on the
  extension-quiet sub-sample (326 clusters, ratio 1.14) but LB .346 < the 1.10× bar (.377) —
  per prereg §2 this alone caps the cell at ACCRUE. Spearman ρ(velocity, extension) =
  −0.23…−0.31 per market (anti-correlated — the legs read opposite phases of the same tape).
- **H2 latency FAILED flat**: median latency improvement = 0.0 sessions in every market
  (n=1,037 episodes). At weight 0.6 inside a re-percentiled blend, the velocity leg almost
  never moves the loud-tier crossing day. The day-one-escalation motivation is NOT delivered
  by this construction; a floor/override construction would be a NEW prereg, not a re-scan.
- Whipsaw receipt: 52.7% (pre-2016) / 64.0% (post-2016) of trigger clusters closed ABOVE the
  trigger close at h21 — fast falls usually bounce by month-end even while the ≥5%-further-dd
  rate stays lifted within the window. Both facts printed.

## Implementation choices (disclosed; two honest implementers should now converge)

Outcome estimator mirrors `risk_radar_intl_audit._grade_entry` (base = as-of close, window =
next 21 rows, immature days excluded both sides). Era/split gates re-run the full machinery
(masks, outcomes, shifts) on the sub-window; <3 pooled clusters ⇒ SPARSE ⇒ cap ACCRUE (no
cell hit this). p = raw fraction of perms ≥ observed. S2 trough = min close in
[onset, onset+63], de-escalation censored at 63. R-B as frozen re-arms every 21 sessions
inside a sustained bear, so episode counts are generous (81–294 per market) — it is the
frozen ruler, used for capture/latency receipts only. Substrate self-checks: the script's
blend reproduces `composite_series` bit-for-bit and the fx stitch matches the engine sub-leg
(hard asserts).

## What happens next (per grammar §6 — no new decisions invented here)

- **ACCRUE cells (s1_any95, s3_ret10, s3_ret21) → Stage-B shadow accrual, no promotion
  clock**: nightly shadow states + `<mkt>_forward_log_<variant>.jsonl` (lane-gated), re-graded
  when the forward log matures. Any future promotion must re-clear the full gate set at
  maturity — including S3's redundancy gate and a latency story that H2 just refuted.
- **NO-GO cells park, printed** (S1@0.88 arm, S2 both): incumbent constructions stand; no
  registry rows (NO-GO ≠ KILL — construction-specific nulls, search space open).
- The live radar is untouched, `prob_cal` stays flat-at-base, cn/hk/ca stay byte-frozen.
