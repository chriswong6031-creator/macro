"""E3 competitive-intelligence loop + E6 learning-spine provenance.

Every test maps to a line in masterplan §10 E3/E6 or to a methodology note in
``research/marketing_dockets/x_corpus_2026_07_29/stats.md`` — the MANUAL v1 of
the corpus this lane automates. Where the docket states a number (48.6% one
raw line, 5.9% strict decimal, 2.8% exactly two raw lines) the classifier is
pinned against a post that produced it.

Stdlib + pyyaml only (marketing-engine CI lane). NO NETWORK: the harvester takes
an injectable transport and every test uses it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import exemplar_store as xs  # noqa: E402
from engine.marketing import labels as lb  # noqa: E402
from engine.marketing import x_intel as xi  # noqa: E402

NOW = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


# ===========================================================================
# THE FIXTURE — the real twitterapi.io /twitter/user/last_tweets response
# shape, verbatim in structure (data.tweets nesting, camelCase counters, the
# legacy createdAt format, an inline RT, HTML entities in text).
# ===========================================================================
def _api_response(tweets: list[dict], *, has_next: bool = False) -> dict:
    return {
        "status": "success",
        "code": 0,
        "msg": "",
        "data": {
            "tweets": tweets,
            "has_next_page": has_next,
            "next_cursor": "DAABCgABGx" if has_next else "",
        },
    }


def _tweet(tid, text, *, author="DeItaone", likes=100, rts=10, replies=5,
           views=50_000, quotes=0, bookmarks=0, created="Tue Jul 28 21:03:12 +0000 2026",
           media=None, quoted=None, followers=912_004):
    row = {
        "type": "tweet",
        "id": str(tid),
        "url": f"https://x.com/{author}/status/{tid}",
        "text": text,
        "source": "Twitter Web App",
        "retweetCount": rts,
        "replyCount": replies,
        "likeCount": likes,
        "quoteCount": quotes,
        "viewCount": views,
        "bookmarkCount": bookmarks,
        "createdAt": created,
        "lang": "en",
        "isReply": False,
        "author": {
            "type": "user", "userName": author, "name": author,
            "followers": followers, "following": 12,
        },
    }
    if media:
        row["extendedEntities"] = {"media": [{"type": m} for m in media]}
    if quoted:
        row["quoted_tweet"] = quoted
    return row


#: The five posts the docket's exemplars.md uses to demonstrate each structure.
WIRE_ONE_LINER = "U.S. MILITARY: ALL IRANIAN MISSILES WERE SUCCESSFULLY INTERCEPTED."
WIRE_HEADLINE_BODY = (
    "TRUMP TO BAN CHINESE ROBOTS, POWER INVERTERS\n"
    "\n"
    "The Trump administration is set to ban imports of new Chinese humanoid robots."
)
RT_ROW = "RT @unusual_whales: BREAKING: FIFA President plans a $20 billion company"
ENTITY_ROW = "Nvidia &amp; AMD both &gt;100 today &lt;- the whole tape"
TRADER_SETUP = "$PLTR reclaimed the 50-day at 102.50.\nWatching 4.75% follow-through."


def _live_response():
    return _api_response([
        _tweet(101, WIRE_ONE_LINER, likes=799, rts=39, replies=69, views=177_178),
        _tweet(102, WIRE_HEADLINE_BODY, likes=739, rts=112, replies=64, views=195_002),
        _tweet(103, RT_ROW, likes=5, rts=1, replies=0, views=900),
        _tweet(104, ENTITY_ROW, likes=40, rts=3, replies=1, views=9_000),
        _tweet(105, TRADER_SETUP, author="traderstewie", likes=61, rts=4,
               replies=9, views=12_000),
    ])


class _Transport:
    """Injectable stand-in for urlopen. Records every call; no network."""

    def __init__(self, response, *, per_handle=None):
        self.response = response
        self.per_handle = per_handle or {}
        self.calls: list[str] = []

    def __call__(self, url, headers):
        self.calls.append(url)
        for handle, resp in self.per_handle.items():
            if f"userName={handle}" in url:
                return resp
        return self.response


# ===========================================================================
# GATE E3.1 — the harvester parses the REAL response shape
# ===========================================================================
class TestHarvestParsesTheRealShape:
    def test_tweets_are_found_under_data_tweets(self):
        """The endpoint nests at data.tweets. A parser that only knows the flat
        `tweets` key bills the call and harvests ZERO rows — silently."""
        got = xi.extract_tweets(_live_response())
        assert [r["id"] for r in got] == ["101", "102", "103", "104", "105"]

    def test_a_flat_tweets_key_still_parses(self):
        """A future endpoint swap must not silently harvest nothing."""
        assert len(xi.extract_tweets({"tweets": [_tweet(1, "x")]})) == 1

    def test_an_unknown_shape_yields_nothing_rather_than_guessing(self):
        assert xi.extract_tweets({"payload": {"stuff": [{"id": "1"}]}}) == []

    def test_retweets_are_dropped(self):
        """A pure RT is somebody else's writing. Keeping it puts another
        account's style into this account's style row."""
        rows = xi.extract_tweets(_live_response())
        assert [xi.is_retweet(r) for r in rows] == [False, False, True, False, False]

    def test_retweet_detection_survives_a_missing_prefix(self):
        assert xi.is_retweet({"text": "no prefix", "retweeted_tweet": {"id": "9"}}) is True
        assert xi.is_retweet({"text": "no prefix", "isRetweet": True}) is True
        assert xi.is_retweet({"text": "an original post"}) is False

    def test_a_quote_tweet_is_NOT_a_retweet(self):
        """The quoting text is the author's own — the docket keeps quotes,
        flagged is_quote, and only excludes PURE retweets."""
        raw = _tweet(9, "This is the whole story.", quoted={"id": "8"})
        assert xi.is_retweet(raw) is False
        row = xi.normalize_tweet(raw, handle="DeItaone", captured_at="2026-07-29T22:00:00Z")
        assert row["is_quote"] is True

    def test_html_entities_are_unescaped_before_classification(self):
        """`&gt;100` must read as a bare integer; `&amp;` must not read as four
        extra characters. The docket unescapes before any classifier runs."""
        row = xi.normalize_tweet(
            _tweet(104, ENTITY_ROW), handle="DeItaone",
            captured_at="2026-07-29T22:00:00Z")
        assert row["text"] == "Nvidia & AMD both >100 today <- the whole tape"
        assert "&amp;" not in row["text"]
        assert row["tags"]["has_bare_int"] is True

    def test_normalize_carries_the_codex_measurement_schema(self):
        """CODEX_CONTENT_CASE_STUDIES §Recommended measurement schema: url, exact
        text, account + follower count AT CAPTURE, publication + capture
        timestamps, replies/reposts/likes/bookmarks/views, media type, quote
        flag, format tags."""
        row = xi.normalize_tweet(
            _tweet(101, WIRE_ONE_LINER, likes=799, rts=39, replies=69,
                   views=177_178, bookmarks=31, media=["photo"]),
            handle="DeItaone", register="wire",
            captured_at="2026-07-29T22:00:00Z")
        for field in ("url", "text", "author", "author_followers", "created_at",
                      "captured_at", "likes", "retweets", "replies", "views",
                      "bookmarks", "quotes", "media_types", "is_quote", "tags"):
            assert field in row, f"codex schema field {field!r} missing"
        assert row["author_followers"] == 912_004
        assert row["media_types"] == ["photo"]
        assert row["author_register"] == "wire"
        assert row["created_day"] == "2026-07-28"

    def test_an_absent_counter_is_None_not_zero(self):
        """"nobody looked" and "we were not told" are different facts, and every
        rate downstream depends on keeping them apart."""
        raw = _tweet(7, "text")
        del raw["viewCount"]
        del raw["bookmarkCount"]
        row = xi.normalize_tweet(raw, handle="x", captured_at="2026-07-29T22:00:00Z")
        assert row["views"] is None
        assert row["bookmarks"] is None

    def test_full_run_harvests_originals_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        transport = _Transport(_live_response())
        conf = {"intel": {"roster": [{"handle": "DeItaone", "register": "wire"}]}}
        h = xi.Harvester(conf, transport=transport)
        state = xi.load_state(tmp_path)
        out = h.run(state=state, now=NOW)
        assert out["calls"] == 1
        assert out["tweets_seen"] == 5
        assert out["retweets_dropped"] == 1
        assert len(out["rows"]) == 4
        assert all(not r["text"].startswith("RT @") for r in out["rows"])
        assert "X-API-Key" not in transport.calls[0], "the key must ride in a header"
        assert "userName=DeItaone" in transport.calls[0]

    def test_no_api_key_means_zero_calls_and_zero_spend(self, tmp_path, monkeypatch):
        """DARK BY DEFAULT — the weekly workflow runs green with no secret."""
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        transport = _Transport(_live_response())
        h = xi.Harvester({"intel": {"roster": [{"handle": "DeItaone"}]}},
                         transport=transport)
        state = xi.load_state(tmp_path)
        out = h.run(state=state, now=NOW)
        assert out["stopped"] == "no_api_key"
        assert transport.calls == []
        assert xi.month_bucket(state, NOW)["calls"] == 0

    def test_dry_run_makes_no_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        transport = _Transport(_live_response())
        h = xi.Harvester({"intel": {"roster": [{"handle": "DeItaone"}]}},
                         transport=transport)
        out = h.run(state=xi.load_state(tmp_path), now=NOW, offline=True)
        assert out["stopped"] == "offline"
        assert transport.calls == []


# ===========================================================================
# GATE E3.2 — the BUDGET CAP refuses, loudly, at the line start
# ===========================================================================
class TestBudgetCap:
    def test_the_cap_refuses_the_next_call(self):
        state = {"months": {"2026-07": {"calls": 600, "tweets": 12000, "usd": 1.8}}}
        ok, reason, meta = xi.budget_check(state, {"intel": {"monthly_call_cap": 600}},
                                           now=NOW)
        assert ok is False
        assert reason == "monthly_call_cap"
        assert meta["calls_remaining"] == 0

    def test_the_usd_cap_is_an_independent_second_stop(self):
        """Defence in depth: if a page ever returns far more than the ~20 tweets
        the call-cap arithmetic assumes, the dollar counter still binds."""
        state = {"months": {"2026-07": {"calls": 3, "tweets": 900_000, "usd": 9.9}}}
        ok, reason, _ = xi.budget_check(
            state, {"intel": {"monthly_call_cap": 600, "monthly_usd_cap": 5.0}}, now=NOW)
        assert ok is False and reason == "monthly_usd_cap"

    def test_a_fresh_month_resets_the_counter(self):
        state = {"months": {"2026-07": {"calls": 600, "tweets": 1, "usd": 1.8}}}
        ok, _reason, _meta = xi.budget_check(
            state, {"intel": {"monthly_call_cap": 600}},
            now=datetime(2026, 8, 1, tzinfo=timezone.utc))
        assert ok is True

    def test_refusal_annotation_starts_the_line_and_flushes(self, capsys):
        """GitHub silently DROPS an annotation that does not start the line —
        the CI-guarded house law. A logger here would emit `WARNING ::warning`."""
        state = {"months": {"2026-07": {"calls": 600, "tweets": 0, "usd": 1.8}}}
        _ok, reason, meta = xi.budget_check(state, {"intel": {"monthly_call_cap": 600}},
                                            now=NOW)
        xi.announce_budget_stop(reason, meta)
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "x-intel-budget" in ln)
        assert line.startswith("::warning title=x-intel-budget::"), line
        assert "600" in line

    def test_the_run_stops_at_the_cap_and_makes_no_further_call(self, tmp_path,
                                                                monkeypatch, capsys):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        transport = _Transport(_live_response())
        conf = {"intel": {
            "monthly_call_cap": 2, "max_calls_per_run": 20,
            "roster": [{"handle": f"acct{i}"} for i in range(5)],
        }}
        h = xi.Harvester(conf, transport=transport)
        state = xi.load_state(tmp_path)
        out = h.run(state=state, now=NOW)
        assert out["calls"] == 2, "the cap must bind mid-roster, not after it"
        assert len(transport.calls) == 2
        assert out["stopped"] == "monthly_call_cap"
        assert capsys.readouterr().out.count("::warning title=x-intel-budget::") == 1

    def test_billing_math_matches_the_published_rate_card(self):
        """$0.15/1,000 tweets, $0.00015 minimum. 20 tweets => $0.003/call, which
        is the arithmetic the 600-call cap is sized on."""
        state = xi._empty_state()
        cost = xi.record_call(state, 20, cfg={"intel": {}}, now=NOW)
        assert cost == pytest.approx(0.003)
        bucket = xi.month_bucket(state, NOW)
        assert (bucket["calls"], bucket["tweets"]) == (1, 20)
        # An empty page still costs the per-request minimum.
        assert xi.record_call(state, 0, cfg={"intel": {}}, now=NOW) == pytest.approx(0.00015)

    def test_600_calls_a_month_is_under_two_dollars(self):
        """The cap comment claims ~$1.80/month. Pin the claim to the code."""
        state = xi._empty_state()
        for _ in range(600):
            xi.record_call(state, 20, cfg={"intel": {}}, now=NOW)
        assert xi.month_bucket(state, NOW)["usd"] == pytest.approx(1.80, abs=0.01)

    def test_max_calls_per_run_stops_one_run_eating_the_month(self, tmp_path,
                                                              monkeypatch):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        transport = _Transport(_live_response())
        conf = {"intel": {"max_calls_per_run": 3,
                          "roster": [{"handle": f"a{i}"} for i in range(10)]}}
        out = xi.Harvester(conf, transport=transport).run(
            state=xi.load_state(tmp_path), now=NOW)
        assert out["calls"] == 3 and out["stopped"] == "max_calls_per_run"


# ===========================================================================
# GATE E3.3 — deterministic classifiers reproduce the DOCKET methodology
# ===========================================================================
class TestClassifiers:
    def test_one_raw_line_is_the_one_liner_shape(self):
        tags = xi.classify(WIRE_ONE_LINER)
        assert (tags["raw_lines"], tags["content_lines"]) == (1, 1)
        assert tags["shape"] == "one_liner"
        assert tags["all_caps_lead"] is True

    def test_headline_blank_body_is_THREE_raw_lines_and_TWO_content_lines(self):
        """The docket's key finding #1: the blank spacer is a structural move a
        naive line count misses entirely."""
        tags = xi.classify(WIRE_HEADLINE_BODY)
        assert tags["raw_lines"] == 3
        assert tags["content_lines"] == 2
        assert tags["has_blank_spacer"] is True
        assert tags["shape"] == "two_part"

    def test_strict_decimal_is_two_digits_and_any_decimal_is_one(self):
        """Docket key finding #2: strict 5.9% vs any-decimal 15.4% — the gap IS
        the finding, so both are measured."""
        assert xi.classify("target 102.50")["decimal_strict"] is True
        assert xi.classify("up 4.7%")["decimal_strict"] is False
        assert xi.classify("up 4.7%")["decimal_any"] is True

    def test_bare_integer_ignores_digits_inside_a_decimal(self):
        assert xi.classify("exactly 100 names")["has_bare_int"] is True
        assert xi.classify("only 4.7 percent")["has_bare_int"] is False

    def test_cashtag_lead_vs_anywhere(self):
        tags = xi.classify(TRADER_SETUP)
        assert tags["has_cashtag"] is True
        assert tags["starts_cashtag"] is True
        assert xi.classify("watching $NVDA here")["starts_cashtag"] is False

    def test_BREAKING_is_not_read_as_a_ticker(self):
        """The docket's exclude list. Without it every wire post reads as a
        ticker lead and the cashtag stat is nonsense."""
        assert xi.classify("BREAKING: KOSPI plunges 9.6%")["starts_ticker"] is False
        assert xi.classify("AAPL breaks out")["starts_ticker"] is True

    def test_media_only_text_is_a_caption_not_a_one_liner(self):
        """Reading a chart post as a one_liner would inflate the very rate the
        quota comparison is made on."""
        assert xi.classify("Weekly chart.", has_media=True)["shape"] == "caption"
        assert xi.classify("Weekly chart.", has_media=False)["shape"] == "one_liner"

    def test_numbered_lines_are_a_list_not_a_stack(self):
        text = "Three reads:\n1. rates\n2. credit\n3. breadth"
        assert xi.classify(text)["shape"] == "list"
        plain = "Three reads.\nRates are moving.\nCredit is not.\nBreadth is thin."
        assert xi.classify(plain)["shape"] == "stack"

    def test_register_guess_is_a_per_post_tag_not_the_authority(self):
        assert xi.classify(WIRE_ONE_LINER)["register_guess"] == "wire"
        assert xi.classify(TRADER_SETUP)["register_guess"] == "trader"

    def test_emoji_and_url_detection(self):
        assert xi.classify("Up 3% today 🚀")["has_emoji"] is True
        assert xi.classify("chart: https://x.com/a/b")["has_url"] is True
        assert xi.classify("no link here")["has_url"] is False


# ===========================================================================
# GATE E3.4 — the corpus is APPEND-ONLY on disk, folded on read
# ===========================================================================
class TestCorpusLedger:
    def _rows(self, captured, **over):
        base = dict(id="101", author="DeItaone", text="a", views=100, likes=1,
                    retweets=0, replies=0, bookmarks=0, captured_at=captured,
                    created_day="2026-07-28", author_register="wire",
                    tags=xi.classify("a"))
        base.update(over)
        return [base]

    def test_dedup_keeps_the_freshest_capture(self, tmp_path):
        p = tmp_path / "corpus.jsonl"
        xi.append_corpus(self._rows("2026-07-22T22:00:00Z", likes=1), path=p)
        xi.append_corpus(self._rows("2026-07-29T22:00:00Z", likes=990), path=p)
        folded = xi.load_corpus(path=p)
        assert len(folded) == 1
        assert folded[0]["likes"] == 990, "cumulative counters: latest is truth"

    def test_the_file_is_appended_never_rewritten(self, tmp_path):
        """merge=union is only correct for a file nobody rewrites; a rewrite
        would make that .gitattributes entry actively harmful."""
        p = tmp_path / "corpus.jsonl"
        xi.append_corpus(self._rows("2026-07-22T22:00:00Z", likes=1), path=p)
        first = p.read_text(encoding="utf-8")
        xi.append_corpus(self._rows("2026-07-29T22:00:00Z", likes=990), path=p)
        assert p.read_text(encoding="utf-8").startswith(first)
        assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_an_identical_recapture_is_dropped(self, tmp_path):
        p = tmp_path / "corpus.jsonl"
        assert xi.append_corpus(self._rows("2026-07-22T22:00:00Z"), path=p) == 1
        assert xi.append_corpus(self._rows("2026-07-29T22:00:00Z"), path=p) == 0

    def test_a_torn_final_line_does_not_blind_us_to_the_good_rows(self, tmp_path):
        p = tmp_path / "corpus.jsonl"
        xi.append_corpus(self._rows("2026-07-22T22:00:00Z"), path=p)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write('{"id": "202", "text": "tor')
        assert len(xi.load_corpus(path=p)) == 1

    def test_gitattributes_carries_the_union_merge(self):
        body = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "data/marketing/x_intel/corpus.jsonl merge=union" in body
        assert "data/marketing/x_intel/state.json merge=union" not in body, \
            "a union-merged JSON document is a syntax error, not a merge"


# ===========================================================================
# GATE E3.5 — the ANALYSIS pass (deterministic; LLM never scores)
# ===========================================================================
def _corpus_row(tid, text, *, author="DeItaone", register="wire", views=50_000,
                likes=100, rts=10, replies=5, day="2026-07-28", media=False):
    return {
        "schema": xi.SCHEMA, "id": str(tid), "author": author,
        "author_register": register, "text": text, "created_day": day,
        "captured_at": "2026-07-29T22:00:00Z", "views": views, "likes": likes,
        "retweets": rts, "replies": replies, "bookmarks": 0, "quotes": 0,
        "is_quote": False, "media_types": ["photo"] if media else [],
        "url": f"https://x.com/{author}/status/{tid}",
        "tags": xi.classify(text, has_media=media),
    }


def _fixture_corpus():
    rows = []
    for i in range(14):
        rows.append(_corpus_row(1000 + i, WIRE_ONE_LINER, views=100_000,
                                likes=800, rts=40, replies=60))
    for i in range(14):
        rows.append(_corpus_row(2000 + i, WIRE_HEADLINE_BODY, views=200_000,
                                likes=700, rts=110, replies=64))
    for i in range(4):
        rows.append(_corpus_row(3000 + i, TRADER_SETUP, author="traderstewie",
                                register="trader", views=12_000, likes=61,
                                rts=4, replies=9))
    return rows


class TestAnalysis:
    def test_report_generates_from_a_fixture_corpus(self, cfg):
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        assert rep["schema"] == xi.REPORT_SCHEMA
        assert rep["n_posts"] == 32
        assert rep["n_authors"] == 2
        assert {e["shape"] for e in rep["by_shape"]} == {"one_liner", "two_part"}
        assert {e["register"] for e in rep["by_register"]} == {"wire", "trader"}
        assert {e["author"] for e in rep["by_author"]} == {"DeItaone", "traderstewie"}

    def test_thin_rows_are_PRINTED_with_a_seeding_verdict_not_hidden(self, cfg):
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        trader = next(e for e in rep["by_register"] if e["register"] == "trader")
        assert trader["n"] == 4
        assert trader["verdict"] == "seeding"
        wire = next(e for e in rep["by_register"] if e["register"] == "wire")
        assert "verdict" not in wire

    def test_zero_views_is_excluded_from_the_rate_not_folded_in_as_zero(self, cfg):
        """An unmeasured post is not an unengaging post. Folding it in as 0.0
        would drag every median down in proportion to API coverage."""
        rows = _fixture_corpus()
        blind = _corpus_row(9999, WIRE_ONE_LINER, views=None, likes=0, rts=0, replies=0)
        rep_before = xi.analyze(rows, cfg=cfg, prior=None, now=NOW)
        rep_after = xi.analyze(rows + [blind], cfg=cfg, prior=None, now=NOW)
        one_before = next(e for e in rep_before["by_shape"] if e["shape"] == "one_liner")
        one_after = next(e for e in rep_after["by_shape"] if e["shape"] == "one_liner")
        assert one_after["n"] == one_before["n"] + 1, "the row is COUNTED"
        assert one_after["n_no_views"] == 1, "and named as unmeasured"
        assert one_after["med_interaction_rate"] == one_before["med_interaction_rate"]

    def test_repost_rate_is_reported_separately_from_interaction_rate(self, cfg):
        """Codex: optimise for repost/view when the goal is DISTRIBUTION. A
        distribution question needs a distribution number."""
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        two = next(e for e in rep["by_shape"] if e["shape"] == "two_part")
        assert two["med_repost_rate"] == pytest.approx(110 / 200_000)
        assert two["med_interaction_rate"] == pytest.approx(874 / 200_000)

    def test_shape_distribution_is_compared_against_OUR_quotas(self, cfg):
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        # 14 wire one-liners; the other 18 (14 headline+body, 4 trader setups)
        # are two content lines each.
        assert rep["shape_distribution"]["one_liner"] == pytest.approx(14 / 32, abs=1e-4)
        assert rep["shape_distribution"]["two_part"] == pytest.approx(18 / 32, abs=1e-4)
        gaps = {g["shape"]: g for g in rep["quota_gap"]}
        assert gaps["one_liner"]["ours_min"] == cfg["shapes"]["quotas"]["one_liner_min"]
        assert gaps["two_part"]["ours_max"] == cfg["shapes"]["quotas"]["two_part_max"]

    def test_decimal_precision_rates_are_reported(self, cfg):
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        prec = rep["precision"]
        # 4 trader posts of 32 carry `102.50` (strict) and `4.75%` (any).
        assert prec["decimal_strict_rate"] == pytest.approx(4 / 32, abs=1e-4)
        assert prec["decimal_any_rate"] == pytest.approx(4 / 32, abs=1e-4)
        # 32/32, and that is CORRECT rather than a bug: the docket records the
        # overlap ("$AAPL reads as leading token AAPL (all caps)"), so the four
        # `$PLTR ...` setups count as ALL-CAPS leads alongside the 28 wire posts.
        assert prec["all_caps_lead_rate"] == pytest.approx(1.0, abs=1e-4)
        assert prec["starts_cashtag_rate"] == pytest.approx(4 / 32, abs=1e-4)

    def test_the_window_excludes_stale_posts(self, cfg):
        old = _corpus_row(4242, WIRE_ONE_LINER, day="2020-01-01")
        rep = xi.analyze(_fixture_corpus() + [old], cfg=cfg, prior=None, now=NOW)
        assert rep["n_posts"] == 32
        assert rep["n_posts_all_time"] == 33

    def test_first_run_says_it_has_no_prior_rather_than_diffing_zeros(self, cfg):
        rep = xi.analyze(_fixture_corpus(), cfg=cfg, prior=None, now=NOW)
        assert rep["diff_vs_prior"]["available"] is False
        assert "first run" in rep["diff_vs_prior"]["reason"]

    def test_week_over_week_diff_reports_movement(self, cfg):
        rows = _fixture_corpus()
        prior = xi.analyze(rows, cfg=cfg, prior=None, now=NOW)
        moved = rows + [_corpus_row(5000 + i, "up 4.7% today") for i in range(8)]
        rep = xi.analyze(moved, cfg=cfg, prior=prior, now=NOW)
        diff = rep["diff_vs_prior"]
        assert diff["available"] is True
        assert diff["prior_n_posts"] == 32
        assert diff["rates"]["decimal_any_rate"]["delta"] > 0
        assert diff["shapes"]["one_liner"]["delta"] > 0

    def test_markdown_renders_every_table(self, cfg):
        md = xi.render_markdown(xi.analyze(_fixture_corpus(), cfg=cfg,
                                           prior=None, now=NOW))
        for heading in ("# X competitive intelligence", "## By shape",
                        "## By register", "## By account",
                        "## Shape distribution vs our quotas",
                        "## Precision + signature rates", "## Week-over-week"):
            assert heading in md, f"{heading!r} missing from the report"
        assert "*(seeding)*" in md, "a thin row must be visibly marked"

    def test_markdown_survives_an_empty_corpus(self, cfg):
        md = xi.render_markdown(xi.analyze([], cfg=cfg, prior=None, now=NOW))
        assert "No posts in the window" in md

    def test_the_module_imports_no_model_client(self):
        """LLM-NEVER-SCORES. Every number here is arithmetic over counters."""
        body = (ROOT / "engine" / "marketing" / "x_intel.py").read_text(encoding="utf-8")
        for banned in ("anthropic", "openai", "llm_client", "deepseek",
                       "from engine.llm", "import llm"):
            assert banned not in body.lower(), f"x_intel must not import {banned!r}"


# ===========================================================================
# GATE E3.6 — the EXEMPLAR STORE: pending never auto-activates
# ===========================================================================
class TestExemplarStore:
    def _candidates(self, cfg):
        return xs.propose_candidates(_fixture_corpus(), cfg=cfg, now=NOW)

    def test_candidates_are_ranked_by_interaction_rate_not_raw_likes(self, cfg):
        """A wire desk at 200k views and a trader at 12k are not comparable on
        likes; ranking on likes fills every register with the biggest account."""
        cands = xs.propose_candidates(_fixture_corpus(), cfg=cfg, now=NOW)
        wire = [c for c in cands if c["register"] == "wire"]
        assert wire, "wire register produced no candidate"
        rates = [c["engagement"]["interaction_rate"] for c in wire]
        assert rates == sorted(rates, reverse=True)

    def test_thin_denominators_are_excluded_outright(self, cfg):
        """min_views: a rate over 900 views is noise wearing a decimal point."""
        rows = [_corpus_row(1, WIRE_ONE_LINER, views=900, likes=900)]
        assert xs.propose_candidates(rows, cfg=cfg, now=NOW) == []

    def test_duplicate_text_is_one_exemplar(self, cfg):
        cands = xs.propose_candidates(_fixture_corpus(), cfg=cfg, now=NOW)
        texts = [c["text"] for c in cands]
        assert len(texts) == len(set(texts))

    def test_candidates_land_in_PENDING_and_activate_nothing(self, tmp_path, cfg):
        res = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        store = res["store"]
        assert res["added"] > 0
        assert store["versions"] == [], "add_pending must never mint a version"
        assert store["latest_version"] == 0
        xs.save_store(store, tmp_path, now=NOW)
        assert xs.active_exemplars("wire", root=tmp_path, cfg=cfg) == [], \
            "an unpinned store shows the writer NOTHING"

    def test_the_pending_pool_is_capped_keeping_the_strongest(self, tmp_path, cfg):
        small = {**cfg, "intel": {**cfg["intel"],
                                  "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                     "max_pending": 2}}}
        res = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=small, now=NOW)
        assert len(res["store"]["pending"]) == 2
        rates = [c["engagement"]["interaction_rate"] for c in res["store"]["pending"]]
        assert rates == sorted(rates, reverse=True)

    def test_promote_mints_a_version_but_does_NOT_activate_it(self, tmp_path, cfg,
                                                              capsys):
        """THE CENTRAL LAW: minting and activating are two operator acts."""
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        res = xs.promote_pending("wave 1", ratified_by="chris", root=tmp_path,
                                 cfg=cfg, now=NOW)
        assert res["ok"] is True and res["version"] == 1
        assert "active_version: 1" in res["activation_hint"]
        # Config still pins nothing => the writer STILL sees nothing.
        assert xs.active_exemplars("wire", root=tmp_path, cfg=cfg) == []
        note = capsys.readouterr().out
        assert note.splitlines()[0].startswith("::notice title=x-intel-exemplars::")
        assert "IT IS NOT LIVE" in note

    def test_the_writer_sees_the_PINNED_version_only(self, tmp_path, cfg):
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        xs.promote_pending("v1", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)
        # A second version exists but is NOT pinned.
        xs.add_pending([{**self._candidates(cfg)[0], "text": "a later exemplar",
                         "text_key": "later0000000000"}],
                       root=tmp_path, cfg=cfg, now=NOW,
                       store=xs.load_store(tmp_path))
        st = xs.load_store(tmp_path)
        st["pending"] = [{"register": "wire", "text": "a later exemplar",
                          "author": "x", "post_id": "9", "text_key": "later000",
                          "engagement": {"interaction_rate": 0.5}}]
        xs.save_store(st, tmp_path, now=NOW)
        xs.promote_pending("v2", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)

        pinned1 = {**cfg, "intel": {**cfg["intel"],
                                    "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                       "active_version": 1}}}
        got = xs.active_exemplars("wire", k=50, root=tmp_path, cfg=pinned1)
        assert got, "version 1 is pinned and must be visible"
        assert all(e["exemplar_version"] == 1 for e in got)
        assert "a later exemplar" not in [e["text"] for e in got]

    def test_a_pin_at_a_missing_version_yields_NOTHING_not_a_neighbour(self, tmp_path,
                                                                       cfg, capsys):
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        xs.promote_pending("v1", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)
        capsys.readouterr()
        bad = {**cfg, "intel": {**cfg["intel"],
                                "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                   "active_version": 7}}}
        assert xs.active_exemplars("wire", root=tmp_path, cfg=bad) == []
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "x-intel-exemplars" in ln)
        assert line.startswith("::warning title=x-intel-exemplars::")

    def test_promotion_requires_a_named_ratifier(self, tmp_path, cfg):
        """An unattributed ratification is indistinguishable from an automatic
        one, which is exactly what this gate exists to prevent."""
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        with pytest.raises(ValueError, match="ratified_by"):
            xs.promote_pending("v1", ratified_by="  ", root=tmp_path, cfg=cfg, now=NOW)

    def test_promoting_an_empty_pool_is_a_refusal_not_an_empty_version(self, tmp_path,
                                                                       cfg):
        res = xs.promote_pending("v1", ratified_by="chris", root=tmp_path,
                                 cfg=cfg, now=NOW)
        assert res["ok"] is False and res["version"] is None

    def test_already_ratified_text_is_not_re_proposed(self, tmp_path, cfg):
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        xs.promote_pending("v1", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)
        again = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        assert again["added"] == 0

    def test_the_writer_hook_accepts_both_register_vocabularies(self, tmp_path, cfg):
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        xs.promote_pending("v1", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)
        pinned = {**cfg, "intel": {**cfg["intel"],
                                   "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                      "active_version": 1}}}
        # "wire" is both an intel register and a house dial register.
        assert xs.active_exemplars("wire", root=tmp_path, cfg=pinned)
        # "persona" is a house name covering trader + macro_color.
        assert xs.active_exemplars("persona", root=tmp_path, cfg=pinned)
        # An unknown name falls back to every register rather than to nothing.
        assert xs.active_exemplars("nonsense", root=tmp_path, cfg=pinned)

    def test_the_hook_order_is_deterministic(self, tmp_path, cfg):
        merged = xs.add_pending(self._candidates(cfg), root=tmp_path, cfg=cfg, now=NOW)
        xs.save_store(merged["store"], tmp_path, now=NOW)
        xs.promote_pending("v1", ratified_by="chris", root=tmp_path, cfg=cfg, now=NOW)
        pinned = {**cfg, "intel": {**cfg["intel"],
                                   "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                      "active_version": 1}}}
        a = xs.active_exemplars(None, k=5, root=tmp_path, cfg=pinned)
        b = xs.active_exemplars(None, k=5, root=tmp_path, cfg=pinned)
        assert [e["post_id"] for e in a] == [e["post_id"] for e in b]

    def test_a_corrupt_store_degrades_to_no_exemplars(self, tmp_path, cfg, capsys):
        xs.store_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        xs.store_path(tmp_path).write_text("{not json", encoding="utf-8")
        pinned = {**cfg, "intel": {**cfg["intel"],
                                   "exemplar_store": {**cfg["intel"]["exemplar_store"],
                                                      "active_version": 1}}}
        assert xs.active_exemplars("wire", root=tmp_path, cfg=pinned) == []
        assert "::warning title=x-intel-exemplars::" in capsys.readouterr().out

    def test_active_version_meta_explains_an_empty_read(self, tmp_path, cfg):
        meta = xs.active_version_meta(root=tmp_path, cfg=cfg)
        assert meta["pinned"] is None
        assert "dark default" in meta["reason"]


# ===========================================================================
# GATE E3.7 — config + the writer-hook contract
# ===========================================================================
class TestConfig:
    def test_the_roster_is_the_dockets_17_accounts(self, cfg):
        handles = {e["handle"] for e in xi.roster(cfg)}
        assert len(handles) == 17
        docket = {
            "DeItaone", "FirstSquawk", "unusual_whales", "KobeissiLetter",
            "Barchart", "StockMKTNewz", "wallstengine", "charliebilello",
            "RyanDetrick", "bespokeinvest", "markminervini", "PeterLBrandt",
            "alphatrends", "traderstewie", "Mr_Derivatives", "jam_croissant",
            "LizAnnSonders",
        }
        assert handles == docket

    def test_every_roster_register_is_a_known_register(self, cfg):
        assert all(e["register"] in xi.REGISTERS for e in xi.roster(cfg))

    def test_the_exemplar_pin_ships_UNSET(self, cfg):
        """Dark by default: a mechanism that changes how every desk sounds does
        not arrive armed."""
        assert xs.pinned_version(cfg) is None
        assert cfg["intel"]["exemplar_store"]["active_version"] is None

    def test_the_call_cap_is_the_documented_600(self, cfg):
        conf = xi.resolve_cfg(cfg)
        assert conf["monthly_call_cap"] == 600
        assert conf["monthly_usd_cap"] > 0
        assert conf["price_per_1k_tweets_usd"] == 0.15

    def test_a_handleless_roster_entry_is_dropped_not_polled(self):
        assert xi.roster({"intel": {"roster": [{"register": "wire"}, "DeItaone"]}}) == [
            {"handle": "DeItaone", "register": "unknown", "tier": "weekly", "note": ""}
        ]


# ===========================================================================
# GATE E3.8 — the weekly workflow
# ===========================================================================
@pytest.fixture(scope="module")
def wf_path() -> Path:
    return ROOT / ".github" / "workflows" / "marketing-x-intel.yml"


@pytest.fixture(scope="module")
def wf(wf_path) -> dict:
    return yaml.safe_load(wf_path.read_text(encoding="utf-8"))


class TestWorkflow:
    def test_the_workflow_parses(self, wf):
        assert wf["name"] == "marketing-x-intel"
        assert "harvest" in wf["jobs"]

    def test_it_runs_weekly_on_sunday_evening_utc(self, wf):
        # PyYAML resolves a bare `on:` key to the boolean True (YAML 1.1).
        triggers = wf.get("on", wf.get(True))
        crons = [c["cron"] for c in triggers["schedule"]]
        assert crons == ["0 22 * * 0"], crons
        assert "workflow_dispatch" in triggers

    def test_it_carries_the_api_key(self, wf_path):
        body = wf_path.read_text(encoding="utf-8")
        assert "TWITTERAPI_IO_KEY: ${{ secrets.TWITTERAPI_IO_KEY }}" in body

    def test_it_runs_off_the_render_pool(self, wf):
        assert wf["jobs"]["harvest"]["runs-on"] == "ubuntu-latest", \
            "the render budget is law — this may never touch the macstudio pool"

    def test_it_has_its_own_concurrency_group_that_never_cancels(self, wf):
        conc = wf["concurrency"]
        assert conc["group"] == "marketing-x-intel"
        assert conc["cancel-in-progress"] is False, \
            "a cancelled harvest may already have spent"

    def test_checkout_is_shallow_and_the_push_loop_deepens(self, wf, wf_path):
        steps = wf["jobs"]["harvest"]["steps"]
        checkout = next(s for s in steps if "actions/checkout" in str(s.get("uses", "")))
        assert checkout["with"]["fetch-depth"] == 1
        assert "git fetch --depth" in wf_path.read_text(encoding="utf-8")

    def test_it_commits_only_this_lanes_paths_with_skip_ci(self, wf_path):
        body = wf_path.read_text(encoding="utf-8")
        assert "git add data/marketing/x_intel" in body
        assert "[skip ci]" in body
        assert "git add data/marketing/outbox" not in body, "ledger law: own paths only"

    def test_the_workflow_cannot_promote_or_activate(self, wf_path):
        """A scheduled run may fill the pending pool and nothing else."""
        body = wf_path.read_text(encoding="utf-8")
        assert "--promote" not in body
        assert "--ratified-by" not in body
        assert "active_version" not in body.split("# ─")[-1]

    def test_it_runs_the_harvest_script(self, wf_path):
        assert "python -m scripts.x_intel_harvest" in wf_path.read_text(encoding="utf-8")


# ===========================================================================
# GATE E3.9 — the RUN produces no commit noise when nothing changed
# ===========================================================================
class TestRunChurn:
    def _seed(self, tmp_path, cfg):
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "marketing.yml").write_text(
            yaml.safe_dump(cfg), encoding="utf-8")
        xi.append_corpus(_fixture_corpus(), root=tmp_path)

    def _run(self, tmp_path, *args):
        import scripts.x_intel_harvest as harvest

        return harvest.main(["--root", str(tmp_path), *args])

    def test_a_dark_run_leaves_NO_diff(self, tmp_path, cfg, monkeypatch, capsys):
        """The workflow's own claim: with no secret the run is green and the
        diff is empty. A rewritten `generated_at` or `last_run` every week would
        put a pure-timestamp commit on main for a run that did nothing."""
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        self._seed(tmp_path, cfg)
        assert self._run(tmp_path) == 0            # first run writes the report
        capsys.readouterr()
        report_before = xi.report_path(tmp_path).read_text(encoding="utf-8")
        md_before = xi.weekly_report_path(tmp_path).read_text(encoding="utf-8")
        assert not xi.state_path(tmp_path).exists(), \
            "a run that spent nothing must not rewrite the spend counter"

        store_before = xs.store_path(tmp_path).read_text(encoding="utf-8")

        assert self._run(tmp_path) == 0            # second, identical run
        capsys.readouterr()
        assert xi.report_path(tmp_path).read_text(encoding="utf-8") == report_before
        assert xi.weekly_report_path(tmp_path).read_text(encoding="utf-8") == md_before
        assert xs.store_path(tmp_path).read_text(encoding="utf-8") == store_before
        assert not xi.state_path(tmp_path).exists()

    def test_analyze_only_forces_a_rebuild(self, tmp_path, cfg, monkeypatch, capsys):
        monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)
        self._seed(tmp_path, cfg)
        self._run(tmp_path)
        capsys.readouterr()
        out = json.loads(_last_json(capsys, self._run, tmp_path, "--analyze-only"))
        assert "skipped" not in out["analysis"]
        assert out["analysis"]["n_posts"] == 32

    def test_a_dry_run_writes_nothing_at_all(self, tmp_path, cfg, monkeypatch,
                                             capsys):
        monkeypatch.setenv("TWITTERAPI_IO_KEY", "test-key")
        self._seed(tmp_path, cfg)
        assert self._run(tmp_path, "--dry-run") == 0
        capsys.readouterr()
        assert not xi.report_path(tmp_path).exists()
        assert not xi.state_path(tmp_path).exists()
        assert not xs.store_path(tmp_path).exists()

    def test_promote_requires_a_ratifier_at_the_cli_too(self, tmp_path, cfg,
                                                        capsys):
        self._seed(tmp_path, cfg)
        assert self._run(tmp_path, "--promote", "v1") == 2
        line = next(ln for ln in capsys.readouterr().out.splitlines()
                    if "x-intel-exemplars" in ln)
        assert line.startswith("::error title=x-intel-exemplars::")


def _last_json(capsys, fn, *args):
    fn(*args)
    out = capsys.readouterr().out
    return out[out.index("{"):]


# ===========================================================================
# GATE E6 — the LEARNING SPINE: shape / angle / trigger provenance
# ===========================================================================
def _label_row(**over):
    row = lb.new_row(
        surface=over.pop("surface", "post"),
        subject_id=over.pop("subject", "s1"),
        as_of=over.pop("day", "2026-07-28"),
        account=over.pop("account", "kelly"),
        format=over.pop("fmt", "signal"),
        register=over.pop("register", "analysis"),
        hook_family=over.pop("hook_family", "confirmation_check"),
        observed=over.pop("observed", {"impressions": 1000, "likes": 40}),
        label=over.pop("label", 0.05),
        observed_at="2026-07-28T15:00:00Z",
    )
    row.update(over)
    return row


class TestLearningSpineProvenance:
    def test_the_row_carries_shape_angle_trigger(self):
        row = _label_row()
        for field in lb.PROVENANCE_DIMS:
            assert field in row, f"{field} must be on every label row"

    def test_an_absent_field_is_unknown_never_a_dropped_row(self):
        """Dropping unstamped rows would make the shape table's denominator
        'posts the mixer happened to stamp' — the denominator defect that
        deletes losers from a rate."""
        assert lb.provenance_for({}) == {"shape": "unknown", "angle": "unknown",
                                         "trigger": "unknown"}
        assert _label_row()["shape"] == "unknown"

    def test_provenance_is_read_off_item_source(self):
        """outbox.py stamps source.shape/source.angle; hot_tape stamps
        source.trigger. All three come off the SAME dict."""
        item = {"source": {"shape": "two_part", "angle": "level_watch",
                           "trigger": "sector_rout"}}
        assert lb.provenance_for(item) == {"shape": "two_part",
                                           "angle": "level_watch",
                                           "trigger": "sector_rout"}

    def test_a_queue_item_key_is_a_fallback_for_the_source_key(self):
        """The queue item carries shape/angle before the outbox flattens them."""
        assert lb.provenance_for({"shape": "list"})["shape"] == "list"

    def test_harvest_stamps_provenance_from_the_outbox_item(self, tmp_path):
        from engine.marketing.outbox import enqueue, make_item, transition

        item = make_item(account="flagship", kind="signal",
                         text="$PLTR reclaimed the 50-day. Watching.",
                         as_of="2026-07-28", provenance="content_studio",
                         now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc),
                         source={"shape": "two_part", "angle": "level_watch"})
        enqueue(item, root=tmp_path, max_per_account_day=99)
        transition(item["id"], "approved", actor="t", root=tmp_path)
        transition(item["id"], "posting", actor="t", root=tmp_path)
        transition(item["id"], "posted", actor="t", root=tmp_path,
                   receipt={"external_id": "buf-1", "at": "2026-07-28T13:00:00Z"})
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps({
            "remote_id": "buf-1", "account": "flagship",
            "metrics": {"impressions": 1000, "likes": 30, "reposts": 4, "comments": 6},
            "polled_at": "2026-07-28T14:00:00Z", "ok": True,
        }) + "\n", encoding="utf-8")

        rows = lb.harvest_post_labels(root=tmp_path,
                                      now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        assert len(rows) == 1
        assert rows[0]["shape"] == "two_part"
        assert rows[0]["angle"] == "level_watch"
        assert rows[0]["trigger"] == "unknown", "a planned post has no detector trigger"

    def test_an_orphan_metrics_row_reports_unknown_provenance(self, tmp_path):
        mp = tmp_path / "data" / "marketing" / "post_metrics.jsonl"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps({
            "remote_id": "orphan-1", "account": "flagship",
            "metrics": {"impressions": 500, "likes": 3},
            "polled_at": "2026-07-28T14:00:00Z", "ok": True,
        }) + "\n", encoding="utf-8")
        rows = lb.harvest_post_labels(root=tmp_path,
                                      now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        assert len(rows) == 1
        assert rows[0]["shape"] == "unknown"

    def test_the_scorecard_buckets_by_each_provenance_dim(self):
        rows = ([_label_row(subject=f"a{i}", shape="one_liner", angle="level_watch",
                            trigger="unknown") for i in range(25)]
                + [_label_row(subject=f"b{i}", shape="two_part", angle="risk_frame",
                              trigger="sector_rout") for i in range(5)])
        card = lb.scorecard(rows, now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        assert card["provenance_dims"] == list(lb.PROVENANCE_DIMS)
        prov = card["provenance"]
        assert set(lb.PROVENANCE_DIMS) <= set(prov)
        shapes = {e["shape"]: e for e in prov["shape"]}
        assert shapes["one_liner"]["n"] == 25
        assert shapes["two_part"]["n"] == 5

    def test_a_thin_provenance_bucket_may_not_be_cited(self):
        """E6's purpose is quota moves that CITE a table row. A row under the
        n-floor carries no ranking claim, exactly like a joint cell."""
        rows = ([_label_row(subject=f"a{i}", shape="one_liner") for i in range(25)]
                + [_label_row(subject=f"b{i}", shape="two_part") for i in range(5)])
        card = lb.scorecard(rows, now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        shapes = {e["shape"]: e for e in card["provenance"]["shape"]}
        assert shapes["two_part"]["verdict"] == "seeding"
        assert "verdict" not in shapes["one_liner"]

    def test_rows_with_NO_provenance_still_appear_under_unknown(self):
        """The conservative rule: absent -> "unknown", never a dropped row."""
        rows = [_label_row(subject=f"x{i}") for i in range(6)]
        card = lb.scorecard(rows, now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        for dim in lb.PROVENANCE_DIMS:
            table = card["provenance"][dim]
            assert [e[dim] for e in table] == ["unknown"]
            assert table[0]["n"] == 6

    def test_the_joint_cell_key_is_unchanged(self):
        """PROVENANCE_DIMS are MARGINAL tables. Folding them into DIMS would
        multiply the cell space ~360x and make every cell "seeding" — see the
        cardinality note on labels.PROVENANCE_DIMS."""
        assert lb.DIMS == ("account", "format", "register", "hook_family")
        rows = [_label_row(subject=f"x{i}", shape=f"s{i}") for i in range(6)]
        card = lb.scorecard(rows, now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        assert len(card["cells"]) == 1, "shape must not split the joint cells"

    def test_null_labels_are_counted_but_never_medianed(self):
        rows = ([_label_row(subject=f"a{i}", shape="one_liner") for i in range(3)]
                + [_label_row(subject=f"n{i}", shape="one_liner", label=None)
                   for i in range(2)])
        card = lb.scorecard(rows, now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc))
        entry = card["provenance"]["shape"][0]
        assert (entry["n"], entry["n_labelled"], entry["n_null"]) == (5, 3, 2)
        assert entry["med_label"] == 0.05

    def test_consolidate_writes_the_provenance_tables(self, tmp_path):
        lb._write_tracked(lb.labels_path(tmp_path),
                          [_label_row(subject=f"t{i}", shape="one_liner")
                           for i in range(3)])
        lb.consolidate(now=datetime(2026, 7, 28, 15, tzinfo=timezone.utc),
                       root=tmp_path)
        card = json.loads(lb.scorecard_path(tmp_path).read_text(encoding="utf-8"))
        assert card["provenance"]["shape"][0]["shape"] == "one_liner"


# ===========================================================================
# E-wave adversarial review — the store's own failure modes and THE WRITER HOOK
# ===========================================================================

class TestProposalSortKeyIsScalar:
    """MAJOR 8. The candidate sort key was
    ``(-rate, -views, str(id), row, rate)`` — a raw dict inside a tuple Python
    sorts. Two rows tying on the first THREE elements (the corpus carries rows
    with no ``id``, so ``str(id or "")`` is ``""`` for both) make it compare
    dict to dict and raise TypeError.

    That raise landed in step 3 of the harvest, AFTER step 1 had already spent
    money and written state.json — and the workflow's ``success()``-gated commit
    then threw that state away, re-opening the whole monthly budget on the next
    run.
    """

    def test_two_id_less_rows_with_identical_engagement_do_not_raise(self):
        a = _corpus_row("", "BREAKING: one wire line that says a thing.")
        b = _corpus_row("", "BREAKING: a different wire line entirely.")
        a["id"] = b["id"] = ""          # both rows carry no post id
        out = xs.propose_candidates([a, b], cfg={}, now=NOW)
        assert len(out) == 2, out

    def test_the_proposal_stays_deterministic_across_two_runs(self):
        rows = _fixture_corpus()
        first = xs.propose_candidates(rows, cfg={}, now=NOW)
        second = xs.propose_candidates(rows, cfg={}, now=NOW)
        assert [c["text_key"] for c in first] == [c["text_key"] for c in second]


class TestStoreSchemaIsValidatedOnRead:
    """m3. ``load_store`` adopted any dict wholesale and ``save_store`` re-stamps
    ``STORE_SCHEMA`` unconditionally — so a store written under a different
    schema was silently relabelled current on the next write, with its entry
    shape assumed rather than verified. Those entries feed the WRITER PROMPT.
    """

    @staticmethod
    def _write(tmp_path, blob) -> Path:
        d = tmp_path / "data" / "marketing" / "x_intel"
        d.mkdir(parents=True, exist_ok=True)
        (d / "exemplar_store.json").write_text(json.dumps(blob), encoding="utf-8")
        return tmp_path

    def test_a_foreign_schema_reads_as_empty_and_says_so(self, tmp_path, capsys):
        root = self._write(tmp_path, {
            "schema": "marketing.x_exemplar_store/v0",
            "latest_version": 9,
            "versions": [{"version": 9, "entries": [{"register": "wire",
                                                     "text": "FROM THE OLD SHAPE"}]}],
            "pending": [],
        })
        store = xs.load_store(root)
        assert store["versions"] == [], "a foreign-schema store was adopted wholesale"
        assert store["latest_version"] == 0

        lines = capsys.readouterr().out.splitlines()
        assert [ln for ln in lines
                if ln.startswith("::warning") and "x-intel-exemplars" in ln], (
            "the schema mismatch was silent — a start-of-line ::warning is the "
            "only form GitHub surfaces")

    def test_the_current_schema_still_round_trips(self, tmp_path):
        root = self._write(tmp_path, {
            "schema": xs.STORE_SCHEMA, "latest_version": 2,
            "versions": [{"version": 2, "entries": []}], "pending": [],
        })
        assert xs.load_store(root)["latest_version"] == 2

    def test_a_saved_store_reloads(self, tmp_path):
        """The mirror: save_store's own output must not trip its reader."""
        (tmp_path / "data" / "marketing" / "x_intel").mkdir(parents=True)
        assert xs.save_store({"latest_version": 1, "versions": [], "pending": []},
                             tmp_path, now=NOW)
        assert xs.load_store(tmp_path)["latest_version"] == 1


