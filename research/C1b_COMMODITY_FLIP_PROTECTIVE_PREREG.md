# C1b — Bearish Commodity-Flip PROTECTIVE Gate — PRE-REGISTRATION

**Battery:** C1b (HK/Canada masterplan §4.1, W7-pre follow-up to C1). **Branch:** `hkca-w7pre-c1b`.
**Author:** quant research agent. **Status:** PRE-REGISTERED — committed BEFORE any run.
**Constitution:** masterplan §6 (pre-reg first; HAC; BH-FDR within family; **program-level DSR
`n_trials` via `TrialLedger.with_declared_budget`, program budget now ≈36**; split-half sign-stability;
effective-N = independent episodes; DSR ≥ 0.90 the only door into a scored seam; survivorship bounds;
suspension-honest fills; verdicts GO/NO-GO/KILL/ACCRUE). **NO WIRING** — reports only.

This is the **gated PROTECTIVE test** the C1 report (`reports/c1-commodity-sector-phase0.md`, #1038)
flagged as open: C1 validated-at-ACCRUE the oil→XEG **long** side (HAC t +2.75 at 4w, DSR 0.54) and
found the **bearish** side directionally symmetric but reported it **exploratory/non-gated** (oil→XEG
after a BEAR flip: mean −1.16%/4w, HAC t = −1.78, hit 38%). C1b asks the **demote-gate question**:
after a commodity flips into a BEAR regime, should the CA board **demote** high-oil-beta names?

---

## 0. Provenance & what is reused verbatim (no definition shopping)

The **regime-episode definition is reused VERBATIM from C1** — `research/C1_COMMODITY_SECTOR_PREREG.md`
§2.2 / §2.3 and its harness `scripts/c1_commodity_sector_phase0.py`
(`slope_z`, `regime_state`, `confirmed_flips`, `fwd_excess`), audit-committed at `4c583f7`:
- slope_z of log(close) over **W=63d**, standardized over **252d** (min 200);
- **±0.5 hysteresis** dead-band state machine (+1 bull / −1 bear / 0 neutral);
- **≥20 trading-day** min-duration debounce;
- a **BEAR flip** (the C1b event) = the first day of a new confirmed **BEAR** episode
  (`confirmed_flips(state, target=-1)`) — the exact `target=-1` path C1 already ran as its
  exploratory `T1n` leg;
- **next-bar close fill**, **non-overlapping** greedy episode windows, suspension-honest
  (drop windows past data end; intersect present bars on both legs, no ffill through a gap).

C1b **changes nothing** in that construction. It only (i) promotes the oil→XEG BEAR leg from
exploratory to a **gated protective trial** under the H4 demote bar, and (ii) adds a **within-Energy
name-tier** protective-differential trial. No parameter is re-tuned; no alternative turn definition
is introduced. Any deviation would be definition-shopping and is banned.

---

## 1. Hypotheses

**H-C1b-sector (primary, one-sided SHORT/protective).** After **oil** (`CL_F`) enters a confirmed
**BEAR** regime, the energy sector ETF `XEG.TO` earns **NEGATIVE** excess return vs `_GSPTSE` over
the forward 2–8w window, on NON-OVERLAPPING episode returns. Direction pre-registered **NEGATIVE**
(a protective de-rate: the sector sells off when its commodity turns down). This is the SIGN-MIRROR
of C1's validated long side (same episode machinery, `target=-1`).

**H-C1b-name (name tier, 5y, one-sided).** Within the CA **Energy** sector, after an oil BEAR flip,
**HIGH oil-beta** names underperform **LOW oil-beta** peers over the forward window — the
**protective differential** `D = ret(HIGH) − ret(LOW) < 0`. This is the SIGN-MIRROR of the dropped
C1 catch-up-gap. The red-team's finding that miners/resource names are ~96% **contemporaneous** with
their commodity and the t+1 residual is NEGATIVE (miners anticipate, not lag — `HK_CANADA_REDTEAM_
FINDINGS.md` L99-101) **CUTS FOR this direction**: fast/contemporaneous transmission means high-beta
names de-rate **fast and hard** when oil turns, so the protective differential is *expected* to be
present even though the long catch-up-gap was refuted. Contemporaneity kills a *lag* bet; it powers a
*de-rate* bet.

**H0 (both).** Mean episode excess (sector) / mean episode differential `D` (name) = 0.

---

## 2. Constructions (exact, frozen)

### 2.1 Data (all in-tree in this worktree; no network)
- **Oil:** `data/yahoo/CL_F.parquet` `close` (continuous adjusted WTI, 2000-08→). Local state stamped
  in the report.
- **Sector tier:** `data/canada/XEG.TO.parquet` `close` (energy ETF, dividend-adjusted TR, 2001-03→);
  benchmark `data/canada/_GSPTSE.parquet` `close` (S&P/TSX Composite price index).
- **Name tier:** `data/canada_search/closes.parquet` (219-name CA close panel, **2021-06→2026-06,
  ~5y** — this is the binding history limit on the name tier, stated up front) + sector labels
  `data/canada_search/members.parquet` (`sector` column; **Energy = 38 names**). Beta market control
  = `_GSPTSE` returns (residual-to-TSX oil-beta, consistent with the sector tier's GSPTSE-relative
  excess), computed with the SAME orthogonal-beta method as `engine/canada_factor_beta.compute_betas`
  (regress name daily returns on [intercept, market, oil] via lstsq; oil-beta = the oil coefficient).

### 2.2 Regime-episode definition — REUSED VERBATIM from C1 (§0 above)
BEAR flip = `confirmed_flips(state, target=-1)` on oil's slope_z regime state. One event per bear
episode. No re-tuning.

### 2.3 Sector-tier forward construction — REUSED VERBATIM from C1 §2.3
`fwd_excess(XEG, _GSPTSE, bear_flip_dates, H)`: next-bar-close fill, non-overlapping greedy windows,
suspension-honest. Primary horizon **4w (20d)**; 2/6/8w are robustness-curve rows within the SAME
test (nuisance dimension, not FDR slots). Episode excess = XEG cum TR − GSPTSE cum over the window.
**Protective/short return** for Sharpe/DSR = the sign-flipped excess (a profitable protective signal
= underweighting XEG when it de-rates = `−excess`); the raw excess mean is still reported directly and
the HAC t is on the raw excess (must be ≤ −2.0 to gate).

### 2.4 Name-tier construction (5y panel; POINT-IN-TIME beta; no look-ahead)
For each oil BEAR-flip event date `t0` (from §2.2, restricted to events whose `t0` and full forward
window fall inside the 2021-06→2026-06 name panel):
1. **PIT oil-beta per Energy name:** using ONLY returns up to and including the flip-confirmation day
   `t0` (data known at `t0` close), regress each Energy name's daily returns on
   `[1, mkt(_GSPTSE), oil(CL_F)]` over the trailing **W_beta = 252** sessions (min_obs = 120). The
   oil coefficient is the name's PIT oil-beta. Names with < min_obs overlap at `t0` are excluded from
   THAT episode (not survivorship-dropped globally). **No forward data enters the beta** — strictly
   causal.
2. **HIGH / LOW split (within-Energy, per episode):** rank the qualifying Energy names by PIT
   oil-beta; **HIGH = top tercile, LOW = bottom tercile** (terciles chosen a priori for a ~38-name
   sector → ~12/12; the middle tercile is discarded to sharpen the contrast). If < 9 qualifying names
   at an episode, that episode is dropped (insufficient cross-section).
3. **Forward differential:** equal-weight the HIGH basket and the LOW basket; entry at the **next bar
   close** after `t0`; forward **4w (20d)** primary (+2/6/8w curve). Suspension-honest (drop past data
   end; present-bar intersection). `D = ret_EW(HIGH) − ret_EW(LOW)` per episode. Non-overlapping in
   time (greedy, same rule as §2.3).
4. **Effective-N:** episodes are the unit; the differential is *market-neutralised by construction*
   (HIGH−LOW cancels the common oil-BEAR sector move), isolating the beta-tilt protective edge.

### 2.5 Suspension / survivorship
- **Suspension:** windows past the last available bar are DROPPED (no partial/ffill); leg gaps use the
  present-bar intersection (no ffill through a gap). CA ETFs/names did not halt for weeks over the
  window, but the rule is enforced in code (reused from C1 `fwd_excess`; name tier mirrors it).
- **Survivorship (sector tier):** index/ETF-level — no name-panel survivorship; bound = **none
  material** (XEG/_GSPTSE live to 2026-06-30). Stamped as in C1 §2.4.
- **Survivorship (name tier):** the `canada_search` panel is **current-constituent** (219 live TSX
  names, zero delisted). A name that de-listed after a bear flip (e.g. an over-levered high-beta E&P
  going to zero in an oil crash) is ABSENT — which **biases the protective differential toward zero**
  (the worst high-beta losers are missing, so measured HIGH-underperformance is a **lower bound** on
  the true de-rate). This is the CONSERVATIVE direction for a demote-gate: survivorship makes the
  protective edge look weaker than it is, so a GO-for-demote under this bias is robust. Reported as a
  **bound**, not a sticker: the true `|D|` is ≥ the measured `|D|`.

---

## 3. Trials & families (frozen trial list — 2 GATED)

**GATED FAMILY (C1b) — 2 trials, one BH-FDR family, primary horizon 4w:**
| Trial | Test | History | Direction (pre-reg) |
|---|---|---|---|
| **P1** | oil BEAR flip → XEG excess vs GSPTSE (sector tier) | 2001-03→ | NEGATIVE (de-rate) |
| **P2** | oil BEAR flip → within-Energy HIGH−LOW oil-beta differential `D` (name tier) | **2021-06→ (~5y)** | NEGATIVE (protective differential) |

**EXPLORATORY / robustness (NOT in the FDR family, NOT gated):** the 2/6/8w horizon curve for each
gated trial (nuisance dimension); the raw HIGH-only and LOW-only excess legs of P2 (decomposition,
descriptive). These do not add FDR slots.

Every config counts toward the PROGRAM trial ledger. Per masterplan §6 + the DSR-plumbing regularization
(status-log 2026-07-03), DSR uses `TrialLedger.with_declared_budget(N, family)`; the **program budget is
now ≈36** (grew from 30→32 at hincl2; C1b's 2 gated trials sit inside the ≈36 program count). We declare
**N = 36**.

---

## 4. Statistics (frozen)

For each gated trial (P1, P2), primary horizon 4w, on the NON-OVERLAPPING episode series
(P1: episode excess; P2: episode differential `D`):
1. **HAC t** (`newey_west_tstat`, lags=4). Report mean, HAC se, t, p. (For the demote direction the
   decision quantity is a NEGATIVE t.)
2. **BH-FDR** (`benjamini_hochberg`, alpha=0.10) across the 2 gated one-sided p-values (one-sided
   toward the NEGATIVE alternative: `p_one = p/2 if mean<0 else 1−p/2`).
3. **`bootstrap_effective_t`** (block=21) on the daily in-window stream (P1: daily excess; P2: daily
   `D`) → `t_eff`, the autocorrelation-honest floor. (Computed when the daily stream ≥ 60 obs.)
4. **DSR** (`deflated_sharpe`) at `TrialLedger.with_declared_budget(36, family)`, on the **protective
   Sharpe** = Sharpe of the sign-flipped series (`−excess` for P1, `−D` for P2), so a genuinely
   protective signal has a POSITIVE protective Sharpe and DSR measures whether it clears the
   multiplicity haircut. **DSR ≥ 0.90 is the only door into a scored/wired seam** — but note C1b's
   verdict frame is DEMOTE (§5), so DSR is reported for every trial and enters the GO-for-demote gate.
5. **Split-half sign-stability:** split episodes at **2013-01-01** for P1 (matching C1's a-priori
   split; P1 is full-history). For P2 (5y panel, entirely post-2013) the split is at the **panel
   midpoint 2023-12-31** (a-priori: midpoint of 2021-06→2026-06), stated as such — require the mean
   SAME SIGN (both negative) in both halves. P2's short panel means its split-half is
   **power-limited**; this is stated, not excused.
6. **Effective-N honesty:** report (a) raw bear-flip count, (b) non-overlapping episode count, (c)
   `t_eff`. Name tier additionally reports the median qualifying cross-section size per episode.

---

## 5. Pre-registered GATES & verdict rule (frozen) — the H4 demote bar

**Decision frame = the DEMOTE-gate precedent (H4 bar, masterplan §6.1 / `reports/…`):** H4 became a
**falling-knife DEMOTE gate** on incremental **HAC t ≤ −2.0 + split-half + FDR** with power (effN).
C1b mirrors that bar exactly.

Per-trial verdict (applied to each of P1/P2 at 4w):
- **GO-for-DEMOTE** — ALL of: HAC t ≤ **−2.0** (protective direction) AND passes BH-FDR at 0.10
  within the family AND split-half **SAME-SIGN negative** AND non-overlapping episode N ≥ 8 (power
  floor). DSR on the protective Sharpe reported; DSR ≥ 0.90 additionally required for any *scored*
  wiring (a demote gate can ship on the H4 bar without DSR, exactly as H4 did, but a NO-WIRING report
  simply records both). Here: **GO-for-demote requires the H4 bar (t≤−2.0 + FDR + split-half + N≥8).**
- **ACCRUE** — mean NEGATIVE and (HAC t in (−2.0, −1.0] OR split-half sign-consistent-negative but
  sub-threshold t OR DSR-protective in [0.50, 0.90)). A real-but-underpowered protective signal →
  register + come back.
- **NO-GO** — mean ≥ 0 at 4w (no de-rate), OR split-half SIGN-FLIPS, OR HAC t > −1.0 with
  DSR-protective < 0.50.
- **KILL** — mean significantly POSITIVE (HAC t ≥ +2.0): the sector/high-beta names *outperform*
  after a bear flip → the protective premise is backwards, the gate would demote the wrong names.

Battery-level verdict = the set {P1, P2}. **Honest prior:** C1's exploratory read already put oil→XEG
BEAR at t = −1.78 (short of −2.0) → **P1 ACCRUE-lean is the pre-registered expectation** (a real but
sub-threshold de-rate). P2 is genuinely open: contemporaneity predicts a present differential, but the
5y panel + survivorship-toward-zero + tercile thinning may leave it underpowered → ACCRUE-lean prior.
A marginal result is ACCRUE, not a tortured GO-for-demote.

**No wiring.** Reports only. NOTHING is wired to any live engine or board regardless of verdict.

---

## 6. What this test does NOT show (pre-committed)

- **Not a tradeable protective strategy net of costs.** Episode excess/differentials are gross
  buy-and-hold; a real demote incurs no cost, but the measured de-rate is gross of slippage/borrow.
- **Not causal.** Oil BEAR regimes co-move with USD-up / risk-off / rates states that independently
  de-rate TSX energy; this is association net of the broad-market leg (sector) and net of the
  common sector move (name differential), not identified transmission.
- **Not out-of-sample (walk-forward).** Split-half is in-sample sign-stability. The name tier's PIT
  beta is causal (no look-ahead) but the HIGH/LOW *edge* is still in-sample.
- **Not a name-selection alpha.** P2 tests a within-sector beta-tilt *differential* as a protective
  overlay, not a stand-alone long/short book.
- **Regime-definition-dependent.** All results are conditional on the C1 slope_z + ±0.5 hysteresis +
  20d definition, frozen (not shopped). An alternative turn definition must be pre-registered.
- **Name tier is 5y and survivorship-biased-toward-zero.** P2's `|D|` is a LOWER bound; a NO-GO on
  P2 does not refute the mechanism (it may be power-starved), and an ACCRUE is conservative.
- **DSR n_trials.** Program budget ≈36 via the ledger path (not a literal), per the DSR-plumbing
  regularization; the honest conservative multiplicity count across both markets.

---

## 7. Registry

Experiment id `hkca-c1b-commodity-flip-protective`, kind `phase0_backtest`, program `hk_canada_stocks`,
wave `W7-pre`, phase per verdict, `n_trials_program_dsr` = 36, come_back_on set for a re-run when the
CA name panel lengthens (name tier is the power-starved leg). Appended at the END of the
`data/experiments/registry_seed.json` experiments array. **Nothing wired.**
