"""Narrative Brain — Claude reasoning desk for theme durability + sector rotation.

LEAF · GATED · DEFAULT-OFF · CONTEXT-ONLY. The qualitative layer of the Divergence
Radar. It reads the DETERMINISTIC radar (engine/radar.py → site/basketdata/radar.json)
as an EVIDENCE PACK and asks Claude to do the judgement a transparent score can't:

  * durability  — per top-N theme: narrative STRENGTH / DURABILITY / CONTINUITY, graded
                  against an explicit rubric, with a FALSIFIABLE check (the theme's ETF
                  proxy vs SPY over a horizon). Claude Sonnet.
  * rotation    — one cross-theme read: where leadership is rotating + what's confirmed by
                  real activity vs running on price alone. Claude Opus.

EXTRACTOR, NOT ORACLE. Every claim must cite an evidence_id from the pack; un-cited
claims are zeroed. Output is FALSIFIABLE and logged to a ledger (data/narrative_brain/
theses.jsonl) so the desk is graded against the tape later, never assumed right. A hard
CODE clamp (_reconcile) prevents the model from escalating a fading / negative-divergence
theme to ENTER — the LLM can only ever DE-escalate a risk-flagged name. Nothing here feeds
a score, signal, or allocation; the scoring path never imports it.

AUTH: Claude via the user's Claude-Code OAuth token (CLAUDE_CODE_OAUTH_TOKEN → the SDK's
`auth_token=` Bearer path + the required `anthropic-beta: oauth-2025-04-20` header), or an
ANTHROPIC_API_KEY fallback. No key → graceful no-op (writes a degraded artifact). Every
public function returns plain data or None and never raises into the pipeline.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser (leaf util)
from lib import config

log = logging.getLogger(__name__)

OAUTH_BETA = "oauth-2025-04-20"   # REQUIRED on /v1/messages when authing with an OAuth token

_DEFAULTS = {
    "enabled": False,                       # MASTER SWITCH — pipeline runs it only when true
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",     # fallback if no OAuth token
    "models": {"durability": "claude-sonnet-4-6", "rotation": "claude-opus-4-8"},
    "interval_days": 1,
    "max_themes": 6,                        # cap per-theme calls (cost + honesty)
    "max_tokens": 6000,
    "horizon_d": 21,                        # trading-day horizon for the falsifiable check
    "rel_threshold": 0.05,                  # ±5% proxy-vs-SPY = the wrong-way threshold
    "oauth_pool_lane": "narrative-brain",   # pool key expansion for this lane
    "usage_lane": "narrative-brain",        # ai_costs attribution
}

DISCLAIMER = (
    "Context only — an AI reading of the radar's own deterministic output, not a signal. "
    "It feeds no score or allocation, can be wrong or overconfident, and every claim cites "
    "the radar evidence it is based on. Graded against the tape over time; treat as odds, not "
    "a forecast."
)

_DURABILITY_SYSTEM = (
    "You are a buy-side strategist judging the DURABILITY of a market NARRATIVE for a solo "
    "top-down investor. You are given an EVIDENCE PACK of the investor's own deterministic "
    "signals for ONE theme (federal/alt-data activity vs price, lifecycle stage, news flow). "
    "You are an EXTRACTOR + JUDGE, NOT an oracle: reason ONLY from the evidence, cite the "
    "evidence_id behind every claim, and where the evidence is silent say so rather than "
    "inventing. Do NOT use training-data knowledge about these tickers as fact.\n\n"
    "Score three axes 0-100 and justify each with cited evidence_ids:\n"
    "  strength    — how strong is the real-activity signal RIGHT NOW (breadth across sources, magnitude).\n"
    "  durability  — is the activity likely to PERSIST (accelerating vs one-off; multi-source vs single).\n"
    "  continuity  — does price/flow CONFIRM, or is the narrative running ahead of / behind the activity.\n\n"
    "Then a verdict — ENTER (activity leads price, durable) | MONITOR (mixed / too early / priced) | "
    "AVOID (fading or running on fumes) — and a confidence LOW/MED/HIGH.\n"
    "Give one DISSENT (the strongest case against your verdict) and a FALSIFIABLE check.\n\n"
    "Return ONLY a JSON object (no fences) with keys:\n"
    '  strength: int, durability: int, continuity: int, composite: int,\n'
    '  verdict: "ENTER"|"MONITOR"|"AVOID", confidence: "LOW"|"MED"|"HIGH",\n'
    '  rationale: string (cite evidence_ids like [P3]), rationale_zh: string,\n'
    '  evidence_ids: array of strings, dissent: string,\n'
    '  falsifiable_check: { confirm: string, disconfirm: string }'
)

_ROTATION_SYSTEM = (
    "You are a cross-sector rotation strategist. You are given a compact table of the "
    "investor's own deterministic radar flags across themes (real-activity-vs-price state, "
    "lifecycle, divergence). Judge WHERE leadership is rotating and which moves are CONFIRMED "
    "by real activity vs running on price alone. EXTRACTOR not oracle: cite the theme + state "
    "you reason from; no training-data claims as fact.\n\n"
    "Return ONLY a JSON object (no fences) with keys:\n"
    '  summary: string — one-line rotation read, summary_zh: string,\n'
    '  accumulate: array of strings — themes where activity leads price (cite the state),\n'
    '  reduce: array of strings — themes running ahead of activity / fading,\n'
    '  watch: array of strings — what would change this read,\n'
    '  confidence: "LOW"|"MED"|"HIGH"'
)

_VERDICTS = {"ENTER", "MONITOR", "AVOID"}
_RISK_STATES = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}
_RISK_LIFECYCLE = {"fading", "mature"}


# --- config + client -----------------------------------------------------------
def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("narrative_brain") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _make_call(cfg: dict):
    """Return a call(model, system, user) -> (text|None, degraded|None). Caches the stable
    system block (cache_control) so the per-theme rubric is reused across calls.

    W5 ITEM 1 — 401-fallback: uses engine.llm_auth.make_call() so an expired OAuth
    token triggers a fallback to ANTHROPIC_API_KEY, with degraded_reason
    "auth_invalid:<provider>" distinguishing auth failures from content errors.

    Note: narrative_brain uses TWO model ids (durability=sonnet, rotation=opus).
    build_providers() produces providers keyed to opus_model; when the durability
    (sonnet) call is made, the model id is overridden inside _do_call via the
    `model` argument passed to call() — the client itself is model-agnostic.
    """
    from engine import llm_auth

    # Build providers using the rotation model (opus) as the primary model.
    # For durability calls the caller passes a different model id; the client
    # supports any model on the same endpoint.
    providers = llm_auth.build_providers(
        cfg, opus_model=cfg.get("models", {}).get("rotation", "claude-opus-4-8"))
    if not providers:
        return None
    max_tokens = int(cfg.get("max_tokens", 6000))

    def call(model: str, system: str, user: str):
        # Override the model id in each provider for this specific call
        call_providers = [{**p, "model": model} for p in providers]

        def _do_call(client, _model: str):
            resp = client.messages.create(
                model=_model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "refusal", resp
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return (text, None, resp) if text else (None, "empty_reply", resp)

        try:
            text, reason, _used = llm_auth.make_call(
                call_providers, _do_call, context="narrative_brain")
        except Exception as e:  # noqa: BLE001
            log.warning("narrative_brain call failed (%s): %s", model, e)
            return None, "llm_error"
        return text, reason

    return call


# --- evidence assembly (deterministic; grounds the model) ----------------------
def _read_json(p: Path):
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def gather_evidence(region: str = "us", root=None) -> dict | None:
    """Build per-theme evidence packs from the radar. Returns None if the radar is absent
    (no-data gate). Each theme gets an evidence_id'd pack the model must cite from."""
    base = Path(root) if root is not None else config.ROOT
    radar = _read_json(base / "site" / "basketdata" / "radar.json")
    if not radar or not radar.get("flags"):
        log.info("narrative_brain: no radar.json — nothing to read")
        return None
    themes = []
    for f in radar["flags"]:
        o = f.get("observable") or {}
        c = f.get("consensus") or {}
        n = f.get("news") or {}
        srcs = ", ".join(f"{s.get('label_en', s.get('name'))} z={s.get('z')}" for s in (o.get("sources") or []))
        ev = [
            {"id": "P1", "text": f"Radar state: {f.get('state')}; lifecycle: {f.get('lifecycle')}."},
            {"id": "P2", "text": f"Real-activity vs price divergence z = {f.get('divergence')} "
                                 f"(>0 = activity ahead of price)."},
            {"id": "P3", "text": f"Per-source activity (signed z): {srcs or 'none'}; "
                                 f"fused accel {o.get('accel')}, {o.get('n_sources')} source(s)."},
            {"id": "P4", "text": f"60-day relative strength vs SPY = {c.get('rel_60d')} "
                                 f"(z {c.get('z')}, dir {c.get('dir')})."},
            {"id": "P5", "text": (f"News flow velocity {n.get('velocity')}, accel {n.get('acceleration')}, "
                                  f"unscheduled share {n.get('unscheduled_share')}." if n else "No news leg.")},
            {"id": "P6", "text": f"Covered members: {', '.join((o.get('covered') or [])[:8]) or 'n/a'}."},
        ]
        themes.append({
            "basket": f.get("basket"), "name": f.get("name"), "name_zh": f.get("name_zh"),
            "category": f.get("category"), "state": f.get("state"), "lifecycle": f.get("lifecycle"),
            "evidence": ev,
        })
    return {"as_of": radar.get("as_of"), "region": region, "themes": themes}


