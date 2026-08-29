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
`status: declared_pending_sol_rule_review` as of the §4 repair pass — see §4.4.
Both hashes were re-pinned a SECOND time by the §6 delta-review repair pass
(RULE-TEXT ITEMS, textual accuracy only) and a THIRD time by Sol's Ruling 1
(SI-W3A-RULER-V1 PR-3 seal law, §6.11 below) — a genuine rule-FORM change, the
first of the three re-pins that is. `recall_floor`'s hash was re-pinned a
FOURTH time by the SI-W3A-RULER-V1 pre-seal fix pass (item 5, §6.12 below) —
textual clarification only (the quantization tie convention), math unchanged.
Every prior hash for each constant is retained here as history; none was ever
computed against real partition data, so no value was voided by any re-pin:**

* `recall_floor` — rule hash `71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf`
  (`scripts.stock_identity_calibrate_w3.rule_hash(RECALL_FLOOR_RULE)`; see the module
  constant for the exact literal rule text — Ruling 1(a):
  `max(quantize_to_nearest_0.05(P25(recall_at_tier on the lawful sealed-calibration
  grading-cell population)), 0.05)`, over cells satisfying BOTH `n_episodes > 0`
  (the cell exists at all) AND a DEFINED `recall_at_tier` value (`.dropna()`). The
  `0.05` floor is now an explicit PREREGISTERED SUBSTANTIVE floor (never a
  rounding artifact); zero-recall cells are NEVER dropped or conditioned out (no
  A3 conditioning); P25 uses `numpy.percentile`'s `linear` interpolation method,
  passed explicitly. The `quantize_to_nearest_0.05` step is Python's built-in
  `round()` applied as `round(p25 / 0.05) * 0.05`; its tie convention at an exact
  `.5` boundary is banker's rounding (round-half-to-even), named explicitly in
  the rule text as of the pre-seal fix pass (item 5, §6.12).
  **Hash history:** Task 3C original
  `7a2dd735ea8f01c5e802adbfb08422b4e722abaedb7e20666b5af79d1f5ae8fb` ->
  §4 repair `671755ddae3e24b34722468d323a25e71bd1a1c174019a6863b1e1341657be69`
  (corrected the population-wording clause from the inaccurate "tier-eligible
  episode" to the actual `n_episodes > 0` predicate) ->
  §6 delta-review repair `c11789af43b1522c9169f89a92c3e7f4ccf79003cac7f97c3e9ed5342af81969`
  (named the SECOND conjunct, `.dropna()`, the code has always applied alongside
  `n_episodes > 0` — a cell can satisfy the count filter yet still carry a NaN
  `recall_at_tier`) -> **Ruling 1(a)**
  `b2f1e249d3f96951b1ddcee9eadaaa67d26b40a053f19176355f44a63a6a0045` (the
  `max(..., 0.05)` preregistered substantive floor — a genuine rule-FORM
  change; the PRIOR three hashes shared byte-identical selection math with only
  textual accuracy differences, but this one changes the actual formula: the
  0.05 floor is now applied unconditionally, never merely a side-effect of
  rounding) -> **pre-seal fix pass, item 5 (text-only)**
  `71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf` (names the
  `quantize_to_nearest_0.05` tie convention — Python's built-in `round()`,
  banker's rounding/round-half-to-even at an exact `.5` tie — explicitly in the
  rule text; `round()` was always the implementation, so the MATH is
  unchanged, only the prose now states the convention it has always had).
* `lambda_fs` — rule hash `8b149a753f5034c737eb0cc0c72d081e56e2d9431dd4adc01ac0cea8cc4ae366`
  (`rule_hash(LAMBDA_FS_RULE)`; Ruling 1(b):
  `median(recall_at_tier * zone_precision) / P75(false_start_rate)`, both over the
  SAME lawful (`n_episodes > 0`) population — the numerator's own population
  further restricted to a DEFINED product (`.dropna()` on
  `recall_at_tier * zone_precision`), the denominator's to a DEFINED
  `false_start_rate` (`.dropna()`, independent of the numerator's filter). P75
  uses `numpy.percentile`'s `linear` interpolation method, passed explicitly. NO
  rounding grid is applied (the prior "rounded to the nearest 0.25" step is
  gone). FAIL-CLOSED: valid only when numerator AND denominator are both finite
  and strictly > 0, else the constant-setting act refuses with a typed
  `BLOCKED_DEGENERATE_CALIBRATION` error/receipt
  (`scripts.stock_identity_calibrate_w3.BlockedDegenerateCalibrationError`) — NO
  epsilon, NO clipping, NO cap, NO alternate quantile, NO fallback fixed lambda
  anywhere in this path (grep-level test:
  `tests/test_stock_identity_w3_calibration.py::test_compute_lambda_fs_never_applies_epsilon_clipping_or_fallback`).
  **Hash history:** original/§4-repair
  `110a7757f44573cf2ef3bf2bcaa68736e1a0476e67f99cdfecd8e4a479027d1e` (unchanged by
  §4 — its population wording, "at least one fire", already matched the
  implementation) -> §6 delta-review repair
  `a1a2aaac5f9f77fe53f0c0d6440b81881d35b9f21883907ebfba5f4c08ef3d8a` (named the
  SECOND conjunct, `.dropna()`, the code has always applied — a cell can satisfy
  `n_fires > 0` yet still carry a NaN `false_start_rate` if every one of its fires
  lacks a resolved `false_start` flag, e.g. no anchor) -> **Ruling 1(b)**
  `8b149a753f5034c737eb0cc0c72d081e56e2d9431dd4adc01ac0cea8cc4ae366` (a WHOLLY
  DIFFERENT formula — `1 / max(P75(false_start_rate), 0.01)` replaced by
  `median(recall_at_tier * zone_precision) / P75(false_start_rate)`, fail-closed,
  no rounding grid — the largest rule-form change either constant has undergone).

All current hashes are deterministic and reproducible from the committed rule text:
`python3 -c "import scripts.stock_identity_calibrate_w3 as m; print(m.rule_hash(m.RECALL_FLOOR_RULE)); print(m.rule_hash(m.LAMBDA_FS_RULE))"`.

**B2/B2-residual disclosure (added by the §6 delta-review repair pass):** neither
rule-text re-pin above changes the rule FORM (P25 of `recall_at_tier` /
inverse-P75 of `false_start_rate`), but the QUANTITY `recall_at_tier` itself was
redefined twice by fixes to `aggregate_cell_metrics`, both under this same
unchanged rule form: **B2** (§4.3 below) changed `recall_at_tier`'s denominator
from "only episodes that already had a recorded fire" to "every tier-eligible
episode in the family's own symbol coverage, regardless of whether it ever
fired"; **B2-residual** (§6.1 below) then corrected HOW that coverage universe
itself is built (from `events`, not `fire_metrics`), which can only ever grow
the coverage set (never shrink it) relative to the B2-only fix. Every
`recall_floor` value ever computed against real partition data under
`RECALL_FLOOR_RULE`'s literal text is therefore taken over a DIFFERENTLY-DEFINED
`recall_at_tier` population than the rule's own P25-selection prose alone would
suggest to a reader unaware of these two implementation fixes — the rule form is
unchanged, but its input quantity's own definition moved underneath it twice.
This is disclosed here so Sol's eventual rule-form review evaluates the rule
against what it actually measures now, not against an earlier, narrower
`recall_at_tier` definition.

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

## 6. Delta-review repair pass — second pass, SI-W3A-RULER-V1 (adversarial delta review)

A second Opus adversarial delta review of the §4 repair pass closed most of the
prior findings but returned one seal-gating residual (B2-residual), two LAW
REGRESSIONS in the null transforms (M4-regression, M11-regression) relative to
the freeze's own §4.3 requirements, plus bounded minors and rule-text items.
This section records what was fixed. **No composite value was computed and
`ruler_spec_v1.json`'s PR-3 fields remain `pending_sealed_calibration`
throughout — the same stop condition as §3.2/§4 above.**

### 6.1 B2-residual — `family_symbol_universe` sourced from EVENTS, not fire_metrics

`aggregate_cell_metrics` (`engine/stock_identity/ruler.py`) gains a required
`events` parameter. `family_symbol_universe` — the per-family symbol coverage
set that bounds `recall_at_tier`'s eligible-episode population (B2, §4.3
above) — is now built from `events.groupby("family_key")` (every symbol a
family fired an event on, attributed or not), never from `fire_metrics`
(attributed-only, per the §4 repair). A `fire_metrics`-derived universe
silently excludes a symbol where a family FIRED but nothing ever attributed,
since such a fire never produces a `fire_metrics` row at all — exactly the
same shape of denominator under-count B2 itself closed, one layer up. Callers
(`scripts/stock_identity_build_ruler.py`,
`scripts/stock_identity_calibrate_w3.py::compute_constants_from_substrate`)
and every test call site were updated to pass `events`. Discriminating test:
`tests/test_stock_identity_ruler.py::test_family_symbol_universe_uses_events_not_fire_metrics_b2_residual`
— a symbol where a family fired but nothing attributed enters the recall
denominator only under the fix (fails under the old fire_metrics-derived
universe, per the test's own docstring). This same fixture shape was already
latent in the pre-existing
`test_recall_denominator_counts_eligible_episodes_regardless_of_fire` fixture
(its BBB reclaim attribution never resolves to a `fire_metrics` row due to an
`episode_index` quirk in the fixture itself, which the B2-residual fix now
correctly counts) — that test's expected `recall_at_tier` moved from `0.5` to
`1/3` accordingly, with its comment corrected to explain why.

### 6.2 M4-regression — `grain_cadence_null` restores cadence phase and stamp lag

The §4 repair's `grain_cadence_null` drew an UNCONSTRAINED offset `K` in
`[63, 252]` sessions and set BOTH `signal_ts` and `signal_known_ts` to the same
shifted value — which (a) can scatter a weekly-grain group's weekday PHASE
across any weekday (an unconstrained `K` is not a multiple of the weekly
period), and (b) collapses every event's own stamp lag
(`signal_known_ts - signal_ts`) to exactly zero, regardless of what it was
before. Both are freeze-law regressions relative to §4.2 ("Grain/timeframe is
always stratified") and the general PIT stamp-lag discipline this repo
enforces elsewhere. Fixed: `K` is now drawn as a multiple of the group's own
DOMINANT grain period in trading sessions
(`engine.stock_identity.ruler_nulls.GRAIN_PERIOD_SESSIONS`: `1D`->1, `3D`->3,
`W`->5, `2W`->10; any other observed grain label, e.g. the pilot cohort's
`2B`/`3B`/`1D-state-over-2D/3D-buckets`, defaults to period 1 — no phase
constraint), the shift is applied to `signal_ts`, and
`signal_known_ts = new_signal_ts + (orig_known_ts - orig_signal_ts)` is
reconstructed per event, preserving each event's own stamp lag exactly as a
timedelta. **Known limitation, disclosed rather than silently redesigned
around:** the grouping stays per `(family_key, symbol)` (the frozen shape); a
group that mixes multiple grains for the same symbol (observed in the real
pilot cohort's `sea_event_classes` family — 15 of 285 `(family_key, symbol)`
groups mix 2-3 distinct grains, e.g. `2B`/`3B`/`W`) applies the DOMINANT
grain's period to every fire in the group, so a MINORITY grain sharing that
group does not get its own phase preserved. Extending to a finer
`(family_key, symbol, grain)` grouping would be a larger, separately-decided
change and was not made here. Discriminating tests
(`tests/test_stock_identity_ruler_nulls.py`):
`test_grain_cadence_null_offset_is_a_multiple_of_the_grain_period`,
`test_grain_cadence_null_preserves_weekly_grain_weekday_distribution`,
`test_grain_cadence_null_preserves_stamp_lag_exactly`.

**MAJOR weekday-phase repair (delta-review third pass) — what is actually
guaranteed:** the §4-repair fix above constrains `K` to a MULTIPLE of the
grain period in SESSIONS, but a fixed session count is not a fixed number of
CALENDAR WEEKS on a real (holiday-bearing) trading calendar — the M4-regression
fix's own discriminating test only appeared to prove weekday preservation
because its fixture was a holiday-free `pd.bdate_range`, where session count
and calendar weeks coincide exactly with no gaps. On a real calendar, a
period-multiple `K` alone does NOT guarantee that every fire in a group lands
back on its own original weekday. `grain_cadence_null` now runs an explicit,
bounded, deterministic-seeded search
(`engine.stock_identity.ruler_nulls._weekday_preserving_offset`,
`GRAIN_CADENCE_PHASE_RETRY_BUDGET = 25`) per `(family_key, symbol)` group:

1. The group's earliest fire (the "anchor") is landed on its own weekday: the
   candidate `K`s in `[63, 252]` (still multiples of the grain period) are
   filtered to those that are weekday-admissible for the anchor alone.
2. Ordered nearest-to-the-original-seeded-draw first (deterministic
   tie-break), each anchor-admissible `K` is tried in turn — up to the retry
   budget — and accepted the moment EVERY fire in the group (not merely the
   anchor) is verified to land back on its own original weekday under that
   same shared `K`.
3. If the retry budget is exhausted with no `K` verified for every fire, the
   LARGEST anchor-admissible multiple is used as a last-resort shift (still a
   real, in-range, session-landing offset), and that group's output rows are
   marked `phase_preserved: false` rather than silently claiming a guarantee
   that was never actually verified. (Pathological last resort, essentially
   unreachable in practice: if NO multiple in the declared range is even
   anchor-admissible, the original unconstrained seeded draw is kept, also
   marked `phase_preserved: false`.)

**Exact guarantee:** for a group marked `phase_preserved: true`, EVERY fire in
that group is verified to land on its own original weekday under the null.
For a group marked `phase_preserved: false`, no such guarantee holds — the
shift is still a valid, real-session, period-constrained, in-declared-range
offset, but the weekday phase of one or more fires may have drifted, and this
is disclosed per row rather than hidden. A group whose symbol has no trading
calendar available at all (untouched, no shift applied) carries
`phase_preserved: <NA>`. Empirically, whether a group actually achieves
`phase_preserved: true` depends on how tightly clustered its fires are and how
the calendar's holidays happen to fall — a narrow, modestly-sized group (e.g.
10 fires within ~200 sessions) reliably finds a fully-verified `K`; a group
whose fires span YEARS (the REAL pilot cohort's actual weekly-grain groups —
see §6.10's real-scale finding, which measures `phase_preserved: false` for
ALL 35 of 35 real weekly-grain groups) can genuinely have no single shared `K`
in `[63, 252]` sessions that keeps every fire's weekday consistent, and is
honestly marked `phase_preserved: false` rather than shipping an unverified
claim. Discriminating tests
(`tests/test_stock_identity_ruler_nulls.py`, both on a holiday-perturbed
fixture, not the holiday-free one):
`test_grain_cadence_null_preserves_weekly_grain_weekday_distribution` (named
regression — the pre-pass-3 `grain_cadence_null`, an unconstrained
period-multiple draw with no weekday admissibility search, lands this exact
fixture/seed's fires on two distinct weekdays, `{3, 4}`, failing the
assertion the current implementation now satisfies),
`test_grain_cadence_null_phase_preserved_column_is_false_when_no_k_satisfies_every_fire`.

### 6.3 M11-regression — `random_fire_null` restores count/dwell matching (freeze §4.3 item 1)

The §4 repair's `random_fire_null` drew each fire's new session INDEPENDENTLY
and uniformly from the symbol's own trading calendar — count-matched, but it
destroys the inter-fire gap MULTISET (dwell/burstiness structure) entirely,
which is a weaker and differently-shaped null than freeze §4.3 item 1's literal
"Count/dwell-matched random fire placement" requirement. Fixed: per
`(family_key, symbol)` group, the ordered session-gap sequence between
consecutive fires (sorted by `signal_ts`) is PERMUTED with the seeded RNG, then
re-anchored at a seeded random start session drawn uniformly from every
position at which the whole permuted sequence still fits within the symbol's
trading-calendar coverage (wrapping forbidden). Because the sequence's total
span (`sum(gaps)`) is invariant under permutation and the real placement
already fit, a feasible anchor always exists — the freeze's "if impossible,
keep the real anchor" fallback is implemented as a defensive no-op guard, never
exercised in practice. Each event's own stamp lag is preserved exactly, via the
same `new_signal_ts + (orig_known_ts - orig_signal_ts)` reconstruction as M4.
Discriminating/restored tests (`tests/test_stock_identity_ruler_nulls.py`):
`test_random_fire_null_preserves_the_inter_fire_gap_multiset` (the restored
dwell-preservation "gap multiset preserved" test), `test_random_fire_null_preserves_stamp_lag_exactly`;
the separation assertion
(`test_grain_cadence_and_random_nulls_separate_from_real_placement`) and the
not-a-single-block-translation check
(`test_random_fire_null_does_not_degenerate_to_a_single_block_translation`)
are both kept, passing under the new implementation.

### 6.4 M5-residual — `c_loc_d_rank_population` is read, hashed, and enforced

`ruler_spec_v1.json` already shipped the non-PR-3 structural field
`c_loc_d_rank_population: "episode_type_x_grain"` (§4.3 above, M5), but
`RulerSpec.from_json` never parsed it, so it was absent from
`to_canonical_dict()` and therefore invisible to `spec_hash()` — a change to
this field would not have re-pinned the spec hash. Fixed: `RulerSpec` gains a
required `c_loc_d_rank_population: str` field, read by `from_json` (required
key, fails fast if the shipped file ever omits it) and carried in
`to_canonical_dict()`. **This changes `RulerSpec.spec_hash()` for the shipped
spec** (the field's VALUE is unchanged; the canonical-dict STRUCTURE gained a
key) — the new pilot-smoke spec hash is recorded in §6.7 below. Separately,
`compute_composites`'s silent global-rank fallback (the `elif` branch that
ran a GLOBAL rank across the whole cell population whenever `episode_type`/
`grain` columns were absent, defeating the exact stratification invariant M5
exists to guarantee) is REMOVED; a missing stratum column now raises the new
typed `MissingRankStratumColumnsError` instead. An unsupported
`c_loc_d_rank_population` value (anything other than the one currently-defined
`"episode_type_x_grain"`) raises a plain `ValueError`. Tests:
`test_ruler_spec_reads_c_loc_d_rank_population_from_json`,
`test_c_loc_d_rank_population_is_carried_in_canonical_dict`,
`test_c_loc_d_rank_population_change_changes_the_spec_hash`,
`test_compute_composites_raises_on_missing_stratum_columns`,
`test_compute_composites_raises_on_unsupported_rank_population`.

### 6.5 M3-minor — `equal_proximity_control` groups by (episode, grain)

`grain` is added to the equal-proximity group key: fires are now paired only
within the SAME episode AND the SAME grain (`groupby(["episode_id", "grain"],
dropna=False)`), never across grains — a daily-cadence fire and a
weekly-cadence fire at a similar ATR distance are measured over different
windows, so pairing them was never a genuine "similarly-placed" comparison.
`grain` is now a required input column (missing -> empty result, same
contract as the pre-existing `episode_id` requirement); every pre-existing
test fixture in `tests/test_stock_identity_ruler_nulls.py` was updated to
carry a `grain` column. Discriminating test:
`test_equal_proximity_control_never_pairs_across_grains_m3_minor`.

### 6.6 B3-minors, M8-minors, M10-minor

* **B3-minor (1), guard-drop visibility:** `scripts/stock_identity_calibration_replay.py`'s
  `main()` now surfaces `n_events_dropped_by_recent_history_guard` and
  `n_episodes_censored_by_recent_history_guard` in the run's own stdout OK
  payload (previously visible only in `provenance_receipt.json`) and emits a
  line-start `::warning title=si-w3a-substrate-guard::...` GitHub annotation
  (bare `print`, never through a logger — house law) when either count is
  nonzero.
* **B3-minor (2), cutoff harmonization:** `scripts/stock_identity_calibrate_w3.py`'s
  second barrier previously recomputed the recent-history cutoff from
  `_load_substrate_bars(episodes, asof)` — bars for only the symbols present in
  the substrate's OWN `episodes` frame, a narrower and potentially DIFFERENT
  symbol set than `run_substrate` used to compute the cutoff it actually
  recorded in provenance. Two different symbol sets can disagree on the
  126th-trading-session-back date purely from calendar composition, which
  would falsely accuse a genuinely-correct substrate of a guard violation it
  never committed. Fixed: the second barrier now compares the substrate
  provenance's recorded `recent_history_guard_cutoff` against the SINGLE
  frozen W1 source of truth — `data/stock_identity/constants/si_constants_v1.json`'s
  `calibration_history_cutoff` (`2026-02-11`, computed once at partition-build
  time by `scripts/stock_identity_build_atlas.py`'s
  `CALIBRATION_LOOKBACK_SESSIONS`-sessions-before-`asof` rule on the canonical
  market calendar) — via the new `frozen_calibration_history_cutoff()`
  function, reading a monkeypatchable `CALIBRATION_CONSTANTS_PATH` module
  constant. `scripts.stock_identity_calibration_replay.recent_history_cutoff`
  is no longer called from `stock_identity_calibrate_w3.py` at all. Tests:
  `test_frozen_calibration_history_cutoff_reads_the_real_committed_constant`,
  `test_main_refuses_when_recorded_cutoff_disagrees_with_frozen_constant`,
  `test_main_never_recomputes_cutoff_from_episodes_only_symbol_set`.
* **M8-minor (1), receipt-hash rename:** the printed receipt-inclusive spec
  hash (previously `sealed_spec_hash`) is renamed `sealed_spec_receipt_hash`
  and an assertion + comment now clarify its relationship to the receipt's own
  `spec_hash_after_seal` field: `sealed.spec_hash()` is the RECEIPT-INCLUSIVE
  hash of the spec exactly as written to disk (`pr3.receipt` embedded), while
  `spec_hash_after_seal` is the RECEIPT-EXCLUSIVE core hash
  (`pr3_receipt` projected to `None` by `core_spec_hash`, since a value cannot
  legally hash itself) — the two are asserted to differ.
* **M8-minor (2), registration-append recovery:** if
  `append_seal_receipt_to_registration` fails AFTER `seal_ruler_spec` already
  succeeded, `main()` now prints a line-start `::warning
  title=si-w3a-registration-append-failed::...` recovery message stating the
  durable receipt already lives in `ruler_spec_v1.json`'s `pr3.receipt` and
  that the registration line can be reconstructed from it via
  `format_seal_receipt_markdown(receipt)` — and explicitly does NOT attempt to
  unseal — before re-raising the original failure. Test:
  `test_registration_append_failure_prints_recovery_message_and_reraises`.
* **M10-minor:** `compute_unconditional_block` now raises the new typed
  `UnconditionalBlockUniverseError` if any OBSERVED `(family_key, symbol)`
  pair (present in `events`) is absent from a caller-supplied `universe` —
  the prior `universe_df.merge(total, how="left")` silently DROPPED such a
  pair from the output instead of surfacing the caller's incomplete universe
  declaration. Test:
  `test_unconditional_block_raises_when_universe_omits_an_observed_pair`.
* Also fixed: the dry-run branch's proof that
  `compute_constants_from_substrate` actually succeeded was a bare
  `assert isinstance(...)`, which `python -O` strips entirely — replaced with
  an explicit `if`/`raise TypeError`. Test:
  `test_dry_run_computation_proof_is_not_a_bare_assert`.

### 6.7 Rule-text items (doc + hash only, rule FORMS unchanged)

`RECALL_FLOOR_RULE` and `LAMBDA_FS_RULE` (`scripts/stock_identity_calibrate_w3.py`)
were each re-pinned a second time to name BOTH conjuncts their respective
`compute_*` functions have always applied — the count filter (`n_episodes > 0`
/ `n_fires > 0`) AND a `.dropna()` on the ranked column itself, which is a
genuine second filter (a cell can satisfy the count filter yet still carry a
NaN ranked value). Full hash history and the B2/B2-residual
differently-defined-quantity disclosure are recorded in §1.2/§3.1 above — this
subsection exists only to name the finding category (RULE-TEXT ITEMS) for the
delta review's own bookkeeping.

### 6.8 Interface deviations from plan text (for Task 4's author)

Four functions' actual signatures deviate from the plan text's original
description — recorded here so Task 4's author (or anyone else reading the
plan document alongside this registration) is not misled by the plan's prose
alone:

* `random_fire_null(events, bars_by_symbol, seed) -> pd.DataFrame` — the plan
  describes this as "independent per-fire random placement"; the actual
  (post-§6.3) implementation is count/dwell-matched (gap-permutation +
  re-anchor), per freeze §4.3 item 1's literal text, not independent placement.
* `grain_cadence_null(events, bars_by_symbol, seed) -> pd.DataFrame` — the plan
  describes a fixed `[63, 252]`-session offset; the actual (post-§6.2)
  implementation constrains that offset to a multiple of the group's dominant
  grain period, and reconstructs `signal_known_ts` from `signal_ts` plus the
  original per-event stamp lag rather than shifting `signal_known_ts` directly.
* `equal_proximity_control(metrics, tolerance_atr) -> tuple[pd.DataFrame, int]`
  — the plan describes pairing within the same episode only; the actual
  (post-§6.5) implementation additionally requires the same `grain`, and
  `grain` is now a required input column.
* `aggregate_cell_metrics(fire_metrics, episodes, spec, events, *, group_cols=...) -> pd.DataFrame`
  — the plan's original three-parameter signature
  (`fire_metrics, episodes, spec`) gains a required fourth positional
  parameter, `events` (post-§6.1), used to build `family_symbol_universe` from
  the full events frame rather than from `fire_metrics` alone. Every caller
  (`scripts/stock_identity_build_ruler.py`,
  `scripts/stock_identity_calibrate_w3.py`) was updated to pass it.

### 6.9 Delta-review third pass — remaining MINORs and a NIT

* **MINOR, cutoff harmonization completed:** §6.6's B3-minor (2) harmonized
  `stock_identity_calibrate_w3.py`'s second barrier onto the frozen
  `si_constants_v1.json` `calibration_history_cutoff`, but
  `scripts/stock_identity_calibration_replay.py`'s `run_substrate` — the FIRST
  barrier, the one that actually executes the (potentially multi-hour) 759-name
  replay — still re-derived its own cutoff via `recent_history_cutoff()` on
  whatever symbol set/calendar that particular run happened to have bars
  loaded for. A disagreement between the two would only surface after the full
  replay completed, when the second barrier's comparison raised. Fixed:
  `run_substrate` now reads the cutoff from the SAME frozen source
  (`frozen_calibration_history_cutoff()`, `CONSTANTS_PATH`'s
  `calibration_history_cutoff`) directly. `recent_history_cutoff()` is kept and
  still called, but only as a cheap CROSS-CHECK against the frozen value — a
  disagreement is surfaced immediately as a line-start
  `::warning title=si-w3a-substrate-cutoff-disagreement::...` GitHub annotation
  (bare `print`, `flush=True` — house law), never raised, and the frozen value
  always wins. Tests:
  `test_frozen_calibration_history_cutoff_reads_the_real_committed_constant_calib_replay`,
  `test_run_substrate_reads_cutoff_from_frozen_constants_not_recomputed`,
  `test_run_substrate_warns_but_does_not_raise_on_cutoff_disagreement`,
  `test_run_substrate_does_not_warn_when_frozen_and_derived_cutoff_agree`.
* **MINOR, eligible-episode receipt fields:** the substrate provenance receipt
  (`provenance_receipt.json`) gains `n_eligible_episodes`, `n_eligible_censored`,
  and `censored_share_of_eligible`, computed from the substrate's own episode
  catalog restricted to `tier <= 2` (the same "useful-zone" tier floor
  `engine.stock_identity.episodes.durable_lows`'s default `min_tier` uses) —
  so the censored-mass question ("how much of the eligible population never
  resolved") is answerable directly from the receipt at 759-name scale,
  before any PR-3 constant is even read, rather than requiring a reader to
  reload the full `calibration_episodes_v1.parquet`. `censored_share_of_eligible`
  is `None` (never a spurious `0.0`) when there are zero eligible episodes.
  Tests: `test_run_substrate_provenance_carries_eligible_episode_fields`,
  `test_run_substrate_eligible_episode_fields_are_zero_on_no_episodes`.
* **NIT, proximity-pair grain column:** `equal_proximity_control`'s output
  pair rows now carry a `grain` column recording the (single, shared) grain
  that scoped the pair (the `(episode_id, grain)` group key §6.5 already
  groups by) — `PROXIMITY_PAIR_COLUMNS` gained the field. A reader of the pair
  output alone can now see which cadence bucket produced a pair without
  rejoining `metrics`. Test:
  `test_equal_proximity_control_pair_rows_carry_the_scoping_grain`.

### 6.10 Pilot smoke re-run and spec hash

`python3 scripts/stock_identity_build_ruler.py --pilot --include-nulls --output-dir <dir>`
re-run after this repair pass, PR-3 still `pending_sealed_calibration`:

* **New `spec_hash`: `43bb66b06a27a896e27c57c7f08deb1dfbc7b2f22fdd8faa778532d78c626bfb`**
  — changed from the §4-repair-pass value because `c_loc_d_rank_population` is
  now carried in `RulerSpec.to_canonical_dict()` (§6.4); the field's VALUE
  (`"episode_type_x_grain"`) is unchanged, only the canonical-dict structure
  gained a key that the hash function has always covered.
* 50 cell rows; `recall_at_tier` defined on 34/50 cells (mean 0.0724, median
  0.0236, P25 0.0011, max 0.3881); `false_start_rate` defined on all 50 cells
  (mean 0.4271, median 0.5048, P75 0.6482, max 0.8199). All 50 cells satisfy
  `n_episodes > 0` and `n_fires > 0`. This distribution (post-B2-residual, so
  the recall denominator is now built from the full events-derived symbol
  coverage) is handed to Sol alongside the rule-form review as the actual
  population `RECALL_FLOOR_RULE`/`LAMBDA_FS_RULE` would draw P25/inverse-P75
  from, per §1.2's disclosure above.
* Null-phase/stamp-lag preservation verified directly against this run's own
  parquet outputs: both `null_grain_cadence_events_v1.parquet` and
  `null_random_fire_events_v1.parquet` reproduce the real events'
  `signal_known_ts - signal_ts` lag EXACTLY, row for row (9,371 of 31,119 real
  events carry a nonzero lag; both nulls preserve every one of them).
  `random_fire_null`'s inter-fire gap MULTISET was independently re-verified
  per `(family_key, symbol)` group against this same run's real events (257
  groups checked, 0 mismatches). `equal_proximity_pairs = 4820` under the new
  (episode, grain)-grouped contract, `equal_proximity_pairs_truncated = 0`,
  and every pair row now carries the scoping `grain` (§6.9 NIT).
* **Weekday-phase MAJOR fix — real-scale finding (delta-review third pass):**
  the real pilot cohort's actual weekly-grain (`grain="W"`) events carry a
  Friday share of **0.7589** (2,684 real `W`-grain events; not the ~0.622
  figure named in the commissioning packet, which this run does not
  reproduce — reported as measured, not adjusted to match). Under the null,
  the weekly-grain rows' weekday share is **NOT preserved in aggregate**
  (Friday share drops to 0.2575; `phase_preserved` is `False` for all 2,684 of
  2,684 weekly-grain rows, and for all 35 of 35 `(family_key, symbol)`
  weekly-grain groups, including single/few-fire groups). This is a
  DISCLOSED, verified structural finding, not an algorithm defect: every real
  pilot weekly-grain group spans MULTIPLE YEARS (the rarest, e.g.
  `weekly_washout_turn`/`AG`, 15 fires from 2018-12-10 to 2026-06-22), and a
  brute-force scan of the ENTIRE declared `[63, 252]`-session range (every
  multiple of the grain period, not merely the seeded/anchor-admissible
  candidates the real search tries) proves the true ceiling for two example
  groups: `weekly_washout_turn`/`KO` (85 pure-`W` fires) tops out at 28/85
  (33%) fires weekday-matched under its single best-possible shared `K` in
  range; `sea_event_classes`/`KO` (1,719 mixed-grain fires, dominant grain
  `2B`) tops out at 115/337 even ignoring the mixed-grain dominant-period
  limitation entirely. No algorithm operating within the FROZEN shape (one
  shared `K` per `(family_key, symbol)` group, drawn from the declared
  `[63, 252]`-session range) can close this gap for groups spanning years —
  it is a property of how many synthetic-calendar holidays accumulate
  differently across DIFFERENT starting epochs within that same session-count
  window, not a search-quality defect. The discriminating unit tests
  (`test_grain_cadence_null_preserves_weekly_grain_weekday_distribution`,
  `test_grain_cadence_null_phase_preserved_column_is_false_when_no_k_satisfies_every_fire`)
  prove the search DOES achieve full, verified weekday preservation for a
  narrower/tighter group (10 fires within ~9 months) and DOES honestly
  disclose `phase_preserved: false` rather than silently claiming success
  when it cannot — the mechanism is correct; the pilot cohort's real group
  time-spans are simply outside what the frozen session-range design can
  guarantee. See the commissioning packet's own delta-review report for the
  disposition of this finding.
* This build packet does not execute the real 759-name calibration-fire
  substrate act (out of scope per the commissioning packet), so the two B3-minor
  guard-drop counters (`n_events_dropped_by_recent_history_guard`,
  `n_episodes_censored_by_recent_history_guard`) cannot be observed from a live
  run here; their surfacing/annotation behavior is proven on synthetic
  fixtures in `tests/test_stock_identity_w3_calibration.py` (e.g.
  `test_run_substrate_drops_or_censors_outputs_beyond_the_recent_history_cutoff`).

## 6.11 Sol's three PR-3 seal-law rulings (SI-W3A-RULER-V1) — implementation

Sol closed the three scientific-law decisions blocking the PR-3 seal with exact
forms. This packet implements all three as ruled, without executing the real
substrate or the seal itself (out of scope; `ruler_spec_v1.json`'s `pr3` block
stays byte-intact and `data/trial_ledger.jsonl` is untouched).

### Ruling 1 — PR-3 constant rules (`scripts/stock_identity_calibrate_w3.py`)

Both `RECALL_FLOOR_RULE` and `LAMBDA_FS_RULE` are REPLACED with new exact
forms (rule-form change, not textual accuracy — see the re-pinned hashes in
§3.1 above):

* **`recall_floor`** = `max(quantize_to_nearest_0.05(P25(recall_at_tier on
  the lawful sealed-calibration grading-cell population)), 0.05)`. The `0.05`
  minimum is now an explicit, PREREGISTERED SUBSTANTIVE floor — stated as
  such in the rule text — never a rounding-artifact side effect. Zero-recall
  cells are never dropped or conditioned out of the population (no A3
  conditioning): `compute_recall_floor`'s population predicate is unchanged
  from the pre-Ruling-1 form (`n_episodes > 0` AND a defined `recall_at_tier`)
  and applies the P25 over the FULL such population, including any
  `recall_at_tier == 0.0` row.
* **`lambda_fs`** = `median(recall_at_tier * zone_precision) /
  P75(false_start_rate)`, on the SAME lawful population, with NO rounding
  grid (the prior "rounded to the nearest 0.25" is gone — the result is the
  exact quotient). FAIL-CLOSED: valid only when the numerator (median of the
  product) AND the denominator (P75 of `false_start_rate`) are BOTH finite
  and strictly greater than zero. Any other outcome raises the typed
  `BlockedDegenerateCalibrationError` (`BLOCKED_DEGENERATE_CALIBRATION`
  status, a JSON receipt naming the numerator/denominator/population size and
  the failing reason, printed via `::error` and returned as exit code `3`
  from `main()`) — there is NO epsilon, NO clipping, NO cap, NO alternate
  quantile, and NO fallback fixed lambda anywhere in `compute_lambda_fs`'s
  code (grep-enforced by
  `test_compute_lambda_fs_never_applies_epsilon_clipping_or_fallback`, which
  scans the function's CODE — not its docstring, which names the prohibition
  in prose — for rescue-shaped tokens). Both rules share one frozen
  population predicate, `_lawful_calibration_population(cells)` =
  `cells.loc[cells["n_episodes"] > 0]`, with each metric's OWN independent
  `.dropna()` applied on top (a cell can satisfy the shared gate yet still
  carry a NaN on any ONE of `recall_at_tier` / `zone_precision` /
  `false_start_rate` independently). Both rules pin the quantile convention
  explicitly (`numpy.percentile(..., method="linear")`) and rely on the
  pre-existing deterministic JSON serialization (`sort_keys=True`) for the
  sealed receipt/spec. Registered BEFORE any partition read via the same
  rule-before-value discipline the module has always used
  (`register_rules_and_grid` hashes the frozen module-level rule-text
  constants before Step 4/5 ever touch computed values). The ±20% diagnostic
  grid (`DIAGNOSTIC_GRID`) is unchanged mechanics — still diagnostic-only,
  still registered before execution, never read back to reselect a constant.

Tests (`tests/test_stock_identity_w3_calibration.py`):
`test_rule_hashes_match_the_registration_document`,
`test_rule_hashes_match_the_currently_committed_registration_values`,
`test_compute_recall_floor_is_p25_rounded_to_nearest_005` (still exercises the
shared quantization/floor path),
`test_compute_lambda_fs_is_median_product_over_p75_false_start_rate`,
`test_compute_lambda_fs_rounds_nothing`,
`test_compute_lambda_fs_raises_typed_blocked_degenerate_on_all_nan_population`,
`test_compute_lambda_fs_raises_typed_blocked_degenerate_on_zero_denominator`,
`test_compute_lambda_fs_raises_typed_blocked_degenerate_on_zero_numerator`,
`test_compute_lambda_fs_never_applies_epsilon_clipping_or_fallback`.

### Ruling 2 — availability-based recall denominator (`engine/stock_identity/ruler.py`)

`aggregate_cell_metrics`'s recall-denominator eligibility universe is
REPLACED: the prior `family_symbol_universe` (built from `events` — every
symbol a family FIRED on anywhere, attributed or not — "fired-on" coverage)
is gone. A new function, `build_family_episode_availability(episodes,
family_keys, family_registry=None, bars_by_symbol=None)`, builds one row per
`(family_key, tier-eligible episode)` pair — REGARDLESS of whether that
family ever fired on that episode's symbol — carrying a typed
`availability_state`:

* `"ELIGIBLE"` (`FAMILY_ELIGIBLE_STATE`) — the W2 family registry's own
  `family_first_available` boundary does not postdate the episode's window
  (start through end, or start alone when end is undefined) AND
  `bars_by_symbol` covers the episode's window for that symbol. A PRESENT
  `family_first_available` field whose value is `None`/falsy means "no known
  start boundary" — the same convention already used throughout
  `data/stock_identity/expert_events/family_registry.json` (21 of 24
  committed entries carry `null`), `engine/stock_identity/replay/registry.py`,
  and `scripts/stock_identity_replay_pilot.py`.
* `"NOT_YET_AVAILABLE"` — the registry's `family_first_available` postdates
  the episode's entire window.
* `"NO_COVERAGE"` — bars were supplied but do not cover the episode's
  instrument/window.
* `"UNESTIMABLE"` — lawful availability cannot be established at all: no
  `family_registry` was supplied, the `family_key` is absent from it, the
  registry entry genuinely lacks the `family_first_available` field, or no
  `bars_by_symbol` was supplied. This is the fail-closed path Ruling 2(c)
  requires — missing eligibility evidence is TYPED, never silently treated
  as available nor folded into the old fired-on read.

`aggregate_cell_metrics` gained two new keyword-only parameters,
`family_registry` and `bars_by_symbol` (both default `None`, preserving the
prior call signature's positional shape — `events` is retained as a required
positional parameter for call-site compatibility only and is no longer read
for eligibility). Instrument/date/grain availability collapses to (ii) input
bars coverage by design, not omission: the committed provenance carries no
grain-differentiated availability signal (one symbol's OHLCV underlies every
grain a family might read it at). Applied identically to the pilot
diagnostics build (`scripts/stock_identity_build_ruler.py`, which now loads
the committed `family_registry.json` via `_family_registry()`) and the
sealed-calibration path (`compute_constants_from_substrate` in
`scripts/stock_identity_calibrate_w3.py`, which defaults to
`load_family_registry()`'s committed read when the caller does not supply an
explicit `family_registry`).

Sol's three required regressions (`tests/test_stock_identity_ruler.py`):

* **(a)** `test_recall_denominator_grows_from_available_zero_fire_symbol_ruling2_regression_a`
  — a symbol with eligible episodes and ZERO fires (never even appearing in
  `events`) GROWS the denominator (1.0 -> 0.5) and cannot improve recall.
* **(b)** `test_recall_denominator_excludes_not_yet_available_symbol_ruling2_regression_b`
  — a symbol whose family only became available after the episode's entire
  window never enters the denominator, even with full bars coverage.
* **(c)** `test_recall_denominator_missing_eligibility_evidence_never_falls_through_to_fired_on_ruling2_regression_c`
  — with no `family_registry`/`bars_by_symbol` supplied, `recall_at_tier` is
  `NaN` (every episode types `UNESTIMABLE`), never silently computed off the
  discarded fired-on universe.

Every pre-existing recall/flooding test in `test_stock_identity_ruler.py` that
exercised the OLD fired-on universe (`test_recall_denominator_counts_eligible_episodes_regardless_of_fire`,
`test_family_symbol_universe_uses_events_not_fire_metrics_b2_residual` — renamed
to a regression-(a)-shaped test above — and
`test_flooding_is_invariant_to_cell_size_at_equal_density`) was updated to
supply an unrestricted `family_registry` + `bars_by_symbol` explicitly, since
the eligibility universe is now genuinely UNIVERSE-WIDE per lawfully-available
family (not scoped to "symbols this family happens to have fired on") — the
flooding-invariance test now computes each family's cell via its OWN
independent call (disjoint `episodes`/`bars_by_symbol` per family) rather than
one combined call, since within one combined call every lawfully-available
family now sees every tier-eligible episode in that catalog regardless of
symbol, which is the intended fix (a silent, fired-on-biased recall universe),
not a defect to route around.

### Ruling 3 — cadence-phase null D3b (`engine/stock_identity/ruler_nulls.py`)

`grain_cadence_null`'s shape changes: it keeps the ONE deterministic,
period-constrained, seeded SHARED base shift `K` per `(family_key, symbol)`
group (unchanged draw mechanics — a multiple of the group's dominant grain
period, from the declared `[63, 252]`-session range). AFTER that base shift,
each fire is INDEPENDENTLY snapped from its own post-`K` position to the
NEAREST actual trading session carrying that fire's own ORIGINAL weekday
(`_snap_to_own_weekday`), bounded to `GRAIN_CADENCE_SNAP_BOUND_SESSIONS` (4)
sessions each way, deterministic tie-break toward the EARLIER session at
equal distance. This supersedes the delta-review third pass's single-shared-K
weekday SEARCH (§6.9 above): that design could never achieve full-group
weekday agreement for real pilot-scale weekly-grain groups spanning multiple
years (verified by brute force, §6.10 above) — per-fire snapping makes exact
weekday preservation achievable per fire regardless of group span, at the
declared cost of a small, disclosed, per-fire gap perturbation.

Event COUNT, event IDENTITY (`event_id`), and each event's own stamp lag
(`signal_known_ts - signal_ts`) are still preserved exactly. The group's
CHRONOLOGICAL fire order is verified preserved in the new (snapped)
positions: an INVERSION (a later fire snapping before an earlier one) or a
NEW COLLISION (two originally-DISTINCT fires snapping to the same session —
a pre-existing tie in the original data is exempt from this check, since two
fires already indistinguishable in time were not distorted by staying tied)
both refuse the group's shift. If any fire in the group has no lawful
same-weekday target within the snap bound, OR the group's snapped positions
collide/invert, the WHOLE group is marked with a new typed column,
`cadence_null_state ∈ {"applied", "unestimable", "no_calendar"}`, and left
COMPLETELY UNTOUCHED (original `signal_ts`/`signal_known_ts` preserved) when
not `"applied"` — never a forced or partially-broken shift. Two more
published per-row columns: `phase_preserved` (nullable boolean — `True` for
every row of an `"applied"` group, `<NA>` otherwise) and `snap_sessions`
(nullable Int64 — the signed per-fire snap distance, stage 2 only,
`<NA>` for non-`"applied"` rows). A new function,
`grain_cadence_null_summary(out)`, reports group/summary gap-distortion
statistics (the distribution of `|snap_sessions|`, per-group max,
unestimable-row/group counts) — wired into
`scripts/stock_identity_build_ruler.py`'s null manifest section
(`manifest["nulls"]["grain_cadence_summary"]`).

`_weekday_preserving_offset` and `GRAIN_CADENCE_PHASE_RETRY_BUDGET` (the
delta-review third pass's per-group weekday SEARCH mechanism) are removed —
superseded, not merely deprecated.

Docstring/registration update: null #6 (`grain_cadence_null`) is now
EXACT-cadence-PHASE with a DECLARED BOUNDED gap perturbation, explicitly NOT
dwell-matched (per-fire independent snapping can move different fires in a
group by different amounts, so the inter-fire session-gap multiset is no
longer preserved exactly). Null #1 (`random_fire_null`) is UNCHANGED and
still carries the exact count/dwell law — this remains the one null in the
pair that is dwell-matched.

Tests (`tests/test_stock_identity_ruler_nulls.py`):
`test_grain_cadence_null_preserves_weekday_for_every_non_unestimable_row`
(real-holiday-calendar fixture proves exact weekday preservation for every
`"applied"` row),
`test_grain_cadence_null_preserves_chronological_order_when_applied` (order
preserved),
`test_grain_cadence_null_preserves_stamp_lag_exactly` (lag preserved,
unchanged from the prior pass),
`test_grain_cadence_null_snap_sessions_within_declared_bound` (snap bound
respected),
`test_grain_cadence_null_dense_cluster_marks_group_unestimable` (a dense,
wide weekly-grain group on the holiday-perturbed calendar produces a
collision/inversion for at least one seed in `range(60)`, yielding the typed
`"unestimable"` state for every row, group left byte-identical to the
original input),
`test_grain_cadence_null_no_calendar_state_is_typed`,
`test_grain_cadence_null_base_shift_is_within_declared_session_range` /
`test_grain_cadence_null_base_shift_is_a_multiple_of_the_grain_period`
(reconstruct the pre-snap base `K` from the published `snap_sessions` column
— the FULLY-realized shift, base + snap, is no longer itself bounded to
`[63, 252]` sessions, since the declared snap perturbation is layered on top;
this is an intentional consequence of Ruling 3's shape, not a defect),
`test_grain_cadence_null_summary_reports_gap_distortion_stats`, plus the
retained separation assertion
(`test_grain_cadence_and_random_nulls_separate_from_real_placement`) and the
pre-existing determinism/no-non-session-landing tests, all unchanged.

## 6.12 Pre-seal fix pass (SI-W3A-RULER-V1) — six bounded mechanical closures

Six items returned by the seal-path delta review as SEAL-PATH-CLEAN with
bounded pre-act conditions and disclosure minors. All are purely additive or
textual; the metric/rule-form math frozen by Sol's three rulings (§6.11) is
untouched, the real substrate/seal act is out of scope, `ruler_spec_v1.json`'s
`pr3` block stays byte-intact (`pr3.recall_floor`/`pr3.lambda_fs` still
`null`, `pr3.note` unchanged — verified via `git diff`), and
`data/trial_ledger.jsonl` is untouched.

**Item 1 — PRE-ACT CONDITION 2, ruler-implementation hash in the seal
receipt.** `build_seal_receipt` (`scripts/stock_identity_calibrate_w3.py`)
now records a `ruler_implementation_sha256` block — the exact byte-for-byte
sha256 of `engine/stock_identity/ruler.py` and `engine/stock_identity/
ruler_nulls.py` AT SEAL TIME, keyed `ruler_py`/`ruler_nulls_py` — alongside
the existing replay-manifest/W2-family-registry/substrate-provenance hashes.
The two new module-level path constants, `RULER_IMPLEMENTATION_PATH` and
`RULER_NULLS_IMPLEMENTATION_PATH`, are monkeypatchable like every other path
constant in the module. This closes the freeze's voiding clause for a
post-value implementation change: a value computed under one version of
`ruler.py`/`ruler_nulls.py` and then re-served after either module changed is
now detectable from the receipt alone, without a separate provenance
channel. Rendered into the registration-doc append block by
`format_seal_receipt_markdown` alongside the other hashes. Purely additive —
no existing receipt field's shape or meaning changed.

Test (`tests/test_stock_identity_w3_calibration.py`):
`test_build_seal_receipt_carries_ruler_implementation_hashes` (fixture-copy
proof: pointing the two path constants at throwaway files, changing ONE
file's bytes moves only its recorded hash), plus the pre-existing
`test_build_seal_receipt_carries_every_m8_field` and
`test_format_seal_receipt_markdown_contains_every_hash`, both extended to
require the new field/hashes.

**Item 2 — MILESTONE DISCLOSURE, null #6 coverage on the real pilot.** Stated
plainly, as a limitation, not folded into the "worked as designed" framing
above: on the real dense pilot cohort, `grain_cadence_null` (null #6) typed
**92 of 285** `(family_key, symbol)` groups `"applied"` and **193 of 285**
`"unestimable"` — **1,661 of 31,119 rows (5.3%)** evaluated under the null,
**94.7% dark** (left untouched, no cadence-null read available for those
rows). This is a direct, measured consequence of Ruling 3's per-fire
weekday-snap-within-a-4-session-bound design on real pilot-scale grain
groups: a group with fires spread wider than the bound in NO single shared
base-K position, for enough of its fires, types `"unestimable"` rather than
forcing a partial or incoherent shift (§6.11 above). **Whether 5.3% coverage
discharges freeze §4.3 item 6 (the null-#6 requirement) is returned to Sol in
the milestone packet** — this packet does not adjudicate that question, only
measures and discloses the real number. (Reproduced via `python3
scripts/stock_identity_build_ruler.py --pilot --include-nulls --output-dir
<dir>`; `null_grain_cadence_events_v1.parquet`'s `cadence_null_state` column,
grouped by `(family_key, symbol)`.)

**Item 3 — MINOR, guard honesty for the no-epsilon/no-fallback test.**
`test_compute_lambda_fs_never_applies_epsilon_clipping_or_fallback`
(`tests/test_stock_identity_w3_calibration.py`) was mutation-proven
non-discriminating for its `max`/`min`-related string tokens: a shape like
`numerator = float(max(product.median(), 0.01)) if not product.empty else
float("nan")` rescues the RAW expression before it is ever bound to a
variable named `numerator`, so a plain `"max(numerator"` token grep never
sees it, while the plain string check passes unchanged. **Repaired via AST
strengthening** (the preferred option), not a docstring-only rescope: the
test now `ast.parse`s the module, walks `compute_lambda_fs`'s own
`ast.Assign` statements, and fails on ANY `max`/`min`/`np.maximum`/
`np.minimum`/`np.clip` call appearing ANYWHERE in the RHS subtree of an
assignment whose target is `numerator` or `denominator` — this catches the
rescue regardless of whether it wraps the bare variable or the raw
expression feeding it. Verified two ways before landing: (a) the new AST
scan flags the `max(product.median(), 0.01)` mutation shape above when
injected into a parsed copy of the source, and (b) the OLD plain-string-token
scan does NOT flag that same mutation (confirming the gap was real, not
theoretical). The remaining plain-string check (`eps =`/`eps=`/`+ eps`/`or
0.01`/`fallback`) is retained for the vocabulary an AST call-shape scan
cannot see (bare identifier/literal patterns, not function calls). The
REAL guard remains the three behavioral degenerate-input tests directly above
it in the file (`..._on_all_nan_population`, `..._on_zero_denominator`,
`..._on_zero_numerator`) — this test is a second, static line of defense, and
its docstring now says so explicitly rather than merely asserting the
prohibition.

**Item 4 — NIT, `phase_preserved` weekday clarification.** One sentence added
to `grain_cadence_null`'s docstring (`engine/stock_identity/ruler_nulls.py`):
"preserved" weekday means the weekday of the trading SESSION a fire's
original `signal_ts` maps to (`calendar.searchsorted(signal_ts,
side="left")`), not necessarily the raw stamp's own calendar-day weekday — a
`signal_ts` that itself lands off-session (weekend/holiday) maps forward to
the next session, and it is THAT session's weekday the null preserves.
Measured on the real pilot cohort: **36 of 1,661 "applied" rows (~2.2%)**
carry a raw `signal_ts` that is not itself a trading day (i.e. its own
calendar date is absent from that symbol's trading calendar). Documentation
only — no behavior changes; `_snap_to_own_weekday`'s target weekday was
always computed this way (`original_weekdays = [calendar[int(p)].weekday()
for p in positions]`, §"Ruling 3" above), this item only names it.

**Item 5 — NIT, quantization tie convention named in `RECALL_FLOOR_RULE`.**
The rule text now states the `quantize_to_nearest_0.05` step's tie
convention explicitly: it is Python's built-in `round()`
(`round(p25 / 0.05) * 0.05`, exactly what `compute_recall_floor` has always
computed), whose behavior at an exact `.5` boundary is banker's rounding
(round-half-to-even) — named here rather than left as an unstated default.
**Math is unchanged** (`round()` was always the implementation; only the
prose now says so), so this is a text-clarification-only re-pin, following
the same disclosure pattern as every prior rule-text-only change in §3.1
above (the population-wording fixes) rather than the rule-FORM changes
(Ruling 1). `recall_floor`'s hash moves a FOURTH time as a direct
consequence — old `b2f1e249d3f96951b1ddcee9eadaaa67d26b40a053f19176355f44a
63a6a0045` (Ruling 1(a)) -> new
`71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf` — recorded
in §3.1 above with every prior hash retained as history. `LAMBDA_FS_RULE` is
untouched; its hash is unchanged. Tests updated to the new literal:
`test_rule_hashes_match_the_currently_committed_registration_values`
(hardcoded hash) and the dynamic `test_rule_hashes_match_the_registration_document`
(asserts the current hash appears somewhere in this file, which the §3.1
edit above satisfies).

**Item 6 — RECONCILIATION, availability-frame statistics at both levels.**
A builder report cited "300 (family,symbol) pairs, 20 unavailable
(NOT_YET_AVAILABLE)"; an independent reviewer measured "4,680 rows, 308
NOT_YET_AVAILABLE" via the same `build_family_episode_availability` frame.
Both numbers are CORRECT and RECONCILE EXACTLY — they are two different,
both-legitimate levels of aggregation over the identical frame produced by
`scripts/stock_identity_build_ruler.py`'s pilot build (`_family_registry()` +
the pilot's own `fire_family_keys`), verified by direct re-run:

* **`(family_key, symbol)`-LEVEL** (the builder's number): `availability[
  ["family_key", "symbol"]].drop_duplicates()` — **300** distinct pairs
  total, **20** of them carrying at least one non-`ELIGIBLE` row (all
  `NOT_YET_AVAILABLE` in the current pilot substrate; `NO_COVERAGE`/
  `UNESTIMABLE` are typed but currently zero here).
* **`(family_key, tier-eligible episode)`-LEVEL, i.e. the frame's raw row
  count** (the reviewer's number): **4,680** rows total (one row per
  `(family_key, episode)` pair the frame enumerates), of which **308** rows
  are typed `NOT_YET_AVAILABLE`.

The relationship: a `(family_key, symbol)` pair whose family becomes
available only partway through the pilot window contributes MANY
`NOT_YET_AVAILABLE` rows (one per tier-eligible episode still before that
family's `family_first_available` boundary) while being just ONE
`(family_key, symbol)` pair in the dedup count — exactly why 20 unavailable
pairs expand to 308 unavailable rows. **Canonical milestone-packet
statistic** (both levels, explicitly labeled, so no future reader has to
re-derive which level a bare number means): *300 (family, symbol) pairs, 20
unavailable at the pair level; 4,680 (family, episode) rows, 308 unavailable
(all `NOT_YET_AVAILABLE`) at the row level.* `_availability_stats`
(`scripts/stock_identity_build_ruler.py`) now emits both levels by name in
`manifest["family_symbol_availability"]`: `n_family_symbol_pairs` /
`n_family_symbol_pairs_unavailable` (pair-level) alongside the new
`n_availability_rows` / `n_availability_rows_unavailable` (row-level), plus
the pre-existing `unavailable_state_counts` (row-level, by typed state).
Reproduced via `python3 scripts/stock_identity_build_ruler.py --pilot
--include-nulls --output-dir <dir>` against the committed pilot substrate
(spec hash unchanged: `43bb66b06a27a896e27c57c7f08deb1dfbc7b2f22fdd8faa778
532d78c626bfb`).

### Pilot smoke re-run (this packet)

Re-run after all six items above: `spec_hash` unchanged
(`43bb66b06a27a896e27c57c7f08deb1dfbc7b2f22fdd8faa778532d78c626bfb` — these
items touch disclosure/receipt/test code, never `RulerSpec`'s geometry or the
still-pending `pr3` sentinel); `recall_at_tier_distribution` unchanged (34/50
cells defined, mean 0.0656, median 0.0209, P25 0.0); `family_symbol_
availability` now reports both levels as Item 6 states; cadence-null summary
unchanged (92/285 applied, 1,661/31,119 rows, `|snap_sessions|` mean
1.22/median 1.0/max 4.0). `data/stock_identity/ruler/ruler_spec_v1.json`'s
`pr3` block and `data/trial_ledger.jsonl` confirmed byte-identical
before/after via `git diff`.

## 6.13 Sol CONFIRMATION-1/CONFIRMATION-2 (SI-W3A-RULER-V1) — availability-eligibility closed law + cadence-control coverage output

Sol's ruling (Slack ts `1787967972.011309`) closed the availability-null
question with exact law, declaring the `_episode_family_availability_state`
predicate as it stood after §6.11's Ruling 2 NOT seal-ready, and separately
required a machine-readable cadence-control coverage/state output for W3B.
Two independent parts, both implemented in `engine/stock_identity/ruler.py`
and `engine/stock_identity/ruler_nulls.py`; D3b's own per-fire mechanics
(§6.11 Ruling 3) stay byte-untouched — no bound widening, no per-fire K, no
coverage rescue.

### Part 1 — availability-eligibility closed law (five points)

`build_family_episode_availability` / `_episode_family_availability_state`
now implement Sol's five-point law exactly:

1. **Hard lower bound (unchanged from Ruling 2).** A non-null
   `family_first_available` remains a hard lower bound — episodes before it
   type `NOT_YET_AVAILABLE`.
2. **Class-P is unavailable regardless of the bound.** A family whose W2
   registry `provenance_class` is `"P"` (prospective-only / structural-
   absence) types `"STRUCTURAL_ABSENCE"` for EVERY tier-eligible episode,
   checked BEFORE any date-bound logic — a Class-P entry with a non-null
   `family_first_available` (the real registry's own `amber_early`, born
   2026-08-11) still resolves here, never to `NOT_YET_AVAILABLE`/`ELIGIBLE`.
3. **Null-bound R/B eligibility requires positive, outcome-independent
   reconstructibility evidence**, drawn entirely from existing W2 registry
   receipts, `bars_by_symbol` plane coverage, and the SAME ticker-identity
   hygiene machinery (`engine.stock_identity.hygiene.check_symbol`) every
   other name in this program is checked against — no second availability/
   event/evidence store:
   * (a) a receipted source/era spec — the registry entry's own `spec_hash`
     is non-empty (every real R/B `_entry()` in
     `engine/stock_identity/replay/registry.py` carries one; only a Class-P
     or malformed entry does not);
   * (b) required producer inputs exist — when the registry's own
     `producer` field embeds a committed `data/...` store path (
     `confirmed_buy`/`rebuy`'s `data/signal_archive/track_record.parquet`,
     `sea_event_classes`'s `data/stock_events`), that path must exist on
     disk; a pure engine-function producer (`grey_dot_macro`, the tier
     cascade, the naive comparators, the locked-spec Terminal ports) names
     no store path, so this check is vacuous for those families, never a
     false exclusion;
   * (c) price-plane coverage — unchanged from Ruling 2, `bars_by_symbol`
     covers the episode's instrument/window;
   * (d) identity resolvability — the symbol passes
     `hygiene.check_symbol(...)["compute_eligible"]` (the same
     splice/reuse-refusal verdict `COMPUTE_BLOCKLIST` already governs
     elsewhere in this program — one committed entry, `ABX`, as of
     2026-08-28).

   These four sub-checks are scoped EXACTLY as Sol's ruling states them —
   "for historical R/B families with NULL first-available" — a family with a
   real, committed `family_first_available` bound (`reclaim_waiver`,
   `washout_turn`, `amber_early`) is governed by point 1 alone and is not
   additionally gated by (a)/(b)/(d).
4. **Fail-closed on any unestablished source-specific availability.** A
   failure of (b) types `"SOURCE_FAILED"`; a failure of (d) types
   `"IDENTITY_UNRESOLVED"`; (a) failing, like every other missing-evidence
   path, types `"UNESTIMABLE"`. None of these ever falls through to
   eligibility, and eligibility is NEVER inferred from the family having
   fired (`aggregate_cell_metrics`'s eligibility universe still never reads
   `events` for this purpose — unchanged from Ruling 2) or from the null
   itself.
5. **A missing registry entry or missing field stays UNESTIMABLE.** Extended
   from Ruling 2 to cover a genuinely missing `provenance_class` field too
   (`_family_provenance_class`'s `field_present=False` path) — a missing
   class is NEVER guessed or defaulted to R/B, which would be exactly the
   eligibility-widening the ruling forbids. Checked against the real
   committed registry: all 24 `data/stock_identity/expert_events/
   family_registry.json` entries carry a `provenance_class` (10 R / 6 B / 8
   P) — the fail-closed path exists but is currently unexercised in
   production; no family lacked the field, so no class was invented and
   nothing needed to be reported as a gap.

**New closed-taxonomy states exercised by this predicate**: `"STRUCTURAL_
ABSENCE"`, `"SOURCE_FAILED"`, `"IDENTITY_UNRESOLVED"` — all three were
already members of `AVAILABILITY_TAXONOMY_TOKENS` (§ frozen taxonomy, freeze
§7) but were never actually PRODUCED by `_episode_family_availability_state`
before this pass; no new token was added.

**Sol's five required regressions** (`tests/test_stock_identity_ruler.py`):

* **(a)** `test_class_p_family_never_eligible_regardless_of_null_date_confirmation1_regression_a`
  — a Class-P family with a null bound, and separately with a SET bound
  (mirroring `amber_early`), both type `STRUCTURAL_ABSENCE`, never
  `ELIGIBLE`.
* **(b)** `test_rb_null_bound_family_eligible_with_lawful_source_input_coverage_confirmation1_regression_b`
  — an R family, null-bound, receipted spec, an EXISTING declared producer
  store (created under a throwaway `repo_root` so the positive branch is
  genuinely exercised), full bars coverage, resolvable identity -> `ELIGIBLE`.
* **(c)** `test_rb_null_bound_family_missing_source_coverage_types_unavailable_confirmation1_regression_c`
  — the SAME family with an absent declared producer store types
  `SOURCE_FAILED`; separately, with no `spec_hash` at all, types
  `UNESTIMABLE`.
* **(d)** `test_zero_fire_eligible_episode_still_grows_denominator_under_narrowed_law_confirmation1_regression_d`
  — under the NARROWED predicate, a zero-fire-but-eligible episode still
  grows `recall_at_tier`'s denominator (1.0 -> 0.5), re-proving Ruling 2's
  regression (a) still holds after CONFIRMATION-1 narrows eligibility.
* **(e)** `test_no_fired_on_fallback_under_any_missing_evidence_path_confirmation1_regression_e`
  — AAA plainly fires, but FOUR distinct missing-evidence paths (no
  registry; missing `provenance_class`; null-bound R missing `spec_hash`;
  null-bound R with an absent declared producer store) all leave
  `recall_at_tier` undefined, never silently read off the fire.

Plus `test_identity_unresolved_symbol_never_eligible_under_null_bound`
(point 3(d) in isolation, against the real `ABX` `COMPUTE_BLOCKLIST` entry
and the real `repo_root` default).

Every pre-existing fixture conferring "unrestricted" lawful availability
(`_unrestricted_registry` in `tests/test_stock_identity_ruler.py`, and the
two `fam.synthetic` fixtures in `tests/test_stock_identity_w3_calibration.py`)
was updated to carry an explicit `provenance_class="R"` and a synthetic
`spec_hash`, matching the precedent Ruling 2 itself set — an "unrestricted"
fixture now means "a receipted R/B family with no declared producer-store
dependency and no registered lower bound", not merely "no lower bound".

### Part 2 — cadence-control coverage output (W3B input)

`engine/stock_identity/ruler_nulls.py` gains `build_cadence_control_coverage`
and `cadence_control_coverage_summary` — a pure, read-only, non-persisted-
elsewhere rollup of `grain_cadence_null`'s own (byte-untouched) per-fire
`cadence_null_state` output to one row per `(family_key, symbol, grain)`
triple, carrying a closed state drawn from `CADENCE_CONTROL_STATES =
("CONTROLLED", "UNESTIMABLE", "NO_CALENDAR")` — a direct rename of D3b's own
`"applied"`/`"unestimable"`/`"no_calendar"` values, never a new computation.
D3b's `cadence_null_state` is uniform per `(family_key, symbol)` group by
construction (the shared base shift `K` and the lawful/unlawful verdict are
decided once per group, never per grain), so a group whose fires span
multiple grains (the real pilot cohort's `sea_event_classes` family) reports
the SAME state for every grain row it touches — read via `.mode()` rather
than assumed, so a future change to that invariant would surface as a mixed-
state group. `scripts/stock_identity_build_ruler.py`'s `--include-nulls`
path now writes `cadence_control_coverage_v1.parquet` alongside the existing
null artifacts and adds a `manifest["nulls"]["cadence_control_coverage"]`
summary block (`n_groups`, `state_counts`, `n_fires_total`).

**Dark-group inference prohibition (verbatim, for W3B/W5).** A group not
exact-phase-controlled may not support any claim requiring cadence-controlled
or cross-grain inference, and W3B/W5 must abstain/exclude where the
preregistered inference requires this control — the power/ABSTAIN law owns
the consequence. Concretely: a `(family_key, symbol, grain)` triple whose
`cadence_control_state` is `"UNESTIMABLE"` or `"NO_CALENDAR"` is NOT
exact-phase-controlled (D3b could not verify or could not even attempt exact
weekday-phase preservation for it), and any downstream inference that
requires cadence control or a cross-grain comparison must abstain from or
exclude that triple rather than silently treating it as controlled. Only
`"CONTROLLED"` triples are exact-phase-controlled in D3b's own sense. This
output makes that distinction machine-readable rather than requiring a
future reader to re-derive it from the raw per-fire null artifact.

Tests (`tests/test_stock_identity_ruler_nulls.py`): empty/missing-column
handling, each of the three states mapped correctly (`NO_CALENDAR` from a
symbol with no calendar; `CONTROLLED` from a sparse, well-separated daily
group that D3b applies cleanly; `UNESTIMABLE` reusing the same dense-Friday-
cluster seed-search construction §6.11's own discriminating test uses), the
mixed-grain-group-reports-uniform-state invariant, closed-state-set
membership, and the summary's state-count/total-fires reporting.

### Pilot smoke re-run (this packet)

Re-run via `python3 scripts/stock_identity_build_ruler.py --pilot
--include-nulls --output-dir <dir>`: `spec_hash` unchanged
(`43bb66b06a27a896e27c57c7f08deb1dfbc7b2f22fdd8faa778532d78c626bfb` — this
repair touches only `ruler.py`/`ruler_nulls.py` logic and docstrings, never
`RulerSpec`'s geometry or the still-pending `pr3` sentinel, confirmed by
direct hash comparison before/after). `data/stock_identity/ruler/
ruler_spec_v1.json`'s `pr3` block and `data/trial_ledger.jsonl` are both
confirmed byte-identical before/after via `git diff` (zero diff).

**Availability distribution — measured IDENTICAL to §6.12's baseline, row for
row.** A direct comparison (the repaired predicate vs. an inline
reconstruction of the pre-CONFIRMATION-1, Ruling-2-only predicate, run over
the SAME committed pilot events/episodes/registry/bars) produced **zero**
row-level differences: **4,372 ELIGIBLE, 308 NOT_YET_AVAILABLE**, no
`STRUCTURAL_ABSENCE`/`SOURCE_FAILED`/`IDENTITY_UNRESOLVED`/`UNESTIMABLE`/
`NO_COVERAGE` rows in either version, on this pilot cohort. This is an
honest, expected result, not a sign the narrowing did nothing: Class-P
families ship zero committed W2 rows by construction, so they never reach
this frame via the wired `fire_family_keys` path (regression (a) above
proves the predicate excludes them correctly when called directly, which is
what makes it correct AS LAW, independent of the current call graph); every
fired R/B family in the real registry carries a genuine `spec_hash` and
either no declared producer-store dependency or one that exists on disk
(`confirmed_buy`/`rebuy`'s `data/signal_archive/track_record.parquet`,
`sea_event_classes`'s `data/stock_events` — both verified present); and no
fired episode in this pilot touches the one `COMPUTE_BLOCKLIST` symbol
(`ABX`). `recall_at_tier_distribution` is therefore unchanged from §6.12: 34/
50 cells defined, mean 0.0656, median 0.0209, P25 0.0; `family_symbol_
availability` unchanged: 300 pairs / 20 unavailable, 4,680 rows / 308
unavailable (all `NOT_YET_AVAILABLE`).

**Cadence-control coverage (new artifact, this packet).** 315
`(family_key, symbol, grain)` groups over 31,119 total fires: **94
`CONTROLLED`**, **221 `UNESTIMABLE`**, **0 `NO_CALENDAR`** (every pilot
symbol carries a trading calendar). Note the granularity difference from
§6.12 Item 2's `92/285` `(family_key, symbol)`-level figure (no grain in the
key) — this artifact adds `grain` to the group key, so a `(family_key,
symbol)` group whose fires span two grains (`sea_event_classes`, observed in
the real pilot cohort) now contributes two coverage rows both carrying the
SAME state, which is why `94+221=315` exceeds `92+193=285`: 30 extra rows
come from mixed-grain groups being counted once per grain they touch, not
from a different underlying verdict.

## 5. Sealed constants receipt (Task 3C Step 5 -- the real, one-time seal)

- Sealed at: `2026-08-29T03:37:58.620149+00:00`
- `recall_floor` = `0.05` (rule hash `71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf`, status `declared_pending_sol_rule_review`)
- `lambda_fs` = `0.00027929738756017066` (rule hash `8b149a753f5034c737eb0cc0c72d081e56e2d9431dd4adc01ac0cea8cc4ae366`, status `declared_pending_sol_rule_review`)
- Roster hash: `2609c8ac83a54aef8a3d2a28077535783cf94f17054a40ad92043cdc1e2bad2e` (n=759)
- Replay-manifest hash: `e6b85fd844b5330f7d227bc464e7ad294687591be3b7361e9ec47232c2344a74`
- W2 family-registry hash: `1d3902f35e4b9e22ca8c4a2a9a3d4440f207cb1a694c9cfc43f7ef73dff4b93e`
- Substrate provenance hash: `2ee5d7120edf96b03e9f29355fd37dcaeeeb0258e30f3aba7e67ce21eb0952d2`
- Ruler implementation hash (`ruler.py`): `42905b81e6fe622dbbbb7f4044b13cc04acf48ace80f16c63439236fc409e708`
- Ruler implementation hash (`ruler_nulls.py`): `cd57271435a9e3c1bb50058bb31919e247fb23703582397b88dc1bcefeaa5ccb`
- Spec hash before seal: `43bb66b06a27a896e27c57c7f08deb1dfbc7b2f22fdd8faa778532d78c626bfb`
- Spec hash after seal: `fda9b8256aff5102792f347dd542af6827fb69aa55d1adf46f8cb0c10d130216`
- Recent-history guard cutoff: `2026-02-11`
- Trial ledger family: `stock_identity_w3_ruler_calibration` (effective N=6)
- Fit-read look budget: `3`

### 5.1 Status-string caveat (SI-W3A-RULER-V1 test-repair pass)

The `status` field recorded on each PR-3 constant above
(`declared_pending_sol_rule_review`) is `RULE_REVIEW_STATUS`, a single
module-level label that predates Sol's rule-form ruling (Ruling 1, §6.11) and
that the seal path never re-derives per constant — it is a labeling artifact,
not evidence the rule form went unreviewed. The `rule`/`rule_hash` fields the
seal actually recorded are exactly Sol's ruled forms (`recall_floor` =
Ruling 1(a), `lambda_fs` = Ruling 1(b)); the hashes above match §6.11's
re-pinned values exactly. Left as-is per the freeze's voiding clause (the
sealed receipt itself may not be edited) — recorded here so a reader does not
mistake the stale `status` string for evidence Sol's ruling never happened.
