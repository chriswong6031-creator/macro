# BioCatalyst Recovery, Functional-Parity, and Alpha-Lobe Masterplan

**Repository:** `mastermindx-market-intelligence/macro`  
**Assessment date:** 2026-08-16  
**Primary production surface:** `biocatalyst.html`  
**Current handoff:** `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md`  
**Purpose:** establish what was actually built, explain why the production product is blank, preserve the valuable substrate, replace the current product direction, and define the path from a facts-only trial workbench to a functioning BioCatalyst intelligence lobe that can contribute bounded, auditable evidence to Prophet.



---

# SECOND-PASS EXECUTION ADDENDUM — Codex Steering Packet

**Second-pass timestamp:** 2026-08-16 01:53–02:00 America/Chicago window  
**Important repository condition:** `main` moved while this review was being performed. It was observed at `d2a3fd8fbf4bb706a4b64c314e20d27c111d9187` and then at `f8201036c1397f1b1cf34d1cfc00c46a0d55bf34` minutes later. **The SHA in this document is evidence, never a checkout instruction. Every Codex session must fetch current `origin/main` immediately before branching.**

This addendum is intentionally more operational than the masterplan below. Its purpose is to stop the next coding session from wandering into another multi-day architecture or contract rabbit hole before the live product works.

## A. New findings from the second pass

### A1. The screenshots narrow the failure more than the previous handoff did

The current browser has two terminal branches:

- `401`, `402`, or `403` -> `lockWorkspace()` -> the explicit full-access/locked state;
- almost everything else -> `handleUnavailable()` -> `workspaceDown = true` -> `paintUnavailableWorkspace()` -> **“Registry page unavailable.”**

The screenshots show the second state, not the locked state.

That materially changes the root-cause ranking. A simple “the user is signed out” explanation is **not the leading hypothesis**, because an anonymous request reaching the BioCatalyst FastAPI route should return `401`, and the client already knows how to paint that as locked. The displayed generic unavailable state instead implies one of these classes:

1. **503 from the API public-projection reader**;
2. **200 JSON followed by a client contract-validation exception**;
3. **network/redirect/content-type/JSON parse failure**;
4. **500 or other non-access server error**;
5. auth failure **plus** an edge/origin behavior that changes the normal 401/403 shape.

Do not begin by rewriting login. Capture the actual status and response first.

### A2. The API has one shared fail-closed seam capable of blanking nearly every mode

`app/biocatalyst.py::_read_bundle()` does this on every current-generation-backed read:

1. constructs `PublicGenerationPublisher(BIOCATALYST_PUBLIC_ROOT)`;
2. calls `read_trial_projection()`;
3. maps `OSError` or `PublicationError` to a generic HTTP 503;
4. reads operational health separately.

If the projection cannot be opened or validated, the route returns:

- status: `503`;
- detail: `trial intelligence temporarily unavailable`;
- no machine-readable public reason beyond that.

This is an excellent evidence-integrity behavior and a bad diagnostic behavior. A single pointer, manifest, schema, artifact, mount, deployment, or reader mismatch can therefore make Milestones, Change Tape, Trial Screen, First-seen Tape, health, and dossiers appear dead together.

The server log retains an internal failure code (`BioCatalyst public projection unavailable (<code>)`), but the browser cannot see a bounded error class. **Read the server journal before changing any contract.**

### A3. The client currently lies about a client contract mismatch by rendering it as a registry outage

The frontend contains strict validators for every payload. That is good. But the failure classification is wrong.

For Milestones and other modes, the sequence is effectively:

1. fetch JSON;
2. run `validate*Envelope(...)`;
3. if validation throws, set `state.contractFailed = true`;
4. throw again;
5. `handleUnavailable()` sets `workspaceDown = true` and calls the generic unavailable painter.

Therefore a **browser/API schema disagreement after a successful HTTP 200 can visually masquerade as “the registry is not answering.”**

This is one of the most important concrete bugs found in this pass. Do not weaken the validators. Preserve fail-closed behavior and surface a separate **client/API contract mismatch** state.

### A4. Authentication has a real silent-failure defect, but it does not by itself explain the screenshot

`templates/biocatalyst.js::withAuth()` currently behaves like this:

```text
if MDXAuth is absent -> continue without Authorization
else MDXAuth.client().auth.getSession()
if a token exists -> attach bearer
if ANY auth/client/session error occurs -> catch and continue without Authorization
```

The API's `require_site_full_user()` reads the **Authorization header** and then runs `enforce_site_full(..., always=True)`. It does not rely on the browser cookie directly. Therefore `withAuth()` silently downgrades auth-runtime failures to an anonymous API call.

This should be fixed regardless of the incident root cause. But if that anonymous request reaches the API normally, the result should be 401 and the UI should paint **locked**, not the generic unavailable state shown in the screenshots. Treat auth as a critical diagnostic branch, not a preconceived answer.

### A5. The site-wide auth config is currently baked correctly in repository output, but production bytes still need proof

`site/theme.js` on the reviewed main carries a real baked `window.SUPABASE_CFG` with the project ref, and `lib/site_assets.py` exists specifically to prevent builders from overwriting the baked file with the template's `null` placeholder.

That file documents a prior real estate-wide failure mode: another builder could copy raw `templates/theme.js` after `build_site.py`, leaving Supabase disabled everywhere. That bug was repaired centrally, but the history makes one diagnostic mandatory:

