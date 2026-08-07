# Calcbench Parity — Claude Continuation Handoff

## Canonical remaining-work plan for Fundamental Forensics

| Field | Value |
|---|---|
| Status | Canonical resume handoff for all remaining Calcbench-parity work |
| Audited | 2026-08-06 |
| Forensics code audit revision | `981d8851e0b43c89532be54e3488a2bd8e57dccc` |
| Handoff delivery base | Fresh `origin/main` at `a1174cec091b02ba8d8aefb7b9358c988d51dc0a`; no audited Forensics path changed between these revisions |
| Product | MastermindX Fundamental Forensics |
| Immediate next lane | Wave 0A — connect the production receipt API to the dedicated attested-history store |
| Scope authority | `research/CALCBENCH_FULL_PARITY_PROGRAM_AND_WAVE_2_BUILD_DOCKET_2026-08-01.md` |
| Deep product/engine assessment | `research/CALCBENCH_FUNDAMENTAL_FORENSICS_ENGINE_ASSESSMENT_AND_BUILD_DOCKET_FOR_FABLE.md` |
| Immediate pilot authority | `research/CALCBENCH_PARITY_WAVE_3B_B4F_FIRST_SEALED_ISSUER_PILOT_2026-08-03.md` |
| This file's role | Supersedes older continuation notes for resume order and current-state truth; it does not replace the detailed contracts in the underlying dockets |
| Authority boundary | Context and review priority only; no ranking, sizing, gating, or trade-originating authority |

---

## 0. Claude: start here

Read `CLAUDE.md`, `AGENTS.md`, this file, the full-parity program, and the B4F
pilot docket before changing code. Query the active build map and
`research/DO_NOT_REBUILD.md`. Work from a freshly fetched `origin/main` in a new
`.claude/worktrees/<task>` worktree on a `claude/<task>` branch. Do not resume an
old Calcbench worktree and do not develop in the shared checkout.

`AGENTS.md` also requires the Claude project memory pass. Search
`~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/memory/MEMORY.md`
and open the delivery entries named `session-finish-full-git-chain`,
`auto-finish-commit-push-pr`, and `go-live-deploy-mechanics`. If the first two
legacy names are absent from the current index, open their current ship-loop
equivalent `auto-commit-pr-merge.md` plus `go-live-deploy-mechanics.md`, and note
the stale alias rather than skipping the memory requirement.

Cold-start discovery commands:

```bash
python3 scripts/context_index_query.py search \
  "Calcbench Fundamental Forensics attested history" --mode adjudication
sed -n '1,180p' docs/ACTIVE_BUILD_MAP.md
grep -n -i 'calcbench\|fundamental forensics\|attested history' \
  docs/ACTIVE_BUILD_MAP.md research/DO_NOT_REBUILD.md
```

Open any cited source before acting; the Context Index is advisory. Also check
current open PRs before claiming a file lane.

Treat this as a sequence of independently reviewable ship units. Do **Wave 0A
first**. Do not jump to another UI, broad issuer ingestion, Excel, a scheduler,
or Prophet scoring while the dedicated serving path is disconnected.

The decisive current fact is:

> The seed/operator write and read the new dedicated attested-history bucket,
> but the production HTTP API still constructs the generic Research Vault store.
> A successful AAPL seed would therefore remain invisible to the current API.

That integration gap was discovered in the 2026-08-06 source audit and is the
first code task.

---

## 1. Executive verdict

The project has a serious, tested filing-forensics foundation. It is not a
mockup, but it is also not close enough to call a complete Calcbench replacement.

What exists today is best described as three different generations that have
not yet been joined into one production query plane:

1. a live premium filing-review workbench using a broad 1,507-ticker projection,
   nine normalized metrics, five deterministic detectors, and bounded
   accession-aware disclosures for a smaller issuer set;
2. a newer bitemporal kernel with a governed 50-metric registry, immutable raw
   occurrences, period algebra, lineage, and query receipts; and
3. a hardened sealed-receipt stack with filing packages, iXBRL extraction,
   Company Facts attestation, immutable `ffqs_` / `ffqsv2_` contracts, CAS,
   authenticated receipt APIs, and a receipt control-room UI—but no live sealed
   issuer publication.

The hard remaining work is not storing “500 million data points.” SEC source
data and object storage are affordable. The moat-bearing work is semantic:
filing completeness, context/dimension preservation, point-in-time laws,
versioned mappings, exception review, corrections, specialist ontologies,
reversible trace, and longitudinal QA.

The correct strategy remains **full clean-room functional parity**, followed by
a better interpretation layer. Do not copy Calcbench code, protected output,
proprietary mappings, branding, or interface geometry. Public SEC evidence and
licensed sources are inputs; competitor workflows are product research only.

### Canonical wave status

