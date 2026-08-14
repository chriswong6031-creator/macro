"""engine/entry_radar/producers/base.py — the adapter contract every producer shares.

An adapter's whole job is: read ONE artifact, decide its availability, and emit
`mastermind.entry_probe_nomination.v1` records with honest provenance.  It
computes nothing, ranks nothing, and combines nothing — combining is the bus's
job and it does not combine either.

THREE INVARIANTS, ALL FROM CONTRACT §5
--------------------------------------
1. **``source_asof`` is the ARTIFACT's own asof**, never the clock.  If the
   artifact carries no asof field the adapter falls back to the file mtime and
   marks ``data_quality="degraded"`` — an unknown vintage is a real degradation,
   and saying so costs less than inventing one.
2. **``observed_at`` is the INGESTION clock.**  The pair is what makes the
   nomination replayable, and ``observed_at >= source_asof`` is enforced by the
   contract itself.
3. **A missing artifact is ``unavailable``, never an empty list.**  This
   worktree is sparse — ``data/`` and ``site/`` are absent — so an adapter that
   read absence as "nothing happening" would report a dead market from a
   checkout.  Every adapter here fails to ``unavailable`` with the reason
   attached.

STALENESS is per-artifact-cadence (``config/entry_radar.yml``
``producers.stale_after_minutes``): a 30-min fastpath artifact three passes old
is stale; a nightly artifact six hours old is fine.  A stale read still carries
real facts and stays usable — ``stale`` is aged, ``unavailable`` is absent, and
they are different states on purpose.

SOURCE-ID CONVENTION: ``<upstream_artifact>:<producer>``.  The prefix is how the
bus discloses correlated families, so two adapters over the SAME upstream
artifact must share a prefix (Track C §1.3 shared-upstream clusters).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import (
    Nomination,
    NominationError,
    ProducerRead,
    parse_ts,
    utcnow,
)

log = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_MIN = 2160.0
DEFAULT_TTL_MIN = 1440.0

#: Candidate keys for an artifact's own asof stamp, in preference order.  The
#: estate has no single convention (Track C): builders variously write
#: ``asof``, ``as_of``, ``generated``, ``generated_at``, ``updated``, ``ts``.
_ASOF_KEYS: tuple[str, ...] = (
    "asof", "as_of", "as_of_date", "generated_at", "generated", "updated_at",
    "updated", "built_at", "ts", "timestamp", "date",
)

#: Candidate keys for a per-row ticker.  Track C confirms ``ticker`` is the
#: house field; ``sym``/``symbol`` appear in the live and breadth lanes.
_TICKER_KEYS: tuple[str, ...] = ("ticker", "sym", "symbol")


def first_key(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def row_ticker(row: Mapping[str, Any]) -> str:
    return str(first_key(row, _TICKER_KEYS) or "").strip().upper()


def artifact_asof(payload: Any, path: Path | None = None) -> tuple[datetime | None, str]:
    """The artifact's OWN asof + a data-quality verdict.

    Returns ``(asof, quality)`` where quality is ``ok`` when the artifact
    declared its vintage and ``degraded`` when we had to fall back to the file
    mtime.  ``(None, "unknown")`` when neither exists.
    """
    if isinstance(payload, Mapping):
        for key in _ASOF_KEYS:
            got = parse_ts(payload.get(key))
            if got is not None:
                return got, "ok"
        for container in ("meta", "metadata", "header", "info"):
            block = payload.get(container)
            if isinstance(block, Mapping):
                for key in _ASOF_KEYS:
                    got = parse_ts(block.get(key))
                    if got is not None:
                        return got, "ok"
    if path is not None:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc), "degraded"
        except OSError:
            pass
    return None, "unknown"


def rows_of(payload: Any, *, keys: Sequence[str] = ()) -> list[Mapping[str, Any]]:
    """Normalise a JSON artifact to a flat row list.

    Handles the three shapes the estate actually ships: a bare list, a dict with
    a named rows key (``rows``/``items``/``tickers``/``names``/... plus any
    caller-supplied key), and a dict keyed BY ticker.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in (*keys, "rows", "items", "records", "data", "names", "tickers",
                "stocks", "entries", "results"):
        block = payload.get(key)
        if isinstance(block, list):
            return [r for r in block if isinstance(r, Mapping)]
        if isinstance(block, Mapping):
            return [{"ticker": k, **v} for k, v in block.items() if isinstance(v, Mapping)]
    # Dict keyed by ticker at the top level (flow_pulse's per-symbol map shape).
    keyed = [{"ticker": k, **v} for k, v in payload.items()
             if isinstance(v, Mapping) and str(k).isupper() and 1 <= len(str(k)) <= 15]
    return keyed


