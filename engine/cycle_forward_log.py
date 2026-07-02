"""Shared forward-log writer for the cycle engines — US sector_cycles + country_cycles.

This module owns the `append_forward_log(data, engine)` call that every cycle page's
build script fires after `compute()`. It mirrors the pattern established in
`engine.china_sector_cycles.append_forward_log` (china_sector_cycles.py:313-358)
but is a SHARED implementation so the US sector and country engines do not duplicate
it — the China writer stays as-is (it owns its own column set and path) while this
module handles sector_cycles and country_cycles.

Schema stored in `data/<engine>/forward_log.parquet` (append-only, keep-FIRST per
(date, id)):

  date         str        ISO date of the build ("asOf" from meta)
  id           str        lowercase ticker or basket id (xlk, ewj, b-mag7…)
  kind         str        "sector" | "basket"
  name         str        display name
  phase        str        5-phase wheel: Trough / Recovery / Expansion / Peak / Downturn
  pos          float      0–100 detrended cycle-position oscillator
  osc_slope    float      22-bar oscillator slope
  signal       str|None   "BUY" | "SELL" | None
  timing_state str        cycles.analyze ladder state
  above200d    bool
  rs_63d       float|None 63d RS vs SPY
  proj_next    str|None   projected next turn kind: "peak" | "trough"
  proj_central str|None   projected turn date, YYYY-MM
  proj_lo      str|None   lower edge of the projection band (Q25 half-cycle), YYYY-MM
  proj_hi      str|None   upper edge of the projection band (Q75 half-cycle), YYYY-MM

NEW columns (proj_lo / proj_hi) fix the N-D2-1 gap: the cone-edge data hole that
makes prospective cone-coverage grading impossible without them.

Discipline: append-only, keep-FIRST per (date, id). A past day's stamp is NEVER
rewritten — this is the PIT invariant. The grader re-enforces this on read;
we enforce it on write.

Never raises: every failure is logged and returns 0.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

# Engines this module handles (path prefix under data/<engine>/)
_ENGINES = frozenset({"sector_cycles", "country_cycles"})


def _extract_rows(data: dict) -> list[dict]:
    """Walk the compute() output and extract one row per series (sector + basket)."""
    asof = (data.get("meta") or {}).get("asOf")
    rows: list[dict] = []
    for rec in (data.get("sectors", []) + data.get("baskets", [])):
        nw = rec.get("now") or {}
        pr = rec.get("proj") or {}
        rows.append({
            "date": asof,
            "id": rec.get("id"),
            "kind": rec.get("kind"),
            "name": rec.get("name"),
            "phase": nw.get("phase"),
            "pos": nw.get("pos"),
            "osc_slope": nw.get("osc_slope"),
            "signal": nw.get("signal"),
            "timing_state": nw.get("timing_state"),
            "above200d": nw.get("above200d"),
            "rs_63d": nw.get("rs_63d"),
            # projection band — nextTurn direction + the three date edges
            "proj_next": pr.get("nextTurn"),
            "proj_central": pr.get("central"),   # YYYY-MM string
            "proj_lo": pr.get("low"),             # Q25 edge  — "low" key in _project_next
            "proj_hi": pr.get("high"),            # Q75 edge  — "high" key in _project_next
        })
    return rows


def append_forward_log(data: dict | None, engine: str) -> int:
    """Append today's per-series cycle signal to an append-only, point-in-time log
    (`data/<engine>/forward_log.parquet`), keyed by (date, id), keep-FIRST-per-date
    so a past day's stamped signal is never rewritten.

    Parameters
    ----------
    data    : the dict returned by `sector_cycles.compute()` or `country_cycles.compute()`
    engine  : "sector_cycles" or "country_cycles"

    Returns the number of new rows appended (0 on any error or empty input).
    Never raises.
    """
    if engine not in _ENGINES:
        log.warning("cycle_forward_log: unknown engine %r — skipped", engine)
        return 0
    try:
        return _append(data, engine)
    except Exception as e:  # noqa: BLE001
        log.warning("cycle_forward_log[%s]: append failed: %s", engine, e)
        return 0


def _append(data: dict | None, engine: str) -> int:
    if not data:
        return 0
    rows = _extract_rows(data)
    asof = (data.get("meta") or {}).get("asOf")
    if not rows or not asof:
        return 0
    # filter out rows with no id (safety)
    rows = [r for r in rows if r.get("id")]
    if not rows:
        return 0

    new = pd.DataFrame(rows)

    try:
        from lib import config
        p = config.data_dir() / engine / "forward_log.parquet"
    except Exception as e:  # noqa: BLE001
        log.warning("cycle_forward_log[%s]: cannot resolve data dir: %s", engine, e)
        return 0

    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        try:
            prior = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("cycle_forward_log[%s]: cannot read prior log (%s) — starting fresh",
                        engine, e)
            prior = pd.DataFrame()
        if not prior.empty:
            combined = pd.concat([prior, new], ignore_index=True)
        else:
            combined = new
    else:
        combined = new

    # keep-FIRST invariant: a stamp for (date, id) that already exists in the prior log
    # is NEVER overwritten — the first write wins.
    combined = combined.drop_duplicates(subset=["date", "id"], keep="first")
    combined.to_parquet(p, index=False)
    return len(new)
