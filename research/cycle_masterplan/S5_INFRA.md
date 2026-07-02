# S5 Infrastructure Inventory — Cycle Masterplan Feasibility Scout
_Verified against /tmp/macro-cycle-fable-main/ (canonical main checkout). All citations are file:line._

---

## 1. Portable primitives from `engine/china_sector_cycles_grader.py`

### What exists (directly portable into `engine/grading_stats.py`)

**`_wilson(k, n, z=1.96)`**
- Canonical definition: `engine/china_sector_pathway.py:56-63`
- The grader delegates to it via import: `engine/china_sector_cycles_grader.py:137`
- Signature: `(k: int, n: int) -> tuple[float, float] | None` (grader wrapper returns None on exception; pathway returns tuple always)
- Implementation: Wilson score interval, pure Python/math. Zero deps. Directly portable.

**`_boot_gap_ci(dates, vals, mask)`**
- Location: `engine/china_sector_cycles_grader.py:143-161`
- Date-blocked bootstrap 95% CI on `(conditional_mean − base_mean)`. Resamples whole stamp DATES (not rows) to respect cross-sectional correlation. `BOOT_DRAWS=800`, `BOOT_SEED=7`.
- Deps: numpy only. Directly portable.

**`MIN_EARN_N = 40`**
- `engine/china_sector_cycles_grader.py:62`
- Mirrors `engine/index_leadership_track._MIN_PROVEN_N`. Pre-registered gate: no effect size earns while n < 40.

**Bar-i+1 convention guard**
- `engine/china_sector_cycles_grader.py:34-36, 110-126, 211-217`
- `_entry_pos()` uses `searchsorted(side='right')` so the stamp bar itself can never be the entry bar.
- `grade()` raises `ValueError` if called with any other `convention` string — deliberate loud failure for tainted callers.
- `_fwd()`: `engine/china_sector_cycles_grader.py:116-130` — computes `{entry, exit, ret, maxdd}` for a trading-bar window anchored at bar i+1.

**Verdict logic**
- `_dd_verdict()` (line 164): "accruing" / "earning" / "falsified" / "inconclusive" based on n vs MIN_EARN_N and CI relative to zero.
- `_rate_verdict()` (line 176): same states, but NEVER emits "earning" by doctrine.

**All of the above are pure numpy/pandas, no scipy/sklearn.** They can be extracted into `engine/grading_stats.py` and re-imported by both the China grader and any new US/sector-cycle grader.

---

## 2. Precision / Recall / Brier machinery

### `engine/hysteresis.py`
- `veto_precision_recall(raw, *, confirm, cancel, run)` — line 89
  - Signature: `(raw: pd.Series, *, confirm: int = DEFAULT_CONFIRM, cancel: int, run: int) -> dict`
  - Returns: `{"single": {precision, recall, flicker_rate}, "hysteretic": {precision, recall, flicker_rate}}`
  - Treats a SUSTAINED topped run (length ≥ `run`) as ground-truth positive. Pure pandas/numpy.
  - **Portable for turn precision/recall** with any binary signal.
- `flip_rate(stream)` line 70, `flicker_rate(stream)` line 79 — both pure pandas. Portable.

### `engine/market_state_tune.py`
- `state_accuracy(calib, *, onsets, dd, H, alert_from)` — line 152
  - Signature: `(calib: dict, *, onsets=None, dd: float = 0.05, H: int = 21, alert_from: str) -> dict`
  - Returns `{precision, recall, f1, fire_rate}` for the ALERT state vs forward SPY drawdown ≥ dd within H bd.
  - Internally calls `detect_events(spy, fwd, depth, min_gap)` (line 27) to find drawdown onsets from SPY prices.
  - **Portable for turn precision/recall** with any binary risk call.
- `compare_calib(proposed, base)` — line 181: do-no-harm gate comparing two calibrations by F1 (full history + 2020+).
- `_backtest(rows, calib)` — line 90: internal vectorized precision/recall/F1/false-positive computation over graded history.

### `engine/validation.py` (shared calibrator primitives)
- `brier_reliability(p, y, n_bins=10)` — line 525
  - Returns `{brier, base_brier, skill_score, reliability: [{bin, n, pred, obs}], n, base_rate}`
  - **Directly portable for Brier + reliability curves.** Pure numpy, min N=30.
