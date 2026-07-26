"""Contract tests for collectors.china_board_breadth (whole-board 沪深 涨跌家数).

Both planes are network sources, so every test here drives the parsing/counting
logic with canned payloads — nothing in this file touches the wire.
"""
from __future__ import annotations

import pandas as pd
import pytest

from collectors import china_board_breadth as cbb


# --------------------------------------------------------------------------- #
#  scope — 沪深 only (the operator's call; 北交所 is out)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code", ["600519", "601398", "603288", "605499",
                                  "688981", "000001", "001979", "002594",
                                  "300750", "301269"])
def test_hushen_codes_accepted(code):
    assert cbb._is_hushen(code)


@pytest.mark.parametrize("code", [
    "830799", "873169", "430418",   # 北交所 — excluded by scope
    "900901", "200011",             # B-shares
    "00700", "6005190", "60051A", "", "sh600519",
])
def test_non_hushen_codes_rejected(code):
    assert not cbb._is_hushen(code)


# --------------------------------------------------------------------------- #
#  counting — 涨/跌/平 split on strict zero (东方财富 convention)
# --------------------------------------------------------------------------- #
def test_counts_split_on_strict_zero():
    pct = pd.Series([1.0] * 500 + [-1.0] * 2400 + [0.0] * 100 + [0.004] * 100)
    df = cbb._counts(pct, "sina", pd.Timestamp("2026-07-24"))
    r = df.iloc[0]
    assert r["n"] == 3100
    assert r["adv"] == 600          # +0.004% is an advance, not a flat print
    assert r["dec"] == 2400
    assert r["flat"] == 100
    assert r["adv"] + r["dec"] + r["flat"] == r["n"]
    assert r["pct_up"] == round(100 * 600 / 3100, 2)
    assert r["source"] == "sina"


def test_counts_indexed_by_session_not_run_date():
    """The index IS the freshness key the heatmap builder gates on — a same-session
    re-run must overwrite its row rather than append a second one."""
    pct = pd.Series([0.5] * 4000)
    df = cbb._counts(pct, "tushare", pd.Timestamp("2026-07-24"))
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index[0] == pd.Timestamp("2026-07-24")
    assert df.index.tz is None          # tz-naive: parquet ledgers reject tz-aware
    assert len(df) == 1


def test_counts_rejects_a_half_failed_pull():
    """A few hundred names is a broken page walk, not a 5,200-name board. Landing it
    would print a confidently wrong denominator — the exact defect this fixes."""
    with pytest.raises(ValueError, match="half-failed"):
        cbb._counts(pd.Series([1.0] * 200), "sina", pd.Timestamp("2026-07-24"))


def test_counts_median_is_the_board_median():
    pct = pd.Series([-3.0] * 3000 + [1.0] * 1000)
    df = cbb._counts(pct, "sina", pd.Timestamp("2026-07-24"))
    assert df.iloc[0]["med_pct"] == pytest.approx(-3.0)


# --------------------------------------------------------------------------- #
#  Sina plane — session date + page walk
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


_SINA_LINE = ('var hq_str_sh000001="上证指数,3853.63,3876.77,3814.19,3861.04,3808.63,0,0,'
              '508203905,915366398293,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,'
              '2026-07-24,15:30:36,00,";')


def test_sina_session_date_parsed_from_index_quote(monkeypatch):
    a = cbb.ChinaBoardBreadthAdapter()
    monkeypatch.setattr(a, "http_get", lambda *_a, **_k: _Resp(text=_SINA_LINE))
    assert a._sina_session_date() == pd.Timestamp("2026-07-24")


def test_sina_session_date_raises_on_garbage(monkeypatch):
    a = cbb.ChinaBoardBreadthAdapter()
    monkeypatch.setattr(a, "http_get", lambda *_a, **_k: _Resp(text='var hq_str_sh000001="";'))
    with pytest.raises(ValueError, match="no session date"):
        a._sina_session_date()


def _sina_walk(monkeypatch, rows, adapter=None):
    """Drive _from_sina over a canned board, one page of 80 at a time."""
    a = adapter or cbb.ChinaBoardBreadthAdapter()
    pages = [rows[i:i + 80] for i in range(0, len(rows), 80)]

    def fake_get(url, **kw):
        if url == cbb._SINA_DATE_URL:
            return _Resp(text=_SINA_LINE)
        page = kw["params"]["page"]
        return _Resp(payload=pages[page - 1] if page <= len(pages) else None)

    monkeypatch.setattr(a, "http_get", fake_get)
    monkeypatch.setattr(cbb.time, "sleep", lambda *_: None)
    return a._from_sina()


def _row(code, pct, trade=10.0):
    return {"code": code, "changepercent": pct, "trade": trade}