class TestCopywriterExemplarHook:
    """BLOCKER 3, writer half. §10 E3 requires "writer/critic prompts load
    exemplars from the store (config-pinned version, never auto-flipped)".
    ``active_exemplars`` shipped with NO production caller: copywriter imported
    neither exemplar_store nor x_intel, so the whole harvest -> pending ->
    operator promotion -> config pin chain ended at a function only tests ran.
    """

    @staticmethod
    def _store(tmp_path) -> Path:
        d = tmp_path / "data" / "marketing" / "x_intel"
        d.mkdir(parents=True, exist_ok=True)
        (d / "exemplar_store.json").write_text(json.dumps({
            "schema": xs.STORE_SCHEMA, "latest_version": 4,
            "versions": [
                {"version": 3, "ratified_by": "chris", "n_entries": 1, "entries": [
                    {"register": "wire", "text": "KOSPI plunges 41.7% on the session.",
                     "post_id": "1", "engagement": {"interaction_rate": 0.3}}]},
                {"version": 4, "ratified_by": "chris", "n_entries": 1, "entries": [
                    {"register": "wire", "text": "NEWER UNPINNED SHOT",
                     "post_id": "2", "engagement": {"interaction_rate": 0.9}}]},
            ],
            "pending": [{"register": "wire", "text": "PENDING SHOT", "post_id": "3",
                         "engagement": {"interaction_rate": 0.99}}],
        }), encoding="utf-8")
        return tmp_path

    def test_unpinned_prompts_are_byte_identical_to_the_baseline(self, tmp_path):
        """DARK-SAFE. `active_version: null` is the shipped state, so today's
        prompt may not move by one byte — and the store is never opened."""
        from engine.marketing import copywriter as cw

        root = self._store(tmp_path)
        base = cw._v2_system_prompt({})
        assert cw._v2_system_prompt({}, root=root) == base
        assert cw._v2_system_prompt(
            {"intel": {"exemplar_store": {"active_version": None}}}, root=root) == base
        assert cw.store_exemplar_block(
            {"intel": {"exemplar_store": {"active_version": None}}}, root=root) == ""

    def test_a_pinned_version_reaches_the_prompt_the_provider_receives(
            self, monkeypatch, tmp_path):
        """Through `write_posts_llm_v2` itself — the real production writer —
        capturing what is handed to `client.messages.create` as `system`."""
        from engine import llm_auth
        from engine.marketing import copywriter as cw

        root = self._store(tmp_path)
        seen: dict = {}

        class _Client:
            class messages:
                @staticmethod
                def create(**kw):
                    seen.update(kw)
                    raise RuntimeError("stop — the prompt is the assertion")

        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        monkeypatch.setattr(llm_auth, "build_providers",
                            lambda *a, **k: [{"name": "oauth", "client": _Client(),
                                              "model": "m", "env_var": "X",
                                              "cred": "x"}])

        def _make_call(providers, fn, context=""):
            try:
                fn(providers[0]["client"], providers[0]["model"])
            except RuntimeError:
                pass
            return None, "captured", "oauth"

        monkeypatch.setattr(llm_auth, "make_call", _make_call)
        cfg = {"llm": {"enabled": True},
               "intel": {"exemplar_store": {"active_version": 3}}}
        cw.write_posts_llm_v2([{"account": "flagship", "type": "signal",
                                "ticker": "NVDA", "top_facts": []}], cfg, root=root)

        system = seen.get("system") or ""
        assert "KOSPI plunges 41.7% on the session." in system, (
            "the pinned exemplar never reached the writer's system prompt")
        assert "NEWER UNPINNED SHOT" not in system, "the store auto-flipped forward"
        assert "PENDING SHOT" not in system, "an unratified candidate reached the writer"

    def test_the_pin_comes_only_from_config_never_from_latest_version(self, tmp_path):
        from engine.marketing import copywriter as cw

        root = self._store(tmp_path)
        # A store with versions but NO pin still yields nothing.
        assert cw.store_exemplar_block({}, root=root) == ""
        # A pin at a version the store does not have yields nothing — never a
        # neighbouring version.
        assert cw.store_exemplar_block(
            {"intel": {"exemplar_store": {"active_version": 99}}}, root=root) == ""

    def test_exemplar_numbers_do_not_widen_the_writers_numeric_gate(self, tmp_path):
        """EPISTEMICS: the engine computes, the model phrases, and an exemplar's
        figures are somebody else's. A model that lifts one must be rejected
        exactly as if it had invented it."""
        from engine.marketing import copywriter as cw

        root = self._store(tmp_path)
        block = cw.store_exemplar_block(
            {"intel": {"exemplar_store": {"active_version": 3}}}, root=root)
        assert "41.7%" in block, "fixture is degenerate — no number in the exemplar"

        ctx = {"account": "flagship", "type": "macro", "ticker": "",
               "shape": "two_part", "numbers_whitelist": ["2.1%"],
               "top_facts": [{"text": "Breadth held at 2.1% on the session."}]}
        hits = cw.validate_copy_v2(
            "Breadth held at 2.1%.\n\nKOSPI plunges 41.7% on the session.", ctx)
        assert [h for h in hits if "41.7" in h], (
            f"a figure that exists only in an exemplar cleared the numeric gate: {hits}")


