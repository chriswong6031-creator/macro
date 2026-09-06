# Policy Turn Clock — CI / Runtime Owner Amendment

Date: 2026-09-03
Status: **FORWARD-REPAIRED BINDING AMENDMENT / HOLD-FOR-SOL / SPEC_ONLY**
Applies to: `policy_turn_clock.v1` W1 on Macro issue #6787
Architecture carrier: PR #6788

This amendment binds runtime ownership and executable CI for the Actor, Liquidity & Monthly Transition Clock. It does not START W1, create a new job/workflow, publish product bytes, append evidence or authorize merge/deploy.

## 1. Single-writer runtime topology

There is one current publisher:

```text
.github/workflows/whitehouse-sentinel.yml
  → collectors.policy_event_clock
  → COLLECT_LANE=hourly python -m scripts.build_policy_turn_clock --mode publish-current
  → current official evidence/status + site/policy_turn_clock.json
```

There is one prospective-ledger advancement opportunity:

```text
scripts/ci/daily_engine_regional_desk_builders.sh
  → COLLECT_LANE=nightly python -m scripts.build_policy_turn_clock --mode ledger-only
  → existing Policy Watch builder
```

`config/dag.yml` mirrors these real paths. It is not an executor.

Nightly does not collect official source evidence and never writes current Policy Watch JSON/HTML. Hourly never appends the prospective ledger.

## 2. Quiet-hour semantic no-op

Tracked bytes are governed by semantic identity, not wall-clock attempts.

A healthy hourly attempt with unchanged:

```text
method_version
input_digest
per-source semantic identity/source watermarks
source status
freshness class
correction lineage
```

must leave tracked official/status/current artifact bytes unchanged. `last_attempt_at` belongs in ephemeral workflow/log evidence and may not force a git-tracked rewrite.

A failure/recovery/staleness/parser-shape/correction/source advance is a semantic change and may publish the truthful new status/current projection.

## 3. Per-source watermark no-regress — binding executable law

Whole-payload `evidence_cutoff` comparison cannot authorize a source regression.

Before hourly publication, the builder fresh-reads the current artifact and reconciles every source key independently. Each source watermark carries owner-native source/revision/availability identity, semantic digest, correction lineage and a last-good evidence reference.

Required behavior:

```text
newer source identity     -> accept that source
same identity + same sem  -> source-level no-op
older source identity     -> retain current last-good/watermark; emit SOURCE_WATERMARK_REGRESSION
failure/stale transition  -> truthful degraded status + retain last-good evidence/watermark
valid correction          -> append/preserve lineage; accept only non-regressive correction identity
mixed A advance/B regress -> A advances, B remains last-good, B gap visible; recompute payload
all attempted regressions -> refuse/no-op current overwrite
```

After source reconciliation, recompute state, `input_digest`, freshness, gaps and `evidence_cutoff` from the accepted evidence set. The published cutoff itself may not move backward.

Mandatory tests in `tests/test_build_policy_turn_clock.py`:

```text
test_mixed_source_advance_and_regression_keeps_new_a_and_last_good_b
test_regressed_source_never_lowers_published_watermark
test_source_failure_preserves_last_good_evidence_and_marks_degraded
test_source_recovery_advances_from_preserved_last_good
test_equal_watermark_equal_semantics_is_noop
test_valid_correction_preserves_original_lineage_and_advances_correction_identity
test_correction_cannot_use_older_source_identity_to_overwrite_newer
test_all_regressive_inputs_refuse_current_overwrite
test_recomputed_evidence_cutoff_never_moves_backward
```

The discriminating mixed-source fixture is binding:

```text
published A=10 B=20
incoming  A=11 B=19
result    A=11 B=20(last-good), B regression gap visible
```

Rejecting the entire payload would lose a legitimate A advance; accepting B@19 would regress truth. The required result does neither.

## 4. Prospective ledger is trigger-gated, not nightly-appended

Path:

```text
data/policy_turn_clock/forward_log.jsonl
```

The append seam itself must call:

```python
engine.ledger_lane.nightly_advance_enabled()
```

so a direct helper call cannot bypass the lane boundary.

