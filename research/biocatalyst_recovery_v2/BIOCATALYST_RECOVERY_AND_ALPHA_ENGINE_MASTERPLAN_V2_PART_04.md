- canonical v3 order;
- v3 + Bio shadow order;
- rank delta per candidate;
- Bio member values and family contributions;
- availability/null reasons;
- source snapshot digests;
- catalyst horizon;
- eventual forward outcomes;
- whether the Bio contribution was redundant with an existing family.

This makes “BioCatalyst improves Prophet” a measurable claim rather than a dashboard impression.

---

## K. Paste-ready P0 Codex prompt — version 2

> **BIOCATALYST P0 RECOVERY ONLY. DO NOT START PARITY OR ALPHA WORK IN THIS SESSION.**
>
> Work in `mastermindx-market-intelligence/macro` from a fresh branch/worktree created from current `origin/main`. The repository is moving rapidly; do not use the SHA in an older handoff as your base. Query current open PRs before editing.
>
> Read first:
>
> 1. `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md`
> 2. `app/biocatalyst.py`
> 3. `templates/biocatalyst.js`
> 4. `templates/biocatalyst.html.j2`
> 5. `templates/theme.js`
> 6. `lib/site_assets.py`
> 7. `scripts/build_biocatalyst.py`
> 8. `scripts/biocatalyst_browser_verifier.py`
> 9. `tests/test_biocatalyst_api.py`
> 10. `tests/test_biocatalyst_page.py`
> 11. `tests/test_biocatalyst_d0b_ui.py`
> 12. `app/deploy/macro-api.service`
>
> **Known evidence before you start:**
>
> - The shell/assets were opened correctly by #5710; private APIs remain `site_full`.
> - The handoff never proved a signed-in entitled browser could hydrate real rows.
> - The screenshots show `Registry page unavailable`, NOT the dedicated locked state.
> - In the current client, only 401/402/403 go to locked. Generic unavailable therefore points first to 503, client contract failure after 200, network/content-type/parse error, 500, or an edge mutation of auth status.
> - `app/biocatalyst.py::_read_bundle()` maps public-projection read/validation failure to generic 503 for all modes.
> - `templates/biocatalyst.js::withAuth()` silently catches every auth/session error and proceeds without Authorization. Fix that, but do not assume it is the incident root cause until status evidence says so.
> - Client `validate*Envelope()` failures are currently allowed to fall into the same generic unavailable painter as a source outage. A 200 contract mismatch can therefore masquerade as registry downtime.
> - Existing API tests override `require_site_full_user`; existing D0b tests are source-level; the existing Playwright verifier tests design/accessibility rather than entitled data. The end-to-end hydration altitude is missing.
> - The B1S2c source soak remains open until 2026-08-26T02:00:00Z. Do not change worker cadence, source roster, freshness budget, launch denominator, fixed cohort, or frozen source policy as part of this serving repair.
>
> **Phase 1 — collect evidence before editing:**
>
> A. Record current `origin/main`, production `/opt/macro` checkout, `/api/health` checkout, served page/CSS/JS/theme asset hashes, and active BioCatalyst generation.
>
> B. Verify anonymous `/api/biocatalyst/v1/health` is 401.
>
> C. With a real entitled bearer supplied interactively and never logged, call `/api/biocatalyst/v1/health` against `127.0.0.1:8000` and the public domain. Record status/content-type/safe body shape only.
>
> D. If 503, inspect `journalctl -u macro-api` and directly run `PublicGenerationPublisher('/var/lib/macro-biocatalyst/public').read_trial_projection()` using `/opt/macro-api/.venv/bin/python`. Preserve the exact error code. Do not mutate evidence files.
>
> E. If both API calls are 200, capture the browser network and the first client validation/parse exception. Prove which `validate*Envelope` fails and why.
>
> F. If auth fails, verify served `theme.js` has live `SUPABASE_CFG`, `MDXAuth.client()` resolves, `getSession()` returns a session, the bearer is actually attached, and `enforce_site_full` accepts it.
>
> **STOP after Phase 1 and write a 1-page evidence table before coding. The table must name the first failing layer.**
>
> **Phase 2 — smallest repair only:**
>
> - Preserve all fail-closed evidence validators.
> - Stop silent auth downgrade; no auth/bootstrap failure may become an anonymous request silently.
> - Add typed client errors for auth/network/http/content-type/json/contract.
> - A client/API contract mismatch must paint `integrity_block`, not `source_outage`.
> - Add bounded public-safe server error code + request correlation while preserving 503 and private headers.
> - Do not make the API public, bypass `site_full`, inline trial data into the shell, weaken a schema, convert an invalid payload to empty, or change source/soak policy.
>
> **Phase 3 — prove the actual user journey:**
>
> Build a separate entitled hydration verifier (do not repurpose the D0b design verifier) and prove:
>
> - auth session restores;
> - health 200;
> - Milestones real rows;
> - Trial Screen real rows;
> - Change Tape real rows for the known history cohort;
> - First-seen truthful coverage state/rows;
> - exact Peer Matrix cohort;
> - dossier opens;
> - source link valid;
> - private/no-store headers;
> - anonymous control locked;
> - zero page errors/unexpected console errors;
> - receipt binds served asset hashes + active generation.
>
> **Definition of done:** a signed-in entitled production-equivalent browser shows real, validated records from the deployed generation, and failure classes are distinguishable. “Tests passed,” “page 200,” “worker success,” and “static screenshot looks good” are explicitly NOT completion.
>
> Open small PRs. Include the evidence table, before/after screenshot, sanitized network summary, focused tests, asset/generation identity, and rollback. After each merged PR, verify the changed live surface before continuing.