| Wave | Status at 2026-08-06 | Owner | Hard prerequisite | Latest evidence | Next action / exit evidence |
|---|---|---|---|---|---|
| 0A dedicated reader | Not started | Claude | Fresh `origin/main`; lane/collision audit | API/store mismatch found in source audit | Merge and deploy dedicated fail-closed reader; then bind read-only VPS secrets |
| 0B B4F activation | Externally blocked | Claude + operator | 0A reader code; six dedicated secrets; protected approval | #4431/#4445 code; zero workflow runs; no packet | Approved seed, four reviewed artifacts, packet PR, zero-write replay |
| 0C paid preview | Not started; parallel | Claude | 0A underway; design doctrine/skill | Live 401/403 funnel audit | Anonymous/free/paid browser and visual gates |
| 1 first v2 publication | Blocked by 0B | Claude + operator | Reviewed canonical packet | B4D/B4E machinery #4381/#4398 | One manual AAPL `ffqsv2_`; API/UI live acceptance |
| 2 corpus + gold QA | Planned | Claude | Wave 1 proof and stable receipt contracts | 12-name Wave 2 slice; local AAPL evidence | Partitioned cohort then 200-issuer blinded gates |
| 3 production query plane | Planned | Claude | Wave 2 evidence/catalog contracts | 50-metric bitemporal kernel #4261/#4267 | Authenticated PIT/as-reported/normalized query acceptance |
| 4 analyst cockpit | Planned | Claude | Stable Wave 3 query contract | Existing workbench #4184/#4210/#4410 | Company, filings, multi-company, disclosure, revision workflows |
| 5 specialist intelligence | Planned | Claude + domain review | Wave 2 gold process; Wave 3 semantics | Five quantitative and five qualitative review detectors | Registered verticals and calibrated detector families |
| 6 API/export/Excel | Planned | Claude | Wave 3 query and tenant contracts | No analyst delivery plane | Cross-surface receipt/value round trips |
| 7 Neural Web/Prophet | Partial context only | Claude + authority review | Receipt-bearing PIT packets; outcome ledger | Current v1 context seam | Leakage-safe context accrual; separately governed promotion |
| 8 parity closure | Not earned | Program owner | Waves 0-7 acceptance | Canonical parity ledger | Independent clean-room, security, temporal, UX, and operations audit |

Update this table after each merged/live-verified wave. “Code complete,”
“externally blocked,” and “live verified” are different states.

---

## 2. Verified current snapshot

### Repository and production

- Forensics code audit baseline: `981d8851e0b43c89532be54e3488a2bd8e57dccc`.
- This handoff was rebased onto fresh `origin/main`
  `a1174cec091b02ba8d8aefb7b9358c988d51dc0a`; a path-limited Git diff confirmed
  that none of the audited Forensics code/config/workflow paths changed between
  the two revisions.
- Production `/api/health` reported `checkout=a1174cec091` and
  `commit=1bef90743ae`. The checkout matched the delivery base and retained the
  audited Forensics paths; the running API process identified an older ancestor.
- `https://mastermind-x.com/fundamental_forensics.html` returned HTTP 200 and
  included the Filing Change Radar and sealed-receipt controls.
- Unauthenticated attested-history requests returned 401 with `private,
  no-store`, `Vary: Authorization`, `nosniff`, and `noindex` boundaries.
- The broad focused baseline passed:

  ```bash
  python3 -m pytest tests/test_fundamental_forensics_*.py tests/test_forensics_api.py -q
  # 666 passed
  ```

- Independent focused audits also passed the operator/seed, receipt-reader/API,
  browser receipt-contract, and Neural Web/Brain suites. These tests prove code
  contracts; fixture-backed tests do not prove live issuer coverage.

### Operations

- The protected GitHub environment `attested-history-seed` exists with one
  required reviewer and a `main`-only deployment policy. Recheck this before use.
- At audit time, GitHub exposed **none** of the six required dedicated secret
  names at repository/environment scope.
- Both manual attested-history workflows had zero historical runs.
- `config/fundamental_forensics/attested_history_operator.v1.json` did not exist.
- The operator has created the dedicated normal-access object-storage bucket.
  Bucket creation alone does not bind GitHub Actions or the VPS reader to it.

Do not record secret values in this file, a PR, an Actions artifact, or chat.
Only verify names and scopes. Any competitor password previously pasted into a
chat should be rotated and must never be committed or used as an ingestion
dependency.

---

## 3. Current architecture: what is real and what it proves

| Plane | Current implementation | Honest boundary |
|---|---|---|
| Premium workbench | Seven-tab filing-review cockpit, issuer search, review queue, history, disclosures, redlines, filing trail, one-issuer period compare, evidence drawer, receipt reader | Real product, but not a general analyst terminal |
| Broad normalized state | 1,507-ticker EDGAR projection; nine metrics; five detectors; private gzip state | Useful newest-state review layer; explicitly not accession-coherent or historical PIT |
| Wave 2 source/disclosure | Immutable SEC document spine, normalized sections/spans, structural diffs, five qualitative review detectors, private R2 flow | Production-capable bounded slice; daily issuer list is 12 and CLI hard cap is 32 |
| Bitemporal kernel | Raw occurrence ledger, distinct source/system clocks, 50 governed metrics, periods, formulas, selection policy, query receipts | Strong engine foundation; not the production workbench query plane |
| Filing evidence | Filing package, safe iXBRL parsing, exact Company Facts occurrence correspondence, source attestations | Real code and local AAPL evidence; not a live sealed issuer |
| Immutable snapshots | `ffqs_` base receipts and `ffqsv2_` attested overlays, strict readers, bounded admission, pointer-last CAS | Contracts exist; no production v2 pointer is published |
| Receipt delivery | Paid, authenticated, bounded latest/root/detail API plus source waterfall UI | Reader only; it cannot acquire, verify, materialize, or publish |
| Neural Web / Brain | Compact filing findings from private v1 state for entitled users | Current-snapshot, display-only, context-only; not true historical replay |
| Prophet | No live governed integration | No accounting score, rank adjustment, gate, or trade authority |
| Bulk/API/Excel | No analyst query/export plane | Receipt lookup and private-state transport are not a Calcbench-like API |

