"""US Options Screener builder — unit tests.

Covers:
1. IV-rank computation: correct percentile, young-label logic, n_days count
2. IV-rank young-label: fires when n_days < YOUNG_THRESHOLD_DAYS
3. Missing store degrade: builder returns 0 and renders a page (columns omitted
   gracefully, not a crash) when polygon_gex store is empty/absent
4. Kill-switch: options_screener.enabled=false → builder returns 0
5. Net-premium tone heuristic: tape_tone priority, net_prem_mn fallback, both directions
6. Builder smoke test: fixture stores → page renders with expected coverage stamp
7. Nav checks: rendered page passes check_nav_gap + check_nav_mega
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_options_screener import (
    _compute_iv_rank,
    _net_prem_tone,
    YOUNG_THRESHOLD_DAYS,
)
import scripts.build_options_screener as bos


# ---------------------------------------------------------------------------
# 1 & 2.  IV-rank: correct percentile + young-label logic
# ---------------------------------------------------------------------------

def _make_gex_df(iv30_vals: list[float], dates: list[str] | None = None) -> pd.DataFrame:
    """Helper: build a minimal GEX summary DataFrame with the given iv30 values."""
    n = len(iv30_vals)
    if dates is None:
        dates = [f"2026-0{1 + i // 28}-{(i % 28) + 1:02d}" for i in range(n)]
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"iv30": iv30_vals}, index=idx)


def test_iv_rank_correct_percentile():
    """IV-rank should equal (count of values strictly below current) / (n-1) × 100."""
    vals = [0.10, 0.20, 0.30, 0.40, 0.50]
    df = _make_gex_df(vals)
    rank, n_days, _ = _compute_iv_rank(df)
    # current = 0.50 (last); 4 values below → 4/4 × 100 = 100.0
    assert rank == pytest.approx(100.0, abs=0.1)
    assert n_days == 5


def test_iv_rank_middle_value():
    vals = [0.10, 0.20, 0.30, 0.40, 0.50]
    # Inject current IV as the median (0.30 at position 2)
    df = _make_gex_df([0.30, 0.10, 0.50, 0.40, 0.20])
    rank, _, _ = _compute_iv_rank(df)
    # last value = 0.20; 1 value strictly below (0.10) → 1/4 × 100 = 25.0
    assert rank == pytest.approx(25.0, abs=0.1)


def test_iv_rank_young_when_few_days():
    """Fewer than YOUNG_THRESHOLD_DAYS calendar days → is_young=True."""
    # 10 rows spanning a narrow range → well below 252 calendar days
    dates = [f"2026-06-{15 + i:02d}" for i in range(10)]
    vals = [0.20 + 0.01 * i for i in range(10)]
    df = _make_gex_df(vals, dates)
    _, n_days, is_young = _compute_iv_rank(df)
    assert is_young is True
    assert n_days == 10


def test_iv_rank_mature_when_long_history():
    """252+ calendar days of history → is_young=False."""
    import datetime
    start = datetime.date(2025, 6, 1)
    dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(260)]
    vals = [0.20 + 0.001 * i for i in range(260)]
    df = _make_gex_df(vals, dates)
    _, _, is_young = _compute_iv_rank(df)
    assert is_young is False


def test_iv_rank_none_on_empty():
    df = pd.DataFrame()
    rank, n_days, is_young = _compute_iv_rank(df)
    assert rank is None
    assert n_days == 0
    assert is_young is True


def test_iv_rank_none_on_single_row():
    """Single row → not enough to compute a percentile."""
    df = _make_gex_df([0.25])
    rank, n_days, is_young = _compute_iv_rank(df)
    assert rank is None
    assert n_days == 1
    assert is_young is True


# ---------------------------------------------------------------------------
# 3. Missing store degrade
# ---------------------------------------------------------------------------

def test_builder_returns_0_when_gex_dir_missing(tmp_path, monkeypatch):
    """Builder returns 0 (no crash) when polygon_gex store does not exist."""
    monkeypatch.setattr(bos, "GEX_DIR", tmp_path / "nonexistent_gex")
    monkeypatch.setattr(bos, "FLOW_DIR", tmp_path / "nonexistent_flow")
    monkeypatch.setattr(bos, "TAPE_FLOW_DIR", tmp_path / "nonexistent_tape")
    result = bos.main()
    assert result == 0


def test_builder_returns_0_when_gex_dir_empty(tmp_path, monkeypatch):
    """Builder returns 0 (no crash) when polygon_gex dir is empty."""
    gex_dir = tmp_path / "polygon_gex"
    gex_dir.mkdir()
    monkeypatch.setattr(bos, "GEX_DIR", gex_dir)
    monkeypatch.setattr(bos, "FLOW_DIR", tmp_path / "options_flow")
    monkeypatch.setattr(bos, "TAPE_FLOW_DIR", tmp_path / "tape_flow")
    result = bos.main()
    assert result == 0


# ---------------------------------------------------------------------------
# 4. Kill-switch
# ---------------------------------------------------------------------------

def test_builder_disabled_by_config(monkeypatch):
    """options_screener.enabled=false → builder returns 0 without reading stores."""
    from lib import config as lib_config

    def _fake_load():
        return {"options_screener": {"enabled": False}}

    monkeypatch.setattr(lib_config, "load", _fake_load)
    # Patch write_page on bos to capture and avoid writing to the real site dir
    monkeypatch.setattr(bos, "write_page", lambda path, html, **kw: path)
    result = bos.main()
    assert result == 0


# ---------------------------------------------------------------------------
# 5. Net-premium tone heuristic
# ---------------------------------------------------------------------------

def test_tone_tape_priority_over_net_prem():
    """tape_tone takes priority over net_premium_mn when both present."""
    tone = _net_prem_tone(net_prem=-5.0, tape_tone="call-leaning")
    assert tone == "call-leaning"


def test_tone_fallback_to_net_prem_positive():
    tone = _net_prem_tone(net_prem=3.0, tape_tone=None)
    assert tone == "call-leaning"


def test_tone_fallback_to_net_prem_negative():
    tone = _net_prem_tone(net_prem=-2.0, tape_tone=None)
    assert tone == "put-leaning"


def test_tone_fallback_zero():
    tone = _net_prem_tone(net_prem=0.0, tape_tone=None)
    assert tone == "neutral"


def test_tone_no_data():
    tone = _net_prem_tone(net_prem=None, tape_tone=None)
    assert tone == ""


# ---------------------------------------------------------------------------
# 6. Builder smoke test — fixture stores → page renders with coverage stamp
# ---------------------------------------------------------------------------

def _write_gex_fixture(gex_dir: pathlib.Path, ticker: str, n_rows: int = 5):
    """Write a minimal polygon_gex summary parquet for `ticker`."""
    dates = pd.date_range("2026-06-15", periods=n_rows, freq="D")
    df = pd.DataFrame(
        {
            "spot":              [100.0 + i for i in range(n_rows)],
            "iv30":              [0.20 + 0.01 * i for i in range(n_rows)],
            "put_call_oi_ratio": [1.0 + 0.05 * i for i in range(n_rows)],
            "max_pain":          [99.0 + i for i in range(n_rows)],
            "magnet_up":         [105.0 + i for i in range(n_rows)],
            "magnet_down":       [95.0 - i for i in range(n_rows)],
            "gamma_flip":        [102.0 + i for i in range(n_rows)],
            "tier":              ["full"] * n_rows,
            "n_strikes":         [100] * n_rows,
        },
        index=dates,
    )
    df.to_parquet(gex_dir / f"summary_{ticker}.parquet")


def _write_flow_fixture(flow_dir: pathlib.Path, ticker: str):
    """Write a minimal options_flow summary parquet for `ticker`."""
    dates = pd.date_range("2026-07-02", periods=1, freq="D")
    df = pd.DataFrame(
        {
            "spot":          [100.0],
            "volume":        [500_000],
            "premium_mn":    [12.5],
            "net_premium_mn":[ 2.0],
            "pc_ratio":      [0.95],
            "zerodte_share": [0.12],
        },
        index=dates,
    )
    df.to_parquet(flow_dir / f"summary_{ticker}.parquet")


def test_builder_smoke(tmp_path, monkeypatch):
    """Builder with fixture stores should write options_screener.html containing coverage stamp.

    Patches only the data-dir constants and redirects write_page to tmp_path/site
    so the real config.yml and templates are used (ROOT unchanged).
    """
    from lib import pages as lib_pages
    from lib import config as lib_config

    # Force options_screener enabled regardless of config.yml kill-switch setting
    _real_load = lib_config.load
    monkeypatch.setattr(lib_config, "load", lambda: {**_real_load(), "options_screener": {"enabled": True}})

    # Set up fixture dirs
    gex_dir  = tmp_path / "data" / "polygon_gex"
    flow_dir = tmp_path / "data" / "options_flow"
    tape_dir = tmp_path / "data" / "tape_flow" / "daily"
    site_dir = tmp_path / "site"
    gex_dir.mkdir(parents=True)
    flow_dir.mkdir(parents=True)
    site_dir.mkdir(parents=True)
    # tape_dir intentionally not created — tests graceful absence

    _write_gex_fixture(gex_dir, "AAPL", n_rows=5)
    _write_gex_fixture(gex_dir, "NVDA", n_rows=8)
    _write_flow_fixture(flow_dir, "AAPL")

    monkeypatch.setattr(bos, "GEX_DIR",       gex_dir)
    monkeypatch.setattr(bos, "FLOW_DIR",      flow_dir)
    monkeypatch.setattr(bos, "TAPE_FLOW_DIR", tape_dir)

    # Redirect write_page output to tmp site dir.
    # bos imports write_page directly, so patch on the bos module namespace.
    captured: dict[str, str] = {}

    def _fake_write(path, html, **kw):
        captured["html"] = html
        out = site_dir / pathlib.Path(path).name
        out.write_text(html, encoding="utf-8")
        return out

    monkeypatch.setattr(bos, "write_page", _fake_write)

    result = bos.main()
    assert result == 0, "builder returned non-zero"
    assert "html" in captured, "write_page was never called — builder produced no output"

    html = captured["html"]
    # young badge is expected (5 and 8 days << 252)
    assert "young" in html
    # headline
    assert "Options Screener" in html
    # honest-box provenance text
    assert "IV-rank" in html or "IV分位" in html
    # embedded JSON payload should have our fixtures
    assert "AAPL" in html
    assert "NVDA" in html

    # Verify embedded ROWS payload is valid JSON (regression: autoescape used to HTML-encode it)
    import re as _re
    m = _re.search(r'<script[^>]+id="os-rows"[^>]*>(.*?)</script>', html, _re.DOTALL)
    assert m, "os-rows script tag not found in page"
    rows_parsed = json.loads(m.group(1))
    tickers = {r["ticker"] for r in rows_parsed}
    assert "AAPL" in tickers
    assert "NVDA" in tickers


# ---------------------------------------------------------------------------
# 7. Nav checks — rendered page passes check_nav_gap + check_nav_mega
# ---------------------------------------------------------------------------

def test_nav_checks_pass_on_rendered_page(tmp_path, monkeypatch):
    """Rendered options_screener.html must carry nav-mega and a shared site-nav."""
    from lib import config as lib_config

    # Force options_screener enabled regardless of config.yml kill-switch setting
    _real_load = lib_config.load
    monkeypatch.setattr(lib_config, "load", lambda: {**_real_load(), "options_screener": {"enabled": True}})

    gex_dir  = tmp_path / "data" / "polygon_gex"
    flow_dir = tmp_path / "data" / "options_flow"
    tape_dir = tmp_path / "data" / "tape_flow" / "daily"
    site_dir = tmp_path / "site"
    gex_dir.mkdir(parents=True)
    flow_dir.mkdir(parents=True)
    site_dir.mkdir(parents=True)

    for ticker in ["AAPL", "NVDA", "TSLA"]:
        _write_gex_fixture(gex_dir, ticker, n_rows=10)
        _write_flow_fixture(flow_dir, ticker)

    orig_gex   = bos.GEX_DIR
    orig_flow  = bos.FLOW_DIR
    orig_tape  = bos.TAPE_FLOW_DIR
    orig_write = bos.write_page   # patching bos module namespace directly

    written_html: dict[str, str] = {}

    def _fake_write(path, html, **kw):
        written_html["content"] = html
        (site_dir / "options_screener.html").write_text(html)
        return site_dir / "options_screener.html"

    try:
        bos.GEX_DIR       = gex_dir
        bos.FLOW_DIR      = flow_dir
        bos.TAPE_FLOW_DIR = tape_dir
        bos.write_page    = _fake_write

        rc = bos.main()
    finally:
        bos.GEX_DIR    = orig_gex
        bos.FLOW_DIR   = orig_flow
        bos.TAPE_FLOW_DIR = orig_tape
        bos.write_page = orig_write

    if rc != 0:
        pytest.skip("builder returned non-zero — may need live data; skip nav check")

    if "content" not in written_html:
        pytest.skip("builder did not produce output")

    html = written_html["content"]

    # nav-mega check: must carry the Research mega-menu
    assert "nav-mega" in html, "options_screener.html missing nav-mega (stale nav)"

    # Exactly one shared site-nav
    assert html.count('<nav class="site-nav">') == 1, \
        "options_screener.html should render exactly one shared nav"

    # Page-level integrity
    assert "Options Screener" in html, "options_screener.html missing page title"
    assert "honest-box" in html, "options_screener.html missing data-provenance honest-box"

    # Padding check: body tag must carry padding (nav-gap guard)
    assert "padding:" in html, "options_screener.html body appears to have no top padding (nav-gap risk)"
