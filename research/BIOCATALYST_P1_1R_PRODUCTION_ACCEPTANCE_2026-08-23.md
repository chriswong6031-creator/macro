# BioCatalyst P1-1R production re-acceptance — 2026-08-23

## Verdict

**P1-1 PRODUCTION RE-ACCEPTANCE: PASS**

The Sol-approved Radar-only row-containment repair is merged, naturally
rendered, naturally deployed, served under its immutable asset stamp, and
proven against the real authenticated `site_full` production journey. The
desktop falsifier recorded by the earlier FAIL receipt now passes at
`2055x1270` and `1280x900` in both English and Chinese; the exact `390x844`
mobile gate, API/private boundary, public evidence, and real revision lineage
also remain clean.

P1-1 is therefore **`PROVEN_LIVE_COHORT_LIMITED`** and its wave status is
`done`. Broader BioCatalyst parity remains **`PARTIAL`**. This is deliberately
not a full-parity, production-scale, post-soak, or P1-2 claim.

The prior FAIL receipt at
`research/BIOCATALYST_P1_1_PRODUCTION_ACCEPTANCE_2026-08-22.md` remains valid
historical evidence and is neither rewritten nor superseded.

## Authority and scope

- Workstream: `WS:BIOCATALYST-CORE-PRODUCT`, wave P1-1 only.
- Repair PR: #6277.
- Sol-approved repair source head:
  `0e48c8830b8a26050ccfae453f2b385118b1ea59`.
- Repair merge:
  `5ec3d9d34111643813baa4a2eea0ebd5ae49f4fd`.
- Automatic render-public commit:
  `456185ab3b94143d734aa05c2a8e20a43b633db8`.
- Production proof was read-only. No manual public-render dispatch,
  `macro-update`, API restart, redeploy, source/cadence/cohort mutation,
  production fixture, or candidate/diagnostic stylesheet was used.
- This records-only closeout changes no runtime, browser, product, CI, deploy,
  source, or generated-site asset.

## Exact merge and automatic render chain

| Evidence | Exact result |
|---|---|
| final pre-merge `origin/main` | `e7ae573bfe9580526cfd94ec6d705f5bdbb60afd` |
| #6277 source head | `0e48c8830b8a26050ccfae453f2b385118b1ea59` |
| squash merge | `5ec3d9d34111643813baa4a2eea0ebd5ae49f4fd` |
| merge time | `2026-08-23T06:32:56Z` |
| immediate post-merge main | `5ec3d9d34111643813baa4a2eea0ebd5ae49f4fd` |
| automatic public-render run | `32623216451` — success |
| render job | `97154497178` — success, `06:33:02Z` to `06:36:40Z` |
| automatic render-public commit | `456185ab3b94143d734aa05c2a8e20a43b633db8` |
| render commit parent | `5216c57afa0793e2ea8a68a20f85bd6729a26049` |

The workflow was the natural `push` run bound to exact merge head `5ec3d9d…`.
It was not manually dispatched, cancelled, rerun, or otherwise manufactured.
Its normal commit changed `site/biocatalyst.html` from the prior stamp to
`biocatalyst.css?v=712a3a77`.

Fresh-main movement after the render commit did not touch any P1-1
runtime/product/browser path. Local ancestry checks against the final records
base proved both the repair merge and render commit remain ancestors of current
main.

## Natural static deployment and exact served bytes

The two-speed delivery path converged without an API-process transition:

1. the automatic renderer pushed `456185ab…`;
2. the next natural updater pulled the merge plus render commit into
   `/opt/macro` and `site.served`;
3. later normal fleet movement advanced `/opt/macro` further while preserving
   the exact accepted asset.

| Evidence | Exact result |
|---|---|
| first converged VPS checkout observed | `456185ab3b94143d734aa05c2a8e20a43b633db8` |
| final VPS checkout observed for this receipt | `fc94d43ad4142e50ec808b2f1a8d6f922ff1fa7b` |
| served page asset reference | `biocatalyst.css?v=712a3a77` |
| exact public URL | `https://www.mastermind-x.com/biocatalyst.css?v=712a3a77` |
| HTTP | `200` |
| response length | `58152` bytes |
| `Content-Type` | `text/css; charset=utf-8` |
| `Cache-Control` | `public, immutable, max-age=31536000` |
| response SHA-256 | `712a3a77307efbe9ec0b6c0cf40d4b35e4fcd8fadf9adff6384056e8f21c886f` |