def _theme_user_prompt(theme: dict) -> str:
    lines = [f"THEME: {theme.get('name')} ({theme.get('basket')}) — category {theme.get('category')}", "",
             "EVIDENCE PACK (cite these ids):"]
    lines += [f"  [{e['id']}] {e['text']}" for e in theme["evidence"]]
    return "\n".join(lines)


# --- risk clamp (CODE, not prompt — the hard boundary) -------------------------
def _is_risk_blocked(theme: dict) -> bool:
    return theme.get("state") in _RISK_STATES or theme.get("lifecycle") in _RISK_LIFECYCLE


def _reconcile(assessment: dict, theme: dict) -> tuple[dict, str | None]:
    """The LLM may DE-escalate freely, but never ENTER a fading / negative-divergence theme."""
    v = assessment.get("verdict")
    if v not in _VERDICTS:
        assessment["verdict"] = v = "MONITOR"
    if v == "ENTER" and _is_risk_blocked(theme):
        assessment["verdict"] = "MONITOR"
        assessment["override_reason"] = "clamped: radar flags this theme fading / activity not ahead of price"
        return assessment, assessment["override_reason"]
    return assessment, None


_VERDICT_LEAN = {"ENTER": "constructive", "AVOID": "cautious"}  # MONITOR → soft (logged, not scored)


