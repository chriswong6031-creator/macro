- the same page shell;
- the same authentication bootstrap;
- the same `fetchJson`/`postJson` helpers;
- the same private API prefix;
- the same published-generation root;
- the same broad error-state renderer.

Because Milestones, Trial Screen, Change Tape, and First-seen Tape all fail in similar ways while the shell itself loads, the most likely problem is a **shared authentication, API, projection, or contract seam**, not five separate UI bugs.

Peer Matrix being empty before the user supplies NCT IDs is expected. The other modes should not all be blank.

### 4.2 The frontend silently degrades authentication

The current client attaches a bearer token only when `window.MDXAuth.client()` exists and returns a session. Any error in that sequence is caught, discarded, and followed by an anonymous request.

This creates a dangerous ambiguity:

- no Supabase client;
- session bootstrap race;
- expired session;
- invalid token;
- wrong token audience;
- user missing `site_full`;
- edge or API rejection;

can all begin with the same hidden client-side failure.

The user then sees “Registry page unavailable,” not “your session could not be established.”

### 4.3 The current generic error state destroys diagnosis

The frontend has broad branches for access errors and broad branches for everything else. Multiple materially different faults collapse into the same copy:

- API returned 500/503;
- edge returned HTML instead of JSON;
- response was 200 with a schema mismatch;
- projection pointer was missing;
- generation validator rejected the artifact;
- request was redirected;
- session was absent;
- network request was blocked.

A generic unavailable card is acceptable as a final fallback. It is not acceptable as the only production telemetry.

### 4.4 The backend can fail closed on the shared generation

The API reads from a pointer-bound published projection. A missing or invalid projection, a failed schema check, or a broken generation can make every endpoint unavailable together.

This is correct for evidence integrity, but the product must expose the distinction between:

- source unavailable;
- collector failed;
- projection missing;
- projection stale;
- projection contract invalid;
- API reader failed;
- entitlement failed;
- frontend parse failed.

At present, the user sees one sentence for all of them.

### 4.5 The handoff itself admits the key proof was never completed

The handoff explicitly states that a signed-in, entitled browser-level payload proof is still owed. Static 200 responses for the page, CSS, and JavaScript are not proof that the private data works.

The production screenshots are therefore not a surprising regression after a fully completed product. They are evidence that the final acceptance gate was never actually passed.

---

## 5. P0 incident plan: make the existing product work before building more

Freeze all feature work until this is complete. No new model, source, or interface should be merged while the shared hydration path is unknown.

### 5.1 Trace the request through all three serving layers

For one known entitled account and one known working trial, capture the same request at:

1. public browser URL;
2. Caddy/edge origin;
3. localhost FastAPI.

For each layer record:

- request ID;
- URL;
- method;
- status;
- content type;
- response bytes;
- token-present boolean;
- entitlement result;
- generation ID;
- projection digest;
- API contract version;
- error code.

The trace must establish exactly where the response changes.

### 5.2 Verify authentication separately from data

Add a small private diagnostic endpoint that returns only:

- authenticated: true/false;
- user ID hash;
- plan/tier;
- `site_full` result;
- token expiry;
- request ID.

It must return no market or user-sensitive payload. This turns “is the session real?” into a direct answer instead of an inference from a failed trial query.

### 5.3 Verify the generation separately from the browser

On the production host:

- resolve the active pointer;
- validate the generation;
- count current trials;
- count history records;
- count milestone rows;
- count change rows;
- count first-seen rows;
- open one known trial;
- run the same API reader as the server;
- record the generation digest and timestamp.

A collector success receipt is not sufficient. The exact generation the API reads must be proven.

### 5.4 Replace generic failures with typed states

The API should emit stable machine-readable codes, and the browser should render them distinctly:

| Code | Meaning | User treatment |
|---|---|---|
| `SIGN_IN_REQUIRED` | No valid session | Sign-in action |
| `ENTITLEMENT_REQUIRED` | Valid session, wrong tier | Upgrade/access action |
| `SOURCE_UNAVAILABLE` | Upstream source could not be reached | Retry and source status |
| `SOURCE_STALE` | Source content exceeds governing freshness clock | Staleness disclosure |
| `PROJECTION_MISSING` | No active published generation | Operator incident |
| `PROJECTION_INVALID` | Generation failed contract validation | Operator incident |
| `CONTRACT_MISMATCH` | Browser/API schema disagreement | Reload/version incident |
| `EMPTY_VALID` | Query is valid and truly has zero matches | Normal empty state |
| `NETWORK_FAILED` | Browser could not reach API | Retry |
| `INTERNAL_ERROR` | Unclassified server error | Request ID and support path |

Never render a locked account as missing data. Never render invalid data as a legitimate zero.

### 5.5 Install a real signed-in browser gate

A Playwright test must use a production-equivalent entitled account and prove:

- page and assets load;
- session is restored;
- `/health` returns the expected auth result;
- Trial Screen returns at least one row;
- Milestones returns at least one row;
- Change Tape returns at least one row;
- First-seen Tape returns at least one row;
- a known peer cohort resolves in the exact order supplied;
- a dossier opens;
- a source locator is clickable;
- anonymous access renders locked, not unavailable;
- a source fault renders source-specific degradation;
- no console error occurs.

