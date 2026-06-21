# Signal Audit — Institutional-Grade Correctness Review

**Repo:** Macro Dashboard (quant macro/equity signal stack)
**Date:** 2026-06-21
**Scope:** Look-ahead/leakage, survivorship bias, sign/inversion, dead legs, calibration honesty, and the opportunity map toward institutional-grade modeling.
**Method:** Direct code reads with file:line citations; empirical reproduction where a leak/inversion was claimed. One refuted high-severity claim (`anticip-cone-fullsample-edges`) was dropped after verifying the live cone is point-in-time by construction (`as_of == end-of-sample`).

---

## PART 1 — CONFIRMED BUG LEDGER (severity-ordered)

Severity legend: **HIGH** = can flip a user-facing verdict / size a wrong-direction position; **MEDIUM** = biases a displayed statistic, double-counts a theme, or silently disables a weighted leg; **LOW** = display/units/disclosure.

### HIGH

#### BUG-1 — Ladder buy-states never check higher-timeframe topping (buy-high) `[logic]`
- **File:** `engine/cycles.py:726-741, 880-922, 937-955`
- **Symbol:** `ladder_state`
- **Evidence:** The FRESH BUY / TURN SIGNALED branch gates only on bullish daily momentum:
  `engine/cycles.py:726` — `elif cand_confirmed and (d.get("macd_cross_up") or d.get("macd_pos") or d.get("macd_approaching_up")):`
  then `:728` — `state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"`. No topping flag participates.
  The only buy-state cap is RSI-level only: `:896-897` — `if state in ("FRESH BUY", "TURN SIGNALED") and cyc.get("above_ma10") and (rsi_d > 70 or (rsi_3 > 70 and rsi_w > 70)):`.
  The bear/topping nudge explicitly excludes buy states: `:948` — `elif early.get("dir") == "down" and state in ("TOP WATCH", "RALLY ON"):`. Confirmed by read: `t3` (3D dict) is consulted only for `rsi_3` (`:894`); its `macd_curl_dn`/`macd_cross_dn` are never read in `ladder_state`.
- **Impact:** A name printing a daily bottoming setup at moderate RSI while its 3D/weekly histogram has peaked and rolled over is scored as a high-conviction BUY with no cap.
- **Fix:** Extend `extended_gate` (`:896-897`) to also fire when `d.get('macd_curl_dn') or t3.get('macd_curl_dn') or t3.get('macd_cross_dn') or w.get('macd_curl_dn') or w.get('macd_cross_dn')`, routing to TOP WATCH; equivalently let `early.get('dir')=='down'` CAP (not merely nudge) FRESH BUY/TURN SIGNALED. Re-run `calibrate_ladder` (state-key change). Gate the fix on the measured penalty from BUG-CAL bucket (opportunity `calibrate-topping-cap-bucket`).

### MEDIUM

#### BUG-2 — Entry/timing axis double/triple-counts the oversold theme `[overfit]`
- **File:** `engine/stock_score.py:583-604` (axis `_axis_entry`); composite definition `engine/strategy_signals.py:350-362`
- **Evidence:** Three legs encoding the SAME oversold/pullback theme are equal-weight averaged: `_drawdown_hump(off_52w_high_pct)` → `present.append("off-high")` (`engine/stock_score.py:583-585`), `_rsi_band(rsi14)` → `present.append("rsi")` (`:586-588`), and the mean-rev composite `rec["strategy"]["entry_z_axis"]` → `present.append("mean-rev-composite")` (`:602-604`) — which is itself the mean of rsi2/rsi14/pullback/%b/stretch. So rsi14 and the pullback signal each enter twice, out of ~4-5 legs.
- **Empirical:** raw `corr(rsi14, entry_z_axis) = -0.90`; banded `off-high` vs `rsi_band` = 0.52; adding the composite lifts an oversold name's `entry_z` ~0.45→0.78 (+70%) purely from re-counting. VIF stays low (1.4-1.6) because coarse step-bands destroy variance, masking the redundancy.
- **Fix:** When `entry_z_axis` is present, treat the mean-rev composite as the single oversold-timing leg and drop the redundant `_rsi_band` and 52w `_drawdown_hump` from the average (or down-weight them). Better: route the entry legs through a decorrelated blend (opportunity `entry-axis-pca-or-decorrelated-blend`).

