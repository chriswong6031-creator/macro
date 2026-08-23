# Executive Capacity Fabric F0 — semantic identity and freshness amendment

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md` and `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_PLACEMENT_AMENDMENT_2026-08-22.md`  
**Status:** **SOL SOURCE-LAW CORRECTION / RECORDS ONLY**  
**Current protected Mastermind reviewed:** `e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`  
**Current Macro material-source review:** provider-control ownership and producer inputs remain materially unchanged from the F0 pickup through the current reconciliation; unrelated press-wire/data churn is explicitly non-semantic.

This amendment corrects a load-bearing semantic-identity defect found during Sol's pre-merge adversarial review. It does not change provider-capacity ownership, quota evidence vocabularies, the closed Phase 1F-C placement object, RF1, HF1 or MH1.

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

## 6. No change to ownership or later gates

This amendment changes no owner:

```text
Shared Provider Control -> provider/capacity observation truth
Model Router            -> task/model suitability
Executive OS             -> final eligible worker claim/lifecycle
Worker harness           -> provider-native execution
Agent OS / Control Room   -> organizational/product projection
```

It also does not accelerate later waves. CF1 remains no-write and existing-provider-only. Phase 1F-C still owns schema v4. CF2-F remains mandatory before capacity-aware placement. RF1 and HF1 remain mandatory before heterogeneous providers share production routes, and MH1 remains mandatory before a second physical Mac becomes a real Executive execution host.

This amendment supersedes only the parent F0 rules that made whole-repository commit identity semantic or implied `snapshot_hash` alone was sufficient freshness evidence for a future Executive claim.
