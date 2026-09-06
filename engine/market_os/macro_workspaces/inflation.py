"""Pure composer for the US ``inflation_system`` workspace snapshot (F01 R2 packet).

Reads exactly one owner-native artifact -- ``inflation_intelligence.v1``
(``data/release_forecast/inflation_intelligence.json``, produced by
``engine.inflation_intelligence.build_inflation_intelligence``) -- and projects
it into a ``mastermind.macro_workspace_snapshot.v1`` body. Mirrors the R1A
``liquidity_regime`` composer's structure and typed-degradation discipline
(architecture section 7 house law); see the note near the bottom of this
docstring for the one remaining forced reuse a future schema revision should fix.

It:

* builds a dual-axis quadrant state
    x = inflation impulse     (disinflationary -> inflationary)
    y = persistence / breadth (narrow-transitory -> broad-persistent)
  with four descriptive quadrants A/B/C/D and disclosed hysteresis, reusing
  the SAME domain-agnostic boundary/hysteresis math as liquidity_regime
  (BOUNDARY=50, HYSTERESIS_BAND=5) -- nothing about that math is liquidity-
  specific;
* publishes each axis's components, signs, weights, coverage floor, frequency
  alignment, thresholds, definition/data versions, and revision behaviour
  (composite/axis law, architecture section 7.9);
* NEVER re-derives a CPI/PCE value from parquet: every published number is
  either read verbatim from ``inflation_intelligence.v1`` (mom_pct, yoy_pct,
  annualized_3m_pct, annualized_6m_pct, acceleration_3m_minus_6m_pp -- all
  already computed by the owner engine) or a disclosed ALGEBRAIC transform of
  exactly one owner-published scalar (a spread between two owner numbers, or
  compounding one owner MoM point to an annualized rate) -- never a fresh
  read of a FRED parquet file;
* keeps ``reference_period`` (the CPI print's calendar month) and
  ``calculation_as_of``/``released_at`` distinct per the inflation-specific
  clock law: CPI/PCE structurally lag their reference month by weeks, so a
  component's freshness is judged against the OWNER's own publication-lag
  tolerance, never against wall-clock "today";
* emits TYPED degraded states, never zero/neutral/calm:
    - a required component's owner value missing  -> SOURCE_FAILED
    - owner classifies the source "stale"          -> STALE_SOURCE
    - the in-progress-month nowcast has no model
      entry yet                                    -> NOT_YET_RELEASED
    - axis coverage below the floor                -> value null + COMPUTATION_REFUSED
    - the sticky-led proxy mix persists while the
      headline impulse reads disinflationary       -> a typed contradiction (DISAGREEMENT)
    - no comparable prior print                     -> vector/changes WARMUP
    - prior print on a different method              -> changes METHOD_CHANGED (refuses deltas)

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library. The composer NEVER reads
a wall clock: ``built_at`` and any evaluation clock are passed in by the
builder, so an identical owner input always yields an identical snapshot body.

Consumes ONLY a real, already-accepted owner artifact (``inflation_intelligence.v1``,
itself display_only/authority=False end-to-end). This does NOT promote the
records-only Rates & Inflation F0 architecture doc into a live F1-F3 claim
(architecture section 10.6 gate) -- ``inflation_intelligence.v1`` is a
separate, already-built, already-on-disk engine output, not that doc.

AXIS IDS: ``axis_id`` is published natively as ``inflation_impulse`` /
``persistence_breadth`` per the orchestrator's contract ruling that the
shared schema's ``axis_id`` enum is being widened to a lowercase-snake-case
pattern in the integration pass -- no borrowed liquidity_regime wire ids.

DEVIATION NOTE (one remaining forced reuse, kept as-is for v1 -- see the R1A
report's "deviations" section): the shared closed schema's ``drivers`` object
still has two fixed keys (``rate_side`` / ``balance_sheet``), not
parameterized per workspace. This module repurposes them as "x-axis drivers"
/ "y-axis drivers" buckets for ``inflation_impulse`` / ``persistence_breadth``
respectively.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "inflation_system.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.inflation"

BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0

# Standardization scales. Each maps an owner-published percent/pp value onto a
# 0-100 half-axis swing centered on a disclosed anchor (never re-fit here;
# the anchor and scale are published verbatim in each axis's transformation
# string so a reader can reproduce the mapping by hand).
IMPULSE_CENTER_PCT = 2.0     # Fed's inflation objective (a policy constant, not a forecast)
IMPULSE_SCALE_PCT = 4.0      # +-4pp around 2% maps to the full 0-100 half-axis swing
SPREAD_SCALE_STICKY_PP = 6.0     # sticky-minus-flexible annualized spread scale
SPREAD_SCALE_ACCEL_PP = 2.0      # 3m-minus-6m acceleration spread scale
SPREAD_SCALE_COREHEAD_PP = 3.0   # core-minus-headline YoY gap scale

# Native axis ids (widened-contract pattern; see module docstring "AXIS IDS").
_AXIS_ID_X = "inflation_impulse"
_AXIS_ID_Y = "persistence_breadth"

_QUADRANTS = {
    "A": {"en": "Disinflating headline, broad/sticky underlying", "zh": "总体降温，但内部广泛/顽固"},
    "B": {"en": "Accelerating and broad-based", "zh": "加速且广泛"},
    "C": {"en": "Disinflating, narrow and transitory", "zh": "降温，狭窄且短暂"},
    "D": {"en": "Accelerating but narrow, possibly transitory", "zh": "加速但狭窄，可能短暂"},
}

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


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately NOT shared with liquidity_regime.py -- each
# domain composer reads only its own owner-native artifact per architecture
# 11.1; duplication here is intentional isolation, not oversight)
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


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _round(v: float | None, n: int = 2) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _pct_to_100(value: float | None, *, center: float, scale: float) -> float | None:
    """Map a %/pp value onto 0-100, centered at ``center`` with a +-``scale``
    half-axis swing. Pure algebra over one already-published owner scalar --
    never a re-derivation from raw series."""
    if value is None:
        return None
    return _clamp(50.0 + ((value - center) / scale) * 50.0, 0.0, 100.0)


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _owner_freshness(entry: Any) -> str:
    """Map the owner's own two-tier CPI/PCE freshness policy
    (``current_with_publication_lag`` | ``stale`` | ``unknown``) onto the
    closed contract vocabulary. Deliberately NEVER emits ``CURRENT``: CPI/PCE
    structurally lag their reference month by weeks even in the best case
    (PCE ~59d, CPI ~32bd -- inflation-specific clock-law note), and the owner
    engine's own policy (``engine.inflation_intelligence._monthly_freshness``)
    does not distinguish a same-month tier from a one-month-lagged tier, so
    this composer does not invent one either: it propagates exactly the
    owner's own classification rather than re-deriving a finer one."""
    if not isinstance(entry, Mapping) or entry.get("available") is not True:
        return "SOURCE_FAILED"
    status = entry.get("freshness_status")
    if status == "current_with_publication_lag":
        return "LATE_WITHIN_TOLERANCE"
    if status == "stale":
        return "STALE_SOURCE"
    return "SOURCE_FAILED"  # "unknown" or any other owner value fails closed


