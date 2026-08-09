"""engine.price_ladder — the adjusted-first ladder, and the CFG-class regression.

THE CONTRACT
============
An excess return differences a name leg against a benchmark leg. Every benchmark this
house grades against exists only BACK-ADJUSTED, so the name leg must be adjusted too. The
breadth close caches are RAW, so they are the LAST rung, and a name that lands there is
stamped rather than silently mixed in.

EVERY BEHAVIOURAL TEST HERE RUNS ON A SYNTHETIC STORE AND NEVER SKIPS.
A regression that only runs when `data/` happens to be present is a dark gate: it passes
by not executing on a CI runner with no data, and the contract goes unpinned exactly
where it is cheapest to break. So the CFG defect is pinned TWICE — once against the real
committed stores (skipped only when they are absent) and once as a synthetic twin built
from a hand-made dividend that always runs. The twin is the gate; the real-store test is
the evidence that the twin describes this repo.

The CONTROL matters as much as the regression: `JPM`/`KO` have no in-window ex-date and
agree to the cent across every source. Without it, a passing CFG assertion could equally
mean "the two stores just hold different data".
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import price_ladder as pl  # noqa: E402

DATA = ROOT / "data"


# --------------------------------------------------------------------------- #
# synthetic store — a payer whose cache leg is raw and whose adjusted leg is not
# --------------------------------------------------------------------------- #
IDX = pd.bdate_range("2026-06-01", periods=30)
EX_DIV_POS = 15          # the ex-date sits INSIDE the measurement window
DIV_FACTOR = 1.0065      # ~0.65%, the CFG-class magnitude


def _raw_series() -> pd.Series:
    """A flat-drift raw close path — no adjustment ever applied."""
    return pd.Series([100.0 + i for i in range(len(IDX))], index=IDX)


def _adjusted_from(raw: pd.Series) -> pd.Series:
    """Back-adjust `raw` for one distribution at EX_DIV_POS: every bar BEFORE the ex-date
    is scaled down, bars from the ex-date on are untouched. That is exactly what the
    adjusted stores hold and what the caches do not."""
    out = raw.astype(float).copy()
    out.iloc[:EX_DIV_POS] = out.iloc[:EX_DIV_POS] / DIV_FACTOR
    return out


def _write_named(root: Path, sub: str, ticker: str, s: pd.Series) -> None:
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": s.values}, index=s.index).to_parquet(d / f"{ticker}.parquet")


def _write_wide(root: Path, rel: str, cols: dict) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cols, index=IDX).to_parquet(p)


@pytest.fixture
def store(tmp_path) -> Path:
    """A complete synthetic data dir: PAYER diverges between bases, FLAT does not."""
    raw = _raw_series()
    _write_wide(tmp_path, "breadth/_closes_cache.parquet",
                {"PAYER": raw.values, "FLAT": raw.values, "CACHEONLY": raw.values})
    _write_named(tmp_path, "baskets/ohlcv", "PAYER", _adjusted_from(raw))
    _write_named(tmp_path, "baskets/ohlcv", "FLAT", raw)          # no ex-div ⇒ identical
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. ladder order — the whole contract
# --------------------------------------------------------------------------- #
def test_adjusted_rung_outranks_the_cache(store):
    r = pl.resolve_close("PAYER", data_dir=str(store))
    assert r.price_source == "baskets_ohlcv"
    assert r.adjusted is True
    assert r.tried[0] == "baskets_ohlcv", "the adjusted rung must be tried FIRST"
    # the value it returns is the ADJUSTED one, not the cache's
    assert r.series.iloc[0] == pytest.approx(100.0 / DIV_FACTOR)


def test_cache_is_the_last_rung_and_is_stamped_unadjusted(store):
    r = pl.resolve_close("CACHEONLY", data_dir=str(store))
    assert r.price_source == "closes_cache_UNADJUSTED"
    assert r.adjusted is False
    assert r.tried[-1] == "closes_cache_UNADJUSTED"
    assert pl.is_adjusted(r.price_source) is False


def test_coverage_is_not_traded_for_basis_purity(store):
    """A name with no adjusted counterpart is KEPT and disclosed — never dropped. Dropping
    it deletes exactly the population a study exists to measure."""
    assert pl.resolve_close("CACHEONLY", data_dir=str(store)).ok


def test_allow_unadjusted_false_refuses_to_mix(store):
    r = pl.resolve_close("CACHEONLY", data_dir=str(store), allow_unadjusted=False)
    assert r.series is None and r.price_source is None
    assert "allow_unadjusted=False" in r.reason


def test_a_name_on_no_rung_is_null_with_the_ladder_disclosed(store):
    r = pl.resolve_close("NOWHERE", data_dir=str(store))
    assert not r.ok and r.price_source is None
    assert r.tried == list(pl.LADDER), "every rung attempted must be recorded"


def test_a_corrupt_parquet_is_a_miss_not_a_crash(store):
    d = store / "baskets" / "ohlcv"
    (d / "JUNK.parquet").write_bytes(b"not a parquet")
    _write_wide(store, "breadth/_closes_cache.parquet",
                {"JUNK": _raw_series().values})
    r = pl.resolve_close("JUNK", data_dir=str(store))
    assert r.price_source == "closes_cache_UNADJUSTED", "a bad rung must fall through"


# --------------------------------------------------------------------------- #
# 2. THE CFG-CLASS REGRESSION — synthetic twin (NEVER SKIPS)
# --------------------------------------------------------------------------- #
def _fwd_ret(s: pd.Series, i0: int, h: int) -> float:
    return float(s.iloc[i0 + h] / s.iloc[i0] - 1.0)


def test_cfg_class_twin_cache_basis_books_the_dividend_as_a_loss(store):
    """The defect, reproduced from first principles: a window that STRADDLES the ex-date
    returns less on the cache than on the adjusted store, by exactly the distribution."""
    raw = _raw_series()
    adj = _adjusted_from(raw)
    i0, h = EX_DIV_POS - 3, 6                      # straddles EX_DIV_POS
    cache_ret = _fwd_ret(raw, i0, h)
    adj_ret = _fwd_ret(adj, i0, h)
    assert cache_ret < adj_ret, "the raw leg must under-report across an ex-date"
    # the gap IS the dividend factor, not noise
    assert (1 + adj_ret) / (1 + cache_ret) == pytest.approx(DIV_FACTOR, rel=1e-9)


def test_cfg_class_twin_the_ladder_returns_the_adjusted_leg(store):
    """The fix: resolving through the ladder yields the adjusted return, so an excess
    against an adjusted benchmark no longer eats the name's own payout."""
    i0, h = EX_DIV_POS - 3, 6
    got = pl.resolve_close("PAYER", data_dir=str(store)).series
    assert _fwd_ret(got, i0, h) == pytest.approx(
        _fwd_ret(_adjusted_from(_raw_series()), i0, h), rel=1e-12)


