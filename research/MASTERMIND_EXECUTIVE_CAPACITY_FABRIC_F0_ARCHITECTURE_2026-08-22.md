# Mastermind-X Executive Capacity Fabric F0

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Status:** **SOL ARCHITECTURE FREEZE CANDIDATE / RECORDS ONLY**  
**Semantic parent:** `shared-ai-provider-control`  
**Organizational workstream:** `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Current Macro pickup:** `21f51a1ecfed778a738b048bd7e5efd30b1d9336`  
**Current protected Mastermind reviewed:** `0f319c79a7b3373a96d4866412c734de12cbf701`  
**Protected Sol Skillpack:** `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`, loaded atomically from that Mastermind commit.  
**Completion:** merge-is-done for this records-only freeze only. It does not build the capacity projection, change Executive placement, add a provider, mutate credentials, or arm production.

---

## 0. Executive ruling

Mastermind-X already has the beginnings of a real heterogeneous AI workforce, but the pieces answer different questions and must remain separate:

```text
Shared AI Provider Control
    = what provider/account capacity exists and what is known about it?

Mastermind Model Router
    = what model / execution classes are acceptable for this task?

Executive OS
    = which already-eligible Worker receives this Job Attempt?

Worker harness / OHF / CLI / ACP
    = how is the selected provider-native session actually executed?

Agent OS / Control Room
    = how is the durable organization recorded and projected?
