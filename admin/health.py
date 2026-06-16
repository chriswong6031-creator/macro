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


def market_freshness() -> list[dict]:
    out = []
    for label, rel in _MARKETS:
        p = DATA / rel
        if not p.exists():
            out.append({"label": label, "exists": False, "date": None, "age_hours": None})
            continue
        d = _read_json(p) or {}
        date = d.get("date") or d.get("asof") or d.get("as_of")
        out.append({
            "label": label, "exists": True,
            "date": date,
            "age_hours": _age_hours_from_mtime(p),
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
    ok = stale = dead = 0
    for nm, s in sorted(sources.items()):
        st = (s or {}).get("status", "?")
        if st == "ok":
            ok += 1
        elif st == "stale":
            stale += 1
        elif st == "dead":
            dead += 1
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

    healthy = (not is_stale) and (not broad_outage) and dead == 0
    return {
        "healthy": healthy,
        "last_run": last_run,
        "age_hours": age,
        "stale": is_stale,
        "stale_threshold_h": _STALE_HOURS,
        "broad_outage": broad_outage,
        "sources": {"ok": ok, "stale": stale, "dead": dead, "total": len(src_rows)},
        "source_rows": src_rows,
        "breaker_tripped": tripped,
        "markets": markets,
        "missing_markets": missing_markets,
    }
