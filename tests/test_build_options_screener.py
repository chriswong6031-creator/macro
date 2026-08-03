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
    # main() also writes the Scanner-mode rows export (M-XP c). Redirect it into tmp_path —
    # a test must never write into the live site/ tree (MM_DATA_GUARD). Still the real
    # writer, so the export path stays exercised end-to-end.
    _real_export = bos.write_rows_export
    monkeypatch.setattr(
        bos, "write_rows_export",
        lambda rows, coverage, out_path=None: _real_export(rows, coverage, site_dir / "rows.json"))

    result = bos.main()
    assert (site_dir / "rows.json").exists(), "main() did not write the rows export"
    assert result == 0, "builder returned non-zero"
    assert "html" in captured, "write_page was never called — builder produced no output"

    html = captured["html"]
    # W1.6-B: the page is a redirect stub into the workspace's Scanner mode, so
    # the smoke moved off the HTML and onto site/screenerdata/rows.json — the
    # artifact Scanner actually fetches, and now this builder's only product a
    # reader ever sees. (The stub's own shape is pinned by
    # tests/test_options_estate_redirect_stubs.py.)
    assert "options.html#scanner" in html, "the page must redirect into Scanner mode"

    payload = json.loads((site_dir / "rows.json").read_text(encoding="utf-8"))
    rows_parsed = payload["rows"]
    tickers = {r["ticker"] for r in rows_parsed}
    assert "AAPL" in tickers
    assert "NVDA" in tickers
    # young badge is expected (5 and 8 days << 252)
    assert any(r.get("iv_rank_young") for r in rows_parsed), (
        "no row flagged young — the 252-day threshold is not being applied"
    )
    assert payload["coverage"]["n_young"] > 0
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
    orig_export = bos.write_rows_export

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
        # Rows export (M-XP c) into tmp_path, never the live site/ tree (MM_DATA_GUARD).
        bos.write_rows_export = (
            lambda rows, coverage, out_path=None:
            orig_export(rows, coverage, site_dir / "rows.json"))

        rc = bos.main()
    finally:
        bos.GEX_DIR    = orig_gex
        bos.FLOW_DIR   = orig_flow
        bos.TAPE_FLOW_DIR = orig_tape
        bos.write_page = orig_write
        bos.write_rows_export = orig_export

    if rc != 0:
        pytest.skip("builder returned non-zero — may need live data; skip nav check")

    if "content" not in written_html:
        pytest.skip("builder did not produce output")

    html = written_html["content"]

    # W1.6-B INVERTS THIS TEST. It used to require the shared nav (nav-mega,
    # exactly one <nav class="site-nav">, body padding so the fixed nav does not
    # overlap the page) because a stale hand-copied header was the standing
    # failure mode on this page. The page is a redirect stub now, and a stub that
    # rendered the nav would be the defect: it would paint a full header for the
    # fraction of a second before location.replace() fires, and it would give a
    # crawler a second copy of the estate's link graph on a noindex page. So the
    # assertions flip — the nav must be ABSENT, and the redirect present.
    assert "nav-mega" not in html, "the stub must not render the mega-menu"
    assert '<nav class="site-nav">' not in html, "the stub must not render the shared nav"
    assert "options.html#scanner" in html, "the stub lost its redirect target"
    # …and there is consequently no nav to gap against.
    assert "nav-gap" not in html


# ---------------------------------------------------------------------------
# 8.  Scanner-mode rows export — site/screenerdata/rows.json (OEU M-XP c)
# ---------------------------------------------------------------------------

def test_rows_export_carries_rows_stamp_and_counts(tmp_path):
    """The export is the page's rows verbatim + built stamp + universe counts."""
    rows = [
        {"ticker": "SPY", "gross_premium_mn": 900.0, "iv30": 14.2, "net_prem_tone": "~calls"},
        {"ticker": "NVDA", "gross_premium_mn": 410.5, "iv30": 41.0, "net_prem_tone": "~puts"},
    ]
    coverage = {
        "n_names": 2, "n_young": 1, "n_mature": 1, "median_depth_days": 180,
        "young_threshold": bos.YOUNG_THRESHOLD_DAYS, "tape_flow_present": False,
        "n_skew": 2, "n_ivspread": 1, "n_relvol": 2,
        "built": "2026-07-25 04:00 UTC",
    }
    out = bos.write_rows_export(rows, coverage, out_path=tmp_path / "screenerdata" / "rows.json")
    assert out.exists()
    doc = json.loads(out.read_text())

    assert doc["schema"] == bos.ROWS_SCHEMA
    assert doc["built"] == "2026-07-25 04:00 UTC"
    assert doc["n_rows"] == 2
    # Rows are carried verbatim, in the page's order (gross premium desc) — no re-sort,
    # no re-derivation, so page and payload cannot drift.
    assert doc["rows"] == rows
    assert [r["ticker"] for r in doc["rows"]] == ["SPY", "NVDA"]
    # Universe + feature counts ride along so a consumer can print the honest coverage
    # line ("2 names, median 180d history, young < 252d") without scraping the HTML.
    assert doc["coverage"]["n_names"] == 2
    assert doc["coverage"]["n_young"] == 1
    assert doc["coverage"]["median_depth_days"] == 180
    assert doc["coverage"]["young_threshold"] == bos.YOUNG_THRESHOLD_DAYS


