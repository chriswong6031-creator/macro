# S-MLC-1 — Leadership Continuation · PRE-REGISTRATION

**Battery:** S-MLC-1 (MLC masterplan §W6, study 1 of 3).
**Program:** Megacap & Leadership Coherence (MLC, chartered 2026-07-14).
**Author:** research agent (Sonnet). **Adjudicated 2026-07-16** — all freeze-review markers resolved; see freeze record at end of document.
**Pre-reg committed:** before any measurement run. No harness code in this PR.
**Wiring:** NONE. This pre-reg gates AUTHORITY only (rank/size/gate). Display surfaces ship freely regardless of verdict (MLC-R2; house law §Epistemics).

---

## 0. Question and honest prior

**Question.** Does `mag7_regime` cohort `trend_state` ∈ {`turning_up`, `running_broad`, `running_narrow`} predict forward **cap-weighted Mag7 excess return vs SPY** over the 10-80d horizon ladder?

This is the directional claim underlying every escalated Mag7 cohort call on the dashboard. If it fails the gauntlet, the cohort state is retained as a context/display signal (confluence use) but may not gate rank, size, or entry authority.

**Mechanism hypothesis.** When the Mag7 cohort enters a confirmed uptrend state, the underlying drivers (earnings-revision breadth, index-rebalancing mechanics, momentum-chasing institutional flows) tend to persist over multi-week horizons because the reversal friction is high for mega-cap index constituents. Laggard rotation is slower than the popular narrative suggests; capital that enters a running regime tends to extend rather than immediately rotate.

**Honest prior.** Equity momentum at single-name and cohort level is broadly documented in academic literature, but the specific claim here is *cohort-state* (a coarse three-value label) predicting *cap-weighted excess* at 10-80d. Coarse labels that collapse a continuous signal into three states typically attenuate IC vs the continuous underlying. The early accrual window (ledger began 2026-07-10; only three dated rows as of pre-reg) means the live study is accrual-gated (see §2). Prior lean: **weakly positive but power-starved until episodes accrue**. Honest committed expectation at the time of this freeze: **likely ACCRUE at first read, not GO**.

**Standing kills honored.** A search of `research/DO_NOT_REBUILD.md` found no prior kill that directly overlaps the S-MLC-1 construction (M7C cohort-state → Mag7 cap-weighted excess vs SPY). The closest adjacent entry is `Shock→archetype beneficiary/casualty ("shelter") map` (§1, TI-R5), which was killed for "laundered directional escalation on *nulled continuation* claims" — note the qualifier: that kill was for continuation claims that were *already nulled*; S-MLC-1 is the fresh pre-registered test that either confirms or nullifies the claim. The kill does not pre-empt this study; it pre-empts proceeding to authority *after* a null. The `sector_rotation_schedule.v1` kill (§1) is not implicated (S-MLC-1 does not produce a rotation schedule). No §2 kill is adjacent. This section may be updated if the adjudicator identifies an overlap missed here.

---

## 1. Data construction

### 1.1 Primary data source

**Live ledger:** `data/mag7_regime/ledger.jsonl`

As of 2026-07-16 (pre-reg date), this ledger contains **3 rows** (2026-07-10, 2026-07-13, 2026-07-15). This is insufficient for any statistical inference.

The study therefore has two data components:

**(A) Reconstructable PIT history:** M7C cohort state is a function of `data/rs_series/` individual member closes, the M7C engine's threshold logic, and SPY closes (all in `data/yahoo/`). A PIT reconstruction going back to M7C inception (~2026-06 per `#2273-79` reference in masterplan §2) is *possible in principle* by replaying `engine/mag7_regime` logic over committed close history. However: (i) the reconstruction is only as PIT-clean as the engine's own historical completeness; (ii) any reconstruction path must be declared here, not selected post-hoc. If a reconstruction is used, it must be pre-declared, run identically in both forward and backward evaluation, and its earliest reliable date must be reported honestly in the results.

**FROZEN (2026-07-16, adjudicated):** PIT reconstruction from committed close history (replay of `engine/mag7_regime`) is ALLOWED as a SECONDARY evidence lane over the window **2015-01-02 → 2026-05-31** with a HARD STOP at 2026-05-31. The 2026-06-01 → registration-date window is excluded as design-contaminated (the M7C thresholds were designed in July 2026 with awareness of the June–July run; applying them back over that window would evaluate the exact tape they were calibrated on). The PRIMARY lane is strict accrual from the registration date (2026-07-16 →). The reconstruction lane supplies additional statistical power and a contemporaneous read; it does not substitute for the accrual-lane verdict.

considered and rejected: accrual-only (insufficient power for years; dismissed); reconstruction with no exclusion window (look-ahead via threshold calibration on evaluated tape; dismissed); reconstruction through registration date (same calibration contamination; dismissed).

