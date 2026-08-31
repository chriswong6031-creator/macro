---
workstream: "WS:ALPHA-INTELLIGENCE-INTEGRATION"
session: sol/alpha-k2c-semantic-owner-repair-20260831
model: sol
ended_because: complete
mission: >
  Commission the already-adjudicated bounded post-merge K2-C semantic-owner repair
  alpha-k2c-semantic-owner-repair-20260828-sol-001 after fresh current-owner,
  current-path, open-PR and source-law archaeology. Preserve #6533/#6547 as durable
  implementation/raw-owner proof, eliminate false semantic positives, consume only
  canonical Data OS/Stock Identity and institutional/K2-B owner evidence, and remain
  typed non-positive wherever those owner seams are unresolved.
state_before: >
  Macro #6632 is merged as 7111e5950f1d9da48254e9ca67fe23a1e99f3c18 and is the
  controlling K2-C/K3-D dependency-state decision. K2-C remains PARTIAL / NOT
  SOL-ACCEPTED. #6533 implementation and #6547 production raw-acquisition receipts
  are on main. Current lib/institutional_13f_adapter.py still emits a recipe that
  manufactures mcx_filer_<CIK> / veh_filer_<CIK> as resolved epochs and maps
  investment_discretion=SOLE to discretionary/concentrated_discretionary_active;
  its top-level security_binding simultaneously remains unresolved with
  dataos_security_id=null. That combination is not an accepted semantic positive.
  Fresh current-main archaeology finds Data OS canonical identity owned by
  lib/dataos/identity.py plus data/reference/security_master.parquet and
  vendor_aliases.parquet. config/identity_seams.yml names no accepted CUSIP axis in
  that master, and repository search finds no current canonical CUSIP->SEC binding
  primitive. K2-B's canonical recipe contract owns manager_complex_epochs and
  vehicle_epochs, including decision_mode / vehicle_class / resolution semantics,
  but the K2-C adapter currently authors those semantics locally rather than reading
  truthful owner evidence. Open PR #6659 writes the security-master builder and must
  not be absorbed; open #6613 is records/architecture only and does not authorize
  K2-C to manufacture identity. No open PR/branch for this exact repair operation was
  found before this commission carrier was created.
changed:
  - path: agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-31-k2c-semantic-owner-repair-commission.md
    what: >
      Creates the one bounded job carrier for the post-merge repair already authorized
      by DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-STATE-2026-08-28. It does not change the
      #6632 decision, implementation code, Data OS, Stock Identity, K2-B, a provider,
      a RuntimeBinding, or production state.
verified:
  - claim: "K2-C is implemented and production raw acquisition is proven, but semantic positive is not Sol-accepted."
    command: "current Macro #6533, #6547, #6632 reconciliation"
    result: "#6533 and #6547 are merged; #6632 explicitly freezes K2-C as PARTIAL / NOT SOL-ACCEPTED."
  - claim: "Current K2-C authors manager/vehicle semantics locally."
    command: "read current main lib/institutional_13f_adapter.py"
    result: >
      build_recipe constructs mcx_filer_<CIK>, mce_filer_<CIK>_v1,
      veh_filer_<CIK>, vie_filer_<CIK>_v1 as resolved and _vehicle_decision derives
      discretionary/concentrated_discretionary_active from SOLE investment_discretion.
  - claim: "Current positive path can coexist with unresolved canonical security binding."
    command: "read current main lib/institutional_13f_adapter.py::run_pilot"
    result: >
      state is chosen from the K2-B compiled observation while security_binding is
      independently emitted as dataos_security_id=null /
      unresolved_no_authoritative_cusip_plane.
  - claim: "Data OS is the current exact security-identity owner and no K2-C-local identity plane is lawful."
    command: "current main lib/dataos/identity.py + config/identity_seams.yml + #6632"
    result: >
      Data OS owns SEC:/ISS:/listing identity over the canonical security master and
      vendor alias artifacts; #6632 requires K2-C exact binding to come from that owner.
  - claim: "No exact repair carrier existed before this branch."
    command: "GitHub PR and branch search for alpha-k2c-semantic-owner-repair-20260828-sol-001 / k2c-semantic-owner"
    result: "Only merged #6632 references the operation; no implementation branch/PR was present."
  - claim: "Open current owner work must not be overwritten."
    command: "current open-PR archaeology"
    result: >
      #6659 currently modifies scripts/build_security_master.py for a separate Data OS
      alias-refinement contract; this repair is forbidden to edit or absorb it. No open
      PR was found for lib/dataos/identity.py, lib/institutional_intelligence.py, or
      lib/institutional_13f_adapter.py itself.
