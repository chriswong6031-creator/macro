# Residual Alpha Momentum — Viability Assessment

*research/RESIDUAL_ALPHA_MOMENTUM.md · 2026-06-14 · branch `quant-factor-expansion`*

**Verdict (Phase 0 complete): the idea works — ship a sector-neutral momentum winner-picker, use the *residual* (beta-stripped) construction, pair it with a short-term-reversal entry overlay, and drop the "velocity/acceleration" leg.** Across a deep 1964→2026 panel (1,506 names, fetched for this test) the operator's core instinct holds: cross-sectional relative momentum *does* rank future winners. Three things resolved decisively:

1. **Momentum is real and significant** — full-history `mom_tot` IC 0.027, t-HAC 3.7, **survives BH-FDR**, +2765% long-short, DSR 0.93 — and **beta-stripped, sector-neutral *residual* momentum is the more durable variant in the modern era**: on 2002–26 the residual long-short returns Sharpe 0.33 / +319% vs plain momentum's 0.12 / **−5.5%** (post-2000 decay hit *plain* momentum hardest — precisely the Blitz–Huij–Martens robustness claim).
2. **The short timeframes are *reversal*, not a picker** — 1-month sector-neutral reversal is the single most significant effect (IC −0.046, t −9.5 full-history). The 2024–26 "continuation" was a regime exception, not the rule.
3. **"Velocity of change" / acceleration is anti-predictive — KILLED** — significant *negative* IC in every deep panel (t −2.7 full-history).

**Honest ceiling:** on the modern era *nothing* clears the strict BH-FDR/DSR bar — these are real-but-modest, crowded, post-publication edges (and the FDR-surviving full-history numbers carry survivorship + pre-2000 tailwinds). Ship as a ranking / context / tilt leg, **not** a standalone market-neutral alpha engine. Measured numbers in §4a.

---

## 1. The idea & honest reframe

**As stated (operator):** each stock has its own beta and Sharpe; its sector has its own. Remove the beta from both and the remaining gain is alpha. Track a large basket per sector, analyze price action across daily → 2d → 3d → weekly → monthly, and use the **velocity and amplitude** of each stock's alpha relative to its peers / sector / subsector / wide index to surface stocks that have *consistently* — or have *just started to* — outperform. Use this to pick winners.

**What is true (and now measured here):**

- **`return − β·benchmark = residual = alpha`** is the correct decomposition. Sorting on that residual is **residual / idiosyncratic momentum** (Blitz–Huij–Martens 2011): ~2× the risk-adjusted profit of total momentum and far milder crashes, *because* the factor exposures that cause momentum crashes are regressed out. **Confirmed directionally on our data** (§4a): in the modern era the residual long-short is materially more durable than plain momentum.
- **Nesting the benchmark works, and sector-neutral is consistently best.** Moskowitz–Grinblatt (1999): industry carries much of single-stock momentum. The within-sector ("winners within a sector") variant is the operator's exact framing — and it ranks at or near the top in every panel.

**What had to be reframed (and the data settled it):**

1. **Short horizons are REVERSAL, not the picker.** The 1-month signal has a strong *negative* IC over 1964–2026 (sector-neutral t −9.5). The picker is the medium horizon (formation ≈ 252−21d). The short frames become a **contrarian entry-timing overlay** — buy the medium-term winner that *recently pulled back*, not the one that just spiked. *Regime nuance:* the sign flips to continuation for high-turnover near-52wk-high mega-caps (the 2024–26 broad panel showed +0.045) — so the overlay's sign must itself be conditioned on regime.
2. **Never estimate short-window betas.** Betas are a 252d rolling estimate, lagged 1d, **shrunk** toward the cross-section (Vasicek-lite) so a few noisy betas can't poison the residual.
3. **Sector ETF ⟂ index collinearity** — orthogonalize sector vs market first; then the two slopes decouple into clean univariate betas (§3).
4. **Amplitude alone is noise** → rank on the residual **information ratio** (alpha ÷ residual vol). **"Acceleration / velocity" is dead** — it's anti-predictive here, not a headline.

---

## 2. What we already have

Estimated reuse: **~80%.** A residual-momentum leg is mostly assembly of existing primitives.

