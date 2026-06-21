"""Tests for engine.valuation — the forward-aware, non-veto valuation haircut."""
from __future__ import annotations
import pytest

from engine import valuation


def _rec(**val):
    return {"valuation": val}


def test_cheap_forward_pe_growth_leader_is_not_penalized() -> None:
    """The NVDA guard: a rich TRAILING multiple but a cheap FORWARD P/E must read
    'cheap' with ZERO haircut — never false-vetoed for being a growth leader."""
    v = valuation.read(_rec(forward_pe=16.6, price_to_sales={"v": 24, "cheap": 5},
                            trailing_pe={"v": 42, "cheap": 48}))
    assert v["band"] == "cheap"
    assert v["haircut_z"] == 0.0
    assert v["watch"] is False
    assert valuation.apply_haircut(0.8, v) == 0.8        # quality untouched


def test_extreme_forward_pe_gets_capped_haircut_not_veto() -> None:
    v = valuation.read(_rec(forward_pe=55.0))
    assert v["band"] == "extreme"
    assert v["haircut_z"] == pytest.approx(-0.40)
    assert v["watch"] is True
    # never a veto: a strong-quality name is capped, not zeroed/negated
    assert valuation.apply_haircut(1.2, v) == pytest.approx(0.3)   # capped to watch ceiling
    assert valuation.apply_haircut(0.1, v) == pytest.approx(0.1 - 0.40)


def test_haircut_is_subtract_only() -> None:
    """A cheap name never gets a BONUS — valuation can only ever lower quality."""
    v = valuation.read(_rec(forward_pe=12.0))
    assert v["haircut_z"] == 0.0
    assert valuation.apply_haircut(0.5, v) == 0.5


def test_trailing_only_is_light_touch() -> None:
    """No forward P/E: only the genuinely extreme tail trips the watch flag."""
    fair = valuation.read(_rec(earnings_yield={"cheap": 45}, trailing_pe={"cheap": 40}))
    assert fair["band"] == "fair" and fair["haircut_z"] == 0.0 and not fair["watch"]
    rich = valuation.read(_rec(earnings_yield={"cheap": 6}, trailing_pe={"cheap": 8},
                               price_to_sales={"cheap": 5}))
    assert rich["band"] == "extreme" and rich["watch"] is True


def test_no_valuation_data_returns_none() -> None:
    assert valuation.read(_rec()) is None
    assert valuation.read({}) is None
    assert valuation.apply_haircut(0.5, None) == 0.5
