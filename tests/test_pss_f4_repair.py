from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.research import pss_f4_repair as repair
from scripts.research import pss_f4_semivar as semivar


def _synthetic_ohlcv(n: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    idx = pd.bdate_range("2020-01-02", periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    open_ = close * np.exp(rng.normal(0, 0.004, n))
    spread = np.abs(rng.normal(0.012, 0.004, n))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.lognormal(15.5, 0.35, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_first_actions_stamps_confirmation_not_watch_start() -> None:
    condition = np.zeros(10, dtype=bool)
    condition[[5, 7]] = True

    result = repair.first_actions(np.array([2, 4, 6]), condition, horizon=3)

    assert result == [(5, 1), (7, 1)]
    assert all(delay >= 0 for _, delay in result)


def test_causal_persistence_stamps_pth_bar_not_run_onset() -> None:
    x = np.array([3.0, 0.8, 0.7, 0.6, 0.5, 2.0])
    base = np.ones(len(x))
    hi = np.full(len(x), 2.0)

    historical = semivar._sustained_run_fires(x, base, hi, P=3)
    causal = semivar._causal_sustained_run_fires(x, base, hi, P=3)

    assert np.flatnonzero(historical).tolist() == [1]
    assert np.flatnonzero(causal).tolist() == [3]


def test_feature_arrays_are_prefix_invariant() -> None:
    x = _synthetic_ohlcv()
    market = x["close"].rolling(3, min_periods=1).mean().to_numpy()
    sector = x["close"].rolling(5, min_periods=1).mean().to_numpy()
    full = repair.feature_arrays(x, market, sector)

    for cut in (320, 410):
        prefix = repair.feature_arrays(x.iloc[:cut], market[:cut], sector[:cut])
        for key in prefix:
            np.testing.assert_allclose(
                np.asarray(prefix[key]),
                np.asarray(full[key])[:cut],
                equal_nan=True,
                err_msg=f"future data changed causal feature {key}",
            )


def test_align_context_never_backfills_from_the_future() -> None:
    source = pd.Series(
        [101.0, 102.0],
        index=pd.to_datetime(["2024-01-03", "2024-01-05"]),
    )
    target = pd.to_datetime(["2024-01-02", "2024-01-04", "2024-01-05"])

    aligned = repair.align_context(source, target)

    assert np.isnan(aligned[0])
    assert aligned[1] == 101.0
    assert aligned[2] == 102.0


def test_paired_delta_uses_per_name_binary_rates() -> None:
    rows = []
    for sym, base_hits, candidate_hits in (
        ("A", [False, False, True], [True, True]),
        ("B", [False, False, False], [False, True]),
    ):
        for i, hit in enumerate(base_hits):
            rows.append(
                {
                    "sym": sym,
                    "kind": "inc",
                    "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "mae": -10.0,
                    "w5": hit,
                    "called": hit,
                    "tail10": True,
                    "tdt": -3.0,
                    "delay": 0,
                }
            )
        for i, hit in enumerate(candidate_hits):
            rows.append(
                {
                    "sym": sym,
                    "kind": "candidate",
                    "date": pd.Timestamp("2024-02-01") + pd.Timedelta(days=i),
                    "mae": -5.0,
                    "w5": hit,
                    "called": hit,
                    "tail10": False,
                    "tdt": 1.0,
                    "delay": 2,
                }
            )

    delta = repair.paired_delta(pd.DataFrame(rows), "candidate")

    assert delta["names"] == 2
    assert delta["mae"] == 5.0
    assert delta["w5"] > 0
    assert delta["called"] > 0
    assert delta["tail10"] == 100.0
