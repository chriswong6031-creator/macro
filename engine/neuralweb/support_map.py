"""engine.neuralweb.support_map — Dependency blast-radius library (W2, RUL-CC-7/CC-14).

Pure-function library over config/synapse.yml.  No side effects, no file writes.

RUL-CC-7: synapse.yml is the authoritative adjacency source.
           confluence_graph.json is a derived view and may NOT be the traversal substrate.
RUL-CC-14: results carry bound='upper' because shared-producer inversion over-attributes
           (a consumer module that produces several artifacts folds all of them in even if
           only one actually reads the input).  This is the right conservatism for an
           operational "what might be compromised" query.

Language law (RUL-CC-5 / RUL-CC-6 extensions):
  - All language describes "downstream surfaces that read this artifact (directly or
    transitively)".
  - Banned strings: "would have", "caused" — do not reintroduce them.

Public API
----------
load_graph(root=None) -> SynapseGraph
    Parse synapse.yml once; return a SynapseGraph dataclass.

downstream(graph, artifact_id) -> list[dict]
    Artifact-level traversal to fixpoint. Returns hop-annotated dicts:
      {artifact_id, hop, via_module, bound, note}

upstream(graph, artifact_id) -> list[dict]
    Transitive inputs.  Returns hop-annotated dicts:
      {artifact_id, hop, via_module, bound, note}

consumers_direct(graph, artifact_id) -> list[dict]
    1-hop consumer module list with terminal flag.

coverage_vs_confluence(confluence_graph_path, graph=None, root=None) -> list[str]
    Registered-but-missing-from-confluence artifact ids.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo root (two levels up from engine/neuralweb/)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent

_OVERATTRIBUTION_NOTE = (
    "Bound is upper: a consumer module that produces multiple artifacts has all its "
    "outputs folded in, even if only one artifact directly reads the upstream input. "
    "Downstream artifacts that read this artifact (directly or transitively); "
    "terminal display surfaces are listed at hop 1 only. "
    "Use for operational 'what downstream artifacts read this' queries — not for "
    "causal attribution."
)

_UPSTREAM_NOTE = (
    "Bound is exact: upstream traversal follows consumer-lists directly — "
    "each result is an artifact whose consumer list includes the producer of "
    "the query artifact (or a transitive ancestor thereof). "
    "No over-attribution applies in the upstream direction."
)

# Module-level cache: (path_str, mtime_ns) -> SynapseGraph
_GRAPH_CACHE: dict[tuple[str, int], "SynapseGraph"] = {}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SynapseGraph:
    """Parsed view over config/synapse.yml for support-map traversal.

    Attributes
    ----------
    artifacts : {artifact_id: {path, producer, consumers, freshness_sla_hours, tier}}
    producer_to_artifacts : {module_path: [artifact_id, ...]}
        Inverted index — all artifacts a given module produces.
        Note: a module producing >1 artifact is the source of the upper-bound
        over-attribution described in RUL-CC-14.
    """
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    producer_to_artifacts: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Graph loader
# ---------------------------------------------------------------------------

def load_graph(root: str | Path | None = None) -> SynapseGraph:
    """Parse config/synapse.yml and return a SynapseGraph.

    Results are memoized by (resolved path, file mtime_ns) so repeated calls
    within the same process pay the parse cost only on the first call or when
    the file is modified.

    Raises
    ------
    FileNotFoundError  — if synapse.yml does not exist at the resolved root.
    ImportError        — if pyyaml is not installed.
    ValueError         — if synapse.yml has no 'artifacts' mapping.
    """
    repo = Path(root) if root is not None else _ROOT
    synapse_path = repo / "config" / "synapse.yml"

    # Cache lookup keyed on (path, mtime_ns) — avoids re-parsing the 6100-line file
    path_str = str(synapse_path.resolve())
    try:
        mtime_ns = os.stat(path_str).st_mtime_ns
    except OSError:
        mtime_ns = 0
    cache_key = (path_str, mtime_ns)
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]

    import yaml  # noqa: PLC0415 — optional dep, present in the engine venv

    raw = yaml.safe_load(synapse_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("artifacts"), dict):
        raise ValueError(f"synapse.yml at {synapse_path} has no 'artifacts' mapping")

    raw_artifacts: dict[str, dict] = raw["artifacts"]

    # Build per-artifact compact view
    artifacts: dict[str, dict[str, Any]] = {}
    producer_to_artifacts: dict[str, list[str]] = {}

    for art_id, entry in raw_artifacts.items():
        if not isinstance(entry, dict):
            continue
        artifacts[art_id] = {
            "path": entry.get("path", ""),
            "producer": entry.get("producer", ""),
            "consumers": list(entry.get("consumers") or []),
            "freshness_sla_hours": entry.get("freshness_sla_hours"),
            "tier": entry.get("tier", ""),
        }
        producer = entry.get("producer", "")
        if producer:
            producer_to_artifacts.setdefault(producer, []).append(art_id)

    graph = SynapseGraph(
        artifacts=artifacts,
        producer_to_artifacts=producer_to_artifacts,
    )
    _GRAPH_CACHE[cache_key] = graph
    return graph


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------

def downstream(
    graph: SynapseGraph,
    artifact_id: str,
) -> list[dict[str, Any]]:
    """Artifact-level downstream traversal to fixpoint (no hop cap).

    For each hop:
      artifact → consumer modules → artifacts those modules produce → ...

    Returns
    -------
    List of dicts, each: {artifact_id, hop, via_module, bound, note}
    Excludes the seed artifact_id itself.
    The result set carries bound='upper' (see RUL-CC-14 / module docstring).

    Terminates at fixpoint: the loop exits when no new artifacts are discovered.
    Handles cycles: any artifact already seen is not re-queued.
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = {artifact_id}

    # frontier: list of (artifact_id_to_expand, current_hop)
    frontier: list[tuple[str, int]] = [(artifact_id, 0)]

    while frontier:
        current_id, hop = frontier.pop(0)

        art = graph.artifacts.get(current_id)
        if art is None:
            continue

        for module in art["consumers"]:
            # Find all artifacts this consumer module produces
            produced = graph.producer_to_artifacts.get(module, [])
            # Also handle terminal consumers (produce nothing registered)
            is_terminal = len(produced) == 0
            if is_terminal:
                # Terminal consumers are shown in consumers_direct, not here
                continue

            for new_art_id in produced:
                if new_art_id in seen:
                    continue
                seen.add(new_art_id)
                result.append({
                    "artifact_id": new_art_id,
                    "hop": hop + 1,
                    "via_module": module,
                    "bound": "upper",
                    "note": _OVERATTRIBUTION_NOTE,
                })
                frontier.append((new_art_id, hop + 1))

    return result


