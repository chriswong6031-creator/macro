# Provider recon — CryptoQuant · CoinGlass · Laevitas

_Researched 2026-06-13 (3 parallel web-research agents, cited). Question: what do
these vendors sell, what are their flagship metrics, and which can we
reverse-engineer onto our free stack for the three modeling layers the user
named — **on-chain regime**, **leverage/liquidation risk**, **options/funding
structure**? Companion to VECTOR_ACCURACY_UPGRADE.md._

## TL;DR — the one big finding
**Laevitas and CoinGlass mostly repackage free public data; CryptoQuant's moat is
the only one we can't copy.**
- **Laevitas** options analytics ≈ a skin over the **free public Deribit API**
  (Deribit = ~80-90% of BTC/ETH options OI). IV term structure, 25Δ skew, max
  pain, put/call, basis, DVOL — all reproducible by us. Only GEX *dealer-sign*
  is a modeling assumption.
- **CoinGlass** derivatives ≈ cross-exchange **aggregation** of OI/funding/
  liquidations. Its signature **liquidation heatmap is MODELED** (OI × assumed
  leverage buckets), not raw prints — so it's a *method to rebuild*, not data to
  copy. We already hold OI + funding across 15 exchanges free via **BGeometrics**.
- **CryptoQuant** is the genuine moat: **wallet-labeled exchange/miner/whale
  flows** (Netflow, Reserve, Whale Ratio, MPI). No free API. BUT its most-cited
  regime signal — the **P&L / Bull-Bear Index = MVRV+NUPL+SOPR vs 365d-MA** — is
  exactly the valuation axis we just built in Tier 1.

Neither CoinGlass nor CryptoQuant has a usable **free API** (paid $29+/mo). The
reproducible path is to *rebuild the metric from raw sources we already reach*,
not to call their API.

---

## 1. CryptoQuant — on-chain regime
**Moat:** proprietary address labeling/clustering of exchange, miner, whale
wallets. No free API (Pro $109/mo for daily API, Premium $799 for block-level).

| Flagship metric | Definition | Reproducible free? |
|---|---|---|
| Exchange Netflow / Reserve | in−out of labeled exch wallets; Reserve = cumulative balance | **NO — the moat.** bgeo exchange-netflow was 403-gated. Proxy only (CoinMetrics aggregate exch balance, weak) |
| Exchange Whale Ratio | top-10 inflow txns / total inflows (72h MA); >0.85 bearish | **NO** — needs per-tx deposit labeling |
| Miner Position Index (MPI) | miner outflow USD / 365d-MA | Partial — we have bgeo `miner_sell_pressure` (outflow/reserve), can build an MPI-like z-score |
| **Coinbase Premium** | Coinbase BTC-USD − Binance/OKX BTC-USDT; % variant /price | **YES** — Coinbase spot (have) − OKX BTC-USDT spot (small add). Institutional-demand proxy |
| Korea/Kimchi Premium | Upbit VWAP − global VWAP, KRW→USD | Yes (Upbit public API + FX) — lower priority |
| **SSR (+ oscillator)** | BTC mcap / stablecoin mcap | **YES — already derived** (D41); add the oscillator (RSI/z of SSR) |
| Taker Buy/Sell Ratio | taker buy vol / sell vol (perps) | Yes — OKX public; Binance/Bybit blocked → single-venue |
| MVRV / NUPL / SOPR / LTH-STH | standard valuation cohort | **YES — Tier-1 done** (MVRV-Z, NUPL) |
| **Bull-Bear Cycle (P&L Index)** | MVRV+NUPL+LTH/STH-SOPR composite, regime = cross of 365d-MA | **YES — rebuildable**; validates our valuation axis |

**Verdict:** on-chain *valuation* regime is fully ours (Tier 1). The labeled
*flow* regime (Netflow/Whale/Reserve) is the real moat — skip or weak-proxy.
Worth adding: **Coinbase Premium**, **SSR oscillator**, **MPI-from-miner-pressure**.

## 2. CoinGlass — leverage / liquidation risk
**Moat:** aggregation across 29+ exchanges. Website free; **API paid only**.

| Flagship | Raw or modeled? | Reproducible from our stack (bgeo OI+funding 15-exch, OKX, Deribit)? |
|---|---|---|
| **Liquidation heatmap** | **MODELED** (OI × assumed 5/10/25/50/100× buckets; "actual may be lower") | **Rebuild the method**, not their numbers — "price distance to dense liq cluster" is the best short-horizon squeeze signal |
| Aggregated OI / OI by exch | raw | **YES** — bgeo gives OI across 15 exchanges |
| **OI-weighted funding** | raw | **YES** — bgeo funding + OI → compute our own weighted aggregate (cleanest crowding gauge) |
| OI-vs-price divergence | derived | **YES** — ΔOI vs Δprice (OI↑ + price flat = crowded/leveraged) |
| Long/Short ratio (global/top) | raw, exch-sourced | Partial — OKX only (Binance/Bybit blocked → not global) |
| Taker buy/sell, CVD | raw | Yes — OKX/Coinbase/Deribit tapes (single-venue) |
| Basis / annualized / perp premium | raw | **YES** — OKX/Deribit futures vs spot (leverage-froth confirmer) |
| Actual liquidation prints | raw (throttled) | Partial — OKX public feed; others blocked → undercount |
| Options OI / max pain | raw (Deribit-dominated) | **YES** — see Laevitas section |

