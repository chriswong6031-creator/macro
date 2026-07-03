# China A-share & Hong Kong — per-stock signal scores & stock/ETF suggestions

*research/CHINA_HK_STOCK_SIGNALS.md · 2026-06-14 · branch `quant-factor-expansion`*

**Goal.** Bring the US dashboard's stock-picking surface — per-stock *signal scores*, ranked
*stock/ETF suggestions*, an alpha leaderboard — to the China A-share and Hong Kong dashboards.
Today both markets have rich per-stock **context** (cycle ladder, MTF momentum, technicals,
seasonality on china_stock.html / hk_stock.html) and sector/ETF rotation, but **no
cross-sectional score that ranks one name against another**, and therefore **no actionable
"here are the names" output**. The missing piece is exactly what the US ships: a
sector-neutral residual-momentum leg layered on the cycle ladder, surfaced as a conviction
score + leaders panel.

## What we already have (verified 2026-06-14)

| Component | 🇨🇳 A-shares | 🇭🇰 Hong Kong |
|---|---|---|
| Regime/macro layer | Q1–Q4 quad + liquidity + cycle tag (calibrated) | Q1–Q4 + **global-risk overlay (primary)** + dual liquidity + HKD peg + AH premium |
| Sector/ETF ranking | 16 ETFs RS-ranked + action board | 12 synthetic baskets RS-ranked |
| Per-stock cycle ladder | ✅ 803 names (`chinastockdata/*.json`) | ✅ ~73 names (`hkstockdata/*.json`) |
| **Per-stock price panel** | ✅ `data/china_search/closes.parquet` — **1211d × 800** (2021-06→2026-06) | ⚠️ `data/hk_breadth/_closes_cache.parquet` — 760d × **73** (thin) |
| Sector labels | ✅ `members.parquet` (12 yfinance buckets) | ✅ `constituents.parquet` (12 buckets) |
| Market proxy | `data/china/510300.SS` (CSI300 ETF) | `^HSI` |
| **Per-stock residual-alpha z** | ❌ → **Phase 1** | ❌ → **Phase 3** |
| **Cross-stock conviction score + ranked picks** | ❌ → **Phase 2** | ❌ → **Phase 3** |
| Fundamental factors (value/quality) | ❌ no free XBRL (Tushare possible, deferred) | ❌ hardest (deferred) |

**Engine reuse.** `engine/residual_alpha.py::compute_residual_alpha(closes, market, tkr_sector)`
already accepts the panel/market/sector-map as **direct arguments** (US `_closes()`/`_names_sectors()`
are just the defaults). So the China leg is *wiring*, not new math. `cycles.py`, `technicals.py`,
`ticker_alerts.py` are 100% price-only and already run on both markets. `holdings_signals.py`
(ETF accumulation) does NOT port — no China/HK sector-SPDR-with-published-holdings analog.

## Phase 0 — validate residual momentum on A-shares (5y GO → ⚠️ DEEP-HISTORY CORRECTION below)

> **⚠️ CORRECTION (2026-06-14, `scripts/china_residual_alpha_deep.py`, `reports/china-residual-alpha-deep.md`).**
> The deep-history fetch flagged below as the "power upgrade" was run — and it **overturns the 5-year
> GO.** On a ~35-year / 400-rebalance panel, cross-sectional momentum (total AND residual) is **NOT a
> validated A-share edge**: IC negative/zero at the shipped 12-1/fwd-21 config over the full (−0.009)
> and modern-2010 (−0.001) eras, long-short Sharpe negative, **nothing clears BH-FDR**; only weakly
> positive-but-insignificant at 6-1/fwd-63d. The robust, FDR-surviving effect is the **opposite —
> short-term REVERSAL** (`rev_st|SN` t −2.7 to −5.0, survives FDR across full/modern/connect eras and
> both market proxies). The 5-year result below was a **favourable-window artifact** (2021-26 happened
> to reward momentum). **A-shares are a retail-driven, mean-reverting cross-section** — recent winners
> give back, recent losers bounce. ⇒ the shipped momentum-leaders ranking **overclaims**; the validated
> read is reversal / the cycle-confirmed pullback (mean-reversion) entry. UI copy + `_setup_score`
> weights corrected accordingly (see build plan). The original 5-year analysis is kept below for the record.

