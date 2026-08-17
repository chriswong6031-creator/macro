"""engine.entry_radar.replay — W5 / PR-5 forward-evidence + replay machinery.

Governing document (load-bearing, not prose): the merged W5 preregistration
``research/live_entry_radar/W5_FORWARD_EVIDENCE_PREREG.md``.  Every frozen number
in this package mirrors that document via :mod:`engine.entry_radar.replay.prereg`,
and the runner refuses to read a single outcome unless the §14 gates verify
(doc hash, merged ancestry, TrialLedger budget row, W3 detector spec hashes).

Package law (inherited, W3 §A5.0 + contract §7):

* PURE ENGINE — no network, no wall-clock, no environment reads, no durable
  writes anywhere in this package.  Vendor I/O lives in
  ``scripts/entry_radar_vendor.py``; orchestration in
  ``scripts/entry_radar_replay.py``; the ONLY durable evidence writer is
  ``scripts/reconcile_entry_radar.py --nightly`` gated by
  ``engine.ledger_lane.nightly_advance_enabled()``.
* Authority all-false.  Nothing here ranks, sizes, gates, originates signals, or
  escalates.  Outcome rows test Radar; they never become per-ticker strategy
  keys (contract §9 side-door law, battery M).
* Replay evidence rows are research artifacts (append-only, fingerprinted),
  never the production forward ledger and never `mastermind.entry_event.v1`
  mutations.
"""
