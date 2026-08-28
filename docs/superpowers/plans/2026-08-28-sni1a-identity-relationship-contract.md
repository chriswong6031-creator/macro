# SNI-1A Identity Relationship Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one pure, deterministic, all-false-authority contract that represents source-receipted single-name identity relationships — including Alibaba 9988/89988 same-economic-security, Tencent 700/80700 same-economic-security, and BABA ADS→Alibaba ordinary-share 1:8 conversion — without reading owners or minting canonical Data OS identity.

**Architecture:** SNI-1A is a contract/validator library only. Data OS remains canonical for admitted `ISS:` / `SEC:` / listing IDs; owner-native/PIT identity bridges retain their own semantics; SNI records only descriptive relationships and typed unresolved canonical identity. The wire is an issuer-scoped `identity_relationship_bundle/v1` containing evidence references and one or more relationship records. Relationship and bundle IDs are deterministic hashes in SNI-only namespaces and never reuse Data OS namespaces.

**Tech Stack:** Python 3.14-compatible stdlib, `jsonschema` Draft 2020-12, existing `lib.dataos.identity` parsers for syntax consistency only, JSON Schema, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md` as amended by `docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md`; decision `DEC:SNI-IDENTITY-AUTHORITY-CHAIN`.

## Global Constraints

- Precondition: the records-only plan `docs/superpowers/plans/2026-08-28-sni-semantic-registration.md` has landed and `WS:SINGLE-NAME-INTELLIGENCE-OS` exists under `program: single-name-intelligence`.
- SNI-1A is one independently reviewable PR. Do not combine SNI-1B owner manifests, SNI-1C reference-twin compilation, SNI-1D owner reads, or SNI-1E UI into this carrier.
- No owner reads: no `data/reference/*.parquet` access, no Company Intelligence/Earnings/Capital/Options/HK stores, no network, no database, no scheduler, no collector, no LLM.
- `lib.dataos.identity` may be imported only for pure ID syntax parsing/normalization checks; an ID string derived by an allocator is not canonical authority.
- A canonical Data OS identity is accepted only when the caller supplies a `data_os_master` resolution receipt. SNI-1A validates that receipt shape; it does not verify the underlying parquet row.
- Null/unresolved canonical HK issuer identity remains legal and visible even when an external CIK/legal-name receipt exists.
- SNI relationship IDs use `snir_` plus 64 lowercase SHA-256 hex characters. Bundle IDs use `snib_` plus 64 lowercase SHA-256 hex characters. They are relationship-record identities, not issuer/security/listing identities.
- Relationship types are closed to `same_economic_security` and `represents_units_of` in v1.
- No hard-coded trading implication, stock score, forecast, target, rank, gate, size, escalation or trade behavior exists.
- Authority booleans are exactly: `can_rank=false`, `can_gate=false`, `can_size=false`, `can_originate_signal=false`, `can_escalate=false`, `can_trade=false`.
- Alibaba/Tencent source facts belong in fixtures as evidence assertions; the generic validator must not contain ticker-specific business logic such as `if ticker == "BABA"`.
- Wrong BABA 1:8 handling is rejected because relationship units must match the structured source-evidence assertion, not because the library hard-codes Alibaba.
- Stale FX / asynchronous cross-market price comparison is held for SNI-1C. SNI-1A contains no price field and no FX conversion implementation.

---

## File Structure

Create these files only for SNI-1A:

```text
contracts/single_name_intelligence/
  README.md
  identity_relationship.v1.schema.json

lib/single_name_intelligence/
  __init__.py
  identity_relationship.py

tests/
  test_single_name_identity_relationship.py
  fixtures/single_name_intelligence/
    alibaba_identity_relationship_valid.json
    tencent_identity_relationship_valid.json
```

Responsibilities:

- `identity_relationship.v1.schema.json` — closed wire shape and all-false authority constants.
- `identity_relationship.py` — schema loading, semantic validation, canonical ordering and deterministic ID functions; no owner I/O.
- `alibaba_identity_relationship_valid.json` — two relationships: same-economic-security for 9988/89988 and `represents_units_of` for BABA→that ordinary-share relationship, ratio asserted by evidence as 1:8.
- `tencent_identity_relationship_valid.json` — same-economic-security for 700/80700, with unresolved canonical issuer allowed.
- `test_single_name_identity_relationship.py` — schema, deterministic-ID, hostile authority/identity/evidence tests and no-owner-I/O guard.
- `README.md` — contract boundary and later-wave handoff; no implementation status inflation.

---

### Task 1: Freeze the v1 wire shape and positive Alibaba/Tencent fixtures

**Files:**
- Create: `contracts/single_name_intelligence/identity_relationship.v1.schema.json`
- Create: `tests/fixtures/single_name_intelligence/alibaba_identity_relationship_valid.json`
- Create: `tests/fixtures/single_name_intelligence/tencent_identity_relationship_valid.json`
- Create: `tests/test_single_name_identity_relationship.py`

**Interfaces:**
- Produces wire schema `mastermind.single_name.identity_relationship_bundle/v1`.
- Produces positive fixtures consumed by every later task.
- Does not yet produce the semantic validator module.

- [ ] **Step 1: Write the failing schema-fixture test**

Create `tests/test_single_name_identity_relationship.py` starting with:

```python
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "single_name_intelligence" / "identity_relationship.v1.schema.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "single_name_intelligence"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_schema_accepts_alibaba_and_tencent_reference_fixtures():
    schema = _load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for name in (
        "alibaba_identity_relationship_valid.json",
        "tencent_identity_relationship_valid.json",
    ):
        errors = sorted(validator.iter_errors(_load_json(FIXTURE_DIR / name)), key=lambda e: list(e.path))
        assert errors == [], "\n".join(error.message for error in errors)
```

- [ ] **Step 2: Run the test and verify the schema is absent**

Run:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_v1_schema_accepts_alibaba_and_tencent_reference_fixtures -q
```

Expected: FAIL with `FileNotFoundError` for `identity_relationship.v1.schema.json`.

- [ ] **Step 3: Create the JSON Schema with these exact top-level requirements**

The schema must use Draft 2020-12, `additionalProperties: false`, and require:

```json
{
  "schema": "mastermind.single_name.identity_relationship_bundle/v1",
  "version": "1.0.0",
  "bundle_id": "snib_<64hex>",
  "issuer_subject": {},
  "evidence_refs": [],
  "relationships": [],
  "authority": {
    "can_rank": false,
    "can_gate": false,
    "can_size": false,
    "can_originate_signal": false,
    "can_escalate": false,
    "can_trade": false
  }
}
```

Freeze these nested definitions:

**`issuer_subject`**

```text
canonical_issuer_id: string matching ^ISS:...$ | null
resolution_state: resolved | owner_unresolved | not_admitted | conflict | unknown
resolution_receipt: data_os_issuer_receipt | null
owner_native_refs: array
external_ids: array
```

If a CIK is carried, it lives in `external_ids`; it never occupies `canonical_issuer_id`.

**`counter_subject`**

```text
mic: four uppercase alphanumerics
observed_code: non-empty uppercase/digit/dot/dash code
trading_currency: three uppercase letters
security_kind: ordinary_share | ads | other
share_class: non-empty string
canonical_identity:
  resolution_state: resolved | owner_unresolved | not_admitted | conflict | unknown
  canonical_listing_id: string | null
  canonical_security_id: string matching ^SEC:...$ | null
  resolution_receipt: data_os_security_receipt | null
  absence_reason: no_issuer_evidence | no_security_evidence | not_admitted | identity_conflict | not_checked | null
```

**`data_os_security_receipt`**

```text
authority_owner: const data_os
master_artifact: const data/reference/security_master.parquet
master_receipt_ref: const data/reference/_receipt.json
master_digest: ^sha256:[0-9a-f]{64}$
observed_at: date-time
```

**`data_os_issuer_receipt`**

Same shape, but `master_artifact` is `data/reference/issuer_master.parquet`.

**`evidence_ref`**

```text
ref_key
source_kind: issuer_primary | exchange_primary | data_os | owner_native
locator
observed_at: date-time
published_at: date-time | null
assertion:
  relationship_type: same_economic_security | represents_units_of
  source_units: positive integer | null
  target_units: positive integer | null
```

**`relationship`** is a `oneOf`:

1. `same_economic_security`
   - `relationship_id: ^snir_[0-9a-f]{64}$`
   - `relationship_type: const same_economic_security`
   - `counter_members`: array with minimum 2 `counter_subject` records
   - `source_counter: null`
   - `target_relationship_id: null`
   - `unit_relationship: null`
   - `evidence_ref_keys`: non-empty unique array
   - `clock`: `{known_at: date-time, effective_state: known|unknown, effective_from: date|null, valid_to: date|null}`
   - `correction_state: current|corrected|superseded|conflict|unknown`
   - `authority: descriptive`

2. `represents_units_of`
   - `relationship_id: ^snir_[0-9a-f]{64}$`
   - `relationship_type: const represents_units_of`
   - `counter_members: []`
   - `source_counter`: one `counter_subject`
   - `target_relationship_id: ^snir_[0-9a-f]{64}$`
   - `unit_relationship`: `{source_units: positive integer, target_units: positive integer}`
   - same evidence/clock/correction/authority requirements.

The schema may enforce structural conditionals, but cross-record target existence, canonical Data OS ID pairing and evidence assertion matching belong to the Python semantic validator in later tasks.

- [ ] **Step 4: Create the Alibaba positive fixture without pretending owner reads occurred**

The Alibaba fixture must:

- set `canonical_issuer_id: null`, `resolution_state: owner_unresolved`, and carry external CIK `0001577552` as a separate source-backed external ID;
- include 9988/HKD and 89988/CNY as `ordinary_share` counter members in one `same_economic_security` relationship;
- leave their canonical Data OS IDs unresolved in this contract fixture unless an explicit synthetic `data_os` receipt is intentionally added for a validator test;
- include BABA/USD/XNYS as `security_kind: ads` in a `represents_units_of` relationship targeting the ordinary-share relationship;
- set `unit_relationship` to `source_units=1`, `target_units=8`;
- carry an issuer-primary evidence assertion for the same 1:8 units using Alibaba's official investor-information locator;
- use no price, FX, expected return or trade field;
- keep all authority false.

Use `observed_at: "2026-08-28T11:00:00Z"` for the design fixture's evidence observation clock and `effective_state: unknown` where an exact relationship-effective date is not frozen by SNI-1A.

- [ ] **Step 5: Create the Tencent positive fixture**

The Tencent fixture must:

- set `canonical_issuer_id: null`, `resolution_state: owner_unresolved`, and carry external CIK `0001293451` separately;
- include 700/HKD and 80700/CNY as two `ordinary_share` counter members in one `same_economic_security` relationship;
- retain unresolved canonical ID fields unless a synthetic Data OS receipt is explicitly being tested;
- carry HKEX/issuer evidence asserting the same-economic-security relationship;
- contain no KWEB/TCEHY directional or proxy semantics — those belong to later owner/context composition;
- keep all authority false.

- [ ] **Step 6: Run schema validation**

Run:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_v1_schema_accepts_alibaba_and_tencent_reference_fixtures -q
```

Expected: PASS.

- [ ] **Step 7: Commit the wire/fixtures**

```bash
git add contracts/single_name_intelligence/identity_relationship.v1.schema.json tests/fixtures/single_name_intelligence tests/test_single_name_identity_relationship.py
git commit -m "contracts(sni): freeze identity relationship wire"
```

---

### Task 2: Implement deterministic IDs, canonical ordering and semantic validation

**Files:**
- Create: `lib/single_name_intelligence/__init__.py`
- Create: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`

**Interfaces:**
- Produces `SingleNameIdentityError`.
- Produces `canonical_json_bytes(value: object) -> bytes`.
- Produces `compute_relationship_id(relationship: Mapping[str, Any]) -> str`.
- Produces `compute_bundle_id(bundle: Mapping[str, Any]) -> str`.
- Produces `normalize_identity_relationship_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]`.
- Produces `validate_identity_relationship_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Add failing tests for public API and deterministic identity**

Append:

```python
import copy

import pytest

from lib.single_name_intelligence.identity_relationship import (
    SingleNameIdentityError,
    compute_bundle_id,
    compute_relationship_id,
    normalize_identity_relationship_bundle,
    validate_identity_relationship_bundle,
)


def test_relationship_and_bundle_ids_are_deterministic_and_order_stable():
    payload = _load_json(FIXTURE_DIR / "alibaba_identity_relationship_valid.json")
    normalized = normalize_identity_relationship_bundle(payload)
    assert validate_identity_relationship_bundle(normalized) == normalized

    reversed_payload = copy.deepcopy(payload)
    reversed_payload["evidence_refs"] = list(reversed(reversed_payload["evidence_refs"]))
    reversed_payload["relationships"] = list(reversed(reversed_payload["relationships"]))
    for relationship in reversed_payload["relationships"]:
        relationship["evidence_ref_keys"] = list(reversed(relationship["evidence_ref_keys"]))
        if relationship["counter_members"]:
            relationship["counter_members"] = list(reversed(relationship["counter_members"]))

    normalized_reversed = normalize_identity_relationship_bundle(reversed_payload)
    assert normalized_reversed == normalized
    assert compute_bundle_id(normalized_reversed) == compute_bundle_id(normalized)
    for relationship in normalized["relationships"]:
        assert relationship["relationship_id"] == compute_relationship_id(relationship)
```

- [ ] **Step 2: Run the test and verify the module is missing**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_relationship_and_bundle_ids_are_deterministic_and_order_stable -q
```

Expected: collection FAIL with `ModuleNotFoundError: lib.single_name_intelligence`.

- [ ] **Step 3: Implement the pure module skeleton**

`lib/single_name_intelligence/identity_relationship.py` begins with:

```python
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from lib.dataos.identity import parse_id, parse_listing_key

SCHEMA = "mastermind.single_name.identity_relationship_bundle/v1"
VERSION = "1.0.0"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "single_name_intelligence"
    / "identity_relationship.v1.schema.json"
)
ALL_FALSE_AUTHORITY = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate_signal": False,
    "can_escalate": False,
    "can_trade": False,
}


class SingleNameIdentityError(ValueError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
```

Load the schema once with `json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))` and create a `Draft202012Validator(..., format_checker=FormatChecker())`.

- [ ] **Step 4: Implement canonical normalization**

`normalize_identity_relationship_bundle()` must deep-copy the caller's mapping and canonicalize only order, never semantic values:

```text
counter_members: sort by (mic, observed_code, trading_currency, security_kind, share_class)
evidence_ref_keys: lexical sort
evidence_refs: sort by ref_key
relationships: first normalize their members/evidence keys, recompute relationship_id, then sort by relationship_id
bundle_id: recompute last from the canonicalized bundle with bundle_id removed
```

Do not mutate the caller's object.

- [ ] **Step 5: Implement deterministic ID helpers**

`compute_relationship_id()` hashes canonical JSON of the relationship with `relationship_id` removed:

```python
def compute_relationship_id(relationship: Mapping[str, Any]) -> str:
    payload = {str(key): value for key, value in relationship.items() if key != "relationship_id"}
    return "snir_" + sha256(canonical_json_bytes(payload)).hexdigest()
```

`compute_bundle_id()` performs the same operation with `bundle_id` removed and returns `snib_<sha256>`.

- [ ] **Step 6: Implement the first validation pass**

`validate_identity_relationship_bundle()` must:

1. normalize a copy;
2. schema-validate the normalized copy;
3. require caller-supplied IDs, if present in the original, to equal recomputed IDs;
4. require the all-false authority block exactly;
5. return the normalized validated dict.

Raise `SingleNameIdentityError` with stable reason prefixes:

```text
SNI1A_R001_SCHEMA
SNI1A_R002_RELATIONSHIP_ID
SNI1A_R003_BUNDLE_ID
SNI1A_R004_AUTHORITY
```

- [ ] **Step 7: Run the deterministic tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: all Task 1/2 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add lib/single_name_intelligence tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): validate deterministic identity relationships"
```

---

### Task 3: Enforce canonical Data OS receipt semantics without reading Data OS

**Files:**
- Modify: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`

**Interfaces:**
- Extends `validate_identity_relationship_bundle()`; no new I/O API.
- Uses `lib.dataos.identity.parse_id()` and `parse_listing_key()` only for syntax and pair consistency.

- [ ] **Step 1: Add hostile tests for resolved/unresolved canonical identity**

Add helpers that copy the Tencent fixture and mutate its first counter. Add these tests:

```python
def test_unresolved_member_cannot_carry_canonical_dataos_ids():
    payload = _load_json(FIXTURE_DIR / "tencent_identity_relationship_valid.json")
    member = payload["relationships"][0]["counter_members"][0]
    member["canonical_identity"]["canonical_listing_id"] = "HK-XHKG-00700"
    member["canonical_identity"]["canonical_security_id"] = "SEC:HK-XHKG-00700"
    with pytest.raises(SingleNameIdentityError, match="SNI1A_R005"):
        validate_identity_relationship_bundle(payload)


def test_resolved_member_requires_dataos_master_receipt_and_matching_id_pair():
    payload = _load_json(FIXTURE_DIR / "tencent_identity_relationship_valid.json")
    member = payload["relationships"][0]["counter_members"][0]
    member["canonical_identity"] = {
        "resolution_state": "resolved",
        "canonical_listing_id": "HK-XHKG-00700",
        "canonical_security_id": "SEC:HK-XHKG-09988",
        "resolution_receipt": {
            "authority_owner": "data_os",
            "master_artifact": "data/reference/security_master.parquet",
            "master_receipt_ref": "data/reference/_receipt.json",
            "master_digest": "sha256:" + "a" * 64,
            "observed_at": "2026-08-28T11:00:00Z"
        },
        "absence_reason": None,
    }
    with pytest.raises(SingleNameIdentityError, match="SNI1A_R006"):
        validate_identity_relationship_bundle(payload)
```

Also add issuer variants:

- `resolution_state=resolved` with null `canonical_issuer_id` → reject;
- unresolved issuer with `canonical_issuer_id="ISS:..."` → reject;
- resolved issuer without a `data/reference/issuer_master.parquet` receipt → reject.

- [ ] **Step 2: Run hostile tests and verify current validator accepts at least one invalid mutation**

Run:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: FAIL in the new hostile tests.

- [ ] **Step 3: Add semantic receipt checks**

Implement stable errors:

```text
SNI1A_R005_UNRESOLVED_HAS_CANONICAL_ID
SNI1A_R006_CANONICAL_ID_PAIR_MISMATCH
SNI1A_R007_RESOLVED_WITHOUT_DATAOS_RECEIPT
```

Rules:

- `resolution_state == "resolved"` requires non-null canonical fields and a Data OS receipt.
- any other resolution state requires canonical fields and resolution receipt to be null.
- security ID must parse as kind `security`.
- listing ID must parse as kind `listing`.
- the `ListingKey` encoded by the security ID must equal the listing ID's `ListingKey`.
- receipt artifact paths are already schema-const; semantic validation must not relax them.
- issuer resolved state requires `canonical_issuer_id` parsing as kind `issuer` plus issuer-master receipt.
- external CIK/name references do not change canonical resolution state.

Never open the master artifacts in this function.

- [ ] **Step 4: Add the anti-minting test**

The contract must distinguish "valid-looking ID" from "owner-receipted ID":

```python
def test_valid_looking_dataos_id_without_receipt_is_not_authority():
    payload = _load_json(FIXTURE_DIR / "tencent_identity_relationship_valid.json")
    member = payload["relationships"][0]["counter_members"][0]
    member["canonical_identity"].update({
        "resolution_state": "resolved",
        "canonical_listing_id": "HK-XHKG-00700",
        "canonical_security_id": "SEC:HK-XHKG-00700",
        "resolution_receipt": None,
        "absence_reason": None,
    })
    with pytest.raises(SingleNameIdentityError, match="SNI1A_R007"):
        validate_identity_relationship_bundle(payload)
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/single_name_intelligence/identity_relationship.py tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): enforce Data OS identity receipts"
```

---

### Task 4: Enforce relationship semantics, evidence clocks and ADS unit evidence

**Files:**
- Modify: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`

**Interfaces:**
- Extends validation over the closed relationship graph within one bundle.
- `represents_units_of.target_relationship_id` resolves only inside the same validated bundle.

- [ ] **Step 1: Add hostile same-economic-security tests**

Add tests that reject:

1. duplicate counter tuples `(mic, observed_code, trading_currency)` inside one relation;
2. one member `security_kind=ordinary_share` and another `security_kind=ads` in `same_economic_security`;
3. fewer than two distinct members;
4. relation evidence keys missing from `evidence_refs`;
5. relation `known_at` earlier than every referenced evidence `observed_at`.

Use stable expected prefix `SNI1A_R008` for member/economic-security violations and `SNI1A_R010` for evidence/clock violations.

- [ ] **Step 2: Add hostile conversion tests**

For the Alibaba fixture:

```python
def test_baba_unit_relation_must_match_source_evidence_assertion():
    payload = _load_json(FIXTURE_DIR / "alibaba_identity_relationship_valid.json")
    conversion = next(
        rel for rel in payload["relationships"] if rel["relationship_type"] == "represents_units_of"
    )
    conversion["unit_relationship"] = {"source_units": 1, "target_units": 1}
    with pytest.raises(SingleNameIdentityError, match="SNI1A_R009"):
        validate_identity_relationship_bundle(payload)
```

The fixture's evidence assertion stays `1 -> 8`. This proves corruption is rejected without adding ticker-specific validator code.

Also reject:

- target relationship ID absent from the same bundle;
- target relationship exists but is not `same_economic_security`;
- source counter `security_kind` is not `ads` for v1 `represents_units_of`;
- referenced evidence assertion has a different relationship type;
- `source_units` or `target_units` differs between relationship and every referenced structured assertion.

- [ ] **Step 3: Run tests and verify the new hostile cases fail**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: FAIL before the new semantic passes are implemented.

- [ ] **Step 4: Implement graph/evidence semantics**

Add stable reason codes:

```text
SNI1A_R008_SAME_SECURITY_MEMBER_INVALID
SNI1A_R009_UNIT_ASSERTION_MISMATCH
SNI1A_R010_EVIDENCE_CLOCK_INVALID
SNI1A_R011_TARGET_RELATION_INVALID
```

Implementation order:

1. build `evidence_by_key` and reject duplicate evidence keys;
2. build `relationship_by_id` after ID verification and reject duplicate relationship IDs;
3. validate every evidence key resolves;
4. validate relationship `known_at >= max(referenced evidence observed_at)`;
5. for known `effective_from`, require non-null date; for unknown, require null;
6. validate same-security members are distinct and share `security_kind` + `share_class`;
7. validate conversion target exists and is same-security;
8. validate conversion source is ADS;
9. require at least one referenced evidence assertion whose `relationship_type` and units exactly match the conversion.

Do not parse URLs, scrape issuer pages, or special-case Alibaba/Tencent in the library.

- [ ] **Step 5: Prove generic behavior with a non-BABA synthetic ratio**

Add a synthetic test that changes the Alibaba source and relationship units together to `1 -> 2`; it should validate. This proves the validator enforces source/relationship consistency rather than hard-coded 1:8 company logic.

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/single_name_intelligence/identity_relationship.py tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): enforce counter and unit relationships"
```

---

### Task 5: Lock the no-owner-I/O boundary and contract documentation

**Files:**
- Create: `contracts/single_name_intelligence/README.md`
- Modify: `tests/test_single_name_identity_relationship.py`
- Modify: `lib/single_name_intelligence/__init__.py`

**Interfaces:**
- Produces documented public API for SNI-1A.
- Produces a static regression guard preventing owner/runtime I/O from entering the contract module.

- [ ] **Step 1: Add the no-owner-I/O source guard**

Append:

```python
import ast


def test_identity_relationship_module_has_no_owner_or_runtime_io_dependencies():
    path = ROOT / "lib" / "single_name_intelligence" / "identity_relationship.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_prefixes = (
        "engine.",
        "collectors.",
        "app.",
        "requests",
        "httpx",
        "yfinance",
        "pandas",
        "sqlalchemy",
        "duckdb",
    )
    assert not sorted(
        name for name in imports if name.startswith(forbidden_prefixes)
    )
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "requests." not in source
```

The permitted `lib.dataos.identity` import is pure syntax validation and must remain limited to parser functions; do not import `VendorAliasTable` or `IssuerMaster` into SNI-1A.

- [ ] **Step 2: Export only the contract API**

`lib/single_name_intelligence/__init__.py` should export:

```python
from .identity_relationship import (
    SingleNameIdentityError,
    compute_bundle_id,
    compute_relationship_id,
    normalize_identity_relationship_bundle,
    validate_identity_relationship_bundle,
)

__all__ = [
    "SingleNameIdentityError",
    "compute_bundle_id",
    "compute_relationship_id",
    "normalize_identity_relationship_bundle",
    "validate_identity_relationship_bundle",
]
```

- [ ] **Step 3: Write the contract README**

`contracts/single_name_intelligence/README.md` must state:

- Data OS owns canonical issuer/security/listing identity.
- `company_identity.v1` and other owner-native identities remain their own PIT/event bridge, not a duplicate master.
- SNI-1A stores nothing and reads no owner.
- `same_economic_security` groups counter observations descriptively; it does not create a `SEC:` ID.
- `represents_units_of` is evidence-backed and unit-explicit.
- unresolved canonical IDs are first-class and legal.
- `snir_`/`snib_` IDs identify relationship records/bundles only.
- correction behavior is append/supersede in later SNI composition; SNI-1A itself persists nothing.
- no price, FX, forecast, score, rank, gate, size, signal, escalation or trade authority exists.
- SNI-1B is the next wave only after SNI-1A acceptance; SNI-1C owns price/FX/asynchronous comparison guards.

- [ ] **Step 4: Run focused tests and compile check**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
python3 -m compileall -q lib/single_name_intelligence
```

Expected: both commands exit 0.

- [ ] **Step 5: Run adjacent identity regressions**

```bash
python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_identity_seam_agreement.py -q
```

Expected: PASS. SNI-1A must not change Data OS behavior; these tests protect against accidental coupling.

- [ ] **Step 6: Run Agent OS validation**

```bash
python3 scripts/agentos.py validate
```

Expected: exit 0; SNI-1A introduces no invalid organizational records.

- [ ] **Step 7: Commit**

```bash
git add contracts/single_name_intelligence/README.md lib/single_name_intelligence/__init__.py tests/test_single_name_identity_relationship.py
git commit -m "docs(sni): freeze relationship contract boundary"
```

---

## Final Exact-Head Verification

Before requesting review, run on the exact PR head:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_identity_seam_agreement.py -q
python3 -m compileall -q lib/single_name_intelligence
python3 scripts/agentos.py validate
```

Then require hosted repository CI on the exact head. Do not call SNI-1A `PROVEN_LIVE`; it is a contract-only capability. Correct state after merge and exact-head validation is **BUILT_NOT_PROVEN / CONTRACT-FROZEN** until SNI-1C/1D supply a real reference-twin consumer path.

## Acceptance Checklist

SNI-1A is accepted only if all are true:

- Alibaba 9988/89988 same-security relationship validates.
- Tencent 700/80700 same-security relationship validates.
- BABA 1:8 conversion validates against its structured evidence assertion.
- wrong ratio with unchanged evidence is rejected.
- a different synthetic ratio validates when evidence and relationship agree, proving no ticker hard-code.
- unresolved Data OS canonical identity remains legal and contains no canonical ID.
- resolved canonical identity requires a Data OS master receipt and matching listing/security pair.
- external CIK cannot silently become a canonical Data OS issuer ID.
- relationship IDs cannot occupy `ISS:` / `SEC:` / Data OS listing namespaces.
- relationship target references are bundle-local and validated.
- evidence clocks are required and cannot post-date the relationship's `known_at`.
- no owner/network/store/runtime I/O is imported.
- all authority is false.
- no price or FX implementation entered SNI-1A.
- Data OS regression tests remain green.

## Plan self-review

- Every SNI-1A requirement from the parent spec is covered except stale-FX comparison, which the binding identity-authority amendment explicitly moves to SNI-1C because SNI-1A has no price/FX operation.
- Data OS remains the only canonical identity authority; this plan never writes its stores or invents a general namespace renderer.
- The wire represents economic-security semantics as relationships rather than a parallel `security_id` system.
- Alibaba/Tencent company facts live in fixtures/evidence and do not leak into generic validator branches.
- Every public function used by later tasks is defined in Task 2.
- No placeholder step or undefined future helper is required to implement this plan.

## Execution Recommendation

Preferred worker avenue for SNI-1A after the semantic-registration predecessor lands: **Terra**. The architecture is frozen, the PR is bounded and contract-heavy, and the work does not justify scarce Fable principal capacity. Return to Sol before widening schema vocabulary, changing Data OS, introducing owner reads, or moving any SNI-1B+ scope into the carrier.
