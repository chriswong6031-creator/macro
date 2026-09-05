---
workstream: WS:EXECUTIVE-CAPACITY-FABRIC
session: claude/autonomy-capacity-contract-20260905-01a06f72
model: codex
ended_because: complete
mission: >
  Persist the accepted Capacity revision-2 contract in the existing Capacity ownership decision
  and leave a cold-stranger continuation without commissioning source, a migration, provider work
  or production measurement.
state_before: >
  The existing F0 ownership decision named Macro Shared Provider Control, Model Router and
  Executive Runtime as the separate capacity, suitability and lifecycle owners, but the accepted
  revision-2 measurement-boundary and Runtime-feasibility design had no Capacity-specific
  canonical continuation after the portfolio acceptance carrier merged.
changed:
  - path: agentos/decisions/DEC-EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT.md
    what: >
      Added hash-pinned revision-2 and source-map evidence plus a design-only addendum that keeps
      F0 ownership intact, records original-command reconciliation and measurement non-interference,
      bounds initial scope and preserves no-rebuild and production-proof limits.
  - path: agentos/handoffs/EXECUTIVE-CAPACITY-FABRIC-2026-09-05-FAIRNESS-CONTRACT-ACCEPTED.md
    what: >
      Added the Capacity-specific continuation for the accepted specification, unresolved source
      facts, exact future commissioning prerequisites and no-repeat boundaries.
verified:
  - claim: "This two-path publication begins at protected Macro main c70ee13f855d920057bb07fa5ef948cd656b77d0."
    command: "git rev-parse HEAD origin/main"
    result: "Both HEAD and origin/main returned c70ee13f855d920057bb07fa5ef948cd656b77d0 before the records-only edits."
  - claim: "The accepted revision-2 package is the supplied exact byte sequence."
    command: "shasum -a 256 /Users/chriswong/Documents/Cluade/exec-prestage-receipts/capacity-h0-census-20260905-01a06f73/CAPACITY-RUNTIME-CONTRACT-PROPOSED-REVISION-2.md"
    result: "SHA-256 returned 7368ad403cde6917026636bb60c4e67ff5c7f8a6e03a55fa3a48b311dd3a4e42."
  - claim: "The fairness source map is the supplied exact byte sequence."
    command: "shasum -a 256 /Users/chriswong/Documents/Cluade/exec-prestage-receipts/capacity-h0-census-20260905-01a06f73/CAPACITY-FAIRNESS-SOURCE-MAP.md"
    result: "SHA-256 returned 764874309c48ca92c9b67726d51ba1de58e585cbaa9b778eb55ad80048880975."
  - claim: "The current protected Mastermind source pin is 0d9cf2f58f9a6a1fe895d5d199abc18735201e24 and the inspected Runtime/Capacity paths are unchanged from the revision's a344 feasibility pin."
    command: "git -C /Users/chriswong/Documents/Cluade/Mastermind rev-parse origin/master && git -C /Users/chriswong/Documents/Cluade/Mastermind diff --name-only a3440f21a0d6df7666bd9ed9f3b02385dac23588..0d9cf2f58f9a6a1fe895d5d199abc18735201e24 -- control_plane/executive_runtime.py control_plane/executive_service.py control_plane/executive_placement_selection.py control_plane/executive_placement_commitment.py control_plane/executive_supervisor.py control_plane/executive_backup.py"
    result: >
      origin/master returned 0d9cf2f58f9a6a1fe895d5d199abc18735201e24 and the constrained path diff
      returned no paths. This is source-procedure continuity only, not implementation, owner release
      or production proof.
  - claim: "The preceding portfolio carrier is protected Macro history, not an external comment or local packet."
    command: "git show --no-patch --format='%H%n%P%n%s' c70ee13f855d920057bb07fa5ef948cd656b77d0"
    result: >
      The current protected tip has parent 8e49149233713f0983a9ebfdac6f437857dc8bcf; that merge
      is the protected carrier for the two portfolio handoffs and is distinct from this Capacity
      specification publication.
  - claim: "No open Macro pull request owned either target path before this draft began."
    command: "gh pr list --repo mastermindx-market-intelligence/macro --state open --limit 100 --json number,headRefName,files"
    result: >
      Filtering the returned file lists for the existing Capacity decision and this new handoff
      returned an empty array. The root-owned PR #6854 had already merged and was not widened.
unverified:
  - claim: "Revision 2 has been implemented in the canonical Executive Runtime."
    what_would_verify: >
      A separately authorized exact Runtime commission must fresh-pin protected Mastermind,
      re-prove path ownership and collisions, implement the bounded source change under the
      existing owners, and pass its focused hostile tests and exact-head review.
  - claim: "A first-runnable clock, complete comparable cohort and accepted realm independence currently exist."
    what_would_verify: >
      Existing Runtime, Capacity and source owners must establish the required source-owned
      Job/Event, cohort and realm proof through the separately accepted implementation; current
      source mapping marks the required facts unavailable.
  - claim: "Capacity fairness has production proof."
    what_would_verify: >
      Production must measure independently authorized work through canonical Runtime after an
      accepted implementation, including complete epochs, restart/adverse cases and the required
      realm and bypass evidence.