```

The missing capability is **not** another provider database. It is a truthful, versioned bridge from the operating Shared AI Provider Control Plane into future Executive placement.

F0 therefore freezes:

1. one canonical provider-capacity ownership law;
2. one secret-free normalized contract, `mastermind.provider_capacity.v1`;
3. evidence, freshness, null and correction semantics that do not invent quota;
4. a future deterministic placement relationship that cannot bypass Model Router, Executive authority or independent-review law;
5. a bounded CF1 implementation wave that proves the contract on the providers already present in Macro before any new vendor is added.

---

## 1. Chairman / user outcome

### Chairman job

Give Mastermind-X a mission once. Do not manually decide which AI subscription/account should run each child task, watch five-hour and weekly quota bars, switch models after provider exhaustion, keep track of which Mac owns which login, or copy state among sessions.

### Sol / Fable job

Decompose by outcome and ambiguity, not by vendor. Commission independently useful child work with explicit quality/authority/independence requirements. Let deterministic machinery select among suitable available workers while preserving enough frontier capacity for high-value interactive and critical work.

### Machine job

Observe provider capacity without exposing credentials; preserve the difference between presence, health, quota evidence and execution state; choose only among Executive-eligible workers; record why a worker was selected; cool or deprioritize capacity when evidence justifies it; and never create duplicate execution merely because another provider appears available.

### 10/10 end-state

A real Sol mission is admitted once. Fable decomposes it. Different useful child Jobs can land on Codex, Claude, Alibaba/Z.AI, ACP workers, metered APIs or local models according to current task suitability, authority, independence, cost and capacity. One provider reaches a five-hour or weekly boundary and becomes unavailable for later work without terminating already-canonical lifecycle truth. Another eligible capacity slot can take a later safe Job. Independent review and bounded repair remain Executive lineage. The Control Room can explain current capacity and placement receipts, but does not own either. The Chairman watches the organization, not provider dashboards.

---

## 2. Current capability ledger

| Capability | State | Current truth |
|---|---|---|
| Semantic provider-capacity owner | `PROVEN_LIVE` | Macro `shared-ai-provider-control` is operating and explicitly owns provider availability/capacity coordination plus shared auth-pool/cooling semantics |
| Claude multi-key identities and cooling | `PROVEN_LIVE` for existing Macro reasoning paths | `engine/neuralweb/key_pool.py` carries capability IDs, presence, local usage ledger, cooling/reset and safe header evidence |
| Multiple attached Codex account identities | `BUILT_NOT_PROVEN` as Executive workforce capacity | `CODEX_ACCOUNT_HOMES` plus stable `codex_account[_N]` identities exist; current host population is not asserted by F0 |
| Provider-reported / estimated / 429-derived budget evidence | `PROVEN_LIVE` inside current Macro budget control | `engine/metabolism/budget_gate.py` distinguishes reported, estimate, 429-window and unknown readings |
| Safe provider health/outcome classification | `BUILT_NOT_PROVEN` as Capacity Fabric input | Existing provider health/waterfall logic exists, but no normalized cross-provider capacity projection consumes it yet |
| Cross-repo provider-capacity bridge to Portfolio | `PROVEN_LIVE` for existing reasoning integration | Existing Macro↔Portfolio bridge is documented; floating implementation coupling remains a hardening issue |
| `mastermind.provider_capacity.v1` | `NOT_BUILT` | F0 freezes it here |
| Executive capacity-aware placement | `NOT_BUILT` | Current Executive routing is not connected to Shared Provider Control capacity evidence |
| Phase 1F-C schema-v4 orchestration | `SPEC_ONLY` / accepted source law | Source law is reviewed; implementation/live proof remain separate |
| Z.AI / Alibaba coding-plan Executive workers | `NOT_BUILT` | Design target only in F0 |
| Grok / Cursor ACP Executive workers | `NOT_BUILT` | Design target only in F0 |
| OpenRouter overflow worker | `NOT_BUILT` | Design target only in F0 |
| Control Room capacity/workforce projection | `NOT_BUILT` | Must consume accepted truth later; it is not part of CF1 |

The distinction above is intentional. Existing provider infrastructure may be proven useful in Macro while still being unconnected to Executive worker placement.

---

## 3. Canonical ownership and no-rebuild law

### Shared AI Provider Control — Macro

Owns:

- provider/capability discovery;
- secret-reference policy and provider-auth pool identity;
- account-slot presence and enablement;
- provider cooling/reset semantics;
- provider quota/budget observations and evidence classification;
- safe provider health/outcome observations;
- corrections to those operational observations.

Does not own:

- Job admission;
- Worker eligibility or authority;
- Executive lifecycle;
- task/model suitability;
- review independence;
- company strategy or market authority.

### Model Router — Mastermind

Owns deterministic task/risk/ambiguity → acceptable model/execution-class policy. It is not a quota store and must not become one.

### Executive OS — Mastermind

Owns Job/Attempt/Worker/Event lifecycle and the final claim/placement decision among workers already lawful under Executive constraints. It owns immutable evidence of the capacity snapshot/reasons used for one claim, not the provider truth itself.

### Worker harness

Owns provider-native start/resume/cancel/result mechanics inside reviewed authority. A provider-native session is not a Job and a provider account is not a Worker lifecycle authority.

### Agent OS / Linear / Slack / Control Room

Agent OS records the organizational workstream/decisions/discoveries/handoffs. Linear projects selected portfolio state. Slack transports dialogue. Control Room later projects workforce/capacity state. None may become provider-capacity or lifecycle authority.

### No-rebuild boundary

F0 explicitly rejects:

- an Executive `ProviderAccount` database;
- an Executive `QuotaHorizon` or second cooling ledger;
- a second provider/account identity registry;
- live quota embedded in Model Router policy;
- provider-specific placement schedulers;
- a cross-repo contract implemented as unversioned floating Python imports;
- a hidden retry/failover plane;
- a host/session registry invented for capacity convenience.

Phase 1F-C owns Executive schema v4. Capacity Fabric must not create a temporary v3 placement schema or another v4 migration.

---

## 4. Contract freeze — `mastermind.provider_capacity.v1`

The projection is a **deterministic, secret-free snapshot** of what Shared Provider Control currently knows. It is not an account database, allocation promise or provider entitlement claim.

### 4.1 Canonical top-level object

Closed F0 shape:

```json
{
  "schema": "mastermind.provider_capacity.v1",
  "generated_at": "2026-08-22T22:00:00Z",
  "producer": {
    "repository": "mastermindx-market-intelligence/macro",
    "commit": "<40-hex>",
    "program": "shared-ai-provider-control",
    "implementation_id": "provider-capacity-v1"
  },
  "snapshot_hash": "<64-lower-hex>",
  "slots": [],
  "degraded": []
}
```

No extra keys are accepted by a strict consumer.

### 4.2 Slot identity

Each slot is one executable capacity identity known to the producer, not one Job or live session.

Required slot fields:

```json
{
  "capability_id": "codex_account_2",
  "provider": "codex",
  "account_label": "codex_account_2",
  "host_ref": "host-<opaque-reviewed-id>",
  "billing_mode": "subscription",
  "credential_kind": "attached_login",
  "execution_surface": "native_cli",
  "present": true,
  "enabled": true,
  "health": {},
  "cooling": {},
  "quota_horizons": [],
  "last_outcome": {}
}
```

Identity laws:

- `capability_id` comes from canonical provider-control identity, e.g. existing Claude/Codex capability IDs. Do not create a second numbering scheme.
- `account_label` is an opaque, non-PII operational label. F0 permits it to equal `capability_id`. Email, billing name, provider account ID, username or token-derived fingerprint are forbidden.
- `host_ref` is an opaque reviewed company-local capacity-host label. It must not expose hostname, IP, serial number, home directory or username. Capacity on two Macs is not assumed interchangeable merely because the provider/account label matches.
- a slot without a configured/reviewed `host_ref` may be projected for diagnostics with a reserved value such as `local-unbound`, but future automatic multi-host placement must treat it as not remotely addressable until host identity/transport law exists.
- duplicate `(host_ref, capability_id)` in one snapshot refuses the projection.

### 4.3 Closed classification vocabularies

`billing_mode`:

```text
subscription | metered_api | credits | local
```

`credential_kind` is descriptive only:

```text
oauth | attached_login | plan_api_key | api_key | local
```

It never carries the credential value or provider auth bytes. Secret-ref names should also be omitted from the consumer projection unless a later reviewed operational need proves they are necessary.

`execution_surface`:

```text
native_cli | supported_tool | acp | api | local
```

This describes how a reviewed Worker adapter reaches the capacity; it does not select the adapter or grant execution authority.

### 4.4 Health

Closed shape:

```json
{
  "state": "available",
  "error_class": null,
  "observed_at": "2026-08-22T22:00:00Z"
}
```

`state`:

```text
available | degraded | unavailable | unknown
```

`error_class`:

```text
null | auth | usage_limit | timeout | not_installed | unsupported | transport | error
```

Presence is not health. `present=true` means the local capability presence condition is satisfied; it is not proof a current provider call would authenticate or succeed. `present=false` also says nothing about another host.

No raw exception, stderr, request, provider response body, file path or credential-shaped value may enter this object.

### 4.5 Cooling

Closed shape:

```json
{
  "active": false,
  "kind": null,
  "reset_at": null,
  "evidence": "unknown",
  "observed_at": null
}
```

`kind`:

```text
null | window | weekly | monthly | concurrency | auth | provider | unknown
```

`evidence`:

```text
exact | provider_reported | estimated | unknown
```

A local policy timer derived from a reported provider reset remains `provider_reported`, not magically `exact`. An operationally imposed deterministic cooldown may be `exact` only for the locally imposed cooldown itself; it must not claim the provider entitlement reset is exact unless independently known.

### 4.6 Quota horizons

`quota_horizons` is an ordered array. Every horizon is independently nullable and independently evidenced.

Closed shape:

```json
{
  "horizon": "five_hour",
  "metric": "provider_allocation",
  "window_type": "rolling",
  "duration_seconds": 18000,
  "limit": null,
  "used": null,
  "remaining": null,
  "used_percent": 57.0,
  "reset_at": "2026-08-22T23:41:00Z",
  "observed_at": "2026-08-22T22:00:00Z",
  "stale_after": "2026-08-22T22:10:00Z",
  "evidence": "provider_reported",
  "source_kind": "provider_api",
  "freshness": "fresh"
}
```

`horizon`:

```text
five_hour | weekly | monthly | billing_cycle | credits | concurrency | custom
```

`metric`:

```text
provider_allocation | requests | tokens | credits | currency | concurrent_sessions | custom
```

`window_type`:

```text
rolling | fixed | billing_cycle | instant | unknown
```

`evidence`:

```text
exact | provider_reported | estimated | unknown
```

`source_kind`:

```text
provider_api | response_headers | local_ledger | config | error_signal | unknown
```

`freshness`:

```text
fresh | stale | unknown
```

Numeric fields accept finite non-negative JSON numbers or `null`. `used_percent` may not be inferred from `used` without a known positive `limit`, and `remaining` may not be inferred from a percentage without a known `limit`.

### 4.7 Last outcome

Closed shape:

```json
{
  "class": "success",
  "observed_at": "2026-08-22T22:00:00Z"
}
```

`class`:

```text
success | auth | usage_limit | timeout | not_installed | unsupported | transport | error | unknown
```

This is descriptive reliability evidence only. It is not a Job/Attempt result.

### 4.8 Degraded rows

Top-level `degraded` uses structured, safe bounded rows rather than raw strings:

```json
{
  "code": "PROVIDER_BUDGET_UNKNOWN",
  "scope": "codex_account_2",
  "observed_at": "2026-08-22T22:00:00Z"
}
```

The F0 implementation may freeze a closed code vocabulary during CF1. Raw exception text, headers outside the safe allowlist, private paths, auth details and provider response bodies are forbidden.

---

## 5. Canonicalization and snapshot identity

The projection uses UTF-8 JSON with:

```text
sort_keys = true
separators = (",", ":")
ensure_ascii = false
NaN / Infinity = rejected
```

`slots` sort deterministically by `(host_ref, provider, capability_id)`. `quota_horizons` sort by a frozen deterministic horizon/metric key. `degraded` sorts by `(code, scope, observed_at)` or a narrower frozen equivalent.

`snapshot_hash` is lowercase SHA-256 over the complete canonical semantic top-level document excluding **only** top-level `generated_at` and `snapshot_hash`.

The producer commit and all slot observations/timestamps/evidence remain semantic. Two snapshots generated at different wall-clock times from byte-identical source evidence therefore share the same semantic hash; changing a provider observation, source timestamp, host/capability identity or producer implementation revision changes the hash.

---

## 6. Time, null, evidence and correction law

### No false zeros

The current Macro admin snapshot may emit numeric zero when no local ledger row contributed to an aggregate. Capacity Fabric may not automatically reinterpret such a display zero as observed unused quota.

Rules:

- no observation => `null` plus `evidence=unknown`;
- an actual observed zero may be represented as `0` only when its source/evidence proves it;
- an estimated zero requires an estimator with a configured real budget and a valid observation base;
- `unknown` is never converted to unlimited/free capacity.

### Reported versus estimated

Provider-reported API/header evidence outranks local estimation for the same horizon when it is fresh and structurally valid. Local estimate remains useful for a horizon with no reported reading, but it stays `estimated`.

A provider 429 classified as a five-hour-window limit is a real provider error signal and may represent `used_percent=100` for the relevant horizon with `evidence=provider_reported`, `source_kind=error_signal` and the applicable reset hint. It must not fill unrelated weekly/monthly horizons.

### Freshness

Every dynamic observation carries `observed_at`; every horizon may carry `stale_after` when a reviewed source-specific freshness budget exists.

- before the accepted freshness deadline: `fresh`;
- after it: `stale`;
- no usable observation/freshness basis: `unknown`.

Stale evidence remains displayable. It must never be relabeled fresh because a wrapper was regenerated.

### Corrections

Provider capacity is mutable operational truth. Corrections generate a new projection/snapshot. They never rewrite an immutable Executive placement snapshot from a historical Attempt.

If a provider result reveals auth failure, usage limit, cooling or transport degradation, the reviewed adapter/provider-control path records that observation for future placement. Executive OS first reconciles the current Attempt/effect state. Capacity feedback does not authorize an immediate second provider call or duplicate Job.

---

## 7. Future Executive placement law — CF2 boundary

CF2 is not implemented in F0/CF1. The relationship is frozen now so CF1 does not accidentally become a scheduler.

Conceptual deterministic sequence:

```text
Job + authority / grant / independence requirements
          |
          v