`COLLECT_LANE=nightly` is necessary but not sufficient. A row may append only for one eligible **first-seen** trigger selected by frozen precedence:

```text
material_state_change
high_impact_event_t24
opex_t_minus_2
post_opex_t_plus_1
month_or_quarter_end_pulse
vx_t_minus_2
vx_rank_roll_boundary
```

Nightly with no eligible first-seen trigger appends **zero** rows and is a successful semantic no-op.

Receipt identity is exactly:

```text
(as_of, trigger_kind, trigger_id, method_version, input_digest)
```

A single invocation appends at most one receipt. If multiple first-seen triggers occur, select the first unseen trigger by the frozen order above. Exact identity reruns are keep-FIRST/no-op.

Corrections append a new `record_kind=correction` row with:

```text
correction_of_receipt_id
original method/input/evidence-cutoff identity
source correction lineage
corrected method/input/source identity
```

They never rewrite the original row. A missing correction target is refused. Correction append is still nightly-lane-gated.

Mandatory executable tests in `tests/test_build_policy_turn_clock.py`:

```text
test_hourly_publish_never_appends_forward_receipt
test_nightly_ineligible_trigger_is_noop
test_nightly_no_trigger_does_not_create_jsonl_file_or_row
test_direct_append_off_lane_is_refused_inside_append_seam
```

plus one parametrized positive test for every trigger family, and:

```text
test_receipt_identity_is_asof_trigger_kind_trigger_id_method_and_input_digest
test_exact_receipt_identity_is_keep_first_on_rerun
test_new_trigger_id_is_not_deduped_as_old_trigger
test_multiple_simultaneous_triggers_use_frozen_precedence_and_append_at_most_one
test_correction_appends_linked_row_without_rewriting_original
test_correction_row_names_original_receipt_and_source_lineage
test_correction_target_missing_is_refused
test_correction_append_is_still_refused_off_nightly_lane
```

These tests exist specifically to kill an implementation that appends once per nightly invocation regardless of event eligibility.

## 5. Options and broad-flow CI contract

Options support and broad-market flow are distinct data axes.

Binding test law in `tests/test_policy_turn_clock.py`:

```text
option_support contains only options/OPEX-owner evidence
broad_market_flow contains only the canonical broad ETF-flow owner projection
option_support has no applicable_support_count / K-of-N result
support_composition is the only cross-axis K-of-N block
broad flow cannot be copied into option_support
stale broad flow leaves option_support unchanged and contributes no supportive vote
SUPPORT_BUILDING requires >=2 independent applicable mechanism families in support_composition
```

The corrected discriminating assertion is:

```python
assert "applicable_support_count" not in out["option_support"]
assert out["support_composition"]["applicable_support_count"] >= 2
```

No weights or hidden scalar score.

## 6. Durable direct machine-consumer executable owner

The direct machine consumer is the existing Neural Web N1 world-state plane:

```text
owner:       engine/neuralweb/world_state.py
input:       site/policy_turn_clock.json
output:      data/neuralweb/world_state.json -> policy_turn_clock lobe
call site:   build_world_state()/build_and_write(), invoked by existing scripts/build_world_state.py
proof:       tests/test_world_state.py
```

`tests/test_world_state.py` must prove direct JSON consumption, preservation of schema/method/input/state/independent axes/gaps/all-false authority, deterministic semantic identity and fail-open missing/corrupt/wrong-schema behavior. HTML scraping and a sibling machine store/API are forbidden.

The policy-turn additions to `tests/test_world_state.py` execute through the existing Neural Web logical CI owner. Do not create a new logical job merely to name the consumer.

## 7. Policy Watch evidence owner

`tests/test_policy_watch_ui.py` plus governed visual-evidence tooling must bind the design packet from the primary design:

```text
DARK: command-center luminance depth / restrained glow only for fresh state
LIGHT: research-workspace white material / hairlines / modest shadow instead of glow
```

Dark degraded/unknown and light degraded/unknown require distinct theme-specific material mechanisms while preserving the same semantics. Token swap alone is insufficient.

Mandatory evidence matrix:

```text
dark/light × EN/ZH × 1440/390
```

