"""Pure composer for the US ``housing_real_estate`` workspace snapshot (F01 / R5).

Reads FIVE raw, ALREADY-LOADED level series -- four FRED parquet series plus one
Zillow series -- and projects them into a ``mastermind.macro_workspace_snapshot.v1``
body:

* ``fred_frames`` -- a dict ``{series_id: rows_or_None}`` where ``rows`` is a plain
  Python list of ``(date, value)`` pairs (or longer tuples -- extra elements are
  ignored, see the digest tests' unconsumed-field negative control) read from
  ``data/fred/<series_id>.parquet``. Exactly four series are consumed:
  ``MORTGAGE30US`` (Freddie Mac PMMS 30y fixed mortgage rate, weekly, column
  ``mortgage_30y``), ``HOUST`` (Census housing starts SAAR, monthly, column
  ``housing_starts``), ``PERMIT`` (Census building permits SAAR, monthly, column
  ``building_permits``), ``CSUSHPISA`` (S&P CoreLogic Case-Shiller US National HPI,
  SA, monthly, column ``case_shiller_sa``) -- column names per ``config.yml:211-214``.
  Any OTHER key in ``fred_frames`` is ignored (this composer never iterates the
  dict blindly; it only ever reads the four series ids it names).
* ``zori`` -- a plain rows list (or ``None``) for Zillow's national ZORI rent index
  (``data/zori/national.parquet``, column ``zori``; see the SA/NSA disclosure below).

This composer never loads a parquet file itself and never imports pandas -- see
the hand-off's "build.py loader spec" for the small ``_load_fred_series(path)``
helper the BUILDER (not this module) needs to add, derived from the WRITER's own
code (``collectors/fred.py`` / ``lib/store.py`` / ``scripts/collect_zori.py``),
never inspected via a live parquet read (this authoring session had no shell).

CENSUS BINDING (2026-09-04 F01 R5/R6 source census + CEO rights rulings,
``research/market_intelligence_productization/
MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md`` section 2
and rulings R-1..R-5): Housing ships v1 as COMPOSABLE-CORE + TYPED-ABSENT REMAINDER,
not the full architecture-10.10 required composition. The composable core is
EXACTLY the four FRED series above (VERIFIED present as ``data/fred/<SERIES>.parquet``
at authoring time) plus national ZORI when its store is populated. Everything the
architecture's "required composition" additionally names -- existing/pending home
sales, completions/new-home sales, Redfin high-frequency inventory/pending/price-
drop/DOM -- is published as a TYPED-ABSENT remainder leg with an honest reason,
never estimated from a different series and never silently dropped from the page.

RIGHTS LAWS (binding, ruling-cited, never re-litigated inline):
* R-1: Case-Shiller reaches this estate via FRED (CSUSHPISA). Neutral attribution
  only -- displayed as "Case-Shiller US National (via FRED)", never re-branded as
  this estate's own index.
* R-2: Freddie Mac PMMS (MORTGAGE30US) via FRED -- same posture as R-1.
* R-3: NAR terms bar STORAGE in a retrieval system (not merely redistribution) --
  existing/pending-home-sales legs that would need NAR are typed RIGHTS_BLOCKED.
  No NAR-derived series is ever stored, and no "affordability index" this composer
  might one day build is ever labeled as NAR's.
* Completions / new-home sales would need a NEW Census-bureau collector (Census
  New Residential Sales; no COMPUTSA-equivalent is registered anywhere in this
  estate per the census) -- this composer does not build collectors; typed
  NOT_COVERED.
* Redfin high-frequency (``scripts/collect_redfin_hf.py``): the collector IS real
  and nightly-wired, but ``data/redfin_hf/`` was EMPTY on the checked runner
  (silent-fail try/except, per the census) -- typed SOURCE_FAILED, an honest
  "collector exists, store empty" state, never NOT_COVERED (that token is reserved
  for legs with no collector at all). The +50-day publication-lag machinery
  (``scripts/housing_hf_phase0.py`` PIT_LAG_DAYS=50, tightened from an optimistic
  30d) and the ~34.5% calendar-seasonality correction Redfin's price-drop share
  needs are both DISCLOSED here but NOT implemented in this composer -- there is no
  data flowing yet for either to operate on; a future revision wires them once
  ``data/redfin_hf/`` is populated.

PIT / REVISION LAW: no ALFRED point-in-time vintage capture exists for ANY housing
series today (not MORTGAGE30US, HOUST, PERMIT, CSUSHPISA, or ZORI). Every level and
derived read below is therefore the LATEST-REVISED value as currently stored --
Census construction data in particular is revised for months after first release,
and a later re-read of the same reference period can show a different number with
no "as it was known then" alternative to fall back on. This is disclosed via the
``no_alfred_pit_vintage_capture`` implication, never silently assumed away.

SA / NSA MIXING LAW: CSUSHPISA and the two Census construction series (HOUST,
PERMIT) are seasonally adjusted (SA) by the publishing agency's own convention;
MORTGAGE30US is a market rate series SA does not apply to. ZORI's OWN collector
docstring (``scripts/collect_zori.py``) describes it as "smoothed, seasonally
adjusted", but the binding 2026-09-04 census recorded it as NOT seasonally adjusted
after inspecting the stored data. This composer cannot execute code in this
authoring environment to arbitrate that conflict against the parquet's own embedded
metadata, so it follows the BINDING census ruling (ZORI = NSA) and tags the read
"(unverified)" in the metric's own transformation text -- and, regardless of which
side of that dispute is correct, NEVER combines ZORI with the SA Case-Shiller series
in one derived value (no mixed-basis ratio, spread, or z-score is ever computed
across the two). The one cross-series derived read this composer DOES publish,
``permits_minus_starts_spread``, subtracts two same-basis SA series (HOUST, PERMIT)
-- never a same-basis-violating pair.

HEADLINE (read this before "fixing" it -- mirrors ``business_activity.py``'s note):
architecture section 10.10 DOES define a real two-axis blueprint (x: demand/
transaction momentum, weak -> strong; y: affordability/financing pressure,
restrictive -> supportive; supply overlay: scarce -> abundant) -- unlike
``monetary_policy``/``liquidity_central_banks``, which have NO headline-model
subsection at all and are therefore honestly ``NOT_APPLICABLE`` by design. Housing
is a DIFFERENT case: the blueprint exists, but the composable-core substrate cannot
compute it. The x-axis needs a demand/transaction-momentum read (existing-home
sales -- RIGHTS_BLOCKED; Redfin pending sales -- SOURCE_FAILED, empty store); the
y-axis needs a genuine affordability COMPOSITE (price-to-income), and this
composer has no income series to build one from -- publishing the single
``mortgage_30y_rate_level`` metric AS an "affordability" axis would fabricate a
composite exactly the way business_activity's docstring warns against. So:
``headline.state_id`` stays ``null`` with ``status="ABSENT"`` and
``null_reason="COMPUTATION_REFUSED"`` (a data refusal, NOT a design
"not-applicable" -- the distinction business_activity.py's own headline already
establishes as estate precedent), and ``axes.items`` stays ``[]`` (schema-legal).
The supply overlay ("scarce -> abundant") IS genuinely computable from HOUST/PERMIT
-- it is published honestly as real metrics/drivers (levels, YoY, the
permits-minus-starts spread) instead of being smuggled into a fabricated quadrant
the contract has no dedicated "overlay" slot for anyway.

CONTRADICTION: architecture 10.10's own alert vocabulary names "rent/home-price
divergence" as an eligible condition. When both Case-Shiller YoY and ZORI YoY are
present and their signs disagree beyond a disclosed flat band, this composer emits
a typed ``home_price_vs_rent_divergence`` DISAGREEMENT on the two implicated
metrics -- a genuine, owner-native two-series read, never a fabricated threshold
beyond the one disclosed flat-band constant.

DRIVERS BUCKET REUSE (disclosed, mirrors ``liquidity_central_banks.py``): the
contract's ``drivers`` block is closed to exactly ``{rate_side, balance_sheet}``.
``rate_side`` is a literal fit for the mortgage-rate legs. ``balance_sheet`` carries
the supply/price/rent legs (starts, permits, the spread, Case-Shiller YoY, ZORI
YoY) -- NOT a balance sheet -- because Housing has no dedicated "supply" bucket to
use; disclosed in the ``driver_bucket_naming_note`` implication, never left implicit.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive ceiling
only. Depends only on the standard library (no pandas import here -- the caller
supplies plain rows so this module stays testable without pandas). The composer
NEVER reads a wall clock: ``built_at`` is supplied by the caller, and every
staleness/age/lookback check is a pure function of ``built_at`` and the given rows,
so an identical set of owner inputs always yields an identical snapshot body.
"""
from __future__ import annotations