**Verdict:** ~70% of their futures moat is already free to us. Highest forward
signal: **OI-weighted funding**, **OI-vs-price divergence**, a **home-built
liquidation-cluster proxy**, **basis**. The heatmap is a model, not magic.

## 3. Laevitas — options / funding structure
**Moat:** cross-exchange aggregation + stored history. Options math is mostly
public-Deribit-derived. Free dashboards + paid Pro/API.

Deribit's **free, unauthenticated** API is the key enabler:
`/public/get_book_summary_by_currency` (per-instrument `mark_iv` + `open_interest`
+ `underlying_price`, whole chain in one call) · `/public/ticker` (greeks + OI +
mark_iv) · `/public/get_instruments` · `/public/get_index_price` ·
`/public/get_volatility_index_data` (DVOL). Rate-limited per IP — poll every few
seconds, not per-ms.

| Metric | Verdict |
|---|---|
| ATM IV term structure / vol surface | **Reproducible** — interpolate mark_iv across expiries |
| **25Δ skew / risk reversal** | **Reproducible** — RR = IV₂₅Δcall − IV₂₅Δput; normalized skew = (IV₂₅Δput − IV₂₅Δcall)/IV_ATM. *Best forward tail-risk gauge.* |
| DVOL | **Already pulled** — just keep it; add percentile/term |
| Vol cones | Reproducible — rolling percentiles (needs our history store) |
| Realized vs Implied / **VRP** | Reproducible — VRP = IV − realized-vol (sentiment/risk-premium gauge) |
| OI by strike / max pain / put-call | Reproducible — all from per-instrument OI |
| Basis / term structure / funding / perp premium | Reproducible — mark_price/index_price/funding fields |
| **GEX / dealer gamma** | **Partly** — raw gamma×OI×spot² surface reproducible; net *dealer sign* is the one genuine modeling assumption (their convention unpublished) |

**Verdict:** the highest-reproducibility layer of all three — Deribit is free and
we already have the pipe. Build the full options panel from
`get_book_summary_by_currency`: **IV term structure, 25Δ skew/RR, DVOL percentile,
VRP, put/call, max pain**, and a GEX surface (with the dealer-sign caveat).

---

## 4. Usefulness-to-modeling verdict (the user's three questions)

| Layer | Useful? | What to add (reproducible) | Predictive vs context |
|---|---|---|---|
| **On-chain regime** | Yes — partly already in Tier 1 | Coinbase Premium · SSR oscillator · MPI-from-miner-pressure · rebuild Bull-Bear P&L Index as a cross-check on our valuation axis | Coinbase Premium = leading institutional-demand; rest = regime context |
| **Leverage/liquidation risk** | **Yes — highest new-signal value** | OI-weighted funding · OI-vs-price divergence · liquidation-cluster proxy · basis/perp premium | Forward risk amplifier; powers flash-crash *pre*-warning |
| **Options/funding structure** | **Yes — highest reproducibility** | IV term structure · **25Δ skew/RR** · DVOL percentile · VRP · put/call · max pain · GEX surface | 25Δ skew + VRP = genuine forward tail-risk signal, orthogonal to trend/valuation |

**Honesty caveat (house rule):** all derivatives series only reach ~1 cycle
(2021/2022→), so they are **confirmation/regime context, not calibration
anchors** — same discipline as Tier 1's cohort metrics. Most predictive, lowest
collinearity additions, ranked: **25Δ skew → OI-weighted funding →
OI-vs-price divergence → Coinbase Premium → VRP**.

## 5. Buildable shortlist (grounds Tiers 2-3 of the upgrade plan)
1. **Deribit full-chain collector** (`get_book_summary_by_currency`) → options panel: IV term structure, 25Δ skew/RR, put/call, max pain, GEX surface. _Biggest win, fully free._
2. **Leverage/liquidation component**: OI-weighted funding + ΔOI-vs-Δprice + liquidation-cluster proxy from bgeo OI (15-exch) → new Risk Index input + flash-crash pre-warning.
3. **Coinbase Premium** (Coinbase spot − OKX BTC-USDT spot; small OKX-spot add) → on-chain-regime / institutional-demand input.
4. **SSR oscillator** + **MPI** from data already on disk.
5. Each gated by the same split-half forward-return/drawdown calibration before any blend.
