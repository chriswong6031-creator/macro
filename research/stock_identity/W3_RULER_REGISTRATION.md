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

## 3. Task 3C — STOPPED at the runtime-estimate gate (sentinels intact)

**Status as of this build packet: the one-time constant-setting act has NOT run.**
`ruler_spec_v1.json`'s `pr3` block still carries `status: "pending_sealed_calibration"`,
`recall_floor: null`, `lambda_fs: null`. No constant was set on a partial roster and no
constant family was set halfway — the stop is clean.

### 3.1 What was built and proven (all committed)

* `data/stock_identity/ruler/calibration_replay_manifest_v1.json` — Step 1, the frozen
  pre-run manifest: mechanical drawn-name roster (`calibration_partition.members`,
  sorted, `roster_sha256 = 2609c8ac83a54aef8a3d2a28077535783cf94f17054a40ad92043cdc1e2bad2e`,
  n=759), verified disjoint from the pilot cohort (21 names + `B`) and the untouched
  blind arm (229 names), the reused W2 entry points
  (`scripts.stock_identity_replay_pilot.stage_registry` / `_fire_fns` / `_spec_hashes` /
  `_ledgers` / `_load`) and their spec hashes as computed at manifest-freeze time, the
  `asof − 126 trading days` recent-history-guard rule, and the R2/store-host storage
  contract (large per-name event/history material is never committed; only this
  manifest and the post-run receipt are).
* `scripts/stock_identity_calibration_replay.py` — the substrate act
  (`run_substrate`), the roster-hash/disjointness checks, the recent-history-guard
  enforcement (`recent_history_cutoff` / `assert_recent_history_guard` /
  `truncate_to_guard`), the typed-blocker exit for unavailable names, zero-fire
  observation semantics, the `calibration_substrate: true` stamp, and the provenance
  receipt (module/function identities of the actually-invoked W2 entry points —
  verified against the REAL, unpatched pilot-replay module on one real drawn-roster
  name in `tests/test_stock_identity_w3_calibration.py::test_run_substrate_provenance_proves_genuine_invocation`).
* `scripts/stock_identity_calibrate_w3.py` — the one-time constant-setting act
  (`seal_ruler_spec`, refuses on re-run), the rule-before-value declarations
  (`RECALL_FLOOR_RULE`, `LAMBDA_FS_RULE` below), the declared ±20% diagnostic grid
  (`DIAGNOSTIC_GRID`) and fit-read look-budget constant, and
  `compute_constants_from_substrate`, which drives the ALREADY-FROZEN Tasks 2-3 ruler
  math (`compute_fire_metrics` / `aggregate_cell_metrics`) over calibration data.
* `tests/test_stock_identity_w3_calibration.py` — 27 tests, all green, proving every
  piece above on synthetic fixtures (per the freeze's "metric/composite primitives are
  frozen and tested on synthetic fixtures first" ordering law) plus a small number of
  cheap real-data checks (manifest roster-hash/disjointness, and the one-real-name
  provenance proof) that do not touch the bounded 759-name act.

**Declared rules (Step 2 — the hash exists and is recorded here BEFORE any value is
computed from partition data):**

* `recall_floor` — rule hash `7a2dd735ea8f01c5e802adbfb08422b4e722abaedb7e20666b5af79d1f5ae8fb`
  (`scripts.stock_identity_calibrate_w3.rule_hash(RECALL_FLOOR_RULE)`; see the module
  constant for the exact literal rule text — P25 of the cell-level `recall_at_tier`
  distribution over tier-eligible cells, rounded to the nearest 0.05).
* `lambda_fs` — rule hash `110a7757f44573cf2ef3bf2bcaa68736e1a0476e67f99cdfecd8e4a479027d1e`
  (`rule_hash(LAMBDA_FS_RULE)`; inverse P75 of the cell-level `false_start_rate`
  distribution over fired cells, rounded to the nearest 0.25).

Both hashes are deterministic and reproducible from the committed rule text:
`python3 -c "import scripts.stock_identity_calibrate_w3 as m; print(m.rule_hash(m.RECALL_FLOOR_RULE)); print(m.rule_hash(m.LAMBDA_FS_RULE))"`.

**Diagnostic grid + fit-read look budget (Step 3):** declared and unit-tested
(`DIAGNOSTIC_GRID` = 6 entries, `{recall_floor, lambda_fs} × {base, minus20, plus20}`;
`FIT_READ_LOOK_BUDGET = 3`, one look each for Q1/Q2/Q3). **Not yet written to the
production `data/trial_ledger.jsonl`** — registration is deferred to the session that
actually executes Step 4/5, since writing a TrialLedger entry for a constant family
whose values do not yet exist, in a session that is about to stop, risks an orphaned
registration in a shared cross-program ledger. `register_rules_and_grid` is fully
implemented and proven against a throwaway ledger
(`tests/test_stock_identity_w3_calibration.py::test_register_rules_and_grid_uses_a_throwaway_ledger`);
the executing session need only call it once against the real ledger before Step 4/5.

### 3.2 Runtime-estimate gate (COO adjudication)

Per the commissioning packet's bounded-runtime instruction, two linear-extrapolation
samples were measured against the REAL drawn roster before attempting the full
759-name act:

| sample | names | sample wall time | per-name avg | linear estimate (759 names) |
|---|---:|---:|---:|---:|
| first 5 (alphabetical) | 5 | 15.3s | 3.06s | **38.7 min** |
| first 15 (alphabetical) | 15 | 146.3s | 9.75s | **123.4 min** |

The 5-name sample alone would have cleared the 45-minute budget, but it is not
representative — its own alphabetically-first names happen to carry unusually short
history/low event counts. The larger, still-cheap 15-name sample (measured in ~2.5
minutes) more than triples the per-name estimate and puts the full-roster act at roughly
**two hours**, well over the 45-minute ceiling. Both estimates cover only the
fire-replay + episode-build stage (`run_substrate`'s own timed block); attribution,
constant computation and output writing are additional and were not separately timed
at 759-name scale, so 123 minutes is itself an underestimate of the true wall time.

**Decision: STOP.** The real drawn-roster substrate act (Step 4) and the one-time
constant-setting act (Step 5) did NOT run. `ruler_spec_v1.json` is byte-identical to
its Task 1 committed state. No partial roster was substituted and no constant was set
from a sample. This is reported to the commissioning COO for adjudication — running the
full act off the render path, in a longer-budget session, or with a narrower family
scope (e.g. dropping the ledger-dependent families that contribute near-zero rows
outside the pilot cohort) are among the options a follow-up act may choose; none of
those choices is made here.

### 3.3 Reproducing the estimate

```bash
python3 scripts/stock_identity_calibration_replay.py \
  --manifest data/stock_identity/ruler/calibration_replay_manifest_v1.json \
  --sample 15 --estimate-only
```
