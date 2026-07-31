"""Chat plain-word projection — internal state enums never reach the chat model raw.

Live guest probes (2026-07-30/31, EN + zh) showed RISK_OFF and CAUTION verbatim in
Mastermind prose, copied out of read_world_state / read_contradictions payloads.
The fix is input-side (W2.1 lesson): chat_plain_words.project_plain_words rewrites
the finite state-enum vocabulary to plain words at the _dispatch_read_tool
boundary — and ONLY there.  Stored artifacts and the cortex internal loop keep the
raw enums (contradictions._RISK_OFF_VERDICTS matches on them).
"""
from __future__ import annotations

import copy
import json

from engine.neuralweb.chat_plain_words import project_plain_words


# ---------------------------------------------------------------------------
# Unit: the projection itself
# ---------------------------------------------------------------------------

class TestProjection:
    def test_verdict_field_value(self):
        """The verified leak: verdict RISK_OFF becomes the plain label."""
        out = project_plain_words({"verdict": "RISK_OFF"})
        assert out == {"verdict": "Risk-off"}

    def test_mtf_grade_value(self):
        """The other verified leak: commodity MTF grade CAUTION."""
        out = project_plain_words({"index": {"mtf_grade": "CAUTION"}})
        assert out == {"index": {"mtf_grade": "Caution"}}

    def test_token_embedded_in_prose(self):
        """contradictions.py composes readings like 'verdict=RISK_OFF' — the
        token must translate INSIDE prose, not only as a whole field value."""
        rec = {
            "b": {"reading": "verdict=RISK_OFF"},
            "note": "scale fields lean with the RISK_OFF verdict; the label has not flipped yet.",
        }
        out = project_plain_words(rec)
        assert out["b"]["reading"] == "verdict=Risk-off"
        assert "Risk-off verdict" in out["note"]
        assert "RISK_OFF" not in json.dumps(out)

    def test_state_tokens_from_live_payload(self):
        """State enums observed in the live world_state payload all map."""
        out = project_plain_words({
            "transition_state": "TRANSITIONING",
            "phase": {"label": "POLICY_PUT"},
            "contagion": {"state": "STEADY", "leadership_state": "BROKEN"},
            "ladder_state": "COUNTERTREND BOUNCE",
            "stages": ["RE-RATING", "BROADENING", "PRECIPICE"],
        })
        assert out["transition_state"] == "Transitioning"
        assert out["phase"]["label"] == "Policy put"
        assert out["contagion"] == {"state": "Steady", "leadership_state": "Broken"}
        assert out["ladder_state"] == "Countertrend bounce"
        assert out["stages"] == ["Re-rating", "Broadening", "Precipice"]

    def test_identifier_lookalikes_untouched(self):
        """Shouty identifiers that are NOT in the map survive byte-identical."""
        payload = {
            "pair": "USDJPY",
            "members": ["MAG7", "AUDUSD", "CPI-016"],
            "note": "MAG7 depth vs AUDUSD carry",
        }
        assert project_plain_words(payload) == payload

    def test_whole_token_boundaries(self):
        """Letters, digits and '_' glue: partial forms never match."""
        payload = {
            "a": "RISK_OFF_2",
            "b": "XCAUTION",
            "c": "CAUTIONARY",
            "d": "TREND-FOLLOWING",
        }
        assert project_plain_words(payload) == payload

    def test_lowercase_and_plain_forms_untouched_and_idempotent(self):
        """Lowercase 'caution' is already plain; a projected payload re-projects
        to itself (idempotent)."""
        payload = {"verdict": "caution", "label_en": "Risk-off", "label_zh": "避险"}
        once = project_plain_words(payload)
        assert once == payload
        assert project_plain_words(once) == once

    def test_verbatim_keys_skip_subtree(self):
        """Values under identifier keys pass verbatim even on a map hit — a
        ticker that collides with a future map entry can never be rewritten."""
        payload = {"symbol": "CAUTION", "tickers": ["AVOID", "WAIT"]}
        assert project_plain_words(payload) == payload

    def test_pure_no_mutation(self):
        """The projection builds new containers — the input dict is untouched
        (artifact-strip law: never mutate a possibly-reused dict)."""
        payload = {"verdict": "RISK_OFF", "nested": {"grade": "CAUTION"}}
        snapshot = copy.deepcopy(payload)
        project_plain_words(payload)
        assert payload == snapshot

    def test_non_string_scalars_pass_through(self):
        payload = {"score": 40, "flag": True, "x": None, "arr": [1.5, "RISK_ON"]}
        out = project_plain_words(payload)
        assert out == {"score": 40, "flag": True, "x": None, "arr": [1.5, "Risk-on"]}


# ---------------------------------------------------------------------------
# Integration: the chat read-tool boundary translates; storage + cortex do not
# ---------------------------------------------------------------------------

def _write_fixtures(root):
    nw = root / "data" / "neuralweb"
    nw.mkdir(parents=True)
    (nw / "world_state.json").write_text(json.dumps({
        "verdict": {
            "verdict": "RISK_OFF", "score": 40, "is_display_only": True,
            "label_en": "Risk-off", "label_zh": "避险", "asof": "2026-07-29",
        },
        "commodity_context": {"index": {"mtf_grade": "CAUTION"}},
    }), encoding="utf-8")
    (nw / "confluence_graph.json").write_text(json.dumps({
        "edges": [{
            "src": "data/regime/latest.json:regime",
            "dst": "market_state",
            "edge_type": "contradicts",
            "display_only": True,
            "note": "pair_id=regime-vs-market_state b=verdict=RISK_OFF",
        }],
    }), encoding="utf-8")


class TestChatBoundary:
    def test_read_world_state_projected(self, tmp_path):
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _write_fixtures(tmp_path)
        out = _dispatch_read_tool("read_world_state", {}, tmp_path)
        assert out["verdict"]["verdict"] == "Risk-off"
        assert out["commodity_context"]["index"]["mtf_grade"] == "Caution"
        # zh label survives alongside for zh answers
        assert out["verdict"]["label_zh"] == "避险"

    def test_read_contradictions_projected(self, tmp_path):
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _write_fixtures(tmp_path)
        out = _dispatch_read_tool("read_contradictions", {}, tmp_path)
        assert out["count"] == 1
        assert "RISK_OFF" not in json.dumps(out)
        assert "verdict=Risk-off" in out["contradictions"][0]["note"]

    def test_stored_artifact_keeps_raw_enum(self, tmp_path):
        """The projection is a read-time view — the artifact on disk is a
        contract other consumers pin and must keep the raw token."""
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        _write_fixtures(tmp_path)
        _dispatch_read_tool("read_world_state", {}, tmp_path)
        raw = (tmp_path / "data" / "neuralweb" / "world_state.json").read_text(encoding="utf-8")
        assert "RISK_OFF" in raw

    def test_cortex_internal_path_keeps_raw_enum(self, tmp_path):
        """cortex.dispatch_tool (metabolism/orchestrator loop) is NOT a chat
        surface — it must keep seeing the raw enums."""
        from engine.neuralweb.cortex import _tool_read_world_state
        _write_fixtures(tmp_path)
        out = _tool_read_world_state(tmp_path, {})
        assert out["verdict"]["verdict"] == "RISK_OFF"

    def test_refusal_path_still_refuses(self, tmp_path):
        from engine.neuralweb.ask_brain import _dispatch_read_tool
        out = _dispatch_read_tool("write_world_state", {}, tmp_path)
        assert "error" in out
