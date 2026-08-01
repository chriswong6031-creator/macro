"""AI Desk — the accountable analyst layer (LLM Tier-C, CONTEXT-ONLY).

LEAF · GATED · DEFAULT-OFF · NEVER-SCORED. This is the inference layer that sits on
top of the dashboard's TRUST-GRADED detection engines and turns detection into
*falsifiable, accountable directional leans*:

  • Engine-1 thematic/sector flow  (engine.group_flow → site/basketdata/flow.json)
  • Engine-2 regime-snap relief radar (engine.regime_snap → data/regime/regime_snap.json)

Both were deliberately built DISPLAY-ONLY because Phase-0 validation proved they
DETECT where flow concentrates / when a relief snap fires but CANNOT predict forward
returns. The whole point of that discipline was to hand a trust-graded signal to a
layer that can make the durability judgement a mechanical leg structurally can't.

WHY THIS IS DIFFERENT FROM master_brain (the morning note): a fluent brief that
never learns it was wrong is a horoscope. Durability comes from a falsifiability
loop, the Phase-0 discipline applied to the AI's OWN output:

  Quant DETECTS (trust-graded) → AI JUDGES (accountable) → track-record GATES (later).

Every thesis the desk emits carries a CONDITIONAL DIRECTIONAL LEAN, a human
falsifier, AND an ENGINE-DERIVED machine-checkable predicate + a check-by date, and
is appended to data/ai_desk/theses.jsonl. A future scorer (Phase C,
engine.ai_desk_scorer) evaluates those predicates against realized closes and feeds
the measured hit-rate back into conviction. The ledger MUST start accruing the day
this ships — you cannot retro-fit falsifiers onto calls already made.

Discipline (mirrors master_brain + regime_snap_veto):
  * CONTEXT-ONLY — a lean is NEVER a number in any score / size / allocation; nothing
    in axes / regime / conditions imports this module. It writes a SEPARATE artifact.
  * NEVER SIZED, NEVER A TRADE — the output is a lean (overweight / underweight /
    fade-fear / avoid) and what would invalidate it, not a weight or an order.
  * GROUNDED + GUARD-RAILED — it reasons over the deterministic detector state and
    carries flow.json's own ai_handoff guardrails (do_not_conclude / ai_directive /
    caveats) INLINE, and is told to honour them and not to fabricate.
  * FIREWALLED + graceful — needs DEEPSEEK_API_KEY; absent the key, disabled, or with
    no detector artifacts present it returns None and never raises into the pipeline.
  * ACCOUNTABLE BY CONSTRUCTION — the MODEL authors the judgement; the ENGINE derives
    the machine-checkable falsifier from (subject, lean, horizon), so every logged
    thesis is scorable (or explicitly marked 'soft' → unscored, never fudged).

Runs on DeepSeek V4 Pro via its Anthropic-compatible endpoint by default (reuses
master_brain's client); one config line swaps it to Claude Opus.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config
from engine import master_brain as _mb          # reuse the DeepSeek/Anthropic client
from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser

log = logging.getLogger(__name__)

SCHEMA = "ai_desk.v1"
DISCLAIMER = (
    "AI desk note — context only, never scored or sized. The detectors it reads are "
    "DISPLAY-ONLY (flow has no validated forward edge; the relief snap is coincident). "
    "Each lean is a fallible, CHECKABLE judgement with a check-by date, not a trade "
    "recommendation or a position size.")

# Conditional directional leans (a lean is NEVER a size). 'neutral' is not a thesis —
# no-view belongs in regime_context, so theses must be one of these four.
_THESIS_LEANS = ("overweight", "underweight", "fade-fear", "avoid")
_CONVICTIONS = ("low", "medium", "high")

# GICS sector (exact flow.json name) -> SPDR sector ETF. All present in data/yahoo/.
_GICS_ETF = {
    "Energy": "XLE", "Information Technology": "XLK", "Financials": "XLF",
    "Health Care": "XLV", "Industrials": "XLI", "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP", "Utilities": "XLU", "Materials": "XLB",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}
_BENCH = "SPY"          # relative-return benchmark (data/yahoo/SPY.parquet)
_VIX = "_VIX"           # fear level for fade-fear theses (data/yahoo/_VIX.parquet)

_FLOW_PATH = ("site", "basketdata", "flow.json")
_SNAP_PATH = ("data", "regime", "regime_snap.json")
_TRACK_PATH = ("data", "ai_desk", "track_record.json")   # written by the Phase-C scorer


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    base = {
        "enabled": False,                 # MASTER SWITCH — pipeline runs it only when true
        "api_key_env": "DEEPSEEK_API_KEY",
        "llm_base_url": "https://api.deepseek.com/anthropic",
        "llm_model": "deepseek-v4-pro",
        "max_tokens": 8000,               # reasoning model — thinking tokens count vs cap
        "max_theses": 3,
        "interval_days": 1,               # regenerate the desk note every N days (1..7)
        "default_horizon_d": 20,
        "falsifier_defaults": {"rel_return": 0.05},   # ±5% rel move = the wrong-way threshold
        "panel": {"enabled": True},                   # Phase B: adversarial analyst panel
    }
    try:
        v = config.load().get("ai_desk", {}) or {}
    except Exception:  # noqa: BLE001 — config-less callers fall back to defaults
        v = {}
    return {**base, **v}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _desk_passport(desk_name: str) -> dict:
    """Honest conviction-provenance passport for a desk card (#41), derived from the outcome
    spine (measured · n / accruing · n=0). Degrade-never-raise → accruing on any failure."""
    try:
        from engine.passport import passport_from_spine
        return passport_from_spine(f"desk:{desk_name}", family=f"desk:{desk_name}")
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {"state": "accruing", "earned": False, "label_en": "accruing · n=0", "n": 0}


# --------------------------------------------------------------------------- #
# io helpers
# --------------------------------------------------------------------------- #
def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


def _regime_label(root) -> str | None:
    """The canonical macro regime quad at log time, stamped on each thesis so the Phase-C
    scorer can report hit-rate per regime. Thin alias over the shared engine.regime_label."""
    from engine.regime_label import quad_label
    return quad_label(root)


def _brief_age_days(prev) -> float | None:
    """Age in days of a previously-generated desk note from its `generated_at`. None
    when missing/unparseable (→ treat as DUE). Drives the regenerate-every-N-days gate."""
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


_BREADTH_MEMO: dict[str, object] = {}


def _breadth_frame(root):
    """The S&P 1500 close matrix (data/breadth/_closes_cache.parquet), memoized per
    root. Columns are tickers; lets the scorer resolve names beyond the ~153 yahoo
    parquets (e.g. individual semiconductors). None if the cache is absent."""
    key = str(root)
    if key not in _BREADTH_MEMO:
        val = None
        try:
            p = Path(root) / "data" / "breadth" / "_closes_cache.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                val = df.sort_index()
        except Exception:  # noqa: BLE001
            val = None
        _BREADTH_MEMO[key] = val
    return _BREADTH_MEMO[key]


def _close_series(ticker: str, root) -> pd.Series | None:
    """Closes for an instrument. Prefers the per-ticker yahoo parquet (cols are
    lowercase 'close'); falls back to the S&P 1500 breadth close cache so subjects
    beyond the ~153 yahoo names are still scorable; then to the China price
    parquets (data/china_stocks/<ticker>.parquet A-share OHLCV, data/china/<t>.parquet
    for CN benches like 510300.SS) so the qledger grader can price China
    event-move claims and their 510300.SS benchmark. None if none has it."""
    try:
        df = pd.read_parquet(Path(root) / "data" / "yahoo" / f"{ticker}.parquet")
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:  # noqa: BLE001
        pass
    bf = _breadth_frame(root)                       # additive fallback; yahoo names unaffected
    if bf is not None and ticker in getattr(bf, "columns", []):
        s = bf[ticker].dropna()
        if len(s):
            return s.sort_index()
    # China parquets — additive fallback, only reached when yahoo/breadth miss.
    for sub in ("china_stocks", "china"):
        try:
            df = pd.read_parquet(Path(root) / "data" / sub / f"{ticker}.parquet")
            s = df["close"].dropna()
            s.index = pd.to_datetime(s.index)
            if len(s):
                return s.sort_index()
        except Exception:  # noqa: BLE001
            continue
    return None


def _level_asof(ticker: str, root, asof) -> float | None:
    s = _close_series(ticker, root)
    if s is None or s.empty:
        return None
    try:
        s = s[s.index <= pd.Timestamp(asof)]
        return round(float(s.iloc[-1]), 4) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# STAGE 0 — the briefing bus (artifact-driven, graceful degrade)
# --------------------------------------------------------------------------- #
def _slim_group(g: dict) -> dict:
    return {k: g.get(k) for k in (
        "name", "name_zh", "type", "id", "stage", "read_quality", "rs_pctile",
        "cohesion", "cohesion_chg", "leadership", "cohesion_gate",
        "directional", "directional_confidence") if k in g}


def _flow_view(flow) -> dict | None:
    """Compact the Engine-1 handoff: the groups + the cross-group structure + the
    guardrails the AI must honour (carried INLINE so it cannot escape them)."""
    if not isinstance(flow, dict):
        return None
    ah = flow.get("ai_handoff") or {}
    sectors = sorted(flow.get("sectors") or [], key=lambda g: g.get("read_quality", 0), reverse=True)
    baskets = sorted(flow.get("baskets") or [], key=lambda g: g.get("read_quality", 0), reverse=True)
    return {
        "as_of": flow.get("as_of"),
        "verdict": flow.get("verdict"),
        "regime": flow.get("regime"),
        "cluster": flow.get("cluster"),
        "sectors": [_slim_group(g) for g in sectors],
        "baskets": [_slim_group(g) for g in baskets],
        "emerging": flow.get("emerging"),
        "cooling": flow.get("cooling"),
        "guardrails": {
            "overall_verdict": ah.get("overall_verdict"),
            "reader_contract": ah.get("reader_contract"),
            "do_not_conclude": ah.get("do_not_conclude"),
            "ai_directive": ah.get("ai_directive"),
            "caveats": ah.get("caveats"),
        },
    }


def _snap_view(snap) -> dict | None:
    """Compact the Engine-2 relief-radar snapshot (+ its AI veto if present)."""
    if not isinstance(snap, dict):
        return None
    keys = ("status", "snap", "relief_magnitude", "fear_built", "fear_rebuilding",
            "vel_pctile", "legs_up", "legs_total", "cap_recent", "vix_term", "veto")
    view = {k: snap.get(k) for k in keys if k in snap}
    return view or None


def gather_desk_state(root=None) -> dict | None:
    """Assemble the point-in-time bundle from the trust-graded detector artifacts +
    the desk's own track record. Each source is OPTIONAL; returns None only when no
    detector artifact is present (nothing to brief on)."""
    root = Path(root) if root else config.ROOT
    fv = _flow_view(_read_json(root.joinpath(*_FLOW_PATH)))
    sv = _snap_view(_read_json(root.joinpath(*_SNAP_PATH)))
    if fv is None and sv is None:
        return None
    track = _read_json(root.joinpath(*_TRACK_PATH))   # None until Phase C
    return {
        "as_of": (fv or {}).get("as_of") or (sv or {}).get("as_of"),
        "flow": fv,
        "regime_snap": sv,
        "track_record": track if isinstance(track, dict) else None,
        "sources_present": {"flow": fv is not None, "regime_snap": sv is not None},
    }


# --------------------------------------------------------------------------- #
# the falsifier contract — the ENGINE derives a machine-checkable predicate from
# (subject, lean, horizon), so every logged thesis is scorable by construction.
# A `check` describes the condition under which the thesis is FALSE: the Phase-C
# scorer marks `miss` when op(realized, threshold) is True, else `hit`; kind='soft'
# is logged but never scored.
# --------------------------------------------------------------------------- #
def _resolve_subject(subject: str):
    """-> (ticker, vs, kind). kind in {'rel_return','level','soft'}."""
    if subject in _GICS_ETF:
        return _GICS_ETF[subject], _BENCH, "rel_return"
    if subject.strip().lower() in ("vix", "fear", "fade-fear"):
        return _VIX, None, "level"
    return None, None, "soft"      # baskets / anything not closeable → soft, unscored


def _derive_check(subject: str, lean: str, horizon: int, cfg: dict) -> dict:
    fd = cfg.get("falsifier_defaults", {}) or {}
    thr = float(fd.get("rel_return", 0.05))
    ticker, vs, kind = _resolve_subject(subject)
    if kind == "rel_return":
        if lean == "overweight":                      # expect outperformance
            op, threshold = "<", -thr                 # FALSE if it underperforms by ≥ thr
        elif lean in ("underweight", "avoid"):        # expect underperformance
            op, threshold = ">", thr                  # FALSE if it outperforms by ≥ thr
        else:
            return {"kind": "soft", "reason": f"lean '{lean}' has no relative-return rule"}
        return {"kind": "rel_return", "subject_ticker": ticker, "vs": vs,
                "op": op, "threshold": threshold, "horizon_d": horizon}
    if kind == "level":
        if lean == "fade-fear":                       # expect fear to ebb
            return {"kind": "level", "subject_ticker": ticker, "vs": None,
                    "op": ">", "ref": "entry", "horizon_d": horizon,
                    "note": "FALSE if VIX makes a new high above the entry level within horizon"}
        return {"kind": "soft", "reason": f"lean '{lean}' has no level rule for {ticker}"}
    return {"kind": "soft", "reason": "subject not resolvable to a closeable instrument"}


def _check_by(asof, horizon: int) -> str | None:
    try:
        return (pd.Timestamp(asof) + pd.offsets.BusinessDay(int(horizon))).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _build_thesis(t: dict, i: int, asof, cfg: dict) -> dict | None:
    """Validate one model-authored thesis and attach the engine-derived falsifier.
    Returns None for malformed / non-directional entries (accountability is mandatory:
    every kept thesis carries a falsifier)."""
    if not isinstance(t, dict):
        return None
    subject = str(t.get("subject") or "").strip()
    lean = str(t.get("lean") or "").strip().lower()
    if not subject or lean not in _THESIS_LEANS:
        return None
    try:
        horizon = int(t.get("horizon_d") or cfg.get("default_horizon_d", 20))
    except Exception:  # noqa: BLE001
        horizon = int(cfg.get("default_horizon_d", 20))
    horizon = max(5, min(60, horizon))
    conv = str(t.get("conviction") or "low").strip().lower()
    if conv not in _CONVICTIONS:
        conv = "low"
    return {
        "id": f"{asof}-{i + 1}",
        "subject": subject,
        "lean": lean,
        "conviction": conv,
        "horizon_d": horizon,
        "thesis": t.get("thesis"),
        "evidence": [str(e) for e in (t.get("evidence") or []) if e],
        "dissent": t.get("dissent"),
        "falsifier": {"text": t.get("falsifier_text"),
                      "check": _derive_check(subject, lean, horizon, cfg)},
        "check_by": _check_by(asof, horizon),
    }


# --------------------------------------------------------------------------- #
# STAGE 1 — the analyst (single structured DeepSeek call; panel is Phase B)
# --------------------------------------------------------------------------- #
_SCHEMA_TAIL = (
    "Return ONLY a JSON object (no markdown fences) with keys:\n"
    "  regime_context: string — 1-2 sentences on what the detectors actually show "
    "(grounded; no invented levels or numbers; this is where any no-view goes).\n"
    "  theses: array of 0..N objects (omit rather than pad — honesty over content), each:\n"
    "     subject: string — EXACTLY one of the sector names provided in flow.sectors, "
    "or \"VIX\" for a relief/fade-fear call. Prefer these (machine-checkable).\n"
    "     lean: one of \"overweight\",\"underweight\",\"avoid\" (for a sector) or "
    "\"fade-fear\" (only for subject \"VIX\"). A lean is a DIRECTION, never a size.\n"
    "     conviction: one of \"low\",\"medium\",\"high\" — be modest; default low when "
    "the catalyst is illegible or the detectors are display-only.\n"
    "     horizon_d: integer trading days, 5..60.\n"
    "     thesis: string — the reasoning, naming WHICH detector leg supports it.\n"
    "     evidence: array of strings (cite the specific leg / cluster / snap state).\n"
    "     dissent: string — the single strongest contrary case.\n"
    "     falsifier_text: string — one concrete condition that would prove this wrong, "
    "phrased as the plain condition itself. This text is shown to users under a 'Changes "
    "this read' label: never write the words 'falsified', 'falsify' or 'refuted' in it.\n"
    "  confidence: one of \"low\",\"medium\",\"high\"."
)

_SYSTEM = (
    "You are the analyst running a markets DESK note for a solo top-down trader. You "
    "are handed the trader's OWN deterministic detector state: a thematic/sector FLOW "
    "lens and a relief-radar REGIME-SNAP snapshot. Your job is to turn that detection "
    "into a SHORT set of accountable, FALSIFIABLE directional leans.\n\n"
    "CRITICAL — these detectors are TRUST-GRADED and DISPLAY-ONLY:\n"
    "- The flow lens has NO validated forward edge (rank-IC ~0 on the unbiased "
    "point-in-time sector universe). It tells you WHERE flow is concentrating, not "
    "what it will do next. The relief snap is COINCIDENT — it confirms a risk-on move "
    "is happening, it does not predict that it lasts.\n"
    "- Therefore you must NOT claim the detectors 'predict' or 'signal' returns. Honour "
    "every item in flow.guardrails.do_not_conclude and flow.guardrails.ai_directive. "
    "Your leans are YOUR fallible judgement EXPRESSED AS FALSIFIABLE CONDITIONALS — not "
    "edge extracted from the detectors.\n\n"
    "Rules:\n"
    "- Reason ONLY over the provided JSON state + well-known market structure. NEVER "
    "fabricate a level, score, or event. If the state doesn't support a view, say so "
    "and return fewer (or zero) theses.\n"
    "- Do NOT rank sectors against baskets (different universes; baskets are hindsight-"
    "curated). Do NOT treat a narrow / high-HHI single-name move as a theme.\n"
    "- NEVER give a position size, weight, dollar amount, or fire a trade — the "
    "deterministic system owns sizing. Give a DIRECTION and what would invalidate it.\n"
    "- Each thesis needs an honest DISSENT (the best bear case) and a CONCRETE "
    "falsifier. Prefer sector or VIX subjects so the call can be scored.\n"
    "- If a track_record is present in the state, CALIBRATE conviction to it (if past "
    "high-conviction calls missed, default lower).\n"
    "- Be honest about small samples and conflicts. This note will be graded against "
    "reality, so do not over-claim.\n\n"
    + _SCHEMA_TAIL
)


def _build_user(state: dict) -> str:
    return ("Today's trust-graded detector state (JSON). Produce your desk note per "
            "your instructions — accountable, falsifiable, never sized.\n<state>\n"
            + json.dumps(state, indent=2, default=str) + "\n</state>")


def _source_verdicts(state: dict) -> dict:
    out = {}
    fv = state.get("flow")
    if isinstance(fv, dict):
        out["flow"] = (fv.get("guardrails") or {}).get("overall_verdict") or fv.get("verdict")
    if isinstance(state.get("regime_snap"), dict):
        out["regime_snap"] = "coincident"
    return out


# --------------------------------------------------------------------------- #
# STAGE 1b — the adversarial PANEL (Phase B). Four independent analysts argue the
# SAME bundle from distinct mandates; a DESK-HEAD adjudicator collapses them into the
# final theses, preserving the skeptic's objection as dissent and gating conviction
# on disagreement. The adjudicator emits the SAME schema as the single analyst, so
# the falsifier / ledger / scorer downstream are untouched. Falls back to the single
# analyst if the panel is disabled or unavailable.
# --------------------------------------------------------------------------- #
_PANEL_CAVEAT = (
    "The detectors are TRUST-GRADED and DISPLAY-ONLY: the flow lens has NO validated "
    "forward edge (rank-IC ~0 on the unbiased point-in-time sector universe) and the "
    "relief snap is COINCIDENT. Reason ONLY over the provided JSON state; never "
    "fabricate levels or events; honour flow.guardrails; never give a size or a trade. "
    "Subjects must be sector names from flow.sectors (or \"VIX\" for a fear call). ")

_PANEL_TAIL = (
    "Return ONLY a JSON object (no fences): {\"stance\": \"<= 2 sentences, the read "
    "from THIS lens only\", \"candidates\": [{\"subject\": \"<sector name or VIX>\", "
    "\"lean\": \"overweight|underweight|avoid|fade-fear|none\", \"rationale\": \"<1 "
    "sentence>\", \"strength\": \"weak|moderate|strong\"}], \"key_risk\": \"<the one "
    "thing that would break this lens's read>\"}")

_PANEL_SYSTEMS = {
    "opportunity": (
        "ROLE: OPPORTUNITY analyst on a markets desk. Argue the STRONGEST honest case "
        "FOR a durable directional lean given where flow is concentrating and any "
        "relief snap. Be specific about which leg supports each idea. " + _PANEL_CAVEAT
        + _PANEL_TAIL),
    "skeptic": (
        "ROLE: SKEPTIC analyst. Your job is to FALSIFY, not to balance. For each "
        "apparent opportunity argue why it is a TRAP: already priced-in, coincident not "
        "predictive, a survivorship artifact, narrow / single-name (not a theme), or "
        "mean-reverting. Name the candidates you would FADE. " + _PANEL_CAVEAT
        + _PANEL_TAIL),
    "base_rate": (
        "ROLE: BASE-RATE analyst. Ignore the narrative. Ask what this SETUP "
        "unconditionally resolves to and anchor on base rates, not the story. "
        "EXPLICITLY weigh that the flow lens is display-only (rank-IC ~0) and the snap "
        "is coincident — so the prior on any edge is weak. " + _PANEL_CAVEAT
        + _PANEL_TAIL),
    "structural": (
        "ROLE: STRUCTURAL analyst. Read ONLY the cross-group cluster map and leadership "
        "breadth. Distinguish genuine co-movement (a supply-chain / theme spread) from a "
        "narrow, high-HHI single-name mirage; say which group actually leads. "
        + _PANEL_CAVEAT + _PANEL_TAIL),
}

_ADJ_SYSTEM = (
    "ROLE: DESK HEAD adjudicator. Four independent analysts (opportunity, skeptic, "
    "base-rate, structural) have argued over the SAME trust-graded detector state; "
    "their JSON stances are given alongside the raw state. Synthesize the FINAL set of "
    "accountable, FALSIFIABLE directional leans for a solo top-down trader.\n\n"
    "Rules:\n"
    "- Keep a lean ONLY if it survives the SKEPTIC. Put the skeptic's strongest "
    "objection to that specific lean in `dissent` — do not soften it.\n"
    "- Calibrate conviction DOWN on disagreement: when analysts conflict, when the "
    "base-rate analyst flags ~0 IC / display-only, or when the move is narrow / "
    "single-name. Reserve \"high\" for genuine multi-analyst agreement (it should be "
    "rare). Default \"low\".\n"
    "- If a track_record is present, calibrate to it (past high-conviction misses → "
    "lean lower).\n"
    "- In `evidence`, cite which analyst and which detector leg supports each lean. "
    "Honour flow.guardrails. NEVER a position size, weight, or trade.\n"
    "- Prefer sector or VIX subjects (machine-checkable). Omit theses rather than pad "
    "— honesty over content.\n\n"
    + _SCHEMA_TAIL)


def _run_panel(state: dict, cfg: dict, call=None) -> dict:
    """Run the four analysts over the same bundle (in parallel). Returns
    {key: stance_dict|None}; never raises."""
    fn = call or _mb._call_model
    user = _build_user(state)

    def _one(key):
        try:
            reply, _ = fn(_PANEL_SYSTEMS[key], user, cfg)
            if reply is None:
                return key, None
            parsed = _extract_json(reply)
            return key, (parsed if isinstance(parsed, dict) else None)
        except Exception:  # noqa: BLE001 — one analyst failing must not sink the panel
            return key, None

    keys = list(_PANEL_SYSTEMS)
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(keys)) as ex:
            results = list(ex.map(_one, keys))
    except Exception:  # noqa: BLE001 — fall back to sequential if threads unavailable
        results = [_one(k) for k in keys]
    return dict(results)


def _adjudicate(state: dict, panel: dict, cfg: dict, call=None):
    """DESK-HEAD synthesis over the panel + raw state → (reply_text, degraded_reason)."""
    fn = call or _mb._call_model
    payload = {"detector_state": state,
               "analyst_panel": {k: v for k, v in panel.items() if v}}
    user = ("The detector state and the four analysts' stances (JSON). Adjudicate into "
            "the FINAL falsifiable leans per your instructions.\n<input>\n"
            + json.dumps(payload, indent=2, default=str) + "\n</input>")
    return fn(_ADJ_SYSTEM, user, cfg)


def synthesize(state: dict, cfg: dict | None = None, call=None) -> dict:
    """Run the analyst over a gathered state. Always returns a brief record (degraded
    fields flagged); never raises. `call` is injectable (defaults to
    master_brain._call_model) so tests run without an API key."""
    cfg = {**(cfg or _cfg()), "usage_stage": "ai-desk"}  # cost drill-down tag
    asof = state.get("as_of")
    brief = {
        "schema": SCHEMA, "is_context_only": True,
        "generated_at": _now_iso(), "state_asof": asof,
        "model": cfg.get("llm_model", "deepseek-v4-pro"),
        "regime_context": None, "theses": [],
        "source_verdicts": _source_verdicts(state),
        "track_record": state.get("track_record"),     # injected by Phase-C scorer; else None
        # #41 badge honesty: the desk's conviction badge carries an honest provenance passport
        # (measured · n / accruing · n=0) derived from the outcome spine, so a cold desk's
        # conviction can't read as an earned number. Shared helper, not a per-page patch.
        "passport": _desk_passport("ai_desk"),
        "confidence": "low",
        "raw_text": None, "degraded_reason": None, "disclaimer": DISCLAIMER,
    }
    panel_on = bool((cfg.get("panel") or {}).get("enabled", True))
    if panel_on:
        panel = _run_panel(state, cfg, call)
        brief["panel"] = {k: v for k, v in panel.items() if v}     # transparency for the page
        if any(panel.values()):
            reply, reason = _adjudicate(state, panel, cfg, call)   # desk-head synthesis
        else:                                                      # whole panel unavailable
            reply, reason = (call or _mb._call_model)(_SYSTEM, _build_user(state), cfg)
    else:
        reply, reason = (call or _mb._call_model)(_SYSTEM, _build_user(state), cfg)
    brief["raw_text"] = reply
    if reply is None:
        brief["degraded_reason"] = reason
        return brief
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        brief["degraded_reason"] = reason or "unparseable_reply"
        return brief
    brief["regime_context"] = parsed.get("regime_context")
    conf = str(parsed.get("confidence") or "low").strip().lower()
    brief["confidence"] = conf if conf in _CONVICTIONS else "low"
    raw_theses = parsed.get("theses") if isinstance(parsed.get("theses"), list) else []
    theses = []
    for i, t in enumerate(raw_theses[: int(cfg.get("max_theses", 3))]):
        th = _build_thesis(t, len(theses), asof, cfg)
        if th is not None:
            theses.append(th)
    brief["theses"] = theses
    if reason:
        brief["degraded_reason"] = reason
    return brief


# --------------------------------------------------------------------------- #
# STAGE 3 — the append-only ledger (the durability substrate; scored in Phase C)
# --------------------------------------------------------------------------- #
def _entry_levels(check: dict, asof, root) -> dict:
    """Snapshot the entry closes the Phase-C scorer needs to evaluate the predicate."""
    out = {}
    for key in ("subject_ticker", "vs"):
        t = check.get(key)
        if t:
            lv = _level_asof(t, root, asof)
            if lv is not None:
                out[t] = lv
    return out


def _append_ledger(brief: dict, root) -> None:
    """Append each thesis to data/ai_desk/theses.jsonl. Never fatal."""
    theses = brief.get("theses") or []
    if not theses:
        return
    try:
        d = Path(root) / "data" / "ai_desk"
        d.mkdir(parents=True, exist_ok=True)
        asof = brief.get("state_asof")
        regime = _regime_label(root)
        with open(d / "theses.jsonl", "a") as fh:
            for t in theses:
                check = (t.get("falsifier") or {}).get("check") or {}
                row = {
                    "id": t["id"], "logged_at": brief["generated_at"], "state_asof": asof,
                    "subject": t["subject"], "lean": t["lean"],
                    "conviction": t["conviction"], "horizon_d": t["horizon_d"],
                    "falsifier": t["falsifier"], "check_by": t["check_by"],
                    "entry_levels": _entry_levels(check, asof, root),
                    "regime": regime,            # macro regime at log time → by_regime track record
                    "status": "open", "scored_at": None, "outcome": None, "realized": None,
                }
                fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("ai_desk ledger append failed: %s", e)


def _persist(brief: dict, root) -> None:
    try:
        out = Path(root) / "data" / "regime" / "ai_desk.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(brief, indent=2, default=str))
        site = Path(root) / "site"
        if site.is_dir():                                   # public copy (Phase-D page); drop raw_text
            pub = {k: v for k, v in brief.items() if k != "raw_text"}
            (site / "ai_desk.json").write_text(json.dumps(pub, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("ai_desk persist failed: %s", e)


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gather → synthesize → persist + append the ledger. Returns the brief, or None
    when disabled (unless `force`) or no detector artifact is present. NEVER raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    try:
        root = Path(root) if root else config.ROOT
        # Interval gate — only regenerate every N days (1..7). When the prior note is
        # younger than the interval, skip the LLM call AND the ledger append (avoids
        # duplicate theses corrupting the Phase-C scorer); the committed ai_desk.json
        # stays live and deploys unchanged. `force` always bypasses the gate.
        if not force:
            try:
                interval = max(1, min(7, int(cfg.get("interval_days", 1))))
            except Exception:  # noqa: BLE001
                interval = 1
            if interval > 1:
                prev = _read_json(Path(root) / "data" / "regime" / "ai_desk.json")
                age = _brief_age_days(prev)
                if age is not None and age < interval:
                    log.info("ai_desk: note is %.1fd old (< %dd interval) — skipping "
                             "regen, keeping prior note", age, interval)
                    return prev
        state = gather_desk_state(root)
        if state is None:
            log.info("ai_desk: no flow/regime_snap artifacts present — nothing to brief")
            return None
        brief = synthesize(state, cfg, call=call)
        if persist:
            _persist(brief, root)
            _append_ledger(brief, root)
        return brief
    except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
        log.error("ai_desk run failed: %s", e)
        return None


def render_markdown(brief: dict) -> str:
    if not brief:
        return "_no desk note_"
    if brief.get("degraded_reason") and not brief.get("regime_context"):
        return f"_ai desk unavailable: {brief['degraded_reason']}_"
    L = [f"# AI Desk — {brief.get('state_asof', '?')} ({brief.get('model', '?')})", ""]
    if brief.get("regime_context"):
        L += [brief["regime_context"], ""]
    if not brief.get("theses"):
        L += ["_no actionable leans today._", ""]
    for t in brief.get("theses") or []:
        chk = (t.get("falsifier") or {}).get("check") or {}
        L += [f"## {t['subject']} — {t['lean']} "
              f"(conviction {t['conviction']}, {t['horizon_d']}d)",
              t.get("thesis") or "",
              f"- evidence: {'; '.join(t.get('evidence') or []) or '—'}",
              f"- dissent: {t.get('dissent') or '—'}",
              f"- falsifier: {(t.get('falsifier') or {}).get('text') or '—'} "
              f"→ check by {t.get('check_by')}",
              f"- machine-check: `{chk.get('kind')}` {json.dumps({k: chk[k] for k in chk if k != 'note'})}",
              ""]
    L += [f"_confidence: {brief.get('confidence', '?')} · context only, never scored or sized_"]
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    logging.basicConfig(level=logging.INFO)
    _force = "--force" in sys.argv[1:]
    _b = run(persist=True, force=_force)
    if _b is None:
        print("ai_desk disabled (set ai_desk.enabled: true or pass --force) "
              "or no detector artifacts present.")
    else:
        print(render_markdown(_b))
