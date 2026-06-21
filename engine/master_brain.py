"""Master brain — cross-asset macro SYNTHESIS (LLM Tier-B).

LEAF · GATED · DEFAULT-OFF · RESEARCH/CONTEXT-ONLY. Reads the DETERMINISTIC
outputs of the dashboards and asks a reasoning LLM to synthesize the picture a
single panel can't. Three LENSES share one engine:
  • macro — the cross-asset read across every dashboard (macro/China/HK/commodity/
    forex/BTC) + the catalyst digest  → data/regime/master_brief.json
  • china — a China & Hong-Kong focused read (US macro / dollar / global liquidity /
    commodities as backdrop)          → data/regime/china_brief.json
  • btc   — a Bitcoin focused read (cycle / valuation / leverage / on-chain / ETF
    flows / macro-liquidity backdrop)  → data/regime/btc_brief.json
Each writes a SEPARATE artifact and a site/ copy the dashboard panel fetches.

This is the analyst's morning note. It NEVER feeds a score, signal, or allocation;
nothing in the scoring path imports it. It READS the engine's outputs and writes a
SEPARATE artifact. Every public function returns plain data or None and never
raises into the pipeline.

Runs on DeepSeek V4 Pro via its Anthropic-compatible endpoint by default — one
config line (`llm_model` / `llm_base_url` / `api_key_env`) swaps it to Claude Opus.
NOTE: unlike the Tier-A digest (public docs only), the brain necessarily sends the
user's DERIVED market-state summary (regime labels, scores, conflicts — NOT
holdings or watchlist composition) to the provider. Swap to a first-party model in
config if that matters.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config
from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser (leaf util)

log = logging.getLogger(__name__)

DEFAULT_THESIS = (
    "Liquidity rotates across risk assets in a rough sequence — US large-cap "
    "semis -> software/growth -> ex-US (China/HK) -> crypto — as net liquidity "
    "expands, and unwinds in reverse when it contracts. Treat this as a HYPOTHESIS "
    "to test against the data, not a fact."
)

CHINA_THESIS = (
    "China equity risk appetite is driven mainly by DOMESTIC policy & liquidity "
    "(PBoC stance, credit impulse, fiscal) rather than earnings, and A-shares "
    "MEAN-REVERT over short horizons — short-term reversal is the robust effect "
    "while momentum is unreliable, so treat 'relative-strength leaders' as EXTENDED "
    "rather than as continuation. Hong Kong additionally rides global risk appetite "
    "and the US dollar far more than mainland A-shares. Treat this as a HYPOTHESIS "
    "to test against the data, not a fact."
)

BTC_THESIS = (
    "Bitcoin is the long-duration, high-beta tail of the GLOBAL LIQUIDITY cycle — "
    "it leads risk assets higher when net liquidity / global M2 expand and unwinds "
    "hardest when they contract; within that, leverage & funding extremes and "
    "valuation / cycle position (MVRV, halving clock) gate the risk-reward. Treat "
    "this as a HYPOTHESIS to test against the data, not a fact."
)

DISCLAIMER_TEXT = (
    "Context only — not a signal. This is an AI-generated SYNTHESIS of the "
    "dashboards' own deterministic outputs. It does not feed any score, signal or "
    "allocation, and it can be wrong or overconfident. Use it as a research read; "
    "verify every claim against the underlying dashboard it cites. Effective sample "
    "sizes on macro regimes are small — treat cross-asset 'reads' as odds, not "
    "forecasts."
)

# Shared output contract + tail every lens reuses, so the three system prompts and
# the client renderer stay identical bar the domain framing.
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  summary: string — one-line TL;DR of the read.\n"
    "  regime_read: string — 1-2 short paragraphs: where we are.\n"
    "  conflicts: array of strings — each a specific signal conflict + what it implies.\n"
    "  rotation_check: string — is reality tracking the working thesis? where it diverges.\n"
    "  transmission: array of strings — key second-order chains to watch.\n"
    "  watch_items: array of strings — what would change this read / what to watch next.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)

MASTER_SYSTEM_TMPL = (
    "You are a senior cross-asset macro strategist writing a SHORT morning brief for "
    "a solo top-down trader. You are given the trader's OWN deterministic dashboard "
    "outputs (already computed, validated signals) across macro regime, China, Hong "
    "Kong, commodities, FX, BONDS (the leading-family credit / curve / rates-vol / "
    "sovereign read), and Bitcoin, plus an optional FOMC catalyst digest. Your job is "
    "SYNTHESIS across them — not to recompute or invent numbers.\n\n"
    "Rules:\n"
    "- Use ONLY the provided state. Never fabricate a level, score, or signal. If "
    "something isn't in the state, say it's not available.\n"
    "- Your value is the CROSS-ASSET view: the unified regime read, where signals "
    "CONFLICT (e.g. risk-on FX vs a cautious macro-risk gauge) and what that implies, "
    "and second-order transmission chains worth watching.\n"
    "- Use the `bonds` block and `cross_asset_confirm` as the LEADING-FAMILY cross-check: "
    "state plainly whether bonds + FX CONFIRM or DIVERGE from the equity regime, and lean "
    "on the bond `drivers_for` hand-off for what bonds imply for FX / commodities / BTC / "
    "equities. Be honest about lead-lag: only credit/EBP and the curve (NTFS) have a "
    "defensible — and noisy — LEADING horizon; rates-vol-vs-VIX, the dollar/EM-FX risk-off "
    "read and FX carry are COINCIDENT confirmation / fragility gauges, and the stock-bond "
    "correlation is a slow regime descriptor. Do NOT claim bonds 'predict' an equity move. "
    "A `cross_asset_confirm` divergence is an attention flag, not a forecast.\n"
    "- Use `rate_inflation_transmission` for the rate/inflation backdrop: state the rates "
    "regime, the inflation read (core PCE vs the 2% target) and whether expectations are "
    "anchored, then name which assets it is a current headwind / tailwind for and which "
    "causal chains are active. The coefficients are MEASURED forward IC but `scored` is "
    "false on purpose — the gate found no leg robust enough to time returns, so frame it "
    "as RISK (which assets are pressured), never as a return forecast.\n"
    "- The nested `yield_curve` is the curve read: state the regime (bull/bear × steepener/"
    "flattener) and its Fed-cycle phase, the recession-dashboard risk (n flags from the "
    "near-term forward spread / 3m10y probit / un-inversion / TP-adjusted slope), the policy "
    "stance, and the curve's style tilt (value vs growth, size). Display-only context — the "
    "curve is REACTIVE; narrate the backdrop, never call it a timing signal.\n"
    "- OPEN with the dominant driver in `macro.market_drivers` when one is present — "
    "name it, the evidence, and what would invalidate it. It is a DETERMINISTIC "
    "cross-asset attribution: narrate it, do not recompute it. If it reads 'mixed' or "
    "'quiet', say so plainly rather than inventing a driver.\n"
    "- If `fed_stance` is present, anchor the rate read with the EXPLICIT Fed reaction "
    "function (hawkish/neutral/dovish) + the market-vs-Fed gap — a display-only read off "
    "the implied path + statement guidance (reactive, not a forecast). If `policy_intel` "
    "is present, factor the interest-driven (realpolitik) Fed/Admin thesis and the "
    "targeted-vs-starved capital rotation into your regime_read and rotation_check, "
    "honoring its FACT/INFERENCE/PRIOR labels — never trade a PRIOR or THEORY as fact.\n"
    "- Evaluate the trader's working rotation thesis against the actual state; say "
    "explicitly where reality tracks it and where it diverges.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Give the read and what to watch.\n"
    "- Be honest about uncertainty and small samples. Flag conflicts rather than "
    "papering over them. Cite which dashboard supports each claim.\n\n"
    "Working rotation thesis to test:\n{thesis}\n\n"
    + _SCHEMA_TAIL
)

CHINA_SYSTEM_TMPL = (
    "You are a senior China & Hong-Kong equity strategist writing a SHORT brief for a "
    "solo top-down trader. You are given the trader's OWN deterministic dashboard "
    "outputs: the China A-share regime (growth/inflation quadrant, PBoC liquidity "
    "overlay, business-cycle tag, sector relative strength, key ratios incl. "
    "USD/CNY), the Hong-Kong regime (its global-risk score, the HKD peg state, sector "
    "RS), and a compact US-macro / commodity / FX BACKDROP. Your job is SYNTHESIS — "
    "not to recompute or invent numbers.\n\n"
    "Rules:\n"
    "- Use ONLY the provided state. Never fabricate a level, score, or signal. If "
    "something isn't in the state, say it's not available.\n"
    "- Centre the read on CHINA and HONG KONG; use the US-macro / dollar / global-"
    "liquidity / commodity backdrop only to explain what is pushing on them.\n"
    "- China A-shares MEAN-REVERT over short horizons — frame relative-strength "
    "leaders as potentially EXTENDED, not as guaranteed continuation, and call out "
    "deep-pullback names as the higher-odds setups. Note where Hong Kong is diverging "
    "from the mainland because of global risk or the dollar.\n"
    "- Surface where signals CONFLICT (e.g. easing PBoC liquidity vs a weak growth "
    "score, or strong sector RS vs a late-cycle tag) and what that implies.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Give the read and what to watch.\n"
    "- Be honest about uncertainty and small samples. Cite which panel supports each "
    "claim.\n\n"
    "Working thesis to test:\n{thesis}\n\n"
    + _SCHEMA_TAIL
)

BTC_SYSTEM_TMPL = (
    "You are a senior crypto & macro strategist writing a SHORT brief on BITCOIN for "
    "a solo trader. You are given the trader's OWN deterministic Bitcoin-Vector "
    "outputs: the composite risk regime & optimal allocation, momentum/structure, "
    "the halving-cycle position, valuation (MVRV-Z, NUPL, Mayer, reserve risk), "
    "leverage & positioning (open interest, funding, basis, CME CoT), options "
    "structure (DVOL, skew, put/call, gamma), on-chain demand (Coinbase premium, "
    "SSR, miners), spot-ETF flows, and the macro-liquidity backdrop (net liquidity, "
    "global M2, real yields, DXY, VIX, cross-asset correlations). Your job is "
    "SYNTHESIS across these layers — not to recompute or invent numbers.\n\n"
    "Rules:\n"
    "- Use ONLY the provided state. Never fabricate a level, score, or signal. If "
    "something isn't in the state, say it's not available.\n"
    "- Centre the read on BITCOIN: tie the cycle/valuation position to the liquidity "
    "backdrop and to positioning/leverage. Flag when valuation, leverage and flows "
    "DISAGREE (e.g. cheap MVRV but crowded funding, or strong ETF flows into a "
    "late-cycle valuation).\n"
    "- Evaluate the working liquidity thesis against the actual state; say where "
    "reality tracks it and where it diverges.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system already "
    "sets the allocation. Give the read and what to watch.\n"
    "- Be honest about uncertainty and small samples (few crypto cycles). Cite which "
    "layer supports each claim.\n\n"
    "Working liquidity thesis to test:\n{thesis}\n\n"
    + _SCHEMA_TAIL
)

_BRIEF_FIELDS = ("summary", "regime_read", "conflicts", "rotation_check",
                 "transmission", "watch_items", "confidence")


def _cfg() -> dict:
    return config.load().get("master_brain", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# state gathering — compact summaries of each dashboard's deterministic output
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


def _brief_age_days(prev: dict | None) -> float | None:
    """Age in days of a previously-generated brief, from its `generated_at`. Returns
    None when missing/unparseable so the caller treats the brief as DUE (regenerate).
    Used by the regenerate-every-N-days interval gate in run()."""
    if not isinstance(prev, dict):
        return None
    ts = prev.get("generated_at")
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        gen = datetime.fromisoformat(ts)
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - gen).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def _leg(x):
    """Compact a conditions leg dict down to its headline fields."""
    if isinstance(x, dict):
        slim = {k: x.get(k) for k in ("label", "state", "value", "score", "pctile") if k in x}
        return slim or x
    return x


def _macro_summary(m: dict) -> dict:
    cond = m.get("conditions") or {}
    dis = m.get("dislocation") or {}
    mr = m.get("macro_risk") or {}
    pb = m.get("playbook") or {}
    dial = pb.get("dial")
    mdr = m.get("market_drivers") or {}
    drivers = None
    if mdr.get("verdict") not in (None, "unknown"):
        drivers = {"primary": mdr.get("primary_label"), "direction": mdr.get("direction"),
                   "verdict": mdr.get("verdict"), "confidence": mdr.get("confidence"),
                   "evidence": mdr.get("evidence"), "invalidation": mdr.get("invalidation")}
    return {
        "date": m.get("date"), "quad": m.get("quad"), "quad_name": m.get("quad_name"),
        "label": m.get("label"),
        "growth_score": m.get("growth_score"), "inflation_score": m.get("inflation_score"),
        "confidence": m.get("confidence"),
        "liquidity_overlay": m.get("liquidity_overlay"), "cycle_tag": m.get("cycle_tag"),
        "transition_state": m.get("transition_state"),
        "macro_risk": {"score": mr.get("score"), "label": mr.get("label")},
        "conditions": {k: _leg(v) for k, v in cond.items()} if isinstance(cond, dict) else None,
        "dislocation": {"verdict": dis.get("verdict"), "put_state": dis.get("put_state"),
                        "headline": dis.get("headline"),
                        "catalyst_narrative": dis.get("catalyst_narrative")},
        "playbook": {"posture": pb.get("posture"),
                     "dial_score": dial.get("score") if isinstance(dial, dict) else dial},
        "market_drivers": drivers,
    }


def _macro_backdrop(m: dict | None) -> dict | None:
    """A SLIM macro summary for the focused (china/btc) lenses — regime + risk +
    posture only, no full conditions block (that's noise for a non-US read)."""
    if not m:
        return None
    mr = m.get("macro_risk") or {}
    pb = m.get("playbook") or {}
    return {
        "date": m.get("date"), "quad": m.get("quad"), "quad_name": m.get("quad_name"),
        "growth_score": m.get("growth_score"), "inflation_score": m.get("inflation_score"),
        "liquidity_overlay": m.get("liquidity_overlay"),
        "macro_risk": {"score": mr.get("score"), "label": mr.get("label")},
        "playbook_posture": pb.get("posture"),
    }


def _bonds_backdrop(root: Path | None = None) -> dict | None:
    """Bond-health backdrop for the cross-asset brain — the INDEPENDENT bond reads
    (cycle clock, credit / curve / rates-vol / sovereign states, the `drivers_for`
    hand-off built for exactly this). Deliberately EXCLUDES the bond contract's
    recession_risk / drawdown_risk / stock_bond_corr numbers, which are byte-identical
    to the macro `conditions` the brain already has (the bonds engine reuses
    engine.conditions) — passing them would double-count."""
    root = Path(root) if root else config.ROOT
    b = _read_json(root / "data/bonds/bond_health.json")
    if not b:
        return None
    p = b.get("pillars") or {}

    def gp(*ks):
        cur = p
        for k in ks:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur

    return {
        "as_of": b.get("as_of"),
        "health_score": b.get("health_score"), "health_label": b.get("health_label"),
        "cycle_phase": b.get("cycle_phase"), "verdict": b.get("verdict_en"),
        "curve": {"taxonomy": gp("curve", "move_taxonomy"), "inverted": gp("curve", "inverted"),
                  "ntfs": gp("curve", "ntfs"), "uninversion_alarm": gp("curve", "uninversion_alarm")},
        "credit": {"distress_band": gp("credit", "distress_band"),
                   "direction": gp("credit", "direction"), "hy_oas": gp("credit", "hy_oas"),
                   "ebp": gp("credit", "ebp")},
        "real_inflation": {"real_10y": gp("real_inflation", "real_10y"),
                           "breakeven_5y5y": gp("real_inflation", "breakeven_5y5y"),
                           "term_premium": gp("real_inflation", "term_premium")},
        "stress": {"move_band": gp("stress", "move_band"),
                   "move_leads_vix": gp("stress", "move_leads_vix"),
                   "repo_stress": gp("stress", "repo_stress")},
        "stock_bond_corr_regime": gp("cross_asset", "regime"),
        "hedge_working": gp("cross_asset", "hedge_working"),
        "sovereign": {"frag_state": gp("sovereign", "frag_state"),
                      "jgb_state": gp("sovereign", "jgb_state")},
        "alarms": b.get("alarms") or [],
        "drivers_for": b.get("drivers_for"),
    }


def _confirm_summary(macro: dict | None) -> dict | None:
    """Compact cross-asset CONFIRMATION read (bonds + FX vs the equity regime) for the
    brain — the verdict + headline + the engine's own `to_brain` payload."""
    c = (macro or {}).get("cross_asset_confirm")
    if not isinstance(c, dict) or c.get("verdict") in (None, "unknown"):
        return None
    out = {"verdict": c.get("verdict"), "headline": c.get("headline_en"),
           "agree_pct": c.get("agree_pct")}
    tb = c.get("to_brain")
    if isinstance(tb, dict):
        out.update(tb)
    return out


_BTC_SMALL_COLS = ("composite_state", "risk_regime", "momentum", "mvrv_z",
                   "funding_z", "net_liquidity_bn", "macro_regime")

# Richer set for the BTC-focused lens — every layer of the vector, all scalar.
_BTC_RICH_COLS = (
    "composite_state", "composite_context", "market_mode", "alloc_optimal",
    "risk_index", "risk_regime", "momentum", "momentum_state", "structure_state",
    "impulse_state", "efficiency_ratio",
    "cycle_phase", "cycle_pct", "days_since_halving", "vdd_multiple", "cycle_position",
    # bottom-anchored 1064/364 cycle clock (the chart's theory) — parity with the halving
    # phase above; CONTEXT only, lets the synthesis cite the projected pivot + maturity
    "cphase_phase", "cphase_pct", "cphase_days_left", "cphase_next_pivot", "cphase_status",
    "mvrv_z", "mvrv_z_pctile", "valuation_state", "nupl", "mayer", "reserve_risk_pctile",
    "market_extreme", "extreme_score",
    "vol_state", "dvol", "dvol_pctile", "rv_cone_pctile", "vrp", "rr_25d", "skew_term",
    "put_call_oi_ratio", "term_slope_30_90",
    "oi_mcap_pctile", "oi_price_divergence", "funding_annual_pct", "funding_z",
    "leverage_stress", "basis_ann", "cme_basis_regime",
    "flow_state", "etf_flow_state", "etf_flow_z",
    "coinbase_premium", "ssr_oscillator", "mpi",
    "net_liquidity_bn", "net_liq_roc", "global_m2_yoy", "global_liq_regime",
    "real_yield", "hy_oas", "vix", "dxy", "macro_score", "macro_regime",
    "stbl_regime", "stbl_growth_z", "peg_state",
    "cot_z", "corr_spx", "corr_gold", "corr_dxy", "risk_asset_regime",
    "hash_ribbon", "puell",
)


def _btc_signals_row(root: Path, cols) -> dict | None:
    """Pull the last row of the vector signals parquet (+ flash state) down to the
    requested columns. Floats rounded; non-numeric strings kept; NaN -> None."""
    out: dict = {}
    fs = _read_json(root / "data/vector/flash_state.json")
    if fs:
        out["alert_state"] = fs.get("state")
        out["price"] = fs.get("price")
    try:
        import math

        import pandas as pd
        df = pd.read_parquet(root / "data/vector/signals.parquet")
        if len(df):
            last = df.iloc[-1]
            try:
                out["date"] = str(getattr(last, "name", ""))[:10] or None
            except Exception:  # noqa: BLE001
                pass
            for c in cols:
                if c in df.columns:
                    v = last[c]
                    try:
                        fv = float(v)
                        out[c] = None if math.isnan(fv) else round(fv, 4)
                    except (TypeError, ValueError):
                        out[c] = v if isinstance(v, str) else None
    except Exception:  # noqa: BLE001
        pass
    return out or None


def _btc_summary(root: Path) -> dict | None:
    return _btc_signals_row(root, _BTC_SMALL_COLS)


def _transmission_summary(macro: dict | None) -> dict | None:
    """Slim rate/inflation transmission read for the LLM brief: the current state, the
    top headwind/tailwind assets, and which causal chains are active. DISPLAY-ONLY
    context (the scored-leg gate found none robust) — narrate, never call it a signal."""
    t = (macro or {}).get("rate_inflation_transmission")
    if not t:
        return None
    st = t.get("state") or {}
    def lab(d):  # the EN side of a bilingual label dict
        return (d or {}).get("label", {}).get("en") if isinstance(d, dict) else None
    out = {
        "rates": lab(st.get("rates")), "inflation": lab(st.get("inflation")),
        "expectations": lab(st.get("expectations")),
        "headwinds": [h.get("asset") for h in (t.get("headwinds") or [])[:4]],
        "tailwinds": [h.get("asset") for h in (t.get("tailwinds") or [])[:4]],
        "active_chains": [c.get("id") for c in (t.get("chains") or []) if c.get("active")],
        "scored": False,
    }
    # slim yield-curve read (engine/yield_curve.py) — regime + recession dashboard +
    # the curve's sector/style tilt. Display-only context; the curve narrates, never sizes.
    yc = (macro or {}).get("yield_curve")
    if yc:
        reg = yc.get("regime") or {}
        rec = yc.get("recession") or {}
        fac = (yc.get("signals") or {}).get("stock_factor") or {}
        out["yield_curve"] = {
            "regime": (reg.get("label") or {}).get("en"),
            "fed_phase": (reg.get("fed_phase") or {}).get("en"),
            "favored": reg.get("favored"), "pressured": reg.get("pressured"),
            "recession_risk": rec.get("risk"), "recession_flags": rec.get("flags"),
            "policy_stance": (rec.get("policy_stance") or {}).get("stance"),
            "style": {k: fac.get(k) for k in ("value_vs_growth", "size", "duration_factor")},
            "market_tendency": ((yc.get("signals") or {}).get("market_tendency") or {}).get("drawdown_risk"),
        }
    return out


def _policy_intel_summary(root: Path) -> dict | None:
    """Compact realpolitik policy-layer read for the macro brief (Fed/Admin intent +
    capital rotation). Context only — carries its own FACT/INFERENCE/PRIOR labels."""
    intel = _read_json(root / "data/policy/intel.json")
    if not intel:
        return None
    rot = intel.get("rotation") or {}
    return {
        "thesis": (intel.get("thesis") or {}).get("en"),
        "regime_read": (intel.get("regime_read") or {}).get("en"),
        "targeted": [r.get("theme_en") for r in (rot.get("targeted") or [])][:7],
        "starved": [r.get("theme_en") for r in (rot.get("starved") or [])][:4],
        "open_predictions_n": sum(1 for p in (intel.get("predictions") or []) if p.get("status") == "open"),
    }


def gather_state(root: Path | None = None) -> dict:
    """Compact cross-asset state assembled from each dashboard's latest.json.
    Excludes holdings / watchlist composition by design. (macro lens)"""
    root = Path(root) if root else config.ROOT
    macro = _read_json(root / "data/regime/latest.json") or {}
    state: dict = {"macro": _macro_summary(macro)}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        state["china"] = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "liquidity_overlay", "cycle_tag", "pending_quad")}
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        state["hk"] = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "global_score", "risk_state",
            "peg_state", "peg_distance", "liquidity_overlay")}
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        state["commodity"] = {k: co.get(k) for k in ("date", "regime", "favored")}
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        state["forex"] = {k: fx.get(k) for k in
                          ("date", "regime", "favored", "risk", "dollar_desk", "transmission")}
    # Bonds: the leading-family credit/curve/rates-vol backdrop — built (drivers_for)
    # for exactly this synthesis, but never wired in until now.
    bonds = _bonds_backdrop(root)
    if bonds:
        state["bonds"] = bonds
    # Cross-asset confirmation: do bonds + FX confirm or diverge from the equity regime?
    conf = _confirm_summary(macro)
    if conf:
        state["cross_asset_confirm"] = conf
    # Rate & inflation transmission: the current rate/inflation state + which assets it
    # is a headwind/tailwind for + which causal chains are active (display-only context).
    tr = _transmission_summary(macro)
    if tr:
        state["rate_inflation_transmission"] = tr
    btc = _btc_summary(root)
    if btc:
        state["btc"] = btc
    if macro.get("catalyst_tone"):
        state["catalyst_tone"] = macro.get("catalyst_tone")
    # explicit Fed reaction-function stance (display-only leaf) + the realpolitik policy layer
    if macro.get("fed_stance"):
        fsd = macro["fed_stance"]
        state["fed_stance"] = {k: fsd.get(k) for k in
                               ("stance", "label_en", "guidance", "implied_cuts_12m", "market_vs_fed_en")}
    pol = _policy_intel_summary(root)
    if pol:
        state["policy_intel"] = pol
    # event-driven special situations (display-only leaf): macro-level landscape only.
    # Per-ticker situation context is consumed directly from site/allocationdata/
    # special_situations.json (schema special_situations.v1, is_context_only).
    ss = _read_json(root / "data/regime/special_situations_latest.json")
    if ss:
        state["special_situations"] = {k: ss.get(k) for k in
                                       ("total", "n_categories", "cross_border", "top_categories")}
    return state


