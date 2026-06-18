# Stock Conviction Score v2 — Predictive Asymmetric-Opportunity Engine

Status: DESIGN (research-grounded). Builds on v1 (`STOCK_CONVICTION_DESIGN.md`).
Goal: turn the honest-but-weak v1 (ranks by residual momentum, IC 0.012, fails FDR)
into a genuinely PREDICTIVE score that ranks by MEASURED forward-return edge and
spots asymmetric, durable opportunities EARLY. The trustworthy base layer the future
AI layer stands on.

## 0. The decisive finding (from the deep-PIT audit + literature)

On modern point-in-time, survivorship-aware data, the validated cross-sectional edges are:

| Leg | mean IC | IC-IR | t-HAC | q-FDR | L/S Sharpe | verdict |
|---|---|---|---|---|---|---|
| **SUE (earnings surprise)** | **+0.039** | 1.23 | 3.16 | **0.019** | **1.26** | SURVIVES FDR — strongest |
| **Insider net-buy (sector-neutral)** | **+0.029** | — | 2.90 | 0.099 | 0.55 | survives loosely |
| Residual momentum (12-1) | +0.012 | 0.08 | 1.50 | 0.40 | ≤0 | FAILS FDR — weak/context |
| value/quality/profit composite | +0.015 | 0.25 | 1.03 | 0.52 | — | "pure noise" |
| China momentum | −0.001..−0.009 | — | — | — | — | KILL (A-shares mean-revert) |
| HK residual momentum | +0.004 | — | 0.35 | — | −0.22 | KILL (pure beta) |

**v1's central flaw: it ranks by the weak leg (residual momentum) and buries the
validated edges (SUE, insider) as display chips.** v2 inverts this.

> **⚠️ Superseded for SUE (2026 — see `reports/sue-deep-history-phase0.md`).** The +0.039 SUE
> row above is the SHALLOW 2023-2025 read. A deep 2011-2026 re-test collapses SUE's
> cross-sectional edge to ~0 (IC 0.0006, HAC t 0.06, fails BH-FDR); **insider net-buying is now
> the lone (borderline) cross-sectional FDR survivor.** SUE is accordingly demoted
> scored→display on factors.html and re-weighted in `engine/stock_score.py` from the dominant
> EDGE leg to a secondary per-name PEAD confluence leg (insider now leads). This doc is kept as
> the v2 design record; the reconciliation supersedes the SUE "FDR survivor / PRIMARY scored
> leg" claims here and in §2.

From the literature, the highest-value signals NOT yet built (effect sizes cited in
`reports/` research output): **analyst estimate-revision momentum** (Mill Street: top
decile 15.6% vs 8.0% bottom; monthly IC ~0.23 — the fastest, strongest, *early* signal),
**Frog-in-the-Pan continuity** (Da-Gurun-Warachka: continuous-info momentum spread 8.86%,
non-reversing), **52-week-high nearness** (George-Hwang: dominates momentum, does NOT
reverse), **gross profitability** (Novy-Marx: clean in large-caps where momentum is weak),
**downside-beta / co-skewness** (Harvey-Siddique: ~3.6%/yr for genuine limited-downside),
and the **MAX/lottery caution** (Bali et al: high max-return → LOWER returns; a penalty).

## 1. What we optimize for (the objective, made measurable)

