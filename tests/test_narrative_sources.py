"""Tests for narrative ignition W2 collectors (NAR-W2).

All tests are hermetic: no network calls, no real Polygon key needed.
Fixtures are constructed in-memory or via tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.narrative_sources import (
    SubstackRssAdapter,
    HnAlgoliaAdapter,
    Edgar8kVelocityAdapter,
    _parse_rss,
    _query_hn,
    _load_registry,
    SUBSTACK_PATH,
    HN_PATH,
    EDGAR_8K_PATH,
    _SUBSTACK_COLS,
    _HN_COLS,
    _EDGAR_COLS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>NVIDIA Blackwell Chip Analysis</title>
      <link>https://example.com/nvda-1</link>
      <pubDate>Thu, 10 Jul 2026 12:00:00 +0000</pubDate>
      <description>SemiAnalysis deep dive into Blackwell architecture.</description>
    </item>
    <item>
      <title>Meta AI Superintelligence</title>
      <link>https://example.com/meta-1</link>
      <pubDate>Wed, 09 Jul 2026 08:00:00 +0000</pubDate>
      <description>Meta's new AI lab and its implications.</description>
    </item>
  </channel>
</rss>"""

_RSS_MINIMAL = """<rss version="2.0">
  <channel>
    <item>
      <title>Minimal Item</title>
      <link>https://example.com/min</link>
    </item>
  </channel>
</rss>"""

_RSS_EMPTY = """<rss version="2.0"><channel></channel></rss>"""

_HN_API_RESPONSE = {
    "hits": [
        {
            "objectID": "42001",
            "title": "Ask HN: NVIDIA GPU shortage",
            "points": 320,
            "num_comments": 85,
            "created_at": "2026-07-10T10:00:00.000Z",
        },
        {
            "objectID": "42002",
            "title": "NVIDIA Blackwell benchmarks",
            "points": 210,
            "num_comments": 44,
            "created_at": "2026-07-10T15:30:00.000Z",
        },
    ]
}

_REGISTRY_CONTENT = {
    "substack_rss": [
        {"feed_id": "semianalysis", "rss_url": "https://www.semianalysis.com/feed",
         "description": "SemiAnalysis"},
    ],
    "hn_keywords": {
        "NVDA": ["NVIDIA", "Blackwell"],
        "META": ["Meta AI"],
    },
    "edgar_8k_velocity": {
        "lookback_days": 30,
        "pace_s": 0.0,
    },
}


# ── 1. Registry yml schema check ──────────────────────────────────────────────

def test_registry_schema_check():
    """config/narrative_sources.yml must have required top-level keys."""
    repo = Path(__file__).resolve().parent.parent
    yml_path = repo / "config" / "narrative_sources.yml"
    assert yml_path.exists(), "config/narrative_sources.yml must exist"
    with yml_path.open() as f:
        reg = yaml.safe_load(f)
    assert isinstance(reg.get("substack_rss"), list), "substack_rss must be a list"
    assert isinstance(reg.get("hn_keywords"), dict),  "hn_keywords must be a dict"
    # Each feed must have feed_id and rss_url
    for feed in reg["substack_rss"]:
        assert "feed_id" in feed, f"feed missing feed_id: {feed}"
        assert "rss_url" in feed, f"feed missing rss_url: {feed}"
    # Citrini excluded (NAR-R11)
    ids = [f["feed_id"] for f in reg["substack_rss"]]
    assert not any("citrini" in i.lower() for i in ids), "Citrini feed must not appear in registry"


# ── 2. RSS parser tests ───────────────────────────────────────────────────────

def test_parse_rss_basic():
    rows = _parse_rss(_RSS_SAMPLE, "semianalysis", "2026-07-10")
    assert len(rows) == 2
    assert rows[0]["feed_id"] == "semianalysis"
    assert rows[0]["url"] == "https://example.com/nvda-1"
    assert rows[0]["title"] == "NVIDIA Blackwell Chip Analysis"
    assert rows[0]["published_date"] == "2026-07-10"
    assert rows[1]["published_date"] == "2026-07-09"
    assert rows[0]["fetch_date"] == "2026-07-10"


