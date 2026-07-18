"""CN/CA/HK action-board lane split — ports the #1513 US (urgency, tag) routing to
scripts/build_china._china_action_board, scripts/build_canada._action_board and
scripts/build_hk._action_board (the "what to act on now" board on each stock page).

Pins (mirrors tests/test_basket_integration.py::test_action_board_caution_tag_routing):
  * caution + "DON'T CHASE"             → on_the_run   (extended uptrend — never take_profits)
  * caution + "UNCONFIRMED — HIGH RISK" → avoid        (bear-trend countertrend bounce)
  * caution + anything else (incl. "TAKE PROFITS") → take_profits; exit → take_profits
  * tag literals match engine/cycles.py entry_timing BYTE-for-byte (em dash U+2014 in
    UNCONFIRMED, ASCII apostrophe in DON'T — a curly-quote drift silently unroutes a lane)
  * both standalone templates render the new lane and stay missing-key-safe on the
    pre-split actions shape (no on_the_run key).

NOTE: The US action_board (scripts/build_site.py) uses lane_hint-first routing with a
conservative unknown→hold default (not take_profits) per the 2026-07-10 us_stocks
scorecard adjudication. CN/CA/HK boards retain the pre-adjudication take_profits
default — their tests below reflect that.
"""
import re
import sys
from pathlib import Path

import pytest
from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_canada import _action_board as canada_board  # noqa: E402
from scripts.build_china import _china_action_board as china_board  # noqa: E402
from scripts.build_hk import _action_board as hk_board  # noqa: E402

# Byte-exact tags as emitted by engine/cycles.py entry_timing
TAG_DONT_CHASE = "DON'T CHASE"                     # ASCII apostrophe
TAG_UNCONFIRMED = "UNCONFIRMED — HIGH RISK"   # em dash, spaces around it
TAG_TAKE_PROFITS = "TAKE PROFITS"


def _sector(ticker: str, urgency: str, tag: str = "") -> dict:
    """Minimal sector card mirroring the real _sector_cards() call shape."""
    return {"ticker": ticker, "name": ticker.rstrip(".TO"), "label": "TEST", "state": "TEST",
            "dir": "up", "entry": {"urgency": urgency, "tag": tag, "days_hi": None}}


# --- routing (both builders share the ported logic) ---------------------------
@pytest.mark.parametrize("board_fn", [china_board, canada_board, hk_board],
                         ids=["china", "canada", "hk"])
def test_caution_tag_routing(board_fn):
    sectors = [
        _sector("AAA", "caution", TAG_DONT_CHASE),      # → on_the_run
        _sector("BBB", "caution", TAG_TAKE_PROFITS),    # → take_profits
        _sector("CCC", "caution", TAG_UNCONFIRMED),     # → avoid
        _sector("DDD", "exit", TAG_TAKE_PROFITS),       # → take_profits
        _sector("EEE", "now", "BUY NOW"),               # → buy_now
        _sector("FFF", "hold", "HOLD"),                 # → hold
        _sector("GGG", "soon", "GET READY"),            # → buy_soon
    ]
    b = board_fn(sectors)
    assert [x["ticker"] for x in b["on_the_run"]] == ["AAA"], "DON'T CHASE→on_the_run"
    assert [x["ticker"] for x in b["take_profits"]] == ["BBB", "DDD"], \
        "caution+TP and exit stay in take_profits"
    assert [x["ticker"] for x in b["avoid"]] == ["CCC"], "UNCONFIRMED bounce→avoid"
    assert [x["ticker"] for x in b["buy_now"]] == ["EEE"]
    assert [x["ticker"] for x in b["hold"]] == ["FFF"]
    assert [x["ticker"] for x in b["buy_soon"]] == ["GGG"]
    # every lane key present even when empty (template contract), no double-listing
    assert set(b) == {"buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"}
    all_tickers = [x["ticker"] for lane in b.values() for x in lane]
    assert len(all_tickers) == len(set(all_tickers)) == 7


@pytest.mark.parametrize("board_fn", [china_board, canada_board, hk_board],
                         ids=["china", "canada", "hk"])
def test_tag_near_miss_does_not_route_to_on_the_run(board_fn):
    """Curly-apostrophe / hyphen variants are NOT the engine tags — they must fall through
    to take_profits (the pre-split default), never silently into on_the_run/avoid."""
    sectors = [_sector("AAA", "caution", "DON’T CHASE"),          # curly apostrophe
               _sector("BBB", "caution", "UNCONFIRMED - HIGH RISK")]   # ASCII hyphen
    b = board_fn(sectors)
    assert b["on_the_run"] == [] and b["avoid"] == []
    assert [x["ticker"] for x in b["take_profits"]] == ["AAA", "BBB"]