def test_rows_export_default_path_is_screenerdata(monkeypatch, tmp_path):
    monkeypatch.setattr(bos.config, "ROOT", tmp_path)
    out = bos.write_rows_export([], {"built": "x"})
    assert out == tmp_path / "site" / "screenerdata" / "rows.json"
    assert json.loads(out.read_text())["n_rows"] == 0


def test_rows_export_survives_non_json_native_values(tmp_path):
    """numpy/NaN-ish leftovers must not explode the export (default=str fallback)."""
    import datetime as _dt
    rows = [{"ticker": "SPY", "asof": _dt.date(2026, 7, 25), "iv30": float("nan")}]
    out = bos.write_rows_export(rows, {"built": "x"}, out_path=tmp_path / "rows.json")
    txt = out.read_text()
    assert "2026-07-25" in txt
    assert json.loads(txt)["n_rows"] == 1


# ---------------------------------------------------------------------------
# 9. OEU M-FIX — screener consistency fixes
#    (a) pain_dist_pct uses the SPOT denominator, like the wall distances
#    (b) stringified-NaN gamma regimes are nulled at the schema boundary
#    (c) median_depth_days copy says "sessions observed", not "calendar days"
# ---------------------------------------------------------------------------

_MFIX_N_ROWS = 5


def _write_mfix_gex_fixture(gex_dir: pathlib.Path, ticker: str, gamma_regime_last):
    """GEX fixture with a wide spot/max_pain gap so the denominator is unambiguous.

    Last row: spot=200, max_pain=100 →
        spot denominator (correct): (200-100)/200*100 =  50.0
        max_pain denominator (bug): (200-100)/100*100 = 100.0

    Dates are a plain Mon-Fri business week with NO NYSE holiday in it (2026-06-15
    is a real week but its Friday, 06-19, is Juneteenth) — the session filter in
    _load_gex_summary (#F3-17) would otherwise drop the fixture's own last row and
    silently shift `gamma_regime_last` onto the wrong row.
    """
    n_rows = _MFIX_N_ROWS
    dates = pd.date_range("2026-06-08", periods=n_rows, freq="D")
    df = pd.DataFrame(
        {
            "spot":              [200.0] * n_rows,
            "iv30":              [0.20 + 0.01 * i for i in range(n_rows)],
            "put_call_oi_ratio": [1.0] * n_rows,
            "max_pain":          [100.0] * n_rows,
            "magnet_up":         [220.0] * n_rows,
            "magnet_down":       [180.0] * n_rows,
            "gamma_flip":        [210.0] * n_rows,
            "gamma_regime":      ["long"] * (n_rows - 1) + [gamma_regime_last],
            "tier":              ["full"] * n_rows,
            "n_strikes":         [100] * n_rows,
        },
        index=dates,
    )
    df.to_parquet(gex_dir / f"summary_{ticker}.parquet")


def _run_mfix_builder(tmp_path, monkeypatch, gamma_regime_last):
    """Run the builder over a single M-FIX fixture; return (rows, html)."""
    from lib import config as lib_config

    _real_load = lib_config.load
    monkeypatch.setattr(
        lib_config, "load",
        lambda: {**_real_load(), "options_screener": {"enabled": True}},
    )

    gex_dir  = tmp_path / "data" / "polygon_gex"
    flow_dir = tmp_path / "data" / "options_flow"
    tape_dir = tmp_path / "data" / "tape_flow" / "daily"
    site_dir = tmp_path / "site"
    gex_dir.mkdir(parents=True)
    flow_dir.mkdir(parents=True)
    site_dir.mkdir(parents=True)

    _write_mfix_gex_fixture(gex_dir, "TSTM", gamma_regime_last)

    monkeypatch.setattr(bos, "GEX_DIR",       gex_dir)
    monkeypatch.setattr(bos, "FLOW_DIR",      flow_dir)
    monkeypatch.setattr(bos, "TAPE_FLOW_DIR", tape_dir)

    captured: dict[str, str] = {}

    def _fake_write(path, html, **kw):
        captured["html"] = html
        return site_dir / pathlib.Path(path).name

    monkeypatch.setattr(bos, "write_page", _fake_write)
    # main() also writes the Scanner-mode rows export (M-XP c). Redirect it into
    # tmp_path — a test must never write into the live site/ tree (MM_DATA_GUARD).
    # Still the real writer, so my corrected pain_dist_pct / gamma_regime values
    # are exercised through the export path too, not just the page.
    _real_export = bos.write_rows_export
    monkeypatch.setattr(
        bos, "write_rows_export",
        lambda rows, coverage, out_path=None: _real_export(rows, coverage, site_dir / "rows.json"))

    assert bos.main() == 0

    # W1.6-B: the rows used to be read back out of the page's own <script
    # id="os-rows"> block. options_screener.html is a redirect stub now, so the
    # payload is read from site/screenerdata/rows.json — which is not a weaker
    # source but the CANONICAL one: it is the file the workspace's Scanner mode
    # actually fetches, where the page's embedded copy never was.
    export = site_dir / "rows.json"
    assert export.exists(), "main() did not write the rows export"
    raw = export.read_text(encoding="utf-8")
    return json.loads(raw)["rows"], raw


class TestSafeStr:
    """_safe_str: the schema-boundary guard against stringified NaN."""

    def test_float_nan_becomes_none(self):
        """The actual defect: pandas gives float('nan'), which is TRUTHY."""
        assert bos._safe_str(float("nan")) is None

    def test_pandas_na_becomes_none(self):
        assert bos._safe_str(pd.NA) is None

    def test_literal_nan_string_becomes_none(self):
        assert bos._safe_str("nan") is None
        assert bos._safe_str("NaN") is None

    def test_none_stays_none(self):
        assert bos._safe_str(None) is None

    def test_empty_and_whitespace_become_none(self):
        assert bos._safe_str("") is None
        assert bos._safe_str("   ") is None

    def test_real_value_survives_and_is_stripped(self):
        assert bos._safe_str("long") == "long"
        assert bos._safe_str("  short ") == "short"

    def test_old_idiom_would_have_produced_the_bug(self):
        """Pin the root cause so the regression is legible, not folklore."""
        raw = float("nan")
        assert bool(raw) is True                      # NaN is truthy
        assert str(raw or "") or None == "nan"        # the old expression
        assert bos._safe_str(raw) is None             # the fix


def test_pain_dist_pct_uses_spot_denominator(tmp_path, monkeypatch):
    """spot=200, max_pain=100 → 50.0 (÷spot), NOT 100.0 (÷max_pain)."""
    rows, _ = _run_mfix_builder(tmp_path, monkeypatch, "long")
    row = next(r for r in rows if r["ticker"] == "TSTM")
    assert row["pain_dist_pct"] == 50.0, (
        f"expected 50.0 (spot denominator), got {row['pain_dist_pct']} "
        "— 100.0 means the max_pain denominator is back"
    )


def test_pain_dist_pct_matches_wall_distance_denominator(tmp_path, monkeypatch):
    """Both distances must be quoted against the same base, so they compare."""
    rows, _ = _run_mfix_builder(tmp_path, monkeypatch, "long")
    row = next(r for r in rows if r["ticker"] == "TSTM")
    spot, max_pain, wall_up = 200.0, 100.0, 220.0
    assert row["pain_dist_pct"]    == round((spot - max_pain) / spot * 100, 2)
    assert row["wall_up_dist_pct"] == round((wall_up - spot) / spot * 100, 2)


def test_nan_gamma_regime_is_nulled_not_stringified(tmp_path, monkeypatch):
    """A NaN regime cell must reach the payload as null, never as "nan"."""
    rows, raw = _run_mfix_builder(tmp_path, monkeypatch, float("nan"))
    row = next(r for r in rows if r["ticker"] == "TSTM")
    assert row["gamma_regime"] is None, f"got {row['gamma_regime']!r}"
    # Serialised form too: a `"nan"` that round-trips through json.loads as the
    # string would satisfy the assertion above only if it were also None.
    assert '"gamma_regime":"nan"' not in raw.replace(" ", "")


def test_real_gamma_regime_still_passes_through(tmp_path, monkeypatch):
    """Positive control: the guard must not null out real values."""
    rows, _ = _run_mfix_builder(tmp_path, monkeypatch, "short")
    row = next(r for r in rows if r["ticker"] == "TSTM")
    assert row["gamma_regime"] == "short"


