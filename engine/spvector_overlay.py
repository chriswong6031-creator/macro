"""S&P / Macro Vector — LLM context/veto OVERLAY (firewalled, live-only).

CONTEXT-ONLY · GATED · NEVER IN THE BACKTEST. Consumes the catalyst_tone digest
(engine/catalyst_tone.py — DeepSeek Tier A, public-docs-only) and turns it into a
LIVE recommendation overlay for the mechanical S&P Vector:

  • KNIFE-VETO — when the mechanical engine is taking a buyable-washout REDEPLOY
    (Phase-2: capitulation + Fed-put-present lifted the weight) but the LLM reads
    the shock as a regime break (shock_reversible="persistent") with adequate
    confidence, VETO the redeploy: the LIVE recommendation reverts to the defensive
    glide weight ("knife-vetoer, not dip-buyer"). This is the one place an opaque
    read earns its keep — refusing a buy is cheap to be wrong about; the mechanical
    engine still governs everything else.
  • TONE CONTEXT — otherwise it just annotates the Fed/guidance/shock read.

It NEVER writes a number into the allocation function or the backtest. The backtest
is pure-mechanical and look-ahead-free (an LLM trained through a knowledge cutoff
cannot honestly be in a historical backtest), so the overlay only adjusts the LIVE
displayed recommendation and is LOGGED FORWARD (overlay_log.jsonl) so its veto/context
calls accrue a real track record before the layer is ever trusted to size anything.

Firewall (mirrors catalyst_tone): imports nothing from the scoring path; every path
degrades to "no overlay" (catalyst_tone disabled / absent / keyless / any error).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from lib import config

_CONF = {"low": 0, "medium": 1, "high": 2}


def _cfg() -> dict:
    return config.load().get("spvector_overlay", {}) or {}


def _conf_rank(c) -> int:
    return _CONF.get(str(c).lower(), 0)


def _catalyst():
    try:
        from engine import catalyst_tone
        return catalyst_tone
    except Exception:  # noqa: BLE001 — layer absent on this branch
        return None


def context_snapshot(asof=None, on_stress_day: bool = False) -> dict | None:
    """Current LLM read, or None when the layer is off / absent / keyless. On a
    stress day prefer the event (shock_reversible) digest; else the FOMC tone digest.
    Never raises."""
    ct = _catalyst()
    if ct is None or not getattr(ct, "enabled", lambda: False)():
        return None
    try:
        snap = ct.event_snapshot(asof) if on_stress_day else None
        return snap or ct.daily_snapshot(asof)
    except Exception:  # noqa: BLE001
        return None


def live_overlay(glide_weight: float, redeploy_weight: float,
                 snapshot: dict | None = None) -> dict:
    """Decide the LIVE overlay from the mechanical weights + the LLM snapshot.

    `glide_weight` = the de-risk glide weight (pre-redeploy); `redeploy_weight` = the
    mechanical weight WITH the Phase-2 buyable-washout redeploy. The engine is
    "taking a redeploy" iff redeploy_weight > glide_weight. If so AND the LLM reads
    shock_reversible="persistent" with confidence >= the floor, VETO: the live
    recommendation reverts to glide_weight. Otherwise the mechanical weight stands
    and the LLM read is surfaced as context. `snapshot` may be injected (tests)."""
    cfg = _cfg()
    floor = cfg.get("veto_confidence_floor", "medium")
    gw, rw = float(glide_weight), float(redeploy_weight)
    out = {
        "enabled": snapshot is not None,
        "context": snapshot,
        "veto": False,
        "veto_reason": "",
        "mechanical_weight": round(rw, 3),
        "overlay_weight": round(rw, 3),
        "note": "LLM overlay off — mechanical recommendation stands." if snapshot is None else "",
        "disclaimer": "Context overlay — NOT in the backtest; advisory + tracked forward.",
    }
    if snapshot is None:
        return out

    sr = str(snapshot.get("shock_reversible", "unknown")).lower()
    conf = snapshot.get("confidence", "low")
    taking_redeploy = rw > gw + 1e-9
    if taking_redeploy and sr == "persistent" and _conf_rank(conf) >= _conf_rank(floor):
        out["veto"] = True
        out["overlay_weight"] = round(gw, 3)
        out["veto_reason"] = (
            f"Knife-veto: the engine wants to redeploy into a washout, but the LLM reads this shock as "
            f"PERSISTENT (regime break), confidence {conf} — defer the buy; hold the defensive "
            f"{round(100 * gw)}% until it stabilizes.")
        out["note"] = out["veto_reason"]
        return out

    # no veto — surface the read as context only (no weight change). Only show a
    # field when it is actually informative, so a quiet/low-confidence digest reads
    # as "neutral" rather than a noisy string of zeros.
    bits = []
    gd = snapshot.get("guidance_direction")
    if gd and gd not in ("unknown", None):
        bits.append(f"Fed guidance {gd}")
    tone = snapshot.get("tone_score")
    if tone is not None and abs(tone) >= 0.05:
        bits.append(f"tone {tone:+.2f}")
    rd = snapshot.get("risk_delta")
    if rd is not None and abs(rd) >= 0.05:
        bits.append(f"risk Δ {rd:+.2f}")
    if sr in ("reversible", "persistent"):
        bits.append(f"shock {sr}")
    out["note"] = ("LLM context — " + ", ".join(bits)) if bits else \
        f"LLM read: neutral — no actionable catalyst (confidence {conf})."
    return out


def log_overlay(overlay: dict, asof=None) -> None:
    """Append the overlay decision to data/spvector/overlay_log.jsonl — the forward
    track record that must accrue before the layer is trusted to touch sizing.
    Degrade-never-raise. Skips logging the degraded (off) overlay."""
    if not _cfg().get("log", True) or not overlay.get("enabled"):
        return
    try:
        d = config.data_dir() / "spvector"
        d.mkdir(parents=True, exist_ok=True)
        ctx = overlay.get("context") or {}
        row = {"asof": str(asof or date.today()),
               "logged": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "veto": overlay.get("veto"),
               "mechanical_weight": overlay.get("mechanical_weight"),
               "overlay_weight": overlay.get("overlay_weight"),
               "shock_reversible": ctx.get("shock_reversible"),
               "tone_score": ctx.get("tone_score"),
               "confidence": ctx.get("confidence"),
               "note": overlay.get("note")}
        with open(d / "overlay_log.jsonl", "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
