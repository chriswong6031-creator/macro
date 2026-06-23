"""Same-origin live-quotes micro-service — the China-reachable alternative to the
Cloudflare Worker (``worker/quotes.worker.js``).

The Worker is the default browser quote source, but Cloudflare is unreliable from
mainland China (the GFW blocks ECH to Cloudflare + ``workers.dev``). When the
dashboard is served from a Hong Kong origin, run this tiny stdlib HTTP server
behind nginx at the SAME origin and point ``config.yml`` ``live.quotes_worker_url``
at that origin — ``site/live.js`` then polls ``<origin>/quotes`` with no Cloudflare
dependency and no code change.

It mirrors the Worker's wire contract EXACTLY and reuses the Python
``engine.live_quotes`` routing (Polygon US -> Yahoo for the rest), so the website
and the bot agree to the last digit.

  GET /quotes?symbols=AAPL,0700.HK,GC=F
    -> {"ts": <ms>, "quotes": {"AAPL": {price, ts, source, basis, prevClose}, ...}}
  GET /health -> {"ok": true}

Run:    python -m scripts.quotes_server --host 127.0.0.1 --port 8787
nginx:  location /quotes { proxy_pass http://127.0.0.1:8787; }
        location /health { proxy_pass http://127.0.0.1:8787; }   # optional

No new dependencies (stdlib ``http.server`` + ``engine.live_quotes``, which the
overlay already uses). Low-traffic, latency-tolerant by design.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import live_quotes

log = logging.getLogger("quotes_server")

# Mirror the Worker: charset for ^VIX, GC=F, 0700.HK, BRK-B; cap + cache window.
_SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.=^-]{0,15}$")
_MAX_SYMBOLS = 200
_CACHE_SEC = 60                      # matches live.poll_seconds + the Worker's CACHE_SEC
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


# ------------------------------------------------------- pure transforms ----

def canonical_symbols(raw: str | None) -> list[str]:
    """Upper, charset-validated, de-duped, SORTED, capped — identical to the Worker
    so the cache key can't be fragmented by order / whitespace / dupes."""
    if not raw:
        return []
    out: list[str] = []
    for s in raw.split(","):
        s = s.strip().upper()
        if s and _SYMBOL_RE.match(s) and s not in out:
            out.append(s)
    return sorted(out)[:_MAX_SYMBOLS]


def _ts_ms(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return None


def to_worker_quotes(fetched: dict) -> dict:
    """Map ``engine.live_quotes`` records -> the Worker / live.js wire shape
    ({price, ts(ms), source, basis, prevClose})."""
    out: dict = {}
    for sym, q in (fetched or {}).items():
        if not q or q.get("price") is None:
            continue
        out[sym] = {
            "price": q.get("price"),
            "ts": _ts_ms(q.get("quote_ts")),
            "source": q.get("source"),
            "basis": q.get("price_basis"),
            "prevClose": q.get("prev_close"),
        }
    return out


def build_payload(symbols: list[str], *, fetcher=live_quotes.fetch_quotes, now_ms: int | None = None) -> dict:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    fetched = fetcher(symbols) if symbols else {}
    return {"ts": now_ms, "quotes": to_worker_quotes(fetched)}


class QuoteCache:
    """TTL cache keyed by the canonical symbol set — a fan of browsers polling the
    same set costs one upstream fetch per window."""

    def __init__(self, ttl: float = _CACHE_SEC, clock=time.time):
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, dict]] = {}

    def get(self, key: str):
        with self._lock:
            hit = self._store.get(key)
            if hit and (self._clock() - hit[0]) < self._ttl:
                return hit[1]
        return None

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._store[key] = (self._clock(), value)


# --------------------------------------------------------------- server ----

_CACHE = QuoteCache()


class _Handler(BaseHTTPRequestHandler):
    server_version = "quotes/1.0"
    fetcher = staticmethod(live_quotes.fetch_quotes)   # overridable in tests

    def _send(self, obj: dict, status: int = 200, extra: dict | None = None) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in {**_CORS, **(extra or {})}.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:       # CORS preflight
        self.send_response(204)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/health":
            return self._send({"ok": True})
        if u.path != "/quotes":
            return self._send({"error": "not found"}, status=404)
        symbols = canonical_symbols((parse_qs(u.query).get("symbols") or [""])[0])
        if not symbols:
            return self._send({"ts": int(time.time() * 1000), "quotes": {}})
        key = ",".join(symbols)
        cached = _CACHE.get(key)
        cache_hdr = {"Cache-Control": f"public, max-age={_CACHE_SEC}"}
        if cached is not None:
            return self._send(cached, extra=cache_hdr)
        try:
            payload = build_payload(symbols, fetcher=type(self).fetcher)
        except Exception as e:  # noqa: BLE001 — never 500 the dashboard
            log.warning("quotes fetch failed: %s", e)
            return self._send({"ts": int(time.time() * 1000), "quotes": {}})
        _CACHE.put(key, payload)
        return self._send(payload, extra=cache_hdr)

    def log_message(self, *a) -> None:  # quiet; nginx logs the access line
        pass


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    log.info("quotes_server on http://%s:%d  (GET /quotes, /health)", args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
