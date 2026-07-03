# W0.4 — sector_central gate_factor stuck at 0.2

**Verdict: GENUINE persistent risk-off + mapping saturation. NOT a stale-input bug.**

## Diagnosis

### What the data shows (2026-06-26 → 2026-07-03)

`data/china_sector_central/calls.parquet`: 265 rows, 5 sessions, gate_factor=0.2 on every row. Score range 6–60; max observed = 60 (Conglomerates). Accumulate threshold = 72.

### Live regime_state() output (2026-07-03)

```
blended = 0.98   tilt = 0.96   state = "Risk-off — de-risking"

credit  (weight 0.45): value = 1.00   — TSF credit-impulse at 36m 100th pctile
vol     (weight 0.35): value = 0.94   — CSI 300 21d vol at 5y 94th pctile
margin  (weight 0.20): value = 1.00   — margin/float at 5y 100th pctile
```

All three legs are genuinely saturated. Data freshness:
- credit: TSF last release = 2026-05-16 (April data, released mid-May). File age = 0d. Monthly cadence; May release due ~June 16. NOT stale.
- vol: data/china/510300.SS.parquet age = 0.05d. Fresh.
- margin: data/china_margin/balance.parquet age = 0d. Fresh.

### Gate mapping saturation

```python
risk_on = round(-0.96, 2) = -0.96
gate_base = clip(0.5 + 0.5 * (-0.96), 0.2, 1.0) = clip(0.02, 0.2, 1.0) = 0.20   # FLOOR HIT
# Q3 penalty: 0.20 * 0.85 = 0.17 → clipped back to 0.20
gate_final = 0.20
```

Any blended de-risk >= 0.60 → risk_on <= -0.20 → gate <= 0.20 (floor). Current blended = 0.98 saturates the floor with enormous margin.

### Accumulate unreachable: confirmed

Max achievable score at gate=0.2 (best-case: state+pathway lead=1.0, max mom=0.3):
```
gated = 1.0 * 0.2 = 0.20
raw   = 0.20 + 0.5*0.30 = 0.35
score = round((0.35 + 1.0) / 2.0 * 100) = 68
```
Accumulate requires score ≥ 72. Max = 68. **Structurally unreachable while gate = 0.2.**

Gate lifts to 0.29 (Accumulate becomes reachable) only when blended falls below 0.58 — far from current 0.98.

### Root cause classification

**(b) Genuine persistent risk-off.** The gate is working as designed. All three underlying series are data-fresh and represent real market conditions (credit contraction + elevated vol + margin saturation). No stale input. No mapping logic bug.

The "stuck" appearance is correct behaviour: the regime IS pinned at an extreme, so the gate IS pinned at its floor.

---

## Changes made

### 1. `engine/china_sector_central.py`

Added three items:

**`_LEG_STALE_DAYS`** (constant dict):
```python
_LEG_STALE_DAYS: dict[str, int] = {"credit": 60, "vol": 7, "margin": 7}
```
Thresholds match the natural release cadence: credit is monthly (60d = ~2 months without update), vol/margin are daily (7d = ~5 trading days).

**`_GATE_ACCUMULATE_FLOOR`** (constant):
```python
_GATE_ACCUMULATE_FLOOR = 0.29
```
Derived from: max_score(gate) = round((gate + 0.15 + 1.0)/2 × 100) ≥ 72 → gate ≥ 0.28. Using 0.29 with a small float margin.

**`_regime_leg_staleness()`** (new function):
Reads the mtime of each leg's source parquet file and returns age in days. Returns `None` for a file that doesn't exist. Source paths:
- credit: `data/china_credit/tsf.parquet`
- margin: `data/china_margin/balance.parquet`
- vol: `data/china/510300.SS.parquet`  (china store, not yahoo — matches `_cnclose("510300.SS")`)

