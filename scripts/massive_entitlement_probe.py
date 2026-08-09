#!/usr/bin/env python3
"""Vendor-entitlement probe for the Polygon.io / Massive (massive.com) market-data key.

WHY — the plan moved (stocks 15-min-delayed + options) -> (at least) stocks **Advanced**,
and every downstream design decision (real-time overlay, second bars, NBBO, tick history
depth, indices) hangs on what the key can ACTUALLY do.  A plan page is a claim; this probe
is the measurement.  It fires one small GET at each capability boundary, records
``{http_status, verdict, evidence}`` per endpoint, and writes a committed capability
manifest the integration masterplan can cite as verified fact instead of vendor marketing.

WHAT IT IS NOT — not a monitor, not a nightly step, not a data collector.  Run it by hand
after a plan change; commit the manifest; cite the manifest.  It fetches nothing but
1-row/1-day probes, so it costs ~35 REST calls and finishes in well under 90s.

VERDICTS (``verdict`` per probe)
  entitled      HTTP 200 — the endpoint answered for this key
  not_entitled  HTTP 403 (Polygon's NOT_AUTHORIZED) — the plan does not cover it
  ambiguous     404 (endpoint absent / renamed), 429 (throttled), other 4xx
  error         5xx, network/timeout failure, or 401 (a KEY problem, not a plan problem)

SECURITY (this repo is public — these are load-bearing, not decoration)
  * The key travels ONLY as an ``Authorization: Bearer`` header.  Never as an ``apiKey``
    query param: query strings end up inside ``requests`` exception messages, retry logs,
    and proxy access logs.
  * Every recorded error string is scrubbed — URLs collapse to ``<url>`` and any
    20+-char ``[A-Za-z0-9_]`` token collapses to ``<token>`` — BEFORE it can reach the
    manifest or stdout.
  * ``_assert_no_key_leak()`` re-reads the serialized manifest and refuses to write if any
    key material (or a 16-char fragment of it) survived.  Belt, braces, and a second belt.
  * ``evidence`` is a TINY extracted marker — a count, a boolean, a timestamp, a status
    word.  Never a raw response body: bodies carry entitlement-irrelevant PII-ish payloads
    and balloon the diff on every re-run.

Run:
    python3 scripts/massive_entitlement_probe.py --out data/massive/capability_manifest.json
    python3 scripts/massive_entitlement_probe.py --skip-ws --strict

Tests: tests/test_massive_entitlement_probe.py (no network — the HTTP layer is stubbed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

SCHEMA = "massive_capability_manifest.v1"
DEFAULT_OUT = "data/massive/capability_manifest.json"
DEFAULT_BASE_URL = "https://api.polygon.io"
DEFAULT_KEY_ENVS = ("POLYGON_API_KEY", "MASSIVE_API_KEY")
USER_AGENT = "macro-dashboard-entitlement-probe/1"

# Probe symbols.  AAPL because every US-equity plan tier carries it; SPY options because
# the chain is the densest public one; I:SPX because index entitlement is a separate SKU.
SYM = "AAPL"
OPT_REF_CONTRACT = "O:SPY251219C00650000"
INDEX_SYM = "I:SPX"

# --- scrubbing -------------------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s'\"<>]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{20,}")
_ERR_MAX = 200

# NYSE full closures.  Only used to keep the "previous business day" probe date off a
# holiday, where an empty aggregate would read as a capability signal instead of a calendar
# one.  Coarse by design — a missed holiday costs one ambiguous evidence count, nothing more.
_MARKET_HOLIDAYS = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def _scrub(text: Any, secrets: tuple[str, ...] = ()) -> str:
    """Make an error MESSAGE safe to record: no URLs, no long tokens, no key material."""
    s = str(text)
    for sec in secrets:
        if sec:
            s = s.replace(sec, "<redacted>")
    s = _URL_RE.sub("<url>", s)
    s = _TOKEN_RE.sub("<token>", s)
    return s[:_ERR_MAX]


def _err(exc: BaseException, secrets: tuple[str, ...] = ()) -> str:
    """``ClassName: <scrubbed message>``.

    The class name is kept VERBATIM and deliberately routed around ``_scrub``: it is a
    Python identifier from our own dependency tree, never key material, and the token
    regex would otherwise eat any name >=20 chars — a live run recorded
    ``ConnectionClosedError`` as ``<token>``, deleting the only diagnostic in the record.
    """
    return f"{type(exc).__name__}: {_scrub(exc, secrets)}"


def _assert_no_key_leak(manifest_text: str, key: str | None) -> None:
    """Final gate before the manifest touches disk.  Raises if key material survived.

    Checks the resolved key AND whatever the key env vars currently hold (a probe run with
    ``--key-env`` pointed at one alias must not leak the other), plus 16-char fragments —
    a truncated key is still key material.  The exception message never quotes the value.
    """
    secrets = {s for s in (key,) if s}
    for name in DEFAULT_KEY_ENVS:
        v = (os.environ.get(name) or "").strip()
        if v:
            secrets.add(v)
    if not secrets:
        return
    tokens = set(_TOKEN_RE.findall(manifest_text))
    for sec in secrets:
        if sec in manifest_text:
            raise RuntimeError("key material found in manifest — refusing to write")
        if len(sec) >= 16 and (sec[:16] in manifest_text or sec[-16:] in manifest_text):
            raise RuntimeError("key fragment found in manifest — refusing to write")
        for tok in tokens:
            if tok == sec or (len(tok) >= 24 and (tok in sec or sec in tok)):
                raise RuntimeError("key-like token found in manifest — refusing to write")


# --- verdicts --------------------------------------------------------------------------
def verdict_for_status(status: int) -> str:
    """HTTP status -> entitlement verdict.  401 is an ``error`` (bad/missing key), NOT
    ``not_entitled``: conflating the two would report a typo'd key as a downgraded plan."""
    if status == 200:
        return "entitled"
    if status == 401:
        return "error"
    if status == 403:
        return "not_entitled"
    if 500 <= status < 600:
        return "error"
    if 400 <= status < 500:      # 404 endpoint-absent, 429 throttled, 422 bad probe args
        return "ambiguous"
    return "ambiguous"


