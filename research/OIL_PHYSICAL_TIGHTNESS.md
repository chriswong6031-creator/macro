# Oil Physical Balance — display-only panel (EIA Weekly Petroleum Status)

**Proposal (ChatGPT #10):** an "Oil Physical Tightness" *scored* composite —
`crude draw z + product draw z + refinery-util z + backwardation − COT crowding` —
fed into commodity alerts/conviction.

**Verdict: build the DISPLAY, drop the SCORE.** Shipped a neutral physical-balance
context panel on `commodities.html`; did **not** wire any of it into scoring.

## Why not scored
1. **The `+ backwardation` leg is already validated wrong-signed** for single-asset oil
   timing — `scripts/commodity_carry_phase0.py` on 38y of EIA WTI futures: 63d basis→spot
   IC −0.16, t_HAC −4.6, both halves. Crediting it as a positive tightness leg re-introduces
   a sign error we already paid to discover (see `engine/commodity_carry_context.py`).
2. **Weekly EIA inventory is the most-arbitraged number in oil.** It releases Wed 10:30 ET
   and the surprise-vs-consensus reprices within minutes; *levels/draws* have weak
   **forward**-return predictability. "Draw = bullish" is a contemporaneous balance read,
   the same trap as the backwardation leg.
3. **Raw inventory z is a calendar.** US crude/gasoline/distillate stocks have a large
   deterministic annual cycle. ChatGPT's raw-z composite mostly measures the time of year.
4. **COT crowding** already has its own panel; mixing positioning into a *physical* read
   muddies both. The shipped composite is therefore **pure physical** (no price, no COT).

If ever promoted to a scored leg it must clear `calibrate_commodities` (split-half/DSR)
first; expectation is DISPLAY-ONLY (anticipated draws are priced, seasonal-z of inventory
has weak forward IC).

## What shipped
`engine/commodity_supply_context.py` — a LEAF (pure functions; never imported by
conviction/alerts/signals/mtf; invariant-tested). Surfaced via `_oil_supply_read()` in
`scripts/build_commodities.py` → the "Physical balance (EIA)" card.

- **Seasonal-anomaly z** (the core fix): each inventory shown as deviation from its
  *same-week-of-year* climatology over a trailing 5y window — a winter draw reads normal.
  Sign: **negative = below 5y season = tight.**
- **Composite `balance_z`** = mean of the inventory seasonal-z's → neutral 3-state label
  (tight / balanced / ample). Display gauge, **not** a price call.
- New reads: **Cushing** (WTI delivery-point), **days-of-supply** (crude + products),
  **SPR 4-week Δ**, product (gasoline/distillate) seasonal-z.
- **Neutral coloring** — the old panel colored a draw green ("bullish") / build red; that
  directional framing is removed. Caveat line states "physical balance ≠ price direction".

## Data (all keyless EIA dnav hist_xls, weekly; reuses the existing `EiaAdapter`)
Added 4 series to `config.yml eia.series` (fetched live, verified to 2026-06-05):

| col | dnav id | use |
|---|---|---|
| `spr_stocks` | WCSSTUS1 | SPR releases/refills (history validated: 727M peak '10, 347M low '23) |
| `refinery_inputs` | WCRRIUS2 | crude days-of-supply denominator |
| `gasoline_supplied` | WGFUPUS2 | gasoline days-of-cover |
| `distillate_supplied` | WDIUPUS2 | distillate days-of-cover (freight/industrial) |

## Live read at build (2026-06-05)
Balance −1.7σ (**tight**): crude −1.3σ, Cushing −1.7σ, gasoline −2.1σ, distillate −1.9σ;
crude days-of-supply 25.4; refinery util 95.3%; **SPR −34.9M/4w** (a real, validated
renewed drawdown off the mid-2025 ~403M refill peak).

## Tests
`tests/test_commodity_supply_context.py` (9) — seasonal-z beats raw at a seasonal extreme;
flags a genuine draw; guards (short/flat/NaN); days-of-supply; balance gauge; bilingual
caveat; **invariant: the leaf is never wired into the scoring path**. Updated
`test_phase_buildout.py::test_eia_supply_read_if_cache` to the new schema.