unresolved:
  - "Current source does not expose first-runnable eligibility history, a complete historical comparable cohort, allocation weight/resource profile, or accepted eligible-realm independence proof."
  - "An exact Runtime commission still needs current protected-source pinning, existing-writer and shared-path collision proof, implementation-owner feasibility, and a separate START."
  - "The proposed typed no-Attempt supervisor propagation overlaps the active HF owner path and must use its eventually protected version or an explicit exact-path release."
next_actions:
  - >
    Before any implementation, the existing Runtime owner must re-read current protected Mastermind,
    the same-SHA source law and current path/process/PR occupancy, then return an exact bounded
    commission or a collision hold. This handoff grants neither source authority nor a writer release.
  - >
    If separately commissioned, retain existing Event and RuntimeStore ownership: reconcile original
    command C before transaction A and in transaction B; persist the actual C claim or proven
    noncommit; leave measurement failure as coverage/denominator UNKNOWN rather than execution refusal.
  - >
    Use the existing offline migration/backup owner for M5 and the existing Runtime/COO/service/
    supervisor propagation path for typed no-Attempt outcomes. Require explicit backup, restore,
    quarantine and recovery proof before any production conclusion.
  - >
    Production may evaluate only independently authorized work after source acceptance. It must retain
    a complete frozen cohort and whole-epoch denominator, report every bypass, preserve censored
    history, and refuse global graduation on missing comparable paths or incomplete evidence.
do_not_redo:
  - "Do not mint a second Capacity decision, strategic state, scheduler, lifecycle, realm registry, quota/account store, collector, controller or retry/failover plane."
  - "Do not use Job creation/update time, Attempt start time, a C1 worker tuple, a partial event history or source freshness as a substitute for first-runnable eligibility or the complete fairness cohort."
  - "Do not turn epoch opening, measurement admission, instrumentation failure or UNKNOWN coverage into a refusal of ordinary otherwise-authorized execution."
  - "Do not treat this records-only acceptance, the local external package, the #6854 merge, CI, a source merge, an installed host, provider evidence or a manual sample as production fairness proof."
  - "Do not reopen the F0 ownership split: Provider Control owns provider facts, Model Router owns suitability, and Executive Runtime owns Job/Attempt/Worker/Event lifecycle and any later mutation."
danger_areas:
  - >
    The events table has one command identity per outcome. A committed allocation must extend the
    existing original-command JOB_CLAIMED; a second same-command observation event, changed replay
    request, retroactive admission or duplicate Attempt can corrupt causality.
  - >
    Ordinary execution remains lawful outside a measurement epoch. An implementation that returns
    fake WAITING_CAPACITY, omits a result, hides an in-scope command or rewrites a closed epoch would
    turn a measurement concern into a new control plane.
  - >
    An M5 change is an offline Runtime/backup operation. Startup migration, uncertain commit,
    changed writer census, failed restore proof or altered receipts must preserve the existing
    quarantine boundary instead of retrying, downgrading or silently resuming writers.
  - >
    Provider homes, tokens, cookies, account identifiers, raw host addresses and private source
    evidence must not enter AgentOS. Realm proof needs existing accepted producing-owner evidence,
    not self-authored JSON, aliases, browser state, executable presence or hash self-consistency.
decisions:
  - DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT
---

## §0 State — accepted specification, no execution effect

The Capacity revision-2 design is now discoverable through the existing F0 ownership decision.
It is a bounded `SPEC_ONLY` / `PARTIAL` contract: no Runtime source change, database migration,
Worker claim, provider action, host action, epoch, measurement run or production acceptance was
created by this publication.

## §1 What is left — in order

1. The existing Runtime owner must obtain a separate exact commission only after fresh protected-source,
   owner, collision and `START` proof. This record does not satisfy any of them.
2. That commission must make the contract source-real through existing Runtime Event, Job, Attempt,
   migration, backup and supervisor owners, including strict original-command replay and typed
   no-Attempt propagation.
3. Production may later assess the implementation only through canonical Runtime evidence from
   independently authorized work. Missing source facts, incomplete epochs and censored histories stay
   `UNKNOWN`; they cannot support a global fairness conclusion.

## §2 What will bite you

The design distinguishes the source-owned first-runnable transition from current eligibility,
capacity availability, Attempt start and observation time. It also separates a durable allocation
result from provider start/acknowledgement and semantic completion. Conflating any of those pairs
creates stale age, duplicate command or false production claims.

## §3 What was decided and found

`DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT` now records the accepted revision-2
design boundary while preserving the original ownership decision. The source map remains a
hash-pinned finding of unavailable source facts, not a substitute implementation.

## §4 Not in scope — do not adopt

This publication does not amend the Capacity workstream state, release a Runtime or HF writer,
approve C2/generated-ID/role-null expansion, change existing dispatch priority or C1 tie law,
authorize a provider/host operation, or create a new measurement or control-plane service.
