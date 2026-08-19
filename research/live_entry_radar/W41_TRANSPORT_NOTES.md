# W4.1 — live-transport correction, receipts

Wave: `WS-LIVE-ENTRY-RADAR` W4.1 (row minted by #5924, frozen scope per
`research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` §6 item 2A).
Pinned main at authoring: `a7cfd4bef589`; rebased onto `4ae76e4700b6` after
`#5897` (W4 test-baseline repair) and `#5921` (Prophet fusion PR-3D-R1) merged
mid-session — neither touches an owned path.

## What was broken

1. **Confirmed-lane transport.** `live_eval._nightly_lanes()` read
   `pack.probe_set["nightly_lanes"]`. `probe_set_snapshot()` never wrote that
   key (it emits only `{source, market_session, count, tickers, admission}`),
   and `build_pack()` had no other write path — so the G0/C5 confirmed-bar
   lanes were `unavailable`/`slice_store_unconfigured` on EVERY pack, even
   when `scripts/entry_radar_live_pack.py`'s `slice_lanes()` successfully read
   a real Terminal slice and ran G0/C5. The nightly builder computed the real
   per-ticker availability (`per_name` dict, `slice_lanes()` lines ~186-228)
   and then discarded it — it only fed the ledger's C5 episode/event write
   path (`ledger.apply_run`) and a top-level aggregate into `health["lanes"]`
   for the spool, never into the pack itself.
2. **W4→W5 envelope mismatch.** W4 spools one `entry_radar.events/v1` PASS
   ENVELOPE per pass (`live_ledger.build_event_payload()`:
   `schema`/`pass_ts`/`pass_id`/`pack{as_of,pack_hash}`/`transitions[]`/
   `events[]`/`health{}`). W5's `read_spool_events()` gated on top-level
   `schema == "mastermind.entry_event.v1"` (`SPOOL_EVENT_SCHEMA`) — every real
   envelope W4 has ever produced was therefore off-schema and
   counted-by-omission, silently. The W4 firewall docstrings and reviewer
   dispositions (`W4_REVIEW_DISPOSITIONS.md`) confirm this was never
   exercised end-to-end against the real producer shape.

## What changed

### `engine/entry_radar/live_pack.py`
- `SCHEMA_LIVE_PACK` bumped `v1` -> `v2`.
- New `LivePack.confirmed_lanes: dict[str, Any]` field: per-ticker
  `{ticker: {g0: {...}, c5: {...}}}`, always populated (never absent), each
  lane row carrying `availability: "available"|"unavailable"` plus a `reason`
  when unavailable. Defaulted honestly to `slice_store_unconfigured` for any
  ticker the confirmed-lane source did not cover.
- New `confirmed_lanes_snapshot(confirmed_lanes, tickers)` — the NORMALIZER.
  Per-LANE granularity: a malformed `g0` row does not blind a sound sibling
  `c5` row. A non-mapping/`None` row (or the whole ticker missing) falls to
  the unavailable default for BOTH lanes.
- `build_pack()` gained an optional `confirmed_lanes: Mapping[str, Any] | None`
  kwarg — INJECTED, mirroring `store_reader`: this module performs no slice
  IO and names no slice path, exactly as before for the daily store.
- `compute_pack_hash()` now covers `confirmed_lanes` (sorted by ticker) —
  a pack whose slice read moved no longer hashes equal to one whose did not.
  `manifest()`/`with_proof()`/`load_pack()` all carry the field through; a
  pre-W4.1 (v1) manifest with no `confirmed_lanes` key defaults to `{}`
  without raising.

### `engine/entry_radar/live_eval.py`
- `_nightly_lanes()` now reads `pack.confirmed_lanes[ticker]` instead of the
  never-populated `pack.probe_set["nightly_lanes"]`. Same honest
  `unavailable`/`slice_store_unconfigured` fallback for a v1 pack, a ticker
  never probed, or a malformed row — never a `KeyError`, never a
  plausible-looking "no candidates" for a lane that never ran.

### `scripts/entry_radar_live_pack.py`
- New `confirmed_lane_pack_rows(lanes, tickers, slice_dir=...)` — reshapes
  `slice_lanes()`'s per-ticker aggregate (`available`/`reason`/
  `g0_grey_events`/`c5_candidates`/...) into the `{g0: {...}, c5: {...}}` rows
  `confirmed_lanes_snapshot` recognises as `available`.