#### BUG-3 — Vector ensemble "both-halves OOS" claim is in-sample-oriented `[survivorship/honesty]`
- **File:** `scripts/calibrate_vector.py:304-369` (esp. 309-312, 327, 339, 352-356)
- **Symbol:** `ensemble_promotion` / `_expret_signal`
- **Evidence:** `_expret_signal` builds the band→mean orientation from the WHOLE sample: `:309-312` — `t = band_table(signal, fwd, bands, labels, [h]); m = {...}; cats...map(m)` with `fwd` full-sample. Each axis is oriented full-sample (`:327`), then the SAME oriented signal is sliced per half: `:352-355` — `def ns(e, idx): ...backtest_core(close.loc[idx], e.reindex(idx)...)`; `table = {name: {half: ns(e, idx) ...}}`. The reported ICs are full-sample too: `:339` `ics = {s: round(...R[s].rank().corr(fwd[h].rank()))...}` and `:356` `ens_ic = round(...ens.rank().corr(fwd[h].rank()))`. The "PROMOTE — beats ... in both halves" verdict (`:362`) and `ensemble_ic` reported as OOF (`:356`, summary `:802`) are therefore NOT out-of-sample.
- **Fix:** Orient the band→mean map and `resid_z` basis on the TRAIN side of each half/fold only (reuse the `oof_cell_probs` OOF pattern already in this file, or `engine.validation.purged_folds`), then report truly out-of-fold per-half Sharpe and pooled OOF IC. Relabel `ensemble_ic` as in-sample until done.

#### BUG-4 — Live ladder calibration is survivor-only, shipped without disclosure `[survivorship]`
- **File:** `scripts/recalibrate.py:28-37`; `engine/cycles.py:1725-1737`; render `scripts/build_site.py:957`
- **Symbol:** `calibrate_ladder` / `recalibrate.main`
- **Evidence:** `scripts/recalibrate.py:32-35` — `for t in top10_union()[::4]: df = store.read("stocks", t) ... panel[t] = df["close"]` — only current sector-ETF top holdings (the ~114 survivors in `data/stocks/*`). `engine/cycles.py:1730` — `'hit_pct': round(100 * (a > 0).mean(), 1)`. Rendered to UI at `scripts/build_site.py:957` — `f'<td>{s["hit_pct"]:.0f}%</td>'`. Shipped JSON carries no `universe`/`survivorship` field.
- **Impact:** Every state's forward win-rate is biased high; drawdown tails too shallow.
- **Fix:** (a) recompute on a delisting-aware PIT panel (opportunity `build-delisting-aware-universe`), or (b) at minimum stamp the JSON with `universe`/`n_names`/`survivorship_biased:true` and surface a one-line caveat next to `hit_pct` (opportunity `stamp-calibration-universe-metadata`).

#### BUG-5 — Bottom-confidence calibration is survivor-only, advertised "no look-ahead" only `[survivorship]`
- **File:** `scripts/calibrate_bottom_confidence.py:3-9, 55, 63`
- **Symbol:** `main`
- **Evidence:** `:55` — `data = config.data_dir() / 'stocks'`; `:63` — `files = sorted(data.glob('*.parquet'))` (the ~114 survivors). Docstring `:3-9` advertises "~40y, no look-ahead" (temporally clean) but never mentions the name set is current survivors only. Shipped JSON keys `['fwd','bands']` carry no survivorship field. The per-band held-rate that GATES whether the score is "worth surfacing" is computed on a survivorship-biased universe.
- **Fix:** Same remedy as BUG-4 — delisting-aware panel or explicit survivorship stamp + UI caveat. Both calibrations share the `data/stocks` survivor panel.

### Notable MEDIUM bugs from the broader sweep (carry into fix phase)

