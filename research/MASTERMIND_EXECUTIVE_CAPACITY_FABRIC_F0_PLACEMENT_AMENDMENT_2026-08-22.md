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

### CF2-F — claim-evidence source-law freeze

After Phase 1F-C v4 implementation is accepted, Sol must freeze and independently review the smallest typed extension to the existing `JOB_CLAIMED` receipt that can bind the capacity decision without changing the v4 placement object.

The source-law candidate should prove whether one bounded nested object, conceptually `capacity_evidence`, is sufficient. It should be expected to bind at least:

- the exact `mastermind.provider_capacity.v1` semantic snapshot hash used for selection;
- the selected provider-capacity slot identity or a digest of its exact secret-free evidence;
- the deterministic capacity-policy version/hash;
- bounded deterministic selection/rejection reason codes needed for audit;
- enough secret-free observation identity to prove the decision used fresh/reported/estimated/unknown evidence as claimed.

The exact closed payload is **not** frozen by this amendment. It must be reviewed against the landed v4 claim/event code, payload-size law, replay semantics and privacy boundary first.

Preferred properties: atomic with the same claim; immutable Event evidence; no provider credential/ref value, private host path, email/account PII or provider-native session handle; no mutable lookup needed to interpret history; duplicate replay reconciles the same evidence; changed evidence under the same claim command conflicts.

### CF2-I — implementation

Only after CF2-F passes may code consume `mastermind.provider_capacity.v1` for Executive ranking/exclusion and write the accepted capacity evidence through the claim receipt.

The first CF2-I canary may remain **single-provider / multi-account** on the existing Codex worker route. That proves Provider Control → capacity snapshot → deterministic account/worker selection → atomic claim-evidence without heterogeneous router/harness changes.

If landed v4 proves `JOB_CLAIMED` cannot safely carry the required evidence atomically, **stop and return to Sol**. Do not widen placement snapshot, invent a second Event/ledger, or declare schema v5 by convenience.

---

## 4. Host identity remains capacity evidence, not placement identity

F0's `host_ref` is useful because provider capacity is host-bound. It does not become a sixth field in Phase 1F-C placement snapshot.

Future CF2-F must define the reviewed join from a capacity slot's opaque `host_ref`/`capability_id` to an Executive Worker/quota registration. Actual execution principal and provider-home/OS identity remain proven through existing Phase 1F-C execution-principal/admission law.

Capacity Fabric may use host information to decide a slot is unavailable or not addressable. It may not claim host/process identity from provider-capacity telemetry.

---

## 5. Historical correction law

Provider capacity changes after claim; historical Executive evidence must not.

- provider correction -> next `provider_capacity.v1` snapshot changes;
- historical placement snapshot remains unchanged;
- historical `JOB_CLAIMED` capacity evidence remains exactly what the claim used;
- later provider observations do not retroactively make the claim healthy/unhealthy;
- replays use persisted claim evidence rather than re-running selection against current provider state.

---

## 6. Heterogeneous routing requires provider-neutral equivalence before PF1

Current Mastermind `ModelRouter` is the correct canonical routing plane: deterministic, stateless, side-effect-free, and separate from lifecycle. F0 does **not** create another router.

But v1 `ModelAlias` is concrete: every alias binds one provider/adapter/model/effort/cost/capability set, and worker routes return an **ordered list of concrete aliases**. Executive candidate ranking uses alias position before stable tie-breaks.

That is safe for today's one live provider family, but a future route such as `[codex.fast, alibaba.fast, grok.fast]` would make vendor/list order look like quality preference even when aliases are intended equally acceptable.

Therefore the first heterogeneous provider may not join a shared task route until **RF1 — routing equivalence** passes.

### RF1 — evolve the existing Model Router, not another router

RF1 must choose the smallest reviewed representation for ordered suitability tiers: either ordered equivalence tiers of concrete aliases or a provider-neutral execution/quality class that resolves deterministically to concrete eligible aliases.

Binding semantics:

```text
risk / ambiguity / required capabilities
        -> Model Router ordered suitability tiers
        -> first tier with lawful Executive candidates
        -> Capacity Fabric ranks candidates WITHIN that tier
        -> Executive atomic claim
```

Rules:

- aliases inside one equivalence tier are equally acceptable on model/task policy; provider order inside the tier is not preference;
- a lower-suitability tier may not beat an available higher tier because it has more quota or lower cost;
- Capacity Fabric never changes risk, ambiguity, required capabilities, review requirements or chosen tier;
- Model Router contains no live quota, health, cooling, account or host state;
- capacity/cost/reliability chooses only among candidates already admitted by the first non-empty lawful tier;
- route/equivalence policy version/hash and selected concrete alias remain receipted in the existing claim path;
- tests prove shuffling aliases within an equivalence tier cannot alter placement merely due file/order position.

CF2-I may prove capacity-aware Codex account selection before RF1 because no heterogeneous alias competition exists. **RF1 is mandatory before PF1 shared-route admission.**

---

## 7. Non-Codex providers require a provider-neutral harness contract before PF1

