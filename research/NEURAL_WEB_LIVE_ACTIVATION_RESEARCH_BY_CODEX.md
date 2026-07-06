# Neural Web Live Activation Research

Date: 2026-07-06  
Status: build-ready research handoff  
Scope: make Neural Web visibly daily, inspectable, and operationally honest.

## Executive Verdict

Neural Web is structurally real today. The repo already has a spine, world state,
kernel estimates, confluence graph, cortex memo, governance rails, synapse
registry, and a Mastermind bridge context. What is missing is the operating layer
that makes those rails feel alive to an operator.

The activation target is not "invent more alpha." The target is:

1. Every daily run can answer whether the cortex actually reasoned.
2. Every registered lobe can show whether it is fresh, stale, missing, or degraded.
3. Bottom-sensor context that already exists in code is refreshed before downstream
   consumers read it.
4. The user gets a canonical daily answer to: "What did Neural Web do today?"

The four proposed fixes are therefore the right next layer. They turn Neural Web
from a set of artifacts into a daily operating organism.

## Already Covered And Excluded

This document does not rehash the Neural Web masterplan, authority ladder,
kernel math, spine construction, confluence graph, or Mastermind bridge theory.
Those are already covered elsewhere in the repo. This handoff is about the
missing live-operating surface around those systems.

Non-goals:

- Do not give Neural Web new trading authority.
- Do not let cortex originate money-path signals.
- Do not turn bottom sensors into ranking, gating, or push-floor logic.
- Do not block the full daily site publish just because cortex fails.
- Do not pipe raw graph or parquet payloads into hot prompts.
- Do not use an LLM to write the first version of the daily brief.

The correct first version is deterministic, display-first, and brutally honest.

## Current Verified Baseline

The July 6, 2026 audit shows a mixed but useful state.

What is live:

- The daily workflow completed on July 6, 2026.
- The live Committee page was freshly served from `mastermind-x.com`.
- `/api/health` answered successfully on `mastermind-x.com`.
- `data/neuralweb/spine_index.parquet` existed with 288,666 rows.
- `data/neuralweb/confluence_graph.json` existed with 148 nodes and 649 edges.
- `data/neuralweb/world_state.json` existed and was included in the Mastermind
  context build.
- `data/neuralweb/mastermind_context.json` existed and exposed lobes including
  bottom sensors, contradictions, cortex, market, options entry, and reliability.

What is not live enough:

- The daily cortex memo reported zero tool-call batches and zero individual
  tool calls. It wrote a forced partial memo instead of proving that deliberation
  happened.
- The cortex job had an OAuth token present, but the model call failed with a
  connection error. The `ANTHROPIC_API_KEY` value observed in the job was empty.
- The bottom-sensor artifact existed, but its `as_of` was July 2, 2026 and the
  producer was not wired into `.github/workflows/daily.yml`.
- `config/synapse.yml` registered bottom sensors as `daily-engine`, but the daily
  workflow did not call `scripts.build_bottom_sensors`.
- The repo has many lobe artifacts, but there is no single machine-readable
  health artifact that answers freshness, row count, authority tier, and producer
  status for all of them.
- There is no canonical daily brief that summarizes changed, contradictory,
  stale, and operator-attention items.

The gap is not conceptual. It is observability plus a few missing producer links.

## Activation Architecture

The desired flow should become:

```text
daily engine builds source artifacts
  -> world_state
  -> bottom_sensors
  -> mastermind_context
  -> neuralweb_health
  -> neuralweb_daily_brief
  -> commit data/ and site/
  -> cortex job reads committed context
  -> cortex either records real tool calls or records degraded/red status
```

The brief can be built in the engine job from deterministic artifacts. Cortex can
still run after the engine job, but the system must not claim the cortex thought
if it had zero tool calls.

## Lane 1: Fix Cortex Model Execution And Red 0-Tool Runs

### What This Will Do

This lane makes the cortex job produce one of two explicit outcomes:

- `ok`: a model provider responded, tool calls were made, and the memo reflects
  actual deliberation over read tools.
- `degraded`: the model did not complete a meaningful tool loop, or it made zero
  tool calls, and the run is visibly red/non-healthy in downstream health surfaces.

