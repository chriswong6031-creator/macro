# Residual momentum · trend quality · crash gating — investigation & Phase 0

*research/RESIDUAL_MOMENTUM_TREND_QUALITY.md · 2026-08-05 · branch `claude/residual-momentum-trend-quality-902b21`*

> **Status: research / diagnostic. Nothing here ranks, sizes or gates a live board.**
> The shipped residual leg remains `engine/residual_alpha.py`. This work extends it,
> measures the extension honestly, and reports three nulls and one live lead.

---

## 0. Verdict up front

| # | Question asked | Answer |
|---|---|---|
| 1 | Do the five requested windows differ? | **They are FOUR.** "12−1 months" and "12 months excluding the last 21 days" are the same construction (form 252 / skip 21). |
| 2 | Does residual momentum beat total momentum? | **Directionally yes, at every window** — reproducing Blitz–Huij–Martens on our panel. But nothing clears BH-FDR; magnitudes are tiny. |
| 3 | Which window is best? | **12−1.** The 3−1 window is the worst and turns negative for plain momentum (short-horizon reversal, as the prior work found). |
| 4 | Do the nine trend-quality measures add anything? | **NULL.** No measure survives BH-FDR, and the composite's edge does **not** survive neutralization against residual momentum — it is repackaged momentum plus noise. |
| 5 | Does residual acceleration work? | **Still no.** Negative IC again, replicating the earlier pre-registered KILL. Carried as a diagnostic; excluded from the composite by construction. |
| 6 | Does crash gating help? | **The one live lead.** See §4c — large drawdown and Sharpe improvements, complementary to vol-targeting, but short of the promotion bar. |

**What this changes today: nothing ships.** Per the repo's epistemics, the gauntlet is a
*promotion* gate, not a build gate — this is built, measured, and parked at diagnostic
tier with its nulls printed.

---

## 1. The idea, and what already existed here

The request restates **residual (idiosyncratic) momentum**: regress each stock on common
factors, keep the residual, and rank on the residual's trailing sum rather than on raw
price momentum. The claim — residual momentum is a *more stable* momentum because the
factor and industry exposures that drive momentum crashes have been regressed out — is
Blitz–Huij–Martens (2011).

**This repo had already tested and shipped that idea.** `research/RESIDUAL_ALPHA_MOMENTUM.md`
(2026-06-14) ran a deep 1962→2026 panel and a point-in-time de-biased re-run. Its
verdict — *"a modest, regime-decayed edge — a ranking/context leg, NOT a standalone
alpha engine"* — is the standing prior, and `engine/residual_alpha.py` is the shipped
implementation: market + sector betas, sector-neutral residual info-ratio, one 12−1
window, wired into the US leaders board.

Two of the request's sub-ideas were **already pre-registered and killed** in that work:

- **Residual acceleration / "velocity of change"** — anti-predictive (full-history IC
  −0.012, t −2.7). Dropped from the shipped engine.
- **Short frames as a picker** — the 1-month signal is *reversal* (full-history
  sector-neutral IC −0.046, t −9.5), kept only as an entry overlay.

So the genuinely new surface was narrower than the request implies, and that is what
was built:

| Requested | Already shipped | Built here |
|---|---|---|
| `r = a + b_m·m + b_s·s + b_f·F + e` | market + sector only | **+ size / value / quality / low-vol legs (`F`)** |
| Test 5 formation windows | one (12−1) | **all of them (= 4 distinct)** |
| `Σ ε` construction | info-ratio form | **both, side by side** |
| 9 trend-quality measures | none | **all nine** |
| 6-condition crash gating | generic vol-targeting only | **all six + the gate** |

---

## 2. Construction

```
r_i = α_i + β_m·m + β_s·s̃ + Σ_f β_f·F̃_f + ε_i
```

- `m` = market (SPY). `s̃` = the stock's GICS-sector equal-weight peer return
  **orthogonalized to the market**. `F̃_f` = each factor leg orthogonalized to the
  market, the sector, *and* the earlier legs (Gram-Schmidt, in that order).
- Because the basis is mutually orthogonal, the multivariate OLS slopes **equal the
  univariate slopes** — so every β stays a cheap rolling `cov/var` and there is no
  per-stock matrix solve. This is the trick the shipped engine already used for
  sector-vs-market, extended to K legs.
