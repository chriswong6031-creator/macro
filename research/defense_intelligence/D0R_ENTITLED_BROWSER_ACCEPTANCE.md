# D0R Workstream A — Production browser acceptance

**Entitled capture window:** 2026-08-17T04:39Z–04:46Z (UTC)  
**Unentitled capture (unchanged):** 2026-08-17T01:51Z–02:01Z  
**Route:** https://www.mastermind-x.com/government_revenue.html  
**Entitled session class:** signed-in through the normal onboarding sheet in an isolated Chrome for Testing window. `/api/me` returned HTTP 200 with `status=active`, `tier=unlimited`, `source=comp`, `role=authenticated`. Paid `/api/government-revenue/*` routes (router-wide `enforce_site_full(..., always=True)`) returned 200, so this is a `site_full` account. No email, name, user id, cookie, or bearer token is recorded here or in git.

The unentitled compact teaser remains true for anonymous visitors. This packet now also records the entitled desk.

## 1. Runtime identity (re-recorded at entitled capture)

| Field | Value | How recorded |
|---|---|---|
| Production `/api/health` | `{"status":"ok","commit":"a0b2aba13b5","checkout":"8b5cd60f706"}` | anonymous curl 2026-08-17T04:45Z |
| `origin/main` at entitled capture | `8b5cd60f706e` | `git rev-parse origin/main` |
| Checkout vs GitHub | VPS checkout matches current `origin/main` prefix `8b5cd60f706` | health JSON |
| Runner `commit` field | still `a0b2aba13b5` (not the checkout) | unexplained; inherited |
| Evidence clocks | `as_of=2026-08-13`; `generated_at=2026-08-13T09:24:42Z`; `published_at` absent | entitled `workspace.json` and `latest.json` |
| Workspace bundle | `government_procurement_workspace.v2` / `grw2-dd9d7af893a7f3c773909351` | same bundle as the compact teaser |
| Recipient graph | still `defense19-v1` on this cut | not re-litigated |
| Page URL after sign-in | `government_revenue.html?signin=1` (sheet closed; param uncleared) | CDP |

The HTML shell can move with main while the published GovRev cut stays 2026-08-13.

## 2. Authenticated flow — what was actually proven

| Required step | Result | State |
|---|---|---|
| Session restoration | Fresh Chrome for Testing profile; operator completed the normal sign-in sheet (passkey/password in the window). `MDXAuth.hasSession=true`. | `CURRENT` for session |
| Entitlement recognized | Cookie `GET government-revenue-data/workspace.json` flipped 401 → **200** at 04:41:14Z; 500 events; `locked=false`; `next_cursor` absent. `/api/me` with page bearer → 200 `tier=unlimited` `source=comp`. | `CURRENT` for access |
| Protected requests authenticated | Cookie-only fetches to `/api/government-revenue/*` and `/api/me` stay **401** `missing bearer token`. The same URLs with `Authorization: Bearer` from `MDXAuth.client().auth.getSession()` return **200 JSON**. Two auth planes. | `CURRENT` (split) |
| Expected APIs return correct type | 200 `application/json` for latest, candidates queue, workspace, events, mapping-backlog. | `CURRENT` |
| Real records render | Changes / Award tape list **500** governed rows. Third visible row is `Reported obligated balance changed — HC101319C0006` / IRDM — the sibling that compact omitted. | `CURRENT` for Change Tape |
| Tabs switch | Yes. Radar/Budget still empty/locked for other reasons. | `PARTIAL` product |
| Record detail opens | HC101319C0006 inspector: receipts, official source, Watch — do not chase. | `CURRENT` |
| Back/refresh | not re-run after hydrate | `UNKNOWN` |
| Unexpected runtime errors | Agency filter/cards dump Python dict reprs. Radar stays on a membership lock despite 200 API. Filmstrip still says “Members only”. | `PARTIAL` / `BROKEN` UX |

**Verdict for Workstream A:** an entitled `site_full` user **can** open the live page and use the 500-event Change/Award tape plus the same 21-name company strip. Paid static JSON and bearer APIs are **200**. Candidate Radar, Budget & programs, Opportunities, and Recompete are **not** a complete entitled desk. Do not treat “signed in” as “every tab live.”

