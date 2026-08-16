"""engine/entry_radar/vendor_minutes.py — the bounded C3 minute reader (W4 §3).

WHAT THIS IS
------------
The production implementation of :class:`four_hour.IntradayReader`: one name,
one session, one already-loaded :class:`challengers.SessionTape`.  C3 needs 4H
buckets and 4H buckets need minutes, and the minutes are the ONE input the
nightly pack cannot freeze — there is no per-name intraday store in this estate,
so the bytes have to come from the vendor at read time.

THE NETWORK LIVES HERE AND NOWHERE ELSE IN THE PACKAGE.  ``challengers``,
``four_hour`` and ``indicator_core`` must never import this module, and a guard
test in ``tests/test_entry_radar_w4_c3_reader.py`` asserts they do not.  The
reason is the ``IntradayReader`` protocol's own docstring: the engine states what
it needs without owning how it arrives, which is what keeps CI network-free and
what keeps a "just this once" fetch out of the math.  This module is the only
place in ``engine/entry_radar/`` where a fetch is even expressible, and even here
the transport is INJECTED — tests hand in a callable over committed rows and
never open a socket.

EPISODE-WINDOWED, NEVER A BULK CRAWL
-------------------------------------
The caller asks for the sessions ONE episode needs — its arm session minus the
4H turn's warm-up, through today — and :data:`MAX_WINDOW_SESSIONS` refuses a
window wider than that shape could justify.  The refusal is deliberate: a reader
that will happily fetch a year of minutes for 1,500 names is a rate-limit
incident waiting for the first pass that mis-computes a window, and the bound
turns that from an outage into an exception.  Pacing follows the
``build_polygon_intraday`` precedent — a sleep on EVERY iteration, empties and
errors included, because the vendor counts requests rather than successes.

THE CACHE IS FOR COMPLETED SESSIONS ONLY, AND ONLY ON ONE ADJUSTMENT BASIS
---------------------------------------------------------------------------
A past session's minutes are settled, so its 4H buckets are cached in the state
dir (``c3_buckets/<TICKER>.json``) rather than re-fetched.  TODAY's tail is
ALWAYS re-fetched: a cached partial session is precisely the "incomplete bucket
read as complete" defect PIT-W4-7 exists to catch, and a cache that could serve
one would defeat the test that guards it.  The cached row carries the
``confirmed`` flag as it was computed at the time, and a cached session is only
ever served when every one of its buckets was confirmed.

WHAT IS NOT TRUE IS THAT THOSE CLOSES ARE IMMUTABLE.  ``AGGS_PARAMS`` asks for
``adjusted=true``, and a split or a large cash dividend retroactively rescales
the vendor's entire adjusted history — so a cache keyed on ``(TICKER, session)``
alone would hand ``run_c3`` a series that mixes PRE-adjustment cached closes
with POST-adjustment fresh ones across the corporate-action boundary.  That seam
fabricates a move in the 4H histogram, which fabricates a turn: the W3-1 defect
reintroduced in the one lane where no basis audit runs.

So each cached session is STAMPED with the adjustment basis it was written on —
``{pack_as_of, substrate_fingerprint}``, supplied by the caller as ``vintage``,
where the fingerprint is a digest of the frozen pack's own adjusted close for
that session.  A normal nightly close appends a bar and moves nothing behind it,
so the stamp is stable; a rescale moves it, and a mismatch drops the WHOLE
ticker's cache and refetches, because a split invalidates every session at once
rather than only the one that was asked for.  A caller passing no ``vintage``
gets the old unchecked behaviour and is told so here rather than silently: the
production caller (``live_eval._run_c3``) always passes one.

WHAT THIS MODULE DOES NOT DO.  It does not decide whether C3 runs (the evaluator
does, from the pack's confirmed K and the ledger's open episodes), it does not
compute a turn, and it writes nothing under ``data/``.  Its whole surface is
"give me this name's minutes for this session, cheaply and no more often than
necessary".
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from engine.entry_radar import challengers as ch
from engine.entry_radar import four_hour as fh

#: The vendor aggregate endpoint, exactly the ``build_polygon_intraday`` shape.
AGGS_PATH = "/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"

#: Query parameters.  ``adjusted=true`` is load-bearing: the pack substrate is an
#: ADJUSTED daily frame, and a raw intraday tape beside it is exactly the spliced
#: basis W3-1 refuses.  ``sort=asc`` because the tape is built in session order.
AGGS_PARAMS: dict[str, Any] = {"adjusted": "true", "sort": "asc", "limit": 50000}

#: Seconds between requests.  ``build_polygon_intraday`` paces at 0.06 s on every
#: iteration including the empty and failed ones; C3 fetches far fewer names, so
#: the same figure is generous rather than tight.
SLEEP_SECONDS = 0.06

#: The widest window one episode can justify: ``C3_ARM_EXPIRY_SESSIONS`` (15) of
#: episode life plus the 4H turn's ~44-session warm-up, doubled for holidays and
#: for an episode that armed before the ledger's own history.  A request past
#: this is a WINDOW BUG, and failing loudly beats fetching a year of minutes for
#: every name in the probe set.
MAX_WINDOW_SESSIONS = 180

_CACHE_DIRNAME = "c3_buckets"
_CACHE_SCHEMA = "entry_radar.c3_buckets/v1"


class VendorMinutesError(fh.C3Error):
    """A refusal by the reader.  Never raised for an EMPTY vendor response."""


def polygon_symbol(ticker: str) -> str:
    """``BRK-B`` → ``BRK.B``.  The estate's store uses a dash, Polygon a dot."""
    return str(ticker).replace("-", ".")