def gather_china_state(root: Path | None = None) -> dict:
    """China & Hong-Kong focused state: the full China/HK regime detail, with a slim
    US-macro / commodity / FX backdrop. (china lens)"""
    root = Path(root) if root else config.ROOT
    state: dict = {}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        state["china"] = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "growth_confidence", "inflation_confidence", "confidence",
            "liquidity_overlay", "cycle_tag", "pending_quad", "pending_days",
            "confirming", "contradicting", "sector_rs", "pair_ratios") if k in ch}
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        state["hk"] = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score", "confidence",
            "liquidity_overlay", "cycle_tag", "global_score", "risk_state",
            "peg_state", "peg_distance", "confirming", "contradicting",
            "sector_rs", "pair_ratios") if k in hk}
        # compact display-only leaves (RORO / slowdown / drawdown / fear-euphoria /
        # tape drivers / property) — context for the narrator; never scored.
        cond = hk.get("conditions") or {}
        if cond:
            state["hk"]["conditions"] = {
                "roro_state": (cond.get("roro") or {}).get("roro_state"),
                "slowdown_score": (cond.get("recession") or {}).get("score"),
                "slowdown_label": (cond.get("recession") or {}).get("label"),
                "drawdown_band": (cond.get("drawdown_risk") or {}).get("band"),
            }
        fe = hk.get("fear_euphoria") or {}
        if fe:
            state["hk"]["fear_euphoria"] = {k: fe.get(k) for k in ("fe_score", "band") if k in fe}
        md = hk.get("market_drivers") or {}
        if md.get("verdict") not in (None, "unknown"):
            state["hk"]["market_drivers"] = {k: md.get(k) for k in
                                             ("verdict", "primary_label", "direction") if k in md}
        prop = hk.get("property") or {}
        if prop:
            state["hk"]["property"] = {k: prop.get(k) for k in
                                       ("regime", "ccl_chg_52w") if k in prop}
    backdrop = _macro_backdrop(_read_json(root / "data/regime/latest.json"))
    if backdrop:
        state["us_macro_backdrop"] = backdrop
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        state["commodity"] = {k: co.get(k) for k in ("date", "regime", "favored")}
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        state["forex"] = {k: fx.get(k) for k in
                          ("date", "regime", "favored", "risk", "dollar_desk", "transmission")}
    # bonds backdrop — global rate-differential / risk-off context that pushes on HK & A-shares
    bonds = _bonds_backdrop(root)
    if bonds:
        state["bonds"] = bonds
    # China intelligence surfaces (news media-sentiment · PBoC stance · alt-data convergence ·
    # divergence radar) — the transmission bus already fans these four into one compact,
    # context-only block. Display/context for the narrator; never scored.
    try:
        from engine import china_intel_bus
        b = china_intel_bus.briefing()
        # widened whitelist (v2): the central-analysis synthesis + flagged tickers + what-changed
        # must propagate, not just the four raw surface blocks (the L551 whitelist gates them).
        keys = ("news", "policy", "altdata", "radar",
                "analysis", "conviction", "cross_surface", "flagged_tickers",
                "what_changed", "salience")
        intel = {k: b.get(k) for k in keys if b.get(k)}
        if intel:
            intel["digest"] = b.get("digest")     # the synthesis-led plain-text rollup
            # the context-only contract MUST travel with the hoisted conviction/flagged tickers
            intel["is_context_only"] = True
            intel["disclaimer"] = b.get("disclaimer")
            intel["disclaimer_zh"] = b.get("disclaimer_zh")
            state["china_intel"] = intel
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("china_intel state unavailable (%s)", e)
    return state


