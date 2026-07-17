"""engine.neuralweb.brief_context — ADB-W1 budgeted NW context composer.

Public API
----------
macro_slice(root=None) -> dict
    Compose the Neural Web context packet for the macro brief (≤10 240 bytes
    serialised).

china_slice(root=None) -> dict
    Compose the Neural Web context packet for the China/HK brief (≤6 144 bytes
    serialised).

Every block carries:
  as_of          str | None   — the artifact's own data-as-of date
  display_only   True         — always
  _tape_family   str          — provenance (ADB-R3)
  _lead_lag      str          — coincident / leading / n/a
  stale          bool         — True when data-asof is more than SLA hours old
                                 (keyed off asof, NOT produced_at — ADB-R11)

Absent or unreadable artifact → {absent: True, reason: str}.

Serialised budget caps (ADB-R2):
  macro_slice  ≤ 10 240 bytes  (10 KB)
  china_slice  ≤  6 144 bytes  ( 6 KB)

When over budget the lowest-priority blocks are dropped in the documented order
below until under budget.  As a last resort, list-valued fields are trimmed.
No exception is ever raised (ADB-R1).

Drop order for macro_slice (lowest priority first):
  12. causal_lab
  11. evidence_clock
  10. attention
   9. sequence
   8. strength
   7. themes
   6. covariance
   5. factor_weather
   4. cross_asset_flows
   3. liquidity_plumbing
   2. contradictions
   1c. global_regimes
   1b. contagion  (CSP-W1; absent = drops cleanly)
   1a. market_core

Drop order for china_slice (lowest priority first):
  5. evidence_morning_line
  4. cortex (tail still kept but payload trimmed)
  3. contradictions
  2. themes_china
  1. global_weather
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLA table (default 30h; keyed by artifact slug).
# Staleness is keyed off the artifact's DATA asof, not produced_at.
# ---------------------------------------------------------------------------
_SLA_HOURS: dict[str, float] = {
    "world_state":              30.0,
    "liquidity_plumbing":       30.0,
    "covariance_spine":         48.0,
    "theme_state":              30.0,
    "confluence_sequence":      30.0,
    "confluence_strength":      30.0,
    "attention_deterministic":  30.0,
    "evidence_clock":           30.0,
    "causal_lab_state":         36.0,
    "cortex_memo":              30.0,
    "mastermind_context":       30.0,
}

_DEFAULT_SLA_HOURS: float = 30.0

# Serialised byte caps
_MACRO_CAP = 10_240
_CHINA_CAP = 6_144

# Tape note for nw_synthesis family (ADB-R3)
_NW_SYNTHESIS_TAPE_NOTE = (
    "cross-stock aggregation of the same US price tape as the macro block "
    "— decomposition, not independent confirmation"
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(s: str | None) -> datetime | None:
    """Parse an ISO date or datetime string into an aware UTC datetime."""
    if not s:
        return None
    try:
        # Try full ISO datetime first
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        # Plain date YYYY-MM-DD
        d = datetime.strptime(s[:10], "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _is_stale(asof_str: str | None, sla_key: str) -> bool:
    """Return True if the data-asof date exceeds the SLA threshold."""
    dt = _parse_date(asof_str)
    if dt is None:
        return True  # unknown asof → treat as stale
    sla_hours = _SLA_HOURS.get(sla_key, _DEFAULT_SLA_HOURS)
    age_hours = (_utcnow() - dt).total_seconds() / 3600
    return age_hours > sla_hours


def _read_json(path: Path) -> dict | None:
    """Read a JSON file; return None on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.debug("brief_context: cannot read %s: %s", path, exc)
        return None


def _absent(reason: str) -> dict:
    return {"absent": True, "reason": reason, "display_only": True}


