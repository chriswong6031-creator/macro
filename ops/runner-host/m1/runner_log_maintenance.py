#!/usr/bin/env python3
"""Compress and bound inactive Actions runner diagnostic logs."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import time
from pathlib import Path


INCIDENT = re.compile(rb"No space left on device|ENOSPC|##\[error\]", re.I)
GIB = 1024**3


def contains_incident(path: Path) -> bool:
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                if INCIDENT.search(chunk):
                    return True
    except OSError:
        return True
    return False


def compress(path: Path) -> Path:
    destination = path.with_name(path.name + ".gz")
    temporary = destination.with_name(destination.name + ".tmp")
    with path.open("rb") as source, gzip.open(temporary, "wb", compresslevel=6) as out:
        shutil.copyfileobj(source, out)
    os.replace(temporary, destination)
    path.unlink()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diag", type=Path, required=True)
    parser.add_argument("--soft-cap-bytes", type=int, default=GIB)
    args = parser.parse_args()
    now = time.time()
    actions: list[dict[str, object]] = []
    args.diag.mkdir(parents=True, exist_ok=True)
    index_path = args.diag / ".incident-index.json"
    try:
        incident_index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        incident_index = {}
    if not isinstance(incident_index, dict):
        incident_index = {}

    # Never touch a file younger than one day: it may be the listener's active log.
    for path in sorted(args.diag.glob("*.log")):
        age_days = (now - path.stat().st_mtime) / 86400
        if age_days < 1:
            continue
        incident = contains_incident(path)
        archived = compress(path)
        incident_index[archived.name] = incident
        actions.append({"action": "compressed", "file": archived.name, "incident": incident})

    archives: list[tuple[Path, bool]] = []
    for path in sorted(args.diag.glob("*.log.gz"), key=lambda item: item.stat().st_mtime):
        age_days = (now - path.stat().st_mtime) / 86400
        # Pre-policy archives have no index. Preserve them conservatively as
        # incident evidence for 30 days instead of decompressing hundreds of files
        # on every listener restart. Every newly compressed log is classified above.
        incident = bool(incident_index.get(path.name, True))
        incident_index[path.name] = incident
        retention = 30 if incident else 14
        if age_days > retention:
            size = path.stat().st_size
            path.unlink()
            incident_index.pop(path.name, None)
            actions.append({"action": "expired", "file": path.name, "bytes": size})
        else:
            archives.append((path, incident))

    bytes_after = sum(
        item.stat().st_size for item in args.diag.iterdir() if item.is_file()
    )

    # A soft cap may evict only normal archives. Incident-bearing evidence keeps
    # its 30-day window even when the cap is exceeded.
    for path, incident in archives:
        if bytes_after <= args.soft_cap_bytes:
            break
        if incident or not path.exists():
            continue
        size = path.stat().st_size
        path.unlink()
        incident_index.pop(path.name, None)
        bytes_after -= size
        actions.append({"action": "cap-expired", "file": path.name, "bytes": size})

    temporary_index = index_path.with_suffix(".tmp")
    temporary_index.write_text(
        json.dumps(incident_index, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_index, index_path)
    bytes_after = sum(
        item.stat().st_size for item in args.diag.iterdir() if item.is_file()
    )

    print(
        "RUNNER_LOG_MAINTENANCE="
        + json.dumps(
            {
                "schema": "runner.log_maintenance.v1",
                "diag": str(args.diag.resolve()),
                "bytes_after": bytes_after,
                "soft_cap_bytes": args.soft_cap_bytes,
                "normal_retention_days": 14,
                "incident_retention_days": 30,
                "actions": actions,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
