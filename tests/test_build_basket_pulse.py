"""Unit tests for scripts/build_basket_pulse.py — FTR W2b/c.

Tests use entirely synthetic quotes + membership fixtures; no network calls,
no data/ reads (except cum_2d which uses a monkeypatched parquet).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import build_basket_pulse as bp


# ── shared helpers ─────────────────────────────────────────────────────────────

def _now_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _make_quote(chg: float, age_min: float = 1.0, prev: float = 100.0,
                now: datetime | None = None, delay_min: float | None = None) -> dict:
    """Synthesise a Worker-contract quote dict.

    delay_min: explicit data-provider delay (mirrors the delayMin field that the
    real quotes worker writes). If None, defaults to age_min so that the synthetic
    quote's apparent staleness matches the intended test scenario.
    build_basket_pulse uses delayMin preferentially over (now - ts) arithmetic.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    ts_ms = int(now.timestamp() * 1000) - int(age_min * 60_000)
    price = prev * (1 + chg / 100)
    return {
        "price": round(price, 4),
        "ts": ts_ms,
        "source": "test",
        "basis": "regular",
        "prevClose": prev,
        "changePct": round(chg, 4),
        "currency": "USD",
        "delayMin": delay_min if delay_min is not None else age_min,
    }


def _make_quotes(tickers_chg: dict[str, float], now: datetime, age_min: float = 1.0) -> dict:
    """Build a quotes dict from {ticker: changePct}."""
    return {tk: _make_quote(chg, age_min=age_min, now=now)
            for tk, chg in tickers_chg.items()}


def _make_membership(baskets: dict[str, list[str]]) -> dict:
    """Build a minimal baskets dict from {id: [ticker, ...]}."""
    out = {}
    for bid, tickers in baskets.items():
        out[bid] = {
            "name": bid,
            "members": [{"ticker": t, "removed": None} for t in tickers],
        }
    return out


# ── session flag tests ─────────────────────────────────────────────────────────

class TestSessionFlag:
    """_et_session returns the correct session label."""

    def _utc(self, hour: int, minute: int = 0) -> datetime:
        """A Wednesday (trading day) in ET summer (UTC-4)."""
        # 2026-07-08 is a Wednesday
        return datetime(2026, 7, 8, hour, minute, tzinfo=timezone.utc)

    def test_premarket(self):
        # 11:00 UTC = 07:00 ET — premarket
        assert bp._et_session(self._utc(11, 0)) == "pre"

    def test_rth_open(self):
        # 13:30 UTC = 09:30 ET — RTH open
        assert bp._et_session(self._utc(13, 30)) == "rth"

    def test_rth_mid(self):
        # 17:00 UTC = 13:00 ET — mid-day RTH
        assert bp._et_session(self._utc(17, 0)) == "rth"

    def test_post_close(self):
        # 21:00 UTC = 17:00 ET — after-hours (post)
        # Note: 20:00 ET + is "closed"; 16:00–20:00 ET is "post"
        # 20:00 UTC = 16:00 ET = RTH close exact → post starts
        assert bp._et_session(self._utc(20, 1)) == "post"

    def test_closed_before_premarket(self):
        # 07:00 UTC = 03:00 ET — closed (before 04:00 ET premarket open)
        assert bp._et_session(self._utc(7, 0)) == "closed"

    def test_closed_after_afterhours(self):
        # 01:00 UTC = 21:00 ET prior day — closed
        assert bp._et_session(self._utc(1, 0)) == "closed"

    def test_weekend_is_closed(self):
        # 2026-07-11 is a Saturday
        sat = datetime(2026, 7, 11, 15, 0, tzinfo=timezone.utc)
        assert bp._et_session(sat) == "closed"


# ── EW computation tests ───────────────────────────────────────────────────────

