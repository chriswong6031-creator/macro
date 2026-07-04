"""Oracle — Rotation Intelligence Web.

Package root (O0–O6).  This namespace deliberately matches the program name
(decision D4 in research/ORACLE_MASTERPLAN_BY_FABLE.md) and does NOT collide
with the existing signal-contract key ``oracle`` in
``scripts/export_signal_contracts.py`` or the "perfect-information baseline"
usage in ``research/entry_timing/`` — those are plain string tokens, not
Python module references.

Sub-modules shipped:
  panel.py  — build_panel_s / build_panel_m  (the rotation panel substrate; P1b)
  graph.py  — build_graph + edge estimation, stability ledger, lead-lag tensor,
               flow-routing matrix, agglomerative clustering (P2a)

Planned in later phases:
  episodes.py, memory.py, live.py
"""