The current behavior is too soft. A forced memo with a human-readable summary
like "budget exhausted after 0 tool-call batches" is useful, but it is not enough.
It needs structured status fields that every downstream page and API can read.

### How It Helps

This answers the user's core question: "Did Neural Web actually do anything
today?"

Without this lane, the cortex can fail at turn zero and the rest of the system
still looks broadly green. That creates false confidence. With this lane, the
operator sees:

- cortex did run and looked at these artifacts, or
- cortex did not really run and here is why.

This preserves the repo's fail-open law while removing silent ambiguity. The site
can still publish, but Neural Web should not get to wear a green badge when its
thinking layer never connected.

### Repo Evidence

Relevant files:

- `engine/neuralweb/cortex.py`
- `engine/llm_auth.py`
- `tests/test_cortex.py`
- `.github/workflows/daily.yml`
- `data/neuralweb/cortex/memo.json`
- `data/neuralweb/cortex/probation.json`
- `admin/neural_web.py`

The cortex implementation already has:

- staleness gating via `data/neuralweb/cortex/last_run_state.json`
- read tools and write tools
- a tool-call budget
- a forced memo path
- probation gating for A2 authority
- offline test coverage with mocked clients

The weak point is provider execution:

- `_run_tool_loop()` chooses one provider and calls the SDK directly.
- A connection exception breaks the loop instead of trying the next valid provider.
- The forced memo path encodes degradation mostly as prose.
- The job can finish successfully while the cortex had zero calls.

### Build Design

Add a structured cortex run status to the memo.

Recommended fields:

```json
{
  "status": "ok",
  "degraded": false,
  "degradation_reason": null,
  "model_provider_attempts": [
    {
      "provider": "oauth",
      "model": "claude-opus-4-20250514",
      "attempted": true,
      "ok": true,
      "error_type": null,
      "error_message": null
    }
  ],
  "tool_call_batches": 3,
  "individual_tool_calls": 9,
  "expected_min_tool_calls": 1,
  "tool_call_census": {
    "read_world_state": 1,
    "read_contradictions": 1,
    "read_graph": 1,
    "write_memo": 1
  }
}
```

For a failed run:

```json
{
  "status": "degraded",
  "degraded": true,
  "degradation_reason": "model_unavailable",
  "model_provider_attempts": [
    {
      "provider": "oauth",
      "attempted": true,
      "ok": false,
      "error_type": "connection_error",
      "error_message": "Connection error."
    },
    {
      "provider": "anthropic",
      "attempted": false,
      "ok": false,
      "error_type": "missing_credential",
      "error_message": "ANTHROPIC_API_KEY not set"
    }
  ],
  "tool_call_batches": 0,
  "individual_tool_calls": 0,
  "expected_min_tool_calls": 1
}
```

Implementation notes:

1. Keep the existing fail-open behavior. `engine.neuralweb.cortex` should still
   return success to the workflow so site publication is not gated.
2. Add a provider-iteration helper in `engine/neuralweb/cortex.py`.
3. Try the next available provider on connection and timeout errors.
4. Mark 401/403 auth failures as auth-dead through the existing `llm_auth`
   machinery where possible.
5. Keep DeepSeek excluded from cortex deliberation unless the governance docs
   explicitly permit it for this path.
6. Always write a memo envelope with structured status.
7. Mirror status into the site copy if a site cortex artifact is used.
8. Surface cortex status in `neuralweb_health.json` and the admin panel.

Suggested helper shape:

```python
def _call_model_with_failover(providers, *, messages, tools, max_tokens, temperature):
    attempts = []
    for provider in providers:
        attempt = {"provider": provider["name"], "attempted": False, "ok": False}
        if not provider.get("client"):
            attempt.update(error_type="missing_client", error_message="no client")
            attempts.append(attempt)
            continue
        attempt["attempted"] = True
        try:
            response = provider["client"].messages.create(...)
            attempt["ok"] = True
            attempts.append(attempt)
            return response, attempts
        except Exception as exc:
            attempt.update(
                error_type=_classify_model_error(exc),
                error_message=str(exc)[:300],
            )
            attempts.append(attempt)
            if _is_auth_error(exc):
                llm_auth.mark_dead(provider["name"], "auth")
            continue
    return None, attempts
```

