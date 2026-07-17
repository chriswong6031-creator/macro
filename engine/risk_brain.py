"""Risk Brain — Claude/Opus reasoning desk for daily DRAWDOWN-RISK analysis.

LEAF · GATED · DEFAULT-OFF. The qualitative risk-officer layer that sits on top of
the deterministic risk stack (engine/risk_state.py, engine/mtf_monitor.py, GEX,
breadth, baskets, narrative rotation, standouts). After 2026-06-23 — a memory/semi
unwind the engine read too quietly — the dashboard should be "run daily by Opus
with clear risk analysis," not only by engines.

It reads a DETERMINISTIC EVIDENCE PACK (the engine's own outputs) and asks Opus to do
the judgement a transparent score can't:
  * a plain-English daily RISK READ (is drawdown risk building? where? why?);
  * does it AGREE with the engine's risk_state, or is the engine too quiet / too loud;
  * which themes / narratives are turning and should be RETIRED or down-weighted;
  * DOMINO / CONTAGION chains (e.g. memory → broad semis → AI capex → Nasdaq);
  * individual leaders WOBBLING under a still-firm index;
  * a bounded de-risk DIRECTIVE (posture + a subtract-only gross tilt) for the books.

EXTRACTOR + RISK OFFICER, NOT ORACLE. Every claim cites an evidence_id; the directive
is clamped in CODE (_reconcile_directive) so the model can only ever be MORE cautious
than the engine, never less — it can NOT tell the books to add risk into an elevated
engine state, and the gross tilt is subtract-only. The de-risk response is SIZING, never
stock selection. Output is FALSIFIABLE and logged to data/risk_brain/theses.jsonl so the
desk is graded against the tape, never assumed right. It writes site/riskdata/risk_brain.json
— a new artifact the Mastermind books read alongside data/regime/latest.json.risk_state.

AUTH: Claude via CLAUDE_CODE_OAUTH_TOKEN (SDK auth_token= + anthropic-beta oauth header)
or ANTHROPIC_API_KEY fallback. No key => graceful no-op (degraded artifact). Every public
function returns plain data or None and never raises into the pipeline.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser (leaf util)
from lib import config

log = logging.getLogger(__name__)

_DEFAULTS = {
    "enabled": False,                       # MASTER SWITCH — pipeline runs it only when true
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",     # fallback if no OAuth token
    "model": "claude-opus-4-8",
    "interval_days": 1,
    "max_tokens": 5000,
    "max_gross_tilt": 0.5,                  # cap on the subtract-only gross reduction the directive can imply
    "horizon_d": 21,                        # trading-day horizon for the falsifiable drawdown check
    "dd_threshold_pct": 5.0,                # the SPY drawdown the elevated-state thesis is graded on
    "oauth_pool_lane": "risk-brain",        # pool key expansion for this lane
    "usage_lane": "risk-brain",             # ai_costs attribution
}

DISCLAIMER = (
    "Context + risk posture — an AI risk-officer reading of the engine's own deterministic "
    "outputs, not a forecast and not stock selection. The directive is a SIZING posture, "
    "clamped in code so it can only be more cautious than the engine, never less. Every claim "
    "cites the evidence it is based on; graded against the tape over time. Treat as odds."
)

_RISK_SYSTEM = (
    "You are the daily RISK OFFICER for a solo top-down investor whose books take their "
    "signals from this dashboard. You are given an EVIDENCE PACK of the investor's own "
    "DETERMINISTIC risk outputs (a fused risk-state, a multi-timeframe technical monitor, "
    "dealer-gamma posture, breadth, thematic baskets, narrative rotation, and standout "
    "leaders). Your job: a clear DRAWDOWN-RISK read and a bounded de-risk posture.\n\n"
    "You are an EXTRACTOR + RISK OFFICER, NOT an oracle. Reason ONLY from the evidence, cite "
    "the evidence_id behind every claim (like [E3]); where the evidence is silent, say so. Do "
    "NOT use training-data knowledge about specific tickers as fact. Bias toward caution: a "
    "missed warning is worse than a false one here.\n\n"
    "Judge: (1) is drawdown risk building, and does the engine's risk_state UNDER- or OVER-state "
    "it? (2) which themes/narratives are turning and should be RETIRED or down-weighted "
    "(running on price, crowded, breaking down)? (3) is there a DOMINO/CONTAGION chain forming "
    "(name a from->to->mechanism)? (4) which leaders are WOBBLING under a still-firm index? (5) a "
    "DIRECTIVE: a sizing POSTURE in {risk-on, neutral, de-gross, defensive} and a subtract-only "
    "gross_tilt in [-1,0] (how much to cut gross; 0 = no cut). The directive is SIZING, never a "
    "stock list. Give a FALSIFIABLE check and a confidence.\n\n"
    "Return ONLY a JSON object (no fences) with keys:\n"
    '  risk_read: string (cite evidence_ids), risk_read_zh: string,\n'
    '  engine_agreement: "agree"|"engine_too_quiet"|"engine_too_loud",\n'
    '  brain_state: "risk-on"|"neutral"|"caution"|"elevated"|"risk-off",\n'
    '  themes_to_retire: array of strings, narratives_to_turn: array of strings,\n'
    '  contagion_chain: array of { from: string, to: string, mechanism: string },\n'
    '  wobbling_leaders: array of strings,\n'
    '  directive: { posture: "risk-on"|"neutral"|"de-gross"|"defensive", gross_tilt: number, '
    'favor: "entries"|"normal", avoid: array of strings, rationale: string },\n'
    '  evidence_ids: array of strings, dissent: string,\n'
    '  falsifiable_check: { confirm: string, disconfirm: string },\n'
    '  confidence: "LOW"|"MED"|"HIGH"'
)

_STATE_RANK = {"risk-on": 0, "neutral": 1, "caution": 2, "elevated": 3, "risk-off": 4}
_POSTURE_RANK = {"risk-on": 0, "neutral": 1, "de-gross": 3, "defensive": 4}
_RANK_POSTURE = {0: "risk-on", 1: "neutral", 2: "de-gross", 3: "de-gross", 4: "defensive"}


# --- config + client (mirrors narrative_brain) ---------------------------------
def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("risk_brain") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _make_call(cfg: dict):
    """Return a call(model, system, user) -> (text, degraded) callable, or None.

    Refactored to use llm_auth.build_providers for pool-aware failover and
    usage capture.  The external call signature is unchanged.
    """
    try:
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(cfg, opus_model=cfg.get("model", "claude-opus-4-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("risk_brain: provider build failed (%s)", e)
        return None
    if not providers:
        return None
    max_tokens = int(cfg.get("max_tokens", 5000))

    def call(model: str, system: str, user: str):
        def _call_fn(client, m: str):
            resp = client.messages.create(
                model=m, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "refusal", resp
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return (text, None, resp) if text else (None, "empty_reply", resp)

        # Override model on providers to use the requested model
        model_providers = [{**p, "model": model} for p in providers]
        try:
            text, reason, _ = llm_auth.make_call(
                model_providers, _call_fn, context="risk_brain")
            return text, reason
        except Exception as e:  # noqa: BLE001 — degrade, never raise
            log.warning("risk_brain call failed (%s): %s", model, e)
            return None, "llm_error"

    return call


# --- evidence assembly (deterministic; grounds the model) ----------------------
def _read_json(p: Path):
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def gather_evidence(root=None) -> dict | None:
    """Build the evidence pack from the engine's own outputs. Returns None when the
    risk_state is absent (no-data gate). Each item is evidence_id'd for citation."""
    base = Path(root) if root is not None else config.ROOT
    data = base / "data"
    latest = _read_json(data / "regime" / "latest.json")
    if not latest or not latest.get("risk_state"):
        log.info("risk_brain: no risk_state in latest.json — nothing to read")
        return None
    rs = latest.get("risk_state") or {}
    cond = latest.get("conditions") or {}
    mtf = _read_json(base / "site" / "riskdata" / "mtf_monitor.json") or {}
    gex = _read_json(base / "site" / "gex" / "index.json") or []
    baskets = _read_json(base / "site" / "basketdata" / "baskets.json") or {}
    alloc = _read_json(base / "site" / "allocationdata" / "allocation.json") or {}
    standouts = _read_json(base / "site" / "factordata" / "us_standouts.json") or {}

    ev = []
    drivers = ", ".join(f"{d.get('key')}({d.get('intensity')})" for d in (rs.get("drivers") or [])[:6])
    ev.append({"id": "E1", "text": f"Engine risk_state = {rs.get('state')} score {rs.get('score')}/100 "
                                   f"(alert {rs.get('alert')}); top drivers: {drivers or 'none'}."})
    comp = cond.get("complacency") or {}
    ev.append({"id": "E2", "text": f"Complacency gauge: state={comp.get('state')}, "
                                   f"breadth_div={comp.get('breadth_div')}, credit_widen={comp.get('credit_widen')}."})
    if mtf:
        breaking = [r.get("ticker") for g in (mtf.get("groups") or {}).values()
                    for r in g if r.get("tag") == "breakdown"][:12]
        ev.append({"id": "E3", "text": f"MTF monitor: {mtf.get('breakdown_count')} breakdowns, "
                                       f"{mtf.get('rolling_count')} rolling; index technical stress "
                                       f"{mtf.get('technical_intensity')}. Breaking down: {', '.join(breaking) or 'none'}."})
    if gex:
        spx = next((r for r in gex if r.get("key") == "SPX"), gex[0] if gex else {})
        ev.append({"id": "E4", "text": f"Dealer gamma (SPX): regime={spx.get('regime')}, "
                                       f"net GEX {spx.get('net_gex_bn')}bn, spot {spx.get('spot')} vs flip "
                                       f"{spx.get('gamma_flip')}, vol-hole={spx.get('vh_state')}."})
    ti = baskets.get("theme_intel") or {}
    if ti:
        rot = ti.get("rotation_5d") or ti.get("rotation") or {}
        ev.append({"id": "E5", "text": f"Thematic rotation (5d): {json.dumps(rot, default=str)[:300]}; "
                                       f"act-now: {json.dumps(ti.get('act_now'), default=str)[:200]}."})
    rk = alloc.get("rotation") or alloc.get("ranks") or {}
    if rk:
        ev.append({"id": "E6", "text": f"Narrative rotation: {json.dumps(rk, default=str)[:400]}."})
    if standouts:
        buys = [b.get("ticker") if isinstance(b, dict) else b for b in (standouts.get("buy") or [])][:10]
        ev.append({"id": "E7", "text": f"Standout buy board (gate_go={standouts.get('gate_go')}): "
                                       f"{', '.join(str(x) for x in buys) or 'none'}."})
    dl = latest.get("dislocation") or {}
    tp = latest.get("turning_point") or {}
    ev.append({"id": "E8", "text": f"Dislocation verdict={dl.get('verdict')} (active={dl.get('dislocation_active')}); "
                                   f"turning_point={tp.get('state')}; macro_risk={(latest.get('macro_risk') or {}).get('label')}."})

    return {"as_of": latest.get("date") or rs.get("asof"),
            "engine_state": rs.get("state"), "engine_score": rs.get("score"),
            "evidence": ev}


