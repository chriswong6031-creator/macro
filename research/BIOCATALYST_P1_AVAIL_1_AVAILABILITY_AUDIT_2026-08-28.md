# BioCatalyst P1-AVAIL-1 availability audit — 2026-08-28

Operation `BIOCATALYST-P1-AVAIL-1-20260827` / MAS-172. Dispatch: Slack
`C0BSBM78V1N` thread `1787879112.101029` (Fable COO dispatch, Sol CONTINUE at
`1787893968.621389`). Chairman report: "the interface is currently down."

## Verdict

**NO ORIGIN-SIDE DEFECT EXISTS.** Every plane of the P1-1 Trial Milestones
delivery chain that is measurable from outside the Chairman's own browser —
edge, static page, immutable assets, updater/`site.served` convergence,
regwall, API route, auth upstream, pointer-bound generation, projection
payload, and the unauthenticated browser runtime — was probed read-only on
2026-08-28 04:50–05:45Z and found healthy, byte-identical to `origin/main`,
and contract-conformant. **No repair was performed because no repairable
defect was found; nothing was mutated in production.**

Two real findings frame the Chairman's report:

1. **The only genuine authenticated-path incident in the 7-day window:**
   `/api/me` returned **502** with log line `auth check upstream failure
   (outage)` six times during **2026-08-27 22:56:17Z–22:59:08Z** (and 4
   requests during a similar blip 2026-08-24 03:38:57–03:39:30Z). This is the
   typed fail-closed answer when the Supabase `/auth/v1/user` upstream check
   fails. It self-healed in under 3 minutes; the Supabase auth plane answered
   `200` on `/auth/v1/health` with the deployed publishable key at probe time.
   A signed-in user during that window would have seen entitled surfaces
   deny — plausibly the Chairman's observation (~2h before the 01:05Z
   dispatch).
2. **The Chairman's failing attempts never reached the origin.** The complete
   `macro-api` journal (floor Jul 09; continuous) records **zero** BioCatalyst
   API requests from any real user between 2026-08-23 07:13Z (the P1-1R
   acceptance session's own traffic) and this audit's probes. The deployed
   page fires its Radar fetch unconditionally on every load
   (`templates/biocatalyst.js` `init()` → `loadMilestones` → `fetchJson`),
   signed-in or not — this audit's own unauthenticated Chromium load logged
   its 401 at origin. Therefore any page load that renders reaches the
   journal. A failure that leaves no origin trace is in front of the origin:
   the Chairman's client/network/edge path (e.g., in-China reachability of
   the EdgeOne POPs, DNS, device), or the page never being loaded at all.
   This vantage cannot be exercised from the fleet host.

## Exact evidence — audited state