- `platt_fit(p, y, iters=400, lr=0.2, l2=1.0)` — line 551
  - Platt logistic recalibration `y ~ sigmoid(a·logit(p)+b)` via GD with L2 shrinkage. Returns `{a, b, brier_recal}`. Pure numpy, min N=40.
- `expected_calibration_error(p, y, n_bins=10)` — line 571: returns `{ece, mce, n}`. Pure numpy.
- `isotonic_calibration(p, y)` — line 597: Pool-Adjacent-Violators isotonic recalibration. Returns `{x, y_cal, n, ece_before, ece_after}`. Pure numpy (no sklearn).
- `apply_calibration(model, p_new)` — line 625: step-function lookup into isotonic model.
- `block_bootstrap_ci(returns, block, B, seed)` — line 453: block-bootstrap CI on Sharpe/Calmar. Portable.
- `deflated_sharpe(sr_daily, skew, kurt, T, n_trials, ...)` — line 254: DSR with multiple-testing correction.

### `engine/risk_radar_backtest.py`
- `detect_events(spy, fwd, depth, min_gap)` — line 27: SPY drawdown onset detection.
- `lift(pct, onsets, *, thr, fwd_bd)` — line 63: lift of a score distribution at onsets.
- `perm_p(pct, onsets, ...)` — line 86: permutation p-value. Pure numpy.
- No explicit "cone coverage rate" function anywhere in this file or elsewhere. **Cone coverage rate (empirical % of realized paths inside stated quantile bands) is ABSENT as a standalone function.** `forward_dist.conditional_distribution()` returns quantile bands but does not measure out-of-sample coverage rate.

### Coverage gap
No function computing empirical cone coverage rate (i.e., what fraction of realized outcomes fell inside the p5-p95 band across held-out windows) exists anywhere in the repo. This is an infra gap that would need to be built in `grading_stats.py`.

---

## 3. Hazard / Survival / Logistic / ML code

### What exists

**`engine/regime_hmm.py`**
- `fit_regime_hmm(scores, min_per_quad, min_covar)` — line 79
- Fits 4-state Gaussian HMM using `hmmlearn>=0.3` (declared in requirements).
- Returns `{"hazard": float, "expected_dwell_months": float, "p_quad": dict, "transition_matrix": list, ...}`
- `hazard = round(1.0 - p_stay, 4)` — P(leave current quad next month). This is a TRANSITION hazard, not a survival model.
- `hmmlearn` is a declared dependency (requirements.txt line with `hmmlearn>=0.3`).

**`engine/meta_label.py`** (lines from grep)
- Uses `sklearn.ensemble.HistGradientBoostingClassifier` (GBT meta-label).
- Declared dep: `scikit-learn>=1.4` in requirements.txt. Marked "default-off, exercised by scripts/meta_label_btc.py".
- Signature: `DEGRADE: returns an empty Series if sklearn is unavailable.`

**`engine/stock_score.py`**
- `_logistic_0_100(z, k=0.62)` — hand-coded logistic squash function, pure numpy. NOT sklearn.

**`scripts/calibrate_baskets.py`**
- `_fit_logistic_signed(X, y, w0, l2, iters, lr)` — sign-constrained logistic fit, L2-shrunk, pure numpy (no sklearn).

**`engine/validation.py`**
- `platt_fit()` — gradient-descent logistic recalibration, pure numpy.
- `isotonic_calibration()` — PAV algorithm, pure numpy (no sklearn).

### True survival/hazard models
**ABSENT.** No Cox PH, no Kaplan-Meier, no lifelines/statsmodels.survival anywhere in engine/ or scripts/. The word "hazard" in the codebase refers exclusively to `1 - p_stay` from the HMM transition matrix (regime_hmm.py).

### Available ML deps (from requirements.txt)
- `scikit-learn>=1.4` — available (for meta_label only; marked default-off)
- `hmmlearn>=0.3` — available (for regime_hmm nightly calibration)
- `scipy` — implied as hmmlearn dependency per requirements.txt comment ("thin pure-Python on scipy/scikit-learn, already deps")
- `statsmodels` — **NOT listed in requirements.txt.** Not a declared dep.
- pandas, numpy, pyarrow — core, always present.