Executive hard eligibility filters
          |
          v
Model Router acceptable model/execution classes
          |
          v
registered worker/quota/provider/account eligibility
          |
          v
Capacity Fabric snapshot ranking of the remaining candidates
          |
          v
Executive atomic claim + immutable placement snapshot
```

Capacity may **rank or exclude only candidates that are already lawful**.

Hard facts that may exclude/deprioritize under reviewed policy:

- provider/capability disabled;
- `present=false` on the required host;
- fresh health `unavailable`;
- active fresh cooling for the required slot;
- fresh known quota exhaustion;
- missing required host binding;
- Executive independence or route/capability requirement not satisfied.

Unknown/stale quota must not look like free capacity. Policy may either:

- allow the candidate with an explicit unknown/stale penalty; or
- require fresh known capacity for a class of work and refuse/escalate when it is absent.

That choice is deterministic policy, not model judgment.

For otherwise equivalent eligible work, later policy may prefer:

1. capacity that satisfies independence and required model class;
2. healthy fresh subscription/local capacity before marginal metered API spend for routine work;
3. configurable reserves for scarce frontier/interactive/critical capacity;
4. greater known headroom where genuinely comparable;
5. recent provider reliability;
6. stable deterministic tie-break.

Do not compare unlike provider percentages as if 20% of every plan has the same economic or quality value. A capacity percentage is one operational dimension, not a universal score.

The future Executive placement receipt should bind at minimum the exact capacity snapshot digest/policy version and deterministic reason codes into the **already accepted Phase 1F-C placement snapshot/claim path**. Do not add another placement ledger or another schema-v4 migration.

No LLM chooses placement, waives independence, interprets unknown quota or authorizes failover.

---

## 8. Host and multi-machine law

Mastermind-X is moving toward multiple Macs/hosts. F0 does not build multi-host execution, but the contract must not make it impossible.

- Provider/account capacity is observed **on a host**.
- `host_ref` is opaque and non-sensitive.
- A Codex login present on Mac A is not assumed callable on Mac B.
- A subscription key available in GitHub Actions is not automatically the same execution surface as a local attached-login slot.
- Future host admission/worker registration must own whether a host can execute a Job; Capacity Fabric only reports the slot relationship.
- No SSH inventory, machine-management database or process-liveness registry is introduced in CF1.

---

## 9. Provider expansion architecture — design target only

After the existing-provider contract and Executive placement vertical prove useful, new providers join by implementing the existing ownership/harness boundaries.

### Existing first vertical

CF1/CF2 prove with current Codex subscription, Claude OAuth and DeepSeek/API sources already in Shared Provider Control. No new vendor is required to validate the architecture.

### Coding-plan family

Z.AI Coding Plan and Alibaba Coding Plan are first-class subscription capacity. Preferred architecture is an accepted coding-agent harness configured to the provider's supported endpoint/tool contract, not a special raw-HTTP scheduler fork.

### Claude Code family

A reviewed Claude Code worker adapter may support native Anthropic and compatible coding-plan endpoints where vendor contracts allow. Provider identity and billing mode remain explicit even if the execution harness family is shared.

### ACP family

Grok/Cursor or other agents exposing reviewed ACP semantics should share one ACP-capable harness family where possible. Provider-native resumable session IDs stay harness-local/secret-safe and do not become Executive lifecycle identity.

### OpenRouter / metered APIs

OpenRouter belongs in metered overflow/specialist capacity when its quality/cost policy justifies it. API spend does not outrank available subscription capacity merely because telemetry is easier to measure.

### Local

Local models later join as `billing_mode=local`, with honest machine/concurrency/resource evidence when a reviewed source exists. F0 does not pretend CPU/GPU availability is already modeled.

One real bounded Executive child Job through the real adapter is required before any new provider becomes `PROVEN_LIVE`.

---

## 10. Failure matrix

| Condition | Capacity projection / future placement behavior |
|---|---|
| provider capability absent on host | project `present=false`; no inferred auth failure |
| capability present but no health call | health `unknown`; no invented healthy state |
| no quota observation | null metrics + `evidence=unknown` |
| display ledger aggregate happens to be zero without source observation | remain unknown; do not claim 0 used |
| fresh reported percentage but absolute plan limit unknown | expose percentage only; `limit/used/remaining=null` |
| estimate configured and reported reading absent | expose estimate with `evidence=estimated` |
| fresh provider-reported reading and estimate both exist | reported wins for that horizon; estimate may not overwrite it |
| five-hour 429 | five-hour horizon may show 100% / cooling from error signal; unrelated horizons remain unchanged |
| stale reading | expose `freshness=stale`; never silently refresh timestamp |
| malformed or unknown ratelimit header | ignore/refuse that reading; do not parser-repair into capacity |
| duplicate `(host_ref, capability_id)` | projection refuses / explicit degradation; no arbitrary winner |
| host identity unavailable | diagnostics allowed under unbound host; future remote placement refuses |
| secret-like value reaches projection candidate | refuse/redact before output; test fails |
| provider error after Attempt started | update future capacity through owning provider path; reconcile Executive Attempt before any next call |
| Capacity projection unavailable | Executive may use only a separately reviewed degraded policy; must not pretend unlimited capacity |
| Model Router and capacity disagree | suitability/authority hard filters win; capacity cannot widen eligibility |
| independence requires a different worker/account/host and none exists | typed exhaustion/escalation; no self-review waiver |
| provider reset/correction arrives later | new projection only; historical placement evidence unchanged |

---

## 11. Ordered program waves

```text
F0   architecture + work identity + contract freeze
 |
