---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "2930780f-f0b0-4efc-a62a-f529085b3a0d (Fable orchestrator, D2B1-R1 wave)"
model: fable
ended_because: complete
mission: >
  V4-D2B1-R1 (Sol amendment 2026-08-20): the predicted transition race fired on the
  first natural D2B1 nightly — duplicate SEC:US-XNYS-VMRK minted for the EQR→VMRK
  NYSE rename while SEC:US-XNYS-EQR stayed RESOLVED. Prove/falsify the mint, then
  execute an explicit supersession (never deletion) onto the continuing EQR
  identity, dated aliases from canonical evidence, and the general
  pending-transition fence. D2B2 stays unauthorized until the next natural refresh
  proves one canonical identity survives.
state_before: >
  At origin/main after nightly commit b6e0062ca889: two master rows for one
  economic security (SEC:US-XNYS-VMRK freshly minted NO_ISSUER_EVIDENCE;
  SEC:US-XNYS-EQR still RESOLVED on CIK 0000906107); EQR in
  coverage.unresolved_names; no EQR→VMRK signal anywhere in-repo; AVB
  (extinguished by the same merger) RESOLVED with no typed marker; no
  security-level supersession machinery of any kind; the mint join keyed on
  listing key only, with no cross-row transition detection.
changed:
  - path: research/prophet_v4/d2/D2B1_R1_FROZEN_CONTRACT_2026-08-20.md
    what: >
      The binding R1 contract (verdict PROVEN; ratified SEC 8-K evidence E1-E4;
      repairs A-D; hostile cases H1-H10; mutation controls; file scope) plus
      AMENDMENTS §1 (14 post-review rulings), §2 (ruling 9 deferred on the
      M5 conflict), §3 (prune-conflict seam ruling + ruling-10 completion).
  - path: scripts/build_security_master.py
    what: >
      Dated RenameEvent EQR→VMRK on 2026-08-18 (8-K accession 0001140361-26-033377
      cited verbatim); authored SECURITY_SUPERSESSIONS registry (exactly
      US-XNYS-VMRK → SEC:US-XNYS-EQR) with exact-listing-key execution;
      security_state/superseded_by axis; security_migrations writer;
      pending-transition fence (_compute_lost fence/exception split, null-CIK
      fail-closed independence); current-symbol dedup/collision discriminator;
      superseded-only alias pruning with vendor_alias_prunes receipts;
      VendorAliasPruneConflict as plain Exception with a dedicated
      run_nightly_refresh handler (restore + named ::warning + return 0).
  - path: data/reference/
    what: >
      security_master.parquet 705 rows = 704 active + 1 superseded tombstone
      (VMRK, byte-frozen except the two new columns); NEW
      security_migrations.parquet (1 row, evidence = the 8-K string);
      vendor_aliases 2823 (wrong-id VMRK family pruned, receipted); receipt gains
      pending_transition_refusals / resurrection_refusals / listing_continuity
      (one explained GOLD entry) / vendor_alias_prunes /
      unregistered_rename_duplicates blocks; issuer plane untouched.
  - path: config/delisted_symbols.yml
    what: >
      AVB typed exit (extinguished by merger 2026-08-17, 8-K evidence,
      successor_ticker null — AVB must NEVER join VMRK).
  - path: config.yml
    what: "breadth.ticker_fixups gains VMRK: EQR (MMC→MRSH precedent)."
  - path: lib/dataos/identity.py
    what: >
      SecurityIssuerRow exposes security_state/superseded_by; superseded rows
      excluded from securities_of_issuer aggregation; grammar unchanged.
  - path: engine/theme_graph/identity_resolution.py
    what: >
      Both join indices exclude superseded master rows; sidecar re-derived (one
      epoch over main; co:us:EQR and co:us:AVB RESOLVED; no co:us:VMRK cell).
  - path: scripts/check_theme_graph_contracts.py
    what: >
      New clause: a sidecar security_id referencing a master row with non-null
      security_state is a violation; selftest fixture proves it fires.
verified:
  - claim: >
      Duplicate mint PROVEN at origin/main pre-repair (SEC:US-XNYS-VMRK minted
      2026-08-20T01:30:18, NO_ISSUER_EVIDENCE, while SEC:US-XNYS-EQR RESOLVED).
    command: >
      git show origin/main:data/reference/security_master.parquet | python3
      (pandas) — rows 704→705, ADDED=[SEC:US-XNYS-VMRK], REMOVED=[]
  - claim: >
      Post-repair master: 705 = 704 active + 1 superseded; zero value changes on
      the 11 pre-existing columns of all pre-existing rows; security_migrations
      exactly 1 row; issuer_master 701 / issuer_migrations 3 byte-identical to
      base aaf83b6ea030.
    command: >
      opus reviewer re-verification receipts (H9 frame diff = 0; git diff --stat
      aaf83b6ea030..13f6241ee786 -- issuer parquets = empty)
  - claim: >
      Fence + refusals survive an end-to-end build (H10) and the nightly seam
      returns 0 with restore + dedicated ::warning on a prune conflict.
    command: >
      pytest tests/test_dataos_security_master.py (H10 + prune-conflict seam
      tests inside the 344-green run); reviewer's escaped-conflict probe re-run
      (rc 0, security-master-nightly-prune-conflict warning, artifacts restored)
  - claim: Five suites 344 passed; guard --strict exit 0; --selftest OK.
    command: >
      python3 -m pytest tests/test_dataos_identity.py
      tests/test_dataos_security_master.py tests/test_dataos_registry.py
      tests/test_theme_graph_identity_resolution.py
      tests/test_theme_graph_contracts.py -q
