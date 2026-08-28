---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "2930780f-f0b0-4efc-a62a-f529085b3a0d (Fable orchestrator, D2B1 wave)"
model: fable
ended_because: complete
mission: >
  V4-D2B1 (Sol commission): make the Data OS issuer axis semantically correct —
  one economic issuer across multiple securities where SEC-registrant CIK evidence
  exists — with mint-once migration receipts, typed refusal states, a nightly
  refresh seam, and the D2A GMI bridge re-derived over the corrected authority.
  Broad master expansion (the 1,868-row NOT_IN_MASTER queue) explicitly deferred
  to D2B2.
state_before: >
  issuer_id duplicated the listing key (GOOG and GOOGL = two "issuers"); master
  703 rows, generated 2026-08-14 from the 2026-08-10 snapshot, manually
  regenerated only; receipt claimed "nothing reads it as authority yet" (false
  since D2A); no refresh seam; the staleness test red on main (RDDT resolvable
  from current seeds, absent from the committed artifact).
changed:
  - path: lib/dataos/identity.py
    what: >
      IssuerMaster pure no-I/O reader (securities_of_issuer / issuer_of_security),
      historical-limitation docstring; issuer_id()/parse_id() UNCHANGED — grammar
      preserved as ISS:<listing-key of the canonical member>, spec §3.2 tie-break
      plus new deterministic rule 4 (lexicographically lowest listing key).
  - path: scripts/build_security_master.py
    what: >
      CIK evidence join (CURRENT-symbol-only via the master's own rename chain,
      dot->dash normalized, two-clock safe); era issuer_semantic_correction_v1
      (idempotent, mint-once; committed issuer values retained, repoints
      receipted); issuer_master + issuer_migrations writers; receipt authority
      decomposition (identity_authority canonical_exact_identity; signal/ranking/
      trade none) + issuer census; run_nightly_refresh fail-closed seam INCLUDING
      the cik_map evidence rail — escape found by the mutation pass, closed
      same-wave (missing cik_map now refuses with a ::warning and keeps last-good
      instead of silently minting evidence-less rows).
  - path: config/dataset_registry.yml
    what: >
      registers reference.issuer_master + reference.issuer_migrations; security
      master gains the issuer axis columns; issuer_id flips nullable true.
  - path: config/identity_seams.yml
    what: >
      master prose updated; two new KNOWINGLY-DIFFERENT rows (capital-structure
      sec-cik namespace; company-intelligence golden-corpus namespace).
  - path: data/reference/
    what: >
      regenerated 704-row master (RDDT entered; zero security_id / listing_key
      moved), new issuer_master.parquet, new issuer_migrations.parquet (3 rows —
      GOOGL/FOXA/NWSA repoint to ISS:US-XNAS-GOOG/FOX/NWS).
  - path: data/theme_graph/identity_resolution.parquet
    what: >
      re-derived from committed nodes.parquet + corrected master (2,806 rows;
      RESOLVED 702, NOT_IN_MASTER 1,868); the merge conflict against main's
      regime-update lane was resolved by RE-DERIVATION over the merged nodes
      plane (merge commit 283ef52f05cc), never pick-a-side; _meta.json restamped
      via the store writer.
  - path: scripts/check_theme_graph_contracts.py
    what: >
      biconditional now issuer-state-aware — a null issuer_id on a RESOLVED
      sidecar row is lawful ONLY when the master's issuer_state is
      NO_ISSUER_EVIDENCE.
  - path: .github/workflows/daily.yml
    what: >
      ONE non-fatal reference-materialization step in the collect job (no new
      timer or control plane).
  - path: tests/
    what: >
      four existing suites extended (14 mutation controls, hostile cases,
      idempotency, refresh fail-closed, cik_map refusal); test_dataos_registry.py
      count assertions updated (ratified deviation — registering two datasets
      moved its enumerations).
  - path: research/
    what: >
      MASTERMIND_SECURITY_MASTER_SPEC.md §3.2 rule-4 amendment note; D2A contract
      AMENDMENTS note; D2B1 frozen contract committed + post-freeze AMENDMENTS;
      CONTRACT_AND_OWNER_MAP issuer-axis note.
