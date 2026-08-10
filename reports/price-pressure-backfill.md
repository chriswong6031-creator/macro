# Price Pressure — historical backfill (DRL W1)

Frozen 2026-08-10 from `data/price_pressure/base_rates.json`. Producer:
`python -m scripts.build_price_pressure --backfill`. Program:
`research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md`.

**What this is.** Every US single-name residual shock the LSR-P0 fence finds over
the store's five-year span, recorded point-in-time, plus what actually happened
to each one afterwards. It is a display-tier honesty layer: it tells a reader
what usually follows a move like the one they are looking at.

**What this is not.** It is not a selection signal and not an entry veto. That
construction is CLOSED at OHLCV grade — `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`,
measured in `reports/liquidity-shock-reversal-phase0.md`: information separation
**0/10** contrasts, microstructure features **3/36** (against 1.8 expected by
chance, none surviving two horizons), the veto stand-in **0/6**, and the real
unconditional 5d reversal (+0.284% liquid decile spread) breaking even at
**14.2 bp/leg**. Continuation is the modal outcome and the recovery that exists
is sub-cost. Nothing below re-litigates that; it displays it.

> **Family-level differences in forward outcomes were measured and are null
> (0/10 contrasts) — DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER; families are
> shown as context, not separation.**

## Construction

Imported wholesale from `scripts/research_liquidity_shock_reversal.py` — no
re-derived math, because the tables below and the display that quotes them must
be computed on the same residual:

- `resid = ret − sector_ex_self_peer(ret)`, `resid_z = resid / rolling60σ(resid).shift(1)`
- Eligible: not a split-repaired bar ∧ close ≥ $5 ∧ 60d median ADV ≥ $5M ∧ σ known
- Shock: `|resid_z| ≥ 3` ∧ volume ≥ 2× trailing 60d median, both sides
- Retrace fraction, one consistent log space: `fwd_h / (−log1p(clip(resid_t0)))`,
  sign-flipped on the up side. `|log1p(resid_t0)| < 0.02` → null (343 rows).
- Terminals are **window-end grades at fixed horizons**. There is no early close:
  a full retrace on day 3 records `days_to_first_100pct_retrace = 3` and the row
  still grades at 21d and 60d.

## Coverage and survivorship

| | |
|---|---|
| Span (stamped, rolling store) | **2021-07-06 → 2026-07-02** — five years, not twenty |
| Panel | 4,281 names |
| Events | 35,677 (down 17,511 · up 18,166) across 1,254 sessions |
| Episodes closed / open | 33,735 / 1,942 |
| EDGAR-covered share of events | 45.7% |
| Peer basis (per event) | sector 52.6% · market 47.4% |
| Sector-labelled share of the panel | 34.3% |
| Thematic-basket context available | 17.1% of events |
| Truncated rows / dead tape | 299 (0.84%) / 271 (0.76%) |

The span is **span-bound**: the vendor store rolls, so a later re-run drops the
oldest era and these rates change. They are stamped for that reason.

- Prices are UNADJUSTED. Splits are repaired by the yahoo-verified detector and
  every repaired bar is stamped **ineligible** — a real one-day crash on a split
  day is excluded rather than mislabelled.
- Dividends are not adjusted: ~0.5% at an ex-date is noise against a 3σ trigger
  but is a small downward bias in every forward window.
- The LSR peer helper backfills unlabelled names with the whole-universe mean, so
  nearly half of these events residualize against **the market, not sector
  peers**. Every row carries `peer_basis`, and the display never prints the word
  "peers" on a market-basis row.
- EDGAR covers 1,314 tickers. Outside that set the family is
  **filing-coverage-unknown** — "we did not look" is not "we looked and found
  nothing", and the two never share a bucket.
- Names that stop trading keep their rows and grade `DELISTED_OR_HALTED` inside
  the terminal shares. Rows whose window has not elapsed are counted as open, per
  cell. Nothing leaves the denominator.

## Down side — the product focus

Retrace fraction of the t0 residual. Positive = came back; negative = went
further. Honest-N is per horizon (`first_in_h`: no same-side shock in the prior
h sessions). `n_dates` matters: shocks bunch on market-wide days.

**5 sessions**

| family | events | episodes | dates | q25 | median | q75 | mean [95% CI] | ≥33% back | still lower |
|---|---|---|---|---|---|---|---|---|---|
| earnings-filing | 4,673 | 4,533 | 804 | −0.345 | −0.043 | +0.272 | −0.015 [−0.050, +0.021] | 21.9% | 53.9% |
| other-filing | 254 | 240 | 196 | −0.462 | −0.020 | +0.330 | −0.040 [−0.124, +0.049] | 25.2% | 50.9% |
| no-filing | 3,285 | 3,044 | 951 | −0.395 | **+0.014** | +0.434 | −0.024 [−0.060, +0.011] | 30.1% | **49.1%** |
| filing-coverage-unknown | 9,299 | 8,800 | 1,147 | −0.374 | +0.007 | +0.344 | −0.025 [−0.051, +0.002] | 25.7% | 49.5% |
| **all** | 17,511 | 16,617 | 1,186 | −0.371 | −0.008 | +0.339 | −0.026 [−0.047, −0.005] | 25.4% | 50.7% |

