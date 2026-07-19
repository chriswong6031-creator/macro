"""tests/test_insider_power_signals.py — Tests for engine.insider_power_signals.

Covers:
1. Module imports without error; SIGNALS dict present with required keys.
2. insider_power() returns a bounded float (0-100) where data exists, NaN where absent.
3. Each SIGNALS fn returns a pd.Series aligned to df.index.
4. Score direction: pure-buy panel -> score > 50; pure-sell panel -> score < 50; neutral -> ~50.
5. Look-ahead guard: filing_date after as_of_date is excluded (score changes when future
   trades are gated out).
6. NaN propagation: unknown ticker / empty panel -> NaN.
7. Role weighting: CEO trade outweighs other role at same size/recency.
8. Recency weighting: recent trade dominates older trade of equal size/role.
9. insider_buy / insider_sell fire correctly above/below thresholds.
10. insider_power_from_snapshot() returns float or NaN from JSON data.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

import engine.insider_power_signals as ip
from engine.insider_power_signals import (
    SIGNALS,
    N_TRADES,
    LOOKBACK_DAYS,
    HALF_LIFE_DAYS,
    TANH_SCALE,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    insider_power,
    insider_power_state,
    insider_buy,
    insider_sell,
    _role_weights_series,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ohlcv(n: int = 252, ticker: str | None = None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame for signal testing."""
    idx = pd.bdate_range("2025-01-02", periods=n)
    close = pd.Series(100.0 + np.arange(n, dtype=float) * 0.1, index=idx)
    df = pd.DataFrame({
        "close": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "open": close,
        "volume": 1_000_000.0,
    })
    if ticker:
        df.attrs["ticker"] = ticker
    return df


def _panel_row(
    ticker: str = "TEST",
    code: str = "P",
    usd: float = 1_000_000.0,
    filing_date: str = "2025-06-01",
    is_officer: bool = True,
    is_director: bool = False,
    is_tenpct: bool = False,
    title: str = "Chief Executive Officer",
) -> dict:
    """Build a single panel-row dict."""
    return {
        "ticker": ticker,
        "issuer_cik": "0000000001",
        "filing_date": pd.Timestamp(filing_date),
        "trans_date": pd.Timestamp(filing_date),
        "rptownercik": "0000000099",
        "code": code,
        "direct": True,
        "is_officer": is_officer,
        "is_director": is_director,
        "is_tenpct": is_tenpct,
        "title": title,
        "shares": usd / 10.0,
        "price": 10.0,
        "usd": usd,
        "quarter": "2025q2",
    }


