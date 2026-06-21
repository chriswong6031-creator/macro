"""Test the overnight/intraday decomposition math (scripts/analyze_index_add_overnight)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import scripts.analyze_index_add_overnight as A  # noqa: E402


def _frames():
    idx = pd.bdate_range("2026-05-01", periods=12)
    rng = np.linspace(100, 112, 12)
    # distinct open/close paths for T and SPY so overnight != intraday
    op = pd.DataFrame({"T": rng + 0.5, "SPY": rng * 0.9 + 0.3}, index=idx)
    cl = pd.DataFrame({"T": rng + 1.0, "SPY": rng * 0.9 + 0.6}, index=idx)
    return op, cl


def test_overnight_plus_intraday_reconstructs_close_to_close():
    op, cl = _frames()
    d = op.index[8]                                   # effective date with >=5 days of runway before
    on_sum, intr_sum = A._decompose("T", d, op, cl)
    # property: overnight_t + intraday_t telescopes to SPY-relative close-to-close (opens cancel)
    e = cl.index.get_loc(d)
    expect = 0.0
    for k in range(A._WIN[0] + 1, A._WIN[1] + 1):     # [-4..0]
        i = e + k
        expect += (np.log(cl["T"].iloc[i] / cl["T"].iloc[i - 1])
                   - np.log(cl["SPY"].iloc[i] / cl["SPY"].iloc[i - 1]))
    assert abs((on_sum + intr_sum) - expect) < 1e-9


def test_decompose_degrades_when_ticker_missing():
    op, cl = _frames()
    assert A._decompose("MISSING", op.index[8], op, cl) is None