def test_parse_rss_minimal_no_date():
    """Item with no pubDate: row still stored with published_date=None."""
    rows = _parse_rss(_RSS_MINIMAL, "test", "2026-07-10")
    assert len(rows) == 1
    assert rows[0]["title"] == "Minimal Item"
    assert rows[0]["published_date"] is None


def test_parse_rss_empty():
    rows = _parse_rss(_RSS_EMPTY, "test", "2026-07-10")
    assert rows == []


def test_parse_rss_malformed_xml():
    """Malformed XML does not raise — returns empty."""
    rows = _parse_rss("<rss><not closed", "test", "2026-07-10")
    assert rows == []


def test_parse_rss_teaser_truncated():
    """Teaser longer than 2048 chars is truncated."""
    long_desc = "x" * 3000
    xml = f"""<rss version="2.0"><channel>
      <item>
        <title>T</title><link>http://x.com/a</link>
        <description>{long_desc}</description>
      </item>
    </channel></rss>"""
    rows = _parse_rss(xml, "test", "2026-07-10")
    assert len(rows[0]["teaser_text"]) <= 2048


# ── 3. SubstackRssAdapter tests ───────────────────────────────────────────────

def test_substack_adapter_dedup(tmp_path, monkeypatch):
    """Second fetch of same URL does not duplicate rows."""
    # Patch config.data_dir to tmp_path
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)

    # Inject a mock registry
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    # Mock HTTP call
    mock_resp = MagicMock()
    mock_resp.text = _RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        first = SubstackRssAdapter().fetch(timeout=5, pace_s=0)
    assert len(first) == 2

    with patch("requests.get", return_value=mock_resp):
        second = SubstackRssAdapter().fetch(timeout=5, pace_s=0)
    # Dedup: same rows, no duplication
    assert len(second) == 2


def test_substack_adapter_pit_columns(tmp_path, monkeypatch):
    """Every stored row must have fetch_date and published_date columns."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    mock_resp = MagicMock()
    mock_resp.text = _RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        df = SubstackRssAdapter().fetch(timeout=5, pace_s=0)

    assert "fetch_date" in df.columns
    assert "published_date" in df.columns
    assert "feed_id" in df.columns
    assert "url" in df.columns


def test_substack_adapter_network_failure_graceful(tmp_path, monkeypatch):
    """Network failure on a feed does not crash; returns existing store (empty here)."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    with patch("requests.get", side_effect=ConnectionError("Network down")):
        result = SubstackRssAdapter().fetch(timeout=5, pace_s=0)

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == _SUBSTACK_COLS


def test_substack_adapter_stores_parquet(tmp_path, monkeypatch):
    """After fetch, parquet file exists with correct columns."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    mock_resp = MagicMock()
    mock_resp.text = _RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        SubstackRssAdapter().fetch(timeout=5, pace_s=0)

    store = tmp_path / "narrative" / SUBSTACK_PATH
    assert store.exists()
    df = pd.read_parquet(store)
    for col in _SUBSTACK_COLS:
        assert col in df.columns, f"Missing column: {col}"


# ── 4. HnAlgoliaAdapter tests ─────────────────────────────────────────────────

def test_hn_adapter_basic(tmp_path, monkeypatch):
    """Adapter stores rows with correct ticker and story_id."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    mock_resp = MagicMock()
    mock_resp.json.return_value = _HN_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        df = HnAlgoliaAdapter().fetch(window_days=2, pace_s=0)

    # Two keywords for NVDA; same story_id deduped across keywords per ticker
    assert "NVDA" in df["ticker"].values
    assert "story_id" in df.columns
    # Dedup: story 42001 appears only once for NVDA even though two keywords hit it
    nvda_df = df[df["ticker"] == "NVDA"]
    assert nvda_df["story_id"].is_unique


