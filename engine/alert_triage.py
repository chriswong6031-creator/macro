"""Alert Command Center — the honest triage layer over every alert engine.

The dashboard already emits alerts from six engines (macro ``engine.alerts``,
``bonds_alerts``, ``forex_alerts``, ``btc_alerts``, ``commodity_alerts`` and the
per-stock ``ticker_alerts``).  Each screams on its own page with its own local
severity scale, so a forex per-pair momentum "high" looks as loud as a credit
blow-out.  This module is a *pure assembler* that pulls the recent cross-asset /
macro feeds into ONE ranked board and answers, per alert, the only questions a
PM actually asks:

  • how loud is it, really?  → a TRUE cross-asset conviction tier (act / watch /
    context), not each engine's local severity word;
  • how much should it grab my attention right now?  → a TRANSPARENT triage
    *priority* (0-100) blended from conviction + severity + recency + whether the
    cross-asset backdrop corroborates it.  This is a prioritiser, NOT a
    probability the call is right — the components are shown;
  • what is the measured edge?  → the ``edge`` note the engine already derived
    from its calibration, PLUS — only where a validated Signal-Lab row backs the
    alert family — the real hit-rate / Deflated-Sharpe / verdict, linked to
    signal_lab.html.  Where there is NO backtest we say so ("documented, not
    backtested") rather than invent a number;
  • what's the regime + event backdrop?  → the current quad / cycle and the next
    high-impact catalyst, shown as shared context.

Honesty rules baked in (this repo's culture):
  - we NEVER fabricate a per-alert hit-rate.  A number appears only when
    ``engine.signal_lab`` already validated that signal family.
  - "priority" is explicitly a triage prioritiser, never dressed up as P(correct).
  - regime "fit" is shown as context; we do not claim a measured
    regime-conditional edge the validation layer doesn't have.

Additive + graceful: every reader is wrapped so a missing feed degrades to an
empty section, never a failed build.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from lib import config

try:  # central logger if present, else a no-op
    from lib.logging import get_logger
    log = get_logger(__name__)
except Exception:  # noqa: BLE001
    import logging
    log = logging.getLogger(__name__)


# --- per-source conviction ----------------------------------------------------
# Bonds / forex / commodity events carry no inline conviction tier, so we assign
# the TRUE cross-asset importance per (source, type) here.  Macro and BTC bring
# their own (ALERT_CONVICTION / CONVICTION) and we reuse those verbatim.  This is
# what stops a forex per-pair flip from outranking a credit blow-out.
_BONDS_TIER = {
    "recession_risk": "act", "uninversion": "act", "credit_band": "act",
    "repo_stress": "act", "rates_vol": "watch", "curve_regime": "watch",
    "corr_regime": "watch",
}
# Forex/commodity are macro CONTEXT, not standalone sizers (Signal Lab: HK/forex
# is global-beta, commodity allocation fails DSR — only the risk_index confirms).
# So a per-pair FX decoupling or an intraday commodity shock is 'watch'/'context',
# never 'act' — that honesty is what keeps the board's top reserved for real
# cross-asset stress (credit, recession, BTC risk regime).
_FOREX_TIER = {
    "peg_approach": "watch", "cnh_basis": "watch", "risk_regime": "watch",
    "smile_regime": "watch", "residual_shock": "context", "carry_flip": "context",
    "momentum": "context", "structure": "context", "positioning": "context",
    "trend_flip": "context",
}
_COMMODITY_TIER = {
    "risk_regime": "watch", "risk_extreme": "watch", "residual_shock": "watch",
    "complex_regime": "watch", "price_shock": "watch", "driver_shift": "context",
    "trend_flip": "context", "momentum": "context", "structure": "context",
    "allocation": "context", "positioning": "context", "value": "context",
}
# Theme-rotation reads (engine.theme_alerts) are tactical CONTEXT — a thematic-basket
# rotation is never a standalone cross-asset sizer, so the loudest a topping/breakdown
# gets is 'watch'. leadership_rotation is debounced at the source (theme_alerts: held #1
# for 2 consecutive builds + >=3-point composite margin over rank-2), so one that fires
# is a persistent, decisive handoff — 'watch', not 'context'. Unbuffered it re-fired on
# every photo-finish rank wobble (6+ rotations in 6 sessions, China book 2026-06).
_THEMES_TIER = {
    "theme_topping": "watch", "theme_deteriorating": "watch",
    "theme_emerging": "watch", "reco_change": "watch",
    "leadership_rotation": "watch",
}
# Forming-narrative detections (engine.emergence_alerts) are a CONTEXT watchlist — a newly
# coherent group of names carries no validated forward edge, so it never rises above context.
_EMERGENCE_TIER = {"narrative_forming": "context"}
# Alternative-data convergence (engine.altdata_alerts) is an unusual-activity flag — a ticker
# lit by several independent political/insider/contract channels at once carries no validated
# forward edge yet, so the loudest it gets is 'watch'.
_ALTDATA_TIER = {"convergence": "watch"}
# Demand-variant divergences (engine.demand_alerts) are display-only / not a buy
# signal until the forward ledger earns a verdict → context tier only.
_DEMAND_TIER = {"demand_ahead": "context", "demand_at_risk": "context"}
# Subsector-rotation flips (engine.subsector_rotation_alerts) ride Finviz's broad
# numbers and carry no validated forward edge — a rotate-in is the loudest at
# 'watch'; a leader rolling over is 'context'.
_ROTATION_TIER = {"rotation_emerging": "watch", "rotation_fading": "context"}
# Oracle rotation engine (engine.oracle.alerts) — onset/confirmed descriptive detections.
# oracle_rollover and oracle_two_sided are high-severity at the source so they reach 'watch';
# onset/confirmed are display_with_edge (onset secondary survived FDR — DISPLAY-WITH-EDGE per R4)
# but are never promoted above 'watch' here.  oracle_regime breadth-aggregate crosses 'watch'.
_ORACLE_TIER = {
    "oracle_onset": "watch",
    "oracle_confirmed": "watch",
    "oracle_rollover": "watch",
    "oracle_two_sided": "watch",
    "oracle_regime": "watch",
}

# Source display metadata: label (EN/ZH), icon, and the page each alert deep-links to.
SOURCES = {
    "macro":     {"label": "Macro Vector",    "label_zh": "宏观向量",   "icon": "📊", "page": "macro.html"},
    "bonds":     {"label": "Bonds",           "label_zh": "债券",       "icon": "🏛️", "page": "bonds.html"},
    "forex":     {"label": "Forex",           "label_zh": "外汇",       "icon": "💱", "page": "forex.html"},
    "vector":    {"label": "Bitcoin Vector",  "label_zh": "比特币向量", "icon": "₿",  "page": "vector.html"},
    "commodity": {"label": "Commodity Vector","label_zh": "大宗商品",   "icon": "🛢", "page": "commodities.html"},
    "themes":    {"label": "Theme Rotation",  "label_zh": "主题轮动",   "icon": "🧺", "page": "baskets.html"},
    "emergence": {"label": "Forming Narratives","label_zh": "成形叙事", "icon": "🔥", "page": "baskets.html"},
    "altdata":   {"label": "Alternative Data",  "label_zh": "替代数据",   "icon": "📊", "page": "alt_data.html"},
    "demand":    {"label": "Demand Desk",      "label_zh": "需求台",     "icon": "🧭", "page": "demand.html"},
    "rotation":  {"label": "Subsector Rotation","label_zh": "子行业轮动", "icon": "🌀", "page": "subsector_rotation.html"},
    "oracle":    {"label": "Oracle Rotation",  "label_zh": "Oracle 轮动", "icon": "🔭", "page": "subsector_rotation.html"},
}

# Risk-OFF / stress alert families whose sign is unambiguous — only these get a
# cross-asset confirm/diverge tag (we refuse to guess direction on the rest).
_STRESS_TYPES = {
    "hy_oas_widening", "ebp_widening", "credit_band", "recession_risk",
    "repo_stress", "uninversion", "rates_vol", "flash_crash", "residual_shock",
    "risk_extreme", "drawdown_risk_high", "capitulation_signal",
}

# (source, type/rule) → exact Signal-Lab REGISTRY name.  ONLY families with a
# genuine validated backtest are listed; everything else gets the honest
# "documented, not backtested" verdict.  Numbers are pulled live from the row.
_VALIDATION_MAP = {
    ("bonds", "recession_risk"): "Recession-risk composite (jobless-claims folded in)",
    ("bonds", "credit_band"): "Bond-health drawdown gauge",
    ("bonds", "rates_vol"): "Bond-health drawdown gauge",
    ("macro", "transition_state_change"): "US macro regime quad (Goldilocks/Reflation/…)",
    ("macro", "gex_flip_cross"): "Index dealer-gamma regime (market GEX)",
    ("commodity", "risk_regime"): "Commodity risk index (gold/silver/copper/oil)",
    ("commodity", "risk_extreme"): "Commodity risk index (gold/silver/copper/oil)",
}

# (source, alert type/rule) → key in data/alerts/rule_scorecard.json — the DIRECT
# event-study backtest of the alert rule itself (scripts/alert_rules_phase0.py).
# net_liquidity_roc_flip resolves to expand/contract by parsing the detail line.
_RULE_MAP = {
    ("macro", "ebp_widening"): "ebp_widening",
    ("macro", "drawdown_risk_high"): "drawdown_risk_high",
    ("macro", "capitulation_signal"): "capitulation_signal",
    ("macro", "hy_oas_widening"): "hy_oas_widening",
    ("macro", "nfci_tightening"): "nfci_tightening",
    ("macro", "sahm_trigger"): "sahm_trigger",
    ("macro", "conditions_recession_state_change"): "recession_high",
}


def _rule_scorecard() -> dict:
    """Live read of the alert-rule event-study scorecard (committed artifact)."""
    try:
        p = config.data_dir() / "alerts" / "rule_scorecard.json"
        return (json.loads(p.read_text()).get("rules") or {}) if p.exists() else {}
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {}


def _rule_key(source: str, type_: str, detail: str) -> str | None:
    if source == "macro" and type_ == "net_liquidity_roc_flip":
        d = (detail or "").lower()
        if "expand" in d or "positive" in d:
            return "net_liq_expand"
        if "contract" in d or "negative" in d:
            return "net_liq_contract"
        return None
    return _RULE_MAP.get((source, type_))


# Priority weights (max 40+30+20+10 = 100).  Surfaced to the page so the score is
# auditable, never a black box.
W_TIER = {"act": 40, "watch": 22, "context": 8}
W_SEVERITY = {"critical": 30, "major": 18, "minor": 6}
W_CONFIRM = {"confirm": 10, "neutral": 0, "diverge": -6}


def _registry_index() -> dict:
    """{registry name → row} from engine.signal_lab, for honest hit/DSR lookup."""
    try:
        from engine.signal_lab import REGISTRY
        return {r["name"]: r for r in REGISTRY}
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {}


def severity_band(tier: str, raw_sev: str) -> str:
    """Collapse (true conviction tier, engine raw severity) → critical/major/minor.
    Tier-led on purpose: a context-tier 'high' is still minor on a macro board."""
    high = raw_sev in ("high", "act")
    if tier == "act":
        return "critical" if high else "major"
    if tier == "watch":
        return "major" if high else "minor"
    return "minor"


# Alert (source, type) → its severity governance. Two forms:
#   * ("spine", engine, family) — the band is bounded by that spine emitter's MEASURED IC.
#   * ("documented_null",)      — a DOCUMENTED near-zero-IC emitter with no spine of its own
#     yet (#42's exact case: narrative-rotation entered_book/left_book, rank-IC≈0 per
#     baskets_calibration). Its band is capped to 'minor' NOW — the honest prior — and it will
#     upgrade to spine-measured governance the moment a rotation spine emitter accrues n>0.
# Everything absent here is untouched (its hardcoded band stands).
_IC_GOVERNED = {
    ("rotation", "entered_book"): ("documented_null",),
    ("rotation", "left_book"):    ("documented_null",),
    ("rotation", "leadership_rotation"): ("documented_null",),
    ("altdata", "convergence"):   ("spine", "altdata_conv", "altdata:convergence"),
}
_BAND_RANK = {"minor": 0, "major": 1, "critical": 2}
_RANK_BAND = {v: k for k, v in _BAND_RANK.items()}
# The measured-IC severity policy (#42 durable form): the hardcoded per-event severity is a
# PRIOR that measured performance overrides — bounded. A validated positive edge (mean signed
# excess > 0 over a meaningful n) is allowed its hardcoded band; a measured-NULL or WRONG-SIGN
# emitter (or a documented-null one) is CAPPED to 'minor' so it can't crowd the board's top.
# Below MIN_N a SPINE-governed emitter is still cold — we neither promote nor demote (honest
# accrual). A documented-null emitter is capped regardless (its ~0 IC is already established).
_IC_MIN_N = 12
_IC_POS_THRESH = 0.0      # signed IC strictly > 0 to keep a promoted band


def _cap_to_minor(band: str) -> str:
    return _RANK_BAND[min(_BAND_RANK.get(band, 0), _BAND_RANK["minor"])]


def ic_severity_cap(source: str, type_: str, band: str, root=None) -> tuple[str, dict]:
    """Bound ``band`` by the emitter's measured / documented edge (#42). Returns (band, note).

    Policy:
      * not governed → band unchanged (hardcoded band stands);
      * documented-null emitter → band capped at 'minor' (its ~0 IC is established);
      * spine-governed + cold (n < _IC_MIN_N) → band unchanged (accruing prior);
      * spine-governed + measured IC ≤ 0 → band capped at 'minor' (null / wrong-sign);
      * spine-governed + measured IC > 0 → band unchanged (measured edge earns its band).

    Degrade-never-raise: any spine read failure returns the band unchanged."""
    gov = _IC_GOVERNED.get((source, type_))
    if not gov:
        return band, {}
    if gov[0] == "documented_null":
        capped = _cap_to_minor(band)
        return capped, {"ic_state": "documented_null", "capped_from": band,
                        "note": "documented rank-IC≈0 emitter — capped so it can't outrank "
                                "validated risk-off signals"}
    try:
        from engine import spine
        _, engine, family = gov
        m = spine.measured_ic(root=root, engine=engine, family=family)
    except Exception:  # noqa: BLE001 — additive, never fatal
        return band, {}
    n = int(m.get("n") or 0)
    ic = m.get("ic")
    if n < _IC_MIN_N or ic is None:
        return band, {"ic_state": "accruing", "ic_n": n}
    if ic <= _IC_POS_THRESH:
        return _cap_to_minor(band), {"ic_state": "null_or_wrong_sign", "ic": ic, "ic_n": n,
                                     "capped_from": band}
    return band, {"ic_state": "validated", "ic": ic, "ic_n": n}


def action_for(tier: str, band: str, ca_tag: str) -> tuple[str, str]:
    """The PM verb. Cross-asset disagreement downgrades an act/watch to
    'confirm first' — exactly the 'don't chase until it confirms' discipline."""
    if tier == "context":
        return ("context", "背景")
    if ca_tag == "diverge":
        return ("confirm first", "先确认")
    if tier == "act":
        return ("high-conviction", "高信念") if band == "critical" else ("reduce risk", "降低风险")
    return ("watch", "观察")


