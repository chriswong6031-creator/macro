# Government Revenue Foresight Wave 8 handoff

Canonical build and operating handoff for Wave 8. The implementation and local release gates are complete; use this document for subsequent product lanes instead of reconstructing the work from chat.

## Exact workspace state

- Worktree: `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/government-revenue-wave8-foundations-20260802`
- Branch: `claude/government-revenue-wave8-foundations-20260802`
- Final pre-push rebase target: `4e20deecce62ae825bfb4c9b0fd387b4c898c7db` (`origin/main` fetched immediately before the release rebase).
- The branch was cleanly rebased; the only generated-page conflict was resolved by rendering from `templates/government_revenue.html.j2`.
- Wave 8 is ready for the normal push/PR/merge/deploy loop. Use `git log -1 --oneline` and `git status --short` for the latest immutable state.
- Wave 7 was already merged separately in PR #4295; do not fold its old preview processes into this task.
- No competitor login was used and no supplied credential was stored.

## What is implemented locally

### Official USAspending IDV relationship rail

- Bounded official IDV discovery using `POST /api/v2/search/spending_by_award/`.
- Exact IDV activity evidence using `POST /api/v2/idvs/activity/`.
- `CONT_IDV_*` parents and `CONT_AWD_*` children only; direct and grandchild relationships remain distinct.
- Hash-only discovery receipts, immutable selection manifest, collection receipts, append-only semantic history, and exact current-generation active relationship manifest.
- Correct roster rotation, unchanged re-observation, relationship removal, and count-only behavior; historical rows cannot leak into the active projection.
- State/status generation bindings now require matching run, clocks, selection scope, manifest digest, bounds, and counts.
- Four-day freshness rule produces `stale`, never a false `ok`.
- Scheduled configuration covers BA, GD, HII, LMT, NOC, and RTX as collection scope only, never issuer attribution.
- Collector is registered in the normal and slow collection lanes.
- A temporary live probe against USAspending succeeded: 24 parents counted, 15 detail IDVs, 452 relationship rows, 26 receipts, complete and projection-eligible. The temporary bundle was deleted and was not added to the repo.
- The final bounded official source generation is included in the feature worktree for commit: 24 selected/count-verified IDVs, 15 complete-detail parents, 452 exact relationship observations, 26 hash-only receipts, and no collection errors. It is the launch baseline; nightly collection advances it.
- Public selection provenance exposes only `idvsel1-*`, reviewed time, selected-parent count, and scope hashes. Discovery receipts and raw selection-manifest fields remain collector-side official public evidence and are omitted from the browser/static runtime contract. Selected parent IDs remain public source-native relationship/provenance entities and can be reconstructed from the published IDV records; none of this material is confidential.
- The current bounded generation has zero exact generated-ID bridges into the 1,934 prime-award dossier. The API and UI therefore publish award-level `not_observed`, `exhaustive: false`, selection count, and manifest receipt. They explicitly say that bounded absence is not evidence that no relationship exists; no fuzzy bridge is permitted.
- Public validation rejects contradictory parent coverage, including forged `complete` states with missing details. The projector fails closed instead of clipping a complete parent at the public row cap.

### DoD P-1/R-1 budget foundation

- Receipt/content/page-text hashing, official-source URL fencing, fiscal-year/exhibit checks, source-native P-1/R-1 lines, separate request/enacted-reference semantics, quantities, append-only versions, and graph contracts.
- Funding stages remain separate: President's Budget request is not authorization, enacted appropriation, execution, obligation, award value, backlog, or revenue.
- Reviewed program-to-award edges require exact documentary evidence, an exact award key, null economic weight, and no semantic/name matching.
- Clean official Comptroller HTTPS URLs only: no credentials, query, fragment, or non-default port.
- Production activation is deliberately hard-disabled while acquisition, durable storage-write proof, and PDF extraction are fixture-only. This is a foundation, not live DoD budget data.

### API, build, workflows, and projection guards

- New read-only routes:
  - `/api/government-revenue/budget-programs`
  - `/api/government-revenue/budget-line/{line_key}`
  - `/api/government-revenue/program/{program_key}`
  - `/api/government-revenue/award/{award_key}/idv-relationships`