@dataclass(frozen=True, slots=True)
class ReaderStats:
    """What one pass's reads cost.  Rides the health receipt's ``c3_reader``."""

    fetched_n: int = 0
    cache_hits: int = 0
    errors: int = 0
    empty: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"fetched_n": self.fetched_n, "cache_hits": self.cache_hits,
                "errors": self.errors, "empty": self.empty}


def default_transport() -> Callable[[str, Mapping[str, Any]], list[dict]]:
    """The entitled REST client, built lazily.

    LAZY ON PURPOSE.  Importing ``collectors.polygon_options`` pulls the whole
    adapter stack (and its HTTP session) into any process that merely imports
    this module, which would put a network client behind every ``engine`` import
    in CI.  Resolving it at first use keeps the import graph honest and keeps the
    test path — which injects its own transport — from ever touching it.
    """
    from collectors.polygon_options import PolygonOptions  # noqa: PLC0415

    client = PolygonOptions()

    def _get(path: str, params: Mapping[str, Any]) -> list[dict]:
        if not client.enabled():
            raise VendorMinutesError(
                "no vendor API key (POLYGON_API_KEY/MASSIVE_API_KEY) — C3 has no "
                "minute source on this host; the lane publishes C3 unavailable "
                "rather than guessing a 4H bar")
        return client._get(path, dict(params))  # noqa: SLF001

    return _get


