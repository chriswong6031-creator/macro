"""Tests for the SGA-W4 alt-data substrate: engine/altdata_stage.py (read-only
projection), collectors/google_trends.py (fail-open pytrends collector), the
config/narrative_sources.yml google_trends section, and the collect.py registration.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import altdata_stage as A

REPO = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ helpers ----

def _write_trends(root: Path, ticker: str, weekly: list[float]) -> None:
    """Write a data/google_trends/<T>.parquet with the given weekly interest series."""
    idx = pd.date_range("2026-01-04", periods=len(weekly), freq="W-SUN")
    df = pd.DataFrame({"interest": weekly, "_norm": np.log1p(weekly)}, index=idx)
    d = root / "google_trends"
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{ticker}.parquet")


def _write_attention(root: Path, ticker: str, views: list[float]) -> None:
    """Write a data/attention/<T>.parquet (wiki pageviews) with the given views."""
    idx = pd.date_range("2025-09-01", periods=len(views), freq="D")
    df = pd.DataFrame({"views": views, "log_views": np.log1p(views)}, index=idx)
    d = root / "attention"
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{ticker}.parquet")


def _write_wsb(root: Path, rows: list[dict]) -> None:
    """Write data/quiver/wallstreetbets.parquet with the WSB schema
    (Ticker, Count, Sentiment, _collected)."""
    d = root / "quiver"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "wallstreetbets.parquet")


# ------------------------------------------------------------------ engine ----

def test_all_absent_fail_open(tmp_path):
    """Every store missing -> each leg None, never raises, one entry per ticker."""
    out = A.attention_for(["AAPL", "tsla"], root=tmp_path)
    assert set(out) == {"AAPL", "TSLA"}          # normalized + present
    for tk in out:
        assert out[tk] == {"trends": None, "wiki": None, "wsb": None}


def test_wsb_read_and_rank_from_tmp_parquet(tmp_path):
    """WSB leg reads the latest collection day and ranks by mention count."""
    _write_wsb(tmp_path, [
        # an older day that must be IGNORED (only the latest date is used)
        {"Ticker": "AAPL", "Count": 999, "Sentiment": 0.0, "_collected": "2026-07-17"},
        # latest day
        {"Ticker": "SMCI", "Count": 373, "Sentiment": 0.05, "_collected": "2026-07-18"},
        {"Ticker": "NVDA", "Count": 207, "Sentiment": -0.01, "_collected": "2026-07-18"},
        {"Ticker": "AAPL", "Count": 50, "Sentiment": 0.02, "_collected": "2026-07-18"},
    ])
    out = A.attention_for(["SMCI", "NVDA", "AAPL", "ABSENT"], root=tmp_path)
    assert out["SMCI"]["wsb"] == {"mentions": 373, "rank": 1}
    assert out["NVDA"]["wsb"] == {"mentions": 207, "rank": 2}
    # AAPL's stale 999-count row from 07-17 must not leak — latest day is 50 -> rank 3
    assert out["AAPL"]["wsb"] == {"mentions": 50, "rank": 3}
    assert out["ABSENT"]["wsb"] is None


def test_trends_wow_calc_and_spark(tmp_path):
    """Trends leg computes week-over-week %, latest, and a capped sparkline."""
    # 14 weekly points; last two 40 -> 60 = +50% wow; spark capped to last 12
    weekly = [10, 12, 15, 20, 18, 22, 25, 30, 28, 35, 40, 38, 40, 60]
    _write_trends(tmp_path, "TSLA", weekly)
    out = A.attention_for(["TSLA"], root=tmp_path)
    t = out["TSLA"]["trends"]
    assert t is not None
    assert t["latest"] == 60.0
    assert t["wow_pct"] == 50.0
    assert len(t["spark"]) == 12          # _SPARK_WEEKS cap
    assert t["spark"][-1] == 60.0
    assert t["spark"][0] == 15.0          # oldest of the last 12


def test_trends_wow_none_when_no_prior(tmp_path):
    """A single-week series has no prior week -> wow_pct is None, not a crash."""
    _write_trends(tmp_path, "HIMS", [42.0])
    out = A.attention_for(["HIMS"], root=tmp_path)
    t = out["HIMS"]["trends"]
    assert t == {"latest": 42.0, "wow_pct": None, "spark": [42.0]}


def test_wiki_z_and_fade_note(tmp_path):
    """Wiki leg returns a numeric z plus the mandatory fade-risk framing note."""
    # 120 noisy baseline days (nonzero MAD) then a 5-day spike -> strongly positive z
    rng = np.random.default_rng(7)
    baseline = (100.0 + rng.normal(0, 8, 120)).clip(min=1).tolist()
    views = baseline + [1000.0] * 5
    _write_attention(tmp_path, "GME", views)
    out = A.attention_for(["GME"], root=tmp_path)
    w = out["GME"]["wiki"]
    assert w is not None
    assert isinstance(w["z_90d"], float)
    assert w["z_90d"] > 0                       # spike -> positive abnormal attention
    # the fade-risk framing is mandatory (SGA-R2/R4 + wiki_pageviews docstring law)
    assert "crowding caution" in w["note"]
    assert "not a buy" in w["note"].lower()
    assert w["note_zh"]                          # bilingual framing present


def test_wiki_z_none_when_too_short(tmp_path):
    """Too little history -> z is None and the leg degrades to None (no exception)."""
    _write_attention(tmp_path, "NEWCO", [10.0, 12.0, 11.0])
    out = A.attention_for(["NEWCO"], root=tmp_path)
    assert out["NEWCO"]["wiki"] is None


def test_all_three_legs_together(tmp_path):
    """A ticker present in all three stores gets all three legs populated."""
    _write_trends(tmp_path, "AAPL", [30, 32, 35, 40, 38, 42, 45, 50])
    rng = np.random.default_rng(3)
    base = (200.0 + rng.normal(0, 15, 118)).clip(min=1).tolist()
    _write_attention(tmp_path, "AAPL", base + [800.0] * 5)
    _write_wsb(tmp_path, [
        {"Ticker": "AAPL", "Count": 120, "Sentiment": 0.1, "_collected": "2026-07-18"},
    ])
    out = A.attention_for(["AAPL"], root=tmp_path)
    r = out["AAPL"]
    assert r["trends"] is not None and r["trends"]["latest"] == 50.0
    assert r["wiki"] is not None
    assert r["wsb"] == {"mentions": 120, "rank": 1}


# ------------------------------------------------------------------ collector ----

def test_collector_no_op_without_pytrends(monkeypatch):
    """When pytrends is absent, the adapter sets expected_failure (runner -> 'blocked')
    and fetch() raises the same reason rather than crashing on the import."""
    import builtins
    import collectors.google_trends as gt

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "pytrends" or name.startswith("pytrends."):
            raise ImportError("No module named 'pytrends'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    ad = gt.GoogleTrendsAdapter()
    assert ad.expected_failure and "pytrends" in ad.expected_failure
    with pytest.raises(Exception):
        ad.fetch()


def test_collector_parse_interest_drops_partial_and_zero():
    """parse_interest keeps completed weeks, drops the partial bucket, and rejects
    an all-zero series; the 2nd _norm column is added (outlier-guard bypass)."""
    import collectors.google_trends as gt
    idx = pd.date_range("2026-01-04", periods=4, freq="W-SUN")
    df = pd.DataFrame(
        {"tesla": [10, 20, 30, 99], "isPartial": [False, False, False, True]},
        index=idx,
    )
    out = gt.parse_interest(df, "tesla")
    assert list(out.columns) == ["interest", "_norm"]
    assert len(out) == 3                       # partial trailing week dropped
    assert out["interest"].tolist() == [10.0, 20.0, 30.0]
    # all-zero series -> empty
    zdf = pd.DataFrame({"tesla": [0, 0, 0], "isPartial": [False, False, False]}, index=idx[:3])
    assert gt.parse_interest(zdf, "tesla").empty
    # missing term column -> empty
    assert gt.parse_interest(df, "absent_term").empty


def test_collector_daily_offset_deterministic_and_in_range():
    """The rotation offset is deterministic and always yields a valid slice."""
    import collectors.google_trends as gt
    o1 = gt._today_offset(44, gt.TOP_N)
    o2 = gt._today_offset(44, gt.TOP_N)
    assert o1 == o2                            # deterministic within a day
    assert 0 <= o1 <= 44 - gt.TOP_N
    # universe smaller than the pick size -> offset 0 (slice = whole universe)
    assert gt._today_offset(5, gt.TOP_N) == 0


# ------------------------------------------------------------------ config + wiring ----

def test_config_section_parses():
    """config/narrative_sources.yml has a google_trends.terms map of ticker->term."""
    import yaml
    doc = yaml.safe_load((REPO / "config" / "narrative_sources.yml").read_text())
    assert "google_trends" in doc
    terms = doc["google_trends"]["terms"]
    assert isinstance(terms, dict) and len(terms) >= 40
    assert terms.get("AAPL") == "iphone"
    assert terms.get("TSLA") == "tesla"
    # every value is a non-empty search term string
    assert all(isinstance(v, str) and v.strip() for v in terms.values())


def test_collector_term_map_reads_config():
    """The collector's _term_map() loads and upper-cases the config section."""
    import collectors.google_trends as gt
    m = gt._term_map()
    assert m.get("AAPL") == "iphone"
    assert m.get("TSLA") == "tesla"
    assert len(m) >= 40


