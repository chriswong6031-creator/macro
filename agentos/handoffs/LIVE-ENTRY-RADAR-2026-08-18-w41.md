---
workstream: WS:LIVE-ENTRY-RADAR
session: claude/radar-w41-transport
model: sonnet
ended_because: complete
prs: [5929]

mission: >
  W4.1 live-transport correction (research/prophet_v4/
  LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md §6 item 2A; W4.1 wave row minted by
  #5924). Fix two transport gaps blocking G0/live per Prophet Operator Lab
  R-LAB-1: (1) the confirmed-lane pack field the RTH evaluator reads was never
  populated by any writer; (2) W5's spool reader gated on a schema no real W4
  producer has ever emitted. Build-worker packet — this session does NOT own
  merge; the commissioning Fable/main session reviews and merges.

state_before: >
  W4/W5 both individually shipped and green, but G0/C5 confirmed-bar lanes
  were structurally unreachable (live_eval._nightly_lanes always fell to
  slice_store_unconfigured regardless of whether a Terminal slice existed) and
  every real W4 pass envelope was silently rejected by W5's spool reader as
  off-schema, so W5 accrued zero live-forward evidence from the real producer
  shape. Main moved twice mid-session: #5897 (W4 test-baseline repair) and
  #5924 (this wave's own commissioning PR, which minted the W4.1 row this
  handoff updates) both merged; this branch was rebased onto post-#5924 main.

