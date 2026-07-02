"""engine/whitehouse_feed.py tests — RSS parse, body extraction, slug ids, dedupe,
recency filter, and the processed-state dedupe ledger. No network, no writes outside
a tmp dir.

Run: python -m tests.test_whitehouse_feed
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import whitehouse_feed as wf  # noqa: E402

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
 <channel>
  <title>The White House</title>
  <item>
    <title>Securing the Nation Against Advanced Cryptographic Attacks</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/securing-the-nation/</link>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=12345</guid>
    <pubDate>Mon, 22 Jun 2026 20:37:30 +0000</pubDate>
    <description>DRIVING INNOVATION WHILE DEFENDING DATA: Today the President signed&#8230;</description>
    <category>Presidential Actions</category>
    <content:encoded><![CDATA[<p>By the authority vested in me&#8230;</p><p>Section 1. <strong>Policy.</strong> Federal agencies shall migrate to post-quantum cryptography.</p><ul><li>One.</li><li>Two.</li></ul>]]></content:encoded>
  </item>
  <item>
    <title>National Homeownership Month, 2026</title>
    <link>https://www.whitehouse.gov/presidential-actions/2026/06/national-homeownership-month-2026/</link>
    <guid isPermaLink="false">https://www.whitehouse.gov/?p=12300</guid>
    <pubDate>Fri, 12 Jun 2026 19:24:42 +0000</pubDate>
    <description>A proclamation.</description>
  </item>
 </channel>
</rss>"""


def test_parse_basic_fields() -> None:
    items = wf._parse(_RSS.encode(), "presidential-actions")
    assert len(items) == 2
    a = items[0]
    assert a["title"].startswith("Securing the Nation")
    assert a["url"].endswith("/securing-the-nation/")
    assert a["guid"] == "https://www.whitehouse.gov/?p=12345"
    assert a["section"] == "presidential-actions"
    assert a["published"] == "2026-06-22T20:37:30+00:00"
    assert "Presidential Actions" in a["categories"]


def test_body_uses_content_encoded_and_cleans_html() -> None:
    a = wf._parse(_RSS.encode(), "news")[0]
    body = a["body"]
    # tags stripped, entities decoded, list/para structure preserved as newlines
    assert "<p>" not in body and "<strong>" not in body
    assert "post-quantum cryptography" in body
    assert "By the authority vested in me…" in body   # &#8230; -> …
    assert "\n" in body                                # block tags became line breaks


def test_slug_id_is_stable_and_dated() -> None:
    a = wf._parse(_RSS.encode(), "news")[0]
    assert a["id"] == "wh-2026-06-22-securing-the-nation"
    # second item slug
    b = wf._parse(_RSS.encode(), "news")[1]
    assert b["id"] == "wh-2026-06-12-national-homeownership-month-2026"


def test_recent_filter_drops_old() -> None:
    now = datetime.now(timezone.utc)
    fresh = {"published": now.isoformat()}
    old = {"published": (now - timedelta(days=30)).isoformat()}
    undated = {"published": ""}
    kept = wf._recent([fresh, old, undated], max_age_days=4.0)
    assert fresh in kept and undated in kept and old not in kept


def test_processed_state_new_items_and_mark(tmp_path: Path = None) -> None:
    items = wf._parse(_RSS.encode(), "news")
    state = {"seen": {}}
    assert len(wf.new_items(items, state)) == 2
    wf.mark_seen(state, items[0], activated=True, importance=82)
    rest = wf.new_items(items, state)
    assert len(rest) == 1 and rest[0]["id"].endswith("homeownership-month-2026")
    assert state["seen"][items[0]["guid"]]["activated"] is True
    assert state["seen"][items[0]["guid"]]["importance"] == 82


def test_state_roundtrip(tmp_path=None) -> None:
    import tempfile
    d = Path(tempfile.mkdtemp())
    state = {"seen": {"g1": {"id": "wh-x", "at": "now", "activated": False, "importance": 10}}}
    wf.save_processed(d, state)
    back = wf.load_processed(d)
    assert back["seen"]["g1"]["id"] == "wh-x"
    # corrupt file -> empty state, never raises
    (d / "data" / "whitehouse" / "processed.json").write_text("{not json")
    assert wf.load_processed(d) == {"seen": {}}


def test_naive_pubdate_treated_as_eastern_not_utc() -> None:
    """WH publishes in ET; a naive (no-timezone) pubDate must be interpreted as
    America/New_York and converted to UTC — NOT assumed to be UTC.  Assuming UTC
    introduced up to +5h recency error (EST offset) per audit finding §WH-tz."""
    # Mon Jun 22 2026 09:00:00 ET = 13:00:00 UTC (EDT = UTC-4 in June)
    naive_pubdate = "Mon, 22 Jun 2026 09:00:00"
    iso = wf._to_iso(naive_pubdate)
    assert iso, "expected a non-empty ISO string"
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None, "result must be timezone-aware"
    # EDT in June is UTC-4 → 09:00 ET = 13:00 UTC
    assert dt.hour == 13, (
        f"naive 09:00 ET should map to 13:00 UTC (EDT), got {dt.isoformat()}")
    assert dt.minute == 0


def test_explicit_utc_pubdate_unchanged() -> None:
    """An explicit +0000 offset on a pubDate must still parse and convert correctly."""
    iso = wf._to_iso("Mon, 22 Jun 2026 20:37:30 +0000")
    dt = datetime.fromisoformat(iso)
    assert dt.hour == 20 and dt.minute == 37


def _run() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")


if __name__ == "__main__":
    _run()
    print("all whitehouse_feed tests passed")