Current `control_plane/worker_adapter.py` has the correct architectural intent: one `WorkerExecutionAdapter` interface lets future providers reuse Executive lifecycle rather than create their own queue/lease/database.

But the current v1 boundary is still Codex-owned:

- `WorkerExecutionAdapter` imports launch/process/result receipt types from `control_plane.codex_worker`;
- common `LaunchSpec` is documented as a Codex turn and contains literal `codex_home`;
- `ProcessRef` and result receipts carry Codex-module structures;
- production `executive_worker_broker.py` is explicitly a dedicated Codex broker and directly imports/instantiates `CodexWorkerAdapter`;
- current secret-canary/auth exception vocabulary is Codex-specific.

Therefore a new provider may not be implemented by passing Alibaba/Z.AI/Grok state through `codex_home` or by creating `executive_alibaba_broker.py`, `executive_grok_broker.py`, etc. The former lies about provider identity; the latter creates parallel lifecycle/control planes.

Call the required gate **HF1 — Harness Contract generalization**.

### HF1 — generalize the existing harness/broker, preserve Codex v1

HF1 must preserve current Codex adapter behavior, P1B/OHF semantics and accepted receipts; keep Executive Job/Attempt lifecycle unchanged; retain one reviewed broker lifecycle boundary; centralize provider-neutral OS-principal/process cleanup/cancel/validation; and keep provider-native home/auth/session mechanics adapter-private.

Preferred shape:

```text
Executive immutable authorized work handoff
        -> provider-neutral execution request/spec
        -> one reviewed worker broker / adapter resolver
             -> Codex adapter + Codex-private auth/home
             -> supported-coding-tool adapter + provider-private plan endpoint/auth
             -> ACP adapter + ACP-private session/transport
```

The exact common v2 schema is not frozen here. HF1 must first separate truly common fields from Codex-specific fields. A common contract must not retain fields whose names/semantics assume Codex. Provider-private config is referenced through reviewed adapter registration and raw credentials never enter model-visible handoffs or Executive persisted payloads.

The broker resolves an immutable reviewed adapter identity; model/caller cannot supply arbitrary executable/provider commands. Unimplemented/unapproved adapters remain fail-closed.

HF1 must prove at minimum:

1. current Codex golden paths/receipts remain compatible where source law requires;
2. one synthetic non-Codex fake adapter traverses the same broker/supervisor start/status/collect/cancel/validate lifecycle with no provider-specific broker or second state store;
3. common request/receipt types contain no `codex_*` field and no vendor-secret value;
4. adapter-private home/auth/session details cannot leak into prompts, generic logs, Executive Events or cross-provider config;
5. peer authorization, dedicated-principal cleanup, cancellation, timeout, validation and replay do not weaken;
6. unknown/unimplemented adapter IDs refuse before provider contact;
7. adapter identity/provider relation is immutable and receipted;
8. HF1 adds zero autonomous failover/retry;
9. if safe generalization would alter frozen P1B/1F-C evidence, HF1 stops for an explicit source-law amendment.

Provider adapter research/fixtures may happen before HF1, but **no non-Codex provider can be called an Executive worker vertical until HF1 passes**. Alibaba/Z.AI should share a supported-coding-tool family where lawful; Grok/Cursor should share an ACP family where lawful.

---

## 8. Multi-host execution is a transport extension, not another Executive runtime

Current production Executive architecture is deliberately local:

- `ExecutiveControlService` is a private local AF_UNIX service with no TCP listener;
- current `ServiceConfig` describes one local worker/provider/quota/model;
- the reviewed worker broker uses a local Unix socket and kernel peer-UID authorization;
- the current production template names one worker UID/user/provider home/broker socket.

Therefore an opaque Capacity Fabric `host_ref` is **not** proof a remote Mac can execute work. The spare MacBook/Mac mini/other host cannot become Executive capacity merely by registering another Worker row or by treating a self-hosted GitHub runner as an Executive worker transport.

Call the required gate **MH1 — Multi-Host Executive Worker Transport**.

### MH1 ownership law

One Executive Runtime remains canonical on the designated control host. A remote machine may run a reviewed **worker-broker endpoint only**. It owns no Job queue, workstream, scheduler, retry policy, company priority, or canonical completion state.

Conceptually:

```text
canonical Executive Runtime / supervisor on control host
        |
        | exact Attempt-bound worker operation over reviewed authenticated transport
        v
registered remote host endpoint
        |
        v
same provider-neutral worker-broker / adapter lifecycle
        |
        v
local OS principal + local provider home/session on that remote host
```

No per-host Executive database. No distributed consensus layer. No Kubernetes-style scheduler. No GitHub Actions job as lifecycle authority. No generic SSH command executor.

### MH1 identity and routing law

