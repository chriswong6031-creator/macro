"""Special Situations newswire lane (collectors/special_news.py, P2.1).

Pins the pure pieces — strict exchange-tagged ticker extraction, remit-restricted keyword
classification, issuer-name parsing, the gated no-op — and the desk merge of a news lane.
"""
from __future__ import annotations

import pandas as pd

from lib import config
from collectors import special_news as sn
from engine import special_situations as sse


# ---- ticker extraction (strict: exchange-tagged only) -----------------------
def test_extract_ticker_requires_exchange_tag():
    assert sn.extract_ticker("Acme Corp (NASDAQ: ACME) announces review") == "ACME"
    assert sn.extract_ticker("Beta Inc (NYSE American: BI) special dividend") == "BI"
    assert sn.extract_ticker("Gamma Co (GAMA) does a thing") is None     # bare paren -> too noisy
    assert sn.extract_ticker("no ticker here") is None
    assert sn.extract_ticker(None) is None


# ---- remit-restricted classification ----------------------------------------
def test_classify_news_remit_only():
    assert sn.classify_news("board to explore strategic alternatives")[0] == "Strategic Reviews"
    assert sn.classify_news("announces a new $500 million share repurchase program")[0] == "Capital Returns"
    assert sn.classify_news("mutually agreed to terminate the merger agreement")[0] == "Deal Terminations"
    # M&A is EDGAR-owned (structural form) -> NOT a newswire-lane category
    assert sn.classify_news("entered into a definitive merger agreement to be acquired")[0] is None
    assert sn.classify_news("ordinary product launch")[0] is None


def test_company_of():
    assert sn._company_of("Acme Corp (NASDAQ: ACME) announces strategic review", "ACME") == "Acme Corp"


# ---- gated no-op -------------------------------------------------------------
def test_fetch_gated_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sn, "_cfg", lambda: {"enabled": True, "newswire": False})
    out = sn.fetch_news_situations()
    assert out.empty                                  # no network touched, nothing written
    assert not (tmp_path / "special_situations" / "news.parquet").exists()


# ---- desk merge -------------------------------------------------------------
def test_fetch_uses_name_resolver_when_no_tag(tmp_path, monkeypatch):
    """When a headline has no exchange tag, the lane resolves the ticker from the company
    name (the fix that takes the lane from 0 -> real items)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sn, "_cfg", lambda: {"enabled": True, "newswire": True})
    (tmp_path / "special_situations").mkdir()
    monkeypatch.setattr("engine.news_rss.query", lambda q, **k: (
        [{"title": "Acme Corp explores strategic alternatives", "url": "http://x",
          "seendate": "2026-06-20", "summary": ""}] if "strategic" in q else []))
    monkeypatch.setattr("engine.name_resolver.resolve",
                        lambda text, market=None: "ACME" if "Acme" in str(text) else None)
    df = sn.fetch_news_situations(window_days=3, per_cat=5)
    assert (df["ticker"] == "ACME").any()
    assert df[df["ticker"] == "ACME"].iloc[0]["category"] == "Strategic Reviews"


def test_fetch_falls_back_to_query_category(tmp_path, monkeypatch):
    """A resolved item whose headline doesn't hit a classify keyword still keeps the
    (category-targeted) query's category at low confidence."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sn, "_cfg", lambda: {"enabled": True, "newswire": True})
    (tmp_path / "special_situations").mkdir()
    monkeypatch.setattr("engine.news_rss.query", lambda q, **k: (
        [{"title": "Preferred Bank", "url": "http://y", "seendate": "2026-06-20", "summary": ""}]
        if "repurchase" in q else []))
    monkeypatch.setattr("engine.name_resolver.resolve", lambda text, market=None: "PFBC")
    df = sn.fetch_news_situations(window_days=3, per_cat=5)
    assert (df["ticker"] == "PFBC").any()
    assert df[df["ticker"] == "PFBC"].iloc[0]["category"] == "Capital Returns"


def test_news_rows_merge_into_desk(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    pd.DataFrame([{"id": "n1", "ticker": "ACME", "company": "Acme Corp",
                   "category": "Strategic Reviews", "stage": "initiated",
                   "date": "2026-06-18", "url": "u", "summary": "Acme to explore alternatives",
                   "source": "Reuters", "confidence": "low"}]
                 ).to_parquet(tmp_path / "special_situations" / "news.parquet")
    d = sse.desk_payload()
    sits = {s["ticker"]: s for s in d["situations"]}
    assert "ACME" in sits
    assert sits["ACME"]["source_lane"] == "newswire" and sits["ACME"]["confidence"] == "low"
    assert d["coverage"]["newswire"] >= 1
