# Oracle Red Queen Interface Contract

**Version:** `1.2.0` (see Version Policy below)
**Effective:** 2026-07-04
**Audience:** Red Queen session and any downstream consumer of `oracle_state.json`.
**Source:** `engine/oracle/contract.py` — this document is the human-readable companion; the machine-enforceable rules live in code.

---

## What `oracle_state.json` is

A structured, versioned JSON payload written nightly by the Oracle pipeline. It describes the *current observed state* of institutional-money rotation across sector/subsector nodes — purely descriptive. It does not forecast anything.

Payload path: `site/basketdata/oracle_state.json`

---

## Staleness Contract

| Field | Rule |
|---|---|
| `asof` | ISO date string (`YYYY-MM-DD`) of the data point the payload describes. |
| staleness | TRADING-DAY-AWARE (v1.1.0): `asof` at most 2 business days behind now, plus a 168h calendar hard cap. A fixed 48h failed every weekend/holiday (first E2E failed on July-4th weekend). |

**Consumers MUST** treat any payload whose `asof` is more than 2 trading days behind (or >168h calendar) as **absent** and surface a staleness warning rather than stale data. Do not display a stale Oracle state as if it were current.

---

## Version Policy (semver `payload_version`)

The field `payload_version` (string, semver) is present in every stamped payload.

| Version type | When to bump | Consumer impact |
|---|---|---|
| Patch `x.y.Z` | Comment-only or internal wording | None |
| Minor `x.Y.0` | **Additive fields** that leave all existing paths unchanged | None — consumers must tolerate unknown fields (tolerant-reader rule) |
| Major `X.0.0` | Semantic change to a required field, field removal, or type change | Breaking — coordinate with Red Queen before deploy |

**Tolerant-reader rule (critical):** Consumers MUST NOT error on fields they do not recognize. Parallel Oracle waves (A3 regime tag, B1 personality fields) add minor-version additive fields to the payload; a consumer that errors on unknown keys will break when those waves merge.

**v1.2.0 (R-SP19, W5):** B1 member roll-up landed — each complex dict in `complexes` now carries an optional `personality_context` sub-object (dominant archetypes/chart labels, tinderbox share, event-override share, member coverage) when `site/factordata/stock_personality.json` is present. Always `confidence_class: "descriptive"`. Absent aggregate → field omitted entirely (no null; tolerant-reader safe). See `engine/oracle/personality_context.py`.

---

## Top-Level Field Semantics

| Field | Type | Required | Description |
|---|---|---|---|
| `schema` | string | yes | Always `"oracle_state.v1"`. |
| `payload_version` | string | yes (stamped) | Semver. May be absent in pre-contract payloads; treat as `"0.0.0"`. |
| `asof` | string (ISO date) | yes | Date of the data this payload describes. |
| `regime` | object | yes | Aggregate regime summary. Fields: `n_active_complexes` (int), `breadth` (float\|null), `vix_regime` (float\|null). |
| `complexes` | list | yes | One item per rotation complex. See Complex Item below. |
| `active_episodes` | list | yes | All non-exhausted episodes. See Episode Item below. |
| `onset_watchlist` | list of strings | yes | Node names where `accel_z > 0.8` but no active episode yet. Display-only signals. |
| `disclaimers` | object | yes | See Disclaimers below. |

### Complex Item

| Field | Type | Description |
|---|---|---|
| `id` | string | Complex identifier (e.g. `"ai_compute"`). |
| `name` | string | English display name. |
| `name_zh` | string | Chinese display name. |
| `state` | string | `"active_in" \| "active_out" \| "active_two_sided" \| "quiet"` |
| `tier` | string\|null | Best tier of any active episode in this complex: `"onset" \| "confirmed" \| "undeniable"`. |
| `direction` | string\|null | `"in" \| "out"` — direction of the most-advanced episode. |
| `n_members_active` | int | Count of nodes with active episodes in this complex. |

### Episode Item

| Field | Type | Description |
|---|---|---|
| `node` | string | Node name (e.g. `"XLK"`, `"AI Compute"`). |
| `direction` | string | `"in"` (money flowing in) or `"out"` (money rotating out). |
| `tier` | string | `"onset" \| "confirmed" \| "undeniable"`. |
| `onset_date` | string (ISO date) | Date the episode was first detected. |
| `confirmed_date` | string\|null | Date the episode was confirmed (breadth + multi-node), or null if still onset. |
| `two_sided` | bool | True if this episode is part of a paired source→sink routing pair. |
| `pair` | string\|null | Paired episode id if `two_sided`, else null. |
| `survivorship_flagged` | bool | True when the underlying panel covers only 2021→ (Tier-M survivorship bias applies). |
| `base_rate_context` | object\|null | Measured base rates for this direction/tier combination, from gauntlet. |
| `analogues` | list\|null | Historical analogues from memory, if present. |
| `confidence_class` | string | Confidence taxonomy (see below). Added by `contract.stamp_payload()`. |
| `lineage` | string | Registration/adjudication document anchor for `confidence_class`. |

### Disclaimers

| Field | Type | Description |
|---|---|---|
| `display_only` | bool | Always `True`. The payload is display-only — never a trading signal. |
| `error_rates` | object | Measured error rates from the P3 gauntlet. Keys: `onset_to_confirmed_conversion` (float\|null), `false_start_rate` (float\|null). These MUST be printed next to any onset-tier alert shown to users. |