The actual implementation should use local code style, but the behavior should
match this contract.

### Red/Degraded Display Rules

Use these rules across health and UI:

- `status=ok`: at least one model response completed and at least one meaningful
  read or write tool call happened.
- `status=warn`: model completed, but tool calls were below expectation, or only
  fallback memo happened.
- `status=degraded`: zero tool calls, all providers unavailable, invalid model
  response, or forced memo before deliberation.
- `status=skipped`: staleness gate intentionally skipped the model because inputs
  were unchanged. This is not red if the last successful run remains fresh.

Important distinction: "red" should mean operationally degraded, not "block the
entire publish." Cortex is a brain lobe, not the deploy gate.

### Tests To Add

Use `tests/test_cortex.py`.

Add or extend tests for:

- provider failover after an OAuth connection error
- missing `ANTHROPIC_API_KEY` recorded as a provider attempt
- zero tool calls writes `status=degraded`
- budget exhaustion after nonzero reads writes `status=warn` or `degraded`
  depending on policy
- staleness-gated skip does not overwrite last good run with fake green
- no providers available writes structured `model_unavailable`
- health extraction can read old cortex memos that do not yet have status fields

### Acceptance Criteria

- A real daily cortex run with tools produces `status=ok`.
- A zero-tool daily cortex run produces `status=degraded`.
- The health artifact and admin surface show cortex as degraded/red when tool
  calls are zero.
- The daily workflow still completes and publishes non-cortex artifacts.
- Offline cortex tests remain fully mocked and do not spend API calls.

## Lane 2: Wire `build_bottom_sensors` Into Daily

### What This Will Do

This lane makes the bottom-sensor lobe refresh every daily engine run, after the
stock-library and world-state inputs are available and before Mastermind context
is compiled.

The code already exists:

- `scripts/build_bottom_sensors.py`
- `engine/neuralweb/bottom_sensors.py`
- `tests/test_bottom_sensors.py`
- `config/synapse.yml` registration
- `docs/SIGNAL_BUS.md` registration

The missing part is workflow execution.

### How It Helps

Bottom sensors are the first place where Neural Web can feel like it is watching
the market rather than just preserving memory. They expose names in states like:

- `WATCH`
- `FRESH_FIRE_TACTICAL`
- `FRESH_FIRE_DURABLE_CAND`
- `HOLD_LAUNCHED`
- `CHASE_RISK`
- `KNIFE_RISK`
- `DEAD_MONEY_RISK`

They also carry entry-context fields such as coiling, distance from lows/highs,
earnings windows, sponsorship state, repair state, and quality bands. That is
exactly the connective tissue needed for the Mastermind bridge and daily brief.

Without daily wiring, downstream consumers can read stale bottom context while
the registry claims the lobe is daily. That is the kind of mismatch the live
operating layer must eliminate.

### Repo Evidence

Current behavior from the July 6 audit:

- `site/neuralwebdata/bottom_sensors.json` existed.
- Its `as_of` was July 2, 2026.
- It contained 1,722 rows.
- A local assemble run completed in about 2.6 seconds.
- The script warned that Oracle panel inputs were missing, but still degraded
  gracefully and produced rows.
- `rg` found no invocation of `build_bottom_sensors` in the daily workflow.

The script comment already says the daily slot should be after world-state when
runtime remains small. The current runtime is comfortably small.

### Build Design

Add a daily workflow step after `build world state (neural-web W1)` and before
`build mastermind context (NW bridge)`.

Recommended workflow step:

```yaml
- name: build bottom sensors (Neural Web entry lobe)
  if: always()
  # Refreshes data/neuralweb/bottom_sensors.parquet and
  # site/neuralwebdata/bottom_sensors.json before Mastermind context reads lobes.
  # Display-only: no ranking, gating, push-floor, or money-path authority.
  # Fail-soft: a failed build leaves the last committed bottom-sensor artifact.
  run: python -m scripts.build_bottom_sensors || echo "::warning::build_bottom_sensors failed (non-fatal - keeping last committed bottom sensors)"
```

Also update `config/dag.yml` so workflow conformance knows the new step is
intentional. The repo already has DAG conformance patterns, so a workflow-only
change is likely to fail or drift unless the DAG declaration moves with it.

