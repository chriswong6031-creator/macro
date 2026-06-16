"""AI knife-vs-dip durability veto for the regime-snap detector (CONTEXT-ONLY).

The regime-snap detector (engine.regime_snap) is VERIFIED COINCIDENT: it confirms a
fast risk-on snap is happening, but its forward returns are ~base-rate, so it
cannot tell a durable relief from a dead-cat bounce. That durability call is the
one judgement a mechanical leg structurally can't make — it turns on the CATALYST
(a signed deal / policy shift vs a verbal head-fake), which lives in the news, not
the price tape. This module makes that call with a single, TRIGGERED LLM call.

Discipline (DECISIONS.md D33 + research/SP_VECTOR_VIABILITY.md):
  * TRIGGERED, not continuous — runs ONLY when a snap is firing/building, so cost is
    O(snap events) (~1-2 a year), never every build.
  * CONTEXT-ONLY — the verdict is shown on the relief-radar card and appended to a
    grading log; it is NEVER a number in any score / size / allocation, and nothing
    in axes / regime / macro_risk / regime_snap reads it. The mechanical core keeps
    its own backtestable track record (D33: keep a mechanical core, an LLM layer on
    top is fine); this is an annotation on top.
  * FIREWALLED + graceful — needs DEEPSEEK_API_KEY; absent the key (or disabled in
    config) it returns None and the card falls back to the deterministic checklist.
  * GROUNDED — it reasons over the deterministic snap state + what's driving the tape
    + recent headlines we already fetch; it is told NOT to fabricate and to answer
    'unclear' (low confidence) when the catalyst isn't legible.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from engine import master_brain as _mb          # reuse the DeepSeek/Anthropic client
from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser
from lib import config

log = logging.getLogger(__name__)

DISCLAIMER = ("AI durability read — context only, never scored or sized. The snap "
              "detector is coincident; this is a fallible judgement on whether the "
              "relief is structural or a dead-cat, not a trade recommendation.")

_LEANS = ("durable", "fragile", "unclear")

_SYSTEM = (
    "You are a markets risk analyst judging the DURABILITY of a cross-asset relief "
    "snap that a deterministic detector has just flagged. The detector is COINCIDENT "
    "— it confirms a fast risk-on move out of a fear washout is happening, but cannot "
    "tell a durable relief from a dead-cat bounce. That is your ONLY job: knife "
    "(fragile / likely to fail) vs dip (durable relief worth fading fear into).\n\n"
    "Reason ONLY over the JSON state and headlines provided, plus well-known market "
    "structure. Do NOT invent facts or events. The decisive question is the CATALYST: "
    "a signed deal, an actual policy/rate shift or a hard data surprise is STRUCTURAL "
    "(more durable); a verbal promise, a rumour or an unsigned 'framework' is VERBAL "
    "(easily reversed — more knife-like). If the headlines do not make the catalyst "
    "legible, answer lean='unclear' with low confidence — do NOT guess.\n\n"
    "Answer four checks: (1) catalyst structural vs verbal; (2) how much of the fear "
    "premium looks already unwound vs left; (3) did this come out of a REAL washout "
    "(capitulation present) or a shallow dip; (4) is the cross-asset confirmation "
    "likely to hold the next session or fade.\n\n"
    "Output STRICT JSON only, nothing around it:\n"
    '{"lean":"durable|fragile|unclear","confidence":"low|medium|high",'
    '"checks":{"catalyst":"...","premium":"...","washout":"...","follow_through":"..."},'
    '"read":"<= 2 plain sentences"}')


def _cfg() -> dict:
    base = {"enabled": True, "model": "deepseek-v4-pro", "max_tokens": 1500,
            "headlines_n": 12, "api_key_env": "DEEPSEEK_API_KEY",
            "llm_base_url": "https://api.deepseek.com/anthropic"}
    try:
        v = config.load()["engine"]["conditions"]["regime_snap"].get("veto") or {}
    except Exception:  # noqa: BLE001 — config-less callers fall back to defaults
        v = {}
    return {**base, **v}


def _bundle(view: dict, drivers, headlines, regime, n: int) -> dict:
    """The deterministic context handed to the model: snap state + what's driving the
    tape + recent headline titles (trimmed to keep the call cheap)."""
    titles = []
    if isinstance(headlines, dict):
        for h in (headlines.get("headlines") or [])[:n]:
            t = h.get("title") if isinstance(h, dict) else None
            if t:
                titles.append(t)
    drv = None
    if isinstance(drivers, dict):
        drv = {k: drivers.get(k) for k in
               ("verdict", "headline", "driver", "direction", "confidence")
               if k in drivers}
    snap = {k: view.get(k) for k in (
        "status", "snap", "relief_magnitude", "fear_built", "vel_pctile", "legs_up",
        "legs_total", "flipped_legs", "cap_recent", "vix_term", "fear_rebuilding",
        "days_since_last_snap")}
    return {"snap": snap, "what_is_driving_today": drv, "regime": regime,
            "recent_headlines": titles}


def assess(view: dict | None, *, drivers=None, headlines=None, regime=None,
           cfg: dict | None = None, call=None, persist: bool = True) -> dict | None:
    """Triggered durability verdict for a firing/building snap. CONTEXT-ONLY.

    Returns None when not triggered, disabled, or the LLM is unavailable (the card
    then shows only the deterministic checklist). Never raises. `call` is injectable
    (defaults to master_brain._call_model) so tests run without an API key."""
    try:
        if not view or view.get("status") in (None, "dormant"):
            return None
        c = {**_cfg(), **(cfg or {})}
        if not c.get("enabled", True):
            return None
        bundle = _bundle(view, drivers, headlines, regime, int(c["headlines_n"]))
        user = ("Snap state + context (JSON). Judge durability per your "
                "instructions.\n<state>\n"
                + json.dumps(bundle, default=str, indent=2) + "\n</state>")
        reply, reason = (call or _mb._call_model)(_SYSTEM, user, c)
        if reply is None:
            return None                                   # no key / refusal / error
        parsed = _extract_json(reply)
        if not isinstance(parsed, dict) or parsed.get("lean") not in _LEANS:
            return None
        verdict = {
            "schema": "regime_snap_veto.v1", "is_context_only": True,
            "lean": parsed["lean"],
            "confidence": parsed.get("confidence", "low"),
            "checks": parsed.get("checks") if isinstance(parsed.get("checks"), dict) else {},
            "read": parsed.get("read"),
            "model": c["model"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "degraded_reason": reason,                     # e.g. "truncated"
            "disclaimer": DISCLAIMER,
        }
        if persist:
            _append_log(verdict, bundle)
        return verdict
    except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
        log.warning("regime-snap veto failed: %s", e)
        return None


def _append_log(verdict: dict, bundle: dict) -> None:
    """Append-only grading log (data/regime_snap/veto_log.jsonl) so the calls can be
    scored later — did 'durable' reads actually persist? Never fatal."""
    try:
        d = config.data_dir() / "regime_snap"
        d.mkdir(parents=True, exist_ok=True)
        row = {"generated_at": verdict["generated_at"], "lean": verdict["lean"],
               "confidence": verdict["confidence"], "snap": bundle["snap"],
               "headlines_n": len(bundle["recent_headlines"])}
        with open(d / "veto_log.jsonl", "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("veto log append failed: %s", e)
