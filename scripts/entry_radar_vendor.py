"""Bounded vendor REST client + session cache for the W5 replay (prereg §4/§5/§11).

WHY THIS LIVES IN ``scripts/`` AND NOT IN THE ENGINE
-----------------------------------------------------
``engine/entry_radar/replay/`` is a pure package (its ``__init__`` states the law:
no network, no wall clock, no environment reads, no durable writes).  Every byte
the replay computes on therefore has to arrive through an injected reader, and
this module is the one implementation of that seam that talks to the vendor.  The
engine never imports it; the runner wires it in.

WHAT THE PREREG FIXES HERE (and what it does not)
--------------------------------------------------
* §4 — the **vendor plane** (Polygon/Massive REST, ``adjusted=true``, split-only)
  is the ONE substrate for minute reconstruction, Panel-B daily history, every
  outcome leg, and Panel-A C1/C2/C3 confirmed-daily history.  ``adjusted=true`` is
  measured split-only (§0(b)); this module never mixes it with the curated
  split+dividend store — it only serves the vendor side, and the caller keeps the
  planes apart.
* §5 — minute aggregates are fetched **per bounded episode window**, never as a
  bulk crawl, and there is no permanent minute store: the cache lives OUTSIDE the
  repo (the runner hands in a scratchpad path; :func:`_assert_cache_outside_repo`
  refuses anything under the repo root) and its manifest + payload hashes are what
  the results package fingerprints.
* §11 — NBBO half-spread reads come from ``v3/quotes``.  A missing, invalid, or
  unentitled quote response is **never** zero cost: :func:`quotes_at` returns an
  empty list and the caller's liquidity floor binds.  That is why this one
  function may not raise on an entitlement error.

IMPORT PURITY.  Nothing at module scope reads the environment, the config file,
the network, or the disk.  The key/base/User-Agent are resolved lazily inside
:func:`_client`, so importing this module in a test process costs nothing and
reaches nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode

import pandas as pd
import requests

from lib import config

log = logging.getLogger(__name__)

#: Repo root — the cache may never live inside it (§5 "no permanent minute store").
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Fallback base if the config block is absent.  ``lib.config`` carries
#: ``polygon.base_url`` = https://api.polygon.io; massive.com is a Polygon clone
#: and answers the same paths, which is why the key falls back to MASSIVE_API_KEY.
BASE_URL_DEFAULT = "https://api.polygon.io"

#: Vendor aggregate page size.  A response of exactly this many rows is treated as
#: TRUNCATED and the window is split — a silently-clipped minute window would
#: fabricate an empty afternoon and, through it, a sampled path that never existed.
AGG_LIMIT = 50_000

#: Calendar-day width of one minute-window request before chunking kicks in.
#: ~960 minute aggregates/session incl. extended hours => ~30 sessions fits inside
#: AGG_LIMIT with room to spare; the truncation check is the real guard.
MINUTE_CHUNK_DAYS = 30

#: Recursion bound on the truncation split (30d -> 15 -> 7 -> 3 -> 1 -> refuse).
MINUTE_SPLIT_MAX_DEPTH = 6

ET = "America/New_York"

DAILY_COLUMNS = ("o", "h", "l", "c", "v")
MINUTE_COLUMNS = ("t", "o", "h", "l", "c", "v")

#: §11 quote read: the last <=50 quotes at or before T.
QUOTE_LIMIT = 50

_MANIFEST_NAME = "manifest.jsonl"
_DAILY_DIR = "vendor_daily"
_MINUTE_DIR = "vendor_minute"
_QUOTE_DIR = "vendor_quotes"
_RANGE_SUFFIX = ".range.json"


class VendorError(RuntimeError):
    """A vendor fetch, cache, or configuration fault.  Named, never swallowed."""


# --------------------------------------------------------------------------- #
# client resolution (lazy — nothing here runs at import)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Client:
    base: str
    key: str | None
    timeout: int
    retries: int
    user_agent: str

    @property
    def online(self) -> bool:
        return bool(self.key)


def _client() -> _Client:
    """Resolve base/key/UA from config + env.  Same key law as
    ``collectors/polygon_options.py:104-107``: POLYGON_API_KEY, then the
    MASSIVE_API_KEY a prior session seeded, so a live run never silently no-ops."""
    try:
        cfg = dict(config.load().get("polygon") or {})
    except Exception as exc:  # noqa: BLE001 — a missing config is not a crash here
        log.warning("entry_radar_vendor: config.load() failed (%s); using defaults", exc)
        cfg = {}
    key = (config.secret(str(cfg.get("api_key_env", "POLYGON_API_KEY")))
           or config.secret("MASSIVE_API_KEY"))
    try:
        ua = str(config.load()["sponsors"]["user_agent"])
    except Exception:  # noqa: BLE001
        ua = "macro-dashboard/entry-radar-w5"
    return _Client(base=str(cfg.get("base_url") or BASE_URL_DEFAULT).rstrip("/"),
                   key=key, timeout=int(cfg.get("request_timeout", 60) or 60),
                   retries=int(cfg.get("retries", 3) or 3), user_agent=ua)


# --------------------------------------------------------------------------- #
# cache discipline
# --------------------------------------------------------------------------- #
def _assert_cache_outside_repo(cache_dir: Path) -> Path:
    """§5: the session cache lives OUTSIDE the repo.  Fail-closed.

    Checked on the RESOLVED path so a ``../`` walk back into the tree is caught
    too.  This is the mechanical half of "no permanent minute store" — prose alone
    has never stopped a convenient ``data/`` write.
    """
    resolved = Path(cache_dir).resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise VendorError(
            f"cache_dir {resolved} is inside the repo ({REPO_ROOT}); §5 forbids a "
            f"durable vendor store in the tree — pass a scratchpad path")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _url_sans_key(url: str, params: dict[str, Any]) -> str:
    """The request URL with the apiKey stripped — what the manifest records."""
    safe = {k: v for k, v in params.items() if k != "apiKey"}
    return f"{url}?{urlencode(sorted(safe.items()))}" if safe else url


def _manifest_append(cache_dir: Path, row: dict[str, Any]) -> None:
    """One jsonl line per FETCH (never per cache hit) — the §5 fetch receipt."""
    path = cache_dir / _MANIFEST_NAME
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def read_manifest(cache_dir: str | Path) -> list[dict[str, Any]]:
    """Every recorded fetch, oldest first.  Torn lines are skipped, never counted."""
    path = Path(cache_dir) / _MANIFEST_NAME
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _http_get(client: _Client, url: str, params: dict[str, Any]) -> requests.Response:
    """GET with the house retry shape (``collectors/base.py:136-156``)."""
    headers = {"User-Agent": client.user_agent}
    last: Exception | None = None
    for attempt in range(max(1, client.retries)):
        try:
            r = requests.get(url, params=params, headers=headers,
                             timeout=client.timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 — retried, then surfaced
            last = exc
            if attempt < client.retries - 1:
                time.sleep(3.0 * (2 ** attempt))
    raise VendorError(f"vendor GET {url.split('?')[0]} failed: {last}") from last


def _get_results(client: _Client, cache_dir: Path, path: str, params: dict[str, Any],
                 *, ticker: str, kind: str) -> list[dict[str, Any]]:
    """One bounded GET -> ``results`` list, with its manifest receipt.

    The payload hash is taken over the RAW response text, so a re-run that gets
    different bytes from the vendor is visible in the results package rather than
    silently absorbed into a different answer.
    """
    if not client.online:
        raise VendorError(
            "no vendor key (POLYGON_API_KEY / MASSIVE_API_KEY); a live fetch is "
            "impossible and a cache miss cannot be approximated")
    url = f"{client.base}{path}"
    full = {**params, "apiKey": client.key}
    response = _http_get(client, url, full)
    text = response.text or ""
    payload = response.json() or {}
    results = payload.get("results") or []
    if not isinstance(results, list):
        results = []
    _manifest_append(cache_dir, {
        "ticker": ticker, "kind": kind, "url": _url_sans_key(url, params),
        "rows": len(results), "status": int(response.status_code),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    })
    return results


# --------------------------------------------------------------------------- #
# daily OHLCV  (§4 vendor plane)
# --------------------------------------------------------------------------- #
def _daily_cache_path(cache_dir: Path, ticker: str) -> Path:
    return cache_dir / _DAILY_DIR / f"{ticker}.parquet"


def _daily_frame(results: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Vendor day aggregates -> o/h/l/c/v indexed by ET SESSION DATE.

    ``t`` is an epoch-ms instant; a day aggregate's instant is the session's
    00:00 ET, so the conversion is tz-aware and then normalised.  Doing it in UTC
    would push every session to the previous day for part of the year.
    """
    rows = [r for r in results if r.get("t") is not None]
    if not rows:
        return pd.DataFrame(columns=list(DAILY_COLUMNS),
                            index=pd.DatetimeIndex([], name="session"))
    idx = (pd.to_datetime([int(r["t"]) for r in rows], unit="ms", utc=True)
           .tz_convert(ET).normalize().tz_localize(None))
    frame = pd.DataFrame({
        "o": [float(r.get("o")) if r.get("o") is not None else float("nan") for r in rows],
        "h": [float(r.get("h")) if r.get("h") is not None else float("nan") for r in rows],
        "l": [float(r.get("l")) if r.get("l") is not None else float("nan") for r in rows],
        "c": [float(r.get("c")) if r.get("c") is not None else float("nan") for r in rows],
        "v": [float(r.get("v") or 0.0) for r in rows],
    }, index=pd.DatetimeIndex(idx, name="session"))
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


