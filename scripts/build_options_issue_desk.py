#!/usr/bin/env python3
"""Build a private Issue Desk projection; never a site/R2 publication step."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine import options_issue_desk as desk


def build(*, repo: Path, state_dir: Path, output: Path, reviewer: str, snapshot: bool = True) -> dict:
    """Write a strict, private projection below the durable desk state directory."""
    state = state_dir.resolve()
    destination = output.resolve()
    if state not in destination.parents:
        raise ValueError("Issue Desk projection output must remain below the private state directory")
    payload = desk.document(repo=repo.resolve(), reviewer=reviewer, root=state, snapshot=snapshot)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    with temporary.open("xb") as handle:
        os.chmod(temporary, 0o600)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    directory_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", required=True, help="verified operator user ID")
    parser.add_argument("--no-snapshot", action="store_true")
    args = parser.parse_args()
    payload = build(repo=args.repo, state_dir=args.state_dir, output=args.output, reviewer=args.reviewer, snapshot=not args.no_snapshot)
    print(json.dumps({"schema": payload["schema"], "available_at": payload["available_at"], "proposals": len(payload["proposals"])}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
