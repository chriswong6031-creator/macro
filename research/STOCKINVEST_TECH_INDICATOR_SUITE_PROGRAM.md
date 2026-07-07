# StockInvest Technical Indicator Suite — Build Program

---

## Directive Update 2026-07-07

**Operator directive (supersedes sequencing gates for infrastructure work):**

BUILD THE FULL MACHINE FIRST. Engines for every StockInvest indicator + catalog + score/confluence + lab must ship before verdict work resumes. Infrastructure gates are open: `ma_crosses`, `pivots`, `rsi_signals`, `formations`, `trend_signals`, `fundamental_screens`, `tech_stars` modules, plus `engine/tech_catalog.py` (AI-friendly signal registry) and `engine/tech_score.py` (−10..+10 composite + confluence runner), plus `lab.characterize` expansion to cover the full catalog. Verdicts, gauntlet runs, and NW promotion are DEFERRED — results do not gate infrastructure. Build first, characterize second, adjudicate third.

---

**Ratified:** 2026-07-07
**Status:** ACTIVE — Wave 1 build-ready. Wave 2 gated on Wave 1 merge. Wave 3 gated on Wave 1 backtest passing its pre-declared PASS gate plus a Fable/Opus adjudication checkpoint.
**Context:** Three-wave program to (a) consolidate the repo's drifting RSI/StochRSI copies into a canonical technical-indicator lab façade, (b) reconstruct and backtest StockInvest's Golden Star / Death Star signals against the pre-registered bottom-finding premise, (c) surface results in a display-only Research screener page, and (d) optionally feed a gauntleted signal into Neural Web as context-tier context only. The money path is fully gated: display-only until the gauntlet passes, then DecisionPacket shadow accrual, then Fable/Opus adjudication.
**Scope fence:** this program covers `engine/lab.py`, a new Research screener page, and the NW synapse registration pathway. It does NOT touch `engine/masterminds.py` (off-limits, Oracle Constitution §III), does not replace `us_standouts.json`, and does not originate buy signals.
**Method:** Codex docs cited by the user are confirmed absent from every branch, stash, and worktree (exhaustive content grep). Reverse-engineering is based on primary-source verbatim quotes from StockInvest's own published pages (primary authority for construction) cross-checked against an independent UI/taxonomy pass (authority for score bands, named lists, universe). Every parameter without a verbatim quote behind it is labeled ASSUMED or UNKNOWN; no gate depends on an unlabeled assumption.

---

## §0. Census corrections (printed per house law)

The pre-write repo census (2026-07-07) found:

1. **CONFIRMED DUPLICATE DRIFT:** `engine/canon.py` is the canonical source for RSI (`rsi()`, line 341) and StochRSI (`stoch_rsi_kd()`, line 412). The following files contain independent reimplementations rather than imports: `engine/coiled.py` (`_stoch_rsi_kd`, with docstring "exact copy of confluence_tiers._stoch_rsi_kd"), `engine/postcross.py` (`_stoch_rsi_kd`), `engine/signal_quality.py` (`_stoch_rsi_kd`), `engine/confluence_tiers.py` (`_stoch_rsi_kd`), `engine/setup_tier.py` (imports from `confluence_tiers`, not `canon`), `engine/donor.py` (`_rsi`, `_rsi_macd`), `engine/basket_score.py` (`_rsi`), `engine/commodity_signals.py` (`_rsi`), `engine/strategy_signals.py` (`wilder_rsi`), `engine/cycles.py` (`stoch_rsi`), `engine/advanced_indicators.py` (`stoch_rsi_cross_up_series`). Total RSI copies: ~15 (canonical + ~14 drifting). Total StochRSI copies: ~7 named defs + 4 that import from non-canon siblings (effectively ~11 live implementations of the same function). The lab façade (Wave 1) is the consolidation surface; it does NOT migrate callers in this program (migration is a separate post-program refactor lane, flagged in §10).

2. **CONFIRMED: `Golden Oracle` (`engine/canon.py:421 confluence_signals`) is display-only, not in the money path.** It feeds `engine/master_brain.py` as a display leaf only. No behavior change in this program.

3. **CONFIRMED: `us_standouts.json` pipeline** (`engine/top_picks.py` → `discovery.html`, `engine/setups.py`/`build_stock_library.py` → `us_standouts.json`) is genuinely simplistic: 60% residual momentum, fails its own DSR haircut, no regime gate on the rank, richer engine display-only with `gate_go=False`. This program augments this ecosystem; it does not replace it.

4. **CONFIRMED: `congress_trades.html.j2`** exists in `templates/` and is the nearest layout sibling for the Wave 2 screener page.

5. **CONFIRMED: Codex source documents for StockInvest construction** cited in the user prompt do NOT exist in any branch, stash, or worktree. Input-2 (verbatim primary-source reverse-engineering) governs construction throughout this program; there is no Codex construction claim to adjudicate against it.

---

## §0.5 Honest priors (printed per house law)

The adjudicating session flagged these priors before drafting, per epistemics law:

1. **HYPOTHESIS, NOT FIND:** "Golden Star finds durable bottoms well" is the *premise under test*, not a pre-existing finding. StockInvest's own published language ("our backtesting shows it falls deep" for Death Star, "higher short-term probability for gains" for Golden Star + high score) is classified as **ASSERTED-marketing**: no sample size, no window, no universe, no metric is given. The backtest in this program is the first honest test of the premise.

2. **LAGGING SIGNAL PRIOR:** Golden Star is an MA-cross family. MA crosses are trend-confirmation signals by construction — they fire *after* the move has started. A bottom-finding role is plausible if the three-entity intersection (MA + MA + price line simultaneously) fires closer to the actual turn than a plain cross, but this is a hypothesis, not established. The backtest is the arbiter.

3. **CODEX PROVENANCE NULL:** both cited Codex documents are confirmed absent. No construction claim in this program derives from Codex; every parameter is anchored to a primary-source quote or labeled ASSUMED/UNKNOWN.

---

## §1. Program-level rulings (adjudicated 2026-07-07)

