"""Wikipedia-attention chip (P2) — collector parse, chip compute, the DISPLAY-ONLY
invariant, and the bilingual / offshore-caveat render.

The whole point of this feature is that it is a neutral over-extension CAUTION, never a
scored or directional signal (research/WIKI_ATTENTION_CHIP_SPEC.md). The load-bearing test
here is `test_display_only_invariant` — it fails loudly the moment attention leaks into any
scoring path. The rest guard the graceful-degradation and bilingual contracts.
"""
from __future__ import annotations

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from collectors import wiki_pageviews as wp
from engine import attention, i18n
from lib import config


# --------------------------------------------------------------------------- #
# 1) collector parse
# --------------------------------------------------------------------------- #
def _canned(views):
    return {"items": [{"project": "en.wikipedia", "article": "Nvidia", "granularity": "daily",
                       "timestamp": f"2026010{i+1}00" if i < 9 else f"202601{i+1}00",
                       "access": "all-access", "agent": "user", "views": v}
                      for i, v in enumerate(views)]}


def test_parse_returns_two_col_dated_numeric_frame():
    df = wp._parse(_canned([100, 120, 90, 5000, 110]))
    assert list(df.columns) == ["views", "log_views"]      # 2-col → outlier guard disabled
    assert isinstance(df.index, pd.DatetimeIndex)
    assert pd.api.types.is_numeric_dtype(df["views"])
    assert pd.api.types.is_numeric_dtype(df["log_views"])
    assert df["views"].iloc[3] == 5000                     # spike preserved, not clipped
    # the Adapter's own validate() must accept the frame
    cleaned = wp.WikiPageviewsAdapter().validate("NVDA", df)
    assert not cleaned.empty and "views" in cleaned.columns


def test_parse_empty_items_raises():
    import pytest
    with pytest.raises(ValueError):
        wp._parse({"items": []})


# --------------------------------------------------------------------------- #
# 2) missing article map → graceful skip / degrade
# --------------------------------------------------------------------------- #
def _profiles(tmp_path, df):
    d = tmp_path / "profile"
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / "profiles.parquet")


def test_ticker_titles_absent_column_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wp.config, "data_dir", lambda: tmp_path)
    _profiles(tmp_path, pd.DataFrame({"name": ["Apple"]}, index=pd.Index(["AAPL"], name="ticker")))
    assert wp._ticker_titles() == {}                       # no wiki_title column → {}


def test_ticker_titles_skips_null_titles(tmp_path, monkeypatch):
    monkeypatch.setattr(wp.config, "data_dir", lambda: tmp_path)
    _profiles(tmp_path, pd.DataFrame(
        {"name": ["Apple", "Nvidia", "Mystery"], "wiki_title": ["Apple_Inc.", None, ""]},
        index=pd.Index(["AAPL", "NVDA", "MYST"], name="ticker")))
    titles = wp._ticker_titles()
    assert titles == {"AAPL": "Apple_Inc."}                # null/blank skipped, no exception


def test_fetch_with_no_titles_raises_so_runner_degrades(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(wp.config, "data_dir", lambda: tmp_path)
    _profiles(tmp_path, pd.DataFrame({"name": ["Apple"]}, index=pd.Index(["AAPL"], name="ticker")))
    with pytest.raises(ValueError):                        # → run_adapter catches → "failed", not a crash
        wp.WikiPageviewsAdapter().fetch()


# --------------------------------------------------------------------------- #
# 3) chip compute / shape
# --------------------------------------------------------------------------- #
def _series(values, start="2026-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"views": values, "log_views": pd.Series(values).pipe(
        lambda s: __import__("numpy").log1p(s)).to_numpy()}, index=idx)


def _panel():
    base = [95 if i % 2 else 105 for i in range(150)]       # mild noise → MAD>0, z≈0
    spike = base[:-5] + [6000, 6500, 7000, 6800, 7200]      # a clear recent attention spike
    return {"SPIKE": _series(spike), "QUIET": _series(base)}


def test_attention_signals_shape_and_clip():
    sig = attention.attention_signals(_panel())
    assert set(sig["SPIKE"]) == {"z", "views", "asof"}
    assert isinstance(sig["SPIKE"]["views"], int)
    assert sig["SPIKE"]["asof"] == "2026-05-30"             # last calendar date of the 150-day span
    # robust z is clipped to the configured display band
    cfg = config.load()["wiki_pageviews"]
    for tk in sig:
        assert cfg["clip_lo"] <= sig[tk]["z"] <= cfg["clip_hi"]


