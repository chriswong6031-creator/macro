# TOPA Phase-0 Prereg — Extended-Move Anatomy: topped vs continued

**Frozen:** 2026-08-10, before any result was computed (commit order is the audit trail).
**Family:** `top_anatomy_p0`
**Authority:** `research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md` §4–§5 (W0); parent docket `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` (L1) — S1⁻/S2⁻/S13⁻ absorbed at episode scale.
**Harness:** `python -m scripts.research_top_anatomy_phase0 --data-root <primary>/data` (module named here per house convention; committed outputs: `data/research/top_anatomy_p0_summary.json` + `reports/top-anatomy-phase0.md`).

## 0. Prior information and trial budget

Adjacent priors on file: sector-ETF scope — extended-then-rolling-over is the only honest topping gate (`engine/sector_signals.py`, 1998–2026); onset scope — no t0 feature separates kept-going from blow-off (W3/W4, closed); W4 found `realized_vol_63d` and `updown_dollar_vol_ratio` are motion-not-quality signatures. No in-repo prior exists on mid/late-life extended-day separation — this is the first construction on that population (ORE-law: first construction, mapped before any kill).

**Trial budget (declared):** 36 features × 1 primary contrast (E1, track W) = 36 tests, BH-FDR q ≤ 0.10 **within each of 6 families**; E1b is 3 pooled models (extension-only, +family winners, full) × 2 CV schemes = 6 fits, no hyperparameter grid (fixed L2 logistic, C=1.0, standardized); 2 extension-definition sensitivity arms are report-only (no registration claims); E2/E3/E4 are descriptive profiles of E1 survivors (no new tests). No `deflated_sharpe`, no Sharpe claims.

## 1. Hypothesis (one, mechanism-named)

**H1 (incremental demand exhaustion is PIT-visible):** among EXTENDED (name, day) observations, features measuring demand absorption and leadership decay — relative-strength deceleration/peak-lag, effort-vs-result deterioration, up/down dollar-volume asymmetry, participation/maturation structure — separate days that resolve TOPPED from days that resolve CONTINUED, *beyond what extension magnitude and realized volatility themselves separate* (they are matched away). Direction is pre-declared per feature in §4's table.

## 2. Wrong-ruler check

The bottom-side PSS §7 lesson mirrored: topped/continued race labels alone (a return ruler) are not sufficient to call a warning "good" — a fire with large remaining upside is a bad warning even if the episode eventually tops. Phase-0 therefore reports, for any E1-surviving feature thresholded at control-P90: median **remaining upside to episode peak**, **peak proximity** (within 5% of peak price), **time proximity** (within ±10td of peak), and **forward-63td excess** vs the all-extended-days null — per-name-first, month-block bootstrapped. These are report metrics, not additional registered tests.

## 3. Data and universe (frozen)

- **Track W (registration):** `data/massive_stock_day/*.parquet`, split-adjusted via `scripts/replay_standout_pipeline.split_adjust` (dividends unadjusted — stated). Days 2021-07-06 → run date. Eligibility at day d: close_d ≥ $3; median 21d dollar volume ≥ $2M; ≥ 260 prior sessions of history (r252 may still be null early — printed, not imputed). Common shares and ADRs as-listed; no derivative/warrant/unit filtering beyond the price/liquidity floors (stated limitation).
- **Track D (era context):** `engine/price_ladder.py` adjusted rungs (`baskets_ohlcv` ∪ `yahoo` ∪ `data_stocks`, first-rung-wins per name), 1997-01-01 → run date, same floors. Survivorship tilt disclosed in every table that uses D. Features requiring open/volume are null where a rung lacks them; per-feature coverage counts printed; a feature with <60% coverage on a track is not interpreted on that track (coverage floor, house law).
- **Cross-sections** (universe medians for RS features): computed per-day over that day's PIT-eligible names within the same track.

## 4. Frozen construction

### 4.1 Extended day (primary)

`EXT(d)` ⇔ `r126(d) ≥ +0.50` AND `close(d) ≥ 0.90 × max(close over trailing 252 sessions)` AND eligibility floors (§3).

Sensitivity arms (report-only): (a) `r63 ≥ +0.35` with the same near-high term; (b) `(close − MA200)/ATR63 ≥ 6` with the same near-high term.

### 4.2 Episode

Contiguous EXT days per name, merging gaps ≤ 21 sessions. Episodes with < 5 EXT days are kept in the tape but excluded from E1 (micro-spells; count printed).

### 4.3 Day-level race label (primary outcome)

