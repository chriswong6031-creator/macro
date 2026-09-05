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
  unreadable receipt can never yield ``healthy`` (:data:`BLIND_REASONS`-equivalent
  handling below); a capability with ZERO readable receipt sources is
  ``could_not_look``, with every missing source named in ``reason_codes``.
* A failure NEWER than the last known success can never yield ``healthy`` — the same
  "worse observation governs" law output_health applies to its reader plane
  (``_READER_SEVERITY``) is applied here across a capability's own receipt sources: the
  WORST readable verdict governs, never the best.
* An ``output_health_artifact`` receipt source may hand this module an ALREADY-JUDGED
  state (it comes from ``resolve_output_health``, which has already applied the §5/§8
  time-basis and clock-kind laws) — the exact same "fold an upstream verdict, never
  re-derive it" shape output_health itself uses for its ``self_health`` and
  ``dependency`` planes. Other receipt types (``nightly_lane``, ``provider_rung``,
  ``sentinel_probe``) carry only raw clocks, and THIS module derives their verdict from
  ``stale_after_hours``.
* Dependency propagation is an UPPER BOUND, never an exact re-derivation and never a
  failover: a capability whose declared ``depends_on`` entry is not healthy is capped at
  ``degraded`` (never silently healed back to ``healthy`` by a fallback receipt, and
  never inherits a worse state than ``degraded`` from the dependency alone — the
  dependency's own record already carries its own, worse verdict).
* A rights/paywall block is a TYPED verdict (``unavailable`` + a ``rights_blocked``
  reason), never conflated with a failure.
* A transition diff (``prev_state`` -> ``state``) rides INSIDE the single output record
  per capability — there is no separate transitions ledger, append-only store or history
  file. Callers that want history persist ``capabilities`` themselves between runs.

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

from datetime import datetime
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

#: Badness rank. Higher = worse. Used to pick the worst of several contributed verdicts
#: and to bound how far a dependency may drag a healthy capability down (never past
#: ``degraded`` from dependency propagation ALONE — see :func:`_cap_by_dependency`).
_STATE_RANK: dict[str | None, int] = {
    None: 4,
    STATE_UNAVAILABLE: 3,
    STATE_STALE: 2,
    STATE_DEGRADED: 1,
    STATE_HEALTHY: 0,
}

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

# --- reason codes ------------------------------------------------------------
# A code may carry a ``:<label>`` suffix naming the receipt source or dependency it is
# ABOUT — :func:`reason_base` strips it for tallying, mirroring output_health's
# ``reason_base``.

REASON_NO_RECEIPT_SOURCES = "no_receipt_sources"
REASON_RECEIPT_UNREADABLE = "receipt_unreadable"
REASON_RECEIPT_CORRUPT = "receipt_corrupt"
REASON_ALL_SOURCES_UNREADABLE = "all_sources_unreadable"
REASON_UNKNOWN_RECEIPT_TYPE = "unknown_receipt_type"
REASON_NO_CLOCK_DATA = "no_clock_data"
REASON_RIGHTS_BLOCKED = "rights_blocked"
REASON_FAILURE_AFTER_SUCCESS = "attempt_newer_than_last_success"
REASON_SUCCESS_STALE = "success_beyond_stale_budget"
REASON_DEPENDENCY_DEGRADED = "dependency_not_healthy"
REASON_DEPENDENCY_COULD_NOT_LOOK = "dependency_could_not_look"
REASON_DEPLOYMENT_COMMIT_SKEW = "deployment_commit_skew"
REASON_CORRECTION_REPLAY = "correction_replay"
REASON_PARTIAL_UPSTREAM_COULD_NOT_LOOK = "partial_upstream_could_not_look"
REASON_ALL_UPSTREAM_COULD_NOT_LOOK = "all_upstream_could_not_look"

REASON_CODES: frozenset[str] = frozenset({
    REASON_NO_RECEIPT_SOURCES,
    REASON_RECEIPT_UNREADABLE,
    REASON_RECEIPT_CORRUPT,
    REASON_ALL_SOURCES_UNREADABLE,
    REASON_UNKNOWN_RECEIPT_TYPE,
    REASON_NO_CLOCK_DATA,
    REASON_RIGHTS_BLOCKED,
    REASON_FAILURE_AFTER_SUCCESS,
    REASON_SUCCESS_STALE,
    REASON_DEPENDENCY_DEGRADED,
    REASON_DEPENDENCY_COULD_NOT_LOOK,
    REASON_DEPLOYMENT_COMMIT_SKEW,
    REASON_CORRECTION_REPLAY,
    REASON_PARTIAL_UPSTREAM_COULD_NOT_LOOK,
    REASON_ALL_UPSTREAM_COULD_NOT_LOOK,
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
    receipt and never decides a health verdict.
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


def _worst(states: Sequence[str]) -> str:
    return max(states, key=lambda s: _STATE_RANK.get(s, 0))


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


# ---------------------------------------------------------------------------
# Per-capability resolution
# ---------------------------------------------------------------------------

def _resolve_one(
    cap: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any] | None],
    *,
    now: datetime,
) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: list[dict[str, str]] = []
    clocks: dict[str, Any] = {key: None for key in CLOCK_KEYS}

    sources_decl = [d for d in (cap.get("receipt_sources") or []) if isinstance(d, Mapping)]
    if not sources_decl:
        return _record(cap, state=None, assessment=ASSESSMENT_COULD_NOT_LOOK,
                        reasons=[REASON_NO_RECEIPT_SOURCES], clocks=clocks, evidence=evidence)

    padded: list[Any] = list(facts) + [None] * max(0, len(sources_decl) - len(facts))

    missing_labels: list[str] = []
    rights_hits: list[tuple[str, str]] = []
    contributed_states: list[str | None] = []
    any_readable = False

    for decl, fact in zip(sources_decl, padded):
        label = _label(decl)

        if decl.get("type") not in RECEIPT_TYPES:
            reasons.append(f"{REASON_UNKNOWN_RECEIPT_TYPE}:{label}")
            missing_labels.append(label)
            continue

        if not isinstance(fact, Mapping) or not fact.get("readable", False):
            reasons.append(f"{REASON_RECEIPT_UNREADABLE}:{label}")
            missing_labels.append(label)
            continue

        if fact.get("corrupt"):
            reasons.append(f"{REASON_RECEIPT_CORRUPT}:{label}")
            missing_labels.append(label)
            continue

        any_readable = True

        if fact.get("rights_blocked"):
            rights_hits.append((label, str(fact.get("rights_detail") or "rights-restricted")))

        bind = fact.get("clocks_bound")
        bind = bind if isinstance(bind, Sequence) and not isinstance(bind, (str, bytes)) else (
            decl.get("clocks") or []
        )
        for key in CLOCK_KEYS:
            if key not in bind:
                continue
            val = fact.get(key)
            if not val:
                continue
            cur = clocks[key]
            cur_dt, val_dt = _as_utc(cur), _as_utc(val)
            if cur is None or (val_dt is not None and cur_dt is not None and val_dt > cur_dt):
                clocks[key] = val

        pc, cc = fact.get("process_commit"), fact.get("checkout_commit")
        if pc and cc and pc != cc:
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
            contributed_states.append(explicit)
        elif explicit is None and str(fact.get("assessment_status") or "") == ASSESSMENT_COULD_NOT_LOOK:
            # An upstream module (output_health) already looked and could not decide.
            # That is a could_not_look CONTRIBUTION, not a missing receipt — the fact
            # itself was readable, its VERDICT is the blindness.
            contributed_states.append(None)
            evidence.append(_evidence("receipt", label, "upstream assessment_status=could_not_look"))

    if not any_readable:
        return _record(
            cap, state=None, assessment=ASSESSMENT_COULD_NOT_LOOK,
            reasons=sorted(set(reasons + [
                f"{REASON_ALL_SOURCES_UNREADABLE}:" + ",".join(sorted(missing_labels))
            ])),
            clocks=clocks, evidence=evidence,
        )

    if rights_hits:
        reasons += [f"{REASON_RIGHTS_BLOCKED}:{label}" for label, _ in rights_hits]
        for label, detail in rights_hits:
            evidence.append(_evidence("receipt", label, detail))
        assessment = ASSESSMENT_PARTIAL if missing_labels else ASSESSMENT_COMPLETE
        return _record(cap, state=STATE_UNAVAILABLE, assessment=assessment,
                        reasons=sorted(set(reasons)), clocks=clocks, evidence=evidence)

    stale_after = _positive_int(cap.get("stale_after_hours")) or DEFAULT_STALE_AFTER_HOURS
    ta = _as_utc(clocks[CLOCK_LAST_ATTEMPTED])
    ts = _as_utc(clocks[CLOCK_LAST_SUCCESSFUL])

    clock_state: str | None = None
    if ta is not None or ts is not None:
        if ta is not None and ts is not None and ta > ts:
            # A failure (or an attempt with no matching success) NEWER than the last
            # known success can never yield healthy.
            reasons.append(REASON_FAILURE_AFTER_SUCCESS)
            age = _hours_between(now, ts)
            if age > stale_after:
                reasons.append(REASON_SUCCESS_STALE)
                clock_state = STATE_STALE
            else:
                clock_state = STATE_DEGRADED
        else:
            anchor = ts if ts is not None else ta
            age = _hours_between(now, anchor)
            if age > stale_after:
                reasons.append(REASON_SUCCESS_STALE)
                clock_state = STATE_STALE
            else:
                clock_state = STATE_HEALTHY

    all_states = list(contributed_states)
    if clock_state is not None:
        all_states.append(clock_state)

    if not all_states:
        # No source contributed an explicit verdict AND no clock data was bound at all —
        # readable sources exist, but none of them could speak to health either way.
        reasons.append(REASON_NO_CLOCK_DATA)
        return _record(cap, state=None, assessment=ASSESSMENT_COULD_NOT_LOOK,
                        reasons=sorted(set(reasons)), clocks=clocks, evidence=evidence)

    real_states = [s for s in all_states if s is not None]
    if not real_states:
        # Every contribution WAS an upstream could_not_look verdict — distinct from
        # "no clock data": these sources were readable and answered, and the answer was
        # blindness on their own axis.
        reasons.append(REASON_ALL_UPSTREAM_COULD_NOT_LOOK)
        return _record(cap, state=None, assessment=ASSESSMENT_COULD_NOT_LOOK,
                        reasons=sorted(set(reasons)), clocks=clocks, evidence=evidence)

    state = _worst(real_states)
    partial = bool(missing_labels) or (len(real_states) != len(all_states))
    if len(real_states) != len(all_states):
        reasons.append(REASON_PARTIAL_UPSTREAM_COULD_NOT_LOOK)
    assessment = ASSESSMENT_PARTIAL if partial else ASSESSMENT_COMPLETE

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
    worst_dep_rank = -1
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
        worst_dep_rank = max(worst_dep_rank, _STATE_RANK.get(dep_state, 4))

    if not dep_reasons:
        return record

    out = dict(record)
    own_rank = _STATE_RANK.get(record.get("state"), 4)
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
        The parsed ``config/capability_health.yml`` ``capabilities`` list.
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
        used only to embed the ``transition`` diff. Omit on a first run.
    now
        Tz-aware; a naive datetime raises :class:`lib.dataos.temporal.TemporalError`.
    """
    observed_at = utc(now)
    receipt_map = receipts or {}
    previous_map = previous or {}

    caps = [c for c in capabilities if isinstance(c, Mapping) and c.get("id")]
    ids_sorted = sorted(str(c["id"]) for c in caps)
    by_id = {str(c["id"]): c for c in caps}

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
        prev = previous_map.get(cid) or {}
        record = dict(record)
        record["transition"] = {"prev_state": prev.get("state"), "state": record["state"]}
        record["reason"] = "; ".join(record["reason_codes"]) if record["reason_codes"] else "ok"
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