def previous_business_day(today: date | None = None) -> str:
    """Latest weekday strictly before ``today`` that is not a known NYSE full closure."""
    d = (today or datetime.now(timezone.utc).date()) - timedelta(days=1)
    for _ in range(12):
        if d.weekday() < 5 and d.isoformat() not in _MARKET_HOLIDAYS:
            return d.isoformat()
        d -= timedelta(days=1)
    return d.isoformat()


# --- evidence extractors ---------------------------------------------------------------
# Each takes the parsed payload and returns a TINY dict of markers.  Never a body slice.
def _count(payload: Any) -> int | None:
    """Row count across Polygon's THREE result envelopes.

    ``results`` (v3 + most of v2), ``tickers`` (the v2 snapshot family), and a bare
    ``resultsCount``/``count``.  The snapshot shape is easy to miss: a live run recorded
    entitled snapshots as ``non_empty: false`` purely because they answer under
    ``tickers``, which reads like a capability gap instead of an extractor gap.
    """
    if isinstance(payload, dict):
        for field in ("results", "tickers"):
            r = payload.get(field)
            if isinstance(r, list):
                return len(r)
            if isinstance(r, dict):
                return 1
        for field in ("resultsCount", "count"):
            rc = payload.get(field)
            if isinstance(rc, int):
                return rc
    return None


def _ev_results(payload: Any) -> dict:
    n = _count(payload)
    return {"results_count": n, "non_empty": bool(n)}


def _ev_aggs(payload: Any) -> dict:
    rc = payload.get("resultsCount") if isinstance(payload, dict) else None
    if rc is None:
        rc = _count(payload)
    return {"results_count": rc, "non_empty": bool(rc)}


def _ev_market_status(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        "market": payload.get("market"),
        "after_hours": bool(payload.get("afterHours")),
        "early_hours": bool(payload.get("earlyHours")),
        "server_time_present": bool(payload.get("serverTime")),
    }


def _ev_last_trade(payload: Any) -> dict:
    res = (payload or {}).get("results") if isinstance(payload, dict) else None
    if not isinstance(res, dict):
        return {"has_result": False}
    ns = res.get("participant_timestamp") or res.get("sip_timestamp") or res.get("t")
    return {"has_result": True, "price_present": res.get("p") is not None,
            "timestamp_ns_present": ns is not None, "timestamp_utc": _ns_to_iso(ns)}


