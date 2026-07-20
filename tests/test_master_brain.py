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


def test_reply_cache_roundtrip_root_aware(tmp_path):
    """Real cache helpers: miss -> call -> post-lint put under the tmp root;
    second run -> hit that skips _call_model entirely. Nothing outside tmp_path
    is touched (a read probe must not even create the cache dir)."""
    calls = {"n": 0}
    reply = json.dumps({"summary": "Plain words only.", "confidence": "low"})

    def fake(system, user, cfg):
        calls["n"] += 1
        return (reply, None)

    orig = mb._call_model
    mb._call_model = fake
    try:
        cfg = {"llm_model": "deepseek-v4-pro"}
        b1 = mb.synthesize({}, cfg, root=tmp_path)
        assert b1["summary"] == "Plain words only." and calls["n"] == 1
        cache_dir = tmp_path / "data" / "master_brain" / "reply_cache"
        assert cache_dir.is_dir() and list(cache_dir.glob("*.txt"))
        b2 = mb.synthesize({}, cfg, root=tmp_path)
        assert b2["summary"] == "Plain words only."
        assert calls["n"] == 1                      # cache hit — no second call
        assert b2["style_flags"] == []
    finally:
        mb._call_model = orig


def test_translate_brief_covers_tldr(monkeypatch):
    """_translate_brief must pre-size zh['tldr'] — a missing key raised KeyError
    inside the fail-open except and silently dropped the ENTIRE zh block."""
    from engine import translate as _tr
    monkeypatch.setattr(_tr, "translate_to_zh",
                        lambda texts, cfg: ["ZH:" + t for t in texts])
    brief = {"tldr": ["Head: one", "What to do: Watch — don't chase."],
             "summary": "s", "regime_read": "r", "rotation_check": None,
             "conflicts": ["c1"], "transmission": [], "watch_items": ["w1"],
             "confidence": "low"}
    mb._translate_brief(brief, {})
    assert "zh" in brief, "zh block must survive a v2 brief with tldr"
    assert brief["zh"]["tldr"] == ["ZH:Head: one",
                                   "ZH:What to do: Watch — don't chase."]
    assert brief["zh"]["conflicts"] == ["ZH:c1"]

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
        assert "desk_track_records" not in state             # no desk tracks present → omitted


def test_gather_state_reads_back_desk_track_records():
    """The macro Brain ingests the Phase-C desks' measured hit-rates (close the loop)."""
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(json.dumps(MACRO))
        (root / "data" / "ai_desk").mkdir(parents=True)
        (root / "data" / "ai_desk" / "track_record.json").write_text(json.dumps({
            "scored_total": 12, "open": 3, "overall": {"hit_rate": 0.42, "dir_accuracy": 0.5},
            "calibration_note": "12 scored, hit-rate 0.42."}))
        (root / "data" / "policy_intent").mkdir(parents=True)
        (root / "data" / "policy_intent" / "track_record.json").write_text(json.dumps({
            "scored_total": 0, "open": 5, "overall": {"hit_rate": None}}))
        state = mb.gather_state(root)
        tr = state["desk_track_records"]
        assert tr["ai_desk"]["hit_rate"] == 0.42 and tr["ai_desk"]["scored"] == 12
        assert tr["ai_desk"]["note"].startswith("12 scored")
        assert tr["policy_intent"]["hit_rate"] is None       # cold desk surfaced, not dropped
        assert "altdata" not in tr                            # absent file → omitted, no crash


def test_desk_track_records_degrades_on_garbage():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "data" / "ai_desk").mkdir(parents=True)
        (root / "data" / "ai_desk" / "track_record.json").write_text("{not json")
        assert mb._desk_track_records(root) == {}             # never raises


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


# --------------------------------------------------------------------------- #
# ABX v2 — new tests (spec §4, §5, §6, §7)
# --------------------------------------------------------------------------- #

def test_interval_for_btc_override():
    """_interval_for: btc=3 override takes precedence over global interval_days."""
    cfg = {"interval_days": 1, "interval_days_by_lens": {"btc": 3}}
    assert mb._interval_for("btc", cfg) == 3
    assert mb._interval_for("macro", cfg) == 1
    assert mb._interval_for("china", cfg) == 1


