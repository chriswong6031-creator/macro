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

import json
from datetime import date, datetime, timezone

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
# gets is 'watch'; a leadership reshuffle is 'context'.
_THEMES_TIER = {
    "theme_topping": "watch", "theme_deteriorating": "watch",
    "theme_emerging": "watch", "reco_change": "watch",
    "leadership_rotation": "context",
}
# Forming-narrative detections (engine.emergence_alerts) are a CONTEXT watchlist — a newly
# coherent group of names carries no validated forward edge, so it never rises above context.
_EMERGENCE_TIER = {"narrative_forming": "context"}

# Source display metadata: label (EN/ZH), icon, and the page each alert deep-links to.
SOURCES = {
    "macro":     {"label": "Macro Vector",    "label_zh": "宏观向量",   "icon": "📊", "page": "macro.html"},
    "bonds":     {"label": "Bonds",           "label_zh": "债券",       "icon": "🏛️", "page": "bonds.html"},
    "forex":     {"label": "Forex",           "label_zh": "外汇",       "icon": "💱", "page": "forex.html"},
    "vector":    {"label": "Bitcoin Vector",  "label_zh": "比特币向量", "icon": "₿",  "page": "vector.html"},
    "commodity": {"label": "Commodity Vector","label_zh": "大宗商品",   "icon": "🛢", "page": "commodities.html"},
    "themes":    {"label": "Theme Rotation",  "label_zh": "主题轮动",   "icon": "🧺", "page": "baskets.html"},
    "emergence": {"label": "Forming Narratives","label_zh": "成形叙事", "icon": "🔥", "page": "baskets.html"},
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

    enriched: list[dict] = []
    for a in raw:
        tier = a["tier"]
        band = severity_band(tier, a["raw_sev"])
        ca_tag = cross_asset_tag(a["type"], ca_verdict)
        age = max(0.0, (today_ts - pd.Timestamp(a["ts"]).normalize()).days)
        score, comp = priority(tier, band, age, ca_tag)
        act_en, act_zh = action_for(tier, band, ca_tag)
        smeta = SOURCES.get(a["source"], {})
        enriched.append({
            **a,
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