def test_cfg_class_twin_control_a_non_payer_agrees_on_both_bases(store):
    """Without this control a passing regression could just mean the two stores hold
    different data. FLAT has no ex-date, so both bases must agree exactly."""
    got = pl.resolve_close("FLAT", data_dir=str(store)).series
    cache = pd.read_parquet(store / "breadth/_closes_cache.parquet")["FLAT"]
    assert np.allclose(got.values, cache.values), "a non-payer must not move"


def test_cfg_class_twin_window_entirely_before_the_ex_date_is_unaffected(store):
    """The exposure is a bounded tail, not all history — a window that closes before the
    ex-date carries ZERO bias. Pinning this stops the fix being over-stated as
    'every historical price was wrong'."""
    raw, adj = _raw_series(), _adjusted_from(_raw_series())
    i0, h = 2, 8                                   # ends well before EX_DIV_POS
    assert _fwd_ret(raw, i0, h) == pytest.approx(_fwd_ret(adj, i0, h), rel=1e-12)


# --------------------------------------------------------------------------- #
# 3. THE CFG REGRESSION — against the real committed stores
# --------------------------------------------------------------------------- #
_REAL = pytest.mark.skipif(
    not (DATA / "breadth" / "_closes_cache.parquet").exists()
    or not (DATA / "baskets" / "ohlcv").exists(),
    reason="committed price stores absent — the synthetic twin above pins the contract",
)


