"""Live uptime/latency probes for every public surface of the site.

Each probe is an independent HTTP GET with a short timeout; they run concurrently
and the results return together so the panel shows one board. Stateless — probes
on demand. (content.py keeps the older single-URL probe; this is the multi-host
board.)"""
from __future__ import annotations

import concurrent.futures
import time

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

# (label, url, expected_status_or_None) — the public endpoints that must stay up.
# None = accept any non-5xx (some surfaces redirect or gate behind auth).
TARGETS = [
    ("Main site", "https://mastermind-x.com/", 200),
    ("macro API", "https://mastermind-x.com/api/health", 200),
    ("Terminal", "https://app.mastermind-x.com/", None),
    ("Brain bot", "https://bot.mastermind-x.com/", None),
    ("Admin console", "https://admin.mastermind-x.com/healthz", 200),
]


def _probe(label: str, url: str, expect: int | None) -> dict:
    if requests is None:
        return {"label": label, "url": url, "ok": False, "error": "requests not installed"}
    t0 = time.time()
    try:
        r = requests.get(url, timeout=10, allow_redirects=True,
                         headers={"User-Agent": "macro-admin-uptime"})
        ms = round((time.time() - t0) * 1000)
        ok = (r.status_code == expect) if expect else (r.status_code < 500)
        return {"label": label, "url": url, "ok": ok, "status": r.status_code, "ms": ms}
    except Exception as e:  # noqa: BLE001
        return {"label": label, "url": url, "ok": False,
                "ms": round((time.time() - t0) * 1000), "error": str(e)[:160]}


def probe_all() -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(TARGETS)) as ex:
        rows = list(ex.map(lambda t: _probe(*t), TARGETS))
    return {"targets": rows, "up": sum(1 for r in rows if r["ok"]), "total": len(rows)}
