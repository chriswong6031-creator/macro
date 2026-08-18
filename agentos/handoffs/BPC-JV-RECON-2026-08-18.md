---
workstream: WS:BPC-JV-RECON
session: claude/bpc-recon-0
model: fable
ended_because: complete
mission: >
  BPC-RECON-0: turn the authorized BioPharmCatalyst snapshots into a complete
  spec for independently rebuilding every reconstructable dataset from
  Mastermind-owned primary sources. Open one research/architecture PR and stop
  for Sol review. No runtime implementation. Do not touch the CT.gov soak.
state_before: >
  No freeze, no WS:BPC-JV-RECON, no jv_snapshot source identity. Authorized dump
  sat in Downloads (2026-08-17). biopharmcatalyst_benchmark remained the only
  BPC source id. Occupied local-main carried unauthorized scraped_*.json files
  that this session treated as out of scope.
changed:
  - path: research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
    what: Reconstruction freeze — evidence hashes, clock/poison split, column classification for nine sheets plus four CSVs, owner map, coverage scores, ranked backlog, RECON-1 spec.
  - path: config/biocatalyst_sources.yml
    what: Added license_class finite_jv_snapshot_seed and source biopharmcatalyst_jv_snapshot (ingest false). Left biopharmcatalyst_benchmark verbatim.
  - path: tests/test_biocatalyst_source_registry.py
    what: Pinned that the benchmark permitted/prohibited uses are unchanged and that the JV snapshot id is distinct.
  - path: agentos/workstreams/WS-BPC-JV-RECON.md
    what: New workstream awaiting Sol review, needs_ceo on RECON-1 as first vertical.
  - path: agentos/decisions/DEC-BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK.md
    what: JV seeds are a distinct source identity from the clean-room benchmark.
  - path: agentos/decisions/DEC-BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE.md
    what: Catalysts share identity/lifecycle, not fiscal event_workspace.v1 ids.
  - path: agentos/decisions/DEC-BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE.md
    what: First vertical is hermetic Drugs@FDA approved-event reconstruction.
  - path: agentos/discoveries/DSC-BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT.md
    what: 4404/15700 Historical FDA rows (28.1%) are left-shifted.
  - path: agentos/discoveries/DSC-BPC-OPENFDA-PRODUCER-IS-STUB.md
    what: collectors.biocatalyst.openfda_regulatory does not exist on disk.
  - path: agentos/discoveries/DSC-BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT.md
    what: W1A cannot supply PIT prices for past catalysts; dated OHLCV is non-W1A.
verified:
  - claim: "Authorized dump SHA256 values match freeze §1."
    command: "python3 hashlib.sha256 over /Users/chriswong/Downloads/New Folder With Items 26/{xlsx,four csvs}"
    result: "xlsx 946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535; historical FDA f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002"
  - claim: "Historical FDA CSV is 15700 rows with 4404 left-shifted (28.1%)."
    command: "python3 csv.reader; first field not digit"
    result: "HEADER 13 cols; ROWS 15700 SHIFTED 4404 PCT 28.1"
  - claim: "collectors/biocatalyst/ has no openfda_regulatory module."
    command: "ls collectors/biocatalyst/"
    result: "__init__.py clinicaltrials_discovery.py clinicaltrials_fixed_cohort.py clinicaltrials_history.py clinicaltrials_v2.py drugs_at_fda.py"
  - claim: "drugs_at_fda remains dark; pdufa_date stays forbidden; soak window unchanged."
    command: "python3 -c yaml.safe_load config/biocatalyst_sources.yml config/biocatalyst_launch_slo_manifest.yml"
    result: "production_ingest_allowed false; prohibited_claims includes pdufa_date; soak_scheduled 2026-08-12T02:00:00Z→2026-08-26T02:00:00Z"
  - claim: "Nine xlsx sheets, no hidden sheets, column names match freeze §5."
    command: "python3 openpyxl.load_workbook data_only=True"
    result: "Device Catalysts 11×12 through Earnings Calendar 504×13; hidden=[]"
unverified:
  - claim: "Sol accepts RECON-1 as the first vertical."
    what_would_verify: "Sol reply on WS:BPC-JV-RECON needs_ceo; until then RECON-1 stays todo."
  - claim: "yfinance P/B coverage includes biotech/small-cap names on the JV sheets."
    what_would_verify: "Intersect Device Pipeline tickers with engine/stock_fundamentals.py price_to_book coverage; not run."
