# D0R Current-State and Liveness Ledger

**Status:** Entitled A captured; architecture B–H filed; D0R not accepted; D1 not started.  
**Production `/api/health` (2026-08-17T04:45Z):** `checkout=8b5cd60f706`, `commit=a0b2aba13b5`.  
**Graph on HEAD:** `recipient-graph:reviewed:2026-08-08:defense19-v1`.  
**Open implementation collision:** #5424 defense20-v1.

Do not read this as a finished D0R.

## 1. What a user can actually open today

| Surface | Anonymous | Entitled site_full (2026-08-17T04:41Z) | Notes |
|---|---|---|---|
| `government_revenue.html` | 200 compact teaser: 2 rows, membership banner | 200; Changes/Award **500**; loading banner leftover | Underscore URL. Cut 2026-08-13. |
| `government-revenue.html` | 404 | 404 | Dead twin. |
| `government-revenue-data/{latest,workspace,candidates}.json` | 401 locked | **200** (workspace 500, candidates.json 22) | Cookie plane |
| `/api/government-revenue/*` cookie-only | 401 missing bearer | **401** missing bearer | Needs Authorization |
| `/api/government-revenue/*` with page bearer | n/a | **200** (workspace 500/50, candidates 22, mapping-backlog 21) | FastAPI plane |
| Candidate Radar | 0 | **0 + membership overlay** despite API 22 | `DSC:GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200` |
| Changes / Award tape | 2 of 500 | **500** including P00032 + balance-changed sibling | Compact is not the desk |
| Opportunities | 0 | 0 | `SOURCE_UNAVAILABLE` |
| Recompete | 0 | 0 | not in this cut |
| Budget | 0 | 0 “Budget request rail unavailable” | `PROJECTION_MISSING` |
| Companies | 21; Link status unavailable | 21; **Members only** | copy not updated after auth |

## 2. HEAD capability snapshot

Unchanged clocks: candidate_count 22; mapping_backlog 21; graph defense19-v1; latest as_of 2026-08-13. Budget files still absent. Collection receipts through 2026-08-14; published cut 2026-08-13.

## 3. Auth planes

Cookie JSON and bearer APIs are separate (`DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES`). Radar JS uses only the bearer queue.

## 4. Authority

All V3 / GovRev flags stay `can_rank/gate/size/entry/execute=false`. Prophet remains pick authority.