def test_interval_for_global_fallback():
    """_interval_for: global interval_days is used when no per-lens override."""
    cfg = {"interval_days": 2, "interval_days_by_lens": {}}
    assert mb._interval_for("macro", cfg) == 2
    assert mb._interval_for("btc", cfg) == 2


def test_interval_for_defaults_to_1():
    """_interval_for: empty cfg falls back to 1."""
    assert mb._interval_for("macro", {}) == 1
    assert mb._interval_for("btc", {}) == 1


def test_interval_for_clamps():
    """_interval_for: result is clamped 1..7."""
    assert mb._interval_for("btc", {"interval_days_by_lens": {"btc": 0}}) == 1
    assert mb._interval_for("btc", {"interval_days_by_lens": {"btc": 100}}) == 7


def test_interval_for_exception_safe():
    """_interval_for: returns 1 on bad values."""
    assert mb._interval_for("btc", {"interval_days_by_lens": {"btc": "not-a-number"}}) == 1
    assert mb._interval_for("macro", {"interval_days": "bad"}) == 1


def test_style_violations_flags_snake_case():
    """_style_violations: snake_case tokens are flagged."""
    violations = mb._style_violations("growth_score -0.143 is declining")
    assert any("snake_case" in v for v in violations), violations


def test_style_violations_flags_sigma():
    """-2.5σ and z-score forms are flagged."""
    assert any("sigma" in v or "z/pctile" in v for v in mb._style_violations("-2.5σ drop"))
    assert any(v for v in mb._style_violations("z-score of 2.1"))
    assert any(v for v in mb._style_violations("at the 90th percentile"))


def test_style_violations_flags_panel_citation():
    """'panel: hk.sector_rs' is flagged (colon form)."""
    violations = mb._style_violations("as shown in panel: hk.sector_rs")
    assert any("panel" in v for v in violations), violations


def test_style_violations_flags_quad_code():
    """'Q1 Goldilocks' and 'Q4' are flagged."""
    assert any("quad code" in v for v in mb._style_violations("Q1 Goldilocks regime"))
    assert any("quad code" in v for v in mb._style_violations("Q4 is next"))


def test_style_violations_flags_hard_banned():
    """cross_asset_confirm and similar tokens are flagged."""
    assert any("banned" in v for v in mb._style_violations("cross_asset_confirm shows divergence"))
    assert any("banned" in v for v in mb._style_violations("neural_web synthesis"))


def test_style_violations_allows_paren_gated():
    """'China's 7-day interbank rate (FR007)' is NOT a violation."""
    text = "China's 7-day interbank rate (FR007) is 2.1%"
    violations = mb._style_violations(text)
    assert not any("FR007" in v for v in violations), (
        f"FR007 inside parens should be allowed, got: {violations}"
    )


def test_style_violations_flags_bare_paren_gated():
    """'FR007 is rising' (no parens) IS a violation."""
    violations = mb._style_violations("FR007 is rising sharply")
    assert any("FR007" in v for v in violations), violations


def test_style_violations_allows_plain_prose():
    """Plain English prose with no machine tokens → no violations."""
    text = "Equity breadth has narrowed over the past two weeks, with chip stocks lagging."
    assert mb._style_violations(text) == []


def test_key_facts_macro_regime_chip():
    """_kf_macro: regime chip has correct label/value/tone for Goldilocks shifting."""
    state = {
        "macro": {
            "quad_name": "Goldilocks",
            "transition_state": "TRANSITIONING",
            "macro_risk": {"label": "low"},
            "liquidity_overlay": "expanding",
        },
        "cross_asset_confirm": {"verdict": "confirm"},
        "bonds": {"credit": {"distress_band": "calm", "direction": "stable"}},
    }
    chips = mb._kf_macro(state)
    regime = next((c for c in chips if c["key"] == "regime"), None)
    assert regime is not None
    assert "shifting" in regime["value_en"]
    assert "转换中" in regime["value_zh"]
    assert regime["tone"] == "warn"


def test_key_facts_macro_missing_source_omitted():
    """_kf_macro: chip omitted when source value is missing."""
    # State with no cross_asset_confirm → bonds chip omitted
    state = {"macro": {"quad_name": "Goldilocks", "macro_risk": {}}}
    chips = mb._kf_macro(state)
    keys = {c["key"] for c in chips}
    assert "bonds" not in keys  # no cross_asset_confirm.verdict


