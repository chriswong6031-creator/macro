"""engine.chronicle.rollups — short (daily) + medium (weekly) "streaming
consciousness" tiers (masterplan §2.3). W0 ships these two deterministically
(pure template renderings of events, no prose); the long/epoch tier and all
LLM narrative polish are W1+ under data/chronicle/llm/ (out of scope here).

Only the CURRENT daily + CURRENT weekly file is written each run; prior files
are left untouched so they accumulate (masterplan instruction, verbatim).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date as _date
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

DAILY_CHAR_BUDGET = 6_000     # ~1.5k tokens equivalent
WEEKLY_CHAR_BUDGET = 10_000   # ~2.5k tokens equivalent
DAILY_MAX_SESSIONS = 10
DAILY_MIN_SESSIONS = 5
WEEKLY_MAX_WEEKS = 13
_TRIM_GUARD = 10_000  # safety bound on the trim loop; real W0 volumes never approach this


def _compact_event(ev: dict) -> dict:
    return {
        "id": ev.get("id"),
        "date": ev.get("date"),
        "source": ev.get("source"),
        "kind": ev.get("kind"),
        "title": ev.get("title"),
        "weight_hint": ev.get("weight_hint"),
        "tickers": ev.get("tickers") or [],
        "source_ref": ev.get("source_ref"),
    }


def _iso_week_key(d: _date) -> str:
    y, w, _wd = d.isocalendar()
    return f"{y}-W{w:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Daily (short tier)
# ─────────────────────────────────────────────────────────────────────────────

def build_daily(events: list[dict], as_of: str) -> dict:
    """Last 5-10 session-dates <= as_of, grouped by date, weight-ordered."""
    dates_present = sorted(
        {e.get("date") for e in events if e.get("date") and e["date"] <= as_of},
        reverse=True,
    )
    session_dates = dates_present[:DAILY_MAX_SESSIONS]

    by_date: dict[str, list[dict]] = {d: [] for d in session_dates}
    for e in events:
        d = e.get("date")
        if d in by_date:
            by_date[d].append(_compact_event(e))
    for d in by_date:
        by_date[d].sort(key=lambda e: (-(e.get("weight_hint") or 0), e.get("id") or ""))

    sessions = [{"date": d, "events": by_date[d]} for d in session_dates]
    earliest_overall = min((e.get("date") for e in events if e.get("date")), default=None)

    note = f"daily rollup covers {len(session_dates)} session-date(s)"
    if session_dates:
        note += f" from {session_dates[-1]} to {session_dates[0]}"
    note += (f"; chronicle event store begins {earliest_overall}" if earliest_overall
             else "; chronicle event store is empty")
    if 0 < len(session_dates) < DAILY_MIN_SESSIONS:
        note += f" (fewer than the target {DAILY_MIN_SESSIONS}-{DAILY_MAX_SESSIONS} sessions — accruing)"

    payload = {
        "schema": "chronicle.rollup.daily/v1",
        "as_of": as_of,
        "sessions": sessions,
        "coverage": {
            "start": session_dates[-1] if session_dates else None,
            "end": session_dates[0] if session_dates else None,
            "note": note,
        },
    }
    if _trim_to_budget(payload, DAILY_CHAR_BUDGET, _daily_remove_lowest):
        payload["coverage"]["note"] += "; trimmed lowest-salience events to fit the display budget"
    return payload


def _daily_remove_lowest(payload: dict) -> bool:
    best = None  # (weight, session_idx, event_idx)
    for si, s in enumerate(payload["sessions"]):
        for ei, e in enumerate(s["events"]):
            w = e.get("weight_hint") or 0
            if best is None or w < best[0]:
                best = (w, si, ei)
    if best is None:
        return False
    _, si, ei = best
    payload["sessions"][si]["events"].pop(ei)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Weekly (medium tier)
# ─────────────────────────────────────────────────────────────────────────────

def build_weekly(events: list[dict], as_of: str) -> dict:
    """Rolling up-to-13-ISO-week rollup, event-cluster level (cluster = source +
    theme within a week; W0 has no narratives, so this renders top events per
    cluster rather than prose)."""
    as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
    week_key = _iso_week_key(as_of_date)
    cutoff = (as_of_date - timedelta(weeks=WEEKLY_MAX_WEEKS)).isoformat()

    in_window = [e for e in events if e.get("date") and cutoff <= e["date"] <= as_of]
    weeks: dict[str, list[dict]] = {}
    for e in in_window:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            continue
        weeks.setdefault(_iso_week_key(d), []).append(e)

    clusters_by_week: dict[str, list[dict]] = {}
    for wk, evs in weeks.items():
        by_cluster: dict[tuple, list[dict]] = {}
        for e in evs:
            theme = (e.get("themes") or [None])[0]
            by_cluster.setdefault((e.get("source"), theme), []).append(e)
        cluster_list = []
        for (source, theme), evs2 in by_cluster.items():
            evs2_sorted = sorted(evs2, key=lambda x: (-(x.get("weight_hint") or 0), x.get("id") or ""))
            cluster_list.append({
                "source": source,
                "theme": theme,
                "n_events": len(evs2_sorted),
                "top_events": [_compact_event(x) for x in evs2_sorted[:5]],
            })
        cluster_list.sort(key=lambda c: (-c["n_events"], c["source"] or ""))
        clusters_by_week[wk] = cluster_list

    week_keys_sorted = sorted(clusters_by_week.keys(), reverse=True)
    earliest_overall = min((e.get("date") for e in events if e.get("date")), default=None)

    note = (f"weekly rollup spans up to {WEEKLY_MAX_WEEKS} ISO weeks ending {week_key}; "
            f"{len(week_keys_sorted)} week(s) have events so far")
    note += (f"; chronicle event store begins {earliest_overall}" if earliest_overall
             else "; chronicle event store is empty")

    payload = {
        "schema": "chronicle.rollup.weekly/v1",
        "as_of": as_of,
        "iso_week": week_key,
        "weeks": [{"iso_week": wk, "clusters": clusters_by_week[wk]} for wk in week_keys_sorted],
        "coverage": {"start": cutoff, "end": as_of, "note": note},
    }
    if _trim_to_budget(payload, WEEKLY_CHAR_BUDGET, _weekly_remove_lowest):
        payload["coverage"]["note"] += "; trimmed lowest-salience events to fit the display budget"
    return payload


def _weekly_remove_lowest(payload: dict) -> bool:
    best = None  # (weight, week_idx, cluster_idx, event_idx)
    for wi, w in enumerate(payload["weeks"]):
        for ci, c in enumerate(w["clusters"]):
            for ei, e in enumerate(c["top_events"]):
                wt = e.get("weight_hint") or 0
                if best is None or wt < best[0]:
                    best = (wt, wi, ci, ei)
    if best is None:
        return False
    _, wi, ci, ei = best
    payload["weeks"][wi]["clusters"][ci]["top_events"].pop(ei)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Budget trimming + atomic write
# ─────────────────────────────────────────────────────────────────────────────

def _trim_to_budget(payload: dict, budget: int, remove_lowest) -> bool:
    truncated = False
    guard = 0
    while len(json.dumps(payload, ensure_ascii=False)) > budget and guard < _TRIM_GUARD:
        if not remove_lowest(payload):
            break
        truncated = True
        guard += 1
    return truncated


def _write_json_atomic(path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def write_daily(repo, doc: dict):
    path = repo / "data" / "chronicle" / "rollups" / "daily" / f"{doc['as_of']}.json"
    _write_json_atomic(path, doc)
    return path


def write_weekly(repo, doc: dict):
    path = repo / "data" / "chronicle" / "rollups" / "weekly" / f"{doc['iso_week']}.json"
    _write_json_atomic(path, doc)
    return path
