---
key: EXECUTIVE-CAPACITY-FABRIC
title: Executive Capacity Fabric — heterogeneous provider and subscription placement
objective: >
  Let Sol/Fable/Executive OS use the company's real AI capacity as one governed workforce:
  discover usable provider/account capacity without exposing credentials, preserve provider-
  native quota/cooling truth, choose among already-eligible workers deterministically, prefer
  subscription/local capacity where policy permits, preserve frontier reserves, and continue
  safely across quota exhaustion without creating duplicate execution or another lifecycle plane.
status: active
program: shared-ai-provider-control
p0: EXECUTIVE_OS
repos: [macro, mastermind]
owner: ceo-sol
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - id: F0
    title: Ownership, contract and no-rebuild architecture freeze
    status: done
  - id: CF1
    title: Secret-free provider-capacity projection over existing Macro provider state
    status: done
    pr: 6297
    depends_on: [F0]
    next_action: >
      COMPLETED_DO_NOT_REPEAT. Sol accepted exact head
      fc12904f59a5758817aa2c76ffaa40bb1ebcbf8e after full hosted CI and fences,
      then squash-merged PR #6297 as dcdd939c45b23abce5ba04f95e330ac914a3904b.
      Reopen CF1 only for a concrete defect or material-source change; do not use it as a place
      to implement Executive placement or new providers.
  - id: CF2-F
    title: Freeze Executive claim-time capacity evidence and acquisition against landed schema v4
    status: todo
    depends_on: [CF1]
    next_action: >
      Sol must now freeze and independently review the smallest typed capacity-evidence extension
      to the existing atomic JOB_CLAIMED receipt plus one secret-free Provider Control acquisition
      seam consuming accepted `mastermind.provider_capacity.v1`. Preserve the closed schema-v4
      placement snapshot byte-for-byte; create no second event, table, service, daemon or schema v5.
      Stop after accepted source law; CF2-I remains a separate implementation wave.
  - id: CF2-I
    title: Executive capacity-aware placement using the reviewed claim receipt
    status: todo
    depends_on: [CF2-F]
    next_action: >
      After CF2-F is accepted, consume `mastermind.provider_capacity.v1` only after Model Router and
      Executive hard eligibility filters, rank eligible candidates deterministically, persist the
      accepted capacity evidence atomically with JOB_CLAIMED, and prove one existing-provider /
      multi-account canary. Do not start before CF2-F acceptance.
  - id: RF1
    title: Provider-neutral Model Router suitability equivalence
    status: todo
    depends_on: [CF2-I]
    next_action: >
      Before any new provider is admitted to the same Executive task routes as an existing
      provider, evolve the existing stateless Model Router with reviewed ordered suitability
      tiers or equivalent provider-neutral execution classes. Capacity may rank only within
      the first lawful equivalence tier; concrete alias/file order must not become a vendor scheduler.
  - id: HF1
    title: Provider-neutral worker harness and broker contract
    status: todo
    depends_on: [CF2-I]
    next_action: >
      Generalize the existing WorkerExecutionAdapter/broker boundary without breaking current
      Codex P1B/OHF semantics: extract truly common execution request/receipt law, keep provider
      homes/auth/session mechanics adapter-private, prove one synthetic non-Codex adapter through
      the same broker lifecycle, and create no provider-specific broker or lifecycle plane.
  - id: PF1
    title: First heterogeneous subscription provider vertical
    status: todo
    depends_on: [RF1, HF1]
    next_action: >
      Add exactly one reviewed provider/harness vertical, with Claude as the preferred first real
      non-Codex proof, and prove one bounded Executive child Job through the real adapter before
      making that provider generally routable. Cursor/Grok and other provider verticals remain V1.x
      expansion and may be researched in parallel, but do not block the first V1 operating proof.
  - id: MH1
    title: Authenticated multi-host Executive worker transport
    status: todo
    depends_on: [HF1]
    next_action: >
      V1.x only. Before a second physical Mac/host carries real Executive work, extend the existing
      worker-broker lifecycle through one private authenticated remote transport while keeping one
      canonical Executive Runtime on the control host. Prove stable Attempt-bound operation identity,
      effect-unknown reconciliation, local-only provider credentials and zero remote queue/scheduler.
decisions:
  - DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT
artifacts:
  - agentos/decisions/DEC-EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_PLACEMENT_AMENDMENT_2026-08-22.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_SEMANTIC_IDENTITY_AMENDMENT_2026-08-22.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_OBSERVATION_NULL_AMENDMENT_2026-08-22.md
  - agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-08-25.md
  - agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-08-25-CF1-ACCEPTED.md
  - docs/superpowers/plans/2026-08-25-mas-126-cf1-reconciliation.md
landmines:
  - "Macro `shared-ai-provider-control` already owns provider availability, auth pools, cooling and quota state; do not create ProviderAccount/QuotaHorizon truth tables in Executive OS."
  - "`usage_snapshot()` is a display aggregate, not a normalized truth contract. Its numeric defaults and fail-soft joins cannot be mapped 1:1 into provider_capacity.v1."
  - "Current Claude `discover_present_keys()` applies enablement filtering/fallback, so `usage_snapshot().present` can hide a disabled-but-installed credential. CF1 obtained unfiltered secret-free presence through the existing Provider Control owner; do not regress to the display field as source truth."
  - "Current Codex `available_accounts()` intentionally returns only usable accounts and therefore combines provider enablement, executable presence and credential presence. Preserve the CF1 source-owned observation seam that separates those dimensions without changing Codex dispatch semantics."
  - "A fail-soft helper that returns []/0/False on absent, corrupt or unreadable source cannot establish an exact zero/healthy/absent fact. Capacity observations must preserve source quality or degrade the affected field to unknown."
  - "Provider-capacity `present`, `enabled`, and `cooling.active` are nullable observations: true/false means observed; null means unknown. A fail-soft fallback may never manufacture false."
  - "`usage_snapshot()` display zeros are not proof of zero usage; no source observation means unknown unless a reviewed estimator with a real budget is configured."
  - "Unknown quota is not unlimited and stale quota is not fresh. Never derive absolute remaining capacity from a percentage when the absolute limit is unknown."
  - "Provider/account presence is not authentication success, and Slack/GitHub/provider process presence is not Executive execution evidence."
  - "Host matters: attached subscription capacity is bound to an opaque reviewed host identity; do not assume accounts on different Macs are globally interchangeable."
  - "Capacity host_ref is observational identity only; it is not an authenticated endpoint or remote execution credential."
  - "Current Executive control/broker path is local AF_UNIX with one configured worker. Multi-host transport remains MH1/V1.x and must not create a second Runtime/queue/scheduler or generic SSH executor."
  - "Model Router suitability and provider capacity are separate filters. Provider health/cost may rank eligible workers but may not redefine model quality, authority or required independence."
  - "Current Model Router routes are ordered concrete model aliases. Before heterogeneous providers share a route, RF1 must define provider-neutral equivalence tiers/classes so alias/file order cannot silently become provider priority."
  - "Current WorkerExecutionAdapter/v1 still imports Codex-owned types and LaunchSpec contains codex_home; before a non-Codex Executive worker is integrated, HF1 must generalize the existing harness/broker without lying about provider identity or forking lifecycle."
  - "Do not create executive_alibaba_broker/executive_grok_broker-style provider lifecycle services. One reviewed broker/adapter lifecycle must resolve immutable approved adapters; provider-private home/auth/session mechanics stay behind the adapter."
  - "Remote timeout/disconnect is EFFECT_UNKNOWN, not permission to send the same Attempt to another host/provider. Reconcile the same host/worker operation first."
  - "A provider 429/auth/transport failure after an Attempt begins does not authorize blind retry or cross-provider failover; reconcile the Executive Attempt/effect state first."
  - "Phase 1F-C owns schema v4. Capacity Fabric must not introduce another v4 migration or temporary v3 placement schema."
  - "Phase 1F-C freezes placement_snapshot_json to exactly worker_id/quota_class/provider/account_label/snapshot time. Capacity Fabric must not add quota, host, policy or reason fields to that object or change its digest definition."
  - "Capacity decision evidence belongs in the existing atomic claim receipt only after CF2-F source-law acceptance; if that seam proves insufficient, return to Sol rather than inventing a second event/ledger or schema v5."
  - "Whole-repository Macro commit identity is audit provenance only. High-churn unrelated repo commits must not change provider-capacity semantic snapshot_hash; material provider-source bytes must."
  - "snapshot_hash and generated_at are distinct: Executive claim evidence must bind both, because identical semantic contents can have different freshness."
  - "CF1 stdout proves the contract, not the future Executive acquisition transport. CF2-F must freeze one secret-free bounded acquisition seam; Executive may not import floating Macro Python or read raw provider ledgers/secrets."
  - "The provider-capacity normalizer receives only secret-free typed observations. Existing Provider Control helpers may continue their already-reviewed credential-presence mechanics internally; that authority is not transferred to the normalizer or Executive OS."
  - "Subscription headroom should reduce marginal API spend for routine eligible work, but policy may reserve scarce frontier capacity for critical/interactive work."
  - "Never expose auth tokens, cookies, API keys, raw auth files, provider-home contents, email/account PII, remote endpoint credentials or private host addresses in the capacity projection."