> **Hash and inspect the `theme.js` bytes actually served by production. Do not infer production auth configuration from the template or the GitHub copy.**

The BioCatalyst-specific builder copies only `biocatalyst.css` and `biocatalyst.js`; it does not own `theme.js`. Thus a BioCatalyst build can be correct while the shared auth runtime served beside it is stale or clobbered.

### A6. The existing browser verifier does not test the failure the user is experiencing

`scripts/biocatalyst_browser_verifier.py` is a design/epistemics verifier. It checks:

- bilingual Tier-1 copy;
- Decision Sentence limits;
- Temporal Braid text equivalents;
- hover-only meaning;
- keyboard focus;
- reduced-motion information parity.

Its Playwright driver opens a fresh unauthenticated context and performs no assertions on:

- Supabase session restoration;
- bearer header presence;
- `site_full` entitlement;
- BioCatalyst API response status;
- JSON content type;
- nonzero Milestone/Screen/Tape rows;
- dossier hydration;
- page/console errors;
- the active generation digest.

So even after the pending 24-cell design capture is finally run, **it still will not close the production-hydration incident.** Keep the design verifier. Add a second, orthogonal **hydration verifier**.

### A7. The current test estate has a missing integration altitude

The relevant existing tests cover different halves but not the whole path:

- `tests/test_biocatalyst_api.py` builds a real synthetic BioCatalyst generation, but mounts the router into a small test FastAPI app and **overrides `require_site_full_user` directly** with a fake paid user.
- `tests/test_biocatalyst_page.py` primarily verifies source/HTML/JS contracts and expected client tokens/branches.
- `tests/test_biocatalyst_d0b_ui.py` is explicitly a **source-level** design-contract suite.
- `scripts/biocatalyst_browser_verifier.py` is a real browser but does not authenticate or require data.

The missing test is:

> **assembled production app + real BioCatalyst auth seam + production-shaped published generation + actual browser client + nonzero result + dossier.**

This gap explains how hundreds or thousands of BioCatalyst tests can be green while the user-visible product is unusable.

### A8. Do not touch the source soak while rescuing the serving path

The 14-day B1S2c source window remains open until `2026-08-26T02:00:00Z`. The current incident can and should be diagnosed on the read/serving/client side without changing the source experiment.

Until the soak closes, the rescue lane should avoid changing:

- `scripts/biocatalyst_worker.py` collection semantics;
- `collectors/biocatalyst/**` source behavior;
- current-record cadence;
- history cadence;
- 900-second hourly timeout;
- source roster;
- launch denominator;
- freshness budget;
- fixed-cohort membership;
- frozen launch manifest policy.

A serving fix should not invalidate a prospective source experiment.

---

## B. Exact incident decision tree for Codex

The next session should treat the production failure as an incident with mutually exclusive branches. **Do not write code until the first branch is identified.**

### B0. Freeze evidence before touching anything

Record all of these in the session notes:

- current `origin/main` full SHA;
- current open PRs touching any intended file;
- production `/opt/macro` checkout SHA;
- global `/api/health` checkout stamp;
- SHA-256 and HTTP status for served:
  - `/biocatalyst.html`;
  - `/biocatalyst.css`;
  - `/biocatalyst.js`;
  - `/theme.js`;
  - `/supabase.js`;
- `systemctl` state for `macro-api` and the three BioCatalyst source lanes;
- active public generation ID and manifest digest;
- public projection current trial count;
- API journal lines around the failing request.

This prevents a stale-deploy problem from being “fixed” in source code.

### B1. Anonymous control

Expected behavior:

```text
GET /api/biocatalyst/v1/health with NO bearer -> 401
```

If it returns anything else, stop. The access/routing boundary is already wrong and entitled-browser debugging is premature.

### B2. Entitled bearer at localhost FastAPI

Using a real entitled token supplied interactively and never logged or committed:

```text
GET http://127.0.0.1:8000/api/biocatalyst/v1/health
Authorization: Bearer <redacted>
```

Interpretation:

- **200 JSON** -> auth + API reader work inside the serving process; continue to B3.
- **401** -> token/session validation failure.
- **403** -> authenticated but `site_full` entitlement failure.
- **503** -> public projection/read-bundle failure. Jump to B5.
- **500** -> uncaught serving bug. Read journal traceback before editing.

### B3. Same bearer through the public domain

Run the identical request through `https://www.mastermind-x.com/...`.

Interpretation:

- localhost 200, public 200 -> edge is not the failure; continue to B4.
- localhost 200, public 401/403 -> Authorization header lost/rewritten or edge auth disagreement.
- localhost 200, public 404 -> route/reverse-proxy/static matcher problem.
- localhost 200, public 5xx -> reverse proxy/origin mismatch.
- both 503 -> shared public-projection problem, not Caddy.

### B4. Public API 200 but browser still shows unavailable

This is the **client integration branch**.

Capture:

- exact endpoint URL;
- HTTP status;
- content type;
- response schema/contract ID;
- row count;
- first exception thrown by `validateMilestoneEnvelope`, `validateScreenEnvelope`, `validateChangeEnvelope`, or `validateProspectiveEnvelope`;
- whether `state.contractFailed` becomes true;
- console and `pageerror` events.

Then compare the returned payload with the frontend validator **field for field**. Do not remove the failing check until you identify which side of the contract is stale.

Correct remedies are one of:

