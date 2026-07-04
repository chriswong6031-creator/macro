"""engine.neuralweb.lagging — Lagging-signal detector (Neural Web W3 PR3).

HONESTY HEADER
--------------
The outputs of this module are ESTIMATES WITH UNCERTAINTY, never findings.

Display-first law: zero behavior-changing consumers may read
data/neuralweb/lagging_signals.json.  No alert severity, board ordering,
or allocation weight may be set from this artifact.

PURPOSE
-------
Three per-fire flags over recent fires (trailing 63 calendar days of spine-index
rows, entity scope only):

  1. fired_in_hostile_regime
     Join fire as_of → data/regime/regime_history.parquet.  Hostile = row whose
     'quad' column is Q3 (Stagflation) or Q4 (Growth-scare/Deflation), OR whose
     'recession' flag is True, OR whose 'inflation_shock' flag is True.

     REGIME_HISTORY COLUMN MAPPING:
       'quad'            — Q1 (Goldilocks) / Q2 (Reflation) / Q3 (Stagflation) /
                           Q4 (Growth-scare/Deflation).  Source: engine/regime.py
                           QUAD_NAMES mapping.  Hostile set: {'Q3', 'Q4'}.
       'recession'       — bool; extra hostile flag (Q4 + credit confirmation).
       'inflation_shock' — bool; extra hostile flag (Q3 + top-decile inflation).
     Any of the three conditions marks the fire hostile.

     Fail-open: missing regime store → null for the date; flag set to False with
     a gap note.

  2. fired_breadth_unconfirmed
     Join as_of → data/breadth/breadth.parquet column 'pct_above_50'.
     Unconfirmed = pct_above_50 on the fire date is below its own trailing-63d
     median over the [as_of - 63 calendar days, as_of) window (strict lookback,
     no lookahead).

     RATIONALE: the 63d median is a simple, single-parameter threshold calibrated
     to the same window as the fire-lookback.  No tuning was applied; the median
     is the honest mid-point of recent breadth history on the fire date.

     Fail-open: missing breadth store → flag set to False with a gap note.

  3. repeat_fire (PROXY FOR EXTENSION — HONESTLY NAMED)
     Fire whose SAME (engine, symbol) pair fired >= 3 times in the prior 21
     calendar days within the trailing-63d window.  High repeat-fire rate is
     a PROXY for chasing an extended move.  This metric is named 'repeat_fire'
     throughout the artifact — NOT 'extended' — because we lack per-ticker price
     data in the spine index to compute an actual extension metric.  The artifact
     and notes field document this limitation.  Once per-ticker context lands,
     this proxy can be replaced with a genuine extension metric.

OUTPUT ARTIFACT: data/neuralweb/lagging_signals.json
  {
    "by_family": {
      "<engine>": {
        "n_recent_fires": int,
        "n_hostile_regime": int,
        "n_breadth_unconfirmed": int,
        "n_repeat_fire": int,
        "flagged": [
          {
            "engine": str,
            "symbol": str,
            "as_of": "YYYY-MM-DD",
            "flags": ["hostile_regime"|"breadth_unconfirmed"|"repeat_fire", ...]
          },
          ...  # up to 50 most recent flagged fires per family
        ]
      }
    },
    "gaps": [...],   # fail-open gap notes
    "produced_at": "...",
    # + five sibling envelope keys
  }

USAGE
-----
  from engine.neuralweb.lagging import build_lagging, write_lagging
  d = build_lagging(root)
  write_lagging(root)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

__all__ = [
    "FIRE_LOOKBACK_DAYS",
    "REPEAT_FIRE_WINDOW_DAYS",
    "REPEAT_FIRE_MIN_COUNT",
    "HOSTILE_QUAD_SET",
    "build_lagging",
    "write_lagging",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Trailing calendar days of spine-index rows to analyse.
FIRE_LOOKBACK_DAYS: int = 63

#: Window for repeat-fire proxy (calendar days prior to each fire).
REPEAT_FIRE_WINDOW_DAYS: int = 21

#: Minimum prior fires in the REPEAT_FIRE_WINDOW to flag repeat_fire.
REPEAT_FIRE_MIN_COUNT: int = 3

#: Hostile quad values in regime_history 'quad' column.
#: Q3=Stagflation, Q4=Growth-scare/Deflation.  Documented in engine/regime.py.
HOSTILE_QUAD_SET: frozenset[str] = frozenset({"Q3", "Q4"})

#: Max flagged fires per family in the output (most-recent first).
MAX_FLAGGED_PER_FAMILY: int = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _data_dir(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root) / "data"
    from lib import config  # noqa: PLC0415
    return config.data_dir()


def _load_index(root: Path | str | None) -> pd.DataFrame:
    from engine.neuralweb.query import load_index  # noqa: PLC0415
    return load_index(root)


def _load_regime_history(root: Path | str | None) -> tuple[pd.DataFrame, list[str]]:
    """Load data/regime/regime_history.parquet.  Fail-open with gap notes."""
    gaps: list[str] = []
    p = _data_dir(root) / "regime" / "regime_history.parquet"
    if not p.exists():
        gaps.append("regime_history: data/regime/regime_history.parquet absent — hostile_regime flags will be False")
        return pd.DataFrame(), gaps
    try:
        df = pd.read_parquet(p)
        return df, gaps
    except Exception as e:  # noqa: BLE001
        gaps.append(f"regime_history: read failed ({e}) — hostile_regime flags will be False")
        return pd.DataFrame(), gaps


def _load_breadth(root: Path | str | None) -> tuple[pd.DataFrame, list[str]]:
    """Load data/breadth/breadth.parquet.  Fail-open with gap notes."""
    gaps: list[str] = []
    p = _data_dir(root) / "breadth" / "breadth.parquet"
    if not p.exists():
        gaps.append("breadth: data/breadth/breadth.parquet absent — breadth_unconfirmed flags will be False")
        return pd.DataFrame(), gaps
    try:
        df = pd.read_parquet(p)
        return df, gaps
    except Exception as e:  # noqa: BLE001
        gaps.append(f"breadth: read failed ({e}) — breadth_unconfirmed flags will be False")
        return pd.DataFrame(), gaps


def _hostile_lookup(
    regime_df: pd.DataFrame,
) -> dict[str, bool]:
    """Build a date-string → hostile_bool lookup from regime_history.

    Hostile = quad in HOSTILE_QUAD_SET OR recession==True OR inflation_shock==True.
    """
    if regime_df.empty:
        return {}
    lookup: dict[str, bool] = {}
    # regime_history has a DatetimeIndex with no name
    idx = regime_df.index
    quad_col = regime_df.get("quad") if "quad" in regime_df.columns else None
    rec_col = regime_df.get("recession") if "recession" in regime_df.columns else None
    shock_col = regime_df.get("inflation_shock") if "inflation_shock" in regime_df.columns else None

    for i in range(len(regime_df)):
        try:
            date_str = str(idx[i])[:10]  # "YYYY-MM-DD"
        except Exception:  # noqa: BLE001
            continue
        hostile = False
        if quad_col is not None:
            q = quad_col.iloc[i]
            if isinstance(q, str) and q in HOSTILE_QUAD_SET:
                hostile = True
        if not hostile and rec_col is not None:
            r = rec_col.iloc[i]
            if r is True or r == 1 or (isinstance(r, (float, int)) and not np.isnan(r) and bool(r)):
                hostile = True
        if not hostile and shock_col is not None:
            s = shock_col.iloc[i]
            if s is True or s == 1 or (isinstance(s, (float, int)) and not np.isnan(s) and bool(s)):
                hostile = True
        lookup[date_str] = hostile
    return lookup


def _breadth_lookup(
    breadth_df: pd.DataFrame,
    fire_dates: list[str],
) -> dict[str, bool]:
    """Build a date-string → breadth_unconfirmed_bool lookup.

    unconfirmed = pct_above_50 on the fire date is below its trailing-63d median
    over [fire_date - 63 days, fire_date) — strict lookback window, no lookahead.

    Returns False (confirmed) for dates without breadth data (fail-open).
    """
    if breadth_df.empty or "pct_above_50" not in breadth_df.columns:
        return {d: False for d in fire_dates}

    pa50 = breadth_df["pct_above_50"].dropna()
    if pa50.empty:
        return {d: False for d in fire_dates}

    # Build a string-keyed series for fast lookup
    pa50_str: dict[str, float] = {}
    for ts, val in pa50.items():
        try:
            pa50_str[str(ts)[:10]] = float(val)
        except Exception:  # noqa: BLE001
            pass

    lookup: dict[str, bool] = {}
    for fire_date_str in fire_dates:
        val = pa50_str.get(fire_date_str)
        if val is None:
            lookup[fire_date_str] = False  # fail-open
            continue
        # Trailing-63d window strictly before fire_date
        try:
            fd = date.fromisoformat(fire_date_str)
            cutoff = (fd - pd.Timedelta(days=FIRE_LOOKBACK_DAYS)).isoformat()
        except Exception:  # noqa: BLE001
            lookup[fire_date_str] = False
            continue
        # Collect pct_above_50 values in [cutoff, fire_date) — strictly before
        window_vals = [
            v for d_str, v in pa50_str.items()
            if cutoff <= d_str < fire_date_str
        ]
        if not window_vals:
            lookup[fire_date_str] = False  # not enough history — fail-open
            continue
        median_val = float(np.median(window_vals))
        lookup[fire_date_str] = val < median_val
    return lookup


# ---------------------------------------------------------------------------
# Build function
# ---------------------------------------------------------------------------

def build_lagging(root: Path | str | None = None) -> dict:
    """Build the lagging_signals diagnostic payload.

    Returns the JSON-serialisable dict (without envelope keys).
    """
    gaps: list[str] = []
    today_str = date.today().isoformat()

    # Load spine index → filter to entity scope, trailing 63 calendar days
    index_df = _load_index(root)
    if index_df.empty:
        gaps.append("spine_index: empty — no recent fires to analyse")
        return {
            "by_family": {},
            "gaps": gaps,
            "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    mask_entity = index_df["scope_type"].astype(str) == "entity"
    entity_df = index_df[mask_entity].copy()

    # Trailing-63d filter by as_of calendar date
    try:
        cutoff_dt = date.fromisoformat(today_str) - pd.Timedelta(days=FIRE_LOOKBACK_DAYS)
        cutoff_str = cutoff_dt.isoformat()
        recent_df = entity_df[entity_df["as_of"].astype(str) >= cutoff_str].copy()
    except Exception as e:  # noqa: BLE001
        gaps.append(f"date filter failed ({e}) — using all entity rows")
        recent_df = entity_df.copy()

    if recent_df.empty:
        gaps.append(f"spine_index: no entity rows in trailing {FIRE_LOOKBACK_DAYS} calendar days")
        return {
            "by_family": {},
            "gaps": gaps,
            "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Load regime and breadth stores (fail-open)
    regime_df, regime_gaps = _load_regime_history(root)
    gaps.extend(regime_gaps)
    breadth_df, breadth_gaps = _load_breadth(root)
    gaps.extend(breadth_gaps)

    # Build lookup tables
    hostile_map = _hostile_lookup(regime_df)

    # Breadth lookup for fire dates present in recent_df
    fire_dates_all = recent_df["as_of"].astype(str).unique().tolist()
    breadth_unconf_map = _breadth_lookup(breadth_df, fire_dates_all)

    # Build repeat-fire lookup: for each (engine, symbol, as_of), count prior fires
    # in the 21-day window.  A fire is "repeat" if count >= REPEAT_FIRE_MIN_COUNT.
    # We use the FULL trailing-63d window (recent_df) as context.
    # For each row, count how many times (engine, symbol) appeared in
    # [as_of - 21d, as_of) within recent_df.
    recent_df["as_of_str"] = recent_df["as_of"].astype(str)
    recent_df["engine_str"] = recent_df["engine"].astype(str)
    recent_df["symbol_str"] = recent_df["symbol"].astype(str)

    # Build an index of (engine, symbol) → sorted list of as_of dates
    from collections import defaultdict  # noqa: PLC0415
    pair_dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for _, row in recent_df.iterrows():
        pair_dates[(row["engine_str"], row["symbol_str"])].append(row["as_of_str"])
    # Sort each list
    for k in pair_dates:
        pair_dates[k] = sorted(set(pair_dates[k]))  # unique dates sorted

    def _is_repeat(engine_v: str, symbol_v: str, as_of_v: str) -> bool:
        dates_for_pair = pair_dates.get((engine_v, symbol_v), [])
        if not dates_for_pair:
            return False
        try:
            fire_dt = date.fromisoformat(as_of_v)
            window_start = (fire_dt - pd.Timedelta(days=REPEAT_FIRE_WINDOW_DAYS)).isoformat()
        except Exception:  # noqa: BLE001
            return False
        prior_count = sum(
            1 for d_str in dates_for_pair
            if window_start <= d_str < as_of_v
        )
        return prior_count >= REPEAT_FIRE_MIN_COUNT

    # Build per-fire flag records
    fire_records: list[dict[str, Any]] = []
    for _, row in recent_df.iterrows():
        eng = str(row["engine_str"])
        sym = str(row["symbol_str"])
        asof = str(row["as_of_str"])

        flags: list[str] = []
        if hostile_map.get(asof, False):
            flags.append("hostile_regime")
        if breadth_unconf_map.get(asof, False):
            flags.append("breadth_unconfirmed")
        if _is_repeat(eng, sym, asof):
            flags.append("repeat_fire")

        fire_records.append({
            "engine": eng,
            "symbol": sym,
            "as_of": asof,
            "flags": flags,
        })

    # Aggregate by family (engine)
    by_family: dict[str, Any] = {}
    engines = sorted(recent_df["engine_str"].unique().tolist())
    for eng in engines:
        eng_fires = [r for r in fire_records if r["engine"] == eng]
        n_recent = len(eng_fires)
        n_hostile = sum(1 for r in eng_fires if "hostile_regime" in r["flags"])
        n_unconf = sum(1 for r in eng_fires if "breadth_unconfirmed" in r["flags"])
        n_repeat = sum(1 for r in eng_fires if "repeat_fire" in r["flags"])

        # Flagged fires: any flag, sorted most-recent first, capped at MAX_FLAGGED
        flagged = sorted(
            [r for r in eng_fires if r["flags"]],
            key=lambda r: r["as_of"],
            reverse=True,
        )[:MAX_FLAGGED_PER_FAMILY]

        by_family[eng] = {
            "n_recent_fires": n_recent,
            "n_hostile_regime": n_hostile,
            "n_breadth_unconfirmed": n_unconf,
            "n_repeat_fire": n_repeat,
            "repeat_fire_proxy_note": (
                "repeat_fire proxies extension (>=3 prior fires in 21d for same "
                "(engine,symbol)) until per-ticker price context lands; "
                "NOT a genuine extension metric"
            ),
            "flagged": flagged,
        }

    return {
        "by_family": by_family,
        "gaps": gaps,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Write function (idempotent)
# ---------------------------------------------------------------------------

def write_lagging(root: Path | str | None = None) -> dict:
    """Build lagging_signals payload and write to data/neuralweb/lagging_signals.json.

    Stamps envelope as sibling keys (artifact_id='lagging-signals').
    Returns stats dict.
    """
    payload = build_lagging(root)

    if root is not None:
        out_dir = Path(root) / "data" / "neuralweb"
    else:
        from lib import config  # noqa: PLC0415
        out_dir = config.data_dir() / "neuralweb"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lagging_signals.json"

    # Stamp with envelope (sibling keys)
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        payload = stamp(payload, artifact_id="lagging-signals")
    except Exception as e:  # noqa: BLE001
        log.warning("lagging.write_lagging: envelope stamp failed: %s", e)

    import json  # noqa: PLC0415
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_families = len(payload.get("by_family", {}))
    total_fires = sum(
        v.get("n_recent_fires", 0)
        for v in payload.get("by_family", {}).values()
    )
    log.info(
        "lagging.write_lagging: wrote %d families / %d recent fires to %s",
        n_families, total_fires, out_path,
    )
    return {
        "output_path": str(out_path),
        "n_families": n_families,
        "total_recent_fires": total_fires,
        "gaps": payload.get("gaps", []),
    }
