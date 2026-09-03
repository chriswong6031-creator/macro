# Actor, Liquidity & Monthly Transition Clock — W1 Implementation Plan

Date: 2026-09-03
Status: **FORWARD-REPAIRED PLAN / HOLD-FOR-SOL / NOT STARTED**
Canonical implementation carrier: Macro issue #6787
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`
Architecture carrier: Macro PR #6788
Protected procedure at repair: `mastermindx-market-intelligence/Mastermind@da6af515c95301377fb5fd8748e374a8948a3540`
Authority: records only until a separately assigned W1 worker posts Pickup ACK, continuity receipt when available, and separate START after every entrance gate is open.

This plan implements `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md` plus the VIX-futures and CI-owner amendments on this same architecture carrier. Where older text conflicts, the forward-repaired design and this plan control.

The implementation is one bounded vertical slice:

```text
official source receipts
→ deterministic event/futures/monthly composition
→ current policy_turn_clock.v1
→ Policy Watch
→ existing Neural Web direct machine consumer
→ eligible-trigger-only prospective receipt
→ exact tests + hosted CI + real proof
```

No score, recommendation, trade authority, new scheduler, new publisher, duplicate machine API, RIC F3 implementation or evaluation-lab outcome computation is included.

---

## Task 0 — Lawful pickup, session-root sparse worktree, exact scope and collision gate

### Step 0.1 — Fresh truth before effect

Fresh-read:

```text
current protected Mastermind/docs/sol_skills/INDEX.md
current Macro main
Macro AGENTS.md and CLAUDE.md
issue #6787
merged architecture PR #6788 exact accepted head
DEC:POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION
this design + VIX + CI amendments
current open PRs touching any planned path
current worktree/branch occupancy
```

Require:

- protected Skillpack compatible;
- architecture PR accepted/merged;
- this operation not already STARTed/effect-unknown elsewhere;
- no STOP/supersession;
- every current owner of `.github/ci/legacy-jobs.yml` terminally released, merged or explicitly reconciled by Sol;
- every other planned shared path collision either absent or explicitly ruled;
- W1 receiver identity and exact session are bound.

If any gate fails, return typed HOLD with `effect=NONE`; do not create another carrier/branch/workflow/job.

### Step 0.2 — Bind to the host-provided session-root worktree

**Do not run the forbidden manual shape** `git worktree add ../...`, do not create a sibling via `../`, and never create/use a `codex/` branch. The current repository law gives each supported harness its own session-root/worktree procedure. The implementation worker operates only in the already assigned/minted session worktree supplied by that harness, or follows the current checked-in harness/`.agents/skills/macro-sparse-worktree` procedure when the harness explicitly requires manual session-root setup.

From the actual assigned session worktree:

```bash
git fetch origin main
git rev-parse --show-toplevel
git branch --show-current
git status --short
git rev-parse HEAD
git rev-parse --git-common-dir
python3 scripts/worktree_sparse.py status
```

Verify:

- top level is the current harness’s lawful session root/worktree, not the shared primary checkout and not an invented Codex-only location;
- expected assigned branch is bound to this operation;
- status is clean before mutation;
- pickup base is a fresh current-main descendant according to current law;
- the worktree is registered and no foreign operation is occupying it.

If the harness has not supplied a lawful linked session worktree, STOP and follow the checked-in repository procedure. This plan does not invent a branch prefix or filesystem destination.

### Step 0.3 — Sparse heavy-tree opt-in is mandatory before use

`data/`, `site/`, `mockups/` and `verify_shots/` are omitted by default in a session worktree. Before any task reads, writes, builds, compares or captures a planned omitted tree, materialize it in the current worktree:

```bash
python3 scripts/worktree_sparse.py status
python3 scripts/worktree_sparse.py add data
python3 scripts/worktree_sparse.py add site
python3 scripts/worktree_sparse.py add mockups
```

Use:

```bash
python3 scripts/worktree_sparse.py full
```

instead if the exact validation genuinely needs the full checkout. `verify_shots/` must also be explicitly added when a governed evidence tool writes there.

Rules:

- never infer a canonical file is absent merely because a sparse tree omitted it;
- never write into an omitted tracked tree—the writer can truncate committed bytes;
- never use an unexpected `git add -A` to sweep generated data/site diffs;
- check `python3 scripts/worktree_sparse.py clean` report-first when an omitted-tree write is suspected;
- do not run the full test suite in a sparse checkout unless `full` has been materialized.

Task 1/2/5 real-data work requires `data`; Task 5/6 current artifact and UI work requires `site`; Task 6/8 design evidence requires `mockups` and, if the current evidence framework uses it, `verify_shots`.

### Step 0.4 — Freeze planned source surface

Expected new files:

```text
collectors/policy_event_clock.py
engine/futures_roll_calendar.py
engine/policy_turn_clock.py
scripts/build_policy_turn_clock.py
templates/partials/_policy_turn_clock.html.j2
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

