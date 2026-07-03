# H1 — Southbound Holding-Δ · PRE-REGISTRATION

**Battery:** HK/CA masterplan §3 H1 (the flagship-mechanism thin test).
**Committed BEFORE any run.** Constitution: research/HK_CANADA_STOCKS_MASTERPLAN_BY_FABLE.md §6 + §6.1; red-team: research/HK_CANADA_REDTEAM_FINDINGS.md (HK critic §62 execution-horizon decay; MISSING: suspension fill rule, survivorship bound, PIT Connect eligibility).

---

## 1. Hypothesis

**Mechanism (literature-strong):** an increase in mainland Southbound ownership of an HK-listed name is fast-decay *demand pressure* — buying by the Connect crowd pushes the name up over the following days/weeks. If real and tradable through our delivery vehicle, a cross-sectional rank of the change in Southbound ownership should positively predict forward HK-relative (vs HSI) returns.

**H1-primary:** Δ4w own_pct (change in % of issued shares held Southbound over the trailing 4 weeks) ranks names by forward 1w/2w/4w HSI-excess return, rank-IC > 0.
**H1-secondary:** Δ1w own_pct, same forward windows.

**Honest prior (pre-registered): ACCRUE.** n ≈ 85 weekly cross-sections ≈ 2 years ≈ **~2 independent regimes** (2024-H2 China-stimulus rip; 2025→ digestion). At effective-N ≈ 2 the DSR≥0.90 door is structurally shut unless the effect is enormous; the honest outcome is ACCRUE with a full-power re-run at ~3y (2027-07). We run it anyway to (a) measure the *sign and rough magnitude* now, and (b) measure the **implementation shortfall** the red-team demanded — the gap between an idealized next-open fill and the render-lagged fill a nightly dashboard actually imposes. If even the lag+0 sign is wrong or trivially small, H1 is a *context chip, never a ranker*, and the card copy must say so.

---

## 2. Data & universe

