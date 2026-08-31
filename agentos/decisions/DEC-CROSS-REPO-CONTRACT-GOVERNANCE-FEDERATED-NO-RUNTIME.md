---
key: CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME
question: >
  How should Mastermind-X govern material Macro / Terminal / Portfolio contracts so
  hidden schema, freshness, privacy, fallback and authority drift is eliminated without
  creating another runtime, traffic proxy, release gate or control plane?
answer: >
  Use a federated owner-native contract model: the canonical producer owns meaning/schema,
  the consumer pins version/conformance and local presentation transforms, existing
  transports continue carrying bytes, and exact import/publication receipts plus actual
  consumer proof establish whether the seam is live. Cross-Repository Contract Governance
  records/audits these boundaries in the existing semantic registry + one Agent OS workstream;
  it does not sit in the traffic path, dispatch work, gate releases, own lifecycle, or mint
  another registry. Direct Terminal-to-Portfolio integration remains rejected by design until
  a concrete future user/machine job and a new Sol ruling justify it.
rationale: >
  The 2026-08-28 three-repository census found that the dominant defects are semantic and
  evidentiary, not lack of another platform: consumer defaults can exceed producer authority,
  imported Macro state inside Portfolio lacks one exact run-level identity, Portfolio writes
  reverse artifacts by impersonating the Macro working tree, and several Terminal bridges
  preserve last-good data while formal cross-repo schema/import receipts lag implementation.
  Existing positive patterns such as the Macro-frozen / Terminal-consumed workspace_layout.v1
  contract already prove that producer ownership + golden conformance + a real consumer can
  solve these problems without a central gateway. A new governance service would duplicate
  control/traffic/state authority and make the audit layer capable of changing the behavior it
  is supposed to describe.
alternatives:
  - option: Central Contract Governance service or cross-repo gateway
    why_not: >
      It would become another traffic/control plane, create new availability and routing
      authority, and violate the one-canonical-system law. Governance must observe/test the
      existing paths rather than proxy them.
  - option: Documentation-only audits with no producer/consumer conformance or receipts
    why_not: >
      The historical audit became stale while implementations evolved. Prose alone cannot
      prevent semantic drift, authority widening or fallback-green failures and cannot prove
      an actual consumer is using current data.
  - option: One central runtime contract registry queried by every repository
    why_not: >
      This duplicates producer-owned contracts/Synapse and introduces another runtime
      dependency. Shared semantics should be generated as versioned fixtures/descriptors from
      canonical owners, not resolved through a new service.
  - option: Build a direct Terminal-to-Portfolio bridge because both products use portfolio language
    why_not: >
      Terminal Conviction Book, Macro descriptive portfolio context and Mastermind autonomous
      paper books are distinct semantic objects. No current user/machine job requires a direct
      Terminal-to-Portfolio transfer, so building one would create unnecessary coupling and
      confuse authority boundaries.
evidence:
  - "config/mastermind_programs.yml@Macro 24ccea3fe482ab97c415db387f272b34c4852ed3: existing project-scoped parent `cross-repo-contract-governance`, lifecycle building, architecture/advisory-only."
  - "agentos/README.md + agentos/schema/workstream.schema.yml: Agent OS is durable organizational memory and cannot become execution/liveness authority."
  - "research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md: historical three-repo seam census and original hardening/consolidation findings."
  - "research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md: current-head reconciliation and capability ledger."
  - "Macro engine/neuralweb/mastermind_context.py@24ccea3fe482ab97c415db387f272b34c4852ed3: all five Neural Web -> Portfolio authority booleans false / context-only standing law."
  - "Portfolio current master@97f85ce5b84030faf4d291f988a1c642fb15e80a: previous seam files remain materially unchanged from the accepted census while Executive/Slack operating-surface work advanced separately."
  - "Terminal #480 / master b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea: workspace_layout.v1 demonstrates owner-frozen contract + digest-pinned consumer conformance + real consumer without a second store."
  - "Chairman explicit approval in the active Sol session on 2026-08-28 after review of the three-repo census, unresolved seam ledger, no-rebuild ruling, closure plan and first Fable commissions."
affects:
  - WS:CROSS-REPO-CONTRACT-GOVERNANCE
  - cross-repo-contract-governance
  - research/CROSS_REPO_CONTRACT_GOVERNANCE_CURRENT_STATE_2026-08-28.md
  - docs/superpowers/specs/2026-08-28-cross-repo-contract-governance-design.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-28
---

# Federated, owner-native contract governance; no governance runtime

This decision freezes the architecture for the Cross-Repository Contract Governance program.

## Binding contract pattern

Every material seam converges toward:

`producer-owned meaning/schema -> consumer conformance/version pin -> existing transport -> import/publication receipt -> actual consumer proof`.

The governance program may create durable records, formal schemas/fixtures at the lawful owner,
consumer tests/adapters, and proof receipts. It may not become the middleman for the traffic.

## Authority intersection law

A consumer may never exercise stronger authority merely because it can read a payload. Effective
authority is bounded by the producer's explicit contract and the consumer's own accepted authority
map. Missing, malformed, stale, unknown or contradictory authority fails inert until reconciled.

This is immediately load-bearing for the current Macro Neural Web -> Portfolio seam.

## Last-good observability law

Last-good serving is not itself a defect. The defect is allowing old readable bytes to look like a
successful current producer/import. A lawful last-good seam must expose producer/source clock,
refresh/import attempt, stale/error state and correction identity sufficiently for the actual
consumer/proof to distinguish current from retained data.

## Direct Terminal -> Portfolio ruling

No direct Terminal -> Portfolio API/import/schema is authorized by this program. Its current
absence is classified `REJECTED_BY_DESIGN`, not `NOT_BUILT`.

A future exception requires:

1. a concrete primary user/machine job that cannot be satisfied through current owner boundaries;
2. current three-repo archaeology and duplicate-system check;
3. explicit data/authority/privacy/correction contract;
4. a new Sol ruling.

## Runtime boundary

Neither the semantic program nor `WS:CROSS-REPO-CONTRACT-GOVERNANCE` can admit/dispatch a Job,
claim a Worker, gate a merge/deploy, manage retries, schedule refreshes, route contract traffic, or
determine liveness. Executive OS remains canonical for live work; GitHub remains canonical for
implementation/evidence; Agent OS records organizational truth.
