# China A-share Dashboard — Engine Overhaul

*Goal:* radically improve the China (A-share) stock ranking engine — richer/more-accurate signals,
deeper + research-proven technical indicators tuned to A-share microstructure, the volatility
black hole, a GEX-analog vol confirmer, fewer page↔engine discrepancies. Reuses the US overhaul
where it transfers; adds A-share-specific edges where the US logic does NOT transfer.

Grounded in a 6-agent code+research survey (`reversal`/`turnover`/`northbound`/`margin`/`limit`/
`qvix` literature + the live CN build).

## 1. What ships today + the load-bearing bug

`scripts/build_china_library.py` mirrors the US build but is **close-only** throughout (thin
`engine.technicals.snapshot`, no vol-squeeze, no OHLCV indicators). The CN conviction is
reversal-led in *design* (`_axis_selection` CN = 0.55·rev_z + 0.25·revision + 0.20·alpha).

**THE bug:** `engine.china_reversal.reversal_watch(top_n=16)` only emits a reversal z for **16
names**, but `conviction_profile` is built for ~800. So for the vast majority the selection axis
has **only `alpha` (residual momentum)** — a signal the engine itself labels *"not a validated
A-share edge."* And the buy shortlist is gated on `alpha ≥ 0.5`. So the board is effectively ranked
and gated by the **wrong** signal (US-style momentum) in a market where **momentum fails and
short-term reversal dominates.**

## 2. A-share research verdicts (what transfers, what inverts)

* **Short-term REVERSAL is the dominant, strongest A-share anomaly** (RSI-5/10 with *tighter* 25/75
  thresholds, 5-day return rank, distance-from-MA20). Overreaction cycles are faster than US.
* **QVIX must be INVERTED vs US.** China has a *positive* return-volatility correlation
  (anti-leverage): a high QVIX is **not** "fear-bottom." Use `qvix_z` (vs 60d), not the level:
  panic-spike (z>+2) → halt entries; suppressed (z<−1) → squeeze/size-up. This is the GEX-analog.
* **Margin-financing (融资余额) surge = crowding / fire-sale risk** (the 2015 crash mechanism) — a
  contrarian RISK, not a positive.
* **Standard 3–12mo momentum FAILS**; only 12-1 momentum + 52-week-high (ex-February) have any
  edge, and only regime-gated. Vol-compression is a **size amplifier** for reversals, not a
  direction. Price-limit days (|ret|>9.5%) need special handling (continuation day+1, fade day+2/3).
* **Does NOT transfer:** US momentum, VIX-as-fear, the low-vol/size/quality anomalies, golden-cross
  as an entry. Use MA120 only as a *regime gate*.

## 3. Design (reuse US + A-share specifics)

1. **Fix reversal coverage** — `reversal_watch` top_n 16 → the whole screenable universe, and gate
   the buy shortlist on the validated reversal (not `alpha`). *The single highest-impact fix.*
2. **Rich close-only technicals** — swap the thin snapshot for `engine.stock_technicals.snapshot`
   (momentum, 52w-high proximity, BBWP, HVP, RSI, MA regime — close-only mode).
3. **New `engine/china_signals.py`** — A-share-specific close-only signals: RSI-5/RSI-10 (faster
   reversal), 5-day return, distance-from-MA20 z, MA120 regime gate, price-limit flag, STAR/ChiNext
   detection → a China-tuned ENTRY refinement (reversal-in-uptrend buy, panic/limit suppression).
4. **Volatility black hole** — `engine.vol_squeeze.assess(close)` (close-only) → "Coiled" chip +
   the bounded squeeze tilt; framed as a *reversal size amplifier* per the A-share evidence.
5. **QVIX vol-regime overlay (the GEX-analog)** — `qvix_z` (vs 60d, inverted) → a CN `risk_overlay`
   that taxes a chase into a panic-spike + a market vol-regime context chip. (A-shares have no
   single-stock options GEX; the index-vol QVIX is the honest analog — stated on the page.)
6. **Per-stock margin-financing risk leg** — a surging 融资余额 (`china_margin_detail`) → an
   idiosyncratic-risk penalty + caution (crowding), not a positive.
7. **CN anticipation cone** — reuse `engine.anticipation.anticipate(close, bench=CSI300)` → the
   risk-shape tilt + favourable-cone notes (the AVGO/NVDA fix), giving CN the cone it lacked.
8. **Regime ctx** — pass a CN `calm`/regime + the qvix risk_overlay into `conviction_profile`.
9. **Page discrepancies** (china.html + china_lookup): fix the sort-key-vs-label claim; clarify the
   α chip is residual momentum (not the reversal edge); make axis labels consistent; mark
   Piotroski/Altman "(context only)"; add a QVIX vol-regime chip + the Coiled chip + the honesty
   notes; make `trust_tier` legible.

## 4. Honest constraints
* A-shares are **close-only** per stock → no ATR/ADX/volume/Donchian/TTM-squeeze; the vol black
  hole uses the close-only BBWP+HVP gate.
* **No single-stock options** → no per-stock GEX; the QVIX market vol-regime is the analog.
* Margin data is ~monthly; treated as a slow positioning/risk read, not a fast signal.
* No new validated alpha is claimed; reversal is the validated edge, the rest are confirmers/risk.

## 5. Phases
1. `engine/china_signals.py` + `engine/china_vol_regime` (qvix) (+ tests)
2. `build_china_library.py` wiring (reversal coverage, rich tech, vol-squeeze, qvix overlay, margin
   leg, anticipation, buy gate)
3. `stock_score.py` CN refinements (China entry tilt, margin idio leg) if needed
4. Page discrepancies + chips (china.html, china_lookup)
5. Phase-0 honesty (reversal/qvix reproducible checks) + tests + verify + commit + merge
