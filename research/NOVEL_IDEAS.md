# Novel Ideas — Honest Scorecard & Integration Plan

Research lead synthesis of 5 adversarially-verified backtest ideas against the live
stock score (`engine/strategy_composite.py`) and the strategy-lab emit. All results sit
on `data/stocks` = **114 CURRENT survivor mega-caps** → every cross-sectional/book-level
absolute number is an **optimistic CONTEXT bound, not proven alpha**. The honest, near-
survivorship-neutral content lives in *within-sleeve, same-names relative comparisons* and
in *non-survivor index tests* (`_GSPC`). Net of 5 bps one-way throughout. DSR `n_trials`
declared per idea.

## 1. Scorecard

| key | idea (1-line) | verdict | net-of-cost survivable? | best honest stat | survivorship | decision |
|---|---|---|---|---|---|---|
| `vol_scaled_momentum_crash` | constant-risk vol-scaling on a 12-1 momentum sleeve (Barroso-Santa-Clara) | **RISK_LEVER** | yes (gross 1.259 → net 1.218 Sharpe; 0.51%/yr cost charged) | within-sleeve Sharpe +0.094, MaxDD −53.6%→−35.4%, worst-month −26.4%→−10.6%, kurtosis 14→5.5; paired block-bootstrap P(ΔSh>0)=0.947 | HEAVY (110 longest-lived survivors; tail months 13–61 names) | **INTEGRATE** (de-risk overlay; already partly live) |
| `pead_sue_pit` | event-time PEAD: seasonal-RW SUE → forward CAR-vs-`_GSPC` strictly after EDGAR filing | **CONTEXT** | no (L/S quintile DSR fails all horizons; short horizons net-negative on cost) | rank-IC 21d +0.0296 (t_HAC 1.79, p 0.073), 63d +0.0255; Q5 CAR63 +2.31% vs Q1 +1.09%; **fails BH-FDR (best q=0.24)** | HIGH (90 survivors) | **INTEGRATE as CONTEXT lens only** |
| `calendar_seasonality_tom_moy` | turn-of-month / month-of-year return tilts (`_GSPC` 1928+ and survivor panel) | **CONTEXT → sizing tilt** | yes for the tilt; the long/flat sleeve UNDERPERFORMS B&H (4.16% vs 6.35% CAGR) | full-sample TOM 12.55 vs 0.93 bps/day (Welch t=6.15, BH+DSR pass, `_GSPC` = non-survivor) **BUT post-2000 spread 2.73 bps t=0.74 p=0.46; post-2015 −0.34 bps (DEAD)** | LOW for `_GSPC` headline; HIGH for panel | **INTEGRATE as a small, decay-discounted sizing-context tilt** |
| `net_liq_regime_gate` | net-liquidity (WALCL−TGA−RRP) 13w RoC as expand/contract gate on the long book | **CONTEXT** | NO — gating long-only-when-expanding strictly *removes* return (gate Sharpe 0.86 vs B&H 1.09) | no horizon clears p<0.05; 21d diff +0.489% HAC t=1.11; 63d sign FLIPS; effective N ≈ a few dozen regime episodes | HIGH (book level) | **DROP as a gate; keep as a one-line risk-on colour, no sizing** |
| `breakout_52w_volume` | George-Hwang 52w-high momentum confirmed by ≥1.5× volume | **CONTEXT** | no — confirmed-breakout basket loses to B&H by ~12 pts CAGR; conf-minus-ALL is NEGATIVE | within-cohort conf-minus-near 63d +0.87% (HAC t=3.58 — **but non-overlap subsample FLIPS to t=−0.44; only 5–8% of phase-offsets reach \|t\|>2**) | SEVERE & decisive (the base-drift that sinks the overlay IS the survivor effect) | **DROP from score; optional CONTEXT chip only** |

## 2. INTEGRATE — exactly how

### 2a. `vol_scaled_momentum_crash` → keep the vol-target sizing overlay, re-frame as DE-RISK
This is **already wired**: `strategy_composite.build_from_close` emits
`size_scalar = VM.live_scalar(c, target=0.15, cap=1.5)`. The research confirms the lever
direction (constant-risk vol-scaling lifts risk-adjusted return and halves the crash tail)
**but corrects the framing**:
- The CAP sweep shows **CAP=1.0 (pure de-risk) Sharpe 1.230 marginally BEATS CAP=2.0's
  1.218** — the "calm-regime lever above 1.0×" adds nothing and slightly hurts.
- **Action:** lower the cap from 1.5 toward **1.0** (or document `cap=1.5` as a deliberate,
  unvalidated allow-modest-lever choice). The honest, supported scope is *constant-risk
  de-risking*, not levering up.