unverified:
  - claim: "A current canonical owner can already resolve the requested 13F CUSIP to one exact Data OS SEC: identity."
    what_would_verify: >
      A current, owner-native Data OS/Stock Identity read that binds the exact CUSIP at
      the relevant valid/known-at cutoff to one admitted SEC: identity. If absent, this
      child must remain typed non-positive and return the missing owner primitive to Sol.
  - claim: "A current canonical institutional/K2-B owner can already supply truthful filer -> manager-complex -> vehicle epoch/class/decision-mode evidence for the real positive example."
    what_would_verify: >
      Current owner-native epoch/relationship records with exact provenance and clocks.
      Filer CIK, manager name, investment_discretion or adapter-authored IDs are not proof.
unresolved:
  - "K2-C acceptance still owes one real two-period positive owner -> K1 -> K2-B -> K2-C receipt after canonical security and manager/vehicle semantics are resolved."
  - "If either canonical owner primitive is absent, this child may close the false-positive bug but cannot self-author the missing owner; it must return OWNER_PRIMITIVE_REQUIRED to Sol."
  - "K5 remains dependency-held until separate K2-C and K3-D Sol acceptance."
next_actions:
  - >
    Keep this operation WAITING_CAPACITY / needs_placement with RECEIVER_BINDING_MODE
    CAPACITY_SELECTABLE and PREFERRED_AVENUE CTO Sol until a positively established
    eligible receiver exists. This records carrier is not a receiver assignment,
    worker-facing OPEN_PICKUP, ACK, watcher, or START.
  - >
    On lawful receiver assignment, the same operation must re-pin current protected
    Skillpack, current Macro main, #6632, all open PRs touching planned write/owner
    paths, and current Data OS/institutional owner contracts before START.
  - >
    Execute RED-first semantic falsifiers, then the smallest adapter-local repair.
    Do not widen into Data OS / Stock Identity / institutional owner implementation.
  - >
    If a required owner primitive is absent, return a typed BLOCKED
    OWNER_PRIMITIVE_REQUIRED with effect and exact missing owner seam. Sol will
    adjudicate any separate owner-specific child; do not create it from worker state.
do_not_redo:
  - "Do not recommission K2-C from scratch."
  - "Do not edit or rewrite merged #6533 or #6547 history."
  - "Do not build a K2-C-local CUSIP map, ticker resolver, security master, manager identity table, vehicle ontology, store, scheduler, cache, queue or retry plane."
  - "Do not derive vehicle class or decision mode from investment_discretion, voting authority, filer CIK, manager name, portfolio concentration or a heuristic label."
  - "Do not call an unresolved security binding positive merely because the CUSIP row was found in both 13F periods."
  - "Do not absorb #6659, #6613, K3-D, K5, Prophet/Fusion, ranking, grading, gate, sizing, signal or trading authority."
danger_areas:
  - >
    K2-B's current vehicleEpoch schema requires a concrete vehicle_class even when
    resolution_state is unresolved. Do not satisfy that shape by choosing a convenient
    class. If truthful owner semantics are unavailable, refuse before constructing a
    positive K2-B recipe rather than laundering missingness through a placeholder.
  - >
    A syntactically derivable SEC: id is not owner evidence. Data OS security_id() mints
    from a canonical listing key; a CUSIP cannot be converted to a listing key by guess,
    ticker/name lookup, OpenFIGI display context, or K2-C-local alias logic.
  - >
    Current Data OS owner work #6659 is live and must remain independently owned. Read
    current accepted owner state; do not edit that branch or make K2-C depend on its
    unmerged behavior.
---

# K2-C semantic-owner repair — bounded CTO Sol commission

**Operation key:** `alpha-k2c-semantic-owner-repair-20260828-sol-001`  
**Parent outcome:** `alpha-k2c-institutional-adapter-20260826-sol-001`  
**Workstream:** `WS:ALPHA-INTELLIGENCE-INTEGRATION`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Commission pickup:** `7ff9aa51990f0aab85119a124c2bb1600f005985`  
**Controlling dependency law:** `DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-STATE-2026-08-28` / merged #6632  
**Protected Skillpack observed by Sol:** `mastermindx-market-intelligence/Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc` (`mastermind.sol_skillpack.v1`, v1.0.1, bootstrap-major 1 compatible)  
**Routing state:** `WAITING_CAPACITY / needs_placement`  
**Receiver binding:** `CAPACITY_SELECTABLE`  
**Preferred avenue:** `CTO Sol`  
**Receiver:** none  
**ACK / WATCH / START:** none