def _user_prompt(evidence: dict) -> str:
    lines = ["DAILY RISK EVIDENCE PACK (cite these ids):", ""]
    lines += [f"  [{e['id']}] {e['text']}" for e in evidence["evidence"]]
    lines += ["", f"Engine risk_state = {evidence.get('engine_state')} "
                  f"({evidence.get('engine_score')}/100). Do you agree, or is the engine too "
                  f"quiet / too loud? Give the risk read + bounded directive."]
    return "\n".join(lines)


# --- risk clamp (CODE, not prompt — the hard boundary) -------------------------
def _reconcile_directive(brief: dict, engine_state: str | None, cfg: dict) -> dict:
    """The model may be MORE cautious than the engine, never less. Clamp the posture up to
    the engine state, make gross_tilt subtract-only + bounded, and record any override."""
    d = brief.get("directive") or {}
    posture = d.get("posture") if d.get("posture") in _POSTURE_RANK else "neutral"

    # subtract-only, bounded gross tilt
    cap = float(cfg.get("max_gross_tilt", 0.5))
    try:
        tilt = float(d.get("gross_tilt", 0.0))
    except (TypeError, ValueError):
        tilt = 0.0
    tilt = max(-cap, min(0.0, tilt))   # never positive (can't add gross), never below -cap

    # clamp posture caution UP to the engine: the brain can't be less cautious than the engine.
    eng_rank = _STATE_RANK.get(engine_state, 1)
    floor_posture = _RANK_POSTURE.get(eng_rank, "neutral")
    override = None
    if _POSTURE_RANK.get(posture, 1) < _POSTURE_RANK.get(floor_posture, 1):
        override = (f"clamped: engine risk_state '{engine_state}' floors the posture at "
                    f"'{floor_posture}' (the brain may not be less cautious than the engine)")
        posture = floor_posture
    # an elevated+ engine implies a real cut even if the model left tilt at 0
    if eng_rank >= _STATE_RANK["elevated"] and tilt == 0.0:
        tilt = -min(cap, 0.25)
        override = override or "clamped: elevated engine state implies a non-zero gross cut"

    d["posture"] = posture
    d["gross_tilt"] = round(tilt, 3)
    if override:
        d["override_reason"] = override
    brief["directive"] = d
    return brief