def test_tag_literals_match_engine_source_bytes():
    """The routed literals must exist byte-for-byte in engine/cycles.py entry_timing —
    guards against em-dash/apostrophe drift between engine and builders."""
    cycles_src = (ROOT / "engine" / "cycles.py").read_text(encoding="utf-8")
    assert f'"{TAG_DONT_CHASE}"' in cycles_src
    assert f'"{TAG_UNCONFIRMED}"' in cycles_src
    assert f'"{TAG_TAKE_PROFITS}"' in cycles_src
    for builder in ("scripts/build_china.py", "scripts/build_canada.py", "scripts/build_hk.py"):
        src = (ROOT / builder).read_text(encoding="utf-8")
        assert f'tag == "{TAG_DONT_CHASE}"' in src, f"{builder}: DON'T CHASE literal drifted"
        assert f'tag == "{TAG_UNCONFIRMED}"' in src, f"{builder}: em-dash literal drifted"


# --- template render (standalone pages, missing-key-safe) ---------------------
def _env(snippet: str) -> Environment:
    from engine import i18n
    env = Environment(loader=DictLoader({"blk": snippet}), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t, help=lambda *a, **k: "")
    return env


def _china_block() -> str:
    # The mx5 redesign (2026-07) folded the china macro "action board" into the
    # Sectors detail dialog, driven by pb_obj (playbook) chips rather than the
    # actions-lane board. Extract that dialog block.
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index('<div class="cnx-dlg" id="cnx-dlg-sector">')
    end = src.index('<div class="cnx-dlg" id="cnx-dlg-policy">', start)
    return src[start:end]


def _canada_block() -> str:
    # #2674 (canada mx5 port) renamed the section marker and dropped the old
    # "/macro-only sections" end comment. The mode-gate {% if %}/{% endif %} pair
    # stays OUTSIDE the slice so the extracted block is balanced Jinja.
    src = (ROOT / "templates" / "canada.html.j2").read_text()
    start = src.index("<!-- ===== What to act on now (sector entry-timing board")
    end = src.index("\n{% endif %}\n\n{% if mode != 'stocks' %}", start)
    return src[start:end]


def _full_actions() -> dict:
    return {"buy_now": [_item("AAA")], "buy_soon": [], "on_the_run": [_item("RRR")],
            "take_profits": [], "hold": [], "avoid": []}


def _item(ticker: str) -> dict:
    return {"ticker": ticker, "name": ticker, "label": "TEST", "tag": "", "days": None,
            "dir": "up"}


def test_china_dlg_sector_leaders_dont_chase_not_green():
    """Redesign: sector 'act on now' moved into dlg-sector. The 'leaders' chips
    must render as caution (hot accent), never as a green buy. #2639 deliberately
    dropped the 'don't chase' wording from the Leaders label (EN+ZH parity) —
    the caution now lives in the hot accent + Leaders framing, not the verb."""
    pb = {"preferred": [{"name": "PPP", "rank": 3}], "leaders": [{"name": "RRR"}], "avoid": []}
    html = _env(_china_block()).get_template("blk").render(pb_obj=pb)
    assert "领先" in html                           # Leaders label present (#2639 copy)
    assert "RRR" in html
    assert "cnx-chip hot" in html                   # caution accent, not a buy/turn chip
    assert '<span class="cnx-chip turn">RRR' not in html  # never a green buy/turn chip


def test_china_dlg_sector_missing_lane_safe():
    """A pb_obj missing the leaders/avoid keys must render, not crash.
    (The dialog now renders only pb_obj.leaders — 'preferred' chips were dropped
    in the mx5 redesign, so the old PPP-renders assertion no longer applies.)"""
    pb = {"preferred": [{"name": "PPP", "rank": 1}]}   # no 'leaders' / 'avoid'
    html = _env(_china_block()).get_template("blk").render(pb_obj=pb)
    assert 'id="cnx-dlg-sector"' in html               # dialog shell rendered
    assert "领先" not in html and "RRR" not in html    # no leaders label/chips


def test_canada_template_renders_on_the_run_lane():
    html = _env(_canada_block()).get_template("blk").render(actions=_full_actions())
    assert "ON THE RUN" in html and "勿追高" in html
    assert "ab-on_the_run" in html                # violet accent class, never green
    assert "RRR" in html


def test_canada_template_missing_key_safe():
    a = _full_actions(); del a["on_the_run"]
    html = _env(_canada_block()).get_template("blk").render(actions=a)
    assert "AAA" in html


def test_no_translated_text_in_title_attributes():
    """CI guard parity (scripts/check_title_i18n.py): no t() inside title=/data-*/aria-*."""
    for block in (_china_block(), _canada_block()):
        assert not re.search(r'(?:title|data-[a-z-]+|aria-[a-z]+)="[^"]*\{\{\s*t\(', block)
