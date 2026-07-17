# S-MLC-2 — Suction Regime Conditionality · PRE-REGISTRATION

**Battery:** S-MLC-2 (MLC masterplan §W6, study 2 of 3).
**Program:** Megacap & Leadership Coherence (MLC, chartered 2026-07-14).
**Author:** research agent (Sonnet). **Adjudicated 2026-07-16** — all freeze-review markers resolved; see freeze record at end of document.
**Pre-reg committed:** before any measurement run and before the W3 suction organ is built. No harness code in this PR.
**Wiring:** NONE. This pre-reg gates AUTHORITY only (rank/size/gate). The W3 suction-ladder organ ships display-tier freely regardless of this study's verdict (MLC-R2; house law §Epistemics).

**Dependency:** the conditioning variable (W3 suction-ladder state) references an organ that is **not yet built** as of this pre-reg. The conditioning variable is therefore defined abstractly here (§1.2). When W3 ships, the exact field names and threshold values must be stamped in a dated APPEND to this doc before the harness runs. The APPEND does not reopen the closed sections of this pre-reg.

---

## 0. Question and honest prior

**Question.** Conditional on the W3 suction-ladder state signaling an "active suction regime" (NVDA/Mag7 cap concentration above a frozen threshold and cw/ew spread widening), do laggard-sector bounce entries **underperform their unconditional base rates** on a 10-40d forward excess-vs-SPY horizon?

This directly falsifies the operator's thesis: "when NVDA or Mag7 is running hard, liquidity gets sucked away from the rest of the tape — entering laggard-sector bounce setups at those moments underperforms because the capital is absorbed by the leaders." A falsification (laggard bounces do NOT underperform conditionally) does not close the suction-organ display surface; it closes only this specific "suction state suppresses laggard-sector bounce returns" claim. A confirmation (conditional underperformance is real) earns the suction-state the right to gate or damp laggard-sector entry signals, gated on a GO verdict here.

**Mechanism hypothesis.** During concentrated megacap runs, active fund rebalancing and ETF inflows disproportionately recirculate into index-heavy names, reducing the marginal capital available for laggard-sector recovery. The mechanism predicts not just that leaders outperform (tested separately in S-MLC-1) but that laggard bounces are specifically *dampened* — they may still show positive absolute return but at lower hit-rates and smaller magnitudes than the unconditional base rate.

**Honest prior.** The "liquidity suction" thesis is a plausible mechanism but frequently overstated in popular commentary. The academic literature on breadth-under-rally is mixed: some evidence for narrowing breadth in late-stage bull phases, but causal direction (suction → laggard underperformance vs both driven by a common macro factor) is hard to identify with PIT data. Prior lean: **uncertain; the null is credible**. A null here does not mean the suction organ has no value as display context; it means the specific authority claim (suction state dampens laggard bounces enough to gate entry) is unsupported. This study should be approached as a rigorous null test, not a confirmation project.

**Standing kills honored.** No entry in `research/DO_NOT_REBUILD.md` directly overlaps this construction. Adjacent entries reviewed:
- `rs-based member-dispersion gates` (§1, R-4): killed as a zero-sum tautology. S-MLC-2 does NOT use RS dispersion as a gate; it uses a cap-concentration + cw/ew spread conditioning variable (a mechanistically distinct construction). However, the conditioning variable must be defined without RS dispersion legs — the threshold design in §1.2 must be audited against R-4 at freeze time.
- `Rotation × cycle-position entry-confluence` (§1, MLC-R3): S-MLC-2 is conditioning on *suction state*, not cycle position. Not implicated unless the W3 organ construction imports cycle-position logic.
- `FRESH BUY as a buy edge on the Act-Now board` (§2): This kill covers a different construction (fresh buy as the positive predictor, not as the conditioned outcome). Not directly implicated.
- `McClellan MCO thrust / MCO-oversold+MSI-washout bounce as radar legs` (§2): Rejected for being coincident-by-construction; the laggard bounce entry definition in this study (§1.3) must avoid defining "bounce" in a way that is tautologically coincident with future returns.
- `Shock→archetype beneficiary/casualty map` (§1, TI-R5): Killed for laundered directional escalation on *nulled* continuation claims. S-MLC-2 does not claim to escalate based on pre-nulled evidence; this is a fresh pre-registered test.