| ID | File:line | One-line |
|---|---|---|
| `sector-rs-tailwind-dead-all-markets` | `engine/stock_score.py:617-629`; library builders | `sector_rs=` never passed to `normalize_rec` → tailwind sector-RS sub-leg dead in EVERY market; tailwind axis runs on null basket leg alone for ~83% of US names. |
| `cn-sel-kind-mislabel-earnings-insider` | `engine/stock_score.py:224` | `_sel_kind` checks `sue/insider/revision` before `rev_z`; CN names with revision data mislabel as "earnings · insider · revisions" though CN has no insider/SUE feeds and its edge is reversal — contradicts the on-card trust_tier. |
| `entry-quality-ignores-curl-dn` | `engine/cycles.py:1332-1358` | `entry_quality` axis (`_eq_freshness`/`_eq_momentum` UP) also never consults `macd_curl_dn`; does NOT independently rescue BUG-1. |
| `extension-penalized-four-places` | `engine/stock_score.py:589-594, 887-893, 448-451, 482-510` | Same over-extension taxed in 4 compounding places; entry axis already discounts it, then composite taxes again. Bounded/subtract-only but verify it doesn't invert strong names. |
| `pit-fwd-delisting-return-truncation` | `scripts/residual_alpha_phase0.py:168, 181-184` | Even the honest PIT path drops delisted forward-NaN rows (`fr.dropna()`) — no delisting-return stitch, so worst outcomes excluded (Shumway bias). |
| `edgar-pit-panel-drops-delisted-ciks` | `collectors/edgar.py:412-424` | PIT fundamentals CIK→ticker map built from CURRENT universe; delisted CIKs dropped → factor backtest only sees survivors. |
| `bt-signals-overlapping-windows-no-purge` | `scripts/_bt_signals.py:19-20, 52, 65-66` | F1=21/F2=63 windows sampled every STEP=10 → overlapping; pooled stats treat as independent (no purge/HAC), inflating effective N. |
| `anticip-volband-fullsample-median` | `engine/anticipation.py:254-257, 287` | Vol-bucket boundary from full-sample median + `cond_up_prob` base over all history; benign live (EB-shrunk, capped [0.43,0.58]) but not strictly PIT vs the banner. |
| `lowvol-quality-axis-wrong-sign` | `engine/stock_score.py:645-649` | Quality fallback averages `low_vol` higher=better, but measured IC is NEGATIVE (`ic_scorecard.json` low_vol mean_ic −0.0209); strongest survivor `payout` (+0.0247) excluded. |

### LOW (disclosure / units — batch-fixable)
`vex-cex-raw-dollar-scale` (`engine/gex_engine.py:157` net_vex/net_cex raw-$ vs net_gex_bn $bn); `commodity-flow-pctile-365-calendar-window` (`engine/commodity_signals.py:221` 365 lookback on 252-day calendar); `score-skin-mixed-meaning-same-bands` (`engine/stock_score.py:903-906` percentile vs logistic skins share band thresholds); `anticip-index-fullsample-rank` (`engine/anticipation.py:251` index = full-series percentile rank); `edgar-asof-lag-proxy-not-filed-date` (`collectors/edgar.py:325-328` fixed 120d lag proxy); `thematic-stats-ntrials-hardcoded-low` (`scripts/thematic_rotation_phase0.py:133-134` DSR n_trials=10 hardcoded); `macro-betas-insample-fit-validation` (`scripts/calibrate_macro_betas.py:68-111` "validate" is in-sample); `gate-does-not-gate-cone` (`engine/anticipation.py:241-245` cone always conditioned on confluence regardless of gate — doc mismatch); `bt-signals-survivorship-unflagged`, `vector-ensemble-ic-mislabeled-oof`.

