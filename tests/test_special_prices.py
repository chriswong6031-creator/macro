"""Deal-target price backfill (collectors/special_prices.py, P1.2).

Pins the plausible-ticker filter, the deal-target ticker selection, the no-op-when-priced
path, and that engine._closes_panel ingests the arb_prices cache.
"""
from __future__ import annotations

import pandas as pd

from lib import config
from collectors import special_prices as sp
from engine import special_situations as sse


def test_plausible_ticker():
    assert sp._plausible_ticker("AAPL")
    assert sp._plausible_ticker("ARX.TO")
    assert not sp._plausible_ticker("NAN")        # null artifact
    assert not sp._plausible_ticker("NSA-PB")     # hyphenated preferred
    assert not sp._plausible_ticker("")


def _seed(tmp_path, rows):
    (tmp_path / "special_situations").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_parquet(tmp_path / "special_situations" / "events.parquet")


def test_deal_target_tickers_selects_arb_with_price(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: "ABC", 2: "DEF", 3: "GHI"}, {}))
    _seed(tmp_path, [
        {"id": "1", "form_type": "DEFM14A", "company": "ABC", "cik": "1", "items": None,
         "date_filed": "2026-06-12", "llm_terms": json.dumps({"price_per_share": 25.0})},
        {"id": "2", "form_type": "SC 13D", "company": "DEF", "cik": "2", "items": None,
         "date_filed": "2026-06-12", "llm_terms": json.dumps({"price_per_share": 9.0})},  # activist, not arb
        {"id": "3", "form_type": "DEFM14A", "company": "GHI", "cik": "3", "items": None,
         "date_filed": "2026-06-12", "llm_terms": None},                                   # no terms
    ])
    tk = sp.deal_target_tickers()
    assert tk == ["ABC"]                          # only the arb-category situation with a price


def test_fetch_noop_when_already_priced(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: "ABC"}, {}))
    _seed(tmp_path, [{"id": "1", "form_type": "DEFM14A", "company": "ABC", "cik": "1",
                      "items": None, "date_filed": "2026-06-12",
                      "llm_terms": json.dumps({"price_per_share": 25.0})}])
    # ABC already in a close cache -> nothing to fetch (no network touched)
    (tmp_path / "breadth").mkdir()
    pd.DataFrame({"ABC": [10.0, 11.0]}, index=pd.bdate_range("2026-06-01", periods=2)).to_parquet(
        tmp_path / "breadth" / "_closes_cache.parquet")
    assert sp.fetch_arb_prices() == 0


def test_closes_panel_ingests_arb_prices(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    (tmp_path / "special_situations").mkdir()
    idx = pd.bdate_range("2026-06-01", periods=5)
    pd.DataFrame({"ZZADR": [50.0] * 5}, index=idx).to_parquet(
        tmp_path / "special_situations" / "arb_prices.parquet")
    panel = sse._closes_panel()
    assert "ZZADR" in panel.columns
