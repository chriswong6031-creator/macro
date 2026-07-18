"""engine.marketing.ledgers — Tiny append-only JSONL helpers.

All functions are fail-soft (never-raise).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Read all lines from a JSONL file.  Returns [] on any error."""
    p = Path(path)
    try:
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("ledgers: skipping malformed line in %s", p)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("ledgers.read_jsonl(%s) failed: %s", path, exc)
        return []


def append_jsonl(path: Path | str, obj: dict[str, Any]) -> bool:
    """Append a JSON line to the file.  Returns True on success."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ledgers.append_jsonl(%s) failed: %s", path, exc)
        return False


def tail(path: Path | str, n: int) -> list[dict[str, Any]]:
    """Return the last n rows from a JSONL file."""
    rows = read_jsonl(path)
    return rows[-n:] if n > 0 else []
