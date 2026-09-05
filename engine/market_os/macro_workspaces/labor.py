"""Pure composer for the US ``labor_markets`` workspace snapshot (F01 / R2, Labor
workspace lane).

Reads owner-native artifacts (canonically ``data/regime/latest.json``) and
projects them into a ``mastermind.macro_workspace_snapshot.v1`` body. It:

* builds a dual-axis quadrant state
    x = labor demand          (weakening -> strengthening)
    y = labor supply/tightness (loose -> tight)
  with four descriptive quadrants A/B/C/D and disclosed hysteresis, mirroring
  the ``liquidity_regime`` R1A pattern exactly (component/axis construction,
  coverage-floor refusal, typed DISAGREEMENT, hysteresis, changes, corrections,
  sources, scenario/alert contracts);
* publishes each axis's components, signs, weights, coverage floor, frequency
  alignment, thresholds, definition/data versions, and revision behaviour
  (composite/axis law, architecture section 7.9);
* carries every KPI under the full metric law (section 7.4) with distinct
  clocks;
* emits TYPED degraded states, never zero/neutral/calm:
    - a required source missing            -> SOURCE_FAILED
    - a required source flagged stale       -> STALE_SOURCE
    - a required source not yet released    -> NOT_YET_RELEASED
    - axis coverage below the floor         -> value null + COMPUTATION_REFUSED
    - claims calm while hiring/income lags  -> a typed contradiction (DISAGREEMENT)
    - no comparable prior print             -> vector/changes WARMUP
    - prior print on a different method     -> changes METHOD_CHANGED (refuses deltas)
  and, per the Labor-specific care in this producer's brief, a whole FAMILY of
  required-but-currently-unpublished capabilities (payroll net-revision history,
  ADP-vs-BLS/household disagreement, unemployment rate, participation, JOLTS
  openings/quits, true average-hourly-earnings wage growth) is carried as typed
  ABSENT metrics with a method-text disclosure, never silently dropped.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive ceiling
only. Depends only on the standard library. The composer NEVER reads a wall
clock: ``built_at`` and any evaluation clock are passed in by the builder, and
freshness is derived from owner-provided source flags/vintages, so an identical
owner input always yields an identical snapshot body.

--------------------------------------------------------------------------
KNOWN CONTRACT GAP (deviation, not silently worked around -- see this
producer's final report for the full write-up):

``contracts/market_os/macro_workspace_snapshot.v1.schema.json`` was authored
for the single R1A workspace and currently hard-codes two liquidity-specific
literals that this module cannot avoid without a shared-file schema change
(explicitly out of scope for a producer worker):

  * ``$defs.axis.properties.axis_id.enum`` is closed to exactly
    ``["funding_pressure", "balance_sheet_support"]``. This module publishes
    the semantically-correct ``labor_demand`` / ``labor_supply_tightness``
    axis ids (matching the Labor blueprint's headline model verbatim), so a
    strict ``contract.validate()`` call on a finalized labor snapshot will
    currently fail on that one enum. Every OTHER closed-schema rule (required
    keys, nested $defs, presence/null vocab, drivers block, etc.) is satisfied
    -- see ``tests/test_macro_workspace_labor.py::test_schema_conformant_modulo_axis_id_enum``
    for the isolating proof.
  * ``drivers`` requires exactly the two liquidity-named keys ``rate_side`` /
    ``balance_sheet``. This module reuses those literal key names (required by
    the closed schema) to carry the labor-demand-axis and
    labor-supply-tightness-axis driver groups respectively; the key NAMES are
    a schema artifact inherited unchanged from R1A, not a domain claim that
    labor drivers are "rates" or "balance sheet" data.

Widening the axis_id enum (and, ideally, renaming/generalizing the drivers
keys) for the whole twelve-workspace suite is a one-time shared-schema change
that should land once, coordinated across every R2-wave producer hitting the
same wall, not per-workspace.
--------------------------------------------------------------------------
"""
from __future__ import annotations

import copy
from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "labor_markets.compose.v1"
AXIS_DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.labor"

BOUNDARY = 50.0
HYSTERESIS_BAND = 5.0
Z_SCALE = 2.5                  # claims z-score that maps to a full half-axis swing
INDEED_CHG_SCALE_PCT = 10.0    # 3-month Indeed postings change (%) for a full swing
WITHHELD_TAX_SCALE_PCT = 8.0   # withheld-tax YoY (%) for a full swing
SAHM_SCALE = 0.50              # the canonical NBER/Sahm-rule recession-trigger level

