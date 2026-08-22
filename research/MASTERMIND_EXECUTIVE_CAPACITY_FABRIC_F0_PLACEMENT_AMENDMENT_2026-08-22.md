# Executive Capacity Fabric F0 — placement integration amendment

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md`  
**Status:** **SOL SOURCE-LAW CORRECTION / RECORDS ONLY**  
**Mastermind authority checked:** protected `e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`  
**Controlling Executive source law:** `research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md`

This amendment corrects potential integration ambiguities in F0 before acceptance. It does not change the provider-capacity ownership or `mastermind.provider_capacity.v1` contract.

---

## 1. The Phase 1F-C placement snapshot is closed

Accepted Phase 1F-C source law freezes the immutable claim-time placement snapshot as containing **exactly**:

```text
worker_id
quota_class
provider
canonical non-empty account_label
snapshot time
```

The placement JSON/digest pair is sealed transactionally at claim and write-once. The later stable execution-principal snapshot binds `placement_snapshot_digest`; it does not make the placement object extensible.

Therefore Capacity Fabric must **not** add any of the following to `placement_snapshot_json`:

```text
capacity_snapshot_hash
capacity_policy_version
capacity_reason_codes
capability_id
host_ref
quota percentages
cooling state
provider health
```

It must not change the placement snapshot digest definition merely to smuggle those fields into the identity object.

Where the parent F0 architecture says capacity evidence is bound "into the placement snapshot/claim path," interpret it as **alongside the frozen placement snapshot inside the canonical atomic claim receipt path**, never as widening the closed placement object.

---

## 2. Existing canonical seam: `JOB_CLAIMED`

Current Executive runtime already appends `JOB_CLAIMED` in the same claim transaction and uses its payload for selection/routing evidence including:

```text
routing_policy_version
preferred_model_aliases
selected_model_alias
routing_reason_codes
```

Phase 1F-C further requires the claim path to bind the same immutable effective-grant and placement digests through later supervisor/result evidence, but it does not authorize callers to mutate the closed placement identity.

The preferred Capacity Fabric integration is therefore:

```text
provider_capacity.v1 snapshot
       +
Executive/ModelRouter hard eligibility
       +
capacity selection policy
       |
       v
one atomic Executive claim transaction
       |
       +-- frozen placement_snapshot_json/digest (UNCHANGED closed v4 identity)
       |
       +-- JOB_CLAIMED capacity-selection evidence (typed extension)
```

No second placement event, allocation ledger, provider database or lifecycle record should be introduced merely to remember why the claim selected a candidate.

---

## 3. CF2 now has a source-law gate before implementation

CF2 is split conceptually into two gates even if later delivered through one narrowly sequenced program:

### CF2-F — claim-evidence source-law freeze

After Phase 1F-C v4 implementation is accepted, Sol must freeze and independently review the smallest typed extension to the existing `JOB_CLAIMED` receipt that can bind the capacity decision without changing the v4 placement object.

The source-law candidate should prove whether one bounded nested object, conceptually:

```text
capacity_evidence
```

is sufficient. It should be expected to bind at least:

- the exact `mastermind.provider_capacity.v1` semantic snapshot hash used for selection;
- the selected provider-capacity slot identity or a digest of its exact secret-free evidence;
- the deterministic capacity-policy version/hash;
- bounded deterministic selection/rejection reason codes needed for audit;
- enough secret-free observation identity to prove the decision used fresh/reported/estimated/unknown evidence as claimed.

The exact closed payload is **not** frozen by this amendment. It must be reviewed against the landed v4 claim/event code, payload-size law, replay semantics and privacy boundary first.

Preferred properties:

- persisted atomically with the same claim that allocates the Attempt;
- immutable as Event evidence;
- no provider credential/ref value, private host path, email/account PII or provider-native session handle;
- no mutable lookup required to interpret the historical claim;
- duplicate replay reconciles the same evidence;
- changed capacity evidence under the same claim command conflicts rather than silently replacing the receipt.

### CF2-I — implementation

Only after CF2-F passes may code consume `mastermind.provider_capacity.v1` for Executive ranking/exclusion and write the accepted capacity evidence through the claim receipt.

The first CF2-I canary may remain **single-provider / multi-account** on the existing Codex worker route. That is enough to prove the Provider Control → capacity snapshot → deterministic account/worker selection → atomic claim-evidence vertical without changing Model Router semantics.

If the landed v4 runtime proves `JOB_CLAIMED` cannot safely carry the required evidence atomically, **stop and return to Sol**. Do not widen placement snapshot, invent a second Event/ledger, or declare schema v5 by convenience. A new schema/event boundary would require its own explicit ruling.

---

## 4. Host identity remains capacity evidence, not placement identity

F0's `host_ref` remains useful in `mastermind.provider_capacity.v1` because provider capacity is host-bound. It does not become a sixth field in the Phase 1F-C placement snapshot.

Future CF2-F must define the reviewed join from a capacity slot's opaque `host_ref`/`capability_id` to an Executive Worker/quota registration. The actual execution principal and provider-home/OS identity remain proven through the existing Phase 1F-C execution-principal/admission law.

Capacity Fabric may use host information to decide that a worker slot is unavailable or not addressable. It may not claim host/process identity from provider-capacity telemetry.

---

## 5. Historical correction law

Provider capacity changes after claim. Historical Executive evidence must not.

- provider correction -> next `provider_capacity.v1` snapshot changes;
- historical placement snapshot remains unchanged;
- historical `JOB_CLAIMED` capacity evidence remains exactly what the claim used;
- later provider observations do not retroactively make the claim healthy/unhealthy;
- replays use the persisted claim receipt rather than re-running capacity selection against current provider state.

This separation is the reason not to put mutable quota/health fields inside placement identity.

---

## 6. Heterogeneous routing requires provider-neutral equivalence before PF1

Current Mastermind `ModelRouter` is the correct canonical routing plane: deterministic, stateless, side-effect-free, and explicitly separate from lifecycle. F0 does **not** create another router.

However, v1 `ModelAlias` is concrete: every alias binds one `provider_alias`, adapter, model, effort, cost class and capability set. Worker routes then return an **ordered list of concrete model aliases**. Current Executive candidate ranking uses that alias position as a route rank before stable tie-breaks.

That is safe for today's single live worker-provider family, but it creates a hidden future trap:

```text
routine route = [codex.fast, alibaba.fast, grok.fast]
```

would make list/vendor order look like a quality preference even when those aliases are intended to be equally acceptable for the task. Capacity Fabric may not solve this by silently ignoring Model Router order, and Model Router may not solve it by importing quota/cooling state.

Therefore the **first heterogeneous provider may not join an existing shared task route until a separate routing-equivalence source law is accepted.** Call this gate `RF1`.

### RF1 — existing Model Router evolution, not another router

RF1 must preserve Model Router as the sole task/model-suitability owner and choose the smallest reviewed representation for **ordered suitability tiers**. Acceptable candidate shapes include:

1. ordered equivalence tiers containing concrete model aliases; or
2. a provider-neutral execution/quality-class grouping that deterministically resolves to concrete eligible aliases.

The final shape is not frozen by F0. It must be reviewed against the then-current router/runtime tests.

Binding semantics must be:

```text
risk / ambiguity / required capabilities
        |
        v
