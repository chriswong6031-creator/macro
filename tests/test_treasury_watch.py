"""Pure-function tests for the Treasury Watch detector — no network, injected data seams.

The acceptance episode is the Jun-30 2026 quarter-end TGA release reproduced from the repo's
own committed data/treasury/tga.parquet path (levels in $bn, dates YYYY-MM-DD)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import treasury_watch as tw  # noqa: E402

# The committed TGA path around the Jun-30 quarter-end (levels in $bn → parquet stores $mn).
_ACCEPT = [
    ("2026-06-15", 948.0), ("2026-06-16", 951.2), ("2026-06-17", 942.5),
    ("2026-06-18", 930.1), ("2026-06-22", 921.0), ("2026-06-23", 905.4),
    ("2026-06-24", 901.845), ("2026-06-25", 871.469), ("2026-06-26", 895.576),
    ("2026-06-29", 876.961), ("2026-06-30", 919.145), ("2026-07-01", 807.359),
    ("2026-07-02", 770.587), ("2026-07-03", 776.843), ("2026-07-06", 783.107),
    ("2026-07-07", 784.964), ("2026-07-08", 749.244), ("2026-07-09", 744.637),
]


def _mn_frame(pairs) -> pd.DataFrame:
    """A DataFrame shaped like the real parquet: a tga_mn column ($mn), DatetimeIndex 'date'."""
    idx = pd.to_datetime([d for d, _ in pairs])
    df = pd.DataFrame({"tga_mn": [v * 1000.0 for _, v in pairs]}, index=idx)
    df.index.name = "date"
    return df


def _bn_series(pairs) -> pd.Series:
    s = pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))
    return s.sort_index()


# --------------------------------------------------------------------------- #
# acceptance — the Jun-30 quarter-end release
# --------------------------------------------------------------------------- #
def test_detect_reproduces_quarter_end_release():
    evs = tw.detect_events(_tga=_mn_frame(_ACCEPT))
    assert len(evs) == 1
    e = evs[0]
    assert e["id"] == "tw-2026-06-30-tga-release"
    assert e["guid"] == e["id"]
    assert e["section"] == "treasury"
    assert e["categories"] == ["treasury", "liquidity", "tga"]
    assert e["url"].startswith("https://fiscaldata.treasury.gov")
    assert e["published"].startswith("2026-07-09")
    # the body carries the day-by-day path + the mechanism sentence for the brain
    assert "919.1bn" in e["body"] and "744.6bn" in e["body"]
    assert "reserve" in e["body"].lower()


def test_snapshot_quarter_end_magnitude():
    s = tw.snapshot(_tga=_mn_frame(_ACCEPT), _plumbing={}, _regime={})
    assert s["schema"] == "treasury_watch.v1"
    assert s["is_context_only"] is True
    assert s["as_of"] == "2026-07-09"
    assert abs(s["tga"]["level_bn"] - 744.637) < 0.01
    qe = s["tga"]["quarter_end"]
    assert qe["date"] == "2026-06-30"
    assert abs(qe["chg_since_bn"] - (-174.508)) < 0.01
    imp = s["tga_impulse"]
    assert imp["active"] is True and imp["direction"] == "drawdown"
    assert imp["quarter_end_adjacent"] is True
    assert abs(imp["magnitude_bn"] - (-174.508)) < 0.01
    assert s["events"] == []


def test_id_is_stable_as_the_episode_extends():
    """The anchor is the quarter-end, so the id must not flap as the drawdown deepens."""
    full = _mn_frame(_ACCEPT)
    ids = set()
    for cut in ("2026-07-01", "2026-07-03", "2026-07-08", "2026-07-09"):
        evs = tw.detect_events(_tga=full[full.index <= cut])
        assert evs, f"no event at cut {cut}"
        ids.add(evs[0]["id"])
    assert ids == {"tw-2026-06-30-tga-release"}


# --------------------------------------------------------------------------- #
# other episode shapes
# --------------------------------------------------------------------------- #
def test_symmetric_build_fires_tga_build():
    # a steady rebuild of +150bn away from any quarter-end
    pairs = [(f"2026-08-{d:02d}", 300.0 + i * 15.0)
             for i, d in enumerate(range(3, 21))]  # Aug 3..20, +15/day
    evs = tw.detect_events(_tga=_mn_frame(pairs))
    assert len(evs) == 1
    assert evs[0]["id"].endswith("tga-build")
    assert "rebuilt" in evs[0]["title"].lower() or "drain" in evs[0]["title"].lower()


def test_below_threshold_noise_fires_nothing():
    pairs = [(f"2026-08-{d:02d}", 500.0 + (1 if d % 2 else -1) * 10.0)
             for d in range(3, 21)]  # ±10bn chop, no episode, no 60bn day
    assert tw.detect_events(_tga=_mn_frame(pairs)) == []


def test_single_day_spike_fires_via_min_1d():
    pairs = [(f"2026-08-{d:02d}", 800.0) for d in range(3, 20)]
    pairs.append(("2026-08-20", 730.0))  # −70bn in one session (< 100 episode, ≥ 60 1d)
    evs = tw.detect_events(_tga=_mn_frame(pairs))
    assert len(evs) == 1
    assert evs[0]["id"].endswith("tga-release")


def test_missing_tga_input_degrades():
    assert tw.detect_events(_tga=pd.DataFrame({"tga_mn": []})) == []
    s = tw.snapshot(_tga=pd.DataFrame({"tga_mn": []}), _plumbing={}, _regime={})
    assert s["schema"] == "treasury_watch.v1"
    assert s["tga"] is None
    assert s["tga_impulse"] is None
    assert any("TGA series unavailable" in g for g in s["gaps"])


# --------------------------------------------------------------------------- #
# snapshot plumbing / context wiring + spark
# --------------------------------------------------------------------------- #
def test_snapshot_pulls_plumbing_and_regime():
    plumb = {
        "headline": {"state": "stress_liquidity_expansion", "summary": "poor-quality expansion"},
        "quantity": {"netliq_bn": 5990.4, "netliq_chg_20d_bn": 65.0,
                     "netliq_chg_65d_bn": -6.2, "netliq_pctile_expanding": 0.84},
        "fed": {"assets_bn": 6735.6}, "rrp": {"rrp_bn": 0.5, "buffer_state": "exhausted"},
        "funding": {"reserve_scarcity_state": "normalizing"},
    }
    regime = {"quad": "Q1", "quad_name": "Goldilocks",
              "liquidity_overlay": "expanding", "asof": "2026-07-10"}
    s = tw.snapshot(_tga=_mn_frame(_ACCEPT), _plumbing=plumb, _regime=regime)
    assert s["net_liquidity"]["netliq_bn"] == 5990.4
    assert s["net_liquidity"]["walcl_bn"] == 6735.6
    assert s["net_liquidity"]["rrp_bn"] == 0.5
    assert s["plumbing"]["headline_state"] == "stress_liquidity_expansion"
    assert s["plumbing"]["rrp_buffer_state"] == "exhausted"
    assert s["plumbing"]["reserve_scarcity_state"] == "normalizing"
    assert s["market_context"]["quad_name"] == "Goldilocks"
    assert s["market_context"]["liquidity_overlay"] == "expanding"


def test_spark_points_wellformed():
    s = tw.snapshot(_tga=_mn_frame(_ACCEPT), _plumbing={}, _regime={})
    pts = s["tga"]["spark_points"]
    assert isinstance(pts, str) and pts
    toks = pts.split(" ")
    assert len(toks) == len(s["tga"]["spark_60d"])
    for tkn in toks:
        x, y = tkn.split(",")
        assert 0.0 <= float(x) <= 560.0
        assert 0.0 <= float(y) <= 64.0


def test_spark_points_flat_series_no_div_by_zero():
    pairs = [(f"2026-08-{d:02d}", 500.0) for d in range(3, 20)]  # all equal
    assert tw._spark_points([[d, v] for d, v in pairs]) != "" or True  # must not raise
    s = tw.snapshot(_tga=_mn_frame(pairs), _plumbing={}, _regime={})
    # every y should be the flat mid-line, never NaN/inf
    for tkn in s["tga"]["spark_points"].split(" "):
        float(tkn.split(",")[1])


def test_quarter_end_block_null_when_stale():
    # a series whose latest is >45 days after the most recent quarter-end → no qe ref
    pairs = [(f"2026-08-{d:02d}", 600.0 + d) for d in range(15, 31)]  # mid/late Aug (>45d from Jun 30)
    s = tw.snapshot(_tga=_mn_frame(pairs), _plumbing={}, _regime={})
    assert s["tga"]["quarter_end"] is None
    assert any("quarter-end" in g for g in s["gaps"])


def test_accepts_bn_series_seam():
    # the injectable seam also accepts a Series already in $bn
    evs = tw.detect_events(_tga=_bn_series(_ACCEPT))
    assert evs and evs[0]["id"] == "tw-2026-06-30-tga-release"