def _enforce_budget(result: dict, cap: int, drop_order: list[str]) -> dict:
    """Drop lowest-priority blocks until serialised size ≤ cap.

    Phase 1: drop whole blocks in drop_order (lowest priority first).
    Phase 2 (last resort): trim list-valued fields across remaining blocks
    until under cap.  The byte cap is always honoured.
    """
    remaining_to_drop = list(drop_order)
    while remaining_to_drop:
        serialised = json.dumps(result, separators=(",", ":"), default=str)
        if len(serialised) <= cap:
            break
        key = remaining_to_drop.pop(0)
        result.pop(key, None)

    # Hard last-resort: trim list fields if still over cap
    serialised = json.dumps(result, separators=(",", ":"), default=str)
    if len(serialised) > cap:
        for block_key, block in list(result.items()):
            if not isinstance(block, dict):
                continue
            for field_key, val in list(block.items()):
                if isinstance(val, list) and val:
                    block[field_key] = val[:max(0, len(val) - 1)]
                    serialised = json.dumps(result, separators=(",", ":"), default=str)
                    if len(serialised) <= cap:
                        break
            if len(serialised) <= cap:
                break

    assert len(json.dumps(result, separators=(",", ":"), default=str)) <= cap, (
        "brief_context: budget cap violated after exhaustive enforcement"
    )
    return result


# ---------------------------------------------------------------------------
# Block composers — each returns a self-contained dict or an absent marker
# ---------------------------------------------------------------------------

def _block_market_core(ws: dict | None, asof_str: str | None) -> dict:
    """Block 1: market_core from world_state."""
    if ws is None:
        return _absent("world_state.json unreadable")
    verdict = ws.get("verdict") or {}
    regime = ws.get("regime") or {}
    breadth = ws.get("breadth") or {}
    recovery = (ws.get("cycle_pattern") or {}).get("recovery") or {}
    data_asof = (
        verdict.get("asof")
        or regime.get("asof")
        or asof_str
    )
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "world_state"),
        "verdict": {
            "verdict": verdict.get("verdict"),
            "score": verdict.get("score"),
            "label_en": verdict.get("label_en"),
            "label_zh": verdict.get("label_zh"),
        },
        "regime": {
            "quad": regime.get("quad"),
            "confidence": regime.get("confidence"),
            "transition_state": regime.get("transition_state"),
            "flip_margin": regime.get("flip_margin"),
        },
        "breadth": {
            "pct_above_50": breadth.get("pct_above_50"),
            "pct_above_200": breadth.get("pct_above_200"),
            "pctile": breadth.get("breadth_above200_pctile"),
        },
        "recovery": {
            "turn_confirmed": recovery.get("turn_confirmed"),
            "phase": recovery.get("phase"),
        },
    }


def _block_contradictions(ws: dict | None, asof_str: str | None) -> dict:
    """Block 2: contradictions from world_state."""
    if ws is None:
        return _absent("world_state.json unreadable")
    contra = ws.get("contradictions") or {}
    data_asof = asof_str
    top_pair_ids = contra.get("top_pair_ids") or []
    # Build top named pair notes (max 3)
    top_notes = top_pair_ids[:3]
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "world_state"),
        "n": contra.get("n", 0),
        "by_severity": contra.get("by_severity") or {},
        "top_pair_notes": top_notes,
    }


def _block_cross_asset_flows(ws: dict | None) -> dict:
    """Block 3: cross_asset_flows from world_state."""
    if ws is None:
        return _absent("world_state.json unreadable")
    caf = ws.get("cross_asset_flows") or {}
    if not caf:
        return _absent("world_state.cross_asset_flows missing")
    data_asof = caf.get("asof")
    return {
        "display_only": True,
        "_tape_family": "flows",
        "_lead_lag": "coincident",
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "world_state"),
        "correlation": caf.get("correlation") or {},
        "global_liquidity_dir": caf.get("global_liquidity_dir"),
        "leadlag": caf.get("leadlag") or {},
    }