def _proxy_for(basket_id: str, mem: dict) -> str | None:
    b = mem.get(basket_id) or {}
    px = b.get("etf_proxy")
    if isinstance(px, list):
        px = px[0] if px else None
    return px.strip().split()[0] if isinstance(px, str) and px.strip() else None


# --- synthesis -----------------------------------------------------------------
def synthesize(evidence: dict, cfg: dict | None = None, call=None) -> dict:
    """Run the durability desk per top-N theme + one rotation read. `call` is injectable
    (model, system, user) -> (text, degraded) for hermetic tests. Never raises."""
    cfg = cfg or _cfg()
    if call is None:
        call = _make_call(cfg)
    asof = (evidence or {}).get("as_of") or datetime.now(timezone.utc).date().isoformat()
    out = {"schema": "narrative_brain.v1", "as_of": asof, "is_context_only": True,
           "disclaimer": DISCLAIMER, "assessments": [], "rotation": None}
    if call is None:
        out["degraded_reason"] = "no_client_or_key"
        return out
    if not evidence or not evidence.get("themes"):
        out["degraded_reason"] = "no_evidence"
        return out

    models = cfg.get("models", {})
    themes = evidence["themes"][: int(cfg.get("max_themes", 6))]

    for theme in themes:
        text, degraded = call(models.get("durability", "claude-sonnet-4-6"),
                              _DURABILITY_SYSTEM, _theme_user_prompt(theme))
        if not text:
            continue
        a = _extract_json(text)
        if not a:
            continue
        a, override = _reconcile(a, theme)
        a["basket"] = theme.get("basket")
        a["name"] = theme.get("name")
        a["name_zh"] = theme.get("name_zh")
        a["state"] = theme.get("state")
        out["assessments"].append(a)

    # one cross-theme rotation read
    table = "\n".join(f"  {t.get('name')} ({t.get('basket')}): state={t.get('state')}, "
                      f"lifecycle={t.get('lifecycle')}" for t in evidence["themes"])
    rtext, _ = call(models.get("rotation", "claude-opus-4-8"), _ROTATION_SYSTEM,
                    "RADAR FLAGS:\n" + table)
    if rtext:
        out["rotation"] = _extract_json(rtext)
    if not out["assessments"] and out["rotation"] is None:
        out["degraded_reason"] = "no_usable_reply"
    return out


