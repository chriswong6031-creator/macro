# D1 — Production truth and signed-in product rescue

**Wave:** D1  
**Status:** written, **not authorized** until Sol accepts D0R and the operator orders D1.  
**Repos:** macro only for this slice. Terminal consumes the same URLs; do not restyle Terminal chrome.  
**PR ancestry:** D0R checkpoint [#5814](https://github.com/mastermindx-market-intelligence/macro/pull/5814). Qledger isolation remains [#5816](https://github.com/mastermindx-market-intelligence/macro/pull/5816). Do not fold [#5424](https://github.com/mastermindx-market-intelligence/macro/pull/5424).

## Observable mission

An entitled `site_full` user opens `government_revenue.html`, sees the 500-event Change Tape without a stale compact-loading banner, sees Candidate Radar **22** (or a typed hydrate failure — never a membership CTA), sees filmstrip copy that is not “Members only”, sees agency facets as names, and sees Budget/SAM as `PROJECTION_MISSING` / `SOURCE_UNAVAILABLE`. The same deployed bytes expose cookie JSON, bearer API, graph id `defense19-v1` (or whatever reviewed graph is on **main when D1 starts**), and browser health.

## Why it matters

Entitled production already has the evidence (cookie workspace 500, bearer candidates 22, mapping-backlog 21). The page lies: Radar overlay “part of a membership”, filmstrip “Members only”, agency Python-dict leaks, compact-loading banner after 500 hydrate, Budget/SAM zeros that read like empty-valid. D1 is product rescue of an existing desk, not a new application.

## Authority precedence

Display / `context_only` only. `can_rank/gate/size/entry/execute` stay **false**. No Prophet family, no Neural Web originated signal, no new collector, no P-1/R-1 graph bake, no SAM collector, no `#5424` merge, no second identity plane.

## Verified current state (do not rediscover)

| Fact | Evidence |
|---|---|
| Live page is `government_revenue.html` (underscore). Hyphenated twin 404s | entitled census 2026-08-17 |
| Cookie JSON 200 vs cookie-only API 401 vs bearer API 200 | `DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES` |
| Radar JS never reads `government-revenue-data/candidates.json` | `templates/government-revenue-candidate-radar.js` `load()` only `fetchPages('/api/government-revenue/candidates…')` |
| `withAuth` no-ops if `MDXAuth` missing; 401 → `locked` | same file lines 14–21, 77–78, 106–118 |
| Filmstrip “Members only” is `tickerRailCopy('locked')` when `candidateStatus==='locked'` | `templates/government_revenue.html.j2` |
| Budget JS catch-all → `unavailable` | `templates/government-revenue-dossiers.js` `createGovernmentRevenueBudget.load` |
| Workspace hydrate is cookie `government-revenue-data/workspace.json` | `hydrateWorkspace` in the j2 |
| Graph live = defense19-v1 | HEAD + A packets |

## Exact scope / files

Touch only:

- `templates/government-revenue-candidate-radar.js`
- `templates/government_revenue.html.j2` (and paired `site/government_revenue.html` if that pair is in `check_template_site_sync`)
- `templates/government-revenue-dossiers.js` (Budget typed failure copy only)
- `templates/government-revenue-candidate-radar.js` consumers / `tests/test_government_revenue_ui.py` / `tests/test_government_revenue_api_auth.py`
- existing `site/` copies of the JS if the sync script requires them

Do not touch `engine/government_revenue/` collectors, `data/`, Prophet, Neural Web, recipient graph, `#5424`, qledger.

## Explicit non-goals

- No SAM/P-1/R-1/FMS/GAO collector.
- No raising the 500 workspace cap.
- No frontend `action_date << known_at` heuristic; use `is_late_discovery`.
- No materiality ratio from `$18.4M / anything`.
- No membership unlock redesign; entitled users are already `site_full`.
- No third global header; no new tokens; no scores.

## User journey

1. Sign in through the normal UI (no token in chat).
2. Open `/government_revenue.html`.
3. Changes tab shows 500; banner that claimed “compact evidence cut while complete workspace loads” is **gone** after a successful cookie hydrate.
4. Candidate Radar shows 22 rows (IRDM `grc1-025ab7cfdb7f9735f0e1e575` present) **or** “Candidate ledger unavailable” with retry — never “View membership plans”.
5. Filmstrip for IRDM says evidence-linked / issuer path — not Members only.
6. Agency filter options are human names or “Unspecified agency”, never `{name: None, ...}` / `[object Object]`.
7. Budget tab: typed `PROJECTION_MISSING` (request graph not baked). Opportunities: typed `SOURCE_UNAVAILABLE`.
8. Open P00032 inspector: official URL, both clocks, Watch stance.

## Data / contract / time / null / correction / rights

- Contracts stay `government_procurement_workspace.v2` and `government_revenue_candidate_queue.v1`.
- Cookie and bearer are one user session: after `MDXAuth` session becomes ready, Radar **must** `load()` again (the script already notes theme.js loads later).
- Optional parallel: cookie `government-revenue-data/candidates.json` is already 200 for entitled users — may be used as a hydrate path **if** the envelope still passes `queueRows` validation. Do not weaken the receipt contract.
- Nulls print. 401 after a proven `site_full` is `unavailable`/`retry`, not `locked`/`plans.html`.
- Rights: display-only flags on every payload remain.

## Deterministic vs inferred

Hydrate success/failure is deterministic HTTP + contract checks. Do not infer “user is anonymous” from a race where MDXAuth was not ready.

## Failure states

| State | When | UI |
|---|---|---|
| CURRENT | cookie workspace 200 matching bundle | 500 rows, banner off |
| SIGN_IN_REQUIRED | anonymous compact teaser | keep 2-row teaser + plans |
| unavailable | entitled bearer 401/5xx after session ready | Radar unavailable + retry, not membership |
| PROJECTION_MISSING | budget graph absent | Budget tab copy from target composition |
| SOURCE_UNAVAILABLE | opportunities freshness unavailable | Opportunities/Recompete |
| locked | **only** unentitled 401 on cookie JSON | membership CTA allowed |

## Ordered implementation steps

1. Reproduce Radar lock locally: load page, call `candidateUI.load()` before MDXAuth ready, then after `getSession`.
2. Subscribe to auth-ready (existing MDXAuth/theme hook) and re-`load()` Radar + Budget.
3. Map entitled 401-before-session to `loading`, not `locked`. Map entitled 401-after-session to `unavailable`.
4. Filmstrip: `tickerRailState` must not return `locked` when `/api/me` is `site_full` / cookie workspace already 500.
5. Agency: coerce `r.agency` to a string name before `populateFilters` (`agency.name` if object; drop Python-repr strings).
6. `workspaceBanner`: if `WORKSPACE_EVENTS.length` already equals `total` (500), do not show loading/compact copy.
7. Budget/SAM copy: use the typed labels in `evidence/compositions/d1-budget-sam-failure.html`.
8. Tests in `tests/test_government_revenue_ui.py`: entitled hydrate after late MDXAuth; no membership overlay; agency options are strings; banner off at 500.

## Tests and production proof

- Unit/UI tests above, plus existing `test_government_revenue_api_auth.py` still 401 without bearer.
- Production: normal UI sign-in; screenshot Radar 22; Changes 500; Budget typed missing; no Members only on IRDM filmstrip. Same health endpoint discipline as D0R.
- Reference look: `research/defense_intelligence/evidence/compositions/d1-*.html`.

## Rollback

Revert the template/JS PR. Compact teaser and APIs unchanged. No data migration.

## Stop condition

Stop when the entitled journey above is live and screenshotted. Do not start Atlas, P-1 collection, or SAM collection. Return for review, then D2.

## Continuation handoff

Write `agentos/handoffs/DEFENSE-PROCUREMENT-V3-<date>.md` with the live URLs, content ids, and any remaining typed failures. D2 consumes the reviewed graph on **main at D2 start**, not a defense21 built around #5424.
