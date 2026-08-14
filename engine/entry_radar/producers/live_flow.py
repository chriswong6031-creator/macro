"""engine/entry_radar/producers/live_flow.py — the 30-min intraday flow fastpath.

``site/live/flow_pulse.json`` (Track C row #13) — the highest-cadence artifact
Radar can read as a file.  Written by
``scripts/build_intraday_flow.py --mode fastpath`` on the 30-minute
``intraday-fastpath.yml`` lane, over the ~360-name
``engine.options_universe.gex_symbols()`` display universe.

AN EPHEMERAL PRODUCER (contract §5)
------------------------------------
The fastpath lane writes **zero** ``data/`` by design (HOUSE-U5): this file is
overwritten every 30 minutes and no vintage is archived.  Its history is
therefore unreconstructible after the fact, which is exactly why every
nomination it yields is spooled at ingestion (``engine/entry_radar/spool.py``)
and why anything built on it is live-forward only (§11 Q4).

ARTIFACT SHAPE (verified from the writer, ``build_intraday_flow.py``:1264-1280):
root ``{schema:"flow_pulse.v1", as_of, as_of_ms, mode, stale, n_tickers,
direction_note, tickers}`` where ``tickers`` is a **list** of per-ticker rows:
``{ticker, bars_today, vwap, vol_durability, higher_lows, cum_vol, last_close,
last_high, last_low, rvol_tod, session_high, session_low, bars_above_vwap}``.

THE PRODUCER'S OWN ``stale`` FLAG IS HONOURED
----------------------------------------------
The artifact self-declares staleness.  When ``stale`` is truthy the read grades
``stale`` regardless of age arithmetic — the producer knows something about its
own inputs that a timestamp does not, and overriding it with a fresh mtime
would be Radar claiming confidence the producer disclaimed.  Also note the
``flow_pulse_lastgood.json`` sibling: a lastgood copy is a RECOVERY artifact,
so reading it must never present as ``ok``.

WHAT IS EMITTED
---------------
Attention facts only — ``rvol_tod`` (time-of-day-adjusted relative volume) and
the structural observations the fastpath already computed (``higher_lows``,
``bars_above_vwap``).  These ADMIT; they never score (§9), and Radar computes
no oscillator here: the higher-lows flag is the producer's own field, read
verbatim, not a Radar turn detector.  Turn detection is PR-3.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import Nomination, NominationError, ProducerRead, parse_ts, utcnow
from engine.entry_radar.producers.base import (
    AdapterResult,
    grade_staleness,
    read_json,
    stale_after,
    unavailable,
)

log = logging.getLogger(__name__)

FLOW_PULSE_SOURCE_ID = "flow_pulse:fastpath"

_DEFAULT_RVOL_MIN = 2.5


def read_flow_pulse(path: Path, *, now: datetime | None = None,
                    cfg: Mapping[str, Any] | None = None,
                    rvol_min: float | None = None,
                    lastgood: bool = False) -> AdapterResult:
    """``site/live/flow_pulse.json`` → intraday attention nominations + features.

    ``rvol_min`` defaults to the ``layer_c.rvol_tod_min`` budget knob: the
    adapter emits a nomination only for names actually showing unusual
    participation, because nominating all ~360 every 30 minutes would make the
    bus a mirror of the artifact rather than an enlistment record.

    ``lastgood=True`` reads the recovery sibling and forces ``stale``.
    """
    stamp = now or utcnow()
    payload, reason = read_json(path)
    if payload is None:
        return AdapterResult(unavailable(FLOW_PULSE_SOURCE_ID, reason, now=stamp))
    if not isinstance(payload, Mapping):
        return AdapterResult(
            unavailable(FLOW_PULSE_SOURCE_ID, f"{path} is not a flow_pulse.v1 object",
                        now=stamp))

    rows = [r for r in (payload.get("tickers") or ()) if isinstance(r, Mapping)]
    asof = parse_ts(payload.get("as_of"))
    if asof is None and payload.get("as_of_ms") is not None:
        try:
            asof = datetime.fromtimestamp(float(payload["as_of_ms"]) / 1000.0,
                                          tz=stamp.tzinfo)
        except (TypeError, ValueError, OSError):
            asof = None

    stale_min = stale_after(cfg, FLOW_PULSE_SOURCE_ID)
    status, age = grade_staleness(asof, now=stamp, stale_after_minutes=stale_min)
    self_declared_stale = bool(payload.get("stale")) or lastgood
    if self_declared_stale:
        status = "stale"

    knob = rvol_min
    if knob is None:
        try:
            knob = float(dict((cfg or {}).get("layer_c") or {}).get("rvol_tod_min",
                                                                    _DEFAULT_RVOL_MIN))
        except (TypeError, ValueError):
            knob = _DEFAULT_RVOL_MIN

    quality = "ok" if asof is not None else "degraded"
    if self_declared_stale:
        quality = "degraded"
    ttl = stamp + timedelta(minutes=max(1.0, stale_min))
    noms: list[Nomination] = []
    features: dict[str, dict[str, Any]] = {}

    for row in rows:
        sym = str(row.get("ticker") or "").strip().upper()
        if not sym:
            continue
        feat: dict[str, Any] = {}
        try:
            rvol = float(row["rvol_tod"]) if row.get("rvol_tod") is not None else None
        except (TypeError, ValueError):
            rvol = None
        if rvol is not None:
            feat["rvol_tod"] = rvol
        if feat:
            features[sym] = feat
        if rvol is None or rvol < knob:
            continue
        extras = []
        if row.get("higher_lows"):
            extras.append("higher lows")
        if row.get("bars_above_vwap"):
            extras.append(f"{row['bars_above_vwap']} bars above VWAP")
        text = f"Intraday participation {rvol:.2f}× the time-of-day norm"
        if extras:
            text += " (" + "; ".join(extras) + ")"
        try:
            noms.append(Nomination(
                ticker=sym, source_id=FLOW_PULSE_SOURCE_ID, source_family="market_price",
                reason_code="flow_pulse.rvol_tod",
                reason_text=text,
                observed_at=stamp,
                source_asof=min(asof, stamp) if asof is not None else stamp,
                source_value=rvol, source_horizon="intraday", ttl_until=ttl,
                evidence_ref=f"flow_pulse.json#{sym}", data_quality=quality,
            ))
        except NominationError as exc:
            log.warning("entry_radar.producers.live_flow: row dropped (%s)", exc)

    read = ProducerRead(source_id=FLOW_PULSE_SOURCE_ID, status=status,
                        nominations=tuple(noms), source_asof=asof, observed_at=stamp,
                        age_seconds=age, stale_after_seconds=stale_min * 60.0,
                        detail=f"{len(noms)} nomination(s) from {len(rows)} row(s); "
                               f"vintage={quality}"
                               + ("; producer self-declared stale" if self_declared_stale else ""))
    return AdapterResult(read, features=features)
