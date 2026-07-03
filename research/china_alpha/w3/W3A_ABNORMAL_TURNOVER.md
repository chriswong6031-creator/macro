# W3-A — Abnormal-turnover cross-sectional signal (Phase-0)

*China Alpha Program · Wave W3 (volume program, ruling F7) · the flagship phase-0 of the wave.*
*Harness: `scripts/china_turnover_phase0.py`. Report: `reports/china-turnover-phase0.md`. Unit
tests: `tests/test_china_turnover_phase0.py`. Registry: `data/experiments/registry_seed.json`
(id `w3a-abnormal-turnover`). NOTHING wired to any page / board / rank regardless of outcome —
pure research + measurement.*

---

## 1. The hypothesis (external evidence)

In a retail-dominated tape a spike in turnover marks the peak of an attention / overreaction cycle.
Names with **abnormally high** recent turnover subsequently UNDERPERFORM (the demand shock unwinds);
**low / stable** abnormal turnover OUTPERFORMS. It is the microstructure sibling of the one validated
A-share selection edge — short-horizon within-sector reversal — expressed on the VOLUME plane instead
of the price plane.

External evidence (`phase1/ashare-signal-research.md §A`): "Anomalies in the China A-share market"
(2000–2019) — abnormal turnover NEGATIVELY predicts returns; the **low-abnormal-turnover long leg
earns +1.24%/mo, t=3.35** (EW), one-way turnover 254%. Repo status: UNTESTED as a standalone leg; no
`turnover_shape` registry entry. Highest EV × buildability new item in the signal-research ledger.

## 2. The proxy and its documented limitation (pre-registered)