def cross_asset_tag(type_: str, ca_verdict: str | None) -> str:
    """For unambiguous stress alerts only: does the cross-asset backdrop corroborate?
    A CONCENTRATED (fragile one-bet) tape confirms stress; a DIVERSIFIED tape
    diverges from it. Everything else (and all non-stress types) → neutral."""
    if type_ not in _STRESS_TYPES or not ca_verdict:
        return "neutral"
    if ca_verdict == "concentrated":
        return "confirm"
    if ca_verdict == "diversified":
        return "diverge"
    return "neutral"


def priority(tier: str, band: str, age_days: float, ca_tag: str) -> tuple[int, dict]:
    """Transparent 0-100 triage priority + its component breakdown."""
    if age_days <= 2:
        w_rec, rec_lbl = 20, "fresh (<2d)"
    elif age_days <= 7:
        w_rec, rec_lbl = 12, "<7d"
    elif age_days <= 21:
        w_rec, rec_lbl = 6, "<21d"
    else:
        w_rec, rec_lbl = 2, "older"
    comp = {
        "conviction": (W_TIER.get(tier, 8), tier),
        "severity": (W_SEVERITY.get(band, 6), band),
        "recency": (w_rec, rec_lbl),
        "cross_asset": (W_CONFIRM.get(ca_tag, 0), ca_tag),
    }
    score = sum(v[0] for v in comp.values())
    return max(0, min(100, score)), comp