## 3. Two auth planes (load-bearing)

| Plane | What hydrates | Entitled result | Cookie-only |
|---|---|---|---|
| Caddy/paywall cookie JSON | `/government-revenue-data/{workspace,latest,candidates}.json` | 200; workspace 2.9 MiB / 500 events; latest 3.5 MiB; candidates.json 22 rows | 401 locked |
| FastAPI bearer | `/api/government-revenue/*`, `/api/me` | 200 when `MDXAuth.client()` session token is attached | 401 missing bearer token |

Candidate Radar JS (`templates/government-revenue-candidate-radar.js`) **only** reads the bearer queue (`government_revenue_candidate_queue.v1`, `items` + mapping-backlog). It does not read cookie `candidates.json`. Changes/Award tape hydrate from cookie/workspace (or compact embed) and therefore show 500 once the cookie plane unlocks.

## 4. Entitled tab census

Headline (same clocks as unentitled): Watch with qualified coverage / Partial or stale coverage; Governed changes **500**; Active opportunities **0**; Closing in 30 days **0**; Mapped exposure **$206.7B**. Evidence cut 2026-08-13. Loading banner still visible after hydrate: “Showing the compact evidence cut while the complete workspace loads.”

| Tab | Visible count | API/source state | Freshness | Valid-empty vs unavailable | Graph/mapping | User-visible failure | Representative row |
|---|---:|---|---|---|---|---|---|
| Candidate Radar | **0** + **locked overlay** | Bearer `/api/government-revenue/candidates?limit=5` **200**, `total=22`, `content_id=grcq1-d93ebaf6878402e3be09e490`; mapping-backlog **200**, `total=21`, same `content_id`. Cookie `candidates.json` also 200 / 22. | `exact_candidate_availability=available` | **not** EMPTY_VALID | exact issuer path | Overlay: “Candidate Radar is locked. The exact-linked candidate ledger is part of a membership.” CTA “View membership plans.” Filmstrip “Members only.” Classify as **hydrate-once / lock not cleared after 200**, not missing data. | none in UI; 22 on API |
| Changes | **500** | Cookie workspace.json 200, 500 `award_change` events; bearer `/api/government-revenue/workspace` 200, `total=500`, first page 50 events | `freshness.status=partial` (award_events ok, mappings partial, opportunities unavailable) | populated | reviewed issuer links on visible IRDM/HII rows | stale/partial chip; agency dict leak on cards | `New obligation observed — HC101319C0006` / IRDM; sibling `Reported obligated balance changed` on same PIID |
| Award Tape | **500** | same workspace events | same | same | same | same | same tape, award-oriented copy |
| Opportunities | **0** | `opportunity_intelligence` empty; freshness `opportunities=unavailable` | unavailable | **SOURCE_UNAVAILABLE** | none | 0 active opportunities | none |
| Recompete Watch | **0** | no recompete events in this 500-cut | award-detail freshness reused | **omission / not derived in this cut**, not proof the rail is empty | award end dates | empty queue | none |
| Budget & Programs | **0** | no P-1/R-1 graph; entitled UI “Budget request rail unavailable” / “No P-1/R-1 request graph is active” | **PROJECTION_MISSING** | not empty-valid | program keys | 0 programs | none |
| Companies | **21** | compact/latest companies | coverage 21 | populated | filmstrip link-state still “Members only” after sign-in | chips do not show linked/pending | LMT · RTX · NOC · GD · LHX · HII · BA · TDG · HWM |

`/api/government-revenue/events?limit=5` returned `total=31` (filtered events endpoint) against workspace `total=500`. Do not treat 31 as the Change Tape size.

## 5. Network / status / content-type matrix (entitled)

Same-origin from `https://www.mastermind-x.com/government_revenue.html` at 2026-08-17T04:41–04:45Z. No cookies or Authorization values stored.

### Cookie / `credentials: same-origin` only

