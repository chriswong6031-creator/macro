# Regime-reliability & factor-crowding engine — external intake adjudication

**Source:** external proposal (ChatGPT), 2026-08-05 — "the regime engine should estimate which
strategies are *reliable*, not just label the market risk-on/risk-off": monitor 16 named signals,
then publish per-signal-family `R[s,t] = E[future strategy performance | current regime]` as a
reliability table, so the product can say *"technically bullish breakout, but breakout continuation
has poor reliability in the present regime."*

**Verdict: REJECT as specified — REDUNDANT in its legal half, FORBIDDEN in its fused half, and
NULL where it is novel.** One instrument built (§6). Measured receipts: `reports/regime-reliability-phase0.md`.

**Adjudicated:** 2026-08-05. **Registry rows:** `research/DO_NOT_REBUILD.md` §1, §2.

---

## §1 Why the framing is right — and why that is not enough

The proposal's *premise* is correct and is already house doctrine. "Which strategies are reliable
now" beats "risk-on/risk-off" — and the house said so first, in
`research/FACTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §1.1, which ruled that factors are a
**de-escalation and conditioning instrument**, not a selection engine. The same masterplan
adjudicated a near-identical external handoff in §2.1 and already ruled on this exact idea:

| Handoff idea (2026-07) | Existing ruling | Bearing on this proposal |
|---|---|---|
| "Factor weather: regime-conditional factor leadership as a market coordinate" | **ADOPT — as coordinate, not prior.** "The classifier carries no folk theory about what works in each state — *the kernel measures that*" | The proposal is the folk-theory form that was explicitly ruled out |
| "Factor-adjusted technicals: signal quality conditional on factor regime" | **ADOPT** → hypothesis H1, pre-registered | Already the registered form of this question |
| "Crowding X-ray: factor concentration risk overlay" | **ALREADY-BUILT** — six modules | The crowding half is built |
| "Factor rotation velocity as a timing signal" | **KILLED** — `acc_res` sign-unstable, fails both-halves + CV | Adjacent construction already dead |

So this proposal is not new intake. It is a re-proposal of an adjudicated topic, arriving without
the evidence the original ruling demanded. That alone is grounds for REJECT-REDUNDANT under the
`DO_NOT_REBUILD.md` authority clause — but the substantive findings below matter more.

---

## §2 Half one — the 16-signal monitor is already built, and fusing it is forbidden

Every one of the 16 monitored signals already exists:

| Proposed signal | Existing home |
|---|---|
| Realized market volatility | `engine/vol_regime.py` |
| Volatility of volatility | `engine/options_desk.py` |
| Cross-sectional dispersion | `engine/dispersion.py` |
| Average pairwise correlation | `engine/dispersion.py` (`avg_corr`), `engine/contagion.py` |
| Market breadth | `engine/live_breadth.py`, `engine/advanced_breadth.py`, `engine/breadth_split.py` |
| Credit spreads | `engine/bond_compass.py`, `engine/bond_cross_asset.py` |
| Yield-curve movement | `engine/bonds.py`, `engine/regime.py` axes |
| Commodity volatility | `engine/active_commodity.py` |
| Dollar regime | `engine/forex_regime.py` |
| Momentum / reversal / size factor returns | `engine/equity_factors.py`, `engine/factor_series.py`, `engine/factor_orthogonal.py` |
| Short-interest regime | `engine/crowding.py`, `engine/altdata_models.py` |
| Options-skew regime | `engine/options_desk.py`, `engine/options_structure.py` |
| Dealer-positioning proxies | `engine/gex_state.py`, `data/polygon_gex/` |
| Sector leadership concentration | `engine/theme_crowding.py`, `engine/index_leadership.py` |

They are already composed into an authority chain: **`risk_radar` → `market_state` →
`regime_vector`**, with `engine/regime_one.py` providing the honest four-way decomposition
(tape / macro / forward / fused_risk) and `engine/regime_coherence.py` asserting at build time
that the generations cannot contradict each other on a stress day.

**Fusing them into one new regime verdict is FORBIDDEN, twice over:**

- `DO_NOT_REBUILD.md` §2 (MSP-R2, 2026-07-18) already rejected "composite market-regime scorecard
  fusing gamma/vol/flow/breadth into a regime verdict" as **REJECT-REDUNDANT + FORBIDDEN fusion
  path** — it duplicates that authority chain.
- Four of the sixteen inputs (short interest, options skew, dealer positioning, COT-style
  positioning) are **positioning keys**. `DO_NOT_REBUILD.md` §1: *"Positioning fusion (positioning
  keys fused into signal scores) — **ILLEGAL**"* (Signal Commons rulings, 2026-07-05).

The monitor half therefore cannot be built as proposed, and needs no building as measured.

---

## §3 Half two — `R[s,t]` is not estimable on the regime axes the proposal names

The reliability table needs graded outcomes stamped with the regime they occurred in. The house
already builds that join — `data/us_board_ledger/retro_grades.parquet` and
`data/signal_archive/track_record.parquet` both carry `quad_hard_label`, `vol_regime`,
`fused_risk_label`, `rate_pressure`, `risk_radar_state`. **The join is not the problem. Contrast is.**

Measured on the 58,149-row signal track record (`reports/regime-reliability-phase0.md` §0):

```
  [PASS] regime_at_entry    cov=100.0%  states=3  min_state_months=725  1962-11-29..2026-07-31
  [----] quad_hard_label    cov=  0.4%  states=2  min_state_months=  1  2026-07-01..2026-07-31
  [----] vol_regime         cov=  0.4%  states=1  min_state_months=  1  2026-07-01..2026-07-31
  [----] fused_risk_label   cov=  0.4%  states=4  min_state_months=  1  2026-07-01..2026-07-31
  [----] rate_pressure      cov=  0.4%  states=1  min_state_months=  1  2026-07-06..2026-07-31
  [----] risk_radar_state   cov=  0.4%  states=2  min_state_months=  1  2026-07-01..2026-07-31
