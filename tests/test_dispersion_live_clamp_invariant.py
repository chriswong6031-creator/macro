"""RUL-F3.7 display-only mechanization: the dispersion→risk_sizing path must
receive regime_gross == 1.0 (the _LIVE_CLAMP), and shadow_gross_mult must never
leak into the live field.

Ratified in research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md
(RUL-F3.7). Ported from the superseded PR #1705 branch (its DISP-GATE-1 harness
was superseded by the canonical #1696 implementation; these boundary-invariant
tests are implementation-independent and guard the single constant the
display-only guarantee currently rests on).
"""

import numpy as np
import pandas as pd
import pytest

class TestRulF37Invariant:
    """RUL-F3.7: dispersion→risk_sizing path must receive regime_gross == 1.0.

    Asserts:
    1. engine.dispersion.assess() returns gross_mult == 1.0 (the _LIVE_CLAMP)
    2. shadow_gross_mult != 1.0 for lean_in/lean_out (confirms the shadow exists)
    3. shadow_gross_mult does NOT appear in the 'gross_mult' key (no leak)
    4. engine.risk_sizing.assess() with regime_gross from dispersion is 1.0
    """

    def _build_returns_panel(self, seed: int = 5) -> pd.DataFrame:
        """Build a synthetic daily-return panel adequate for dispersion.assess()."""
        rng = np.random.default_rng(seed)
        n_dates = 300
        n_tickers = 30
        dates = pd.bdate_range("2021-01-01", periods=n_dates)
        log_rets = rng.normal(0, 0.015, size=(n_dates, n_tickers))
        prices = 100 * np.exp(np.cumsum(log_rets, axis=0))
        closes = pd.DataFrame(prices, index=dates, columns=[f"T{i}" for i in range(n_tickers)])
        return closes.pct_change(fill_method=None).dropna()

    def test_dispersion_assess_gross_mult_live_is_1(self):
        """engine.dispersion.assess() must return gross_mult == 1.0 (the live clamp)."""
        from engine import dispersion
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        assert result is not None, "dispersion.assess() returned None on a valid panel"
        assert result["gross_mult"] == 1.0, (
            f"INVARIANT VIOLATED: gross_mult should be 1.0 but got {result['gross_mult']}"
        )

    def test_shadow_gross_mult_is_not_1_for_extreme_states(self):
        """shadow_gross_mult must differ from 1.0 for lean_in/lean_out states.

        This confirms the shadow dial exists and has meaningful values,
        and that the live clamp is genuinely suppressing it.
        """
        from engine import dispersion
        from engine.dispersion import _SHADOW_GROSS
        # Shadow grosses for lean_in and lean_out should NOT be 1.0
        assert _SHADOW_GROSS["lean_in"] != 1.0, "lean_in shadow gross should differ from 1.0"
        assert _SHADOW_GROSS["lean_out"] != 1.0, "lean_out shadow gross should differ from 1.0"

    def test_gross_mult_key_is_live_not_shadow(self):
        """The 'gross_mult' key in dispersion.assess() output must be the live clamp (1.0),
        never the shadow_gross_mult value."""
        from engine import dispersion
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        if result is None:
            pytest.skip("dispersion.assess() returned None on this synthetic panel")
        # The live gross_mult must be 1.0
        assert result["gross_mult"] == 1.0
        # The shadow may be different (and is stored separately)
        shadow = result["shadow_gross_mult"]
        state = result["state"]
        if state in ("lean_in", "lean_out"):
            # For non-neutral states, shadow should differ from 1.0
            # (unless coincidentally at neutral boundary)
            pass  # Not strictly testable without controlling the state
        # Key invariant: gross_mult != shadow_gross_mult when state is lean_in or lean_out
        if state == "lean_in":
            assert result["gross_mult"] != shadow, "lean_in: gross_mult should not equal shadow"
        elif state == "lean_out":
            assert result["gross_mult"] != shadow, "lean_out: gross_mult should not equal shadow"

    def test_risk_sizing_receives_correct_regime_gross(self):
        """risk_sizing.assess() called with gross_mult from dispersion must receive 1.0.

        This simulates the actual call chain: dispersion.assess() → gross_mult →
        risk_sizing.assess(regime_gross=...). The regime_gross in risk_sizing output
        must be 1.0.
        """
        from engine import dispersion, risk_sizing
        returns = self._build_returns_panel()
        disp_result = dispersion.assess(returns)
        if disp_result is None:
            pytest.skip("dispersion.assess() returned None")

        # Simulate the call chain: pass dispersion's gross_mult to risk_sizing
        regime_gross = disp_result["gross_mult"]
        assert regime_gross == 1.0, f"Expected 1.0 from dispersion, got {regime_gross}"

        # Build a synthetic close series for risk_sizing
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.default_rng(42).normal(0, 0.015, 300))),
            index=pd.bdate_range("2021-01-01", periods=300),
        )
        sizing_result = risk_sizing.assess(prices, regime_gross=regime_gross)
        if sizing_result is None:
            pytest.skip("risk_sizing.assess() returned None on synthetic prices")

        # The regime_gross passed in (and reflected in output) must be 1.0
        assert sizing_result["regime_gross"] == 1.0, (
            f"INVARIANT VIOLATED: risk_sizing received regime_gross="
            f"{sizing_result['regime_gross']} instead of 1.0"
        )

    def test_shadow_gross_mult_does_not_leak_to_live_field(self):
        """Specifically test that shadow_gross_mult values (1.20, 0.75) do not appear
        in the gross_mult (live) field under any state."""
        from engine import dispersion
        from engine.dispersion import _SHADOW_GROSS, _LIVE_CLAMP
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        if result is None:
            pytest.skip("dispersion.assess() returned None")

        # The live gross_mult must always be _LIVE_CLAMP = 1.0
        assert result["gross_mult"] == _LIVE_CLAMP, (
            f"INVARIANT VIOLATED: gross_mult={result['gross_mult']} != _LIVE_CLAMP={_LIVE_CLAMP}"
        )
        # The live gross_mult must not be any of the shadow values (unless _LIVE_CLAMP == shadow)
        for state, shadow_val in _SHADOW_GROSS.items():
            if shadow_val != _LIVE_CLAMP:
                assert result["gross_mult"] != shadow_val, (
                    f"Shadow value {shadow_val} for state {state!r} leaked into gross_mult"
                )


# ---------------------------------------------------------------------------
# Test 9: Harness run on synthetic data (absent-file-safe)
# ---------------------------------------------------------------------------