# Quadrant labels (Labor headline model: x = labor demand, y = labor
# supply/tightness). Mirrors liquidity_regime._classify's exact branch
# structure with x playing the "tight" role and y playing the "strong" role.
_QUADRANTS = {
    "A": {"en": "Cooling demand / Tight market", "zh": "需求降温 / 市场偏紧"},
    "B": {"en": "Strong hiring / Tight market", "zh": "招聘强劲 / 市场偏紧"},
    "C": {"en": "Weak demand / Loose market", "zh": "需求疲软 / 市场宽松"},
    "D": {"en": "Strong demand / Loose market", "zh": "需求强劲 / 市场宽松"},
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
# small pure helpers (duplicated from the liquidity_regime pattern rather than
# imported -- each domain module in engine/market_os/macro_workspaces/ is a
# self-contained producer per architecture 11.1; there is no shared-helpers
# module to import from without creating unwanted cross-domain coupling)
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


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


def _labor_freshness(value_present: bool, vintage: Any, stale_inputs: list, name: str) -> str:
    """Mirrors liquidity_regime._funding_freshness exactly: the ``conditions``
    block (vintages / stale_inputs) is a TOP-LEVEL shared block in
    ``data/regime/latest.json``, not liquidity-specific -- Labor reads the same
    structure under its own field names (``claims``, ``indeed``, ``withheld_tax``,
    ``sahm``, ``recession_claims``). None of these currently have a vintage
    entry published (unlike nfci/ofr_fsi/hy_oas), so in practice every present
    labor field reads CURRENT today; the vintage/stale_inputs lookups are kept
    so a future owner addition of per-field labor vintages is honoured for
    free, and so STALE_SOURCE / NOT_YET_RELEASED are real, testable code paths
    rather than dead branches."""
    v = vintage if isinstance(vintage, Mapping) else {}
    if not value_present:
        return "NOT_YET_RELEASED" if v.get("not_yet_released") is True else "SOURCE_FAILED"
    if name in (stale_inputs or []) or v.get("stale") is True:
        return "STALE_SOURCE"
    return "CURRENT"


# --------------------------------------------------------------------------- #
# axis component construction (identical shape to liquidity_regime._component)
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
    # Both blocks live INSIDE conditions in the real owner artifact
    # (conditions.labor_nowcast / conditions.recession) — verified against
    # data/regime/latest.json 2026-09-04 after the first real build published
    # SOURCE_FAILED from a top-level read. Fall back to top-level for older
    # fixture shapes rather than silently refusing either layout.
    _conditions = _get(r, "conditions") or {}
    labor = _get(_conditions, "labor_nowcast") or _get(r, "labor_nowcast") or {}
    recession = _get(_conditions, "recession") or _get(r, "recession") or {}
    cond = _get(r, "conditions") or {}
    stale_inputs = _get(cond, "stale_inputs") or []
    vintages = _get(cond, "vintages") or {}

    claims_trend = _get(labor, "claims_trend")
    indeed_trend = _get(labor, "indeed_trend")
    income_trend = _get(labor, "income_trend")

    # ---- labor demand (x) components -------------------------------------- #
    claims_z = _num(_get(labor, "claims_z"))
    claims_std = None if claims_z is None else _clamp(
        50.0 - (_clamp(claims_z, -Z_SCALE, Z_SCALE) / Z_SCALE) * 50.0, 0.0, 100.0)
    x1 = _component(
        "claims_momentum", "Initial-claims momentum", "初请失业金动能",
        "labor_nowcast.claims_z", "engine.regime.labor_nowcast",
        claims_z, claims_std, 1, 0.40,
        _labor_freshness(claims_z is not None, _get(vintages, "claims"), stale_inputs, "claims"),
    )
    indeed_chg = _num(_get(labor, "indeed_chg_3m_pct"))
    indeed_std = None if indeed_chg is None else _clamp(
        50.0 + (_clamp(indeed_chg, -INDEED_CHG_SCALE_PCT, INDEED_CHG_SCALE_PCT) / INDEED_CHG_SCALE_PCT) * 50.0,
        0.0, 100.0)
    x2 = _component(
        "job_postings_momentum", "Job-postings momentum (Indeed)", "职位发布动能（Indeed）",
        "labor_nowcast.indeed_chg_3m_pct", "engine.regime.labor_nowcast",
        indeed_chg, indeed_std, 1, 0.35,
        _labor_freshness(indeed_chg is not None, _get(vintages, "indeed"), stale_inputs, "indeed"),
    )
    withheld_yoy = _num(_get(labor, "withheld_tax_yoy_pct"))
    withheld_std = None if withheld_yoy is None else _clamp(
        50.0 + (_clamp(withheld_yoy, -WITHHELD_TAX_SCALE_PCT, WITHHELD_TAX_SCALE_PCT) / WITHHELD_TAX_SCALE_PCT) * 50.0,
        0.0, 100.0)
    x3 = _component(
        "income_growth_proxy", "Withheld-tax income growth (proxy)", "预扣税收入增长（代理指标）",
        "labor_nowcast.withheld_tax_yoy_pct", "engine.regime.labor_nowcast",
        withheld_yoy, withheld_std, 1, 0.25,
        _labor_freshness(withheld_yoy is not None, _get(vintages, "withheld_tax"), stale_inputs, "withheld_tax"),
    )
    x_components = [x1, x2, x3]
    x_value, x_status, x_null, x_avail = _axis_value(x_components, min_components=2, coverage_floor=0.5)

    # ---- labor supply/tightness (y) components ----------------------------- #
    sahm = _num(_get(recession, "sahm"))
    sahm_std = None if sahm is None else _clamp(
        50.0 - (_clamp(sahm, -SAHM_SCALE, SAHM_SCALE) / SAHM_SCALE) * 50.0, 0.0, 100.0)
    y1 = _component(
        "sahm_rule_level", "Sahm rule level", "萨姆规则水平",
        "recession.sahm", "engine.regime.recession",
        sahm, sahm_std, 1, 0.55,
        _labor_freshness(sahm is not None, _get(vintages, "sahm"), stale_inputs, "sahm"),
    )
    claims_recession = _num(_get(recession, "components", "claims"))
    claims_recession_std = None if claims_recession is None else _clamp(
        100.0 - _clamp(claims_recession, 0.0, 1.0) * 100.0, 0.0, 100.0)
    y2 = _component(
        "claims_recession_subscore", "Claims-based recession subscore", "基于初请的衰退子评分",
        "recession.components.claims", "engine.regime.recession",
        claims_recession, claims_recession_std, 1, 0.45,
        _labor_freshness(claims_recession is not None, _get(vintages, "recession_claims"),
                         stale_inputs, "recession_claims"),
    )
    y_components = [y1, y2]
    y_value, y_status, y_null, y_avail = _axis_value(y_components, min_components=2, coverage_floor=0.5)

    # ---- contradiction: claims calm vs hiring/income lagging --------------- #
    contradiction = _detect_contradiction(claims_trend, indeed_trend, income_trend)
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

    # ---- freshness roll-up over the REQUIRED set --------------------------- #
    required_ids = ("claims_momentum", "job_postings_momentum", "sahm_rule_level",
                    "claims_recession_subscore")
    by_id = {c["component_id"]: c for c in (x_components + y_components)}
    required_avail = _required_availability(by_id, required_ids, asof)
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_ids), 4)
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    # ---- quadrant + hysteresis --------------------------------------------- #
    headline = _headline(x_value, x_status, x_null, y_value, y_status, y_null,
                         asof, prior_snapshot, contradiction)

    # ---- changes vs prior accepted print ------------------------------------ #
    changes = _changes(headline, x_value, y_value, prior_snapshot)

    # ---- assemble envelope --------------------------------------------------- #
    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "labor_markets",
            "title": _bil("Labor Markets", "劳动力市场"),
            "subtitle": _bil("Labor demand x labor supply/tightness", "劳动力需求 × 劳动力供给/紧张度"),
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
            _axis("labor_demand", "Labor demand", "劳动力需求",
                  "higher_stronger", x_value, x_status, x_null, x_components, x_avail,
                  low_en="Weakening demand", low_zh="需求走弱", high_en="Strengthening demand", high_zh="需求走强",
                  weights_law="weighted mean of standardized components, weights renormalized over present components; initial-claims momentum 0.40, Indeed job-postings momentum 0.35, withheld-tax income-growth proxy 0.25",
                  transformation="claims z-score inverted and mapped 50-clamp(z/2.5,-1,1)*50 (elevated claims = weaker demand); Indeed 3m change and withheld-tax YoY mapped 50+clamp(pct/scale,-1,1)*50; prior-only owner reads, no in-composer estimation",
                  frequency_alignment="mixed: initial-claims 4-week average is weekly (Thu, DOL/FRED); Indeed job-postings index refreshes weekly (Indeed Hiring Lab); withheld-tax YoY is a daily-accrual Treasury proxy; each carried against the same shared calculation_as_of because the current owner artifact (data/regime/latest.json#labor_nowcast) does not yet publish a per-field vintage the way conditions.vintages does for nfci/ofr_fsi/hy_oas -- a disclosed limitation, not a silent one"),
            _axis("labor_supply_tightness", "Labor supply / tightness", "劳动力供给 / 紧张度",
                  "higher_tighter", y_value, y_status, y_null, y_components, y_avail,
                  low_en="Loose market", low_zh="市场宽松", high_en="Tight market", high_zh="市场偏紧",
                  weights_law="weighted mean of standardized components, weights renormalized over present; Sahm rule level 0.55, claims-based recession subscore 0.45",
                  transformation=f"Sahm rule inverted and mapped 50-clamp(sahm/{SAHM_SCALE},-1,1)*50 against the canonical {SAHM_SCALE}-point NBER/Sahm recession-trigger scale (lower sahm = tighter); claims-recession subscore inverted 100-clamp(score,0,1)*100",
                  frequency_alignment="Sahm rule is derived from the monthly BLS unemployment rate (first Friday, Employment Situation); the claims-based recession subscore shares the weekly claims cadence used on the demand axis -- two different native cadences carried under one axis, each with its own owner_ref"),
        ]},
        "metrics": {"items": _metrics(labor, recession, asof, x_value, y_value,
                                      x_components, y_components, vintages, stale_inputs)},
        "series": {
            "items": [],
            "status": "ABSENT",
            "null_reason": "INSUFFICIENT_HISTORY",
        },
        "drivers": _drivers(x_components, y_components),
        "changes": changes,
        "implications": {"items": _implications(headline, x_value, y_value, contradiction,
                                               worst, coverage_ratio)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(asof, vintages, stale_inputs)},
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
def _detect_contradiction(claims_trend, indeed_trend, income_trend) -> dict:
    """Two named contradiction kinds, both implicating the DEMAND (x) axis --
    calm initial claims alone never gets to assert unambiguous labor-market
    strength when the hiring or income signal disagrees. Mirrors
    liquidity_regime._detect_contradiction's two-kind, typed-DISAGREEMENT
    pattern exactly, just with both kinds landing on x instead of y."""
    kind = None
    comps: list[str] = []
    if claims_trend == "falling" and indeed_trend == "falling":
        kind = "low_hires_low_fires"
        comps = ["claims_momentum", "job_postings_momentum"]
    elif claims_trend == "falling" and income_trend == "falling":
        kind = "claims_income_divergence"
        comps = ["claims_momentum", "income_growth_proxy"]
    if kind is None:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    if kind == "low_hires_low_fires":
        en = ("Initial claims are falling (few new layoffs) while Indeed job postings are ALSO "
              "falling (few new openings) - a 'low hires, low fires' freeze, not confirmed labor-market "
              "strength: calm claims alone can mask a hiring slowdown.")
        zh = ("初请失业金人数下降（裁员少），但Indeed职位发布数同样在下降（新增招聘少）——"
              "这是一种'低招聘、低裁员'的停滞状态，并非确认的劳动力市场强劲：单看初请数据平静可能掩盖招聘放缓。")
    else:
        en = ("Initial claims are falling (few new layoffs) while the withheld-tax income proxy is ALSO "
              "falling (aggregate paycheck growth weakening) - claims alone read calm while the income "
              "signal disagrees.")
        zh = ("初请失业金人数下降（裁员少），但预扣税收入代理指标同样在下降（总薪资增长走弱）——"
              "单看初请数据平静，但收入信号并不一致。")
    return {"present": True, "kind": kind, "en": en, "zh": zh, "components": comps}


