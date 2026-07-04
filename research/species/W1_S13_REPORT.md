# W1 S13 Phase-0 Report — US Within-Sector Reversal Sleeve

*2026-07-04 · prereg: research/species/W1_S13_PREREG.md (committed before the run)
· harness: scripts/s13_reversal_phase0.py · raw: research/species/_s13_phase0_out.json
· trial family `s13_reversal_sleeve` (m=2, DSR n_trials=2 from the ledger).*

## Verdict

**S13 SURVIVES phase-0 — as the 3M-formation construction only, and REGIME-SCOPED.**
The 1M variant fails the modern-era DSR leg. The pre-registered mega-cap sign flip
(K2) is confirmed with real money attached: the sleeve lost −11.8%/yr vs SPY over
2024-01→2026-06 — **the hostile regime is the one live today**, so nothing that
ships from this phase-0 may imply current tradability. Next rung (display chip)
requires the §1.3 ladder separately; promotion criteria unchanged.

## Primary table (monthly EW deepest-quintile within-sector, excess vs SPY)

| era | months | 3M: mean/mo | ann | HAC t | DSR (m=2) | verdict | 1M: mean/mo | DSR |
|---|---|---|---|---|---|---|---|---|
| PIT full 1996–2026 | 358 | **+0.49%** | +5.9% | 2.49 | **0.991** | SURVIVES | +0.28% | 0.910 marginal |
| Modern 2002–2026 (K1) | 292 | +0.34% | +4.0% | 1.72 | 0.908 | MARGINAL | +0.20% | **0.760 FAILS** |
| Pre-flip 2002–2023 | 264 | +0.48% | +5.7% | 2.36 | 0.981 | SURVIVES | +0.34% | 0.941 marginal |
| Flip 2024–2026 (K2) | 28 | **−0.98%** | −11.8% | −2.42 | 0.016 | FAILS | −1.18% | 0.002 |

3M bootstrap Sharpe CI (PIT era, 3-month blocks, B=2000): [0.13, 0.81], P(Sharpe>0)=0.996.
Effective n = 358 monthly episodes (the honest count; ~65 names/month).

## Kill criteria (pre-registered, in order)

- **K1 (modern-era decay): PASS for 3M** — modern mean excess positive (+0.34%/mo)
  and DSR 0.908 ≥ 0.90 (marginal band, not fail). **1M FAILS K1's DSR leg**
  (0.760) — the 1M construction is closed as the carried variant; it remains in
  the ledger as the registered inferior config.
- **K2 (2024–26 mega-cap flip): TRIGGERED** — pre-2024 modern era +0.48%/mo
  (DSR 0.981) vs 2024–26 **−0.98%/mo (t −2.42)**. Per prereg: the species does
  not die; it is REGIME-SCOPED. `mega-cap-dominance` moves from hypothesized to
  **measured** hostile cell. Any surface carries the regime caveat, and the cell
  is live at the time of writing.
- **K3 (Tencent-trap concentration): CLEAN** — top contributor ADBE at 3.1% of
  cumulative excess (3M config; threshold 50%). The edge is broad.
- **K4 (sign sanity): PASS** — within-sector monthly rank-IC of formation return
  is negative in both configs (3M: −0.0111; 1M: −0.0101, HAC t −1.9), matching
  the seed study's modern-era magnitude (−0.011) almost exactly. Reversal, not
  momentum; construction validated.

## Safety-net axes (context per §1.1; promotion keys on clean8_21, rotational)

3M config, 23,336 fires across 358 episodes:

| axis | clean8_21 (primary) | clean15_126 (context) |
|---|---|---|
| CLEAN_LIFTOFF | 28.3% | 33.9% |
| CUSHIONED | 13.0% | 5.4% |
| DEAD_MONEY | 20.1% | 0.1% |
| STOPPED | **38.5%** | 60.6% |

The stop-out rate is HIGH in absolute terms — these are deepest-quintile losers
(knife-adjacent by construction), and the sleeve's economics come from the
liftoff tail, not from safety. **This is a portfolio-unit species: the safety
net lives at the SLEEVE level (diversified monthly basket), not per fire.** Any
future attempt to trade single names off this signal would face a 38.5% 21-day
stop-out rate — the per-name overlay remains adjacent-falsified (timing as
return-alpha), exactly as the registry records.

## Honesty / leak audit (per §1.2 + prereg contract)

- **Fills:** signal at month-end close t; entry = first close STRICTLY AFTER t;
  exit = first close after the next rebalance; delisted-mid-month names grade at
  their last print (the honest loss). No same-bar fills anywhere.
- **Survivorship:** PIT membership restricts each rebalance to actual members;
  member-price coverage averaged **69.4%** (printed per prereg). The missing 31%
  skews toward catastrophic losers Yahoo no longer serves (LEHMQ/ENRNQ/WAMUQ/BSC
  class) — the deepest-loser quintile is exactly where they would have landed, so
  **all positive numbers above are optimistic bounds**. This caveat blocks any
  promotion past display until the sleeve re-confirms on a fuller panel
  (the massive store now accrues forward — future re-runs get honest coverage).
- **Sector map is current GICS applied to history (non-PIT)** — same limitation
  as the seed study; disclosed, not fixed here.
- **Multiplicity:** grid registered in `data/trial_ledger.jsonl` before the run;
  DSR n_trials=2 via the ledger handle (not a literal); no other knob searched.
- **No gates:** `assert_no_gate` enforced in the harness config (§1.5).

## Registry / gating updates shipped with this report

- S13 `validation_status` stays `phase0` (promotion is the §1.3 ladder's job);
  `gating.maturation` records: phase-0 PASSED (3M construction), 1M closed,
  regime scope mandatory, hostile cell live, re-read on the monthly review.
- `regime_scope.hypothesized_hostile` → measured: `mega-cap-dominance (2024–26:
  −11.8%/yr, t −2.42)`.

## In plain English

We tested the owner's named strength — buying each sector's most beaten-down
stocks once a month — the honest way: only names actually in the index at the
time, no timing filters (they killed this edge in China), and a stated price for
every entry and exit. Over thirty years it works: about half a percent a month
over the market, strong enough to survive the statistical haircut for having
tried two versions. But the last two and a half years — the mega-cap era — it
lost money fast, exactly as we suspected before running the test. So the
strategy earns a place on the shelf with a big label: **works over decades,
currently in its worst weather.** We also confirmed the fine print: roughly a
third of these beaten-down names keep falling hard individually — the safety
comes from holding the whole monthly basket, never from any single name.