class VendorMinuteReader:
    """Bounded per-name minute aggregates, with a completed-session cache.

    Satisfies :class:`four_hour.IntradayReader` — ``reader(ticker, session)``
    returns one session's :class:`~challengers.SessionTape`.  :meth:`buckets` is
    the cheaper path the evaluator prefers: it answers in 4H buckets and can
    serve a completed session from the state dir without a request at all.

    ``transport`` is ``(path, params) -> list[row]`` where each row is the
    vendor's aggregate dict (``t`` ms, ``o``/``h``/``l``/``c``/``v``).  Tests
    inject a callable over committed fixtures; production gets
    :func:`default_transport`.
    """

    def __init__(self, *, transport: Callable[[str, Mapping[str, Any]], list[dict]]
                 | None = None, state_dir: Path | str | None = None,
                 sleep_seconds: float = SLEEP_SECONDS,
                 price_basis: str = ch.BASIS_ADJUSTED,
                 max_window_sessions: int = MAX_WINDOW_SESSIONS) -> None:
        self._transport = transport
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self.sleep_seconds = float(sleep_seconds)
        self.price_basis = str(price_basis)
        self.max_window_sessions = int(max_window_sessions)
        self.fetched_n = 0
        self.cache_hits = 0
        self.errors = 0
        self.empty = 0
        self._cache: dict[str, dict[str, Any]] = {}

    # -- the IntradayReader protocol ---------------------------------------
    def __call__(self, ticker: str, session: date) -> ch.SessionTape:
        """One session's minutes.  An empty vendor response is an EMPTY tape.

        Empty is not an error and not a raise: a halted name, a session with no
        prints in the window, and a symbol the vendor does not carry all produce
        the same honest answer — a tape with no minutes, from which
        ``four_hour_buckets`` derives buckets with ``close=None`` that
        ``run_c3`` discloses as ``confirmed_empty`` rather than fabricating.
        """
        rows = self._fetch(ticker, session)
        return fh.tape_from_rows(
            session, [(datetime.fromtimestamp(float(r["t"]) / 1000.0, tz=timezone.utc),
                       r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v") or 0.0)
                      for r in rows if r.get("t") is not None],
            price_basis=self.price_basis,
            vintage=f"polygon_minute_aggs:{session.isoformat()}")

    # -- the cached path the evaluator prefers ------------------------------
    def buckets(self, ticker: str, session: date, *, now: datetime | None = None,
                vintage: Mapping[str, Any] | None = None,
                ) -> tuple[fh.FourHourBucket, ...]:
        """This session's 4H buckets, from the cache when the session is done.

        A cached entry is served ONLY when every bucket in it was confirmed AND
        it was written on the same adjustment basis this call declares.  Today's
        session — and any session whose cached buckets were not all confirmed
        when they were written — is always re-derived, because a partial session
        served from a cache is the incomplete-bucket read PIT-W4-7 forbids.

        ``vintage`` is ``{pack_as_of, substrate_fingerprint}`` for THIS session
        (see the module docstring).  A fingerprint that disagrees with the stored
        one invalidates the whole ticker before anything is served.
        """
        if vintage is not None:
            self._invalidate_on_vintage(ticker, session, vintage)
        cached = self._cached_buckets(ticker, session)
        if cached is not None:
            self.cache_hits += 1
            return cached
        derived = fh.four_hour_buckets(self(ticker, session), now=now)
        if derived and all(b.confirmed for b in derived):
            self._store_buckets(ticker, session, derived, vintage=vintage)
        return derived

    def stats(self) -> ReaderStats:
        return ReaderStats(fetched_n=self.fetched_n, cache_hits=self.cache_hits,
                           errors=self.errors, empty=self.empty)

    def assert_window(self, start: date, end: date) -> None:
        """Refuse a window no episode could justify (the bulk-crawl guard)."""
        from lib.nyse_calendar import sessions_between  # noqa: PLC0415
        span = len(sessions_between(start, end))
        if span > self.max_window_sessions:
            raise VendorMinutesError(
                f"C3 window {start}..{end} spans {span} sessions, past the "
                f"{self.max_window_sessions}-session bound — the reader is "
                f"episode-windowed by design (W4 §3); a window this wide is a "
                f"caller bug, and fetching it would be a bulk crawl across the "
                f"whole probe set")

    # -- internals ----------------------------------------------------------
    def _fetch(self, ticker: str, session: date) -> list[dict]:
        path = AGGS_PATH.format(symbol=polygon_symbol(ticker), multiplier=1,
                                timespan="minute", start=session.isoformat(),
                                end=session.isoformat())
        transport = self._transport
        if transport is None:
            transport = self._transport = default_transport()
        try:
            rows = transport(path, dict(AGGS_PARAMS)) or []
        except Exception:
            self.errors += 1
            raise
        finally:
            # Pace EVERY call, empties and failures included — the vendor counts
            # requests, not successes (build_polygon_intraday's own comment).
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)
        self.fetched_n += 1
        if not rows:
            self.empty += 1
        return list(rows)

    def _cache_path(self, ticker: str) -> Path | None:
        if self.state_dir is None:
            return None
        safe = "".join(c if c.isalnum() or c in "._-" else "_"
                       for c in str(ticker).upper())
        return self.state_dir / _CACHE_DIRNAME / f"{safe}.json"

    def _cache_file(self, ticker: str) -> dict[str, Any]:
        key = str(ticker).upper()
        if key in self._cache:
            return self._cache[key]
        path = self._cache_path(ticker)
        body: dict[str, Any] = {"schema": _CACHE_SCHEMA, "ticker": key, "sessions": {}}
        if path is not None and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, Mapping) and raw.get("schema") == _CACHE_SCHEMA:
                    body = {"schema": _CACHE_SCHEMA, "ticker": key,
                            "sessions": dict(raw.get("sessions") or {})}
            except (OSError, ValueError):
                body = {"schema": _CACHE_SCHEMA, "ticker": key, "sessions": {}}
        self._cache[key] = body
        return body

    @staticmethod
    def _entry(raw: Any) -> tuple[list[Any], dict[str, Any]]:
        """``(bucket rows, vintage)`` from either stored shape.

        The bare-list form predates the adjustment stamp and is read rather than
        rejected; it simply carries no vintage, which the check below treats as
        UNCHECKABLE rather than as agreement.
        """
        if isinstance(raw, list):
            return list(raw), {}
        if isinstance(raw, Mapping):
            return list(raw.get("buckets") or []), dict(raw.get("vintage") or {})
        return [], {}

    def _invalidate_on_vintage(self, ticker: str, session: date,
                               vintage: Mapping[str, Any]) -> None:
        """Drop the WHOLE ticker's cache when the adjustment basis has moved.

        Whole-ticker, not per-session: a split rescales every session at once, so
        invalidating only the one that was asked for would leave the rest of the
        window on the old basis and reassemble the same spliced series.

        Only ``substrate_fingerprint`` is compared.  ``pack_as_of`` moves every
        night by construction and comparing it would throw the cache away daily,
        which is the cost this cache exists to avoid; it is stored as the human
        receipt for WHEN the row was written.  A fingerprint absent on either
        side is UNCHECKABLE — a session outside the frozen substrate has no pack
        close to compare against — and an uncheckable row is served rather than
        thrashed, which is a stated hole and not a silent one.
        """
        wanted = vintage.get("substrate_fingerprint")
        if not wanted:
            return
        body = self._cache_file(ticker)
        _rows, stored = self._entry(body["sessions"].get(session.isoformat()))
        got = stored.get("substrate_fingerprint")
        if not got or str(got) == str(wanted):
            return
        body["sessions"] = {}
        path = self._cache_path(ticker)
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass

    def _cached_buckets(self, ticker: str,
                        session: date) -> tuple[fh.FourHourBucket, ...] | None:
        rows, _vintage = self._entry(
            self._cache_file(ticker)["sessions"].get(session.isoformat()))
        if not rows:
            return None
        try:
            built = tuple(_bucket_from_dict(row) for row in rows)
        except (KeyError, TypeError, ValueError):
            return None
        return built if built and all(b.confirmed for b in built) else None

    def _store_buckets(self, ticker: str, session: date,
                       buckets: Sequence[fh.FourHourBucket],
                       vintage: Mapping[str, Any] | None = None) -> None:
        body = self._cache_file(ticker)
        body["sessions"][session.isoformat()] = {
            "buckets": [b.to_dict() for b in buckets],
            "vintage": {k: v for k, v in dict(vintage or {}).items() if v is not None},
        }
        path = self._cache_path(ticker)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(body, allow_nan=False, separators=(",", ":"),
                                 sort_keys=True).encode("utf-8")
            fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
                tmp = ""
            finally:
                if tmp:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
        except OSError:
            return


