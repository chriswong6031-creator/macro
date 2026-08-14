# Mastermind Evaluation Standards

**Status** proposed policy for quantitative research and intelligence evaluation ·
**Authored** 2026-08-12 · **Companion** `MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md`

Every rule below is stated as a **checkable obligation** with the failure it prevents. Where the
failure has already occurred in this repository, the case is cited — a standard grounded in the
firm's own history is obeyed; generic quant boilerplate is not.

---

## §1 The three tiers of claim

Everything Mastermind produces sits in exactly one tier, and the tier determines what may be
said about it in public, to the operator, and to a user.

| Tier | Requirement | May be said |
|---|---|---|
| **Display** | none — a null never blocks building or accrual | "here is a reading"; no performance claim |
| **Accruing** | registered in a ledger, pre-declared horizon, outcomes attaching | "recording since D; not yet decidable" |
| **Validated** | pre-registered gates met at the declared horizon, on held-out or live-forward data | "measured edge, here is the evidence" |

**§1.1** Context, data, detection and tagging infrastructure ships at Display tier **freely**.
A null never blocks a build. The gauntlet is a *promotion* gate, not a build gate.

**§1.2** A factor that is null as a standalone signal is **retained as a confluence input**.
Non-standalone ≠ worthless.

**§1.3** A kill closes the **specific construction tested**, never the search space. "Not found
yet" ≠ "does not exist." Every kill row names the construction it closes and the re-open path.

**§1.4** The word "validated" in user-facing text is CI-enforced
(`scripts/check_validated_claims.py`). It is not a synonym for "we like it."

---

## §2 Temporal integrity

**§2.1 The four regimes, in ascending order of evidential weight.**

| Regime | Definition | Weight |
|---|---|---|
| Training | period used for discovery | none on its own |
| Validation | period used for tuning | none on its own |
| Holdout | untouched until a single pre-registered read | moderate — **one look only** |
| Walk-forward | repeated simulation using only information available at each date | strong |
| **Live-forward** | prediction recorded before the outcome exists | **decisive** |

**§2.2** A holdout that has been looked at more than once is a validation set. There is no
procedure for restoring holdout status; mint a new one from later data.

**§2.3** Live-forward is the only regime that may move an engine to Validated.

**§2.4 Verdicts only at the declared horizon.** A claim declares `horizon_d` at registration.
Grades accrue at every shorter in-scope horizon on the way there; **those are ACCRUING, not
verdicts.** Reading a 5-day grade as the record of a 63-day signal is forbidden
(`DNR:KILL-OFFHORIZON-VERDICTS`) and is now machine-checked by
`scripts/check_qledger_metric_validity.py` (invariant V3).

> **Live case.** As of 2026-08-12 *no* claim family in the Universal Scoreboard has produced a
> single verdict at its own declared ruler: `radar` and the `altdata` family declare 63 days,
> `policy` 126, `narrative_source_call` 28, `whitehouse` 7 — and the grade corpus holds only
> horizons {1, 3, 4, 5, 21}. Every hit rate currently computable from that store is off-horizon.

**§2.5 The falsifier must be able to fire.** A promotion conditioned on a future read that
*structurally cannot occur* is unfalsifiable and must not age toward confirmed-by-default.

> **Live case.** `DNR:HOLD-PSQ-TILT-CLOCK` — a provisional grant was conditioned on a forward
> shadow read whose sole input file is gitignored and has never been committed, so the cohort is
> permanently empty and the auto-demote clause (`n_matured_126 >= 30`) can never evaluate true.
> The clock was frozen rather than allowed to mature into a confirmation. **This is the standard.**

---

## §3 Leakage: the eight classes, each with its check

A study is not eligible for promotion until every applicable row is answered in writing.

| # | Class | Check |
|---|---|---|
| 1 | **Lookahead** | every feature timestamped ≤ decision time; PIT store or explicit embargo. `qledger` implements a `timestamp_quality` embargo — use it |
| 2 | **Survivorship** | the historical universe must include delisted/dead names. State the universe's construction date and its selection rule |
| 3 | **Revision leakage** | macro series must be as-first-published, not as-revised |
| 4 | **Timestamp leakage** | after-close information must not enter an intraday model |
| 5 | **Corporate actions** | prices adjusted; the adjustment vintage named |
| 6 | **Universe leakage** | index membership as-of the date, never today's constituents |
| 7 | **Hyperparameter overfitting** | count the looks; report deflated statistics (DSR) when >1 |
| 8 | **Multiple testing** | report family-wise or FDR-adjusted significance (BH q) with the number of tests |

