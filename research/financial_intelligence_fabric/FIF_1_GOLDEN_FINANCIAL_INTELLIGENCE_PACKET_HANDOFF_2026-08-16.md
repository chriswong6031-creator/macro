# FIF-1 Execution Handoff
## Golden Financial Intelligence Packet v1 — Hermetic Temporal Vertical Slice

**Workstream:** `WS:FINANCIAL-INTELLIGENCE-FABRIC`  
**Program:** `fundamental-forensics`  
**Packet:** `financial_intelligence_packet.v1`  
**Date:** 2026-08-16  
**Execution type:** One bounded code PR, then stop  
**Authority:** Display/context/research only  
**Primary outcome:** One deterministic, reusable packet proving that the existing governed metric query and provenance machinery can serve a product, API, dossier, Terminal client, and Neural Web without creating another semantic model.

## FIF-1R closure (operator review of 674f3a07)

FIF-1R stays on PR #5809. Do not start FIF-2.

- Pure kernel: `assemble_financial_intelligence_packet(...)` takes `PacketBuildContext` and `PacketEvidenceDigests`. Filesystem, schema load, and builder hashing live in `build_financial_intelligence_packet_from_repo` / the CLI.
- Formula evidence: unrequested dependencies occupy `evidence_cells`. Every formula `dependency_cell_id` must resolve inside the packet down to a direct source fact. User `cells` stay exactly the requested metric set.
- Schema: cell `oneOf` valued XOR non-valued. Both-null and both-set are invalid. Valued direct cells require accession/source/mapping receipts; valued formula cells require formula rule/digest/dependencies.
- Nested acceptance: synthetic 2024-12-31 debt/cash facts support a `net_debt` request that walks `total_debt` → three direct debt leaves + cash. Those facts are not in `DEFAULT_REQUESTED_METRICS`.
- Golden `content_sha256` is regenerated after this contract freeze and must be regenerated again after any builder-source edit.

See `DEC:FIF-1R-HERMETIC-PACKET-CONTRACT`.

---

# 1. Mission

Build a hermetic `financial_intelligence_packet.v1` contract and adapter over the existing Fundamental Forensics query machinery.

The packet must prove, with the existing deterministic fixture, that Mastermind can:

- select a governed set of financial metrics;
- preserve exact temporal policy and cutoffs;
- distinguish as-reported, latest-known-as-of, and latest-restated values;
- expose revisions without hindsight leakage;
- preserve direct and formula provenance;
- represent missing, unsupported, and not-evaluable states explicitly;
- produce deterministic bytes and a stable content hash;
- serve as the future common payload for Filing Forensics, Terminal, stock dossiers, Neural Web, API, and exports.

Do not build an API, UI, collector, publisher, peer engine, new database, or production AAPL pipeline in this PR.

---

# 2. Why this is the first build

The repo already contains:

- a 50-metric governed registry;
- a deterministic bitemporal query kernel;
- a Company Facts occurrence ledger;
- filing-clock and submissions logic;
- rich cell provenance;
- disclosure projection machinery.

The current Filing Forensics page does not consume those capabilities as a coherent reusable product contract.

This PR closes that seam without colliding with:

- FF-0 PR #5794, which currently owns `app/forensics.py`, private state, health, and the Filing Forensics UI;
- Earnings Intelligence E0 PR #5799, which owns the E0/E1/E2 architecture freeze;
- legacy attested-history Wave 0B, which is blocked on an operator credential.

The packet is the smallest valuable convergence point.

---

# 3. Preflight

Before editing:

1. Fetch current `origin/main`.
2. Record the exact base SHA in the PR and handoff.
3. Check PR #5794 status and changed files.
4. Check PR #5799 status and changed files.
5. Read:
   - `agentos/workstreams/WS-CALCBENCH-FILING-FORENSICS-PARITY.md`
   - `agentos/handoffs/CALCBENCH-FILING-FORENSICS-PARITY-2026-08-16.md`
   - `research/CALCBENCH_FUNDAMENTAL_FORENSICS_ENGINE_ASSESSMENT_AND_BUILD_DOCKET_FOR_FABLE.md`
   - `research/DO_NOT_REBUILD.md`
   - `engine/fundamental_forensics/query.py`
   - `engine/fundamental_forensics/metric_registry.py`
   - `engine/fundamental_forensics/companyfacts_ledger.py`
   - `tests/fixtures/fundamental_forensics/companyfacts_versions.json`
   - `tests/fixtures/fundamental_forensics/submissions_versions.json`
