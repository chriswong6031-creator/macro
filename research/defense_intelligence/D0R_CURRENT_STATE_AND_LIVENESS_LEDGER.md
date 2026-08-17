# D0R Current-State and Liveness Ledger

**Status:** D0R Workstream A started, not complete.  
**Base:** `origin/main` `455284b7beae` (2026-08-16, #5803 squash merge).  
**Production checkout reported by `/api/health`:** `455284b7bea`.  
**Graph on HEAD:** `recipient-graph:reviewed:2026-08-08:defense19-v1`.  
**Open implementation collision:** #5424 defense20-v1 recipient graph.

Do not read this as a finished D0R. Rows below are either verified this session or explicitly `unverified`.

## 1. What a user can actually open today

| Surface | Anonymous result | Entitled result | Notes |
|---|---|---|---|
| `https://www.mastermind-x.com/government_revenue.html` | HTTP 200, 256 KB HTML, tabs named in markup | unverified | Nav and template use underscore. This is the live page. |
| `https://www.mastermind-x.com/government-revenue.html` | HTTP 404 | n/a | Dead twin. Do not cite as the product URL. |
| `https://www.mastermind-x.com/government-revenue-data/latest.json` | HTTP 401 locked + `signin_url` | unverified | Access gate is live. Epistemics remain display/context-only on the artifact. |
| `/api/government-revenue/*` | unverified anonymously; code path is `site_full` router-wide | unverified | 24 GET routes in `app/government_revenue.py`. |

## 2. HEAD capability snapshot (git, 2026-08-13 clocks)

From `candidate_projection_status.json` and `latest.json` at HEAD:

| Item | HEAD value | Clock | Healthy? |
|---|---:|---|---|
| candidate_count | 22 | generated_at 2026-08-13T09:24:42Z | unknown until entitled browser |
| ledger_line_count | 30 | same | unknown |
| mapping_backlog_count | 21 | same | unknown |
| recipient graph | defense19-v1 digest `0733a966…` | reviewed 2026-08-08 | ready per status file |
| latest.json as_of | 2026-08-13 | known_at 08:04:38Z | 3 days behind D0R date; do not call it "today" |
| ingest truncation | `collection_truncated_by_safety_cap: true` | ingest_status | bounded sample, not a full corpus |
| award_event_spine | live; 35239 action-version rows; 194 event snapshots | ingest_status | live ≠ complete |
| authority | display / context_only | both artifacts | no rank/size/gate |

Missing artifacts on HEAD `data/government_revenue/` (not in `git ls-tree`): `budget_program_graph.json` is referenced by the API path list but is not in the committed directory listing above. Treat budget-program graph as `unverified` until the file or an explicit absence is confirmed.

## 3. Engine / builder / DAG (exists ≠ live feature)

Present on disk in this worktree:

- `engine/government_revenue/` — 22 modules.
- builders `scripts/build_government_revenue.py`, `scripts/build_government_revenue_candidates.py`.
- DAG entries `build_government_revenue` and `check_government_revenue_projection`; live workflow `.github/workflows/government-revenue-live.yml`.
- UI: `templates/government_revenue.html.j2` plus radar/dossiers/briefcase JS and parity CSS.

Not yet classified as wired vs built-but-inert: `prophet_annotation.py`, `shadow_context.py`, `sbir_progression.py`, `federation.py`, `market_context.py`, `issuer_graph_expansion.py`. A module file is not a user capability.

## 4. Authority split that must survive every later wave

From `app/government_revenue.py` module docstring and HEAD artifacts:

1. **Access** — paid `site_full`. Anonymous latest.json is 401 locked.
2. **Epistemics** — display/context only. No rank, size, gate, originate, add-candidate, or escalate.

V3 does not change either dimension. D0R must keep them separate.

## 5. Identity / graph collision

HEAD is defense19-v1. #5424 would publish defense20-v1 (BWXT + refreshed exact edges) and is still open. D2 must consume whichever graph is then on `origin/main`; it must not mint a parallel reviewed manifest (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`).

The 2026-08-11 Government Revenue handoff remains useful archaeology and is not current-state truth.

## 6. Stop / continue

Continue in this wave:

1. entitled-browser capture;
2. one source-to-screen lineage;
3. capability/authority ledger including built-but-inert modules;
4. confirm VPS data-dir vs HEAD.

Do not:

- fix the hyphenated 404;
- merge or rebase #5424 from D0R;
- implement D1;
- start original D0.
