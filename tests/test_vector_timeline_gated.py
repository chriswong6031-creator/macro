"""Tests for scripts.build_vector.vector_timeline() gating behavior.

Tests that gated spans are correctly marked and gracefully handle both
post-W0 (override_active column) and pre-W0 (deterministic midterm_blackout)
computation modes."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_vector import vector_timeline  # noqa: E402


def _mock_sig(start_date="2025-12-28", end_date="2026-01-05"):
    """Create a minimal signal DataFrame for testing."""
    idx = pd.date_range(start_date, end_date)
    return pd.DataFrame({
        "close": [50000.0 + i * 100 for i in range(len(idx))],
        "cycle_position": [0.5] * len(idx),
        "cycle_phase": ["markup"] * len(idx),
        "cphase_phase": [""] * len(idx),
        "momentum_state": ["bear"] * len(idx),
        "valuation_state": ["fair"] * len(idx),
        "market_extreme": ["normal"] * len(idx),
        "composite_state": ["NEUTRAL"] * len(idx),
        "risk_index": [60.0] * len(idx),
        "alloc_optimal": [0.0] * len(idx),
    }, index=idx)


def _mock_ladder(sig_index):
    """Create a minimal ladder DataFrame aligned with signal index."""
    return pd.DataFrame({
        "ladder_state": ["DECLINE"] * len(sig_index),
        "regime": ["bear"] * len(sig_index),
    }, index=sig_index)


def test_gated_with_override_active_column():
    """Test A: override_active column present (post-W0).

    The gated array should follow override_active exactly, ignoring gate_cfg.
    """
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    # Add override_active column: True only on 2025-12-30
    sig["override_active"] = False
    sig.loc["2025-12-30", "override_active"] = True

    tape = vector_timeline(sig, ladder, gate_cfg={"enabled": True, "buy_lead_days": 0})

    assert "gated" in tape
    assert len(tape["gated"]) == len(sig)

    # 2025-12-30 should be gated (1), all others ungated (0)
    for i, date_str in enumerate(tape["dates"]):
        expected = 1 if date_str == "2025-12-30" else 0
        assert tape["gated"][i] == expected, f"Day {date_str} should be {expected}"


def test_gated_with_deterministic_gate_cfg():
    """Test B: no override_active column; deterministic midterm gate computation.

    With gate enabled and window 2026-01-01 onward (midterm year),
    dates in 2026 should be gated (1), 2025 dates ungated (0).
    """
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    gate_cfg = {"enabled": True, "buy_lead_days": 0}
    tape = vector_timeline(sig, ladder, gate_cfg=gate_cfg)

    assert "gated" in tape
    assert len(tape["gated"]) == len(sig)

    # 2026-01-01 onward should be gated (midterm year)
    for i, date_str in enumerate(tape["dates"]):
        year_part = date_str[:4]
        expected = 1 if year_part == "2026" else 0
        assert tape["gated"][i] == expected, f"Day {date_str} (year {year_part}) should be {expected}"


def test_gate_disabled():
    """Test B continued: gate_cfg with enabled=False should yield all zeros."""
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    gate_cfg = {"enabled": False}
    tape = vector_timeline(sig, ladder, gate_cfg=gate_cfg)

    assert "gated" in tape
    assert all(v == 0 for v in tape["gated"]), "All should be ungated when gate disabled"


def test_override_active_takes_precedence():
    """Test C: override_active column present → gate_cfg is ignored."""
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    # Add override_active: only 2025-12-30 is True
    sig["override_active"] = False
    sig.loc["2025-12-30", "override_active"] = True

    # Even with gate enabled (which would gate all 2026 dates),
    # override_active should take precedence
    gate_cfg = {"enabled": True, "buy_lead_days": 0}
    tape = vector_timeline(sig, ladder, gate_cfg=gate_cfg)

    # Only 2025-12-30 should be gated
    for i, date_str in enumerate(tape["dates"]):
        expected = 1 if date_str == "2025-12-30" else 0
        assert tape["gated"][i] == expected, f"Day {date_str} should respect override_active only"


def test_gated_array_length_matches():
    """Test that gated array length always matches dates and other columns."""
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    tape = vector_timeline(sig, ladder)

    dates_len = len(tape["dates"])
    assert len(tape["gated"]) == dates_len
    assert len(tape["price"]) == dates_len
    assert len(tape["phase"]) == dates_len
    assert len(tape["alloc"]) == dates_len


def test_missing_gated_column_no_crash():
    """Test backward compatibility: old ladder backtest without gated should not crash."""
    sig = _mock_sig()
    ladder = _mock_ladder(sig.index)

    # Call with gate_cfg=None (default); should compute deterministically
    tape = vector_timeline(sig, ladder, gate_cfg=None)

    # Should still produce a gated array (computed via midterm_blackout)
    assert "gated" in tape
    assert len(tape["gated"]) == len(sig)
