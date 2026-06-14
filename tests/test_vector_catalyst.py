"""Bitcoin Vector scheduled-catalyst (FOMC / jobs) window (D-vec-CAT).
Deterministic calendar logic, no network.

Run: .venv/bin/python -m tests.test_vector_catalyst
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from scripts.build_vector import catalyst_window, _next_first_friday  # noqa: E402

CFG = {"imminent_days": 3}


def test_picks_nearest_event_and_imminent_flag():
    # 2026-06-14: next FOMC 2026-06-17 (3d), next NFP 2026-07-03 (first Fri July)
    c = catalyst_window("2026-06-14", CFG)
    assert c["next_event"] == "FOMC" and c["days"] == 3 and c["imminent"] is True
    assert c["fomc_days"] == 3
    # a week earlier -> FOMC is 10d out, jobs report (first Fri June = 2026-06-05) is sooner
    c2 = catalyst_window("2026-06-01", CFG)
    assert c2["next_event"] == "Jobs report" and c2["imminent"] is False


def test_first_friday_logic():
    assert _next_first_friday(pd.Timestamp("2026-06-01")) == pd.Timestamp("2026-06-05")
    assert _next_first_friday(pd.Timestamp("2026-06-06")) == pd.Timestamp("2026-07-03")  # rolled to July
    # exactly on the first Friday counts as today
    assert _next_first_friday(pd.Timestamp("2026-07-03")) == pd.Timestamp("2026-07-03")


def test_tz_aware_input_is_handled():
    c = catalyst_window(pd.Timestamp("2026-06-14", tz="UTC"), CFG)   # tz-aware must not crash
    assert c and c["days"] >= 0


if __name__ == "__main__":
    for fn in [test_picks_nearest_event_and_imminent_flag, test_first_friday_logic,
               test_tz_aware_input_is_handled]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector catalyst tests passed")
