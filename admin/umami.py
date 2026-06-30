"""Umami web-analytics reader (cloud.umami.is) + setup/status.

The whole site is tagged with the Umami script (injected once via theme.js), so
pageview data collects for free and is viewable in the Umami Cloud dashboard.
READING it back programmatically needs the Umami Cloud API, which is a PAID
feature — so this degrades gracefully: with no API key it reports that the tag is
live and links to the dashboard; set UMAMI_API_KEY to light up in-panel numbers.

Self-hosted Umami works the same way: point UMAMI_API_BASE at the instance and
use a key minted there (same x-umami-api-key / bearer contract)."""
from __future__ import annotations

import time

from . import settings

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore


def status() -> dict:
    key = settings.umami_api_key()
    configured = bool(key and requests)
    reason = None
    if not configured:
        reason = ("requests not installed" if not requests else
                  "UMAMI_API_KEY not set — the Umami Cloud API is a paid feature. "
                  "View stats in the dashboard, or self-host Umami for a free key.")
    return {
        "website_id": settings.umami_website_id(),
        "dashboard_url": settings.umami_dashboard_url(),
        "api_base": settings.umami_api_base(),
        "configured": configured,
        "tag_installed": True,   # theme.js injects the script on every page
        "reason": reason,
        "setup_steps": [
            "The tracking script is already live on every page (via theme.js) — "
            "data is collecting now, for free.",
            "View traffic at cloud.umami.is → website d7734c31… (free).",
            "To pull numbers INTO this panel: create an API key (paid Umami Cloud "
            "Settings → API, or any self-hosted instance) and set UMAMI_API_KEY.",
            "Optional overrides: UMAMI_API_BASE (self-host), UMAMI_WEBSITE_ID.",
        ],
    }


def _headers(key: str) -> dict:
    # Umami Cloud authenticates with x-umami-api-key; self-hosted accepts a
    # bearer token — send both so one config covers either deployment.
    return {"x-umami-api-key": key, "Authorization": f"Bearer {key}",
            "Accept": "application/json"}


def report(days: int = 7) -> dict:
    key = settings.umami_api_key()
    if not (key and requests):
        return {"ok": False, "degraded": True, "error": status()["reason"]}
    end = int(time.time() * 1000)
    start = end - int(days) * 86400 * 1000
    base = f"{settings.umami_api_base()}/websites/{settings.umami_website_id()}"
    params = {"startAt": start, "endAt": end}
    try:
        st = requests.get(f"{base}/stats", headers=_headers(key), params=params, timeout=12)
        if st.status_code != 200:
            return {"ok": False, "error": f"HTTP {st.status_code}: {st.text[:160]}"}
        s = st.json()

        def _val(metric):  # umami returns {"value":N,"prev":M} (or a scalar)
            m = s.get(metric)
            return m.get("value") if isinstance(m, dict) else m

        def _metric(kind):
            r = requests.get(f"{base}/metrics", headers=_headers(key),
                             params={**params, "type": kind}, timeout=12)
            return r.json() if r.status_code == 200 else []

        top_pages = [{"path": r.get("x"), "views": r.get("y")}
                     for r in (_metric("url") or [])[:15]]
        top_countries = [{"country": r.get("x"), "visitors": r.get("y")}
                         for r in (_metric("country") or [])[:12]]
        top_referrers = [{"referrer": r.get("x") or "(direct)", "visitors": r.get("y")}
                         for r in (_metric("referrer") or [])[:10]]
        return {"ok": True, "days": days,
                "summary": {"pageviews": _val("pageviews"), "visitors": _val("visitors"),
                            "visits": _val("visits"), "bounces": _val("bounces")},
                "top_pages": top_pages, "top_countries": top_countries,
                "top_referrers": top_referrers}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def active() -> dict:
    key = settings.umami_api_key()
    if not (key and requests):
        return {"ok": False, "degraded": True, "error": status()["reason"]}
    base = f"{settings.umami_api_base()}/websites/{settings.umami_website_id()}"
    try:
        r = requests.get(f"{base}/active", headers=_headers(key), timeout=10)
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        d = r.json()
        n = (d[0].get("x") if isinstance(d, list) and d
             else d.get("visitors") if isinstance(d, dict) else 0)
        return {"ok": True, "active": n or 0}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