def _required_availability(by_id, required_ids, asof) -> list[dict]:
    labels = {
        "claims_momentum": ("Initial-claims momentum", "初请失业金动能"),
        "job_postings_momentum": ("Job-postings momentum (Indeed)", "职位发布动能（Indeed）"),
        "sahm_rule_level": ("Sahm rule level", "萨姆规则水平"),
        "claims_recession_subscore": ("Claims-based recession subscore", "基于初请的衰退子评分"),
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
            # No per-field vintage exists for labor components today (see the
            # frequency_alignment disclosure on the demand axis) -- the whole
            # snapshot shares one calculation clock until the owner publishes
            # per-field labor vintages the way it already does for nfci/ofr_fsi.
            "source_asof": asof,
            "null_reason": comp.get("null_reason") if not present else None,
        })
    return out


def _classify(x: float, y: float) -> str:
    strengthening = x >= BOUNDARY
    tight = y >= BOUNDARY
    if not strengthening and tight:
        return "A"
    if strengthening and tight:
        return "B"
    if not strengthening and not tight:
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
                prior_x_num = prior_x if isinstance(prior_x, (int, float)) else None
                prior_y_num = prior_y if isinstance(prior_y, (int, float)) else None
                if prior_x_num is not None and prior_y_num is not None:
                    if (x_value >= BOUNDARY) != (prior_x_num >= BOUNDARY):
                        crossed_axes.append("labor_demand")
                    if (y_value >= BOUNDARY) != (prior_y_num >= BOUNDARY):
                        crossed_axes.append("labor_supply_tightness")
                    within_band = {
                        "labor_demand": abs(x_value - BOUNDARY) <= HYSTERESIS_BAND,
                        "labor_supply_tightness": abs(y_value - BOUNDARY) <= HYSTERESIS_BAND,
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
        near_axis = "labor_demand" if dx <= dy else "labor_supply_tightness"
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
        "subtitle": _bil("Labor demand / supply-tightness regime", "劳动力需求 / 供给紧张度状态"),
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
    for mid, cur, prev in (("labor_demand", x_value, prior_x),
                          ("labor_supply_tightness", y_value, prior_y)):
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


def _metrics(labor, recession, asof, x_value, y_value, x_components, y_components,
             vintages, stale_inputs) -> list[dict]:
    x_fresh = _worst_freshness([c["freshness"] for c in x_components]) if x_components else "SOURCE_FAILED"
    y_fresh = _worst_freshness([c["freshness"] for c in y_components]) if y_components else "SOURCE_FAILED"

    initial_claims = _num(_get(labor, "initial_claims_4wk"))
    continued_claims = _num(_get(labor, "continued_claims"))
    claims_yoy = _num(_get(labor, "claims_yoy_pct"))
    claims_z = _num(_get(labor, "claims_z"))
    indeed_level = _num(_get(labor, "indeed_postings"))
    indeed_chg = _num(_get(labor, "indeed_chg_3m_pct"))
    withheld_yoy = _num(_get(labor, "withheld_tax_yoy_pct"))
    sahm = _num(_get(recession, "sahm"))
    claims_recession = _num(_get(recession, "components", "claims"))

    items = [
        _metric("labor_demand", x_value, "score_0_100", "score", "composite_prior_only",
                "higher_stronger", "engine.market_os.macro_workspaces.labor",
                "axes.labor_demand", asof, x_fresh,
                transformation="weighted-mean composite; see axes[labor_demand]"),
        _metric("labor_supply_tightness", y_value, "score_0_100", "score", "composite_prior_only",
                "higher_tighter", "engine.market_os.macro_workspaces.labor",
                "axes.labor_supply_tightness", asof, y_fresh,
                transformation="weighted-mean composite; see axes[labor_supply_tightness]"),
        _metric("initial_claims_4wk", initial_claims, "count", "persons", "four_week_moving_average",
                "higher_weaker", "engine.regime.labor_nowcast", "labor_nowcast.initial_claims_4wk",
                asof, _labor_freshness(initial_claims is not None, _get(vintages, "claims"),
                                       stale_inputs, "claims")),
        _metric("continued_claims", continued_claims, "count", "persons", "level",
                "higher_weaker", "engine.regime.labor_nowcast", "labor_nowcast.continued_claims",
                asof, _labor_freshness(continued_claims is not None, _get(vintages, "claims"),
                                       stale_inputs, "claims"),
                transformation="published informationally only -- no owner-provided percentile/z-score "
                               "exists for this raw level, so it is NOT fed into the labor_supply_tightness "
                               "axis (no in-composer estimation of a standardization scale)"),
        _metric("claims_yoy_pct", claims_yoy, "percent", "pct", "year_over_year",
                "higher_weaker", "engine.regime.labor_nowcast", "labor_nowcast.claims_yoy_pct",
                asof, _labor_freshness(claims_yoy is not None, _get(vintages, "claims"),
                                       stale_inputs, "claims")),
        _metric("claims_z", claims_z, "z_score", "stddev", "level",
                "higher_weaker", "engine.regime.labor_nowcast", "labor_nowcast.claims_z",
                asof, _labor_freshness(claims_z is not None, _get(vintages, "claims"),
                                       stale_inputs, "claims")),
        _metric("indeed_postings_index", indeed_level, "index", "index", "level",
                "higher_stronger", "engine.regime.labor_nowcast", "labor_nowcast.indeed_postings",
                asof, _labor_freshness(indeed_level is not None, _get(vintages, "indeed"),
                                       stale_inputs, "indeed")),
        _metric("indeed_chg_3m_pct", indeed_chg, "percent", "pct", "three_month_change",
                "higher_stronger", "engine.regime.labor_nowcast", "labor_nowcast.indeed_chg_3m_pct",
                asof, _labor_freshness(indeed_chg is not None, _get(vintages, "indeed"),
                                       stale_inputs, "indeed")),
        _metric("withheld_tax_yoy_pct", withheld_yoy, "percent", "pct", "year_over_year",
                "higher_stronger", "engine.regime.labor_nowcast", "labor_nowcast.withheld_tax_yoy_pct",
                asof, _labor_freshness(withheld_yoy is not None, _get(vintages, "withheld_tax"),
                                       stale_inputs, "withheld_tax"),
                transformation="proxy for aggregate wage-and-employment income growth (Treasury daily "
                               "withholding accrual), NOT the BLS average-hourly-earnings wage-growth "
                               "series -- see avg_hourly_earnings_yoy for the true (currently absent) wage metric"),
        _metric("sahm_rule_value", sahm, "ratio", "pp", "level",
                "higher_looser", "engine.regime.recession", "recession.sahm",
                asof, _labor_freshness(sahm is not None, _get(vintages, "sahm"), stale_inputs, "sahm")),
        _metric("recession_claims_subscore", claims_recession, "ratio", "score_0_1", "level",
                "higher_weaker", "engine.regime.recession", "recession.components.claims",
                asof, _labor_freshness(claims_recession is not None, _get(vintages, "recession_claims"),
                                       stale_inputs, "recession_claims")),
        # ---- typed ABSENT: required-by-blueprint capabilities with no
        # currently published owner artifact. Per this producer's Labor-
        # specific care instruction: payrolls carry revision history as
        # first-class economics; when the owner doesn't expose it, that is a
        # typed ABSENT slot with method-text disclosure, never silence.
        _metric("payrolls_nfp_change_and_revision", None, "count", "persons_thousands", "level",
                "higher_stronger", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="BLS establishment survey publishes a net revision to the PRIOR TWO "
                               "MONTHS' nonfarm-payroll change with every new monthly print (first "
                               "Friday). No currently published Mastermind owner artifact carries a "
                               "multi-vintage NFP series: data/release_forecast/latest.json's "
                               "actual/actual_first fields hold at most one vintage per period today "
                               "(insufficient to derive a revision delta), and PAYEMS_all_vintages.parquet "
                               "under data/fred_vintage/release_targets/ is a binary vintage store this "
                               "JSON-only producer does not parse. Structural gap, not a transient outage."),
        _metric("unemployment_rate_u3", None, "percent", "pct", "level",
                "higher_looser", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="BLS U-3 unemployment rate is not currently published by any "
                               "data/*.json or site/*.json owner artifact this producer can read; the "
                               "engine derives the Sahm rule from it internally but does not re-publish "
                               "the underlying rate."),
        _metric("labor_force_participation_rate", None, "percent", "pct", "level",
                "higher_stronger", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="Not currently published by any owner artifact this producer can read."),
        _metric("jolts_job_openings", None, "count", "persons_thousands", "level",
                "higher_tighter", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="Not currently published by any owner artifact this producer can read "
                               "(JOLTS runs on a ~6-week reporting lag; no owner adapter found)."),
        _metric("jolts_quits_rate", None, "percent", "pct", "level",
                "higher_tighter", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="Not currently published by any owner artifact this producer can read."),
        _metric("avg_hourly_earnings_yoy", None, "percent", "pct", "year_over_year",
                "higher_tighter", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="The true BLS average-hourly-earnings wage-growth series is not "
                               "currently published by any owner artifact this producer can read; "
                               "withheld_tax_yoy_pct is carried separately as an explicitly-labeled "
                               "proxy and must not be read as this series."),
        _metric("adp_bls_payroll_divergence", None, "count", "persons_thousands", "level",
                "higher_stronger", "engine.market_os.macro_workspaces.labor", "UNPUBLISHED",
                None, "SOURCE_FAILED", status="ABSENT", null_reason="NOT_COVERED",
                transformation="Architecture 10.5 names 'payroll/household/claims disagreement' "
                               "(ADP-vs-BLS / establishment-vs-household survey) as a required, lawful "
                               "DISAGREEMENT case. No ADP employment series or BLS household (CPS) "
                               "unemployment series is currently published by any owner artifact this "
                               "producer can read, so this contradiction cannot be lawfully computed "
                               "today; it is disclosed ABSENT rather than fabricated."),
    ]
    return items


def _drivers(x_components, y_components) -> dict:
    """The closed schema's ``drivers`` block requires exactly the two
    liquidity-named keys ``rate_side`` / ``balance_sheet`` (see the module
    docstring's KNOWN CONTRACT GAP). They are reused here, unchanged, to carry
    the labor_demand-axis and labor_supply_tightness-axis driver groups
    respectively -- the key NAMES are a schema artifact inherited from R1A,
    not a domain claim."""
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
    demand_drivers = [_to_driver(c, u) for c, u in zip(
        x_components, ["z_score", "percent", "percent"])]
    tightness_drivers = [_to_driver(c, u) for c, u in zip(
        y_components, ["ratio", "ratio"])]
    return {"rate_side": demand_drivers, "balance_sheet": tightness_drivers}


def _band(v, lo, hi):
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _implications(headline, x_value, y_value, contradiction, worst_freshness, coverage_ratio) -> list[dict]:
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
                f"US labor market reads {state_id} - {label_en} (labor demand x={x_value}, "
                f"labor supply/tightness y={y_value}, boundary 50).",
                f"美国劳动力市场读数为 {state_id} - {label_zh}（劳动力需求 x={x_value}，"
                f"劳动力供给/紧张度 y={y_value}，分界 50）。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["hiring", "layoffs", "wages"],
            "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
            "trace_ref": "data/regime/latest.json#labor_nowcast",
        })
    else:
        items.append({
            "implication_id": "state_unavailable",
            "text": _bil(
                "US labor-market state cannot be classified: axis coverage is below the disclosed "
                "floor. No quadrant is asserted rather than defaulting to a neutral state.",
                "美国劳动力市场状态无法分类：轴覆盖低于披露下限。不默认中性状态，故不给出象限。"),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["hiring", "layoffs", "wages"],
            "contradictions": [],
            "trace_ref": "data/regime/latest.json#labor_nowcast",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": f"{contradiction['kind']}_contradiction",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE",
            "confidence": conf,
            "horizon": "current",
            "channels": ["hiring", "layoffs", "wages"],
            "contradictions": [contradiction["kind"]],
            "trace_ref": "data/regime/latest.json#labor_nowcast",
        })
    return items