def _block_liquidity_plumbing(lp_data: dict | None) -> dict:
    """Block 4: liquidity_plumbing."""
    if lp_data is None:
        return _absent("liquidity_plumbing.json unreadable")
    data_asof = lp_data.get("asof")
    headline = lp_data.get("headline") or {}
    quantity = lp_data.get("quantity") or {}
    rrp = lp_data.get("rrp") or {}
    quality = lp_data.get("quality") or {}
    return {
        "display_only": True,
        "_tape_family": "rates_credit",
        "_lead_lag": "leading",
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "liquidity_plumbing"),
        "headline_state": headline.get("state"),
        "quantity": {
            "netliq_chg_20d_bn": quantity.get("netliq_chg_20d_bn"),
            "netliq_pctile_expanding": quantity.get("netliq_pctile_expanding"),
        },
        "rrp_buffer_state": rrp.get("buffer_state"),
        "quality_label": quality.get("label"),
        # Standing condition note per memory rrp_exhausted = regime CONSTANT since 2025-12-31
        "rrp_note": (
            "RRP exhausted is a standing regime condition since 2025-12-31 — "
            "buffer_state reflects this constant, not a new development."
        ),
    }


def _block_global_regimes(ws: dict | None, mc: dict | None, asof_str: str | None) -> dict:
    """Block 5: global_regimes from world_state (fallback: mastermind_context lobes.macro_weather)."""
    gr = None
    source = "world_state"
    if ws is not None:
        gr = ws.get("global_regimes")
    if not gr and mc is not None:
        mw = (mc.get("lobes") or {}).get("macro_weather") or {}
        if mw:
            gr = {
                "us": {"quad": mw.get("us_quad")},
                "china": {"quad": mw.get("china_quad")},
                "hk": {"quad": mw.get("hk_quad")},
                "canada": {"quad": mw.get("canada_quad")},
                "dispersion_note": mw.get("contradiction_note"),
            }
            source = "mastermind_context.macro_weather"
    if not gr:
        return _absent("global_regimes not available in world_state or mastermind_context")
    data_asof = asof_str
    # Extract compact per-region block
    def _region(r: dict | None) -> dict:
        if not r:
            return {}
        return {k: r.get(k) for k in ("quad", "quad_name", "confidence", "cycle_tag",
                                       "liquidity_overlay", "stale") if r.get(k) is not None}
    return {
        "display_only": True,
        "_tape_family": "price_regime",
        "_lead_lag": "coincident",
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "world_state"),
        "source": source,
        "us": _region(gr.get("us") or {}),
        "china": _region(gr.get("china") or {}),
        "hk": _region(gr.get("hk") or {}),
        "canada": _region(gr.get("canada") or {}),
        "dispersion_note": gr.get("dispersion_note"),
    }


def _block_factor_weather(ws: dict | None) -> dict:
    """Block 6: factor_weather from world_state."""
    if ws is None:
        return _absent("world_state.json unreadable")
    fw = ws.get("factor_weather") or {}
    if not fw:
        return _absent("world_state.factor_weather missing")
    data_asof = fw.get("factor_state_as_of")
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "world_state"),
        "style_regime": fw.get("style_regime"),
        "factor_leader": fw.get("factor_leader"),
    }


def _block_covariance(cv_data: dict | None) -> dict:
    """Block 7: covariance from covariance_spine.json."""
    if cv_data is None:
        return _absent("covariance_spine.json unreadable")
    data_asof = cv_data.get("as_of")
    blocks = cv_data.get("blocks") or {}
    rates = blocks.get("rates") or {}
    factors = blocks.get("factors") or {}
    dispersion = blocks.get("dispersion") or {}
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "covariance_spine"),
        "rates_dominant_pc_share": rates.get("dominant_pc_share"),
        "factors_effective_factor_bets_pr": factors.get("effective_factor_bets_pr"),
        "dispersion_state": dispersion.get("state"),
    }


