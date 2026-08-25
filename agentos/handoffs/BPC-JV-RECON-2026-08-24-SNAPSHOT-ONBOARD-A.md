---
workstream: WS:BPC-JV-RECON
session: warp/warp-2b1d7bf0a28b4f9d9016367398c3bd93
model: codex
ended_because: complete
mission: >
  Implement Macro issue #6374 as the first bounded licensed-snapshot vertical:
  admit the Chairman-authorized W4 workbook plus four CSVs, preserve a private
  R2 corpus, derive a safe pointer-bound Historical Event History projection,
  expose it through the existing entitled BioCatalyst page, and stop at an
  exact-head HOLD-FOR-SOL PR without merge, publication, deployment, or
  production-acceptance claims.
state_before: >
  RECON-0 was merged architecture only. SNAPSHOT-ONBOARD was uncommissioned in
  the durable record, no licensed snapshot had been admitted, no historical
  projection/API/panel existed, and the W1–W4 archaeology language predated the
  Chairman's clarification that W4 is the canonical nine-sheet export and W1 is
  unnecessary.
changed:
  - path: engine/biocatalyst/jv_snapshot.py
    what: Exact-byte W4 plus four-CSV admission, deterministic normalization, Historical FDA left-shift repair, identity reconciliation, safe redaction, deduplication, and coverage accounting.
  - path: engine/biocatalyst/historical_events.py
    what: Content-addressed, pointer-bound public projection publication, closed validation, integrity checks, filtering, ordering, and HMAC cursor pagination.
  - path: scripts/biocatalyst_snapshot_onboard.py
    what: Check-by-default operator CLI with separate explicit private-R2 and public-projection publication arms and a safe summary surface.
  - path: contracts/biocatalyst/
    what: Closed JSON contracts for snapshot manifests, historical-event records, and generation manifests.
  - path: app/biocatalyst.py
    what: Existing site_full-entitled Historical Event History API with typed private/no-store failure states.
  - path: templates/biocatalyst.html.j2
    what: Independent EN/ZH Historical Event History panel with filters, expandable provenance/repair/identity detail, and typed unavailable states.
  - path: templates/biocatalyst.js
    what: Closed client validation, safe rendering, filtering/pagination interaction, and localized state handling.
  - path: templates/biocatalyst.css
    what: Token-based desktop/mobile containment for the new dense history panel in dark and light themes.
  - path: site/biocatalyst.html
    what: Generated paired site artifact for the template change.
  - path: site/biocatalyst.js
    what: Generated paired site artifact for the client change.
  - path: site/biocatalyst.css
    what: Generated paired site artifact for the style change.
  - path: tests/
    what: Snapshot, projection, CLI, API, UI, localization, safety, integrity, and hydration coverage for the bounded vertical.
  - path: .github/ci/legacy-jobs.yml
    what: Existing biocatalyst-serving job owns the onboarding CLI and all five new suites; no new CI authority surface.
  - path: research/BIOCATALYST_SNAPSHOT_ONBOARD_A_CORPUS_AND_CONTRACT_FREEZE_2026-08-24.md
    what: Exact input/output receipts, scope law, contract freeze, fixed-point proof, and accepted controlled Chromium evidence.
  - path: agentos/workstreams/WS-BPC-JV-RECON.md
    what: Commissioned in-progress SNAPSHOT-ONBOARD A state plus W4-only and no-expansion boundaries.
