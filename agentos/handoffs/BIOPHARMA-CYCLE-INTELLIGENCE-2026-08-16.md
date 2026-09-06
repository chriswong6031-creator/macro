---
workstream: "WS:BIOPHARMA-CYCLE-INTELLIGENCE"
session: sol/biopharma-cycle-intelligence-architecture-20260816
model: codex
ended_because: complete
mission: >
  Reconcile the moved repository, decide whether the major specialist programs
  should be amalgamated, and initiate a durable Biopharma Cycle Intelligence OS
  masterplan with exact program boundaries and a bounded first continuation wave.
state_before: >
  The Seasonality/biopharma build had valuable temporal, calendar, event-study,
  model, calibration, Neural Web, and Prophet-shaped code, but several major
  components had no production builder or consumer. BioCatalyst, Market Memory,
  Defense Procurement V3, FIF, Earnings, Neural Web, Prophet, Terminal, and
  Portfolio were advancing under separate extensive plans with overlapping
  temporal, episode, market-response, and authority ambitions. The earlier BCI
  analysis predated BioCatalyst P0-C1, Defense D0R, Earnings recovery, and the
  real Company Intelligence event_workspace.v1 merge.
prs:
  - 5821
decisions:
  - DEC:BIOPHARMA-FEDERATED-NOT-MEGA-MERGED
changed:
  - path: research/BIOPHARMA_CYCLE_INTELLIGENCE_OS_MASTERPLAN_2026-08-16.md
    what: >
      Added the federated BCI product/system architecture, ownership matrix,
      four-clock model, episode/memory/context design, product journeys,
      research/authority laws, no-rebuild boundaries, and BCI-0A through BCI-11 waves.
  - path: research/BIOPHARMA_CYCLE_INTELLIGENCE_CURRENT_HEAD_DELTA_2026-08-16.md
    what: >
      Reconciled the architecture against current main through #5817 and recorded
      the new event_workspace.v1 reuse obligation plus updated BioCatalyst,
      Defense, FIF, Market Memory, Earnings, and Seasonality status.
  - path: research/BIOPHARMA_CYCLE_INTELLIGENCE_BCI_0B_ARCHAEOLOGY_HANDOFF_2026-08-16.md
    what: >
      Added the first bounded continuation mission: current-state archaeology,
      contract reuse, user/product evidence, temporal/identity/correction audit,
      authority audit, supersession ledger, and exact BCI-0C/BCI-1 handoffs, with
      a hard no-code stop condition.
  - path: agentos/decisions/DEC-BIOPHARMA-FEDERATED-NOT-MEGA-MERGED.md
    what: >
      Recorded the Sol architecture ruling to federate rather than mega-merge,
      subject to Chairman acceptance of the draft PR.
  - path: agentos/workstreams/WS-BIOPHARMA-CYCLE-INTELLIGENCE.md
    what: >
      Opened the durable BCI execution front door under the existing biocatalyst
      semantic parent, with only BCI-0A active and every later wave gated.
  - path: agentos/handoffs/BIOPHARMA-CYCLE-INTELLIGENCE-2026-08-16.md
    what: >
      Recorded this exact continuation state and do-not-redo boundaries.
verified:
  - claim: >
      The architecture branch is rebased directly onto current main and changes
      only BCI research and Agent OS files.
    command: >
      GitHub.compare_commits base=main head=sol/biopharma-cycle-intelligence-architecture-20260816
    result: >
      Base and merge-base are 5d600641bc3513f69a37cfb8cac1f1d86238e896;
      branch was one commit ahead and zero behind before this handoff addition;
      five added files and no runtime modifications.
  - claim: >
      Current main includes a real context-only event_workspace.v1 with immutable
      sibling publication, a verified reader, stable aliases, and correction replay.
    command: >
      GitHub.fetch_commit 5d600641bc3513f69a37cfb8cac1f1d86238e896;
      GitHub.fetch_file engine/company_intelligence/event_workspace.py;
      GitHub.fetch_file engine/neuralweb/company_intelligence_reader.py
    result: >
      PR #5817 merged as current main; event_workspace.v1 publishes under
      company_intelligence/event_workspaces, has all-false Prophet flags, and is
      read through marker to immutable generation without checkout/latest fallback.
  - claim: >
      BioCatalyst P0-C1 typed hydration-state code is merged, but that merge alone
      is not entitled production-browser acceptance.
    command: >
      GitHub.search_commits query='typed client hydration states P0-C1'
    result: >
      PR #5810 merged as 9d91bf877da428b96741c80c20f5a1c2a2b5ccc1;
      scope remained frontend hydration classification and did not change source truth.
  - claim: >
      Market Memory M0A's first technical-intake repair merged, while the broad
      V2 and M0B continuation remains gated on prospective evidence.
    command: >
      GitHub.search_commits recent repository commits; GitHub.fetch_file
      agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    result: >
      PR #5805 merged as e1ec8865ac92ccebd11f8208fe2c1e09a85c21e9;
      the checked-in workstream still names prospective disposition/freshness work
      and has not established operational learned/hybrid retrieval.
  - claim: >
      FIF remains an independent packet program under review and has not started FIF-2.
    command: >
      GitHub.get_pr_info repository=mastermindx-market-intelligence/macro pr=5809
    result: >
      PR #5809 remains open, mergeable, held for FIF-1R re-review on head
      457b4b4c08f962e8cd54dbaf9b7b805bd9846ed5; body says do not start FIF-2.
  - claim: >
      Defense D0R merged as an independent archaeology/architecture wave and did
      not start D1 in that PR.
    command: >
      GitHub.search_commits query='D0R entitled census architecture packets'
    result: >
      PR #5814 merged as 810d6ae0b4438072e9c52ae3f6a0520f5221d37b.
  - claim: >
      The current Seasonality research browser is not a commissioned API.
    command: >
      GitHub.fetch_file app/seasonality.py
    result: >
      Module explicitly says handlers only, unwired, registers nothing, and has
      no APIRouter or path decorator.
  - claim: >
      The semantic registry already separates the biocatalyst parent and Market
      Memory horizontal data plane.
    command: >
      GitHub.fetch config/mastermind_programs.yml and search for BioCatalyst and market-memory
    result: >
      biocatalyst owns event/clinical/seasonality intelligence; market-memory is
      a distinct cognitive architecture data plane.