### The five live quantitative detectors

The live broad workbench currently evaluates only:

1. margin compression despite revenue growth;
2. receivables stretch;
3. inventory build;
4. rising capital intensity; and
5. accruals trending up.

Do not describe this five-detector layer as the complete Fundamental Forensics
Engine. The 50-metric bitemporal registry is a different, newer kernel and is
not yet wired into the production workbench.

---

## 4. Critical integration defects and product gaps

### P0: the dedicated bucket is not connected to the production API

The seed and read-only operator require the dedicated runtime variables:

- `FF_ATTESTED_R2_READONLY_ENDPOINT`
- `FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID`
- `FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY`
- `FF_ATTESTED_R2_READONLY_BUCKET`

They reject a Research Vault fallback and mint short-lived, prefix-scoped
children for controlled jobs. See:

- `scripts/seed_fundamental_forensics_attested_history.py`
- `scripts/run_fundamental_forensics_attested_history.py`
- `.github/workflows/attested-history-aapl-seed.yml`
- `.github/workflows/attested-history-operator.yml`

The live HTTP route in `app/forensics.py::_build_store`, however, calls
`engine.research_vault.r2_store.build_store()`. That factory reads
`R2_RESEARCH_BUCKET` and Research Vault/generic credentials. It never selects
the dedicated attested-history bucket.

Consequences:

- never repoint `R2_RESEARCH_*` to the new bucket;
- do not assume seeding will make the UI populate;
- do not reuse the one-shot operator constructor blindly in the long-running
  API, because its temporary child credential expires;
- implement a dedicated, renewable, read-only server-store adapter and an
  explicit VPS secret-delivery path.

The intended name/scope mapping is explicit:

| GitHub secret | GitHub scope | Workflow/runtime name | Consumer |
|---|---|---|---|
| `R2_ATTESTED_HISTORY_ENDPOINT` | Repository | `FF_ATTESTED_R2_READONLY_ENDPOINT` | Seed, read-only operator, and VPS API reader |
| `R2_ATTESTED_HISTORY_BUCKET` | Repository | `FF_ATTESTED_R2_READONLY_BUCKET` | Seed, read-only operator, and VPS API reader |
| `R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID` | Repository | `FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID` | Seed, read-only operator, and VPS API reader |
| `R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY` | Repository | `FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY` | Seed, read-only operator, and VPS API reader |
| `R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID` | Protected `attested-history-seed` environment | `FF_ATTESTED_R2_SEED_ACCESS_KEY_ID` | Manual seed only |
| `R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY` | Protected `attested-history-seed` environment | `FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY` | Manual seed only |

Wave 0A must add the four repository read-only mappings to
`.github/workflows/deploy-api-secrets.yml`, which writes their `FF_*` runtime
names to `/etc/macro-api.env` and restarts `macro-api`. The two environment
writer secrets never enter that workflow or the VPS.

### P0: B4F produces v1 evidence, not a served v2 receipt

The one-shot AAPL seed writes bounded SEC source objects and one immutable v1
base receipt. It intentionally uses `publish_latest=False` and does not publish
an attested `ffqsv2_` overlay or advance its latest pointer. The current
read-only operator also performs zero writes.

Therefore the sequence is:

`dedicated reader seam -> B4F v1 seed/review -> canonical packet -> read-only replay -> B4G v2 publisher -> API/UI acceptance`

Anything shorter is a false completion claim.

### Product funnel defect

The workbench HTML can be reached anonymously, while its CSS/JS are currently
behind the registration wall. A signed-in free user receives a generic
“Data unavailable / Retry” response on the premium API's 403 instead of an
upgrade state. This is not a security leak, but it is a poor paid-product
journey and conflicts with the repository's preview pattern.

Fix this as a small parallel UI lane after Wave 0A begins. Do not expose private
rows in shell bytes or create a fake sample payload.

### Scale constraints to respect

- Current Wave 2 acquisition is a 12-name scheduled slice, capped at 32 issuers
  and 256 MiB per run.
- Synchronous kernel queries are intentionally bounded to 50 tickers x 50
  metrics x 32 periods and 10,000 cells.
- Current v1 snapshot admission can be monolithic and large. Broad history
  needs issuer/period partitioning plus a catalog; do not scale one giant
  snapshot.
- Receipt serving is deliberately compact and bounded. Keep heavy SEC parsing,
  replay, and materialization off request paths and off page rendering.

---

## 5. Already covered — do not rebuild

Extend these foundations; do not create parallel equivalents:

- the live Filing Change Radar shell and its private-state route;
- nine-metric/five-detector broad normalized projection;
- Wave 2 SEC accession/document spine and checksum-bound private source store;
- filing HTML normalization, source spans, section taxonomy, redlines, and
  qualitative detectors;
- raw occurrence ledger, bitemporal clocks, metric registry, period algebra,
  formula DAG, and query receipts;
