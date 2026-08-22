---
workstream: "WS:CN-LIMIT-ALPHA"
session: sol/chairman-tushare-compliance-override-2026-08-21
model: sol
ended_because: chairman_override_frozen_for_build
mission: >
  Execute the Chairman's 2026-08-21 final override: remove the CEO/Codex-generated
  TuShare license-document authorization system from the full-A spine and every active
  CN-Limit/TuShare authority document, while preserving independent technical readiness,
  PIT, provenance, canary, completeness, and DNR boundaries.
state_before: >
  DEP-CAI is done. DEP-EXACT is technically prepared but active code and R6 records still
  require a written commercial grant, authorization receipt, trust allowlist, and
  code-reviewed license-document hash before any full-A network/store mutation. Chairman
  states TuShare licensing/compliance was already verified internally and privately and
  that the controlling agreement cannot be disclosed to coding sessions or third parties
  because of NDA/confidentiality and privacy constraints. The Chairman overrules and
  nulls the later CEO/Codex licensing-document gate.
changed:
  - {path: agentos/decisions/DEC-CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE.md, what: "new binding Chairman decision"}
  - {path: agentos/decisions/DEC-CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT.md, what: "replaced by non-authoritative supersession tombstone"}
  - {path: agentos/discoveries/DSC-TUSHARE-TOKEN-IS-NOT-A-COMMERCIAL-GRANT.md, what: "replaced by superseded discovery tombstone; public-terms inference cannot reopen private compliance"}
  - {path: research/cn_limit/TUSHARE_VENDOR_LETTER_PACKET_2026-08-21.md, what: "cancelled; no vendor letter or license upload required"}
verified:
  - {claim: "Chairman is final authority for this override", result: "explicit operator instruction 2026-08-21"}
unverified:
  - {claim: "runtime/masterplan cleanup complete", what_would_verify: "the bounded implementation commission below plus tests and stale-reference sweep"}
unresolved:
  - "Runtime and active masterplan cleanup must land before DEP-EXACT can be reclassified from licensing-blocked to technical-readiness-only."
next_actions:
  - "Fable executes the bounded implementation commission in this handoff on the same PR/branch or a directly stacked implementation PR."
do_not_redo:
  - "Do not ask for, upload, inspect, hash, quote, summarize, or persist the private TuShare agreement or compliance evidence."
  - "Do not re-research public TuShare terms to adjudicate Mastermind-X's private compliance status."
  - "Do not reintroduce authorization-receipt/trust-allowlist/license-document gates under a new name."
  - "Do not weaken technical canary, completeness, PIT, source-row accounting, quota/rate or correction controls merely because the licensing gate is removed."
  - "Do not relax DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT."
decisions: ["DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE"]
---

# Fable implementation commission — Chairman TuShare override

## Observable mission

Make the current repository and runtime incapable of blocking or reopening TuShare use on
a requirement to disclose or validate private licensing documents. At completion, a coding
session reading code, tests, R6, the full-A contract, AgentOS, or generated governance docs
must learn exactly one compliance fact: **`CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`**, with
private agreement details explicitly out of coding scope.

## Why it matters

The existing full-A spine mixed confidential compliance custody into runtime authorization.
That both leaks sensitive compliance metadata and creates a false dependency that can stop
the exact-plane program after the Chairman has already resolved licensing privately.
Removing it unlocks the correct next job: technical canary/completeness, not legal-document
collection.

## Authority and precedence

1. Chairman operator override, 2026-08-21 — final authority.
2. `DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE` — binding repository record.
3. R6 architecture after amendment.
4. Historical CEO/Codex grant-gate documents — superseded/null, never active authority.

No model or worker may downgrade this decision based on public vendor terms or absence of
private agreement bytes in the repo.

## Exact scope

Repository: `mastermindx-market-intelligence/macro`.

### Runtime/code

`collectors/china_tushare_spine.py`:

- delete the written-license authorization subsystem rather than bypass it;
- remove `AUTHORIZATION_SCHEMA_VERSION`, `AUTHORIZATION_TRUST_SCHEMA_VERSION`,
  `CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256`,
  `AUTHORIZATION_REQUIRED_SCOPE`, `AUTHORIZATION_RECORDED_SCOPE`,
  `AuthorizationGrant`, authorization receipt/trust-allowlist loaders and validators,
  grant-document/hash/chain verification, and related private-store mirror files;
- remove CLI flags `--authorization-receipt` and `--authorization-trust-allowlist` and all
  required-argument/refusal behavior tied to them;
- remove authorization/grant/trust fields from runtime state/completeness manifests where
  they exist solely for license proof;
- update docstring/examples/comments so no coding-visible license document is required;
- preserve token secrecy: `TUSHARE_TOKEN` remains read only through the canonical client and
  is never logged/persisted;
- preserve `BULK_HISTORICAL_BACKFILL_READY` only as a **technical readiness** gate if its
  independent live-canary/throughput rationale still survives. Rename/reword comments and
  tests so it cannot be read as a licensing gate;
- do not automatically flip `BULK_HISTORICAL_BACKFILL_READY` in this PR unless the already
  frozen technical evidence bar is independently satisfied. The Chairman override removes
  licensing evidence, not canary correctness.

`tests/test_china_tushare_spine.py`:

- delete authorization-grant/trust-root tests;
- replace them with regression tests proving normal bounded collection no longer accepts or
  requires license-document arguments;
