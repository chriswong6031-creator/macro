# Rate & Inflation Transmission

*How the interest-rate / rate-expectations / inflation (CPI, core PCE) state propagates
— first, second and third order — into every asset class we track. A display-only leaf,
calibrated like the bond-health legs, never scored.*

## Why

The dashboard already SCORES the validated rate/inflation legs that carry forward
content (breakeven direction + TIPS-nominal momentum in the inflation axis; real yields
for commodities/BTC; the term-premium-adjusted curve in recession-risk). What was
missing was (1) the **actual inflation prints** — headline & core CPI, headline & core
PCE (the FOMC's 2% target gauge), PPI, ECI wages — only the Atlanta/Cleveland model
*nowcasts* and market breakevens were ingested; and (2) a single place that traces the
**cause → first/second/third-order → per-asset headwind/tailwind** chain with honest,
measured coefficients and conditional scenarios.

## Data added (all free / keyless FRED, point-in-time vintaged)

| series | column | note |
|---|---|---|
| CPIAUCSL / CPILFESL | headline_cpi / core_cpi | the actual CPI prints (YoY + 3m-ann derived) |
| PCEPI / PCEPILFE | headline_pce / core_pce | **core PCE = the Fed's 2% target** |
| PPIFIS / PPIFES | ppi_final_demand / ppi_core | pipeline / margin pressure |
| ECIALLCIV / ECIWAG | eci_comp / eci_wages | wage inflation (quarterly) |
| CUSR0000SASLE / CUSR0000SAH1 | cpi_core_services / cpi_shelter | the sticky-services vs lagging-shelter debate |
| EXPINF1YR/5YR/10YR | infl_exp_1y/5y/10y | Cleveland MODEL expectations (the market/survey/model triangle) |

All revision-prone releases are added to the ALFRED vintage matrix
(`collectors/fred.py:DEFAULT_VINTAGE_SERIES`) so point-in-time backtests read what was
knowable. The Cleveland EXPINF curve is a model that re-revises its whole history (like
NFCI), so it is deliberately excluded from the bounded initial-release matrix.

## Engine (`engine/rate_inflation_transmission.py`) — display-only leaf

A leaf that imports nothing from the scoring core and is imported by nothing in it. It
reads the causal feature frame + the MEASURED coefficient matrix and emits:

- **State** — rates (real-10y level/percentile/speed, curve, policy gap; regime +
  direction), inflation (core PCE/CPI/PPI/ECI, vs-2%-target, re-acceleration), and the
  expectations triangle (breakevens vs Cleveland model vs UMich survey; anchoring read).
- **Inflation decomposition** — headline−core, core-services vs shelter, PCE−CPI, and
  realized core CPI vs the 10y breakeven the market prices.
- **Per-asset headwind/tailwind** — for each asset, the sum of every *active* driver's
  current extension × its measured forward IC for that asset. Only the **change / gap**
  drivers feed the live read; the raw **level** drivers are excluded (their forward-return
  IC partly reflects spurious co-trend, and `be10y` level is mechanically collinear with
  the already-scored tips-nominal leg — VIF flags it at 300k+).
- **Transmission chains** — four causal mechanisms (real-rate, sticky-inflation,
  policy-easing, expectations), each laid out 1st→2nd→3rd order and annotated with the
  live measured cells + whether the trigger is currently active.
- **Conditional scenarios** — per-asset implied 63d moves under a rate/inflation shock,
  using the MEASURED **contemporaneous** beta (asset 63d return vs same-window driver
  change). Illustrative & regime-dependent — never a forecast.

## Calibration (`scripts/calibrate_rate_inflation.py`)

Mirrors `calibrate_bonds.py`. Two jobs, both leakage-free (drivers are causal; targets
are strictly forward; split at 2015 with a forward-window embargo):

1. **Transmission matrix** — signed split-half Spearman IC of each driver vs each
   asset's forward 63d return → the per-cell coefficient + CONFIRMED/DIRECTIONAL/CONTEXT/
   INVERTED verdict + a contemporaneous OLS beta for the scenarios.
2. **Scored-leg gate** — each rate/inflation RISK driver (as STRESS) vs the forward 63d
   S&P drawdown, the *same* bar the bond-health legs pass: sign-stable in full + both
   purged halves, |IC|≥0.10, the high-stress tercile's P(≥10% drawdown) above base with a
   block-bootstrap CI that clears it, AND purged-CV sign robustness. Each is also run
   through the Clark-West / OOS-R² return-forecast bar.

### Result (2026-06): NO leg is scored-eligible — and that is the honest finding

| leg | verdict | IC dd (full/pre/post) | purged-CV robust | OOS-R² |
|---|---|---|:--:|--:|
| real-rate SPEED (real10y_chg63) | DIRECTIONAL | 0.139 / 0.052 / 0.222 | ✗ | −0.11 |
| nominal-rate speed | DIRECTIONAL | 0.095 / 0.068 / 0.208 | ✗ | −0.12 |
| inflation re-accel | DIRECTIONAL | 0.053 / 0.049 / 0.073 | ✗ | −0.13 |
| core-PCE-vs-target gap | DIRECTIONAL | 0.042 / 0.009 / 0.130 | ✗ | −0.31 |
| real-rate LEVEL | CONTEXT | 0.047 / 0.053 / 0.004 | — | −0.17 |
| TP-adjusted curve | CONTEXT | 0.005 / 0.010 / 0.031 | — | −0.26 |
| expectations wedge | INVERTED | −0.054 / −0.050 / −0.106 | — | −0.10 |

Real-rate *speed* is the strongest — it flags forward drawdown risk (high-tercile edge
+7.2pp, bootstrap CI [0.11, 0.30] clears the base) — but it is **regime-dependent**
(pre-2015 IC only 0.05) and fails the purged-CV sign test, so it does **not** earn a
scored MRS leg. Every driver's **OOS-R² for the LEVEL of forward returns is negative**:
rate/inflation repricing flags *risk*, not *return*. This matches the house stance
("repricing is reactive; rate-of-change beats level") — now measured, not asserted. The
config `transmission.scored_legs.*` flags default OFF; flip on only after a refresh
confirms.

## Transmission matrix highlights (CONFIRMED cells)

- **Real-rate speed** → headwind to QQQ/XLK/SPY/materials/copper/oil/small-caps, tailwind
  to TLT. Textbook discount-rate transmission.
- **Breakeven / 5y5y level** → headwind to long-duration growth (QQQ/XLK), copper, FXI.
- **Sticky core-PCE gap** → broad equity headwind, worst for small caps & defensives'
  relative-favoured flip.
- **TP-adjusted curve** → TLT tailwind, financials headwind.
- **Expectations wedge (unanchoring)** → gold headwind, dollar tailwind in-sample.

## Surfaces

- Dedicated page `transmission.html` (built by `scripts/build_transmission.py`, in the
  Research nav). Daily build; weekly calibration refresh.
- `latest.json["rate_inflation_transmission"]` block (written by `engine/run.py`) →
  consumed by the macro panel + the LLM brief (`engine/master_brain.py`).

## Roadmap (fast-follows)

1. **Per-sector rate/inflation beta** overlay on sector heat (display context chip).
2. **Per-stock macro-sensitivity** chip on `stock.html` (rate-beta tier + duration bucket
   + inflation-hedge), with the "single-name secondary betas are noisy" caveat.
3. **NY Fed Survey of Consumer Expectations** as a fourth expectations source (needs a
   non-FRED collector — deferred from the FRED-only foundation).
4. **MOVE (rates-vol)** as an explicit transmission driver once the yfinance series is
   cached in CI (not in the local store today).