No kill is triggered by this pre-registration. This section must be re-verified when W3 ships (the W3 organ construction may import a killed pattern if not carefully designed).

---

## 1. Data construction

### 1.1 Outcome universe — laggard-sector bounce entries

**Sector universe:** the 11 SPDR sector ETFs: XLK, XLF, XLV, XLE, XLY, XLU, XLI, XLB, XLRE, XLC, XLP.

**Note on XLRE and XLC:** XLRE inception 2015-10-08; XLC inception 2018-06-19 (verified from `data/yahoo/` parquet files). These are excluded from the pre-2016 and pre-2019 samples respectively. Analyses using deep history (XLK/XLF/XLV etc. 1998-12-22→) must exclude XLRE and XLC from those pre-inception windows, not impute.

**Data source:** `data/yahoo/{XLK,XLF,...}.parquet` for total-return closes (dividend-adjusted). Benchmark: `data/yahoo/SPY.parquet`.

### 1.2 Conditioning variable — W3 suction-ladder state (abstract definition)

The W3 organ is not yet built. The following abstract definition specifies what data the conditioning variable must capture. When W3 ships, the exact field names must be appended to this doc (dated APPEND, not an edit to this section).

**Abstract conditioning variable (suction-active flag):**

A trading day `t` is in an **ACTIVE SUCTION REGIME** if ALL of the following hold simultaneously:

**(C1) Megacap cap-weight elevation:** NVDA (or Mag7-as-a-cohort) share of SPX market cap is above a frozen high-concentration threshold.

**FROZEN (2026-07-16, adjudicated):** C1 threshold = NVDA share of SPX market cap ≥ its trailing **756-session** (3-year) **75th percentile** AND ≥ **5.0% hard floor**. The 756-session lookback (not 252d) is required so that consolidations within a multi-year concentration trend do not flip the active state. The 5.0% hard floor ensures that early-history percentiles cannot fire at trivial concentration levels before NVDA had material SPX weight.

considered and rejected: 252d percentile (state-flappy during consolidations within multi-year runs; dismissed); fixed 6%-only threshold (level-arbitrary, no regime adaptation; dismissed).

**(C2) cw/ew spread widening:** The trailing 21-session cap-weighted-minus-equal-weight return spread is **> 0** (RSP serves as the equal-weight proxy; cap-weighted = Mag7-cw return over the same 21 sessions). A day satisfies C2 if cw return exceeds ew return over the trailing 21 sessions — a DIRECTIONAL sign condition.

**FROZEN (2026-07-16, adjudicated):** C2 = sign condition (cw-minus-ew spread > 0), not a percentile threshold. Rationale: the suction mechanism is inherently directional — cap-weighted outrunning equal-weight is the mechanism. A sign condition is mechanism-true and simpler than a percentile gate; percentile forms introduce unnecessary sensitivity to distributional shape.

considered and rejected: 50th percentile of rolling 252d history (percentile form of the same direction condition; dismissed); 75th percentile to match C1 (over-tightens the gate; dismissed).

**(C3) Duration floor:** The suction-active state (C1 AND C2 jointly satisfied) must have been jointly held for **≥5 consecutive sessions** before day t.

**FROZEN (2026-07-16, adjudicated):** C3 = ≥5 consecutive sessions confirmed. This guards against reacting to one-day blips in the concentration or spread measures without introducing a longer lag that would reduce event count.

A day `t` is in a **SUCTION-INACTIVE REGIME** (the control state) if C1 is NOT satisfied (C2 and C3 are irrelevant in the inactive state).

Days that satisfy C1 but not C2 or not C3 are in a **MIXED** zone.

**FROZEN (2026-07-16, adjudicated):** The partition is a THREE-WAY split: active / inactive / mixed. Statistical inference is computed ACTIVE vs INACTIVE only. The mixed bucket is printed descriptively (event counts, mean returns) but is NEVER pooled into either the active or inactive cell for any verdict computation.

considered and rejected: reclassify mixed into inactive bucket (muddies the inactive control group; dismissed); exclude mixed days entirely without printing (non-transparent; dismissed).

