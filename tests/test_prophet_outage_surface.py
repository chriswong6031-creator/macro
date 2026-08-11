"""Plain-language board disclosure for the one receipted Prophet outage replay."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from scripts.build_site import (
    _PROPHET_OUTAGE_NOTE,
    _attach_prophet_outage_notes,
)
from scripts.build_prophet import (
    OUTAGE_ORIGINATION_DISCLOSURE,
    _origination_disclosure,
)


MODE = "outage_backfill_2026_08_09"


def _write_index(site: Path, plans: list[dict]) -> None:
    path = site / "prophet" / "index.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"plans": plans}), encoding="utf-8")


def test_only_the_exact_authorised_mode_marks_its_matching_board_card(tmp_path):
    _write_index(tmp_path, [
        {"asset": "AAA", "origination_mode": MODE},
        {"asset": "BBB", "origination_mode": "live"},
        {"asset": "CCC", "origination_mode": "some_future_exception"},
    ])
    board = {"buy": [{"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}]}

    result = _attach_prophet_outage_notes(tmp_path, board)

    assert result["buy"][0]["prophet_outage_note"] == _PROPHET_OUTAGE_NOTE
    assert "prophet_outage_note" not in result["buy"][1]
    assert "prophet_outage_note" not in result["buy"][2]


def test_missing_or_unreadable_index_leaves_the_board_unchanged(tmp_path):
    board = {"buy": [{"ticker": "AAA"}]}
    assert _attach_prophet_outage_notes(tmp_path, board) == board

    path = tmp_path / "prophet" / "index.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert _attach_prophet_outage_notes(tmp_path, board) == board


def test_reader_copy_is_bilingual_and_contains_no_internal_vocabulary():
    assert OUTAGE_ORIGINATION_DISCLOSURE == _PROPHET_OUTAGE_NOTE
    assert _origination_disclosure({"origination_mode": MODE}) == _PROPHET_OUTAGE_NOTE
    assert _origination_disclosure({"origination_mode": "live"}) is None
    assert all(_PROPHET_OUTAGE_NOTE[key].strip() for key in (
        "label_en", "label_zh", "tip_en", "tip_zh",
    ))
    visible = " ".join(_PROPHET_OUTAGE_NOTE.values()).lower()
    for banned in (
        "backfill", "mixed vintage", "mixed_vintage", "origination_mode",
        "outage_backfill", "anticipation-v1", "selection_era",
    ):
        assert banned not in visible


def test_dashboard_routes_the_note_through_the_shared_card_mark(tmp_path):
    root = Path(__file__).resolve().parent.parent
    dashboard = (root / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    card = (root / "templates" / "_prophet_card.html.j2").read_text(encoding="utf-8")
    publisher = (root / "scripts" / "build_prophet.py").read_text(encoding="utf-8")
    assert publisher.count(
        '"origination_disclosure": _origination_disclosure(plan)'
    ) == 2, "healthy and degraded index rows must both carry the reader note"
    assert "n.get('prophet_outage_note')" in dashboard
    assert "'k':'replay'" in dashboard
    assert ".pv-mk-replay" in card

    env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=True)
    html = str(env.get_template("_prophet_card.html.j2").module.pv_card({
        "href": "#", "tk": "AAA", "name": "AAA", "sec": "Technology",
        "verb": "buy", "marks": [{
            "k": "replay",
            "en": _PROPHET_OUTAGE_NOTE["label_en"],
            "zh": _PROPHET_OUTAGE_NOTE["label_zh"],
            "tip_en": _PROPHET_OUTAGE_NOTE["tip_en"],
            "tip_zh": _PROPHET_OUTAGE_NOTE["tip_zh"],
        }],
    }))
    assert 'class="pv-mk-i pv-mk-replay"' in html
    assert _PROPHET_OUTAGE_NOTE["label_en"] in html
    assert _PROPHET_OUTAGE_NOTE["label_zh"] in html
