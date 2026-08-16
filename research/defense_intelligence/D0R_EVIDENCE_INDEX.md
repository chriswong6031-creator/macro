# D0R Evidence Index

**Wave:** D0R (in progress, not complete)  
**Date:** 2026-08-16  
**Branch:** `claude/defense-procurement-d0r-20260816`  
**Canonical architecture:** `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`  
**Canonical handoff:** `research/DEFENSE_PROCUREMENT_D0R_FINANCIAL_ALPHA_RECONNAISSANCE_HANDOFF_2026-08-16.md`

Every load-bearing current-state claim in this D0R kickoff points here.

## Repository ancestry

| Claim | Command | Result |
|---|---|---|
| V3/D0R architecture merged | `gh pr view 5803 --json state,mergedAt,mergeCommit` | MERGED 2026-08-16T19:05:39Z; merge `455284b7beaefee4743c8e925d8000361f0d4cb8` |
| Files present on `origin/main` | `git cat-file -e origin/main:research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md` (and D0R twin) | both exist |
| D0R worktree base | `git rev-parse HEAD` in `.claude/worktrees/defense-procurement-d0r` | `455284b7beae` |
| Open GovRev implementation PR | `search_pull_requests` `is:open government-revenue OR govrev` | #5424 still open (`data(govrev)` defense20-v1 recipient graph). #5803 no longer open. |

## Production / live

| Claim | Command | Result |
|---|---|---|
| VPS serving the merge checkout | `curl -sS -L https://mastermind-x.com/api/health` | `{"status":"ok","commit":"a0b2aba13b5","checkout":"455284b7bea"}` |
| Hyphenated page URL is dead | `curl -sS -L https://mastermind-x.com/government-revenue.html` | HTTP 404, 0 bytes at `https://www.mastermind-x.com/government-revenue.html` |
| Underscore page URL is live | `curl -sS -L https://mastermind-x.com/government_revenue.html` | HTTP 200, 256555 bytes; title `Government Revenue Foresight — Mastermind`; HTML contains Candidate Radar, Award Tape, Recompete, Opportunities, Companies, Budget, locked, workspace |
| Anonymous latest.json is locked | `curl -sS -L https://www.mastermind-x.com/government-revenue-data/latest.json` | HTTP 401 `{"locked":...,"reason":...,"signin_url":...}` |
| Nav target | `templates/_navlinks.html.j2:300` | `href="{{ NP }}government_revenue.html"` |

Anonymous HTML presence is not entitled-browser proof. Signed-in network/API capture is still open.

## HEAD artifacts (git, sparse-safe)

Read with `git show HEAD:<path>`. `data/` is omitted from this sparse worktree on disk.

| Claim | Command | Result |
|---|---|---|
| Company artifact clocks | `git show HEAD:data/government_revenue/latest.json` | schema `company_government_revenue.v1`; `as_of` 2026-08-13; `known_at` 2026-08-13T08:04:38Z; `generated_at` 2026-08-13T09:24:42Z |
| Authority on latest.json | same | `tier=display`, `context_only=true`, all rank/size/gate/originate/add/escalate flags false |
| Candidate projection status | `git show HEAD:data/government_revenue/candidate_projection_status.json` | `candidate_count` 22; `ledger_line_count` 30; `mapping_backlog_count` 21; graph `recipient-graph:reviewed:2026-08-08:defense19-v1`; `source_health.status=ok` |
| Collection bound | `git show HEAD:data/government_revenue/ingest_status.json` | `collection_truncated_by_safety_cap: true`; `award_event_spine.activation_state=live`; actions_seen 34306 / actions_total 35242 |
| Artifact inventory | `git ls-tree --name-only HEAD:data/government_revenue` | awards/actions/events parquets; candidate queue/ledger/status; dossiers; IDV; subaward; workspace; recipient_entity_graph; ingest/heartbeat receipts |

These are committed HEAD bytes, not a live entitled API payload.

## Code / runtime owners

| Claim | Evidence |
|---|---|
| Engine modules | `ls engine/government_revenue` — 22 modules including `candidates`, `award_events`, `entity_resolution`, `opportunities`, `prophet_annotation`, `shadow_context`, `idv_*`, `subaward_dossiers`, `workspace` |
| API gate | `app/government_revenue.py` module docstring + `APIRouter(dependencies=[Depends(require_site_full_user)])` at line 102 |
| API mount | `app/main.py` ~1961 `include_router(government_revenue_router)` |
| API routes | 24 `@router.get("/api/government-revenue/...")` routes from `/latest` through `/event/{event_id}` |
| DAG | `config/dag.yml` `build_government_revenue`, `check_government_revenue_projection`, workflow `.github/workflows/government-revenue-live.yml` |
| Program key | `config/mastermind_programs.yml` `government-revenue-foresight` — authority_class `context_only` |

## Explicitly unverified (must not be treated as proven)

- Entitled signed-in browser: tabs, row counts, console/network errors, 1440/820/390.
- Production data-dir vs git HEAD drift on the VPS.
- Why `/api/health` `commit` is `a0b2aba13b5` while `checkout` is `455284b7bea`.
- Mastermind `config/strategic_state.yml` — not present in this Mastermind checkout.
- Runtime lineage of one award-change event source→browser.
- Built-but-inert module census (Prophet annotation, shadow context, SBIR, federation).
- #5424 merge/conflict state beyond "still open".

## Next evidence to collect

1. Entitled session capture of `government_revenue.html` and `/api/government-revenue/latest`.
2. One event traced through `award_event_snapshots` → candidate projection → API → browser.
3. Capability/authority ledger for every visible tab and every engine module.
4. Confirm whether VPS `data/government_revenue` matches HEAD `defense19-v1` or a newer unpublished graph.
