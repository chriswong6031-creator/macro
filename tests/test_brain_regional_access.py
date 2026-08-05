"""Mastermind AI can see Hong Kong, mainland-China and Canadian data (2026-08-04).

THE DEFECT THESE PIN
--------------------
The brain had TWO price ladders. ``brain_gateway._load_symbol_closes`` was
region-aware (US + china_stocks + hk_stocks + the wide regional matrices), so the
brain could quote Tencent's 20-day return and RSI. ``chart_render._PRICE_SUBDIRS``
— which feeds ``chart_digest`` (the Eyes), ``measure_line`` and
``render_inline_chart`` — was ``("data/baskets/ohlcv", "data/stocks")``, US only.
So the same turn that produced a Tencent technical read produced "no data" for
every Tencent candle, for all of Hong Kong, all A-shares and all of the TSX, while
1,678 A-share and 158 HK per-name OHLCV parquets sat in the repo updated that night.
Neither ladder reached data/hk, data/china or data/canada at all, so the Hang Seng
and the S&P/TSX had no chart AND no technicals.

The tests are written against SYNTHETIC trees so they pin the resolution rules
rather than today's inventory, except where a test explicitly reads the real repo.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from engine.marketing import chart_render as CR
from engine.neuralweb import chart_perception as cp
from engine.neuralweb import market_packet as mp

pytest.importorskip("pyarrow")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _ohlcv(path, n=420, base=100.0, intrabar=True):
    """Write a daily-bar parquet. intrabar=False → close+volume only (the shape of
    data/hk, data/china, data/canada and every wide matrix)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range(end=pd.Timestamp(date(2026, 8, 4)), periods=n)
    closes = [base + (i % 17) - (i % 5) * 0.5 for i in range(n)]
    cols = {"close": closes, "volume": [1_000_000] * n}
    if intrabar:
        cols |= {
            "open": [c - 0.4 for c in closes],
            "high": [c + 2.5 for c in closes],
            "low": [c - 2.5 for c in closes],
        }
    pd.DataFrame(cols, index=pd.Index(days, name="Date")).to_parquet(path)


def _wide(path, symbols, n=420):
    path.parent.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range(end=pd.Timestamp(date(2026, 8, 4)), periods=n)
    frame = pd.DataFrame(
        {s: [50.0 + (i % 13) for i in range(n)] for s in symbols},
        index=pd.Index(days, name="Date"),
    )
    frame.to_parquet(path)


@pytest.fixture()
def tree(tmp_path):
    """A miniature of the real store layout, one name per region."""
    _ohlcv(tmp_path / "data/stocks/AAPL.parquet")
    _ohlcv(tmp_path / "data/baskets/ohlcv/CVI.parquet")
    _ohlcv(tmp_path / "data/hk_stocks/0700.HK.parquet")
    _ohlcv(tmp_path / "data/china_stocks/600519.SS.parquet")
    _ohlcv(tmp_path / "data/hk/_HSI.parquet", intrabar=False)
    _ohlcv(tmp_path / "data/china/000001.SS.parquet", intrabar=False)
    _ohlcv(tmp_path / "data/canada/_GSPTSE.parquet", intrabar=False)
    _wide(tmp_path / "data/canada_search/closes.parquet", ["SHOP.TO", "RY.TO"])
    return tmp_path


# ---------------------------------------------------------------------------
# 1. the ladder reaches every region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", [
    "AAPL", "CVI",                       # US, both curated trees
    "0700.HK", "600519.SS",              # per-name regional OHLCV
    "_HSI", "000001.SS", "_GSPTSE",      # regional index/ETF trees
    "SHOP.TO", "RY.TO",                  # Canada — wide matrix only
])
def test_every_region_loads_bars(tree, symbol):
    bars = CR.load_ohlcv(symbol, tree, n=90)
    assert bars is not None, f"{symbol}: no bars"
    dates, o, h, l, c, v = bars
    assert len(dates) == 90
    assert all(lo <= cl <= hi for lo, cl, hi in zip(l, c, h)), f"{symbol}: bad OHLC"