Suggested order in the engine band:

```text
oracle_nightly
build_world_state
build_bottom_sensors
build_nw_mastermind_context
build_options_flow_attention
commit_engine_outputs
```

The important invariant is:

```text
bottom_sensors must be fresher before mastermind_context snapshots lobes
```

### Staleness And Gap Handling

Bottom sensors should remain display-only at birth.

Known partial-input gaps should be recorded, not treated as hard failures:

- missing Oracle short/medium panels
- missing sponsorship primitives
- missing repair primitives
- earnings data gaps

The health artifact should distinguish:

- producer failed
- artifact missing
- artifact stale
- artifact fresh but partial

"Fresh but partial" is better than stale silence.

### Tests To Add

Use existing `tests/test_bottom_sensors.py`.

Add or confirm coverage for:

- JSON artifact envelope includes `as_of`, `n_rows`, `rows`, and display-only flag.
- Missing Oracle panels do not fail the build.
- Empty or partial input sets produce a valid artifact with explicit gaps.
- Schema remains stable.

Add a workflow/DAG check if there is an existing conformance test path. The
minimum static assertion is that `scripts.build_bottom_sensors` appears in both
`.github/workflows/daily.yml` and `config/dag.yml`.

### Acceptance Criteria

- Next daily run updates `site/neuralwebdata/bottom_sensors.json`.
- `as_of` matches the latest available trading-date context, not a stale prior
  week artifact.
- `mastermind_context.json` sees bottom sensors after the refresh.
- Health shows bottom sensors as `fresh` or `fresh_partial`, not stale.
- No money-path behavior changes.

## Lane 3: Add `neuralweb_health.json`

### What This Will Do

This lane adds a single machine-readable operating truth file:

- `data/neuralweb/health.json`
- `site/neuralwebdata/health.json`

It should summarize every important lobe and artifact with:

- lobe id
- artifact id
- path
- `as_of`
- produced timestamp
- freshness status
- row count
- byte size
- authority tier
- horizon role
- producer
- last successful producer observation
- gaps
- degraded status

This is the answer to: "Is Neural Web live right now?"

### How It Helps

The repo already has many artifacts and a synapse registry, but the operator
needs one page-loadable truth source. Health turns scattered artifact knowledge
into a single inspectable status object.

It helps four audiences:

- User/operator: sees whether Neural Web actually updated today.
- Claude/Codex/Fable: gets one canonical state file before making changes.
- Admin/Committee UI: can render honest green/yellow/red lobe badges.
- Future automation: can alert on stale, missing, or degraded lobes without
  parsing every artifact.

It also closes the registry/workflow mismatch class of bug. If `synapse.yml`
claims a lobe is daily, but the workflow never produces it, health should say so.

### Repo Evidence

The repo already has most inputs:

- `config/synapse.yml` has producer, cadence, storage, tier, horizon role,
  freshness SLA, consumers, and external consumers.
- `engine/neuralweb/mastermind_context.py` already builds a lobe manifest.
- `admin/neural_web.py` already computes some SLA freshness, but only inside
  the admin panel and not as a durable artifact.
- Cortex memo already has a `tool_call_census`, but needs structured status.
- Bottom sensors already carry `as_of` and `n_rows` in site JSON.

So the health builder should compose existing metadata, not create a new
parallel registry.

### Build Design

Add:

- `engine/neuralweb/health.py`
- `scripts/build_neuralweb_health.py`

The CLI should:

1. Read `config/synapse.yml`.
2. Select Neural Web relevant artifacts from the registry and bridge manifest.
3. Inspect each artifact path without running heavy producers.
4. Compute freshness against `freshness_sla_hours`.
5. Count rows cheaply.
6. Read cortex memo/probation for status.
7. Emit `data/neuralweb/health.json`.
8. Emit public copy `site/neuralwebdata/health.json`.

Run it after `build_nw_mastermind_context` and before `commit engine outputs`.

Recommended workflow slot:

```text
build_world_state
build_bottom_sensors
build_nw_mastermind_context
build_neuralweb_health
build_neuralweb_brief
```

### Proposed Schema