Harness `scripts/china_residual_alpha_phase0.py` mirrors the validated US harness
(`scripts/residual_alpha_phase0.py`) exactly — same `score_panel` / `quintile_ls` /
`engine/validation.py` stack (rank-IC, IC-IR, Newey-West HAC t, BH-FDR, Deflated Sharpe,
block-bootstrap CI). Universe: `data/china_search/` top-800; market: CSI300 ETF (and an
EW-mean robustness run); EW-peer sector baskets; betas 252/126d, lagged 1d, Vasicek-shrunk
0.66. Report: `reports/china-residual-alpha-phase0.md`.

**Pre-registered gate:** GO if residual momentum IC>0, beats plain total momentum, durable;
REFINE if underpowered/mixed; KILL if residual IC ≤ 0.

**Results (forward 21d unless noted; 3 configs × 2 market defs):**

| read | `mom_tot` IC | residual (`ir_res`) IC | residual LS Sharpe | `mom_tot` LS Sharpe | `rev_st|SN` | `acc_res` |
|---|--:|--:|--:|--:|--:|--:|
| 12-1, CSI300 mkt | 0.025 | 0.021 | **0.89** (P>0 .90) | 0.59 | −0.003 | −0.010 |
| 12-1, EW mkt | 0.025 | **0.027** | **0.76** | 0.59 | −0.003 | −0.006 |
| 6-1, CSI300 mkt | 0.018 | 0.008 | 0.50 | 0.16 | **−0.024** (t −1.1) | −0.026 (t −1.8) |
| 12-1 **fwd 63d** | 0.053 | **0.055** (74% hit) | 0.53 | 0.23 | −0.010 | −0.027 |

**Verdict — GO as a ranking/context leg (NOT a standalone strategy).** Mirrors the US leg:

1. **Momentum is real and positive on A-shares** — every momentum signal IC>0 across all
   3 horizons and both market definitions (this was not guaranteed on a retail-driven tape).
2. **The beta-stripped residual is the more *tradable* construction** — the residual
   info-ratio (`ir_res`) out-Sharpes plain total momentum in the long-short at **every**
   horizon under **both** market definitions (0.89 vs 0.59 at the ships config), and beats
   total on IC at 63d and at 21d under the EW market. The **63d horizon is strongest**
   (IC 0.055, 74% monthly hit, q_FDR ≈ 0.39 — nearest to surviving).
3. **Short frame = reversal** (`rev_st|SN` negative, strongest at 6-1) — confirms the
   retail prior; keep as the regime-conditioned **entry-timing overlay** (already in
   `residual_alpha._entry`), not the score.
4. **Acceleration is anti-predictive — KILLED** (negative IC, t to −2.05), exactly as US.
5. **Honest ceiling:** nothing clears strict BH-FDR(10%)/DSR≥0.90 — only ~5y of history
   (low power) and a survivorship-biased top-mcap-today universe (inflates momentum, so a
   weak read is conservative; the dollar-neutral LS partly controls it since both legs are
   drawn from the same survivor set). Ship as **context / ranking / sector-tilt / per-stock
   read**, framed honestly — not a high-conviction market-neutral book.

**Score choice:** sector-neutral z of the residual **info-ratio** (`ir_res`) over a 12-1
window — i.e. the exact thing `engine/residual_alpha.py` already computes. Reversal as the
entry overlay; acceleration dropped. Phase-0 supports the *current* engine config directly.

**Power upgrade (DONE — and it flipped the verdict, see the ⚠️ correction at the top of this
section):** the one-time deep-history fetch (`scripts/china_residual_alpha_deep.py --fetch` → 800
names × ~35y) lifted the rebalance count from 33 to ~400 and revealed the 5-year momentum read was a
favourable-window artifact. Remaining unbought data: point-in-time CSI membership (kills survivorship —
which would only *weaken* momentum further, since survivorship biases it up). The honest A-share edge is
**mean-reversion**, so the next real build is a reversal/pullback-led signal, not a momentum one.

## Reversal-native signal — Phase 0 (validated; REFUTES the intuitive "confirmed pullback" design)

`scripts/china_reversal_phase0.py` → `reports/china-reversal-phase0.md`. Long-only top-quintile of
within-sector reversal fuel, forward 21d, EXCESS over the EW-universe (cross-sectional skill net of
the A-share drift), on the deep panel (~790 names, 388 monthly rebalances, 1990→2026).

