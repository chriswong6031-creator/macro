# BioCatalyst SNAPSHOT-ONBOARD A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. No delegated agents are commissioned in this session.

**Goal:** Convert the Chairman-authorized W4-plus-four-CSV finite corpus into deterministic private artifacts, an entitlement-gated Historical Event History API, and an in-place EN/ZH BioCatalyst consumer without changing live CT.gov source/soak authority.

**Architecture:** `engine/biocatalyst/jv_snapshot.py` owns byte admission, workbook/CSV census, Historical FDA repair, normalization and canonical JSONL. `engine/biocatalyst/historical_events.py` owns the pointer-bound public projection and pure query contract under the existing BioCatalyst public root. `scripts/biocatalyst_snapshot_onboard.py` is the explicit finite-ingest operator path using the existing dedicated R2 store. `app/biocatalyst.py` authenticates, loads the validated projection and returns a private DTO. The existing BioCatalyst shell gains one independent historical section; no raw licensed data is committed.

**Tech stack:** Python 3.11+, stdlib CSV/JSON/hash/date/path, openpyxl, pandas/pyarrow only for existing Data OS parquet artifacts, FastAPI, vanilla JS/CSS/Jinja, pytest, JSON Schema, existing BioCatalyst R2/public-root conventions.

**Spec:** `research/BIOCATALYST_SNAPSHOT_ONBOARD_A_CORPUS_AND_CONTRACT_FREEZE_2026-08-24.md`; Macro issue #6374.

**Global constraints:** W4 is canonical; W1 absent by Chairman ruling. Never write licensed raw rows to git. Never edit the two BioCatalyst source/soak manifests. Preserve unresolved identity and temporal poison as typed states. Use `apply_patch`; materialize `site/` before rendering. Stop at one draft `[HOLD-FOR-SOL]` PR with no `merge-on-green`, no native auto-merge and no deployment.

## Task 1: Freeze executable contracts and red tests

**Files:**
- Create: `contracts/biocatalyst/biocatalyst_jv_snapshot_manifest.v1.schema.json`
- Create: `contracts/biocatalyst/historical_event_record.v1.schema.json`
- Create: `contracts/biocatalyst/historical_event_generation.v1.schema.json`
- Create: `tests/test_biocatalyst_jv_snapshot.py`
- Create: `tests/test_biocatalyst_historical_events.py`

1. Write schemas with closed objects for the corpus manifest, product-safe record and pointer-bound generation.
2. Write failing tests for five exact byte hashes, ordered W4 sheets/dimensions, W2/W3 additive classifier, missing/hash mismatch, 4,404 repaired Historical FDA rows, deterministic byte output, duplicate id refusal, malformed date/row, excluded poison/URL fields, and raw/normalized separation.
3. Write failing projection tests for generation/pointer hash validation, last-good retention, deterministic filters/order/cursor, ready/empty/partial/unavailable distinctions and recursive private-field refusal.
4. Run `python -m pytest -q tests/test_biocatalyst_jv_snapshot.py tests/test_biocatalyst_historical_events.py` and confirm failures are missing implementations, not fixture errors.
5. Commit contract/test scaffold only after implementation later greens it; do not commit deliberately red state.

## Task 2: Implement deterministic finite-snapshot admission and normalization

**Files:**
- Create: `engine/biocatalyst/jv_snapshot.py`
- Modify: `tests/test_biocatalyst_jv_snapshot.py`

1. Add frozen `AuthorizedInput` metadata for W4 plus four CSVs, safe-name and exact-byte admission.
2. Implement workbook/CSV logical census and `classify_workbooks()` with the four issue-authorized relationship labels.
3. Implement Historical FDA missing-index repair from raw CSV-reader rows; require exactly 15,700 rows and 4,404 repairs for the frozen hash while permitting fixture counts through explicit expected parameters.
4. Normalize Historical FDA, Device History and honest historical Device Pipeline rows into closed records. Parse DD/MM/YYYY `ET` as a calendar date with `day` precision and no invented intraday timezone. Exclude poison and private locator fields at construction time.
5. Resolve identity through injected `VendorAliasTable`/`IssuerMaster`; never fuzzy match. Carry event-date alias evidence and current-only issuer caveat as typed state.
6. Generate stable source-projection ids and canonical JSONL; reject divergent duplicate ids and prove fixed-point bytes.
7. Run the Task 1 ingestion tests until green.

## Task 3: Implement existing-plane storage and pointer-bound read projection

**Files:**
- Create: `engine/biocatalyst/historical_events.py`
- Create: `scripts/biocatalyst_snapshot_onboard.py`
- Modify: `tests/test_biocatalyst_historical_events.py`
- Modify: `tests/test_biocatalyst_jv_snapshot.py`

1. Implement immutable raw, manifest and normalized R2 keys using the existing `BinaryObjectStore`/`mirror_bytes_verified` seam. Verify readback before any public promotion.
2. Implement a public projection at `<BIOCATALYST_PUBLIC_ROOT>/historical_events/generations/<content-id>/` with closed `manifest.json`, `events.jsonl` and last-written atomic `current.json`. Reject symlinks, unexpected files, hash/byte mismatch and pointer-generation mismatch.
3. Implement `read_current()` and pure `query_events()` with deterministic descending order, closed filters and HMAC query-bound cursor.
4. Implement the explicit CLI with required five input paths, identity root, public root and `--publish-private` switch. Default `--check` builds and verifies without external writes; private publication requires existing dedicated BioCatalyst R2 environment and does not print secrets/object payloads.
5. Run fixed-point and hostile projection tests until green.