prs: []
verified:
  - claim: "Canonical W4 plus four CSV inputs are exact-byte admitted."
    command: "From the approved local input directory: shasum -a 256 BioPharmCatalyst_Tables.xlsx BioPharmCatalyst_All_Companies_Sorted_By_Ticker.csv biopharmcatalyst_historical_fda_all_verified_2009_2026.csv biopharmcatalyst_mergers_acquisitions.csv biopharmcatalyst_hedge_funds.csv"
    result: "W4 946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535; CSVs a08afff0430c06138997f6b8a3e28fee63bb742eecdb4ea936c8bea99f225ee0, f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002, aa33b6dea553b982b32621a3ee759d20283c25b1e6d267289f6e7d38e5afb3fd, fbb968bae5f4f5f6a33f21ee6c02db4450f26cf19aa765ae6e2a6e7212164640."
  - claim: "The actual W4 projection is deterministic and byte-identical across two runs."
    command: "Run scripts/biocatalyst_snapshot_onboard.py twice with identical observed_at, W4/CSV/security/alias inputs, and distinct output roots; compare generated file hashes."
    result: "generation bpcjv_gen_755d98c85beb38603dacefcc; normalized SHA-256 6a750dbf64b294ef111bdd0100630c69c1b298c8600287708b176247af2a712b; 25,420,416 bytes; 16,384 events; both runs byte-identical."
  - claim: "Focused implementation suites pass."
    command: "python3 -m pytest -q tests/test_biocatalyst_jv_snapshot.py tests/test_biocatalyst_historical_events.py tests/test_biocatalyst_snapshot_onboard.py tests/test_biocatalyst_historical_event_api.py tests/test_biocatalyst_historical_event_ui.py"
    result: "35 passed."
  - claim: "Template and generated-site assets are synchronized."
    command: "python3 scripts/check_template_site_sync.py"
    result: "91 pairs checked; sync passed."
  - claim: "Controlled real-Chromium proof covers realistic licensed density."
    command: "Standard Chrome against exact branch assets/API and the actual 16,384-event projection; desktop/mobile, dark/light, EN/ZH, combined filtering, expansion, repaired/resolved and unresolved rows, console and containment inspection."
    result: "All eight visual combinations contained with zero page-origin errors; combined FATE filter returned and expanded the deterministic repaired row; Lantheus showed honest unresolved identity; hardened final smoke remained clean."
unverified:
  - claim: "Private R2 snapshot is published in production object storage."
    what_would_verify: "After explicit Sol release and merge, execute the separately armed private publication against the canonical R2 destination and verify its immutable receipt."
  - claim: "Public projection is deployed and available to a real entitled production user."
    what_would_verify: "After explicit Sol release and merge, deploy through the normal lane and prove a nonzero real site_full production response plus populated panel interaction on the deployed generation."
  - claim: "SNAPSHOT-ONBOARD A is production accepted."
    what_would_verify: "The post-merge private-public generation bind, deployed pointer/hash proof, and real entitled browser/API acceptance described in the freeze receipt."
decisions:
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK"
unresolved:
  - "Sol has not yet reviewed or released the exact held PR head."
  - "No private R2 upload, public projection publication, deployment, or real entitled production acceptance has occurred."
  - "Runtime source-registry insertion and CONTINUOUS-RECON remain separately gated and uncommissioned."
next_actions:
  - "Sol reviews the exact held PR head and either releases or returns findings."
  - "Only after explicit Sol release: merge the same PR, publish the exact private/public generation through the armed lanes, deploy normally, and run the freeze's real entitled production-acceptance matrix."
  - "Do not start CONTINUOUS-RECON, a successor snapshot wave, source/cohort/cadence expansion, or any continuous BPC collection from this handoff."
do_not_redo:
  - "Do not require W1. W4 is the Chairman-authorized canonical nine-sheet workbook; upload suffixes are not chronology and W2/W3 are archaeology only."
  - "Do not re-hash or re-census the admitted W4 plus four CSVs; exact receipts are frozen in the research artifact."
  - "Do not re-count the 4,404/15,700 Historical FDA left shift or alter its deterministic repair law."
  - "Do not repeat the full controlled Chromium matrix unless a product/runtime/browser asset changes; the exact evidence is frozen in the research artifact."
  - "Do not join export-time price, IV, OI, expected move, or market cap onto historical rows as pre-event features."
  - "Do not expose licensed descriptions, URLs, raw rows, private object locators, export timestamps, generation internals, or signed-cursor material in the public projection/API."
  - "Do not mutate config/biocatalyst_sources.yml, the soak manifest, the CT.gov canary, or production_ingest_allowed in this wave."
danger_areas:
  - "The delivery head is the PR headRefOid at stop and is intentionally reported in the PR/final return rather than self-embedded in this handoff."
  - "The actual licensed projection contains 16,384 records and must remain a generated private/public artifact, never a committed corpus."
  - "A controlled local site_full override is browser proof of the exact build, not production entitlement or deployment proof."
  - "The source denominator includes 12 future Device Pipeline rows excluded from Historical Event History; silently dropping them would falsify coverage."
  - "The 24 source-URL tokens are deterministically redacted; restoring them would violate the public projection boundary."
---

## Current state

SNAPSHOT-ONBOARD A is implemented from the Chairman-authorized W4 workbook and
four CSVs. The exact deterministic generation contains 16,384 safe historical
events and is exercised by focused tests and a realistic real-Chromium matrix.
The live source registry, CT.gov canary, soak controls, production storage, and
deployment are untouched. The delivery is `BUILT_NOT_PRODUCTION_PROVEN` and is
held for Sol at the PR's exact head. There is no authority for
CONTINUOUS-RECON or another BioCatalyst source/cohort/cadence wave.
