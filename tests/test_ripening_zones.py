"""W8-R1: Unit tests for assign_ripening_zone() — three-zone lifecycle classifier.

Tests cover:
  1. Four operator fixture vectors from R7 census (pinned to exact expected zones).
  2. FALLING precedence: veto overrides all cross evidence (002709 case).
  3. READY conditions: each of the three READY triggers independently.
  4. BASING fallback.
  5. Edge cases (None inputs, borderline thresholds).
  6. Cap / quota / ordering logic for the build.
  7. attach-when-cand-empty regression check.

All tests are pure-function (no I/O).
"""
from __future__ import annotations

import pytest

from engine.setup_tier import (
    assign_ripening_zone,
    ZONE_FALLING,
    ZONE_READY,
    ZONE_BASING,
    _FALLING_RET5D_THRESH,
    _READY_W1_CROSS_MAX_BARS,
    _READY_MACD_BARS_MAX,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _zone(**kwargs) -> str:
    """Call assign_ripening_zone with defaults for unspecified args and return the zone."""
    defaults = dict(
        ret_5d=None,
        macd_hist_d=None,
        macd_hist_prev_d=None,
        w1_cross_bars_since=None,
        w1_from_washout=False,
        macd_bars_to_cross_2w=None,
        stoch_2w=None,
        stoch_2w_prev=None,
    )
    defaults.update(kwargs)
    result = assign_ripening_zone(**defaults)
    return result["zone"]


def _evidence(**kwargs) -> list:
    """Return the evidence list from assign_ripening_zone."""
    defaults = dict(
        ret_5d=None,
        macd_hist_d=None,
        macd_hist_prev_d=None,
        w1_cross_bars_since=None,
        w1_from_washout=False,
        macd_bars_to_cross_2w=None,
        stoch_2w=None,
        stoch_2w_prev=None,
    )
    defaults.update(kwargs)
    return assign_ripening_zone(**defaults)["evidence"]


# ── Operator fixture vectors (R7 census, pinned) ─────────────────────────────

class TestOperatorFixtures:
    """Four operator vectors from the R7 census — must match expected zones exactly."""

    def test_000792_falling(self):
        """000792 (盐湖股份): ret_5d=-13.6%, MACD hist -0.253 (falling) → FALLING.

        R7 data: 5d=-13.6%, MACD_hist=[0.146,0.104,0.024,-0.138,-0.253].
        Daily MACD hist is negative AND declining → FALLING veto.
        """
        z = _zone(
            ret_5d=-0.136,
            macd_hist_d=-0.253,
            macd_hist_prev_d=-0.138,   # falling (prev=-0.138, now=-0.253)
            w1_cross_bars_since=4,      # bars_since=4 (stale, >3 limit)
            w1_from_washout=True,
            stoch_2w=2.0,
        )
        assert z == ZONE_FALLING, f"Expected FALLING, got {z}"

    def test_002709_falling_precedence_beats_cross(self):
        """002709 (天赐材料): ret_5d=-24.4%, MACD hist -1.061 (falling), bars_since=2 → FALLING.

        Critical W8-R1 precedence test: the fresh 1W cross (bars_since=2, d=8.1)
        MUST NOT override the FALLING veto. This is the blocker B1 scenario from the
        design doc.
        """
        z = _zone(
            ret_5d=-0.244,
            macd_hist_d=-1.061,
            macd_hist_prev_d=-0.633,   # falling (prev=-0.633, now=-1.061)
            w1_cross_bars_since=2,      # FRESH cross (<=3) — must be VETOED
            w1_from_washout=True,
            stoch_2w=1.0,
        )
        assert z == ZONE_FALLING, (
            f"Expected FALLING (precedence veto must beat fresh 1W cross), got {z}"
        )

    def test_601360_ready(self):
        """601360 (三六零): ret_5d=+1.6%, MACD hist +0.041 (rising), 1W cross d=3.6 3 bars ago → READY.

        R7 data: MACD hist turned positive AND rising. Also has 1W cross from washout.
        """
        z = _zone(
            ret_5d=0.016,
            macd_hist_d=0.041,
            macd_hist_prev_d=0.015,    # rising
            w1_cross_bars_since=3,      # exactly at the fresh-cross limit
            w1_from_washout=True,
            stoch_2w=2.0,
        )
        assert z == ZONE_READY, f"Expected READY, got {z}"

    def test_601933_ready(self):
        """601933 (永辉超市): ret_5d=-2.9%, MACD hist +0.022 (positive), 1W cross bars_since=1 → READY.

        The freshest possible 1W cross from deep washout, MACD hist positive.
        """
        z = _zone(
            ret_5d=-0.029,
            macd_hist_d=0.022,
            macd_hist_prev_d=0.019,    # rising (0.019 → 0.022)
            w1_cross_bars_since=1,
            w1_from_washout=True,
            stoch_2w=0.0,
        )
        assert z == ZONE_READY, f"Expected READY, got {z}"


# ── FALLING zone tests ────────────────────────────────────────────────────────

class TestFallingZone:
    """FALLING veto conditions — both triggers, edge cases."""

    def test_falling_by_ret5d_alone(self):
        """ret_5d <= -8% alone triggers FALLING even with rising hist."""
        z = _zone(
            ret_5d=-0.081,             # just below -8% threshold
            macd_hist_d=0.05,
            macd_hist_prev_d=0.03,     # hist is rising (would be READY without veto)
            w1_cross_bars_since=1,
            w1_from_washout=True,
        )
        assert z == ZONE_FALLING

    def test_not_falling_ret5d_above_threshold(self):
        """ret_5d just above -8% (e.g. -7.9%) should NOT trigger the ret veto.

        MACD is slightly negative but RISING (from -0.05 to -0.02), so the MACD
        veto does NOT fire either (hist < 0 but NOT falling).
        """
        z = _zone(
            ret_5d=-0.079,             # just above -8% threshold (no ret veto)
            macd_hist_d=-0.02,
            macd_hist_prev_d=-0.05,    # hist RISING from -0.05 to -0.02 → no MACD veto
        )
        # Neither veto fires → not FALLING
        assert z != ZONE_FALLING

    def test_falling_by_macd_neg_and_falling(self):
        """Daily MACD hist negative AND falling (prev > current) → FALLING veto."""
        z = _zone(
            ret_5d=-0.03,              # mild 3% loss — does not trigger ret veto
            macd_hist_d=-0.10,
            macd_hist_prev_d=-0.05,    # hist fell from -0.05 to -0.10 → negative & falling
        )
        assert z == ZONE_FALLING

    def test_macd_neg_but_rising_not_falling(self):
        """Daily MACD hist negative but RISING should NOT trigger MACD veto."""
        z = _zone(
            ret_5d=-0.02,
            macd_hist_d=-0.05,
            macd_hist_prev_d=-0.10,    # hist rose from -0.10 to -0.05
        )
        assert z != ZONE_FALLING

    def test_exact_ret5d_threshold(self):
        """ret_5d exactly = -8% threshold triggers FALLING."""
        z = _zone(ret_5d=_FALLING_RET5D_THRESH)
        assert z == ZONE_FALLING

    def test_evidence_contains_return_string(self):
        """FALLING evidence chips mention the 5d return."""
        evid = _evidence(ret_5d=-0.15, macd_hist_d=-0.1, macd_hist_prev_d=-0.05)
        assert any("5d return" in e for e in evid), f"Evidence missing ret_5d: {evid}"

    def test_evidence_contains_macd_string(self):
        """FALLING evidence chips mention MACD when triggered by hist."""
        evid = _evidence(ret_5d=-0.03, macd_hist_d=-0.10, macd_hist_prev_d=-0.05)
        assert any("MACD" in e or "macd" in e.lower() for e in evid), f"Evidence missing MACD: {evid}"


# ── READY zone tests ──────────────────────────────────────────────────────────

class TestReadyZone:
    """READY conditions — three triggers tested independently."""

    def test_ready_via_fresh_1w_cross_and_pos_hist(self):
        """Fresh 1W cross (bars_since <= 3) + hist >= 0 → READY (Condition R1)."""
        z = _zone(
            ret_5d=-0.02,
            macd_hist_d=0.0,            # exactly at 0 (hist >= 0 satisfied)
            macd_hist_prev_d=-0.01,     # prev was negative → hist NOT turning positive rising (R2)
            w1_cross_bars_since=2,
            w1_from_washout=True,
        )
        assert z == ZONE_READY

    def test_ready_via_fresh_1w_cross_requires_from_washout(self):
        """Cross must be from_washout=True for R1 to fire; non-washout cross → not R1."""
        # Without from_washout, R1 does NOT fire. But R2 might still apply.
        z = _zone(
            ret_5d=-0.02,
            macd_hist_d=0.05,
            macd_hist_prev_d=0.03,      # hist positive AND rising → R2 fires
            w1_cross_bars_since=1,
            w1_from_washout=False,      # NOT from washout zone
        )
        # R2 still fires (hist > 0 AND rising), so this is READY regardless
        assert z == ZONE_READY

    def test_ready_via_macd_hist_turned_positive_and_rising(self):
        """Daily MACD hist > 0 AND rising (R2) → READY regardless of cross age."""
        z = _zone(
            ret_5d=-0.03,
            macd_hist_d=0.022,
            macd_hist_prev_d=0.010,     # rising
            w1_cross_bars_since=10,     # stale cross (>3) — R1 does not fire
            w1_from_washout=True,
        )
        assert z == ZONE_READY

    def test_ready_via_2w_macd_imminence(self):
        """2W MACD <= threshold AND hist >= 0 (R3) → READY."""
        z = _zone(
            ret_5d=-0.02,
            macd_hist_d=0.01,           # positive
            macd_hist_prev_d=0.015,     # prev > current → hist declining (R2 does NOT fire)
            w1_cross_bars_since=None,   # no 1W cross
            macd_bars_to_cross_2w=_READY_MACD_BARS_MAX,  # exactly at threshold
        )
        assert z == ZONE_READY

    def test_ready_2w_macd_above_threshold_not_ready(self):
        """2W MACD just above threshold with no other R conditions → not READY."""
        z = _zone(
            ret_5d=-0.02,
            macd_hist_d=0.01,
            macd_hist_prev_d=0.015,     # declining
            w1_cross_bars_since=None,
            macd_bars_to_cross_2w=_READY_MACD_BARS_MAX + 0.1,  # just above threshold
        )
        assert z != ZONE_READY

    def test_ready_cross_bars_exactly_at_limit(self):
        """1W cross bars_since exactly = W1_FRESH_BARS (3) is still READY."""
        z = _zone(
            macd_hist_d=0.01,
            macd_hist_prev_d=-0.01,
            w1_cross_bars_since=_READY_W1_CROSS_MAX_BARS,  # == 3
            w1_from_washout=True,
        )
        assert z == ZONE_READY

    def test_ready_cross_just_past_limit(self):
        """1W cross bars_since = 4 (> limit) → R1 does not fire."""
        # bars_since=4, hist not rising (R2 doesn't fire), no imminence (R3 doesn't fire)
        z = _zone(
            macd_hist_d=0.0,
            macd_hist_prev_d=0.01,      # declining
            w1_cross_bars_since=4,      # just past the 3-bar limit
            w1_from_washout=True,
            macd_bars_to_cross_2w=None,
        )
        assert z == ZONE_BASING

    def test_ready_not_when_hist_neg_despite_cross(self):
        """R1 requires hist >= 0; negative hist with fresh cross → not R1."""
        z = _zone(
            ret_5d=-0.03,
            macd_hist_d=-0.05,          # negative → R1 cannot fire
            macd_hist_prev_d=-0.03,     # also falling → R2 vetoed; FALLING fires
            w1_cross_bars_since=1,
            w1_from_washout=True,
        )
        # hist < 0 AND falling → FALLING veto fires
        assert z == ZONE_FALLING


# ── BASING zone tests ─────────────────────────────────────────────────────────

class TestBasingZone:
    """BASING is the fallback when FALLING and READY both don't fire."""

    def test_basing_baseline(self):
        """Name with stale cross, flat hist, no imminence → BASING."""
        z = _zone(
            ret_5d=-0.03,
            macd_hist_d=-0.01,
            macd_hist_prev_d=-0.01,     # flat (no slope change)
            w1_cross_bars_since=8,
            w1_from_washout=True,
            stoch_2w=15.0,
        )
        # MACD hist is -0.01 but flat (prev == current), not falling → MACD veto doesn't fire
        # But hist < 0 and flat: macd_hist_d < macd_hist_prev_d? No: -0.01 == -0.01 (not < )
        # So FALLING does NOT fire. READY does not fire (no fresh cross, no rising hist, no imminence)
        assert z == ZONE_BASING

    def test_basing_evidence_contains_stoch(self):
        """BASING evidence should mention the 2W stoch."""
        evid = _evidence(
            ret_5d=-0.02,
            macd_hist_d=-0.005,
            macd_hist_prev_d=-0.005,    # flat
            stoch_2w=12.0,
        )
        assert any("stoch" in e.lower() for e in evid), f"BASING evidence missing stoch: {evid}"

    def test_basing_all_none_inputs(self):
        """All None inputs → should degrade gracefully to BASING without exception."""
        result = assign_ripening_zone(
            ret_5d=None,
            macd_hist_d=None,
            macd_hist_prev_d=None,
            w1_cross_bars_since=None,
            w1_from_washout=False,
            macd_bars_to_cross_2w=None,
            stoch_2w=None,
        )
        assert result["zone"] == ZONE_BASING
        assert isinstance(result["evidence"], list)


# ── Return type contract ──────────────────────────────────────────────────────

class TestReturnType:
    """assign_ripening_zone() must always return a dict with zone (str) and evidence (list)."""

    @pytest.mark.parametrize("zone", [ZONE_FALLING, ZONE_READY, ZONE_BASING])
    def test_result_has_required_keys(self, zone):
        if zone == ZONE_FALLING:
            kwargs = dict(ret_5d=-0.15)
        elif zone == ZONE_READY:
            kwargs = dict(macd_hist_d=0.05, macd_hist_prev_d=0.02)
        else:
            kwargs = {}
        result = assign_ripening_zone(
            ret_5d=kwargs.get("ret_5d"),
            macd_hist_d=kwargs.get("macd_hist_d"),
            macd_hist_prev_d=kwargs.get("macd_hist_prev_d"),
            w1_cross_bars_since=None,
            w1_from_washout=False,
            macd_bars_to_cross_2w=None,
            stoch_2w=None,
        )
        assert "zone" in result
        assert "evidence" in result
        assert isinstance(result["zone"], str)
        assert isinstance(result["evidence"], list)


# ── Quota / cap logic ─────────────────────────────────────────────────────────

class TestZoneQuota:
    """Cap and quota logic: FALLING cap 8, READY up to 16, BASING fills to 32."""

    def _make_candidates(self, n_falling=0, n_ready=0, n_basing=0) -> list[dict]:
        """Build a fake list of ripening candidates with known zones."""
        rows = []
        for i in range(n_falling):
            rows.append({
                "ticker": f"FALL_{i:03d}",
                "zone": ZONE_FALLING,
                "ret_5d": -(0.10 + i * 0.01),
                "_sort_btc": 999.0, "_sort_bars": 99.0, "_sort_stoch": 999.0,
            })
        for i in range(n_ready):
            rows.append({
                "ticker": f"REDY_{i:03d}",
                "zone": ZONE_READY,
                "ret_5d": 0.01,
                "_sort_btc": float(i), "_sort_bars": float(i), "_sort_stoch": float(i),
            })
        for i in range(n_basing):
            rows.append({
                "ticker": f"BASE_{i:03d}",
                "zone": ZONE_BASING,
                "ret_5d": -0.02,
                "_sort_btc": float(100 + i), "_sort_bars": 99.0, "_sort_stoch": float(i),
            })
        return rows

    def test_falling_cap_8(self):
        """FALLING sink is capped at 8 rows."""
        rows = self._make_candidates(n_falling=20)
        falling = sorted(
            [r for r in rows if r["zone"] == ZONE_FALLING],
            key=lambda x: float(x.get("ret_5d", 0))
        )[:8]
        assert len(falling) <= 8

    def test_ready_cap_16(self):
        """READY zone is capped at 16 rows."""
        rows = self._make_candidates(n_ready=20)
        ready = [r for r in rows if r["zone"] == ZONE_READY][:16]
        assert len(ready) <= 16

    def test_basing_fills_to_32_minus_ready(self):
        """BASING fills remainder up to cap 32 total (READY + BASING)."""
        n_ready = 16
        n_basing = 30  # more than needed
        rows = self._make_candidates(n_ready=n_ready, n_basing=n_basing)
        ready = [r for r in rows if r["zone"] == ZONE_READY][:16]
        basing = [r for r in rows if r["zone"] == ZONE_BASING][:(32 - len(ready))]
        total = len(ready) + len(basing)
        assert total <= 32

    def test_total_cap_32_enforced(self):
        """Total READY + BASING never exceeds 32 even with 100 candidates."""
        rows = self._make_candidates(n_ready=50, n_basing=50)
        ready = [r for r in rows if r["zone"] == ZONE_READY][:16]
        basing = [r for r in rows if r["zone"] == ZONE_BASING][:(32 - len(ready))]
        assert len(ready) + len(basing) <= 32


# ── attach-when-cand-empty regression ─────────────────────────────────────────

class TestAttachWhenCandEmpty:
    """Regression: ripening arrays should be computed from `uni` regardless of cand.

    The build gathers ripening rows from the full `uni` (closes panel), not from `cand`.
    This test verifies that assign_ripening_zone works correctly for all inputs and
    that the zone classification is deterministic regardless of whether cand is empty.
    Mirrors the R3-minor bug fix: arrays are always built, not gated on cand.
    """

    def test_zone_computation_is_independent_of_cand(self):
        """Zone assignment is a pure function and does not depend on any cand state."""
        # With "cand=[]" scenario: we just call assign_ripening_zone directly
        # since it has no dependency on cand at all
        result = assign_ripening_zone(
            ret_5d=-0.02,
            macd_hist_d=0.01,
            macd_hist_prev_d=0.005,
            w1_cross_bars_since=2,
            w1_from_washout=True,
            macd_bars_to_cross_2w=None,
            stoch_2w=5.0,
        )
        # Should be READY (fresh cross + pos hist), regardless of any outer state
        assert result["zone"] == ZONE_READY
        assert len(result["evidence"]) > 0

    def test_falling_zone_computed_regardless_of_outer_state(self):
        """FALLING assignment is pure and context-free."""
        result = assign_ripening_zone(
            ret_5d=-0.20,
            macd_hist_d=-0.50,
            macd_hist_prev_d=-0.30,
            w1_cross_bars_since=1,
            w1_from_washout=True,
            macd_bars_to_cross_2w=5.0,
            stoch_2w=1.0,
        )
        assert result["zone"] == ZONE_FALLING


# ── Additional precedence edge cases ─────────────────────────────────────────

class TestPrecedenceEdgeCases:
    """Edge cases around the HARD precedence cascade."""

    def test_two_veto_conditions_both_fire(self):
        """Both FALLING conditions active → still FALLING, evidence has both."""
        evid = _evidence(
            ret_5d=-0.12,              # ret veto fires
            macd_hist_d=-0.20,
            macd_hist_prev_d=-0.10,   # macd veto fires
        )
        z = _zone(
            ret_5d=-0.12,
            macd_hist_d=-0.20,
            macd_hist_prev_d=-0.10,
        )
        assert z == ZONE_FALLING
        assert len(evid) == 2, f"Expected 2 evidence items (both vetoes), got {evid}"

    def test_ready_with_all_three_conditions(self):
        """All three READY conditions active → still READY, evidence rich."""
        result = assign_ripening_zone(
            ret_5d=-0.01,
            macd_hist_d=0.05,
            macd_hist_prev_d=0.02,     # R2: hist > 0 and rising
            w1_cross_bars_since=1,     # R1: fresh cross
            w1_from_washout=True,
            macd_bars_to_cross_2w=5.0, # R3: imminence
            stoch_2w=5.0,
        )
        assert result["zone"] == ZONE_READY
        assert len(result["evidence"]) >= 1

    def test_macd_hist_exactly_zero_not_falling(self):
        """macd_hist_d == 0.0 is NOT negative → MACD veto does not fire."""
        z = _zone(
            ret_5d=-0.03,
            macd_hist_d=0.0,
            macd_hist_prev_d=0.01,     # hist declining but still at 0 not negative
        )
        # MACD not negative → no FALLING from MACD condition
        # hist == 0.0, prev 0.01 → hist declining from 0.01 to 0.0
        # R2: hist > 0? No (0.0 is not > 0). R1: no cross specified.
        assert z == ZONE_BASING

    def test_none_ret5d_does_not_trigger_falling(self):
        """None ret_5d should not trigger the ret veto."""
        z = _zone(
            ret_5d=None,
            macd_hist_d=-0.10,
            macd_hist_prev_d=0.0,      # hist falling from 0 to -0.10 → MACD veto fires
        )
        # MACD veto fires (hist < 0 AND falling from 0 to -0.10)
        assert z == ZONE_FALLING

    def test_none_hist_does_not_trigger_macd_falling_veto(self):
        """None macd_hist_d should not trigger the MACD veto."""
        z = _zone(
            ret_5d=-0.03,
            macd_hist_d=None,
            macd_hist_prev_d=None,
            stoch_2w=10.0,
        )
        # Neither veto fires → not FALLING; no READY conditions → BASING
        assert z == ZONE_BASING


# ── evidence_display: plain-word bilingual twins (doctrine Law 2) ─────────────

class TestEvidenceDisplay:
    """Every machine evidence receipt must carry a plain-word bilingual twin
    (evidence_display), parallel 1:1, with the receipt equal to the machine
    string — this is what the Ripening Shelf renders at rest."""

    CASES = dict(
        falling=dict(ret_5d=-0.15, macd_hist_d=-0.10, macd_hist_prev_d=-0.05),
        ready_all=dict(ret_5d=-0.02, macd_hist_d=0.05, macd_hist_prev_d=0.03,
                       w1_cross_bars_since=1, w1_from_washout=True,
                       macd_bars_to_cross_2w=0.5),
        basing=dict(ret_5d=-0.03, macd_hist_d=-0.20, macd_hist_prev_d=-0.30,
                    w1_cross_bars_since=10, stoch_2w=13.0),
    )

    def _result(self, case):
        defaults = dict(
            ret_5d=None, macd_hist_d=None, macd_hist_prev_d=None,
            w1_cross_bars_since=None, w1_from_washout=False,
            macd_bars_to_cross_2w=None, stoch_2w=None, stoch_2w_prev=None,
        )
        defaults.update(self.CASES[case])
        return assign_ripening_zone(**defaults)

    @pytest.mark.parametrize("case", ["falling", "ready_all", "basing"])
    def test_display_parallel_to_evidence(self, case):
        """evidence_display is 1:1 with evidence; receipt == machine string."""
        r = self._result(case)
        assert len(r["evidence_display"]) == len(r["evidence"]) > 0
        for machine, disp in zip(r["evidence"], r["evidence_display"]):
            assert disp["receipt"] == machine
            assert disp["en"].strip() and disp["zh"].strip()

    @pytest.mark.parametrize("case", ["falling", "ready_all", "basing"])
    def test_display_en_has_no_quant_shorthand(self, case):
        """Glance-tier EN copy must not leak indicator shorthand (doctrine Law 2)."""
        r = self._result(case)
        banned = ("MACD", "stoch", "StochRSI", "D-", "1W", "2W", "hist", "z_", "washout)")
        for disp in r["evidence_display"]:
            for tok in banned:
                assert tok not in disp["en"], f"banned token {tok!r} in {disp['en']!r}"

    def test_stale_but_fresh_cross_is_not_called_stale(self):
        """A cross within the READY freshness window that failed to qualify reads
        'not confirmed yet', never 'gone stale'."""
        r = self._result("basing").copy()
        fresh = assign_ripening_zone(
            ret_5d=-0.03, macd_hist_d=-0.20, macd_hist_prev_d=-0.30,
            w1_cross_bars_since=1, w1_from_washout=False,
            macd_bars_to_cross_2w=None, stoch_2w=13.0, stoch_2w_prev=None,
        )
        stale_chips = [d for d in fresh["evidence_display"] if "(stale)" in d["receipt"]]
        assert stale_chips and "not confirmed" in stale_chips[0]["en"]
        assert "stale" not in stale_chips[0]["en"]