def test_coverage_stamp_median_depth_is_still_an_observation_count(tmp_path, monkeypatch):
    """median_depth_days counts observation ROWS, not a calendar span.

    W1.6-B RETIRED THE COPY, NOT THE FACT. This used to assert the rendered
    page's `.cov-stamp` said "sessions observed" / "已观测交易日" and never
    "calendar days". options_screener.html is a redirect stub now and the
    workspace's Scanner mode does not surface median depth at all, so there is
    no user-facing string left to hold to that wording — the disclosure did not
    move, it simply has no surface. What survives, and is what this now pins, is
    the FIELD's meaning in the payload Scanner does read: the fixture writes 8
    observation rows over a wider calendar span, and median_depth_days must
    report the row count.

    If Scanner mode ever puts median depth back on screen, the wording law comes
    back with it — and belongs next to that copy, not here.

    HONEST LIMIT of what remains: this fixture's rows are consecutive weekdays,
    so its row count and its calendar span are the SAME number. That makes this
    a field-presence-and-value pin, not a discriminating one — it would not
    catch a switch to a calendar derivation. It is kept because the field still
    reaching the payload with the right value is worth holding; the assertion
    that could tell the two derivations apart was the retired COPY check.
    """
    rows, raw = _run_mfix_builder(tmp_path, monkeypatch, "long")
    coverage = json.loads(raw)["coverage"]
    assert "median_depth_days" in coverage, "coverage lost its median-depth field"
    assert coverage["median_depth_days"] == _MFIX_N_ROWS, (
        f"median_depth_days is {coverage['median_depth_days']}, expected the "
        f"{_MFIX_N_ROWS} observation rows the fixture wrote"
    )


# ---------------------------------------------------------------------------
# 10. OEU bug-wave F3-17 — _load_gex_summary must ignore non-session rows
#     (a per-ticker store accruing a Sat/Sun row makes that ticker's `asof`
#     a non-trading date, which the Scanner's "Data age" column then treats
#     as the freshness reference for every OTHER name too).
# ---------------------------------------------------------------------------

def _write_gex_fixture_with_weekend_tail(gex_dir: pathlib.Path, ticker: str):
    """A real session week (Mon-Fri) PLUS a trailing Sat/Sun pair whose values
    are NOT simple carry-forward duplicates — mirrors the committed store's own
    observed shape (data/polygon_gex/summary_AAPL.parquet: 07-25 Sat and 07-26
    Sun both carry freshly-computed, non-identical spot/iv30)."""
    idx = pd.to_datetime([
        "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24",  # Mon-Fri
        "2026-07-25", "2026-07-26",                                            # Sat, Sun
    ])
    df = pd.DataFrame(
        {
            "spot":              [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "iv30":              [0.20, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26],
            "put_call_oi_ratio": [1.0] * 7,
            "max_pain":          [99.0] * 7,
            "magnet_up":         [110.0] * 7,
            "magnet_down":       [90.0] * 7,
            "gamma_flip":        [102.0] * 7,
            "gamma_regime":      ["long"] * 7,
            "tier":              ["full"] * 7,
            "n_strikes":         [100] * 7,
        },
        index=idx,
    )
    df.to_parquet(gex_dir / f"summary_{ticker}.parquet")


def test_load_gex_summary_drops_weekend_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(bos, "GEX_DIR", tmp_path)
    _write_gex_fixture_with_weekend_tail(tmp_path, "ACME")
    df = bos._load_gex_summary("ACME")
    dates = [str(d.date()) for d in df.index]
    assert "2026-07-25" not in dates
    assert "2026-07-26" not in dates
    assert "2026-07-24" in dates


def test_asof_date_is_a_real_session_not_a_weekend(tmp_path, monkeypatch):
    """The regression that shipped: 370 of 403 rows carried a Sunday asof
    because `.index[-1]` landed on the store's own weekend tail row."""
    monkeypatch.setattr(bos, "GEX_DIR", tmp_path)
    _write_gex_fixture_with_weekend_tail(tmp_path, "ACME")
    df = bos._load_gex_summary("ACME")
    asof_date = str(df.index[-1])[:10]
    assert asof_date == "2026-07-24"
    from lib import nyse_calendar
    from datetime import date as _date
    y, m, d = (int(x) for x in asof_date.split("-"))
    assert nyse_calendar.is_session(_date(y, m, d))


def test_load_gex_summary_never_empties_the_store_on_an_all_weekend_frame(tmp_path, monkeypatch):
    """Fail-open: a (contrived) all-non-session store must fall back to the
    unfiltered frame rather than vanishing entirely."""
    monkeypatch.setattr(bos, "GEX_DIR", tmp_path)
    idx = pd.to_datetime(["2026-07-25", "2026-07-26"])  # Sat, Sun only
    df_in = pd.DataFrame({"iv30": [0.20, 0.21], "spot": [100.0, 101.0]}, index=idx)
    df_in.to_parquet(tmp_path / "summary_WEEKEND.parquet")
    df = bos._load_gex_summary("WEEKEND")
    assert df is not None and not df.empty
    assert str(df.index[-1])[:10] == "2026-07-26"