def _ev_last_nbbo(payload: Any) -> dict:
    res = (payload or {}).get("results") if isinstance(payload, dict) else None
    if not isinstance(res, dict):
        return {"has_result": False}
    ns = res.get("sip_timestamp") or res.get("t")
    # Polygon v2 last-NBBO: lowercase p/s = BID price/size, uppercase P/S = ASK.
    return {"has_result": True,
            "bid_present": (res.get("p") if "p" in res else res.get("bid_price")) is not None,
            "ask_present": (res.get("P") if "P" in res else res.get("ask_price")) is not None,
            "timestamp_utc": _ns_to_iso(ns)}


def _ev_exchanges(payload: Any) -> dict:
    """The FINRA/TRF mapping matters downstream: exchange id 4 is the off-exchange print
    venue, so its presence + name decides whether we can split lit vs dark volume."""
    res = (payload or {}).get("results") if isinstance(payload, dict) else None
    rows = res if isinstance(res, list) else []
    hit = next((r for r in rows if isinstance(r, dict) and r.get("id") == 4), None)
    return {"count": len(rows), "exchange_id_4_present": hit is not None,
            "exchange_id_4_name": (hit or {}).get("name")}


def _ev_options_chain(payload: Any) -> dict:
    res = (payload or {}).get("results") if isinstance(payload, dict) else None
    rows = res if isinstance(res, list) else []
    first = rows[0] if rows and isinstance(rows[0], dict) else {}
    greeks = first.get("greeks") if isinstance(first.get("greeks"), dict) else {}
    return {
        "results_count": len(rows),
        "has_greeks": bool(greeks),
        "has_delta": greeks.get("delta") is not None,
        "has_implied_volatility": first.get("implied_volatility") is not None,
        "has_open_interest": first.get("open_interest") is not None,
        "has_last_quote": isinstance(first.get("last_quote"), dict),
        "has_last_trade": isinstance(first.get("last_trade"), dict),
    }


def _ns_to_iso(ns: Any) -> str | None:
    """Nanosecond epoch -> ISO-8601 Z.  A timestamp IS the real-time tell: a delayed plan
    that answers 200 still hands back a stamp ~15 minutes behind the wall clock."""
    try:
        v = int(ns)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 1e17:            # nanoseconds
        v = v / 1e9
    elif v > 1e14:          # microseconds
        v = v / 1e6
    elif v > 1e11:          # milliseconds
        v = v / 1e3
    try:
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


# --- REST probe engine -----------------------------------------------------------------
class RestProber:
    """One GET per probe, one retry on 5xx/timeout, ``{http_status, verdict, evidence}`` out.

    The key rides an ``Authorization: Bearer`` header set once on the session — no probe
    can accidentally put it in a query string, because no probe ever sees it.
    """

    def __init__(self, key: str | None, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 15.0, session: Any = None) -> None:
        self.key = key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        self.session = session if session is not None else requests.Session()
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            self.session.headers.update(headers)
        except AttributeError:              # a bare stub without .headers is fine
            pass
        self.results: dict[str, dict] = {}

    # -- internals
    def _secrets(self) -> tuple[str, ...]:
        return tuple(s for s in (self.key,) if s)

    def _request(self, path: str, params: dict | None) -> tuple[Any, dict]:
        rec: dict[str, Any] = {"http_status": None, "verdict": "error", "evidence": {}}
        payload: Any = None
        for attempt in (0, 1):                      # one GET, one retry on 5xx/timeout
            try:
                resp = self.session.get(self.base_url + path, params=params or None,
                                        timeout=self.timeout)
            except Exception as exc:                # requests embeds the URL — scrub it
                rec["evidence"]["error"] = _err(exc, self._secrets())
                if attempt == 0:
                    continue
                rec["verdict"] = "error"
                return None, rec
            status = int(getattr(resp, "status_code", 0) or 0)
            rec["http_status"] = status
            if 500 <= status < 600 and attempt == 0:
                continue
            rec["verdict"] = verdict_for_status(status)
            try:
                payload = resp.json()
            except Exception:
                payload = None
            rec["evidence"].pop("error", None)      # a retried-away 5xx is not an error
            break
        # Polygon also declares refusal in the BODY on some paths; honor it over the code.
        if isinstance(payload, dict):
            st = str(payload.get("status") or "").upper()
            if st == "NOT_AUTHORIZED":
                rec["verdict"] = "not_entitled"
                rec["evidence"]["body_status"] = "NOT_AUTHORIZED"
            elif st in ("ERROR", "NOT_FOUND"):
                rec["evidence"]["body_status"] = st
        return payload, rec

    def probe(self, name: str, path: str, params: dict | None = None,
              evidence: Callable[[Any], dict] | None = None) -> Any:
        """Run one probe, store its record under ``name``, return the parsed payload."""
        payload, rec = self._request(path, params)
        if evidence is not None and payload is not None:
            try:
                extra = evidence(payload) or {}
                if isinstance(extra, dict):
                    rec["evidence"].update(extra)
            except Exception as exc:
                rec["evidence"]["evidence_error"] = _err(exc, self._secrets())
        self.results[name] = rec
        return payload