@pytest.mark.parametrize("symbol", ["0700.HK", "600519.SS", "_HSI", "SHOP.TO"])
def test_the_eyes_open_on_regional_symbols(tree, symbol):
    """chart_digest returned {'available': False, 'reason': 'no data'} for every
    one of these — the Chart Mastermind was blind outside the US."""
    digest = cp.chart_digest(symbol, "1D", root=tree)
    assert digest["available"] is True, digest
    assert digest["bars"] > 0
    assert digest["levels"] is not None
    weekly = cp.chart_digest(symbol, "1W", root=tree)
    assert weekly["available"] is True, weekly


def test_measure_line_no_longer_reports_no_data_offshore(tree):
    out = cp.measure_line("0700.HK", "1D",
                          {"t": 1_735_000_000, "p": 100.0},
                          {"t": 1_750_000_000, "p": 110.0}, root=tree)
    assert out.get("reason") != "no data", out


# ---------------------------------------------------------------------------
# 2. the safety property that makes appending the regional trees legitimate
# ---------------------------------------------------------------------------

def test_us_trees_are_searched_first(tree):
    """Same ticker in a US tree and a regional tree → US bars win. This is why the
    append is safe; it is also what stops data/hk/EEM.parquet from ever outranking
    a curated US ETF should one be added."""
    _ohlcv(tree / "data/stocks/DUPE.parquet", base=100.0)
    _ohlcv(tree / "data/hk_stocks/DUPE.parquet", base=900.0)
    bars = CR.load_ohlcv("DUPE", tree, n=10)
    assert bars is not None and bars[4][-1] < 200.0, "regional tree shadowed a US name"


def test_massive_store_still_excluded_from_the_default():
    assert "data/massive_stock_day" not in CR._PRICE_SUBDIRS
    assert CR._PRICE_SUBDIRS[:2] == ("data/baskets/ohlcv", "data/stocks")


def test_a_bare_ticker_never_reaches_a_wide_matrix(tree):
    """Wide matrices are keyed by exchange suffix. An unqualified US ticker must not
    be able to fall into one — that would be the shadowing bug in another costume."""
    assert CR._wide_close_series("AAPL", tree, 30) is None
    assert CR._wide_close_series("SHOP.TO", tree, 30) is not None


def test_every_real_us_ticker_still_resolves_to_a_us_tree():
    """Against the REAL repo: the regional append must not have moved a single one
    of the ~2,700 curated US names onto a non-US file."""
    root = mp.Path(__file__).resolve().parent.parent
    us_names = set()
    for sub in CR._US_PRICE_SUBDIRS:
        us_names |= {p.stem for p in (root / sub).glob("*.parquet")}
    if not us_names:
        pytest.skip("curated US trees absent in this checkout")
    strays = [
        t for t in sorted(us_names)
        if (p := CR._price_parquet(t, root)) is not None
        and not any(str(p).endswith(f"{sub}/{t}.parquet") for sub in CR._US_PRICE_SUBDIRS)
    ]
    assert strays == [], f"US tickers now resolving outside the US trees: {strays[:10]}"


# ---------------------------------------------------------------------------
# 3. index aliases — same instrument, different spelling; never a proxy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spelling,stored", [
    ("HSI", "_HSI"), ("^HSI", "_HSI"), ("hangseng", "_HSI"),
    ("TSX", "_GSPTSE"), ("^GSPTSE", "_GSPTSE"),
    ("SHCOMP", "000001.SS"), ("^SSEC", "000001.SS"),
])
def test_index_aliases_resolve(tree, spelling, stored):
    assert CR.resolve_price_symbol(spelling) == stored
    assert CR.load_ohlcv(spelling, tree, n=30) is not None


def test_no_etf_is_served_as_an_index_alias():
    """510300.SS is the CSI 300 ETF, not the index. Aliasing it would launder a fund
    as the benchmark — the same rule market_packet's _INDEX_ETF_FALLBACK applies."""
    assert "CSI300" not in CR._PRICE_SYMBOL_ALIASES
    assert "510300.SS" not in CR._PRICE_SYMBOL_ALIASES.values()


# ---------------------------------------------------------------------------
# 4. close-only bars disclose themselves, and the gap null is PRINTED
# ---------------------------------------------------------------------------

