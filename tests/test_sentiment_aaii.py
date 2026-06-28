"""Guard the AAII bull/bear scraper parse path.

AAII's free results page ships its table header as the first DATA row (read_html
then sees numeric 0..n column names) and its reported dates are year-less ('Jun
24'). It also sits behind a PerimeterX bot wall that 403s short user-agents and
intermittently serves a "Pardon Our Interruption" interstitial. The adapter must
parse the real table, infer the year, and degrade cleanly when challenged.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sentiment import AaiiAdapter  # noqa: E402

_REAL_PAGE = """<html><body>
<table>
<tr><td>Reported Date</td><td>Bullish</td><td>Neutral</td><td>Bearish</td></tr>
<tr><td>Jun 24</td><td>44.9%</td><td>18.9%</td><td>36.1%</td></tr>
<tr><td>Jun 17</td><td>36.6%</td><td>24.1%</td><td>39.4%</td></tr>
<tr><td>Dec 31</td><td>30.0%</td><td>30.0%</td><td>40.0%</td></tr>
</table>
<table><tr><td>Take the Sentiment Survey</td><td>Download Historical Data</td></tr></table>
</body></html>"""

_CHALLENGE = ('<!DOCTYPE html><html><head><title>Pardon Our Interruption</title>'
              '</head><body></body></html>')


def _adapter_returning(html):
    a = AaiiAdapter()
    a.http_get = lambda *args, **kw: type("R", (), {"status_code": 200, "text": html})()
    return a


def test_parses_header_in_first_row_and_infers_year():
    df = _adapter_returning(_REAL_PAGE).fetch()["aaii"].sort_index()
    assert list(df.columns) == ["aaii_bullish", "aaii_neutral", "aaii_bearish"]
    assert abs(df["aaii_bullish"].iloc[-1] - 44.9) < 1e-9  # newest = Jun 24
    yr = datetime.now(timezone.utc).year
    assert str(df.index.max().date()) == f"{yr}-06-24"
    # a year-less December row read mid-year rolls back to the prior year
    assert str(df.index.min().date()) == f"{yr - 1}-12-31"


def test_bot_challenge_degrades_cleanly():
    try:
        _adapter_returning(_CHALLENGE).fetch()
        raise AssertionError("bot-challenge page must raise, not return junk")
    except ValueError as e:
        assert "challenge" in str(e).lower()


def test_uses_browser_user_agent():
    # the bot wall 403s short/"research" agents; a full browser UA is required
    assert "Chrome" in AaiiAdapter._UA and "Mozilla" in AaiiAdapter._UA