### REFUTED (do not action)
- `anticip-cone-fullsample-edges` — verified live cone is PIT because `anticipate()` is only ever called with the full series so `as_of == end-of-sample`; `forward_paths` NaNs the trailing `horizon` rows and `conditional_distribution` filters `ret.notna()`, so no future-of-today bar contributes. The full-sample quantile edges ARE the causal as-of-today distribution. Residual: the cone is not truncate-invariant for *replayed past dates* (a test-coverage gap, opportunity `pit-cone-test-coverage`), not a live leak.

---

## PART 2 — RANKED OPPORTUNITY MAP (toward institutional grade)

Ranking bias: highest-payoff, data-grounded, honestly-validatable. Risk/timing/capital-efficiency levers kept even when not return-alpha; ideas with no plausible net-of-cost edge on free data are demoted/dropped.

### Tier A — Infrastructure that unblocks everything else (do first)

**A1 — Build the delisting-aware PIT universe** (`build-delisting-aware-universe`, effort med)
The #1 institutional-credibility hole. Membership ledger `data/breadth/sp1500_pit_membership.parquet` (3,286 intervals, 1,780 with real end_dates) is committed; the three price panels (`_closes_deep`, `_closes_delisted`, `_closes_delisted_1500`) are gitignored/absent and must be regenerated offline (`scripts.residual_alpha_fetch`, `residual_alpha_pit.fetch_delisted`, `midsmall_pit.fetch_delisted`). Then `residual_alpha_phase0 --pit` unions + filters by `_eligible`. **Validation:** re-run every factor/ladder/bottom stat on PIT-filtered union; expect win-rates to drop. **Payoff:** turns survivor-biased stats into delisting-aware ones; coverage ceiling ~112/1,496 delisted priced on free Yahoo — disclose it. Basis: Shumway (1997), CRSP PIT.

**A2 — Vol-managed sizing scalar** (new infra; lever, not alpha — high priority)
Build one PIT realized-vol-targeting scalar on top of every directional read (`size ∝ target_vol / forecast_vol`, capped). The repo already has `engine/vol_forecast.cone_vol_ann` (HAR) per name and several risk composites. **Validation:** Sharpe / max-drawdown of a vol-scaled vs equal-weight version of any existing scored sleeve on the PIT panel; vol-managed momentum is one of the most replicated risk-adjusted improvements (Moreira-Muir 2017, Barroso-Santa-Clara). **Payoff:** capital-efficiency + drawdown control even with zero new alpha — keep regardless of IC.

**A3 — Purged-CV / OOS orientation harness** (`shared-oos-orientation-helper` + `overlap-aware-event-study-se`, effort med)
One reusable "fit orientation/band-map on train fold, apply to test fold" primitive in `engine.validation` (routing `ensemble_promotion` through it, BUG-3) + a block/HAC SE for the overlapping-window event studies (BUG `bt-signals-overlapping-windows-no-purge`). `engine.validation` already has `purged_folds`, `resid_z`, `ic_summary`, `deflated_sharpe`, `block_bootstrap_ci`. **Validation:** mechanically guarantee any "both-halves"/"OOF" claim is leak-free; honest ensemble Sharpe will likely fall (correctly downgrading PROMOTE→KEEP-HEURISTIC). Basis: Bailey/López de Prado.

### Tier B — High-payoff modeling levers (data already on-build, PIT)

**B1 — Ensemble risk-on/off scalar** (`macro-ensemble-risk-onoff-scalar`, effort med)
Four independently-constructed PIT risk composites already exist on every build (`conditions` MRS/stress, `forex_signals` dollar.risk_off, `cross_asset` absorption verdict, `btc_signals` risk_index). Average/vote them into ONE scalar feeding the stock chase-tax + book eligibility instead of MRS alone. **Validation:** forward-IC and drawdown of the ensemble gate vs MRS-only on PIT panel; ensembling de-correlated gauges should reduce whipsaw. Basis: GS FCI / Chicago NFCI blends. **Payoff:** more stable risk gate, all inputs free + PIT.

