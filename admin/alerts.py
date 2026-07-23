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


def _age_days(ts) -> float | None:
    if not ts:
        return None
    s = str(ts).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:len(fmt) + 2], fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        except ValueError:
            continue
    return None


def _triage_calibration() -> dict | None:
    """Compact read of the alert-triage rule scorecard — which rules earned predictive
    authority (backtested hit-rate vs base) and how stale the calibration is. The Alerts
    tab previously had ZERO visibility into this lobe (which had gone ~37 days stale)."""
    from .paths import DATA
    p = DATA / "alerts" / "rule_scorecard.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    rules_in = d.get("rules") or {}
    rows = []
    for key, r in rules_in.items():
        horizons = r.get("horizons") or {}
        earned = [(h, hd) for h, hd in horizons.items() if hd.get("survives")]
        if earned:
            pick_h, pick = earned[0]
        elif horizons:
            pick_h, pick = max(horizons.items(),
                               key=lambda kv: (kv[1].get("hit_uplift") if kv[1].get("hit_uplift") is not None else -9))
        else:
            pick_h, pick = None, {}
        rows.append({
            "key": key, "label": r.get("label") or key, "thesis": r.get("thesis"),
            "horizon_d": pick_h, "hit": pick.get("hit"), "base_hit": pick.get("base_hit"),
            "hit_uplift": pick.get("hit_uplift"), "q_fdr": pick.get("q_fdr"),
            "survives": bool(pick.get("survives")),
        })
    rows.sort(key=lambda x: (not x["survives"], -(x["hit_uplift"] if x["hit_uplift"] is not None else -9)))
    gen = d.get("generated_utc")
    return {
        "generated_utc": gen, "age_days": _age_days(gen),
        "n_earned": d.get("n_earned"), "n_total": len(rules_in),
        "target": d.get("target"), "rules": rows,
    }


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
            "triage_calibration": _triage_calibration(),
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
        "triage_calibration": _triage_calibration(),
    }