def test_hn_adapter_pit_columns(tmp_path, monkeypatch):
    """fetch_date and created_at columns must be present."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    mock_resp = MagicMock()
    mock_resp.json.return_value = _HN_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        df = HnAlgoliaAdapter().fetch(window_days=2, pace_s=0)

    assert "fetch_date" in df.columns
    assert "created_at" in df.columns
    assert "points" in df.columns
    assert "num_comments" in df.columns


def test_hn_adapter_dedup_cross_keyword(tmp_path, monkeypatch):
    """Same story_id from two keywords for same ticker appears only once."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    # Two keywords map the same story
    monkeypatch.setattr(ns, "_load_registry", lambda: {
        "hn_keywords": {"NVDA": ["NVIDIA", "Blackwell"]},
    })

    same_story = {"hits": [{"objectID": "99", "title": "NVDA story",
                             "points": 10, "num_comments": 5,
                             "created_at": "2026-07-10T10:00:00.000Z"}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = same_story
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        df = HnAlgoliaAdapter().fetch(window_days=2, pace_s=0)

    # Should appear once for ticker NVDA
    assert len(df[df["ticker"] == "NVDA"]) == 1


def test_hn_adapter_parquet_columns(tmp_path, monkeypatch):
    """Stored parquet has all expected columns."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    mock_resp = MagicMock()
    mock_resp.json.return_value = _HN_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        HnAlgoliaAdapter().fetch(window_days=2, pace_s=0)

    store = tmp_path / "narrative" / HN_PATH
    assert store.exists()
    df = pd.read_parquet(store)
    for col in _HN_COLS:
        assert col in df.columns, f"Missing column: {col}"


# ── 5. Edgar8kVelocityAdapter tests ──────────────────────────────────────────

_SUBMISSIONS_RESP = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K", "8-K"],
            "filingDate": ["2026-07-08", "2026-07-07", "2026-07-05", "2026-06-01"],
        }
    }
}


def _make_ticker_parquet(tmp_path, group, tickers):
    """Write a minimal constituents.parquet to tmp_path/group/."""
    grp_dir = tmp_path / group
    grp_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(index=tickers).to_parquet(grp_dir / "constituents.parquet")


def test_edgar_adapter_counts(tmp_path, monkeypatch):
    """Adapter correctly counts 8-K forms per ticker per date."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    # Write breadth universe
    _make_ticker_parquet(tmp_path, "breadth", ["AAPL", "NVDA"])

    # Write company_tickers.json
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True, exist_ok=True)
    ct = {"0": {"ticker": "AAPL", "cik_str": "320193"},
          "1": {"ticker": "NVDA", "cik_str": "1045810"}}
    (edgar_dir / "company_tickers.json").write_text(json.dumps(ct))

    mock_resp = MagicMock()
    mock_resp.json.return_value = _SUBMISSIONS_RESP
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200

    with patch("collectors.narrative_sources._sec_get_json",
               return_value=_SUBMISSIONS_RESP):
        df = Edgar8kVelocityAdapter().fetch(lookback_days=90)

    assert not df.empty
    # Should have rows for the 8-K dates within lookback
    assert "ticker" in df.columns
    assert "date" in df.columns
    assert "n_8k" in df.columns
    assert "fetch_date" in df.columns
    # 8-K count on 2026-07-08: 1, on 2026-07-05: 1
    aapl_rows = df[df["ticker"] == "AAPL"]
    assert len(aapl_rows) >= 1
    # n_8k values should all be positive integers
    assert (df["n_8k"] > 0).all()


def test_edgar_adapter_pit_columns(tmp_path, monkeypatch):
    """fetch_date and date columns must both be present (PIT contract)."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    _make_ticker_parquet(tmp_path, "breadth", ["MSFT"])
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True, exist_ok=True)
    (edgar_dir / "company_tickers.json").write_text(
        json.dumps({"0": {"ticker": "MSFT", "cik_str": "789019"}})
    )

    with patch("collectors.narrative_sources._sec_get_json",
               return_value=_SUBMISSIONS_RESP):
        df = Edgar8kVelocityAdapter().fetch(lookback_days=90)

    assert "date" in df.columns
    assert "fetch_date" in df.columns


def test_edgar_adapter_dedup(tmp_path, monkeypatch):
    """Running the adapter twice doesn't duplicate (ticker, date) rows."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    _make_ticker_parquet(tmp_path, "breadth", ["GOOGL"])
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True, exist_ok=True)
    (edgar_dir / "company_tickers.json").write_text(
        json.dumps({"0": {"ticker": "GOOGL", "cik_str": "1652044"}})
    )

    with patch("collectors.narrative_sources._sec_get_json",
               return_value=_SUBMISSIONS_RESP):
        df1 = Edgar8kVelocityAdapter().fetch(lookback_days=90)

    with patch("collectors.narrative_sources._sec_get_json",
               return_value=_SUBMISSIONS_RESP):
        df2 = Edgar8kVelocityAdapter().fetch(lookback_days=90)

    # Second run should not grow the row count (dedup on ticker+date)
    assert len(df2) == len(df1)