- add a source/AST regression that fails if any active spine code reintroduces the removed
  identifiers or private-license document gate vocabulary;
- keep secret-hygiene, fail-closed request/schema, range/cap, canary/readiness and
  completeness tests.

Inspect `.github/workflows/tushare-spine-backfill.yml` and any CLI wrapper. Remove license
receipt/allowlist inputs/secrets/arguments if present. Do not alter unrelated credentials.

### Active architecture / masterplan

Amend, do not merely annotate, active authoritative TuShare/CN-Limit documents so the old
requirement is not an executable prerequisite:

- `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`
- `research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md`
- `research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json`
- `research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md`
- `research/cn_limit/CN_LIMIT_R6_EXECUTIVE_HANDOFF_INDEX_2026-08-19.md` if it carries the gate
- `research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md` if it carries the gate
- `research/TUSHARE_P0_ENTITLEMENT_RIGHTS_MATRIX_2026-08-19.md` only for TuShare clauses that
  tell coding sessions the private licensing question remains open or require a vendor letter;
  preserve unrelated source/endpoint/rights findings.
- `research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md`: preserve its historical operator wiring
  rulings; make clear Chairman 2026-08-21 private-compliance status is current authority if
  later text conflicts.

Required masterplan replacement rule:

> TuShare licensing/compliance: `CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`. The controlling
> agreement and supporting evidence are confidential and outside coding/agent scope under
> NDA/privacy constraints. No coding session or runtime gate may request or verify those
> documents. DEP-EXACT gates only on independently technical exact-plane correctness,
> access operation, canary, range-campaign and completeness requirements.

### AgentOS / durable memory

Update `WS-CN-LIMIT-ALPHA`:

- remove `WAITING_FOR_WRITTEN_VENDOR_GRANT` and the vendor-letter/receipt/allowlist ladder;
- record the Chairman override and set DEP-EXACT's remaining state to its truthful technical
  state (for example `TECHNICAL_CANARY_REQUIRED` / equivalent schema-valid status), based on
  what remains after code archaeology;
- name the exact next technical action;
- do not mark DEP-EXACT done merely because the licensing blocker is removed.

Amend the current CN-Limit handoff with the override or add a successor handoff that clearly
supersedes the licensing portions. Update generated governance/state docs that are derived
from AgentOS through their canonical generator rather than hand-editing generated output.

Review current China Alpha/TuShare rights records and active masterplans for the same specific
TuShare vendor-letter/license-upload requirement. Remove only this superseded construction;
do not weaken unrelated vendors' rights controls.

## Explicit non-goals

- no disclosure of private licensing terms;
- no legal re-analysis by the coding worker;
- no broad removal of rights controls for non-TuShare sources;
- no CN-Limit model, feature, rank, gate, score, size or UI implementation;
- no restored adjusted-plane W1-W3 evidence;
- no unauthorized claim that technical completeness is already proven;
- no raw TuShare redistribution policy invention — private agreement compliance remains a
  Chairman/compliance function, not something the coder infers.

## Ordered implementation sequence

1. Reconcile current `main` and open PRs touching the owned files.
2. Stale-reference census for all removed identifiers/phrases.
3. Runtime spine + CLI/workflow removal.
4. Tests: replace license-gate tests with anti-resurrection + retained technical controls.
5. Full-A contract amendment.
6. R6 freeze/registry/command packet/index amendment; update any manifest/hash relationships
   those mutable artifacts maintain, following repository precedent.
7. AgentOS workstream/handoff reconciliation and generated-doc refresh.
8. Repo-wide stale-reference sweep. Classify every remaining match as either:
   - historical tombstone/supersession statement; or
   - unrelated non-TuShare vendor control.
   No active TuShare requirement may remain.
9. Run targeted tests, AgentOS validate, relevant contract/registry/fence checks and CI.
10. Production-shaped dry-run/canary **planning** proof that no license-document argument is
    requested. Do not execute a bulk campaign unless the independent technical gate allows it.

## Acceptance tests

Must prove all of the following:

- importing/using the spine exposes no authorization-grant/trust-allowlist machinery;
- CLI help has no authorization receipt/trust-allowlist flags;
- bounded non-dry execution is not refused for missing license-document artifacts;
- token remains secret and required where network access actually occurs;
- technical `BULK_HISTORICAL_BACKFILL_READY` behavior, if retained, is justified only by
  canary/throughput/correctness and is unchanged by private licensing evidence;
- active R6/full-A/masterplan text contains no vendor-letter or uploaded-license dependency;
- current AgentOS context returns the Chairman-private compliance rule, not the old CEO rule;
- repo-wide search for the removed identifiers has no active-code/active-authority matches;
- unrelated vendor-rights controls remain intact;
- `python3 scripts/agentos.py validate` exits 0;
- relevant CI/fence suites are green.

## Stop condition

Stop and return to Sol only if removing the license subsystem would also remove a genuinely
independent technical integrity control that cannot be separated cleanly. Do not preserve the
license gate merely because tests or manifests are coupled to it; decouple them.

## Required continuation handoff

Return:
`STATUS / CHANGED PATHS / REMOVED GATES / RETAINED TECHNICAL GATES / MASTERPLAN RECONCILIATION / AGENTOS STATE / STALE-REFERENCE CENSUS / TESTS+CI / PRODUCTION-SHAPED PROOF / EXACT NEXT ACTION`.
