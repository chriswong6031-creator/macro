---
workstream: WS:BPC-JV-RECON
session: claude/bpc-recon-0
model: fable
ended_because: complete
mission: >
  Soak-safe freeze closure on PR #5909. Revert live source-registry mutation
  and new JV registry tests. Keep accepted architecture. Add sequencing law
  that runtime registration waits for the post-soak successor registry /
  successor launch-manifest transition. Do not start SNAPSHOT-ONBOARD,
  CONTINUOUS-RECON, or runtime work. Do not reopen architecture.
state_before: >
  Sol-accepted architecture was still inserting biopharmcatalyst_jv_snapshot
  into the live soak-bound config/biocatalyst_sources.yml. Semantic CI found a
  direct pr_regression because the launch SLO manifest hash-binds those
  predecessor bytes.
changed:
  - path: config/biocatalyst_sources.yml
    what: Reverted this PR's modifications; file matches the soak-bound predecessor on origin/main.
  - path: tests/test_biocatalyst_source_registry.py
    what: Reverted the four new JV runtime-registry tests; pre-existing tests preserved.
  - path: agentos/decisions/DEC-BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK.md
    what: New Sol sequencing DEC — canonical identity frozen now; runtime insertion deferred.
  - path: agentos/decisions/DEC-BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK.md
    what: Answer records deferred runtime insertion; evidence no longer cites a live YAML JV row.
  - path: agentos/decisions/DEC-BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN.md
    what: Evidence no longer cites live YAML/tests; decided_by remains chairman.
  - path: research/BPC_RECON_0_JV_SNAPSHOT_ARCHAEOLOGY_AND_SOURCE_SYSTEM_RECONSTRUCTION_FREEZE_2026-08-18.md
    what: Soak-safe freeze; sequencing law; §14 no longer claims the live registry already holds the JV identity.
  - path: agentos/workstreams/WS-BPC-JV-RECON.md
    what: Sequencing landmine; new DEC listed; status/waves unchanged.
  - path: agentos/handoffs/BPC-JV-RECON-2026-08-18.md
    what: Handoff rewritten for soak-safe closure.
prs: [5909]
verified:
  - claim: "config/biocatalyst_sources.yml matches origin/main (no JV identity, no licensed_finite_snapshot class)."
    command: "git diff origin/main -- config/biocatalyst_sources.yml"
    result: "empty"
  - claim: "New JV runtime-registry tests are gone; pre-existing source-registry tests remain."
    command: "git diff origin/main -- tests/test_biocatalyst_source_registry.py"
    result: "empty"
  - claim: "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN decided_by remains chairman."
    command: "python3 -c yaml frontmatter"
    result: "decided_by: chairman"
  - claim: "AgentOS records validate (0 errors)."
    command: "python3 scripts/agentos.py validate"
    result: "236 records (28 workstreams, 77 decisions, 62 discoveries, 69 handoffs) — 0 error(s), 13 warning(s); warnings are unrelated phantom-owns-path / active-but-complete"
  - claim: "Focused source-registry tests pass without requiring the JV identity in the live registry."
    command: "python3 -m pytest tests/test_biocatalyst_source_registry.py -q"
    result: "12 passed"
unverified:
  - claim: "W4 is a superset of W1–W3 with identical common-sheet content."
    what_would_verify: "SNAPSHOT-ONBOARD census of the four File Library bytes. Not run in this PR."
  - claim: "File Library W4 bytes equal the locally hashed W4 SHA256."
    what_would_verify: "Hash File Library BioPharmCatalyst_Tables(3).xlsx when bytes are in an implementation environment."
decisions:
  - "DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN"
  - "DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK"
  - "DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK"
  - "DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE"
  - "DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE"
discoveries:
  - "DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT"
  - "DSC:BPC-OPENFDA-PRODUCER-IS-STUB"
  - "DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT"
  - "DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK"