def gather_btc_state(root: Path | None = None) -> dict:
    """Bitcoin focused state: the rich vector signal row + a slim US-macro backdrop.
    (btc lens)"""
    root = Path(root) if root else config.ROOT
    state: dict = {}
    btc = _btc_signals_row(root, _BTC_RICH_COLS)
    if btc:
        state["btc"] = btc
    backdrop = _macro_backdrop(_read_json(root / "data/regime/latest.json"))
    if backdrop:
        state["us_macro_backdrop"] = backdrop
    # bonds backdrop — BTC is a long-duration, real-rate-sensitive liquidity asset, so the
    # real-10y / credit / rates-vol read (and the bond layer's `drivers_for.bitcoin` gate) is
    # directly relevant.
    bonds = _bonds_backdrop(root)
    if bonds:
        state["bonds"] = bonds
    return state


# --------------------------------------------------------------------------- #
# lens registry — domain framing + state builder + output file, one engine each
# --------------------------------------------------------------------------- #
LENSES: dict[str, dict] = {
    "macro": {"out": "master_brief.json", "state_fn": gather_state,
              "system": MASTER_SYSTEM_TMPL, "thesis": DEFAULT_THESIS},
    "china": {"out": "china_brief.json", "state_fn": gather_china_state,
              "system": CHINA_SYSTEM_TMPL, "thesis": CHINA_THESIS},
    "btc":   {"out": "btc_brief.json", "state_fn": gather_btc_state,
              "system": BTC_SYSTEM_TMPL, "thesis": BTC_THESIS},
}