def _block_themes(ts_data: dict | None) -> dict:
    """Block 8: themes from theme_state.json."""
    if ts_data is None:
        return _absent("theme_state.json unreadable")
    data_asof = ts_data.get("as_of")
    themes = ts_data.get("themes") or []
    n_themes = ts_data.get("n_themes", len(themes))
    # Stage counts from foresight.stage
    stage_counts: dict[str, int] = {}
    noteworthy = []
    for t in themes:
        fc = t.get("foresight") or {}
        stage = fc.get("stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        if len(noteworthy) < 3:
            noteworthy.append({
                "name": t.get("name_en", t.get("theme_id", "?")),
                "stage": stage,
            })
    # n_falsifiers_fired — count themes with any falsifier indication
    n_falsifiers_fired = ts_data.get("n_falsifiers_fired", 0)
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "theme_state"),
        "n_themes": n_themes,
        "stage_counts": stage_counts,
        "n_falsifiers_fired": n_falsifiers_fired,
        "noteworthy": noteworthy,
    }


def _block_sequence(cs_data: dict | None) -> dict:
    """Block 9: sequence from confluence_sequence.json.

    Only macro-level subjects (regime:/breadth:/sector: prefix) are included.
    When no macro-prefix subjects match, subjects is [] with an explanatory note
    (ADB-R2: per-ticker subjects must never reach the macro prompt).
    """
    if cs_data is None:
        return _absent("confluence_sequence.json unreadable")
    data_asof = cs_data.get("asof")
    subjects = cs_data.get("subjects") or []
    # Only macro-level subjects — NO ticker fallback (ADB-R2)
    macro_subjects = [
        s for s in subjects
        if any(s.get("subject", "").startswith(p) for p in ("regime:", "breadth:", "sector:"))
    ]
    top_subjects = [
        {
            "subject": s.get("subject"),
            "persistence_streak": s.get("persistence_streak"),
            "state": s.get("state"),
        }
        for s in macro_subjects[:5]
    ]
    cpairs = cs_data.get("contradiction_pairs") or []
    top_cpairs = [
        {
            "pair_id": cp.get("pair_id"),
            "persistence_streak": cp.get("persistence_streak"),
            "state": cp.get("state"),
        }
        for cp in cpairs[:3]
    ]
    result: dict[str, Any] = {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "confluence_sequence"),
        "subjects": top_subjects,
        "contradiction_pairs": top_cpairs,
    }
    if not macro_subjects:
        result["note"] = "no macro-level subjects in tape"
    return result


_MACRO_SUBJECT_PREFIXES = ("regime:", "breadth:", "sector:")


def _block_strength(cst_data: dict | None) -> dict:
    """Block 9b: strength from confluence_strength.json (ADB-R11 live stale case).

    The live acceptance criterion: produced_at may be fresh while the artifact's
    data asof is 2026-07-02 (~240h vs 30h SLA) — stale must be True.
    asof_field in synapse: 'produced_at' (the file's envelope key), but
    ADB-R11 requires staleness keyed off the DATA asof, not produced_at.
    The data asof key in the file is 'asof'.

    Only macro-prefix subjects (regime:/breadth:/sector:) are included.
    Per-ticker rows are stripped (ADB-R2).
    """
    if cst_data is None:
        return _absent("confluence_strength.json unreadable")
    # The artifact uses 'asof' for data-as-of (may be 2026-07-02 in production)
    data_asof = cst_data.get("asof")
    rows = cst_data.get("rows") or []
    n_rows = len(rows)
    # Filter to macro-prefix subjects only (ADB-R2)
    macro_rows = [
        r for r in rows
        if any(r.get("subject", "").startswith(p) for p in _MACRO_SUBJECT_PREFIXES)
    ]
    macro_subjects = [
        {
            "subject": r.get("subject"),
            "n_independent_confirming": r.get("n_independent_confirming"),
            "state": r.get("state"),
            "direction": r.get("direction"),
        }
        for r in macro_rows[:5]
    ]
    result: dict[str, Any] = {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "confluence_strength"),
        "n_rows": n_rows,
        "subjects": macro_subjects,
    }
    if not macro_rows:
        result["note"] = "no macro-level subjects in tape"
    return result


