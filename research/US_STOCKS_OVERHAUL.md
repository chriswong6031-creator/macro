# US Stocks Dashboard — Engine & Page Overhaul (v1)

*Goal (user brief):* radically improve the engine that ranks the US-stock board
(`us_stocks.html`); use richer, more accurate signals; apply deeper + research-proven
technical indicators; add the **volatility black hole** concept for single stocks; add
**GEX options data as a verifier/confirmer**; reduce page↔engine discrepancies (or clarify
them); generally make the signals more honest and more accurate.

This document is the audit + design. It is grounded in an 11-agent code/research survey of
the live engine, page, GEX/vol-hole machinery, the data layer, and the academic/practitioner
literature on technical + dealer-gamma signals.

---

## 1. What ships today (audit)

* **The board.** `scripts/build_stock_library.py` writes two artifacts the page reads:
  * `site/factordata/us_standouts.json` — the **wide "Standout individual stocks" board**.
    It is sorted by the **4-axis Conviction `composite_z`** (selection · entry · tailwind ·
    quality) from `engine/stock_score.py`, then split into buy / watch / laggards by an
    entry-quality gate. `rank_by` is written `"conviction"` (gate NEUTRAL).
  * `site/factordata/setups.json` — the **Top Setups** table, sorted by the **validated
    sector-neutral residual-alpha** leg (`rank_setups(rank_by="alpha")`).
* **The conviction engine** (`engine/stock_score.py`) is an explicit, honesty-first
  decomposition: each axis is a signed z over already-cross-sectional legs; `composite_z` is a
  display/ordering prior (never a claimed validated alpha unless a deep-CI Phase-0 sets
  `gate_go`); subtract-only macro + idiosyncratic risk taxes; a within-market percentile is the
  0–100 display skin.

### 1.1 The biggest problems

1. **The page lies about the rank.** The standout sub-header says *"cleared the +0.5 α floor ·
   ranked across the full S&P 1500 by validated residual momentum"* and the α-chip tooltip calls
   alpha *"the validated ranking leg"* — but the board actually sorts by `composite_z`
   (alpha is a 0.10–0.28 weight leg), and the `+0.5 α floor` belongs to a *different* board
   (Top Setups). The per-card `trust_tier` simultaneously says the edge is *"a confluence read,
   not a standalone alpha."* These contradict each other on the same card. (12 distinct
   label/engine discrepancies catalogued — see §5.)
2. **Thin technicals.** The per-stock `tech` block is `snapshot(close)` only: `rsi14`,
   `pct_vs_50/200dma`, `off_52w_high_pct`, `macd_pos`. No ATR, ADX, volume, squeeze, realized-vol
   percentile, multi-horizon RS, vol-scaled momentum, or 52-week-high proximity. RSI is
   implemented **five different ways** across the repo; the 52-week-high window has **three**
   different `min_periods`.
3. **GEX is wasted.** Per-stock GEX is computed with the *light* `compute_gex()` (no walls, no
   `vol_hole`, `iv30` left in the wrong unit) for a **stale hardcoded 25-name list**, and the
   engine only reads `gamma_regime` as a one-sided *risk* haircut (`short=0.6`). The rich
   `site/gex/<T>.json` payloads (regime, gamma-flip distance, call/put walls, `vol_hole` state,
   expected move) already exist for ~20 single names + ETFs and are never joined.
4. **No single-stock volatility black hole on the board.** `engine/dannytrades.py` already
   computes a price-based Bollinger-bandwidth squeeze box, and `engine/gex_model.volatility_hole`
   computes the dealer-gamma vol-hole — but neither reaches the standout board or the entry timing.
5. **Entry-axis math dilutes hard penalties.** `_axis_entry` takes an *unweighted mean* of
   urgency + drawdown + RSI + extension/lottery penalties, so a `-1.0` parabolic flag gets averaged
   away by a good urgency reading; the result is then multiplied by an undocumented `1.6`.

---

## 2. Data reality (hard constraints)

