---
workstream: WS:BPC-JV-RECON
session: claude/bpc-recon-0
model: fable
ended_because: complete
mission: >
  Amend PR #5909 in place after Sol REQUEST CHANGES. Correct JV finite-snapshot
  vs continuous-feed rights, census all four workbooks, change program-completion
  law, split SNAPSHOT-ONBOARD vs CONTINUOUS-RECON, demote Drugs@FDA ZIP replay
  to calibration, reframe ticker+date+drug as jv_reconciliation_match_key,
  convert architectural DECs to proposed rulings pending Sol. Do not open a
  replacement PR. Do not start RECON-1 or any runtime work.
state_before: >
  PR #5909 freeze treated JV snapshots as matching-only / operator-held never
  git, and treated RECON-1 hermetic Drugs@FDA ZIP replay as program completion.
  Sol accepted the archaeology foundation and requested conceptual amendments
  only. Local worktree was at origin/claude/bpc-recon-0.
changed:
  - path: research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
    what: Amended freeze — Chairman rights, four-workbook census, completion law, two-concept roadmap, jv_reconciliation_match_key, poison complement, proposed-pending-Sol DECs.
  - path: config/biocatalyst_sources.yml
    what: Replaced finite_jv_snapshot_seed with licensed_finite_snapshot; kept production_ingest_allowed false as continuous-producer gate; added finite_snapshot_capabilities and continuous_feed_rights.
  - path: tests/test_biocatalyst_source_registry.py
    what: Replaced permanent JV import/projection block with tests pinning finite licensed snapshot use allowed vs continuous API/scraping and temporal leakage forbidden.
  - path: agentos/workstreams/WS-BPC-JV-RECON.md
    what: Program-done is corpus + producers + consumers + PIT research, not RECON-1. Waves SNAPSHOT-ONBOARD and CONTINUOUS-RECON; RECON-1 dropped as a standalone vertical.
  - path: agentos/decisions/DEC-BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN.md
    what: New Chairman-authority rights DEC.
  - path: agentos/decisions/DEC-BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK.md
    what: Distinct id kept; matching-only / never-git withdrawn; proposed pending Sol.
  - path: agentos/decisions/DEC-BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE.md
    what: ticker+date+drug is jv_reconciliation_match_key; proposed pending Sol.
  - path: agentos/decisions/DEC-BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE.md
    what: Calibration component only; CI ZIP is not production proof; not program-done.
  - path: agentos/discoveries/DSC-BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK.md
    what: W1–W3 not recovered; W4 is canonical surviving capture, not a proven superset.
prs: [5909]
verified:
  - claim: "Only one distinct BioPharmCatalyst workbook byte-identity is on disk (9-sheet W4)."
    command: "ls \"/Users/chriswong/Downloads/New Folder With Items 26/BioPharmCatalyst_Tables.xlsx\" \"/Users/chriswong/Documents/Cluade/Mastermind/BioPharmCatalyst_Tables.xlsx\""
    result: "two copies exist; python3 hashlib.sha256 both = 946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535; 353040 bytes; 9 sheets"
  - claim: "Four CSV SHA256 values match freeze §1 and seed_inventory.csv_sha256."
    command: "python3 hashlib.sha256 over the four CSVs in Downloads/New Folder With Items 26"
    result: "all_companies a08afff0430c06138997f6b8a3e28fee63bb742eecdb4ea936c8bea99f225ee0; historical_fda f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002; ma aa33b6dea553b982b32621a3ee759d20283c25b1e6d267289f6e7d38e5afb3fd; hedge fbb968bae5f4f5f6a33f21ee6c02db4450f26cf19aa765ae6e2a6e7212164640"
  - claim: "production_ingest_allowed stays false on the JV snapshot; finite-snapshot capabilities are allowed."
    command: "python3 -c yaml.safe_load config/biocatalyst_sources.yml"
    result: "biopharmcatalyst_jv_snapshot production_ingest_allowed false; license_class licensed_finite_snapshot; continuous_bpc_api forbidden"
  - claim: "AgentOS records validate (0 errors)."
    command: "python3 scripts/agentos.py validate"
    result: "230 records (27 workstreams, 74 decisions, 61 discoveries, 68 handoffs) — 0 error(s), 13 warning(s); warnings are unrelated phantom-owns-path / active-but-complete"
  - claim: "Source-registry tests pin finite snapshot vs continuous feed."
    command: "python3 -m pytest tests/test_biocatalyst_source_registry.py -q"
    result: "16 passed"
unverified:
  - claim: "Sol accepts the amended freeze, Chairman rights encoding, and two-concept roadmap."
    what_would_verify: "Sol reply on WS:BPC-JV-RECON needs_ceo / PR #5909. Until then do not start SNAPSHOT-ONBOARD or CONTINUOUS-RECON."
  - claim: "The missing 3/6/8-sheet predecessor workbooks are lost rather than stored in an unsearched location."
    what_would_verify: "Operator recovers a second distinct BioPharmCatalyst*.xlsx whose SHA256 differs from W4, or closes W1–W3 as lost."
