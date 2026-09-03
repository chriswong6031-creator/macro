"""engine.flow_observatory.quality — per-leg source-quality state machine (W2).

Pure module: no I/O beyond the two trading-day calendars (``lib.cn_calendar`` /
``lib.hk_calendar``, themselves dependency-free stdlib code — masterplan §4 module-layout
freeze, "quality.py (W2)"). Every function takes plain dicts/values in and returns plain
dicts/values out; ``scripts/build_flow_velocity`` (via ``engine.flow_observatory.contract``)
is the only caller that touches disk or a wall clock.

This is the module that makes source quality BINDING rather than advisory (W2_SPEC.md §0):
before this wave, ``lib.desk_guard.stale_legs`` only ever emitted a ``::warning`` — no page
branch rendered staleness, so the #4676 12-day A-share freeze rendered as confidently
current beside a live Southbound leg. ``classify_leg`` below is the per-leg decision that
feeds ``sources[].status`` (and, through :func:`publication_state`, the desk-wide
``publication_state``) so the machine contract and the UI are reading the SAME verdict.
"""
from __future__ import annotations

from typing import Any

from lib import cn_calendar, hk_calendar

# ── status enum (frozen — W2_SPEC.md §1) ────────────────────────────────────────────
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
STALE = "STALE"
UNAVAILABLE = "UNAVAILABLE"
HISTORICAL_ONLY = "HISTORICAL_ONLY"
REVISED = "REVISED"

STATUS_ENUM = frozenset({HEALTHY, DEGRADED, STALE, UNAVAILABLE, HISTORICAL_ONLY, REVISED})
CONFIDENCE_ENUM = frozenset({"HIGH", "MEDIUM", "LOW", "INSUFFICIENT"})

# worst-of severity order (spec §1: "HEALTHY < DEGRADED < STALE < UNAVAILABLE"). REVISED is
# deliberately absent here — it folds to DEGRADED's severity for any ROLLUP computation
# (worst-of / desk backstop) while the LEG's own record keeps the literal "REVISED" label
# (spec §1 last line: "REVISED maps to DEGRADED severity for the rollup but keeps its own
# label on the leg"). HISTORICAL_ONLY never enters a severity comparison (excluded from
# worst-of entirely, spec §1) so it carries no numeric rank.
_SEVERITY: dict[str, int] = {HEALTHY: 0, DEGRADED: 1, STALE: 2, UNAVAILABLE: 3}

# nb_aggregate is handled by name (always HISTORICAL_ONLY, frozen 2024-08-16 — do_not_redo);
# lhb_inst_seats is handled by name (event-window, no stale state by design). Every other
# leg_id is a calendar-gap leg; sb_aggregate/hk_sb_holdings measure against the HK calendar,
# cn_large_order_proxy against the CN calendar (masterplan §3 per-leg market column).
_CN_CALENDAR_LEGS = frozenset({"cn_large_order_proxy"})
_HK_CALENDAR_LEGS = frozenset({"sb_aggregate", "hk_sb_holdings"})
_CALENDAR_LEGS = _CN_CALENDAR_LEGS | _HK_CALENDAR_LEGS
# coverage-collapse only applies to legs with a real scored/observed COUNT (spec §1); the
# southbound aggregate is a single scalar channel, not a population of scored names.
_COVERAGE_CHECK_LEGS = frozenset({"cn_large_order_proxy", "hk_sb_holdings"})
# legs excluded from the desk-level wall-clock backstop and from worst-of rollup: a leg
# frozen ON PURPOSE (HISTORICAL_ONLY, checked by status) or with NO stale state by design
# (lhb_inst_seats, checked by id — "a quiet Dragon-Tiger stretch is market behavior, not
# degradation", spec §1).
_BACKSTOP_EXEMPT_LEGS = frozenset({"lhb_inst_seats"})
_ROLLUP_EXEMPT_LEGS = frozenset({"lhb_inst_seats"})

