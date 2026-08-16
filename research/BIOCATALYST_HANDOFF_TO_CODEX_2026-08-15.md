# BioCatalyst — next-session handoff, 2026-08-15

> Snapshot time: `2026-08-15T10:10:43Z` against `origin/main`
> `576ce390092192b4270ae53a4d3b91713e7e374d`. This document supersedes the
> action state in `BIOCATALYST_HANDOFF_TO_CODEX_2026-08-10.md`; the older file
> remains useful as historical evidence for the publication repair and exact
> soak activation.

## 0. Executive verdict

BioCatalyst is a **live, narrow, evidence-first ClinicalTrials.gov product and
operating data lane**. It is not yet a closed-beta-complete biopharma platform,
not functionally equivalent to the 32-row benchmark, and not a predictive or
trading system.

The current collector, history lane, fixed-cohort transport, trial APIs, and
five-mode browser workbench are real. The current launch-critical transport
record is excellent: 81 of 81 due hourly opportunities completed inside their
frozen windows, four of four daily history runs mirrored exactly, and three of
three scheduled fixed-cohort runs reconciled 4/4. The calendar-bound soak is
still open until `2026-08-26T02:00:00Z`.

There are two separate reasons nobody may call the project complete:

1. The launch-SLO evidence has not been built or verified, and a **freshness
   clock conflict** described below can invalidate the pass.
2. The closed-beta source denominator has only **2 of 6 mandatory families
   available**. A successful ClinicalTrials.gov soak does not create the four
   missing source/identity families.

| Claim | Honest state now | Evidence boundary |
|---|---|---|
| Product exists in production | **Yes** | Page, assets, private APIs and current projection are live |
| Current-record collector works | **Yes** | 81/81 due opportunities; 4 configured / 4 observed |
| Record-history mirroring works | **Yes, bounded to the four-NCT proof cohort** | 4/4 scheduled history runs; 381 objects/run, 366 history objects |
| Fixed-cohort transport works | **Yes, private and exact** | 3/3 scheduled runs; exact 4 requested / 4 returned |
| Fourteen-day launch soak passed | **Not established** | Window remains open; final typed evidence and verifier pass do not exist |
| Biopharma closed beta is ready | **No** | Closed-beta manifest says 2/6 mandatory source families available |
| Functional benchmark parity | **No — 8/32** | 24 rows remain partial, blocked, or unbuilt |
| Prophet or Neural Web authority exists | **No, deliberately** | All authority flags remain false |

## 1. What exists now

### 1.1 User-facing product

Production URL:

`https://www.mastermind-x.com/biocatalyst.html?field=primary_completion&window=90`

The current product is one responsive, bilingual trial workbench with five
user-selectable modes:

- **Milestones** — source-reported registry milestones, never automatically a
  market catalyst;
- **Trial Screen** — literal, server-owned filtering and facets;
- **Peer Matrix** — exact comparison of 2–100 caller-supplied NCT IDs, with no
  automatic peer discovery or ranking;
- **Change Tape** — replay-verified exact before/after field values, source
  paths, source versions, and correction lineage; and
- **First-seen Tape** — retention/activation-gated prospective observations,
  with no historical backfill claim.

The right-side dossier reads the current registry record and its source
evidence. The shell already contains responsive mobile behavior, dark/light
themes, English/Chinese copy, explicit loading/locked/stale/empty/unavailable
states, and a Mastermind research affordance.

The shell and payload are intentionally split:

- `/biocatalyst.html`, `/biocatalyst.css`, and `/biocatalyst.js` are public
  presentation assets and contain no trial payload;
- all analytical APIs require `site_full`, return private/no-store responses,
  and may return `401` to an anonymous caller; and
- raw R2 evidence, receipts, object keys, private hashes, filesystem paths, and
  credentials never enter the browser response.

PR `#5710`, merge `50a47d036f6d6bf14d13caf9b9512c207f09e5a7`, fixed one
concrete cause of an intermittently inert workbench by keeping all three public
shell assets outside the registration wall while leaving the analytical API
paid. At this snapshot the page, CSS, and JavaScript each returned `200`; an
anonymous health API request returned the expected `401`.

**Proof still owed:** this handoff did not perform an authenticated `site_full`
browser capture after `#5710`. The production pointer is healthy, but the next
session should verify the signed-in `/health`, `/trials/milestones`, and visible
record render before declaring the earlier `Registry page unavailable` report
fully closed. Public shell `200` is not payload proof; a paid-API entitlement or
request failure would produce a separate unavailable state even when all three
assets load correctly.

### 1.2 Private API that must be extended, not replaced