def _block_attention(ad_data: dict | None) -> dict:
    """Block 10: attention from attention_deterministic.json."""
    if ad_data is None:
        return _absent("attention_deterministic.json unreadable")
    data_asof = ad_data.get("as_of")
    items = ad_data.get("items") or []
    top_items = [
        {
            "kind": it.get("kind"),
            "severity": it.get("severity"),
            "summary_en": it.get("summary_en"),
        }
        for it in items[:5]
    ]
    return {
        "display_only": True,
        "_tape_family": "nw_synthesis",
        "_lead_lag": "coincident",
        "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "attention_deterministic"),
        "items": top_items,
    }


def _block_evidence_clock(ec_data: dict | None) -> dict:
    """Block 11: evidence_clock from evidence_clock.json."""
    if ec_data is None:
        return _absent("evidence_clock.json unreadable")
    data_asof = ec_data.get("as_of")
    summary = ec_data.get("summary") or {}
    return {
        "display_only": True,
        "_tape_family": "ops",
        "_lead_lag": "n/a",
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "evidence_clock"),
        "morning_line": summary.get("morning_line"),
        "top_due": summary.get("top_due") or {},
    }


def _block_causal_lab(cl_data: dict | None) -> dict:
    """Block 12: causal_lab from causal_lab_state.json."""
    if cl_data is None:
        return _absent("causal_lab_state.json unreadable")
    data_asof = cl_data.get("asof")
    # Parse asof — can be full ISO datetime
    data_asof_date = data_asof[:10] if data_asof else None
    funnel = cl_data.get("funnel") or {}
    ll = cl_data.get("llm_lane") or {}
    return {
        "display_only": True,
        "_tape_family": "ops",
        "_lead_lag": "n/a",
        "as_of": data_asof_date,
        "stale": _is_stale(data_asof, "causal_lab_state"),
        "new_edges_this_week_by_verdict": funnel.get("edges_by_verdict") or {},
        "nulls_added": funnel.get("nulls_count", 0),
        "llm_lane_status": ll.get("status"),
    }


def _block_cortex(memo: dict | None) -> dict:
    """Block 13: cortex per ADB-R5.

    If run_status.status != 'degraded': include summary, what_fired,
    deserves_operator, decaying_families, memo_as_of, age_hours, is_context_only.
    If degraded: {status:'degraded', reason: ...}.
    Always includes memo_as_of/age when present.
    """
    if memo is None:
        return _absent("cortex/memo.json unreadable")
    rs = memo.get("run_status") or {}
    data_asof = memo.get("as_of")
    age_hours: float | None = None
    if data_asof:
        dt = _parse_date(data_asof)
        if dt:
            age_hours = round((_utcnow() - dt).total_seconds() / 3600, 1)
    if rs.get("status") == "degraded":
        return {
            "display_only": True,
            "_tape_family": "ops",
            "_lead_lag": "n/a",
            "as_of": data_asof,
            "stale": _is_stale(data_asof, "cortex_memo"),
            "status": "degraded",
            "reason": rs.get("degradation_reason"),
            "memo_as_of": data_asof,
            "age_hours": age_hours,
        }
    # Memo strings are model-authored and unbounded; clip them so a verbose
    # memo can never blow the byte cap (cortex is undroppable by design —
    # an oversized packet would otherwise discard the whole slice).
    def _clip(s, n=600):
        return s[:n] if isinstance(s, str) else s

    def _clip_list(v, items=5, each=200):
        if not isinstance(v, list):
            return v
        return [_clip(x, each) if isinstance(x, str) else x for x in v[:items]]

    return {
        "display_only": True,
        "_tape_family": "ops",
        "_lead_lag": "n/a",
        "as_of": data_asof,
        "stale": _is_stale(data_asof, "cortex_memo"),
        "is_context_only": True,
        "summary": _clip(memo.get("summary")),
        "what_fired": _clip_list(memo.get("what_fired")),
        "deserves_operator": _clip_list(memo.get("deserves_operator")),
        "decaying_families": _clip_list(memo.get("decaying_families")),
        "memo_as_of": data_asof,
        "age_hours": age_hours,
    }