**(B) Forward-accruing from pre-reg date:** dates ≥ 2026-07-16 in `data/mag7_regime/ledger.jsonl`. These are unambiguously PIT and constitute the authoritative evidence stream. Retroactive states (A) may be used as supplementary context but may not substitute for or over-ride the accrual-gated inference (see §2 for the episode floor).

### 1.2 Outcome construction

**Mag7 cap-weighted excess return vs SPY:**

- Mag7 members: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA.
- Cap weights: use SPX constituent weights as of the episode start date from the last committed `data/etf_holdings/SPY` snapshot (forward-looking weights are unavailable PIT; use beginning-of-episode weight as the approximation — declare and stamp this approximation, as it introduces a minor look-ahead through weight changes within the episode).
- Benchmark: SPY total-return (dividend-adjusted close from `data/yahoo/SPY.parquet`).
- Forward return: measured close-to-close from the day *after* the state is recorded (fills at T+1 open, measured at T+1+h close), horizons h = 10, 21, 40, 63 trading bars (roughly 2w, 4w, 8w, 13w — the "10-80d ladder" per MLC masterplan §W6).

**FROZEN (2026-07-16, adjudicated):** The return basis is **total-return (dividend-adjusted)** on BOTH legs — both the Mag7 cap-weighted portfolio and the SPY benchmark must use dividend-adjusted closes. The harness MUST assert and print the return basis explicitly before any run. If a data source is found to be price-return only, the run must be halted and the basis corrected before producing any result. This is a non-negotiable data-integrity requirement.

considered and rejected: price-return on both legs (masks the dividend-yield differential between Mag7 and SPY; dismissed).

### 1.3 Episode definition

An **episode** is defined as a contiguous block of trading days during which `trend_state` is constant in the set {`turning_up`, `running_broad`, `running_narrow`}. The episode start date is the first day the state enters that set (from outside it, i.e., from `neutral` or any future non-continuation state). The episode end date is the first day the state exits the set.

**State transitions are recorded once per trading day** (nightly engine). Non-trading days are interpolated by holding the last known state (no spurious transitions on weekends/holidays).

**Non-continuation states** (`neutral`, and any future states outside the three above) define the out-of-set baseline. Their forward returns are computed identically and used as the natural control group.

### 1.4 Exclusions

- Exclude the first episode if it begins within 5 trading days of the first committed ledger row (insufficient warm-up for the state to be meaningfully established).
- **FROZEN (2026-07-16, adjudicated):** The PRIMARY ruler has NO earnings-window exclusion (MLC-R10: earnings is disclosure, not a gate; removing earnings windows introduces selection bias by systematically excising high-volatility disclosure periods). The ≥2-of-7-members-reporting split is printed as a **descriptive secondary** statistic only — it must appear in the report for transparency but carries no verdict weight and may not flip or override the primary result.

  considered and rejected: primary exclusion of ≥2-of-7 earnings windows (introduces selection bias; MLC-R10 violation; dismissed).

---

## 2. Pre-registered gates and episode floor

### 2.1 Episode floor (accrual gate)

**This study does not run until the following floor conditions are met:**

**FROZEN (2026-07-16, adjudicated):** The episode floor is a TWO-LANE gate:

- **Reconstruction lane** (secondary evidence): requires ≥20 non-overlapping 21d episodes over the window 2015-01-02 → 2026-05-31. This lane may run as soon as the reconstruction harness is built; it produces contextual evidence but cannot alone authorize PROMOTION.
- **Accrual lane** (primary evidence): PROMOTION additionally requires ≥8 post-registration non-overlapping 21d episodes (post-2026-07-16) AND sign-consistency between the two lanes (both lanes must show the same directional point estimate). A PROMOTION verdict is blocked if the accrual lane has fewer than 8 episodes or if the signs diverge across lanes.

Rationale: reconstruction buys statistical power that the early accrual window cannot supply, but the exclusion of the design-contaminated 2026-06-01→ window means the reconstruction lane cannot alone demonstrate that the M7C construction generalizes beyond its own calibration sample. Sign-consistency between the independent lanes is the promotion gate.

considered and rejected: accrual-only with 20-episode floor (first read 2028-2031; impractical; dismissed); reconstruction-only with no accrual check (no out-of-calibration-sample evidence; dismissed); 10-episode floor with "indicative" label (too weak for promotion; dismissed).

**Interim reads are diagnostic only** — they may be produced for internal operator awareness but may not produce a GO/KILL verdict until the floor is met.

**Come-back dates:**

**FROZEN (2026-07-16, adjudicated):** Two come-back dates apply under the two-lane structure:
- **Reconstruction lane read:** as soon as the harness is built and the 2015-01-02 → 2026-05-31 window is replayed (no wait required; episodes exist historically).
- **Promotion come-back:** when ≥8 non-overlapping 21d accrual-lane episodes have been observed (post-2026-07-16). At ~4 M7C trend transitions per year, this is estimated at **2028-07-16** (two years accrual). The promotion come-back may advance if transition frequency is higher than estimated — the harness reports the live accrual count on each run.

