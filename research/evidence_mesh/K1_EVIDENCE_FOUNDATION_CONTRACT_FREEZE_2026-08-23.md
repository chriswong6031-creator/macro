# K1 Evidence Foundation contract freeze — 2026-08-23

Status: **CONTRACT FROZEN; PHYSICAL STORE REFUSED; SOL ACCEPTANCE REQUESTED**

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
K1 was reconciled and built from fresh Macro `origin/main`
`21fab35211433ab9bc4dafda3757d5aa30e11a3e`. The only K1-owner-area change between
the historical pin and that base is an additive issuer-profile change in
`engine/company_intelligence/issuer_profiles.py`; it does not alter the frozen
Evidence Foundation identities, clocks, or readers.

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
| FIF-3A2 #6302 | open draft `HOLD-FOR-SOL` | head `9598c5430c587b2ec9d1f84d3fa6e2d704808bcc` | later FIF production acceptance remains held; K1 did not modify, merge, or route around it |

K1 therefore uses current owner contracts and fixtures. It does not describe a
merge as production proof and does not consume or alter the held FIF-3A2 carrier.

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
- `contracts/evidence_foundation/vocabulary.v1.json` — 17 owner identity/clock/reader bindings
- `contracts/evidence_foundation/README.md` — interoperability law
- `lib/evidence_foundation.py` — deterministic identity and semantic validator

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
| `observed` | when the owner actually retrieved/first saw it |
| `system_recorded` | when the owner durably retained/registered it |
| `belief_or_build` | the owner's belief, vintage, or build clock |
| `review_due` | a future review/maturity deadline, never observation time |

Each vocabulary row carries `synapse_asof_field`. It is the existing Synapse field
when that exact owner-native object is registered (`computed_at` for Theme Graph,
`asof` for QLedger), and literal `null` otherwise. `null` prevents guessed catalog
clocks.

### Owner adoption inventory

| Owner object | Native identity | Key clock bindings | Direct reader |
|---|---|---|---|
| Data OS security master | `security_id` | `effective_at`, `ingested_at` | `lib.dataos.identity.IssuerMaster` |
| Theme Graph evidence | `evidence_id` | `published_at`, `effective_at`, `computed_at` | `engine.theme_graph.store.read_evidence` |
| Theme Graph edge belief | `edge_id + belief_time` | `valid_*`, `evidence_time`, `belief_time`, `computed_at` | `engine.theme_graph.store.read_edges` |
| FIF raw occurrence | `occurrence_id` | `clocks.accepted_at`, `clocks.recorded_at` | `BitemporalMetricQueryEngine.query_matrix` |
| FIF packet | `packet_id` | source/system cutoffs, governance, build | `build_financial_intelligence_packet_from_repo` |
| Earnings event | `event_id` | lifecycle effective/available/observed | `CompanyEvent` |
| Earnings workspace generation | `generation_id + event_id` | lifecycle available/observed, generated | `read_event_workspace` |
| Institutional 13F receipt | `receipt_id` | report/accepted/retained | `RawEvidenceReceipt` |
| Institutional 13F catalog generation | `generation_id` | report/source-cutoff/published | `load_catalog_generation` |
| GovRev event v2 | `event_id` | `change.effective_at`, `change.known_at`, `change.first_seen_at` | `_validated_award_events` |
| Bio current source snapshot | `source_snapshot_id` | effective/published/retrieved/first-seen | `read_validated_generation` |
| Bio history source snapshot | `source_snapshot_id` | submitted/retrieved/transaction | `read_validated_generation` |
| Bio change fact | `change_fact_id` | `transaction_from` | `read_validated_generation` |
| Bio outcome | `outcome_id` | effective/known/observed | `read_validated_generation` |
| TXI episode | `episode_id` | `asof` | `_read_ledger` |
| QLedger claim | `claim_id` | asof/vector-asof/registration/review-due | `load_claims` |
| Market Memory outcome | `outcome_record_id` | effective/available/known/observed/recorded | `load_record` |

The institutional census dedup precedent, Fundamental Forensics
`KnowledgeClock`/`VintagePolicy`, QLedger evidence-clock separation, and merged PIT
replay harness were explicitly included in the archaeology. Derived heads such as
the QLedger evidence-clock start and current Theme/TXI/workspace heads are excluded
from owner objects.

### Relations, corrections, missingness, replay

- Every relation carries separate source-independence, information-novelty, and
  economic/mechanism-independence axes.