import datetime as _dt
from hashlib import sha256
from typing import Any, Mapping, Sequence

METHOD_VERSION = "housing_real_estate.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.housing"
WORKSPACE_ID = "housing_real_estate"

# The four composable-core FRED series (source census 2026-09-04 section 2). All
# four were VERIFIED present as data/fred/<SERIES>.parquet at authoring time (see
# the hand-off's "what could not be verified without a shell"). Column names per
# config.yml:211-214.
SERIES_MORTGAGE = "MORTGAGE30US"      # column: mortgage_30y   (weekly)
SERIES_STARTS = "HOUST"               # column: housing_starts (monthly, SA)
SERIES_PERMITS = "PERMIT"             # column: building_permits (monthly, SA)
SERIES_CASE_SHILLER = "CSUSHPISA"     # column: case_shiller_sa (monthly, SA)

# Cadence / grace-window laws (disclosed, not silently invented). Freshness is
# measured against the REFERENCE-PERIOD date each source is stamped with, so the
# cadence must be the worst-case age of the newest print the agency can possibly
# have published: publication lag at release PLUS one full release interval
# (right before the next print supersedes it). A shorter cadence mislabels a
# maximally-fresh source as late/stale -- a truth error in the wrong direction
# (proven live 2026-09-04: the June Case-Shiller print, published late August
# and the newest possible on Sept 4, read STALE_SOURCE under a 62d law measured
# from its 2026-06-01 reference date). Grace covers release-day jitter and
# shutdown-delayed releases; beyond grace = a genuinely missed release.
#   - PMMS (mortgage rate): weekly, Thursday-dated and published same day, so
#     lag~0 + 7d interval -- cadence 7d, grace 5d covers holiday-shifted
#     release days (mirrors liquidity_central_banks.py's W-FRI cadence law).
#   - Census New Residential Construction (HOUST/PERMIT): period-start dated,
#     released together ~17th-19th of the month AFTER the reference month (lag
#     ~48d) + up to ~31d until the next print -- cadence 80d, grace 17d.
#   - Case-Shiller (CSUSHPISA): period-start dated; S&P publishes a reference
#     month on the LAST TUESDAY two months later (lag up to ~92d) + up to ~35d
#     between last-Tuesday releases -- cadence 124d, grace 15d.
#   - ZORI: month-END dated, published ~2-3 weeks after month end (lag ~14-21d,
#     the collector's own "approximately a 1-month lag" per scripts/
#     collect_zori.py pit_lag_days=30) + ~31d until superseded -- cadence 50d,
#     grace 15d.
_MORTGAGE_CADENCE_DAYS = 7
_MORTGAGE_GRACE_DAYS = 5
_CONSTRUCTION_CADENCE_DAYS = 80
_CONSTRUCTION_GRACE_DAYS = 17
_CASE_SHILLER_CADENCE_DAYS = 124
_CASE_SHILLER_GRACE_DAYS = 15
_ZORI_CADENCE_DAYS = 50
_ZORI_GRACE_DAYS = 15

# Derived-read lookback windows (disclosed constants, never silently invented).
_THIRTEEN_WEEK_DAYS = 91
_YOY_DAYS = 365
# How far the LOCATED comparison row may sit short of the exact lookback target
# before this composer refuses the derived read as insufficient history, rather
# than silently comparing against a much-older stitched value. Weekly data can
# land within a couple of weeks of any target; monthly data needs a wider window
# to absorb 28-31 day month-length variance plus the occasional gap.
_WEEKLY_LOOKBACK_SLACK_DAYS = 10
_MONTHLY_LOOKBACK_SLACK_DAYS = 20

# Rent-vs-home-price contradiction flat band (percentage points, YoY): a leg
# reading smaller than this in magnitude is itself flat/noisy and can never be
# read as "disagreeing" with anything (mirrors liquidity_central_banks.py's
# _FED_FLAT_BAND_PCT disclosed-constant pattern).
_HOME_PRICE_RENT_FLAT_BAND_PCT = 1.0

# Disclosed context constants (documentation only -- NOT applied as freshness/lag
# machinery here, since no Redfin data is flowing yet to apply them to; see the
# module docstring and the redfin_store_empty_disclosure implication).
_REDFIN_PIT_LAG_DAYS_DISCLOSED = 50
_REDFIN_PRICE_DROP_SEASONALITY_PCT_DISCLOSED = 34.5

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

_TRACKED_CHANGE_METRICS = (
    "mortgage_30y_rate_level", "housing_starts_yoy", "building_permits_yoy",
    "case_shiller_national_hpi_yoy",
)
_TRACKED_CORRECTION_METRICS = (
    "mortgage_30y_rate_level", "mortgage_30y_rate_change_13w",
    "housing_starts_level", "housing_starts_yoy",
    "building_permits_level", "building_permits_yoy",
    "permits_minus_starts_spread",
    "case_shiller_national_hpi_level", "case_shiller_national_hpi_yoy",
    "national_rent_zori_level", "national_rent_zori_yoy",
)

_UNVERIFIED_SA_NOTE = (
    " (unverified against the parquet's own embedded metadata -- this composer "
    "cannot execute code to inspect it in this authoring environment; the SA/NSA "
    "basis is declared from the well-known FRED series convention / config.yml "
    "inline annotation instead, per the disclosed SA/NSA fallback law)"
)


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from any
# sibling composer, mirrors the shape of liquidity_central_banks.py /
# monetary_policy.py so this file can be added without touching any other module)
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


def _round(v: float | None, n: int = 4) -> float | None:
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


def _parse_date(s: Any) -> _dt.date | None:
    if isinstance(s, _dt.date):
        return s
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _iso(d: _dt.date | None) -> str | None:
    return d.isoformat() if isinstance(d, _dt.date) else None


def _age_days(built_at: Any, asof: Any) -> int | None:
    """Pure function of two GIVEN date/datetime values -- never a wall-clock
    read. ``built_at`` is always supplied by the caller (the builder), never
    sourced from ``datetime.now()`` inside this module."""
    b, a = _parse_date(built_at), _parse_date(asof)
    if b is None or a is None:
        return None
    return (b - a).days


# --------------------------------------------------------------------------- #
# raw-row handling (this composer, unlike its siblings, is handed plain level
# rows instead of a pre-aggregated owner JSON -- these helpers are the new
# surface that earns that trust)
# --------------------------------------------------------------------------- #
def _clean_rows(rows: Any) -> list[tuple[_dt.date, float]]:
    """Defensively normalize a caller-supplied row list: accept ``(date, value)``
    pairs or longer tuples (extra elements are ignored -- an unconsumed-field
    negative control for the digest tests), drop unparseable dates / non-numeric
    values, de-duplicate a repeated date keeping the LAST-listed occurrence
    (mirrors ``lib.store.upsert``'s own "new wins" convention), and sort
    ascending by date. Never raises on malformed input -- a bad row is dropped,
    never fabricated into a fake reading."""
    if not rows:
        return []
    out: dict[_dt.date, float] = {}
    for row in rows:
        if row is None:
            continue
        try:
            d_raw, v_raw = row[0], row[1]
        except (IndexError, TypeError, KeyError):
            continue
        d = _parse_date(d_raw)
        v = _num(v_raw)
        if d is None or v is None:
            continue
        out[d] = v
    return sorted(out.items())


