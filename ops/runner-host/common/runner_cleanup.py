#!/usr/bin/env python3
"""Fail-closed cleanup for sealed persistent PC CI runner slots."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


# The sealed PC CI slots, and nothing else. This is an exact allowlist, not a
# prefix match: runner-5, runner-0 and any render root are refused, so a
# mistyped or hostile --runner-root can never scrub a tree this helper does not
# own. Adding a root here is a deliberate capacity act.
PC_CI_ROOTS = {
    Path("/opt/mastermind-ci/runner-1"),
    Path("/opt/mastermind-ci/runner-2"),
    Path("/opt/mastermind-ci/runner-3"),
    Path("/opt/mastermind-ci/runner-4"),
}


def remove_entry(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)


def scrub_pc_state(
    runner_root: Path,
    temporary_roots: tuple[Path, ...] = (Path("/tmp"), Path("/var/tmp")),
) -> int:
    work = runner_root / "_work"
    if (
        runner_root not in PC_CI_ROOTS
        or runner_root.is_symlink()
        or runner_root.resolve(strict=False) != runner_root
        or not work.is_dir()
        or work.is_symlink()
        or work.resolve(strict=True).parent != runner_root
    ):
        raise RuntimeError("runner work root is outside the sealed PC CI allowlist")
    scrubbed = 0
    for entry in work.iterdir():
        remove_entry(entry)
        scrubbed += 1
    for directory in (work / "_temp", work / "_home"):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)
    for temporary in temporary_roots:
        if temporary.is_dir() and not temporary.is_symlink():
            for entry in temporary.iterdir():
                remove_entry(entry)
                scrubbed += 1
    return scrubbed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-root", required=True)
    args = parser.parse_args()
    try:
        scrubbed = scrub_pc_state(Path(args.runner_root))
    except (OSError, RuntimeError) as exc:
        print(f"::error title=runner-cleanup::state scrub failed: {exc}", flush=True)
        return 78
    print(
        "RUNNER_CLEANUP="
        + json.dumps(
            {
                "schema": "runner.cleanup.v1",
                "runner_root": args.runner_root,
                "scrubbed_entries": scrubbed,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
