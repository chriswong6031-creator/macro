"""tests/test_altdata_brain_reconcile.py — de-escalation-only clamp matrix for _reconcile.

House law: LLMs may only de-escalate calibrated keys — never originate signals, scores,
or escalations.  This suite verifies that _reconcile enforces that constraint on every
axis (action, conviction, lean) across the full combinatorial clamp matrix.

Key invariant: the ACTION and CONVICTION ceilings are a function of DETERMINISTIC fields
only (rs_vs_spy_60d, channels, weighted_score, extended) — never of any LLM-proposed
field (lean, action, conviction).

Tests are PURE UNIT — no network, no LLM, no filesystem.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.altdata_brain import (
    _reconcile, _det_baseline, _ACTION_RANK, _CONV_RANK,
    _BULLISH_WITNESS_CHANNELS,
)

# A sample bullish channel witness guaranteed to be in _BULLISH_WITNESS_CHANNELS.
_SAMPLE_BULLISH = next(iter(sorted(_BULLISH_WITNESS_CHANNELS)))


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
    channels: list | None = None,
) -> dict:
    """Minimal thesis dict that _reconcile expects (cluster fields already merged).

    `channels` is a list of channel names present in the cluster (deterministic).
    When None, no channels are present (simulates a cluster with no bullish witnesses).
    """
    return {
        "lean": lean,
        "action": action,
        "conviction": conviction,
        "weighted_score": weighted_score,
        "extended": extended,
        "rs_vs_spy_60d": rs_vs_spy_60d,
        "channels": channels if channels is not None else [],
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

    def test_none_rs_with_bullish_channel_gives_accumulate(self):
        """rs=None but a bullish channel witness present → deterministic overweight ceiling."""
        t = _make_t(lean="overweight", weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[_SAMPLE_BULLISH])
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert lean == "overweight"
        assert act == "ACCUMULATE"
        assert conv == "medium"

    def test_none_rs_without_bullish_channel_gives_watch(self):
        """rs=None AND no bullish channel witness → no directional support → WATCH/low ceiling.

        This is the origination-hole fix: the old code (incorrectly) read t.get('lean') and
        allowed an LLM-proposed overweight to escalate the ceiling to ACCUMULATE when the
        price series was absent.  The new invariant: ceiling = WATCH, conviction = 'low'
        when there is no deterministic directional witness (rs OR bullish channel).
        """
        t = _make_t(lean="overweight", weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[])
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        # No directional witness → watch_only → returned lean = "underweight" (canonical)
        assert lean == "underweight"
        assert act == "WATCH"
        assert conv == "low"

    def test_none_rs_without_bullish_channel_underweight_llm_gives_watch(self):
        """rs=None, no bullish channel, LLM says underweight → ceiling still WATCH (not AVOID).

        The deterministic ceiling action is WATCH regardless of LLM lean when evidence is absent.
        """
        t = _make_t(lean="underweight", weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[])
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "WATCH"
        assert conv == "low"

    def test_underweight_lean_gives_avoid_low(self):
        """rs < 0 → deterministic underweight → AVOID ceiling (price trend is the witness)."""
        t = _make_t(lean="underweight", weighted_score=1.2, extended=False, rs_vs_spy_60d=-5.0)
        act, conv, lean = _det_baseline(t, min_weighted=0.9)
        assert act == "AVOID"
        assert conv == "low"
        assert lean == "underweight"

    def test_no_rs_no_channels_give_watch_regardless_of_llm_lean(self):
        """Deterministic baseline ignores t['lean'] entirely — WATCH ceiling for no-evidence."""
        for llm_lean in ("overweight", "underweight", "avoid"):
            t = _make_t(lean=llm_lean, weighted_score=1.2, extended=False,
                        rs_vs_spy_60d=None, channels=[])
            act, conv, lean = _det_baseline(t, min_weighted=0.9)
            assert act == "WATCH", f"lean={llm_lean}: expected WATCH, got {act}"
            assert conv == "low"


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
    """Verify the original extended/bearish-lean hard blocks still fire as defense-in-depth.

    The ceiling (_det_baseline) normally fires first and prevents ACCUMULATE reaching the
    hard blocks. Tests in this class that do NOT monkeypatch _det_baseline exercise the
    CEILING (and are labeled accordingly). Tests that DO monkeypatch _det_baseline bypass
    the ceiling to verify the hard blocks fire independently — these have real power over
    the defense-in-depth layer.
    """

    def test_extended_action_ceiling_fires_before_hardblock(self):
        """Extended name → the deterministic ceiling (not the hard block) clamps action to WATCH.

        The ceiling fires first: extended=True means _det_baseline returns det_action=WATCH
        directly. The hard block is also present for defense-in-depth but is unreachable here
        because the ceiling already demoted the action.  This test exercises the CEILING.
        """
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=True, rs_vs_spy_60d=40.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert "clamped" in out

    def test_negative_rs_ceiling_fires_before_hardblock(self):
        """Negative rs → the deterministic ceiling clamps action to AVOID.

        rs<0 → _det_baseline returns det_lean=underweight, det_action=AVOID. The
        LLM's ACCUMULATE is clamped to AVOID by the ceiling. This test exercises the CEILING
        (the hard block for bearish lean is also a defense-in-depth safety net but
        unreachable here since action is already AVOID after ceiling fires).
        """
        t = _make_t(lean="underweight", action="ACCUMULATE", conviction="low",
                    weighted_score=0.3, extended=False, rs_vs_spy_60d=-10.0)
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "AVOID", out
        assert "clamped" in out

    # -----------------------------------------------------------------------
    # Hard-block bypass tests — these have REAL POWER over the defense-in-depth
    # layer by monkeypatching _det_baseline to return an ACCUMULATE ceiling.
    # If the hard blocks were removed, these tests would fail.
    # -----------------------------------------------------------------------

    def test_hardblock_extended_fires_when_ceiling_bypassed(self):
        """Defense-in-depth: extended hard block demotes ACCUMULATE→WATCH even when the
        deterministic ceiling erroneously permits ACCUMULATE.

        Monkeypatch _det_baseline to return ('ACCUMULATE','medium','overweight') — simulating
        a scenario where the ceiling passes ACCUMULATE for an extended name (e.g. a future
        regression in _det_baseline).  The hard block must still fire and demote to WATCH.
        """
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.2, extended=True, rs_vs_spy_60d=40.0)
        with patch("engine.altdata_brain._det_baseline",
                   return_value=("ACCUMULATE", "medium", "overweight")):
            out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", (
            "extended hard block must demote ACCUMULATE→WATCH even when ceiling is bypassed; "
            f"got: {out}"
        )
        assert "clamped" in out

    def test_hardblock_bearish_lean_fires_when_ceiling_bypassed(self):
        """Defense-in-depth: bearish-lean hard block demotes ACCUMULATE→AVOID even when the
        deterministic ceiling erroneously permits ACCUMULATE.

        Monkeypatch _det_baseline to return ('ACCUMULATE','medium','overweight') on a thesis
        whose actual lean is 'underweight' after the clamp would run.  The hard block must
        catch that ACCUMULATE+bearish lean is always forbidden.
        """
        t = _make_t(lean="underweight", action="ACCUMULATE", conviction="medium",
                    weighted_score=1.5, extended=False, rs_vs_spy_60d=-5.0)
        with patch("engine.altdata_brain._det_baseline",
                   return_value=("ACCUMULATE", "medium", "overweight")):
            out = _reconcile(t, min_weighted=0.9)
        # After monkeypatching: ceiling lean = "overweight" (rank 2), LLM lean = "underweight"
        # (rank 1) → lean stays "underweight" (de-escalation respected). Hard block fires:
        # lean=underweight + action=ACCUMULATE → AVOID.
        assert out["action"] == "AVOID", (
            "bearish-lean hard block must demote ACCUMULATE→AVOID even when ceiling is bypassed; "
            f"got: {out}"
        )
        assert "clamped" in out


# ---------------------------------------------------------------------------
# rs=None clamp matrix (item 3: extended coverage for the origination-hole fix)
# Matrix: rs=None × {witness present, absent} × {LLM overweight/underweight} × {extended T/F}
# ---------------------------------------------------------------------------

class TestRsNoneClampMatrix:
    """Full combinatorial matrix verifying _reconcile with rs_vs_spy_60d=None.

    When rs is absent the ceiling depends entirely on whether a bullish channel witness
    is present in the cluster's channels list.
    """

    # ---- rs=None, bullish witness PRESENT, LLM overweight ----

    def test_rs_none_witness_present_llm_overweight_not_extended(self):
        """rs=None + witness + LLM overweight + not extended → ceiling ACCUMULATE/medium."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[_SAMPLE_BULLISH])
        out = _reconcile(t, min_weighted=0.9)
        # ceiling = ACCUMULATE; LLM conviction "high" > ceiling "medium" → clamped to medium
        assert out["action"] == "ACCUMULATE", out
        assert out["conviction"] == "medium", out
        assert out["lean"] == "overweight", out

    def test_rs_none_witness_present_llm_overweight_extended(self):
        """rs=None + witness + LLM overweight + extended → ceiling WATCH (entry gone)."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=True,
                    rs_vs_spy_60d=None, channels=[_SAMPLE_BULLISH])
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert out["conviction"] in ("medium", "low"), out
        assert "clamped" in out

    # ---- rs=None, bullish witness PRESENT, LLM underweight ----

    def test_rs_none_witness_present_llm_underweight_not_extended(self):
        """rs=None + witness + LLM underweight + not extended → LLM de-escalates lean to
        underweight; ceiling ACCUMULATE but action de-escalated by LLM."""
        t = _make_t(lean="underweight", action="WATCH", conviction="low",
                    weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[_SAMPLE_BULLISH])
        out = _reconcile(t, min_weighted=0.9)
        # ceiling lean = overweight; LLM lean = underweight (rank 1 < 2) → de-escalation kept
        assert out["lean"] == "underweight", out
        # ceiling action = ACCUMULATE; LLM action = WATCH (rank 1 < 2) → de-escalation kept
        assert out["action"] == "WATCH", out

    def test_rs_none_witness_present_llm_underweight_extended(self):
        """rs=None + witness + LLM underweight + extended → ceiling WATCH; LLM WATCH kept."""
        t = _make_t(lean="underweight", action="WATCH", conviction="low",
                    weighted_score=1.2, extended=True,
                    rs_vs_spy_60d=None, channels=[_SAMPLE_BULLISH])
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out

    # ---- rs=None, bullish witness ABSENT, LLM overweight ----

    def test_rs_none_no_witness_llm_overweight_not_extended(self):
        """rs=None + no witness + LLM overweight + not extended → ceiling WATCH/low (no evidence)."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[])
        out = _reconcile(t, min_weighted=0.9)
        # No directional witness → ceiling = WATCH; LLM ACCUMULATE (rank 2 > WATCH rank 1) clamped
        assert out["action"] == "WATCH", out
        assert out["conviction"] == "low", out
        assert "clamped" in out

    def test_rs_none_no_witness_llm_overweight_extended(self):
        """rs=None + no witness + LLM overweight + extended → ceiling still WATCH/low."""
        t = _make_t(lean="overweight", action="ACCUMULATE", conviction="high",
                    weighted_score=1.2, extended=True,
                    rs_vs_spy_60d=None, channels=[])
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "WATCH", out
        assert out["conviction"] == "low", out
        assert "clamped" in out

    # ---- rs=None, bullish witness ABSENT, LLM underweight ----

    def test_rs_none_no_witness_llm_underweight_not_extended(self):
        """rs=None + no witness + LLM underweight + not extended → ceiling WATCH; LLM AVOID de-escalates."""
        t = _make_t(lean="underweight", action="AVOID", conviction="low",
                    weighted_score=1.2, extended=False,
                    rs_vs_spy_60d=None, channels=[])
        out = _reconcile(t, min_weighted=0.9)
        # Ceiling WATCH (rank 1); LLM AVOID (rank 0) → de-escalation respected
        assert out["action"] == "AVOID", out
        assert out["lean"] == "underweight", out  # de-escalation respected; lean not clamped up

    def test_rs_none_no_witness_llm_underweight_extended(self):
        """rs=None + no witness + LLM underweight + extended → ceiling WATCH; LLM AVOID kept."""
        t = _make_t(lean="underweight", action="AVOID", conviction="low",
                    weighted_score=1.2, extended=True,
                    rs_vs_spy_60d=None, channels=[])
        out = _reconcile(t, min_weighted=0.9)
        assert out["action"] == "AVOID", out

    def test_rs_none_no_witness_llm_accumulate_always_clamped_to_watch(self):
        """ACCUMULATE is always blocked when there is no deterministic directional witness,
        regardless of LLM lean, weighted_score, or extended flag."""
        for llm_lean in ("overweight", "underweight", "avoid"):
            t = _make_t(lean=llm_lean, action="ACCUMULATE", conviction="high",
                        weighted_score=2.0, extended=False,
                        rs_vs_spy_60d=None, channels=[])
            out = _reconcile(t, min_weighted=0.9)
            assert out["action"] in ("WATCH", "AVOID"), (
                f"lean={llm_lean}: ACCUMULATE must not pass through with no evidence; got {out['action']}"
            )


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
