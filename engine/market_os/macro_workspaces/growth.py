"""Pure composer for the US ``growth_real_economy`` workspace snapshot (F01 / R2).

Reads owner-native artifacts (canonically ``data/regime/latest.json``, the same
canonical regime read used by ``liquidity_regime.py``) and projects them into a
``mastermind.macro_workspace_snapshot.v1`` body. Mirrors the R1A
``liquidity_regime`` composer's structure and typed-degradation discipline:

* builds a dual-axis quadrant state
    x = growth momentum      (deteriorating -> accelerating)
    y = growth level/breadth (weak -> strong)
  with four descriptive quadrants A/B/C/D and disclosed hysteresis, mirroring
  architecture 10.2's headline model;
* preserves the Leading -> Coincident -> Lagging SEQUENCE separately (never
  averaged into the headline composite) as individually-clocked metrics --
  only leading+coincident momentum/breadth feed the x/y composite; lagging is
  published purely as trailing confirmation context (architecture 10.2: "A
  secondary sequence view preserves Leading -> Coincident -> Lagging rather
  than averaging the tiers into one scalar");
* publishes full composite-law disclosure (component list, signs, weights,
  coverage floor, thresholds, definition/data versions, revision behaviour --
  section 7.9) for the two composites as real ``axes.items`` entries,
  ``axis_id`` = ``growth_momentum`` / ``growth_level_breadth`` (the shared
  schema's axis_id enum has been widened by the orchestrator's integration
  pass beyond the original two liquidity_regime values); the same
  composite-level summary is ALSO carried in
  ``metrics[growth_momentum]/[growth_level_breadth].transformation`` so a
  metrics-only reader gets it too;
* emits a typed nowcast-vs-hard-data DISAGREEMENT when GDPNow signals strong
  acceleration while the coincident hard-data tier is still trending down
  (architecture 10.2: "nowcast versus hard-data disagreement" is REQUIRED
  composition; "nowcast/hard-data contradiction" is a named failure state),
  and a second typed DISAGREEMENT when the coincident index level reads
  strong while its diffusion (breadth) is narrow;
* emits TYPED degraded states, never zero/neutral/calm:
    - a required source missing              -> SOURCE_FAILED
    - the whole business_cycle owner offline  -> SOURCE_FAILED
    - the owner artifact flagged stale        -> STALE_SOURCE
    - axis coverage below the floor           -> value null + COMPUTATION_REFUSED
    - no comparable prior print               -> vector/changes WARMUP
    - prior print on a different method       -> changes METHOD_CHANGED (refuses deltas)
    - stale/uncalibrated business-cycle model -> a descriptive caveat implication
      (architecture 10.2 failure state: "recession label unsupported by the
      accepted calibration")

SCHEMA KEY LAW (read before touching this file): the ``drivers`` block is
closed to exactly the keys ``rate_side`` / ``balance_sheet`` -- names
inherited from the ``liquidity_regime`` workspace and left as-is for v1 (the
buckets themselves are not being widened/renamed in this pass). This
composer publishes growth-momentum drivers under ``rate_side`` and
growth-level/breadth drivers under ``balance_sheet`` -- semantically
repurposed, not renamed, with an explicit one-line disclosure baked into
every driver's own ``note`` field so a reader of the driver object itself is
never misled.

``axes.items[*].components`` reuses the SAME component dicts (built by
:func:`_component`) that feed the x/y composite math, so a fired contradiction
mutates ``coverage_state``/``value_status`` in place before the axis object is
constructed -- the axis-level DISAGREEMENT and the composite metric's
DISAGREEMENT always agree, they are two views of the same underlying state.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library. The composer NEVER reads
a wall clock: ``built_at`` and any evaluation clock are passed in by the
builder, and freshness is derived from owner-provided flags, so an identical
owner input always yields an identical snapshot body.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "growth_real_economy.compose.v1"
AXIS_DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.growth"

BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0

# Standardization scale constants (modeling assumptions, disclosed in each
# composite metric's transformation text): center = the value mapped to a
# neutral 50, scale = the +/- distance from center mapped to a full 0/100
# swing (clamped beyond that).
GDPNOW_CENTER, GDPNOW_SCALE = 2.0, 4.0      # ~trend real GDP growth ~2% SAAR
WEI_CENTER, WEI_SCALE = 1.5, 4.0            # WEI's long-run average growth read
TIER_MOM6_CENTER, TIER_MOM6_SCALE = 0.0, 2.0
GROWTH_AXIS_SCORE_CENTER, GROWTH_AXIS_SCORE_SCALE = 0.0, 1.0  # engine/axes.py growth_score is ~zero-centered

# Contradiction thresholds (modeling assumptions, disclosed in the
# contradiction's own text).
NOWCAST_ACCEL_THRESHOLD = 65.0     # gdpnow standardized >= this = "strongly accelerating"
INDEX_STRONG_THRESHOLD = 65.0      # coincident index standardized >= this = "strong level"
DIFFUSION_NARROW_THRESHOLD = 35.0  # coincident diffusion standardized <= this = "narrow breadth"

# A business-cycle calibration older than this is flagged as a descriptive
# caveat (architecture 10.2 failure state: "recession label unsupported by
# the accepted calibration").
CALIBRATION_STALE_DAYS = 365

# Quadrant labels (architecture 10.2 dual-axis headline model).
_QUADRANTS = {
    "A": {"en": "Decelerating momentum, still broad strength", "zh": "动能减速，广度仍强"},
    "B": {"en": "Accelerating momentum, broad strength", "zh": "动能加速，广度强劲"},
    "C": {"en": "Decelerating momentum, narrow/weak breadth", "zh": "动能减速，广度狭窄疲软"},
    "D": {"en": "Accelerating momentum, narrow/weak breadth", "zh": "动能加速，广度狭窄疲软"},
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
# small pure helpers (mirrors liquidity_regime.py's generic helpers exactly)
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


def _center_scale_to_100(v: float | None, center: float, scale: float) -> float | None:
    if v is None:
        return None
    return _clamp(50.0 + ((v - center) / scale) * 50.0, 0.0, 100.0)


def _pct_clamp_0_100(v: float | None) -> float | None:
    return None if v is None else _clamp(v, 0.0, 100.0)


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _nowcast_freshness(value_present: bool, artifact_stale: bool) -> str:
    """Freshness for fields with no owner-native per-source vintage tracking
    (growth_nowcast, growth_score, recession, labor_nowcast all lack the
    per-source ``vintages``/``stale_inputs`` structure that liquidity_quality
    has): fall back to the whole-artifact ``freshness.stale`` flag."""
    if not value_present:
        return "SOURCE_FAILED"
    return "STALE_SOURCE" if artifact_stale else "CURRENT"


def _gate_unavailable(v: Any, bc_available: Any) -> Any:
    """Null a business_cycle-tier-sourced raw value when the owner itself
    reports ``available: false`` -- keeps value-presence and freshness in
    lockstep so a populated-but-untrusted number can never read PRESENT
    while its freshness says SOURCE_FAILED."""
    return None if bc_available is False else v


def _cycle_freshness(value_present: bool, bc_available: Any, artifact_stale: bool) -> str:
    """Same fallback as :func:`_nowcast_freshness`, additionally gated on the
    owner's own ``business_cycle.available`` flag: if the tier engine itself
    is reported offline, every tier-derived value is SOURCE_FAILED regardless
    of whether a (now-stale) prior value is still sitting in the artifact."""
    if not value_present:
        return "SOURCE_FAILED"
    if bc_available is False:
        return "SOURCE_FAILED"
    return "STALE_SOURCE" if artifact_stale else "CURRENT"


def _bil(en: str | None, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


# --------------------------------------------------------------------------- #
# component construction (generic; identical shape to liquidity_regime.py)
# --------------------------------------------------------------------------- #
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


def _composite_value(components: list[dict], min_components: int, coverage_floor: float):
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


def _axis(axis_id, label_en, label_zh, direction, value, value_status, null_reason,
          components, components_available, *, low_en, low_zh, high_en, high_zh,
          weights_law, transformation, frequency_alignment, data_version) -> dict:
    """Full R1A axis-object shape (identical keys to liquidity_regime.py's
    ``_axis()``) -- section 7.9 composite disclosure lives here as the
    PRIMARY home now that the shared schema's axis_id enum is widened to
    accept lowercase-snake-case ids beyond the original two liquidity_regime
    values. ``components`` is passed the SAME component dicts used to
    compute the composite (built by :func:`_component`), so any in-place
    DISAGREEMENT mutation applied to them by the caller (see the
    contradiction-handling block in :func:`compose`) is carried through
    automatically -- the axis object is built from those components AFTER
    that mutation runs."""
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
        "definition_version": AXIS_DEFINITION_VERSION,
        "data_version": data_version,
        "revision_behavior": "recomputed each owner cadence from prior-only owner reads; a method-version change breaks comparability and is reported as such, never as a numeric delta",
        "authority_ceiling": "DESCRIPTIVE",
        "freshness": fresh,
    }


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(regime_latest: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``regime_latest`` into an UNSEALED snapshot body. The builder
    seals it via ``contract.finalize`` (content_sha256 + generation_id)."""
    r = regime_latest or {}
    asof = _get(r, "asof") or _get(r, "date")
    cond = _get(r, "conditions") or {}
    growth_nowcast = _get(cond, "growth_nowcast") or {}
    recession = _get(cond, "recession") or {}
    labor_nowcast = _get(cond, "labor_nowcast") or {}
    bc = _get(r, "business_cycle") or {}
    bc_available = bc.get("available") if isinstance(bc, Mapping) else None
    bc_asof = _get(bc, "asof") or asof
    tiers = _get(bc, "tiers") or {}
    leading = _get(tiers, "leading") or {}
    coincident = _get(tiers, "coincident") or {}
    lagging = _get(tiers, "lagging") or {}
    calibration = _get(bc, "calibration_resolution") or {}
    bc_calibration_version = calibration.get("calibration_version") if isinstance(calibration, Mapping) else None
    artifact_freshness = _get(r, "freshness") or {}
    artifact_stale = bool(artifact_freshness.get("stale")) if isinstance(artifact_freshness, Mapping) else False

    gdpnow_raw = _num(_get(growth_nowcast, "gdpnow"))
    wei_raw = _num(_get(growth_nowcast, "wei"))
    # business_cycle.available == False means the tier engine itself is
    # reported offline: null the tier-derived raw values out here (not just
    # their freshness label) so presence/status/null_reason stay consistent
    # everywhere downstream -- _component()/_metric() key off value-presence,
    # not freshness, so a populated-but-untrusted number would otherwise
    # still read PRESENT despite freshness saying SOURCE_FAILED.
    leading_mom6_raw = _gate_unavailable(_num(_get(leading, "mom6")), bc_available)
    coincident_mom6_raw = _gate_unavailable(_num(_get(coincident, "mom6")), bc_available)
    leading_diffusion_raw = _gate_unavailable(_num(_get(leading, "diffusion")), bc_available)
    coincident_diffusion_raw = _gate_unavailable(_num(_get(coincident, "diffusion")), bc_available)
    coincident_index_raw = _gate_unavailable(_num(_get(coincident, "index")), bc_available)
    growth_score_raw = _num(_get(r, "growth_score"))  # NOT business_cycle-sourced; ungated

    # ---- x components: growth momentum (deteriorating -> accelerating) --- #
    x1 = _component(
        "gdpnow_growth", "GDPNow growth nowcast", "GDPNow 实时增长预估",
        "conditions.growth_nowcast.gdpnow", "engine.conditions.growth_nowcast",
        gdpnow_raw, _center_scale_to_100(gdpnow_raw, GDPNOW_CENTER, GDPNOW_SCALE), 1, 0.35,
        _nowcast_freshness(gdpnow_raw is not None, artifact_stale),
    )
    x2 = _component(
        "wei_growth", "Weekly Economic Index growth", "每周经济指数增长",
        "conditions.growth_nowcast.wei", "engine.conditions.growth_nowcast",
        wei_raw, _center_scale_to_100(wei_raw, WEI_CENTER, WEI_SCALE), 1, 0.30,
        _nowcast_freshness(wei_raw is not None, artifact_stale),
    )
    x3 = _component(
        "leading_tier_momentum", "Leading tier 6M momentum", "领先层六个月动能",
        "business_cycle.tiers.leading.mom6", "engine.business_cycle",
        leading_mom6_raw, _center_scale_to_100(leading_mom6_raw, TIER_MOM6_CENTER, TIER_MOM6_SCALE), 1, 0.20,
        _cycle_freshness(leading_mom6_raw is not None, bc_available, artifact_stale),
    )
    x4 = _component(
        "coincident_tier_momentum", "Coincident tier 6M momentum", "同步层六个月动能",
        "business_cycle.tiers.coincident.mom6", "engine.business_cycle",
        coincident_mom6_raw, _center_scale_to_100(coincident_mom6_raw, TIER_MOM6_CENTER, TIER_MOM6_SCALE), 1, 0.15,
        _cycle_freshness(coincident_mom6_raw is not None, bc_available, artifact_stale),
    )
    x_components = [x1, x2, x3, x4]
    x_value, x_status, x_null, x_avail = _composite_value(x_components, min_components=2, coverage_floor=0.5)

    # ---- y components: growth level/breadth (weak -> strong) ------------- #
    y1 = _component(
        "leading_diffusion", "Leading tier diffusion (breadth)", "领先层扩散度（广度）",
        "business_cycle.tiers.leading.diffusion", "engine.business_cycle",
        leading_diffusion_raw, _pct_clamp_0_100(leading_diffusion_raw), 1, 0.30,
        _cycle_freshness(leading_diffusion_raw is not None, bc_available, artifact_stale),
    )
    y2 = _component(
        "coincident_diffusion", "Coincident tier diffusion (breadth)", "同步层扩散度（广度）",
        "business_cycle.tiers.coincident.diffusion", "engine.business_cycle",
        coincident_diffusion_raw, _pct_clamp_0_100(coincident_diffusion_raw), 1, 0.35,
        _cycle_freshness(coincident_diffusion_raw is not None, bc_available, artifact_stale),
    )
    y3 = _component(
        "coincident_index_level", "Coincident tier index level", "同步层指数水平",
        "business_cycle.tiers.coincident.index", "engine.business_cycle",
        coincident_index_raw, _pct_clamp_0_100(coincident_index_raw), 1, 0.20,
        _cycle_freshness(coincident_index_raw is not None, bc_available, artifact_stale),
    )
    y4 = _component(
        "growth_axis_score", "Growth axis composite (engine/axes.py)", "增长轴综合评分（engine/axes.py）",
        "growth_score", "engine.axes",
        growth_score_raw, _center_scale_to_100(growth_score_raw, GROWTH_AXIS_SCORE_CENTER, GROWTH_AXIS_SCORE_SCALE), 1, 0.15,
        _nowcast_freshness(growth_score_raw is not None, artifact_stale),
    )
    y_components = [y1, y2, y3, y4]
    y_value, y_status, y_null, y_avail = _composite_value(y_components, min_components=2, coverage_floor=0.5)

    # ---- contradiction: nowcast vs hard data / level vs breadth ---------- #
    contradiction = _detect_contradiction(x_components, y_components, _get(coincident, "direction"))

    if contradiction["present"]:
        affected_ids = set(contradiction["components"])
        x_ids = {c["component_id"] for c in x_components}
        y_ids = {c["component_id"] for c in y_components}
        if x_value is not None and affected_ids & x_ids:
            x_status = "DISAGREEMENT"
            for c in x_components:
                if c["component_id"] in affected_ids:
                    c["coverage_state"] = "DISAGREEMENT"
        if y_value is not None and affected_ids & y_ids:
            y_status = "DISAGREEMENT"
            for c in y_components:
                if c["component_id"] in affected_ids:
                    c["coverage_state"] = "DISAGREEMENT"

    # ---- freshness roll-up over the REQUIRED set -------------------------- #
    required_ids = ("gdpnow_growth", "wei_growth", "leading_diffusion", "coincident_diffusion")
    by_id = {c["component_id"]: c for c in (x_components + y_components)}
    labels = {
        "gdpnow_growth": ("GDPNow growth nowcast", "GDPNow 实时增长预估"),
        "wei_growth": ("Weekly Economic Index growth", "每周经济指数增长"),
        "leading_diffusion": ("Leading tier diffusion (breadth)", "领先层扩散度（广度）"),
        "coincident_diffusion": ("Coincident tier diffusion (breadth)", "同步层扩散度（广度）"),
    }
    src_asof = {
        "gdpnow_growth": asof,
        "wei_growth": asof,
        "leading_diffusion": bc_asof,
        "coincident_diffusion": bc_asof,
    }
    required_avail = _required_availability(by_id, required_ids, labels, src_asof)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_ids), 4)
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    # ---- quadrant + hysteresis -------------------------------------------- #
    headline = _headline(x_value, x_status, x_null, y_value, y_status, y_null, asof, prior_snapshot)

    # ---- changes vs prior accepted print ----------------------------------- #
    changes = _changes(x_value, y_value, prior_snapshot)

    # ---- axis objects (full section-7.9 disclosure) ----------------------- #
    # Built AFTER the contradiction-handling block above so a fired
    # DISAGREEMENT (value_status + the affected components' coverage_state)
    # is already baked into x_status/y_status/x_components/y_components.
    axis_growth_momentum = _axis(
        "growth_momentum", "Growth momentum", "增长动能",
        "deteriorating_to_accelerating", x_value, x_status, x_null, x_components, x_avail,
        low_en="Decelerating", low_zh="减速", high_en="Accelerating", high_zh="加速",
        weights_law=("weighted mean of standardized components, weights renormalized over present "
                     "components; gdpnow_growth 0.35, wei_growth 0.30, leading_tier_momentum 0.20, "
                     "coincident_tier_momentum 0.15"),
        transformation=("gdpnow/wei mapped via center+scale: 50+clamp((v-center)/scale,-1,1)*50 "
                        "(gdpnow center=2.0pct SAAR, scale=4.0pct; wei center=1.5pct, scale=4.0pct); "
                        "leading/coincident tier mom6 mapped with center=0, scale=2.0 index-pts; "
                        "prior-only owner reads, no in-composer estimation"),
        frequency_alignment=("mixed: GDPNow near-daily intra-quarter nowcast, WEI weekly (Fri), "
                             "leading/coincident tier mom6 monthly with per-leg publication lag "
                             "(see business_cycle.calibration_resolution / sources[business_cycle_leading])"),
        data_version=bc_calibration_version,
    )
    axis_growth_level_breadth = _axis(
        "growth_level_breadth", "Growth level/breadth", "增长水平/广度",
        "weak_to_strong", y_value, y_status, y_null, y_components, y_avail,
        low_en="Weak", low_zh="疲弱", high_en="Strong", high_zh="强劲",
        weights_law=("weighted mean of standardized components, weights renormalized over present "
                     "components; leading_diffusion 0.30, coincident_diffusion 0.35, "
                     "coincident_index_level 0.20, growth_axis_score 0.15"),
        transformation=("leading_diffusion/coincident_diffusion/coincident_index_level are direct "
                        "0-100 passthroughs (already percent-of-legs-positive / normalized index "
                        "readings); growth_axis_score (engine/axes.py) mapped via center=0, scale=1.0; "
                        "lagging tier is INTENTIONALLY EXCLUDED (published separately as "
                        "confirmation-only context: metrics[lagging_tier_index]/[lagging_tier_diffusion]/"
                        "[lagging_tier_momentum]), consistent with its trailing definition"),
        frequency_alignment=("leading/coincident tier diffusion and index monthly with per-leg "
                             "publication lag; growth_axis_score (engine/axes.py) shares the same "
                             "build cadence as the regime read"),
        data_version=bc_calibration_version,
    )

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "growth_real_economy",
            "title": _bil("Growth & Real Economy", "增长与实体经济"),
            "subtitle": _bil("Growth momentum x level/breadth", "增长动能 × 水平/广度"),
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
        "axes": {"items": [axis_growth_momentum, axis_growth_level_breadth]},
        "metrics": {"items": _metrics(
            x_value, x_status, x_null, x_components, y_value, y_status, y_null, y_components,
            gdpnow_raw, wei_raw, leading_mom6_raw, coincident_mom6_raw,
            leading_diffusion_raw, coincident_diffusion_raw, coincident_index_raw,
            growth_score_raw, leading, lagging, recession, labor_nowcast,
            asof, bc_asof, bc_available, artifact_stale,
        )},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(x_components, y_components),
        "changes": changes,
        "implications": {"items": _implications(
            headline, x_value, y_value, contradiction, worst, coverage_ratio, bc, calibration,
        )},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(asof, bc_asof, artifact_stale)},
        "corrections": _corrections(x_components, y_components, asof, prior_snapshot),
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
def _detect_contradiction(x_components: list[dict], y_components: list[dict], coincident_direction: Any) -> dict:
    """Two typed contradictions, surfaced as DISAGREEMENT (architecture 10.2:
    'nowcast versus hard-data disagreement' is required composition;
    'nowcast/hard-data contradiction' is a named failure state). Checked in
    order; only the first that fires is reported (mirrors liquidity_regime's
    if/elif single-contradiction-at-a-time discipline)."""
    by_x = {c["component_id"]: c for c in x_components}
    by_y = {c["component_id"]: c for c in y_components}
    gdpnow_std = (by_x.get("gdpnow_growth") or {}).get("standardized_value")
    idx_std = (by_y.get("coincident_index_level") or {}).get("standardized_value")
    diff_std = (by_y.get("coincident_diffusion") or {}).get("standardized_value")

    kind = None
    comps: list[str] = []
    if gdpnow_std is not None and gdpnow_std >= NOWCAST_ACCEL_THRESHOLD and coincident_direction == "falling":
        kind = "nowcast_vs_hard_data"
        comps = ["gdpnow_growth", "coincident_tier_momentum"]
    elif (idx_std is not None and diff_std is not None
          and idx_std >= INDEX_STRONG_THRESHOLD and diff_std <= DIFFUSION_NARROW_THRESHOLD):
        kind = "narrow_breadth_despite_level"
        comps = ["coincident_index_level", "coincident_diffusion"]

    if kind is None:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}

    if kind == "nowcast_vs_hard_data":
        en = ("The GDPNow / high-frequency growth nowcast reads strongly accelerating, but the coincident "
              "hard-data tier (payrolls, real income, manufacturing/trade sales, industrial production) is "
              "still trending down (direction=falling) - the nowcast acceleration is not yet confirmed by "
              "hard data.")
        zh = ("GDPNow/高频增长实时预估读数显示强劲加速，但同步硬数据层（薪资、实际收入、制造/贸易销售、工业生产）"
              "方向仍为下行（falling）——加速信号尚未获得硬数据确认。")
    else:
        en = ("The coincident tier's composite index level reads strong, but its diffusion (breadth) is "
              "narrow - the strength is concentrated in a few legs rather than broad-based.")
        zh = "同步层综合指数水平读数强劲，但其扩散度（广度）狭窄——强势集中于少数分项，而非广泛支撑。"

    return {"present": True, "kind": kind, "en": en, "zh": zh, "components": comps}


