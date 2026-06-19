"""International thematic baskets — engine + seeder contract.

Synthetic-frame unit tests for the cross-country composite/breadth math (no caches needed) plus
integration smokes that no-op when the intl_search cache is absent (CI shard), mirroring
tests/test_theme_scoring.py's style.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import baskets_intl as bi
from engine import narrative_rotation as nr


def _frame():
    idx = pd.date_range("2022-01-03", periods=300, freq="B")
    rng = np.random.default_rng(0)
    cols = [f"T{i}" for i in range(10)]
    px = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, size=(len(idx), len(cols))), axis=0),
                      index=idx, columns=cols)
    meta = pd.DataFrame({"weight": np.linspace(5, 0.5, len(cols))}, index=cols)
    return px, meta


def test_build_composite_is_a_rebased_level_series():
    px, meta = _frame()
    comp = bi.build_composite(px, meta)
    assert comp is not None and "close" in comp.columns
    assert len(comp) == len(px)
    c = comp["close"].dropna()
    assert c.iloc[0] == 100.0                      # rebased to 100 at the first valid day
    assert (c > 0).all() and np.isfinite(c).all()


def test_build_composite_handles_missing_weights():
    px, _ = _frame()
    assert bi.build_composite(px, pd.DataFrame({"nope": [1]})) is None   # no weight column → None


def test_region_cfg_intl_is_wired():
    cfg = nr._region_cfg("intl")
    assert cfg is not None
    assert cfg["bench_label"] == "Intl ex-US" and cfg["group"] == "intl"
    assert cfg["bench_default"] == bi.BENCHMARK_DEFAULT
    assert callable(cfg["membership"]) and callable(cfg["closes"])


# --------------------------------------------------------------- integration smoke
def test_seeder_only_emits_cache_validated_tickers():
    mem = bi._membership()
    closes = bi._closes()
    if mem is None or closes is None:              # caches absent in CI shard
        return
    cols = set(closes.columns)
    for bid, b in mem["baskets"].items():
        present = [m["ticker"] for m in b["members"] if m["ticker"] in cols]
        assert len(present) >= 3, f"{bid} has <3 cache-present members"
        # every emitted ticker must be a real column (no hallucinated symbols)
        assert all(m["ticker"] in cols for m in b["members"]), f"{bid} has an off-cache ticker"


def test_compute_intl_baskets_contract():
    d = bi.compute_intl_baskets()
    if d is None:                                  # caches absent in CI shard
        return
    assert d["benchmark_label"] == "Intl ex-US"
    assert d["baskets"], "expected at least one intl basket"
    b0 = d["baskets"][0]
    assert b0["n_members"] >= 3 and "perf" in b0
    assert d["chart"]["bench"][-1] is not None      # composite benchmark populated