---

## 1. Executive decision

The project should **not be discarded**, but the current product direction should be **stopped and re-chartered immediately**.

The codebase contains a surprisingly serious evidence and temporal-data substrate:

- bounded ClinicalTrials.gov collection;
- point-in-time and correction-lineage contracts;
- immutable generations and atomic publication;
- R2 mirroring and receipts;
- current, historical, and first-seen trial records;
- a private read API;
- a fixed-cohort collection lane;
- a forward outcome ledger;
- sponsor-to-ticker review machinery;
- source health, SLO, and acceptance contracts;
- five narrow trial-research modes.

That work is valuable and expensive to reproduce correctly.

However, the thing a paying user sees is not remotely close to the intended product. It is a fragile, mostly blank, single-page ClinicalTrials.gov workbench. It is neither a practical BioPharmCatalyst-style platform nor an investment-intelligence lobe. The recent handoff did not repair that mismatch. PR #5749 was a documentation-only handoff. PR #5710 fixed public delivery of the shell assets but did not prove authenticated payload hydration.

The correct strategy is therefore:

> **Preserve the evidence spine. Replace the product shell, feature roadmap, and authority model. Build functional parity in modular surfaces. Build the alpha engine as a separate, point-in-time feature and research plane. Integrate it into Prophet only through a bounded evidence-family contribution after shadow validation.**

The immediate goal is not another architecture document or another hundred unit tests. The immediate goal is a signed-in production browser showing real records, with the exact failure state visible when it cannot.

---

## 2. What the last session actually accomplished

### 2.1 The final handoff was not a product fix

PR #5749, merged as `c7d00d12a3cc1e5ebcc409b6e125537e704b81a2`, changed only handoff documentation. It did not modify the API, frontend, collector, deployment, or data contracts.

Its useful contribution was to record:

- the actual runtime layout;
- current production run counters;
- source-coverage limits;
- the open prospective soak;
- the missing authenticated browser proof;
- the freshness-clock contradiction;
- the current parity count;
- the intended seven-surface product direction.

That is useful as an inventory. It is not evidence that the product was fixed.

### 2.2 The last code fix repaired only the static shell boundary

PR #5710, merged as `50a47d036f6d6bf14d13caf9b9512c207f09e5a7`, moved the BioCatalyst page, CSS, and JavaScript into the public edge allowlist while keeping the private API behind `site_full`.

That explains the current production symptom precisely:

- the shell renders;
- the layout and controls appear;
- the private data still fails to hydrate;
- the browser falls into generic unavailable states.

The PR solved “the workbench assets themselves return 401.” It did not solve “a signed-in entitled user can successfully load non-empty private records.”

### 2.3 The substantive work exists, but it is narrow

The substantive implementation came from many earlier PRs and includes:

- normalized trial intelligence API and workbench;
- trial history and evidence receipts;
- milestone monitor;
- registry change tape;
- first-seen tape;
- trial screen and facets;
- explicit peer cohorts;
- exact before/after change values;
- current and history workers;
- source soak and fixed cohort;
- temporal operating packets;
- forward record store;
- source and authority contracts.

This is a **ClinicalTrials.gov temporal evidence platform**. It is not yet a BioPharmCatalyst-equivalent application.

### 2.4 The success metrics were operational, not product metrics

The handoff’s “81/81 hourly opportunities,” “4/4 history runs,” and “3/3 fixed-cohort runs” are useful operational run counters. They do not demonstrate:

- breadth of company or asset coverage;
- non-empty browser rendering;
- successful entitlement propagation;
- successful user-facing API hydration;
- parity with the target platform;
- a working investment signal;
- a validated relationship to future returns.

A timer can execute successfully while the customer-facing product remains empty. That is what the screenshots indicate.

---

## 3. Current-state scorecard

| Plane | Current state | Assessment |
|---|---|---|
| Evidence provenance | Strong | The best part of the project. Preserve it. |
| Clinical trial temporal history | Strong but narrow | Useful foundation for trial revision and first-seen research. |
| Collection operations | Partially proven | Current and history lanes have run, but breadth and long-run reliability remain limited. |
| Source-family coverage | Weak | Only 2 of 6 mandatory closed-beta source families are available. |
| Entity resolution | Partial and highly constrained | Reviewed sponsor mapping exists, but company/security/asset/indication graph is incomplete. |
| Public product shell | Loads | Static asset boundary was fixed. |
| Authenticated data hydration | Not production-proven | The exact missing proof named by the handoff. Current screenshots show failure. |
| Product information architecture | Inadequate | Five modes in one three-column workbench cannot carry the target estate. |
| Functional parity | Very low | Internal ledger says 8/32, but only four rows are genuinely implemented product jobs. |
| Market and company intelligence | Mostly absent | No practical stock dashboard, company estate, movers, capital, or rich calendar. |
| Options and flow | Absent from BioCatalyst | Powerful estate exists elsewhere in Macro/Terminal but is not joined here. |
| Outcome and timing models | Contract/shadow stage | Not authorized as a live investment signal. |
| Asymmetry/dislocation model | Unbuilt | This is the new core lobe work. |
| Prophet integration | Deliberately prohibited by old charter | Must be re-authorized explicitly before implementation. |
| User value today | Low | A sophisticated backend hidden behind a broken and incomplete product. |

---

## 4. Why the production page is blank

### 4.1 The evidence points to one shared hydration failure

The five modes do not represent five independent applications. They share:

