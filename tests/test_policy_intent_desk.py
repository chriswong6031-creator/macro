"""Tests for engine.policy_intent_desk — deterministic parts (LLM call injected)."""
from __future__ import annotations

import json

from engine import policy_intent_desk as pid

_REPLY = json.dumps({
    "regime_context": "Low-yield engineering + re-industrialization; revealed > narrative.",
    "confidence": "medium",
    "theses": [
        {"actor": "admin", "subject": "XLE", "lean": "overweight", "conviction": "medium",
         "horizon_d": 40, "thesis": "Energy theater + Iran fragility", "evidence": ["energy theater"],
         "dissent": "ceasefire holds, oil fades", "falsifier_text": "XLE lags SPY by 5%"},
        {"actor": "fed", "subject": "TLT", "lean": "avoid", "conviction": "low",
         "horizon_d": 60, "thesis": "Yield suppression but term-premium risk", "evidence": ["dollar theater"],
         "dissent": "growth scare bid", "falsifier_text": "TLT beats SPY by 5%"},
        {"actor": "admin", "subject": "NOTATICKER", "lean": "overweight"},   # dropped: bad subject
        {"actor": "admin", "subject": "XLF", "lean": "sideways"},            # dropped: bad lean
    ],
})


def _fake_call(system, user, cfg):
    return _REPLY, None


_REPLY_BILINGUAL = json.dumps({
    "regime_context": "Low-yield engineering + re-industrialization.",
    "regime_context_zh": "压低收益率 + 再工业化。",
    "confidence": "medium",
    "theses": [
        {"actor": "admin", "subject": "XLE", "lean": "overweight", "conviction": "medium",
         "horizon_d": 40, "thesis": "Energy theater", "thesis_zh": "能源战区",
         "evidence": ["energy theater"], "dissent": "ceasefire holds", "dissent_zh": "停火维持",
         "falsifier_text": "XLE lags SPY by 5%", "falsifier_text_zh": "XLE 跑输 SPY 5%"},
    ],
})


def _fake_call_bilingual(system, user, cfg):
    return _REPLY_BILINGUAL, None


def test_derive_check_rel_return():
    ov = pid._derive_check("XLE", "overweight", 40, pid._cfg())
    assert ov["kind"] == "rel_return" and ov["op"] == "<" and ov["threshold"] == -0.05 and ov["vs"] == "SPY"
    av = pid._derive_check("TLT", "avoid", 60, pid._cfg())
    assert av["op"] == ">" and av["threshold"] == 0.05
    # ITA (defense, no local series) is now GRADEABLE via a correlated surrogate (XLI)
    corr = pid._derive_check("ITA", "overweight", 40, pid._cfg())
    assert corr["kind"] == "rel_return" and corr["via"] == "correlated"
    assert corr["subject_ticker"] == "XLI" and corr["surrogate_of"] == "ITA"
    assert corr["threshold"] < -0.05            # wider threshold than a direct proxy (×1.6)
    # a cash/dollar soft (no equity surrogate) stays soft
    soft = pid._derive_check("UUP", "overweight", 40, pid._cfg())
    assert soft["kind"] == "soft" and soft["via"] == "soft"


def test_synthesize_builds_and_validates_theses():
    state = {"as_of": "2026-06-18", "allowed_subjects": sorted(pid._ALLOWED)}
    brief = pid.synthesize(state, pid._cfg(), call=_fake_call)
    assert brief["schema"] == pid.SCHEMA and brief["is_context_only"] is True
    subs = [t["subject"] for t in brief["theses"]]
    assert subs == ["XLE", "TLT"]                       # bad subject + bad lean dropped
    xle = brief["theses"][0]
    assert xle["falsifier"]["check"]["kind"] == "rel_return"
    assert xle["check_by"] and xle["actor"] == "admin"
    assert brief["confidence"] == "medium"


def test_synthesize_captures_bilingual_fields():
    state = {"as_of": "2026-06-18", "allowed_subjects": sorted(pid._ALLOWED)}
    brief = pid.synthesize(state, pid._cfg(), call=_fake_call_bilingual)
    assert brief["regime_context_zh"] == "压低收益率 + 再工业化。"
    assert brief["disclaimer_zh"] and "意图台" in brief["disclaimer_zh"]   # static zh disclaimer
    th = brief["theses"][0]
    assert th["thesis_zh"] == "能源战区" and th["dissent_zh"] == "停火维持"
    assert th["falsifier"]["text_zh"] == "XLE 跑输 SPY 5%"


def test_synthesize_zh_fields_degrade_to_none_when_absent():
    # English-only reply (no *_zh keys) → zh fields are None; the template falls back to en.
    state = {"as_of": "2026-06-18", "allowed_subjects": sorted(pid._ALLOWED)}
    brief = pid.synthesize(state, pid._cfg(), call=_fake_call)
    assert brief["regime_context_zh"] is None
    assert brief["disclaimer_zh"]                                          # static, always present
    assert brief["theses"][0]["thesis_zh"] is None
    assert brief["theses"][0]["falsifier"]["text_zh"] is None


