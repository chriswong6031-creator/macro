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

import hashlib
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

# Forward-watch tail — ONLY appended to the macro lens when forward_calendar is in state.
# (ADB-W2) Generates forward_watch rows + optional forward_read narrative.
_FORWARD_TAIL = (
    "\n\nIf `forward_calendar` is present in the state, also emit these two OPTIONAL keys "
    "(omit both if forward_calendar is absent or all sub-blocks are absent):\n"
    "  forward_watch: array of objects, one per notable upcoming event or release, with keys:\n"
    "    date: the date string VERBATIM from forward_calendar (e.g. \"2026-07-14\").\n"
    "    label: the event label VERBATIM from forward_calendar (e.g. \"CPI\", \"FOMC\").\n"
    "    kind: the kind/type string VERBATIM from forward_calendar.\n"
    "    note: <=20 words of plain-word framing — context for the trader, NO new numbers.\n"
    "  forward_read: optional string, <=3 sentences of narrative context for the forward "
    "picture. HARD RULES that are ABSOLUTE — violating any makes the field INVALID:\n"
    "  (a) Every digit-sequence in forward_watch rows and in forward_read MUST exist "
    "VERBATIM in the forward_calendar state block — no arithmetic, no rounding, no derived "
    "composites.\n"
    "  (b) Each forward_watch row cites exactly ONE source artifact (one event, one release, "
    "or one hazard — never combine two source numbers in one row).\n"
    "  (c) Model-emitted confidence fields (confidence_v2 etc.) are QUOTED from the state — "
    "never originated by you.\n"
    "  (d) If a sub-block has absent:true, say it is not available or omit the row — never "
    "synthesise as if data were present.\n"
    "  (e) Claims has model_status='benchmark_only' — only quote its benchmark values, "
    "never a projection band.\n"
    "  (f) Hazard numbers include their horizon exactly as given (e.g. '1m').\n"
    "  (g) Never add policy-timing or policy-intent predictions (these are conditions-framed "
    "calendar entries, never 'will fire' claims)."
)

# Producer tail — ONLY appended to the macro lens. Lets the brain stake its OWN falsifiable
# cross-asset leans (graded by master_brain_scorer), turning it from a read-only loop into a
# full closed loop. Subjects are restricted to instruments that are actually in the price
# cache (UUP/EEM/GLD are NOT cached → US dollar / EM / Gold are intentionally omitted).
_MACRO_THESES_TAIL = (
    "\n\nOPTIONALLY add a `theses` array — but usually EMPTY. Stake a lean ONLY on a "
    "genuine multi-dashboard cross-asset divergence you have real conviction in; a lean is a "
    "DIRECTION, never a size, and it is graded against realized prices, so OMIT rather than "
    "pad. Each thesis object:\n"
    "    subject: one of \"US equities\",\"Long Treasuries\",\"Investment-grade credit\","
    "\"High-yield credit\",\"Small caps\",\"Growth over value\",\"Semiconductors\","
    "\"China equities\",\"Bitcoin\",\"VIX\".\n"
    "    lean: one of \"overweight\",\"underweight\",\"avoid\",\"fade-fear\" (fade-fear is VIX-only).\n"
    "    conviction: \"low\"|\"medium\"|\"high\" — default low; reserve high for genuine agreement.\n"
    "    horizon_d: integer trading days, 5..60.\n"
    "    thesis: one sentence naming the divergence.\n"
    "    falsifier_text: one concrete condition that would prove the lean wrong."
)