unresolved:
  - "UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS — whether W4 is a superset of W1–W3 with identical common-sheet content."
  - "Post-soak successor source-registry / successor launch-manifest insertion of biopharmcatalyst_jv_snapshot — not this PR."
  - "Whether drugs_at_fda rights_state advances beyond review_required_before_b4 (not requested in this PR)."
next_actions:
  - "After #5909 merges, return to Sol for commissioning of the first bounded SNAPSHOT-ONBOARD vertical. Do not begin it from this PR."
  - "Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, Drugs@FDA work, device/CDRH, PDUFA work, or any runtime implementation from this PR."
  - "Keep merge-on-green off on #5909."
do_not_redo:
  - "Do not re-hash the locally verified W4 workbook and four CSVs; freeze §1 hashes stand."
  - "Do not re-count the Historical FDA 28.1% left-shift (4404/15700)."
  - "Do not call W4 a proven superset of W1–W3, and do not call W1–W3 lost."
  - "Do not treat W1→W4 as four temporal vintages unless a later census proves time-varying common-sheet content."
  - "Do not invent predecessor SHA-256 values from File Library metadata."
  - "Do not mutate the soak-bound predecessor source registry or re-hash the active launch manifest during soak."
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
  - "The launch SLO hash-binds the entire predecessor source registry. Any live YAML mutation during soak is a pr_regression."
  - "A write into a sparse worktree omitted data/ or site/ tree truncates the committed artifact."
  - "Export-time Price, IV, OI, expected move, and market cap on Catalyst Impact / Device Pipeline will look like useful features. Joining them onto 2009–2026 Historical FDA rows is the poison-list failure mode."
  - "Sibling biocatalyst-p0-* worktrees own the soak. Editing collectors/biocatalyst/clinicaltrials_*.py from this workstream will collide."
  - "Do not re-arm merge-on-green on #5909."
  - "event_workspace.v1 claim_citations_pending must stay True."
  - "DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK stays local-bounded."
---

## §0 State — what is true right now

Sol accepted the RECON-0 architecture. Semantic CI then found a soak-bound
registry hash miss. This head makes #5909 a soak-safe architecture freeze:
canonical identity `biopharmcatalyst_jv_snapshot` is frozen in freeze/DECs/WS;
the live source registry is the unchanged predecessor; runtime registration
waits for the post-soak successor transition. RECON-0 remains done. SNAPSHOT-ONBOARD
and CONTINUOUS-RECON remain todo. Matcher-only RECON-1 stays dropped.

## §1 What is LEFT — in order

1. Merge PR #5909 after CI/fences and semantic ci-gate show no #5909-attributable pr_regression. Keep `merge-on-green` off.
2. After merge, return to Sol for commissioning of the first bounded SNAPSHOT-ONBOARD vertical.
3. Do not start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, Drugs@FDA work, device/CDRH, PDUFA work, or any runtime implementation from this PR.

## §2 What will bite you

The Historical FDA CSV cannot be matched raw: 28.1% of rows are left-shifted.
W1–W3 were absent from the operator filesystem searched 2026-08-19 but still
exist in the Chairman's File Library. The soak-bound predecessor registry must
not be mutated. Export-time IV/OI/expected-move columns are capture-time
overlays, not pre-event features.

## §3 What was decided and found

- `DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN` — Chairman authority; `decided_by: chairman`.
- `DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK` — distinct canonical identity; runtime row deferred.
- `DEC:BPC-JV-SNAPSHOT-RUNTIME-REGISTRY-POST-SOAK` — soak-safe sequencing; `decided_by: ceo-sol`.
- `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE` — `jv_reconciliation_match_key`.
- `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` — calibration component, not program completion.

## §4 Not in scope — do not adopt

No runtime collector, no soak change, no live YAML JV row, no machine-enforced
JV source-registry tests in this PR, no launch-manifest re-hash, no Prophet
flag, no snapshot ingest, no SNAPSHOT-ONBOARD or CONTINUOUS-RECON start, no
`merge-on-green`.