```json
{
  "schema": "neuralweb.health.v1",
  "produced_at": "2026-07-06T09:05:00Z",
  "as_of": "2026-07-06",
  "overall_status": "warn",
  "summary_counts": {
    "lobes_total": 12,
    "fresh": 9,
    "fresh_partial": 1,
    "stale": 1,
    "missing": 0,
    "degraded": 1
  },
  "lobes": [
    {
      "id": "bottom_sensors",
      "artifact_id": "neuralweb-bottom-sensors",
      "path": "site/neuralwebdata/bottom_sensors.json",
      "data_path": "data/neuralweb/bottom_sensors.parquet",
      "producer": "scripts/build_bottom_sensors.py",
      "last_successful_producer": "scripts/build_bottom_sensors.py",
      "cadence": "daily-engine",
      "owner_program": "neural-web",
      "tier": "display",
      "horizon_role": "tactical_entry",
      "authority": {
        "mode": "display",
        "can_rank": false,
        "can_gate": false,
        "can_originate": false
      },
      "as_of": "2026-07-06",
      "produced_at": "2026-07-06T08:44:00Z",
      "age_hours": 0.4,
      "freshness_sla_hours": 30,
      "status": "fresh_partial",
      "row_count": 1722,
      "byte_size": 524288,
      "gaps": [
        "oracle_panel_s_missing",
        "oracle_panel_m_missing"
      ],
      "evidence": [
        "data/neuralweb/bottom_sensors.parquet",
        "site/neuralwebdata/bottom_sensors.json"
      ]
    }
  ],
  "cortex": {
    "status": "degraded",
    "tool_call_batches": 0,
    "individual_tool_calls": 0,
    "degradation_reason": "model_unavailable",
    "probation_granted": false
  },
  "workflow_conformance": {
    "bottom_sensors_declared_daily": true,
    "bottom_sensors_found_in_daily_workflow": true,
    "bottom_sensors_found_in_dag": true
  }
}
```

### Row Count Rules

Do not fully load large artifacts unless necessary.

Recommended count logic:

- JSON with `n_rows`: use `n_rows`.
- JSON with `rows`: use `len(rows)`.
- JSON with `candidate_context`: use `len(candidate_context)`.
- JSONL: count lines, capped or streaming.
- Parquet: use pyarrow metadata if available.
- Missing pyarrow: fall back to `None`, not failure.

### Status Rules

Recommended lobe statuses:

- `fresh`: artifact exists and age is within SLA.
- `fresh_partial`: artifact exists and is within SLA but reports gaps.
- `stale`: artifact exists but exceeds SLA.
- `missing`: expected artifact path does not exist.
- `degraded`: artifact exists but reports an explicit degraded status, or cortex
  had zero tool calls.
- `unknown`: insufficient metadata.

Recommended overall rules:

- `ok`: no stale, missing, or degraded lobes.
- `warn`: stale or fresh-partial lobes exist, but no critical degraded lobe.
- `degraded`: cortex degraded, core world state missing/stale, or major lobe
  missing.

### Last Successful Producer

Do not rely on live GitHub API calls inside the nightly health builder. Health
should be deterministic from committed files.

For v1, define `last_successful_producer` as:

```text
the synapse producer associated with the newest existing artifact that passes
the lobe's minimum validity check
```

If the artifact is missing, set it to `null`. If the artifact exists but is
stale, keep the producer but mark status `stale`.

Future v2 can append a local `data/neuralweb/producer_runs.jsonl` ledger if exact
producer success history becomes necessary.

### Admin And UI Consumption

Update `admin/neural_web.py` to read `data/neuralweb/health.json` if present.

Keep the current fallback behavior:

- no engine imports
- no subprocesses
- committed artifacts only
- missing files fail open with honest placeholders

The admin panel should stop re-deriving everything once the health file exists.
It can still keep fallbacks for older clones.

### Tests To Add

Create `tests/test_neuralweb_health.py`.

Coverage:

- fresh JSON artifact with `n_rows`
- stale artifact by mtime or produced timestamp
- missing artifact
- parquet row count via metadata or graceful fallback
- cortex zero-tool memo makes cortex degraded
- old cortex memo without new fields remains parseable
- registry metadata maps through tier and horizon role
- workflow conformance flags missing bottom-sensor daily step
- site copy is written

### Acceptance Criteria

