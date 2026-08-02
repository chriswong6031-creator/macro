"""Admit and atomically publish a human-reviewed recipient entity graph.

This command never derives mappings from discovery tickers or recipient names.
An analyst supplies the complete candidate JSON; the command applies the same
strict exact-ID, temporal, evidence, ownership, ambiguity, and cycle admission
used by the runtime before replacing the canonical graph.

Usage::

    python -m scripts.curate_government_revenue_recipient_graph \
      --input /path/to/reviewed-candidate.json
    python -m scripts.curate_government_revenue_recipient_graph \
      --input data/government_revenue/recipient_entity_graph.json --check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue.entity_resolution import (  # noqa: E402
    load_recipient_entity_graph,
)


DEFAULT_TARGET = _ROOT / "data" / "government_revenue" / "recipient_entity_graph.json"


def _canonical_graph_bytes(graph: dict[str, Any]) -> str:
    return json.dumps(
        graph,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def curate_graph(
    input_path: Path,
    *,
    target_path: Path = DEFAULT_TARGET,
    as_of: str | None = None,
    check_only: bool = False,
) -> dict[str, Any]:
    """Validate a complete reviewed graph and optionally publish exact bytes."""

    try:
        source = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("reviewed recipient graph candidate is unreadable") from exc
    if not isinstance(source, dict):
        raise ValueError("reviewed recipient graph candidate must be a JSON object")
    cutoff = as_of or source.get("graph_known_at")
    loaded = load_recipient_entity_graph(source, as_of=cutoff)
    if loaded.get("status") != "ready":
        codes = ",".join(loaded.get("error_codes") or ["unknown_graph_error"])
        raise ValueError(f"reviewed recipient graph candidate failed admission: {codes}")
    if not check_only:
        _atomic_write(target_path, _canonical_graph_bytes(source))
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strictly admit a complete human-reviewed recipient graph."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--as-of",
        help="Optional inclusive knowledge cutoff; defaults to graph_known_at.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate without replacing the canonical graph.",
    )
    args = parser.parse_args()
    loaded = curate_graph(
        args.input,
        target_path=args.target,
        as_of=args.as_of,
        check_only=args.check,
    )
    action = "validated" if args.check else "published"
    print(
        f"recipient graph {action}: id={loaded.get('graph_id')} "
        f"digest={loaded.get('graph_digest')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