unverified:
  - claim: Agent OS validation and repository CI pass on the final PR head.
    what_would_verify: >
      Run python3 scripts/agentos.py validate and allow the required GitHub checks
      on PR #5821 to conclude after this handoff commit.
  - claim: The Chairman accepts the federation ruling and sequencing.
    what_would_verify: >
      Explicit Chairman review/acceptance or amendment on PR #5821 before merge.
  - claim: Entitled BioCatalyst production-browser acceptance is complete after P0-C1.
    what_would_verify: >
      Real signed-in production browser/network evidence across the required modes,
      dossier, source receipt, typed states, and viewport/theme/language matrix.
  - claim: Market Memory recorded the first prospective W2C disposition and is ready for M0B.
    what_would_verify: >
      Durable opportunity row/disposition, production service evidence, and an
      updated Market Memory Agent OS handoff/workstream from its owner.
  - claim: Company Intelligence event_workspace.v1 is the correct user-facing composition for BCI.
    what_would_verify: >
      BCI-0B contract/product archaeology followed by BCI-0C real-data experience
      compositions and owner review.
unresolved:
  - Chairman acceptance or amendment of federation versus mega-merge.
  - Whether BCI remains permanently a subprogram under biocatalyst or earns a separate semantic program card after archaeology.
  - Exact separation among BCI market episode, Company Intelligence event workspace, current BCI context, and Market Memory retrieval packet.
  - Exact first real event family for BCI-1.
  - Entitled BioCatalyst P0 production acceptance after #5810.
  - Market Memory prospective W2C disposition and M0B readiness.
  - FIF-1R acceptance and first real production packet/service.
  - Cross-repository Neural Web contradiction eligibility hardening before BCI publishes decision-visible conflicts.
next_actions:
  - Review PR #5821 and accept or amend the federation ruling.
  - Let CI and Agent OS validation conclude; repair only architecture-record defects on this PR.
  - Merge BCI-0A only after acceptance; do not mark ready merely because checks are green.
  - Commission BCI-0B from research/BIOPHARMA_CYCLE_INTELLIGENCE_BCI_0B_ARCHAEOLOGY_HANDOFF_2026-08-16.md.
  - Require BCI-0B to stop without runtime code and return exact BCI-0C and BCI-1 handoffs.
do_not_redo:
  - Do not propose pausing every specialist program and merging it into BCI without overturning DEC:BIOPHARMA-FEDERATED-NOT-MEGA-MERGED.
  - Do not create a second clinical/regulatory collector or BioCatalyst truth store.
  - Do not build a general analogue/index/retrieval system inside BCI while Market Memory owns it.
  - Do not duplicate FIF, Capital Structure, Options, Earnings, or Company Intelligence truth and publication planes.
  - Do not create a BCI user-facing event workspace before adjudicating event_workspace.v1.
  - Do not treat app/seasonality.py as a live API or disconnected modules as commissioned engines.
  - Do not start BCI-1, a model, Prophet contribution, or UI from the architecture PR.
  - Do not create a second semantic program card before BCI-0B proves the need.
danger_areas:
  - The repository moves rapidly; every operator must fetch current main and live PRs before branching.
  - Documentation can drift into claims of completion. Require real production input and a real consumer.
  - BCI context-only contradictions could affect Portfolio indirectly through generic graph-conflict counts unless action eligibility is typed and enforced.
  - BioCatalyst alpha/asymmetry language overlaps BCI ownership; preserve P0/source/product recovery while routing market-response work to BCI.
  - Market Memory is partly operational and partly synthetic/specification. Do not call its learned/hybrid retrieval live without exact proof.
  - Event workspace, BCI episode, current context, and Market Memory packet are related but not interchangeable; blurring them will create duplicate stores.
---

# BCI-0A completion note

The architecture branch and draft PR now exist. The work performed here is a
program/ownership freeze, not the implementation of Biopharma Cycle Intelligence.

The recommended company architecture is federated:

```text
specialist domain truth and products
→ governed domain/context/episode packets
→ Market Memory historical experience
→ Neural Web context and contradiction
→ Prophet shadow contribution
→ evidence-gated authority, if ever earned
```

BioCatalyst and BCI remain within one biopharma family, but their jobs are distinct:
BioCatalyst owns clinical/regulatory truth and workflow; BCI owns market episodes,
expectations, response intelligence, peer read-through, memory profiles, and
prospective learning.

Market Memory, FIF, Defense, Earnings, Options, Terminal, Portfolio, Neural Web, and
Prophet remain independent owners. They continue through their own bounded accepted
waves and expose explicit ports when ready.

The next BCI action is BCI-0B archaeology only. No runtime implementation has been
authorized.