## Task 4: Add entitlement-gated API

**Files:**
- Modify: `app/biocatalyst.py`
- Create: `tests/test_biocatalyst_historical_event_api.py`

1. Write failing API tests for signed-out/ineligible denial, private headers, valid real-shaped response, filters, invalid cursor/query, unavailable/partial/empty reasons and recursive leakage guard.
2. Add lazy runtime import and `GET /api/biocatalyst/v1/historical-events` using `require_site_full_user` and `_PRIVATE_HEADERS`.
3. Read only the pointer-bound Historical Event projection; return context-only authority and corpus denominators. Do not expose private paths, hashes, receipts or raw rows.
4. Run `python -m pytest -q tests/test_biocatalyst_historical_event_api.py tests/test_biocatalyst_api.py tests/test_biocatalyst_catalyst_radar_api.py` until green.

## Task 5: Add in-place Historical Event History consumer

**Files:**
- Modify: `templates/biocatalyst.html.j2`
- Modify: `templates/biocatalyst.js`
- Modify: `templates/biocatalyst.css`
- Create: `tests/test_biocatalyst_historical_event_ui.py`
- Modify: `tests/biocatalyst_hydration_harness.js`
- Modify: `tests/test_biocatalyst_hydration.py`
- Generate: `site/biocatalyst.html`
- Generate: `site/biocatalyst.js`
- Generate: `site/biocatalyst.css`

1. Write failing DOM/static/hydration tests for EN/ZH labels, company/ticker/date/family/stage/asset filters, ready/empty/partial/unavailable/access states, expandable provenance/repair/identity detail and recursive text leakage.
2. Add one Historical Event History section to the existing BioCatalyst workbench. Keep the current Trial Milestones experience unchanged.
3. Append an independently guarded client controller that requests only the historical endpoint when the section exists, validates the closed DTO, renders deterministic rows/details, and handles all typed states without zeros or silent disappearance.
4. Add token-only responsive CSS for desktop/mobile, dark/light and EN/ZH. No global nav overrides.
5. Materialize `site/` with `python3 scripts/worktree_sparse.py add site`, run `python -m scripts.build_biocatalyst`, then verify template/site byte sync.
6. Run `node --check templates/biocatalyst.js` and focused UI/hydration/page tests.

## Task 6: Wire CI, Agent OS and durable handoff

**Files:**
- Modify: `.github/ci/legacy-jobs.yml`
- Modify: `agentos/workstreams/WS-BPC-JV-RECON.md`
- Create: `agentos/handoffs/BPC-JV-RECON-2026-08-24-SNAPSHOT-ONBOARD-A.md`

1. Add all new test modules to the existing `biocatalyst-serving` run command; create no new job.
2. Update `WS:BPC-JV-RECON` from stale commissioning language to active `SNAPSHOT-ONBOARD A` held-for-Sol state. Preserve RECON-0 and continuation boundaries.
3. Write a cold-start handoff containing exact base/Skillpack/input hashes, architecture, counts, proof commands, PR/head placeholders replaced with exact values before final commit, unresolved production upload/deploy gate, and no-next-wave rule.
4. Run `python3 scripts/agentos.py validate`, `python3 scripts/check_contract_delta.py --base origin/main --head HEAD`, CI manifest validation and `git diff --check`.

## Task 7: Exact-head verification, browser proof and held PR

**Files:** no new scope; only proof-driven fixes within files above.

1. Run the real five-file CLI in check/build mode twice and compare normalized/generation bytes. Record family and identity counts without recording licensed rows.
2. Start the exact branch app against the generated real-input historical projection and a controlled existing CT.gov projection. Run real Chromium at desktop/mobile, dark/light and EN/ZH; verify nonzero history, filters, one detail trace, one repaired-row trace, no overflow and no console errors.
3. Run current `biocatalyst-serving`, sponsor/ticker, template/site sync, title i18n, Agent OS, contract delta, CI manifest, 12 CI packs, fences, self-mod fence, capability broker and grader-manifest checks required by current main.
4. Re-fetch `origin/main`, recheck open PR changed-path collision and rebase only if a genuine semantic conflict requires it under current authority.
5. Commit, push, open one draft PR titled `[HOLD-FOR-SOL] BioCatalyst SNAPSHOT-ONBOARD A — Historical Event History`; ensure `merge-on-green` absent and `autoMergeRequest` null. Add the exact proof/production gate and stop for Sol.

## Self-review

- **Spec coverage:** admission, census, rights, storage, identity, clocks, repair, deterministic projection, API, entitled UI, hostile tests, browser proof, CI/Agent OS and hold state are each mapped to a task.
- **Placeholder audit:** no implementation `TODO`, `TBD`, ellipsis or invented production receipt is permitted. Handoff PR/head fields are populated only after the exact objects exist.
- **Type consistency:** source-projection ids never masquerade as fiscal/canonical company-event ids; ticker remains evidence; event date and capture/observed clocks stay separate; issuer mapping remains current-only when that is all the owner plane can prove.
- **Scope audit:** no live source registry, soak/cohort/cadence, continuous BPC, M&A/ownership/options/probability/Prophet, P1-2, deployment or merge action is present.