def _state_asof(state: dict) -> str | None:
    for k in ("macro", "china", "btc", "hk"):
        d = state.get(k)
        if isinstance(d, dict) and d.get("date"):
            return d.get("date")
    return None


def _thesis_for(lens: str, cfg: dict) -> str:
    spec = LENSES.get(lens, LENSES["macro"])
    # per-lens override (<lens>_thesis), then legacy rotation_thesis (macro only), then default
    return (cfg.get(f"{lens}_thesis")
            or (cfg.get("rotation_thesis") if lens == "macro" else None)
            or spec["thesis"])


# --------------------------------------------------------------------------- #
# the model call (DeepSeek V4 Pro via the Anthropic-compatible endpoint)
# --------------------------------------------------------------------------- #
def _client(cfg: dict):
    try:
        import anthropic
    except ImportError:
        return None
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    try:
        return anthropic.Anthropic(
            base_url=cfg.get("llm_base_url", "https://api.deepseek.com/anthropic"),
            api_key=key)
    except Exception:  # noqa: BLE001
        return None


def _call_model(system: str, user: str, cfg: dict) -> tuple[str | None, str | None]:
    """Return (reply_text, degraded_reason). Never raises."""
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    try:
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-v4-pro"),
            max_tokens=int(cfg.get("max_tokens", 4000)),
            system=system,
            messages=[{"role": "user", "content": user}])
        sr = getattr(resp, "stop_reason", None)
        if sr == "refusal":
            return None, "stop_refusal"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if not text:
            return None, "empty_reply"
        return text, ("truncated" if sr == "max_tokens" else None)
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("master_brain model call failed (%s)", e)
        return None, "llm_error"


