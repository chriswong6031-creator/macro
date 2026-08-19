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
    what: "SCHEMA_LIVE_PACK v1->v2. New LivePack.confirmed_lanes field (per-ticker {g0,c5} rows, always populated). New confirmed_lanes_snapshot() normalizer (per-lane granularity, honest slice_store_unconfigured default). build_pack() gained an injected confirmed_lanes kwarg (no slice IO in this module, mirrors store_reader). compute_pack_hash() now covers confirmed_lanes. manifest()/with_proof()/load_pack() carry the field through; a v1 manifest with no confirmed_lanes key defaults to {}. REVIEW ROUND 1 (S1): load_pack() now routes confirmed_lanes through confirmed_lanes_snapshot() (was a bare dict(...) with no normalization on the production read path). REVIEW ROUND 1 (N4): new _SCHEMA_LIVE_PACK_V1 constant; load_pack() defaults a missing/empty schema to it, never to the live SCHEMA_LIVE_PACK, so a genuinely pre-W4.1 manifest is never mislabeled v2."
  - path: engine/entry_radar/live_eval.py
    what: "_nightly_lanes() reads pack.confirmed_lanes[ticker] instead of the never-populated pack.probe_set['nightly_lanes']. Same honest unavailable/slice_store_unconfigured fallback for a v1 pack, an uncovered ticker, or a malformed row."
  - path: scripts/entry_radar_live_pack.py
    what: "New confirmed_lane_pack_rows() reshapes slice_lanes()'s per-ticker aggregate into confirmed_lanes_snapshot's recognised {g0,c5} shape. main() reordered: slice_lanes() now runs BEFORE build_pack() (same tickers build_pack independently re-derives) so the v2 pack carries confirmed_lanes inside its own pack_hash from construction. Step 4 (ledger C5 event application) reuses the same lanes/c5_runs; the slice store is read once. REVIEW ROUND 1 (N1): removed the unused slice_dir kwarg from confirmed_lane_pack_rows()."
  - path: scripts/reconcile_entry_radar.py
    what: "read_spool_events() now accepts the real entry_radar.events/v1 pass envelope in addition to the bare-event shape it already accepted: unwraps events[], validates each inner event against mastermind.entry_event.v1 via EntryEvent.from_dict (torn/foreign events counted-by-omission), derives each event's observed_at from the EARLIEST envelope pass_ts across the whole spool that carried its event_id (_note_earliest_pass_ts, parsed-instant comparison). Transport fact added to the RETURNED COPY only; the immutable event/store is never mutated. New module constant ENVELOPE_SCHEMA. REVIEW ROUND 1 (B1/S3): the envelope branch now collects events keep-first by the VALIDATED event_id (mirrors engine/prophet_lab/sources.py's events_by_id.setdefault pattern) instead of appending one record per envelope appearance — spool_then_commit is at-least-once by design and append_forward_rows dedups only against already-persisted rows, so an unfixed appearance-per-record read would append unrepairable duplicate forward.parquet rows for a re-spooled event; observed_spool_events (S3, same root cause) is fixed for free since it counts the now-deduplicated records list. REVIEW ROUND 1 (S2): _note_earliest_pass_ts() now parses BEFORE latching a candidate, including the first one — previously an unparseable first pass_ts (e.g. 'pending') latched without parsing and every later comparison ValueError'd against the stored garbage, permanently pinning it. REVIEW ROUND 1 (S4): restated the module comment to name the actual pin (a test), since asserting ENVELOPE_SCHEMA against live_ledger.SCHEMA_ENTRY_RADAR_EVENTS at runtime would require importing the pandas-pulling live_ledger module into a script that otherwise avoids that cost on its report-only paths. REVIEW ROUND 1 (N3): _observed_at()'s docstring updated — it no longer claims observed_at 'does not exist yet'."
  - path: tests/test_entry_radar_w41_transport.py
    what: "20 tests (14 original + 6 from review round 1): real-envelope schema acceptance, byte-exact event identity through the envelope, earliest-pass_ts first observation with keep-first dedup (B1, proven against reverse file-discovery order), distinct-event observed_spool_events counting (S3), unparseable-pass_ts non-latching in both orderings at spool level and unit level (S2), torn-inner-event skip, bare-shape backward compatibility, full main() end-to-end forward.parquet row, v2 schema + default confirmed lanes, real confirmed-lane row surviving pack->RTH reader, pack-hash coverage, v1-pack backward compatibility, load_pack normalizing a hand-repaired manifest row (S1), load_pack labeling a schema-missing manifest as v1 (N4), per-lane malformed-row normalization (4 parametrized cases)."
  - path: research/live_entry_radar/W41_TRANSPORT_NOTES.md
    what: "Receipts doc: what was broken, what changed per file, verification commands and their output, scope discipline notes, and a 'Review round 1 dispositions' table (finding id -> fix) plus a one-paragraph answer on spool pruning/retention (grepped, none exists in-repo for the events spool)."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W4.1 row: todo -> in_progress, baseline-discipline note updated (#5897 merged, branch rebased clean), build-worker receipts appended. next_action updated to note the PR is a build-worker packet awaiting commissioning-session review, not yet merged."

verified:
  - claim: "The full entry_radar suite is green, including all 20 W41-transport tests, after applying every review-round-1 fix, against post-#5897/#5924 main."
    command: "python3.12 -m pytest tests/test_entry_radar_*.py -q"
    result: "1474 passed, 2 skipped"
  - claim: "The six registered detector spec hashes are byte-identical to PUBLISHED_SPEC_HASHES — no detector spec touched."
    command: "python3.12 -c \"from engine.entry_radar import live_pack as lp; print(lp.assert_published_spec_hashes() == lp.PUBLISHED_SPEC_HASHES)\""
    result: "True"
  - claim: "Prophet-protected paths carry a clean diff against origin/main."
    command: "git diff --stat origin/main -- engine/prophet_bridge.py engine/prophet_doors.py engine/entry_signal.py 'engine/prophet_*.py'"
    result: "(empty output)"
  - claim: "agentos records still validate with 0 errors after the WS-LIVE-ENTRY-RADAR.md edit."
    command: "python3.12 scripts/agentos.py validate"
    result: "225 records — 0 error(s), 13 warning(s) (the same pre-existing sparse-tree phantom-path warnings noted by #5924's own verification)"
  - claim: "The same-event_id-across-two-envelopes case now returns exactly one record with the earliest observed_at, and no fixture spooling malformed/garbage pass_ts values can permanently corrupt first-observation."
    command: "python3.12 -m pytest tests/test_entry_radar_w41_transport.py -q -k 'keep_first_dedup or unparseable or note_earliest or observed_spool_events_counts'"
    result: "6 passed"

unverified:
  - claim: "The nightly builder correctly reads a REAL Terminal .slice.json file end-to-end (ENTRY_RADAR_SLICE_DIR set) and confirmed_lane_pack_rows() reshapes slice_lanes()'s real per_name output (not just synthetic dicts handed directly to build_pack/confirmed_lanes_snapshot in tests)."
    what_would_verify: "Run scripts/entry_radar_live_pack.py --dry-run with ENTRY_RADAR_SLICE_DIR pointed at a fixture directory containing at least one <SYM>.slice.json, and inspect the resulting pack.confirmed_lanes for that ticker; or add a unit test that calls confirmed_lane_pack_rows() against slice_lanes()'s actual per_name dict shape (available=True with g0_grey_events/c5_candidates keys) rather than only the normalizer downstream of it. Not required by review round 1; still open."
  - claim: "This PR (#5929, pushed and opened) has been reviewed, CI-concluded, and merged, with live verification on the VPS plane."
    what_would_verify: "Complete CI -> commissioning-session review -> merge -> live verification per the shared workspace completion law. This build-worker session does not own that chain and did not arm merge-on-green."

unresolved:
  - "Whether confirmed_lane_pack_rows()'s reshaping is exercised against slice_lanes()'s REAL per-ticker output shape (see first unverified item) — flagged for the commissioning session or a follow-up test, not blocking this packet."

next_actions:
  - "Commissioning session: review PR #5929 (engine/entry_radar/live_pack.py, live_eval.py, scripts/entry_radar_live_pack.py, scripts/reconcile_entry_radar.py, tests/test_entry_radar_w41_transport.py), including the 'Review round 1 dispositions' table in W41_TRANSPORT_NOTES.md."
  - "Weigh the remaining unresolved item (real-slice-store integration gap)."
  - "Since this PR edits scripts/**, verify main is genuinely green (authority-changed discipline) before merging — do not rely on an inherited-red excuse."
  - "Let CI conclude on #5929 and own the merge + live verification chain — do not arm merge-on-green without that review."
  - "After merge: flip the W4.1 wave row in agentos/workstreams/WS-LIVE-ENTRY-RADAR.md to done with the merged squash sha."

do_not_redo:
  - "Do not re-litigate the schema-mismatch diagnosis: read_spool_events() gating on top-level mastermind.entry_event.v1 while W4 spools entry_radar.events/v1 was verified by inspecting live_ledger.build_event_payload() directly (SCHEMA_ENTRY_RADAR_EVENTS = 'entry_radar.events/v1') against reconcile_entry_radar.py's SPOOL_EVENT_SCHEMA constant — this is not a hypothesis, it was read from both source files."
  - "Do not add a second confirmed-lane read path — scripts/entry_radar_live_pack.py's slice_lanes() is the ONE nightly reader of the Terminal slice store; both the pack's confirmed_lanes field and the ledger's C5 event application now consume that single call's result. A second call would double the slice-store IO for no reason."
  - "Do not try to make the bare-event spool shape (schema=mastermind.entry_event.v1 at top level) go away — tests/test_entry_radar_w5_reconciler.py's 23 existing tests depend on it, and it may still be a real producer shape for something other than W4. Both shapes coexist by design in read_spool_events()."
  - "Do not revert read_spool_events()'s envelope branch to one-record-per-appearance (review round 1 finding B1) — spool_then_commit is at-least-once by design (live_ledger.py, 'SPOOL BEFORE CONSUME'), so the same event_id legitimately appears in more than one envelope, and append_forward_rows dedups only against already-persisted rows, never within a new batch. Keep-first-by-validated-event_id is load-bearing, not a style choice."
  - "Do not latch _note_earliest_pass_ts()'s first candidate without parsing it first (review round 1 finding S2) — an unparseable first pass_ts permanently pins garbage because every later comparison then ValueErrors against stored junk."

danger_areas:
  - "engine/entry_radar/live_pack.py SCHEMA_LIVE_PACK bump to v2 is a pack-identity change: any code outside this diff that hardcodes 'entry_radar.live_pack/v1' as a literal string (none found in this repo at authoring — grepped) would silently stop matching. Re-grep before assuming this stays isolated if new callers appear."
  - "reconcile_entry_radar.read_spool_events() now performs real EntryEvent.from_dict() validation on every inner event of every real envelope, which is materially more work per spool file than the prior bare-schema-string check. Not measured against a large nightly spool; if R-LAB-1's live commissioning produces a very large backlog spool, watch nightly runtime."
  - "Do not confuse this wave's 'confirmed_lanes' pack field with W5's separate ledger-side C5 event application (slice_lanes()'s c5_runs, applied via ledger.apply_run) — they now share ONE slice_lanes() call (moved earlier in main()) but remain two different consumers of the same read; do not re-merge them into one code path without re-reading both docstrings."
---

## Context

See `research/live_entry_radar/W41_TRANSPORT_NOTES.md` for the full technical
writeup (what was broken, what changed per file, verification commands and
output). This handoff is the cold-stranger summary; that doc is the receipts.
