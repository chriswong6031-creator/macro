"""PIT daily-append CN regime store (SA-W2, SA-R7).

Appends ONE row per trading date to data/china_regime/regime_daily.parquet —
a permanent, append-only, point-in-time snapshot of the CN regime as it was
computed on the night it was written.

UNLIKE data/china_regime/regime_history.parquet (which is fully overwritten each
run by china_run.py), this store is keep-FIRST per date: once a date's row is
written, a re-run on the same night never overwrites it.  This makes it safe to
stamp own_market_regime on CN board rows going FORWARD from the store's birth date
(2026-07-12+) without any risk of non-PIT backfill.

Schema (schema_version=1):
    date              — YYYY-MM-DD string (the regime's as-of date; dedup key)
    quad              — 'Q1'/'Q2'/'Q3'/'Q4' | null
    quad_name         — 'Goldilocks'/'Reflation'/'Stagflation'/'Growth-scare' | null
    liquidity         — 'expanding'/'contracting'/'neutral'/'unknown'
    cycle             — 'early'/'mid'/'late'/'unknown'
    growth_score      — float
    inflation_score   — float
    regime_confidence — float
    schema_version    — int (always 1 for this version)
    written_at        — ISO UTC timestamp when this row was appended

FAIL-CLOSED: all writes are gated on CN_LANE=='asia' (the environment variable
set by asia-close.yml).  If CN_LANE is absent or not 'asia', append() refuses and
logs a warning — the store never grows from a non-production lane.

NEVER-RAISE: every public function returns a falsy result on error, never raises,
so a failure here can never suppress the build that calls it.

Freshness stamp: data/standout_audit/cn_audit_state.json carries a
regime_store_last_date field (updated after every successful append).

Usage (from scripts/build_china_library.py after china_run.py has produced its
regime artifact):

    import os
    from engine import china_regime_store
    if os.environ.get('CN_LANE') == 'asia':
        china_regime_store.append(asof=today_str)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_STORE_PATH = ("data", "china_regime", "regime_daily.parquet")
_STATE_PATH = ("data", "standout_audit", "cn_audit_state.json")
_SCHEMA_VERSION = 1

# Columns sourced from regime_history.parquet (all produced by china_run.py).
# These are the fields the nightly computation already produces; we snapshot
# today's latest row and keep it permanently.
_REGIME_COLS = (
    "quad",
    "quad_name",
    "liquidity",
    "cycle",
    "growth_score",
    "inflation_score",
    "regime_confidence",
)


def _store_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r.joinpath(*_STORE_PATH)


def _state_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r.joinpath(*_STATE_PATH)


def _regime_history_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    return r / "data" / "china_regime" / "regime_history.parquet"


def _read_today_regime(asof: str, root: Path | None = None) -> dict | None:
    """Read the row for ``asof`` from regime_history.parquet (the overwrite store).

    Returns a dict of _REGIME_COLS keys, or None if the store is absent or the
    date is not covered.  Never raises.
    """
    p = _regime_history_path(root)
    if not p.exists():
        log.warning("china_regime_store: regime_history.parquet not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("china_regime_store: cannot read regime_history.parquet: %s", exc)
        return None
    # regime_history has a DatetimeIndex (the date is the index)
    target = pd.Timestamp(asof)
    if target not in df.index:
        # Try the last available date if it's the same calendar date (timezone shift)
        closest = df.index[df.index.date == target.date()] if hasattr(df.index[0], 'date') else []
        if len(closest) == 0:
            log.warning("china_regime_store: asof=%s not in regime_history (last=%s)",
                        asof, df.index[-1] if len(df) else "empty")
            return None
        target = closest[-1]
    row = df.loc[target]
    result: dict = {}
    for col in _REGIME_COLS:
        val = row.get(col) if hasattr(row, 'get') else (row[col] if col in row.index else None)
        # Convert numpy/pandas scalar to Python native
        if pd.isna(val) if not isinstance(val, str) else False:
            result[col] = None
        elif hasattr(val, 'item'):
            result[col] = val.item()
        else:
            result[col] = val
    return result


def append(asof: str, root: Path | None = None) -> bool:
    """Append today's CN regime row to the PIT daily store (keep-FIRST per date).

    FAIL-CLOSED: returns False immediately if CN_LANE != 'asia'.  This is
    tested in tests/test_china_regime_store.py — changing this gate requires
    updating that test.

    Returns True when a row was successfully written (new or already present),
    False on any failure or non-asia lane.  Never raises.
    """
    lane = os.environ.get("CN_LANE", "")
    if lane != "asia":
        log.warning(
            "china_regime_store.append: refusing write — CN_LANE=%r (expected 'asia'). "
            "This store is fail-closed: only the asia lane may persist CN regime rows.",
            lane,
        )
        return False
    try:
        regime_row = _read_today_regime(asof, root)
        if regime_row is None:
            log.warning("china_regime_store: cannot read regime for %s — skip append", asof)
            return False

        p = _store_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)

        written_at = datetime.now(timezone.utc).isoformat()
        new_row: dict = {
            "date": str(asof),
            "schema_version": _SCHEMA_VERSION,
            "written_at": written_at,
            **regime_row,
        }
        new_df = pd.DataFrame([new_row])

        if p.exists():
            try:
                prior = pd.read_parquet(p)
            except Exception as exc:  # noqa: BLE001
                log.warning("china_regime_store: cannot read prior store: %s — starting fresh", exc)
                prior = pd.DataFrame()

            if not prior.empty and str(asof) in prior["date"].astype(str).values:
                # Keep-first: date already present — do NOT overwrite
                log.info("china_regime_store: date %s already present — keep-first, skip write", asof)
                _update_state(asof, root)
                return True

            # Union schema: preserve any extra columns from prior (defensive)
            all_cols = list(dict.fromkeys([*new_df.columns, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=all_cols), new_df.reindex(columns=all_cols)],
                ignore_index=True,
            )
        else:
            combined = new_df

        combined.to_parquet(p, index=False)
        log.info("china_regime_store: appended %s — store now %d rows; quad=%s cycle=%s",
                 asof, len(combined), regime_row.get("quad"), regime_row.get("cycle"))
        _update_state(asof, root)
        return True

    except Exception as exc:  # noqa: BLE001
        log.warning("china_regime_store.append failed for %s: %s", asof, exc)
        return False


def _update_state(asof: str, root: Path | None = None) -> None:
    """Update data/standout_audit/cn_audit_state.json with the latest regime date.

    Never raises.  Creates the state file if absent.  Only updates
    regime_store_last_date — other fields are preserved.
    """
    try:
        p = _state_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        state: dict = {}
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                state = {}
        state["regime_store_last_date"] = str(asof)
        state["regime_store_updated_at"] = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("china_regime_store._update_state failed: %s", exc)


def get_regime_for_date(asof: str, root: Path | None = None) -> dict | None:
    """Look up the PIT CN regime for ``asof`` from the daily store.

    Returns a dict with keys matching _REGIME_COLS, or None when:
    - the store is absent (pre-store dates → keep null + 'us_proxy' stratum)
    - the date is not covered

    This is the ONLY source for own_market_regime stamps on CN board rows.
    Callers must NOT fall back to regime_history.parquet — that would break the
    PIT guarantee (SA-R7).
    """
    p = _store_path(root)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        mask = df["date"].astype(str) == str(asof)
        if not mask.any():
            return None
        row = df[mask].iloc[0]
        result: dict = {}
        for col in _REGIME_COLS:
            val = row.get(col) if hasattr(row, 'get') else None
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                result[col] = None
            elif hasattr(val, 'item'):
                result[col] = val.item()
            else:
                result[col] = val
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("china_regime_store.get_regime_for_date failed for %s: %s", asof, exc)
        return None


def store_birth_date(root: Path | None = None) -> str | None:
    """Return the earliest date in the PIT store, or None if the store is absent.

    Used by attribution to determine the seam date: rows before this date are
    stamped with stratum='us_proxy' and never pooled with own-market cells.
    """
    p = _store_path(root)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        dates = df["date"].astype(str)
        return str(sorted(dates)[0])
    except Exception as exc:  # noqa: BLE001
        log.warning("china_regime_store.store_birth_date failed: %s", exc)
        return None