# --------------------------------------------------------------------------- #
# public: synthesize one brief
# --------------------------------------------------------------------------- #
def synthesize(state: dict, cfg: dict | None = None, lens: str = "macro") -> dict:
    """Run the LLM synthesis over a gathered state for one LENS. Always returns a
    brief record (degraded fields flagged); never raises."""
    cfg = cfg or _cfg()
    spec = LENSES.get(lens, LENSES["macro"])
    brief = {
        "schema": "master_brief.v1", "lens": lens, "is_context_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "state_asof": _state_asof(state),
        "summary": None, "regime_read": None, "conflicts": [], "rotation_check": None,
        "transmission": [], "watch_items": [], "confidence": "low",
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER_TEXT,
    }
    system = spec["system"].format(thesis=_thesis_for(lens, cfg))
    user = ("Today's deterministic state (JSON). Synthesize per your "
            "instructions.\n<state>\n"
            + json.dumps(state, indent=2, default=str) + "\n</state>")
    reply, reason = _call_model(system, user, cfg)
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"   # surfaces "truncated"
        return brief
    for k in _BRIEF_FIELDS:
        if k in parsed:
            brief[k] = parsed[k]
    if reason:
        brief["degraded_reason"] = reason          # parsed, but flag e.g. truncation
    return brief