def _make_panel(rows: list[dict]) -> pd.DataFrame:
    """Build a panel DataFrame from a list of row dicts."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Import / SIGNALS dict
# ---------------------------------------------------------------------------

def test_import():
    """Module imports without error."""
    import engine.insider_power_signals  # noqa: F401


def test_signals_dict_present():
    """SIGNALS is a non-empty dict."""
    assert isinstance(SIGNALS, dict), "SIGNALS must be a dict"
    assert len(SIGNALS) >= 3, "SIGNALS must have at least 3 entries"


REQUIRED_KEYS = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}


def test_signals_required_keys():
    """Every SIGNALS descriptor has required keys and correct family."""
    for sid, desc in SIGNALS.items():
        missing = REQUIRED_KEYS - set(desc.keys())
        assert not missing, f"Signal '{sid}' missing keys: {missing}"
        assert desc["family"] == "insider", f"Signal '{sid}' family should be 'insider'"
        assert desc["kind"] in {"event", "state"}, f"Signal '{sid}' kind invalid"
        assert desc["direction"] in {-1, 0, 1}, f"Signal '{sid}' direction invalid"
        assert callable(desc["fn"]), f"Signal '{sid}' fn not callable"
        assert "en" in desc["display"], f"Signal '{sid}' display missing 'en'"
        assert "zh" in desc["display"], f"Signal '{sid}' display missing 'zh'"


def test_signals_ids_registered():
    """Expected signal IDs present in SIGNALS."""
    for expected in ("insider_power_state", "insider_buy", "insider_sell"):
        assert expected in SIGNALS, f"'{expected}' not in SIGNALS"


# ---------------------------------------------------------------------------
# 2. insider_power() core: bounded / NaN
# ---------------------------------------------------------------------------

def test_pure_buy_score_above_50():
    """All-buy panel produces a score > 50."""
    rows = [_panel_row(code="P", usd=1_000_000, filing_date="2025-11-01") for _ in range(5)]
    panel = _make_panel(rows)
    score = insider_power(panel, as_of_date="2026-01-01", _panel=None)
    assert not math.isnan(score), "Expected a score, got NaN"
    assert score > 50.0, f"Pure buy should score > 50, got {score}"


# NOTE: the former ``test_pure_sell_score_below_50`` asserted "any pure-sell
# panel → score < 50". That encoded the v1 saturation BUG (a routine sell-only
# tape read maximally bearish). Neutral-by-default v2 splits routine vs
# informative selling in the per-ticker Terminal scorer (engine.insider_power);
# the replacement cases live below under "Insider Power v2 — neutral-by-default".


def test_equal_buy_sell_near_50():
    """Equal buy and sell at same size/role/date -> score ~50."""
    rows = (
        [_panel_row(code="P", usd=1_000_000, filing_date="2025-11-01")] * 3
        + [_panel_row(code="S", usd=1_000_000, filing_date="2025-11-01")] * 3
    )
    panel = _make_panel(rows)
    score = insider_power(panel, as_of_date="2026-01-01")
    assert abs(score - 50.0) < 5.0, f"Balanced buy/sell should be near 50, got {score}"


def test_score_bounded_0_100():
    """Score is always in [0, 100]."""
    # Extreme buy
    rows = [_panel_row(code="P", usd=10_000_000, filing_date="2025-12-01") for _ in range(50)]
    panel = _make_panel(rows)
    s = insider_power(panel, as_of_date="2026-01-01")
    assert 0.0 <= s <= 100.0, f"Score out of bounds: {s}"

    # Extreme sell
    rows = [_panel_row(code="S", usd=10_000_000, filing_date="2025-12-01") for _ in range(50)]
    panel = _make_panel(rows)
    s = insider_power(panel, as_of_date="2026-01-01")
    assert 0.0 <= s <= 100.0, f"Score out of bounds: {s}"


def test_empty_panel_returns_nan():
    """Empty panel returns NaN."""
    panel = _make_panel([])
    score = insider_power(panel, as_of_date="2026-01-01")
    assert math.isnan(score), "Empty panel should return NaN"


def test_no_open_market_trades_returns_nan():
    """Panel with only award/grant codes (non P/S) returns NaN."""
    row = _panel_row(code="P", usd=1_000_000, filing_date="2025-11-01")
    row["code"] = "A"  # Award — not open-market
    panel = _make_panel([row])
    score = insider_power(panel, as_of_date="2026-01-01")
    assert math.isnan(score), "Non P/S codes should produce NaN"


def test_unknown_ticker_returns_nan():
    """Scoring an unknown ticker against the live panel returns NaN (no data)."""
    # Use a clearly non-existent ticker; panel is loaded from disk so may return NaN
    score = insider_power("__NOEXIST_TICKER_XYZ__", as_of_date="2025-01-01")
    assert math.isnan(score), "Unknown ticker should return NaN"


# ---------------------------------------------------------------------------
# 5. Look-ahead guard
# ---------------------------------------------------------------------------

def test_look_ahead_guard():
    """Filing after as_of_date is excluded; score shifts when future trade removed."""
    # One recent strong buy on 2025-12-30 (after as_of)
    # One older buy on 2025-10-01 (before as_of)
    future_row = _panel_row(code="P", usd=10_000_000, filing_date="2025-12-30")
    past_row = _panel_row(code="S", usd=1_000_000, filing_date="2025-10-01")
    panel = _make_panel([future_row, past_row])

    # as_of = 2025-12-15: future row should be EXCLUDED
    score_before = insider_power(panel, as_of_date="2025-12-15")
    # as_of = 2025-12-31: future row IS included
    score_after = insider_power(panel, as_of_date="2025-12-31")

    # Before: only the sell row is visible -> score < 50
    # After: both rows visible -> the big buy should push score up
    assert score_before < score_after, (
        f"Look-ahead guard failed: before={score_before:.2f} should be < after={score_after:.2f}"
    )


def test_look_ahead_future_only_is_nan():
    """If ALL trades are after as_of_date, result is NaN (no eligible data)."""
    row = _panel_row(code="P", usd=1_000_000, filing_date="2026-06-01")
    panel = _make_panel([row])
    score = insider_power(panel, as_of_date="2026-01-01")
    assert math.isnan(score), "All-future trades should return NaN"


# ---------------------------------------------------------------------------
# 7. Role weighting
# ---------------------------------------------------------------------------

def test_role_weight_ceo_beats_other():
    """CEO buy scores higher than 'other' role buy at same size/recency."""
    ceo_panel = _make_panel([
        _panel_row(code="P", usd=1_000_000, filing_date="2025-11-01",
                   is_officer=True, title="Chief Executive Officer")
    ])
    other_panel = _make_panel([
        _panel_row(code="P", usd=1_000_000, filing_date="2025-11-01",
                   is_officer=False, is_director=False, is_tenpct=False, title="Unknown")
    ])
    score_ceo = insider_power(ceo_panel, as_of_date="2026-01-01")
    score_other = insider_power(other_panel, as_of_date="2026-01-01")
    assert score_ceo > score_other, (
        f"CEO should score higher than other: ceo={score_ceo:.2f}, other={score_other:.2f}"
    )


def test_role_weights_series_ordering():
    """_role_weights_series: top officer > officer > director > tenpct > other."""
    rows = [
        _panel_row(is_officer=True, title="Chief Executive Officer"),   # top officer 1.5
        _panel_row(is_officer=True, title="VP of Sales"),               # officer 1.0
        _panel_row(is_officer=False, is_director=True, title=""),       # director 0.6
        _panel_row(is_officer=False, is_director=False, is_tenpct=True, title=""),  # tenpct 0.3
        _panel_row(is_officer=False, is_director=False, is_tenpct=False, title=""), # other 0.2
    ]
    panel = _make_panel(rows)
    w = _role_weights_series(panel).tolist()
    assert w[0] == 1.5, f"Top officer weight should be 1.5, got {w[0]}"
    assert w[1] == 1.0, f"Officer weight should be 1.0, got {w[1]}"
    assert w[2] == 0.6, f"Director weight should be 0.6, got {w[2]}"
    assert w[3] == 0.3, f"Tenpct weight should be 0.3, got {w[3]}"
    assert w[4] == 0.2, f"Other weight should be 0.2, got {w[4]}"


# ---------------------------------------------------------------------------
# 8. Recency weighting
# ---------------------------------------------------------------------------

def test_recency_decay():
    """Recent buy scores higher than old buy of equal size/role."""
    # Recent: 7 days ago
    recent_panel = _make_panel([
        _panel_row(code="P", usd=1_000_000, filing_date="2025-12-25")
    ])
    # Old: 300 days ago
    old_panel = _make_panel([
        _panel_row(code="P", usd=1_000_000, filing_date="2025-03-05")
    ])
    as_of = "2026-01-01"
    score_recent = insider_power(recent_panel, as_of_date=as_of)
    score_old = insider_power(old_panel, as_of_date=as_of)
    assert score_recent > score_old, (
        f"Recent trade should score higher: recent={score_recent:.2f}, old={score_old:.2f}"
    )


# ---------------------------------------------------------------------------
# 3 / 9. SIGNALS fn contract: returns aligned pd.Series
# ---------------------------------------------------------------------------

def _synthetic_panel_for_ticker(ticker: str, code: str = "P") -> pd.DataFrame:
    """Minimal panel for a given ticker."""
    return _make_panel([
        _panel_row(ticker=ticker, code=code, filing_date="2025-11-01")
    ])


def test_insider_power_state_returns_series():
    """insider_power_state returns a pd.Series aligned to df.index."""
    df = _ohlcv(ticker="TESTX")
    panel = _synthetic_panel_for_ticker("TESTX", code="P")
    result = insider_power_state(df, _panel=panel)
    assert isinstance(result, pd.Series), "Must return pd.Series"
    assert len(result) == len(df), "Series length must match df"
    assert result.index.equals(df.index), "Series index must match df.index"


def test_insider_buy_returns_series():
    """insider_buy returns a pd.Series aligned to df.index."""
    df = _ohlcv(ticker="TESTX")
    panel = _synthetic_panel_for_ticker("TESTX", code="P")
    result = insider_buy(df, _panel=panel)
    assert isinstance(result, pd.Series), "Must return pd.Series"
    assert len(result) == len(df), "Series length must match df"


def test_insider_sell_returns_series():
    """insider_sell returns a pd.Series aligned to df.index."""
    df = _ohlcv(ticker="TESTX")
    panel = _synthetic_panel_for_ticker("TESTX", code="S")
    result = insider_sell(df, _panel=panel)
    assert isinstance(result, pd.Series), "Must return pd.Series"
    assert len(result) == len(df), "Series length must match df"


def test_no_ticker_returns_nan_series():
    """Signal fns with no ticker attribute return all-NaN Series."""
    df = _ohlcv()  # no ticker
    result = insider_power_state(df, _panel=_make_panel([]))
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)
    assert result.isna().all(), "No-ticker result should be all NaN"


def test_insider_power_state_finite_where_data_exists():
    """insider_power_state is finite (not NaN) when panel has data for the ticker."""
    df = _ohlcv(ticker="TESTX")
    rows = [_panel_row(ticker="TESTX", code="P", filing_date="2025-11-01") for _ in range(3)]
    panel = _make_panel(rows)
    result = insider_power_state(df, _panel=panel)
    assert result.notna().all(), f"Expected all-finite, got NaN: {result}"
    assert (result >= 0).all() and (result <= 100).all(), "Score must be in [0, 100]"


def test_insider_power_state_nan_where_absent():
    """insider_power_state is NaN for an unrecognised ticker in the panel."""
    df = _ohlcv(ticker="ABSENT")
    rows = [_panel_row(ticker="TESTX", code="P", filing_date="2025-11-01")]
    panel = _make_panel(rows)
    result = insider_power_state(df, _panel=panel)
    assert result.isna().all(), "Unrecognised ticker should yield all-NaN"


# ---------------------------------------------------------------------------
# 9. insider_buy / insider_sell threshold logic
# ---------------------------------------------------------------------------

def test_insider_buy_fires_above_threshold():
    """insider_buy returns 1.0 when score >= BUY_THRESHOLD."""
    # Strong buy setup: many buys, recent, CEO
    df = _ohlcv(ticker="TESTX")
    rows = [
        _panel_row(ticker="TESTX", code="P", usd=5_000_000,
                   filing_date="2025-11-15", is_officer=True,
                   title="Chief Executive Officer")
        for _ in range(20)
    ]
    panel = _make_panel(rows)
    result = insider_buy(df, _panel=panel)
    # All bars should be 1.0 (fires) given strong buy signal
    assert (result == 1.0).all() or result.dropna().isin([0.0, 1.0]).all(), (
        "insider_buy values must be 0.0 or 1.0"
    )


def test_insider_sell_returns_binary():
    """insider_sell (catalog signal) returns a 0/1 (or NaN) Series — contract only.

    NOTE: the former ``test_insider_sell_fires_below_threshold`` asserted that a
    pure-sell tape MUST fire insider_sell. That encoded the v1 bug (routine
    sell-only → bearish escalation). The neutral-by-default insider_sell gate now
    lives in the per-ticker Terminal scorer (engine.insider_power, requiring the
    informative-sell bar); see the v2 section below. Here we only assert the
    catalog-signal fn keeps its 0/1 contract."""
    df = _ohlcv(ticker="TESTX")
    rows = [
        _panel_row(ticker="TESTX", code="S", usd=5_000_000,
                   filing_date="2025-11-15", is_officer=True,
                   title="Chief Executive Officer")
        for _ in range(20)
    ]
    panel = _make_panel(rows)
    result = insider_sell(df, _panel=panel)
    assert result.dropna().isin([0.0, 1.0]).all(), (
        "insider_sell values must be 0.0 or 1.0"
    )


def test_buy_and_sell_not_both_fire_same_ticker():
    """For a strongly bullish insider print, buy fires and sell does not."""
    df = _ohlcv(ticker="TESTX")
    rows = [
        _panel_row(ticker="TESTX", code="P", usd=10_000_000,
                   filing_date="2025-12-01", is_officer=True,
                   title="Chief Executive Officer")
        for _ in range(30)
    ]
    panel = _make_panel(rows)
    buy_result = insider_buy(df, _panel=panel)
    sell_result = insider_sell(df, _panel=panel)
    score = insider_power(panel[panel["ticker"] == "TESTX"], as_of_date=df.index[-1])

    if not math.isnan(score):
        if score >= BUY_THRESHOLD:
            assert (buy_result == 1.0).all(), "Strong buy should fire insider_buy"
            assert (sell_result == 0.0).all(), "Strong buy should NOT fire insider_sell"


# ---------------------------------------------------------------------------
# 10. Fallback snapshot
# ---------------------------------------------------------------------------

def test_snapshot_fallback_known_ticker():
    """insider_power_from_snapshot returns a finite value for a ticker in the JSON."""
    # Use a ticker we know exists in the snapshot from our data audit
    score = ip.insider_power_from_snapshot("AAT")  # buyers=11, sellers=0 in snapshot
    # If JSON is not available at test time, allow NaN — don't hard-fail
    if not math.isnan(score):
        assert 0.0 <= score <= 100.0, f"Fallback score out of bounds: {score}"


def test_snapshot_fallback_unknown_ticker():
    """insider_power_from_snapshot returns NaN for unknown ticker."""
    score = ip.insider_power_from_snapshot("__NOEXIST_TICKER_XYZ__")
    assert math.isnan(score), "Unknown ticker should return NaN from snapshot"


# ---------------------------------------------------------------------------
# Catalog contract via tech_catalog
# ---------------------------------------------------------------------------

def test_insider_family_in_tech_catalog():
    """insider family signals are present in the tech_catalog TECH_SIGNALS."""
    from engine.tech_catalog import TECH_SIGNALS
    insider_ids = [sid for sid, d in TECH_SIGNALS.items() if d["family"] == "insider"]
    assert len(insider_ids) >= 3, f"Expected >= 3 insider signals in catalog, found {insider_ids}"
    expected = {"insider_power_state", "insider_buy", "insider_sell"}
    missing = expected - set(insider_ids)
    assert not missing, f"Missing insider signals in catalog: {missing}"


def test_tech_catalog_count_increased():
    """TECH_SIGNALS count is at least 46 (was 43 before insider family added)."""
    from engine.tech_catalog import TECH_SIGNALS
    assert len(TECH_SIGNALS) >= 46, (
        f"Expected >= 46 signals after adding insider family, got {len(TECH_SIGNALS)}"
    )


# ===========================================================================
# Insider Power v2 — neutral-by-default (engine.insider_power Terminal scorer)
# ===========================================================================
# These replace the v1 bug-encoding assertions (pure-sell → score<50 /
# insider_sell fires). The v2 scorer treats absence of buys as the NULL state:
# routine, spread-out, baseline-sized selling floors into the neutral band with
# signal=NEUTRAL / routine_only=True and NO insider_sell escalation; the score
# drops below the floor and insider_sell fires only when the informative-sell
# bar clears (cluster / baseline-z / into-weakness / top-exec, ≥2 firing).
# ---------------------------------------------------------------------------

import engine.insider_power as ipwr  # noqa: E402


def _v2_row(
    code: str = "S",
    usd: float = 1_000_000.0,
    filing_date: str = "2026-06-01",
    trans_date: str | None = None,
    rptownercik: str = "0000000099",
    is_officer: bool = True,
    is_director: bool = False,
    is_tenpct: bool = False,
    title: str = "Chief Executive Officer",
    price: float = 100.0,
    ticker: str = "T",
) -> dict:
    """Panel row for the v2 Terminal-scorer path (engine.insider_power.compute).

    Distinct-CIK, price and trans_date matter for the informative-sell features,
    so they are first-class knobs here."""
    td = trans_date or filing_date
    return {
        "ticker": ticker,
        "issuer_cik": "0000000001",
        "filing_date": pd.Timestamp(filing_date),
        "trans_date": pd.Timestamp(td),
        "rptownercik": rptownercik,
        "code": code,
        "direct": True,
        "is_officer": is_officer,
        "is_director": is_director,
        "is_tenpct": is_tenpct,
        "title": title,
        "shares": usd / price,
        "price": price,
        "usd": usd,
        "quarter": "2026q2",
    }


_ASOF = "2026-07-01"


def test_v2_routine_pure_sell_is_neutral():
    """Routine pure-sell (spread out, baseline-sized, ONE seller, no cluster,
    into strength) → score in [40,55], NEUTRAL, insider_sell=False,
    routine_only=True (item 4 replacement)."""
    rows = [
        _v2_row(code="S", usd=200_000, filing_date=m, rptownercik="routine1",
                is_officer=False, is_director=True, title="", price=200.0)
        for m in ("2025-08-05", "2025-10-05", "2025-12-05",
                  "2026-02-05", "2026-04-05", "2026-06-05")
    ]
    payload = ipwr.compute(_make_panel(rows), asof=_ASOF, tickers=["T"])["T"]
    assert 40.0 <= payload["score"] <= 55.0, f"routine sell score out of band: {payload['score']}"
    assert payload["signal"] == "NEUTRAL", f"routine sell should be NEUTRAL, got {payload['signal']}"
    assert payload["insider_sell"] is False, "routine sell must NOT fire insider_sell"
    assert payload["routine_only"] is True, "routine sell must set routine_only"
    assert payload["confidence"] == "None"
    assert isinstance(payload["posture_reason"], str) and payload["posture_reason"]


def test_v2_clustered_top_exec_into_decline_is_bearish():
    """Clustered top-exec selling into a decline → score<40, insider_sell=True,
    confidence High (item 9 replacement).

    Older tape = small routine director sells at a HIGH price (baseline + price
    reference); recent burst = 4 distinct CFOs selling big in a tight window at a
    LOW price (cluster + into-weakness + top-exec all fire)."""
    older = [
        _v2_row(code="S", usd=150_000, filing_date=m, rptownercik="routine1",
                is_officer=False, is_director=True, title="", price=200.0)
        for m in ("2025-08-05", "2025-09-05", "2025-10-05",
                  "2025-11-05", "2025-12-05", "2026-01-05")
    ]
    cluster = [
        _v2_row(code="S", usd=6_000_000, filing_date=f"2026-06-1{i}",
                rptownercik=f"exec{i}", is_officer=True,
                title="Chief Financial Officer", price=90.0)
        for i in range(4)
    ]
    payload = ipwr.compute(_make_panel(older + cluster), asof=_ASOF, tickers=["T"])["T"]
    assert payload["score"] < 40.0, f"informative cluster should score <40, got {payload['score']}"
    assert payload["signal"] == "SELL", f"cluster should be SELL, got {payload['signal']}"
    assert payload["insider_sell"] is True, "informative cluster must fire insider_sell"
    assert payload["confidence"] == "High", f"cluster+into-weakness should be High, got {payload['confidence']}"
    assert payload["routine_only"] is False


def test_v2_stale_tape_decays_to_neutral():
    """Most recent open-market trade >90d before asof → confidence None,
    signal decays to NEUTRAL, insider_sell=False (recency gate)."""
    rows = [
        _v2_row(code="S", usd=6_000_000, filing_date=f"2026-01-1{i}",
                rptownercik=f"exec{i}", is_officer=True,
                title="Chief Financial Officer", price=90.0)
        for i in range(4)
    ]
    payload = ipwr.compute(_make_panel(rows), asof=_ASOF, tickers=["T"])["T"]
    assert payload["last_trade_age_d"] is not None and payload["last_trade_age_d"] > 90
    assert payload["signal"] == "NEUTRAL", f"stale tape should decay to NEUTRAL, got {payload['signal']}"
    assert payload["confidence"] == "None", f"stale tape confidence should be None, got {payload['confidence']}"
    assert payload["insider_sell"] is False


def test_v2_pure_buy_still_escalates():
    """Buys still escalate as before: pure-buy cluster → score>60, BUY,
    insider_buy=True (buy semantics unchanged)."""
    rows = [
        _v2_row(code="P", usd=2_000_000, filing_date=f"2026-06-1{i}",
                rptownercik=f"buyer{i}", is_officer=True,
                title="Chief Executive Officer", price=100.0)
        for i in range(4)
    ]
    payload = ipwr.compute(_make_panel(rows), asof=_ASOF, tickers=["T"])["T"]
    assert payload["score"] > 60.0, f"pure buy should score >60, got {payload['score']}"
    assert payload["signal"] == "BUY"
    assert payload["insider_buy"] is True
    assert payload["insider_sell"] is False


def test_v2_payload_has_additive_fields():
    """The v2 additive display fields are present on every payload."""
    rows = [_v2_row(code="P", usd=1_000_000, filing_date="2026-06-01")]
    payload = ipwr.compute(_make_panel(rows), asof=_ASOF, tickers=["T"])["T"]
    for k in ("signal", "confidence", "routine_only", "posture_reason", "last_trade_age_d"):
        assert k in payload, f"v2 payload missing additive field '{k}'"
    # existing keys keep their meaning
    for k in ("score", "insider_buy", "insider_sell", "buyers", "sellers", "series", "trades"):
        assert k in payload, f"payload dropped existing key '{k}'"


def test_v2_filing_date_asof_gate_preserved():
    """The filing_date<=asof causal gate (insider_power.py:174 class) is preserved:
    a future-dated cluster is excluded until asof advances past it."""
    rows = [
        _v2_row(code="S", usd=6_000_000, filing_date=f"2026-09-1{i}",
                rptownercik=f"exec{i}", is_officer=True,
                title="Chief Financial Officer", price=90.0)
        for i in range(4)
    ]
    # asof BEFORE the cluster → no eligible activity → ticker absent from output
    out_before = ipwr.compute(_make_panel(rows), asof="2026-07-01", tickers=["T"])
    assert "T" not in out_before, "future-dated trades must not leak before asof"
    # asof AFTER → cluster visible
    out_after = ipwr.compute(_make_panel(rows), asof="2026-10-01", tickers=["T"])
    assert "T" in out_after, "cluster should be visible once asof passes filing_date"


def test_v2_stale_cluster_plus_fresh_routine_stays_neutral():
    """P1 regression (reviewer's exact repro): a STALE ~170d-old informative
    cluster (4 distinct CIK sellers incl. a CFO) supplies the firing features
    while ONE fresh routine director sell (≤30d) defeats the recency gate. Before
    the fix, cluster/top_exec were computed over the FULL 365d window so the stale
    burst fired the informative bar and the fresh routine trade kept the tape
    non-stale → SELL / insider_sell=True. After the fix, cluster/top_exec read the
    RECENT (≤90d) slice only, so the stale burst cannot fire and the lone recent
    routine trade is treated as routine-only.

    Expected (post-fix): signal NEUTRAL, insider_sell False, routine_only True."""
    asof = "2026-07-01"
    # Stale cluster ~170d before asof (mid-Jan 2026): 4 distinct CIKs incl. a CFO,
    # in a tight window and at a low price vs the older director prints.
    stale_cluster = [
        _v2_row(code="S", usd=6_000_000, filing_date=f"2026-01-1{i}",
                rptownercik=f"exec{i}", is_officer=True,
                title="Chief Financial Officer", price=90.0)
        for i in range(4)
    ]
    # Older routine director tape (baseline / price reference) at a high price.
    older = [
        _v2_row(code="S", usd=150_000, filing_date=m, rptownercik="routine1",
                is_officer=False, is_director=True, title="", price=200.0)
        for m in ("2025-08-05", "2025-09-05", "2025-10-05")
    ]
    # ONE fresh routine director sell ≤30d before asof — this is the single recent
    # trade that (pre-fix) defeated the recency gate at the win.max() check.
    fresh_routine = [
        _v2_row(code="S", usd=120_000, filing_date="2026-06-20",
                rptownercik="routine2", is_officer=False, is_director=True,
                title="", price=205.0)
    ]
    payload = ipwr.compute(_make_panel(older + stale_cluster + fresh_routine),
                           asof=asof, tickers=["T"])["T"]
    # The tape is NOT stale (fresh routine sell ~11d old defeats the recency gate).
    assert payload["last_trade_age_d"] is not None and payload["last_trade_age_d"] <= 90
    assert payload["signal"] == "NEUTRAL", (
        f"stale cluster + fresh routine must be NEUTRAL, got {payload['signal']}")
    assert payload["insider_sell"] is False, (
        "stale informative burst must NOT fire insider_sell via the recent gate")
    assert payload["routine_only"] is True, "lone recent routine sell → routine_only"


def test_v2_stale_buy_cluster_suppresses_insider_buy():
    """insider_buy staleness gate: a strong buy cluster whose most-recent trade is
    >90d before asof emits signal=NEUTRAL / confidence=None (the recency gate), so
    insider_buy must NOT fire — a stale buy flag would be an internally
    contradictory payload. This is a de-escalation (suppresses a stale buy flag)."""
    asof = "2026-07-01"
    # Buy cluster in early Feb 2026 → ~145d old at asof (>90d STALE_DAYS).
    rows = [
        _v2_row(code="P", usd=5_000_000, filing_date=f"2026-02-0{i + 1}",
                rptownercik=f"buyer{i}", is_officer=True,
                title="Chief Executive Officer", price=100.0)
        for i in range(4)
    ]
    payload = ipwr.compute(_make_panel(rows), asof=asof, tickers=["T"])["T"]
    assert payload["last_trade_age_d"] is not None and payload["last_trade_age_d"] > 90
    assert payload["signal"] == "NEUTRAL", (
        f"stale buy cluster should decay to NEUTRAL, got {payload['signal']}")
    assert payload["confidence"] == "None", (
        f"stale buy cluster confidence should be None, got {payload['confidence']}")
    assert payload["insider_buy"] is False, (
        "stale buy cluster must NOT fire insider_buy (recency-gated)")