def test_bar_basis_separates_real_wicks_from_synthesized_ones(tree):
    assert CR.bar_basis("0700.HK", tree) == "intrabar"
    assert CR.bar_basis("_HSI", tree) == "close_to_close"
    assert CR.bar_basis("SHOP.TO", tree) == "close_to_close"
    assert CR.bar_basis("NOPE", tree) == "none"


def test_close_only_bars_cannot_express_a_gap():
    """The reason the null must be printed rather than returned as []. With
    high = max(prev_close, close) and low = min(prev_close, close),
    low[i] > high[i-1] is unsatisfiable — so the detector ALWAYS returns []."""
    closes = [100.0]
    for i in range(400):                      # violent walk, huge single-day moves
        closes.append(closes[-1] * (1.35 if i % 3 else 0.7))
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) for o, c in zip(opens, closes)]
    lows = [min(o, c) for o, c in zip(opens, closes)]
    assert cp._unfilled_gaps(list(range(len(closes))), highs, lows, closes) == []


def test_a_close_only_digest_prints_the_gap_null(tree):
    digest = cp.chart_digest("SHOP.TO", "1D", root=tree)
    assert digest["bar_basis"] == "close_to_close"
    assert digest["bar_basis_note"]
    gaps = digest["gaps"]
    assert isinstance(gaps, dict) and gaps["measurable"] is False, (
        "an empty gap LIST reads as the finding 'no unfilled gaps'; on close-only "
        "bars that is a blind spot, not a finding"
    )
    assert "not a fact about the tape" in gaps["note"]


def test_an_intrabar_digest_keeps_its_real_gap_list(tree):
    digest = cp.chart_digest("0700.HK", "1D", root=tree)
    assert digest["bar_basis"] == "intrabar"
    assert isinstance(digest["gaps"], list)
    assert "bar_basis_note" not in digest


def test_section_filter_cannot_strip_the_disclosure(tree):
    """bar_basis rides in the header: narrowing to one section must not be a way to
    receive close-only bars with no warning attached."""
    digest = cp.chart_digest("SHOP.TO", "1D", sections=["levels"], root=tree)
    assert digest["bar_basis"] == "close_to_close"
    assert digest["bar_basis_note"]


def test_only_the_1d_digest_carries_gaps_at_all(tree):
    """Pins the reachability the correction relies on: _weekly_snapshot builds with
    want_gaps=False, so the 1W digest and the weekly block riding on a 1D digest have
    no gaps key. If that ever changes, an uncorrected empty list would reappear on
    close-only symbols and this test is where it surfaces."""
    for symbol in ("0700.HK", "SHOP.TO"):
        assert "gaps" not in cp.chart_digest(symbol, "1W", root=tree)
        weekly = cp.chart_digest(symbol, "1D", root=tree).get("weekly") or {}
        assert "gaps" not in weekly