#: Parsed daily-cache frames, keyed by (path, mtime_ns, size) — see
#: :func:`_read_daily_cache`.  Bounded so a long-lived process (the live
#: gateway) cannot grow without limit; the replay's working set is far smaller.
_DAILY_PARSE_CACHE: "OrderedDict[tuple[str, int, int], pd.DataFrame]" = OrderedDict()
_DAILY_PARSE_CACHE_MAX = 4096


def _read_daily_cache(path: Path) -> pd.DataFrame | None:
    """Parse a pre-warmed daily cache file, MEMOIZED on (path, mtime, size).

    ``daily_ohlcv`` is its only caller and calls it once per invocation, so the
    W5 replay re-parsed the SAME parquet on every episode — the bench (SPY) and
    sector-ETF legs are read once per episode by construction, and a name that
    fires n times is read n times.  Re-parsing is pure waste: an unchanged file
    yields an identical frame, so the key carries mtime_ns AND size and any
    rewrite (including ``daily_ohlcv``'s own ``to_parquet`` merge-back) misses
    the memo and re-reads.  Every branch ``daily_ohlcv`` takes afterwards —
    ``_cache_covers``, fetch-or-not, ``_slice`` — is byte-identical either way.

    The memoized frame is shared, and the callers treat it as read-only
    (``_slice`` copies, ``_merge_daily`` concatenates); do not mutate it in place.
    """
    if not path.exists():
        return None
    try:
        stat = path.stat()
        key = (str(path), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:  # noqa: BLE001 — an unstattable path is a miss, not a crash
        return None
    hit = _DAILY_PARSE_CACHE.get(key)
    if hit is not None:
        _DAILY_PARSE_CACHE.move_to_end(key)
        return hit
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 — a corrupt cache is a miss, not a crash
        log.warning("entry_radar_vendor: unreadable daily cache %s (%s)", path, exc)
        return None
    missing = [c for c in DAILY_COLUMNS if c not in frame.columns]
    if missing:
        raise VendorError(f"pre-warmed daily cache {path} is missing {missing}; the "
                          f"orchestrator's layout must match {list(DAILY_COLUMNS)}")
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame.index.name = "session"
    parsed = frame[list(DAILY_COLUMNS)].sort_index()
    _DAILY_PARSE_CACHE[key] = parsed
    while len(_DAILY_PARSE_CACHE) > _DAILY_PARSE_CACHE_MAX:
        _DAILY_PARSE_CACHE.popitem(last=False)
    return parsed


def _recorded_ranges(path: Path) -> list[tuple[date, date]]:
    side = path.with_suffix(path.suffix + _RANGE_SUFFIX)
    if not side.exists():
        return []
    try:
        raw = json.loads(side.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for lo, hi in raw or []:
        try:
            out.append((date.fromisoformat(str(lo)), date.fromisoformat(str(hi))))
        except Exception:  # noqa: BLE001
            continue
    return out


def _record_range(path: Path, start: date, end: date) -> None:
    side = path.with_suffix(path.suffix + _RANGE_SUFFIX)
    ranges = _recorded_ranges(path)
    ranges.append((start, end))
    side.write_text(json.dumps([[a.isoformat(), b.isoformat()] for a, b in ranges]),
                    encoding="utf-8")


def _cache_covers(frame: pd.DataFrame | None, path: Path, start: date, end: date) -> bool:
    """Is the on-disk daily cache authoritative for ``[start, end]``?

    TWO ANSWERS, deliberately different:

    * A cache this module wrote carries a ``.range.json`` sidecar naming the
      windows actually fetched — coverage is then exact, and an IPO whose history
      begins after ``start`` does not force an endless re-fetch.
    * A cache the ORCHESTRATOR pre-warmed carries no sidecar.  The prereg's
      instruction is that it MUST be honored, so the test is only that it reaches
      the requested end; a short leading edge is read as the name's own history,
      not as a hole.  (Stated rather than inferred: a pre-warm that is genuinely
      short at the front is indistinguishable from an IPO without a second feed.)
    """
    if frame is None or frame.empty:
        return False
    for lo, hi in _recorded_ranges(path):
        if lo <= start and hi >= end:
            return True
    return bool(frame.index[-1].date() >= end)


def daily_ohlcv(ticker: str, start: date | str, end: date | str, *,
                cache_dir: str | Path) -> pd.DataFrame:
    """Vendor daily OHLCV for ``[start, end]`` on the §4 plane, cached per ticker.

    ONE ``/v2/aggs/ticker/{T}/range/1/day`` call (``adjusted=true``, ascending,
    ``limit=50000``) per uncached window.  Columns ``o,h,l,c,v``; index = ET
    session dates.  A cache pre-warmed at ``<cache_dir>/vendor_daily/<T>.parquet``
    is honored without a fetch (see :func:`_cache_covers`).
    """
    cache_dir = _assert_cache_outside_repo(Path(cache_dir))
    start = start if isinstance(start, date) else date.fromisoformat(str(start))
    end = end if isinstance(end, date) else date.fromisoformat(str(end))
    if end < start:
        raise VendorError(f"daily window {start}..{end} runs backwards")
    path = _daily_cache_path(cache_dir, ticker)
    cached = _read_daily_cache(path)
    client = _client()
    if _cache_covers(cached, path, start, end) or (cached is not None and not client.online):
        assert cached is not None
        return _slice(cached, start, end)
    if not client.online:
        raise VendorError(
            f"{ticker}: no vendor key and no pre-warmed daily cache at {path}")

    results = _get_results(
        client, cache_dir,
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}",
        {"adjusted": "true", "sort": "asc", "limit": AGG_LIMIT},
        ticker=ticker, kind="daily")
    fetched = _daily_frame(results)
    merged = fetched if cached is None else _merge_daily(cached, fetched)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path)
    _record_range(path, start, end)
    return _slice(merged, start, end)


