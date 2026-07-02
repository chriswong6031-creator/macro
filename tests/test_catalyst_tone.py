"""Tests for engine/catalyst_tone.py — the LLM Tier-A digest leaf module.

No network / no API key needed: the model call is stubbed; the safety gates
(JSON parse, schema validation, verbatim-citation verification, confidence floor,
degrade-never-raise) are exercised as pure functions. Run as a plain script:
    python tests/test_catalyst_tone.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import date

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
    orig = ct._cfg
    ct._cfg = lambda: {"enabled": False}     # force disabled, independent of operational config
    try:
        assert ct.enabled() is False
        assert ct.digest_document(DOC, kind="fomc") is None
    finally:
        ct._cfg = orig


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


# --------------------------------------------------------------------------- #
# Stage 3 — source fetch + daily snapshot
# --------------------------------------------------------------------------- #
def test_recent_fomc():
    assert ct._recent_fomc(date(2026, 6, 18), 120) == date(2026, 6, 17)  # last meeting
    assert ct._recent_fomc(date(2026, 6, 18), 0) is None                 # 1 day old > 0
    assert ct._recent_fomc(date(2020, 1, 1), 120) is None                # before all


def test_html_to_statement_trims_body():
    html = ("<html><head><style>x{}</style></head><body><nav>menu junk</nav>"
            "<div>Recent indicators suggest economic activity expanded. "
            "The Committee decided to maintain the target range. "
            "Voting for the monetary policy action were all members.</div></body></html>")
    out = ct._html_to_statement(html, 20000)
    assert out.startswith("Recent indicators")
    assert "maintain the target range" in out
    assert "menu junk" not in out          # trimmed before the body
    assert "Voting for the monetary policy action" not in out  # trimmed after the body


def test_daily_snapshot_disabled():
    orig = ct._cfg
    ct._cfg = lambda: {"enabled": False}
    try:
        assert ct.daily_snapshot("2026-06-18") is None
    finally:
        ct._cfg = orig


def test_daily_snapshot_nothing_recent():
    orig_cfg, orig_recent = ct._cfg, ct._recent_fomc
    ct._cfg = lambda: {"enabled": True}
    ct._recent_fomc = lambda today, age: None
    try:
        assert ct.daily_snapshot("2026-06-18") is None
    finally:
        ct._cfg, ct._recent_fomc = orig_cfg, orig_recent


def test_daily_snapshot_stubbed_compacts():
    orig_cfg, orig_recent, orig_dig = ct._cfg, ct._recent_fomc, ct._cached_or_digest_fomc
    ct._cfg = lambda: {"enabled": True, "max_age_days": 120}
    ct._recent_fomc = lambda today, age: date(2026, 6, 17)
    ct._cached_or_digest_fomc = lambda meeting, cfg: {
        "schema": "catalyst_tone.v1", "is_context_only": True, "kind": "fomc_statement",
        "doc_id": "fomc_2026-06-17", "asof": "2026-06-17", "tone_score": 0.3,
        "guidance_direction": "on_hold", "risk_delta": 0.0, "shock_reversible": "unknown",
        "confidence": "high", "confidence_gated": False, "dropped_fields": [],
        "evidence": [], "degraded_reason": None, "disclaimer": "x", "extra": "stripped"}
    try:
        snap = ct.daily_snapshot("2026-06-18")
        assert snap["kind"] == "fomc_statement"
        assert snap["tone_score"] == 0.3 and snap["guidance_direction"] == "on_hold"
        assert "disclaimer" in snap
        assert "extra" not in snap          # compacted to the snapshot key set
    finally:
        ct._cfg, ct._recent_fomc, ct._cached_or_digest_fomc = orig_cfg, orig_recent, orig_dig


# --------------------------------------------------------------------------- #
# Stage 2 — dislocation narrative cross-check (additive; never changes verdict)
# --------------------------------------------------------------------------- #
def test_dislocation_narrative_corroborates():
    from engine import dislocation as dz
    n = dz._catalyst_narrative("buyable_washout",
                               {"shock_reversible": "reversible", "confidence": "high",
                                "doc_id": "fomc_x", "evidence": []})
    assert n["agreement"] == "corroborates" and n["is_context_only"] is True
    n2 = dz._catalyst_narrative("stand_aside",
                                {"shock_reversible": "persistent", "confidence": "high"})
    assert n2["agreement"] == "corroborates"


def test_dislocation_narrative_diverges():
    from engine import dislocation as dz
    n = dz._catalyst_narrative("buyable_washout",
                               {"shock_reversible": "persistent", "confidence": "high"})
    assert n["agreement"] == "diverges" and "caution" in n["note"].lower()
    n2 = dz._catalyst_narrative("stand_aside",
                                {"shock_reversible": "reversible", "confidence": "medium"})
    assert n2["agreement"] == "diverges"


def test_dislocation_narrative_none_cases():
    from engine import dislocation as dz
    assert dz._catalyst_narrative("buyable_washout", None) is None          # no catalyst
    assert dz._catalyst_narrative("buyable_washout",
                                  {"shock_reversible": "unknown"}) is None   # gated/unknown
    assert dz._catalyst_narrative("calm",
                                  {"shock_reversible": "reversible"}) is None  # no live dislocation


# --------------------------------------------------------------------------- #
# Stage 3b — dislocation-day event trigger (GDELT digest)
# --------------------------------------------------------------------------- #
def test_event_snapshot_disabled():
    orig = ct._cfg
    ct._cfg = lambda: {"enabled": False, "event_enabled": False}
    try:
        assert ct.event_snapshot("2026-06-14") is None
    finally:
        ct._cfg = orig


def test_event_snapshot_no_headlines():
    oc, of, og = ct._cfg, ct._fetch_event_headlines, ct._gdelt_snapshot_get
    ct._cfg = lambda: {"enabled": True, "event_enabled": True, "llm_min_confidence": "high"}
    ct._fetch_event_headlines = lambda today, cfg: []
    ct._gdelt_snapshot_get = lambda today, cfg: None  # no cached snapshot for this date
    try:
        assert ct.event_snapshot("2026-06-14") is None
    finally:
        ct._cfg, ct._fetch_event_headlines, ct._gdelt_snapshot_get = oc, of, og


def test_event_snapshot_stubbed():
    oc, of, om, og = ct._cfg, ct._fetch_event_headlines, ct._call_model, ct._gdelt_snapshot_get
    ct._cfg = lambda: {"enabled": True, "event_enabled": True, "llm_min_confidence": "high"}
    ct._gdelt_snapshot_get = lambda today, cfg: None  # force fallthrough to fetch stub
    ct._fetch_event_headlines = lambda today, cfg: [
        "Stocks plunge as Fed signals higher-for-longer", "Treasury yields spike on hot inflation"]
    reply = json.dumps({"tone_score": 0.7, "risk_delta": 0.6, "shock_reversible": "persistent",
                        "confidence": "high",
                        "evidence": [{"field": "shock_reversible",
                                      "quote_span": "Fed signals higher-for-longer"}]})
    ct._call_model = lambda *a, **k: (reply, None)
    try:
        ev = ct.event_snapshot("2026-06-14", context="dislocation test")
        assert ev["kind"] == "dislocation"
        assert ev["shock_reversible"] == "persistent"   # citation verified against the headline
        assert ev["doc_id"].startswith("event_")
    finally:
        ct._cfg, ct._fetch_event_headlines, ct._call_model, ct._gdelt_snapshot_get = oc, of, om, og


def test_norm_matches_unicode_and_mojibake_dashes():
    # Regression: Fed rate ranges use the non-breaking hyphen U+2011; the model's quote
    # and/or the reply encoding can differ from the source ("3â€‑1/2" mojibake). _norm must
    # reconcile typography so a GENUINE verbatim quote isn't wrongly dropped -> neutral.
    src = ct._norm("maintain the target range for the federal funds rate at "
                   "3‑1/2 to 3‑3/4 percent")
    assert ct._norm("target range for the federal funds rate at 3-1/2 to 3-3/4 percent") in src   # ascii hyphen
    assert ct._norm("target range for the federal funds rate at "
                    "3â€‑1/2 to 3â€‑3/4 percent") in src             # mojibake form
    # anti-hallucination invariant still holds: words not in the source never match
    assert ct._norm("a fabricated structural regime break in liquidity") not in src


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