#: desk-level wall-clock backstop — the ONLY calendar-day rule (spec §1 last bullet). Kept
#: as a same-value sibling constant to lib.desk_guard.DESK_MAX_AGE_DAYS (10) rather than an
#: import: desk_guard is explicitly OUT OF SCOPE for this wave (its own advisory path is
#: untouched — W2_SPEC.md OUT OF SCOPE), and this module must not couple its binding
#: publication law to a constant owned by a different, advisory-only guard.
DESK_BACKSTOP_DAYS = 10


def _parse_date(value):
    """Parse an ISO ``YYYY-MM-DD`` stamp, or None when it is not one.

    A pure, module-level copy of ``lib.desk_guard._as_date`` / the identical helper already
    duplicated into ``engine.flow_observatory.contract`` (S8 repair there) — this module has
    the same "no cross-module private-import" constraint (module-layout freeze) and the same
    two-line parse is cheaper to repeat than to couple.
    """
    from datetime import date, datetime

    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ── per-leg classification (spec §1) ────────────────────────────────────────────────
def classify_leg(leg_id: str, effective_date, coverage: dict[str, Any] | None,
                 panels_meta: dict[str, Any] | None, today) -> dict[str, Any]:
    """One leg's {status, confidence, reasons, gap_sessions} (spec §1, frozen rules).

    ``coverage`` is the leg's own coverage dict (``{"n_observed": ..., ...}`` — the same
    shape ``contract.build_sources`` already assembles per leg). ``panels_meta`` is a plain
    dict of whatever this leg needs beyond its own coverage/date — the pseudosignature in
    the spec names it generically, so this module defines its shape here (documented per
    key below) rather than inventing a wider signature the spec did not pin:

      * ``present`` (bool, optional) — whether the panel/store was actually readable this
        run, distinct from a readable-but-stale date. Defaults to ``effective_date is not
        None`` when omitted (the ordinary case: no date at all IS "not present").
      * ``prev_effective_date`` (str|None) — the SAME leg's effective_date from the previous
        state_log entry (REVISED detection input).
      * ``trailing_median`` / ``trailing_n`` (float|None, int) — the leg's trailing-20-session
        coverage median and how many sessions fed it (coverage-collapse input; INSUFFICIENT
        history <5 sessions skips the check per spec).

    ``today`` is the wall-clock anchor used to find each calendar leg's "newest session ≤
    today" — a legitimate side-input (not hidden I/O: the caller supplies it explicitly, so
    this function stays pure/deterministic for a given ``today``). ``today=None`` (the
    legacy/no-anchor case some callers use) skips gap measurement entirely and reports
    ``gap=0`` — i.e. "nothing to measure staleness against, assume current" — never a
    fabricated STALE/DEGRADED read from an anchor the caller did not supply.
    """
    coverage = coverage or {}
    meta = panels_meta or {}

    if leg_id == "nb_aggregate":
        # frozen 2024-08-16, never rebuilt (do_not_redo) — never stale by construction.
        return {"status": HISTORICAL_ONLY, "confidence": "HIGH",
                "reasons": ["discontinued"], "gap_sessions": None}

    if leg_id == "lhb_inst_seats":
        present = meta.get("present")
        if present is None:
            present = effective_date is not None
        if not present:
            return {"status": UNAVAILABLE, "confidence": "INSUFFICIENT",
                    "reasons": ["unreadable_as_of"], "gap_sessions": None}
        # event-window source: HEALTHY with cadence "event-window" — NO stale state (a
        # quiet Dragon-Tiger stretch is market behavior, not degradation, spec §1).
        return {"status": HEALTHY, "confidence": "HIGH",
                "reasons": ["event_window"], "gap_sessions": None}

    if leg_id not in _CALENDAR_LEGS:
        raise ValueError(f"quality.classify_leg: unknown leg_id {leg_id!r}")

    ed = _parse_date(effective_date)
    present = meta.get("present", effective_date is not None)
    if not present or ed is None:
        return {"status": UNAVAILABLE, "confidence": "INSUFFICIENT",
                "reasons": ["unreadable_as_of"], "gap_sessions": None}

    calendar = cn_calendar if leg_id in _CN_CALENDAR_LEGS else hk_calendar
    today_d = _parse_date(today)
    if today_d is None:
        gap = 0
    else:
        newest = calendar.last_session_on_or_before(today_d)
        gap = calendar.sessions_between(ed, newest)

    reasons: list[str] = []
    if leg_id == "hk_sb_holdings":
        # expected T−1: HEALTHY through gap<=1 (spec §1 — "expected T−1 ... is HEALTHY
        # there, not degraded"), DEGRADED at 2, STALE at 3+.
        if gap <= 1:
            status, confidence = HEALTHY, "HIGH"
            if gap == 1:
                reasons = ["expected_t_minus_1"]
        elif gap == 2:
            status, confidence, reasons = DEGRADED, "MEDIUM", ["behind_expected_lag"]
        else:
            status, confidence, reasons = STALE, "LOW", ["behind_expected_lag"]
    else:  # cn_large_order_proxy / sb_aggregate — gap0 HEALTHY, gap1 DEGRADED, gap>=2 STALE
        if gap == 0:
            status, confidence = HEALTHY, "HIGH"
        elif gap == 1:
            status, confidence, reasons = DEGRADED, "MEDIUM", ["one_session_behind"]
        else:
            status, confidence, reasons = STALE, "LOW", ["sessions_behind"]

    # coverage collapse (cn_large_order_proxy, hk_sb_holdings only — spec §1).
    if leg_id in _COVERAGE_CHECK_LEGS:
        scored = coverage.get("n_observed")
        trailing_median = meta.get("trailing_median")
        trailing_n = meta.get("trailing_n") or 0
        if 0 < trailing_n < 5:
            # INSUFFICIENT history: skip the collapse check, but say so via confidence.
            if confidence == "HIGH":
                confidence = "MEDIUM"
        elif trailing_n >= 5 and scored is not None and trailing_median:
            if scored < 0.7 * trailing_median:
                if _SEVERITY.get(status, 0) < _SEVERITY[DEGRADED]:
                    status = DEGRADED
                reasons = list(reasons) + ["coverage_collapse"]
                confidence = "LOW"

    # REVISED (W2 minimal, spec §1): a backward-moving effective_date vs the leg's own
    # previous state_log entry overrides the gap-based read — the number that is "current"
    # today is not the one that was current before, so what dropped is trust in the CURRENT
    # publication, not merely its recency. Full value-level revision receipts are W3.
    prev_ed = _parse_date(meta.get("prev_effective_date"))
    if prev_ed is not None and ed < prev_ed:
        status, confidence, reasons = REVISED, "LOW", ["date_regression"]

    return {"status": status, "confidence": confidence, "reasons": reasons, "gap_sessions": gap}