def render_markdown(brief: dict) -> str:
    """Human-readable rendering of a brief (for the CLI / a future panel)."""
    if not brief:
        return "_no brief_"
    if brief.get("degraded_reason") and not brief.get("regime_read"):
        return f"_master brief unavailable: {brief['degraded_reason']}_"
    L = [f"# Master brief — {brief.get('state_asof','?')} ({brief.get('model','?')})", ""]
    if brief.get("summary"):
        L += [f"**{brief['summary']}**", ""]
    if brief.get("regime_read"):
        L += ["## Regime read", brief["regime_read"], ""]
    if brief.get("conflicts"):
        L += ["## Conflicts", *[f"- {c}" for c in brief["conflicts"]], ""]
    if brief.get("rotation_check"):
        L += ["## Thesis check", brief["rotation_check"], ""]
    if brief.get("transmission"):
        L += ["## Transmission chains to watch", *[f"- {c}" for c in brief["transmission"]], ""]
    if brief.get("watch_items"):
        L += ["## Watch next", *[f"- {c}" for c in brief["watch_items"]], ""]
    L += [f"_confidence: {brief.get('confidence','?')} · context only, not a signal_"]
    return "\n".join(L)


_ZH_SCALARS = ("summary", "regime_read", "rotation_check")
_ZH_LISTS = ("conflicts", "transmission", "watch_items")