| Route | Present job |
|---|---|
| `GET /api/biocatalyst/v1/health` | Bounded current-generation health |
| `GET /api/biocatalyst/v1/trials` | Current trial projection |
| `GET /api/biocatalyst/v1/trials/{nct_id}` | Trial dossier/detail |
| `GET /api/biocatalyst/v1/trials/milestones` | Registry milestone view |
| `GET /api/biocatalyst/v1/trials/changes` | Legacy historical-change projection |
| `GET /api/biocatalyst/v1/trials/change-tape` | Replay-verified Change Tape |
| `GET /api/biocatalyst/v1/trials/prospective-changes` | First-seen change ledger |
| `GET /api/biocatalyst/v1/trials:screen` | Facts-only literal-AND screen |
| `GET /api/biocatalyst/v1/trials:screen/facets` | Atomic facet counts |
| `POST /api/biocatalyst/v1/trial-peer-sets:resolve` | Explicit-NCT facts-only peer comparison |

Keep generation/query/caller-bound cursors, bounded payloads, authentication,
entitlement, `private, no-store`, `Vary: Authorization`, and explicit
unavailable responses. Do not create a second API, SPA, trial store, pointer,
or browser-side truth plane.

### 1.3 Operating data system

The production system has three armed lanes:

| Lane | Unit | Current contract |
|---|---|---|
| Current record | `macro-biocatalyst.service` / `.timer` | Hourly, forced `BIOCATALYST_HISTORY_ENABLED=0`, 900-second timeout |
| Record history | `macro-biocatalyst-history.service` / `.timer` | Daily around 02:20 UTC, forced `BIOCATALYST_HISTORY_ENABLED=1`, 2700-second timeout |
| Fixed cohort | `macro-biocatalyst-fixed-cohort.service` / `.timer` | Daily, private exact-membership transport, 600-second timeout, no R2/public projection authority |

The lane-specific `/usr/bin/env BIOCATALYST_HISTORY_ENABLED={0,1}` process
prefixes are load-bearing. systemd `EnvironmentFile=` values override ordinary
`Environment=` lines regardless of textual order; the earlier hourly timeout
was caused by inheriting history mode. Do not remove the process prefixes or
widen the 900-second boundary.

Current publication uses one atomic public generation pointer, immutable local
generation artifacts, and verified R2 mirror receipts. A process exit code by
itself is never success: require the complete generation, pointer/health
binding, mirror receipt, exact object hashes/counts, and service completion.

### 1.4 Fixed cohort

- cohort ID: `ctgov_fixed_cohort_ec83219c405a1eec0ec86324`;
- active manifest SHA-256:
  `c1d8bdd27607ea32333e8021131b61ca8bd0bca803ad5189aed04afc521d624f`;
- membership: four exact NCT IDs in a root-owned immutable manifest, never an
  environment variable or CLI list;
- latest scheduled run:
  `ctgov_fixed_cohort_transport_run_46c8e61eb82ad5d81bec9c27`;
- latest result: `complete`, `exact_fixed_cohort_match`, 4 requested / 4
  returned, no error code; and
- authority: `facts_and_context_only`, with dynamic expansion, scoring,
  prediction, Prophet and Neural Web authority explicitly prohibited.

The first pre-window transport attempt correctly quarantined on
`NEXT_PAGE_TOKEN_PRESENT`. The final transport asks for one bounded sentinel
slot, still accepts exactly the four manifest members, and still rejects a
continuation token. Preserve the rejected receipt as fail-closed proof; it is
not a scheduled soak miss.

### 1.5 Forward outcome clocks

Nine immutable family-clock activation receipts exist. Three families opened
at `2026-08-11T20:20:43.514252Z`:

- `trial_progression_termination`;
- `timing_slip`; and
- `enrollment_site_change`.

Six remain closed on their declared blockers; `endpoint_readout` is among the
closed families. These receipts start prospective accrual only. They do not
create forecasts, probabilities, rankings, scores, sizing, Prophet behavior,
or Neural Web authority.

### 1.6 Cross-plane capability now present

`BC-C2` is merged as a narrow, private, point-in-time Capital Structure read
adapter. It can return owner-verified filing-event context for a caller-supplied
SEC issuer at a requested system clock. It does **not** make cash, runway,
fully diluted shares, financing capacity, financing probability, or dilution
distribution available. Capital Structure remains the truth owner.

The narrow transcript adapter is also available for caller-supplied ticker
context. It is not a general corporate document/span service and does not
prove issuer/security/sponsor/trial identity.

## 2. Production and repository snapshot

### 2.1 Live evidence at `2026-08-15T10:10:43Z`