- **Universe + sectors:** `data/{breadth,smallcap_breadth,midcap_breadth}/constituents.parquet` (503+603+400, each with GICS `sector`); `equity_factors._names_sectors()` returns ticker→(name, sector).
- **Live price matrix:** `equity_factors._closes()` → ~1,506-name daily matrix, but **only ~3 years** (rolled forward) — the power bottleneck.
- **Deep matrix (fetched for Phase 0):** `scripts/residual_alpha_fetch.py` → `data/breadth/_closes_deep.parquet` — **1,506 names × 1962→2026** (1,433 with >5y, 1,104 with >15y). *Survivorship-biased* (current members only). Loaded via `--closes deep`.
- **Benchmarks:** `data/yahoo/` — SPY (1993→), SPDR sectors (1998→), `_GSPC` (1927→).
- **Validation (reused wholesale):** `engine/validation.py` — `rank_ic`, `ic_summary` (mean IC / IC-IR / Newey-West HAC t / hit), `benjamini_hochberg`, `deflated_sharpe`+`dsr_verdict`, `block_bootstrap_ci`, `purged_folds`, `resid_z`. Harness mirrors `scripts/factor_ic_scorecard.py`.

**The sobering prior held:** the existing value/quality/low-vol composite doesn't survive BH-FDR here (`SP_VECTOR_VIABILITY.md` §3). Neither does residual momentum on the modern era — but momentum *does* full-history, which is the one cross-sectional signal that clears the bar on this universe.

---

## 3. Construction spec (the math)

```
r_{i,t}  =  α_{i,t}  +  β^m_i · m_t  +  β^s_i · s̃_{k(i),t}  +  ε_{i,t}
```

- `m_t` = market return (SPY). `s̃_{k,t}` = sector *k*'s return **orthogonalized to the market** (EW peer-basket return; SPDR ETF as alternative). `k(i)` = stock *i*'s GICS sector.
- Because `s̃ ⟂ m`, the two slopes **decouple into univariate rolling betas** (252d, lagged 1d, shrunk): `β^m = cov(r,m)/var(m)`, `β^s = cov(r,s̃)/var(s̃)`.
- `ε_{i,t}` (+ intercept) = the stock-specific return after market *and* sector are removed — the operator's "alpha"; the BHM residual.

**Candidate signals (cross-sectional, monthly), each raw + sector-neutral:**

| Signal | Definition | Result (§4a) |
|---|---|---|
| `mom_tot` | total return over [t−252, t−21] | real, FDR-surviving full-history; decayed post-2000 |
| `mom_res` | Σ ε over the window | **durable in the modern era; beats `mom_tot` 2002-26** |
| `ir_res` | ε mean/std over the window (info ratio) | best modern IC (sector-neutral) |
| `rev_st` | last-21d return | **strong negative — reversal/timing, not a picker** |
| `acc_res` | recent vs prior residual trend | **negative — KILLED** |

Label: forward 21d (and 63d). Sector-neutral = demean within GICS = the "winners within a sector" view.

---

## 4. Phase 0 validation harness

`scripts/residual_alpha_phase0.py` (clones `factor_ic_scorecard.py`). Per monthly rebalance: build `m`, per-sector `s̃`, per-stock causal residual ε → five candidate signals (+ sector-neutral) → `rank_ic` vs forward return → `ic_summary` → `benjamini_hochberg`; plus a dollar-neutral top-vs-bottom-quintile **net** backtest with `deflated_sharpe` + `block_bootstrap_ci`. Flags: `--closes {live,deep}`, `--shrink W`, `--start YYYY` (era), `--spdr` (110-name cross-check).

**Pre-registered gate:** GO if residual momentum has IC>0, survives BH-FDR, beats `mom_tot`, and its long-short DSR ≥ 0.90. REFINE if directionally right but underpowered. KILL if IC ≤ 0 / no better than total momentum.

---

## 4a. Phase 0 results (2026-06-14 · `reports/residual-alpha-phase0.md`)

Forward 21d. Three reads, betas 252d shrunk (0.66), formation 12−1 (252/21):

| panel | span | rebal | `mom_tot` IC | `mom_res` IC | `ir_res` IC | `rev_st` (SN) IC | residual vs total |
|---|---|--:|--:|--:|--:|--:|---|
| broad live | 2024-06→2026-04 | 23 | 0.0102 | **0.0247** | 0.0246 | **+0.0351** | residual wins; short = *continuation* (regime) |
| **deep full** | 1964→2026 | **747** | **0.0268\*** | 0.0071 | 0.0066 | −0.0456\* | total wins (pre-2000 + survivorship era) |
| **deep modern** | 2002→2026 | 291 | 0.0036 | **0.0065** | **0.0071** | −0.0112\* | **residual wins** (apples-to-apples) |

