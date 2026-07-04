"""
scripts/gen_signal_bus_doc.py — Generate docs/SIGNAL_BUS.md from config/synapse.yml.

Deterministic: same registry -> byte-identical output every run.
No timestamp in output; stable ordering throughout.

Usage:
    python -m scripts.gen_signal_bus_doc            # writes docs/SIGNAL_BUS.md
    python -m scripts.gen_signal_bus_doc --out FILE  # write to a custom path
    python -m scripts.gen_signal_bus_doc --stdout    # print to stdout
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYNAPSE_YML = _REPO_ROOT / "config" / "synapse.yml"
_OUTPUT_DOC = _REPO_ROOT / "docs" / "SIGNAL_BUS.md"

_TOP_N_MERMAID = 15  # cap for the producer->artifact->consumer graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_registry(synapse_path: Path) -> dict[str, Any]:
    with synapse_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data


def _consumer_count(entry: dict) -> int:
    return len(entry.get("consumers", [])) + len(entry.get("external_consumers", []))


def _sorted_artifacts(arts: dict[str, dict]) -> list[tuple[str, dict]]:
    """Return artifacts sorted deterministically: descending consumer_count, then id."""
    return sorted(arts.items(), key=lambda kv: (-_consumer_count(kv[1]), kv[0]))


def _mermaid_safe(s: str) -> str:
    """Escape mermaid node labels: replace / and : with _ for node ids."""
    return s.replace("/", "_").replace(":", "_").replace("-", "_").replace(".", "_")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _header() -> str:
    lines = [
        "# Signal Bus — Artifact Registry",
        "",
        "The **signal bus** is the set of cross-engine data artifacts that flow between "
        "producers and consumers inside the Macro Dashboard engine. Each artifact is the "
        "single authoritative output of one producer (a script or engine module); every "
        "downstream reader — whether another engine module, a site-build script, or an "
        "external system — is listed explicitly. The registry lives in `config/synapse.yml` "
        "and is the single source of truth: it records each artifact's path, format, "
        "freshness SLA, storage backend, tier on the qualification ladder, and full consumer "
        "list derived from the W0 census (workflow wf_67ace3c1 + wf_dd79661a red-team, "
        "2026-07-04). In W0 the registry is **passive** — it names what exists; read-gating "
        "and envelope stamping follow in W1 and W2.",
        "",
        "> generated from `config/synapse.yml` — do not edit by hand; "
        "regenerate with `python -m scripts.gen_signal_bus_doc`",
        "",
    ]
    return "\n".join(lines)


def _summary_tables(arts: dict[str, dict]) -> str:
    lines = ["## Summary", ""]

    # By owner_program
    by_owner: Counter = Counter(v.get("owner_program", "unknown") for v in arts.values())
    lines += [
        "### Artifacts by owner_program",
        "",
        "| owner_program | count |",
        "|---|---|",
    ]
    for owner, count in sorted(by_owner.items()):
        lines.append(f"| {owner} | {count} |")
    lines.append("")

    # By tier
    by_tier: Counter = Counter(v.get("tier", "unknown") for v in arts.values())
    lines += [
        "### Artifacts by tier",
        "",
        "| tier | count |",
        "|---|---|",
    ]
    for tier, count in sorted(by_tier.items()):
        lines.append(f"| {tier} | {count} |")
    lines.append("")

    # By storage
    by_storage: Counter = Counter(v.get("storage", "unknown") for v in arts.values())
    lines += [
        "### Artifacts by storage",
        "",
        "| storage | count |",
        "|---|---|",
    ]
    for storage, count in sorted(by_storage.items()):
        lines.append(f"| {storage} | {count} |")
    lines.append("")

    return "\n".join(lines)


def _per_owner_sections(arts: dict[str, dict]) -> str:
    # Group by owner_program, sorted owner name for stability
    by_owner: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for aid, entry in _sorted_artifacts(arts):
        owner = entry.get("owner_program", "unknown")
        by_owner[owner].append((aid, entry))

    lines = ["## Artifacts by owner_program", ""]

    for owner in sorted(by_owner.keys()):
        entries = by_owner[owner]
        lines += [f"### {owner}", ""]
        lines += [
            "| id | path | format | cadence | tier | consumers | external consumers |",
            "|---|---|---|---|---|---|---|",
        ]
        for aid, entry in entries:
            n_int = len(entry.get("consumers", []))
            n_ext = len(entry.get("external_consumers", []))
            lines.append(
                f"| {aid} "
                f"| `{entry.get('path', '')}` "
                f"| {entry.get('format', '')} "
                f"| {entry.get('cadence', '')} "
                f"| {entry.get('tier', '')} "
                f"| {n_int} "
                f"| {n_ext} |"
            )
        lines.append("")

    return "\n".join(lines)


def _mermaid_graph(arts: dict[str, dict]) -> str:
    """Producer -> artifact -> consumer graph for top N artifacts by consumer count."""
    top_n = _sorted_artifacts(arts)[:_TOP_N_MERMAID]

    # Collect unique producers and consumers across top-N
    # Node ids must be mermaid-safe identifiers
    lines = [
        "## Producer → Artifact → Consumer Graph",
        "",
        f"Flowchart covering the top {_TOP_N_MERMAID} artifacts by total consumer count. "
        "Node count is capped — the full graph (64 artifacts, 200+ nodes) is unreadable.",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    # Track unique node declarations to avoid duplicates
    declared: set[str] = set()

    def declare_node(node_id: str, label: str, shape: str = "default") -> str:
        if node_id in declared:
            return ""
        declared.add(node_id)
        if shape == "artifact":
            return f'    {node_id}["{label}"]'
        elif shape == "producer":
            return f'    {node_id}(("{label}"))'
        else:
            return f'    {node_id}["{label}"]'

    # Build edges: producer -> artifact -> top consumers (cap consumers per artifact)
    MAX_CONSUMERS_SHOWN = 4  # keep graph legible

    producer_nodes: dict[str, str] = {}  # label -> node_id
    artifact_nodes: dict[str, str] = {}  # artifact_id -> node_id
    consumer_nodes: dict[str, str] = {}  # consumer label -> node_id

    def _node_id_for(prefix: str, label: str) -> str:
        return f"{prefix}_{_mermaid_safe(label)}"

    node_declarations: list[str] = []
    edge_lines: list[str] = []

    for aid, entry in top_n:
        producer = entry.get("producer", "?")
        consumers = entry.get("consumers", [])
        ext_consumers = entry.get("external_consumers", [])
        all_consumers = consumers + ext_consumers

        # Producer node
        prod_id = _node_id_for("P", producer)
        if prod_id not in producer_nodes:
            producer_nodes[prod_id] = producer
            node_declarations.append(f'    {prod_id}(("{producer}"))')

        # Artifact node
        art_id = _node_id_for("A", aid)
        if art_id not in artifact_nodes:
            artifact_nodes[art_id] = aid
            node_declarations.append(f'    {art_id}["{aid}"]')

        edge_lines.append(f"    {prod_id} --> {art_id}")

        # Consumer nodes (capped)
        shown = all_consumers[:MAX_CONSUMERS_SHOWN]
        overflow = len(all_consumers) - len(shown)
        for c in shown:
            c_id = _node_id_for("C", c)
            if c_id not in consumer_nodes:
                consumer_nodes[c_id] = c
                node_declarations.append(f'    {c_id}["{c}"]')
            edge_lines.append(f"    {art_id} --> {c_id}")

        if overflow > 0:
            overflow_id = _node_id_for("OVF", aid)
            node_declarations.append(f'    {overflow_id}["...+{overflow} more"]')
            edge_lines.append(f"    {art_id} --> {overflow_id}")

    lines.extend(node_declarations)
    lines.extend(edge_lines)
    lines += ["```", ""]

    return "\n".join(lines)


def _rot_appendix(arts: dict[str, dict]) -> str:
    """Appendix: artifacts with non-empty known_extra_writers."""
    entries_with_rot = [
        (aid, entry)
        for aid, entry in sorted(arts.items())
        if entry.get("known_extra_writers")
    ]

    lines = [
        "## Appendix — Known Extra Writers",
        "",
        "Artifacts below have `known_extra_writers` — additional code paths that write "
        "to the same artifact outside the declared producer. These are flagged for "
        "eventual single-writer consolidation under the Neural Web architecture.",
        "",
    ]

    for aid, entry in entries_with_rot:
        writers = entry.get("known_extra_writers", [])
        path = entry.get("path", "")
        lines += [
            f"### {aid}",
            "",
            f"- **path:** `{path}`",
            f"- **declared producer:** `{entry.get('producer', '?')}`",
            "- **extra writers:**",
        ]
        for w in writers:
            lines.append(f"  - {w}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate(synapse_path: Path = _SYNAPSE_YML) -> str:
    """Return the full SIGNAL_BUS.md content as a string."""
    registry = _load_registry(synapse_path)
    arts: dict[str, dict] = registry.get("artifacts", {})

    sections = [
        _header(),
        _summary_tables(arts),
        _per_owner_sections(arts),
        _mermaid_graph(arts),
        _rot_appendix(arts),
    ]

    # Join sections; ensure file ends with exactly one newline
    content = "\n".join(sections)
    if not content.endswith("\n"):
        content += "\n"
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate docs/SIGNAL_BUS.md from config/synapse.yml")
    parser.add_argument("--out", type=Path, default=None, help="Output path (default: docs/SIGNAL_BUS.md)")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing a file")
    args = parser.parse_args()

    content = generate()

    if args.stdout:
        sys.stdout.write(content)
        return

    out_path = args.out if args.out is not None else _OUTPUT_DOC
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