| construction | excess /mo | Sharpe | maxDD | hit |
|---|--:|--:|--:|--:|
| **rev 3mo · deepest quintile (NO gate)** | **+0.56%** | **0.58** | −37.6% | 56% |
| rev 1mo · deepest quintile | +0.37% | 0.38 | −49.3% | 54% |
| rev 1mo · moderate band (avoid worst) | +0.10% | 0.16 | −31.7% | 53% |
| rev + turn-confirmation (ret_5d>0) | **−0.29%** | −0.29 | −78.9% | 48% |
| rev + turn + quality floor | −0.21% | −0.19 | −78.0% | 48% |
| rev 3mo + market-healthy gate | +0.36% | 0.34 | −39.5% | 54% |
| mom 12-1 (killed momentum, ref) | +0.03% | 0.03 | −57.3% | 47% |

**Verdict: the validated A-share signal is 3-month within-sector reversal, deepest quintile, NO gates**
(Sharpe 0.58, +0.56%/mo, 56% hit). It beats 1-month reversal, the killed momentum, and — decisively —
**every refinement the intuition suggested:**
- **Turn-confirmation HURTS** (excess flips negative): waiting for the bounce = buying AFTER the
  mean-reversion. The edge is in the UNCONFIRMED dip.
- **Quality floors HURT**: the deepest decliners carry the most reversal fuel.
- **Moderate-band / market-regime timing** don't improve risk-adjusted return.

So the operator's proposed construction — *cycle-confirmed pullbacks of quality names* — is **refuted**;
confirmation and quality both forfeit the edge. **Caveats:** excess is cross-sectional skill, NOT
net-of-cost (reversal is high-turnover); −37.6% drawdown is deep (contrarian, bleeds in sustained
declines); quality-filtering hurts, so the raw signal surfaces the deepest decliners *including
potentially-broken names* → a responsible product needs a light liquidity / non-ST(delisting-risk)
screen and honest "high-variance contrarian, size small" framing, **not** a confident buy list. **Build
is a product decision (the signal inverts the request + carries real risk) — flagged for the operator.**

## Build plan & status

- **Phase 1 (China alpha leg) — SHIPPED + verified.** `compute_china_alpha()` in
  `scripts/build_china_library.py` runs the engine on the China panel (CSI300 market) →
  `site/factordata/china_alpha.json` (775 names, 11 sectors); per-stock `alpha` embedded in
  `chinastockdata/*.json`; alpha-z added to `index.json` for client ranking; an **"Alpha
  leaders"** table on china.html (top 16, bilingual, entry tags) and an **"Alpha vs sector"**
  panel on china_stock.html. Sanity holds: CATL's +68% total momentum strips to +11% residual;
  Moutai is a laggard; entry overlay tags pullback/extended correctly.
- **Phase 2 (China suggestions) — SHIPPED + verified.** `_setup_score()` re-ranks the alpha
  leaders by cycle timing (alpha dominates ±3, cycle/overlay tilt ±1) → a **"Top setups"** board
  on china.html (12 buys + 6 laggards) + `site/factordata/china_setups.json`. Confluence works:
  603156 (alpha +1.92 but FRESH BUY + pullback) ranks #1 at setup +3.42, above the raw #1 alpha
  leader 603268 (+2.56 but COUNTERTREND BOUNCE → +2.86). Honest label throughout: selection ×
  timing, a shortlist to size/confirm, NOT a buy list. 348 tests green.
