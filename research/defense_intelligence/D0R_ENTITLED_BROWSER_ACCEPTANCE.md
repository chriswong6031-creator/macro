# D0R Workstream A — Production browser acceptance

**Capture window:** 2026-08-17T01:51Z–02:01Z (UTC)  
**Route:** https://www.mastermind-x.com/government_revenue.html  
**Session class actually obtained:** unentitled / anonymous Cursor+Chrome browser  
**Entitled `site_full` session:** not obtained — `SIGN_IN_REQUIRED`

This artifact answers the standing question with the session that existed, not the session that was wanted. A 200 HTML shell is not entitled-product proof. The entitled APIs were probed from the same browser and returned 401.

## 1. Runtime identity (do not assume GitHub main == VPS)

| Field | Value | How recorded |
|---|---|---|
| `origin/main` SHA at worktree | `e7cdfa25732209d56633f2d734024c90057d3538` | `git rev-parse HEAD` after `git fetch` + worktree from `origin/main` |
| Production `/api/health` | `{"status":"ok","commit":"a0b2aba13b5","checkout":"e7cdfa25732"}` | same-origin fetch and anonymous curl, 2026-08-17T01:51Z |
| Checkout vs GitHub | VPS checkout matches current `origin/main` prefix `e7cdfa25732` | health JSON |
| Runner `commit` field | still `a0b2aba13b5` (not the checkout) | unexplained; not rediscovered as a defect in this wave |
| HTML `Last-Modified` | Fri, 14 Aug 2026 12:51:09 GMT | response headers |
| HTML bytes | 256555 (curl) / 244800 decoded | public GET |
| Page title | Government Revenue Foresight — Mastermind | live DOM |
| Asset versions (determinable) | `government-revenue-dossiers.js?v=bb1a583e`; `government-revenue-candidate-radar.js?v=c705713b`; `government-revenue-briefcase.js?v=22f49156`; `government-revenue-briefcase-ui.js?v=d92aa027`; `theme.css?v=54439ad9`; `government-revenue-parity.css?v=a45b5eb3`; `account.js` / `nav_market.js` `?v=20260814-sf-inter-font-upgrade` | live HTML |
| Compact artifact schema | `company_government_revenue.v1` | `#gov-data` |
| Workspace schema / bundle | `government_procurement_workspace.v2` / `grw2-dd9d7af893a7f3c773909351` | `#gov-data` |
| Artifact clocks | `as_of=2026-08-13`; `known_at=2026-08-13T08:04:38.715316+00:00`; `generated_at=2026-08-13T09:24:42.812875+00:00`; `published_at=absent` | `#gov-data` |
| Recipient graph on HEAD | `recipient-graph:reviewed:2026-08-08:defense19-v1` digest `0733a966c4442a4fc5bb883d1670320218ecc3b6754131f7ee84965d3036f758` | `candidate_projection_status.json` |
| API/schema contract | compact page embed `company_government_revenue.v1` + workspace `government_procurement_workspace.v2`; paid router `app/government_revenue.py` 24 GET routes, `require_site_full_user` | code + live 401s |
| Capture time | Cursor CDP `2026-08-17T01:54:09.346Z`; Chrome headless screenshots ~02:00Z | this session |

Production had moved since the architecture merge (`checkout` was `455284b7bea` at kickoff; now `e7cdfa25732`). The Government Revenue compact payload clocks did **not** move with that checkout — they remain 2026-08-13.

## 2. Authenticated flow — what was actually proven

| Required step | Result | State |
|---|---|---|
| Session restoration | No Supabase session in the Cursor isolated browser. Header showed Settings/Terminal, not an account chip. | `SIGN_IN_REQUIRED` |
| Entitlement recognized | Workspace hydration `GET government-revenue-data/workspace.json` → 401 `{"locked":true,"reason":"authentication_required","signin_url":"/?signin=1"}`. Banner: “Showing the first 2 governed records. The complete workspace is part of a membership.” | `ENTITLEMENT_REQUIRED` (access) after auth |
| Protected requests authenticated | `/api/government-revenue/{latest,candidates,workspace,events}` → 401 `{"detail":"missing bearer token"}` | `AUTH_BOOTSTRAP_FAILED` for the API plane |
| Expected APIs return correct type | 401 JSON, `content-type: application/json` — correct *failure* type, not a payload | `API_UNAVAILABLE` for entitled read-models |
| Real records render | Yes — compact `#gov-data` still paints 2 award-change rows and 21 companies | `PARTIAL` |
| Tabs switch | Yes (Cursor snapshot + `?mode=` screenshots) | proven for compact shell |
| Record detail opens | Yes — HC101319C0006 inspector with revision diff, receipts, official source | proven for compact row |
| Evidence/source actions | Official USAspending link present; View receipts control present; full drawer not pixel-captured after browser MCP drop | `PARTIAL` |
| Back/refresh | not exercised after MCP drop | `UNKNOWN` |
| Unexpected runtime errors | no pageerror captured; candidate/budget UIs sit in loading then degrade | `PARTIAL` |

**Verdict for Workstream A:** an entitled user was **not** proven. An unentitled user **can** open the live page and use a two-record compact Change/Award tape plus a 21-name company filmstrip. The complete 500-event workspace, Candidate Radar ledger, dossiers APIs, briefcase save/export, and budget graph do not hydrate without authentication.