---

## 4. `engine/event_calendar.py` + Alerts Infra — Falsifier-Tripwire Plug-in Points

### Event calendar API
- `us_macro_events(today, horizon_days=14)` — line 337: returns list of upcoming macro events (NFP, CPI, FOMC, auctions, etc.) with `{type, date, label, tag}`.
- `high_impact_strip(today, horizon_days=14)` — line 428: subset of highest-impact events.
- `imminent_line(today, horizon_days=14)` — line 441: formatted string of imminent events.
- FRED release dates fetched live via `_fred_release_dates(release_id, today, end)` (line 166) using FRED API.
- No direct tripwire hook inside event_calendar.py itself — it is a pure data producer.

### Alert infrastructure (`engine/alerts.py`)
- Alert model: `Alert` namedtuple with `{rule: str, severity: str, message: str, message_zh: str}`.
- Alert rules are functions: `(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | Alert | list[Alert] | None`.
  - Existing rules: `transition_state_change`, `axis_confidence_floor`, `sector_rs_percentile_cross`, `hy_oas_widening`, `sahm_trigger`, `ebp_widening`, `drawdown_risk_high`, `conditions_recession_state_change`, `nfci_tightening`, `circuit_breaker_open`, `gex_flip_cross`, `net_liquidity_roc_flip`.
- **`log_and_dedup(alerts, asof)`** (line 499): appends to `data/alerts/alerts_log.parquet` keyed `(date, rule, message)`. Idempotent — re-running the same day cannot double-fire.
- **Dispatch**: `scripts/notify.py` — `send_telegram(msg)` (line 113) via `TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID`; `send_discord(msg)` (line 129) via `DISCORD_WEBHOOK_URL`. Both read `data/regime/latest.json` + `run_status.json`; never recompute engine state.
- `engine/experiments_registry.py:182-183`: calls `notify.send_telegram(msg)` and `notify.send_discord(msg)` directly for experiment state-change alerts.

**Plug-in pattern for a falsifier-tripwire monitor:**
1. Write a new rule function `cycle_turn_falsified(hist, f) -> Alert | None` that reads the grader scorecard output (when a verdict flips from "accruing" → "falsified").
2. Register it in the rules list in the alerts runner script.
3. Pass output to `log_and_dedup()` → `scripts/notify.send_telegram/send_discord()`.
No new infra needed — the pattern is already established and tested.

---

## 5. FRED Collector — What Is Collected, and Adding New Series

### Currently collected (150 parquet files in `data/fred/`)
Full series list parsed from `config.yml` fred.series groups:
- **rates**: DGS2, DGS10, T10Y2Y, DFII10, T10YIE
- **credit**: BAMLH0A0HYM2 (HY OAS ✓), BAMLC0A0CM (IG OAS ✓), BAMLEMCBPIOAS, BAMLHYH0A0HYM2TRIV
- **risk**: VIXCLS, OVXCLS
- **housing**: MORTGAGE30US only
- **liquidity**: WALCL, RRPONTSYD, M2SL, ECBASSETSW, JPNASSETS
- **labor**: ICSA, IC4WSA, CCSA, IHLIDXUS, IHLIDXNEWUS
- **conditions**: NFCI, ANFCI, NFCIRISK, NFCICREDIT, NFCILEVERAGE
- **recession**: SAHMREALTIME, RECPROUSM156N, THREEFYTP10
- **nowcast**: GDPNOW, WEI
- **cycle_leading**: AWHMAN, ICSA, PERMIT, NEWORDER
- **cycle_coincident**: W875RX1, CMRMTSPL
- **cycle_lagging**: UEMPMEAN, ISRATIO, BUSLOANS, MPRIME, CUSR0000SAS
- **bonds_extra**: BAMLH0A3HYC (CCC OAS ✓), IORB, SOFR99, USRECD
- **inflation**: CPIAUCSL, CPILFESL, PCEPI, PCEPILFE, PPIFIS, PPIFES, ECIALLCIV, ECIWAG, T5YIE, DFII5
- **bottleneck**: TCU, MCUMFN, CAPUTLG-family, ISRATIO, AMTMUO, AMTMVS, DGORDER, NEWORDER, PCU-family
- **fx**: DEXUSEU/DEXJPUS/DEXUSUK/DEXUSAL/DEXCAUS/DEXSZUS/DEXMXUS/DEXBZUS/DEXCHUS + BIS REER family
- Full list: 150 files confirmed.

