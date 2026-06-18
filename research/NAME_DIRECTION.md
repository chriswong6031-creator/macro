# Single-Name Direction (v0) — design

The third and final stage of the directional anticipation program (index → sector/theme →
single name). The question: **does the one validated equity directional driver — real rates —
transmit to single names out-of-sample?** And can we answer it *without* the data-mining trap
of fitting 1,500 independent per-name models?

## What the prior stages established

`engine/index_direction.py` + its Phase-0 found exactly one robustly-OOS-priced equity
directional driver across index → sector → theme: **real rates** (the `real_rate` leg drives
QQQ-med, XLK-med, SMH-long, XLP-long; `copper_gold` adds XLI-long). Everything else, every
horizon, is an honest coin-flip. So the *only* single-name channel worth testing is the name's
exposure to real rates — not a fresh per-name factor hunt.

## The honest design (Approach A — pooled macro-transmission)

One leg per name, one shared validated signal, **one pooled slope** — validated as ~2
hypotheses (medium 42td, long 189td), never 1,500 per-name fits (which would collapse under
Benjamini-Hochberg and have no power on ~20y of overlapping returns).

```
dur_i,t    = −beta_i,t          beta = cov(r_i, Δreal10)/var(Δreal10), causal (lagged 1d)
                                negated so dur>0 = rate-sensitive growth/duration name,
                                dur<0 = inverse (financials/energy that rise when rates rise)
shrunk_i,t = Vasicek(dur_i,t)   w=0.66 toward the cross-sectional mean (single-name rate-beta
                                persistence is only ~0.36 → shrink is mandatory)
signal_i,t = shrunk_i,t · rr_leg_t    rr_leg = the EXACT index_direction real_rate leg
                                      (z of the 60d real-rate change; high = rates fell = bullish)
r̂_i,t      = b · signal_i,t     ONE pooled slope b, fit through-origin on (fwd − own-mean) ~ signal,
                                sign-restricted to + (b<0 → collapse to coin-flip)
P(up)      = Φ(r̂ / σ_h), Platt-recalibrated, clamped to a TIGHT band (0.44, 0.58)
```

The shipped lean is `b·signal` — a *tilt around each name's own drift* — so Phase-0 validates
exactly that: `forecast_i = own_mean_i + b·signal_i` vs the per-name expanding mean (Goyal-Welch),
never an absolute-level forecast that would just relabel the equity premium.

## Honesty guards (mirroring index_direction)

- **Unit of inference = the per-DATE cross-section** (~250–280 monthly obs), HAC-corrected —
  *never* the 1,500×dates cells (which would fabricate N: all names load the same one macro bet).
- **Three statistics must agree** per horizon: cross-sectional rank-IC (dispersion ranks right),
  pooled Campbell-Thompson OOS-R² + Clark-West (level accuracy + nested test), and it must
  **beat a driver-only nested bench** — the same real-rate call given to every name with *no*
  beta dispersion. If dispersion adds nothing, it's the already-validated XLK/SMH cell in disguise.
- **Calibrated P(up)**: recalibrated Brier skill ≥ −0.01.
- **BH-FDR across the 2 horizons**; DSR (frozen `N_TRIALS`) + block-bootstrap = reported context.
- **Survivorship**: GO decided on the **PIT** (S&P-1500 point-in-time membership) panel, with the
  deep (current-members, survivorship-biased, optimistic) panel reported alongside.
- **Long horizon is structurally underpowered**: DFII10 (the real-rate underlying) starts 2003
  (~23y), so 189td overlap on a monthly grid leaves few effective obs — any long GO is provisional.
- **Frozen before the gate read** (anti-snooping, asserted in tests): `shrink=0.66`,
  band `(0.44, 0.58)`, natural-sign (not ReLU) beta as primary (ReLU reported as sensitivity),
  `N_TRIALS=4`.

## Integration (zero-cost-when-null)

`engine/name_direction.py` is a thin bridge (reuses `residual_alpha._causal_beta/_shrink` +
`index_direction.forecast_to_p_up/sigma_h/build_legs`). `anticipation.anticipate()` gains a
parallel `elif asset_class=='us_equity'` branch (next to the `asset in PRESETS` index branch)
that calls it — but `scripts/build_stock_library.py` only builds the shared rate inputs (and so
only pays the per-name beta cost) **when the NAME_DIRECTION gate has a scored horizon**. The
risk cone (already validated for every name) is untouched; the lean moves only the direction
center, width unchanged, on a separate axis from the cross-sectional Conviction rank.

## Expected outcome

Stated plainly: the honest base case is that this **scores nothing** — and that is the correct,
publishable deliverable, fully consistent with Goyal-Welch and the Gu-Kelly-Xiu ~0.3–0.4%
stock-level OOS-R² ceiling (a single linear macro channel sits at the low end). If nothing
clears, every name stays a coin-flip, only the risk cone is live, and
`research/NAME_DIRECTION_PHASE0.md` records the validated null. A scored horizon would ship a
tight, colored lean labeled **"validated macro-transmission overlay, not per-name alpha"** —
the name supplies only an exposure to an edge validated elsewhere.

v1 (only after a clean v0 GO, re-counting the BH family): add the sector's validated driver
(`copper_gold` for XLI-sector names). Do **not** pile on legs to rescue a NEUTRAL v0 — that is
exactly the data-mining the pooled design exists to prevent.