### 1.3 Laggard-sector bounce entry definition

A **laggard-sector bounce entry event** on day `t` for sector ETF `s` occurs when:

**(E1) RS-rank laggard:** sector `s` is in the **bottom 3** of the 11 SPDR sectors by **60-session RS** vs SPY, measured over the 60 trading days ending day `t-1` (PIT, no look-ahead).

**FROZEN (2026-07-16, adjudicated):** E1 = bottom 3 of 11 SPDRs by 60-session RS (not 20d). The 60-session window is the Leadership Board's sector momentum rank, which is the surface the operator actually reads. The study must interrogate the construction as the operator experiences it. This is an event-population definition only — consistent with the R-4 zero-sum kill, RS rank here defines which sectors are studied, not a new gate on a signal.

**(E2) Up-day bounce:** on day `t`, the sector ETF posts a return >= +2 standard deviations of its own 252d daily return distribution (measured as of day `t-1`, rolling).

**FROZEN (2026-07-16, adjudicated):** +2σ confirmed (own 252d rolling daily-return σ, measured as of t−1). Rationale: self-normalizing across sector volatility regimes; a fixed-% threshold would over-select high-vol sectors. considered and rejected: fixed +1.5% day (vol-regime-biased), +1.5σ (event population too diluted toward noise days).

**(E3) Non-earnings day [DROPPED at freeze — see ruling below]:** the bounce entry does not fall on an S&P 500 earnings-heavy day (defined as: >= 3 S&P 100 constituents reporting that day, per `data/earnings/` if available).

**FROZEN (2026-07-16, adjudicated):** E3 is DROPPED from the primary event definition (MLC-R10: earnings is disclosure, never a gate — same ruling as S-MLC-1 Ruling 4). The earnings-heavy-day split is printed as a descriptive secondary only, and only if `data/earnings/` coverage permits; it can never change the primary verdict. considered and rejected: retaining E3 as a primary filter (violates MLC-R10; also makes the event population dependent on a store with known freshness defects).

**Event fill:** entry = **close of day t+1** (next-day close). Forward windows measured from that same t+1 close — no overlap double-count.

**FROZEN (2026-07-16, adjudicated):** Entry fill = **t+1 close. MANDATORY.** Same-day close (close[t]) is look-ahead because E1 RS rank and E2 realized return are computed from day-t data and are not actionable until after close on day t. The t+1 close is the earliest non-look-ahead fill. Forward windows are measured from t+1 close (i.e., the t+1-to-t+1+h return), eliminating double-count of the t+1 open-to-close move.

considered and rejected: same-day close (look-ahead; MANDATORY exclusion; dismissed).

### 1.4 Base-rate construction

**R-4 zero-sum audit (adjudicated 2026-07-16):** E1 defines an EVENT POPULATION (sectors in the bottom 3 of 11 SPDRs by RS), not a gate on a new signal. This is distinct from the killed class (R-4, "rs-based member-dispersion gates"): a dispersion gate would condition a signal's authority on the spread between members; E1 instead selects a sub-population of existing sector ETFs to study a conditional return claim. Defining a sample population by RS rank is epidemiologically standard (selecting cases for study) and is not a zero-sum tautology. Any future use of this study's findings that wires RS-dispersion as a gatekeeping signal would require a fresh pre-reg and R-4 review.

The conditional test compares laggard-sector bounce entries (E1+E2+E3 satisfied) in SUCTION-ACTIVE windows vs. the SAME events in SUCTION-INACTIVE windows.

**Headline comparison:**

`Conditional_excess(suction-active) vs Conditional_excess(suction-inactive)`

The unconditional base rate is the pooled excess return over all (E1+E2+E3) events regardless of suction state. This is printed as context but is NOT the primary verdict cell.

The primary verdict tests: `mean_excess_return(active) < mean_excess_return(inactive)` — i.e., suction DEPRESSES the laggard bounce magnitude.

**FROZEN (2026-07-16, adjudicated):** Test direction = **one-sided PRIMARY** (active < inactive; direction pre-declared because the mechanism is directional — suction suppresses laggard bounce returns). The two-sided p-value is printed as a **receipt** alongside the one-sided verdict, for transparency, but carries no decision weight. The one-sided test at α=0.05 is the binding gate.