def _validation(source: str, type_: str, engine_edge: str, engine_edge_zh: str,
                reg: dict, rule_sc: dict | None = None, detail: str = "") -> dict:
    """Honest edge block. Precedence: (1) the rule's OWN event-study backtest
    (rule_scorecard.json) — most direct; (2) a Signal-Lab row backing the family;
    (3) the engine's calibrated edge note; (4) documented-only.

    Always returns the SAME key set (None / [] / {} where absent) so the template
    can read v.hit / v.dsr / v.horizons without tripping Jinja's missing-key
    Undefined (which is-not-none → True → format crash)."""
    base = {"backtested": False, "verdict": "documented", "scorecard_name": None,
            "hit": None, "dsr": None, "ic": None, "n": None, "horizon": None,
            "extra": [], "report": None, "link": "signal_lab.html",
            "horizons": {}, "note": "", "note_zh": ""}

    # (1) the alert rule's own forward-SPY event study (scripts/alert_rules_phase0)
    rk = _rule_key(source, type_, detail)
    rule = (rule_sc or {}).get(rk) if rk else None
    if rule:
        v = rule.get("verdict")
        if v == "earned":
            hh = rule["headline_horizon"]
            hd = rule["horizons"][hh]
            hits = {h: rule["horizons"][h]["hit"] for h in rule.get("earned_horizons", [])}
            return {**base, "backtested": True, "verdict": "backtested",
                    "scorecard_name": rule["label"], "hit": hd["hit"],
                    "horizon": f"{hh}d", "n": rule["n_events"], "horizons": hits,
                    "report": "alert-rules-phase0",
                    "note": f"Event study on 33y SPY: {hh}d hit {hd['hit']:.0%} vs "
                            f"{hd['base_hit']:.0%} base — survives FDR.",
                    "note_zh": f"33 年标普事件研究：{hh} 日命中 {hd['hit']:.0%}"
                               f"（基准 {hd['base_hit']:.0%}）— 通过 FDR。"}
        if v == "no_edge":
            return {**base, "verdict": "no_edge", "scorecard_name": rule["label"],
                    "report": "alert-rules-phase0",
                    "note": "Event-tested on 33y SPY — NO forward edge (FDR q>0.10). "
                            "Shown as risk context, not a timing signal.",
                    "note_zh": "33 年标普事件检验 — 无前瞻边际（FDR q>0.10）。"
                               "作为风险背景，而非择时信号。"}
        if v == "underpowered":
            return {**base, "verdict": "underpowered", "scorecard_name": rule["label"],
                    "report": "alert-rules-phase0",
                    "note": f"Too few historical firings ({rule['n_events']}) to "
                            "backtest — documented conviction only.",
                    "note_zh": f"历史触发次数过少（{rule['n_events']}），无法回测 — 仅有据可查。"}

    name = _VALIDATION_MAP.get((source, type_))
    row = reg.get(name) if name else None
    if row:
        return {**base, "backtested": True,
                "verdict": row["tier"],          # scored / confirmer / display / killed
                "scorecard_name": row["name"],
                "hit": row.get("hit"), "dsr": row.get("dsr"),
                "ic": row.get("ic"), "n": row.get("n"),
                "horizon": row.get("horizon"), "extra": row.get("extra") or [],
                "report": row.get("source"),
                "note": engine_edge or "", "note_zh": engine_edge_zh or ""}
    if engine_edge:
        # BTC's edge note is derived from a real backtest (data/vector/calibration.json);
        # the macro ALERT_CONVICTION notes are documented conviction, not calibration —
        # label each honestly so the page never overstates what was measured.
        is_cal = source == "vector"
        return {**base, "backtested": "engine" if is_cal else False,
                "verdict": "calibrated" if is_cal else "documented",
                "note": engine_edge, "note_zh": engine_edge_zh or engine_edge}
    return {**base, "note": "Conviction is documented, not separately backtested "
            "as a timing signal.",
            "note_zh": "信念有据可查，但未作为择时信号单独回测。"}


