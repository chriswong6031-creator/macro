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
  • a rendered marker the recompute no longer produces is RETAINED and counted;
  • the DERIVED date fields (`signal_date`, `confirmed_date` — functions of the marker's
    own `date` plus the grid, not independent facts) are BACKFILLED when the rendered
    marker carries no value, and a non-null rendered value is never overwritten. That is
    what lets a marker published mid-confirmation with `confirmed_date: null` name the
    date it cleared, without opening a channel that could re-date a shown marker;
  • `recorded_at` — the run that FIRST published a marker — is sticky: a rendered marker
    keeps its stamp, and one rendered before the field existed discloses null rather than
    being back-stamped with tonight's run (see `merge_markers`).

All divergence is disclosed in the payload's `pit` dict (cumulative across nights) —
the merged file may drift from tonight's pure recompute, and that is the point: the
file is the record of what was shown, not of what tonight's data revision implies.

THE ONE EXCEPTION — AN ADJUDICATED ERA CHANGE (R-SQ7). The law above exists to stop
UNEXPLAINED nightly mutation. It cannot be allowed to absorb an EXPLAINED one: when the
marker engine's bucketing grid is deliberately re-anchored, every historical marker
legitimately re-dates at once. Under the same-era law that re-draw would be swallowed —
re-dated markers inside TOL_DAYS keep their old rendered date forever, re-phased ones
beyond it are DROPPED (`drift_deep_new`) or ghost-RETAINED (`drift_lost`) — so the
rendered chart would keep the OLD grid while every live `gate()` consumer (boards, the
HK/CN lanes) moved to the new one the same night: a permanent split-brain, plus a
one-time drift-counter burst burying real future drift. So `merge_payload` compares the
payload's `anchor_era`, and on a MISMATCH it yields exactly once — tonight's recompute
replaces the marker history WHOLESALE, `pit["era_cutover"]` records the crossing forever,
and the append-only law resumes under the new era on the next night. That is the same
doctrine as `regen_hk_g1_fixture --force`: an engine-change PR knows itself. Unexplained
re-datings stay blocked exactly as before.

