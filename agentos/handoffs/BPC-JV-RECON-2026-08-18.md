---
workstream: WS:BPC-JV-RECON
session: claude/bpc-recon-0
model: fable
ended_because: complete
mission: >
  Apply Sol's one remaining factual correction on PR #5909 before architecture
  acceptance. Keep the same PR. Bound DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK
  to local operator state; record File Library membership of W1–W4; set
  relationship UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS; add SNAPSHOT-ONBOARD
  census obligation. Do not start SNAPSHOT-ONBOARD or CONTINUOUS-RECON. Do not
  reopen architecture.
state_before: >
  Sol accepted rights architecture, completion law, two-track roadmap, poison
  rules, reconciliation key, source-owner map, and authority. Freeze still
  treated W1–W3 as unrecovered / not on disk globally, and designated W4 the
  canonical surviving capture. DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK
  had been promoted past its local-search bound.
changed:
  - path: agentos/discoveries/DSC-BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK.md
    what: Local-only claim retained; File Library membership of W1–W4 recorded; relationship UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS; temporal law added.
  - path: research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
    what: §1.1 three-layer census; SNAPSHOT-ONBOARD census protocol; W4 not a proven superset; W1→W4 not vintages.
  - path: agentos/workstreams/WS-BPC-JV-RECON.md
    what: needs_ceo is the corpus-state correction; SNAPSHOT-ONBOARD next_action is census-when-bytes, do not start from #5909.
  - path: config/biocatalyst_sources.yml
    what: Replaced predecessor_workbooks not_recovered_on_disk with local/global/relationship/temporal fields and File Library members with sha256 null.
  - path: tests/test_biocatalyst_source_registry.py
    what: Pins local W4 hash, File Library membership without invented hashes, and UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS.
  - path: agentos/handoffs/BPC-JV-RECON-2026-08-18.md
    what: Handoff rewritten for the corpus-state correction.
prs: [5909]
verified:
  - claim: "Local operator copies of W4 still hash to the pinned SHA256."
    command: "python3 hashlib.sha256 of Downloads and Mastermind BioPharmCatalyst_Tables.xlsx (prior session; not re-run this correction)"
    result: "946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535; 353040 bytes; 9 sheets"
  - claim: "seed_inventory no longer asserts predecessor_workbooks not_recovered_on_disk; File Library member sha256 values are null."
    command: "python3 -c yaml.safe_load config/biocatalyst_sources.yml"
    result: "local_operator_state w4_bytes_only_hash_verified; global_corpus_state all_four_exist_in_chairman_file_library; relationship_state UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS; four members sha256 None"
  - claim: "AgentOS records validate (0 errors)."
    command: "python3 scripts/agentos.py validate"
    result: "234 records (27 workstreams, 76 decisions, 62 discoveries, 69 handoffs) — 0 error(s), 13 warning(s); warnings are unrelated phantom-owns-path / active-but-complete"
  - claim: "Source-registry tests pin local vs global workbook state."
    command: "python3 -m pytest tests/test_biocatalyst_source_registry.py -q"
    result: "16 passed"
unverified:
  - claim: "Sol accepts this remaining corpus-state correction and therefore the freeze."
    what_would_verify: "Sol reply on WS:BPC-JV-RECON needs_ceo / PR #5909. Until then do not start SNAPSHOT-ONBOARD or CONTINUOUS-RECON."
  - claim: "W4 is a superset of W1–W3 with identical common-sheet content."
    what_would_verify: "SNAPSHOT-ONBOARD census of the four File Library bytes (SHA-256, sheet set, dimensions, content hashes, pair class). Not run in this PR."
  - claim: "File Library W4 bytes equal the locally hashed W4 SHA256."
    what_would_verify: "Hash File Library BioPharmCatalyst_Tables(3).xlsx when those bytes are in an implementation environment. Do not invent the hash from metadata."
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
  - "Sol ruling on the remaining corpus-state correction (accept vs further wording vs hold)."
  - "UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS — whether W4 is a superset of W1–W3 with identical common-sheet content."
  - "Whether drugs_at_fda rights_state advances beyond review_required_before_b4 (not requested in this PR)."
  - "Device-applicant to issuer join remains unbuilt; not started."