`*` = survives BH-FDR(10%) in that panel.

**The story is era-dependence.** Plain `mom_tot` was hugely powerful 1964–2000 (full-history LS **+2765%**, t-HAC 3.7, survives FDR, DSR 0.93) but has **decayed**: in the modern era its long-short *lost* money (Sharpe 0.12, **−5.5%**, IC 0.0036). The **residual** version is the durable one — modern long-short Sharpe **0.33 / +319%**, and it out-ranks `mom_tot` on IC in *both* shorter panels. That asymmetry — total momentum decays, residual momentum persists — is exactly the BHM result, reproduced on our data.

**Two legs resolved cleanly:**
- `rev_st` (short frame): **reversal long-run** (full-history sector-neutral IC −0.046, t −9.5; modern −0.011, t −2.4), the single most significant effect; only the recent 2024–26 mega-cap regime flipped it positive. A regime-conditioned timing/entry overlay, not a picker.
- `acc_res` (acceleration / "just-started velocity"): **anti-predictive** (full-history −0.012, t −2.7). KILLED.

**The honest ceiling.** On the *modern* era nothing clears BH-FDR(10%) or DSR ≥ 0.90 (best: residual LS DSR 0.75, P(SR>0) 0.96; `rev_st|SN` IC q 0.17). These are real-but-modest, crowded edges. The FDR/DSR-surviving full-history `mom_tot` numbers are inflated by (a) the pre-2000 golden age and (b) **survivorship** (current members back to inception biases momentum *up*).

**Determination: GO as a ranking/context leg, not a standalone strategy.** The operator's thesis is confirmed — relative momentum picks winners, the beta-stripped sector-neutral residual is the durable construction, short frames are reversal-timing, acceleration is dead. But the magnitude is modest in the current regime, so it belongs as a **factor leg / sector tilt / per-stock context read**, framed honestly, alongside the existing factors — not a high-conviction market-neutral book.

---

## 5. Traps & kill-criteria (pre-registered, all now checked)

- **Short-window betas** — handled: 252d rolling, shrunk, lagged.
- **Sector⟂index collinearity** — handled: orthogonalize then decouple.
- **Multiple testing** — BH-FDR across the candidate panel + DSR on the long-short; *nothing* survives on the modern era — reported, not hidden.
- **Era / decay** — the `--start` re-run exposed that full-history `mom_tot` dominance is a pre-2000 artifact; the modern comparison is the honest one.
- **Survivorship** — the deep panel is current-members-only; biases momentum up, so the modern-era *failure to clear the bar* is conservative, the full-history *pass* is optimistic. Point-in-time membership is the remaining unbought data.
- **Acceleration** — pre-registered and KILLED (negative IC).

---

## 6. Productionization (if shipped as a leg)

- **Engine:** `engine/residual_alpha.py` — shrunk orthogonalized betas; per-stock daily residual; **sector-neutral residual momentum (12−1)** as the score; **short-term (1mo) reversal** as a regime-conditioned entry overlay; drop acceleration.
- **UI (existing patterns):** (1) *within-sector alpha leaders* on `site/sectors/*.html` (constituent-card macro in `templates/sector.html.j2`); (2) *alpha vs sector/index* panel on the stock page (`build_stock_library.py` → `stockdata/*.json` → `site/stock.html`); (3) optional cross-sector leaderboard (clone `factors.html`). Label honestly: "a modest, regime-decayed edge — context, not a buy list."
- **Path to a stronger claim:** point-in-time index membership (kill survivorship) → re-run the modern panel; blend residual momentum with the *orthogonal* value/quality composite (a combination may clear FDR where neither leg does).

---

## 7. Literature

- Blitz, Huij, Martens (2011), *Residual Momentum* — residual ≈ 2× risk-adjusted return & milder crashes vs total momentum. **Reproduced here as modern-era durability.**
- Moskowitz & Grinblatt (1999), *Do Industries Explain Momentum?* — industry carries much of single-stock momentum (→ sector-neutral).
- Jegadeesh (1990) / Lehmann (1990) — short-horizon reversal. **Reproduced (full-history `rev_st` < 0).**
- 52-week-high / turnover work — short-term reversal → continuation conditional on high turnover (the 2024–26 exception).
- Acceleration / "momentum of momentum" — **not supported here (negative IC); killed.**
