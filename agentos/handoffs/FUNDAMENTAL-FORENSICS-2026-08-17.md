---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-1-broad-sec
model: local
ended_because: complete
mission: >
  FF-1 Incremental Broad SEC Source Plane after FF-0 live smoke closed.
  One PR, no merge, no FF-2, no FF-0 edits. Stop after implementation,
  acceptance evidence, CI ownership/trigger closure, this handoff, and an
  open PR returned to Sol for review.

state_before: >
  FF-0 is CLOSED. Operator-signed production smoke on 2026-08-17: signed-in
  GET /api/forensics/health 200, Cache-Control private/no-store, status=stale
  reason_code=SOURCE_STALE, broad_source_at=2026-07-12T11:23:15Z distinct from
  evaluated_at, and desktop Open signal analysis opens the visible drawer.
  No FF-1 source plane existed. Wave-2 remains the 12-ticker SEC lane under
  concurrency group filing-forensics-sec.

changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: "Incremental broad SEC poll kernel. Universe bind from
      data/edgar/fundamentals.parquet (fail-closed on empty, malformed CIK,
      duplicate ticker/CIK, oversize). Content-addressed objects under
      fundamental_forensics/broad-sec/v1/. Company Facts only when relevant
      10-K/10-Q/20-F/40-F accession set changes. Poll clocks never enter
      source identity. latest-complete advances only after every expected
      issuer is observed."
  - path: collectors/edgar_forensics.py
    what: "Small retrieve_current hook. Same retry/pacing/stream caps as fetch,
      without writing the Wave-2 raw tree."
  - path: scripts/run_fundamental_forensics_broad_sec.py
    what: "CLI. Repo-root pin before imports. Schedule is incremental only;
      recovery requires --recovery-from. Samples poll_started_at before work;
      recorded_at and poll_completed_at are sampled inside the kernel after
      issuer I/O. Does not stamp one retrieved_at onto every fetch."
  - path: contracts/fundamental_forensics_broad_sec_run.schema.json
    what: "Draft 2020-12 run receipt. additionalProperties false."
  - path: contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json
    what: "Draft 2020-12 issuer source manifest. Company Facts snapshot_kind is
      current_observed; no as_of."
  - path: .github/workflows/filing-forensics-broad-sec.yml
    what: "Scheduled 03:15 UTC incremental poll. Shares concurrency group
      filing-forensics-sec, cancel-in-progress false. Recovery only via
      workflow_dispatch. No continue-on-error. Off daily.yml."
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: "Acceptance: two-run idempotence, one new 10-Q, amendment lineage,
      cutoff withholding, Company Facts never as-of, partial/complete-head,
      429/5xx reuse, oversize/invalid/wrong-URL, CAS readback, queue overflow,
      historical_submissions_required."
  - path: tests/test_filing_forensics_broad_sec_lane.py
    what: "Lane pins: off render path, shared concurrency group, schedule cannot
      enter recovery, hard gate."
  - path: .github/ci/legacy-jobs.yml
    what: "Named both new suites on the existing engine-render-guards pytest
      line. No new job, no new pip dependency."
  - path: .github/workflows/ci.yml
    what: "Explicit path entries for the runner, workflow, lane test, and two
      contracts. engine/fundamental_forensics/** already covers the kernel."
  - path: config/dag.yml
    what: "Declared poll_broad_sec lane for the new workflow."
  - path: config/r2_delivery_plane_classification.v1.json
    what: "New VENDOR_RAW family fundamental_forensics_broad_sec_source for
      PRIVATE_STORE:fundamental_forensics/broad-sec/v1/**. Did not overload
      Wave-2 sec-source/v1."
  - path: tests/fixtures/r2_delivery_macro_evidence_files.v1.tsv
    what: "Receipt for engine/fundamental_forensics/broad_sec_store.py."
  - path: tests/fixtures/r2_delivery_macro_anchor_lines.v1.tsv
    what: "PREFIX fingerprint at line 50."
  - path: research/R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md
    what: "Family count 105→106; VENDOR_RAW 11→12."
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: "FF-0 done; FF-1 awaiting_ci; FF-2 todo and forbidden until Sol
      reviews FF-1."

verified:
  - claim: "Entry script pins repo root before repo imports. Kernel still has no datetime.now/utcnow."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_check_script_import_pinning.py::test_unpinned_entry_scripts_only_shrink tests/test_fundamental_forensics_contract.py::test_kernel_sources_do_not_use_an_implicit_current_clock -q"
    result: "passed in the combined pin/clock/census run"
  - claim: "Repaired FF-1 acceptance: honest CLI clocks, empty-store recovery bootstrap without mass Company Facts, accumulate-only accession ledger, >64-issuer recovery convergence, compact heads, PIT fail-closed, noncanonical universe cannot advance latest-complete."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_fundamental_forensics_broad_sec.py tests/test_filing_forensics_broad_sec_lane.py -q"
    result: "30 passed"
  - claim: "R2 census receipt for engine/fundamental_forensics/broad_sec_store.py re-pinned at PREFIX line 50."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_r2_delivery_plane_classification.py::test_all_evidence_anchors_are_pinned_to_reproducible_file_receipts -q"
    result: "passed after TSV update"
  - claim: "Two-issuer live SEC canary against a local temp store: incremental established submissions baselines with zero Company Facts; recovery from 2026-07-12T11:23:15Z fetched Company Facts for both AAPL and MSFT; Submissions and Company Facts retrieval clocks were distinct; no production R2 write."
    command: "local two-issuer live_fetchers canary (AAPL/MSFT, LocalStore, no R2)"
    result: "incremental complete cf_fetched=0; recovery complete cf_fetched=2 bytes=8670295; AAPL sub_at 13:20:10Z cf_at 13:20:11Z recorded 13:20:12Z"

  - claim: "Existing edgar collector fetch contracts still pass after retrieve_current was extracted from the same retry loop."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_edgar_forensics_collector.py -q"
    result: "included in the 152-pass combined run"
  - claim: "Private-plane census, trigger-closure, and DAG conformance hold for the new family, suites, and workflow."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_r2_delivery_plane_classification.py tests/test_ci_trigger_closure.py tests/test_dag_conformance.py -q"
    result: "included in the 152-pass combined run; check_dag_conformance.py reports filing-forensics-broad-sec.yml / poll_broad_sec OK"
  - claim: "AgentOS records validate."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python scripts/agentos.py validate"
    result: "0 error(s), 11 pre-existing warning(s); exit 0"

unverified:
  - claim: "Live scheduled poll against data/edgar/fundamentals.parquet on the Studio writes a complete census to private Research R2."
    what_would_verify: "After Sol merges, the 03:15 UTC lane (or a workflow_dispatch incremental run) exits 0 and latest-complete.json exists under fundamental_forensics/broad-sec/v1/ with universe issuer_count matching the parquet."
  - claim: "Live parquet issuer count is <= HARD_MAX_UNIVERSE_ISSUERS (2500)."
    what_would_verify: "Read data/edgar/fundamentals.parquet unique ticker/CIK counts on a full checkout. This session was sparse and did not open data/."

unresolved:
  - "This session must not merge. Return the PR to Sol."
  - "FF-2 is forbidden until FF-1 is reviewed and merged."
  - "Recovery does not crawl historical Submissions shards. If the window predates filings.recent it reason-codes historical_submissions_required."
  - "Production workflow uses R2 via build_store() from R2_RESEARCH_* ; tests used LocalStore only."

next_actions:
  - "Sol reviews this FF-1 PR. Do not squash-merge from the worker session."
  - "Do not start FF-2."
  - "Do not modify FF-0."

do_not_redo:
  - "Do not write a second data.sec.gov HTTP client. retrieve_current and SecCompanyFactsCollector.fetch are the hooks."
  - "Do not point persist_response at Wave-2 latest from this plane."
  - "Do not let poll_completed_at or retrieved_at masquerade as sec_accepted_at or broad_source_at."
  - "Do not default recorded_at to poll_started_at, and do not stamp one retrieved_at onto every fetch."
  - "Do not treat prior_manifest is None as equivalent to every issuer needing Company Facts."
  - "Do not write the full run receipt into latest-observation or latest-complete; those pointers are 16KiB."
  - "Do not advance latest-complete on a partial poll."
  - "Do not overload fundamental_forensics/sec-source/v1 for this plane."
  - "Do not scale Wave-2 or invent a second 1,500-name universe JSON."

danger_areas:
  - "A write into sparse-omitted data/ truncates the committed artifact. Universe tests use tmp parquet."
  - "LocalStore conditional writes cap predecessor versioning at 16KiB. Large SEC objects are create-only (expected_version=None); pointers stay small."
  - "Shared concurrency group filing-forensics-sec serializes with Wave-2. A second group would hammer SEC."
  - "engine/fundamental_forensics/*.py still must not call datetime.now."
---
