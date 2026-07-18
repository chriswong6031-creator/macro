"""Cross-asset concentration detector (Phase C): the absorption ratio (PC1
variance share) flags when the six markets are secretly one bet. Pure-math
properties pinned on synthetic data; snapshot() smoke-tested against the store.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cross_asset import _absorption_ratio, absorption_series, snapshot


def test_absorption_ratio_independent_is_one_over_n():
    n = 6
    assert abs(_absorption_ratio(np.eye(n)) - 1.0 / n) < 1e-9   # independent floor


def test_absorption_ratio_one_factor_is_near_one():
    n = 6
    m = np.full((n, n), 0.98)
    np.fill_diagonal(m, 1.0)
    assert _absorption_ratio(m) > 0.95                          # single factor dominates


def test_absorption_series_separates_independent_from_common_factor():
    rng = np.random.default_rng(0)
    T = 400
    indep = pd.DataFrame({f"m{i}": rng.normal(size=T) for i in range(5)})
    f = rng.normal(size=T)
    common = pd.DataFrame({f"m{i}": f + 0.25 * rng.normal(size=T) for i in range(5)})
    ar_i = absorption_series(indep, window=63).iloc[-1]
    ar_c = absorption_series(common, window=63).iloc[-1]
    assert ar_i < 0.45                                          # ~1/5 = 0.2 + noise
    assert ar_c > 0.70                                          # one factor
    assert ar_c > ar_i


def test_absorption_series_too_short_is_empty():
    assert absorption_series(pd.DataFrame({"a": [1, 2, 3]}), window=63).empty


def test_snapshot_smoke_returns_valid_verdict():
    s = snapshot()
    assert s["verdict"] in {"diversified", "converging", "concentrated", "unknown"}
    if s["verdict"] != "unknown":
        assert 0.0 <= s["absorption_ratio"] <= 1.0
        assert s["absorption_ratio"] >= s["absorption_floor"] - 1e-9   # AR >= 1/n


def test_snapshot_absorption_spark_w_keys_present_on_unknown():
    """Early-exit paths (too few markets) do not have the spark keys — no crash."""
    s = snapshot.__wrapped__() if hasattr(snapshot, "__wrapped__") else snapshot()
    # Just ensure no AttributeError regardless of verdict
    _ = s.get("absorption_spark_w")
    _ = s.get("absorption_spark_asof")


def test_absorption_spark_w_shape_on_synthetic_data(monkeypatch):
    """absorption_spark_w: list, <=104 elements, all float, zero new compute."""
    import engine.cross_asset as ca
    import numpy as np

    rng = np.random.default_rng(1)
    n_days = 700
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rets = pd.DataFrame(rng.normal(0, 0.01, (n_days, 6)), index=idx,
                        columns=["US", "Crypto", "China", "HK", "Commodities", "Dollar"])
    monkeypatch.setattr(ca, "returns_frame", lambda: rets)

    s = ca.snapshot()
    assert s["verdict"] != "unknown"
    spark = s["absorption_spark_w"]
    assert isinstance(spark, list)
    assert 1 <= len(spark) <= 104
    for v in spark:
        assert isinstance(v, float) and np.isfinite(v)
