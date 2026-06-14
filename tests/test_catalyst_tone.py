"""Tests for engine/catalyst_tone.py — the LLM Tier-A digest leaf module.

No network / no API key needed: the model call is stubbed; the safety gates
(JSON parse, schema validation, verbatim-citation verification, confidence floor,
degrade-never-raise) are exercised as pure functions. Run as a plain script:
    python tests/test_catalyst_tone.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import catalyst_tone as ct  # noqa: E402

DOC = ("The Committee decided to raise the target range for the federal funds rate "
       "by 25 basis points. Inflation remains elevated and the Committee is strongly "
       "committed to returning inflation to its 2 percent objective.")


def test_extract_json():
    assert ct._extract_json('{"a": 1}') == {"a": 1}
    assert ct._extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert ct._extract_json('Here is the result:\n{"a": 3}\nThanks!') == {"a": 3}
    assert ct._extract_json('not json at all') is None
    assert ct._extract_json('') is None
    assert ct._extract_json('[1, 2, 3]') is None  # a list is not a record


def test_validate_clamps_and_enums():
    v = ct._validate({"tone_score": 5, "risk_delta": -9,
                      "guidance_direction": "TIGHTENING", "shock_reversible": "bogus",
                      "confidence": "HIGH", "evidence": "nope"})
    assert v["tone_score"] == 1.0           # clamped to [-1,1]
    assert v["risk_delta"] == -1.0          # clamped
    assert v["guidance_direction"] == "tightening"   # lowercased, valid enum
    assert v["shock_reversible"] == "unknown"        # invalid -> unknown
    assert v["confidence"] == "high"
    assert v["evidence"] == []              # non-list -> []


def test_validate_bad_numbers_and_conf():
    v = ct._validate({"tone_score": "abc", "confidence": "wat"})
    assert v["tone_score"] == 0.0           # unparseable number -> neutral
    assert v["confidence"] == "low"         # invalid enum -> low


def test_citation_verification_drops_fabricated():
    rec = ct._validate({
        "tone_score": 0.8, "guidance_direction": "tightening",
        "shock_reversible": "persistent", "confidence": "high",
        "evidence": [
            {"field": "guidance_direction",
             "quote_span": "raise the target range for the federal funds rate"},  # real
            {"field": "tone_score",
             "quote_span": "strongly committed to returning inflation"},          # real
            {"field": "shock_reversible",
             "quote_span": "a structural regime break in liquidity"},             # FABRICATED
        ],
    })
    ct._verify_citations(rec, DOC)
    assert rec["guidance_direction"] == "tightening"   # verified -> kept
    assert rec["tone_score"] == 0.8                     # verified -> kept
    assert rec["shock_reversible"] == "unknown"         # fabricated -> dropped
    assert "shock_reversible" in rec["dropped_fields"]
    assert all(e["field"] != "shock_reversible" for e in rec["evidence"])


def test_field_without_evidence_is_dropped():
    rec = ct._validate({"tone_score": 0.5, "confidence": "high", "evidence": []})
    ct._verify_citations(rec, DOC)
    assert rec["tone_score"] == 0.0          # no supporting citation -> neutral
    assert "tone_score" in rec["dropped_fields"]


def test_confidence_floor_collapses():
    rec = ct._validate({"tone_score": 0.9, "guidance_direction": "tightening",
                        "confidence": "low",
                        "evidence": [{"field": "tone_score",
                                      "quote_span": "Inflation remains elevated"}]})
    ct._verify_citations(rec, DOC)
    ct._apply_confidence_floor(rec, "high")
    assert rec["confidence_gated"] is True
    assert rec["tone_score"] == 0.0
    assert rec["guidance_direction"] == "unknown"
    assert rec["evidence"] == []


def test_confidence_floor_passes_when_met():
    rec = ct._validate({"tone_score": 0.7, "confidence": "high",
                        "evidence": [{"field": "tone_score",
                                      "quote_span": "Inflation remains elevated"}]})
    ct._verify_citations(rec, DOC)
    ct._apply_confidence_floor(rec, "high")
    assert rec["confidence_gated"] is False
    assert rec["tone_score"] == 0.7


def test_digest_disabled_returns_none():
    assert ct.enabled() is False             # config ships default-off
    assert ct.digest_document(DOC, kind="fomc") is None


def test_digest_degrades_without_key():
    orig_cfg, orig_call = ct._cfg, ct._call_model
    ct._cfg = lambda: {"enabled": True, "llm_min_confidence": "high"}
    ct._call_model = lambda *a, **k: (None, "no_client_or_key")
    try:
        rec = ct.digest_document(DOC, kind="fomc")
        assert rec is not None
        assert rec["degraded_reason"] == "no_client_or_key"
        assert rec["tone_score"] == 0.0 and rec["shock_reversible"] == "unknown"
        assert rec["is_context_only"] is True
    finally:
        ct._cfg, ct._call_model = orig_cfg, orig_call


def test_digest_full_path_with_stubbed_model():
    orig_cfg, orig_call = ct._cfg, ct._call_model
    ct._cfg = lambda: {"enabled": True, "llm_min_confidence": "high"}
    reply = ('{"tone_score": 0.8, "guidance_direction": "tightening", '
             '"risk_delta": 0.4, "shock_reversible": "unknown", "confidence": "high", '
             '"evidence": ['
             '{"field": "guidance_direction", "quote_span": "raise the target range for the federal funds rate"}, '
             '{"field": "tone_score", "quote_span": "strongly committed to returning inflation"}, '
             '{"field": "risk_delta", "quote_span": "totally fabricated phrase not in the doc"}]}')
    ct._call_model = lambda *a, **k: (reply, None)
    try:
        rec = ct.digest_document(DOC, kind="fomc_statement", context="FOMC test")
        assert rec["guidance_direction"] == "tightening"   # verified
        assert rec["tone_score"] == 0.8                     # verified
        assert rec["risk_delta"] == 0.0                     # fabricated citation -> dropped
        assert "risk_delta" in rec["dropped_fields"]
        assert rec["degraded_reason"] is None
        assert rec["confidence_gated"] is False
        assert rec["is_context_only"] is True
    finally:
        ct._cfg, ct._call_model = orig_cfg, orig_call


def test_never_raises_on_garbage_reply():
    orig_cfg, orig_call = ct._cfg, ct._call_model
    ct._cfg = lambda: {"enabled": True, "llm_min_confidence": "high"}
    ct._call_model = lambda *a, **k: ("this is not json", None)
    try:
        rec = ct.digest_document(DOC)
        assert rec["degraded_reason"] == "unparseable_reply"
    finally:
        ct._cfg, ct._call_model = orig_cfg, orig_call


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