A high score = high probability-weighted, ASYMMETRIC, DURABLE, EARLY forward payoff:
- **Edge** — measured positive forward-return rank (will it go higher): validated legs.
- **Entry** — is now the inflection (early, before it's obvious; don't chase): timing gate.
- **Asymmetry** — convex upside / limited downside (how much higher vs how much risk).
- **Durability** — the business survives the holding period (quality).
All conditioned **coarsely** on the macro regime (the dashboard's reason to exist).

## 2. The four axes — v2 legs (each a sector-neutral winsor-z, PIT)

### EDGE (the validated predictive core — drives the RANK)
- **`sue`** — standardized unexpected earnings (FDR survivor). PROMOTED from chip to
  PRIMARY scored leg. (US: EDGAR EPS panel.)
- **`insider`** — Form-4 net opportunistic buying / mcap, sector-neutral (FDR-adjacent).
  PROMOTED to scored leg. Fuse with SUE as the validated "smart-money + earnings" core.
- **`revision`** — analyst EPS estimate-revision momentum (NEW, highest-literature-IC,
  *fast/early*). US via yfinance/Nasdaq revision counts; CN via Eastmoney forecast-history
  diff. VALIDATE before scoring.
- **`mom_q`** — momentum QUALITY: sector-neutral residual 12-1 × Frog-in-the-Pan
  continuity × 52-week-high nearness (NEW; the non-reversing, durable-trend form). Residual
  momentum alone is weak → only its high-quality (continuous, near-high) form is kept.

### ENTRY (timing / inflection — a GATE + modifier, not a return leg)
- cycle ladder hard-gate (downtrend/exit/parabolic → never "Buy"; validated risk-placement).
- pullback-in-uptrend (constructive) vs extended; **MAX/lottery caution** (down-weight).
- volume-confirmed accumulation + volatility-contraction breakout (short-horizon, evidence-
  backed) — NEW, display/entry only.

### ASYMMETRY (convexity / upside — NEW axis)
- **`downside_asym`** — downside-beta vs upside-beta ratio + co-skewness vs benchmark
  (genuine limited-downside). NEW, price-only, PIT.
- sector + thematic-basket tailwind (keep; small, declared sector tilt).
- lottery caution (down-weight high MAX / high recent positive skew — NEVER up).

### DURABILITY (quality — the business survives)
- **`gross_profit`** — gross profits / assets (Novy-Marx). NEW from EDGAR. Clean in large-caps.
- **`inv_conserv`** — low asset growth / conservative investment (Cooper-Gulen-Schill).
- **`fund_trend`** — revenue/margin/FCF acceleration vs sector (NEW, EDGAR quarterly).
- accruals + accounting-quality verdict = FILTER/CAP only (decayed as a return leg).

## 3. Combination (no overfitting)

- Every leg → `sector_neutral_z` (PIT, winsorized). Löwdin-orthogonalize across legs
  (`engine/factor_orthogonal`, already present) to kill collinearity.
- **EVIDENCE-WEIGHTED, not equal**: weight ∝ each leg's own measured out-of-sample IC-IR
  (estimated on a purged in-sample fold; shrunk; floored at 0 so a NEGATIVE-IC leg gets ZERO
  weight, never inverted). SUE/insider/revision carry real weight; noise legs → ~0.
- **Light regime conditioning ONLY** (factor-timing is mostly a mirage — keep coarse):
  (a) vol-scale the composite's conviction sizing by trailing realized vol (causal);
  (b) recession-risk / RORO gate: when recession_risk≥60 or RORO<−1σ, shift weight from
  momentum→quality/low-risk; (c) factor-momentum tilt: nudge a leg's weight up if its own
  recent 6-12m cross-sectional IC was positive & persistent. NO heavy quad-based timing.
- **NO ML stacking** (≈120 effective monthly periods → overfits; de Prado DSR).

## 4. The rank decision (this is the v2 upgrade over v1)

v1 kept the rank on residual momentum because the composite didn't beat it. v2 ranks by the
**validated EDGE blend (SUE + insider + revision, evidence-weighted)** because those legs
DO beat residual momentum on measured IC/Sharpe — gated by the deep-PIT Phase-0
(`scripts/stock_conviction_phase0.py`, extended). Ship the v2 rank for a market ONLY where
the validated blend beats the v1 baseline on BOTH mean rank-IC AND net quintile L/S Sharpe at
63d, family-wide DSR, split-half. Markets where nothing validates (HK) stay an honest
exposure screen. China: reversal/entry-led (momentum dead), validated reversal only.

## 5. Validation infrastructure (now runnable)

Regenerated locally: `_closes_deep.parquet` (1962→2026, 1498 names) + (running)
`sp500_pit_membership` + `_closes_delisted` (survivorship-clean S&P 500, 1996→). The
extended Phase-0 measures the **per-leg IC table** (every candidate leg + the blend), the
quintile L/S Sharpe + DSR + BH-FDR, split-half stability, and the long-only top-decile
DURABILITY (max-DD, Sortino, worst-21d). "Basis inspection" — per-leg IC shipped on the page
so an operator (and the future AI layer) can see WHY the score moved.

## 6. UI / operational improvements

- **Per-leg basis panel** on the stock page: each leg's z + its measured IC tier (validated /
  context / penalty), so the score is legible and trustworthy.
- **Asymmetry axis** shown explicitly (downside-beta, co-skew, convexity read).
- **"Why now" entry line**: the inflection trigger (52wh reclaim / volume accumulation /
  vol-contraction) when present — the "a trader would become interested here" cue.
- **Freshness/responsiveness**: revision-momentum + price legs update daily → the score moves
  FAST on genuine shifts; SUE/fundamentals update on filings (labeled with as-of lag).