Do not label the entitled product `PROVEN_LIVE`.

## 3. Tab census (unentitled production)

Headline counters on the compact page: Watch with qualified coverage / “Partial or stale coverage”; Governed changes **500**; Active opportunities **0**; Closing in 30 days **0**; Mapped exposure **$206.7B**. The 500 is the workspace `total`, not the 2 rows the anonymous browser is allowed to list (`next_cursor=djI6Mg`).

| Tab | Visible count | API/source state | Freshness | Valid-empty vs unavailable | Graph/mapping dependency | User-visible failure | Representative row |
|---|---:|---|---|---|---|---|---|
| Candidate Radar | 0 | `/api/government-revenue/candidates` 401 missing bearer; `candidates.json` 401 locked | candidate UI “Checking exact issuer links” then empty | **not** a valid empty: HEAD `candidate_count=22` | exact issuer path + candidate ledger | loading copy; filmstrip “Link status unavailable” (not “Members only”) | none |
| Changes | 2 | compact workspace events only; full `workspace.json` 401 | workspace freshness `partial`; award_events ok on HEAD status | compact teaser, not the 500 | reviewed issuer path on both visible rows | membership banner | `New obligation observed — HC101319C0006` / IRDM |
| Award Tape | 2 | same compact events (award_change kind) | same | same | same | membership banner | same two rows |
| Opportunities | 0 | compact `opportunity_intelligence.opportunities=[]`; SAM rail freshness `unavailable` | `freshness.opportunities.status=unavailable` | **SOURCE_UNAVAILABLE**, not EMPTY_VALID | none in this cut | 0 active opportunities in headline | none |
| Recompete Watch | 0 | compact workspace has no recompete events; award-detail freshness claims 170 visible award records | recompetes freshness object reused award-detail `ok` | compact 0 is **omission by lock/cap**, not proof the rail is empty | award end dates | empty queue | none |
| Budget & Programs | 0 | `budget_program_graph.json` / `budget-program.json` **absent from HEAD**; UI “Loading budget request graph” | budget verifying → no rows | **PROJECTION_MISSING** | DoD P-1/R-1 graph | loading, then 0 programs | none |
| Companies | 21 | compact `DATA.companies` | coverage 21 mapped | list is populated | filmstrip link-state needs candidate API | “Link status unavailable” on every chip | LMT · Lockheed Martin |

## 4. Network / status / content-type matrix

All fetches used `credentials: same-origin` from `https://www.mastermind-x.com/government_revenue.html` at 2026-08-17T01:54:45Z. No cookies or Authorization headers are recorded.

| URL | HTTP | Content-Type | Body class |
|---|---:|---|---|
| `government-revenue-data/workspace.json` | 401 | application/json | locked + `authentication_required` |
| `government-revenue-data/latest.json` | 401 | application/json | locked + `authentication_required` |
| `government-revenue-data/candidates.json` | 401 | application/json | locked + `authentication_required` |
| `/api/government-revenue/latest` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/candidates?limit=5` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/workspace` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/events` | 401 | application/json | `missing bearer token` |
| `/api/health` | 200 | application/json | ok |

Anonymous static HTML remains 200. That is the compact shell, not the paid read-model.

## 5. Console / pageerror

Cursor CDP did not surface a `pageerror` list before the browser MCP disconnected. Headless Chrome logged only Chromium allocator/GCM noise, not product JS exceptions. Candidate Radar and Budget UIs remained in loading copy — classify as client waiting on a 401/missing projection, not a thrown render exception.

## 6. Screenshots (unentitled)

Under `research/defense_intelligence/evidence/`:

- `d0r-unentitled-desktop-changes.png` — populated Changes tape (2)
- `d0r-unentitled-desktop-detail.png` — HC101319C0006 inspector
- `d0r-unentitled-desktop-awards.png`
- `d0r-unentitled-desktop-candidates.png` — loading / 0 candidates
- `d0r-unentitled-desktop-opportunities.png`
- `d0r-unentitled-desktop-recompetes.png`
- `d0r-unentitled-desktop-budget.png` — budget graph verifying, 0 programs
- `d0r-unentitled-desktop-companies.png`
- `d0r-unentitled-mobile-changes.png` — 390×844; tabs wrap; Inspect on the compact row

Cursor live session additionally showed the HC101319C0006 revision diff (`federal_action_obligation → 18416666.66`, `action_date → 2026-05-12`, `action_type → C`, `description → YEAR 7 INCREMENTAL FUNDI`).

## 7. Product verdict

**Unentitled production Government Revenue is a locked compact teaser.** It is not broken as a 404. It is not the entitled desk.

- Live / usable without sign-in: page chrome, 2 compact award-change rows, 21-name coverage strip, official-source link on the selected row.
- Locked / unpaid: full 500-event workspace, candidate ledger, mapping backlog, briefcase save/export/alerts, paid JSON artifacts, `/api/government-revenue/*`.
- Missing even as a committed artifact: budget-program graph.
- Unavailable as a source in this cut: SAM opportunities (`status=unavailable`, 0 records).
- Stale vs “today”: evidence cut 2026-08-13 while capture is 2026-08-17; USAspending monthly completeness through 2026-05.

Exact next proof still required for A to pass as written: a real `site_full` session that hydrates `workspace.json` and `/api/government-revenue/candidates` with 200 JSON, then repeats the tab census.