---

## Confidence Taxonomy

Every signal-bearing episode item carries `confidence_class`:

| Value | Meaning | Current members |
|---|---|---|
| `validated` | Primary endpoint cleared a registered gauntlet with pre-bound vocabulary; FDR-survived. | **None currently.** P3 primaries NULL (see Adjudication R1). |
| `display_with_edge` | Secondary endpoint with measured edge; may render with caveats and error rates printed. | `ep_in_onset_21d` (+0.62%, boot_p 0.0075, BH-survived 109-family); `ep_out_onset_5d` (+0.50%); 6 placebo-surviving routing cells (P3b R2 RESOLVED). |
| `exploratory` | Tier-1 effect exists but no gauntlet adjudication. | Accruing routing cells not in the 6 survivors. |
| `descriptive` | Observed description of state; no edge claim. | All confirmed/undeniable-tier primaries (NULL per P3 R1); everything else not listed above. |

The `lineage` field on each item provides the exact document anchor that establishes this classification.

---

## The NEVER Guarantees

> Additive-extension naming rule: because banned-implication checking is substring-based (err-toward-safety), additive field NAMES must avoid the substrings `forecast`, `predicted`, `target`, `expected_return`. asof parses at UTC midnight; the trading-day rule makes weekend/holiday gaps first-class rather than accidental failures.

Prohibitions (a) and (b) are enforced by `validate_payload()` in code; (c) defines a consumer-side DISPLAY OBLIGATION plus the semantics of the `survivorship_flagged` field (the flag's presence is data; honoring the watermark is the consumer's contractual duty):

**(a) No forecast without validated lineage.**
Any payload key containing the substrings `"forecast"`, `"predicted"`, `"target"`, or `"expected_return"` is an error unless the containing item has `confidence_class == "validated"`. Since no endpoint is currently validated, these keys must not appear in any payload.

**(b) Onset-alert items must carry error-rate context.**
Any episode at `tier == "onset"` is an alert-class item. The payload's `disclaimers.error_rates.false_start_rate` must be numeric (not null). Consumers MUST print the false-start rate next to any onset-tier alert: "~38% of onset signals are false starts before the 5-day confirmation window."

**(c) Tier-M facts carry the survivorship watermark.**
Any episode item where `survivorship_flagged == True` describes a signal derived from a panel that covers 2021→ only (single era; survivorship-biased composition). Consumers must display this watermark: "Survivorship-flagged panel (2021→ only); n is small." Such items may NEVER feed a score, size computation, or gate.

---

## Minimal Python Consumption Example

The following 5-line filter gives a consumer the set of episodes with measured edge (safe to display with appropriate caveats):

```python
import json

state = json.load(open("site/basketdata/oracle_state.json"))

# Validated-only filter (currently empty — no primary endpoint cleared gauntlet)
validated = [
    ep for ep in state["active_episodes"]
    if ep.get("confidence_class") == "validated"
]

# Display-with-edge filter (the honest display surface)
display_edges = [
    ep for ep in state["active_episodes"]
    if ep.get("confidence_class") == "display_with_edge"
]
```

A consumer that wishes to be strict should also verify the payload is not stale:

```python
from datetime import datetime, timezone

asof = datetime.fromisoformat(state["asof"]).replace(tzinfo=timezone.utc)
age_hours = (datetime.now(timezone.utc) - asof).total_seconds() / 3600
if age_hours > 48:
    raise RuntimeError(f"Oracle payload is {age_hours:.0f}h stale — treat as absent")
```

---

## Validation

`engine/oracle/contract.validate_payload(payload)` returns `(ok: bool, errors: list[str])`.

The nightly pipeline (`scripts/oracle_nightly.py`, Step 6) calls this IMMEDIATELY BEFORE writing the file. A failing payload is never written; the prior file is preserved; `oracle_nightly.py` exits nonzero.

Consumers that cache the payload independently SHOULD also call `validate_payload` on load as a defensive check.

---

## Additive Extension Protocol (for parallel waves)

Parallel Oracle build waves (A3 regime tag, B1 personality, C washout columns) add fields to `oracle_state.json` as **minor-version additive fields**. Protocol:

1. Add new fields at END of existing dicts or lists; never rename or remove existing ones.
2. Bump `payload_version` to the next minor version once the wave merges to main.
3. New fields that are signal-bearing MUST carry `confidence_class` and `lineage`.
4. Fields whose absence would block a downstream consumer must be marked optional-with-default in that consumer (`state.get("regime_tag", "unknown")`).
5. If a wave references a column not yet merged (e.g. `personality_class`), mark the compound `blocked_missing_column` in the registry; never crash.

---

## What This File Does NOT Cover

- The compound registry schema (`data/oracle/compounds/registry.jsonl`) — see `ORACLE_COMPOUND_LIBRARY.md`.
- The gauntlet harness mechanics — see `ORACLE_GAUNTLET_P3_ADJUDICATION.md`.
- The forward ledger PIT schema — see `data/oracle/forward_ledger.jsonl` comments and `scripts/oracle_nightly.py` Step 9.
