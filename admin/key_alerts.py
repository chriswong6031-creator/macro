"""admin.key_alerts — the landing page's "needs your eyes" rail.

Composes the operator-salient alert states from COMMITTED artifacts only (admin law:
no engine imports, no subprocess, read-only) into one capped list, each item carrying a
ready-to-paste ``brief_prompt`` — the "check in with Fable" nudge: copy it into a Claude
session and the session starts with the alert's full context and artifact paths.

Sources (each fail-open — a missing/malformed artifact drops its section, never the rail):
  * data/transmission/chain_state.json       — transmission cascades not dormant
    (arming / propagating / expressed / failed), the TXI staged-episode tracker.
  * data/cycle_ontology/tripwire_state.json  — cycle-thesis tripwires in FIRED state.
  * site/alertsdata/feed.json                — triaged alert feed, high-priority recent rows.

Display notes: internal state words (arming/FIRED) are fine here — the admin console is
the operator surface, not a customer page. Items are ranked most-actionable first
(expressed/failed cascades > FIRED tripwires > propagating > high-priority triage > arming)
and capped so the landing stays a glance, not a log.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_MAX_ITEMS = 8
_TRIAGE_PRIORITY_FLOOR = 70
_TRIAGE_MAX_AGE_DAYS = 3.0
_CASCADE_SALIENCE = {"expressed": 0, "failed": 1, "propagating": 3, "arming": 5}
_TRIPWIRE_SALIENCE = 2
_TRIAGE_SALIENCE = 4


def _read_json(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — absent/malformed → section drops, rail survives
        return None


def _age_days(ts) -> float | None:
    if not ts:
        return None
    s = str(ts).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[: len(fmt) + 2], fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        except ValueError:
            continue
    return None


def _cascade_items() -> list[dict]:
    from .paths import DATA
    doc = _read_json(DATA / "transmission" / "chain_state.json")
    if not isinstance(doc, dict):
        return []
    out: list[dict] = []
    for ch in doc.get("chains") or []:
        state = ch.get("state")
        if state not in _CASCADE_SALIENCE:
            continue
        label = ((ch.get("title") or {}).get("en")
                 or ch.get("chain") or "cascade").strip()
        hops = ch.get("hops") or []
        confirmed = sum(1 for h_ in hops if h_.get("confirmed"))
        detail = f"{state} · {confirmed}/{len(hops)} hops confirmed" if hops else state
        asof = ch.get("asof") or doc.get("asof")
        prompt = (
            f"Check in on the '{label}' transmission cascade — state={state}, "
            f"{confirmed}/{len(hops)} hops confirmed, asof {asof}. Read "
            f"data/transmission/chain_state.json (and chain_calibration.json if present) "
            f"plus knowledge/transmission/{ch.get('chain')}.yaml. Tell me: what changed, "
            f"the historical base rate for the next hop in the current regime cell, which "
            f"surfaces should reflect this state, and whether anything in "
            f"research/TRANSMISSION_INTELLIGENCE_ACTIVATION_MASTERPLAN_BY_FABLE.md is "
            f"unblocked by it. Watch-vocabulary read only — no calls."
        )
        out.append({
            "kind": "cascade", "id": ch.get("chain"), "title": label,
            "state": state, "detail": detail, "asof": asof,
            "salience": _CASCADE_SALIENCE[state], "brief_prompt": prompt,
        })
    return out


def _tripwire_items() -> list[dict]:
    # tripwire_state.json is a TOP-LEVEL dict keyed by tripwire id:
    #   {"<id>": {"version", "state", "fired_on", "latched", "current_leg", "as_of"}}.
    # Claim prose lives in the sibling registry falsifiers.json — enriched when readable.
    from .paths import DATA
    doc = _read_json(DATA / "cycle_ontology" / "tripwire_state.json")
    if not isinstance(doc, dict):
        return []
    claims: dict[str, str] = {}
    reg = _read_json(DATA / "cycle_ontology" / "falsifiers.json")
    reg_entries = reg.get("entries") if isinstance(reg, dict) else reg
    if isinstance(reg_entries, list):
        for e in reg_entries:
            if isinstance(e, dict) and e.get("id"):
                claims[str(e["id"])] = str(e.get("claim") or "")
    out: list[dict] = []
    for tid, e in doc.items():
        if not isinstance(e, dict) or e.get("state") != "FIRED":
            continue
        fired_on = e.get("fired_on")
        leg = e.get("current_leg")
        leg_note = ("condition still holding" if leg is True
                    else "condition no longer met" if leg is False else "live leg unreadable")
        claim = claims.get(str(tid), "").strip()
        prompt = (
            f"Check in on cycle tripwire '{tid}' (FIRED{f' {fired_on}' if fired_on else ''}; "
            f"{leg_note}). Registered claim: \"{claim or 'see registry'}\". Read "
            f"data/cycle_ontology/tripwire_state.json and the matching entry in "
            f"data/cycle_ontology/falsifiers.json. Tell me what fired, whether the "
            f"condition still holds on the live leg, what it changes about the cycle "
            f"read, and whether the entry needs a version re-author."
        )
        out.append({
            "kind": "tripwire", "id": str(tid), "title": str(tid),
            "state": "FIRED", "detail": (claim[:110] or leg_note),
            "asof": fired_on or e.get("as_of"),
            "salience": _TRIPWIRE_SALIENCE, "brief_prompt": prompt,
        })
    return out


def _triage_items() -> list[dict]:
    from .paths import SITE
    doc = _read_json(SITE / "alertsdata" / "feed.json")
    alerts = doc.get("alerts") if isinstance(doc, dict) else None
    if not isinstance(alerts, list):
        return []
    out: list[dict] = []
    for a in alerts:
        try:
            pri = float(a.get("priority") or 0)
        except (TypeError, ValueError):
            continue
        ts = a.get("emit_ts") or a.get("ts") or a.get("date")
        age = _age_days(ts)
        if pri < _TRIAGE_PRIORITY_FLOOR or (age is not None and age > _TRIAGE_MAX_AGE_DAYS):
            continue
        title = (a.get("title") or "alert").strip()
        surface = a.get("surface") or a.get("source") or ""
        prompt = (
            f"Check in on the triaged alert '{title}' (priority {pri:.0f}, "
            f"surface {surface}, {ts}). Read site/alertsdata/feed.json for the row "
            f"(alert_id {a.get('alert_id')}) and its source engine's artifact. Tell me the "
            f"read, whether it corroborates or contradicts the current cascades/tripwires, "
            f"and what to watch next."
        )
        out.append({
            "kind": "triage", "id": a.get("alert_id") or title, "title": title,
            "state": f"P{pri:.0f}",
            "detail": " · ".join(x for x in (a.get("severity"), surface) if x)[:110],
            "asof": ts, "salience": _TRIAGE_SALIENCE, "brief_prompt": prompt,
        })
    return out


def panel() -> dict:
    """The landing rail payload. Never raises; every section fail-open."""
    items: list[dict] = []
    counts = {}
    for name, fn in (("cascades", _cascade_items),
                     ("tripwires", _tripwire_items),
                     ("triage", _triage_items)):
        try:
            rows = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("key_alerts %s section failed: %s", name, exc)
            rows = []
        counts[name] = len(rows)
        items.extend(rows)
    items.sort(key=lambda r: (r.get("salience", 9), str(r.get("asof") or "")))
    total = len(items)
    return {
        "available": True,
        "items": items[:_MAX_ITEMS],
        "counts": counts,
        "total": total,
        "truncated": total > _MAX_ITEMS,
    }
