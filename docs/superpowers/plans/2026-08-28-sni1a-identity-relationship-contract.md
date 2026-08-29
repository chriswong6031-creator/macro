# SNI-1A Identity Relationship Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one pure, deterministic, all-false-authority contract that represents source-receipted single-name identity relationships — Alibaba 9988/89988 same-economic-security, Tencent 700/80700 same-economic-security, and BABA ADS→Alibaba ordinary-share 1:8 conversion — without reading owners or minting canonical Data OS identity.

**Architecture:** SNI-1A is a contract/validator library only. Data OS remains canonical for admitted `ISS:` / `SEC:` / listing IDs; owner-native/PIT identity bridges retain their own semantics; SNI records only descriptive relationships and typed unresolved canonical identity. The wire is an issuer-scoped `identity_relationship_bundle/v1` containing evidence references and one or more relationship records. Relationship and bundle IDs are deterministic hashes in SNI-only namespaces and never reuse Data OS namespaces.

**Tech Stack:** Python 3.14-compatible stdlib, `jsonschema` Draft 2020-12, existing `lib.dataos.identity` pure parsers/normalizers for syntax consistency only, JSON Schema, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md` as amended by `docs/superpowers/specs/2026-08-28-sni1-identity-authority-amendment.md`; decision `DEC:SNI-IDENTITY-AUTHORITY-CHAIN`.

## Global Constraints

- Precondition: `docs/superpowers/plans/2026-08-28-sni-semantic-registration.md` has landed and `WS:SINGLE-NAME-INTELLIGENCE-OS` exists under `program: single-name-intelligence`.
- SNI-1A is one independently reviewable PR. Do not combine SNI-1B owner manifests, SNI-1C reference-twin compilation, SNI-1D owner reads, or SNI-1E UI into this carrier.
- No owner reads: no `data/reference/*.parquet` access, no Company Intelligence/Earnings/Capital/Options/HK stores, no network, no database, no scheduler, no collector, no LLM.
- `lib.dataos.identity` may be imported only for pure parsing/normalization checks. Deriving a syntactically valid Data OS ID is never proof the stored master admitted it.
- A canonical Data OS identity is accepted only when the caller supplies a `data_os_master` resolution receipt. SNI-1A validates receipt shape and internal consistency; it does not verify the underlying master row.
- Null/unresolved canonical HK issuer identity remains legal and visible even when external CIK/legal-name evidence exists.
- SNI relationship IDs use `snir_` + 64 lowercase SHA-256 hex characters. Bundle IDs use `snib_` + 64 lowercase SHA-256 hex characters. These identify SNI records only.
- Relationship types are closed to `same_economic_security` and `represents_units_of` in v1.
- No hard-coded company/ticker branch exists in the validator. Alibaba/Tencent facts live in fixtures/evidence, not generic code.
- Wrong BABA 1:8 handling is rejected because relationship units must match the structured source-evidence assertion, not because the library knows BABA's ratio.
- Evidence for `same_economic_security` must bind the exact counter-member descriptor set, not merely assert a generic relationship type.
- Any resolved canonical Data OS member must agree with the observed member country, MIC and code as well as with its paired `SEC:`/listing identity.
- No stock score, forecast, target, rank, gate, size, signal, escalation or trade behavior exists.
- Authority booleans are exactly `can_rank=false`, `can_gate=false`, `can_size=false`, `can_originate_signal=false`, `can_escalate=false`, `can_trade=false`.
- Stale FX / asynchronous cross-market price comparison is held for SNI-1C. SNI-1A has no price field and no FX conversion implementation.

---

## File Structure

Create exactly:

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
- `identity_relationship.py` — schema loading, semantic validation, canonical ordering and deterministic IDs; no owner I/O.
- Alibaba fixture — `same_economic_security` for 9988/89988 plus `represents_units_of` for BABA→ordinary-share relationship, with evidence assertion 1:8.
- Tencent fixture — `same_economic_security` for 700/80700 with source-bound exact members.
- Tests — schema, IDs, evidence binding, Data OS receipt semantics, hostile authority/identity cases and no-owner-I/O guard.
- README — contract boundary and later-wave handoff.

---

### Task 1: Freeze the v1 wire shape and positive reference fixtures

**Files:**
- Create: `contracts/single_name_intelligence/identity_relationship.v1.schema.json`
- Create: `tests/fixtures/single_name_intelligence/alibaba_identity_relationship_valid.json`
- Create: `tests/fixtures/single_name_intelligence/tencent_identity_relationship_valid.json`
- Create: `tests/test_single_name_identity_relationship.py`

- [ ] **Step 1: Write the failing schema-fixture test**

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
        errors = sorted(
            validator.iter_errors(_load_json(FIXTURE_DIR / name)),
            key=lambda error: list(error.path),
        )
        assert errors == [], "\n".join(error.message for error in errors)
```

- [ ] **Step 2: Prove the test is red**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_v1_schema_accepts_alibaba_and_tencent_reference_fixtures -q
```

Expected: FAIL because the schema/fixtures do not exist.

- [ ] **Step 3: Create the JSON Schema**

Use Draft 2020-12, `additionalProperties: false`, and require this top-level shape:

```text
schema: const mastermind.single_name.identity_relationship_bundle/v1
version: const 1.0.0
bundle_id: ^snib_[0-9a-f]{64}$
issuer_subject
evidence_refs[]
relationships[]
authority: six const-false booleans
```

Freeze these nested definitions.

#### `issuer_subject`

```text
canonical_issuer_id: ^ISS:.+$ | null
resolution_state: resolved | owner_unresolved | not_admitted | conflict | unknown
resolution_receipt: data_os_issuer_receipt | null
owner_native_refs: array
external_ids: array
```

External CIK/name identity is separate evidence and never fills `canonical_issuer_id` by itself.

#### `counter_descriptor`

Used both inside relationships and evidence assertions:

```text
country: two uppercase letters
mic: four uppercase alphanumerics
observed_code: non-empty uppercase/digit/dot/dash string
trading_currency: three uppercase letters
security_kind: ordinary_share | ads | other
share_class: non-empty string
```

#### `counter_subject`

Contains one `counter_descriptor` plus:

```text
canonical_identity:
  resolution_state: resolved | owner_unresolved | not_admitted | conflict | unknown
  canonical_listing_id: string | null
  canonical_security_id: ^SEC:.+$ | null
  resolution_receipt: data_os_security_receipt | null
  absence_reason: no_security_evidence | not_admitted | identity_conflict | not_checked | unknown | null
```

#### Data OS receipts

Security receipt:

```text
authority_owner: const data_os
master_artifact: const data/reference/security_master.parquet
master_receipt_ref: const data/reference/_receipt.json
master_digest: ^sha256:[0-9a-f]{64}$
observed_at: date-time
```

Issuer receipt is identical except `master_artifact = data/reference/issuer_master.parquet`.

#### `evidence_ref`

```text
ref_key
source_kind: issuer_primary | exchange_primary | data_os | owner_native
locator
observed_at: date-time
published_at: date-time | null
assertion:
  relationship_type: same_economic_security | represents_units_of
  counter_members: array[counter_descriptor] | null
  source_counter: counter_descriptor | null
  source_units: positive integer | null
  target_units: positive integer | null
```

Schema conditionals:

- `same_economic_security` assertion requires at least two `counter_members`; source counter/units are null.
- `represents_units_of` assertion requires `source_counter`, positive `source_units`/`target_units`; `counter_members` is null.

#### `relationship`

`oneOf` two closed shapes.

**`same_economic_security`**

```text
relationship_id: ^snir_[0-9a-f]{64}$
relationship_type: const same_economic_security
counter_members: minimum 2 counter_subject records
source_counter: null
target_relationship_id: null
unit_relationship: null
evidence_ref_keys: non-empty unique array
clock:
  known_at: date-time
  effective_state: known | unknown
  effective_from: date | null
  valid_to: date | null
correction_state: current | corrected | superseded | conflict | unknown
authority: const descriptive
```

**`represents_units_of`**

```text
relationship_id: ^snir_[0-9a-f]{64}$
relationship_type: const represents_units_of
counter_members: empty array
source_counter: counter_subject
target_relationship_id: ^snir_[0-9a-f]{64}$
unit_relationship:
  source_units: positive integer
  target_units: positive integer
evidence_ref_keys: non-empty unique array
same clock/correction/authority shape
```

Cross-record target existence, member/evidence equality and canonical ID pair checks belong to Python semantic validation.

- [ ] **Step 4: Create Alibaba reference fixture**

Required semantic content:

- issuer external CIK `0001577552`, but `canonical_issuer_id=null`, `resolution_state=owner_unresolved`;
- 9988 / HKD and 89988 / CNY as ordinary-share counter subjects in one same-security relationship;
- BABA / USD / XNYS as ADS source counter in a conversion relation targeting that same-security relationship;
- conversion units `1 -> 8`;
- issuer-primary evidence assertion whose `source_counter` exactly matches BABA and whose units are `1 -> 8`;
- same-security evidence assertion whose `counter_members` exactly match the 9988/89988 descriptor set;
- canonical Data OS IDs remain unresolved in this design fixture; resolved-ID behavior is covered synthetically later;
- evidence `observed_at = 2026-08-28T11:00:00Z` and relationship `known_at` no earlier than that observation;
- `effective_state=unknown`, `effective_from=null` where the fixture is not freezing a sourced effective date;
- no price, FX, forecast, score or trade field;
- all authority false.

The first draft may use valid-pattern temporary `snir_...` / `snib_...` values. Task 2 normalizes and rewrites fixtures to their final deterministic IDs before the fixture becomes semantic golden truth.

- [ ] **Step 5: Create Tencent reference fixture**

Required semantic content:

- issuer external CIK `0001293451`, canonical issuer unresolved;
- 700 / HKD and 80700 / CNY ordinary-share counter subjects in one same-security relationship;
- exchange/issuer evidence assertion with an exact two-member descriptor set matching the relationship;
- no KWEB/TCEHY proxy semantics in this identity contract;
- canonical Data OS fields unresolved unless a synthetic resolved receipt is intentionally added by a test;
- same clock and authority law as Alibaba.

- [ ] **Step 6: Prove schema green**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_v1_schema_accepts_alibaba_and_tencent_reference_fixtures -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add contracts/single_name_intelligence/identity_relationship.v1.schema.json tests/fixtures/single_name_intelligence tests/test_single_name_identity_relationship.py
git commit -m "contracts(sni): freeze identity relationship wire"
```

---

### Task 2: Implement deterministic normalization, relationship graph IDs and base validation

**Files:**
- Create: `lib/single_name_intelligence/__init__.py`
- Create: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`
- Normalize: both positive fixture JSON files

**Public API:**

```text
SingleNameIdentityError
canonical_json_bytes(value) -> bytes
compute_relationship_id(relationship) -> str
compute_bundle_id(bundle) -> str
normalize_identity_relationship_bundle(bundle) -> dict
validate_identity_relationship_bundle(bundle) -> dict
```

- [ ] **Step 1: Write the failing public-API/determinism tests**

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

    shuffled = copy.deepcopy(payload)
    shuffled["evidence_refs"] = list(reversed(shuffled["evidence_refs"]))
    shuffled["relationships"] = list(reversed(shuffled["relationships"]))
    for relation in shuffled["relationships"]:
        relation["evidence_ref_keys"] = list(reversed(relation["evidence_ref_keys"]))
        if relation["counter_members"]:
            relation["counter_members"] = list(reversed(relation["counter_members"]))

    assert normalize_identity_relationship_bundle(shuffled) == normalized
```

- [ ] **Step 2: Prove red**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py::test_relationship_and_bundle_ids_are_deterministic_and_order_stable -q
```

Expected: collection FAIL because `lib.single_name_intelligence` is absent.

- [ ] **Step 3: Implement module skeleton**

`identity_relationship.py` begins:

```python
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from lib.dataos.identity import normalize_hk_symbol, parse_id, parse_listing_key

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

Load the schema once and build a Draft 2020-12 validator with `FormatChecker()`.

- [ ] **Step 4: Implement canonical ordering and two-pass ID remap**

Counter descriptor sort key:

```text
(country, mic, observed_code, trading_currency, security_kind, share_class)
```

Canonicalize:

1. evidence assertion `counter_members` by descriptor sort key;
2. evidence refs by `ref_key`;
3. relationship `counter_members` by descriptor sort key;
4. relationship `evidence_ref_keys` lexically.

Then normalize relationship IDs in dependency order:

1. normalize and compute all `same_economic_security` relationship IDs;
2. build `old_relationship_id -> new_relationship_id` map for those records;
3. rewrite every `represents_units_of.target_relationship_id` through that map;
4. compute conversion relationship IDs after target rewrite;
5. sort all relationships by final relationship ID;
6. compute bundle ID from the fully canonical bundle with `bundle_id` removed.

This is required so a draft fixture can be normalized once without a circular manual hash exercise.

- [ ] **Step 5: Implement ID helpers**

```python
def compute_relationship_id(relationship: Mapping[str, Any]) -> str:
    payload = {str(key): value for key, value in relationship.items() if key != "relationship_id"}
    return "snir_" + sha256(canonical_json_bytes(payload)).hexdigest()


def compute_bundle_id(bundle: Mapping[str, Any]) -> str:
    payload = {str(key): value for key, value in bundle.items() if key != "bundle_id"}
    return "snib_" + sha256(canonical_json_bytes(payload)).hexdigest()
```

- [ ] **Step 6: Implement base schema/ID/authority validation**

Stable reason prefixes:

```text
SNI1A_R001_SCHEMA
SNI1A_R002_RELATIONSHIP_ID
SNI1A_R003_BUNDLE_ID
SNI1A_R004_AUTHORITY
```

`validate_identity_relationship_bundle()` must:

1. keep the caller's original IDs for mismatch detection;
2. normalize a deep copy;
3. schema-validate normalized content;
4. reject original non-temporary IDs that disagree with computed IDs;
5. require the exact all-false authority block;
6. return normalized content without mutating caller input.

For initial temporary fixture IDs, use one explicit development-only sentinel format accepted by the schema, for example all-zero hashes. Normalization may replace exactly that sentinel. Any other mismatched supplied ID is an error. Remove sentinels from golden fixtures in Step 7.

- [ ] **Step 7: Rewrite positive fixtures to final canonical SNI IDs**

Run this one-shot development command after the module exists:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from lib.single_name_intelligence.identity_relationship import normalize_identity_relationship_bundle

root = Path("tests/fixtures/single_name_intelligence")
for name in (
    "alibaba_identity_relationship_valid.json",
    "tencent_identity_relationship_valid.json",
):
    path = root / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_identity_relationship_bundle(payload)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
PY
```

Then add:

```python
def test_golden_fixtures_are_already_canonical():
    for name in (
        "alibaba_identity_relationship_valid.json",
        "tencent_identity_relationship_valid.json",
    ):
        payload = _load_json(FIXTURE_DIR / name)
        assert normalize_identity_relationship_bundle(payload) == payload
        assert validate_identity_relationship_bundle(payload) == payload
```

- [ ] **Step 8: Run tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add lib/single_name_intelligence tests/fixtures/single_name_intelligence tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): validate deterministic identity relationships"
```

---

### Task 3: Enforce Data OS receipt semantics and observed-member consistency

**Files:**
- Modify: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`

- [ ] **Step 1: Add hostile resolved/unresolved tests**

Add tests for:

- unresolved member carrying canonical listing/security ID → reject;
- resolved member missing Data OS receipt → reject;
- resolved issuer missing issuer-master receipt → reject;
- unresolved issuer carrying `ISS:` canonical ID → reject;
- security ID and listing ID encoding different listing keys → reject;
- member descriptor country/MIC/code inconsistent with supplied canonical listing → reject.

Example:

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

Example mismatch:

```python
def test_resolved_member_must_match_observed_counter_descriptor():
    payload = _load_json(FIXTURE_DIR / "tencent_identity_relationship_valid.json")
    member = payload["relationships"][0]["counter_members"][0]
    member["canonical_identity"] = {
        "resolution_state": "resolved",
        "canonical_listing_id": "HK-XHKG-09988",
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

- [ ] **Step 2: Prove red**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: at least one new hostile test FAILS because semantic checks are absent.

- [ ] **Step 3: Implement stable errors**

```text
SNI1A_R005_UNRESOLVED_HAS_CANONICAL_ID
SNI1A_R006_CANONICAL_MEMBER_MISMATCH
SNI1A_R007_RESOLVED_WITHOUT_DATAOS_RECEIPT
```

Rules:

- `resolution_state == resolved` requires canonical fields and matching Data OS receipt.
- every non-resolved state requires canonical fields + resolution receipt to be null.
- security ID parses as kind `security`; listing ID parses as kind `listing`.
- security ID and listing ID must encode the same `ListingKey`.
- parsed listing country and MIC must equal the member descriptor.
- for `XHKG`, `normalize_hk_symbol(observed_code)` must equal the supplied canonical listing key; this is a pure consistency check, not authority minting.
- for other current SNI-1A reference MICs, parsed listing code must equal `observed_code.upper()` and MIC/country must match.
- resolved issuer requires a Data OS issuer-master receipt and a parsed `ISS:` ID.
- external CIK/name references never change canonical resolution state.

Never open Data OS artifacts in this module.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/single_name_intelligence/identity_relationship.py tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): enforce Data OS identity receipts"
```

---

### Task 4: Bind relationships to exact source assertions and clocks

**Files:**
- Modify: `lib/single_name_intelligence/identity_relationship.py`
- Modify: `tests/test_single_name_identity_relationship.py`

- [ ] **Step 1: Add same-economic-security hostile cases**

Reject:

1. duplicate counter descriptors in one relationship;
2. member `security_kind` mismatch;
3. member `share_class` mismatch;
4. fewer than two distinct members;
5. missing evidence key;
6. evidence assertion whose member descriptor set differs from relationship member set;
7. relationship `known_at` earlier than any referenced evidence `observed_at`.

Use:

```text
SNI1A_R008_SAME_SECURITY_MEMBER_INVALID
SNI1A_R010_EVIDENCE_CLOCK_INVALID
SNI1A_R012_EVIDENCE_MEMBER_MISMATCH
```

- [ ] **Step 2: Add conversion hostile cases**

For Alibaba, mutate relationship units to `1 -> 1` while leaving evidence `1 -> 8`:

```python
def test_baba_unit_relation_must_match_source_evidence_assertion():
    payload = _load_json(FIXTURE_DIR / "alibaba_identity_relationship_valid.json")
    conversion = next(
        relation
        for relation in payload["relationships"]
        if relation["relationship_type"] == "represents_units_of"
    )
    conversion["unit_relationship"] = {"source_units": 1, "target_units": 1}
    with pytest.raises(SingleNameIdentityError, match="SNI1A_R009"):
        validate_identity_relationship_bundle(payload)
```

Also reject:

- conversion target absent from bundle;
- target exists but is not same-security;
- source counter is not ADS;
- evidence assertion relationship type differs;
- evidence `source_counter` descriptor differs from relationship source counter;
- units differ from every referenced evidence assertion.

Use:

```text
SNI1A_R009_UNIT_ASSERTION_MISMATCH
SNI1A_R011_TARGET_RELATION_INVALID
SNI1A_R013_EVIDENCE_SOURCE_COUNTER_MISMATCH
```

- [ ] **Step 3: Prove red**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: new hostile cases FAIL before semantic checks are implemented.

- [ ] **Step 4: Implement evidence/graph validation**

Order:

1. build `evidence_by_key`, reject duplicate keys;
2. build `relationship_by_id`, reject duplicate IDs;
3. resolve every relationship evidence key;
4. parse evidence/relationship datetimes and require `known_at >= every referenced observed_at`;
5. enforce clock effective-state/null pairing;
6. same-security: compare canonicalized descriptor SET from relation against at least one referenced same-security assertion's exact descriptor SET;
7. same-security members must share `security_kind` and `share_class` and be unique;
8. conversion target must resolve to same-security relationship in the same bundle;
9. conversion source must be ADS;
10. at least one referenced conversion assertion must exactly match the source descriptor and unit ratio.

Source evidence extraction can still be wrong; SNI-1A's job is to prevent the wire from contradicting the structured assertion it claims to rely on. Actual source parsing belongs to later owner adapters.

- [ ] **Step 5: Prove no BABA hard-code**

Add a synthetic test that copies Alibaba, changes conversion relationship and evidence units together to `1 -> 2`, normalizes IDs, and validates. Expected: PASS. This proves source consistency, not company-specific code, governs the ratio.

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lib/single_name_intelligence/identity_relationship.py tests/test_single_name_identity_relationship.py
git commit -m "feat(sni): bind identity relations to source assertions"
```

---

### Task 5: Lock the no-owner-I/O boundary and document the contract

**Files:**
- Create: `contracts/single_name_intelligence/README.md`
- Modify: `lib/single_name_intelligence/__init__.py`
- Modify: `tests/test_single_name_identity_relationship.py`

- [ ] **Step 1: Add static no-owner/runtime I/O guard**

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
    assert not sorted(name for name in imports if name.startswith(forbidden_prefixes))
    assert "VendorAliasTable" not in source
    assert "IssuerMaster" not in source
    assert ".write_text(" not in source
    assert ".write_bytes(" not in source
    assert "requests." not in source
```

Permitted Data OS imports: `parse_id`, `parse_listing_key`, `normalize_hk_symbol` only.

- [ ] **Step 2: Export the public API**

`lib/single_name_intelligence/__init__.py`:

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

- [ ] **Step 3: Write contract README**

Must state:

- Data OS owns canonical issuer/security/listing identity.
- `company_identity.v1` and other owner-native identities remain PIT/event bridges, not a second master.
- SNI-1A reads no owner and stores nothing.
- `same_economic_security` groups source-observed counters descriptively; it creates no `SEC:` ID.
- `represents_units_of` is source-assertion and unit explicit.
- resolved Data OS IDs require receipts; unresolved state is first-class.
- `snir_`/`snib_` identify SNI relationship records/bundles only.
- correction persistence belongs to later SNI composition; this module persists nothing.
- no price/FX/forecast/score/rank/gate/size/signal/escalation/trade authority exists.
- SNI-1C owns stale-FX/asynchronous comparison guards.

- [ ] **Step 4: Run focused tests and compile check**

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
python3 -m compileall -q lib/single_name_intelligence
```

Expected: both exit 0.

- [ ] **Step 5: Run adjacent Data OS identity regressions**

```bash
python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_identity_seam_agreement.py -q
```

Expected: PASS; SNI-1A changes no Data OS behavior.

- [ ] **Step 6: Run Agent OS validation**

```bash
python3 scripts/agentos.py validate
```

Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add contracts/single_name_intelligence/README.md lib/single_name_intelligence/__init__.py tests/test_single_name_identity_relationship.py
git commit -m "docs(sni): freeze relationship contract boundary"
```

---

## Final Exact-Head Verification

Before requesting review:

```bash
python3 -m pytest tests/test_single_name_identity_relationship.py -q
python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_identity_seam_agreement.py -q
python3 -m compileall -q lib/single_name_intelligence
python3 scripts/agentos.py validate
```

Then require hosted repository CI on the exact PR head. Do not call SNI-1A `PROVEN_LIVE`; it is a contract-only capability. Correct state after merge and exact-head validation is **BUILT_NOT_PROVEN / CONTRACT-FROZEN** until later SNI waves supply a real reference-twin owner path and consumer.

## Acceptance Checklist

SNI-1A is accepted only if:

- Alibaba 9988/89988 same-security relation validates and is bound to an exact source assertion member set.
- Tencent 700/80700 same-security relation validates under the same law.
- BABA 1:8 conversion validates against structured evidence.
- wrong ratio with unchanged evidence is rejected.
- a synthetic non-BABA ratio validates when relationship and evidence agree.
- unresolved canonical identity is legal and contains no canonical ID/receipt.
- resolved canonical identity requires a Data OS master receipt.
- resolved listing/security IDs agree with each other and with observed country/MIC/code.
- external CIK cannot self-promote into canonical Data OS issuer ID.
- SNI IDs never occupy `ISS:` / `SEC:` / Data OS listing namespaces.
- conversion targets are bundle-local and validated.
- evidence clocks are required and cannot post-date relationship `known_at`.
- no owner/network/store/runtime I/O enters the module.
- all authority remains false.
- no price or FX implementation enters SNI-1A.
- Data OS regression tests remain green.

## Plan self-review

- Every SNI-1A identity/counter requirement is covered; stale-FX comparison is explicitly held for SNI-1C by the binding amendment because SNI-1A has no price operation.
- Data OS remains the only canonical identity authority; this plan never writes its stores or invents a general namespace renderer.
- Economic-security semantics are relationships, not a parallel security-ID system.
- Evidence binds exact counter descriptors and conversion units, preventing generic relation labels from laundering mismatched members.
- Alibaba/Tencent facts live in fixtures/evidence and never leak into generic ticker branches.
- Golden fixture IDs become fully canonicalized within Task 2; no dummy ID survives final verification.
- No placeholder helper or undefined implementation step remains.

## Execution Recommendation

Preferred worker avenue after semantic registration: **Terra**. The architecture is frozen, the mission is bounded and contract-heavy, and the work does not justify scarce Fable principal capacity. Return to Sol before widening vocabulary, changing Data OS, introducing owner reads, adding price/FX logic, or moving any SNI-1B+ scope into this carrier.
