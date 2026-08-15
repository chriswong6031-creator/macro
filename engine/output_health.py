"""engine/output_health.py — the output-level health contract (Eval OS T4).

WHAT THIS ANSWERS, AND WHAT IT REFUSES TO ANSWER
------------------------------------------------
Per engine OUTPUT (one synapse artifact): healthy / degraded / stale / unavailable — or
that Eval OS could not determine the answer at all. The fourth answer is the point of the
module. PRODUCER HEALTH != OUTPUT HEALTH != READER HEALTH: a producer whose nightly job
went green can still be shipping a frozen file, and a file whose watermark is current can
still be stale in the copy a paying reader actually receives. Three planes, three
verdicts, and this module joins them under ONE precedence order instead of letting each
caller invent its own.

"I could not look" NEVER renders as "I looked and it was clean" (CLAUDE.md §Epistemics).
:data:`BLIND_REASONS` is that law as data: any of those reasons on an output's OWN core
evidence short-circuits to ``state=None, assessment_status='could_not_look'``, and no
later rule can convert that into ``healthy`` or ``unavailable``. An unreadable artifact
and a deleted artifact are different facts; the whole value of this layer is refusing to
collapse them.

A JOINING LAYER, NOT ANOTHER MONITOR
------------------------------------
Nothing here monitors anything. It reads already-existing evidence — the synapse census,
the T1 engine registry, a presence/watermark observation per artifact, the reader plane
(freshness sentinel + R2 audit), semantic self-health (Neural Web lobes, foresight legs)
and provider telemetry — and normalizes them. It builds no registry, keeps no dependency
graph of its own, holds no dead-man switch and COMMITS NOTHING. There is therefore no
T4 fixed point: this module's output is not a synapse artifact and cannot grade itself.

PURE. NO I/O, NO CLOCK, NO ENVIRONMENT
--------------------------------------
Every read, every probe and every wall-clock reading happens in
``scripts/build_output_health.py`` (or in the admin layer) and arrives here as an
argument. ``now`` is INJECTED and must be tz-aware — :func:`lib.dataos.temporal.utc`
refuses a naive datetime rather than guessing a zone, which is the same refusal the rest
of the estate makes. Same inputs -> byte-identical output; every list is sorted.

NO SCORES, NO RANKS, NO PROMOTION
---------------------------------
The record carries no score, weight, rank, promotion state or authority MUTATION. It
reports T1's ``artifact_authority`` and ``output_class`` verbatim and mutates neither. No
field here is a model input; health is an operating fact about a file, never a signal.

THE TIME-BASIS LAW (§5 of the commission)
-----------------------------------------
The governing watermark field is ``staleness_from`` when declared, else ``asof_field`` —
and the value is read from THAT FIELD ONLY. An observation naming a different field is
REFUSED (:data:`REASON_WATERMARK_FIELD_MISMATCH`), because a silent fallback to whatever
timestamp the file happens to carry is how a frozen store reads fresh forever. A promised
field that is absent from the content is blindness, not freshness.

DATE-ONLY WATERMARKS RESOLVE ONE WAY ONLY. ``2026-08-14`` is read at its most conservative
instant (end of that date, 00:00 UTC the next day). Inside SLA that is enough to prove
CURRENT. Beyond SLA it proves nothing: distinguishing a weekend/holiday lag from an
outage needs a declared calendar, synapse has no ``freshness_calendar`` field, and
inferring one from a ticker or a program name is a guess. So it returns
``date_only_calendar_unknown`` and could_not_look — deliberately NOT the weekend-aware
rule ``engine/neuralweb/health.py`` applies to its own rollup.

THE READER PLANE OUTRANKS THE PRODUCER (§8)
-------------------------------------------
A definitive CONTENT-clock reader verdict of stale/missing overrides any producer-side
current-ness, because the reader copy is what consumers actually receive. Clock kind is
adjudicated by CONTRACT, not by newest timestamp: content-clock evidence outranks
transport-clock evidence in BOTH directions — a fresh ``Last-Modified`` never rescues a
stale content watermark, and a stale transport stamp never overrides a definitively fresh
reader content watermark. A transport-clock verdict decides only where no content clock
exists at all.

DEPENDENCY BOUNDS ARE UPPER UNLESS PROVEN EXACT (§6)
----------------------------------------------------
Direct inputs are inferred mechanically: B is an input of A when A's producer appears in
B's ``consumers``. That inversion is EXACT only when A's producer registers exactly one
artifact; for a multi-output producer the inputs of all its outputs fold together, so the
bound is ``upper``. ``engine/neuralweb/support_map.py``'s ``_UPSTREAM_NOTE`` claims
upstream traversal is always exact — that claim does not hold for multi-output producers
(136 of 365 live producers, covering 412 of 642 artifacts), so this module computes its
own bound rather than inheriting it.

A self-loop (a producer that lists itself among its own artifact's consumers — 120 live
cases) is EXCLUDED from that artifact's inputs: reading your own prior vintage is not a
freshness gate on yourself.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from lib.dataos.temporal import TemporalError, utc

SCHEMA = "mastermind.output_health.v1"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

STATE_HEALTHY = "healthy"
STATE_DEGRADED = "degraded"
STATE_STALE = "stale"
STATE_UNAVAILABLE = "unavailable"

#: Ordered worst-first — the order the precedence ladder resolves them in.
STATES: tuple[str, ...] = (STATE_UNAVAILABLE, STATE_STALE, STATE_DEGRADED, STATE_HEALTHY)

ASSESSMENT_COMPLETE = "complete"
ASSESSMENT_PARTIAL = "partial"
ASSESSMENT_COULD_NOT_LOOK = "could_not_look"
ASSESSMENT_STATUSES: tuple[str, ...] = (
    ASSESSMENT_COMPLETE,
    ASSESSMENT_PARTIAL,
    ASSESSMENT_COULD_NOT_LOOK,
)

#: WHICH OBSERVATION PLANE DECIDED. Mandatory whenever ``state`` is non-null: a health
#: verdict that cannot say which plane produced it is unauditable, and the three planes
#: disagree often enough that the answer is the interesting half of the record.
#:   audit             — our own probe of the artifact (presence ladder / R2 anchor)
#:   content_watermark — the governing watermark inside the artifact
#:   write_time        — file mtime, lawful ONLY under the write-time contract (§5.2a)
#:   reader            — the freshness sentinel / R2 audit view of the served copy
#:   self_health       — the producer's own semantic health surface
#:   dependency        — an upstream input's state, folded in
DECIDED_BY_AUDIT = "audit"
DECIDED_BY_CONTENT = "content_watermark"
DECIDED_BY_WRITE_TIME = "write_time"
DECIDED_BY_READER = "reader"
DECIDED_BY_SELF_HEALTH = "self_health"
DECIDED_BY_DEPENDENCY = "dependency"
DECIDED_BY_VALUES: tuple[str, ...] = (
    DECIDED_BY_AUDIT,
    DECIDED_BY_CONTENT,
    DECIDED_BY_DEPENDENCY,
    DECIDED_BY_READER,
    DECIDED_BY_SELF_HEALTH,
    DECIDED_BY_WRITE_TIME,
)

DISPLAY_FULL = "full"
DISPLAY_REDUCED = "reduced"
DISPLAY_NONE = "none"
DISPLAY_UNKNOWN = "unknown"

#: state -> what a display surface may claim. A null state is ``unknown`` and must never
#: be rendered as a clean read.
DISPLAY_CONFIDENCE: dict[str | None, str] = {
    STATE_HEALTHY: DISPLAY_FULL,
    STATE_DEGRADED: DISPLAY_REDUCED,
    STATE_STALE: DISPLAY_NONE,
    STATE_UNAVAILABLE: DISPLAY_NONE,
    None: DISPLAY_UNKNOWN,
}

EVIDENCE_PLANES: tuple[str, ...] = (
    "dependency",
    "producer",
    "provider",
    "reader",
    "registry",
    "self_health",
)

# --- reason codes ----------------------------------------------------------
# BASE codes. A code may carry a ``:<artifact_id>`` suffix where the reason is ABOUT a
# named input; :func:`reason_base` strips it, which is what keeps the vocabulary closed
# while still naming the culprit.

REASON_NOT_IN_ENGINE_REGISTRY = "not_in_engine_registry"
REASON_PLACEHOLDER_PATH = "placeholder_path"
REASON_SPARSE_UNMATERIALIZED = "sparse_unmaterialized"
REASON_PRESENCE_UNOBSERVABLE = "presence_unobservable"
REASON_RUNTIME_ONLY_UNOBSERVABLE = "runtime_only_unobservable"
REASON_R2_UNOBSERVABLE = "r2_unobservable"
REASON_CONTENT_PARSE_ERROR = "content_parse_error"
REASON_WATERMARK_UNREADABLE_FORMAT = "watermark_unreadable_format"
REASON_WATERMARK_FIELD_MISMATCH = "watermark_field_mismatch"
REASON_PROMISED_ASOF_FIELD_ABSENT = "promised_asof_field_absent"
REASON_WATERMARK_UNPARSEABLE = "watermark_unparseable"
REASON_WATERMARK_UNREAD = "watermark_unread"
REASON_NAIVE_WATERMARK_COERCED_UTC = "naive_watermark_coerced_utc"
REASON_DATE_ONLY_CONSERVATIVE = "date_only_conservative"
REASON_DATE_ONLY_CALENDAR_UNKNOWN = "date_only_calendar_unknown"
REASON_NO_FRESHNESS_CONTRACT = "no_freshness_contract"
REASON_NO_SLA_DECLARED = "no_sla_declared"
REASON_WRITE_TIME_UNTRUSTED = "write_time_untrusted"
REASON_READER_STALE_OVERRIDES_PRODUCER = "reader_stale_overrides_producer"
REASON_PRODUCER_BEHIND_READER = "producer_behind_reader"
REASON_TRANSPORT_OUTRANKED = "transport_clock_outranked_by_content"
REASON_READER_INDETERMINATE = "reader_indeterminate"
REASON_SELF_INPUT_EXCLUDED = "self_input_excluded"
REASON_DEPENDENCY_CYCLE = "dependency_cycle"
REASON_REQUIRED_INPUT_UNASSESSED = "required_input_unassessed"
REASON_OPTIONAL_INPUT_MISSING = "optional_input_missing"
REASON_OPTIONAL_INPUT_STALE = "optional_input_stale"
REASON_OPTIONAL_INPUT_DEGRADED = "optional_input_degraded"
REASON_OPTIONAL_INPUT_UNASSESSED = "optional_input_unassessed"
REASON_ILLEGAL_OPTIONAL_UPSTREAM = "illegal_optional_upstream"
REASON_PROVIDER_RUNG_FAILURES = "provider_rung_failures_noted"
REASON_SELF_MONITOR_NO_SELF_EVIDENCE = "self_monitor_no_self_evidence"
REASON_SELF_HEALTH_UNKNOWN = "self_health_unknown"
REASON_SELF_HEALTH_MISSING = "self_health_missing"

REASON_CODES: frozenset[str] = frozenset({
    REASON_NOT_IN_ENGINE_REGISTRY,
    REASON_PLACEHOLDER_PATH,
    REASON_SPARSE_UNMATERIALIZED,
    REASON_PRESENCE_UNOBSERVABLE,
    REASON_RUNTIME_ONLY_UNOBSERVABLE,
    REASON_R2_UNOBSERVABLE,
    REASON_CONTENT_PARSE_ERROR,
    REASON_WATERMARK_UNREADABLE_FORMAT,
    REASON_WATERMARK_FIELD_MISMATCH,
    REASON_PROMISED_ASOF_FIELD_ABSENT,
    REASON_WATERMARK_UNPARSEABLE,
    REASON_WATERMARK_UNREAD,
    REASON_NAIVE_WATERMARK_COERCED_UTC,
    REASON_DATE_ONLY_CONSERVATIVE,
    REASON_DATE_ONLY_CALENDAR_UNKNOWN,
    REASON_NO_FRESHNESS_CONTRACT,
    REASON_NO_SLA_DECLARED,
    REASON_WRITE_TIME_UNTRUSTED,
    REASON_READER_STALE_OVERRIDES_PRODUCER,
    REASON_PRODUCER_BEHIND_READER,
    REASON_TRANSPORT_OUTRANKED,
    REASON_READER_INDETERMINATE,
    REASON_SELF_INPUT_EXCLUDED,
    REASON_DEPENDENCY_CYCLE,
    REASON_REQUIRED_INPUT_UNASSESSED,
    REASON_OPTIONAL_INPUT_MISSING,
    REASON_OPTIONAL_INPUT_STALE,
    REASON_OPTIONAL_INPUT_DEGRADED,
    REASON_OPTIONAL_INPUT_UNASSESSED,
    REASON_ILLEGAL_OPTIONAL_UPSTREAM,
    REASON_PROVIDER_RUNG_FAILURES,
    REASON_SELF_MONITOR_NO_SELF_EVIDENCE,
    REASON_SELF_HEALTH_UNKNOWN,
    REASON_SELF_HEALTH_MISSING,
})

#: THE COULD-NOT-LOOK SET. Any of these on the output's OWN evidence means Eval OS was
#: blind, and blindness is a THIRD answer — never healthy, never unavailable (§7).
BLIND_REASONS: frozenset[str] = frozenset({
    REASON_PLACEHOLDER_PATH,
    REASON_SPARSE_UNMATERIALIZED,
    REASON_PRESENCE_UNOBSERVABLE,
    REASON_RUNTIME_ONLY_UNOBSERVABLE,
    REASON_R2_UNOBSERVABLE,
    REASON_CONTENT_PARSE_ERROR,
    REASON_WATERMARK_UNREADABLE_FORMAT,
    REASON_WATERMARK_FIELD_MISMATCH,
    REASON_PROMISED_ASOF_FIELD_ABSENT,
    REASON_WATERMARK_UNPARSEABLE,
    REASON_WATERMARK_UNREAD,
    REASON_DATE_ONLY_CALENDAR_UNKNOWN,
})

#: ``parse_error`` values an adapter may pass to name a SPECIFIC blindness. Anything else
#: lands as :data:`REASON_CONTENT_PARSE_ERROR` with the raw string kept in ``evidence``,
#: so a free-form message can never mint a reason code.
BLIND_PARSE_TOKENS: frozenset[str] = frozenset({REASON_WATERMARK_UNREADABLE_FORMAT})

#: Semantic self-health, already normalized by the adapter (§9).
SELF_HEALTH_STATUSES: tuple[str, ...] = ("degraded", "missing", "ok", "unknown")

#: Reader-plane verdicts. ``indeterminate`` is evidence only: it blocks nothing and
#: decides nothing — a reader that could not answer is not a reader that saw a problem.
READER_VERDICTS: tuple[str, ...] = ("fresh", "indeterminate", "missing", "stale")
CLOCK_CONTENT = "content"
CLOCK_TRANSPORT = "transport"

DEPENDENCY_EXACT = "exact"
DEPENDENCY_UPPER = "upper"

#: Same pattern as ``engine/neuralweb/synapse.py``: a path holding ``<SYM>``-style tokens
#: names a FAMILY of files and cannot be probed as one.
_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+>")

#: A watermark that is a calendar date and nothing else.
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The literal string a synapse entry uses to say "this artifact carries no watermark".
_NULL_FIELD = "null"


def reason_base(code: str) -> str:
    """The base reason code — the part before any ``:<artifact_id>`` suffix."""
    return str(code).split(":", 1)[0]


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def _declared_field(value: Any) -> str | None:
    """A declared field NAME, or None when the entry declares no field.

    ``None`` and the literal string ``"null"`` are the same declaration (63 live
    artifacts, 62 of them YAML null and one the string) and both mean NO content-watermark
    contract.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == _NULL_FIELD:
        return None
    return text


