"""Pure composer for the US ``liquidity_regime`` workspace snapshot (F01 / R1A).

Reads owner-native artifacts (canonically ``data/regime/latest.json``) and
projects them into a ``mastermind.macro_workspace_snapshot.v1`` body. It:

* builds a dual-axis quadrant state
    x = funding pressure   (easier -> tighter)
    y = balance-sheet support (weaker -> stronger)
  with four descriptive quadrants A/B/C/D and disclosed hysteresis;
* publishes each axis's components, signs, weights, coverage floor, frequency
  alignment, thresholds, definition/data versions, and revision behaviour
  (composite/axis law, section 7.9);
* publishes rate-side and balance-sheet driver tables with signed impact;
* carries every KPI under the full metric law (section 7.4) with distinct clocks;
* emits TYPED degraded states, never zero/neutral/calm:
    - a required source missing            -> SOURCE_FAILED
    - a required source flagged stale       -> STALE_SOURCE
    - a required source not yet released    -> NOT_YET_RELEASED
    - axis coverage below the floor         -> value null + COMPUTATION_REFUSED
    - quantity expanding while quality is
      hollow/stressed                       -> a typed contradiction (DISAGREEMENT)
    - no comparable prior print             -> vector/changes WARMUP
    - prior print on a different method      -> changes METHOD_CHANGED (refuses deltas)

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive ceiling
only. Depends only on the standard library. The composer NEVER reads a wall
clock: ``built_at`` and any evaluation clock are passed in by the builder, and
freshness is derived from owner-provided source flags/vintages, so an identical
owner input always yields an identical snapshot body.
"""
from __future__ import annotations

import copy
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "liquidity_regime.compose.v1"
# Bumped 1.0.0 -> 1.1.0: adversarial review round 1 finding F1 corrected the
# hysteresis crossing rule (a method change to axes[*]/headline.hysteresis
# semantics). Architecture 7.8 requires the definition version to move on a
# method change; this constant feeds both axis.definition_version and
# metric.definition_version, so the move is disclosed directly in the
# published artifact.
AXIS_DEFINITION_VERSION = "1.1.0"
PRODUCER = "engine.market_os.macro_workspaces.liquidity_regime"

BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0
ROC_SCALE_BN = 500.0   # net-liquidity RoC that maps to a full half-axis swing
Z_SCALE = 2.5          # HY-OAS z that maps to a full half-axis swing
# F7: the ON RRP buffer is a facility balance and cannot economically go
# negative. A near-zero reading (0 <= value <= floor) is a legitimate typed
# "at the floor" disclosure; a negative reading is a data-quality failure.
RRP_FLOOR_BN = 1.0

# Quadrant labels (architecture 10.1 / reference A/B/C/D grid).
_QUADRANTS = {
    "A": {"en": "Easy funding / Strong support", "zh": "宽松融资 / 强支持"},
    "B": {"en": "Tight funding / Strong support", "zh": "紧张融资 / 强支持"},
    "C": {"en": "Easy funding / Weak support", "zh": "宽松融资 / 弱支持"},
    "D": {"en": "Tight funding / Weak support", "zh": "紧张融资 / 弱支持"},
}

