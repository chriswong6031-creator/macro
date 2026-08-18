---
workstream: WS:PROPHET-US-V4-RECOVERY
session: claude/prophet-v4-d2a-identity-bridge
model: fable
ended_because: complete
mission: >
  V4-D2A (first child of the Sol-recut d2): ship the canonical identity authority
  bridge — a machine can ask which Data OS issuer/security/listing any GMI company
  node resolves to at a requested as-of date, or receive a typed refusal — without
  changing node ids, without ticker fallback, without touching membership, rank,
  gates, or ThemeState.
state_before: >
  Post-D1 record said d2 executes inside GMI with Gate 1 joining through
  stock_identity. Sol's D2A commission amended that: fresh archaeology showed the
  declared exact-identity master is the Mastermind Data OS spine
  (config/identity_seams.yml; lib/dataos/identity.py; data/reference master/aliases),
  the GMI co:market:symbol#epoch ids are KNOWINGLY-DIFFERENT topology ids, and
  Stock Identity is behavioral/expert-routing. The graph's 2,806 company nodes were
  ticker-string-keyed with no resolution plane; the master (703 rows, 100% US,
  authority display_only) had no real consumer.
changed:
  - path: engine/theme_graph/identity_resolution.py
    what: deterministic 7-rule resolver (closed 7-state enum, two-clock alias law,
      cross-market agreement check) + reader API resolve_graph_node_identity /
      read_identity_resolution; first real consumer of lib.dataos.identity
  - path: contracts/theme_graph/identity_resolution.v1.schema.json
    what: gmi.identity_resolution/v1 row contract (19 columns)
  - path: engine/theme_graph/store.py
    what: additive writer/reader for the sidecar (capability pattern, lane-gated)
  - path: engine/theme_graph/materialize.py
    what: additive derive rule; resolution_asof = generation belief_time
  - path: scripts/build_theme_graph.py
    what: additive wiring after write_capability; counts into _meta.json
  - path: scripts/check_theme_graph_contracts.py
    what: identity section — orphan/missing-row breaches (strict), state-ids
      biconditional, RESOLVED-ids-in-master, absent-file notice, always-on census;
      selftest fixtures
  - path: config/identity_seams.yml
    what: one additive ADOPT row for the new reader (delegates to the master)
  - path: data/theme_graph/identity_resolution.parquet
    what: first real bake, 2,806 rows (701 RESOLVED / 1,869 NOT_IN_MASTER /
      233 UNSUPPORTED_MARKET / 2 DEFERRED / 1 ENTITY_TYPE_CONFLICT)
  - path: research/prophet_v4/d2/
    what: D2A_FROZEN_CONTRACT_2026-08-18.md (+post-review amendments) and
      D2A_COVERAGE_RECEIPT_2026-08-18.md (cohort tables, reconciliation, D2B gap)
  - path: research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md
    what: Gate 1 supersession note (Sol identity-authority amendment)
  - path: research/prophet_v4/CONTRACT_AND_OWNER_MAP.md
    what: exact-identity authority row (Data OS spine); boundary clarifications
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: d2 in_progress with the recut + amendment; d3/d5 rows record Sol's
      accepted adjudications
  - path: agentos/discoveries/DSC-THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY.md
    what: new landmine — full pipeline re-bake diverges in a session worktree
  - path: tests/test_theme_graph_identity_resolution.py
    what: hostile fixtures against real stores, mutation tests, two-clock probes,
      full-population sweeps, committed-artifact reproducibility test
