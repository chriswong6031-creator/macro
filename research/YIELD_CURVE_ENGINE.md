# Yield-Curve Analytics Engine

*The unified, theory-grounded interest-rate read. A display-only leaf
(`engine/yield_curve.py`) that turns the full Treasury curve into shape, regime,
recession, forward and signal reads — surfaced on `transmission.html` and emitted
dashboard-wide as `latest.json["yield_curve"]`. Never scored.*

## Why

The dashboard already ingests the full curve (FRED CMT 3m→30y, TIPS real 5y/10y,
breakevens 5y/10y/5y5y, Kim-Wright `THREEFYTP10` term premium) and the bond page already computes the best
single curve primitives — the NY-Fed 10y-3m probit, the Engstrom-Sharpe near-term
forward spread, the bull/bear × steepener/flattener taxonomy, the un-inversion alarm.
But those were **siloed on the bonds page**, and the rate/inflation transmission page —
the one place that traces rates → every asset — carried only a thin four-KPI rates card
(real 10y, 2s10s, policy gap). The curve, in other words, was under-read relative to
inflation everywhere it mattered for cross-asset and sector/factor allocation.

This engine closes that gap. It **reuses** the bond-engine primitives (imports the
probit, the NTFS, the move taxonomy, the un-inversion alarm — so the two pages can never
drift) and **adds** the curve theory that was missing: the level/slope/curvature shape
decomposition with the Litterman-Scheinkman PCA variance, the butterfly spreads, the
real and breakeven curve slopes, curve momentum/speed, the forward-rate grid with carry
& roll-down, and four typed signal families for the rest of the dashboard.

## What it computes (all from data already in the frame)

| Block | Metrics |
|---|---|
| **shape** | level (avg yield), slope (2s10s), curvature (2s5s10s butterfly), 5s10s30s fly, and a PCA of daily curve changes reporting the variance each of level/slope/curvature spans (the Litterman-Scheinkman result, **measured on our data**, not asserted) |
| **slopes** | 2s10s, 3m10y, 5s30s, 2s5s, real 5s10s (TIPS), breakeven 5s10s, TP-adjusted 2s10s — each with level + 5y percentile + 63d change + an inverted flag |
| **momentum** | real-10y / nominal-10y / front-2y 63d speed (bp), the 63d slope change, and the \|real-rate speed\| percentile — the "rate-of-change beats level" reads |
| **regime** | bull/bear × steepener/flattener (reused taxonomy) + Fed-cycle phase + favoured/pressured asset lists + the term-premium direction (so "duration = safe haven" is explicit) |
| **recession** | NTFS + NY-Fed 10y-3m probit + un-inversion alarm + TP-adjusted slope → a 0–4-flag composite risk band |
| **forwards** | 1y1y / 2y1y / 5y5y forward rates + 10y carry, roll-down and carry+roll |
| **signals** | core_macro, **sector** (per-sector curve tilt, tagged MEASURED vs THEORY), **stock_factor** (value/growth, size, duration), **market_tendency** (curve-speed → drawdown risk) |

## Discipline — display / context only, never scored

The house calibrator's scored-leg gate (`scripts/calibrate_rate_inflation.py`, the same
forward-drawdown bar the bond-health legs pass) found **no rate/inflation leg robust
enough to move an allocation**. We add the curve-shape candidates (NTFS, curvature,
\|real-rate speed\|, the flattening impulse) to that gate so they are tested honestly on
the same bar — but the engine remains display-only. Two refinements over a naive build,
both grounded in the research synthesis (`research/yield-curve-research` workflow):

- **Sector / factor tilts are tagged `MEASURED` vs `THEORY`.** A tile is `MEASURED`
  only when the transmission IC matrix has a CONFIRMED/DIRECTIONAL forward-IC cell for
  that asset under the curve driver; otherwise it is `THEORY` (textbook channel, no edge
  claim). Neither is a trade signal.
- **Honest caveats are carried inline**, including the ones the fact-check flagged:
  the value/growth–curve link is only ~0.10-correlated long-run and largely **not** pure
  duration (AQR/Asness); bull steepeners have been ~flat-to-negative for equities despite
  the textbook "recovery" framing (Lombard Odier); a term-premium-driven bear steepener
  is **not** the bullish growth kind; and the un-inversion roughly coincides with
  recession onset (≈3–6m, 1990/2001) rather than the unsourced "8–19 month" range.

## What the research says to trust (and not)

From the multi-agent research synthesis, adversarially fact-checked:

- **3m10y over 2s10s** wherever a single recession spread is needed (Estrella-Mishkin
  γ = −0.5333, −0.6629 — the NY-Fed vintage). The **NTFS** (Engstrom-Sharpe, Fed 2018-19)
  statistically **dominates** the 2s10s, rendering it redundant in a joint probit.
- **Real-yield velocity** is the cleanest drawdown precursor (2022: ~+250bp real-yield →
  S&P −25%, stock-bond hedge breaking; 1994's +300bp from a positive base cost only ~10%
  — speed and starting point beat cumulative level). Flagged at \|Δ63d real-10y\| ≥ ~75bp.
- **Curve regime label** is directionally robust as a *context tilt*, never sizing alone.
- **Display-only / fragile:** raw 2s10s level (redundant once NTFS is in); the ACM /
  Kim-Wright / Cochrane-Piazzesi term premium (material model dispersion — show a band);
  sector & factor betas (wide CIs, R²≈0.08–0.18); MOVE/VIX thresholds and crypto
  rate-correlation (unsourced or contested); carry/roll-down & butterfly (mechanics, not
  alpha). The engine treats every one of these accordingly.

## Surfaces

- **`transmission.html`** — a new "Yield curve" section: shape + PCA, regime card,
  recession dashboard, slopes & momentum table, forwards & carry, and the sector / style /
  market-tendency signal families. Built by `scripts/build_transmission.py`.
- **`latest.json["yield_curve"]`** (written by `engine/run.py`) and the transmission
  contract `data/transmission/latest.json["yield_curve"]` — consumed by the macro panel,
  the LLM brief, and the per-stock macro-sensitivity read.

## Config & calibration

`config.yml: yield_curve.*` (just the regime window; the percentile/momentum/PCA windows
are documented engine constants). The curve candidate legs are gated through
`scripts/calibrate_rate_inflation.py` → `data/transmission/calibration.json`; nothing is
wired to a score until a refresh confirms it passes — the same restraint as bonds.

## Roadmap (fast-follows)

1. **Term-premium model band** — add ACM (`ACMTP10`, not yet collected) alongside the
   Kim-Wright `THREEFYTP10` we already use, shown as a band rather than a single point, per
   the fact-check on model dispersion (the codebase historically mislabels THREEFYTP10 as
   "ACM" — it is Kim-Wright).
2. **Wright-augmented probit** (add the fed-funds level to the 3m10y probit) as a second
   recession gauge — confirmed in-sample, OOS gain treated cautiously.
3. **Low-frequency trend spread** (HP-filtered `T10Y3M`) as the OOS-valid equity-premium
   context leg (Faria-Verona 2020) — the one curve read with genuine return content.