6. Search the repo for an existing equivalent packet contract or adapter.
7. If an equivalent canonical packet already exists, stop and report the exact path and overlap. Do not create a duplicate.
8. Confirm that the fixture can be transformed into the existing raw-ledger/query inputs without network access.
9. Confirm which existing CI lane runs `tests/test_fundamental_forensics_*`.

If CI registration requires editing a file still changed by open PR #5794, do not create a conflicting CI edit. Implement and test locally, then either:

- rebase after #5794 merges and add the minimal registration; or
- stop with the exact CI-registration blocker.

Do not work around the collision by creating a new CI job.

---

# 4. Allowed files

Preferred new files:

- `contracts/financial_intelligence_packet.schema.json`
- `engine/fundamental_forensics/financial_intelligence_packet.py`
- `scripts/build_financial_intelligence_packet.py`
- `tests/test_financial_intelligence_packet.py`
- `tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json`

Optional, only if required by an existing registry pattern:

- one small registry entry for the new contract;
- one minimal AgentOS handoff at PR completion;
- one minimal test-path registration after PR #5794 has merged or conflict is otherwise cleared.

Small modifications are allowed only in:

- `engine/fundamental_forensics/__init__.py`, if the existing package export convention requires it;
- an existing contract registry, if all comparable contracts are registered there.

Every modification outside the preferred new files must be justified in the PR body.

---

# 5. Forbidden files and work

Do not modify:

- `app/forensics.py`
- `engine/fundamental_forensics/private_state.py`
- `engine/fundamental_forensics/health.py`
- `templates/fundamental_forensics.html.j2`
- `templates/fundamental_forensics.js`
- `templates/fundamental_forensics.css`
- corresponding `site/fundamental_forensics*`
- attested-history credential, seed, verifier, admission, operator, or publisher files
- `.github/workflows/filing-forensics-sec.yml`
- `scripts/build_fundamental_forensics.py`
- `scripts/run_fundamental_forensics_wave2.py`
- Earnings Intelligence E0/E1/E2 documents or implementation
- Terminal repository code
- Neural Web runtime code
- Prophet code
- the metric registry’s metric inventory
- the existing query policies
- SEC acquisition code
- R2 object layouts
- public navigation.

Do not:

- add a network call;
- fetch SEC data;
- write to R2;
- create a database;
- create an endpoint;
- create a page;
- add a detector;
- add a peer comparison;
- add an LLM;
- add a score;
- change the current customer projection;
- claim production or point-in-time activation.

---

# 6. Contract requirements

The JSON Schema must be Draft 2020-12 or match the repo’s current contract convention.

The root object must be closed-world unless existing house style requires narrowly documented extension points.

Required root fields:

```yaml
schema: financial_intelligence_packet.v1
packet_id: stable content-derived identifier
content_sha256: digest of the canonical packet body
entity:
  entity_id:
  cik:
  ticker:
  name:
query:
  policy:
  source_event_cutoff:
  system_recorded_cutoff:
  requested_metrics:
  requested_periods:
governance:
  metric_registry_version:
  metric_registry_digest:
  query_engine_version:
  packet_builder_version:
  packet_builder_digest:
periods: []
cells: []
revisions: []
disclosure_changes: []
coverage:
limitations: []
receipts:
authority:
  class: context_only
  display_only: true
```

No wall-clock generation time may be labeled as source freshness.

A `built_at` field is optional only when the caller injects it. It must not affect `packet_id` or `content_sha256`.

## 6.1 Entity

Required:

- canonical entity identifier available in the fixture path;
- CIK;
- ticker, when supplied by the caller;
- legal name;
- explicit identity basis.

The fixture entity is synthetic. Do not pretend it is AAPL.

## 6.2 Query policy

Allowed values must be the existing query-policy vocabulary, not a new vocabulary.

The packet must record:

- source-event cutoff;
- system-recorded cutoff;
- selected policy;
- requested metric IDs;
- requested period IDs;
- whether the request is historical replay or retrospective research.

Both cutoffs are mandatory for historical policies.

## 6.3 Cells

Each cell must carry:

- stable cell ID;
- metric ID;
- label;
- statement family;
- period;
- value or explicit non-value state;
- unit;
- direct or formula status;
- source occurrence IDs;
- accession;
- concept;
- taxonomy;
- source URL or canonical source reference when present in the existing provenance object;
- source digest;
- source-event time;
- system-recorded time;
- mapping rule ID and digest;
- formula rule ID and digest when applicable;
- dependency cell IDs when applicable;
- quality state;
- coverage state.

A cell may not contain both a numeric value and a missing state.

Required non-value states:

- `missing`
- `unsupported`
- `not_evaluable`
- `not_applicable`

Use existing vocabulary where the query kernel already defines equivalent values. Do not create duplicate aliases.

## 6.4 Revisions

A revision record must identify:

- metric;
- period;
- original value and accession;
- revised value and accession;
- original source-event and recorded clocks;
- revised source-event and recorded clocks;
- absolute and percentage delta when mathematically valid;
- whether the revision is visible under the selected policy and cutoffs;
- exact cell or source receipts.

The packet must not include a revision that was not knowable by the selected cutoffs unless the policy is explicitly retrospective/latest-restated.

## 6.5 Disclosure changes

This field may be empty in the fixture packet.

The contract must support future bounded entries containing:

- disclosure family;
- prior and current document/accession;
- exact source receipts;
- deterministic change type;
- title and short factual summary;
- coverage;
- display/context authority.

Do not synthesize a disclosure change from the numeric fixture.

## 6.6 Coverage

Required coverage dimensions:

- requested metrics;
- valued metrics;
- missing metrics;
- unsupported metrics;
- direct cells;
- formula cells;
- periods requested;
- periods returned;
- source-trace complete count;
- governance-trace complete count;
- revision coverage;
- disclosure coverage state.

Coverage is evidence availability, not a company-quality score.

## 6.7 Limitations

The fixture packet must state at least:

- synthetic fixture entity;
- no production source claim;
- no broad issuer coverage claim;
- no filing-package rendering;
- no disclosure projection in this fixture unless explicitly supplied;
- no peer context;
- no market interpretation;
- no trading authority.

## 6.8 Receipts

The packet must include:

- input fixture digests;
- submissions fixture digest;
- registry digest;
- builder code/config digest;
- query request digest;
- response or packet-body digest;
- source and governance receipt counts.

Do not include credentials, object keys, private raw rows unrelated to the packet, or local absolute paths.

---

# 7. Determinism and canonicalization

Implement one canonical serialization function.

Requirements:

- UTF-8;
- stable key ordering;
- stable list ordering;
- no incidental dictionary order;
- no NaN or Infinity;
- normalized date/time representation;
- stable decimal/number policy;
- no host path;
- no process ID;
- no random UUID;
- no implicit current time;
- no environment-dependent fields.

`packet_id` must be derived from canonical content.

Recommended form:

`fip_<first 24 lowercase hex characters of content_sha256>`

Digest construction:

1. Build packet body without `packet_id` and `content_sha256`.
2. Canonically serialize the body.
3. SHA-256 the canonical bytes.
4. Add `content_sha256`.
5. Derive `packet_id`.
6. Serialize the final packet canonically.

A repeated build with identical inputs must produce byte-identical output.

---

# 8. Fixture laws

**Operator supersession 2026-08-16 (`DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE`):**
do not manufacture the filing-authority ledger from Company Facts rows. Query
input is the independent synthetic filing-package fixture:

- `tests/fixtures/fundamental_forensics/filing_package_raw_ledger_v1.json`

Keep as separate occurrence-inventory witnesses (hashed in packet receipts only):

- `tests/fixtures/fundamental_forensics/companyfacts_versions.json`
- `tests/fixtures/fundamental_forensics/submissions_versions.json`

The tests must prove these laws against the filing-package fixture through the
existing query kernel. The numeric/temporal laws are unchanged.

The tests must prove these laws.

## Law 1 — Original value

For the 2023 revenue period, the original filing value is:

`1050`

under an as-reported policy selecting the 2024 filing.

## Law 2 — Later revision

The same 2023 revenue period later appears as:

`1060`

in the 2025 filing.

The packet must expose the revision only when the selected policy and cutoffs permit it.

## Law 3 — No future leakage

A source-event or recorded cutoff before the 2025 filing cannot return `1060` as the latest-known value.

It must return `1050`, or an explicit absence if the earlier cutoff predates the original filing.

## Law 4 — Pre-original absence

A cutoff before the original 2024 filing must not return either value.

## Law 5 — Deterministic duplicate handling

The fixture contains a duplicate original revenue occurrence.

The result and provenance must be deterministic and must not double count.

## Law 6 — Restated hindsight is labeled

A latest-restated request may return `1060`, but the packet must identify:

- the revised accession;
- the original accession;
- that the result uses a later restatement;
- the exact policy.

## Law 7 — Other revised facts follow the same rule

At least one additional revised metric in the fixture must prove the same temporal behavior, such as receivables, inventory, capex, operating income, net income, operating cash flow, or assets.

Do not hard-code metric names that are not governed by the current registry. Select a governed fixture-compatible metric.