- Only `exact_duplicate`, `same_fact`, and `same_event` may have an automatic
  effect, and only with a deterministic key.
- `corroborates`, `contradicts`, `shares_upstream`, `corrects`, `supersedes`, and
  `projects` never auto-net, rank, promote, or suppress.
- Corrections append and name predecessor references. Predecessors never mutate.
- Missingness is typed and can never be substituted with zero.
- Historical replay binds a cutoff for every clock class and refuses any native
  clock beyond its class cutoff. Current-rule recomputation is a separate mode.

## 4. Golden fixture packet

The manifest freezes eight byte-receipted fixtures:

| Fixture | Verdict | Bytes | SHA-256 |
|---|---:|---:|---|
| `fif_packet_valid.json` | valid | 2639 | `edda10ade34664c0506483798a314b0cbc534563178c24800bfc76acd3e172a4` |
| `earnings_workspace_valid.json` | valid | 2481 | `3f1beff0cd9fe03a6b2a3a66750c40fcbac7a1c00ce87078132ea1adeba81bf3` |
| `duplicate_corroboration_hostile.json` | invalid | 2897 | `abd9eaf4119b42217529becba4484ea78913b6ae6e638c677bb9ebfea876652c` |
| `correction_append_valid.json` | valid | 3183 | `24db3f2617f7ffafce17266339dd54897382a630d5f56e4ad4848b7e6637d004` |
| `replay_valid.json` | valid | 2515 | `f83a02112dcc0171a57717dbc0899202315c028cef9214b6516a3ff1ba8b52ae` |
| `replay_lookahead_hostile.json` | invalid | 2431 | `e911a93cbc1c7a476d9e217f52a718245e582ee4b3d08255fa4fd0ffa5571a16` |
| `typed_missingness_valid.json` | valid | 1899 | `40070b3895bf06d9394760a95908655f7f854c2c3faefce82c595ac932564d10` |
| `authority_leak_hostile.json` | invalid | 1947 | `1f62ce979d2743734e53cbd1492551a0bfb8b9b0f3b9378cc1bf9f9f90d41e50` |

`tests/test_evidence_foundation_contract.py` validates schema, semantic verdict,
deterministic ids, exact fixture bytes/hashes, owner identities and clocks, every
owner reader symbol on current base, Synapse `asof_field` fail-closed behavior,
pointer-only provenance, append/supersede corrections, replay/lookahead refusal,
typed missingness, and zero authority. Its no-store proof enumerates tracked and
untracked Git paths, so it remains valid in a sparse worktree and does not infer
absence from omitted `data/` or `site/` directories.

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

The targeted fixture/contract suite concluded **15 passed**. The only warnings were
three unrelated pytest temporary-directory cleanup warnings outside this worktree.

### Required CI-authority scope addition

The initial contract surface did not name `.github/ci/legacy-jobs.yml`. Repository
contract-delta validation then correctly failed because the new pytest suite had no
hosted `run:` owner. K1 therefore added one step to the existing `signal-contract`
/ Fundamental Forensics lane. It created no new workflow or job. This is an explicit,
required delivery-scope addition, not evidence-plane expansion.

After wiring, contract-delta reports `0 introduced, 0 inherited`. The current
12-pack plan places `signal-contract` in pack 5; pack validation reports 201 valid
legacy jobs and 18 jobs in pack 5. Because `.github/ci/**` is CI authority,
semantic evidence will carry `authority_changed=true`: merge requires concluded
exact-head checks, and final delivery additionally requires a successful `ci.yml`
run on a main descendant of the merge under the merged authority.

## 6. Exact K1 acceptance request to Sol

> Sol, accept K1 / FABLE-A Evidence Foundation v1.0.0 as a contract-only freeze.
> The current protected Skillpack was loaded from Mastermind
> `db0bac5fe3f72348262d42c8bd26b836bda9f61d`; Macro was reconciled to
> `21fab35211433ab9bc4dafda3757d5aa30e11a3e`. The physical-store flip condition is
> adverse: no named current PR or workstream commits to a one-query native-object
> read across at least three owner stores for one subject. K1 therefore preserves
> direct owner readers, copies no bodies, creates no store/index/control plane, and
> freezes only the pointer schema, 17-owner vocabulary, semantic validator, and
> eight exact-hash fixtures. All authority axes, including ENTRY_OPEN, are false.
> Please rule ACCEPT or return exact K1 amendments. This packet does not authorize or
> begin K2, K3, K4, B1, K2-B, or D5-EARNINGS.
