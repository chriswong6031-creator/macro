---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "Fable orchestrator (V4-D2B3 implementation; one Sonnet builder, fresh Opus reviewer x3 rounds)"
model: fable
ended_because: complete
mission: >
  V4-D2B3 implementation (Sol GO 2026-08-22, §0 gate closed by Sol adjudication:
  D2B2-US DONE/PROVEN_LIVE off the natural 2026-08-22 chain — Data OS generated_at
  01:07:17 -> GMI natural computed_at 04:50:47Z nightly/nightly, reconciled us
  RESOLVED 1210 / NOT_IN_MASTER 25 / DEFERRED 1 / ENTITY_TYPE_CONFLICT 1). Implement
  research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md VERBATIM incl.
  AMENDMENTS §1-§2 (amendments win over base prose): retire the historical
  co:us:GOLD fossil and the co:us:IBIT company-kind node, correct their edges via
  the existing (edge_id,belief_time) lineage, make the bake structurally
  conflict/retirement-aware, preserve every historical belief, leave Data OS
  untouched.
state_before: >
  At origin/main 2a728891a656 (contract merged in #6221, squash 1fb517a77e2d;
  zero implementation). Graph: co:us:GOLD canonical epoch-1 fossil with its
  gold_miners MEMBER_OF edge still latest-belief-open; co:us:IBIT company node
  coexisting with lawful etf:IBIT; no co:us:ABX; zero retired nodes anywhere;
  edges==edges_latest_belief 8292 (closure lineage production-unused); no
  node_lifecycle table; no ratified_at in the breaks registry; guard had no
  retirement/conflict invariants; bake had no suppression pass. WS d2 entry
  still read D2B2-US BUILT_NOT_PROVEN.
changed:
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: >
      Recorded Sol's D2B2-US NATURAL-PROOF ADJUDICATION (DONE/PROVEN_LIVE, exact
      production receipt) + D2B3 implementation gate OPEN in the d2 wave entry.
  - path: engine/theme_graph/store.py
    what: >
      node_lifecycle.parquet sibling table (KEY=(node_id,computed_at), schema
      gmi.node_lifecycle/v1, contracts/theme_graph/node_lifecycle.v1.schema.json),
      lane-gated write_node_lifecycle(), read_node_lifecycle(latest=True)
      latest-by-computed_at collapse, read_nodes(current: bool = False) —
      raw default byte-stable, current=True overlays status/retire_date/merged_into.
  - path: engine/theme_graph/materialize.py
    what: >
      R-A1 POST-PASS structural suppression after all suites/local planes: company
      nodes colliding with the same-build etf symbol set AND edges src'd from them
      are removed with one typed company_mint_refusals receipt each (etf_conflict);
      retired-remint refusal per R-A6 (typed receipt, NEVER raises). Materialize
      stays pure — build() gains retired_node_ids, read by scripts/build_theme_graph.py
      from the store and passed in.
  - path: scripts/check_theme_graph_contracts.py
    what: >
      Fail-closed lifecycle schema/enum validation; break-retirement invariant
      (absent prior passes — ABX shape); retired-consistency invariant (retired src
      with open latest-belief MEMBER_OF = breach); R-A9 unconditional ratified_at
      fail-closed; matrix-7 backdating breach (computed_at < cited break's
      ratified_at); NEW registry-independent conflict-retirement invariant
      (unretired company/etf same-symbol collision = breach — makes the IBIT half
      load-bearing; adjudicated addition from review round 1). Selftest fixtures
      for every breach class, both directions.
  - path: config/theme_graph_identity_breaks.yml
    what: "Additive ratified_at: 2026-08-14 on both ratified rows (R-A4); loaders read named keys only."
  - path: scripts/correct_gmi_identity_lineage.py
    what: >
      NEW one-shot curated correction script — breaks-registry/structure-driven,
      zero ticker literals in logic, imports only identity+store (Data OS
      non-interference test-pinned), idempotent (re-run: skipped_already_retired,
      zero digest movement). Executed ONCE this session.
  - path: data/theme_graph/
    what: >
      Correction artifacts: node_lifecycle.parquet NEW (exactly 2 rows — co:us:GOLD
      retired retire_date=2025-12-02 verbatim break_date reason=identity_break;
      co:us:IBIT retired retire_date=2026-08-22 reason=entity_type_conflict);
      edges.parquet +2/-0 (GOLD gold_miners edge truncated valid_to=2025-12-02;
      IBIT crypto_rails edge ANNULLED valid_to=valid_from=2023-05-09); evidence
      +2/-0; _meta.json counts refreshed + correction_receipt (transient by design —
      next nightly lawfully drops it; durable record is node_lifecycle.parquet).
      nodes.parquet/identity_resolution.parquet/capability.parquet byte-identical
      (set-diff-proven vs base 7cb39c7f9310). ABX: lawful no-op, nothing minted.
  - path: scripts/theme_coverage_gaps.py
    what: "Flipped to read_nodes(current=True) + retired-like filter — retired nodes are not coverage gaps (§11)."
  - path: tests/test_theme_graph_lifecycle.py
    what: >
      26 tests: full §10 hostile matrix 1-14, R-A1's two mandatory cross-day tests,
      etf_conflict two-consecutive-day fence, matrix-13 first-divergence pin
      (append-only-lawful assertions only), epoch routing from the real registry,
      correction-script no-op/idempotency/import-fence pins. Wired into
      .github/ci/legacy-jobs.yml (audit_unrun_tests clean).