| Check | Observed state |
|---|---|
| Production repository checkout | `576ce390092192b4270ae53a4d3b91713e7e374d` |
| `/api/health` | `status: ok`, checkout `576ce390092` |
| BioCatalyst page / CSS / JS | `200` / `200` / `200` |
| Anonymous BioCatalyst API | `401`, expected entitlement boundary |
| Current public generation | `ctgov_run_20260815T100023291081Z_e679bb3d2518` |
| Public health | `fresh`, enabled, 4 configured / 4 observed, no error code |
| Current mirror receipt | 15 unique, positive-byte, SHA-256-bound objects |
| Hourly schedule | 81 expected / 81 started / 81 completed / 81 successful |
| Missing or duplicate hourly openings | 0 / 0 |
| Hourly opportunities outside 900 seconds | 0 |
| Maximum hourly service runtime | 224.459 seconds |
| Daily history schedule | 4 expected / 4 completed / 4 successful |
| Latest history mirror | 381 objects, exactly 366 history objects |
| Scheduled fixed cohort | 3 runs / 3 exact 4/4 / 0 failures |
| Timer state | all three enabled, active, waiting on their next due run |

The hourly denominator above covers every opening from
`2026-08-12T02:00:00Z` through `2026-08-15T10:00:00Z`. It contains no
maintenance exclusions, post-hoc exclusions, substituted pre-window proofs,
omissions, extras, or duplicate openings.

The complete frozen window contains **336** hourly openings: start inclusive,
end exclusive, from `2026-08-12T02:00:00Z` through the final opening at
`2026-08-26T01:00:00Z`. The verifier cannot run a pass before
`2026-08-26T02:00:00Z`.

### 2.2 Critical freshness-clock conflict

Transport success and launch-SLO freshness are not currently the same claim.

The frozen launch manifest says the freshness clock origin is:

`ClinicalTrials.gov API v2 /version dataTimestamp observed by the committed source receipt`

The operations runbook and production code say the raw offset-optional
`dataTimestamp` is lineage/version evidence and is **never used for elapsed
freshness arithmetic**. Public health derives age from transaction-time
`last_success_at`; the source registry describes the two-hour target as worker
operations after an observed source refresh.

Provisional measurement over the same 81 hourly generations shows the two
readings have opposite results:

| Candidate clock | p95 elapsed | Opportunities at or below 7,200 seconds |
|---|---:|---:|
| Literal service completion minus raw `/version dataTimestamp` value | 93,835 seconds | 0/81 |
| Service completion minus committed `last_success_at` transaction time | 191 seconds | 81/81 |

This is the highest-risk unresolved item in the launch closeout. The scheduled
manifest is immutable and the offline verifier requires the completed successor
to preserve its frozen source policy exactly. Therefore:

- do not widen 7,200 seconds;
- do not rewrite `clock_origin` after seeing the data;
- do not fill `freshness_seconds` with the favorable clock without a reviewed,
  reproducible derivation from the already-frozen runbook/registry semantics;
- do not treat public health `fresh` as proof that the launch artifact's
  freshness field is valid; and
- if the literal raw timestamp value is adjudicated as binding, record the soak
  as failed. A new prospective window under a corrected predecessor policy
  would then be required.

The next session should settle the derivation before building the final
artifact. Ambiguity fails closed; it is not permission to choose the green
reading.

### 2.3 Shipped merges that define the current state

| PR / merge | What it actually shipped |
|---|---|
| `#5311` / `f69157e2f424` | Publication across the worker/API sandbox mount boundary |
| `#5328` / `c14f03904317` | Narrow governed Capital Structure PIT adapter |
| `#5336` / `138293dd4662` | Bounded outcome-family activation receipts |
| `#5387` / `812685f5d736` | Verified Change Tape values in the live browser |
| `#5399` / `2371f537a253` | B1S2c lane split and frozen soak schedule |
| `#5404` / `2f30530edeb3` | Correct lane-specific runtime environment boundary |
| `#5428` / `029982b68611` | Exact activation and live proof handoff |
| `#5710` / `50a47d036f6d` | Public workbench shell assets outside regwall; paid API unchanged |

There were no open GitHub pull requests with `biocatalyst` in the title at this
snapshot.

Verification baseline:

- the prior exact BioCatalyst suite on the activation merge was **1377 passed**;
- current-main launch-verifier, closed-beta-manifest, product-page and deploy
  suites: **118 passed** in 37.13 seconds, with three non-failing pytest
  temporary-directory cleanup warnings; and
- attempting `pytest -q tests/ -k biocatalyst` in a generic local Python 3.12
  environment is not a valid baseline because pytest still imports unrelated
  modules during collection and this workstation environment lacks the Stripe
  SDK. Use explicit BioCatalyst test paths or the repository CI environment.

## 3. What is not done

### 3.1 Launch and acceptance gates

