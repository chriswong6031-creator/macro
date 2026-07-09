"""Pick Lab fires/grades JSONL I/O (spec §4, PL-R2/R4/R6/R10).

Entry books:
  data/pick_lab/fires.jsonl    — fires ledger
  data/pick_lab/grades.jsonl   — grades ledger

Long-hold books (horizon_role=hold_thesis) — SEPARATE per PL-R6:
  data/pick_lab/lh_fires.jsonl
  data/pick_lab/lh_grades.jsonl

All rows carry authority="display_only".  Keep-first dedup semantics:
  fires  keyed on (engine_id, ticker, fire_date)
  grades keyed on (engine_id, ticker, fire_date, horizon)

Refire lockout helper: is_open(engine_id, ticker, trading_dates, fires, lockout)
returns True when a ticker already has a fire for this engine within lockout sessions.

Profile support (additive):
  append_fires / load_fires / append_grades / load_grades accept an optional
  'profile' keyword argument (engine.pick_lab.profile.MarketProfile).  When
  supplied, the profile's path fields are used instead of the module-level
  constants.  Omitting profile (or passing None) preserves exact US behaviour.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ paths -----

PICK_LAB_DIR = Path("data") / "pick_lab"
FIRES_PATH = PICK_LAB_DIR / "fires.jsonl"
GRADES_PATH = PICK_LAB_DIR / "grades.jsonl"
LH_FIRES_PATH = PICK_LAB_DIR / "lh_fires.jsonl"
LH_GRADES_PATH = PICK_LAB_DIR / "lh_grades.jsonl"

_WRITE_LOCK = threading.Lock()

# ------------------------------------------------------------------ keys ------

FIRE_KEY = ("engine_id", "ticker", "fire_date")
GRADE_KEY = ("engine_id", "ticker", "fire_date", "horizon")

# ------------------------------------------------------------------ schema ----

# Required fields per spec §4 — enforced on append.
_FIRE_REQUIRED = {
    "engine_id", "ticker", "fire_date", "authority",
}
_GRADE_REQUIRED = {
    "engine_id", "ticker", "fire_date", "horizon", "authority",
}

# ------------------------------------------------------------------ helpers ---


def _json_default(o: Any) -> str:
    if isinstance(o, (datetime,)):
        return o.isoformat()
    item = getattr(o, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return str(o)


def load_jsonl(path: str | Path) -> list[dict]:
    """Load an append-only JSONL file; absent-file-safe (returns []).

    Tolerates torn final lines (parse errors on individual lines are skipped).
    """
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue  # tolerate torn final line
    except OSError:
        return []
    return rows


def keep_first(
    rows: list[dict],
    key_fields: tuple[str, ...],
) -> list[dict]:
    """Return rows keeping only the FIRST occurrence per unique key.

    Forward-ledger keep-first semantics (PL-R10 / PL-R2).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        k = tuple(row.get(f) for f in key_fields)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    """Atomically overwrite path with rows (tempfile + os.replace).

    All rows must carry authority='display_only'.
    """
    for i, row in enumerate(rows):
        if row.get("authority") != "display_only":
            raise ValueError(
                f"write_jsonl: row[{i}] must carry authority='display_only'; "
                f"got {row.get('authority')!r}"
            )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp_", suffix=".jsonl")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=_json_default) + "\n")
            os.replace(tmp, str(p))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _append_line(path: Path, row: dict) -> None:
    """Append one JSONL row (in-place; no tempfile needed for single-row append)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=_json_default) + "\n")


# ------------------------------------------------------------------ fires -----


def _validate_fire(row: dict) -> None:
    missing = _FIRE_REQUIRED - set(row)
    if missing:
        raise ValueError(f"fire row missing required fields: {missing}")
    if row["authority"] != "display_only":
        raise ValueError(
            f"fire row must carry authority='display_only'; got {row['authority']!r}"
        )


def append_fires(
    fires: list[dict],
    *,
    hold_thesis: bool = False,
    profile=None,
) -> int:
    """Append fire rows; enforce keep-first dedup and authority.

    Parameters
    ----------
    fires       : list of fire dicts per spec §4.
    hold_thesis : if True, writes to lh_fires.jsonl (PL-R6 firewall).
    profile     : optional MarketProfile; when supplied, uses profile path fields.
                  Defaults to US_PROFILE paths (no behaviour change for US callers).

    Returns number of rows actually written (deduped against existing).
    """
    if not fires:
        return 0

    if profile is not None:
        path = profile.lh_fires_path if hold_thesis else profile.fires_path
    else:
        path = LH_FIRES_PATH if hold_thesis else FIRES_PATH

    # Validate all rows before writing anything
    for row in fires:
        _validate_fire(row)
        row["authority"] = "display_only"  # enforce

    # Load existing, compute existing keys
    existing = load_jsonl(path)
    existing_keys: set[tuple] = {
        tuple(r.get(f) for f in FIRE_KEY) for r in existing
    }

    written = 0
    for row in fires:
        k = tuple(row.get(f) for f in FIRE_KEY)
        if k in existing_keys:
            log.debug(
                "append_fires: skip duplicate %s/%s/%s",
                row.get("engine_id"), row.get("ticker"), row.get("fire_date"),
            )
            continue
        existing_keys.add(k)
        _append_line(path, row)
        written += 1

    log.info(
        "append_fires: wrote %d/%d rows to %s",
        written, len(fires), path,
    )
    return written


def load_fires(*, hold_thesis: bool = False, profile=None) -> list[dict]:
    """Load fires (keep-first dedup applied).

    profile : optional MarketProfile; when supplied, uses profile path fields.
    """
    if profile is not None:
        path = profile.lh_fires_path if hold_thesis else profile.fires_path
    else:
        path = LH_FIRES_PATH if hold_thesis else FIRES_PATH
    return keep_first(load_jsonl(path), FIRE_KEY)


# ------------------------------------------------------------------ grades ----


def _validate_grade(row: dict) -> None:
    missing = _GRADE_REQUIRED - set(row)
    if missing:
        raise ValueError(f"grade row missing required fields: {missing}")
    if row["authority"] != "display_only":
        raise ValueError(
            f"grade row must carry authority='display_only'; got {row['authority']!r}"
        )


def append_grades(
    grades: list[dict],
    *,
    hold_thesis: bool = False,
    profile=None,
) -> int:
    """Append grade rows; enforce keep-first dedup and authority.

    Parameters
    ----------
    grades      : list of grade dicts per spec §4.
    hold_thesis : if True, writes to lh_grades.jsonl (PL-R6 firewall).
    profile     : optional MarketProfile; when supplied, uses profile path fields.

    Returns number of rows actually written.
    """
    if not grades:
        return 0

    if profile is not None:
        path = profile.lh_grades_path if hold_thesis else profile.grades_path
    else:
        path = LH_GRADES_PATH if hold_thesis else GRADES_PATH

    for row in grades:
        _validate_grade(row)
        row["authority"] = "display_only"

    existing = load_jsonl(path)
    existing_keys: set[tuple] = {
        tuple(r.get(f) for f in GRADE_KEY) for r in existing
    }

    written = 0
    for row in grades:
        k = tuple(row.get(f) for f in GRADE_KEY)
        if k in existing_keys:
            log.debug(
                "append_grades: skip duplicate %s/%s/%s/h=%s",
                row.get("engine_id"), row.get("ticker"),
                row.get("fire_date"), row.get("horizon"),
            )
            continue
        existing_keys.add(k)
        _append_line(path, row)
        written += 1

    log.info(
        "append_grades: wrote %d/%d rows to %s",
        written, len(grades), path,
    )
    return written


def load_grades(*, hold_thesis: bool = False, profile=None) -> list[dict]:
    """Load grades (keep-first dedup applied).

    profile : optional MarketProfile; when supplied, uses profile path fields.
    """
    if profile is not None:
        path = profile.lh_grades_path if hold_thesis else profile.grades_path
    else:
        path = LH_GRADES_PATH if hold_thesis else GRADES_PATH
    return keep_first(load_jsonl(path), GRADE_KEY)


# ---------------------------------------------------------------- refire ------


def is_open(
    engine_id: str,
    ticker: str,
    trading_dates: pd.DatetimeIndex,
    fires: list[dict],
    lockout_sessions: int,
) -> bool:
    """Return True when ticker has an open fire in this book.

    A ticker is 'open' if its last fire_date for engine_id is within
    lockout_sessions trading sessions ago (per PL-R4 no-refire-while-open rule).

    Parameters
    ----------
    engine_id        : Book identifier.
    ticker           : Ticker to check.
    trading_dates    : Full trading calendar as DatetimeIndex (used to count sessions).
    fires            : Existing fire rows (already keep-first deduped).
    lockout_sessions : Number of sessions to lock (21 entry; 63 LH).
    """
    # Filter to fires for this (engine_id, ticker)
    relevant = [
        r for r in fires
        if r.get("engine_id") == engine_id and r.get("ticker") == ticker
    ]
    if not relevant:
        return False

    last_fire_date = max(
        pd.Timestamp(r["fire_date"]) for r in relevant
    )

    # Count sessions between last_fire_date and last date in trading_dates
    if len(trading_dates) == 0:
        return False

    current_date = trading_dates[-1]
    # Positions in the sorted trading calendar
    dates_sorted = trading_dates.sort_values()
    try:
        last_fire_pos = dates_sorted.searchsorted(last_fire_date, side="left")
        current_pos = dates_sorted.searchsorted(current_date, side="left")
    except Exception:  # noqa: BLE001
        return False

    sessions_elapsed = current_pos - last_fire_pos
    return sessions_elapsed < lockout_sessions