- `site/neuralwebdata/health.json` exists after daily.
- It includes every major lobe consumed by `mastermind_context.json`.
- Cortex can never be silently green after a zero-tool run.
- Bottom sensors cannot be registered daily while unwired without a warning.
- Admin/Committee can render lobe status from one file.

## Lane 4: Add Daily Neural Web Brief

### What This Will Do

This lane adds a deterministic daily brief:

- `data/neuralweb/daily_brief.json`
- `site/neuralwebdata/daily_brief.json`
- optional append-only history: `data/neuralweb/daily_brief_history.jsonl`

The brief answers:

- What changed?
- What contradicted?
- What is stale?
- What deserves operator attention?

It should be the canonical "what did Neural Web do today?" surface.

### How It Helps

Health tells the operator whether the organism is alive. The brief tells the
operator what it noticed.

The brief is the most important human-facing unlock because it converts hidden
artifact churn into an actual daily narrative. It also forces the system to admit
when nothing meaningful changed.

Good daily brief behavior:

- "Cortex did not complete model deliberation today."
- "Bottom sensors refreshed and produced 1,722 rows."
- "World state is stale by two sessions."
- "Confluence graph still has four contradiction records."
- "Operator attention: fix provider credentials before treating cortex as live."

Bad daily brief behavior:

- "The market is bullish because Neural Web says so."
- "Buy these setups."
- "Cortex validated this."
- "All systems healthy" when cortex had zero tool calls.

### Build Design

Add:

- `engine/neuralweb/daily_brief.py`
- `scripts/build_neuralweb_brief.py`

Inputs:

- `data/neuralweb/health.json`
- `data/neuralweb/mastermind_context.json`
- `data/neuralweb/world_state.json`
- `data/neuralweb/confluence_graph.json`
- `data/neuralweb/cortex/memo.json`
- previous `data/neuralweb/daily_brief.json` if present
- optional previous `data/neuralweb/health.json` snapshot from history

Outputs:

- `data/neuralweb/daily_brief.json`
- `site/neuralwebdata/daily_brief.json`
- append one compact row to `data/neuralweb/daily_brief_history.jsonl`

Run after `build_neuralweb_health`.

### Proposed Schema

```json
{
  "schema": "neuralweb.daily_brief.v1",
  "produced_at": "2026-07-06T09:06:00Z",
  "as_of": "2026-07-06",
  "status": "warn",
  "did_the_brain_run": {
    "cortex_status": "degraded",
    "tool_call_batches": 0,
    "individual_tool_calls": 0,
    "summary": "Cortex wrote a fallback memo but made zero tool calls."
  },
  "what_changed": [
    {
      "kind": "lobe_refresh",
      "id": "bottom_sensors",
      "summary": "Bottom sensors refreshed from 2026-07-02 to 2026-07-06.",
      "severity": "info"
    }
  ],
  "what_contradicted": [
    {
      "id": "contradictions",
      "summary": "Confluence graph reports 4 contradiction/tension records.",
      "severity": "watch",
      "evidence_path": "data/neuralweb/confluence_graph.json"
    }
  ],
  "what_is_stale": [
    {
      "id": "world_state",
      "as_of": "2026-07-02",
      "freshness_sla_hours": 30,
      "severity": "warn"
    }
  ],
  "operator_attention": [
    {
      "priority": 1,
      "area": "cortex",
      "summary": "Fix model-provider execution; zero-tool cortex run is degraded.",
      "suggested_owner": "neural-web",
      "action_type": "ops_fix"
    }
  ],
  "candidate_watch": [
    {
      "ticker": "EXAMPLE",
      "summary": "Display-only bottom context changed.",
      "authority": "display_only"
    }
  ],
  "caveats": [
    "Daily brief is deterministic and display-only.",
    "No trading authority is implied."
  ]
}
```

### Delta Method

Do not compute nightly deltas by shelling out to `git diff` on large files.

Instead, store compact previous state:

```json
{
  "as_of": "2026-07-06",
  "lobe_status": {
    "bottom_sensors": {
      "as_of": "2026-07-06",
      "status": "fresh",
      "row_count": 1722,
      "hash": "abc123"
    }
  },
  "contradiction_count": 4,
  "cortex_status": "degraded"
}
```

