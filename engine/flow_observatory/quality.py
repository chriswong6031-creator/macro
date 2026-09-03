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

W2 REPAIR ROUND (B1/B2/S1/S2): three defects fixed in this pass, each with its own note at
the call site below —

  * B1 — the gap math used to walk ``last_session_on_or_before(today)`` against a bare
    calendar date, which (a) counts a session that has not yet CLOSED as already published
    (no settle-buffer awareness — the exact "forbidden shape" ``lib.cn_calendar.sessions_
    behind``'s own docstring names) and (b) fed a bare UTC date straight into an Asia
    calendar with no timezone conversion at all. ``classify_leg`` now takes ``now`` (a real
    instant, ideally a tz-aware ``datetime``) and routes it through the calendar's own
    ``expected_last_session``/``sessions_behind`` — the same reader every other staleness
    surface in the estate already uses.
  * B2 — the escalation streak (:func:`consecutive_degraded_sessions`) used to walk
    ``log_rows`` by ``session`` (the MARKET session), which never advances during a genuine
    freeze — so the streak could never grow past 1 in the exact #4676 shape it exists to
    catch. It now walks a per-BUILD-RUN accelerator (``health.runs``, keyed by
    ``written_at`` date) that ``engine.flow_observatory.changes.append_state_log`` carries
    forward across every build regardless of whether the session itself advanced.
  * S1 — a backward-moving ``effective_date`` (REVISED) used to REPLACE the gap-based status
    outright, which could downgrade an already-STALE read to a milder-looking "revised" one.
    It is now a FLAG (``revised: True`` on the leg) that can only ever WORSEN the gap-based
    status (floored at DEGRADED), never mask it; the literal "REVISED" status string is
    reserved for the one case where nothing else would have surfaced the leg's trouble at
    all (the gap verdict alone reads HEALTHY).
  * S2 — ``lhb_inst_seats`` used to be fully excluded from :func:`publication_state`'s
    worst-of rollup regardless of its own status. An UNREADABLE ``lhb_inst_seats`` really
    does degrade the desk, so it now ENTERS the rollup — capped at DEGRADED severity/value so
    the event-window leg alone can never push the desk-wide read to STALE/UNAVAILABLE while
    every primary lens is current.
"""
from __future__ import annotations

from datetime import date as _date, datetime as _datetime
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
# legs excluded from the desk-level wall-clock backstop: a leg frozen ON PURPOSE
# (HISTORICAL_ONLY, checked by status) or with NO stale state by design (lhb_inst_seats,
# checked by id — "a quiet Dragon-Tiger stretch is market behavior, not degradation", spec
# §1). NOTE (S2): this is the BACKSTOP exemption only — lhb_inst_seats' participation in the
# publication_state ROLLUP is a separate, capped (not excluded) rule; see
# ``_ROLLUP_VALUE_CAP`` below.
_BACKSTOP_EXEMPT_LEGS = frozenset({"lhb_inst_seats"})
# S2: lhb_inst_seats' HEALTHY reading (its ordinary "no stale state by design" event-window
# semantics — a quiet Dragon-Tiger stretch) is STILL excluded from the rollup entirely, same
# as before S2. What changes is its UNAVAILABLE (unreadable) reading: that no longer gets
# the SAME blanket exclusion (an unreadable store is not "a quiet stretch", it is a real
# gap), so it now ENTERS the rollup — capped at DEGRADED severity/value via
# ``_ROLLUP_VALUE_CAP`` below, so the event-window leg alone can never push the desk-wide
# read all the way to STALE/UNAVAILABLE while every primary lens is current.
_ROLLUP_EXCLUDE_WHEN_HEALTHY = frozenset({"lhb_inst_seats"})
_ROLLUP_VALUE_CAP: dict[str, str] = {"lhb_inst_seats": DEGRADED}

#: desk-level wall-clock backstop — the ONLY calendar-day rule (spec §1 last bullet). Kept
#: as a same-value sibling constant to lib.desk_guard.DESK_MAX_AGE_DAYS (10) rather than an
#: import: desk_guard is explicitly OUT OF SCOPE for this wave (its own advisory path is
#: untouched — W2_SPEC.md OUT OF SCOPE), and this module must not couple its binding
#: publication law to a constant owned by a different, advisory-only guard.
DESK_BACKSTOP_DAYS = 10

#: B2 — how many per-build-run records ``health.runs`` keeps (append-only, oldest dropped).
RUNS_HISTORY_CAP = 30


def _parse_date(value):
    """Parse an ISO ``YYYY-MM-DD`` stamp, or None when it is not one.

    A pure, module-level copy of ``lib.desk_guard._as_date`` / the identical helper already
    duplicated into ``engine.flow_observatory.contract`` (S8 repair there) — this module has
    the same "no cross-module private-import" constraint (module-layout freeze) and the same
    two-line parse is cheaper to repeat than to couple.
    """
    if isinstance(value, _date):
        return value
    if not value:
        return None
    try:
        return _datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _newest_completed_session(calendar, now):
    """The newest session a store SHOULD already hold, for the wall-clock anchor ``now``
    (B1 repair — the actual gap-math fix).

    ``now`` is either:
      * a real ``datetime`` (tz-aware, or naive treated as UTC per the pipeline convention)
        — the CORRECT path, routed through the calendar's own ``expected_last_session``,
        which applies the settle-buffer (a session that has not yet closed locally does not
        count as "should be published yet") AND the UTC-to-local conversion in one call. This
        is the path every PRODUCTION caller (``contract.build_v2`` /
        ``scripts.build_flow_velocity``) must use — see the module docstring's B1 note.
      * a bare ``date`` with no time-of-day — a LEGACY shim for callers/tests that only have
        a calendar date, not a clock reading. With no time-of-day to test against a settle
        buffer, the least-invented reading is "already settled": equivalent to
        ``calendar.last_session_on_or_before(now)`` directly. This preserves the pre-B1
        meaning for date-only fixtures (coverage-collapse, REVISED, historical-only, etc. —
        none of which are testing settle-buffer timing) while the real production bug (a
        bare UTC date silently skipping the settle buffer) is closed at the one place it
        actually mattered: the real wall-clock build anchor.
    """
    if isinstance(now, _datetime):
        return calendar.expected_last_session(now)
    return calendar.last_session_on_or_before(now)


# ── per-leg classification (spec §1) ────────────────────────────────────────────────
def classify_leg(leg_id: str, effective_date, coverage: dict[str, Any] | None,
                 panels_meta: dict[str, Any] | None, now) -> dict[str, Any]:
    """One leg's {status, confidence, reasons, gap_sessions, revised} (spec §1, frozen
    rules; ``revised`` added by the S1 repair — see module docstring).

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

    ``now`` (B1 repair) is the wall-clock anchor used to find each calendar leg's "newest
    session that should already be published" — a legitimate side-input (not hidden I/O: the
    caller supplies it explicitly, so this function stays pure/deterministic for a given
    ``now``). It may be a real ``datetime`` (the correct production shape — routed through
    the calendar's own settle-buffer-aware ``expected_last_session``) or a bare ``date``
    (legacy shim, see :func:`_newest_completed_session`). ``now=None`` (the legacy/no-anchor
    case some callers use) skips gap measurement entirely and reports ``gap=0`` — i.e.
    "nothing to measure staleness against, assume current" — never a fabricated
    STALE/DEGRADED read from an anchor the caller did not supply.
    """
    coverage = coverage or {}
    meta = panels_meta or {}

    if leg_id == "nb_aggregate":
        # frozen 2024-08-16, never rebuilt (do_not_redo) — never stale by construction.
        return {"status": HISTORICAL_ONLY, "confidence": "HIGH",
                "reasons": ["discontinued"], "gap_sessions": None, "revised": False}

    if leg_id == "lhb_inst_seats":
        present = meta.get("present")
        if present is None:
            present = effective_date is not None
        if not present:
            return {"status": UNAVAILABLE, "confidence": "INSUFFICIENT",
                    "reasons": ["unreadable_as_of"], "gap_sessions": None, "revised": False}
        # event-window source: HEALTHY with cadence "event-window" — NO stale state (a
        # quiet Dragon-Tiger stretch is market behavior, not degradation, spec §1).
        return {"status": HEALTHY, "confidence": "HIGH",
                "reasons": ["event_window"], "gap_sessions": None, "revised": False}

    if leg_id not in _CALENDAR_LEGS:
        raise ValueError(f"quality.classify_leg: unknown leg_id {leg_id!r}")

    ed = _parse_date(effective_date)
    present = meta.get("present", effective_date is not None)
    if not present or ed is None:
        return {"status": UNAVAILABLE, "confidence": "INSUFFICIENT",
                "reasons": ["unreadable_as_of"], "gap_sessions": None, "revised": False}

    calendar = cn_calendar if leg_id in _CN_CALENDAR_LEGS else hk_calendar
    if now is None:
        gap = 0
    else:
        newest = _newest_completed_session(calendar, now)
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

    # S1 REVISED repair: a backward-moving effective_date is a FLAG, never a status override
    # that can mask staleness. Previously this REPLACED the gap-based status outright with a
    # bare "REVISED", which could downgrade an already-STALE/UNAVAILABLE read to look like a
    # milder, distinct case — exactly the "stale reads as confidently current" failure this
    # module exists to prevent. The gap status above is computed FIRST; a detected regression
    # can only ever WORSEN it (floored at DEGRADED), never replace a worse read. The literal
    # "REVISED" status string is reserved for the one case where nothing else would have
    # surfaced this leg's trouble at all: the gap verdict alone reads HEALTHY.
    revised = False
    prev_ed = _parse_date(meta.get("prev_effective_date"))
    if prev_ed is not None and ed < prev_ed:
        revised = True
        reasons = list(reasons) + ["date_regression"]
        confidence = "LOW"
        if status == HEALTHY:
            status = REVISED
        else:
            status = max((status, DEGRADED), key=lambda s: _SEVERITY.get(s, 0))

    return {"status": status, "confidence": confidence, "reasons": reasons,
            "gap_sessions": gap, "revised": revised}


# ── desk-level wall-clock backstop (spec §1 last bullet; the ONLY calendar-day rule) ────
def apply_desk_backstop(leg_results: dict[str, dict[str, Any]],
                        leg_effective_dates: dict[str, Any], today,
                        backstop_days: int = DESK_BACKSTOP_DAYS) -> dict[str, dict[str, Any]]:
    """Floor every live leg to at least STALE when the desk's OWN freshest live leg is more
    than ``backstop_days`` CALENDAR days old (total-freeze catch-all — the case a purely
    per-leg relative gate cannot see, mirroring ``lib.desk_guard``'s existing backstop
    without importing it — desk_guard's own advisory path is out of scope for this wave).

    ``today`` is a bare calendar ``date`` (or an ISO string) — this is the ONE calendar-day
    rule in the module (spec §1 last bullet) and is deliberately NOT session-aware, so it
    does not need the B1 datetime/settle-buffer treatment ``classify_leg`` now requires; a
    10-day budget is coarse enough that a UTC-vs-local day boundary cannot itself flip it.

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
def _rollup_entry(leg_id: str, status: str | None) -> tuple[int, str] | None:
    """(severity, emitted_value) for one leg's contribution to :func:`publication_state`, or
    None when the leg is excluded from the rollup entirely.

    Exclusions: a missing/None status, HISTORICAL_ONLY (spec §1's original exclusion,
    unchanged), and — S2 — ``lhb_inst_seats`` reading its own ordinary HEALTHY/event-window
    state (a quiet Dragon-Tiger stretch is market behavior, not degradation; this half of
    the original exclusion is UNCHANGED by S2).

    S1: REVISED always EMITS as DEGRADED here — "never emit a literal REVISED top-level
    value" — so a REVISED leg can win the worst-of comparison without ever surfacing the
    literal string "REVISED" as the desk-wide ``publication_state``.

    S2: an UNAVAILABLE (or otherwise non-HEALTHY) ``lhb_inst_seats`` is NO LONGER given the
    same blanket exclusion — an unreadable store is a real gap, not a quiet stretch — so it
    now ENTERS the rollup, capped at DEGRADED severity/value (``_ROLLUP_VALUE_CAP``) so it
    can never on its own push the desk-wide read to STALE/UNAVAILABLE while every primary
    lens is current. Every other leg contributes its FULL severity, uncapped.
    """
    if status in (None, HISTORICAL_ONLY):
        return None
    if status == HEALTHY and leg_id in _ROLLUP_EXCLUDE_WHEN_HEALTHY:
        return None
    value = DEGRADED if status == REVISED else status
    cap = _ROLLUP_VALUE_CAP.get(leg_id)
    if cap is not None and _SEVERITY.get(value, 0) > _SEVERITY.get(cap, 0):
        value = cap
    return _SEVERITY.get(value, 0), value


def publication_state(leg_statuses: dict[str, str | None]) -> str:
    """worst-of LIVE legs (order HEALTHY < DEGRADED < STALE < UNAVAILABLE); HISTORICAL_ONLY
    legs are excluded from the comparison entirely (spec §1). See :func:`_rollup_entry` for
    the S1 (REVISED never headlines) and S2 (lhb_inst_seats capped-in, not excluded) repairs.

    No live/eligible leg at all (every leg HISTORICAL_ONLY) is the one edge case where the
    desk itself is reported HISTORICAL_ONLY — never a fabricated HEALTHY for a desk with
    nothing live to be healthy ABOUT.
    """
    entries = [_rollup_entry(lid, s) for lid, s in (leg_statuses or {}).items()]
    entries = [e for e in entries if e is not None]
    if not entries:
        return HISTORICAL_ONLY
    return max(entries, key=lambda e: e[0])[1]


# ── B2: per-BUILD-RUN escalation streak (never keyed on the market session) ────────────
def _extract_runs(log_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The append-only per-build-run history (``health.runs``) from the state_log row with
    the newest ``written_at`` (B2 repair — see module docstring). ``append_state_log``
    carries this list FORWARD across every build, including a rebuild of the SAME session
    (a frozen ``market_session`` idempotently replaces its own row, but the row's own
    ``health.runs`` keeps growing) — so the newest-WRITTEN row is always authoritative,
    never the newest-SESSION row (those can be the same row for many consecutive nights
    during a freeze, which is exactly the shape that broke the OLD session-keyed walk).

    Returns ``[]`` for pre-B2 state_log content (no row carries ``health.runs`` yet) or an
    empty/missing log — an honest "no run history" rather than a fabricated streak.
    """
    candidates = [r for r in (log_rows or []) if r.get("written_at")]
    if not candidates:
        return []
    newest = max(candidates, key=lambda r: r["written_at"])
    return list((newest.get("health") or {}).get("runs") or [])


def consecutive_degraded_sessions(log_rows: list[dict[str, Any]], current_run_date: str | None,
                                  current_publication_state: str | None) -> int:
    """How many consecutive BUILD RUNS (by DISTINCT ``run_date``, including the current one)
    have NOT been HEALTHY (B2 repair, W2_SPEC.md §2).

    Previously this walked ``log_rows``' ``session`` key — the MARKET session, not the build
    RUN. During a genuine multi-day freeze ``market_session`` stops advancing entirely (the
    same frozen trading date every night), so the old walk kept comparing that one logged
    ``session`` entry to itself and the streak could never grow past 1 — dead in the exact
    #4676 shape this counter exists to catch. Runs are now read from :func:`_extract_runs`
    (the log's own append-only accelerator, which survives the per-session idempotent
    REPLACE — see ``engine.flow_observatory.changes.append_state_log``).

    ``current_run_date`` is a plain ``YYYY-MM-DD`` string (the CURRENT build's own date,
    e.g. ``generated_at[:10]``) — distinct from ``current_session`` (the market date), which
    is exactly the distinction B2 exists to enforce. Returns 0 outright when the CURRENT run
    is itself healthy/historical or the run date is missing — a streak that just ended, or
    was never measurable, is not an escalating one.
    """
    if current_publication_state in (HEALTHY, HISTORICAL_ONLY, None) or not current_run_date:
        return 0
    runs = [r for r in _extract_runs(log_rows)
           if r.get("run_date") and r["run_date"] < current_run_date]
    runs.sort(key=lambda r: r["run_date"], reverse=True)
    streak = 1
    for r in runs:
        prior = r.get("publication_state")
        if prior in (None, HEALTHY, HISTORICAL_ONLY):
            break
        streak += 1
    return streak


def leg_consecutive_bad_runs(log_rows: list[dict[str, Any]], leg_id: str,
                             current_run_date: str | None, current_status: str | None) -> int:
    """Per-leg counterpart to :func:`consecutive_degraded_sessions` (B2): how many
    consecutive BUILD RUNS (by ``run_date``, including the current one) this ONE leg has
    read DEGRADED-or-worse. Walks the SAME ``health.runs`` accelerator, keyed per-leg via
    ``runs[].legs[leg_id]`` rather than the desk-wide ``publication_state`` — a leg's own
    streak can differ from the desk's worst-of rollup (one leg may have been STALE for nine
    runs while another only just went DEGRADED today), and the escalation annotation names
    each leg's OWN run count (SF-8 repair — the annotation line reads "<leg> <status> ×<n>
    runs", never a borrowed desk-wide count)."""
    if current_status in (HEALTHY, HISTORICAL_ONLY, None) or not current_run_date:
        return 0
    runs = [r for r in _extract_runs(log_rows)
           if r.get("run_date") and r["run_date"] < current_run_date]
    runs.sort(key=lambda r: r["run_date"], reverse=True)
    streak = 1
    for r in runs:
        prior = (r.get("legs") or {}).get(leg_id)
        if prior in (None, HEALTHY, HISTORICAL_ONLY):
            break
        streak += 1
    return streak


def compute_health(pub_state: str, leg_results: dict[str, dict[str, Any]],
                   log_rows: list[dict[str, Any]], current_run_date: str | None) -> dict[str, Any]:
    """The desk-wide ``health`` block (spec §2): ``{publication_state,
    consecutive_degraded_sessions, reasons}`` — exactly the three keys the spec's shape
    shows; per-leg detail lives in ``sources[]``, not duplicated here.

    ``current_run_date`` (B2 repair) is the CURRENT build's own date (``generated_at[:10]``),
    never the market session — see :func:`consecutive_degraded_sessions`.
    """
    reasons = sorted({reason for res in (leg_results or {}).values()
                      for reason in (res.get("reasons") or [])
                      if res.get("status") not in (HEALTHY, HISTORICAL_ONLY)})
    return {
        "publication_state": pub_state,
        "consecutive_degraded_sessions": consecutive_degraded_sessions(
            log_rows, current_run_date, pub_state),
        "reasons": reasons,
    }


def should_escalate(health: dict[str, Any] | None) -> bool:
    """≥2-consecutive-RUN degradation escalates to ::error (spec §2)."""
    return bool(health and (health.get("consecutive_degraded_sessions") or 0) >= 2)
