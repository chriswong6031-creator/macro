# Executive Capacity Fabric F0 — presence, enablement, cooling and slot-completeness amendment

**Date:** 2026-08-22  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md`  
**Status:** **SOL SOURCE-LAW CORRECTION / RECORDS ONLY**

This amendment closes false-negative defects in the F0 slot schema before implementation. The parent draft made `present`, `enabled`, and `cooling.active` mandatory booleans even though current provider sources can be absent, unreadable, fail-soft, or semantically conflated. It also left open whether an absent/unknown capability could simply disappear from `slots`, which would make omission an undocumented fourth truth value. Both defects violate the same explicit-null law already applied to quota.

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

## 4. Cooling active is nullable

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

## 5. Unknown source quality must be visible

Whenever a required slot fact is `null` because its source was absent, corrupt, unreadable, incomplete or semantically ambiguous, CF1 must emit a safe structured `degraded` row. The CF1 implementation review freezes the bounded code vocabulary, but it must distinguish at least the meaningful classes needed to avoid false negatives, such as:

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

## 6. CF1 discriminating tests

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
10. every null source-quality state emits the appropriate safe degraded row;
11. deleting a slot from the supported inventory changes semantic snapshot identity and is not equivalent to `present=false`;
12. changing true/false/null changes the semantic snapshot hash;
13. dynamic helper results cannot add an undeclared capability slot or remove a declared one;
14. no normalizer test needs or exposes a real credential value.

---

## 7. Precedence

This amendment supersedes only parent F0 language/examples that require boolean `present`, boolean `enabled`, or boolean `cooling.active`; could interpret a fail-soft false/zero/empty helper result as a known negative without source-quality proof; or could treat omission from `slots` as evidence that a known capability is absent/unusable.

All other F0 ownership, identity, semantic-hash, freshness, placement, acquisition, RF1/HF1/MH1 and no-rebuild rulings remain unchanged.