def _positive_int(value: Any) -> int | None:
    """An SLA in hours, or None. A non-positive or non-int SLA is treated as undeclared —
    synapse's own validator refuses those, so this is belt-and-braces, not a second rule."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _as_utc(value: Any) -> datetime | None:
    """Tz-aware UTC, or None when the value cannot be read as an instant WITHOUT guessing."""
    if value is None:
        return None
    try:
        return utc(value)
    except (TemporalError, TypeError):
        return None


def _naive_as_utc(text: str) -> datetime | None:
    """A tz-NAIVE full timestamp coerced to UTC — the documented legacy allowance.

    The signal bus writes UTC (``engine/neuralweb/health.py`` treats every unqualified
    stamp that way), so this is an adapter allowance for that convention rather than a
    guess about an unknown producer — and it is DISCLOSED every time it fires
    (:data:`REASON_NAIVE_WATERMARK_COERCED_UTC`). A date-only value never reaches here.
    """
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=timezone.utc)


def _hours_between(now: datetime, then: datetime) -> float:
    return round((now - then).total_seconds() / 3600.0, 3)


def _evidence(plane: str, source: str, detail: str) -> dict[str, str]:
    return {"plane": plane, "source": source, "detail": detail}


def _sorted_evidence(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    seen: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row.get("plane")), str(row.get("source")), str(row.get("detail")))
        seen.setdefault(key, {"plane": key[0], "source": key[1], "detail": key[2]})
    return [seen[key] for key in sorted(seen)]


# ---------------------------------------------------------------------------
# Index over the two registries
# ---------------------------------------------------------------------------

class _Index:
    """Derived views over synapse + the T1 registry. Built once per resolve call."""

    def __init__(
        self,
        synapse: Mapping[str, Any],
        registry: Mapping[str, Any],
    ) -> None:
        raw = synapse.get("artifacts") or {}
        self.entries: dict[str, Mapping[str, Any]] = {
            str(aid): entry for aid, entry in raw.items() if isinstance(entry, Mapping)
        }
        self.ids: list[str] = sorted(self.entries)

        self.producer_of: dict[str, str] = {
            aid: str(entry.get("producer") or "") for aid, entry in self.entries.items()
        }
        self.producer_outputs: dict[str, list[str]] = {}
        for aid in self.ids:
            self.producer_outputs.setdefault(self.producer_of[aid], []).append(aid)

        # consumer module -> artifacts that declare it. The inversion the input inference
        # walks: B is an input of A when A's PRODUCER consumes B.
        self.consumed_by: dict[str, list[str]] = {}
        for aid in self.ids:
            for module in self.entries[aid].get("consumers") or []:
                self.consumed_by.setdefault(str(module), []).append(aid)

        # --- T1 join ------------------------------------------------------
        self.engine_of: dict[str, str] = {}
        self.output_class_of: dict[str, str | None] = {}
        self.authority_of: dict[str, str] = {}
        for engine in registry.get("engines") or []:
            if not isinstance(engine, Mapping):
                continue
            eid = str(engine.get("engine_id"))
            klass = engine.get("output_class")
            for row in engine.get("artifacts") or []:
                if not isinstance(row, Mapping):
                    continue
                aid = str(row.get("id"))
                self.engine_of[aid] = eid
                self.output_class_of[aid] = klass if isinstance(klass, str) else None
                self.authority_of[aid] = str(row.get("artifact_authority") or "unknown")
        # T1 EXCLUSIONS ARE NOT DROPS. An excluded cell still lists its artifact ids, and
        # its ``would_be_artifact_authorities`` is the set over the whole cell — so it
        # answers per artifact only when the cell is homogeneous. Where it is not, the
        # honest answer is "unknown", never the first sorted value.
        for row in registry.get("excluded") or []:
            if not isinstance(row, Mapping):
                continue
            would_be = [str(a) for a in row.get("would_be_artifact_authorities") or []]
            for aid in row.get("artifacts") or []:
                aid = str(aid)
                self.authority_of.setdefault(
                    aid, would_be[0] if len(would_be) == 1 else "unknown"
                )

    def required_inputs(self, artifact_id: str) -> list[str]:
        """Direct inferred inputs of *artifact_id*, self EXCLUDED (§6)."""
        producer = self.producer_of.get(artifact_id, "")
        if not producer:
            return []
        return sorted(
            aid for aid in self.consumed_by.get(producer, []) if aid != artifact_id
        )

    def self_loop(self, artifact_id: str) -> bool:
        """True when the artifact lists its own producer among its consumers."""
        producer = self.producer_of.get(artifact_id, "")
        if not producer:
            return False
        return producer in {
            str(m) for m in (self.entries[artifact_id].get("consumers") or [])
        }

    def dependency_bound(self, artifact_id: str) -> str:
        """``exact`` only when the producer registers exactly one artifact (§6)."""
        producer = self.producer_of.get(artifact_id, "")
        outputs = self.producer_outputs.get(producer, [])
        return DEPENDENCY_EXACT if len(outputs) == 1 else DEPENDENCY_UPPER


def optional_upstream_violations(
    synapse: Mapping[str, Any],
    artifact_id: str,
    declared: Sequence[str],
) -> list[str]:
    """Why each declared ``health_optional_upstreams`` entry is illegal (empty = legal).

    The three conditions, mirrored from ``engine/neuralweb/synapse.validate_registry`` so
    the resolver refuses what the validator refuses (a validator a runtime does not obey
    is decoration):

      (a) the entry names an existing artifact,
      (b) it is in the mechanically inferred direct-upstream candidate set of the
          consuming artifact — the derived graph stays the source of truth and the field
          expresses only the optional DELTA,
      (c) the consuming artifact carries ``notes`` (optionality is a semantic claim and
          needs a written, evidence-backed reason).
    """
    index = _Index(synapse, {})
    return _optional_violations(index, artifact_id, declared)


def _optional_violations(
    index: _Index, artifact_id: str, declared: Sequence[str]
) -> list[str]:
    entry = index.entries.get(artifact_id)
    if entry is None:
        return [f"{artifact_id}: unknown artifact"]
    candidates = set(index.required_inputs(artifact_id))
    problems: list[str] = []
    if declared and not entry.get("notes"):
        problems.append(
            f"{artifact_id}: health_optional_upstreams requires a notes field giving the "
            f"evidence for treating an input as optional"
        )
    for raw in declared:
        upstream = str(raw)
        if upstream not in index.entries:
            problems.append(
                f"{artifact_id}: health_optional_upstreams {upstream!r} is not a "
                f"registered artifact id"
            )
        elif upstream not in candidates:
            problems.append(
                f"{artifact_id}: health_optional_upstreams {upstream!r} is not in the "
                f"inferred direct-upstream set of {artifact_id}"
            )
    return sorted(problems)


# ---------------------------------------------------------------------------
# Reader plane
# ---------------------------------------------------------------------------

def _reader_rows(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [row for row in value if isinstance(row, Mapping)]
    return []


#: Severity order for two readers of the SAME clock kind. The WORSE observation governs:
#: a reader that received a stale copy saw a real thing, and understatement is the
#: dangerous direction for a health verdict (the same reason T1 takes MAX authority).
_READER_SEVERITY = {"missing": 0, "stale": 1, "fresh": 2, "indeterminate": 3}


def _reader_rank(row: Mapping[str, Any]) -> tuple[int, int, str]:
    """Sort key: content clock before transport, then worst verdict, then source name.

    THE CLOCK-KIND LAW IS A RANKING, not a special case: whichever plane holds the
    stronger clock governs, in both directions. The source name is only ever a tie-break
    between two equally strong, equally severe observations, so the choice is
    deterministic without being arbitrary about the verdict.
    """
    content = 0 if row.get("clock_kind") == CLOCK_CONTENT else 1
    severity = _READER_SEVERITY.get(str(row.get("verdict")), 3)
    return (content, severity, str(row.get("source") or ""))


def _governing_reader(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return sorted(rows, key=_reader_rank)[0] if rows else None


# ---------------------------------------------------------------------------
# Freshness axis (§5 time-basis law + §8 clock-kind law)
# ---------------------------------------------------------------------------

#: Freshness verdicts. ``vacuous`` = the artifact declares no freshness contract, so the
#: axis is complete and empty — NOT a gap (7 live artifacts declare neither watermark nor
#: SLA, and the registry's own declaration is that freshness is not part of their
#: contract). ``unassessable`` blocks healthy without creating a negative.
FRESH_CURRENT = "current"
FRESH_STALE = "stale"
FRESH_VACUOUS = "vacuous"
FRESH_UNASSESSABLE = "unassessable"
FRESH_BLIND = "blind"


def _producer_freshness(
    *,
    entry: Mapping[str, Any],
    obs: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """The producer-side freshness read, before the reader plane is folded in."""
    field = _declared_field(entry.get("staleness_from")) or _declared_field(
        entry.get("asof_field")
    )
    sla = _positive_int(entry.get("freshness_sla_hours"))
    out: dict[str, Any] = {
        "verdict": FRESH_UNASSESSABLE,
        "decided_by": None,
        "reasons": [],
        "evidence": [],
        "age_hours": None,
        "source_asof": None,
        "field": field,
    }
    mtime = _as_utc(obs.get("mtime_utc"))
    mtime_trusted = bool(obs.get("mtime_trusted"))

    if field is None:
        # --- write-time contract (§5.2) --------------------------------
        if sla is None:
            out["verdict"] = FRESH_VACUOUS
            out["reasons"].append(REASON_NO_FRESHNESS_CONTRACT)
            return out
        if mtime is None or not mtime_trusted:
            # mtime from a checkout is an OBSERVER stamp — a status sweep or a Finder
            # visit rewrites it repo-wide — so it is evidence only where the caller
            # declares it trustworthy. Absent trust the axis is unassessed; it never
            # becomes staleness.
            out["reasons"].append(REASON_WRITE_TIME_UNTRUSTED)
            return out
        age = _hours_between(now, mtime)
        out["age_hours"] = age
        out["decided_by"] = DECIDED_BY_WRITE_TIME
        out["verdict"] = FRESH_CURRENT if age <= sla else FRESH_STALE
        out["evidence"].append(
            _evidence("producer", "mtime", f"write-time contract: {age}h vs SLA {sla}h")
        )
        return out

    # --- content-watermark contract (§5.3) -----------------------------
    used = obs.get("watermark_field_used")
    if isinstance(used, str) and used.strip() and used.strip() != field:
        # THE NO-SILENT-FALLBACK LAW. An observation that read a DIFFERENT field is
        # refused outright: substituting whatever timestamp the file happens to carry is
        # exactly how a frozen store keeps reading fresh.
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(REASON_WATERMARK_FIELD_MISMATCH)
        out["evidence"].append(
            _evidence(
                "producer",
                "watermark",
                f"observation read {used.strip()!r}; the declared field is {field!r}",
            )
        )
        return out

    parse_error = obs.get("parse_error")
    if isinstance(parse_error, str) and parse_error.strip():
        token = parse_error.strip()
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(
            token if token in BLIND_PARSE_TOKENS else REASON_CONTENT_PARSE_ERROR
        )
        out["evidence"].append(_evidence("producer", "content", token))
        return out

    if obs.get("asof_field_present") is False:
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(REASON_PROMISED_ASOF_FIELD_ABSENT)
        out["evidence"].append(
            _evidence(
                "producer",
                "content",
                f"declared field {field!r} is absent from the content — no substitute "
                f"field is consulted",
            )
        )
        return out

    raw = obs.get("content_asof_raw")
    if raw is None:
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(REASON_WATERMARK_UNREAD)
        return out
    if not isinstance(raw, str) or not raw.strip():
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(REASON_WATERMARK_UNPARSEABLE)
        out["source_asof"] = raw if isinstance(raw, str) else None
        return out

    text = raw.strip()
    out["source_asof"] = raw
    if mtime is not None:
        out["evidence"].append(
            _evidence(
                "producer",
                "mtime",
                f"mtime {mtime.isoformat()} recorded as corroboration only — a content "
                f"watermark is present and governs",
            )
        )

    if _DATE_ONLY_RE.match(text):
        day = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        end_of_day = day + timedelta(days=1)
        age_min = _hours_between(now, end_of_day)
        out["age_hours"] = age_min
        out["evidence"].append(
            _evidence(
                "producer",
                "watermark",
                f"date-only {text}: minimum age {age_min}h read at end of content date",
            )
        )
        if sla is None:
            out["verdict"] = FRESH_VACUOUS
            out["reasons"] += [REASON_NO_SLA_DECLARED, REASON_DATE_ONLY_CONSERVATIVE]
            return out
        if age_min <= sla:
            out["verdict"] = FRESH_CURRENT
            out["decided_by"] = DECIDED_BY_CONTENT
            out["reasons"].append(REASON_DATE_ONLY_CONSERVATIVE)
            return out
        # Beyond SLA a date-only watermark cannot separate a weekend/holiday lag from an
        # outage, and synapse declares no calendar. Inferring one from a name is the guess
        # this module exists to refuse.
        out["verdict"] = FRESH_BLIND
        out["reasons"].append(REASON_DATE_ONLY_CALENDAR_UNKNOWN)
        return out

    stamp = _as_utc(text)
    if stamp is None:
        stamp = _naive_as_utc(text)
        if stamp is None:
            out["verdict"] = FRESH_BLIND
            out["reasons"].append(REASON_WATERMARK_UNPARSEABLE)
            return out
        out["reasons"].append(REASON_NAIVE_WATERMARK_COERCED_UTC)
    age = _hours_between(now, stamp)
    out["age_hours"] = age
    if sla is None:
        out["verdict"] = FRESH_VACUOUS
        out["reasons"].append(REASON_NO_SLA_DECLARED)
        return out
    out["decided_by"] = DECIDED_BY_CONTENT
    out["verdict"] = FRESH_CURRENT if age <= sla else FRESH_STALE
    out["evidence"].append(
        _evidence("producer", "watermark", f"{field}={text}: {age}h vs SLA {sla}h")
    )
    return out


def _reader_presence(reader: Mapping[str, Any] | None) -> bool | None:
    """What the reader plane proves about EXISTENCE, or None when it proves nothing.

    A reader that read the object at all proves it exists; a reader that definitively
    could not fetch it proves it does not. Anything else is silent on presence.
    """
    if reader is None:
        return None
    verdict = reader.get("verdict")
    if verdict == "missing":
        return False
    if verdict in ("fresh", "stale"):
        return True
    return None


def _fold_reader(
    *,
    fresh: dict[str, Any],
    reader: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply the reader plane to the producer-side freshness read (§8). Mutates in place."""
    if reader is None:
        return fresh
    verdict = reader.get("verdict")
    clock = reader.get("clock_kind")

    if verdict == "indeterminate":
        # A reader that could not answer is not a reader that saw a problem: evidence
        # only, no state effect, and it blocks nothing.
        fresh["reasons"].append(REASON_READER_INDETERMINATE)
        return fresh

    if verdict == "missing":
        # Presence, not freshness — handled by the presence axis. Recorded here so the
        # override is disclosed on the record either way.
        fresh["reasons"].append(REASON_READER_STALE_OVERRIDES_PRODUCER)
        return fresh

    producer_answered_on_content = fresh["decided_by"] == DECIDED_BY_CONTENT

    if verdict == "stale":
        if clock == CLOCK_CONTENT:
            fresh["verdict"] = FRESH_STALE
            fresh["decided_by"] = DECIDED_BY_READER
            fresh["reasons"].append(REASON_READER_STALE_OVERRIDES_PRODUCER)
            if reader.get("observed_asof") and not fresh["source_asof"]:
                fresh["source_asof"] = str(reader["observed_asof"])
            return fresh
        # Transport clock. It decides only where no content clock answered at all —
        # a fresh content watermark outranks a stale transport stamp.
        if producer_answered_on_content:
            fresh["reasons"].append(REASON_TRANSPORT_OUTRANKED)
            return fresh
        fresh["verdict"] = FRESH_STALE
        fresh["decided_by"] = DECIDED_BY_READER
        fresh["reasons"].append(REASON_READER_STALE_OVERRIDES_PRODUCER)
        return fresh

    # verdict == "fresh"
    if clock == CLOCK_CONTENT:
        if fresh["verdict"] == FRESH_STALE:
            # The reader copy is the one consumers receive, so it governs — and the
            # producer lag is kept as a diagnostic rather than dropped.
            fresh["reasons"].append(REASON_PRODUCER_BEHIND_READER)
        fresh["verdict"] = FRESH_CURRENT
        fresh["decided_by"] = DECIDED_BY_READER
        return fresh
    # Transport clock, fresh: a server stamp says when bytes were served, not what is in
    # them, so it never rescues a stale or unreadable content watermark.
    if fresh["verdict"] in (FRESH_STALE, FRESH_BLIND):
        fresh["reasons"].append(REASON_TRANSPORT_OUTRANKED)
        return fresh
    if fresh["verdict"] == FRESH_UNASSESSABLE:
        # No content clock exists at all (write-time contract, no trusted mtime): a
        # server-stamped transport clock IS the best lawful evidence here.
        fresh["verdict"] = FRESH_CURRENT
        fresh["decided_by"] = DECIDED_BY_READER
        fresh["reasons"] = [
            r for r in fresh["reasons"] if r != REASON_WRITE_TIME_UNTRUSTED
        ]
    return fresh


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------

