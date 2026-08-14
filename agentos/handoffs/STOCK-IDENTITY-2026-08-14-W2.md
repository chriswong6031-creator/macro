---
workstream: WS:STOCK-IDENTITY
session: stock-identity-w2-replay (Claude, same session as W1, worktree vigorous-mirzakhani-3ae795)
model: fable
ended_because: ci_handoff
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
    what: NEW — TODO-SHIP module list
  - path: scripts/stock_identity_replay_pilot.py + scripts/stock_identity_pilot_addendum.py
    what: NEW — replay CLI + B/GOLD addendum CLI
  - path: data/stock_identity/expert_events/
    what: NEW — family_registry.json, pilot_events_v0.parquet, event_edges_v0.parquet, attribution_v0.parquet, inventory_v0.md (all authority all-false)
  - path: data/stock_identity/ohlcv/B.parquet + addendum artifacts + dossiers B/GOLD
    what: NEW/REGEN — TODO-SHIP receipts
  - path: tests/test_stock_identity_replay*.py + firewall amendment
    what: NEW — TODO-SHIP list
verified:
  - claim: "TODO-SHIP"
    command: "TODO-SHIP"
    result: "TODO-SHIP"
unverified:
  - "TODO-SHIP"
unresolved:
  - "Dead Instrument Control Set (ruling 2): ≥5 identity-resolved terminated US instruments with full adjusted OHLCV on a fingerprint-compatible plane — separately registered act, BLOCKS PR-5/Q1. Not built in W2."
  - "TODO-SHIP: STARTER verdict + any fixture blockers"
next_actions:
  - "W3 / PR-3 (ruler engine + estimability census) needs its own operator/CI-normal start — W2 ends at handoff by ruling; do NOT auto-roll."
  - "TODO-SHIP"
do_not_redo:
  - "Do not reinterpret NYSE GOLD as Barrick/miner anywhere — operator ruling 2026-08-14 + #5613 forensics; B is the miner pilot."
  - "Do not write into the Radar entry_event store or engine/entry_radar/** — W2's store is program-owned and schema-compatible only."
  - "Do not extend R1 for family extraction — the written justification in W2 registration §1 records why its scope cannot serve."
danger_areas:
  - "engine/stock_identity/replay/** is the ONLY place protected signal engines may be imported (read-only, enumerated allowlist, test-enforced); the identity layer's total firewall is load-bearing for G-3."
  - "Class P families must never gain rows (no synthetic history) — zero-row test."
prs: [5612]
decisions:
  - DEC:SI-METHOD-LAW-CHANNELS
---

## Note

TODO-SHIP: final summary.