**B2 — Net-liquidity gate → SELECTION (not just per-name nudge)** (`net-liquidity-gate-generalize`, effort low)
`engine.regime.liquidity_overlay` (WALCL−TGA−RRP, 3-bd lagged, debounced) is the repo's strongest adversarially-validated orthogonal factor (cited 141-instrument walk-forward edge in `cycles.py:400-411`) but only nudges the US daily ladder. Propagate the same PIT RoC gate to book-level eligibility (raise conviction bar when contracting). **Validation:** split forward returns of the long book by expanding vs contracting liquidity on PIT panel (the split is already measured for ladder setups). **Payoff:** scales an already-validated edge; lowest effort high-conviction item.

**B3 — Regime-conditional weighting (PEAD/momentum/mean-rev)** (`regime-conditional-entry-weights` + meta-label, effort low-med)
The EDGE axis already scales momentum by `calm`. Extend symmetric regime-conditioning to the entry axis (scale oversold-timing DOWN in high-stress — mean-reversion is a falling knife in down-tapes; Daniel-Moskowitz logic the module already cites for momentum). Pair with a **meta-labeling** layer (López de Prado): a secondary purged-CV classifier predicting whether the primary entry/PEAD signal will pay, sizing 0/partial/full. **Validation:** purged-CV AUC of the meta-label + net-of-cost Sharpe uplift vs primary-alone. **Payoff:** improves timing precision without new primary signals.

**B4 — PEAD / earnings-drift via the insider+SUE plumbing** (`insider-panel-path-canonicalization` + EDGAR PIT, effort med)
The 0.40-weight insider EDGE leg is silently dead (`insider_signals()` reads non-existent `insider_panel.parquet` while a `panel/` quarterly dir + `insider.parquet` exist; `equity_factors.py:83,179`). Reconcile the path AND pair SUE with the leak-free EDGAR PIT fundamentals panel (fixing `edgar-pit-panel-drops-delisted-ciks`). **Validation:** purged-CV IC of SUE-drift + insider-net-buy on the **delisting-aware** panel (A1); known to be the lone FDR survivor — defend it net-of-cost. Basis: Bernard-Thomas PEAD, insider-net-buy literature.

**B5 — Variance-risk-premium chip** (`cone-realized-vs-implied-width-gap` + `skew-tail-leg-activate`, effort low)
Cross `cone_vol_ann` (realized HAR) against GEX `iv30`/expected_move per name; surface the VRP gap. Activate the already-wired CBOE SKEW macro leg through Phase-0 as a tail overlay. **Validation:** the IV>RV spread is among the most robust documented option premia (Carr-Wu, Bollerslev-Tauchen-Zhou); run the SKEW leg through the calendar-blocked IC battery before promoting. **Payoff:** orthogonal context/regime read; data already on-build.

### Tier C — Worthwhile but conditional / context-only

**C1 — Wire the dead legs + coverage telemetry** (`wire-sector-rs-tailwind`, `wire-quality-context-z-us`, `tailwind-axis-coverage-instrumentation`, effort low) — re-activate sector-RS tailwind (small declared overlay; Moskowitz-Grinblatt industry momentum) + the US quality composite (`factors.json` composite into `quality_context_z`); add a build-time per-leg null-rate SLO that fails when a high-weight leg fires on <X% of the universe (prevents recurrence of the slug-vs-id / top_n=16 / sector_rs dead-leg class).

**C2 — Calibration-driven signed-weight vector** (`signed-weight-pattern-to-stock-axes`, effort med) — port `commodity_conviction`'s "weight sign = measured IC sign" pattern to the equity axes using `ic_scorecard.json`, so an inverted leg (low_vol) auto-flips and adding a leg is safe-by-construction. Fixes the `lowvol-quality-axis-wrong-sign` class permanently.

**C3 — Credit-spread + absorption de-risk overlays** (`credit-cycle-spread-risk-gate`, `absorption-ratio-derisk-overlay`, effort low-med) — gate cyclical/high-beta chases on widening+elevated HY OAS (Gilchrist-Zakrajsek EBP); use top-quintile cross-asset absorption (Kritzman-Page) as a portfolio fragility de-risk. Both are timing/sizing levers; context-only is fine.

