"""engine.flow_observatory.changes — state_log.jsonl (W1 minimal precursor) + change_summary.

``data/flow_observatory/state_log.jsonl`` is the minimal precursor to W3's full
append-only observations ledger (masterplan §5): one line per valid market session,
carrying just enough per-theme state to derive rank_change / state_started /
state_age_sessions / prior_state and the "what changed today" diff going forward, with
honest "first tracked session" nulls until history accrues.

Advance gate: ``engine.ledger_lane.asia_advance_enabled() or nightly_advance_enabled()``
— house law, the group_pulse precedent (``engine/group_pulse.py``
``advance_episode_ledger``): nightly/asia-close are the SOLE advancers of forward
ledgers; intraday/manual lanes compute and discard. Idempotent per session: a rerun on
the same session REPLACES that session's own line (never duplicates it); every other
session's line is left byte-identical.

W3 module-layout split (masterplan §4 freeze): this file (``state_log.jsonl`` +
``compute_changes``) stays the run/health journal and the "what changed today" diff
entry point. ``engine.flow_observatory.history`` (new) owns the full append-only,
revision-safe PRODUCT observation ledger (``data/flow_observatory/observations.parquet``)
that state age/onset/prior-state/rank-change and ``sources[].first_known_at`` derive from
once it is deep enough — ``compute_changes`` below now reads FROM the ledger when
``ledger_rows`` is supplied and holds ≥2 theme sessions, falling back to this file's
state_log path otherwise (both paths tested, spec §2/§3 test 10).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.ledger_lane import asia_advance_enabled, nightly_advance_enabled

log = logging.getLogger(__name__)

STATE_LOG_REL = Path("flow_observatory") / "state_log.jsonl"


def state_log_path(data_root: Path) -> Path:
    return Path(data_root) / STATE_LOG_REL


def advance_enabled() -> bool:
    return bool(asia_advance_enabled() or nightly_advance_enabled())


def read_state_log(data_root: Path) -> list[dict[str, Any]]:
    """Every readable line, oldest-first. A corrupt line is skipped, never fatal — this
    file is a derived accelerator for change/rank history, not the system of record."""
    p = state_log_path(data_root)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("flow_observatory: state_log unreadable (%s)", e)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("flow_observatory: skipping unparseable state_log line")
    out.sort(key=lambda r: r.get("session") or "")
    return out


def previous_valid_entry(log_rows: list[dict[str, Any]],
                         before_session: str | None = None) -> dict[str, Any] | None:
    """The newest entry strictly before ``before_session`` (or overall newest when
    ``before_session`` is None) — "the previous valid market session" record."""
    rows = [r for r in log_rows if r.get("session")]
    if before_session:
        rows = [r for r in rows if r["session"] < before_session]
    if not rows:
        return None
    return max(rows, key=lambda r: r["session"])


def theme_state_history(theme_id: str, current_quadrant: str, log_rows: list[dict[str, Any]],
                        current_session: str) -> dict[str, Any]:
    """{state_started, state_age_sessions, prior_state, note} for one theme (spec §1.3).

    ``state_log`` stores one point-in-time record per session, never a running age, so the
    age/onset are DERIVED by walking backward from the session immediately before
    ``current_session`` while the theme's quadrant stays unchanged. No prior line at all
    (a fresh install, or a theme absent from every logged session) yields the honest
    "first tracked session" null rather than a manufactured age of 0/1.
    """
    rows = sorted((r for r in log_rows if r.get("session") and r["session"] < current_session),
                  key=lambda r: r["session"], reverse=True)   # newest-first, strictly prior
    if not rows:
        return {"state_started": None, "state_age_sessions": None, "prior_state": None,
                "note": "first tracked session"}
    prior_rec = (rows[0].get("themes") or {}).get(theme_id)
    prior_state = prior_rec.get("quadrant") if isinstance(prior_rec, dict) else None
    started, age = current_session, 1
    for r in rows:
        rec = (r.get("themes") or {}).get(theme_id)
        if not isinstance(rec, dict) or rec.get("quadrant") != current_quadrant:
            break
        started, age = r["session"], age + 1
    return {"state_started": started, "state_age_sessions": age, "prior_state": prior_state,
            "note": None}


_QUALITY_CHANGE_STATUSES = frozenset({"DEGRADED", "STALE", "UNAVAILABLE", "REVISED"})


def leg_quality_history(log_rows: list[dict[str, Any]], leg_id: str,
                        before_session: str | None) -> dict[str, Any]:
    """{'prev_effective_date', 'trailing_median', 'trailing_n'} for one source leg — the
    W2 coverage-collapse and REVISED-detection inputs (``engine.flow_observatory.quality``),
    derived from state_log ``health.legs[leg_id]`` records strictly before
    ``before_session``. Honest empty dict (never a fabricated 0) when there is no prior
    session at all — ``quality.classify_leg`` treats an absent key as "no history yet",
    which correctly skips both checks rather than reading a missing history as a collapse.
    """
    if not before_session:
        return {}
    rows = sorted((r for r in log_rows if r.get("session") and r["session"] < before_session),
                  key=lambda r: r["session"], reverse=True)
    if not rows:
        return {}
    prev_leg = ((rows[0].get("health") or {}).get("legs") or {}).get(leg_id) or {}
    covs: list[float] = []
    for r in rows[:20]:
        leg = ((r.get("health") or {}).get("legs") or {}).get(leg_id) or {}
        n = leg.get("coverage_n")
        if isinstance(n, (int, float)) and not isinstance(n, bool):
            covs.append(n)
    trailing_median = None
    if covs:
        s = sorted(covs)
        mid = len(s) // 2
        trailing_median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return {"prev_effective_date": prev_leg.get("effective_date"),
           "trailing_median": trailing_median, "trailing_n": len(covs)}


def _theme_changes_from_state_log(current: dict[str, Any], log_rows: list[dict[str, Any]],
                                  session: str | None, revised_ids: set[str]
                                  ) -> tuple[list[dict], list[dict], str | None, str | None]:
    """W1/W2 path (unchanged behavior) — transitions/rank_movers vs the previous valid
    state_log entry. Returns ``(transitions, rank_movers, previous_valid_session, reason)``;
    ``previous_valid_session`` is ``None`` (with reason ``"no_previous_snapshot"``) when
    there is no prior entry at all."""
    prev = previous_valid_entry(log_rows, before_session=session)
    if prev is None:
        return [], [], None, "no_previous_snapshot"
    cur_themes = current.get("themes") or {}
    prev_themes = prev.get("themes") or {}
    transitions: list[dict[str, Any]] = []
    rank_movers: list[dict[str, Any]] = []
    for tid, crec in cur_themes.items():
        if tid in revised_ids:
            continue  # a correction, not a fresh transition (spec §3 test 9)
        prec = prev_themes.get(tid)
        if not isinstance(prec, dict):
            continue
        cq, pq = crec.get("quadrant"), prec.get("quadrant")
        if cq is not None and pq is not None and cq != pq:
            transitions.append({"id": tid, "from_quadrant": pq, "to_quadrant": cq})
        cr, pr = crec.get("rank"), prec.get("rank")
        if cr is not None and pr is not None and abs(cr - pr) >= 3:
            rank_movers.append({"id": tid, "from_rank": pr, "to_rank": cr, "delta": cr - pr})
    return transitions, rank_movers, prev.get("session"), None


def _theme_changes_from_ledger(current: dict[str, Any], ledger_rows: list[dict[str, Any]],
                               session: str | None, revised_ids: set[str]
                               ) -> tuple[list[dict], list[dict], str | None, str | None]:
    """W3 path — transitions/rank_movers vs the ledger's own previous-valid-session
    snapshot (spec §2: "compute_changes gains the ledger as its transition/rank source").
    Same output shape as :func:`_theme_changes_from_state_log`, so callers cannot tell
    which path fired except by the returned ``previous_valid_session``.
    """
    from engine.flow_observatory import history as fo_history

    prev_session = fo_history.previous_valid_ledger_session(ledger_rows, "theme", session)
    if prev_session is None:
        return [], [], None, "no_previous_snapshot"
    prev_quadrants = fo_history.previous_values(ledger_rows, "theme", prev_session, "quadrant") or {}
    prev_ranks = fo_history.previous_values(ledger_rows, "theme", prev_session, "rank") or {}
    cur_themes = current.get("themes") or {}
    transitions: list[dict[str, Any]] = []
    rank_movers: list[dict[str, Any]] = []
    for tid, crec in cur_themes.items():
        if tid in revised_ids:
            continue  # a correction, not a fresh transition (spec §3 test 9)
        cq, pq = crec.get("quadrant"), prev_quadrants.get(tid)
        if cq is not None and pq is not None and cq != pq:
            transitions.append({"id": tid, "from_quadrant": pq, "to_quadrant": cq})
        cr, pr = crec.get("rank"), prev_ranks.get(tid)
        if cr is not None and pr is not None and abs(cr - pr) >= 3:
            rank_movers.append({"id": tid, "from_rank": pr, "to_rank": cr, "delta": cr - pr})
    return transitions, rank_movers, prev_session, None


def compute_changes(current: dict[str, Any], log_rows: list[dict[str, Any]], *,
                    ledger_rows: list[dict[str, Any]] | None = None,
                    revisions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """``change_summary`` (spec §1.6, extended W3 §2): transitions + rank movers + quality
    transitions + source_revisions vs the previous VALID session only (never the most
    recent calendar day — a lane that skipped a session must not manufacture a phantom
    transition across the gap it didn't log).

    ``current`` = ``{"session": "...", "themes": {id: {"quadrant","state","vel","rank","abs"}},
    "legs": {leg_id: status}}``. ``legs`` is optional (W1 callers omit it; quality_transitions
    is simply empty then). Missing log -> ALL-NULL + ``"no_previous_snapshot"`` reason;
    ``material_change`` is ``None`` (unknown), never ``False`` — "no data" and "nothing
    changed" are different claims and the field must not conflate them (spec §1.6 / §4
    missing≠zero law).

    W3: ``ledger_rows`` (the append-only observations ledger, read once at the top of the
    build — :mod:`engine.flow_observatory.history`) becomes the transition/rank source
    once it holds ≥2 distinct theme sessions (spec §2: "state_log summaries stay as
    fallback until the ledger has ≥2 sessions" — both paths are tested,
    :func:`_theme_changes_from_ledger` / :func:`_theme_changes_from_state_log`).
    ``revisions`` (``history.preview_revisions``/``append_observations`` receipts for THIS
    build) populate ``source_revisions[]`` directly and are EXCLUDED from ``transitions``/
    ``rank_movers`` for the same entity — a correction must produce a REVISED what-changed
    row, never ALSO a duplicate transition row (spec §3 test 9).
    """
    session = current.get("session")
    revisions = list(revisions or [])
    revised_ids = {r.get("id") for r in revisions if r.get("entity_kind") in (None, "theme")}
    from engine.flow_observatory import history as fo_history

    ledger_rows = ledger_rows or []
    ledger_ready = bool(ledger_rows) and fo_history.ledger_session_count(ledger_rows, "theme") >= 2
    if ledger_ready:
        transitions, rank_movers, prev_session, reason = _theme_changes_from_ledger(
            current, ledger_rows, session, revised_ids)
    else:
        transitions, rank_movers, prev_session, reason = _theme_changes_from_state_log(
            current, log_rows, session, revised_ids)

    if prev_session is None:
        return {"previous_valid_session": None, "material_change": None,
                "transitions": [], "rank_movers": [], "source_revisions": revisions,
                "quality_transitions": [], "reason": reason or "no_previous_snapshot"}

    # quality transitions (W2, spec §3 "what changed today"): a leg ENTERING DEGRADED/
    # STALE/UNAVAILABLE/REVISED since the previous valid session is a material change —
    # source quality drift is worth surfacing the same way a quadrant flip is. Unchanged by
    # W3 — this stays state_log-based (the per-BUILD leg-status journal), independent of
    # the theme transition source switch above.
    prev_entry = previous_valid_entry(log_rows, before_session=session)
    prev_legs = ((prev_entry.get("health") or {}).get("legs") or {}) if prev_entry else {}
    cur_legs = current.get("legs") or {}
    quality_transitions: list[dict[str, Any]] = []
    for leg_id, cur_status in cur_legs.items():
        prev_status = (prev_legs.get(leg_id) or {}).get("status")
        if cur_status in _QUALITY_CHANGE_STATUSES and cur_status != prev_status:
            quality_transitions.append({"kind": "quality", "id": leg_id,
                                        "from_status": prev_status, "to_status": cur_status})

    return {"previous_valid_session": prev_session,
            "material_change": bool(transitions or rank_movers or quality_transitions or revisions),
            "transitions": transitions, "rank_movers": rank_movers,
            "quality_transitions": quality_transitions,
            "source_revisions": revisions, "reason": None}


_RUNS_HISTORY_CAP = 30


def _prior_runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The most recent row's ``health.runs`` (B2 repair): a build-run history that survives
    the per-session idempotent REPLACE below. Read from whichever row has the newest
    ``written_at`` among EVERYTHING currently on disk (including, on a same-session rebuild,
    that session's own about-to-be-replaced row) — so a frozen ``market_session`` that gets
    rebuilt every night still accumulates one run per night, and a NEW session inherits the
    PREVIOUS session's accumulated history rather than starting over."""
    candidates = [r for r in rows if r.get("written_at")]
    if not candidates:
        return []
    newest = max(candidates, key=lambda r: r["written_at"])
    return list((newest.get("health") or {}).get("runs") or [])


