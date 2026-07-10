"""Cap-source mechanics for the S&P 500 heatmap builder.

Covers the pieces that keep ``size_basis`` on real market caps across lanes:
the committed-reference staleness gate (weekly Polygon sweep), the
prev-payload recycle guard, and the poisoned-record plausibility screen.
No network: every path here must run offline.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts import build_sp500_heatmap as bh


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "_data", lambda *p: tmp_path.joinpath(*p))
    (tmp_path / "sp500_heatmap").mkdir()
    return tmp_path / "sp500_heatmap"


def _write_ref(data_dir, asof: str | None) -> None:
    df = pd.DataFrame({"ticker": ["AAPL"], "shares": [1.5e10]}).set_index("ticker")
    if asof is not None:
        df["asof"] = asof
    df.to_parquet(data_dir / "reference.parquet")


def test_cache_age_absent_and_unstamped(data_dir):
    assert bh._cap_cache_age_days() is None  # absent
    _write_ref(data_dir, asof=None)
    assert bh._cap_cache_age_days() is None  # pre-asof cache counts as stale


def test_cache_age_from_asof_stamp(data_dir):
    from datetime import datetime, timedelta, timezone
    stamp = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    _write_ref(data_dir, asof=stamp)
    assert bh._cap_cache_age_days() == 3.0


def test_refresh_skipped_while_fresh(data_dir, monkeypatch, caplog):
    from datetime import datetime, timezone
    _write_ref(data_dir, asof=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    # a key in the env must NOT trigger a sweep while the cache is fresh
    monkeypatch.setenv("POLYGON_API_KEY", "k")
    before = (data_dir / "reference.parquet").read_bytes()
    with caplog.at_level("INFO", logger="build_sp500_heatmap"):
        bh.refresh_caps(pd.DataFrame(index=["AAPL"]))
    assert "refresh skipped" in caplog.text
    assert (data_dir / "reference.parquet").read_bytes() == before


def test_refresh_stale_without_key_keeps_cache(data_dir, monkeypatch, caplog):
    _write_ref(data_dir, asof="2020-01-01")
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with caplog.at_level("WARNING", logger="build_sp500_heatmap"):
        bh.refresh_caps(pd.DataFrame(index=["AAPL"]))
    assert "needs a Polygon key" in caplog.text
    assert (data_dir / "reference.parquet").exists()


def test_prev_payload_recycle_requires_marketcap(tmp_path):
    md = tmp_path / "marketdata"
    md.mkdir()
    payload = {"size_basis": "weight_proxy",
               "tiles": [{"t": "AAPL", "size": 3.5e12}]}
    (md / "sp500_heatmap.json").write_text(json.dumps(payload))
    # a proxy payload must NOT be recycled as if its sizes were real caps
    assert bh._load_caps_from_prev_payload(tmp_path) == {}
    payload["size_basis"] = "marketcap"
    (md / "sp500_heatmap.json").write_text(json.dumps(payload))
    assert bh._load_caps_from_prev_payload(tmp_path) == {"AAPL": 3.5e12}


def test_complete_caps_screens_poisoned_record(monkeypatch):
    # calibration names: cap/weight ratio = 10bn per weight-pct
    weights = {"XLY": {"A": 10.0, "B": 8.0, "C": 6.0, "BKNG": 5.0, "MISS": 2.0}}
    monkeypatch.setattr(bh, "_load_weights_by_etf", lambda: weights)
    caps = {"A": 100e9, "B": 80e9, "C": 60e9,
            "BKNG": 5.8e9}  # poisoned: implied is 5.0 * 10bn = 50bn, 8x screen trips
    out = bh._complete_caps(caps, ["A", "B", "C", "BKNG", "MISS"])
    assert out["BKNG"] == pytest.approx(50e9)      # re-estimated, not kept
    assert out["MISS"] == pytest.approx(20e9)      # gap-filled from weight
    assert out["A"] == 100e9                       # sane real caps untouched