Model Router ordered suitability tiers
        |
        v
first tier with lawful Executive candidates
        |
        v
Capacity Fabric ranks candidates WITHIN that tier
        |
        v
Executive atomic claim
```

Rules:

- aliases inside one equivalence tier are **equally acceptable on model/task policy**; provider order inside the tier is not a preference signal;
- a lower-quality/lower-suitability tier may not beat an available higher tier merely because it has more quota or lower marginal cost;
- Capacity Fabric never changes risk, ambiguity, required capabilities, review requirements or the chosen suitability tier;
- Model Router contains no live quota, health, cooling, account or host state;
- capacity/cost/reliability chooses only among candidates already admitted by the first non-empty lawful suitability tier;
- route/equivalence policy version/hash and the selected concrete model alias remain receipted in the existing claim path;
- unknown capacity may cause escalation/degraded placement policy, but never semantic promotion of a lower-suitability model;
- tests must prove shuffling aliases within an equivalence tier cannot change a placement solely because of file/order position when capacity evidence is otherwise identical.

### Sequencing consequence

CF2-I may prove capacity-aware account selection with the current Codex route before RF1, because no heterogeneous alias competition exists.

**RF1 is mandatory before PF1**, the first new provider is made eligible for the same Executive task routes as an existing provider. New provider adapter development may occur in isolation before RF1, but it cannot be called integrated heterogeneous routing until RF1 passes.

---

## 7. Non-Codex providers require a provider-neutral harness contract before PF1

Current Mastermind has the correct architectural instinct in `control_plane/worker_adapter.py`: one `WorkerExecutionAdapter` interface is meant to let future Qwen/GLM/xAI/ACP/cloud workers reuse the existing Executive lifecycle rather than create their own queue, lease model or database.

But the current **v1 type boundary is still Codex-owned**:

- `WorkerExecutionAdapter` imports `LaunchSpec`, `ProcessRef`, `CollectionReceipt`, `CancelReceipt` and `ValidationReceipt` from `control_plane.codex_worker`;
- common `LaunchSpec` is documented as a Codex turn and contains a literal `codex_home` field;
- `ProcessRef` and result receipts carry Codex-module `BinaryAttestation`/worker structures;
- the production `executive_worker_broker.py` is explicitly a dedicated Codex worker broker and directly imports/instantiates `CodexWorkerAdapter`;
- existing secret-canary/auth exception language is Codex-specific and must not be falsely generalized to another provider.

Therefore the first non-Codex provider may not be implemented by:

```text
passing an Alibaba/Z.AI/Grok home through `codex_home`
```

or by:

```text
creating executive_alibaba_broker.py + executive_grok_broker.py + ...
```

Both would violate the one-canonical-system law: the former makes a provider-specific contract lie about identity; the latter creates provider-specific lifecycle/control planes.

Call the required gate **HF1 — Harness Contract generalization**.

### HF1 — generalize the existing harness/broker, preserve Codex v1

HF1 must be a separate source-law + bounded implementation wave before PF1. It may proceed in parallel with RF1 after CF2-I when their changed paths are disjoint, but PF1 depends on both.

HF1 must preserve these current truths:

- current Codex adapter behavior, P1B/OHF semantics and accepted live/proof receipts remain valid;
- Executive Job/Attempt/lease/claim lifecycle remains unchanged;
- there is one reviewed worker-broker lifecycle boundary, not one per provider;
- dedicated OS-principal/UID sweep, process identity, cancellation and validation semantics remain centralized where they are provider-neutral;
- provider-native session and auth/home mechanics remain adapter-private;
- provider-specific attestation may be added through explicit typed capability/receipt extensions without weakening the common floor.

The preferred architecture is conceptually:

```text
Executive immutable authorized work handoff
        |
        v