# ── desk-level wall-clock backstop (spec §1 last bullet; the ONLY calendar-day rule) ────
def apply_desk_backstop(leg_results: dict[str, dict[str, Any]],
                        leg_effective_dates: dict[str, Any], today,
                        backstop_days: int = DESK_BACKSTOP_DAYS) -> dict[str, dict[str, Any]]:
    """Floor every live leg to at least STALE when the desk's OWN freshest live leg is more
    than ``backstop_days`` CALENDAR days old (total-freeze catch-all — the case a purely
    per-leg relative gate cannot see, mirroring ``lib.desk_guard``'s existing backstop
    without importing it — desk_guard's own advisory path is out of scope for this wave).

    ``lhb_inst_seats`` (no stale state by design) and any leg already HISTORICAL_ONLY are
    exempt. Returns a NEW dict — never mutates the caller's ``leg_results``.
    """
    today_d = _parse_date(today)
    if today_d is None:
        return leg_results
    live_dates = []
    for leg_id, raw_date in (leg_effective_dates or {}).items():
        if leg_id in _BACKSTOP_EXEMPT_LEGS:
            continue
        if (leg_results.get(leg_id) or {}).get("status") == HISTORICAL_ONLY:
            continue
        d = _parse_date(raw_date)
        if d is not None:
            live_dates.append(d)
    if not live_dates:
        return leg_results
    newest = max(live_dates)
    if (today_d - newest).days <= backstop_days:
        return leg_results

    out: dict[str, dict[str, Any]] = {}
    for leg_id, result in leg_results.items():
        if leg_id in _BACKSTOP_EXEMPT_LEGS or result.get("status") == HISTORICAL_ONLY:
            out[leg_id] = result
            continue
        if _SEVERITY.get(result.get("status"), 0) < _SEVERITY[STALE]:
            out[leg_id] = {**result, "status": STALE, "confidence": "LOW",
                          "reasons": list(result.get("reasons") or []) + ["desk_backstop"]}
        else:
            out[leg_id] = result
    return out


