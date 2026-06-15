# MRS transition-leg clamp — calibration A/B spec

**Status:** scaffold shipped (config-driven, **default `1.0` = byte-identical, NOT flipped live**). Flipping to `0.5` requires the validation below to pass first.

## The problem

The macro-risk score (MRS, `engine/conditions.py`) folds a `transition` leg whose value is set by the regime transition state:

| `transition_state`        | leg value (pre-existing) |
|---------------------------|--------------------------|
| `TRANSITIONING` / `NEW_REGIME` | **1.0** |
| `WEAKENING`               | 0.5 |
| else (`STABLE`)           | 0.0 |

leg weight `transition = 0.25` (`_mrs_weights`). So a `TRANSITIONING` regime pushes MRS toward risk-OFF by up to `0.25 / Σweights` — and `TRANSITIONING`/`NEW_REGIME` is, by construction, the state the regime is in **at a turn**. In the Iran whipsaw this meant the architecture leaned risk-off *hardest* in the days immediately before the violent snap-back: **pro-cyclical into the turn.** The leg amplifies conviction precisely where conviction is least reliable.

## The change

Clamp the `TRANSITIONING`/`NEW_REGIME` value from `1.0` to `0.5` (i.e. equal to `WEAKENING`), so an in-flux regime no longer pushes MRS risk-off *harder* than a merely weakening one. This is:

- **sign-preserving** — never flips a leg's direction;
- **subtract-only** — can only *lower* the risk-off push, never raise it;
- **bounded** — max effect is the leg's `0.25` weight on a `[0,1]` score;
- **a guardrail, not a bet** — it removes a known amplification rather than adding a directional call.

### Implementation (already in tree, default-off)

`engine/conditions.py`:
- `_mrs_transition_high()` reads `engine.macro_overlay.transition_high` (**default `1.0`**).
- Both MRS paths use it: the scalar `_mrs_transition_val()` and the series `_macro_risk_legs()` (`.mask(... , _mrs_transition_high())`), so the live snapshot and the calibrate() honesty bands cannot drift.
- A/B = set `engine.macro_overlay.transition_high: 0.5` in `config.yml`. No code change.

Invariant: with the default, `_mrs_transition_val("TRANSITIONING") == 1.0` and the whole MRS series is byte-identical to pre-change (locked by `tests/test_turning_point.py::test_mrs_transition_high_default_is_one` and the unchanged `tests/test_conditions.py`).

## Validation plan (must pass before flipping to 0.5)

Run inside the existing MRS honesty calibration (`scripts/` MRS calibrator / `macro_risk_series` → calibrate bands), A=`1.0` vs B=`0.5`:

1. **MRS honesty band re-fit.** Recompute the calibrated MRS→forward-outcome bands on the full history under B. Confirm the bands stay monotonic and the label thresholds (`low/moderate/elevated/severe`) remain well-separated — i.e. the clamp doesn't smear the score.
2. **Forward-outcome A/B, episode-declustered.** For days in `TRANSITIONING`/`NEW_REGIME`, compare A vs B on forward SPY / sector-dispersion outcomes. Block-bootstrap by *episode* (not by day) — transition clusters are autocorrelated. Report the 95% CI on (B − A); the clamp ships only if B is **no worse** (the claim is "removes a harmful amplification," so the bar is *do no harm*, not *add edge*).
3. **Sector-overlay turnover.** The MRS feeds the sector-heat macro penalty + per-name ladder. Confirm B does not increase whipsaw turnover (it should *decrease* it at turns).
4. **Honest `n_trials`.** Count this as one of the variants tried; fold into the DSR denominator for any downstream scored claim.

## What this is NOT

- Not a new signal, not new data, not a directional view.
- Not the fragility banner (`engine/turning_point.py`) — that is display-only and never touches MRS. This clamp is the *one* scored change the turning-point analysis surfaced, and it is conservative because it only *removes* a pro-cyclical-into-the-turn push.

## Expected outcome

Most likely B is statistically indistinguishable from A on returns but modestly *reduces drawdown/turnover at transitions* — the same family as the dislocation drawdown-only effect. If even the do-no-harm bar isn't cleared, leave the default at `1.0` and keep the scaffold for future re-test.
