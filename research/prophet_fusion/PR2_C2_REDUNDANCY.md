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
families / 4 members are fit-eligible today); the first measured redundancy matrices (within-F2
dependence `alpha×off_high` mean ρ **+0.436**; cross-family |ρ| ≤ 0.25 — the C1 voters
are not siblings of each other); permutation-calibrated conditional-MI reads (F2's H=10
excess +0.0050 bits at one-sided p 0.056, everything else smaller; H=21 refuses at 7
dates); and the first governed family-grain "what does X add?" table with BH-FDR, in
which **F5 FLOW-POSITIONING is the sole surviving incremental-positive** (partial ρ|G0
+0.074, CI [+0.017, +0.130], p_adj 0.040) while **F2's negative read — CI excluding
zero — does NOT survive the adjustment** (p_adj 0.055 → `null_unresolved`). The
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

1. **`short_interest` `pit_status`: `snapshot_not_pit` → `pit_settlement`**, on #5602's
   merged fix: `context_api._short_int_dim` now resolves historical query dates against
   the history+panel union gated on the store's own `knowable_date` (settlement + 10
   calendar days), basis `pit_settlement`; current dates keep the snapshot path. The
   arena gains `BACKTEST_LAWFUL_STATUSES = {pit, pit_settlement}` (the producer enforces
   the §9.1 availability join itself). Two caveats bind every consumer and are pinned in
   the registry note: committed depth is **3 settlements** (first knowable 2026-07-10 —
   coverage receipts, not inference; re-run `scripts/backfill_finra_short_interest.py`
   before any deep join), and bases must never mix undisclosed. No frame in this PR
   consumes a `short_int__*` column — this is a truth repair, not a behavior change.
2. **The variance-floor law** (`semantics.variance_floor` + `variance_floor_spec`):
   the registered resolution of `DSC:COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE`.
   Defined on features alone — no outcome enters the rule: a member is VOTE-INERT on a
   frame when fewer than 50% of frame dates carry ≥2 distinct non-null oriented values.
   Inert members stay in every census and redundancy table (disclosed, never hidden)
   but carry no vote and enter no fitted design matrix. Both falsifier halves are
   suite-pinned: a news_burst-shaped near-constant reads inert; a sparse-but-VARIABLE
   synthetic member passes. The floor value is read from the registry at run time
   (mutation-tested), never hard-coded.
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
| F1 TECHNICAL-CONFLUENCE | — | `tier_cascade` below the 0.50 presence floor (0.250; measured serve-side 0.080); 9 members unwired/absent from frame |
| F2 MOMENTUM-EXTENSION | `alpha`, `off_high` | — |
| F3 THEME-STRUCTURE | — | absent from frame (the frozen payload carries no theme/basket/relay evidence column) |
| F4 CATALYST-EVENT | `sue_fresh` | other members unwired or absent |
| F5 FLOW-POSITIONING | `smartmoney_add` | `insider_cluster` **serving_dead** (C1-raced / C2-fit-excluded — the panel collector stopped at 2026q1); `gex_confirm_verdict` below presence floor (0.209) AND vote-inert (variation share low) |
| F6 MACRO-REGIME | — | structurally excluded (`cross_sectional: false` — row-constant per night, by design; more data does not fix this) |
| F7 QUALITY-FUNDAMENTAL | — | absent from frame; `forensics` additionally `snapshot_not_pit` |
| F8 ATTENTION-CROWDING | — | `news_burst` **vote-inert**: variation share 0.333 < 0.50 — measured by the new law, not asserted |

Variance-axis receipts (share of frame dates carrying ≥2 distinct non-null oriented
values): `alpha`/`off_high` 1.000 · `insider_cluster` 0.708 · `sue_fresh`/
`smartmoney_add` 0.583 · **`news_burst` 0.333** — the DSC's own motivating case is the
first thing the law catches, and F8's exactly-zero LOFO delta in PR-1b (§9.2 there) is
now explained by a registered, feature-only rule rather than by a post-hoc note.

Train-vs-serve: measured only where both sides carry the columns (see §8 note on the
false-exclusion trap this avoids). The ledger chips' candidates-store telemetry columns
were unstamped as of this PR, so their serve coverage reads `not_yet_measurable` —
disclosed, and the exclusion rule fires only on MEASURED skew. The census is the first
artifact that flips when the post-PR-1a telemetry begins stamping.

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
Scan-tier stamps ride as secondary exhibits, tier-disclosed, never mixed with curated.

**The registry's `known_redundancy_edges`, re-measured as promised:** all 8 edges are
**NOT_MEASURABLE today**, each named with its missing side (`composite_momentum_leg`,
`total_return_z`, `blowoff_risk`, `hub_theme_leg`, the insider chip surfaces, the theme
producer surfaces, `cycle_ladder`, the options internals — all unwired). The asserted
priors (ρ=0.984 momentum-leg duplication, etc.) therefore REMAIN ASSERTIONS with
receipts, not measurements; the table exists so the next wiring wave flips rows from
refusal to measurement instead of re-litigating prose.

