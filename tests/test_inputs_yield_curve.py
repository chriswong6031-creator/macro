"""Regression guard for the canonical full Treasury curve feature projection."""
from __future__ import annotations

import pandas as pd

from engine import inputs


def test_existing_ccw_us20y_alias_reaches_the_canonical_feature_frame(monkeypatch):
    index = pd.bdate_range("2026-01-02", periods=5)
    configured_tickers = {
        ticker
        for group in inputs.config.load()["yahoo"]["tickers"].values()
        for ticker in group
    }
    closes = pd.DataFrame(
        {ticker: [100.0] * len(index) for ticker in configured_tickers},
        index=index,
    )
    us20y = pd.Series([4.20, 4.21, 4.22, 4.23, 4.24], index=index)

    monkeypatch.setattr(inputs, "yahoo_closes", lambda: closes)
    monkeypatch.setattr(inputs, "_fred", lambda _aliases: {"us20y": us20y})
    monkeypatch.setattr(inputs.store, "read", lambda *_args, **_kwargs: None)

    frame = inputs.build_features()

    assert "us20y" in frame.columns
    pd.testing.assert_series_equal(frame["us20y"], us20y, check_names=False)