**C4 — Regime-quad sector tilt** (`regime-quad-sector-tilt`, effort med) — promote the PIT growth/inflation quad into a sector-eligibility tilt using the per-name macro-sensitivity chip already computed. Mainstream framework (Hedgeye/Bridgewater quadrant); validate the quad→sector forward spread on the PIT panel before scoring.

**C5 — PIT cone test + causal kernel** (`pit-cone-test-coverage`, `causal-conditional-kernel`, effort low-med) — extend the truncate-recompute test to the full `anticipate()` output (cone ret_q/dd/p_up), and add an expanding-edges mode to `forward_dist` for any historical replay. Closes the documented residual from the refuted cone claim.

### Demoted / drop (no plausible net-of-cost edge on this data)
- **`breadth-internals-thrust-confirm`** — keep ONLY the A/D-vs-price divergence leg; the McClellan/thrust internals are coincident-by-construction (module admits it) → no forward edge, demote to context.
- **`btc-liquidity-riskappetite-proxy`**, **`prediction-markets-event-risk-gate`** — context-only confirmers at best; crypto/Polymarket noise makes standalone net-of-cost alpha implausible. Fold into B1 as a low-weight ensemble input, do not build a dedicated scored leg.
- **`cross-asset-leadlag-transmission-timing`** (effort high) — keep as a *cautious next-session prior* for ex-US books only where the link is FDR+stability-gated; do not invest in it as primary alpha. The honest default is "contemporaneous."
- **`forex-dollar-smile-riskoff-gate`** / **`commodity-driver-axis-sector-conditioner`** — subsume into the B1 ensemble rather than shipping parallel scored gates (avoids correlated double-counting, the exact BUG-2 failure mode at the macro level).

---

## PART 3 — PHASED BUILD PLAN

**Phase 0 — Bug fixes (correctness first, no new infra)**
- BUG-1 topping veto in `ladder_state` (gated on the measured penalty bucket from `calibrate-topping-cap-bucket`); BUG-2 entry-axis de-dup; BUG-3 OOS-orient `ensemble_promotion` + relabel `ensemble_ic`; BUG `cn-sel-kind-mislabel` reorder; `entry-quality-ignores-curl-dn`; wire dead legs (`sector-rs`, US `quality_context_z`, insider panel path); low_vol sign fix; LOW disclosure/units batch (vex/cex scale, flow-pctile window, score-skin band note, gate-cone doc).

**Phase 1 — Core infra**
- A1 PIT survivorship-aware universe (regen 3 price panels + wire into `recalibrate.py` + `calibrate_bottom_confidence.py`); delisting-return stitch (`delisting-return-stitch`); A2 vol-managed sizing scalar; A3 purged-CV + OOS-orientation helper + overlap-aware HAC SE; calibration-universe metadata stamp + UI caveat (BUG-4/5 disclosure path).

**Phase 2 — Per-idea backtests (on PIT panel, purged-CV, net-of-cost)**
- B2 net-liquidity selection gate; B4 PEAD/SUE + insider on delisting-aware panel; B3 regime-conditional weights + meta-label classifier; B1 ensemble risk-on/off scalar; B5 VRP + SKEW Phase-0. Each emits an honest OOF IC/Sharpe + DSR with `n_trials` = true family size; drop any that fail net-of-cost.

**Phase 3 — Combine + integrate**
- C2 signed-weight vector (makes the composite robust-by-construction); fold surviving B-ideas into the conviction axes with declared weights; C1 coverage telemetry SLO in the build; C3/C4/C5 context overlays; combine vol-managed sizing (A2) with the surviving gates into book-level eligibility.

**Phase 4 — Regions + PR**
- Propagate the validated axes + dead-leg wiring + signed-weights to CA/Intl/CN/HK builders; add the per-leg coverage test asserting >0 names carry each high-weight leg per market; PR per region with the honest backtest artifacts + survivorship/PIT provenance attached.

---

*Every bug above carries a file:line citation verified by direct read; the five core bugs and the ensemble-orientation leak were re-confirmed against the live code in this checkout.*