_CYCLE = object()


def resolve_output_health(
    *,
    synapse: Mapping[str, Any],
    registry: Mapping[str, Any],
    observations: Mapping[str, Mapping[str, Any]],
    reader_observations: Mapping[str, Any] | None = None,
    self_health: Mapping[str, Mapping[str, Any]] | None = None,
    provider_events: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    optional_upstream_overrides: Mapping[str, Sequence[str]] | None = None,
    now: datetime,
) -> dict[str, Any]:
    """Resolve one health record per synapse artifact. PURE — see the module docstring.

    Parameters
    ----------
    synapse
        Parsed ``config/synapse.yml`` (the artifact census: path, producer, consumers,
        storage, asof_field, staleness_from, freshness_sla_hours, notes).
    registry
        The T1 view from ``scripts/build_intelligence_registry.build()`` — supplies
        ``engine_id``, the curated ``output_class`` overlay and ``artifact_authority``.
        An artifact in synapse but in no T1 engine cell keeps a record with
        ``engine_id: null`` and :data:`REASON_NOT_IN_ENGINE_REGISTRY`; nothing is dropped
        and no cell is invented.
    observations
        Per artifact: ``exists`` (bool | None — None means COULD NOT DETERMINE),
        ``presence_source`` ('filesystem' | 'git_head' | 'declared' | None),
        ``content_asof_raw``, ``asof_field_present``, ``watermark_field_used``,
        ``mtime_utc``, ``mtime_trusted``, ``parse_error``, ``sparse_unmaterialized``.
    reader_observations
        Per artifact, one mapping or a sequence of them:
        ``{source, verdict, clock_kind, observed_asof?, detail?}``.
    self_health
        Per artifact ``{source, status, detail?, source_artifact?}`` with ``status``
        already normalized to ok | degraded | missing | unknown. ``source_artifact`` names
        the artifact the evidence was DERIVED FROM; when its producer is the graded
        artifact's own producer the entry is REFUSED
        (:data:`REASON_SELF_MONITOR_NO_SELF_EVIDENCE`) — a monitor may not grade its own
        outputs, and deriving that mechanically beats a hand list of health artifacts.
    provider_events
        Per artifact, provider-waterfall rows. DIAGNOSTIC ONLY: a failed rung followed by
        a successful fallback describes the call, not the output, and never changes state.
    optional_upstream_overrides
        The RESOLVED view of the synapse ``health_optional_upstreams`` field — a whole
        replacement, not a patch: when it is passed, an artifact absent from it has no
        optional inputs regardless of what its own entry declares. Omit it (the default)
        to read the field off each artifact's entry.
    now
        Tz-aware; a naive datetime raises :class:`lib.dataos.temporal.TemporalError`.
    """
    observed_at = utc(now)
    index = _Index(synapse, registry)
    reader_map = reader_observations or {}
    self_map = self_health or {}
    provider_map = provider_events or {}
    override_map = optional_upstream_overrides

    records: dict[str, dict[str, Any]] = {}

    def resolve(artifact_id: str, stack: tuple[str, ...]) -> Any:
        # Memoized + cycle-safe. Inside a dependency cycle the entry point decides which
        # member reports the unassessable input, so the walk starts from the sorted id
        # list and never from an arbitrary order — same inputs, same output.
        if artifact_id in records:
            return records[artifact_id]
        if artifact_id in stack:
            return _CYCLE
        record = _build_record(
            artifact_id=artifact_id,
            index=index,
            observations=observations,
            reader_map=reader_map,
            self_map=self_map,
            provider_map=provider_map,
            override_map=override_map,
            now=observed_at,
            resolve=resolve,
            stack=stack + (artifact_id,),
        )
        records[artifact_id] = record
        return record

    for artifact_id in index.ids:
        resolve(artifact_id, ())

    outputs = [records[aid] for aid in index.ids]
    presence_sources = {
        str(observations.get(aid, {}).get("presence_source") or "")
        for aid in index.ids
    } - {""}
    return {
        "schema": SCHEMA,
        "generated": {
            "observed_at": observed_at.isoformat(),
            # DERIVED, never declared: which plane the presence probes actually read
            # from. A sparse worktree answers 'git_head' for the artifacts it omits, and
            # saying so is what keeps a sparse run from reading like a full one.
            "root_mode": (
                "unobserved"
                if not presence_sources
                else next(iter(presence_sources))
                if len(presence_sources) == 1
                else "mixed"
            ),
            "inputs": {
                "observations": len(observations),
                "optional_upstream_overrides": (
                    None if override_map is None else len(override_map)
                ),
                "provider_events": len(provider_map),
                "reader_observations": len(reader_map),
                "registry_engines": len(registry.get("engines") or []),
                "self_health": len(self_map),
                "synapse_artifacts": len(index.ids),
            },
        },
        "outputs": outputs,
        "summary": _summary(outputs),
    }


