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
blast_radius: platform
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
  - id: CF2
    title: Executive capacity-aware placement on accepted schema-v4 runtime
    status: todo
    depends_on: [CF1]
    next_action: >
      After the separately accepted Phase 1F-C schema-v4 implementation lands, commission one
      Mastermind wave that consumes `mastermind.provider_capacity.v1` only after Model Router
      and Executive eligibility filters, binds capacity evidence into the existing placement
      snapshot/claim path, and proves one real existing-provider canary without adding vendors.
decisions:
  - DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT
artifacts:
  - agentos/decisions/DEC-EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT.md
  - research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md
landmines:
  - "Macro `shared-ai-provider-control` already owns provider availability, auth pools, cooling and quota state; do not create ProviderAccount/QuotaHorizon truth tables in Executive OS."
  - "`usage_snapshot()` display zeros are not proof of zero usage; no source observation means unknown unless a reviewed estimator with a real budget is configured."
  - "Unknown quota is not unlimited and stale quota is not fresh. Never derive absolute remaining capacity from a percentage when the absolute limit is unknown."
  - "Provider/account presence is not authentication success, and Slack/GitHub/provider process presence is not Executive execution evidence."
  - "Host matters: attached subscription capacity is bound to an opaque reviewed host identity; do not assume accounts on different Macs are globally interchangeable."
  - "Model Router suitability and provider capacity are separate filters. Provider health/cost may rank eligible workers but may not redefine model quality, authority or required independence."
  - "A provider 429/auth/transport failure after an Attempt begins does not authorize blind retry or cross-provider failover; reconcile the Executive Attempt/effect state first."
  - "Phase 1F-C owns schema v4. Capacity Fabric must not introduce another v4 migration or temporary v3 placement schema."
  - "Subscription headroom should reduce marginal API spend for routine eligible work, but policy may reserve scarce frontier capacity for critical/interactive work."
  - "Never expose auth tokens, cookies, API keys, raw auth files, provider-home contents, email/account PII, or secret-ref values in the capacity projection."
do_not_redo:
  - "Do not create a provider/account/quota database in Mastermind Executive OS."
  - "Do not duplicate Macro key_pool, budget_gate, llm_auth, provider_health or Codex account-home identity logic."
  - "Do not import floating Macro provider internals directly into Mastermind as the cross-repo contract; publish/consume a versioned projection instead."
  - "Do not put live quota/cooling state into Model Router policy files."
  - "Do not use LLM judgment to select a worker, waive an independence requirement, or interpret unknown quota as capacity."
  - "Do not add Z.AI, Alibaba, Claude Code, Grok, Cursor, OpenRouter or local-provider adapters in CF1; prove the contract first on existing Codex/Claude/DeepSeek sources."
  - "Do not widen Capacity Fabric into Wake, Slack dispatch, Control Room P1, merge/deploy authority or capital/trading authority."
next_action: >
  After F0 is accepted on Macro main, commission CF1 only: a deterministic, secret-free,
  no-write `mastermind.provider_capacity.v1` producer over existing provider-control state with
  a real machine/operator consumer and exact-head proof. Keep Executive placement and all new
  provider verticals held.
---

## Capability state

`SPEC_ONLY` at F0. The provider-control substrate itself is operating and multi-account-aware,
but no canonical `mastermind.provider_capacity.v1` producer exists and Executive OS does not yet
consume provider capacity for worker placement.

## 10/10 end-state

A real Sol mission is decomposed through accepted Executive/COO law; child Jobs can land on
heterogeneous subscription/API/local workers according to suitability, independence and fresh
capacity; one provider can become cooling/exhausted without duplicate execution; a different
eligible provider can take later safe work; independent review/repair still follows Executive
lineage; placement receipts explain why each worker was selected; the Control Room can later
project workforce/capacity truth without owning it; and the Chairman does not manually choose
providers, watch quotas or carry messages between sessions.

## Learning boundary

Later descriptive metrics may include provider reliability, capacity evidence age, quota
utilisation, marginal API spend avoided, repair rate and independent-review catches. They are
operational learning signals only. Provider sentiment/summary/model output never gains market,
portfolio, authority or capital control from this workstream.
