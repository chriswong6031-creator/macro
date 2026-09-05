# D5 Earnings Intelligence Vector Implementation Plan

> **Execution:** Use `superpowers:subagent-driven-development`; every production behavior follows RED → GREEN → REFACTOR and every task receives an independent review before the next task begins.

**Goal:** Ship the first bounded D5 Earnings evidence translation as an authenticated Prophet Lab episode-detail read, preserving B1 generation identity, lawful point-in-time Earnings revision selection, typed absence/correction states, and zero execution or ranking authority.

**Binding specification:**

- `research/prophet_v4/flagship_cells/CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md`
- `research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md`
- `agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-26-d5-architecture-reconciled.md`
- `agentos/decisions/DEC-PROPHET-B1-CANONICAL-EPISODE-BINDINGS.md`
- `agentos/decisions/DEC-PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY.md`

**Architecture:** Extend the existing Data OS identity reader with one fail-closed current issuer-to-CIK lookup. Add one pure, dependency-injected `prophet.intelligence_vector/v1` projection module that consumes an exact B1 snapshot plus the existing verified Earnings revision-chain reader. Wire a single read-only detail route into the existing Prophet Lab router. Do not add a cache, store, queue, scheduler, ranker, lifecycle owner, identity plane, or live-writing path.

**Global constraints:**

- Use `load_candidate_episode_store_snapshot`; pin both exact `episode_id` and exact `generation_id`.
- Resolve `ISS -> CIK` only through `lib.dataos.identity.IssuerMaster`; never direct-read identity parquet in D5, compare unrelated company IDs, join on ticker, or use alias fallback.
- Use `read_event_source_revisions`/`read_all_event_source_revisions`; never use a current-body reader for decision-time evidence.
- Admit revisions only under A7 clocks and correction-generation law. Later revisions are lineage and never rewrite the decision observation.
- Emit only `earnings.event`, `fusion_bindings: []`, `tradable_at: NOT_ASSERTED`, content-addressed projection IDs, conservative dependence groups, typed missingness/correction states, and all authority flags false.
- Never serialize raw workspaces, source bodies, claims, transcripts, private paths, arbitrary owner dictionaries, scores, ranks, weights, confidence, conviction, counts, or `ENTRY_OPEN` synonyms.
- Keep `consensus_unlicensed` as a warning, never a numeric/neutral/rights-blocked value.
- Stop after the one Earnings family and one Prophet Lab consumer are accepted on main and proven live.

## Task 1: Canonical current issuer-to-CIK identity seam

**Files:**

- Modify: `tests/test_dataos_identity.py`
- Modify: `lib/dataos/identity.py`

1. Add focused failing tests for exact ten-digit CIK resolution, repeated same-CIK rows, absent/NaN CIK returning `None`, normalization, and conflicting non-null CIKs failing closed with the existing typed identity error family.
2. Run only the focused new tests and record the expected RED caused by the absent API.
3. Extend `SecurityIssuerRow`/`IssuerMaster.from_records` to retain the already-present `issuer_cik` without adding a second source or reader.
4. Add `IssuerMaster.cik_of_issuer(issuer_id: str) -> str | None` with current-observation-only semantics and conflict refusal.
5. Run the focused tests, then the complete `tests/test_dataos_identity.py` file. Keep the change minimal and backward compatible.
6. Commit this task independently and obtain a task-scoped spec/quality review.

## Task 2: Pure D5 Earnings projection and real-reader correction battery

**Files:**

- Create: `engine/prophet_lab/intelligence_vector.py`
- Modify: `tests/test_company_intelligence_workspace_chain.py`
- Modify: `tests/test_prophet_lab.py`

1. Add RED tests that define the closed envelope, exact B1 episode/generation pin, content-addressed `projection_id`, decision-cut fields, allowlisted Earnings values, source/evidence refs, conservative dependence groups, typed coverage/identity/admissibility states, `fusion_bindings: []`, `tradable_at: NOT_ASSERTED`, and all-false authority.
2. Add RED negative tests rejecting prohibited authority/ranking/count fields and preventing raw workspace/body/claim/transcript/private-path leakage.
3. Using the existing `_raw_workspace`, `_mint`, and `_server` helpers, add RED real-reader tests for:
   - two generations with distinct `issuer_release` hashes: decision observation stays at N while N+1 is `OBSERVED` correction lineage;
   - two body generations without `issuer_release`: reader collapse forces `NOT_OBSERVABLE`, never “no correction”;
   - `source_available_at <= cut < observed_at`: `ABSENT`, `NOT_CAPTURED_AT_DECISION`, `AFTER_DECISION_CUT`;
   - unknown clocks: typed `UNKNOWN` naming the missing clock;
   - unresolved tie: typed `CONFLICTED`;
   - broken predecessor/hash/bound: `UNESTIMABLE` or `CORRECTION_PENDING` only with a sanitized `WorkspaceChainIntegrityError` receipt;
   - one verified fetch per chain hop.