def _cache_value(ticker: str, date: str):
    for g in pl.CACHE_GROUPS:
        p = DATA / g / "_closes_cache.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if ticker in df.columns:
            df.index = pd.to_datetime(df.index)
            v = df[ticker].get(pd.Timestamp(date))
            if v is not None and pd.notna(v):
                return float(v)
    return None


@_REAL
def test_real_store_cfg_diverges_from_the_cache_by_a_dividend():
    """The receipt this whole PR rests on (#4698): CFG at 2026-06-22 reads 67.9900 in the
    cache and 67.5514 adjusted — 0.649%, exactly its quarterly distribution."""
    cache = _cache_value("CFG", "2026-06-22")
    adj = pl.resolve_close("CFG", asof="2026-06-22", start="2026-06-01").series
    if cache is None or adj is None or adj.empty:
        pytest.skip("CFG absent from the committed stores")
    got = float(adj.iloc[-1])
    assert cache == pytest.approx(67.99, abs=1e-3)
    assert got == pytest.approx(67.5514, abs=1e-3)
    assert cache / got == pytest.approx(1.0065, abs=5e-4)


@_REAL
@pytest.mark.parametrize("ticker", ["JPM", "KO"])
def test_real_store_control_non_payers_agree_across_sources(ticker):
    """The control leg. These have no in-window ex-date, so cache and adjusted agree to
    the cent — which is why the defect read as noise until it was looked for by name."""
    cache = _cache_value(ticker, "2026-06-22")
    r = pl.resolve_close(ticker, asof="2026-06-22", start="2026-06-01")
    if cache is None or not r.ok:
        pytest.skip(f"{ticker} absent from the committed stores")
    assert float(r.series.iloc[-1]) == pytest.approx(cache, abs=1e-2)


@_REAL
def test_real_store_ladder_prefers_adjusted_for_a_cached_name():
    """CFG is IN the breadth cache. The ladder must still return the adjusted series —
    otherwise 'adjusted-first' only applies to names the cache happens to miss."""
    assert _cache_value("CFG", "2026-06-22") is not None, "CFG must be in the cache"
    assert pl.resolve_close("CFG").price_source in pl.ADJUSTED_SOURCES


# --------------------------------------------------------------------------- #
# 4. freshness walk — a stale adjusted rung must not silently lose coverage
# --------------------------------------------------------------------------- #
def test_min_last_walks_past_a_stale_adjusted_rung(tmp_path):
    """Measured 2026-08-06: baskets/ohlcv stops 2026-07-10 for ARWR/FN/HL while the
    caches run to 07-31. Preferring the stale rung silently cost graded episodes."""
    raw = _raw_series()
    _write_named(tmp_path, "baskets/ohlcv", "STALE", raw.iloc[:10])   # ends early
    _write_named(tmp_path, "yahoo", "STALE", raw)                     # fresh
    r = pl.resolve_close("STALE", data_dir=str(tmp_path), min_last=IDX[-1])
    assert r.price_source == "yahoo", "a stale rung must not stop the walk"
    assert r.series.index.max() == IDX[-1]


def test_a_stale_adjusted_rung_loses_to_a_COMPLETE_cache_and_says_so(tmp_path):
    """When NO adjusted rung reaches the window, the COMPLETE raw cache wins — stamped.

    This inverts an earlier draft of this rule, and the reversal is the point. Preferring
    a stale adjusted series drops real bars to buy a basis guarantee that protects
    nothing when the two agree: HL/ARWR/TR are bit-identical between cache and
    baskets/ohlcv across their entire 762-session overlap (the store is just stale), and
    preferring it deleted HL@2026-07-01 and TR@2026-07-10 from the postmortem's LOSER
    cohort. A silently vanished loser is worse than a disclosed unadjusted one.
    """
    raw = _raw_series()
    _write_named(tmp_path, "baskets/ohlcv", "STALE", raw.iloc[:10])
    _write_wide(tmp_path, "breadth/_closes_cache.parquet", {"STALE": raw.values})
    r = pl.resolve_close("STALE", data_dir=str(tmp_path), min_last=IDX[-1])
    assert r.price_source == "closes_cache_UNADJUSTED"
    assert r.adjusted is False, "and it must be STAMPED, never silently mixed"
    assert r.series.index.max() == IDX[-1], "the whole window must survive"
    assert r.reason and "baskets_ohlcv" in r.reason, (
        "the passed-over stale rung must be named, or the fallback is silent")