def test_spike_flags_quiet_does_not():
    sig = attention.attention_signals(_panel())
    thr = config.load()["wiki_pageviews"]["chip_threshold"]
    assert sig["SPIKE"]["z"] >= thr                          # spike → caution chip would render
    assert sig["QUIET"]["z"] < thr                           # quiet → no chip


def test_constant_series_yields_no_signal():
    # a perfectly flat series has MAD 0 → undefined z → excluded (no spurious chip)
    flat = {"FLAT": _series([100] * 150)}
    assert "FLAT" not in attention.attention_signals(flat)


# --------------------------------------------------------------------------- #
# 4) DISPLAY-ONLY invariant (the core guard)
# --------------------------------------------------------------------------- #
def test_display_only_invariant():
    """attention must NOT appear in any scoring/ranking path."""
    import re
    forbidden = re.compile(r"attention|wiki_pageviews|attn_z|\battn\b")
    for mod in ("engine/axes.py", "engine/top_picks.py", "engine/setups.py",
                "engine/equity_factors.py"):
        src = (config.ROOT / mod).read_text()
        hit = forbidden.search(src)
        assert hit is None, f"{mod} references attention in a scoring path: {hit.group(0)!r}"


def test_compute_scores_ignores_attention():
    """compute_scores must not consume an attention field even if one is handed in."""
    from engine.top_picks import compute_scores
    rows = [{"ticker": "AAA", "sector": "Tech", "alpha": 1.2, "attention": {"z": 6.0}},
            {"ticker": "BBB", "sector": "Tech", "alpha": -0.4, "attention": {"z": 6.0}}]
    out = compute_scores(rows)
    assert "AAA" in out and "top_score" in out["AAA"]
    # the score is alpha-driven and blind to attention: AAA (high alpha) still beats BBB
    assert out["AAA"]["top_score"] > out["BBB"]["top_score"]


# --------------------------------------------------------------------------- #
# 5) bilingual render + offshore caveat (discovery `conv` macro)
# --------------------------------------------------------------------------- #
def _render_conv(ticker, attn_z=2.5):
    """Render the real discovery.html.j2 with a single Top-Picks row carrying the
    attention z, so the `conv()` macro's chip is exercised exactly as in production."""
    row = {"ticker": ticker, "name": ticker, "sector": "Technology", "price": 100.0,
           "top_score": 1.0, "band": "strong", "alpha": 1.0, "alpha_band": "strong",
           "conviction_z": 0.0, "n_legs": 0, "legs": {}, "entry": "steady",
           "entry_en": "Steady", "entry_zh": "稳定", "entry_css": "tp-steady", "buyzone": False,
           "total_mom": 5.0, "rev_1m": 1.0, "rev_pctile": 50.0, "sector_rank": 1, "sector_n": 10,
           "ins_buyers": 0, "ins_bps": None, "attn_z": attn_z}
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr)
    return env.get_template("discovery.html.j2").render(
        strongest=[row], weakest=[], buyzone=[], sectors=[], by_sector={}, sector_order=[],
        entry_meta={}, tilt_legs=[], alpha_w=0.6, tilt_w=0.4, attn_threshold=2.0,
        as_of="2026-06-14", windows={"beta_win": 252, "form": 252, "skip": 21}, n=1,
        built="2026-06-14 00:00 UTC")


def test_chip_is_bilingual():
    html = _render_conv("AAPL")
    assert "l-en" in html and "l-zh" in html                # the t() macro emits both spans
    assert "关注" in html                                    # zh label present
    assert "👁" in html


def test_chip_below_threshold_absent():
    assert "👁" not in _render_conv("AAPL", attn_z=1.2)      # sub-threshold → no chip


def test_offshore_caveat_fires_for_cn_hk_only():
    for cn in ("600519.SS", "000001.SZ", "0700.HK"):
        h = _render_conv(cn)
        assert "intl only" in h and "仅境外" in h            # mainland-blind caveat shown
    assert "intl only" not in _render_conv("AAPL")           # US name: no caveat
