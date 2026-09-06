"""Market Ontology: pure read-only projections over engine.theme_graph (GMI).

A leaf consumer plane, not a graph owner. Every module here reads GMI only through
``engine.theme_graph.store``'s public collapse functions (``read_edges(latest_belief=True)``,
``read_identity_resolution(latest=True)``) and enforces rights only through
``engine.theme_graph.rights`` — never a raw parquet read, never a second rights
implementation. Nothing in the scoring path may import this package.

No re-exports beyond the three public names below.
"""
from __future__ import annotations

from engine.market_ontology.exposure_map import ShockSpec, compose_exposure_map, to_json

__all__ = ["compose_exposure_map", "ShockSpec", "to_json"]