- All betas are 252d rolling, **lagged one day**, and Vasicek-shrunk (0.66) toward the
  cross-section so a few noisy betas cannot poison the residual.
- Orthogonality is therefore **approximate** — an exact in-window Gram-Schmidt would
  peek at the current window's covariance. That approximation is deliberate and
  inherited from the validated harness.

**Factor legs** are built point-in-time: at each month-end the factor cross-section is
rebuilt as it was knowable then, and the leg's daily return is its equal-weight
top-minus-bottom-quintile spread held to the next month-end. `size` is small-minus-large
on market cap.

> **Honest ceiling on `F`.** Free fundamentals are annual, so value/quality ranks refresh
> ~once a year per name, and the factor history is only as long as the live price cache
> (~3y). **The deep panel has no factor legs at all** — there, the construction reduces
> exactly to the shipped market+sector form (pinned by a cross-engine test). Absent legs
> are reported absent, never imputed to zero.

### Windows

| key | form / skip | note |
|---|---|---|
| `w3_1` | 63 / 21 | 3−1 months |
| `w6_1` | 126 / 21 | 6−1 months |
| `w12_1` | 252 / 21 | 12−1 months |
| `w6_ex5` | 126 / 5 | 6 months ex-last-5d |
| `w12_ex21` | 252 / 21 | **identical to `w12_1`** |

`distinct_windows()` de-duplicates so one construction is not counted twice in the
multiple-testing correction; the collapse is printed in every report rather than
silently applied.

### Trend quality (nine measures, on the residual path)

`slope_t` (OLS slope ÷ its standard error) · `pos_days` · `impulse_legs` (zig-zag leg
count) · `max_dd` · `top3_share` (share of total **absolute** daily movement in the
largest 3 days) · `ud_vol` (log up/down volume) · `atr_dist` (distance from trend origin
in ATR) · `resid_vs_hist` · `resid_accel` *(killed — diagnostic only)*.

Every measure is oriented so higher = better, which is what lets the composite be a
plain mean of z-scores. Only `top3_share` is negated to get there; `max_dd` is already
oriented, since a shallow drawdown (−0.01) is a *larger* number than a deep one (−0.50).
Getting that backwards still produces a plausible-looking composite, so the ordering is
pinned directly by test.

**Equal weights, on purpose.** Fitting leg weights on the same panel the composite is
then scored against is a scorecard grading its own homework.

### Crash gate (six conditions)

`mom_vol` · `rebound` · `xs_corr` · `loser_run` · `breadth_rev` · `extension`, each a
causal **expanding percentile** of its own statistic (unit-free, self-calibrating, no
hand-set thresholds fitted to whichever crash we last looked at). Exposure =
`clip(1 − mean stress, 0, 1)`, **lagged one bar**.

Three deliberate choices that decide whether the gate is real:

1. **`rebound` only fires inside a drawdown.** A fast advance at an all-time high is a
   bull market, not a bear-market rebound; gating on it would cut exposure exactly where
   momentum works best.
2. **A missing input is absent, not a neutral 0.5 vote** — otherwise two live conditions
   read as a six-condition consensus.
3. **"No drawdown" (genuinely zero stress) and "in a drawdown, too little history to
   rank" (unmeasurable → NaN) are different answers.** Collapsing both to 0.0 would
   report *calm* for *cannot tell*.

---

## 3. Harness

`scripts/residual_momentum_phase0.py` — window sweep (BH-FDR across the **whole** grid),
trend-quality per-measure IC + incremental IC over residual momentum, and a crash-gated
backtest against the Barroso–Santa-Clara vol-target baseline. Multiple testing is
**ledgered, not asserted**: every candidate is logged to the Trial Ledger at generation
and the Deflated Sharpe reads its n from there.

Section C **refuses to run on the live panel**: the live cache begins in 2023 and
contains no momentum crash, so a crash gate scored there would grade itself on a sample
with nothing to catch and return a confident null.

---

## 4. Results

Modern era **2002–2026**, deep panel (1,503 names, survivorship-biased), 269 monthly
rebalances, forward 21d, betas 252d shrunk 0.66. Full report:
`reports/residual-momentum-phase0-modern.md`; full-history re-run in
`reports/residual-momentum-phase0-full.md`.

### 4a. Window sweep — residual beats total everywhere, and nothing clears the bar

Sector-neutral mean IC, by window:

| window | `mom_res` (Σε) | `ir_res` (Σε/σ) | `mom_tot` (control) | residual − total |
|---|--:|--:|--:|--:|
| **`w12_1`** | **0.0056** | 0.0053 | 0.0036 | **+0.0020** |
| `w6_ex5` | 0.0023 | 0.0026 | 0.0005 | +0.0018 |
| `w6_1` | 0.0017 | 0.0024 | 0.0004 | +0.0013 |
| `w3_1` | 0.0005 | −0.0003 | −0.0016 | +0.0021 |

Three clean readings:

1. **The residual beats plain momentum at every single window** — the Blitz–Huij–Martens
   claim reproduces on our panel, and it is the most consistent thing in the table.
2. **12−1 is the best window** by a wide margin, and the ranking degrades monotonically
   as the formation window shortens. At 3−1, *plain* momentum turns **negative**
   (−0.0056 raw) — short-horizon reversal, exactly as the prior work found. Excluding
   only the last 5 days (`w6_ex5`) is slightly better than excluding a full month at the
   same 6-month formation, but both are far behind 12−1.
3. **Σε and Σε/σ are a coin flip** (0.0056 vs 0.0053). Nothing here justifies preferring
   one construction over the other.

**But the honest headline is the null:** best t_HAC 0.84, **nothing survives BH-FDR(10%)**
(best q ≈ 0.997 across the 24-cell grid). These are real-direction, no-magnitude effects.
That is the same verdict the shipped leg already carries, now confirmed across the
window table rather than at a single window.

### 4b. Trend quality — NULL, and it is repackaged momentum

| measure | mean IC | t_HAC | survives FDR |
|---|--:|--:|---|
| `slope_t` | 0.0056 | 0.87 | no |
| `pos_days` | 0.0036 | 0.57 | no |
| `top3_share` | 0.0029 | 0.68 | no |
| `composite` | 0.0024 | 0.35 | no |
| `max_dd` | −0.0019 | −0.21 | no |
| `resid_vs_hist` | −0.0023 | −0.37 | no |
| `impulse_legs` | −0.0033 | −1.09 | no |
| `resid_accel` *(killed prior)* | −0.0052 | −1.07 | no |

`ud_vol` and `atr_dist` are **not scored** — they need volume and high/low, which the
deep close-only panel does not carry. Reported absent, not imputed.

**The decisive test is the incremental one.** Neutralized against residual momentum, the
composite's small positive IC (0.0022) does not merely shrink — it **flips sign**
(−0.0017). Trend quality on this panel carries **no information independent of the
momentum score it describes**.

`resid_accel` prints negative again (−0.0052), directionally replicating the earlier
pre-registered kill (full-history −0.012, t −2.7). **The kill stands.**

> The battery still does what it was built to do *mechanically* — on constructed paths
> with identical total residual, the two-gap-day name scores `top3_share` 0.36 vs the
> accumulator's 0.08, and the composite ranks the accumulator higher. It discriminates.
> It just does not predict.

### 4c. Crash gating — the one live lead

All six conditions live. Mean exposure 0.611.

| variant | Sharpe | cum % | max DD % | skew | DSR | bootstrap Sharpe CI | P(SR>0) |
|---|--:|--:|--:|--:|--:|---|--:|
| ungated | 0.10 | 5.7 | −64.1 | −1.42 | 0.04 | [−0.33, 0.11, 0.57] | 0.673 |
| crash-gated | 0.32 | 73.7 | −28.6 | −1.63 | 0.25 | [−0.09, 0.33, 0.79] | 0.937 |
| vol-target (Barroso) | 0.29 | 67.6 | −35.7 | −0.47 | 0.21 | [−0.13, 0.30, 0.75] | 0.913 |
| **gate × vol-target** | **0.48** | **80.0** | **−13.7** | **−0.35** | **0.54** | **[0.07, 0.49, 0.93]** | **0.987** |

**The two gates are complementary, not redundant.** They read different information —
the crash gate reads cross-sectional/regime state, vol-targeting reads the sleeve's own
volatility — and stacking them beats either alone on every column at once: Sharpe
0.10 → 0.48, max drawdown −64% → −14%, and skew −1.42 → −0.35 (the left tail that makes
momentum crashes what they are). It is the only variant whose bootstrap Sharpe CI
excludes zero.

**The gain is timing, not de-risking.** Sharpe is scale-invariant, so holding 0.611
exposure on average cannot by itself move the Sharpe column.

**Per era — not one episode:**

| era | SR ungated | SR both | maxDD ungated | maxDD both |
|---|--:|--:|--:|--:|
| 2004–2010 | −0.46 | **+0.26** | −62.2% | **−12.4%** |
| 2010–2016 | 0.53 | **0.86** | −16.0% | **−6.3%** |
| 2016–2022 | −0.06 | **0.27** | −41.7% | **−11.3%** |
| 2022–2026 | 0.75 | *0.62* | −21.5% | **−9.7%** |

**Drawdown improves in 4 of 4 eras; Sharpe in 3 of 4.** The 2022–26 Sharpe loss
(0.75 → 0.62) is the honest cost of the insurance: gating in a *good* momentum regime
gives up return. That the drawdown result holds in every block — including the two eras
where the ungated sleeve made money — is what separates this from a 2009 detector.

**Still short of promotion.** Best DSR 0.54, far below the 0.90 bar, over 38 ledgered
trials. And the underlying sleeve is barely profitable ungated (Sharpe 0.10) on a
survivorship-biased panel — the gate is improving something that is itself not
established.

> **Why the gate result is more robust to survivorship than the levels are.**
> Survivorship inflates the gated and ungated sleeves *alike* — both trade the same
> names. The *difference* between them is therefore the less contaminated number, which
> is why the drawdown deltas deserve more weight than the absolute Sharpes.

---

## 4d. How this can be used

Ordered by what the evidence actually supports:

1. **Crash gating is the part worth pursuing.** It is a *risk* lever, not an alpha claim
   — and risk levers are where this panel's evidence is strongest (a drawdown
   improvement replicated in 4 of 4 eras is a much sturdier thing than an IC of 0.005).
   The natural next step is a **pre-registered** gate test on the sleeves that actually
   ship, with the exposure scalar as the deliverable rather than a new ranking.
2. **Keep the 12−1 window** for the shipped residual leg. The sweep confirms the
   existing choice is the right one and quantifies what the alternatives cost — that is
   a settled question now, not a standing "should we try other windows?"
3. **Do not add trend quality to a ranker.** It measures what it claims to measure but
   adds nothing beyond momentum. It may still earn a place as *display* context ("this
   name's move came from two gap days") — a descriptive read a user can act on, which
   is a different claim from predictive power and needs no gate.
4. **Do not resurrect acceleration.** Second independent negative.
5. **Industry momentum stays modeled separately** — which is what stripping `β_s·s̃`
   already accomplishes. The request's instinct here matches what the engine does.

---

## 5. Traps handled

- **Short-window betas** → 252d rolling, shrunk, lagged.
- **Sector ⟂ index collinearity** → orthogonalize, then decouple into univariate betas.
- **Multiple testing** → BH-FDR over the whole candidate grid; DSR reads a ledgered n.
- **Look-ahead** → pinned by test: truncating the future cannot change past residuals,
  past percentiles, or the gate's exposure.
- **The skipped window** → pinned: a spike inside the skipped tail must not reach the signal.
- **Survivorship** → the deep panel is current-members-only, which inflates momentum.
  A modern-era *failure* to clear the bar is therefore conservative; a *pass* is optimistic.
  The gate comparison is more robust to this than the levels are: survivorship inflates
  gated and ungated sleeves alike, so the *difference* is the less contaminated number.
- **One-episode risk** → §4c prints a per-era breakdown, losing eras included.
- **Constant de-risking masquerading as timing** → Sharpe is scale-invariant, so holding
  less on average cannot move it; mean exposure is printed beside the Sharpe lift.

---

## 6. Literature

- Blitz, Huij & Martens (2011), *Residual Momentum*.
- Moskowitz & Grinblatt (1999), *Do Industries Explain Momentum?* — industry momentum
  belongs in its own model, not smuggled into the single-stock score (which is precisely
  what stripping `β_s·s̃` accomplishes here).
- Daniel & Moskowitz (2016), *Momentum Crashes* — the left tail and its regime.
- Barroso & Santa-Clara (2015), *Momentum has its moments* — scale by the sleeve's own
  realized volatility.
- Moreira & Muir (2017), *Volatility-Managed Portfolios*.
- Jegadeesh (1990) / Lehmann (1990) — short-horizon reversal.
