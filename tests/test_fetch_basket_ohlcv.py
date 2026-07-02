"""Write-path guard of scripts/fetch_basket_ohlcv: vendor placeholder rows (all-zero
OHLC from before a listing, e.g. DEC 2021→2023) must not be persisted to the deep
baskets OHLCV store. engine/basket_index already masks them at read time (#876); the
collector must stop re-writing them on refresh."""
import numpy as np
import pandas as pd

from scripts.fetch_basket_ohlcv import _scrub_placeholder_prices


def _frame(rows: dict) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(rows, orient="index",
                                columns=["open", "high", "low", "close", "volume"])
    df.index = pd.DatetimeIndex(df.index, name="Date")
    return df


def test_all_zero_placeholder_rows_dropped():
    df = _frame({
        "2021-01-04": [0.0, 0.0, 0.0, 0.0, 1_000_000],   # pre-listing placeholder
        "2023-11-29": [0.0, 0.0, 0.0, 0.0, 2_000_000],
        "2023-11-30": [10.0, 11.0, 9.5, 10.5, 500_000],  # first real print
    })
    out = _scrub_placeholder_prices(df)
    assert list(out.index) == [pd.Timestamp("2023-11-30")]
    assert (out["close"] > 0).all()


def test_partial_nonpositive_cells_masked_row_kept():
    df = _frame({"2024-01-02": [0.0, 11.0, 9.5, 10.5, 500_000]})
    out = _scrub_placeholder_prices(df)
    assert len(out) == 1
    assert np.isnan(out["open"].iloc[0])
    assert out["close"].iloc[0] == 10.5


def test_genuine_rows_untouched():
    df = _frame({
        "2024-01-02": [10.0, 11.0, 9.5, 10.5, 500_000],
        "2024-01-03": [10.5, 12.0, 10.4, 11.8, 600_000],
    })
    out = _scrub_placeholder_prices(df)
    pd.testing.assert_frame_equal(out, df)