- Exact canonical/public twins for IDV; optional exact twins for DoD budget graph.
- The five collector-owned IDV source files ship in the feature commit. The serialized `government-revenue-live` workflow materializes and commits the canonical/public IDV twins after merge; production is not verified until that projection commit and deployment complete.
- Generic render lanes copy canonical bytes only and fail on one-sided or stale twins.
- Government Revenue live workflow owns projection publication and protects collector-owned source bundles from mutation.
- IDV config/contracts now trigger the serialized Government Revenue projection lane.

### Premium UI

- Added `Budget & Programs` mode with queue count, filter/URL state, loading/unavailable honesty, and a compact premium inspector.
- Added request-amount frame, funding-stage firewall, source-native line cards, reviewed bridge cards, and receipt/page-hash evidence drawer.
- Added optional IDV relationship section inside award dossiers with direct/grandchild labels and exact source evidence.
- Explicit authority copy says relationship only: not vehicle seat, participation, utilization, conversion, award value, revenue, backlog, issuer attribution, or Prophet signal authority.
- Responsive CSS and template/site JavaScript pair are synchronized.
- `site/government_revenue.html` was rendered locally from the committed canonical generation.

## Validation completed

- Complete Government Revenue / USAspending / DoD matrix: `367 passed` with a real zero exit after the final truth-labeling patches.
- Focused Wave 8 hardening matrix: `117 passed`; the final IDV source/artifact/API slice: `26 passed`.
- An additional repository-wide smoke run reached `1,283 passed` with no failures before it was intentionally stopped at 2%; the entire repository matrix is too large and unrelated to serve as this vertical's release gate.
- Template/site synchronization: `79/79` pairs.
- JavaScript syntax checks passed for the paired dossier module and extracted page runtime.
- `python3 -m scripts.build_government_revenue --site-only` passed.
- `python3 -m scripts.check_government_revenue_projection` passed:
  - bundle `grw2-789f370ded31cf1991561da3`
  - 31 events, 1,934 prime awards, 1,949 subawards
  - budget graph absent in the current committed canonical generation, by the production activation fence
- `python3 scripts/check_site_asset_refs.py site` passed.
- `git diff --check` passed.
- Desktop (1280×720) and mobile (390×844) browser QA passed: no page overflow, no console warnings/errors, functional mode switching, and a working mobile inspector sheet. The budget-unavailable state is explicit and does not masquerade as zero.
- A live public-artifact dry projection passed with content ID `griv1-8ad4a70479de9d7f2e33bb96`, 24 parents, 452 relationships, current freshness, verified official discovery provenance, and zero unsafe raw-selection fields.

## Next work in priority order

1. Keep DoD budget data unavailable until a real PDF acquisition/extraction/storage receipt exists. Do not bypass the fixture activation fence.
2. Add targeted award-detail expansion for source-native IDV children. The launch generation has 452 relationships but none intersects the current bounded 1,934-award dossier by exact generated ID; never solve this with fuzzy issuer or PIID matching.
3. Build the SBIR-to-production progression lane, then deepen SAM opportunity coverage when `SAM_API_KEY` is available. OTA normalization remains a separate source-governance problem.
4. Add general parent-IDV dossier navigation only after a bounded public contract and pagination design exists; the current award route intentionally returns exact child bridges only.
5. Keep Government Revenue as a Neural Web display/context lobe until calibrated outcome evidence justifies a separately governed authority proposal. No current field may directly rank, size, gate, originate, add candidates, escalate, or fire Prophet.

## Resume commands

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/government-revenue-wave8-foundations-20260802"
git status --short
git log -1 --oneline
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
pytest -q tests/test_government_revenue*.py tests/test_usaspending*.py tests/test_dod_budget_collector.py tests/test_build_government_revenue.py tests/test_check_government_revenue_projection.py tests/test_dag_conformance.py
python3 -m scripts.check_template_site_sync
python3 -m scripts.check_government_revenue_projection
python3 scripts/check_site_asset_refs.py site
git diff --check
```

## Non-negotiable authority fence

- HigherGov/GovTribe were used only as public product-pattern references. Preserve jobs-to-be-done, not proprietary implementation or copied assets.
- Recipient search terms are collection scope, not public-company attribution.
- IDV observations are relationship context only and cannot rank, size, gate, originate, add candidates, escalate, or feed Prophet as a trusted signal.
- P-1/R-1 requests cannot be relabeled as funded execution or revenue.
- Never expose raw response bodies, headers, credentials, signed URLs, or fuzzy parent/child bridges.
