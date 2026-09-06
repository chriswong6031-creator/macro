# Market Ontology F04 Explorer — Architecture Amendment 2: Access and Transport

**Date:** 2026-09-04  
**Status:** `BINDING_ARCHITECTURE_AMENDMENT / RECORDS_ONLY / NO PRODUCT EFFECT`  
**Operation:** `marketontology-f04-explorer-architecture-20260904-sol-001`  
**Carrier:** Macro PR #6820 / `sol/market-ontology-f04-explorer-architecture-20260904`  
**Parent preserved:** `marketontology-f04-ontology-transmission-20260826-fable-001`  
**Protected procedure at adjudication:** `Mastermind@22b36b830bd5560942186ada7597508f918696af` / `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1  
**Predecessor architecture head:** `93fa67df98ee39f046f47bb2d02e8b3159cd9593`  
**Capability delta:** `NONE — this amendment prevents a new paid-payload mirror leak`

> **AMENDED (2026-09-04).** Amendment 3,
> `MARKET_ONTOLOGY_F04_EXPLORER_ARCHITECTURE_AMENDMENT_3_REVIEW_CLOSURE_2026-09-04.md`,
> controls the F00 consumption edge, authenticated shared navigation, request-time
> source-manifest/deployed-checkout freshness, K1 evidence forms, denominator honesty,
> theme art directions, protected dependency paths, and the eight-record PR #6820 census.
> Amendment 2 remains controlling for access and transport.

This amendment closes an access-architecture defect discovered after Amendment 1: the planned gated static file `/premiumdata/ontology_explorer.json` would be committed into the public Macro repository. Caddy could correctly deny the primary-domain route while raw GitHub, anonymous clone and the GitHub Pages mirror still exposed the same bytes. A primary-origin `401/403` would therefore be false proof of commercial access integrity.

The X1 product shell remains public and discoverable. The current proprietary explorer snapshot moves to the existing authenticated Macro API pattern and is never committed to a public Git/R2/static path.

---

## 1. Canonical finding

Current source law and repository evidence establish all of the following:

1. `mastermindx-market-intelligence/macro` is public.
2. Existing files under `site/premiumdata/` are tracked and have anonymous raw GitHub download URLs.
3. `research/PAYWALL_GIT_MIRROR_EXPOSURE_ADJUDICATION.md` records that “committed to git” is equivalent to anonymously readable and recommends keeping full ranked/graded payloads out of public Git.
4. `research/PRODUCT_ACCESS_ENTITLEMENT_TRUTH_CENSUS_2026-08.md` states that a green primary-domain probe is not an access attestation because GitHub Pages, public R2 and raw Git can bypass the served gate.
5. Current Agent OS records still say the full book plus `premiumdata` are anonymously served by raw Git/clone/Pages, so a complete paid-boundary pass is not issuable estate-wide.
6. The repository already has a canonical authenticated read-only product pattern: `require_user` followed by `enforce_site_full(..., always=True)`, private/no-store/noindex response headers, and a pure projection/router boundary in modules such as `app/prophet_lab.py` and `app/capital_structure.py`.

Therefore a new F04 current snapshot under `site/premiumdata/` would knowingly widen a documented access defect. It is prohibited.

---

## 2. Supersession map

This amendment supersedes every architecture, decision, handoff, plan or PR clause that says or implies:

- X1 publishes `/premiumdata/ontology_explorer.json`;
- `site_full` enforcement on a static path is sufficient proof that the snapshot is paid/private;
- the current full-fidelity explorer response may be committed anywhere under `site/**`, another public Git path, the GitHub Pages artifact, or a publicly bound R2 key;
- anonymous/Free denial on `mastermind-x.com` alone proves access integrity;
- committed browser evidence may contain the full current response or private user state.

The following remain unchanged:

- `/ontology.html` is a public, discoverable shell;
- `ontology_explorer_snapshot.v1` remains tenant-neutral and immutable by source-manifest identity;
- `LIVE_TRACE`, scenario, method, owner, privacy and authority boundaries from Amendment 1;
- `site_full` remains the commercial entitlement feature;
- no new auth framework, billing system, database, queue, user store or model owner is created.

Amendment 2 is binding alongside Amendment 1. Where access/transport wording conflicts, Amendment 2 controls.

---

## 3. X1 delivery architecture

### 3.1 Public shell

The following may remain in public Git and be served anonymously:

- `site/ontology.html`;
- presentation CSS/JavaScript that contains no current owner values, paid response body, private state or secret;
- bilingual methodology and a non-current instructional/reference diagram;
- locked, unavailable and sign-in/upgrade states;
- an explicitly approved bounded marketing/reference screenshot, if one is separately classified public-safe.

The shell may explain what the product does. It may not contain the current `ontology_explorer_snapshot.v1` in HTML, inline scripts, static imports, preload hints, service-worker precache manifests, source maps or fallback fixtures.

### 3.2 Authenticated current snapshot endpoint

X1 uses one authenticated, read-only Macro API route:

```text
GET /api/ontology/explorer/v1
Authorization: Bearer <Supabase access token>
```

The exact final path may change only if current API namespace archaeology proves a canonical adjacent namespace. It must remain one bounded product endpoint in the existing Macro API, not a second service or gateway.

The route follows the existing paid-reader pattern:

```text
require_user
-> enforce_site_full(always=True)
-> load exact owner input bytes/generations
-> pure F04 composer
-> validate ontology_explorer_snapshot.v1
-> private no-store response
```

Required response headers on success and every auth/entitlement/error response:

```text
Cache-Control: private, no-store
Vary: Authorization
X-Content-Type-Options: nosniff
X-Robots-Tag: noindex, noarchive
```

No unauthenticated edge/cache may convert an authenticated response into a shared cached object.

### 3.3 Projection source and lifetime

Preferred X1 implementation computes the tenant-neutral snapshot at request time from the exact deployed canonical owner artifacts through a pure deterministic composer. `snapshot_id` and `source_manifest_hash` derive from the exact owner bytes/generation identities and method version, so identical inputs produce the same logical snapshot without persisting another truth store.

A bounded in-process cache may be used only if:

- keyed by the complete source manifest and method version;
- contains tenant-neutral data only;
- cannot outlive or mask a changed owner generation;
- failed validation is never cached;
- HTTP responses remain `private, no-store`;
- cache state is not treated as durable truth.

If latency later requires a precomputed snapshot, it may be written only to an already accepted runtime-private artifact root or private object store through its canonical owner and provisioning. It may not be added to public Git, Pages, public R2 or a new F04-specific persistence plane. Missing accepted private transport returns `DECISION_REQUEST`; it does not justify falling back to `/premiumdata/`.

### 3.4 Router boundary

The API router is transport only. It may:

- authenticate and enforce entitlement;
- resolve bounded owner paths/generations;
- invoke the pure composer;
- validate the response;
- attach private headers and typed errors;
- enforce response-size and path-count limits.

It may not:

- implement TXI/rates/GMI/K3-D formulas;
- write owner artifacts, episodes, calibration, Portfolio, Watchlist or user state;
- generate model prose;
- persist scenario assumptions;
- create a second entitlement or session system;
- return raw source bodies or unbounded owner dumps.

### 3.5 Client behavior

The public client:

1. renders methodology/locked state without current values;
2. resolves the existing authenticated session and bearer token;
3. requests the API only after identity is available;
4. distinguishes `401`, `403`, `409/422` contract refusal and `503` owner/product unavailability;
5. keeps last-good data only in memory for the current page session and visibly marks it stale after a failed refresh;
6. never stores the full snapshot in localStorage, IndexedDB, Cache Storage, a service worker or a share URL;
7. never appends current values, evidence bodies or assumptions to query parameters/analytics.

Page reload without a successful authorized response returns to the locked/loading/unavailable state rather than reconstructing from a browser cache.

---

## 4. Access and mirror threat model

X1 must prove every path below, not only the primary origin.

| Path | Required outcome |
|---|---|
| `mastermind-x.com/ontology.html` anonymous | Public methodology/locked shell; no current snapshot bytes |
| API anonymous/malformed token | `401`, private/no-store headers |
| API authenticated Free/no `site_full` | `403`, private/no-store headers |
| API authenticated Essential/Pro with `site_full` | `200`, validated current snapshot, private/no-store headers |
| raw GitHub / repository contents | No current F04 snapshot file exists |
| anonymous clone | No current F04 snapshot or private overlay exists in any commit in the X1 carrier |
| GitHub Pages/static mirror | No current F04 snapshot or serialized body exists |
| public R2 base | No F04 current snapshot key exists |
| page source / JS bundles / source maps | No current response body, token, private overlay or secret |
| browser Cache Storage/service worker | No current snapshot persisted |
| committed evidence | No full response, token, holdings, weights, user ID or private session state |

The API endpoint itself must not be reachable through a raw/static mirror because it is runtime code, not a generated static artifact.

---

## 5. Evidence and proof policy

### 5.1 Public repository evidence

Public Git may contain:

- schemas and tests;
- response hashes, source-manifest hashes and generation IDs;
- status/header assertions;
- redacted/synthetic payload fixtures;
- bounded UI screenshots containing only information explicitly approved as public preview;
- counts and negative proof that no static snapshot path exists.

Public Git may not contain:

- full current API response;
- current multi-path paid payload dump;
- bearer token/cookie/session identifiers;
- raw holdings, weights, watchlist or saved-view data;
- private R2/object-store URLs or credentials;
- screenshots that expose a full paid dataset or another user's private state.

### 5.2 Production proof

Production proof records:

- exact deployed commit/build identity;
- endpoint status and required headers for anonymous, Free, Essential and Pro test identities;
- response schema/hash/source-manifest identity for authorized reads without publishing the full response;
- public-shell byte/source inspection;
- raw Git/Pages/public-R2 absence checks;
- browser network/cache/storage inspection;
- cleanup/restoration of any test identity or session state.

A primary-origin `401` with a tracked static twin is a failure.

---

## 6. Relationship to the existing estate-wide access defect

X1 is not authorized to repair the entire public Git/R2/Pages product-access estate. That is a separate broad program and may involve commercial, deployment and storage decisions beyond this child.

X1 must satisfy the narrower no-widening law:

> The F04 Explorer introduces no new full-fidelity current paid payload in public Git, Pages, public R2, public HTML, browser-persistent storage or committed evidence.

Existing public owner inputs and pre-existing premium leaks remain visible in the architecture ledger and prevent any claim that Mastermind's whole paid boundary is solved. X1 may claim only that its own new current snapshot transport is authenticated and does not add another mirror bypass.

If the Chairman later directs estate-wide access closure, that work must extend the canonical access/deployment owners and cannot be smuggled into F04 X1.

---

## 7. Revised X1 implementation paths

Expected X1 paths after fresh archaeology become conceptually:

```text
engine/ontology_explorer/                 # pure tenant-neutral projection only
app/ontology_explorer.py                  # authenticated read-only transport
app/main.py                               # minimal existing-router registration
scripts/build_ontology_explorer.py?       # only for validation/fixtures or runtime-private precompute; no public payload write
config / tests for canonical API/access wiring
site/ontology.html + public-safe assets    # shell only
```

The exact repository paths are not pre-authorized; current owner conventions and collision census decide them.

Explicitly prohibited:

```text
site/premiumdata/ontology_explorer.json
data/ontology_explorer/current_paid.json committed to public Git
public R2 ontology_explorer/current.json
inline window.__ONTOLOGY_SNAPSHOT__ = {...current values...}
service-worker precache of the API response
```

No new private bucket or secret is required for the preferred request-time X1 path.

---

## 8. Required hostile tests

### 8.1 Repository and build tests

- fail if any current F04 snapshot path is tracked under `site/**`, public artifact manifests or public-R2 publisher config;
- fail if the shell or bundle contains a representative current owner value or serialized snapshot schema/body;
- fail if a service-worker/precache manifest includes the API endpoint or response;
- fail if generated evidence contains full response/private fields;
- positive control proves the public shell still builds without current data.

### 8.2 API tests

- anonymous/missing/malformed/expired authorization fails closed with private headers;
- authenticated user without `site_full` receives `403` even when global paywall is staged/observe mode;
- entitled user receives one validated tenant-neutral snapshot;
- success and every error carry exact private/no-store/noindex/nosniff/Vary policy;
- source path/generation failure returns typed `503`, never an old static fallback;
- malformed owner input is not cached and cannot produce `200`;
- response refuses private/scenario/action-authority fields;
- router performs zero writes and invokes no model/forecast engine;
- bounded size/path/node limits fail closed.

### 8.3 Cross-origin/mirror proof

- no raw GitHub path for the current snapshot;
- no Pages/static path;
- no public R2 key;
- authorized browser response is absent from Cache Storage, localStorage and IndexedDB after reload;
- browser history/URL and analytics contain no snapshot body, evidence body, assumption or private overlay.

At least one mutation that writes the snapshot under `site/premiumdata/` must make the guard red.

---

## 9. Revised X1 acceptance

X1 cannot be accepted unless:

1. `/ontology.html` is public-safe and useful without current data;
2. current snapshot is delivered only by the authenticated read-only Macro API or an explicitly accepted equivalent private transport;
3. entitlement is `site_full` with `always=True` semantics;
4. success and errors are private/no-store/noindex/nosniff and vary on Authorization;
5. no current F04 snapshot exists in raw Git, clone, Pages, public R2, shell, bundle, source map, service-worker cache or committed evidence;
6. the response is tenant-neutral and every private/session/scenario field remains outside it;
7. Amendment 3 request-time owner-generation/source-manifest and typed
   deployed-checkout/pull-lag proof passes;
8. anonymous, Free, Essential and Pro behavior is proven against the exact production subject;
9. browser storage/network inspection proves no persistent unauthorized copy;
10. the capability claim is limited to F04 no-widening/access correctness, not estate-wide access integrity.

---

## 10. Routing, state and release gate

This amendment changes no placement or runtime truth.

```text
PARENT_OPERATION: marketontology-f04-ontology-transmission-20260826-fable-001
PREFERRED_AVENUE: Fable
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
CURRENT PRODUCT EFFECT: NONE
CURRENT ACCESS EFFECT: NONE
CURRENT WORKER EFFECT: NONE
```

Architecture PR #6820 subsequently merged as immutable history with eight records counted by
Git:

1. original architecture freeze;
2. Amendment 1;
3. Amendment 2;
4. binding decision;
5. Fable handoff;
6. implementation plan.
7. exact capability closure map.
8. F00 return reconciliation handoff.

The bounded follow-up repair adds Amendment 3 and minimally amends all eight predecessor
records. Its delta is verified against the two existing review packets; no third full review is
commissioned.

A merge makes this access ruling durable only. It does not create the API, alter an entitlement, remove existing public leaks, provision storage, place Fable, start X1 or deploy anything.

---

## 11. Exact next implementation decision

The X1 builder must begin with current API/auth/source-root archaeology and choose the smallest existing-pattern implementation:

```text
public shell
+ existing Macro auth/site_full dependency
+ pure request-time snapshot composition
+ private/no-store response
+ zero public payload file
```

If current production topology cannot support that without a new durable store, external secret or access framework, stop with `DECISION_REQUEST` before writing. Do not fall back to public static payloads.
