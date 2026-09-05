"""Pure view model for the Macro & Monetary suite shell (F01 / R1B).

Turns one validated ``mastermind.macro_workspace_snapshot.v1`` snapshot into the
flat, pre-labelled structure the shared Jinja shell renders. Doing the work here
instead of in the template is deliberate:

* every closed vocabulary is resolved through :mod:`lib.macro_suite_labels`, so
  no producer slug can reach a page;
* every absence becomes a TYPED absence (a null reason + a reviewed label), so a
  template can never fall back to ``0``, ``neutral``, ``easy`` or a blank cell;
* the rules are unit-testable without rendering HTML.

The builder is generic over the twelve workspace identities: it reads only
contract blocks, never a ``liquidity_regime`` field name. A workspace page
supplies identity and its own dominant-visualization choice; everything else in
the section 6.3 grammar comes from here.

Pure: no I/O, no clock read, no network. ``page_built_at`` is supplied.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from lib import macro_suite_labels as L

# Reading orders the shell can compose. The grammar order is merged architecture
# section 6.3 and remains the default for every workspace; the decision-first
# order is the narrowly amended one (see build_view's docstring).
LAYOUT_GRAMMAR = "grammar"
LAYOUT_DECISION_FIRST = "decision_first"
_LAYOUTS = frozenset({LAYOUT_GRAMMAR, LAYOUT_DECISION_FIRST})

EM_DASH = L.EM_DASH


def _pair(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def _bilingual(node: Any) -> dict[str, str] | None:
    """Normalise a contract ``{"en", "zh"}`` node; ``zh`` may legitimately be
    null, in which case the toggle shows the English string in both modes."""
    if not isinstance(node, Mapping):
        return None
    en = node.get("en")
    if en is None:
        return None
    zh = node.get("zh")
    return {"en": str(en), "zh": str(zh) if zh else str(en)}


def _absence(null_reason: Any, fallback: str = "UNKNOWN") -> dict[str, Any]:
    """A typed absence cell: a reviewed reason label plus its raw token for the
    evidence drawer. Missing NEVER becomes zero or neutral."""
    token = null_reason or fallback
    return {"token": str(token), "label": L.label("null_reason", token), "display": EM_DASH}


def _region_view(code: Any, display_name: Any, supported: bool) -> dict[str, Any]:
    """Region identity with a reviewed bilingual name.

    The contract's ``display_name`` is English by design. Rendering it raw would
    put an English proper noun in the middle of a Chinese page, so a supported
    region resolves through the reviewed table and falls back to the artifact's
    own name only when we have not reviewed that region yet.
    """
    fallback = str(display_name) if display_name else str(code or "")
    reviewed = L.REGION.get(str(code)) if code else None
    return {
        "code": code,
        "display_name": fallback,
        "display": dict(reviewed) if reviewed else _pair(fallback, fallback),
        "supported": supported,
    }


def _clock_rows(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every section 7.5 clock this node carries, present or typed-absent."""
    rows = []
    for key, name, meaning in L.CLOCKS:
        value = L.date_or_none(node.get(key))
        rows.append({
            "key": key,
            "name": name,
            "meaning": meaning,
            "value": value,
            "absent": value is None,
        })
    return rows


# --- context header ----------------------------------------------------------

def _context(snapshot: Mapping[str, Any], page_built_at: str) -> dict[str, Any]:
    availability = snapshot.get("availability") or {}
    generation = snapshot.get("generation") or {}
    region = snapshot.get("region") or {}

    required = []
    cuts: list[str] = []
    for item in availability.get("required") or []:
        asof = L.date_or_none(item.get("source_asof"))
        if asof:
            cuts.append(asof)
        required.append({
            "component_id": item.get("component_id"),
            "label": _bilingual(item.get("label")) or _pair(L.deslug(item.get("component_id") or ""),
                                                            L.deslug(item.get("component_id") or "")),
            "required": bool(item.get("required")),
            "freshness": L.label("freshness", item.get("freshness")),
            "freshness_tone": L.tone("freshness", item.get("freshness")),
            "presence": L.label("presence", item.get("status")),
            "presence_tone": L.tone("presence", item.get("status")),
            "source_asof": asof,
            "absence": None if asof else _absence(item.get("null_reason")),
        })

    contradiction = availability.get("contradiction") or {}
    contradiction_view = None
    if contradiction.get("present"):
        contradiction_view = {
            "kind": L.label("presence", contradiction.get("kind")) if contradiction.get("kind") else None,
            "kind_raw": contradiction.get("kind"),
            "text": _bilingual(contradiction) or _pair("Contradiction present", "存在矛盾"),
            "components": list(contradiction.get("components") or []),
        }

    state = availability.get("state")
    # The header states the page's OWN freshness conservatively over the
    # required set (section 7.6); an optional degraded leg cannot turn it green.
    return {
        "state": state,
        "state_label": L.label("freshness", state),
        "state_tone": L.tone("freshness", state),
        "worst_freshness": L.label("freshness", availability.get("worst_freshness")),
        "worst_freshness_tone": L.tone("freshness", availability.get("worst_freshness")),
        # Raw token beside the label: a consumer that must DECIDE (rather than
        # print) needs the token, and re-deriving it from a label is a bug.
        "worst_freshness_token": availability.get("worst_freshness"),
        "coverage": L.fmt_ratio_pct(availability.get("coverage_ratio")),
        "required": required,
        "degraded": list(availability.get("degraded") or []),
        "reasons": list(availability.get("reasons") or []),
        "contradiction": contradiction_view,
        "last_source_cut": max(cuts) if cuts else None,
        "calculation_as_of": L.date_or_none(generation.get("calculation_as_of")),
        "artifact_built_at": L.date_or_none(generation.get("built_at")),
        "page_built_at": page_built_at,
        "region_supported": bool(region.get("supported")),
    }


