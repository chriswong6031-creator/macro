"""Tests for Fix #43 — decision-surface consistency bugs.

(a) analyst_trends(): hot must be based on the revision-DELTA ('upgrading' direction),
    never the consensus LEVEL (bull>=0.6 AND rising). A ticker with a high level but
    stable/downgrading direction must NOT fire hot.

(b) whitehouse_brain._norm_tickers(): existence gate — a ticker not in the known
    universe is dropped and logged; a known ticker passes through; the gate opens
    (nothing dropped) when the universe file is absent.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


# ──────────────────────────────────────────────── #43a: analyst delta channel ────

def _make_reco_parquet(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal recommendation.parquet-shaped DataFrame."""
    return pd.DataFrame(rows)


def test_analyst_hot_uses_delta_upgrading_not_level(monkeypatch) -> None:
    """A ticker with bull_ratio >= 0.6 but direction=='stable' must NOT fire hot.
    A ticker with bull_ratio < 0.6 but direction=='upgrading' MUST fire hot."""
    # Ticker A: high level but net-buy count did NOT rise (stable)
    # Ticker B: lower level but net-buy count DID rise (upgrading)
    df = _make_reco_parquet([
        # A: strongBuy=5, buy=2, hold=2, sell=1 → bull=7/10=0.70; prev_buy=7 (no change)
        {"ticker": "A", "period": "2026-06-01",
         "strongBuy": 5, "buy": 2, "hold": 2, "sell": 1, "strongSell": 0, "prev_buy": 7.0},
        # B: strongBuy=1, buy=2, hold=5, sell=2 → bull=3/10=0.30; prev_buy=2 (rose)
        {"ticker": "B", "period": "2026-06-01",
         "strongBuy": 1, "buy": 2, "hold": 5, "sell": 2, "strongSell": 0, "prev_buy": 2.0},
    ])
    from engine import altdata
    monkeypatch.setattr(altdata, "_finnhub", lambda ds: df if ds == "recommendation" else None)
    rows = altdata.analyst_trends(top=99)
    by_ticker = {r["ticker"]: r for r in rows}
    # A: high level (0.70) but stable → must NOT be hot
    assert "A" in by_ticker
    assert by_ticker["A"]["hot"] is False, (
        "level=0.70 with no delta rise must NOT fire hot (level is discredited)"
    )
    # B: low level (0.30) but upgrading → MUST be hot
    assert "B" in by_ticker
    assert by_ticker["B"]["hot"] is True, (
        "direction=='upgrading' (delta>0) must fire hot regardless of level"
    )


def test_analyst_downgrading_does_not_fire_hot(monkeypatch) -> None:
    """A ticker where the net-buy count fell (direction=='downgrading') must not fire."""
    df = _make_reco_parquet([
        # C: bull=8/10=0.80 but net-buy FELL (prev_buy=9)
        {"ticker": "C", "period": "2026-06-01",
         "strongBuy": 6, "buy": 2, "hold": 1, "sell": 1, "strongSell": 0, "prev_buy": 9.0},
    ])
    from engine import altdata
    monkeypatch.setattr(altdata, "_finnhub", lambda ds: df if ds == "recommendation" else None)
    rows = altdata.analyst_trends(top=99)
    assert rows[0]["ticker"] == "C"
    assert rows[0]["hot"] is False


def test_analyst_empty_feed_returns_empty(monkeypatch) -> None:
    from engine import altdata
    monkeypatch.setattr(altdata, "_finnhub", lambda ds: None)
    assert altdata.analyst_trends() == []


# ──────────────────────────────────────────────── #43b: whitehouse ticker existence gate ────

def _make_universe_file(root: Path, tickers: list[str]) -> None:
    p = root / "site" / "factordata"
    p.mkdir(parents=True, exist_ok=True)
    verdicts = {t: {"eligible": True} for t in tickers}
    (p / "signal_gate.json").write_text(json.dumps({"as_of": "2026-07-01", "verdicts": verdicts}))


def test_existence_gate_drops_fabricated_ticker() -> None:
    """A hallucinated/delisted ticker not in the universe must be dropped."""
    from engine import whitehouse_brain as wb
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_universe_file(root, ["AAPL", "GM", "TM"])
        raw = [
            {"symbol": "AAPL", "direction": "benefit", "rationale": "real"},
            {"symbol": "HALLUCINATED_TICKER_XYZ", "direction": "benefit", "rationale": "fake"},
        ]
        result = wb._norm_tickers(raw, {}, root)
        syms = [r["symbol"] for r in result]
        assert "AAPL" in syms
        assert "HALLUCINATED_TICKER_XYZ" not in syms


def test_existence_gate_passes_known_ticker() -> None:
    """A ticker in the universe must pass through."""
    from engine import whitehouse_brain as wb
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_universe_file(root, ["GM", "TM", "F"])
        raw = [{"symbol": "GM", "direction": "benefit", "rationale": "domestic OEM"}]
        result = wb._norm_tickers(raw, {}, root)
        assert [r["symbol"] for r in result] == ["GM"]


def test_existence_gate_opens_when_universe_absent() -> None:
    """When the signal_gate.json doesn't exist, no tickers are dropped (graceful degrade).
    Uses ZFAKE (valid shape, ≤6 chars) to test a non-existent ticker doesn't get dropped."""
    from engine import whitehouse_brain as wb
    with tempfile.TemporaryDirectory() as tmpdir:
        # Do NOT create the universe file
        raw = [
            {"symbol": "GM", "direction": "benefit", "rationale": "real"},
            {"symbol": "ZFAKE", "direction": "hurt", "rationale": "fabricated"},  # valid shape, 5 chars
        ]
        result = wb._norm_tickers(raw, {}, Path(tmpdir))
        syms = [r["symbol"] for r in result]
        assert "GM" in syms
        assert "ZFAKE" in syms  # gate open (no universe file) → nothing dropped


def test_existence_gate_logs_dropped_ticker() -> None:
    """A dropped ticker must produce a log.info message (checked via log propagation)."""
    import io
    from engine import whitehouse_brain as wb
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_universe_file(root, ["AAPL"])
        raw = [{"symbol": "NOTRL", "direction": "benefit", "rationale": "ghost"}]
        # Capture log output via a stream handler
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("engine.whitehouse_brain")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            wb._norm_tickers(raw, {}, root)
            out = stream.getvalue()
            assert "NOTRL" in out, (
                f"dropped ticker must be logged at INFO level, got: {out!r}"
            )
        finally:
            logger.removeHandler(handler)


def test_existence_gate_shape_check_still_applies() -> None:
    """Shape check (len>6, non-alnum) still blocks malformed symbols before the gate."""
    from engine import whitehouse_brain as wb
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _make_universe_file(root, ["TOOLONG_SYM", "bad sym!"])  # even if they were in universe
        raw = [
            {"symbol": "TOOLONG_SYM", "direction": "benefit", "rationale": "x"},
            {"symbol": "bad sym!", "direction": "benefit", "rationale": "y"},
        ]
        result = wb._norm_tickers(raw, {}, root)
        assert result == []  # blocked at shape check, never reaches existence gate