- **Signal source:** `data/hk_southbound/holdings.parquet` — MultiIndex (date, ticker), 464 daily trading dates 2024-07-10→2026-07-02, 729 tickers seen (~407 median/day). Column `own_pct` = Southbound holding as % of issued shares (range 0–77, in percent). #1065 backfill (2y rolling Eastmoney window — no deeper history exists; see red-team FATAL HK-1).
- **Price panel:** `data/hk_stocks/*.parquet` — 157 per-ticker OHLC files, 2000→2026-07-03, columns {open, high, low, close, volume}. `open` present ⇒ next-open fills feasible. (The expanded `data/hk_stocks_ext/` is R2-only / not landed in-tree — no per-ticker parquets present; we fall back to the 157 panel per the prompt's fallback clause.)
- **Universe = holdings ∩ price panel = 147 common names.** After the Δ4w warmup, **~106 valid names per Friday** (median), **85 weekly cross-sections** with ≥10 valid Δ4w names. This panel is mega-cap-skewed (0700/9988/HSBC/ICBC…) — a stated bias, not the full 729-name Southbound universe.
- **Benchmark:** `data/hk/_HSI.parquet` (close, fresh to 2026-07-03). Excess return = name return − HSI return over the identical fill-open→horizon window. (`data/hk_search/_HSI_deep.parquet` is stale at 2026-06-12 and would truncate the forward window — NOT used.)

---

## 3. Exact construction

### 3.1 Weekly cross-sections
- Cross-section dates = **Fridays** present in the holdings date index (89 Fridays; a week missing its Friday print — HK holiday — is simply skipped, never carried).
- `own_pct` reshaped to a (date × ticker) panel restricted to the 147 common names, reindexed onto the full holdings trading-date axis (so Δ is measured over *calendar* weeks of prints).
- **Signal, primary:** `Δ4w = own_pct[Friday] − own_pct[Friday − 4 Fridays]`.
- **Signal, secondary:** `Δ1w = own_pct[Friday] − own_pct[Friday − 1 Friday]`.
- A name enters a cross-section only if BOTH endpoints of its Δ are non-null (no imputation of a missing own_pct print).

### 3.2 Forward returns — NEXT-OPEN fills, two lags (the implementation-shortfall test)
Southbound holdings for date T disclose **T+1** (after HK close). The earliest a mechanistic actor could trade on the disclosure is the open of the first session strictly after T.

- **lag+0 (idealized disclosure fill):** buy at the **open of the 1st trading session > Friday T**. Forward return measured from that open.
- **lag+1 (dashboard-honest fill):** buy at the **open of the 2nd trading session > Friday T** — one extra session for the overnight render + next-morning read. This is the red-team's explicit implementation-shortfall demand; the two are reported side by side.

Trading calendar = the union price index of the panel. Horizons in **sessions**: 1w = 5, 2w = 10, 4w = 20.
- Fill open = `open[fill_date]`; horizon-end price = `close[fill_date + h sessions]`.
- Name return = `close_end / open_fill − 1`.
- **HSI-excess:** HSI return over the identical [fill_date, fill_date+h] window (HSI close-to-close, anchored at the HSI close on the session *before* fill_date to align the window start), subtracted from the name return. (HSI has no open; using its close bracket over the same session span is the standard index-excess convention.)

### 3.3 Suspension / halt rule (red-team MISSING, HK critic)
HK names halt for weeks. **No forward return is computed by forward-filling through a halt.** A name is INCLUDED at horizon h only if it has a *real* print (non-null close, and volume > 0 where volume exists) on **both** the fill date and the horizon-end date, AND had no gap > 5 consecutive missing sessions inside the window. If the fill-open session itself has no valid print within **5 sessions** of Friday T, the name is EXCLUDED from that cross-section (never ffilled). This is applied identically to lag+0 and lag+1.

### 3.4 Survivorship BOUND (red-team MISSING)
The 147-name panel is *current constituents* of the 157 store — survivors. Southbound-heavy names that later delisted/were-suspended are absent, which can only *inflate* a positive long-short. We report a **survivorship-adjusted lower bound** on the top-minus-bottom quintile spread: any name that goes permanently dark (no valid print for the remainder of the sample after a cross-section it was long in) is imputed a **−100% forward return** at that cross-section (worst-case reversal-buy loss). The reported LS spread is bracketed [raw upper, survivorship-imputed lower]. Given the 2y window and mega-cap panel, we expect ~0 dark names — if so, we state the bound is *degenerate* (upper==lower) and that the true survivorship risk is *unmeasurable at this depth*, not zero.

---

## 4. Statistics (constitution §6)

Per (signal, horizon, lag) cell:
1. **Rank-IC per Friday** = Spearman(signal cross-section, forward HSI-excess) — `engine.validation.rank_ic` (≥10 joint names required).
2. **IC summary** = mean IC, IC-IR, **HAC (Newey-West) t-stat** on the IC series — `engine.validation.ic_summary` (periods_per_year=52). Overlapping 2w/4w windows serially-correlate the IC series; HAC corrects.
3. **Quintile long-short**: top-quintile − bottom-quintile EW, non-overlapping *weekly-rebalanced* net of `COST_BPS` (reuse the `scripts/residual_alpha_phase0.py` idiom); Sharpe, cumulative, and **DSR**.
4. **DSR** via `engine.validation.deflated_sharpe` at **program `n_trials = 30`** (the whole HK/CA program's config count — masterplan §6). DSR≥0.90 is the ONLY door into a scored seam. `t_eff` from `bootstrap_effective_t` where the LS return series is long enough (≥60 obs); else raw T with a stated caveat.
5. **BH-FDR within the H1 family** (`benjamini_hochberg`, α=0.10) across the primary+secondary IC p-values.
6. **Split-half sign-stability:** split the 85 Fridays into first-half / second-half; the mean IC (and LS Sharpe) must carry the **same sign** in both halves to be credible. Reported per cell.
7. **Effective-N (episode honesty):** stated as **~2 independent regimes** (block-length ≈ the whole 2024-H2 stimulus episode). The per-Friday IC count (~85) is NOT the independent-N; DSR and the verdict are read against the ~2-regime reality.

### 4.1 GO / NO-GO / KILL / ACCRUE gates (pre-stated)
| Verdict | Condition |
|---|---|
| **GO** | lag+1 rank-IC HAC t ≥ 2.0 AND DSR ≥ 0.90 AND same-sign split-half AND BH-reject — on ≥1 horizon. (Structurally near-impossible at N≈2 regimes; stated for completeness.) |
| **ACCRUE** | Sign positive and economically plausible at lag+0 and/or lag+1, but fails DSR≥0.90 or split-half or BH — i.e. *promising but under-powered*. Full re-run 2027-07. **Pre-registered expected outcome.** |
| **NO-GO** | Sign near-zero / inconsistent across horizons, OR lag+0→lag+1 shortfall erases the sign ⇒ the edge does not survive the delivery vehicle ⇒ context chip only, never a ranker. |
| **KILL** | Sign robustly *negative* at lag+1 with HAC t ≤ −2.0 (the demand-pressure mechanism refuted, not merely under-powered). |

**Implementation-shortfall reading (mandatory, non-gated):** report lag+0 IC and lag+1 IC side by side; the *shortfall* = lag+0 − lag+1 measures how much of any edge the render/next-open lag eats. If lag+0 shows a sign and lag+1 does not, the card copy must state "positioning context, not a next-morning tradable ranker."

---

## 5. Pre-registered trial list (exactly 2 gated trials in the H1 family)
| # | Signal | Horizons | Lags | Gated? |
|---|---|---|---|---|
| T1 (PRIMARY) | Δ4w own_pct | 1w/2w/4w | lag+0, lag+1 | YES |
| T2 (SECONDARY) | Δ1w own_pct | 1w/2w/4w | lag+0, lag+1 | YES |

Horizons and lags are *reported* facets of each of the 2 pre-registered signals (not separate hypotheses); BH-FDR is applied across the 2 signals' best-horizon IC p-values. Program-level DSR counts these inside the ≈30 program configs. No other signal is run. No sector-neutralization (red-team: HK has no PIT sector map; sector-neutral would leak a 2026 taxonomy — excluded by pre-registration).

## 6. Exploratory (NON-GATED) — H5 peg-liquidity interaction
Report whether the Δ4w spread is stronger in EASY peg-liquidity weeks. Regime read reuses the H5 pre-reg's live wire: `agg_balance` (HKMA aggregate balance) — high aggregate balance = easy HKD liquidity. Split Fridays into EASY (top-tercile agg_balance) vs TIGHT (bottom-tercile) and report the Δ4w mean IC in each. **Exploratory only — no verdict, no gate, no trial slot, no DSR.** If `agg_balance` is unavailable in-tree, report that and skip.

## 7. Registry
UPDATE the existing `hk-southbound-holdings-panel` entry's phase-0 note (do not duplicate) AND append one new phase-0 verdict entry `hkca-h1-southbound-holdings` at the END of the experiments array. come_back_on = 2027-07-01 (3y full-power read).

## 8. What this pre-reg CANNOT show (stated up front)
- Not a full-power test: N≈2 regimes; ACCRUE is the honest ceiling.
- Not the true Southbound universe: mega-cap 147-name panel, not all 729 names.
- Not survivorship-clean beyond the −100% dark-name bound (2y depth ⇒ likely degenerate bound).
- Not PIT-Connect-eligibility-gated: we use presence-in-holdings as the eligibility proxy (a name appears in the file only if Southbound-eligible that week), which is itself PIT-honest for *inclusion* but does not reconstruct the historical roster.
- No costs beyond COST_BPS on the LS leg; no capacity/impact modeling.
