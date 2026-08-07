"""Guards for the adjusted-basis re-run's BASIS CONTROL.

Synthetic stores only — no repo data, no network.

The thing worth guarding here is not the arithmetic, it is the confound #4698 hit and
warned about: `baskets/ohlcv` carries the large-cap sleeve ~2 years deeper than the
breadth cache, so a naive basis swap grows the studied population and prints a COVERAGE
change as a basis effect (#4698 measured +31%, 22,616 → 29,675).

`pin_and_intersect` is the defence, so every test below builds a store where the adjusted
source is DELIBERATELY deeper and asymmetric, and asserts the trap is closed — including
the mutation that proves the mask check can actually see a failure.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load(name: str):
    """Import a sibling research module by path, registered before exec so a module
    carrying a ``@dataclass`` (price_ladder.Resolved) can resolve its own annotations."""
    if name in sys.modules:
        return sys.modules[name]
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


RR = _load("veto_leg_isolation_adjusted_rerun")
PL = _load("price_ladder")
MIN_HIST = 60          # small floor so the fixtures stay cheap


# --------------------------------------------------------------- fixtures --
def _frame(names, idx, base=100.0, step=1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {t: base + step * np.arange(len(idx)) + i for i, t in enumerate(names)}, index=idx)


def _stores(tmp_path: Path, names=("AAA", "BBB"), n=700, late_start=500):
    """A synthetic store shaped like the real confound.

    #4698's +31% came from the large-cap `breadth` cache starting 2025-03-18 while
    `baskets/ohlcv` carries the same names back to 2014 — so INSIDE the studied window the
    adjusted source has sessions the cache does not. A fixture where the adjusted source
    is merely older would not reproduce it: `close_panel(start=...)` clips the pre-window
    history away, and the confound would be closed for the wrong reason.

    Here BBB is the late-starting sleeve: absent from the cache for the first
    ``late_start`` sessions of the frame, present in the adjusted store throughout.
    """
    d = tmp_path / "data"
    (d / "baskets" / "ohlcv").mkdir(parents=True)
    (d / "breadth").mkdir(parents=True)
    idx = pd.bdate_range("2022-01-01", periods=n)
    cache = _frame(names, idx)
    cache.iloc[:late_start, cache.columns.get_loc("BBB")] = np.nan
    cache.to_parquet(d / "breadth" / "_closes_cache.parquet")
    adj = _frame(names, idx, base=90.0)                   # different VALUES too
    for t in names:
        adj[[t]].rename(columns={t: "close"}).to_parquet(d / "baskets" / "ohlcv" / f"{t}.parquet")
    return str(d), cache, adj


# ------------------------------------------- 1. the coverage trap is closed --
def test_pin_and_intersect_closes_the_coverage_trap(tmp_path):
    data_dir, cache, _adj = _stores(tmp_path)
    adj_panel, prov = PL.close_panel(
        list(cache.columns), asof=str(cache.index[-1].date()),
        start=str(cache.index[0].date()), data_dir=data_dir, allow_unadjusted=False)

    # THE TRAP EXISTS on this fixture — without this the test proves nothing. INSIDE the
    # studied window the adjusted source carries sessions the cache does not, so an
    # unpinned swap would hand the late-starting sleeve extra warm-up and grow n.
    cache_cells = int(cache.notna().to_numpy().sum())
    adj_cells = int(adj_panel.notna().to_numpy().sum())
    assert adj_cells > cache_cells, "fixture does not reproduce the coverage confound"
    assert adj_cells / cache_cells > 1.20, "confound too small to be a meaningful guard"

    pc, pa, proof = RR.pin_and_intersect(cache, adj_panel, min_hist=MIN_HIST)

    assert proof["masks_identical"] is True
    assert proof["mask_mismatches"] == 0
    assert proof["identical_index"] is True
    assert proof["identical_columns"] is True
    # population held EXACTLY at the cache's — the trap's signature was a growing n
    assert pc.shape == pa.shape == cache.shape
    assert proof["intersection_cells"] == cache_cells
    assert proof["cells_dropped_from_adjusted"] == adj_cells - cache_cells
    assert pc.index.equals(cache.index)
    # the late sleeve keeps exactly its cache-observed cells, no more
    assert int(pa["BBB"].notna().sum()) == int(cache["BBB"].notna().sum())
    # and the VALUES really do differ, or we would be comparing a panel with itself
    obs = pc.notna().to_numpy()
    assert not np.allclose(pc.to_numpy()[obs], pa.to_numpy()[obs])


def test_pin_and_intersect_is_symmetric_about_missing_dates(tmp_path):
    """A date the CACHE carries and the adjusted source does not must ALSO be dropped
    from both. Masking adjusted down to the cache would leave this half open."""
    data_dir, cache, _ = _stores(tmp_path)
    adj_panel, _ = PL.close_panel(
        list(cache.columns), asof=str(cache.index[-1].date()),
        start=str(cache.index[0].date()), data_dir=data_dir, allow_unadjusted=False)
    # the hole must sit where BOTH names are observed in the cache, or the "did it leak
    # into a sibling" check would be reading BBB's own late start instead
    hole = cache.index[600]
    assert bool(pd.notna(cache.loc[hole, "AAA"])) and bool(pd.notna(cache.loc[hole, "BBB"]))
    adj_panel.loc[hole, "AAA"] = np.nan            # adjusted-side hole

    pc, pa, proof = RR.pin_and_intersect(cache, adj_panel, min_hist=MIN_HIST)
    assert proof["masks_identical"] is True
    assert bool(pd.isna(pc.loc[hole, "AAA"])), "cache side kept a cell adjusted lacks"
    assert bool(pd.isna(pa.loc[hole, "AAA"]))
    assert bool(pd.notna(pc.loc[hole, "BBB"])), "the hole leaked into an unrelated name"
    assert bool(pd.notna(pa.loc[hole, "BBB"]))
    assert proof["cells_dropped_from_cache"] >= 1


def test_a_name_with_no_adjusted_source_leaves_both_columns(tmp_path):
    data_dir, cache, _ = _stores(tmp_path)
    cache["CCC"] = 50.0                            # in the cache, in no adjusted store
    adj_panel, prov = PL.close_panel(
        list(cache.columns), asof=str(cache.index[-1].date()),
        start=str(cache.index[0].date()), data_dir=data_dir, allow_unadjusted=False)
    assert "CCC" in prov["unresolved_tickers"]

    pc, pa, proof = RR.pin_and_intersect(cache, adj_panel, min_hist=MIN_HIST)
    assert "CCC" not in pc.columns and "CCC" not in pa.columns
    assert "CCC" in proof["dropped_tickers"]
    assert list(pc.columns) == list(pa.columns)
    assert proof["names_kept"] == 2 and proof["names_dropped"] == 1


def test_mask_gate_can_see_a_one_sided_mask(tmp_path):
    """MUTATION: mask only one side and confirm `masks_identical` goes False. Without
    this, every `is True` assertion above would also pass on a gate wired to a constant."""
    data_dir, cache, _ = _stores(tmp_path)
    adj_panel, _ = PL.close_panel(
        list(cache.columns), asof=str(cache.index[-1].date()),
        start=str(cache.index[0].date()), data_dir=data_dir, allow_unadjusted=False)
    pc, pa, _ = RR.pin_and_intersect(cache, adj_panel, min_hist=MIN_HIST)

    broken = pa.copy()
    broken.iloc[5, 0] = np.nan                     # a one-sided hole, as a wrong pipeline
    mc, mb = pc.notna().to_numpy(), broken.notna().to_numpy()
    assert not np.array_equal(mc, mb)
    assert int((mc != mb).sum()) == 1


# ------------------------------------------------- 2. the ladder's contract --
def test_ladder_prefers_adjusted_and_refuses_the_cache_when_told(tmp_path):
    data_dir, cache, _ = _stores(tmp_path)
    r = PL.resolve_close("AAA", data_dir=data_dir, allow_unadjusted=False)
    assert r.ok and r.adjusted is True and r.price_source == "baskets_ohlcv"

    cache["DDD"] = 50.0
    cache.to_parquet(Path(data_dir) / "breadth" / "_closes_cache.parquet")
    refused = PL.resolve_close("DDD", data_dir=data_dir, allow_unadjusted=False)
    assert not refused.ok and refused.price_source is None
    allowed = PL.resolve_close("DDD", data_dir=data_dir, allow_unadjusted=True)
    assert allowed.ok and allowed.adjusted is False
    assert allowed.price_source == "closes_cache_UNADJUSTED"


def test_the_adjusted_run_never_admits_an_unadjusted_name(tmp_path):
    """The B column exists to remove a basis mix; a cache fallback inside it would put
    the mix straight back."""
    data_dir, cache, _ = _stores(tmp_path)
    cache["EEE"] = 50.0
    cache.to_parquet(Path(data_dir) / "breadth" / "_closes_cache.parquet")
    _panel, prov = PL.close_panel(
        list(cache.columns), asof=str(cache.index[-1].date()),
        start=str(cache.index[0].date()), data_dir=data_dir, allow_unadjusted=False)
    assert prov["names_on_unadjusted_basis"] == 0
    assert prov["resolved_from"]["closes_cache_UNADJUSTED"] == 0
    assert "EEE" in prov["unresolved_tickers"]


# --------------------------------------------------- 3. the vendoring receipt --
def test_vendored_ladder_is_byte_identical_to_its_source():
    """price_ladder.py is carried here from #4698 rather than re-implemented. The receipt
    must PROVE that, not assert it — and must not silently pass when the source ref is
    absent from a shallow checkout."""
    rec = RR.ladder_receipt()
    assert rec["local_sha256"] and len(rec["local_sha256"]) == 64
    if rec.get("source_sha256") is None:
        pytest.skip(f"source ref not in this checkout: {rec.get('note')}")
    assert rec["identical"] is True, "vendored ladder has drifted from #4698's copy"
    assert rec["source_sha256"] == rec["local_sha256"]