def run_rest_battery(prober: RestProber, probe_day: str | None = None) -> dict[str, dict]:
    """Fire the whole REST battery.  Order is cheap-to-expensive so a throttled key still
    yields the load-bearing tells (real-time trades/quotes) before anything gets dropped."""
    day = probe_day or previous_business_day()
    p = prober.probe

    # -- calendar / plumbing (also proves the auth header itself works)
    p("market_status", "/v1/marketstatus/now", evidence=_ev_market_status)
    p("market_holidays", "/v1/marketstatus/upcoming",
      evidence=lambda pl: {"count": len(pl) if isinstance(pl, list) else _count(pl)})

    # -- the real-time tells.  Delayed plans answer 403 NOT_AUTHORIZED here.
    p("last_trade", f"/v2/last/trade/{SYM}", evidence=_ev_last_trade)
    p("last_nbbo", f"/v2/last/nbbo/{SYM}", evidence=_ev_last_nbbo)

    # -- bar granularity.  Second aggregates are the Advanced-tier tell.
    p("aggs_minute", f"/v2/aggs/ticker/{SYM}/range/1/minute/{day}/{day}", evidence=_ev_aggs)
    p("aggs_second", f"/v2/aggs/ticker/{SYM}/range/1/second/{day}/{day}",
      params={"limit": 50}, evidence=_ev_aggs)
    p("aggs_grouped_daily", f"/v2/aggs/grouped/locale/us/market/stocks/{day}",
      evidence=_ev_aggs)

    # -- tick history + its depth matrix (verdict AND non-emptiness both matter)
    p("trades_recent", f"/v3/trades/{SYM}", params={"limit": 1}, evidence=_ev_results)
    p("trades_2015", f"/v3/trades/{SYM}", params={"limit": 1, "timestamp": "2015-06-15"},
      evidence=_ev_results)
    p("trades_2005", f"/v3/trades/{SYM}", params={"limit": 1, "timestamp": "2005-06-15"},
      evidence=_ev_results)
    p("quotes_recent", f"/v3/quotes/{SYM}", params={"limit": 1}, evidence=_ev_results)

    # -- snapshots
    p("snapshot_ticker", "/v2/snapshot/locale/us/markets/stocks/tickers",
      params={"tickers": SYM}, evidence=_ev_results)
    p("snapshot_gainers", "/v2/snapshot/locale/us/markets/stocks/gainers",
      evidence=_ev_results)
    p("snapshot_unified", "/v3/snapshot", params={"ticker.any_of": SYM},
      evidence=_ev_results)

    # -- reference data
    p("ref_exchanges", "/v3/reference/exchanges", params={"asset_class": "stocks"},
      evidence=_ev_exchanges)
    p("ref_conditions", "/v3/reference/conditions",
      params={"asset_class": "stocks", "limit": 1000},
      evidence=lambda pl: {"count": _count(pl)})
    p("ref_splits", "/v3/reference/splits", params={"limit": 1}, evidence=_ev_results)
    p("ref_dividends", "/v3/reference/dividends", params={"limit": 1}, evidence=_ev_results)
    p("ref_financials", "/vX/reference/financials", params={"limit": 1},
      evidence=_ev_results)

    # -- short interest / volume (404 vs 403 distinguishes "moved" from "not on plan")
    p("short_interest_stocks_v1", "/stocks/v1/short-interest", params={"limit": 1},
      evidence=_ev_results)
    p("short_interest_legacy", "/v1/reference/short-interest", params={"limit": 1},
      evidence=_ev_results)
    p("short_volume", "/stocks/v1/short-volume", params={"limit": 1}, evidence=_ev_results)

    # -- news / vendor add-ons
    p("news", "/v2/reference/news", params={"limit": 1}, evidence=_ev_results)
    p("benzinga_ratings", "/benzinga/v1/ratings", params={"limit": 1}, evidence=_ev_results)
    p("benzinga_earnings", "/benzinga/v1/earnings", params={"limit": 1},
      evidence=_ev_results)
    p("treasury_yields", "/fed/v1/treasury-yields", params={"limit": 1},
      evidence=_ev_results)

    # -- options
    contracts = p("options_contracts", "/v3/reference/options/contracts",
                  params={"limit": 1}, evidence=_ev_results)
    p("options_chain_snapshot", f"/v3/snapshot/options/{SYM}", params={"limit": 5},
      evidence=_ev_options_chain)
    p("options_trades", f"/v3/trades/{OPT_REF_CONTRACT}", params={"limit": 1},
      evidence=_ev_results)
    prober.results["options_trades"]["evidence"]["contract_source"] = "reference"
    if prober.results["options_trades"].get("http_status") == 404:
        alt = _first_contract_ticker(contracts)
        if alt:
            p("options_trades", f"/v3/trades/{alt}", params={"limit": 1},
              evidence=_ev_results)
            prober.results["options_trades"]["evidence"]["contract_source"] = "fallback"

    # -- other asset classes (record-only tells)
    p("indices_snapshot", "/v3/snapshot/indices", params={"ticker.any_of": INDEX_SYM},
      evidence=_ev_results)
    p("fx_prev", "/v2/aggs/ticker/C:EURUSD/prev", evidence=_ev_aggs)
    p("crypto_prev", "/v2/aggs/ticker/X:BTCUSD/prev", evidence=_ev_aggs)

    return prober.results