## §5 Conditional mutual information (family grain)

Registered estimator (echoed in `registered.cmi_estimator`): within-date percentiles →
fixed tercile bins; Z = the G0 champion replay (the same `rung_g0` machinery PR-1b
validated byte-exact); Y = excess>0; date-equal weights; plug-in CMI in bits,
calibrated against B=500 within-(date×Z-bin) permutations, seed 20260818; refusal below
300 rows / 8 dates / any empty Z-bin.

| Family | H=5 excess bits (p) | H=10 excess bits (p) | H=21 |
|---|---|---|---|
| F2 | +0.0035 (0.13) | **+0.0050 (0.056)** | NOT_ESTIMABLE (7 dates < 8) |
| F4 | −0.0002 (0.23) | +0.0007 (0.232) | NOT_ESTIMABLE |
| F5 | −0.0004 (0.19) | +0.0012 (0.190) | NOT_ESTIMABLE |

Reading: no family's information excess clears its permutation null at conventional
thresholds on this depth; F2 is nearest (0.056) — directionally consistent with F2
carrying the largest |partial ρ| in §6 (CMI is unsigned; it cannot see that F2's
relationship is negative). H=21 refusing at 7 dates is the estimator working, not a gap.

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

**Descriptive tier (in-sample, the PR-1b §9.4 construction extended — suite-pinned to
reproduce §9.4's published numbers to 3 decimal places):** per family × horizon, plain
ρ and partial ρ | G0 with date-blocked CIs. These are the numbers the §7 table consumes,
and every cell carries `tier: descriptive_in_sample_counterfactual`.

## §7 The governed "what does X add?" table (H=10, BH-FDR at family grain)

Multiplicity registered BEFORE outcomes: n_tests = **3** — the count of families
carrying a score-eligible member, derived from the feature-side census alone (F8 fell
out on the variance axis, so the count is 3, not 4 — decided by a feature-only rule,
never by results). BH-FDR α=0.05; H=5/H=21 carry separately-bookkept secondary tables
(3 tests each, 0 rejections).

| Family | Verdict | partial ρ&#124;G0 | 95% CI | p / p_adj | n dates |
|---|---|---|---|---|---|
| F1 | `insufficient_coverage` | — | — | — | 0 |
| F2 | **`null_unresolved`** | −0.083 | [−0.154, −0.007] | 0.037 / 0.055 | 15 |
| F3 | `insufficient_coverage` | — | — | — | 0 |
| F4 | `null_unresolved` | +0.012 | [−0.049, +0.066] | 0.701 / 0.701 | 12 |
| F5 | **`incremental_positive`** | +0.074 | [+0.017, +0.130] | 0.013 / **0.040** | 15 |
| F6 | `not_estimable` (structural) | — | — | — | 0 |
| F7 | `insufficient_coverage` | — | — | — | 0 |
| F8 | `not_estimable` (vote-inert) | — | — | — | 0 |

**One rejection: F5.** The F5 signal is small (+0.074), thin (15 dates), carried by
`smartmoney_add` alone on the fit-eligible side (insider_cluster is serving-dead and
rides as a member-level sub-row), descriptive-tier, and on a replay frame — every one
of those qualifiers travels with the verdict.

**F2's verdict is the table's most instructive cell.** Its CI excludes zero on the
negative side — the same read PR-1b's exploratory §9.4 published — but the family-grain
BH adjustment lifts its p to 0.055 and the governed verdict is `null_unresolved`, not
`incremental_negative`. There is no contradiction: PR-1b's table was exploratory and
unadjusted by prereg; this table is the registered family-grain instrument, and under
it the edge-leg question stays OPEN. The four-construction convergence PR-1b reported
(G3 leads, G4 second, G1 last, F2's LOFO) remains a strengthened hypothesis whose
adjudication is prospective — exactly where the PR-1b Adjudication left it, now with
the multiplicity discipline made explicit.

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

Two census-rule clarifications landed during the build, both feature-side and both
documented in-code: the train/serve comparison uses only columns present on BOTH sides
(pooling a member's unstamped store columns into the mean had spuriously excluded
F2.residual_alpha — serve 0.930 vs train 1.000 on the column that actually trains, with
the whole-member figure still printed beside it); and verdict precedence puts
`structurally_excluded` above absence (F6's degeneracy is by design — more data does
not fix it) and the train-frame gates above the forward-looking serve skew, with every
unused reason preserved in `sub_reasons`.

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
- **CMI:** minimums 300 rows / 8 dates; H=21 holds 7 dates and refuses.
- **MDE:** the frame's measured minimum detectable ΔP@5 remains **~17.4pp** (PR-1b §10,
  inherited — no rung is raced here) against a +3pp registered increment.
- The registered `written_before_outcomes` power block byte-precedes every outcome
  section, as in PR-1b.

## §10 What this PR does NOT answer

1. **Whether C2 beats C1** — refused, not measured. Nothing here licenses "fitting
   helps" or "fitting doesn't help".
2. **Whether the F5 positive or F2 negative reads survive out-of-sample** — both are
   descriptive, in-sample, replay-frame quantities; the prospective shadow race
   (PR-3, prereg'd in the PR-1b Adjudication) is their first honest test.
3. **Anything era-transported** — the PR-1b two-regime warning stands unchanged; today's
   live regime is in no cell of this frame, and W2 adds no new era evidence.
4. **Anything at H=42/63** (zero rows), anything class-conditional (cohort columns
   still null), anything about insider evidence (collector still stopped at 2026q1),
   anything about serving-time chip behavior until the telemetry columns stamp.
5. **The known-edges priors** — all 8 remain unmeasured for want of wired second sides.

## §11 Reproducing this

```
python3 -m scripts.prophet_fusion_c2 --out research/prophet_fusion/pr2_c2
python3 -m scripts.prophet_fusion_c2 --selftest
python3 -m pytest tests/test_prophet_fusion_c2.py tests/test_prophet_fusion_families.py \
                  tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py \
                  tests/test_prophet_fusion_race.py -q
```

`report.json` carries no wall-clock stamp; two runs are byte-identical (pinned by
suite; verified independently by the commissioning session against a fresh double run).
Seeds: bootstrap 20260814 (B=2000), CMI permutation 20260818 (B=500); the C2 path
itself is RNG-free. Real-frame runtime ≈ 4 seconds.

---

## Adjudication (main loop)

Written by the commissioning session after independently re-running the CLI (byte
parity with the committed artifact confirmed), re-running the suites, and reviewing the
harness's load-bearing paths. Bounded by: every cell is descriptive, in-sample, on a
survivorship-flagged counterfactual replay whose measured MDE (~17.4pp) dwarfs the
registered increment, with the live regime in no cell.

**1. Is there enough lawful data to estimate family contributions?** For any FITTED or
cross-fitted read: **no** — 0 usable folds, 67 more graded dates needed, and the
refusal is the correct output, not a shortfall of the wave. For the descriptive
estimability/redundancy plane: yes, and that plane is what accrual-era decisions
actually need — it says which families are even measurable, which was the
commissioning's first question.

**2. Which families add incremental information after Prophet conditioning
(descriptive tier)?** One family survives the governed instrument: **F5
FLOW-POSITIONING, +0.074 partial ρ|G0, p_adj 0.040** — small, thin, smartmoney-carried,
and consistent across three constructions (PR-1b's LOFO +2.7pp, its partial CI, this
table). **F2's negative edge-leg read does not survive family-grain FDR** (p_adj
0.055) and is `null_unresolved` — the honest tightening of PR-1b's exploratory read,
not a reversal of it. F4 is flat. Everything else cannot yet be measured, each for a
named structural reason.

**3. How redundant are the families with one another?** The measured answer matches
the registry's priors in shape: cross-family |ρ| ≤ 0.25 (breadth, where it exists, is
real breadth), while the load-bearing redundancy is WITHIN F2 (+0.436 alpha×off_high).
F5's two threads are near-independent (−0.075). All 8 registered known-edges remain
unmeasurable — their second sides are unwired, which is now a wiring worklist with
named rows rather than an open question.

