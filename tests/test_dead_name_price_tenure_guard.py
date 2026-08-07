"""Identity guard for the dead-name PRICE registry (a ticker string is a MUTABLE key).

Fetching by bare ticker string returns whoever holds the string at request time, so a
window that predates the registrant welds two companies into one key. Invariants:

  * a pre-tenure segment behind a >= SPLICE_GAP_DAYS hole is REFUSED (FI, ALTM);
  * a gap INSIDE the tenure is a corporate event and is KEPT — the Ch.11 price->0
    tail is the anti-survivorship data the panel exists to hold, never a splice;
  * a contiguous pre-tenure lookback is KEPT (same company, before index inclusion);
  * the Polygon producer CLAMPS its request start to tenure_start - lookback rather
    than the global ANCHOR_DATE (asserted on the value actually passed to the fetcher,
    so removing the clamp reds this test);
  * price_coverage() stamps the index-exit universe basis + the splice quarantine;
  * splice annotations START the line (GitHub drops them otherwise).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from collectors import edgar_deadname_prices as dp


def _mem(ticker="FI", start="2023-06-07", end="2025-11-11"):
    return pd.DataFrame({"ticker": [ticker],
                         "start_date": pd.to_datetime([start]),
                         "end_date": pd.to_datetime([end]),
                         "src": ["sp500"]})


def _seg(start, n, base):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([base + i * 0.1 for i in range(n)], index=idx)


# --------------------------------------------------------------------------- #
# split_identity_seam
# --------------------------------------------------------------------------- #
def test_pre_tenure_segment_behind_a_gap_is_refused():
    """The FI shape: a prior registrant's tape, then an empty year, then the holder."""
    foreign_seg = _seg("2021-07-06", 63, 15.0)          # Frank's International
    own = _seg("2023-06-07", 120, 115.0)                # Fiserv
    s = pd.concat([foreign_seg, own])

    kept, foreign = dp.split_identity_seam(s, pd.Timestamp("2023-06-07"))

    assert len(foreign) == 63
    assert foreign.index.max() < pd.Timestamp("2023-06-07")
    assert len(kept) == 120 and kept.index.min() == pd.Timestamp("2023-06-07")


def test_gap_inside_tenure_is_kept_bankruptcy_tail_survives():
    """EBIX/ENDP: Ch.11 halt then an OTC price->0 tail. Same company — never a splice,
    and dropping it would delete exactly the anti-survivorship rows we want."""
    pre = _seg("2023-01-02", 60, 16.0)
    post = pd.Series([0.02, 0.015, 0.01], index=pd.bdate_range("2023-06-01", periods=3))
    s = pd.concat([pre, post])

    kept, foreign = dp.split_identity_seam(s, pd.Timestamp("2019-12-17"))

    assert len(foreign) == 0
    assert len(kept) == len(s)
    assert float(kept.min()) == pytest.approx(0.01)      # the wipeout tail is retained


def test_contiguous_pre_tenure_lookback_is_kept():
    """Trading before index inclusion is the SAME company — legitimate lookback."""
    s = _seg("2022-01-03", 400, 40.0)                    # no hole anywhere

    kept, foreign = dp.split_identity_seam(s, pd.Timestamp("2023-06-07"))

    assert len(foreign) == 0 and len(kept) == len(s)


def test_no_tenure_start_is_a_noop():
    s = _seg("2021-07-06", 30, 10.0)
    kept, foreign = dp.split_identity_seam(s, None)
    assert len(foreign) == 0 and len(kept) == len(s)


def test_tenure_bounds_reads_the_membership_span():
    assert dp.tenure_bounds("FI", _mem())[0] == pd.Timestamp("2023-06-07")
    assert dp.tenure_bounds("NOPE", _mem()) is None


