"""International collectors (collectors/special_intl.py, Phase 4).

Pins the exchange-tagged ticker extraction (-> suffixed symbol), the per-market gate
no-op, and the engine merge of the cross-border intl lane.
"""
from __future__ import annotations

import pandas as pd

from lib import config
from collectors import special_intl as si
from engine import special_situations as sse


def test_extract_intl_ticker_suffixes():
    assert si.extract_intl_ticker("Barclays plc (LSE: BARC) Rule 2.7 offer") == "BARC.L"
    assert si.extract_intl_ticker("ARC Resources (TSX: ARX) plan of arrangement") == "ARX.TO"
    assert si.extract_intl_ticker("Tencent (HKEX: 0700) privatisation") == "0700.HK"
    assert si.extract_intl_ticker("BHP (ASX: BHP) substantial holder notice") == "BHP.AX"
    assert si.extract_intl_ticker("Some Co (TSXV: XYZ) bid") == "XYZ.V"
    assert si.extract_intl_ticker("No exchange tag here (CEO: jdoe)") is None
    assert si.extract_intl_ticker(None) is None


def test_fetch_gated_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(si, "_cfg", lambda: {"enabled": True, "intl_uk": False, "intl_canada": False})
    out = si.fetch_intl_situations()
    assert out.empty
    assert not (tmp_path / "special_situations" / "intl.parquet").exists()


def test_intl_rows_merge_into_desk_cross_border(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    pd.DataFrame([{"id": "i1", "ticker": "BARC.L", "company": "Barclays",
                   "category": "Tender Offers", "stage": "live", "market": "uk", "country": "GB",
                   "date": "2026-06-18", "url": "u", "summary": "Rule 2.7 offer", "confidence": "low"}]
                 ).to_parquet(tmp_path / "special_situations" / "intl.parquet")
    d = sse.desk_payload()
    sits = {s["ticker"]: s for s in d["situations"]}
    assert "BARC.L" in sits
    assert sits["BARC.L"]["source_lane"] == "intl" and sits["BARC.L"]["cross_border"] is True
    assert sits["BARC.L"]["country"] == "GB"
    assert d["coverage"]["intl"] >= 1
