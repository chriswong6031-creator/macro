"""Pure composer for the US ``business_activity`` workspace snapshot (F01 / R2).

Mirrors the R1A ``liquidity_regime`` pattern (typed presence/null, DISAGREEMENT
emission, content-derived digest via ``contract.finalize``, corrections subset,
definition_version discipline, zh-label integrity) over a DIFFERENT owner
substrate: ``engine.business_cycle``'s published Leading / Coincident / Lagging
tier composite, read from the SAME canonical owner artifact liquidity_regime
reads (``data/regime/latest.json#business_cycle`` -- CLAUDE.md: "data/regime/
latest.json is the canonical regime read"). That block is written by
``engine/run.py`` (``latest["business_cycle"] = business_cycle_snapshot()``),
never recomputed here: this module imports no owner engine module, only reads
the published dict.

WHY THE HEADLINE IS ALWAYS ABSENT (read this before "fixing" it)
------------------------------------------------------------------
The architecture's Business Activity headline model (blueprint section 10.4) is

    x-axis: new demand/orders,        contracting -> expanding
    y-axis: production/utilization,   contracting -> expanding
    inventory overlay:                destocking -> restocking

but ``engine.business_cycle`` does NOT publish orders / production / inventory
as separable legs. Its three tiers are Conference-Board-style BLENDS:

    leading    = mfg hours, claims, permits, cap-goods ORDERS, equities,
                 HY spread, curve, consumer sentiment      (8 legs)
    coincident = payrolls, real income, mfg+trade sales, industrial
                 PRODUCTION                                 (4 legs)
    lagging    = unemployment duration, inventory/sales RATIO, C&I loans,
                 prime rate, CPI services                   (5 legs)

"new orders" (NEWORDER) lives inside `leading` next to five unrelated legs;
"production" (INDPRO) lives inside `coincident` next to three unrelated legs;
"inventory" (ISRATIO) lives inside `lagging` next to four unrelated legs. The
published artifact exposes only the TIER-LEVEL composite (index/momentum/
diffusion/direction/leg-count), never the individual leg value. Labeling
`leading_mom6` as "new demand/orders" or `coincident_mom6` as "production/
utilization" would be a fabricated decomposition dressed as a real one --
exactly what the architecture (section 7.7: "Missing never becomes zero,
neutral, unchanged...") and this workspace's own care note ("if the owner
artifact doesn't distinguish X, disclose that in method text rather than
inventing the distinction") forbid.

So: no dual-axis quadrant is asserted. `axes.items` is `[]` (schema-legal --
no minItems), `headline.state_id` is always `null` /
`status="ABSENT"` / `null_reason="COMPUTATION_REFUSED"`, and `drivers` is
`{"rate_side": [], "balance_sheet": []}` (schema-legal empty arrays -- there
is no axis to have driving components in the first place; see also the
"deviations" note in the hand-off about those two container keys being
inherited liquidity_regime naming, never generalized in the closed schema).
The REAL, honest, owner-published tier-level reads are published in full
under `metrics.items` instead of being discarded.

SURVEY LANE
-----------
ISM/regional-Fed manufacturing & services PMIs are 50-line diffusion indexes
(not zero-line series) with real preliminary/final print conventions -- but
this repository wires NO lawful ISM/PMI/regional-Fed collector at all (grep
finds only NLP news-text pattern matchers for the strings "ism"/"pmi", never
a data collector). The survey lane is therefore typed ABSENT /
`RIGHTS_BLOCKED` in full, never estimated from hard data, and no prelim/final
distinction is invented in its absence.

CONTRADICTION
--------------
`engine.business_cycle`'s own "3 D's" recession rule requires Depth (leading
6-month momentum below a calibrated threshold) AND Breadth (diffusion at/below
a cutoff) to BOTH fire together. When the owner's own published
`recession_signal.conditions.depth` and `.breadth` booleans disagree, that is
a genuine, owner-native, non-fabricated contradiction -- typed DISAGREEMENT on
the two implicated leading-tier metrics (`leading_tier_momentum_6m`,
`leading_tier_diffusion`), mirroring the R1A quantity-vs-quality pattern.

NO rank/gate/size/trade authority. NO LLM-originated facts. Descriptive
ceiling only. Depends only on the standard library. Never reads a wall clock:
`built_at` is supplied by the caller and freshness is derived only from the
owner's own presence/leg-count flags, so identical owner input always yields
an identical snapshot body.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

METHOD_VERSION = "business_activity.compose.v1"
DEFINITION_VERSION = "1.0.0"
PRODUCER = "engine.market_os.macro_workspaces.business_activity"

# Total configured legs per tier (engine/business_cycle.py LEADING/COINCIDENT/
# LAGGING module-level lists) -- used ONLY to compute an honest coverage ratio
# and a coverage-floor refusal; never re-derives the tier value itself (that
# computation belongs to the owner, not this composer).
TIER_TOTAL_LEGS: dict[str, int] = {"leading": 8, "coincident": 4, "lagging": 5}
TIER_MIN_LEGS = 2          # mirrors engine.business_cycle.tier_index(min_legs=2)
TIER_COVERAGE_FLOOR = 0.5  # mirrors liquidity_regime's own axis coverage_floor

REQUIRED_TIERS = ("leading", "coincident")
OPTIONAL_TIERS = ("lagging",)
ALL_TIERS = REQUIRED_TIERS + OPTIONAL_TIERS

_TIER_LABELS: dict[str, tuple[str, str]] = {
    "leading": ("Leading tier", "领先层"),
    "coincident": ("Coincident tier", "同步层"),
    "lagging": ("Lagging tier", "滞后层"),
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
# small pure helpers (mirrors liquidity_regime.py)
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


def _round(v: float | None, n: int = 4) -> float | None:
    return None if v is None else round(float(v), n)


def _bil(en: str, zh: str | None) -> dict:
    return {"en": en, "zh": zh}


def _band(v: float | None, lo: float, hi: float) -> str | None:
    if v is None:
        return None
    return "LOW" if v < lo else ("HIGH" if v > hi else "MEDIUM")


def _worst_freshness(states: list[str]) -> str:
    if not states:
        return "SOURCE_FAILED"
    return max(states, key=lambda s: _FRESH_SEVERITY.get(s, 0))


# --------------------------------------------------------------------------- #
# tier presence / coverage
# --------------------------------------------------------------------------- #
def _tier_presence(bc: Any, tname: str) -> tuple[Mapping | None, str]:
    """(tier_dict_or_None, freshness). SOURCE_FAILED when business_cycle is
    absent/unavailable or the specific tier is missing from ``tiers`` -- the
    owner artifact carries no vintage/staleness flag for this block (unlike
    liquidity_quality/conditions), so STALE_SOURCE / NOT_YET_RELEASED are
    never fabricated here; see the module docstring."""
    if not isinstance(bc, Mapping) or bc.get("available") is not True:
        return None, "SOURCE_FAILED"
    tier = _get(bc, "tiers", tname)
    if not isinstance(tier, Mapping):
        return None, "SOURCE_FAILED"
    return tier, "CURRENT"


def _coverage_ratio(tname: str, n_legs: int | None) -> float | None:
    total = TIER_TOTAL_LEGS.get(tname, 0)
    if n_legs is None or total <= 0:
        return None
    return _clamp(n_legs / total, 0.0, 1.0)


def _coverage_ok(tname: str, n_legs: int | None) -> bool:
    if n_legs is None or n_legs < TIER_MIN_LEGS:
        return False
    ratio = _coverage_ratio(tname, n_legs)
    return ratio is not None and ratio >= TIER_COVERAGE_FLOOR


def _component_availability(bc: Any, tname: str, asof: str | None, required: bool) -> dict:
    tier, fresh = _tier_presence(bc, tname)
    n_legs = int(_num(_get(tier, "n_legs"))) if (tier is not None and _num(_get(tier, "n_legs")) is not None) else None
    present = tier is not None
    coverage_ok = _coverage_ok(tname, n_legs) if present else False
    status = "PRESENT" if (present and coverage_ok) else ("PARTIAL" if present else "ABSENT")
    null_reason = None
    if not present:
        null_reason = "SOURCE_FAILED"
    elif not coverage_ok:
        null_reason = "COMPUTATION_REFUSED"
    label_en, label_zh = _TIER_LABELS[tname]
    return {
        "component_id": f"{tname}_tier",
        "label": _bil(label_en, label_zh),
        "required": required,
        "freshness": fresh,
        "status": status,
        "source_asof": (tier.get("asof") if present else None) or asof,
        "null_reason": null_reason,
    }


# --------------------------------------------------------------------------- #
# metric builder (mirrors liquidity_regime._metric)
# --------------------------------------------------------------------------- #
def _metric(metric_id, value, value_type, unit, basis, direction, owner_ref,
            owner_field, reference_period, freshness, *, source_refs=None,
            transformation=None, status="PRESENT", null_reason=None,
            coverage: float | None = None) -> dict:
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
        "coverage": _round(coverage, 4) if coverage is not None else None,
        "freshness": freshness,
        "rights_state": "RIGHTS_BLOCKED" if freshness == "RIGHTS_BLOCKED" else "OPEN",
        "status": status if value is not None else "ABSENT",
        "null_reason": null_reason if value is not None else (null_reason or "SOURCE_FAILED"),
        "authority_ceiling": "DESCRIPTIVE",
    }


# --------------------------------------------------------------------------- #
# contradiction: the owner's own 3-D's depth/breadth disagreement
# --------------------------------------------------------------------------- #
def _detect_contradiction(bc: Any) -> dict:
    rs = _get(bc, "recession_signal")
    if not isinstance(rs, Mapping) or rs.get("available") is not True:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    cond = rs.get("conditions")
    depth = cond.get("depth") if isinstance(cond, Mapping) else None
    breadth = cond.get("breadth") if isinstance(cond, Mapping) else None
    if not isinstance(depth, bool) or not isinstance(breadth, bool) or depth == breadth:
        return {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    kind = "depth_breadth_divergence"
    if depth and not breadth:
        en = ("The leading tier's 6-month momentum has crossed the calibrated recession-risk DEPTH "
              "threshold, but BREADTH (the share of leading legs confirming) has not -- the "
              "deterioration is concentrated, not broad-based; the owner's 3 D's rule requires both "
              "to fire together before a recession-risk signal is asserted.")
        zh = ("领先层的6个月动量已越过校准的衰退风险深度阈值，但广度（确认走弱的领先分项占比）尚未确认——"
              "走弱是集中的而非广泛的；所有者的三要素规则要求深度与广度同时触发才判定衰退风险信号。")
    else:
        en = ("BREADTH (the share of leading legs weakening) has crossed the calibrated recession-risk "
              "cutoff, but the leading tier's 6-month momentum DEPTH has not -- the weakening is broad "
              "but shallow; the owner's 3 D's rule requires both to fire together before a "
              "recession-risk signal is asserted.")
        zh = ("广度（走弱的领先分项占比）已越过校准的衰退风险阈值，但领先层6个月动量的深度尚未确认——"
              "走弱广泛但程度较浅；所有者的三要素规则要求深度与广度同时触发才判定衰退风险信号。")
    return {"present": True, "kind": kind, "en": en, "zh": zh,
            "components": ["leading_tier_momentum_6m", "leading_tier_diffusion"]}


# --------------------------------------------------------------------------- #
# headline (always ABSENT -- see module docstring)
# --------------------------------------------------------------------------- #
def _headline(asof: str | None, prior_snapshot: Mapping | None) -> dict:
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    return {
        "state_id": None,
        "state_label": {"en": None, "zh": None},
        "subtitle": _bil("New demand/orders x production/utilization", "新增需求/订单 × 生产/产能利用"),
        "method_version": METHOD_VERSION,
        "effective_date": asof,
        "quadrant": {"x": None, "y": None, "x_status": "ABSENT", "y_status": "ABSENT"},
        "prior_state": {"state_id": None, "effective_date": prior_eff, "method_version": prior_method},
        "transition_distance": None,
        "nearest_boundary": {"axis": None, "distance": None, "null_reason": "COMPUTATION_REFUSED"},
        "one_month_vector": {"dx": None, "dy": None, "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"},
        "hysteresis": {
            "band": 0.0, "applied": False, "held_prior": False,
            "note": ("no dual-axis quadrant is computed for business_activity: the blueprinted new-demand/"
                     "orders x production/utilization decomposition is not separable from the currently "
                     "published engine.business_cycle tier composites (legs are blended within leading/"
                     "coincident/lagging, never individually published); see metrics[*_tier_*] for the real "
                     "available composite reads and implications[headline_unavailable] for the full disclosure"),
        },
        "status": "ABSENT",
        "null_reason": "COMPUTATION_REFUSED",
    }


# --------------------------------------------------------------------------- #
# changes / corrections (metric-level, since there is no axis to compare)
# --------------------------------------------------------------------------- #
_CHANGE_METRIC_IDS = (
    "leading_tier_momentum_6m", "coincident_tier_momentum_6m",
    "lagging_tier_momentum_6m", "coincident_lagging_ratio_momentum_6m",
)
_CORRECTION_METRIC_IDS = (
    "leading_tier_index", "leading_tier_momentum_6m", "leading_tier_diffusion",
    "coincident_tier_index", "coincident_tier_momentum_6m", "coincident_tier_diffusion",
    "lagging_tier_index", "lagging_tier_momentum_6m", "lagging_tier_diffusion",
)


def _prior_metric_value(prior_snapshot: Mapping | None, metric_id: str) -> Any:
    for m in (_get(prior_snapshot, "metrics", "items") or []):
        if isinstance(m, Mapping) and m.get("metric_id") == metric_id:
            return m.get("value")
    return None


def _changes(metrics_by_id: dict, asof: str | None, prior_snapshot: Mapping | None) -> dict:
    if prior_snapshot is None:
        return {"comparability": "NO_PRIOR", "prior_generation_id": None, "prior_effective_date": None,
                "prior_method_version": None, "deltas": [], "status": "ABSENT", "null_reason": "WARMUP"}
    prior_method = _get(prior_snapshot, "headline", "method_version")
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    prior_eff = _get(prior_snapshot, "headline", "effective_date")
    if prior_method != METHOD_VERSION:
        return {"comparability": "METHOD_CHANGED", "prior_generation_id": prior_gen,
                "prior_effective_date": prior_eff, "prior_method_version": prior_method,
                "deltas": [], "status": "ABSENT", "null_reason": "COMPUTATION_REFUSED"}
    deltas = []
    for mid in _CHANGE_METRIC_IDS:
        cur = metrics_by_id.get(mid, {}).get("value")
        prev = _prior_metric_value(prior_snapshot, mid)
        delta = None
        if isinstance(cur, (int, float)) and not isinstance(cur, bool) and \
           isinstance(prev, (int, float)) and not isinstance(prev, bool):
            delta = _round(cur - prev)
        deltas.append({"metric_id": mid, "prior_value": prev, "current_value": cur, "delta": delta,
                       "note": "same method version; numeric comparison permitted when both values are present"})
    return {"comparability": "COMPARABLE", "prior_generation_id": prior_gen, "prior_effective_date": prior_eff,
            "prior_method_version": prior_method, "deltas": deltas, "status": "PRESENT", "null_reason": None}


def _corrections(metrics_by_id: dict, asof: str | None, prior_snapshot: Mapping | None) -> dict:
    """Same scoped-subset supersession discipline as liquidity_regime's
    ``_corrections`` (F8): compares published tier-level fields between two
    prints of the SAME reference period, not a persisted vintage ledger."""
    prior_gen = _get(prior_snapshot, "generation", "generation_id")
    if prior_snapshot is None:
        return {"predecessor_generation_id": None, "changed_fingerprints": [], "correction_state": "none",
                "note": "First-known snapshot for this owner input; predecessor recorded when a prior accepted print exists."}
    prior_asof = _get(prior_snapshot, "headline", "effective_date")
    if prior_asof != asof:
        return {"predecessor_generation_id": prior_gen, "changed_fingerprints": [], "correction_state": "none",
                "note": "Reference period differs from the predecessor print (a new observation, not a revision of the same period); no correction asserted."}
    changed: list[str] = []
    for mid in _CORRECTION_METRIC_IDS:
        cur = metrics_by_id.get(mid, {}).get("value")
        prev = _prior_metric_value(prior_snapshot, mid)
        if cur != prev:
            digest16 = sha256(f"business_cycle:{mid}:{cur!r}".encode("utf-8")).hexdigest()[:16]
            changed.append(f"business_cycle:{mid}:{digest16}")
    if changed:
        return {"predecessor_generation_id": prior_gen, "changed_fingerprints": sorted(changed),
                "correction_state": "superseded",
                "note": "Same reference period as the predecessor print, but one or more owner-native tier fields changed value: this print supersedes the prior one as a revision."}
    return {"predecessor_generation_id": prior_gen, "changed_fingerprints": [], "correction_state": "none",
            "note": "Same reference period as the predecessor print; no tracked tier field changed value (no-change republication)."}


# --------------------------------------------------------------------------- #
# scenario / alert contracts (declared vocabulary only -- R2 non-goal: execution)
# --------------------------------------------------------------------------- #
def _scenario_contract() -> dict:
    return {
        "execution_available": False,
        "result_schema": "mastermind.macro_workspace_scenario_result.v1",
        "assumptions": [
            {"assumption_id": "leading_tier_momentum_bp", "label": _bil("Leading-tier momentum", "领先层动量"),
             "unit": "bp", "step": 25.0, "min": -500.0, "max": 500.0,
             "owner_field": "business_cycle.tiers.leading.mom6"},
            {"assumption_id": "coincident_tier_momentum_bp", "label": _bil("Coincident-tier momentum", "同步层动量"),
             "unit": "bp", "step": 25.0, "min": -500.0, "max": 500.0,
             "owner_field": "business_cycle.tiers.coincident.mom6"},
            {"assumption_id": "leading_breadth_pct", "label": _bil("Leading-tier breadth", "领先层广度"),
             "unit": "pct", "step": 5.0, "min": 0.0, "max": 100.0,
             "owner_field": "business_cycle.tiers.leading.diffusion"},
            {"assumption_id": "inventory_sales_ratio_chg", "label": _bil("Inventory/sales ratio change", "库存/销售比变化"),
             "unit": "ratio", "step": 0.05, "min": -1.0, "max": 1.0, "owner_field": None},
            {"assumption_id": "cap_goods_orders_pct", "label": _bil("Cap-goods orders growth", "资本品订单增长"),
             "unit": "pct", "step": 0.5, "min": -20.0, "max": 20.0, "owner_field": None},
        ],
        "status": "PARTIAL",
        "note": ("Assumption vocabulary is declared and closed; R2 ships no scenario execution endpoint "
                 "(non-goal). inventory_sales_ratio_chg / cap_goods_orders_pct have no owner_field because "
                 "engine.business_cycle does not publish those legs individually (see the module docstring); "
                 "a future owner-native pure scenario function produces "
                 "mastermind.macro_workspace_scenario_result.v1 with no canonical write."),
    }


def _alert_contract() -> dict:
    return {
        "service_available": False,
        "eligible_conditions": [
            {"condition_id": "leading_tier_rollover", "kind": "state_transition",
             "label": _bil("Leading-tier rollover", "领先层转向"), "params": ["direction"]},
            {"condition_id": "coincident_confirmation", "kind": "state_transition",
             "label": _bil("Coincident-tier confirmation", "同步层确认"), "params": ["direction"]},
            {"condition_id": "breadth_break", "kind": "boundary_approach",
             "label": _bil("Breadth break", "广度突破"), "params": ["tier", "threshold"]},
            {"condition_id": "recession_signal_transition", "kind": "state_transition",
             "label": _bil("Recession-signal transition", "衰退信号转变"), "params": ["target_state"]},
            {"condition_id": "source_stale_or_failed", "kind": "source_stale_or_failed",
             "label": _bil("Source stale or failed", "数据源过期或失败"), "params": ["source_id"]},
        ],
        "status": "ABSENT",
        "note": ("Eligible condition types are declared; R2 writes no alert (non-goal). Alerts extend the "
                 "existing Terminal alert lifecycle later; a page shows the Alerts tab only once the service "
                 "can create/list/evaluate/delete these real conditions."),
    }


def _sources(bc: Any, asof: str | None) -> list[dict]:
    bc_present = isinstance(bc, Mapping) and bc.get("available") is True
    fresh = "CURRENT" if bc_present else "SOURCE_FAILED"
    return [
        {
            "source_id": "business_cycle",
            "label": _bil("Business-cycle Leading/Coincident/Lagging composite", "商业周期领先/同步/滞后综合指数"),
            "owner_ref": "engine.business_cycle",
            "provider": "FRED / Yahoo (Conference-Board-style standardized-leg composite; see engine/business_cycle.py)",
            "reference_period": asof,
            "released_at": None, "first_known_at": None, "collected_at": None, "revised_at": None,
            "correction_state": "unknown",
            "transform": "tier-level standardized-leg cumulative composite; individual legs are not separately published",
            "rights_state": "OPEN", "definition_id": None, "definition_version": None,
            "artifact_ref": "data/regime/latest.json#business_cycle", "freshness": fresh,
        },
        {
            "source_id": "survey_pmi",
            "label": _bil("ISM / regional-Fed manufacturing & services surveys", "ISM/地区联储制造业与服务业调查"),
            "owner_ref": "NONE -- no lawful ISM/PMI or regional-Fed survey collector is wired in this repository",
            "provider": None, "reference_period": None, "released_at": None, "first_known_at": None,
            "collected_at": None, "revised_at": None, "correction_state": "unknown", "transform": None,
            "rights_state": "RIGHTS_BLOCKED", "definition_id": None, "definition_version": None,
            "artifact_ref": None, "freshness": "RIGHTS_BLOCKED",
        },
    ]


_GRANULAR_REFUSED = (
    ("new_orders_demand", "New demand / orders", "新增需求/订单"),
    ("production_utilization", "Production / capacity utilization", "生产/产能利用率"),
    ("inventory_cycle_phase", "Inventory cycle (destocking/restocking)", "库存周期（去库存/补库存）"),
    ("capex_orders_growth", "Capex / cap-goods orders growth", "资本支出/资本品订单增长"),
    ("shipments_sales_growth", "Manufacturing & trade shipments/sales growth", "制造业与贸易出货/销售增长"),
)


# --------------------------------------------------------------------------- #
# implications
# --------------------------------------------------------------------------- #
def _implications(bc: Any, bc_available: bool, contradiction: dict, worst_freshness: str,
                  coverage_ratio: float, calibrated: bool, phase_en: str | None,
                  rs_available: bool, state_val: str | None) -> list[dict]:
    conf = {
        "data_coverage": _band(coverage_ratio, 0.5, 0.99),
        "source_health": "HIGH" if worst_freshness == "CURRENT" else "LOW",
        "revision_risk": "MEDIUM",
        "method_stability": "HIGH" if calibrated else "MEDIUM",
        "evidence_breadth": "MEDIUM",
        "contradiction_state": "PRESENT" if contradiction["present"] else "ABSENT",
    }
    items: list[dict] = [{
        "implication_id": "headline_unavailable",
        "text": _bil(
            "No dual-axis Business Activity state (new demand/orders x production/utilization) is asserted: "
            "the owner-published engine.business_cycle artifact exposes only blended leading/coincident/"
            "lagging tier composites, not the individual orders/production/inventory legs the blueprinted "
            "headline needs. Rather than estimate a fabricated split, the real tier-level reads are "
            "published as metrics instead.",
            "未给出双轴商业活动状态（新增需求/订单 × 生产/产能利用）：所有者发布的 engine.business_cycle 制品"
            "仅公开了混合的领先/同步/滞后层综合指数，而非蓝图所需的独立订单/生产/库存分项。为避免虚构拆分，"
            "改以指标形式发布真实的分层读数。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["orders", "production", "inventory"],
        "contradictions": [contradiction["kind"]] if contradiction["present"] else [],
        "trace_ref": "data/regime/latest.json#business_cycle",
    }]
    for tname in ("leading", "coincident", "lagging"):
        tier, _fresh = _tier_presence(bc, tname)
        if tier is None:
            continue
        label_en, label_zh = _TIER_LABELS[tname]
        mom, diff, direction = tier.get("mom6"), tier.get("diffusion"), tier.get("direction")
        items.append({
            "implication_id": f"{tname}_tier_read",
            "text": _bil(
                f"{label_en}: 6-month momentum {mom}, direction {direction}, breadth {diff} "
                "(share of legs rising over the diffusion window, 0-100).",
                f"{label_zh}：6个月动量 {mom}，方向 {direction}，广度 {diff}"
                "（扩散窗口内上升分项占比，0-100）。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": (["orders", "production", "inventory"] if tname != "lagging" else ["inventory", "credit"]),
            "contradictions": [], "trace_ref": f"data/regime/latest.json#business_cycle.tiers.{tname}",
        })
    if bc_available and phase_en:
        items.append({
            "implication_id": "phase_clock_read",
            "text": _bil(
                f"Owner four-phase cycle clock reads '{phase_en}' from the sign of leading vs coincident "
                "6-month momentum. This read is shared substrate with the future Growth & Real Economy "
                "workspace; it is disclosed here for context, not claimed as a business_activity-exclusive state.",
                f"所有者四阶段周期时钟读数为“{phase_en}”，依据领先层与同步层6个月动量的符号得出。该读数与未来的"
                "“增长与实体经济”工作区共享同一底层数据，此处仅作背景披露，不作为商业活动专属状态。"),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["orders", "production"], "contradictions": [],
            "trace_ref": "data/regime/latest.json#business_cycle.phase",
        })
    if rs_available:
        ec = "HISTORICAL_ASSOCIATION" if calibrated else "DESCRIPTIVE"
        cal_txt_en = (" Calibrated leave-one-recession-out on a tiny (~3 endogenous) modern-recession sample "
                      "-- a recession-RISK timeline, not a crash oracle." if calibrated else
                      " Not currently calibrated against a version-matched, fresh operating point.")
        cal_txt_zh = ("已在极小样本（约3次内生衰退）上做留一法样本外校准——这是衰退风险时间线，并非崩盘预言。"
                      if calibrated else "当前未使用版本匹配且新鲜的校准操作点。")
        items.append({
            "implication_id": "recession_signal_read",
            "text": _bil(
                f"Owner recession-risk signal (Conference-Board '3 D's' on the leading tier) reads "
                f"'{state_val}'.{cal_txt_en}",
                f"所有者衰退风险信号（基于领先层的Conference-Board“三要素”规则）读数为“{state_val}”。{cal_txt_zh}"),
            "evidence_class": ec, "confidence": conf, "horizon": "months",
            "channels": ["orders", "production", "credit"], "contradictions": [],
            "trace_ref": "data/regime/latest.json#business_cycle.recession_signal",
        })
    if contradiction["present"]:
        items.append({
            "implication_id": "depth_breadth_divergence",
            "text": _bil(contradiction["en"], contradiction["zh"]),
            "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
            "channels": ["orders", "production"], "contradictions": [contradiction["kind"]],
            "trace_ref": "data/regime/latest.json#business_cycle.recession_signal.conditions",
        })
    items.append({
        "implication_id": "survey_lane_unavailable",
        "text": _bil(
            "The survey lane (ISM/regional-Fed manufacturing & services PMIs) is not shown: no lawful "
            "survey collector is wired in this repository (RIGHTS_BLOCKED). Only the hard-data lane "
            "(engine.business_cycle tier composites) is published; a preliminary/final print distinction "
            "is not invented in its absence.",
            "调查分项（ISM/地区联储制造业与服务业PMI）未展示：本仓库未接入任何合法的调查数据采集器"
            "（权利受限，RIGHTS_BLOCKED）。仅发布硬数据分项（engine.business_cycle 分层综合指数），"
            "不会在缺失时臆造初值/终值的区分。"),
        "evidence_class": "DESCRIPTIVE", "confidence": conf, "horizon": "current",
        "channels": ["orders", "production"], "contradictions": [], "trace_ref": None,
    })
    return items


# --------------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------------- #
def compose(regime_latest: Mapping[str, Any], *, built_at: str,
            prior_snapshot: Mapping[str, Any] | None = None,
            code_version: str | None = None) -> dict:
    """Project ``regime_latest['business_cycle']`` into an UNSEALED snapshot
    body. The builder seals it via ``contract.finalize`` (content_sha256 +
    generation_id), exactly like liquidity_regime."""
    r = regime_latest or {}
    bc = _get(r, "business_cycle")
    bc_available = isinstance(bc, Mapping) and bc.get("available") is True
    asof = (bc.get("asof") if bc_available else None) or _get(r, "asof") or _get(r, "date")

    metrics: list[dict] = []

    # ---- tier composites (leading/coincident required; lagging optional) --- #
    for tname in ALL_TIERS:
        tier, fresh = _tier_presence(bc, tname)
        n_legs_raw = _num(_get(tier, "n_legs")) if tier is not None else None
        n_legs = int(n_legs_raw) if n_legs_raw is not None else None
        coverage_ok = _coverage_ok(tname, n_legs)
        cov_ratio = _coverage_ratio(tname, n_legs)
        label_en, label_zh = _TIER_LABELS[tname]
        owner_field_base = f"business_cycle.tiers.{tname}"
        asof_t = (_get(tier, "asof") if tier is not None else None) or asof
        refuse_reason = "SOURCE_FAILED" if tier is None else "COMPUTATION_REFUSED"

        idx_val = _num(_get(tier, "index")) if (tier is not None and coverage_ok) else None
        mom_val = _num(_get(tier, "mom6")) if (tier is not None and coverage_ok) else None
        trend_val = _num(_get(tier, "trend")) if (tier is not None and coverage_ok) else None
        diff_val = _num(_get(tier, "diffusion")) if (tier is not None and coverage_ok) else None
        raw_dir = _get(tier, "direction")
        dir_val = raw_dir if (tier is not None and coverage_ok and isinstance(raw_dir, str)) else None

        metrics.append(_metric(f"{tname}_tier_index", idx_val, "index", "index_pt", "rebased_100_composite",
                               "higher_stronger", "engine.business_cycle", f"{owner_field_base}.index",
                               asof_t, fresh, coverage=cov_ratio,
                               transformation=(f"{label_en.lower()}: standardized-leg cumulative composite, "
                                               "rebased to 100 at first valid month (Conference-Board method)"),
                               null_reason=refuse_reason if idx_val is None else None))
        metrics.append(_metric(f"{tname}_tier_momentum_6m", mom_val, "number", "index_pt", "6m_change",
                               "higher_accelerating", "engine.business_cycle", f"{owner_field_base}.mom6",
                               asof_t, fresh, coverage=cov_ratio,
                               transformation="tier index level minus its value 6 months prior (CB '6-month change', red line)",
                               null_reason=refuse_reason if mom_val is None else None))
        metrics.append(_metric(f"{tname}_tier_trend", trend_val, "number", "index_pt", "ema_of_6m_change",
                               "higher_accelerating", "engine.business_cycle", f"{owner_field_base}.trend",
                               asof_t, fresh, coverage=cov_ratio,
                               transformation="EMA smoothing of the 6-month momentum series (blue line)",
                               null_reason=refuse_reason if trend_val is None else None))
        metrics.append(_metric(f"{tname}_tier_diffusion", diff_val, "score_0_100", "pct", "share_of_legs_rising_6m",
                               "higher_broader", "engine.business_cycle", f"{owner_field_base}.diffusion",
                               asof_t, fresh, coverage=cov_ratio,
                               transformation="share of the tier's sign-adjusted legs that rose over the diffusion window (CB breadth, 0-100)",
                               null_reason=refuse_reason if diff_val is None else None))
        metrics.append(_metric(f"{tname}_tier_direction", dir_val, "categorical", None, "sign_of_6m_momentum",
                               "n/a", "engine.business_cycle", f"{owner_field_base}.direction",
                               asof_t, fresh, coverage=cov_ratio,
                               transformation="'rising' if 6-month momentum > 0 else 'falling'",
                               null_reason=refuse_reason if dir_val is None else None))
        metrics.append(_metric(f"{tname}_tier_leg_count", n_legs, "count", "legs", "count_of_available_legs",
                               "higher_broader_input_coverage", "engine.business_cycle",
                               f"{owner_field_base}.n_legs", asof_t, fresh, coverage=cov_ratio,
                               transformation=(f"owner-published live leg count out of {TIER_TOTAL_LEGS.get(tname, '?')} "
                                               "configured legs -- never refused by the coverage floor; the count itself "
                                               "is the ragged-edge honesty flag"),
                               null_reason="SOURCE_FAILED" if tier is None else None))

    # ---- coincident/lagging ratio momentum (itself a classic leading read) - #
    cl_val = _num(_get(bc, "cl_ratio_mom6")) if bc_available else None
    cl_fresh = "CURRENT" if bc_available else "SOURCE_FAILED"
    metrics.append(_metric("coincident_lagging_ratio_momentum_6m", cl_val, "number", "ratio_pt", "6m_change_of_ratio",
                           "higher_stronger", "engine.business_cycle", "business_cycle.cl_ratio_mom6", asof, cl_fresh,
                           transformation="6-month change in (coincident_index / lagging_index), rebased to 100 at first valid month; itself a classic leading read",
                           null_reason=None if cl_val is not None else ("SOURCE_FAILED" if not bc_available else "COMPUTATION_REFUSED")))

    # ---- recession signal (3 D's) ------------------------------------------ #
    rs = _get(bc, "recession_signal") if bc_available else None
    rs_available = isinstance(rs, Mapping) and rs.get("available") is True
    rs_fresh = "CURRENT" if bc_available else "SOURCE_FAILED"
    state_val = rs.get("state") if rs_available else None
    months_val = _num(rs.get("months_active")) if rs_available else None
    cond = rs.get("conditions") if rs_available else None
    depth_val = cond.get("depth") if isinstance(cond, Mapping) else None
    breadth_val = cond.get("breadth") if isinstance(cond, Mapping) else None

    def _rs_null(v):
        return None if v is not None else ("SOURCE_FAILED" if not bc_available else "COMPUTATION_REFUSED")

    metrics.append(_metric("recession_signal_state", state_val, "categorical", None, "three_ds_rule", "n/a",
                           "engine.business_cycle", "business_cycle.recession_signal.state", asof, rs_fresh,
                           transformation="Conference-Board '3 D's' (Depth+Duration AND Diffusion) rule on the leading tier, held N months",
                           null_reason=_rs_null(state_val)))
    metrics.append(_metric("recession_signal_depth", depth_val, "categorical", None, "leading_mom6_below_threshold",
                           "n/a", "engine.business_cycle", "business_cycle.recession_signal.conditions.depth",
                           asof, rs_fresh, null_reason=_rs_null(depth_val)))
    metrics.append(_metric("recession_signal_breadth", breadth_val, "categorical", None, "diffusion_at_or_below_cutoff",
                           "n/a", "engine.business_cycle", "business_cycle.recession_signal.conditions.breadth",
                           asof, rs_fresh, null_reason=_rs_null(breadth_val)))
    metrics.append(_metric("recession_signal_months_active", months_val, "count", "months", "consecutive_months_in_state",
                           "n/a", "engine.business_cycle", "business_cycle.recession_signal.months_active",
                           asof, rs_fresh, null_reason=_rs_null(months_val)))

    # ---- 4-phase cycle clock ------------------------------------------------ #
    phase = _get(bc, "phase") if bc_available else None
    phase_en = phase.get("label") if isinstance(phase, Mapping) else None
    metrics.append(_metric("business_cycle_phase", phase_en, "categorical", None, "leading_x_coincident_momentum_sign",
                           "n/a", "engine.business_cycle", "business_cycle.phase.label", asof,
                           "CURRENT" if bc_available else "SOURCE_FAILED",
                           transformation="four-phase clock from the sign of leading/coincident 6-month momentum (expansion/slowdown/contraction/recovery)",
                           null_reason=None if phase_en is not None else ("SOURCE_FAILED" if not bc_available else "COMPUTATION_REFUSED")))

    # ---- LORO out-of-sample calibration stat -------------------------------- #
    measured = _get(bc, "measured") if bc_available else None
    calibrated = bool(_get(bc, "calibrated")) if bc_available else False
    catch_rate = _num(measured.get("oos_catch_rate")) if (calibrated and isinstance(measured, Mapping)) else None
    metrics.append(_metric("recession_signal_oos_catch_rate", catch_rate, "ratio", "ratio", "leave_one_recession_out",
                           "higher_more_reliable", "engine.business_cycle", "business_cycle.measured.oos_catch_rate",
                           asof, "HISTORICAL_AS_KNOWN" if catch_rate is not None else ("SOURCE_FAILED" if not bc_available else "CURRENT"),
                           transformation="out-of-sample (leave-one-recession-out) catch rate on ~3 endogenous modern recessions; tiny sample, see caveat",
                           null_reason=None if catch_rate is not None else ("SOURCE_FAILED" if not bc_available else "INSUFFICIENT_HISTORY")))

    # ---- survey lane: typed absent in full ---------------------------------- #
    metrics.append(_metric("survey_composite_pmi", None, "score_0_100", "diffusion_index_50_line", "diffusion_index",
                           "higher_expansion_below50_contraction", "engine.business_cycle (no survey collector)",
                           "NONE", None, "RIGHTS_BLOCKED",
                           transformation=("ISM/regional-Fed manufacturing & services PMIs are 50-line diffusion "
                                           "indexes (>50 expansion, <50 contraction), NOT a zero-line series; no "
                                           "lawful collector for this survey family is wired in this repository -- "
                                           "typed RIGHTS_BLOCKED, never estimated from hard data"),
                           null_reason="RIGHTS_BLOCKED"))

    # ---- granular blueprint items not separable from published tiers ------- #
    for mid, en, zh in _GRANULAR_REFUSED:
        metrics.append(_metric(mid, None, "number", None, "leg_level_not_separable", "n/a",
                               "engine.business_cycle (blended; not separately published)", mid, None,
                               "CURRENT" if bc_available else "SOURCE_FAILED",
                               transformation=(f"{en} is blended inside the published leading/coincident/lagging "
                                               "tier composites (engine.business_cycle mixes multiple legs per "
                                               "tier and publishes only the tier-level aggregate); the individual "
                                               "leg is not separately published -- refused rather than estimated. "
                                               "See the *_tier_index / *_tier_momentum_6m / *_tier_diffusion "
                                               "metrics for the real available reads."),
                               null_reason="COMPUTATION_REFUSED"))

    metrics_by_id = {m["metric_id"]: m for m in metrics}

    # ---- contradiction: owner's own depth/breadth divergence --------------- #
    contradiction = _detect_contradiction(bc) if bc_available else \
        {"present": False, "kind": None, "en": None, "zh": None, "components": []}
    if contradiction["present"]:
        for cid in contradiction["components"]:
            m = metrics_by_id.get(cid)
            if m is not None and m["value"] is not None:
                m["status"] = "DISAGREEMENT"
                m["null_reason"] = "DISAGREEMENT"

    # ---- availability roll-up over the REQUIRED tier set -------------------- #
    required_avail = [_component_availability(bc, t, asof, True) for t in REQUIRED_TIERS]
    optional_avail = [_component_availability(bc, t, asof, False) for t in OPTIONAL_TIERS]
    all_avail = required_avail + optional_avail
    worst = _worst_freshness([c["freshness"] for c in required_avail])
    n_present = sum(1 for c in required_avail if c["status"] in ("PRESENT", "PARTIAL"))
    coverage_ratio = round(n_present / len(required_avail), 4) if required_avail else 0.0
    degraded = [c["component_id"] for c in required_avail if c["freshness"] != "CURRENT"]
    reasons: list[str] = []
    if worst != "CURRENT":
        reasons.append(f"worst_required_source_freshness={worst}")
    if contradiction["present"]:
        reasons.append(f"contradiction={contradiction['kind']}")

    headline = _headline(asof, prior_snapshot)
    changes = _changes(metrics_by_id, asof, prior_snapshot)

    snapshot = {
        "schema": {"contract": "mastermind.macro_workspace_snapshot.v1", "version": "1.0.0"},
        "workspace": {
            "id": "business_activity",
            "title": _bil("Business Activity", "商业活动"),
            "subtitle": _bil("New demand/orders x production/utilization", "新增需求/订单 × 生产/产能利用"),
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
            "class": "context_only", "display_only": True, "can_rank": False, "can_gate": False,
            "can_size": False, "can_originate_signal": False, "can_execute": False,
            "axis_authority_ceiling": "DESCRIPTIVE",
        },
        "availability": {
            "state": worst,
            "required": all_avail,
            "degraded": degraded,
            "coverage_ratio": coverage_ratio,
            "worst_freshness": worst,
            "contradiction": contradiction,
            "reasons": reasons,
        },
        "headline": headline,
        "axes": {"items": []},
        "metrics": {"items": list(metrics_by_id.values())},
        "series": {"items": [], "status": "ABSENT", "null_reason": "INSUFFICIENT_HISTORY"},
        "drivers": {"rate_side": [], "balance_sheet": []},
        "changes": changes,
        "implications": {"items": _implications(bc, bc_available, contradiction, worst, coverage_ratio,
                                                 calibrated, phase_en, rs_available, state_val)},
        "scenario_contract": _scenario_contract(),
        "alert_contract": _alert_contract(),
        "sources": {"items": _sources(bc, asof)},
        "corrections": _corrections(metrics_by_id, asof, prior_snapshot),
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
