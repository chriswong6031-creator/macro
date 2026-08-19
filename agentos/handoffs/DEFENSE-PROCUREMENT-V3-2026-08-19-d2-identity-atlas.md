# DEFENSE-PROCUREMENT-V3 — D2 Identity Atlas handoff (2026-08-19)

Ships with PR #5932 (this document exists on main only if that PR merged).
Session: Fable orchestrator, D2 directive from Sol 2026-08-18. Start-main SHA
`a7cfd4bef589f3c21be4712847ba35653a9fc995`.

## What D2 shipped

- **Graph**: `recipient-graph:reviewed:2026-08-19:defense21-v1`, digest
  `93171ba0e6f7286de02e0918ef85be7db80df3f6b7fd8eb3d47e7e8e4adfa843`
  (predecessor `defense19-v1` / `0733a966…`, every row byte-preserved,
  test-pinned). Delta: +BWXT company, +6 legal entities, +5 sam_uei
  identifiers, +6 ownership edges, +8 evidence receipts (SEC 10-K, Ex.21,
  five award records, recipient-children parent-plane record — all real
  fetched bytes through the proposer receipt seam, content-bound by
  assertions in `scripts/mint_defense21_recipient_graph.py`).
- **Atlas artifact**: `government_revenue_identity_atlas.v1` at
  `data/government_revenue/identity_atlas.json` (+ site twin
  `government-revenue-data/identity-atlas.json`, cookie plane), built by
  `engine/government_revenue/identity_atlas.py` inside
  `scripts/build_government_revenue.py` on the plane clock (a future-known
  graph degrades every issuer to not_asserted — tested).
- **Product**: Identity Atlas section in the company inspector
  (`templates/government_revenue.html.j2` + `government-revenue-dossiers.js`)
  — four-rung identity rail that visibly breaks at unresolved hops, EN/ZH,
  receipts behind expands, locked/teaser degradation, event-free by schema.
- **Pilot outcomes**: IRDM reviewed (P00032 clocks untouched) · HII reviewed
  (N0002415C2114/AZ0010 empty-impacts event still unlinked) · LMT reviewed
  (registrant + 14 identifiers unflattened; Sikorsky auto-attach forbidden by
  test; "filing-known display" is a recorded scope cut, curated-file pathway
  named in the spec) · GE `not_asserted` with separation boundary shown ·
  BWXT reviewed ×5 with 3 refused identifiers visible (1 conflict, 2 gaps) ·
  SPR `listing_terminated` historical, never live.
- Records: `DEC:D2-BWXT-EXACT-ADMISSION-GE-STAYS-UNRESOLVED`,
  `DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK`. Binding spec:
  `research/defense_intelligence/D2_IDENTITY_ATLAS_EXECUTION_SPEC.md`.

## Verified (command per claim)

- defense19 byte-preservation + digest: reviewer-independent rebuild of
  `_graph_fingerprint()` over the committed file; row-by-row deep-equal vs
  `git show origin/main:data/government_revenue/recipient_entity_graph.json`
  (0 missing / 0 changed / order-prefix true, all five tables).
- Receipts: refetch of Ex.21 + five award records + children endpoint
  (`curl` with contact UA) — byte lengths and sha256 match committed rows.
- UI↔artifact contract: `python3.12 -m pytest
  tests/test_government_revenue_identity_atlas.py -q` (27 passed) — includes
  the node-harness test rendering the SHIPPED JS factory against the
  COMMITTED artifact (IRDM/BWXT unbroken reviewed rail, GE frozen sentence,
  SPR historic, real sha256 rendering).
- Candidate gates: `python3.12 -m pytest
  tests/test_government_revenue_candidates.py -q` (41 passed) — includes the
  synthetic 2026-08-10-incident-class test proving the row-level
  discriminator fails it while excusing genuinely new paths.
- Pair sync: `python3.12 -m scripts.check_template_site_sync` (89 pairs OK).

## do_not_redo

- Do NOT re-stamp `config/government_revenue/candidate_historical_suppressions.v1.json`
  or `candidate_issuance_corrections.v1.json` to chase candidate clocks after
  a graph republish — they are an immutable sha-bound incident pair; the
  measured attempt redded 7 quarantine tests (see DSC above).
- Do NOT re-mint defense21 to "fix" the frozen-clock render gate — a re-mint
  moves the graph clock FORWARD and widens the gap; the gate clears when the
  govrev freeze commit postdates the graph clock.
- Do NOT admit MMACD85DT5D5 / PM7HBL2KDX46 / URJ3CAC3MSH8 without NEW
  evidence closing the exact hop each fails (see DEC above).
- Do NOT mine #5424's GE handling or its retained LHX/NOC `-de` /
  GM-GDLS rows — recorded defects.

## danger_areas

- `.github/ci/legacy-jobs.yml:7641` runs `test_check_government_revenue_projection.py`
  in a pack (fixture-driven, insensitive to live clocks — 35 passed), but the
  render lanes run `scripts.check_government_revenue_projection` against the
  LIVE tree; a graph republish reds that gate until main's next projection
  freeze. Sequence any future graph merge behind a freeze commit.
- The two transitional BWXT candidates (`grc1-2431cef9…`, `grc1-81a1a8df…`,
  source `CONT_AWD_89233123CNA000308`) are expected to be issued forward by
  the first post-merge projection freeze; if they are still unaccounted after
  a freeze, that is an escape, not a transition.
- Atlas `unresolved_identifiers` are curated-evidence-only by design;
  scope-observed identifiers surface as counts. Naming a scope-observed
  identifier under an issuer is the GE third-party mis-association defect.

## Next

Return to Sol with the acceptance record (graph ids/digests, pilot outcomes,
live proof). D3 (`DEFENSE_D3_TEMPORAL_EVENT_AND_CHANGE_TAPE_HANDOFF.md`)
stays unauthorized until Sol rules. #5424 disposition (close as superseded
for BWXT vs recut) is a Sol call.