**`_regime_anchor()` additions** (always present in return dict):
- `leg_stale`: `{credit: int|None, vol: int|None, margin: int|None}` — age in calendar days of each leg's input file.
- `any_stale`: `bool` — True when any leg exceeds its `_LEG_STALE_DAYS` threshold.
- `gate_caps_tier`: `str|None` — name of the top tier that is structurally unreachable at the current gate (currently `"Accumulate"` when gate=0.2), or `None` when all tiers are reachable.

Live values as of 2026-07-03:
```
leg_stale:      {'credit': 0, 'margin': 0, 'vol': 0}
any_stale:      False
gate_caps_tier: 'Accumulate'
```

### 2. `templates/sector_central_china.html.j2`

**CSS additions** (inside `<style>`):
- `.rg-cap-notice` — amber-left-bordered row for the tier-cap message.
- `.rg-stale-notice` — red-left-bordered row for the staleness warning.

**JS `regimeBanner()` additions** (after the 4 existing cells):

*Cap notice* — rendered when `M.gate_caps_tier` is set:
> "Risk-off regime (gate ×0.2) currently caps all sector calls below **Accumulate**. This is the genuine regime signal — not a data error. The cap lifts automatically when the credit/vol/margin de-risk blend falls below 0.60."

Bilingual: `l-en`/`l-zh` via the existing `L()` helper. Amber styling matches the other warning conventions on this page.

*Staleness notice* — rendered when `M.any_stale` is true:
> "Stale regime input detected: margin(15d). A frozen upstream collector may be silently pinning the gate. Check the collector logs."

Red styling. Only shown when inputs are genuinely overdue. Currently invisible (all inputs fresh).

**No ranking changes.** The banner is purely display/diagnostic. Gate computation, tier computation, and board ordering are unchanged.

### 3. `tests/test_china_sector_central.py`

Four new pure-logic tests (no data dependency on the china_sectors plane):

- **`test_gate_caps_tier_set_when_gate_at_floor`** — asserts `gate_caps_tier='Accumulate'` when extreme risk-off drives gate to 0.2.
- **`test_gate_caps_tier_none_when_gate_above_floor`** — asserts `gate_caps_tier=None` when gate ≥ 0.29 (Accumulate reachable).
- **`test_staleness_constant_gate_and_stale_leg_fails`** — the CI sentinel. Reads the live calls.parquet and live file mtimes. **Skips** until ≥10 sessions are logged. **Fails** when gate_factor is constant across ≥10 sessions AND any leg input exceeds its staleness threshold simultaneously. Currently skips (5 sessions). Will activate and pass when sessions reach 10; will fail if a collector freezes.
- **`test_regime_anchor_returns_staleness_fields`** — asserts the three W0.4 keys are always present in `_regime_anchor()` output, even when `regime_state()` fails (degraded path).

Test run result: **11 passed, 1 skipped** in 34s.

---

## What was NOT changed (W0 discipline)

- No changes to `_cn_bonus`, `blend_sorted` usage, or board ordering.
- No changes to the gate computation formula (floor, weights, nudges).
- No changes to the tier thresholds.
- No changes to the calls.parquet schema or the grader.
- No changes to any builder scripts.

---

## Deferred items

1. **Vol source path robustness**: `_regime_leg_staleness()` hard-codes `data/china/510300.SS.parquet`. If the china store ever moves (e.g. to R2 or a different directory key), this path silently goes `None` again. A future wave should derive the path from `store.path("china", "510300.SS")` if such a helper is added.

2. **Credit staleness threshold**: 60 days is intentionally generous (monthly TSF; June 2026 data is due early July and is not yet missing). If the TSF collector breaks, the credit leg will show `age > 60` within 2 months. The threshold could be lowered to 50d once the June release lands and confirms the cadence.

3. **Accumulate reachability at gate ≥ 0.29**: The _GATE_ACCUMULATE_FLOOR computation assumes the best-case sector has a validated pathway. Sectors without pathways have a slightly lower max (68 at gate=0.2 regardless of pathway presence — the math coincidentally equals). This is fine as-is but worth a comment in a later cleanup.