# --- causal implications ribbon ---------------------------------------------

def _implications(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    # NOTE the view key is `entries`, never `items`: in Jinja, `x.items` on a
    # dict resolves to the built-in dict method, not the value. Guarded by
    # tests/test_template_items_footgun.py.
    items = []
    for raw in (snapshot.get("implications") or {}).get("items") or []:
        text = _bilingual(raw.get("text"))
        if text is None:
            continue
        confidence = raw.get("confidence") or {}
        bands = []
        for key, name in L.CONFIDENCE_DIMENSION.items():
            token = confidence.get(key)
            if key == "contradiction_state":
                value = L.label("presence", token)
            else:
                value = L.label("confidence_band", token)
            bands.append({"name": name, "value": value,
                          "absence": None if value else _absence(None)})
        items.append({
            "implication_id": raw.get("implication_id"),
            "text": text,
            "evidence_class": raw.get("evidence_class"),
            "evidence_label": L.label("evidence_class", raw.get("evidence_class")),
            "evidence_claim": L.label("evidence_claim", raw.get("evidence_class")),
            "horizon": L.label("horizon", raw.get("horizon")),
            "channels": [L.label("channel", c) for c in (raw.get("channels") or [])],
            "contradictions": list(raw.get("contradictions") or []),
            "confidence": bands,
            "trace_ref": raw.get("trace_ref"),
        })
    # The ribbon renders ONLY what the snapshot carries. An empty block is a
    # typed absence, never invented prose.
    return {
        "entries": items[:3],
        "truncated": max(0, len(items) - 3),
        "absent": not items,
        "absence_text": _pair(
            "This snapshot carries no evidence-grounded implication. Nothing is inferred here.",
            "本快照未附带任何有证据支持的推论。此处不作任何推断。"),
    }


# --- headline state band ------------------------------------------------------

def _axis_view(axis: Mapping[str, Any]) -> dict[str, Any]:
    value = axis.get("value")
    thresholds = axis.get("thresholds") or {}
    components = []
    for component in axis.get("components") or []:
        components.append({
            "component_id": component.get("component_id"),
            "label": _bilingual(component.get("label")),
            "owner_field": component.get("owner_field"),
            "owner_ref": component.get("owner_ref"),
            "raw": L.value_pair(component.get("raw_value")),
            "raw_absence": None if component.get("raw_value") is not None else _absence(component.get("null_reason")),
            "standardized": L.fmt_number(component.get("standardized_value")),
            "contribution": L.fmt_signed(component.get("contribution")),
            "contribution_sign": _sign(component.get("contribution")),
            "sign": component.get("sign"),
            "weight": L.fmt_number(component.get("weight")),
            "coverage": L.label("presence", component.get("coverage_state")),
            "coverage_tone": L.tone("presence", component.get("coverage_state")),
            "freshness": L.label("freshness", component.get("freshness")),
            "freshness_tone": L.tone("freshness", component.get("freshness")),
        })
    return {
        "axis_id": axis.get("axis_id"),
        "label": _bilingual(axis.get("label")),
        "direction": L.label("direction", axis.get("direction_semantics")),
        "value": L.fmt_number(value),
        "value_raw": value if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
        "absence": None if value is not None else _absence(axis.get("null_reason")),
        "freshness": L.label("freshness", axis.get("freshness")),
        "freshness_tone": L.tone("freshness", axis.get("freshness")),
        "boundary": thresholds.get("boundary"),
        "boundary_text": L.fmt_number(thresholds.get("boundary")),
        "hysteresis_band": thresholds.get("hysteresis_band"),
        "low_label": _bilingual(thresholds.get("low_label")),
        "high_label": _bilingual(thresholds.get("high_label")),
        "components": components,
        "components_available": axis.get("components_available"),
        "min_components": axis.get("min_components"),
        "coverage_floor": L.fmt_ratio_pct(axis.get("coverage_floor")),
        "weights_law": axis.get("weights_law"),
        "transformation": axis.get("transformation"),
        "frequency_alignment": axis.get("frequency_alignment"),
        "revision_behavior": axis.get("revision_behavior"),
        "definition_version": axis.get("definition_version"),
        "data_version": axis.get("data_version"),
        "authority_ceiling": axis.get("authority_ceiling"),
    }


def _sign(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "flat"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _headline(snapshot: Mapping[str, Any], axes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    headline = snapshot.get("headline") or {}
    quadrant = headline.get("quadrant") or {}
    vector = headline.get("one_month_vector") or {}
    prior = headline.get("prior_state") or {}
    boundary = headline.get("nearest_boundary") or {}
    hysteresis = headline.get("hysteresis") or {}

    axis_by_id = {a["axis_id"]: a for a in axes}
    boundary_axis = axis_by_id.get(boundary.get("axis"))

    vector_present = vector.get("status") == "PRESENT" and vector.get("dx") is not None
    return {
        "state_id": headline.get("state_id"),
        "state_label": _bilingual(headline.get("state_label")),
        "subtitle": _bilingual(headline.get("subtitle")),
        "status": headline.get("status"),
        "absence": None if headline.get("state_id") else _absence(headline.get("null_reason")),
        "method_version": headline.get("method_version"),
        "effective_date": L.date_or_none(headline.get("effective_date")),
        "x": quadrant.get("x"),
        "y": quadrant.get("y"),
        "x_text": L.fmt_number(quadrant.get("x")),
        "y_text": L.fmt_number(quadrant.get("y")),
        "x_absence": None if quadrant.get("x") is not None else _absence(headline.get("null_reason")),
        "y_absence": None if quadrant.get("y") is not None else _absence(headline.get("null_reason")),
        "prior": {
            "state_id": prior.get("state_id"),
            "effective_date": L.date_or_none(prior.get("effective_date")),
            "method_version": prior.get("method_version"),
            "absent": not prior.get("state_id"),
        },
        "transition_distance": L.fmt_number(headline.get("transition_distance")),
        "nearest_boundary": {
            "axis_label": boundary_axis["label"] if boundary_axis else None,
            "distance": L.fmt_number(boundary.get("distance")),
            "absence": None if boundary.get("distance") is not None else _absence(boundary.get("null_reason")),
        },
        "vector": {
            "present": vector_present,
            "dx": L.fmt_signed(vector.get("dx")),
            "dy": L.fmt_signed(vector.get("dy")),
            "dx_raw": vector.get("dx"),
            "dy_raw": vector.get("dy"),
            "absence": None if vector_present else _absence(vector.get("null_reason")),
            "status": L.label("presence", vector.get("status")),
        },
        "hysteresis": {
            "band": L.fmt_number(hysteresis.get("band")),
            "applied": bool(hysteresis.get("applied")),
            "held_prior": bool(hysteresis.get("held_prior")),
            "note": hysteresis.get("note"),
        },
    }


# --- dominant visualization: the quadrant state map --------------------------
# Generic over any two-axis workspace: nine of the twelve blueprints in section
# 10 are x/y state models, so the map is shell furniture rather than a
# liquidity-only widget. The letter grid follows the producer's classification
# law: A = low-x/high-y, B = high-x/high-y, C = low-x/low-y, D = high-x/low-y.

_QUADRANT_GRID = (
    # (letter, x-half, y-half, css position)
    ("A", "low", "high", "tl"),
    ("B", "high", "high", "tr"),
    ("C", "low", "low", "bl"),
    ("D", "high", "low", "br"),
)


def _quadrant_map(headline: Mapping[str, Any], axes: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if len(axes) < 2:
        return None
    x_axis, y_axis = axes[0], axes[1]
    cells = []
    for letter, x_half, y_half, position in _QUADRANT_GRID:
        x_label = x_axis["low_label"] if x_half == "low" else x_axis["high_label"]
        y_label = y_axis["low_label"] if y_half == "low" else y_axis["high_label"]
        if not x_label or not y_label:
            return None
        cells.append({
            "letter": letter,
            "position": position,
            # Two lines, not one: a single "X / Y" string overflows its quadrant
            # and collides with the neighbouring cell at map scale.
            "line1": dict(x_label),
            "line2": dict(y_label),
            "label": _pair(f"{x_label['en']} / {y_label['en']}",
                           f"{x_label['zh']} / {y_label['zh']}"),
            "current": letter == headline.get("state_id"),
        })

    x_value, y_value = headline.get("x"), headline.get("y")
    plotted = isinstance(x_value, (int, float)) and isinstance(y_value, (int, float))
    return {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "cells": cells,
        "plotted": plotted,
        # SVG space is 0-100 on both axes with y inverted (0 at the bottom).
        "point": {"cx": round(float(x_value), 2), "cy": round(100 - float(y_value), 2)} if plotted else None,
        "absence": None if plotted else _absence(None),
        "boundary_x": x_axis.get("boundary"),
        "boundary_y": y_axis.get("boundary"),
        "band_x": x_axis.get("hysteresis_band"),
        "band_y": y_axis.get("hysteresis_band"),
        "vector": headline.get("vector"),
    }


# --- what changed -------------------------------------------------------------

def _changes(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    changes = snapshot.get("changes") or {}
    comparability = changes.get("comparability")
    deltas = []
    for delta in changes.get("deltas") or []:
        deltas.append({
            "metric_id": delta.get("metric_id"),
            "label": L.label("metric", delta.get("metric_id")),
            "prior": L.fmt_number(delta.get("prior_value")),
            "current": L.fmt_number(delta.get("current_value")),
            "delta": L.fmt_signed(delta.get("delta")),
            "sign": _sign(delta.get("delta")),
            "note": delta.get("note"),
        })
    comparable = comparability == "COMPARABLE"
    return {
        "comparability": comparability,
        "comparability_label": L.label("comparability", comparability),
        "comparable": comparable,
        "deltas": deltas,
        "prior_generation_id": changes.get("prior_generation_id"),
        "prior_effective_date": L.date_or_none(changes.get("prior_effective_date")),
        "prior_method_version": changes.get("prior_method_version"),
        "absence": None if comparable and deltas else _absence(changes.get("null_reason")),
        "status": L.label("presence", changes.get("status")),
    }


# --- component metrics --------------------------------------------------------

def _metrics(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for metric in (snapshot.get("metrics") or {}).get("items") or []:
        value = metric.get("value")
        rows.append({
            "metric_id": metric.get("metric_id"),
            "label": L.label("metric", metric.get("metric_id")),
            "value": L.value_pair(value),
            "absence": None if value is not None else _absence(metric.get("null_reason")),
            "unit": L.label("unit", metric.get("unit")),
            "basis": L.label("basis", metric.get("basis")),
            "direction": L.label("direction", metric.get("direction_semantics")),
            "freshness": L.label("freshness", metric.get("freshness")),
            "freshness_tone": L.tone("freshness", metric.get("freshness")),
            "presence": L.label("presence", metric.get("status")),
            "rights": L.label("rights_state", metric.get("rights_state")),
            "reference_id": metric.get("reference_id"),
            "definition_id": metric.get("definition_id"),
            "definition_version": metric.get("definition_version"),
            "owner_ref": metric.get("owner_ref"),
            "model_version": metric.get("model_version"),
            "transformation": metric.get("transformation"),
            "coverage": L.fmt_ratio_pct(metric.get("coverage")),
            "authority_ceiling": metric.get("authority_ceiling"),
            "clocks": _clock_rows(metric),
            "reference_period": L.date_or_none(metric.get("reference_period")),
            "source_refs": list(metric.get("source_refs") or []),
        })
    return rows


def _series(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    block = snapshot.get("series") or {}
    items = []
    for entry in block.get("items") or []:
        points = [p for p in (entry.get("points") or []) if p.get("v") is not None]
        items.append({
            "series_id": entry.get("series_id"),
            "label": _bilingual(entry.get("label")),
            "unit": L.label("unit", entry.get("unit")),
            "basis": L.label("basis", entry.get("basis")),
            "count": len(points),
            "first": points[0]["t"] if points else None,
            "last": points[-1]["t"] if points else None,
            "freshness": L.label("freshness", entry.get("freshness")),
            "freshness_tone": L.tone("freshness", entry.get("freshness")),
            "revision_behavior": entry.get("revision_behavior"),
            "source_ref": entry.get("source_ref"),
        })
    return {
        # `entries`, not `items` — see the note in _implications.
        "entries": items,
        "absent": not items,
        "absence": None if items else _absence(block.get("null_reason")),
        "status": L.label("presence", block.get("status")),
    }


def _drivers(snapshot: Mapping[str, Any], axes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    block = snapshot.get("drivers") or {}
    axis_by_index = list(axes)
    groups = []
    for key, fallback_en, fallback_zh, axis_index in (
        ("rate_side", "Rate-side drivers", "利率侧驱动", 0),
        ("balance_sheet", "Balance-sheet drivers", "资产负债表驱动", 1),
    ):
        rows = []
        for driver in block.get(key) or []:
            magnitude = driver.get("impact_magnitude")
            sign = driver.get("impact_sign")
            signed = None
            if isinstance(magnitude, (int, float)) and isinstance(sign, int):
                signed = L.fmt_signed(magnitude * sign)
            rows.append({
                "driver_id": driver.get("driver_id"),
                "label": _bilingual(driver.get("label")),
                "owner_field": driver.get("owner_field"),
                "value": L.value_pair(driver.get("value")),
                "absence": None if driver.get("value") is not None else _absence(None),
                "unit": L.label("unit", driver.get("unit")),
                "impact": signed,
                "impact_sign": "up" if (sign or 0) > 0 else ("down" if (sign or 0) < 0 else "flat"),
                "impact_absence": None if signed is not None else _absence(None),
                "note": driver.get("note"),
                "coverage": L.label("presence", driver.get("coverage_state")),
                "coverage_tone": L.tone("presence", driver.get("coverage_state")),
            })
        axis = axis_by_index[axis_index] if axis_index < len(axis_by_index) else None
        groups.append({
            "group_id": key,
            "title": (axis["label"] if axis and axis.get("label") else _pair(fallback_en, fallback_zh)),
            "fallback_title": _pair(fallback_en, fallback_zh),
            "rows": rows,
            "absent": not rows,
            "absence": None if rows else _absence(None),
        })
    return groups


# --- diagnostics --------------------------------------------------------------

def _diagnostics(snapshot: Mapping[str, Any], context: Mapping[str, Any],
                 changes: Mapping[str, Any], series: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Constraints, supports, disagreements, missing components, source issues
    and method warnings — assembled from what the snapshot actually declares."""
    out: list[dict[str, Any]] = []

    if context.get("contradiction"):
        out.append({
            "tone": "bad",
            "title": _pair("Contradictory signals", "信号相互矛盾"),
            "body": context["contradiction"]["text"],
        })

    stale = [c for c in context.get("required") or []
             if c["freshness_tone"] in ("warn", "bad")]
    if stale:
        names_en = ", ".join(c["label"]["en"] for c in stale)
        names_zh = "、".join(c["label"]["zh"] for c in stale)
        out.append({
            "tone": "warn",
            "title": _pair("Required source not current", "必需数据源并非最新"),
            "body": _pair(f"Degraded required components: {names_en}.",
                          f"降级的必需分项：{names_zh}。"),
        })

    for component in context.get("required") or []:
        if component["absence"] is not None:
            out.append({
                "tone": "warn",
                "title": component["label"],
                "body": _pair(
                    f"No accepted source cut. Reason: {component['absence']['label']['en']}.",
                    f"没有已接受的数据截止。原因：{component['absence']['label']['zh']}。"),
            })

    if context.get("degraded"):
        joined = ", ".join(str(d) for d in context["degraded"])
        out.append({
            "tone": "warn",
            "title": _pair("Optional legs degraded", "可选分项已降级"),
            "body": _pair(f"Shown separately, and excluded from the page state: {joined}.",
                          f"单独呈现，且不计入本页状态：{joined}。"),
        })

    if not changes.get("comparable"):
        out.append({
            "tone": "neutral",
            "title": _pair("No method-comparable prior print", "无方法可比的历史读数"),
            "body": changes["comparability_label"],
        })

    if series.get("absent"):
        out.append({
            "tone": "neutral",
            "title": _pair("Component histories not published", "未发布分项历史序列"),
            "body": series["absence"]["label"],
        })

    scenario = snapshot.get("scenario_contract") or {}
    if not scenario.get("execution_available"):
        out.append({
            "tone": "neutral",
            "title": _pair("Scenario execution not available", "情景推演功能不可用"),
            "body": _pair(
                "The assumption vocabulary is declared and closed, but no scenario "
                "function is published — so no Scenario tab is offered.",
                "假设变量词表已声明并封闭，但尚未发布情景函数 — 因此不提供“情景”标签页。"),
        })

    alerts = snapshot.get("alert_contract") or {}
    if not alerts.get("service_available"):
        out.append({
            "tone": "neutral",
            "title": _pair("Alert service not available", "预警服务不可用"),
            "body": _pair(
                "Eligible conditions are declared, but no service can create, list, "
                "evaluate or delete them — so no Alerts tab is offered.",
                "可用的预警条件已声明，但尚无服务能够创建、列出、评估或删除它们 — 因此不提供“预警”标签页。"),
        })

    if not out:
        out.append({
            "tone": "ok",
            "title": _pair("No constraint recorded", "未记录任何约束"),
            "body": _pair("Every required component is present and current.",
                          "所有必需分项均已具备且为最新。"),
        })
    return out


# --- evidence drawer ----------------------------------------------------------

def _evidence(snapshot: Mapping[str, Any], context: Mapping[str, Any],
              page_built_at: str, artifact: Mapping[str, Any]) -> dict[str, Any]:
    sources = []
    for source in (snapshot.get("sources") or {}).get("items") or []:
        sources.append({
            "source_id": source.get("source_id"),
            "label": _bilingual(source.get("label")),
            "provider": source.get("provider"),
            "owner_ref": source.get("owner_ref"),
            "artifact_ref": source.get("artifact_ref"),
            "transform": source.get("transform"),
            "definition_id": source.get("definition_id"),
            "definition_version": source.get("definition_version"),
            "rights": L.label("rights_state", source.get("rights_state")),
            "freshness": L.label("freshness", source.get("freshness")),
            "freshness_tone": L.tone("freshness", source.get("freshness")),
            "correction": L.label("correction_state", source.get("correction_state")),
            "clocks": _clock_rows({
                **source,
                "observed_at": source.get("reference_period"),
                "available_at": source.get("first_known_at"),
                "calculation_as_of": None,
            }),
        })

    generation = snapshot.get("generation") or {}
    authority = snapshot.get("authority") or {}
    corrections = snapshot.get("corrections") or {}
    return {
        "sources": sources,
        "non_economic_clocks": [
            {"name": name, "meaning": meaning,
             "value": generation.get("built_at") if key == "built_at" else page_built_at}
            for key, name, meaning in L.NON_ECONOMIC_CLOCKS
        ],
        "generation": {
            "generation_id": generation.get("generation_id"),
            "producer": generation.get("producer"),
            "code_version": generation.get("code_version"),
            "content_sha256": generation.get("content_sha256"),
            "calculation_as_of": context.get("calculation_as_of"),
        },
        "artifact": dict(artifact),
        "authority": {
            "class": authority.get("class"),
            "ceiling": authority.get("axis_authority_ceiling"),
            "flags": [
                {"name": _pair("Can rank", "可排名"), "value": bool(authority.get("can_rank"))},
                {"name": _pair("Can gate", "可作为闸门"), "value": bool(authority.get("can_gate"))},
                {"name": _pair("Can size", "可决定仓位"), "value": bool(authority.get("can_size"))},
                {"name": _pair("Can originate a signal", "可产生信号"),
                 "value": bool(authority.get("can_originate_signal"))},
                {"name": _pair("Can execute", "可执行交易"), "value": bool(authority.get("can_execute"))},
            ],
            "statement": _pair(
                "Display-only context. This page cannot rank, gate, size, originate a "
                "signal, or execute anything.",
                "仅供展示的背景信息。本页不能排名、设闸、定仓位、产生信号或执行任何交易。"),
        },
        "corrections": {
            "state": L.label("correction_state", corrections.get("correction_state")),
            "predecessor": corrections.get("predecessor_generation_id"),
            "changed_fingerprints": list(corrections.get("changed_fingerprints") or []),
            "note": corrections.get("note"),
        },
    }


# --- declared-but-withheld capabilities --------------------------------------

def _withheld_tabs(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Tabs the reference grammar allows but this snapshot forbids.

    Rendered as a note, NEVER as a tab: section 6.2 forbids a decorative tab and
    section 9.2 forbids showing Alerts before the service can serve real
    conditions.
    """
    out = []
    scenario = snapshot.get("scenario_contract") or {}
    if not scenario.get("execution_available"):
        out.append({
            "tab_id": "scenario",
            "name": _pair("Scenario", "情景"),
            "reason": _pair("No scenario execution is published for this workspace.",
                            "本工作区尚未发布情景推演能力。"),
            "declared": [
                {"label": _bilingual(a.get("label")),
                 "unit": L.label("unit", a.get("unit")),
                 "step": L.fmt_number(a.get("step")),
                 "min": L.fmt_number(a.get("min")),
                 "max": L.fmt_number(a.get("max"))}
                for a in scenario.get("assumptions") or []
            ],
            "declared_title": _pair("Assumption vocabulary declared (not executable)",
                                    "已声明的假设变量词表（尚不可执行）"),
        })
    alerts = snapshot.get("alert_contract") or {}
    if not alerts.get("service_available"):
        out.append({
            "tab_id": "alerts",
            "name": _pair("Alerts", "预警"),
            "reason": _pair("No alert service can create, evaluate or delete these conditions yet.",
                            "尚无服务能够创建、评估或删除这些预警条件。"),
            "declared": [
                {"label": _bilingual(c.get("label")),
                 "unit": L.label("alert_kind", c.get("kind")),
                 "step": None, "min": None, "max": None}
                for c in alerts.get("eligible_conditions") or []
            ],
            "declared_title": _pair("Eligible conditions declared (not offered)",
                                    "已声明的可用条件（尚未开放）"),
        })
    return out


# --- next action -------------------------------------------------------------
# The doctrine requires every signal surface to answer "so what do I do", and the
# authority ceiling forbids this lane from answering with a position, a size or a
# gate. The compliant answer is a RESEARCH action, and it is chosen by a total
# function over typed tokens the producer already published — no model, no
# weighting, no judgement. When the honest answer is "watch, don't chase", that
# is what it says.

#: Freshness tokens that mean this print cannot be read as today's answer.
_NOT_TODAYS_ANSWER = frozenset({
    "SOURCE_FAILED", "STALE_SOURCE", "RIGHTS_BLOCKED", "SIMULATED", "NOT_YET_RELEASED",
})


def _next_action(context: Mapping[str, Any],
                 headline: Mapping[str, Any]) -> dict[str, Any]:
    """One typed research action, in a fixed precedence.

    Precedence is deliberate and is the whole design: an unusable print outranks
    a disagreement, a disagreement outranks a boundary watch, and a settled quiet
    read says so plainly rather than manufacturing something to do.
    """
    heading = _pair("Next action", "下一步")

    state = context.get("state")
    if state in _NOT_TODAYS_ANSWER or context.get("worst_freshness_token") in _NOT_TODAYS_ANSWER:
        return {
            "token": "WAIT_FOR_SOURCES",
            "heading": heading,
            "tone": "warn",
            "text": _pair(
                "Do not read this as today's answer. A required source is not current — "
                "wait for the next accepted print.",
                "请勿将此视为今日读数。某项必需数据源并非最新 — 请等待下一次已接受的读数。"),
            "watch": None,
        }

    if context.get("contradiction"):
        return {
            "token": "TREAT_AS_UNSETTLED",
            "heading": heading,
            "tone": "warn",
            "text": _pair(
                "Required components disagree. Read them separately below — the summary "
                "state is not settled while they conflict.",
                "必需分项之间存在矛盾。请在下方分别查看 — 矛盾未消解前，汇总状态尚未确定。"),
            "watch": None,
        }

    boundary = headline.get("nearest_boundary") or {}
    if boundary.get("distance") and boundary.get("axis_label"):
        return {
            "token": "WATCH_BOUNDARY",
            "heading": heading,
            "tone": "neutral",
            # Plain words on purpose, and no "recommendation": the merged authority
            # guard in tests/test_macro_suite_pages.py bans that vocabulary from
            # the surface outright, and a denial is still a use.
            "text": _pair(
                "Watch the axis closest to changing this state. Nothing here tells "
                "you to act.",
                "关注最接近改变当前状态的坐标轴。此处不提供任何操作指示。"),
            "watch": {
                "label": _pair("Closest to changing", "最接近发生改变"),
                "axis_label": boundary.get("axis_label"),
                "distance": boundary.get("distance"),
            },
        }

    return {
        "token": "WATCH_ONLY",
        "heading": heading,
        "tone": "neutral",
        "text": _pair(
            "Nothing here asks you to act. Watch — don't chase.",
            "此处没有需要采取的操作。观察即可 — 不要追高杀跌。"),
        "watch": None,
    }


# --- public entry points ------------------------------------------------------

def build_view(snapshot: Mapping[str, Any], *, page_built_at: str,
               artifact: Mapping[str, Any],
               layout: str = LAYOUT_GRAMMAR) -> dict[str, Any]:
    """The complete section 6.3 view for one validated snapshot.

    ``artifact`` carries the publication receipt the page shows in the evidence
    drawer: ``{"path", "sha256", "bytes", "manifest_path", "min_client_contract"}``.

    ``layout`` selects the reading order the shell composes. ``LAYOUT_GRAMMAR``
    is the merged architecture section 6.3 order and stays the default for every
    workspace. ``LAYOUT_DECISION_FIRST`` leads with state / what changed / why it
    matters / next action and demotes the expanded diagnostics behind disclosure;
    it is authorized for the Liquidity Regime pattern-setter alone by the Sol
    ruling of 2026-09-05, recorded in
    ``research/market_intelligence_productization/MARKET_ONTOLOGY_F01_R1_DECISION_FIRST_AMENDMENT_2026-09-05.md``.
    The selector is a rendering order only: it changes no producer semantics, no
    metric, and no freshness or null verdict.
    """
    if layout not in _LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}; expected one of {sorted(_LAYOUTS)}")
    axes = [_axis_view(a) for a in (snapshot.get("axes") or {}).get("items") or []]
    context = _context(snapshot, page_built_at)
    headline = _headline(snapshot, axes)
    changes = _changes(snapshot)
    series = _series(snapshot)

    tabs = [
        {"tab_id": "current", "name": _pair("Current", "当前")},
        {"tab_id": "drivers", "name": _pair("Drivers", "驱动因子")},
        {"tab_id": "history", "name": _pair("History", "历史")},
    ]

    return {
        "ok": True,
        "layout": layout,
        "decision_first": layout == LAYOUT_DECISION_FIRST,
        "next_action": _next_action(context, headline),
        "workspace": {
            "id": (snapshot.get("workspace") or {}).get("id"),
            "title": _bilingual((snapshot.get("workspace") or {}).get("title")),
            "subtitle": _bilingual((snapshot.get("workspace") or {}).get("subtitle")),
        },
        "region": _region_view((snapshot.get("region") or {}).get("code"),
                               (snapshot.get("region") or {}).get("display_name"),
                               bool((snapshot.get("region") or {}).get("supported"))),
        "context": context,
        "implications": _implications(snapshot),
        "headline": headline,
        "axes": axes,
        "tabs": tabs,
        "withheld_tabs": _withheld_tabs(snapshot),
        "quadrant_map": _quadrant_map(headline, axes),
        "diagnostics": _diagnostics(snapshot, context, changes, series),
        "changes": changes,
        "metrics": _metrics(snapshot),
        "series": series,
        "drivers": _drivers(snapshot, axes),
        "evidence": _evidence(snapshot, context, page_built_at, artifact),
        "learning_events": list((snapshot.get("learning") or {}).get("event_names") or []),
        "page_built_at": page_built_at,
    }


def degraded_view(*, workspace_id: str, title: Mapping[str, str],
                  subtitle: Mapping[str, str], region_code: str,
                  region_display_name: str, page_built_at: str,
                  artifact: Mapping[str, Any], failure_kind: str,
                  failure_detail: str) -> dict[str, Any]:
    """The honest refusal page.

    Used when the artifact is missing, unreadable, fails the closed schema,
    declares an unsupported contract version, or does not match its published
    content hash. It renders the workspace identity, the typed failure, and the
    exact receipt — and NOTHING that could be mistaken for a state. There is no
    zero, no neutral quadrant, no empty chart.
    """
    return {
        "ok": False,
        "layout": LAYOUT_GRAMMAR,
        "decision_first": False,
        "workspace": {"id": workspace_id, "title": dict(title), "subtitle": dict(subtitle)},
        "region": _region_view(region_code, region_display_name, True),
        "page_built_at": page_built_at,
        "failure": {
            "kind": failure_kind,
            "label": L.label("null_reason", failure_kind),
            "detail": failure_detail,
            "headline": _pair("This workspace is not rendering a state",
                              "本工作区当前不呈现任何状态"),
            "body": _pair(
                "The published snapshot did not pass the closed contract, so nothing on "
                "this page may be read as the current regime. No value has been "
                "substituted, defaulted or estimated.",
                "已发布的快照未通过封闭契约校验，因此本页任何内容都不得视为当前体制读数。"
                "系统没有以任何默认值、替代值或估计值填补。"),
            "next": _pair("The page recovers automatically on the next accepted producer build.",
                          "下一次生产端成功构建后，本页将自动恢复。"),
        },
        "artifact": dict(artifact),
    }


# ==========================================================================
# Macro & Monetary suite hub (F01 / R1)
# ==========================================================================
#
# The hub COMPOSES what each workspace owner already published. It runs the
# same `_context`, `_headline` and `_changes` composers the workspace pages
# use, so the hub and the page can never disagree about a state, a clock or a
# delta. It originates nothing.
#
# Three constructions are deliberately absent, and must stay absent
# (`DNR:KILL-FUSED-COMPOSITE`, `DNR:KILL-REGIME-SCORECARD`, and the Sol ruling
# of 2026-09-05):
#   * no cross-workspace normalized magnitude,
#   * no fused composite or single "macro regime" verdict,
#   * no importance score, ranking or reordering of the closed registry order.
# Operational trouble is carried in its own attention notice precisely so that
# "this source broke" is never rendered as "this matters most".

#: How many change lines the hub prints before it defers to the workspaces.
HUB_CHANGE_LIMIT = 5

#: Freshness tokens that mean a reader must not treat the row as settled.
_ATTENTION_FRESHNESS = frozenset({
    "SOURCE_FAILED", "STALE_SOURCE", "RIGHTS_BLOCKED", "SIMULATED",
})

#: Null reasons that mean the same thing, in the null-reason vocabulary.
_ATTENTION_NULL_REASON = frozenset({
    "SOURCE_FAILED", "RIGHTS_BLOCKED", "DISAGREEMENT", "REVISION_PENDING_REBUILD",
})

#: Comparability states that mean a printed delta cannot be read as a like-for-like move.
_ATTENTION_COMPARABILITY = frozenset({
    "METHOD_CHANGED", "DEFINITION_INCOMPARABLE",
})


def _attention(vocabulary: str, token: Any) -> dict[str, Any]:
    """One typed attention cell, labelled in the vocabulary it actually came from.

    Resolving a comparability token through the null-reason table would mint an
    unreviewed label and register an unknown token, so the namespace travels
    with the token rather than being assumed at the call site.
    """
    return {
        "namespace": vocabulary,
        "token": str(token),
        "label": L.label(vocabulary, token),
        "tone": L.tone("freshness", token) if vocabulary == "freshness" else "warn",
    }


def _hub_attention_reason(context: Mapping[str, Any],
                          changes: Mapping[str, Any]) -> dict[str, Any] | None:
    """The one typed reason this row needs attention, or None when it is settled.

    Deterministic and token-driven: it reads the owner's own published freshness,
    null-reason and comparability vocabularies in a fixed precedence. It never
    weighs one workspace against another, and it never invents a severity — the
    attention notice is an operational note, not an importance ordering.
    """
    for token in (context.get("state"), context.get("worst_freshness_token")):
        if token in _ATTENTION_FRESHNESS:
            return _attention("freshness", token)
    if context.get("contradiction"):
        return _attention("null_reason", "DISAGREEMENT")
    for reason in context.get("reasons") or []:
        if reason in _ATTENTION_NULL_REASON:
            return _attention("null_reason", reason)
    if changes.get("comparability") in _ATTENTION_COMPARABILITY:
        return _attention("comparability", changes["comparability"])
    return None


def build_hub_view(entries: Sequence[Mapping[str, Any]], *,
                   page_built_at: str) -> dict[str, Any]:
    """The Macro & Monetary hub view.

    ``entries`` arrive in the closed registry order and are rendered in that
    order. Each entry is
    ``{"workspace_id", "region", "output", "title", "subtitle",
       "snapshot" | None, "failure" | None}``.
    """
    rows: list[dict[str, Any]] = []
    changes_pool: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    effective_dates: list[str] = []

    for entry in entries:
        snapshot = entry.get("snapshot")
        row: dict[str, Any] = {
            "workspace_id": entry["workspace_id"],
            "href": entry["output"],
            "title": dict(entry["title"]),
            "subtitle": dict(entry["subtitle"]),
            "region": entry.get("region"),
        }

        if not snapshot:
            failure = entry.get("failure") or {}
            kind = failure.get("kind") or "UNKNOWN"
            row.update({
                "available": False,
                "absence": _absence(kind),
                # An unreadable workspace is NEVER calm and NEVER zero. It says
                # so in words, and it says what would fix it.
                "absence_text": _pair(
                    "Not readable in this build — no state is shown for it.",
                    "本次构建无法读取 — 因此不展示任何状态读数。"),
                "recovery_text": _pair(
                    "Recovers on the next accepted producer build.",
                    "下一次生产端成功构建后自动恢复。"),
            })
            rows.append(row)
            unavailable.append({"workspace_id": entry["workspace_id"],
                                "title": dict(entry["title"]),
                                "reason": _absence(kind)})
            attention.append({"workspace_id": entry["workspace_id"],
                              "title": dict(entry["title"]),
                              "href": entry["output"],
                              "reason": _attention("null_reason", kind),
                              "tone": "bad"})
            continue

        axes = [_axis_view(a) for a in (snapshot.get("axes") or {}).get("items") or []]
        context = _context(snapshot, page_built_at)
        headline = _headline(snapshot, axes)
        changes = _changes(snapshot)

        if headline.get("effective_date"):
            effective_dates.append(str(headline["effective_date"]))

        row.update({
            "available": True,
            "state_id": headline.get("state_id"),
            "state_label": headline.get("state_label"),
            "effective_date": headline.get("effective_date"),
            "freshness": context.get("state_label"),
            "freshness_tone": context.get("state_tone"),
            "coverage": context.get("coverage"),
            "comparability_label": changes.get("comparability_label"),
            "comparable": changes.get("comparable"),
            "change_count": len(changes.get("deltas") or []),
            "changes_absence": changes.get("absence"),
        })
        rows.append(row)

        # Changes are pooled in registry order and truncated in registry order.
        # No magnitude comparison decides what a reader sees first.
        for delta in changes.get("deltas") or []:
            # A row the producer published with no prior, no current and no delta
            # is not a change — it is a metric that could not be compared. Putting
            # it here would spend one of the few slots saying nothing, and would
            # print a bare em dash where the reader expects a move. The workspace's
            # own what-changed table still carries the row and its typed reason.
            if not (delta.get("delta") and delta.get("prior") and delta.get("current")):
                continue
            changes_pool.append({
                "workspace_id": entry["workspace_id"],
                "workspace_title": dict(entry["title"]),
                "href": entry["output"],
                "label": delta.get("label"),
                "prior": delta.get("prior"),
                "current": delta.get("current"),
                "delta": delta.get("delta"),
                "sign": delta.get("sign"),
            })

        reason = _hub_attention_reason(context, changes)
        if reason:
            attention.append({"workspace_id": entry["workspace_id"],
                              "title": dict(entry["title"]),
                              "href": entry["output"],
                              "reason": reason,
                              "tone": reason["tone"]})

    available = [r for r in rows if r.get("available")]
    shown = changes_pool[:HUB_CHANGE_LIMIT]

    return {
        "page_built_at": page_built_at,
        "kicker": _pair("Macro & Monetary", "宏观与货币"),
        "title": _pair("Macro & Monetary", "宏观与货币"),
        "deck": _pair("Fourteen research workspaces, one current read.",
                      "十四个研究工作区，一个当前读数。"),
        "as_of": {
            # The suite is only as current as its oldest accepted print.
            "effective_date": min(effective_dates) if effective_dates else None,
            "newest_effective_date": max(effective_dates) if effective_dates else None,
            "label": _pair("Suite effective date", "套件生效日期"),
            "note": _pair(
                "The suite is dated by its oldest accepted workspace print, never its newest.",
                "套件日期取自最旧的已接受工作区读数，而非最新读数。"),
        },
        "coverage": {
            "available": len(available),
            "total": len(rows),
            "complete": len(available) == len(rows),
            "label": _pair("Workspaces readable", "可读取工作区"),
        },
        "workspaces": rows,
        "changes": {
            "entries": shown,
            "shown": len(shown),
            "remaining": max(0, len(changes_pool) - len(shown)),
            "total": len(changes_pool),
            "heading": _pair("Recent changes", "近期变化"),
            # Named honestly: these are the first N in the suite's own order, not
            # a curated set of the N that matter most.
            "note": _pair(
                "The first few changes in suite order — not a ranking. Open a workspace for its full list.",
                "按套件既定顺序列出的前几项变化 — 并非重要性排序。完整列表请进入相应工作区。"),
            "empty_text": _pair(
                "No workspace published a method-comparable change in this build.",
                "本次构建中，没有工作区发布方法可比的变化。"),
        },
        "attention": {
            "entries": attention,
            "count": len(attention),
            "heading": _pair("Needs data attention", "数据需要关注"),
            "note": _pair(
                "Source or revision trouble. This is an operational note, not a judgement about what matters.",
                "数据源或修订问题。这是运行状态提示，不代表重要性判断。"),
            "clear_text": _pair("Every workspace read cleanly in this build.",
                                "本次构建中所有工作区均读取正常。"),
        },
        "unavailable": unavailable,
    }