def read_json(path: Path) -> tuple[Any, str]:
    """``(payload, "")`` or ``(None, reason)``.  Absence is a REASON, not a value."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, f"{path} absent"
    except OSError as exc:
        return None, f"{path} unreadable: {exc}"
    except ValueError as exc:
        return None, f"{path} is not valid JSON: {exc}"


def grade_staleness(asof: datetime | None, *, now: datetime,
                    stale_after_minutes: float) -> tuple[str, float | None]:
    """``("ok"|"stale", age_seconds)``.  An unknown asof grades ``stale``.

    Unknown-vintage grading stale rather than ok is deliberate: we cannot prove
    it is current, and a §5 availability state must never be more confident
    than its evidence.
    """
    if asof is None:
        return "stale", None
    age = max(0.0, (now - asof).total_seconds())
    return ("stale" if age > max(1.0, stale_after_minutes) * 60.0 else "ok"), age


def stale_after(cfg: Mapping[str, Any] | None, source_id: str) -> float:
    """Per-artifact staleness budget from ``config/entry_radar.yml``.

    Exact id first, then the LONGEST matching prefix — so one
    ``breadth:constituents`` entry covers every per-index id
    (``breadth:constituents:sp500``, ``:sp400`` …) without the config having to
    enumerate them, and a config key can never bind nothing.
    """
    block = dict((cfg or {}).get("producers") or {})
    table = dict(block.get("stale_after_minutes") or {})
    got = table.get(source_id)
    if got is None:
        prefixes = [k for k in table if source_id.startswith(f"{k}:")]
        if prefixes:
            got = table[max(prefixes, key=len)]
    if got is None:
        got = block.get("default_stale_after_minutes", DEFAULT_STALE_AFTER_MIN)
    try:
        return float(got)
    except (TypeError, ValueError):
        return DEFAULT_STALE_AFTER_MIN


def clamp_asof(asof: datetime | None, now: datetime) -> tuple[datetime | None, bool]:
    """``(asof, clamped)`` — never let a FUTURE vintage pass silently.

    An artifact stamped ahead of the clock cannot be construction-checked by the
    §5 postdate law (``observed_at >= source_asof``) without clamping, but a
    SILENT clamp makes that law trivially satisfiable: any vintage, however
    wrong, is rewritten to now and then passes.  So every clamp is recorded —
    callers mark ``data_quality="degraded"`` and refuse to grade the read
    ``ok`` — which keeps the check meaningful and surfaces a clock skew or a
    mis-stamped producer instead of burying it.
    """
    if asof is None:
        return None, False
    return (now, True) if asof > now else (asof, False)


def build_read(source_id: str, *, payload: Any, reason: str, path: Path | None,
               now: datetime, cfg: Mapping[str, Any] | None,
               emit, ttl_minutes: float = DEFAULT_TTL_MIN) -> ProducerRead:
    """The shared adapter body: availability first, then emission.

    ``emit(rows, ctx) -> list[Nomination]`` is the only per-producer part.  A
    nomination that violates the frozen contract is dropped with a warning
    rather than poisoning the whole read — one malformed row must not cost the
    other 359.
    """
    if payload is None:
        return ProducerRead(source_id=source_id, status="unavailable", observed_at=now,
                            detail=reason or "artifact unavailable")

    asof, quality = artifact_asof(payload, path)
    safe_asof, clamped = clamp_asof(asof, now)
    status, age = grade_staleness(asof, now=now,
                                  stale_after_minutes=stale_after(cfg, source_id))
    if clamped:
        # A future vintage is not a fresh one.  Grading it `ok` would let a
        # mis-stamped producer look like the healthiest source we have.
        status = "stale"
        quality = "degraded"
    ctx = {
        "source_id": source_id,
        "observed_at": now,
        "source_asof": safe_asof if safe_asof is not None else now,
        "data_quality": quality if quality != "unknown" else "degraded",
        "ttl_until": now + timedelta(minutes=max(1.0, ttl_minutes)),
    }
    noms: list[Nomination] = []
    for row in emit(payload, ctx) or ():
        if isinstance(row, Nomination):
            noms.append(row)
            continue
        try:
            noms.append(Nomination(**row))
        except (NominationError, TypeError) as exc:
            log.warning("entry_radar.producers: %s dropped a row (%s)", source_id, exc)
    return ProducerRead(source_id=source_id, status=status, nominations=tuple(noms),
                        source_asof=asof, observed_at=now, age_seconds=age,
                        stale_after_seconds=stale_after(cfg, source_id) * 60.0,
                        detail=f"{len(noms)} nomination(s); vintage={quality}"
                               + (" (FUTURE vintage clamped)" if clamped else ""))


def unavailable(source_id: str, detail: str, *, now: datetime | None = None) -> ProducerRead:
    """The honest empty read: we could not look."""
    return ProducerRead(source_id=source_id, status="unavailable",
                        observed_at=now or utcnow(), detail=detail)


class AdapterResult:
    """A ``ProducerRead`` plus whatever side-tables that adapter also produced.

    ``ProducerRead`` is frozen AND slotted — correct for a contract object, and
    it means an adapter cannot smuggle an extra field onto it.  Adapters that
    yield BOTH nominations and layer inputs (features for Layer C, names for
    Layer A's classifier, ``history_age_sessions`` for the young cohort) return
    this instead.  One wrapper for all of them: three identical classes would
    be three places to keep in step.
    """

    __slots__ = ("read", "features", "names", "history_age")

    def __init__(self, read: ProducerRead, *,
                 features: Mapping[str, Mapping[str, Any]] | None = None,
                 names: Mapping[str, str] | None = None,
                 history_age: Mapping[str, int] | None = None) -> None:
        self.read = read
        self.features: dict[str, dict[str, Any]] = {
            k: dict(v) for k, v in (features or {}).items()}
        self.names: dict[str, str] = dict(names or {})
        self.history_age: dict[str, int] = dict(history_age or {})

    @property
    def status(self) -> str:
        return self.read.status

    @property
    def nominations(self) -> tuple[Nomination, ...]:
        return self.read.nominations