def append_state_log(session: str, entry: dict[str, Any], data_root: Path,
                     require_lane: bool = True, written_at: str | None = None) -> dict[str, Any]:
    """Append (or idempotently REPLACE) this session's line.

    Gated on the nightly/asia-close advance lanes — house law, nightly is the sole
    advancer of forward ledgers (an intraday/manual lane computes and discards).
    ``require_lane=False`` is the test/backfill seam only, mirroring
    ``engine.group_pulse.advance_episode_ledger``'s ``require_nightly_lane`` seam.

    B2 repair: the written row's ``health`` gains a ``runs`` list — one compact record per
    BUILD RUN (``{run_date, publication_state, legs: {leg_id: status}}``), appended (never
    replaced) and capped at the newest ``_RUNS_HISTORY_CAP`` entries. This is the accelerator
    ``quality.consecutive_degraded_sessions``/``leg_consecutive_bad_runs`` walk instead of
    the ``session`` key — a market session that stops advancing during a freeze must not
    also freeze the escalation streak (see ``engine.flow_observatory.quality`` module
    docstring, B2).
    """
    if require_lane and not advance_enabled():
        log.info("flow_observatory: state_log advance skipped (off nightly/asia-close lane)")
        return {"written": False, "reason": "off_ledger_lane", "rows": 0}
    if not session:
        return {"written": False, "reason": "no_session", "rows": 0}
    rows = read_state_log(data_root)
    stamp = written_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_date = str(stamp)[:10]
    health = dict(entry.get("health") or {})
    run_record = {"run_date": run_date, "publication_state": health.get("publication_state"),
                 "legs": {lid: (leg or {}).get("status")
                         for lid, leg in (health.get("legs") or {}).items()}}
    health["runs"] = (_prior_runs(rows) + [run_record])[-_RUNS_HISTORY_CAP:]
    rows = [r for r in rows if r.get("session") != session]
    new_row = {"session": session, "written_at": stamp,
              "themes": entry.get("themes") or {}, "aggregate": entry.get("aggregate") or {},
              "market_read": entry.get("market_read") or {},
              "health": health}
    rows.append(new_row)
    rows.sort(key=lambda r: r["session"])
    p = state_log_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
                     for r in rows) + "\n"
    p.write_text(text, encoding="utf-8")
    return {"written": True, "rows": len(rows), "path": str(p)}
