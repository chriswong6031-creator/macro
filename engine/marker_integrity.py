"""engine/marker_integrity.py — the append-only marker law (Rotation Command RC-R2).

The bug this kills (masterplan §0.4, verified from committed renders): signal-marker
files are fully recomputed each night, so a marker the site already RENDERED can be
silently re-dated or deleted — site/subsector_signals/b-ai-software.json carried a
2026-07-06 buy in the 07-07 render that became 2026-07-09 in the 07-10 render, and a
software-application rebuy was re-graded take→block. A file that mutates its own history
is not a point-in-time record, so nothing built on it (ledgers, graders, the §7 chart)
is falsifiable.

THE LAW, applied at every marker write (one merge with the previously rendered file):

  • every previously rendered marker persists — original date, original type, forever;
  • a recomputed marker of the SAME type within TOL_DAYS of a rendered one is the SAME
    print → the rendered date wins (never re-dated), and only if the rendered marker is
    still inside FRESH_DAYS of the previous as-of may its quality/reason refine
    (pending→take/block is the designed confirmation flow); outside that window a
    relabel is blocked and counted;
  • a recomputed marker with no rendered counterpart is APPENDED if it is recent
    (inside FRESH_DAYS of the previous as-of — a genuinely new signal), DROPPED and
    counted if it lands deep in history (a recompute inventing the past);
  • a rendered marker the recompute no longer produces is RETAINED and counted.

All divergence is disclosed in the payload's `pit` dict (cumulative across nights) —
the merged file may drift from tonight's pure recompute, and that is the point: the
file is the record of what was shown, not of what tonight's data revision implies.
Pure functions; no I/O.
"""
from __future__ import annotations

from datetime import date, timedelta

TOL_DAYS = 4        # same-type prints this close (calendar days) are the same marker
FRESH_DAYS = 21     # markers younger than this vs the previous as-of may still refine


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def merge_markers(prev: list[dict] | None, new: list[dict] | None,
                  prev_asof: str | None) -> tuple[list[dict], dict]:
    """Merge tonight's recomputed markers into the previously rendered ones under the
    law above. Returns (merged_markers, pit_stats_for_tonight)."""
    new = list(new or [])
    if not prev:
        return new, {"new_file": True, "appended": len(new)}
    prev = list(prev)
    anchor = _d(prev_asof) if prev_asof else max((_d(m["date"]) for m in prev),
                                                 default=_d(new[-1]["date"]) if new else date.min)
    fresh_floor = anchor - timedelta(days=FRESH_DAYS)

    # nearest-date greedy matching, same type, within tolerance
    unmatched_new = list(range(len(new)))
    match_for_prev: dict[int, int] = {}
    for pi, pm in enumerate(prev):
        pd_, pt = _d(pm["date"]), pm.get("type")
        best, best_gap = None, TOL_DAYS + 1
        for ni in unmatched_new:
            nm = new[ni]
            if nm.get("type") != pt:
                continue
            gap = abs((_d(nm["date"]) - pd_).days)
            if gap <= TOL_DAYS and gap < best_gap:
                best, best_gap = ni, gap
        if best is not None:
            match_for_prev[pi] = best
            unmatched_new.remove(best)

    stats = {"kept_frozen": 0, "refined": 0, "appended": 0,
             "drift_lost": 0, "drift_deep_new": 0, "relabel_blocked": 0}
    merged: list[dict] = []
    for pi, pm in enumerate(prev):
        row = dict(pm)
        ni = match_for_prev.get(pi)
        if ni is not None:
            nm = new[ni]
            changed = any(nm.get(k) != pm.get(k) for k in ("quality", "reason"))
            if changed:
                if _d(pm["date"]) >= fresh_floor:
                    row["quality"] = nm.get("quality", pm.get("quality"))
                    if nm.get("reason") is not None:
                        row["reason"] = nm["reason"]
                    stats["refined"] += 1
                else:
                    stats["relabel_blocked"] += 1
        else:
            if _d(pm["date"]) <= anchor - timedelta(days=TOL_DAYS):
                stats["drift_lost"] += 1        # recompute lost it; the render keeps it
        stats["kept_frozen"] += 1
        merged.append(row)

    for ni in unmatched_new:
        nm = new[ni]
        if _d(nm["date"]) >= fresh_floor:
            merged.append(dict(nm))
            stats["appended"] += 1
        else:
            stats["drift_deep_new"] += 1        # recompute invented deep history; dropped

    merged.sort(key=lambda m: (_d(m["date"]), m.get("type") or ""))
    return merged, stats


def merge_payload(prev: dict | None, new: dict) -> dict:
    """Full signal-file merge: tonight's live fields (asof/state/trail_stop/…) pass
    through; `markers` obey the law; `pit` accumulates drift counts across nights."""
    out = dict(new)
    prev_markers = (prev or {}).get("markers")
    merged, stats = merge_markers(prev_markers, new.get("markers"),
                                  (prev or {}).get("asof"))
    out["markers"] = merged
    cum = dict((prev or {}).get("pit") or {})
    cum.pop("last_night", None)
    for k, v in stats.items():
        if isinstance(v, (int, float)):
            cum[k] = int(cum.get(k, 0)) + int(v)
    cum["last_night"] = stats
    cum["prev_asof"] = (prev or {}).get("asof")
    out["pit"] = cum
    return out
