# Prophet US Conditional Fusion — PR-2: C2, redundancy, and the incremental question

**Program:** `research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md` (§5.3 redundancy
prereg, §8.1 C2 row + complexity-ladder law, §8.5 data depth, §8.7 power, §9 validation,
§10.6 anti-double-count, §14 row PR-2).
**Machine table:** `research/prophet_fusion/pr2_c2/report.json`
(`schema: prophet_fusion.pr2_c2.v1`).
**Runner:** `python3 -m scripts.prophet_fusion_c2 --out research/prophet_fusion/pr2_c2`
**Suite:** `tests/test_prophet_fusion_c2.py`

> Every number below is a descriptive, in-sample read of a frozen counterfactual-replay
> frame. The inferential C2 fit and the cross-fitted incremental estimates are REFUSED
> on this frame (§6, §8). Nothing here is promotion-bearing.

`counterfactual_replay: true` · `non_promotion_bearing: true` · frame-2 survivorship
labels carried (reconstructed curated universe; `price_basis` pooled by explicit flag —
exploratory, promotion-barred) · `horizons_available: [5, 10, 21]` · authority stanza
all-false.

Nothing here ranks, sizes, gates, originates a signal, or escalates. `us_prophet_v2`
remains the deployed champion; `engine/` is untouched by this PR.

---

## §0 What to read first, in one paragraph

W2 asked: after controlling for what Prophet already knows, which evidence families add
incremental information, how redundant are they, and is there enough lawful data to
estimate those contributions at all? **The lawful answer to the third question is NO for
any fitted read — and that refusal is the wave's central result.** The frozen §9.2 fold
law needs ≥60 training and ≥10 test dates after purge and embargo; the graded frame
still holds 24 dates (none of them prophet-scored), so the harness refuses the C2 fit
and the cross-fitted incremental estimates outright, and **91 graded dates (67 more than
we hold) are needed before the first lawful fold exists** — a number derived by running
the fold builder itself, not asserted. What W2 could lawfully establish, it did: an
estimability census over all 8 families × 55 registry members on both frames (3
families / 4 members are fit-eligible today); the first measured redundancy matrices
(within-F2 dependence `alpha×off_high` mean ρ **+0.436**; cross-family |ρ| ≤ 0.25 — the
C1 voters are not siblings of each other); permutation-calibrated conditional-MI reads
(F2's H=10 excess +0.0050 bits at one-sided p 0.058, everything else smaller; H=21
refuses at 7 dates); and the first governed family-grain "what does X add?" table with
BH-FDR — in which, under the t-referenced instrument the independent adversarial review
forced (§12, F-1), **no family survives**: the table has ZERO rejections; **F5
FLOW-POSITIONING is the nearest miss** (partial ρ|G0 +0.074, p_t 0.027, p_adj 0.080),
and its serving-lawful decomposition (+0.052, CI covering zero) is printed beside the
verdict because the shipped score leans on a serving-dead member (§12, F-2). F2's
negative edge-leg read lands `null_unresolved` (p_t 0.056, p_adj 0.083). The
variance-floor law registered by the coverage-floor DSC is now in `families.yml` and
measured: `news_burst` reads vote-inert on this frame (variation share 0.333), which
retroactively explains its exactly-zero LOFO in PR-1b.

---

## §1 The frames

**Frame 2 (raced by PR-1b, measured here): the graded-board frame.** Unchanged since
the race — `retro_grades.parquet`, 24 dates 2026-06-15→07-31, 2,251 (date, ticker)
pairs, H ∈ {5, 10, 21} with 42/63 at zero rows; two legacy selection regimes inside the
window; the live `us_prophet_v1/v2` regime has no graded rows here. All PR-1b frame
receipts carry forward (era boundaries, price-basis pooling tag, store/ledger delta).

