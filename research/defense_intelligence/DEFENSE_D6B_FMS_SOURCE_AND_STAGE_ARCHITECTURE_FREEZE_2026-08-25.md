# DEFENSE D6-B — FMS Congressional-Notification Source & Stage Architecture Freeze (2026-08-25)

Sol commission D6-B0 (authorized in the D6-A acceptance ruling, macro PR #6385 comment
5404403124). This document freezes the executable architecture for the Foreign Military
Sales congressional-notification source vertical so the D6-B implementation worker makes
**zero** source, identity, stage, amount, correction, ownership, consumer, canary, or
failure-state decisions. Research/records only: this wave ships no collector, schema
file, API, template, or generated data. **D6-B implementation is NOT authorized by this
document** — it requires a separate Sol authorization.

Pins: protected Sol Skillpack `mastermindx-market-intelligence/Mastermind@51f9942733b86e550bb9169d2a43462bd28e774f`
(current head at pickup; D6-A was accepted under `4d323d03e4151449a4b76abfdfefca1d56825fde`);
Macro pickup `origin/main = 99af5edd762637935afa2ce75d040e3ed5bd0532` (2026-08-25T15:05Z;
Sol's review reference `ce4a33aeeed779530942560c5b05f4df8ab0306c` treated as historical only).
Repo-census evidence in this doc is against that head. No newer accepted source law was
found in `agentos/decisions/` or `research/defense_intelligence/`; no material collision.

---

## §0 — Acceptance gates for D6-B implementation ("not done unless")

The D6-B implementation wave is NOT DONE unless all of the following hold. A masterplan
pointer is context, not enforcement; these gates are the enforcement.

1. **Source boundary honored**: current-cycle collection reads ONLY the State surface
   (§3); historical DSCA material enters only through the explicitly bounded archival
   path; a State fetch failure is typed `source_unavailable` and NEVER silently answered
   with stale DSCA-era results (§16 test T6).
2. **Identity**: every case is keyed by the source-native transmittal number when
   present; the fallback identity (§6) is used otherwise and is never silently replaced;
   country+system never forms an identity.
3. **Stage honesty**: every published record's stage is `congressional_notification`
   unless a NEW official first-party evidence class (named in §4.3) proves more; no
   record ever advances on elapsed time (§16 test T3).
4. **Amount honesty**: the only amount semantic is `estimated_notification_value` (§5);
   it never appears as, sums into, or is labeled award, backlog, obligation, revenue, or
   cash; a missing amount is null, never zero.
5. **Correction plane**: same-URL-same-bytes re-observation is a receipted no-op;
   same-identity-changed-bytes appends a new observation version with a new `known_at`
   and preserves the predecessor; nothing is ever mutated in place.
6. **No duplicate planes**: no new general event store, no second identity/correction/
   publication plane, no `government_procurement_event.v2` rows minted (§9), no D5
   contract modification, no `government_program_dossier.v1` widening.
7. **Consumer proven**: the frozen consumer (§13) serves both §15 canaries from the
   real production read model, inside the existing page-weight fence, with the
   anonymous entitlement boundary intact (API + site data 401/locked), and the card
   template provably renders every §13.4 answer from real read-model fields. Proof
   standard = the D6-A standard (production handlers + served-bytes + template/JS
   consumer-chain proof); an authenticated-browser walkthrough is required only if
   Sol's D6-B authorization demands one — the Chairman sequencing amendment's
   no-walkthrough form remains the default.
8. **Hostile canary proven**: Transmittal 26-13 (notified 2026-01-30, ~7 months before
   this freeze) publishes with `congressional_notification` as its highest proven stage
   and an explicit advancement condition, not an inferred sale (§15.3) — with no
   review-period arithmetic anywhere in the pipeline.
9. **Kill tests shipped**: every §16 adversarial test exists as a real failing-by-
   mutation test wired into a merge-binding CI pack.
10. **Production proof**: same standard as D6-A — acquisition receipts, committed
    append-only artifacts, publication descent proof, live API/consumer proof, anonymous
    boundary proof, all receipted in the closing handoff.

---

## §1 — Why this vertical exists (context, not law)

The D6-A budget rail proves what the U.S. government *requests* for domestic programs.
FMS adds the allied-demand path: allied requirement → proposed USG sale → congressional
notification → potential LOA → implemented case → procurement/delivery → company
economics. Those stages must never collapse (H-fms in
`D0R_HISTORICAL_EVENT_CASEBOOK.md:134`: "36(b) notification AR fades unless LOA
implemented"; adversarial state "FMS notification not yet sale" in
`D0R_GOLDEN_UNIVERSE_AND_ARCHETYPE_ROSTER.md` §G4; workflow row 50 of
`D0R_BENCHMARK_AND_WORKFLOW_MATRIX.md`: "BUILD with stage labels; never treat 36(b) as
revenue"). Repo census 2026-08-25: **zero existing FMS/DSCA code or content anywhere in
the repo** (case-insensitive grep across collectors/, engine/, app/, templates/, docs/,
research/ — 24 hits, all incidental substring collisions) — clean field, no duplicate risk.

## §2 — Source census 2026-08-25 (receipts)

All receipts below were taken 2026-08-25 (UTC times per row). Transport per receipt:
`browser` = Browser-pane in-page `fetch` + `crypto.subtle` SHA-256 (lawful public
transport where Akamai rejects CLI TLS fingerprints, per the standing census law);
`cli` = plain curl from the Mac Studio host family the runners use.

| # | Surface | URL | Transport | Status | Bytes | SHA-256 | Retrieved (UTC) |
|---|---|---|---|---|---|---|---|
| R1 | DSCA Major Arms Sales landing/archive | `https://www.dsca.mil/press-media/major-arms-sales` | browser | 200 | 79,526 | `33fd727f45418f5ed9217169e1475ed78f2fb1e92b7721844ee0ff0a27670f92` | 15:12:47Z |
| R2 | DSCA historical notice (canary A) | `https://www.dsca.mil/Press-Media/Major-Arms-Sales/Article-Display/Article/4394629/kingdom-of-saudi-arabia-patriot-advanced-capability-3-missile-segment-enhanceme` | browser | 200 | 64,958 | `d53b9e978aaf5019df381265b27a82278e819f26f7e93395b8c82c9a66cecc6b` | 15:13:34Z |
| R3 | DSCA notice certification PDF (canary A) | `https://media.defense.gov/2026/Jan/30/2003868787/-1/-1/1/PRESS%20RELEASE%20-%20SAUDI%20ARABIA%2026-13%20CN.PDF` | browser | 200 | 133,064 (`%PDF` magic) | `c7e3bcadda94f4f9014bd9eac70827f57bc1e60fe67c20a273074732a8af9c55` | 15:13:43Z |
| R4 | State current-notification surface | `https://www.state.gov/arms-sales-congressional-notifications` | browser | 200 | 194,545 | `6ba951b5e09ff9c07f0b24d1fe23a9934434b9aa994641c09305ee6fd5f83d85` | 15:15:00Z |
| R5 | State post-migration notice (canary B) | `https://www.state.gov/releases/bureau-of-political-military-affairs/2026/03/sweden-m142-high-mobility-artillery-rocket-systems/` | browser | 200 | 176,925 | `a2caf669c2e06ac52b60ff0c76faf7f6ea4353c160ed1f0f9c69943931da42eb` | 15:16:27Z |
| R5c | Same URL as R5 | (same) | cli | 200 | 176,926 | `692236b01d40430f77aaab33a197c7d0e79e7931cdf4423c0858f1e076fbd37a` (two consecutive CLI fetches byte-identical) | 15:18:06Z |
| R6 | DSCA Major Arms Sales Library (pre-Dec-2024 archive + version files) | `https://www.dsca.mil/Press-Media/Major-Arms-Sales/Major-Arms-Sales-Library` | browser | 200 | 110,947 | `684a3655581a574a76541e156d888e31f6898ca835263cd604804271cc484740` | 15:17:15Z |
| R7 | Federal Register 36(b) reprint (third surface) | `https://www.federalregister.gov/documents/full_text/text/2026/07/22/2026-14768.txt` (raw text of doc 2026-14768; citation `91 FR 46080`, pub 2026-07-22) | cli | 200 | 9,571 | `6460ef5b7f1e48f2716e6696e239691dcd5bc53586c104b580702974771c8142` (carries "Transmittal No. 26-74" ×3 + "Date Report Delivered to Congress: June 5, 2026") | 15:43:55Z |

**Migration statement (R1, verbatim):** "In accordance with Executive Order 14383
'ESTABLISHING AN AMERICA FIRST ARMS TRANSFER STRATEGY' signed on February 6, 2026, all
future Foreign Military Sales web posts for cases notified to Congress will be published
on the U.S. Department of State's website."

**Archive-boundary statement (R4, verbatim):** "An archive of Foreign Military Sales
cases formally notified to Congress prior to February 26, 2026, is available at the
website of the U.S. Department of War's Defense Security Cooperation Agency, at:
https://www.dsca.mil/Press-Media/Major-Arms-Sales".

Census facts the implementation may rely on (each observed directly this census):

- **DSCA landing** lists notices Dec 2024 → Feb 6, 2026 (newest visible: "Ukraine –
  Class IX Spare Parts", Feb. 6, 2026), with facet counts (COCOM, category, value
  bands); "To find entries prior to December 2024, search our Major Arm Sales Library."
  Article URL grammar: `/Press-Media/Major-Arms-Sales/Article-Display/Article/<cms-id>/<slug>`.
- **DSCA notice body (R2)** carries: `Transmittal No. 26-13`; dateline "WASHINGTON,
  January 30, 2026"; "The State Department has made a determination approving a possible
  Foreign Military Sale…"; "The Defense Security Cooperation Agency delivered the
  required certification notifying Congress."; "estimated cost of $9.0 billion";
  principal-contractor sentence; the caveat "The description and dollar value are for
  the highest estimated quantity and dollar value based on initial requirements. Actual
  dollar value will be lower depending on final requirements, budget authority, and
  signed sales agreement(s), if and when concluded."; an attached certification PDF (R3)
  on `media.defense.gov`.
- **DSCA Library (R6)** is searchable "by Country name, CN number, or U.S. Department of
  Defense Combatant Command"; files are named `PRESS RELEASE - <COUNTRY> <YY-NN> CN.PDF`;
  it holds **correction versions as separate preserved files** — observed live:
  `DENMARK 25-101 CN.PDF`, `DENMARK 25-101 CNV2.PDF`, `DENMARK 25-101 CNV3.PDF`, and
  `DENMARK 25-99.PDF` beside `DENMARK 25-99 V1.PDF`.
- **State surface (R4)** is owned by the Bureau of Political-Military Affairs; 55 items
  at census; item type label "FOREIGN MILITARY SALES: CONGRESSIONAL NOTIFICATION";
  listing pagination `/arms-sales-congressional-notifications/page/<n>/` (10/page);
  article URL grammar `/releases/bureau-of-political-military-affairs/<YYYY>/<MM>/<slug>/`.
  Oldest visible State posts are dated March 2026 (Sweden M142 HIMARS, UAE F-16 M&U) —
  consistent with the Feb-26-2026 boundary.
- **State notice body (R5)** carries: `Transmittal #26-27`; header date "MARCH 10,
  2026"; "The U.S. Department of State has made a determination approving a possible
  Foreign Military Sale…"; "The estimated total cost is $930 million."; principal-
  contractor sentence ("Lockheed Martin, located in Grand Prairie, Texas"). It does
  **NOT** carry: any attached PDF, any certification-delivery sentence, any DSCA
  mention, and — critically — **no** "highest estimated quantity" caveat paragraph.
  Machine metadata: `article:modified_time = 2026-08-21T18:27:14+00:00` — this March
  post was **modified in place five months later** with no visible version history.
- **Federal Register (R7)**: FR reprints the unclassified 36(b) certification text as
  "Arms Sales Notification" documents (2,006 total; current through 2026-07-22 at
  census), DoD/OSD-published, CLI-accessible JSON API. Probed doc 2026-14768 carries
  `[Transmittal No. 26-74]`, the statutory reference "36(b)(1) of the Arms Export
  Control Act", and — decisive for the clock law — `(viii) Date Report Delivered to
  Congress: June 5, 2026` against FR publication 2026-07-22 (≈7-week lag).
- **Transport matrix** (from the runner host family): `www.state.gov` → **200 to plain
  CLI, byte-deterministic across consecutive fetches** (R5c); `www.dsca.mil` and
  `media.defense.gov` → **403 to CLI** (Akamai TLS fingerprinting; browser transport
  succeeds); `samm.dsca.mil` and `www.federalregister.gov` → 200 to CLI. Browser and
  CLI fetches of the same State URL return *different* bytes (R5 vs R5c) — receipts are
  transport-scoped; the production collector's canonical transport is CLI (§3.4).
- **SAMM** (`https://samm.dsca.mil/chapter/chapter-5`, CLI-accessible): official
  lifecycle vocabulary "Letter of Request (LOR)", "LOR Actionable" (C5.2.5.2.2), "LOR
  Complete" (C5.2.5.2.3), "Letter of Offer and Acceptance (LOA)", with "Congressional
  Notification (CN) pursuant to AECA section 36(b)" required **before LOA signature**
  (C5.1.5; detailed CN process in C5.7 "Congressional Notification - Arms Export
  Control Act 36(b) for Security Assistance Programs").

## §3 — Frozen source-boundary law

1. **Current source (authoritative for cases notified on/after 2026-02-26):** the State
   Department PM-Bureau surface, listing
   `https://www.state.gov/arms-sales-congressional-notifications` + its
   `/releases/bureau-of-political-military-affairs/<YYYY>/<MM>/<slug>/` articles. This
   is the ONLY lawful current-cycle collection surface. If it is unreachable or its
   schema breaks, the rail types `source_unavailable` — it never substitutes Google
   snippets, mirrors, journalism, or the DSCA archive for currency.
2. **Historical source (authoritative for cases notified before 2026-02-26):** the DSCA
   Major Arms Sales surface — the landing widget (Dec 2024 → Feb 2026) and the Major
   Arms Sales Library (pre-Dec-2024, PDF-file-per-version). Historical acquisition is a
   **bounded archival backfill**, never part of the current-cycle poll.
3. **Boundary rule:** the boundary is enforced by *which surface a case's observations
   come from*, deduplicated by transmittal identity (§6) — never by assuming a cutover
   date at parse time. Both first-party boundary statements (EO 14383 signed 2026-02-06;
   State's "prior to February 26, 2026" archive statement) are receipted above; the
   ~20-day gap between them is a fact about the source, not something the collector
   resolves. A transition-window transmittal that appears on both surfaces is ONE case
   with observations from each (§16 test T11).
4. **Transport law:** current-source production collection uses ordinary CLI HTTP
   (proven 200 + byte-deterministic, R5c) from the existing runner infrastructure, with
   the D6-A fetch discipline (allowlisted hosts, no redirect following across hosts,
   size caps, content-type checks). DSCA/media.defense.gov cannot be fetched by CLI
   (403). **Frozen v1 scope:** the current State surface in full, PLUS canary A
   (Transmittal 26-13) acquired once through the **bounded browser-transport archival
   path** — required, because §0.7/§0.8 gate on both canaries. That path is: fetch the
   DSCA article + certification PDF in the Browser pane under the standing in-browser
   receipt law (in-page `fetch` + `crypto.subtle` sha256, receipts recorded); stage the
   exact bytes locally; put them into the canonical R2 immutable store through the
   standard put + strict-readback + byte/sha-equality lane (R2 is not a blocked host —
   only the *fetch* needs the browser); commit the observation with
   `transport: browser_in_page_fetch` recorded on its receipt. Browser-acquired
   observations are archival: they are not polled, and the §8 idempotence law applies
   to whichever transport performs any later re-observation. **Bulk historical
   backfill beyond canary A** (the Dec-2024→Feb-2026 widget and the pre-Dec-2024
   Library corpus) is deferred to Sol (§17-U2). No credentials or login exist anywhere
   on this path; none may be invented or requested.
5. **Federal Register (supplementary official record, not a third collection plane):**
   FR reprints of 36(b) certifications may be attached as *additional observations* on
   an existing case identity — they are the only routinely published official source of
   the certification-delivery date (§7) and of itemized MDE/non-MDE breakdowns for
   post-migration cases. v1 MAY defer FR joining entirely (§17-U3); if joined, FR rows
   attach by transmittal number and NEVER mint a case.

## §4 — Frozen stage law

### §4.1 Stage vocabulary (namespace)

Frozen enum, grounded in the SAMM lifecycle (LOR → CN before LOA signature → LOA →
implementation) and the commissioned minimum:

```
request_or_inquiry          (LOR-class; pre-notification)
congressional_notification  (AECA 36(b) certification delivered to Congress)
loa_offered
loa_accepted
loa_implemented
procurement_or_delivery_evidence
```

### §4.2 v1 provable subset

The censused surfaces prove EXACTLY ONE stage: `congressional_notification`. The DSCA
body sentence ("delivered the required certification notifying Congress") and the State
determination sentence assert notification and nothing later; neither surface publishes
LOA offer/acceptance/implementation events, and no other routine official public surface
doing so was found in this census. Therefore **v1 records carry
`stage = congressional_notification` always**; the rest of the enum exists so later
evidence classes have a home, not so v1 can infer.

### §4.3 Advancement evidence classes

A stage above `congressional_notification` requires a NEW first-party official evidence
class, e.g.: a USG announcement of LOA signature/implementation naming the case; a
DSCA/State official case-status publication; an official notification explicitly
referencing an implemented predecessor case. Contractor press releases, journalism, and
analyst claims are NOT advancement evidence. Absent such evidence the case shows its
current stage plus `stage_not_observed` for everything later, with the UI's "what would
confirm advancement" line (§13.4).

### §4.4 The review-period rule (critical)

Passage of the 15/30-day congressional review period is **not** evidence an LOA was
offered, accepted, or implemented. The review period is context only; the implementation
must not even compute a "review complete" state from dates (that computation is the
first step toward time-based advancement). SAMM C5.7 is the official home of the review
mechanics; the C5.7 body text and the per-country 15-vs-30-day classes were NOT fully
receipted this census (the chapter page truncates before C5.7) — a builder who wants to
*display* review-period context must first receipt C5.7 itself, and may still never
derive stage from it. (§16 test T3.)

## §5 — Frozen 36(b) amount law

- **Semantic name:** `estimated_notification_value`. Census of the existing canonical
  amount vocabulary (the five-member DoD-budget enum `president_budget_request` /
  `prior_year_enacted_reference` / `reconciliation_request` / etc., and the award tape's
  obligation amounts) found no existing semantic that honestly names a 36(b) notified
  value, so the commission's suggested class is adopted verbatim.
- **Definition:** the estimated value stated in a 36(b) congressional notification for
  a *proposed* Foreign Military Sale. Source language: "estimated cost of $9.0 billion"
  (R2), "The estimated total cost is $930 million" (R5), FR "highest estimated quantity
  and dollar value".
- **It is NOT and never converts to:** funded value, signed LOA value, obligation,
  award, company backlog, company revenue, or cash. It never sums into any award-tape,
  backlog, or revenue aggregate. Display copy must carry the negative ("what this
  amount does NOT mean") per §13.4.
- **No in-plane aggregation:** cross-case summation or aggregation of
  `estimated_notification_value` — totals, by-country totals, by-period totals,
  "pipeline" figures — is FORBIDDEN everywhere in v1 (read model, API, UI). Summing
  highest-estimate values across heterogeneous proposed sales manufactures a
  pseudo-backlog number, the exact semantic this vertical exists to prevent. Any
  future aggregate is a separate Sol decision with its own semantic name and caveat
  law. (§16 test T13.)
- **Caveat preservation:** the DSCA/FR caveat ("…for the highest estimated quantity and
  dollar value… Actual dollar value will be lower…") is captured verbatim as
  `source_caveat` when the notice body carries it. Census fact: **State posts do not
  carry the caveat paragraph** (R5) — therefore the caveat semantics live in the
  `estimated_notification_value` semantic itself (contract description + UI law), and
  a missing per-notice caveat is null, never synthesized (no LLM/paraphrase text).
- **Missing value:** a notice without a parseable stated value publishes
  `estimated_notification_value: null` — never 0 (§16 test T10). Printed-value parse
  law follows D6-A: deterministic extraction from official text, no LLM numeric
  origination, unknown layout fails closed.

## §6 — Frozen identity law

- **Primary identity = the transmittal number**, the strongest source-native ID and the
  only one present on all three official surfaces: DSCA body "Transmittal No. 26-13"
  (R2), State body "Transmittal #26-27" (R5), FR heading "[Transmittal No. 26-74]" (R7).
  The DSCA Library confirms it is the archive's own retrieval key ("Search the library
  by Country name, CN number, or…"). Observed grammar: `YY-NN` (two-digit FY-style year,
  dash, sequence number).
- **Case key:** `fms:transmittal:<yy-nn>`. One transmittal = one case, regardless of
  how many surfaces/versions expose it (§16 test T11).
- **Frozen label-detection + normalization grammar** (so a variant miss cannot
  silently mint a fallback identity):
  - Admitted label sites, in precedence order: (1) notice body text; (2) FR document
    heading/body; (3) an attachment/Library filename matching
    `\b(\d{2})-(\d{1,3})\s*CN(?:V\d+)?\.PDF` (case-insensitive).
  - Body/heading detection regex (case-insensitive, applied to visible text):
    `transmittal\s*(?:no\.?|number|num\.?|#)?\s*[:\-]?\s*(\d{2})\s*[-‐-―]\s*(\d{1,3})`
    — covers the three observed grammars ("Transmittal No. 26-13",
    "Transmittal #26-27", "[Transmittal No. 26-74]") and tolerates unicode dash
    variants.
  - Normalization: `<yy>-<n>` with the year kept as printed (two digits) and the
    sequence number stripped of leading zeros; every dash variant normalizes to ASCII
    hyphen; surrounding whitespace removed.
  - Multiple distinct transmittal numbers detected in one notice → `conflicted` for
    review, never a guess.
  - **Mis-key guard:** whenever an observation binds to an existing case key but its
    `customer_country` differs materially from the case's, the case is flagged
    `conflicted` for review — never auto-merged. This is also the named guard for the
    (distant) two-digit-year reuse collision class: a future `YY-NN` reissue colliding
    with an archived case surfaces as `conflicted` instead of silently merging.
- **Fallback identity** (only when a notice page carries NO transmittal label anywhere
  in body or attachments): `fms:urlpath:<sha256(canonical URL path)[:24]>` where the
  canonical URL path is the article path lowercased without scheme/host/query/fragment
  and with one trailing slash. Properties frozen with it:
  - *Collision:* article paths are unique per post on both surfaces (slug + CMS id on
    DSCA; dated slug path on State); two distinct notices cannot share a fallback key.
  - *Correction:* in-place edits (the observed State pattern, R5 `article:modified_time`)
    keep the URL, so versions of the same notice keep the same fallback identity —
    corrections append to one case.
  - *Split risk:* a source-side republish at a NEW URL would mint a second case; the
    implementation must flag same-(country, capability-title) collisions across
    fallback-identity cases as `conflicted` for review — never auto-merge.
  - *Supersession:* if a transmittal number later becomes visible for a fallback-keyed
    case, the case records an identity-supersession observation (append; both keys
    preserved; fallback aliases to the transmittal). History is never rewritten under
    the new key, and the new identity is never backdated (§16 test T9).
- **Country + weapon name is not an identity** under any circumstances.
- Secondary source-native anchors captured per observation, never as identity: canonical
  official URL, DSCA CMS article id, attachment file name (`…<YY-NN> CN[Vn].PDF`), FR
  document number + citation, document SHA-256.

## §7 — Frozen clock law

Four clocks, each with its own evidence source; none is ever fabricated from another:

| Clock | Meaning | Evidence | v1 availability |
|---|---|---|---|
| `official_notification_date` | date the 36(b) certification was delivered to Congress | FR "(viii) Date Report Delivered to Congress" (R7); DSCA-era body dateline + certification sentence (R2) | DSCA-era: from body dateline. State-era: **null unless the FR join lands** — the State post does NOT assert it (R5) |
| `official_web_publication_date` | date the official web post displays | State header date; DSCA article date | both eras |
| `first_observed_at` / `known_at` | when OUR collector first receipted the observation | our receipt `observed_at`, D6-A convention (`known_at` bound to receipt `observed_at`) | always |
| correction `known_at` | when we receipted a changed version | the new observation's `observed_at` | always |

Rules: a webpage date is never `official_notification_date` (the State page date is a
publication date; DSCA's dateline co-asserts certification delivery and may seed the
notification date for DSCA-era cases only, marked with its provenance). Source-side
`article:modified_time` is captured as evidence on the observation but never replaces
our `known_at`. No clock is ever advanced or inferred by elapsed time.

## §8 — Frozen correction law

Grounded in two first-party behaviors observed this census: DSCA historically publishes
correction versions as separate preserved files (`DENMARK 25-101 CN/CNV2/CNV3`, R6);
State edits posts **in place** at the same URL with only a machine `modified_time`
(R5) — so on the current source, *our append-only observation plane is the only version
history that exists*.

- Same official URL + same bytes → **idempotent re-observation**: receipted no-op,
  counts unchanged (D6-A idempotence discipline).
- Same case identity + changed official bytes (same URL edited, or a `CNVn` successor
  file, or a corrected FR reprint) → **append a new observation/version** with a new
  `known_at`; the predecessor observation and its receipt are preserved verbatim;
  nothing is mutated in place (§16 test T8).
- **Retraction/removal**: if a previously observed official URL starts returning
  404/410, or a case vanishes from the official listing while its URL dies, append a
  `retraction_observed` observation (with the probe receipt). The case and its history
  remain visible with the retraction state; deletion of history is forbidden. If the
  source offers no detectable removal signal, no retraction state is invented.
- Receipt/versioning field conventions follow the D6-A triad verbatim: `receipt_id`,
  `observed_at`, `publisher`, `source_url`, `final_url`, `response_sha256`,
  `extractor_version`, `parser_version`; case/line versioning via append-only
  observation versions keyed on the case key. Sol's D6-A unresolved ruling #1 binds
  here too: any future FMS parser-version bump requires generation
  scoping/tombstones frozen FIRST.

## §9 — Frozen contract-owner adjudication

Question: where does canonical FMS truth live, and does it compose with
`government_procurement_event.v2`?

Census facts (repo, 2026-08-25, head 99af5edd):

- `government_procurement_event.v2` (`contracts/government_revenue/government_procurement_event.v2.schema.json`;
  sole producer `engine/government_revenue/award_events.py:1917`): `kind` enum is
  `["opportunity", "recompete", "award_change"]`; the runtime emits ONLY
  `award_change`; required top-level fields include `agency`, `award_change`,
  `listed_company_impacts`, `primary_ticker`; the event identity seed
  (`award_events.py:1735-1776`) is
  `{award_key, source_rail, state_hash, known_at, event_type, changed_fields}` —
  **`award_key` is load-bearing in the identity itself**. An FMS congressional
  notification has no award, no obligation, no recipient-award lineage, different
  clocks, and a stage ladder the contract does not model.
- The D6-A precedent: the budget vertical did NOT enter the event tape; it shipped a
  GovRev-owned source triad + `government_budget_program_graph.v1` read model + its own
  API routes + a bounded page mode.

**Adjudication:**

- **A. Extend/reuse `government_procurement_event.v2` — REJECTED.** There is no
  semantically honest additive representation: reusing `kind: award_change` is the
  commissioned kill-test T12; adding a new kind would still inherit an identity seed
  and required-field set built around awards, would touch the live proven award-tape
  contract for a source with alien clock/stage/amount semantics, and would put
  notification values one field away from award aggregation.
- **B. GovRev-owned FMS source contract + read model, composed into an existing
  product consumer — FROZEN.** Exactly the D6-A pattern: an append-only FMS source
  plane (receipts + case-observation records, D6-A field conventions §8) and one
  derived read model (`government_fms_case.v1`-class, §10 sketch) published through the
  EXISTING GovRev publication plane (same builder, same `government-revenue-data/`
  site-twin convention, same entitlement), consumed by the existing page (§13). No new
  event system, no new identity/correction/publication plane.
- **C. New general defense event store — REJECTED** (presumptive commission rejection;
  duplicate-plane prohibition; nothing in the census requires it).

**Composition with the event plane:** v1 emits ZERO `government_procurement_event.v2`
rows. A future stage-transition→event-tape bridge (e.g. an FMS-aware event kind so
notifications surface on the changes tape) is a **named rejected-for-now alternative**
requiring its own Sol authorization and its own kind/identity design; nothing in this
freeze presumes it.

Decision record: `DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL`
(`agentos/decisions/DEC-FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL.md`).

## §10 — Read-model sketch (design prose — NOT a schema file; D6-B writes the schema)

Case record (`government_fms_case.v1`-class), one per case key:

- identity: `case_key` (§6), `transmittal_number` | null, `identity_basis`
  (`transmittal` | `url_fallback`), `case_identity_state` (`resolved` |
  `identity_unresolved` | `conflicted` — case tier; deliberately a different field
  name from the contractor-tier `identity_state`, whose vocabulary is the reviewed
  four-state set), aliases.
- customer: `customer_country` (source-printed name; no ISO normalization without a
  reviewed table), region/COCOM only if source-printed.
- capability: `capability_title` (the FULL source-printed post title, verbatim — no
  splitting parse; any customer/capability split on the card is a design-lane
  *presentation* of this one verbatim field, never a second data field), plus
  `source_item_enumeration` (the notice's itemized articles/services list, verbatim
  capture, no summarization).
- stage: `stage` (§4; v1 always `congressional_notification`), `stage_evidence`
  (per-stage receipt refs), `later_stages: stage_not_observed`, `advancement_condition`
  (typed, from the frozen catalog — v1 catalog has EXACTLY ONE member,
  `official_evidence_of_offered_accepted_or_implemented_loa`; adding members requires
  the §4.3 evidence-class design, never ad-hoc strings).
- amount: `estimated_notification_value` | null, `currency: USD`, `source_caveat`
  (verbatim | null), amount receipt ref. No aggregates (§5).
- contractors: list of `{name_as_printed, location_as_printed, identity_state
  (not_reviewed | reviewed | reviewed_none | conflicted), issuer_ref | null}` (§11).
- program links: `program_links` — a LIST of five-key pointer objects (§12); v1
  publishes exactly one entry (the whole-case link state, `not_reviewed`); reviewed
  curation may later carry one entry per named system.
- clocks (§7) + observations[] (append-only version history, §8) + per-observation
  receipts (§8 conventions) + `source_surface` (`dsca` | `state` | `federal_register`).
- rail-level artifact: `content_id` + generation id per the D6-A graph conventions.

## §11 — Frozen contractor/company law

A notification's principal-contractor sentence means exactly "source says this entity
may be principal contractor" — never contract awarded, revenue earned, economic share
known, or ticker proven. Census exhibit: the SAME issuer appears as "Lockheed-Martin
Corporation, located in Dallas, TX" (R2) and "Lockheed Martin, located in Grand
Prairie, Texas" (R5) — free-text name forms are not identity. Frozen:

- Contractor names are captured verbatim with `identity_state: not_reviewed` by
  default. **No ticker is ever minted from contractor prose** (§16 test T4).
- Public-issuer linkage may ONLY consume the existing reviewed identity path — the D2
  Identity Atlas plane (`government_revenue_identity_atlas.v1`, whose contract is
  display/context-only and "Never carries an event or award reference") or an
  equivalent reviewed curation with per-hop evidence — or remain unresolved. v1 ships
  all `not_reviewed`; any curation is a separate reviewed act.
- **No economic weight**: no revenue share, no backlog attribution, no per-issuer value
  split, ever, at any review state. (Mirrors D6-A's `economic_weight: null` edge law.)

## §12 — Frozen program law

A system/product name in a notification (e.g. "PATRIOT Advanced Capability-3", "M142")
may be *proposed* for review against the D5 ontology; **no automatic string link** (§16
test T5). Of the three commissioned homes, frozen: **an FMS read-model pointer to a D5
program** — an **FMS-owned five-key link object** that reuses the admitted-state
*pattern* of `government_procurement_event.v2`'s `$defs/programLink` but is defined in
the FMS contract, NOT schema-reused by reference. (The event plane's `not_reviewed`
branch requires a non-null `ontology_graph_id` because the workspace builder always has
the ontology graph loaded; the FMS v1 builder does not consult D5 at all, so verbatim
reuse would be unsatisfiable.) Frozen FMS shape — exactly five keys:

```
state:                reviewed | not_reviewed | reviewed_none | conflicted | source_unavailable
reason_code:          "no_reviewed_program_link" when state ∈ {not_reviewed, reviewed_none};
                      "ontology_unavailable" when state = source_unavailable; null otherwise
program_id:           ^acq-program:[a-z0-9][a-z0-9:-]*$ when reviewed; null otherwise
program_case_link_id: ^prog-case:[a-f0-9]{12}$ when reviewed; null otherwise
ontology_graph_id:    ^program-ontology:… of the graph generation actually consulted;
                      null when no consult occurred (the v1 constant case)
```

v1 ships every case with the single entry
`{state: not_reviewed, reason_code: no_reviewed_program_link, program_id: null,
program_case_link_id: null, ontology_graph_id: null}` — null `ontology_graph_id` is the
honest v1 value because no ontology consult occurs. `reviewed` may ONLY ever be minted
by the D5 curator flow in a later authorized wave, which then also stamps the consulted
`ontology_graph_id`. **D5 is not modified in B0 or D6-B v1**;
`government_program_ontology.v1.budget_program_keys` stays empty-enforced (schema line
221 `{"type": "array", "maxItems": 0}` + runtime assertion `program_ontology.py:636`).

## §13 — Frozen product consumer

### §13.1 The one consumer

**A bounded FMS case rail on the existing `government_revenue.html` page** (the first
commissioned candidate location). Census: the page has 8 mode tabs (`awards`, `budget`,
`candidates`, `companies`, `opportunities`, `programs`, `recompetes`, `changes`); the
FMS rail is a ninth bounded mode (`data-mode="fms"`) built on the budget-mode pattern:
entitled read-model JSON + API routes + a mode section. Rejected: the `changes` event
tape (requires the contract §9 rejects); widening `government_program_dossier.v1`
(prohibited); a separate FMS page (estate archaeology shows the existing family
supports the job — the budget rail just proved this exact composition).

### §13.2 Delivery plane

Same as D6-A: read model published as `data/government_revenue/fms_case_*.json` +
site twin `site/government-revenue-data/fms-cases.json` through the existing
`government-revenue-live` publication lane; API routes in the existing entitled router
(`/api/government-revenue/fms-cases`, `/api/government-revenue/fms-case/{case_key}`),
inheriting `require_site_full_user` and the anonymous 401/locked boundary. No new
publication or entitlement plane.

### §13.3 Page-weight fence (hard)

`RAW_HTML_BUDGET_BYTES = 303_104` (`scripts/build_government_revenue.py:113`, enforced
at build `:1053` and by `tests/test_government_revenue_ui.py:671`). Census headroom:
`site/government_revenue.html` on main = 274,214 bytes → **28,890 bytes free**. Frozen:
the FMS mode's HTML shell delta is ≤ 8,192 bytes; all case bodies live in the entitled
JSON read model, never in the HTML. If implementation cannot fit the shell in that
budget, the fence is re-negotiated with Sol explicitly — never silently widened.

### §13.4 The five-second user answers (card law)

The case card must answer, in glance-tier plain words (EN/ZH per house bilingual law;
no internal state names, no raw slugs, no falsifier/refutation vocabulary front-facing):

1. Who is the foreign customer? → `customer_country`.
2. What capability/system is proposed? → `capability_title`.
3. What exact stage has been reached? → stage in plain words ("Notified to Congress —
   not a signed sale"), with later stages explicitly not observed.
4. What amount was notified, and what does it NOT mean? → `estimated_notification_value`
   + the standing negative ("an estimate for a proposed sale — not a contract award,
   backlog, or revenue") + `source_caveat` when present.
5. Which contractors/program links are reviewed versus merely named? →
   `identity_state` / program-link state badges (reviewed vs named-in-source).
6. When did this become known? → `known_at` (+ official dates where held, §7).
7. What official step would confirm advancement? → `advancement_condition` ("an
   implemented LOA announced by an official source — the passage of the review period
   alone confirms nothing").

Exact palette/type/copy are design-lane work at implementation (opus `designer` /
main-loop per the standing design lane); this freeze pins the information architecture
only.

## §14 — Frozen failure states

Reuse of the canonical GovRev lowercase snake_case vocabulary (census: exact spellings
live in `engine/government_revenue/program_dossier.py:109-126`,
`freshness.py:45-175`, `award_events.py:190`, and the programLink `$defs`), mapped from
the commissioned names:

| Commissioned name | Frozen token | Tier | Canonical home / status |
|---|---|---|---|
| CURRENT | `current` | dossier/display | existing display mapping (`program_dossier.py:115`) |
| SOURCE_UNAVAILABLE | `source_unavailable` | dossier/display | existing (same mapping's fail branch) |
| SOURCE_STALE | `stale` | dossier/display + freshness | existing (both tiers) |
| RIGHTS_BLOCKED | `rights_blocked` | dossier/display | D0R display-tier vocab; new lowercase token at contract tier |
| VALID_EMPTY | `empty_valid` | dossier/display | D0R display-tier spelling adopted (a truly empty official listing is a valid state, never coerced from unavailability) |
| IDENTITY_UNRESOLVED | `identity_unresolved` | case (`case_identity_state`) | new (fallback-identity in force, §6); the third case-tier token is `resolved`, the healthy default |
| PROGRAM_UNRESOLVED | `not_reviewed` (`program_links[].state`) | linkage | pattern per §12 |
| CONTRACTOR_IDENTITY_UNRESOLVED | `not_reviewed` (contractor `identity_state`) | linkage | pattern reuse (§11) |
| STAGE_NOT_OBSERVED | `stage_not_observed` | case/stage | new (§4.3) |
| CORRECTED | `corrected` | case/observation | existing published state (`candidates.py:953`; note `award_events.py:190` is an upstream input-token set for *detecting* source correction language, not a published state — the FMS `corrected` is OUR appended-observation state, §8) |
| CONFLICTED | `conflicted` | case + linkage | existing (workspace/entity_resolution/programLink) |

**Two state planes, deliberately distinct vocabularies:**

1. **Workspace freshness plane** (what the rail writes into the workspace `freshness.fms`
   block): the EXISTING `freshness.py` vocabulary — `ok` / `partial` / `stale` /
   `unavailable` / `blocked` / `failed` / `unknown` (`freshness.py:14-21`,
   `_STATUS_RANK`). The FMS rail writes THESE tokens there (writing `current` into that
   plane would rank as `unknown`). An empty-but-healthy listing is `status: ok` with a
   zero visible-record count (the SAM `latest.json` pattern) — the never-coerce rule
   binds the writer: a fetch/parse failure is `unavailable`/`failed`, never ok-with-zero.
2. **Dossier/display + FMS contract tier**: the table above; `program_dossier.py:115`'s
   existing mapping (`ok→current`, `partial→partial`, `stale→stale`, else
   `source_unavailable`) carries plane 1 into plane 2.

Rules: `partial` remains available for a listing that loads while some articles fail.
`empty_valid` is only lawful when the listing itself was fetched and parsed successfully
and genuinely contains zero **qualifying items** — frozen predicate: a listing entry
carrying the type label "FOREIGN MILITARY SALES: CONGRESSIONAL NOTIFICATION" on the
PM-Bureau notifications listing (non-FMS PM releases share the `/releases/` namespace
and never qualify by URL shape alone). 0-plus-unavailable is never `empty_valid` (D0R
failure-behavior law; §16 test T14). Display tier renders all of these through the
existing glance-tier plain-word treatment, never as raw tokens.

## §15 — Frozen pilot canaries

### §15.1 Canary A — historical, DSCA-hosted

**Transmittal No. 26-13** — "Kingdom of Saudi Arabia – PATRIOT Advanced Capability-3
Missile Segment Enhancement Missiles", notified (certification delivered) 2026-01-30;
golden program Patriot/PAC-3 (G3 roster), golden issuer LMT. Receipts R2 (article,
sha256 `d53b9e97…cecc6b`) + R3 (certification PDF, sha256 `c7e3bcad…af9c55`).
Receipt-bound expected values: `estimated_notification_value` = $9,000,000,000
("estimated cost of $9.0 billion"); customer "Kingdom of Saudi Arabia"; principal
contractor as printed "Lockheed-Martin Corporation, located in Dallas, TX"
(`not_reviewed`); `source_caveat` = the "highest estimated quantity…" paragraph
verbatim; `official_notification_date` 2026-01-30 (DSCA body dateline + certification
sentence); `official_web_publication_date` 2026-01-30 (independently printed as the
article's own date — "NEWS | Jan. 30, 2026" page header and the landing listing's date,
R1/R2 — the two clocks coincide here but each has its own printed source, per §7);
stage `congressional_notification`. Production acquisition: the §3.4 bounded
browser-transport archival path.

### §15.2 Canary B — current, State-hosted

**Transmittal #26-27** — "Sweden – M142 High Mobility Artillery Rocket Systems",
State post dated 2026-03-10 (among the first post-migration posts); golden program
HIMARS/GMLRS, golden issuer LMT. Receipts R5/R5c. Receipt-bound expected values:
`estimated_notification_value` = $930,000,000 ("The estimated total cost is $930
million"); customer "Government of Sweden"; principal contractor as printed "Lockheed
Martin, located in Grand Prairie, Texas" (`not_reviewed`); `source_caveat` = null
(census: State posts omit the caveat paragraph); `official_notification_date` = null
in v1 (the State post does not assert it; §7); `official_web_publication_date`
2026-03-10; stage `congressional_notification`. Both canaries are golden-program
first-party fits — nothing was contorted.

### §15.3 Hostile state — months elapsed, no advancement evidence

Case 26-13 was notified 2026-01-30 — ~207 days before this freeze's census — and no
official public evidence of an offered/accepted/implemented LOA exists on any censused
surface. Whatever statutory review period applies (deliberately NOT computed here —
the per-country review classes are unreceipted, §17-U1, and the law forbids deriving
anything from them, §4.4), more than enough calendar time has passed that a
time-advances-stage bug WOULD have advanced this case. **Expected published result:
`stage = congressional_notification` remains the highest proven stage**, later stages
`stage_not_observed`, advancement condition displayed. Any implementation that shows
26-13 as a sale, an award, or "review complete → advanced" — or that stores/renders
any review-period-elapsed conclusion at all — fails the wave.

Reference composition (real receipted data, frozen §10 shape):
`research/defense_intelligence/evidence/fms_reference_composition_2026-08-25.json`.

## §16 — Frozen adversarial kill tests

D6-B implementation must ship each as a real test that FAILS under the described
mutation, wired merge-binding (D6-A discipline):

- **T1** — a `congressional_notification` case rendered/labeled as a completed sale
  (or any completed-sale vocabulary in the card for an unadvanced case) → fail.
- **T2** — `estimated_notification_value` appearing in, summing into, or labeled as
  award / obligation / backlog / revenue / cash anywhere → fail.
- **T3** — any code path that raises `stage` (or displays advancement) from elapsed
  time / review-period arithmetic → fail.
- **T4** — a ticker/issuer_ref minted from contractor prose without the reviewed
  identity path (`identity_state: reviewed` absent) → fail.
- **T5** — a D5 program link in state `reviewed` created by string similarity rather
  than the D5 curator → fail.
- **T6** — State listing/article fetch failure that yields anything other than typed
  `source_unavailable` (e.g. silently serving DSCA-era or cached results as current) → fail.
- **T7** — a search-engine snippet, mirror, or non-official transport result accepted
  as an observation receipt → fail.
- **T8** — same URL + changed bytes overwriting a predecessor observation (any in-place
  mutation of case history) → fail.
- **T9** — a fallback identity silently replaced/backdated when a transmittal is later
  discovered (supersession must append, alias, and preserve) → fail.
- **T10** — a missing stated value published as 0 (or any coercion of null→0) → fail.
- **T11** — one transmittal exposed by two surfaces (DSCA/State/FR) producing two cases
  → fail.
- **T12** — an FMS record emitted as `government_procurement_event.v2` (any kind,
  including `award_change`) → fail.
- **T13** (freeze-added, §5) — any cross-case sum/aggregate of
  `estimated_notification_value` anywhere in the read model, API, or UI → fail.
- **T14** (freeze-added, §14) — a listing fetch/parse failure, or a zero-row parse of
  a listing whose fetch failed, published as `empty_valid` / freshness `ok` (the
  0-plus-unavailable coercion) → fail.

## §17 — Unresolveds preserved for Sol (named; not silently resolved)

- **U1 — SAMM C5.7 body not fully receipted:** the review-period mechanics (15 vs 30
  days; country classes; thresholds) were not captured verbatim this census (chapter
  page truncates before C5.7). v1 does not need them (no time-based logic is lawful,
  §4.4); any display of review-period context requires receipting C5.7 first.
- **U2 — Bulk historical backfill depth:** DSCA CLI transport is 403; the Library's
  pre-Dec-2024 PDF corpus and the Dec-2024→Feb-2026 widget were censused but not
  acquired. The v1 floor is FROZEN (§3.4: full current State surface + canary A via
  the bounded browser-transport archival path); whether to backfill the DSCA archive
  beyond canary A is Sol's call; the freeze binds the mechanics either way.
- **U3 — Federal Register join:** FR is the only routine official source of
  `official_notification_date` for State-era cases (§7) and of itemized certification
  detail. Joining it (attach-by-transmittal observations) is designed (§3.5) but not
  mandated for v1; deferring leaves State-era notification dates null.
- **U4 — Boundary-window completeness:** the ~Feb-06→Feb-26-2026 window between the EO
  signature and State's stated archive boundary was not exhaustively censused for
  cases appearing on both/neither surface; dedup-by-transmittal (§6) makes this safe,
  but a completeness sweep of the window is an implementation-time verification task.
- **U5 — ZH glance-tier vocabulary** for FMS stage/amount negatives (bilingual law)
  is design-lane work at implementation; no ZH copy is frozen here.

---

*Companion:* `DEFENSE_D6B_FMS_IMPLEMENTATION_HANDOFF.md` (paste-ready D6-B commission).
*Decision:* `DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL`.
*Registry:* `D0R_SOURCE_RIGHTS_AND_PIT_REGISTRY.md` — one E2 re-census row added and
the main-registry DSCA row rewritten, 2026-08-25.
*Review:* the freeze package was adversarially reviewed (opus) before Sol — 5 blockers
/ 11 mediums / 6 lows found and repaired in this document's final form; the
contract-owner adjudication (§9/DEC) and source law survived attack unchanged.
