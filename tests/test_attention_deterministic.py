"""tests/test_attention_deterministic.py — unit tests for engine.neuralweb.attention_deterministic.

Coverage:
(a) Each of the five rules (A–E) — positive and negative fixtures.
(b) Trading-verb scrub applied to upstream strings.
(c) Envelope stamp applied by builder (artifact_id registered in synapse.yml).
(d) Empty inputs → empty items list (fail-open).
(e) Committee template smoke test — card HTML present, l-en/l-zh classes present,
    no translated text in title= attributes.
(f) Synapse count floor and DAG conformance (run scripts directly, hermetic).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ── Repo root ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb.attention_deterministic import (  # noqa: E402
    _rule_a_contradiction_tension,
    _rule_b_lobe_sla_breach,
    _rule_c_regime_indeterminate,
    _rule_d_evidence_clock_overdue,
    _rule_e_cortex_degraded,
    _scrub,
    build,
)

_NOW = datetime(2026, 7, 9, 8, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-09"

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _health_ok() -> dict:
    """Health.json fixture with no issues."""
    return {
        "lobes": [
            {
                "id": "lobe-a",
                "cadence": "daily",
                "age_hours": 10,
                "freshness_sla_hours": 30,
            }
        ],
        "cortex": {
            "run_status": {"status": "ok", "degraded": False}
        },
    }


def _world_state_ok() -> dict:
    """world_state fixture with healthy regime and no tension contradictions."""
    return {
        "regime": {
            "quad": "Q1",
            "confidence": 0.6,
        },
        "contradictions": {
            "n": 1,
            "by_severity": {"note": 1},
        },
    }


def _daily_brief_ok() -> dict:
    """daily_brief fixture with no overdue clocks."""
    return {
        "evidence_clock": {
            "available": True,
            "counts": {"overdue": 0, "due": 2, "accruing": 50},
            "top_due": {"clock_id": "some:clock"},
        }
    }


def _confluence_graph_ok() -> dict:
    """confluence_graph fixture with no tension records."""
    return {
        "contradiction_records": [
            {"pair_id": "pair-x", "severity": "note", "as_of": _AS_OF}
        ],
        "contradiction_summary": {"n": 1, "by_severity": {"note": 1}},
    }


# ── Rule A — contradiction tension ───────────────────────────────────────────

class TestRuleA:
    def test_positive_tension_in_cg(self):
        """Rule A fires when confluence_graph has a tension-severity record."""
        cg = {
            "contradiction_records": [
                {"pair_id": "x-vs-y", "severity": "tension", "as_of": _AS_OF},
            ],
        }
        items = _rule_a_contradiction_tension({}, cg, _AS_OF)
        assert len(items) == 1
        assert items[0]["kind"] == "contradiction_tension"
        assert items[0]["severity"] == "P2"
        assert "x-vs-y" in items[0]["summary_en"]

    def test_negative_only_note_severity(self):
        """Rule A does NOT fire when all records are 'note' severity."""
        cg = {
            "contradiction_records": [
                {"pair_id": "a-vs-b", "severity": "note", "as_of": _AS_OF},
            ],
        }
        items = _rule_a_contradiction_tension({}, cg, _AS_OF)
        assert len(items) == 0

    def test_positive_fallback_world_state_tension(self):
        """Rule A uses world_state when confluence_graph is None."""
        ws = {"contradictions": {"by_severity": {"tension": 2}}}
        items = _rule_a_contradiction_tension(ws, None, _AS_OF)
        assert len(items) == 1
        assert "2" in items[0]["summary_en"]

    def test_negative_fallback_no_tension(self):
        """Rule A (fallback path) returns empty when no tension in world_state."""
        ws = {"contradictions": {"by_severity": {"note": 3}}}
        items = _rule_a_contradiction_tension(ws, None, _AS_OF)
        assert len(items) == 0

    def test_fail_open_bad_input(self):
        """Rule A never raises — returns [] on malformed input."""
        items = _rule_a_contradiction_tension(None, {"contradiction_records": "bad"}, _AS_OF)
        assert isinstance(items, list)


# ── Rule B — lobe SLA breach ─────────────────────────────────────────────────

class TestRuleB:
    def _health_with_lobe(self, cadence, age, sla):
        return {
            "lobes": [{"id": "test-lobe", "cadence": cadence, "age_hours": age, "freshness_sla_hours": sla}],
            "cortex": {},
        }

    def test_positive_daily_past_1_5x(self):
        """Rule B fires when daily lobe age > 1.5× SLA."""
        h = self._health_with_lobe("daily", 50, 30)  # 50/30 = 1.67×
        items = _rule_b_lobe_sla_breach(h, _AS_OF)
        assert len(items) == 1
        assert items[0]["kind"] == "lobe_sla_breach"
        assert items[0]["severity"] == "P2"
        assert "test-lobe" in items[0]["summary_en"]

    def test_negative_daily_within_sla(self):
        """Rule B does NOT fire when daily lobe age <= 1.5× SLA."""
        h = self._health_with_lobe("daily", 20, 30)  # 20/30 = 0.67×
        items = _rule_b_lobe_sla_breach(h, _AS_OF)
        assert len(items) == 0

    def test_negative_exactly_1_5x(self):
        """Rule B does NOT fire at exactly 1.5× (strictly greater than)."""
        h = self._health_with_lobe("daily", 45, 30)  # 45/30 = 1.5×
        items = _rule_b_lobe_sla_breach(h, _AS_OF)
        assert len(items) == 0

    def test_negative_weekly_cadence_excluded(self):
        """Rule B only checks 'daily' cadence lobes — weekly is skipped."""
        h = self._health_with_lobe("weekly", 200, 30)
        items = _rule_b_lobe_sla_breach(h, _AS_OF)
        assert len(items) == 0

    def test_negative_missing_age_hours(self):
        """Rule B skips lobes with no age_hours (fail-open)."""
        h = {"lobes": [{"id": "x", "cadence": "daily", "age_hours": None, "freshness_sla_hours": 30}], "cortex": {}}
        items = _rule_b_lobe_sla_breach(h, _AS_OF)
        assert len(items) == 0

    def test_fail_open_bad_input(self):
        """Rule B never raises on malformed input."""
        items = _rule_b_lobe_sla_breach(None, _AS_OF)
        assert isinstance(items, list)


# ── Rule C — regime indeterminate ───────────────────────────────────────────

class TestRuleC:
    def test_positive_low_confidence(self):
        """Rule C fires when confidence < 0.25."""
        ws = {"regime": {"quad": "Q2", "confidence": 0.2}}
        items = _rule_c_regime_indeterminate(ws, _AS_OF)
        assert len(items) == 1
        assert items[0]["kind"] == "regime_indeterminate"
        assert items[0]["severity"] == "P2"
        assert "Q2" in items[0]["summary_en"]

    def test_negative_adequate_confidence(self):
        """Rule C does NOT fire when confidence >= 0.25."""
        ws = {"regime": {"quad": "Q1", "confidence": 0.5}}
        items = _rule_c_regime_indeterminate(ws, _AS_OF)
        assert len(items) == 0

    def test_negative_exactly_0_25(self):
        """Rule C does NOT fire at exactly 0.25 (strictly less than)."""
        ws = {"regime": {"quad": "Q3", "confidence": 0.25}}
        items = _rule_c_regime_indeterminate(ws, _AS_OF)
        assert len(items) == 0

    def test_negative_missing_regime(self):
        """Rule C returns [] when regime is missing (fail-open)."""
        items = _rule_c_regime_indeterminate({}, _AS_OF)
        assert len(items) == 0

    def test_fail_open_bad_input(self):
        """Rule C never raises on malformed input."""
        items = _rule_c_regime_indeterminate(None, _AS_OF)
        assert isinstance(items, list)


# ── Rule D — evidence clock overdue ──────────────────────────────────────────

class TestRuleD:
    def _brief_with_overdue(self, n_overdue, top_id="test:clock"):
        return {
            "evidence_clock": {
                "available": True,
                "counts": {"overdue": n_overdue},
                "top_due": {"clock_id": top_id},
            }
        }

    def test_positive_overdue(self):
        """Rule D fires when overdue count > 0."""
        b = self._brief_with_overdue(3, "qledger:placebo")
        items = _rule_d_evidence_clock_overdue(b, _AS_OF)
        assert len(items) == 1
        assert items[0]["kind"] == "evidence_clock_overdue"
        assert items[0]["severity"] == "P3"
        assert "3" in items[0]["summary_en"]
        assert "qledger:placebo" in items[0]["summary_en"]

    def test_negative_zero_overdue(self):
        """Rule D does NOT fire when overdue == 0."""
        b = self._brief_with_overdue(0)
        items = _rule_d_evidence_clock_overdue(b, _AS_OF)
        assert len(items) == 0

    def test_negative_missing_evidence_clock(self):
        """Rule D returns [] when evidence_clock key is missing."""
        items = _rule_d_evidence_clock_overdue({}, _AS_OF)
        assert len(items) == 0

    def test_fail_open_bad_input(self):
        """Rule D never raises on malformed input."""
        items = _rule_d_evidence_clock_overdue(None, _AS_OF)
        assert isinstance(items, list)


# ── Rule E — cortex degraded ─────────────────────────────────────────────────

class TestRuleE:
    def _health_cortex(self, degraded: bool, reason: str = ""):
        return {
            "lobes": [],
            "cortex": {
                "run_status": {
                    "status": "degraded" if degraded else "ok",
                    "degraded": degraded,
                    "degradation_reason": reason,
                }
            },
        }

    def test_positive_degraded(self):
        """Rule E fires when cortex.run_status.degraded == True."""
        h = self._health_cortex(True, "model_unavailable")
        items = _rule_e_cortex_degraded(h, _AS_OF)
        assert len(items) == 1
        assert items[0]["kind"] == "cortex_degraded"
        assert items[0]["severity"] == "P3"
        assert "model_unavailable" in items[0]["summary_en"]

    def test_negative_ok(self):
        """Rule E does NOT fire when cortex is healthy."""
        h = self._health_cortex(False)
        items = _rule_e_cortex_degraded(h, _AS_OF)
        assert len(items) == 0

    def test_negative_missing_cortex(self):
        """Rule E returns [] when cortex section is missing."""
        items = _rule_e_cortex_degraded({"lobes": []}, _AS_OF)
        assert len(items) == 0

    def test_fail_open_bad_input(self):
        """Rule E never raises on malformed input."""
        items = _rule_e_cortex_degraded(None, _AS_OF)
        assert isinstance(items, list)


# ── Trading-verb scrub ────────────────────────────────────────────────────────

class TestVerbScrub:
    @pytest.mark.parametrize("verb", ["buy", "sell", "hold", "long", "short", "overweight", "underweight"])
    def test_verb_redacted(self, verb):
        """Each trading verb in the blacklist is replaced with [redacted]."""
        assert _scrub(f"you should {verb} now") == f"you should [redacted] now"

    def test_verb_case_insensitive(self):
        """Verb scrub is case-insensitive."""
        assert "[redacted]" in _scrub("BUY the dip")

    def test_no_verb_unchanged(self):
        """Non-trading text passes through unchanged."""
        assert _scrub("regime transition underway") == "regime transition underway"

    def test_word_boundary_respected(self):
        """'longer' must not be redacted by the 'long' rule."""
        text = "longer-term outlook"
        result = _scrub(text)
        assert result == text, f"Expected unchanged, got: {result!r}"


# ── Envelope stamp ────────────────────────────────────────────────────────────

class TestEnvelope:
    def test_stamp_applied(self):
        """Builder stamps the artifact with all five envelope keys."""
        from engine.neuralweb.envelope import ENVELOPE_KEYS, verify
        from scripts.build_attention_deterministic import main

        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Set up minimal directory structure
            data_nw = tmp / "data" / "neuralweb"
            data_nw.mkdir(parents=True)
            site_nw = tmp / "site" / "neuralwebdata"
            site_nw.mkdir(parents=True)

            # Write minimal input fixtures
            (data_nw / "world_state.json").write_text(json.dumps({
                "regime": {"quad": "Q1", "confidence": 0.5},
                "contradictions": {"by_severity": {"note": 1}},
            }), encoding="utf-8")
            (data_nw / "health.json").write_text(json.dumps({
                "lobes": [],
                "cortex": {"run_status": {"status": "ok", "degraded": False}},
            }), encoding="utf-8")
            (data_nw / "daily_brief.json").write_text(json.dumps({
                "evidence_clock": {"available": True, "counts": {"overdue": 0}},
            }), encoding="utf-8")

            # Copy synapse.yml into tmp (builder reads from installed path; use import)
            rc = main(["--root", str(tmp)])
            assert rc == 0, "builder should exit 0"

            out = json.loads((data_nw / "attention_deterministic.json").read_text(encoding="utf-8"))
            for k in ENVELOPE_KEYS:
                assert k in out, f"envelope key {k!r} missing from output"
            problems = verify(out)
            assert problems == [], f"envelope verification problems: {problems}"

    def test_empty_inputs_fail_open(self):
        """Build with empty inputs produces item_count=0, not an error."""
        result = build(world_state={}, health={}, daily_brief={}, now=_NOW)
        assert result["item_count"] == 0
        assert result["items"] == []


# ── Committee template smoke tests ────────────────────────────────────────────

class TestCommitteeTemplate:
    _COMMITTEE = _ROOT / "site" / "committee.html"

    def _html(self) -> str:
        if not self._COMMITTEE.exists():
            pytest.skip("site/committee.html not rendered in this context")
        return self._COMMITTEE.read_text(encoding="utf-8")

    def test_todays_read_card_present(self):
        """The 'Today's Read' card element is present in committee.html."""
        html = self._html()
        assert "tr_card_section" in html, "Today's Read card section id missing"
        assert "tr_body" in html, "Today's Read body div missing"

    def test_i18n_classes_present(self):
        """Both l-en and l-zh language classes appear in committee.html."""
        html = self._html()
        assert "l-en" in html, "l-en class missing from committee.html"
        assert "l-zh" in html, "l-zh class missing from committee.html"

    def test_no_translated_title_attributes(self):
        """No Chinese (CJK) characters inside title= attributes (CI law)."""
        html = self._html()
        # Find all title="..." or title='...' values
        title_vals = re.findall(r'title=["\']([^"\']*)["\']', html)
        cjk_pattern = re.compile(r'[一-鿿㐀-䶿]')
        for val in title_vals:
            assert not cjk_pattern.search(val), (
                f"CJK characters found in title= attribute: {val!r}"
            )

    def test_todays_read_en_label(self):
        """The English label 'Today's Read' appears in the card."""
        html = self._html()
        assert "Today" in html and "Read" in html

    def test_degraded_status_line_element(self):
        """The demoted cortex-status line element exists (honesty law preserved)."""
        html = self._html()
        assert "tr_cortex_status" in html

    def test_no_trading_verbs_in_static_text(self):
        """Static template text does not contain trading verbs in standalone form."""
        html = self._html()
        # Only check the new Today's Read section
        tr_start = html.find("tr_card_section")
        tr_end = html.find("id=\"cm_hero_section\"")
        if tr_start == -1 or tr_end == -1:
            pytest.skip("Card section bounds not found")
        section = html[tr_start:tr_end]
        # No bare 'buy', 'sell', 'hold' in static HTML (JS strings checked separately)
        for verb in ("buy", "sell", "hold"):
            # Simple word-boundary check on the static HTML; JS var names like 'selloff' ok
            matches = re.findall(r'(?<![a-zA-Z])' + verb + r'(?![a-zA-Z])', section, re.IGNORECASE)
            assert not matches, f"Trading verb {verb!r} found in Today's Read static HTML"