| Gate | State | Why it remains open |
|---|---|---|
| B1S2c fourteen-day soak | Running | Calendar ends `2026-08-26T02:00:00Z` |
| Launch-SLO evidence | Not built | No real raw-telemetry/generation/recovery/CI artifact set exists |
| Launch-SLO evidence assembler | Not operationally packaged | Verifier exists as a library; production telemetry-to-artifact CLI/workflow does not |
| Freshness semantics | Unsettled | Frozen manifest wording conflicts with runbook/runtime elapsed clock |
| Authenticated browser proof after `#5710` | Not captured in this handoff | Public assets and server state are green; signed-in payload render still needs proof |
| D0b browser acceptance | Not run | `biocatalyst_product_acceptance_v2.yml` remains `draft_awaiting_browser_capture` |
| Closed-beta source denominator | Failed closed | 2 of 6 mandatory families available |

The browser acceptance manifest has named design approval **with amendments**,
but the trusted browser matrix is `not_run`. It requires 24 viewport/theme/
language/motion cells, the frozen accessibility/content checks, real browser
bytes, and a digest-bound verification receipt. The old synthetic D0a plates
are not an implementation target and are not product acceptance.

### 3.2 Closed-beta denominator

`config/biocatalyst_closed_beta_source_manifest.yml` is deliberately
`draft_denominator_unarmed` and says `closed_beta_source_denominator_not_met`.

| Mandatory family | Availability now | Real blocker/state |
|---|---|---|
| ClinicalTrials.gov current record | Available | Launch evidence still incomplete |
| ClinicalTrials.gov discovery scope | Unavailable | Dark contract/hermetic harness only |
| Regulator application/submission | Unavailable | Drugs@FDA rights/activation review not complete |
| Company and asset PIT identity | Unavailable | No reviewed owning-plane PIT read contract |
| Security/corporate-actions PIT context | Unavailable | Bootstrap roster is not a complete security master |
| Capital Structure PIT | Available, narrow | Event-state context only; cash/runway/dilution unavailable |

Even a clean B1 launch-SLO pass moves only the ClinicalTrials.gov operating
claim. It must not silently set all mandatory families available or convert the
closed-beta denominator to ready.

### 3.3 Functional parity

The honest benchmark tally remains **8 of 32**:

| Bucket | Rows | Counts toward current §17 parity? |
|---|---:|---|
| Implemented with eligible source and user surface | 4 | yes |
| Formally excluded | 2 | yes |
| Licensed-later with honest unavailable state | 1 | yes |
| Correct by design — Neural Web/Prophet deliberately unwired | 1 | yes |
| Partial | 3 | no |
| Blocked on another plane or source-rights decision | 15 | no |
| In-program, not built | 6 | no |

The four implemented jobs are Trial Screen, registry Milestones, Change Tape,
and explicit Peer Matrix. The partial jobs are the narrow corporate/transcript
surface, API/data product expansion, and Mastermind research compiler/caller.

Most remaining parity work cannot be completed responsibly by adding more
BioCatalyst-local code. Ten blocked rows reduce to missing adjacent-plane,
versioned, point-in-time read contracts; five more are source-rights or
market-data decisions.

### 3.4 Product and data capabilities still absent

- governed discovery and measured expansion beyond the four-NCT proof cohort;
- integration of the fixed-cohort transport output into the existing evidence
  plane after the soak gate;
- full company, asset × indication, regulatory, patent, partnership, financing,
  ownership, transaction, market/options, and catalyst dossiers;
- point-in-time company/security/corporate-action identity;
- a complete catalyst calendar/radar across registry, regulator, corporate and
  market facts;
- Terminal/Supabase-backed saved cohorts, watches, correction-aware alerts,
  exports, and tenant audit trail;
- a production source/review/replay/rollback console;
- expanded versioned API scopes for dossiers/events/as-of/updated-since;
- browser-verified D0b state atlas and seven-surface information architecture;
- complete outcome/forecast homes, calibrated baselines, preregistered
  challengers, or expected-value scenario graphs;
- an operating BioCatalyst packet producer and one governed Neural Web reader;
  and
- any Prophet behavioral authority.

## 4. Remaining work, in the order that matters

Realistic timing guardrails:

- the earliest possible B1 source-soak close is
  `2026-08-26T02:00:00Z`, and only if the frozen evidence recomputes cleanly;
- a full biopharma closed-beta date is not yet knowable because four mandatory
  source/identity families depend on adjacent owners or rights decisions;
- 32-row benchmark parity is a multi-wave program, not one continuation
  session; and
- predictive superiority requires months of prospective, correction-aware
  accrual after eligible clocks open. Historical-fit shortcuts do not reduce
  that calendar.

### Priority 0 — before `2026-08-26T02:00:00Z`

1. **Keep the production schedule untouched.** Continue hourly, daily-history,
   and fixed-cohort monitoring. Preserve every failure, outage, retry, and
   scheduled opening; no post-hoc exclusions.
