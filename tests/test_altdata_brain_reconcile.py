"""tests/test_altdata_brain_reconcile.py — de-escalation-only clamp matrix for _reconcile.

House law: LLMs may only de-escalate calibrated keys — never originate signals, scores,
or escalations.  This suite verifies that _reconcile enforces that constraint on every
axis (action, conviction, lean) across the full combinatorial clamp matrix.

Tests are PURE UNIT — no network, no LLM, no filesystem.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.altdata_brain import _reconcile, _det_baseline, _ACTION_RANK, _CONV_RANK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_t(
    lean: str = "overweight",
    action: str = "ACCUMULATE",
    conviction: str = "high",
    weighted_score: float = 1.2,
    extended: bool = False,
    rs_vs_spy_60d: float | None = 5.0,
) -> dict:
    """Minimal thesis dict that _reconcile expects (cluster fields already merged)."""
    return {
        "lean": lean,
        "action": action,
        "conviction": conviction,
        "weighted_score": weighted_score,
        "extended": extended,
        "rs_vs_spy_60d": rs_vs_spy_60d,
    }


# ---------------------------------------------------------------------------
# _det_baseline unit tests
# ---------------------------------------------------------------------------

class TestDetBaseline:
    """Verify the deterministic ceiling logic in isolation."""

    def test_strong_overweight_gives_accumulate_medium(self):
        t = _make_t(lean="overweight", weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "ACCUMULATE"
        assert conv == "medium"
        assert lean == "overweight"

    def test_overweight_but_weak_score_gives_watch(self):
        t = _make_t(lean="overweight", weighted_score=0.5, extended=False, rs_vs_spy_60d=5.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "WATCH"
        assert conv == "low"
        assert lean == "overweight"

    def test_overweight_but_extended_gives_watch(self):
        t = _make_t(lean="overweight", weighted_score=1.2, extended=True, rs_vs_spy_60d=5.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "WATCH"
        assert conv == "medium"  # conviction ceiling not affected by extended alone
        assert lean == "overweight"

    def test_overweight_but_negative_rs_demotes_lean(self):
        t = _make_t(lean="overweight", weighted_score=1.2, extended=False, rs_vs_spy_60d=-10.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert lean == "underweight"
        assert act == "AVOID"   # bearish lean → AVOID ceiling
        assert conv == "low"

    def test_overweight_none_rs_keeps_overweight(self):
        """None rs_vs_spy_60d (no price series) does not demote lean."""
        t = _make_t(lean="overweight", weighted_score=1.2, extended=False, rs_vs_spy_60d=None)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert lean == "overweight"
        assert act == "ACCUMULATE"

    def test_underweight_lean_gives_avoid_low(self):
        t = _make_t(lean="underweight", weighted_score=1.2, extended=False, rs_vs_spy_60d=-5.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "AVOID"
        assert conv == "low"
        assert lean == "underweight"

    def test_avoid_lean_gives_avoid_low(self):
        t = _make_t(lean="avoid", weighted_score=1.2, extended=False, rs_vs_spy_60d=None)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "AVOID"
        assert conv == "low"
        assert lean == "avoid"


# ---------------------------------------------------------------------------
# _reconcile: LLM escalation is clamped to deterministic ceiling
# ---------------------------------------------------------------------------

class TestReconcileEscalationClamped:
    """LLM tries to ESCALATE above the deterministic baseline — must be clamped down."""

    def test_llm_high_conviction_clamped_to_medium(self):
        """Overweight + strong score → conviction ceiling = medium; LLM says high → clamped."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["conviction"] == "medium", out
        assert "clamped" in out
        assert "conviction" in out["clamped"]

    def test_llm_high_conviction_with_weak_score_clamped_to_low(self):
        """Overweight + weak score → conviction ceiling = low; LLM says high → clamped to low."""
        t = _make_t(lean="overweight", action="WATCH", conviction="high",
                    weighted_score=0.5, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["conviction"] == "low", out
        assert "clamped" in out

    def test_llm_medium_conviction_with_weak_score_clamped_to_low(self):
        """Medium conviction with weak score → clamped to low."""
        t = _make_t(lean="overweight", action="WATCH", conviction="medium",
                    weighted_score=0.5, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["conviction"] == "low", out

    def test_llm_accumulate_clamped_to_watch_when_score_weak(self):
        """Overweight + weak weighted_score → action ceiling = WATCH; LLM says ACCUMULATE → clamped."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="low",
                    weighted_score=0.5, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert "clamped" in out
        assert "action" in out["clamped"]

    def test_llm_accumulate_clamped_to_avoid_on_underweight(self):
        """Underweight lean → action ceiling = AVOID; LLM says ACCUMULATE → clamped to AVOID."""
        t = _make_t(lean="underweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.5, extended=False, rs_vs_spy_60d=-5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "AVOID", out
        assert "clamped" in out

    def test_llm_overweight_clamped_to_underweight_on_negative_rs(self):
        """LLM lean=overweight but rs<0 → lean clamped to underweight."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=-20.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["lean"] == "underweight", out
        assert "clamped" in out
        assert "lean" in out["clamped"]

    def test_llm_accumulate_clamped_to_avoid_after_lean_demote(self):
        """LLM lean=overweight + action=ACCUMULATE but rs<0 → lean→underweight, action→AVOID."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=-20.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["lean"] in ("underweight", "avoid"), out
        assert out["action"] == "AVOID", out


# ---------------------------------------------------------------------------
# _reconcile: LLM de-escalation is RESPECTED
# ---------------------------------------------------------------------------

class TestReconcileDeEscalationRespected:
    """LLM de-escalates below the deterministic baseline — must be preserved."""

    def test_llm_watch_respected_when_ceiling_is_accumulate(self):
        """Deterministic ceiling = ACCUMULATE; LLM proposes WATCH → de-escalation kept."""
        t = _make_t(lean="overweight", action="WATCH", conviction="low",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert "clamped" not in out or "action" not in out.get("clamped", "")

    def test_llm_avoid_respected_when_ceiling_is_accumulate(self):
        """Deterministic ceiling = ACCUMULATE; LLM proposes AVOID → de-escalation kept."""
        t = _make_t(lean="avoid", action="AVOID", conviction="low",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        # lean="avoid" → ceiling AVOID; LLM says AVOID → OK
        assert out["action"] == "AVOID", out

    def test_llm_low_conviction_respected_when_ceiling_is_medium(self):
        """Ceiling conviction = medium; LLM proposes low → de-escalation respected."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="low",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["conviction"] == "low", out

    def test_no_clamp_at_ceiling(self):
        """LLM output exactly matches deterministic ceiling → no clamping occurs."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "ACCUMULATE", out
        assert out["conviction"] == "medium", out
        assert out["lean"] == "overweight", out
        # No clamping → 'clamped' key absent
        assert "clamped" not in out, f"unexpected clamping: {out.get('clamped')}"


# ---------------------------------------------------------------------------
# _reconcile: Original hard blocks still fire (regression)
# ---------------------------------------------------------------------------

class TestReconcileHardBlocks:
    """Verify the original extended/bearish-lean hard blocks still fire."""

    def test_extended_accumulate_clamped_to_watch(self):
        """Extended name + ACCUMULATE → WATCH (hard block, unchanged from original)."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=True, rs_vs_spy_60d=40.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert "clamped" in out

    def test_bearish_lean_accumulate_hard_blocked(self):
        """Underweight lean + ACCUMULATE → AVOID via hard block."""
        # Build a thesis where the deterministic action ceiling would normally fire first,
        # but set rs_vs_spy_60d > 0 so lean doesn't change, and the original hard block
        # for bearish lean still fires.
        t = _make_t(lean="underweight", action="ACCUMULATE", conviction="low",
                    weighted_score=0.3, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        # underweight lean → ceiling AVOID → action clamped to AVOID (baseline); hard block
        # also confirms it cannot be ACCUMULATE
        assert out["action"] == "AVOID", out

    def test_avoid_lean_accumulate_hard_blocked(self):
        """Avoid lean + ACCUMULATE → AVOID."""
        t = _make_t(lean="avoid", action="ACCUMULATE", conviction="low",
                    weighted_score=1.5, extended=False, rs_vs_spy_60d=None)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "AVOID", out

    def test_extended_action_clamped_and_noted(self):
        """Extended name → deterministic ceiling is WATCH (not ACCUMULATE); action clamped,
        clamped note is present.  The ceiling fires before the hard block on extended names."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=True, rs_vs_spy_60d=40.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert "clamped" in out, out


# ---------------------------------------------------------------------------
# _reconcile: det_baseline audit field
# ---------------------------------------------------------------------------

class TestReconcileDetBaselineAuditField:
    """When any clamping occurs, det_baseline is present for audit trail."""

    def test_det_baseline_present_when_clamped(self):
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=0.5, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert "det_baseline" in out, out
        b = out["det_baseline"]
        assert "action" in b and "conviction" in b and "lean" in b

    def test_det_baseline_absent_when_no_clamp(self):
        """At-ceiling output → det_baseline is NOT added (no noise on clean records)."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        assert "det_baseline" not in out, out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestReconcileEdgeCases:
    """Unknown / missing values should not crash _reconcile."""

    def test_none_weighted_score_treated_as_zero(self):
        """None weighted_score → treated as 0 → action ceiling WATCH for overweight."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=None, extended=False, rs_vs_spy_60d=5.0)
        t["weighted_score"] = None
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] in ("WATCH", "AVOID"), out

    def test_invalid_action_string_not_clamped_up(self):
        """Garbage action string (unknown rank treated as 0 / floor).  _reconcile does not
        normalise unknown strings itself — _build_thesis does that upstream.  Unknown action
        is treated as rank 0 (AVOID rank) so it is BELOW any ceiling — no upward clamping.
        The garbage string passes through unchanged (not a correctness risk: _build_thesis
        rejects unknown values before calling _reconcile in the real pipeline)."""
        t = _make_t(lean="overweight", action="YOLO", conviction="low",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        # Unknown action rank defaults to 0 (floor), so clamp never fires upward.
        # The string passes through: this is intentional since _build_thesis normalises upstream.
        assert out["action"] == "YOLO"
        assert "clamped" not in out or "action" not in out.get("clamped", "")

    def test_invalid_conviction_string_not_clamped_up(self):
        """Unknown conviction rank defaults to 0 (floor) so no upward clamp fires.
        _reconcile does not normalise unknown strings itself (see _build_thesis upstream)."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="extreme",
                    weighted_score=1.2, extended=False, rs_vs_spy_60d=5.0)
        out = _reconcile(t, min_weighted=0.9)
        # "extreme" → _CONV_RANK.get("extreme", 0) = 0; ceiling "medium" rank 1 > 0 is false,
        # so no conviction clamp fires.
        assert out["conviction"] == "extreme"
        assert "clamped" not in out or "conviction" not in out.get("clamped", "")