def upstream(
    graph: SynapseGraph,
    artifact_id: str,
) -> list[dict[str, Any]]:
    """Artifact-level upstream traversal to fixpoint (no hop cap).

    Walks in the reverse direction: artifacts whose consumer-module list includes
    the producer of the seed artifact, recursively.

    The question answered: "which registered artifacts flow into this artifact,
    directly or transitively?"

    Returns
    -------
    List of dicts, each: {artifact_id, hop, via_module, bound, note}
    Excludes the seed artifact_id itself.
    Carries bound='exact': upstream traversal follows consumer-lists directly
    with no shared-producer inversion, so there is no over-attribution.
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = {artifact_id}

    # Build a reverse index on demand: consumer_module → [artifact_ids that list it]
    # (i.e. "which artifacts are read by this module")
    # For upstream: we want artifacts that produce output read by the seed's producer.
    # Traversal: seed producer is a consumer_module → find artifacts that list it →
    # those artifacts' producers are also consumer_modules → recurse.

    # Frontier: list of (module_path_to_find_in_consumers, current_hop)
    seed_art = graph.artifacts.get(artifact_id)
    if seed_art is None:
        return []

    seed_producer = seed_art["producer"]
    if not seed_producer:
        return []

    # We need: "which artifacts have this module in their consumers list?"
    # Build reverse consumer index: consumer_module → [artifact_id, ...]
    consumer_to_artifacts: dict[str, list[str]] = {}
    for art_id, art in graph.artifacts.items():
        for mod in art["consumers"]:
            consumer_to_artifacts.setdefault(mod, []).append(art_id)

    # frontier: module paths whose consuming-artifact ancestors we want
    frontier: list[tuple[str, int]] = [(seed_producer, 0)]
    visited_modules: set[str] = {seed_producer}

    while frontier:
        module, hop = frontier.pop(0)

        # Find artifacts that list this module as a consumer
        for src_art_id in consumer_to_artifacts.get(module, []):
            if src_art_id in seen:
                continue
            seen.add(src_art_id)
            result.append({
                "artifact_id": src_art_id,
                "hop": hop + 1,
                "via_module": module,
                "bound": "exact",
                "note": _UPSTREAM_NOTE,
            })
            # The producer of this upstream artifact is the next module to trace
            src_art = graph.artifacts.get(src_art_id)
            if src_art is None:
                continue
            src_producer = src_art["producer"]
            if src_producer and src_producer not in visited_modules:
                visited_modules.add(src_producer)
                frontier.append((src_producer, hop + 1))

    return result


def consumers_direct(
    graph: SynapseGraph,
    artifact_id: str,
) -> list[dict[str, Any]]:
    """Return 1-hop consumer modules for an artifact.

    Each entry: {module, terminal, produced_artifacts}
      terminal=True  — this module produces no registered artifact (site builders,
                       admin, notify, etc.); it is a downstream surface end-node.
      terminal=False — this module produces ≥1 registered artifact; it passes the
                       data onward in the pipeline.
    produced_artifacts is the list of artifact ids this module produces (empty if terminal).
    """
    art = graph.artifacts.get(artifact_id)
    if art is None:
        return []

    result: list[dict[str, Any]] = []
    for module in art["consumers"]:
        produced = graph.producer_to_artifacts.get(module, [])
        result.append({
            "module": module,
            "terminal": len(produced) == 0,
            "produced_artifacts": produced,
        })
    return result


def coverage_vs_confluence(
    confluence_graph_path: str | Path,
    graph: SynapseGraph | None = None,
    root: str | Path | None = None,
) -> list[str]:
    """Compare synapse-registered artifact ids vs confluence_graph.json edge references.

    Returns the list of artifact ids that are registered in synapse.yml but do NOT
    appear as 'artifact:<id>' references in any edge of the confluence graph.

    Parameters
    ----------
    confluence_graph_path : path to data/neuralweb/confluence_graph.json
    graph : pre-loaded SynapseGraph (loads if None)
    root  : repo root (used only when graph is None)

    Notes
    -----
    RUL-CC-7: synapse.yml is authoritative.  This function surfaces drift between
    the two registries for ops monitoring — it does NOT use confluence_graph as a
    traversal substrate.
    """
    if graph is None:
        graph = load_graph(root)

    cg_path = Path(confluence_graph_path)
    if not cg_path.exists():
        # Can't compare — return all registered ids as "unknown coverage"
        return sorted(graph.artifacts.keys())

    try:
        cg = json.loads(cg_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return sorted(graph.artifacts.keys())

    # Collect all artifact ids referenced in any edge
    referenced: set[str] = set()
    for edge in cg.get("edges") or []:
        for field in ("src", "dst"):
            val = edge.get(field)
            if isinstance(val, str) and val.startswith("artifact:"):
                referenced.add(val[len("artifact:"):])

    registered = set(graph.artifacts.keys())
    missing = sorted(registered - referenced)
    return missing