## Law 8 — Extension fact is not silently standardized

The fixture extension concept `CustomerCount` must remain:

- explicit raw/extension evidence; or
- unsupported/unmapped;

unless an existing governed mapping already covers it.

Do not add a mapping in this PR.

## Law 9 — Formula provenance

Select at least one formula metric already supported by the current registry and satisfiable from the fixture.

Its packet cell must include:

- formula rule ID and digest;
- dependency cell IDs;
- direct source receipts for all dependencies.

If no formula metric is satisfiable from the existing fixture and registry, stop and report that exact fixture limitation. Do not invent a formula.

## Law 10 — Every valued cell is reversible

Every numeric cell must have enough provenance to reach its source occurrence and accession.

## Law 11 — Same input, same bytes

Two builds in the same process and two builds in separate processes must produce identical bytes.

## Law 12 — No current clock

Monkeypatch or guard the packet module so an implicit `datetime.now`, `datetime.utcnow`, or equivalent current-time call fails the test.

---

# 9. Builder API

Preferred pure function:

```python
def build_financial_intelligence_packet(
    *,
    entity: EntityInput,
    ledger: RawLedgerInput,
    filing_metadata: FilingMetadataInput,
    query_request: MetricQueryRequest,
    metric_registry: MetricRegistry,
    disclosure_projection: Mapping[str, Any] | None = None,
    built_at: datetime | None = None,
) -> dict[str, Any]:
    ...
```

Use the repo’s actual types where available. Do not create mirror dataclasses if the query module already exports appropriate request and result types.

Additional helpers may include:

```python
def canonical_packet_bytes(packet: Mapping[str, Any]) -> bytes:
    ...

def packet_digest(packet_body: Mapping[str, Any]) -> str:
    ...

def validate_packet(packet: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    ...
```

The builder must be pure with respect to:

- network;
- filesystem, except through the CLI wrapper;
- object store;
- environment;
- wall clock.

---

# 10. CLI

Provide a small offline CLI:

```text
python3 scripts/build_financial_intelligence_packet.py \
  --ledger tests/fixtures/fundamental_forensics/filing_package_raw_ledger_v1.json \
  --companyfacts-witness tests/fixtures/fundamental_forensics/companyfacts_versions.json \
  --submissions-witness tests/fixtures/fundamental_forensics/submissions_versions.json \
  --policy latest_known_as_of \
  --source-event-cutoff 2025-12-31T23:59:59Z \
  --system-recorded-cutoff 2026-08-05T12:00:02Z \
  --output /tmp/financial_intelligence_packet.json
```

The exact flags may follow existing CLI conventions.

Requirements:

- no default to “now” for cutoffs;
- explicit output path;
- atomic local write;
- schema validation;
- prints a bounded summary:
  - packet ID;
  - digest;
  - cell count;
  - revision count;
  - coverage;
- no full private packet dump to logs;
- no network;
- no R2.

---

# 11. Tests

Required test groups:

## 11.1 Schema

- valid golden packet passes;
- unknown root field fails if contract is closed-world;
- invalid authority fails;
- cell with both value and missing state fails;
- non-finite number fails;
- missing cutoffs fail for historical policy.

## 11.2 Temporal

- original revenue = 1050;
- later revision = 1060;
- no future leakage;
- pre-original absence;
- latest-restated is explicitly labeled;
- second revised metric follows same law.

## 11.3 Provenance

- every valued cell has source receipt;
- every mapped cell has governance receipt;
- formula dependencies are complete;
- accessions match fixture;
- duplicate occurrence handling is deterministic;
- extension fact is not silently mapped.

## 11.4 Determinism

- same process byte identity;
- subprocess byte identity;
- environment variable changes do not change bytes;
- local path changes do not change bytes;
- injected `built_at` does not change content hash if it is excluded by contract, or is rejected from identity if the design chooses no `built_at`.

## 11.5 Safety

- no network calls;
- no object-store writes;
- no implicit current time;
- no credentials or local absolute paths;
- authority remains context/display only.

## 11.6 Regression

Run existing focused suites for:

- query;
- metric registry;
- Company Facts ledger;
- temporal law;
- data contracts;
- Fundamental Forensics contract.

Do not broaden into unrelated repository-wide failures.

---

# 12. Expected golden output

Commit one canonical expected packet generated from the synthetic fixture.

The golden output must be small enough for review and must visibly demonstrate:

- entity identity;
- query policy and cutoffs;
- at least two periods;
- original/latest behavior;
- one revision;
- direct provenance;
- formula provenance if fixture-compatible;
- coverage;
- limitations;
- authority;
- content hash.