```

Every rich axis is stamped on **0.4% of the record, inside a single month**, and `vol_regime` and
`rate_pressure` are observed in **one state**. A conditional expectation over one observed state is
undefined everywhere else; a table built on it *reads* as a comparison while *being* a constant.

The board ledger is no better: `retro_grades.parquet` holds 2,282 rows across **18 trading days**,
and every graded fire in it sits in `quad=Q1`, `vol_regime=normalizing`, `rate_pressure=pressure` —
**zero regime contrast**. The graded qledger (38,247 claims) spans 2026-06-15 → 2026-08-05, seven
weeks, one regime.

Nor does the raw regime history rescue it. `data/regime/regime_v2_pit.parquet` is PIT-clean back to
1971, but yields **422 quad episodes (median 24 days); post-2010 only 128, of which 14 are ≥63 days
long**. That is the honest N for a 63-day-horizon regime-conditional claim — and the proposal wants
to condition on a *sixteen-dimensional* regime. The house has already written this constraint down
in `engine/meta_label.py`: *"GBT overfits catastrophically on the ~10-episode macro/crisis layer
(n≈crises)"* — which is why meta-labeling was confined to the one high-N surface (BTC daily bars).

---

## §4 Where it *is* testable, the effect is null

`regime_at_entry` (bull/bear/choppy) is the one axis with 64 years and 100% coverage — 57,642
matured signals across 763 months, with forward drawdown outcomes. Full method and tables:
`reports/regime-reliability-phase0.md`.

The proposal's claim is an **interaction** claim: a family's reliability must *change* with regime.
It is not enough that bear tapes are worse for everything — that is a market main effect the stack
already publishes, and `regime_at_entry` and `fwd_mdd_60` are both functions of the same price
series, so the raw table is partly tautological. Removing month fixed effects (which absorb the
common market/vol/macro condition) and decomposing:

| Term | Magnitude |
|---|---|
| **Family main effect** (which signal fired) | **3.59 pp** |
| Regime main effect | 0.95 pp |
| Largest single interaction | 1.49 pp |

**Knowing which family fired is worth 3.8× more than knowing the regime.** And the interaction is
not robust:

- Only **5 of 15** interaction cells have a month-block bootstrap 95% CI excluding 0 (B=600).
- The two largest interactions sit in the two **thinnest** cells (n=48 and n=41); both CIs include 0.
- Era-split sign stability (DT-R16 split at 2010) is **8/13 = 62%** — against a 50% coin-flip
  expectation. The house kill standard for split-half sign flips (`fund_crowding` phase-0, PSS-F3)
  is not met.

**NULL.** The dominant, era-stable term is *which family fired*, not the regime it fired in — and
that term is already what the board ranks on.

*Scope of this null:* it closes the construction "per-family reliability table conditioned on a
market-regime label, graded on forward drawdown". It does **not** close regime conditioning as
de-escalation context (already live), nor the pre-registered H1 (§5), nor a future test on a richer
axis once the estimability gate turns green (§6).

---

## §5 What already ships the value the proposal is reaching for

The proposal's motivating sentence — *"this breakout is real but continuation is unreliable now"* —
is already a shipped behaviour, in the honest form:

- **`engine/dispersion.py`** is precisely a per-family reliability dial: it measures cross-sectional
  dispersion and average pairwise correlation and publishes *"Selection pays — high dispersion"* vs
  *"Macro tape — selection muted"*. **This is the proposal's own idea, already built, already
  measured — and its `gross_mult` is clamped to 1.0** because the selection-IR edge was never
  measured (`US_BOARD_MEASUREMENT.md` §Study 3). The shadow magnitude is retained so a future
  measured promotion is one config flip. That clamp is the empirical answer to this proposal,
  reached before it arrived.
- **`style_regime`** (Factor Intelligence D-6) is the shipped "factor weather" coordinate, wired
  into `engine/neuralweb/world_state.py` and `mechanism_pathways.py` — deliberately *without* a
  folk-theory reliability prior attached.
- **`engine/regime_one.py`** publishes `fused_risk` with an explicit `confidence` that **degrades at
  inflections**, plus flip attribution that vetoes a regime flip caused by a data outage rather than
  by data. That is a more honest reliability statement than a fitted `R[s,t]`.
- **Crowding** is built six ways over (`engine/theme_crowding.py`, `engine/factor_exposure.py`,
  `engine/crowding.py`, `engine/froth_fragility.py`, `engine/ownership_crowding.py`,
  `engine/personality_crowding_hazard.py`, plus the `scripts/fund_crowding_phase0.py` study —
  note the Factor Intelligence masterplan §2.1 cites an `engine/fund_crowding.py` that does not
  exist; the fund-crowding work lives in the script and `reports/fund-crowding-phase0.md`)
  — and `engine/crowding.py` documents why
  it is display-only: crowding showed **no forward-return underperformance**, and its short-interest
  leg has no point-in-time history to backtest at all.

---

## §6 What was built — the estimability gate

One real gap surfaced. The regime stamps exist on the graded records, but **nothing reads them to
answer "can a regime-conditional claim be made at all?"** — so a future session (or an LLM surface)
could compute a confident 6×4 reliability grid from 235 rows in one month, with `vol_regime` held
constant, and nothing in the stack would object.

**`engine/regime_conditioning_coverage.py`** (measurement-only, display-tier, emits no signal) closes
that. For each candidate regime axis it reports coverage, observed states, and **distinct months per
state — months, not rows, because same-month signals share one market** — against three frozen gates:

```
MIN_COVERAGE = 0.20   an axis stamped on <20% of the record cannot describe the record
MIN_STATES   = 2      one observed state is a constant, not a condition
MIN_MONTHS_STATE = 12 per-state independent months (H1 prereg floor was >=10, rounded to a year)
```

Verdicts: `estimable` / `insufficient_coverage` / `single_state` / `insufficient_contrast`. Anything
but `estimable` is a hard NO for that axis. `tests/test_regime_conditioning_coverage.py` (16 tests)
pins each failure mode, including the 2,282-rows/18-days trap and placeholder tokens (`unknown`,
`n/a`) manufacturing fake contrast; all three central guards are mutation-verified.

This is the "how you would make it" answer: the gate is what must turn green before `R[s,t]` is
attemptable at all. Today it is green on exactly one axis, and on that axis the effect is null (§4).

---

## §7 Re-open conditions

A future regime-reliability proposal is admissible only with **all** of:

1. `engine/regime_conditioning_coverage.py` returning `estimable` for the specific axis to be
   conditioned on — on the record that will be graded, not a different one.
2. A fresh pre-registration naming the family set, the horizon, and the outcome metric **before**
   the table is computed, with the interaction (not the raw cell means) as the primary quantity.
3. An era-split sign-stability gate at the house standard, and a floor on the thinnest cell.
4. No fusion of positioning keys into any regime score (standing: ILLEGAL), and no new composite
   regime verdict beside `risk_radar → market_state → regime_vector` (standing: MSP-R2).

Accrual note: the vector stamps began 2026-07-01. At ~21 stamped sessions/month, `quad_hard_label`
reaches the 12-month per-state floor no earlier than **mid-2027**, and only if the market actually
visits ≥2 quads — which is exactly what the gate in §6 is there to report, rather than assume.
