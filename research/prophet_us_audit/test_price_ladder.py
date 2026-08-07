"""Unit + regression tests for the adjusted-first price ladder.

Two classes of test here, and the split is deliberate.

**Synthetic (always run).** Ladder ordering, fallback disclosure, ex-distribution
resolution, and the absent-name null are pinned against a store built in ``tmp_path``.
These never skip, so the contract stays pinned on a runner with no ``data/`` (CI packs
install minimal deps and carry no data tree — memory:
``ci-packs-install-minimal-deps-not-requirements``).

**Store-dependent (skips with a reason).** ``test_cfg_regression_against_real_stores``
reproduces the ORIGINAL measured receipt — CFG at 2026-06-22 reading 67.9900 in the
breadth cache versus 67.5514 in ``data/baskets/ohlcv`` — and asserts the ladder resolves
to the adjusted value. It can only run where the stores exist.

A skipping test proves nothing (memory: ``a-gate-hung-on-a-skipping-fixture-is-dark``),
so the SAME defect shape is also reconstructed synthetically from those exact numbers in
``test_cfg_regression_shape_synthetic``, which never skips. If the real-store test is
skipped, the defect logic is still pinned; if the real store changes underneath, the
synthetic test still fails on a ladder regression.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

_spec = importlib.util.spec_from_file_location("price_ladder", HERE / "price_ladder.py")
price_ladder = importlib.util.module_from_spec(_spec)
sys.modules["price_ladder"] = price_ladder
_spec.loader.exec_module(price_ladder)

resolve_close = price_ladder.resolve_close
close_panel = price_ladder.close_panel

# ---- the measured receipt this module exists to prevent -------------------------
CFG_DATE = "2026-06-22"
CFG_CACHE = 67.9900        # data/{breadth}/_closes_cache.parquet — raw, pre-ex-div
CFG_ADJUSTED = 67.5514     # data/baskets/ohlcv/CFG.parquet — back-adjusted
CFG_CONVERGE_DATE = "2026-07-07"   # after the 2026-07-01 ex-date both sources agree
CFG_CONVERGE = 71.3170


# --------------------------------------------------------------------------- #
# synthetic store
# --------------------------------------------------------------------------- #
def _sessions(n: int = 12, start: str = "2026-06-15") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _write(path: Path, s: pd.Series, col: str = "close") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({col: s.values}, index=s.index).to_parquet(path)


def _store(root: Path, *, baskets=None, yahoo=None, stocks=None, cache=None,
           cache_group: str = "breadth") -> Path:
    """Build a ``data_dir``-shaped tree; each arg is {ticker: Series}."""
    data = root / "data"
    for tk, s in (baskets or {}).items():
        _write(data / "baskets" / "ohlcv" / f"{tk}.parquet", s)
    for tk, s in (yahoo or {}).items():
        _write(data / "yahoo" / f"{tk}.parquet", s)
    for tk, s in (stocks or {}).items():
        _write(data / "stocks" / f"{tk}.parquet", s)
    if cache:
        frame = pd.DataFrame(cache)
        (data / cache_group).mkdir(parents=True, exist_ok=True)
        frame.to_parquet(data / cache_group / "_closes_cache.parquet")
    return data


# --------------------------------------------------------------------------- #
# 1. adjusted-first ordering
# --------------------------------------------------------------------------- #
def test_ladder_prefers_baskets_over_every_other_rung(tmp_path):
    idx = _sessions()
    data = _store(
        tmp_path,
        baskets={"AAA": pd.Series(1.0, index=idx)},
        yahoo={"AAA": pd.Series(2.0, index=idx)},
        stocks={"AAA": pd.Series(3.0, index=idx)},
        cache={"AAA": pd.Series(4.0, index=idx)},
    )
    r = resolve_close("AAA", data_dir=str(data))
    assert r.price_source == "baskets_ohlcv"
    assert r.adjusted is True
    assert float(r.series.iloc[0]) == 1.0
    # a hit on rung 1 must not have consulted the later rungs
    assert r.tried == ["baskets_ohlcv"]


def test_ladder_falls_to_yahoo_then_stocks_then_cache(tmp_path):
    """Each rung is reached only when every adjusted rung above it is absent."""
    idx = _sessions()
    data = _store(
        tmp_path,
        yahoo={"BBB": pd.Series(2.0, index=idx)},
        stocks={"BBB": pd.Series(3.0, index=idx), "CCC": pd.Series(3.0, index=idx)},
        cache={"BBB": pd.Series(4.0, index=idx), "CCC": pd.Series(4.0, index=idx),
               "DDD": pd.Series(4.0, index=idx)},
    )
    b = resolve_close("BBB", data_dir=str(data))
    assert (b.price_source, b.adjusted) == ("yahoo", True)
    assert b.tried == ["baskets_ohlcv", "yahoo"]

    c = resolve_close("CCC", data_dir=str(data))
    assert (c.price_source, c.adjusted) == ("data_stocks", True)
    assert c.tried == ["baskets_ohlcv", "yahoo", "data_stocks"]

    d = resolve_close("DDD", data_dir=str(data))
    assert (d.price_source, d.adjusted) == ("closes_cache_UNADJUSTED", False)
    assert d.tried == ["baskets_ohlcv", "yahoo", "data_stocks", "closes_cache_UNADJUSTED"]


def test_cache_only_name_is_searched_across_all_three_groups(tmp_path):
    """A midcap/smallcap-only name must still resolve — the cache rung is a union."""
    idx = _sessions()
    data = _store(tmp_path, cache={"MID": pd.Series(9.0, index=idx)},
                  cache_group="midcap_breadth")
    r = resolve_close("MID", data_dir=str(data))
    assert r.price_source == "closes_cache_UNADJUSTED"
    assert float(r.series.iloc[0]) == 9.0


# --------------------------------------------------------------------------- #
# 2. fallback disclosure
# --------------------------------------------------------------------------- #
def test_panel_counts_and_names_every_unadjusted_fallback(tmp_path):
    idx = _sessions()
    data = _store(
        tmp_path,
        baskets={"ADJ1": pd.Series(1.0, index=idx), "ADJ2": pd.Series(1.0, index=idx)},
        cache={"RAW1": pd.Series(4.0, index=idx), "RAW2": pd.Series(4.0, index=idx)},
    )
    px, prov = close_panel(["ADJ1", "ADJ2", "RAW1", "RAW2", "GONE"], data_dir=str(data))

    assert prov["resolved_from"]["baskets_ohlcv"] == 2
    assert prov["resolved_from"]["closes_cache_UNADJUSTED"] == 2
    assert prov["resolved_from"]["unresolved"] == 1
    # the fallback is COUNTED and NAMED, not merely counted
    assert prov["names_on_unadjusted_basis"] == 2
    assert prov["unadjusted_tickers"] == ["RAW1", "RAW2"]
    assert prov["unresolved_tickers"] == ["GONE"]
    assert prov["price_source"]["RAW1"] == "closes_cache_UNADJUSTED"
    assert prov["price_source"]["ADJ1"] == "baskets_ohlcv"
    assert prov["price_source"]["GONE"] is None
    assert prov["ladder"][0] == "baskets_ohlcv"
    assert prov["ladder"][-1] == "closes_cache_UNADJUSTED"
    assert set(px.columns) == {"ADJ1", "ADJ2", "RAW1", "RAW2"}


def test_allow_unadjusted_false_refuses_the_cache_and_says_why(tmp_path):
    idx = _sessions()
    data = _store(tmp_path, cache={"RAW1": pd.Series(4.0, index=idx)})
    r = resolve_close("RAW1", data_dir=str(data), allow_unadjusted=False)
    assert r.series is None
    assert r.price_source is None
    assert "allow_unadjusted=False" in r.reason
    assert "closes_cache_UNADJUSTED" not in r.tried


# --------------------------------------------------------------------------- #
# 3. an ex-distribution name resolves to the ADJUSTED series
# --------------------------------------------------------------------------- #
def test_ex_distribution_name_resolves_to_the_adjusted_series(tmp_path):
    """The name pays a distribution mid-window; cache and adjusted disagree BEFORE the
    ex-date and agree after. The ladder must return the adjusted leg, so the measured
    return does not book the distribution as a loss."""
    idx = _sessions(6, "2026-06-22")
    ex = 3                                        # ex-date at index 3
    raw = pd.Series([100.0, 101.0, 102.0, 101.4, 102.4, 103.4], index=idx)
    factor = 1.0 - 0.006                          # 0.6% distribution
    adj = raw.copy()
    adj.iloc[:ex] = (raw.iloc[:ex] * factor).round(4)
    data = _store(tmp_path, baskets={"PAYER": adj}, cache={"PAYER": raw})

    r = resolve_close("PAYER", data_dir=str(data))
    assert r.price_source == "baskets_ohlcv"
    assert r.adjusted is True
    # pre-ex-date the two bases differ; the ladder took the adjusted one
    assert float(r.series.iloc[0]) == pytest.approx(99.4, abs=1e-6)
    assert float(r.series.iloc[0]) != pytest.approx(float(raw.iloc[0]), abs=1e-6)
    # post-ex-date they agree — which is why this defect hides
    assert float(r.series.iloc[-1]) == pytest.approx(float(raw.iloc[-1]), abs=1e-6)

    # and the measured full-window return differs by ~the distribution
    ret_adj = float(r.series.iloc[-1] / r.series.iloc[0] - 1)
    ret_raw = float(raw.iloc[-1] / raw.iloc[0] - 1)
    assert ret_adj - ret_raw == pytest.approx(0.006, abs=5e-4)
    assert ret_raw < ret_adj                      # the cache books the payout as a LOSS


# --------------------------------------------------------------------------- #
# 4. absent from every source -> null WITH a reason
# --------------------------------------------------------------------------- #
def test_absent_from_every_source_returns_null_with_reason(tmp_path):
    data = _store(tmp_path, baskets={"OTHER": pd.Series(1.0, index=_sessions())})
    r = resolve_close("NOPE", data_dir=str(data))
    assert r.series is None
    assert r.ok is False
    assert r.price_source is None
    assert r.adjusted is None
    assert r.reason and "absent from every source" in r.reason
    # every rung was actually attempted before giving up
    assert r.tried == list(price_ladder.LADDER)


def test_empty_and_unreadable_files_do_not_pass_as_a_hit(tmp_path):
    """An empty parquet and a non-parquet file must both fall THROUGH, not resolve.
    'absent' and 'unreadable' are different failures and neither may read as data
    (memory: ``absent-baseline-is-not-an-unreadable-baseline``)."""
    idx = _sessions()
    data = _store(tmp_path, yahoo={"EMPTY": pd.Series(dtype=float)},
                  cache={"EMPTY": pd.Series(5.0, index=idx),
                         "JUNK": pd.Series(5.0, index=idx)})
    junk = data / "baskets" / "ohlcv"
    junk.mkdir(parents=True, exist_ok=True)
    (junk / "JUNK.parquet").write_bytes(b"not a parquet file")

    e = resolve_close("EMPTY", data_dir=str(data))
    assert e.price_source == "closes_cache_UNADJUSTED"
    j = resolve_close("JUNK", data_dir=str(data))
    assert j.price_source == "closes_cache_UNADJUSTED"


def test_asof_and_start_clip_the_series(tmp_path):
    idx = _sessions(20, "2026-06-01")
    data = _store(tmp_path, baskets={"AAA": pd.Series(range(20), index=idx, dtype=float)})
    r = resolve_close("AAA", data_dir=str(data), start="2026-06-10", asof="2026-06-19")
    assert r.series.index.min() >= pd.Timestamp("2026-06-10")
    assert r.series.index.max() <= pd.Timestamp("2026-06-19")


def test_a_window_that_closes_before_the_ex_date_carries_no_bias(tmp_path):
    """The bounding claim in the module docstring, pinned: cache and adjusted agree
    exactly on any window that ends before the first post-rebuild distribution, so this
    defect must NOT be restated as 'all history is wrong'."""
    idx = _sessions(10, "2026-06-01")
    raw = pd.Series([100.0 + i for i in range(10)], index=idx)
    adj = raw.copy()
    adj.iloc[:8] = (raw.iloc[:8] * 0.99).round(6)      # ex-date at index 8
    data = _store(tmp_path, baskets={"P": adj}, cache={"P": raw})
    r = resolve_close("P", data_dir=str(data))
    # window entirely before the ex-date: identical measured return on both bases
    w = slice(0, 5)
    assert float(adj.iloc[w].iloc[-1] / adj.iloc[w].iloc[0] - 1) == pytest.approx(
        float(raw.iloc[w].iloc[-1] / raw.iloc[w].iloc[0] - 1), abs=1e-9)
    assert r.adjusted is True


# --------------------------------------------------------------------------- #
# 5. THE REGRESSION — the CFG 2026-06-22 receipt
# --------------------------------------------------------------------------- #
def test_cfg_regression_shape_synthetic():
    """The measured CFG numbers, replayed against a synthetic store. Never skips.

    This is the always-on half of the regression: if the ladder ever re-orders so the
    cache wins, this fails on a data-less runner too.
    """
    idx = pd.DatetimeIndex([pd.Timestamp(CFG_DATE), pd.Timestamp(CFG_CONVERGE_DATE)])
    cache = pd.Series([CFG_CACHE, CFG_CONVERGE], index=idx)
    adjusted = pd.Series([CFG_ADJUSTED, CFG_CONVERGE], index=idx)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        data = _store(Path(td), baskets={"CFG": adjusted}, cache={"CFG": cache})
        r = resolve_close("CFG", data_dir=str(data))

    assert r.price_source == "baskets_ohlcv"
    assert r.adjusted is True
    assert float(r.series.loc[pd.Timestamp(CFG_DATE)]) == pytest.approx(CFG_ADJUSTED, abs=1e-4)

    # the defect, quantified: the cache basis understates the window return
    ret_cache = CFG_CONVERGE / CFG_CACHE - 1
    ret_adj = CFG_CONVERGE / CFG_ADJUSTED - 1
    assert (ret_adj - ret_cache) * 100 == pytest.approx(0.68, abs=0.05)
    assert ret_cache < ret_adj


@pytest.mark.skipif(
    not (REPO / "data" / "baskets" / "ohlcv" / "CFG.parquet").exists()
    or not (REPO / "data" / "breadth" / "_closes_cache.parquet").exists(),
    reason="store-dependent: needs data/baskets/ohlcv/CFG.parquet + the breadth cache "
           "(CI packs carry no data/ tree); the synthetic twin above still pins the shape",
)
def test_cfg_regression_against_real_stores():
    """The original receipt, against the real stores: the two bases DO disagree at
    2026-06-22, and the ladder resolves to the adjusted one."""
    cache = pd.read_parquet(REPO / "data" / "breadth" / "_closes_cache.parquet")
    cache.index = pd.to_datetime(cache.index)
    d = pd.Timestamp(CFG_DATE)
    assert "CFG" in cache.columns, "CFG left the breadth cache — re-pin this receipt"
    assert d in cache.index, "2026-06-22 left the breadth cache — re-pin this receipt"

    raw = float(cache.loc[d, "CFG"])
    assert raw == pytest.approx(CFG_CACHE, abs=1e-3), (
        f"the cache no longer reads {CFG_CACHE} at {CFG_DATE} (got {raw}) — if the cache "
        "was rebuilt this receipt must be re-measured, never loosened")

    r = resolve_close("CFG", data_dir=str(REPO / "data"), asof="2026-07-31")
    assert r.price_source == "baskets_ohlcv"
    assert r.adjusted is True
    got = float(r.series.loc[d])
    assert got == pytest.approx(CFG_ADJUSTED, abs=1e-3)

    # the discrepancy is real and this is its size
    assert (raw - got) / got * 100 == pytest.approx(0.649, abs=0.02)
    # ...and it is GONE after the ex-date, which is why it hid for so long
    cd = pd.Timestamp(CFG_CONVERGE_DATE)
    if cd in cache.index and cd in r.series.index:
        assert float(cache.loc[cd, "CFG"]) == pytest.approx(float(r.series.loc[cd]), abs=1e-3)


@pytest.mark.skipif(
    not (REPO / "data" / "breadth" / "_closes_cache.parquet").exists(),
    reason="store-dependent: needs the breadth cache",
)
def test_non_payer_and_no_exdiv_names_agree_across_bases():
    """The control half of the receipt: names with no post-rebuild ex-date agree
    EXACTLY across both bases. Without this, a passing CFG assertion could equally be
    explained by the two stores simply being different data."""
    cache = pd.read_parquet(REPO / "data" / "breadth" / "_closes_cache.parquet")
    cache.index = pd.to_datetime(cache.index)
    d = pd.Timestamp(CFG_DATE)
    checked = 0
    for tk in ("JPM", "KO", "ALB", "CEG"):
        if tk not in cache.columns or d not in cache.index:
            continue
        r = resolve_close(tk, data_dir=str(REPO / "data"), asof="2026-07-31")
        if not r.ok or d not in r.series.index:
            continue
        assert float(cache.loc[d, tk]) == pytest.approx(float(r.series.loc[d]), abs=1e-3), (
            f"{tk} disagrees across bases at {CFG_DATE} — the control assumption moved")
        checked += 1
    if checked == 0:
        pytest.skip("no control name resolvable in this store")
