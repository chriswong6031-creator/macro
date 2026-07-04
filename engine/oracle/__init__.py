"""Oracle — Rotation Intelligence Web.

Package root (O0–O6).  This namespace deliberately matches the program name
(decision D4 in research/ORACLE_MASTERPLAN_BY_FABLE.md) and does NOT collide
with the existing signal-contract key ``oracle`` in
``scripts/export_signal_contracts.py`` or the "perfect-information baseline"
usage in ``research/entry_timing/`` — those are plain string tokens, not
Python module references.

Sub-modules shipped:
  panel.py       — build_panel_s / build_panel_m  (the rotation panel substrate; P1b)
  graph.py       — build_graph + edge estimation, stability ledger, lead-lag tensor,
                   flow-routing matrix, agglomerative clustering (P2a)
  episodes.py    — hysteresis state machine + rotation episode catalog (P2b)
  timemachine.py — Time Machine feed helpers (P6)
  live.py        — build_oracle_state → site/basketdata/oracle_state.json (P5)
  alerts.py      — state-diff alert engine, idempotent ids, silent seed (P5)
  tilt.py        — config-gated [-1,1] dark tilt for stock_score (P5)
"""