From each EXT day d with entry price c_d: scan forward ≤ 250 sessions.
- **TOPPED(d)** if close first falls to ≤ 0.80 × (running max close from d onward) — i.e. a −20% drawdown from the post-d peak — before close ever reaches ≥ 1.15 × c_d **measured from the race state at that moment** (formally: walk forward; track running_peak; TOPPED fires the first day close ≤ 0.80×running_peak; CONTINUED fires the first day close ≥ 1.15×c_d; whichever fires first wins; if the same day satisfies both, TOPPED wins — conservative).
- **CONTINUED(d)** if the +15% barrier fires first.
- **CENSORED(d)** otherwise (horizon end or data end, incl. delisting without a −20% print — delisting with a terminal collapse will fire TOPPED naturally; counts per class printed).

Display-grade auxiliary outcomes (descriptive only, no tests): max forward drawdown from post-d peak at 21/63/126td; fwd returns 21/63/126td; drawdown ≥{10,15,30}% event flags.

### 4.4 Episode peak and terminal top (for lead-time anchoring)

`peak(e)` = argmax close over [episode_start, episode_end + 63 sessions]. Episode **TOPPED** if min close over [peak, peak + 126 sessions] ≤ 0.80 × close(peak) with no intervening close > close(peak) before that −20% print; else **SURVIVED** (censoring stated at data edge). `days_to_peak(d) = peak_date − d` in sessions (positive = d precedes peak).

### 4.5 Matched-control design (E1, primary)

- **Cases:** for each TOPPED episode (per §4.4) on track W, snapshot days at offsets `days_to_peak ∈ {21, 10, 5}` (three pre-declared snapshots; a snapshot exists only if that day is an EXT day — counts printed per offset).
- **Controls:** EXT days (from other names) whose day-level race label (§4.3) is CONTINUED, drawn from the same calendar quarter, same r126 quintile (within-track, within-quarter), same rv63 tercile, same 21d-dollar-volume tercile. Up to 4 controls per case, nearest-neighbor by |Δr126| then |Δrv63| within the bucket, sampled without replacement within a case; cases with zero eligible controls are dropped and counted.
- **Estimator (W4 spec mirrored):** per-feature matched-set Δ = case − mean(controls); headline = median Δ across case-sets; CI = 95% percentile bootstrap resampling **calendar-month blocks** (B=2000); robustness = ticker-cluster bootstrap (report-only). Separation claim requires: month-block CI excluding 0 in the pre-declared direction AND BH-FDR q ≤ 0.10 within family (6 families) at the pooled-offsets level; per-offset profiles are descriptive.

### 4.6 Feature library (36 features; all PIT at d; formulas frozen)

Let c=close, o=open, v=volume, $v = c×v; MA_k = k-session simple MA of c; ATR_k = k-session mean true range; r_k = c_d/c_{d−k} − 1; rv_k = std of daily log returns over k sessions (annualized ×√252); slope_k(x) = OLS slope of x on t over k sessions; eqw index = per-day median cumulative-return index of the track's PIT universe; rs_line = c / eqw_index (rebased per name).

**A. Extension & geometry (8):** A1 r21; A2 r63; A3 r126; A4 r252; A5 (c−MA50)/ATR21; A6 (c−MA200)/ATR21; A7 late_gain_share = (ln c_d − ln c_{d−21})/(ln c_d − ln c_{d−126}) when denom > 0.05 else null; A8 trend_r2_63 = R² of ln c on t, 63s. *Direction: higher ⇒ TOPPED for A5–A7; A1–A4, A8 exploratory (matched-away in part; sign not pre-committed).*
**B. Momentum & acceleration (6):** B1 accel = r21 − r21 lagged 21s; B2 RSI14 (Wilder); B3 RSI14 − RSI14 lagged 10s; B4 newhigh63_rate21 = share of last 21 sessions with c = 63s max; B5 upday_rate21; B6 max consecutive-up-day streak in 21s. *Direction: B1,B3 lower ⇒ TOPPED (deceleration); B2,B4–B6 exploratory.*
**C. Volatility structure (6):** C1 rv21; C2 rv21/rv63; C3 semivol_down/up 63s (std of negative vs positive daily returns); C4 ATR21/c minus its value 21s ago; C5 gap_freq21 = share of last 21 sessions with |o/c_prev − 1| > 2% (null without opens); C6 mean(TR,5)/mean(TR,63). *Direction: higher ⇒ TOPPED for C2,C3,C4; C1,C5,C6 exploratory.*
**D. Volume & effort (6):** D1 dvol_z = z of ln(mean $v, 21s) vs its own trailing 252s distribution; D2 slope_21(ln v); D3 updown_dvol_ratio21 = Σ($v | ret>0)/Σ($v | ret<0) over 21s; D4 Δ21 progress_per_effort, where ppe = r21 / mean21(v/mean252(v)); D5 corr21(v_z, |ret|); D6 churn21 = share of last 21 sessions with v > 1.5×mean252(v) AND |ret| < 0.5×std63(ret). *Direction: lower ⇒ TOPPED for D3,D4,D5; higher ⇒ TOPPED for D6; D1,D2 exploratory.*
**E. Relative strength (5):** E1f xr63 = r63 − median universe r63; E2f xr21 likewise; E3f rs_peak_lag = sessions since rs_line's 63s max; E4f price_rs_gap = rs_peak_lag − (sessions since c's 63s max); E5f rs_decel = slope_21(ln rs_line) − slope_21(ln rs_line) lagged 21s. *Direction: higher ⇒ TOPPED for E3f,E4f; lower ⇒ TOPPED for E5f; E1f,E2f exploratory.*
**F. Maturation & structure (5):** F1 episode_age (sessions since episode start); F2 c/max(c in episode so far) − 1; F3 sessions since last 63s high; F4 deepest dip in last 21s vs running 63s max; F5 reclaim_speed = sessions the most recent completed ≥5% intra-episode dip took to reclaim its pre-dip high (null if none/unreclaimed; unreclaimed-flag printed). *Direction: higher ⇒ TOPPED for F1,F3; lower (more negative) ⇒ TOPPED for F2,F4; F5 higher ⇒ TOPPED.*