verified:
  - claim: 306 passed pre-merge across the seven identity/theme-graph suites; 132 passed post-merge on the two core suites
    command: "TZ=UTC python3 -m pytest tests/test_dataos_identity.py tests/test_dataos_security_master.py tests/test_dataos_registry.py tests/test_identity_seam_agreement.py tests/test_theme_graph_identity_resolution.py tests/test_theme_graph_contracts.py tests/test_gh_annotation_line_start.py -q"
  - claim: staleness heal red to green (RDDT carried by the regenerated master)
    command: "TZ=UTC python3 -m pytest tests/test_dataos_security_master.py::test_the_committed_artifact_is_not_stale_against_the_current_seeds -q"
  - claim: strict guard exit 0 with census; selftest OK
    command: "python3 scripts/check_theme_graph_contracts.py --strict / --selftest"
  - claim: idempotency — sha256 equality of the four reference artifacts across two consecutive builder runs
    command: "shasum -a 256 data/reference/*.parquet (twice, compared)"
  - claim: mutation controls 14/14 provably die — 13 died first pass; control 11 was a GENUINE ESCAPE (missing cik_map silently regenerated with a ::notice), closed by ed49d19083d0 and re-proven to die
    command: "mutate-and-observe pass over the contract §12 list (targeted pytest per control)"
  - claim: hostile cases — GOOG/GOOGL, FOX/FOXA, NWS/NWSA one issuer per pair; BRK.B dash-join RESOLVED; GOLD DEFERRED (live map GOLD is Gold.com 1591588 — the exception prevented a WRONG grouping); FI/FISV correctly REFUSED (SEC map lags the FISV-to-FI rename; two-clock law held); IBIT RESOLVED to the trust CIK with the sidecar ENTITY_TYPE_CONFLICT retained
    command: "pandas queries against the committed parquets, re-run first-hand by the orchestrator"
unverified:
  - >
    live-refresh production proof (fresh source -> nightly materialization with
    no manual edits): completes on the first post-merge nightly under the fixed
    collector (#5936, merged 2026-08-19T07:10Z); the listing snapshot was still
    2026-08-10 at PR time — contract §10 freshness gate honestly BLOCKED until
    that run lands.
  - >
    EQR->VMRK: pending evidence — needs CIK continuity from a post-2026-08-18
    weekly CIK map; deliberately NOT repaired (no timeless alias anywhere).
unresolved:
  - >
    4 NO_ISSUER_EVIDENCE rows (AEP, CTRA, TPH, and FISV-via-FI); FI heals when
    the SEC company_tickers file catches up; the others need source investigation
    in D2B2.
  - 1,868 NOT_IN_MASTER graph nodes = the D2B2 expansion queue (out of scope).
  - IBIT ENTITY_TYPE_CONFLICT + GOLD/B membership lineage = D2B3 (GMI-side).
next_actions:
  - >
    Verify the first post-merge nightly ran the reference step (daily.yml collect
    job log, security-master-nightly annotations) and that a post-2026-08-10
    snapshot flowed source -> master -> receipt with no manual edits.
  - >
    D2B2 (NOT authorized): broad expansion from canonical listing/registrant
    sources; acceptance = resolved + explicit refusals accounting over the
    source-supported population.
  - >
    D2B3 (NOT authorized): GMI corrections (GOLD/B lineage, IBIT entity kind) +
    sidecar re-bake.
do_not_redo:
  - >
    Do not re-litigate the issuer id grammar — ISS:<listing-key of the canonical
    member> (spec §3.2 + rule 4); CIK is grouping evidence, never the id.
  - >
    Do not join historical/dated alias symbols against the current CIK map (the
    two-clock law); FI/FISV NO_ISSUER_EVIDENCE is CORRECT behavior, not a bug.
  - >
    Do not "fix" GOLD via the live CIK map — that CIK is Gold.com, not Barrick;
    the receipt exception exists precisely for this.
  - Do not hand-write master rows (RDDT precedent — canonical regeneration only).
  - >
    Do not re-mint per-listing issuers for evidence-less new rows (NULL + typed
    state is the law; tests kill the fallback).
  - >
    Do not resolve a theme-graph sidecar merge conflict by picking a side —
    re-derive from the merged nodes plane + the branch's master (283ef52f05cc is
    the precedent).
danger_areas:
  - >
    pandas 3 nullable-string parquet columns hand back float('nan'), not None —
    readers/writers must pd.isna() (bug found and fixed in two places this wave).
  - >
    The era is mint-once — later CIK evidence disagreeing with a committed
    grouping must become a typed state, never a rewrite; a future correction era
    needs Sol authorization.
  - >
    data/symbol_directory/ is collector-owned and read-only for sessions; the
    manifest under-reports (n_symbols 0 is display-only damage from the frozen
    era) — gate freshness on snapshot files + completion receipts, never the
    manifest.
  - >
    The nightly engine lane re-derives the theme-graph sidecar and pushes it to
    main — any PR that regenerates the sidecar WILL conflict with main within
    hours, and its pull_request CI schedules NOTHING while conflicted (no
    buildable merge ref); resolve fast, push fast.
prs: [5965]
---
