"""Pipeline health + data freshness from the repo's committed state files.

Primary source is data/run_status.json (what heartbeat.yml evaluates): top-level
last_run + per-source status + circuit_breaker counts. We add per-market dashboard
freshness from each market's latest.json (using file mtime as a format-agnostic
freshness anchor, plus the human date string each file carries)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .paths import DATA

_STALE_HOURS = 96.0   # heartbeat.yml's staleness threshold

# statuses that mean a feed genuinely failed to deliver this run (these move the verdict)
_DOWN_STATUSES = {"dead", "failed", "check_failed", "error", "not_run"}

# (label, relative path under data/)
_MARKETS = [
    ("US macro regime", "regime/latest.json"),
    ("China regime", "china_regime/latest.json"),
    ("Hong Kong regime", "hk_regime/latest.json"),
    ("Canada regime", "canada_regime/latest.json"),
    ("Commodities", "commodity/latest.json"),
    ("Forex", "forex/latest.json"),
    ("Bonds", "bonds/latest.json"),
    ("Cross-asset", "crossasset/latest.json"),
    ("US stocks", "us_stocks/latest.json"),
    ("China stocks", "china_stocks/latest.json"),
    ("HK stocks", "hk_stocks/latest.json"),
    ("Canada stocks", "canada_stocks/latest.json"),
]


def _read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _age_hours_from_mtime(path) -> float | None:
    try:
        return (time.time() - path.stat().st_mtime) / 3600.0
    except OSError:
        return None


def _parse_iso_age_hours(ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return None


def _parse_any_age_hours(ts) -> float | None:
    """Age in hours from a date string, tolerant of the formats the market latest.json
    files actually carry: ISO ('2026-07-21', optionally with time/tz) AND the
    'Jul 22, 2026' / 'Jul 22 2026' variant that forex + commodities emit. Used so
    dashboard freshness reflects the DATA's date, not the file mtime (which is just the
    checkout/deploy time in a git working tree and says nothing about staleness)."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    s = ts.strip()
    a = _parse_iso_age_hours(s)
    if a is not None:
        return a
    for fmt in ("%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        except ValueError:
            continue
    return None


def market_freshness() -> list[dict]:
    out = []
    for label, rel in _MARKETS:
        p = DATA / rel
        if not p.exists():
            out.append({"label": label, "exists": False, "date": None, "age_hours": None})
            continue
        d = _read_json(p) or {}
        date = d.get("date") or d.get("asof") or d.get("as_of")
        age = _parse_any_age_hours(date)
        age_source = "date"
        if age is None:
            age = _age_hours_from_mtime(p)   # last resort — the file carried no parseable date
            age_source = "mtime"
        out.append({
            "label": label, "exists": True,
            "date": date,
            "age_hours": age,
            "age_source": age_source,
        })
    return out


def summary() -> dict:
    """One 'is the pipeline healthy?' object for the Health panel."""
    rs = _read_json(DATA / "run_status.json") or {}
    last_run = rs.get("last_run")
    age = _parse_iso_age_hours(last_run) if isinstance(last_run, str) else None
    sources = rs.get("sources", {}) or {}
    breaker = rs.get("circuit_breaker", {}) or {}

    src_rows = []
    # Bucket every status, not just ok/stale/dead. The old code counted only those
    # three, so blocked/failed/no_creds/empty/check_failed feeds were invisible in the
    # tally AND could never move the verdict (dead stayed 0, so "Healthy" was pinned on).
    # "down" = a genuine failure to deliver (flips the verdict); "blocked" = throttled/
    # paywalled upstream (surfaced, but doesn't cry wolf on chronic external blocks);
    # "gated" = missing creds (operator config, not a pipeline fault); "empty" = ran but
    # returned no rows.
    # "dead" is retained as a subset of "down" (literal dead status) for backward-compat
    # with existing consumers of the old sources schema.
    counts = {"ok": 0, "stale": 0, "down": 0, "dead": 0, "blocked": 0, "gated": 0, "empty": 0, "other": 0}
    for nm, s in sorted(sources.items()):
        st = (s or {}).get("status", "?")
        if st == "ok":
            counts["ok"] += 1
        elif st == "stale":
            counts["stale"] += 1
        elif st in _DOWN_STATUSES:
            counts["down"] += 1
            if st == "dead":
                counts["dead"] += 1
        elif st == "blocked":
            counts["blocked"] += 1
        elif st == "no_creds":
            counts["gated"] += 1
        elif st == "empty":
            counts["empty"] += 1
        else:
            counts["other"] += 1
        src_rows.append({
            "name": nm, "status": st,
            "rows": (s or {}).get("rows"),
            "last_date": (s or {}).get("last_date"),
            "error": (s or {}).get("error"),
            "breaker": breaker.get(nm, 0),
        })

    tripped = sum(1 for c in breaker.values() if isinstance(c, (int, float)) and c >= 3)
    is_stale = age is not None and age > _STALE_HOURS
    broad_outage = tripped >= 8
    markets = market_freshness()
    missing_markets = [m["label"] for m in markets if not m["exists"]]

    down = counts["down"]
    healthy = (not is_stale) and (not broad_outage) and down == 0
    return {
        "healthy": healthy,
        "last_run": last_run,
        "age_hours": age,
        "stale": is_stale,
        "stale_threshold_h": _STALE_HOURS,
        "broad_outage": broad_outage,
        "down_count": down,
        "sources": {
            "ok": counts["ok"], "stale": counts["stale"], "down": down,
            "dead": counts["dead"], "blocked": counts["blocked"], "gated": counts["gated"],
            "empty": counts["empty"], "other": counts["other"],
            "total": len(src_rows),
        },
        "source_rows": src_rows,
        "breaker_tripped": tripped,
        "markets": markets,
        "missing_markets": missing_markets,
    }
