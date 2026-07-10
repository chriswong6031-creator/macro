"""TS-U5 settled-close tape — settle-basis filter, recompute, day-flow attach.

Companion to tests/test_build_basket_pulse.py (TS-U0 graded modes). All clock
fixtures use 2026-07-09, a Thursday NYSE session (EDT: 16:00 ET = 20:00 UTC).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts import build_basket_pulse as bp

_CLOSE = datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc)       # 16:00 ET
_CLOSE_MS = int(_CLOSE.timestamp() * 1000)
_POST_TICK = datetime(2026, 7, 9, 20, 35, tzinfo=timezone.utc)  # 16:35 ET
_SATURDAY = datetime(2026, 7, 11, 15, 0, tzinfo=timezone.utc)


def _q(chg: float, *, basis: str = "regular", ts_ms: int | None = _CLOSE_MS,
       prev: float = 100.0) -> dict:
    price = prev * (1 + chg / 100)
    return {"price": round(price, 4), "ts": ts_ms, "source": "test", "basis": basis,
            "prevClose": prev, "changePct": round(chg, 4), "currency": "USD",
            "delayMin": 5.0}


def _quotes_file(tmp_path, quotes: dict) -> object:
    p = tmp_path / "quotes.json"
    p.write_text(json.dumps({"quotes": quotes}))
    return p


def _membership_file(tmp_path, baskets: dict[str, list[str]]) -> object:
    out = {bid: {"name": bid,
                 "members": [{"ticker": t, "removed": None} for t in ts]}
           for bid, ts in baskets.items()}
    p = tmp_path / "membership.json"
    p.write_text(json.dumps({"baskets": out}))
    return p


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setattr(bp, "_cum_2d", lambda bid, chg: None)
    # the fastpath workflow exports LIVE_QUOTES_PATH — it must never leak into
    # these tests (_load_quotes prefers it over quotes_path candidates)
    monkeypatch.delenv("LIVE_QUOTES_PATH", raising=False)


class TestSettleFilter:
    def test_regular_at_bell_accepted(self):
        assert bp._settle_quote_ok(_q(1.0), _CLOSE_MS) is True

    def test_regular_intraday_print_rejected(self):
        # delayed feed can show a 15:40 ET 'regular' print at 16:05 — not the settle
        early = _CLOSE_MS - 20 * 60_000
        assert bp._settle_quote_ok(_q(1.0, ts_ms=early), _CLOSE_MS) is False

    def test_day_basis_accepted(self):
        assert bp._settle_quote_ok(_q(1.0, basis="day", ts_ms=None), _CLOSE_MS) is True

    def test_close_auction_trade_accepted(self):
        bell = _CLOSE_MS + 30_000
        assert bp._settle_quote_ok(_q(1.0, basis="trade", ts_ms=bell), _CLOSE_MS) is True

    def test_after_hours_prints_rejected(self):
        ah = _CLOSE_MS + 90 * 60_000
        assert bp._settle_quote_ok(_q(1.0, basis="minute", ts_ms=ah), _CLOSE_MS) is False
        assert bp._settle_quote_ok(_q(1.0, basis="trade", ts_ms=ah), _CLOSE_MS) is False

    def test_pre_close_stale_trade_rejected(self):
        # a ~15:45 ET delayed print IS the frozen-tape problem — never the settle
        stale = _CLOSE_MS - 15 * 60_000
        assert bp._settle_quote_ok(_q(1.0, basis="trade", ts_ms=stale), _CLOSE_MS) is False
        assert bp._settle_quote_ok(_q(1.0, basis="minute", ts_ms=stale), _CLOSE_MS) is False

    def test_prev_basis_rejected(self):
        assert bp._settle_quote_ok(_q(0.0, basis="prev", ts_ms=None), _CLOSE_MS) is False


class TestSettledClose:
    def test_settled_recompute_on_post_tick(self, tmp_path):
        qs = {"AAA": _q(1.0), "BBB": _q(2.0), "CCC": _q(-3.0)}
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_POST_TICK, out_dir=tmp_path)
        assert res["mode"] == bp.MODE_LAST_RTH
        assert res["settled_close"] is True
        assert res["session_date"] == "2026-07-09"
        assert res["baskets"][0]["live_ew_chg_pct"] == pytest.approx(0.0, abs=0.01)
        assert res["baskets"][0]["tape_rank"] == 1
        assert res["baskets"][0]["stale"] is False
        # sidecar persisted (weekend serving picks up the settled state)
        side = json.loads((tmp_path / bp.LASTGOOD_FILENAME).read_text())
        assert side.get("settled_close") is True

    def test_ah_contaminated_snapshot_not_claimed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bp, "_eod_basket_chg", lambda bid, mems: (None, None))
        ah = _CLOSE_MS + 90 * 60_000
        qs = {"AAA": _q(1.0, basis="minute", ts_ms=ah),
              "BBB": _q(2.0, basis="trade", ts_ms=ah),
              "CCC": _q(-3.0, basis="minute", ts_ms=ah)}
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_POST_TICK, out_dir=tmp_path)
        assert res.get("settled_close") is not True
        assert res["mode"] == bp.MODE_EOD  # no sidecar -> eod fall-through

    def test_mixed_sources_above_threshold(self, tmp_path):
        ah = _CLOSE_MS + 90 * 60_000
        qs = {"AAA": _q(1.0), "BBB": _q(3.0),                       # settle-clean
              "CCC": _q(-9.0, basis="minute", ts_ms=ah)}            # AH drift
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_POST_TICK, out_dir=tmp_path)
        # 2/3 settle-basis >= 0.60 -> claimed; EW over the clean two only
        assert res["settled_close"] is True
        assert res["baskets"][0]["live_ew_chg_pct"] == pytest.approx(2.0, abs=0.01)

    def test_weekend_serves_settled_sidecar(self, tmp_path, monkeypatch):
        # hermetic: an empty quotes file would fall through _load_quotes'
        # <2-quote candidate skip to real snapshots on disk
        monkeypatch.setattr(bp, "_load_quotes", lambda qp: ({}, None))
        sidecar = {
            "schema": "basket_pulse.v1",
            "as_of_utc": "2026-07-10T20:35:00+00:00",
            "as_of_quotes": "2026-07-10T20:00:00+00:00",
            "built": "2026-07-10 20:35:00 UTC",
            "session": "post", "mode": bp.MODE_LAST_RTH,
            "settled_close": True, "session_date": "2026-07-10",
            "delay_min_median": None, "coverage_pct": 100.0,
            "quotes_source": None, "n_quotes_total": 3, "stale_min": 20,
            "baskets": [{"id": "b1", "n_members": 3, "n_quoted": 3,
                         "live_ew_chg_pct": 0.5, "cum_2d_pct": None,
                         "tape_rank": 1, "stale": False, "delay_min": None}],
            "od_spread_print": None, "shock_day_relative_bid": None, "complexes": [],
        }
        (tmp_path / bp.LASTGOOD_FILENAME).write_text(json.dumps(sidecar))
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, {}),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_SATURDAY, out_dir=tmp_path)
        assert res["mode"] == bp.MODE_LAST_RTH
        assert res.get("settled_close") is True          # preserved verbatim
        assert res["session"] == "closed"                 # restamped to now

    def test_no_recompute_during_rth(self, tmp_path):
        rth = datetime(2026, 7, 9, 18, 0, tzinfo=timezone.utc)  # 14:00 ET
        qs = {"AAA": _q(1.0, ts_ms=int(rth.timestamp() * 1000)),
              "BBB": _q(2.0, ts_ms=int(rth.timestamp() * 1000)),
              "CCC": _q(-3.0, ts_ms=int(rth.timestamp() * 1000))}
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=rth, out_dir=tmp_path)
        assert res["mode"] in (bp.MODE_LIVE, bp.MODE_DELAYED)
        assert "settled_close" not in res


class TestDayFlow:
    _FLOW = {"b1": {"dollar_vol_surge": 1.8, "cmf": 0.12,
                    "label_en": "Net inflow (accumulation)",
                    "label_zh": "净流入（吸筹）", "as_of": "2026-07-09"}}

    def test_attached_on_settled_build(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bp, "_load_theme_flow", lambda path=None: (self._FLOW, "2026-07-09"))
        qs = {"AAA": _q(1.0), "BBB": _q(2.0), "CCC": _q(-3.0)}
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_POST_TICK, out_dir=tmp_path)
        assert res["baskets"][0]["day_flow"]["dollar_vol_surge"] == 1.8
        assert res["day_flow_as_of"] == "2026-07-09"
        # sidecar stays flow-free — serving re-attaches the freshest read
        side = json.loads((tmp_path / bp.LASTGOOD_FILENAME).read_text())
        assert "day_flow" not in side["baskets"][0]

    def test_absent_flow_is_graceful(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bp, "_load_theme_flow", lambda path=None: ({}, None))
        qs = {"AAA": _q(1.0), "BBB": _q(2.0), "CCC": _q(-3.0)}
        res = bp.build(
            quotes_path=_quotes_file(tmp_path, qs),
            membership_path=_membership_file(tmp_path, {"b1": ["AAA", "BBB", "CCC"]}),
            now=_POST_TICK, out_dir=tmp_path)
        assert res["settled_close"] is True
        assert "day_flow" not in res["baskets"][0]

    def test_loader_shape_walk(self, tmp_path):
        art = {"as_of": "2026-07-09",
               "theme_intel": {"as_of": "2026-07-09", "themes": [
                   {"id": "b1", "tape": {"as_of": "2026-07-09",
                                         "flow": {"dollar_vol_surge": 2.1, "cmf": -0.08,
                                                  "label_en": "Net outflow (distribution)",
                                                  "label_zh": "净流出（派发）",
                                                  "directional": False}}},
                   {"id": "b2", "tape": None},                       # <60-bar basket
                   {"id": "b3", "tape": {"as_of": "2026-07-09", "flow": None}},  # no $vol
               ]}}
        p = tmp_path / "baskets.json"
        p.write_text(json.dumps(art))
        flow_map, as_of = bp._load_theme_flow(path=p)
        assert as_of == "2026-07-09"
        assert set(flow_map) == {"b1"}
        assert flow_map["b1"]["cmf"] == -0.08
        assert flow_map["b1"]["as_of"] == "2026-07-09"

    def test_loader_missing_file(self, tmp_path):
        flow_map, as_of = bp._load_theme_flow(path=tmp_path / "nope.json")
        assert flow_map == {} and as_of is None