# ---------------------------------------------------------------------------
# CSP-W1: contagion block (reads world_state.contagion_regime)
# ---------------------------------------------------------------------------

def _block_contagion(ws: dict | None) -> dict | None:
    """Block contagion: contagion_regime from world_state (CSP-W1).

    Budget: ~0.6 KB.  Returns None when the block is entirely null/degraded
    so it drops cleanly from the macro_slice.

    Deterministic numeric text only — engine-computed fields re-projected to
    the AI context plane.  No LLM-originated content.

    Honesty tail per #2752 chip idiom: "accruing — unproven; does not change
    the score" is appended whenever the block is present and non-trivial.
    """
    if ws is None:
        return None
    cr = ws.get("contagion_regime")
    if not cr or not isinstance(cr, dict):
        return None

    state = cr.get("state")
    leadership_state = cr.get("leadership_state")
    us_spillover = cr.get("us_spillover")
    n_alert = cr.get("n_alert")
    d3_alert = cr.get("d3_alert")
    n_mature = cr.get("n_mature")
    origin_complex = cr.get("origin_complex")
    intl_markets = cr.get("intl_markets_in_alert") or []
    degraded = cr.get("degraded") or []
    asof = cr.get("asof")

    # Drop when fully null/degraded (pre-#2752 lanes where all sources absent)
    if state is None and leadership_state is None and us_spillover is None and not intl_markets:
        return None

    # Compact per-market list (market + mature flag)
    markets_compact = [
        {"market": m.get("market"), "mature": m.get("mature")}
        for m in intl_markets
        if isinstance(m, dict)
    ]

    block: dict = {
        "display_only": True,
        "is_context_only": True,
        "_tape_family": "contagion",
        "_lead_lag": "coincident",
        "as_of": asof,
        "stale": _is_stale(asof, "world_state"),
        "state": state,
        "origin_complex": origin_complex,
        "leadership_state": leadership_state,
        "us_spillover": us_spillover,
        "n_alert": n_alert,
        "d3_alert": d3_alert,
        "n_mature": n_mature,
        "intl_markets_in_alert": markets_compact,
        "honesty_note": (
            "accruing — unproven; does not change the score"
        ),
    }
    if degraded:
        block["degraded"] = degraded[:3]  # cap for budget

    return block


# ---------------------------------------------------------------------------
# macro_slice
# ---------------------------------------------------------------------------

# Drop order for budget enforcement: lowest-priority first
_MACRO_DROP_ORDER = [
    "causal_lab",        # 12
    "evidence_clock",    # 11
    "attention",         # 10
    "sequence",          # 9
    "strength",          # 8b
    "themes",            # 8
    "covariance",        # 7
    "factor_weather",    # 6
    "cross_asset_flows", # 3
    "liquidity_plumbing",# 4
    "contradictions",    # 2
    "global_regimes",    # 5
    "contagion",         # 1c — CSP-W1 context block
    "market_core",       # 1 — last resort
]

_CHINA_DROP_ORDER = [
    "evidence_morning_line",
    "contradictions",
    "themes_china",
    "global_weather",
]