- `main()` reordered: the confirmed-lane read (`slice_lanes()`) now runs
  BEFORE `build_pack()` (using the same tickers `build_pack` independently
  re-derives via the pure `probe_set_snapshot()`), so the v2 pack carries
  `confirmed_lanes` — and therefore its own `pack_hash` — from the moment it
  exists. Step 4 (ledger C5 event application) reuses the same `lanes`/
  `c5_runs` already computed in step 2; the slice store is read once, not
  twice.

### `scripts/reconcile_entry_radar.py`
- `read_spool_events()` now accepts BOTH shapes:
  - the real W4 envelope (`schema == "entry_radar.events/v1"`): `events[]` is
    unwrapped, each inner event is VALIDATED against
    `mastermind.entry_event.v1` via `EntryEvent.from_dict` (a torn/foreign
    inner event is counted-by-omission, never repaired), and each surviving
    event's `observed_at` is set to the EARLIEST envelope `pass_ts` across the
    WHOLE spool that carried its `event_id` (`_note_earliest_pass_ts`,
    parsed-instant comparison, not string order) — the transport fact is added
    to the RETURNED COPY only, never written into the immutable
    `mastermind.entry_event.v1` record or the append-only store upstream;
  - the bare-event shape the reader already accepted (kept for a producer or
    fixture that spools one event directly with no envelope) — full backward
    compatibility, proven by the unmodified 23-test
    `test_entry_radar_w5_reconciler.py` suite staying green.
- `ENVELOPE_SCHEMA = "entry_radar.events/v1"` named locally (this script keeps
  zero top-level `engine.entry_radar` imports; `EntryEvent`/`EntryEventError`
  are imported lazily inside the function, matching the file's existing lazy
  import convention for `engine.*`).

### Exact-event preservation (contract item 3)
No change to `EntryEventStore` (`entry_events.py`, append-only,
`AppendOnlyViolation` on mutation), `PendingDelta`, or `spool_then_commit`'s
spool-before-consume order. `test_event_identity_is_preserved_byte_exact_through_the_envelope`
asserts every `EVENT_FIELDS` key on the record `read_spool_events()` returns
equals the original `EntryEvent.to_dict()` value, and that the only keys added
are the transport-plane `observed_at`/`_spool_path`.

## Tests

New file: `tests/test_entry_radar_w41_transport.py` (14 tests) — real-envelope
schema acceptance, byte-exact event identity through the envelope,
earliest-`pass_ts` first-observation (proven against reverse file-discovery
order, not "first seen"), torn-inner-event skip, bare-shape backward
compatibility, a full `reconcile_entry_radar.main()` end-to-end run producing
a `forward.parquet` row, v2 schema + default confirmed-lane rows, a real
confirmed-lane row surviving pack -> RTH reader, pack-hash coverage of
`confirmed_lanes`, v1-pack backward compatibility, and per-lane malformed-row
normalization (4 parametrized cases).

## Verification (commands run, this checkout)

```
python3.12 -m pytest tests/test_entry_radar_*.py -q
  -> 1467 passed, 3 skipped

python3.12 -c "
from engine.entry_radar import live_pack as lp
reg = lp.assert_published_spec_hashes()
print(reg == lp.PUBLISHED_SPEC_HASHES)"
  -> True   # six spec hashes byte-identical, no detector spec touched

git diff --stat origin/main -- engine/prophet_bridge.py engine/prophet_doors.py \
  engine/entry_signal.py 'engine/prophet_*.py'
  -> (empty) — Prophet-protected paths untouched
```

## Scope discipline

- No `data/` write path changed beyond what W5 already owned; W5 remains the
  sole durable `data/entry_radar/**` writer (unchanged `DURABLE_WRITES`).
- No detector spec, firing predicate, or `mastermind.entry_event.v1` field
  list change.
- No Prophet Lab API/UI work; nothing armed; no deploy env touched.
- `#5897` (W4 test-baseline repair) merged as `bc7bf982a45a` mid-session; this
  branch was rebased onto its post-merge main and carries no conflicting
  changes (disjoint files — `#5897` touched only
  `tests/test_entry_radar_w4_lane.py`).