def test_synthesize_degrades_without_key():
    brief = pid.synthesize({"as_of": "2026-06-18"}, pid._cfg(), call=lambda s, u, c: (None, "no_client_or_key"))
    assert brief["theses"] == [] and brief["degraded_reason"] == "no_client_or_key"


def test_build_thesis_rejects_bad():
    assert pid._build_thesis({"subject": "ZZZ", "lean": "overweight"}, 0, "2026-06-18", pid._cfg()) is None
    assert pid._build_thesis({"subject": "XLE", "lean": "nope"}, 0, "2026-06-18", pid._cfg()) is None
    ok = pid._build_thesis({"subject": "xle", "lean": "OverWeight"}, 0, "2026-06-18", pid._cfg())
    assert ok and ok["subject"] == "XLE" and ok["lean"] == "overweight"


def test_gather_state_reads_intel(tmp_path):
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "policy" / "intel.json").write_text(json.dumps({
        "as_of": "2026-06-18", "thesis": {"en": "T"},
        "administration": {"theaters": [{"title_en": "China", "basis": "FACT", "capital_en": "x"}]},
        "rotation": {"targeted": [{"theme_en": "Defense", "proxies": ["ITA"], "basis": "FACT"}]},
        "predictions": [{"text_en": "P open", "status": "open"}, {"text_en": "P hit", "status": "hit"}],
    }))
    (tmp_path / "data" / "regime" / "latest.json").write_text(json.dumps({"quad_name": "Goldilocks"}))
    st = pid.gather_state(root=tmp_path)
    assert st["thesis"] == "T" and st["market"]["quad"] == "Goldilocks"
    assert len(st["theaters"]) == 1 and st["open_predictions"] == ["P open"]
    assert "XLE" in st["scorable_subjects"]


def test_gather_state_none_without_intel(tmp_path):
    assert pid.gather_state(root=tmp_path) is None


def test_run_persists_and_appends(tmp_path):
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "site").mkdir()
    (tmp_path / "data" / "policy" / "intel.json").write_text(json.dumps({"as_of": "2026-06-18", "thesis": {"en": "T"}}))
    brief = pid.run(persist=True, root=tmp_path, force=True, call=_fake_call)
    assert brief and len(brief["theses"]) == 2
    assert (tmp_path / "site" / "policy_intent.json").exists()
    rows = (tmp_path / "data" / "policy_intent" / "theses.jsonl").read_text().strip().splitlines()
    assert len(rows) == 2
    r0 = json.loads(rows[0])
    assert r0["status"] == "open" and r0["subject"] == "XLE" and r0["falsifier"]["check"]["kind"] == "rel_return"
    # public copy drops raw_text
    pub = json.loads((tmp_path / "site" / "policy_intent.json").read_text())
    assert "raw_text" not in pub


def test_gld_aliases_to_scorable_gold_futures():
    tk, vs, kind, via = pid._resolve_subject("GLD")
    assert (tk, vs, kind, via) == ("GC_F", "SPY", "rel_return", "direct")
    chk = pid._derive_check("GLD", "overweight", 40, pid._cfg())
    assert chk["kind"] == "rel_return" and chk["subject_ticker"] == "GC_F"


def test_correlated_surrogates_are_scorable_and_resolve():
    """Every soft→surrogate mapping must point at a SCORABLE ticker (else the surrogate
    grade silently expires too) and resolve to a 'correlated' rel_return check."""
    for soft, surrogate in pid._SOFT_PROXY.items():
        assert surrogate in pid._SCORABLE, f"{soft} -> {surrogate}: surrogate not scorable"
        tk, vs, kind, via = pid._resolve_subject(soft)
        assert kind == "rel_return" and via == "correlated" and tk == surrogate


def test_every_scorable_subject_has_a_price_series():
    """Regression guard for the GLD class of bug: a SCORABLE subject MUST resolve to a
    ticker that actually has a data/yahoo price series, else it scores 'expired', never graded."""
    from lib import config
    ydir = config.ROOT / "data" / "yahoo"
    for s in pid._SCORABLE:
        tk, vs, kind, via = pid._resolve_subject(s)
        assert kind == "rel_return", f"{s} should be scorable"
        assert (ydir / f"{tk}.parquet").exists(), f"{s} -> {tk}: no price series (would never score)"


def test_run_thesis_ids_carry_run_token(tmp_path):
    (tmp_path / "data" / "policy").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "site").mkdir()
    (tmp_path / "data" / "policy" / "intel.json").write_text(json.dumps({"as_of": "2026-06-18", "thesis": {"en": "T"}}))
    brief = pid.run(persist=True, root=tmp_path, force=True, call=_fake_call)
    ids = [t["id"] for t in brief["theses"]]
    # ids are run-token-stamped (date-token-seq), so same-day re-runs can't collide
    assert all(len(i.split("-")) >= 3 for i in ids), ids
    assert len(set(ids)) == len(ids)
