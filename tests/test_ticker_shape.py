"""Tests for engine/ticker_shape.py — the two-level ticker gate.

The seven strings pinned below are the ACTUAL garbage keys that reached
data/hub/signal_snapshots.jsonl for 26 snapshot days (2026-06-21 → 07-21) via the
special_situations channel. Both levels must refuse every one of them; the permissive
level must still accept legitimate non-US forms, or the boundary tripwire would cry
wolf the first time a real foreign symbol crossed it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from engine.ticker_shape import plausible_symbol, valid_us_ticker  # noqa: E402

# The historical corruption, verbatim.
GARBAGE = ["CONSECUTIVE", "()", "N/A", "ASX:PEX", "IT:ETH", "KOEI-R-A", "TBD"]


# --------------------------------------------------------------------------- #
# valid_us_ticker — the STRICT emitter gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sym", ["AAPL", "V", "BRK.B", "BRK-B", "SCHWPD"])
def test_valid_us_ticker_accepts_us_shapes(sym):
    assert valid_us_ticker(sym) == sym


def test_valid_us_ticker_returns_the_stripped_original_not_the_uppercased_form():
    """Case is normalized for the CHECK only. Emitters key on the returned string, so
    upper-casing it here would silently rewrite every existing key in the artifact."""
    assert valid_us_ticker("aapl") == "aapl"
    assert valid_us_ticker("  AAPL  ") == "AAPL"


@pytest.mark.parametrize("bad", GARBAGE + ["", None, "600519.SS", "nan"])
def test_valid_us_ticker_rejects(bad):
    # 600519.SS is a REAL symbol — it is rejected because this gate is US-only, not
    # because the string is junk. The permissive level below is where it belongs.
    assert valid_us_ticker(bad) is None


# --------------------------------------------------------------------------- #
# plausible_symbol — the PERMISSIVE boundary tripwire
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sym", ["AAPL", "BRK.B", "BRK-B", "0700.HK", "600519.SS",
                                 "BTC-USD", "ANANTRAJ", "SCHWPD", "APOLLOHOSP"])
def test_plausible_symbol_accepts_any_exchange_form(sym):
    assert plausible_symbol(sym) is True


@pytest.mark.parametrize("bad", GARBAGE + ["", "AB CD", "X" * 11])
def test_plausible_symbol_rejects(bad):
    assert plausible_symbol(bad) is False


def test_plausible_symbol_is_wider_than_the_us_gate():
    """The two levels differ on purpose — a foreign symbol at a boundary is not an alarm,
    but it is also not something an emitter may publish as a US ticker key."""
    assert valid_us_ticker("0700.HK") is None and plausible_symbol("0700.HK") is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
