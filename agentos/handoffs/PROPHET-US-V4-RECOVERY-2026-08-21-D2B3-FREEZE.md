---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "Fable orchestrator (V4-D2B3 archaeology + contract freeze; two census scouts, opus design review)"
model: fable
ended_because: complete
mission: >
  V4-D2B3 (Sol commission 2026-08-21): correct the remaining known GMI
  company-plane identity defects through the existing append-only correction
  lineage — reused GOLD must no longer conflate prior holders with Gold.com;
  IBIT must no longer masquerade as an active company beside its ETF node.
  Precondition: D2B2-US PROVEN_LIVE from a natural GMI generation consuming
  the Aug-22+ Data OS generation. At freeze time only the Data OS half was
  proven, so per the commission this session delivered archaeology + the
  frozen contract ONLY and stopped before implementation.
state_before: >
  At origin/main 12467e2d5e9d. Graph: co:us:GOLD (canonical epoch-1 fossil,
  minted 2026-08-11, its MEMBER_OF gold_miners edge still latest belief —
  the 2026-08-14 roster repair added co:us:B's edge but never closed GOLD's),
  co:us:B (canonical, 3 edges), co:us:IBIT + etf:IBIT coexisting
  (ENTITY_TYPE_CONFLICT), NO co:us:ABX, zero retired/epoch-2 nodes anywhere.
  Store: NODE_KEY=(node_id,) keep-first — nodes write-once, NO retirement
  path exists; EDGE_KEY=(edge_id,belief_time) + latest-belief collapse — a
  tested but production-unused correction lineage (edges==edges_latest_belief
  8292). Epoch law live at mint time (materialize→identity.company_node_id
  consults ratified breaks; GOLD/ABX evidence would mint #2 today). Data OS:
  B fail-closed zero rows (DEFERRED_IDENTITY_KEYS), GOLD one disclosed-unsafe
  legacy alias row, ABX zero rows, IBIT lawfully RESOLVED as a security
  (CIK 1980994, directory etf=True). Precondition: Aug-22 Data OS generation
  landed (receipt 2026-08-22T01:07:17, us_gmi_admission 1236/1210/0 natural
  steady state); natural GMI generation consuming it NOT yet landed at freeze.
changed:
  - path: research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md
    what: >
      Fable-frozen correction design: §0 precondition gate (implementation
      blocked until D2B2-US PROVEN_LIVE, with the exact one-shot verification
      recipe); §2 mechanism rulings — node_lifecycle.parquet sibling table
      (KEY=(node_id,computed_at), latest collapse; nodes.parquet stays
      write-once/bit-identical), read_nodes(current=False default) overlay,
      edge corrections via the EXISTING (edge_id,belief_time) lineage only,
      bake gains deterministic etf-conflict mint refusal + retired-remint
      refusal (resurrection-proofing), one-shot curated correction script (no
      new timer/allocator/namespace); §3 GOLD retire@2025-12-02 verbatim from
      the ratified break row + gold_miners edge truncation, #2 NEVER
      pre-minted; §4 IBIT retirement + crypto_rails company-edge ANNULMENT
      (valid_to=valid_from, distinct law from truncation) + nightly typed
      refusal receipt, etf:IBIT preserved; §5 ABX = generality control on the
      prior-node-ABSENT shape, zero ticker literals in logic; §6 guard
      invariants (break-retirement, retired-consistency); §7 D2A sidecar
      FROZEN UNCHANGED (states/counts stay {DEFERRED:2, CONFLICT:1} — history
      preserved deliberately, D2B2 proof numbers undisturbed); §8 Data OS
      non-interference; §9 dates law (no invented dates, no backdating);
      §10 14-item hostile test matrix; §11 owned files + per-consumer
      decision table; §12-§14 acceptance/operator model/non-goals.
verified:
  - claim: >
      Node/edge/sidecar inventory for GOLD/B/ABX/IBIT as stated in contract §1
      (fossil GOLD node + open gold_miners edge; IBIT dual nodes; no co:us:ABX;
      zero retired/epoch-2 rows; 7 target edges; sidecar states 10/6/10 gens).
    command: >
      python3+pandas over data/theme_graph/{nodes,edges,identity_resolution}
      .parquet at 12467e2d5e9d (two independent census packets + orchestrator
      re-derivation of every load-bearing row).
  - claim: >
      Store mechanics: NODE_KEY write-once keep-first (store.py:103,:292-296),
      no read_nodes collapse/status filter anywhere (repo-wide grep), edge
      lineage tested (test_theme_graph_materialize.py:480-496), materialize
      hardcodes canonical (:279-280), breaks consumed at mint
      (materialize.py:252,:458/:466,:627/:645 → identity.py:122-138), guard
      enforces node⇒row epoch law only (check_theme_graph_contracts.py:544-565).
    command: grep -n / Read on the cited files (orchestrator, first-hand).
  - claim: >
      Data OS typed uncertainty verbatim: DEFERRED_IDENTITY_KEYS["B"]
      (build_security_master.py:517-532), DISCLOSED_IDENTITY_EXCEPTIONS["GOLD"]
      (:540-553); B/ABX zero rows across master/aliases/migrations; rails
      confirm all three current-holder CIKs against the ratified break rows
      (GOLD=1591588 Gold.com, B=756894 Barrick, ABX=1814287 Abacus,
      IBIT=1980994 etf=True).
    command: >
      pandas over data/reference/*.parquet + data/symbol_directory/
      {snapshots/2026-08-22,cik_map/2026-08-18}.parquet; Read on
      build_security_master.py.
  - claim: >
      Precondition state: Aug-22 Data OS generation exists (receipt
      generated_at 2026-08-22T01:07:17, us_gmi_admission 1236/1210/0);
      data/theme_graph/ last written by the D2B2 merge 71b4813266c1 — no
      natural GMI generation had consumed the Aug-22 master at freeze.
    command: >
      git show origin/main:data/reference/_receipt.json | python3 -c ...;
      git log origin/main -- data/theme_graph/ (one-shot, no polling).
next_actions:
  - >
    IMPLEMENTING SESSION (after Sol authorizes): first run the §0 one-shot
    gate — natural theme-graph bake computed_at ≥ 2026-08-22 consuming a
    master generated_at ≥ 2026-08-22, sidecar us holding D2B2 steady state.
    Gate closed → stop and report, do not poll, do not code.
  - >
    Gate open → one Sonnet builder implements the frozen contract exactly
    (§2-§11); fresh Opus reviewer attacks per §13; merge = BUILT_NOT_PROVEN;
    DONE on the next natural production GMI cycle per §13.
  - >
    The design-review packet (opus, pre-merge of this freeze) and any
    amendments it forced are recorded in the contract itself — read the
    contract as merged, not this handoff, for the binding text.
unresolved:
  - >
    Edge belief_time stability across bakes was verified only via the store
    test and dedup mechanics; the implementing builder must re-confirm at the
    emit sites that nightly re-emissions carry a STABLE belief_time (else a
    closed edge would reopen — contract matrix item 3 pins this).
unverified:
  - >
    Whether the guard's edge-interval validation accepts valid_to==valid_from
    (the IBIT annulment encoding) — contract requires the builder to make the
    guard accept-and-pin it; if the schema fights back, the amendment path is
    a typed annulment marker, adjudicated by the commissioning seat.
do_not_redo:
  - >
    Do NOT pre-mint co:us:GOLD#2 / co:us:ABX#2 (evidence-less hand-written
    rows; the live epoch law mints them when evidence arrives).
  - >
    Do NOT extend NODE_KEY with a time column (adjudicated — nightly re-mints
    would bloat ~3,878 rows/bake and resurrect retirements next bake).
  - >
    Do NOT flip status in place on nodes.parquet rows (history rewrite,
    commission-forbidden; the write-once row must stay bit-identical).
  - >
    Do NOT re-scope derive_rows population or load_gmi_us_seeds/admission
    targets to active-only in D2B3 (frozen §7/§8 — keeps D2B2 nightly proof
    numbers and strict equality tests undisturbed; a future wave's own diff).
  - >
    Do NOT treat sidecar DEFERRED(B,GOLD)/CONFLICT(IBIT) states or their
    _meta counts as defects to zero — they are the lawful preserved history.
  - >
    co:us:ABX absent is CORRECT (prior node never minted); do not "repair" it.
danger_areas:
  - >
    A `merged`/`retired` lifecycle row is only as load-bearing as its
    consumers: the §11 decision table is exhaustive at freeze time; any new
    nodes reader found during implementation gets an explicit recorded
    decision, never a silent default.
  - >
    _meta.json edges vs edges_latest_belief diverge for the first time
    (8294 vs 8292 after correction) — sweep for equality assumptions before
    merging (contract matrix 13).
  - >
    The Canada node co:ca:ABX.TO shares the ABX symbol string — every ABX
    query/test must scope market=us or it will touch the wrong node.
---

Archaeology packets (two census workers + orchestrator verification) are
summarized in contract §1; the contract is the single binding artifact. This
wave wrote NO engine/data changes — records only, by commission design
(precondition gate). Return to Sol after merge.