do_not_redo:
  - "Do not create a provider/account/quota database in Mastermind Executive OS."
  - "Do not duplicate Macro key_pool, budget_gate, llm_auth, provider_health or Codex account-home identity logic."
  - "Do not change existing provider dispatcher selection/fail-open behavior merely to make Capacity Fabric easier; observation APIs remain read-only and independently tested."
  - "Do not import floating Macro provider internals directly into Mastermind as the cross-repo contract; consume the accepted versioned projection."
  - "Do not put live quota/cooling state into Model Router policy files."
  - "Do not create a second router for provider capacity; evolve the existing stateless Model Router through RF1."
  - "Do not create one Executive Runtime/database/queue per Mac or use GitHub Actions/tmux/SSH as Executive lifecycle authority."
  - "Do not create a long-lived capacity daemon/service merely to bridge Macro to Executive without a separate architecture ruling."
  - "Do not use LLM judgment to select a worker, waive an independence requirement, or interpret unknown quota as capacity."
  - "Do not widen Phase 1F-C placement_snapshot_json for Capacity Fabric."
  - "Do not disguise Alibaba/Z.AI/Grok/Cursor behind a `codex_home` field or copy Codex-only secret-canary semantics into the common harness contract."
  - "Do not reopen CF1 implementation absent a concrete defect or material-source change."
  - "Do not widen Capacity Fabric into Wake, Slack dispatch, Control Room, browser/devserver resources, host arming, merge/deploy authority or capital/trading authority."
next_action: >
  Commission and execute `WS:EXECUTIVE-CAPACITY-FABRIC::CF2-F — Freeze Executive claim-time
  capacity evidence and acquisition` against current protected Mastermind plus accepted Macro CF1.
  The wave is source-law/architecture only and stops before CF2-I implementation. Worker Browser /
  DevServer Resource Fabric architecture and existing C1/S0-R1/ASD/host-readiness lanes may proceed
  independently in parallel because their authority and changed-path surfaces are disjoint.
---

## Capability state

CF1 is accepted and merged in Macro as `dcdd939c45b23abce5ba04f95e330ac914a3904b`.
The strict no-write `mastermind.provider_capacity.v1` producer and machine/operator JSON consumer are
`BUILT_NOT_PROVEN` as an always-on production placement capability: the contract is implemented and
exact-head tested, but Executive OS still does not consume it at claim time. CF2-F is the next source-law
dependency; CF2-I capacity-aware placement, RF1 provider-neutral suitability, HF1 common harness, PF1
first real non-Codex worker and MH1 multi-host transport remain not built / held by their dependencies.

## 10/10 end-state

A real Sol mission is decomposed through accepted Executive/COO law; child Jobs can land on
heterogeneous subscription/API/local workers according to suitability, independence and fresh
capacity; one provider can become cooling/exhausted without duplicate execution; a different
eligible provider can take later safe work; independent review/repair still follows Executive
lineage; claim receipts explain why each worker was selected while the closed placement identity
remains stable; the existing Model Router defines provider-neutral suitability tiers while capacity
selects only within the first lawful tier; one provider-neutral harness/broker lifecycle executes
approved Codex/supported-tool/ACP adapters without vendor-specific queues or brokers; one canonical
Executive Runtime can later drive bounded worker brokers on multiple authenticated physical hosts
without copying provider credentials or creating per-host lifecycle state; the Control Room can
later project workforce/capacity truth without owning it; and the Chairman does not manually choose
providers, watch quotas, assign Macs or carry messages between sessions.

## Learning boundary

Later descriptive metrics may include provider reliability, capacity evidence age, quota
utilisation, marginal API spend avoided, host availability, remote transport reliability, repair
rate and independent-review catches. They are operational learning signals only. Provider
sentiment/summary/model output never gains market, portfolio, authority or capital control from
this workstream.