# ── desk-wide rollup (spec §1: publication_state = worst-of live legs) ─────────────────
def _rollup_severity(status: str | None) -> int:
    if status == REVISED:
        status = DEGRADED
    return _SEVERITY.get(status, 0)


def publication_state(leg_statuses: dict[str, str | None]) -> str:
    """worst-of LIVE legs (order HEALTHY < DEGRADED < STALE < UNAVAILABLE); HISTORICAL_ONLY
    and event-window legs (``lhb_inst_seats``) are excluded from the comparison entirely
    (spec §1). REVISED folds to DEGRADED severity here but its OWN leg keeps the literal
    "REVISED" label (``sources[].status`` stays REVISED; only this desk-wide rollup number
    treats it as DEGRADED-severity, matching the spec's 4-value HEALTHY<DEGRADED<STALE<
    UNAVAILABLE ordering, which does not itself list REVISED as a rollup bucket).

    No live/eligible leg at all (every leg HISTORICAL_ONLY or event-window) is the one edge
    case where the desk itself is reported HISTORICAL_ONLY — never a fabricated HEALTHY for
    a desk with nothing live to be healthy ABOUT.
    """
    candidates = [s for lid, s in (leg_statuses or {}).items()
                 if lid not in _ROLLUP_EXEMPT_LEGS and s not in (None, HISTORICAL_ONLY)]
    if not candidates:
        return HISTORICAL_ONLY
    return max(candidates, key=_rollup_severity)


def consecutive_degraded_sessions(log_rows: list[dict[str, Any]], current_session: str | None,
                                  current_publication_state: str | None) -> int:
    """How many sessions in a row (including the current one) have NOT been HEALTHY.

    Walks ``log_rows``' own logged ``health.publication_state`` backward from the newest
    entry strictly before ``current_session``, stopping at the first HEALTHY/HISTORICAL_ONLY/
    missing entry. Returns 0 outright when the CURRENT session is itself healthy — a streak
    that just ended is not an escalating one.
    """
    if current_publication_state in (HEALTHY, HISTORICAL_ONLY, None) or not current_session:
        return 0
    rows = sorted((r for r in (log_rows or []) if r.get("session") and r["session"] < current_session),
                  key=lambda r: r["session"], reverse=True)
    streak = 1
    for r in rows:
        prior = (r.get("health") or {}).get("publication_state")
        if prior in (None, HEALTHY, HISTORICAL_ONLY):
            break
        streak += 1
    return streak


def compute_health(pub_state: str, leg_results: dict[str, dict[str, Any]],
                   log_rows: list[dict[str, Any]], current_session: str | None) -> dict[str, Any]:
    """The desk-wide ``health`` block (spec §2): ``{publication_state,
    consecutive_degraded_sessions, reasons}`` — exactly the three keys the spec's shape
    shows; per-leg detail lives in ``sources[]``, not duplicated here."""
    reasons = sorted({reason for res in (leg_results or {}).values()
                      for reason in (res.get("reasons") or [])
                      if res.get("status") not in (HEALTHY, HISTORICAL_ONLY)})
    return {
        "publication_state": pub_state,
        "consecutive_degraded_sessions": consecutive_degraded_sessions(
            log_rows, current_session, pub_state),
        "reasons": reasons,
    }


def should_escalate(health: dict[str, Any] | None) -> bool:
    """≥2-consecutive-session degradation escalates to ::error (spec §2)."""
    return bool(health and (health.get("consecutive_degraded_sessions") or 0) >= 2)