### 4.7 Pooled increment (E1b)

Day-level TOPPED vs CONTINUED on all EXT days (not just matched sets), track W. Models: (M0) r126 alone; (M1) M0 + rv63; (M2) all 36. Fixed logistic, standardized, L2 C=1.0. CV-A: 5-fold grouped by ticker. CV-B: expanding walk-forward by calendar quarter with a 63-session purge/embargo between train end and test start. Metric: AUC (day-level) and episode-level AUC (episode max prob vs episode outcome). Claim of interest: AUC(M2) − AUC(M1), both CV schemes, sign-consistent. No feature selection inside folds beyond the fixed set (no tuning).

### 4.8 Lead-time and ordering (E2/E3, on E1 survivors only)

E2: median matched Δ by days_to_peak buckets {−63..−22, −21..−6, −5..−1, 0..+5}; a survivor is labeled **EARLY/MID/LATE** by the earliest bucket whose month-block CI excludes 0, or **POST-TOP CONFIRMATION** if only the {0..+5} bucket separates. E3: within TOPPED episodes, median first-crossing order of survivor features at control-P90 thresholds (descriptive sequence table).

### 4.9 Era & cap stability (E4)

Descriptive sign-stability tables of E1 survivors: track W eras {2021H2–2022, 2023–2024, 2025–2026}; track D eras {1997–2003, 2004–2012, 2013–2020, 2021–2026} for features computable on D; dollar-volume terciles as the cap proxy (massive store carries no shares outstanding — stated).

## 5. Gates and decision rules

- **This is a discovery phase-0: there is no program kill on a null.** Outcomes bind copy and sequencing, not existence:
  - **≥1 family with ≥1 DETECTION-grade survivor** (E1 pass + E2 label EARLY/MID/LATE, i.e. any pre-peak bucket) ⇒ Wave-2 hazard-model prereg is chartered; Wave-1 copy may cite the survivor legs as "what we watch" (display-tier, no probabilities).
  - **Survivors exist but all label POST-TOP CONFIRMATION** ⇒ they may power only the `breaking`-state legs in Wave 1; no "early warning" copy anywhere.
  - **Zero survivors** ⇒ Wave 1 ships descriptive-only (states + episode-library base rates, no separation claims); Wave 2 pivots to cross-sectional/theme constructions (different construction, fresh prereg; this row closes only the single-name-OHLCV matched-contrast construction).
- **Integrity gates (hard, from masterplan §0):** G0.2 delisting verification (≥3 named dead tickers in the W tape with terminal bars); G0.3 episode honest-N on every table; G0.4 lead-time labels mandatory; G0.5 today's-tape coverage appendix + Opus red-team before presentation.
- Any deviation from this construction discovered mid-run (data defect, degenerate bucket) is recorded in §6 with its trigger BEFORE outcomes are read at the affected step; silent re-pins are forbidden.

## 6. Ratification log (append-only)

- 2026-08-10: Frozen at charter. No results computed. (Deviations, if any, and results-time entries append below with dates.)
- 2026-08-10 (pre-outcome deviation, data defect — trigger recorded before any label was computed): the massive store keys by TICKER and tickers are reused across corporate identities (verified: `BBBY.parquet` = old Bed Bath & Beyond through 2023, an 850-day gap, then a different company from 2025-08-29). **Rule added:** every ticker's series is split at interior gaps > 60 sessions into identity segments treated as independent names (own history floor, episodes, PIT windows truncated at segment start; nothing crosses a boundary). Segment counts printed in the summary. This is an identity repair, not a construction change; race/feature definitions are untouched.