def _translate_brief(brief: dict, cfg: dict) -> None:
    """Attach a Chinese version (brief['zh']) via the shared DeepSeek translator
    (engine/translate.translate_to_zh) so the dashboard's 中文 toggle shows the brief
    in Chinese. The brief is unique daily, so it's translated fresh each run — a cheap
    V4-Flash pass. Degrade-never-raise: on any failure brief['zh'] is omitted and the
    panel falls back to English (per field)."""
    if not cfg.get("translate_zh", True):
        return
    if brief.get("degraded_reason") and not brief.get("regime_read"):
        return                                       # nothing usable to translate
    try:
        from engine import translate as _tr
        texts: list[str] = []
        layout: list[tuple[str, int | None]] = []
        for k in _ZH_SCALARS:
            v = brief.get(k)
            if isinstance(v, str) and v.strip():
                layout.append((k, None)); texts.append(v)
        for k in _ZH_LISTS:
            for i, v in enumerate(brief.get(k) or []):
                if isinstance(v, str) and v.strip():
                    layout.append((k, i)); texts.append(v)
        if not texts:
            return
        tcfg = {                                     # force-on Flash translate (independent of profile_translation)
            "enabled": True,
            "base_url": cfg.get("llm_base_url", "https://api.deepseek.com/anthropic"),
            "api_key_env": cfg.get("api_key_env", "DEEPSEEK_API_KEY"),
            "model": cfg.get("translate_model", "deepseek-v4-flash"),
            # small batches + generous cap: a Flash batch that hits max_tokens fails the
            # WHOLE batch closed (translate._translate_one_batch), and a long brief in one
            # 24-item batch blows the cap -> zero zh. Split it so any truncation is local.
            "max_chars": 2000, "max_tokens": 8000, "batch_size": 6,
        }
        zh_list = _tr.translate_to_zh(texts, tcfg)
        if not zh_list or all(x is None for x in zh_list):
            return
        zh: dict = {"summary": None, "regime_read": None, "rotation_check": None,
                    "conflicts": [None] * len(brief.get("conflicts") or []),
                    "transmission": [None] * len(brief.get("transmission") or []),
                    "watch_items": [None] * len(brief.get("watch_items") or [])}
        for (k, i), t in zip(layout, zh_list):
            if t is None:
                continue
            if i is None:
                zh[k] = t
            else:
                zh[k][i] = t
        brief["zh"] = zh
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("master_brief zh translation failed (%s)", e)