- **Phase 3 (Hong Kong) — deep-history validated → KILL the residual-alpha leg; do NOT ship.**
  First read on the 3y cache (73 names, ~23 rebalances) was inconclusive, so the binding
  constraint (history length) was removed: `scripts/hk_residual_alpha_phase0.py --fetch` pulls
  full yfinance history for the curated constituents + ^HSI → a **~40-year, 447-rebalance** deep
  panel (`data/hk_search/closes_deep.parquet`, 1986→2026; 73 names at the original run, **157**
  since the 2026-06-18 expansion), then re-runs the identical harness.
  `reports/hk-residual-alpha-phase0.md`. **Definitive result — the residual DIES on HK:**

  | signal | DEEP full (447 reb) | DEEP modern 2010+ (171 reb) |
  |---|--:|--:|
  | `mom_tot` (plain/beta) | IC +0.028, t **2.2** ✓FDR, LS Sharpe 0.20 | IC +0.028, LS 0.20 |
  | `mom_res` (residual) | IC +0.012, t 1.28, **LS +0.17, DSR 0.28** | IC +0.012, **LS +0.31, DSR 0.33** |
  | `ir_res` | IC +0.014, LS −0.05 | IC +0.012, LS 0.21 |
  | `acc_res\|SN` | IC −0.023, t −3.0 ✓FDR (KILLED) | −0.020, t −2.3 |

  *(Table refreshed 2026-07-03 from the live 157-name panel: the original 73-name run gave mom_res
  LS Sharpe −0.22 full / −0.35 modern — the panel expansion sign-flipped a near-zero Sharpe, but
  the KILL rests on DSR/IC grounds (fails DSR in every window, IC≈0), not sign.)*

  HK's ONLY positive cross-sectional signal is plain TOTAL-return momentum — but it's weak (fails
  DSR) and it is **beta, not alpha**. The **residual (beta-stripped) construction — the durable
  winner-picker for US + China A-shares — has no tradable edge in HK**: IC ≈ 0, the long-short
  fails the DSR haircut in every window, and its near-zero Sharpe flips sign with panel
  composition. Stripping market+sector beta REMOVES HK's signal: the cross-section is
  beta-dominated, the hard-data confirmation that **HK is a macro/global-risk product, not a
  stock-selection one** (~2× global-beta, `china-global-factors`; matches the HK model's own "no
  stable single-sector outperformance" disclaimer). Shipping the China leg here would deploy a
  signal with no demonstrated edge.
  **Recommended HK path instead:** a per-stock **global-risk-beta** context read (which names are
  most levered to the validated risk-on/off overlay), NOT residual momentum. Name-count expansion
  doesn't change this — tested: the 73→157 expansion left the residual dead across 447 rebalances;
  HK lacks idiosyncratic stock momentum, full stop.
- **Phase 3b (Hong Kong global-risk-beta) — SHIPPED + verified.** The honest HK per-name read,
  pivoting from selection to RISK EXPOSURE. `engine/hk_global_beta.py`: each constituent's causal
  252d beta to global risk (S&P 500, lagged one day for the overnight US→HK transmission),
  Vasicek-shrunk, ranked into **amplifiers** (high beta — global cyclicals: Baidu, copper miners,
  CXO) vs **cushions** (low beta — domestic SOE energy/staples/telecom: CNOOC, PetroChina, China
  Mobile), conditioned on the live `risk_state` into a tilt (favored / exposed / lag). Validated
  (deep 40y panel, lagged-SPY, monthly): high-minus-low global-beta forward-21d is **+0.41% in
  Risk-on, −0.74% in Risk-off** (the risk-off signal cleaner, t −1.3) — directionally correct,
  modest → framed as risk CONTEXT for sizing within the validated regime, NOT a forecast or buy
  list (beta is a descriptive exposure, not an alpha). Wired into `build_hk_library`
  (`compute_hk_global_betas()` → `site/factordata/hk_global_beta.json`; per-stock `global_beta`
  embedded in `hkstockdata`) and `build_hk` (reordered so the board renders server-side). UI:
  **"Global-risk exposure — amplifiers vs cushions"** panel on hk.html (after the global-risk
  overlay hero) + **"Global-risk beta"** panel on hk_stock.html. `engine/hk_global_beta.py` +
  `tests/test_hk_global_beta.py` (4 tests); 359 tests green; browser-verified.
- **Phase 4 (optional).** China fundamentals via Tushare/akshare (value/quality leg);
  per-stock northbound Stock-Connect holdings (a China-specific "smart money" signal with no
  US analog, free from Eastmoney — note `_leaderboard()` in build_china.py already hits the
  Eastmoney datacenter); discovery-style cross-sector leaderboard; deep-history A-share fetch +
  PIT CSI membership to lift Phase 0 from "context" toward a stronger claim.

## Honest cautions (carried into the UI copy)

- Modest, crowded, regime-decayed edge; nothing clears the strict bar on 5y → **context, not a
  buy list** (same disclaimer the US leg ships with).
- Survivorship: top-mcap-today universe. Note it; deep-history + PIT membership is the fix.
- A-share daily price limits (±10%/±20%) and retail reversal mean the short frame is timing,
  not selection.
- Fundamentals are the genuinely hard gap (no free XBRL); ship momentum/cycle/regime first.

## Literature
Blitz–Huij–Martens (2011) *Residual Momentum*; Moskowitz–Grinblatt (1999) *Do Industries
Explain Momentum?*; Jegadeesh (1990)/Lehmann (1990) short-horizon reversal. All reproduced
directionally on A-shares here (residual durability, sector-neutral best, short = reversal).
See `research/RESIDUAL_ALPHA_MOMENTUM.md` for the US parent study.