def _merge_daily(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if new.empty:
        return old
    combined = pd.concat([old, new])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined[list(DAILY_COLUMNS)]


def _slice(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    return frame.loc[(frame.index >= lo) & (frame.index <= hi)].copy()


# --------------------------------------------------------------------------- #
# minute windows  (§5 PIT replay substrate)
# --------------------------------------------------------------------------- #
def _minute_cache_path(cache_dir: Path, ticker: str, start: date, end: date) -> Path:
    return (cache_dir / _MINUTE_DIR
            / f"{ticker}__{start.isoformat()}__{end.isoformat()}.parquet")


def _minute_frame(results: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Vendor minute aggregates -> ``t,o,h,l,c,v`` with ``t`` tz-aware ET.

    ``t`` stays an INSTANT (not a date): the A5.1 sampler decides RTH membership
    and interval boundaries from it, and a naive stamp would make that decision
    unanswerable (``challengers.MinuteBar.__post_init__`` refuses naive bars for
    exactly this reason).
    """
    rows = [r for r in results if r.get("t") is not None]
    if not rows:
        empty = {c: pd.Series(dtype="float64") for c in MINUTE_COLUMNS[1:]}
        empty["t"] = pd.Series(dtype=f"datetime64[ns, {ET}]")
        return pd.DataFrame(empty)[list(MINUTE_COLUMNS)]
    stamps = pd.to_datetime([int(r["t"]) for r in rows], unit="ms", utc=True).tz_convert(ET)
    frame = pd.DataFrame({
        "t": stamps,
        "o": [float(r.get("o")) if r.get("o") is not None else float("nan") for r in rows],
        "h": [float(r.get("h")) if r.get("h") is not None else float("nan") for r in rows],
        "l": [float(r.get("l")) if r.get("l") is not None else float("nan") for r in rows],
        "c": [float(r.get("c")) if r.get("c") is not None else float("nan") for r in rows],
        "v": [float(r.get("v") or 0.0) for r in rows],
    })
    frame = (frame.drop_duplicates(subset="t", keep="last")
             .sort_values("t").reset_index(drop=True))
    return frame[list(MINUTE_COLUMNS)]


def _fetch_minute_span(client: _Client, cache_dir: Path, ticker: str,
                       lo: date, hi: date, depth: int = 0) -> pd.DataFrame:
    """One bounded minute request, split on truncation.

    A response holding exactly ``AGG_LIMIT`` rows is TRUNCATED, not complete.
    Accepting it would hand the sampler a window whose afternoon simply is not
    there — an empty interval reads as "no print", and "no print" is a lawful
    sampled state, so the loss would be invisible.  The window is halved instead,
    down to a single session; a single session that still truncates refuses.
    """
    results = _get_results(
        client, cache_dir,
        f"/v2/aggs/ticker/{ticker}/range/1/minute/{lo.isoformat()}/{hi.isoformat()}",
        {"adjusted": "true", "sort": "asc", "limit": AGG_LIMIT},
        ticker=ticker, kind="minute")
    if len(results) < AGG_LIMIT:
        return _minute_frame(results)
    if lo == hi or depth >= MINUTE_SPLIT_MAX_DEPTH:
        raise VendorError(
            f"{ticker} {lo}..{hi}: vendor returned the full {AGG_LIMIT}-row page and "
            f"the window cannot be split further; the tape would be silently clipped")
    mid = (pd.Timestamp(lo) + (pd.Timestamp(hi) - pd.Timestamp(lo)) / 2).date()
    left = _fetch_minute_span(client, cache_dir, ticker, lo, mid, depth + 1)
    right = _fetch_minute_span(client, cache_dir, ticker,
                               (pd.Timestamp(mid) + pd.Timedelta(days=1)).date(),
                               hi, depth + 1)
    out = pd.concat([left, right], ignore_index=True)
    return (out.drop_duplicates(subset="t", keep="last")
            .sort_values("t").reset_index(drop=True))


def minute_window(ticker: str, start_session: date | str, end_session: date | str, *,
                  cache_dir: str | Path) -> pd.DataFrame:
    """Vendor 1-minute aggregates spanning ``[start_session, end_session]``.

    ``adjusted=true``, ascending, one bounded window per episode (§5 — never a
    bulk crawl).  Columns ``t,o,h,l,c,v`` with ``t`` tz-aware ET.  Cached per
    ``(ticker, start, end)``; the 50k page limit is handled by chunking and, if a
    chunk still fills the page, by splitting it.
    """
    cache_dir = _assert_cache_outside_repo(Path(cache_dir))
    lo = (start_session if isinstance(start_session, date)
          else date.fromisoformat(str(start_session)))
    hi = (end_session if isinstance(end_session, date)
          else date.fromisoformat(str(end_session)))
    if hi < lo:
        raise VendorError(f"minute window {lo}..{hi} runs backwards")
    path = _minute_cache_path(cache_dir, ticker, lo, hi)
    if path.exists():
        try:
            cached = pd.read_parquet(path)
            if "t" in cached.columns:
                return cached[list(MINUTE_COLUMNS)]
        except Exception as exc:  # noqa: BLE001
            log.warning("entry_radar_vendor: unreadable minute cache %s (%s)", path, exc)

    client = _client()
    if not client.online:
        raise VendorError(f"{ticker}: no vendor key and no cached minute window at {path}")

    parts: list[pd.DataFrame] = []
    cursor = lo
    step = pd.Timedelta(days=MINUTE_CHUNK_DAYS - 1)
    while cursor <= hi:
        chunk_hi = min(hi, (pd.Timestamp(cursor) + step).date())
        parts.append(_fetch_minute_span(client, cache_dir, ticker, cursor, chunk_hi))
        cursor = (pd.Timestamp(chunk_hi) + pd.Timedelta(days=1)).date()
    frame = (pd.concat(parts, ignore_index=True) if parts
             else _minute_frame([]))
    if not frame.empty:
        frame = (frame.drop_duplicates(subset="t", keep="last")
                 .sort_values("t").reset_index(drop=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return frame[list(MINUTE_COLUMNS)]


def minute_rows_for_session(frame: pd.DataFrame, session: date) -> list[list[Any]]:
    """Slice one ET session out of a minute window into ``challengers``' row shape.

    ``[iso_start, o, h, l, c, v]`` — exactly what ``four_hour.tape_from_rows``
    parses, so a vendor response and a committed fixture land in the same object.
    """
    if frame is None or frame.empty:
        return []
    stamps = pd.DatetimeIndex(frame["t"])
    if stamps.tz is None:
        stamps = stamps.tz_localize(ET)
    mask = stamps.normalize().date == session
    rows: list[list[Any]] = []
    for stamp, row in zip(stamps[mask], frame.loc[mask].itertuples(index=False)):
        rows.append([stamp.isoformat(), float(row.o), float(row.h), float(row.l),
                     float(row.c), float(row.v)])
    return rows


# --------------------------------------------------------------------------- #
# NBBO quotes  (§11 cost law)
# --------------------------------------------------------------------------- #
def _quote_cache_path(cache_dir: Path, ticker: str, ns: int) -> Path:
    return cache_dir / _QUOTE_DIR / f"{ticker}__{ns}.json"


def quotes_at(ticker: str, ts_utc: datetime | pd.Timestamp | str, *,
              cache_dir: str | Path) -> list[dict[str, Any]]:
    """The last <=50 NBBO quotes at or before ``ts_utc`` (§11 half-spread input).

    **NEVER RAISES.**  §11's cost law says a missing, invalid, or unentitled NBBO
    means the LIQUIDITY FLOOR binds — never zero cost — so the honest return on a
    403, a network fault, or an empty page is ``[]`` and the caller's floor does
    the rest.  Raising here would turn an entitlement fact into a run failure and
    tempt a caller into treating "no quotes" as "no spread".  (The prereg's §0(c)
    note records that v3/quotes DID answer under the estate key; the law is
    written to work under either entitlement state, which is why this is the one
    fetch in the module that degrades instead of refusing.)
    """
    try:
        cache_dir = _assert_cache_outside_repo(Path(cache_dir))
    except VendorError:
        raise
    stamp = pd.Timestamp(ts_utc)
    stamp = stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")
    ns = int(stamp.value)
    path = _quote_cache_path(cache_dir, ticker, ns)
    if path.exists():
        try:
            return list(json.loads(path.read_text(encoding="utf-8")) or [])
        except Exception:  # noqa: BLE001 — a torn cache is a miss, not a failure
            pass
    client = _client()
    if not client.online:
        return []
    try:
        results = _get_results(
            client, cache_dir, f"/v3/quotes/{ticker}",
            {"timestamp.lte": ns, "order": "desc", "limit": QUOTE_LIMIT,
             "sort": "timestamp"},
            ticker=ticker, kind="quotes")
    except Exception as exc:  # noqa: BLE001 — §11: the floor binds, never a crash
        _manifest_append(cache_dir, {
            "ticker": ticker, "kind": "quotes", "rows": 0,
            "url": f"{client.base}/v3/quotes/{ticker}?timestamp.lte={ns}",
            "error": repr(exc)})
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results), encoding="utf-8")
    return list(results)


def half_spread_bps(quotes: Iterable[dict[str, Any]]) -> float | None:
    """Median half-spread in bps over VALID quotes (bid > 0, ask > bid), else None.

    None means UNMEASURED — the caller's floor binds (§11).  Zero is never
    returned for an empty or invalid set.
    """
    values: list[float] = []
    for q in quotes or ():
        bid, ask = q.get("bid_price"), q.get("ask_price")
        try:
            bid, ask = float(bid), float(ask)
        except (TypeError, ValueError):
            continue
        if not (bid > 0 and ask > bid):
            continue
        mid = (ask + bid) / 2.0
        if mid <= 0:
            continue
        values.append((ask - bid) / 2.0 / mid * 1e4)
    if not values:
        return None
    return float(pd.Series(values).median())


# --------------------------------------------------------------------------- #
# reference shares outstanding  (§7 market-cap PIT proxy: shares × close[D])
# --------------------------------------------------------------------------- #
def shares_outstanding(ticker: str, *, cache_dir: str | Path) -> float | None:
    """Current split-consistent shares outstanding from the vendor reference
    endpoint (the §7 frozen cap proxy's shares leg).  Cached per ticker;
    ``None`` on any miss — an unknown cap maps to the "unknown" bucket, which
    the missing-control law then handles (never a fabricated cap)."""
    cache_dir = _assert_cache_outside_repo(Path(cache_dir))
    path = cache_dir / "reference" / f"{ticker}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            v = payload.get("share_class_shares_outstanding") or payload.get(
                "weighted_shares_outstanding")
            return float(v) if v else None
        except Exception:  # noqa: BLE001 — torn cache is a miss
            pass
    client = _client()
    if not client.online:
        return None
    try:
        resp = _http_get(client, f"{client.base}/v3/reference/tickers/{ticker}",
                         {"apiKey": client.key})
        payload = (resp.json() or {}).get("results") or {}
    except Exception as exc:  # noqa: BLE001 — a reference miss is not a run failure
        _manifest_append(cache_dir, {"ticker": ticker, "kind": "reference",
                                     "rows": 0, "error": repr(exc)})
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: payload.get(k) for k in ("ticker", "share_class_shares_outstanding",
                                        "weighted_shares_outstanding", "market_cap",
                                        "list_date")}
    path.write_text(json.dumps(keep), encoding="utf-8")
    _manifest_append(cache_dir, {"ticker": ticker, "kind": "reference", "rows": 1})
    v = keep.get("share_class_shares_outstanding") or keep.get(
        "weighted_shares_outstanding")
    return float(v) if v else None



def list_date(ticker: str, *, cache_dir: str | Path):
    """The vendor reference listing date (ISO string) or None — cached beside
    shares (same payload).  Drives the §3 grid-anchor recovery for names whose
    vendor daily history starts after their listing (the vendor's own data
    floor): phase = NYSE sessions between listing and first bar, mod 3."""
    cache_dir = _assert_cache_outside_repo(Path(cache_dir))
    path = cache_dir / "reference" / f"{ticker}.json"
    if not path.exists():
        shares_outstanding(ticker, cache_dir=cache_dir)  # populates the cache
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("list_date") or None
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "VendorError", "AGG_LIMIT", "DAILY_COLUMNS", "MINUTE_COLUMNS", "QUOTE_LIMIT",
    "daily_ohlcv", "minute_window", "minute_rows_for_session", "quotes_at",
    "half_spread_bps", "read_manifest", "shares_outstanding", "list_date",
]