# --- synthesis -----------------------------------------------------------------
def synthesize(evidence: dict, cfg: dict | None = None, call=None) -> dict:
    """Run the risk-officer desk (one Opus call). `call` is injectable (model, system,
    user) -> (text, degraded) for hermetic tests. Never raises."""
    cfg = cfg or _cfg()
    if call is None:
        call = _make_call(cfg)
    asof = (evidence or {}).get("as_of") or datetime.now(timezone.utc).date().isoformat()
    out = {"schema": "risk_brain.v1", "as_of": asof, "is_context_only": True,
           "disclaimer": DISCLAIMER, "engine_state": (evidence or {}).get("engine_state")}
    if call is None:
        out["degraded_reason"] = "no_client_or_key"
        return out
    if not evidence or not evidence.get("evidence"):
        out["degraded_reason"] = "no_evidence"
        return out

    text, degraded = call(cfg.get("model", "claude-opus-4-8"), _RISK_SYSTEM, _user_prompt(evidence))
    if not text:
        out["degraded_reason"] = degraded or "no_reply"
        return out
    a = _extract_json(text)
    if not a:
        out["degraded_reason"] = "unparseable_reply"
        return out
    a = _reconcile_directive(a, evidence.get("engine_state"), cfg)
    out.update(a)
    return out


