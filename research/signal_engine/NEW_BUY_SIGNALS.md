# New Buy Signals — Skeptically Vetted Candidate Shortlist

*Deliverable: `research/signal_engine/NEW_BUY_SIGNALS.md` — brainstorm/propose stage. Nothing here is validated. Everything ships only after the held-out diagnostic in §6.*

## 1. Framing (read this first; do not misread the intent)

This is a **DISPLAY-ONLY entry-quality / drawdown-risk signal engine**. It is **not** a standalone algo, **not** a stock-picker, and **not** a return-alpha engine. Its only customers are (a) the Mastermind / Opus brain, which consumes these flags as **inputs**, and (b) the owner, who reviews them on a chart. The binding rules live in [`CHARTER.md`](./CHARTER.md) — read it before touching anything below.

The single validated **KEEPER** we are augmenting is the faithful port of the owner's **MACD-RSI × StochRSI** confluence on the **3-day (3D)** frame, plus its generalizing **buy-filter** (confluence buy + reclaim-and-hold + bearish-divergence veto + 200-day-MA soft bar-raiser). On 110 held-out US names it took avg max drawdown from **-23.7% → -15.5%, shallower on 84% of names**. Critically: it **reduces drawdown; it does not add return.** That is the bar.

Every candidate below is proposed as an **additional orthogonal input alongside** that keeper — a quality bar-raiser, never a hard gate, mirroring exactly how the 200MA is used. Value is measured in **drawdown reduction, shake-out avoidance, smaller avg loss, better entry efficiency / per-trade expectancy** — never "beats buy-and-hold." **Generalization on held-out names is the only verdict.** In-sample beauty is worthless.

## 2. How to read this

A candidate has to clear **two** independent bars to graduate from "context chip" to "shipped scored leg":