This packet is the bounded job carrier authorized by the already-merged #6632
source-law decision. It is deliberately **not** a worker-facing delivery while no
positively established eligible receiver exists. A preferred avenue is not a
RuntimeBinding. Do not infer a numbered account, native session, ACK, watcher or START.

## Observable mission

Repair K2-C so the adapter can no longer emit a semantic positive unless **both** of
these are owner-proven for the same real two-period receipt and cutoff:

1. the 13F row's CUSIP is bound through canonical Data OS / Stock Identity truth to one
   exact admitted `SEC:` security identity; and
2. the filer/vehicle context is bound through canonical institutional/K2-B owner evidence
   to truthful manager-complex and vehicle epochs, including resolution state, vehicle
   class and decision mode.

If either owner seam is unresolved, return a deterministic typed non-positive state.
The mission is to make false positives impossible first; it is not permission to invent
the missing owner facts.

## Current falsifier — why the repair is required

Current `lib/institutional_13f_adapter.py` has two independent semantic defects:

- `_vehicle_decision()` maps `investment_discretion == SOLE` to
  `decision_mode=discretionary` plus `vehicle_class=concentrated_discretionary_active`,
  despite 13F investment discretion describing authority over a reported position rather
  than proving the vehicle's investment style/class;
- `build_recipe()` mints `mcx_filer_<CIK>` / `veh_filer_<CIK>` identities, marks those
  epochs resolved, and can feed a positive K2-B compile while `run_pilot()` separately
  emits `dataos_security_id=null / unresolved_no_authoritative_cusip_plane`.

The first repaired RED must demonstrate that this exact present behavior is rejected.
A SOLE 13F row plus unresolved canonical security/manager/vehicle owners must never yield
`PILOT_COMPILED` or `MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT`.

## Current owner archaeology — frozen no-rebuild boundary

### Security identity

Canonical authority is Data OS:

- `lib/dataos/identity.py`;
- `data/reference/security_master.parquet`;
- `data/reference/vendor_aliases.parquet`;
- `config/identity_seams.yml` as the declared registry.

Data OS IDs are `ISS:`, `SEC:` and canonical listing keys. Symbol is never identity.
The current registry does not establish CUSIP as an admitted alias axis of the master.
Therefore:

- do not derive a `SEC:` id from CUSIP syntax;
- do not infer listing key from issuer name/ticker;
- do not promote `engine/entity_resolver.py`, OpenFIGI, a display resolver or SEC row text
  into canonical identity authority;
- do not edit Data OS owner paths from this child.

If a fresh claim-time read discovers a canonical owner-native CUSIP->SEC primitive that
was not visible at commission time, use it only after exact owner/source-law review and
pin the owner receipt. Otherwise the security binding remains typed unresolved.

### Manager-complex / vehicle semantics

K2-B owns the canonical recipe contract in
`contracts/institutional_intelligence/manager_intent_recipe.v1.schema.json` and compiler
semantics in `lib/institutional_intelligence.py`. The contract distinguishes:

- `manager_complex_epochs` with `manager_complex_id`, `complex_epoch_id`, status,
  resolution state and decision mode;
- `vehicle_epochs` with `vehicle_id`, `vehicle_epoch_id`, manager/complex linkage,
  status, resolution state, decision mode and closed vehicle class.

K2-C may consume truthful owner-native values. It may not author them from filer CIK,
`investment_discretion`, portfolio shape, display labels or convenience defaults. If a
current institutional/K2-B owner does not supply a resolved epoch for the requested
cutoff, K2-C must remain non-positive.

## Frozen implementation ceiling

Expected writes are adapter-local unless fresh archaeology proves even these are
insufficient:

- `lib/institutional_13f_adapter.py`;
- `tests/test_institutional_13f_adapter_contract.py`;
- `research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md` only for
  exact repaired proof/limitation receipts.

A small adapter-local fixture may be added under the existing K2-C test namespace if
needed. **Do not modify** the Data OS security master/builder, identity seam registry,
Stock Identity, K2-B schema/compiler, institutional 13F owner store/catalog, #6659, or
another owner's contract without a new Sol adjudication.