The brief builder can compare today's compact snapshot to the previous snapshot
from `daily_brief_history.jsonl`.

Suggested change detection:

- `as_of` changed
- `status` changed
- row count changed materially
- contradiction count changed
- cortex status changed
- stale lobe entered or exited stale state
- new gap note appeared
- candidate context count changed

### Contradiction Summary

For v1, summarize contradiction counts and a few records. Do not overinterpret.

Inputs:

- `confluence_graph.json` edge types such as contradiction/tension/note
- `mastermind_context.json` contradiction lobe summary if present

Output:

- count
- top records
- whether count increased/decreased from prior brief
- evidence path

Avoid language like "resolved" unless the history explicitly supports it. Prefer
"no longer present in the current graph" if a prior contradiction disappears.

### Operator Attention Rules

Operator attention should be deterministic and conservative.

Priority examples:

- P1: cortex degraded with zero tool calls
- P1: world state missing
- P1: Mastermind context missing
- P2: registered daily lobe stale
- P2: bottom sensors unwired or stale
- P2: contradiction count increased
- P3: fresh-partial lobe has known missing optional inputs

This section should never recommend a trade. It should recommend maintenance,
inspection, or follow-up research only.

### UI Placement

First version can be JSON-only.

Then expose it in one or both:

- Admin Neural Web panel
- Committee page/Neural Web section

Keep UI copy short:

- status badge
- "brain run" line
- 3 changed items
- 3 stale items
- 3 operator attention items

Put detailed records behind expanders or JSON links. The user has repeatedly
preferred compressed surfaces with progressive disclosure.

### Tests To Add

Create `tests/test_neuralweb_daily_brief.py`.

Coverage:

- first run without prior brief
- cortex degraded produces operator attention
- stale lobe from health appears in `what_is_stale`
- contradiction count appears
- bottom-sensor refresh appears in `what_changed`
- no trading verbs or rank/gate fields appear
- site copy is written
- malformed optional inputs fail open

### Acceptance Criteria

- `site/neuralwebdata/daily_brief.json` exists after daily.
- It answers the four user questions in structured fields.
- It records cortex zero-tool runs as degraded.
- It names stale lobes from health.
- It never gives trading authority.
- Admin/Committee can render it without importing engine code.

## Build Order

Recommended rollout:

1. Cortex status hardening.
2. Bottom-sensor daily wiring.
3. Health artifact.
4. Daily brief.
5. Admin/Committee display.

This order works because health depends on cortex status and bottom-sensor
freshness, and the daily brief depends on health.

PR split:

- PR A: cortex provider failover plus structured degraded status.
- PR B: wire bottom sensors into daily and DAG conformance.
- PR C: health builder and health site artifact.
- PR D: daily brief builder and optional UI read path.

PR B and PR C can be combined if the code is small, but PR A should stand alone
because cortex provider handling has different failure risk.

## Workflow Integration Target

Target engine job order:

```yaml
- name: build world state (neural-web W1)
  run: python -m scripts.build_world_state || echo "::warning::build_world_state failed (non-fatal) - keeping last committed world_state"

- name: build bottom sensors (Neural Web entry lobe)
  run: python -m scripts.build_bottom_sensors || echo "::warning::build_bottom_sensors failed (non-fatal - keeping last committed bottom sensors)"

- name: build mastermind context (NW bridge)
  run: python -m scripts.build_nw_mastermind_context || echo "::warning::build_nw_mastermind_context failed (non-fatal) - keeping last committed mastermind_context"

- name: build neuralweb health
  run: python -m scripts.build_neuralweb_health || echo "::warning::build_neuralweb_health failed (non-fatal - keeping last committed health)"

- name: build neuralweb daily brief
  run: python -m scripts.build_neuralweb_brief || echo "::warning::build_neuralweb_brief failed (non-fatal - keeping last committed daily brief)"
```

All outputs should live under `data/` and `site/` so the existing `git add data/
site/ reports/` commit step stages them.

## Config And Registry Work

Required registry changes:

- Ensure bottom sensors remain registered in `config/synapse.yml`.
- Add health artifact registration:
  - path: `data/neuralweb/health.json`
  - site path: `site/neuralwebdata/health.json` if site artifacts are registered
  - producer: `scripts/build_neuralweb_health.py`
  - cadence: `daily-engine`
  - tier: `infrastructure`
  - horizon_role: `context`
  - weights: `none`
