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
* `tests/test_stock_identity_w3_calibration.py` — 50 tests, all green (27 original +
  23 added by the §4 repair pass below), proving every piece above on synthetic
  fixtures (per the freeze's "metric/composite primitives are frozen and tested on
  synthetic fixtures first" ordering law) plus a small number of cheap real-data
  checks (manifest roster-hash/disjointness, and the one-real-name provenance proof)
  that do not touch the bounded 759-name act.

**Declared rules (Step 2 — the hash exists and is recorded here BEFORE any value is
computed from partition data). Both rule declarations carry
`status: declared_pending_sol_rule_review` as of the §4 repair pass — see §4.4:**

* `recall_floor` — rule hash `671755ddae3e24b34722468d323a25e71bd1a1c174019a6863b1e1341657be69`
  (`scripts.stock_identity_calibrate_w3.rule_hash(RECALL_FLOOR_RULE)`; see the module
  constant for the exact literal rule text — P25 of the cell-level `recall_at_tier`
  distribution over cells with `n_episodes > 0` (at least one fire), rounded to the
  nearest 0.05). **This hash changed from the Task 3C value
  `7a2dd735ea8f01c5e802adbfb08422b4e722abaedb7e20666b5af79d1f5ae8fb`** — the §4 repair
  pass corrected the rule text's population-wording clause (it previously said
  "tier-eligible episode", which is a different quantity from the `n_episodes > 0`
  predicate the code has always applied) to name the actual predicate
  `compute_recall_floor` filters on. This is a textual accuracy fix, not a rule-form
  change: the SELECTION MATH is byte-identical, and no value had been computed under
  the old text to void.
* `lambda_fs` — rule hash `110a7757f44573cf2ef3bf2bcaa68736e1a0476e67f99cdfecd8e4a479027d1e`
  (`rule_hash(LAMBDA_FS_RULE)`; inverse P75 of the cell-level `false_start_rate`
  distribution over fired cells, rounded to the nearest 0.25). Unchanged by the §4
  repair pass — its population wording ("at least one fire") already matched the
  implementation.

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

## 4. Repair pass — adversarial review REPAIR-BEFORE-SEAL (SI-W3A-RULER-V1)

An Opus adversarial review of the state above found bounded, specified defects
(B1-B4, M1-M11 plus minors) and returned REPAIR-BEFORE-SEAL rather than clearing
the wave for the real Task 3C act. This section records what was fixed, on the
Sonnet build lane, with the frozen fix definitions the finding list specified.
**No composite value was computed and `ruler_spec_v1.json`'s PR-3 fields remain
`pending_sealed_calibration` throughout this repair** — the same stop condition
as §3.2 above, now with the defects that would have contaminated a future real
seal closed first.

### 4.1 B1 — partial seal + constant-shopping law

* `scripts/stock_identity_calibration_replay.py`: `--sample N` without
  `--estimate-only` now hard-refuses (`SampledSubstrateWriteRefused`) BEFORE
  `run_substrate` is ever called — a sampled run can no longer fall through to a
  real substrate-directory write with a status-OK provenance receipt.
  `--estimate-only` still writes timing output only, no substrate directory, no
  provenance receipt.
* `scripts/stock_identity_calibrate_w3.py`: before computing anything, the
  substrate's `provenance_receipt.json` is checked against the replay manifest's
  drawn roster — `n_names_attempted == len(roster)` AND
  `provenance["roster_sha256"] == manifest["roster"]["roster_sha256"]` — via
  `assert_full_roster_coverage`, refusing with the typed `PartialSubstrateError`
  on either mismatch.
* `--dry-run` now runs the real pipeline end-to-end (so a genuine wiring/input
  defect still raises) but masks every derived constant value
  (`build_dry_run_report` — no parameter through which a real value could reach
  the printed report) and never constructs a `TrialLedger` or calls
  `seal_ruler_spec`. The PRIOR implementation printed the full receipt
  (containing the real numeric values) unconditionally, before ever checking
  `args.dry_run`, and unconditionally wrote the diagnostic-grid/look-budget
  entries to the shared `data/trial_ledger.jsonl` even in dry-run mode — both
  fixed.