verified:
  - claim: all D2A test modules green
    command: python3 -m pytest tests/test_theme_graph_identity_resolution.py tests/test_theme_graph_contracts.py tests/test_theme_graph_materialize.py tests/test_identity_seam_agreement.py tests/test_gh_annotation_line_start.py -q
    result: 130 passed
  - claim: strict guard green on the committed bake with the census printed
    command: python3 -m scripts.check_theme_graph_contracts --strict
    result: exit 0; census 2806 rows, 701/1869/233/2/1; same-security node-sets SATS+ECHO, FI+FISV
  - claim: protected planes byte-identical to HEAD
    command: git hash-object on nodes/edges/evidence/capability.parquet vs git rev-parse HEAD (adversarial review attack 19)
    result: all four IDENTICAL; lib/dataos, data/reference, engine/stock_identity untouched
  - claim: opus 30-attack battery run and dispositioned
    command: reviewer packet + post-fix re-verification (same reviewer)
    result: 27 attacks failed outright; F2 BLOCKER (historical-asof two-clock collapse) + F1 + F3 fixed in-PR; F4/F5 minor fixes applied
  - claim: RESOLVED count reconciles with the independent pre-bridge estimate
    command: Scout D census vs baked parquet (coverage receipt section 2)
    result: 703 naive-matchable − GOLD (exception) − IBIT (conflict) = 701; no unexplained residue
unverified:
  - claim: byte-level reproducibility of the committed sidecar via the FULL pipeline
    what_would_verify: nothing in a session worktree — see DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY; the reproducibility test re-derives via derive_rows over committed inputs instead, which is the honest local check
unresolved:
  - "D2B queue: 1,869 NOT_IN_MASTER rows (master covers 21-57% of any V4 population); expansion path (DataOS-owned PR vs GMI correction PR split) is Sol's call after this return."
  - "GOLD membership-edge defect and IBIT entity-kind repair: D2B lineage work, deliberately untouched here."
  - "Reader has no non-test caller yet (expected at D2A); D3's contract should make the reader-only join rule mechanical, not prose (review F5 advisory)."
next_actions:
  - "Merge the D2A PR (this session owns it to merge; authority-changing — needs main actually green)."
  - "Return to Sol with the section-20 packet; Sol decides D2B commissioning and the one-vs-two-PR split."
  - "No D2B/D2C/D2D/D2E/D3/D5 work in this session."
do_not_redo:
  - "Do not re-litigate the identity authority: Data OS spine is the exact-identity master (Sol D2A amendment); the old stock_identity Gate 1 wording is SUPERSEDED, not missing."
  - "Do not 'fix' B/GOLD/IBIT in the bridge — B and GOLD are receipt-declared identity exceptions, IBIT is a deliberate ENTITY_TYPE_CONFLICT; repair is D2B lineage work."
  - "Do not expand the master or edit data/reference/** from a GMI/V4 session — D2B decides the expansion path."
  - "Do not re-measure the D2B gap by hand — every NOT_IN_MASTER sidecar row is the queue with receipts attached."
danger_areas:
  - "DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY — never regenerate graph planes via the full scripts.build_theme_graph in a session worktree; derive the target plane from the committed nodes.parquet."
  - "Historical asof resolutions use DATED alias rows only (post-F2 two-clock law); current-catalog rows (store/yahoo_fetch, both bounds null) are excluded as historical evidence — do not optimize that exclusion away."
  - "source_native_symbol is parse provenance, never a join key; the reader API is the only sanctioned resolution path."
prs: [5894]
---

## Cold-stranger summary

Sol recut D2 into child slices and corrected the identity authority: exact
issuer/security/listing identity comes from the Data OS spine, GMI keeps its topology
node ids, and D2A bridges the two planes with an additive resolution sidecar. The bridge
is live in the committed artifact: 2,806 company nodes each carry a typed resolution row
(701 resolve; 1,869 honestly NOT_IN_MASTER — the measured D2B queue; B/GOLD deferred by
receipt; IBIT surfaced as an entity-kind conflict; SATS/ECHO and FI/FISV exposed as two
topology nodes over one security). The guard fails strict if any company node lacks a
row, if ids contradict the state, or if a RESOLVED id is not in the master. Start at
`research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md`; every count has a reproduce
command in the coverage receipt.
