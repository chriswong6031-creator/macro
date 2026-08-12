"""Regression test for the Stock-Connect leaderboard: scripts/build_china.py's
_leaderboard() must produce the exact keys/fields templates/china.html.j2's Connect
Flows card + cnx-dlg-flows popup read off ``leaderboard``.

The bug this guards: _leaderboard() returned {"nb": ..., "sb_buy": ..., "sb_sell": ...}
with row fields {code, name, chg, val}, while the template reads
leaderboard.northbound_turnover / leaderboard.southbound_buy with row fields
{name_zh, ticker, turnover|net, chg}. Jinja treats an unmatched attribute as falsy
rather than erroring, so every {% if leaderboard.X %} silently skipped — the popup's
eyebrow header rendered but the tables never did, and the summary card's "Top buys"
line never did either. Nothing caught it: the fetch is wrapped in a catch-all
try/except (best-effort by design) and no test exercised the shape.

ZERO NETWORK: requests.get is monkeypatched (FakeResponse pattern from
tests/test_china_cb_collector.py). The render half reuses the REAL template source via
the DictLoader snippet-extraction pattern from tests/test_china_fx_context_render.py,
so a future rename on either side (builder or template) fails this test instead of
silently going dark again.
"""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import DictLoader, Environment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_china import _leaderboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class FakeResponse:
    """Minimal requests.Response stand-in (.json())."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _row(mt: str, code: str, name: str, chg: float, deal_amt: float, net_buy: float) -> dict:
    return {"TRADE_DATE": "2026-08-11", "MUTUAL_TYPE": mt, "SECURITY_CODE": code,
            "SECURITY_NAME": name, "CHANGE_RATE": chg, "DEAL_AMT": deal_amt,
            "NET_BUY_AMT": net_buy}


# northbound legs (foreign -> A-shares), ranked by DEAL_AMT
_BY_LEG = {
    "001": [_row("001", "600519", "贵州茅台", 1.2, 50.0e8, 0)],
    "003": [_row("003", "300750", "宁德时代", -0.5, 30.0e8, 0)],
    # southbound legs (mainland -> HK): one net buyer, one net seller
    "002": [_row("002", "00700", "腾讯控股", -2.2, 0, 5.5e8)],
    "004": [_row("004", "09988", "阿里巴巴-W", 0.3, 0, -3.1e8)],
}


def _fake_get(url, params=None, headers=None, timeout=None):
    mt = params["filter"].split('"')[1]
    return FakeResponse({"result": {"data": _BY_LEG[mt]}})


def _mock_fetch(monkeypatch) -> None:
    import requests
    monkeypatch.setattr(requests, "get", _fake_get)


# ---------------------------------------------------------------------------
# builder contract: the shape the template actually consumes
# ---------------------------------------------------------------------------

def test_leaderboard_shape_matches_template_contract(monkeypatch):
    _mock_fetch(monkeypatch)
    lb = _leaderboard()
    assert lb is not None
    assert lb.keys() >= {"date", "northbound_turnover", "southbound_buy", "southbound_sell"}

    nb_row = lb["northbound_turnover"][0]
    assert {"name_zh", "name", "ticker", "turnover", "chg"} <= nb_row.keys()
    assert nb_row["ticker"] == "600519", "northbound_turnover must sort by DEAL_AMT desc"

    sb_row = lb["southbound_buy"][0]
    assert {"name_zh", "name", "net", "chg"} <= sb_row.keys()
    assert sb_row["net"] > 0, "southbound_buy's top row must be a net BUYER"

    sell_row = lb["southbound_sell"][0]
    assert sell_row["net"] < 0, "southbound_sell's top row must be a net SELLER"


# ---------------------------------------------------------------------------
# render half: the REAL template snippet, fed the REAL builder output
# ---------------------------------------------------------------------------

_T_MACRO = '{%- macro t(en, zh="") -%}{{ en }}{%- endmacro -%}\n'


def _snippet(start_marker: str, end_marker: str) -> str:
    src = (ROOT / "templates" / "china.html.j2").read_text()
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return _T_MACRO + src[start:end]


def _render(key: str, snippet: str, **ctx) -> str:
    env = Environment(loader=DictLoader({key: snippet}), autoescape=False)
    return env.get_template(key).render(**ctx)


def test_popup_dialog_renders_real_rows_from_the_real_leaderboard_output(monkeypatch):
    _mock_fetch(monkeypatch)
    lb = _leaderboard()
    snippet = _snippet("<!-- Connect Flows dialog -->", "<!-- Property dialog -->")
    html = _render("dlg", snippet, leaderboard=lb, latest={"date": lb["date"]},
                    I={"southbound": None})

    assert "<table" in html, "the leaderboard tables must actually render"
    assert "贵州茅台" in html and "600519" in html, "top northbound row must render"
    assert "腾讯控股" in html, "top southbound-buy row must render"


def test_summary_card_top_buys_line_renders_from_the_real_leaderboard_output(monkeypatch):
    _mock_fetch(monkeypatch)
    lb = _leaderboard()
    snippet = _snippet("{# Connect Flows card #}", "{# Macro News card #}")
    html = _render("card", snippet, leaderboard=lb, I={"southbound": None})

    assert "腾讯控股" in html, "the 'Top buys' teaser needs r.name_zh populated"


def test_popup_dialog_is_silent_but_error_free_when_leaderboard_is_none():
    """The best-effort fetch degrades to None on failure; the popup must not crash."""
    snippet = _snippet("<!-- Connect Flows dialog -->", "<!-- Property dialog -->")
    html = _render("dlg", snippet, leaderboard=None, latest={"date": "2026-08-11"},
                    I={"southbound": None})
    assert "<table" not in html