- immutable `ffqs_` query snapshots;
- bounded filing package and safe iXBRL extraction;
- B3 exact Company Facts occurrence attestation;
- `ffqsv2_` overlay schema, materializer foundation, strict reader, and pointer
  CAS primitives;
- paid latest/root/root-detail receipt API and receipt control-room UI;
- zero-write read-only operator and manual AAPL seed workflow;
- current context-only Neural Web and Brain seam;
- private R2/no-store/`site_full` security boundary.

Repository fence: do not create a parallel filing knowledge base. Preserve the
existing source, ledger, receipt, and authority contracts
(`DNR:KILL-PARALLEL-KNOWLEDGE-BASE`).

### Merged implementation anchors

| Capability | Merge |
|---|---|
| Product assessment | `b6898e236bb` / PR #4172 |
| Filing Forensics workbench | `c4e1e0d411f` / PR #4184 |
| Wave 2 SEC disclosure source spine | `8f6403c4e1a` / PR #4210 |
| Wave 3A receipt kernel | `fb47a29f1c4` / PR #4261 |
| Immutable query snapshots | `f1563e45239` / PR #4267 |
| Filing package and iXBRL/B3 evidence | `516830284ae`, `f82ed8b127a`, `2b69de87469` / PRs #4276, #4286, #4288 |
| Attestation clock and v2 overlay | `5a508ebda09`, `3b044734885` / PRs #4289, #4290 |
| Bounded authenticated receipt API | `53f5776e1a6` / PR #4360 |
| Materializer foundation and pointer CAS | `a2f97de7339`, `02b3a5ffefc` / PRs #4381, #4398 |
| Receipt control room and zero-write operator | `80ed393d222`, `e803374f97e` / PRs #4410, #4411 |
| Manual AAPL seed and R2 isolation | `59478c96de6`, `1122c2f9382` / PRs #4431, #4445 |

All were ancestors of the audit baseline. These merges prove implementation
history; they do not prove that B4F was activated against live R2.

---

## 6. Remaining build waves

Each wave below is a capability gate, not a calendar estimate. Ship small PRs,
keep the canonical status table in this file current, and do not call the
program “full parity” until the final acceptance suite passes.

### Wave 0 — close the activation seam

#### Wave 0A: dedicated production receipt reader

**Build**

1. Add a dedicated attested-history store factory for the API. It must use only
   `FF_ATTESTED_R2_READONLY_*`, never Research Vault or generic R2 fallbacks.
2. Design the long-running credential lifecycle. Either use a truly
   bucket/prefix-scoped direct Get/Head credential or renew short-lived children
   before expiry under a lock. Do not cache a 30-minute child forever.
3. Bind `app/forensics.py::_build_store` to this factory and keep its bounded
   immutable-reader cache and fail-closed 503 behavior.
4. Extend `.github/workflows/deploy-api-secrets.yml` to deliver **only** the
   dedicated read-only values to `/etc/macro-api.env`; never deliver writer
   credentials to the VPS.
5. Add tests for missing values, wrong bucket, denied Put/Delete/List, expiry or
   refresh, concurrent initialization, no fallback, cache reset, 401/403 before
   storage access, bounded reads, and safe 503s.

The deploy-workflow edit is not complete unless all of these are mechanically
pinned:

- the macro-api job imports all four repository secrets into dedicated
  temporary workflow variables;
- `_add` emits all four `FF_ATTESTED_R2_READONLY_*` runtime names;
- the remote rewrite removes every existing
  `FF_ATTESTED_R2_READONLY_(ENDPOINT|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)`
  line before appending, so rotation or removal cannot leave a stale credential;
- `R2_ATTESTED_HISTORY_SEED_*` / `FF_ATTESTED_R2_SEED_*` occur zero times in
  the VPS delivery path;
- the macro-admin job receives none of the attested-history variables; and
- before dispatch, name-only checks confirm `VPS_DEPLOY_KEY` and at least one
  `CLAUDE_CODE_OAUTH_TOKEN_N` are available, because the current shared deploy
  workflow exits before R2 delivery without them. If that coupling is removed,
  do it as an explicit reviewed refactor with equivalent fail-closed tests.

**Exit gate**

Wave 0A has two separately recorded closure states:

**Code/live binary complete**

- A local/fake dedicated store is the only store reachable from the receipt API.
- Tests prove no `R2_RESEARCH_*` or generic fallback.
- VPS secret deployment is explicit and writer-free.
- Existing receipt API/privacy suites and the full forensics baseline pass.
- The PR is merged and production advances to the merge. With secrets absent,
  the entitled receipt route must fail closed; that is a valid shipped code
  state, not activation.
- For this API-code lane, follow the apex redirect with `curl -fsSL` and require
  `/api/health`'s **`commit`** field—not merely `checkout`—to equal the Wave 0A
  merge or a descendant. `checkout` proves the VPS pulled Git; `commit` proves
  the running API process restarted onto the code.

**Credential binding complete**

- All four repository read-only names are provisioned securely.
- The reviewed deploy workflow writes the corresponding `FF_*` names to
  `/etc/macro-api.env`, restarts `macro-api`, and the process reports healthy.
- No writer secret is present in the VPS environment.
- Only after both states may Wave 0B treat the production reader as connected.

#### Wave 0B: provision and execute the controlled B4F pilot