def macro_slice(root: Path | None = None) -> dict:
    """Return the NW context packet for the macro brief.

    Never raises.  On any error returns a minimal dict with absent markers.
    Serialised size is enforced ≤ 10 240 bytes by dropping lowest-priority
    blocks in the documented order.
    """
    try:
        from engine import config as _config
        _root = Path(root) if root else _config.ROOT
    except Exception:  # noqa: BLE001
        _root = Path(root) if root else Path(__file__).parent.parent.parent

    try:
        return _build_macro_slice(_root)
    except Exception as exc:  # noqa: BLE001
        log.exception("brief_context.macro_slice: unexpected error: %s", exc)
        return {
            "absent": True,
            "reason": f"macro_slice failed: {exc}",
            "display_only": True,
        }


def _build_macro_slice(root: Path) -> dict:
    nw = root / "data" / "neuralweb"

    # Read all source artifacts (each read is individually fail-open)
    ws       = _read_json(nw / "world_state.json")
    lp_data  = _read_json(nw / "liquidity_plumbing.json")
    cv_data  = _read_json(nw / "covariance_spine.json")
    ts_data  = _read_json(nw / "theme_state.json")
    cs_data  = _read_json(nw / "confluence_sequence.json")
    cst_data = _read_json(nw / "confluence_strength.json")
    ad_data  = _read_json(nw / "attention_deterministic.json")
    ec_data  = _read_json(nw / "evidence_clock.json")
    cl_data  = _read_json(nw / "causal_lab_state.json")
    memo     = _read_json(nw / "cortex" / "memo.json")
    # mastermind_context only as fallback for global_regimes
    mc       = _read_json(nw / "mastermind_context.json")

    # World-state top-level asof
    ws_asof = (ws or {}).get("produced_at") or (ws or {}).get("as_of")

    result: dict[str, Any] = {}

    result["market_core"]       = _block_market_core(ws, ws_asof)
    result["contradictions"]    = _block_contradictions(ws, ws_asof)
    result["cross_asset_flows"] = _block_cross_asset_flows(ws)
    result["liquidity_plumbing"]= _block_liquidity_plumbing(lp_data)
    result["global_regimes"]    = _block_global_regimes(ws, mc, ws_asof)
    result["factor_weather"]    = _block_factor_weather(ws)
    result["covariance"]        = _block_covariance(cv_data)
    result["themes"]            = _block_themes(ts_data)
    result["sequence"]          = _block_sequence(cs_data)
    result["strength"]          = _block_strength(cst_data)
    result["attention"]         = _block_attention(ad_data)
    result["evidence_clock"]    = _block_evidence_clock(ec_data)
    result["causal_lab"]        = _block_causal_lab(cl_data)
    result["cortex"]            = _block_cortex(memo)
    # CSP-W1 contagion block — None when fully null/degraded, drops cleanly
    _contagion = _block_contagion(ws)
    if _contagion is not None:
        result["contagion"]     = _contagion

    # Enforce budget
    _enforce_budget(result, _MACRO_CAP, _MACRO_DROP_ORDER)

    return result


# ---------------------------------------------------------------------------
# china_slice
# ---------------------------------------------------------------------------

def china_slice(root: Path | None = None) -> dict:
    """Return the NW context packet for the China/HK brief.

    Never raises.  Serialised size enforced ≤ 6 144 bytes.
    """
    try:
        from engine import config as _config
        _root = Path(root) if root else _config.ROOT
    except Exception:  # noqa: BLE001
        _root = Path(root) if root else Path(__file__).parent.parent.parent

    try:
        return _build_china_slice(_root)
    except Exception as exc:  # noqa: BLE001
        log.exception("brief_context.china_slice: unexpected error: %s", exc)
        return {
            "absent": True,
            "reason": f"china_slice failed: {exc}",
            "display_only": True,
        }


