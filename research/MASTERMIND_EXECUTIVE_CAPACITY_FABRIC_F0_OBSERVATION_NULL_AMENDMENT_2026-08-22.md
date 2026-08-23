# Executive Capacity Fabric F0 — presence, enablement, cooling, health and slot-completeness amendment

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md`  
**Status:** **SOL SOURCE-LAW CORRECTION / RECORDS ONLY**

This amendment closes false-negative and stale-health defects in the F0 slot schema before implementation. The parent draft made `present`, `enabled`, and `cooling.active` mandatory booleans even though current provider sources can be absent, unreadable, fail-soft, or semantically conflated. It also left open whether an absent/unknown capability could simply disappear from `slots`, which would make omission an undocumented fourth truth value, and it gave `health` no explicit freshness state. Those defects violate the same explicit-null/freshness law already applied to quota.

---

## 1. Nullable state is mandatory

The v1 slot retains the field names `present` and `enabled`, but each is now exactly:

```text
true | false | null
```

Semantics:

- `present=true` — the Provider Control owner actually observed the local capability/credential presence condition as satisfied;
- `present=false` — the owner actually observed that presence condition as absent on this host;
- `present=null` — presence is unknown because the source could not establish either truth value.

Likewise:

- `enabled=true` — current reviewed provider-control policy was successfully observed to enable the slot;
- `enabled=false` — current policy was successfully observed to disable the slot;
- `enabled=null` — enablement could not be established.

`false` is evidence, not a fallback value. A missing file, parser error, helper exception, ambiguous fail-soft return, incomplete source or unsupported join may not become `false` merely because a Python boolean needs a value.

When a direct current observation has no source-native timestamp, the freshness anchor for non-null `present`/`enabled` is the snapshot's exact `generated_at`. Old source evidence may not be stamped with `generated_at` to look current.

---

## 2. Canonical inventory is independent of presence/usability

`slots` is a projection of the producer's **reviewed capability inventory**, not a list of only currently usable providers.

For every provider/capability identity that CF1 supports and that is part of the reviewed local Provider Control inventory, exactly one `(host_ref, capability_id)` slot is emitted whether its dynamic state is present, absent, disabled, cooling, unhealthy or unknown.

Therefore:

```text
known inventory slot + credential observed absent   -> slot remains, present=false
known inventory slot + presence source unreadable  -> slot remains, present=null + degradation
known inventory slot + provider disabled           -> slot remains, enabled=false
known inventory slot + executable missing          -> slot remains; presence is independent; health carries not_installed/equivalent
capability not in reviewed producer inventory      -> no slot
```

**Omission is not absence.** A consumer may interpret a missing slot only as “this producer snapshot does not define that `(host_ref, capability_id)` inventory identity.” It may never infer `present=false`, `enabled=false`, exhausted, unavailable or deleted merely from omission.

### 2.1 Inventory source

CF1 must derive the supported inventory from stable Provider Control definitions/configuration that do not themselves depend on credential usability. It must not construct inventory from dynamic helpers whose contract returns only present/usable accounts.

For the initial existing-provider CF1 vertical, acceptable candidate sources include the current reviewed static/configured capability definitions already owned by Provider Control, such as the Claude/Codex/DeepSeek capability IDs and reviewed capability-manifest rows actually used by the producer. The exact inventory reader and supported set are frozen by the CF1 implementation review from the current code/data-flow census.

Hard rules:

- do not use `discover_present_keys()` as the inventory list;
- do not use Codex `available_accounts()` as the inventory list;
- do not invent a second provider account numbering scheme;
- do not synthesize infinite/undeclared Codex slots merely because capability-id naming is patterned;
- if an inventory/config source that is required to enumerate a supported class is malformed, unreadable or internally contradictory, fail/degrade that class visibly rather than silently shrinking the array;
- inventory identity must not depend on the current quota/cooling/health result;
- adding/removing a reviewed supported capability identity is semantic and therefore changes the snapshot hash.

A provider configuration that intentionally declares three Codex account homes but only one has an attached login should still be able to project the reviewed configured slots independently of whether `available_accounts()` currently deems each one usable. The implementation review must prove the precise configured-slot law from the then-current Codex owner code without opening credential contents.

---

## 3. Presence, enablement and health stay orthogonal

The following are all lawful and distinct:

```text
present=true,  enabled=false, health=unknown
present=true,  enabled=true,  health=unavailable/not_installed
present=false, enabled=true,  health=unknown
present=null,  enabled=true,  health=unknown
```

Rules:

- disabling a provider does not make its credential/account absent;
- a missing executable does not make an attached credential absent;
- a present credential does not prove authentication success;
- `present=false` on one host says nothing about another host;
- health may not be inferred from presence/enablement unless a reviewed health observation independently proves it.

Current source helpers that intentionally answer **usability** rather than presence must not be reused as if they answered this field. In particular:

- Claude `discover_present_keys()` currently applies enablement filtering/fallback;
- Codex `available_accounts()` currently combines provider enablement, executable readiness and credential presence.

CF1 may add narrow read-only observation helpers inside those existing provider owners to expose the orthogonal facts. Existing dispatch behavior remains unchanged.

---

## 4. Health is freshness-aware

The parent health shape is superseded. The closed v1 health object is:

```json
{
  "state": "available",
  "error_class": null,
  "observed_at": "2026-08-22T22:00:00Z",
  "stale_after": "2026-08-22T22:10:00Z",
  "evidence": "exact",
  "source_kind": "local_observation",
  "freshness": "fresh"
}
```

`state` remains:

```text
available | degraded | unavailable | unknown
```

`error_class` remains:

```text
null | auth | usage_limit | timeout | not_installed | unsupported | transport | error
```

`evidence`:

```text
exact | provider_reported | estimated | unknown
```

`source_kind`:

```text
local_observation | provider_attempt | provider_api | local_ledger | config | error_signal | unknown
```

`freshness`:

```text
fresh | stale | unknown
```

`observed_at` and `stale_after` are ISO-8601 timestamps or `null`.

Rules:

- `state=unknown` because there is no usable health observation requires `observed_at=null`, `stale_after=null`, `evidence=unknown`, `source_kind=unknown`, `freshness=unknown`, plus a safe degradation row;
- an explicit health observation that itself yields an unknown/unclassifiable state may carry its real `observed_at`, but it still must not be promoted to `available`;
- a stale historical success remains `state=available` only as the historical observed state and MUST carry `freshness=stale`; later placement policy may display it but may not treat it as fresh availability;
- `stale_after` exists only when the source class has a reviewed freshness budget; otherwise `freshness=unknown` unless the observation is a projection-time local fact whose freshness anchor is the snapshot `generated_at` under an explicitly reviewed rule;
- `exact` describes the exact local observation/state, not provider entitlement truth;
- a provider attempt/response classification remains `provider_reported` or the reviewed source evidence class; do not upgrade it because the local ledger persisted it.

CF2 may hard-exclude or positively prefer based on health only under its later reviewed policy and only when the health freshness/evidence permits it. A stale/unknown historical success cannot silently outrank a fresh known candidate.

---

## 5. Cooling active is nullable

`cooling.active` is amended from boolean to:

```text
true | false | null
```

Semantics:

- `true` — current Provider Control cooling is observed active;
- `false` — the relevant cooling source was successfully observed and proves no active cooling state;
- `null` — cooling could not be established.

When `active=null`:

```text
kind = null
reset_at = null
evidence = "unknown"
observed_at = null
```

and the top-level `degraded` array must contain a bounded safe row identifying the affected slot/source class.

When `active=false`, `evidence` must describe why that negative is trusted. For a complete local policy/cooling ledger observation, `exact` may describe the **local cooling state only**; it never upgrades provider entitlement/reset truth.

A fail-soft helper returning `False` after an exception is not an observed negative and must normalize to `null` unless an independent complete observation exists.

---

## 6. No-observation quota and last-outcome shapes

The parent quota/last-outcome vocabularies remain, with these explicit null rules.

### Quota

For a known horizon with **no usable usage observation**:

```text
limit = null
used = null
remaining = null
used_percent = null
reset_at = null
observed_at = null
stale_after = null
evidence = unknown
source_kind = unknown
freshness = unknown
```

Static horizon-definition facts that are independently known (for example a reviewed `horizon`, `metric`, `window_type` or fixed `duration_seconds`) may remain populated; they are not usage observations.

An absent/unreadable ledger or provider telemetry source is not a zero. A fail-soft `0` from a helper whose source completeness is not proven normalizes to `null`/unknown.

### Last outcome

`last_outcome` remains:

```json
{
  "class": "success",
  "observed_at": "2026-08-22T22:00:00Z"
}
```

but `observed_at` is nullable. With no known prior outcome:

```text
class = unknown
observed_at = null
```

If a real outcome exists but cannot be safely classified, `class=unknown` may carry its real source timestamp plus a degradation row. The producer must never stamp an absent/old outcome with current `generated_at` merely to make it recent.

---

## 7. Unknown source quality must be visible

Whenever a required slot fact is null/unknown because its source was absent, corrupt, unreadable, incomplete or semantically ambiguous, CF1 must emit a safe structured `degraded` row. The CF1 implementation review freezes the bounded code vocabulary, but it must distinguish at least the meaningful classes needed to avoid false negatives, such as:

```text
PROVIDER_PRESENCE_UNKNOWN
PROVIDER_ENABLEMENT_UNKNOWN
PROVIDER_COOLING_UNKNOWN
PROVIDER_BUDGET_UNKNOWN
PROVIDER_HEALTH_UNKNOWN
PROVIDER_INVENTORY_UNKNOWN
SOURCE_CORRUPT
SOURCE_UNREADABLE
```

These codes expose observation quality; they do not become provider health or Executive Job status. Raw exception text, credential refs/values, private paths, usernames, hostnames and provider response bodies are forbidden.

---

## 8. CF1 discriminating tests

CF1 acceptance must prove at minimum:

1. known configured slot with credential absent remains in `slots` with `present=false`;
2. known configured slot with unreadable presence source remains in `slots` with `present=null` and degradation;
3. installed-but-disabled Claude credential => `present=true`, `enabled=false`;
4. Codex credential present + provider disabled => `present=true`, `enabled=false` without requiring binary execution;
5. Codex credential present + enabled + executable missing => presence remains true while health reports `not_installed` or the accepted equivalent;
6. unreadable/corrupt presence source => `present=null`, never false;
7. unreadable enablement source => `enabled=null`, never true via fail-open fallback;
8. fail-soft `is_cooling()` error/ambiguous source => `cooling.active=null`, never false;
9. complete cooling source with no active cooldown => `active=false` with trustworthy local evidence;
10. no health source => health unknown with null timestamps/unknown evidence/freshness and degradation;
11. historical success beyond its reviewed freshness deadline remains stale and is never serialized as fresh merely because the snapshot is new;
12. no quota observation => all dynamic usage/reset timestamps/numbers null and evidence/source/freshness unknown;
13. no last outcome => class unknown, observed_at null;
14. every null source-quality state emits the appropriate safe degraded row;
15. deleting a slot from the supported inventory changes semantic snapshot identity and is not equivalent to `present=false`;
16. changing true/false/null or health freshness/evidence changes the semantic snapshot hash;
17. dynamic helper results cannot add an undeclared capability slot or remove a declared one;
18. no normalizer test needs or exposes a real credential value.

---

## 9. Precedence

This amendment supersedes only parent F0 language/examples that require boolean `present`, boolean `enabled`, or boolean `cooling.active`; omit health freshness/evidence/source quality; require non-null health/last-outcome timestamps when no observation exists; could interpret a fail-soft false/zero/empty helper result as a known negative without source-quality proof; or could treat omission from `slots` as evidence that a known capability is absent/unusable.

All other F0 ownership, identity, semantic-hash, freshness, placement, acquisition, RF1/HF1/MH1 and no-rebuild rulings remain unchanged.