for fresh/support, rolloff, catalyst, degraded, unknown and conflict; 768 functional/geometry checks are additive.

Relevant existing checks:

```bash
python3 scripts/check_design_system.py --mode enforce-added
python3 scripts/check_runtime_style_injection.py
python3 scripts/check_ui_visual_evidence.py
```

A human reviewer adjudicates actual art direction; CI proves receipt/state identity, not taste.

## 8. Shared CI ownership gate

W1 does not START while any unruled current owner collides on a planned shared CI path.

At this forward-repair census, active open owners of `.github/ci/legacy-jobs.yml` still included:

```text
#6721
#6706
#6651
#6625
#6514
#6389
#6296
```

`.github/workflows/ci.yml` remained actively owned by open #6628. PR #6791 had merged and was not a live owner. This list is a timestamped observation, not a lock. The W1 worker must repeat the **complete current census** at START and before the shared edit.

No new workflow/job/CI planner may be used to evade this gate.

## 9. Canonical logical-job composition

After the collision gate is open, the smallest additive composition is:

- put the four new W1 suites in one compatible existing policy/front-facing logical job in `.github/ci/legacy-jobs.yml`;
- preserve `tests/test_policy_watch_ui.py` in its canonical existing owner unless current manifest proves another exact non-duplicating composition;
- extend the existing Neural Web owner to execute the policy-turn additions in `tests/test_world_state.py`;
- add precise source/test/template/script/workflow path closures;
- add matching `.github/workflows/ci.yml` triggers;
- include the real nightly script and hourly workflow/DAG subjects in the applicable conformance owner;
- preserve unrelated current-main manifest/workflow bytes;
- run selected logical owners through the canonical pack runner.

No:

```text
new logical job
new workflow
new runner or trust plane
new permission/secret
new concurrency controller
new merge controller
new unrun-test exemption
```

unless a later separate Sol ruling explicitly changes architecture.

## 10. Required exact validation

After required sparse trees are materialized:

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

Then run the exact selected logical job(s) through the canonical pack runner. Direct pytest alone is not executable CI proof.

## 11. Required hostile mutations

Each mutation must RED, then be restored:

| Mutation | Required discriminator |
|---|---|
| delete one W1 suite from all manifest commands | unrun/owner failure |
| source subject omitted from owner paths | source-law/path-closure failure |
| manifest owner exists but `ci.yml` trigger removed | trigger conformance failure |
| duplicate logical owner | duplicate-owner failure |
| suite added to unrun baseline | forbidden-baseline failure |
| unrelated current-main manifest line deleted | current-main preservation diff/review failure |
| nightly clock invocation removed | runtime/DAG conformance failure |
| nightly mode changed to `publish-current` | single-writer failure |
| hourly lane changed to nightly | lane/ledger failure |
| quiet wall-clock-only rerun rewrites tracked bytes | semantic no-op failure |
| source A advances while B regresses and B@old is accepted | per-source no-regress failure |
| source A advances while B regresses and entire A advance is discarded | mixed-source preservation failure |
| nightly with no trigger appends a row | ineligible-trigger no-op failure |
| direct off-lane append succeeds | append-seam lane failure |
| correction rewrites original receipt | append-only correction failure |
| `option_support.applicable_support_count` reintroduced | axis-separation failure |
| broad flow copied into `option_support` | axis-owner failure |
| Neural Web consumer test removed from real owner | direct machine-consumer execution failure |
| world state scrapes Policy Watch HTML | machine-contract failure |
| light theme uses only token swap and no required evidence receipt | design-evidence failure / human reject |

## 12. Natural hosted CI and return

Push only through the normal branch. Observe natural hosted CI on the immutable W1 head. Return only after the selected owner(s), Agent OS/schema/source-law/fence/contract-delta checks and canonical pack execution are terminal or a typed inherited hold is proven.

Keep the implementation PR Draft/HOLD, labels empty, auto-merge null. No Ready, merge, deploy, issue #6794 outcome computation or production/decision-usefulness claim.

This amendment freezes executable ownership. It does not claim that W1 is built or that the future shared-path collisions are already released.