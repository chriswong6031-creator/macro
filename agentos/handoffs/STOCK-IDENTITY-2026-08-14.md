---
workstream: WS:STOCK-IDENTITY
session: stock-identity-w1-atlas (Claude, W1 build session, worktree vigorous-mirzakhani-3ae795)
model: fable
ended_because: ci_handoff
mission: >
  W1 / PR-1: Identity Atlas v0 per masterplan §14 PR-1 row under the §16.9 execution
  authorization — sealed calibration partition + blind arm drawn/named/hashed, catalog/state/
  zone constants frozen on the partition, fingerprint v0 + state tagger v0 + episode catalog
  v0 built over the pilot cohort, per-name dossiers, coverage census started, pilot data
  gates resolved, stock-identity registry row minted. Descriptive only — zero expert-fit.
state_before: >
  PR-0 (#5583) merged 2026-08-14T10:02Z (merge 29d89724c8) with all §16 rulings ratified
  and §16.9 authorizing W1 on merge. No engine/data/scripts surface existed for the program.
  A first W1 launch attempt earlier the same day correctly aborted on the precondition
  (#5583 then unmerged atop a red main); this session re-verified the merge before building.
changed:
  - path: research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md
    what: NEW — the W1 registration (universe, pilot completion rules, blind-arm procedure + provisionality, sealed calibration partition SI-SEALED-CAL-P1 + §16.2-consistent material reading, FIT/TEST boundary 2020-01-01 declared, constants selection rules + receipts, fingerprint v0 enumeration + block partition + UNIV_EW factor panel, state tagger v0, episode catalog v0, census v0 rules, data-gate verdicts, earnings DEFER, hashes)
  - path: engine/stock_identity/
    what: NEW — plane/partition/fingerprint/state/episodes/census/dossier modules (TODO-SHIP fill exact list)
  - path: scripts/stock_identity_build_atlas.py + scripts/stock_identity_calibrate.py + scripts/stock_identity_collect_missing.py
    what: NEW — atlas pipeline CLI, sealed-partition calibration (rule-then-value receipts, TrialLedger-registered sensitivity grid), BABA/WPM deep-OHLCV collection (program-owned plane)
  - path: data/stock_identity/
    what: NEW — partition manifest + universe snapshot, si_constants_v1.json (spec-hashed), pilot fingerprints/states/episode catalog, coverage census v0, BABA/WPM ohlcv + provenance manifest; all artifacts authority all-false
  - path: research/stock_identity/dossiers/
    what: NEW — per-pilot-name operator-readable dossiers (md + chart)
  - path: tests/test_stock_identity_*.py
    what: NEW — partition disjointness/reproducibility, metric-block purity, truncation invariance, state totality/exclusivity, synthetic episode segmentation, G-8 import firewall, banned-token/authority artifact walk
  - path: config/mastermind_programs.yml
    what: stock-identity minted as subprogram_of market-timing-intelligence (§16.7)
  - path: agentos/workstreams/WS-STOCK-IDENTITY.md
    what: W0 flipped done (PR #5583 merged); W1 wave updated with PR + operator-return gate
verified:
  - claim: "TODO-SHIP: partition hashes reproduce from committed snapshot + seeds"
    command: "TODO-SHIP"
    result: "TODO-SHIP"
  - claim: "TODO-SHIP: all stock_identity tests pass"
    command: "python3 -m pytest tests/test_stock_identity_*.py -q"
    result: "TODO-SHIP"
  - claim: "TODO-SHIP: G-8 protected paths untouched"
    command: "git diff --stat origin/main...HEAD -- <G-8 paths>"
    result: "TODO-SHIP (empty)"
  - claim: "TODO-SHIP: agentos records schema-valid"
    command: "python3 scripts/agentos.py validate"
    result: "TODO-SHIP"
unverified:
  - "Dossiers are committed but NOT yet operator-reviewed — the §16.9 post-W1 operator return is the W2 gate, not a W1 deliverable."
  - "Blind-arm final size is provisional (3 per non-empty stratum); PR-5's power simulation prefix-shrinks or clean-pool-extends per the registration §3 rules."
unresolved:
  - "Miner deep history: AEM/PAAS/AG/GOLD reach only the baskets plane's 2014 inception; deepening to cover the 2011-2015 gold bear is a named PR-2+ decision if the miner-emergence test needs it (registration §9)."
  - "Earnings-date deep backfill DEFERRED (registration §9) — revisit at PR-4/PR-5 if diagnostic F6/epoch face-validity needs it."
next_actions:
  - "OPERATOR RETURN (§16.9, blocking W2): review the Identity Atlas + dossiers (research/stock_identity/dossiers/); W2 (expert replay + provenance) launches only after this return."
  - "W2 pre-read: re-check Radar #5578 merge state (still OPEN at W1, revalidated 2026-08-14); entry_event.v1 remains proposed."
do_not_redo:
  - "Do not redraw the blind arm or the sealed calibration partition — SI-SEALED-CAL-P1 is drawn/named/hashed; constants are frozen; a redraw voids the W1 registration (masterplan §9.3)."
  - "Do not backfill BABA/WPM into data/stocks or data/baskets — their deep history lives in the program-owned data/stock_identity/ohlcv plane (registration §11)."
  - "Do not read §13's dead-name clause as satisfiable from config/delisted_symbols.yml alone — the ledger holds 2 rows (CTRA, TPH); the W1 substitution rule is in registration §2."
danger_areas:
  - "The word 'personality' is banned for this program's concepts (three prior senses live in-repo); the program says identity / behavioral fingerprint."
  - "No expert-fit content may exist in any W1 artifact (§16.9) — the banned-token test enforces it; W2+ adds expert data behind the post-W1 operator return."
  - "G-8 path partition — every engine PR prints the clean git diff --stat on the protected paths."
prs: [5583]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Note

W1 executed per the §16.9 authorization: descriptive/measurement-first, understanding-before-
backtest honored (no fit tables, no expert joins). The sealed calibration partition was drawn
and hashed BEFORE any constant was chosen (draw order enforced in code and receipts). The
session ends at scripts/ci_handoff.py with the W1 PR armed for the sweeper; the program now
waits on the post-W1 operator return before any expert replay/fit work.