def _bucket_from_dict(row: Mapping[str, Any]) -> fh.FourHourBucket:
    """Rebuild a cached bucket, IN THE SESSION'S OWN TIMEZONE.

    ``effective_minutes``/``clipped`` are DERIVED.  The cached row carries them
    for a human reader and they are deliberately NOT passed to the constructor:
    they are properties computed from ``start`` and ``effective_end``, and
    accepting them as input would let a corrupted cache assert a clipping the
    timestamps contradict.

    THE TIMEZONE IS THE LOAD-BEARING PART.  ``FourHourBucket.to_dict`` serialises
    through ``utc_iso``, so a naive round-trip returns UTC-aware datetimes while
    a freshly derived bucket carries the EASTERN ones ``session_window_et``
    produced.  Same instants, different ``tzinfo`` — and
    ``confirmed_four_hour_series`` builds a ``pd.DatetimeIndex`` over them, which
    refuses a list of mixed offsets outright (measured: ``Tz-aware datetime
    cannot be converted to datetime64 unless utc=True``).  A run mixing one
    cached session with one fresh one would therefore raise, and only for names
    whose episode window straddles the cache — the worst possible shape for a
    bug.  The zone is taken FROM the session window rather than named here, so a
    calendar change moves both paths together.
    """
    session = date.fromisoformat(str(row["session"]))
    tz = fh.session_window_et(session)[0].tzinfo
    return fh.FourHourBucket(
        session=str(row["session"]), index=int(row["index"]),
        start=_parse(row["start"], tz), effective_end=_parse(row["effective_end"], tz),
        confirmed=bool(row["confirmed"]),
        close=(None if row.get("close") is None else float(row["close"])),
        minutes=int(row.get("minutes") or 0),
        nominal_minutes=int(row.get("nominal_minutes") or fh.FOUR_HOUR_MINUTES))


def _parse(raw: Any, tz: Any = None) -> datetime:
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed if tz is None else parsed.astimezone(tz)


__all__ = ["AGGS_PARAMS", "AGGS_PATH", "MAX_WINDOW_SESSIONS", "SLEEP_SECONDS",
           "ReaderStats", "VendorMinuteReader", "VendorMinutesError",
           "default_transport", "polygon_symbol"]
