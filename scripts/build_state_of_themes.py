"""scripts/build_state_of_themes.py — TIL W4 State of Themes renderer.

Reads the four site/neuralwebdata theme artifacts (tolerant: missing artifact
→ honest empty-state, never crash) and renders templates/state_of_themes.html.j2
→ site/state_of_themes.html.

Also reads:
  data/neuralweb/theme_phase_history.jsonl   — weekly-delta strip
  site/basketdata/options_witness.json        — crowding check drawer sections
  site/basketdata/clinical_pipeline.json      — clinical pipeline drawer sections
  site/basketdata/trade_flows.json            — import flows page note + drawer sections
All basketdata artifacts are tolerant: missing/corrupt → sections silently absent,
never crash.

Called from scripts/build_site.py after the build_thematic_state step.

Usage:
    python -m scripts.build_state_of_themes [--root /path/to/repo]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import jinja2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("build_state_of_themes")

# ---------------------------------------------------------------------------
# Leg ordering and labels
# ---------------------------------------------------------------------------

_LEG_ORDER = [
    "bottleneck_tightness",
    "stale_consensus_gap",
    "cyclical_dislocation",
    "entry_cleanliness",
    "crowding_hazard",
    "falsifier_clarity",
    "orthogonality",
]

_LEG_LABELS = {
    "bottleneck_tightness": ("btl", "Supply bottleneck tightness", "供应瓶颈紧张度"),
    "stale_consensus_gap": ("gap", "Stale consensus gap", "共识差距"),
    "cyclical_dislocation": ("dis", "Cyclical dislocation", "周期错位"),
    "entry_cleanliness": ("cln", "Entry cleanliness", "入场质量"),
    "crowding_hazard": ("crw", "Crowding hazard", "拥挤风险"),
    "falsifier_clarity": ("fal", "Falsifier clarity", "假证伪清晰度"),
    "orthogonality": ("ort", "Orthogonality vs market", "市场正交性"),
}

# ---------------------------------------------------------------------------
# Options-witness band → plain-word maps
# ---------------------------------------------------------------------------

# Leg A (call-OI HHI concentration): normal/rising/elevated or None
# Leg B (PCR): normal/declining/complacency/elevated_put or None
# Leg C (IV premium): normal/rising/elevated/compressed or None
# Worst-band ranking for section-level stance (higher = more concern):
_OW_BAND_SEVERITY = {
    "elevated": 3,
    "elevated_put": 2,
    "complacency": 3,    # low put protection = fragile = hazard
    "rising": 2,
    "declining": 1,
    "compressed": 1,
    "normal": 0,
    None: -1,
}

# Leg A (HHI): plain state words
_OW_LEG_A_BAND_EN = {
    "elevated": "crowding sign — don't chase",
    "rising": "concentration building — be alert",
    "normal": "normal — no crowding sign",
    None: "no read yet (accruing)",
}
_OW_LEG_A_BAND_ZH = {
    "elevated": "有拥挤迹象——勿追高",
    "rising": "集中度上升——保持警惕",
    "normal": "正常——无拥挤迹象",
    None: "暂无读数（累积中）",
}

# Leg B (PCR): pcr_collapse_into_strength triggers hazard regardless of band
_OW_LEG_B_BAND_EN = {
    "elevated_put": "heavy hedging",
    "normal": "hedging normal",
    "declining": "hedges coming off — watch for complacency",
    "complacency": "crowding sign — don't chase",
    None: "no read yet (accruing)",
}
_OW_LEG_B_BAND_ZH = {
    "elevated_put": "对冲力度大",
    "normal": "对冲正常",
    "declining": "对冲减少——警惕自满",
    "complacency": "有拥挤迹象——勿追高",
    None: "暂无读数（累积中）",
}

# Leg C (IV premium): plain state words
_OW_LEG_C_BAND_EN = {
    "elevated": "crowding sign — don't chase",
    "rising": "options getting pricier — be alert",
    "compressed": "options priced cheap",
    "normal": "normal — no crowding sign",
    None: "no read yet (accruing)",
}
_OW_LEG_C_BAND_ZH = {
    "elevated": "有拥挤迹象——勿追高",
    "rising": "期权趋贵——保持警惕",
    "compressed": "期权定价偏低",
    "normal": "正常——无拥挤迹象",
    None: "暂无读数（累积中）",
}


def _ow_leg_severity(band, pcr_collapse: bool = False) -> int:
    """Return severity rank for an options-witness band (higher = more concern)."""
    if pcr_collapse:
        return 3  # collapse into strength = crowding hazard regardless of band
    return _OW_BAND_SEVERITY.get(band, -1)


def _ow_leg_b_word_en(band, pcr_collapse: bool = False) -> str:
    if pcr_collapse:
        return "crowding sign — don't chase"
    return _OW_LEG_B_BAND_EN.get(band, "no read yet (accruing)")


def _ow_leg_b_word_zh(band, pcr_collapse: bool = False) -> str:
    if pcr_collapse:
        return "有拥挤迹象——勿追高"
    return _OW_LEG_B_BAND_ZH.get(band, "暂无读数（累积中）")


def _ow_worst_severity(leg_a: dict, leg_b: dict, leg_c: dict) -> int:
    a_sev = _ow_leg_severity(leg_a.get("band") if leg_a else None)
    b_sev = _ow_leg_severity(
        leg_b.get("band") if leg_b else None,
        bool(leg_b.get("pcr_collapse_into_strength")) if leg_b else False,
    )
    c_sev = _ow_leg_severity(leg_c.get("band") if leg_c else None)
    return max(a_sev, b_sev, c_sev)


# ---------------------------------------------------------------------------
# Clinical-pipeline velocity_read map
# ---------------------------------------------------------------------------

_CP_VELOCITY_EN = {
    "accelerating": "picking up",
    "decelerating": "slowing",
    "neutral": "steady",
}
_CP_VELOCITY_ZH = {
    "accelerating": "加快",
    "decelerating": "放缓",
    "neutral": "平稳",
}


def _cp_velocity_word_en(velocity_read: str | None) -> str:
    return _CP_VELOCITY_EN.get(velocity_read or "", "steady")


def _cp_velocity_word_zh(velocity_read: str | None) -> str:
    return _CP_VELOCITY_ZH.get(velocity_read or "", "平稳")


# ---------------------------------------------------------------------------
# Trade-flows confirmation map
# ---------------------------------------------------------------------------

_TF_CONFIRMATION_EN = {
    "confirms": "imports confirm the demand story",
    "contradicts": "imports cut against the story",
    "neutral": "no clear read",
    "mixed_direction": "mixed picture across product lines",
}
_TF_CONFIRMATION_ZH = {
    "confirms": "进口数据印证需求",
    "contradicts": "进口数据与论点相悖",
    "neutral": "无明确读数",
    "mixed_direction": "各产品线方向不一",
}


def _tf_confirmation_word_en(confirmation: str | None) -> str:
    return _TF_CONFIRMATION_EN.get(confirmation or "", "no clear read")


def _tf_confirmation_word_zh(confirmation: str | None) -> str:
    return _TF_CONFIRMATION_ZH.get(confirmation or "", "无明确读数")


# ---------------------------------------------------------------------------
# Asymmetry leg band → plain-word map (for drawer "Setup legs" section)
# ---------------------------------------------------------------------------

_ASYM_BAND_EN = {
    "low": "favorable",
    "med": "middling",
    "high": "caution",
    None: "no data yet",
    "null": "no data yet",
}
_ASYM_BAND_ZH = {
    "low": "有利",
    "med": "中等",
    "high": "谨慎",
    None: "暂无数据",
    "null": "暂无数据",
}


# Stage sort order for column sort (higher = more actionable)
_STAGE_SORT = {
    "WATCH": 1,
    "BROADENING": 3,
    "RE-RATING": 4,
    "PRECIPICE": 5,
    "ACCELERATING": 6,
    "CORRECTING": 2,
}

_STAGE_EN = {
    "WATCH": "Watch",
    "BROADENING": "Broadening",
    "RE-RATING": "Re-rating",
    "PRECIPICE": "Precipice",
    "ACCELERATING": "Accelerating",
    "CORRECTING": "Correcting",
}

_STAGE_ZH = {
    "WATCH": "观察中",
    "BROADENING": "扩张中",
    "RE-RATING": "重估值",
    "PRECIPICE": "临界点",
    "ACCELERATING": "加速中",
    "CORRECTING": "回调中",
}

_DIV_LABELS = {
    "hidden-opportunity": ("Hidden opportunity", "hidden-opportunity", "opp", "隐藏机会"),
    "crowded-and-fading": ("Crowded & fading", "crowded-and-fading", "crowd", "拥挤衰退"),
    "consensus-aligned": ("Consensus aligned", "consensus-aligned", "", "共识一致"),
    "diverging": ("Diverging", "diverging", "", "背离中"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list | None:
    """Load JSON from path; return None on any error."""
    try:
        if not path.exists():
            log.warning("artifact missing: %s", path)
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load %s: %s", path, exc)
        return None


def _load_jsonl(path: Path) -> list[dict]:
    """Load JSONL; return [] on any error."""
    try:
        if not path.exists():
            log.warning("jsonl missing: %s", path)
            return []
        lines = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw:
                try:
                    lines.append(json.loads(raw))
                except Exception:  # noqa: BLE001
                    pass
        return lines
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load %s: %s", path, exc)
        return []


def _strip_tier_suffix(stage: str | None) -> str:
    """'PRECIPICE (text)' → 'PRECIPICE'"""
    if not stage:
        return "WATCH"
    return re.sub(r"\s*\(.*?\)$", "", stage).strip()


def _band(val: float | None) -> str:
    """Numeric 0-1 → band string; None → 'null'"""
    if val is None:
        return "null"
    if val <= 0.33:
        return "low"
    if val <= 0.66:
        return "med"
    return "high"


# ---------------------------------------------------------------------------
# Filter chip computation
# ---------------------------------------------------------------------------

def _compute_filter_flags(legs: dict, falsifier_any_fired: bool) -> list[str]:
    """Return list of filter chip keys that apply to this theme."""
    flags: list[str] = []
    bt = legs.get("bottleneck_tightness", {})
    sg = legs.get("stale_consensus_gap", {})
    crw = legs.get("crowding_hazard", {})

    bt_band = bt.get("band") if isinstance(bt, dict) else _band(bt.get("value") if isinstance(bt, dict) else None)
    sg_band = sg.get("band") if isinstance(sg, dict) else None
    crw_band = crw.get("band") if isinstance(crw, dict) else None

    # secular_at_cyclical: high stale_consensus_gap + high or med bottleneck
    if sg_band == "high" and bt_band in ("high", "med"):
        flags.append("secular_at_cyclical")

    # bottleneck_tight: high bottleneck
    if bt_band == "high":
        flags.append("bottleneck_tight")

    # thesis_review: any falsifier fired
    if falsifier_any_fired:
        flags.append("thesis_review")

    # crowded: high crowding_hazard
    if crw_band == "high":
        flags.append("crowded")

    return flags


# ---------------------------------------------------------------------------
# Weekly delta from phase history
# ---------------------------------------------------------------------------

def _compute_weekly_delta(history: list[dict]) -> tuple[list[str], list[str]]:
    """Return (transitions, fired_falsifiers) string lists for this week."""
    if not history:
        return [], []

    one_week_ago = datetime.now(tz=timezone.utc) - timedelta(days=7)
    transitions: list[str] = []
    seen_transitions: set[str] = set()

    # Group by theme_id, find latest + prior records
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for rec in history:
        by_theme[rec.get("theme_id", "")].append(rec)

    for theme_id, recs in by_theme.items():
        recs = sorted(recs, key=lambda r: r.get("ts", ""))
        if len(recs) < 2:
            continue
        latest = recs[-1]
        prior = recs[-2]
        ts_str = latest.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts < one_week_ago:
            continue
        curr_stage = latest.get("foresight_stage", "")
        prev_stage = prior.get("foresight_stage", "")
        # Compare on the STRIPPED stage (drop the '(text)/(fingerprint)' evidence-tier
        # suffix) so an evidence-tier change that leaves the stage the same does not
        # surface a spurious 'PRECIPICE -> PRECIPICE' transition (post-review fix).
        curr_base = _strip_tier_suffix(curr_stage)
        prev_base = _strip_tier_suffix(prev_stage)
        if curr_base and prev_base and curr_base != prev_base:
            key = f"{theme_id}:{prev_base}→{curr_base}"
            if key not in seen_transitions:
                seen_transitions.add(key)
                label = (
                    f"{theme_id.replace('_', ' ').title()}: "
                    f"{_strip_tier_suffix(prev_stage)} → {_strip_tier_suffix(curr_stage)}"
                )
                transitions.append(label)

    return transitions, []


# ---------------------------------------------------------------------------
# Pathway builder (compact linear flow from nodes/edges)
# ---------------------------------------------------------------------------

def _build_pathway_nodes(pathway: dict | None) -> list[dict]:
    """Extract a compact linear node sequence from theme_pathways entry."""
    if not pathway:
        return []
    nodes_raw = pathway.get("nodes", [])
    edges_raw = pathway.get("edges", [])

    # node_type → CSS class
    _css = {
        "enabling_infrastructure": "driver",
        "bottleneck": "bottleneck",
        "direct_beneficiary": "winner",
        "derivative_beneficiary": "winner",
        "avoid": "avoid",
        "risk": "avoid",
        "macro_driver": "driver",
        "demand_driver": "driver",
    }

    node_map: dict[str, dict] = {n["id"]: n for n in nodes_raw}

    # Build a simple ordered path: driver → bottleneck → winners; limit to 5 nodes
    ordered_ids: list[str] = []
    seen: set[str] = set()

    # Start from driver-type nodes
    for n in nodes_raw:
        if n.get("node_type") in ("enabling_infrastructure", "macro_driver", "demand_driver"):
            if n["id"] not in seen:
                ordered_ids.append(n["id"])
                seen.add(n["id"])

    # Follow edges once
    for e in sorted(edges_raw, key=lambda x: x.get("order", 99)):
        src, dst = e.get("src"), e.get("dst")
        if src in seen and dst and dst not in seen:
            ordered_ids.append(dst)
            seen.add(dst)
        if len(ordered_ids) >= 5:
            break

    # Add avoid nodes last (if any, up to 1)
    for n in nodes_raw:
        if n.get("node_type") == "avoid" and n["id"] not in seen:
            ordered_ids.append(n["id"])
            seen.add(n["id"])
            break

    result = []
    for nid in ordered_ids[:6]:
        n = node_map.get(nid, {})
        ntype = n.get("node_type", "")
        result.append({
            "label_en": n.get("label_en", nid),
            "label_zh": n.get("label_zh", ""),
            "css": _css.get(ntype, ""),
        })
    return result


# ---------------------------------------------------------------------------
# Collision footnote
# ---------------------------------------------------------------------------

def _build_collision_note(pathways_data: dict | None) -> tuple[str, str]:
    """Return (note_en, note_zh) collision footnote."""
    if not pathways_data:
        return "", ""
    cc = pathways_data.get("cross_theme_collision_map", {})
    note_en = cc.get("note_en", "")
    note_zh = cc.get("note_zh", "")
    collisions = cc.get("collisions", [])
    # show top 3 heaviest cross-theme tickers
    top = sorted(collisions, key=lambda c: c.get("n_themes", 0), reverse=True)[:3]
    if top:
        ticker_parts = [
            f"{c['ticker']} ({c['n_themes']} themes)"
            for c in top
        ]
        note_en = (note_en + " " if note_en else "") + "Most cross-theme tickers: " + ", ".join(ticker_parts) + "."
        ticker_zh = [
            f"{c['ticker']}（{c['n_themes']}主题）"
            for c in top
        ]
        note_zh = (note_zh + " " if note_zh else "") + "跨主题最多股票：" + "、".join(ticker_zh) + "。"
    return note_en.strip(), note_zh.strip()


# ---------------------------------------------------------------------------
# Main composition
# ---------------------------------------------------------------------------

def compose(root: Path) -> dict[str, Any]:
    """Build template context from live artifacts. Never raises."""
    nwd = root / "site" / "neuralwebdata"
    data_nw = root / "data" / "neuralweb"
    bkd = root / "site" / "basketdata"

    state = _load_json(nwd / "theme_state.json")
    thesis = _load_json(nwd / "theme_thesis.json")
    asymmetry = _load_json(nwd / "theme_asymmetry.json")
    pathways_data = _load_json(nwd / "theme_pathways.json")
    history = _load_jsonl(data_nw / "theme_phase_history.jsonl")

    # ── Basketdata artifacts (tolerant — absent/corrupt → sections silently absent) ──
    options_witness = _load_json(bkd / "options_witness.json")
    clinical_pipeline = _load_json(bkd / "clinical_pipeline.json")
    trade_flows = _load_json(bkd / "trade_flows.json")

    # ── Build options-witness index by theme_id ──
    ow_by_id: dict[str, dict] = {}
    if options_witness and isinstance(options_witness.get("themes"), dict):
        ow_by_id = options_witness["themes"]
    _ow_as_of = (options_witness or {}).get("as_of", "")
    _ow_cov_stats = (options_witness or {}).get("coverage_stats", {})

    # ── Build clinical-pipeline index by theme_id ──
    cp_by_id: dict[str, dict] = {}
    if clinical_pipeline and isinstance(clinical_pipeline.get("themes"), dict):
        cp_by_id = clinical_pipeline["themes"]
    _cp_as_of = (clinical_pipeline or {}).get("as_of", "")

    # ── Trade-flows: check if any theme has data ──
    _tf_themes_with_data = 0
    tf_by_id: dict[str, dict] = {}
    if trade_flows:
        _cs = trade_flows.get("coverage_stats", {})
        _tf_themes_with_data = _cs.get("themes_with_data", 0)
        if isinstance(trade_flows.get("themes"), dict):
            tf_by_id = trade_flows["themes"]
    _tf_as_of = (trade_flows or {}).get("as_of", "")

    # ── Trade-flows page-level accrual note (shown once when all-null) ──
    trade_flows_page_note_en = ""
    trade_flows_page_note_zh = ""
    if trade_flows is not None and _tf_themes_with_data == 0:
        trade_flows_page_note_en = (
            "Customs import-flow checks are being set up — no data has arrived yet. "
            "Per-theme import reads will appear here once the feed activates."
        )
        trade_flows_page_note_zh = (
            "海关进口流量核对正在接入中——数据尚未到达。"
            "数据接通后，各主题的进口读数将显示在此。"
        )

    # ── Build thesis index by theme_id ──
    thesis_by_id: dict[str, dict] = {}
    if thesis and isinstance(thesis.get("theses"), list):
        for t in thesis["theses"]:
            tid = t.get("theme_id")
            if tid:
                thesis_by_id[tid] = t

    # ── Build asymmetry index by theme_id ──
    asym_by_id: dict[str, dict] = {}
    if asymmetry and isinstance(asymmetry.get("themes"), list):
        for t in asymmetry["themes"]:
            tid = t.get("theme_id")
            if tid:
                asym_by_id[tid] = t

    # ── Build pathway index by theme_id ──
    pathway_by_id: dict[str, dict] = {}
    if pathways_data and isinstance(pathways_data.get("theme_pathways"), list):
        for p in pathways_data["theme_pathways"]:
            tid = p.get("theme_id")
            if tid:
                pathway_by_id[tid] = p

    # ── Header counts ──
    n_themes = 0
    n_falsifier_fired = 0
    n_stale_legs = 0
    as_of = "—"

    if state:
        n_themes = state.get("n_themes", 0)
        as_of = state.get("as_of", "—")
        n_stale_legs = len(state.get("stale_legs", []))
    if thesis:
        n_falsifier_fired = thesis.get("n_falsifier_fired", 0)

    # ── Filter chip counts ──
    chip_secular_at_cyclical = 0
    chip_bottleneck_tight = 0
    chip_thesis_review = 0
    chip_crowded = 0

    state_themes = (state or {}).get("themes", [])
    for st_th in state_themes:
        tid = st_th.get("theme_id", "")
        asym_th = asym_by_id.get(tid, {})
        legs = asym_th.get("legs", {})
        th_data = thesis_by_id.get(tid, {})
        any_fired = (th_data.get("falsifier_summary", {}) or {}).get("any_fired", False)
        flags = _compute_filter_flags(legs, any_fired)
        if "secular_at_cyclical" in flags:
            chip_secular_at_cyclical += 1
        if "bottleneck_tight" in flags:
            chip_bottleneck_tight += 1
        if "thesis_review" in flags:
            chip_thesis_review += 1
        if "crowded" in flags:
            chip_crowded += 1

    # ── Build theme rows ──
    themes = []
    for st_th in state_themes:
        tid = st_th.get("theme_id", "")
        asym_th = asym_by_id.get(tid, {})
        th_data = thesis_by_id.get(tid, {})
        pathway = pathway_by_id.get(tid)

        # Stage
        foresight = st_th.get("foresight", {}) or {}
        stage_raw = foresight.get("stage", "WATCH")
        stage_key = _strip_tier_suffix(stage_raw)
        stage_label_en = _STAGE_EN.get(stage_key, stage_key.title())
        stage_label_zh = _STAGE_ZH.get(stage_key, stage_key)
        stage_sort = _STAGE_SORT.get(stage_key, 0)

        # Legs
        raw_legs = asym_th.get("legs", {})
        legs_ordered = []
        for leg_id in _LEG_ORDER:
            leg_data = raw_legs.get(leg_id, {})
            if isinstance(leg_data, dict):
                band = leg_data.get("band") or "null"
                note_en = leg_data.get("note_en", "")
                note_zh = leg_data.get("note_zh", "")
            else:
                band = "null"
                note_en = ""
                note_zh = ""
            lbl = _LEG_LABELS.get(leg_id)
            abbr = lbl[0] if lbl else leg_id[:3]
            tip_en = f"{lbl[1] if lbl else leg_id} ({band}): {note_en[:120]}" if note_en else f"{lbl[1] if lbl else leg_id}: {band}"
            tip_zh = f"{lbl[2] if lbl else leg_id} ({band}): {note_zh[:120]}" if note_zh else tip_en
            legs_ordered.append({
                "id": leg_id,
                "abbr": abbr,
                "band": band,
                "tip_en": tip_en,
                "tip_zh": tip_zh,
            })

        # Falsifiers
        fals_summary = (th_data.get("falsifier_summary", {}) or {})
        any_fired = fals_summary.get("any_fired", False)
        n_fired = fals_summary.get("n_fired", 0)
        n_armed = fals_summary.get("n_armed", 0)
        n_total = n_fired + n_armed + fals_summary.get("n_qualitative", 0) + fals_summary.get("n_data_missing", 0)
        if n_total > 0:
            falsifier_label = f"{n_fired}/{n_total} fired"
        else:
            falsifier_label = ""
        falsifier_sort = n_fired * 10 + n_armed

        raw_falsifiers = th_data.get("falsifiers", []) or []
        falsifiers = []
        for f in raw_falsifiers[:8]:
            state_str = f.get("state", "qualitative")
            falsifiers.append({
                "state": state_str,
                "rule_en": (f.get("rule_en") or "").strip(),
                "rule_zh": (f.get("rule_zh") or "").strip(),
            })

        # Divergence
        div_board = st_th.get("divergence_board", {}) or {}
        quadrant = div_board.get("quadrant")
        div_info = _DIV_LABELS.get(quadrant, (quadrant or "—", quadrant, "", quadrant or "—"))
        div_label_en = div_info[0] if div_info else "—"
        div_label_zh = div_info[3] if len(div_info) > 3 else div_label_en
        div_class = div_info[2] if len(div_info) > 2 else ""
        divergence_val = div_board.get("divergence")
        divergence_sort = divergence_val if divergence_val is not None else 0.0

        # Filter flags
        raw_legs_for_filter = asym_th.get("legs", {})
        filter_flags = _compute_filter_flags(raw_legs_for_filter, any_fired)

        # Pathway nodes
        pathway_nodes = _build_pathway_nodes(pathway)

        # Thesis text
        variant_perception_en = (th_data.get("variant_perception_en") or "").strip()
        variant_perception_zh = (th_data.get("variant_perception_zh") or "").strip()
        mechanism_en = (th_data.get("mechanism_en") or "").strip()
        mechanism_zh = (th_data.get("mechanism_zh") or "").strip()
        evidence_refs = th_data.get("evidence_refs", []) or []

        # ── Asymmetry "Setup legs" drawer section ──
        # Re-uses the same legs_ordered already computed above but maps band → plain word.
        asym_legs_section: list[dict] = []
        for leg_id in _LEG_ORDER:
            leg_data = raw_legs.get(leg_id, {})
            if isinstance(leg_data, dict):
                band = leg_data.get("band") or "null"
                note_en = leg_data.get("note_en", "")
                note_zh = leg_data.get("note_zh", "")
            else:
                band = "null"
                note_en = ""
                note_zh = ""
            lbl = _LEG_LABELS.get(leg_id)
            plain_en = _ASYM_BAND_EN.get(band, "no data yet")
            plain_zh = _ASYM_BAND_ZH.get(band, "暂无数据")
            asym_legs_section.append({
                "id": leg_id,
                "name_en": lbl[1] if lbl else leg_id,
                "name_zh": lbl[2] if lbl else leg_id,
                "band": band,
                "word_en": plain_en,
                "word_zh": plain_zh,
                "note_en": note_en,
                "note_zh": note_zh,
            })

        # ── Options-witness crowding check drawer section ──
        ow_th = ow_by_id.get(tid)
        ow_section: dict = {}
        if ow_th is not None:
            la = ow_th.get("leg_a_call_oi_hhi") or {}
            lb = ow_th.get("leg_b_pcr") or {}
            lc = ow_th.get("leg_c_iv_premium") or {}

            def _ow_suppressed(leg: dict) -> bool:
                """True when band is None (suppressed or absent)."""
                return leg.get("band") is None

            la_stale = bool(la.get("stale"))
            lb_stale = bool(lb.get("stale"))
            lc_stale = bool(lc.get("stale"))
            pcr_collapse = bool(lb.get("pcr_collapse_into_strength"))

            # Leg-A state word
            la_band = None if (_ow_suppressed(la) or la_stale) else la.get("band")
            la_word_en = _OW_LEG_A_BAND_EN.get(la_band, "no read yet (accruing)")
            la_word_zh = _OW_LEG_A_BAND_ZH.get(la_band, "暂无读数（累积中）")

            # Leg-B state word (pcr_collapse overrides)
            lb_band = None if (_ow_suppressed(lb) or lb_stale) else lb.get("band")
            lb_word_en = _ow_leg_b_word_en(lb_band, pcr_collapse and not lb_stale)
            lb_word_zh = _ow_leg_b_word_zh(lb_band, pcr_collapse and not lb_stale)

            # Leg-C state word
            lc_band = None if (_ow_suppressed(lc) or lc_stale) else lc.get("band")
            lc_word_en = _OW_LEG_C_BAND_EN.get(lc_band, "no read yet (accruing)")
            lc_word_zh = _OW_LEG_C_BAND_ZH.get(lc_band, "暂无读数（累积中）")

            # Section-level stance: worst severity across three legs
            worst = max(
                _ow_leg_severity(la_band),
                _ow_leg_severity(lb_band, pcr_collapse and not lb_stale),
                _ow_leg_severity(lc_band),
            )
            if worst >= 3:
                stance_en = "Crowding signs building — be choosy, don't chase."
                stance_zh = "拥挤迹象增加——精选入场，勿追高。"
            elif worst >= 2:
                stance_en = "Some concentration building — monitor before adding."
                stance_zh = "集中度上升——加仓前保持观察。"
            elif worst >= 1:
                stance_en = "Minor signals — nothing urgent."
                stance_zh = "轻微信号——无紧迫情况。"
            elif worst == 0:
                stance_en = "No crowding signs in the options tape."
                stance_zh = "期权盘面无拥挤迹象。"
            else:
                # All legs null/suppressed
                stance_en = "Not enough option coverage to read crowding."
                stance_zh = "期权覆盖不足，无法读取拥挤度。"

            # Coverage count strings for h4 hover tip
            la_cov = f"{la.get('coverage_count','?')}/{la.get('coverage_total','?')}" if la else "—"
            lb_cov = f"{lb.get('coverage_count','?')}/{lb.get('coverage_total','?')}" if lb else "—"
            lc_cov = f"{lc.get('coverage_count','?')}/{lc.get('coverage_total','?')}" if lc else "—"
            ow_h4_tip_en = (
                f"Options crowding check — context only, not a signal. "
                f"as_of: {_ow_as_of}; "
                f"leg-A coverage {la_cov}, leg-B coverage {lb_cov}, leg-C coverage {lc_cov}."
            )
            ow_h4_tip_zh = (
                f"期权拥挤度检查——仅供参考，非信号。"
                f"截止日期：{_ow_as_of}；"
                f"腿A覆盖{la_cov}，腿B覆盖{lb_cov}，腿C覆盖{lc_cov}。"
            )

            covered = not (
                _ow_suppressed(la) and _ow_suppressed(lb) and _ow_suppressed(lc)
            )

            ow_section = {
                "available": True,
                "covered": covered,
                "stance_en": stance_en,
                "stance_zh": stance_zh,
                "h4_tip_en": ow_h4_tip_en,
                "h4_tip_zh": ow_h4_tip_zh,
                "leg_a": {
                    "word_en": la_word_en,
                    "word_zh": la_word_zh,
                    "note_en": la.get("note_en", ""),
                    "note_zh": la.get("note_zh", ""),
                },
                "leg_b": {
                    "word_en": lb_word_en,
                    "word_zh": lb_word_zh,
                    "note_en": lb.get("note_en", ""),
                    "note_zh": lb.get("note_zh", ""),
                },
                "leg_c": {
                    "word_en": lc_word_en,
                    "word_zh": lc_word_zh,
                    "note_en": lc.get("note_en", ""),
                    "note_zh": lc.get("note_zh", ""),
                },
            }

        # ── Clinical-pipeline drawer section ──
        cp_th = cp_by_id.get(tid)
        cp_section: dict = {}
        if cp_th is not None and (cp_th.get("n_studies_total") or 0) > 0:
            yoy = cp_th.get("theme_registration_yoy_pct")
            vel = cp_th.get("theme_registration_velocity_read")
            n_phase3 = cp_th.get("n_phase3_trailing12m", 0)

            if yoy is not None:
                sign = "+" if yoy >= 0 else ""
                yoy_str_en = f"{sign}{yoy:.0f}% vs a year ago"
                yoy_str_zh = f"同比{sign}{yoy:.0f}%"
            else:
                yoy_str_en = ""
                yoy_str_zh = ""

            vel_en = _cp_velocity_word_en(vel)
            vel_zh = _cp_velocity_word_zh(vel)

            if yoy_str_en and n_phase3 is not None:
                line1_en = (
                    f"Drug-trial registrations {vel_en}: {yoy_str_en}; "
                    f"{n_phase3} late-stage (Phase-3) trials started in the past 12 months."
                )
                line1_zh = (
                    f"药物试验注册{vel_zh}：{yoy_str_zh}；"
                    f"过去12个月启动了{n_phase3}项晚期（III期）试验。"
                )
            elif yoy_str_en:
                line1_en = f"Drug-trial registrations {vel_en}: {yoy_str_en}."
                line1_zh = f"药物试验注册{vel_zh}：{yoy_str_zh}。"
            else:
                line1_en = "Drug-trial registration data accruing."
                line1_zh = "药物试验注册数据累积中。"

            cp_h4_tip_en = (
                "Context only — shows where research money is committing, not a buy signal. "
                f"Source: ClinicalTrials.gov v2 (keyless, INDUSTRY-sponsored only). as_of: {_cp_as_of}. "
                + (cp_th.get("coverage_note") or "")
            )
            cp_h4_tip_zh = (
                "仅供参考——显示研究资金投向，非买入信号。"
                f"来源：ClinicalTrials.gov v2（无需密钥，仅行业赞助）。截止日期：{_cp_as_of}。"
                + (cp_th.get("coverage_note_zh") or "")
            )

            cp_section = {
                "available": True,
                "line1_en": line1_en,
                "line1_zh": line1_zh,
                "h4_tip_en": cp_h4_tip_en,
                "h4_tip_zh": cp_h4_tip_zh,
            }

        # ── Trade-flows drawer section (per-theme — only when data exists) ──
        tf_section: dict = {}
        if _tf_themes_with_data > 0:
            tf_th = tf_by_id.get(tid)
            if tf_th is not None and (tf_th.get("n_codes_with_data") or 0) > 0:
                yoy_pct = tf_th.get("yoy_pct")
                conf = tf_th.get("confirmation")
                conf_word_en = _tf_confirmation_word_en(conf)
                conf_word_zh = _tf_confirmation_word_zh(conf)
                if yoy_pct is not None:
                    sign = "+" if yoy_pct >= 0 else ""
                    yoy_en = f" ({sign}{yoy_pct:.0f}% vs a year ago)"
                    yoy_zh = f"（同比{sign}{yoy_pct:.0f}%）"
                else:
                    yoy_en = ""
                    yoy_zh = ""
                tf_cov_tip_en = (
                    "Import-flow check — context only. "
                    f"as_of: {_tf_as_of}. "
                    + (tf_th.get("coverage_note") or "")
                )
                tf_cov_tip_zh = (
                    "进口流量核对——仅供参考。"
                    f"截止日期：{_tf_as_of}。"
                    + (tf_th.get("coverage_note_zh") or "")
                )
                tf_section = {
                    "available": True,
                    "line_en": f"Import flows: {conf_word_en}{yoy_en}.",
                    "line_zh": f"进口流量：{conf_word_zh}{yoy_zh}。",
                    "h4_tip_en": tf_cov_tip_en,
                    "h4_tip_zh": tf_cov_tip_zh,
                }

        themes.append({
            "theme_id": tid,
            "name_en": st_th.get("name_en", tid),
            "name_zh": st_th.get("name_zh", ""),
            "stage_raw": stage_raw,
            "stage_key": stage_key,
            "stage_label_en": stage_label_en,
            "stage_label_zh": stage_label_zh,
            "stage_sort": stage_sort,
            "legs_ordered": legs_ordered,
            "falsifier_any_fired": any_fired,
            "falsifier_label": falsifier_label,
            "falsifier_sort": falsifier_sort,
            "falsifiers": falsifiers,
            "div_label_en": div_label_en,
            "div_label_zh": div_label_zh,
            "div_class": div_class,
            "divergence_sort": divergence_sort,
            "filter_flags": ",".join(filter_flags),
            "variant_perception_en": variant_perception_en,
            "variant_perception_zh": variant_perception_zh,
            "mechanism_en": mechanism_en,
            "mechanism_zh": mechanism_zh,
            "pathway_nodes": pathway_nodes,
            "evidence_refs": evidence_refs,
            # New drawer sections
            "asym_legs_section": asym_legs_section,
            "ow_section": ow_section,
            "cp_section": cp_section,
            "tf_section": tf_section,
        })

    # ── Weekly delta ──
    weekly_transitions, weekly_fired = _compute_weekly_delta(history)

    # ── Collision footnote ──
    collision_note_en, collision_note_zh = _build_collision_note(pathways_data)

    return {
        "as_of": as_of,
        "n_themes": n_themes,
        "n_falsifier_fired": n_falsifier_fired,
        "n_stale_legs": n_stale_legs,
        "chip_secular_at_cyclical": chip_secular_at_cyclical,
        "chip_bottleneck_tight": chip_bottleneck_tight,
        "chip_thesis_review": chip_thesis_review,
        "chip_crowded": chip_crowded,
        "themes": themes,
        "weekly_transitions": weekly_transitions,
        "weekly_fired": weekly_fired,
        "collision_note_en": collision_note_en,
        "collision_note_zh": collision_note_zh,
        # Trade-flows page-level note (shown once when all-null accrual state)
        "trade_flows_page_note_en": trade_flows_page_note_en,
        "trade_flows_page_note_zh": trade_flows_page_note_zh,
    }


def render(root: Path) -> str:
    """Render the template with live data. Returns HTML string."""
    templates_dir = root / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=True,
        undefined=jinja2.Undefined,
    )
    ctx = compose(root)
    tpl = env.get_template("state_of_themes.html.j2")
    return tpl.render(**ctx)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render state_of_themes.html")
    parser.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _REPO_ROOT
    out_path = root / "site" / "state_of_themes.html"

    try:
        html = render(root)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        log.info("wrote %s", out_path)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("render failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
