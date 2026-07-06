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
    assert out == [
        {"outcome": "No change", "prob": 0.92, "mkt_volume24hr": None},
        {"outcome": "25 bps cut", "prob": 0.06, "mkt_volume24hr": None},
    ]


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


# INTL-48 — _fetch_active must paginate to reach low-volume events (recession)
def test_fetch_active_paginates(monkeypatch):
    """_fetch_active must combine pages until empty; low-volume events past page 1 are captured."""
    page0 = [{"title": f"Event {i}", "markets": [1], "volume": 1000 - i} for i in range(100)]
    page1 = [{"title": "US recession by end of 2026?", "markets": [{"outcomePrices": ["0.115", "0.885"],
              "groupItemTitle": "US recession by end of 2026?"}], "volume": 1000}]

    call_log: list = []

    def fake_http_get(url, retries, params):
        offset = int(params.get("offset", 0))
        call_log.append(offset)

        class FakeResp:
            def json(inner_self):  # noqa: N805
                return page0 if offset == 0 else page1 if offset == 100 else []
        return FakeResp()

    adapter = pmc.PredictionMarketsAdapter()
    monkeypatch.setattr(adapter, "http_get", fake_http_get)
    events = adapter._fetch_active()
    # Must have issued at least two page requests
    assert len(call_log) >= 2
    titles = [e["title"] for e in events]
    assert "US recession by end of 2026?" in titles, "recession event must be in the combined list"


def test_match_event_recession():
    """match_event must find recession by substring match regardless of case."""
    evs = [
        {"title": "US recession by end of 2026?", "endDate": "2026-12-31T00:00:00Z",
         "markets": [{"outcomePrices": ["0.115"], "groupItemTitle": "Yes"}], "volume": 1000},
    ]
    ev = pmc.match_event(evs, "recession", "max_volume")
    assert ev is not None and "recession" in ev["title"].lower()