2. **Settle the freshness derivation before closeout.** Reconcile the frozen
   manifest, source registry, runbook, actual receipts, and verifier field
   semantics without changing the scheduled policy. Produce a reviewable
   ruling. If no single derivation is justified, the result is fail-closed.
3. **Build the missing evidence assembler as non-authorizing tooling.** The repo
   has `verify_biocatalyst_launch_slo_evidence(...)`, schemas, hostile tests, and
   synthetic fixture builders, but no production CLI that maps the real 336
   opportunities into canonical typed artifacts. Build and test the assembler
   against copied/read-only evidence; do not manufacture the final result or
   mutate the scheduled manifest before the window ends.
4. **Prove the authenticated product path.** With a real `site_full` session,
   verify health, milestones, one trial record, and visible non-empty rendering
   after `#5710`. Diagnose entitlement/API/client errors separately from
   collector publication.
5. **Avoid launch-critical runtime churn.** Product/documentation work may
   proceed in isolated branches, but do not alter the hourly cadence, timeout,
   freshness budget, source roster, denominator, publisher, or process
   environment during the prospective window unless an incident requires an
   honest corrective action.

### Priority 0 — on or after `2026-08-26T02:00:00Z`

1. Freeze a read-only evidence snapshot containing exactly the 336 scheduled
   openings and the immutable receipts/generations they bind.
2. Build one canonical `raw_telemetry` artifact for
   `clinicaltrials_gov_v2`, with exactly one observation for every frozen
   opening and monotone stage results.
3. Build the aggregate `telemetry_generation` artifact and bind exactly the
   raw-telemetry digest set.
4. Execute real correction-replay and rollback/restore drills after the soak
   end. Capture typed input/readback objects, exact digests, chronology and
   verification checks. A self-described `result: passed` is insufficient.
5. Run the exact CI/contract/integrity/source-recomputation checks after the
   window and capture the typed `ci_validation` artifact against a full commit
   OID.
6. Construct a successor launch manifest that preserves every frozen source,
   threshold, cadence, denominator, authority and window field. Set
   `soak_complete_passed` only if the evidence recomputation truly passes.
7. Call `verify_biocatalyst_launch_slo_evidence(...)` against an absolute,
   non-symlink offline store with the required sentinel and canonical,
   content-addressed files.
8. If verification fails, record the failure without deleting opportunities
   or changing thresholds. Determine whether remediation requires a new
   prospective window under a new predecessor.
9. If verification passes, update the launch-SLO and closed-beta manifests only
   as far as the evidence permits. The closed-beta manifest must still show any
   unavailable mandatory families and must not claim denominator readiness
   unless all six are genuinely available.
10. Ship the successor artifacts through a fresh branch, PR, squash merge,
    production deployment, exact ancestry/health proof, and live surface check.
    Only then may the soak monitor be paused.

The offline verifier expects five typed evidence roles: per-source raw
telemetry, per-source correction replay, per-source rollback restore, one
aggregate telemetry generation, and one aggregate CI validation artifact. See
`docs/BIOCATALYST_LAUNCH_SLO_OFFLINE_VERIFIER.md` before writing any builder.

### Priority 1 — finish the bounded live trial product

After the B1S2c gate settles:

1. **W1-C controlled ingestion:** connect fixed-cohort receipt/run output into
   the existing raw-receipt, storage, watermark, publication and read planes.
   Reuse the current collector/storage/publisher; do not create a second store.
2. **W1-D measured discovery:** graduate the hermetic discovery harness through
   explicit, reviewed coverage epochs. Expand by bounded cohorts with exact
   pagination, completeness, rollback and correction denominators — never an
   unbounded universe switch.
3. **D0b product acceptance:** implement the approved state atlas in the
   existing shell, then capture the 24-cell real-browser matrix and verifier
   receipt. The current five-mode workbench is useful but is not the final
   seven-surface product.
4. **API and operations:** finish stable search/dossier/events/as-of/
   updated-since scopes, source health/review/replay console, audit export and
   correction guarantees.
5. **Tenant state:** connect saved cohorts, watches, alerts and exports only
   through the Terminal/Supabase owner plane.

### Priority 2 — unblock adjacent facts rather than duplicate them

