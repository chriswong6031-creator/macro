---
workstream: WS:STOCK-IDENTITY
session: stock-identity-w2-replay (Claude, same session as W1, worktree vigorous-mirzakhani-3ae795)
model: fable
ended_because: merged (terminal CI handoff retired by #5513 mid-session — a session owns its PR through merge)
mission: >
  W2 / PR-2: Expert Replay + Provenance Pinning under the 2026-08-14 §16.9 operator return
  (W1 ACCEPTED, W2 AUTHORIZED, six binding rulings): era-pinned Class R replay over the pilot,
  entry_event.v1-compatible program-owned event store, event↔episode attribution join, leak
  fixtures, STARTER Class-C resolution, GOLD identity correction + Barrick B pilot addendum.
  Descriptive only — zero ruler metrics, zero expert-fit.
state_before: >
  W1 merged as #5612 (2026-08-14T12:22Z). Operator return accepted W1 and authorized W2 with
  rulings: (1) descriptive-only; (2) survivor-only stands, Dead Instrument Control Set gates
  PR-5; (3) GOLD = Gold.com/A-Mark not Barrick — B added via addendum, sealed partitions
  untouched, #5613 sibling owns config acks + roster repair; (4) N=42 descriptive-only;
  (5) degenerate cluster component never inferential N; (6) mixed dossier formats accepted.
  Radar #5578 MERGED since W1 start → entry_event.v1 vocabulary adopted (store still Radar
  PR-2's, never written by this program).
changed:
  - path: research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md
    what: NEW — W2 registration (rulings §0, R1 evaluate-first justification §1, scoped import-firewall amendment §2, family registry design §3, event-store schema §4, naive comparator specs §5, pilot addendum §6, leak fixtures §7)
  - path: engine/stock_identity/replay/
    what: NEW — 14 modules (grid, events, registry, attribution, leak, grey_dot, confirmed_buy, tiers, washout_turn, reclaim_waiver, bottom_watch, starter, sea, naive); the ONLY subpackage allowed to import the protected signal engines (enumerated allowlist, test-pinned in __init__ and tests)
  - path: scripts/stock_identity_replay_pilot.py + scripts/stock_identity_pilot_addendum.py
    what: NEW — stage-resumable replay CLI (per-(family,symbol) chunk skip) + B/GOLD addendum CLI
  - path: data/stock_identity/expert_events/
    what: NEW — family_registry.json (24 family keys incl. 8 Class P zero-row entries), pilot_events_v0.parquet (31,119 events, 22 names, era split 14,846 pre-2010 / 16,273 post), event_edges_v0.parquet (64 typed edges), attribution_v0.parquet (34,491 rows under frozen P_pre=5), inventory_v0.md — all authority all-false, entry_event.v1-compatible vocabulary with field_origin extended {ledger_recorded, replay_recomputed}
  - path: data/stock_identity/ohlcv/B.parquet + addendum artifacts + dossiers B/GOLD
    what: NEW/REGEN — B 10,454 rows 1985-02-13→asof (fetch_ohlc auto_adjust=True; ABX→GOLD→B one-continuous-listing lineage note); addendum_b_{fingerprint,state,catalog}.parquet (193 episodes) vs the FROZEN W1 cross-section; B.md/.png dossier; GOLD.md/.svg regenerated as "reused-ticker hygiene case study (bullion dealer instrument)" with dated ruling citation
  - path: tests/test_stock_identity_replay.py + tests/test_stock_identity_replay_leak.py + amended tests/test_stock_identity_atlas.py
    what: NEW/AMENDED — 77 new tests (152 total green); firewall scoped-allowlist amendment; wired into the stock-identity atlas guards CI step
verified:
  - claim: Full stock-identity suite green (W1's 75 + W2's 77)
    command: python3 -m pytest tests/test_stock_identity_*.py -q
    result: "152 passed in 19.68s (orchestrator's own run after the builder's identical result); skip-clean 41 passed/33 skipped without artifacts"
  - claim: G-8 protected paths untouched (imports only)
    command: git diff --stat origin/main...HEAD -- <G-8 paths>
    result: "empty (committed AND working tree)"
  - claim: W1 sealed objects byte-identical after the whole W2 build; B in no sealed list
    command: sealed-hash test recomputing via W1's OWN functions (partition.sha256_of_symbols / universe_sha256 / procedure / fingerprint.spec_hash)
    result: "all five hashes identical (blind 88e2b0d8…, calibration 77e111c1…, fingerprint spec 0e3457b1…, procedure a546c649…, universe 841ed546…)"
  - claim: Zero ruler/fit content in any W2 artifact
    command: writer-level assert_no_ruler_columns + banned-token tests (6, incl. writer-refusal mutation)
    result: "pass; only inventory + join-coverage aggregates exist"
  - claim: Class P zero rows (no synthetic history)
    command: tests (8 Class P families enumerated with family_first_available)
    result: "0 rows for amber_early/door_r_rearm/turn_watch_deck/gc_v2_scores/radar_c1_c2/starter_pending/_failed/_converted"
  - claim: New suites named by a workflow; packs valid
    command: python3 scripts/audit_unrun_tests.py && run_ci_pack --validate-only 0..11
    result: "audit exit 0; 12/12 valid"
unverified:
  - "Leak-fixture greens are per-family CI-reproducible, but the weekly_washout_turn start-invariance EXEMPTION (whole-sample percentile by producer design) means its recomputed events near the 15th-pctile gate depend on history depth — a PR-3 measurement caveat, canary-tested so the exemption cannot go stale silently."
  - "bottom_watch_terminal carries a declared approximation for the Terminal 'blocked' predicate (below-200DMA proxy) — recorded in parity_notes, never silently."
unresolved:
  - "Dead Instrument Control Set (ruling 2): ≥5 identity-resolved terminated US instruments with full adjusted OHLCV on a fingerprint-compatible plane — separately registered act, BLOCKS PR-5/Q1. Not built in W2."
  - "STARTER licensing context ruled NOT_PIT_RECONSTRUCTABLE (both producer-read artifacts are single-vintage nightly overwrites, as_of 2026-08-13; PIT membership exists but is not the licensed object) → trio reclassified Class P per the pre-registered consequence matrix; starter_signature ships Class R (2,559 events). Re-opening the trio requires a dated basket-STATE store to start accruing — a future registered act."
  - "Grey-dot twin parity MEASURED and large: 654 agree / 76 macro-only / 2,065 terminal-only (terminal fires ~3.7×; four named divergence axes incl. oscillator family — signal_quality uses technicals.rsi while the locked-spec port pins canon — and 2D bucketing; the port cuts 3D bars on the Macro absolute anchor because the Terminal bar_anchor is not committed). Families stay separate; PR-3 must grain-stratify and never rank the twins against each other on proximity."
  - "confirmed_buy ledger arm: 454/1,160 ledger rows known-ts-stampable (100% of current-era-stamped rows; 32.3% of pre-era rows whose labels come from the retired 3B binning) — refused rather than guessed; recompute arm covers the depth separately with spec_postdates_history honesty."
  - "reclaim_waiver: 0 events (family_first_available 2026-08-13 — its state artifact is a single vintage; 7/22 pilot names qualify at notch 20 but no marker became knowable inside the one-vintage window). Structural absence, never a null verdict."
next_actions:
  - "W3 / PR-3 (ruler engine + estimability census) needs its own operator go — W2 ends at handoff by ruling; do NOT auto-roll. PR-3 pre-reads: twin-parity grain handling, the weekly-washout exemption caveat, cluster-rule refinement (W1 finding), N=42 descriptive-only status."
  - "Dead Instrument Control Set: register + build before PR-5/Q1 (blocking, ruling 2)."
  - "Shift-audit deviation of record (registration §9.6): calendar-anchored grids make literal date-shift invariance false BY DESIGN; start-invariance + forming-bar are the implemented RUL-31-shaped fixtures — carry this forward as the house shape for calendar-anchored replay."
do_not_redo:
  - "Do not reinterpret NYSE GOLD as Barrick/miner anywhere — operator ruling 2026-08-14 + #5613 forensics; B is the miner pilot."
  - "Do not write into the Radar entry_event store or engine/entry_radar/** — W2's store is program-owned and schema-compatible only."
  - "Do not extend R1 for family extraction — the written justification in W2 registration §1 records why its scope cannot serve."
danger_areas:
  - "engine/stock_identity/replay/** is the ONLY place protected signal engines may be imported (read-only, enumerated allowlist, test-enforced); the identity layer's total firewall is load-bearing for G-3."
  - "Class P families must never gain rows (no synthetic history) — zero-row test."
prs: [5612, 5643]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Note

W2 executed under the 2026-08-14 §16.9 return: 31,119 era-pinned events across 16 shipping
family keys (8 more enumerated Class P at zero rows), attribution joined under frozen W1
constants, every fixture green or exemption-declared-with-canary, GOLD's identity corrected
and Barrick B added without touching a sealed object. No ruler number exists in the wave.
Mid-session law change honored: #5513 retired the terminal CI handoff, so this session
owns PR #5643 through concluded-green merge + live verification (merge-on-green armed as
the performing backstop). W3 is NOT started — the operator owns the next go.