def _load_context() -> dict:
    """Regime + cross-asset + risk-appetite backdrop from regime/latest.json."""
    try:
        d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
    except Exception:  # noqa: BLE001
        return {}
    ca = d.get("cross_asset") or {}
    cond = d.get("conditions") or {}
    ra = cond.get("recession") or {}
    risk = cond.get("risk_appetite") or {}
    dd = cond.get("drawdown_risk") or {}
    fc = cond.get("financial_conditions") or {}
    return {
        "asof": d.get("date"),
        "regime": {
            "quad": d.get("quad"), "quad_name": d.get("quad_name"),
            "label": d.get("label"), "cycle": d.get("cycle_tag"),
            "transition": d.get("transition_state"),
        },
        "cross_asset": {
            "verdict": ca.get("verdict"), "headline": ca.get("headline"),
            "dominant_cluster": ca.get("dominant_cluster") or [],
            "mean_abs_corr": ca.get("mean_abs_corr"),
        },
        "risk_backdrop": {
            "recession_band": ra.get("label"), "drawdown_band": dd.get("band"),
            "nfci_state": fc.get("state"), "nfci_trend": fc.get("trend"),
            "vix_term": risk.get("vix_term_state"), "vrp": risk.get("vrp_state"),
            "stock_bond_corr": risk.get("stock_bond_corr"),
        },
    }


def _events(today: date, horizon_days: int = 14) -> dict:
    """Next high-impact US catalysts + the single nearest one (for event-risk chip)."""
    try:
        from engine import event_calendar
        strip = event_calendar.high_impact_strip(today, horizon_days)
    except Exception:  # noqa: BLE001
        return {"items": [], "next": None}
    items = []
    for ev in strip[:6]:
        try:
            dleft = (date.fromisoformat(ev["date"]) - today).days
        except Exception:  # noqa: BLE001
            dleft = None
        items.append({"type": ev["type"], "label": ev.get("label", ev["type"]),
                      "md": ev.get("md"), "time_et": ev.get("time_et", ""),
                      "days": dleft})
    nxt = items[0] if items else None
    return {"items": items, "next": nxt}


def _macro_raw(today: pd.Timestamp, cutoff: pd.Timestamp) -> list[dict]:
    """Recent macro alerts from the parquet log, normalised + enriched via alert_view."""
    out: list[dict] = []
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    if not p.exists():
        return out
    try:
        from engine.alerts import alert_view
        mdf = pd.read_parquet(p)
        mdf = mdf[pd.to_datetime(mdf["date"]) >= cutoff]
        for _, r in mdf.iterrows():
            v = alert_view(r["rule"], r["severity"], r["message"])
            out.append({
                "source": "macro", "type": r["rule"], "asset": "macro",
                "ts": pd.Timestamp(r["date"]).isoformat(), "date_only": True,
                "raw_sev": r["severity"],
                "tier": v.get("tier", "context"),
                "headline": (v.get("icon", "") + " " + v.get("plain_en", r["message"])).strip(),
                "headline_zh": (v.get("icon", "") + " " + (v.get("plain_zh") or v.get("plain_en") or r["message"])).strip(),
                "detail": r["message"], "detail_zh": r["message"],
                "anchor": v.get("anchor") or "",
                "edge": v.get("edge_en", ""), "edge_zh": v.get("edge_zh", ""),
            })
    except Exception as e:  # noqa: BLE001
        log.warning("triage: macro feed unavailable (%s)", e)
    return out