**§3.1 Survivorship is the house's recurring failure and is *always* flattering.**

> **Live case.** `DNR:KILL-PRIMED-DIRECTIONAL-GATE` — the phase-0 calibration found every stage
> carried E[R] > 0, *including the blocked arm at +0.205*. A gate whose rejected trades also make
> money is not measuring a gate; it is measuring survivor-universe drift. The pre-registered
> three-leg test failed anyway, and the weaker "expectancy > 0" criterion — which would have
> shipped a false GO — was **retired as a gate**. Retiring the criterion, not just the signal,
> is the behaviour this standard requires.

**§3.2 Look-ahead selection in the *store* is a distinct defect from look-ahead in the *model*.**

> **Live case.** `DNR:KILL-PHASE3-START-WEIGHT` — the ClinicalTrials store is top-100-per-sponsor
> ordered by last-update, making the pre-2019 slice look-ahead-selected regardless of how the
> model uses it. Any re-test was blocked on fixing collector pagination *first*. **Audit the
> collector, not only the model.**

**§3.3 A gitignored input is a silent hole.** An input absent from CI and from cold clones
produces a study that cannot be reproduced and a live path that silently degrades. Any input to
a promotion-bearing study must be tracked or have a documented fetch step.
(`DNR:HOLD-FACTOR-UNIVERSE-WIDENING` names exactly this hazard for
`data/russell_breadth/_closes_cache.parquet`.)

**§3.4 Winsorisation and normalisation are part of the universe definition.** Changing the
universe changes clip points, which reorders legs that are means of separately-winsorised
z-scores even when the underlying ratios are unchanged (measured: composite Spearman 0.703,
74.7% of names change decile, top-10 survives 2/10). Report rank churn, never only median shift —
a median-shift-only reading returns a false GO.

---

## §4 Metric validity

Enforced by `engine/qledger_validity.py` and `scripts/check_qledger_metric_validity.py`.

**§4.1 Signed excess may not be pooled across directions.** `grades.excess` is raw
subject-minus-control return and is **not** direction-signed; `hit` carries direction. A correct
bearish call therefore contributes a *negative* excess. Pooling across a mixed-direction family
measures universe drift, not skill. Legal alternatives: hit rate, mean |excess|, or a per-direction
split.

> **Live case.** `scripts/grade_qledger.py` emits a per-family `excess_mean`. For `radar`
> (3,681 bullish + 5,626 bearish claims) that number is uninterpretable. The pooled corpus figure
> is −0.0065 at t=−17.9 — impressive-looking, and meaningless. The same script's placebo duel
> correctly uses `mean_abs_excess`, so the distinction was understood but not enforced.

**§4.2 A salience claim has no hit rate.** `direction == 0` asserts importance, not direction;
`hit` is undefined and stored null. 71% of the live corpus is salience. A headline claim count
that does not separate salience from directional overstates the directional evidence base ~3.5×.
Salience is evaluated by rank-IC against realised |move|.

**§4.3 Never evaluate a descriptive analytic on forward returns.** GEX, concentration, exposure
and correlation are *facts*. Their metrics are reconciliation against source, reproducibility and
freshness. Attaching a forward-return metric to a descriptive analytic is itself a defect.

**§4.4 Honest N is episodes, not fires.** Report the count of independent date clusters, not the
row count. `qledger` already computes this. A signal firing 200 times across 4 days is n≈4.

> **Live case.** The Prophet live ledger holds 28 closed plans across **24 distinct signal dates**
> and 26 distinct assets. Quote 24, not 28.

**§4.5 Every metric carries its base rate.** A 32% hit rate is uninterpretable without the
matched-universe base rate; a 67% bullish accuracy in a rally where 65% of stocks rose is
approximately zero information. Report **incremental** value against: market, sector, matched
universe, naive strategy, and prior probability. The `qledger` matched control and the `*_pit`
twin desks exist for this.

**§4.6 Report the uncertainty with the estimate, always.** A mean without an interval is not a
result. Use date-blocked or ticker-blocked bootstrap CIs where observations cluster.

> **Live case.** Prophet US mean is +0.514% with se 2.88 → **t = +0.178**, CI [−5.14%, +6.17%].
> The point estimate is positive; the result is indistinguishable from zero. Both facts must be
> reported in the same sentence.

**§4.7 Reporting floors.** Below **50 matured observations** at the declared horizon, an engine
may report *accrual status only* — no hit rate, no alpha, no ranking claim in any external or
user-facing surface. Internal telemetry is unrestricted.