verified:
  - claim: "Full targeted theme-graph battery green at head"
    command: "TZ=UTC python3 -m pytest tests/test_theme_graph_{identity,materialize,contracts,crosswalk,local_plane,lifecycle}.py tests/test_theme_sources_registry.py tests/test_cn_limit_rules.py tests/test_gh_annotation_line_start.py -q"
    result: "314+ passed (26/26 lifecycle at final head after the round-2 repair)"
  - claim: "Guard green on the corrected committed store; every breach class fires"
    command: "python3 -m scripts.check_theme_graph_contracts --strict; --selftest"
    result: "exit 0; selftest OK. Reviewer mutation battery: backdated computed_at, dropped GOLD row, re-opened annulled edge, stripped ratified_at, orphan row, corrupt parquet, dropped IBIT row (post-FIX-3) — ALL fired; corrupt file fail-closed"
  - claim: "No resurrection under a real simulated next-day natural bake"
    command: "reviewer probe: materialize.build(belief_time=2026-08-23, retired_node_ids=...) over a tmp copy with 6,234-edge hostile source drift"
    result: "delta touching corrected edge_ids: []; GOLD/IBIT company nodes computed: []; refusal receipt present; us idres {RESOLVED 1210, NOT_IN_MASTER 25, DEFERRED 1} == R-A2 frozen expectation exactly"
  - claim: "Blast radius exactly as frozen"
    command: "NaN-safe set-diff vs true pre-correction base 7cb39c7f9310"
    result: "nodes/identity_resolution/capability byte-identical; edges +2/-0; evidence +2/-0; lifecycle 2 rows; edges 8294 vs edges_latest_belief 8292 stable"
  - claim: "Data digests unmoved by the fix passes"
    command: "sha256sum data/theme_graph/*.parquet _meta.json across all three snapshots"
    result: "byte-identical throughout rounds 2-3"
unverified:
  - "Natural-nightly survival on REAL production artifacts (§13 DONE) — by construction only measurable after the next natural GMI cycle post-merge."
  - "Full repo suite — forbidden in a sparse tree; 9 targeted suites + guard ran instead."
unresolved:
  - "Pre-existing red NOT of this branch: tests/test_theme_graph_identity_resolution.py TestD2B2US::test_cn_hk_resolution_unchanged_by_the_us_admission asserts 987==984 (cn RESOLVED moving-data pin broken by the 08-22 nightly; fixture reads committed parquet byte-identical to base). Needs its owning lane's re-pin."
  - "Pre-existing: 5 tests/test_house_law_registry.py failures naming 4 scripts absent from this diff."
next_actions:
  - "After merge: watch the next natural GMI nightly; grade against R-A2's frozen expectation (retired standing, refusal receipt in real _meta.json, us {1210/25/1/0}, gold_miners current view without open GOLD edge); then return to Sol for D2B3 DONE/PROVEN_LIVE."
  - "D2C/D2D/D2E/D3/D5/Canada remain NOT authorized — Sol reviews after this child."
do_not_redo:
  - "Do not 'fix' edges > edges_latest_belief back to equality — lawful first production use of the closure lineage; the divergence grows nightly."
  - "Do not re-run the correction script expecting changes — idempotent, correction committed."
  - "Do not pin global edge-history deltas or multi-belief edge_id sets in tests — changed_edges lawfully appends later-belief rows every nightly (round-2 NEW-DEFECT, repaired 11ba026c4989)."
  - "Do not assert correction_receipt presence in _meta.json — the nightly rewrites _meta wholesale and drops it by design."
  - "Do not byte-compare parquets via a pandas round-trip — to_parquet does not reproduce identical bytes; restore via git checkout."
  - "Do not zero GOLD/B DEFERRED_IDENTITY_EXCEPTION or historical IBIT ENTITY_TYPE_CONFLICT sidecar rows — lawful end-state (§7/R-A3)."
  - "Natural sidecar DEFERRED 2->1 (GOLD absent) is R-A2 population mechanics, NOT a regression."
danger_areas:
  - "Conflict-retirement invariant blast radius (ACCEPTED design): any future unretired company/etf same-symbol collision in raw nodes.parquet hard-reds --strict until a curated lifecycle retirement lands — loud fail-closed surfacing is the IBIT lesson as law. Today: 55 etf symbols, 1 collision (retired), 0 near-misses."
  - "Bare-symbol (not market-scoped) suppression matching is the R-A1 frozen shape; cross-market shares suppress with only a ::notice. Bounded today (CA .TO suffixes, CN/HK numeric). Reopen only via contract amendment."
  - "data/theme_graph artifacts in this PR conflict with any nightly graph write while the PR is open — ship same-day; on conflict re-run the correction over merged store, never pick-a-side (D2B1 trap)."
---

# V4-D2B3 implementation — GMI Identity Correction Lineage (GOLD reuse + IBIT entity kind)

Implements the frozen D2B3 contract (merged #6221) under Sol's 2026-08-22 GO. Eight
commits on `claude/v4-d2b3-gmi-identity-correction`. Review record: fresh-context Opus
adversarial review round 1 = FAIL (no BLOCKER — every substantive attack survived; 2
MAJOR + 4 MINOR in the proof layer), adjudicated fix pass by the same builder, round 2
= five fixes durable + one NEW-DEFECT (matrix-10 moving-data pin), repaired by the
orchestration seat with the reviewer's probe-proven subset form and adjudicated CLOSED.
Merge = BUILT_NOT_PROVEN; the natural-nightly proof and Sol's DONE adjudication are the
next session's charter. Frontmatter carries the full changed/verified/do_not_redo/danger
record — cold-stranger sufficient.