def test_edgar_adapter_absent_universe_graceful(tmp_path, monkeypatch):
    """Missing universe stores -> returns empty DataFrame, does not raise."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)
    # No breadth parquets, no membership.json
    df = Edgar8kVelocityAdapter().fetch()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == _EDGAR_COLS


def test_edgar_adapter_missing_cik_map_graceful(tmp_path, monkeypatch):
    """Missing company_tickers.json -> returns empty DataFrame, does not raise."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)
    _make_ticker_parquet(tmp_path, "breadth", ["AAPL"])
    # No company_tickers.json
    df = Edgar8kVelocityAdapter().fetch()
    assert isinstance(df, pd.DataFrame)


def test_edgar_adapter_parquet_columns(tmp_path, monkeypatch):
    """Stored parquet has all expected columns."""
    import collectors.narrative_sources as ns  # noqa: PLC0415
    monkeypatch.setattr(ns.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ns, "_load_registry", lambda: _REGISTRY_CONTENT)

    _make_ticker_parquet(tmp_path, "breadth", ["AMD"])
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True, exist_ok=True)
    (edgar_dir / "company_tickers.json").write_text(
        json.dumps({"0": {"ticker": "AMD", "cik_str": "2488"}})
    )

    with patch("collectors.narrative_sources._sec_get_json",
               return_value=_SUBMISSIONS_RESP):
        Edgar8kVelocityAdapter().fetch(lookback_days=90)

    store = tmp_path / "narrative" / EDGAR_8K_PATH
    assert store.exists()
    df = pd.read_parquet(store)
    for col in _EDGAR_COLS:
        assert col in df.columns, f"Missing column: {col}"


# ── 6. Analyst snapshot accrual tests ─────────────────────────────────────────

def test_analyst_snapshot_accrual(tmp_path):
    """_append_analyst_snapshots writes to data/narrative/analyst_snapshots.parquet."""
    from collectors.yf_analyst import _append_analyst_snapshots, _SNAPSHOT_COLS  # noqa: PLC0415

    snap_path = tmp_path / "analyst_snapshots.parquet"
    rows = [
        {"ticker": "AAPL", "as_of": "2026-07-10",
         "target_mean": 230.0, "target_high": 260.0, "target_low": 200.0,
         "num_analysts": 35, "recommendation": "buy"},
        {"ticker": "NVDA", "as_of": "2026-07-10",
         "target_mean": 180.0, "target_high": 210.0, "target_low": 150.0,
         "num_analysts": 40, "recommendation": "strong_buy"},
    ]
    _append_analyst_snapshots(rows, snapshot_path=snap_path)

    assert snap_path.exists()
    df = pd.read_parquet(snap_path)
    assert len(df) == 2
    for col in _SNAPSHOT_COLS:
        assert col in df.columns, f"Missing column: {col}"
    assert set(df["ticker"]) == {"AAPL", "NVDA"}
    assert (df["snapshot_date"] == "2026-07-10").all()


