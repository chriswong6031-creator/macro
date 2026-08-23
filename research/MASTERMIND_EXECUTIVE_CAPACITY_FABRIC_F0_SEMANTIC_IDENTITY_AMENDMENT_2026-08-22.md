# Executive Capacity Fabric F0 — semantic identity, freshness and acquisition amendment

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md` and `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_PLACEMENT_AMENDMENT_2026-08-22.md`  
**Status:** **SOL SOURCE-LAW CORRECTION / RECORDS ONLY**  
**Current protected Mastermind reviewed:** `e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`  
**Current Macro material-source review:** provider-control ownership and producer inputs remain materially unchanged from the F0 pickup through the current reconciliation; unrelated press-wire/data churn is explicitly non-semantic.

This amendment corrects load-bearing semantic-identity, freshness, credential-boundary and cross-repo acquisition defects found during Sol's pre-merge adversarial review. It does not change provider-capacity ownership, quota evidence vocabularies, the closed Phase 1F-C placement object, RF1, HF1 or MH1.

---

## 1. Defect: whole-repository SHA is not capacity semantics

The parent F0 draft put the current Macro repository commit inside the `producer` object and then made that field part of `snapshot_hash`.

Macro is a high-churn monorepo. Unrelated marketing, press-wire, rendered-site, research-vault and market-data commits advance `main` many times per hour without changing provider-capacity code or evidence. Therefore the original rule would produce:

```text
identical provider evidence
+ identical provider-capacity implementation
+ unrelated press-wire commit
=> different snapshot_hash
```

That violates F0's own acceptance law that unchanged source evidence should retain the same semantic identity across invocations. It would also make later Executive claim receipts look like capacity decisions changed when only unrelated repository history moved.

**Ruling:** whole-repository Git revision is audit provenance, not provider-capacity semantics.

---

## 2. Revised closed top-level shape

The canonical F0 top-level object is amended to:

```json
{
  "schema": "mastermind.provider_capacity.v1",
  "generated_at": "2026-08-22T22:00:00Z",
  "producer": {
    "repository": "mastermindx-market-intelligence/macro",
    "program": "shared-ai-provider-control",
    "implementation_id": "provider-capacity-v1",
    "implementation_version": 1
  },
  "audit": {
    "repository_commit": "<40-hex>"
  },
  "snapshot_hash": "<64-lower-hex>",
  "slots": [],
  "degraded": []
}
```

No extra top-level keys are accepted by a strict consumer.

Rules:

- `producer.repository`, `producer.program`, `producer.implementation_id` and `producer.implementation_version` are semantic contract identity.
- `audit.repository_commit` is the exact Git commit from which the producer executed. It is retained for forensic provenance and debugging but is **not** capacity semantics.
- `audit` is closed in v1 to exactly `repository_commit`. Do not turn it into a dumping ground for hostnames, worktree paths, users, branch names, credentials or process details.
- A normalization/contract behavior change that is not byte-compatible with the accepted v1 law requires an explicit reviewed `implementation_version` change or a new schema; silently changing semantics under the same implementation identity is forbidden.

---

## 3. Revised semantic hash law

To compute `snapshot_hash`:

1. validate the complete strict snapshot first;
2. make a semantic copy;
3. remove exactly top-level `generated_at`, `snapshot_hash` and `audit`;
4. canonicalize the remaining object using UTF-8 JSON, sorted keys, separators `(',', ':')`, `ensure_ascii=false`, and reject NaN/Infinity;
5. compute lowercase SHA-256 over those canonical bytes.

Nothing else is omitted.

Therefore:

- unrelated Git commits do not churn semantic identity;
- a changed provider/capability/host identity changes the hash;
- changed present/enabled/health/cooling/quota/outcome/degraded evidence changes the hash;
- changed source observation timestamps that are part of those evidence objects change the hash;
- changed producer contract identity/version changes the hash;
- a different wall-clock projection time alone does not change the hash.

CF1 tests must include an explicit mutation proving that changing only `audit.repository_commit` leaves `snapshot_hash` unchanged while changing `producer.implementation_version` changes it.

---

## 4. Freshness is distinct from semantic identity

Two snapshots may lawfully have the same semantic hash but different `generated_at` values. That means they have the same semantic capacity contents but were projected at different times.

This is intentional, but it creates a binding requirement for later Executive use.

### Projection-time observations

Facts such as direct local presence/enablement checks are observed by the producer during the projection. Where no more specific upstream observation timestamp exists, their freshness anchor is the snapshot's exact `generated_at`.

Facts with source-native timestamps (`health.observed_at`, cooling observations, quota `observed_at` / `stale_after`, last outcome time) retain those source timestamps as semantic evidence. CF1 may never stamp an old source observation with the current projection time merely to make it look fresh.

### CF2-F binding requirement

The later claim-evidence source-law freeze must bind **both**:

```text
capacity_snapshot_hash
capacity_snapshot_generated_at
```

plus the accepted selected-slot/policy/evidence fields.

A historical claim cannot be reconstructed from `snapshot_hash` alone because the same semantic contents can be freshly re-observed at a later projection time. Replay uses the persisted exact pair; it never reruns capacity selection against current time/provider state.

If the landed v4 `JOB_CLAIMED` receipt cannot carry this pair atomically under the reviewed replay/privacy law, stop and return to Sol. Do not widen `placement_snapshot_json`, create a second placement Event/ledger, or invent schema v5 by convenience.

---

## 5. CF1 acceptance additions

In addition to the parent F0 CF1 packet, CF1 must prove:

1. two invocations over unchanged semantic provider evidence but different wall-clock `generated_at` values produce the same `snapshot_hash`;
2. changing only `audit.repository_commit` leaves the semantic hash unchanged;
3. changing `producer.implementation_version` changes the semantic hash;
4. changing a source observation timestamp that is semantic evidence changes the hash;
5. a direct projection-time presence observation is not represented as older/newer than `generated_at` unless a real source timestamp exists;
6. stale source evidence stays stale after projection and is never refreshed by serialization;
7. the machine/operator consumer displays or exposes both `snapshot_hash` and `generated_at` so later freshness policy has an auditable input;
8. no Git path, hostname, username, credential, token, cookie, provider-home path or private process identity appears in `audit` or any other public field.

---

## 6. Cross-repo acquisition is a separate CF2-F gate

CF1's real stdout/CLI consumer proves that the normalized contract is usable. It does **not** prove that the Executive service can later obtain the same snapshot safely.

Current systems deliberately run under different principals and environments. The Executive service must not assume it can read Macro's raw ledgers, provider homes, secret-bearing environment, or capability-manifest secret refs merely because the repositories live on the same machine.

Therefore CF1 does not freeze an Executive transport. Before CF2-I, CF2-F must review and freeze the smallest secret-free acquisition seam that preserves the Provider Control → Executive ownership boundary.

Candidate families, in preference order if available at the time, are:

1. an already-existing reviewed local Provider Control read endpoint that returns exactly `mastermind.provider_capacity.v1` and grants no mutation; or
2. a bounded subprocess/executable contract that invokes the reviewed Macro producer under the appropriate provider-control principal/environment and returns only strict JSON stdout.

Neither candidate is accepted merely by appearing in this document. CF2-F must verify the then-current estate and choose one.

Hard rules:

- Executive must not import floating Macro Python modules as the cross-repo contract;
- Executive must not parse raw `key_ledger`, budget files, provider-home directories, auth files, environment secrets or provider responses itself;
- do not add a long-lived capacity daemon, database, queue or second provider-control service just to make the bridge convenient unless a separate architecture ruling proves it necessary;
- acquisition timeout/unavailability yields unavailable/unknown capacity optimization, never permission to read secret/raw provider state as a fallback;
- the producer remains the authority for normalization/evidence classification; Executive validates the strict returned contract but does not reinterpret source rows;
- the acquisition receipt used by CF2-F must bind at least the exact `snapshot_hash`, exact `generated_at`, producer contract identity/version, and non-semantic `audit.repository_commit` used for that historical decision;
- if the acquisition principal/host cannot lawfully observe a configured slot, that slot is unavailable to that acquisition path; do not copy provider credentials across principals/hosts to make it visible.

This keeps CF1 independently useful and no-write while preventing CF2 from quietly becoming a raw cross-repo provider-state reader.

---

## 7. Credential-access boundary inside Provider Control

`secret-free projection` describes the contract boundary, not a claim that the existing Provider Control implementation never touches a credential value internally.

Some current owning helpers establish presence under existing Provider Control authority. For example, current Macro helper paths may test configured secret presence or inspect an attached-login home while returning only safe capability IDs/booleans/typed observations. That existing authority is not transferred to Capacity Fabric or Executive OS.

CF1 must follow this exact split:

```text
existing Provider Control helper
  may perform its already-reviewed credential/presence mechanics
        |
        | secret-free typed return only
        v