def test_an_undeterminable_basis_never_defaults_to_real_wicks(tree, monkeypatch):
    """The disclosure's failure value must not be the one answer that lets a
    synthesized chart read as a measured one."""
    monkeypatch.setattr(
        "engine.marketing.chart_render.bar_basis",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert cp._bar_basis("SHOP.TO", tree) == "unknown"


def test_measure_line_says_a_touch_means_the_close(tree):
    out = cp.measure_line("_HSI", "1D",
                          {"t": 1_735_000_000, "p": 100.0},
                          {"t": 1_750_000_000, "p": 104.0}, root=tree)
    assert out["bar_basis"] == "close_to_close"
    assert "CLOSE" in out["bar_basis_note"]


def test_the_disclosure_never_leaks_an_internal_knob(tree):
    """Anti-distillation: output text carries plain words, never a parameter value."""
    digest = cp.chart_digest("SHOP.TO", "1D", root=tree)
    text = json.dumps(digest, ensure_ascii=False)
    for knob in ("_ATR_PERIOD", "_ZIGZAG_ATR_MULT", "_TOUCH_BAND_ATR",
                 "_LEVEL_CLUSTER_ATR", "_PCTL_LOOKBACK"):
        assert knob not in text
    for value in ("1.5", "0.6", "0.5", "252", "420"):
        assert value not in digest["bar_basis_note"]


# ---------------------------------------------------------------------------
# 5. the two ladders are now one
# ---------------------------------------------------------------------------

def test_technicals_and_charts_agree_on_which_symbols_exist(tree):
    """The original defect in one assertion: for every symbol, either BOTH the
    technical snapshot and the chart digest see it, or neither does."""
    from engine.neuralweb import brain_gateway as bg

    for symbol in ("AAPL", "0700.HK", "600519.SS", "_HSI", "_GSPTSE", "SHOP.TO"):
        has_tech = bool(bg._technical_snapshot(symbol, tree).get("last"))
        has_chart = cp.chart_digest(symbol, "1D", root=tree).get("available") is True
        assert has_tech == has_chart is True, (
            f"{symbol}: technicals={has_tech} chart={has_chart} — the ladders disagree"
        )


def test_one_bar_is_a_price_not_a_history(tmp_path):
    """The hand-rolled ladder required two rows; chart_render.load_closes does not.
    Routing through it must not start emitting a 'technical snapshot' built from a
    single close, where every return, MA, RSI and MACD is necessarily null."""
    from engine.neuralweb import brain_gateway as bg

    d = tmp_path / "data" / "stocks"
    d.mkdir(parents=True)
    pd.DataFrame(
        {"close": [10.0], "volume": [1]},
        index=pd.Index(pd.bdate_range(end="2026-08-04", periods=1), name="Date"),
    ).to_parquet(d / "ONE.parquet")
    assert bg._technical_snapshot("ONE", tmp_path) == {}


def test_a_trend_label_is_never_asserted_without_a_moving_average(tmp_path):
    """'mixed / transition' claims a trend read. With too few bars for even SMA20
    there is no moving average to be mixed ABOUT — and the wide regional matrices
    make short histories easy to hit."""
    from engine.neuralweb import brain_gateway as bg

    d = tmp_path / "data" / "stocks"
    d.mkdir(parents=True)
    pd.DataFrame(
        {"close": [10.0 + i * 0.1 for i in range(5)], "volume": [1] * 5},
        index=pd.Index(pd.bdate_range(end="2026-08-04", periods=5), name="Date"),
    ).to_parquet(d / "FIVE.parquet")
    tech = bg._technical_snapshot("FIVE", tmp_path)["technicals"]
    assert tech["sma20"] is None and tech["sma50"] is None and tech["sma200"] is None
    assert tech["trend"] == "too little history for a trend read"


# ---------------------------------------------------------------------------
# 6. fundamentals route to the region's own baked tree
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,subdir", [
    ("AAPL", "stockdata"),
    ("600519.SS", "chinastockdata"),
    ("0700.HK", "hkstockdata"),
    ("SHOP.TO", "canadastockdata"),
    ("8306.T", "intlstockdata"),
])
def test_fundamentals_read_the_regional_bake(tmp_path, symbol, subdir):
    from engine.neuralweb import brain_gateway as bg

    d = tmp_path / "site" / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{symbol}.json").write_text(
        json.dumps({"asof": "2026-08-04", "name": symbol, "profile": {"sector": "X"}}),
        encoding="utf-8",
    )
    out = bg._tool_get_fundamentals({"symbol": symbol}, tmp_path)
    assert out["available"] is True, out
    assert out["source"] == f"site/{subdir}/{symbol}.json"


def test_a_missing_regional_file_names_the_regional_path(tmp_path):
    from engine.neuralweb import brain_gateway as bg

    out = bg._tool_get_fundamentals({"symbol": "9999.HK"}, tmp_path)
    assert out["available"] is False
    assert "hkstockdata" in out["note"], out


# ---------------------------------------------------------------------------
# 7. the grounding packet carries the regional boards, each on its OWN clock
# ---------------------------------------------------------------------------