def _latest(rows: list[tuple[_dt.date, float]]) -> tuple[_dt.date, float] | None:
    return rows[-1] if rows else None


def _value_before_or_at(rows: list[tuple[_dt.date, float]], target: _dt.date,
                         slack_days: int) -> tuple[_dt.date, float] | None:
    """The most recent row with date <= ``target``, accepted ONLY if it lands
    within ``slack_days`` of ``target`` -- never an arbitrarily-old fallback
    masquerading as a fresh 13w/YoY comparison point. Returns ``None`` (refuse)
    when no row reaches back far enough or the nearest one is too stale."""
    best: tuple[_dt.date, float] | None = None
    for d, v in rows:
        if d <= target:
            best = (d, v)
        else:
            break
    if best is None:
        return None
    if (target - best[0]).days > slack_days:
        return None
    return best


def _cadence_freshness(built_at: Any, asof: _dt.date | None, cadence_days: int,
                        grace_days: int, value_present: bool) -> str:
    """Weekly/monthly release-cadence law (see module docstring's per-series
    constants). ``value_present=False`` (series wholly absent) always reads
    SOURCE_FAILED; an ``asof`` in the future relative to ``built_at`` (a clock
    inversion) also reads SOURCE_FAILED rather than a nonsensical CURRENT."""
    if not value_present or asof is None:
        return "SOURCE_FAILED"
    age = _age_days(built_at, asof)
    if age is None or age < 0:
        return "SOURCE_FAILED"
    if age <= cadence_days:
        return "CURRENT"
    if age <= cadence_days + grace_days:
        return "LATE_WITHIN_TOLERANCE"
    return "STALE_SOURCE"