engine/provider_capacity.py normalizer
  NEVER receives/opens/serializes the credential value
        |
        v
mastermind.provider_capacity.v1
```

Rules:

- the new CF1 normalizer must not directly call a secret store to obtain token/key/password/cookie values;
- it must not open provider auth files, Codex auth JSON, browser cookies, provider-home secret material or raw credential-bearing environment values;
- it may consume existing reviewed Provider Control helper results whose public return contract is already secret-free, even when the owning helper internally tests credential presence under its existing principal;
- CF1 must not widen which OS principal, process, host or repository can access the underlying credential merely to populate `present`/health fields;
- if a safe existing helper cannot establish a field, emit unknown/degraded evidence rather than adding a new secret read to the normalizer;
- tests should inject typed helper fixtures and include an import/AST redline proving `engine/provider_capacity.py` contains no direct credential-store/auth-file access path;
- later Executive acquisition must execute through the reviewed Provider Control acquisition seam. The Executive principal does not inherit Provider Control credentials.

This clarifies the parent CF1 non-goal: **no new direct provider-credential read in the Capacity Fabric normalizer**. It does not outlaw existing provider-control credential mechanics that already own provider authentication/presence and return a secret-free observation.

---

## 8. No change to ownership or later gates

This amendment changes no owner:

```text
Shared Provider Control -> provider/capacity observation truth
Model Router            -> task/model suitability
Executive OS             -> final eligible worker claim/lifecycle
Worker harness           -> provider-native execution
Agent OS / Control Room   -> organizational/product projection
```

It also does not accelerate later waves. CF1 remains no-write and existing-provider-only. Phase 1F-C still owns schema v4. CF2-F remains mandatory before capacity-aware placement. RF1 and HF1 remain mandatory before heterogeneous providers share production routes, and MH1 remains mandatory before a second physical Mac becomes a real Executive execution host.

This amendment supersedes only the parent F0 rules that made whole-repository commit identity semantic, implied `snapshot_hash` alone was sufficient freshness evidence for a future Executive claim, implied CF1's local CLI proof automatically defined the later Executive acquisition transport, or could be read as requiring the new Capacity Fabric normalizer itself to gain direct access to provider credentials.