**Frame 1 (coverage/redundancy exhibits only): the candidates store.** Five stamps
(07-31, 08-05/06/07, 08-12 scan-heal); the only board-adjacent cross-section is the
2026-08-07 curated stamp (1,717 rows). Read PER STAMP, never pooled across the
universe-widening break. The grades sibling (`data/us_prophet_rank/grades/`) is still
absent, and the report prints the loader's refusal as a receipt rather than working
around it silently.

Frames are never pooled with each other.

## §2 Registry repairs landed in this PR (and what did NOT change)

1. **`short_interest` `pit_status`: `snapshot_not_pit` → `pit_settlement` — with
   backtest admission DEFERRED.** #5602's merged fix is real:
   `context_api._short_int_dim` resolves historical query dates against the
   history+panel union gated on `knowable_date`, basis `pit_settlement`; current dates
   keep the snapshot path. The registry now records that mechanism truthfully. But the
   adversarial review (§12, F-5) measured that on every frame this repo can build,
   `knowable_date` is itself DERIVED — `settlement_date + 10 CALENDAR days` — and 10
   calendar days under-waits the "~8 sessions" FINRA publication lag by 2–3 days on all
   three committed settlements. An under-waiting derived lag manufactures look-ahead at
   exactly the publication boundary, so `pit_settlement` is **NOT** in the arena's
   `BACKTEST_LAWFUL_STATUSES`: a `short_int__*` column still refuses in any backtest
   frame, deliberately, until the owning lane reconciles the constant (8 business
   sessions, or `max(derived, capture_date)` — the history store's real `capture_date`
   is currently unused; reconciliation chipped to the owning lane). The registry note
   carries the full receipt, and the two admission tests are written to flip the day
   the reconciliation lands. Depth (3 settlements) and basis-mixing caveats bind
   regardless. No frame in this PR consumes a `short_int__*` column.
2. **The variance-floor law** (`semantics.variance_floor` + `variance_floor_spec`):
   the registered resolution of `DSC:COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE`.
   Defined on features alone — no outcome enters the rule: a member is VOTE-INERT on a
   frame when fewer than 50% of frame dates carry ≥2 distinct non-null oriented values
   (null-semantics-aware: for a `measured_negative` member whose negatives are
   null-encoded, the null state counts as one distinct value — the general law as
   registered, §12 F-9). Inert members stay in every census and redundancy table
   (disclosed, never hidden) but carry no vote and enter no fitted design matrix. Both
   falsifier halves are suite-pinned. The floor value is read from the registry at run
   time (mutation-tested), never hard-coded. The threshold's lever arm on multiplicity
   is disclosed in §7's sensitivity block (§12, F-3). The as-of-night form required for
   any PROSPECTIVE lane is explicitly UNIMPLEMENTED as of PR-2 and carried to PR-3
   (§12, F-11).
3. **`sue_z` re-home DEFERRED with its reason recorded**: the PR-1a telemetry columns
   enter the candidates store by forward schema union and no post-#5604 nightly had
   stamped as of this PR — claiming the column now would be a phantom.

**Not changed:** the PR-1b report and doc; O1–O6; G0/G0′/G1/G2/G3/G4; the primary
tuple; the presence floors themselves; C1's registered construction (the F8 floor gap
is resolved by the GENERAL law above, not by hand-tuning C1); the meaning of
`counterfactual_replay`.

## §3 Estimability census (all 8 families, both frames)

Fit-eligibility on frame 2, decided mechanically by the registry + the census (every
exclusion named, several reasons per member where they stack):

| Family | Fit-eligible members | Why the rest are out |
|---|---|---|
| F1 TECHNICAL-CONFLUENCE | — | `tier_cascade` below the 0.50 presence floor (0.250; measured serve-side 0.080) |
| F2 MOMENTUM-EXTENSION | `alpha`, `off_high` | — |
| F3 THEME-STRUCTURE | — | absent from frame (the frozen payload carries no theme/basket/relay evidence column) |
| F4 CATALYST-EVENT | `sue_fresh` | other members unwired or absent |
| F5 FLOW-POSITIONING | `smartmoney_add` | `insider_cluster` **serving_dead** (C1-raced / C2-fit-excluded — the panel collector stopped at 2026q1); `gex_confirm_verdict` below presence floor (0.209) AND vote-inert |
| F6 MACRO-REGIME | — | structurally excluded (`cross_sectional: false` — row-constant per night, by design; more data does not fix this) |
| F7 QUALITY-FUNDAMENTAL | — | absent from frame; `forensics` additionally `snapshot_not_pit` |
| F8 ATTENTION-CROWDING | — | `news_burst` **vote-inert**: variation share 0.333 < 0.50 — measured by the new law, not asserted |