next_actions:
  - "Wait for Sol review of the corpus-state correction on PR #5909. Do not arm merge-on-green. Do not squash-merge."
  - "Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or snapshot ingestion from this PR."
  - "On Sol PASS of the freeze only: a later session may commission SNAPSHOT-ONBOARD from a fresh origin/main worktree, with the four File Library bytes, and run the census protocol."
do_not_redo:
  - "Do not re-hash the locally verified W4 workbook and four CSVs; freeze §1 hashes stand."
  - "Do not re-count the Historical FDA 28.1% left-shift (4404/15700)."
  - "Do not call W4 a proven superset of W1–W3, and do not call W1–W3 lost."
  - "Do not treat W1→W4 as four temporal vintages unless a later census proves time-varying common-sheet content."
  - "Do not invent predecessor SHA-256 values from File Library metadata."
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
  - "Do not reopen the accepted architecture (rights, completion law, two-track roadmap, poison, match key, source-owner map)."
danger_areas:
  - "A write into a sparse worktree omitted data/ or site/ tree truncates the committed artifact. Snapshot onboarding must not git add -A under data/ on a sparse tree."
  - "Export-time Price, IV, OI, expected move, and market cap on Catalyst Impact / Device Pipeline will look like useful features. Joining them onto 2009–2026 Historical FDA rows is the poison-list failure mode. Capture-time research use from 2026-08-17 onward is the complement, not a back-join."
  - "Sibling biocatalyst-p0-* worktrees own the soak. Editing collectors/biocatalyst/clinicaltrials_*.py from this workstream will collide."
  - "A sibling session previously blanket-armed merge-on-green on #5909; a later comment disarmed it. Do not re-arm."
  - "event_workspace.v1 claim_citations_pending must stay True; a catalyst PR that sets it False to complete the workspace is a contract break."
  - "Promoting a local-filesystem miss into a global lost claim is the defect Sol just caught. DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK stays local-bounded."
---

## §0 State — what is true right now

Sol accepted the RECON-0 architecture except one corpus-state fact. That fact
is now corrected on the same PR #5909: local operator state is W4 bytes only;
global corpus state is W1/W2/W3/W4 exist in the Chairman's File Library;
relationship is `UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`; W1→W4 are not
four temporal vintages unless a later census proves otherwise. No producer
ran. SNAPSHOT-ONBOARD and CONTINUOUS-RECON were not started. The next move is
Sol's acceptance of this correction.

## §1 What is LEFT — in order

1. Sol answers `needs_ceo` on `WS:BPC-JV-RECON` (accept this corpus-state correction vs further wording vs hold).
2. Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or snapshot ingestion from this PR.
3. Do not merge this freeze PR until Sol has accepted the correction. Do not arm `merge-on-green`.

## §2 What will bite you

The Historical FDA CSV cannot be matched raw: 28.1% of rows are left-shifted
(`DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT`). Keep raw and repaired forms separate.
W1–W3 were absent from the operator filesystem searched 2026-08-19
(`DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK`) but they still exist in the
Chairman's File Library — do not invent SHA-256 from metadata, and do not call
W4 a proven superset. Export-time IV/OI/expected-move columns are tonight's
Polygon EOD overlay, not pre-event features
(`DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT`). Occupied checkouts may still hold
unauthorized `scraped_*.json` files — they are not this freeze's evidence.

## §3 What was decided and found

- `DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN` — Chairman authority; storage/product/repo/research allowed; no continuing API; not Prophet. Accepted by Sol.
- `DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK` — distinct id; matching-only withdrawn; proposed pending Sol; architecture accepted.
- `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE` — `jv_reconciliation_match_key`; architecture accepted.
- `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` — calibration component; ZIP replay is not production proof; architecture accepted.
- `DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK` — local W4 only; File Library still holds W1–W4; relationship unresolved.
- `DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT` — unshift 4404 rows; keep raw vs repaired.
- `DSC:BPC-OPENFDA-PRODUCER-IS-STUB` — device/openFDA work is net-new.
- `DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT` — dated OHLCV is non-W1A.

## §4 Not in scope — do not adopt

No runtime collector, no soak change, no Prophet flag, no LoA model, no live
Drugs@FDA ZIP ingest, no snapshot row ingest in this PR, no BPC continuous API,
no second event bus, no duplicate SEC ingest, no replacement PR, no start of
SNAPSHOT-ONBOARD or CONTINUOUS-RECON, no merge of this PR before Sol acceptance
of the corpus-state correction.