_OVERLAY_SUPPORT = {"expanding": 75.0, "neutral": 50.0, "contracting": 25.0}
_QUALITY_SUPPORT = {
    "benign-expansion": 85.0,
    "stress-expansion": 55.0,
    "neutral": 50.0,
    "neutral-hollow": 40.0,
    "contracting": 20.0,
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
# small pure helpers
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


def _z_to_100(z: float | None) -> float | None:
    return None if z is None else _clamp(50.0 + (_clamp(z, -Z_SCALE, Z_SCALE) / Z_SCALE) * 50.0, 0.0, 100.0)


def _roc_to_100(roc: float | None) -> float | None:
    return None if roc is None else _clamp(50.0 + (_clamp(roc, -ROC_SCALE_BN, ROC_SCALE_BN) / ROC_SCALE_BN) * 50.0, 0.0, 100.0)


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _funding_freshness(value_present: bool, vintage: Any, stale_inputs: list, name: str) -> str:
    v = vintage if isinstance(vintage, Mapping) else {}
    if not value_present:
        return "NOT_YET_RELEASED" if v.get("not_yet_released") is True else "SOURCE_FAILED"
    if name in (stale_inputs or []) or v.get("stale") is True:
        return "STALE_SOURCE"
    return "CURRENT"


def _liquidity_freshness(value_present: bool, lq: Mapping) -> str:
    if not value_present:
        return "NOT_YET_RELEASED" if lq.get("not_yet_released") is True else "SOURCE_FAILED"
    walcl_stale = lq.get("walcl_stale_days")
    if lq.get("degraded") is True or (isinstance(walcl_stale, (int, float)) and walcl_stale > 5):
        return "STALE_SOURCE"
    return "CURRENT"


def _bil(en: str, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


# --------------------------------------------------------------------------- #
# axis component construction
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
def compose(regime_latest: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``regime_latest`` into an UNSEALED snapshot body. The builder
    seals it via ``contract.finalize`` (content_sha256 + generation_id)."""
    r = regime_latest or {}
    asof = _get(r, "asof") or _get(r, "date")
    lq = _get(r, "liquidity_quality") or {}
    cond = _get(r, "conditions") or {}
    stale_inputs = _get(cond, "stale_inputs") or []
    vintages = _get(cond, "vintages") or {}
    stress_overlay = _get(lq, "stress_overlay") or {}
    composition = _get(lq, "composition") or {}

    # ---- balance-sheet support (y) components ---------------------------- #
    overlay_raw = _get(r, "liquidity_overlay")
    overlay_std = _OVERLAY_SUPPORT.get(overlay_raw) if isinstance(overlay_raw, str) else None
    y1 = _component(
        "liquidity_overlay_level", "Net-liquidity overlay", "净流动性趋势",
        "liquidity_overlay", "engine.regime.liquidity_overlay",
        overlay_raw, overlay_std, 1, 0.35,
        _liquidity_freshness(overlay_std is not None, lq),
    )
    quality_raw = _get(lq, "label")
    quality_std = _QUALITY_SUPPORT.get(quality_raw) if isinstance(quality_raw, str) else None
    y2 = _component(
        "liquidity_quality_level", "Net-liquidity quality", "净流动性质量",
        "liquidity_quality.label", "engine.regime.liquidity_quality",
        quality_raw, quality_std, 1, 0.40,
        _liquidity_freshness(quality_std is not None, lq),
    )
    roc_raw = _num(_get(lq, "quantity_roc_bn"))
    roc_std = _roc_to_100(roc_raw)
    y3 = _component(
        "net_liquidity_roc", "Net-liquidity RoC", "净流动性变化率",
        "liquidity_quality.quantity_roc_bn", "engine.regime.liquidity_quality",
        roc_raw, roc_std, 1, 0.25,
        _liquidity_freshness(roc_std is not None, lq),
    )
    y_components = [y1, y2, y3]
    y_value, y_status, y_null, y_avail = _axis_value(y_components, min_components=2, coverage_floor=0.5)

    # ---- funding pressure (x) components -------------------------------- #
    nfci_pct = _num(_get(cond, "financial_conditions", "nfci_pctile"))
    x1 = _component(
        "nfci_pctile", "NFCI percentile", "NFCI 分位",
        "conditions.financial_conditions.nfci_pctile", "engine.conditions.financial_conditions",
        nfci_pct, _pct_to_100(nfci_pct), 1, 0.30,
        _funding_freshness(nfci_pct is not None, _get(vintages, "nfci"), stale_inputs, "nfci"),
    )
    ofr_pct = _num(_get(cond, "systemic_stress", "ofr_fsi_pctile"))
    x2 = _component(
        "ofr_fsi_pctile", "OFR FSI percentile", "OFR 金融压力分位",
        "conditions.systemic_stress.ofr_fsi_pctile", "engine.conditions.systemic_stress",
        ofr_pct, _pct_to_100(ofr_pct), 1, 0.30,
        _funding_freshness(ofr_pct is not None, _get(vintages, "ofr_fsi"), stale_inputs, "ofr_fsi"),
    )
    hy_z = _num(_get(stress_overlay, "hy_oas_z"))
    x3 = _component(
        "hy_oas_z", "HY OAS z-score", "高收益利差 z 值",
        "liquidity_quality.stress_overlay.hy_oas_z", "engine.regime.liquidity_quality",
        hy_z, _z_to_100(hy_z), 1, 0.20,
        _funding_freshness(hy_z is not None, _get(vintages, "hy_oas"), stale_inputs, "hy_oas"),
    )
    scare = _num(_get(r, "regime_vector", "rate_pressure_rates_scare_score"))
    x4 = _component(
        "rates_scare_score", "Rates scare score", "利率恐慌评分",
        "regime_vector.rate_pressure_rates_scare_score", "engine.regime.regime_vector",
        scare, (None if scare is None else _clamp(scare, 0.0, 100.0)), 1, 0.20,
        "CURRENT" if scare is not None else "SOURCE_FAILED",
    )
    x_components = [x1, x2, x3, x4]
    x_value, x_status, x_null, x_avail = _axis_value(x_components, min_components=2, coverage_floor=0.5)

    # ---- contradiction: quantity vs quality ----------------------------- #
    contradiction = _detect_contradiction(lq, roc_raw, quality_raw, stress_overlay, composition)

    # F3: a fired contradiction is a typed DISAGREEMENT on the AFFECTED axis,
    # never left silently PRESENT with the contradiction only visible in a
    # side block. The numeric axis value stays published (typed disagreement,
    # not censoring) -- only value_status / the quadrant's matching x_status
    # or y_status / the implicated components' coverage_state move to
    # DISAGREEMENT. Guarded on the axis value actually being computed: an
    # already-ABSENT axis (coverage-floor refusal) is a different typed state
    # and must not be overwritten to claim a value exists.
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

    # F7: RRP buffer floor/failure flag, threaded to the drivers note.
    rrp_raw_for_floor = _num(_get(lq, "rrp_buffer_bn"))
    rrp_floor_flag = rrp_raw_for_floor is not None and 0 <= rrp_raw_for_floor <= RRP_FLOOR_BN

    # ---- freshness roll-up over the REQUIRED set ------------------------ #
    required_ids = ("net_liquidity_roc", "liquidity_quality_level", "nfci_pctile", "ofr_fsi_pctile")
    by_id = {c["component_id"]: c for c in (y_components + x_components)}
    required_avail = _required_availability(by_id, required_ids, asof, vintages, lq)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_ids), 4)
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    # ---- quadrant + hysteresis ------------------------------------------ #
    headline = _headline(x_value, x_status, x_null, y_value, y_status, y_null,
                         asof, prior_snapshot, contradiction)

    # ---- changes vs prior accepted print -------------------------------- #
    changes = _changes(headline, x_value, y_value, prior_snapshot)

    # ---- assemble envelope ---------------------------------------------- #
    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "liquidity_regime",
            "title": _bil("Liquidity Regime Monitor", "流动性体制监测"),
            "subtitle": _bil("Funding pressure x balance-sheet support", "融资压力 × 资产负债表支持"),
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
            _axis("funding_pressure", "Funding pressure", "融资压力",
                  "higher_tighter", x_value, x_status, x_null, x_components, x_avail,
                  low_en="Easy funding", low_zh="宽松融资", high_en="Tight funding", high_zh="紧张融资",
                  weights_law="weighted mean of standardized components, weights renormalized over present components; NFCI pctile 0.30, OFR FSI pctile 0.30, HY OAS z 0.20, rates scare 0.20",
                  transformation="percentiles x100; z-score mapped 50+clamp(z/2.5,-1,1)*50; scare score passthrough (already 0-100); prior-only owner reads, no in-composer estimation",
                  frequency_alignment="mixed: NFCI/ANFCI weekly (Fri), OFR FSI ~2-business-day lag, HY OAS daily, rates scare daily; each carried with its own source clock"),
            _axis("balance_sheet_support", "Balance-sheet support", "资产负债表支持",
                  "higher_stronger", y_value, y_status, y_null, y_components, y_avail,
                  low_en="Weak support", low_zh="弱支持", high_en="Strong support", high_zh="强支持",
                  weights_law="weighted mean of standardized components, weights renormalized over present; quality label 0.40, overlay level 0.35, net-liquidity RoC 0.25",
                  transformation="owner labels mapped to descriptive support levels (benign-expansion 85 ... contracting 20); RoC mapped 50+clamp(roc/500bn,-1,1)*50; "
                                 f"RRP buffer disclosure (informational, not axis-weighted): a balance at or below {RRP_FLOOR_BN}bn carries an exhausted-floor flag in "
                                 "the implications and drivers while the value itself remains published; a negative balance is physically impossible for a facility "
                                 "and is treated as a failed source reading",
                  frequency_alignment="net-liquidity quantity/quality is weekly (Fed H.4.1 Wed, released Thu) with a 3-business-day owner lag; overlay/quality share the same cadence"),
        ]},
        "metrics": {"items": _metrics(r, lq, cond, stress_overlay, asof, vintages,
                                      x_value, y_value, x_components, y_components)},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(x_components, y_components, rrp_floor=rrp_floor_flag),
        "changes": changes,
        "implications": {"items": _implications(headline, x_value, y_value, contradiction,
                                               worst, coverage_ratio, lq)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(asof, vintages, lq, stale_inputs)},
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
def _detect_contradiction(lq, roc_raw, quality_raw, stress_overlay, composition) -> dict:
    """Quantity-vs-quality contradiction, surfaced as a typed DISAGREEMENT.
    Never let a hollow/stressed expansion read as calm support."""
    kind = None
    comps: list[str] = []
    if quality_raw == "stress-expansion":
        kind = "quantity_vs_quality"
        comps = ["net_liquidity_roc", "liquidity_quality_level"]
    elif roc_raw is not None and roc_raw > 0 and (
        lq.get("rrp_exhausted") is True
        or composition.get("mechanical") is True
        or stress_overlay.get("confirming_stress") is True
    ):
        kind = "hollow_expansion"
        comps = ["net_liquidity_roc", "liquidity_quality_level"]
    if kind is None:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    en = ("Net liquidity is expanding on quantity, but the owner's quality read flags it as "
          "hollow/stressed (RRP exhausted, mechanical composition, or confirming credit/funding stress) "
          "- the expansion is not benign support.")
    return {"present": True, "kind": kind, "en": en,
            "zh": "净流动性数量在扩张，但质量读数标记为空心/受压（逆回购枯竭、机械性构成或信用/融资压力确认），并非良性支持。",
            "components": comps}


def _required_availability(by_id, required_ids, asof, vintages, lq) -> list[dict]:
    labels = {
        "net_liquidity_roc": ("Net-liquidity RoC", "净流动性变化率"),
        "liquidity_quality_level": ("Net-liquidity quality", "净流动性质量"),
        "nfci_pctile": ("NFCI percentile", "NFCI 分位"),
        "ofr_fsi_pctile": ("OFR FSI percentile", "OFR 金融压力分位"),
    }
    src_asof = {
        "net_liquidity_roc": _get(lq, "asof") or asof,
        "liquidity_quality_level": _get(lq, "asof") or asof,
        "nfci_pctile": _get(vintages, "nfci", "asof"),
        "ofr_fsi_pctile": _get(vintages, "ofr_fsi", "asof"),
    }
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
    tight = x >= BOUNDARY
    strong = y >= BOUNDARY
    if not tight and strong:
        return "A"
    if tight and strong:
        return "B"
    if not tight and not strong:
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
    raw = None
    crossed_axes: list[str] = []
    if computable:
        raw = _classify(x_value, y_value)
        state_id = raw
        if comparable_prior:
            applied = True
            if raw != prior_id:
                # F1 fix: hysteresis may hold the prior quadrant ONLY if every
                # axis that actually crossed the 50 boundary (relative to its
                # OWN prior print value) is within the band. An axis idling
                # near its own boundary WITHOUT crossing it must never suppress
                # a decisive flip on a different axis (the old rule ORed
                # "either axis near ITS boundary", which let a calm axis
                # suppress the other's real flip).
                prior_x_num = prior_x if isinstance(prior_x, (int, float)) else None
                prior_y_num = prior_y if isinstance(prior_y, (int, float)) else None
                if prior_x_num is not None and prior_y_num is not None:
                    if (x_value >= BOUNDARY) != (prior_x_num >= BOUNDARY):
                        crossed_axes.append("funding_pressure")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("balance_sheet_support")
                    within_band = {
                        "funding_pressure": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "balance_sheet_support": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
                    }
                    # Vacuously true when crossed_axes is empty: raw != prior_id
                    # here only because prior_id was itself an earlier HELD
                    # state that no longer matches classify(prior_x, prior_y) —
                    # nothing has crossed a boundary since that print, so keep
                    # holding it.
                    if all(within_band[a] for a in crossed_axes):
                        state_id = prior_id
                        held_prior = True
                # else: no usable numeric prior axis values (e.g. WARMUP-style
                # malformed prior) -> hysteresis cannot hold anything; the raw
                # classification stands.

    if state_id is not None:
        label = _QUADRANTS[state_id]
        state_label = {"en": label["en"], "zh": label["zh"]}
        status = "PRESENT"
        null_reason = None
    else:
        state_label = {"en": None, "zh": None}
        status = "ABSENT"
        null_reason = x_null or y_null or "COMPUTATION_REFUSED"

    # nearest boundary (score units)
    if computable:
        dx = abs(x_value - BOUNDARY)
        dy = abs(y_value - BOUNDARY)
        near_axis = "funding_pressure" if dx <= dy else "balance_sheet_support"
        near_dist = round(min(dx, dy), 2)
        nb_null = None
    else:
        near_axis, near_dist, nb_null = None, None, "COMPUTATION_REFUSED"

    # one-month vector
    if computable and comparable_prior and isinstance(prior_x, (int, float)) and isinstance(prior_y, (int, float)):
        vec = {"dx": round(x_value - prior_x, 2), "dy": round(y_value - prior_y, 2),
               "status": "PRESENT", "null_reason": None}
        transition_distance = round(((x_value - prior_x) ** 2 + (y_value - prior_y) ** 2) ** 0.5, 2)
    else:
        # F6: mirror _changes()'s own comparability gate (prior_method !=
        # METHOD_VERSION -> METHOD_CHANGED/COMPUTATION_REFUSED) instead of
        # collapsing every non-WARMUP case into INSUFFICIENT_HISTORY. A prior
        # print on an incomparable method is a refused computation, not a
        # genuine lack of history.
        if prior_snapshot is None:
            vec_null = "WARMUP"
        elif prior_method != METHOD_VERSION:
            vec_null = "COMPUTATION_REFUSED"
        else:
            vec_null = "INSUFFICIENT_HISTORY"
        vec = {"dx": None, "dy": None, "status": "ABSENT", "null_reason": vec_null}
        transition_distance = None

    # F1: disclosure text describes the corrected per-axis-crossing rule.
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
        "subtitle": _bil("Rate / liquidity regime", "利率 / 流动性体制"),
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
    for mid, cur, prev in (("funding_pressure", x_value, prior_x),
                          ("balance_sheet_support", y_value, prior_y)):
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
        "definition_version": AXIS_DEFINITION_VERSION,
        "data_version": None,
        "revision_behavior": "recomputed each owner cadence from prior-only owner reads; a method-version change breaks comparability and is reported as such, never as a numeric delta",
        "authority_ceiling": "DESCRIPTIVE",
        "freshness": fresh,
    }


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


def _metrics(r, lq, cond, stress_overlay, asof, vintages, x_value, y_value,
             x_components, y_components) -> list[dict]:
    lq_asof = _get(lq, "asof") or asof
    x_fresh = _worst_freshness([c["freshness"] for c in x_components]) if x_components else "SOURCE_FAILED"
    y_fresh = _worst_freshness([c["freshness"] for c in y_components]) if y_components else "SOURCE_FAILED"
    # F7: a negative RRP buffer is physically impossible for a facility
    # balance -> typed SOURCE_FAILED, never published as a trustworthy number.
    # 0 <= value <= RRP_FLOOR_BN is a legitimate near-zero floor read: status
    # stays PRESENT (see _implications/_drivers for the 'rrp_floor' flag).
    rrp_raw = _num(_get(lq, "rrp_buffer_bn"))
    rrp_negative = rrp_raw is not None and rrp_raw < 0
    rrp_status = "SOURCE_FAILED" if rrp_negative else "PRESENT"
    rrp_null_reason = "SOURCE_FAILED" if rrp_negative else None
    items = [
        _metric("funding_pressure", x_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", "engine.market_os.macro_workspaces.liquidity_regime",
                "axes.funding_pressure", asof, x_fresh,
                transformation="weighted-mean composite; see axes[funding_pressure]"),
        _metric("balance_sheet_support", y_value, "score_0_100", "score", "composite_prior_only",
                "higher_stronger", "engine.market_os.macro_workspaces.liquidity_regime",
                "axes.balance_sheet_support", asof, y_fresh,
                transformation="weighted-mean composite; see axes[balance_sheet_support]"),
        _metric("net_liquidity_roc_bn", _num(_get(lq, "quantity_roc_bn")), "currency_bn", "USD_bn",
                "roc_over_owner_window", "higher_stronger", "engine.regime.liquidity_quality",
                "liquidity_quality.quantity_roc_bn", lq_asof,
                _liquidity_freshness(_get(lq, "quantity_roc_bn") is not None, lq)),
        _metric("rrp_buffer_bn", rrp_raw, "currency_bn", "USD_bn",
                "level", "higher_more_cushion", "engine.regime.liquidity_quality",
                "liquidity_quality.rrp_buffer_bn", lq_asof,
                "SOURCE_FAILED" if rrp_negative else _liquidity_freshness(rrp_raw is not None, lq),
                status=rrp_status, null_reason=rrp_null_reason),
        _metric("nfci", _num(_get(cond, "financial_conditions", "nfci")), "index", "stddev",
                "level", "higher_tighter", "engine.conditions.financial_conditions",
                "conditions.financial_conditions.nfci", _get(vintages, "nfci", "asof"),
                _funding_freshness(_get(cond, "financial_conditions", "nfci") is not None,
                                   _get(vintages, "nfci"), _get(cond, "stale_inputs") or [], "nfci")),
        _metric("ofr_fsi", _num(_get(cond, "systemic_stress", "ofr_fsi")), "index", "stddev",
                "level", "higher_more_stress", "engine.conditions.systemic_stress",
                "conditions.systemic_stress.ofr_fsi", _get(vintages, "ofr_fsi", "asof"),
                _funding_freshness(_get(cond, "systemic_stress", "ofr_fsi") is not None,
                                   _get(vintages, "ofr_fsi"), _get(cond, "stale_inputs") or [], "ofr_fsi")),
        _metric("hy_oas_pct", _num(_get(stress_overlay, "hy_oas_pct")), "percent", "pct",
                "level", "higher_wider_spread", "engine.regime.liquidity_quality",
                "liquidity_quality.stress_overlay.hy_oas_pct", _get(vintages, "hy_oas", "asof"),
                _funding_freshness(_get(stress_overlay, "hy_oas_pct") is not None,
                                   _get(vintages, "hy_oas"), _get(cond, "stale_inputs") or [], "hy_oas")),
        _metric("rates_scare_score", _num(_get(r, "regime_vector", "rate_pressure_rates_scare_score")),
                "score_0_100", "score", "level", "higher_tighter", "engine.regime.regime_vector",
                "regime_vector.rate_pressure_rates_scare_score", asof,
                "CURRENT" if _get(r, "regime_vector", "rate_pressure_rates_scare_score") is not None else "SOURCE_FAILED"),
    ]
    return items


def _drivers(x_components, y_components, *, rrp_floor: bool = False) -> dict:
    def _to_driver(c, unit):
        contrib = c["contribution"]
        sign = 0 if contrib is None else (1 if contrib > 0 else (-1 if contrib < 0 else 0))
        note = f"signed push = (standardized-50)*weight toward the axis high side; standardized={c['standardized_value']}, weight={c['weight']}"
        # F7: rrp_buffer_bn is informational (not itself axis-weighted); the
        # nearest weighted proxy for it is net_liquidity_roc, so the floor
        # flag surfaces there rather than inventing a new driver slot (the
        # drivers schema is closed to exactly rate_side/balance_sheet).
        if rrp_floor and c["component_id"] == "net_liquidity_roc":
            note += (f" [rrp_floor] RRP buffer is at/below its {RRP_FLOOR_BN}bn descriptive floor: "
                     "the benign RRP->reserves cushion is exhausted.")
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
        x_components, ["percentile", "percentile", "z_score", "score"])]
    balance_sheet = [_to_driver(c, u) for c, u in zip(
        y_components, ["categorical", "categorical", "USD_bn"])]
    return {"rate_side": rate_side, "balance_sheet": balance_sheet}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _implications(headline, x_value, y_value, contradiction, worst_freshness,
                  coverage_ratio, lq) -> list[dict]:
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
        # F11: the zh narrative must interpolate the zh quadrant label, never
        # the English one -- each language string stays self-contained.
        label_en = _QUADRANTS[state_id]["en"]
        label_zh = _QUADRANTS[state_id]["zh"]
        items.append({
            "implication_id": "state_descriptive",
            "text": _bil(
                f"US liquidity regime reads {state_id} - {label_en} (funding pressure x={x_value}, "
                f"balance-sheet support y={y_value}, boundary 50).",
                f"美国流动性体制读数为 {state_id} - {label_zh}（融资压力 x={x_value}，资产负债表支持 y={y_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["funding", "reserves", "credit"],
            "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
            "trace_ref": "data/regime/latest.json#liquidity_quality",
        })
    else:
        items.append({
            "implication_id": "state_unavailable",
            "text": _bil(
                "US liquidity regime cannot be classified: axis coverage is below the disclosed floor. "
                "No quadrant is asserted rather than defaulting to a neutral state.",
                "美国流动性体制无法分类：轴覆盖低于披露下限。不默认中性状态，故不给出象限。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["funding", "reserves", "credit"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#liquidity_quality",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": "quantity_quality_contradiction",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["reserves", "funding", "credit"],
            "contradictions": [contradiction["kind"]],
            "trace_ref": "data/regime/latest.json#liquidity_quality",
        })
    if lq.get("rrp_exhausted") is True:
        items.append({
            "implication_id": "rrp_exhausted_note",
            "text": _bil(
                "ON RRP buffer is at/near its floor: the benign RRP->reserves plumbing is exhausted, so "
                "further Treasury issuance drains bank reserves directly.",
                "隔夜逆回购缓冲接近下限：良性的逆回购->准备金管道已枯竭，进一步的国债发行将直接消耗银行准备金。"),
            "evidence_class": "MECHANISM_SUPPORTED",
            "confidence": conf,
            "horizon": "weeks",
            "channels": ["reserves", "funding"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#liquidity_quality.rrp_exhausted",
        })
    # F7: our own typed near-zero floor read (rrp_floor), independent of the
    # owner's own rrp_exhausted boolean above -- a diagnostics entry so a
    # zero/near-zero buffer is never a silent, unflagged PRESENT number.
    rrp_raw = _num(_get(lq, "rrp_buffer_bn"))
    if rrp_raw is not None and 0 <= rrp_raw <= RRP_FLOOR_BN:
        items.append({
            "implication_id": "rrp_floor_note",
            "text": _bil(
                f"RRP buffer reads {rrp_raw}bn, at/below the {RRP_FLOOR_BN}bn descriptive floor "
                "(rrp_floor): a typed disclosure that the buffer has essentially no further room to "
                "cushion, not a neutral reading.",
                f"逆回购缓冲读数为 {rrp_raw} 十亿美元，处于 {RRP_FLOOR_BN} 十亿美元描述性下限（rrp_floor）"
                "或以下：这是类型化披露——缓冲已基本没有进一步缓冲空间，而非中性读数。"),
            "evidence_class": "MECHANISM_SUPPORTED",
            "confidence": conf,
            "horizon": "weeks",
            "channels": ["reserves", "funding"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#liquidity_quality.rrp_buffer_bn",
        })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "policy_rate_bp", "label": _bil("Policy rate", "政策利率"),
             "unit": "bp", "step": 25.0, "min": -300.0, "max": 300.0,
             "owner_field": "regime_vector.rate_pressure"},
            {"assumption_id": "real_10y_bp", "label": _bil("10Y real yield", "10年期实际收益率"),
             "unit": "bp", "step": 10.0, "min": -200.0, "max": 200.0,
             "owner_field": "regime_vector.rate_pressure_real10y_chg63_bp"},
            {"assumption_id": "bank_reserves_bn", "label": _bil("Bank reserves", "银行准备金"),
             "unit": "USD_bn", "step": 50.0, "min": -1000.0, "max": 1000.0,
             "owner_field": "liquidity_quality.quantity_roc_bn"},
            {"assumption_id": "credit_growth_pct", "label": _bil("Credit growth", "信贷增长"),
             "unit": "pct", "step": 0.5, "min": -10.0, "max": 10.0, "owner_field": None},
            {"assumption_id": "hy_oas_bp", "label": _bil("HY OAS", "高收益利差"),
             "unit": "bp", "step": 25.0, "min": -300.0, "max": 500.0,
             "owner_field": "liquidity_quality.stress_overlay.hy_oas_pct"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; R1A ships no scenario execution endpoint (non-goal). A future owner-native pure scenario function produces mastermind.macro_workspace_scenario_result.v1 with no canonical write.",
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
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; R1A writes no alert (non-goal). Alerts extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service can create/list/evaluate/delete these real conditions.",
    }


# F8: which axis components' owner-native raw values back which named source.
_SOURCE_COMPONENT_MAP: dict[str, tuple[str, ...]] = {
    "net_liquidity": ("liquidity_overlay_level", "liquidity_quality_level", "net_liquidity_roc"),
    "nfci": ("nfci_pctile",),
    "ofr_fsi": ("ofr_fsi_pctile",),
    "hy_oas": ("hy_oas_z",),
}


def _prior_component_raw(prior_snapshot, component_id):
    for axis in (_get(prior_snapshot, "axes", "items") or []):
        for c in (axis.get("components") or []):
            if c.get("component_id") == component_id:
                return c.get("raw_value")
    return None


def _corrections(x_components, y_components, asof, prior_snapshot) -> dict:
    """F8: minimal, honest supersession detection.

    A "correction" is a REVISION of the same reference period's published
    read (predecessor's headline.effective_date == this print's asof), not
    the normal day-over-day evolution of a new observation -- a new asof is
    a new print, never a correction of the old one. changed_fingerprints
    lists which owner-native source components moved between the two prints
    of that SAME period, each as ``{source_id}:{component_id}:{digest16}``.

    This is a scoped subset of full source-vintage revision tracking (per
    adversarial review finding F8): it compares the published axis-component
    raw values captured in the predecessor print against this print's, not a
    persisted vintage/revision ledger. Sufficient to make correction_state
    honest (never hardcoded 'none' when a same-period value actually moved),
    not a complete revision-history system.
    """
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
            prev = _prior_component_raw(prior_snapshot, cid)
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


def _sources(asof, vintages, lq, stale_inputs) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, ref_period, name):
        vint = _get(vintages, name) if name else None
        fresh = _funding_freshness(True, vint, stale_inputs, name) if name else \
            _liquidity_freshness(True, lq)
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
        _src("net_liquidity", "Net liquidity (quantity + quality)", "净流动性（数量+质量）",
             "engine.regime.liquidity_quality", "Federal Reserve H.4.1 / FRED",
             _get(lq, "asof") or asof, None),
        _src("nfci", "NFCI (financial conditions)", "NFCI 金融条件",
             "engine.conditions.financial_conditions", "Chicago Fed / FRED",
             _get(vintages, "nfci", "asof"), "nfci"),
        _src("ofr_fsi", "OFR Financial Stress Index", "OFR 金融压力指数",
             "engine.conditions.systemic_stress", "OFR",
             _get(vintages, "ofr_fsi", "asof"), "ofr_fsi"),
        _src("hy_oas", "HY OAS credit spread", "高收益期权调整利差",
             "engine.regime.liquidity_quality", "ICE BofA / FRED",
             _get(vintages, "hy_oas", "asof"), "hy_oas"),
    ]
