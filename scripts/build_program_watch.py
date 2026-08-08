#!/usr/bin/env python3
"""Emit the biopharma seasonality program watch — WHEN to check in, and with WHAT.

Writes ``data/seasonality/program_watch.json``: four tripwires read from real
repo state, each carrying the exact prompt to paste back when it fires, and each
distinguishing "checked, not yet" from "could not check".

Two properties this file exists to hold:

* **Idempotent.**  Two runs over identical inputs produce byte-identical JSON.
  The engine takes ``asof`` as an explicit argument and reads no clock, so the
  only clock read in the whole lane is the ``--asof`` default below — resolved
  exactly the way the sibling ``build_seasonality_shadow_state`` resolves it
  (the covered set's own ``as_of``, falling back to the UTC date).  The file is
  written tmp + ``os.replace`` so a reader never sees a half-written artifact.
* **Annotations that actually appear.**  Every FIRED tripwire is printed as a
  bare ``print("::notice ...", flush=True)``.  House law, guarded repo-wide by
  ``tests/test_gh_annotation_line_start.py``: every builder here logs with a
  prefixing format, so ``log.info("::notice ...")`` emits ``INFO ::notice ...``
  and GitHub silently drops it — the call reviews as an alarm, runs clean, and
  produces nothing in the Actions summary.  ``flush`` is load-bearing because
  stdout is block-buffered when piped in Actions.

Nothing this writes is user-facing.  ``site/measurement.html`` renders ONE fact
derived from the same ledger counts (windows on the record, windows graded) and
nothing else: the prompts, doc paths, and module names here are private-channel
content and a leak of any of them onto a ``site/`` page is a defect.

Fail-open: a watch must never take the nightly down.  ``main`` returns 0
unconditionally.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.seasonality import program_watch  # noqa: E402

log = logging.getLogger("build_program_watch")

INDEX_PATH = "site/seasonalitydata/index.json"
OUT_PATH = "data/seasonality/program_watch.json"


def _escape_annotation(value: str) -> str:
    """Percent-encode the three characters that corrupt an Actions annotation.

    GitHub's workflow-command grammar is line-oriented: an unescaped newline
    truncates the annotation at that point and a stray ``%`` can eat the
    following two characters as an escape.  These messages interpolate matched
    FILENAMES from the contracts directory and free-text ``why`` prose, so the
    payload is not under this file's control.  ``%`` first — escaping it after
    the others would double-encode the ``%0A`` they produce.
    """
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _notice(title: str, message: str) -> None:
    """Emit a GitHub Actions annotation.

    A bare ``print`` on purpose — see the module docstring.  Never route this
    through ``log``: a prefixed record is not an annotation, it is a log line
    that looks like one.
    """
    print(
        f"::notice title={_escape_annotation(title)}::{_escape_annotation(message)}",
        flush=True,
    )


def resolve_asof(root: Path, *, now: datetime | None = None) -> str:
    """The as-of this watch is stamped with.

    Same ladder as ``scripts/build_seasonality_shadow_state``: the covered set's
    own ``as_of`` first, the UTC date only as a fallback.  Reading the index
    keeps the watch on the same clock as the artifacts it is watching, so a
    checkout whose index is a night stale does not report a fresher as-of than
    the state it actually inspected.
    """
    index_path = root / INDEX_PATH
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = None
    if isinstance(loaded, dict):
        raw = loaded.get("as_of")
        if isinstance(raw, str) and raw:
            try:
                return date.fromisoformat(raw[:10]).isoformat()
            except ValueError:
                pass
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).date().isoformat()


def write_atomic(path: Path, text: str) -> None:
    """tmp + ``os.replace`` — a reader never sees a partial artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def build(*, root: Path, asof: str | None = None) -> dict[str, Any]:
    """Evaluate, annotate the fired tripwires, write the artifact, return a summary."""
    root = Path(root)
    started = time.time()
    resolved = asof or resolve_asof(root)
    payload = program_watch.evaluate(root, asof=resolved)

    for tripwire in payload["tripwires"]:
        if tripwire["state"] != "fired":
            continue
        _notice(
            f"seasonality_watch_{tripwire['key']}",
            f"{tripwire['headline']} — {tripwire['why']}",
        )

    out = root / OUT_PATH
    write_atomic(
        out,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    summary = {
        "asof": resolved,
        "counts": payload["counts"],
        "fired": [t["key"] for t in payload["tripwires"] if t["state"] == "fired"],
        "bytes": out.stat().st_size,
        "elapsed_s": round(time.time() - started, 2),
    }
    log.info("seasonality program watch: %s", json.dumps(summary, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the biopharma seasonality program watch."
    )
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    parser.add_argument(
        "--asof",
        default=None,
        help="ISO date to stamp. Default: site/seasonalitydata/index.json as_of, "
        "falling back to the UTC date (same ladder as build_seasonality_shadow_state).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        summary = build(root=args.root, asof=args.asof)
        print(json.dumps(summary, sort_keys=True), flush=True)
    except Exception as exc:  # noqa: BLE001 — fail-open: a watch never blocks the nightly
        log.warning("seasonality program watch failed: %s", exc, exc_info=True)
        print(
            "::warning title=seasonality_program_watch::"
            + _escape_annotation(f"build failed ({exc}) — previous watch retained"),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
