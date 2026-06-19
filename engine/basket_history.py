"""Per-theme score HISTORY — the point-in-time record of how a theme's score/label/reco
moved over time (for the detail-page sparkline + change timeline).

Two honest sources, both already point-in-time:
  • the numeric SCORE SERIES from the append-only signal archive ('baskets' stream, written
    by scripts/archive_signals from data/baskets/latest.json) — accrues one row per day;
  • the dated CHANGE TIMELINE from engine.theme_alerts (reco flips, emerging/topping/
    deteriorating) — already logged since the desk shipped.

Read-only + graceful: empty history → empty series (the page shows 'history accruing').
"""
from __future__ import annotations

import pandas as pd


def score_series(basket_id: str, field: str = "score", region: str = "us") -> list[dict]:
    """Dated [{date, value}] of one scalar (score / components.* / textures.*) for a basket,
    pulled from the 'baskets' signal-archive snapshots. Empty until history accrues."""
    try:
        from engine.signal_archive import load_archive
        df = load_archive("baskets" if region == "us" else f"baskets_{region}")
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty or "snapshot_json" not in df.columns:
        return []
    import json
    out = []
    for _, row in df.iterrows():
        try:
            snap = json.loads(row["snapshot_json"])
        except Exception:  # noqa: BLE001
            continue
        themes = snap.get("themes") or []
        th = next((t for t in themes if t.get("id") == basket_id), None)
        if not th:
            continue
        v = th
        for part in field.split("."):
            v = (v or {}).get(part) if isinstance(v, dict) else None
        if v is not None:
            out.append({"date": str(row.get("asof") or snap.get("as_of")), "value": v})
    return out


def change_timeline(basket_id: str, days: int = 365, region: str = "us") -> list[dict]:
    """This theme's dated score/label/reco CHANGE events from engine.theme_alerts, newest
    first — the 'when scoring changed' record the user asked for."""
    try:
        from engine import theme_alerts
        evs = [e for e in theme_alerts.load_events(region) if e.get("asset") == basket_id]
    except Exception:  # noqa: BLE001
        return []
    if not evs:
        return []
    evs.sort(key=lambda e: e.get("ts", ""), reverse=True)
    cutoff = (pd.Timestamp(evs[0]["ts"]) - pd.Timedelta(days=days)) if evs else None
    out = []
    for e in evs:
        if cutoff is not None and pd.Timestamp(e["ts"]) < cutoff:
            continue
        out.append({"ts": e["ts"], "type": e.get("type"), "severity": e.get("severity"),
                    "headline": e.get("headline"), "headline_zh": e.get("headline_zh")})
    return out