def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "initial_claims_4wk_k", "label": _bil("Initial claims (4wk avg)", "初请失业金（4周均值）"),
             "unit": "persons_thousands", "step": 5.0, "min": 150.0, "max": 500.0,
             "owner_field": "labor_nowcast.initial_claims_4wk"},
            {"assumption_id": "payroll_change_k", "label": _bil("Payroll change", "非农就业变动"),
             "unit": "persons_thousands", "step": 25.0, "min": -500.0, "max": 500.0,
             "owner_field": None},
            {"assumption_id": "unemployment_rate_pp", "label": _bil("Unemployment rate", "失业率"),
             "unit": "pp", "step": 0.1, "min": 2.0, "max": 12.0, "owner_field": None},
            {"assumption_id": "wage_growth_pct", "label": _bil("Wage growth (proxy)", "薪资增长（代理指标）"),
             "unit": "pct", "step": 0.25, "min": -5.0, "max": 10.0,
             "owner_field": "labor_nowcast.withheld_tax_yoy_pct"},
        ],
        "status": "PARTIAL",
        "note": "Assumption vocabulary is declared and closed; this producer ships no scenario execution "
                "endpoint (non-goal). payroll_change_k and unemployment_rate_pp carry no owner_field "
                "because no owner artifact currently publishes NFP level or U-3 (see the ABSENT metrics "
                "above) -- they are declared for forward compatibility, not backed by a live read today.",
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "sahm_risk_state", "kind": "state_transition",
             "label": _bil("Sahm-style risk state", "萨姆规则风险状态"), "params": ["target_state"]},
            {"condition_id": "claims_break", "kind": "component_shock",
             "label": _bil("Claims break", "初请数据突变"), "params": ["component_id", "z"]},
            {"condition_id": "wage_persistence", "kind": "component_shock",
             "label": _bil("Wage/income persistence", "薪资/收入持续性"), "params": ["component_id", "z"]},
            {"condition_id": "source_revision", "kind": "source_revision",
             "label": _bil("Material source revision", "数据源重大修订"), "params": ["source_id"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed (data outage)", "数据源过期或失败（数据中断）"),
             "params": ["source_id"]},
            {"condition_id": "low_hires_low_fires", "kind": "contradiction_change",
             "label": _bil("Low-hires/low-fires contradiction", "低招聘/低裁员矛盾"), "params": []},
        ],
        "status": "ABSENT",
        "note": "Eligible condition types are declared; this producer writes no alert (non-goal). Alerts "
                "extend the existing Terminal alert lifecycle later; a page shows the Alerts tab only "
                "once the service can create/list/evaluate/delete these real conditions.",
    }