provider-neutral execution request/spec
        |
        v
one reviewed worker broker / adapter resolver
        |
        +--> Codex adapter + Codex-private home/auth mechanics
        +--> supported-coding-tool adapter + provider-private plan endpoint/auth mechanics
        +--> ACP adapter + ACP-private session/transport mechanics
```

The exact common v2 schema is **not frozen here**. HF1 must first separate truly common fields from Codex-specific fields on the landed runtime. Likely common facts include Job/worker/run identity, workspace/run directory, immutable grant/authority, model/execution selection, timeout/cancel bounds, artifact/validation limits, expected base, isolation evidence and supervisor-required process receipts. A generic contract must not include a field whose name or semantics assumes Codex.

Provider-private configuration should be referenced through a reviewed adapter registration/config boundary. It may include a dedicated provider home or endpoint reference where needed, but raw token/key/cookie bytes remain outside model-visible handoffs and Executive persisted payloads.

The broker must resolve an immutable reviewed adapter identity; the model/caller may not select arbitrary executable/provider commands. An unimplemented or unapproved adapter remains fail-closed exactly as v1 `ADAPTER_DESCRIPTORS` intends.

### HF1 acceptance requirements

At minimum, HF1 must prove:

1. current Codex golden paths/receipts remain byte/behavior compatible where source law requires it;
2. one synthetic non-Codex fake adapter can traverse the **same** broker/supervisor start/status/collect/cancel/validate lifecycle without any provider-specific broker or second queue/state store;
3. common request/receipt types contain no `codex_*`-named field and no vendor-secret value;
4. adapter-private provider home/auth/session details cannot leak into prompts, generic logs, Executive events or cross-provider config;
5. peer authorization, dedicated-principal/process cleanup, cancellation, timeout, validation and replay behavior do not weaken for the new adapter seam;
6. unknown/unimplemented adapter IDs refuse before provider contact;
7. the adapter identity/provider relationship is immutable and receipted so a job cannot begin on one adapter and be collected as another;
8. HF1 introduces zero autonomous provider failover/retry. A provider failure returns through normal Executive Attempt semantics;
9. Phase 1F-C placement/execution-principal evidence remains valid; if a required HF1 change would alter a frozen P1B/1F-C evidence schema, HF1 stops for an explicit source-law amendment instead of silently widening it.

### Sequencing consequence

Provider adapter research/fixtures may happen before HF1, but **no non-Codex provider can be called an Executive worker vertical until HF1 passes**. Alibaba/Z.AI should share the supported-coding-tool harness family where lawful; Grok/Cursor should share an ACP family where lawful. Provider-specific execution mechanics live behind those reviewed adapters, not in Executive lifecycle.

---

## 8. Revised sequence

```text
F0     provider-capacity ownership + contract freeze
CF1    Macro provider_capacity.v1 producer + real no-write consumer
OF1    accepted Phase 1F-C v4 implementation
CF2-F  Executive claim-evidence source-law freeze against landed v4
CF2-I  existing-provider capacity-aware placement using the accepted claim receipt seam
RF1    provider-neutral Model Router suitability/equivalence freeze + implementation
HF1    provider-neutral worker-harness/broker contract freeze + implementation
PF1+   one new provider/harness vertical per PR; shared-route admission requires RF1 + HF1
OF2    real heterogeneous Fable fan-out / exhaustion / review / repair / aggregation proof
```

RF1 and HF1 may run in parallel after their shared upstream gates only when their exact source/code paths are disjoint. PF1 depends on **both**.

This amendment supersedes any reading of F0 that would put Capacity Fabric fields directly into `placement_snapshot_json`, claim that CF2 implementation can begin immediately after v4 without a fresh claim-evidence source-law review, use concrete model-alias list order as an accidental cross-provider scheduler, disguise a new provider behind Codex-specific common types, or create one Executive broker/lifecycle per vendor.