decisions:
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-OPENFDA-PRODUCER-IS-STUB"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
  - "DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK"
unresolved:
  - "Sol ruling on amended freeze needs_ceo (accept vs further changes vs hold)."
  - "Whether drugs_at_fda rights_state advances beyond review_required_before_b4 (not requested in this PR)."
  - "Recovery or closure of the 3/6/8-sheet predecessor workbooks."
  - "Device-applicant to issuer join remains unbuilt; not started."
next_actions:
  - "Wait for Sol review of amended PR #5909. Do not arm merge-on-green. Do not squash-merge."
  - "Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or snapshot ingestion from this PR."
  - "On Sol PASS of the amended freeze only: a later session may commission SNAPSHOT-ONBOARD from a fresh origin/main worktree."
do_not_redo:
  - "Do not re-hash the surviving W4 workbook and four CSVs; freeze §1 hashes stand."
  - "Do not re-count the Historical FDA 28.1% left-shift (4404/15700)."
  - "Do not treat missing 3/6/8-sheet workbooks as proven supersets of W4."
  - "Do not rewrite biopharmcatalyst_benchmark permitted_uses or prohibited_uses."
  - "Do not inspect, scrape, or depend on BPC's private continuous API."
  - "Do not flip production_ingest_allowed true to authorize snapshot import."
  - "Do not commit unauthorized scraped_*.json files."
  - "Do not modify b2_history_canary, BIOCATALYST_HISTORY_ENABLED, or the soak window."
  - "Do not stuff PDUFA/device/conference into evt_cik…_fy_action, or use ticker+date+drug as canonical event identity."
  - "Do not treat collectors.biocatalyst.openfda_regulatory as implemented."
  - "Do not treat Market Memory W1A as a historical PIT price source for past catalysts."
  - "Do not describe CI ZIP replay as production proof."
  - "Do not open a replacement PR for #5909."
danger_areas:
  - "A write into a sparse worktree omitted data/ or site/ tree truncates the committed artifact. Snapshot onboarding must not git add -A under data/ on a sparse tree."
  - "Export-time Price, IV, OI, expected move, and market cap on Catalyst Impact / Device Pipeline will look like useful features. Joining them onto 2009–2026 Historical FDA rows is the poison-list failure mode. Capture-time research use from 2026-08-17 onward is the complement, not a back-join."
  - "Sibling biocatalyst-p0-* worktrees own the soak. Editing collectors/biocatalyst/clinicaltrials_*.py from this workstream will collide."
  - "A sibling session previously blanket-armed merge-on-green on #5909; a later comment disarmed it. Do not re-arm."
  - "event_workspace.v1 claim_citations_pending must stay True; a catalyst PR that sets it False to complete the workspace is a contract break."
---

## §0 State — what is true right now

The RECON-0 freeze is amended for Sol. Chairman finite-snapshot rights are
encoded. Continuous BPC API and authenticated scraping stay forbidden.
`production_ingest_allowed` stays false as the continuous-producer gate.
Program completion is corpus + producers + consumers + PIT research, not a
hermetic ZIP matcher. W1–W3 workbooks were not recovered. No producer ran.
The CT.gov soak was not edited. The next move is Sol's review of the same
PR #5909.

## §1 What is LEFT — in order

1. Sol answers `needs_ceo` on `WS:BPC-JV-RECON` (accept amended freeze vs further changes vs hold).
2. Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or snapshot ingestion from this PR.
3. Do not merge this freeze PR until Sol has reviewed the amendment. Do not arm `merge-on-green`.

## §2 What will bite you

The Historical FDA CSV cannot be matched raw: 28.1% of rows are left-shifted
(`DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT`). Keep raw and repaired forms separate.
Predecessor 3/6/8-sheet workbooks are missing
(`DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK`) — do not invent a supersession
proof. Export-time IV/OI/expected-move columns are tonight's Polygon EOD overlay,
not pre-event features (`DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT`). Occupied
checkouts may still hold unauthorized `scraped_*.json` files — they are not this
freeze's evidence.

## §3 What was decided and found

- `DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN` — Chairman authority; storage/product/repo/research allowed; no continuing API; not Prophet.
- `DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK` — distinct id; matching-only withdrawn; proposed pending Sol.
- `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE` — `jv_reconciliation_match_key`; proposed pending Sol.
- `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` — calibration component; ZIP replay is not production proof; proposed pending Sol.
- `DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK` — only W4 recovered.
- `DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT` — unshift 4404 rows; keep raw vs repaired.
- `DSC:BPC-OPENFDA-PRODUCER-IS-STUB` — device/openFDA work is net-new.
- `DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT` — dated OHLCV is non-W1A.

## §4 Not in scope — do not adopt

No runtime collector, no soak change, no Prophet flag, no LoA model, no live
Drugs@FDA ZIP ingest, no snapshot row ingest in this PR, no BPC continuous API,
no second event bus, no duplicate SEC ingest, no replacement PR, no merge of
this PR before Sol review of the amendment.