- **RUL-1 (three-wave, sequenced):** Wave 2 does not begin until Wave 1 is merged and the `characterize()` white-space map is committed. Wave 3 does not begin until Wave 1's backtest clears its pre-declared PASS gate (§6) AND a Fable/Opus checkpoint adjudication occurs. No parallel wave dispatch.
- **RUL-2 (display-only until gauntleted):** every surface in this program is display-only. The word "validated" must not appear in any user-facing string (CI-enforced by `scripts/check_validated_claims.py`). Golden Star fires are research artifacts, not buy recommendations.
- **RUL-3 (no fresh-buy surface — KILLED):** the pattern of routing a freshly-fired Golden Star to an act-now surface (notifications, live alerts, Discord sentinel) is forbidden. It launders a lagging trend signal as a time-critical buy trigger without a gauntlet. Killed here; do not re-propose.
- **RUL-4 (no LLM-originated signals):** LLMs may only de-escalate calibrated keys. No LLM originates a signal, score, or escalation in this program. The Score reconstruction (§4.7) is a deterministic formula from StockInvest's published band breakpoints; it is NOT an LLM inference.
- **RUL-5 (no positioning fusion):** Golden Star + Neural Web routing (Wave 3) delivers context-tier metadata only — it does NOT feed into allocation() or sizing in any form. The positioning-fusion prohibition applies.
- **RUL-6 (no human-override gate in allocation()):** the midterm-blackout gate pattern from the BTC vector registry is explicitly forbidden here. No gate in this program wires into the Mastermind allocation path.
- **RUL-7 (no fused shield/meta-router):** the Golden Score reconstruction does not become an input to a fused portfolio-level meta-router. It is a display annotation.
- **RUL-8 (no free-horizon verdicts):** the backtest verdict is rendered ONLY at the pre-declared ruler: 7/35 Golden Star, price-line gate ON, 21d time-exit. Other configs are sensitivities that feed the multiple-testing budget but do not generate independent verdicts.
- **RUL-9 (ticker-cluster / time-confound guard is LETHAL):** all CIs use block bootstrap over calendar blocks; effective N is reported via `bootstrap_effective_t`. Raw per-fire N is display-only; verdict N = time-blocks. Era split at 2010 mandatory.
- **RUL-10 (no staleness-alpha):** any finding that fires only because Golden Star clusters with broad market rallies is flagged as a beta artifact. The matched-placebo null (B4 in §6) is the control.
- **RUL-11 (no `engine/masterminds.py` edits):** off-limits per Oracle Constitution §III. Wave 3 context injection routes exclusively through synapse.yml + spine-adapter contract, same as other context-tier artifacts.
- **RUL-12 (bilingual EN/ZH):** all user-facing UI in Wave 2 ships bilingual. No translated text in `title=` attributes (CI-guarded). Wave 3 synapse chip follows the same bilingual chip law.
- **RUL-13 (nightly-only ledger writes):** the nightly pipeline is the sole advancer of any forward ledger. Intraday lanes (manual lab runs, off-render backtest) discard `data/` writes or write to explicit gitignored paths.
- **RUL-14 (pre-registered gates before results):** the PREREG (§6) is merged before any backtest run. If the backtest is run before the prereg is merged, the results are invalidated and must be re-run.
- **RUL-15 (`us_standouts.json` untouched):** this program does not edit the standout pipeline. Wave 2 lists are derived from separate lab.py outputs and written to a new artifact (§5).

---

## §2. Reverse-engineered signal specifications (authority: primary-source verbatim quotes)

All specifications carry confidence labels: **WELL-SUPPORTED** (verbatim-anchored), **PLAUSIBLE** (construction well-supported; exact thresholds speculative), **SPECULATIVE** (inferred; no verbatim definition). Parameters labeled **ASSUMED** have no quote behind them; parameters labeled **UNKNOWN** are unresolved and their calibration is a Wave 1 task (see §3.5).

### 2.1 Golden Star (base signal)
**Confidence: PLAUSIBLE**

Three-entity intersection: short MA, long MA, and price line must "meet in a special combination" simultaneously. The price-line condition is the documented delta over a plain Golden Cross (verbatim: "cross the price line at the same time").