Variance-axis receipts (share of frame dates carrying ≥2 distinct non-null oriented
values): `alpha`/`off_high` 1.000 · `insider_cluster` 0.708 · `sue_fresh`/
`smartmoney_add` 0.583 · **`news_burst` 0.333** — the DSC's own motivating case is the
first thing the law catches, and F8's exactly-zero LOFO delta in PR-1b (§9.2 there) is
now explained by a registered, feature-only rule rather than by a post-hoc note.

Train-vs-serve: the ratio compares RAW non-null coverage on both sides, only over
columns present on both sides, with the semantic figure printed beside it (§12, F-10 —
like with like). The ledger chips' candidates-store telemetry columns were unstamped as
of this PR, so their serve coverage reads `not_yet_measurable` — disclosed, and the
exclusion rule fires only on MEASURED skew. The census is the first artifact that flips
when the post-PR-1a telemetry begins stamping.

## §4 Redundancy matrices (§5.3, first measurements)

**Within-family (frame 2, oriented percentiles, date-blocked):**

| Pair | mean ρ | 95% CI | n dates | note |
|---|---|---|---|---|
| F2 `alpha` × `off_high` | **+0.436** | [+0.392, +0.481] | 24 | the two F2 votes share ~44% of their ordering — one family budget is the right budget |
| F5 `insider_cluster` × `smartmoney_add` | −0.075 | [−0.098, −0.049] | 14 | near-independent, slightly opposed — F5's two threads are not one member in two hats (PR-1b §9.5 agrees) |
| F5 `gex_confirm_verdict` × `insider_cluster` | −0.106 | [−0.171, −0.034] | 6 | thin; gex vote-inert on this frame |
| F5 `gex_confirm_verdict` × `smartmoney_add` | +0.020 | [−0.118, +0.145] | 7 | thin; unreadable |

**Cross-family (frame 2, family scores):** |ρ| ≤ 0.25 everywhere (F2×F4 +0.245 is the
largest; F2×F5 −0.130). The C1 voters are not correlated siblings of one another — the
load-bearing redundancy in the estate remains WITHIN F2, exactly as the registry's
documented-edge priors say.

**Frame 1 (2026-08-07 curated cross-section, single-date tier, no CI):** within-family
blocks over registry-homed numeric columns; F6 skipped as structurally excluded
(row-constant — within-date ρ undefined); plain categoricals listed as not measurable.
Where a measured column belongs to a member that is not backtest-lawful (short
interest, forensics), the block says so (`members_measured_but_not_backtest_lawful` +
a PIT disclosure string) — a measured redundancy cell is a structural fact about the
store, never an admission. Scan-tier stamps ride as secondary exhibits,
tier-disclosed, never mixed with curated.

**The registry's `known_redundancy_edges`, re-measured as promised:** 7 of 8 edges are
**NOT_MEASURABLE today**, each named with its missing side (`composite_momentum_leg`,
`total_return_z`, `blowoff_risk`, the insider chip surfaces, the theme producer
surfaces, `cycle_ladder`, the options internals — all unwired); the 8th (the hub-leg
row whose second side is written as the range "F1..F4") is marked
`unresolvable_pair_spec` — a range in member-key position can never resolve to a
member, so that row needs a registry re-spec, not wiring. The asserted priors
(ρ=0.984 momentum-leg duplication, etc.) therefore REMAIN ASSERTIONS with receipts,
not measurements; the table exists so the next wiring wave flips resolvable rows from
refusal to measurement instead of re-litigating prose.