def _jsonl_raw(source: str, today: pd.Timestamp, cutoff: pd.Timestamp,
               tier_map: dict) -> list[dict]:
    """Recent events from a jsonl alert engine, with a per-(source,type) tier."""
    out: list[dict] = []
    try:
        mod = {
            "bonds": "bonds_alerts", "forex": "forex_alerts",
            "vector": "btc_alerts", "commodity": "commodity_alerts",
            "themes": "theme_alerts", "emergence": "emergence_alerts",
            "altdata": "altdata_alerts",
            "demand": "demand_alerts",
            "rotation": "subsector_rotation_alerts",
            "oracle": "oracle.alerts",
        }[source]
        m = __import__("engine." + mod, fromlist=[mod])
        for e in m.load_events():
            ts = pd.Timestamp(e["ts"])
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
            if ts < cutoff:
                continue
            type_ = e.get("type", "")
            # BTC carries its own conviction tier; others use the per-source map.
            tier = e.get("tier") or tier_map.get(type_, "context")
            out.append({
                "source": source, "type": type_, "asset": e.get("asset") or source,
                "ts": ts.isoformat(),
                "date_only": (ts.hour == 0 and ts.minute == 0),
                "raw_sev": e.get("severity", "info"), "tier": tier,
                "headline": e.get("headline", ""),
                "headline_zh": e.get("headline_zh") or e.get("headline", ""),
                "detail": e.get("detail", ""),
                "detail_zh": e.get("detail_zh") or e.get("detail", ""),
                "anchor": e.get("anchor") or "#timeline",
                "edge": e.get("edge", ""), "edge_zh": e.get("edge_zh", ""),
            })
    except Exception as ex:  # noqa: BLE001
        log.warning("triage: %s feed unavailable (%s)", source, ex)
    return out


def build_triage(days: int = 30, today: date | None = None,
                 per_source_context_cap: int = 6, max_items: int = 60) -> dict:
    """Assemble the full Alert Command Center payload. Pure assembler, graceful.

    days                    look-back window (the board shows what is *live now*)
    per_source_context_cap  cap context-tier alerts per source so a noisy feed
                            (forex per-pair) can't drown the actionable ones
    max_items               global cap after ranking
    """
    today = today or datetime.now(timezone.utc).date()
    today_ts = pd.Timestamp(today)
    cutoff = today_ts - pd.Timedelta(days=days)
    reg = _registry_index()
    rule_sc = _rule_scorecard()
    ctx = _load_context()
    ca_verdict = (ctx.get("cross_asset") or {}).get("verdict")

    raw: list[dict] = []
    raw += _macro_raw(today_ts, cutoff)
    raw += _jsonl_raw("bonds", today_ts, cutoff, _BONDS_TIER)
    raw += _jsonl_raw("forex", today_ts, cutoff, _FOREX_TIER)
    raw += _jsonl_raw("vector", today_ts, cutoff, {})       # tier inline on events
    raw += _jsonl_raw("commodity", today_ts, cutoff, _COMMODITY_TIER)
    raw += _jsonl_raw("themes", today_ts, cutoff, _THEMES_TIER)
    raw += _jsonl_raw("emergence", today_ts, cutoff, _EMERGENCE_TIER)
    raw += _jsonl_raw("altdata", today_ts, cutoff, _ALTDATA_TIER)
    raw += _jsonl_raw("demand", today_ts, cutoff, _DEMAND_TIER)
    raw += _jsonl_raw("rotation", today_ts, cutoff, _ROTATION_TIER)
    raw += _jsonl_raw("oracle", today_ts, cutoff, _ORACLE_TIER)

    enriched: list[dict] = []
    for a in raw:
        tier = a["tier"]
        band = severity_band(tier, a["raw_sev"])
        # #42: measured-IC severity — the hardcoded band is a prior; a spine-measured null /
        # wrong-sign emitter is capped so it can't outrank validated risk-off signals.
        band, ic_note = ic_severity_cap(a["source"], a["type"], band)
        ca_tag = cross_asset_tag(a["type"], ca_verdict)
        age = max(0.0, (today_ts - pd.Timestamp(a["ts"]).normalize()).days)
        score, comp = priority(tier, band, age, ca_tag)
        act_en, act_zh = action_for(tier, band, ca_tag)
        smeta = SOURCES.get(a["source"], {})
        # Stable content-hash ID: (source, type, asset, date-part).
        # Truncated to 12 hex chars — collision-probability negligible for
        # the ~60-alert board.  Used by the admin Alerts capture tab.
        _id_key = f"{a['source']}|{a['type']}|{a.get('asset', '')}|{a['ts'][:10]}"
        alert_id = hashlib.sha256(_id_key.encode()).hexdigest()[:12]
        enriched.append({
            **a,
            "alert_id": alert_id,
            "severity": band, "age_days": int(age),
            "priority": score, "priority_components": comp,
            "cross_asset_tag": ca_tag,
            "action": act_en, "action_zh": act_zh,
            "source_label": smeta.get("label", a["source"]),
            "source_label_zh": smeta.get("label_zh", a["source"]),
            "source_icon": smeta.get("icon", "•"),
            "link": smeta.get("page", "macro.html") + (a.get("anchor") or ""),
            "validation": _validation(a["source"], a["type"], a.get("edge", ""),
                                      a.get("edge_zh", ""), reg, rule_sc,
                                      a.get("detail", "")),
            "ic_severity": ic_note,
        })

    # collapse re-fires of the same (source,type,asset) within the window: keep the
    # newest, highest-priority instance so the board reads current, not repetitive.
    best: dict[tuple, dict] = {}
    for a in enriched:
        key = (a["source"], a["type"], a["asset"])
        cur = best.get(key)
        if cur is None or (a["priority"], a["ts"]) > (cur["priority"], cur["ts"]):
            best[key] = a
    deduped = list(best.values())

    deduped.sort(key=lambda x: (x["priority"], x["ts"]), reverse=True)

    # keep every act/watch; cap the context-tier long tail per source
    seen_ctx: dict[str, int] = {}
    kept: list[dict] = []
    for a in deduped:
        if a["tier"] == "context":
            n = seen_ctx.get(a["source"], 0)
            if n >= per_source_context_cap:
                continue
            seen_ctx[a["source"]] = n + 1
        kept.append(a)
    kept = kept[:max_items]

    summary = {
        "total": len(kept),
        "critical": sum(1 for a in kept if a["severity"] == "critical"),
        "major": sum(1 for a in kept if a["severity"] == "major"),
        "minor": sum(1 for a in kept if a["severity"] == "minor"),
        "actionable": sum(1 for a in kept if a["tier"] == "act"),
        "by_source": {s: sum(1 for a in kept if a["source"] == s) for s in SOURCES},
        "backtested": sum(1 for a in kept if a["validation"].get("backtested") is True),
    }

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "asof": ctx.get("asof"),
        "window_days": days,
        "regime": ctx.get("regime") or {},
        "cross_asset": ctx.get("cross_asset") or {},
        "risk_backdrop": ctx.get("risk_backdrop") or {},
        "events": _events(today),
        "summary": summary,
        "alerts": kept,
        "weights": {"tier": W_TIER, "severity": W_SEVERITY, "confirm": W_CONFIRM},
    }


