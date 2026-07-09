"""engine.neuralweb.attention_deterministic — deterministic operator-attention items.

PURPOSE
-------
Produces a display-only, zero-LLM list of attention items derived entirely from
structured artifact values committed to the repo.  Every rule is deterministic and
pre-registered here in the module docstring — no model inference, no NLP, no
trading verbs.

PRE-REGISTERED RULES
--------------------
Rule A — contradiction tension:
    Any record in world_state.contradictions (or confluence_graph contradiction
    nodes) whose severity == 'tension' raises a P2 item.

Rule B — daily-cadence lobe past 1.5× SLA:
    Any lobe in health.json with cadence == 'daily' (any variant) and
    age_hours > 1.5 × freshness_sla_hours raises a P2 item.
    Lobes with missing age_hours or freshness_sla_hours are skipped (fail-open).

Rule C — regime confidence low:
    If world_state.regime.confidence < 0.25, raises a P2 item labelled
    'regime indeterminate'.

Rule D — evidence clock overdue:
    If daily_brief.evidence_clock.counts.overdue > 0, raises a P3 item with
    the count and top-due clock id.

Rule E — cortex degraded:
    If health.json cortex.run_status.degraded == True, raises a P3 item noting
    that the cortex deliberation is currently unavailable.

ITEM SHAPE
----------
Each item is a dict::

    {
        "kind":         str,   # one of: contradiction_tension | lobe_sla_breach |
                               #   regime_indeterminate | evidence_clock_overdue |
                               #   cortex_degraded
        "severity":    str,   # "P1" | "P2" | "P3"  (maintenance vocabulary)
        "summary_en":  str,   # plain-English summary (no trading verbs)
        "summary_zh":  str,   # Mandarin summary (no trading verbs)
        "evidence_path": str, # artifact path supporting this item
        "as_of":       str,   # ISO-8601 date or datetime for freshness context
    }

CONSTRAINTS
-----------
- NO LLM anywhere — all text is template-filled from structured values.
- NO writes to data/reflexes/cortex_attention/ (that is the cortex A2 earn-in
  track; this artifact is a separate display-only surface).
- Trading-verb scrub applied to any upstream-sourced free-text strings before
  they enter the artifact (same scrub as daily_brief.py).
- Fail-open: any rule that raises an unhandled exception logs a warning and
  returns zero items from that rule — never blocks the build.
- Output is display-only, annotate-never-rank (Article 2).
- Empty inputs → empty items list (not an error).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trading-verb scrub (same vocabulary as daily_brief.py)
# ---------------------------------------------------------------------------

_TRADING_VERBS: frozenset[str] = frozenset(
    {"buy", "sell", "hold", "add", "trim", "long", "short", "overweight", "underweight"}
)


def _scrub(text: str) -> str:
    """Redact trading verbs from *text* before it enters the artifact."""
    result = text
    for verb in _TRADING_VERBS:
        pattern = re.compile(r"(?<!\w)" + re.escape(verb) + r"(?!\w)", re.IGNORECASE)
        if pattern.search(result):
            log.warning("attention_deterministic: trading verb %r scrubbed from upstream string", verb)
            result = pattern.sub("[redacted]", result)
    return result


# ---------------------------------------------------------------------------
# Rule implementations — each returns list[dict], never raises
# ---------------------------------------------------------------------------


def _rule_a_contradiction_tension(
    world_state: dict,
    confluence_graph: dict | None,
    as_of: str,
) -> list[dict]:
    """Rule A: contradiction records with severity == 'tension'.

    Sources checked (in order of preference):
    1. confluence_graph.contradiction_records — full record list with per-record severity.
    2. world_state.contradictions.by_severity — summary dict (used if cg absent).
    """
    items: list[dict] = []
    try:
        # Source 1: full records from confluence_graph
        if confluence_graph:
            cg_records: list[dict] = confluence_graph.get("contradiction_records", []) or []
            for rec in cg_records:
                if not isinstance(rec, dict):
                    continue
                sev = (rec.get("severity") or "").lower()
                if sev == "tension":
                    label = _scrub(rec.get("pair_id") or rec.get("label") or rec.get("note") or "")
                    items.append(
                        {
                            "kind": "contradiction_tension",
                            "severity": "P2",
                            "summary_en": (
                                f"Tension: {label}" if label else "Tension-severity contradiction detected"
                            ),
                            "summary_zh": f"矛盾张力：{label}" if label else "检测到张力级矛盾",
                            "evidence_path": "site/neuralwebdata/confluence_graph.json",
                            "as_of": as_of,
                        }
                    )
            return items

        # Source 2 (fallback): world_state.contradictions summary dict
        ws_contras = world_state.get("contradictions") or {}
        if isinstance(ws_contras, dict):
            by_sev = ws_contras.get("by_severity") or {}
            tension_n = int(by_sev.get("tension", 0) or 0)
            if tension_n > 0:
                items.append(
                    {
                        "kind": "contradiction_tension",
                        "severity": "P2",
                        "summary_en": (
                            f"{tension_n} tension-severity contradiction(s) detected"
                        ),
                        "summary_zh": f"检测到 {tension_n} 个张力级矛盾",
                        "evidence_path": "data/neuralweb/world_state.json",
                        "as_of": as_of,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_deterministic rule_a failed: %s", exc)
    return items


def _rule_b_lobe_sla_breach(health: dict, as_of: str) -> list[dict]:
    """Rule B: daily-cadence lobes past 1.5× their freshness SLA."""
    items: list[dict] = []
    try:
        lobes: list[dict] = health.get("lobes", []) or []
        for lobe in lobes:
            cadence: str = (lobe.get("cadence") or "").lower()
            if "daily" not in cadence:
                continue
            age_hours = lobe.get("age_hours")
            sla_hours = lobe.get("freshness_sla_hours")
            if age_hours is None or sla_hours is None or sla_hours <= 0:
                continue
            try:
                age_f = float(age_hours)
                sla_f = float(sla_hours)
            except (TypeError, ValueError):
                continue
            if age_f > 1.5 * sla_f:
                lobe_id = lobe.get("id") or "unknown"
                items.append(
                    {
                        "kind": "lobe_sla_breach",
                        "severity": "P2",
                        "summary_en": (
                            f"Lobe '{lobe_id}' overdue: {age_f:.0f}h old vs {sla_f:.0f}h SLA"
                            f" ({age_f / sla_f:.1f}×)"
                        ),
                        "summary_zh": (
                            f"脉叶 '{lobe_id}' 过期：{age_f:.0f}小时，SLA {sla_f:.0f}小时"
                            f"（{age_f / sla_f:.1f}倍）"
                        ),
                        "evidence_path": "site/neuralwebdata/health.json",
                        "as_of": as_of,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_deterministic rule_b failed: %s", exc)
    return items


def _rule_c_regime_indeterminate(world_state: dict, as_of: str) -> list[dict]:
    """Rule C: regime confidence < 0.25."""
    items: list[dict] = []
    try:
        regime = world_state.get("regime") or {}
        confidence = regime.get("confidence")
        if confidence is None:
            return items
        try:
            conf_f = float(confidence)
        except (TypeError, ValueError):
            return items
        if conf_f < 0.25:
            quad = regime.get("quad") or regime.get("label") or "unknown"
            items.append(
                {
                    "kind": "regime_indeterminate",
                    "severity": "P2",
                    "summary_en": (
                        f"Regime indeterminate: {quad} confidence {conf_f:.0%}"
                        " (below 25% threshold)"
                    ),
                    "summary_zh": (
                        f"周期不明确：{quad} 置信度 {conf_f:.0%}（低于25%阈值）"
                    ),
                    "evidence_path": "data/neuralweb/world_state.json",
                    "as_of": as_of,
                }
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_deterministic rule_c failed: %s", exc)
    return items


def _rule_d_evidence_clock_overdue(daily_brief: dict, as_of: str) -> list[dict]:
    """Rule D: evidence_clock overdue count > 0."""
    items: list[dict] = []
    try:
        ec = daily_brief.get("evidence_clock") or {}
        counts = ec.get("counts") or {}
        overdue_n: int = int(counts.get("overdue", 0) or 0)
        if overdue_n <= 0:
            return items
        top_due = ec.get("top_due") or {}
        top_id = top_due.get("clock_id") or ""
        items.append(
            {
                "kind": "evidence_clock_overdue",
                "severity": "P3",
                "summary_en": (
                    f"{overdue_n} evidence clock(s) overdue"
                    + (f"; top: {top_id}" if top_id else "")
                ),
                "summary_zh": (
                    f"{overdue_n} 个证据时钟逾期"
                    + (f"；最高优先级：{top_id}" if top_id else "")
                ),
                "evidence_path": "data/neuralweb/evidence_clock.json",
                "as_of": as_of,
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_deterministic rule_d failed: %s", exc)
    return items


def _rule_e_cortex_degraded(health: dict, as_of: str) -> list[dict]:
    """Rule E: cortex run_status.degraded == True."""
    items: list[dict] = []
    try:
        cortex = health.get("cortex") or {}
        run_status = cortex.get("run_status") or {}
        if not isinstance(run_status, dict):
            return items
        is_degraded: bool = bool(run_status.get("degraded", False))
        if not is_degraded:
            return items
        reason = _scrub(run_status.get("degradation_reason") or "")
        items.append(
            {
                "kind": "cortex_degraded",
                "severity": "P3",
                "summary_en": (
                    "Cortex deliberation unavailable"
                    + (f": {reason}" if reason else "")
                ),
                "summary_zh": (
                    "皮层审议当前不可用"
                    + (f"：{reason}" if reason else "")
                ),
                "evidence_path": "site/neuralwebdata/health.json",
                "as_of": as_of,
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("attention_deterministic rule_e failed: %s", exc)
    return items


# ---------------------------------------------------------------------------
# Public build function
# ---------------------------------------------------------------------------


def build(
    *,
    world_state: dict,
    health: dict,
    daily_brief: dict,
    confluence_graph: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build the attention_deterministic artifact.

    Parameters
    ----------
    world_state:
        Parsed data/neuralweb/world_state.json.
    health:
        Parsed data/neuralweb/health.json.
    daily_brief:
        Parsed data/neuralweb/daily_brief.json.
    confluence_graph:
        Optional parsed data/neuralweb/confluence_graph.json.
    now:
        UTC datetime for as_of and produced_at (injectable for deterministic tests).

    Returns
    -------
    dict
        Artifact payload (WITHOUT envelope — caller applies stamp()).
    """
    now = now or datetime.now(timezone.utc)
    as_of: str = now.strftime("%Y-%m-%d")

    # Run each rule — all fail-open
    items: list[dict] = []
    items.extend(_rule_a_contradiction_tension(world_state, confluence_graph, as_of))
    items.extend(_rule_b_lobe_sla_breach(health, as_of))
    items.extend(_rule_c_regime_indeterminate(world_state, as_of))
    items.extend(_rule_d_evidence_clock_overdue(daily_brief, as_of))
    items.extend(_rule_e_cortex_degraded(health, as_of))

    # Sort by severity (P1 first) then kind for stable output
    _sev_order = {"P1": 0, "P2": 1, "P3": 2}
    items.sort(key=lambda x: (_sev_order.get(x.get("severity", "P3"), 99), x.get("kind", "")))

    # Summary counts for quick consumer access
    counts: dict[str, int] = {}
    for item in items:
        sev = item.get("severity", "unknown")
        counts[sev] = counts.get(sev, 0) + 1

    return {
        "as_of": as_of,
        "item_count": len(items),
        "counts_by_severity": counts,
        "items": items,
        "caveats": [
            "deterministic: all items are template-filled from structured artifact values; no LLM",
            "display-only: no signals, no scoring authority, no ranking authority",
            "no trading authority: items contain no buy/sell/hold guidance",
            "does not write to data/reflexes/cortex_attention/ (cortex A2 earn-in track is separate)",
        ],
    }
