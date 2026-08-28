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

WHO RENDERS THIS PAGE (verified 2026-08-20 — there is no ``build_alerts.py``)
----------------------------------------------------------------------------
``build_triage()`` has exactly one page owner, and it is the shared site plane:

    scripts/build_site.py :: build_alerts_page(env, site, generated)
        payload = alert_triage.build_triage()
        payload["generated_utc"] = generated          # aligned with the rest of the site
        -> templates/alerts.html.j2  -> site/alerts.html
        -> site/factordata/alerts_triage.json         (the whole payload, machine-readable)
        -> site/alertsdata/feed.json                  (admin Alerts capture tab, RUL-8)

Nothing else renders it.  The only OTHER consumer of this module is the push spine below
(``push_priority_alerts`` / ``push_ops_alert``), which re-runs ``build_triage()`` itself.
Extend that plane — do not add a parallel builder.

TIME (see engine/alert_time.py for the full contract)
-----------------------------------------------------
Three clocks are kept separate and are NOT interchangeable: ``event_date`` / ``event_ts``
(when the thing happened), ``source_asof`` (the observation it was derived from), and
``recorded_at`` / ``generated_utc`` (when we processed it).  The board's "today" is the
**America/New_York** day, because this is a US cross-asset desk — at 00:30Z New York is
still on the previous afternoon, and a board that rolled over with UTC spent the whole
nightly window mislabelling the prior session as "today".
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from engine import alert_time
from lib import config

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
_ROTATION_TIER = {"rotation_emerging": "watch", "rotation_fading": "context",
                  "rotation_event": "watch"}
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
# Watchlist buy-zone enter-detection (B6).  Operator-account only, no validated
# forward edge yet — capped at 'context' (display-only, never an 'act' trigger).
_WATCHLIST_TIER = {"buy_zone_enter": "context"}