**§4.8 State the look count.** When a record is re-read as it accrues, every headline is a look.

> **Live case.** The Prophet record read 12.5% win rate (n=16) on 2026-08-05 and 32.1% (n=28) at
> `HEAD` one week later. Both are honest; neither is decisive. At n≈20 a handful of closures moves
> the headline tens of percentage points, so **no decision may be conditioned on a series this
> short**, in either direction.

---

## §5 Benchmarks

**§5.1** Raw return is not a result. Every predictive engine grades against its **declared
benchmark** — the universal baseline — and never against zero. A **matched control** is the
stricter *second* evidence basis, and it is **required exactly where the family's control policy
says so**: three states (`matched_control_required`, `benchmark_only`, `not_applicable`) held in
one governed table, changed only by a governed edit with cited evidence
(`research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md`; the classification is grounded in
`research/EVAL_OS_P0D_CONTROL_CENSUS.md` §3–§4). Benchmark-relative evidence is **labelled
benchmark-relative** and is never presented as matched-control. Where controls are required,
**control coverage is part of the evidence** — the issued cohort stays in the denominator — and
the gate **fails closed** without it: no bench record substitutes for missing controls, under any
data condition.

> **Live defect.** `data/prophet/ledger.jsonl` has no benchmark field. Its schema is
> `[asof, asset, close_date, days_held, direction, id, option_result_pct, outcome,
> plan_adherence, schema, signal_date, stock_result_pct]`, so `stock_result_pct` is a raw return.
> The awkward part is that Prophet's *other* surface does this correctly: `grade_us_board.py`
> grades the board versus SPY **and** the name's sector ETF at 5/10/21/63d. The un-benchmarked
> surface is the one carrying the public performance narrative. **Highest-value single fix in
> this document.**

**§5.2** The control must be matched on what the signal does *not* claim to predict — sector,
size, beta, liquidity. An unmatched benchmark converts a sector bet into apparent skill.

**§5.3** A placebo arm belongs in every scored family. The live placebo tape scores t = +0.94 —
indistinguishable from zero, exactly as designed. Placebo results are published beside real
results, never suppressed.

---

## §6 Segmentation

Aggregate performance hides the weakness that matters. Report by: market cap, liquidity, sector,
country, regime, volatility, signal strength, holding period, entry state, beta, catalyst
presence, earnings proximity.

**§6.1** Segment dimensions are declared **before** the read. Choosing the segmentation after
seeing results is multiple testing wearing a disguise.

**§6.2** A segment must be *estimable* before it is reported. Conditional expectations over a
state observed in a single value are undefined.

> **Live case.** `DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` — the proposed family × regime grid was
> refused not merely as null but as **unestimable**: the conditioning axes were stamped on 0.4% of
> the record within one month, `vol_regime` and `rate_pressure` were observed in a *single* state,
> and the board ledger's 2,282 graded fires spanned 18 trading days with zero regime contrast.
> A machine-checkable coverage assessment (`engine.regime_conditioning_coverage.assess()`) is now
> required to return `estimable` before the axis may be used. **Extend that pattern to every
> segmentation axis.**

**§6.3** Interaction claims must be compared against main effects. In the cited case the claimed
interaction was 3.8× *smaller* than the family main effect, with era-split sign stability at 62% —
a coin flip.

---

## §7 Regression: did the model get stupider?

**§7.1** Version comparison is **prospective wherever possible**: challengers re-slice the same
nightly candidate artifact the champion used, graded by the same closure rules, on the same
nights. `engine/prophet_arena.py` is the reference implementation. A one-off backtest of a
re-slice is not evidence for a live rule change.

**§7.2** The comparison scorecard is **multidimensional and reported whole**: coverage, alpha,
drawdown, timing, sector concentration, false positives, crash frequency, ranking monotonicity.
A single improved average never ships alone — "better mean return" may not mask "4× worse tail."

**§7.3** An engine change that improves the mean and worsens the tail is a **warning gate**, not
an automatic block. It ships with a written waiver naming the trade-off.

---

## §8 Gates

| Gate | Blocks? | Contents |
|---|---|---|
| **Hard** | yes | lookahead/leakage check fails · `scored`-tier artifact without `evidence_ref` · metric-validity `invalid` on a published number · required input `unavailable` · schema/registry integrity |
| **Warning** | no, waiver required | alpha decline beyond threshold · monotonicity degradation · concentration jump · false-positive rise |
| **Informational** | no | coverage, timing distribution, holding-period drift |

