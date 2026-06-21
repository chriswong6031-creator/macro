"""Tests for engine.theme_downside_rs — down-day-conditional relative strength.

Primary tests use SYNTHETIC in-memory frames to prove the math deterministically.
One live-data smoke test is guarded with pytest.skip if the store is
unavailable (so CI stays green on machines without the data store).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(bench_rets: list[float], member_rets: dict[str, list[float]],
                added: str = "2020-01-01") -> dict:
    """Build a minimal group_flow _setup-like dict from raw return lists.

    We prepend a neutral (0%) day to every series so that pct_change() on the
    bench level yields all supplied bench_rets with no leading NaN.
    The idx and rets DataFrame include the prepended row; callers pass
    lookback_d = len(bench_rets) to target only the intended window.
    """
    n = len(bench_rets)
    for t, r in member_rets.items():
        assert len(r) == n, f"member {t} length must equal len(bench_rets)={n}"

    # Extra row at the start so pct_change has no NaN over the window of interest.
    bench_full  = [0.0] + list(bench_rets)
    n_full      = n + 1
    idx         = pd.bdate_range("2020-01-01", periods=n_full)

    bench_r     = pd.Series(bench_full, index=idx)
    bench_level = (1 + bench_r).cumprod()

    closes_data, rets_data = {}, {}
    for t, r_list in member_rets.items():
        full_rets = [0.0] + list(r_list)
        s = pd.Series(full_rets, index=idx)
        closes_data[t] = (1 + s).cumprod().values
        rets_data[t]   = full_rets

    closes_df = pd.DataFrame(closes_data, index=idx)
    rets_df   = pd.DataFrame(rets_data,   index=idx)

    members = [{"ticker": t, "added": added, "removed": None} for t in member_rets]
    mem = {
        "baskets": {
            "basket_a": {
                "members":  members,
                "name":     "Basket A",
                "name_zh":  "篮子A",
                "category": "Test",
                "tags":     [],
            }
        }
    }
    return {"closes": closes_df, "rets": rets_df, "idx": idx,
            "bench": bench_level, "mem": mem, "region": "us"}


def _trio(n: int, down_ret: float, up_ret: float) -> dict[str, list[float]]:
    """Three identical members alternating down_ret / up_ret — satisfies _MIN_MEMBERS=3."""
    series = [down_ret if i % 2 == 0 else up_ret for i in range(n)]
    return {"A": series, "B": series, "C": series}


def _run(state: dict, lookback_d: int) -> dict:
    """Call downside_rs with a synthetic state by monkey-patching group_flow._setup."""
    import engine.group_flow as gf
    from engine import theme_downside_rs as M

    original = gf._setup
    gf._setup = lambda region="us": state
    try:
        result = M.downside_rs(region="us", lookback_d=lookback_d)
    finally:
        gf._setup = original
    return result


# ---------------------------------------------------------------------------
# Synthetic-data tests
# ---------------------------------------------------------------------------

class TestDownsideRsBasicMath:

    def test_holds_up_alpha_and_capture(self):
        """Three identical members at −1% on down days vs −2% bench → alpha=+1%, capture=0.5."""
        n = 20                                            # window of interest
        bench_rets = [-0.02, 0.02] * (n // 2)           # 10 down, 10 up
        members    = _trio(n, down_ret=-0.01, up_ret=0.03)
        state      = _make_state(bench_rets, members)
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["n_down_days"] == 10
        assert r["lookback"] == n
        assert r["down_day_alpha"] == pytest.approx(0.01, abs=1e-6)
        assert r["down_capture"]   == pytest.approx(0.5,  abs=1e-6)
        assert r["holds_up"] is True

    def test_underperforms_on_down_days(self):
        """Three members at −4% on down days vs −2% bench → alpha=−2%, capture=2.0."""
        n = 20
        bench_rets = [-0.02, 0.02] * (n // 2)
        members    = _trio(n, down_ret=-0.04, up_ret=0.01)
        state      = _make_state(bench_rets, members)
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_day_alpha"] == pytest.approx(-0.02, abs=1e-6)
        assert r["down_capture"]   == pytest.approx(2.0,   abs=1e-6)
        assert r["holds_up"] is False

    def test_down_capture_below_one_sets_holds_up(self):
        """Basket loses 75% of bench decline → capture=0.75 → holds_up=True."""
        n = 20
        bench_rets = [-0.04, 0.02] * (n // 2)
        members    = _trio(n, down_ret=-0.03, up_ret=0.01)
        state      = _make_state(bench_rets, members)
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_capture"] == pytest.approx(0.75, abs=1e-6)
        assert r["holds_up"] is True

    def test_n_down_days_counted_correctly(self):
        """10 down days + 20 up days — only 10 should be counted."""
        n = 30
        bench_rets = [-0.01] * 10 + [0.01] * 20
        rets_a     = [-0.005] * 10 + [0.015] * 20
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_a, "C": rets_a})
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["n_down_days"] == 10

    def test_all_up_days_returns_neutral_skeleton(self):
        """No benchmark down days → fewer than _MIN_DOWN_DAYS → neutral skeleton."""
        n = 10
        bench_rets = [0.01] * n
        rets_a     = [0.015] * n
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_a, "C": rets_a})
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_day_alpha"] is None
        assert r["holds_up"] is False
        assert r["n_down_days"] == 0

    def test_lookback_subsets_to_last_rows(self):
        """lookback_d=10 on 30-row history → only last 10 rows used."""
        n = 30
        # first 20 rows are all UP, last 10 rows are all DOWN
        bench_rets = [0.01] * 20 + [-0.01] * 10
        rets_a     = [0.015] * 20 + [-0.005] * 10
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_a, "C": rets_a})
        # total history = n+1 = 31 rows; lookback_d=10 → tail 10 rows all DOWN
        res = _run(state, lookback_d=10)
        r = res["basket_a"]
        assert r["n_down_days"] == 10
        assert r["lookback"] == 10

    def test_empty_setup_returns_empty_dict(self):
        """If _setup returns None the public function returns {} without raising."""
        import engine.group_flow as gf
        from engine import theme_downside_rs as M

        original = gf._setup
        gf._setup = lambda region="us": None
        try:
            result = M.downside_rs(region="us")
        finally:
            gf._setup = original
        assert result == {}

    def test_short_history_returns_empty(self):
        """n_full=6 with lookback_d=63 → guard (6 < 63) triggers → {}."""
        n = 5
        bench_rets = [-0.01, 0.01, -0.01, 0.01, -0.01]
        rets_a     = [-0.005, 0.015, -0.005, 0.015, -0.005]
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_a, "C": rets_a})
        # n_full = 6; guard: 6 < max(63, 10) = 63 → {}
        res = _run(state, lookback_d=63)
        assert res == {}

    def test_output_keys_present(self):
        """Every result dict must contain the five expected keys."""
        n = 20
        bench_rets = [-0.02, 0.02] * (n // 2)
        members    = _trio(n, down_ret=-0.01, up_ret=0.03)
        state      = _make_state(bench_rets, members)
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        for key in ("down_day_alpha", "down_capture", "holds_up", "n_down_days", "lookback"):
            assert key in r, f"missing key: {key}"

    def test_median_cross_sectional_used(self):
        """Three asymmetric members: median drives the result (proves median not mean).

        Down days: A=−1%, B=−5%, C=−1.5% → sorted [−5,−1.5,−1] → median=−1.5%.
        Bench=−2%.  alpha = −1.5% − (−2%) = +0.5%.
        down_capture = −1.5% / −2% = 0.75.

        (Mean would be −2.5%, giving alpha=−0.5% and capture=1.25 — opposite verdict.)
        """
        n = 10
        bench_rets = [-0.02, 0.02] * (n // 2)    # 5 down, 5 up
        rets_a = [-0.010, 0.03] * (n // 2)
        rets_b = [-0.050, 0.03] * (n // 2)
        rets_c = [-0.015, 0.03] * (n // 2)
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_b, "C": rets_c})
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_day_alpha"] == pytest.approx(0.005, abs=1e-6)
        assert r["down_capture"]   == pytest.approx(0.75,  abs=1e-6)
        assert r["holds_up"] is True

    def test_too_few_members_returns_neutral(self):
        """Basket with only 2 live members hits _MIN_MEMBERS guard → neutral skeleton."""
        n = 20
        bench_rets = [-0.02, 0.02] * (n // 2)
        rets_a     = [-0.01, 0.03] * (n // 2)
        state = _make_state(bench_rets, {"A": rets_a, "B": rets_a})   # 2 < 3
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_day_alpha"] is None
        assert r["n_down_days"] == 0

    def test_holds_up_false_when_worse_than_benchmark(self):
        """Members lose 50% MORE than benchmark (capture=1.5, alpha<0) → holds_up=False."""
        n = 20
        bench_rets = [-0.02, 0.02] * (n // 2)
        members    = _trio(n, down_ret=-0.03, up_ret=0.02)   # 50% worse, capture=1.5
        state      = _make_state(bench_rets, members)
        res = _run(state, lookback_d=n)
        r = res["basket_a"]
        assert r["down_capture"] == pytest.approx(1.5, abs=1e-6)
        assert r["holds_up"] is False


# ---------------------------------------------------------------------------
# Live-data smoke test (guarded)
# ---------------------------------------------------------------------------

class TestDownsideRsLiveSmoke:

    def test_live_us_region(self):
        from engine import theme_downside_rs as M
        import engine.group_flow as gf

        try:
            s = gf._setup(region="us")
        except Exception:
            pytest.skip("data store unavailable")

        if s is None or len(s.get("idx", [])) == 0:
            pytest.skip("no US data in store")

        result = M.downside_rs(region="us", lookback_d=63)

        assert isinstance(result, dict)

        if result:
            bid, r = next(iter(result.items()))
            for key in ("down_day_alpha", "down_capture", "holds_up", "n_down_days", "lookback"):
                assert key in r, f"basket {bid} missing key: {key}"
            assert isinstance(r["holds_up"], bool)
            assert isinstance(r["n_down_days"], int)