At the 2026-08-06 audit, these names were absent.

Repository-scoped GitHub secrets:

- `R2_ATTESTED_HISTORY_ENDPOINT`
- `R2_ATTESTED_HISTORY_BUCKET`
- `R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID`
- `R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY`

Protected `attested-history-seed` environment secrets:

- `R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID`
- `R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY`

**Run order**

1. Recheck secret-name presence and environment protection without reading or
   printing values.
2. Deploy the read-only server binding to the VPS through the reviewed secret
   delivery workflow.
3. Dispatch on `main` only:

   ```bash
   gh workflow run attested-history-aapl-seed.yml \
     --ref main -f enable_aapl_seed=true
   ```

4. Approve the protected environment and wait for the exact run/attempt to
   finish.
5. Download and independently review all four non-confidential artifacts:
   `attested_history_operator_packet.json`,
   `attested_history_preflight_receipt.json`,
   `attested_history_seed_receipt.json`, and
   `attested_history_seed_bundle_receipt.json`.
6. Recompute byte lengths and SHA-256 values. Verify repository, commit, ref,
   workflow, run/attempt, dependency lock, environment, storage-control probe,
   issuer/accession, object IDs, and explicit nonclaims.
7. Create a separate packet-activation PR containing the reviewed
   `config/fundamental_forensics/attested_history_operator.v1.json` **and the
   necessary operator contract-test transition only**. The current inert test
   `test_contracts_and_workflow_are_inert_and_no_production_packet_exists`
   explicitly asserts that this file is absent; replace that assertion with
   byte-exact canonical-packet admission, Git provenance, workflow binding, and
   tamper rejection. Never reconstruct or hand-edit the packet, and do not mix
   unrelated feature changes into this PR.
8. After that packet is merged, dispatch:

   ```bash
   gh workflow run attested-history-operator.yml \
     --ref main -f enable_readonly_preflight=true
   ```

9. Accept only a replay receipt with zero storage writes and zero write
   attempts.

**Exit gate**

- Protected seed run on `main` succeeded and was approved.
- Four artifacts agree by exact IDs, lengths, and hashes.
- Canonical packet is separately reviewed, committed, merged, and live.
- Read-only replay succeeds against the same dedicated bucket.
- No v2/public receipt, scheduler, broad coverage, or parity claim is made yet.

#### Wave 0C: paid preview and entitlement UX

This can run as a separate UI PR once Wave 0A is underway.

- Read `docs/DESIGN_DOCTRINE.md` and invoke the repository-mandated
  `frontend-design:frontend-design` skill before changing the user-facing
  surface. If that skill is unavailable, stop the UI lane and record the exact
  tooling blocker rather than improvising a flagship design.
- Serve anonymous-safe CSS/JS and a useful product anatomy/coverage preview.
- Distinguish anonymous 401, free-tier 403, temporary 503, and genuine empty
  coverage states.
- Provide precise sign-in/upgrade actions; never show paid rows or private
  receipt content in public bytes.
- Preserve EN/ZH, light/dark, keyboard use, and 390px/1440px layouts.

Exit only with browser journey tests and production-shaped visual captures.

### Wave 1 — publish the first real sealed AAPL receipt (B4G)

Design a separately reviewed single-writer publisher. Do not turn either
existing manual workflow into a scheduler.

**Build**

- consume the exact committed operator packet and pinned source authority;
- reconstruct the governed query candidate and B3 occurrence bindings;
- materialize the complete `ffqsv2_` overlay and coverage/non-evaluable states;
- publish immutable objects first and advance the v2 latest pointer last;
- enforce B4E exact-predecessor CAS, an exclusive writer/lease fence, replay
  idempotency, crash recovery, and stale-writer rejection;
- emit a bounded publication receipt and rollback/recovery instructions;
- keep AAPL-only and manual until independent review passes.

**Exit gate**

- one real AAPL `ffqsv2_` publication exists in the dedicated bucket;
- a separate read-only process validates it from exact bytes;
- an entitled production request returns it from latest/root/detail APIs;
- the receipt UI shows AAPL and prints partial/evidence-only coverage honestly;
- no SEC fetch, replay, verification, or write occurs on HTTP request paths;
- pointer races, ABA/stale writer, crash-before-pointer, tamper, and missing
  object tests pass.

### Wave 2 — issuer-partitioned corpus, gold QA, and durable operations

Do not jump from one AAPL receipt to one global 10,000-issuer object.

**Build**

- issuer/accession-partitioned immutable source and receipt namespaces;
- a compact coverage/freshness catalog with latest-good pointers and receipts;
- worker queues, bounded SEC acquisition, polite pacing, retries, dead letters,
  correction/reprocessing rules, observability, and recovery runbooks;
- staged expansion: AAPL -> frozen 12-name cohort -> 200-issuer gold corpus ->
  broader eligible universe;
- complete accession manifests, filing packages, contexts, units, dimensions,
  presentation/calculation relationships, source spans, and checksums;
- a blinded exception-review workflow with versioned decisions.

**Exit gate**

- frozen 200-issuer/form sample matches SEC manifests;
- supported section extraction reaches at least 98% precision;
- A-C mappings reach at least 99% agreement on the blinded gold corpus;
- amendments, restatements, corrections, 53-week years, stubs, duplicate iXBRL,
  extensions, dimensions, units, signs, and scales have explicit gold cases;