def _first_contract_ticker(payload: Any) -> str | None:
    res = (payload or {}).get("results") if isinstance(payload, dict) else None
    if isinstance(res, list) and res and isinstance(res[0], dict):
        t = res[0].get("ticker")
        return t if isinstance(t, str) and t.startswith("O:") else None
    return None


# --- WebSocket probes ------------------------------------------------------------------
WS_CLUSTERS = (
    ("ws_stocks_realtime", "wss://socket.polygon.io/stocks", "T.AAPL,Q.AAPL"),
    ("ws_stocks_delayed", "wss://delayed.polygon.io/stocks", "T.AAPL"),
    ("ws_options", "wss://socket.polygon.io/options", "T.O:SPY*"),
    ("ws_indices", "wss://socket.polygon.io/indices", "V.I:SPX"),
)


def _ws_lib() -> tuple[str | None, Any]:
    """Return whichever WS client is ALREADY importable.  Never installs anything."""
    try:
        import websockets.sync.client as _wsc     # websockets >= 13 sync API
        return "websockets", _wsc
    except Exception:
        pass
    try:
        import websocket as _wsclient             # websocket-client
        return "websocket-client", _wsclient
    except Exception:
        return None, None


class _WSAdapter:
    """One tiny surface over the two client libs: send / recv(timeout) / close."""

    def __init__(self, kind: str, conn: Any) -> None:
        self.kind = kind
        self.conn = conn

    def send(self, text: str) -> None:
        self.conn.send(text)

    def recv(self, timeout: float) -> str:
        if self.kind == "websockets":
            return self.conn.recv(timeout=timeout)
        self.conn.settimeout(timeout)
        return self.conn.recv()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def _ws_connect(kind: str, lib: Any, url: str, timeout: float) -> _WSAdapter:
    if kind == "websockets":
        return _WSAdapter(kind, lib.connect(url, open_timeout=timeout, close_timeout=2))
    return _WSAdapter(kind, lib.create_connection(url, timeout=timeout))


def _is_timeout(exc: BaseException) -> bool:
    return "timeout" in type(exc).__name__.lower() or isinstance(exc, TimeoutError)