MASTER_SYSTEM_TMPL = (
    "You are a senior cross-asset macro strategist writing a SHORT morning brief for "
    "a solo top-down trader. You are given the trader's OWN deterministic dashboard "
    "outputs (already computed, validated signals) across macro regime, China, Hong "
    "Kong, commodities, FX, BONDS (the leading-family credit / curve / rates-vol / "
    "sovereign read), and Bitcoin, plus an optional FOMC catalyst digest. Your job is "
    "SYNTHESIS across them — not to recompute or invent numbers.\n\n"
    "SAME-TAPE RULE (critical): every input block carries `_tape_family` and `_lead_lag` "
    "metadata. Blocks sharing the SAME `_tape_family` (e.g. price_regime) are derived "
    "from the SAME underlying price series — they are ONE observation of that series, "
    "not independent confirmation. Do NOT count them as separate evidence: `macro`, "
    "`forex`, `commodity`, `cross_asset_confirm`, `btc`, and `entry_quality_breadth` are "
    "all price_regime reads. A conflict between them is a DECOMPOSITION of one tape, not "
    "a cross-asset disagreement. True independence only exists across tape families "
    "(price_regime vs rates_credit vs policy_text). `_lead_lag: leading` means a "
    "defensible but noisy forward horizon exists; `coincident` means moves-with, not ahead-of.\n\n"
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
    "- If `entry_quality_breadth` is present, it is a RISK / ENTRY-QUALITY breadth check "
    "from the MTF confluence buy-filter across the US deep equity universe — it appears "
    "ONLY because that breadth DISAGREES with the regime read, so treat it as a CALIBRATION "
    "check: read its `calibration_check` line (e.g. a risk-on regime with few take-quality "
    "entries = narrow leadership / rotation, not broad conviction). Its `trend_breadth` "
    "(% above the 200-day) is the regime-tracking read; the long/short state mix is "
    "short-horizon mean-reversion-oscillator colour, NOT a regime turn — do not read a "
    "washed-out oscillator at a pullback low as a bear. It is a DRAWDOWN / entry-quality "
    "read, NEVER a return / alpha signal or an auto-trade trigger; it is ONE input among "
    "many; and it is a DIFFERENT axis from any cycle 'entry quality' (cycle proximity) — "
    "do not conflate them. Use it to TEMPER conviction in the regime call, not to flip it.\n"
    "- Evaluate the trader's working rotation thesis against the actual state; say "
    "explicitly where reality tracks it and where it diverges.\n"
    "- If `desk_track_records` is present, CALIBRATE to it: weight each desk's read by its "
    "measured hit-rate, and treat a cold desk (few scored, tiny sample) or a sub-50% desk as "
    "weak evidence — don't amplify a conflict that rests only on a desk that has been wrong.\n"
    "- Do NOT give position sizes or fire trades — the deterministic system does "
    "that. Give the read and what to watch.\n"
    "- Be honest about uncertainty and small samples. Flag conflicts rather than "
    "papering over them. Cite which dashboard supports each claim.\n"
    "- If `neural_web` is present in the state, use it to CALIBRATE and cross-check "
    "your read — never as independent confirmation when a block carries "
    "_tape_family='nw_synthesis' (those are aggregations of the same US price tape "
    "the macro block already reads, i.e. decomposition, not independent signal).\n"
    "- If a neural_web block has stale:true or absent:true, say so plainly "
    "('X is stale as of DATE' / 'not available') — never paper over a stale or "
    "absent block by synthesising as if the data were current.\n"
    "- The neural_web.cortex block is the overnight AI deliberation. When its "
    "status is 'degraded', treat NW deliberation as absent (one honest line). "
    "When present, weigh what_fired and deserves_operator as attention flags — "
    "never as primary signals.\n\n"
    "Working rotation thesis to test:\n{thesis}\n\n"
    + _SCHEMA_TAIL + _MACRO_THESES_TAIL + _FORWARD_TAIL
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
    "claim.\n"
    "- If `neural_web` is present in the state, use it to CALIBRATE and cross-check "
    "your read — never as independent confirmation when a block carries "
    "_tape_family='nw_synthesis' (same-tape decomposition, not independent signal).\n"
    "- If a neural_web block has stale:true or absent:true, say so plainly "
    "('X is stale as of DATE' / 'not available') — never paper over a stale block.\n"
    "- The neural_web.cortex block is the overnight AI deliberation. When degraded, "
    "treat NW deliberation as absent (one honest line). When present, weigh "
    "what_fired and deserves_operator as attention flags, never as primary signals.\n\n"
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


# --------------------------------------------------------------------------- #
# the macro PRODUCER — the brain's own falsifiable cross-asset leans. Mirrors the proven
# engine.ai_desk producer (resolve subject → engine-derived machine-checkable falsifier →
# validated thesis → append-only ledger), graded by engine.master_brain_scorer. ADDITIVE,
# macro-lens only, degrade-never-raise. ai_desk imports master_brain at module top, so every
# ai_desk reference here MUST be lazy (inside a function) to avoid an import cycle.
# --------------------------------------------------------------------------- #
_THESIS_LEANS = ("overweight", "underweight", "avoid", "fade-fear")
_CONVICTIONS = ("low", "medium", "high")
_BENCH = "SPY"
_VIX = "_VIX"
# subject (lowercased) -> (ticker, benchmark). ONLY tickers verified present in data/yahoo/.
# UUP/EEM/GLD are NOT cached, so US dollar / Emerging markets / Gold are omitted until a
# collector backfill; the cache-gate in _mb_derive_check is the safety net for map drift.
_XASSET_ETF = {
    "us equities": ("SPY", None),
    "long treasuries": ("TLT", "SPY"),
    "investment-grade credit": ("LQD", "SPY"),
    "high-yield credit": ("HYG", "SPY"),
    "small caps": ("IWM", "SPY"),
    "growth over value": ("IWF", "IWD"),
    "semiconductors": ("SMH", "SPY"),
    "china equities": ("FXI", "SPY"),
    "bitcoin": ("BTC-USD", "SPY"),   # NB: BTC trades 7d but check_by uses BusinessDay (context-only)
}


def _mb_cached(ticker, root) -> bool:
    try:
        from engine.ai_desk import _close_series        # lazy — avoid the ai_desk import cycle
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


def _mb_resolve(subject: str):
    s = (subject or "").strip().lower()
    if s in _XASSET_ETF:
        t, vs = _XASSET_ETF[s]
        return t, vs, "rel_return"
    if s in ("vix", "fear", "fade-fear"):
        return _VIX, None, "level"
    return None, None, "soft"


def _mb_derive_check(subject: str, lean: str, horizon: int, root) -> dict:
    ticker, vs, kind = _mb_resolve(subject)
    if kind == "rel_return":
        # cache-presence gate: an uncached ticker would silently EXPIRE after the grace
        # window (never 'soft'), so downgrade to soft → logged-unscored, honest.
        if root is not None and not _mb_cached(ticker, root):
            return {"kind": "soft", "reason": f"{ticker} not in price cache"}
        thr = 0.05
        if lean == "overweight":
            op, threshold = "<", -thr
        elif lean in ("underweight", "avoid"):
            op, threshold = ">", thr
        else:
            return {"kind": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
        return {"kind": "rel_return", "subject_ticker": ticker, "vs": vs,
                "op": op, "threshold": threshold, "horizon_d": horizon}
    if kind == "level":
        if lean == "fade-fear":
            return {"kind": "level", "subject_ticker": ticker, "vs": None, "op": ">",
                    "ref": "entry", "horizon_d": horizon,
                    "note": "FALSE if VIX makes a new high above the entry level within horizon"}
        return {"kind": "soft", "reason": f"lean '{lean}' has no level rule"}
    return {"kind": "soft", "reason": "subject not resolvable to a closeable instrument"}


def _mb_check_by(asof, horizon: int):
    try:
        import pandas as pd                               # lazy — master_brain stays pandas-free at import
        return (pd.Timestamp(asof) + pd.offsets.BusinessDay(int(horizon))).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _mb_build_thesis(t: dict, i: int, asof, root, cfg: dict) -> dict | None:
    """Validate one model-authored cross-asset lean + attach the engine-derived falsifier.
    Returns None for malformed / non-directional entries (every kept lean is scorable)."""
    if not isinstance(t, dict):
        return None
    subject = str(t.get("subject") or "").strip()
    lean = str(t.get("lean") or "").strip().lower()
    if not subject or lean not in _THESIS_LEANS:
        return None
    try:
        horizon = int(t.get("horizon_d") or 20)
    except Exception:  # noqa: BLE001
        horizon = 20
    horizon = max(5, min(60, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    if conv not in _CONVICTIONS:
        conv = "low"
    return {
        "id": f"mb-{asof}-{i + 1}",
        "subject": subject, "lean": lean, "conviction": conv, "horizon_d": horizon,
        "thesis": t.get("thesis"),
        "falsifier": {"text": t.get("falsifier_text"),
                      "check": _mb_derive_check(subject, lean, horizon, root)},
        "check_by": _mb_check_by(asof, horizon),
    }


def _mb_entry_levels(check: dict, asof, root) -> dict:
    out = {}
    try:
        from engine.ai_desk import _level_asof           # lazy — avoid the import cycle
        for key in ("subject_ticker", "vs"):
            tk = check.get(key)
            if tk:
                lv = _level_asof(tk, root, asof)
                if lv is not None:
                    out[tk] = lv
    except Exception:  # noqa: BLE001
        pass
    return out


def _append_ledger(brief: dict, root) -> None:
    """Append the macro brief's theses to data/master_brain/theses.jsonl. Never fatal."""
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        from engine.regime_label import quad_label
        d = Path(root) / "data" / "master_brain"
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        regime = quad_label(root)
        with open(d / "theses.jsonl", "a") as fh:
            for t in theses:
                check = (t.get("falsifier") or {}).get("check") or {}
                row = {
                    "id": t["id"], "logged_at": brief["generated_at"], "state_asof": asof,
                    "subject": t["subject"], "lean": t["lean"], "conviction": t["conviction"],
                    "horizon_d": t["horizon_d"], "falsifier": t["falsifier"],
                    "check_by": t["check_by"], "entry_levels": _mb_entry_levels(check, asof, root),
                    "regime": regime, "status": "open", "scored_at": None,
                    "outcome": None, "realized": None,
                }
                fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("master_brain: ledger append failed: %s", e)


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
    # Override-Registry (W0): feed the AI brief both the final (possibly gated)
    # allocation and the pure engine series + override flag so the LLM can narrate
    # the override honestly (e.g. "engine wants 22% but override holds to 0%").
    # W2: override_released marks a Class-1 structural-invalidation auto-release.
    "alloc_optimal_raw", "override_active", "override_released",
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


_DESK_TRACKS = (
    ("ai_desk", "data/ai_desk/track_record.json"),
    ("policy_intent", "data/policy_intent/track_record.json"),
    ("altdata", "data/altdata/track_record.json"),
    ("radar", "data/radar/track_record.json"),
    ("stock_desk", "data/stock_desk/track_record.json"),
    ("demand_chain", "data/demand_chain/track_record.json"),
)


def _desk_track_records(root) -> dict:
    """Compact hit-rate summary of the Phase-C falsifiable-thesis desks, injected into the
    macro state so the Brain calibrates its synthesis to which desks have actually been
    right — down-weighting a desk that is cold (tiny sample) or has been wrong. This is the
    read-back that turns the flagship brain from an open loop into a consumer of measured
    desk accuracy. CONTEXT-ONLY; reads the scorers' track_record.json (never a score/size)."""
    out = {}
    for name, rel in _DESK_TRACKS:
        d = _read_json(Path(root) / rel)
        if not isinstance(d, dict):
            continue
        ov = d.get("overall") or {}
        rec = {"scored": d.get("scored_total"), "open": d.get("open"),
               "hit_rate": ov.get("hit_rate"), "dir_accuracy": ov.get("dir_accuracy")}
        if d.get("calibration_note"):
            rec["note"] = d["calibration_note"]
        out[name] = rec
    return out



# --------------------------------------------------------------------------- #
# entry-quality breadth — the MTF confluence buy-filter leaf, aggregated into a
# RISK / ENTRY-QUALITY breadth CALIBRATION check for the brain. This is the seam
# where the brain CONSUMES data/signal_archive/mtf_signals_latest.json (the leaf
# run.py loads into latest["mtf_signals"]; see research/signal_engine/CHARTER.md §7).
# Hard rules (CHARTER §2–4): it is a RISK / drawdown / entry-quality read, NOT a
# return / alpha signal; ONE input among many; never scored, never an auto-trade
# trigger; a DIFFERENT axis from engine.cycles entry_quality (cycle proximity) —
# do not conflate. Surfaced ONLY when the breadth DISAGREES with the macro regime.
# --------------------------------------------------------------------------- #
def _macro_risk_posture(macro: dict | None) -> tuple[str, int]:
    """Coarse risk-on / risk-off / neutral read off the macro summary, as an integer
    tilt: low macro-risk + expanding growth & liquidity -> risk-on; the inverse ->
    risk-off. Used ONLY to decide whether the entry-quality breadth DISAGREES with the
    regime (a calibration check) — it is NOT itself a signal. Reads keys that exist on
    BOTH the raw data/regime/latest.json dict and the _macro_summary shape (growth_score,
    liquidity_overlay, macro_risk.label), so either may be passed."""
    if not isinstance(macro, dict):
        return "unknown", 0
    tilt = 0
    mr = ((macro.get("macro_risk") or {}).get("label") or "").lower()
    tilt += {"low": 2, "moderate": 1, "elevated": -1, "severe": -2}.get(mr, 0)
    g = macro.get("growth_score")
    if isinstance(g, (int, float)):
        tilt += 1 if g > 0.25 else -1 if g < -0.25 else 0
    liq = (macro.get("liquidity_overlay") or "").lower()
    tilt += 1 if "expand" in liq else -1 if "contract" in liq else 0
    posture = "risk-on" if tilt >= 2 else "risk-off" if tilt <= -2 else "neutral"
    return posture, tilt


def entry_quality_breadth(macro: dict | None, root: Path | None = None) -> dict | None:
    """Aggregate the MTF buy-filter leaf across the US deep universe into a one-line
    entry-quality BREADTH read, and flag a calibration CONFLICT when that breadth
    disagrees with the macro regime posture. DISPLAY-ONLY risk/entry-quality context
    (CHARTER §2) — one input among many, never a return signal, never auto-traded."""
    root = Path(root) if root else config.ROOT
    leaf = _read_json(root / "data" / "signal_archive" / "mtf_signals_latest.json")
    return breadth_from_leaf(leaf, macro)


def breadth_from_leaf(leaf: dict | None, macro: dict | None) -> dict | None:
    """Pure aggregation of an mtf_signals leaf (the §7B shape) into the entry-quality
    breadth read + calibration check. Split out so the disk path and the historical
    regression harness share ONE code path."""
    if not isinstance(leaf, dict):
        return None
    sigs = [s for s in (leaf.get("signals") or []) if isinstance(s, dict)]
    n = len(sigs)
    if n < 20:                      # too thin to read breadth honestly
        return None

    def pct(c: int) -> int:
        return round(100.0 * c / n)

    def _last(s: dict) -> dict:          # malformed/absent `last` -> {} (degrade-never-raise)
        last = s.get("last")
        return last if isinstance(last, dict) else {}

    long_pct = pct(sum(1 for s in sigs if s.get("state") == "long-bias"))
    short_pct = pct(sum(1 for s in sigs if s.get("state") == "short-bias"))
    mixed_pct = pct(sum(1 for s in sigs if s.get("state") == "mixed"))
    above_pct = pct(sum(1 for s in sigs if s.get("above200") is True))
    # entry-posture = names whose LAST signal is a fresh entry (buy/rebuy); quality
    # (take/block/pending) only exists on those.
    entries = [s for s in sigs if _last(s).get("type") in ("buy", "rebuy")]
    ne = len(entries)
    entry_pct = pct(ne)
    take_n = sum(1 for s in entries if _last(s).get("quality") == "take")
    block_n = sum(1 for s in entries if _last(s).get("quality") == "block")
    pend_n = sum(1 for s in entries if _last(s).get("quality") == "pending")

    def qpct(c: int) -> int | None:
        return round(100.0 * c / ne) if ne else None

    take_pct, block_pct, pending_pct = qpct(take_n), qpct(block_n), qpct(pend_n)
    # take_share = take over RESOLVED entries (exclude pending) — the conviction read used
    # for the conflict test, so a wave of not-yet-confirmable entries can't masquerade as
    # low conviction (a pending entry isn't a blocked one).
    resolved = take_n + block_n
    take_share = round(100.0 * take_n / resolved) if resolved else None

    # Two ORTHOGONAL dimensions — CHARTER §5 is explicit that the 3D confluence is a
    # MEAN-REVERSION oscillator, so its long/short state mix is SHORT-HORIZON entry-timing
    # colour, NOT a regime read (at a local low inside an uptrend the whole universe reads
    # short-bias). Only the 200-day TREND breadth tracks the slow regime — so the regime
    # conflict is anchored on trend breadth, and entry quality is reported separately.
    #   thresholds: 40/60 trend bands; 45/55 take-share bands (around a 50% midpoint) —
    #   coarse, symmetric, display-only cut points, never tuned to past P&L (CHARTER §3).
    trend_breadth = ("broad-up" if above_pct >= 60
                     else "broad-down" if above_pct <= 40 else "split")
    entry_breadth = ("n/a" if take_share is None
                     else "endorsed" if take_share >= 55
                     else "narrow" if (ne >= 8 and take_share <= 45) else "mixed")

    take_txt = f"{take_pct}% take-quality entries" if take_pct is not None else "no fresh entries"
    summary = (f"entry-quality breadth (risk / display-only): {above_pct}% above 200-day, "
               f"{take_txt}, {long_pct}% long-bias ({n} US names, {ne} at entry)")

    # Surface a calibration CONFLICT only when the breadth DISAGREES with the regime: a
    # rolled-over / narrow tape under a risk-on read, or a still-broad tape under risk-off.
    macro_posture, _tilt = _macro_risk_posture(macro)
    conflict = None
    if macro_posture == "risk-on":
        if trend_breadth == "broad-down":
            conflict = (f"macro read is risk-on, but equity breadth has broadly rolled over "
                        f"(only {above_pct}% above the 200-day, {short_pct}% short-bias) — "
                        f"not broad risk appetite.")
        elif entry_breadth == "narrow":
            conflict = (f"macro read is risk-on, but only {take_share}% of fresh entries clear "
                        f"the buy-filter ({ne} at entry) — suggests narrow leadership / rotation, "
                        f"not broad conviction (trend breadth is {trend_breadth}).")
    elif macro_posture == "risk-off":
        if trend_breadth == "broad-up" and (take_share is None or take_share >= 50):
            extra = f", {take_share}% of fresh entries clear the filter" if take_share is not None else ""
            conflict = (f"macro read is risk-off, but equity breadth is still broadly up "
                        f"({above_pct}% above the 200-day{extra}) — the de-risk may be lagging or "
                        f"the all-clear premature; watch breadth to confirm the turn.")

    return {
        "kind": "entry-quality / risk breadth (NOT a return signal)",
        "asof": leaf.get("asof"), "tf": leaf.get("tf"), "universe": leaf.get("universe"),
        "n": n, "n_at_entry": ne,
        "long_bias_pct": long_pct, "short_bias_pct": short_pct, "mixed_pct": mixed_pct,
        "above200_pct": above_pct, "entry_posture_pct": entry_pct,
        "take_pct": take_pct, "block_pct": block_pct, "pending_pct": pending_pct,
        "take_share_resolved_pct": take_share,
        "trend_breadth": trend_breadth,        # regime-tracking (above-200)
        "entry_breadth": entry_breadth,        # short-horizon entry conviction
        "macro_posture": macro_posture,
        "summary": summary,
        "calibration_check": conflict,        # populated ONLY on a regime conflict
        "is_risk_breadth_only": True,
        "axis_note": ("3D MTF confluence buy-filter breadth; a DIFFERENT axis from cycle "
                      "entry_quality (cycle proximity) — do not conflate."),
    }


def gather_state(root: Path | None = None) -> dict:
    """Compact cross-asset state assembled from each dashboard's latest.json.
    Excludes holdings / watchlist composition by design. (macro lens)

    #35 same-tape labeling (W7): each block carries two metadata fields so the
    synthesis LLM knows which inputs share a root cause:
      tape_family — the underlying series family the block derives from.
        price_regime     : US price/momentum tape (quad legs, equity breadth, FX risk-off,
                           commodity, BTC are all different reads of the SAME price series)
        price_regime_cn  : China price tape
        price_regime_hk  : HK price tape
        rates_credit     : rates, credit spreads (EBP, HY-OAS) — partially leading
        policy_text      : forward-looking policy documents (FOMC text, Fed guidance, WH intel)
      lead_lag — this block's documented temporal relationship to equity returns:
        coincident : moves with prices (no forward-predictive edge documented for this block)
        leading    : has a defensible (though noisy) leading horizon on this price tape
    These tags are NOT an IC claim — they are honest provenance so the Brain cannot
    count five price-regime reads as five independent observations of the same signal.
    """
    root = Path(root) if root else config.ROOT
    macro = _read_json(root / "data/regime/latest.json") or {}
    macro_sum = _macro_summary(macro)
    # Attach tape provenance to the macro block (W7 #35)
    macro_sum["_tape_family"] = "price_regime"
    macro_sum["_lead_lag"] = "coincident"
    macro_sum["_tape_note"] = (
        "US equity/macro quad — 73% market-proxy legs (copper-gold, XLY/XLP, breadth). "
        "Coincident: moves with and re-encodes the price tape it is derived from."
    )
    state: dict = {"macro": macro_sum}
    ch = _read_json(root / "data/china_regime/latest.json")
    if ch:
        ch_block = {k: ch.get(k) for k in (
            "date", "quad", "quad_name", "growth_score", "inflation_score",
            "liquidity_overlay", "cycle_tag", "pending_quad")}
        ch_block["_tape_family"] = "price_regime_cn"
        ch_block["_lead_lag"] = "coincident"
        state["china"] = ch_block
    hk = _read_json(root / "data/hk_regime/latest.json")
    if hk:
        hk_block = {k: hk.get(k) for k in (
            "date", "quad", "quad_name", "global_score", "risk_state",
            "peg_state", "peg_distance", "liquidity_overlay")}
        hk_block["_tape_family"] = "price_regime_hk"
        hk_block["_lead_lag"] = "coincident"
        state["hk"] = hk_block
    co = _read_json(root / "data/commodity/latest.json")
    if co:
        co_block = {k: co.get(k) for k in ("date", "regime", "favored")}
        co_block["_tape_family"] = "price_regime"
        co_block["_lead_lag"] = "coincident"
        state["commodity"] = co_block
    fx = _read_json(root / "data/forex/latest.json")
    if fx:
        fx_block = {k: fx.get(k) for k in
                    ("date", "regime", "favored", "risk", "dollar_desk", "transmission",
                     "regime_radar", "stance")}
        fx_block["_tape_family"] = "price_regime"
        fx_block["_lead_lag"] = "coincident"
        fx_block["_tape_note"] = (
            "FX risk-off/dollar read is a COINCIDENT fragility gauge — moves with prices, "
            "not ahead of them. Do not treat it as independent of the equity regime."
        )
        state["forex"] = fx_block
    # Bonds: the leading-family credit/curve/rates-vol backdrop — built (drivers_for)
    # for exactly this synthesis, but never wired in until now.
    bonds = _bonds_backdrop(root)
    if bonds:
        bonds["_tape_family"] = "rates_credit"
        bonds["_lead_lag"] = "leading"
        bonds["_tape_note"] = (
            "Credit/EBP and the curve (NTFS) have a defensible but noisy LEADING horizon. "
            "Rates-vol-vs-VIX and FX carry are COINCIDENT. The stock-bond correlation is a "
            "slow regime descriptor. Treat partial leading — do not claim bonds predict equities."
        )
        state["bonds"] = bonds
    # Cross-asset confirmation: do bonds + FX confirm or diverge from the equity regime?
    conf = _confirm_summary(macro)
    if conf:
        conf["_tape_family"] = "price_regime"
        conf["_lead_lag"] = "coincident"
        conf["_tape_note"] = (
            "SAME tape as `macro` and `forex` — bonds+FX vs equity regime divergence. "
            "This is ONE observation of the price_regime tape, not independent confirmation."
        )
        state["cross_asset_confirm"] = conf
    # Rate & inflation transmission: the current rate/inflation state + which assets it
    # is a headwind/tailwind for + which causal chains are active (display-only context).
    tr = _transmission_summary(macro)
    if tr:
        tr["_tape_family"] = "rates_credit"
        tr["_lead_lag"] = "coincident"
        tr["_tape_note"] = (
            "Rate/inflation read — rates are coincident to growth/inflation realizations. "
            "Scored=False: gate found no leg robust enough to time returns."
        )
        state["rate_inflation_transmission"] = tr
    btc = _btc_summary(root)
    if btc:
        btc["_tape_family"] = "price_regime"
        btc["_lead_lag"] = "coincident"
        state["btc"] = btc
    if macro.get("catalyst_tone"):
        ct_block = dict(macro["catalyst_tone"])
        ct_block["_tape_family"] = "policy_text"
        ct_block["_lead_lag"] = "leading"
        ct_block["_tape_note"] = (
            "FOMC text digest — forward-looking policy signal, independent of price tape. "
            "Context only; shock_reversible read is the binding use case."
        )
        state["catalyst_tone"] = ct_block
    # explicit Fed reaction-function stance (display-only leaf) + the realpolitik policy layer
    if macro.get("fed_stance"):
        fsd = macro["fed_stance"]
        fed_block = {k: fsd.get(k) for k in
                     ("stance", "label_en", "guidance", "implied_cuts_12m", "market_vs_fed_en")}
        fed_block["_tape_family"] = "policy_text"
        fed_block["_lead_lag"] = "leading"
        state["fed_stance"] = fed_block
    pol = _policy_intel_summary(root)
    if pol:
        pol["_tape_family"] = "policy_text"
        pol["_lead_lag"] = "leading"
        state["policy_intel"] = pol
    # event-driven special situations (display-only leaf): macro-level landscape only.
    # Per-ticker situation context is consumed directly from site/allocationdata/
    # special_situations.json (schema special_situations.v1, is_context_only).
    ss = _read_json(root / "data/regime/special_situations_latest.json")
    if ss:
        state["special_situations"] = {k: ss.get(k) for k in
                                       ("total", "n_categories", "cross_border", "top_categories")}
    # Read-back: the measured hit-rates of the falsifiable-thesis desks, so the Brain
    # calibrates its synthesis to which desks have actually been right (close the loop).
    tracks = _desk_track_records(root)
    if tracks:
        state["desk_track_records"] = tracks
    # W4 (#13): the SHADOW deterministic desk-weight vector from the outcome spine's
    # partial-pooling. Computed alongside the context read; the live flip is gated behind the
    # arm-by-evidence predicate (engine.pooling.arming). Surfaced so the divergence from
    # equal-weight is visible and the loop is measurable — the brain sees which desks the
    # spine down-weights, not just their hit-rates.
    try:
        from engine import desk_scorer as _ds
        dw = _ds.desk_weights(root=root)
        if dw and dw.get("per_desk"):
            state["desk_weights_shadow"] = {
                "armed": dw.get("armed"), "arming": dw.get("arming"),
                "divergence_l1": dw.get("divergence_l1"),
                "live_weights": dw.get("live_weights"),
                "shadow_weights": dw.get("shadow_weights"),
            }
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # MTF buy-filter entry-quality BREADTH (the brain CONSUMING the mtf_signals leaf) —
    # a RISK / entry-quality calibration check (CHARTER §2). Surfaced ONLY when it
    # CONFLICTS with the macro regime read; one input among many, never scored.
    eqb = entry_quality_breadth(macro, root)
    if eqb and eqb.get("calibration_check"):
        eqb["_tape_family"] = "price_regime"
        eqb["_lead_lag"] = "coincident"
        eqb["_tape_note"] = (
            "MTF buy-filter breadth — derived from the SAME US price tape as `macro`. "
            "SAME tape_family = one observation, not independent confirmation."
        )
        state["entry_quality_breadth"] = eqb
    # Oracle rotation directive — optional additive block (data/oracle/rotation_directive.json).
    # Surfaces rolling-over leaders and rotation context so the Brain can temper conviction
    # and raise cash; never a directional buy signal. Degrades silently when absent.
    try:
        _od = _read_json(root / "data" / "oracle" / "rotation_directive.json")
        if isinstance(_od, dict) and _od.get("rolling_over_leaders") is not None:
            oracle_block = {
                "rolling_over_leaders": _od.get("rolling_over_leaders"),
                "strengthening_complexes": _od.get("strengthening_complexes"),
                "regime_aggregate": _od.get("regime_aggregate"),
                "instruction": _od.get("instruction"),
                "asof": _od.get("asof"),
                "_tape_family": "price_regime",
                "_lead_lag": "coincident",
                "_tape_note": (
                    "Oracle rotation context: rolling-over leaders for conviction tempering "
                    "and cash-raising guidance. Display-only. NOT a directional buy signal. "
                    "Primaries NULL per P3 gauntlet; onset secondaries DISPLAY-WITH-EDGE only."
                ),
            }
            state["oracle_rotation"] = oracle_block
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # ADB-W1: inject NW context packet (lazy import so a broken NW package never breaks the brief)
    try:
        from engine.neuralweb import brief_context  # noqa: PLC0415
        state["neural_web"] = brief_context.macro_slice(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    # ADB-W2: forward-calendar state block (events, releases, rebalance, cycle hazards,
    # odds fingerprint, hypothesis clocks).  Fail-open: any failure → absent markers.
    try:
        from engine import forward_calendar_context as _fcc  # noqa: PLC0415
        state["forward_calendar"] = _fcc.gather_forward_calendar(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
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
                          ("date", "regime", "favored", "risk", "dollar_desk", "transmission",
                           "regime_radar", "stance")}
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
        # widened whitelist (v3): the central-analysis synthesis (now opportunity/edge/lifecycle-
        # ranked) + flagged tickers + what-changed + the risk-appetite regime + off-desk discovery
        # must propagate, not just the raw surface blocks (the whitelist gates them).
        keys = ("news", "policy", "altdata", "radar",
                "analysis", "conviction", "cross_surface", "flagged_tickers",
                "what_changed", "salience", "regime", "discovery")
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
    # ADB-W1: inject NW China context packet (lazy import so a broken NW package never breaks the brief)
    try:
        from engine.neuralweb import brief_context  # noqa: PLC0415
        state["neural_web"] = brief_context.china_slice(root)
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
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
# content-hash reply cache — determinism kit (W7 #33)
#
# master_brain synthesis is CONVERSATIONAL/NARRATIVE (not graded → not in a
# ledger), BUT its output shapes the daily brief users act on and the producer
# theses land in theses.jsonl (a graded ledger). Temperature=0 + seed=0 makes
# the call as deterministic as the provider allows. The content-hash cache gives
# a HARD guarantee: the same state JSON on the same day → identical brief, even
# if the provider's temperature=0 isn't perfectly deterministic.
# --------------------------------------------------------------------------- #
def _mb_prompt_hash(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _mb_reply_cache_path(prompt_hash: str, cfg: dict):
    from pathlib import Path as _P
    cdir = config.ROOT / cfg.get("reply_cache_dir", "data/master_brain/reply_cache")
    _P(cdir).mkdir(parents=True, exist_ok=True)
    return _P(cdir) / f"{prompt_hash}.txt"


def _mb_reply_cache_get(prompt_hash: str, cfg: dict) -> str | None:
    p = _mb_reply_cache_path(prompt_hash, cfg)
    try:
        return p.read_text() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _mb_reply_cache_put(prompt_hash: str, text: str, cfg: dict) -> None:
    try:
        _mb_reply_cache_path(prompt_hash, cfg).write_text(text)
    except Exception:  # noqa: BLE001
        pass


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
    """Return (reply_text, degraded_reason). Never raises.

    Determinism kit (W7 #33): temperature=0 + seed=0 for greedy/deterministic
    sampling. Content-hash cache: SHA-256(model‖system‖user) → cached reply text;
    same inputs always yield the same output so the same day's theses ledger rows
    are not polluted by sampling noise across re-runs.

    W5 ITEM 1 — 401-fallback: master_brain defaults to DeepSeek as its primary
    provider (llm_base_url / api_key_env configurable). The waterfall is built via
    engine.llm_auth.build_providers() so a 401 from any provider falls back cleanly.
    The degraded_reason distinguishes "auth_invalid:<provider>" from "llm_error".
    """
    from engine import llm_auth

    # master_brain uses a non-standard provider config: the default provider is
    # DeepSeek, but it is fully config-overridable via llm_base_url/api_key_env.
    # We build a minimal provider descriptor directly rather than using build_providers()
    # (which assumes the oauth→anthropic→deepseek order), because master_brain
    # intentionally sends derived market state to an endpoint the operator chose.
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    model = cfg.get("llm_model", "deepseek-v4-pro")
    env_var = cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    providers = [{"name": "deepseek", "env_var": env_var, "cred": "present",
                  "client": client, "model": model,
                  "usage_lane": "master-brain"}]

    # content-hash cache check (graded producer theses land in a ledger)
    phash = _mb_prompt_hash(model, system, user)
    cached = _mb_reply_cache_get(phash, cfg)
    if cached is not None:
        log.debug("master_brain: reply cache HIT (%s)", phash[:12])
        return cached, None

    max_tokens = int(cfg.get("max_tokens", 4000))

    def _do_call(_client, _model: str):
        kw: dict = {
            "model": _model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            # temperature removed — rejected (400) on opus-4.7+ per Anthropic API
        }
        try:
            kw["seed"] = 0
            resp = _client.messages.create(**kw)
        except TypeError:
            del kw["seed"]
            resp = _client.messages.create(**kw)
        sr = getattr(resp, "stop_reason", None)
        if sr == "refusal":
            return None, "stop_refusal", resp
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if not text:
            return None, "empty_reply", resp
        return text, ("truncated" if sr == "max_tokens" else None), resp

    try:
        text, reason, _ = llm_auth.make_call(providers, _do_call, context="master_brain")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("master_brain model call failed (%s)", e)
        return None, "llm_error"

    if text:
        _mb_reply_cache_put(phash, text, cfg)
    return text, reason


# --------------------------------------------------------------------------- #
# public: synthesize one brief
# --------------------------------------------------------------------------- #
def synthesize(state: dict, cfg: dict | None = None, lens: str = "macro", root=None) -> dict:
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
        "theses": [],    # macro-lens producer leans (always present → additive when absent)
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
    # ADB-W2: forward_watch and forward_read (macro lens only).  Parsed defensively:
    # - forward_watch: must be a list of dicts; any malformed row is dropped.
    # - forward_read: must be a string; missing → omitted.
    if lens == "macro":
        try:
            raw_fw = parsed.get("forward_watch")
            if isinstance(raw_fw, list):
                valid_rows = []
                for row in raw_fw:
                    if isinstance(row, dict) and row.get("date") and row.get("label"):
                        valid_rows.append({
                            "date": str(row["date"]),
                            "label": str(row["label"]),
                            "kind": str(row.get("kind", "")),
                            "note": str(row.get("note", ""))[:120],  # guard runaway notes
                        })
                if valid_rows:
                    brief["forward_watch"] = valid_rows
            raw_fr = parsed.get("forward_read")
            if isinstance(raw_fr, str) and raw_fr.strip():
                brief["forward_read"] = raw_fr.strip()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("master_brain: forward_watch/read parse failed: %s", e)
    # macro-lens producer: stake the brain's OWN falsifiable leans. Wrapped in its own try so
    # a theses bug can NEVER discard the free-text already copied above (the schema tail is
    # placed last, so a truncated reply drops the trailing theses array first, not the narrative).
    if lens == "macro" and cfg.get("emit_theses", True):
        try:
            raw = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
            built = []
            for t in raw[: int(cfg.get("max_theses", 2))]:
                th = _mb_build_thesis(t, len(built), brief["state_asof"], root, cfg)
                if th is not None:
                    built.append(th)
            brief["theses"] = built
        except Exception as e:  # noqa: BLE001 — a theses bug must never lose the free-text
            log.warning("master_brain: theses parse failed: %s", e)
            brief["theses"] = []
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
        brief = synthesize(state, cfg, lens=lens, root=root)
        # ADB-R9: additive optional keys — schema id stays master_brief.v1
        brief["nw_context_used"] = bool(state.get("neural_web"))
        _nw = state.get("neural_web") or {}
        _cortex = _nw.get("cortex") or {}
        brief["cortex_status"] = (
            _cortex.get("status", "absent") if not _cortex.get("absent") else "absent"
        )
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
        if lens == "macro":                   # producer: append the brain's own leans (macro only)
            _append_ledger(brief, root)
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
