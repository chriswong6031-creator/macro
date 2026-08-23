# K1 Evidence Foundation contract freeze — 2026-08-23

Status: **REPAIRED CANDIDATE; PHYSICAL STORE REFUSED; FRESH REVIEW PENDING**

This is the K1 / FABLE-A return packet. It freezes a shared pointer vocabulary over
owner-native evidence without creating a new truth store, reader plane, index,
scheduler, ranker, gate, sizer, originator, or entry authority. It starts no K2, K3,
K4, B1, K2-B, or D5-EARNINGS work.

## 1. Authority and current-state reconciliation

The protected Sol Skillpack was loaded atomically from the current protected
`mastermindx-market-intelligence/Mastermind` `master` commit:

- repository commit: `db0bac5fe3f72348262d42c8bd26b836bda9f61d`
- Skillpack tree: `0a009d5314a4a3bbb1aac2f111b68644fc7a64d8`
- schema: `mastermind.sol_skillpack.v1`
- version: `1.0.0`
- minimum bootstrap major: `1`
- protected branch evidence: strict required check `test`; `enforce_admins=true`
- procedure blobs from that same commit:
  - `BOOTSTRAP_KERNEL.md` — `75bd572bd43c3666dd751b40ba578740d6a55b83`
  - `CLOSEOUT.md` — `c7ed91693d65b27d73631b89b6bc1d70d3b5af06`
  - `COLD_START.md` — `e1d8185c28ece624abcb73cc7b04c863c4634988`
  - `COMMISSION_WAVE.md` — `df6d974367d72d5fbbc16eb19c5fb5febe04936d`
  - `INDEX.md` — `bd11694aea5ad8c6aba1245ba2b04c5d3185267e`
  - `RECONCILE_STATE.md` — `d7113c723656b5f22d61ec6b9924e38b3d93c73c`
  - `REVIEW_RETURN.md` — `e1e35ebb0b8d70ebd30f6010936894bf26c13fd3`

The handoff's Mastermind pin is exactly current. The Macro handoff pin
`fb2375441f21b94201edc4ed6ac2c40f67274cde` remains an ancestor, but is historical.
The repaired candidate was reconciled against fresh Macro `origin/main`
`7cc324f2e1c6425ac9710863b3aa4ca8ac20b7c4`. Since the first K1 candidate base,
the first K1-owner-area mainline change was #6308 in
`engine/company_intelligence/event_workspace_build.py`: it carries corrected
lifecycle state forward and adds the filing form inside an existing workspace source
row. It does not change `WORKSPACE_SCHEMA`, `WORKSPACE_KEYS`, or the three native
workspace clocks. #6312
later added a display-only supplier-language annotation to the government award-event
parser; it did not change `EVENT_CONTRACT`, native `event_id`, registered event clocks,
or `_validated_award_events`. #6302 then merged as
`e210a80d2bad56b351d90ef82ddaa4ec114887b9`, adding the AAPL FY2026 Q3 10-Q and
stable Earnings event reference on main. The later #6324 records closeout now
classifies FIF-3A2 as `ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN` after Sol PASS /
`ACCEPTED_FOR_LANDING` on exact product head
`9598c5430c587b2ec9d1f84d3fa6e2d704808bcc`. Its decision also explicitly keeps
the production attested issuer service `NOT_BUILT` and FIF-3 `IN_PROGRESS`; accepted
golden-fixture/on-main status is not production/live proof. The remaining base movement
through `7cc324f2e1c6425ac9710863b3aa4ca8ac20b7c4` touched Agent OS governance,
Intelligence Workspace, render, press, records, Canada/public display, marketing
publication, and research-vault data rather than changing a registered K1 owner
contract. K1 did not start, modify, or extend D5; it only reconciled already-merged
owner source on its base.

The current Mastermind strategic state remains
`mastermind.strategic_state.v1`, phase `PRE_REVENUE_MVP_CONVERGENCE`, with the
Executive hierarchy Chairman Chris → CEO Sol → COO Fable → workers. The standing
`duplicate_control_planes` prohibition is binding. Agent OS remains a knowledge
plane with no runtime authority.

### Stale FIF / Fundamental Forensics prose reconciled

Historical stop prose in the c0 packet is no longer current PR state:

| Carrier | Current GitHub state | Exact receipt | What it proves |
|---|---|---|---|
| FIF-1R3 #5889 | merged 2026-08-19 | `f4183edade53603fad7a97f702eb4c6e5eabff5d` | `financial_intelligence_packet.v1` is accepted mainline contract/code; merge alone does not prove every later production wave |
| FF-1P2R #5898 | merged 2026-08-22 | `21f51a1ecfed778a738b048bd7e5efd30b1d9336` | current-quarter EDGAR discovery landed; no inference of unrelated production readiness |
| FF-1R #6285 | merged 2026-08-23 | `1e7d9f5030fd7c7c06fb03f022857510c5d0f9ed` | bounded July recovery is accepted mainline owner law |
| FIF-3A2 #6302 + closeout #6324 | merged and Sol-accepted golden fixture 2026-08-23 | `e210a80d2bad56b351d90ef82ddaa4ec114887b9` (accepted product head `9598c5430c587b2ec9d1f84d3fa6e2d704808bcc`); decision `DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN` at `8c125a80bc8c` | `ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN`; production attested issuer service remains `NOT_BUILT`, FIF-3 remains `IN_PROGRESS`, and no production/live state is inferred |

K1 therefore uses current owner contracts and fixtures. It distinguishes Sol's
exact-head acceptance and on-main golden-fixture state from absent production/live
service proof, and it does not extend FIF-3A2.

## 2. Physical-store flip-condition verdict

**Verdict: FALSE. Do not build a physical Evidence Mesh.**

The binding flip condition requires a **named PR or workstream committed to consume,
in one query, native objects across at least three owner stores for one subject
without importing those engines**. Current `origin/main`, Agent OS, the active build
map, open PRs, and live worktrees contain no such committed consumer. The only hits
for the exact requirement are the A0 hypothetical/gate text and the FABLE-A dispatch
decision itself:

```text
research/evidence_mesh/A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md
agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md
agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-19.md
agentos/decisions/DEC-ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH.md
```

The A0 Brain example is hypothetical and cannot self-certify demand. No open PR
touches the K1 target paths. Live worktree census likewise shows no sibling K1
worktree or proposed-path owner. The contract therefore keeps owner readers direct.

Consequences:

- no `data/evidence_mesh/` or `data/evidence_foundation/`
- no `engine/evidence_mesh/`
- no database, index, warehouse, truth mirror, control plane, or global reader
- no `config/synapse.yml` entry for a nonexistent artifact
- no native evidence bodies copied into a shared store

Any later store requires a new named committed consumer, new persistence
adjudication through Data OS conventions, an owner, producer, native
`asof_field`, freshness SLA, and Synapse registration. K1 does not pre-authorize it.

## 3. Frozen contract surface

The contract version is `1.0.0`:

- `.github/ci/legacy-jobs.yml` — binding run in the existing signal-contract lane
- `contracts/evidence_foundation/reference.v1.schema.json` — closed JSON Schema wire
- `contracts/evidence_foundation/vocabulary.v1.json` — 13 source-bound owner identity/schema/type/clock/accessor bindings
- `contracts/evidence_foundation/README.md` — interoperability law
- `lib/evidence_foundation.py` — the canonical combined JSON-Schema plus semantic fail-closed validator

The reference is a pointer only. Its deterministic `reference_id` is `efr_` plus
SHA-256 over canonical JSON of the complete object excluding only `reference_id`.
No join/write clock is added to content identity.

### Object classes and authority boundary

The five object classes are distinct:

- `world_observation`
- `derived_view`
- `system_belief`
- `forward_claim`
- `instrument_state`

Every wire object must materialize this exact authority envelope:

```json
{
  "can_rank": false,
  "can_gate": false,
  "can_size": false,
  "can_originate": false,
  "can_open_entry": false
}
```

Absence defaults down semantically but fails the v1 wire, so no producer can gain
authority by omission. `ENTRY_OPEN` remains false.

### Canonical identity and clock law

Owner-native identity is reused. K1 mints no universal entity id and excludes
`ticker_store_key` and a Stock Identity behavioral fingerprint as entity identities.
CIK ↔ security/listing joins are only through the current PIT owner alias; the struck
symbol-directory plus `cik_map` branch stays forbidden. Theme node ids preserve their
owner epoch semantics.

Seven clock classes are frozen without renaming native fields:

| Class | Meaning |
|---|---|
| `world_valid` | when the fact/state applies in the world |
| `source_published` | when the owner source published/accepted it |
| `knowable` | when it became lawfully available to the system |
| `observed` | when the owner actually retrieved or observed it |
| `system_recorded` | when the owner durably retained/registered it |
| `belief_or_build` | the owner's belief, vintage, or build clock |
| `review_due` | a future review/maturity deadline, never observation time |

Each vocabulary row carries `synapse_asof_field`. It is the existing Synapse field
when that exact owner-native object is registered (`computed_at` for Theme Graph,
`asof` for QLedger), and literal `null` otherwise. `null` prevents guessed catalog
clocks.

### Owner adoption inventory

