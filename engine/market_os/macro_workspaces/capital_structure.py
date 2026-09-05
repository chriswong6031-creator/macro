"""Pure composer for the US ``capital_structure`` workspace snapshot (F01 / R4).

Reads ONE owner-native artifact and projects it into a
``mastermind.macro_workspace_snapshot.v1`` body:

* ``data/capital_structure/projection.json`` (schema
  ``capital_structure.projection_bundle.v1`` / per-record schema
  ``capital_structure.projection.v1``, producer ``WS:CAPITAL-STRUCTURE-
  INTELLIGENCE-V2``) -- a nightly, issuer-scoped projection of SEC-filing
  CAPITAL-STRUCTURE EVENTS (shelf registrations, current reports, corporate
  actions, ...): a top-level ``coverage`` census (issuer/event/classification/
  review/edge counts, a ``freshness``/``generation_freshness`` pair with their
  OWN disclosed SLAs, a ``horizon_state``/``horizon_reason_codes`` discovery-
  lag disclosure, and a ``source_status``), a ``records`` array of ONE entry
  per issuer (identity, a per-issuer ``coverage`` census, a ``timeline`` of
  observed events, and the issuer's own ``latest_observed_event``), a
  ``source_receipt`` (artifact hashes and the underlying SEC form-policy
  ledger receipt), and -- critically -- an ``unavailable`` list disclosed at
  BOTH the whole-projection level and every individual record: ``[
  "active_instrument_overhang", "cash_runway", "financing_probability",
  "fully_diluted_shares", "instruments", "normalized_terms",
  "offering_ability", "remaining_capacity" ]``.

READ-ONLY PROJECTION LAW (why this composer never ranks or scores)
--------------------------------------------------------------------
This workspace projects the existing ``WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2``
owner; it creates no new truth, extracts no instrument terms, and ranks
nothing (the owner's OWN ``authority`` block already discloses
``is_context_only: true`` and every ``*_authority`` flag ``false`` -- this
composer's fixed contract authority block agrees with, never overrides, that
owner-native disclosure). The reference "Structure" section other financial
products ship is GLOBAL WEALTH COMPOSITION (equities/bonds/real assets by
sector), not corporate capital structure -- an unrelated concept sharing only
a word. Architecture section 10.3 is deliberately reference-absent for this
workspace: no reference layout is imitated here; only what section 10.3
itself specifies is implemented.

WHY THE HEADLINE IS ALWAYS COMPUTATION_REFUSED (read this before "fixing" it)
--------------------------------------------------------------------------------
Architecture 10.3 DOES define a two-axis headline blueprint:

    x-axis: refinancing pressure,                low -> high
    y-axis: balance-sheet resilience/market access, weak -> strong

-- unlike ``monetary_policy``/``liquidity_central_banks`` (10.7/10.9), which
define NO headline model at all and are therefore correctly ``NOT_APPLICABLE``.
Capital Structure is different: a blueprint exists, but the single owner
artifact this composer is scoped to read cannot honestly support it. Computing
"refinancing pressure" needs a maturity/refinancing wall and financing
capacity; computing "balance-sheet resilience/market access" needs cash
runway and instrument-level headroom. The owner artifact's own top-level AND
per-record ``unavailable`` lists name exactly those fields --
``active_instrument_overhang``, ``cash_runway``, ``financing_probability``,
``fully_diluted_shares``, ``instruments``, ``normalized_terms``,
``offering_ability``, ``remaining_capacity`` -- as not currently published,
at every issuer and in aggregate. Synthesizing a quadrant score from event/
filing CLASSIFICATION metadata alone (what this artifact actually carries)
would be a fabricated methodology dressed as a real one -- exactly what
section 7.7 ("Missing never becomes zero, neutral, unchanged...") and the
composer laws ("never invent methodology over data the owner itself
discloses it does not have") forbid. This mirrors ``business_activity.py``'s
own headline refusal precedent more closely than ``monetary_policy``'s: a
blueprint is named, but the currently available owner substrate cannot
support it, so ``headline.null_reason`` is the data-insufficiency member
``COMPUTATION_REFUSED``, not the model-absence member ``NOT_APPLICABLE``
(both are real vocabulary members, section 7.7, but they mean different
things and this composer does not conflate them). ``axes.items`` stays an
empty (schema-legal) array; ``drivers`` stays ``{"rate_side": [],
"balance_sheet": []}`` (schema-legal empty -- there is no axis to have
driving components in the first place; the ``rate_side``/``balance_sheet``
container names are inherited R1A liquidity-regime naming, never generalized
in the closed schema, and simply unused here rather than repurposed).

WHAT THIS COMPOSER ACTUALLY PUBLISHES INSTEAD
-------------------------------------------------
The real, owner-published, honestly-aggregable content:

* the owner's OWN top-level ``coverage`` census, propagated as-is (issuer/
  event/classification/deferred/review/edge counts, the ``freshness`` /
  ``generation_freshness`` pair with their own disclosed SLAs, and the
  ``horizon_state`` discovery-lag disclosure) -- never recomputed;
* TWO composer-derived ratios that are honest divisions of two owner-
  published counts (``classified_event_count / event_count`` and
  ``review_count / event_count``) -- no invented weighting, no threshold;
* a SINGLE pass over ``records`` (this module never loads the projection --
  ``build.py`` does -- and never iterates it more than once) computing plain
  per-issuer CENSUS counts of fields that genuinely exist on every record:
  how many issuers have a "classified" latest event, a pending review, a
  shelf-registration as their latest event family (architecture 10.3's
  "issuance and refinancing conditions" leg -- disclosed as a coarse census,
  never a scored issuance-conditions index), a non-empty relationships edge
  list, a non-null ``correction_of`` (architecture 10.3's "amendment/
  correction lineage" leg), or an owner-flagged event contradiction
  (``coverage.contradiction_ids``, this composer's ONLY contradiction
  signal -- entirely owner-native, never a composer-invented threshold);
* a TYPED ``NOT_COVERED`` metric for every entry in the owner's own
  top-level ``unavailable`` list, one metric per disclosed name (data-driven,
  not a hardcoded guess at the owner's vocabulary) -- the owner's typed
  degradation is surfaced, never masked, exactly matching architecture 10.3's
  named-but-unavailable required-composition legs (maturity/refinancing wall,
  coverage/leverage/covenant context).

SCOPE BOUNDARY (disclosed, not silently narrowed): this composer reads
EXACTLY ONE owner path, ``data/capital_structure/projection.json``. It never
opens ``data/regime/latest.json`` or any Financial-Conditions/Rates-owner
artifact, so architecture 10.3's "aggregate credit-spread and financing-cost
context" leg is NOT_COVERED here even though a HY-OAS/spread reading exists
elsewhere in this repository -- that context belongs to the Financial
Conditions / Monetary Policy workspaces, never duplicated into this one by
reaching outside the scoped owner input. "Issuer and sector drilldowns" and
"portfolio exposure join at request time" are both explicitly request-time UI
concerns, not snapshot aggregates: this composer NEVER republishes the
``records`` array itself (the composer law: aggregate, never republish the
record set), so no single-issuer metric appears here.

FRESHNESS LAW: the owner publishes on a nightly cadence (``coverage.
generation_freshness`` carries the owner's own ~30h SLA disclosure). This
composer's OWN freshness is a pure function of ``built_at`` vs the owner's
``generated_at`` -- CURRENT within a disclosed 36h nightly-cadence tolerance,
LATE_WITHIN_TOLERANCE within a further 12h grace, STALE_SOURCE beyond that
(see ``_NIGHTLY_CURRENT_HOURS`` / ``_NIGHTLY_GRACE_HOURS``) -- and can only
ever be DOWNGRADED (never upgraded) by the owner's own disclosed
``coverage.source_status`` reading something other than ``"ok"`` (the same
no-look-ahead law ``liquidity_central_banks.py`` uses for GLT leg receipts).
This is a DIFFERENT concept from the owner's own ``coverage.freshness`` /
``coverage.generation_freshness`` enums (event-detection-latency and
generation-compile-latency SLAs respectively) -- both are propagated as their
own separate categorical metrics, never conflated with this composer's
CURRENT/LATE_WITHIN_TOLERANCE/STALE_SOURCE freshness taxonomy.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library. The composer NEVER reads
a wall clock: ``built_at`` is passed in by the builder, and every staleness/
age check is a pure function of ``built_at`` and the owner artifact's own
clocks, so an identical owner input always yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "capital_structure.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.capital_structure"
OWNER_REF = "engine.capital_structure_event_projection"

# Nightly-cadence release-lag law (disclosed, not silently invented): a build
# within 36h of the owner's own generated_at is CURRENT; a further 12h grace
# window is LATE_WITHIN_TOLERANCE; beyond that, STALE_SOURCE. Mirrors the
# W-FRI weekly-grid pattern in liquidity_central_banks.py, scaled to this
# owner's nightly cadence instead of a weekly one.
_NIGHTLY_CURRENT_HOURS = 36.0
_NIGHTLY_GRACE_HOURS = 12.0

# Owner-disclosed enum readings this composer treats as "nothing to report" --
# anything else observed in these three owner fields is surfaced verbatim in
# ``availability.reasons`` as a genuine, disclosed diagnostic (never silently
# dropped). These sentinel sets are a composer judgment call, not an
# owner-published closed vocabulary: the owner discloses free-form strings
# here, and this composer conservatively treats only the obviously-nominal
# readings as benign.
_BENIGN_COVERAGE_STATES = frozenset({"complete", "full"})
_BENIGN_SOURCE_STATUSES = frozenset({"ok"})
_BENIGN_HORIZON_STATES = frozenset({"current", "nominal", "ok", "complete"})

_FRESH_SEVERITY = {
    "CURRENT": 0,
    "HISTORICAL_AS_KNOWN": 1,
    "LATE_WITHIN_TOLERANCE": 2,
    "SIMULATED": 3,
    "STALE_SOURCE": 4,
    "NOT_YET_RELEASED": 5,
    "RIGHTS_BLOCKED": 6,
    "NOT_COVERED": 7,
    "SOURCE_FAILED": 8,
}

# Metric ids tracked for "what changed" / corrections (architecture 7.8/6.3.7)
# in place of an axis x/y pair -- this workspace has no computed headline to
# diff (see module docstring).
_TRACKED_CHANGE_METRICS = (
    "cs_issuer_count", "cs_event_count", "cs_classified_event_count",
    "cs_deferred_event_count", "cs_review_count",
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, so this file can be added without touching any other
# module; the shape below intentionally mirrors monetary_policy.py /
# liquidity_central_banks.py)
# --------------------------------------------------------------------------- #
def _get(d: Any, *path: str) -> Any:
    cur = d
    for key in path:
        if isinstance(cur, Mapping) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _round(v: float | None, n: int = 6) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str | None, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _ratio(numer: float | None, denom: float | None) -> float | None:
    """Honest division of two owner-published counts; refused (never a
    fabricated 0) when the denominator is missing or zero."""
    if numer is None or denom is None or denom == 0:
        return None
    return _round(numer / denom, 6)


def _parse_dt(s: Any) -> _dt.datetime | None:
    if not isinstance(s, str) or not s:
        return None
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(txt)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _age_hours(built_at: Any, generated_at: Any) -> float | None:
    """Pure function of two GIVEN timestamp strings -- never a wall-clock
    read. ``built_at`` is always supplied by the caller (the builder), never
    sourced from ``datetime.now()`` inside this module."""
    b, g = _parse_dt(built_at), _parse_dt(generated_at)
    if b is None or g is None:
        return None
    return (b - g).total_seconds() / 3600.0


def _nightly_freshness(built_at: Any, generated_at: Any, value_present: bool,
                        *, owner_fresh: bool = True) -> str:
    """Nightly-cadence release-lag law (see module docstring). ``owner_fresh``
    carries the owner's OWN ``coverage.source_status`` read; it can only ever
    DOWNGRADE a would-be-CURRENT date-math result, never upgrade a genuinely
    stale/absent one (the same no-look-ahead law GLT leg receipts use)."""
    if not value_present:
        return "SOURCE_FAILED"
    age = _age_hours(built_at, generated_at)
    if age is None or age < 0:
        return "SOURCE_FAILED"
    if age <= _NIGHTLY_CURRENT_HOURS:
        tier = "CURRENT"
    elif age <= _NIGHTLY_CURRENT_HOURS + _NIGHTLY_GRACE_HOURS:
        tier = "LATE_WITHIN_TOLERANCE"
    else:
        tier = "STALE_SOURCE"
    if not owner_fresh and tier == "CURRENT":
        return "STALE_SOURCE"
    return tier


def _metric(metric_id, value, value_type, unit, basis, direction, owner_field,
            reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            calculation_as_of=None, owner_ref=OWNER_REF) -> dict:
    return {
        "metric_id": metric_id,
        "reference_id": f"mastermind.market_reference/v1#{metric_id}",
        "definition_id": owner_field,
        "definition_version": DEFINITION_VERSION,
        "owner_ref": owner_ref,
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "basis": basis,
        "direction_semantics": direction,
        "reference_period": reference_period,
        "observed_at": reference_period,
        "released_at": None,
        "available_at": None,
        "collected_at": None,
        "revised_at": None,
        "calculation_as_of": calculation_as_of if calculation_as_of is not None else reference_period,
        "market_session": None,
        "source_refs": source_refs or ["data/capital_structure/projection.json"],
        "source_digest": None,
        "transformation": transformation,
        "model_version": METHOD_VERSION,
        "uncertainty": {"kind": None, "value": None},
        "coverage": None,
        "freshness": freshness,
        "rights_state": "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metric_value(snapshot: Mapping | None, metric_id: str) -> Any:
    for m in (_get(snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


# --------------------------------------------------------------------------- #
# one single pass over ``records`` (never iterated more than once)
# --------------------------------------------------------------------------- #
def _aggregate_records(records: list) -> dict:
    classified = 0
    pending_review = 0
    shelf = 0
    with_relationships = 0
    correction_present = 0
    contradiction_flagged = 0
    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        latest = _get(rec, "latest_observed_event")
        latest = latest if isinstance(latest, Mapping) else {}
        if latest.get("classification_state") == "classified":
            classified += 1
        review = _get(latest, "review")
        review = review if isinstance(review, Mapping) else {}
        if review.get("state") == "pending":
            pending_review += 1
        if latest.get("family") == "shelf":
            shelf += 1
        relationships = latest.get("relationships")
        if isinstance(relationships, list) and len(relationships) > 0:
            with_relationships += 1
        if latest.get("correction_of") is not None:
            correction_present += 1
        rec_coverage = _get(rec, "coverage")
        rec_coverage = rec_coverage if isinstance(rec_coverage, Mapping) else {}
        contradiction_ids = rec_coverage.get("contradiction_ids")
        if isinstance(contradiction_ids, list) and len(contradiction_ids) > 0:
            contradiction_flagged += 1
    return {
        "n_records": len(records),
        "classified": classified,
        "pending_review": pending_review,
        "shelf": shelf,
        "with_relationships": with_relationships,
        "correction_present": correction_present,
        "contradiction_flagged": contradiction_flagged,
    }


def _detect_contradiction(agg: dict) -> dict | None:
    """The composer's ONLY contradiction signal: the owner's OWN per-record
    ``coverage.contradiction_ids`` (never a composer-invented threshold)."""
    n = agg["contradiction_flagged"]
    if not n:
        return None
    return {
        "kind": "issuer_event_contradiction",
        "en": (f"{n} issuer record(s) carry an owner-flagged event contradiction "
               "(coverage.contradiction_ids is non-empty) -- two or more observed "
               "events for that issuer conflict in the owner's own classification "
               "pipeline. This composer never resolves the conflict; it surfaces "
               "the owner's own flag unchanged."),
        "zh": (f"{n} 个发行人记录带有所有者自身标记的事件矛盾"
               "（coverage.contradiction_ids 非空）——该发行人的两个或以上观测事件"
               "在所有者自身的分类流程中相互冲突。本组合器不会解决该冲突，"
               "只原样呈现所有者自身的标记。"),
        "components": ["cs_issuer_contradiction_flagged_count"],
    }


# --------------------------------------------------------------------------- #
# required availability
# --------------------------------------------------------------------------- #
def _required_availability(fresh: str, coverage_ok: bool, records_ok: bool,
                            as_of: Any) -> list[dict]:
    specs = [
        ("event_coverage_census", coverage_ok,
         "Event & issuer coverage census", "事件与发行人覆盖普查"),
        ("issuer_records", records_ok,
         "Issuer capital-structure event records", "发行人资本结构事件记录"),
    ]
    rows = []
    for cid, present, en, zh in specs:
        this_fresh = fresh if present else "SOURCE_FAILED"
        status = "PRESENT" if present and this_fresh == "CURRENT" else ("PARTIAL" if present else "ABSENT")
        null_reason = None if present else "SOURCE_FAILED"
        rows.append({
            "component_id": cid, "label": _bil(en, zh), "required": True,
            "freshness": this_fresh, "status": status,
            "source_asof": as_of if present else None,
            "null_reason": null_reason,
        })
    return rows


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(as_of, coverage: Mapping, coverage_ok: bool, records_ok: bool,
             agg: dict, unavailable: list, fresh: str,
             contradiction: dict | None) -> list[dict]:
    items: list[dict] = []
    contradiction_hit = contradiction is not None

    def _cov_num(field, *, as_int: bool):
        raw = _num(coverage.get(field)) if coverage_ok else None
        val = int(raw) if (raw is not None and as_int) else raw
        status = "PRESENT" if val is not None else "ABSENT"
        null_reason = None if val is not None else ("UNKNOWN" if coverage_ok else "SOURCE_FAILED")
        return val, status, null_reason

    # -- owner top-level coverage census (pass-through, no computation) ------ #
    for field, mid, unit, direction in (
        ("issuer_count", "cs_issuer_count", "issuers", "n/a"),
        ("event_count", "cs_event_count", "events", "n/a"),
        ("classified_event_count", "cs_classified_event_count", "events", "n/a"),
        ("deferred_event_count", "cs_deferred_event_count", "events", "n/a"),
        ("review_count", "cs_review_count", "events", "n/a"),
        ("edge_count", "cs_edge_count", "edges", "n/a"),
        ("generation_age_hours", "cs_owner_generation_age_hours", "hours", "n/a"),
    ):
        is_count = field != "generation_age_hours"
        val, status, null_reason = _cov_num(field, as_int=is_count)
        items.append(_metric(
            mid, val, "count" if is_count else "number", unit,
            "owner_native_census", direction, f"coverage.{field}", as_of, fresh,
            status=status, null_reason=null_reason,
        ))

    for field, mid in (
        ("state", "cs_coverage_state"),
        ("freshness", "cs_event_detection_freshness_state"),
        ("generation_freshness", "cs_generation_freshness_state"),
        ("source_status", "cs_source_status"),
        ("horizon_state", "cs_horizon_state"),
    ):
        val = coverage.get(field) if coverage_ok else None
        status = "PRESENT" if val is not None else "ABSENT"
        null_reason = None if val is not None else ("UNKNOWN" if coverage_ok else "SOURCE_FAILED")
        items.append(_metric(
            mid, val, "categorical", None, "owner_native_categorical", None,
            f"coverage.{field}", as_of, fresh, status=status, null_reason=null_reason,
            transformation=(
                "owner-native enum member, a DIFFERENT vocabulary from this "
                "snapshot's own freshness taxonomy -- never conflated with it"
            ) if mid in ("cs_event_detection_freshness_state", "cs_generation_freshness_state") else None,
        ))

    # -- composer-derived ratios: honest division of two owner counts ------- #
    event_count = _num(coverage.get("event_count")) if coverage_ok else None
    classified_count = _num(coverage.get("classified_event_count")) if coverage_ok else None
    review_count = _num(coverage.get("review_count")) if coverage_ok else None
    class_rate = _ratio(classified_count, event_count)
    review_ratio = _ratio(review_count, event_count)
    items.append(_metric(
        "cs_event_classification_rate", class_rate, "ratio", "ratio_0_1",
        "classified_over_total_events", "higher_more_classified",
        "coverage.classified_event_count / coverage.event_count", as_of, fresh,
        transformation="classified_event_count divided by event_count; refused (never 0) when event_count is missing or zero",
        null_reason=None if class_rate is not None else "COMPUTATION_REFUSED",
    ))
    items.append(_metric(
        "cs_review_backlog_ratio", review_ratio, "ratio", "ratio_0_1",
        "pending_review_over_total_events", "higher_more_backlog",
        "coverage.review_count / coverage.event_count", as_of, fresh,
        transformation="review_count divided by event_count; refused (never 0) when event_count is missing or zero",
        null_reason=None if review_ratio is not None else "COMPUTATION_REFUSED",
    ))

    # -- single-pass record census (see _aggregate_records) ------------------ #
    def _rec_count(mid, value, unit, direction, owner_field, note):
        status = "PRESENT" if records_ok else "ABSENT"
        null_reason = None if records_ok else "SOURCE_FAILED"
        return _metric(
            mid, value if records_ok else None, "count", unit, "owner_native_census",
            direction, owner_field, as_of, fresh if records_ok else "SOURCE_FAILED",
            status=status, null_reason=null_reason, transformation=note,
        )

    items.append(_rec_count(
        "cs_issuer_records_count", agg["n_records"], "issuers", "n/a",
        "records[*]", "count of issuer records actually present in this projection"))
    items.append(_rec_count(
        "cs_issuer_latest_event_classified_count", agg["classified"], "issuers", "n/a",
        "records[*].latest_observed_event.classification_state",
        "count of issuers whose latest observed event reached the owner's classified terminal state"))
    share = _ratio(_num(agg["classified"]), _num(agg["n_records"]))
    items.append(_metric(
        "cs_issuer_latest_event_classified_share", share, "ratio", "ratio_0_1",
        "classified_over_total_issuer_records", "higher_more_classified",
        "records[*].latest_observed_event.classification_state", as_of,
        fresh if records_ok else "SOURCE_FAILED",
        status="PRESENT" if records_ok else "ABSENT",
        null_reason=(None if share is not None else "COMPUTATION_REFUSED") if records_ok else "SOURCE_FAILED",
        transformation="classified issuer-record count divided by total issuer-record count; refused when there are zero records",
    ))
    items.append(_rec_count(
        "cs_issuer_pending_review_count", agg["pending_review"], "issuers", "n/a",
        "records[*].latest_observed_event.review.state",
        "count of issuers whose latest observed event is currently in the owner's pending review queue"))
    items.append(_rec_count(
        "cs_issuer_shelf_registration_count", agg["shelf"], "issuers", "n/a",
        "records[*].latest_observed_event.family",
        "count of issuers whose latest observed event family is a shelf registration -- a coarse market-access census, never a scored issuance-conditions index"))
    shelf_share = _ratio(_num(agg["shelf"]), _num(agg["n_records"]))
    items.append(_metric(
        "cs_issuer_shelf_registration_share", shelf_share, "ratio", "ratio_0_1",
        "shelf_over_total_issuer_records", "higher_more_shelf_activity",
        "records[*].latest_observed_event.family", as_of,
        fresh if records_ok else "SOURCE_FAILED",
        status="PRESENT" if records_ok else "ABSENT",
        null_reason=(None if shelf_share is not None else "COMPUTATION_REFUSED") if records_ok else "SOURCE_FAILED",
        transformation="shelf-registration issuer-record count divided by total issuer-record count; refused when there are zero records",
    ))
    items.append(_rec_count(
        "cs_issuer_with_relationships_count", agg["with_relationships"], "issuers", "n/a",
        "records[*].latest_observed_event.relationships",
        "count of issuers whose latest observed event carries a non-empty owner-native relationships edge list"))
    items.append(_rec_count(
        "cs_issuer_correction_present_count", agg["correction_present"], "issuers", "n/a",
        "records[*].latest_observed_event.correction_of",
        "count of issuers whose latest observed event is itself a correction of a prior event (architecture 10.3 amendment/correction lineage leg)"))
    contradiction_val = agg["contradiction_flagged"]
    contradiction_status = "DISAGREEMENT" if (contradiction_hit and records_ok) else ("PRESENT" if records_ok else "ABSENT")
    items.append(_metric(
        "cs_issuer_contradiction_flagged_count",
        contradiction_val if records_ok else None, "count", "issuers", "owner_native_census",
        "n/a", "records[*].coverage.contradiction_ids", as_of,
        fresh if records_ok else "SOURCE_FAILED",
        status=contradiction_status,
        null_reason=("DISAGREEMENT" if (contradiction_hit and records_ok) else None) if records_ok else "SOURCE_FAILED",
        transformation="count of issuer records whose own coverage.contradiction_ids is non-empty (owner-native, never a composer-invented threshold)",
    ))

    # -- typed NOT_COVERED for every owner-disclosed unavailable capacity ---- #
    for name in unavailable:
        if not isinstance(name, str) or not name:
            continue
        mid = f"cs_{name}"
        items.append(_metric(
            mid, None, "number", None, "owner_disclosed_unavailable", "n/a",
            f"unavailable[]:{name}", as_of, "NOT_COVERED",
            status="ABSENT", null_reason="NOT_COVERED",
            transformation=(
                f"the owner-native projection explicitly discloses '{name}' as not "
                "currently published, at both the whole-projection level and every "
                "individual issuer record; this composer never estimates a value in "
                "its place"
            ),
        ))

    return items


# --------------------------------------------------------------------------- #
# headline (always COMPUTATION_REFUSED -- see module docstring)
# --------------------------------------------------------------------------- #
def _headline(as_of, prior_snapshot) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil(
            "Refinancing pressure x balance-sheet resilience/market access",
            "再融资压力 × 资产负债表韧性/市场准入"),
        "method_version": METHOD_VERSION,
        "effective_date": as_of,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {"state_id": None, "effective_date": prior_eff, "method_version": prior_method},
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "COMPUTATION_REFUSED"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": ("architecture section 10.3 names a refinancing-pressure x balance-sheet-"
                     "resilience/market-access quadrant, but the scoped owner artifact for this "
                     "composer (data/capital_structure/projection.json) is an event/filing "
                     "classification projection only -- it explicitly types the instrument-level "
                     "substance both axes would need (maturity/refinancing terms, cash runway, "
                     "financing capacity) as not currently published, at both the whole-"
                     "projection level and every individual issuer record. No quadrant score is "
                     "estimated from event-classification metadata alone; the real, honestly-"
                     "aggregable coverage and event census is published under metrics instead."),
        },
        "status": "ABSENT",
        "null_reason": "COMPUTATION_REFUSED",
    }


# --------------------------------------------------------------------------- #
# changes / corrections
# --------------------------------------------------------------------------- #
def _changes(metrics_by_id: dict, prior_snapshot: Mapping | None) -> dict:
    if prior_snapshot is None:
        return {"comparability": "NO_PRIOR", "prior_generation_id": None,
                "prior_effective_date": None, "prior_method_version": None,
                "deltas": [], "status": "ABSENT", "null_reason": "WARMUP"}
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_method != METHOD_VERSION:
        return {"comparability": "METHOD_CHANGED", "prior_generation_id": prior_gen,
                "prior_effective_date": prior_eff, "prior_method_version": prior_method,
                "deltas": [], "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"}
    deltas = []
    for mid in _TRACKED_CHANGE_METRICS:
        cur = metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        delta = None
        if isinstance(cur, (int, float)) and not isinstance(cur, bool) and \
           isinstance(prev, (int, float)) and not isinstance(prev, bool):
            delta = _round(cur - prev, 4)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _corrections(metrics_by_id: dict, effective_date, prior_snapshot: Mapping | None) -> dict:
    """Scoped supersession detection over the tracked metric subset (mirrors
    the liquidity_central_banks/monetary_policy pattern; see
    liquidity_regime._corrections for the full caveat about this being a
    scoped subset, not a persisted vintage ledger)."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {
            "predecessor_generation_id": None,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists.",
        }
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_eff != effective_date:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted.",
        }
    changed: list[str] = []
    for mid in _TRACKED_CHANGE_METRICS:
        cur = metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        if cur != prev:
            digest16 = sha256(f"{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
            changed.append(f"{mid}:{mid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native metrics changed value: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen,
        "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no tracked metric changed value (no-change republication).",
    }


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- R4 non-goal: execution)
# --------------------------------------------------------------------------- #
def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "review_backlog_ratio", "label": _bil("Review backlog ratio", "审查积压比率"),
             "unit": "ratio", "step": 0.05, "min": 0.0, "max": 1.0,
             "owner_field": "coverage.review_count"},
            {"assumption_id": "classification_rate", "label": _bil("Event classification rate", "事件分类完成率"),
             "unit": "ratio", "step": 0.05, "min": 0.0, "max": 1.0,
             "owner_field": "coverage.classified_event_count"},
            {"assumption_id": "maturity_wall_horizon_months", "label": _bil("Maturity-wall horizon", "到期墙期限"),
             "unit": "months", "step": 1.0, "min": 0.0, "max": 120.0, "owner_field": None},
            {"assumption_id": "refinancing_capacity_pct", "label": _bil("Refinancing capacity", "再融资能力"),
             "unit": "pct", "step": 5.0, "min": 0.0, "max": 100.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": ("Assumption vocabulary is declared and closed; this composer ships no scenario execution "
                 "endpoint (non-goal). maturity_wall_horizon_months / refinancing_capacity_pct have no "
                 "owner_field because the scoped owner projection discloses instrument-level terms as "
                 "unavailable (see the module docstring); a future owner-native pure scenario function "
                 "produces mastermind.macro_workspace_scenario_result.v1 with no canonical write."),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "new_capital_structure_event", "kind": "component_shock",
             "label": _bil("New capital-structure event observed", "新增资本结构事件"), "params": ["issuer_id", "family"]},
            {"condition_id": "review_backlog_shock", "kind": "component_shock",
             "label": _bil("Review backlog shock", "审查积压冲击"), "params": ["review_backlog_ratio"]},
            {"condition_id": "issuer_contradiction_flagged", "kind": "contradiction_change",
             "label": _bil("Issuer event contradiction flagged", "发行人事件矛盾标记"), "params": ["issuer_id"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
        ],
        "status": "ABSENT",
        "note": ("Eligible condition types are declared; this composer writes no alert (non-goal). Alerts "
                 "extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once "
                 "the service can create/list/evaluate/delete these real conditions."),
    }