def _handshake_status(exc: BaseException) -> int | None:
    """HTTP status of a rejected WS upgrade, if the client lib exposed one.

    A non-entitled cluster often refuses at the HANDSHAKE (403) rather than at auth, so
    without this the strongest entitlement answer would be filed as a transport error.
    ``websockets`` carries it on ``exc.response.status_code``; ``websocket-client`` puts
    it on ``exc.status_code``.
    """
    for obj, attr in ((getattr(exc, "response", None), "status_code"), (exc, "status_code")):
        val = getattr(obj, attr, None)
        if isinstance(val, int):
            return val
    return None


def _close_code(exc: BaseException) -> int | None:
    """WebSocket close code of a server-initiated close, if the lib exposed one.

    ``websockets`` hangs it off ``exc.rcvd.code``; ``websocket-client`` uses
    ``exc.status_code``.  1008 (policy violation) is the one that matters here — see the
    verdict note in ``probe_ws``.
    """
    for obj, attr in ((getattr(exc, "rcvd", None), "code"), (exc, "code"),
                      (exc, "status_code")):
        val = getattr(obj, attr, None)
        if isinstance(val, int) and 1000 <= val < 5000:
            return val
    return None


def _ws_frames(raw: Any) -> list[dict]:
    try:
        obj = json.loads(raw)
    except Exception:
        return []
    if isinstance(obj, dict):
        obj = [obj]
    return [f for f in obj if isinstance(f, dict)]


def probe_ws(url: str, sub: str, key: str | None, *, timeout: float = 10.0,
             data_wait_s: float = 8.0, lib_pair: tuple[str | None, Any] | None = None,
             now: Callable[[], float] | None = None) -> dict:
    """Connect, auth, subscribe, listen briefly.  AUTH is the entitlement verdict; a data
    frame is informational only — outside RTH an entitled cluster is legitimately silent."""
    import time as _time
    clock = now or _time.monotonic
    kind, lib = lib_pair if lib_pair is not None else _ws_lib()
    rec: dict[str, Any] = {"http_status": None, "verdict": "error", "evidence": {}}
    if not kind:
        rec["verdict"] = "ambiguous"
        rec["evidence"] = {"status": "skipped_no_lib"}
        return rec
    ev: dict[str, Any] = {"lib": kind, "connected": False, "auth_status": None,
                          "subscribe_status": None, "data_frames": 0}
    rec["evidence"] = ev
    conn: _WSAdapter | None = None
    secrets = tuple(s for s in (key,) if s)
    try:
        conn = _ws_connect(kind, lib, url, timeout)
        ev["connected"] = True
        conn.send(json.dumps({"action": "auth", "params": key or ""}))
        deadline = clock() + min(timeout, 8.0)
        while ev["auth_status"] is None and clock() < deadline:
            try:
                for f in _ws_frames(conn.recv(2.0)):
                    st = str(f.get("status") or "")
                    if st in ("auth_success", "auth_failed", "auth_timeout", "error"):
                        ev["auth_status"] = st
                        break
            except Exception as exc:
                if not _is_timeout(exc):
                    raise
                break
        if ev["auth_status"] == "auth_success":
            conn.send(json.dumps({"action": "subscribe", "params": sub}))
            deadline = clock() + data_wait_s
            while clock() < deadline:
                try:
                    frames = conn.recv(min(2.0, data_wait_s))
                except Exception as exc:
                    if _is_timeout(exc):
                        continue
                    raise
                for f in _ws_frames(frames):
                    if f.get("ev") == "status":
                        ev["subscribe_status"] = str(f.get("status") or "")
                    else:
                        ev["data_frames"] = int(ev["data_frames"]) + 1
                if ev["data_frames"]:
                    break
    except Exception as exc:
        ev["error"] = _err(exc, secrets)
        hs = _handshake_status(exc)
        if hs is not None:
            ev["handshake_status"] = hs
        cc = _close_code(exc)
        if cc is not None:
            ev["close_code"] = cc
    finally:
        if conn is not None:
            conn.close()

    if ev.get("handshake_status") in (401, 403):
        # The cluster refused the upgrade outright — that IS the entitlement answer.
        rec["verdict"] = "not_entitled"
        return rec

    auth = ev.get("auth_status")
    if auth == "auth_success" and ev.get("close_code") == 1008 \
            and ev.get("subscribe_status") != "success":
        # Authenticated, then closed on POLICY VIOLATION before the subscribe was acked.
        # 1008 is Polygon's concurrent-connection ceiling as often as it is an entitlement
        # refusal, and this probe opens four sockets back-to-back — so it is genuinely
        # undecided, not a "no".  Recording it as not_entitled would publish a false gap.
        rec["verdict"] = "ambiguous"
    elif auth == "auth_success":
        rec["verdict"] = "not_entitled" if ev.get("subscribe_status") == "error" else "entitled"
    elif auth in ("auth_failed", "auth_timeout"):
        rec["verdict"] = "not_entitled"
    elif auth == "error":
        rec["verdict"] = "not_entitled"
    elif ev.get("error"):
        rec["verdict"] = "error"
    else:
        rec["verdict"] = "ambiguous"
    return rec