| Needed contract/decision | Rows or surfaces it unlocks | Owner action required |
|---|---|---|
| Company PIT identity | company screen/dossier, asset graph, M&A | Publish reviewed as-of/as-known identity with ambiguity behavior |
| Security + corporate-actions PIT | ticker joins, market context, movers | Publish complete versioned security/listing/corporate-action read contract |
| Corporate document + exact span | guidance, PDUFA/CRL claims, partnerships, M&A | Publish versioned document/span adapter; reuse owner archive |
| Capital capability expansion | cash/runway/dilution/IPO/lockup | Capital Structure owner must expose verified capabilities; Bio cannot infer them |
| Terminal/Supabase tenant state | saved cohorts, watches, alerts, portfolio news | Publish tenant-scoped product adapter |
| Drugs@FDA/openFDA rights | regulatory dossiers, labels, safety, shortages | Record source-specific rights/retention/projection decision, then arm separate lanes |
| Market/options PIT rights | event studies, implied move, movers, EV scenarios | Publish rights-reviewed sessions/options/corporate-action adapter |
| Licensed analyst estimates | ratings/targets/expectations | Commercial license and redistribution/training contract, or remain unavailable |

These are the highest-leverage moves. A next session should not fake progress by
creating BioCatalyst-owned issuer maps, quote stores, document archives, or user
databases around absent owner contracts.

### Priority 3 — earn forward intelligence

After eligible point-in-time inputs exist:

1. extend the single operational ledger with `O1b` feature snapshots,
   forecasts, outcomes, model registrations, evaluation manifests and
   contribution traces;
2. accrue each outcome family prospectively under its own frozen policy;
3. build transparent timing/progression/comparable baselines with cohort,
   censoring, sample, uncertainty and calibration evidence;
4. add market-reaction and financing/EV scenario branches only after exact
   `C1 + C2 + MKT0` dependency receipts exist;
5. run preregistered challengers in shadow only;
6. operate one deterministic BioCatalyst packet producer and one allowlisted
   Neural Web reader; and
7. give Prophet post-selection facts context and shadow contribution traces
   only after PIT identity is eligible.

Prophet P3 authority is a separate future governance decision. The first
possible authority is shrink-only — cap or abstain — and requires matured
forward evidence, calibration/stability proof, A5 review and a fresh operator
ruling. It is not an ordinary completion item.

## 5. Final envisioned product

### 5.1 What it should contain

The final BioCatalyst is one temporal evidence and research suite, not a set of
disconnected biotech pages:

1. **Catalyst Radar** — source-reported upcoming constraints and fresh changes,
   with no hidden probability or trade stance.
2. **Explorer** — bounded, inspectable filters across eligible trials,
   companies, assets, indications, regulatory records and catalysts.
3. **Dossiers** — company, asset × indication, trial and regulatory views with
   point-in-time/as-known selectors, contradictions and missing dependencies.
4. **Change Tape** — exact revisions, corrections and evidence chronology.
5. **Research Workbench** — explicit peer matrices, pinned evidence and a
   governed Research Tray.
6. **Alerts** — correction-aware, tenant-scoped watches that explain why a user
   received an event.
7. **Data / API** — visible source coverage, freshness, field semantics,
   entitlements, export policy and stable API versions.

Behind these surfaces is one typed temporal graph linking company/issuer,
sponsor, asset, target, indication, trial, application/submission, regulator
event, patent/exclusivity, partnership, financing event and security — but only
through eligible point-in-time evidence. Every edge carries effective time,
known time, source, evidence locator, correction lineage, review state and
authority ceiling.

### 5.2 What it should look and feel like

The design target is an operator cockpit with an **epistemic envelope**:

- a narrow seven-surface left rail;
- a top command line for search, as-known mode, completeness and Research Tray;
- one focused main canvas instead of dense competing cards;
- a persistent desktop **Evidence Thread**, tablet drawer, and mobile bottom
  sheet containing source class, record/version locator, known-at/effective
  time and correction links;
- a small **Research Tray** whose canonical state lives in the product plane;
- deep-observatory dark mode with graphite structure, warm bone text and mint
  for source-backed movement;
- separately composed warm-quartz light mode with navy text and forest source
  accents;
- violet only for explicitly model-labelled material, never as a confidence
  trick;
- amber/red for caution and error, not sentiment;
- native desktop/tablet/mobile layouts, English/Chinese copy, keyboard/screen
  reader support and reduced-motion information parity; and
- progressive disclosure: glanceable answer → inspectable rationale → exact
  source evidence.

Every rich-value surface visibly carries five cues: fact class, time,
provenance, completeness and authority. An unavailable dependency is a
first-class state, not a zero, blank panel, hidden tab or infinite loading
shimmer.

The final suite should let an analyst move from an upcoming catalyst to the
exact source record, historical corrections, comparable trials, regulator and
corporate evidence, financing dependency, saved watch and later transparent
scenario distribution without losing the original query or as-known context.
It should feel calmer and more trustworthy than benchmark products, not merely
contain more fields.

### 5.3 What the final product must never become

- a visual clone of BioPharmCatalyst;
- a second Company, Corporate, Capital, Terminal, News, market-data or user
  truth plane;