- **Regime banner**: which regime tilt is currently applied (e.g., "late-cycle → quality up").
- Per-market trust tier + calibration bands (kept from v1, now backed by measured IC).

## 7. Build order
1. Validation harness extension — measure every candidate leg on deep+PIT (the IC table). ← FIRST (decides weights)
2. NEW price-only legs (cheap, PIT, validatable now): Frog-in-the-Pan, 52wh, downside-asym, MAX-caution → `engine/momentum_quality.py` + `engine/asymmetry.py`.
3. NEW analyst-revision collector (US yfinance + CN Eastmoney) → validate.
4. NEW fundamental legs: gross-profitability, conservative-investment, fund-trend (EDGAR).
5. Rebuild `engine/stock_score.py` v2 composite (evidence-weighted, orthogonalized, regime-coarse, SUE/insider/revision-led).
6. Wire builds (US/CN/CA; HK stays screen) + per-leg basis JSON.
7. Templates: basis panel, asymmetry axis, "why now" line, regime banner.
8. Calibrate + full Phase-0 report + tests + browser-verify + ship.

## 8. v3 — "reason and improve" findings (deep+PIT regime audit, 2008–2026, 63d)

Two harnesses, the owner's two lenses (`scripts/conviction_v2_regime.py` regime-conditional
IC + long-only top-decile; `scripts/pead_freshness_phase0.py` PEAD freshness). Discipline:
measure-before-score, literature prior not data-mining, long-only durability is the objective.

**WON (built into the engine, US only):**
- **`regime_switch` — the EDGE momentum leg is regime-conditional.** Residual momentum's
  forward IC is +0.030 in a calm/risk-on tape (SPY>200dma & lo-vol) but −0.028 in a down
  tape / −0.017 hi-vol; SUE is regime-robust (+0.002..+0.006). Conditioning lifts overall IC
  **0.0098 → 0.0192** and the long-only top-decile to **15.4% ann / Sortino 1.01 / maxDD −35%**
  (SPY 13.4% / −47%) — beats both legs AND a static 50/50 blend. Daniel-Moskowitz (2016)
  "Momentum Crashes" prior. → `_edge_weights(calm)` scales ONLY the momentum context leg
  (0.04 stress → 0.28 calm); `current_calm(SPY)` supplies the live tape; `_regime_tilt` banner.
- **PEAD freshness decay on SUE.** SUE drift decays post-announcement; weighting by
  `exp(−days_since_filing/45)` lifts SUE IC **0.0065 → 0.0085**, IC-IR 0.084 → 0.108, and the
  long-only top-decile **13.3% → 14.0% ann / Sharpe .79 → .82 / maxDD −38.1% → −36.7%** — an
  improvement on EVERY metric, no trade-off. Makes the score early/fast. → `_pead_decay(days)`.
  FOLLOW-UP DONE: `collectors/edgar_eps.py` now overlays the REAL earliest SEC filing date per
  quarter (EDGAR companyconcept, min `filed` over original 10-Q/10-K), replacing the synthetic
  period_end+60d — the real ~34d-median, per-name-staggered date breaks the old ~74% one-value
  cluster and sharpens the freshness decay (synthetic kept only as a per-row fallback). PIT-safe.

**REJECTED (measured, do NOT score — adding them is noise, not power):**
- **Asymmetry / downside-asym (convexity).** Standalone forward IC is NEGATIVE (−0.008); its
  top-decile is high-vol growth (vol 25.7%, DD −47%), not limited-downside. A 25% blend bumps
  Sharpe (0.86) only by adding hidden bull-market beta — IC DROPS to 0.0154 and DD WORSENS.
  Stays DISPLAY-ONLY risk-shape (as v2 had it). `near_52w_high` (−0.009) and `max_caution`
  (−0.006) also negative on this sector-neutral 63d panel.
- **Low-volatility defensive tilt.** Pure low-vol gives the shallowest DD (−32.5%) but BELOW-
  SPY return (11.8%); a stress-conditional low-vol tilt on `regime_switch` gives up more
  return/Sharpe (0.81 vs 0.83) than the ~1pp of drawdown it saves. Poor exchange rate.

**Net:** `regime_switch` is the robust ceiling for price+SUE legs on large-caps; the genuine
remaining power is the validated EVENT edge (SUE) used at its native cadence/freshness, not
more price axes. The honest invariants and the NEUTRAL gate (badge, not rank) are unchanged.
