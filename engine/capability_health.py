"""engine/capability_health.py — F13 V1: the Capability Health & Freshness projection.

WHAT THIS ANSWERS
------------------
Per CAPABILITY (a product-facing surface: a Prophet board, the market-reference build,
the stock dossiers, the foresight desk, ...) one verdict in
{healthy, degraded, stale, unavailable} — or ``could_not_look`` when Eval OS has no
readable evidence at all. Capability health is coarser than artifact-level output health
(``engine/output_health.py``): several artifacts, nightly lanes and provider-telemetry
rows can all speak for one capability, and a capability's declared owner needs ONE
sentence, not forty per-artifact records.

A JOINING LAYER, NOT ANOTHER MONITOR — SAME LAW AS output_health.py
--------------------------------------------------------------------
This module reads no files, makes no network calls and keeps no state of its own. It
takes already-loaded RECEIPT FACTS (one small dict per declared receipt source, built by
``scripts/build_capability_health.py`` from EXISTING receipts: the output_health view,
``data/run_status.json``, ``engine/provider_health.py``'s JSONL, and freshness-sentinel
surfaces) and folds them into one record per capability declared in
``config/capability_health.yml``. It builds no registry of its own, holds no dead-man
switch and COMMITS NOTHING.

THE JOIN PATTERN, EXTENDED FROM output_health.py
--------------------------------------------------
* "I could not look" NEVER renders as "I looked and it was clean". A missing, corrupt or
  unreadable receipt can never yield ``healthy``; a capability with ZERO readable receipt
  sources is ``could_not_look``.
* EVERY declared receipt source resolves ITS OWN verdict from ITS OWN evidence ONLY
  (:func:`_source_verdict`) — never from a sibling source's clocks (repair 2026-09-04,
  finding C2: an earlier revision max-merged ``last_attempted``/``last_successful``
  independently ACROSS sources before deciding, so source A's attempt clock was compared
  against source B's success clock and the verdict flipped on iteration order). The
  per-capability clocks published on the record are a DISPLAY aggregate only — never an
  adjudication input.
* An attempt with NO PRIOR SUCCESS from that same source can never anchor ``healthy``
  (repair finding C1: "attempted but never proven successful" is could_not_look on that
  source's own axis, not a free pass to the attempt clock). A failure NEWER than the last
  known success (from the SAME source) can never yield healthy either.
* The capability's headline verdict is the WORST of every declared source's own verdict —
  INCLUDING an unreadable/corrupt/unknown-type/blind source's ``could_not_look``
  contribution (repair finding I3: a genuinely unreadable source can never be masked by a
  healthy-reading sibling; ``could_not_look`` outranks every real state in the badness
  order, so its presence anywhere in the fold governs the whole capability).
* An ``output_health_artifact`` receipt source may hand this module an ALREADY-JUDGED
  state (it comes from ``resolve_output_health``, which has already applied the §5/§8
  time-basis and clock-kind laws) — the exact same "fold an upstream verdict, never
  re-derive it" shape output_health itself uses for its ``self_health`` and
  ``dependency`` planes. Other receipt types (``nightly_lane``, ``provider_rung``,
  ``sentinel_probe``) carry only raw clocks, and THIS module derives their verdict from
  ``stale_after_hours``.
* A clock value that is present but UNPARSEABLE, or that resolves to an instant more than
  one hour in the future, is a CORRUPT receipt on that source's axis — never silently
  treated as absent, and never able to read as fresh/healthy (repair findings I2/I4).
* Dependency propagation is an UPPER BOUND, never an exact re-derivation and never a
  failover: a capability whose declared ``depends_on`` entry is not healthy is capped at
  ``degraded`` (never silently healed back to ``healthy`` by a fallback receipt, and
  never inherits a worse state than ``degraded`` from the dependency alone — the
  dependency's own record already carries its own, worse verdict).
* A rights/paywall block is a TYPED per-source verdict (``unavailable`` + a
  ``rights_blocked`` reason), never conflated with a failure.
* A deployment-skew receipt (the process's own commit disagreeing with the checkout it
  is running against) CAPS that source's state at ``degraded`` — it can never read
  healthy while a skew is detected, even when every other signal on that source says
  healthy (repair fixture (e) ruling). It never drags an already-worse state down
  further; the cap only ever matters when the source would otherwise have been healthy.
* A transition diff (``prev_state`` -> ``state``) rides INSIDE the single output record
  per capability — there is no separate transitions ledger, append-only store or history
  file. ``prev_seen`` distinguishes "no previous record at all" from "the previous record
  was itself could_not_look" (both would otherwise read as ``prev_state: null``).
* A record whose ``state`` is anything other than ``healthy`` (including ``None`` /
  could_not_look) never renders its summary ``reason`` as ``"ok"`` — an empty
  ``reason_codes`` list still names the state.

PURE. NO I/O, NO CLOCK, NO ENVIRONMENT
--------------------------------------
Every read and every wall-clock reading happens in
``scripts/build_capability_health.py``. ``now`` is INJECTED and must be tz-aware —
:func:`lib.dataos.temporal.utc` refuses a naive datetime. Same inputs -> byte-identical
output; every list is sorted.

NO SCORES, NO RANKS, NO PROMOTION, NO SCHEDULING
--------------------------------------------------
This module carries no score, weight, rank or promotion state, originates no retry or
probe, and performs no failover. It is a read-only OPS/RELIABILITY projection over
existing receipts (F13), not an evaluation or grading surface (qledger's domain).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from lib.dataos.temporal import TemporalError, utc

SCHEMA = "mastermind.capability_health.v1"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

STATE_HEALTHY = "healthy"
STATE_DEGRADED = "degraded"
STATE_STALE = "stale"
STATE_UNAVAILABLE = "unavailable"

#: Worst-first — the order the "worse observation governs" fold resolves in.
STATES: tuple[str, ...] = (STATE_UNAVAILABLE, STATE_STALE, STATE_DEGRADED, STATE_HEALTHY)

#: Badness rank. Higher = worse. ``None`` (could_not_look) ranks WORSE than every real
#: state on purpose (repair finding I3): a source that cannot speak to health at all is a
#: worse observation than one that speaks and reports even ``unavailable``, so its
#: presence anywhere in a worst-of fold governs the whole capability. An unrecognized
#: value also defaults to the WORST rank (repair finding M3) — garbage-in must never be
#: read as the healthiest possible state.
_STATE_RANK: dict[str | None, int] = {
    None: 4,
    STATE_UNAVAILABLE: 3,
    STATE_STALE: 2,
    STATE_DEGRADED: 1,
    STATE_HEALTHY: 0,
}
_WORST_RANK_DEFAULT = 4

ASSESSMENT_COMPLETE = "complete"
ASSESSMENT_PARTIAL = "partial"
ASSESSMENT_COULD_NOT_LOOK = "could_not_look"
ASSESSMENT_STATUSES: tuple[str, ...] = (
    ASSESSMENT_COMPLETE,
    ASSESSMENT_PARTIAL,
    ASSESSMENT_COULD_NOT_LOOK,
)

#: The CLOSED receipt-source vocabulary (§1 of the F13 commission). An entry naming
#: anything else fails closed: :func:`validate_registry` reports it, and the resolver
#: treats it as unreadable rather than inventing a verdict for a type it does not know.
RECEIPT_TYPE_OUTPUT_HEALTH_ARTIFACT = "output_health_artifact"
RECEIPT_TYPE_NIGHTLY_LANE = "nightly_lane"
RECEIPT_TYPE_PROVIDER_RUNG = "provider_rung"
RECEIPT_TYPE_SENTINEL_PROBE = "sentinel_probe"
RECEIPT_TYPES: frozenset[str] = frozenset({
    RECEIPT_TYPE_OUTPUT_HEALTH_ARTIFACT,
    RECEIPT_TYPE_NIGHTLY_LANE,
    RECEIPT_TYPE_PROVIDER_RUNG,
    RECEIPT_TYPE_SENTINEL_PROBE,
})

#: The clock vocabulary a receipt source may declare it binds (§1: "which of
#: last_attempted/last_successful/data_as_of/render_release each source binds").
CLOCK_LAST_ATTEMPTED = "last_attempted"
CLOCK_LAST_SUCCESSFUL = "last_successful"
CLOCK_DATA_AS_OF = "data_as_of"
CLOCK_RENDER_RELEASE = "render_release"
CLOCK_KEYS: tuple[str, ...] = (
    CLOCK_LAST_ATTEMPTED,
    CLOCK_LAST_SUCCESSFUL,
    CLOCK_DATA_AS_OF,
    CLOCK_RENDER_RELEASE,
)

DEFAULT_STALE_AFTER_HOURS = 48

#: A clock value resolving more than this far into the future is CORRUPT, not fresh
#: (repair finding I4). One hour of slack absorbs ordinary clock skew between the runner
#: that wrote the receipt and the host that resolves this build.
FUTURE_CLOCK_TOLERANCE = timedelta(hours=1)

# --- reason codes ------------------------------------------------------------
# A code may carry a ``:<label>`` suffix naming the receipt source or dependency it is
# ABOUT — :func:`reason_base` strips it for tallying, mirroring output_health's
# ``reason_base``.

REASON_NO_RECEIPT_SOURCES = "no_receipt_sources"
REASON_RECEIPT_UNREADABLE = "receipt_unreadable"
REASON_RECEIPT_CORRUPT = "receipt_corrupt"
REASON_UNKNOWN_RECEIPT_TYPE = "unknown_receipt_type"
REASON_NO_CLOCK_EVIDENCE = "no_clock_evidence"
REASON_UPSTREAM_COULD_NOT_LOOK = "upstream_could_not_look"
REASON_NO_PRIOR_SUCCESS = "no_prior_success"
REASON_CLOCK_UNPARSEABLE = "clock_value_unparseable"
REASON_CLOCK_FUTURE_DATED = "clock_value_future_dated"
REASON_RIGHTS_BLOCKED = "rights_blocked"
REASON_FAILURE_AFTER_SUCCESS = "attempt_newer_than_last_success"
REASON_SUCCESS_STALE = "success_beyond_stale_budget"
REASON_DEPENDENCY_DEGRADED = "dependency_not_healthy"
REASON_DEPENDENCY_COULD_NOT_LOOK = "dependency_could_not_look"
REASON_DEPLOYMENT_COMMIT_SKEW = "deployment_commit_skew"
REASON_CORRECTION_REPLAY = "correction_replay"

REASON_CODES: frozenset[str] = frozenset({
    REASON_NO_RECEIPT_SOURCES,
    REASON_RECEIPT_UNREADABLE,
    REASON_RECEIPT_CORRUPT,
    REASON_UNKNOWN_RECEIPT_TYPE,
    REASON_NO_CLOCK_EVIDENCE,
    REASON_UPSTREAM_COULD_NOT_LOOK,
    REASON_NO_PRIOR_SUCCESS,
    REASON_CLOCK_UNPARSEABLE,
    REASON_CLOCK_FUTURE_DATED,
    REASON_RIGHTS_BLOCKED,
    REASON_FAILURE_AFTER_SUCCESS,
    REASON_SUCCESS_STALE,
    REASON_DEPENDENCY_DEGRADED,
    REASON_DEPENDENCY_COULD_NOT_LOOK,
    REASON_DEPLOYMENT_COMMIT_SKEW,
    REASON_CORRECTION_REPLAY,
})


def reason_base(code: str) -> str:
    """The base reason code — the part before any ``:<label>`` suffix."""
    return str(code).split(":", 1)[0]


# ---------------------------------------------------------------------------
# Registry validation — fails CLOSED on an unknown receipt-source type
# ---------------------------------------------------------------------------

def validate_registry(capabilities: Sequence[Mapping[str, Any]]) -> list[str]:
    """Structural problems in the parsed ``config/capability_health.yml`` list.

    Empty = valid. Every problem is reported (never just the first), sorted, so a fixer
    sees the whole list in one pass. This is schema validation ONLY — it never reads a
    receipt and never decides a health verdict. The BUILDER (not this function) is what
    turns a non-empty result into a fail-closed refusal to write (repair finding C3) —
    this function only ever reports.
    """
    problems: list[str] = []
    seen_ids: set[str] = set()
    ids_declared: set[str] = set()

    for cap in capabilities:
        cid = cap.get("id") if isinstance(cap, Mapping) else None
        if not isinstance(cid, str) or not cid.strip():
            problems.append("capability entry missing a non-empty string 'id'")
            continue
        ids_declared.add(cid)

    for cap in capabilities:
        if not isinstance(cap, Mapping):
            problems.append("capability entry is not a mapping")
            continue
        cid = cap.get("id")
        if not isinstance(cid, str) or not cid.strip():
            continue  # already reported above
        if cid in seen_ids:
            problems.append(f"{cid}: duplicate capability id")
        seen_ids.add(cid)

        sources = cap.get("receipt_sources")
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)) or not sources:
            problems.append(f"{cid}: no receipt_sources declared")
            sources = []
        for i, decl in enumerate(sources):
            if not isinstance(decl, Mapping):
                problems.append(f"{cid}: receipt_sources[{i}] is not a mapping")
                continue
            typ = decl.get("type")
            if typ not in RECEIPT_TYPES:
                problems.append(
                    f"{cid}: receipt_sources[{i}] has unknown type {typ!r} "
                    f"(known: {sorted(RECEIPT_TYPES)})"
                )
            ref = decl.get("ref")
            if not isinstance(ref, str) or not ref.strip():
                problems.append(f"{cid}: receipt_sources[{i}] missing a non-empty 'ref'")
            for key in decl.get("clocks") or []:
                if key not in CLOCK_KEYS:
                    problems.append(
                        f"{cid}: receipt_sources[{i}] declares unknown clock {key!r} "
                        f"(known: {list(CLOCK_KEYS)})"
                    )

        for dep in cap.get("depends_on") or []:
            if dep == cid:
                problems.append(f"{cid}: depends_on cannot include itself")
            elif dep not in ids_declared:
                problems.append(
                    f"{cid}: depends_on {dep!r} is not a registered capability id"
                )

    return sorted(problems)


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return utc(value)
    except (TemporalError, TypeError, ValueError):
        return None


def _hours_between(now: datetime, then: datetime) -> float:
    return round((now - then).total_seconds() / 3600.0, 3)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _worst(states: Sequence[str | None]) -> str | None:
    """The single worst verdict in *states* — ``None`` (could_not_look) wins over every
    real state (repair finding I3), and an unrecognized value defaults to the WORST rank,
    never the healthiest (repair finding M3)."""
    if not states:
        return None
    return max(states, key=lambda s: _STATE_RANK.get(s, _WORST_RANK_DEFAULT))


def _evidence(plane: str, source: str, detail: str) -> dict[str, str]:
    return {"plane": plane, "source": source, "detail": detail}


def _sorted_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    seen: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row.get("plane")), str(row.get("source")), str(row.get("detail")))
        seen.setdefault(key, {"plane": key[0], "source": key[1], "detail": key[2]})
    return [seen[key] for key in sorted(seen)]


def _label(decl: Mapping[str, Any]) -> str:
    return f"{decl.get('type')}:{decl.get('ref')}"


def _clock_reading(raw: Any, *, now: datetime) -> tuple[datetime | None, str | None]:
    """One raw clock value -> ``(instant_or_None, corrupt_reason_or_None)``.

    ``corrupt_reason`` is :data:`REASON_CLOCK_UNPARSEABLE` when *raw* is present but
    cannot be read as an instant at all, or :data:`REASON_CLOCK_FUTURE_DATED` when it
    parses but resolves more than :data:`FUTURE_CLOCK_TOLERANCE` beyond *now* (repair
    findings I2/I4). A genuinely ABSENT value (``None``/``""``) is neither present-and-bad
    NOR a reading — it returns ``(None, None)``, distinct from a corrupt one.
    """
    if raw is None or raw == "":
        return None, None
    dt = _as_utc(raw)
    if dt is None:
        return None, REASON_CLOCK_UNPARSEABLE
    if dt > now + FUTURE_CLOCK_TOLERANCE:
        return None, REASON_CLOCK_FUTURE_DATED
    return dt, None


# ---------------------------------------------------------------------------
# Per-SOURCE resolution (C1/C2/I2/I3/I4: every source decides from ITS OWN evidence only)
# ---------------------------------------------------------------------------

def _source_verdict(
    decl: Mapping[str, Any],
    fact: Mapping[str, Any] | None,
    *,
    stale_after_hours: int,
    now: datetime,
) -> tuple[str | None, list[str], list[dict[str, str]], dict[str, Any]]:
    """ONE declared receipt source's own verdict, from ONLY that source's own evidence.

    Returns ``(state_or_None, reason_codes, evidence_rows, clocks_for_display)``.
    ``state_or_None`` is a real :data:`STATES` value, or ``None`` — a could_not_look
    CONTRIBUTION meaning this source could not speak to health at all. No other source's
    clocks are ever consulted here (repair finding C2): a capability-level "most recent
    across sources" merge exists ONLY for the record's display ``clocks`` field, built by
    the caller — never as an input to this function's own verdict.
    """
    label = _label(decl)
    reasons: list[str] = []
    evidence: list[dict[str, str]] = []
    display_clocks: dict[str, Any] = {}

    if decl.get("type") not in RECEIPT_TYPES:
        return None, [f"{REASON_UNKNOWN_RECEIPT_TYPE}:{label}"], evidence, display_clocks

    if not isinstance(fact, Mapping) or not fact.get("readable", False):
        return None, [f"{REASON_RECEIPT_UNREADABLE}:{label}"], evidence, display_clocks

    if fact.get("corrupt"):
        return None, [f"{REASON_RECEIPT_CORRUPT}:{label}"], evidence, display_clocks

    # Clocks this source is DECLARED to bind, honoring a per-fact override (a source that
    # can only ever supply a subset of what the registry declares).
    bind = fact.get("clocks_bound")
    bind = (
        bind if isinstance(bind, Sequence) and not isinstance(bind, (str, bytes))
        else (decl.get("clocks") or [])
    )
    for key in CLOCK_KEYS:
        val = fact.get(key)
        if val:
            display_clocks[key] = val

    if fact.get("rights_blocked"):
        detail = str(fact.get("rights_detail") or "rights-restricted")
        evidence.append(_evidence("receipt", label, detail))
        return STATE_UNAVAILABLE, [f"{REASON_RIGHTS_BLOCKED}:{label}"], evidence, display_clocks

    pc, cc = fact.get("process_commit"), fact.get("checkout_commit")
    skew = bool(pc and cc and pc != cc)
    if skew:
        reasons.append(f"{REASON_DEPLOYMENT_COMMIT_SKEW}:{label}")
        evidence.append(_evidence(
            "receipt", label,
            f"process_commit={pc} checkout_commit={cc} — deployment skew"
        ))

    replay_of = fact.get("replay_of")
    if replay_of:
        reasons.append(f"{REASON_CORRECTION_REPLAY}:{label}")
        evidence.append(_evidence(
            "receipt", label,
            f"replay_of={replay_of} data_as_of={fact.get('data_as_of')} "
            f"— original clock preserved in evidence, not overwritten silently",
        ))

    explicit = fact.get("state")
    if explicit in STATES:
        # A deployment-skew receipt CAPS state at degraded (repair fixture (e) ruling):
        # a source cannot be reported healthy while its own process/checkout commits
        # disagree, even when its upstream verdict was otherwise healthy.
        capped = STATE_DEGRADED if (skew and explicit == STATE_HEALTHY) else explicit
        return capped, reasons, evidence, display_clocks

    if explicit is None and str(fact.get("assessment_status") or "") == ASSESSMENT_COULD_NOT_LOOK:
        # An upstream module (output_health) already looked and could not decide. That is
        # a could_not_look CONTRIBUTION, not a missing receipt — the fact itself was
        # readable, its VERDICT is the blindness.
        evidence.append(_evidence("receipt", label, "upstream assessment_status=could_not_look"))
        reasons.append(f"{REASON_UPSTREAM_COULD_NOT_LOOK}:{label}")
        return None, reasons, evidence, display_clocks

    if CLOCK_LAST_ATTEMPTED not in bind and CLOCK_LAST_SUCCESSFUL not in bind:
        # This source never even declares an attempt/success clock (e.g. it only ever
        # binds data_as_of/render_release, or nothing at all) and carried no explicit
        # state — it has nothing to say about health either way.
        reasons.append(f"{REASON_NO_CLOCK_EVIDENCE}:{label}")
        return None, reasons, evidence, display_clocks

    # --- clock-derived verdict — THIS SOURCE'S OWN (ta, ts) pairing only (C2) ----------
    ta_raw = fact.get(CLOCK_LAST_ATTEMPTED) if CLOCK_LAST_ATTEMPTED in bind else None
    ts_raw = fact.get(CLOCK_LAST_SUCCESSFUL) if CLOCK_LAST_SUCCESSFUL in bind else None
    ta, ta_bad = _clock_reading(ta_raw, now=now)
    ts, ts_bad = _clock_reading(ts_raw, now=now)
    if ta_bad:
        reasons.append(f"{ta_bad}:{label}:last_attempted")
        return None, reasons, evidence, display_clocks
    if ts_bad:
        reasons.append(f"{ts_bad}:{label}:last_successful")
        return None, reasons, evidence, display_clocks

    if ts is None:
        if ta is None:
            reasons.append(f"{REASON_NO_CLOCK_EVIDENCE}:{label}")
            return None, reasons, evidence, display_clocks
        # C1: attempted, but this source has NEVER recorded a success -> could_not_look,
        # NEVER healthy. An attempt clock alone is not proof of anything but an attempt.
        reasons.append(f"{REASON_NO_PRIOR_SUCCESS}:{label}")
        return None, reasons, evidence, display_clocks

    evidence.append(_evidence(
        "receipt", label,
        f"last_attempted={ta.isoformat() if ta else None} last_successful={ts.isoformat()}",
    ))

    if ta is not None and ta > ts:
        # A failure (an attempt strictly newer than the last known success, from the SAME
        # source) can never yield healthy.
        reasons.append(f"{REASON_FAILURE_AFTER_SUCCESS}:{label}")
        age = _hours_between(now, ts)
        if age > stale_after_hours:
            reasons.append(f"{REASON_SUCCESS_STALE}:{label}")
            return STATE_STALE, reasons, evidence, display_clocks
        return STATE_DEGRADED, reasons, evidence, display_clocks

    age = _hours_between(now, ts)
    if age > stale_after_hours:
        reasons.append(f"{REASON_SUCCESS_STALE}:{label}")
        return STATE_STALE, reasons, evidence, display_clocks
    # Same deployment-skew cap as the explicit-state branch above: a fresh success clock
    # alone never overrides a detected commit mismatch back to healthy.
    return (STATE_DEGRADED if skew else STATE_HEALTHY), reasons, evidence, display_clocks


# ---------------------------------------------------------------------------
# Per-capability resolution
# ---------------------------------------------------------------------------

def _resolve_one(
    cap: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any] | None],
    *,
    now: datetime,
) -> dict[str, Any]:
    sources_decl = [d for d in (cap.get("receipt_sources") or []) if isinstance(d, Mapping)]
    if not sources_decl:
        return _record(cap, state=None, assessment=ASSESSMENT_COULD_NOT_LOOK,
                        reasons=[REASON_NO_RECEIPT_SOURCES],
                        clocks={key: None for key in CLOCK_KEYS}, evidence=[])

    stale_after = _positive_int(cap.get("stale_after_hours")) or DEFAULT_STALE_AFTER_HOURS
    padded: list[Any] = list(facts) + [None] * max(0, len(sources_decl) - len(facts))

    all_states: list[str | None] = []
    reasons: list[str] = []
    evidence: list[dict[str, str]] = []
    # DISPLAY-ONLY aggregate ("most recent across sources per clock key") — never fed
    # back into any source's own verdict (C2). Published so a UI can show one freshness
    # line per capability even though ADJUDICATION happened per-source.
    clocks: dict[str, Any] = {key: None for key in CLOCK_KEYS}

    for decl, fact in zip(sources_decl, padded):
        state, src_reasons, src_evidence, src_clocks = _source_verdict(
            decl, fact, stale_after_hours=stale_after, now=now
        )
        all_states.append(state)
        reasons.extend(src_reasons)
        evidence.extend(src_evidence)
        for key, val in src_clocks.items():
            cur = clocks[key]
            cur_dt, val_dt = _as_utc(cur), _as_utc(val)
            if cur is None or (val_dt is not None and (cur_dt is None or val_dt > cur_dt)):
                clocks[key] = val

    # The capability's headline state is the WORST of every source's own verdict,
    # including a could_not_look (None) contribution from any single source (I3): a
    # blind or unreadable source can never be masked by a healthy-reading sibling.
    state = _worst(all_states)
    assessment = ASSESSMENT_COULD_NOT_LOOK if state is None else ASSESSMENT_COMPLETE

    return _record(cap, state=state, assessment=assessment,
                    reasons=sorted(set(reasons)), clocks=clocks, evidence=evidence)


def _record(
    cap: Mapping[str, Any],
    *,
    state: str | None,
    assessment: str,
    reasons: list[str],
    clocks: Mapping[str, Any],
    evidence: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "id": cap.get("id"),
        "label_en": cap.get("label_en"),
        "owner": cap.get("owner"),
        "artifacts": list(cap.get("artifacts") or []),
        "state": state,
        "assessment_status": assessment,
        "reason_codes": list(reasons),
        "clocks": dict(clocks),
        "next_action": cap.get("next_action_hint"),
        "evidence": _sorted_evidence(evidence),
    }


def _cap_by_dependency(
    record: dict[str, Any],
    *,
    depends_on: Sequence[str],
    base_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Cap *record* at ``degraded`` when a declared dependency is not healthy.

    Upper bound only (mirrors output_health's dependency-bound law): a bad dependency can
    drag a healthy capability down to ``degraded`` — never further, and never via a
    silent failover back to healthy. A capability already worse than ``degraded`` on its
    own evidence is left exactly as it was; its own record already names the worse cause.
    """
    dep_reasons: list[str] = []
    for dep_id in depends_on:
        dep = base_by_id.get(str(dep_id))
        if dep is None or dep.get("id") == record.get("id"):
            continue
        dep_state = dep.get("state")
        if dep_state == STATE_HEALTHY:
            continue
        if dep_state is None:
            dep_reasons.append(f"{REASON_DEPENDENCY_COULD_NOT_LOOK}:{dep_id}")
        else:
            dep_reasons.append(f"{REASON_DEPENDENCY_DEGRADED}:{dep_id}")

    if not dep_reasons:
        return record

    out = dict(record)
    own_rank = _STATE_RANK.get(record.get("state"), _WORST_RANK_DEFAULT)
    if own_rank < _STATE_RANK[STATE_DEGRADED]:
        # own state is healthy (rank 0) and a dependency is not — cap at degraded.
        out["state"] = STATE_DEGRADED
        if out["assessment_status"] == ASSESSMENT_COMPLETE:
            out["assessment_status"] = ASSESSMENT_PARTIAL
    out["reason_codes"] = sorted(set(out["reason_codes"]) | set(dep_reasons))
    return out