def _sources(as_of, generated_at, fresh, source_receipt: Mapping) -> list[dict]:
    def _src(source_id, en, zh, provider, ref_period, artifact_ref, freshness_val,
             definition_version=None):
        return {
            "source_id": source_id,
            "label": _bil(en, zh),
            "owner_ref": OWNER_REF,
            "provider": provider,
            "reference_period": ref_period,
            "released_at": None,
            "first_known_at": None,
            "collected_at": generated_at,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": None,
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": definition_version,
            "artifact_ref": artifact_ref,
            "freshness": freshness_val,
        }

    items = [
        _src("capital_structure_event_projection",
             "Capital-structure event & filing classification projection", "资本结构事件与文件分类投影",
             "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2 (SEC EDGAR filing events)", as_of,
             "data/capital_structure/projection.json", fresh),
    ]
    ledger = _get(source_receipt, "source_ledger_receipt")
    if isinstance(ledger, Mapping) and (ledger.get("record_count") is not None
                                         or ledger.get("form_policy_version") is not None):
        items.append(_src(
            "capital_structure_source_ledger",
            "Underlying SEC form-policy source ledger receipt", "底层SEC表格政策数据源清单回执",
            "SEC EDGAR (via capital-structure source ledger)", as_of,
            "data/capital_structure/projection.json#source_receipt.source_ledger_receipt", fresh,
            definition_version=ledger.get("form_policy_version"),
        ))
    return items


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(coverage: Mapping, coverage_ok: bool, unavailable: list, agg: dict,
                   records_ok: bool, contradiction: dict | None, worst_freshness: str,
                   coverage_ratio: float, owner_authority: Mapping) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH",
        "evidence_breadth": "LOW",
        "contradiction_state": "PRESENT" if contradiction else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "No refinancing-pressure x balance-sheet-resilience/market-access state is asserted: the scoped "
            "owner projection publishes capital-structure EVENT and FILING classification metadata only, and "
            "explicitly discloses the instrument-level terms both axes would need (maturity/refinancing "
            "capacity, cash runway) as not currently published. Rather than estimate a fabricated score, the "
            "real event and issuer census is published as metrics instead.",
            "未给出再融资压力 × 资产负债表韧性/市场准入状态：所设定的所有者投影仅发布资本结构事件与文件"
            "分类元数据，并明确披露两轴所需的工具层面条款（到期/再融资能力、现金续航）目前尚未发布。"
            "为避免虚构评分，改以指标形式发布真实的事件与发行人普查数据。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["financing", "credit_markets"],
        "contradictions": [contradiction["kind"]] if contradiction else [],
        "trace_ref": "data/capital_structure/projection.json#coverage",
    }]

    if coverage_ok:
        issuer_count = coverage.get("issuer_count")
        event_count = coverage.get("event_count")
        classified = coverage.get("classified_event_count")
        deferred = coverage.get("deferred_event_count")
        items.append({
            "implication_id": "event_census_read",
            "text": _bil(
                f"The owner-published projection covers {issuer_count} issuers and {event_count} "
                f"capital-structure events this cycle ({classified} classified, {deferred} deferred pending "
                "further review) -- a filing-classification census, not a risk score.",
                f"所有者发布的投影本周期覆盖 {issuer_count} 个发行人和 {event_count} 项资本结构事件"
                f"（已分类 {classified} 项，延期待进一步审查 {deferred} 项）——这是文件分类普查，并非风险评分。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [],
            "trace_ref": "data/capital_structure/projection.json#coverage",
        })

    if records_ok and agg["n_records"] > 0:
        items.append({
            "implication_id": "issuer_census_read",
            "text": _bil(
                f"Across {agg['n_records']} issuer records read this cycle: {agg['classified']} have a "
                f"classified latest event, {agg['pending_review']} sit in the owner's pending review queue, "
                f"and {agg['shelf']} carry a shelf-registration filing as their most recent observed event "
                "(a coarse market-access census, not a scored issuance-conditions index).",
                f"本周期读取的 {agg['n_records']} 个发行人记录中：{agg['classified']} 个的最新事件已完成分类，"
                f"{agg['pending_review']} 个仍处于所有者的待审查队列中，{agg['shelf']} 个的最新观测事件为"
                "货架注册文件（这是粗粒度的市场准入普查，并非评分化的发行条件指数）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing", "issuance"], "contradictions": [],
            "trace_ref": "data/capital_structure/projection.json#records",
        })

    if coverage_ok and coverage.get("horizon_state") not in _BENIGN_HORIZON_STATES and coverage.get("horizon_state") is not None:
        codes = coverage.get("horizon_reason_codes") or []
        items.append({
            "implication_id": "owner_horizon_state_degraded",
            "text": _bil(
                f"The owner itself marks this cycle's discovery horizon as '{coverage.get('horizon_state')}' "
                f"({'; '.join(str(c) for c in codes) if codes else 'no reason codes disclosed'}). This "
                "composer passes that read through unchanged rather than smoothing it over.",
                f"所有者自身将本周期的发现视野标记为“{coverage.get('horizon_state')}”"
                f"（{'；'.join(str(c) for c in codes) if codes else '未披露原因代码'}）。"
                "本组合器原样传递该判断，不做平滑处理。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [], "trace_ref": "data/capital_structure/projection.json#coverage",
        })

    if contradiction:
        items.append({
            "implication_id": f"contradiction_{contradiction['kind']}",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [contradiction["kind"]],
            "trace_ref": "data/capital_structure/projection.json#records[*].coverage.contradiction_ids",
        })

    if unavailable:
        listed = ", ".join(str(u) for u in unavailable)
        items.append({
            "implication_id": "unavailable_capacities_disclosure",
            "text": _bil(
                f"The owner projection explicitly discloses the following capacities as not currently "
                f"published, at both the whole-projection level and every issuer record: {listed}. Each is "
                "typed rather than silently omitted or estimated -- see the corresponding metric for each name.",
                f"所有者投影明确披露以下能力目前尚未发布，且在整体投影层面与每条发行人记录层面均如此："
                f"{listed}。每一项均以类型化方式呈现，而非被静默省略或臆造——具体见各自对应的指标。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [], "trace_ref": "data/capital_structure/projection.json#unavailable",
        })

    items.append({
        "implication_id": "scope_boundary_disclosure",
        "text": _bil(
            "This workspace reads exactly one owner path, the capital-structure event projection. Aggregate "
            "credit-spread and financing-cost context (named in architecture section 10.3) is not composed "
            "here even though a comparable reading exists elsewhere in this repository -- that context "
            "belongs to the Financial Conditions and Monetary Policy workspaces and is never duplicated into "
            "this one by reaching outside the scoped owner input. Issuer-level drilldowns and a portfolio "
            "exposure join are both request-time concerns; this composer never republishes the underlying "
            "records array itself.",
            "本工作区仅读取一个所有者数据路径，即资本结构事件投影。架构第10.3节提及的综合信用利差与融资"
            "成本背景本处不予汇编，即便本仓库其他位置存在可比读数——该背景属于金融条件与货币政策工作区，"
            "不会通过越界读取所有者输入而在此重复呈现。发行人层面的下钻与投资组合敞口关联均为请求时概念；"
            "本组合器绝不会原样重新发布底层记录数组本身。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["financing"], "contradictions": [], "trace_ref": "engine.market_os.macro_workspaces.capital_structure#scope",
    })

    if isinstance(owner_authority, Mapping) and owner_authority and any(
        owner_authority.get(k) is True for k in
        ("entry_authority", "prophet_authority", "rank_authority", "sizing_authority")
    ):
        items.append({
            "implication_id": "owner_authority_claim_exceeds_composer_ceiling",
            "text": _bil(
                "The owner artifact's own authority block claims a real (non-context-only) authority flag "
                "this cycle. This snapshot's published authority block is fixed by the shared contract to "
                "context_only regardless -- the owner's claim is disclosed here, never used to widen this "
                "snapshot's own descriptive ceiling.",
                "所有者制品自身的权限区块本周期声明了一项真实（非仅限上下文）的权限标记。"
                "本快照发布的权限区块由共享合约固定为仅限上下文，与此无关——所有者的声明仅在此披露，"
                "绝不会用于扩大本快照自身的描述性上限。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [], "trace_ref": "data/capital_structure/projection.json#authority",
        })
    elif isinstance(owner_authority, Mapping) and owner_authority:
        items.append({
            "implication_id": "owner_authority_disclosure_agrees",
            "text": _bil(
                "The owner artifact's own authority block agrees with this snapshot's fixed contract "
                "authority: context-only, no rank/entry/sizing/prophet authority.",
                "所有者制品自身的权限区块与本快照固定的合约权限一致：仅限上下文，不含排名/入场/仓位/"
                "预言权限。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [], "trace_ref": "data/capital_structure/projection.json#authority",
        })
    # owner_authority missing/empty entirely: no authority-disclosure implication
    # is fabricated (there is nothing owner-native to agree or disagree with).

    return items


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(projection: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``projection`` (``capital_structure.projection_bundle.v1``)
    into an UNSEALED snapshot body. The builder seals it via
    ``contract.finalize``. Iterates ``projection['records']`` exactly ONCE
    (``_aggregate_records``); never republishes the record set itself."""
    p = projection or {}

    as_of = p.get("as_of")
    generated_at = p.get("generated_at")

    coverage = _get(p, "coverage")
    coverage_ok = isinstance(coverage, Mapping)
    coverage = coverage if coverage_ok else {}

    records_raw = p.get("records")
    records_ok = isinstance(records_raw, list)
    records = records_raw if records_ok else []

    unavailable_raw = p.get("unavailable")
    unavailable = unavailable_raw if isinstance(unavailable_raw, list) else []

    source_receipt = _get(p, "source_receipt")
    source_receipt = source_receipt if isinstance(source_receipt, Mapping) else {}

    owner_authority = _get(p, "authority")
    owner_authority = owner_authority if isinstance(owner_authority, Mapping) else {}

    # ``owner_fresh`` only ever DOWNGRADES a would-be-CURRENT date-math result
    # (see ``_nightly_freshness``). When ``coverage`` itself is entirely
    # missing there is no owner health signal to read at all -- that absence
    # is already correctly captured by ``event_coverage_census`` reading
    # ABSENT via its own presence check below, so this defaults to True
    # (neutral) rather than forcing a redundant downgrade that would also
    # wrongly penalize the otherwise-independent ``issuer_records`` component
    # (which has its own clock-independent presence check and does not read
    # ``coverage`` at all).
    owner_source_status = coverage.get("source_status") if coverage_ok else None
    owner_fresh = (owner_source_status in _BENIGN_SOURCE_STATUSES) if coverage_ok else True
    fresh = _nightly_freshness(built_at, generated_at, generated_at is not None, owner_fresh=owner_fresh)

    agg = _aggregate_records(records)
    contradiction = _detect_contradiction(agg) if records_ok else None

    metrics = _metrics(as_of, coverage, coverage_ok, records_ok, agg, unavailable, fresh, contradiction)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail = _required_availability(fresh, coverage_ok, records_ok, as_of)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]

    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if coverage_ok:
        state_val = coverage.get("state")
        if state_val is not None and state_val not in _BENIGN_COVERAGE_STATES:
            reasons.append(f"owner_coverage_state={state_val}")
        if owner_source_status is not None and owner_source_status not in _BENIGN_SOURCE_STATUSES:
            reasons.append(f"owner_source_status={owner_source_status}")
        horizon_val = coverage.get("horizon_state")
        if horizon_val is not None and horizon_val not in _BENIGN_HORIZON_STATES:
            reasons.append(f"owner_horizon_state={horizon_val}")
    if contradiction:
        reasons.append(f"contradiction={contradiction['kind']}")

    headline = _headline(as_of, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "capital_structure",
            "title": _bil("Capital Structure", "资本结构"),
            "subtitle": _bil("Refinancing pressure x balance-sheet resilience/market access",
                              "再融资压力 × 资产负债表韧性/市场准入"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": generated_at or as_of,
            "content_sha256": "0" * 64,
        },
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False,
            "can_execute": False, "axis_authority_ceiling": "DESCRIPTIVE",
        },
        "availability": {
            "state": worst,
            "required": required_avail,
            "degraded": degraded,
            "coverage_ratio": coverage_ratio,
            "worst_freshness": worst,
            "contradiction": {
                "present": contradiction is not None,
                "kind": contradiction["kind"] if contradiction else None,
                "en": contradiction["en"] if contradiction else None,
                "zh": contradiction["zh"] if contradiction else None,
                "components": contradiction["components"] if contradiction else [],
            },
            "reasons": reasons,
        },
        "headline": headline,
        "axes": {"items": []},
        "metrics": {"items": metrics},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": {"rate_side": [], "balance_sheet": []},
        "changes": changes,
        "implications": {"items": _implications(
            coverage, coverage_ok, unavailable, agg, records_ok, contradiction,
            worst, coverage_ratio, owner_authority)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(as_of, generated_at, fresh, source_receipt)},
        "corrections": _corrections(metrics_by_id, as_of, prior_snapshot),
        "learning": {
            "instrumentation": "first_party",
            "event_names": [
                "macro_workspace_opened", "macro_state_changed_seen",
                "macro_driver_expanded", "macro_source_opened",
                "macro_degraded_state_seen", "macro_unknown_or_refusal_seen",
            ],
            "privacy_note": "Event definitions reuse the existing first-party analytics owner; no second analytics store, no user identity copied into the artifact.",
        },
    }
    return snapshot