### 4.2 B3 — recent-history guard

`run_substrate` now computes `recent_history_cutoff(asof)` from the combined
calendar of the drawn roster's OWN loaded bars and truncates bars to it BEFORE
any event/episode is generated, so `ep_mod.build_catalog` — which can only ever
see through-cutoff bars — censors rather than resolves an episode whose
resolution would need later data. A defense-in-depth post-filter then drops any
event, and re-censors any episode, whose date still landed beyond the cutoff
despite the truncated input — measured against the REAL 759-name universe, at
least one reused W2 family fire function draws on state outside the bars frame
it was handed, so input-truncation alone did not provably bound every output
date. `assert_recent_history_guard` is repurposed to check the substrate's own
OUTPUTS (max event `signal_known_ts`, max episode `end_date`/`start_date`), not
self-truncated inputs; the prior input-side check survives as
`assert_bars_within_guard`. `scripts/stock_identity_calibrate_w3.py`'s second
barrier independently recomputes the same cutoff from its own asof/calendar,
cross-checks it against the substrate provenance's recorded
`recent_history_guard_cutoff` (refusing on mismatch), and re-runs the output
guard against the loaded substrate — never merely against a freshly
self-truncated bars copy. `data/stock_identity/ruler/calibration_replay_manifest_v1.json`'s
`clock.recent_history_guard_enforcement` prose now describes this real
mechanism.

### 4.3 B2, M1, M5, M6, M7, M10 — ruler metric/composite fixes

* **B2** (`engine/stock_identity/ruler.py::aggregate_cell_metrics`):
  `recall_at_tier`'s denominator is now every tier-eligible (tier<=2) episode in
  the `episodes` catalog for the cell's family/episode_type coverage
  (regardless of whether it ever fired), not merely episodes that already had a
  recorded fire — closing a coverage-gap-hides-in-the-denominator inflation.
* **M1** (`compute_composites`): a `NaN` `recall_at_tier` now fails the
  recall-floor gate closed (`c_loc_d` masked to `NaN`) instead of being treated
  as "not below floor" by the prior `.fillna(False)`; a new `c_loc_d_gate_reason`
  column records `"recall_at_tier_nan"` vs `"below_recall_floor"`.
* **M5** (`compute_composites`): C-LOC-D's rank normalization is now computed
  WITHIN each `(episode_type, grain)` stratum, never globally. Frozen in
  `data/stock_identity/ruler/ruler_spec_v1.json` as the non-PR-3 structural field
  `c_loc_d_rank_population: "episode_type_x_grain"`.
* **M6** (`compute_fire_metrics`): `mae_after` is now strictly forward-from-fire
  — window `(known_ts, known_ts + useful_zone_window_sessions]` in trading
  sessions — and uses `low` (long-side convention) with `close` fallback
  recorded in a new `mae_basis` column; it can never read a pre-fire bar (the
  prior window could span back to a lagging fire's anchor date, which sits
  BEFORE `known_ts`).
* **M7** (`aggregate_cell_metrics`): `flooding` is now
  `n_fires / (n_eligible_episodes_in_cell * useful_zone_window_sessions)` —
  fires per eligible-episode-session — instead of raw `n_fires / window`, so two
  cells at equal density but different absolute size report equal flooding.