# --------------------------------------------------------------------------- #
# producer clamps the request window (mutation-pinned on the passed value)
# --------------------------------------------------------------------------- #
def test_polygon_producer_clamps_start_to_tenure_not_the_global_anchor(monkeypatch, tmp_path):
    import scripts.research.fetch_dead_name_prices_polygon as m

    for sub in ("edgar", "breadth", "research"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    # tenure starts LONG after ANCHOR_DATE — the exact shape that produced FI
    pd.DataFrame({"ticker": ["LATE"],
                  "start_date": pd.to_datetime(["2023-06-07"]),
                  "end_date": pd.to_datetime(["2025-11-11"]),
                  "src": ["sp500"]}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    pd.DataFrame({"ticker": ["LATE"], "date": pd.to_datetime(["2021-09-01"])}).to_parquet(
        tmp_path / "research" / "gate_fires_baskets.parquet")
    monkeypatch.setattr(m.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)

    seen: dict[str, str] = {}

    def _fake(ticker, start, end, key):
        seen[ticker] = start
        return _seg("2023-06-07", 30, 115.0)

    monkeypatch.setattr(m, "_polygon_fetch", _fake)
    m.fetch(max_new=5)

    expected = (pd.Timestamp("2023-06-07")
                - pd.Timedelta(days=m.TENURE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    assert seen["LATE"] == expected, "request start must be clamped to the registrant's tenure"
    assert seen["LATE"] > m.ANCHOR_DATE, "the global anchor must not be used for a late tenure"


def test_producer_refuses_a_spliced_reply(monkeypatch, tmp_path, capsys):
    """Even with a clamped window the vendor can still answer with a prior holder's
    tape, so the seam check must strip it before it reaches the parquet."""
    import scripts.research.fetch_dead_name_prices_polygon as m

    for sub in ("edgar", "breadth", "research"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["LATE"],
                  "start_date": pd.to_datetime(["2023-06-07"]),
                  "end_date": pd.to_datetime(["2025-11-11"]),
                  "src": ["sp500"]}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    pd.DataFrame({"ticker": ["LATE"], "date": pd.to_datetime(["2021-09-01"])}).to_parquet(
        tmp_path / "research" / "gate_fires_baskets.parquet")
    monkeypatch.setattr(m.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)
    monkeypatch.setattr(m, "_polygon_fetch",
                        lambda t, s, e, k: pd.concat([_seg("2021-07-06", 40, 15.0),
                                                      _seg("2023-06-07", 30, 115.0)]))
    m.fetch(max_new=5)

    df = pd.read_parquet(tmp_path / "edgar" / "dead_name_prices.parquet")
    assert df["date"].min() >= pd.Timestamp("2023-06-07"), "pre-tenure rows reached the store"
    assert len(df) == 30
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "dead-name-splice" in ln)
    assert line.startswith("::warning"), "GitHub drops an annotation that is not line-initial"


def test_collector_refuses_a_spliced_reply(monkeypatch, tmp_path, capsys):
    """collectors.edgar_deadname_prices runs the same guard — Stooq is UNWINDOWED
    (full vendor history), so its reply is the likeliest splice of all."""
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dp.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dp.time, "sleep", lambda *a, **k: None)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({"LATE": {"cik": 1, "method": "seed"}}))
    _mem("LATE").to_parquet(tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    monkeypatch.setattr(dp, "_stooq_daily",
                        lambda t: pd.concat([_seg("2021-07-06", 40, 15.0),
                                             _seg("2023-06-07", 30, 115.0)]))

    out = dp.fetch_dead_prices(force=True)

    assert out["date"].min() >= pd.Timestamp("2023-06-07")
    assert len(out) == 30
    seen = json.loads((tmp_path / "edgar" / "_dead_name_prices_seen.json").read_text())
    assert seen["LATE"]["refused_pre_tenure"] == 40
    assert next(ln for ln in capsys.readouterr().out.splitlines()
                if "dead-name-splice" in ln).startswith("::warning")


# --------------------------------------------------------------------------- #
# coverage stamp
# --------------------------------------------------------------------------- #
def test_price_coverage_stamps_index_exit_basis_and_splice_quarantine(monkeypatch, tmp_path):
    """The universe is an INDEX-EXIT set: a name that merely left the S&P is still
    trading, so the stamp must say so rather than imply every name died."""
    for sub in ("edgar", "breadth", "quarantine", "baskets/ohlcv"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dp.config, "data_dir", lambda: tmp_path)
    pd.DataFrame({"ticker": ["ALIVE", "GONE", "KEEP"],
                  "start_date": pd.to_datetime(["2019-01-01"] * 3),
                  "end_date": pd.to_datetime(["2024-01-01", "2024-01-01", None]),
                  "src": ["sp500"] * 3}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(json.dumps({}))
    # ALIVE left the index but still prints a fresh live store
    idx = pd.bdate_range(pd.Timestamp.now().normalize() - pd.Timedelta(days=10), periods=6)
    pd.DataFrame({"close": range(6)}, index=idx).to_parquet(
        tmp_path / "baskets" / "ohlcv" / "ALIVE.parquet")
    pd.DataFrame({"ticker": ["ALIVE"], "date": idx[:1], "close": [1.0],
                  "source": ["polygon"]}).to_parquet(
        tmp_path / "edgar" / "dead_name_prices.parquet")
    (tmp_path / "quarantine" / "dead_name_prices_spliced.json").write_text(json.dumps(
        {"applied": True, "n_names_spliced": 2, "n_rows_quarantined": 224,
         "findings": [{"ticker": "FI"}, {"ticker": "ALTM"}]}))

    out = dp.price_coverage()

    basis = out["universe_basis"]
    assert basis["measured"] is True
    assert "INDEX EXIT" in basis["basis"]
    assert basis["n_still_trading"] == 1 and basis["n_universe"] == 2
    assert "must NOT be trimmed" in basis["caveat"]
    q = out["identity_splice_quarantine"]
    assert q["applied"] is True and q["n_rows"] == 224 and set(q["names"]) == {"FI", "ALTM"}


def test_price_coverage_stamp_survives_a_missing_quarantine(monkeypatch, tmp_path):
    for sub in ("edgar", "breadth"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dp.config, "data_dir", lambda: tmp_path)
    pd.DataFrame({"ticker": ["GONE", "KEEP"],
                  "start_date": pd.to_datetime(["2019-01-01"] * 2),
                  "end_date": pd.to_datetime(["2024-01-01", None]),
                  "src": ["sp500"] * 2}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(json.dumps({}))

    q = dp.price_coverage()["identity_splice_quarantine"]

    assert q["applied"] is False and q["n_rows"] == 0