Reference pins at pickup: dispatch Macro main `d84468e41f40…`; observed
`origin/main` `7c80d25eac3e9fb43ebe1ea1599b74486ac28b40` (moved by nightly
data commits only). VPS checkout `/opt/macro` = `eca7c761efd05b…`; running
API commit `033f929087a0…` (#6572 line, natural updater restart 02:36:14Z),
8 data-only commits behind checkout — normal restart-regex behavior.

### Edge + static + assets (2026-08-28 ~05:05–05:15Z, both EdgeOne A records)

| Probe | Result |
|---|---|
| `GET /biocatalyst.html` | 200, 70171 B, `cache-control: public, must-revalidate, max-age=60` (public shell by design — Caddyfile `@reg_html` exclusion) |
| All 10 referenced `.js`/`.css` assets | 200 each |
| `biocatalyst.css?v=712a3a77` | SHA-256 `712a3a77307efbe9…` == `origin/main:site/biocatalyst.css` |
| `biocatalyst.js?v=c35dac39` | SHA-256 `c35dac39a3718d8d…` == `origin/main:site/biocatalyst.js` |
| `theme.js?v=0956049c` / `live.js?v=cfb8c072` | SHA-256 match `origin/main` byte-exact |
| Asset stamps in served HTML | identical to `origin/main:site/biocatalyst.html` |
| Both EdgeOne A records (43.159.98.106 / 43.159.99.101) | page 200 + radar 401 identically |
| DNS via 223.5.5.5 / 114.114.114.114 / 8.8.8.8 | consistent CNAME `…eo.dnse3.com` |

The served CSS stamp is the exact P1-1R-accepted asset
(`research/BIOCATALYST_P1_1R_PRODUCTION_ACCEPTANCE_2026-08-23.md`).

### API contracts (public vantage)

| Probe | Result |
|---|---|
| unsigned `GET /api/biocatalyst/v1/catalyst-radar?limit=50&horizon=next_365d&milestone_kind=all` | **401** `{"detail":"missing bearer token"}`, `private, no-store`, `Vary: Authorization` |
| `Authorization: Bearer <garbage>` same query | **401** `{"detail":"invalid token"}` — reaches origin (`eo-cache-status: MISS`) |
| unsigned `GET /api/me` (origin-local) | **401** — route live post-restart |
| `GET /api/health` | 200 `{"status":"ok","commit":"033f929087a","checkout":"eca7c761efd"}` |
| Supabase `GET /auth/v1/health` with deployed publishable key | 200 |

Auth precedes query validation, so the typed-400 contract is not reachable
unsigned; it is proven in-process below.

### Data plane (VPS, read-only)

| Field | Value |
|---|---|
| pointer generation | `ctgov_run_20260828T050054568203Z_e679bb3d2518` |
| published / last success | `2026-08-28T05:00:55.701117Z` |
| health state / budget | `fresh` / 7200 s |
| cohort configured / observed | 4 / 4 |
| source dataset timestamp | `2026-08-27T09:00:05` |
| generation cadence Aug 27 00:00Z → Aug 28 05:00Z | one generation every hour, **zero gaps** |
| `last_error_code` | null |

### Production handler execution (production checkout + interpreter, auth hop injected, read-only)

`app.biocatalyst.catalyst_radar()` executed in-process under
`/opt/macro-api/.venv/bin/python` as `macro-biocatalyst` against the live
pointer-bound bundle:

- HTTP 200 shape; `as_of=2026-08-28T05:00:55.701117Z`, schema
  `biocatalyst_api.v1`, health `fresh`.
- 4 returned rows, no next cursor; NCTs `NCT06602479`, `NCT05020236`.
- Radar coverage: 4 trials in cohort, 4 with events, **3 upcoming + 1
  occurred + 0 current + 4 beyond horizon = 8 events total** — the exact
  P1-1R arithmetic; 0 unusable dates, 0 absent dates, 0 missing identity.
- Revision lineage: `has_revisions` ×2 (NCT06602479 primary_completion +
  completion, 3 lineage entries each = 6 public entries),
  `history_not_collected` ×2 (NCT05020236) — matches P1-1R.
- Authority block intact (`source_fact`, `decision_authority=false`, frozen
  forbidden uses). Recursive forbidden-key walk (score/probability/
  materiality/rank/token/secret/credential/r2/bucket/receipt): **0 hits**.
- `catalyst_radar(horizon="bogus")` → **HTTPException 400 `invalid
  horizon`** with `private, no-store` + `Vary: Authorization` — the typed
  400 contract holds.

### Browser runtime (real Chromium, unauthenticated — the shell every user executes)

- Page renders the designed locked state; the Radar fetch fires and reaches
  origin; the only console error is the expected 401.
- Zero document/body horizontal overflow at 2055×1270, 1280×900, 390×844 in
  EN and ZH (ZH via the page's own `data-lang`/`langchange` mechanism);
  mobile ZH shell renders correctly.
- Populated-state geometry (cards, queue scroll) requires the entitled
  session — see boundary below.

### 5xx census (7-day journal)

- The `/api/me` 502 windows above — **the only 5xx on any auth/BioCatalyst
  path**. Zero 5xx and zero 524 on any `/api/biocatalyst/*` route.
- Out-of-scope observation, flagged for Sol, untouched per dispatch: the
  stock-dossier plane (`/api/dossier-quote/NVDA`, shipped in #6572) has
  answered **503** to an external 60 s poller continuously since
  2026-08-28 04:09:31Z (80+ hits at audit time; two 200s right after the
  02:36Z restart, 404 before it). Different surface, different owner; not a
  BioCatalyst dependency (`biocatalyst.js` never calls it).

## Boundary (named, fail-closed)

Step (9) **real entitled production acceptance** cannot be produced by this
session at audit time: the operator's authenticated Chrome (claude-in-chrome)
is disconnected from this session, and credential-based sign-in by an agent
is prohibited. The entitled journey (real `/api/me` 200 + entitled Radar 200
+ populated-page geometry + evidence drill-down) therefore remains the
untested hop, exactly as it was the untested hop for the Chairman's report.
This audit does **not** claim `PROVEN_LIVE`; it claims **no origin-side
defect and full contract health at every hop short of the entitled browser**.

## What this means for the report

If the Chairman's failure is real and current, it lives on the Chairman-side
access path (client, network, in-China edge reachability) or occurred during
the 22:56–22:59Z auth-upstream window and has since self-healed. The
deterministic next probes need the failing vantage: exact URL used, what
rendered (redirect to signin / locked panel / spinner / error page), a
timestamp, and whether other authenticated pages worked — or one
claude-in-chrome-connected session to run the standing entitled acceptance.

## Non-claims and non-actions

- No production mutation, restart, redeploy, cache purge, updater dispatch,
  source/cadence/cohort change, or fixture. Probes were read-only.
- PR #6389 untouched, unrebased, unmerged, hold preserved.
- No P1-2, no soak/successor adjudication, no authority change.
- P1-1's `PROVEN_LIVE_COHORT_LIMITED` standing claim is neither re-proven
  nor withdrawn by this audit; the 2026-08-23 receipt stands as history.