considered and rejected: two-sided test as primary (discards pre-declared mechanistic direction; dismissed).

### 1.5 Coherence with the W3 field guide (adjudicated 2026-07-16)

The conditioning composite C1∧C2∧C3 defined in §1.2 pools the field guide's **suction-grind** and **suction-parabolic** states (see `research/MEGACAP_SUCTION_FIELD_GUIDE.md` §5–6; merges as PR #2667). The field guide characterizes both as regimes in which cap-weighted concentration is elevated and widening — C1∧C2∧C3 is the formal operationalization of their shared signature.

Two binding constraints from the field guide carry into this study:

1. **Two-axis independence requirement (field guide freeze-review-2 binding):** The C1 (concentration) and C2 (cw/ew spread) axes must be empirically independent at the W3 organ level before this study runs. The W3 organ build spec must document the C1-C2 correlation and confirm that joint satisfaction of both is not mechanically tautological (i.e., C2 is not simply a lagged restatement of C1). This requirement is BINDING on the W3 organ construction — it is not waivable by this pre-reg.

2. **Four-state display discretization must freeze before first run (field guide freeze-review-3 binding):** The W3 organ's four-state display discretization (suction-grind, suction-parabolic, consolidating, inactive) must be frozen at organ build, BEFORE this study's first run. The display states must not be adjusted to fit this study's observed event counts or returns. Any adjustment to the display discretization after the study has been run constitutes a post-hoc design change and requires a new pre-reg.

---

## 2. Pre-registered gates and sample requirements

### 2.1 Sample requirements before running

The study requires a **minimum effective episode count** to produce decision-grade inference.

**FROZEN (2026-07-16, adjudicated):** effective-N floor = ≥30 non-overlapping suction-active 21d events, confirmed. This is a PROMOTION gate, not a run gate — the harness runs and prints results at any N (nulls published); below the floor the verdict is capped at ACCRUE. If the W3 PIT reconstruction cannot reach ≥30 (NVDA cap-share history limits the active-state sample), the feasible N is reported and the study waits on accrual — the floor itself does not move (no recalibration; a dated APPEND may only extend the data window, never lower the floor).

### 2.2 Statistical gates — ALL must pass for a GO verdict (suction conditioning is effective)

| Gate | Rule | Required for GO |
|---|---|---|
| **Primary test** | Within-month episode-label PERMUTATION (DT-R14): permute the suction-active/inactive label within calendar month across events, 10,000 draws; null hypothesis = no conditional difference | p < 0.05, direction = active < inactive |
| **HAC t-statistic** | Newey-West HAC on `excess_return(active) - excess_return(matched inactive)`, where "matched inactive" is drawn from SAME sector SAME calendar month but in inactive state | `|t| >= 2.0`, correct sign |
| **Episode-first-month blocking** | Block by calendar month of event; report within-block conditional difference | Same sign as pooled; reported |
| **Overlap correction** | At horizons > event spacing, de-overlap returns before HAC | Applied |
| **BH-FDR** | BH across the test matrix (4 horizons × 11 sectors + pooled; plus suction-active vs inactive cells = ~52 cells; `alpha = 0.10`) | Pooled-active cell survives FDR |
| **Split-half sign-stability** | Split events by calendar median date of suction-active events; same sign of conditional difference in both halves | Required for GO |
| **Effective-N** | Report non-overlapping suction-active events at `horizon_role` | >= 30 for decision-grade |
| **Magnitude floor** | The conditional difference must be economically meaningful | >= 0.5% at 21d — **FROZEN (2026-07-16, adjudicated):** confirmed; a conditional-underperformance claim thinner than 0.5%/21d cannot justify authority even if statistically clean |

**Time-preserving null law (DT-R14 enforcement):** The permutation preserves time structure by permuting the active/inactive label within-month. Naïve i.i.d. bootstrap over event returns is anti-conservative and forbidden (effective N = MONTHS due to cross-sector correlation structure). The sector-level correlation among the 11 ETFs during suction windows is high (all simultaneously lagging in a mega-cap run) — this must be modeled by clustering standard errors at the date level, not the event level.