| Tier | Universe | Data available | What we can compute |
|---|---|---|---|
| **A** | ~20 single names + ETFs with `site/gex/<T>.json` (AAPL, NVDA, TSLA, META, AMD, MSFT, GOOGL, AMZN, AVGO, MU, MSTR, COIN, PLTR, SMCI, NFLX, UBER, HOOD, GME, BABA, MRVL…) | full OHLCV **+** dealer-gamma payload | deep OHLCV technicals **+** price vol-squeeze **+** GEX confirmer |
| **B** | 114 names in `data/stocks/*.parquet` | full OHLCV (close/high/low/volume) | deep OHLCV technicals **+** price vol-squeeze |
| **C** | ~503 S&P 500 names (breadth close cache) + S&P 400/600 | **close only** | close-only enrichments (vol-scaled momentum, 52wk-high proximity, realized-vol pctile, BB-bandwidth squeeze proxy, MA regime) |

This tiering is honest and visible on the page: ATR/ADX/volume/GEX chips only render where the
data exists; the rest of the board still gets the close-only upgrades. **No new data collection
is required** — every input already lands in the repo before `build_stock_library` runs.

---

## 3. Research verdict — what actually has edge

From the literature survey (sources in the workflow transcript). Used to decide what may touch
*ranking* vs what is *confirmer/display only*.

* **Strong** (cross-sectional ranking): residual momentum; **volatility-scaled momentum**
  (Daniel–Moskowitz "Momentum Crashes"); **52-week-high proximity** (George–Hwang); MA trend
  regime; relative strength. Net-GEX→realized-vol is **strong** academically (Soebhag 2023) but
  predicts *vol regime*, not price.
* **Moderate** (timing confirmer, not standalone alpha): ADX/DMI trend strength; TTM squeeze /
  BBWP / HVP compression; volume confirmation (OBV/CMF/relative volume); Donchian breakouts;
  Connors RSI-2.
* **Context only / weak:** Choppiness Index (state descriptor); raw skew level; **charm**
  (structurally bearish — *exclude from any tilt*, per the existing GEX work).
* **GEX-as-confirmer rules:** use the gamma regime, gamma-flip distance, wall proximity, and
  `vol_hole` state; use 25Δ risk-reversal **change** not level; **exclude raw charm + absolute
  skew**; suppress to NEUTRAL in the 2 days pre-OPEX; require minimum options liquidity. The
  confirmer may only **downgrade** confidence (CONFIRM→NEUTRAL→CAUTION) — it can **never
  manufacture a buy** on a weak setup.

---

## 4. Design

Three new pure-function engine modules + careful wiring. Everything respects the honesty gate:
*validated → may rank; confirmer/display → context only.*

### 4.1 `engine/stock_technicals.py` — canonical, OHLCV-aware technical snapshot
Supersedes the thin `snapshot(close)` (kept back-compatible). Graceful: computes whatever the
available columns allow. Vetted set:
* **Trend:** above 20/50/200, golden cross, `pct_vs_*dma`, 50-dma slope, **ADX(14)+DI±**.
* **Momentum / RS:** 1/3/6/12m return, **12-1 momentum**, **vol-scaled momentum**,
  **52-week-high proximity**, `off_52w_high`.
* **Mean-reversion:** RSI-14 (canonical), **RSI-2** (Connors), distance-from-50dma.
* **Volatility / squeeze:** **ATR%**, **HV(20) + HVP(252)**, **BB bandwidth + BBWP(252)**,
  **Keltner**, **TTM squeeze** flag, **Choppiness(14)**, **NR7**.
* **Volume:** relative volume, **OBV slope**, **CMF(20)**, dollar volume, volume-confirmed
  breakout.
* **Channels:** Donchian(20/55) position.

### 4.2 `engine/vol_squeeze.py` — single-stock volatility black hole (price)
Dual-gate compression (BBWP<20 **and** HVP<20) + duration counter + sticky squeeze box; a
directional fire requires the close to clear the box **with** volume confirmation. States:
`COMPRESSED` / `COILED_UP` / `COILED_DOWN` / `FIRED_UP` / `FIRED_DOWN` / `EXPANSION` / `NONE`.
Honest framing: a *timing* read ("a move is loading; direction unconfirmed until it fires"),
moderate edge, never a standalone alpha. This is the price analog of the GEX `vol_hole`.