CF1  existing provider state -> provider_capacity.v1 -> real no-write consumer
 |
OF1  separately accepted Phase 1F-C implementation owns Executive schema v4
 |
CF2  Executive capacity-aware placement consumes provider_capacity.v1 in v4 claim path
 |
PF1+ one real provider/harness vertical per PR
 |
OF2  heterogeneous Fable fan-out + quota exhaustion + independent review + repair + aggregate
 |
ASD / Wake / Control Room projection integrate only after their own proof gates
```

CF1 and Phase 1F-C implementation may proceed independently because CF1 changes no Executive schema/runtime.

---

## 12. CF1 operator commission — existing-provider capacity projection

**Executable only after F0 is accepted and merged. F0 merge itself does not start CF1.**

### Observable mission

After CF1, one deterministic no-write Macro command produces a strict `mastermind.provider_capacity.v1` snapshot from the provider-control state that already exists, and one real operator/machine consumer can read it without learning credentials or mistaking unknown quota for free capacity.

### Why it matters

Executive placement cannot safely become quota-aware until provider truth has one normalized, versioned, correction-safe boundary. CF1 creates an independently useful visibility/machine contract without touching Executive lifecycle or adding vendors.

### Authority / document precedence

At pickup, re-read in order:

1. explicit current Chairman/Sol commission;
2. accepted F0 decision/workstream/research record;
3. current protected Sol Skillpack;
4. current Macro `config/mastermind_programs.yml` `shared-ai-provider-control` ownership;
5. current `engine/neuralweb/key_pool.py`, `engine/metabolism/budget_gate.py`, `engine/llm_auth.py`, `engine/provider_health.py`, `engine/codex_provider.py`, `config/capability_manifest.yml`;
6. current cross-repo contract audit;
7. current Mastermind Phase 1F-C source law for non-collision only.

If a newer accepted source changes ownership or a concurrent PR modifies the same provider-control semantics, stop and return to Sol rather than inventing a reconciliation.

### Verified current state at F0 freeze

Macro F0 pickup is `21f51a1ecfed778a738b048bd7e5efd30b1d9336`.

Current substrate includes:

- Claude capability pool identities and local cooling/usage/header evidence;
- multiple isolated Codex account homes/capability IDs;
- DeepSeek capability presence;
- reported-first/estimated/429/unknown budget behavior;
- safe provider outcome/error classes;
- capability manifest secret-reference redline;
- an existing admin metabolism/key-pool consumer.

`mastermind.provider_capacity.v1` does not exist yet. Executive placement does not consume it.

### Exact scope / repository

Primary and only implementation repo: `mastermindx-market-intelligence/macro`.

Preferred additive paths after builder archaeology:

```text
engine/provider_capacity.py
scripts/build_provider_capacity.py
focused tests / fixtures
```

A minimal existing operator/admin consumer may be extended if it can consume the same contract cleanly without widening UI scope. A CLI/no-write JSON stdout consumer is sufficient for CF1 if it is a real machine/operator path.

Do not modify Mastermind runtime or schema.

### Explicit non-goals

No:

- new provider;
- Z.AI/Alibaba/Grok/Cursor/OpenRouter/local worker;
- Executive placement or schema change;
- network probe requirement added merely for CF1;
- auth login, token/key mutation or provider credential read;
- persistent provider-capacity database or generated state authority;
- Control Room capacity UI;
- Wake/Slack/dispatch changes;
- provider-source behavior rewrite unless a real source defect is independently returned to Sol;
- routing/model policy redesign.

### Complete user / machine journey

1. Operator/machine invokes the no-write capacity producer.
2. Producer reads existing provider-control sources only.
3. Every capability slot is normalized with source/evidence/freshness law.
4. Unknown/missing evidence remains null/unknown rather than zero/unlimited.
5. Canonical ordering and `snapshot_hash` are computed.
6. JSON is emitted to stdout / returned to the real consumer.
7. No credential/auth bytes appear and no provider or canonical store is mutated.
8. A second invocation with unchanged source evidence produces the same semantic snapshot hash despite a different `generated_at`.
9. Corrupt/unsupported source evidence degrades/refuses honestly without fabricating a healthy slot.

### Data / time / null / correction behavior

Implement exactly the F0 contract. `generated_at` is display time and excluded from the semantic snapshot hash. Source observation times remain semantic. No dynamic observation may be made newer merely by projection. No absolute remaining quota is derived from a percentage without a known limit. Corrections appear on the next projection; CF1 stores no corrective shadow truth.

### Deterministic vs statistical vs model-generated method

CF1 is **100% deterministic**.

No model call, sentiment, LLM parser or statistical imputation is permitted. Existing configured token-budget estimates may be represented only as `evidence=estimated`; CF1 does not invent a new estimator.

### Failure states

Test and expose at least:

- absent capability;
- disabled capability;
- provider health unknown;
- no quota observation;
- display-zero/no-ledger ambiguity;
- reported reading;
- estimated fallback;
- 429-window evidence;
- stale evidence;
- malformed/unknown header;
- duplicate slot identity;
- unbound host identity;
- corrupt local ledger row;
- missing optional source;
- secret-shaped value contamination;
- invalid canonical JSON / NaN;
- non-deterministic ordering/hash drift.

### Ordered implementation sequence

1. Re-read current ownership and collision state.
2. Freeze executable schema validators/canonicalization/golden vectors first.
3. Implement source adapters over existing provider-control public/semi-public APIs without copying provider policy.
4. Implement strict normalization/evidence/freshness rules.
5. Implement canonical sort/hash.
6. Implement no-write JSON stdout/operator consumer.
7. Add source-specific fixtures for current Claude/Codex/DeepSeek states.
8. Add secret-redline/static no-write tests.
9. Run focused tests and full exact-head Macro CI/fences.
10. Obtain independent adversarial review.
11. Open one HOLD-FOR-SOL PR and stop.

### Acceptance tests and real proof

Required discriminators:

- provider-reported reading outranks estimate for the same horizon;
- no observation + current `usage_snapshot` numeric zero remains unknown rather than zero-used capacity;
- configured estimator is labeled estimated;
- 429 window affects only its horizon;
- stale source never becomes fresh on rerender;
- multiple Claude/Codex slots keep stable identity/order;
- absent/disabled/cooling fields remain distinct;
- host_ref is opaque and deterministic;
- duplicate slot identity refuses;
- percentage without absolute limit never creates remaining count;
- canonical hash changes on semantic source/producer change but not `generated_at` alone;
- output contains no token/key/cookie/auth file content, private path, email/account PII or secret-ref value;
- producer causes zero canonical source writes and zero provider calls if CF1 is specified as local-state-only;
- real current Macro provider state can be projected successfully through the real CLI/consumer.

Real proof packet must include exact source/base/head SHAs, semantic snapshot hash, safely summarized slot/evidence census, before/after no-write receipt, secret scan, focused/full CI/fences and independent review. Do not paste credentials or raw sensitive provider state into the PR.

### Stop condition

Stop with one held CF1 PR after the current-provider projection and real consumer are complete. Do not begin Executive placement, add any provider, change schema v4, or start heterogeneous orchestration.

### Continuation handoff

Return to Sol:

- pickup/base/head SHAs;
- changed-file/import census;
- exact contract/golden-vector digest;
- current real slot/evidence census in secret-safe form;
- focused/full CI/fences;
- no-write/secret-redline receipts;
- adversarial findings and repairs;
- every discovered upstream provider-control defect;
- confirmation CF2/provider expansion remains unstarted;
- exact next action.

---

## 13. F0 acceptance

F0 may merge only when:

- changed files are exactly the intended records-only architecture/workstream/decision set;
- `WS:EXECUTIVE-CAPACITY-FABRIC` validates under Agent OS law;
- the semantic parent remains current `shared-ai-provider-control`;
- current Macro/Mastermind collision review remains clean;
- no provider/runtime/config/credential/Linear/Slack state is changed;
- current exact-head CI/fences are green;
- Sol accepts the architecture and CF1 commission.

F0 merge accepts architecture only. It does not build CF1, does not start an implementation session, does not make Executive placement quota-aware and does not make any new provider live.