# ---------------------------------------------------------------------------
# PUSH SPINE — Neural Web W6a/W6b
# ---------------------------------------------------------------------------
# Article-2 surface: priority inputs are unvalidated hand-weights. These
# functions are CONFIG-GATED (alert_push.enabled=false by default in W6a;
# enabled=true in W6b — operator decision, see config.yml comment block).
# Enabling is an operator event — it converts a display-only priority score
# into automated outbound dispatch. Per Article 2: no ranking/priority surface
# may RAISE a score without SHADOW-with-track-record tier. These functions
# never raise scores; they only dispatch alerts that already cleared the floor.
#
# W6b DESIGN: per-lane dedup stores (push_sent_<lane>.jsonl) preserve single-
# writer law per file. The dedup window check reads ALL stores (read-many,
# write-one). This means basket_freeze, signal_sanity, and healthcheck each
# own their own ledger file and are the SOLE writer to that file — no race,
# no lock needed. push_priority_alerts() continues to use push_sent.jsonl
# (the original lane). The dedup check for ops alerts reads all push_sent*
# files so cross-lane duplicates are also suppressed.
#
# WHITEHOUSE: the whitehouse pattern (single-writer hourly sentinel) is SACRED
# and is NOT migrated here. It remains untouched. push_ops_alert() never
# reads data/whitehouse/alerts.jsonl.
#
# SIGNAL SENTINELS (vector/commodity): PHASE 3 — not migrated in this PR.
# They have existing dedup; the migration would add priority context only.
# Noted as follow-up in the W6b masterplan entry.

_PUSH_SENT_PATH = "alert_triage/push_sent.jsonl"  # relative to data_dir()

# Per-lane ledger file names (relative to data/alert_triage/).
# Each lane is the SOLE writer to its own file (single-writer law per file).
# The dedup check reads all of them (read-many, write-one).
_OPS_LANES: dict[str, str] = {
    "basket_freeze": "push_sent_basket_freeze.jsonl",
    "signal_sanity": "push_sent_signal_sanity.jsonl",
    "healthcheck": "push_sent_healthcheck.jsonl",
}


def _push_sent_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "data" / _PUSH_SENT_PATH
    return config.data_dir() / _PUSH_SENT_PATH


def _load_recent_sends(
    p: Path,
    window_hours: int,
    now: datetime,
) -> set[tuple[str, str, str]]:
    """Load (source, type, asset) keys sent within the dedup window."""
    cutoff = now - timedelta(hours=window_hours)
    seen: set[tuple[str, str, str]] = set()
    if not p.exists():
        return seen
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    sent_at_raw = rec.get("sent_at", "")
                    sent_at = datetime.fromisoformat(sent_at_raw.replace("Z", "+00:00"))
                    if sent_at >= cutoff.replace(tzinfo=timezone.utc):
                        seen.add((
                            str(rec.get("source", "")),
                            str(rec.get("type", "")),
                            str(rec.get("asset", "")),
                        ))
                except Exception:  # noqa: BLE001 — skip malformed lines
                    pass
    except Exception:  # noqa: BLE001 — file read failure → empty dedup store
        pass
    return seen