- freshness/SLO alerts distinguish stale, absent, failed, and not-covered;
- one issuer failure cannot poison or block the whole publication set.

### Wave 3 — make the 50-metric kernel the production bitemporal query plane

The present workbench and the newer receipt kernel must converge here. Extend
the existing query engine; do not create a third semantic model.

**Build**

- authenticated query jobs over company, metric, period, as-of, vintage, filing,
  and rule-version selectors;
- true original/latest/as-of/revision views with acceptance-time enforcement;
- accession-coherent “Reported” statements beside versioned “Normalized” rows;
- Q4, TTM, calendar/fiscal alignment, ratios, split/FX policy, and typed formula
  lineage;
- entity/security master, historical universe/peer membership, and
  point-in-time cohort receipts;
- issuer/period partitions, stable pagination, quotas, saved queries, and
  asynchronous execution off the render/request path;
- expand from 50 to 150-300 high-confidence core metrics before long-tail
  catalog chasing.

**Exit gate**

- every value reverses to formula -> selected raw occurrences -> exact filing
  evidence and governing policy versions;
- incompatible unit, dimension, fiscal, or period rows are withheld or visibly
  “not comparable,” never coerced silently;
- preliminary, amendment, recast, correction, rule-revision, stub, and 53-week
  tests show zero future leakage;
- frozen direct calculations match API results and UI values exactly;
- private, tenant, quota, no-store, and resource-ceiling tests pass.

### Wave 4 — flagship analyst cockpit and multi-company workflows

Preserve the current Filing Change Radar, redlines, evidence drawer, filing
trail, and receipt control room. Evolve them into a faster operator cockpit.

**Surfaces**

1. Company Dashboard — recency, coverage, data quality, material changes, saved
   work, and clear next review action.
2. Company In Detail — Reported/Normalized statements, annual/quarterly/
   cumulative views, original/latest/as-of, revisions, and exact trace.
3. Recent Filings — whole-universe feed, forms, readiness/latency, alerts, and
   export.
4. Multi-Company — 2-10 issuer comparisons with explicit common basis and
   “not comparable” states.
5. Bulk Query / Analytics — metric-period builder, common-size views, peer
   median/percentile, point-in-time cohort receipt, saved screens.
6. Interactive Disclosures — accession/form/topic/keyword search, cross-company
   note comparison, tables, source excerpts, and structural redline.
7. Revision Timeline — what changed, when it became knowable, why a value
   changed, and which rule/source caused it.

**UX law**

- the first screen answers “what changed and what deserves review?”;
- evidence is reachable within two actions;
- raw IDs and receipt mechanics live behind progressive disclosure;
- no score without evidence and no false “nothing changed” when coverage is
  absent;
- responsive EN/ZH, light/dark, keyboard, focus, loading, error, empty,
  partial, stale, and unavailable states are first-class;
- use production-shaped data and attach 1440px and 390px captures to UI PRs.

**Exit gate**

- user-workflow tests cover company -> filing -> finding -> exact source,
  reported vs normalized, as-of, multi-company, disclosure search, and export;
- UI, API, and exported values share the same query receipt;
- no request-time filing computation and no private payload in static HTML.

### Wave 5 — forensic interpretation and specialist data verticals

This is the largest moat-building wave. Ship each family as a registered,
versioned dataset with its own schema, gold sample, coverage receipt, parser
version, confidence, source span/table identity, and “not evaluable” law.

**Priority detector families**

- revenue-recognition policy and estimate changes;
- receivables/revenue and inventory/revenue divergence;
- capitalized-cost and capital-intensity changes;
- recurring restructuring and non-GAAP exclusion creep;
- stock-compensation dilution and share-count bridges;
- tax-rate anomalies and deferred-tax changes;
- pension assumptions and funded-status changes;
- customer/supplier concentration and purchase commitments;
- lease obligations, debt covenants, maturity walls, and refinancing pressure;
- going-concern, auditor, controls/material-weakness, and risk-factor changes;
- segment definition changes and disappearing KPIs.

**Specialist data families**

- operating and geographic segments;
- deferred-tax assets/liabilities and tax reconciliations;
- fair value, Level 3 rollforwards, derivatives, and investments;
- debt instruments, leases, pensions, and equity compensation;
- concentrations, commitments, restructurings, discontinued operations;
- M&A consideration, PPA, goodwill, and acquired intangibles;
- banking, insurance, REIT, energy, utility, and other industry ontologies;
- earnings releases, non-GAAP reconciliations, KPIs, guidance, and
  preliminary/final linkage;
- proxy, auditor fees/flags, controls, people/entity graph, compensation, and
  ownership where lawful source rights exist.

**Interpretation engine**

Use deterministic evidence features first. An LLM may summarize admitted
evidence and competing explanations, but it may not invent a fact, silently
resolve an ambiguous mapping, assert management intent, or become the source of
a detector result. Preserve inputs, thresholds, rule versions, limitations,
benign alternatives, review state, and outcome labels.

**Exit gate**

- 10-20 highest-value detector families are live before long-tail breadth;
- every alert is reversible and calibrated on a time-forward outcome ledger;
- false-positive, abstention, coverage, drift, and correction rates are visible;
- low confidence never masquerades as normalized fact or company quality.