def test_sina_walk_counts_only_traded_hushen_names(monkeypatch):
    rows = ([_row(f"6{i:05d}", 1.5) for i in range(1500)]         # 沪 advancing
            + [_row(f"0{i:05d}", -2.0) for i in range(2000)]      # 深 declining
            + [_row(f"3{i:05d}", 0.0) for i in range(600)]        # 创业板 flat
            + [_row(f"83{i:04d}", 9.0) for i in range(300)]       # 北交所 — out of scope
            + [_row(f"60{i:04d}", -5.0, trade=0.0) for i in range(120)])  # 停牌 — no print
    df = _sina_walk(monkeypatch, rows)
    r = df.iloc[0]
    assert r["n"] == 4100            # 1500 + 2000 + 600; BJ and suspended excluded
    assert (r["adv"], r["dec"], r["flat"]) == (1500, 2000, 600)
    assert r["source"] == "sina"
    assert df.index[0] == pd.Timestamp("2026-07-24")


def test_sina_walk_skips_unparseable_rows(monkeypatch):
    rows = [_row(f"6{i:05d}", 1.0) for i in range(3200)]
    rows += [{"code": "600001"}, {"code": "600002", "changepercent": None},
             {"code": "600003", "changepercent": "n/a", "trade": 5.0}]
    df = _sina_walk(monkeypatch, rows)
    assert df.iloc[0]["n"] == 3200


def test_sina_walk_dedupes_repeated_codes(monkeypatch):
    """Sina re-serves rows near a page boundary when the board shifts mid-walk."""
    rows = [_row(f"6{i:05d}", 1.0) for i in range(3100)]
    rows += [_row("600000", 1.0)] * 50
    df = _sina_walk(monkeypatch, rows)
    assert df.iloc[0]["n"] == 3100


# --------------------------------------------------------------------------- #
#  plane selection — premium primary, keyless fallback
# --------------------------------------------------------------------------- #
def test_fetch_falls_back_to_sina_when_tushare_is_gated(monkeypatch):
    a = cbb.ChinaBoardBreadthAdapter()
    monkeypatch.setattr(a, "_from_tushare", lambda: None)
    called = {}

    def fake_sina():
        called["yes"] = True
        return cbb._counts(pd.Series([1.0] * 4000), "sina", pd.Timestamp("2026-07-24"))

    monkeypatch.setattr(a, "_from_sina", fake_sina)
    out = a.fetch()
    assert called and out["breadth"].iloc[0]["source"] == "sina"


def test_fetch_falls_back_when_tushare_raises(monkeypatch):
    """A premium-plane outage must degrade to the keyless walk, never fail the run."""
    a = cbb.ChinaBoardBreadthAdapter()

    def boom():
        raise RuntimeError("tushare 500")

    monkeypatch.setattr(a, "_from_tushare", boom)
    monkeypatch.setattr(a, "_from_sina",
                        lambda: cbb._counts(pd.Series([1.0] * 4000), "sina",
                                            pd.Timestamp("2026-07-24")))
    assert a.fetch()["breadth"].iloc[0]["source"] == "sina"


def test_fetch_prefers_tushare_when_available(monkeypatch):
    a = cbb.ChinaBoardBreadthAdapter()
    monkeypatch.setattr(a, "_from_tushare",
                        lambda: cbb._counts(pd.Series([1.0] * 5000), "tushare",
                                            pd.Timestamp("2026-07-24")))
    monkeypatch.setattr(a, "_from_sina", lambda: pytest.fail("Sina walked despite a live token"))
    assert a.fetch()["breadth"].iloc[0]["source"] == "tushare"


def test_tushare_plane_filters_scope_and_dedupes(monkeypatch):
    a = cbb.ChinaBoardBreadthAdapter()
    codes = ([f"6{i:05d}.SS" for i in range(2000)]
             + [f"0{i:05d}.SZ" for i in range(2000)]
             + [f"83{i:04d}.BJ" for i in range(300)])   # 北交所 — excluded
    df = pd.DataFrame({"ts_code": codes + ["600000.SS"],       # duplicate row
                       "pct_chg": [1.0] * 2000 + [-1.0] * 2000 + [3.0] * 300 + [1.0]})

    class _TC:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def snapshot_by_date(*_a, **_k):
            return df, "20260724"

    monkeypatch.setitem(__import__("sys").modules, "collectors.tushare_client", _TC)
    out = a._from_tushare()
    r = out.iloc[0]
    assert r["n"] == 4000            # BJ dropped, duplicate collapsed
    assert (r["adv"], r["dec"]) == (2000, 2000)
    assert out.index[0] == pd.Timestamp("2026-07-24")


def test_adapter_is_registered_and_blocked_when_sources_are_down():
    """Registered in the asia lane (name starts with 'china' → the shard's prefix match
    picks it up), and flagged so an outage reports 'blocked' rather than tripping the
    circuit breaker for every other china_* collector. Read as text, not imported —
    an unregistered collector is a dead wire that never runs (#1253 class)."""
    from pathlib import Path
    registry = Path(__file__).resolve().parent.parent / "scripts" / "collect.py"
    line = [ln for ln in registry.read_text(encoding="utf-8").splitlines()
            if "ChinaBoardBreadthAdapter" in ln]
    assert line, "china_board_breadth is not in the collect.py adapter registry"
    assert "collectors.china_board_breadth" in line[0]
    assert cbb.ChinaBoardBreadthAdapter.name.startswith("china")
    assert cbb.ChinaBoardBreadthAdapter.expected_failure
    assert cbb.ChinaBoardBreadthAdapter.group == "china_board_breadth"
