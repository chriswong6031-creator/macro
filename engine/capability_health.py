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
  one hour (16 hours for a BARE calendar-date value — repair round-3, 2026-09-06
  independent review, item 3, window corrected round-5 item 2: a date-grain source can
  legitimately report a calendar date up to a UTC+14 timezone lead ahead of ``now``, plus
  2h of ordinary skew — 14h + 2h = 16h, never the original 26h's undocumented figure) in
  the future, is a CORRUPT receipt
  on that source's axis — never silently treated as absent, and never able to read as
  fresh/healthy (repair findings I2/I4). This applies to ALL FOUR clock kinds
  (last_attempted, last_successful, data_as_of, render_release), not just the two that
  feed the ta/ts adjudication path (repair IMPORTANT-1, 2026-09-05 independent review):
  a corrupt data_as_of/render_release can never enter the published ``clocks`` display
  block either, and forces the SAME could_not_look verdict on that source as a corrupt
  ta/ts would.
* A ``nightly_lane`` receipt NEVER truthfully binds ``data_as_of`` (repair round-3,
  2026-09-06 independent review): ``collectors/base.py``'s ``last_date`` is the group-MAX
  OBSERVATION date across a source's own stored series, not an as-of instant — a lane
  entry with a fresh, healthy attempt/success clock and a legitimately far-future
  ``last_date`` (fred's FEDTARMD FOMC-projection series, real production shape) is a
  HEALTHY lane, not a corrupt one. ``scripts/build_capability_health.py``'s
  ``nightly_lane_facts`` no longer maps ``last_date`` onto ``data_as_of`` at all, and
  ``config/capability_health.yml``'s ``nightly_lane`` declarations no longer claim that
  clock. This engine module's corruption law is unchanged and still applies in FULL to
  any source that genuinely binds ``data_as_of``/``render_release`` (an
  ``output_health_artifact``'s already-judged ``source_asof``) — the fix is entirely in
  what the ADAPTER and REGISTRY claim a lane receipt carries, never a type-based carve-out
  inside this pure resolver.
* Removing ``last_date`` from ``data_as_of`` (above) fixed a false-GREEN-turned-permanent-
  corrupt bug but, on its own, left the nightly-lane DATA-FRESHNESS axis unrepresented: a
  lane's ``status`` is derived from the SAME group-max ``last`` that a forward-dated
  projection series poisons, so a genuinely frozen sibling series inside that same group
  can never push ``status`` off "ok". Repair round-5 restores that axis from a receipt
  that is immune to the poisoning: ``collectors/base.py``'s per-series frozen-tail
  detector writes named rows to ``run_status.json``'s top-level ``stale_series`` array
  explicitly "for the health surface" (one row per (group, series), each comparing that
  ONE series' own last observation against its OWN cadence budget, never the group max).
  ``scripts/build_capability_health.py``'s ``nightly_lane_facts`` joins a ref's matching
  ``stale_series`` rows onto that ref's fact (exact ``group == ref`` match) and forces an
  explicit ``state=stale`` with a ``state_detail`` evidence string naming the frozen
  series — the ABSENCE of a matching row, combined with a healthy ``status``, is what
  actually composes to "healthy": the owning collector's own staleness detector found
  nothing wrong on EITHER axis it knows how to check, not a silent skip of the data axis.
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

import re
from datetime import date, datetime, timedelta, timezone
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

#: The SAME future-corruption check, widened for a BARE calendar-date value only (repair
#: round-3, item 3; window corrected round-5, item 2): a date has no time-of-day, so a
#: source reporting "today's date" from as far ahead as UTC+14 (Kiribati/Line Islands —
#: the real maximum legitimate calendar-date lead any host's local clock can produce)
#: can legitimately name a calendar date that is, in absolute UTC instant terms, up to
#: 14h ahead of a UTC-based ``now``. +2h of ordinary clock/runner skew on top of that
#: 14h ceiling gives the 16h window below — e.g. a `2026-09-06` date value at
#: now=2026-09-05T22:30Z is a real calendar-date lead, not corruption. The window is
#: DERIVED (14h true timezone ceiling + 2h skew budget), not an arbitrarily round
#: number — round-3's original 26h figure had no derivation at all and was simply too
#: wide. An INSTANT-grain value (anything carrying a real time-of-day) keeps the tight
#: :data:`FUTURE_CLOCK_TOLERANCE` — this wider window applies ONLY when the raw value
#: itself parsed as a bare date (see :func:`_parse_instant_or_date`).
DATE_GRAIN_FUTURE_TOLERANCE = timedelta(hours=16)

#: Length cap + join-safety scrub applied to ANY third-party-derived free text — an
#: adapter's ``blind_reason`` (which embeds a raw, unbounded collector status string) or
#: ``rights_detail`` (repair round-3, item 4); and, as of repair round-5 item 3, every
#: OTHER evidence ingress that interpolates a receipt-carried value straight into an
#: evidence string: ``process_commit``/``checkout_commit`` (deployment-skew evidence),
#: ``replay_of``/``data_as_of`` (correction-replay evidence), and an adapter's own
#: ``state_detail`` (an explicit-state fact's free-text disclosure — e.g.
#: ``nightly_lane_facts``' ``stale_series`` join, repair round-5 item 1). This module is
#: the PUBLISHER of the single joined ``"; ".join(reason_codes)`` reason string, so it is
#: the one place that can guarantee an embedded "; " in foreign text can never be
#: misread as extra, fabricated reason codes — independent of whatever cap an individual
#: adapter applies on its own (``scripts/build_capability_health.py``'s
#: ``_RIGHTS_DETAIL_MAX_CHARS`` stays: defense for ONE adapter; this is defense for
#: every adapter, including ones that forget to cap, and for every ingress, not just the
#: two round-3 first covered).
FOREIGN_TEXT_MAX_CHARS = 300

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
#: repair MINOR-5: an upstream module (output_health) reached only a PARTIAL assessment
#: and recorded no explicit state for this source — distinct from
#: :data:`REASON_NO_CLOCK_EVIDENCE` (this source declares no last_attempted/
#: last_successful at all) so a reader is never told "no clock evidence" when the real
#: cause is an upstream partial verdict with nothing derivable from it. The resolved
#: state stays could_not_look either way — only the reason NAME changes.
REASON_UPSTREAM_PARTIAL_BLIND = "upstream_partial_blind"
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
#: repair MINOR-1: an adapter (currently ``nightly_lane_facts``) that recognizes a
#: receipt shape it has no honest verdict for (an unrecognized/absent collector status,
#: e.g. ``check_failed`` from a non-Adapter collect.py step) supplies a fully-formatted
#: ``blind_reason`` string on the fact — see ``fact.get("blind_reason")`` in
#: :func:`_source_verdict`. The base code below is what :func:`reason_base` extracts
#: from it; the adapter appends its own ``:<ref>:<status>`` detail.
REASON_UNKNOWN_COLLECTOR_STATUS = "unknown_collector_status"

REASON_CODES: frozenset[str] = frozenset({
    REASON_NO_RECEIPT_SOURCES,
    REASON_RECEIPT_UNREADABLE,
    REASON_RECEIPT_CORRUPT,
    REASON_UNKNOWN_RECEIPT_TYPE,
    REASON_NO_CLOCK_EVIDENCE,
    REASON_UPSTREAM_COULD_NOT_LOOK,
    REASON_UPSTREAM_PARTIAL_BLIND,
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
    REASON_UNKNOWN_COLLECTOR_STATUS,
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

    problems.extend(_detect_depends_on_cycles(capabilities, ids_declared=ids_declared))

    return sorted(problems)


def _detect_depends_on_cycles(
    capabilities: Sequence[Mapping[str, Any]], *, ids_declared: set[str]
) -> list[str]:
    """MINOR-2 repair: the pairwise checks above (self-loop, unresolvable ref) cannot
    see a LONGER cycle — ``a depends_on b`` and ``b depends_on a`` each look locally
    valid; only walking the whole graph reveals the loop.

    CORRECTED RATIONALE (repair round-3, item 5, 2026-09-06 independent review): this is
    registry-hygiene fail-closedness, NOT a non-termination guard. The original comment
    here claimed ``_cap_by_dependency`` "never terminates on a cyclic depends_on graph
    (each side caps the other, forever)" — that was FALSE. ``_cap_by_dependency`` is a
    single non-recursive pass over one capability's already-resolved ``base_by_id``
    records (built once, up front, in :func:`resolve_capability_health`); it walks each
    capability's own ``depends_on`` list exactly once and returns, so it terminates on
    ANY graph, cyclic or not — it would simply produce a MEANINGLESS answer on a cycle
    (each side capping the other from a snapshot neither can see reflected in the
    other's own resolution, since both were already resolved independently before either
    cap was applied). A cyclic dependency declaration is refused here because it can
    never express a coherent "this depends on that" ordering, not because resolving one
    would hang.

    Only edges between two DECLARED, non-self ids are walked — a self-loop or an
    unresolvable reference is already reported by the caller and would otherwise be
    reported again here as a spurious "cycle".
    """
    graph: dict[str, list[str]] = {}
    for cap in capabilities:
        if not isinstance(cap, Mapping):
            continue
        cid = cap.get("id")
        if not isinstance(cid, str) or cid not in ids_declared:
            continue
        graph[cid] = sorted({
            str(dep) for dep in (cap.get("depends_on") or [])
            if dep != cid and dep in ids_declared
        })

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(graph, WHITE)
    found: set[tuple[str, ...]] = set()
    problems: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        color[node] = GRAY
        for dep in graph.get(node, []):
            if color.get(dep, WHITE) == GRAY:
                idx = path.index(dep) if dep in path else 0
                cycle_nodes = [*path[idx:], dep]
                key = tuple(sorted(set(cycle_nodes)))
                if key not in found:
                    found.add(key)
                    problems.append(
                        f"depends_on cycle detected: {' -> '.join(cycle_nodes)}"
                    )
            elif color.get(dep, WHITE) == WHITE:
                visit(dep, [*path, dep])
        color[node] = BLACK

    for cid in sorted(graph):
        if color.get(cid) == WHITE:
            visit(cid, [cid])

    return problems


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


#: Round-5 repair, item 5: ``date.fromisoformat``/``datetime.fromisoformat`` widened
#: their accepted grammar in Python 3.11+ to most of ISO 8601 — including ISO WEEK
#: dates (``"2026-W36-1"``) and the COMPACT basic format (``"20260904"``, no
#: separators). No collector or adapter in this repo ever produces either shape; a
#: source's calendar-date clock is always the canonical ``YYYY-MM-DD`` extended form.
#: Accepting the wider grammar here would let an unusual or malformed string parse
#: into a plausible-looking date instead of being disclosed as unparseable — this
#: regex is the fence that keeps the bare-date fallback to EXACTLY the one shape this
#: module actually promises to read.
_CANONICAL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_instant_or_date(raw: Any) -> tuple[datetime | None, bool]:
    """Read *raw* as a tz-aware instant. Returns ``(instant_or_None, is_date_grain)``.

    A BARE calendar date reads as midnight UTC on that date and is flagged
    ``is_date_grain=True`` so a caller can apply the wider future-tolerance window
    (repair round-3, item 3) — accepted in EITHER of the two shapes a receipt fact can
    carry (repair round-3, item 6): a CANONICAL ISO date string (``"2026-09-04"``,
    matched against :data:`_CANONICAL_DATE_RE` — round-5 item 5) or a real
    ``datetime.date`` object, which is exactly what PyYAML hands back for an unquoted
    date scalar in ``config/capability_health.yml``. A string that merely fromisoformat
    CAN parse but does not match the canonical ``YYYY-MM-DD`` shape (an ISO week date,
    a compact basic-format date, ...) is treated as unparseable, not as a silently
    accepted date — see :data:`_CANONICAL_DATE_RE`'s docstring for why.

    Used by BOTH :func:`_clock_reading`'s corruption check and the capability-level
    display-clock merge in :func:`_resolve_one` (repair round-3, item 7) — the merge
    previously routed through :func:`_as_utc` alone, which cannot read a bare date at
    all, silently degenerating "most recent wins" into "first non-None wins" whenever
    two date-grain values were being compared. Routing both through this one function
    keeps the merge order-independent.
    """
    if raw is None or raw == "":
        return None, False
    dt = _as_utc(raw)
    if dt is not None:
        return dt, False
    d: date | None = None
    if isinstance(raw, str):
        stripped = raw.strip()
        if _CANONICAL_DATE_RE.match(stripped):
            try:
                d = date.fromisoformat(stripped)
            except ValueError:
                d = None
    elif isinstance(raw, date) and not isinstance(raw, datetime):
        d = raw
    if d is not None:
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc), True
    return None, False


def _cap_foreign_text(value: Any) -> str:
    """Cap length and scrub the ``"; "`` reason-join separator out of third-party text
    before it is allowed into reason_codes/evidence/the joined reason string (repair
    round-3, item 4). See :data:`FOREIGN_TEXT_MAX_CHARS`."""
    text = str(value).replace("; ", " - ")
    return text[:FOREIGN_TEXT_MAX_CHARS]


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
    cannot be read as an instant (or a real calendar date — see below) at all, or
    :data:`REASON_CLOCK_FUTURE_DATED` when it parses but resolves more than
    :data:`FUTURE_CLOCK_TOLERANCE` beyond *now* (repair findings I2/I4). A genuinely
    ABSENT value (``None``/``""``) is neither present-and-bad NOR a reading — it returns
    ``(None, None)``, distinct from a corrupt one.

    IMPORTANT-1 repair: ``data_as_of``/``render_release`` are frequently DATE-grain, not
    instant-grain (a collector's ``last_date: "2026-09-04"`` is the real, common shape —
    though a ``nightly_lane`` receipt never actually binds ``data_as_of`` as of repair
    round-3; see the module docstring). ``lib.dataos.temporal.utc()`` correctly REFUSES
    to promote a bare date to an instant for point-in-time reads (§D3: a date has no
    timezone, doing so is a guess) — but a corruption check only needs "is this a real
    calendar date, and is it implausibly far in the future", never a real instant used
    anywhere else. A bare date (an ISO string OR a real ``datetime.date`` object —
    repair round-3, item 6) is read as midnight UTC on that date SOLELY for that
    comparison, via :func:`_parse_instant_or_date`; the ORIGINAL raw value is still what
    gets published in the record's ``clocks`` block (see the caller) — this function
    never invents a timestamp that overwrites what was actually received. A date-grain
    reading gets the wider :data:`DATE_GRAIN_FUTURE_TOLERANCE` window rather than
    :data:`FUTURE_CLOCK_TOLERANCE` (repair round-3, item 3).
    """
    if raw is None or raw == "":
        return None, None
    dt, is_date_grain = _parse_instant_or_date(raw)
    if dt is None:
        return None, REASON_CLOCK_UNPARSEABLE
    tolerance = DATE_GRAIN_FUTURE_TOLERANCE if is_date_grain else FUTURE_CLOCK_TOLERANCE
    if dt > now + tolerance:
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

    # IMPORTANT-1 repair: route EVERY one of the four clock kinds through the same
    # unparseable/future-dated corruption check, not just last_attempted/last_successful.
    # Previously data_as_of/render_release were copied into the published `clocks` block
    # VERBATIM with no check at all — a lane entry with a healthy, fresh checked_at but a
    # garbage or future-dated `last_date` (the real fred/yahoo shape passes `last_date`
    # straight through as data_as_of) could publish e.g. data_as_of=2028-01-01 right next
    # to state=healthy, reason="ok". A corrupt clock of ANY kind is now a corrupt receipt
    # on THIS source's axis — same severity as the fact-level `corrupt` flag above: it
    # never enters `clocks`, and this source's own verdict becomes could_not_look,
    # regardless of what any other field on the fact says (rights_blocked, an explicit
    # state, deployment skew, ...). Every bad clock is reported, not just the first.
    clock_bad_reasons: list[str] = []
    for key in CLOCK_KEYS:
        raw = fact.get(key)
        _, bad = _clock_reading(raw, now=now)
        if bad:
            clock_bad_reasons.append(f"{bad}:{label}:{key}")
        elif raw:
            display_clocks[key] = raw
    if clock_bad_reasons:
        # round review MINOR-1: this early return still fails CLOSED (could_not_look) —
        # a corrupt clock must keep outranking even a HEALTHY upstream verdict
        # (test_important1_corrupt_clock_outranks_an_otherwise_healthy_explicit_state),
        # so the resolved state here is deliberately left None, unchanged. But when
        # output_health already reached an explicit judgment on this same fact
        # (fact["state"] in STATES — including a non-healthy one like stale), that
        # judgment used to vanish with no trace: the record read identically to "no one
        # could look" whether or not anyone upstream ever looked. Disclose it instead —
        # a reader can now tell "upstream judged it, we could not read its clock" apart
        # from "no one could look" — without changing the fail-closed resolved state.
        explicit_upstream_state = fact.get("state")
        if explicit_upstream_state in STATES:
            evidence.append(_evidence(
                "receipt", label,
                f"upstream state={explicit_upstream_state}, watermark unreadable — "
                "clock corruption outranks the upstream verdict",
            ))
        return None, clock_bad_reasons, evidence, display_clocks

    # MINOR-1 repair: an adapter (nightly_lane_facts) that recognizes a receipt shape it
    # has no honest verdict for (an unknown/absent collector status) supplies a
    # fully-formatted `blind_reason` on the fact rather than leaving it to fall through
    # to a generic no-clock-evidence read or a fabricated "attempted, no prior success".
    # Domain knowledge of the actual ref/status value lives only in the adapter, so the
    # engine treats this as an opaque, already-typed disclosure — never silently
    # downgraded, never able to read healthy.
    blind_reason = fact.get("blind_reason")
    if isinstance(blind_reason, str) and blind_reason:
        # round-3, item 4: blind_reason embeds a raw, adapter-supplied collector status
        # string (see REASON_UNKNOWN_COLLECTOR_STATUS) that this engine never controls
        # the length or contents of — cap and reason-join-scrub it at THIS boundary,
        # the one place that can guarantee it before it enters reason_codes/reason.
        safe_blind_reason = _cap_foreign_text(blind_reason)
        evidence.append(_evidence("receipt", label, safe_blind_reason))
        reasons.append(safe_blind_reason)
        return None, reasons, evidence, display_clocks

    # Clocks this source is DECLARED to bind, honoring a per-fact override (a source that
    # can only ever supply a subset of what the registry declares).
    bind = fact.get("clocks_bound")
    bind = (
        bind if isinstance(bind, Sequence) and not isinstance(bind, (str, bytes))
        else (decl.get("clocks") or [])
    )

    if fact.get("rights_blocked"):
        # round-3, item 4: rights_detail is likewise adapter-supplied third-party text
        # (a raw collector error string) — cap/scrub it here too, independent of
        # whatever cap the adapter already applied on its own.
        detail = _cap_foreign_text(fact.get("rights_detail") or "rights-restricted")
        evidence.append(_evidence("receipt", label, detail))
        return STATE_UNAVAILABLE, [f"{REASON_RIGHTS_BLOCKED}:{label}"], evidence, display_clocks

    pc, cc = fact.get("process_commit"), fact.get("checkout_commit")
    skew = bool(pc and cc and pc != cc)
    if skew:
        reasons.append(f"{REASON_DEPLOYMENT_COMMIT_SKEW}:{label}")
        # round-5 repair (item 3): process_commit/checkout_commit are receipt-carried
        # text — cap/scrub them at this boundary too, uniformly with blind_reason/
        # rights_detail (round-3, item 4), so the "every third-party text is capped
        # and join-safe" guarantee holds for every evidence ingress, not only the two
        # round-3 first covered.
        evidence.append(_evidence(
            "receipt", label,
            f"process_commit={_cap_foreign_text(pc)} "
            f"checkout_commit={_cap_foreign_text(cc)} — deployment skew"
        ))

    replay_of = fact.get("replay_of")
    if replay_of:
        reasons.append(f"{REASON_CORRECTION_REPLAY}:{label}")
        evidence.append(_evidence(
            "receipt", label,
            f"replay_of={_cap_foreign_text(replay_of)} "
            f"data_as_of={_cap_foreign_text(fact.get('data_as_of'))} "
            f"— original clock preserved in evidence, not overwritten silently",
        ))

    explicit = fact.get("state")
    if explicit in STATES:
        # A deployment-skew receipt CAPS state at degraded (repair fixture (e) ruling):
        # a source cannot be reported healthy while its own process/checkout commits
        # disagree, even when its upstream verdict was otherwise healthy.
        capped = STATE_DEGRADED if (skew and explicit == STATE_HEALTHY) else explicit
        # Round-5 repair (item 1): an adapter that forces an explicit state onto a fact
        # (e.g. nightly_lane_facts' stale_series join — a frozen-tail per-series
        # receipt immune to the group-max poisoning a forward-dated projection series
        # causes) may attach a free-text `state_detail` naming exactly what it found
        # (series/last_obs/age_days). That is third-party-derived text — capped and
        # reason-join-scrubbed at this boundary the same way blind_reason/rights_detail
        # already are (round-3, item 4), never left to ride uncapped or unsafe into the
        # published record.
        state_detail = fact.get("state_detail")
        if isinstance(state_detail, str) and state_detail:
            evidence.append(_evidence("receipt", label, _cap_foreign_text(state_detail)))
        return capped, reasons, evidence, display_clocks

    if explicit is None and str(fact.get("assessment_status") or "") == ASSESSMENT_COULD_NOT_LOOK:
        # An upstream module (output_health) already looked and could not decide. That is
        # a could_not_look CONTRIBUTION, not a missing receipt — the fact itself was
        # readable, its VERDICT is the blindness.
        evidence.append(_evidence("receipt", label, "upstream assessment_status=could_not_look"))
        reasons.append(f"{REASON_UPSTREAM_COULD_NOT_LOOK}:{label}")
        return None, reasons, evidence, display_clocks

    if (
        explicit is None
        and str(fact.get("assessment_status") or "") == ASSESSMENT_PARTIAL
        and CLOCK_LAST_ATTEMPTED not in bind
        and CLOCK_LAST_SUCCESSFUL not in bind
    ):
        # MINOR-5 repair: an upstream module reached only a PARTIAL assessment and
        # recorded no explicit state, and this source declares no last_attempted/
        # last_successful of its own to fall back on. This used to fall through to the
        # generic REASON_NO_CLOCK_EVIDENCE branch below, which reads as "this source
        # declares no clock kind" — misleading when the real cause is an upstream
        # partial verdict with nothing derivable from it. Name it truthfully; the
        # resolved state is could_not_look either way (fail-closed, unchanged).
        evidence.append(_evidence(
            "receipt", label, "upstream assessment_status=partial, no derivable state",
        ))
        reasons.append(f"{REASON_UPSTREAM_PARTIAL_BLIND}:{label}")
        return None, reasons, evidence, display_clocks

    if CLOCK_LAST_ATTEMPTED not in bind and CLOCK_LAST_SUCCESSFUL not in bind:
        # This source never even declares an attempt/success clock (e.g. it only ever
        # binds data_as_of/render_release, or nothing at all) and carried no explicit
        # state — it has nothing to say about health either way.
        reasons.append(f"{REASON_NO_CLOCK_EVIDENCE}:{label}")
        return None, reasons, evidence, display_clocks

    # --- clock-derived verdict — THIS SOURCE'S OWN (ta, ts) pairing only (C2) ----------
    # ta/ts are already known non-corrupt here (the IMPORTANT-1 sweep above returns
    # early on any bad clock of any kind, ta/ts included), so `_clock_reading` can only
    # ever hand back a real instant or a genuine absence — never a `bad` reason.
    ta_raw = fact.get(CLOCK_LAST_ATTEMPTED) if CLOCK_LAST_ATTEMPTED in bind else None
    ts_raw = fact.get(CLOCK_LAST_SUCCESSFUL) if CLOCK_LAST_SUCCESSFUL in bind else None
    ta, _ = _clock_reading(ta_raw, now=now)
    ts, _ = _clock_reading(ts_raw, now=now)

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
            # round-3, item 7: read through the SAME bare-date-aware parser the
            # corruption check uses, not `_as_utc` alone — otherwise a date-grain
            # value's merge silently degenerates to "first non-None wins" instead of
            # "most recent wins" (a date-grain reading is invisible to `_as_utc`).
            cur_dt, _ = _parse_instant_or_date(cur)
            val_dt, _ = _parse_instant_or_date(val)
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
        # MINOR-2 repair: the repo's UI law is bilingual EN/ZH (CLAUDE.md §Ops); publish
        # the ZH label/next-action alongside the EN ones the same way `label_en` already
        # foreshadowed the slot. Both are None (not "", not a placeholder) when a
        # registry entry has not yet been translated — a reader can tell "no ZH text
        # written yet" from "translated to an empty string" — so this stays a additive,
        # non-breaking key for any registry entry not yet carrying `label_zh`.
        "label_zh": cap.get("label_zh"),
        "owner": cap.get("owner"),
        "artifacts": list(cap.get("artifacts") or []),
        "state": state,
        "assessment_status": assessment,
        "reason_codes": list(reasons),
        "clocks": dict(clocks),
        "next_action": cap.get("next_action_hint"),
        "next_action_zh": cap.get("next_action_hint_zh"),
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
        ``checkout_commit`` (deployment-skew detection), ``replay_of`` (an ISO instant
        naming the value a correction/replay receipt is amending), and ``state_detail``
        (round-5: free text an adapter attaches alongside an explicit ``state`` — e.g.
        nightly_lane_facts' stale_series join names the frozen series/last_obs/age_days —
        surfaced as capped, join-safe evidence, never as a reason code of its own).
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
