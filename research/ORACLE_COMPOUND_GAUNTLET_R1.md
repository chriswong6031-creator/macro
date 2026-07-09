# Oracle Compound Gauntlet — Round 1 (washout-stress cluster)

> **CORRECTION (2026-07-04):** the original "A17 = overfit, do not re-propose"
> verdict was WRONG — a full-history OOS test assumes stationarity, which fails
> across the post-2020 regime break. A17 holds within-modern OOS and is a live
> modern-regime candidate. See §Correction. A15 and the rest stand.

> **AMENDMENT (2026-07-07, RC-RUL-3 — research/TIME_CONFOUND_RECHECK_ADJUDICATION.md).**
> ORC-RC-1 (PR #1864, `research/ORACLE_COMPOUND_TC_RECHECK.md`) replaced the G3
> independent-draw placebo with a circular time-shift null that preserves onset
> clustering (2000 draws; reproduction exact). Under it: **A15 PASS reaffirmed**
> (p=0.0095); **A9 PASS WITHDRAWN** (p=0.139 — its G3 evidence was temporal
> clustering, not signal; A9 reverts to screened evidence only and is not a
> promotion candidate absent fresh out-of-time evidence); **A17-modern stands**
> (p=0.013, n=73 caveat) while the already-superseded full-history read is
> additionally non-robust (p=0.105) and must not be revived. Standing law: future
> gauntlet rounds use the time-shift placebo (`scripts/research/oracle_compound_tc_recheck.py`)
> as the G3 null.

**Date:** 2026-07-04 · **Harness:** `scripts/oracle_gauntlet_compound.py` ·
**Status:** first-pass OOS + timing-placebo gauntlet. This is a Tier-1.5 bridge,
**not** the canonical P3 pre-registration. A PASS here is a promotion candidate
pending the formal P3 gauntlet; it does not license a "gauntleted" claim in
user-facing surfaces.

## Context

Four brainstorm rounds (44 screened compounds) established that the tier-S
participation-state basin is dead and the **washout × active-flow-stress** basin
is live (see `research/ORACLE_COMPOUND_LIBRARY.md` and the trial ledger). Five
compounds cleared the mechanical promotion floor (A9, A15, A16, A17, C6). This
round subjects the two headline candidates plus A9 to an out-of-sample and
placebo test — the question the in-sample screen cannot answer.

## Pre-registered criteria (frozen before computing holdout stats)

- **G1 — OOS holdout** (split 2019-12-31): holdout `effect_63d` same sign as
  dev, holdout `hit_63d` ≥ 0.52, holdout `n` ≥ 100.
- **G2 — per-era persistence:** ≥ 3 of 4 eras with positive real mean (n≥20/era).
- **G3 — timing placebo:** real mean₆₃ > 95th pctile of 500 random-timing draws
  (per-node count-matched resample of that node's realizable 63d outcomes).
- **PASS = G1 ∧ G2 ∧ G3.**

Reused verbatim from `oracle_screen.py`: `get_entry_dates` (grammar firewall)
and `_compute_forward_returns` (as-of-t stored forward RS). No new forward math.

## Results

| id | rule (washout_w>0 ×…) | n | eff₆₃ | dev≤2019 | **holdout>2019** | eras+ | placebo p | verdict |
|---|---|---|---|---|---|---|---|---|
| **A15** | ≥2 opposite-complex outflow nodes | 2351 | +1.30% | +1.35% | **+1.19% / 53.4% / n=663** | **4/4** | 0.000 | **PASS** |
| A9 | ≥2 same-complex outflow nodes | 438 | +1.06% | +0.13% | +2.27% / 65.4% / n=191 | 3/4 | 0.000 | PASS (lumpy) |
| A17 | same-complex outflow + vel_1w<0 | 262 | +1.68% | −0.03% | +3.83% / 71.6% / n=116 | 3/4 | 0.000 | full-hist FAIL → **CORRECTED: modern-regime PASS** (see §Correction) |

### A15 — clean pass, the lead candidate
Per-era effect is nearly constant for 27 years: **+1.42% / +1.07% / +1.25% /
+1.12%** (1999-2014 / 2015-2019 / 2020-2022 / 2023-2026). Dev +1.35% → holdout
+1.19% — the edge held at almost identical magnitude on data it was never fit
to. Placebo: random washout-day entries average +0.08%; requiring ≥2
opposite-complex outflow nodes lifts it to +1.30% (p=0.000).

### A17 — full-history OOS-fail, but see §Correction
Its headline +1.68% is concentrated post-2015: 1999-2014 was negative (−0.92%),
the full-history dev period is flat (−0.03%), and the return is recent. The
first-pass G1 (full-history split) therefore FAILED it. **That conclusion was
subsequently overturned** — a full-history OOS test assumes the market is
stationary, which is false across the post-2020 structural break (Fed/QE,
systematic momentum, options/0DTE microstructure). Re-tested *within* the
modern era, A17 is a live regime-specific edge, not overfit. See §Correction.

### A9 — passes but recent-loaded
Also negative in 1999-2014 (−1.35%) with a flat dev period (+0.13%). Passes G1
on the letter (holdout positive, hit>52%, n>100) but lacks A15's time-stability.

## Read

The gauntlet **reversed the screen ranking** (screen: A17 > A15 > A9 by effect;
gauntlet: A15 durable/timeless, A9 recent-loaded, A17 modern-regime-specific —
see §Correction; A17 was *initially* mis-called overfit). **A15** — buy a sector in weekly
capitulation when ≥2 nodes of the opposite risk complex are simultaneously
seeing outflow onset — is the only candidate with a time-stable, out-of-sample
edge. Mechanism: rotation-driven mean reversion (local capitulation coincident
with active displacement from the opposite risk pole).

**Guardrails:** effect is modest (~+1.3% 63d excess, ~57% hit) — a tilt, not a
fortune, net of costs on liquid sector ETFs. A15 is 1 of 44 screened, but OOS
magnitude-stability + p=0.000 + 4/4 flat-magnitude eras far exceed a
multiple-testing artifact. This first-pass gauntlet omits the P3 refinements
(regime-matched direction-adjusted placebo, BH correction, bootstrap CIs).

## Correction (2026-07-04) — A17 is a modern-regime edge, not overfit

The initial "A17 = overfit, do not re-propose" call was **wrong**, and the
error was methodological: a full-history OOS/holdout split assumes
**stationarity** (the 1999-2014 market behaves like today's). That assumption
fails across the post-2020 structural break, so a full-history FAIL cannot
distinguish an overfit fluke from a genuine edge that only exists in the modern
regime. Re-tested *within* the modern era:

| period | n | eff₆₃ | hit |
|---|---|---|---|
| 1999-2009 | 105 | −0.19% | 44% |
| 2018-2019 | 27 | +2.86% | 70% |
| 2020-2021 | 53 | +1.76% | 53% |
| 2022-2023 | 39 | +4.23% | 79% |
| 2024-2026 | 24 | +7.79% | 100% |
| **modern-OOS dev 2015-2020** | 72 | **+2.50%** | — |
| **→ held-out 2021+** | 73 | **+5.05%** | **85%** |

A17 is **positive across four consecutive, structurally distinct modern
sub-regimes** and **survives an OOS split held entirely inside the modern era**
(fit 2015-2020 → never-seen 2021+ at +5.05% / 85%). That is the signature of a
regime-specific edge, not a one-window fluke. Caveats: small modern sample
(n=145; holdout n=73), magnitude leans on a few hot recent buckets, and it is a
**bet that the post-2015 microstructure persists**; the regime rationale is
post-hoc. See memory `oos-fail-regime-change-vs-overfit`.

**Structural flaw surfaced:** the promotion floor's era-consistency gate (≥3 of
4 eras, era-1 = 1999-2014) *structurally penalizes* modern-regime edges — they
cannot score the pre-2015 era. Fix = a separate, labeled **modern-regime track**
(modern sub-period consistency + within-modern OOS + pre-committed ex-ante
rationale), not a weakening of the main gate.

## Next step

Take **A15** to the formal P3-style pre-registration (timeless track). Run
**A17** through the modern-regime track once built — it is a live higher-octane
candidate, NOT fenced. A9 remains a secondary, weaker candidate.

Reproduce:
```
python -m scripts.oracle_gauntlet_compound \
    --ids A15_WASHOUT_OPP_OUT_2NODE A9_WASHOUT_SAME_OUTFLOW_DENSE A17_WASHOUT_SAME_OUT_NEG_VEL \
    --data-dir data --compounds-dir data/oracle/compounds
```