- Add daily brief artifact registration:
  - path: `data/neuralweb/daily_brief.json`
  - site path: `site/neuralwebdata/daily_brief.json`
  - producer: `scripts/build_neuralweb_brief.py`
  - cadence: `daily-engine`
  - tier: `display`
  - horizon_role: `context`
  - weights: `none`

Required DAG changes:

- Add `scripts.build_bottom_sensors`.
- Add `scripts.build_neuralweb_health`.
- Add `scripts.build_neuralweb_brief`.

Required docs changes:

- Update `docs/SIGNAL_BUS.md` with the two new artifacts.
- Mention that health is the canonical lobe status surface.
- Mention that daily brief is deterministic and display-only.

## Validation Plan

Local validation:

```bash
python -m scripts.build_bottom_sensors
python -m scripts.build_nw_mastermind_context
python -m scripts.build_neuralweb_health
python -m scripts.build_neuralweb_brief
python -m pytest tests/test_bottom_sensors.py tests/test_cortex.py tests/test_neuralweb_health.py tests/test_neuralweb_daily_brief.py
```

If new tests do not yet exist, run the existing relevant coverage first:

```bash
python -m pytest tests/test_bottom_sensors.py tests/test_cortex.py tests/test_admin_neural_web.py
```

Static checks:

```bash
rg "build_bottom_sensors" .github/workflows/daily.yml config/dag.yml
rg "build_neuralweb_health" .github/workflows/daily.yml config/dag.yml config/synapse.yml
rg "build_neuralweb_brief" .github/workflows/daily.yml config/dag.yml config/synapse.yml
```

Post-nightly validation:

```bash
curl -fsS https://mastermind-x.com/neuralwebdata/health.json | jq '.overall_status, .summary_counts'
curl -fsS https://mastermind-x.com/neuralwebdata/daily_brief.json | jq '.status, .did_the_brain_run, .operator_attention[:3]'
curl -fsS https://mastermind-x.com/neuralwebdata/bottom_sensors.json | jq '.as_of, .n_rows'
```

## Risk Register

### Cortex Provider Risk

The model provider can fail for reasons unrelated to code:

- expired OAuth token
- missing Actions secret
- network issue
- SDK/API compatibility issue
- model name drift

Mitigation:

- structured provider attempts
- failover
- degraded status
- no full-publish block
- local mocked tests

### False Green Risk

The worst outcome is a run that appears healthy while the core lobe failed.

Mitigation:

- zero tool calls always degrade cortex
- health derives status from structured fields
- brief repeats the degraded state in operator attention

### Health Artifact Staleness

Health can itself become stale if built too early or not built after all lobes.

Mitigation:

- run health after lobe producers
- register health in synapse
- include health's own `produced_at`
- add health to the daily brief stale checks

### Bottom-Sensor Partial Inputs

Bottom sensors currently tolerate missing Oracle panels. That is acceptable, but
it should be visible.

Mitigation:

- artifact-level gaps
- `fresh_partial` status
- no money-path authority

### Brief Overreach

The daily brief could become a narrative engine that sounds smarter than the
data allows.

Mitigation:

- deterministic v1
- no LLM prose generation
- no trade recommendations
- evidence paths for every claim
- short UI with expanders

## Definition Of "Live"

Neural Web should be considered "live" when these are true after a daily run:

- `health.json` was produced today.
- `daily_brief.json` was produced today.
- every major lobe has a status.
- stale and missing lobes are named.
- bottom sensors are refreshed or explicitly marked stale/partial.
- cortex is either `ok` with real tool calls or `degraded` with provider evidence.
- Committee/Admin can render the answer without running engine code.
- no new trading authority was granted by these surfaces.

In plain English:

Neural Web is live when it can say what it saw today, what failed today, what is
stale today, and what a human should inspect next.

## Final Recommendation

Implement the four lanes exactly in this order:

1. Make cortex status honest.
2. Refresh bottom sensors daily.
3. Build one health artifact.
4. Build one deterministic daily brief.

That is the shortest path from "brainstem plus memory spine" to "awake enough
that the operator can tell what happened today."