Expected modified files:

```text
engine/event_calendar.py
engine/neuralweb/world_state.py
scripts/build_policy_watch.py
templates/policy_watch.html.j2
tests/test_policy_watch_ui.py
tests/test_world_state.py
config/dag.yml
.github/workflows/whitehouse-sentinel.yml
scripts/ci/daily_engine_regional_desk_builders.sh
.github/workflows/ci.yml
.github/ci/legacy-jobs.yml
```

Conditional only when current source proves exact expectation change:

```text
tests/test_dag_conformance.py
```

Unconditional no-edit paths:

```text
engine/yield_momentum.py
engine/rates_inflation_command.py
scripts/build_rates_command.py
agentos/workstreams/WS-RATES-INFLATION-COMMAND.md
collectors/cboe_vix_futures.py
```

Before START and again immediately before every shared CI-manifest/workflow edit, perform a complete current open-PR census. At architecture repair time, `.github/ci/legacy-jobs.yml` remained actively owned by open #6721, #6706, #6651, #6625, #6514, #6389 and #6296; `.github/workflows/ci.yml` remained actively owned by open #6628. #6791 had merged. These numbers are historical observations only; current GitHub truth controls.

Post `PATH_FREEZE` naming exact current owners and paths before edits. Any unruled collision returns `BLOCKED PATH_COLLISION effect=NONE`.

### Step 0.5 — RED discipline

No implementation source before the relevant test is RED for the intended reason. Keep each task independently reviewable. Do not widen scope to repair an unrelated inherited red.

---

## Task 1 — Official evidence collector and correction-safe Event Calendar composition

### Files

Create:

```text
collectors/policy_event_clock.py
tests/test_policy_event_clock.py
```

Modify:

```text
engine/event_calendar.py
```

### RED tests first

Add fixtures/tests proving:

```python
def test_fed_event_stable_identity_survives_reordering(): ...
def test_treasury_event_stable_identity_survives_reordering(): ...
def test_formatting_only_page_change_does_not_create_revision(): ...
def test_reused_revision_with_semantic_change_is_visible_collision(): ...
def test_silent_revision_preserves_both_receipts(): ...
def test_scheduled_source_status_is_distinct_from_observed_phase(): ...
def test_virtual_event_does_not_prove_actor_physical_location(): ...
def test_prerecorded_event_does_not_prove_actor_physical_location(): ...
def test_explicit_live_presence_can_project_current_location_only_inside_window(): ...
def test_ended_event_cannot_project_current_location(): ...
def test_conflicting_official_presence_receipts_remain_conflicting(): ...
def test_buyback_mechanism_is_not_collapsed_into_purpose(): ...
def test_buyback_max_offered_submitted_accepted_amounts_are_distinct(): ...
def test_missing_treasury_amount_remains_null(): ...
def test_cancelled_or_revised_operation_keeps_lineage(): ...
def test_keep_first_store_is_idempotent(): ...
def test_collector_status_changes_only_on_semantic_status_transition(): ...
```

Tests must fail because W1 collector/composition behavior is absent, not because of sparse missing data.

### Implement smallest source owner

`collectors/policy_event_clock.py`:

- bounded official-public Fed/Treasury/TreasuryDirect adapters;
- stable `source_event_id` independent of page order;
- explicit or fallback semantic `source_revision`;
- canonical semantic digest;
- keep-FIRST persistence via existing first-seen utility;
- explicit `record_kind`, source clocks, rights and parser version;
- Treasury operation mechanism/purpose and four separate nullable amount fields;
- event location, attendance mode and physical presence basis separated;
- no private-location inference;
- no model call.

`engine/event_calendar.py` consumes the normalized official rows in its existing composition role; do not create a second calendar.

### GREEN + hostile mutations

Run the focused suite. Then mutate one at a time and require RED:

- derive event ID from page position;
- reuse revision token and drop changed semantics;
- infer presence from venue/Watch Live;
- infer accepted amount from announced maximum;
- map buyback purpose into operation kind;
- overwrite first-seen receipt.

Restore each mutation.

---

## Task 2 — Equity/Treasury quarterly roll + monthly VX settlement helper

### Files

Create:

```text
engine/futures_roll_calendar.py
tests/test_futures_roll_calendar.py
```

### RED tests

```python
def test_equity_and_treasury_rolls_are_quarterly(): ...
def test_ordinary_month_is_not_applicable_for_equity_and_treasury(): ...
def test_scheduled_window_is_not_active_without_progress_input(): ...
def test_live_progress_can_mark_active_without_direction(): ...
def test_august_is_not_applicable_for_equity_treasury_but_vx_is_monthly(): ...
def test_september_2026_standard_vx_expiry_is_2026_09_16(): ...
def test_weekly_front_does_not_replace_standard_monthly_expiry(): ...
def test_vx_holiday_rule_moves_to_prior_business_day(): ...
def test_vx_dte_and_rule_conflict_is_unknown_not_silent_preference(): ...
def test_fresh_curve_classifies_contango_flat_and_backwardation(): ...
def test_stale_curve_is_not_current_or_flat(): ...
def test_rank_roll_boundary_blocks_same_contract_change_claim(): ...
def test_vx_settlement_alone_has_zero_directional_authority(): ...
```

Use deterministic acceptance fixtures for 2026-08/09 and current official rule semantics. Do not hard-code one year as eternal truth.

### Implement

Pure helpers only; no network/store owner. Consume existing `data/cboe/vix_futures.parquet` / `data/cboe/vix_curve.parquet` or the existing projection when supplied by the builder. Do not touch `collectors/cboe_vix_futures.py`.

Preserve independent families:

```text
equity_index
treasury
volatility
```

Weekly front, standard monthly M1 and quarterly rolls never collapse into one status.

### GREEN + mutations

Kill:

- quarterly-only blanket `futures_roll=not_applicable` in August;
- weekly front replacing monthly M1;
- calendar window called active without progress;
- M1 rank reset described as same-contract price shock;
- stale/missing M2 called flat;
- any rank/gate/size/trade field becoming true.

---

## Task 3 — Pure policy-turn composer input closure, identity and state vocabulary

### Files

Create:

```text
engine/policy_turn_clock.py
tests/test_policy_turn_clock.py
```

### RED contract tests

Prove the public interface requires explicit injected inputs for:

```text
events
official_treasury_operations
opex
opex_risk
option_surface
broad_market_flow
rebalance_calendar
rebalance_pulse
duration_extension_context
treasury_tga
futures_roll
market_confirmation
prior_clock
now
```

Tests:

```python
def test_compose_has_no_filesystem_network_or_model_read(): ...
def test_input_order_does_not_change_payload(): ...
def test_equivalent_utc_and_et_instant_has_same_us_decision_date(): ...
def test_generated_at_is_not_semantic_change_identity(): ...
def test_method_version_is_exposed(): ...
def test_input_digest_is_stable(): ...
def test_source_versions_and_watermarks_are_exposed(): ...
def test_method_version_mismatch_refuses_prior_delta(): ...
def test_missing_required_calendar_truth_can_force_unknown(): ...
def test_all_authority_fields_are_false(): ...
```

### Implement pure normalizers

Normalize `now` once to `America/New_York`. Source-native clocks remain unmodified in evidence. All nulls/staleness/conflicts survive.

Top-level payload must include independent:

```text
option_support
broad_market_flow
support_composition
treasury_liquidity
futures_roll
rebalance
market_confirmation
```

No hidden global numeric score.

---

## Task 4 — State composition with options/broad-flow axis separation

### Files

Continue:

```text
engine/policy_turn_clock.py
tests/test_policy_turn_clock.py
```

### RED cases