**21 sessions**

| family | events | episodes | dates | q25 | median | q75 | mean [95% CI] | ≥33% back | ≥80% back | still lower |
|---|---|---|---|---|---|---|---|---|---|---|
| earnings-filing | 4,673 | 4,377 | 790 | −0.630 | −0.079 | +0.435 | −0.078 [−0.133, −0.020] | 29.4% | 14.8% | 53.9% |
| other-filing | 254 | 222 | 180 | −0.690 | +0.042 | +0.592 | −0.124 [−0.315, +0.072] | 34.1% | 18.2% | 46.7% |
| no-filing | 3,285 | 2,819 | 915 | −0.766 | +0.028 | +0.764 | −0.073 [−0.142, −0.001] | 38.3% | 24.4% | 48.8% |
| filing-coverage-unknown | 9,299 | 8,359 | 1,126 | −0.780 | −0.110 | +0.586 | −0.105 [−0.153, −0.057] | 32.9% | 19.4% | 54.6% |
| **all** | 17,511 | 15,777 | 1,170 | −0.739 | −0.073 | +0.571 | −0.086 [−0.124, −0.050] | 32.9% | 19.0% | 53.3% |

**Terminal state at 21 sessions (down, all families):** `ACCEPTED_LOWER_21D`
**66.4%**, `RECOVERED_21D` 19.3%, `PARTIAL_21D` 14.0%, `DELISTED_OR_HALTED`
0.23%; 436 rows still open (window not elapsed). Read plainly: **two out of
three of these moves were still mostly unretraced a month later.** The
family columns above differ by a few points and every interval overlaps its
neighbours — see the null-contrast statement.

`ACCEPTED_LOWER` is avoid-evidence only. It is never a short thesis
(`DNR:KILL-DIRECTIONAL-SHORTING`).

## Up side (published, secondary)

At 21 sessions: median retrace +0.110, mean +0.114 [+0.076, +0.154], 41.1% gave
back ≥33%, 45.5% still above the shock price. Terminal shares: `KEPT_21D`
57.8%, `GAVE_BACK_21D` 26.9%, `PARTIAL_21D` 15.0%, `DELISTED_OR_HALTED` 0.31%.
Both sides ship so the surface reads as a pressure lens rather than a dip screen.

## Exemplars (measured, not asserted)

**MU, April 2025 — a non-fire, and that is correct behavior.** MU fired the
single-name fence **0 times** that month; its worst residual z was **−2.44 on
2025-04-04**, never crossing the −3 fence. On 2025-04-03 it fell −16.1% with a
residual of only −6.9% (z −2.28), and on 2025-04-04 −12.9% with −7.1% (z −2.44):
the semi complex fell together, so almost all of the move was the sector, not the
name. That separation is the construction's purpose. A MU-type long-horizon
secular washout is a different family and belongs to the winners-program linkage
(masterplan §8 leg 5), not to this fence.

**CDE, 2026-08 — two honesty traps, both live.** CDE is in the panel but is
**not EDGAR-covered**, so its family is `filing-coverage-unknown` and its chip
must read *"filings not tracked for this name"* — never "no filing". Its GICS
sector is **Materials** (chemicals and steel), so a "peers implied" line would be
economically false; the thematic-basket residual against **silver_miners** (10
names) carries the honest comparison. The 2026-08 episode postdates this frozen
snapshot (store ends 2026-07-02) and arrives on the first nightly with
`era="gap"` via the self-healing catch-up — this seed contains 5 earlier CDE
events, not that one.

## Limitations

1. **Eras.** Every row here is `era="backfill"`. It is context, never promotion
   evidence; the §7 gauntlet reads forward-era rows only, and accrual starts at
   the first nightly. The store snapshot used ends 2026-07-02 while the canonical
   R2 store is at 2026-08-07, so the first nightly's catch-up will add ~5 weeks
   of `era="gap"` rows — displayed, never evidence.
2. **No day taxonomy.** No historical `market_drivers` day classification exists
   (17 graded rows), so the tables carry no systemic-day or contagion split at
   all. Day character survives as per-event NUMBERS (`panel_shock_count`,
   `panel_share_z2`, `spy_ret_z`) and, for the current day only, as a live banner.
3. **Not tested at intended fidelity.** The order-flow half of the original
   design (signed imbalance, NBBO spread) has never been measured — the tape
   entitlement 403s. A null at OHLCV grade does not close the tape-grade version.
4. **These are marginal distributions, not a strategy.** The 5d medians sit
   within a fifth of a residual of zero on every family. Anyone reading a
   sub-1% edge here should re-read the 14.2 bp/leg break-even above.
