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

CHINA = {
    "date": "2026-06-12", "quad": "Q3", "quad_name": "Stagflation",
    "growth_score": -0.4, "inflation_score": 0.9, "confidence": 0.6,
    "liquidity_overlay": "neutral", "cycle_tag": "mid", "pending_quad": None,
    "confirming": ["def/cyc declining"], "contradicting": [],
    "sector_rs": [{"name": "Technology", "rank": 1}],
    "pair_ratios": {"usdcny": {"chg_20d_pct": 0.1}},
}

HK = {
    "date": "2026-06-12", "quad": "Q3", "global_score": 0.25, "risk_state": "neutral",
    "peg_state": "weak-side", "peg_distance": 0.0, "liquidity_overlay": "neutral",
    "sector_rs": [{"name": "Financials", "rank": 1}],
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


# --------------------------------------------------------------------------- #
# lens machinery — focused China & BTC briefs share the macro engine
# --------------------------------------------------------------------------- #
def test_lens_registry():
    assert set(mb.LENSES) == {"macro", "china", "btc"}
    assert mb.LENSES["macro"]["out"] == "master_brief.json"
    assert mb.LENSES["china"]["out"] == "china_brief.json"
    assert mb.LENSES["btc"]["out"] == "btc_brief.json"


def test_state_asof_picks_available_date():
    assert mb._state_asof({"china": {"date": "2026-06-12"}}) == "2026-06-12"
    assert mb._state_asof({"btc": {"date": "2026-06-14"}}) == "2026-06-14"
    assert mb._state_asof({}) is None


def test_gather_china_state_focused():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "data" / "china_regime").mkdir(parents=True)
        (root / "data" / "china_regime" / "latest.json").write_text(json.dumps(CHINA))
        (root / "data" / "hk_regime").mkdir(parents=True)
        (root / "data" / "hk_regime" / "latest.json").write_text(json.dumps(HK))
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(json.dumps(MACRO))
        s = mb.gather_china_state(root)
        assert s["china"]["quad"] == "Q3"
        assert s["china"]["sector_rs"] == [{"name": "Technology", "rank": 1}]
        assert s["hk"]["peg_state"] == "weak-side"
        assert s["us_macro_backdrop"]["quad"] == "Q1"          # slim US backdrop attached
        assert "conditions" not in s["us_macro_backdrop"]      # heavy field NOT in the backdrop
        assert "btc" not in s                                  # china lens excludes crypto


def test_gather_btc_state_focused():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "data" / "vector").mkdir(parents=True)
        idx = pd.to_datetime(["2026-06-13", "2026-06-14"])
        df = pd.DataFrame({"composite_state": ["RISK-OFF", "DISTRIBUTE"],
                           "momentum": [0.1, -0.2], "mvrv_z": [0.30, 0.34],
                           "valuation_state": ["fair", "fair"], "vix": [15.0, 16.0]}, index=idx)
        df.to_parquet(root / "data" / "vector" / "signals.parquet")
        (root / "data" / "vector" / "flash_state.json").write_text(
            json.dumps({"state": "calm", "price": 65000}))
        s = mb.gather_btc_state(root)
        btc = s["btc"]
        assert btc["composite_state"] == "DISTRIBUTE"          # last row, not the first
        assert btc["mvrv_z"] == 0.34
        assert btc["date"] == "2026-06-14"
        assert btc["alert_state"] == "calm" and btc["price"] == 65000
        assert "us_macro_backdrop" not in s                    # no regime/latest.json -> skipped


def test_synthesize_uses_lens_system_prompt():
    orig = mb._call_model
    captured = {}

    def fake(system, user, cfg):
        captured["system"] = system
        return (json.dumps({"summary": "s", "confidence": "low"}), None)
    mb._call_model = fake
    try:
        b = mb.synthesize({"btc": {"date": "2026-06-14"}}, {}, lens="btc")
        assert b["lens"] == "btc" and b["state_asof"] == "2026-06-14"
        assert "BITCOIN" in captured["system"].upper()         # btc-specific framing
        mb.synthesize({"china": {"date": "2026-06-12"}}, {}, lens="china")
        assert "CHINA" in captured["system"].upper()           # china-specific framing
    finally:
        mb._call_model = orig


def test_run_writes_per_lens_output():
    orig_cfg, orig_call = mb._cfg, mb._call_model
    reply = json.dumps({"summary": "x", "regime_read": "r", "confidence": "low"})
    mb._cfg = lambda: {"enabled": True, "llm_model": "test", "translate_zh": False}
    mb._call_model = lambda system, user, cfg: (reply, None)
    try:
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "data" / "china_regime").mkdir(parents=True)
            (root / "data" / "china_regime" / "latest.json").write_text(json.dumps(CHINA))
            (root / "site").mkdir()
            b = mb.run(persist=True, root=root, lens="china")
            assert b["lens"] == "china"
            assert (root / "data" / "regime" / "china_brief.json").exists()
            saved = json.loads((root / "site" / "china_brief.json").read_text())   # site copy for the panel
            assert saved["summary"] == "x" and saved["lens"] == "china"
    finally:
        mb._cfg, mb._call_model = orig_cfg, orig_call


def test_run_unknown_lens_is_safe():
    assert mb.run(persist=False, force=True, lens="bogus") is None   # no crash, no write


def test_run_all_runs_configured_lenses():
    orig_cfg, orig_run = mb._cfg, mb.run
    mb._cfg = lambda: {"enabled": True, "lenses": ["china", "btc"]}
    calls = []
    mb.run = lambda persist=True, root=None, force=False, lens="macro": (
        calls.append(lens) or {"lens": lens})
    try:
        out = mb.run_all(persist=False)
        assert set(out) == {"china", "btc"} and calls == ["china", "btc"]
    finally:
        mb._cfg, mb.run = orig_cfg, orig_run


def test_run_all_disabled_returns_empty():
    orig = mb._cfg
    mb._cfg = lambda: {"enabled": False}
    try:
        assert mb.run_all(persist=False) == {}      # gated unless force / enabled
    finally:
        mb._cfg = orig


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
