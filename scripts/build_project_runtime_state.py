#!/usr/bin/env python3
"""Collect and render the private Mastermind-X runtime-state manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.project_runtime_state import (  # noqa: E402
    SystemEvidenceReader,
    canonical_json,
    collect_runtime_state,
    load_topology,
    render_markdown,
    validate_snapshot,
    write_private_atomic,
)

DEFAULT_TOPOLOGY = ROOT / "config" / "production_topology.yml"
DEFAULT_SCHEMA = ROOT / "contracts" / "runtime" / "mastermind.runtime_state.v1.schema.json"


def _private_target(value: str) -> Path:
    target = Path(value).expanduser().resolve()
    for public_root in (ROOT / "site", ROOT / "data", ROOT / "docs"):
        resolved_root = public_root.resolve()
        if target == resolved_root or resolved_root in target.parents:
            raise argparse.ArgumentTypeError(
                "volatile runtime state cannot be written under site/, data/, or docs/"
            )
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a sanitized, read-only runtime snapshot from reviewed topology.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--vps", action="store_true", help="read bounded evidence from VPS paths")
    modes.add_argument("--local", action="store_true", help="run locally; missing VPS evidence is explicit")
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--format", choices=("json", "markdown", "none"), default="json")
    parser.add_argument("--json-out", type=_private_target, help="atomic private JSON output path")
    parser.add_argument("--markdown-out", type=_private_target, help="atomic private Markdown output path")
    parser.add_argument("--render", type=_private_target, help="alias for --markdown-out")
    parser.add_argument("--check", action="store_true", help="validate the canonical JSON Schema and privacy guard")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.render and args.markdown_out:
        _parser().error("--render and --markdown-out are aliases; choose one")
    mode = "vps" if args.vps or (not args.local and Path("/opt/macro").is_dir()) else "local"
    topology = load_topology(args.topology)
    snapshot = collect_runtime_state(
        topology,
        reader=SystemEvidenceReader(mode=mode, repo_root=ROOT),
        mode=mode,
    )
    if args.check:
        validate_snapshot(snapshot, args.schema_path)
    json_text = canonical_json(snapshot)
    markdown = render_markdown(snapshot)
    if args.json_out:
        write_private_atomic(args.json_out, json_text)
    markdown_target = args.markdown_out or args.render
    if markdown_target:
        write_private_atomic(markdown_target, markdown)
    if args.format == "json":
        sys.stdout.write(json_text)
    elif args.format == "markdown":
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
