"""Verify a deployed live-quotes Cloudflare Worker before turning the intraday layer on.

Run this with your worker URL after `wrangler deploy` to confirm the endpoint is reachable,
CORS-enabled, key-wired, and returns the quote contract the browser live.js + engine.live_quotes
expect — so you turn the live layer on with confidence, not hope.

    python -m scripts.check_live_worker https://macro-quotes.<sub>.workers.dev
    # or, if LIVE_QUOTES_WORKER_URL / config.yml live.quotes_worker_url is set:
    python -m scripts.check_live_worker

Exit 0 = healthy and serving valid quotes; exit 1 = a problem (printed). No project deps beyond
requests; safe to run locally.
"""
from __future__ import annotations

import sys

_PROBE = ["AAPL", "SPY", "0700.HK", "GC=F"]      # US (Polygon) + HK + future (Yahoo) routing
_BASES = {"trade", "minute", "day", "prev", "regular"}


def _resolve(argv) -> str | None:
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip().rstrip("/")
    try:
        sys.path.insert(0, ".")
        from scripts.build_live_overlay import resolve_worker_url
        return resolve_worker_url() or None
    except Exception:  # noqa: BLE001
        return None


def main(argv=None) -> int:
    import requests
    argv = argv if argv is not None else sys.argv
    url = _resolve(argv)
    if not url:
        print("✗ no worker URL — pass it as an argument or set LIVE_QUOTES_WORKER_URL / "
              "config.yml live.quotes_worker_url")
        return 1
    if not url.startswith("https://"):
        print(f"✗ URL must be https:// — got {url!r}")
        return 1
    print(f"checking {url} …")

    # 1) /health
    try:
        h = requests.get(f"{url}/health", timeout=15)
        if h.status_code != 200 or not (h.json() or {}).get("ok"):
            print(f"✗ /health did not return {{ok:true}} (HTTP {h.status_code})")
            return 1
    except Exception as e:  # noqa: BLE001
        print(f"✗ /health unreachable: {e}")
        return 1
    print("  ✓ /health ok")

    # 2) /quotes — contract + CORS + routing
    try:
        r = requests.get(f"{url}/quotes", params={"symbols": ",".join(_PROBE)}, timeout=20)
    except Exception as e:  # noqa: BLE001
        print(f"✗ /quotes unreachable: {e}")
        return 1
    if r.status_code != 200:
        print(f"✗ /quotes HTTP {r.status_code}")
        return 1
    if r.headers.get("Access-Control-Allow-Origin") != "*":
        print("✗ missing CORS header (Access-Control-Allow-Origin: *) — the browser will block it")
        return 1
    body = r.json()
    quotes = body.get("quotes") or {}
    if "ts" not in body or not isinstance(quotes, dict):
        print(f"✗ /quotes shape wrong (expected {{ts, quotes:{{}}}}): {str(body)[:200]}")
        return 1
    if not quotes:
        print("⚠ /quotes returned 0 quotes — markets may be closed, but the contract is OK. "
              "Re-run during US/HK trading hours to confirm price routing.")
        return 0
    sources = set()
    for sym, q in quotes.items():
        if not isinstance(q, dict) or not isinstance(q.get("price"), (int, float)) or q["price"] <= 0:
            print(f"✗ {sym}: bad price field {q!r}")
            return 1
        if q.get("basis") not in _BASES:
            print(f"✗ {sym}: unexpected basis {q.get('basis')!r}")
            return 1
        sources.add(q.get("source"))
    polygon_us = any(quotes.get(s, {}).get("source") == "polygon" for s in ("AAPL", "SPY"))
    print(f"  ✓ /quotes returned {len(quotes)}/{len(_PROBE)} valid quotes (sources: {sorted(sources)})")
    if not polygon_us:
        print("  ⚠ no Polygon-sourced US quote — POLYGON_API_KEY may be unset on the worker "
              "(`wrangler secret put POLYGON_API_KEY`); US names fall back to Yahoo (still works).")
    print("\n✓ worker healthy & serving the quote contract — safe to set LIVE_QUOTES_WORKER_URL "
          "(repo variable) or config.yml live.quotes_worker_url.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