Do not commit a huge raw ledger or source-document body.

---

# 13. Acceptance checklist

The PR is acceptable only when all are true.

- [ ] One packet schema exists.
- [ ] One pure packet builder exists.
- [ ] One offline CLI exists.
- [ ] One human-reviewable golden packet exists.
- [ ] Original 2023 revenue is 1050.
- [ ] Revised 2023 revenue is 1060 only after permitted cutoffs.
- [ ] Pre-revision query never leaks 1060.
- [ ] Pre-original query returns explicit absence.
- [ ] Duplicate occurrence resolution is deterministic.
- [ ] Extension `CustomerCount` is not silently mapped.
- [ ] At least one formula metric has complete dependency provenance, or the session stops with a proven fixture limitation rather than inventing one.
- [ ] Every valued cell reverses to an accession and source receipt.
- [ ] Every mapped/formula cell carries governance rule IDs and digests.
- [ ] Missing and unsupported states are explicit.
- [ ] Packet bytes and digest are deterministic.
- [ ] No network, R2, implicit current time, random ID, or local path enters the build.
- [ ] Schema and focused regression tests pass.
- [ ] No forbidden files changed.
- [ ] PR body separates fixture-proven from production-wired.
- [ ] Session stops after PR stabilization.

---

# 14. Suggested test commands

Use the repo’s actual environment and adjust only paths, not scope.

```bash
python3 -m pytest \
  tests/test_financial_intelligence_packet.py \
  tests/test_fundamental_forensics_query.py \
  tests/test_fundamental_forensics_metric_registry.py \
  tests/test_fundamental_forensics_companyfacts_ledger.py \
  -q
```

Locate the exact existing test filenames before running; do not invent missing filenames.

Schema validation:

```bash
python3 scripts/build_financial_intelligence_packet.py \
  --companyfacts tests/fixtures/fundamental_forensics/companyfacts_versions.json \
  --submissions tests/fixtures/fundamental_forensics/submissions_versions.json \
  --policy latest_known_as_of \
  --source-event-cutoff 2024-12-31T23:59:59Z \
  --system-recorded-cutoff 2024-12-31T23:59:59Z \
  --output /tmp/fip.json
```

Determinism:

```bash
sha256sum /tmp/fip-a.json /tmp/fip-b.json
cmp /tmp/fip-a.json /tmp/fip-b.json
```

Run existing house-law and AgentOS validation only if required by the changed scope.

---

# 15. PR instructions

Suggested branch:

`claude/fif-1-golden-financial-intelligence-packet`

Suggested title:

`feat(forensics): add deterministic financial intelligence packet v1`

PR summary must state:

- it adapts the existing query and registry;
- it creates no new semantic model;
- it is hermetic and fixture-proven;
- it is not production-wired;
- it does not alter Filing Forensics UI or API;
- it does not touch attested history or Earnings Intelligence;
- it has zero signal, score, rank, gate, sizing, or trading authority.

Required maturity declaration:

```text
Contract: code-present + fixture-proven
Production source wiring: absent
Attested publication: absent
User-visible product: absent
Terminal integration: absent
Neural Web integration: absent
Prophet authority: none
```

---

# 16. Stop conditions

Stop immediately and report instead of expanding scope when:

1. An equivalent canonical packet already exists.
2. The query kernel cannot be invoked without a redesign.
3. The fixture cannot supply required filing metadata.
4. A formula metric cannot be proven from the current fixture and registry.
5. CI execution requires editing a file still in active conflict with PR #5794.
6. A needed type is private and exposing it would require a broad query-module refactor.
7. The only path forward requires network access or R2.
8. A temporal law is ambiguous in existing code.
9. The agent discovers an apparent value disagreement between fixture, ledger, and query results.

In each case:

- capture the exact file, symbol, input, expected behavior, and observed behavior;
- propose the smallest next decision;
- do not build a workaround;
- stop.

---

# 17. Completion handoff

At PR completion, write a concise handoff with:

- base and head SHA;
- changed files;
- contract version;
- exact fixture inputs and digests;
- exact expected values;
- test commands and counts;
- maturity declaration;
- unverified production claims;
- any fixture or formula limitation;
- CI status;
- next recommended handoff;
- files the next session must not redo.

The next handoff should be **FIF-2 Read-Only Query API**, but only after:

- PR #5794 is merged or app-route conflicts are cleared;
- the packet contract is accepted;
- the operator decides whether the first live issuer uses the attested AAPL snapshot or a clearly labeled shadow source package.

Do not begin FIF-2 in this session.
