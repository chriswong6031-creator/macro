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


class _FakeRefClient:
    """ticker_details stub: value per symbol, or an Exception instance to raise."""

    def __init__(self, by_sym):
        self._by_sym = by_sym

    def ticker_details(self, sym):
        r = self._by_sym.get(sym)
        if isinstance(r, Exception):
            raise r
        return r or {}


def _run_refresh(monkeypatch, by_sym, symbols):
    import collectors.polygon_options as po
    monkeypatch.setenv("POLYGON_API_KEY", "k")
    monkeypatch.setattr(po, "PolygonOptions", lambda: _FakeRefClient(by_sym))
    bh.refresh_caps(pd.DataFrame(index=list(symbols)), force=True)


def test_refresh_extracts_shares_from_details_dict(data_dir, monkeypatch):
    # Pins the /v3/reference/tickers contract: results is ONE dict (not a page
    # list) — routing it through the paginating _get iterated its keys and wrote
    # shares=None for all 503 rows on every sweep 2026-07-11..08-02.
    by_sym = {
        "BKNG": {"weighted_shares_outstanding": 774_878_436,
                 "sic_code": "4700", "sic_description": "TRANSPORTATION SERVICES"},
        "BRK.B": {"share_class_shares_outstanding": 1_300_000_000},
    }
    _run_refresh(monkeypatch, by_sym, ["BKNG", "BRK-B"])
    ref = pd.read_parquet(data_dir / "reference.parquet")
    assert ref.loc["BKNG", "shares"] == 774_878_436.0     # weighted preferred
    assert ref.loc["BKNG", "sic"] == "4700"
    assert ref.loc["BRK-B", "shares"] == 1_300_000_000.0  # share-class fallback,
    assert bh._shares_coverage(ref) == 1.0                # queried as BRK.B


def test_refresh_refuses_majority_none_overwrite(data_dir, monkeypatch, capsys):
    # A populated committed reference must survive a systemically failing sweep.
    _write_ref(data_dir, asof="2020-01-01")
    before = pd.read_parquet(data_dir / "reference.parquet")
    _run_refresh(monkeypatch, {"AAPL": RuntimeError("boom")}, ["AAPL"])
    after = pd.read_parquet(data_dir / "reference.parquet")
    assert after["shares"].notna().sum() == before["shares"].notna().sum() == 1
    assert after.loc["AAPL", "asof"] == "2020-01-01"  # stale stamp kept -> retries
    lines = capsys.readouterr().out.splitlines()
    # GitHub parses '::' only at column 0 — both annotations must START their line
    assert any(ln.startswith("::warning title=sp500-ref-shares-coverage::")
               for ln in lines)
    assert any(ln.startswith("::warning title=sp500-ref-refused-overwrite::")
               for ln in lines)


def test_refresh_low_coverage_bootstrap_still_writes(data_dir, monkeypatch, capsys):
    # No committed reference yet: even a degraded sweep seeds the cache (today's
    # behavior), but the coverage ::warning must fire so it can't rot silently.
    by_sym = {"AAPL": {"weighted_shares_outstanding": 1.5e10},
              "MSFT": RuntimeError("boom")}
    _run_refresh(monkeypatch, by_sym, ["AAPL", "MSFT"])
    ref = pd.read_parquet(data_dir / "reference.parquet")
    assert bh._shares_coverage(ref) == 0.5
    assert ref.loc["AAPL", "shares"] == 1.5e10
    out = capsys.readouterr().out
    assert any(ln.startswith("::warning title=sp500-ref-shares-coverage::")
               and "MSFT: RuntimeError: boom" in ln
               for ln in out.splitlines())


def test_refresh_all_none_over_all_none_overwrites(data_dir, monkeypatch):
    # The current committed cache is 0% populated — a fresh (even failing) sweep
    # may replace it; the clobber veto belongs to majority-POPULATED caches only.
    df = pd.DataFrame({"ticker": ["AAPL"], "shares": [None]}).set_index("ticker")
    df["asof"] = "2020-01-01"
    df.to_parquet(data_dir / "reference.parquet")
    _run_refresh(monkeypatch, {"AAPL": RuntimeError("boom")}, ["AAPL"])
    ref = pd.read_parquet(data_dir / "reference.parquet")
    assert ref.loc["AAPL", "asof"] != "2020-01-01"  # rewritten, stamp advanced


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