def test_key_facts_btc_system_chip():
    """_kf_btc: system chip for ACCUMULATE with alloc=0 → bad tone."""
    state = {"btc": {
        "composite_state": "ACCUMULATE",
        "alloc_optimal": 0,
        "override_active": False,
        "cycle_phase": "markup",
        "valuation_state": "cheap",
        "leverage_stress": "low",
        "etf_flow_state": "inflow",
        "global_liq_regime": "expanding",
    }}
    chips = mb._kf_btc(state)
    sys_chip = next((c for c in chips if c["key"] == "system"), None)
    assert sys_chip is not None
    assert "allocation 0%" in sys_chip["value_en"]
    assert "仓位 0%" in sys_chip["value_zh"]
    assert sys_chip["tone"] == "bad"


def test_key_facts_btc_never_raises():
    """_kf_btc: returns [] not raises on garbage state."""
    assert mb._kf_btc({"btc": {"composite_state": None}}) is not None


def test_key_facts_china_peg_states():
    """_kf_china: peg chip maps weak-side correctly."""
    state = {
        "china": {"quad_name": "Goldilocks", "liquidity_overlay": "neutral"},
        "hk": {"risk_state": "risk_on", "peg_state": "weak-side"},
        "china_intel": {},
    }
    chips = mb._kf_china(state)
    peg = next((c for c in chips if c["key"] == "peg"), None)
    assert peg is not None
    assert "watching" in peg["value_en"].lower() or "weak" in peg["value_en"].lower()
    assert "需留意" in peg["value_zh"]
    assert peg["tone"] == "warn"


def test_key_facts_for_dispatch():
    """_key_facts_for: dispatches to correct builder, returns [] for unknown lens."""
    assert mb._key_facts_for("unknown", {}) == []
    # macro with empty state returns whatever chips are available (no crash)
    result = mb._key_facts_for("macro", {})
    assert isinstance(result, list)


def test_run_attaches_refresh_days(tmp_path):
    """run(): brief includes refresh_days = _interval_for(lens, cfg)."""
    orig_cfg, orig_call = mb._cfg, mb._call_model
    reply = json.dumps({"summary": "x", "confidence": "low"})
    mb._cfg = lambda: {"enabled": True, "llm_model": "test", "translate_zh": False,
                       "interval_days": 1, "interval_days_by_lens": {"btc": 3}}
    mb._call_model = lambda system, user, cfg: (reply, None)
    try:
        (tmp_path / "data" / "regime").mkdir(parents=True)
        (tmp_path / "site").mkdir()
        b = mb.run(persist=True, root=tmp_path, lens="macro")
        assert b["refresh_days"] == 1
        b_btc = mb.run(persist=True, root=tmp_path, lens="btc")
        assert b_btc["refresh_days"] == 3
    finally:
        mb._cfg, mb._call_model = orig_cfg, orig_call


def test_run_attaches_key_facts(tmp_path):
    """run(): brief includes key_facts list (may be empty for empty state)."""
    orig_cfg, orig_call = mb._cfg, mb._call_model
    reply = json.dumps({"summary": "x", "confidence": "low"})
    mb._cfg = lambda: {"enabled": True, "llm_model": "test", "translate_zh": False}
    mb._call_model = lambda system, user, cfg: (reply, None)
    try:
        (tmp_path / "data" / "regime").mkdir(parents=True)
        (tmp_path / "site").mkdir()
        b = mb.run(persist=True, root=tmp_path, lens="macro")
        assert "key_facts" in b
        assert isinstance(b["key_facts"], list)
    finally:
        mb._cfg, mb._call_model = orig_cfg, orig_call


def test_synthesize_schema_is_v2():
    """synthesize: schema field is master_brief.v2."""
    orig = mb._call_model
    mb._call_model = lambda s, u, c: (json.dumps({"summary": "x", "confidence": "low"}), None)
    try:
        b = mb.synthesize({}, {})
        assert b["schema"] == "master_brief.v2"
    finally:
        mb._call_model = orig


def test_zh_lists_includes_tldr():
    """_ZH_LISTS must include 'tldr' so the translator covers it."""
    assert "tldr" in mb._ZH_LISTS