```python
def test_option_replacement_alone_cannot_build_support(): ...
def test_broad_flow_alone_cannot_build_support(): ...
def test_options_and_broad_flow_are_distinct_axes(): ...
def test_option_support_never_contains_cross_axis_count(): ...
def test_two_independent_support_mechanisms_can_build_support(): ...
def test_stale_broad_flow_does_not_change_option_support(): ...
def test_opex_proximity_does_not_infer_dealer_sign(): ...
def test_replacement_requires_comparable_same_owner_root_observations(): ...
def test_missing_replacement_is_unknown_not_absent(): ...
def test_vx_settlement_alone_does_not_open_volatility_window(): ...
def test_rolloff_plus_fresh_independent_confirmation_can_open_volatility_window(): ...
def test_month_end_schedule_without_observed_pulse_is_not_dominant(): ...
def test_month_end_fresh_nonquiet_pulse_can_be_dominant(): ...
def test_bond_index_extension_is_not_equity_flow(): ...
def test_high_impact_catalyst_can_override_mechanical_window(): ...
def test_conflicting_fresh_axes_return_mixed(): ...
```

The corrected two-mechanism test is structurally:

```python
def test_two_independent_support_mechanisms_can_build_support():
    out = compose(**REPLACEMENT_AND_SUPPORTIVE_FLOW)
    assert out["option_support"]["replacement"] == "building"
    assert out["broad_market_flow"]["status"] == "supportive"
    assert "applicable_support_count" not in out["option_support"]
    assert out["support_composition"]["applicable_support_count"] >= 2
    assert {"option_replacement", "broad_market_flow"} <= set(
        out["support_composition"]["supporting_mechanisms"]
    )
    assert out["state"] == "SUPPORT_BUILDING"
```

This kills the prior cross-axis bug: the K-of-N result belongs only to `support_composition`; broad flow never becomes an `option_support` fact.

### Implement deterministic precedence

Closed states only:

```text
SUPPORT_BUILDING
SUPPORT_STABLE
PINNED
SUPPORT_ROLLOFF_IMMINENT
VOLATILITY_WINDOW_OPEN
MONTH_END_REBALANCE_DOMINANT
CATALYST_DOMINANT
MIXED
UNKNOWN
```

Use the binding precedence from the design. `SUPPORT_BUILDING` counts independently sourced mechanism families at most once each, literal K-of-N, no weights. Stale/unavailable families cast no supportive vote. Preserve exact predicate receipts in `state_basis` and `support_composition.predicate_results`.

### Hostile mutations

Require RED if:

- `option_support.applicable_support_count` is reintroduced;
- broad-flow status is copied into option support;
- one option-replacement axis creates `SUPPORT_BUILDING`;
- VX settlement alone opens volatility window;
- month-end calendar eligibility alone creates dominance;
- stale confirmation is treated neutral/fresh;
- a hidden weighted score is added.

---

## Task 5 — Builder modes, per-source no-regress and eligible-trigger prospective ledger

### Files

Create:

```text
scripts/build_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

Generated after sparse opt-in:

```text
site/policy_turn_clock.json
data/policy_turn_clock/forward_log.jsonl
```

### RED builder/purity tests

```python
def test_builder_gathers_existing_owners_without_network(): ...
def test_publish_current_writes_exact_json_contract(): ...
def test_verify_mode_writes_nothing(): ...
def test_ledger_only_never_writes_current_json(): ...
def test_same_semantic_inputs_later_attempt_is_byte_stable(): ...
def test_same_semantic_inputs_do_not_create_changed_axes(): ...
def test_source_versions_and_watermarks_participate_in_digest(): ...
```

### RED per-source no-regress tests

At minimum:

```python
def test_mixed_source_advance_and_regression_keeps_new_a_and_last_good_b(): ...
def test_regressed_source_never_lowers_published_watermark(): ...
def test_source_failure_preserves_last_good_evidence_and_marks_degraded(): ...
def test_source_recovery_advances_from_preserved_last_good(): ...
def test_equal_watermark_equal_semantics_is_noop(): ...
def test_valid_correction_preserves_original_lineage_and_advances_correction_identity(): ...
def test_correction_cannot_use_older_source_identity_to_overwrite_newer(): ...
def test_all_regressive_inputs_refuse_current_overwrite(): ...
def test_recomputed_evidence_cutoff_never_moves_backward(): ...
```

Required mixed-source fixture:

```text
published: source A watermark=10, source B watermark=20
incoming:  source A watermark=11, source B watermark=19
expected: source A=11 accepted; source B=20 last-good retained;
          B emits SOURCE_WATERMARK_REGRESSION; payload may publish because A advanced;
          no field derived from B@19 enters current state.
