"""Tests for the S&P Vector LLM context/veto overlay (engine/spvector_overlay.py).
The veto DECISION logic is the testable core (the LLM call itself degrades to None
without a key). Run: python -m tests.test_spvector_overlay
"""
from __future__ import annotations

from engine import spvector_overlay as ov

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}  {detail}")


def snap(sr="unknown", conf="high", tone=0.0, gd="unknown", rd=0.0):
    return {"shock_reversible": sr, "confidence": conf, "tone_score": tone,
            "guidance_direction": gd, "risk_delta": rd}


def test_degraded_no_llm():
    o = ov.live_overlay(0.33, 1.0, snapshot=None)
    check("no snapshot -> overlay off, mechanical stands",
          o["enabled"] is False and o["veto"] is False and o["overlay_weight"] == 1.0, str(o))


def test_knife_veto_fires():
    # engine taking a redeploy (1.0 > 0.33) + LLM says persistent regime break, high conf
    o = ov.live_overlay(0.33, 1.0, snapshot=snap(sr="persistent", conf="high"))
    check("persistent shock + redeploy -> VETO", o["veto"] is True, str(o))
    check("veto reverts to glide weight", o["overlay_weight"] == 0.33, str(o))


def test_reversible_no_veto():
    o = ov.live_overlay(0.33, 1.0, snapshot=snap(sr="reversible", conf="high"))
    check("reversible shock -> no veto, redeploy stands", o["veto"] is False and o["overlay_weight"] == 1.0, str(o))


def test_low_confidence_no_veto():
    o = ov.live_overlay(0.33, 1.0, snapshot=snap(sr="persistent", conf="low"))
    check("persistent but low confidence -> no veto (below floor)", o["veto"] is False and o["overlay_weight"] == 1.0, str(o))


def test_not_redeploying_no_veto():
    # not taking a redeploy (glide == mechanical) -> nothing to veto even if persistent
    o = ov.live_overlay(1.0, 1.0, snapshot=snap(sr="persistent", conf="high"))
    check("no active redeploy -> no veto", o["veto"] is False and o["overlay_weight"] == 1.0, str(o))


def test_context_annotation():
    o = ov.live_overlay(1.0, 1.0, snapshot=snap(sr="reversible", conf="high", tone=0.4, gd="tightening", rd=0.3))
    check("context note surfaces Fed read", "LLM context" in o["note"] and "tightening" in o["note"], o["note"])


def test_context_snapshot_safe():
    # returns a dict or None, NEVER raises — regardless of whether the LLM layer is
    # enabled / cached / keyless in this environment (firewall: degrade-never-raise)
    r = ov.context_snapshot()
    check("context_snapshot returns dict-or-None, never raises", r is None or isinstance(r, dict), repr(r)[:80])


def main() -> int:
    for fn in (test_degraded_no_llm, test_knife_veto_fires, test_reversible_no_veto,
               test_low_confidence_no_veto, test_not_redeploying_no_veto,
               test_context_annotation, test_context_snapshot_safe):
        print(f"\n{fn.__name__}"); fn()
    print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