# --- accountability ledger -----------------------------------------------------
def _append_ledger(brief: dict, cfg: dict, root=None) -> int:
    """Append a falsifiable thesis when the brain calls elevated+ risk: graded on whether SPY
    draws down >= dd_threshold within the horizon. Idempotent by id. Never raises."""
    if not brief or brief.get("degraded_reason"):
        return 0
    state = (brief.get("brain_state") or "").lower()
    if _STATE_RANK.get(state, 0) < _STATE_RANK["elevated"]:
        return 0   # only log a graded thesis when the brain actually calls drawdown risk
    asof = brief.get("as_of")
    horizon = int(cfg.get("horizon_d", 21))
    thr = float(cfg.get("dd_threshold_pct", 5.0))
    try:
        import pandas as pd
        check_by = (pd.Timestamp(asof) + pd.Timedelta(days=int(horizon * 1.6))).date().isoformat()
    except Exception:  # noqa: BLE001
        check_by = None
    row = {
        "id": f"{asof}-rb-state",
        "subject": "SPY", "subject_ticker": "SPY", "lean": "cautious",
        "conviction": (brief.get("confidence") or "low").lower(),
        "horizon_d": horizon, "thesis": brief.get("risk_read"),
        "brain_state": state, "engine_state": brief.get("engine_state"),
        "directive": brief.get("directive"),
        "falsifier": {"text": (brief.get("falsifiable_check") or {}).get("disconfirm"),
                      "check": {"kind": "max_drawdown", "subject_ticker": "SPY",
                                "op": ">=", "threshold": thr, "horizon_d": horizon}},
        "check_by": check_by, "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        p = (config.data_dir() if root is None else (Path(root) / "data")) / "risk_brain" / "theses.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        seen = set()
        if p.exists():
            for line in p.read_text().splitlines():
                try:
                    seen.add(json.loads(line).get("id"))
                except Exception:  # noqa: BLE001
                    continue
        if row["id"] in seen:
            return 0
        with p.open("a") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return 1
    except Exception as e:  # noqa: BLE001
        log.warning("risk_brain ledger append failed: %s", e)
        return 0


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gate (enabled + interval + no-data), synthesize, persist site/riskdata/risk_brain.json,
    append the falsifiable ledger. Never raises into the pipeline."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    base = Path(root) if root is not None else config.ROOT
    site = base / "site" / "riskdata" / "risk_brain.json"
    if not force and int(cfg.get("interval_days", 1)) > 1 and site.exists():
        try:
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(site.stat().st_mtime, timezone.utc)).days
            if age < int(cfg["interval_days"]):
                return _read_json(site)
        except Exception:  # noqa: BLE001
            pass
    evidence = gather_evidence(root=root)
    if evidence is None:
        return None
    brief = synthesize(evidence, cfg, call=call)
    if persist:
        try:
            site.parent.mkdir(parents=True, exist_ok=True)
            site.write_text(json.dumps(brief, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001
            log.warning("risk_brain persist failed: %s", e)
        _append_ledger(brief, cfg, root=root)
    return brief


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    res = run(force=a.force)
    if not res:
        print("risk_brain: disabled (set risk_brain.enabled + CLAUDE_CODE_OAUTH_TOKEN) or no risk_state")
    else:
        print(json.dumps({"degraded": res.get("degraded_reason"),
                          "brain_state": res.get("brain_state"),
                          "directive": res.get("directive")}, indent=2, default=str))