Pure functions; no I/O.
"""
from __future__ import annotations

from datetime import date, timedelta

TOL_DAYS = 4        # same-type prints this close (calendar days) are the same marker
FRESH_DAYS = 21     # markers younger than this vs the previous as-of may still refine

#: Derived date fields (engine/signal_quality.analyze) — a pure function of the marker's
#: own `date` plus the bucketing grid, NOT independent facts. They are BACKFILLED when the
#: rendered marker has no value (it predates the field, or its confirmation window was
#: still open and it published a disclosed null), and a NON-NULL rendered value is never
#: overwritten: that would be exactly the silent re-dating this module exists to stop.
#: null -> value is not a mutation of a shown date, it is filling a disclosed hole, so it
#: needs no FRESH_DAYS gate — a marker's confirmation lands ~6 sessions out, but an old
#: marker that predates the field must still be able to gain it.
_DERIVED_DATE_FIELDS = ("signal_date", "confirmed_date")


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def _first_write(m: dict, run_stamp: str | None) -> dict:
    """A copy of ``m`` stamped as first published by ``run_stamp`` (no-op without one)."""
    out = dict(m)
    if run_stamp is not None:
        out["recorded_at"] = run_stamp
    return out


def _backfill_dates(row: dict, nm: dict) -> int:
    """Fill absent/null derived dates on a rendered marker from tonight's recompute.

    Returns the number of fields filled (disclosed in `pit["date_backfilled"]`).
    """
    filled = 0
    for field in _DERIVED_DATE_FIELDS:
        if field not in nm:
            # Tonight's recompute does not carry the field at all — e.g. `confirmed_date`
            # on a sell/cut, where materialising it would be a schema violation.
            continue
        if row.get(field) is not None:
            continue                      # a published value is never re-dated
        if nm[field] is not None:
            filled += 1
        # Materialised even when null: a marker still inside its confirmation window
        # publishes `confirmed_date: null`, and a reader must be able to tell "pending"
        # from "this build predates the field". An absent key says neither.
        row[field] = nm[field]
    return filled


def merge_markers(prev: list[dict] | None, new: list[dict] | None,
                  prev_asof: str | None, *,
                  run_stamp: str | None = None) -> tuple[list[dict], dict]:
    """Merge tonight's recomputed markers into the previously rendered ones under the
    law above. Returns (merged_markers, pit_stats_for_tonight).

    ``run_stamp`` opts into the ``recorded_at`` provenance contract: the wall-clock date
    of the run that FIRST published a marker. A marker already in the rendered file keeps
    whatever it was stamped with — it was not first written tonight — and one rendered
    before the field existed discloses ``None`` rather than claiming tonight's date, which
    is the whole point: ``recorded_at`` is what makes a publication LAG measurable
    (``recorded_at`` minus ``signal_date``), and back-stamping it with the current run
    would erase exactly the outage evidence it exists to carry. Callers that pass nothing
    are untouched, so this module's other consumer (``build_subsector_confluence``) keeps
    its artifact byte-identical until it opts in.
    """
    new = list(new or [])
    if not prev:
        # A brand-new file: every marker in it genuinely IS first written by this run.
        return ([_first_write(m, run_stamp) for m in new],
                {"new_file": True, "appended": len(new)})
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
             "drift_lost": 0, "drift_deep_new": 0, "relabel_blocked": 0,
             "date_backfilled": 0}
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
            # Derived dates fill their holes independently of the quality/reason refine
            # window: a marker that published `confirmed_date: null` while its confirmation
            # was open must be able to name the date it cleared, even on a night its
            # quality did not move.
            stats["date_backfilled"] += _backfill_dates(row, nm)
        else:
            if _d(pm["date"]) <= anchor - timedelta(days=TOL_DAYS):
                stats["drift_lost"] += 1        # recompute lost it; the render keeps it
        if run_stamp is not None:
            # Already rendered => not first written tonight. No prior stamp means it
            # predates the field: a disclosed null, never a back-stamp.
            row.setdefault("recorded_at", None)
        stats["kept_frozen"] += 1
        merged.append(row)

    for ni in unmatched_new:
        nm = new[ni]
        if _d(nm["date"]) >= fresh_floor:
            merged.append(_first_write(nm, run_stamp))
            stats["appended"] += 1
        else:
            stats["drift_deep_new"] += 1        # recompute invented deep history; dropped

    merged.sort(key=lambda m: (_d(m["date"]), m.get("type") or ""))
    return merged, stats


def merge_payload(prev: dict | None, new: dict, *,
                  run_stamp: str | None = None) -> dict:
    """Full signal-file merge: tonight's live fields (asof/state/trail_stop/…) pass
    through; `markers` obey the law; `pit` accumulates drift counts across nights.

    THE ERA GATE (R-SQ7) runs first. When the payload's ``anchor_era`` differs from the
    rendered file's — including the pre-era case where the stored file carries none —
    tonight's marker history is taken WHOLESALE, with no matching pass at all, and the
    crossing is stamped into ``pit["era_cutover"]``. The cumulative drift counters carry
    over untouched: they measure the same-era law's history and must not be reset by a
    change that is not drift. Callers need no edit — ``build_signal_quality`` and
    ``build_subsector_confluence`` both merge through here, so the cutover happens once,
    in one place, on the night the era moves.
    """
    out = dict(new)
    prev_markers = (prev or {}).get("markers")
    prev_era = (prev or {}).get("anchor_era")
    new_era = new.get("anchor_era")
    if prev and prev_era != new_era:
        # Wholesale replacement: every marker is re-dated onto the new grid, so tonight IS
        # the run that first published these rows in this form. The crossing is recorded in
        # pit["era_cutover"], which is where a reader learns the stamps moved as a cohort.
        out["markers"] = [_first_write(m, run_stamp) for m in (new.get("markers") or [])]
        cum = dict((prev or {}).get("pit") or {})
        cum.pop("last_night", None)
        # A cutover is NOT drift: the counters keep their meaning across the seam, and the
        # night itself is recorded as its own shape so no reader mistakes a wholesale
        # replacement for `appended` markers.
        cutover = {"from": prev_era, "to": new_era, "at_asof": new.get("asof"),
                   "prev_markers": len(prev_markers or [])}
        cum["last_night"] = {"era_cutover": cutover}
        cum["era_cutover"] = cutover
        cum["prev_asof"] = (prev or {}).get("asof")
        out["pit"] = cum
        return out
    merged, stats = merge_markers(prev_markers, new.get("markers"),
                                  (prev or {}).get("asof"), run_stamp=run_stamp)
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
