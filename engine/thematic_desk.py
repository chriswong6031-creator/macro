"""AI Desk for Thematic Investing — an accountable LLM reasoning layer on the
Narrative-Rotation pages (allocation*.html), one desk per market (US/China/HK/Canada).

This is the sibling of engine.ai_desk (the macro/sector desk) pointed at THEMES instead of
GICS sectors. It reuses that chassis's discipline — quant DETECTS → AI JUDGES → track-record
GATES — without touching the live macro desk:

  gather → an LLM analyst turns the deterministic narrative_rotation state into a SHORT set
  of FALSIFIABLE, check-by-date leans → each is logged to an append-only ledger → a scorer
  grades them against realized proxy-vs-benchmark returns → the track record feeds back so
  conviction self-calibrates.

HONEST BY CONSTRUCTION (the whole point — see scripts/thematic_rotation_phase0.py):
  * cross-sectional theme momentum has rank-IC ~0; rotation-timing has NO validated forward
    edge; the only validated edge is DRAWDOWN control via the absolute-trend gate. So the AI
    cannot "predict the next narrative". Its leans are FALLIBLE HYPOTHESES expressed as
    falsifiable conditionals — graded over time — NOT edge extracted from the detectors.
  * it inherits, inline, the narrative_rotation ai_handoff `do_not_conclude` fences (no
    fade, no sizing, crowding = size-down only, inflows/attention ≠ buy, no next-theme call).
  * DISPLAY-ONLY: nothing here feeds any score/size/axis. The desk grades ITSELF.

Scorability: a theme is gradable only when its basket carries a SCALAR `etf_proxy`
(membership.json → surfaced in allocation.json ranks). overweight ⇒ FALSE if the proxy
underperforms the market benchmark by ≥ threshold over the horizon; avoid/underweight ⇒
the mirror. No proxy (or a blend) → the lean is logged `soft` and never scored (honest).

LLM = DeepSeek via engine.master_brain._call_model (the same gated client the macro desk
uses); when the key/feature is off the desk degrades to no theses and the page shows only
the deterministic handoff contract.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine import ai_desk as _ad           # reuse _check_by / _extract_json / _cfg
from engine import master_brain as _mb      # the LLM client (_call_model)
from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "thematic_desk.v1"

# region → (benchmark ticker, store group). Proxies live in the SAME store group as the
# benchmark (US proxies in yahoo; CN/HK/CA proxies in their region store). Mirrors
# engine.narrative_rotation._region_cfg.
REGION = {
    "us":     {"bench": "SPY",       "group": "yahoo",  "bench_label": "S&P 500"},
    "china":  {"bench": "510300.SS", "group": "china",  "bench_label": "CSI 300"},
    "hk":     {"bench": "_HSI",      "group": "hk",     "bench_label": "Hang Seng"},
    "canada": {"bench": "XIC.TO",    "group": "canada", "bench_label": "S&P/TSX"},
}
_ALLOC_FILE = {"us": "allocation.json", "china": "allocation_china.json",
               "hk": "allocation_hk.json", "canada": "allocation_canada.json"}
_LEANS = ("overweight", "underweight", "avoid")
_CONVICTIONS = ("low", "medium", "high")
_LEDGER_DIR = ("data", "thematic_desk")


def _cfg() -> dict:
    """Share the ai_desk LLM config (key/model/max_tokens/enabled/falsifier_defaults)."""
    return _ad._cfg()


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# close reads (region-aware via lib.store, unlike ai_desk's yahoo-only helper)
# --------------------------------------------------------------------------- #
def _close_asof(group: str, sym: str, on_or_before) -> float | None:
    try:
        df = store.read(group, sym)
        if df is None or "close" not in df.columns:
            return None
        s = df["close"].astype(float).dropna()
        s.index = pd.to_datetime(s.index)
        s = s[s.index <= pd.Timestamp(on_or_before)]
        return round(float(s.iloc[-1]), 6) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def _close_on_or_after(group: str, sym: str, on_or_after) -> float | None:
    """First close at/after a date (the scorer's exit read; tolerates weekends/holidays)."""
    try:
        df = store.read(group, sym)
        if df is None or "close" not in df.columns:
            return None
        s = df["close"].astype(float).dropna()
        s.index = pd.to_datetime(s.index)
        s = s[s.index >= pd.Timestamp(on_or_after)]
        return round(float(s.iloc[0]), 6) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# STATE — slim the narrative_rotation payload into the desk's briefing bundle
# --------------------------------------------------------------------------- #
def _alloc_view(region: str, root) -> dict | None:
    p = Path(root) / "site" / "allocationdata" / _ALLOC_FILE[region]
    d = _ad._read_json(p)
    if not d or not d.get("ranks"):
        return None
    ranks = [{
        "name": r.get("name"), "name_zh": r.get("name_zh"), "id": r.get("id"),
        "category": r.get("category"), "rank": r.get("rank"), "score": r.get("score"),
        "eligible": r.get("eligible"),
        "durability_bar": (r.get("durability") or {}).get("bar"),
        "hurst_tag": (r.get("durability") or {}).get("hurst_tag"),
        "breadth": (r.get("durability") or {}).get("breadth"),
        "crowding_z": (r.get("crowding") or {}).get("crowding_z"),
        "crowded": (r.get("crowding") or {}).get("crowded"),
        "etf_proxy": r.get("etf_proxy"),
        "scorable": isinstance(r.get("etf_proxy"), str) and bool(r.get("etf_proxy")),
    } for r in d["ranks"]]
    return {
        "region": region, "market": d.get("market_en"), "as_of": d.get("as_of"),
        "benchmark": REGION[region]["bench_label"],
        "headline": d.get("headline"), "ranks": ranks, "rotation": d.get("rotation"),
        "backtest_verdict": (d.get("backtest") or {}).get("verdict"),
        "gate_helps": (d.get("backtest") or {}).get("gate_helps"),
        # carry the fences INLINE so the analyst honours them (mirrors ai_desk._flow_view)
        "guardrails": (d.get("ai_handoff") or {}),
    }


def gather_thematic_state(region: str, root=None) -> dict | None:
    """Point-in-time bundle for one market: the narrative_rotation view + the desk's own
    track record. Returns None only if the allocation artifact is absent."""
    root = Path(root) if root else config.ROOT
    nr = _alloc_view(region, root)
    if nr is None:
        return None
    track = _ad._read_json(Path(root).joinpath(*_LEDGER_DIR, "track_record.json"))
    tr = None
    if isinstance(track, dict):
        tr = (track.get("by_market") or {}).get(region) or track.get("overall")
    return {"as_of": nr.get("as_of"), "region": region, "market": nr.get("market"),
            "narrative_rotation": nr, "track_record": tr, "macro_narrative": _macro_narrative(root),
            "theme_candidates": _theme_candidates(region, root)}


def _theme_candidates(region: str, root) -> dict | None:
    """Slim view of the theme-discovery radar (US only) — coherent NEW groups of names not in
    a basket, for the narrative-scout to consider. DISPLAY-ONLY candidate generator; flags are
    noisy and carry NO forward edge (data/theme_discovery/phase0.json). Never a buy list."""
    if region != "us":
        return None
    d = _ad._read_json(Path(root) / "site" / "allocationdata" / "theme_candidates.json")
    if not d or not d.get("candidates"):
        return None
    cands = [{"label": c.get("label"), "n": c.get("n"), "cohesion": c.get("cohesion"),
              "cohesion_chg": c.get("cohesion_chg"), "ipo_wave": c.get("ipo_wave"),
              "tickers": [m.get("ticker") for m in (c.get("constituents") or [])][:8]}
             for c in d["candidates"][:5]]
    return {"candidates": cands, "verdict": d.get("verdict"),
            "note": "noisy candidate radar — for human review/watchlist, NO forward edge, never a buy"}


def _macro_narrative(root=None) -> dict | None:
    """A slim MARKET-LEVEL narrative backdrop (which macro/policy/geo narrative dominates
    headlines + the unscheduled-surprise share) — COINCIDENT context for the desk's regime
    read; NOT per-theme news and NEVER a buy/sell trigger. Read from the JSON artifact the
    BUILD writes (scripts.build_allocation._run_macro_narrative, which owns the GDELT news
    bus) so engine/ stays free of that bus module (the scoring-isolation invariant). None
    when absent. Never raises."""
    root = Path(root) if root else config.ROOT
    d = _ad._read_json(root / "site" / "allocationdata" / "macro_narrative.json")
    return d if isinstance(d, dict) and d.get("dominant_themes") else None


# --------------------------------------------------------------------------- #
# the falsifier — theme → its proxy ETF vs the regional benchmark (scorable),
# else soft (logged, never scored). Reuses the rel_return op/threshold logic.
# --------------------------------------------------------------------------- #
def _proxy_for(subject: str, ranks: list) -> tuple[str | None, str | None]:
    """Match a thesis subject to a theme row → (scalar etf_proxy, theme_id) or (None,None)."""
    s = (subject or "").strip().lower()
    for r in ranks:
        if s in (str(r.get("name") or "").lower(), str(r.get("name_zh") or "").lower(),
                 str(r.get("id") or "").lower()):
            p = r.get("etf_proxy")
            return (p if isinstance(p, str) and p else None), r.get("id")
    return None, None


def _derive_check(subject: str, lean: str, horizon: int, region: str,
                  ranks: list, cfg: dict) -> dict:
    thr = float((cfg.get("falsifier_defaults", {}) or {}).get("rel_return", 0.05))
    proxy, tid = _proxy_for(subject, ranks)
    if not proxy:
        return {"kind": "soft", "reason": "theme has no scalar etf_proxy → not cleanly scorable"}
    if lean == "overweight":
        op, threshold = "<", -thr                 # FALSE if proxy underperforms bench by ≥ thr
    elif lean in ("underweight", "avoid"):
        op, threshold = ">", thr                  # FALSE if proxy outperforms bench by ≥ thr
    else:
        return {"kind": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
    return {"kind": "theme_rel_return", "theme_id": tid, "subject_ticker": proxy,
            "vs": REGION[region]["bench"], "group": REGION[region]["group"],
            "op": op, "threshold": threshold, "horizon_d": horizon}


def _build_thesis(t: dict, i: int, asof, region: str, ranks: list, cfg: dict) -> dict | None:
    if not isinstance(t, dict):
        return None
    subject = str(t.get("subject") or "").strip()
    lean = str(t.get("lean") or "").strip().lower()
    if not subject or lean not in _LEANS:
        return None
    try:
        horizon = int(t.get("horizon_d") or cfg.get("default_horizon_d", 20))
    except Exception:  # noqa: BLE001
        horizon = int(cfg.get("default_horizon_d", 20))
    horizon = max(5, min(60, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    conv = conv if conv in _CONVICTIONS else "low"
    return {
        "id": f"{region}-{asof}-{i + 1}", "market": region, "subject": subject, "lean": lean,
        "conviction": conv, "horizon_d": horizon, "thesis": t.get("thesis"),
        "evidence": [str(e) for e in (t.get("evidence") or []) if e][:5],
        "dissent": t.get("dissent"),
        "falsifier": {"text": t.get("falsifier_text"),
                      "check": _derive_check(subject, lean, horizon, region, ranks, cfg)},
        "check_by": _ad._check_by(asof, horizon),
    }


# --------------------------------------------------------------------------- #
# the analyst (single structured DeepSeek call; the adversarial panel is a fast-follow)
# --------------------------------------------------------------------------- #
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  regime_context: string — 1-2 sentences on what the detector state actually shows for "
    "this market (grounded; no invented numbers). Put any no-view here.\n"
    "  theses: array of 0..N objects (omit rather than pad — honesty over content), each:\n"
    "     subject: string — EXACTLY one theme name from narrative_rotation.ranks[].name.\n"
    "     lean: one of \"overweight\",\"underweight\",\"avoid\". A lean is a DIRECTION, never a size.\n"
    "     conviction: one of \"low\",\"medium\",\"high\" — be modest; default low.\n"
    "     horizon_d: integer trading days, 5..60.\n"
    "     thesis: string — reasoning, naming WHICH detector leg supports it (rank/durability/"
    "trend-gate/crowding/rotation).\n"
    "     evidence: array of strings citing the specific legs.\n"
    "     dissent: string — the single strongest contrary case.\n"
    "     falsifier_text: string — one concrete condition that would prove this wrong, "
    "phrased as the plain condition itself (e.g. 'XLK lags SPY by 5% before the check-by "
    "date'). This text is shown to users under a 'Changes this read' label: never write "
    "the words 'falsified', 'falsify' or 'refuted' in it.\n"
    "  emerging_watch: string|null — at most ONE early-hypothesis to watch (a theme whose "
    "leadership may be forming OR fading) WITH the observable condition you are watching "
    "for (the one that would retire the watch); or null. This is a watch, not a call. This "
    "text is shown to users VERBATIM under an 'AI scout watch' label: state the condition "
    "plainly and never write 'kill criterion', 'falsified', 'falsify' or 'refuted' in it.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)

_SYSTEM = (
    "You are the analyst running a THEMATIC desk note for a solo top-down trader, for ONE "
    "market. You are handed the trader's OWN deterministic Narrative-Rotation detector state "
    "(theme momentum ranks, an absolute-trend eligibility gate, durability, crowding texture, "
    "and a rotation radar). Turn it into a SHORT set of accountable, FALSIFIABLE directional "
    "leans on THEMES.\n\n"
    "CRITICAL — this detector is TRUST-GRADED and DISPLAY-ONLY:\n"
    "- Cross-sectional theme momentum has rank-IC ~0 (an attention/FOCUS lens, NOT alpha). "
    "Rotation-timing has NO validated forward edge. The ONE validated edge is DRAWDOWN/shake-"
    "out control via the absolute-trend gate. Durability/crowding/rotation are COINCIDENT.\n"
    "- If narrative_rotation.gate_helps is false, the trend discipline did NOT even cut "
    "drawdown on THIS market's history (it mean-reverts) — be especially humble; lean low.\n"
    "- Therefore NEVER claim the detector 'predicts' returns. Your leans are YOUR fallible "
    "judgement EXPRESSED AS FALSIFIABLE CONDITIONALS — not edge extracted from the detector.\n"
    "- Honour EVERY item in narrative_rotation.guardrails.do_not_conclude and "
    ".ai_directive.\n"
    "- A state.macro_narrative backdrop (which macro/policy/geo narrative dominates "
    "headlines + the unscheduled-surprise share) may be present. It is COINCIDENT, "
    "market-level context for the regime read — NOT per-theme news and NEVER a buy "
    "trigger.\n\n"
    "Rules:\n"
    "- Reason ONLY over the provided JSON state + well-known market structure. NEVER fabricate "
    "a level, score or event. If the state doesn't support a view, return fewer (or zero) "
    "theses and say so in regime_context.\n"
    "- Prefer subjects that are scorable (ranks[].scorable==true, i.e. have a proxy ETF) so "
    "the call can be graded. You MAY still lean on an unscorable theme, but mark conviction "
    "low.\n"
    "- Crowding is a SIZE-DOWN caution ONLY — never a fade, short, or sell. Do NOT treat the "
    "leading theme as a buy because it leads, and do NOT fade the dominant theme on a crowding "
    "flag (reflexivity). Do NOT predict the NEXT narrative; only flag a CONFIRMED handoff.\n"
    "- NEVER give a position size, weight, dollar amount, or fire a trade — sizing is owned by "
    "the deterministic allocator. Give a DIRECTION and what would invalidate it.\n"
    "- Each thesis needs an honest DISSENT (best bear case) and a CONCRETE falsifier.\n"
    "- If a track_record is present, CALIBRATE conviction to it (if past high-conviction calls "
    "missed, default lower). Small samples → lean low. This note is GRADED against reality.\n\n"
    + _SCHEMA_TAIL
)


def _build_user(state: dict) -> str:
    return ("Today's trust-graded thematic detector state for this market (JSON). Produce "
            "your desk note per your instructions — accountable, falsifiable, never sized.\n"
            "<state>\n" + json.dumps(state, indent=2, default=str) + "\n</state>")


DISCLAIMER = (
    "Context only — the desk's fallible, CHECKABLE hypotheses, graded against reality over "
    "time. NOT investment advice, NOT a buy list, NOT a size. The validated edge on this page "
    "is drawdown control; everything the AI says is display-only.")


# --------------------------------------------------------------------------- #
# the adversarial panel — four roles debate the SAME state in parallel, then a
# desk-head adjudicates into the final falsifiable leans (mirrors engine.ai_desk).
# The adjudicator's schema is unchanged, so the falsifier/ledger/scorer downstream
# are untouched — the panel only improves the QUALITY of the leans.
# --------------------------------------------------------------------------- #
_PANEL_CAVEAT = (
    "\nCRITICAL — the detector is TRUST-GRADED and DISPLAY-ONLY: theme momentum rank-IC ~0 "
    "(a FOCUS lens, not alpha), rotation-timing has NO validated edge, the ONLY validated edge "
    "is DRAWDOWN control via the absolute-trend gate, and durability/crowding/rotation are "
    "COINCIDENT. If narrative_rotation.gate_helps is false the discipline did not even cut "
    "drawdown on this market (it mean-reverts) — be especially humble. Honour every item in "
    "narrative_rotation.guardrails.do_not_conclude. NEVER a position size, weight, or trade. "
    "Your view is a fallible, falsifiable conditional — not edge extracted from the detector.")

_PANEL_SYSTEMS = {
    "trend_rider": (
        "ROLE: TREND-RIDER analyst on a thematic desk. Argue the STRONGEST honest case FOR "
        "staying with the leading durable theme(s) — because the absolute-trend gate (staying "
        "with the trend, not calling tops) is the one validated edge here. Cite the rank, the "
        "durability bar, and the trend gate for each idea." + _PANEL_CAVEAT),
    "crowding_skeptic": (
        "ROLE: CROWDING-SKEPTIC analyst. Your job is to FALSIFY the longs, not to balance. "
        "Name which theme is most over-extended / crowded (crowding_z, rs-stretch, % parabolic, "
        "thinning breadth, narrowing leadership) and argue it is therefore a SIZE-DOWN. You are "
        "FORBIDDEN to call a fade/short/sell (reflexivity — crowding is a sizing caution only). "
        "Put the sharpest bear case on each long." + _PANEL_CAVEAT),
    "narrative_scout": (
        "ROLE: NARRATIVE-EMERGENCE SCOUT. Look for ONE early-hypothesis worth watching — a theme "
        "whose leadership may be FORMING or FADING — and name the observable condition you are "
        "watching for, the one that would retire the watch. You may draw "
        "on state.theme_candidates (a DISPLAY-ONLY radar of coherent NEW name-groups not yet in a "
        "basket) — but it is NOISY (only ~10% persist) and has NO forward edge, so treat any "
        "candidate as a watch-hypothesis to grade, never a buy, and let IPO-wave/hype RAISE the "
        "bar. Remember emergence usually reads LATE and attention/inflow spikes mark TOPS. Put it "
        "in emerging_watch; keep theses minimal." + _PANEL_CAVEAT),
    "macro_regime": (
        "ROLE: MACRO-REGIME analyst. Read the regime signals — breadth-of-rotation, the "
        "one-narrative/absorption gauge, gate_helps, the headline cash level — AND the "
        "state.macro_narrative backdrop (which macro/policy/geo narrative is dominating "
        "headlines + the unscheduled/surprise share). Say whether the regime supports risk-on "
        "theme exposure AT ALL, or argues for more cash / smaller size. The news backdrop is "
        "COINCIDENT market-level context (not per-theme) — use it to read risk appetite, never "
        "as a buy trigger. Do not pick individual winners." + _PANEL_CAVEAT),
}

_ADJ_SYSTEM = (
    "ROLE: DESK-HEAD adjudicator for a THEMATIC desk. Four independent analysts (trend-rider, "
    "crowding-skeptic, narrative-scout, macro-regime) argued over the SAME trust-graded "
    "detector state; their JSON stances are given alongside the raw state. Synthesize the FINAL "
    "set of accountable, FALSIFIABLE per-theme leans for a solo top-down trader.\n\n"
    "Rules:\n"
    "- Keep a long lean ONLY if it survives the CROWDING-SKEPTIC; put that analyst's sharpest "
    "objection to the specific theme in `dissent` — do not soften it.\n"
    "- Calibrate conviction DOWN on disagreement: when analysts conflict, when the macro-regime "
    "analyst says risk-off / raise cash, when gate_helps is false, or when leadership is narrow. "
    "Reserve \"high\" for genuine multi-analyst agreement (rare). Default \"low\".\n"
    "- Crowding is a SIZE-DOWN caution only — never emit a fade/short/sell. Do NOT predict the "
    "next narrative; route the scout's idea into emerging_watch (a graded hypothesis), not a "
    "thesis, unless a handoff is already CONFIRMED.\n"
    "- If a track_record is present, calibrate to it (past high-conviction misses → lean lower).\n"
    "- In `evidence`, cite which analyst and which detector leg supports each lean. Honour "
    "narrative_rotation.guardrails. NEVER a size/weight/trade. Prefer scorable subjects "
    "(ranks[].scorable). Omit theses rather than pad — honesty over content.\n\n"
    + _SCHEMA_TAIL)


def _slim_stance(s: dict) -> dict:
    """A compact view of one analyst's stance for the page (transparency, not scored)."""
    if not isinstance(s, dict):
        return {}
    leans = [{"subject": t.get("subject"), "lean": t.get("lean")}
             for t in (s.get("theses") or []) if isinstance(t, dict) and t.get("subject")][:3]
    return {"stance": s.get("regime_context"), "leans": leans,
            "watch": s.get("emerging_watch")}


def _run_panel(state: dict, cfg: dict, call=None) -> dict:
    """Run the four analysts over the same bundle in parallel. {role: stance|None}; never raises."""
    fn = call or _mb._call_model
    user = _build_user(state)

    def _one(key):
        try:
            reply, _ = fn(_PANEL_SYSTEMS[key], user, cfg)
            parsed = _ad._extract_json(reply) if reply is not None else None
            return key, (parsed if isinstance(parsed, dict) else None)
        except Exception:  # noqa: BLE001 — one analyst failing must not sink the panel
            return key, None

    keys = list(_PANEL_SYSTEMS)
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(keys)) as ex:
            results = list(ex.map(_one, keys))
    except Exception:  # noqa: BLE001 — sequential fallback
        results = [_one(k) for k in keys]
    return dict(results)


def _adjudicate(state: dict, panel: dict, cfg: dict, call=None):
    """Desk-head synthesis over the panel + raw state → (reply_text, degraded_reason)."""
    fn = call or _mb._call_model
    payload = {"detector_state": state, "analyst_panel": {k: v for k, v in panel.items() if v}}
    user = ("The detector state and the four analysts' stances (JSON). Adjudicate into the FINAL "
            "falsifiable per-theme leans per your instructions.\n<input>\n"
            + json.dumps(payload, indent=2, default=str) + "\n</input>")
    return fn(_ADJ_SYSTEM, user, cfg)


def synthesize(state: dict, cfg: dict | None = None, call=None) -> dict:
    """Run the analyst over a gathered state → a brief record. Never raises. `call` is
    injectable (defaults to master_brain._call_model) so tests run without an API key."""
    cfg = cfg or _cfg()
    region = state.get("region")
    asof = state.get("as_of")
    ranks = (state.get("narrative_rotation") or {}).get("ranks") or []
    brief = {
        "schema": SCHEMA, "is_context_only": True, "market": region,
        "generated_at": _now_iso(), "state_asof": asof,
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "regime_context": None, "emerging_watch": None, "theses": [],
        "track_record": state.get("track_record"), "confidence": "low",
        "macro_narrative": state.get("macro_narrative"),    # coincident backdrop, for display
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER,
        # #41 badge honesty: the desk's conviction badge carries an honest provenance passport
        # (measured·n / accruing·n=0), derived from the outcome spine, so a cold lean can't read
        # as an earned edge. Set here so every return path (incl. degraded) carries it.
        "passport": _ad._desk_passport(f"thematic_{region}"),
    }
    # adversarial panel (default on) → desk-head adjudication; analyst-only fallback.
    panel_on = bool((cfg.get("panel") or {}).get("enabled", True))
    if panel_on:
        panel = _run_panel(state, cfg, call)
        brief["panel"] = {k: _slim_stance(v) for k, v in panel.items() if v}
        if any(panel.values()):
            reply, reason = _adjudicate(state, panel, cfg, call)
        else:                                          # whole panel unavailable → single analyst
            reply, reason = (call or _mb._call_model)(_SYSTEM, _build_user(state), cfg)
    else:
        reply, reason = (call or _mb._call_model)(_SYSTEM, _build_user(state), cfg)
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _ad._extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"
        return brief
    brief["regime_context"] = parsed.get("regime_context")
    brief["emerging_watch"] = parsed.get("emerging_watch")
    conf = str(parsed.get("confidence") or "low").strip().lower()
    brief["confidence"] = conf if conf in _CONVICTIONS else "low"
    raw = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
    theses = []
    for t in raw[: int(cfg.get("max_theses", 3))]:
        th = _build_thesis(t, len(theses), asof, region, ranks, cfg)
        if th is not None:
            theses.append(th)
    brief["theses"] = theses
    if reason:
        brief["degraded_reason"] = reason
    return brief


# --------------------------------------------------------------------------- #
# ledger (append-only) + public per-market brief
# --------------------------------------------------------------------------- #
def _entry_levels(check: dict, asof, root) -> dict:
    """Snapshot the proxy + bench closes the scorer needs (region-aware)."""
    out = {}
    g = check.get("group", "yahoo")
    for t in (check.get("subject_ticker"), check.get("vs")):
        if t:
            lv = _close_asof(g, t, asof)
            if lv is not None:
                out[t] = lv
    return out


def _append_ledger(brief: dict, root) -> None:
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        d = Path(root).joinpath(*_LEDGER_DIR)
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        seen = set()
        lp = d / "theses.jsonl"
        if lp.exists():
            for line in lp.read_text().splitlines():
                try:
                    seen.add(json.loads(line).get("id"))
                except Exception:  # noqa: BLE001
                    pass
        with open(lp, "a") as fh:
            for th in theses:
                if th["id"] in seen:
                    continue
                check = (th.get("falsifier") or {}).get("check") or {}
                row = {**th, "market": brief.get("market"), "logged_at": _now_iso(),
                       "state_asof": asof, "entry_levels": _entry_levels(check, asof, root)}
                fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("thematic_desk ledger append failed: %s", e)


def run(market: str = "us", persist: bool = True, root=None, call=None) -> dict | None:
    """Gather → synthesize → persist the public brief + ledger for one market. Additive:
    returns None (and writes nothing) when disabled / no key / no state. Never raises."""
    region = (market or "us").lower()
    if region not in REGION:
        return None
    if call is None and not enabled():
        log.info("thematic_desk[%s]: disabled (ai_desk.enabled=false) — skipping", region)
        return None
    root = Path(root) if root else config.ROOT
    try:
        state = gather_thematic_state(region, root)
        if state is None:
            return None
        brief = synthesize(state, _cfg(), call)
        if persist:
            site = Path(root) / "site" / "allocationdata"
            site.mkdir(parents=True, exist_ok=True)
            (site / f"ai_desk_{region}.json").write_text(json.dumps(brief, default=str))
            _append_ledger(brief, root)
        return brief
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("thematic_desk run[%s] failed: %s", region, e)
        return None


# --------------------------------------------------------------------------- #
# scorer — grade past-due theses vs realized proxy-vs-bench returns (region-aware)
# --------------------------------------------------------------------------- #
# Outcomes that are final once written to scored.jsonl. Mirrors engine.desk_scorer's
# append-only convention (theses.jsonl is the desk's; outcomes go to a separate file, one
# row per id) minus `expired` — see _prior_outcomes for why that one stays retryable.
_FINAL_OUTCOMES = ("hit", "miss", "unscored")


def _append_scored(d: Path, rows: list) -> None:
    """Append newly-final outcomes to the append-only scored.jsonl. Never raises: an
    unwritable audit trail must not cost us the track record."""
    if not rows:
        return
    try:
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "scored.jsonl", "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("thematic_desk scored append failed: %s", e)


def _eval(check: dict, entry: dict, check_by: str) -> dict | None:
    g = check.get("group", "yahoo")
    et, vs = check.get("subject_ticker"), check.get("vs")
    e0 = (entry or {}).get(et) or _close_asof(g, et, check.get("_asof"))
    b0 = (entry or {}).get(vs) or _close_asof(g, vs, check.get("_asof"))
    e1 = _close_on_or_after(g, et, check_by)
    b1 = _close_on_or_after(g, vs, check_by)
    if None in (e0, e1, b0, b1) or e0 == 0 or b0 == 0:
        return None
    realized = (e1 / e0 - 1.0) - (b1 / b0 - 1.0)
    op, thr = check.get("op"), float(check.get("threshold", 0.0))
    # FALSE if it moves the wrong way by ≥ threshold (inclusive at the boundary, matching
    # the documented "by ≥ threshold" falsifier spec).
    falsified = (realized <= thr) if op == "<" else (realized >= thr)
    dir_ok = (realized > 0) if op == "<" else (realized < 0)
    return {"outcome": "miss" if falsified else "hit", "realized": round(realized, 4),
            "directionally_correct": bool(dir_ok)}


def _bucket(rows: list) -> dict:
    dec = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    n = len(dec)
    hits = sum(1 for r in dec if r["outcome"] == "hit")
    dok = sum(1 for r in dec if r.get("directionally_correct"))
    return {"n": n, "hits": hits, "misses": n - hits,
            "hit_rate": round(hits / n, 3) if n else None,
            "dir_accuracy": round(dok / n, 3) if n else None}


def _calibration_note(overall: dict) -> str:
    if overall["n"] == 0:
        return ("No thematic theses scored yet — the track record begins once the first "
                "check-by dates pass. Until then every lean is a provisional hypothesis.")
    parts = [f"{overall['n']} scored, hit-rate {overall['hit_rate']} "
             f"(directional accuracy {overall['dir_accuracy']})."]
    if overall["n"] < 20:
        parts.append("Sample is small — treat conviction as provisional; the honest "
                     "expectation is no exploitable forward edge (display-only).")
    return " ".join(parts)


def _prior_outcomes(d: Path) -> dict:
    """Already-graded outcomes from scored.jsonl, by thesis id (last write wins).

    Only FINAL outcomes are read back. `open` is retried every run by definition, and
    `expired` here means the price plane could not value the thesis — which for this desk is
    emitted on the first unpriceable read, with none of desk_scorer's GRACE_BD business days
    of slack (URNM carries two such theses today, with no parquet on any plane). Freezing
    that would turn a collector gap into a permanent verdict, so it stays retryable."""
    out = {}
    try:
        for line in (d / "scored.jsonl").read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get("id") and r.get("outcome") in _FINAL_OUTCOMES:
                    out[r["id"]] = r
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001 — absent file is the cold-start case, not an error
        pass
    return out


def score_ledger(root=None, today=None) -> dict | None:
    """Grade every past-due, scorable thesis; write data/thematic_desk/track_record.json
    (overall + by_market + by_conviction) and append new outcomes to
    data/thematic_desk/scored.jsonl. Additive/idempotent; never raises."""
    root = Path(root) if root else config.ROOT
    today = pd.Timestamp(today) if today else pd.Timestamp(datetime.now(timezone.utc).date())
    d = Path(root).joinpath(*_LEDGER_DIR)
    lp = d / "theses.jsonl"
    if not lp.exists():
        return None
    try:
        rows = {}
        for line in lp.read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get("id"):
                    rows[r["id"]] = r            # dedupe by id (last wins)
            except Exception:  # noqa: BLE001
                pass
        prior = _prior_outcomes(d)
        scored, fresh = [], []
        for r in rows.values():
            check = (r.get("falsifier") or {}).get("check") or {}
            cb = r.get("check_by")
            base = {"id": r.get("id"), "market": r.get("market"), "subject": r.get("subject"),
                    "lean": r.get("lean"), "conviction": r.get("conviction"),
                    "kind": check.get("kind"), "check_by": cb}
            was = prior.get(r.get("id"))
            if was is not None:
                # A verdict is reached ONCE. The aggregation dimensions are re-read from the
                # ledger, but the OUTCOME is the one already published — a later re-adjustment
                # of the stored price history (yfinance re-bases the whole series on every
                # dividend; lib/store.upsert `overwrite_overlap`) must not silently rewrite a
                # grade the track record has already reported.
                scored.append({**base, **{k: was.get(k) for k in
                                          ("outcome", "realized", "directionally_correct")}})
                continue
            if check.get("kind") != "theme_rel_return" or not cb:
                row = {**base, "outcome": "unscored"}
            elif pd.Timestamp(cb) > today:
                row = {**base, "outcome": "open"}
            else:
                res = _eval({**check, "_asof": r.get("state_asof")},
                            r.get("entry_levels") or {}, cb)
                row = {**base, **(res or {"outcome": "expired"})}
            scored.append(row)
            if row.get("outcome") in _FINAL_OUTCOMES:
                fresh.append({**row, "scored_at": _now_iso()})
        _append_scored(d, fresh)
        dec = [s for s in scored if s.get("outcome") in ("hit", "miss")]
        overall = _bucket(dec)
        track = {
            "schema": SCHEMA, "as_of": today.date().isoformat(),
            "scored_total": len(dec),
            "open": sum(1 for s in scored if s.get("outcome") == "open"),
            "unscored_soft": sum(1 for s in scored if s.get("outcome") == "unscored"),
            "overall": overall,
            "by_market": {m: _bucket([s for s in dec if s.get("market") == m]) for m in REGION},
            "by_conviction": {c: _bucket([s for s in dec if s.get("conviction") == c])
                              for c in _CONVICTIONS},
            "calibration_note": _calibration_note(overall),
            "recent": [{k: s.get(k) for k in ("id", "market", "subject", "lean",
                        "conviction", "outcome", "realized", "check_by")}
                       for s in sorted(dec, key=lambda s: s.get("check_by") or "",
                                       reverse=True)[:12]],
        }
        out = d / "track_record.json"
        out.write_text(json.dumps(track, indent=2, default=str))
        # public copy for the page badge
        pub = Path(root) / "site" / "allocationdata" / "ai_desk_track.json"
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(json.dumps(track, default=str))
        return track
    except Exception as e:  # noqa: BLE001
        log.error("thematic_desk score_ledger failed: %s", e)
        return None