**4. The C1-weights question C2 inherited:** unanswered by law (no lawful fit), and
the `would_have_entered` receipt shows how thin the question currently is — 3 families,
7 parameters. Equal-weight C1 remains the standing simple rung; nothing was learned
that perturbs it.

**5. What W2 changes about the program's posture:** (a) the variance-floor law closes
the presence/variance gap generally — future family votes cannot silently carry dead
voters; (b) the census + train/serve machinery turns "can this family be trusted at
serving time" into a computed artifact that flips automatically when the PR-1a
telemetry stamps; (c) the fold-law arithmetic (67 more dates) gives the program its
honest clock — the C2 leaderboard conversation has a date, and it is not soon.

**Recommendation for W3 (PR-3, the nightly shadow-scoring wave):** proceed EXACTLY on
the PR-1b Adjudication's prereg — G3, G4, C1-as-raced, C1−F2 vs G0/G0′, zero authority,
prereg before the first stamped night. Nothing in W2 perturbs that registration; W2's
F5 result is additional motivation for the C1-family telemetry inside the shadow lane
but registers NO new rung (a C2 shadow entry would be a fitted rung with no lawful
fit — it stays out). Carry into PR-3's design: as-of-night floor evaluation (both
presence AND variance axes — the whole-frame floor look-ahead lesson applies to the new
axis identically), and the §13.0 closure verification as a precondition for trusting
any context-vector-fed telemetry.

*Return packet to Sol rides in the PR body and the workstream handoff; stop-after-W2
per the commissioning.*