changed:
  - path: engine/entry_radar/live_pack.py
    what: "SCHEMA_LIVE_PACK v1->v2. New LivePack.confirmed_lanes field (per-ticker {g0,c5} rows, always populated). New confirmed_lanes_snapshot() normalizer (per-lane granularity, honest slice_store_unconfigured default). build_pack() gained an injected confirmed_lanes kwarg (no slice IO in this module, mirrors store_reader). compute_pack_hash() now covers confirmed_lanes. manifest()/with_proof()/load_pack() carry the field through; a v1 manifest with no confirmed_lanes key defaults to {}."
  - path: engine/entry_radar/live_eval.py
    what: "_nightly_lanes() reads pack.confirmed_lanes[ticker] instead of the never-populated pack.probe_set['nightly_lanes']. Same honest unavailable/slice_store_unconfigured fallback for a v1 pack, an uncovered ticker, or a malformed row."
  - path: scripts/entry_radar_live_pack.py
    what: "New confirmed_lane_pack_rows() reshapes slice_lanes()'s per-ticker aggregate into confirmed_lanes_snapshot's recognised {g0,c5} shape. main() reordered: slice_lanes() now runs BEFORE build_pack() (same tickers build_pack independently re-derives) so the v2 pack carries confirmed_lanes inside its own pack_hash from construction. Step 4 (ledger C5 event application) reuses the same lanes/c5_runs; the slice store is read once."
  - path: scripts/reconcile_entry_radar.py
    what: "read_spool_events() now accepts the real entry_radar.events/v1 pass envelope in addition to the bare-event shape it already accepted: unwraps events[], validates each inner event against mastermind.entry_event.v1 via EntryEvent.from_dict (torn/foreign events counted-by-omission), derives each event's observed_at from the EARLIEST envelope pass_ts across the whole spool that carried its event_id (_note_earliest_pass_ts, parsed-instant comparison). Transport fact added to the RETURNED COPY only; the immutable event/store is never mutated. New module constant ENVELOPE_SCHEMA."
  - path: tests/test_entry_radar_w41_transport.py
    what: "New file, 14 tests: real-envelope schema acceptance, byte-exact event identity through the envelope, earliest-pass_ts first observation (proven against reverse file-discovery order), torn-inner-event skip, bare-shape backward compatibility, full main() end-to-end forward.parquet row, v2 schema + default confirmed lanes, real confirmed-lane row surviving pack->RTH reader, pack-hash coverage, v1-pack backward compatibility, per-lane malformed-row normalization (4 parametrized cases)."
  - path: research/live_entry_radar/W41_TRANSPORT_NOTES.md
    what: "New receipts doc: what was broken, what changed per file, verification commands and their output, scope discipline notes."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W4.1 row: todo -> in_progress, baseline-discipline note updated (#5897 merged, branch rebased clean), build-worker receipts appended. next_action updated to note the PR is a build-worker packet awaiting commissioning-session review, not yet merged."

verified:
  - claim: "The full entry_radar suite is green, including the 14 new W4.1 tests, against post-#5897/#5924 main."
    command: "python3.12 -m pytest tests/test_entry_radar_*.py -q"
    result: "1467 passed, 3 skipped"
  - claim: "The six registered detector spec hashes are byte-identical to PUBLISHED_SPEC_HASHES — no detector spec touched."
    command: "python3.12 -c \"from engine.entry_radar import live_pack as lp; print(lp.assert_published_spec_hashes() == lp.PUBLISHED_SPEC_HASHES)\""
    result: "True"
  - claim: "Prophet-protected paths carry a clean diff against origin/main."
    command: "git diff --stat origin/main -- engine/prophet_bridge.py engine/prophet_doors.py engine/entry_signal.py 'engine/prophet_*.py'"
    result: "(empty output)"
  - claim: "agentos records still validate with 0 errors after the WS-LIVE-ENTRY-RADAR.md edit."
    command: "python3.12 scripts/agentos.py validate"
    result: "224 records — 0 error(s), 13 warning(s) (the same pre-existing sparse-tree phantom-path warnings noted by #5924's own verification)"

unverified:
  - claim: "The nightly builder correctly reads a REAL Terminal .slice.json file end-to-end (ENTRY_RADAR_SLICE_DIR set) and confirmed_lane_pack_rows() reshapes slice_lanes()'s real per_name output (not just synthetic dicts handed directly to build_pack/confirmed_lanes_snapshot in tests)."
    what_would_verify: "Run scripts/entry_radar_live_pack.py --dry-run with ENTRY_RADAR_SLICE_DIR pointed at a fixture directory containing at least one <SYM>.slice.json, and inspect the resulting pack.confirmed_lanes for that ticker; or add a unit test that calls confirmed_lane_pack_rows() against slice_lanes()'s actual per_name dict shape (available=True with g0_grey_events/c5_candidates keys) rather than only the normalizer downstream of it."
  - claim: "A real nightly spooling the same still-open episode across multiple RTH passes appends only ONE forward.parquet row per episode_address within a single reconciler run."
    what_would_verify: "append_forward_rows only dedups new_rows against rows ALREADY PERSISTED in forward.parquet (the 'seen' set), not within the new batch itself. Add a test that spools two envelopes carrying the SAME event_id (different pass_ts) in one reconciler run and asserts forward.parquet ends with exactly one row for that episode_address, not two. This risk pre-dates W4.1 (append_forward_rows is unchanged) but was dormant because zero real envelopes ever parsed before this fix — W4.1 is what makes it reachable for the first time."
  - claim: "This PR (#5929, pushed and opened) has been reviewed, CI-concluded, and merged, with live verification on the VPS plane."
    what_would_verify: "Complete CI -> commissioning-session review -> merge -> live verification per the shared workspace completion law. This build-worker session does not own that chain and did not arm merge-on-green."

unresolved:
  - "Whether confirmed_lane_pack_rows()'s reshaping is exercised against slice_lanes()'s REAL per-ticker output shape (see first unverified item) — flagged for the commissioning session or a follow-up test, not blocking this packet."
  - "Whether the newly-reachable duplicate-envelope-same-episode append behavior needs a fix in append_forward_rows() before Radar live commissioning proceeds (LAB0 §6 step 3), or whether it is acceptable as-is (e.g. because episodes in practice only spool once per address in a night) — needs a decision, not made here."

next_actions:
  - "Commissioning session: review PR #5929 (engine/entry_radar/live_pack.py, live_eval.py, scripts/entry_radar_live_pack.py, scripts/reconcile_entry_radar.py, tests/test_entry_radar_w41_transport.py)."
  - "Weigh the two unresolved items above, especially the real-slice-store integration gap and the newly-reachable duplicate-envelope dedup question."
  - "Let CI conclude on #5929 and own the merge + live verification chain — do not arm merge-on-green without that review."
  - "After merge: flip the W4.1 wave row in agentos/workstreams/WS-LIVE-ENTRY-RADAR.md to done with the merged squash sha."
  - "Decide whether the duplicate-envelope forward-row question needs its own follow-up wave before Radar live commissioning (LAB0 §6 step 3) proceeds."

do_not_redo:
  - "Do not re-litigate the schema-mismatch diagnosis: read_spool_events() gating on top-level mastermind.entry_event.v1 while W4 spools entry_radar.events/v1 was verified by inspecting live_ledger.build_event_payload() directly (SCHEMA_ENTRY_RADAR_EVENTS = 'entry_radar.events/v1') against reconcile_entry_radar.py's SPOOL_EVENT_SCHEMA constant — this is not a hypothesis, it was read from both source files."
  - "Do not add a second confirmed-lane read path — scripts/entry_radar_live_pack.py's slice_lanes() is the ONE nightly reader of the Terminal slice store; both the pack's confirmed_lanes field and the ledger's C5 event application now consume that single call's result. A second call would double the slice-store IO for no reason."
  - "Do not try to make the bare-event spool shape (schema=mastermind.entry_event.v1 at top level) go away — tests/test_entry_radar_w5_reconciler.py's 23 existing tests depend on it, and it may still be a real producer shape for something other than W4. Both shapes coexist by design in read_spool_events()."

danger_areas:
  - "engine/entry_radar/live_pack.py SCHEMA_LIVE_PACK bump to v2 is a pack-identity change: any code outside this diff that hardcodes 'entry_radar.live_pack/v1' as a literal string (none found in this repo at authoring — grepped) would silently stop matching. Re-grep before assuming this stays isolated if new callers appear."
  - "reconcile_entry_radar.read_spool_events() now performs real EntryEvent.from_dict() validation on every inner event of every real envelope, which is materially more work per spool file than the prior bare-schema-string check. Not measured against a large nightly spool; if R-LAB-1's live commissioning produces a very large backlog spool, watch nightly runtime."
  - "Do not confuse this wave's 'confirmed_lanes' pack field with W5's separate ledger-side C5 event application (slice_lanes()'s c5_runs, applied via ledger.apply_run) — they now share ONE slice_lanes() call (moved earlier in main()) but remain two different consumers of the same read; do not re-merge them into one code path without re-reading both docstrings."
---

## Context

See `research/live_entry_radar/W41_TRANSPORT_NOTES.md` for the full technical
writeup (what was broken, what changed per file, verification commands and
output). This handoff is the cold-stranger summary; that doc is the receipts.