1. **Orthogonality.** It must add information the existing stack does not already carry. The existing stack is **close-only**: RSI-MACD momentum, StochRSI oscillator, 200MA trend, price/oscillator bearish-divergence, reclaim-and-hold. A near-duplicate of any of those — or of an already-shipped display engine (`engine/extension.py` ext_z, `engine/spotlight.py` sector-RS tilt, the `macro-risk-overlay` sector-beta tax, `engine/velocity.py` efficiency ratio) — is worthless even if it is "orthogonal to the confluence leaf." We measure this empirically (phi / Cramér's V / Spearman at the actual buy bars), not by argument.
2. **Held-out generalization on the charter metric.** Conditional on a confluence buy the keeper already takes, the new flag must materially reduce **forward max-drawdown / shake-out rate** on held-out names, **after residualizing on the gates already present** (200MA, weekly-trend, bearish-div). If the gap vanishes once you hold the existing gates fixed, it is redundant and stays context-only. The filter was tuned on Tencent/BABA, so **all 110 US names are held out.**

**Repo-killed ideas we refuse to re-pitch naively** (re-proposing any of these without a materially different construction *and* fresh held-out evidence is an automatic kill):

- **RVOL "volume confirms momentum"** — NO-GO (clean uplift negative, failed FDR). A *drawdown* framing of volume may differ from that *return/IC* study, but the burden of proof is on the new framing to show it.
- **FINRA daily short-volume squeeze** — NO-GO.
- **Regime / exit-ROUTING classifier** (efficiency + vol axes) — KILLED. Great on ~7 names, no better than a fixed exit on 105 held-out. Lesson: **drawdown control comes from filtering bad ENTRIES, not clever exit-routing.** A one-way entry-confidence read is a *different* thing, but it lives in the same feature space and inherits a high burden.
- **IBD constructive-base / pivot-proximity scan** — NO-GO (anti-predictive, FDR-surviving negative IC).
- **Narrative / cross-sectional momentum rank-IC ≈ 0** — only the trend-gate / drawdown-control survived.
- **Charter folklore to avoid outright:** Hurst exponent, Choppiness Index thresholds, ADX as a filter.

> **Honest status of this document:** every candidate's adversarial verdict came back **demote-to-context** or **kill** at the brainstorm stage. **Zero candidates are "survive-and-ship."** What follows therefore ranks the *least-dead* candidates — the ones whose orthogonal axis is real and whose held-out drawdown test is worth actually running — above the ones that are folklore, redundant, or already empirically refuted. "Survivor" below means **"survives to a fundable held-out diagnostic,"** not "validated."

## 3. The skeptically-vetted shortlist

| Candidate | Axis | What it detects | Repo data available | Orthogonal to existing stack? | Verdict | Why |
|---|---|---|---|---|---|---|
| **ATR%-Percentile Compression Gate (3D)** | volatility (H/L range) | Entry into a compressed intraday-range regime vs an expanded one | data/stocks H/L/C (unused); `expanding_percentile` | **Yes** vs confluence (uses unused H/L); weaker vs ext_z (corr risk) | **Context → top diagnostic** | Cleanest charter-blessed primitive (ATR%-pctile); but VCP pattern is folklore and the cited gradient is unverified/in-sample — must survive *within* the trend-gated cohort |
| **Volume Dry-Up Pullback Confirmer (VDU)** | volume (pullback bars) | Price retraces into the buy on below-30th-pctile volume = benign low supply | data/stocks close+vol (post-2000, ≥200 bars); `volume_signature` | **Yes** — first leg touching volume on *pullback* bars | **Context → diagnostic** | Genuinely new volume location/target vs the RVOL kill, but practitioner folklore base, misapplied cite, and 4-5 latent DOF violate tiny-spec |
| **HAR-Vol Regime Percentile Gate** | volatility (dispersion) | Entry in low-vol calm (≤35th) vs elevated/rising vol (≥70th) | `vol_forecast.har_vol/vol_regime` (built) | Dimension real; *information* plausibly redundant with 200MA/weekly | **Context → diagnostic** | HAR forecasting is OOS-validated, but vol-MANAGING entries OOS is not (Cederburg et al. 2020); widest-DD windows are the below-200/weekly-down windows already vetoed |
| **HAR-Vol Shock Residual Veto** | volatility (vol surprise) | Buy fires mid-spike (realized ≫ HAR forecast) vs after it resolves | `vol_forecast` (spread = one-liner) | **Yes** — vol-surprise axis genuinely new per-name | **Context** | Conceptually distinct, but confluence buys fire post-pullback so the buy population under-samples mid-spike entries → marginal lift likely ~nil; daily/3D alignment hazard |
| **Kaufman ER Entry-Quality Gate** | trend quality (path geometry) | Choppy vs clean directional path into the buy | `velocity.efficiency_ratio` (built) | Yes vs live stack; **duplicate of the KILLED router's eff axis** | **Context (high kill risk)** | The repo already tested ER(10) as an entry-conditioning lever inside the killed router and it failed OOS; re-skinning doesn't change the input/panel/metric |
| **Rolling R² Trend-Clarity Bar-Raiser** | trend quality (linearity) | Clean linear advance vs noisy zig-zag above 200MA | `indicators.rolling_slope` (R² = 2-line add) | Yes vs oscillators; **~0.5 corr w/ Kaufman ER** | **Context** | Only OOS evidence (Cai/Li/Keasey 2024) is a *return/momentum* finding — wrong target; redundant with ER + router resemblance |
| **Extension Parabolic Veto (ext_z≥2)** | structure | Buy into the parabolic crash-risk cohort | `extension.extension_signals` (shipped) | **No** — overlaps RSI<65 + ext_z (already display) | **Context (near-null)** | Re-proposal of a shipped flag; at actual entry points fwd-DD identical (-8.1% vs -7.6%); only 0.26% of buys uniquely vetoed; -94% headline was n=2 B&H artifact |
| **Bar-Overlap / Directional Coherence** | trend quality (H/L stacking) | Stacking (trend) vs heavy-overlap (chop) bars | data/stocks H/L (unused) | Collinear (~0.4-0.5) with charter-blessed ER | **Context (kill-leaning)** | Reinvented Choppiness Index (charter-flagged folklore); same axis ER already owns; base-scanner-family kill precedent |
| **OBV Trend-Divergence Veto** | volume | OBV slope falling while price higher-high | `volume_signature._obv_slope` (built) | **No** — admitted analog of existing bearish-div veto | **Context (kill-leaning)** | OBV is price-driven → fires on overlapping bars; misapplied Lee-Swaminathan cite; lives in shadow of RVOL kill |
| **ANSW + PDP Stop/Pullback Geometry** | structure (pivots) | Wide vs tight implied stop; healthy vs broken pullback depth | data/stocks H/L/C; new fractal helper | Distinct geometry; ext_z correlated in spirit | **Context (ANSW leg drop)** | ANSW R-multiple language is a return-hunt tell; **repaint risk** (Williams fractal confirmed +2 bars, mixed with live close) |
| **Swing Failure Recovery (SFR)** | structure (sweep-recover) | Within-bar pierce below swing low that recovers same 3D bar | data/stocks H/L; fractal helper | Touches unused H/L; correlated w/ StochRSI oversold-reclaim | **Context (kill-leaning)** | **Repaint risk** + rare on 3D bars (single-digit n/name = the "great on 7 names" trap); win-rate cite is a return smuggle |
| **NH-NL + McClellan Breadth Gate** | breadth regime | Market internals deteriorating at the buy bar | data/breadth; `advanced_breadth` (built) | Echoes 200MA/weekly-down (~37% residual only) | **Context (low value)** | Blunt market-direction switch (fires 52% of all days); single market-wide series → date-clustered, near-zero effective N (router trap) |
| **Sector ETF Trend Alignment** | trend quality / context | Stock's GICS sector ETF in RS breakdown vs SPY | data/yahoo SPDRs; PIT membership | **No** — duplicates macro-risk-overlay B-1 + spotlight sector-RS | **Context (redundant)** | Re-counts info brain already has; external cites are sector-momentum return-alpha (repo found rank-IC≈0); PIT/repaint hazard |
| **HLMS Higher-Low Structure** | trend quality (pivots) | Latest confirmed swing low > prior swing low | data/stocks; existing `swing_points` | **No** — price-half of existing divergence primitive | **KILL** | `divergence_at` already computes the same consecutive-swing-low comparison; adds no new geometry; repaint risk; "shared helper" doesn't exist |
| **UVBR Up/Down Volume Balance** | volume | 42-bar up/down-vol balance = accumulation regime | `volume_signature` (built) | New axis but carries no signal | **KILL** | Failed its own pre-committed kill test: -11.9% vs -11.8% fwd-DD, t=-0.76 p=0.45, corr≈0, tail sign-flips. Same graveyard as RVOL/short-vol |
| **COT Net-Spec Percentile Extremes** | breadth regime | ES-futures leveraged-fund positioning at extremes | data/cot/cot_es_spx.parquet | Orthogonal construction but empirically uninformative | **KILL** | Probe run: crowded (≥90th) -11.4% vs mid -11.6% (NOT deeper); Spearman = **-0.06, wrong-signed**; one weekly market-wide series → effective N ≈ handful of weeks; +5d publication-lag lookahead trap |

## 4. Survivor subsections (survivor = "worth a held-out diagnostic," not "validated")

### 4.1 ATR%-Percentile Compression Gate (3D, high/low dimension) — *axis: volatility*

- **What it detects.** Whether the confluence buy fires into a **compressed intraday-range regime** (ATR% at a multi-month-low percentile on the 3D frame) versus an expanded-range environment where adverse excursion is widest.
- **No-lookahead / no-repaint mechanism (tiny spec).** Resample daily H/L/C to 3D (max/min/last). TrueRange = max(high−low, |high−prevclose|, |low−prevclose|); Wilder **ATR(14)**; **ATR% = ATR14/close** (scale-free). `expanding_percentile(ATR%, min_obs=252)` — strictly forward-only. At the buy: **≤30th pctile = PASS** (compressed, confirm as usual); **≥65th = caution flag** (chasing range expansion). **One free parameter** (ATR period = 14, standard); percentile, not absolute threshold.
- **Repo reuse.** `data/stocks/*.parquet` H/L/C (present for all 114 names back to 1980 — **entirely unused** by the close-only signal engine); `engine/indicators.expanding_percentile`. New work is a trivial 3D-resampled ATR function. ATR%-percentile is a **charter-blessed primitive.**
- **Orthogonality argument & probe numbers.** Orthogonal to the **confluence leaf** (all close-only). The cited Phase-0 (50 names, 7000+ entries: low-ATR entries −3.0% vs high-ATR −4.6% max fwd-DD, monotone across tertiles) is **unverified, pooled, and almost certainly in-sample** — do not lean on it. The honest concern is overlap with the already-shipped `extension.ext_z`: both proxy "is this name agitated," so orthogonality vs the **full display stack** is weaker than vs the leaf.
- **Overfitting / lookahead risk + strongest objection.** Lookahead-safe by construction (Wilder ATR + expanding percentile). **Strongest objection:** the academic support is for volatility *clustering/persistence* (Cont, Mandelbrot), **not** the VCP entry pattern (Minervini practitioner folklore, no OOS test) — the candidate quietly borrows the former's credibility for the latter. Trends are low-vol, so the **200MA + weekly-trend gates may already absorb most of the low-ATR signal.** Survives only if the gradient holds *within* the (above200 & weekly_bull) cohort on held-out names **and** |corr(ATR%-pctile, ext_z)| < ~0.6.

### 4.2 Volume Dry-Up Pullback Confirmer (VDU) — *axis: volume*

- **What it detects.** Whether price retraces **into** the 3D buy on below-30th-percentile volume — distinguishing benign low-supply consolidation from distribution, flagging **lower shake-out risk.**
- **No-lookahead / no-repaint mechanism.** On the 3D series: for the 1–3 consecutive down-bars immediately preceding the confluence buy, take the **minimum bar volume** and compare to that bar's **strictly-prior trailing-60-bar volume distribution**. **VDU = True** when that minimum < **30th percentile**. All percentile anchors computed on data strictly before bar *i* (forward-only). **Restrict to post-2000 bars; require ≥200 non-zero volume bars** before activating.
- **Repo reuse.** `data/stocks/*.parquet` close+vol (109/114 names have >1000 non-zero bars); `engine/volume_signature.py` rolling-percentile infrastructure. Reads volume **during the retracement** — a location no existing leg touches.
- **Orthogonality argument.** The entire existing stack is close-only; VDU is the **first leg touching volume on pullback bars.** Distinct from the RVOL kill on **both** location (pullback vs rally/breakout bar) and target (drawdown vs return-IC) — the charter explicitly allows this distinction. Partial overlap with `volume_signature` (basket-level, 42d return window, untested) but not a true duplicate.
- **Overfitting / lookahead risk + strongest objection.** **Strongest objection:** the mechanism is grounded almost entirely in **Minervini VCP practitioner folklore** (survivorship-contaminated marketing), and the one peer-reviewed cite (Lee & Swaminathan 2000) is **misapplied** — it studies multi-year cross-sectional turnover, not a single-pullback-bar percentile. The "one free parameter" claim is **false**: 30th pctile, 60-bar window, 20-bar median, "1-3 down-bars" span, and the post-2000 cutoff are ~4-5 latent researcher DOF → tiny-spec violation + multiple-testing inflation. Volume is thin/backfilled pre-2000 (the repo's own caveat), shrinking the clean held-out panel. Ship only if VDU=True buys show shallower fwd-DD *and* lower whipsaw on a clear **majority** of held-out names after FDR/Bonferroni, with a fixed (no per-name-tuned) percentile.

### 4.3 HAR-Vol Regime Percentile Entry Gate — *axis: volatility (dispersion)*

- **What it detects.** Whether the entry occurs in a **low-vol calm window** (HAR-RV ≤35th pctile of own trailing history) vs an **elevated/rising** vol environment (≥70th & 5-bar slope > 0), gating entries where expected adverse excursion is widest.
- **No-lookahead / no-repaint mechanism.** `vol_forecast.har_vol(close)` (RV over 2/5/22/66-bar lags, literature-fixed) → `vol_regime()` expanding 252-bar percentile. At the 3D buy bar: **≤35th → full-weight; ≥70th & rising → veto; ≥70th & peaking/falling → allow with note.** Optionally read SPY HAR-vol for the ambient regime. **Zero tunable parameters** (HAR lags fixed; 35/70 are round-number pre-registrations). Wire-up only.
- **Repo reuse.** `engine/vol_forecast.py` (`har_vol`, `vol_regime` — built, already called by `engine/anticipation.py`); `data/yahoo/SPY.parquet`.
- **Orthogonality argument.** RSI-MACD / StochRSI / 200MA / bearish-div / reclaim-and-hold are all **first-moment/direction**; HAR-RV is a **second-moment (dispersion)** axis genuinely absent from the stack. The *dimension* is real.
- **Overfitting / lookahead risk + strongest objection.** **Strongest objection (information-redundancy + citation gap):** the Moreira-Muir (2017) citation is continuous vol-*scaling* of diversified factor weights for **Sharpe** (a return result), not a binary veto on single-name buys; and the OOS rebuttal **Cederburg/DeMiguel/Nogales (2020, JFE)** shows vol-managed strategies largely **fail OOS** for everything except the market factor. "Positive OOS R²" holds for vol *forecasting* but does **not** transfer to "vol-gating entries reduces single-name drawdown OOS." Worse, the widest-drawdown windows are exactly the **below-200MA / weekly-down** windows the existing buy-filter already vetoes — so the gate may add little conditional information over the trend gates, which is precisely how the prior regime-router died. Ship only if, conditional on buy-filter = take **and** above200 = True, the ≥70th-&-rising bucket shows materially deeper fwd-DD on held-out names.

## 5. Demoted to context / killed — honest one-liners

**Demoted to context (orthogonal axis but unproven marginal value, run only if cheap):**

- **HAR-Vol Shock Residual Veto** — vol-surprise axis is genuinely new, but confluence buys fire *post*-pullback so they already under-sample mid-spike entries; marginal lift likely ~nil. Watch the daily-vs-3D alignment (read the daily value as-of the 3D close, no peeking).
- **Kaufman ER Entry Gate** — the repo **already tested ER(10) as an entry-conditioning lever** inside the killed regime-router and it failed OOS; re-skinning as a one-sided bar-raiser doesn't change the input/panel/metric. High kill risk.
- **Rolling R² Trend-Clarity** — only OOS evidence (Cai/Li/Keasey 2024) validates R² as a *return/momentum* enhancer (wrong target); ~0.5 redundant with the already-shipped Kaufman ER; router-resemblance.
- **Extension Parabolic Veto (ext_z≥2)** — re-proposal of a **shipped** display flag whose own validation the repo flagged as basket-level null; at actual entry points fwd-DD is identical (-8.1% vs -7.6%), only **0.26%** of buys are uniquely vetoed, and the radioactive -94% headline came from an **n=2** B&H cohort.
- **Bar-Overlap Coherence** — a reinvented **Choppiness Index** (charter-flagged folklore) targeting the exact axis the charter-blessed ER already owns (~0.4-0.5 corr); base-scanner-family kill precedent.
- **OBV Trend-Divergence Veto** — self-admitted **analog of the existing bearish-div veto**; OBV is price-driven so it fires on overlapping bars; misapplied Lee-Swaminathan cite; shadow of the RVOL kill.
- **ANSW + PDP Stop/Pullback Geometry** — drop the **ANSW** leg (R-multiple "good R/bad R" language is a return-hunt tell + implies exit-routing the keeper avoids); the **PDP** veto could survive *only* as a strictly lag-2-confirmed, no-repaint read. As specified it mixes a confirmed swing high with the live close → repaint.
- **SFR Sweep-and-Recover** — repaint risk (Williams fractal confirms +2 bars; spec never states the lag) **plus** single-digit events/name on 3D bars (the "great on 7 names" trap); "55-65% win rate" cite is a return smuggle; correlated with a StochRSI oversold-reclaim the oscillator already sees.
- **NH-NL + McClellan Breadth Gate** — fires on **52% of all calendar days** (a market-direction switch, not a precision entry filter); one market-wide series → fully date-clustered, near-zero effective N (the router's exact failure mode); breadth is coincident-by-construction.
- **Sector ETF Trend Alignment** — duplicates **two** already-shipped seams (macro-risk-overlay gate B-1 + spotlight sector-RS tilt); every external cite is sector-momentum **return-alpha** (repo found rank-IC≈0); PIT-membership & repaint hazards.

**Killed:**

- **HLMS Higher-Low Structure** — the core computation (latest confirmed swing low > prior swing low) is **already implemented** as the price half of `divergence_at` on the same 5-bar fractal; adds no new geometry; repaint risk; the "shared pivot helper from ANSW/SFR" **does not exist** in the repo.
- **UVBR Up/Down Volume Balance** — **failed its own pre-committed kill test** on 11,955 real buy events: -11.9% vs -11.8% fwd-DD, t=-0.76, p=0.45, corr≈0, and the extreme tail **sign-flips** (distribution-biased marginally *shallower*). Same graveyard as RVOL/short-vol.
- **COT Net-Spec Extremes** — decisive probe (9,130 buys): crowded (≥90th) -11.4% vs mid -11.6% (**not** deeper), Spearman(cot_pct, fwd-DD) = **-0.06 (wrong-signed)**; one weekly market-wide series → effective N ≈ a handful of distinct weeks; the stored parquet is dated to the Tuesday report not Friday publish → a **+5d publication-lag lookahead trap**.

## 6. Top 2-3 picks — concrete spec + held-out diagnostic plan

> All three emit a **soft quality bar-raiser**, never a hard veto — exactly how the 200MA is used in `engine/signal_quality.py` (`signal_frame` / `analyze`, helpers `_swing_highs`, `_bear_div`). The flag adjusts the confidence tier the brain consumes; it never blocks an entry outright.

### Pick #1 — ATR%-Percentile Compression Gate (highest priority: charter-blessed, zero-volume-quality dependency, cleanest spec)

**Inputs:** `data/stocks/*.parquet` daily H/L/C, all 114 names.
**Computation (exact):**
1. Resample daily → 3D (high=max, low=min, close=last).
2. `TR = max(high−low, |high−prevclose|, |low−prevclose|)`; `ATR14 = Wilder(TR, 14)`; `ATRpct = ATR14 / close`.
3. `atr_pctile = expanding_percentile(ATRpct, min_obs=252)` (forward-only).

**Marker emitted (per §7 contract):** at a confluence buy the keeper would take — `atr_pctile ≤ 30 → quality_boost = +1` (compressed, confirm as usual); `atr_pctile ≥ 65 → quality_caution = -1` (range-expansion). Mid-band → no change. Display chip only.

**Diagnostic / backtest plan (charter metrics only — NO beat-B&H):**
- **Trade-level simulation** of the keeper exactly as traded (enter / exit / cut / rebuy, `REV_BARS` anti-shakeout intact) across **all 110 held-out US names** (the filter was tuned on Tencent/BABA only).
- Split keeper-**take** buys by `atr_pctile` **tertile**. Report per-tertile: **avg & p10 forward max-drawdown** (10/20/40 3D bars), **shake-out rate** (price round-trips to entry / cut-loss fires within `REV_BARS`), **avg-loss size**, **entry efficiency**, **per-trade expectancy**.
- **Incremental test (decisive):** repeat the split *within* the `(above200 & weekly_bull)` cohort. The gate earns its keep only if the low-ATR tertile is materially shallower **inside the already-trend-gated set.**
- **Redundancy guard:** Spearman(`atr_pctile`, `extension.ext_z`) at the buy bars; if |corr| ≥ ~0.6 it is re-expressing the shipped extension lens → downgrade to display-only.
- **Pre-committed kill rule:** percentiles fixed in advance (30/65, no per-name tuning); confirmed/forward-only series only. **If the ATR-gated buy-filter does not beat the simpler keeper baseline on held-out forward drawdown on a majority of names, ship the simpler baseline.**

### Pick #2 — Volume Dry-Up Pullback Confirmer (VDU) (highest *orthogonality* — only true volume axis untouched by every prior kill)

**Inputs:** `data/stocks/*.parquet` close+volume, **post-2000, names with ≥200 non-zero volume bars** (~109/114).
**Computation (exact):** at a keeper buy bar, over the 1-3 consecutive down-bars immediately preceding it, `vdu = min(down_bar_volume) < pctile30(strictly-prior trailing-60-bar volume)`.
**Marker emitted:** `vdu = True → quality_boost = +1` (benign low-supply pullback, lower shake-out risk). Absence is **neutral, never a veto.** Display chip only.

**Diagnostic / backtest plan:**
- **Orthogonality first:** 2×2 contingency / **phi** of VDU vs the keeper take/block label; point-biserial of VDU vs RSI-MACD hist, StochRSI k, rsi14, above200 at the buy bar. If |phi| > ~0.3 it is re-encoding the existing filter → demote.
- **Conditional drawdown:** within keeper-**take** buys only, compare forward 10/20-bar max-DD, shake-out rate, and avg-loss for VDU=True vs False, on **held-out names**.
- **Multiple-testing discipline:** because VDU carries ~4-5 latent DOF, **fix the spec (30th pctile / 60-bar / 20-bar median / 1-3 down-bars / post-2000) before any run** and apply **FDR/Bonferroni** across names.
- **Pre-committed kill rule:** ship only if VDU=True buys are shallower **and** lower-whipsaw on a clear **majority** of held-out names (matching the 84% / −23.7%→−15.5% bar the keeper cleared). Otherwise it stays a brain context input, not a scored leg — **and if it fails, ship the simpler baseline.**

### Pick #3 — HAR-Vol Regime Percentile Gate (run only if cheap; lowest marginal-value confidence of the three)

**Inputs:** per-name 3D close + `data/yahoo/SPY.parquet`.
**Computation (exact):** `vol_pctile = vol_forecast.vol_regime(close, 252)`; `slope = vol_pctile − vol_pctile.shift(5)`.
**Marker emitted:** `vol_pctile ≤ 35 → quality_boost = +1`; `vol_pctile ≥ 70 & slope > 0 → quality_caution = -1`; `≥70 & slope ≤ 0 → neutral note`. Display chip only.

**Diagnostic / backtest plan:**
- **Raw-redundancy cross-tab first:** `vol_pctile` bucket (≤35 / 35-70 / ≥70) vs `above200` and `weekly_bull` booleans, to quantify how much the gate just re-expresses the trend gates.
- **Conditional drawdown:** conditional on keeper-**take** AND `above200 = True`, compare forward max-DD for `≤35` vs `≥70 & rising` on **held-out names**, with a **block/date-clustered bootstrap CI** (vol regime is autocorrelated and partly market-wide).
- **Pre-committed kill rule:** thresholds (35/70) fixed in advance. If the elevated-vol deepening **vanishes once the 200MA/weekly state is held fixed**, it adds nothing → context-only. **Lean on the drawdown framing, never the Moreira-Muir alpha framing.** If it doesn't beat the baseline on held-out drawdown, ship the baseline.

## 7. Tripwire check (charter §4)

- **No beat-buy-and-hold anywhere.** Every metric in §6 is drawdown reduction / shake-out rate / avg-loss / entry efficiency / per-trade expectancy. ✅
- **Contemporaneous detection, no catalyst prediction.** ATR%, HAR-RV, and pullback-volume are all read *at* the buy bar from past data; none forecast a future event. ✅
- **No-lookahead / no-repaint / percentiles / tiny spec.** ATR% and HAR-vol use forward-only expanding percentiles and confirmed bars; VDU uses strictly-prior trailing windows. The two repaint-prone structure candidates (HLMS, SFR) and the lookahead-prone COT leg were **killed/demoted explicitly for that reason.** Percentiles, not absolutes, throughout. ✅
- **Generalization is the only verdict.** All three picks ship **only** after the held-out, trade-level diagnostic on the 110 names, with a pre-committed "ship the simpler baseline if it doesn't beat it" kill rule. ✅
- **Orthogonality enforced empirically.** Each pick's plan opens with a redundancy probe (phi / Spearman vs the existing stack and shipped engines) before any drawdown claim. ✅

**Status:** brainstorm/propose only. **Nothing here is validated.** No candidate currently graduates past "context chip"; the three picks are the ones whose held-out diagnostic is worth funding next.
