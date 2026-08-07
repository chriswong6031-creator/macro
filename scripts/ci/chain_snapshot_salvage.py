"""Select the delayed-chain snapshot files that are safe to commit after a red collect.

WHY THIS EXISTS (2026-08-06 postmortem — see collectors/cboe.py KNOWN_PERMANENT_GAPS)
------------------------------------------------------------------------------------
`commit data` in daily.yml gates on ``steps.collectors.outcome == 'success'``, and that
gate is correct: the collectors step is the only producer of the bulk market plane, and
committing that tree behind a red/skipped producer is what caused the 2026-08-04 P0.

But two stores in that tree are not like the others. ``data/cboe/putcall.parquet`` and
``data/cboe/gex*.parquet`` are ONE-ROW-PER-SESSION SNAPSHOTS of a delayed-quotes chain
endpoint that serves only the LIVE book. Every other store re-fetches its history each
night, so a skipped commit costs those nothing — the next run refills them. These twelve
cannot be refilled by anything, ever. When the commit is skipped the row is still on
disk, and the next run's ``actions/checkout`` (clean by default) resets the tracked
parquet and destroys it.

That is not a hypothetical. 2026-08-03: gex + all ten symbols recovered on the
post-cooldown sweep (``cboe_gex -> ok (11 rows, last 2026-08-03)``), then `run
collectors` died on ``AttributeError: 'NYGamingAdapter' object has no attribute
'fetch_result_status'`` and every one of those rows was deleted the next evening.
2026-08-04: the whole family collected clean and was deleted the same way.

So this is scoped by the property that actually distinguishes them — unrecoverable and
producer-complete — not by "commit more of the tree when things are broken":

  * ONLY the declared chain family (collectors.cboe.CHAIN_FAMILY_SERIES). Not a glob
    over data/, not data/cboe/* — cor1m/skew/vvix/vix_futures re-fetch full history
    every night and must stay behind the collectors gate.
  * Each file must PARSE and its last row must be a real NYSE session. A collectors
    step that died mid-write leaves a torn parquet; a torn file is dropped, not staged.
  * No normalizer runs downstream of these files, which is what made the 08-04 P0
    possible for the page tree. The adapters write the final artifact directly.

Fail-open to an empty list: this runs on a night that is already red, and it must never
be the reason the job gets redder.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _chain_snapshot_files() -> tuple[str, ...]:
    """Repo-relative paths of the delayed-chain family, DERIVED from the collector.

    Deliberately not a second hand-typed list and deliberately not a glob over
    data/cboe/. collectors.cboe.CHAIN_FAMILY_SERIES is the declared inventory (its
    own comment: "Dropping a symbol from collection is an explicit decision — update
    this too"), so deriving keeps one source of truth and lets a newly collected
    symbol inherit the same protection automatically. A glob would instead sweep in
    cor1m/skew/vvix/vix_futures, which re-fetch full history every night and MUST
    stay behind the collectors gate.
    """
    from collectors.cboe import CHAIN_FAMILY_SERIES

    return tuple(f"data/cboe/{s}.parquet" for s in CHAIN_FAMILY_SERIES)


def _readable_session_tipped(path: Path) -> bool:
    """True when *path* parses and its last row lands on a real NYSE session.

    The session check is the torn-write guard with teeth: a truncated parquet usually
    fails to parse, but a snapshot written on a non-session day (or with a corrupted
    index) is the shape that silently poisons every `.iloc[-1]` reader downstream
    (#3721). Refusing to salvage it is strictly better than publishing it.
    """
    try:
        import pandas as pd

        from lib import nyse_calendar

        df = pd.read_parquet(path)
        if df is None or df.empty:
            return False
        return bool(nyse_calendar.is_session(pd.Timestamp(df.index.max()).date()))
    except Exception:  # noqa: BLE001 — unreadable/torn/unexpected shape => not salvageable
        return False


def select_salvageable(root: Path | str = ".") -> list[str]:
    """Repo-relative paths of chain snapshots that exist and are safe to commit."""
    base = Path(root)
    return [rel for rel in _chain_snapshot_files()
            if (base / rel).is_file() and _readable_session_tipped(base / rel)]


def main(argv: list[str] | None = None) -> int:
    root = (argv or sys.argv[1:] or ["."])[0]
    for rel in select_salvageable(root):
        print(rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