def _build_record(
    *,
    artifact_id: str,
    index: _Index,
    observations: Mapping[str, Mapping[str, Any]],
    reader_map: Mapping[str, Any],
    self_map: Mapping[str, Mapping[str, Any]],
    provider_map: Mapping[str, Sequence[Mapping[str, Any]]],
    override_map: Mapping[str, Sequence[str]] | None,
    now: datetime,
    resolve: Any,
    stack: tuple[str, ...],
) -> dict[str, Any]:
    entry = index.entries[artifact_id]
    obs = observations.get(artifact_id) or {}
    path = str(entry.get("path") or "")
    storage = str(entry.get("storage") or "")
    sla = _positive_int(entry.get("freshness_sla_hours"))

    reasons: list[str] = []
    evidence: list[dict[str, str]] = []
    blind: list[str] = []

    engine_id = index.engine_of.get(artifact_id)
    if engine_id is None:
        reasons.append(REASON_NOT_IN_ENGINE_REGISTRY)
        evidence.append(
            _evidence(
                "registry",
                "intelligence_registry",
                "artifact is registered in synapse but sits in no T1 engine cell — health "
                "is still computed; no cell is invented",
            )
        )

    # --- reader plane ---------------------------------------------------
    reader_rows = _reader_rows(reader_map.get(artifact_id))
    reader = _governing_reader(reader_rows)
    for row in reader_rows:
        source = str(row.get("source") or "reader")
        label = f"{row.get('verdict')} on the {row.get('clock_kind')} clock"
        if row is reader:
            if row.get("detail"):
                label += f" — {row['detail']}"
        else:
            label += f" (outranked by {reader.get('source') if reader else 'n/a'})"
        evidence.append(_evidence("reader", source, label))

    # --- presence -------------------------------------------------------
    # PRESENCE RESOLVES BEFORE FRESHNESS. A definitively absent output has no watermark to
    # read, so computing freshness first would turn `unavailable` into "could not look" on
    # the missing content — the exact conflation this module exists to prevent.
    placeholder = bool(_PLACEHOLDER_RE.search(path))
    reader_presence = _reader_presence(reader)
    exists = obs.get("exists")
    presence_decided_by = DECIDED_BY_AUDIT
    if reader_presence is False:
        exists = False
        presence_decided_by = DECIDED_BY_READER
    elif exists is None and reader_presence is True:
        # A reader that read the object proves presence. This is the ONLY presence
        # rescue — never a fabrication from silence.
        exists = True
        presence_decided_by = DECIDED_BY_READER
    if presence_decided_by == DECIDED_BY_READER:
        evidence.append(
            _evidence(
                "reader",
                str(reader.get("source") if reader else "reader"),
                f"presence resolved from the reader plane: exists={exists}",
            )
        )

    # --- freshness ------------------------------------------------------
    freshness_moot = exists is False
    if freshness_moot:
        fresh: dict[str, Any] = {
            "verdict": FRESH_VACUOUS,
            "decided_by": None,
            "reasons": [],
            "evidence": [],
            "age_hours": None,
            "source_asof": None,
            "field": None,
        }
        if reader is not None and reader.get("verdict") == "missing":
            reasons.append(REASON_READER_STALE_OVERRIDES_PRODUCER)
    else:
        fresh = _fold_reader(
            fresh=_producer_freshness(entry=entry, obs=obs, now=now), reader=reader
        )

    if placeholder:
        # A `<SYM>`-style path names a family, not a file. Nothing about it is probeable
        # as one artifact, so this short-circuits everything below it.
        blind.append(REASON_PLACEHOLDER_PATH)
    elif exists is None:
        if obs.get("sparse_unmaterialized"):
            blind.append(REASON_SPARSE_UNMATERIALIZED)
        elif storage == "gitignored-local":
            blind.append(REASON_RUNTIME_ONLY_UNOBSERVABLE)
        elif storage in ("r2", "git+r2"):
            blind.append(REASON_R2_UNOBSERVABLE)
        else:
            blind.append(REASON_PRESENCE_UNOBSERVABLE)
    elif obs.get("sparse_unmaterialized") and exists is not True:
        blind.append(REASON_SPARSE_UNMATERIALIZED)

    presence_source = obs.get("presence_source")
    if presence_source:
        evidence.append(
            _evidence("producer", "presence", f"exists={exists} via {presence_source}")
        )

    if not placeholder:
        reasons.extend(fresh["reasons"])
        evidence.extend(fresh["evidence"])
        if fresh["verdict"] == FRESH_BLIND:
            blind.extend(r for r in fresh["reasons"] if r in BLIND_REASONS)

    # --- semantic self health -------------------------------------------
    self_row = self_map.get(artifact_id)
    self_health_out: dict[str, Any] | None = None
    self_status: str | None = None
    if isinstance(self_row, Mapping):
        source_artifact = self_row.get("source_artifact")
        same_producer = (
            isinstance(source_artifact, str)
            and source_artifact in index.entries
            and index.producer_of.get(source_artifact)
            == index.producer_of.get(artifact_id)
        )
        if same_producer:
            reasons.append(REASON_SELF_MONITOR_NO_SELF_EVIDENCE)
            evidence.append(
                _evidence(
                    "self_health",
                    str(self_row.get("source") or "self_health"),
                    f"refused: {source_artifact} shares this artifact's producer — a "
                    f"monitor may not grade its own output",
                )
            )
        else:
            self_status = str(self_row.get("status") or "unknown")
            self_health_out = {
                "source": str(self_row.get("source") or "self_health"),
                "status": self_status,
            }
            if self_row.get("detail"):
                self_health_out["detail"] = str(self_row["detail"])
            evidence.append(
                _evidence(
                    "self_health",
                    self_health_out["source"],
                    f"{self_status}"
                    + (f" — {self_health_out['detail']}" if "detail" in self_health_out else ""),
                )
            )
            if self_status == "unknown":
                reasons.append(REASON_SELF_HEALTH_UNKNOWN)
            elif self_status == "missing":
                reasons.append(REASON_SELF_HEALTH_MISSING)

    # --- provider telemetry (diagnostic only) ----------------------------
    events = provider_map.get(artifact_id) or []
    if events:
        reasons.append(REASON_PROVIDER_RUNG_FAILURES)
        for event in sorted(
            (e for e in events if isinstance(e, Mapping)),
            key=lambda e: (str(e.get("rung") or ""), str(e.get("error_class") or "")),
        ):
            evidence.append(
                _evidence(
                    "provider",
                    str(event.get("rung") or "provider"),
                    f"{event.get('error_class') or 'attempt'} — DIAGNOSTIC ONLY: a failed "
                    f"rung with a successful fallback does not degrade the output",
                )
            )

    # --- dependencies -----------------------------------------------------
    if index.self_loop(artifact_id):
        reasons.append(REASON_SELF_INPUT_EXCLUDED)

    required_ids = index.required_inputs(artifact_id)
    declared_optional = (
        override_map.get(artifact_id)
        if override_map is not None
        else entry.get("health_optional_upstreams")
    )
    declared_optional = [str(x) for x in (declared_optional or [])]
    optional_problems = (
        _optional_violations(index, artifact_id, declared_optional)
        if declared_optional
        else []
    )
    optional_ids: list[str] = []
    if optional_problems:
        # A refused declaration is NOT silently downgraded to "no optional inputs": the
        # optional axis stays unresolved, which blocks healthy and names why.
        for problem in optional_problems:
            evidence.append(_evidence("dependency", "health_optional_upstreams", problem))
        for upstream in sorted(set(declared_optional)):
            reasons.append(f"{REASON_ILLEGAL_OPTIONAL_UPSTREAM}:{upstream}")
    else:
        optional_ids = sorted(set(declared_optional))
    # An input declared optional is not ALSO required — otherwise the declaration would
    # change nothing and the field would be decoration.
    optional_set = set(optional_ids)
    required_ids = [aid for aid in required_ids if aid not in optional_set]

    def input_rows(ids: Sequence[str]) -> tuple[list[dict[str, Any]], bool]:
        rows: list[dict[str, Any]] = []
        cycled = False
        for upstream in ids:
            resolved = resolve(upstream, stack)
            if resolved is _CYCLE:
                cycled = True
                rows.append(
                    {
                        "artifact_id": upstream,
                        "state": None,
                        "assessment_status": ASSESSMENT_COULD_NOT_LOOK,
                    }
                )
                continue
            rows.append(
                {
                    "artifact_id": upstream,
                    "state": resolved["state"],
                    "assessment_status": resolved["assessment_status"],
                }
            )
        return rows, cycled

    required_rows, required_cycled = input_rows(required_ids)
    optional_rows, optional_cycled = input_rows(optional_ids)
    if required_cycled or optional_cycled:
        reasons.append(REASON_DEPENDENCY_CYCLE)
        evidence.append(
            _evidence(
                "dependency",
                "synapse",
                "an input's resolution re-entered this artifact — the input is reported "
                "unassessable rather than recursed into",
            )
        )

    required_states = {row["state"] for row in required_rows}
    unassessed_required = sorted(
        row["artifact_id"] for row in required_rows if row["state"] is None
    )
    for upstream in unassessed_required:
        reasons.append(f"{REASON_REQUIRED_INPUT_UNASSESSED}:{upstream}")

    optional_negative: list[str] = []
    for row in optional_rows:
        if row["state"] == STATE_UNAVAILABLE:
            reasons.append(f"{REASON_OPTIONAL_INPUT_MISSING}:{row['artifact_id']}")
            optional_negative.append(row["artifact_id"])
        elif row["state"] == STATE_STALE:
            reasons.append(f"{REASON_OPTIONAL_INPUT_STALE}:{row['artifact_id']}")
            optional_negative.append(row["artifact_id"])
        elif row["state"] == STATE_DEGRADED:
            reasons.append(f"{REASON_OPTIONAL_INPUT_DEGRADED}:{row['artifact_id']}")
            optional_negative.append(row["artifact_id"])
        elif row["state"] is None:
            reasons.append(f"{REASON_OPTIONAL_INPUT_UNASSESSED}:{row['artifact_id']}")
            optional_negative.append(row["artifact_id"])

    # --- state precedence (§7) -------------------------------------------
    state: str | None = None
    decided_by: str | None = None
    assessment = ASSESSMENT_COMPLETE

    if blind:
        # OBSERVER BLINDNESS SHORT-CIRCUITS FIRST and is never converted: not to healthy
        # (we did not look), not to unavailable (absence was not observed).
        state, decided_by = None, None
        assessment = ASSESSMENT_COULD_NOT_LOOK
        reasons.extend(blind)
    else:
        if exists is False:
            state, decided_by = STATE_UNAVAILABLE, presence_decided_by
        elif STATE_UNAVAILABLE in required_states:
            state, decided_by = STATE_UNAVAILABLE, DECIDED_BY_DEPENDENCY
        elif fresh["verdict"] == FRESH_STALE:
            state, decided_by = STATE_STALE, fresh["decided_by"] or DECIDED_BY_CONTENT
        elif STATE_STALE in required_states:
            state, decided_by = STATE_STALE, DECIDED_BY_DEPENDENCY
        elif self_status in ("degraded", "missing"):
            # `missing` from a SEMANTIC monitor against an output our own probe just read
            # is a disagreement, not a deletion: our probe owns presence, so the monitor's
            # view lands as reduced completeness rather than as absence.
            state, decided_by = STATE_DEGRADED, DECIDED_BY_SELF_HEALTH
        elif STATE_DEGRADED in required_states:
            state, decided_by = STATE_DEGRADED, DECIDED_BY_DEPENDENCY
        elif optional_negative:
            state, decided_by = STATE_DEGRADED, DECIDED_BY_DEPENDENCY

        gaps = (
            fresh["verdict"] == FRESH_UNASSESSABLE
            or bool(unassessed_required)
            or bool(optional_problems)
            or self_status == "unknown"
        )
        if state is None:
            if gaps:
                assessment = ASSESSMENT_PARTIAL
            else:
                state, decided_by = STATE_HEALTHY, _healthy_decided_by(fresh)
        elif gaps:
            # A definitive negative still resolves state under a partial assessment (§7).
            assessment = ASSESSMENT_PARTIAL

    return {
        "engine_id": engine_id,
        "artifact_id": artifact_id,
        "output_class": index.output_class_of.get(artifact_id),
        "authority": index.authority_of.get(artifact_id, "unknown"),
        "path": path,
        "storage": storage,
        "state": state,
        "assessment_status": assessment,
        "decided_by": decided_by,
        "observed_at": now.isoformat(),
        "source_asof": fresh["source_asof"],
        "freshness_sla_hours": sla,
        "age_hours": fresh["age_hours"],
        "dependency_bound": index.dependency_bound(artifact_id),
        "required_inputs": sorted(required_rows, key=lambda r: r["artifact_id"]),
        "optional_inputs": sorted(optional_rows, key=lambda r: r["artifact_id"]),
        "reader_observation": _reader_record(reader),
        "self_health": self_health_out,
        "reason_codes": sorted(set(reasons)),
        "evidence": _sorted_evidence(evidence),
        "display_confidence_state": DISPLAY_CONFIDENCE[state],
    }