**§8.1** Hard gates are **integrity** properties only. Performance-based hard gates on short
records are noise-driven vetoes and will stop research without improving it (§4.8).

**§8.2** A gate that fires fleet-wide on first wiring gets routed around rather than obeyed. New
gates ship WARN-tier with a dated plan to promote them, and the promotion is a deliberate act.

---

## §9 Nulls, absence, and language

**§9.1** Nulls are **printed, not hidden**. A pre-registered gate that fails is published with
the same prominence as one that passes.

**§9.2** *"I could not look"* must never render as *"I looked and saw nothing."* An absent store,
an unavailable feed, or a skipped check is disclosed explicitly. This applies to CI gates, to
scorecards, and to user-facing surfaces alike.

**§9.3** LLMs may only **de-escalate** calibrated keys. They never originate signals, scores or
escalations (house constitution A7). Generated prose is evaluated, never trusted
(`engine/neuralweb/response_eval.py`).

**§9.4** Confidence language must be earned. "High confidence" is reserved for outputs with a
calibration curve at the declared horizon. Where an engine emits a *relative score*, the surface
must not render it as a *probability*. Confidence degrades explicitly with input staleness
(architecture §3) and with unresolved same-horizon contradiction (architecture §4).

**§9.5** Falsifier and refutation language stays out of user-facing surfaces (operator ruling,
2026-07-27). Full verdicts live on the Calibration Lab; user surfaces show windows, watch
conditions, and plain-word状态 updates.

---

## §10 Pre-registration

**§10.1** A promotion-bearing study registers, before the read: hypothesis and mechanism; universe
and its construction rule; horizon; primary metric; **pre-declared pass/fail thresholds**;
segmentation axes; the falsifier; and the auto-demote clause.

**§10.2** The falsifier must be able to fire (§2.5), and the auto-demote clause must name a
cohort that will actually accrue.

**§10.3** Results are published whether or not they pass, in a paired `_RESULTS.md`.

**§10.4** A kill appends a row to `research/DO_NOT_REBUILD.md` with a minted stable key, the
construction closed, the evidence, and the re-open path. Cite rows as `DNR:<KEY>`, never by row
number.

---

## §11 Adjudication coverage

**§11.1** Statistical rigour does not substitute for an adversarial pass on the **conclusion**.
Before presenting a discovered rule: run it against the motivating live exemplars *and* the
current regime, and lead with that answer.

**§11.2** Report episode-level honest-N and state whether today is in-sample of the winning cell.

**§11.3** Name who is missing from the panel — survivorship, delistings — before trusting any
cohort mean.

**§11.4** **An instrument verdict is not a market verdict.** A terminal chain or tripwire state
means its *declared windows* failed, never "the thesis is false." Report the scope ("no 22-day
rolldown yet"), not a verdict the instrument cannot support.

> **Live case.** `research/CASE_STUDY_GOLD_REAL_RATE_2026_08.md` — the engine narrated "no peak;
> restriction still building" nightly while the real-rate-peak call was already +20%, because a
> trailing-63-day window is structurally blind to a fresh peak for weeks. Where a display-tier
> state disagrees with the terminal asset's tape, **the dual read leads and the state verdict is
> the footnote.**

---

## §12 Checklists

**Before promoting an engine above Display**
- [ ] Prereg exists, with pre-declared thresholds, and its falsifier can fire (§2.5, §10)
- [ ] Every applicable leakage class answered in writing (§3)
- [ ] Verdict read at the declared horizon (§2.4)
- [ ] Evidence basis satisfied per the family's control policy (matched control where required,
      with coverage), and a placebo arm (§5)
- [ ] Honest-N ≥ 50 matured episodes at that horizon (§4.4, §4.7)
- [ ] Uncertainty reported with the estimate (§4.6)
- [ ] Pre-declared segments, each estimable (§6)
- [ ] Multidimensional regression vs the incumbent (§7)
- [ ] `evidence_ref` recorded in the engine registry (§8 hard gate)
- [ ] Adversarial pass on the conclusion against live exemplars (§11)

**Before publishing any number externally**
- [ ] Metric legal for the output class (§4.1–§4.3)
- [ ] Base rate reported alongside (§4.5)
- [ ] N, horizon, and date range stated (§4.4, §4.7)
- [ ] Look count stated where the record is re-read (§4.8)
- [ ] Nulls and unavailable inputs disclosed (§9.1, §9.2)
- [ ] The word "validated" used only per §1.4