def _regional_root(tmp_path, ca_as_of="2026-07-31"):
    for sub, label, bench, as_of in (
        ("hkbasketdata", "HSI", [1.00, 1.02], "2026-08-04"),
        ("chinabasketdata", "CSI 300", [1.00, 0.99], "2026-08-04"),
        ("canadabasketdata", "S&P/TSX", [1.00, 1.005], ca_as_of),
    ):
        d = tmp_path / "site" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "baskets.json").write_text(json.dumps({
            "as_of": as_of,
            "benchmark_label": label,
            "chart": {"dates": ["2026-08-03", as_of], "bench": bench},
            "theme_intel": {"rotation_5d": {"climbers": [{"name": "Widgets"}]}},
        }), encoding="utf-8")
    for sub, payload in (
        ("hk_regime", {"date": "2026-08-04", "quad": "Q1", "quad_name": "Goldilocks",
                       "cycle_tag": "mid", "liquidity_overlay": "neutral",
                       "risk_state": "Risk-on", "peg_state": "weak-side",
                       "confidence": 0.094}),
        ("china_regime", {"date": "2026-08-04", "quad": "Q3",
                          "quad_name": "Stagflation", "cycle_tag": "mid",
                          "liquidity_overlay": "contracting", "confidence": 0.281}),
        ("canada_regime", {"date": ca_as_of, "quad": "Q2", "quad_name": "Reflation",
                           "cycle_tag": "late", "liquidity_overlay": "neutral",
                           "confidence": 0.136}),
    ):
        d = tmp_path / "data" / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_packet_carries_all_three_boards(tmp_path):
    packet = mp.build_packet(_regional_root(tmp_path))
    codes = [e["code"] for e in packet["regional"]]
    assert codes == ["HK", "CN", "CA"]
    hk = packet["regional"][0]
    assert hk["bench_label"] == "HSI"
    assert hk["quad_name"] == "Goldilocks"
    assert hk["bench_change_pct"] == pytest.approx(2.0, abs=0.01)


def test_each_board_renders_its_own_session_stamp(tmp_path):
    """A Canadian print under Hong Kong's date would be a fabricated fact. These
    boards close at different times and CA is routinely a session behind."""
    text = mp.render_digest(mp.build_packet(_regional_root(tmp_path)), char_budget=20000)
    line = next(ln for ln in text.split("\n") if ln.startswith("REGIONAL"))
    assert "HK (2026-08-04)" in line
    assert "CN (2026-08-04)" in line
    assert "CA (2026-07-31)" in line


def test_numeric_confidence_never_reaches_the_prompt(tmp_path):
    """Module law: a decimal beside the word 'confidence' reads to a model as a
    calibrated probability, and none of these reads are that."""
    packet = mp.build_packet(_regional_root(tmp_path))
    blob = json.dumps(packet["regional"])
    assert "confidence" not in blob
    for leaked in ("0.094", "0.281", "0.136"):
        assert leaked not in blob


def test_a_missing_board_is_omitted_not_borrowed(tmp_path):
    """Fail-soft, per block: losing Canada must not blank HK or lend it CA's stamp."""
    root = _regional_root(tmp_path)
    (root / "site" / "canadabasketdata" / "baskets.json").unlink()
    (root / "data" / "canada_regime" / "latest.json").unlink()
    packet = mp.build_packet(root)
    assert [e["code"] for e in packet["regional"]] == ["HK", "CN"]
    assert any("regional CA" in g for g in packet["gaps"])


def test_regional_sources_are_in_the_cache_key(tmp_path):
    """A nightly regional refresh must invalidate the digest cache like any other
    source, or the brain serves yesterday's Hang Seng all day."""
    for region in mp._REGIONS:
        assert region.basket_rel in mp._ROOT_SOURCES
        assert region.regime_rel in mp._ROOT_SOURCES


# ---------------------------------------------------------------------------
# 8. the doctrine knows these boards exist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "how does the hang seng look", "what is going on with A-shares",
    "is the TSX a buy", "恒生指数怎么样", "南向资金", "分析一下沪深300",
    "tencent 0700.HK setup", "chart SHOP.TO", "600519.SS valuation",
])
def test_regional_questions_route_to_the_regional_lens(message):
    from engine.neuralweb import analyst_doctrine as ad

    assert "lens_regional" in [m["id"] for m in ad.route(message)], message


@pytest.mark.parametrize("message", [
    "analyze AAPL", "is TSLA overbought", "draw a trendline on NVDA",
])
def test_us_questions_do_not_route_to_it(message):
    from engine.neuralweb import analyst_doctrine as ad

    assert "lens_regional" not in [m["id"] for m in ad.route(message)], message