- Re-label the field/comment in `strategy_composite.py` line 56–59 and line 83 from
  "lets calm regimes lever modestly" → "constant-risk **de-risk** scalar; values >1.0 are
  an unvalidated lever, the validated benefit is the ≤1.0 down-scaling that crushes the
  crash tail."
- **CAVEATS to carry in the emit:** (i) this is a SIZING/risk lever, **not** return-alpha
  (CAGR falls as expected from de-risking); (ii) absolute Sharpe/DSR are survivorship-
  inflated — only the within-sleeve relative lift is trustworthy; (iii) the Sharpe lift is
  *borderline* (paired bootstrap lower bound crosses 0; significant ~95% one-sided only).

### 2b. `pead_sue_pit` → add a CONTEXT-only post-earnings drift tilt
- **Emit a `pead_sue` block** (NOT on the sized entry axis): standardized SUE + its
  cross-sectional rank + a 1–3-month "drift window active" flag (days since filing ≤ 63).
- Wire it as a **CONTEXT lens / confirmer** alongside `entry_z_axis`, mirroring how the
  existing emit already separates context from the sized axis. It may *confirm* a high-SUE
  name over a 1–3-month window; it must **never** size on its own.
- **CAVEATS:** weak (best IC p=0.073, **fails FDR q=0.24**), DSR fails at every horizon,
  L/S trade not survivable net of cost; SUE here is seasonal-random-walk (no PIT analyst
  estimates) which *understates* true PEAD; survivor panel inflates it. Strictly a positive
  directional **colour**, horizon 21–63d.

### 2c. `calendar_seasonality_tom_moy` → small, decay-discounted sizing-context tilt
- The `_GSPC` headline is genuinely non-survivorship-biased and full-sample bulletproof,
  but **decayed**: post-2000 TOM spread 2.73 bps (t=0.74, p=0.46), post-2015 reversed. So
  it is **not** a market-timing on/off switch (the long/flat sleeve underperforms B&H).
- **Action:** emit a deterministic **`calendar_tilt`** sizing-context field — a small
  multiplier nudge on `size_scalar` (e.g. lean intended exposure *into* the TOM window /
  Santa, lean *out of* Sep weakness) — explicitly **decay-discounted** (apply a fraction of
  the full-sample effect, or cap the nudge at a few percent) and flagged as a *budgeting*
  hint, never a buy/flat trigger.
- **CAVEATS:** effect concentrated pre-1990, statistically dead in the modern era; per-day
  index means ignore entry spread/slippage. Treat as the *weakest* of the integrations —
  acceptable only because it is a tiny sizing nudge with a non-survivor pedigree, not alpha.

## 3. DROP — and why

- **`net_liq_regime_gate` — DROP as a gate.** No horizon clears p<0.05; the 63d sign flips;
  effective N is a few dozen macro episodes (largely a 2020-21 QE artifact); and gating
  long-only-when-expanding **strictly removes return** (Sharpe 0.86 vs B&H 1.09 at 57%
  exposure). The trend200 DSR=0.976 "SURVIVES" is a red herring — it certifies the gated
  sleeve's own Sharpe is non-zero in a 16-yr bull, not that the gate beats holding. Keep at
  most a **one-line "net-liquidity expanding = mild risk-on colour"** narrative chip with
  **no sizing or gating authority**.

- **`breakout_52w_volume` — DROP from the score/emit as alpha.** Every breakout bucket
  *underperforms* simply owning these survivors (conf-minus-ALL is negative at 21d & 63d);
  the basket loses to B&H by ~12 pts CAGR; DSR=1.0 only certifies the basket's own Sharpe is
  non-random. The base-drift that sinks the overlay **is** the survivor effect. The
  within-cohort conf-minus-near "p=0.0004" is HAC-overstated: a proper non-overlapping
  subsample flips to t=−0.44 and only 5–8% of phase-offsets reach |t|>2. At most a passive
  **CONTEXT chip** ("confirmed 52w breakout = higher-quality cohort, esp. 63d"), never a buy
  or sizing trigger — and even that is survivorship-capped.

## 4. Net effect on the live system
- `strategy_composite.py` keeps its current shape (validated entry-timing axis + trend gate
  + vol-target `size_scalar`). The only **code-level** change is re-framing/re-capping the
  `size_scalar` toward pure de-risk (2a) and adding two **CONTEXT-only** emit blocks
  (`pead_sue` 2b, `calendar_tilt` 2c) that never touch the sized entry axis.
- Net-liquidity and 52w-breakout do **not** enter the score; they remain narrative colour at
  most. No survivorship-inflated cross-sectional claim is promoted to alpha.