The access column is intentionally typed. `parser` means the owner contract validates
caller-held canonical bytes; it is not represented as a store reader. `collection`
means the owner returns a native collection and the full native key selects one row.

| Owner object | Native identity | Key clock bindings | Owner accessor |
|---|---|---|---|
| Theme Graph evidence | `evidence_id` | published/effective/computed | `read_evidence` (collection) |
| Theme Graph edge belief | `edge_id + belief_time` | valid/evidence/belief/computed | `read_edges` (collection; historical selection) |
| FIF raw occurrence | `occurrence_id` | all five `TemporalClocks` fields | `RawFactLedger.by_id` (direct) |
| FIF packet | `packet_id` | source/system cutoffs, governance, build | `validate_packet_semantics` (parser) |
| Earnings workspace generation | `generation_id + event_id` | lifecycle available/observed, generated | `validate_event_workspace` (parser; native identity checked) |
| Institutional 13F receipt | `filer_cik + accession + receipt_id` | report/accepted/retained | `RawEvidenceReceipt.from_json_bytes` (parser) |
| GovRev event v2 | `event_id` | effective/known/first-seen/last-seen | `_validated_award_events` (collection) |
| Bio current source snapshot | `nct_id + source_snapshot_id` | effective/published/dataset/update/retrieved/first-seen/valid-from+to/transaction-from+to | `validate_contract` (parser) |
| Bio history source snapshot | `nct_id + source_version + source_snapshot_id` | submitted/QC/retrieved/transaction-from+to | `validate_contract` (parser) |
| TXI transition row | `chain + rev + episode_id + transition + hop + asof` | `asof` | `_read_ledger` (collection) |
| QLedger stored claim | `claim_id` | asof/vector-asof/registration/review-due | `load_claims` (collection) |
| Market Memory outcome | `outcome_record_id` | effective/available/known/observed/recorded | `load_record` (direct) |

The institutional census dedup precedent, Fundamental Forensics
`KnowledgeClock`/`VintagePolicy`, QLedger evidence-clock separation, and merged PIT
replay harness were explicitly included in the archaeology. Derived heads such as
the QLedger evidence-clock start and current Theme/TXI/workspace heads are excluded
from owner objects.

Data OS remains the canonical identity/join owner, but it is deliberately deferred
as an Evidence Foundation owner row. `IssuerMaster` is explicitly no-I/O;
`issuer_of_security` returns a scalar from a caller-constructed subset and is not a
native `security_master.parquet` object reader. K1 found no honest row-returning
storage API and will not misclassify that convenience lookup as a direct reader.
Likewise, the public Earnings convenience reader follows the current marker and can
alias generations; K1 binds the native `event_workspace.v1` parser until a real
generation-aware reader exists.

### Relations, corrections, missingness, replay

- Every relation carries separate source-independence, information-novelty, and
  economic/mechanism-independence axes. V1 records them only as
  `declarative_unverified`; it makes no detection or verification claim without
  typed deterministic owner lineage IDs.
- V1 permits no automatic effect: every relation carries `automatic_effect=false`
  and `deterministic_key=null` until a typed owner-native lineage key is frozen.
- `corroborates`, `contradicts`, `shares_upstream`, `corrects`, `supersedes`, and
  `projects` never auto-net, rank, promote, or suppress.
- Corrections append and name predecessor references. The `corrects`/`supersedes`
  relation target set must exactly equal the predecessor set, with the right relation
  kind and an honest native chronology-verification state. Predecessors never mutate.
- Missingness is typed and can never be substituted with zero.
- Every known replay cutoff is parsed even when unused. Historical replay refuses an
  unavailable vintage, requires known FIF accepted/recorded clocks, refuses any
  native clock beyond its class cutoff, and treats same-day date/datetime comparisons
  as ambiguous symmetrically. Current-rule recomputation remains the separate mode
  already present in owner/source law; K1 invents no new replay mode.

## 4. Golden fixture packet

The manifest freezes eight byte-receipted fixtures:

| Fixture | Verdict | Bytes | SHA-256 |
|---|---:|---:|---|
| `fif_packet_valid.json` | valid | 3168 | `d9657d3baa86ea1f60442b6e6a367e4831863aae01d1fc7510166dc312140861` |
| `earnings_workspace_valid.json` | valid | 2981 | `abf73734e79f21277b68a0dd4cf6347012b28287b484b69d96e284be9a771589` |
| `duplicate_corroboration_hostile.json` | invalid | 3667 | `f1731de02cbdec27aaab897a77215a4fdcdd5dbfb6879f64106b2b4fbcad652f` |
| `correction_append_valid.json` | valid | 3927 | `241550bbd082fab3dab321d4d071a90f505d2ef52ca38f437776d334bd6fa3fd` |
| `replay_valid.json` | valid | 3509 | `ea4e1c05568c004b371dcb721ebc9cf512f420482e0f926406882fc157bd8614` |
| `replay_lookahead_hostile.json` | invalid | 3415 | `4f24b366cad2f1344955b771adc8fe4614da9fe18cd66480c8ba4e05c0ee91b7` |
| `typed_missingness_valid.json` | valid | 2808 | `cece49f53fc161f7a2dbd24d821fc38ca5bd5f4d0daa5140c79dc8ab246e3eaa` |
| `authority_leak_hostile.json` | invalid | 2603 | `61f7ebbd0964657f8b3556e63a302619dcbe4cfb4dccfc620ca25896e151b765` |

`tests/test_evidence_foundation_contract.py` uses only the combined validator for
consumer verdicts. It proves exact source-backed schema/identity/clock/accessor
inventories, native Earnings parser identity, one-pointer selection, exact fixture
bytes/hashes, native-schema and per-clock deletion kills, 13F/GovRev/Bio
cutoff-inversion kills, FIF unknown-clock and unavailable-vintage replay kills, TXI
collision resistance, declarative-only independence, v1 automatic-effect refusal,
correction target equality, all-class invalid cutoffs, symmetric cross-grain ambiguity,
typed missingness, body refusal, and zero authority. Its no-store proof enumerates the
actual changed-file inventory and calls the sparse-worktree API only to observe omitted
trees; it never infers absence from `Path.exists()`.

## 5. Validation commands

```bash
python3 -m json.tool contracts/evidence_foundation/reference.v1.schema.json
python3 -m json.tool contracts/evidence_foundation/vocabulary.v1.json
python3 -m compileall -q lib/evidence_foundation.py tests/test_evidence_foundation_contract.py
python3 -m pytest -q tests/test_evidence_foundation_contract.py
python3 scripts/agentos.py validate
python3 scripts/check_contract_delta.py --base origin/main
python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 5 --pack-count 12 --validate-only
```

The repaired targeted fixture/contract suite concluded **41 passed**. The only warnings were
three unrelated pytest temporary-directory cleanup warnings outside this worktree.
After restoring the full checkout required by the committed Bio fixtures, the
owner-source regression selection (Data OS no-I/O negative control, Theme Graph,
FIF, Earnings workspace, 13F, government events, Bio current/history, TXI, QLedger,
and Market Memory) additionally concluded **569 passed, 1 skipped**. Its remaining
warnings were three unrelated temporary-directory cleanup warnings plus one upstream
Starlette deprecation warning. The preceding sparse run's Bio fixture misses are not
counted as contract failures: all 72 were `FileNotFoundError` for intentionally omitted
`data/` fixtures, and the identical selection passed after full materialization.

### Required CI-authority scope addition

The initial contract surface did not name `.github/ci/legacy-jobs.yml`. Repository
contract-delta validation then correctly failed because the new pytest suite had no
hosted `run:` owner. K1 therefore added one step to the existing `signal-contract`
/ Fundamental Forensics lane. It created no new workflow or job. This is an explicit,
required delivery-scope addition, not evidence-plane expansion.

After wiring, contract-delta reports `0 introduced, 0 inherited`. The current
12-pack plan places `signal-contract` in pack 5; pack validation reports 202 valid
legacy jobs and 18 jobs in pack 5. Because `.github/ci/**` is CI authority,
semantic evidence will carry `authority_changed=true`: merge requires concluded
exact-head checks, and final delivery additionally requires a successful `ci.yml`
run on a main descendant of the merge under the merged authority.

## 6. Exact K1 acceptance request to Sol

> Sol, accept K1 / FABLE-A Evidence Foundation v1.0.0 as a contract-only freeze.
> The current protected Skillpack was loaded from Mastermind
> `db0bac5fe3f72348262d42c8bd26b836bda9f61d`; Macro was reconciled to
> `7cc324f2e1c6425ac9710863b3aa4ca8ac20b7c4`. The physical-store flip condition is
> adverse: no named current PR or workstream commits to a one-query native-object
> read across at least three owner stores for one subject. K1 therefore preserves
> owner-bound accessors, copies no bodies, creates no store/index/control plane, and
> freezes only the pointer schema, 13-owner vocabulary, combined fail-closed validator, and
> eight exact-hash fixtures. All authority axes, including ENTRY_OPEN, are false.
> Please rule ACCEPT or return exact K1 amendments. This packet does not authorize or
> begin K2, K3, K4, B1, K2-B, or D5-EARNINGS.