decisions:
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-OPENFDA-PRODUCER-IS-STUB"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
unresolved:
  - "Sol ruling on needs_ceo: RECON-1 vs device/CDRH vs PDUFA NLP vs hold."
  - "Whether drugs_at_fda rights_state advances beyond review_required_before_b4 (not requested for RECON-1)."
  - "Device-applicant to issuer join remains unbuilt; not started."
next_actions:
  - "Wait for Sol review of this freeze PR. Do not arm merge-on-green. Do not squash-merge."
  - "On Sol PASS of RECON-1: open a new claude/bpc-recon-1 worktree from fresh origin/main and execute freeze §11 (hermetic Drugs@FDA matcher, unshift fixture, context consumer, no live ZIP ingest, no soak edits)."
  - "On Sol choosing a different vertical: supersede DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE before writing code."
do_not_redo:
  - "Do not re-hash the 2026-08-17 authorized dump; freeze §1 hashes were re-verified 2026-08-18."
  - "Do not re-count the Historical FDA 28.1% left-shift (4404/15700)."
  - "Do not rewrite biopharmcatalyst_benchmark permitted_uses or prohibited_uses."
  - "Do not inspect, scrape, or depend on BPC's private continuous API."
  - "Do not commit BPC row dumps or unauthorized scraped_*.json files."
  - "Do not modify b2_history_canary, BIOCATALYST_HISTORY_ENABLED, or the soak window."
  - "Do not stuff PDUFA/device/conference into evt_cik…_fy_action fiscal ids."
  - "Do not treat collectors.biocatalyst.openfda_regulatory as implemented."
  - "Do not treat Market Memory W1A as a historical PIT price source for past catalysts."
  - "Do not build LoA/LoP or a community-vote scraper as the first vertical."
danger_areas:
  - "A write into a sparse worktree omitted data/ or site/ tree truncates the committed artifact. RECON-1 must not git add -A under data/."
  - "Export-time Price, IV, OI, expected move, and market cap on Catalyst Impact / Device Pipeline will look like useful features. Joining them onto 2009–2026 Historical FDA rows is the poison-list failure mode."
  - "Sibling biocatalyst-p0-* worktrees own the soak. Editing collectors/biocatalyst/clinicaltrials_*.py from this workstream will collide."
  - "open PRs #5821 (BCI architecture) and #5901 (Capital Structure V2 freeze) are adjacent docs; do not duplicate their owner planes."
  - "event_workspace.v1 claim_citations_pending must stay True; a catalyst PR that sets it False to 'complete' the workspace is a contract break."
---

## §0 State — what is true right now

RECON-0 is written. The freeze, the distinct `biopharmcatalyst_jv_snapshot` source
identity, the three decisions, and the three discoveries are in this PR. No producer
ran. The CT.gov record-history canary and the 2026-08-12→08-26 soak window were not
edited. The next move is Sol's: accept RECON-1 as the first vertical, or name a
different one.

## §1 What is LEFT — in order

1. Sol answers `needs_ceo` on `WS:BPC-JV-RECON` (RECON-1 vs device/CDRH vs PDUFA NLP vs hold).
2. If PASS: new worktree `claude/bpc-recon-1` from fresh `origin/main`; execute freeze §11.
3. If a different vertical: supersede `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` first.
4. Do not merge this freeze PR until Sol has reviewed it. Do not arm `merge-on-green`.

## §2 What will bite you

The Historical FDA CSV cannot be matched raw: 28.1% of rows are left-shifted
(`DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT`). Catalyst Impact's IV/OI/expected-move
columns are tonight's Polygon EOD overlay, not pre-event features
(`DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT`). The YAML producer
`collectors.biocatalyst.openfda_regulatory` is a stub
(`DSC:BPC-OPENFDA-PRODUCER-IS-STUB`). Occupied checkouts may still hold unauthorized
`scraped_*.json` files — they are not this freeze's evidence.

## §3 What was decided and found

- `DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK` — new source id; benchmark YAML unchanged.
- `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE` — share envelope, not `fy_action` ids.
- `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` — first vertical is hermetic Drugs@FDA Approved matching.
- `DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT` — unshift 4404 rows before matching.
- `DSC:BPC-OPENFDA-PRODUCER-IS-STUB` — device/openFDA work is net-new.
- `DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT` — dated OHLCV is non-W1A.

## §4 Not in scope — do not adopt

No runtime collector, no soak change, no Prophet flag, no LoA model, no live
Drugs@FDA ZIP ingest, no committing BPC rows, no BPC continuous API, no second
event bus, no duplicate SEC ingest, no merge of this PR before Sol review.