next_actions:
  - >
    SURVIVAL PROOF (Sol's D2B2 gate): on the first post-merge natural nightly,
    verify one canonical identity survives — no new VMRK/EQR mint, tombstone not
    resurrected, receipt sane. EXPECT the first nightly to report "identity
    inputs advanced — regenerated" and churn parquet BYTES without content
    change: the artifact set carries mixed pyarrow writer provenance (builder
    24.0.0 vs runner 25.0.1) and the run homogenizes it. Content is the check on
    night one, bytes thereafter.
  - >
    The weekly CIK map will bring VMRK→0000906107 and reassign bare
    "EQR"→0000931182 (ERP Operating LP): the EQR row must stay RESOLVED on
    906107 via its VMRK join key and the tombstone must stay unexamined (both
    test-pinned, H3/H4).
  - >
    Owed follow-ups, each needing its own reviewed lane: same-id-refinement
    carve-out to the M5 prune rule (restores the store-space VMRK alias; design
    in AMENDMENT §2) and breadth-lane retirement of the
    data/stocks/VMRK.parquet double store (8,309-row spliced duplicate of
    EQR.parquet; ticker_fixups VMRK:EQR already points lanes at EQR).
unresolved:
  - >
    Store vendor space has no VMRK answer (ruling 9 deferred by AMENDMENT §2;
    carve-out design named there).
  - >
    data/stocks/VMRK.parquet double store awaits the breadth-lane retirement
    (out of R1 scope — price stores forbidden).
  - >
    4 active NO_ISSUER_EVIDENCE rows (AEP, CTRA, TPH, FISV-via-FI) unchanged
    from D2B1 — FI heals on a future CIK map; not R1's surface.
unverified:
  - >
    The exact first-nightly churn set on the self-hosted runner is inferred from
    parquet footer writer strings (24.0.0 vs 25.0.1), not observed on the runner.
  - >
    The survival proof itself — this wave merged before the next natural refresh
    by design (Sol's gate is that refresh).
do_not_redo:
  - >
    Do not re-flag the missing store-space VMRK alias as a bug — AMENDMENT §2
    adjudicated the deferral (M5 stays strict; absence beats the wrong-id answer
    it replaced).
  - >
    Never join, alias, or rename AVB→VMRK on any axis — AvalonBay was
    EXTINGUISHED (8-K accession 0001193125-26-354068); VMRK continues EQR only.
  - >
    Never evidence-join the bare string "EQR" post-2026-08-17 — SEC reassigned it
    to CIK 931182 (ERP Operating LP); the continuing row's join key is VMRK.
  - >
    Never delete or "clean up" the SEC:US-XNYS-VMRK tombstone row or its
    security_migrations receipt — supersession is the correction, deletion is
    forbidden (Sol condition).
  - >
    Do not treat the first post-merge nightly's "inputs advanced" regeneration +
    parquet byte churn as a defect — it is the one-time writer-provenance
    homogenization (reviewer finding mA, adjudicated accept-and-disclose).
  - >
    Do not hand-create snapshots, restamp manifests, or hand-write master rows to
    "help" any of this — canonical builders only (parent contract law).
danger_areas:
  - >
    RenameEvents NEVER auto-execute supersession — only the authored
    SECURITY_SUPERSESSIONS registry does, on exact listing key. An unregistered
    rename-implied duplicate is a receipt disclosure (unregistered_rename_duplicates).
  - >
    The fence fails closed on null-CIK lost rows; registered identity-exception
    rows (GOLD/B) are fence-EXCLUDED but census-disclosed
    (listing_continuity explained entries). A GOLD-class rename can therefore
    mint a new id — accepted, disclosed residual (AMENDMENT §1 ruling 3).
  - >
    Any future dated rename whose alias family has committed open-bounded rows
    will hit VendorAliasPruneConflict on the nightly: rc 0, last-good restored,
    dedicated ::warning, master frozen until the carve-out lands or curation
    resolves it by hand. That freeze is by design — do not "fix" it by weakening
    M5.
  - >
    The sidecar is re-derived nightly by the engine lane and pushes to main — a
    PR regenerating it conflicts within hours and pull_request CI schedules
    NOTHING on a CONFLICTING PR. Resolve by re-derivation over merged nodes,
    never pick-a-side.
---

# V4-D2B1-R1 handoff — VMRK duplicate-mint supersession + pending-transition fence

PR #6082, branch claude/v4-d2b1-r1-vmrk-supersession. Wave receipts: prove/falsify
probe (orchestrator), opus root-cause packet (mint path, race enumeration: EQR rename
race + AVB exit + CTRA/TPH benign), sonnet researcher packet (SEC 8-K primary
evidence, falsification attempt failed, EQR→931182 trap), three builder passes, opus
review FAIL → fix pass → re-verification (all fixed, one new MAJOR) → surgical pass →
targeted CONFIRMED. Contract + three amendments in
research/prophet_v4/d2/D2B1_R1_FROZEN_CONTRACT_2026-08-20.md.