### 2.2 Statistical gates — ALL must pass for a GO verdict

| Gate | Rule | Required for GO |
|---|---|---|
| **Primary test** | Within-month episode-label PERMUTATION (DT-R14 primary): permute episode-start labels within calendar month, 10,000 draws, compute mean excess return for continuation states; p-value = fraction of permutations exceeding the observed mean | p < 0.05, correct sign |
| **HAC t-statistic** | Newey-West HAC t on the excess return series at the pre-declared `horizon_role` ruler (see §2.3), `lags = floor(n_episodes^(1/3))` | `|t| >= 2.0`, correct sign |
| **Episode-first-month blocking** | Supplement to permutation: block by first month of each episode and report within-block variation | Same sign as pooled; reported |
| **Overlap correction** | At horizons > episode length, returns from overlapping windows must be de-overlapped before HAC (Hodrick 1992 or Newey-West with appropriate lag selection) | Applied and reported |
| **BH-FDR** | Benjamini-Hochberg across the horizon family (4 horizons × 3 state-buckets + pooled all-continuation = 13 cells; `alpha = 0.10`) | Survives FDR for the `horizon_role` cell |
| **Split-half sign-stability** | Divide episodes by calendar median date; both halves must have the same sign on excess return | Same sign both halves |
| **Effective-N honesty** | Report `n_episodes_nonoverlapping` (not row count) at each horizon | `n_episodes_nonoverlapping >= 20` at the `horizon_role` horizon for a decision-grade verdict |
| **State-bucket disaggregation** | Report `turning_up`, `running_broad`, `running_narrow` separately in addition to pooled | Pooled is the primary verdict cell; per-bucket is context |

**Time-preserving null law (DT-R14 enforcement):** Ticker-cluster or episode-cluster bootstrap CIs *without* time control are anti-conservative (effective N = MONTHS, not episodes). The permutation test above preserves time structure by permuting within-month. Any supplementary bootstrap must use within-month episode-label permutation as the re-sampling unit, never naïve i.i.d. bootstrap over episode returns.

**Overlap correction on the multi-horizon ladder (house law):** The 10-80d ladder is descriptive. Verdicts are produced ONLY at the `horizon_role` ruler (see §2.3). Reporting returns at all four horizons is required for transparency but a GO/KILL is determined solely at the `horizon_role` horizon. Verdicts at non-declared horizons are FORBIDDEN per §3 of DO_NOT_REBUILD.md wrong-ruler law.

**Excess-vs-index ruler (house law):** All outcomes are reported as Mag7-cw minus SPY total-return. Absolute Mag7 returns are printed as diagnostic context only and never used for a verdict. Long-horizon absolute returns are especially misleading (drift contamination).

### 2.3 Pre-declared horizon_role ruler

**FROZEN (2026-07-16, adjudicated):** `horizon_role` = **21d** (trading days). This is the swing 2–4 week ruler the Leadership Board serves. The 10-80d ladder remains descriptive — all four horizons are reported, but GO/KILL verdicts are produced ONLY at the 21d horizon.

considered and rejected: 10d (fastest but noise-dominated; dismissed); 40d (longer accrual required; dismissed).

**`horizon_role`: 21d (trading days).** All verdicts in this document reference the 21d horizon.

---

## 3. Verdict mapping (pre-committed)

- **GO** — all gates in §2.2 pass at the `horizon_role` horizon. Enables escalation of M7C `trend_state` to CONFIRMER+ on the qual_ladder, allowing scored use in size/rank/gate contexts per MLC-R2.
- **ACCRUE** — positive point estimate (excess mean > 0, HAC t > 0) but at least one of {`|t| < 2.0`, fails FDR, fails split-half, effective-N < 20} is unmet. The M7C trend_state remains DISPLAY; come-back date set to when effective-N floor is met.
- **NO-GO** — excess mean ≈ 0 or positive but DSR-equivalent power insufficient to distinguish from noise. No change to display status. Continuation as confluence input retained (non-standalone ≠ worthless, house law §Epistemics).
- **KILL** — excess mean is negative AND sign-stable AND HAC |t| >= 2.0 (anti-predictive). A kill closes this specific construction (M7C cohort-state → Mag7-cw excess at 21d), not the search space. A construction kill triggers a DO_NOT_REBUILD.md append per house law.

---

## 4. What a GO buys (authority escalation path)

A GO at the `horizon_role` horizon enables the following specific changes, no more:

1. `config/qual_ladder.yml`: promote `mag7_cohort_trend_state` from `DISPLAY` to `CONFIRMER` (or `SCORED` depending on evidence strength — **NOT ADJUDICATED: the CONFIRMER vs SCORED tier distinction was not resolved in the 2026-07-16 freeze ruling; this decision is deferred to the results PR when evidence strength is known**).
2. The M7C cohort strip on the Leadership Board (W1) may display a strength-of-evidence chip ("trend continuation historically confirmed — N episodes").
3. Any rank/size/gate authority downstream of M7C `trend_state` may be proposed in a subsequent PR, citing this study's GO verdict and referencing the registered outcome.

A GO does NOT automatically wire any entry gate, size adjustment, or rank change. Those require a separate construction proposal citing this evidence.

---

## 5. What this pre-reg deliberately does NOT claim

- It does not claim individual Mag7 names continue (only the cap-weighted cohort).
- It does not claim laggard sectors underperform during continuation runs (that is S-MLC-2).
- It does not claim the entry/timing edge of a weekly-wait construction (that is S-MLC-3).
- It does not test any construction other than M7C cohort state → Mag7-cw excess vs SPY at 21d.
- It does not use LLM-originated verdicts, signals, or escalations at any step (house law §1).
- It does not claim that a null makes the cohort state worthless — a null makes it display-only; it is retained as a confluence input per house law §Epistemics.

---

## 6. Deliverables (when the floor in §2.1 is met)

1. `scripts/s_mlc_1_leadership_continuation.py` — harness (PIT-clean, time-preserving permutation primary, HAC secondary, overlap-corrected horizons).
2. `reports/s-mlc-1-leadership-continuation.md` — **bold verdict** first, gates table, honest effective-N count, "what this does NOT show," horizon ladder printed.
3. Registry append to `data/experiments/registry_seed.json` — one entry `s-mlc-1-leadership-continuation` with `kind: phase0_backtest`, `registered_on: 2026-07-16`, `come_back_on: <adjudicator-set>`, and `prereg: research/S_MLC_1_LEADERSHIP_CONTINUATION_PREREG.md`.
4. If verdict = GO: `config/qual_ladder.yml` amendment (new row for `mag7_cohort_trend_state`), companion PR per house law.
5. NO engine wiring in the pre-reg or results PR.

---

Registered 2026-07-16. FROZEN 2026-07-16 (adjudicated freeze record below). Any amendment requires a dated APPEND section, never edits to frozen sections.

```yaml
# machine-checkable frontmatter
study_id: s-mlc-1-leadership-continuation
program: mlc
wave: W6
battery: S-MLC-1
registered_on: "2026-07-16"
frozen_on: "2026-07-16"
status: frozen
horizon_role: 21d  # FROZEN 2026-07-16: confirmed (swing 2-4w ruler)
episode_floor_reconstruction: 20  # non-overlapping 21d episodes in 2015-01-02→2026-05-31 window (secondary lane)
episode_floor_accrual_promotion: 8  # non-overlapping 21d episodes post-2026-07-16 (required for PROMOTION; plus sign-consistency across lanes)
primary_test: within-month-episode-label-permutation  # DT-R14
authority_target: mag7_cohort_trend_state  # qual_ladder key on GO
prereg_file: research/S_MLC_1_LEADERSHIP_CONTINUATION_PREREG.md
```

---

## Freeze record

*All rulings applied 2026-07-16. Every item resolved by adjudication.*

| # | Item | Ruling | Rationale |
|---|---|---|---|
| 1 | PIT reconstruction (§1.1A) | ALLOWED as a SECONDARY evidence lane over 2015-01-02 → 2026-05-31 with a HARD STOP at 2026-05-31; the 2026-06-01 → registration window is excluded | Reconstruction buys power; the exclusion window guards against thresholds fit on the evaluated tape (design contamination) |
| 2 | Episode floor | Reconstruction lane requires ≥20 non-overlapping 21d episodes; PROMOTION additionally requires ≥8 post-registration accrual-lane episodes AND sign-consistency between the two lanes | No promotion on reconstruction alone; accrual lane provides out-of-calibration-sample evidence |
| 3 | horizon_role | 21d (the swing 2–4 week ruler the Leadership Board serves); 10-80d ladder stays descriptive | Canonical window with most power and least overlap for this board's purpose |
| 4 | Earnings-window exclusion | PRIMARY = NO exclusion (MLC-R10: earnings is disclosure, not a gate); the ≥2-of-7-reporting split is printed as a descriptive secondary only | Earnings exclusion introduces selection bias by removing high-volatility disclosure periods |
| 5 | Return basis | Total-return (dividend-adjusted) on BOTH legs; harness must assert and print the basis before any run | Eliminates dividend-yield differential bias between Mag7 and SPY |
| — | qual_ladder tier (CONFIRMER vs SCORED) | NOT ADJUDICATED — deferred to results PR when evidence strength is known | Tier distinction requires knowing the magnitude and stability of the effect |