- Dynamic short MA formula (verbatim): `short_n = round(((N_days / 5) / 2) + 1)` where `N_days` = chart window length in trading days.
- Long MA: standard 100 and 200 day (verbatim). Timeframe assignment ASSUMED: 100 for medium chart windows, 200 for long. Named-list mapping below takes priority over the dynamic formula for the three documented families.
- Two filter dimensions: volatility/liquidity and trend (verbatim). Low-volume names give more false signals (reliability down-weight, NOT a hard exclusion — verbatim: "give more false signals" does not say "are removed").
- Confirmation: **+2 trading days** (verbatim). Entry is the open of confirm_day+1 (PIT: avoids look-ahead on the confirm bar itself).
- Rarity: ~5.3% of ~30k tickers/day, fewer than 70/day.
- MA type: **SMA** (ASSUMED — StockInvest's cited standard periods are classic SMA conventions; "EMA" never appears in source).

**Unknown/Assumed parameters requiring calibration in Wave 1 (§3.5):**
- `P`: price-line proximity band ("at the same time"). Back-propagated from Death Star's verbatim "1–3% range" → ASSUMED ~1–3% price proximity to the crossing MAs at the cross bar.
- `L`: liquidity floor for the reliability filter. UNKNOWN; calibrate against StockInvest ground-truth.
- `k`: trend lookback for the trend filter. UNKNOWN; calibrate.

**Pseudocode:**
```python
# T0 = cross bar; P, L, k = UNKNOWN (calibrate in Wave 1)
ma_s = SMA(short_n); ma_l = SMA(long_n)
golden_cross_now  = (ma_s[t] > ma_l[t]) and (ma_s[t-1] <= ma_l[t-1])
price_coincident  = abs(price[t] - ma_s[t]) / price[t] <= P          # ASSUMED ~0.03
liquidity_ok      = dollar_adv(price, volume, 21) >= L                # UNKNOWN
trend_ok          = SMA(long_n) is rising over trailing k days        # UNKNOWN
golden_star[t+2]  = golden_cross_now and price_coincident and liquidity_ok and trend_ok
```

### 2.2 Golden Star Short-Term
**Confidence: PLAUSIBLE**

Named-list families confirmed by independent UI/taxonomy pass: **7/35** and **21/100**. RSI-14 is context/scoring input (verbatim: "RSI 14 is used for the short term") — ASSUMED not a hard gate.

```python
# Short-term family: (short_n, long_n) in {(7, 35), (21, 100)}
rsi_ctx = RSI(14)   # context annotation, not a filter gate
golden_star_ST[t+2] = golden_star(short_n, long_n)  # same geometry as §2.1
```

**Note on internal conflict resolution:** the dynamic-formula interpretation for "Short-Term" and the named-list mapping (7/35, 21/100) are both present in source. The named-list mapping is preferred because it is independently confirmed by the platform's own list navigation; the dynamic formula is best read as how a chart widget picks a short MA for any given zoom level.

### 2.3 Golden Star Long-Term
**Confidence: PLAUSIBLE (best-supported variant)**

Named-list family: **50/200** (standard Golden Cross). RSI-21 is context (verbatim: "21 for the medium term"). Both sources agree on 50/200; it is the most evidenced parameter set in the entire specification.

```python
# Long-term family: (50, 200)
rsi_ctx = RSI(21)
golden_star_LT[t+2] = golden_star(50, 200)
```

**Note:** there is a documented tension between "50/200" (Golden-Cross convention) and "100 and 200" (verbatim long-term MA pair). The named Long-Term list defaults to 50/200; the 100/200 pair may be the chart-overlay display pair. Both are flagged in the lab registry.

### 2.4 New Golden Star
**Confidence: SPECULATIVE (inferred from convergent independent sources)**

No verbatim definition exists. Two independent passes converge on: **Golden Star with age ≤ 1–2 trading days after confirmation** (i.e., the subset that just fired). This is the defensible inference. It does NOT produce a mechanically distinct signal — treat as `golden_star` with an `age_since_confirm <= 1` flag. Premium-gated on the platform; treat as display annotation only.

```python
new_golden_star[t] = golden_star_confirmed[t] and (t - signal_onset_day <= 1)
```

### 2.5 Death Star Short-Term
**Confidence: PLAUSIBLE (stronger primary documentation than Golden Star for the core mechanic)**

Death Star has the strongest verbatim support for the simultaneous intersection: "moving averages cross each other in a certain pattern that are on the price line" and "the averages should cross the price line **at the same time**." This is back-propagated to the Golden Star geometry as confirming evidence. Price-line band verbatim: "within 1–3%."

```python
# Short-term family: (7, 35) or (21, 100)
death_cross_now  = (ma_s[t] < ma_l[t]) and (ma_s[t-1] >= ma_l[t-1])
price_coincident = abs(price[t] - ma_s[t]) / price[t] <= 0.03       # verbatim "1–3%"
death_star_ST[t+2] = death_cross_now and price_coincident            # +2d confirm
rsi_ctx = RSI(14)
```

**Warning re published backtest claims:** "our backtesting shows that a stock with these signals will most certainly fall for a long period and deep down" (verbatim, Death Star). Classified as ASSERTED-marketing. No sample, window, universe, or metric provided. Treat as hypothesis.

### 2.6 Death Star Long-Term
**Confidence: PLAUSIBLE**

```python
# Long-term family: (50, 200)
death_star_LT[t+2] = death_cross(50, 200) and price_coincident (<=~3%), +2d confirm
rsi_ctx = RSI(21)
```

### 2.7 Score & Top Buy
**Confidence: WELL-SUPPORTED for scale and bands; PLAUSIBLE for input list; SPECULATIVE for weighting**

Score scale: **−10 to +10**. Bands (verbatim + UI confirmation):
- `[5.00, 10.00]` Strong Buy / 强烈买入
- `[1.00, 4.99]`  Buy / 买入
- `[−0.99, 0.99]` Hold / 持有
- `[−4.99, −1.00]` Sell / 卖出
- `[−10.00, −5.00]` Strong Sell / 强烈卖出

Score inputs (verbatim named): moving averages, trends, volumes, pivot points (algorithmic zigzag tops/bottoms, ±3% verify), RSI-14 and RSI-21; plus MACD, Bollinger, double tops/bottoms, select fundamentals (over/undervalued) from third-party sources. **Weighting function is unpublished and UNKNOWN — it cannot be reconstructed with confidence.** The lab will implement the score bands as a display annotation only; no weighting reconstruction attempt.

**Critical separation (both sources agree):** Score ≠ Forecast. The "66-session prediction credits" product is community-driven and "doesn't affect the technical analysis." Keep it out of the Score spec. Score and Golden Star are independent axes — Top Buy does not require a Golden Star.

**Top Buy list:** `score >= 1.00`, sorted descending, public top-100. Display-only in this program.

---

## §3. Wave 1 spec — `engine/lab.py` technical-indicator lab façade

### 3.1 Purpose

`engine/lab.py` is the canonical source-of-truth for every technical indicator used by this program. It does not replace `engine/canon.py` (which stays the repo-wide canonical indicator module); it is a focused façade that:
1. Imports from `engine/canon.py` for the two canonically-defined functions (`rsi`, `stoch_rsi_kd`).
2. Adds the Golden Star / Death Star / New Golden Star constructors with all ASSUMED/UNKNOWN parameters explicitly labeled and defaulted.
3. Provides a `characterize(close: pd.Series, adv: pd.Series, **kwargs) -> dict` function that runs the full white-space map on a single ticker and returns a structured dict of indicator readings, signal fires, and calibration flags.
4. Provides a `registry() -> list[dict]` function returning the canonical indicator registry (name, params, confidence, source-anchor, unknown-params, status).

This file is the single source of truth for Wave 2's screener compute and Wave 3's NW context artifact. Callers import from `engine.lab`; they do not re-implement.

### 3.2 Indicator registry (canonical, Wave 1)

The registry is the machine-readable source for the screener page and for the `characterize()` white-space map. Each entry carries:
- `id`: kebab-slug (e.g., `golden-star-st-7-35`)
- `name` / `name_zh`: bilingual display name
- `family`: `golden_star | death_star | score_band | rsi | stoch_rsi | sma`
- `params`: frozen dict of parameter values (known) and `{param: "UNKNOWN"}` markers for unknowns
- `confidence`: `well_supported | plausible | speculative`
- `source_anchor`: short verbatim quote snippet that grounds the parameter
- `unknown_params`: list of param names requiring calibration (§3.5)
- `status`: `display_only | display_only_pending_calibration | killed`

Minimum registry at Wave 1 merge:
| id | family | params | confidence | status |
|---|---|---|---|---|
| `golden-star-st-7-35` | golden_star | short=7, long=35, rsi=14, P=UNKNOWN, L=UNKNOWN, k=UNKNOWN | plausible | display_only_pending_calibration |
| `golden-star-st-21-100` | golden_star | short=21, long=100, rsi=14, P=UNKNOWN, L=UNKNOWN, k=UNKNOWN | plausible | display_only_pending_calibration |
| `golden-star-lt-50-200` | golden_star | short=50, long=200, rsi=21, P=UNKNOWN, L=UNKNOWN, k=UNKNOWN | plausible | display_only_pending_calibration |
| `new-golden-star` | golden_star | age_thresh=1, base=golden-star-st | speculative | display_only |
| `death-star-st-7-35` | death_star | short=7, long=35, P=0.03 (verbatim), rsi=14 | plausible | display_only |
| `death-star-st-21-100` | death_star | short=21, long=100, P=0.03, rsi=14 | plausible | display_only |
| `death-star-lt-50-200` | death_star | short=50, long=200, P=0.03, rsi=21 | plausible | display_only |
| `score-bands` | score_band | scale=[-10,10], bands=SB≥5/B≥1/Hold/S/SS≤-5, weighting=UNKNOWN | well_supported (bands) / speculative (weighting) | display_only |

### 3.3 `characterize()` white-space map

`characterize(close, adv, N_days=None, P=0.03, L=5e6, k=21) -> dict`

Returns for a single ticker as of the last bar:
- `signals`: dict of signal-id → `{fired: bool, fire_date: date|None, age_bars: int|None, confidence: str}`
- `rsi_14`: float, `rsi_21`: float
- `stoch_rsi`: `{k: float, d: float}` (from `engine.canon.stoch_rsi_kd`)
- `sma_state`: dict of SMA readings for {7, 21, 35, 50, 100, 200}
- `dollar_adv_21`: float
- `calibration_flags`: list of `{param: str, value: Any, source: "assumed"|"calibrated"|"unknown"}` — every ASSUMED/UNKNOWN parameter that was used is listed with its source tag
- `as_of`: date

The white-space map name refers to the practice of mapping what the lab can and cannot determine with confidence before running any backtest, making the unknowns visible rather than silently defaulted.

### 3.4 Golden Star / Death Star constructors

```python
def golden_star_fires(
    close: pd.Series,
    adv: pd.Series,
    short_n: int,
    long_n: int,
    P: float = 0.03,   # ASSUMED; label in output
    L: float = 5e6,    # ASSUMED; label in output
    k: int = 21,       # ASSUMED; label in output
    confirm_lag: int = 2,
) -> pd.Series:
    """
    Returns a boolean Series of Golden Star fires at the confirmation bar (close[t+2]).
    Entry for backtest: open of confirm_day+1 (PIT).
    All ASSUMED parameters are annotated in the returned metadata (carry-through to characterize()).
    """
```

All parameter labels are carry-through metadata, not silently dropped. Any consumer of this function sees which parameters are assumed.

### 3.5 Calibration task (Wave 1, ops lane, not on the render path)

The user has a StockInvest free trial. Before Wave 2 ships, the operator should:
1. Pull the current Golden Star list from StockInvest and record 20–30 tickers as ground-truth fires.
2. Run `characterize()` on those tickers with varying `P` (0.01, 0.02, 0.03, 0.05), `L` (1M, 5M, 10M), and `k` (10, 21, 42).
3. Select the `(P, L, k)` combination that maximizes the overlap with StockInvest ground-truth.
4. Record the calibrated values in `data/lab/calibration.json` (gitignored Mac-local, single writer: operator). Print achieved overlap; print it honestly even if imperfect.
5. Update the registry entries from `display_only_pending_calibration` to `display_only` (calibrated) in a follow-up PR.

This calibration is ops-lane work, not nightly compute. The Wave 2 screener ships with `pending_calibration` flags visible to the operator until Step 5 is done.

### 3.6 Tests

Synthetic-fixture-only (no dependence on Mac-local data):
- `test_lab_rsi_delegates_to_canon`: assert `lab.rsi()` returns the same series as `canon.rsi()` on a synthetic close.
- `test_lab_stoch_rsi_delegates_to_canon`: same for `stoch_rsi_kd`.
- `test_golden_star_confirm_lag`: fire on bar T, confirmed entry at T+2, verify no look-ahead.
- `test_golden_star_price_coincident_gate`: fire suppressed when price gap > P.
- `test_death_star_price_coincident_verbatim`: fire at exactly 2.9% proximity (pass) and 3.1% (fail), verifying the verbatim 1–3% band.
- `test_characterize_returns_calibration_flags`: all ASSUMED params appear in `calibration_flags` with `source="assumed"`.
- `test_registry_completeness`: all entries in the registry carry `confidence`, `unknown_params`, and `status` fields.
- `test_new_golden_star_age_flag`: age-threshold logic correct.

### 3.7 Storage

- `engine/lab.py` — git-committed (Wave 1 PR).
- `data/lab/calibration.json` — Mac-local, explicit `.gitignore` entry (RUL-13 path: ops-lane write, not nightly).
- `data/lab/characterize_cache/` — Mac-local, explicit `.gitignore` entry (off-render computation cache).
- `data/lab/backtest_results/` — Mac-local, explicit `.gitignore` entry. Summary JSON is git-committed (§6.9).

---

## §4. Wave 2 spec — display-only Research screener page

**Gated on:** Wave 1 merged + `characterize()` white-space map committed.

### 4.1 Page identity

- Template: `templates/tech_indicator_screener.html.j2`
- Site copy (paired, byte-matching): `site/tech_indicator_screener.html`
- Nearest layout sibling: `templates/congress_trades.html.j2`
- Navigation section: Research (same section as Congressional Trades, Foresight Desk)
- Route: `tech_indicator_screener.html`
- Page title: "Technical Indicator Lab | 技术指标实验室" (bilingual, no translated text in `title=` attributes — CI-guarded)

### 4.2 Data artifact

- `data/lab/indicator_screener.json` — git-committed, written by nightly job `scripts/build_indicator_screener.py`, single writer.
- Schema:
```json
{
  "as_of": "YYYY-MM-DD",
  "calibration_status": "pending | calibrated",
  "golden_star_fires": [
    {
      "ticker": "AAPL",
      "family": "7/35",
      "fire_date": "YYYY-MM-DD",
      "age_bars": 0,
      "confidence": "plausible",
      "rsi_14": 52.3,
      "rsi_21": 49.1,
      "dollar_adv_21_m": 8420.5,
      "is_new": true,
      "calibration_flags": ["P=assumed(0.03)", "L=assumed(5M)", "k=assumed(21)"]
    }
  ],
  "death_star_fires": [...],
  "backtest_verdict": {
    "status": "pending | pass | fail | null",
    "note": "Pre-registered backtest has not yet run",
    "pass_gate_ref": "research/STOCKINVEST_TECH_INDICATOR_SUITE_PROGRAM.md §6.6"
  },
  "score_bands": { "note": "Score weighting is unpublished. Band breakpoints are verbatim from source." }
}
```

### 4.3 Page design constraints

- **Display-only banner** at top: "Research display — signals are not recommendations. Parameters P, L, k are assumed pending calibration." EN/ZH.
- **Backtest verdict panel**: shows the verdict from `backtest_verdict.status`. If `pending`, displays "Backtest pending — see §6 of the program masterplan." If `fail` or `null`, displays the null honestly (per epistemics law: nulls are printed, not hidden).
- **Golden Star / Death Star tables**: show ticker, family, fire date, age, RSI context, ADV, calibration flags. Sortable by date. Paginated.
- **Calibration flags column**: visible. Operators see which parameters are assumed.
- **Augments, does not replace**: a footnote links to `us_standouts.json` (via `discovery.html`) and notes the relation ("existing standout system uses a different methodology; these lists are independent").
- **No act-now surface**: no notifications, no Discord integration, no "Top Buy" button (the fresh-buy routing is killed, RUL-3).
- `theme.js` included (new page law; provides window.MDXAuth + getSupabaseClient).
- Bilingual EN/ZH, paired template/site assets must byte-match (CI-guarded).

### 4.4 Nightly script

`scripts/build_indicator_screener.py`:
- Loads prices from the standard nightly price store (same source as `build_stock_library.py`).
- Calls `engine.lab.characterize()` for each ticker in the standard US universe (same universe filter as the standout system: `dollar_adv_21 >= $5M`).
- Collects fires, sorts by recency, writes `data/lab/indicator_screener.json`.
- Runtime budget: O(n_tickers × short_lookback); must fit within the nightly render budget. Initial implementation: vectorized SMA across the universe in one pass, then per-ticker fire detection. Target < 60 seconds.
- Does not write to `us_standouts.json` or any existing data artifact.

---

## §5. Pre-registered bottom-finding backtest

**MANDATORY GATE:** this section is the pre-registration that must be merged (as part of Wave 1 PR) before any backtest run. Running before merge invalidates results. The PASS gate in §6.6 is frozen here.

### 5.0 Harness reuse (verified against `engine/validation.py`)

The following repo-standard harness functions are used verbatim:
- `purged_folds(index, k, embargo)` + `cpcv_paths(n_obs, n_groups, k_test, embargo)` driving `backtest_core(close, alloc, cost_bps)` — walk-forward OOS.
- `deflated_sharpe(sr_daily, skew, kurt, T, ledger=...)` — multiple-testing haircut. **Must receive a real trials ledger; bare integer N is refused.**
- `block_bootstrap_ci(returns, block=21, B=5000)` — for strategy CI.
- `paired_delta_ci(a, b, block=21)` — for head-to-head vs benchmark.
- `prob_backtest_overfitting(perf, n_splits=16)` — PBO.
- `bootstrap_effective_t(returns, block=21)` — time-clustered effective N.

### 5.1 Premise under test

"Golden Star finds durable bottoms well."

Ruler (ratified oracle-reversion frame): reversion-capture — win-rate + MFE/MAE safety + regime split, **ABSOLUTE** returns (not SPY-excess), **21 trading day TIME-exit** (operator-ratified center of the 20–25d band). Display-only until the gauntlet passes; nulls are printed, not hidden.

### 5.2 Exact signal event

- Fire = Golden Star confirmed (§2.1/§2.2) at the **+2 trading-day** confirmation bar.
- **Entry:** open of confirm_day+1 (PIT: avoids look-ahead on the confirm bar). This is a conservatively PIT entry — the +2d lag is structural, not a fudge.
- **Primary verdict signal:** Golden Star Short-Term (7/35). This family is chosen because "finds bottoms" is a short-horizon reversion claim and 7/35 is the best-documented short family with the highest temporal resolution.

### 5.3 Ticker-cluster / time-confound guard

Golden Stars cluster in time (market-wide conditions drive many cross events simultaneously). This is the LETHAL confound documented in house memory (ticker-cluster bootstrap time confound). Mitigation:
- All CIs use block bootstrap over **calendar blocks** (block=21 trading days).
- Effective N is reported via `bootstrap_effective_t`; raw per-fire count is display-only.
- The matched-placebo null (§5.4) further neutralizes the regime-timing confound.
- Era split at 2010 (DT-R16 era-split law, MANDATORY).

### 5.4 Universe

- US common stocks, `dollar_adv(21) >= $5M` at signal date (drops the illiquid tail that StockInvest itself flags as false-signal-prone — verbatim: "low volume or illiquid stocks give more false signals").
- **Survivorship-safe:** point-in-time constituents; delisted names retained through delist event. Survivorship-biased cohorts must be flagged and reported as descriptive-only.
- Same universe fed to benchmark bottom-finders (§5.6) — apples-to-apples comparison.

### 5.5 Horizon and exit

- **Primary time-exit:** 21 trading days (center of ratified 20–25d band).
- **Pre-declared sensitivities** (counted in budget, §5.8; not independent verdicts): 20d and 25d exits.
- **Metrics per fire (absolute, not SPY-excess):**
  - Forward return to exit
  - MFE and MAE over the holding window
  - MFE/MAE ratio (safety)
  - Durable-bottom indicator = *close never revisits below (signal-day low − 1×ATR(14)) within the window* — if breached, counts as a failed bottom

### 5.6 Null hypothesis

H0: Golden Star fires carry **no bottom-finding edge** — 21d absolute win-rate, mean forward return, and MFE/MAE at Golden Star dates are indistinguishable from date-and-liquidity-matched random entries in the same universe.

**Null construction (matched-placebo):** for each Golden Star fire, draw M=1000 placebo entries matched on (calendar week, ADV decile) from non-firing names in the same universe. Build the block-bootstrap null distribution of each metric. This neutralizes the regime-timing confound: a Golden Star firing in a market-wide rally must beat *other stocks entered the same week*, not cash.

### 5.7 Benchmark (repo's existing bottom-finders)

Head-to-head via `paired_delta_ci`:
1. **`us_stocks` bottoming-alignment rank** — the existing standout system's primary bottom-finding signal.
2. **Oracle reversion base** — the ratified reversion ruler's incumbent (already published to registry).

Golden Star must show it is **not merely redundant** with the incumbent bottom-finder. Required outputs: overlap % of fired names (same week), paired delta in 21d absolute reversion-capture, CI bounds from `paired_delta_ci`.

### 5.8 Multiple-testing budget (frozen before run)

Total pre-registered trials fed to `deflated_sharpe` ledger:
- 2 MA families {7/35, 21/100} × 2 geometry readings {price-line gate ON, price-line gate OFF} × 3 exits {20, 21, 25d} = **12 configs**
- Verdict rendered ONLY at: **7/35, price-line gate ON, 21d exit**
- The other 11 are sensitivities/robustness: logged to the ledger so the DSR haircut is honest, never presented as independent verdicts
- Regime split (§5.9) and horizon sensitivities count against the ledger, no free peeking

### 5.9 Pre-declared PASS gate (frozen; no post-hoc threshold changes)

All four must hold on **OOS/walk-forward folds** (`purged_folds`, embargo = 21d):

**Gate 1 — Win-rate:**
21d absolute WR ≥ **58%** AND block-bootstrap 95% CI lower bound > matched-placebo null median (§5.6).

**Gate 2 — Safety:**
Median **MFE/MAE ≥ 1.5** AND durable-bottom rate ≥ placebo null + CI lower bound > 0.

**Gate 3 — Deflated significance:**
`deflated_sharpe(..., ledger=)` DSR verdict ≥ "supported" after full trials ledger (§5.8). `prob_backtest_overfitting` PBO < 0.5.

**Gate 4 — Non-redundancy & robustness:**
`paired_delta_ci` vs incumbent bottom-finder has CI **not** entirely ≤ 0 (adds something beyond incumbent) AND sign is **fold-robust** (≥ ⌈k × 0.7⌉ folds agree) AND regime-split check passes: fires in downtrend AND uptrend regimes both show WR CI-lower > placebo (a bottom-finder that only fires in bull tape is a beta artifact — **FAILS Gate 4 even if Gates 1–3 pass**).

**If any gate fails:** result is printed as NULL in the registry per epistemics law. Not retried. Not quietly dropped. A FAIL is interpreted through the ratified caveat that OOS failure can be regime-change, not overfit; the regime-split in Gate 4 is what disambiguates (see oracle-reversion memory: "a backtest FAIL assumes stationarity; scrutinize KILLS as hard as promotions").

### 5.10 What this test cannot conclude

- It tests the **assumed reconstruction** (7/35 and 21/100, P≈3% price-line band) because the true `P`, `L`, and `k` are UNKNOWN (§2.1). A NULL therefore falsifies *this reconstruction*, not necessarily StockInvest's private construction. This caveat is printed alongside every verdict.
- "New Golden Star" reduces to the same fire (age≤1d) — not separately gauntleted.
- Long-term 50/200 Death/Golden Star are trend signals, not bottom signals — out of scope for this backtest.
- Score weighting is unpublished — the Score is not backtested here.

---

## §6. Wave 3 spec — Neural Web context artifact (GATED)

**Gated on:** Wave 1 backtest clearing all four PASS gates (§5.9) AND a Fable/Opus adjudication checkpoint that reviews the full results. Do not begin until both conditions are met.

### 6.1 What Wave 3 delivers

A single context-tier synapse artifact: `golden-star-context` registered in `synapse.yml`. The artifact carries:
- Current Golden Star fire count (7/35 family) as of the last nightly
- Age distribution of fires (< 2d, 2–5d, > 5d)
- Calibration status flag
- Backtest verdict summary (pass/null/pending, not the full results)

This is **context metadata only** — it informs how other NW signals interpret the tape, not how they act on it. It does not change any weight, score, or allocation.

### 6.2 What Wave 3 does NOT do

- Does NOT edit `engine/masterminds.py` (off-limits, Oracle Constitution §III).
- Does NOT route Golden Star fires to any act-now surface.
- Does NOT promote Golden Star to a scored or confirmer-tier synapse (display tier only, unless/until a separate gauntlet pass occurs on the NW-specific signal).
- Does NOT merge the "Golden Oracle" (`engine/canon.py:421 confluence_signals`) with this artifact — they are separate display leaves.
- Does NOT modify the Master-Brain confluence leaf except for a single display annotation showing the new context key's current reading.

### 6.3 Synapse registration

Following the spine-adapter contract:
```yaml
# synapse.yml addition (Wave 3)
- id: golden-star-context
  tier: display
  horizon_role: context
  scored_path_surfaces: []
  producer: scripts/build_indicator_screener.py
  cadence: nightly
  asof_field: as_of          # full ISO timestamp (ETM-R1..R8 law: full ISO mandatory)
  description_en: "Golden Star MA-cross context: current fire count and calibration status (display-only)"
  description_zh: "金星MA交叉背景：当前触发数与校准状态（仅展示）"
  gated: true
  gate_ref: "research/STOCKINVEST_TECH_INDICATOR_SUITE_PROGRAM.md §5.9"
```

### 6.4 Master-Brain display leaf (optional)

If the adjudication checkpoint approves, a single read-only annotation is added to the existing "Golden Oracle" confluence leaf in `engine/canon.py:421 confluence_signals`: appending the `golden-star-context` reading to the leaf's context block. This is the only permissible edit to canon.py in Wave 3. No new logic, no weight changes.

---

## §7. Wave plan

| Wave | PR | What | Model lane | Gating | Risk |
|---|---|---|---|---|---|
| W1-A | PR-1 | This program doc + DO_NOT_REBUILD entry | Sonnet build | None | LOW |
| W1-B | PR-2 | `engine/lab.py`: indicator registry + `characterize()` + Golden/Death Star constructors + tests | Sonnet build, Opus review | PR-1 merged | HIGH — keystone |
| W1-C | PR-3 | `scripts/research/golden_star_backtest.py`: pre-registered harness; PREREG section §5 is the authority; run ONLY after PR-3 merged; commit summary JSON result | Sonnet build, Opus stats review | PR-2 merged; §5 prereg frozen | HIGH — stats integrity |
| W1-D | PR-4 | Backtest verdict report + registry null/pass entry + ops calibration task note | Opus stats review, Fable/Opus adjudication checkpoint | PR-3 run and results committed | HIGH — verdict |
| W2-A | PR-5 | `scripts/build_indicator_screener.py` + `data/lab/indicator_screener.json` (first nightly pass) | Sonnet build | PR-4 merged | MED |
| W2-B | PR-6 | `templates/tech_indicator_screener.html.j2` + paired `site/tech_indicator_screener.html` + navlinks entry | Sonnet build, Opus review | PR-5 merged | MED |
| W3-A | PR-7 | Synapse registration (`synapse.yml` + `SIGNAL_BUS.md` regen) + optional Master-Brain display leaf annotation | Sonnet build, Opus review, Fable/Opus adjudication checkpoint | Wave 1 PASS gate cleared + adjudication done | MED |

**Merge sequencing law:** PRs within each wave merge strictly in order. W2 does not begin until all W1 PRs are merged. W3 does not begin until Wave 1 PASS gate is cleared and the adjudication checkpoint is documented. `synapse.yml` and `SIGNAL_BUS.md` are append-only git files subject to the registry-drift merge race; regenerate SIGNAL_BUS.md on the trailing merge of any synapse edit.

**Post-program queue (mechanical, specs locked):**
- Calibration follow-up PR after operator ground-truth exercise (§3.5).
- Caller migration (consoldiating the ~15 RSI / ~11 StochRSI callers to import from `engine.lab` or `engine.canon`) — separate refactor program, not this program (scope fence).
- Death Star backtest (separate program; this program establishes the harness, but the Death Star premise test is a distinct question).
- Score reconstruction study (separate program; weighting is UNKNOWN and the Score is not a signal — a Score backtest requires its own adjudication).

---

## §8. Overlap and DO_NOT_REBUILD awareness

### 8.1 Existing artifacts this program augments (DO NOT duplicate or replace)

| Artifact | Location | Relation |
|---|---|---|
| Signal Lab | `site/signal_lab.html` + `engine/signal_lab.py` | Different surface — Signal Lab is an evidence-tier registry for macro + NW signals. This program adds a technical-indicator Research screener. They are siblings, not competitors. |
| Oracle compound library | `data/oracle/compounds/registry.jsonl` + compound grammar | The Oracle compound library governs NW chemical signals. This program does not add a compound; it adds a context artifact. |
| Research Factory | `research/RESEARCH_FACTORY_PROGRAM.md` + funnel | This program's Research screener is display-only; it does not go through the Research Factory promotion pipeline in Wave 1 or 2. If Wave 3 PASS gate is cleared, the gauntlet runs through the standard pipeline. |
| `us_standouts.json` | `engine/top_picks.py` → `discovery.html`, `engine/setups.py`/`build_stock_library.py` | NOT replaced. Wave 2 screener is a separate Research surface. The wave 2 screener explicitly footnotes its independence from the standout system. |
| Golden Oracle | `engine/canon.py:421 confluence_signals` → `engine/master_brain.py` | Display-only leaf. Wave 3 optionally adds a context annotation to it, but does not change its logic or promote it. |
| Canonical indicator functions | `engine/canon.py`: `rsi()` (line 341), `stoch_rsi_kd()` (line 412) | `engine/lab.py` delegates to these; it does not re-implement them. |

### 8.2 Killed and forbidden patterns (do not re-propose)

| Pattern | Kill reason | Authority |
|---|---|---|
| **FRESH-BUY surface** (routing a freshly-fired Golden Star to notifications/Discord/act-now) | Launders a lagging trend signal as a time-critical buy trigger without a gauntlet | RUL-3 this program |
| **LLM-originated signals** | Constitution; LLMs may only de-escalate calibrated keys | House law + RUL-4 |
| **Human-override gate in allocation()** | BTC vector registry precedent; midterm-blackout gate is a laundered human override | `btc-vector-override-registry-program.md` |
| **Fused shield/meta-router** (Golden Score as input to portfolio-level meta-router) | Forbidden design per Mastermind control plane program | RUL-7 + `mastermind-control-plane-program.md` |
| **Positioning fusion** (Golden Star + NW → direct sizing) | Positioning fusion illegal; Signal Commons W6 ruling | `signal-commons-program.md` W6 + RUL-5 |
| **Staleness-alpha** (Golden Star "works" only because it fires in bull tape) | Gate 4 of PASS gate catches this explicitly; a bottom-finder that only works in bull tape FAILS | RUL-10 + §5.9 Gate 4 |
| **Free-horizon verdicts** (running multiple exit horizons and picking the best) | Forking-paths law; all horizon variants enter the trials ledger before the run | RUL-8 + §5.8 |
| **Era-pooled inference** (no pre-2010/post-2010 split) | DT-R16 era-split law | `dannytrades-adjudication-program.md` DT-R16 + RUL-9 |
| **Score weighting reconstruction as a signal** | Score weighting is UNKNOWN and unpublished; reconstructing it without evidence is speculative score-origination | §2.7; RUL-4 |
| **"Validated" in user-facing strings** | CI-enforced (`scripts/check_validated_claims.py`) | House epistemics law |

### 8.3 DO_NOT_REBUILD entries to append (post this program PR)

Append to `research/DO_NOT_REBUILD.md`:

| Pattern | Verdict | Authority |
|---|---|---|
| Fresh-buy surface routing Golden Star fires to act-now notifications | KILLED — FRESH-BUY: lagging signal laundered as time-critical buy trigger | RUL-3, this program |
| Score weighting reconstruction for Golden Score as allocatable signal | KILLED — UNKNOWN weighting + LLM-origination risk; bands are display-only | RUL-4/7, this program |

---

## §9. What this program does NOT do (scope fences)

- No edits to `engine/masterminds.py` (Oracle Constitution §III — unconditional).
- No changes to `us_standouts.json`, `engine/top_picks.py`, `engine/setups.py`, or `build_stock_library.py`.
- No caller migration of existing RSI/StochRSI copies (tracked as a separate refactor; see §3.1 census note).
- No Death Star backtest (separate program — this program builds the harness; Death Star premise test is a separate adjudication).
- No Score weighting reconstruction study (UNKNOWN weighting; a Score backtest requires its own adjudication and is not in scope here).
- No new nightly compute beyond `build_indicator_screener.py` (target < 60s, within render budget).
- No positioned-money outputs at any wave.

---

## §10. Status log

| Date | Entry |
|---|---|
| 2026-07-07 | Program ratified. Wave 1 build-ready. W1-A (PR-1) dispatched: this doc + DO_NOT_REBUILD append. |
| 2026-07-07 | Wave 1 outcome (partial): lab façade (`engine/lab.py`) + Golden Star (7/35) and Death Star reconstruction landed and verified against synthetic fixtures. The premise-backtest agent was cut off before completing §5.9; **no §5.9 verdict exists**. A FIRST-PASS DESCRIPTIVE read was run on the survivor universe (NOT the §5.9 gate — full gauntlet deferred per operator directive above): the **SHORT-TERM Golden Star (7/35)** fires median +12.7% above the trailing-60d low, approximately 54 calendar days after the low, with 85% of fires occurring in up-tape (rising 60d SMA). 21d WR = 58.5% vs base rate 57.1% — a 1.4pp spread that does not clear any pre-declared edge threshold. Interpretation: the 7/35 Golden Star behaves as a lagging trend-confirmation signal, not a bottom-finder, under this descriptive read of the survivor universe. Survivorship caveat applies (delisted names not yet confirmed in universe). The **LONG-TERM (50/200) Golden Star was NOT tested** and is a separate signal with different temporal properties; no read exists for it. Operator directive: build the full engine suite (Wave 2 per §11) before resuming verdict work. |

---

## §11. Wave 2 — Engine Suite & Catalog

**Per operator directive (Directive Update 2026-07-07):** build all signal-production modules and the AI-friendly catalog before returning to gauntlet work. No verdict gate applies to this section.

### 11.1 Signal modules to build

Each module lives under `engine/` and produces a vectorized signal series over the standard US universe. All modules import indicator primitives from `engine/lab.py` or `engine/canon.py`; no new indicator re-implementations.

| Module | Coverage |
|---|---|
| `engine/ma_crosses.py` | All Golden Star / Death Star families (7/35, 21/100, 50/200); plain Golden Cross / Death Cross for comparison; `new_golden_star` age flag |
| `engine/pivots.py` | Algorithmic pivot tops/bottoms (zigzag ±3% verify as per §2.7 source quote); support/resistance levels; pivot recency |
| `engine/rsi_signals.py` | RSI-14 and RSI-21 zone reads (overbought/oversold bands); StochRSI K/D cross; RSI divergence flag (descriptive) |
| `engine/formations.py` | Double top / double bottom detection (verbatim-named in Score input list §2.7); Bollinger-squeeze entry flag |
| `engine/trend_signals.py` | MACD line/signal cross; trend-strength read from MA slope; multi-timeframe trend alignment |
| `engine/fundamental_screens.py` | Over/undervalued flag relay from third-party fundamentals data already in repo; passes through existing data, does not re-source |
| `engine/tech_stars.py` | Golden Star + Death Star + New Golden Star composite signal emitter; single entry point that calls `ma_crosses` with correct family routing and confirms +2d lag |

### 11.2 `engine/tech_catalog.py` — AI-friendly signal registry

Machine-readable registry of every signal produced by the suite. Each entry carries enough context for an LLM consumer (Neural Web cortex, research scripts) to interpret a reading without needing to inspect module code.

Required fields per entry:
- `id`: kebab-slug (e.g., `golden-star-st-7-35`)
- `name` / `name_zh`: bilingual display name
- `module`: source module path
- `signal_class`: `trend_confirmation | mean_reversion | momentum | breadth | fundamental`
- `direction`: `bullish | bearish | neutral`
- `primary_params`: dict of param name → value or `"UNKNOWN"`
- `source_anchor`: short verbatim quote or `"ASSUMED"` / `"INFERRED"`
- `confidence`: `well_supported | plausible | speculative`
- `temporal_role`: `lagging | coincident | leading` (honest label — Golden Star 7/35 = `lagging` per Wave 1 descriptive read)
- `known_bias`: free-text honest prior (e.g., "fires preferentially in up-tape — 85% in bull regime per Wave 1 descriptive read")
- `status`: `display_only | display_only_pending_calibration | killed`
- `verdict_ref`: path to §5.9 result or `"pending"`

`tech_catalog.py` exposes `catalog() -> list[dict]` and `lookup(id: str) -> dict`. It is the canonical source for the Wave 2 screener and for any NW artifact that references a signal by ID.

### 11.3 `engine/tech_score.py` — composite score + confluence runner

Implements the −10..+10 score display annotation and a confluence summary over the full signal suite.

**Score bands** (verbatim from §2.7, frozen):
- `[5.00, 10.00]` Strong Buy / 强烈买入
- `[1.00, 4.99]` Buy / 买入
- `[−0.99, 0.99]` Hold / 持有
- `[−4.99, −1.00]` Sell / 卖出
- `[−10.00, −5.00]` Strong Sell / 强烈卖出

**Score weighting is UNKNOWN** (§2.7 ruling stands). `tech_score.py` does NOT reconstruct a weighting function. It provides:
- `score_band(score: float) -> str`: maps a raw score to the named band. Display annotation only.
- `confluence_runner(ticker: str, signals: dict) -> dict`: counts bullish vs bearish signal fires across all active modules; returns `{bullish_count, bearish_count, net, top_signals: list[str]}`. This is a raw count, not a weighted score — it is labeled `confluence_raw` to distinguish it from StockInvest's proprietary weighting.
- `display_score(confluence_raw: dict) -> float`: maps `net` count to a display score in [−10, +10] via a linear interpolation anchored to the verbatim band breakpoints. This is a DISPLAY APPROXIMATION — labeled as such in all outputs. It does not claim to reproduce StockInvest's internal model.

**RUL-4 still applies:** the display score is a deterministic formula over signal counts, not an LLM inference. It is explicitly labeled as a display approximation in every output surface.

### 11.4 `lab.characterize` expansion

`engine/lab.characterize()` (§3.3) is expanded to call all Wave 2 modules and return their readings alongside the original Golden/Death Star output. The returned dict gains a `tech_catalog_readings` key: signal-id → `{fired: bool, value: Any, band: str|None, temporal_role: str, known_bias: str}`. This makes `characterize()` the single-call white-space map over the full suite.

### 11.5 Tests

Each module ships with synthetic-fixture tests (no Mac-local data dependency):
- `test_ma_crosses_all_families`: verify 7/35, 21/100, 50/200 cross detection + confirm lag.
- `test_pivots_zigzag_verify`: confirm ±3% verify gate suppresses low-amplitude swings.
- `test_rsi_signals_delegates_to_canon`: assert no re-implementation.
- `test_formations_double_bottom_synthetic`: geometric double-bottom fixture fires; non-pattern suppressed.
- `test_tech_catalog_all_ids_unique`: no duplicate IDs.
- `test_tech_catalog_required_fields`: all entries carry the mandatory fields (§11.2).
- `tech_score_band_boundaries`: exact band boundary values from §2.7 tested against score_band().
- `tech_score_confluence_runner_counts`: bullish/bearish count correctness on synthetic signal dict.
- `test_characterize_expansion_includes_catalog`: expanded characterize() output contains `tech_catalog_readings`.

### 11.6 Wave 2 merge sequence

Build order (modules can be built in parallel; catalog and score depend on modules):
1. `engine/ma_crosses.py` + `engine/pivots.py` + `engine/rsi_signals.py` (parallel)
2. `engine/formations.py` + `engine/trend_signals.py` + `engine/fundamental_screens.py` (parallel)
3. `engine/tech_stars.py` (depends on ma_crosses)
4. `engine/tech_catalog.py` (depends on all modules being final)
5. `engine/tech_score.py` (depends on catalog)
6. `lab.characterize` expansion (depends on score)

All six steps merge before verdict or gauntlet work resumes.