def _summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in records:
            value = row.get(key)
            label = "null" if value is None else str(value)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items()))

    reason_hist: dict[str, int] = {}
    for row in records:
        for code in row.get("reason_codes") or []:
            base = reason_base(code)
            reason_hist[base] = reason_hist.get(base, 0) + 1

    return {
        "n_capabilities": len(records),
        "by_state": tally("state"),
        "by_assessment_status": tally("assessment_status"),
        "reason_codes": dict(sorted(reason_hist.items())),
    }


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------

def resolve_capability_health(
    *,
    capabilities: Sequence[Mapping[str, Any]],
    receipts: Mapping[str, Sequence[Mapping[str, Any] | None]] | None = None,
    previous: Mapping[str, Mapping[str, Any]] | None = None,
    now: datetime,
) -> dict[str, Any]:
    """Resolve one health record per declared capability. PURE — see module docstring.

    Parameters
    ----------
    capabilities
        The parsed ``config/capability_health.yml`` ``capabilities`` list. A duplicate
        ``id`` is deduplicated (last entry wins, matching dict-construction semantics) so
        the OUTPUT never contains two rows for the same id — the builder is expected to
        refuse a registry with a duplicate id outright (repair finding C3); this is
        defense in depth for direct callers.
    receipts
        Per capability id, one receipt FACT per declared ``receipt_sources`` entry, in
        the SAME order. A fact is a small dict: ``readable`` (bool), ``corrupt`` (bool),
        ``rights_blocked`` (bool), ``rights_detail`` (str), ``state`` (an already-judged
        verdict — used verbatim for an ``output_health_artifact`` source),
        ``assessment_status`` (``could_not_look`` when an upstream module looked and
        could not decide), the four clock fields, ``clocks_bound`` (override of the
        declared ``clocks`` list — the loader uses this when a source can only ever
        supply a SUBSET of what the registry declares), ``process_commit`` /
        ``checkout_commit`` (deployment-skew detection) and ``replay_of`` (an ISO instant
        naming the value a correction/replay receipt is amending).
    previous
        Per capability id, the PREVIOUS resolved record (or just ``{"state": ...}``) —
        used only to embed the ``transition`` diff. A capability id ABSENT from this
        mapping gets ``prev_seen: False`` (no history at all); a capability id PRESENT
        with ``state: None`` gets ``prev_seen: True, prev_state: None`` (it was
        could_not_look last time) — the two are never conflated.
    now
        Tz-aware; a naive datetime raises :class:`lib.dataos.temporal.TemporalError`.
    """
    observed_at = utc(now)
    receipt_map = receipts or {}
    previous_map = previous or {}

    caps = [c for c in capabilities if isinstance(c, Mapping) and c.get("id")]
    by_id = {str(c["id"]): c for c in caps}  # duplicate id: last one wins
    ids_sorted = sorted(by_id)

    base: dict[str, dict[str, Any]] = {}
    for cid in ids_sorted:
        cap = by_id[cid]
        facts = receipt_map.get(cid) or []
        base[cid] = _resolve_one(cap, facts, now=observed_at)

    final: dict[str, dict[str, Any]] = {}
    for cid in ids_sorted:
        cap = by_id[cid]
        depends_on = [str(d) for d in (cap.get("depends_on") or [])]
        record = _cap_by_dependency(base[cid], depends_on=depends_on, base_by_id=base)
        record = dict(record)
        prev_seen = cid in previous_map
        prev = previous_map.get(cid) or {}
        record["transition"] = {
            "prev_seen": prev_seen,
            "prev_state": prev.get("state") if prev_seen else None,
            "state": record["state"],
        }
        reason_codes = record["reason_codes"]
        if reason_codes:
            record["reason"] = "; ".join(reason_codes)
        elif record["state"] != STATE_HEALTHY:
            # A degraded/stale/unavailable/could_not_look record with an empty
            # reason_codes list must still never say "ok" (repair finding M1).
            record["reason"] = f"state={record['state'] if record['state'] is not None else 'could_not_look'}"
        else:
            record["reason"] = "ok"
        final[cid] = record

    outputs = [final[cid] for cid in ids_sorted]
    return {
        "schema": SCHEMA,
        "generated": {
            "observed_at": observed_at.isoformat(),
            "inputs": {
                "capabilities": len(caps),
                "receipts": sum(len(v) for v in receipt_map.values()),
                "previous": len(previous_map),
            },
        },
        "capabilities": outputs,
        "summary": _summary(outputs),
    }