# Source display metadata: label (EN/ZH), icon, and the page each alert deep-links to.
SOURCES = {
    "macro":     {"label": "Macro Vector",    "label_zh": "宏观向量",   "icon": "📊", "page": "macro.html"},
    "bonds":     {"label": "Bonds",           "label_zh": "债券",       "icon": "🏛️", "page": "bonds.html"},
    "forex":     {"label": "Forex",           "label_zh": "外汇",       "icon": "💱", "page": "forex.html"},
    "vector":    {"label": "Bitcoin Vector",  "label_zh": "比特币向量", "icon": "₿",  "page": "vector.html"},
    "commodity": {"label": "Commodity Vector","label_zh": "大宗商品",   "icon": "🛢", "page": "commodities.html"},
    # themes: page must carry a #theme-<id> resolver — baskets.html is a redirect stub
    # since the Sector Intelligence consolidation (#4237); the resolver lives on the
    # merged page (tests/test_theme_hash_deeplink.py pins both halves).
    "themes":    {"label": "Theme Rotation",  "label_zh": "主题轮动",   "icon": "🧺", "page": "sector_central.html"},
    # emergence: the alert carries a precise `#ne-<signature>` anchor and the card that
    # anchor names is rendered by templates/forming_narratives.js, which is included by
    # sector_central.html.j2 — NOT by baskets.html, a redirect stub since the Sector
    # Intelligence consolidation (#4237).  That stub forwards only `#theme-*` and dumps
    # everything else on `sector_central.html#actnow-section`, so routing here through
    # baskets.html threw the reader onto a generic page section instead of the exact
    # evidence the alert is about.  Point at the canonical evidence owner directly.
    "emergence": {"label": "Forming Narratives","label_zh": "成形叙事", "icon": "🔥", "page": "sector_central.html"},
    "altdata":   {"label": "Alternative Data",  "label_zh": "替代数据",   "icon": "📊", "page": "alt_data.html"},
    "demand":    {"label": "Demand Desk",      "label_zh": "需求台",     "icon": "🧭", "page": "demand.html"},
    "rotation":  {"label": "Subsector Rotation","label_zh": "子行业轮动", "icon": "🌀", "page": "subsector_rotation.html"},
    "oracle":    {"label": "Oracle Rotation",  "label_zh": "Oracle 轮动", "icon": "🔭", "page": "subsector_rotation.html"},
    # B6 — Watchlist sentinel: operator-specific buy-zone enter-detection.
    # Display-only; no validated backtest; tier capped at 'context' until
    # a forward ledger earns a verdict.
    "watchlist": {"label": "Watchlist Sentinel", "label_zh": "自选清单哨兵", "icon": "👁", "page": "watchlist.html"},
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


def priority(tier: str, band: str, age_days: float | None, ca_tag: str) -> tuple[int, dict]:
    """Transparent 0-100 triage priority + its component breakdown.

    ``age_days`` is measured in BOARD days (America/New_York), and may be None when the
    event time is unknown.  An unknown date earns ZERO recency credit — we will not hand a
    freshness bonus to an alert that cannot prove it is fresh.
    """
    if age_days is None:
        w_rec, rec_lbl = 0, "date unknown"
    elif age_days <= 2:
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
    except Exception as e:  # noqa: BLE001
        # An unreadable backdrop is MISSING, not neutral.  cross_asset_tag() already
        # declines to tag anything without a verdict, but the board must SAY the
        # backdrop is missing instead of quietly presenting "no confirmation" as if
        # the tape had been consulted and had nothing to add.
        log.warning("triage: regime backdrop unavailable (%s)", e)
        return {"_state": READ_UNAVAILABLE}
    ca = d.get("cross_asset") or {}
    cond = d.get("conditions") or {}
    ra = cond.get("recession") or {}
    risk = cond.get("risk_appetite") or {}
    dd = cond.get("drawdown_risk") or {}
    fc = cond.get("financial_conditions") or {}
    return {
        "_state": READ_OK,
        "asof": d.get("date"),
        "regime": {
            "quad": d.get("quad"), "quad_name": d.get("quad_name"),
            "quad_name_zh": enum_zh("quad", d.get("quad_name")),
            "label": d.get("label"), "cycle": d.get("cycle_tag"),
            "transition": d.get("transition_state"),
        },
        "cross_asset": {
            "verdict": ca.get("verdict"), "verdict_zh": enum_zh("ca", ca.get("verdict")),
            "headline": ca.get("headline"),
            "dominant_cluster": ca.get("dominant_cluster") or [],
            "mean_abs_corr": ca.get("mean_abs_corr"),
        },
        "risk_backdrop": {
            "recession_band": ra.get("label"), "recession_band_zh": enum_zh("band", ra.get("label")),
            "drawdown_band": dd.get("band"), "drawdown_band_zh": enum_zh("band", dd.get("band")),
            "nfci_state": fc.get("state"), "nfci_state_zh": enum_zh("nfci", fc.get("state")),
            "nfci_trend": fc.get("trend"),
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


# ---------------------------------------------------------------------------
# SOURCE READ HEALTH — a failed read is MISSING EVIDENCE, never zero alerts
# ---------------------------------------------------------------------------
# Every reader used to collapse three different worlds into the same ``[]``:
#   * the feed read fine and genuinely has nothing to say;
#   * the feed has never produced anything yet (no store on disk);
#   * the reader CRASHED and we have no idea what it holds.
# The board then computed its pressure gauge from whatever survived, so a bonds
# outage and a quiet bonds tape were mathematically identical — and if the dead
# feed had been carrying stress events, losing it LOWERED the score and produced a
# more constructive headline.  An outage could make the product look safer.
#
# This is deterministic read metadata for THIS build.  It is not a health database,
# not a producer SLA, and it says nothing about freshness: a transition-event store
# legitimately has no events for weeks, and "latest event is old" is NOT a failure.
READ_OK = "ok"                          # read succeeded, events in the window
READ_OK_ZERO = "ok_zero_events"         # read succeeded, legitimately nothing to say
READ_NO_COVERAGE = "no_coverage"        # no store yet — first run / this feed has no coverage
READ_UNAVAILABLE = "unavailable"        # import/read/parse failed — we do NOT know what it holds

# The families that can contribute act-tier weight or risk-off STRESS to the board
# read.  These are the ONLY sources whose disappearance can LOWER the pressure score,
# so these are the ones whose absence costs the board its whole-tape authority.
# (macro/bonds/commodity own the stress clusters; vector carries its own inline tier
# and can reach 'act' on the BTC risk regime.)
_CONSEQUENTIAL_SOURCES = ("macro", "bonds", "commodity", "vector")


def _read(source: str, state: str, events: list[dict], reason: str | None = None) -> dict:
    """One reader's typed result.  ``reason`` is for OUR logs — never rendered."""
    return {"source": source, "state": state, "events": events, "reason": reason}


def _store_state(mod) -> tuple[str, str | None]:
    """Distinguish 'this feed has no store yet' from 'the store is there and empty'.

    Every jsonl alert engine exposes ``_path()``.  If we cannot resolve it we say so
    rather than guessing — an unanswerable probe is not a clean bill of health.
    """
    try:
        return (READ_OK_ZERO, None) if mod._path().exists() else (READ_NO_COVERAGE, None)
    except Exception as e:  # noqa: BLE001
        return READ_OK_ZERO, f"store path unresolved: {type(e).__name__}"


def _window_date(clocks: dict, ev: dict) -> date | None:
    """The date the WINDOW filter scans on — a store-scan bound, not an event claim.

    Normally the event's board day.  When the event time is unknown the only handle we
    have is the record clock, so we scan on that and the alert still renders with its date
    disclosed as unknown (it earns no recency credit — see ``priority``).
    """
    bd = alert_time.parse_date(clocks.get("board_date"))
    if bd is not None:
        return bd
    return alert_time.parse_date(ev.get("ts") or clocks.get("recorded_at"))


def _macro_raw(today: date, cutoff: date) -> dict:
    """Recent macro alerts from the parquet log, normalised + enriched via alert_view."""
    out: list[dict] = []
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    if not p.exists():
        return _read("macro", READ_NO_COVERAGE, out)
    try:
        from engine.alerts import alert_href, alert_view
        mdf = pd.read_parquet(p)
        mdf = mdf[pd.to_datetime(mdf["date"]).dt.date >= cutoff]
        for _, r in mdf.iterrows():
            v = alert_view(r["rule"], r["severity"], r["message"])
            # The macro log's `date` column is a market-SESSION date: it has no clock time
            # and never gains a fabricated one.
            sess = pd.Timestamp(r["date"]).date().isoformat()
            out.append({
                "source": "macro", "type": r["rule"], "asset": "macro",
                "ts": sess, "date_only": True,
                "event_date": sess, "event_ts": None, "source_asof": sess,
                "recorded_at": None, "board_date": sess,
                "date_precision": alert_time.PRECISION_DATE,
                "raw_sev": r["severity"],
                "tier": v.get("tier", "context"),
                "headline": (v.get("icon", "") + " " + v.get("plain_en", r["message"])).strip(),
                "headline_zh": (v.get("icon", "") + " " + (v.get("plain_zh") or v.get("plain_en") or r["message"])).strip(),
                "detail": r["message"], "detail_zh": r["message"],
                "anchor": v.get("anchor") or "",
                # page-qualified (ALERT_META anchors are bare ids, and v5 homes may
                # live on another page) — enrichment prefers this over page+anchor
                "link": alert_href(v.get("anchor") or ""),
                "edge": v.get("edge_en", ""), "edge_zh": v.get("edge_zh", ""),
            })
    except Exception as e:  # noqa: BLE001
        log.warning("triage: macro feed unavailable (%s)", e)
        # UNAVAILABLE, not empty: we do not know what this feed holds, and saying
        # "zero macro alerts" would be a claim we cannot support.
        return _read("macro", READ_UNAVAILABLE, [], f"{type(e).__name__}: {e}")
    return _read("macro", READ_OK if out else READ_OK_ZERO, out)


def _jsonl_raw(source: str, today: date, cutoff: date,
               tier_map: dict) -> dict:
    """Recent events from a jsonl alert engine, with a per-(source,type) tier.

    Time handling goes through ``engine.alert_time``: a session date stays a session date,
    an offset-aware instant KEEPS its offset (the old ``tz_localize(None)`` destroyed that
    provenance), and an event with no usable time is carried with its date disclosed as
    unknown rather than silently dated to the build.

    Returns a TYPED read (see READ_*): a crash is ``unavailable`` — missing evidence — and
    is never reported as "this feed had no alerts".
    """
    out: list[dict] = []
    mod_obj = None
    try:
        mod = {
            "bonds": "bonds_alerts", "forex": "forex_alerts",
            "vector": "btc_alerts", "commodity": "commodity_alerts",
            "themes": "theme_alerts", "emergence": "emergence_alerts",
            "altdata": "altdata_alerts",
            "demand": "demand_alerts",
            "rotation": "subsector_rotation_alerts",
            "oracle": "oracle.alerts",
            "watchlist": "watchlist_alerts",
        }[source]
        m = mod_obj = __import__("engine." + mod, fromlist=[mod])
        for e in m.load_events():
            clocks = alert_time.normalize_event(e)
            wd = _window_date(clocks, e)
            if wd is not None and wd < cutoff:
                continue
            type_ = e.get("type", "")
            # BTC carries its own conviction tier; others use the per-source map.
            tier = e.get("tier") or tier_map.get(type_, "context")
            out.append({
                "source": source, "type": type_, "asset": e.get("asset") or source,
                # `ts` is the event stamp the rest of the board sorts and hashes on: the
                # offset-aware instant when there is one, else the session date.
                "ts": clocks["event_ts"] or clocks["event_date"] or str(e.get("ts") or ""),
                "date_only": clocks["date_precision"] == alert_time.PRECISION_DATE,
                **{k: clocks[k] for k in
                   ("event_date", "event_ts", "source_asof", "recorded_at",
                    "board_date", "date_precision")},
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
        # UNAVAILABLE — not "zero alerts".  If this feed was carrying stress events,
        # treating its silence as calm is how an outage makes the board look safer.
        return _read(source, READ_UNAVAILABLE, [], f"{type(ex).__name__}: {ex}")
    if out:
        return _read(source, READ_OK, out)
    # Zero events is a legitimate answer for a transition-event store — but only if the
    # store is actually there.  No store yet is a different, disclosed thing.
    state, reason = _store_state(mod_obj) if mod_obj is not None else (READ_OK_ZERO, None)
    return _read(source, state, out, reason)


# ---------------------------------------------------------------------------
# MODELING v2 — persistence, lifecycle, storyline clustering, board read
# ---------------------------------------------------------------------------
# The v1 board deduplicated re-fires down to a single best instance, which threw
# away the fact that a flag firing every day for a week is stickier than a one-off.
# It also showed 60 disconnected rows with no board-level synthesis, so the two
# loudest-by-VOLUME feeds (single-name alt-data + theme rotation) buried the two
# most-important-by-CONSEQUENCE ones (credit / recession / the BTC risk regime).
#
# These helpers recover that information WITHOUT breaking the honesty culture:
#   • persistence + lifecycle are DESCRIPTIVE (a fire-count is a fact, not a
#     forecast).  They feed the DEMOTE-ONLY severity cap below as one corroborator,
#     so a persisting flag can RETAIN the engine's own prior band (decline a
#     demotion) — it can preserve, but never manufacture, priority above that prior.
#     No surface is ever raised above its hardcoded prior — Article-2 safe;
#   • the corroboration cap only ever DEMOTES a severity band (extends the #42
#     "cap a null emitter, never raise it" doctrine to the whole board), so no
#     surface gains conviction it didn't earn;
#   • storyline clustering + the board read are pure display groupings over the
#     already-ranked feed; they do not reorder it.

# (source, type) → storyline cluster id.  DISPLAY grouping only.
_CLUSTER = {
    # ---- risk-off STRESS spine (macro + bonds + commodity) ----
    ("bonds", "recession_risk"): "stress", ("bonds", "credit_band"): "stress",
    ("bonds", "uninversion"): "stress", ("bonds", "repo_stress"): "stress",
    ("bonds", "rates_vol"): "stress", ("bonds", "curve_regime"): "stress",
    ("bonds", "corr_regime"): "stress",
    ("macro", "hy_oas_widening"): "stress", ("macro", "ebp_widening"): "stress",
    ("macro", "nfci_tightening"): "stress", ("macro", "drawdown_risk_high"): "stress",
    ("macro", "capitulation_signal"): "stress", ("macro", "sahm_trigger"): "stress",
    ("macro", "conditions_recession_state_change"): "stress",
    ("commodity", "risk_regime"): "stress", ("commodity", "risk_extreme"): "stress",
    ("commodity", "price_shock"): "stress", ("commodity", "residual_shock"): "stress",
    # ---- REGIME shifts ----
    ("macro", "transition_state_change"): "regime", ("macro", "gex_flip_cross"): "regime",
    ("vector", "risk_regime"): "regime", ("vector", "impulse_warn_down"): "regime",
    ("vector", "impulse_warn_up"): "regime", ("vector", "leadership"): "regime",
    # ---- LIQUIDITY & rates plumbing ----
    ("macro", "net_liquidity_roc_flip"): "liquidity",
    # ---- SECTOR & THEME rotation ----
    ("themes", "theme_topping"): "rotation", ("themes", "theme_deteriorating"): "rotation",
    ("themes", "theme_emerging"): "rotation", ("themes", "reco_change"): "rotation",
    ("themes", "leadership_rotation"): "rotation",
    ("rotation", "rotation_emerging"): "rotation", ("rotation", "rotation_fading"): "rotation",
    ("rotation", "rotation_event"): "rotation",
    ("rotation", "entered_book"): "rotation", ("rotation", "left_book"): "rotation",
    ("oracle", "oracle_onset"): "rotation", ("oracle", "oracle_confirmed"): "rotation",
    ("oracle", "oracle_rollover"): "rotation", ("oracle", "oracle_two_sided"): "rotation",
    ("oracle", "oracle_regime"): "rotation",
    ("emergence", "narrative_forming"): "rotation",
    # ---- SINGLE-NAME unusual activity ----
    ("altdata", "convergence"): "single_name",
    ("demand", "demand_ahead"): "single_name", ("demand", "demand_at_risk"): "single_name",
    ("watchlist", "buy_zone_enter"): "single_name",
}
# cluster id → display metadata (icon, bilingual label, sort order).
CLUSTER_META = {
    "stress":      {"label": "Risk-off stress",       "label_zh": "风险规避压力", "icon": "🛑", "order": 0,
                    "gist": "credit, recession & rates plumbing under strain",
                    "gist_zh": "信用、衰退与利率体系承压"},
    "regime":      {"label": "Regime shift",           "label_zh": "机制转变",     "icon": "🧭", "order": 1,
                    "gist": "the market's underlying weather is changing",
                    "gist_zh": "市场的底层“天气”正在改变"},
    "liquidity":   {"label": "Liquidity & rates",      "label_zh": "流动性与利率", "icon": "💧", "order": 2,
                    "gist": "the tide of money into risk assets is turning",
                    "gist_zh": "流入风险资产的资金潮汐正在转向"},
    "rotation":    {"label": "Sector & theme rotation","label_zh": "板块与主题轮动", "icon": "🔄", "order": 3,
                    "gist": "leadership is handing off between themes",
                    "gist_zh": "领涨在主题之间交接"},
    "single_name": {"label": "Single-name flags",      "label_zh": "个股信号",     "icon": "🎯", "order": 4,
                    "gist": "unusual activity converging on individual tickers",
                    "gist_zh": "个股上出现多渠道异常活动汇聚"},
    "other":       {"label": "Other",                  "label_zh": "其他",         "icon": "•",  "order": 9,
                    "gist": "", "gist_zh": ""},
}


def cluster_of(source: str, type_: str) -> str:
    """Storyline cluster for an alert (display grouping only)."""
    return _CLUSTER.get((source, type_), "other")


# Bilingual maps for the small closed enum sets that appear in the board read +
# the backdrop strip (regime/latest.json states).  Unknown values fall through to
# the raw token so a new upstream state degrades to English, never crashes.
_CA_ZH = {"concentrated": "集中", "diversified": "分散", "converging": "趋同", "unknown": "未知"}
_BAND_ZH = {"low": "低", "moderate": "中等", "elevated": "偏高", "high": "高",
            "severe": "严重", "extreme": "极端", "none": "无"}
_NFCI_ZH = {"loose": "宽松", "easing": "趋松", "neutral": "中性", "tight": "收紧", "tightening": "趋紧"}
_QUAD_ZH = {"Goldilocks": "金发经济", "Reflation": "再通胀", "Inflation": "通胀",
            "Stagflation": "滞胀", "Deflation": "通缩", "Disinflation": "去通胀",
            "Growth": "增长", "Slowdown": "放缓", "Recovery": "复苏", "Contraction": "收缩"}


def enum_zh(kind: str, value):
    """Chinese label for a closed-enum backdrop value (verdict / band / nfci / quad),
    falling back to the raw token.  Exposed so the template can render the backdrop
    strip bilingually without duplicating the maps."""
    if value is None:
        return None
    return {"ca": _CA_ZH, "band": _BAND_ZH, "nfci": _NFCI_ZH, "quad": _QUAD_ZH}.get(kind, {}).get(value, value)


# RECURRENCE IS NOT PERSISTENCE (2026-08-20).
#
# An event log can prove how many times something fired, when it first fired, when it
# last fired, and the elapsed span between those.  It CANNOT, by itself, prove the
# condition was continuously active in between.  The old code computed
# ``streak_days = (last - first).days``, called that a streak, and then called anything
# with >=3 fires over >=3 days "persisting" — so Silver, which fired 3 times across 29
# days, was presented as a 29-day persistent condition.  Three sparse pokes are not a
# month-long state.
#
# So generic event history now earns only what it can prove — fire_count, first/last
# event, span_days, and the word "re-fired" — and the lifecycle vocabulary for a generic
# log is new / recurring / aging.  "persisting" (and its partner "fading") is reserved
# for a source that explicitly establishes current-state continuity by setting
# ``continuity_verified`` on the event.  No producer sets it today; the path exists so a
# real continuity contract can claim the word later without re-litigating this.
_RECUR_MIN_FIRES = 3
_RECUR_MIN_DAYS = 3


def _fire_board_date(e: dict) -> date | None:
    """The board day one raw fire belongs to (normalising on the fly if needed)."""
    bd = alert_time.parse_date(e.get("board_date"))
    if bd is not None:
        return bd
    return alert_time.parse_date(alert_time.normalize_event(e).get("board_date"))


def _fire_sort_key(e: dict) -> tuple:
    """Order fires without ever comparing a tz-aware stamp to a naive one.

    Since the time contract stopped stripping offsets, one group can hold both a session
    date ("2026-08-19") and an offset-aware instant ("2026-08-20T00:30:00+00:00"), and
    ``pd.Timestamp`` raises on that comparison.  We sort on the BOARD day first (the unit
    the board actually reasons in), then on the instant within the day where one exists.
    """
    bd = _fire_board_date(e) or date.min
    inst = alert_time.parse_instant(e.get("event_ts"))
    return (bd, inst.timestamp() if inst is not None else 0.0, str(e.get("ts") or ""))


def _recurrence(instances: list[dict]) -> dict:
    """Aggregate same-key raw fires into the facts an event log can actually prove.

    ``span_days`` is the elapsed board-day distance from the FIRST to the LAST fire.  It
    is deliberately NOT called a streak: nothing here shows the condition held in
    between.  ``continuity_verified`` is True only if a source explicitly says so.
    """
    ordered = sorted(instances, key=_fire_sort_key)
    first, last = ordered[0], ordered[-1]
    fd, ld = _fire_board_date(first), _fire_board_date(last)
    span = int((ld - fd).days) if (fd is not None and ld is not None) else 0
    return {"fire_count": len(instances),
            "first_event_at": str(first.get("ts") or ""),
            "last_event_at": str(last.get("ts") or ""),
            "first_board_date": fd.isoformat() if fd else None,
            "last_board_date": ld.isoformat() if ld else None,
            "span_days": span,
            "continuity_verified": any(bool(e.get("continuity_verified")) for e in instances)}


def lifecycle_of(fire_count: int, span_days: int, age_days: float | None,
                 continuity_verified: bool = False) -> str:
    """Descriptive lifecycle stage from the fire pattern (never a prediction).

    From a generic event log we can only claim:
      new       — it has fired ONCE, recently.  "New" is about when the thing FIRST
                  appeared, not when it last did: a flag that also fired 29 days ago is
                  not new, however fresh its latest firing is (measured 2026-08-20 — the
                  old rule read `age_days <= 2` off the LATEST fire and labelled 2-fire
                  29-day-old rotation rows "new" on the live board);
      recurring — it has fired more than once ("re-fired 3× across 29d").  That is a
                  count and an elapsed span, NOT a claim it held in between;
      aging     — a single older fire still inside the window.

    ``persisting`` / ``fading`` require ``continuity_verified`` — an explicit
    current-state contract from the source.  A gap-filled transition log never earns it.

    The count threshold for "re-fired" is the honest one — more than once.  The old 3
    fires / 3 days bar was inherited from the severity corroborator, and that corroborator
    is gone (see ``corroborated_severity``), so display no longer borrows its numbers.
    """
    fresh = age_days is not None and age_days <= 2   # an unknown date is never "fresh"
    repeated = fire_count > 1
    if continuity_verified and fire_count >= _RECUR_MIN_FIRES and span_days >= _RECUR_MIN_DAYS:
        return "persisting" if fresh else "fading"
    if repeated:
        return "recurring"
    return "new" if fresh else "aging"


def corroborated_severity(band: str, tier: str, ca_tag: str, validation: dict,
                          fire_count: int = 0, span_days: int = 0,
                          continuity_verified: bool = False) -> tuple[str, str | None]:
    """DEMOTE-ONLY severity cap: the engine severity word is a PRIOR that an alert
    must corroborate to keep.  An isolated, unvalidated, one-off flag should not sit
    at the same visual volume as a cross-asset-confirmed or backtested signal — so
    without ANY corroborator we step the band down one notch.

    RECURRENCE IS NOT CORROBORATION (2026-08-20).  This used to accept
    ``fire_count >= 3 and streak_days >= 3`` as evidence, which meant three sparse
    re-fires across a month could decline a demotion and hold a `major` band.  On a
    watch-tier alert that is 22 + 18 + 20 = 60 instead of 22 + 6 + 20 = 48 — a real
    ordering difference, and one that also clears the outbound push floor.  A gap-filled
    transition log cannot show a condition held, so it corroborates nothing.  Only
    SOURCE-VERIFIED continuity (``continuity_verified``) counts, and no producer sets
    that today.  ``fire_count`` / ``span_days`` are still accepted so callers need not
    change, and are still DISPLAYED — they are simply no longer authority.

    Still demote-only, so it remains Article-2 clean: no surface gains conviction it did
    not earn.  Returns (band, reason|None)."""
    if band == "minor":
        return band, None
    corroborated = (
        tier == "act"                                    # already true cross-asset weight
        or ca_tag == "confirm"                           # the tape agrees with it
        or validation.get("backtested") is True          # a measured edge backs the family
        # source-verified continuity ONLY — never bare recurrence
        or (continuity_verified and fire_count >= _RECUR_MIN_FIRES
            and span_days >= _RECUR_MIN_DAYS)
    )
    if corroborated:
        return band, None
    return {"critical": "major", "major": "minor"}[band], "uncorroborated"


def _scrub(text: str) -> str:
    """Strip upstream NaN/None artifacts from a display string (e.g. a bonds detail
    that reads 'crossed the crisis band at nan').  Display hygiene only."""
    if not text:
        return text
    for bad in (" at nan", " at None", " (nan)", " (None)", "报 nan", "，报 nan"):
        text = text.replace(bad, "")
    return text.replace("  ", " ").strip()


def coverage_report(reads: list[dict], context_state: str) -> dict:
    """What evidence this build could actually see.

    ``complete`` — every consequential family read, and the cross-asset backdrop read.
    ``partial``  — at least one consequential family (or the backdrop) is UNAVAILABLE, so
                   the board keeps showing the alerts it has but forfeits whole-tape
                   authority.  A feed with no store yet (``no_coverage``) is disclosed but
                   does NOT degrade the board: never having produced anything is a known
                   state, not a hole where evidence used to be.

    Reasons stay internal.  A user is told WHICH evidence family is missing, never a
    traceback.
    """
    sources = []
    for r in reads:
        meta = SOURCES.get(r["source"], {})
        sources.append({
            "source": r["source"],
            "label": meta.get("label", r["source"]),
            "label_zh": meta.get("label_zh", r["source"]),
            "state": r["state"],
            "events": len(r["events"]),
            "consequential": r["source"] in _CONSEQUENTIAL_SOURCES,
        })
    unavailable = [s for s in sources if s["state"] == READ_UNAVAILABLE]
    blocking = [s for s in unavailable if s["consequential"]]
    backdrop_missing = context_state == READ_UNAVAILABLE
    partial = bool(blocking) or backdrop_missing
    return {
        "state": "partial" if partial else "complete",
        "sources": sources,
        "unavailable": [s["label"] for s in unavailable],
        "unavailable_zh": [s["label_zh"] for s in unavailable],
        "blocking": [s["label"] for s in blocking],
        "blocking_zh": [s["label_zh"] for s in blocking],
        "no_coverage": [s["label"] for s in sources if s["state"] == READ_NO_COVERAGE],
        "context_state": context_state,
        "backdrop_missing": backdrop_missing,
        "n_unavailable": len(unavailable),
    }


def _board_read(kept: list[dict], ctx: dict, coverage: dict | None = None) -> dict:
    """A one-line synthesis of what the whole board is saying — a DESCRIPTIVE read
    of the current alert mix plus the documented backdrop, explicitly NOT a forecast
    and never a P(risk-off).  Transparent: the driver counts are shown.

    PARTIAL COVERAGE (2026-08-20).  The pressure score is computed from what survived
    the read, so a dead feed used to be indistinguishable from a quiet one — and if the
    dead feed held stress events, losing it LOWERED the score and produced a more
    constructive headline.  An outage could make the product look safer.  So when a
    consequential family or the cross-asset backdrop is unavailable we do not publish a
    whole-tape verdict at all: stance becomes ``partial``, the score becomes None, and the
    line says which evidence is missing.  We do NOT substitute a conservative fake score
    either — unknown stays unknown.  The ranked feed below it is unaffected and still
    usable; only the claim to read the WHOLE tape is withdrawn.
    """
    stress = [a for a in kept if a.get("cluster") == "stress"]
    stress_confirm = sum(1 for a in stress if a.get("cross_asset_tag") == "confirm")
    act = [a for a in kept if a.get("tier") == "act"]
    crit = [a for a in kept if a.get("severity") == "critical"]
    ca = (ctx.get("cross_asset") or {}).get("verdict")
    rb = ctx.get("risk_backdrop") or {}
    # transparent, bounded pressure gauge (display only; not a probability)
    score = min(100, len(stress) * 8 + stress_confirm * 6 + len(act) * 10 + len(crit) * 6)
    if ca == "concentrated":
        score = min(100, score + 8)
    if score >= 45:
        stance, stance_zh = "risk-off", "偏防御"
    elif score >= 20:
        stance, stance_zh = "mixed", "喜忧参半"
    else:
        stance, stance_zh = "constructive", "偏进攻"
    drivers, drivers_zh = [], []
    if act:
        drivers.append(f"{len(act)} act-tier call{'s' if len(act) != 1 else ''}")
        drivers_zh.append(f"{len(act)} 条执行级信号")
    if stress:
        d = f"{len(stress)} risk-off stress alert{'s' if len(stress) != 1 else ''}"
        if stress_confirm:
            d += f" ({stress_confirm} cross-asset-confirmed)"
        drivers.append(d)
        drivers_zh.append(f"{len(stress)} 条风险规避压力警报" +
                          (f"（{stress_confirm} 条获跨资产佐证）" if stress_confirm else ""))
    if ca:
        # full-domain map — the verdict can be concentrated / diversified / converging /
        # unknown (engine.cross_asset); a binary 'concentrated vs 分散' mislabels the last two.
        article = "an" if ca == "unknown" else "a"
        drivers.append(f"{article} {ca} tape")
        drivers_zh.append(f"盘面{_CA_ZH.get(ca, ca)}")
    if rb.get("recession_band"):
        drivers.append(f"recession risk {rb['recession_band']}")
        drivers_zh.append(f"衰退风险 {_BAND_ZH.get(rb['recession_band'], rb['recession_band'])}")
    cov = coverage or {"state": "complete"}
    if cov.get("state") == "partial":
        # WITHDRAW the whole-tape verdict. Not a downgrade of it, not a pessimistic
        # substitute for it — there is no honest verdict to publish from a partial read.
        missing = list(cov.get("blocking") or cov.get("unavailable") or [])
        missing_zh = list(cov.get("blocking_zh") or cov.get("unavailable_zh") or [])
        if cov.get("backdrop_missing"):
            missing.append("cross-asset backdrop")
            missing_zh.append("跨资产背景")
        n = len(missing)
        lead = (f"Partial tape read — {n} evidence "
                f"{'family is' if n == 1 else 'families are'} unavailable "
                f"({', '.join(missing)})")
        lead_zh = f"盘面读数不完整 — {n} 类证据缺失（{'、'.join(missing_zh)}）"
        tail = (" The alerts below are what we CAN see; this is not a complete read of "
                "the tape, so no overall stance is shown.")
        tail_zh = "以下警报仅为我们能够读到的部分；这不是对整体盘面的完整解读，因此不给出总体立场。"
        seen = (" Of the evidence we do have: " + ", ".join(drivers) + "."
                if drivers else "")
        seen_zh = ("已读到的部分：" + "、".join(drivers_zh) + "。" if drivers_zh else "")
        return {"stance": "partial", "stance_zh": "证据不完整", "score": None,
                "coverage": "partial", "missing": missing, "missing_zh": missing_zh,
                "subset_drivers": drivers,
                "one_liner": lead + "." + seen + tail,
                "one_liner_zh": lead_zh + "。" + seen_zh + tail_zh}
    lead = {"risk-off": "The tape is leaning risk-off",
            "mixed": "The tape is mixed",
            "constructive": "The tape is broadly constructive"}[stance]
    lead_zh = {"risk-off": "整体盘面偏防御",
               "mixed": "整体盘面喜忧参半",
               "constructive": "整体盘面偏进攻"}[stance]
    one = lead + (" — " + ", ".join(drivers) + "." if drivers else ".")
    one_zh = lead_zh + ("：" + "、".join(drivers_zh) + "。" if drivers_zh else "。")
    return {"stance": stance, "stance_zh": stance_zh, "score": score,
            "coverage": "complete", "missing": [], "missing_zh": [],
            "drivers": drivers, "one_liner": one, "one_liner_zh": one_zh}


def _volume_context(raw: list[dict], today: date, days: int) -> dict:
    """How busy the last week has been vs the window's own trailing weekly rate — so
    a user can tell a genuinely loud week from ambient chatter.  Descriptive stat.

    Counted in BOARD days: a fire stamped 2026-08-20T00:30Z belongs to the Aug-19 desk
    session, so it lands in the same bucket the card shows."""
    if not raw:
        return {}
    # callers historically passed a pd.Timestamp here; accept either and reason in dates
    today = alert_time.parse_date(today) or today
    fires = [d for d in (_fire_board_date(e) for e in raw) if d is not None]
    if not fires:
        return {}
    last7 = sum(1 for t in fires if 0 <= (today - t).days <= 7)
    weeks = max(1.0, days / 7.0)
    baseline_wk = len(fires) / weeks
    ratio = (last7 / baseline_wk) if baseline_wk > 0 else 1.0
    if ratio >= 1.25:
        state, state_zh = "busier", "更繁忙"
    elif ratio <= 0.75:
        state, state_zh = "quieter", "更平静"
    else:
        state, state_zh = "normal", "正常"
    return {"last_7d": last7, "baseline_weekly": round(baseline_wk, 1),
            "ratio": round(ratio, 2), "state": state, "state_zh": state_zh,
            "total_in_window": len(fires)}


def _storylines(kept: list[dict]) -> list[dict]:
    """Collapse the ranked feed into a handful of storyline cards — one per cluster —
    so the board reads as 'a few stories', not 60 disconnected rows.  Pure grouping
    over the already-ranked feed; it does NOT reorder the feed itself."""
    groups: dict[str, list[dict]] = {}
    for a in kept:
        groups.setdefault(a.get("cluster", "other"), []).append(a)
    out: list[dict] = []
    for cl, items in groups.items():
        meta = CLUSTER_META.get(cl, CLUSTER_META["other"])
        items = sorted(items, key=lambda x: (x["priority"], x["ts"]), reverse=True)
        top = items[0]
        assets = []
        for x in items:
            a = str(x.get("asset") or "")
            if a and a not in (x["source"], "macro", "rates", "vector") and len(a) <= 6 and a not in assets:
                assets.append(a)
        out.append({
            "cluster": cl, "label": meta["label"], "label_zh": meta["label_zh"],
            "icon": meta["icon"], "gist": meta["gist"], "gist_zh": meta["gist_zh"],
            "order": meta["order"], "count": len(items),
            "act": sum(1 for x in items if x["tier"] == "act"),
            "critical": sum(1 for x in items if x["severity"] == "critical"),
            "recurring": sum(1 for x in items if x.get("lifecycle") == "recurring"),
            "persisting": sum(1 for x in items if x.get("lifecycle") == "persisting"),
            "top_headline": top["headline"], "top_headline_zh": top.get("headline_zh") or top["headline"],
            "top_priority": top["priority"], "top_source": top["source"],
            "assets": assets[:10],
        })
    # most consequential storyline first: any act-tier, then criticals, then top priority
    out.sort(key=lambda s: (s["act"] > 0, s["critical"], s["top_priority"], s["count"]),
             reverse=True)
    return out


def build_triage(days: int = 30, today: date | None = None,
                 per_source_context_cap: int = 6, max_items: int = 60,
                 now: datetime | None = None) -> dict:
    """Assemble the full Alert Command Center payload. Pure assembler, graceful.

    days                    look-back window (the board shows what is *live now*)
    per_source_context_cap  cap context-tier alerts per source so a noisy feed
                            (forex per-pair) can't drown the actionable ones
    max_items               global cap after ranking
    today                   explicit BOARD day override (tests / replay)
    now                     injected wall clock; the board day is derived from it in
                            America/New_York.  Used only when ``today`` is not given.

    BOARD DAY: this is a US cross-asset desk, so "today" is the New York day, not UTC's.
    At 2026-08-20T00:30Z New York is still 2026-08-19 20:30 — the board must not have
    rolled over.  Everything downstream (recency points, "today / 1d ago", new_today, the
    catalyst countdown, the 7-day fire volume) reads THIS date.
    """
    today = today or alert_time.board_date(now)
    cutoff = today - timedelta(days=days)
    reg = _registry_index()
    rule_sc = _rule_scorecard()
    ctx = _load_context()
    ca_verdict = (ctx.get("cross_asset") or {}).get("verdict")

    # Every reader returns a TYPED result so a crashed feed is recorded as missing
    # evidence rather than silently folded into "no alerts".  Each CALL is additionally
    # wrapped: the readers guard their own internals, but this module's contract is that
    # a bad feed degrades a section and never fails the build, so a reader that raises at
    # the boundary must still land as `unavailable` rather than taking the page down.
    def _safe(source: str, fn, *args) -> dict:
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            log.warning("triage: %s reader raised at the boundary (%s)", source, e)
            return _read(source, READ_UNAVAILABLE, [], f"{type(e).__name__}: {e}")

    reads: list[dict] = [
        _safe("macro", _macro_raw, today, cutoff),
        _safe("bonds", _jsonl_raw, "bonds", today, cutoff, _BONDS_TIER),
        _safe("forex", _jsonl_raw, "forex", today, cutoff, _FOREX_TIER),
        _safe("vector", _jsonl_raw, "vector", today, cutoff, {}),   # tier inline on events
        _safe("commodity", _jsonl_raw, "commodity", today, cutoff, _COMMODITY_TIER),
        _safe("themes", _jsonl_raw, "themes", today, cutoff, _THEMES_TIER),
        _safe("emergence", _jsonl_raw, "emergence", today, cutoff, _EMERGENCE_TIER),
        _safe("altdata", _jsonl_raw, "altdata", today, cutoff, _ALTDATA_TIER),
        _safe("demand", _jsonl_raw, "demand", today, cutoff, _DEMAND_TIER),
        _safe("rotation", _jsonl_raw, "rotation", today, cutoff, _ROTATION_TIER),
        _safe("oracle", _jsonl_raw, "oracle", today, cutoff, _ORACLE_TIER),
        _safe("watchlist", _jsonl_raw, "watchlist", today, cutoff, _WATCHLIST_TIER),
    ]
    coverage = coverage_report(reads, ctx.get("_state", READ_UNAVAILABLE))
    if coverage["state"] == "partial":
        log.warning("triage: PARTIAL coverage — unavailable: %s (backdrop_missing=%s)",
                    coverage["blocking"] or coverage["unavailable"],
                    coverage["backdrop_missing"])
    raw: list[dict] = [e for r in reads for e in r["events"]]

    # ---- recurrence-aware grouping (v2) ------------------------------------
    # Collapse re-fires of the same (source, type, asset) BEFORE enriching, but keep
    # the fire pattern instead of discarding it.  The representative is the newest
    # fire (freshest headline + timestamp); its recurrence stats summarise the rest.
    # Those stats are DISPLAY facts, not authority: see corroborated_severity().
    # A row claiming a board day AFTER today is either a scheduled catalyst that leaked
    # into the fired-alert feed or a clock defect.  Either way it is not evidence that
    # something HAS happened, so it is quarantined out of the ranked board rather than
    # handed the top of it by the recency term.
    quarantined = [a for a in raw if alert_time.is_future(a, today)]
    if quarantined:
        log.warning("triage: quarantined %d future-dated alert(s): %s", len(quarantined),
                    sorted({f"{a['source']}:{a['type']}" for a in quarantined}))
    raw = [a for a in raw if not alert_time.is_future(a, today)]

    groups: dict[tuple, list[dict]] = {}
    for a in raw:
        groups.setdefault((a["source"], a["type"], a.get("asset") or a["source"]), []).append(a)

    enriched: list[dict] = []
    for key, instances in groups.items():
        rec = _recurrence(instances)
        rep = max(instances, key=_fire_sort_key)                    # newest fire
        tier = rep["tier"]
        band = severity_band(tier, rep["raw_sev"])
        # #42: measured-IC severity — the hardcoded band is a prior; a spine-measured null /
        # wrong-sign emitter is capped so it can't outrank validated risk-off signals.
        band, ic_note = ic_severity_cap(rep["source"], rep["type"], band)
        ca_tag = cross_asset_tag(rep["type"], ca_verdict)
        validation = _validation(rep["source"], rep["type"], rep.get("edge", ""),
                                 rep.get("edge_zh", ""), reg, rule_sc, rep.get("detail", ""))
        # v2: DEMOTE-ONLY corroboration cap — an isolated, unvalidated one-off can't
        # sit at the same volume as a confirmed / backtested signal.  Bare recurrence is
        # NOT a corroborator (2026-08-20): a transition log cannot show a state held.
        band, corr_reason = corroborated_severity(
            band, tier, ca_tag, validation, rec["fire_count"], rec["span_days"],
            rec["continuity_verified"])
        # Age is in BOARD days off the representative (latest) fire.  None when that fire
        # has no usable event time — then no recency credit and no "today" wording.
        rep_board = rec["last_board_date"]
        age = alert_time.age_days({"board_date": rep_board}, today)
        score, comp = priority(tier, band, age, ca_tag)
        act_en, act_zh = action_for(tier, band, ca_tag)
        life = lifecycle_of(rec["fire_count"], rec["span_days"], age,
                            rec["continuity_verified"])
        smeta = SOURCES.get(rep["source"], {})
        # Stable content-hash ID: (source, type, asset, BOARD date).  Truncated to 12 hex
        # chars — collision-probability negligible for the ~60-alert board.  Keyed on the
        # board date so the id names the day the card shows; a row whose event date this
        # repair corrected (rotation) legitimately re-keys, everything else is unchanged.
        _id_key = (f"{rep['source']}|{rep['type']}|{rep.get('asset', '')}|"
                   f"{rep_board or str(rep.get('ts') or '')[:10]}")
        alert_id = hashlib.sha256(_id_key.encode()).hexdigest()[:12]
        enriched.append({
            **rep,
            "headline": _scrub(rep.get("headline", "")),
            "headline_zh": _scrub(rep.get("headline_zh", "")),
            "detail": _scrub(rep.get("detail", "")),
            "detail_zh": _scrub(rep.get("detail_zh", "")),
            "alert_id": alert_id,
            "severity": band,
            "age_days": None if age is None else int(age),
            "board_date": rep_board,
            "date_precision": rep.get("date_precision", alert_time.PRECISION_UNKNOWN),
            "priority": score, "priority_components": comp,
            "cross_asset_tag": ca_tag,
            "action": act_en, "action_zh": act_zh,
            "cluster": cluster_of(rep["source"], rep["type"]),
            "lifecycle": life,
            # RECURRENCE facts — what an event log can prove.  `span_days` is elapsed
            # first-to-last distance, NOT a streak: nothing here shows the condition
            # held in between, which is why the card says "re-fired N× across Md".
            "fire_count": rec["fire_count"], "span_days": rec["span_days"],
            "first_event_at": rec["first_event_at"], "last_event_at": rec["last_event_at"],
            "first_board_date": rec["first_board_date"],
            "last_board_date": rec["last_board_date"],
            "continuity_verified": rec["continuity_verified"],
            "severity_capped": corr_reason,
            "source_label": smeta.get("label", rep["source"]),
            "source_label_zh": smeta.get("label_zh", rep["source"]),
            "source_icon": smeta.get("icon", "•"),
            "link": rep.get("link") or (smeta.get("page", "macro.html") + (rep.get("anchor") or "")),
            "validation": validation,
            "ic_severity": ic_note,
        })

    enriched.sort(key=lambda x: (x["priority"], x["ts"]), reverse=True)

    # keep every act/watch; cap the context-tier long tail per source
    seen_ctx: dict[str, int] = {}
    kept: list[dict] = []
    for a in enriched:
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
        # `recurring` is what a generic event log can prove.  `persisting` is kept as a
        # separate counter and only a source-verified continuity contract can fill it —
        # today it is always 0, which is the honest number.
        "recurring": sum(1 for a in kept if a["lifecycle"] == "recurring"),
        "persisting": sum(1 for a in kept if a["lifecycle"] == "persisting"),
        "new_today": sum(1 for a in kept if a["age_days"] == 0),
        "date_unknown": sum(1 for a in kept if a["board_date"] is None),
        "by_source": {s: sum(1 for a in kept if a["source"] == s) for s in SOURCES},
        "by_cluster": {c: sum(1 for a in kept if a["cluster"] == c) for c in CLUSTER_META},
        "backtested": sum(1 for a in kept if a["validation"].get("backtested") is True),
        "total_fires_in_window": sum(a["fire_count"] for a in kept),
    }

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        # The desk's day, in New York.  Distinct from generated_utc on purpose: one is
        # when we built the page, the other is the session the board is reading.
        "board_date": today.isoformat(),
        "board_tz": alert_time.BOARD_TZ_NAME,
        "quarantined": len(quarantined),
        "asof": ctx.get("asof"),
        "window_days": days,
        "regime": ctx.get("regime") or {},
        "cross_asset": ctx.get("cross_asset") or {},
        "risk_backdrop": ctx.get("risk_backdrop") or {},
        "events": _events(today),
        "summary": summary,
        # What evidence this build could see.  `coverage.state == "partial"` means the
        # board below is a partial read and the whole-tape verdict is withdrawn.
        "coverage": coverage,
        "coverage_state": coverage["state"],
        "board_read": _board_read(kept, ctx, coverage),
        "volume": _volume_context(raw, today, days),
        "storylines": _storylines(kept),
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
    # M3 escalation organ (PR-3): persistent NW health degradation detector
    "nw_health": "push_sent_nw_health.jsonl",
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