class TestEwChg:
    """Equal-weight average computation + coverage rules."""

    def test_ew_math_basic(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = _make_quotes({"A": 2.0, "B": 4.0, "C": 6.0}, now)
        ew, n_q, n_m, stale = bp._ew_chg(["A", "B", "C"], qs, _now_ms(now))
        assert ew == pytest.approx(4.0, abs=0.01)
        assert n_q == 3 and n_m == 3 and stale is False

    def test_coverage_below_30pct_returns_null(self):
        """A basket with 16 members but only 4 quoted (25%) → null EW."""
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        tickers = [f"T{i:02d}" for i in range(16)]
        # Only 4 quoted
        qs = _make_quotes({t: 1.0 for t in tickers[:4]}, now)
        ew, n_q, n_m, _ = bp._ew_chg(tickers, qs, _now_ms(now))
        assert ew is None, "coverage 4/16=25% < 30% must return None"
        assert n_q == 4 and n_m == 16

    def test_stale_quotes_excluded_from_ew(self):
        """Quotes older than stale_min are excluded from the EW average."""
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        # 3 fresh quotes at +4%, 2 stale at +100% — stale should be excluded
        fresh = _make_quotes({"A": 4.0, "B": 4.0, "C": 4.0}, now, age_min=1.0)
        stale = _make_quotes({"D": 100.0, "E": 100.0}, now, age_min=25.0)
        qs = {**fresh, **stale}
        tickers = ["A", "B", "C", "D", "E"]
        ew, n_q, n_m, any_stale = bp._ew_chg(tickers, qs, _now_ms(now), stale_min=20)
        # EW uses only fresh quotes [4.0, 4.0, 4.0]
        assert ew == pytest.approx(4.0, abs=0.01)
        assert any_stale is True
        assert n_q == 5   # both stale and fresh are counted in n_quoted

    def test_no_quotes_returns_null(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        ew, n_q, n_m, _ = bp._ew_chg(["X", "Y", "Z"], {}, _now_ms(now))
        assert ew is None
        assert n_q == 0 and n_m == 3

    def test_coverage_exactly_at_30pct_threshold(self):
        """Exactly 30% coverage = at the boundary → should return a value."""
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        # 3 out of 10 = 30%
        tickers = [f"T{i}" for i in range(10)]
        qs = _make_quotes({t: 2.0 for t in tickers[:3]}, now)
        ew, _, _, _ = bp._ew_chg(tickers, qs, _now_ms(now))
        # Exactly 0.30 is not < 0.30 so it should compute
        assert ew is not None


# ── tape rank tests ────────────────────────────────────────────────────────────

class TestTapeRanks:
    """Cross-sectional rank: 1=weakest, N=strongest."""

    def test_rank_ordering(self):
        data = [
            {"id": "A", "live_ew_chg_pct": -1.0},
            {"id": "B", "live_ew_chg_pct": 0.5},
            {"id": "C", "live_ew_chg_pct": 2.0},
        ]
        ranks = bp._tape_ranks(data)
        assert ranks["A"] == 1  # weakest
        assert ranks["B"] == 2
        assert ranks["C"] == 3  # strongest

    def test_null_live_ew_gets_none_rank(self):
        data = [
            {"id": "A", "live_ew_chg_pct": 1.0},
            {"id": "B", "live_ew_chg_pct": None},
        ]
        ranks = bp._tape_ranks(data)
        assert ranks["A"] == 1
        assert ranks["B"] is None

    def test_all_null_returns_none_ranks(self):
        data = [
            {"id": "X", "live_ew_chg_pct": None},
            {"id": "Y", "live_ew_chg_pct": None},
        ]
        ranks = bp._tape_ranks(data)
        assert all(v is None for v in ranks.values())


# ── shock-day relative bid gating tests ───────────────────────────────────────

class TestShockDayRelativeBid:
    """FT-R3: populated ONLY when oil_shock/geopolitical primary AND index down."""

    def _baskets_data(self, chg: float = 1.0) -> list[dict]:
        return [{"id": "test_basket", "live_ew_chg_pct": chg}]

    def test_populated_when_oil_shock_and_index_down(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {
            "SPY": _make_quote(-1.5, now=now),
            "XLK": _make_quote(2.0, now=now),
        }
        md = {"primary": "oil_shock", "family": "inflation"}
        result = bp._shock_day_relative_bid(md, self._baskets_data(1.0), qs, _now_ms(now))
        assert result is not None
        assert result["active_driver"] == "oil_shock"
        assert result["index_chg_pct"] < 0
        assert result["t1_fade_note"] == bp._T1_FADE_NOTE
        # NO beneficiary/casualty/direction fields (FT-R3)
        assert "beneficiary" not in result
        assert "casualty" not in result
        assert "direction" not in result

    def test_not_populated_when_index_up(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {"SPY": _make_quote(+0.5, now=now)}
        md = {"primary": "oil_shock", "family": "inflation"}
        result = bp._shock_day_relative_bid(md, self._baskets_data(), qs, _now_ms(now))
        assert result is None

    def test_not_populated_when_wrong_driver(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {"SPY": _make_quote(-1.0, now=now)}
        md = {"primary": "ai_semis", "family": "equity-leadership"}
        result = bp._shock_day_relative_bid(md, self._baskets_data(), qs, _now_ms(now))
        assert result is None

    def test_not_populated_when_no_market_drivers(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {"SPY": _make_quote(-1.0, now=now)}
        result = bp._shock_day_relative_bid(None, self._baskets_data(), qs, _now_ms(now))
        assert result is None

    def test_populated_when_geopolitical_family(self):
        """Geopolitical family (future driver) also gates the shock readout."""
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {"SPY": _make_quote(-2.0, now=now)}
        md = {"primary": "geopolitical_risk", "family": "geopolitical"}
        result = bp._shock_day_relative_bid(md, self._baskets_data(1.5), qs, _now_ms(now))
        assert result is not None
        assert result["active_driver"] == "geopolitical_risk"

    def test_rows_descriptive_only_no_ranking_field(self):
        """Rows carry id + live_ew_chg_pct; no beneficiary ranking."""
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {"SPY": _make_quote(-1.0, now=now)}
        md = {"primary": "oil_shock", "family": "inflation"}
        bdata = [
            {"id": "energy_complex", "live_ew_chg_pct": 2.5},
            {"id": "defensives", "live_ew_chg_pct": -0.3},
        ]
        result = bp._shock_day_relative_bid(md, bdata, qs, _now_ms(now))
        assert result is not None
        for row in result["rows"]:
            assert set(row.keys()) == {"id", "live_ew_chg_pct"}


# ── offense/defense spread tests ──────────────────────────────────────────────

class TestOdSpread:
    """od_spread_print = EW(defense) - EW(offense); None when any missing/stale."""

    def test_spread_math(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {
            "XLP": _make_quote(1.0, now=now),
            "XLU": _make_quote(2.0, now=now),
            "XLV": _make_quote(3.0, now=now),
            "SMH": _make_quote(-1.0, now=now),
            "XLK": _make_quote(1.0, now=now),
        }
        spread = bp._od_spread(qs, _now_ms(now))
        # defense avg = (1+2+3)/3 = 2.0; offense avg = (-1+1)/2 = 0.0; spread = 2.0
        assert spread == pytest.approx(2.0, abs=0.01)

    def test_returns_none_when_etf_missing(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {
            "XLP": _make_quote(1.0, now=now),
            # XLU and XLV missing
            "SMH": _make_quote(1.0, now=now),
            "XLK": _make_quote(1.0, now=now),
        }
        assert bp._od_spread(qs, _now_ms(now)) is None

    def test_returns_none_when_etf_stale(self):
        now = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
        qs = {
            "XLP": _make_quote(1.0, age_min=25.0, now=now),  # stale
            "XLU": _make_quote(1.0, now=now),
            "XLV": _make_quote(1.0, now=now),
            "SMH": _make_quote(1.0, now=now),
            "XLK": _make_quote(1.0, now=now),
        }
        assert bp._od_spread(qs, _now_ms(now), stale_min=20) is None


# ── full build integration tests ───────────────────────────────────────────────

class TestBuild:
    """Integration tests using synthetic fixtures (no data/ reads for memberships)."""

    def _synthetic_membership(self, tmp_path: Path) -> Path:
        m = {
            "version": "test",
            "baskets": _make_membership({
                "basket_a": ["AA", "AB", "AC"],
                "basket_b": ["BA", "BB", "BC", "BD", "BD2", "BD3", "BD4"],
            }),
        }
        p = tmp_path / "membership.json"
        p.write_text(json.dumps(m))
        return p

    def test_build_emits_required_schema_keys(self, tmp_path, monkeypatch):
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)  # 10:00 ET = RTH
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, now=now),
            "AB": _make_quote(2.0, now=now),
            "AC": _make_quote(3.0, now=now),
            "BA": _make_quote(-1.0, now=now),
            "BB": _make_quote(-2.0, now=now),
            "BC": _make_quote(-3.0, now=now),
            "BD": _make_quote(0.5, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        # monkeypatch cum_2d to avoid reading parquet
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(
            quotes_path=qs_path,
            membership_path=mem_path,
            now=now,
        )

        assert result["schema"] == "basket_pulse.v1"
        assert result["session"] == "rth"
        assert "as_of_utc" in result
        assert "built" in result
        assert isinstance(result["coverage_pct"], float)
        assert isinstance(result["baskets"], list)
        assert len(result["baskets"]) == 2

    def test_basket_ew_and_rank_computed(self, tmp_path, monkeypatch):
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(3.0, now=now),
            "AB": _make_quote(3.0, now=now),
            "AC": _make_quote(3.0, now=now),
            "BA": _make_quote(-1.0, now=now),
            "BB": _make_quote(-1.0, now=now),
            "BC": _make_quote(-1.0, now=now),
            "BD": _make_quote(-1.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        baskets = {b["id"]: b for b in result["baskets"]}

        # basket_a: EW = 3.0; basket_b: EW = -1.0
        assert baskets["basket_a"]["live_ew_chg_pct"] == pytest.approx(3.0, abs=0.01)
        assert baskets["basket_b"]["live_ew_chg_pct"] == pytest.approx(-1.0, abs=0.01)

        # basket_b is weaker → rank 1; basket_a is stronger → rank 2
        assert baskets["basket_b"]["tape_rank"] == 1
        assert baskets["basket_a"]["tape_rank"] == 2

    def test_low_coverage_basket_has_null_ew(self, tmp_path, monkeypatch):
        """A basket with only 1 out of 10 members quoted (<30%) → null EW."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        tickers_10 = [f"M{i:02d}" for i in range(10)]
        qs = {"quotes": {tickers_10[0]: _make_quote(5.0, now=now)}}  # only 1 quoted
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps(qs))

        mem = {"version": "t", "baskets": _make_membership({"big_basket": tickers_10})}
        mem_path = tmp_path / "membership.json"
        mem_path.write_text(json.dumps(mem))
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        b = result["baskets"][0]
        assert b["live_ew_chg_pct"] is None, "coverage 1/10=10% should return null"
        assert b["tape_rank"] is None

    def test_premarket_session_flag(self, tmp_path, monkeypatch):
        """11:00 UTC = 07:00 ET → session = 'pre'."""
        now = datetime(2026, 7, 8, 11, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text('{"quotes":{}}')
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        assert result["session"] == "pre"

    def test_shock_day_relative_bid_gated(self, tmp_path, monkeypatch, tmp_path_factory):
        """shock_day_relative_bid populated when oil_shock + SPY down."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, now=now),
            "AB": _make_quote(1.0, now=now),
            "AC": _make_quote(1.0, now=now),
            "SPY": _make_quote(-1.5, now=now),
        }}))
        drivers = {"primary": "oil_shock", "family": "inflation", "verdict": "clear"}
        drivers_path = tmp_path / "market_drivers.json"
        drivers_path.write_text(json.dumps(drivers))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(
            quotes_path=qs_path,
            membership_path=mem_path,
            drivers_path=drivers_path,
            now=now,
        )
        sdr = result["shock_day_relative_bid"]
        assert sdr is not None
        assert sdr["active_driver"] == "oil_shock"
        assert sdr["index_chg_pct"] < 0
        assert sdr["t1_fade_note"] == bp._T1_FADE_NOTE
        # FT-R3: no direction/beneficiary/casualty
        assert "beneficiary" not in sdr
        assert "direction" not in sdr

    def test_shock_day_not_populated_when_index_flat(self, tmp_path, monkeypatch):
        """shock_day_relative_bid = null when SPY not down."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, now=now),
            "AB": _make_quote(1.0, now=now),
            "AC": _make_quote(1.0, now=now),
            "SPY": _make_quote(+0.3, now=now),  # UP
        }}))
        drivers_path = tmp_path / "market_drivers.json"
        drivers_path.write_text(json.dumps({"primary": "oil_shock", "family": "inflation"}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(
            quotes_path=qs_path,
            membership_path=mem_path,
            drivers_path=drivers_path,
            now=now,
        )
        assert result["shock_day_relative_bid"] is None

    def test_empty_quotes_produces_valid_output(self, tmp_path, monkeypatch):
        """No quotes → coverage 0%, all live_ew_chg_pct null, still a valid JSON."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text('{"quotes":{}}')
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        # JSON serializable (allow_nan=False contract)
        raw = json.dumps(result, allow_nan=False)
        assert "NaN" not in raw
        for b in result["baskets"]:
            assert b["live_ew_chg_pct"] is None

    def test_output_is_nan_safe(self, tmp_path, monkeypatch):
        """Output must be serializable with allow_nan=False."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text('{"quotes":{}}')
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        # Must not raise
        json.dumps(result, allow_nan=False)

    def test_build_emits_new_schema_fields(self, tmp_path, monkeypatch):
        """TS-R1: build result includes mode, delay_min_median, as_of_quotes."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)  # RTH
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, now=now),
            "AB": _make_quote(1.0, now=now),
            "AC": _make_quote(1.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        assert "mode" in result
        assert "delay_min_median" in result
        assert "as_of_quotes" in result


# ── graded-mode tests (TS-R1) ──────────────────────────────────────────────────

class TestGradedModes:
    """TS-R1: live, delayed, last_rth, eod modes.

    Fixtures use the real pathology: 238-min delays, post-session.
    """

    def _synthetic_membership(self, tmp_path: Path) -> Path:
        m = {
            "version": "test",
            "baskets": _make_membership({
                "basket_a": ["AA", "AB", "AC"],
                "basket_b": ["BA", "BB"],
            }),
        }
        p = tmp_path / "membership.json"
        p.write_text(json.dumps(m))
        return p

    # RTH, fresh quotes → live mode
    def test_live_mode_rth_fresh_quotes(self, tmp_path, monkeypatch):
        """Fresh quotes during RTH → mode=live, values computed."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)  # 10:00 ET RTH
        qs_path = tmp_path / "quotes.json"
        # All quotes fresh (delayMin=1 via default age_min=1)
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(2.0, now=now),
            "AB": _make_quote(2.0, now=now),
            "AC": _make_quote(2.0, now=now),
            "BA": _make_quote(-1.0, now=now),
            "BB": _make_quote(-1.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        assert result["mode"] == bp.MODE_LIVE
        assert result["session"] == "rth"
        baskets = {b["id"]: b for b in result["baskets"]}
        assert baskets["basket_a"]["live_ew_chg_pct"] == pytest.approx(2.0, abs=0.01)
        assert baskets["basket_b"]["live_ew_chg_pct"] == pytest.approx(-1.0, abs=0.01)
        assert result["delay_min_median"] is not None

    # RTH, delayed quotes (238-min delay, real-world Polygon pathology) → delayed mode
    def test_delayed_mode_rth_238min_delay(self, tmp_path, monkeypatch):
        """Delayed quotes during RTH (238-min data-provider delay) → mode=delayed,
        values computed anyway (honest-delay law), delay_min_median populated."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)  # 10:00 ET RTH
        qs_path = tmp_path / "quotes.json"
        # Simulate 238-min Polygon free-tier delay
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(3.0, age_min=238.0, now=now),
            "AB": _make_quote(3.0, age_min=238.0, now=now),
            "AC": _make_quote(3.0, age_min=238.0, now=now),
            "BA": _make_quote(-2.0, age_min=238.0, now=now),
            "BB": _make_quote(-2.0, age_min=238.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        assert result["mode"] == bp.MODE_DELAYED, (
            "Quotes with 238-min delay must yield mode=delayed, not null")
        # Values MUST be computed (honest-delay law: delayed value beats null)
        baskets = {b["id"]: b for b in result["baskets"]}
        assert baskets["basket_a"]["live_ew_chg_pct"] is not None, (
            "Delayed mode must compute EW from delayed quotes, not null")
        assert baskets["basket_a"]["live_ew_chg_pct"] == pytest.approx(3.0, abs=0.01)
        assert baskets["basket_b"]["live_ew_chg_pct"] == pytest.approx(-2.0, abs=0.01)
        assert result["delay_min_median"] == pytest.approx(238.0, abs=1.0)

    # Post-session + no quotes + no lastgood → eod mode
    def test_eod_mode_post_session_no_quotes_no_sidecar(self, tmp_path, monkeypatch):
        """Post-session, no quotes, no lastgood sidecar → mode=eod.
        eod_basket_chg called; no crash on missing parquet."""
        # 21:00 UTC = 17:00 ET → closed
        now = datetime(2026, 7, 8, 21, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text('{"quotes":{}}')
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)
        # No parquet files → eod_basket_chg returns None gracefully
        monkeypatch.setattr(bp, "_eod_basket_chg", lambda bid, mems: (None, None))

        result = bp.build(
            quotes_path=qs_path, membership_path=mem_path, now=now,
            out_dir=tmp_path,  # no sidecar present → eod
        )
        assert result["mode"] == bp.MODE_EOD
        json.dumps(result, allow_nan=False)  # NaN-safe contract

    # Post-session + valid sidecar → last_rth mode
    def test_last_rth_mode_with_sidecar(self, tmp_path, monkeypatch):
        """Post-session with a lastgood sidecar → mode=last_rth, original values served."""
        # Create a fake lastgood sidecar
        lastgood = {
            "schema": "basket_pulse.v1",
            "as_of_utc": "2026-07-08T20:00:00+00:00",
            "as_of_quotes": "2026-07-08T20:00:00+00:00",
            "built": "2026-07-08 20:00:00 UTC",
            "session": "rth",
            "mode": bp.MODE_DELAYED,
            "delay_min_median": 238.0,
            "coverage_pct": 99.5,
            "quotes_source": None,
            "n_quotes_total": 5,
            "stale_min": 20,
            "baskets": [
                {"id": "basket_a", "n_members": 3, "n_quoted": 3,
                 "live_ew_chg_pct": 2.5, "cum_2d_pct": None, "tape_rank": 2,
                 "stale": True, "delay_min": 238.0},
                {"id": "basket_b", "n_members": 2, "n_quoted": 2,
                 "live_ew_chg_pct": -1.0, "cum_2d_pct": None, "tape_rank": 1,
                 "stale": True, "delay_min": 238.0},
            ],
            "od_spread_print": None,
            "shock_day_relative_bid": None,
            "complexes": [],
        }
        sidecar_path = tmp_path / bp.LASTGOOD_FILENAME
        sidecar_path.write_text(json.dumps(lastgood))

        # Now build in post-session
        now = datetime(2026, 7, 8, 21, 0, tzinfo=timezone.utc)  # 17:00 ET post
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text('{"quotes":{}}')
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(
            quotes_path=qs_path, membership_path=mem_path, now=now,
            out_dir=tmp_path,
        )
        assert result["mode"] == bp.MODE_LAST_RTH
        # Values from sidecar are preserved
        baskets = {b["id"]: b for b in result["baskets"]}
        assert baskets["basket_a"]["live_ew_chg_pct"] == pytest.approx(2.5, abs=0.01)
        assert result["session"] == "post"  # current session
        assert result["delay_min_median"] == pytest.approx(238.0, abs=1.0)
        json.dumps(result, allow_nan=False)

    # Lastgood sidecar is saved on live/delayed compute
    def test_lastgood_sidecar_saved_on_live_compute(self, tmp_path, monkeypatch):
        """Successful live build writes basket_pulse_lastgood.json."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)  # RTH
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, now=now),
            "AB": _make_quote(1.0, now=now),
            "AC": _make_quote(1.0, now=now),
            "BA": _make_quote(-1.0, now=now),
            "BB": _make_quote(-1.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(
            quotes_path=qs_path, membership_path=mem_path, now=now,
            out_dir=tmp_path,
        )
        sidecar = tmp_path / bp.LASTGOOD_FILENAME
        assert sidecar.exists(), "lastgood sidecar must be written on live build"
        saved = json.loads(sidecar.read_text())
        assert saved["mode"] in (bp.MODE_LIVE, bp.MODE_DELAYED)
        assert saved["coverage_pct"] > 0

    # Mode=delayed: per-basket delay_min field is populated
    def test_delayed_mode_per_basket_delay_min(self, tmp_path, monkeypatch):
        """In delayed mode, each basket row has a delay_min field."""
        now = datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)
        qs_path = tmp_path / "quotes.json"
        qs_path.write_text(json.dumps({"quotes": {
            "AA": _make_quote(1.0, age_min=193.0, now=now),
            "AB": _make_quote(1.0, age_min=193.0, now=now),
            "AC": _make_quote(1.0, age_min=193.0, now=now),
            "BA": _make_quote(-1.0, age_min=155.0, now=now),
            "BB": _make_quote(-1.0, age_min=155.0, now=now),
        }}))
        mem_path = self._synthetic_membership(tmp_path)
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)

        result = bp.build(quotes_path=qs_path, membership_path=mem_path, now=now)
        assert result["mode"] == bp.MODE_DELAYED
        for b in result["baskets"]:
            assert b.get("delay_min") is not None, (
                f"basket {b['id']} missing delay_min in delayed mode")

    # NaN-safe output for all modes
    def test_all_modes_nan_safe(self, tmp_path, monkeypatch):
        """All build paths produce allow_nan=False safe JSON."""
        monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)
        monkeypatch.setattr(bp, "_eod_basket_chg", lambda bid, mems: (None, None))
        mem_path = self._synthetic_membership(tmp_path)

        for label, qs_content, dt, extra in [
            ("live", json.dumps({"quotes": {
                "AA": _make_quote(1.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
                "AB": _make_quote(1.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
                "AC": _make_quote(1.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
            }}), datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc), {}),
            ("delayed", json.dumps({"quotes": {
                "AA": _make_quote(1.0, age_min=238.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
                "AB": _make_quote(1.0, age_min=238.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
                "AC": _make_quote(1.0, age_min=238.0, now=datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc)),
            }}), datetime(2026, 7, 8, 14, 0, tzinfo=timezone.utc), {}),
            ("eod", '{"quotes":{}}', datetime(2026, 7, 8, 21, 0, tzinfo=timezone.utc),
             {"out_dir": tmp_path}),
        ]:
            qs_path = tmp_path / f"quotes_{label}.json"
            qs_path.write_text(qs_content)
            result = bp.build(
                quotes_path=qs_path, membership_path=mem_path, now=dt, **extra)
            try:
                json.dumps(result, allow_nan=False)
            except Exception as e:
                raise AssertionError(f"mode={label}: NaN in output: {e}") from e