**Overlap correction on the multi-horizon ladder (house law):** The 10-40d ladder is descriptive. The pre-declared `horizon_role` ruler is the only binding verdict cell (see §2.3).

**Excess-vs-index ruler (house law):** All outcomes are ETF return minus SPY total-return. Absolute sector returns are printed as context only.

### 2.3 Pre-declared horizon_role ruler

**FROZEN (2026-07-16, adjudicated):** `horizon_role` = **21d** (trading days), consistent with S-MLC-1 and the battery's swing 2–4 week ruler. The 10-40d ladder is descriptive; GO/KILL verdicts produced at 21d only.

**`horizon_role`: 21d (trading days).** All binding verdicts reference the 21d horizon.

---

## 3. Verdict mapping (pre-committed)

**Primary verdict question:** "Is conditional mean_excess_return(suction-active) statistically significantly lower than mean_excess_return(suction-inactive) at the 21d horizon?"

- **GO (suction conditioning is real)** — all gates in §2.2 pass; the conditional mean is negative and sign-stable. Enables the W3 suction-ladder state to gate or damp laggard-sector entry recommendations. Specific authority: suction-state may be wired as a DEMOTE trigger in the W2 coherence layer for laggard-sector ACT-NOW entries (demote, not kill — consistent with MLC-R8).
- **ACCRUE** — conditional difference is in the predicted direction but at least one gate is unmet (effective-N < 30, or |t| < 2.0, or fails FDR). The W3 organ ships display-only; no gate authority. Come-back on deeper history or more accrual.
- **NO-GO** — conditional difference is near zero or unconvincing after all corrections. The suction thesis for laggard-bounce suppression is unsupported as a standalone construction. The W3 organ remains display-only, retained as confluence context (non-standalone ≠ worthless per house law §Epistemics). The search space is not closed: alternative constructions of suction conditionality (e.g., conditioning on a different definition of laggard, a different suction metric, or a longer horizon) may be proposed with fresh preregs.
- **KILL** — conditional difference is negative in the WRONG direction (suction-active bounces outperform inactive by a statistically significant margin with correct sign). A kill on this construction does NOT close the suction organ — it closes only the "suction dampens laggard-sector bounce returns" authority claim.

---

## 4. What a GO buys (authority escalation path)

A GO enables the following, no more:

1. W3 suction-ladder state `suction_regime` field is promoted to `CONFIRMER` in `config/qual_ladder.yml` for the specific authority path: demotion of laggard-sector bounce entries in the W2 coherence layer.
2. The W2 coherence layer (ACT-NOW conflicted shelf) may show a chip: "Mag7 suction active — laggard bounce entries historically suppressed" when the suction-active condition holds.
3. No size reduction, no entry suppression beyond the demote-to-conflicted-shelf mechanism (MLC-R8).

A GO does NOT claim the suction organ predicts market-wide returns, broad portfolio performance, or any variable other than laggard-sector bounce entry returns at 21d.

---

## 5. What this pre-reg deliberately does NOT claim

- It does not claim Mag7 leaders continue to outperform during suction regimes (that is S-MLC-1).
- It does not claim entry-timing cost of weekly-wait construction (that is S-MLC-3).
- It does not use RS-dispersion as a gate (MLC-R4; R-4 kill honored — the E1 RS-rank condition defines the *event population*, not a gate on a new signal).
- It does not claim any specific *mechanism* for the suction effect; it tests the empirical conditional return pattern.
- It does not test the hypothesis if the W3 organ is not built (the study is gated on W3 delivery).
- It does not close the W3 suction-organ's display surface regardless of verdict.
- A null here does not imply the suction thesis is false — it implies this construction did not detect it at the pre-declared ruler. Alternative constructions are open per house law §Epistemics (kills are construction-specific).

---

## 6. Deliverables (when W3 ships and threshold stamping APPEND is made)