def _component(component_id, label_en, label_zh, owner_field, owner_ref, raw,
               standardized, sign, weight, freshness) -> dict:
    present = standardized is not None
    if not present:
        coverage_state = "ABSENT"
        null_reason = "SOURCE_FAILED" if freshness == "SOURCE_FAILED" else (
            "NOT_YET_RELEASED" if freshness == "NOT_YET_RELEASED" else "UNKNOWN")
    elif freshness == "STALE_SOURCE":
        coverage_state, null_reason = "PARTIAL", None
    else:
        coverage_state, null_reason = "PRESENT", None
    contribution = None if standardized is None else _round((standardized - BOUNDARY) * weight, 2)
    return {
        "component_id": component_id,
        "label": _bil(label_en, label_zh),
        "owner_field": owner_field,
        "owner_ref": owner_ref,
        "raw_value": raw,
        "standardized_value": _round(standardized, 2),
        "contribution": contribution,
        "sign": sign,
        "weight": weight,
        "coverage_state": coverage_state,
        "freshness": freshness,
        "null_reason": null_reason,
    }


def _axis_value(components: list[dict], min_components: int, coverage_floor: float):
    present = [c for c in components if c["standardized_value"] is not None]
    total = len(components)
    available = len(present)
    coverage = (available / total) if total else 0.0
    if available < min_components or coverage < coverage_floor:
        return None, "ABSENT", "COMPUTATION_REFUSED", available
    wsum = sum(c["weight"] for c in present)
    if wsum <= 0:
        return None, "ABSENT", "COMPUTATION_REFUSED", available
    value = sum(c["standardized_value"] * c["weight"] for c in present) / wsum
    status = "PRESENT" if available == total else "PARTIAL"
    return _round(_clamp(value, 0.0, 100.0), 2), status, None, available


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(inflation_intelligence: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project an ``inflation_intelligence.v1`` payload into an UNSEALED
    snapshot body. The builder seals it via ``contract.finalize``."""
    r = inflation_intelligence or {}
    asof = _get(r, "asof")
    released = _get(r, "released_state") or {}
    headline_e = _get(released, "headline") or {}
    core_e = _get(released, "core") or {}
    proxies = _get(released, "underlying_proxies") or {}
    sticky_e = _get(proxies, "sticky") or {}
    flexible_e = _get(proxies, "flexible") or {}
    next_release = _get(r, "next_release_forecast") or {}
    current_pressure = _get(r, "current_month_proxy_pressure") or {}
    core_pressure = _get(current_pressure, "core_model_pressure") or {}

    # ---- x axis: inflation impulse --------------------------------------- #
    core_ann3 = _num(core_e.get("annualized_3m_pct"))
    x1 = _component(
        "core_cpi_annualized_3m", "Core CPI, 3-month annualized", "核心CPI 3个月年化",
        "released_state.core.annualized_3m_pct", "engine.inflation_intelligence.released_state.core",
        core_ann3, _pct_to_100(core_ann3, center=IMPULSE_CENTER_PCT, scale=IMPULSE_SCALE_PCT),
        1, 0.35, _owner_freshness(core_e),
    )
    headline_ann3 = _num(headline_e.get("annualized_3m_pct"))
    x2 = _component(
        "headline_cpi_annualized_3m", "Headline CPI, 3-month annualized", "总体CPI 3个月年化",
        "released_state.headline.annualized_3m_pct", "engine.inflation_intelligence.released_state.headline",
        headline_ann3, _pct_to_100(headline_ann3, center=IMPULSE_CENTER_PCT, scale=IMPULSE_SCALE_PCT),
        1, 0.20, _owner_freshness(headline_e),
    )
    core_yoy = _num(core_e.get("yoy_pct"))
    x3 = _component(
        "core_cpi_yoy", "Core CPI, year-over-year", "核心CPI 同比",
        "released_state.core.yoy_pct", "engine.inflation_intelligence.released_state.core",
        core_yoy, _pct_to_100(core_yoy, center=IMPULSE_CENTER_PCT, scale=IMPULSE_SCALE_PCT),
        1, 0.20, _owner_freshness(core_e),
    )
    # In-progress-month nowcast: a single owner-published MoM% point,
    # compounded to an annualized rate by pure algebra (never a re-derivation
    # from raw series -- the point itself is the owner's own projection).
    nowcast_point = None
    nowcast_proj = core_pressure.get("release_radar_projection") if isinstance(core_pressure, Mapping) else None
    if isinstance(nowcast_proj, Mapping):
        nowcast_point = _num(nowcast_proj.get("point"))
    nowcast_ann = None
    if nowcast_point is not None:
        nowcast_ann = _round(((1.0 + nowcast_point / 100.0) ** 12 - 1.0) * 100.0, 4)
    nowcast_available = bool(core_pressure.get("available")) and nowcast_point is not None
    x4_freshness = "SIMULATED" if nowcast_available else "NOT_YET_RELEASED"
    x4 = _component(
        "current_month_core_nowcast_annualized", "Current-month core nowcast, annualized",
        "本月核心通胀模型预估（年化）",
        "current_month_proxy_pressure.core_model_pressure.release_radar_projection.point",
        "engine.inflation_intelligence.current_month_proxy_pressure",
        nowcast_point, _pct_to_100(nowcast_ann, center=IMPULSE_CENTER_PCT, scale=IMPULSE_SCALE_PCT)
        if nowcast_available else None,
        1, 0.25, x4_freshness,
    )
    x_components = [x1, x2, x3, x4]
    x_value, x_status, x_null, x_avail = _axis_value(x_components, min_components=2, coverage_floor=0.5)

    # ---- y axis: persistence / breadth ------------------------------------ #
    sticky_ann3 = _num(sticky_e.get("annualized_3m_pct"))
    flexible_ann3 = _num(flexible_e.get("annualized_3m_pct"))
    sticky_flex_spread = (
        _round(sticky_ann3 - flexible_ann3, 4) if sticky_ann3 is not None and flexible_ann3 is not None else None
    )
    y1 = _component(
        "sticky_flexible_spread", "Sticky minus flexible CPI, 3m annualized", "顽固-灵活CPI利差（3个月年化）",
        "released_state.underlying_proxies.{sticky,flexible}.annualized_3m_pct",
        "engine.inflation_intelligence.released_state.underlying_proxies",
        sticky_flex_spread, _pct_to_100(sticky_flex_spread, center=0.0, scale=SPREAD_SCALE_STICKY_PP),
        1, 0.35, _worst_freshness([_owner_freshness(sticky_e), _owner_freshness(flexible_e)]),
    )
    core_accel = _num(core_e.get("acceleration_3m_minus_6m_pp"))
    y2 = _component(
        "core_acceleration_3m_minus_6m", "Core CPI acceleration, 3m vs 6m", "核心CPI加速度（3个月对6个月）",
        "released_state.core.acceleration_3m_minus_6m_pp", "engine.inflation_intelligence.released_state.core",
        core_accel, _pct_to_100(core_accel, center=0.0, scale=SPREAD_SCALE_ACCEL_PP),
        1, 0.25, _owner_freshness(core_e),
    )
    sticky_accel = _num(sticky_e.get("acceleration_3m_minus_6m_pp"))
    y3 = _component(
        "sticky_acceleration_3m_minus_6m", "Sticky-price CPI acceleration, 3m vs 6m", "顽固价格CPI加速度（3个月对6个月）",
        "released_state.underlying_proxies.sticky.acceleration_3m_minus_6m_pp",
        "engine.inflation_intelligence.released_state.underlying_proxies.sticky",
        sticky_accel, _pct_to_100(sticky_accel, center=0.0, scale=SPREAD_SCALE_ACCEL_PP),
        1, 0.20, _owner_freshness(sticky_e),
    )
    core_head_gap = (
        _round(core_yoy - headline_e.get("yoy_pct"), 4)
        if core_yoy is not None and _num(headline_e.get("yoy_pct")) is not None else None
    )
    y4 = _component(
        "core_minus_headline_yoy_gap", "Core minus headline CPI, YoY gap", "核心-总体CPI同比缺口",
        "released_state.{core,headline}.yoy_pct", "engine.inflation_intelligence.released_state",
        core_head_gap, _pct_to_100(core_head_gap, center=0.0, scale=SPREAD_SCALE_COREHEAD_PP),
        1, 0.20, _worst_freshness([_owner_freshness(core_e), _owner_freshness(headline_e)]),
    )
    y_components = [y1, y2, y3, y4]
    y_value, y_status, y_null, y_avail = _axis_value(y_components, min_components=2, coverage_floor=0.5)

    # ---- contradiction: sticky-led breadth vs a disinflationary headline -- #
    proxy_mix_read = _get(current_pressure, "underlying_proxy_mix", "read")
    contradiction = _detect_contradiction(proxy_mix_read, x_value, x_status)

    if contradiction["present"]:
        affected_ids = set(contradiction["components"])
        y_ids = {c["component_id"] for c in y_components}
        x_ids = {c["component_id"] for c in x_components}
        if y_value is not None and affected_ids & y_ids:
            y_status = "DISAGREEMENT"
            for c in y_components:
                if c["component_id"] in affected_ids:
                    c["coverage_state"] = "DISAGREEMENT"
        if x_value is not None and affected_ids & x_ids:
            x_status = "DISAGREEMENT"
            for c in x_components:
                if c["component_id"] in affected_ids:
                    c["coverage_state"] = "DISAGREEMENT"

    # ---- freshness roll-up over the REQUIRED set -------------------------- #
    required_ids = ("core_cpi_annualized_3m", "headline_cpi_annualized_3m",
                     "sticky_flexible_spread", "core_acceleration_3m_minus_6m")
    by_id = {c["component_id"]: c for c in (x_components + y_components)}
    required_avail = _required_availability(by_id, required_ids, released)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_ids), 4)
    degraded = [c["component_id"] for c in required_avail if c["freshness"] not in ("LATE_WITHIN_TOLERANCE",)]
    reasons: list[str] = []
    if worst not in ("LATE_WITHIN_TOLERANCE",):
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    # ---- quadrant + hysteresis -------------------------------------------- #
    headline = _headline(x_value, x_status, x_null, y_value, y_status, y_null,
                         asof, prior_snapshot, contradiction)

    # ---- changes vs prior accepted print ----------------------------------- #
    changes = _changes(x_value, y_value, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "inflation_system",
            "title": _bil("Inflation System", "通胀体系"),
            "subtitle": _bil("Inflation impulse x persistence & breadth", "通胀冲量 × 持续性与广度"),
        },
        "region": {"code": "US", "supported": True, "display_name": "United States"},
        "generation": {
            "generation_id": "PENDING",
            "built_at": built_at,
            "rendered_at": None,
            "producer": PRODUCER,
            "code_version": code_version,
            "calculation_as_of": asof,
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
            "contradiction": contradiction,
            "reasons": reasons,
        },
        "headline": headline,
        "axes": {"items": [
            _axis(_AXIS_ID_X, "Inflation impulse", "通胀冲量",
                  "higher_more_inflationary", x_value, x_status, x_null, x_components, x_avail,
                  low_en="Disinflationary", low_zh="通缩/降温", high_en="Inflationary", high_zh="通胀/升温",
                  weights_law="weighted mean of standardized components, weights renormalized over present components; core CPI 3m ann. 0.35, headline CPI 3m ann. 0.20, core CPI YoY 0.20, current-month core nowcast (annualized) 0.25",
                  transformation=f"each %/pp value mapped 50+((v-{IMPULSE_CENTER_PCT})/{IMPULSE_SCALE_PCT})*50, clamped [0,100], centered on the Fed's 2% objective (a policy constant, not a forecast); the nowcast leg compounds one owner MoM point to an annualized rate via ((1+x/100)^12-1)*100 before the same mapping; no raw-series re-derivation",
                  frequency_alignment="CPI-family monthly release, ~1-2 calendar month publication lag per the owner's own freshness policy; the current-month nowcast leg is a distinct, faster (intra-month) clock, carried as SIMULATED never CURRENT"),
            _axis(_AXIS_ID_Y, "Persistence & breadth", "持续性与广度",
                  "higher_more_persistent_broad", y_value, y_status, y_null, y_components, y_avail,
                  low_en="Narrow / transitory", low_zh="狭窄/短暂", high_en="Broad / persistent", high_zh="广泛/顽固",
                  weights_law="weighted mean of standardized components, weights renormalized over present; sticky-minus-flexible 3m ann. spread 0.35, core 3m-vs-6m acceleration 0.25, sticky-price 3m-vs-6m acceleration 0.20, core-minus-headline YoY gap 0.20",
                  transformation=f"each spread/pp value mapped 50+(v/scale)*50 clamped [0,100] around a 0 center (scale={SPREAD_SCALE_STICKY_PP}pp for the sticky-flexible spread, {SPREAD_SCALE_ACCEL_PP}pp for the two acceleration legs, {SPREAD_SCALE_COREHEAD_PP}pp for the core-headline gap); every spread is an algebraic difference of two owner-published scalars, never a fresh parquet read",
                  frequency_alignment="same monthly CPI-family cadence and publication lag as the x-axis; all four legs share the owner's released_state clock"),
        ]},
        "metrics": {"items": _metrics(r, released, headline_e, core_e, sticky_e, flexible_e,
                                      next_release, current_pressure, x_value, y_value)},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(x_components, y_components),
        "changes": changes,
        "implications": {"items": _implications(headline, x_value, y_value, contradiction,
                                               worst, coverage_ratio, next_release)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(released, next_release)},
        "corrections": _corrections(headline_e, core_e, sticky_e, flexible_e, asof, prior_snapshot),
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
# sub-builders
# --------------------------------------------------------------------------- #
def _detect_contradiction(proxy_mix_read: Any, x_value: float | None, x_status: str) -> dict:
    """Sticky-led breadth vs a disinflationary headline impulse, surfaced as a
    typed DISAGREEMENT. If the categories that are hardest to reverse (sticky
    prices) are leading the pressure while the summary impulse reads calm,
    the "disinflating" headline read is not yet trustworthy support."""
    kind = None
    comps: list[str] = []
    if proxy_mix_read == "sticky_led" and x_value is not None and x_value < BOUNDARY and x_status != "ABSENT":
        kind = "sticky_led_but_headline_disinflationary"
        comps = ["sticky_flexible_spread", "sticky_acceleration_3m_minus_6m"]
    if kind is None:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    en = ("Sticky-price categories are leading the underlying price mix (sticky_led), but the "
          "headline inflation impulse currently reads disinflationary - the calm headline read "
          "is not yet corroborated by the harder-to-reverse component of the basket.")
    zh = "顽固价格类别正在主导潜在价格结构（sticky_led），但总体通胀冲量目前读数为通缩/降温——这一平静的总体读数尚未得到篮子中更难逆转部分的印证。"
    return {"present": True, "kind": kind, "en": en, "zh": zh, "components": comps}


def _required_availability(by_id, required_ids, released) -> list[dict]:
    labels = {
        "core_cpi_annualized_3m": ("Core CPI, 3-month annualized", "核心CPI 3个月年化"),
        "headline_cpi_annualized_3m": ("Headline CPI, 3-month annualized", "总体CPI 3个月年化"),
        "sticky_flexible_spread": ("Sticky minus flexible CPI spread", "顽固-灵活CPI利差"),
        "core_acceleration_3m_minus_6m": ("Core CPI acceleration, 3m vs 6m", "核心CPI加速度（3个月对6个月）"),
    }
    core_e = _get(released, "core") or {}
    headline_e = _get(released, "headline") or {}
    proxies = _get(released, "underlying_proxies") or {}
    src_period = {
        "core_cpi_annualized_3m": core_e.get("observation_period"),
        "headline_cpi_annualized_3m": headline_e.get("observation_period"),
        "sticky_flexible_spread": _get(proxies, "sticky", "observation_period"),
        "core_acceleration_3m_minus_6m": core_e.get("observation_period"),
    }
    out = []
    for cid in required_ids:
        comp = by_id.get(cid, {})
        present = comp.get("standardized_value") is not None
        fresh = comp.get("freshness", "SOURCE_FAILED")
        status = "PRESENT" if present and fresh in ("LATE_WITHIN_TOLERANCE",) else (
            "PARTIAL" if present else "ABSENT")
        en, zh = labels[cid]
        out.append({
            "component_id": cid,
            "label": _bil(en, zh),
            "required": True,
            "freshness": fresh,
            "status": status,
            "source_asof": src_period.get(cid),
            "null_reason": comp.get("null_reason") if not present else None,
        })
    return out


def _classify(x: float, y: float) -> str:
    """Domain-agnostic quadrant math -- identical shape to liquidity_regime's
    own classifier, only the labels attached to A/B/C/D differ per domain."""
    accelerating = x >= BOUNDARY
    persistent_broad = y >= BOUNDARY
    if not accelerating and persistent_broad:
        return "A"
    if accelerating and persistent_broad:
        return "B"
    if not accelerating and not persistent_broad:
        return "C"
    return "D"


def _headline(x_value, x_status, x_null, y_value, y_status, y_null, asof,
              prior_snapshot, contradiction) -> dict:
    computable = x_value is not None and y_value is not None
    prior_id = _get(prior_snapshot, "headline", "state_id")
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_x = _get(prior_snapshot, "headline", "quadrant", "x")
    prior_y = _get(prior_snapshot, "headline", "quadrant", "y")
    comparable_prior = prior_id in ("A", "B", "C", "D") and prior_method == METHOD_VERSION

    state_id = None
    held_prior = False
    applied = False
    crossed_axes: list[str] = []
    if computable:
        raw = _classify(x_value, y_value)
        state_id = raw
        if comparable_prior:
            applied = True
            if raw != prior_id:
                prior_x_num = prior_x if isinstance(prior_x, (int, float)) else None
                prior_y_num = prior_y if isinstance(prior_y, (int, float)) else None
                if prior_x_num is not None and prior_y_num is not None:
                    if (x_value >= BOUNDARY) != (prior_x_num >= BOUNDARY):
                        crossed_axes.append("inflation_impulse")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("persistence_breadth")
                    within_band = {
                        "inflation_impulse": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "persistence_breadth": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
                    }
                    if all(within_band[a] for a in crossed_axes):
                        state_id = prior_id
                        held_prior = True

    if state_id is not None:
        label = _QUADRANTS[state_id]
        state_label = {"en": label["en"], "zh": label["zh"]}
        status = "PRESENT"
        null_reason = None
    else:
        state_label = {"en": None, "zh": None}
        status = "ABSENT"
        null_reason = x_null or y_null or "COMPUTATION_REFUSED"

    if computable:
        dx = abs(x_value - BOUNDARY)
        dy = abs(y_value - BOUNDARY)
        near_axis = "inflation_impulse" if dx <= dy else "persistence_breadth"
        near_dist = round(min(dx, dy), 2)
        nb_null = None
    else:
        near_axis, near_dist, nb_null = None, None, "COMPUTATION_REFUSED"

    if computable and comparable_prior and isinstance(prior_x, (int, float)) and isinstance(prior_y, (int, float)):
        vec = {"dx": round(x_value - prior_x, 2), "dy": round(y_value - prior_y, 2),
               "status": "PRESENT", "null_reason": None}
        transition_distance = round(((x_value - prior_x) ** 2 + (y_value - prior_y) ** 2) ** 0.5, 2)
    else:
        if prior_snapshot is None:
            vec_null = "WARMUP"
        elif prior_method != METHOD_VERSION:
            vec_null = "COMPUTATION_REFUSED"
        else:
            vec_null = "INSUFFICIENT_HISTORY"
        vec = {"dx": None, "dy": None, "status": "ABSENT", "null_reason": vec_null}
        transition_distance = None

    if not applied:
        note = "no comparable prior print; raw threshold classification, hysteresis not applied"
    elif not held_prior and state_id == prior_id:
        note = "raw classification already matches the prior print; no boundary crossing, hysteresis not engaged"
    elif held_prior:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "no axis"
        note = (f"prior quadrant held: {crossed_txt} crossed the 50 boundary since the prior "
                f"print but stayed within the {HYSTERESIS_BAND}-pt hysteresis band of ITS OWN boundary")
    else:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "the classification"
        note = (f"prior quadrant not held: {crossed_txt} crossed the 50 boundary and moved beyond "
                f"the {HYSTERESIS_BAND}-pt hysteresis band, so the transition to the raw quadrant is accepted")

    return {
        "state_id": state_id,
        "state_label": state_label,
        "subtitle": _bil("Inflation regime", "通胀体制"),
        "method_version": METHOD_VERSION,
        "effective_date": asof,
        "quadrant": {"x": x_value, "y": y_value, "x_status": x_status, "y_status": y_status},
        "prior_state": {
            "state_id": prior_id if prior_id in ("A", "B", "C", "D") else None,
            "effective_date": _get(prior_snapshot, "headline", "effective_date"),
            "method_version": prior_method,
        },
        "transition_distance": transition_distance,
        "nearest_boundary": {"axis": near_axis, "distance": near_dist, "null_reason": nb_null},
        "one_month_vector": vec,
        "hysteresis": {"band": HYSTERESIS_BAND, "applied": applied, "held_prior": held_prior, "note": note},
        "status": status,
        "null_reason": null_reason,
    }


def _changes(x_value, y_value, prior_snapshot) -> dict:
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
    prior_x = _get(prior_snapshot, "headline", "quadrant", "x")
    prior_y = _get(prior_snapshot, "headline", "quadrant", "y")
    deltas = []
    for mid, cur, prev in (("inflation_impulse", x_value, prior_x),
                          ("persistence_breadth", y_value, prior_y)):
        delta = None
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            delta = round(cur - prev, 2)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _axis(axis_id, label_en, label_zh, direction, value, value_status, null_reason,
          components, components_available, *, low_en, low_zh, high_en, high_zh,
          weights_law, transformation, frequency_alignment) -> dict:
    fresh = _worst_freshness([c["freshness"] for c in components]) if components else "SOURCE_FAILED"
    return {
        "axis_id": axis_id,
        "label": _bil(label_en, label_zh),
        "direction_semantics": direction,
        "value": value,
        "value_status": value_status,
        "null_reason": null_reason,
        "components": components,
        "weights_law": weights_law,
        "transformation": transformation,
        "min_components": 2,
        "coverage_floor": 0.5,
        "components_available": components_available,
        "frequency_alignment": frequency_alignment,
        "thresholds": {
            "boundary": BOUNDARY,
            "hysteresis_band": HYSTERESIS_BAND,
            "low_label": _bil(low_en, low_zh),
            "high_label": _bil(high_en, high_zh),
        },
        "definition_version": DEFINITION_VERSION,
        "data_version": None,
        "revision_behavior": "recomputed each owner cadence from prior-only owner reads; a method-version change breaks comparability and is reported as such, never as a numeric delta",
        "authority_ceiling": "DESCRIPTIVE",
        "freshness": fresh,
    }


def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, released_at=None,
            calculation_as_of=None, source_refs=None, transformation=None,
            status="PRESENT", null_reason=None) -> dict:
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
        "released_at": released_at,
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
        "rights_state": "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metrics(r, released, headline_e, core_e, sticky_e, flexible_e,
             next_release, current_pressure, x_value, y_value) -> list[dict]:
    items = [
        _metric("inflation_impulse", x_value, "score_0_100", "score", "composite_prior_only",
                "higher_more_inflationary", PRODUCER, "axes.inflation_impulse",
                _get(r, "asof"), "LATE_WITHIN_TOLERANCE" if x_value is not None else "SOURCE_FAILED",
                transformation="weighted-mean composite; see axes[inflation_impulse]"),
        _metric("persistence_breadth", y_value, "score_0_100", "score", "composite_prior_only",
                "higher_more_persistent_broad", PRODUCER, "axes.persistence_breadth",
                _get(r, "asof"), "LATE_WITHIN_TOLERANCE" if y_value is not None else "SOURCE_FAILED",
                transformation="weighted-mean composite; see axes[persistence_breadth]"),
        _metric("headline_cpi_yoy_pct", _num(headline_e.get("yoy_pct")), "percent", "pct_yoy",
                "seasonally_adjusted_not_original_vintage", "higher_more_inflationary",
                "engine.inflation_intelligence.released_state.headline", "released_state.headline.yoy_pct",
                headline_e.get("observation_period"), _owner_freshness(headline_e)),
        _metric("headline_cpi_mom_pct", _num(headline_e.get("mom_pct")), "percent", "pct_mom",
                "seasonally_adjusted_not_original_vintage", "higher_more_inflationary",
                "engine.inflation_intelligence.released_state.headline", "released_state.headline.mom_pct",
                headline_e.get("observation_period"), _owner_freshness(headline_e)),
        _metric("core_cpi_yoy_pct", _num(core_e.get("yoy_pct")), "percent", "pct_yoy",
                "seasonally_adjusted_not_original_vintage", "higher_more_inflationary",
                "engine.inflation_intelligence.released_state.core", "released_state.core.yoy_pct",
                core_e.get("observation_period"), _owner_freshness(core_e)),
        _metric("core_cpi_mom_pct", _num(core_e.get("mom_pct")), "percent", "pct_mom",
                "seasonally_adjusted_not_original_vintage", "higher_more_inflationary",
                "engine.inflation_intelligence.released_state.core", "released_state.core.mom_pct",
                core_e.get("observation_period"), _owner_freshness(core_e)),
        _metric("core_cpi_annualized_6m_pct", _num(core_e.get("annualized_6m_pct")), "percent", "pct_saar",
                "seasonally_adjusted_not_original_vintage", "higher_more_inflationary",
                "engine.inflation_intelligence.released_state.core", "released_state.core.annualized_6m_pct",
                core_e.get("observation_period"), _owner_freshness(core_e)),
        _metric("sticky_cpi_annualized_3m_pct", _num(sticky_e.get("annualized_3m_pct")), "percent", "pct_saar",
                "monthly_proxy_series", "higher_more_persistent",
                "engine.inflation_intelligence.released_state.underlying_proxies.sticky",
                "released_state.underlying_proxies.sticky.annualized_3m_pct",
                sticky_e.get("observation_period"), _owner_freshness(sticky_e)),
        _metric("flexible_cpi_annualized_3m_pct", _num(flexible_e.get("annualized_3m_pct")), "percent", "pct_saar",
                "monthly_proxy_series", "higher_more_transitory",
                "engine.inflation_intelligence.released_state.underlying_proxies.flexible",
                "released_state.underlying_proxies.flexible.annualized_3m_pct",
                flexible_e.get("observation_period"), _owner_freshness(flexible_e)),
    ]
    # Forward calendar / forecast metrics: distinct clocks -- calculation_as_of
    # is the model's cutoff, released_at stays null (not yet released), and
    # freshness is SIMULATED (a model projection, never an observation).
    core_next = _get(next_release, "core") or {}
    proj = core_next.get("release_radar_projection") if isinstance(core_next.get("release_radar_projection"), Mapping) else None
    proj_point = _num(proj.get("point")) if isinstance(proj, Mapping) else None
    items.append(_metric(
        "next_cpi_core_release_projection_mom_pct", proj_point, "percent", "pct_mom_sa",
        "release_radar_champion_projection", "higher_more_inflationary",
        PRODUCER,
        "next_release_forecast.core.release_radar_projection.point",
        core_next.get("period"), "SIMULATED" if proj_point is not None else "NOT_YET_RELEASED",
        released_at=None, calculation_as_of=core_next.get("forecast_asof"),
        status="PRESENT" if proj_point is not None else "ABSENT",
        null_reason=None if proj_point is not None else "NOT_YET_RELEASED",
    ))
    release_date = core_next.get("release_date")
    items.append(_metric(
        "next_cpi_release_date", release_date, "categorical", None, "bls_calendar",
        None, PRODUCER, "next_release_forecast.core.release_date",
        core_next.get("period"), "CURRENT" if release_date is not None else "SOURCE_FAILED",
        released_at=None, calculation_as_of=_get(r, "asof"),
        status="PRESENT" if release_date is not None else "ABSENT",
        null_reason=None if release_date is not None else "UNKNOWN",
    ))
    pressure_dir = _get(current_pressure, "pressure_direction")
    items.append(_metric(
        "current_month_pressure_direction", pressure_dir, "categorical", None, "model_nowcast",
        "higher_more_inflationary", PRODUCER, "current_month_proxy_pressure.pressure_direction",
        _get(current_pressure, "period"), "SIMULATED" if pressure_dir is not None else "NOT_YET_RELEASED",
        released_at=None, calculation_as_of=_get(r, "asof"),
        status="PRESENT" if pressure_dir is not None else "ABSENT",
        null_reason=None if pressure_dir is not None else "NOT_YET_RELEASED",
    ))
    return items


def _drivers(x_components, y_components) -> dict:
    """Populates the shared contract's two CLOSED driver-bucket keys
    (``rate_side`` / ``balance_sheet`` -- see module docstring DEVIATION
    NOTE): here they hold the x-axis (inflation impulse) and y-axis
    (persistence/breadth) driver tables respectively."""
    def _to_driver(c, unit):
        contrib = c["contribution"]
        sign = 0 if contrib is None else (1 if contrib > 0 else (-1 if contrib < 0 else 0))
        note = f"signed push = (standardized-50)*weight toward the axis high side; standardized={c['standardized_value']}, weight={c['weight']}"
        return {
            "driver_id": c["component_id"],
            "label": c["label"],
            "owner_field": c["owner_field"],
            "value": c["raw_value"],
            "unit": unit,
            "impact_sign": sign,
            "impact_magnitude": None if contrib is None else abs(contrib),
            "note": note,
            "coverage_state": c["coverage_state"],
        }
    rate_side = [_to_driver(c, u) for c, u in zip(
        x_components, ["pct_saar", "pct_saar", "pct_yoy", "pct_saar"])]
    balance_sheet = [_to_driver(c, u) for c, u in zip(
        y_components, ["pp_spread", "pp", "pp", "pp"])]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _implications(headline, x_value, y_value, contradiction, worst_freshness,
                  coverage_ratio, next_release) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "LATE_WITHIN_TOLERANCE" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH",
        "evidence_breadth": "MEDIUM",
        "contradiction_state": "PRESENT" if contradiction["present"] else "ABSENT",
    }
    items: list[dict] = []
    state_id = headline["state_id"]
    if state_id is not None:
        label_en = _QUADRANTS[state_id]["en"]
        label_zh = _QUADRANTS[state_id]["zh"]
        items.append({
            "implication_id": "state_descriptive",
            "text": _bil(
                f"US inflation regime reads {state_id} - {label_en} (impulse x={x_value}, "
                f"persistence/breadth y={y_value}, boundary 50).",
                f"美国通胀体制读数为 {state_id} - {label_zh}（冲量 x={x_value}，持续性/广度 y={y_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["prices", "expectations", "wages"],
            "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
            "trace_ref": "data/release_forecast/inflation_intelligence.json#released_state",
        })
    else:
        items.append({
            "implication_id": "state_unavailable",
            "text": _bil(
                "US inflation regime cannot be classified: axis coverage is below the disclosed floor. "
                "No quadrant is asserted rather than defaulting to a neutral state.",
                "美国通胀体制无法分类：轴覆盖低于披露下限。不默认中性状态，故不给出象限。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["prices", "expectations", "wages"],
            "contradictions": [],
            "trace_ref": "data/release_forecast/inflation_intelligence.json#released_state",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": "sticky_led_headline_disinflation_contradiction",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["prices", "expectations"],
            "contradictions": [contradiction["kind"]],
            "trace_ref": "data/release_forecast/inflation_intelligence.json#current_month_proxy_pressure.underlying_proxy_mix",
        })
    release_date = _get(next_release, "core", "release_date") or _get(next_release, "headline", "release_date")
    if release_date is not None:
        items.append({
            "implication_id": "next_release_calendar_note",
            "text": _bil(
                f"Next CPI print is scheduled {release_date}; the displayed forward path is the "
                "Release Radar champion projection, a model estimate, not an official observation.",
                f"下一次CPI数据预计于 {release_date} 公布；显示的前瞻路径为Release Radar冠军模型的预测，"
                "属于模型估计，并非官方观测值。"),
            "evidence_class": "MODEL_HYPOTHESIS",
            "confidence": conf,
            "horizon": "weeks",
            "channels": ["prices"],
            "contradictions": [],
            "trace_ref": "data/release_forecast/inflation_intelligence.json#next_release_forecast",
        })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "shelter_mom_shock_pp", "label": _bil("Shelter MoM shock", "住房环比冲击"),
             "unit": "pp", "step": 0.05, "min": -1.0, "max": 1.0,
             "owner_field": "current_month_proxy_pressure.headline_model_pressure.component_freshness[component=shelter]"},
            {"assumption_id": "energy_mom_shock_pct", "label": _bil("Energy MoM shock", "能源环比冲击"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0,
             "owner_field": "current_month_proxy_pressure.headline_model_pressure.component_freshness[component=energy_gasoline]"},
            {"assumption_id": "core_services_mom_shock_pp", "label": _bil("Core services ex-shelter MoM shock", "核心服务（不含住房）环比冲击"),
             "unit": "pp", "step": 0.05, "min": -1.0, "max": 1.0,
             "owner_field": "current_month_proxy_pressure.headline_model_pressure.component_freshness[component=core_services_ex_shelter]"},
            {"assumption_id": "wage_growth_shock_pp", "label": _bil("Wage growth shock", "工资增长冲击"),
             "unit": "pp", "step": 0.1, "min": -3.0, "max": 3.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; this packet ships no scenario execution endpoint (non-goal). A future owner-native pure scenario function produces mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "quadrant_transition", "kind": "state_transition",
             "label": _bil("Regime change", "体制变化"), "params": ["target_quadrant"]},
            {"condition_id": "boundary_approach", "kind": "boundary_approach",
             "label": _bil("Boundary approach", "接近分界"), "params": ["axis", "distance"]},
            {"condition_id": "component_shock", "kind": "component_shock",
             "label": _bil("Component shock", "分项冲击"), "params": ["component_id", "z"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
            {"condition_id": "release_approaching", "kind": "release_approaching",
             "label": _bil("CPI release approaching", "CPI数据即将公布"), "params": ["release_type", "release_date"]},
            {"condition_id": "contradiction_change", "kind": "contradiction_change",
             "label": _bil("Contradiction appeared or resolved", "矛盾出现或消解"), "params": ["kind"]},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; this packet writes no alert (non-goal). Alerts extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service can create/list/evaluate/delete these real conditions.",
    }


_SOURCE_COMPONENT_MAP: dict[str, tuple[str, ...]] = {
    "cpi_headline_core": ("headline_cpi_yoy_pct", "headline_cpi_mom_pct", "core_cpi_yoy_pct", "core_cpi_mom_pct"),
    "cpi_sticky_flexible_proxies": ("sticky_cpi_annualized_3m_pct", "flexible_cpi_annualized_3m_pct"),
}


def _raw_snapshot_values(headline_e, core_e, sticky_e, flexible_e) -> dict:
    return {
        "headline_cpi_yoy_pct": headline_e.get("yoy_pct"),
        "headline_cpi_mom_pct": headline_e.get("mom_pct"),
        "core_cpi_yoy_pct": core_e.get("yoy_pct"),
        "core_cpi_mom_pct": core_e.get("mom_pct"),
        "sticky_cpi_annualized_3m_pct": sticky_e.get("annualized_3m_pct"),
        "flexible_cpi_annualized_3m_pct": flexible_e.get("annualized_3m_pct"),
    }


def _prior_metric_value(prior_snapshot, metric_id):
    for m in (_get(prior_snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _corrections(headline_e, core_e, sticky_e, flexible_e, asof, prior_snapshot) -> dict:
    """Same scoped, honest supersession-detection shape as liquidity_regime's
    ``_corrections``: a same-reference-period print whose owner-native values
    moved is a revision, a new reference period is simply a new print."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {
            "predecessor_generation_id": None,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists.",
        }
    prior_asof = _get(prior_snapshot, "headline", "effective_date")
    if prior_asof != asof:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": [],
            "correction_state": "none",
            "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted.",
        }
    current_raw = _raw_snapshot_values(headline_e, core_e, sticky_e, flexible_e)
    changed: list[str] = []
    for source_id, metric_ids in _SOURCE_COMPONENT_MAP.items():
        for mid in metric_ids:
            cur = current_raw.get(mid)
            prev = _prior_metric_value(prior_snapshot, mid)
            if cur != prev:
                digest16 = sha256(f"{source_id}:{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
                changed.append(f"{source_id}:{mid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native source values changed: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen,
        "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no source value changed (no-change republication).",
    }


def _sources(released, next_release) -> list[dict]:
    headline_e = _get(released, "headline") or {}
    core_e = _get(released, "core") or {}
    proxies = _get(released, "underlying_proxies") or {}
    sticky_e = _get(proxies, "sticky") or {}
    return [
        {
            "source_id": "cpi_headline_core",
            "label": _bil("CPI-U headline & core (index levels)", "CPI-U 总体与核心（指数水平）"),
            "owner_ref": "engine.inflation_intelligence.released_state",
            "provider": "BLS CPI-U via FRED (CPIAUCSL / CPILFESL)",
            "reference_period": headline_e.get("observation_period") or core_e.get("observation_period"),
            "released_at": None,
            "first_known_at": None,
            "collected_at": None,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": "mom_pct / yoy_pct / annualized_3m_pct / annualized_6m_pct computed by the owner engine from monthly index levels; latest-local-vintage, not original-release vintage",
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": None,
            "artifact_ref": "data/release_forecast/inflation_intelligence.json",
            "freshness": _owner_freshness(headline_e),
        },
        {
            "source_id": "cpi_sticky_flexible_proxies",
            "label": _bil("Sticky- & flexible-price CPI proxies", "顽固价格与灵活价格CPI代理指标"),
            "owner_ref": "engine.inflation_intelligence.released_state.underlying_proxies",
            "provider": "Atlanta Fed sticky/flexible CPI via FRED (STICKCPIM157SFRBATL / FLEXCPIM157SFRBATL)",
            "reference_period": sticky_e.get("observation_period"),
            "released_at": None,
            "first_known_at": None,
            "collected_at": None,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": "monthly_pct / annualized_3m_pct / annualized_6m_pct computed by the owner engine",
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": None,
            "artifact_ref": "data/release_forecast/inflation_intelligence.json",
            "freshness": _owner_freshness(sticky_e),
        },
        {
            "source_id": "release_radar_forecast",
            "label": _bil("Release Radar CPI forward path", "Release Radar CPI前瞻路径"),
            "owner_ref": "engine.inflation_intelligence.next_release_forecast",
            "provider": "Mastermind Release Radar (champion projection + Cleveland Fed nowcast benchmark)",
            "reference_period": _get(next_release, "core", "period") or _get(next_release, "headline", "period"),
            "released_at": None,
            "first_known_at": None,
            "collected_at": None,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": "display_only champion-path projection with a Cleveland-benchmark-augmented combined estimate; not a street-consensus comparison",
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": None,
            "artifact_ref": "data/release_forecast/inflation_intelligence.json",
            "freshness": "SIMULATED" if _get(next_release, "available") else "NOT_YET_RELEASED",
        },
    ]