def test_analyst_snapshot_dedup(tmp_path):
    """Re-running with the same (ticker, snapshot_date) does not duplicate rows."""
    from collectors.yf_analyst import _append_analyst_snapshots  # noqa: PLC0415

    snap_path = tmp_path / "snapshots.parquet"
    rows = [{"ticker": "META", "as_of": "2026-07-10",
              "target_mean": 600.0, "target_high": 700.0, "target_low": 500.0,
              "num_analysts": 45, "recommendation": "buy"}]

    _append_analyst_snapshots(rows, snapshot_path=snap_path)
    _append_analyst_snapshots(rows, snapshot_path=snap_path)

    df = pd.read_parquet(snap_path)
    assert len(df) == 1  # dedup on (ticker, snapshot_date)


def test_analyst_snapshot_all_null_skipped(tmp_path):
    """All-null analyst rows (no PT, no analyst count) are not stored."""
    from collectors.yf_analyst import _append_analyst_snapshots  # noqa: PLC0415

    snap_path = tmp_path / "snapshots.parquet"
    null_rows = [{"ticker": "ZZZ", "as_of": "2026-07-10",
                   "target_mean": None, "target_high": None, "target_low": None,
                   "num_analysts": None, "recommendation": None}]
    _append_analyst_snapshots(null_rows, snapshot_path=snap_path)
    # File not created (or empty) since all rows were null
    assert not snap_path.exists() or len(pd.read_parquet(snap_path)) == 0


def test_analyst_snapshot_accrual_nonfatal(tmp_path, monkeypatch):
    """A crash in _append_analyst_snapshots does not propagate from run()."""
    from collectors import yf_analyst  # noqa: PLC0415

    monkeypatch.setattr(yf_analyst, "_append_analyst_snapshots",
                        MagicMock(side_effect=RuntimeError("intentional")))
    monkeypatch.setattr(yf_analyst, "_load_existing", MagicMock(return_value=None))
    monkeypatch.setattr(yf_analyst, "_load_candidate_universe", MagicMock(return_value=["AAPL"]))
    monkeypatch.setattr(yf_analyst, "_stale_tickers", MagicMock(return_value=["AAPL"]))
    monkeypatch.setattr(yf_analyst, "_upsert_and_write", MagicMock())

    stub_row = {"ticker": "AAPL", "as_of": "2026-07-10",
                "target_mean": 220.0, "target_high": 250.0, "target_low": 190.0,
                "implied_upside_pct": 5.0, "target_dispersion": 0.3,
                "recommendation": "buy", "num_analysts": 30,
                "current_price": 210.0, "provenance_note": "yfinance_info_pit_snapshot"}
    monkeypatch.setattr(yf_analyst, "_fetch_one", MagicMock(return_value=stub_row))

    # Should not raise even though _append_analyst_snapshots throws
    result = yf_analyst.run(out_path=tmp_path / "targets.parquet")
    assert isinstance(result, list)


# ── 7. Citrini exclusion guard ────────────────────────────────────────────────

def test_no_citrini_in_registry():
    """NAR-R11: Citrini must not appear as a feed_id or rss_url in the registry."""
    repo = Path(__file__).resolve().parent.parent
    yml_path = repo / "config" / "narrative_sources.yml"
    with yml_path.open() as f:
        reg = yaml.safe_load(f)
    for feed in (reg.get("substack_rss") or []):
        assert "citrini" not in feed.get("feed_id", "").lower(), (
            f"Citrini feed must not appear in registry (NAR-R11): {feed}"
        )
        assert "citrini" not in feed.get("rss_url", "").lower(), (
            f"Citrini URL must not appear in registry (NAR-R11): {feed}"
        )