1. `scripts/s_mlc_2_suction_conditionality.py` — harness (PIT-clean, within-month permutation primary, HAC secondary; cluster SEs at date level for cross-sector events).
2. `reports/s-mlc-2-suction-conditionality.md` — **bold verdict** first, gates table, conditional vs unconditional excess table, "what this does NOT show."
3. Dated APPEND to this pre-reg stamping the exact W3 field names, threshold values, and first reliable date once W3 ships.
4. Registry append to `data/experiments/registry_seed.json` — entry `s-mlc-2-suction-conditionality`, `kind: phase0_backtest`, `registered_on: 2026-07-16`, `come_back_on: <set when W3 ships>`, `prereg: research/S_MLC_2_SUCTION_CONDITIONALITY_PREREG.md`.
5. If GO: `config/qual_ladder.yml` amendment for `suction_regime` field promotion.
6. NO engine wiring in the pre-reg or results PR.

---

Registered 2026-07-16. FROZEN 2026-07-16 (adjudicated freeze record below). Any amendment requires a dated APPEND section, never edits to frozen sections. The threshold-stamping APPEND (when W3 ships) is explicitly pre-authorized above and does not reopen the closed sections.

```yaml
# machine-checkable frontmatter
study_id: s-mlc-2-suction-conditionality
program: mlc
wave: W6
battery: S-MLC-2
registered_on: "2026-07-16"
frozen_on: "2026-07-16"
status: frozen
depends_on: W3-suction-organ  # conditioning variable not yet built
horizon_role: 21d  # FROZEN 2026-07-16: confirmed (swing 2-4w ruler)
effective_n_floor: 30  # FROZEN 2026-07-16: promotion gate not run gate; floor never lowers
primary_test: within-month-event-label-permutation  # DT-R14, cluster at date
authority_target: suction_regime  # qual_ladder key on GO
test_direction: one-sided  # FROZEN 2026-07-16: one-sided PRIMARY (active < inactive); two-sided p printed as receipt
prereg_file: research/S_MLC_2_SUCTION_CONDITIONALITY_PREREG.md
```

---

## Freeze record

*All rulings applied and frozen 2026-07-16. Every parameter of this prereg is now frozen; any amendment requires a dated APPEND, never edits to frozen sections.*

| # | Item | Ruling | Rationale |
|---|---|---|---|
| 1 | C1 threshold | NVDA share of SPX market cap ≥ trailing 756-session 75th percentile AND ≥ 5.0% hard floor | 756d (not 252d) prevents consolidations from flipping state; 5.0% floor keeps early-history percentiles from firing at trivial levels |
| 2 | C2 threshold | Trailing 21-session cw-minus-ew spread > 0 (sign condition; RSP = equal-weight proxy) | Mechanism is directional — cw outrunning ew is the suction signal; sign condition is mechanism-true and simpler than a percentile |
| 3 | C3 duration floor | C1 AND C2 jointly held ≥5 consecutive sessions | Guards against one-day blips without excessive lag |
| 4 | Mixed-zone | Three-way partition (active/inactive/mixed); inference active-vs-inactive only; mixed printed descriptively, never pooled | Clean control group requires excluding mixed-zone contamination |
| 5 | E1 (laggard event) | Sector ETF in bottom 3 of 11 SPDRs by 60-session RS | Leadership Board surface uses 60d RS; study must interrogate the construction as the operator experiences it |
| 6 | E2 (entry fill) | t+1 close. MANDATORY | Same-day close is look-ahead; t+1 close is earliest non-look-ahead fill |
| 7 | Test direction | One-sided PRIMARY (active < inactive); two-sided p printed as receipt | Mechanism is pre-declared directional; one-sided test at α=0.05 is the binding gate |
| 8 | E2 bounce threshold (+2σ) | FROZEN: +2σ of own 252d daily-return σ as of t−1 | Self-normalizing across sector vol regimes; fixed-% thresholds over-select high-vol sectors |
| 9 | E3 earnings-day exclusion | FROZEN: DROPPED from primary; descriptive split only | MLC-R10 — earnings is disclosure, never a gate (matches S-MLC-1 Ruling 4) |
| 10 | Effective-N floor (≥30) | FROZEN: ≥30 confirmed; promotion gate, not run gate; floor never lowers | Below floor → verdict capped at ACCRUE; nulls still published |
| 11 | Magnitude floor (0.5% at 21d) | FROZEN: confirmed | Economic-significance floor independent of p-value |