def _required_availability(by_id: dict, required_ids: tuple, labels: dict, src_asof: dict) -> list[dict]:
    out = []
    for cid in required_ids:
        comp = by_id.get(cid, {})
        present = comp.get("standardized_value") is not None
        fresh = comp.get("freshness", "SOURCE_FAILED")
        status = "PRESENT" if present and fresh == "CURRENT" else ("PARTIAL" if present else "ABSENT")
        en, zh = labels[cid]
        out.append({
            "component_id": cid,
            "label": _bil(en, zh),
            "required": True,
            "freshness": fresh,
            "status": status,
            "source_asof": src_asof.get(cid),
            "null_reason": comp.get("null_reason") if not present else None,
        })
    return out


def _classify(x: float, y: float) -> str:
    accelerating = x >= BOUNDARY
    strong = y >= BOUNDARY
    if not accelerating and strong:
        return "A"
    if accelerating and strong:
        return "B"
    if not accelerating and not strong:
        return "C"
    return "D"


def _headline(x_value, x_status, x_null, y_value, y_status, y_null, asof, prior_snapshot) -> dict:
    computable = x_value is not None and y_value is not None
    prior_id = _get(prior_snapshot, "headline", "state_id")
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_x = _get(prior_snapshot, "headline", "quadrant", "x")
    prior_y = _get(prior_snapshot, "headline", "quadrant", "y")
    comparable_prior = prior_id in ("A", "B", "C", "D") and prior_method == METHOD_VERSION

    state_id = None
    held_prior = False
    applied = False
    raw = None
    crossed_axes: list[str] = []
    if computable:
        raw = _classify(x_value, y_value)
        state_id = raw
        if comparable_prior:
            applied = True
            if raw != prior_id:
                # Mirrors liquidity_regime.py's F1-corrected hysteresis rule:
                # the prior quadrant may be held ONLY if every axis that
                # actually crossed the 50 boundary (relative to its OWN prior
                # print value) is within the band. An axis idling near its
                # own boundary WITHOUT crossing it must never suppress a
                # decisive flip on a different axis.
                prior_x_num = prior_x if isinstance(prior_x, (int, float)) else None
                prior_y_num = prior_y if isinstance(prior_y, (int, float)) else None
                if prior_x_num is not None and prior_y_num is not None:
                    if (x_value >= BOUNDARY) != (prior_x_num >= BOUNDARY):
                        crossed_axes.append("growth_momentum")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("growth_level_breadth")
                    within_band = {
                        "growth_momentum": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "growth_level_breadth": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
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
        near_axis = "growth_momentum" if dx <= dy else "growth_level_breadth"
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
    elif not held_prior and raw == prior_id:
        note = "raw classification already matches the prior print; no boundary crossing, hysteresis not engaged"
    elif held_prior:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "no axis"
        note = (f"prior quadrant held: {crossed_txt} crossed the 50 boundary since the prior "
                f"print but stayed within the {HYSTERESIS_BAND}-pt hysteresis band of ITS OWN "
                f"boundary; an axis idling near 50 without crossing it can never suppress a "
                f"decisive flip on a different axis")
    else:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "the classification"
        note = (f"prior quadrant not held: {crossed_txt} crossed the 50 boundary and moved beyond "
                f"the {HYSTERESIS_BAND}-pt hysteresis band, so the transition to the raw quadrant "
                f"is accepted")

    return {
        "state_id": state_id,
        "state_label": state_label,
        "subtitle": _bil("Growth / real economy regime", "增长/实体经济体制"),
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
    for mid, cur, prev in (("growth_momentum", x_value, prior_x),
                          ("growth_level_breadth", y_value, prior_y)):
        delta = None
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            delta = round(cur - prev, 2)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None) -> dict:
    return {
        "metric_id": metric_id,
        "reference_id": f"mastermind.market_reference/v1#{metric_id}",
        "definition_id": owner_field,
        "definition_version": AXIS_DEFINITION_VERSION,
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
        "calculation_as_of": reference_period,
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


def _metrics(x_value, x_status, x_null, x_components, y_value, y_status, y_null, y_components,
             gdpnow_raw, wei_raw, leading_mom6_raw, coincident_mom6_raw,
             leading_diffusion_raw, coincident_diffusion_raw, coincident_index_raw,
             growth_score_raw, leading, lagging, recession, labor_nowcast,
             asof, bc_asof, bc_available, artifact_stale) -> list[dict]:
    x_fresh = _worst_freshness([c["freshness"] for c in x_components]) if x_components else "SOURCE_FAILED"
    y_fresh = _worst_freshness([c["freshness"] for c in y_components]) if y_components else "SOURCE_FAILED"
    by_x = {c["component_id"]: c for c in x_components}
    by_y = {c["component_id"]: c for c in y_components}

    # Context-only tier fields (leading index level, and the whole lagging
    # tier) each get their OWN freshness computed from their own presence --
    # never borrowed from an unrelated component, which could silently
    # mislabel a genuinely-missing field as CURRENT (or vice versa). Gated by
    # bc_available the same way as the composite's own tier components, so a
    # reported-offline tier engine nulls the value everywhere, not just its
    # freshness label.
    leading_index_raw = _gate_unavailable(_num(_get(leading, "index")), bc_available)
    leading_index_fresh = _cycle_freshness(leading_index_raw is not None, bc_available, artifact_stale)
    lagging_index_raw = _gate_unavailable(_num(_get(lagging, "index")), bc_available)
    lagging_index_fresh = _cycle_freshness(lagging_index_raw is not None, bc_available, artifact_stale)
    lagging_diffusion_raw = _gate_unavailable(_num(_get(lagging, "diffusion")), bc_available)
    lagging_diffusion_fresh = _cycle_freshness(lagging_diffusion_raw is not None, bc_available, artifact_stale)
    lagging_mom6_raw = _gate_unavailable(_num(_get(lagging, "mom6")), bc_available)
    lagging_momentum_fresh = _cycle_freshness(lagging_mom6_raw is not None, bc_available, artifact_stale)

    recession_score_raw = _num(_get(recession, "score"))
    recession_score_fresh = _nowcast_freshness(recession_score_raw is not None, artifact_stale)
    sahm_raw = _num(_get(recession, "sahm"))
    sahm_fresh = _nowcast_freshness(sahm_raw is not None, artifact_stale)
    real_income_proxy_raw = _num(_get(labor_nowcast, "withheld_tax_yoy_pct"))
    real_income_proxy_fresh = _nowcast_freshness(real_income_proxy_raw is not None, artifact_stale)

    momentum_transformation = (
        "weighted mean of standardized components (weights renormalized over present components): "
        "gdpnow_growth w=0.35 (see metrics[gdpnow_growth]; center=2.0pct SAAR, scale=4.0pct), "
        "wei_growth w=0.30 (see metrics[wei_growth]; center=1.5pct, scale=4.0pct), "
        "leading_tier_momentum w=0.20 (see metrics[leading_tier_momentum]; center=0, scale=2.0 index-pts mom6), "
        "coincident_tier_momentum w=0.15 (see metrics[coincident_tier_momentum]; center=0, scale=2.0 index-pts mom6); "
        "min_components=2, coverage_floor=0.5; boundary=50.0 (deteriorating<50<=accelerating), hysteresis_band=5.0; "
        "definition_version=1.0.0, data_version=business_cycle.calibration_resolution.calibration_version "
        "(see sources[business_cycle_leading]/[business_cycle_coincident]); revision_behavior=recomputed each "
        "owner cadence from prior-only owner reads, a method-version change breaks comparability and is reported "
        "as such, never as a numeric delta; authority_ceiling=DESCRIPTIVE. NOTE: this composite-level summary is "
        "also published as a full axis object at axes.items[growth_momentum], including per-component raw/"
        "standardized values, sign, weight, and coverage state."
    )
    breadth_transformation = (
        "weighted mean of standardized components (weights renormalized over present components): "
        "leading_diffusion w=0.30 (see metrics[leading_diffusion]; direct 0-100 passthrough, already a "
        "percent-of-legs-positive breadth measure), coincident_diffusion w=0.35 (see metrics[coincident_diffusion]; "
        "direct 0-100 passthrough), coincident_index_level w=0.20 (see metrics[coincident_index_level]; direct "
        "0-100 passthrough), growth_axis_score w=0.15 (see metrics[growth_axis_score]; center=0, scale=1.0, "
        "engine/axes.py composite); lagging tier is INTENTIONALLY EXCLUDED from this composite (published "
        "separately as confirmation-only context: metrics[lagging_tier_index]/[lagging_tier_diffusion]/"
        "[lagging_tier_momentum]), consistent with its trailing definition; min_components=2, coverage_floor=0.5; "
        "boundary=50.0 (weak<50<=strong), hysteresis_band=5.0; definition_version=1.0.0, "
        "data_version=business_cycle.calibration_resolution.calibration_version; revision_behavior=recomputed "
        "each owner cadence from prior-only owner reads; authority_ceiling=DESCRIPTIVE. NOTE: this "
        "composite-level summary is also published as a full axis object at "
        "axes.items[growth_level_breadth], including per-component raw/standardized values, sign, weight, "
        "and coverage state."
    )

    items = [
        _metric("growth_momentum", x_value, "score_0_100", "score", "composite_prior_only",
                "deteriorating_to_accelerating", "engine.market_os.macro_workspaces.growth",
                "growth_momentum_composite", asof, x_fresh, transformation=momentum_transformation,
                status=x_status if x_value is not None else "ABSENT", null_reason=x_null),
        _metric("growth_level_breadth", y_value, "score_0_100", "score", "composite_prior_only",
                "weak_to_strong", "engine.market_os.macro_workspaces.growth",
                "growth_level_breadth_composite", asof, y_fresh, transformation=breadth_transformation,
                status=y_status if y_value is not None else "ABSENT", null_reason=y_null),
        _metric("gdpnow_growth", gdpnow_raw, "percent", "pct_saar", "level", "higher_stronger",
                "engine.conditions.growth_nowcast", "conditions.growth_nowcast.gdpnow", asof,
                (by_x.get("gdpnow_growth") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("wei_growth", wei_raw, "percent", "pct_annualized_equiv", "level", "higher_stronger",
                "engine.conditions.growth_nowcast", "conditions.growth_nowcast.wei", asof,
                (by_x.get("wei_growth") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("leading_tier_momentum", leading_mom6_raw, "number", "index_pts_mom6", "six_month_momentum",
                "higher_accelerating", "engine.business_cycle", "business_cycle.tiers.leading.mom6", bc_asof,
                (by_x.get("leading_tier_momentum") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("coincident_tier_momentum", coincident_mom6_raw, "number", "index_pts_mom6", "six_month_momentum",
                "higher_accelerating", "engine.business_cycle", "business_cycle.tiers.coincident.mom6", bc_asof,
                (by_x.get("coincident_tier_momentum") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("leading_diffusion", leading_diffusion_raw, "percent", "pct_legs_positive", "level",
                "higher_broader", "engine.business_cycle", "business_cycle.tiers.leading.diffusion", bc_asof,
                (by_y.get("leading_diffusion") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("coincident_diffusion", coincident_diffusion_raw, "percent", "pct_legs_positive", "level",
                "higher_broader", "engine.business_cycle", "business_cycle.tiers.coincident.diffusion", bc_asof,
                (by_y.get("coincident_diffusion") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("coincident_index_level", coincident_index_raw, "index", "index_0_100", "level",
                "higher_stronger", "engine.business_cycle", "business_cycle.tiers.coincident.index", bc_asof,
                (by_y.get("coincident_index_level") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("growth_axis_score", growth_score_raw, "z_score", "z", "level", "higher_stronger",
                "engine.axes", "growth_score", asof,
                (by_y.get("growth_axis_score") or {}).get("freshness", "SOURCE_FAILED")),
        _metric("leading_tier_index", leading_index_raw, "index", "index_0_100", "level", "higher_stronger",
                "engine.business_cycle", "business_cycle.tiers.leading.index", bc_asof, leading_index_fresh,
                transformation="context-only (leading tier), not part of the growth_momentum/growth_level_breadth composite"),
        _metric("lagging_tier_index", lagging_index_raw, "index", "index_0_100", "level", "higher_stronger",
                "engine.business_cycle", "business_cycle.tiers.lagging.index", bc_asof, lagging_index_fresh,
                transformation="confirmation-only (lagging tier), intentionally excluded from the headline composite"),
        _metric("lagging_tier_diffusion", lagging_diffusion_raw, "percent", "pct_legs_positive", "level",
                "higher_broader", "engine.business_cycle", "business_cycle.tiers.lagging.diffusion", bc_asof,
                lagging_diffusion_fresh,
                transformation="confirmation-only (lagging tier), intentionally excluded from the headline composite"),
        _metric("lagging_tier_momentum", lagging_mom6_raw, "number", "index_pts_mom6", "six_month_momentum",
                "higher_accelerating", "engine.business_cycle", "business_cycle.tiers.lagging.mom6", bc_asof,
                lagging_momentum_fresh,
                transformation="confirmation-only (lagging tier), intentionally excluded from the headline composite"),
        _metric("recession_risk_score", recession_score_raw, "ratio", "probability_0_1", "level",
                "higher_more_risk", "engine.conditions.recession", "conditions.recession.score", asof,
                recession_score_fresh,
                transformation="descriptive context only; see implications[recession_calibration_caveat] when calibration is stale"),
        _metric("sahm_rule_value", sahm_raw, "number", "pp", "level", "higher_more_risk",
                "engine.conditions.recession", "conditions.recession.sahm", asof, sahm_fresh),
        _metric("real_income_proxy_yoy", real_income_proxy_raw, "percent", "pct_yoy", "level", "higher_stronger",
                "engine.conditions.labor_nowcast", "conditions.labor_nowcast.withheld_tax_yoy_pct", asof,
                real_income_proxy_fresh,
                transformation="high-frequency PROXY (withheld tax receipts YoY), NOT BEA real personal income; disclosed as a proxy, not a canonical income series"),
    ]
    return items


def _drivers(x_components: list[dict], y_components: list[dict]) -> dict:
    momentum_note = (
        "[schema key law] published under drivers.rate_side because the shared "
        "macro_workspace_snapshot.v1 schema names this array 'rate_side' (inherited from the "
        "liquidity_regime workspace); it carries a growth-momentum driver here, not a rate-side reading."
    )
    breadth_note = (
        "[schema key law] published under drivers.balance_sheet because the shared "
        "macro_workspace_snapshot.v1 schema names this array 'balance_sheet' (inherited from the "
        "liquidity_regime workspace); it carries a growth-level/breadth driver here, not a balance-sheet reading."
    )

    def _to_driver(c, unit, side_note):
        contrib = c["contribution"]
        sign = 0 if contrib is None else (1 if contrib > 0 else (-1 if contrib < 0 else 0))
        note = (f"signed push = (standardized-50)*weight toward the axis high side; "
                f"standardized={c['standardized_value']}, weight={c['weight']}. {side_note}")
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

    rate_side = [_to_driver(c, u, momentum_note) for c, u in zip(
        x_components, ["percent", "percent", "index_pts", "index_pts"])]
    balance_sheet = [_to_driver(c, u, breadth_note) for c, u in zip(
        y_components, ["percent", "percent", "index", "z_score"])]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _implications(headline, x_value, y_value, contradiction, worst_freshness,
                  coverage_ratio, bc, calibration) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
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
                f"US growth regime reads {state_id} - {label_en} (growth momentum x={x_value}, "
                f"growth level/breadth y={y_value}, boundary 50).",
                f"美国增长体制读数为 {state_id} - {label_zh}（增长动能 x={x_value}，"
                f"增长水平/广度 y={y_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["output", "employment", "production", "orders"],
            "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
            "trace_ref": "data/regime/latest.json#business_cycle",
        })
    else:
        items.append({
            "implication_id": "state_unavailable",
            "text": _bil(
                "US growth regime cannot be classified: axis coverage is below the disclosed floor. "
                "No quadrant is asserted rather than defaulting to a neutral state.",
                "美国增长体制无法分类：轴覆盖低于披露下限。不默认中性状态，故不给出象限。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["output", "employment", "production", "orders"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#business_cycle",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": f"{contradiction['kind']}_contradiction",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["output", "employment", "production"],
            "contradictions": [contradiction["kind"]],
            "trace_ref": "data/regime/latest.json#business_cycle",
        })
    calibrated = bc.get("calibrated") if isinstance(bc, Mapping) else None
    age_days = calibration.get("calibration_age_days") if isinstance(calibration, Mapping) else None
    if calibrated is False or (isinstance(age_days, (int, float)) and age_days > CALIBRATION_STALE_DAYS):
        items.append({
            "implication_id": "recession_calibration_caveat",
            "text": _bil(
                "Business-cycle tier calibration is stale or unmarked as calibrated: recession/turning-point "
                "context shown on this page is descriptive only and must not be read as a validated recession call.",
                "商业周期分层校准已过期或未标记为已校准：本页展示的衰退/转折点背景仅供描述参考，"
                "不得视为经过验证的衰退判断。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["output"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#business_cycle.calibration_resolution",
        })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "gdpnow_pct", "label": _bil("GDPNow growth", "GDPNow 增长"),
             "unit": "pct_saar", "step": 0.25, "min": -6.0, "max": 10.0,
             "owner_field": "conditions.growth_nowcast.gdpnow"},
            {"assumption_id": "claims_level", "label": _bil("Initial claims (4wk avg)", "初次申请（4周均值）"),
             "unit": "count", "step": 5000.0, "min": 150000.0, "max": 500000.0,
             "owner_field": "conditions.labor_nowcast.initial_claims_4wk"},
            {"assumption_id": "indpro_yoy_pct", "label": _bil("Industrial production YoY", "工业生产同比"),
             "unit": "pct_yoy", "step": 0.25, "min": -10.0, "max": 10.0, "owner_field": None},
            {"assumption_id": "real_income_pct", "label": _bil("Real income growth", "实际收入增长"),
             "unit": "pct_yoy", "step": 0.25, "min": -10.0, "max": 10.0,
             "owner_field": "conditions.labor_nowcast.withheld_tax_yoy_pct"},
            {"assumption_id": "financial_conditions_shock", "label": _bil("Financial conditions shock", "金融条件冲击"),
             "unit": "index", "step": 0.1, "min": -3.0, "max": 3.0,
             "owner_field": "conditions.financial_conditions.nfci"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; R2 ships no scenario execution endpoint (non-goal). A future owner-native pure scenario function produces mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "quadrant_transition", "kind": "state_transition",
             "label": _bil("Quadrant change", "象限变化"), "params": ["target_quadrant"]},
            {"condition_id": "leading_rollover", "kind": "boundary_approach",
             "label": _bil("Broad leading rollover", "领先指标广泛转向"), "params": ["axis", "distance"]},
            {"condition_id": "coincident_confirmation", "kind": "component_shock",
             "label": _bil("Coincident confirmation", "同步指标确认"), "params": ["component_id", "z"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
            {"condition_id": "nowcast_hard_data_contradiction", "kind": "contradiction_change",
             "label": _bil("Nowcast / hard-data contradiction", "实时预估/硬数据矛盾"), "params": ["kind"]},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; R2 writes no alert (non-goal). Alerts extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service can create/list/evaluate/delete these real conditions.",
    }


def _sources(asof, bc_asof, artifact_stale: bool) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period):
        fresh = "STALE_SOURCE" if artifact_stale else "CURRENT"
        return {
            "source_id": source_id,
            "label": _bil(en, zh),
            "owner_ref": owner_ref,
            "provider": provider,
            "reference_period": ref_period,
            "released_at": None,
            "first_known_at": None,
            "collected_at": None,
            "revised_at": None,
            "correction_state": "unknown",
            "transform": None,
            "rights_state": "OPEN",
            "definition_id": None,
            "definition_version": None,
            "artifact_ref": "data/regime/latest.json",
            "freshness": fresh,
        }
    return [
        _src("gdpnow", "GDPNow real-time GDP nowcast", "GDPNow 实时GDP预估",
             "engine.conditions.growth_nowcast", "Federal Reserve Bank of Atlanta", asof),
        _src("wei", "NY Fed Weekly Economic Index", "纽约联储每周经济指数",
             "engine.conditions.growth_nowcast", "Federal Reserve Bank of New York / FRED", asof),
        _src("business_cycle_leading",
             "Leading tier composite (claims/permits/new orders/S&P 500/HY OAS/yield curve/consumer sentiment)",
             "领先层综合指数（初次申请/开工许可/新订单/标普500/高收益利差/收益率曲线/消费者信心）",
             "engine.business_cycle", "Mastermind engine.business_cycle (multi-source; see calibration config)", bc_asof),
        _src("business_cycle_coincident",
             "Coincident tier composite (nonfarm payrolls/real income/mfg-trade sales/industrial production)",
             "同步层综合指数（非农就业/实际收入/制造贸易销售/工业生产）",
             "engine.business_cycle", "Mastermind engine.business_cycle (multi-source; see calibration config)", bc_asof),
        _src("business_cycle_lagging",
             "Lagging tier composite (avg unemployment duration/inventory-sales ratio/business loans/prime rate/shelter CPI)",
             "滞后层综合指数（平均失业时长/库存销售比/工商贷款/最优惠利率/住房CPI）",
             "engine.business_cycle", "Mastermind engine.business_cycle (multi-source; see calibration config)", bc_asof),
        _src("growth_axis", "Growth axis composite", "增长轴综合评分",
             "engine.axes", "Mastermind engine.axes (internal composite over hard + survey inputs)", asof),
        _src("recession_context", "Recession-risk context (NY Fed probability, Sahm rule, EBP, yield curve)",
             "衰退风险背景（纽约联储概率、Sahm法则、超额债券溢价、收益率曲线）",
             "engine.conditions.recession", "NY Fed / Federal Reserve Board / FRED", asof),
        _src("labor_nowcast_income_proxy",
             "Withheld tax receipts YoY (real-time income proxy, NOT BEA real income)",
             "预扣税收入同比（实时收入代理指标，非BEA实际收入）",
             "engine.conditions.labor_nowcast", "Daily Treasury Statement via engine.conditions.labor_nowcast", asof),
    ]


# Which x/y components' owner-native raw values back which named source (used
# for the corrections/supersession scan below).
_SOURCE_COMPONENT_MAP: dict[str, tuple[str, ...]] = {
    "gdpnow": ("gdpnow_growth",),
    "wei": ("wei_growth",),
    "business_cycle_leading": ("leading_tier_momentum", "leading_diffusion"),
    "business_cycle_coincident": ("coincident_tier_momentum", "coincident_diffusion", "coincident_index_level"),
    "growth_axis": ("growth_axis_score",),
}


def _prior_component_value(prior_snapshot, metric_id):
    """Look up a leaf component's previously-published RAW value. Since
    axes.items is empty (see module docstring), each leaf component's raw
    value lives in metrics.items[metric_id].value instead of an
    axes.items[*].components[*].raw_value slot."""
    for m in (_get(prior_snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _corrections(x_components, y_components, asof, prior_snapshot) -> dict:
    """Minimal, honest supersession detection (mirrors liquidity_regime.py's
    F8 scoped subset of full source-vintage revision tracking): a
    "correction" is a REVISION of the SAME reference period's published read,
    never the normal day-over-day evolution of a new observation."""
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
    current_raw = {c["component_id"]: c["raw_value"] for c in (list(x_components) + list(y_components))}
    changed: list[str] = []
    for source_id, comp_ids in _SOURCE_COMPONENT_MAP.items():
        for cid in comp_ids:
            cur = current_raw.get(cid)
            prev = _prior_component_value(prior_snapshot, cid)
            if cur != prev:
                digest16 = sha256(f"{source_id}:{cid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
                changed.append(f"{source_id}:{cid}:{digest16}")
    if changed:
        return {
            "predecessor_generation_id": prior_gen,
            "changed_fingerprints": sorted(changed),
            "correction_state": "superseded",
            "note": "Same reference period as the predecessor print, but one or more owner-native source components changed value: this print supersedes the prior one as a revision.",
        }
    return {
        "predecessor_generation_id": prior_gen,
        "changed_fingerprints": [],
        "correction_state": "none",
        "note": "Same reference period as the predecessor print; no source component changed value (no-change republication).",
    }
