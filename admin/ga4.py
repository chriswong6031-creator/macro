"""Optional Google Analytics 4 reader (real-time active users + a short report).

The page tag (measurement id G-BZTZ9W1BBB, injected via theme.js) collects data with
no setup. READING that data needs the GA4 Data API, which requires:
  • GA4_PROPERTY_ID  — the numeric property id (NOT the G-XXXX measurement id)
  • a service account with Viewer access to the property, pointed to by either
    GA4_SA_JSON or GOOGLE_APPLICATION_CREDENTIALS (path to its JSON key)
  • the optional dep:  pip install -r admin/requirements.txt  (google-analytics-data)

Everything degrades gracefully: with nothing configured the Traffic panel shows the
measurement id, what's collecting, and step-by-step setup instructions.

China note: GA4 is blocked by the Great Firewall, so mainland-China traffic is
undercounted. This reader is provider-pluggable — a Baidu Tongji source can be added
later without touching the UI contract.
"""
from __future__ import annotations

import os

MEASUREMENT_ID = "G-BZTZ9W1BBB"

SETUP_STEPS = [
    "Create / open the GA4 property at analytics.google.com (data tag G-BZTZ9W1BBB is already on every page).",
    "Copy the numeric Property ID (Admin → Property settings) and set GA4_PROPERTY_ID in <repo>/.env.",
    "Create a Google Cloud service account, enable the 'Google Analytics Data API', download its JSON key.",
    "In GA4 Admin → Property Access Management, add the service-account email as a Viewer.",
    "Point GA4_SA_JSON (or GOOGLE_APPLICATION_CREDENTIALS) at the JSON key path in <repo>/.env.",
    "Install the reader dep:  .venv/bin/pip install -r admin/requirements.txt  then restart the admin app.",
]


def _property_id() -> str | None:
    v = os.environ.get("GA4_PROPERTY_ID", "").strip()
    return v or None


def _creds_path() -> str | None:
    for k in ("GA4_SA_JSON", "GOOGLE_APPLICATION_CREDENTIALS"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return None


def _client():
    """Build a BetaAnalyticsDataClient or raise with a friendly reason."""
    creds = _creds_path()
    if not creds:
        raise RuntimeError("no service-account JSON (set GA4_SA_JSON / GOOGLE_APPLICATION_CREDENTIALS)")
    if not os.path.exists(creds):
        raise RuntimeError(f"service-account JSON not found: {creds}")
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", creds)
    from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
    return BetaAnalyticsDataClient()


def status() -> dict:
    pid = _property_id()
    creds = _creds_path()
    try:
        import google.analytics.data_v1beta  # noqa: F401
        lib = True
    except Exception:  # noqa: BLE001
        lib = False
    configured = bool(pid and creds and lib and (creds and os.path.exists(creds)))
    reason = None
    if not configured:
        if not lib:
            reason = "google-analytics-data not installed (pip install -r admin/requirements.txt)"
        elif not pid:
            reason = "GA4_PROPERTY_ID not set"
        elif not creds:
            reason = "no service-account JSON (GA4_SA_JSON / GOOGLE_APPLICATION_CREDENTIALS)"
        elif not os.path.exists(creds):
            reason = f"service-account JSON not found: {creds}"
    return {
        "configured": configured,
        "measurement_id": MEASUREMENT_ID,
        "property_id": pid,
        "has_credentials": bool(creds),
        "library_installed": lib,
        "reason": reason,
        "setup_steps": SETUP_STEPS,
        "china_note": ("GA4 is blocked in mainland China — those visits are undercounted. "
                       "A Baidu Tongji source can be added later (skipped for now)."),
    }


def realtime() -> dict:
    """Active users in the last 30 minutes, + by-country split. Graceful on any error."""
    if not status()["configured"]:
        return {"ok": False, "error": status()["reason"]}
    try:
        from google.analytics.data_v1beta.types import (  # type: ignore
            RunRealtimeReportRequest, Dimension, Metric)
        client = _client()
        req = RunRealtimeReportRequest(
            property=f"properties/{_property_id()}",
            dimensions=[Dimension(name="country")],
            metrics=[Metric(name="activeUsers")],
        )
        resp = client.run_realtime_report(req)
        total = 0
        by_country = []
        for row in resp.rows:
            n = int(row.metric_values[0].value or 0)
            total += n
            by_country.append({"country": row.dimension_values[0].value, "active": n})
        by_country.sort(key=lambda x: -x["active"])
        return {"ok": True, "active_users": total, "by_country": by_country[:12]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def report(days: int = 7) -> dict:
    """Sessions / users / pageviews totals + top pages + top countries over N days."""
    if not status()["configured"]:
        return {"ok": False, "error": status()["reason"]}
    try:
        from google.analytics.data_v1beta.types import (  # type: ignore
            RunReportRequest, DateRange, Dimension, Metric, OrderBy)
        client = _client()
        prop = f"properties/{_property_id()}"
        dr = [DateRange(start_date=f"{int(days)}daysAgo", end_date="today")]

        totals = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr,
            metrics=[Metric(name="sessions"), Metric(name="totalUsers"),
                     Metric(name="screenPageViews"), Metric(name="newUsers")],
        ))
        t = totals.rows[0].metric_values if totals.rows else None
        summary = {
            "sessions": int(t[0].value) if t else 0,
            "users": int(t[1].value) if t else 0,
            "pageviews": int(t[2].value) if t else 0,
            "new_users": int(t[3].value) if t else 0,
        }

        pages = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr,
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
            limit=15,
        ))
        top_pages = [{"path": r.dimension_values[0].value,
                      "views": int(r.metric_values[0].value)} for r in pages.rows]

        countries = client.run_report(RunReportRequest(
            property=prop, date_ranges=dr,
            dimensions=[Dimension(name="country")],
            metrics=[Metric(name="totalUsers")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="totalUsers"), desc=True)],
            limit=12,
        ))
        top_countries = [{"country": r.dimension_values[0].value,
                          "users": int(r.metric_values[0].value)} for r in countries.rows]

        return {"ok": True, "days": days, "summary": summary,
                "top_pages": top_pages, "top_countries": top_countries}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