def run_ws_battery(key: str | None, timeout: float = 10.0, data_wait_s: float = 8.0,
                   settle_s: float = 1.5) -> dict[str, dict]:
    """Probe each cluster in turn, pausing between them.

    The pause is load-bearing, not politeness: Polygon caps concurrent connections per
    plan and closes the newcomer with 1008.  Four sockets opened back-to-back trip that
    ceiling and the result reads like an entitlement gap (measured on the first live run).
    """
    import time as _time
    pair = _ws_lib()
    out: dict[str, dict] = {}
    for i, (name, url, sub) in enumerate(WS_CLUSTERS):
        if i and settle_s:
            _time.sleep(settle_s)
        out[name] = probe_ws(url, sub, key, timeout=timeout, data_wait_s=data_wait_s,
                             lib_pair=pair)
    return out


# --- derivation ------------------------------------------------------------------------
def _v(block: dict, name: str) -> str | None:
    rec = block.get(name)
    return rec.get("verdict") if isinstance(rec, dict) else None


def _entitled(block: dict, name: str) -> bool | None:
    """True/False only on a decisive verdict; None when the probe could not decide."""
    v = _v(block, name)
    if v == "entitled":
        return True
    if v == "not_entitled":
        return False
    return None


def _non_empty(block: dict, name: str) -> bool:
    rec = block.get(name) or {}
    return bool((rec.get("evidence") or {}).get("non_empty"))


def derive(rest: dict, ws: dict) -> dict:
    """Turn per-probe verdicts into the handful of facts downstream design actually asks."""
    notes: list[str] = []

    rt_trades = _entitled(rest, "last_trade")
    rt_quotes = _entitled(rest, "last_nbbo")
    sec_aggs = _entitled(rest, "aggs_second")
    if sec_aggs and not _non_empty(rest, "aggs_second"):
        notes.append("aggs_second answered 200 but returned no bars — entitlement yes, "
                     "coverage unverified (probe day may be thin).")

    # Depth ladder: each probe asks for ONE trade on a date N years back.  A plan whose
    # history window excludes that date answers 403; a plan that includes it returns a row.
    if _v(rest, "trades_2005") == "entitled" and _non_empty(rest, "trades_2005"):
        depth = "20y+"
    elif _v(rest, "trades_2015") == "entitled" and _non_empty(rest, "trades_2015"):
        depth = "10y"
    elif _v(rest, "trades_recent") == "entitled" and _non_empty(rest, "trades_recent"):
        depth = "5y"
    elif _v(rest, "trades_recent") == "not_entitled":
        depth = "shallow"
    else:
        depth = "unknown"
    notes.append("tick_history_depth ladder: 2005 probe -> 20y+, 2015 probe -> 10y, "
                 "recent-only -> 5y, /v3/trades refused -> shallow.")

    opts = _entitled(rest, "options_chain_snapshot")
    if opts is None:
        opts = _entitled(rest, "options_contracts")
    opts_rt = _entitled(ws, "ws_options")
    if opts_rt is None and ws:
        notes.append("options_realtime is WS-derived; a REST-only run cannot separate "
                     "real-time from delayed options.")

    idx = _entitled(rest, "indices_snapshot")
    if idx is None:
        idx = _entitled(ws, "ws_indices")

    ws_rt = _entitled(ws, "ws_stocks_realtime")
    if ws_rt is not None and rt_trades is not None and ws_rt != rt_trades:
        notes.append("REST real-time trades and the real-time WS cluster disagree — "
                     "the WS auth result is the stronger entitlement signal.")

    return {
        "realtime_trades": rt_trades,
        "realtime_quotes": rt_quotes,
        "second_aggs": sec_aggs,
        "tick_history_depth": depth,
        "options_entitled": opts,
        "options_realtime": opts_rt,
        "indices_entitled": idx,
        "plan_guess": _plan_guess(rt_trades, rt_quotes, sec_aggs, depth, opts, idx),
        "notes": notes,
    }


