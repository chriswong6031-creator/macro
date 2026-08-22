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
    status: todo
    depends_on: [F0]
    next_action: >
      Implement one no-write Macro vertical from existing key-pool/budget/provider state to
      `mastermind.provider_capacity.v1` and a real JSON/operator consumer, with exact unknown,
      staleness, correction and secret-redline proof. Do not modify Executive placement.
  - id: CF2-F
    title: Freeze Executive claim-time capacity evidence against landed schema v4
    status: todo
    depends_on: [CF1]
    next_action: >
      After the separately accepted Phase 1F-C schema-v4 implementation lands, freeze and
      independently review the smallest typed capacity-evidence extension to the existing
      atomic JOB_CLAIMED receipt. Preserve the closed v4 placement snapshot byte-for-byte;
      do not create another event/table or assume schema v5 by convenience.
  - id: CF2-I
    title: Executive capacity-aware placement using the reviewed claim receipt
    status: todo
    depends_on: [CF2-F]
    next_action: >
      Consume `mastermind.provider_capacity.v1` only after Model Router and Executive hard
      eligibility filters, rank eligible candidates deterministically, persist the accepted
      capacity evidence atomically with JOB_CLAIMED, and prove one existing-provider/multi-account canary.
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
      Add exactly one reviewed provider/harness vertical, prove one real bounded Executive child
      Job through the real adapter, and only then make that provider eligible in the RF1-reviewed
      task routes. Do not call documentation or adapter installation PROVEN_LIVE.
  - id: MH1
    title: Authenticated multi-host Executive worker transport
    status: todo
    depends_on: [HF1]
    next_action: >
      Before a second physical Mac/host carries real Executive work, extend the existing worker-
      broker lifecycle through one private authenticated remote transport while keeping one canonical
      Executive Runtime on the control host. Prove stable Attempt-bound operation identity,
      effect-unknown reconciliation, local-only provider credentials and zero remote queue/scheduler.
decisions:
  - DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT
artifacts:
  - agentos/decisions/DEC-EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_PLACEMENT_AMENDMENT_2026-08-22.md
landmines:
  - "Macro `shared-ai-provider-control` already owns provider availability, auth pools, cooling and quota state; do not create ProviderAccount/QuotaHorizon truth tables in Executive OS."
  - "`usage_snapshot()` display zeros are not proof of zero usage; no source observation means unknown unless a reviewed estimator with a real budget is configured."
  - "Unknown quota is not unlimited and stale quota is not fresh. Never derive absolute remaining capacity from a percentage when the absolute limit is unknown."
  - "Provider/account presence is not authentication success, and Slack/GitHub/provider process presence is not Executive execution evidence."
  - "Host matters: attached subscription capacity is bound to an opaque reviewed host identity; do not assume accounts on different Macs are globally interchangeable."
  - "Capacity host_ref is observational identity only; it is not an authenticated endpoint or remote execution credential."
  - "Current Executive control/broker path is local AF_UNIX with one configured worker. Before a second physical host carries Executive work, MH1 must add a reviewed authenticated transport without a second Runtime/queue/scheduler or generic SSH executor."
  - "Model Router suitability and provider capacity are separate filters. Provider health/cost may rank eligible workers but may not redefine model quality, authority or required independence."
  - "Current Model Router routes are ordered concrete model aliases. Before heterogeneous providers share a route, RF1 must define provider-neutral equivalence tiers/classes so alias/file order cannot silently become provider priority."
  - "Current WorkerExecutionAdapter/v1 still imports Codex-owned types and LaunchSpec contains codex_home; before a non-Codex Executive worker is integrated, HF1 must generalize the existing harness/broker without lying about provider identity or forking lifecycle."
  - "Do not create executive_alibaba_broker/executive_grok_broker-style provider lifecycle services. One reviewed broker/adapter lifecycle must resolve immutable approved adapters; provider-private home/auth/session mechanics stay behind the adapter."
  - "Remote timeout/disconnect is EFFECT_UNKNOWN, not permission to send the same Attempt to another host/provider. Reconcile the same host/worker operation first."
  - "A provider 429/auth/transport failure after an Attempt begins does not authorize blind retry or cross-provider failover; reconcile the Executive Attempt/effect state first."
  - "Phase 1F-C owns schema v4. Capacity Fabric must not introduce another v4 migration or temporary v3 placement schema."
  - "Phase 1F-C freezes placement_snapshot_json to exactly worker_id/quota_class/provider/account_label/snapshot time. Capacity Fabric must not add quota, host, policy or reason fields to that object or change its digest definition."
  - "Capacity decision evidence belongs in the existing atomic claim receipt only after a fresh reviewed CF2-F source-law freeze; if that seam proves insufficient, return to Sol rather than inventing a second event/ledger or schema v5."
  - "Subscription headroom should reduce marginal API spend for routine eligible work, but policy may reserve scarce frontier capacity for critical/interactive work."
  - "Never expose auth tokens, cookies, API keys, raw auth files, provider-home contents, email/account PII, remote endpoint credentials or private host addresses in the capacity projection."
do_not_redo:
  - "Do not create a provider/account/quota database in Mastermind Executive OS."
  - "Do not duplicate Macro key_pool, budget_gate, llm_auth, provider_health or Codex account-home identity logic."
  - "Do not import floating Macro provider internals directly into Mastermind as the cross-repo contract; publish/consume a versioned projection instead."
  - "Do not put live quota/cooling state into Model Router policy files."
  - "Do not create a second router for provider capacity; evolve the existing stateless Model Router through RF1."
  - "Do not create one Executive Runtime/database/queue per Mac or use GitHub Actions/tmux/SSH as Executive lifecycle authority."
  - "Do not use LLM judgment to select a worker, waive an independence requirement, or interpret unknown quota as capacity."
  - "Do not widen Phase 1F-C placement_snapshot_json for Capacity Fabric."
  - "Do not disguise Alibaba/Z.AI/Grok/Cursor behind a `codex_home` field or copy Codex-only secret-canary semantics into the common harness contract."
  - "Do not add Z.AI, Alibaba, Claude Code, Grok, Cursor, OpenRouter or local-provider adapters in CF1; prove the contract first on existing Codex/Claude/DeepSeek sources."
  - "Do not widen Capacity Fabric into Wake, Slack dispatch, Control Room P1, merge/deploy authority or capital/trading authority."
next_action: >
  After F0 is accepted on Macro main, commission CF1 only: a deterministic, secret-free,
  no-write `mastermind.provider_capacity.v1` producer over existing provider-control state with
  a real machine/operator consumer and exact-head proof. Keep CF2-F/CF2-I, RF1, HF1, PF1 and
  MH1 held.
---

## Capability state

`SPEC_ONLY` at F0. The provider-control substrate itself is operating and multi-account-aware,
but no canonical `mastermind.provider_capacity.v1` producer exists and Executive OS does not yet
consume provider capacity for worker placement. Multi-host Executive execution is also not built;
current reviewed control/broker architecture is local-host only.

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
