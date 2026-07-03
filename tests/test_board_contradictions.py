"""tests/test_board_contradictions.py — Unit tests for W2 check_board_contradictions.py
and the W2 arbiter band demotion rule (rule 3 in build_stock_library).

Covers:
* check_board_contradictions: all 4 invariant pass + fail cases.
* Arbiter rule 3: band demoted when verdict is lagging/no-clear-edge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_board_contradictions import _check  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _artifact(tmp_path: Path, rows: list[dict]) -> str:
    """Write a minimal us_standouts.json and return its path."""
    data = {"as_of": "2026-07-01", "buy": rows, "watch": [], "laggards": []}
    p = tmp_path / "us_standouts.json"
    p.write_text(json.dumps(data))
    return str(p)


def _clean_row(ticker: str = "AAPL", **overrides) -> dict:
    """Minimal clean row that passes all 4 invariants."""
    row = {
        "ticker": ticker,
        "state": "HOLD",
        "label": "Hold",
        "urgency": "caution",
        "lane": "buy",
        "alpha": 0.5,
        "conviction": {
            "band": "neutral",
            "verdict": "strong edge",
        },
        "signal": {"ticks": 1},
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# absent artifact = no violations (graceful degrade)
# ---------------------------------------------------------------------------

def test_absent_artifact_clean(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    violations = _check(path)
    assert violations == [], "absent artifact must not produce violations"


# ---------------------------------------------------------------------------
# invariant (a): FRESH-BUY with stale cross
# ---------------------------------------------------------------------------

class TestInvariantA:
    def test_passes_when_fresh_buy_with_fresh_ticks(self, tmp_path):
        row = _clean_row(state="FRESH BUY", conviction={"band": "high", "verdict": "strong edge"},
                         signal={"ticks": 2})  # ticks=2, FRESH_TICKS=2, 2 <= FRESH_TICKS+1=3 → OK
        violations = _check(_artifact(tmp_path, [row]))
        a_viol = [v for v in violations if v.startswith("(a)")]
        assert not a_viol, f"Unexpected (a) violations: {a_viol}"

    def test_fails_when_fresh_buy_with_stale_ticks(self, tmp_path):
        row = _clean_row(state="FRESH BUY", conviction={"band": "high", "verdict": "strong edge"},
                         signal={"ticks": 10})  # 10 > FRESH_TICKS+1=3 → violation
        violations = _check(_artifact(tmp_path, [row]))
        a_viol = [v for v in violations if v.startswith("(a)")]
        assert len(a_viol) == 1, f"Expected 1 (a) violation, got: {a_viol}"
        assert "ticks=10" in a_viol[0]

    def test_fails_when_fresh_buy_with_extended_grade(self, tmp_path):
        row = _clean_row(state="TURN SIGNALED", conviction={"band": "high", "verdict": "strong edge"},
                         signal={"ticks": 1},
                         extension_read={"grade": "parabolic"})
        violations = _check(_artifact(tmp_path, [row]))
        a_viol = [v for v in violations if v.startswith("(a)")]
        assert a_viol, f"Expected (a) violation for extended grade"


# ---------------------------------------------------------------------------
# invariant (b): urgency=imminent on blocked/BOTTOMING state
# ---------------------------------------------------------------------------

class TestInvariantB:
    def test_passes_when_imminent_with_fresh_state(self, tmp_path):
        row = _clean_row(state="FRESH BUY", urgency="imminent",
                         signal={"ticks": 1},
                         conviction={"band": "high", "verdict": "strong edge"})
        violations = _check(_artifact(tmp_path, [row]))
        b_viol = [v for v in violations if v.startswith("(b)")]
        assert not b_viol, f"Unexpected (b) violations: {b_viol}"

    def test_fails_when_imminent_with_bottoming_state(self, tmp_path):
        row = _clean_row(state="BOTTOMING", urgency="imminent",
                         conviction={"band": "neutral", "verdict": "building edge"})
        violations = _check(_artifact(tmp_path, [row]))
        b_viol = [v for v in violations if v.startswith("(b)")]
        assert b_viol, f"Expected (b) violation for imminent+BOTTOMING"

    def test_fails_when_imminent_with_blocked_label(self, tmp_path):
        row = _clean_row(state="HOLD", urgency="imminent", label="Hold (blocked)",
                         conviction={"band": "neutral", "verdict": "building edge"})
        violations = _check(_artifact(tmp_path, [row]))
        b_viol = [v for v in violations if v.startswith("(b)")]
        assert b_viol, f"Expected (b) violation for imminent+blocked label"


# ---------------------------------------------------------------------------
# invariant (c): high/constructive band with lagging/no-clear-edge verdict
# ---------------------------------------------------------------------------

class TestInvariantC:
    def test_passes_when_high_band_strong_verdict(self, tmp_path):
        row = _clean_row(conviction={"band": "high", "verdict": "strong edge"})
        violations = _check(_artifact(tmp_path, [row]))
        c_viol = [v for v in violations if v.startswith("(c)")]
        assert not c_viol

    def test_fails_when_high_band_lagging_verdict(self, tmp_path):
        row = _clean_row(conviction={"band": "high", "verdict": "Lagging"})
        violations = _check(_artifact(tmp_path, [row]))
        c_viol = [v for v in violations if v.startswith("(c)")]
        assert c_viol, f"Expected (c) violation for high band + Lagging verdict"

    def test_fails_when_constructive_band_no_clear_edge(self, tmp_path):
        row = _clean_row(conviction={"band": "constructive", "verdict": "no clear edge"})
        violations = _check(_artifact(tmp_path, [row]))
        c_viol = [v for v in violations if v.startswith("(c)")]
        assert c_viol, f"Expected (c) violation for constructive band + no-clear-edge"

    def test_passes_when_neutral_band_lagging_verdict(self, tmp_path):
        """neutral band is allowed with any verdict (already demoted)."""
        row = _clean_row(conviction={"band": "neutral", "verdict": "Lagging"})
        violations = _check(_artifact(tmp_path, [row]))
        c_viol = [v for v in violations if v.startswith("(c)")]
        assert not c_viol


# ---------------------------------------------------------------------------
# invariant (d): alpha sort broken — slot-1 negative while positives exist
# ---------------------------------------------------------------------------

class TestInvariantD:
    def test_passes_when_sorted_correctly(self, tmp_path):
        rows = [
            _clean_row("AAPL", alpha=1.2, lane="buy"),
            _clean_row("MSFT", alpha=0.8, lane="buy"),
            _clean_row("GOOG", alpha=0.3, lane="buy"),
        ]
        violations = _check(_artifact(tmp_path, rows))
        d_viol = [v for v in violations if v.startswith("(d)")]
        assert not d_viol

    def test_fails_when_slot1_negative_and_positives_exist(self, tmp_path):
        rows = [
            _clean_row("AAPL", alpha=-0.5, lane="buy"),   # slot-1 negative
            _clean_row("MSFT", alpha=0.8, lane="buy"),    # positive exists
        ]
        violations = _check(_artifact(tmp_path, rows))
        d_viol = [v for v in violations if v.startswith("(d)")]
        assert d_viol, f"Expected (d) violation for broken sort"

    def test_passes_when_all_negative_alpha(self, tmp_path):
        """All-negative alpha rows are valid (no positive to displace slot-1)."""
        rows = [
            _clean_row("AAPL", alpha=-0.3, lane="buy"),
            _clean_row("MSFT", alpha=-0.8, lane="buy"),
        ]
        violations = _check(_artifact(tmp_path, rows))
        d_viol = [v for v in violations if v.startswith("(d)")]
        assert not d_viol


# ---------------------------------------------------------------------------
# clean fixture: all 4 invariants pass
# ---------------------------------------------------------------------------

def test_clean_fixture_passes_all_invariants(tmp_path):
    rows = [
        _clean_row("AAPL", alpha=1.2, state="HOLD", urgency="caution",
                   conviction={"band": "high", "verdict": "strong edge"},
                   signal={"ticks": 1}),
        _clean_row("MSFT", alpha=0.5, state="HOLD", urgency="caution",
                   conviction={"band": "neutral", "verdict": "Lagging"},
                   signal={"ticks": 1}),
    ]
    violations = _check(_artifact(tmp_path, rows))
    assert violations == [], f"Clean fixture should have no violations, got: {violations}"


# ---------------------------------------------------------------------------
# arbiter rule 3: band demotion when verdict is lagging/no-clear-edge
# ---------------------------------------------------------------------------

class TestArbiterRule3:
    """Tests the demotion logic inline (mirrors the build_stock_library arbiter rule 3)."""

    def _apply_rule3(self, rows: list[dict]) -> list[dict]:
        """Apply arbiter rule 3 in isolation."""
        _BAND_DEMOTE = {"high": "constructive", "constructive": "neutral"}
        _LAGGING_VERDICTS = ("lagging", "no clear edge")
        for r in rows:
            c = r.get("conviction") or {}
            v = (c.get("verdict") or "").lower()
            b = (c.get("band") or "")
            if b in _BAND_DEMOTE and any(k in v for k in _LAGGING_VERDICTS):
                c["band"] = _BAND_DEMOTE[b]
                r["arbiter_note"] = f"band demoted {b}->{_BAND_DEMOTE[b]} (verdict={c.get('verdict')})"
        return rows

    def test_high_band_lagging_demotes_to_constructive(self):
        rows = [{"conviction": {"band": "high", "verdict": "Lagging"}}]
        result = self._apply_rule3(rows)
        assert result[0]["conviction"]["band"] == "constructive"
        assert "arbiter_note" in result[0]

    def test_constructive_band_no_clear_edge_demotes_to_neutral(self):
        rows = [{"conviction": {"band": "constructive", "verdict": "no clear edge"}}]
        result = self._apply_rule3(rows)
        assert result[0]["conviction"]["band"] == "neutral"

    def test_neutral_band_not_further_demoted(self):
        rows = [{"conviction": {"band": "neutral", "verdict": "Lagging"}}]
        result = self._apply_rule3(rows)
        # neutral not in _BAND_DEMOTE → no change
        assert result[0]["conviction"]["band"] == "neutral"
        assert "arbiter_note" not in result[0]

    def test_high_band_strong_verdict_not_demoted(self):
        rows = [{"conviction": {"band": "high", "verdict": "strong edge"}}]
        result = self._apply_rule3(rows)
        assert result[0]["conviction"]["band"] == "high"
        assert "arbiter_note" not in result[0]

    def test_two_step_demotion_high_then_constructive(self):
        """Running rule 3 twice: first high→constructive, second constructive→neutral."""
        rows = [{"conviction": {"band": "high", "verdict": "Lagging"}}]
        first_pass = self._apply_rule3(rows)
        assert first_pass[0]["conviction"]["band"] == "constructive"
        second_pass = self._apply_rule3(first_pass)
        assert second_pass[0]["conviction"]["band"] == "neutral"