def run(persist: bool = True, root: Path | None = None, force: bool = False,
        lens: str = "macro") -> dict | None:
    """Gather state -> synthesize -> persist data/regime/<out> + site/<out> for one
    LENS. Returns the brief, or None when disabled (unless `force`, for on-demand/CLI
    use) or the lens is unknown. NEVER raises into the pipeline."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    spec = LENSES.get(lens)
    if spec is None:
        log.warning("master_brain: unknown lens %r", lens)
        return None
    try:
        root = Path(root) if root else config.ROOT
        # Interval gate — only regenerate every N days (1..7). When the existing brief
        # is younger than the interval, skip the (paid) LLM call and KEEP the prior
        # brief live: the committed data/regime/<out> + site/<out> are left untouched
        # so the dashboard deploys the previous note verbatim. `force` (CLI/on-demand)
        # always bypasses the gate. Anchored off data/regime (the canonical write
        # target); a missing/unparseable generated_at falls through to regeneration.
        if not force:
            try:
                interval = max(1, min(7, int(cfg.get("interval_days", 1))))
            except Exception:  # noqa: BLE001
                interval = 1
            if interval > 1:
                prev = _read_json(root / "data" / "regime" / spec["out"])
                age = _brief_age_days(prev)
                if age is not None and age < interval:
                    log.info("master_brain: lens=%s brief is %.1fd old (< %dd interval) "
                             "— skipping regen, keeping prior brief", lens, age, interval)
                    return prev
        state = spec["state_fn"](root)
        brief = synthesize(state, cfg, lens=lens)
        _translate_brief(brief, cfg)          # attach brief['zh'] for the 中文 toggle
        if persist:
            try:
                payload = json.dumps(brief, indent=2, default=str)
                out = root / "data" / "regime" / spec["out"]
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(payload)
                site = root / "site"          # client-fetched by the dashboard panel
                if site.is_dir():
                    (site / spec["out"]).write_text(payload)
            except Exception as e:  # noqa: BLE001
                log.warning("master_brief persist failed (lens=%s: %s)", lens, e)
        return brief
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("master_brain run failed (lens=%s: %s)", lens, e)
        return None


def run_all(persist: bool = True, root: Path | None = None,
            force: bool = False) -> dict[str, dict | None]:
    """Run every configured lens (master_brain.lenses, default macro+china+btc).
    Returns {lens: brief}. Disabled (and not forced) -> {} . NEVER raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return {}
    lenses = cfg.get("lenses") or list(LENSES.keys())
    out: dict[str, dict | None] = {}
    for lens in lenses:
        if lens in LENSES:
            out[lens] = run(persist=persist, root=root, force=force, lens=lens)
        else:
            log.warning("master_brain: skipping unknown lens %r in config", lens)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    argv = sys.argv[1:]
    force = "--force" in argv                 # ad-hoc run even when enabled is false
    want = [a for a in argv if a in LENSES]   # optional explicit lens(es): macro/china/btc
    results = ({ln: run(persist=True, force=force, lens=ln) for ln in want}
               if want else run_all(persist=True, force=force))
    if not results:
        print("master_brain disabled — set master_brain.enabled: true, or pass --force")
    for ln, b in results.items():
        print(f"\n===== lens: {ln} =====")
        print(render_markdown(b) if b else "(none)")
        if b and b.get("degraded_reason"):
            print(f"[degraded: {b['degraded_reason']}]")