If the schema makes truthful unresolved manager/vehicle semantics impossible, the
bounded solution is to refuse **before** constructing the K2-B positive recipe, not to
widen this child into a K2-B schema migration.

## Required RED -> GREEN proof

At minimum add discriminating tests for all of these:

1. **Unresolved security kills positive** — real/fixture two-period rows can be present
   and SOLE, but absent canonical `SEC:` binding must yield typed non-positive and must
   never reach an eligible-context positive.
2. **SOLE is not vehicle semantics** — `investment_discretion=SOLE` alone cannot select
   discretionary, vehicle class, or resolved manager/vehicle epochs.
3. **CIK is not manager-complex identity** — no `mcx_filer_<CIK>` / `veh_filer_<CIK>`
   synthetic resolved identity can support a positive.
4. **Owner-proven positive only** — if and only if a current canonical security binding
   and canonical manager/vehicle epochs are supplied through their real owner seam, the
   existing two-period share-change evidence can reach the K2-B compiler's positive path.
   If the repository currently lacks those owner primitives, record this discriminator as
   owner-blocked rather than faking a fixture that claims production availability.
5. **Adverse/refusal preserved** — missing filing, not-yet-knowable, ambiguous lineage,
   unsupported amendment, CUSIP grammar, missing security row, ambiguous row, units,
   raw-receipt mismatch and non-increasing periods keep their existing typed behavior.
6. **Authority stays false** — no score/rank/gate/size/originate/open-entry/trade authority
   changes anywhere in the receipt or K2-B recipe.
7. **Determinism** — identical owner receipts + owner semantic bindings + cutoff produce
   byte-identical canonical receipt identity.

The RED must fail on current accepted main for the intended semantic reason. Do not
weaken the K2-B compiler or alter tests merely to preserve the old positive fixture.

## Claim-time collision law

Immediately before START, and again before RESULT:

- fetch current Macro `main`;
- re-read #6632 and this commission from current source;
- census all open PRs that touch each planned write path or the owner paths being read;
- pay particular attention to Data OS #6659 and any successor identity/Stock Identity
  carrier;
- if a competing writer owns one planned K2-C path or source law has changed, return
  `BLOCKED CURRENT_OWNER_OR_PATH_COLLISION` with exact PR/head/path/hunk and effect.

Do not solve a collision by opening a second repair operation or changing another PR.

## Owner-primitive blocker contract

If the repaired false-positive seam is implementable but a real positive cannot be
completed because current owners expose no lawful CUSIP->SEC bridge and/or no truthful
manager/vehicle epoch evidence, return:

`BLOCKED OWNER_PRIMITIVE_REQUIRED`

with:

- `effect`: exact files/commits already changed by this child, or `NONE`;
- `missing_security_owner_primitive`: exact current Data OS/Stock Identity gap;
- `missing_manager_vehicle_owner_primitive`: exact institutional/K2-B gap;
- `proof`: current owner paths/receipts searched and why candidate substitutes are not
  authoritative;
- `proposed_owner`: the canonical existing owner that should receive a separate bounded
  mechanical/source child;
- no implementation of that owner child and no receiver selection.

Sol will adjudicate whether an owner-specific follow-on is mechanical enough for Terra
or requires a separate CTO Sol architecture turn.

## Return / acceptance gate

A worker RESULT is not K2-C acceptance. Return the same operation with:

- immutable branch/head and exact changed-file list;
- RED evidence and final GREEN evidence;
- exact current owner refs used;
- one real two-period owner-read receipt and one real adverse/refusal receipt;
- truthful statement of whether a real owner-backed semantic positive was reached;
- focused tests plus relevant contract/Agent OS/full CI;
- fresh open-PR path/hunk/semantic census;
- no unresolved blocker/major from independent adversarial review.

Sol will review the exact head under `REVIEW_RETURN`. If owner primitives remain absent,
Sol may accept the false-positive repair as a partial capability improvement while K2-C
stays `PARTIAL / NOT SOL-ACCEPTED`; K5 remains held.

## Non-goals / authority ceiling

No local identity plane, second institutional store, persistence, scheduler, cache,
retry, queue, worker lifecycle, manager classifier, vehicle classifier, scoring model,
ranking, grade, gate, size, trading action, UI, K5, Prophet/Fusion wiring, K3-D rewrite,
or source purchase. All authority remains false.