def _append_sent(p: Path, alert: dict, sent_at: datetime) -> None:
    """Append a sent-record to the push_sent.jsonl dedup store."""
    rec = {
        "source": alert.get("source", ""),
        "type": alert.get("type", ""),
        "asset": alert.get("asset", ""),
        "headline": alert.get("headline", "")[:120],
        "priority": alert.get("priority", 0),
        "sent_at": sent_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as e:  # noqa: BLE001 — never fail the dispatch on append
        log.warning("push_sent append failed (non-fatal): %s", e)


def _format_push_payload(alert: dict) -> str:
    """Format one alert into a Telegram-ready push message."""
    icon = alert.get("source_icon", "•")
    headline = alert.get("headline", "")
    detail = (alert.get("detail") or "")[:200]
    action = alert.get("action", "")
    score = alert.get("priority", 0)
    site_url = (config.load().get("notify") or {}).get("site_url", "")
    link = alert.get("link", "")
    url_part = f"\n  <a href='{site_url}/{link}'>→ view</a>" if site_url and link else ""
    lines = [
        f"{icon} <b>{headline}</b>",
    ]
    if detail and detail.strip():
        lines.append(detail.strip())
    lines.append(f"  conviction: {action} | priority: {score}/100{url_part}")
    return "\n".join(lines)


# Explicit push-suppress list: families whose IC is documented-null or capped —
# these must never push regardless of score (Article-2 hard floor exception).
_PUSH_SUPPRESS = frozenset({
    ("rotation", "entered_book"),
    ("rotation", "left_book"),
    ("rotation", "leadership_rotation"),
})


def push_priority_alerts(
    threshold: int = 60,
    window_hours: int = 6,
    root: Path | str | None = None,
    *,
    today: date | None = None,
    _dedup_store: Path | None = None,  # injectable for tests
) -> list[dict]:
    """Run ``build_triage()``, filter to priority >= threshold, dedup against
    recent sends, dispatch via ``scripts.notify``.

    CONFIG-GATED: reads ``alert_push.enabled`` from config.yml.  Default is
    ``false``.  When disabled this function is a pure no-op (returns []).
    Enabling it is an **operator + Article-2 event** — it converts the
    display-only priority score into automated outbound dispatch.

    Parameters
    ----------
    threshold:
        Priority floor (0-100).  Alerts with priority < threshold are not
        dispatched.  Default 60 = act/critical or act/major-fresh minimum.
    window_hours:
        Dedup window.  An alert with the same (source, type, asset) key is
        silenced for this many hours after its last send.
    root:
        Optional repo root override (used in tests).
    today:
        Date override (used in tests).
    _dedup_store:
        Path override for push_sent.jsonl (used in tests).

    Returns
    -------
    list[dict]
        Newly dispatched alerts (empty list if gated off, no new alerts, or
        dispatch failed).

    Never raises — exits 0 whether it dispatched, skipped, or errored.
    """
    # --- CONFIG GATE (default OFF) ------------------------------------------
    try:
        cfg = config.load()
        push_cfg = cfg.get("alert_push") or {}
        if not push_cfg.get("enabled", False):
            log.debug("push_priority_alerts: disabled (alert_push.enabled=false)")
            return []
    except Exception as e:  # noqa: BLE001 — never fail the call site
        log.warning("push_priority_alerts: config read failed (%s) — no-op", e)
        return []

    # --- BUILD TRIAGE -------------------------------------------------------
    try:
        triage = build_triage(today=today)
        alerts = triage.get("alerts") or []
    except Exception as e:  # noqa: BLE001
        log.warning("push_priority_alerts: build_triage failed (%s) — no-op", e)
        return []

    # --- FILTER: priority floor + explicit suppress list --------------------
    candidates = [
        a for a in alerts
        if a.get("priority", 0) >= threshold
        and (a.get("source", ""), a.get("type", "")) not in _PUSH_SUPPRESS
    ]
    if not candidates:
        log.debug("push_priority_alerts: no alerts above threshold=%d", threshold)
        return []

    # --- DEDUP --------------------------------------------------------------
    now = datetime.now(timezone.utc)
    dedup_path = _dedup_store if _dedup_store is not None else _push_sent_path(root)
    recent = _load_recent_sends(dedup_path, window_hours, now)
    to_send = [
        a for a in candidates
        if (a.get("source", ""), a.get("type", ""), a.get("asset", "")) not in recent
    ]
    if not to_send:
        log.info("push_priority_alerts: all %d candidates in dedup window — nothing new",
                 len(candidates))
        return []

    # --- DISPATCH -----------------------------------------------------------
    try:
        from scripts.notify import send_discord, send_telegram  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.warning("push_priority_alerts: cannot import notify (%s) — no-op", e)
        return []

    dispatched: list[dict] = []
    for a in to_send:
        msg = _format_push_payload(a)
        ok_tg = ok_dc = False
        try:
            ok_tg = send_telegram(msg)
        except Exception as e:  # noqa: BLE001
            log.warning("push_priority_alerts: send_telegram failed (%s)", e)
        try:
            ok_dc = send_discord(msg)
        except Exception as e:  # noqa: BLE001
            log.warning("push_priority_alerts: send_discord failed (%s)", e)
        if ok_tg or ok_dc:
            _append_sent(dedup_path, a, now)
            dispatched.append(a)
            log.info("push_priority_alerts: dispatched %s/%s priority=%d",
                     a.get("source"), a.get("type"), a.get("priority", 0))
        else:
            log.info("push_priority_alerts: no channel available for %s/%s",
                     a.get("source"), a.get("type"))

    return dispatched


# ---------------------------------------------------------------------------
# OPS-TIER PUSH ADAPTER — Neural Web W6b
# ---------------------------------------------------------------------------
# push_ops_alert() is the single entry point for ops-tier senders
# (basket_freeze, signal_sanity, healthcheck) that previously called
# send_telegram/send_discord directly with no dedup and no priority floor.
#
# DESIGN INVARIANTS:
# 1. DISPATCH-ALWAYS FOR OPS LANES: ops/liveness alerts (heartbeat, tripwire,
#    churn-guard) MUST reach the operator regardless of the enabled flag.
#    When alert_push.enabled=false the dedup spine and per-lane ledger are
#    skipped, but send_telegram/send_discord are still called raw so that
#    disabling the noise-reduction spine cannot silence a critical liveness
#    alert.  The flag controls dedup+ledger overhead only, not the send.
# 2. PER-LANE SINGLE-WRITER: the caller names its lane; the dedup record is
#    appended ONLY to data/alert_triage/push_sent_<lane>.jsonl. Single-writer
#    law per file is preserved. No lock needed.
# 3. DEDUP WINDOW (enabled only): before dispatch, reads ALL push_sent*.jsonl
#    files (the original push_sent.jsonl + all per-lane files) so cross-lane
#    duplicates are also suppressed within the window_hours window.  Skipped
#    entirely when enabled=false (raw dispatch has no dedup).
# 4. MESSAGE PRESERVED: the caller supplies the message text verbatim; no
#    content rewriting. The ops message is wrapped in a minimal envelope only
#    for the dedup key (source + type_ + "").
# 5. NEVER RAISES: always returns bool; exceptions are logged, never re-raised.
# 6. WHITEHOUSE UNTOUCHED: this function never reads whitehouse/ or calls any
#    whitehouse-specific path.

def _ops_lane_path(lane: str, root: Path | str | None = None) -> Path:
    """Return path to per-lane dedup store for `lane`."""
    fname = _OPS_LANES.get(lane, f"push_sent_{lane}.jsonl")
    if root is not None:
        return Path(root) / "data" / "alert_triage" / fname
    return config.data_dir() / "alert_triage" / fname


def _load_recent_sends_all_lanes(
    window_hours: int,
    now: datetime,
    root: Path | str | None = None,
) -> set[tuple[str, str, str]]:
    """Load (source, type, asset) dedup keys from ALL push_sent* files.

    This is read-many: it scans push_sent.jsonl plus every per-lane file so
    cross-lane duplicates are suppressed. Each file is still written by exactly
    one lane (single-writer per file).
    """
    base = config.data_dir() if root is None else Path(root) / "data"
    triage_dir = base / "alert_triage"
    seen: set[tuple[str, str, str]] = set()
    if not triage_dir.exists():
        return seen
    # Collect all push_sent* files (the original + per-lane)
    store_paths = list(triage_dir.glob("push_sent*.jsonl"))
    for p in store_paths:
        seen |= _load_recent_sends(p, window_hours, now)
    return seen


def push_ops_alert(
    source: str,
    type_: str,
    message: str,
    severity: str = "major",
    lane: str = "",
    window_hours: int | None = None,
    root: Path | str | None = None,
    _now: datetime | None = None,
    _dedup_store: Path | None = None,
) -> bool:
    """Dispatch a single ops-tier alert, bypassing the spine only for dedup/ledger.

    This is the W6b adapter for senders that previously called send_telegram/
    send_discord directly.  Unlike push_priority_alerts(), ops/liveness alerts
    are dispatch-always: ``alert_push.enabled=false`` disables the dedup spine
    and per-lane ledger but still calls send_telegram/send_discord raw so that
    a heartbeat or tripwire failure is never silenced by a flag flip.  When the
    spine is enabled, per-lane dedup and the JSONL ledger are applied normally.

    Parameters
    ----------
    source:
        Alert source identifier (e.g. "basket_freeze", "signal_sanity",
        "healthcheck"). Used as the dedup key component.
    type_:
        Alert type within the source (e.g. "churn_guard", "tripwire_failed",
        "heartbeat_failed"). Used as the dedup key component.
    message:
        The human-readable message text to dispatch verbatim.
    severity:
        "critical", "major", or "minor". Used only for logging; does not gate
        dispatch (the config threshold applies).
    lane:
        The per-lane ledger name (one of: "basket_freeze", "signal_sanity",
        "healthcheck"). Determines which push_sent_<lane>.jsonl is written.
        Defaults to source if empty.
    window_hours:
        Dedup window override (hours). If None, reads from config
        alert_push.window_hours (default 6).
    root:
        Repo root override (used in tests).
    _now:
        datetime override (used in tests).
    _dedup_store:
        Explicit dedup store path override (used in tests; overrides lane
        resolution).

    Returns
    -------
    bool
        True if dispatched on at least one channel, False otherwise.

    Never raises — always returns bool.
    """
    # --- CONFIG GATE --------------------------------------------------------
    # Ops/liveness alerts dispatch unconditionally — disabling the spine
    # (alert_push.enabled=false) must not silence a heartbeat or tripwire
    # failure.  When disabled we skip the dedup+ledger path and call the
    # transport raw so the operator still receives the alert.
    _spine_enabled = False
    _window_hours = window_hours if window_hours is not None else 6
    try:
        cfg = config.load()
        push_cfg = cfg.get("alert_push") or {}
        _spine_enabled = bool(push_cfg.get("enabled", False))
        if window_hours is None:
            _window_hours = int(push_cfg.get("window_hours", 6))
    except Exception as e:  # noqa: BLE001
        log.warning("push_ops_alert(%s/%s): config read failed (%s) — proceeding with raw dispatch",
                    source, type_, e)

    now = _now if _now is not None else datetime.now(timezone.utc)
    _lane = lane or source

    # --- DEDUP: read ALL lanes (read-many) — spine-enabled path only --------
    # When the spine is disabled we skip dedup entirely and dispatch raw so
    # that alert_push.enabled=false cannot silence a liveness/tripwire alert.
    if _spine_enabled:
        try:
            dedup_key = (str(source), str(type_), "")
            all_recent = _load_recent_sends_all_lanes(_window_hours, now, root=root)
            if dedup_key in all_recent:
                log.info("push_ops_alert(%s/%s): in dedup window (%dh) — skipped",
                         source, type_, _window_hours)
                return False
        except Exception as e:  # noqa: BLE001
            log.warning("push_ops_alert(%s/%s): dedup check failed (%s) — proceeding",
                        source, type_, e)
    else:
        log.debug("push_ops_alert(%s/%s): spine disabled — raw dispatch (no dedup, no ledger)",
                  source, type_)

    # --- DISPATCH -----------------------------------------------------------
    try:
        from scripts.notify import send_discord, send_telegram  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.warning("push_ops_alert(%s/%s): cannot import notify (%s) — no-op", source, type_, e)
        return False

    ok_tg = ok_dc = False
    try:
        ok_tg = send_telegram(message)
    except Exception as e:  # noqa: BLE001
        log.warning("push_ops_alert(%s/%s): send_telegram failed (%s)", source, type_, e)
    try:
        ok_dc = send_discord(message)
    except Exception as e:  # noqa: BLE001
        log.warning("push_ops_alert(%s/%s): send_discord failed (%s)", source, type_, e)

    if ok_tg or ok_dc:
        if _spine_enabled:
            # --- WRITE: per-lane ledger only (write-one, spine-enabled path) ----
            rec = {
                "source": source,
                "type": type_,
                "asset": "",
                "headline": message[:120],
                "priority": -1,   # ops alerts have no triage priority score
                "severity": severity,
                "sent_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            write_path = _dedup_store if _dedup_store is not None else _ops_lane_path(_lane, root=root)
            try:
                write_path.parent.mkdir(parents=True, exist_ok=True)
                with open(write_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            except Exception as e:  # noqa: BLE001
                log.warning("push_ops_alert: lane ledger append failed (non-fatal): %s", e)
        log.info("push_ops_alert: dispatched %s/%s severity=%s", source, type_, severity)
        return True

    log.info("push_ops_alert: no channel available for %s/%s", source, type_)
    return False
