"""Pure-function + builder tests for the contrarian fragility tag (display-only).
No network. The disk-reading builder is exercised on a synthetic in-memory panel.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import crowding as cr  # noqa: E402


def test_fragility_fires_only_when_all_three_legs_elevated():
    # all three legs >= 80 and genuinely above the 50dma -> flag
    f = cr.fragility(rs_pctile=92, si_pctile=85, ext_pctile=88,
                     pct_vs_50dma=14.2, days_to_cover=6.4)
    assert f is not None
    assert f["rs_pctile"] == 92 and f["si_pctile"] == 85 and f["ext_pctile"] == 88
    assert f["pct_vs_50dma"] == 14.2 and f["days_to_cover"] == 6.4


def test_fragility_requires_every_leg():
    # crowded + extended but NOT shorted -> no flag (the conjunction is the point)
    assert cr.fragility(95, 40, 95, 12.0) is None
    # crowded + shorted but not extended
    assert cr.fragility(95, 95, 40, 12.0) is None
    # all pctiles high but not actually above the 50dma (pct <= 0) -> no flag
    assert cr.fragility(95, 95, 95, -1.0) is None
    # missing inputs degrade to None
    assert cr.fragility(None, 95, 95, 12.0) is None


def test_compute_fragility_on_synthetic_panel():
    # one obviously fragile name (FRAG: crowded leader, heavily shorted, extended)
    # vs a quiet laggard (CALM). Bench is flat so RS == price path.
    idx = pd.date_range("2023-01-02", periods=400, freq="B")
    bench = pd.Series(100.0, index=idx)
    frag = pd.Series(np.linspace(100, 320, 400), index=idx)          # strong uptrend
    frag.iloc[-1] = frag.iloc[-1] * 1.18                            # spike above 50dma
    calm = pd.Series(100 + np.sin(np.linspace(0, 12, 400)) * 2, index=idx)  # flat/choppy
    closes = pd.DataFrame({"FRAG": frag, "CALM": calm})
    si = pd.DataFrame({"days_to_cover": [9.0, 1.0]}, index=["FRAG", "CALM"])

    out = cr.compute_fragility(closes=closes, si=si, bench=bench)
    assert "FRAG" in out                       # crowded + shorted + extended
    assert "CALM" not in out                    # neither crowded, shorted, nor extended
    assert out["FRAG"]["days_to_cover"] == 9.0


def test_compute_fragility_degrades_without_si():
    idx = pd.date_range("2023-01-02", periods=300, freq="B")
    closes = pd.DataFrame({"X": pd.Series(np.linspace(100, 200, 300), index=idx)})
    # no days_to_cover column -> graceful empty map, never raises
    assert cr.compute_fragility(closes=closes, si=pd.DataFrame(), bench=pd.Series(100.0, index=idx)) == {}