```

A whole-payload “older/newer” check is not a substitute.

### Implement source reconciliation

Before current publication:

1. fresh-read the existing current artifact;
2. compare each source key independently using owner-native watermark/revision/availability identity plus semantic digest/correction lineage;
3. accept advances;
4. preserve equal identities as byte-stable;
5. preserve current last-good on regression and emit a typed gap;
6. let truthful failure/stale status change while retaining last-good evidence/watermark;
7. accept a valid correction only with explicit lineage and non-regressive source identity;
8. recompute payload state/digest/cutoff from the reconciled evidence set;
9. refuse/no-op when nothing semantically valid advanced/changed.

No cross-lane lock service.

### RED prospective-ledger tests — kill unconditional nightly append

The following are mandatory executable tests, not prose acceptance only:

```python
def test_hourly_publish_never_appends_forward_receipt(): ...
def test_nightly_ineligible_trigger_is_noop(): ...
def test_nightly_no_trigger_does_not_create_jsonl_file_or_row(): ...
def test_direct_append_off_lane_is_refused_inside_append_seam(): ...
```

Parametrize every eligible first-seen family:

```python
@pytest.mark.parametrize("trigger_kind", [
    "material_state_change",
    "high_impact_event_t24",
    "opex_t_minus_2",
    "post_opex_t_plus_1",
    "month_or_quarter_end_pulse",
    "vx_t_minus_2",
    "vx_rank_roll_boundary",
])
def test_each_trigger_family_can_append_first_seen_receipt(trigger_kind): ...
```

Receipt identity and idempotence:

```python
def test_receipt_identity_is_asof_trigger_kind_trigger_id_method_and_input_digest(): ...
def test_exact_receipt_identity_is_keep_first_on_rerun(): ...
def test_new_trigger_id_is_not_deduped_as_old_trigger(): ...
def test_multiple_simultaneous_triggers_use_frozen_precedence_and_append_at_most_one(): ...
```

Correction semantics:

```python
def test_correction_appends_linked_row_without_rewriting_original(): ...
def test_correction_row_names_original_receipt_and_source_lineage(): ...
def test_correction_target_missing_is_refused(): ...
def test_correction_append_is_still_refused_off_nightly_lane(): ...
```

### Implement ledger gate

`append_forward_receipt()` itself calls `engine.ledger_lane.nightly_advance_enabled()`; callers cannot bypass the lane check.

Nightly lane is necessary but never sufficient. Build the eligible-trigger set from current/prior semantic evidence. If no first-seen trigger exists, append zero rows. When multiple first-seen triggers are present, select the first unseen trigger by the frozen design order and append at most one receipt.

Receipt identity:

```text
(as_of, trigger_kind, trigger_id, method_version, input_digest)
```

Corrections append `record_kind=correction` with `correction_of_receipt_id`; originals remain immutable.

### GREEN + hostile mutations

Kill:

- `if nightly: append(...)` unconditional path;
- lane check only in CLI while direct helper bypasses it;
- receipt identity omitting trigger ID or method/input identity;
- correction overwriting original JSONL line;
- whole-payload no-regress that permits one source to move backward;
- source failure that erases last-good evidence.

---

## Task 6 — Policy Watch product, binding dual-theme packet and durable Neural Web machine consumer

### Files

Create:

```text
templates/partials/_policy_turn_clock.html.j2
```

Modify:

```text
scripts/build_policy_watch.py
templates/policy_watch.html.j2
tests/test_policy_watch_ui.py
engine/neuralweb/world_state.py
tests/test_world_state.py
```

Generated after `site/` opt-in:

```text
site/policy_watch.html
```

Design evidence after `mockups/` (and current framework’s evidence directory) opt-in:

```text
mockups/refs/policy-turn-clock/**
```

### Product RED tests

```python
def test_policy_watch_loads_same_origin_policy_turn_clock_json(): ...
def test_static_shell_does_not_embed_independent_current_payload(): ...
def test_noscript_or_fetch_failure_is_explicit_unavailable_state(): ...
def test_unknown_is_not_rendered_as_neutral_or_current(): ...
def test_degraded_shows_stale_clock_and_named_gap(): ...
def test_weekly_vx_and_standard_monthly_vx_are_distinct(): ...
def test_all_authority_false_is_visible_in_contract_not_trade_language(): ...
def test_en_zh_semantics_cover_every_state_and_gap_label(): ...
def test_keyboard_accessible_evidence_and_source_details(): ...
def test_ui_does_not_depend_on_color_only_state_meaning(): ...
```

### Binding art-direction packet

Baseline:

```text
research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md
research/DESIGN_DOCTRINE.md
mockups/design_system/specimen.html
existing Policy Watch route/composition
```

**DARK TREATMENT — command center:** near-black luminance depth; restrained instrument wells; narrow luminous edge/restrained glow only for fresh state; precise warning/catalyst rails; high-information clocks. Dark degraded removes glow/material lift and adds segmented/dashed warning rail + explicit stale clock/gap. Dark unknown uses neutral graphite/charcoal, explicit UNKNOWN and missing evidence, with no directional tint.

**LIGHT TREATMENT — research workspace:** cool neutral canvas; white research material; graphite type; disciplined hairlines; modest shadow instead of glow; restrained semantic ink/tint in labels/rails. Light degraded keeps the white/cool material and uses a mechanically distinct caution rail/hatch + explicit stale clock/gap. Light unknown is a neutral research sheet with explicit UNKNOWN/missing evidence and no pale-green “fine” implication.

Same IA, semantics, density, state meaning, action and interaction across themes; materially different depth mechanism by design. Token substitution alone is not PASS. No parallel token root or opaque runtime stylesheet.

### Evidence matrix — binding

Capture/review every required cell:

```text
dark  × EN × 1440 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
dark  × EN ×  390 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
dark  × ZH × 1440 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
dark  × ZH ×  390 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
light × EN × 1440 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
light × EN ×  390 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
light × ZH × 1440 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
light × ZH ×  390 × {fresh/support, rolloff, catalyst, degraded, unknown, conflict}
```

Also run 768 geometry/function checks in both themes/languages. Use governed evidence receipt format. Run where applicable:

```bash
python3 scripts/check_design_system.py --mode enforce-added
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_ui_visual_evidence.py
```

Automated checks prove matrix completeness/state identity; a human/Opus review judges actual dark/light art direction.

### Durable direct machine consumer RED tests

`tests/test_world_state.py` gains exact contract tests:

```python
def test_world_state_directly_consumes_policy_turn_clock_json(): ...
def test_world_state_policy_turn_lobe_preserves_schema_method_digest_state_axes_and_authority(): ...
def test_world_state_does_not_scrape_policy_watch_html_for_policy_turn(): ...
def test_missing_policy_turn_json_is_fail_open_typed_gap(): ...
def test_corrupt_or_wrong_schema_policy_turn_is_fail_open_typed_gap(): ...
def test_policy_turn_authority_violation_is_not_laundered_into_world_state(): ...
def test_changed_policy_turn_input_digest_changes_world_state_semantic_identity(): ...
def test_same_policy_turn_digest_remains_deterministic_under_world_state_clock_law(): ...
```

### Implement one existing machine lobe, not another API

Exact owner/path/input/output/call site:

```text
owner:       Neural Web N1 world-state composition
path:        engine/neuralweb/world_state.py
input:       site/policy_turn_clock.json
output:      data/neuralweb/world_state.json top-level policy_turn_clock lobe
call site:   build_world_state() / build_and_write(), reached by existing scripts/build_world_state.py
proof:       tests/test_world_state.py
```

The helper reads JSON directly, validates the policy-turn contract minimally enough to fail open, preserves the all-false authority and independent axes, and returns a display-only lobe. It does not recompute state, create a second policy-turn store, register a new API, parse HTML or silently substitute old content.

Missing/corrupt/invalid input follows the existing Neural Web fail-open shape: null/absent lobe plus typed gap. No direction or capital authority.

### GREEN + product mutations

Kill:

- light theme implemented as token-only copy with no distinct material mechanism/evidence;
- degraded/unknown rendered identically to fresh/neutral;
- missing EN/ZH state text;
- hidden independent current clock embedded in HTML;
- Neural Web reader scraping HTML;
- new sibling machine JSON store;
- invalid authority accepted into world state.

---

## Task 7 — Real hourly/nightly execution and canonical CI ownership

### Files

Modify:

```text
.github/workflows/whitehouse-sentinel.yml
scripts/ci/daily_engine_regional_desk_builders.sh
config/dag.yml
.github/workflows/ci.yml
.github/ci/legacy-jobs.yml
```

Potential expectation-only change after proof:

```text
tests/test_dag_conformance.py
```

### Re-census shared paths before edit

Fresh-read every open owner at action time. If any active owner remains on `.github/ci/legacy-jobs.yml` or `.github/workflows/ci.yml`, do not “work around” it by adding a workflow/job. Return `BLOCKED PATH_COLLISION` unless Sol explicitly authorizes a composition.

### RED runtime/conformance tests

Ensure current test/conformance surface fails when any of these is true:

- nightly regional-desk script omits `--mode ledger-only` before Policy Watch;
- nightly uses `publish-current`;
- hourly uses nightly lane or can append forward receipt;
- DAG claims an invocation not present in real workflow/script;
- healthy quiet hourly attempt changes tracked status bytes;
- current publisher can overwrite one source with an older watermark;
- Policy Watch current payload is published by more than hourly owner.

### Wire real owners

Hourly `.github/workflows/whitehouse-sentinel.yml`:

```text
python -m collectors.policy_event_clock
COLLECT_LANE=hourly python -m scripts.build_policy_turn_clock --mode publish-current
focused validation
stage only exact owned official/status/current artifact paths
existing normal rebase/push behavior
```

Nightly `scripts/ci/daily_engine_regional_desk_builders.sh` immediately before existing Policy Watch:

```text
python -m scripts.build_policy_turn_clock --mode ledger-only
```

No official-source network call nightly. No current JSON write nightly.

DAG mirrors both exact modes.

### Canonical CI ownership

Add the four new suites to one compatible existing logical owner in `.github/ci/legacy-jobs.yml`:

```text
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

`tests/test_policy_watch_ui.py` remains in its existing owner unless exact current manifest proves a non-duplicating compatible composition.

`tests/test_world_state.py` already has Neural Web ownership; extend that existing executable owner to cover the policy-turn lobe rather than creating a duplicate logical job. If current manifest structure proves a different minimal execution arrangement, preserve exactly-one intended owner per suite and document it.

Update source/test/template/workflow path closures precisely. Update `.github/workflows/ci.yml` triggers so test-only and source-only changes each schedule the owning jobs. Do not use broad globs to hide a missing dependency.

### Exact validation commands

At minimum, after materializing required checkout paths:

```bash
python -m pytest \
  tests/test_policy_event_clock.py \
  tests/test_futures_roll_calendar.py \
  tests/test_policy_turn_clock.py \
  tests/test_build_policy_turn_clock.py \
  tests/test_policy_watch_ui.py \
  tests/test_world_state.py \
  tests/test_dag_conformance.py -q
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
python3 scripts/agentos.py validate
git diff --check
```

Then run the exact selected logical owner(s) through the canonical pack runner, not only direct pytest.

### Required CI mutations

Each must RED, then restore:

1. remove one new suite from all manifest commands;
2. keep suite but remove its source subject from owner paths;
3. keep manifest owner but remove matching `ci.yml` trigger;
4. add duplicate logical owner;
5. add suite to unrun baseline;
6. delete unrelated current-main manifest marker;
7. remove nightly ledger-only invocation;
8. change nightly to publish-current;
9. change hourly lane to nightly;
10. advance only wall-clock attempt on quiet hour;
11. let one source watermark regress while another advances;
12. make nightly append with no eligible trigger;
13. call append helper directly off-lane and let it succeed;
14. remove Neural Web machine-consumer test from its real owner.

No new workflow/job/runner/permission/secret/concurrency/merge-control plane.

---

## Task 8 — Real end-to-end proof and immutable HOLD return

### Step 8.1 — Real official-source path

Against current public official surfaces, prove:

- at least one Fed actor/event receipt;
- at least one Treasury event/operation receipt when available;
- TreasuryDirect buyback semantics including purpose and separate amounts;
- source versions/watermarks and evidence cutoff;
- exact current phase derived independently from immutable source status;
- no unsupported actor-location claim.

If current source lacks a desired operation, prove typed no-data/unavailable behavior rather than manufacturing a positive row.

### Step 8.2 — Real existing market-owner path

After `data/` opt-in, read current canonical:

```text
OPEX/options owner
broad ETF flow owner
Treasury/TGA owner
Rebalance owner
Cboe VX front + standard monthly curve or canonical projection
market-state/volatility/breadth/credit confirmation owners
```

Prove source as-of/availability/staleness and short-history limitations. Do not backfill facts W1 does not own.

### Step 8.3 — Current artifact proof

Build one real `policy_turn_clock.v1` and show:

- exact schema/method/input digest/source watermarks;
- independent `option_support`, `broad_market_flow`, `support_composition`;
- correct futures-family separation;
- current state and predicate basis;
- gaps/disagreements;
- all authority false.

Run a synthetic mixed-source watermark replay proving source A can advance while source B’s regression is rejected/preserved-last-good. Run a source-failure/recovery replay and a correction replay.

### Step 8.4 — Policy Watch browser proof

Render real current artifact plus deterministic fixture states. Capture and review the complete binding evidence matrix:

```text
dark/light × EN/ZH × 1440/390
```

for fresh/support, rolloff, catalyst, degraded, unknown and conflict, plus 768 geometry checks.

Record:

- no console/page-origin errors;
- no document/card horizontal overflow;
- correct keyboard/focus behavior;
- current JSON fetch from same origin;
- degraded/unknown theme-specific mechanisms;
- distinct dark command-center and light research-workspace treatments;
- no stale embedded payload fallback.

### Step 8.5 — Durable direct machine proof

Using the real existing world-state call path, prove:

```text
site/policy_turn_clock.json
→ engine/neuralweb/world_state.py build_world_state()/build_and_write()
→ data/neuralweb/world_state.json policy_turn_clock lobe
```

Show the lobe preserves policy-turn method/input/state/axes/gaps/all-false authority and is derived from direct JSON, not HTML. Show missing/corrupt input produces the typed fail-open gap. Show same policy-turn digest remains deterministic; changed digest changes world-state semantic identity.

This is the required durable machine consumer. A one-off reader script does not satisfy acceptance.

### Step 8.6 — Prospective receipt proof

A natural nightly run may append only when one frozen first-seen trigger is actually eligible. Prove:

- no-trigger nightly run appends zero;
- eligible trigger appends at most one keep-FIRST receipt;
- rerun is idempotent;
- exact receipt identity is frozen;
- direct off-lane append is refused;
- a correction fixture appends a linked correction row without rewriting original.

If the real current nightly has no eligible trigger, zero rows is the correct production proof. Do not fabricate a live event just to create a receipt; use fixture proof for positive path and wait for a natural eligible trigger for later live evidence.

### Step 8.7 — Natural hosted CI

Push normally. Observe natural hosted CI to terminal state for the immutable head. Require:

- Agent OS/schema validation attributable to candidate;
- exact source-law/fence/contract-delta checks;
- selected logical jobs actually execute the new suites;
- canonical pack runner proof;
- no candidate-introduced failure;
- current-main relationship reconciled without force.

Inherited failures are named with main/head comparison evidence; do not repair foreign scope.

### Step 8.8 — Immutable return

Return on the canonical W1 carrier:

```text
RESULT / HOLD-FOR-SOL
operation
receiver/session identity
pickup ACK / continuity / START receipts
pickup base
current main integrated
head
tree
parents
changed-file census
planned-path collision census
focused tests
mutation tests
Agent OS validation
pack ownership/execution proof
hosted CI checks
official-source receipts
policy_turn_clock digest
per-source no-regress proof
quiet no-op proof
Policy Watch evidence matrix
Neural Web direct-machine-consumer proof
prospective receipt or lawful no-trigger zero-row proof
authority all-false proof
remaining gaps
effect=BUILT_NOT_PROVEN / PRODUCTION_INERT
```

Keep PR OPEN/DRAFT/HOLD with labels empty and auto-merge null. Do not mark Ready, merge, deploy, start issue #6794 outcome computation, wire Prophet/portfolio, or claim production/decision usefulness.

---

## Completion standard for this implementation PR

A W1 implementation candidate is reviewable only when one independently useful vertical exists end-to-end:

- **Truth:** correction-safe official/public evidence + exact source/freshness/nulls.
- **Intelligence:** deterministic separate axes, support composition, futures/calendar/catalyst precedence and explicit unknowns.
- **Product:** real Policy Watch dynamic consumer across dark/light, EN/ZH and desktop/mobile states.
- **Machine:** existing Neural Web world state directly consumes the same exact JSON contract.
- **Learning:** the nightly prospective lane is trigger-gated, keep-FIRST, correction-safe and capable of accruing evidence without unconditional rows.

Green CI, source files, generated JSON or a rendered card alone are insufficient.