- an inferred sponsor/ticker/issuer identity engine;
- a calendar that labels every registry date a market catalyst;
- a web-scraped probability or analyst-estimate product without rights;
- an LLM-originated evidence or signal plane;
- a collection of headline scores multiplied into fake expected value; or
- a way for BioCatalyst to add, reorder, promote or size Prophet candidates.

## 6. Absolute authority, provenance and research fences

- **Facts before joins. Joins before models. Models before shadows. Shadows
  before authority.**
- BioCatalyst is facts/context only today. No ranking, probability, score,
  sizing, escalation, candidate admission or trade call may originate here.
- `DNR:KILL-PHASE3-START-WEIGHT` remains live. Phase-3 START is display/context
  only; adverse/null evidence may not be sign-flipped or hidden.
- Sponsor-to-ticker context remains caller-supplied or operator-attested and
  post-selection. No inferred join may enter truth.
- The retrospective pre-2019 store is look-ahead selected and unusable for
  clean model evidence. Future claims require prospective, preregistered
  accrual.
- ClinicalTrials.gov records are sponsor/investigator submissions, not
  government validation of science, safety or outcomes.
- Current-state diffs do not prove protocol change, materiality, halt onset,
  site activation or enrollment velocity.
- Fixed-cohort membership is immutable, root-owned and exact. The fixed lane
  has no R2/publication/model authority.
- Raw/derived R2 evidence is dedicated private service data. Customer delivery
  remains through an allowlisted, pointer-bound server projection only.
- Corrections append or supersede; they never rewrite prior evidence.
- A backend does not move a parity row to implemented until an eligible source
  and user-reachable surface both exist.
- No launch or closed-beta claim may use backfill, denominator deletion,
  pre-window substitution, weighted rescue, or post-hoc maintenance exclusion.

## 7. Production/account transfer

### 7.1 Non-secret locations

| Item | Value |
|---|---|
| SSH host | `root@146.190.142.17` |
| Local SSH key | `~/.ssh/macro_dashboard_deploy_v2` |
| Production repository | `/opt/macro` |
| Main BioCatalyst runtime | `/opt/macro-biocatalyst/current` |
| Main state | `/var/lib/macro-biocatalyst/state` |
| Public projection | `/var/lib/macro-biocatalyst/public` |
| Fixed-cohort runtime | `/opt/macro-biocatalyst-fixed-cohort/current` |
| Fixed-cohort state | `/var/lib/macro-biocatalyst-fixed-cohort` |
| Fixed-cohort manifests | `/etc/macro-biocatalyst-fixed-cohort` |
| Root environment | `/etc/macro-biocatalyst.env`, `root:root`, mode `0600` |
| Contact address | `biocatalyst@mastermind-x.com` |
| User agent | `MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)` |

Credential values are present and have working receipts, but must never be
copied into a handoff, issue, PR, shell transcript or test fixture.

Non-secret runtime state at transfer:

- `BIOCATALYST_ENABLED=1`;
- the shared environment contains `BIOCATALYST_HISTORY_ENABLED=1`, while the
  service process prefixes enforce hourly=0 and daily-history=1;
- `BIOCATALYST_PROSPECTIVE_ENABLED=0`;
- `BIOCATALYST_CANARY_NCTS` contains four sorted explicit NCT IDs;
- R2 endpoint, bucket and access credentials are present;
- fixed-cohort transport is enabled, with membership held only in root-owned
  immutable manifests; and
- the separate activation-heartbeat timer remains disabled while prospective
  source collection remains off.

### 7.2 Minimum live checks

```bash
curl -fsS https://www.mastermind-x.com/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' \
  'https://www.mastermind-x.com/biocatalyst.html?field=primary_completion&window=90'

ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
systemctl is-enabled \
  macro-biocatalyst.timer \
  macro-biocatalyst-history.timer \
  macro-biocatalyst-fixed-cohort.timer
systemctl is-active \
  macro-biocatalyst.timer \
  macro-biocatalyst-history.timer \
  macro-biocatalyst-fixed-cohort.timer
systemctl show macro-biocatalyst.service \
  -p ActiveState -p SubState -p Result -p ExecMainStatus
journalctl -u macro-biocatalyst.service --since '2026-08-12 02:00:00 UTC' --no-pager
journalctl -u macro-biocatalyst-history.service --since '2026-08-12 00:00:00 UTC' --no-pager
journalctl -u macro-biocatalyst-fixed-cohort.service --since '2026-08-12 00:00:00 UTC' --no-pager
```

Then verify, rather than assume:

- exactly one current-record start and completion per frozen hourly opening;
- completion no later than opening + 900 seconds;
- success run ID and immutable committed generation;
- public `current.json` and `health.json` bind the same generation;
- 4 configured / 4 observed and no bounded error code;
- a valid mirror receipt with unique object keys, positive byte counts and
  lowercase 64-character SHA-256 values;
