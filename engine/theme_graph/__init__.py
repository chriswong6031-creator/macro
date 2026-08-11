"""GMI theme graph — the point-in-time, evidence-backed semantic spine.

`research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §4.1-§4.3 (W1b).

Three modules, one job each:

* :mod:`engine.theme_graph.identity` — permanent node ids. A company node id never
  re-points at a different company; epochs come only from the ratified break file.
* :mod:`engine.theme_graph.store`    — the append-only bitemporal parquet stores and
  their latest-belief read view, lane-gated like every other ledger here.
* :mod:`engine.theme_graph.materialize` — nodes/edges/evidence built from the six live
  membership documents, the crosswalk and the THS concept map.

This package is a PRODUCT DATA PLANE (masterplan §4.5): it assembles what owners
already emit and computes no score, no rank and no weight of its own. The 22
``engine/theme_*.py`` singles are separate organs and are not touched from here.
"""
