# D0R Current-State and Liveness Ledger

**Status:** D0R continuation A/B/C filed; entitled A still open; D0R not accepted.  
**Base at capture:** `origin/main` `e7cdfa257322` (2026-08-16, #5808).  
**Production `/api/health`:** `checkout=e7cdfa25732`, `commit=a0b2aba13b5`.  
**Graph on HEAD:** `recipient-graph:reviewed:2026-08-08:defense19-v1`.  
**Open implementation collision:** #5424 defense20-v1.

Do not read this as a finished D0R.

## 1. What a user can actually open today

| Surface | Anonymous / this-agent result | Entitled result | Notes |
|---|---|---|---|
| `https://www.mastermind-x.com/government_revenue.html` | HTTP 200 compact teaser: 2 award-change rows, 21 companies, membership banner | unverified | Underscore URL. Evidence cut 2026-08-13. |
| `https://www.mastermind-x.com/government-revenue.html` | HTTP 404 | n/a | Dead twin. |
| `government-revenue-data/{latest,workspace,candidates}.json` | HTTP 401 locked `authentication_required` | unverified | Access gate live. |
| `/api/government-revenue/*` | HTTP 401 `missing bearer token` | unverified | Router-wide `site_full`. |
| Candidate Radar | 0, loading copy, filmstrip “Link status unavailable” | unverified | HEAD `candidate_count` 22 — 0 is not EMPTY_VALID. |
| Changes / Award tape | 2 compact rows (HC101319C0006 IRDM, N0002415C2114 HII) of workspace `total` 500 | unverified | `PARTIAL` + `ENTITLEMENT_REQUIRED` for the rest. |
| Opportunities | 0 | unverified | `SOURCE_UNAVAILABLE` in freshness. |
| Recompete / Budget | 0 | unverified | Budget artifact missing on HEAD (`PROJECTION_MISSING`). |
| Companies | 21 names | unverified | Link state blocked by candidate API. |

## 2. HEAD capability snapshot (git, 2026-08-13 clocks)

Unchanged from kickoff: candidate_count 22; ledger_line_count 30; mapping_backlog_count 21; graph defense19-v1 digest `0733a966…`; latest.json as_of 2026-08-13; ingest truncated by safety cap; award_event_spine live; authority display/context_only.

New: live compact bundle id `grw2-dd9d7af893a7f3c773909351` matches HEAD workspace. Collection receipts for the golden award continue through 2026-08-14 with a new actions `response_sha256`; the published event is pinned to the 2026-08-12 receipt.

Budget `budget_program_graph.json` / `budget-program.json` confirmed **absent** on HEAD (`git cat-file` miss).

## 3. Engine / builder / DAG

Present: 22 modules under `engine/government_revenue/`. Builders and `government-revenue-live.yml` remain the producer path. Render expects `budget-program.json` that is not committed.

Wired beyond the page: `federation.reviewed_award_change_context` → Prophet bridge + Neural Web context (live output not captured). `prophet_annotation.annotate_plans_from_repo` fail-open on Prophet plans.

Dark (tests only / no builder import): `shadow_context`, `market_context`, `sbir_progression`, `issuer_graph_expansion`.

## 4. Authority split

1. **Access** — paid `site_full`. Anonymous artifacts 401 locked.
2. **Epistemics** — display/context only. No rank, size, gate, originate, add-candidate, or escalate.

V3 does not change either dimension.

## 5. Identity / graph collision

HEAD is defense19-v1 (19 graph companies). Compact strip lists 21 names (includes GE, BWXT). #5424 defense20-v1 still open. D2 must not mint a parallel reviewed manifest (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`).

## 6. Stop / continue

This continuation stops. Next authorized D0R action: entitled `site_full` browser census, then architecture-handoff workstreams B–H.

Do not:

- start D1 or original D0;
- merge or rebase #5424;
- repair the UI defects listed in `D0R_DISCOVERY_AND_BLOCKERS.md`;
- grant rank/gate/size/entry/execution authority.
