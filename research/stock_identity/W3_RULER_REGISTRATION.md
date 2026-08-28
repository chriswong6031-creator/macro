# Stock Identity W3A — Episode Localization Ruler Registration

**Wave:** SI-W3A (episode ruler engine), plan `docs/superpowers/plans/2026-08-28-stock-identity-w3-measurement-release.md` Tasks 1-3, 3B, 3C.
**Binding law:** `research/stock_identity/W3_FINAL_ARCHITECTURE_FREEZE_2026-08-27.md` §4.1/§4.1b/§4.2/§4.3.
**Authority:** all five axes false. Research/display only. No fit, rank or routing authority is granted by this registration.

## 1. Source of every constant in `data/stock_identity/ruler/ruler_spec_v1.json`

### 1.1 Previously-frozen W1 geometry (carried verbatim, never re-derived)

| field | value | source |
|---|---|---|
| `atr_basis` | `wilder_atr14_at_prior_confirmed_close` | `engine/stock_identity/episodes.py::ATR_BASIS` |
| `p_pre_sessions` | `5` | `data/stock_identity/constants/si_constants_v1.json` → `values.P_pre` |
| `useful_zone_window_sessions` | `15` | `si_constants_v1.json` → `values.w` |
| `useful_zone_delta_atr` | `0.75` | `si_constants_v1.json` → `values.delta` |
| `false_start_atr_threshold` | `3.75` | `si_constants_v1.json` → `values.theta_fs` |
| `episode_type_anchor` | `{reset_decline: durable_low, reclaim: recapture_bar, failed_breakdown: breakdown_low}` | `engine/stock_identity/episodes.py` anchor-per-type construction (masterplan §7.3, review finding 25) |
| `grain_classes` | `["daily", "weekly"]` | mechanical classification of every observed W2 `grain` string (`engine.stock_identity.ruler.grain_class`); not itself a partition-computed statistic — a closed 2-class cadence taxonomy over the grain strings W2's nine family groups actually emit (`1D`, `3D`, `2W`, `W`, `1D-state-over-2D/3D-buckets`) |

None of these values were computed against `SI-SEALED-CAL-P1` by this registration — they are sealed W1 constants read as-is.

### 1.2 The PR-3 ruler-composite constant family — PENDING

`pr3.status == "pending_sealed_calibration"`, `pr3.recall_floor == null`, `pr3.lambda_fs == null`, `pr3.receipt == null`.

These fields are set **exactly once** by Task 3C's calibration-fire substrate + one-time
constant-setting act against the drawn-name component of `SI-SEALED-CAL-P1`
(`data/stock_identity/partition/partition_manifest_v1.json` → `calibration_partition`),
under rule-before-value discipline: the selection rule for each constant is declared in
`scripts/stock_identity_calibrate_w3.py` and this document BEFORE any value is computed
from partition data. The blind arm and the pilot/exemplar cohort contribute nothing to
this constant family. See §3 below, populated by Task 3C.

Fixture-only constants used in `tests/test_stock_identity_ruler.py` /
`tests/test_stock_identity_ruler_nulls.py` (e.g. `lambda_fs=0.5`, `recall_floor=0.3` /
`0.4`) exist only inside test code, are chosen purely for arithmetic legibility, carry
**no prior** on the value Task 3C later computes, and are never serialized to
`ruler_spec_v1.json` or readable from any script path.

## 2. Closed column contracts (plan Task 1 interface, Global Constraints)

* Per-fire (`engine.stock_identity.ruler.FIRE_METRIC_COLUMNS`): `event_id, family_key,
  symbol, episode_id, episode_type, episode_tier, grain, signal_known_ts, lead_lag,
  price_dist, atr_dist, mae_after, capture, false_start`.
* Unconditional block (`UNCONDITIONAL_BLOCK_COLUMNS`): `family_key, symbol, total_fires,
  attributed_fires, fires_per_name_year, episode_attribution_rate`.
* Cell aggregate (`CELL_METRIC_COLUMNS`): `family_key, episode_type, grain, n_fires,
  n_episodes, false_start_rate, flooding, recall_at_tier, zone_precision,
  relative_order, consistency, atr_dist_median_in_zone`.
* Graded composites: exactly `c_loc_r, c_loc_d` — `RulerSpec.graded_composites` is closed
  to these two, test-enforced (`test_ruler_spec_has_only_two_graded_composites`).
* No output column, and no identifier anywhere in `engine/stock_identity/ruler.py`, may
  carry `best_expert`, `expert_rank`, `winner`, `route` or `prophet_score`
  (`FORBIDDEN_OUTPUT_TOKENS`, test-enforced on both the source AST and every produced
  DataFrame's columns).

## 3. Task 3C receipt (populated when the one-time constant-setting act runs)

See `data/stock_identity/ruler/calibration_replay_manifest_v1.json` for the frozen
calibration-fire substrate manifest and this section's Task-3C amendment for the
per-constant selection rules, rule hashes, roster hash, replay/family/spec hashes and
computed values, or — if the runtime-estimate gate in the commissioning packet stopped
execution before the one-time act — the recorded estimate and the explicit statement
that the sentinels in `ruler_spec_v1.json` remain untouched.

*(This section is appended by Task 3C; it does not exist before that task runs.)*