### HY-OAS status
- `BAMLH0A0HYM2` (HY OAS): **ALREADY COLLECTED.** `data/fred/BAMLH0A0HYM2.parquet` exists. FRED serves only rolling 3y window since Apr 2026; collector is append-only so pre-window history is kept permanently (`config.yml:89`, `collectors/fred.py:9-12`).
- `BAMLH0A3HYC` (CCC OAS): **ALREADY COLLECTED.** `data/fred/BAMLH0A3HYC.parquet` exists.

### Case-Shiller status
- **ABSENT.** No `CSUSHPISA` or any Case-Shiller series in `data/fred/` or `config.yml` fred.series groups. Housing group has only `MORTGAGE30US`. Adding it is trivial: add `CSUSHPISA: cs_hpi` (or similar) under `fred.series.housing` in `config.yml` — the collector loop in `collectors/fred.py:83` iterates all series from that config dict automatically.

### ISM / Manufacturing PMI status
- **ABSENT.** No `MANEMP`, `NAPM`, ISM series ID in `data/fred/` or config. The `cycle_leading` group has `NEWORDER` (durable goods orders) and `AWHMAN` (mfg hours) as manufacturing proxies, but not the ISM PMI composite. Adding `ISM/MANEMP` follows the same one-line config pattern.

### Adding new series: effort = trivial
Adding any new FRED series requires only one config.yml entry: `new_series_id: column_name` under the appropriate `fred.series.<group>`. The collector automatically picks it up on next run. No code changes needed.

---

## Summary Table

| Area | Status |
|---|---|
| `_wilson` | PRESENT: `engine/china_sector_pathway.py:56`. Delegates from grader. Portable. |
| `_boot_gap_ci` | PRESENT: `engine/china_sector_cycles_grader.py:143`. Portable. |
| `MIN_EARN_N=40` | PRESENT: `engine/china_sector_cycles_grader.py:62`. Pre-registered, not tuneable. |
| Bar-i+1 guard | PRESENT: `_entry_pos()` + `grade()` ValueError. Portable. |
| Turn precision/recall | PRESENT: `hysteresis.veto_precision_recall` + `market_state_tune.state_accuracy`. Both pure pandas/numpy. |
| Brier + reliability curves | PRESENT: `validation.brier_reliability`. Pure numpy. |
| Calibration (Platt/isotonic/ECE) | PRESENT: `validation.platt_fit`, `validation.isotonic_calibration`, `validation.expected_calibration_error`. Pure numpy, no sklearn. |
| Cone coverage rate | ABSENT. No function computing empirical out-of-sample quantile coverage rate. Gap to build. |
| Hazard/survival model | ABSENT (as dedicated survival model). `regime_hmm.hazard = 1 - p_stay` is a transition probability, not a survival curve. |
| Logistic regression | PRESENT (hand-coded pure numpy): `stock_score._logistic_0_100`, `calibrate_baskets._fit_logistic_signed`, `validation.platt_fit`. sklearn logistic ABSENT from deps except via scikit-learn>=1.4 (meta_label only, default-off). |
| sklearn | PRESENT in requirements (`scikit-learn>=1.4`) but marked default-off (meta_label only). |
| scipy | IMPLIED dep (hmmlearn needs it), not explicitly listed. Likely importable. |
| statsmodels | ABSENT from requirements.txt. Not a declared dep. |
| hmmlearn | PRESENT (`hmmlearn>=0.3`). Used for nightly calibration only, not render path. |
| HY-OAS | ALREADY COLLECTED (`BAMLH0A0HYM2`, `BAMLH0A3HYC`). |
| Case-Shiller | ABSENT. Trivial to add: one config.yml line. |
| ISM PMI | ABSENT. Trivial to add: one config.yml line. |
| Alert dispatch | PRESENT: `alerts.log_and_dedup()` → `scripts/notify.send_telegram/send_discord()`. Falsifier tripwire = new rule function + registration. |
| Event calendar hook | Event calendar is a data producer only. Alerts runner is the plug-in surface. |