### 4.3 `engine/gex_confirm.py` — GEX verifier/confirmer
Pure function over a joined `site/gex/<T>.json` payload + the stock's own direction → a discrete
**CONFIRM / NEUTRAL / CAUTION** verdict for a long entry, following the §3 recipe. Bounded: only
downgrades, never creates a buy. Replaces the crude one-sided `gamma_regime` risk usage. Also
adds an explicit `rr_25d` (25Δ risk-reversal) to `engine/gex_model.vol_smile`, and joins the rich
GEX payload into the stock record (fixing the `iv30` unit bug + missing walls/`vol_hole`).

### 4.4 Wiring (`stock_score.py` + `build_stock_library.py`)
* **Entry axis:** replace the flat mean with a weighting that preserves hard penalties; add a
  **vol-squeeze timing tilt**, a **GEX-confirmer tilt** (bounded ±), and a **trend-quality**
  (ADX-confirmed) tilt. Document the scaling. Smooth the step-function `drawdown_hump`.
* **Idio risk:** upgrade the GEX leg to the confirmer's read (adds a neutral state); add a
  vol-regime component. Keep subtract-only + bounded.
* **Selection:** add **vol-scaled momentum** and **52-week-high proximity** as light,
  regime-scaled *context* legs (display unless a gate validates them). Fix the confidence-floor
  that over-ranks single-leg names.
* **Pipeline:** compute the tech/squeeze maps over the OHLCV universe; join `site/gex/<T>.json`;
  thread new kwargs through `normalize_rec`; surface `gex_confirm` + `vol_squeeze` on board rows.
  Fix the `ProcessPoolExecutor` `name_dir_inputs` arg-drop and the missing `MRVL` join; broaden
  the GEX universe from `site/gex/`.

### 4.5 Page (`templates/dashboard.html.j2`)
Fix all 12 discrepancies (§5) and add two new, clearly-captioned chips to the standout cards and
Top Setups: **"Options check"** (GEX CONFIRM/NEUTRAL/CAUTION) and **"Coiled/Firing"** (vol black
hole). Make the rank label always match the actual sort key.

### 4.6 Phase-0 honesty (`scripts/us_stocks_signal_phase0.py`)
Run whatever validation is reproducible on the committed data (vol-scaled vs raw-momentum IC on
the available window; squeeze→forward-move asymmetry on the 114 OHLCV names; GEX-regime→forward-RV,
extending `validate_gex`) and write an honest report with explicit limitations (the deep PIT panel
is offline-only, so no new multi-decade alpha is claimed). New legs enter the *rank* only if a
gate passes; otherwise they are display/confirmer.

---

## 5. Discrepancies to fix (page ↔ engine)

1. Standout sub-header "+0.5 α floor · ranked by validated residual momentum" → accurate text
   (ranked by the Conviction composite; the entry-quality gate count).
2. α-chip tooltip "the validated ranking leg" → match `trust_tier` ("a light context leg, not a
   standalone validated alpha").
3. `rank_by` should drive the header so the label always matches the sort key.
4. `eligible` counter semantics + label.
5. Dual field names `alpha` vs `alpha_z` across the two card paths.
6. Sector heat "3mo" vs tooltip "60 trading days".
7. HOLD/avoid column collapses two different urgency semantics.
8. Score **band** vs verdict **verb** can disagree (note it).
9. `iv30` unit mismatch (decimal vs percent) between stock record and `site/gex`.
10. `MRVL` in `OPTIONABLE_GEX` but no join target.
11. `ProcessPoolExecutor` silently drops `name_dir_inputs`.
12. `accounting=='watch'` caps quality but never overrides the verdict verb.

---

## 6. Phases

1. `engine/stock_technicals.py` (+ tests)
2. `engine/vol_squeeze.py` (+ tests)
3. `engine/gex_confirm.py` + `rr_25d` + GEX join (+ tests)
4. `stock_score.py` wiring (+ tests)
5. `build_stock_library.py` pipeline wiring + bug fixes
6. Template/UI: discrepancies + new chips
7. Phase-0 honesty script + report
8. Build · verify · full test suite · adversarial review · commit · PR · merge

## 7. Non-goals / guardrails
* No new claimed validated alpha without a passing gate. GEX + squeeze are **confirmers**.
* Never relax the radioactive over-extension floor (>35% / parabolic).
* Confirmers can only lower conviction, never rescue an AVOID/extended name.
* Every new signal renders only where its data exists; missing ≠ neutral.