def test_a_caller_that_refuses_unadjusted_gets_the_stale_adjusted_rung(tmp_path):
    """`allow_unadjusted=False` means 'rather lose the window than mix bases' — so the
    stale adjusted series is the best honest answer, with the staleness disclosed."""
    raw = _raw_series()
    _write_named(tmp_path, "baskets/ohlcv", "STALE", raw.iloc[:10])
    _write_wide(tmp_path, "breadth/_closes_cache.parquet", {"STALE": raw.values})
    r = pl.resolve_close("STALE", data_dir=str(tmp_path), min_last=IDX[-1],
                         allow_unadjusted=False)
    assert r.price_source == "baskets_ohlcv" and r.adjusted is True
    assert r.reason and "ends before" in r.reason


def test_min_last_default_reads_no_extra_file(store):
    """The cheap path must stay cheap on the render budget: with no min_last the first
    hit wins and later rungs are never opened."""
    r = pl.resolve_close("PAYER", data_dir=str(store))
    assert r.tried == ["baskets_ohlcv"]


# --------------------------------------------------------------------------- #
# 5. panel + overlay provenance
# --------------------------------------------------------------------------- #
def test_close_panel_stamps_every_name_and_counts_the_residual(store):
    panel, prov = pl.close_panel(["PAYER", "CACHEONLY", "NOWHERE"], data_dir=str(store))
    assert prov["price_source"]["PAYER"] == "baskets_ohlcv"
    assert prov["price_source"]["CACHEONLY"] == "closes_cache_UNADJUSTED"
    assert prov["price_source"]["NOWHERE"] is None
    assert prov["names_on_unadjusted_basis"] == 1
    assert prov["unadjusted_tickers"] == ["CACHEONLY"]
    assert prov["unresolved_tickers"] == ["NOWHERE"]
    assert set(panel.columns) == {"PAYER", "CACHEONLY"}


def test_overlay_replaces_values_but_preserves_the_column_set(store):
    """grade_us_board's coverage denominators and continuity clock are denominated in the
    panel's shape; a basis fix that silently narrowed it would move unrelated numbers."""
    cache = pd.read_parquet(store / "breadth/_closes_cache.parquet")
    cache.index = pd.to_datetime(cache.index)
    out, prov = pl.overlay_adjusted(cache, ["PAYER", "CACHEONLY"], data_dir=str(store))
    assert set(out.columns) == set(cache.columns), "column set must not change"
    assert prov["n_columns_rebased"] == 1
    assert out["PAYER"].iloc[0] == pytest.approx(100.0 / DIV_FACTOR)
    assert out["CACHEONLY"].equals(cache["CACHEONLY"]), "untouched name keeps its column"


def test_overlay_adds_an_admitted_name_absent_from_the_panel(store):
    """The admitted-but-uncached case: a board name resolvable on an adjusted rung is
    ADDED rather than dropped."""
    cache = pd.read_parquet(store / "breadth/_closes_cache.parquet")
    cache.index = pd.to_datetime(cache.index)
    _write_named(store, "baskets/ohlcv", "NEWNAME", _raw_series())
    out, prov = pl.overlay_adjusted(cache, ["NEWNAME"], data_dir=str(store))
    assert "NEWNAME" in out.columns
    assert prov["price_source"]["NEWNAME"] == "baskets_ohlcv"


def test_is_adjusted_is_tri_state():
    assert pl.is_adjusted("baskets_ohlcv") is True
    assert pl.is_adjusted("closes_cache_UNADJUSTED") is False
    assert pl.is_adjusted(None) is None and pl.is_adjusted("mystery") is None


def test_every_ladder_tag_classifies():
    """A rung whose tag is in neither family would stamp rows `price_basis: null` and
    read as 'pre-era' forever."""
    for src in pl.LADDER:
        assert pl.is_adjusted(src) is not None, src