The acceptance artifact should contain screenshots, a redacted HAR, response summaries, and the active generation digest.

### 5.6 Settle the freshness-clock contradiction

The launch manifest and deployed runtime currently use different freshness meanings. One uses the ClinicalTrials.gov dataset timestamp; the other uses the local successful transaction time. The same runs pass under one and fail under the other.

This cannot be “fixed” by choosing whichever clock is green.

The correct model should expose at least two clocks:

- **source content age:** how old the upstream dataset says its content is;
- **transport age:** how long since our system successfully retrieved and published it.

Product health can then say:

- transport fresh / source content stale;
- transport stale / source content unknown;
- both fresh;
- both stale.

Any launch SLO must name which axis governs each feature.

---

## 6. The central product mistake: the project optimized for governance instead of the commissioned product

The work followed a very conservative internal charter:

- no inferred company/security links;
- no scores;
- no probabilities;
- no candidate origination;
- no Prophet reordering;
- no market stance;
- no second application;
- no separate market-data plane;
- no broad discovery before fixed-cohort proof.

Those restrictions produced a trustworthy substrate. They also made the intended product impossible.

The internal parity ledger even counts “Neural Web/Prophet deliberately not wired” as a parity-satisfying row. That is internally coherent under the old charter and directly contrary to the current business goal.

The user’s actual objective is:

1. a rich BioPharmCatalyst-class information product;
2. a domain lobe that extracts and learns from clinical, regulatory, financing, ownership, market, and options information;
3. a point-in-time signal plane that identifies asymmetric opportunity and unpriced information;
4. a bounded contribution to Prophet ranking among already excellent candidates.

That objective requires a formal charter change.

---

## 7. Required governance reset

Create a new decision record before implementation:

### Proposed ruling

> BioCatalyst may build reviewed entity resolution, event probabilities, timing models, financing-survival features, market-response models, options and positioning features, and an asymmetric-opportunity research score. These outputs begin at display or shadow authority. After passing frozen forward gates, BioCatalyst may contribute bounded evidence-family members that affect order among already-admitted Prophet candidates. It may not initially admit a new candidate, change position size, alter entry geometry, or bypass execution safeguards.

### What this changes

It supersedes the old “never rank or reorder Prophet” rule for a narrow, explicit path.

### What it does not change

- no look-ahead;
- no invented identity;
- no silent zero for missing data;
- no browser-side re-ranking;
- no duplicate Prophet implementation;
- no duplicate Massive/Polygon or options ingest;
- no direct live authority without shadow evidence;
- no unbounded additive mega-score;
- no use of current-only data in historical evaluation;
- no raw ClinicalTrials.gov field treated as investment truth without entity and temporal review.

---

## 8. What “functional parity” should mean

The target should be clean-room functional parity, not visual copying and not replication of proprietary content or private APIs.

Your screenshots show that the benchmark is an estate, not one dashboard.

### 8.1 Target feature families

#### Calendars and event data

- FDA calendar;
- PDUFA calendar;
- clinical readout calendar;
- AdCom calendar;
- historical catalyst calendar;
- biotech IPO calendar;
- medical-device calendar;
- biotech conference calendar;
- earnings calendar;
- foreign approval calendar.

#### Company, asset, and pipeline research

- company pages;
- drug pipeline database and screener;
- medical-device pipeline database and screener;
- asset × indication pages;
- trial explorer;
- trial insights;
- regulatory history;
- label/safety/recall/shortage context;
- patent and exclusivity context;
- licensing and partnership context.

#### Financial and ownership intelligence

- cash database;
- burn and runway;
- debt, converts, warrants, ATM and shelf capacity;
- dilution and financing survival through catalyst;
- earnings estimates;
- analyst ratings;
- insider trades;
- 13F and hedge-fund ownership;
- M&A and transactions;
- IPO and lockup history.

#### Market and portfolio tools

- biotech stocks dashboard;
- premarket and after-hours movers;
- gainers and losers;
- unusual volume;
- sector/subsector heatmaps;
- relative-strength and residual-return views;
- model portfolios;
- watchlists;
- portfolio news;
- catalyst impact;
- options data;
- alerts and historical notifications.

#### Research and distribution

- analysis pages;
- probability-of-success research;
- catalyst timing research;
- market-impact research;
- API;
- exports;
- BPC-style reports and training content.

### 8.2 Current practical parity

The internal ledger’s 8/32 count includes exclusions, licensed-later, correct-by-design unwiring, and partial work. For the user-visible parity goal, the more honest current count is approximately:

- **4 implemented product jobs**: trial screen, milestone monitor, trial revision intelligence, peer comparison;
- **3 partial jobs**: narrow transcript seam, partial API, partial research compiler;
- **the rest absent, blocked, or not productized.**

This is a strong trial-history subsystem and a weak platform.

---

## 9. Replace the single blank workbench with a modular product estate

The current three-column screen can remain as an advanced trial-research workspace. It should no longer be the product’s primary shell.

### 9.1 Recommended top-level surfaces

