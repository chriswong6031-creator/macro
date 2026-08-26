# DEFENSE D6-B1 — Coverage-Aware FMS Implementation Spec (FROZEN, 2026-08-25)

Authority chain: Chairman D6-B launch intent 2026-08-25 → protected Skillpack
`Mastermind@51f9942733b86e550bb9169d2a43462bd28e774f` → Sol authorization macro #6404
comment 5416302430 (U1–U5 rulings, EN/ZH vocabulary, T1–T14) → D6-B0 freeze
`DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md` (blob
`4ed41deca82c`, verified unchanged at claim) → `DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL`
(blob `71adba5e88c9`) → U4 hold return (PR #6420, merge `bdc2b08d3da9`) → **D6-B1
coverage-aware continuation commission (Chairman channel, in-session relay 2026-08-25;
text preserved in the D6-B1 continuation handoff)**, which released the U4 hold and
replaced the web-surface population assumption with the official-union coverage law.
Everything in the D6-B0 freeze stands EXCEPT where §2 below records the D6-B1 delta.
This spec is the builder's frozen packet: builders make zero source, identity, stage,
amount, correction, ownership, consumer, canary, or failure-state decisions.

## §0 Acceptance gates (the wave is NOT DONE unless…)

1. All D6-B0 freeze §0 gates 1–10 hold (source boundary, identity, stage honesty,
   amount honesty, correction plane, no duplicate planes, consumer proven, hostile
   canary, kill tests, production proof) — as amended by §2 below.
2. The official-union population law is implemented: FR bounded denominator/recovery +
   State current presentation observations + DSCA historical observations →
   transmittal-number dedupe → one case per transmittal → explicit source/coverage
   manifest in the read model.
3. Hostile cases all pass (§11): 26-23 canonical despite State/DSCA web absence;
   26-28 present despite State corpus omission; 26-27 positive web/official case with
   FR join `official_notification_date = 2026-03-10`; duplicate copy across source
   families produces ONE transmittal case; FR publication lag never rewrites
   congressional-delivery time; a missing web page never becomes `empty_valid`; a
   zero/unreconciled official denominator can never pass publication silently.
4. Kill tests T1–T14 (freeze §16) + the D6-B1 battery (§11) are merge-binding and
   fail under mutation.
5. Page fence: `site/government_revenue.html` ≤ 303,104 bytes total (current main:
   274,138 → 28,966 free) and the FMS shell delta ≤ 8,192 bytes. Bake locally via
   `scripts/build_government_revenue.py` before pushing template edits.
6. EN/ZH production vocabulary is EXACTLY the U5 frozen table (§9.3). Typography may
   change; meaning may not. No raw internal state tokens front-facing.
7. Anonymous boundary intact: `/api/government-revenue/fms-*` and the site twin
   401/locked anonymously; HTML leaks no case bodies.
8. Production proof through the real lane (§12): merge → fms acquisition lane → the
   `government-revenue-live` publication lane → live API + served twin + rendered
   EN/ZH UI + hostile 26-13 stage-hold. Merge/green CI is not acceptance.

## §1 Claim-time census pins (2026-08-25)

- Recovery-clone carrier `~/.claude-recovery/macro-d6b1` (primary local clone git
  object reads kernel-blocked by iCloud-evicted packs), branch
  `claude/d6b1-fms-coverage-vertical-20260825` off origin/main `43bfd1817656`.
- Freeze blob `4ed41deca82c…` + DEC blob `71adba5e88c9…` verified byte-identical.
- Planning census artifact:
  `research/defense_intelligence/evidence/fms_d6b1_full_scope_census_2026-08-25.json`
  (FR full-scope denominator, State corpus receipts, DSCA browser manifest,
  reconciliation). All planning fetches receipted sha256; DSCA/media bytes acquired
  through the bounded Browser-pane lane (in-page fetch + crypto.subtle sha256 +
  clipboard bridge) with in-page/on-disk sha equality verified; 26-13 article sha
  `d53b9e97…cecc6b` and PDF sha `c7e3bcad…af9c55` match the B0-freeze receipts R2/R3
  exactly; 25-105 article sha `f3981f7c…` matches the U4 receipt.

## §2 D6-B1 population law (the ONLY delta to the D6-B0 freeze)

- **Scope**: cases whose population clock falls in 2026-01-01 → 2026-08-25 inclusive
  (claim-time). Population clock = FR `Date Report Delivered to Congress` when FR
  evidence exists, else the DSCA body dateline (DSCA-era), else the State article
  header date. Nothing outside the window is built in v1.
- **Population = official union**, deduped by exact normalized transmittal (freeze §6
  grammar unchanged):
  1. **Federal Register — bounded denominator AND recovery source.** All
     Defense-Department "Arms Sales Notification" NOTICE documents published
     2026-01-01→claim date (API `conditions[term]="arms sales notification"`,
     `agencies[]=defense-department`, `type[]=NOTICE`). Original 36(b)(1)
     certifications carry a bracket-header transmittal matching `^\d{2}-\d{1,3}$`.
     **Amendment/modification notices (letter-suffixed brackets: `26-0G`, `0M-25`) are
     excluded from the denominator with a recorded reason and NEVER mint or touch a
     case in v1** (the phantom `26-0` trap). Correction notices (title/ACTION carries
     "Correction"; no delivered-date line) attach as correction observations to an
     existing in-scope case by exact transmittal, never mint, never enter the
     denominator. **AMENDED vs D6-B0/U3: an in-scope original 36(b)(1) FR document
     whose transmittal matches no State/DSCA observation now MINTS a recovery case**
     (this is the D6-B1 ruling; U4 proved 10 such certifications exist). FR still
     never advances stage, and FR publication date never becomes any case clock.
  2. **State PM-Bureau — current presentation observations** (freeze §3.1 unchanged):
     the listing + qualifying articles (predicate: listing entry labeled "FOREIGN
     MILITARY SALES: CONGRESSIONAL NOTIFICATION"). CLI transport, D6-A fetch
     discipline.
  3. **DSCA — historical observations, bounded to the scope window** (freeze §3.2/§3.4
     mechanics unchanged): the 14 in-scope articles (Jan-8→Feb-6 2026) + the 26-13
     certification PDF, acquired ONCE via the browser-transport archival path and
     committed as staged bytes (§3); the acquisition lane replays staged bytes into R2
     with strict readback. **No pre-2026 DSCA archive backfill** (Sol U2 boundary
     unchanged); the coverage manifest must disclose this exactly.
- **Case classifications** (per-case `source_coverage.classification`):
  `dsca_and_fr` | `state_and_fr` | `fr_only` | `state_only` | `dsca_only` |
  `state_fallback`. `web_presence: false` exactly when no State/DSCA observation
  exists (the `fr_only` class).
- **Expected v1 corpus (census 2026-08-25, deterministic scripts, receipts in §1
  artifact)**: 70 cases = 15 DSCA-era FR transmittals (14 `dsca_and_fr` + 26-3
  `fr_only`) + 42 State-era FR transmittals (33 `state_and_fr` + 9 `fr_only`:
  26-21, 26-23, 26-24, 26-28, 26-29, 26-32, 26-38, 26-41, 26-49) + 12 `state_only`
  (FR lag tail: 26-59, 26-61, 26-65, 26-66, 26-70, 26-76, 26-78, 26-80, 26-82,
  26-83, 26-85, 26-92) + 1 `state_fallback`
  (`singapore-hellfire-missiles`, genuinely no transmittal label → fallback identity
  `fms:urlpath:<sha256(path)[:24]>`). Live-run counts may drift as sources post; the
  reconciliation gate (§7) is the invariant, not these exact numbers.
- **Fallback↔recovery collision law** (freeze §6 fallback split-risk, applied):
  when an `fr_only` recovery case and a fallback-identity web case share the same
  `customer_country`, BOTH cases are flagged `case_identity_state: conflicted` for
  review; they are NEVER auto-merged (transmittal similarity/country+capability can
  not join them; only a later reviewed supersession act may). Census instance:
  FR 26-24 (Singapore) ↔ `singapore-hellfire-missiles`.

## §3 Data architecture (mirror the D6-A dod_budget triad exactly)

Collector-owned append-only planes (`collectors/fms_notifications.py`):
- `data/government_revenue/fms_collection_receipts.jsonl` — one row per production
  fetch/replay: D6-A receipt fields verbatim (`receipt_id`, `observed_at`,
  `publisher`, `source_url`, `final_url`, `response_sha256`, `bytes`, `http_status`,
  `content_type`, `transport` (`cli` | `browser_in_page_fetch_staged`),
  `extractor_version`, `parser_version`, `r2_object_key` | null).
- `data/government_revenue/fms_observations.jsonl` — append-only case observations:
  `observation_id`, `case_key`, `source_surface` (`state` | `dsca` |
  `federal_register`), `kind` (`listing_article` | `certification_pdf` |
  `fr_raw_text` | `fr_correction` | `retraction_observed`), `version` (per
  case+surface+url, 1-based), `known_at` (= receipt `observed_at`), receipt ref,
  verbatim extracted fields (§5). Same URL + same bytes ⇒ receipted no-op (no new
  observation). Same case + changed bytes ⇒ append version N+1; predecessors
  immutable.
- `data/government_revenue/fms_projection_state.json` — projection/idempotence state.
- `data/government_revenue/fms_staged_objects/` — the committed browser-acquired DSCA
  bytes: 14 article HTML files + `saudi-arabia-26-13-cn.pdf` + `manifest.json`
  (browser receipts incl. in-page shas). The lane replays these into R2 and refuses
  any staged file whose bytes do not match its manifest sha256.

R2 immutable store (production lane only; creds are lane secrets): key prefix
`government-revenue/fms/sha256/<sha256>.<html|pdf|txt>`; put → bounded strict
readback → byte+sha equality, refusing on any mismatch (mirror
`collectors/dod_budget_live.py::put_and_verify_pdf`, generalized for html/txt with
content-type checks and size caps; PDF requires `%PDF` magic).

Read model (built by `engine/government_revenue/fms_cases.py` from the triad,
deterministic, no network): `data/government_revenue/fms_case_graph.json`; site twin
`site/government-revenue-data/fms-cases.json` written by
`scripts/build_government_revenue.py` (`_write_fms_case_twins`, mirroring
`_write_budget_program_graph_twins` at :855, wired into `build()` and
`build_site_only()`), published exclusively by the `government-revenue-live` lane.

## §4 Contract — `contracts/government_revenue/government_fms_case.v1.schema.json`

Top level (mirror `government_budget_program_graph.v1` conventions):
`contract: "government_fms_case.v1"`, `schema_version: "1.0.0"`,
`content_id: ^grfms1-[a-f0-9]{24}$` (deterministic hash of canonical body),
`as_of`, `known_at`, `authority` (copy the budget graph display-tier authority block
verbatim: all-false capabilities, `context_only: true`, `tier: "display"`),
`scope {delivered_from, delivered_through}`, `coverage` (§7), `cases[]`,
`limitations[]`.

Case object (freeze §10 shape, plus D6-B1 coverage fields):
- `case_key` (`^fms:(transmittal:\d{2}-\d{1,3}|urlpath:[a-f0-9]{24})$`),
  `transmittal_number` | null, `identity_basis` (`transmittal` | `url_fallback`),
  `case_identity_state` (`resolved` | `identity_unresolved` | `conflicted`),
  `aliases[]`.
- `customer_country` (source-printed; for `fr_only` cases the FR "(i) Prospective
  Purchaser" verbatim), `capability_title` (verbatim web post title; **null for
  `fr_only` cases — never synthesized**), `source_item_enumeration` (verbatim; FR
  "(iii) Description…" text for FR-sourced cases) | null.
- `stage: "congressional_notification"` (const in v1), `later_stages:
  "stage_not_observed"`, `advancement_condition:
  "official_evidence_of_offered_accepted_or_implemented_loa"` (const), stage evidence
  receipt refs.
- `estimated_notification_value` (integer USD | null; **null never 0**), `currency:
  "USD"`, `source_caveat` (verbatim | null), `value_provenance`
  (`state_body` | `dsca_body` | `fr_total_estimated_value` | null). Precedence when
  multiple surfaces state a value: web body first (State for State-era, DSCA for
  DSCA-era), FR total otherwise; a material web↔FR disagreement ⇒ case `conflicted`,
  value null. **No cross-case aggregate anywhere** (T13).
- `contractors[]`: `{name_as_printed, location_as_printed | null, identity_state:
  "not_reviewed", issuer_ref: null}`; the "There is no principal contractor…"
  sentence ⇒ empty list + `contractor_note` verbatim; silent absence ⇒ empty list,
  note null. No ticker minting (T4).
- `program_links[]`: exactly one entry `{state: "not_reviewed", reason_code:
  "no_reviewed_program_link", program_id: null, program_case_link_id: null,
  ontology_graph_id: null}` (freeze §12; T5).
- `clocks`: `official_notification_date {value, provenance:
  "fr_delivered_to_congress" | "dsca_body_dateline" | null}`,
  `official_web_publication_date {value, provenance: "state_header_date" |
  "dsca_article_date" | null}`, `first_observed_at`. FR join sets
  `official_notification_date` with FR provenance (26-27 ⇒ `2026-03-10` from FR
  `2026-07237` / `91 FR 19115`); State-era cases without FR join keep null — never
  copied from the web date (Sol U3). **FR publication_date is never any clock.**
- `source_coverage`: `{classification (§2), surfaces[], web_presence: bool}`.
- `observations[]`: the per-case append-only history (projection of the observation
  plane rows: observation_id, source_surface, kind, version, source_url,
  response_sha256, bytes, transport, observed_at, known_at, r2_object_key | null).
- `case_state`: `current` | `corrected` | `conflicted` | `retraction_observed`.

## §5 Frozen parse grammars (deterministic; unknown layout fails closed to null +
typed parse state; no LLM origination anywhere)

Transmittal (all surfaces; freeze §6 verbatim):
`transmittal\s*(?:no\.?|number|num\.?|#)?\s*[:\-]?\s*(\d{2})\s*[-‐‑‒–—―]\s*(\d{1,3})`
case-insensitive on visible text; normalize `<yy>-<n>` (strip leading zeros of the
sequence); multiple distinct numbers in one notice ⇒ `conflicted`. FR bracket header:
`\[Transmittal No\.\s*([A-Z0-9-]+)\]` then classify `^(\d{2})-(\d{1,3})$` original
vs letter-suffixed amendment (exclude-with-reason).

State article (survey-proven on all 46 corpus articles, receipts in §1 artifact):
- title: `og:title` meta, verbatim.
- web publication date: header date `(January|…|December) D, YYYY` — first
  title-case date in the article header region (the survey's residual-zero grammar);
  anchor structurally, not by page-wide first match, if the header region is
  identifiable; fail closed to null.
- value (amended after full-corpus survey; five receipted sentence classes:
  "estimated total cost is", "estimated total cost is up to", "estimated total
  cost for the case is", "for an estimated cost of", "The estimated cost is",
  "The total estimated cost is"):
  `(?:total\s+)?estimated\s+(?:total\s+)?(?:program\s+)?cost\s+(?:for\s+the\s+case\s+)?(?:is|of)\s+(?:up\s+to\s+)?\$([\d,.]+)\s*(billion|million)`
  → integer USD; 46/46 census articles carry exactly one value under this
  grammar. Genuinely absent ⇒ null. Multiple distinct values ⇒ null +
  `conflicted`.
- title anchor (amended, implementation-frozen): the article `<h1>` verbatim on
  BOTH State and DSCA (og:title is receipt-proven truncated on DSCA and
  suffix-contaminated on State).
- `customer_country` (amended, implementation-frozen; precedence per field):
  (1) the verbatim segment of the `<h1>` title before its first dash separator
  (dash classes ` – ` / ` — ` / ` - ` and bare unicode-dash variants; the
  "Country – Capability" split is the sources' own printed format — 60/60
  census articles yield a non-null prefix); (2) the FR join's
  "(i) Prospective Purchaser" verbatim (always the source for `fr_only`
  cases); (3) the determination-sentence grammar; (4) null. A material
  disagreement between (1) and (2) trips the existing §6 mis-key/conflict
  guard — never silent field selection.
- contractor: `The principal contractors?(?: for this (?:effort|case))? (?:will be|is|are) <LIST>.`
  LIST split on `;` / `, and ` with per-entry `NAME(, located in PLACE)?` — verbatim
  capture, location null when absent (e.g. "Aero Vironment Inc."). Explicit-none:
  `There is no principal contractor associated with this (potential|proposed) sale`.
- determination sentence + `article:modified_time` captured as evidence.

DSCA article (survey-proven on all 14 staged articles):
- dateline `WASHINGTON,\s+(Month D, YYYY)` (day may be zero-padded) — seeds
  `official_notification_date` with `dsca_body_dateline` provenance (freeze §7).
- value `estimated cost of \$X million|billion`; caveat paragraph ("highest
  estimated quantity…") verbatim as `source_caveat` (present on 14/14).
- article date from the article page header = `official_web_publication_date`.

FR raw text (survey-proven on all 267 scanned docs):
- `(i) Prospective Purchaser: <X>`; `(ii) Total Estimated Value:` table (the annex
  label may interleave classification markings, e.g. `(ii) (U) Total Estimated
  Value:` — receipted variant FR 2026-09109) → the dotted-leader `TOTAL` row,
  grammar `TOTAL\.{2,}\s*\$\s*([\d,.]+)\s*(billion|million)` tolerant of leading
  artifacts on the line (receipted: a literal apostrophe precedes TOTAL in
  2026-09109), as `fr_total_estimated_value`; absent row ⇒ null, never guessed;
  `(iii) Description and Quantity…: <text>` verbatim; `(viii) Date Report Delivered
  to Congress: <Month D, YYYY>` → the delivered clock. Corrections: title/ACTION
  contains "Correction" ⇒ `fr_correction` observation attaching by exact transmittal
  to an existing case (never minting; the four census correction docs are all
  out-of-scope 2025 originals).

## §6 Unchanged laws (implement exactly; do not re-decide)

Freeze §4 stage law (v1 = `congressional_notification` only; zero review-period
arithmetic — Sol U1); §5 amount law; §6 identity law incl. mis-key guard; §7 clock
law; §8 correction law (idempotent same-bytes, append changed-bytes, retraction
observations, D6-A receipt fields, parser-version bump requires generation scoping
frozen first); §9 ownership (zero `government_procurement_event.v2` rows — T12); §11
contractor law; §12 program-link law; §13 consumer law; §14 two-plane failure states
(workspace freshness writes `ok/partial/stale/unavailable/blocked/failed/unknown`;
never ok-with-zero on failure). State listing/article fetch failure ⇒ typed
`source_unavailable`; never serve DSCA-era or cached data as current (T6).

## §7 Coverage manifest + reconciliation gate (D6-B1-new, read-model `coverage`)

```
coverage: {
  law: "official_union_v1",
  sources: {
    federal_register: {role: "denominator_and_recovery", publication_window: [lo, hi],
                       docs_scanned: N, originals: N, amendments_excluded: N,
                       corrections: N, status},
    state_pm_bureau:  {role: "current_presentation", listing_pages: N,
                       qualifying_articles: N, status},
    dsca_press:       {role: "historical_observations_bounded",
                       articles_staged: N, status,
                       disclosure: "In-scope 2026 articles + the 26-13 certification
                       PDF only; the pre-2026 DSCA archive is NOT covered."}
  },
  history_disclosure: <the pilot-only/pre-2026 sentence above>,
  reconciliation: {
    denominator_transmittals: N,        # in-scope FR originals
    cases_built: N,
    denominator_unbuilt: [],            # MUST be empty to publish
    web_only_cases: N,                  # state_only + fallback
    web_absent_cases: [transmittals]    # fr_only class, explicit
  }
}
```

**Publication gate (hostile case 7):** the read-model builder REFUSES to emit (typed
failure, freshness `failed`) when `denominator_transmittals == 0`, when any
denominator transmittal has no built case (`denominator_unbuilt` non-empty), or when
the FR source status is not ok — a zero or unreconciled denominator can never pass
silently. A State-fetch failure with FR ok still publishes FR/DSCA truth with
`state_pm_bureau.status: unavailable` and case-level staleness — never `empty_valid`,
never silent.

## §8 API (inside the existing entitled router `app/government_revenue.py`)

- `GET /api/government-revenue/fms-cases` → the read model (scrubbed via the
  router's `_scrub_public` conventions; contract-validated load mirroring
  `_load_budget_program_graph` at :436).
- `GET /api/government-revenue/fms-case/{case_key}` → one case; validate case_key
  against the §4 regex; 404 unknown; 422 malformed.
Both inherit `require_site_full_user` (router-wide dependency, :102). No new auth.

## §9 Ninth mode (design pinned here; Sonnet builder implements verbatim)

1. Tab: `<button class="mode-tab" … data-mode="fms">{{ t('FMS Congressional
   Notifications','FMS 国会通知') }}<span class="mode-count" id="countFms">—</span></button>`
   after the `companies` tab (`templates/government_revenue.html.j2:102`).
2. JS factory `createGovernmentRevenueFms` in
   `templates/government-revenue-dossiers.js` (binary-flagged file — edit with care,
   `grep -a`), mirroring `createGovernmentRevenueBudget` exactly: authenticated
   fetch of `fms-cases`, contract check (`government_fms_case.v1`, `1.0.0`,
   `^grfms1-[a-f0-9]{24}$`, `validAuthority`), queue rows
   `{id: 'fms:'+case_key, kind: 'fms_case', truth: 'official', truthCopy:
   tr('Official 36(b) congressional notification','36(b) 国会通知官方记录'), …,
   title: capability_title || customer_country, subtitle: transmittal + ' · ' +
   customer_country, date: known_at}`, count into `#countFms`.
3. Inspector sections (the seven §13.4 answers, budget-inspector visual idiom):
   hero (customer country + verbatim capability title + transmittal id + truth
   badges); stage card — `Notified to Congress — not a signed sale` /
   `已通知国会 — 尚非已签署军售` + `Later stage not observed` / `未观察到后续阶段`;
   amount card — `Estimated notification value` / `通知估算金额` + value (or null
   state) + `Proposed-sale estimate — not an award, backlog, or revenue` /
   `拟议军售估算 — 并非合同授予、订单积压或收入` + verbatim `source_caveat` when
   present; clocks card — official notification date (or `Official notification
   date unavailable` / `官方通知日期暂无`) + web publication date + known_at;
   linkage card — per contractor `Named in source — identity not reviewed` /
   `来源点名 — 身份未审核`, program `Program link not reviewed` / `项目关联未审核`;
   advancement card — `Requires official evidence of an offered, accepted, or
   implemented LOA` / `须有官方证据证明 LOA 已提出、接受或实施`; coverage note for
   `web_presence: false` cases (plain words: recovered from the Federal Register
   official record; no agency web post exists) + the history disclosure; evidence
   drawer listing observations/receipts (source, sha, dates, version chain).
4. Shell delta ≤ 8,192 bytes in the baked HTML; case bodies live only in the
   entitled JSON.
5. No cross-case totals anywhere in the mode (no sum chips, no pipeline figures).

## §10 Lanes

- `.github/workflows/fms-acquire.yml` — dispatch-only, mirror of
  `dod-budget-acquire.yml` byte-for-byte in structure: same runner labels, R2
  secrets, `concurrency group: government-revenue-live, cancel-in-progress: false`;
  runs `python -m collectors.fms_notifications acquire` (State listing+articles CLI
  fetch, FR API fetch, DSCA staged replay→R2, receipts+observations append,
  fms_case_graph build); commits ONLY the fms triad + graph files back to the
  dispatched ref with the same unexpected-diff refusal.
- `government-revenue-live.yml`: add the fms twin publication next to the budget
  twin (site twin write + freshness block; census the exact integration points —
  single-publisher law holds; NEVER cancel its runs).
- No schedule anywhere (Sol sets cadence later).

## §11 Merge-binding adversarial battery (`tests/test_fms_notifications.py` +
`tests/test_fms_ui.py`; wire into `.github/ci/legacy-jobs.yml` with
`run_ci_pack.py --validate-only` re-run)

Freeze T1–T14 verbatim, plus (D6-B1 + Sol acceptance list):
- B1: 26-23 fixture (FR 2026-07278 raw text) builds a canonical `fr_only` case,
  delivered `2026-02-26`, purchaser "Government of Jordan", value $280,000,000 from
  the FR Total row, `web_presence: false`, `capability_title: null`.
- B2: 26-28 (FR 2026-09109) same class; removing the State corpus cannot remove it.
- B3: 26-27 positive: State article fixture + FR 2026-07237 join ⇒ ONE case,
  `official_notification_date 2026-03-10` (FR provenance),
  `official_web_publication_date 2026-03-10` (State provenance), $930,000,000,
  contractor "Lockheed Martin, located in Grand Prairie, Texas" not_reviewed.
- B4: duplicate across families (26-13 DSCA article + FR original) ⇒ one case, two
  observations (T11 sharpened to three families).
- B5: FR lag: a case whose FR doc publishes months late keeps
  `official_notification_date` = the (viii) delivered date; asserting FR
  publication_date into any clock fails.
- B6: State fetch failure ⇒ typed `source_unavailable`/freshness `unavailable`,
  NEVER `empty_valid`/ok-with-zero; FR/DSCA truth still publishes with the State
  status disclosed (§7).
- B7: reconciliation gate: zero-doc FR sweep, or a denominator transmittal with no
  built case ⇒ builder refuses to publish (typed failure).
- B8: amendment notice (letter-suffix bracket fixture, e.g. 26-0G) neither mints nor
  modifies any case; FR correction doc appends `fr_correction` to an existing case
  only.
- B9: fallback↔recovery collision (26-24 ↔ singapore-hellfire fixtures) ⇒ both
  `conflicted`, two cases, no auto-merge.
- B10: staged-replay integrity: a staged DSCA file whose bytes mismatch its manifest
  sha is refused (no observation, no R2 put).
- B11: browser-staged strict readback: the R2 put path requires byte+sha equality
  readback (mock store; mutation of readback bytes fails).
- B12: EN/ZH copy: the U5 table strings are present verbatim in the mode template/JS;
  mutation of the stage negative or amount negative fails.
- B13: fence: baked page ≤ 303,104 and FMS shell delta ≤ 8,192.
- B14: anonymous 401/locked on both routes + site twin; no case bodies in HTML.

## §11b Post-red-team amendments (adjudicated 2026-08-26 after the independent
opus review; these are frozen law equal to the sections they amend)

1. **Paired plain-copy law**: `templates/government-revenue-dossiers.js` ships
   with its byte-matching `site/government-revenue-dossiers.js` twin in the
   same PR (`python -m scripts.check_template_site_sync --fix`). The rendered
   `site/government_revenue.html` page stays live-lane-owned and is NOT
   committed by the carrier.
2. **Evidence drawer**: the FMS inspector MUST emit the `data-fms-evidence`
   action button (mirror the budget inspector's actions block) so the
   receipts/observation-history drawer is reachable — journey step 6.
3. **Receipt idempotence**: acquisition receipts join observations under the
   same-URL-same-bytes idempotence law — a re-run against unchanged bytes
   appends ZERO receipt rows (timestamp-free duplicate predicate consulted
   before append, mirroring `dod_budget_live`); the acquire lane's no-op
   early-exit must be genuinely reachable, with a two-run test proving it.
4. **Population-clock window (§2) is enforced in the engine**: a case whose
   population clock falls outside [2026-01-01, as_of] is excluded from the
   graph; `scope.delivered_from/delivered_through` publish the POPULATION
   window, never the FR publication-query bounds (those stay in
   `coverage.sources.federal_register.publication_window`). State sweep
   page-cap exhaustion (a page limit reached while entries keep appearing) is
   a typed failure, never `ok`.
5. **Partial-failure law (freeze §14 `partial`)**: a per-article State fetch
   failure does not abort the sweep — remaining articles still acquire, the
   failure list is recorded, and `state_pm_bureau.status = "partial"` (with
   failed/succeeded counts) when the listing succeeded but ≥1 article failed.
   Total listing failure remains `unavailable`.
6. **`empty_valid` encoding (v1)**: the frozen predicate is encoded as
   `state_pm_bureau.status: "ok"` + `qualifying_articles: 0`, lawful ONLY when
   the listing fetch+parse succeeded; the display tier renders the plain-word
   empty state from it. `stale` / `rights_blocked` remain vocabulary homes with
   no lawful v1 emitter (no staleness clock is authorized until Sol sets an
   acquisition cadence; no rights block exists on these public sources).
7. **Freshness derivation**: `freshness.fms.status` = worst-of the FR and
   State source statuses mapped into the freshness vocabulary (never
   FR-alone); staleness/age logic stays out of v1 pending Sol's cadence.
8. **`multi_surface` classification**: `source_coverage.classification` gains
   the value `multi_surface` for any surface combination not named by the six
   §2 classes (e.g. a transition-window case observed on both webs plus FR);
   the `surfaces[]` array remains the exhaustive truth. Classification
   precedence must never drop an observed surface silently.
9. **Correction-to-amendment brackets**: an FR correction whose bracket fails
   the numeric original grammar (e.g. `26-1C`, `0M-25` family) is excluded
   with reason exactly like amendment notices — typed, no crash, `::error`/
   `::warning` annotations printed line-start with flush.
10. **`case_key_for_transmittal` normalizes** (leading-zero strip) before
    minting a key — `26-013` and `26-13` can never mint distinct identities.
11. **Graph `known_at`** = the latest observation `known_at` in the build
    (never null in a production build with observations).
12. **Fence measurement**: the UI fence test measures a freshly RENDERED page
    (template + current committed data), not the committed `site/` page.
13. Vacuous-test repairs: T6/T14 assert `state_pm_bureau.status` directly; the
    U5-mutation test must exercise the real check; a 422 malformed-case-key
    test runs authenticated; a case-graph-level mis-key conflict test exists.

## §12 Production-proof sequence (after merge)

1. Dispatch `fms-acquire.yml` on main (preflight the shared concurrency group; never
   cancel a live run). Lane: live State+FR acquisition, staged DSCA replay→R2 with
   strict-readback receipts, triad+graph commit to main.
2. `government-revenue-live` publishes the twin + page.
3. Verify live: authenticated API both canaries (26-13, 26-27) + a recovery case
   (26-23); anonymous 401/locked negatives; served twin byte-equality vs committed;
   rendered EN/ZH desktop+mobile proof; hostile 26-13 stage-hold; census zero FMS
   `government_procurement_event.v2` rows and zero notification values in any
   award/backlog/revenue aggregate.
4. Closing handoff + Sol return with the full receipt packet (Sol comment §"Production
   proof packet"). D6-C+ / D7+ remain UNAUTHORIZED.

## §11c — Production amendments (2026-08-26, post-merge production proof)

Frozen by the commissioning session after the first two production dispatches.
Each amendment carries its live exemplar; none relaxes a refusal.

1. **§6b — State acquires via STAGED REPLAY in CI (supersedes the §6 live
   CLI leg and the §11b.6 `empty_valid` law).** Production runs 32952963771
   and 32953625355 (the published graph, commit 9e777ad2145c):
   the same `https://www.state.gov/arms-sales-congressional-notifications`
   listing that presents 10-11 qualifying articles to a residential fetch
   served the hosted runner bytes parsing to ZERO qualifying entries, and
   the empty_valid law published `state_pm_bureau: {status: ok,
   qualifying_articles: 0}` with **no byte receipt** — an unseen surface
   encoded as a seen-and-empty one. CI therefore never fetches state.gov:
   it replays the sha-frozen residential capture
   (`data/government_revenue/fms_staged_objects/state_manifest.json` +
   bytes), with R2 put + strict readback per article, transport
   `cli_residential_staged` (additive `TRANSPORTS`/schema-enum extension).
   Refusals (all fail the whole run, mirroring the frozen B10/B11 DSCA
   law): missing manifest, any sha mismatch, a staged listing parsing to
   zero qualifying entries, a listing entry with no staged bytes. The
   capture lever is `python3 -m collectors.fms_notifications_live
   stage-state`, run from a residential network; it refuses to stage an
   empty capture, and records its User-Agent in the manifest (state.gov's
   edge serves the python-requests UA the challenge page even
   residentially). Coverage discloses `role:
   current_presentation_staged`. **Consequences for the battery:** T6/T14
   take their staged forms (integrity failure / absent manifest are the
   typed refusals), old B6 ("State unavailable still publishes") is
   superseded — a live outage is impossible in CI and an integrity failure
   fails closed — and M5 becomes the ok-with-zero impossibility proof.
   New C2/C3 pin the incomplete-capture and empty-capture refusals.

2. **§5 country precedence is a FALL-THROUGH, not a surface election.**
   Production 26-13: the DSCA certification press release parses no
   title-prefix country, and the engine's `elif` discarded the FR annex's
   "Kingdom of Saudi Arabia", publishing `customer_country: null` on the
   flagship canary. A higher-precedence surface's None now falls through
   to the next surface (new C1 test). `capability_title` remains
   web-only per §4.

3. **Push-race note (lane design, unchanged):** `fms-acquire.yml`'s
   commit-back step (a faithful mirror of `dod-budget-acquire.yml`) lost
   `git push HEAD:main` once to the wire lanes' cadence (run 32952963771,
   non-fast-forward rejection; the re-dispatch 32953625355 landed
   9e777ad2145c). No retry loop was added — that would be a two-lane
   design change; re-dispatch after a diagnosed race is the house remedy.
   Flagged in the Sol return.