The same full SHA-256 was read from
`/opt/macro/site.served/biocatalyst.css`. `/api/health.commit` is intentionally
not used as the deployment identity: this is a static CSS repair and no API
restart is required or claimed.

Standard Google Chrome's real resource inventory independently recorded the
stylesheet asset as:

`https://www.mastermind-x.com/biocatalyst.css?v=712a3a77`

with asset id `abcc90c78945e98b`, kind `stylesheet`, and both resource-link and
DOM `href` provenance. The page contained zero candidate, diagnostic, or
scratch style elements.

## Current public generation

The natural generation advanced once during the proof. The final matrix was
refreshed against the newer generation below; the source dataset and the four
rendered Radar rows remained stable. The only row-payload difference from the
immediately prior `06:00Z` generation was each row's public
`evidence.source_clocks.retrieved_at` value.

| Field | Production value |
|---|---|
| generation | `ctgov_run_20260823T070024098061Z_e679bb3d2518` |
| schema | `1.6.0` |
| published / last success | `2026-08-23T07:00:24.779012Z` |
| source dataset timestamp | `2026-08-21T09:00:05` |
| coverage class | `current_only` |
| configured / observed cohort | `4 / 4` |
| trial count | `4` |

The generation id and schema were read from the current pointer-bound public
bundle using the production checkout and production interpreter. The
authenticated browser response independently returned the same `as_of`, source
timestamp, health clock, and 4/4 coverage.

## Authentication and live HTTP contract

The existing authenticated standard-Chrome session remained inside the local
browser boundary. Only safe status, entitlement, headers, public response
fields, and aggregate evidence were returned. No token, cookie, email, name,
user id, or other credential was printed, persisted, screenshotted, or
committed.

| Probe | Result |
|---|---|
| authenticated `/api/me` | HTTP **200**; `status=active`; `plan=unlimited`; `features` includes `site_full` |
| entitled default Radar | HTTP **200**; `private, no-store`; `Vary: Authorization, Accept-Encoding` |
| entitled invalid horizon | HTTP **400**; `detail=invalid horizon`; `private, no-store`; `Vary: Authorization` |
| unsigned default Radar | HTTP **401**; `detail=missing bearer token`; `private, no-store`; `Vary: Authorization` |

The exact default request was
`limit=50&horizon=next_365d&milestone_kind=all`. Its final current-generation
response carried:

- 4 returned rows and no next cursor;
- 3 `upcoming`, 1 `occurred`, and 0 `current` events rendered;
- 4 events beyond horizon and 8 total source milestone events;
- exact arithmetic: `3 + 1 + 0 + 4 = 8`;
- 4 trials in cohort and 4 trials with events;
- 0 absent dates, 0 unusable dates, and 0 trials missing identity;
- NCTs `NCT06602479` and `NCT05020236`;
- revision states: 2 `has_revisions`, 2 `history_not_collected`;
- 6 total public revision-lineage entries.

The captured production response-status window contained only expected
`200`, `204`, `400`, and signed-out `401` results for the probes above. It
contained zero `5xx` responses and zero `524` responses.

## Live safety walk

The final current-generation Radar JSON was recursively inspected. Results:

| Boundary | Violations |
|---|---:|
| score/probability/materiality/rank/credential/token/private keys | 0 |
| source-path/R2/bucket/receipt keys | 0 |
| bare 32-64 character hash values | 0 |

The top-level contract remained only `as_of`, `authority`, `catalyst_radar`,
`coverage`, `effective_horizon`, `health`, `pagination`, `query`,
`schema_version`, and `source`. Authority remained
`classification=source_fact`, `decision_authority=false`, allowed uses
`display/context/explain`, and the frozen prohibitions on originating a signal,
ranking or selecting a security, sizing a position, gating a decision,
executing a trade, and raising authority.

## Real Chrome geometry — deployed bytes only

All measurements below came from the real populated production page in
standard Google Chrome after the final generation refresh. The exact deployed
stylesheet URL was present at every cut. The page had four real Radar cards,
zero diagnostic style overrides, zero row scroll overflow, zero tracked
descendant escapes, zero adjacent-row overlaps, zero document/body horizontal
overflow, and zero mobile chip overflow in all six cuts.

| View | Language | Row/descendant/adjacent failures | Page/chip horizontal failures | Queue behavior |
|---|---|---:|---:|---|
| `2055x1270` | EN | `0 / 0 / 0` | `0 / 0` | `clientHeight=219`, `scrollHeight=635`, `overflow-y:auto` |
| `2055x1270` | ZH | `0 / 0 / 0` | `0 / 0` | `clientHeight=240`, `scrollHeight=606`, `overflow-y:auto` |
| `1280x900` | EN | `0 / 0 / 0` | `0 / 0` | `clientHeight=116`, `scrollHeight=723`, `overflow-y:auto` |
| `1280x900` | ZH | `0 / 0 / 0` | `0 / 0` | `clientHeight=179`, `scrollHeight=606`, `overflow-y:auto` |
| `390x844` | EN | `0 / 0 / 0` | `0 / 0` | `clientHeight=scrollHeight=1017`, `overflow-y:visible` |
| `390x844` | ZH | `0 / 0 / 0` | `0 / 0` | `clientHeight=scrollHeight=958`, `overflow-y:visible` |

For every card, `scrollHeight <= clientHeight` and
`scrollWidth <= clientWidth`. Every visible descendant rectangle was contained
within its owning card, with the measured tolerance limited to subpixel
rounding. The minimum adjacent-row gap was 7 CSS pixels. Desktop queue scrolling
therefore remains present and expected; mobile retains the designed
height-auto/visible behavior.

## Real revision-rich evidence journey

The live `NCT06602479` primary-completion row remained revision-rich and was
opened from the populated Radar. The inspector rendered the current official
record and two public links to:

`https://clinicaltrials.gov/study/NCT06602479`

The complete milestone-date lineage rendered newest-first in both EN and ZH:

1. `2025-09-15 -> 2026-12-18`, record version `9 -> 10`, observed
   `2026-08-23T02:24:54.105388Z`;
2. `2026-09-07 -> 2025-09-15`, record version `6 -> 7`, observed
   `2026-08-23T02:24:53.380473Z`;
3. `2026-09-02 -> 2026-09-07`, record version `1 -> 2`, observed
   `2026-08-23T02:24:52.107984Z`.

The final `07:00Z` generation's exact revision arrays, titles, milestone dates,
status, and public source links were identical to the preceding natural
generation; only the public retrieval clock advanced. Chinese lineage was
reopened after that final refresh. The already-open English inspector and the
final English row/asset pass therefore bridge exactly across unchanged lineage
data and unchanged runtime/browser assets, rather than relying on a fixture or
invented row.

The page-origin console/page-error walk was empty. The only warning records were
two unrelated `chrome-extension://` LavaMoat runtime notices; neither originated
from `mastermind-x.com` and neither is a product warning or error.

## State and non-claims

- P1-1 wave status: `done`.
- P1-1 acceptance: `PROVEN_LIVE_COHORT_LIMITED`.
- Broader BioCatalyst parity: `PARTIAL`.
- The claim is bounded to the current four-NCT production cohort and this P1-1
  Trial Milestones slice.
- The earlier production FAIL remains a preserved historical receipt.
- No deployment, restart, updater invocation, production fixture, runtime
  mutation, source/cadence/cohort change, scoring/ranking/gating, or authority
  increase occurred in this closeout.
- No production-scale, full-parity, post-soak, or closed-beta claim is made.
- No P1-2 work began and no P1-2 authority is inferred.

P1-1 is closed at PROVEN_LIVE_COHORT_LIMITED. Broader parity remains PARTIAL.
No P1-2 or source/cohort expansion is commissioned by this closeout. Any later
BioCatalyst product wave requires a separate explicit Sol commission and must
respect the still-binding source/soak gates.