def _healthy_decided_by(fresh: Mapping[str, Any]) -> str:
    """Which plane earned a ``healthy``: the one that proved current-ness.

    A vacuous freshness axis leaves the presence probe as the deciding plane — the record
    still has to name one, and ``audit`` is the honest answer for "we opened it and the
    registry declares no freshness contract".
    """
    return fresh.get("decided_by") or DECIDED_BY_AUDIT


def _reader_record(reader: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if reader is None:
        return None
    out: dict[str, Any] = {
        "source": str(reader.get("source") or "reader"),
        "verdict": str(reader.get("verdict") or "indeterminate"),
    }
    if reader.get("detail"):
        out["detail"] = str(reader["detail"])
    if reader.get("observed_asof"):
        out["observed_asof"] = str(reader["observed_asof"])
    return out


def _summary(outputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts the record set already contains — never a second derivation of state."""
    def tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in outputs:
            value = row.get(key)
            # A null state is counted under "null" and never folded into a real state —
            # the count of what we could not determine is the headline number here.
            label = "null" if value is None else str(value)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items()))

    reason_hist: dict[str, int] = {}
    for row in outputs:
        for code in row.get("reason_codes") or []:
            base = reason_base(code)
            reason_hist[base] = reason_hist.get(base, 0) + 1

    return {
        "n_outputs": len(outputs),
        "by_state": tally("state"),
        "by_assessment_status": tally("assessment_status"),
        "by_dependency_bound": tally("dependency_bound"),
        "by_decided_by": tally("decided_by"),
        "reason_codes": dict(sorted(reason_hist.items())),
    }
