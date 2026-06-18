"""Pure-function tests for the prediction-markets collector + engine — no network."""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import prediction_markets as pmc  # noqa: E402
from engine import prediction_markets as pme  # noqa: E402


def test_extract_outcomes_list_and_json():
    ev = {"markets": [
        {"groupItemTitle": "No change", "outcomePrices": ["0.92", "0.08"]},
        {"groupItemTitle": "25 bps cut", "outcomePrices": "[\"0.06\", \"0.94\"]"},  # JSON string
        {"question": "junk", "outcomePrices": None},                                # skipped
    ]}
    out = pmc.extract_outcomes(ev)
    assert out == [{"outcome": "No change", "prob": 0.92}, {"outcome": "25 bps cut", "prob": 0.06}]


def test_match_event_nearest_end_and_volume():
    # Forward-relative end dates so "nearest_end" (endDate >= today) is not time-bombed.
    soon = (date.today() + timedelta(days=3)).isoformat() + "T00:00:00Z"
    later = (date.today() + timedelta(days=45)).isoformat() + "T00:00:00Z"
    other = (date.today() + timedelta(days=14)).isoformat()
    evs = [
        {"title": "Fed Decision (soon)?", "endDate": soon, "markets": [1], "volume": 10},
        {"title": "Fed Decision (later)?", "endDate": later, "markets": [1], "volume": 99},
        {"title": "World Cup", "endDate": other, "markets": [1], "volume": 999},
    ]
    near = pmc.match_event(evs, "Fed Decision", "nearest_end")
    assert near["title"] == "Fed Decision (soon)?"           # soonest future end
    vol = pmc.match_event(evs, "Fed Decision", "max_volume")
    assert vol["title"] == "Fed Decision (later)?"           # highest volume
    assert pmc.match_event(evs, "recession", "nearest_end") is None


def test_build_panel_with_change():
    df = pd.DataFrame([
        {"snapshot_date": "2026-06-13", "event_key": "fed_next", "event_title": "Fed Decision in June?",
         "end_date": "2026-06-17", "outcome": "No change", "prob": 0.90},
        {"snapshot_date": "2026-06-13", "event_key": "fed_next", "event_title": "Fed Decision in June?",
         "end_date": "2026-06-17", "outcome": "25 bps cut", "prob": 0.10},
        {"snapshot_date": "2026-06-14", "event_key": "fed_next", "event_title": "Fed Decision in June?",
         "end_date": "2026-06-17", "outcome": "No change", "prob": 0.96},
        {"snapshot_date": "2026-06-14", "event_key": "fed_next", "event_title": "Fed Decision in June?",
         "end_date": "2026-06-17", "outcome": "25 bps cut", "prob": 0.04},
    ])
    panel = pme.build_panel(df, {"fed_next": {"label_en": "Next Fed decision", "label_zh": "下次决议"}})
    assert panel["asof"] == "2026-06-14" and panel["prior"] == "2026-06-13"
    e = panel["events"][0]
    assert e["top"]["outcome"] == "No change" and e["top"]["prob"] == 96.0
    assert e["outcomes"][0]["chg_pp"] == 6.0                 # 96 - 90
    assert e["outcomes"][1]["chg_pp"] == -6.0               # 4 - 10


def test_build_panel_none_on_empty():
    assert pme.build_panel(pd.DataFrame(), {"x": {}}) is None
    assert pme.build_panel(None, {}) is None