4. Verify every new test fails for the missing D5 module/behavior before production code is written.
5. Implement a pure/injectable adapter and closed validator. Keep B1, Earnings reader, Context Vector, Fusion, rank, workflows, and data stores unchanged.
6. Use current-generation manifest event discovery only after canonical identity resolution and disclose that limitation in the response receipt. Do not conceal it as historical event-set reconstruction.
7. Run focused RED/GREEN cycles, then both full test files. Commit independently and obtain a task-scoped spec/quality review.

## Task 3: Existing Prophet Lab read-only episode-detail route

**Files:**

- Modify: `tests/test_prophet_lab_api.py`
- Modify: `app/prophet_lab.py`

1. Add RED API tests for a bounded route under the existing Prophet Lab API family: anonymous `401`, free-tier `403`, paid `200`, private/no-store headers, existing kill switch `503`, absent episode `404`, typed `200` identity-unresolved/not-covered, corrupt B1 or source-integrity `503`, and no prohibited/raw fields.
2. Verify RED is caused by the missing route.
3. Add exactly one route to the existing router, using `require_site_full_user`, existing response framing, and the existing kill switch. Load an atomic B1 snapshot, find one exact episode, construct `IssuerMaster`, and call the pure D5 adapter.
4. Keep the endpoint read-only and side-effect free. Do not add caches, background work, new routers, queues, stores, or lifecycle authority. The endpoint performs one bounded event chain read for the requested episode, not a four-event fan-out.
5. Run the focused API tests and complete `tests/test_prophet_lab_api.py` plus `tests/test_prophet_lab.py`. Commit independently and obtain a task-scoped spec/quality review.

## Task 4: Integrated verification, records, delivery, and live proof

**Files:**

- Modify only the narrow D5 state in `research/prophet_v4/CAPABILITY_LEDGER.md`
- Modify only the D5 state in `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md`
- Add a dated D5 acceptance handoff under `agentos/handoffs/`
- Modify other records only if the binding Agent OS protocol requires them for exact evidence

1. Run the complete focused battery:

   ```bash
   pytest -q tests/test_dataos_identity.py
   pytest -q tests/test_company_intelligence_workspace_chain.py
   pytest -q tests/test_prophet_lab.py tests/test_prophet_lab_api.py
   python3 scripts/agentos.py validate
   ```

2. Run the repository-owned CI pack validation/job lines selected by the changed-path routing. Do not run the full suite in a sparse worktree.
3. Dispatch one independent hostile whole-branch reviewer against the exact base/head, binding Cell F contract/amendments, changed-file census, and prohibited-state checklist. Fix load-bearing findings test-first and re-review the fix.
4. Re-fetch and reconcile fresh `origin/main`; re-run the exact relevant tests before push. Preserve unrelated dirt and never touch the shared `index.lock`.
5. Commit records only after implementation evidence is exact. Push the `claude/d5-earnings-20260829` branch, open one PR, arm `merge-on-green`, wait for every binding check to conclude, resolve genuine failures, squash-merge, and verify the merge commit plus exact main file hashes.
6. Wait for the repository's normal deploy lane. Verify the real authenticated paid endpoint for one exact covered B1 episode and separately verify typed unresolved/not-covered behavior. Record source, observed, produced, and browser/consumer clocks separately; verify exact B1 generation/event/source refs, no raw bodies, all authority false, empty fusion bindings, and absence of score/rank/weight/count/entry fields.
7. Update the closeout records with exact PR/source/merge/CI/deploy/live receipts, validate them, deliver them through the same full PR/merge/main/live chain if they are a separate carrier, and return the final evidence packet.
8. Stop. Do not start Defense, Bio, Institutional, a second adapter family, a cache/index program, or any later wave.