def _pct_change(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return _round((cur / prior - 1.0) * 100.0, 4)


def _level_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return _round(a - b, 4)


def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            calculation_as_of=None) -> dict:
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
        "source_refs": source_refs or [owner_ref],
        "source_digest": None,
        "transformation": transformation,
        "model_version": METHOD_VERSION,
        "uncertainty": {"kind": None, "value": None},
        "coverage": None,
        "freshness": freshness,
        "rights_state": "RIGHTS_BLOCKED" if freshness == "RIGHTS_BLOCKED" else "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metric_value(snapshot: Mapping | None, metric_id: str) -> Any:
    for m in (_get(snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _component_availability(component_id: str, label_en: str, label_zh: str,
                             rows: list[tuple[_dt.date, float]], freshness: str,
                             required: bool) -> dict:
    present = bool(rows)
    latest = _latest(rows)
    status = "PRESENT" if present and freshness == "CURRENT" else ("PARTIAL" if present else "ABSENT")
    if present:
        null_reason = None
    elif freshness == "SOURCE_FAILED":
        null_reason = "SOURCE_FAILED"
    else:
        null_reason = "UNKNOWN"
    return {
        "component_id": component_id,
        "label": _bil(label_en, label_zh),
        "required": required,
        "freshness": freshness,
        "status": status,
        "source_asof": _iso(latest[0]) if latest else None,
        "null_reason": null_reason,
    }


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(fred_frames: Mapping[str, Any] | None, zori: Sequence[Any] | None, *,
            built_at: str, prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``fred_frames`` (dict of raw FRED level rows, see module
    docstring) + ``zori`` (raw ZORI national rows) into an UNSEALED snapshot
    body. The builder seals it via ``contract.finalize``."""
    ff = fred_frames if isinstance(fred_frames, Mapping) else {}

    mortgage = _clean_rows(ff.get(SERIES_MORTGAGE))
    starts = _clean_rows(ff.get(SERIES_STARTS))
    permits = _clean_rows(ff.get(SERIES_PERMITS))
    case_shiller = _clean_rows(ff.get(SERIES_CASE_SHILLER))
    zori_rows = _clean_rows(zori)

    m_fresh = _cadence_freshness(built_at, _latest(mortgage)[0] if mortgage else None,
                                  _MORTGAGE_CADENCE_DAYS, _MORTGAGE_GRACE_DAYS, bool(mortgage))
    s_fresh = _cadence_freshness(built_at, _latest(starts)[0] if starts else None,
                                  _CONSTRUCTION_CADENCE_DAYS, _CONSTRUCTION_GRACE_DAYS, bool(starts))
    p_fresh = _cadence_freshness(built_at, _latest(permits)[0] if permits else None,
                                  _CONSTRUCTION_CADENCE_DAYS, _CONSTRUCTION_GRACE_DAYS, bool(permits))
    cs_fresh = _cadence_freshness(built_at, _latest(case_shiller)[0] if case_shiller else None,
                                   _CASE_SHILLER_CADENCE_DAYS, _CASE_SHILLER_GRACE_DAYS, bool(case_shiller))
    z_fresh = _cadence_freshness(built_at, _latest(zori_rows)[0] if zori_rows else None,
                                  _ZORI_CADENCE_DAYS, _ZORI_GRACE_DAYS, bool(zori_rows))

    # -- derive the raw values contradiction detection needs BEFORE building the
    # metric list (mirrors liquidity_central_banks.py's compute-then-detect order)
    cs_yoy_val = _yoy_value(case_shiller)
    zori_yoy_val = _yoy_value(zori_rows)
    contradictions = _detect_contradiction(cs_yoy_val, zori_yoy_val)
    fired_kinds = {c["kind"] for c in contradictions}

    metrics = _metrics(built_at, mortgage, starts, permits, case_shiller, zori_rows,
                        m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh,
                        cs_yoy_val, zori_yoy_val, fired_kinds)
    metrics_by_id = {m["metric_id"]: m["value"] for m in metrics}

    required_avail, optional_avail = _required_availability(
        mortgage, starts, permits, case_shiller, zori_rows,
        m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh)
    all_avail = required_avail + optional_avail
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    for c in contradictions:
        reasons.append(f"contradiction={c['kind']}")

    primary_contradiction = contradictions[0] if contradictions else {
        "kind": None, "en": None, "zh": None, "components": [],
    }

    dates: list[_dt.date] = []
    for rows in (mortgage, starts, permits, case_shiller):
        latest = _latest(rows)
        if latest:
            dates.append(latest[0])
    effective_date = _iso(max(dates)) if dates else None

    headline = _headline(effective_date, prior_snapshot)
    changes = _changes(metrics_by_id, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": WORKSPACE_ID,
            "title": _bil("Housing & Real Estate", "住房与房地产"),
            "subtitle": _bil("Demand/transaction momentum x affordability/financing pressure",
                              "需求/成交动能 × 可负担性/融资压力"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": effective_date,
            "content_sha256": "0" * 64,
        },
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False,
            "can_execute": False, "axis_authority_ceiling": "DESCRIPTIVE",
        },
        "availability": {
            "state": worst,
            "required": all_avail,
            "degraded": degraded,
            "coverage_ratio": coverage_ratio,
            "worst_freshness": worst,
            "contradiction": {
                "present": bool(contradictions),
                "kind": primary_contradiction["kind"],
                "en": primary_contradiction["en"],
                "zh": primary_contradiction["zh"],
                "components": primary_contradiction["components"],
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
        "drivers": _drivers(metrics_by_id),
        "changes": changes,
        "implications": {"items": _implications(
            metrics_by_id, contradictions, worst, coverage_ratio, bool(zori_rows))},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(mortgage, starts, permits, case_shiller, zori_rows,
                                       m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh)},
        "corrections": _corrections(metrics_by_id, effective_date, prior_snapshot),
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


# --------------------------------------------------------------------------- #
# derived-value + contradiction helpers
# --------------------------------------------------------------------------- #
def _yoy_value(rows: list[tuple[_dt.date, float]]) -> float | None:
    latest = _latest(rows)
    if latest is None:
        return None
    prior = _value_before_or_at(rows, latest[0] - _dt.timedelta(days=_YOY_DAYS),
                                 _MONTHLY_LOOKBACK_SLACK_DAYS)
    if prior is None:
        return None
    return _pct_change(latest[1], prior[1])


def _detect_contradiction(cs_yoy: float | None, zori_yoy: float | None) -> list[dict]:
    """Case-Shiller YoY vs ZORI YoY sign disagreement beyond the disclosed flat
    band (architecture 10.10's own "rent/home-price divergence" alert vocabulary;
    see module docstring). Both sides are genuine owner-native YoY reads; the only
    composer-invented number is the disclosed flat-band constant that keeps a
    merely-noisy reading from manufacturing a contradiction."""
    if cs_yoy is None or zori_yoy is None:
        return []
    if abs(cs_yoy) < _HOME_PRICE_RENT_FLAT_BAND_PCT or abs(zori_yoy) < _HOME_PRICE_RENT_FLAT_BAND_PCT:
        return []
    cs_dir = "rising" if cs_yoy > 0 else "falling"
    zori_dir = "rising" if zori_yoy > 0 else "falling"
    if cs_dir == zori_dir:
        return []
    cs_dir_zh = "上涨" if cs_yoy > 0 else "下跌"
    zori_dir_zh = "上涨" if zori_yoy > 0 else "下跌"
    return [{
        "kind": "home_price_vs_rent_divergence",
        "en": (f"Home prices are {cs_dir} year-over-year ({cs_yoy:g}%, Case-Shiller "
               f"US National via FRED) while the national rent read is {zori_dir} "
               f"year-over-year ({zori_yoy:g}%, Zillow ZORI) -- the price and rent "
               "legs of the housing cycle are pointing in opposite directions."),
        "zh": (f"房价同比{cs_dir_zh}（{cs_yoy:g}%，凯斯-席勒美国全国房价指数，经FRED），"
               f"而全国租金读数同比{zori_dir_zh}（{zori_yoy:g}%，Zillow ZORI）——"
               "住房周期的价格分项与租金分项方向相反。"),
        "components": ["case_shiller_national_hpi_yoy", "national_rent_zori_yoy"],
    }]


# --------------------------------------------------------------------------- #
# availability
# --------------------------------------------------------------------------- #
def _required_availability(mortgage, starts, permits, case_shiller, zori_rows,
                            m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh) -> tuple[list[dict], list[dict]]:
    specs = [
        ("mortgage_rate", "30-year fixed mortgage rate", "30年期固定抵押贷款利率",
         mortgage, m_fresh, True),
        ("housing_starts", "Housing starts", "新屋开工", starts, s_fresh, True),
        ("building_permits", "Building permits", "新增营建许可", permits, p_fresh, True),
        ("case_shiller_hpi", "Case-Shiller US National home-price index",
         "凯斯-席勒美国全国房价指数", case_shiller, cs_fresh, True),
        ("national_rent_zori", "National rent index (Zillow ZORI)",
         "全国租金指数（Zillow ZORI）", zori_rows, z_fresh, False),
    ]
    rows = [_component_availability(cid, en, zh, r, fr, req) for cid, en, zh, r, fr, req in specs]
    required_rows = [r for r in rows if r["required"]]
    optional_rows = [r for r in rows if not r["required"]]
    return required_rows, optional_rows


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(built_at, mortgage, starts, permits, case_shiller, zori_rows,
             m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh,
             cs_yoy_val, zori_yoy_val, fired_kinds: set[str]) -> list[dict]:
    items: list[dict] = []

    # -- mortgage rate: level + 13-week change (financing-pressure legs) ----- #
    m_latest = _latest(mortgage)
    m_level = m_latest[1] if m_latest else None
    m_date = _iso(m_latest[0]) if m_latest else None
    items.append(_metric(
        "mortgage_30y_rate_level", m_level, "percent", "percent", "market_rate_level",
        "higher_more_restrictive_financing", f"data/fred/{SERIES_MORTGAGE}.parquet",
        "fred.MORTGAGE30US.mortgage_30y", m_date, m_fresh,
        source_refs=["FRED:MORTGAGE30US (Freddie Mac PMMS via FRED, ruling R-2)"],
        transformation=(
            "Freddie Mac Primary Mortgage Market Survey 30-year fixed rate, "
            "republished by FRED; a market rate series SA/NSA does not apply to."
            + _UNVERIFIED_SA_NOTE
            + " No ALFRED point-in-time vintage exists for this series (see the "
              "no_alfred_pit_vintage_capture disclosure); the stored value is the "
              "current stored read."
        ),
    ))
    m13_prior = (_value_before_or_at(mortgage, m_latest[0] - _dt.timedelta(days=_THIRTEEN_WEEK_DAYS),
                                      _WEEKLY_LOOKBACK_SLACK_DAYS)
                 if m_latest else None)
    m13_val = _level_diff(m_level, m13_prior[1]) if m13_prior else None
    items.append(_metric(
        "mortgage_30y_rate_change_13w", m13_val, "number", "pct_pts",
        "trailing_13w_level_change", "higher_more_restrictive_financing",
        f"data/fred/{SERIES_MORTGAGE}.parquet", "fred.MORTGAGE30US.mortgage_30y",
        m_date, m_fresh, source_refs=["FRED:MORTGAGE30US"],
        transformation=(
            "Current level minus the level roughly 13 weeks (91 days) prior, in "
            "percentage points; refused when no observation lands within "
            f"{_WEEKLY_LOOKBACK_SLACK_DAYS} days of that lookback target."
        ),
        null_reason="INSUFFICIENT_HISTORY" if m_latest else None,
    ))

    # -- housing starts: level + YoY ------------------------------------------ #
    s_latest = _latest(starts)
    s_level = s_latest[1] if s_latest else None
    s_date = _iso(s_latest[0]) if s_latest else None
    items.append(_metric(
        "housing_starts_level", s_level, "number", "thousands_of_units_saar",
        "level", "higher_more_supply_pipeline", f"data/fred/{SERIES_STARTS}.parquet",
        "fred.HOUST.housing_starts", s_date, s_fresh, source_refs=["FRED:HOUST"],
        transformation=(
            "Census Bureau new privately-owned housing units started, seasonally "
            "adjusted annual rate, republished by FRED."
            + _UNVERIFIED_SA_NOTE
            + " No ALFRED point-in-time vintage exists for this series; Census "
              "construction data is revised for months after first release, and "
              "this composer publishes the current stored (latest-revised) read."
        ),
    ))
    s_yoy_val = _yoy_value(starts)
    items.append(_metric(
        "housing_starts_yoy", s_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_supply_pipeline", f"data/fred/{SERIES_STARTS}.parquet",
        "fred.HOUST.housing_starts", s_date, s_fresh, source_refs=["FRED:HOUST"],
        transformation="12-month percent change of the same SA series.",
        null_reason="INSUFFICIENT_HISTORY" if s_latest else None,
    ))

    # -- building permits: level + YoY ----------------------------------------- #
    p_latest = _latest(permits)
    p_level = p_latest[1] if p_latest else None
    p_date = _iso(p_latest[0]) if p_latest else None
    items.append(_metric(
        "building_permits_level", p_level, "number", "thousands_of_units_saar",
        "level", "higher_more_supply_pipeline", f"data/fred/{SERIES_PERMITS}.parquet",
        "fred.PERMIT.building_permits", p_date, p_fresh, source_refs=["FRED:PERMIT"],
        transformation=(
            "Census Bureau new private housing units authorized by building "
            "permits, seasonally adjusted annual rate, republished by FRED."
            + _UNVERIFIED_SA_NOTE
            + " No ALFRED point-in-time vintage exists for this series; this "
              "composer publishes the current stored (latest-revised) read."
        ),
    ))
    p_yoy_val = _yoy_value(permits)
    items.append(_metric(
        "building_permits_yoy", p_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_supply_pipeline", f"data/fred/{SERIES_PERMITS}.parquet",
        "fred.PERMIT.building_permits", p_date, p_fresh, source_refs=["FRED:PERMIT"],
        transformation="12-month percent change of the same SA series.",
        null_reason="INSUFFICIENT_HISTORY" if p_latest else None,
    ))

    # -- permits minus starts: a leg-floor-refused two-series spread ---------- #
    spread_val = _level_diff(p_level, s_level) if (s_latest and p_latest) else None
    if s_latest and p_latest:
        spread_fresh = _worst_freshness([s_fresh, p_fresh])
        spread_null = None
    elif s_latest or p_latest:
        spread_fresh = "SOURCE_FAILED"
        spread_null = "COMPUTATION_REFUSED"
    else:
        spread_fresh = "SOURCE_FAILED"
        spread_null = "SOURCE_FAILED"
    items.append(_metric(
        "permits_minus_starts_spread", spread_val, "number", "thousands_of_units_saar",
        "level_difference_permits_minus_starts", "higher_more_pipeline_ahead_of_starts",
        f"data/fred/{SERIES_PERMITS}.parquet + data/fred/{SERIES_STARTS}.parquet",
        "fred.PERMIT.building_permits - fred.HOUST.housing_starts",
        p_date or s_date, spread_fresh,
        source_refs=["FRED:PERMIT", "FRED:HOUST"],
        transformation=(
            "PERMIT level minus HOUST level (both seasonally-adjusted annual rate, "
            "thousands of units) -- a same-basis SA-vs-SA subtraction, never mixed "
            "with an NSA series. A leg-floor refusal: this composer never publishes "
            "the spread from only one of the two legs -- refused rather than "
            "defaulting the missing leg to zero."
        ),
        null_reason=spread_null,
    ))

    # -- Case-Shiller: level + YoY (with DISAGREEMENT tagging if the rent-vs- #
    # -- price contradiction fired) -------------------------------------------- #
    cs_latest = _latest(case_shiller)
    cs_level = cs_latest[1] if cs_latest else None
    cs_date = _iso(cs_latest[0]) if cs_latest else None
    items.append(_metric(
        "case_shiller_national_hpi_level", cs_level, "index", "index_pt_jan2000_100",
        "level", "higher_more_expensive", f"data/fred/{SERIES_CASE_SHILLER}.parquet",
        "fred.CSUSHPISA.case_shiller_sa", cs_date, cs_fresh, source_refs=["FRED:CSUSHPISA"],
        transformation=(
            "S&P CoreLogic Case-Shiller U.S. National Home Price Index, seasonally "
            "adjusted, republished by FRED (ruling R-1 -- neutral 'via FRED' "
            "attribution, never re-branded as this estate's own index). The "
            "published print is itself a roughly 2-month-lagged 3-month moving "
            "average by S&P's own construction, which this composer discloses but "
            "never un-smooths or nowcasts."
            + _UNVERIFIED_SA_NOTE
        ),
    ))
    cs_disagree = "home_price_vs_rent_divergence" in fired_kinds and cs_yoy_val is not None
    items.append(_metric(
        "case_shiller_national_hpi_yoy", cs_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_expensive", f"data/fred/{SERIES_CASE_SHILLER}.parquet",
        "fred.CSUSHPISA.case_shiller_sa", cs_date, cs_fresh, source_refs=["FRED:CSUSHPISA"],
        transformation="12-month percent change of the same SA, ~2-month-lagged 3-month-moving-average series.",
        status="DISAGREEMENT" if cs_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if cs_disagree else ("INSUFFICIENT_HISTORY" if cs_latest else None),
    ))

    # -- ZORI national rent: level + YoY (optional leg) ------------------------ #
    z_latest = _latest(zori_rows)
    z_level = z_latest[1] if z_latest else None
    z_date = _iso(z_latest[0]) if z_latest else None
    items.append(_metric(
        "national_rent_zori_level", z_level, "number", "usd_per_month", "level",
        "higher_more_expensive_rent", "data/zori/national.parquet",
        "zori.national.zori", z_date, z_fresh, source_refs=["Zillow Research ZORI (national, smoothed)"],
        transformation=(
            "Zillow Research ZORI (smoothed, all home types), national aggregate, "
            "collected directly from Zillow -- not FRED. Zillow's own collector-"
            "side methodology note describes this series as seasonally adjusted, "
            "but the 2026-09-04 binding source census recorded it as NOT "
            "seasonally adjusted after inspecting the stored data; this composer "
            "follows the binding census ruling (NSA)" + _UNVERIFIED_SA_NOTE
            + " and never combines it with the SA Case-Shiller series in one "
              "derived read. Approximately a 1-month publication lag per the "
              "collector's own note; no ALFRED-equivalent point-in-time vintage "
              "capture exists for this series."
        ),
    ))
    zori_disagree = "home_price_vs_rent_divergence" in fired_kinds and zori_yoy_val is not None
    items.append(_metric(
        "national_rent_zori_yoy", zori_yoy_val, "percent", "percent", "yoy_pct_change",
        "higher_more_expensive_rent", "data/zori/national.parquet",
        "zori.national.zori", z_date, z_fresh, source_refs=["Zillow Research ZORI (national, smoothed)"],
        transformation="12-month percent change of the same (NSA-per-census) series.",
        status="DISAGREEMENT" if zori_disagree else "PRESENT",
        null_reason="DISAGREEMENT" if zori_disagree else ("INSUFFICIENT_HISTORY" if z_latest else None),
    ))

    # -- typed-ABSENT remainder: rights-blocked / not-covered / source-failed - #
    items.append(_metric(
        "existing_home_sales", None, "count", "units_saar", "n/a", "n/a",
        "NONE -- NAR terms bar storage in a retrieval system (ruling R-3)",
        "NONE", None, "RIGHTS_BLOCKED",
        transformation=(
            "NAR (National Association of REALTORS) existing-home-sales data is "
            "rights-blocked for storage in this estate's retrieval system -- NAR's "
            "own terms bar storage, not merely redistribution. No NAR-derived "
            "series is ever stored or shown here, and this composer never builds "
            "an emulated stand-in for NAR's own index. A future in-house "
            "affordability construct may use only public, non-NAR inputs, and "
            "would never be labeled as NAR's."
        ),
        null_reason="RIGHTS_BLOCKED",
    ))
    items.append(_metric(
        "new_home_sales", None, "count", "units_saar", "n/a", "n/a",
        "NONE -- no Census New Residential Sales collector is wired in this estate",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "Census Bureau New Residential Sales would supply this leg, but no "
            "collector for that release exists in this estate today. Building a "
            "new collector is out of scope for this composer; typed as not "
            "covered rather than estimated from a different series."
        ),
        null_reason="NOT_COVERED",
    ))
    items.append(_metric(
        "housing_completions", None, "count", "units_saar", "n/a", "n/a",
        "NONE -- no Census completions (COMPUTSA-equivalent) collector is wired",
        "NONE", None, "NOT_COVERED",
        transformation=(
            "Census Bureau housing completions (a COMPUTSA-equivalent release) has "
            "no collector registered anywhere in this estate today. This composer "
            "does not build new collectors; typed as not covered."
        ),
        null_reason="NOT_COVERED",
    ))
    redfin_note = (
        "scripts/collect_redfin_hf.py is a real, nightly-wired collector for this "
        "leg, but its store (data/redfin_hf/) was empty on the checked runner -- "
        "an honest 'collector exists, data absent' state, distinct from a "
        "leg with no collector at all. Once populated, this leg needs a "
        f"{_REDFIN_PIT_LAG_DAYS_DISCLOSED}-day publication lag before predictive "
        "use (tightened from an optimistic 30 days by prior phase-0 study), which "
        "this composer discloses but does not implement here -- there is no data "
        "flowing yet for that machinery to operate on."
    )
    items.append(_metric(
        "pending_home_sales_redfin", None, "count", "count", "n/a", "n/a",
        "NONE -- scripts/collect_redfin_hf.py store is empty", "NONE", None, "SOURCE_FAILED",
        transformation=redfin_note, null_reason="SOURCE_FAILED",
    ))
    items.append(_metric(
        "active_listings_redfin", None, "count", "count", "n/a", "n/a",
        "NONE -- scripts/collect_redfin_hf.py store is empty", "NONE", None, "SOURCE_FAILED",
        transformation=redfin_note, null_reason="SOURCE_FAILED",
    ))
    items.append(_metric(
        "price_drop_share_redfin", None, "percent", "percent", "n/a", "n/a",
        "NONE -- scripts/collect_redfin_hf.py store is empty", "NONE", None, "SOURCE_FAILED",
        transformation=(
            redfin_note + " This particular leg is additionally roughly "
            f"{_REDFIN_PRICE_DROP_SEASONALITY_PCT_DISCLOSED:g} percent pure "
            "calendar-month seasonality when not deseasonalized (prior phase-0 "
            "finding); a future consumer must deseasonalize before use."
        ),
        null_reason="SOURCE_FAILED",
    ))
    items.append(_metric(
        "median_days_on_market_redfin", None, "count", "days", "n/a", "n/a",
        "NONE -- scripts/collect_redfin_hf.py store is empty", "NONE", None, "SOURCE_FAILED",
        transformation=redfin_note, null_reason="SOURCE_FAILED",
    ))

    return items


# --------------------------------------------------------------------------- #
# headline (always refused -- see module docstring: COMPUTATION_REFUSED, not
# NOT_APPLICABLE -- architecture 10.10 DOES define a two-axis blueprint)
# --------------------------------------------------------------------------- #
def _headline(effective_date, prior_snapshot) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil("Demand/transaction momentum x affordability/financing pressure; supply scarce -> abundant",
                          "需求/成交动能 × 可负担性/融资压力；供给 稀缺 → 充裕"),
        "method_version": METHOD_VERSION,
        "effective_date": effective_date,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {"state_id": None, "effective_date": prior_eff, "method_version": prior_method},
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "COMPUTATION_REFUSED"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": (
                "architecture section 10.10 defines a real two-axis blueprint "
                "(demand/transaction momentum x affordability/financing pressure, "
                "supply scarce-to-abundant overlay), but the composable-core data "
                "this composer has cannot fill it in: the demand/transaction axis "
                "would need existing-home sales (rights-blocked) or Redfin pending "
                "sales (collector store empty), and the affordability axis would "
                "need a genuine price-to-income composite this estate has no income "
                "series to build. Publishing the mortgage-rate level alone as an "
                "'affordability axis' would fabricate a composite the data does not "
                "support. The supply overlay IS computable from starts/permits and is "
                "published honestly as real metrics/drivers instead of being forced "
                "into a quadrant the contract has no dedicated overlay slot for. See "
                "the headline_unavailable implication for the reader-facing version."
            ),
        },
        "status": "ABSENT",
        "null_reason": "COMPUTATION_REFUSED",
    }


# --------------------------------------------------------------------------- #
# drivers (bucket reuse, disclosed -- see module docstring)
# --------------------------------------------------------------------------- #
def _drivers(metrics_by_id: dict) -> dict:
    def _mk(driver_id, label_en, label_zh, owner_field, value, unit, note):
        sign = 0
        mag = None
        if isinstance(value, (int, float)):
            sign = 1 if value > 0 else (-1 if value < 0 else 0)
            mag = abs(value)
        return {
            "driver_id": driver_id, "label": _bil(label_en, label_zh),
            "owner_field": owner_field, "value": value, "unit": unit,
            "impact_sign": sign, "impact_magnitude": mag, "note": note,
            "coverage_state": "PRESENT" if value is not None else "ABSENT",
        }

    rate_side = [
        _mk("mortgage_30y_rate_level", "30-year mortgage rate", "30年期抵押贷款利率",
            "fred.MORTGAGE30US.mortgage_30y", metrics_by_id.get("mortgage_30y_rate_level"), "percent",
            "higher = more restrictive home-purchase financing"),
        _mk("mortgage_30y_rate_change_13w", "Mortgage rate 13w change", "抵押贷款利率13周变化",
            "fred.MORTGAGE30US.mortgage_30y", metrics_by_id.get("mortgage_30y_rate_change_13w"), "pct_pts",
            "positive = financing conditions tightened over the trailing 13 weeks"),
    ]
    balance_sheet = [
        _mk("housing_starts_yoy", "Housing starts YoY", "新屋开工同比",
            "fred.HOUST.housing_starts", metrics_by_id.get("housing_starts_yoy"), "percent",
            "bucket reuse: published under drivers.balance_sheet because the contract's driver "
            "bucket pair is fixed as rate_side/balance_sheet and Housing has no dedicated supply "
            "bucket -- see the driver_bucket_naming_note implication"),
        _mk("building_permits_yoy", "Building permits YoY", "营建许可同比",
            "fred.PERMIT.building_permits", metrics_by_id.get("building_permits_yoy"), "percent",
            "bucket reuse: see housing_starts_yoy's note"),
        _mk("permits_minus_starts_spread", "Permits minus starts spread", "许可减开工利差",
            "fred.PERMIT.building_permits - fred.HOUST.housing_starts",
            metrics_by_id.get("permits_minus_starts_spread"), "thousands_of_units_saar",
            "positive = permits running ahead of starts (pipeline building); bucket reuse, see housing_starts_yoy's note"),
        _mk("case_shiller_national_hpi_yoy", "Case-Shiller US National HPI YoY", "凯斯-席勒美国全国房价指数同比",
            "fred.CSUSHPISA.case_shiller_sa", metrics_by_id.get("case_shiller_national_hpi_yoy"), "percent",
            "bucket reuse: see housing_starts_yoy's note"),
        _mk("national_rent_zori_yoy", "National rent index YoY", "全国租金指数同比",
            "zori.national.zori", metrics_by_id.get("national_rent_zori_yoy"), "percent",
            "bucket reuse: see housing_starts_yoy's note"),
    ]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(metrics_by_id: dict, contradictions: list[dict], worst_freshness: str,
                   coverage_ratio: float, zori_present: bool) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "HIGH",
        "method_stability": "HIGH",
        "evidence_breadth": "LOW" if not zori_present else "MEDIUM",
        "contradiction_state": "PRESENT" if contradictions else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "No dual-axis Housing state (demand/transaction momentum x "
            "affordability/financing pressure) is asserted: the composable-core "
            "data this page has -- mortgage rate, starts, permits, and the "
            "Case-Shiller home-price index -- cannot fill in a demand/transaction "
            "read (existing-home sales are rights-blocked; Redfin pending sales "
            "have no populated store yet) or a genuine affordability composite "
            "(no income series is available). The real, honest supply-side reads "
            "(starts, permits, the permits-minus-starts spread) are published as "
            "metrics instead of being forced into a fabricated quadrant.",
            "本页未给出双轴住房状态（需求/成交动能 × 可负担性/融资压力）：本页拥有的可组合核心数据"
            "——抵押贷款利率、新屋开工、营建许可与凯斯-席勒房价指数——无法填补需求/成交读数"
            "（成屋销售权利受限；Redfin待售数据尚无已填充的存储）或真实的可负担性综合指标"
            "（没有可用的收入序列）。真实、诚实的供给侧读数（开工、许可、许可减开工利差）"
            "以指标形式发布，而非被强行纳入一个虚构的象限。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing", "financing", "supply"],
        "contradictions": [c["kind"] for c in contradictions],
        "trace_ref": "engine.market_os.macro_workspaces.housing#headline",
    }]

    mrl = metrics_by_id.get("mortgage_30y_rate_level")
    if mrl is not None:
        m13 = metrics_by_id.get("mortgage_30y_rate_change_13w")
        m13_txt_en = f", {m13:+.2f} percentage points over the trailing 13 weeks" if m13 is not None else ""
        m13_txt_zh = f"，较13周前变化{m13:+.2f}个百分点" if m13 is not None else ""
        items.append({
            "implication_id": "mortgage_rate_read",
            "text": _bil(
                f"The 30-year fixed mortgage rate reads {mrl:g}%{m13_txt_en}.",
                f"30年期固定抵押贷款利率读数为{mrl:g}%{m13_txt_zh}。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["financing"], "contradictions": [],
            "trace_ref": f"data/fred/{SERIES_MORTGAGE}.parquet",
        })

    starts_yoy = metrics_by_id.get("housing_starts_yoy")
    permits_yoy = metrics_by_id.get("building_permits_yoy")
    spread = metrics_by_id.get("permits_minus_starts_spread")
    if starts_yoy is not None or permits_yoy is not None:
        starts_txt_en = f"starts {starts_yoy:+.1f}% YoY" if starts_yoy is not None else "starts YoY unavailable"
        permits_txt_en = f"permits {permits_yoy:+.1f}% YoY" if permits_yoy is not None else "permits YoY unavailable"
        starts_txt_zh = f"开工同比{starts_yoy:+.1f}%" if starts_yoy is not None else "开工同比不可得"
        permits_txt_zh = f"许可同比{permits_yoy:+.1f}%" if permits_yoy is not None else "许可同比不可得"
        spread_txt_en = f" Permits-minus-starts spread reads {spread:+.1f} thousand units SAAR." if spread is not None else ""
        spread_txt_zh = f" 许可减开工利差读数为{spread:+.1f}千套（季节调整年化）。" if spread is not None else ""
        items.append({
            "implication_id": "supply_pipeline_read",
            "text": _bil(
                f"Supply pipeline: {starts_txt_en}, {permits_txt_en}.{spread_txt_en}",
                f"供给管道：{starts_txt_zh}，{permits_txt_zh}。{spread_txt_zh}"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["supply"], "contradictions": [],
            "trace_ref": f"data/fred/{SERIES_STARTS}.parquet",
        })

    cs_yoy = metrics_by_id.get("case_shiller_national_hpi_yoy")
    if cs_yoy is not None:
        items.append({
            "implication_id": "home_price_read",
            "text": _bil(
                f"Case-Shiller US National home prices (via FRED) read {cs_yoy:+.1f}% "
                "year-over-year; this print is a roughly 2-month-lagged 3-month "
                "moving average by the publisher's own construction.",
                f"凯斯-席勒美国全国房价指数（经FRED）同比读数为{cs_yoy:+.1f}%；"
                "该数值本身是发布方按其自身方法构建的约滞后2个月的3个月移动平均值。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["housing_prices"], "contradictions": [],
            "trace_ref": f"data/fred/{SERIES_CASE_SHILLER}.parquet",
        })

    if zori_present:
        zori_yoy = metrics_by_id.get("national_rent_zori_yoy")
        if zori_yoy is not None:
            items.append({
                "implication_id": "rent_read",
                "text": _bil(
                    f"The national ZORI rent index (Zillow) reads {zori_yoy:+.1f}% "
                    "year-over-year.",
                    f"全国ZORI租金指数（Zillow）同比读数为{zori_yoy:+.1f}%。"),
                "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
                "channels": ["rent"], "contradictions": [],
                "trace_ref": "data/zori/national.parquet",
            })
    else:
        items.append({
            "implication_id": "rent_leg_absent",
            "text": _bil(
                "The national rent leg (Zillow ZORI) is not shown this cycle: no "
                "populated store was supplied to this build.",
                "本周期未展示全国租金分项（Zillow ZORI）：本次构建未提供已填充的存储。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["rent"], "contradictions": [], "trace_ref": None,
        })

    for c in contradictions:
        items.append({
            "implication_id": f"contradiction_{c['kind']}",
            "text": _bil(c["en"], c["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["housing_prices", "rent"], "contradictions": [c["kind"]],
            "trace_ref": f"data/fred/{SERIES_CASE_SHILLER}.parquet",
        })

    items.append({
        "implication_id": "no_alfred_pit_vintage_capture",
        "text": _bil(
            "No point-in-time vintage capture exists for any series on this page "
            "today. Every level and derived read above is the current stored "
            "(latest-revised) value, not what was knowable in real time; Census "
            "construction data in particular is revised for months after first "
            "release, so a later re-read of the same reference period can differ "
            "from what is shown here.",
            "本页所有序列目前均无时点（PIT）版本捕获。以上所有水平值与派生读数均为当前存储的"
            "（最新修订后的）数值，而非当时实际可知的数值；人口普查局的建筑类数据在首次发布后"
            "会持续修订数月，因此同一参考期的后续重新读取可能与此处展示的数值不同。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "nar_rights_blocked_disclosure",
        "text": _bil(
            "Existing-home sales are not shown: NAR licensing terms bar storing "
            "this data in a retrieval system, so this estate does not collect or "
            "store it, and never builds a stand-in labeled as NAR's own index.",
            "本页未展示成屋销售数据：NAR的许可条款禁止在检索系统中存储该数据，"
            "因此本估值体系不采集也不存储该数据，也绝不构建标注为NAR自有指数的替代品。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "new_construction_not_covered_disclosure",
        "text": _bil(
            "New-home sales and housing completions are not shown: no collector "
            "for either official Census release exists in this estate yet. This "
            "workspace does not estimate either figure from a different series.",
            "新屋销售与住宅竣工数据未展示：本估值体系目前尚未为这两项官方人口普查局发布"
            "接入任何采集器。本工作区不会用其他序列估算这两项数值。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing", "supply"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "redfin_store_empty_disclosure",
        "text": _bil(
            "Pending sales, active listings, price-drop share, and median days on "
            "market (Redfin) are not shown: the collector for this data is wired "
            "and runs nightly, but its store held no rows as of this build. Once "
            "populated, these reads need a roughly 50-day publication lag before "
            "predictive use, and the price-drop leg needs deseasonalization -- "
            "both are disclosed here, neither is implemented in this composer yet.",
            "待售房屋、在售库存、降价房源占比与上市天数中位数（Redfin）均未展示：该数据的"
            "采集器已接入且每晚运行，但截至本次构建其存储中没有任何数据行。填充后，这些读数"
            "在用于预测前需要约50天的发布滞后，且降价分项需要去季节化处理——两者均已在此披露，"
            "但本组合器尚未实现相应机制。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing", "supply"], "contradictions": [], "trace_ref": None,
    })

    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The drivers.balance_sheet bucket in this snapshot carries supply, "
            "home-price, and rent legs (starts, permits, the permits-minus-starts "
            "spread, Case-Shiller YoY, ZORI YoY), not a balance sheet. The "
            "contract's driver bucket pair is fixed as rate_side/balance_sheet and "
            "this workspace has no dedicated supply bucket to use, so the naming "
            "is cosmetic bucket reuse, disclosed here rather than left implicit.",
            "本快照中drivers.balance_sheet分组承载的是供给、房价与租金分项（开工、许可、"
            "许可减开工利差、凯斯-席勒同比、ZORI同比），而非资产负债表。合约的驱动因素分组"
            "固定为rate_side/balance_sheet，本工作区没有独立的供给分组可用，因此命名属于"
            "用途借用，在此明确披露而非隐含处理。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["housing"], "contradictions": [], "trace_ref": None,
    })

    return items


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- R5 non-goal: execution)
# --------------------------------------------------------------------------- #
def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "mortgage_rate_bp", "label": _bil("Mortgage rate", "抵押贷款利率"),
             "unit": "bp", "step": 25.0, "min": -300.0, "max": 300.0,
             "owner_field": "fred.MORTGAGE30US.mortgage_30y"},
            {"assumption_id": "housing_starts_pct", "label": _bil("Housing starts growth", "新屋开工增长"),
             "unit": "pct", "step": 1.0, "min": -50.0, "max": 50.0,
             "owner_field": "fred.HOUST.housing_starts"},
            {"assumption_id": "building_permits_pct", "label": _bil("Building permits growth", "营建许可增长"),
             "unit": "pct", "step": 1.0, "min": -50.0, "max": 50.0,
             "owner_field": "fred.PERMIT.building_permits"},
            {"assumption_id": "home_price_yoy_pct", "label": _bil("Home-price YoY", "房价同比"),
             "unit": "pct", "step": 0.5, "min": -30.0, "max": 30.0,
             "owner_field": "fred.CSUSHPISA.case_shiller_sa"},
            {"assumption_id": "household_income_pct", "label": _bil("Household income growth", "家庭收入增长"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0, "owner_field": None},
            {"assumption_id": "inventory_months_supply", "label": _bil("Months' supply of inventory", "库存月供应量"),
             "unit": "months", "step": 0.5, "min": 0.0, "max": 24.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": (
            "Assumption vocabulary is declared and closed; this composer ships no "
            "scenario execution endpoint (non-goal). household_income_pct has no "
            "owner_field because this estate has no income series in the "
            "composable core; inventory_months_supply has no owner_field because "
            "the Redfin inventory leg's store is currently empty. A future "
            "owner-native pure scenario function produces "
            "mastermind.macro_workspace_scenario_result.v1 with no canonical write."
        ),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "affordability_threshold", "kind": "boundary_approach",
             "label": _bil("Affordability threshold", "可负担性阈值"), "params": ["mortgage_rate_pct"]},
            {"condition_id": "permit_start_turn", "kind": "state_transition",
             "label": _bil("Permit/start turn", "许可/开工转向"), "params": ["direction"]},
            {"condition_id": "inventory_regime_change", "kind": "state_transition",
             "label": _bil("Inventory regime change", "库存体制变化"), "params": ["regime"]},
            {"condition_id": "rent_home_price_divergence", "kind": "contradiction_change",
             "label": _bil("Rent/home-price divergence", "租金/房价背离"), "params": ["kind"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "release_approaching", "kind": "release_approaching",
             "label": _bil("Release approaching", "数据发布临近"), "params": ["source_id", "days"]},
        ],
        "status": "ABSENT",
        "note": (
            "Eligible condition types are declared; this composer writes no alert "
            "(non-goal). Alerts extend the existing Terminal alert lifecycle "
            "later; a page shows the Alerts tab only once the service can "
            "create/list/evaluate/delete these real conditions."
        ),
    }


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def _sources(mortgage, starts, permits, case_shiller, zori_rows,
             m_fresh, s_fresh, p_fresh, cs_fresh, z_fresh) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, artifact_ref, fresh, rights="OPEN"):
        return {
            "source_id": source_id, "label": _bil(en, zh), "owner_ref": owner_ref,
            "provider": provider, "reference_period": ref_period, "released_at": None,
            "first_known_at": None, "collected_at": None, "revised_at": None,
            "correction_state": "unknown", "transform": None, "rights_state": rights,
            "definition_id": None, "definition_version": None, "artifact_ref": artifact_ref,
            "freshness": fresh,
        }

    m_asof = _iso(_latest(mortgage)[0]) if mortgage else None
    s_asof = _iso(_latest(starts)[0]) if starts else None
    p_asof = _iso(_latest(permits)[0]) if permits else None
    cs_asof = _iso(_latest(case_shiller)[0]) if case_shiller else None
    z_asof = _iso(_latest(zori_rows)[0]) if zori_rows else None

    return [
        _src("mortgage_rate", "30-year fixed mortgage rate (Freddie Mac PMMS, via FRED)",
             "30年期固定抵押贷款利率（Freddie Mac PMMS，经FRED）", "collectors.fred[MORTGAGE30US]",
             "Freddie Mac / FRED", m_asof, f"data/fred/{SERIES_MORTGAGE}.parquet", m_fresh),
        _src("housing_starts", "Housing starts (Census New Residential Construction, via FRED)",
             "新屋开工（人口普查局新建住宅统计，经FRED）", "collectors.fred[HOUST]",
             "US Census Bureau / FRED", s_asof, f"data/fred/{SERIES_STARTS}.parquet", s_fresh),
        _src("building_permits", "Building permits (Census New Residential Construction, via FRED)",
             "新增营建许可（人口普查局新建住宅统计，经FRED）", "collectors.fred[PERMIT]",
             "US Census Bureau / FRED", p_asof, f"data/fred/{SERIES_PERMITS}.parquet", p_fresh),
        _src("case_shiller_hpi", "Case-Shiller US National (via FRED)",
             "凯斯-席勒美国全国房价指数（经FRED）", "collectors.fred[CSUSHPISA]",
             "S&P CoreLogic Case-Shiller / FRED", cs_asof, f"data/fred/{SERIES_CASE_SHILLER}.parquet", cs_fresh),
        _src("national_rent_zori", "National rent index (Zillow ZORI, smoothed)",
             "全国租金指数（Zillow ZORI，平滑处理）", "scripts.collect_zori",
             "Zillow Research", z_asof, "data/zori/national.parquet", z_fresh),
        _src("existing_home_sales_nar", "Existing-home sales (NAR)", "成屋销售（NAR）",
             "NONE -- rights-blocked for storage (ruling R-3)", "National Association of REALTORS",
             None, None, "RIGHTS_BLOCKED", rights="RIGHTS_BLOCKED"),
        _src("new_home_sales_census", "New-home sales (Census New Residential Sales)",
             "新屋销售（人口普查局新建住宅销售统计）",
             "NONE -- no collector wired in this estate", "US Census Bureau",
             None, None, "NOT_COVERED"),
        _src("housing_completions_census", "Housing completions (Census, COMPUTSA-equivalent)",
             "住宅竣工（人口普查局，COMPUTSA同类统计）",
             "NONE -- no collector wired in this estate", "US Census Bureau",
             None, None, "NOT_COVERED"),
        _src("redfin_high_frequency", "Redfin high-frequency inventory/pending/price-drop/DOM",
             "Redfin高频库存/待售/降价/上市天数数据", "scripts.collect_redfin_hf",
             "Redfin Data Center", None, "data/redfin_hf/", "SOURCE_FAILED"),
    ]


# --------------------------------------------------------------------------- #
# changes / corrections
# --------------------------------------------------------------------------- #
def _changes(current_metrics_by_id: dict, prior_snapshot: Mapping | None) -> dict:
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
        cur = current_metrics_by_id.get(mid)
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


def _corrections(current_metrics_by_id: dict, effective_date, prior_snapshot: Mapping | None) -> dict:
    """Scoped supersession detection over the tracked metric subset (mirrors the
    liquidity_central_banks/monetary_policy pattern; see liquidity_regime.py's
    own _corrections for the full caveat about this being a scoped subset, not a
    persisted vintage ledger)."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {
            "predecessor_generation_id": None, "changed_fingerprints": [],
            "correction_state": "none",
            "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists.",
        }
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_eff != effective_date:
        return {
            "predecessor_generation_id": prior_gen, "changed_fingerprints": [],
            "correction_state": "none",
            "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted.",
        }
    changed: list[str] = []
    for mid in _TRACKED_CORRECTION_METRICS:
        cur = current_metrics_by_id.get(mid)
        prev = _metric_value(prior_snapshot, mid)
        if cur != prev:
            digest16 = sha256(f"{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
            changed.append(f"{mid}:{mid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen, "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native metrics changed value: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen, "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no tracked metric changed value (no-change republication).",
    }