## §5 Conditional mutual information (family grain)

Registered estimator (echoed in `registered.cmi_estimator`): within-date percentiles →
fixed tercile bins; Z = the G0 champion replay (the same `rung_g0` machinery PR-1b
validated byte-exact); Y = excess>0; date-equal weights; plug-in CMI in bits,
calibrated against B=500 within-(date×Z-bin) permutations, seed 20260818, one-sided
p = (1 + #{null ≥ observed}) / (B + 1); refusal below 300 rows / 8 dates / any empty
Z-bin.

| Family | H=5 excess bits (p) | H=10 excess bits (p) | H=21 |
|---|---|---|---|
| F2 | +0.0035 (0.060) | **+0.0050 (0.058)** | NOT_ESTIMABLE (7 dates < 8) |
| F4 | −0.0002 (0.469) | +0.0007 (0.234) | NOT_ESTIMABLE |
| F5 | −0.0004 (0.545) | +0.0012 (0.192) | NOT_ESTIMABLE |

Reading: no family's information excess clears its permutation null on this depth; F2
is nearest at both short horizons (0.058–0.060) — directionally consistent with F2
carrying the largest |partial ρ| in §6 (CMI is unsigned; it cannot see that F2's
relationship is negative). H=21 refusing at 7 dates is the estimator working, not a
gap. This table is machine-checked against `report.json` by the suite (§12, F-4 — the
first draft of this section hand-transcribed three cells wrongly; the pin exists so
that class of error cannot ship again).

## §6 The incremental-vs-Prophet harness, and its refusal

The registered incremental comparison is CROSS-FITTED residualization against the G0
champion replay (masterplan §10.6): per fold, an OLS residualizer (outcome percentile ~
a + b·G0 percentile) is fitted on train dates only, frozen (params + sha256 fingerprint,
`FoldNormalizer`-style), and applied to test dates; family scores are then correlated
with the residuals out-of-fold. On this frame:

> `fold 0 refused (§9.2 minimum-usable-fold): 0 train dates after purge+embargo
> (minimum 60) and 4 test dates (minimum 10), at horizon=21 embargo=21 over 24
> distinct dates. The harness refuses the fold; it never silently shrinks one.`

Usable folds: **0**. The inferential tier is `refused_no_lawful_folds` for every
family. The machinery is proven end-to-end on synthetic depth instead (§8): the
residualizer's fingerprint does not move when test-fold outcomes are mutated, a planted
incremental family is recovered with its CI excluding zero, and a pure-noise family's
CI covers zero.

**Descriptive tier (in-sample, the PR-1b §9.4 construction extended — suite-pinned
against PR-1b's committed `report.json` itself at abs 5e-4, no hand-typed literals):**
per family × horizon, plain ρ and partial ρ | G0 with date-blocked bootstrap CIs
(B=2000, seed 20260814). **P-value instrument (§12, F-1):** every cell prints BOTH the
t-referenced p (df = n_dates − 1; the verdict-bearing reference at these block counts)
and the normal-approximation p (PR-1b §8.2 continuity); the review measured that the
normal reference had been deciding the table's only rejection, and the correction
changed the rejection count from 1 to 0 — stated plainly here and in the artifact's
`p_method`, not waved away. **Registered descriptive minimum (§12, F-7):**
`DESCRIPTIVE_MIN_DATES = 8` (equal to the CMI minimum) — a descriptive cell below it is
NOT_ESTIMABLE with its counts, which removes the entire H=21 secondary table (7/7/4
blocks) rather than publishing p-values an adjacent estimator refuses at the same
depth.

## §7 The governed "what does X add?" table (H=10, BH-FDR at family grain)

Multiplicity registered BEFORE outcomes: n_tests = **3** — the count of families
carrying a score-eligible member, derived from the feature-side census alone (F8 fell
out on the variance axis; the sensitivity block below bounds the m=4 question). BH-FDR
α=0.05 on **p_t**; H=5 carries its own separately-bookkept secondary table (3 tests, 0
rejections); H=21's secondary table is empty by the §6 depth minimum.

| Family | Verdict | partial ρ&#124;G0 | 95% CI | p_t / p_normal / p_adj | n dates |
|---|---|---|---|---|---|
| F1 | `insufficient_coverage` | — | — | — | 0 |
| F2 | `null_unresolved` | −0.083 | [−0.154, −0.007] | 0.056 / 0.037 / 0.083 | 15 |
| F3 | `insufficient_coverage` | — | — | — | 0 |
| F4 | `null_unresolved` | +0.012 | [−0.049, +0.066] | 0.708 / 0.701 / 0.708 | 12 |
| F5 | **`null_unresolved`** | +0.074 | [+0.017, +0.130] | **0.027** / 0.013 / **0.080** | 15 |
| F6 | `not_estimable` (structural) | — | — | — | 0 |
| F7 | `insufficient_coverage` | — | — | — | 0 |
| F8 | `not_estimable` (vote-inert) | — | — | — | 0 |

**Zero rejections.** Under the t-referenced instrument, no family's incremental read
survives family-grain BH-FDR on this depth.

**F5 is the nearest miss, and its row carries the decomposition that matters
forward (§12, F-2):** the score-membership construction above (+0.074, p_t 0.027)
includes `insider_cluster`, whose collector stopped at 2026q1 — the family's evidence
as it existed HISTORICALLY on this frame, which is the registered descriptive
question. The SERVING-LAWFUL construction (`design_membership_effect`:
`smartmoney_add` alone) reads **+0.052, CI [−0.003, +0.111], 12 dates, p_t 0.106** —
a CI covering zero before any adjustment. A forward-looking reader (PR-3's prereg)
should reason from the serving-lawful number; the historical one is real but not
reproducible at serving time until the insider collector heals.

**F2's cell:** the CI excludes zero on the negative side — the same shape PR-1b's
exploratory §9.4 published — but p_t 0.056 / p_adj 0.083 does not survive, and the
governed verdict is `null_unresolved`. There is no contradiction with PR-1b: that
table was exploratory and unadjusted by prereg; this one is the registered
family-grain instrument. The edge-leg question stays OPEN, its adjudication
prospective (the PR-1b shadow-race prereg), exactly where the PR-1b Adjudication left
it.

**Sensitivity (the F-3 disclosure):** with the vote-inert member retained
(`requested_n_tests: 4`), the frame supplies only 3 tests — F8's own partial-ρ cell is
NOT_ESTIMABLE at 6 date-blocks < 8, so the depth minimum excludes it independently of
the variance floor. Bounding F8's hypothetical p at both extremes (0 and 1), **no real
family rejects at either extreme** — the table's zero-rejection state does not depend
on the variance-floor threshold, whose 0.50 mirrors the registered presence floor and
was not tuned.

## §8 C2 — the machinery, its refusal, and what would have entered

Registered model classes: `elastic_net_logistic_nonneg` (P(excess>0)) and
`elastic_net_linear_nonneg` (excess magnitude), both at family grain — one evidence
column per eligible family (the within-date member-percentile mean of oriented
members), one first-class missingness indicator per family, an intercept, and nothing
else. Evidence coefficients carry the elastic-net penalty under a **w ≥ 0 bound** (the
governed-direction monotonic sign law: a family may be shrunk to zero, never re-pointed
against its filed direction by outcome data — on the feasible set the L1 term is
linear, so scipy L-BFGS-B from a zero init is exact and RNG-free); missingness
coefficients carry ridge only; the intercept is free. Grid: α ∈ {0.01, 0.1, 1.0} ×
l1_ratio ∈ {0.0, 0.5, 1.0} (size 9, registered), inner selection on the last 20% of
train dates (date-contiguous, horizon-embargoed, refusing when it cannot be cut), ties
to the LARGEST α then l1_ratio — simpler wins ties, by law. The ordinal head of §8.1's
class description is DEFERRED this wave with its reason on record: no governed ordinal
implementation exists in the dependency set, and adding one for a fit the fold law
refuses anyway is complexity the ladder has not earned.

On the real frame the fit path calls the fold builder FIRST and stops:
`c2_fit.status = refused_no_lawful_folds`, the same verbatim refusal as §6, **zero
fitted coefficients anywhere in the artifact** (suite-asserted: no
coefficients/theta/chosen/heads key exists), and the `would_have_entered` receipt: 3
families (F2: alpha+off_high; F4: sue_fresh; F5: smartmoney_add), 3 evidence columns +
3 missingness columns + intercept = 7 parameters. **There is no in-sample fallback fit
in the module** — an in-sample C2 leaderboard entry is precisely the weakened result
the commissioning forbids, and the absence of the path is itself suite-pinned.

**Complexity-ladder disposition: C2 earns nothing this wave.** No lawful fitted read
exists, so no C2-vs-C1 comparison was run on real data (the machinery for that
comparison runs in the synthetic selftest only, labeled as machinery proof). C1 as
raced remains the standing simple rung; the ladder question re-opens when the fold law
is satisfiable.

## §9 Power / distance-to-power

- **Fold law:** need 91 graded dates for the first lawful fold (60 train + 10 test +
  21 embargo, derived by searching `arena.build_folds` itself so purge/test-size rules
  cannot drift from the number) — hold 24, **67 more needed**; ~3.2 months of nightly
  accrual as arithmetic, not a calendar promise. Prophet-scored graded dates: **0**
  (the champion has still never been graded — §6.1 of the masterplan; first H=10
  maturation ~2026-08-24).
- **Descriptive/CMI minimums:** 8 date-blocks (both tiers, registered); H=21 holds 7
  and refuses across the board.
- **MDE:** the frame's measured minimum detectable ΔP@5 remains **~17.4pp** (PR-1b §10,
  inherited — no rung is raced here) against a +3pp registered increment. Every
  descriptive effect in §7 sits far inside that band's noise floor; and the three
  F5 statistics sometimes cited together (its partial ρ here, PR-1b's LOFO +2.7pp,
  PR-1b's partial CI) are three views of ONE score on ONE 15-date window, not
  independent corroboration — the LOFO magnitude is ~6× below the frame's own minimum
  readable ΔP@5 (§12, F-12).
- The registered `written_before_outcomes` power block byte-precedes every outcome
  section, as in PR-1b.

## §10 What this PR does NOT answer

1. **Whether C2 beats C1** — refused, not measured. Nothing here licenses "fitting
   helps" or "fitting doesn't help".
2. **Whether any family's incremental read survives out-of-sample** — every measured
   cell is descriptive, in-sample, replay-frame, and NONE survives the governed
   instrument even in-sample; the prospective shadow race (PR-3, prereg'd in the
   PR-1b Adjudication) is the first honest test.
3. **Anything era-transported** — the PR-1b two-regime warning stands unchanged; today's
   live regime is in no cell of this frame, and W2 adds no new era evidence.
4. **Anything at H=42/63** (zero rows), anything class-conditional (cohort columns
   still null), anything about insider evidence (collector still stopped at 2026q1),
   anything about serving-time chip behavior until the telemetry columns stamp.
5. **The known-edges priors** — 7 of 8 unmeasured for want of wired second sides; the
   8th needs a registry re-spec (§4).
6. **Short-interest evidence at any tier** — the `pit_settlement` mechanism is real
   but backtest admission is deferred on the knowable-lag reconciliation (§2).

## §11 Reproducing this

```
python3 -m scripts.prophet_fusion_c2 --out research/prophet_fusion/pr2_c2
python3 -m scripts.prophet_fusion_c2 --selftest
python3 -m pytest tests/test_prophet_fusion_c2.py tests/test_prophet_fusion_families.py \
                  tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py \
                  tests/test_prophet_fusion_race.py -q
```

`report.json` carries no wall-clock stamp; runs are byte-identical (pinned by suite;
verified independently by the commissioning session). Seeds: bootstrap 20260814
(B=2000), CMI permutation 20260818 (B=500); the C2 path itself is RNG-free. Real-frame
runtime ≈ 4 seconds. Suite: 73 tests (this module) + 182 (siblings) = 255 across the
fusion CI step.

## §12 Adversarial review disposition (commissioning §18)

Independent opus review over the full branch diff, 2026-08-14. Verdict:
**SHIP-WITH-FIXES** — machinery clean (leakage seams, family budget, residualizer
freeze, determinism, live-path fence all verified with receipts); the defects were in
the inferential claims and the shipped prose. Every BLOCKER/MAJOR was reproduced
before it was fixed; every fix re-verified; mutation receipts (g)/(h) added for the
two blockers.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| F-1 | BLOCKER | The normal-approximation p decided the table's only rejection and the shipped `p_method` string denied it | FIXED: t reference (df=n−1) is the verdict-bearing instrument; both p's printed in every cell; rejection count changed 1→0 and the artifact says so; small-n guard raised to the registered minimum; mutation receipt (g) |
| F-2 | BLOCKER | F5's published effect leaned on the serving-dead insider_cluster; "smartmoney-carried" was refuted by the decomposition | FIXED: `design_membership_effect` (serving-lawful, +0.052, CI covers 0) printed beside the verdict; doc rewritten; mutation receipt (h) |
| F-3 | MAJOR | Variance-floor threshold set in the same PR as the table it flips; consequence undisclosed | FIXED: §7 sensitivity block bounds the m=4 variant at both extremes — zero rejections either way; "not tuned" stated with its basis |
| F-4 | MAJOR | Doc's CMI H=5 p-column was mis-transcribed (three wrong cells) | FIXED: cells corrected from the artifact; doc table now machine-checked by suite |
| F-5 | MAJOR | "Never a derived statutory lag" was false — knowable_date is derived at settlement+10 CALENDAR days, 2–3 days short of the 8-session publication lag | FIXED fail-closed: `pit_settlement` removed from `BACKTEST_LAWFUL_STATUSES`; registry note rewritten with the receipt; admission tests flip on reconciliation; engine-side constant chipped to the owning lane |
| F-6 | MAJOR | No workstream handoff in the PR | FIXED: same-day handoff amended in place (this PR) |
| F-7 | MAJOR | H=21 descriptive p-values published from 4–7 blocks while CMI refuses at 7 | FIXED: `DESCRIPTIVE_MIN_DATES = 8` registered; H=21 secondary table now refuses with counts |
| F-8 | ADVISORY | PR-1b parity test used hand-typed literals; doc overstated its tolerance | FIXED: test reads PR-1b's committed report.json, abs 5e-4, every shared family |
| F-9 | ADVISORY | Variance axis ignored `null_semantics` generality | FIXED: null-encoded measured-negative state counts as a distinct value; both member shapes suite-pinned |
| F-10 | ADVISORY | Train/serve ratio compared semantic train vs raw serve | FIXED: raw-vs-raw ratio; semantic figure beside |
| F-11 | ADVISORY | Registry stated an as-of-night property the harness does not implement | FIXED: registry tense corrected — unimplemented as of PR-2, carried to PR-3 |
| F-12 | ADVISORY | "Consistent across three constructions" framed three statistics of one score as corroboration | FIXED: §9 restates them as three views of one score; the LOFO magnitude placed against the frame's own MDE |
| nits | — | CMI p +1/(B+1); requirements/CI comment accuracy; the F1..F4 range edge can never resolve | ALL FIXED (`unresolvable_pair_spec` for the range row) |

Attacked and clean, per the review's own receipts: leakage seams (4 `assert_no_outcomes`
gates, within-date-only transforms, frozen residualizer), family-budget enforcement,
determinism (byte-identity across repeated runs), the live-Prophet fence (zero
references to any fusion module from engine/, app/, admin/, or workflows), and
REGISTERED_SIGNS provenance (no sign minted in this PR).

---

## Adjudication (main loop)

Written by the commissioning session after independently re-running the CLI (byte
parity with the committed artifact confirmed), re-running the suites, reviewing the
harness's load-bearing paths, and adjudicating the adversarial review's findings.
Bounded by: every cell is descriptive, in-sample, on a survivorship-flagged
counterfactual replay whose measured MDE (~17.4pp) dwarfs the registered increment,
with the live regime in no cell.

**1. Is there enough lawful data to estimate family contributions?** For any FITTED or
cross-fitted read: **no** — 0 usable folds, 67 more graded dates needed, and the
refusal is the correct output, not a shortfall of the wave. For the descriptive
estimability/redundancy plane: yes, and that plane is what accrual-era decisions
actually need — it says which families are even measurable, which was the
commissioning's first question.

**2. Which families add incremental information after Prophet conditioning
(descriptive tier)?** Under the governed instrument: **none survives** — the table has
zero rejections at every horizon it can read. The nearest miss is F5 FLOW-POSITIONING
(+0.074 partial ρ|G0, p_t 0.027, p_adj 0.080), whose serving-lawful decomposition
(+0.052, CI covering zero, p_t 0.106) is the number a forward-looking reader should
reason from — the stronger historical read leans on the serving-dead insider member.
F2's negative edge-leg read (CI excluding zero, p_adj 0.083) stays `null_unresolved`:
the honest tightening of PR-1b's exploratory read, not a reversal. The instrument
change that produced this state was forced by the adversarial review against the
draft's own arithmetic (§12, F-1) and moves in the conservative direction; the draft's
one-rejection table is superseded and does not exist in any committed artifact.

**3. How redundant are the families with one another?** The measured answer matches
the registry's priors in shape: cross-family |ρ| ≤ 0.25 (breadth, where it exists, is
real breadth), while the load-bearing redundancy is WITHIN F2 (+0.436 alpha×off_high).
F5's two threads are near-independent (−0.075). 7 of 8 registered known-edges remain
unmeasurable with named missing sides; the 8th needs a registry re-spec.

**4. The C1-weights question C2 inherited:** unanswered by law (no lawful fit), and
the `would_have_entered` receipt shows how thin the question currently is — 3 families,
7 parameters. Equal-weight C1 remains the standing simple rung; nothing was learned
that perturbs it.

**5. What W2 changes about the program's posture:** (a) the variance-floor law closes
the presence/variance gap generally — future family votes cannot silently carry dead
voters, and its multiplicity lever is disclosed, not latent; (b) the census +
train/serve machinery turns "can this family be trusted at serving time" into a
computed artifact that flips automatically when the PR-1a telemetry stamps; (c) the
fold-law arithmetic (67 more dates) gives the program its honest clock — the C2
leaderboard conversation has a date, and it is not soon; (d) the p-instrument episode
is now part of the program's method record: at 12–15 date-blocks the normal
approximation is not a neutral convenience, and the governed tables carry both
references from here on.

**Recommendation for W3 (PR-3, the nightly shadow-scoring wave):** proceed EXACTLY on
the PR-1b Adjudication's prereg — G3, G4, C1-as-raced, C1−F2 vs G0/G0′, zero authority,
prereg before the first stamped night. Nothing in W2 perturbs that registration; W2
registers NO new rung (a C2 shadow entry would be a fitted rung with no lawful fit —
it stays out), and W2's zero-rejection table adds no basis for touching the C1
membership. Carry into PR-3's design: as-of-night floor evaluation on BOTH axes
(presence and variance — the whole-frame look-ahead lesson applies to the new axis
identically, and the as-of-night form is explicitly unimplemented as of this PR); the
t-referenced p instrument for any table the lane grades; and the §13.0 closure
verification as a precondition for trusting any context-vector-fed telemetry.

*Return packet to Sol rides in the PR body and the workstream handoff; stop-after-W2
per the commissioning.*
