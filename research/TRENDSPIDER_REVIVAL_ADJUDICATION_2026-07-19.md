# TrendSpider Rejected-Indicator Revival Adjudication

- Date: 2026-07-19
- Adjudicator: main-loop session (Fable), operator-ordered follow-up to
  `research/TRENDSPIDER_INDICATOR_GAP_AUDIT_AND_COMBO_RESEARCH_PLAN_2026-07-19.md` (Codex)
- Scope: re-examine every item the Codex audit rejected as `OPAQUE`, `REPAINT`,
  `DATA_BLOCKED`, or `DUPLICATE` and rule on revival, based on fresh web research
  into the published mechanics of each construction.
- Authority: research specification + display-tier build only. **No promotion,
  ranking, sizing, or entry-stack authority is granted by this document.** All
  RUL-33 entry-stack fences remain in force.

## 0. Method

Six research lanes swept independent public sources (original author
publications, StockCharts ChartSchool, MetaTrader/TradeStation docs, MQL5/
TradingView open implementations, SMC/ICT primary tutorials) for the actual
mathematics of each rejected item. No vendor code was copied; every revived
construction cites classical public mathematics. Vendor parity is `unknown`
everywhere — these are generic constructions under generic names.

## 1. Revived — first-class passports (built this wave)

| Item | Codex status | Ruling | Basis |
|---|---|---|---|
| TradingWarz Golden → **bar-structure grammar** (inside/outside bars, OBIB "coil", triple-IB) | OPAQUE | REVIVED as `engine/bar_structure_signals.py` | The bar logic is the classical inside/outside-bar canon (Raschke, Brooks et al.), independently republished in ThinkScript; only the visual packaging was branded. H/L columns only. |
| TheSTRAT patterns (Rob Smith) | OTHER_LAB (`pattern_structure`) | REVIVED into the same module: 2U/2D scenario taxonomy + 2-1-2 / 3-1-2 continuation & reversal triggers | Fully public methodology (strat.trading and many independents). Pure H/L comparisons; break-bar triggers are causal at bar close. |
| Williams Fractals | REPAINT | REVIVED as `engine/fractal_pivot_signals.py` with a hard 2-bar confirmation lag: every event fires on the confirmation bar (`actionable_lag=2`) | The repaint objection dissolves once the event is bound to the bar where the pattern becomes knowable (i+2). Formula fully public (Bill Williams 1995, MT5 docs). |
| Zig Zag → **swing structure state** (HH/HL vs LH/LL) | REPAINT | REVIVED in the same module, built from *confirmed* fractal pivots only | The causal variant uses only pivots already confirmed as of each bar; the truncation-prefix test is mandatory in its test suite. |
| Elder Ray (Bull/Bear Power) | DUPLICATE (`price_pressure`) | REVIVED in `engine/trend_strength_signals.py` | H/L decomposition around EMA(13) is a distinct mechanism (nothing local reads high/low extension vs consensus value); HLC only; Elder 1993, fully public. |

## 2. Revived — challenger-only (sandbox tournament; excluded from main Combo search)

| Item | Codex status | Ruling | Basis / fence |
|---|---|---|---|
| QQE | DUPLICATE (`rsi_composite`) | Challenger in `engine/challenger_signals.py` | The double-Wilder-smoothed ATR-of-RSI trailing band is a genuinely distinct construction (TradeStation docs + open MQL sources give the full algorithm). Must beat the RSI/StochRSI cluster representative to advance. |
| Ultimate Oscillator | DUPLICATE (`multi_horizon_momentum`) | Challenger; `entry_stack_blocked=true` (named in RUL-33-OSCSPECIES) | Buying-pressure/true-range multi-window blend is HLC-computable and distinct from plain ROC blends; still momentum-family, so tournament only. |
| Fisher Transform | DUPLICATE (`normalized_momentum`) | Challenger | arctanh-Gaussianized midpoint is a unique distribution shaping (Ehlers primary paper is public); must beat simpler normalized-range parents. |
| Schaff Trend Cycle | DUPLICATE (`macd_cycle`) | Challenger | Double-stochastic of MACD; only advances if it beats the MACD cluster representative. |
| Fair Value Gap (generic 3-candle imbalance) | (§5.9 gap fence) | Challenger + display-tier only, **fresh prereg required before any authority claim** | Distinct construction from the falsified PM3 unfilled-overhead-gap map (H/L 3-bar imbalance vs gap-to-open map). The PM3 kill stands untouched; this opens no promotion door. Detection is causal at bar close; H/L only. |

## 3. Stays dead (revival declined)

| Item | Reason |
|---|---|
| Chande Momentum Oscillator | Algebraically `2·RSI − 100` (raw-sum variant). True duplicate of the RSI cluster. |
| Average Daily Range | ATR minus the gap adjustment; owned by the nATR/ATR family. |
| Swenlin PMO / Departure-chart relatives | Double-smoothed ROC — MACD-family skin. |
| Dots (IntroMoto) | Multi-period RSI OB/OS markers; owned by rsi_bands. Exact filter undisclosed. |
| Relative Trend Index (Zeiierman) | Formula public, but it is a stochastic normalization of BB extremes — same normalized-position family as %B/StochRSI. Not worth a QA slot now; may enter a future family tournament. |
| GoNoGo Trend/Oscillator | Vendor weights undisclosed; a generic rebuild would be a *fused* multi-factor composite, which the confluence program forbids as a leg (fused evidence masquerading as one signal; cf. LH-U2 kill of fused verdicts). Components are already individually owned. |
| TW Pivot | Nothing disclosed (`NONE`); a guessed rebuild would be an invention adjacent to DeMark-style countdowns, which RUL-33-OSCSPECIES declined. `blocked_proprietary` stands. |
| Wick Sniper | Disclosed skeleton = Keltner/ATR-band variant (owned); band formula proprietary. |
| Wick Oscillator / Pressure-Response | Wick decomposition requires `open` (upper wick = H − max(O,C)); US store has no open column. Approximating wicks without the body boundary changes the construction. Blocked. |
| Order Blocks / OB Proximity | Candle direction needs `open`; zone/level tooling belongs to the levels/anchor lane that carries standing kills (AVWAP fence); TrendSpider sensitivity defaults undisclosed. Deferred, not reopened. |
| Balance of Power, Relative Vigor Index, Accumulative Swing Index | Formulas fully public but all require `open`, which `data/stocks/` does not carry (confirmed: columns are close/high/low/volume). |
| Fractal Trendlines / ZigZag supply-demand zones | Generic algorithms exist but are level/zone tools with weak event grammar for this lab; deferred to a future levels study. |

## 4. Data note for future revival

`data/china_stocks/` and `data/hk_stocks/` **do** carry `open` (5-column
schema). If the US collector ever adds `open`, the blocked open-dependent
passports (BOP, RVI, ASI, wick family, order blocks) become buildable; the CN/HK
lanes could pilot them sooner. That is a separate data-lane decision, not
authorized here.

## 5. Standing fences restated

- `entry_stack_blocked=true` travels in catalog metadata for every RUL-33-named
  construction (KAMA/ER, CHOP/VHF, Connors RSI, MFI, Aroon, SuperTrend, TSI/SMI,
  Coppock, KST, Ultimate Oscillator, Ichimoku legacy signals). Technical Lab
  results cannot route these into A3, buy scores, or Neural Web authority
  without a new adjudication that names and overturns the ruling.
- Challenger-only signals are excluded from the main Combo search by catalog
  flag; they advance only by beating their family representative under the
  Combo v2 gauntlet.
- Nothing in this wave may use the word "validated" in any user-facing string.