### Wave 6 — full delivery plane: API, exports, alerts, and Excel

**Build**

- versioned typed APIs for companies, filings, statements, metrics, raw XBRL,
  disclosures, dimensions, specialist datasets, lineage, and revisions;
- async CSV/XLSX/Parquet exports with exact query/coverage receipts, expiry,
  quotas, audit logs, and tenant-bound downloads;
- saved screens, portfolios, filing/change alerts, and notification controls;
- Office.js Excel add-in with formula builder, dynamic arrays, statement
  download, trace, original/latest/as-of, refresh, and explicit unavailable
  states;
- security, rate limits, abuse controls, schema migration policy, and client
  compatibility tests.

**Exit gate**

- UI, API, export, and Excel round-trip the same values and receipt IDs;
- Windows/Mac/Web workbook matrix passes;
- no static private URL, cross-tenant object, stale silent export, or unbounded
  query path exists;
- source/licensing terms permit every delivered dataset and redistribution mode.

### Wave 7 — Neural Web, Brain, and Prophet context accrual

This is where Fundamental Forensics becomes strategically more valuable than a
standalone Calcbench clone.

**Build**

- replace current snapshot-only context with compact, receipt-bearing,
  bitemporal packets from the production query plane;
- add deterministic Brain tools for filing changes, disclosure comparison,
  source trace, revision timeline, accounting assumptions, and coverage;
- join filing evidence to earnings, ownership, event, supply-chain, market, and
  position context through stable entity/time keys;
- attach a display-only Prophet evidence pack after selection, never during
  candidate ranking;
- accrue detector outcomes, analyst overrides, corrections, and calibration by
  version and observable date.

**Promotion law**

Initial authority is display/context only. After preregistered, time-forward
measurement, a forensic signal may earn narrowly bounded **risk de-escalation**
or uncertainty-widening authority. It must not boost a candidate, originate a
trade, or become a hidden composite score without a separate governed decision.

**Exit gate**

- historical context never reads a snapshot published after the requested date;
- every context packet carries source, as-of, coverage, rule, and receipt IDs;
- missing/late/partial evidence abstains visibly;
- outcome ledgers are leakage-safe and version-aware;
- any authority promotion has its own preregistration, holdout, rollback, and
  monitoring contract.

### Wave 8 — parity closure and professional hardening

Close the remaining parity ledger only after Waves 0-7 are stable:

- complete supported filing/document/form coverage and processing clocks;
- long-tail metric and specialist-family coverage;
- Raw XBRL and filer-quality surfaces;
- auditor/proxy/compensation/professional workflows;
- notifications, support tooling, usage metering, tenant administration,
  retention, backups, restore drills, incident response, and SLOs;
- blinded parity-by-job audit against the public Calcbench product catalog;
- independent security, temporal-integrity, accessibility, performance, and
  clean-room provenance review.

Full parity means the supported user jobs and acceptance gates are proven. It
does not mean identical screenshots, identical row counts, or proprietary data
we do not have rights to redistribute.

---

## 7. Dependency map

```text
Wave 0A dedicated reader ─> Wave 0B B4F v1 seed/review ─> Wave 1 B4G v2 publication
       │                                                     │
       └─> Wave 0C paid preview (parallel; does not gate B4F) │
                                                             v
Wave 2 corpus + gold QA ─> Wave 3 bitemporal query plane ─> Wave 4 cockpit
             │                    │                           │
             └────────────────────┴──────────────> Wave 5 specialist intelligence
                                                       │
                                                       v
                                         Wave 6 API/export/Excel
                                                       │
                                                       v
                                       Wave 7 Neural Web/Prophet
                                                       │
                                                       v
                                           Wave 8 parity closure
```

Wave 5 families can be developed in parallel once Wave 2 evidence and Wave 3
query contracts are stable. UI prototypes may explore earlier, but they may not
create a second data contract.

---

## 8. Exact first-session runbook for Claude

### 8.1 Establish a clean baseline

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard"
git fetch origin main --prune
git worktree add -b claude/calcbench-wave0-dedicated-reader-YYYYMMDD \
  .claude/worktrees/calcbench-wave0-dedicated-reader-YYYYMMDD origin/main
cd .claude/worktrees/calcbench-wave0-dedicated-reader-YYYYMMDD
git status --short --branch
```

Read the root guidance and current dockets. Query the active build map and DNR
fences. Confirm no active Calcbench/Forensics PR owns the same files.

### 8.2 Reproduce the disconnect before editing

Inspect:

```bash
sed -n '140,175p' app/forensics.py
sed -n '180,210p' engine/research_vault/r2_store.py
sed -n '1050,1080p' engine/research_vault/r2_store.py
sed -n '860,960p' scripts/run_fundamental_forensics_attested_history.py
sed -n '100,125p' .github/workflows/attested-history-aapl-seed.yml
sed -n '100,120p' .github/workflows/attested-history-operator.yml
```

Write a failing API/store integration test proving the receipt route does not
use Research Vault fallback. Then implement Wave 0A.

### 8.3 Baseline and focused validation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_fundamental_forensics_attested_history_operator.py \
  tests/test_fundamental_forensics_attested_history_pilot.py \
  tests/test_fundamental_forensics_attested_history_seed.py

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_fundamental_forensics_attested_query_snapshots.py \
  tests/test_fundamental_forensics_attested_history_reader.py \
  tests/test_forensics_api.py

node --test tests/fundamental_forensics_receipt_contract.test.mjs

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_fundamental_forensics_*.py tests/test_forensics_api.py
```