- `host_ref` in `provider_capacity.v1` remains secret-free observation identity, not an authenticated network address or execution credential.
- Executive worker registration/config must establish an immutable reviewed `worker_id -> host execution endpoint` relationship before remote placement; the exact storage/config shape is not frozen by F0.
- Transport-authenticated host identity must be stronger than caller-supplied `host_ref`. A remote endpoint must prove the expected company host/principal through a reviewed cryptographic or OS-backed mechanism.
- Private endpoint address, certificate/key material, VPN identity, machine serial, username and filesystem paths do not enter `provider_capacity.v1`.
- A Worker cannot silently move hosts mid-Attempt. Host/endpoint binding used by the launch must be immutable for that Attempt and receipted in the remote transport evidence or an accepted existing execution-principal extension.
- Phase 1F-C closed placement snapshot is not widened for host identity. If live multi-host proof requires host identity in a frozen Executive evidence object, MH1 must return for a source-law amendment rather than adding it ad hoc.

### MH1 operation / effect-unknown law

Remote transport loss is not proof the worker call failed.

Every modifying remote operation must carry a stable operation identity bound to the exact Executive Job/Attempt/generation and one selected host/worker. Then:

```text
send exact operation
   -> response received: reconcile normally
   -> timeout/disconnect: EFFECT_UNKNOWN
        -> query the SAME host/worker operation status through the SAME reviewed transport identity
        -> accepted/committed receipt: continue reconciliation, no resend
        -> true not-found after complete reconciliation: only then consider same-operation retry under source law
        -> status unavailable: remain uncertain, no failover
```

Never route the same logical Attempt to another Mac/provider because the first network reply was lost. Cross-host failover is a **new Executive Attempt/recovery decision** only after canonical current-Attempt state makes that legal.

### MH1 broker / security law

The existing local broker's kernel peer-UID check cannot simply be replaced with “IP allowed”. MH1 must preserve an equally explicit principal boundary for remote requests.

The remote endpoint must expose only the bounded broker operations required by HF1 (`start/status/collect/cancel/validate` or their reviewed successor), not arbitrary shell/SSH, file upload, generic command argv, provider credential access, Git merge/deploy or service control.

Each remote host keeps provider credential/home bytes local. Control host sends only reviewed provider-neutral work specs plus adapter/model identifiers; it never copies attached-login credential directories among Macs.

Network transport must be private/authenticated and must not create a public listener. The exact mechanism (mutual TLS, an already-reviewed private overlay transport, or another company-controlled authenticated channel) is a future MH1 decision; F0 does not bless a vendor or protocol by convenience.

### MH1 acceptance requirements

Before remote hosts become `PROVEN_LIVE` Executive capacity, MH1 must prove at minimum:

1. exactly one canonical Executive Runtime remains authoritative while two physical hosts execute different bounded test Attempts;
2. remote host endpoint cannot select Job priority, scan/claim arbitrary Jobs, widen grant, or choose fallback work;
3. wrong host/principal/certificate/endpoint identity refuses before provider contact;
4. exact worker/host binding is immutable for one Attempt and auditable without exposing private addresses/credentials;
5. provider credentials remain local to each host and absent from control-host work handoffs/logs;
6. timeout-after-remote-commit reconciles the same operation and creates zero duplicate provider turns;
7. true remote endpoint outage leaves the Attempt blocked/lost according to reviewed Executive law, not silently rerouted;
8. restart of control host or remote endpoint preserves/reconciles canonical Runtime truth without a per-host cursor/queue database;
9. remote cancellation/validation/process cleanup retain the same bounded principal/process guarantees as local broker law;
10. one host may be busy/cooling/offline without marking another host's provider slot unavailable;
11. a self-hosted CI runner, tmux session, GUI tab or SSH reachability alone never counts as Executive host admission;
12. no public listener, generic shell, cross-host credential copy, second lifecycle DB, scheduler or autonomous failover is introduced.

### Sequencing consequence

MH1 is **not required** for the first single-host CF2-I or PF1 provider canary. It is required before the company claims multi-Mac Executive capacity or routes real Executive work to a second physical host. HF1 is an upstream dependency because remote execution should carry the provider-neutral broker contract, not freeze Codex-specific wire types into a network protocol.

---

## 9. Revised sequence

```text
F0     provider-capacity ownership + contract freeze
CF1    Macro provider_capacity.v1 producer + real no-write consumer
OF1    accepted Phase 1F-C v4 implementation
CF2-F  Executive claim-evidence source-law freeze against landed v4
CF2-I  existing-provider capacity-aware placement using the accepted claim receipt seam
RF1    provider-neutral Model Router suitability/equivalence freeze + implementation
HF1    provider-neutral worker-harness/broker contract freeze + implementation
PF1+   one new provider/harness vertical per PR; shared-route admission requires RF1 + HF1
MH1    authenticated multi-host worker transport; required before second physical host carries real Executive work
OF2    real heterogeneous Fable fan-out / exhaustion / review / repair / aggregation proof
```

RF1 and HF1 may run in parallel after shared upstream gates when their exact paths are disjoint. PF1 depends on both. MH1 depends on HF1 but can be sequenced independently of the first single-host PF1 if product priority favors provider diversity before multi-host compute.

This amendment supersedes any reading of F0 that would put Capacity Fabric fields directly into `placement_snapshot_json`, claim CF2 can begin without fresh claim-evidence review, use alias order as a provider scheduler, disguise new providers behind Codex-specific common types, create one broker/lifecycle per vendor, or treat `host_ref`/SSH/CI-runner reachability as remote Executive execution authority.