* **M10** (`compute_unconditional_block`): gains a `universe` argument (the
  caller's roster x family universe) and emits an explicit
  `total_fires=0, fires_per_name_year=0.0, episode_attribution_rate=NaN,
  no_coverage=True` row for every zero-event pair instead of omitting it;
  `UNCONDITIONAL_BLOCK_COLUMNS` gains `no_coverage`.
  `scripts/stock_identity_build_ruler.py` now supplies this universe from the
  committed calibration replay manifest's `spec_hashes_at_manifest_freeze` keys
  (the W2 family registry's family_key set, frozen at manifest-freeze time)
  crossed with the pilot cohort's own symbols — deliberately NOT a live
  `stage_registry()` rebuild, which this build script has no need to re-invoke.

### 4.4 B4 — rule-review disclosure

The adversarial review previewed pilot/partial-derived values for the two PR-3
rule forms — `lambda_fs≈1.5`, `recall_floor≈0.0` — from design-tier material
(`SI-SEALED-CAL-P1` was never read for this preview). **Those previews are
VOID**: they were never computed under receipted rule text against the real
calibration-fire substrate, they predate this repair's B2/M1/M5/M6/M7/M10
metric fixes (any of which changes what the real substrate would compute), and
neither rule FORM has been ruled on by Sol. This repair does **not** change
either rule's form — `RECALL_FLOOR_RULE` and `LAMBDA_FS_RULE` in
`scripts/stock_identity_calibrate_w3.py` still compute the same P25-of-recall /
inverse-P75-of-false-start-rate selections (§1 above); RECALL_FLOOR_RULE's
population-wording clause was corrected for accuracy, §3.1 above, which is not
a form change. Both rule declarations now carry an explicit
`RULE_REVIEW_STATUS = "declared_pending_sol_rule_review"`, echoed into
`register_rules_and_grid`'s receipt and into the real seal receipt's
per-constant `recall_floor`/`lambda_fs` blocks (`"status"` field) — so a reader
of any future receipt can see the rule form was pending Sol review at seal
time without cross-referencing source. **No seal may treat either rule form as
accepted until Sol rules on it.**

### 4.5 M2/M3, M4, M11 — nulls/controls (`engine/stock_identity/ruler_nulls.py`)

* **M2/M3** `equal_proximity_control` now pairs fires only within the SAME
  episode (`groupby("episode_id")`), excludes same-family pairs from output
  without letting them consume any scan budget (grouped, uncapped per episode —
  fire counts per episode are small), and returns `(pairs, truncated_count)`;
  `truncated_count` is always `0` under this design and is surfaced in both a
  parquet-side summary (`equal_proximity_summary_v1.json`) and the build
  manifest JSON (`nulls.equal_proximity_pairs_truncated`).
* **M4** `grain_cadence_null` is now a deterministic seeded trading-session
  circular shift: one offset `K` in `[63, 252]` sessions is drawn per
  `(family_key, symbol)` and every fire in the group moves `K` sessions forward
  on that symbol's own trading calendar, wrapping within its coverage — never a
  calendar-day shift, never a non-trading date.
* **M11** `random_fire_null` now places each fire independently and uniformly
  on the symbol's own trading calendar (seeded, deterministic) rather than one
  block-translation offset for the whole group.
* Both seeded nulls' deterministic seeds are recorded in
  `scripts/stock_identity_build_ruler.py`: `RANDOM_NULL_SEED = 20260828`
  (unchanged), `GRAIN_CADENCE_NULL_SEED = 20260829` (new).

### 4.6 Minors

`availability_state` values in `build_support_coverage` are now drawn from the
freeze §7 taxonomy (`NO_COVERAGE` for missing bars, `MEASURED_ZERO` for a real
unattributed fire, `CENSORED` for a censored-episode attribution); `"resolved"`
is the one deliberate non-problem state, not drawn from that taxonomy.
`assert_capacity` now takes the `ChannelAConstitution` and reads
`constitution.capacity_denominator` instead of a hardcoded module default;
`count_p_eff` raises if `p_eff_terms.keys() != set(feature_subset)`. The support
frame gains `calendar_block_basis = "calendar_quarter_provisional"`, also
surfaced in the build manifest. The dead `random_null_attribution` variable was
removed from `stock_identity_build_ruler.py`. The vacuous same-family
equal-proximity test (a same-family pair that was never actually within
tolerance, so it proved nothing) was replaced with a genuinely-in-tolerance
same-family pair that must be excluded without displacing a legitimate
cross-family pair. Substrate work/registry files stay under the manifest's own
declared storage locations (scratch env var / this repo's `data`/`research`
trees) — never another session's scratchpad.
