"""Pure composer for the US ``financial_conditions`` workspace snapshot (F01 / R3).

Reads the SAME owner artifact R1A reads (canonically ``data/regime/latest.json``)
and projects it into a ``mastermind.macro_workspace_snapshot.v1`` body. Financial
Conditions and Liquidity Regime read overlapping owner sections (NFCI, OFR FSI,
HY OAS) — this module reuses the identical owner fields R1A already consumes for
those three so the two workspaces can never silently disagree at the owner
level (see the ``test_*_agrees_with_r1a_at_owner_level`` tests). Composition
still differs on purpose (architecture 10.8 vs 10.1 are different questions) and
every difference is disclosed in each metric's ``transformation`` text rather
than reusing a name for a different quantity.

Blueprint (architecture 10.8) headline model::

    x-axis: conditions level, easy -> tight
    y-axis: impulse, easing -> tightening

Channel decomposition (architecture 10.8 "Required composition"): rates,
credit, dollar/funding, equities/volatility, lending — kept structurally
separate from the two OFFICIAL/ESTABLISHED indexes (NFCI, OFR FSI), which are
published verbatim as their own metrics. NO metric here feeds a Mastermind
channel AND is also the blended official index value for that same channel —
channels are built from OFR FSI *functional sub-legs* and NFCI *subindices*
(narrower, unblended reads), never from the blended nfci/ofr_fsi headline
numbers themselves. That is the "no hidden blend" law (architecture 7.9 /
10.8) made concrete.

*** CONTRACT-VOCABULARY NOTE ***
``contracts/market_os/macro_workspace_snapshot.v1.schema.json`` — the file this
module may NOT edit — was widened in the integration pass so
``$defs.axis.properties.axis_id`` accepts any lowercase-snake-case id, not only
R1A's ``funding_pressure``/``balance_sheet_support`` pair. This module now
publishes two real axis objects, ``financial_conditions_level`` and
``financial_conditions_impulse``, following the R1A axis shape EXACTLY (same
key set, ``additionalProperties: false``) with full component/weight/
threshold/hysteresis disclosure per architecture 7.9 — see ``_axis()``,
``_LEVEL_WEIGHTS_LAW``/``_LEVEL_METHOD_NOTE``, and
``_IMPULSE_WEIGHTS_LAW``/``_IMPULSE_METHOD_NOTE``. Each axis's ``components``
are the SAME objects that drive its value computation (level: the 4
channel-score wrappers; impulse: the 3 owner-native momentum legs) — one list,
no duplicated or divergent disclosure between the axis and the math.

``drivers`` remains closed to exactly ``{rate_side, balance_sheet}`` — an
R1A-shaped pair that was NOT widened. This module maps rates+credit channel
drivers into ``rate_side`` and dollar/funding+equities-vol channel drivers
into ``balance_sheet``; the mapping is cosmetic bucket reuse, disclosed in
each driver's own ``note`` and in the ``driver_bucket_naming_note``
implication (kept v1, unchanged by the axis_id widening).

Emits TYPED degraded states, never zero/neutral/calm:
    - a required source missing            -> SOURCE_FAILED
    - a required source flagged stale       -> STALE_SOURCE
    - a required source not yet released    -> NOT_YET_RELEASED
    - channel coverage below the floor      -> value null + COMPUTATION_REFUSED
    - broad stress calm vs risk appetite
      not calm                              -> a typed contradiction (DISAGREEMENT)
    - no comparable prior print             -> vector/changes WARMUP
    - prior print on a different method     -> changes METHOD_CHANGED (refuses deltas)
    - lending channel / IG OAS / dollar-FX
      leg (no owner source exists at all)   -> permanent typed NOT_COVERED

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive ceiling
only. Depends only on the standard library. The composer NEVER reads a wall
clock: ``built_at`` is passed in by the builder, and freshness is derived from
owner-provided source flags/vintages, so an identical owner input always
yields an identical snapshot body.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "financial_conditions.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.financial_conditions"

BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0

# Standardization scales: a raw move of this magnitude maps to a full
# half-swing (0 or 100) after clamping. Chosen from the owner's own native
# scale for each series (NFCI/OFR sub-legs and z-scores are ~N(0,1)-ish;
# 13-week NFCI/OFR-FSI drift rarely exceeds ~1.0 index point; a 50bp 63-day
# real-10y move is a large impulse).
Z_SCALE = 2.5
NFCI_CHG_SCALE = 0.5
OFR_CHG_SCALE = 1.0
REAL10Y_CHG_SCALE_BP = 50.0

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

_QUADRANTS = {
    "A": {"en": "Easy conditions / Easing impulse", "zh": "宽松条件 / 边际放松"},
    "B": {"en": "Tight conditions / Tightening impulse", "zh": "紧张条件 / 边际收紧"},
    "C": {"en": "Easy conditions / Tightening impulse", "zh": "宽松条件 / 边际收紧"},
    "D": {"en": "Tight conditions / Easing impulse", "zh": "紧张条件 / 边际放松"},
}


# --------------------------------------------------------------------------- #
# small pure helpers (deliberately self-contained -- no cross-import from
# liquidity_regime.py, so this file can be added without touching any other
# module; the shape below intentionally mirrors it)
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


def _pct_to_100(p: float | None) -> float | None:
    return None if p is None else _clamp(p * 100.0, 0.0, 100.0)


def _z_to_100(z: float | None, scale: float) -> float | None:
    return None if z is None else _clamp(50.0 + (_clamp(z, -scale, scale) / scale) * 50.0, 0.0, 100.0)


def _ratio_to_100(r: float | None) -> float | None:
    return None if r is None else _clamp(r * 100.0, 0.0, 100.0)


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _channel_freshness(components: list[dict]) -> str:
    """Roll a channel's own freshness up from its REAL legs only. A
    permanently-declared-but-never-sourced leg (freshness=NOT_COVERED, e.g.
    IG OAS inside credit_channel) must not drag an otherwise-CURRENT channel
    down to NOT_COVERED -- that would misreport a channel that actually
    computes a real number today. Falls back to NOT_COVERED only when EVERY
    leg is permanently uncovered."""
    real = [c["freshness"] for c in components if c["freshness"] != "NOT_COVERED"]
    if not real:
        return "NOT_COVERED"
    return _worst_freshness(real)


def _vintage_freshness(value_present: bool, vintage: Any, stale_inputs: list, name: str) -> str:
    v = vintage if isinstance(vintage, Mapping) else {}
    if not value_present:
        return "NOT_YET_RELEASED" if v.get("not_yet_released") is True else "SOURCE_FAILED"
    if name in (stale_inputs or []) or v.get("stale") is True:
        return "STALE_SOURCE"
    return "CURRENT"


def _volregime_freshness(value_present: bool, vol_regime: Mapping) -> str:
    if not value_present:
        return "SOURCE_FAILED"
    if vol_regime.get("available") is False:
        return "SOURCE_FAILED"
    return "CURRENT"


def _bil(en: str, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


# --------------------------------------------------------------------------- #
# component / composite construction (mirrors R1A's axis-component shape so a
# reviewer can diff the two composers directly; NOT published as axes.items --
# see the module docstring's CONTRACT-VOCABULARY DEVIATION)
# --------------------------------------------------------------------------- #
def _component(component_id, label_en, label_zh, owner_field, owner_ref, raw,
               standardized, sign, weight, freshness) -> dict:
    present = standardized is not None
    if not present:
        null_reason = "SOURCE_FAILED" if freshness == "SOURCE_FAILED" else (
            "NOT_YET_RELEASED" if freshness == "NOT_YET_RELEASED" else (
                "NOT_COVERED" if freshness == "NOT_COVERED" else "UNKNOWN"))
        coverage_state = "ABSENT"
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
    """Weighted mean over PRESENT components; weights renormalize over what's
    actually available. A permanently-absent declared component (e.g. IG OAS,
    the dollar/FX leg, lending) dilutes the denominator forever and is never
    silently dropped from the disclosure -- it stays listed with
    coverage_state=ABSENT/null_reason=NOT_COVERED."""
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
          weights_law, transformation, frequency_alignment) -> dict:
    """Same shape R1A ships (schema $defs/axis, additionalProperties:false) --
    axis_id is now a widened lowercase-snake-case value, not R1A's borrowed
    funding_pressure/balance_sheet_support pair (see module docstring)."""
    fresh = _channel_freshness(components) if components else "SOURCE_FAILED"
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
    fc = _get(r, "conditions", "financial_conditions") or {}
    ss = _get(r, "conditions", "systemic_stress") or {}
    vintages = _get(r, "conditions", "vintages") or {}
    stale_inputs = _get(r, "conditions", "stale_inputs") or []
    stress_overlay = _get(r, "liquidity_quality", "stress_overlay") or {}
    rates = _get(r, "rate_inflation_transmission", "state", "rates") or {}
    vol_regime = _get(r, "vol_regime") or {}
    risk_state = _get(r, "risk_state") or {}

    # ---- rates channel ---------------------------------------------------- #
    real10y_pctile = _num(rates.get("real_10y_pctile"))
    rates_fresh = _vintage_freshness(real10y_pctile is not None, _get(vintages, "us10y"), stale_inputs, "us10y")
    rc1 = _component("real_10y_pctile", "Real 10Y yield percentile", "10年期实际收益率分位",
                      "rate_inflation_transmission.state.rates.real_10y_pctile",
                      "engine.sector_rate_inflation.rate_inflation_transmission",
                      real10y_pctile, _pct_to_100(real10y_pctile), 1, 1.0, rates_fresh)
    rates_components = [rc1]
    rates_value, rates_status, rates_null, rates_avail = _composite_value(
        rates_components, min_components=1, coverage_floor=1.0)

    # ---- credit channel ---------------------------------------------------- #
    hy_oas_z = _num(_get(stress_overlay, "hy_oas_z"))
    hy_fresh = _vintage_freshness(hy_oas_z is not None, _get(vintages, "hy_oas"), stale_inputs, "hy_oas")
    cc1 = _component("hy_oas_z_credit_leg", "HY OAS z-score (credit channel)", "高收益利差 z 值（信用分项）",
                      "liquidity_quality.stress_overlay.hy_oas_z", "engine.regime.liquidity_quality",
                      hy_oas_z, _z_to_100(hy_oas_z, Z_SCALE), 1, 0.45, hy_fresh)
    nfci_credit = _num(_get(fc, "subindices", "nfci_credit"))
    nfci_fresh = _vintage_freshness(nfci_credit is not None, _get(vintages, "nfci"), stale_inputs, "nfci")
    cc2 = _component("nfci_credit_subindex", "NFCI credit subindex", "NFCI 信用分项",
                      "conditions.financial_conditions.subindices.nfci_credit",
                      "engine.conditions.financial_conditions",
                      nfci_credit, _z_to_100(nfci_credit, Z_SCALE), 1, 0.25, nfci_fresh)
    cc3 = _component("ig_oas_credit_leg", "IG OAS (declared, not currently sourced)", "投资级利差（已声明，暂无数据源）",
                      "N/A", "N/A", None, None, 1, 0.30, "NOT_COVERED")
    credit_components = [cc1, cc2, cc3]
    credit_value, credit_status, credit_null, credit_avail = _composite_value(
        credit_components, min_components=2, coverage_floor=0.5)

    # ---- dollar/funding channel -------------------------------------------- #
    ofr_funding = _num(_get(ss, "functional", "funding"))
    ofr_fresh = _vintage_freshness(ofr_funding is not None, _get(vintages, "ofr_fsi"), stale_inputs, "ofr_fsi")
    dc1 = _component("ofr_funding_functional", "OFR FSI funding functional leg", "OFR 压力指数-融资功能分项",
                      "conditions.systemic_stress.functional.funding", "engine.conditions.systemic_stress",
                      ofr_funding, _z_to_100(ofr_funding, Z_SCALE), 1, 0.50, ofr_fresh)
    dc2 = _component("dollar_index_leg", "Broad dollar index (declared, not currently sourced)",
                      "广义美元指数（已声明，暂无数据源）",
                      "N/A", "N/A", None, None, 1, 0.50, "NOT_COVERED")
    dollar_funding_components = [dc1, dc2]
    dollar_funding_value, dollar_funding_status, dollar_funding_null, dollar_funding_avail = _composite_value(
        dollar_funding_components, min_components=1, coverage_floor=0.5)

    # ---- equities/volatility channel --------------------------------------- #
    vr_risk = _num(vol_regime.get("risk_score"))
    vr_fresh = _volregime_freshness(vr_risk is not None, vol_regime)
    ec1 = _component("vol_regime_risk_score", "Vol-regime risk score", "波动率体制风险评分",
                      "vol_regime.risk_score", "engine.vol_regime",
                      vr_risk, _ratio_to_100(vr_risk), 1, 0.60, vr_fresh)
    move_pctile = _num(vol_regime.get("move_pctile"))
    move_fresh = _volregime_freshness(move_pctile is not None, vol_regime)
    ec2 = _component("move_pctile", "MOVE (bond vol) percentile", "MOVE（债券波动率）分位",
                      "vol_regime.move_pctile", "engine.vol_regime",
                      move_pctile, _pct_to_100(move_pctile), 1, 0.40, move_fresh)
    equities_vol_components = [ec1, ec2]
    equities_vol_value, equities_vol_status, equities_vol_null, equities_vol_avail = _composite_value(
        equities_vol_components, min_components=1, coverage_floor=0.5)

    # ---- lending channel: no owner source exists at all -------------------- #
    lending_value, lending_status, lending_null = None, "ABSENT", "NOT_COVERED"

    # ---- level composite (x): weighted mean of the 4 available channels ---- #
    # Each channel is itself already a weighted-mean composite (see rc1/cc*/
    # dc*/ec* above); it is re-wrapped through _component() here so the SAME
    # objects that drive the math also carry the full axisComponent shape
    # (label/owner_field/owner_ref/freshness/coverage_state) required to
    # publish axes.items[0].components under architecture 7.9 -- one list,
    # no duplicated/divergent disclosure.
    level_axis_components = [
        _component("rates_channel", "Rates channel", "利率分项",
                   "channels.rates_channel_score", PRODUCER,
                   rates_value, rates_value, 1, 0.30, _channel_freshness(rates_components)),
        _component("credit_channel", "Credit channel", "信用分项",
                   "channels.credit_channel_score", PRODUCER,
                   credit_value, credit_value, 1, 0.30, _channel_freshness(credit_components)),
        _component("dollar_funding_channel", "Dollar/funding channel", "美元/融资分项",
                   "channels.dollar_funding_channel_score", PRODUCER,
                   dollar_funding_value, dollar_funding_value, 1, 0.20,
                   _channel_freshness(dollar_funding_components)),
        _component("equities_vol_channel", "Equities/volatility channel", "股票/波动率分项",
                   "channels.equities_vol_channel_score", PRODUCER,
                   equities_vol_value, equities_vol_value, 1, 0.20,
                   _channel_freshness(equities_vol_components)),
    ]
    level_value, level_status, level_null, level_avail = _composite_value(
        level_axis_components, min_components=2, coverage_floor=0.5)

    # ---- impulse composite (y): weighted mean of 13w/63d momentum legs ----- #
    nfci_chg = _num(fc.get("nfci_change_13w"))
    nfci_chg_fresh = _vintage_freshness(nfci_chg is not None, _get(vintages, "nfci"), stale_inputs, "nfci")
    ic1 = _component("nfci_change_13w", "NFCI 13-week change", "NFCI 13周变化",
                      "conditions.financial_conditions.nfci_change_13w", "engine.conditions.financial_conditions",
                      nfci_chg, _z_to_100(nfci_chg, NFCI_CHG_SCALE), 1, 0.35, nfci_chg_fresh)
    ofr_chg = _num(ss.get("ofr_fsi_change_13w"))
    ofr_chg_fresh = _vintage_freshness(ofr_chg is not None, _get(vintages, "ofr_fsi"), stale_inputs, "ofr_fsi")
    ic2 = _component("ofr_fsi_change_13w", "OFR FSI 13-week change", "OFR 压力指数13周变化",
                      "conditions.systemic_stress.ofr_fsi_change_13w", "engine.conditions.systemic_stress",
                      ofr_chg, _z_to_100(ofr_chg, OFR_CHG_SCALE), 1, 0.35, ofr_chg_fresh)
    real10y_chg = _num(rates.get("real_10y_chg_63d_bp"))
    real10y_chg_fresh = _vintage_freshness(real10y_chg is not None, _get(vintages, "us10y"), stale_inputs, "us10y")
    ic3 = _component("real_10y_chg_63d_bp", "Real 10Y yield 63-day change", "10年期实际收益率63日变化",
                      "rate_inflation_transmission.state.rates.real_10y_chg_63d_bp",
                      "engine.sector_rate_inflation.rate_inflation_transmission",
                      real10y_chg, _z_to_100(real10y_chg, REAL10Y_CHG_SCALE_BP), 1, 0.30, real10y_chg_fresh)
    impulse_components = [ic1, ic2, ic3]
    impulse_value, impulse_status, impulse_null, impulse_avail = _composite_value(
        impulse_components, min_components=2, coverage_floor=0.5)

    # ---- contradiction: official broad-stress calm vs risk appetite not calm #
    contradiction = _detect_contradiction(ss, risk_state)

    if contradiction["present"]:
        # F3-equivalent: a fired contradiction is a typed DISAGREEMENT on the
        # implicated composite AND on the affected axis object's value_status
        # (never left silently PRESENT beside the contradiction block). Value
        # stays published (typed disagreement, not censoring). Guarded on the
        # composite actually being computed.
        if level_value is not None:
            level_status = "DISAGREEMENT"
        if equities_vol_value is not None:
            equities_vol_status = "DISAGREEMENT"
            for c in equities_vol_components:
                c["coverage_state"] = "DISAGREEMENT"
            # the equities_vol_channel entry inside the level axis's own
            # components list is the SAME implicated leg -- flag it there too.
            for c in level_axis_components:
                if c["component_id"] == "equities_vol_channel":
                    c["coverage_state"] = "DISAGREEMENT"

    # ---- freshness roll-up over the REQUIRED set ---------------------------- #
    required_ids = ("nfci_pctile", "ofr_fsi_pctile", "hy_oas_pct", "real_10y_pctile", "vol_regime_risk_score")
    required_avail = _required_availability(fc, ss, stress_overlay, rates, vol_regime, vintages, stale_inputs)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_ids), 4)
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    headline = _headline(level_value, level_status, level_null, impulse_value, impulse_status,
                         impulse_null, asof, prior_snapshot, contradiction)
    changes = _changes(headline, level_value, impulse_value, prior_snapshot)

    axes_items = [
        _axis("financial_conditions_level", "Conditions level", "条件水平", "higher_tighter",
              level_value, level_status, level_null, level_axis_components, level_avail,
              low_en="Easy conditions", low_zh="宽松条件", high_en="Tight conditions", high_zh="紧张条件",
              weights_law=_LEVEL_WEIGHTS_LAW, transformation=_LEVEL_METHOD_NOTE,
              frequency_alignment="mixed: real-10y-yield daily, HY OAS/NFCI credit subindex ~weekly "
                                   "(NFCI Fri cadence), OFR FSI funding functional leg ~2-business-day "
                                   "lag, vol-regime risk score/MOVE percentile daily; each channel "
                                   "carries its own source clock (see the channel-score metrics)"),
        _axis("financial_conditions_impulse", "Conditions impulse", "条件边际冲量", "higher_tightening_impulse",
              impulse_value, impulse_status, impulse_null, impulse_components, impulse_avail,
              low_en="Easing impulse", low_zh="边际放松", high_en="Tightening impulse", high_zh="边际收紧",
              weights_law=_IMPULSE_WEIGHTS_LAW, transformation=_IMPULSE_METHOD_NOTE,
              frequency_alignment="13-week (NFCI/OFR FSI) and 63-day (real-10y yield) rate-of-change "
                                   "windows; NFCI/OFR FSI ~weekly cadence, real-10y-yield daily"),
    ]

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "financial_conditions",
            "title": _bil("Financial Conditions", "金融条件"),
            "subtitle": _bil("Conditions level x impulse", "条件水平 × 边际冲量"),
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
        "axes": {"items": axes_items},
        "metrics": {"items": _metrics(
            fc, ss, stress_overlay, rates, vol_regime, risk_state, asof, vintages, stale_inputs,
            rates_value, rates_status, rates_null, rates_components,
            credit_value, credit_status, credit_null, credit_components,
            dollar_funding_value, dollar_funding_status, dollar_funding_null, dollar_funding_components,
            equities_vol_value, equities_vol_status, equities_vol_null, equities_vol_components,
            lending_value, lending_status, lending_null,
            level_value, level_status, level_null,
            impulse_value, impulse_status, impulse_null,
        )},
        "series": {"items": [], "status": "ABSENT", "null_reason": "INSUFFICIENT_HISTORY"},
        "drivers": _drivers(rates_components, credit_components, dollar_funding_components,
                            equities_vol_components),
        "changes": changes,
        "implications": {"items": _implications(
            headline, level_value, impulse_value, contradiction, worst, coverage_ratio)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(asof, vintages, stale_inputs, vol_regime, rates)},
        "corrections": _corrections(fc, ss, stress_overlay, rates, vol_regime, asof, prior_snapshot),
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
def _detect_contradiction(ss: Mapping, risk_state: Mapping) -> dict:
    """Broad official stress reads calm while the market risk-appetite gauge
    disagrees (architecture 10.8 user job: "whether broad stress agrees with
    market risk appetite"). Deterministic, testable, owner-native only."""
    stress_state = ss.get("state")
    appetite_state = (risk_state.get("state") or "")
    if stress_state == "calm" and isinstance(appetite_state, str) and appetite_state.lower().startswith("risk-off"):
        en = ("OFR Financial Stress Index reads calm (broad systemic stress), but the risk-appetite "
              "gauge reads risk-off - the market's own price-based appetite disagrees with the "
              "official broad-stress read.")
        zh = "OFR金融压力指数读数为平静（广义系统性压力低），但风险偏好指标读数为风险规避——基于市场价格的风险偏好与官方广义压力读数不一致。"
        return {"present": True, "kind": "broad_stress_vs_risk_appetite", "en": en, "zh": zh,
                "components": ["equities_vol_channel", "level"]}
    return {"present": False, "kind": None, "en": None, "zh": None, "components": []}


def _required_availability(fc, ss, stress_overlay, rates, vol_regime, vintages, stale_inputs) -> list[dict]:
    nfci_p = _num(fc.get("nfci_pctile"))
    ofr_p = _num(ss.get("ofr_fsi_pctile"))
    hy_pct = _num(stress_overlay.get("hy_oas_pct"))
    real10y_p = _num(rates.get("real_10y_pctile"))
    vr_risk = _num(vol_regime.get("risk_score"))
    defs = [
        ("nfci_pctile", ("NFCI percentile", "NFCI 分位"), nfci_p,
         _vintage_freshness(nfci_p is not None, _get(vintages, "nfci"), stale_inputs, "nfci"),
         _get(vintages, "nfci", "asof")),
        ("ofr_fsi_pctile", ("OFR FSI percentile", "OFR 金融压力分位"), ofr_p,
         _vintage_freshness(ofr_p is not None, _get(vintages, "ofr_fsi"), stale_inputs, "ofr_fsi"),
         _get(vintages, "ofr_fsi", "asof")),
        ("hy_oas_pct", ("HY OAS level", "高收益利差水平"), hy_pct,
         _vintage_freshness(hy_pct is not None, _get(vintages, "hy_oas"), stale_inputs, "hy_oas"),
         _get(vintages, "hy_oas", "asof")),
        ("real_10y_pctile", ("Real 10Y yield percentile", "10年期实际收益率分位"), real10y_p,
         _vintage_freshness(real10y_p is not None, _get(vintages, "us10y"), stale_inputs, "us10y"),
         _get(vintages, "us10y", "asof")),
        ("vol_regime_risk_score", ("Vol-regime risk score", "波动率体制风险评分"), vr_risk,
         _volregime_freshness(vr_risk is not None, vol_regime), vol_regime.get("asof")),
    ]
    out = []
    for cid, (en, zh), value, fresh, src_asof in defs:
        present = value is not None
        status = "PRESENT" if present and fresh == "CURRENT" else ("PARTIAL" if present else "ABSENT")
        out.append({
            "component_id": cid,
            "label": _bil(en, zh),
            "required": True,
            "freshness": fresh,
            "status": status,
            "source_asof": src_asof,
            "null_reason": None if present else (
                "SOURCE_FAILED" if fresh == "SOURCE_FAILED" else
                "NOT_YET_RELEASED" if fresh == "NOT_YET_RELEASED" else "UNKNOWN"),
        })
    return out


def _classify(x: float, y: float) -> str:
    tight = x >= BOUNDARY
    tightening = y >= BOUNDARY
    if not tight and not tightening:
        return "A"
    if tight and tightening:
        return "B"
    if not tight and tightening:
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
                        crossed_axes.append("conditions_level")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("conditions_impulse")
                    within_band = {
                        "conditions_level": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "conditions_impulse": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
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
        near_axis = "conditions_level" if dx <= dy else "conditions_impulse"
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
        note = (f"prior quadrant held: {crossed_txt} crossed the 50 boundary since the prior print but "
                f"stayed within the {HYSTERESIS_BAND}-pt hysteresis band of ITS OWN boundary")
    else:
        crossed_txt = " and ".join(crossed_axes) if crossed_axes else "the classification"
        note = (f"prior quadrant not held: {crossed_txt} crossed the 50 boundary and moved beyond the "
                f"{HYSTERESIS_BAND}-pt hysteresis band, so the transition to the raw quadrant is accepted")

    return {
        "state_id": state_id,
        "state_label": state_label,
        "subtitle": _bil("Financial conditions regime", "金融条件体制"),
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


def _changes(headline, x_value, y_value, prior_snapshot) -> dict:
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
    for mid, cur, prev in (("financial_conditions_level", x_value, prior_x),
                          ("financial_conditions_impulse", y_value, prior_y)):
        delta = None
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            delta = round(cur - prev, 2)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur,
                       "delta": delta, "note": "same method version; numeric comparison permitted"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen,
            "prior_effective_date": prior_eff, "prior_method_version": prior_method,
            "deltas": deltas, "status": "PRESENT", "null_reason": None}


_LEVEL_WEIGHTS_LAW = (
    "weighted mean of 4 channel-score components, weights renormalized over available channels; "
    "rates_channel 0.30, credit_channel 0.30, dollar_funding_channel 0.20, equities_vol_channel 0.20 "
    "(a 5th declared channel, lending, is always ABSENT/NOT_COVERED and carries no weight here -- "
    "see the lending_channel_score metric for its own disclosure)"
)
_IMPULSE_WEIGHTS_LAW = (
    "weighted mean of 3 owner-native momentum legs, weights renormalized over available; "
    "nfci_change_13w 0.35, ofr_fsi_change_13w 0.35, real_10y_chg_63d_bp 0.30"
)
_LEVEL_METHOD_NOTE = (
    "weighted mean of 4 Mastermind channel scores (renormalized over available channels; the "
    "'lending' channel is declared but always ABSENT/NOT_COVERED -- no owner source exists): "
    "rates 0.30 (real-10y-yield percentile only, min_components=1/coverage_floor=1.0), "
    "credit 0.30 (HY OAS z 0.45 + NFCI credit subindex 0.25 + IG OAS declared-not-sourced 0.30, "
    "min_components=2/coverage_floor=0.5), dollar_funding 0.20 (OFR FSI funding functional leg 0.50 "
    "+ broad-dollar-index declared-not-sourced 0.50, min_components=1/coverage_floor=0.5), "
    "equities_vol 0.20 (vol-regime risk score 0.60 + MOVE percentile 0.40, "
    "min_components=1/coverage_floor=0.5). boundary=50.0, hysteresis_band=5.0. NONE of these "
    "channel inputs is the blended official nfci/ofr_fsi value itself (those are published "
    "separately, unmodified, as their own metrics) -- no hidden blend (architecture 7.9/10.8)."
)
_IMPULSE_METHOD_NOTE = (
    "weighted mean of 3 momentum legs (13-week/63-day rate-of-change, distinct from R1A's LEVEL-"
    "only funding_pressure axis, which never reads a _change field): NFCI 13w change 0.35 "
    "(scale=0.5 index-pt -> full half-swing), OFR FSI 13w change 0.35 (scale=1.0), real-10y-yield "
    "63d change 0.30 (scale=50bp). min_components=2/coverage_floor=0.5. boundary=50.0, "
    "hysteresis_band=5.0, positive move = tightening impulse (sign=+1 on all three legs)."
)


def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            rights_state="OPEN") -> dict:
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
        "calculation_as_of": reference_period,
        "market_session": None,
        "source_refs": source_refs or [owner_ref],
        "source_digest": None,
        "transformation": transformation,
        "model_version": METHOD_VERSION,
        "uncertainty": {"kind": None, "value": None},
        "coverage": None,
        "freshness": freshness,
        "rights_state": rights_state,
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


def _metrics(fc, ss, stress_overlay, rates, vol_regime, risk_state, asof, vintages, stale_inputs,
             rates_value, rates_status, rates_null, rates_components,
             credit_value, credit_status, credit_null, credit_components,
             dollar_funding_value, dollar_funding_status, dollar_funding_null, dollar_funding_components,
             equities_vol_value, equities_vol_status, equities_vol_null, equities_vol_components,
             lending_value, lending_status, lending_null,
             level_value, level_status, level_null,
             impulse_value, impulse_status, impulse_null) -> list[dict]:
    nfci_fresh = _vintage_freshness(fc.get("nfci_pctile") is not None, _get(vintages, "nfci"), stale_inputs, "nfci")
    ofr_fresh = _vintage_freshness(ss.get("ofr_fsi_pctile") is not None, _get(vintages, "ofr_fsi"), stale_inputs, "ofr_fsi")
    hy_fresh = _vintage_freshness(stress_overlay.get("hy_oas_pct") is not None, _get(vintages, "hy_oas"), stale_inputs, "hy_oas")
    rates_fresh = _vintage_freshness(rates.get("real_10y") is not None, _get(vintages, "us10y"), stale_inputs, "us10y")
    vr_fresh = _volregime_freshness(vol_regime.get("vix") is not None, vol_regime)

    items = [
        # --- OFFICIAL / ESTABLISHED indexes, shown separately, verbatim ---- #
        _metric("nfci", _num(fc.get("nfci")), "index", "stddev", "level", "higher_tighter",
                "engine.conditions.financial_conditions", "conditions.financial_conditions.nfci",
                _get(vintages, "nfci", "asof"), nfci_fresh,
                transformation="official Chicago Fed NFCI, unmodified pass-through; not a Mastermind composite"),
        _metric("nfci_pctile", _num(fc.get("nfci_pctile")), "percent", "pct", "level", "higher_tighter",
                "engine.conditions.financial_conditions", "conditions.financial_conditions.nfci_pctile",
                _get(vintages, "nfci", "asof"), nfci_fresh,
                transformation="official NFCI percentile rank, unmodified; IDENTICAL owner field/value to "
                               "liquidity_regime's funding_pressure axis nfci_pctile component (hand-trace)"),
        _metric("ofr_fsi", _num(ss.get("ofr_fsi")), "index", "stddev", "level", "higher_more_stress",
                "engine.conditions.systemic_stress", "conditions.systemic_stress.ofr_fsi",
                _get(vintages, "ofr_fsi", "asof"), ofr_fresh,
                transformation="official OFR Financial Stress Index, unmodified pass-through"),
        _metric("ofr_fsi_pctile", _num(ss.get("ofr_fsi_pctile")), "percent", "pct", "level", "higher_more_stress",
                "engine.conditions.systemic_stress", "conditions.systemic_stress.ofr_fsi_pctile",
                _get(vintages, "ofr_fsi", "asof"), ofr_fresh,
                transformation="official OFR FSI percentile rank, unmodified; IDENTICAL owner field/value to "
                               "liquidity_regime's funding_pressure axis ofr_fsi_pctile component (hand-trace)"),
        _metric("hy_oas_pct", _num(stress_overlay.get("hy_oas_pct")), "percent", "pct", "level",
                "higher_wider_spread", "engine.regime.liquidity_quality",
                "liquidity_quality.stress_overlay.hy_oas_pct", _get(vintages, "hy_oas", "asof"), hy_fresh,
                transformation="identical metric_id/owner_field/value to liquidity_regime's own hy_oas_pct "
                               "metric (hand-trace); level here, not the z-score used in this workspace's "
                               "credit channel"),
        _metric("hy_oas_z", _num(stress_overlay.get("hy_oas_z")), "z_score", "stddev", "level",
                "higher_wider_spread", "engine.regime.liquidity_quality",
                "liquidity_quality.stress_overlay.hy_oas_z", _get(vintages, "hy_oas", "asof"), hy_fresh,
                transformation="SAME owner field/value R1A reads internally for its funding_pressure axis "
                               "hy_oas_z component (weight 0.20 there); published here as a first-class "
                               "metric and fed into this workspace's credit_channel at weight 0.45 -- the "
                               "raw owner number agrees at the owner level, the two workspaces' USE of it "
                               "differs on purpose and is disclosed"),

        # --- rates / impulse raw legs -------------------------------------- #
        _metric("real_10y", _num(rates.get("real_10y")), "percent", "pct", "level", "higher_tighter",
                "engine.sector_rate_inflation.rate_inflation_transmission",
                "rate_inflation_transmission.state.rates.real_10y", _get(vintages, "us10y", "asof"), rates_fresh),
        _metric("real_10y_pctile", _num(rates.get("real_10y_pctile")), "percent", "pct", "level",
                "higher_tighter", "engine.sector_rate_inflation.rate_inflation_transmission",
                "rate_inflation_transmission.state.rates.real_10y_pctile", _get(vintages, "us10y", "asof"),
                rates_fresh, transformation="sole rates_channel component (min_components=1, coverage_floor=1.0)"),
        _metric("real_10y_chg_63d_bp", _num(rates.get("real_10y_chg_63d_bp")), "basis_points", "bp",
                "roc_63d", "higher_tightening_impulse", "engine.sector_rate_inflation.rate_inflation_transmission",
                "rate_inflation_transmission.state.rates.real_10y_chg_63d_bp", _get(vintages, "us10y", "asof"),
                rates_fresh, transformation="impulse leg; see financial_conditions_impulse.transformation"),
        _metric("nfci_change_13w", _num(fc.get("nfci_change_13w")), "number", "index_pts", "roc_13w",
                "higher_tightening_impulse", "engine.conditions.financial_conditions",
                "conditions.financial_conditions.nfci_change_13w", _get(vintages, "nfci", "asof"), nfci_fresh,
                transformation="impulse leg; a field R1A's funding_pressure axis never reads (level-only)"),
        _metric("ofr_fsi_change_13w", _num(ss.get("ofr_fsi_change_13w")), "number", "index_pts", "roc_13w",
                "higher_tightening_impulse", "engine.conditions.systemic_stress",
                "conditions.systemic_stress.ofr_fsi_change_13w", _get(vintages, "ofr_fsi", "asof"), ofr_fresh,
                transformation="impulse leg; a field R1A's funding_pressure axis never reads (level-only)"),
        _metric("nfci_credit_subindex", _num(_get(fc, "subindices", "nfci_credit")), "z_score", "stddev",
                "level", "higher_tighter", "engine.conditions.financial_conditions",
                "conditions.financial_conditions.subindices.nfci_credit", _get(vintages, "nfci", "asof"),
                nfci_fresh, transformation="credit_channel leg; a NFCI SUBindex, not the blended nfci value "
                                            "(no hidden blend)"),
        _metric("ofr_funding_functional", _num(_get(ss, "functional", "funding")), "z_score", "stddev",
                "level", "higher_more_stress", "engine.conditions.systemic_stress",
                "conditions.systemic_stress.functional.funding", _get(vintages, "ofr_fsi", "asof"), ofr_fresh,
                transformation="dollar_funding_channel leg; an OFR FSI functional sub-leg, not the blended "
                               "ofr_fsi value (no hidden blend)"),
        _metric("vix", _num(vol_regime.get("vix")), "index", "vol_pts", "level", "higher_more_stress",
                "engine.vol_regime", "vol_regime.vix", vol_regime.get("asof"), vr_fresh),
        _metric("vol_regime_risk_score", _num(vol_regime.get("risk_score")), "ratio", "ratio_0_1", "level",
                "higher_more_stress", "engine.vol_regime", "vol_regime.risk_score", vol_regime.get("asof"),
                vr_fresh, transformation="equities_vol_channel primary leg (weight 0.60)"),
        _metric("move_pctile", _num(vol_regime.get("move_pctile")), "percent", "pct", "level",
                "higher_more_stress", "engine.vol_regime", "vol_regime.move_pctile", vol_regime.get("asof"),
                vr_fresh, transformation="equities_vol_channel secondary leg (weight 0.40)"),
        _metric("risk_appetite_score", _num(risk_state.get("score")), "score_0_100", "score", "level",
                "higher_more_risk_off", "engine.risk_state", "risk_state.score", risk_state.get("asof"),
                "CURRENT" if risk_state.get("score") is not None else "SOURCE_FAILED",
                transformation="context only for the broad_stress_vs_risk_appetite contradiction check; "
                               "never itself a channel input"),

        # --- declared-but-not-currently-sourced legs (typed, never fabricated) #
        _metric("ig_oas_pct", None, "percent", "pct", "level", "higher_wider_spread", "N/A", "N/A", None,
                "NOT_COVERED", status="ABSENT", null_reason="NOT_COVERED", rights_state="UNKNOWN",
                transformation="declared credit_channel leg (weight 0.30); no IG OAS owner source exists "
                               "today -- architecture 10.8 failure state 'missing credit component'"),
        _metric("dollar_index_pctile", None, "percent", "pct", "level", "higher_tighter", "N/A", "N/A", None,
                "NOT_COVERED", status="ABSENT", null_reason="NOT_COVERED", rights_state="UNKNOWN",
                transformation="declared dollar_funding_channel leg (weight 0.50); no broad-dollar-index "
                               "owner source exists today -- the channel currently runs funding-only"),
        _metric("lending_channel_score", lending_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", PRODUCER, "N/A", None, "NOT_COVERED",
                status=lending_status, null_reason=lending_null, rights_state="UNKNOWN",
                transformation="declared 5th Mastermind channel (architecture 10.8); no bank-lending/G.19 "
                               "owner source is wired at all -- permanently NOT_COVERED, never defaults to "
                               "neutral/calm"),

        # --- channel composites --------------------------------------------- #
        _metric("rates_channel_score", rates_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", PRODUCER, "N/A", asof, rates_fresh if rates_value is not None else "SOURCE_FAILED",
                status=rates_status, null_reason=rates_null,
                transformation="weighted mean; real_10y_pctile only, weight 1.0, min_components=1, "
                               "coverage_floor=1.0, boundary=50.0"),
        _metric("credit_channel_score", credit_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", PRODUCER, "N/A", asof, hy_fresh if credit_value is not None else "SOURCE_FAILED",
                status=credit_status, null_reason=credit_null,
                transformation="weighted mean; hy_oas_z 0.45 + nfci_credit_subindex 0.25 + ig_oas 0.30 "
                               "(declared, never present), renormalized over available, min_components=2, "
                               "coverage_floor=0.5, boundary=50.0"),
        _metric("dollar_funding_channel_score", dollar_funding_value, "score_0_100", "score",
                "composite_prior_only", "higher_tighter", PRODUCER, "N/A", asof,
                ofr_fresh if dollar_funding_value is not None else "SOURCE_FAILED",
                status=dollar_funding_status, null_reason=dollar_funding_null,
                transformation="weighted mean; ofr_funding_functional 0.50 + dollar_index_leg 0.50 (declared, "
                               "never present), renormalized over available, min_components=1, "
                               "coverage_floor=0.5, boundary=50.0"),
        _metric("equities_vol_channel_score", equities_vol_value, "score_0_100", "score",
                "composite_prior_only", "higher_tighter", PRODUCER, "N/A", asof,
                vr_fresh if equities_vol_value is not None else "SOURCE_FAILED",
                status=equities_vol_status, null_reason=equities_vol_null,
                transformation="weighted mean; vol_regime_risk_score 0.60 + move_pctile 0.40, "
                               "min_components=1, coverage_floor=0.5, boundary=50.0"),

        # --- headline composites ---------------------------------------------- #
        _metric("financial_conditions_level", level_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", PRODUCER, "N/A", asof, "CURRENT" if level_value is not None else "SOURCE_FAILED",
                status=level_status, null_reason=level_null, transformation=_LEVEL_METHOD_NOTE),
        _metric("financial_conditions_impulse", impulse_value, "score_0_100", "score", "composite_prior_only",
                "higher_tightening_impulse", PRODUCER, "N/A", asof,
                "CURRENT" if impulse_value is not None else "SOURCE_FAILED",
                status=impulse_status, null_reason=impulse_null, transformation=_IMPULSE_METHOD_NOTE),
    ]
    return items


def _to_driver(c, unit):
    contrib = c["contribution"]
    sign = 0 if contrib is None else (1 if contrib > 0 else (-1 if contrib < 0 else 0))
    note = f"signed push = (standardized-50)*weight toward tighter; standardized={c['standardized_value']}, weight={c['weight']}"
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


def _drivers(rates_components, credit_components, dollar_funding_components, equities_vol_components) -> dict:
    # DEVIATION (see module docstring): the shared drivers block is closed to
    # exactly {rate_side, balance_sheet} -- an R1A-shaped pair. rates+credit
    # channel drivers map into rate_side; dollar/funding+equities-vol channel
    # drivers map into balance_sheet. The bucket NAME is cosmetic reuse; each
    # driver's own label/owner_field/note carries its true identity.
    rate_side = (
        [_to_driver(c, u) for c, u in zip(rates_components, ["percentile"])]
        + [_to_driver(c, u) for c, u in zip(credit_components, ["z_score", "z_score", "bp"])]
    )
    balance_sheet = (
        [_to_driver(c, u) for c, u in zip(dollar_funding_components, ["z_score", "percent"])]
        + [_to_driver(c, u) for c, u in zip(equities_vol_components, ["ratio_0_1", "percentile"])]
    )
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _implications(headline, level_value, impulse_value, contradiction, worst_freshness, coverage_ratio) -> list[dict]:
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
                f"US financial conditions read {state_id} - {label_en} (level x={level_value}, "
                f"impulse y={impulse_value}, boundary 50).",
                f"美国金融条件读数为 {state_id} - {label_zh}（水平 x={level_value}，边际冲量 y={impulse_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["rates", "credit", "dollar_funding", "equities_vol"],
            "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
            "trace_ref": "data/regime/latest.json#conditions",
        })
    else:
        items.append({
            "implication_id": "state_unavailable",
            "text": _bil(
                "US financial conditions cannot be classified: channel coverage is below the disclosed "
                "floor. No quadrant is asserted rather than defaulting to a neutral state.",
                "美国金融条件无法分类：分项覆盖低于披露下限。不默认中性状态，故不给出象限。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["rates", "credit", "dollar_funding", "equities_vol"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#conditions",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": "broad_stress_vs_risk_appetite",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["equities_vol"],
            "contradictions": [contradiction["kind"]],
            "trace_ref": "data/regime/latest.json#systemic_stress",
        })
    items.append({
        "implication_id": "driver_bucket_naming_note",
        "text": _bil(
            "The shared drivers block is closed to exactly {rate_side, balance_sheet} (R1A's pair). "
            "This workspace maps rates+credit channel drivers into rate_side and dollar_funding+"
            "equities_vol channel drivers into balance_sheet; the bucket NAME is cosmetic reuse -- "
            "each driver's own label/owner_field/note carries its true identity.",
            "共享的 drivers 结构固定为 {rate_side, balance_sheet}（源自流动性体制）。本工作区将利率+信用"
            "分项驱动因子归入 rate_side，将美元/融资+股票波动率分项驱动因子归入 balance_sheet；分桶名称"
            "仅为表面复用——每个驱动因子自身的标签/字段/说明才是其真实身份。"),
        "evidence_class": "DESCRIPTIVE",
        "confidence": conf,
        "horizon": "current",
        "channels": [],
        "contradictions": [],
        "trace_ref": "contracts/market_os/macro_workspace_snapshot.v1.schema.json#/$defs/driver",
    })
    items.append({
        "implication_id": "lending_channel_not_covered",
        "text": _bil(
            "The lending channel (architecture 10.8's fifth Mastermind channel) has no owner source "
            "wired today. It is permanently typed NOT_COVERED, never defaulted to neutral/calm.",
            "借贷分项（架构10.8的第五个Mastermind分项）目前没有接入数据源，永久标记为NOT_COVERED，不会默认为中性/平静。"),
        "evidence_class": "DESCRIPTIVE",
        "confidence": conf,
        "horizon": "current",
        "channels": ["lending"],
        "contradictions": [],
        "trace_ref": "data/regime/latest.json",
    })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "real_10y_bp", "label": _bil("10Y real yield", "10年期实际收益率"),
             "unit": "bp", "step": 10.0, "min": -200.0, "max": 200.0,
             "owner_field": "rate_inflation_transmission.state.rates.real_10y_chg_63d_bp"},
            {"assumption_id": "hy_oas_bp", "label": _bil("HY OAS", "高收益利差"),
             "unit": "bp", "step": 25.0, "min": -300.0, "max": 500.0,
             "owner_field": "liquidity_quality.stress_overlay.hy_oas_pct"},
            {"assumption_id": "ig_oas_bp", "label": _bil("IG OAS", "投资级利差"),
             "unit": "bp", "step": 10.0, "min": -150.0, "max": 300.0, "owner_field": None},
            {"assumption_id": "dollar_index_pct", "label": _bil("Broad dollar index", "广义美元指数"),
             "unit": "pct", "step": 1.0, "min": -20.0, "max": 20.0, "owner_field": None},
            {"assumption_id": "vix_level", "label": _bil("VIX", "VIX恐慌指数"),
             "unit": "index_pts", "step": 1.0, "min": 5.0, "max": 90.0, "owner_field": "vol_regime.vix"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; R3 ships no scenario execution endpoint "
                "(non-goal). A future owner-native pure scenario function produces "
                "mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "quadrant_transition", "kind": "state_transition",
             "label": _bil("Quadrant change", "象限变化"), "params": ["target_quadrant"]},
            {"condition_id": "boundary_approach", "kind": "boundary_approach",
             "label": _bil("Boundary approach", "接近分界"), "params": ["axis", "distance"]},
            {"condition_id": "component_shock", "kind": "component_shock",
             "label": _bil("Component shock", "分项冲击"), "params": ["component_id", "z"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
            {"condition_id": "category_disagreement", "kind": "contradiction_change",
             "label": _bil("Stress / risk-appetite disagreement", "压力与风险偏好背离"),
             "params": ["kind"]},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; R3 writes no alert (non-goal). Alerts extend the "
                "existing Terminal alert lifecycle later; a page shows the Alerts tab only once the "
                "service can create/list/evaluate/delete these real conditions.",
    }


_SOURCE_METRIC_MAP: dict[str, tuple[str, ...]] = {
    "nfci": ("nfci", "nfci_pctile", "nfci_change_13w", "nfci_credit_subindex"),
    "ofr_fsi": ("ofr_fsi", "ofr_fsi_pctile", "ofr_fsi_change_13w", "ofr_funding_functional"),
    "hy_oas": ("hy_oas_pct", "hy_oas_z"),
    "us10y": ("real_10y", "real_10y_pctile", "real_10y_chg_63d_bp"),
    "vol_regime": ("vix", "vol_regime_risk_score", "move_pctile"),
}


def _prior_metric_raw(prior_snapshot, metric_id):
    for m in (_get(prior_snapshot, "metrics", "items") or []):
        if m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _corrections(fc, ss, stress_overlay, rates, vol_regime, asof, prior_snapshot) -> dict:
    """Same scoped-subset supersession law as R1A (architecture 7.8): compares
    this print's published metric values for the SAME reference period against
    the predecessor's, never a persisted vintage/revision ledger."""
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
    current_vals = {
        "nfci": _num(fc.get("nfci")), "nfci_pctile": _num(fc.get("nfci_pctile")),
        "nfci_change_13w": _num(fc.get("nfci_change_13w")),
        "nfci_credit_subindex": _num(_get(fc, "subindices", "nfci_credit")),
        "ofr_fsi": _num(ss.get("ofr_fsi")), "ofr_fsi_pctile": _num(ss.get("ofr_fsi_pctile")),
        "ofr_fsi_change_13w": _num(ss.get("ofr_fsi_change_13w")),
        "ofr_funding_functional": _num(_get(ss, "functional", "funding")),
        "hy_oas_pct": _num(stress_overlay.get("hy_oas_pct")), "hy_oas_z": _num(stress_overlay.get("hy_oas_z")),
        "real_10y": _num(rates.get("real_10y")), "real_10y_pctile": _num(rates.get("real_10y_pctile")),
        "real_10y_chg_63d_bp": _num(rates.get("real_10y_chg_63d_bp")),
        "vix": _num(vol_regime.get("vix")), "vol_regime_risk_score": _num(vol_regime.get("risk_score")),
        "move_pctile": _num(vol_regime.get("move_pctile")),
    }
    changed: list[str] = []
    for source_id, metric_ids in _SOURCE_METRIC_MAP.items():
        for mid in metric_ids:
            cur = current_vals.get(mid)
            prev = _prior_metric_raw(prior_snapshot, mid)
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


def _sources(asof, vintages, stale_inputs, vol_regime, rates) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, name):
        vint = _get(vintages, name) if name else None
        fresh = _vintage_freshness(True, vint, stale_inputs, name) if name else "CURRENT"
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
        _src("nfci", "NFCI (financial conditions)", "NFCI 金融条件",
             "engine.conditions.financial_conditions", "Chicago Fed / FRED",
             _get(vintages, "nfci", "asof"), "nfci"),
        _src("ofr_fsi", "OFR Financial Stress Index", "OFR 金融压力指数",
             "engine.conditions.systemic_stress", "OFR",
             _get(vintages, "ofr_fsi", "asof"), "ofr_fsi"),
        _src("hy_oas", "HY OAS credit spread", "高收益期权调整利差",
             "engine.regime.liquidity_quality", "ICE BofA / FRED",
             _get(vintages, "hy_oas", "asof"), "hy_oas"),
        _src("us10y", "10Y nominal/real Treasury yield", "10年期名义/实际国债收益率",
             "engine.sector_rate_inflation.rate_inflation_transmission", "Treasury / FRED",
             _get(vintages, "us10y", "asof"), "us10y"),
        _src("vol_regime", "Equity/bond volatility regime (VIX, MOVE)", "股票/债券波动率体制（VIX，MOVE）",
             "engine.vol_regime", "CBOE / ICE", vol_regime.get("asof"), None),
    ]