class TestWorkflowCommitsSpentStateEvenOnFailure:
    """MAJOR 8. state.json holds the monthly call/USD counter and is written in
    step 1, immediately AFTER the money is spent — while steps 2 and 3 can still
    raise. Under ``success()`` any such crash discarded the counter and the next
    run read $0.00, re-opening a budget the account had already been billed for.
    """

    def test_the_commit_step_runs_on_always(self, wf):
        steps = wf["jobs"]["harvest"]["steps"]
        commit = next(s for s in steps
                      if "git add data/marketing/x_intel" in str(s.get("run", "")))
        assert "always()" in commit["if"], commit["if"]
        assert "success()" not in commit["if"], (
            "a crash after the spend still discards the spend counter")
        # Never on a dry run: it writes nothing.
        assert "dry_run" in commit["if"]

    def test_the_summary_reads_pure_json_not_a_tee_of_mixed_stdout(self, wf_path):
        """`| tee /tmp/x_intel_run.json` captured ::warning/::notice lines into a
        file the summary block fences as ```json."""
        body = wf_path.read_text(encoding="utf-8")
        assert "tee /tmp/x_intel_run.json" not in body
        assert "--json-out /tmp/x_intel_run.json" in body

    def test_json_out_writes_only_the_report(self, tmp_path, capsys):
        """And the annotations still reach stdout, where GitHub parses them."""
        import scripts.x_intel_harvest as harvest

        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "marketing.yml").write_text(
            yaml.safe_dump({"intel": {"enabled": True, "roster": []}}), encoding="utf-8")
        out = tmp_path / "run.json"
        assert harvest.main(["--root", str(tmp_path), "--dry-run",
                             "--json-out", str(out)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["dry_run"] is True
        assert "budget" in payload
