# S&P / Macro Vector — Viability Assessment

*research/SP_VECTOR_VIABILITY.md · 2026-06-13 · branch `quant-factor-expansion`*

**Verdict: BUILD — but reframe the goal.** Ship a drawdown-reduction / Sharpe engine with positive bill carry, validated drawdown-first against a dumb baseline, run in a tax-advantaged account. Do **not** promise to "steadily beat the index CAGR with confidence" — that is not defensible from this data.

---

## 1. Objective & honest reframe

**As stated (operator):** a tactical allocation that switches a broad US index ↔ treasuries/cash at the prevailing bill yield, modeled on the Bitcoin Vector, to **beat the index's annual return over a long history, with confidence, by avoiding deep drawdowns**.

**Why the as-stated goal is not defensible** (all measured, several reproduced here on the repo's own SPY 1993-2026 + DTB3):

- Single index-vs-cash timing **structurally forgoes the equity risk premium** while flat. A Monte-Carlo of 2000 random long/flat switches (2bps, bill carry credited) beats SPY Sharpe ~20% of the time but CAGR only ~1.6%.
- The **only** bootstrap-robust effect across the entire repo is **drawdown reduction**. For the best signal (dislocation Fed-put switch), the drawdown-diff CI excludes zero (median +3.9pp, 95% CI [+0.3, +6.3]) while the **return** diff (+7.4 [−2.7, +12.3]) and hit-rate diff (+30.3 [−5.1, +63.0]) **span zero** (`research/DISLOCATION_VALIDATION.md`).
- **Effective-N is single digits.** Verified count of independent peak-to-recovery ≥20% SPY bears, 1993-2026 = **4** (−47.5% 2000-02, −55.2% 2007-09, −33.7% 2020, −24.5% 2022). ~7 at ≥15% or on DJI/RUT. "With confidence" on CAGR is mathematically unsupportable on n≈4.
- The DSR deflates **Sharpe, not CAGR** — the metric the operator cares about is unprotected by the existing overfitting guard.

**Achievable & defensible objective:** *equal-or-slightly-lower CAGR delivered at +0.10–0.20 higher Sharpe/Sortino and roughly half the max drawdown, plus a real bill-carry tailwind in high-rate regimes and large dry powder to redeploy at bottoms.* Reproduced baseline (cash-credited 200dma long/flat, 3bps):

| Strategy | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| SPY buy & hold | **10.81%** | 0.65 | −55.2% |
| 200dma long/flat + bill carry | 8.62% | **0.75** | **−25.2%** |
| 200dma, no cash credit | 8.21% | 0.72 | −28.9% |

Carry contributes only **+0.41pp/yr** on average (≈0 in ZIRP, ~0.3pp now). Frame the product as a **better risk-adjusted ride + crash insurance with positive carry**, defaulting **LONG**, judged on forward drawdown — explicitly warning that it **will lag SPY CAGR in prolonged bulls** (that give-up is the premium paid for the protection, banked when the cycle breaks). Over a full cycle it can match-to-modestly-beat; year-by-year it cannot promise to beat.

---

## 2. What we already have

The repo holds everything an index-vs-cash switch needs end-to-end (verified on disk):

- **Equity legs** (`data/yahoo/`): SPY 8400 rows 1993→2026, `_DJI` 1992→, `_RUT` 1987→ (longest), QQQ 1999→.
- **Cash leg** (`data/fred/`): `DTB3` 18,102 rows 1954→ (`us3m`, annualized %, last 3.63), `DGS3MO` 1981→, `DFF` 1954→. Far out-spans equity history — never binds.
- **Vol**: `_VIX` 1990→, `_VIX3M`, `_VVIX`, MOVE (collected, unused).
- **Credit**: HY-OAS `BAMLH0A0HYM2` 1996→ (usable). IG-OAS effectively unavailable (823 rows from 2023).
- **Net-liquidity**: WALCL 2002→, RRP 2003→, TGA 2005→ — the binding short-history macro constraint (~3-4 cycles, 2-3 real contractions).
- **Conditions/regime**: NFCI 1971→, curve T10Y2Y/T10Y3M, term-premium-adjusted curve, deep `engine/conditions.py` suite, and a 14,465-row daily `regime_history.parquet` 1971→2026.
- **Validation + calibration stack** (directly clonable): `engine/validation.py` (`backtest_core`, `deflated_sharpe`, `purged_folds`, `block_bootstrap_ci`, IC/Newey-West/BH-FDR) + `scripts/calibrate_vector.py` (`backtest`, `forward_drawdown`, `drawdown_table`, `band_table`, `whipsaw`, `fold_robust`, `oof_cell_probs`) + `scripts/build_vector.py` (dashboard view-model).

Estimated reuse: **~75-85%**.

---

## 3. Signal shortlist with measured records

Against the house rule (judge on forward **drawdown**; demand split-half robustness; respect effective-N), only a small set carries real index-timing edge.

**CONFIRMED / usable:**

| Signal | Location | Measured record | Role |
|---|---|---|---|
| Macro-stress drawdown gauge (recession-risk + NFCI + EBP + HY-OAS) | `conditions.py:185` | Monotone P(≥10% DD/63d): ~8→26→36→38% by band | **Primary de-risk trigger** |
| Recession composite incl. **term-premium-adjusted curve** | `conditions.py:87` | High band −0.88%/mo, −14.8% worst 3-mo DD; often earlier than price quad | De-risk; TP-curve fixes the 2022-24 false inversion |
| Net-liquidity overlay (WALCL−RRP−TGA RoC, lag_bd=3) | `regime.py:100` | +6/+8pp hit, −2.3pp DD on buy setups; **orthogonal to and subsumes trend**; survives split-half/bootstrap/jackknife | Risk-ON bias (odds edge, not magnitude) |
| Dislocation Gate-1 Fed-put switch | `dislocation.py` | **Only effect whose bootstrap DD-CI excludes zero**; LOYO sign 26/28 yrs | "Stand aside in a knife / redeploy in a buyable washout" governor |
| Capitulation gauge (VRP-pctile + VIX>30 + COT washout) | `conditions.py:198` | ≥2 signals → +9.3%/63d, 86% hit — **only when Fed-put present** | Re-deploy leg (conditioned by Gate-1) |
| NFCI tight-and-tightening / quad×NFCI-direction | `conditions.py:76` | 13-20pp hit split, both halves | Second confirmer |
| HY-OAS **widening/RoC** | `BAMLH0A0HYM2` | Leg of the (monotone) drawdown gauge | De-risk confirmer (use RoC, not level) |

**NEGATIVE / context-only (do not put in the scoring path):**

- **Trend / Kaufman Efficiency-Ratio gate** — NEGATIVE on equities; ER quartiles ~58% hit flat; **does not survive controlling for net-liquidity**. Use 200dma only as a *coincident confirm*.
- **RORO, equity VRP, VIX term structure, SKEW, stock-bond corr regime** — no equity-direction edge (QUANT_FACTOR_EXPANSION §6 kill list). Stock-bond corr matters only for the *cash/Treasury* leg (when bonds stop hedging, a duration defensive sleeve loses its hedge — 2022).
- **Cross-sectional equity factors** (value/quality/low-vol/BAB) — none survive BH-FDR; stock-selection, not index timing.
- **MOVE** — collected, wired into no equity signal, no measured record.
- **macro_score** as a tactical equity gate — A/B-rejected (cut CAGR, flat Sharpe/MaxDD, redundant with momentum); kept strategic-standalone only.

**Redundancy map:** the drawdown gauge already blends recession-risk + NFCI + EBP + HY-OAS, so those legs triple-count — pre-register them once. Liquidity and trend are **not** additive (liquidity wins).

---

## 4. The clone spec + cash-leg

**Cash-leg accounting bug (the one hard prerequisite).** `engine/validation.py` `backtest_core()` lines 50-52 compute `gross = pos*ret; net = gross − cost; hold = ret` — **the (1−pos) flat sleeve earns ZERO.** The *same* bug exists in `scripts/build_vector.py` `alloc_equity()` lines 64-67 (`(1 + pos*ret).cumprod()`). For an equity-vs-bills strategy with 25-50% of capital in bills, that understates CAGR by multiple points **and** makes the comparison vs all-equity B&H unfair. Both must be patched in lockstep, or the displayed equity curve diverges from the scorecard.

Fix (default `None` keeps BTC/commodity/forex callers identical):

```python
def backtest_core(close, alloc, cost_bps=0.0, cash_yield=None):
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)   # act next bar
    turnover = pos.diff().abs().fillna(0.0)
    cost = (cost_bps/1e4)*turnover
    if cash_yield is not None:
        rf = (cash_yield/100.0/365.0).reindex(ret.index).ffill().fillna(0.0)  # ann% -> per-cal-day
        cash_leg = (1.0 - pos).clip(lower=0) * rf   # clip: a >100% pos pays no phantom bill rebate
    else:
        cash_leg = 0.0
    gross = pos*ret + cash_leg
    net   = gross - cost
    hold  = ret                       # buy&hold benchmark stays all-equity, no cash
    ...
```

Use `/365` (calendar days — ffill accrues bill interest across weekends/holidays). The equity calibrator passes `cash_yield=DTB3.us3m`; BTC/commodity/forex pass nothing. Report the headline Sharpe on total return (current behavior, now includes carry) **and** on excess return (`net − rf`) for an honest risk-free-relative read. DSR/bootstrap inherit the carry via `net`.

**Other clone changes:** `TRADING_YEAR=252`; `block_bootstrap_ci(ann=252)`; `cost_bps` 1-3 one-way for liquid index ETFs; pass `cash_yield` to **both** `backtest()` and the bootstrap `backtest_core` call; keep `alloc ∈ [0,1]` (long/flat, no leverage/short); clone `build_vector.py → build_spvector.py` and mirror the cash leg in the displayed curve; add a hub card.

---

## 5. Honest-N & validation plan

**Effective-N is the binding constraint, not row count.** 8400 SPY days / 14,465 regime rows are massively autocorrelated. What governs overfitting is the count of **independent bear episodes**: **4** (live SPY ≥20%, verified), ~7 (≥15% or DJI/RUT), ~12-14 ceiling **only** if `^GSPC` is spliced to 1927. The dislocation put-absent sample is n≈5 (63d). The `regime_history` recession flag is 50 fragmented runs (only 3 ≥30 days) — unusable as a clean episode label.

**Validation loop (mandatory, drawdown-first):**

1. **Phase-0 baseline** frozen first: B&H, naive 200dma, contracting-net-liquidity gate — all cash-credited.
2. `backtest_core` next-bar (no look-ahead), turnover cost, cash carry.
3. `purged_folds` (embargoed CV) + an explicit 2012-2025 second-half OOS.
4. `deflated_sharpe` with an **honest** `n_trials` = families × variants × thresholds (~200), **not** the **50 declared** in `data/vector/trial_log.json` (which itself screened 31 families × 4 variants).
5. `block_bootstrap_ci` (block≈21, B=5000, ann=252) on CAGR/Sharpe/MaxDD.
6. **Leave-one-crisis-out** jackknife + **QE-era (2020-21) exclusion**.
7. **AQR-null** permutation baseline.
8. Judge **forward DRAWDOWN by band** first (`forward_drawdown`, `band_table`); report CAGR **with and without** the cash credit; report **after-tax** (35% ST) sensitivity.

Pass bar per leg: cuts MaxDD vs B&H **and** beats the 200dma+liquidity baseline on Sharpe OOS **and** drawdown-reduction CI excludes zero **and** survives leave-one-crisis-out. Fail any → demote to "context, not signal."

---

## 6. TAA literature reality

Independent evidence converges on the same conclusion: **single index-vs-cash timing does not reliably beat buy-and-hold CAGR; it improves Sharpe and cuts drawdown.**

- **Faber 10-month SMA (S&P only, since 1901):** 9.32% timed vs 10.18% B&H compounded — **lagged** CAGR, ~30-40% lower vol/DD, higher Sharpe. The cleanest proof.
- **Faber GTAA (5-asset)** 10.5% vs 9.9% and **GEM dual momentum** 15.8% vs 11.4% — the CAGR wins come from **diversification across uncorrelated sleeves / a futures structure**, not from timing one index. GEM captured only ~42% of the 2009-2017 bull.
- **200dma SPY 2010-2020:** 8.5% vs 12.8% B&H — a ~4.3pp/yr whipsaw drag in a trend-light bull.
- **AQR Century of Trend / Moreira-Muir vol-managed:** robust Sharpe + crisis convexity, **not** large CAGR gains (and the market-timing piece is OOS-fragile per Cederburg et al.).
- **Growth-Trend Timing (Philosophical Economics):** the single most transferable design — only allow a price-trend exit when a **recession filter also agrees**; captures most bears while in cash <15% of the time, killing whipsaws.
- **"Miss the 10 best days"** is roughly **symmetric** (out 12 best −5.1%/yr vs out 12 worst +5.8%/yr) and best/worst days cluster together in bear regimes — not a reason to avoid timing, and the regime a risk-OFF gate is built to detect.

**Operator concerns, adjudicated:** (a) *policy-supported prolonged bull* → valid; the cure is recession-gating, not abandoning timing — expect to match/modestly-lag CAGR and bank the payoff later as shallower drawdown. (b) *sector rotation masks the index* → also valid and in your favor: dispersion cancels at the index level, so do **not** time on fast price-trend (rotation whipsaws you); time on the slow macro-confirmed signal that fires on broad correlated risk-OFF events.

---

## 7. Data gaps & LLM verdict

**Data to add (ranked):**
1. **`^GSPC` daily to 1927** (existing fetch infra) — triples the independent-bear count ~4→~12-14; the single biggest confidence lever. Net-liquidity gate stays capped at ~2005+.
2. **ALFRED/PIT vintages** for revised gates (NFCI, recession-prob, Sahm, GDPNow) — removes the look-ahead that flatters the recession-gated CAGR-beating variant (only a partial `data/fred_vintage` exists).
3. **Forward earnings-yield / ERP history** from Shiller `ie_data.xls` (rates legs already on disk) — slow strategic redeploy tilt only, never a trigger.
4. **Shiller CAPE monthly** — LOW priority, starting-valuation context band, not in the scoring path.
5. **Index revision-breadth** — SKIP (no clean free source; momentum cousin that fails the liquidity control).

**LLM decision — keep it OUT of the scoring/backtest path (`needed_in_scoring_path = false`):** non-reproducible/version-drift breaks the house rule; structural training-leakage makes any pre-cutoff backtest contaminated and un-deflatable by DSR/purged-CV; effective-N≈4 cannot absorb an opaque high-variance input. Its legitimate role is **around** the mechanical core, **after** the deterministic engine is built and DSR-validated standalone: a two-tier DeepSeek→Claude **context/veto overlay** feeding dislocation Gate-1 and `conditions.py` annotations (FOMC/CPI/earnings-season tone, "is this shock reversible / knife vs dip"). It may downgrade conviction, veto a redeploy, or write the human brief — but its output is **logged as context, never a number inside the allocation function.** Keep it firewalled, event-triggered, and track its veto hit-rate forward before it ever touches sizing.

---

## 8. Adversarial findings

Two independent skeptics put ~7-12% confidence on the as-stated goal and ~75-80% on the reframe. Reproduced/strongest:

- **Tax drag (fatal in a taxable account):** a 200dma switch with ~3.2 round-trips/yr realizes ~all gains short-term; at 35% ST the after-tax CAGR falls to ~5.2% vs B&H ~10.8% (cumulative tax ~3.5× initial capital). Viable only in a tax-advantaged account or a low-turnover recession-gated design.
- **Gross CAGR already lags** (reproduced: 8.62% vs 10.81%). The one config that edged B&H (recession-gated GTT, ~94% invested, ~11 trades/33yr) leaned on **revised** recession-prob (look-ahead) and shrinks point-in-time.
- **Whipsaw/lag:** 77.7% of naive switches reverse <21 days; 2010-2020 lagged ~5pp/yr with DD no better than B&H; the 2020 V was sold low and bought back higher.
- **Multiple testing:** ~200 plausible configs ⇒ a chance CAGR-beater is near-certain; DSR (Sharpe-only) does **not** protect the CAGR claim; honest-trial DSR on the BTC headline already falls 0.995→0.917 at n=2000.
- **Manageable:** the cash-leg bug must be fixed before any number is trusted; once fixed, carry is rate-regime-dependent (~0% ZIRP, ~5% now) — report with/without.

These are **not** reasons not to build — they are the spec for what to build (slow, recession-gated, tax-advantaged, drawdown-judged) and what **not** to claim (a confident CAGR beat).

---

## 9. Phased build plan with gates

- **Phase 0 — Harness + dumb baseline (HARD GATE):** patch `backtest_core(cash_yield=)` + `alloc_equity()`; wire DTB3; clone `calibrate_vector → calibrate_spvector` (252yr, 1-3bps). Freeze the baseline board (B&H / 200dma / net-liquidity, all cash-credited) on CAGR (±carry)/Sharpe/Sortino/MaxDD/turnover/time-in-mkt/after-tax. *Gate: reproduce the baseline numbers; cash leg non-zero in BOTH backtest and displayed curve; no candidate proceeds unless it beats 200dma+net-liquidity net-of-cost OOS.*
- **Phase 1 — Pre-registered de-risk core:** blend drawdown gauge + recession/TP-curve + HY-OAS widening + contracting net-liq + vol-target into a 0-100 score; graded hysteretic glide path (100/66/33/0) with min-holding. *Gate: OOS cut MaxDD vs B&H, raise Sharpe vs baseline, drawdown-CI excludes zero, survive leave-one-crisis-out, whipsaw <~15%.*
- **Phase 2 — Re-deploy leg:** Fed-put-conditioned capitulation + breadth-thrust re-entry. *Gate: improves recovery capture without raising MaxDD/whipsaw; capitulation contribution conditional on put-present; DSR >0.90 at honest n_trials.*
- **Phase 3 — Confidence audit + framing + dashboard:** full DSR/bootstrap/jackknife/QE-exclusion/AQR-null; clone `build_vector → build_spvector` with cash-credited curve, hub card, and UI panels showing the post-2009 lag + symmetric best/worst-days + prominent tax/tax-advantaged framing. *Gate: headline survives DSR >~0.90 at honest trials and all adversarial cuts; report framed strictly as drawdown/Sharpe + carry. If DSR collapses, ship only the net-liquidity + recession-gated variant (build-narrow fallback).*
- **Phase 4 (optional) — CAGR upgrade via diversification:** only if wanted — long-Treasury defensive sleeve (watch the 2022 stock-bond corr breakdown) and/or relative-strength across SPX/Nasdaq/Dow/Russell. *Gate: its own fresh OOS proof; default to NOT building.*

---

## 10. Bottom line

The data and code are **ready**; the engineering is low-risk (~75-85% reuse). The binding constraint is honest-N (4 independent SPY bears), and every confirmed signal in this repo is a **drawdown** gauge, not a return forecast. **Build the S&P Vector — as a drawdown-reduction / Sharpe engine with positive bill carry, defaulting LONG, recession-gated, run in a tax-advantaged account, and validated drawdown-first against a 200dma+net-liquidity baseline with an honest Deflated-Sharpe trial count.** Expect Sharpe +0.10-0.20 and roughly half the max drawdown with high confidence; expect CAGR equal-or-slightly-lower with low confidence on any beat. Fix the cash-leg bug first, splice `^GSPC` to 1927 to triple the episode count before trusting any headline, and keep the LLM as a firewalled context/veto co-pilot — never a number in the allocation function.