_SOURCE_COMPONENT_MAP: dict[str, tuple[str, ...]] = {
    "claims": ("claims_momentum",),
    "indeed": ("job_postings_momentum",),
    "withheld_tax": ("income_growth_proxy",),
    "sahm": ("sahm_rule_level",),
    "recession_claims": ("claims_recession_subscore",),
}


def _prior_component_raw(prior_snapshot, component_id):
    for axis in (_get(prior_snapshot, "axes", "items") or []):
        for c in (axis.get("components") or []):
            if c.get("component_id") == component_id:
                return c.get("raw_value")
    return None


def _corrections(x_components, y_components, asof, prior_snapshot) -> dict:
    """Minimal, honest supersession detection -- mirrors
    liquidity_regime._corrections exactly (F8 pattern): a "correction" is a
    REVISION of the same reference period's published read, not the normal
    day-over-day evolution of a new observation."""
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


def _sources(asof, vintages, stale_inputs) -> list[dict]:
    def _src(source_id, en, zh, owner_ref, provider, name):
        vint = _get(vintages, name)
        fresh = _labor_freshness(True, vint, stale_inputs, name)
        return {
            "source_id": source_id,
            "label": _bil(en, zh),
            "owner_ref": owner_ref,
            "provider": provider,
            "reference_period": asof,
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
        _src("claims", "Initial + continued jobless claims", "初请+续请失业金人数",
             "engine.regime.labor_nowcast", "U.S. Department of Labor / FRED", "claims"),
        _src("indeed", "Indeed job-postings index", "Indeed 职位发布指数",
             "engine.regime.labor_nowcast", "Indeed Hiring Lab", "indeed"),
        _src("withheld_tax", "Withheld income-tax receipts (income proxy)", "预扣所得税收入（收入代理指标）",
             "engine.regime.labor_nowcast", "U.S. Treasury Daily Statement", "withheld_tax"),
        _src("sahm", "Sahm rule (unemployment-rate based)", "萨姆规则（基于失业率）",
             "engine.regime.recession", "FRED / Federal Reserve (Sahm)", "sahm"),
        _src("recession_claims", "Claims-based recession subscore", "基于初请的衰退子评分",
             "engine.regime.recession", "Mastermind recession composite", "recession_claims"),
    ]
