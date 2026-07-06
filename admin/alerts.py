"""admin.alerts — Alert feed reader for the admin Alerts capture tab.

Reads the committed site/alertsdata/feed.json written by build_alerts_page()
and serves it to the authed admin console.  No write path, no public access
(RUL-8: auth wall stays; this is a GET-only reader).

The feed is built nightly by the CI render pipeline.  If the file is absent
(first deploy before any render) the panel returns an empty list with a note.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_MAX_ALERTS = 200   # guard against an unexpectedly huge file


def _feed_path():
    from .paths import SITE
    return SITE / "alertsdata" / "feed.json"


def panel(limit: int = 60) -> dict:
    """Return the alert feed for the admin Alerts tab.

    Returns
    -------
    {
      "ok": bool,
      "generated_utc": str | None,
      "alerts": [
        {
          "alert_id": str,    # stable 12-hex content-hash ID
          "emit_ts": str,     # ISO-8601 UTC
          "title": str,
          "surface": str,     # "source:type" hint
          "severity": str,
          "tier": str,
          "priority": int,
          "source": str,
        }, ...
      ],
      "note": str | None,
    }
    """
    p = _feed_path()
    if not p.exists():
        return {
            "ok": True,
            "generated_utc": None,
            "alerts": [],
            "note": "feed not yet generated — run the nightly build to populate",
        }
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("alerts feed read failed: %s", exc)
        return {"ok": False, "generated_utc": None, "alerts": [],
                "note": f"feed read error: {exc}"}

    alerts = (raw.get("alerts") or [])[:min(limit, _MAX_ALERTS)]
    return {
        "ok": True,
        "generated_utc": raw.get("generated_utc"),
        "alerts": alerts,
        "note": None,
    }