- each daily-history success has 381 objects and 366 history objects, or an
  explicitly explained new exact count;
- each scheduled fixed-cohort receipt is complete and exact 4/4; and
- all denominator opportunities remain present, including failures and
  upstream outages.

Do not call an `activating` oneshot complete. Wait for `inactive/dead`, then
check the generation and receipt.

## 8. Canonical files for the next session

Read these in this order:

1. `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md` — current state and
   next actions;
2. `config/biocatalyst_launch_slo_manifest.yml` — frozen 14-day source policy;
3. `docs/BIOCATALYST_LAUNCH_SLO_OFFLINE_VERIFIER.md` and
   `engine/sector_intelligence/launch_slo_verifier.py` — final evidence rules;
4. `config/biocatalyst_closed_beta_source_manifest.yml` — six-family launch
   denominator and honest unavailable states;
5. `research/BIOCATALYST_PARITY_LEDGER_2026-08-06.md` — 32-row benchmark truth;
6. `config/biocatalyst_product_acceptance_v2.yml` and
   `research/BIOCATALYST_D0A_IA_STATE_CONTENT_CONTRACT.md` — final product and
   browser-acceptance contract;
7. `research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md`
   — long-form dependency/wave map;
8. `docs/biocatalyst_operations_runbook.md` — source, runtime, incident,
   replay, R2 and activation behavior;
9. `config/biocatalyst_sources.yml`, `config/sector_intelligence_ownership.yml`
   and `data/biocatalyst/fixtures/shared_plane_read_adapters.v1.json` — source
   rights and adjacent-owner eligibility; and
10. `app/biocatalyst.py`, `templates/biocatalyst.*`,
    `scripts/biocatalyst_worker.py`, `collectors/biocatalyst/**` and
    `engine/biocatalyst/**` — implementation.

## 9. Next-session opening checklist

1. Fetch `origin/main`; work from a fresh task branch/worktree. The shared
   checkout is dirty and must not be cleaned or repurposed.
2. Re-query open PRs and the Active Build Map before touching shared CI,
   deployment, access, navigation, Capital, Corporate, Neural Web or Prophet
   paths.
3. Re-run the production denominator/timer/receipt check from the frozen start.
4. Confirm whether current time is before or after
   `2026-08-26T02:00:00Z`.
5. Before the close: monitor, settle freshness semantics, build non-authorizing
   evidence assembly tooling, and prove the signed-in page.
6. At/after the close: build the real 336-row evidence set, drills and CI
   artifact; run the offline verifier; record pass or failure honestly.
7. Do not update the closed-beta manifest beyond what the six-family
   denominator supports.
8. Ship every tracked change through branch → PR → squash merge →
   `origin/main` ancestry → production checkout/health → changed live surface.
9. Pause the `biocatalyst-b1s2c-soak-monitor` automation only after the launch
   evidence is genuinely settled and the authorized live loop is complete, or
   after a genuine external blocker has been reported.

## 10. Paste-ready continuation prompt

> Continue BioCatalyst from
> `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md`. Treat it as the current
> state, the August 6 remaining-waves document as the long-form dependency map,
> and the August 10/12 handoffs as historical evidence.
>
> First fetch fresh `origin/main`, re-query open BioCatalyst PRs, and verify
> production from the immutable `2026-08-12T02:00:00Z` denominator. Preserve
> all failures and all Prophet, Neural Web, PIT, provenance, entitlement,
> rights and zero-authority fences.
>
> The transport record was 81/81 hourly, 4/4 history and 3/3 scheduled fixed
> cohort at `2026-08-15T10:10:43Z`, but do not infer launch-SLO pass from that.
> Resolve the frozen freshness-clock conflict first: literal `/version
> dataTimestamp` age was red while transaction `last_success_at` age was green.
> Do not change the scheduled threshold or policy after observing the result.
>
> If before `2026-08-26T02:00:00Z`, continue failure-only monitoring, build
> non-authorizing real-evidence assembly tooling, and capture an authenticated
> post-`#5710` browser proof. If at or after the close, build exactly 336
> opportunity rows plus real correction-replay, rollback/restore, telemetry-
> generation and CI artifacts; run
> `verify_biocatalyst_launch_slo_evidence(...)`; record failure honestly or
> ship the verified successor through PR, merge, deploy and live proof.
>
> A B1 soak pass does not make closed beta ready: the committed denominator has
> only 2/6 mandatory families available and functional parity is 8/32. Do not
> fake identity, source rights, documents, market data, tenant state, models or
> authority around those blockers.

The operating maxim remains:

> **Facts before joins. Joins before models. Models before shadows. Shadows
> before authority. All of it should feel effortless in the product.**