The source uses the **turnover ratio** = shares traded / free-float shares. We hold **no historical
per-name float-share series**, so — exactly as the signal-research doc pre-registered ("volume-z is a
clean fallback that needs nothing else") — we test a **volume-based proxy**:

```
abn_turn = ln( mean(volume, last 21d) / mean(volume, trailing 252d skip the last 21d) )   per name
```

**How the proxy differs from the true ratio, and why it is still the right cross-sectional test:**
- It **omits the float normalisation.** But `abn_turn` is a WITHIN-NAME ratio, so a constant float
  cancels exactly; float only matters if it *changed materially inside the 252d window* (a large equity
  issuance or unlock), which affects a minority of names in any month.
- It is a **share-volume z, not a turnover-ratio z.** For the cross-sectional RANK the anomaly relies
  on, a within-name volume ratio is the closest float-free surrogate.
- **Consequence stated up front:** the numbers here test the MECHANISM on our substrate; they do NOT
  reproduce the paper's +1.24%/mo point estimate, and a positive result is a proxy result. This is
  logged so no downstream reader mistakes a proxy GO for a float-normalised replication.

## 3. Substrate and measurement constitution (binding — masterplan §4)

- **Substrate:** `data/china_stocks_raw/` — append-only, **survivorship-clean**, real per-name volume
  and OHLC (incl. `open`/`high`/`low`) back to 2008 (some names to 1991), fresh to 2026-07-03. **NEVER**
  the trimmed close-only `china_search` panel (which retroactively deletes dropped names — maximally
  destructive to reversal-family signals). Verified: 1568 raw files; after filters 1279 names.
- **Benchmark:** **CSI300-relative excess, always** (`510300.SS` via `lib.store`). The ETF history
  begins **2012-05-04**, which bounds the excess backtest window (169 monthly rebalances,
  2012-05 → 2026-05).
- **Fill realism:** entry at **T+1 (H+L)/2**; **locked-limit rows excluded** at the entry bar
  (`high==low==close` on the raw plane => unfillable, dropped from the entry). Close-to-close reported
  **alongside** (the T+1 grading tax; masterplan measures it ~0.9–1.1pp/entry).
- **Split hygiene (raw-plane specific):** the raw plane is **unadjusted**, so splits / ex-dividends
  appear as single-day price jumps (measured: 143 of 1.2M daily returns exceed |25%|; ~0.19% of 21d
  forward windows are contaminated). Daily returns with **|ret| > 0.25** (beyond the physical A-share
  ±20% limit envelope) are **zeroed** before compounding the forward return — they are corporate-action
  artifacts, not returns. The SIGNAL (volume) is not price-adjusted, so it is unaffected; only the
  return metric is cleaned.
- **Splits:** time-HALF (early / late by rebalance-count median) and **pre/post-2024**.
- **Placebo:** **2000-permutation** label shuffle (seed=3, deterministic) on the primary L/S spread.
- **Positive control:** the VALIDATED 3-month within-sector reversal through the SAME harness must
  reproduce a positive spread (proves the instrument is live, not a dead null).

## 4. Universe filters (pre-registered)

- ≥ **400** trading days of history (stable trailing-252d baseline + rebalance-grid room).
- **ADV floor for fill realism:** trailing-60d median (`close × volume`) ≥ **1e8 yuan** (~US$14M).
  (Universe median ADV ≈ 5.0亿, matching the board's post-#791 median 4.5亿.)
- **Exclude** names whose locked-limit days exceed **20%** of their history (5 names).
- Names without a resolved sector (from `china_search/members.parquet`) are dropped (needed for the
  within-sector reversal residualisation).

Filter accounting (measured): excluded `{history: 44, locked: 5, adv: 142, no_sector: 98}` →
**1279 names** retained.

## 5. Design and the six mandatory tests

- **Monthly rebalance** (calendar month-end → last trading day on/before), **deciles** on `abn_turn`
  (cross-sectional; a **sector-neutral** robustness variant reported alongside).
- **Primary metric = LOW-minus-HIGH decile L/S**, CSI300-relative 21d-forward, **HAC (Newey-West) t**
  (lags=4). "Low-minus-high" because the anomaly's edge is the LOW-abnormal-turnover leg outperforming.

| Test | What it does |
|---|---|
| **T1** | Primary decile L/S spread — full + early/late + pre/post-2024 (+ sector-neutral). |
| **T2** | **Orthogonality** — cross-sectionally residualise `abn_turn` on the **within-sector 3M reversal** signal (mirrors `engine/china_reversal` math: `rev3 = −r63`, within-sector demeaned) each rebalance; report the residual spread. **If residual \|t\| < 2 the signal is REDUNDANT-WITH-REVERSAL** and the verdict says so *regardless of the raw t*. |
| **T3** | Monotonicity across the 10 deciles (Spearman of decile# vs mean excess). |
| **T4** | 2000-permutation placebo (seed=3) on the primary spread. |
| **T5** | **Positive control** — the reversal signal through the same harness must reproduce a positive spread. |
| **T6** | Fill-realistic vs close-to-close gap. |

## 6. Pre-registered verdict thresholds (fixed BEFORE running)

- **GO** — primary fill-realistic L/S **\|t\| ≥ 3** on the FULL window **AND** spread **sign-stable
  across BOTH era splits** (early/late same sign AND pre/post-2024 same sign) **AND** the **T2 residual
  \|t\| ≥ 2** (adds information beyond reversal) **AND** T5 positive control fires.
- **ACCRUE** — **2 ≤ \|t\| < 3** full-sample, **OR** \|t\| ≥ 3 but only in one era (era-only /
  not split-stable), **OR** residual \|t\| in [2,3) while raw is strong — a forward ledger opens,
  nothing wired.
- **NO-GO** — \|t\| < 2 full-sample; **OR** sign-unstable across both splits; **OR** T2 residual
  \|t\| < 2 (**REDUNDANT-WITH-REVERSAL**) regardless of raw t; **OR** T5 positive control fails
  (instrument dead → the whole run is void).

---

## 7. RESULTS

**MACHINE VERDICT: NO-GO** — primary |t|=0.69<2 (null; placebo perm_p=0.511); also sign-unstable
across era splits; residual ⊥reversal |t|=0.72<2 (redundant with reversal). Deterministic
(seed=3), reproduced identically across two runs. Universe 1279 names, 169 monthly rebalances,
CSI300-relative window 2012-05 → 2026-05.

**T1 — primary low-minus-high decile L/S (CSI300-relative, fill-realistic):**

| era | n | mean %/reb | t_HAC | Sharpe | maxDD % | hit |
|---|--:|--:|--:|--:|--:|--:|
| full | 169 | +0.362 | **0.69** | 0.18 | −47.6 | 0.574 |
| early | 85 | +0.904 | 1.32 | 0.44 | −44.9 | 0.647 |
| late | 84 | **−0.186** | −0.24 | −0.10 | −47.6 | 0.500 |
| pre-2024 | 140 | +0.623 | 1.17 | 0.32 | −44.9 | 0.593 |
| 2024+ | 29 | **−0.896** | −0.57 | −0.42 | −47.6 | 0.483 |
| full · sector-neutral | 169 | +0.296 | 0.73 | 0.19 | −48.9 | 0.562 |

Full-sample |t| = 0.69, far below the |t|≥3 GO floor and below the |t|≥2 ACCRUE floor. The sign
**flips** in BOTH splits (early + / late −; pre-2024 + / 2024+ −) — what positive mean exists is an
early-window artifact.

- **T2 orthogonality** — residualising `abn_turn` on the within-sector 3M reversal signal leaves
  t_HAC = **0.72** (mean +0.309%), essentially unchanged from raw (0.69 / +0.362%). Residual |t| < 2
  ⇒ **REDUNDANT-WITH-REVERSAL** by the pre-registered rule. (Moot here since the raw signal is itself
  null, but logged as the constitution requires.)
- **T3 monotonicity** — Spearman(decile#, excess) = **+0.079** (≈ flat, NOT the negative monotone
  gradient the hypothesis predicts). Deciles: D0 +0.80, D1–D8 all in +0.71…+0.99, D9 (highest
  abn-turn) +0.44. The only weakly-hypothesis-consistent feature is D9 being lowest; there is no
  clean gradient.
- **T4 placebo** — real t 0.69 sits at **perm_p = 0.511**, dead center of a clean 2000-shuffle null
  (mean +0.026, sd 1.053). Statistically indistinguishable from a random relabelling. (The null's
  0-mean, sd≈1 shape also validates the placebo instrument.)
- **T5 positive control** — the within-sector 3M reversal through the SAME harness earns a
  **positive** high-minus-low spread: **+0.638%/reb, t_HAC 1.18, Sharpe 0.33**. The instrument is
  **LIVE** and directionally reproduces the one validated A-share edge, so the abn_turn null is a
  **true negative, not a dead harness**. (Weaker than the literature's 0.58 Sharpe / +0.56%/mo
  because this harness is deliberately more conservative than the flagship reversal report: the
  CSI300-relative window is 2012+ only — 169 rebalances vs 388 — and it uses a decile-EXTREME L/S
  D9−D0 with fill-realistic T+1 entries and locked-limit exclusion, versus the report's
  deepest-quintile long-only EW-universe-excess construction. The point of T5 is the SIGN and
  liveness, which both hold.)
- **T6 fill tax** — fill-realistic +0.362%/reb vs close-to-close +0.331%/reb. On an L/S spread the
  T+1 entry tax nets out across the two legs, so the spread-level gap is tiny (−0.03pp); the
  entry-level tax appears at the single-name level (panel-wide fwd_fill mean 1.45% vs fwd_c2c 1.63%,
  ≈0.18pp/entry, consistent with the constitution's documented ~0.9–1.1pp for a single-leg long).

## 8. Interpretation and next step

**This is a well-powered true negative.** The volume-based abnormal-turnover proxy does not reproduce
the paper's +1.24%/mo t=3.35 low-abn-turnover edge on our survivorship-clean CSI300-relative
substrate: the L/S is null (t 0.69), placebo-indistinguishable (perm_p 0.51), sign-unstable across
both era splits, and — to the extent any weak signal exists — subsumed by the reversal factor it is a
volume-plane sibling of (residual t 0.72). The positive control firing confirms the harness can detect
a real A-share edge, so the null is about abn_turn, not the instrument.

**Two candidate reasons the proxy underperforms the paper (both stated as hypotheses, not excuses):**
1. **Float normalisation matters more than assumed.** The paper's turnover RATIO divides by free-float;
   our within-name volume ratio cancels a *constant* float but not float that *changes* (issuance /
   unlocks are common in A-shares). If the true edge lives in the ratio's float leg, a volume-z cannot
   see it. Reopening requires a historical float-share series (not currently held).
2. **Window + benchmark.** The paper is 2000–2019 EW; our CSI300-relative window is 2012–2026, and the
   edge is early-window-only here (pre-2024 +0.62 / 2024+ −0.90) — the abn_turn premium, if it ever
   existed on our tape, has decayed exactly as the reversal-family decay (do-not-rerun: turn/vol-dry-up
   gates) would predict.

**Do-not-rerun ledger update (add to `phase1/phase0-verdicts.md`):** `abn_turn` volume-z proxy as a
standalone cross-sectional leg is **NO-GO / redundant-with-reversal** on the raw CSI300-relative plane.
Do NOT re-run the volume-z construction. **Reopen ONLY** with a materially different design that clears
its own pre-registration and the same gate: (a) a genuine **turnover RATIO** built from a historical
float-share series (the float-normalised signal the paper actually tested), or (b) **turnover
STABILITY** (low variance of turnover) rather than the abnormal-turnover level — the
"Stable-Turnover-Momentum + IVOL" variant the signal-research doc flags as the daily-cost-survivable
form. Neither is buildable today without new float data.

**Wave carry-forward:** the volume plane's flagship candidate is spent for now. The remaining F7 legs
(margin-velocity risk leg after a daily backfill; volume-price DIVERGENCE at bottoms — guarded, since
volume dry-up is FALSIFIED-H4) are independent of this null and unaffected. The orthogonality harness
built here (`_rebalance_spreads(..., residual_on=rev3_sn)`) is reusable for every subsequent volume-leg
phase-0's reversal-redundancy gate.