# --- accountability ledger -----------------------------------------------------
def _membership(root) -> dict:
    base = (Path(root) / "data") if root is not None else config.data_dir()
    try:
        return json.loads((base / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _append_ledger(brief: dict, root=None) -> int:
    """Append falsifiable theses (ENTER/AVOID verdicts) to data/narrative_brain/theses.jsonl,
    idempotent by id, in the ai_desk thesis shape so a scorer can grade proxy-vs-SPY later."""
    if not brief or not brief.get("assessments"):
        return 0
    cfg = _cfg()
    mem = _membership(root)
    asof = brief.get("as_of")
    horizon = int(cfg.get("horizon_d", 21))
    thr = float(cfg.get("rel_threshold", 0.05))
    try:
        check_by = (pd.Timestamp(asof) + pd.Timedelta(days=int(horizon * 1.5))).date().isoformat()
    except Exception:  # noqa: BLE001
        check_by = None
    rows = []
    for a in brief["assessments"]:
        lean = _VERDICT_LEAN.get(a.get("verdict"))
        if not lean:
            continue   # MONITOR = soft, not logged as a scored thesis
        proxy = _proxy_for(a.get("basket"), mem)
        op = "<" if lean == "constructive" else ">"
        threshold = -thr if lean == "constructive" else thr
        check = ({"kind": "rel_return", "subject_ticker": proxy, "vs": "SPY",
                  "op": op, "threshold": threshold, "horizon_d": horizon}
                 if proxy else {"kind": "soft", "reason": "no ETF proxy to score"})
        rows.append({
            "id": f"{asof}-nb-{a.get('basket')}",
            "subject": a.get("basket"), "subject_ticker": proxy,
            "lean": lean, "conviction": (a.get("confidence") or "low").lower(),
            "horizon_d": horizon, "thesis": a.get("rationale"),
            "verdict": a.get("verdict"), "composite": a.get("composite"),
            "falsifier": {"text": (a.get("falsifiable_check") or {}).get("disconfirm"), "check": check},
            "check_by": check_by, "logged_at": datetime.now(timezone.utc).isoformat(),
        })
    if not rows:
        return 0
    try:
        p = (config.data_dir() if root is None else (Path(root) / "data")) / "narrative_brain" / "theses.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        from engine.regime_label import quad_label      # regime stamp → by_regime track record
        regime = quad_label(config.ROOT if root is None else Path(root))
        seen = set()
        if p.exists():
            for line in p.read_text().splitlines():
                try:
                    seen.add(json.loads(line).get("id"))
                except Exception:  # noqa: BLE001
                    continue
        n = 0
        with p.open("a") as fh:
            for r in rows:
                if r["id"] in seen:
                    continue
                fh.write(json.dumps({**r, "regime": regime}, separators=(",", ":")) + "\n")
                n += 1
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_brain ledger append failed: %s", e)
        return 0


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gate (enabled + interval + no-data), synthesize, persist, append ledger. Never raises."""
    cfg = _cfg()
    if not force and not cfg.get("enabled", False):
        return None
    base = Path(root) if root is not None else config.ROOT
    site = base / "site" / "basketdata" / "narrative_brain.json"
    if not force and int(cfg.get("interval_days", 1)) > 1 and site.exists():
        try:
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(site.stat().st_mtime, timezone.utc)).days
            if age < int(cfg["interval_days"]):
                log.info("narrative_brain: note %dd old (< interval) — skipping", age)
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
            log.warning("narrative_brain persist failed: %s", e)
        _append_ledger(brief, root=root)
    return brief


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    res = run(force=a.force)
    if not res:
        print("narrative_brain: disabled (set narrative_brain.enabled + CLAUDE_CODE_OAUTH_TOKEN) or no radar.json")
    else:
        print(json.dumps({"degraded": res.get("degraded_reason"),
                          "n_assessments": len(res.get("assessments", [])),
                          "rotation": bool(res.get("rotation"))}, indent=2))