def _build_china_slice(root: Path) -> dict:
    nw = root / "data" / "neuralweb"

    ws      = _read_json(nw / "world_state.json")
    mc      = _read_json(nw / "mastermind_context.json")
    ts_data = _read_json(nw / "theme_state.json")
    ec_data = _read_json(nw / "evidence_clock.json")
    memo    = _read_json(nw / "cortex" / "memo.json")

    ws_asof = (ws or {}).get("produced_at") or (ws or {}).get("as_of")

    result: dict[str, Any] = {}

    # Block 1: global_weather — china/hk quads + policy from mastermind_context
    # Prefer mastermind_context lobes.macro_weather for china-specific enrichment
    mw: dict = {}
    if mc is not None:
        mw = (mc.get("lobes") or {}).get("macro_weather") or {}

    china_entry = mw.get("china") or {}
    hk_entry    = mw.get("hk") or {}
    mw_asof     = mw.get("asof") or ws_asof

    # Build global_weather — china/hk focus
    if mw or ws:
        gr = (ws or {}).get("global_regimes") or {}
        china_gr = gr.get("china") or {}
        hk_gr    = gr.get("hk") or {}
        result["global_weather"] = {
            "display_only": True,
            "_tape_family": "price_regime",
            "_lead_lag": "coincident",
            "as_of": mw_asof,
            "stale": _is_stale(mw_asof, "mastermind_context"),
            "china_quad": mw.get("china_quad") or china_gr.get("quad"),
            "china_phase_label": china_entry.get("china_quad") or china_entry.get("phase_label"),
            "china_who_controls": china_entry.get("who_controls"),
            "china_policy_impulse": china_entry.get("policy_impulse"),
            "hk_quad": mw.get("hk_quad") or hk_gr.get("quad"),
            "hk_risk_state": hk_gr.get("risk_state"),
            "us_quad": mw.get("us_quad") or (ws or {}).get("regime", {}).get("quad"),
        }
    else:
        result["global_weather"] = _absent("neither mastermind_context nor world_state readable")

    # Block 2: themes_china — all themes (china filtering is expensive; include all with stage)
    if ts_data is not None:
        data_asof = ts_data.get("as_of")
        themes = ts_data.get("themes") or []
        stage_counts: dict[str, int] = {}
        for t in themes:
            fc = t.get("foresight") or {}
            stage = fc.get("stage", "unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        result["themes_china"] = {
            "display_only": True,
            "_tape_family": "nw_synthesis",
            "_lead_lag": "coincident",
            "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
            "as_of": data_asof,
            "stale": _is_stale(data_asof, "theme_state"),
            "n_themes": ts_data.get("n_themes", len(themes)),
            "stage_counts": stage_counts,
            "note": "stage_counts across all tracked themes (china filtering omitted for budget)",
        }
    else:
        result["themes_china"] = _absent("theme_state.json unreadable")

    # Block 3: contradictions (compact)
    if ws is not None:
        contra = ws.get("contradictions") or {}
        result["contradictions"] = {
            "display_only": True,
            "_tape_family": "nw_synthesis",
            "_lead_lag": "coincident",
            "tape_note": _NW_SYNTHESIS_TAPE_NOTE,
            "as_of": ws_asof,
            "stale": _is_stale(ws_asof, "world_state"),
            "n": contra.get("n", 0),
            "by_severity": contra.get("by_severity") or {},
        }
    else:
        result["contradictions"] = _absent("world_state.json unreadable")

    # Block 4: cortex tail
    result["cortex"] = _block_cortex(memo)

    # Block 5: evidence_morning_line (compact)
    if ec_data is not None:
        summary = ec_data.get("summary") or {}
        data_asof = ec_data.get("as_of")
        result["evidence_morning_line"] = {
            "display_only": True,
            "_tape_family": "ops",
            "_lead_lag": "n/a",
            "as_of": data_asof,
            "stale": _is_stale(data_asof, "evidence_clock"),
            "morning_line": summary.get("morning_line"),
        }
    else:
        result["evidence_morning_line"] = _absent("evidence_clock.json unreadable")

    # Enforce budget
    _enforce_budget(result, _CHINA_CAP, _CHINA_DROP_ORDER)

    return result
