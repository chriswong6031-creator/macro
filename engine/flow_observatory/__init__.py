"""engine.flow_observatory — the flow_observatory.v2 contract package (Flow Observatory V2).

Module layout freeze (masterplan §4): ``engine/flow_velocity.py`` keeps the velocity math
and panel builders; this package owns the additive schema on top of it.

  contract.py  — pure assembly/validation of the ``flow_observatory.v2`` additive fields
                 (quadrant classification, abs/rel enrichment, market_read, sources[]).
                 No I/O. W1.
  changes.py   — ``data/flow_observatory/state_log.jsonl`` (W1 minimal precursor) and
                 ``change_summary`` (previous-session diff). W1 minimal, W3 full.
  quality.py   — the per-leg HEALTHY/DEGRADED/STALE/UNAVAILABLE/REVISED state machine (W2).
  history.py   — the append-only observations ledger + replay (W3).
  groups.py    — official/curated lenses, coverage floor, overlap, concentration and
                 contribution (W4). Reuses ``engine.flow_velocity``'s kinetics
                 primitives; no second velocity engine.
"""
from __future__ import annotations