Add narrow tests for the new reader and deploy allowlist; do not weaken existing
limits merely to make a test pass.

### 8.4 Secret-name audit after Wave 0A ships

Names only—never values:

```bash
gh secret list --json name --jq '.[].name | select(startswith("R2_ATTESTED_HISTORY_"))'
gh secret list --env attested-history-seed --json name \
  --jq '.[].name | select(startswith("R2_ATTESTED_HISTORY_"))'
gh run list --workflow attested-history-aapl-seed.yml --limit 10
gh run list --workflow attested-history-operator.yml --limit 10
```

If any required name is absent, stop before dispatch and request secure operator
provisioning. Do not ask for values in chat.

### 8.5 Ship discipline

For every tracked change:

1. start the task from a freshly fetched `origin/main`; before opening its PR,
   incorporate any necessary current-main update without overwriting unrelated
   work, then rerun validation;
2. stage only explicit task paths;
3. commit, push, and open a PR;
4. default to `gh pr edit <number> --add-label merge-on-green`; the sweeper
   merges only after every non-spurious check concludes. Manual squash-merge is
   allowed only after concluded checks. Never use `gh pr merge --auto --squash`
   because this repository has no branch protection and it merges immediately;
5. verify the merge is an ancestor of `origin/main`;
6. wait for render/VPS deployment as applicable;
7. verify `/api/health` has advanced to the merge or a descendant and test the
   changed live surface;
8. update this handoff's status table with observed evidence, not intent.

Never use an old dirty worktree, never overwrite unrelated changes, never
force-push, never weaken a failed gate, and never claim “live” from a local test.

---

## 9. Capability-to-wave ledger

| Capability | Current | Completion wave |
|---|---|---:|
| Dedicated receipt serving | Disconnected store binding | 0A |
| First controlled source/base seed | Code only; no live run | 0B |
| Paid/free product journey | Security works; UX is unclear | 0C |
| First user-served sealed issuer | No v2 publication | 1 |
| Durable multi-issuer evidence corpus | 12-name bounded slice; one-issuer pilot | 2 |
| 150-300 core normalized metrics | 50-metric kernel; nine live metrics | 3 |
| True original/latest/as-of query | Kernel foundation only | 3 |
| As-reported statements | Missing as a product surface | 3-4 |
| Recent-filings terminal | Partial filing trail only | 4 |
| Multi-company and analytics | Missing | 4 |
| Cross-company disclosure search | Missing | 4 |
| Forensic detector breadth | Five quantitative + five qualitative | 5 |
| Segments/dimensional/specialist data | Mostly missing | 5 |
| Non-GAAP/KPI/guidance/proxy/auditor | Missing or separate narrow collectors | 5 |
| Query API and async export | Missing | 6 |
| Excel delivery | Missing | 6 |
| Receipt-bearing Neural Web context | Current snapshot-only context | 7 |
| Prophet governed evidence use | Missing | 7 |
| Full clean-room parity certification | Not earned | 8 |

---

## 10. Resource and cost truth

This program does not require a multimillion-dollar cash budget simply because
Calcbench advertises hundreds of millions of data points. With Codex/Claude
doing implementation, direct storage for the staged corpus can remain modest on
R2/B2/E2-class object storage, and SEC source access is public.

Costs that do remain real are:

- compute for parsing, reprocessing, query jobs, exports, and tests;
- metadata/query databases, queues, monitoring, backups, and restore capacity;
- source licensing for non-filed releases, transcripts, or other non-SEC data;
- security, tenant isolation, email/alert delivery, Office distribution, and
  operational support; and
- human review for ambiguous mappings and the gold corpus.

Keep spend proportional to evidence: one issuer, then 12, then 200, then broad
coverage. The semantic exception ledger and correction history—not raw object
bytes—are the moat.

---

## 11. What requires operator input

Claude can continue engineering autonomously. Operator input is required only
for boundaries that code cannot manufacture:

- secure provisioning/rotation of the six dedicated secret values;
- protected-environment approval for the first writer run;
- licensed-source decisions for non-SEC content;
- product pricing/entitlement decisions if tiers change; and
- explicit approval of any future authority promotion beyond context-only.

The new bucket has already been created. Do not ask the operator to create a
second one unless a concrete isolation or region requirement is discovered.

---

## 12. Definition of done

The work is not done when the UI looks impressive, the bucket contains many
objects, a fixture passes, or a metric can be queried once.

The parity program is complete only when:

- the full capability ledger is supported or explicitly rights-excluded;
- source, temporal, mapping, disclosure, query, specialist, API/export, Excel,
  workflow/UI, multi-user security, and restore gates pass;
- every displayed value/change reverses to exact evidence and governing rules;
- coverage, confidence, corrections, and unknown states are honest;
- every production change is merged, deployed, and independently checked live;
- a clean-room provenance audit passes; and
- Neural Web/Prophet use remains within its measured authority contract.

Until then, describe progress by the exact wave and acceptance evidence. Never
say “complete Calcbench clone” or “full parity” early.