| URL | HTTP | Content-Type | Body class |
|---|---:|---|---|
| `government-revenue-data/workspace.json` | **200** | application/json | `government_procurement_workspace.v2`; 500 events; P00032 present; kinds=`award_change` |
| `government-revenue-data/latest.json` | **200** | application/json | `company_government_revenue.v1` |
| `government-revenue-data/candidates.json` | **200** | application/json | schema `1.0.0`; 22 candidates |
| `/api/government-revenue/latest` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/candidates?limit=5` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/workspace` | 401 | application/json | `missing bearer token` |
| `/api/government-revenue/events?limit=5` | 401 | application/json | `missing bearer token` |
| `/api/me` | 401 | application/json | `missing bearer token` |
| `/api/health` | 200 | application/json | ok |

### Bearer from in-page `MDXAuth.client().auth.getSession()` (token not recorded; `hasAccessToken=true`, 1259 chars)

| URL | HTTP | Content-Type | Body class |
|---|---:|---|---|
| `/api/me` | **200** | application/json | `tier=unlimited`, `status=active`, `source=comp` (PII omitted) |
| `/api/government-revenue/latest` | **200** | application/json | `company_government_revenue.v1`; `as_of=2026-08-13`; 596798 bytes on this GET |
| `/api/government-revenue/candidates?limit=5` | **200** | application/json | `government_revenue_candidate_queue.v1`; `total=22`; `items=5`; `content_id=grcq1-d93ebaf6878402e3be09e490` |
| `/api/government-revenue/workspace` | **200** | application/json | workspace v2; `total=500`; page `events=50` |
| `/api/government-revenue/events?limit=5` | **200** | application/json | `total=31`; `events=5` |
| `/api/government-revenue/mapping-backlog?limit=5` | **200** | application/json | `total=21`; same candidate `content_id` |

Machine copy: `research/defense_intelligence/evidence/d0r-entitled-api-census.json` (sanitized).

## 6. Screenshots (entitled)

Under `research/defense_intelligence/evidence/`:

- `d0r-entitled-signin-sheet.png` — normal UI sheet before session
- `d0r-entitled-desktop-changes.png` / `d0r-entitled-desktop-changes-tab.png` — 500-row Change Tape; P00032 + balance-changed sibling
- `d0r-entitled-desktop-awards.png`
- `d0r-entitled-desktop-candidates.png` — **locked overlay** despite API 200/22
- `d0r-entitled-desktop-opportunities.png`
- `d0r-entitled-desktop-recompetes.png`
- `d0r-entitled-desktop-budget.png` — Budget request rail unavailable
- `d0r-entitled-desktop-companies.png`
- `d0r-entitled-mobile-390.png`
- `d0r-entitled-tablet-820.png`

Unentitled PNGs are retained separately (`d0r-unentitled-*.png`). Do not overwrite them.

## 7. Product verdict

**Entitled production Government Revenue is a 500-event award-change tape on an Aug 13 cut, plus locked/missing rails that sign-in does not repair.**

- Live / usable when signed in: Change Tape 500, Award tape 500, HC101319C0006 inspector, official source, 21-name coverage strip (still labeled Members only).
- API-live but UI-locked: Candidate Radar (22 on queue + 21 mapping-backlog, overlay still membership).
- Missing artifact: budget-program graph (`PROJECTION_MISSING`).
- Source unavailable: SAM opportunities.
- Stale vs capture day: evidence 2026-08-13; capture 2026-08-17; health checkout `8b5cd60f706`.
- UX defects visible only (or still) when entitled: Python dict agency facets on cards; loading banner after 500 hydrate; filmstrip “Members only”; Radar lock not cleared after bearer 200.

Exact D1 rescue (not started here): rehydrate Candidate Radar and filmstrip after session; stop dumping dict facets; drop the compact-loading banner once workspace 200 lands; budget graph or honest missing state without a verifying spinner.

## 8. Unentitled baseline (still true)

Anonymous visitors still get the 2-of-500 compact teaser, membership banner, and 401 on both JSON planes. See the 2026-08-17T01:51Z matrix in git history of this file and `d0r-unentitled-*.png`. Compact `#gov-data` is not the entitled tape.