# --------------------------------------------------------------------------- #
# empty_reply retry — a degraded/rate-limited endpoint can return a 200 with no
# text (the China lens went blank this way on 2026-07-20 while macro succeeded
# seconds earlier). _call_model must re-call before giving up. Patch the shared
# waterfall (engine.llm_auth.make_call, imported locally inside _call_model) plus
# mb._client (so we clear the client-is-None guard).
# --------------------------------------------------------------------------- #
class _SeedCapClient:
    """Minimal Anthropic-shaped client: records the seed kwarg, always returns
    an empty completion (no text blocks) so _do_call reports 'empty_reply'."""

    def __init__(self, seen_seeds):
        self._seen = seen_seeds
        self.messages = self

    def create(self, **kw):
        self._seen.append(kw.get("seed"))

        class _Resp:
            stop_reason = "end_turn"
            content = []          # no text blocks → empty_reply

        return _Resp()


def test_call_model_retries_empty_reply():
    """A transient empty reply is retried and the recovered text is returned."""
    from engine import llm_auth
    orig_client, orig_make = mb._client, llm_auth.make_call
    calls = {"n": 0}
    mb._client = lambda cfg: object()          # non-None → we reach make_call

    def fake_make_call(providers, call_fn, *, context=""):
        calls["n"] += 1
        if calls["n"] == 1:
            return (None, "empty_reply", "deepseek")   # first call blanks
        return ("recovered brief", None, "deepseek")   # retry succeeds
    llm_auth.make_call = fake_make_call
    try:
        text, reason = mb._call_model("sys", "user", {"empty_reply_retries": 2})
        assert text == "recovered brief" and reason is None
        assert calls["n"] == 2                          # one retry was enough
    finally:
        mb._client, llm_auth.make_call = orig_client, orig_make


def test_call_model_empty_reply_gives_up_after_retries():
    """When every attempt blanks, _call_model degrades to (None, 'empty_reply')
    after exactly 1 primary + N retries (default N=2)."""
    from engine import llm_auth
    orig_client, orig_make = mb._client, llm_auth.make_call
    calls = {"n": 0}
    mb._client = lambda cfg: object()

    def fake_make_call(providers, call_fn, *, context=""):
        calls["n"] += 1
        return (None, "empty_reply", "deepseek")
    llm_auth.make_call = fake_make_call
    try:
        text, reason = mb._call_model("sys", "user", {"empty_reply_retries": 2})
        assert text is None and reason == "empty_reply"
        assert calls["n"] == 3                          # 1 primary + 2 retries
    finally:
        mb._client, llm_auth.make_call = orig_client, orig_make


def test_call_model_retry_nudges_seed():
    """Primary attempt keeps seed=0 (determinism); each retry nudges the seed so a
    deterministically-empty completion can differ."""
    from engine import llm_auth
    orig_client, orig_make = mb._client, llm_auth.make_call
    seeds: list = []
    mb._client = lambda cfg: object()

    def fake_make_call(providers, call_fn, *, context=""):
        return call_fn(_SeedCapClient(seeds), "deepseek-v4-pro")
    llm_auth.make_call = fake_make_call
    try:
        text, reason = mb._call_model("sys", "user", {"empty_reply_retries": 2})
        assert text is None and reason == "empty_reply"
        assert seeds == [0, 1, 2]                        # deterministic, then nudged
    finally:
        mb._client, llm_auth.make_call = orig_client, orig_make


def test_call_model_no_retry_on_truncation():
    """A 'truncated' reply carries real (capped) content — it must NOT be retried."""
    from engine import llm_auth
    orig_client, orig_make = mb._client, llm_auth.make_call
    calls = {"n": 0}
    mb._client = lambda cfg: object()

    def fake_make_call(providers, call_fn, *, context=""):
        calls["n"] += 1
        return ("partial brief", "truncated", "deepseek")
    llm_auth.make_call = fake_make_call
    try:
        text, reason = mb._call_model("sys", "user", {})
        assert text == "partial brief" and reason == "truncated"
        assert calls["n"] == 1                           # no retry on real content
    finally:
        mb._client, llm_auth.make_call = orig_client, orig_make


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
