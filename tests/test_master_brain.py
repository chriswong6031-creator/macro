"""Tests for engine/master_brain.py — the LLM Tier-B cross-asset synthesis.

No network / no API key needed: the model call is stubbed and state is read from a
temp dir. Run as a plain script:  python tests/test_master_brain.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import master_brain as mb  # noqa: E402

MACRO = {
    "date": "2026-06-12", "quad": "Q1", "quad_name": "Goldilocks", "label": "Q1",
    "growth_score": 0.4, "inflation_score": -0.1, "confidence": 0.7,
    "liquidity_overlay": "contracting", "cycle_tag": "mid", "transition_state": "stable",
    "macro_risk": {"score": 0.11, "label": "low", "components": {"x": 1}},
    "conditions": {"recession": {"label": "low", "value": 0.1, "extra": "drop"},
                   "risk_appetite": {"state": "risk-on"}},
    "dislocation": {"verdict": "calm", "put_state": "put-present",
                    "headline": "no acute dislocation", "catalyst_narrative": None,
                    "inputs": {"big": "dropped"}},
    "playbook": {"posture": "constructive", "dial": {"score": 1, "reasons": ["x"]}},
}


def test_macro_summary_compacts():
    s = mb._macro_summary(MACRO)
    assert s["quad"] == "Q1" and s["macro_risk"]["score"] == 0.11
    assert s["dislocation"]["verdict"] == "calm"
    assert "inputs" not in s["dislocation"]                  # heavy field dropped
    assert s["playbook"]["dial_score"] == 1                  # dial flattened to its score
    assert s["conditions"]["recession"]["value"] == 0.1
    assert "extra" not in s["conditions"]["recession"]       # leg compacted


def test_gather_state_reads_present_skips_missing():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(json.dumps(MACRO))
        (root / "data" / "forex").mkdir(parents=True)
        (root / "data" / "forex" / "latest.json").write_text(
            json.dumps({"date": "2026-06-13", "regime": "US growth premium",
                        "favored": ["USD"], "risk": "risk-on"}))
        state = mb.gather_state(root)
        assert state["macro"]["quad"] == "Q1"
        assert state["forex"]["regime"] == "US growth premium"
        assert "china" not in state and "hk" not in state    # missing files skipped, no crash


def test_synthesize_stubbed_parses_fields():
    orig = mb._call_model
    reply = json.dumps({
        "summary": "Goldilocks but liquidity contracting.",
        "regime_read": "Macro Q1 with low macro-risk; FX risk-on.",
        "conflicts": ["FX risk-on vs contracting liquidity overlay"],
        "rotation_check": "Partly tracking — ex-US not yet confirming.",
        "transmission": ["liquidity drain -> crypto first to wobble"],
        "watch_items": ["FOMC Jun 17"], "confidence": "medium", "ignored": "x"})
    mb._call_model = lambda system, user, cfg: (reply, None)
    try:
        b = mb.synthesize({"macro": mb._macro_summary(MACRO)}, {"llm_model": "deepseek-v4-pro"})
        assert b["summary"].startswith("Goldilocks")
        assert b["conflicts"] == ["FX risk-on vs contracting liquidity overlay"]
        assert b["confidence"] == "medium"
        assert b["degraded_reason"] is None
        assert b["is_context_only"] is True
        assert b["raw_text"] == reply
    finally:
        mb._call_model = orig


def test_synthesize_degrades_without_key():
    orig = mb._call_model
    mb._call_model = lambda system, user, cfg: (None, "no_client_or_key")
    try:
        b = mb.synthesize({"macro": {}}, {})
        assert b["degraded_reason"] == "no_client_or_key"
        assert b["regime_read"] is None and b["is_context_only"] is True
    finally:
        mb._call_model = orig


def test_synthesize_unparseable():
    orig = mb._call_model
    mb._call_model = lambda system, user, cfg: ("this is not json", None)
    try:
        b = mb.synthesize({"macro": {}}, {})
        assert b["degraded_reason"] == "unparseable_reply"
        assert b["raw_text"] == "this is not json"   # raw kept so the read isn't lost
    finally:
        mb._call_model = orig


def test_run_disabled_returns_none():
    orig = mb._cfg
    mb._cfg = lambda: {"enabled": False}        # force disabled, independent of operational config
    try:
        assert mb.enabled() is False
        assert mb.run(persist=False) is None    # gated unless force=True
    finally:
        mb._cfg = orig


def test_render_markdown():
    b = {"state_asof": "2026-06-12", "model": "deepseek-v4-pro",
         "summary": "TL;DR", "regime_read": "the read",
         "conflicts": ["c1"], "rotation_check": "rc",
         "transmission": ["t1"], "watch_items": ["w1"], "confidence": "medium"}
    md = mb.render_markdown(b)
    assert "Master brief" in md and "TL;DR" in md and "- c1" in md and "confidence: medium" in md
    assert mb.render_markdown({"degraded_reason": "llm_error"}).startswith("_master brief unavailable")


def test_synthesize_truncated_flags():
    orig = mb._call_model
    reply = json.dumps({"summary": "ok", "confidence": "low"})
    mb._call_model = lambda system, user, cfg: (reply, "truncated")
    try:
        b = mb.synthesize({"macro": {}}, {})
        assert b["summary"] == "ok"                 # parsed what completed
        assert b["degraded_reason"] == "truncated"  # but truncation is flagged
    finally:
        mb._call_model = orig


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