def test_registration_line_present_in_collect():
    """collect.py registers the adapter in the specs list AND the slow shard set."""
    src = (REPO / "scripts" / "collect.py").read_text()
    assert '"collectors.google_trends", "GoogleTrendsAdapter"' in src
    # registered in the slow/altdata shard next to stocktwits
    assert '"google_trends"' in src


# ============================================================
# Alt-data trending builder (SGA-2 §E — altdata_trending.json)
# ============================================================

def _seed_dir(root: Path) -> Path:
    d = root / "stage_analysis" / "backfill"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_seed(root: Path, fname: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(_seed_dir(root) / fname)


def _seed_all_sources(root: Path) -> None:
    """Minimal but complete four-source seed: one matched topic + trend row each."""
    _write_seed(root, "altdata_gt.parquet", [
        {"google_query": "iphone", "request_name": "iPhone", "matching_date": "2026-06-01",
         "ticker": "AAPL", "company_name": "Apple Inc.",
         "explanation": "Maker of the iPhone flagship product line."},
    ])
    _write_seed(root, "trending_gt.parquet", [
        {"google_query": "iphone", "request_name": "iPhone", "request_type": "Product",
         "description_by_llm": "Apple's flagship smartphone.", "period": "2026-06-01",
         "index_growth_yoy_w1": 120.5, "gt_index_growth_change_w1": 15.0},
    ])
    _write_seed(root, "altdata_reddit.parquet", [
        {"subreddit": "wallstreetbets", "classifier": "finance", "matching_date": "2026-06-01",
         "ticker": "GME", "company_name": "GameStop Corp.",
         "explanation": "Frequently discussed meme stock on this subreddit."},
    ])
    _write_seed(root, "top_growing_subreddits.parquet", [
        {"subreddit": "wallstreetbets", "tag_classification": "finance", "as_of_date": "2026-06-01",
         "subreddit_description": "Options and momentum trading community.",
         "subscriber_yoy_growth_pct": 0.42, "subscriber_yoy_growth_pct_2w_ago": 0.40},
    ])
    _write_seed(root, "altdata_wiki.parquet", [
        {"wikipage": "Nvidia", "classifier": "technology", "matching_date": "2026-06-01",
         "ticker": "NVDA", "company_name": "NVIDIA Corp.",
         "explanation": "The Wikipedia page for the GPU maker itself."},
    ])
    _write_seed(root, "wiki_top_pages.parquet", [
        {"wikipage": "Nvidia", "classifier": "technology", "period": "2026-06-01",
         "page_description": "GPU and AI accelerator company.",
         "momentum": 88.4, "momentum_absolute": 1200.0},
    ])
    _write_seed(root, "altdata_tiktok.parquet", [
        {"hashtag": "stanley", "classifier": "product", "matching_date": "2026-06-01",
         "ticker": "HELE", "company_name": "Helen of Troy Ltd.",
         "explanation": "Owns consumer brands trending on the platform."},
    ])
    _write_seed(root, "top_growing_tiktok.parquet", [
        {"main_hashtag": "stanley", "short_classification_by_chatgpt": "product",
         "description_by_chatgpt": "Viral drinkware trend.", "created_date": "2026-06-01",
         "current_value": 100, "value_1y_ago": 25, "grid_current": 5, "grid_1w_ago": 3},
    ])


def test_trending_per_source_projection(tmp_path):
    """Each of the four sources projects to a topic list with the contract fields."""
    _seed_all_sources(tmp_path)
    art = A.build_altdata_trending(root=tmp_path)
    assert art["schema"] == "altdata_trending.v1"
    assert set(art["sources"]) == {"google", "reddit", "wikipedia", "tiktok"}
    g = art["sources"]["google"]["topics"]
    assert len(g) == 1
    row = g[0]
    assert set(row) >= {"topic", "yoy_pct", "chg_2w_pct", "type", "description",
                        "matched_ticker", "matched_company", "explanation"}
    assert row["matched_ticker"] == "AAPL"
    assert row["yoy_pct"] == 120.5           # gt yoy passed straight through
    assert row["chg_2w_pct"] == 15.0
    # reddit yoy fraction scaled to percent; 2w change derived
    rd = art["sources"]["reddit"]["topics"][0]
    assert rd["yoy_pct"] == 42.0             # 0.42 * 100
    assert rd["chg_2w_pct"] == 2.0           # (0.42 - 0.40) * 100
    # tiktok yoy derived from current vs 1y-ago index
    tt = art["sources"]["tiktok"]["topics"][0]
    assert tt["yoy_pct"] == 300.0            # (100-25)/25 * 100


def test_trending_match_and_explanation_preserved(tmp_path):
    """The topic->ticker match + LLM explanation survive into the artifact + rollup."""
    _seed_all_sources(tmp_path)
    art = A.build_altdata_trending(root=tmp_path)
    nv = art["sources"]["wikipedia"]["topics"][0]
    assert nv["matched_ticker"] == "NVDA"
    assert nv["matched_company"] == "NVIDIA Corp."
    assert "GPU maker" in nv["explanation"]
    # per-ticker rollup records which source mentioned it, with the explanation
    roll = art["by_ticker"]["NVDA"]
    assert roll["sources"] == ["wikipedia"]
    assert roll["topics"][0]["explanation"] == nv["explanation"]


def test_trending_tiktok_seed_only_flag(tmp_path):
    """TikTok is flagged seed_only (no lawful live source); others are live."""
    _seed_all_sources(tmp_path)
    art = A.build_altdata_trending(root=tmp_path)
    assert art["sources"]["tiktok"]["seed_only"] is True
    assert art["sources"]["tiktok"]["live"] is False
    for src in ("google", "reddit", "wikipedia"):
        assert art["sources"][src]["seed_only"] is False
        assert art["sources"][src]["live"] is True
    # display-tier discipline on the artifact envelope
    assert art["is_context_only"] is True and art["display_only"] is True


def test_trending_missing_seeds_fail_open(tmp_path):
    """No seed dir at all -> full four-source scaffold, empty lists, no crash, writes."""
    art = A.build_altdata_trending(root=tmp_path)
    assert set(art["sources"]) == {"google", "reddit", "wikipedia", "tiktok"}
    for src in art["sources"].values():
        assert src["topics"] == []
    assert art["by_ticker"] == {}
    # tiktok flag holds even with no data
    assert art["sources"]["tiktok"]["seed_only"] is True
    # artifact still committed to disk
    assert (tmp_path / "stage_analysis" / "altdata_trending.json").exists()


def test_trending_missing_ticker_row_dropped(tmp_path):
    """A matched row with no ticker is skipped (ticker-linked surface only)."""
    _write_seed(tmp_path, "altdata_gt.parquet", [
        {"google_query": "orphan", "request_name": "Orphan", "matching_date": "2026-06-01",
         "ticker": None, "company_name": None, "explanation": "no ticker match"},
        {"google_query": "iphone", "request_name": "iPhone", "matching_date": "2026-06-01",
         "ticker": "AAPL", "company_name": "Apple Inc.", "explanation": "the iPhone maker"},
    ])
    art = A.build_altdata_trending(root=tmp_path)
    tickers = [r["matched_ticker"] for r in art["sources"]["google"]["topics"]]
    assert tickers == ["AAPL"]           # the ticker-less orphan row is dropped