def _plan_guess(rt_trades: bool | None, rt_quotes: bool | None, sec_aggs: bool | None,
                depth: str, opts: bool | None, idx: bool | None) -> str:
    if rt_trades and rt_quotes:
        stocks = "advanced_or_higher (real-time trades + NBBO quotes)"
    elif rt_trades and rt_quotes is False:
        stocks = "starter_or_developer (real-time trades, no NBBO)"
    elif rt_trades is False:
        stocks = "basic_or_delayed (no real-time trades)"
    else:
        stocks = "unknown"
    bits = [f"stocks: {stocks}", f"tick_history: {depth}",
            f"second_aggs: {_word(sec_aggs)}", f"options: {_word(opts)}",
            f"indices: {_word(idx)}"]
    return "; ".join(bits)


def _word(flag: bool | None) -> str:
    return "unknown" if flag is None else ("entitled" if flag else "not_entitled")


# --- manifest --------------------------------------------------------------------------
def build_manifest(key_source: str, base_url: str, rest: dict, ws: dict,
                   probed_at: str | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "probed_at_utc": probed_at or datetime.now(timezone.utc)
                                             .isoformat(timespec="seconds")
                                             .replace("+00:00", "Z"),
        "key_source": key_source,
        "base_url": base_url,
        "rest": rest,
        "ws": ws,
        "derived": derive(rest, ws),
    }


def serialize(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_manifest(manifest: dict, out_path: Path, key: str | None) -> str:
    text = serialize(manifest)
    _assert_no_key_leak(text, key)          # last gate before disk
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text


def resolve_key(key_env: str | None) -> tuple[str | None, str]:
    """Return (key, LABEL).  LABEL is the env var NAME — never the value."""
    names = (key_env,) if key_env else DEFAULT_KEY_ENVS
    for name in names:
        if not name:
            continue
        try:
            from lib import config                       # repo-standard secret read
            val = config.secret(name)
        except Exception:
            val = (os.environ.get(name) or "").strip() or None
        if val:
            return val, name
    return None, "none"


def _base_url() -> str:
    try:
        from lib import config
        cfg = (config.load() or {}).get("polygon") or {}
        return str(cfg.get("base_url") or DEFAULT_BASE_URL)
    except Exception:
        return DEFAULT_BASE_URL


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"manifest path (default {DEFAULT_OUT})")
    ap.add_argument("--key-env", default=None,
                    help="env var holding the key (default: POLYGON_API_KEY then MASSIVE_API_KEY)")
    ap.add_argument("--skip-ws", action="store_true", help="REST battery only")
    ap.add_argument("--timeout", type=float, default=15.0, help="per-request timeout (s)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any probe errored")
    args = ap.parse_args(argv)

    key, label = resolve_key(args.key_env)
    if not key:
        # Bare print at line start — a logger would prefix it and GitHub would drop it.
        print("::warning title=massive-entitlement-probe::no vendor key in env; "
              "no manifest written", flush=True)
        print("no key found in env — set POLYGON_API_KEY (or MASSIVE_API_KEY)")
        return 1 if args.strict else 0

    base = _base_url()
    prober = RestProber(key, base_url=base, timeout=args.timeout)
    rest = run_rest_battery(prober)
    ws: dict[str, dict] = {}
    if not args.skip_ws:
        ws = run_ws_battery(key, timeout=min(args.timeout, 10.0))

    manifest = build_manifest(label, base, rest, ws)
    out = Path(args.out)
    write_manifest(manifest, out, key)

    for name, rec in list(rest.items()) + list(ws.items()):
        print(f"{name:26s} {str(rec.get('http_status') or '-'):>4s}  {rec['verdict']}")
    print(f"\nmanifest -> {out}")
    print(json.dumps(manifest["derived"], indent=2, sort_keys=True))

    errored = [n for n, r in list(rest.items()) + list(ws.items()) if r["verdict"] == "error"]
    if errored:
        print(f"probes reporting error: {', '.join(sorted(errored))}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
