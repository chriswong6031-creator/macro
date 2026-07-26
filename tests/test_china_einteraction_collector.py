"""Tests for collectors/china_einteraction.py — 上证e互动 (SSE) investor-Q&A collector.

Pure/offline surface only — NO network. Fixtures are the REAL responses captured from
sns.sseinfo.com on 2026-07-25: the /allcompany.do directory fragment (note the UNQUOTED
uid attribute, exactly as the venue serves it) and two /ajax/userfeeds.do items trimmed
out of the live 18 KB body with every parsed attribute and string byte-faithful. The
trimmed feed parses to the same rows as the full capture.

Covers:
  - directory fragment → {code: uid} (unquoted attribute; avatar filename is the code)
  - feed item parse: feed_id, code/name prefix, question/answer text, both timestamps
  - parse_feed_from / parse_code_prefix as pure functions incl. their degrade paths
  - unanswered item (no .m_qa block) and the sub-300-byte empty-feed rule
  - map-build night short-circuits the feed pulls; a truncated build resumes
  - dedup keep-LAST on feed_id, cursor rotation, the wall-clock guard

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_einteraction as ce  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# REAL captured fixtures (sns.sseinfo.com, 2026-07-25)
# --------------------------------------------------------------------------- #

# POST /allcompany.do → {"content": "<html>"} — first 3 companyBox blocks verbatim.
# The uid attribute is UNQUOTED (uid=65) exactly as served; lxml handles it.
_ALLCOMPANY_FRAGMENT = (
    "<div class='companyBox'>\t\t<a rel='tag' uid=65 href='user.do?uid=65' title='浦发银行'>"
    "\t\t\t<img src='https://sns.sseinfo.com/resources/images/avatar/company/600000.png"
    "?random=1785048740083' height='40px' width='40px'  /><br/>\t\t</a>     "
    "<div><a href='user.do?uid=65'>600000</a></div>     "
    "<div><a href='user.do?uid=65'>浦发银行</a></div> </div>"
    "<div class='companyBox'>\t\t<a rel='tag' uid=92 href='user.do?uid=92' title='白云机场'>"
    "\t\t\t<img src='https://sns.sseinfo.com/resources/images/avatar/company/600004.png"
    "?random=1785048740083' height='40px' width='40px'  /><br/>\t\t</a>     "
    "<div><a href='user.do?uid=92'>600004</a></div>     "
    "<div><a href='user.do?uid=92'>白云机场</a></div> </div>"
    "<div class='companyBox'>\t\t<a rel='tag' uid=181 href='user.do?uid=181' title='东风股份'>"
    "\t\t\t<img src='https://sns.sseinfo.com/resources/images/avatar/company/600006.png"
    "?random=1785048740083' height='40px' width='40px'  /><br/>\t\t</a>     "
    "<div><a href='user.do?uid=181'>600006</a></div>     "
    "<div><a href='user.do?uid=181'>东风股份</a></div> </div>"
)

# POST /ajax/userfeeds.do?...&uid=65 → PURE HTML. Two real items (share/like/comment
# chrome stripped); the question anchor prefix, both m_feed_from strings and the
# nested .m_qa answer block are exactly as served.
_FEED_HTML = """
<div class="m_feed_item" id="item-1756552">
<div class="m_feed_detail" style="border: none;">
<div class="m_feed_face">
<a href="user.do?uid=308780" rel="face" title="投资者_1746777412006" uid="308780"><img alt="" height="40" src="https://sns.sseinfo.com/resources/images/avatar/202505/308780.png" title="投资者_1746777412006" width="40"/></a>
<p>投资者_1746777412006</p>
</div>
<div class="m_feed_cnt">
<div class="m_feed_txt">
<a href="user.do?uid=65">:浦发银行(600000)</a>今年以来，浦发业绩上涨，但股价已经跌去30%，股民损失惨重，请问是什么原因造成的呢？
 </div>
<div class="m_feed_func">
<div class="m_feed_from">
<span>2026年06月25日 11:40</span>
<em>来自</em>
<a href="javascript:;">网站</a>
</div>
</div>
</div>
</div>
<div class="m_feed_detail m_qa">
<div class="m_feed_face">
<a class="ansface" href="user.do?uid=65" rel="tag" title="65" uid="65"><img alt="" height="30" src="https://sns.sseinfo.com/resources/images/avatar/company/600000.png" title="浦发银行" width="30"/></a>
<p>浦发银行</p>
</div>
<div class="m_feed_cnt">
<div class="m_feed_txt" id="m_feed_txt-1756552">
 上市公司股价波动受证券市场等多方面影响，公司密切关注股价走势和自身市值表现，坚守主业本源，把深耕经营、夯实基本面作为稳定内在价值的根本抓手，持续完善价值提升和市值管理工作的长效机制。感谢您的提问！
 </div>
</div>
<div class="m_feed_func top10" style="margin-left: 70px;">
<div class="m_feed_from" style="padding-left: 35px;">
<span>2026年07月01日 17:38</span>
<em>来自</em>
<a href="javascript:;">网站</a>
</div>
</div>
</div>
</div>
<div class="m_feed_item" id="item-1757193">
<div class="m_feed_detail" style="border: none;">
<div class="m_feed_face">
<a href="user.do?uid=335880" rel="face" title="投资者_1782380191155" uid="335880"><img alt="" height="40" src="https://sns.sseinfo.com/resources/images/avatar/202606/335880.png" title="投资者_1782380191155" width="40"/></a>
<p>投资者_1782380191155</p>
</div>
<div class="m_feed_cnt">
<div class="m_feed_txt">
<a href="user.do?uid=65">:浦发银行(600000)</a>什么时候分红
 </div>
<div class="m_feed_func">
<div class="m_feed_from">
<span>2026年06月25日 17:43</span>
<em>来自</em>
<a href="javascript:;">网站</a>
</div>
</div>
</div>
</div>
<div class="m_feed_detail m_qa">
<div class="m_feed_face">
<a class="ansface" href="user.do?uid=65" rel="tag" title="65" uid="65"><img alt="" height="30" src="https://sns.sseinfo.com/resources/images/avatar/company/600000.png" title="浦发银行" width="30"/></a>
<p>浦发银行</p>
</div>
<div class="m_feed_cnt">
<div class="m_feed_txt" id="m_feed_txt-1757193">
 公司2025年度利润分配方案已经2026年6月26日召开的公司2025年年度股东会审议通过，后续将根据相关要求尽快推进分红派息相关事宜。感谢您的提问！
 </div>
</div>
<div class="m_feed_func top10" style="margin-left: 70px;">
<div class="m_feed_from" style="padding-left: 35px;">
<span>2026年07月01日 17:38</span>
<em>来自</em>
<a href="javascript:;">网站</a>
</div>
</div>
</div>
</div>
"""

# Same markup with the .m_qa block removed — an as-yet-unanswered question.
_FEED_HTML_UNANSWERED = _FEED_HTML.split('<div class="m_feed_detail m_qa">')[0] + "</div>"

_TS = "2026-07-25T12:00:00+00:00"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# directory fragment → uid map
# --------------------------------------------------------------------------- #

class TestParseCompanyPage:
    def test_real_fragment_maps_code_to_uid(self):
        assert ce.parse_company_page(_ALLCOMPANY_FRAGMENT) == {
            "600000": "65", "600004": "92", "600006": "181"}

    def test_unquoted_uid_attribute_is_read(self):
        # uid=65 (no quotes) is how the venue serves it; a naive regex on uid="…" misses it.
        assert ce.parse_company_page(_ALLCOMPANY_FRAGMENT)["600000"] == "65"

    def test_empty_and_codeless_fragments_degrade(self):
        assert ce.parse_company_page("") == {}
        assert ce.parse_company_page("<div><a rel='tag' uid=9>no image</a></div>") == {}


# --------------------------------------------------------------------------- #
# pure string parsers
# --------------------------------------------------------------------------- #

class TestParseFeedFrom:
    def test_real_string(self):
        assert ce.parse_feed_from("2026年06月25日 11:40 来自 网站") == (
            "2026-06-25T11:40:00+08:00", "网站")

    def test_seconds_variant(self):
        ts, src = ce.parse_feed_from("2026年6月5日 9:07:31 来自 手机")
        assert ts == "2026-06-05T09:07:31+08:00"
        assert src == "手机"

    def test_unparseable_date_is_blank_never_invented(self):
        assert ce.parse_feed_from("来自 网站") == ("", "网站")
        assert ce.parse_feed_from("") == ("", "")
        assert ce.parse_feed_from(None) == ("", "")

    def test_missing_source_clause(self):
        ts, src = ce.parse_feed_from("2026年06月25日 11:40")
        assert ts == "2026-06-25T11:40:00+08:00"
        assert src == ""


class TestParseCodePrefix:
    def test_real_prefix(self):
        assert ce.parse_code_prefix(":浦发银行(600000)") == ("600000", "浦发银行")

    def test_fullwidth_parens(self):
        assert ce.parse_code_prefix("：白云机场（600004）") == ("600004", "白云机场")

    def test_absent_prefix(self):
        assert ce.parse_code_prefix("no code here") == ("", "")
        assert ce.parse_code_prefix("") == ("", "")


# --------------------------------------------------------------------------- #
# feed item parse (real markup)
# --------------------------------------------------------------------------- #

class TestParseFeedItems:
    def test_two_items_from_the_real_body(self):
        rows = ce.parse_feed_items(_FEED_HTML, _TS)
        assert [r["feed_id"] for r in rows] == ["1756552", "1757193"]

    def test_first_item_field_by_field(self):
        row = ce.parse_feed_items(_FEED_HTML, _TS)[0]
        assert row["feed_id"] == "1756552"
        assert row["code"] == "600000"
        assert row["name"] == "浦发银行"
        assert row["asker_uid"] == "308780"
        assert row["question"].startswith("今年以来，浦发业绩上涨")
        # The name(code) anchor prefix is stripped out of the question body.
        assert "600000" not in row["question"]
        assert row["answer"].startswith("上市公司股价波动受证券市场等多方面影响")
        assert row["q_ts"] == "2026-06-25T11:40:00+08:00"
        assert row["a_ts"] == "2026-07-01T17:38:00+08:00"
        assert row["q_source"] == "网站"
        assert row["a_source"] == "网站"
        assert row["fetched_at"] == _TS

    def test_second_item_short_question(self):
        row = ce.parse_feed_items(_FEED_HTML, _TS)[1]
        assert row["question"] == "什么时候分红"
        assert row["asker_uid"] == "335880"
        assert row["q_ts"] == "2026-06-25T17:43:00+08:00"

    def test_unanswered_item_has_empty_answer_fields(self):
        rows = ce.parse_feed_items(_FEED_HTML_UNANSWERED, _TS)
        assert len(rows) == 1
        assert rows[0]["question"].startswith("今年以来")
        assert rows[0]["answer"] == ""
        assert rows[0]["a_ts"] == "" and rows[0]["a_source"] == ""

    def test_empty_body(self):
        assert ce.parse_feed_items("", _TS) == []
        assert ce.parse_feed_items("<html><body></body></html>", _TS) == []

    def test_shard_code_is_authoritative_over_the_text_prefix(self):
        # F9: the collector knows which company it queried. A question that merely
        # MENTIONS another listco (or carries no prefix) must never re-key the row —
        # the text-parsed prefix is only a display-name fallback.
        rows = ce.parse_feed_items(_FEED_HTML, _TS, code="601999")
        assert rows and all(r["code"] == "601999" for r in rows)
        assert rows[0]["name"] == "浦发银行"    # prefix still supplies the display name


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

class TestQaStore:
    def test_rows_land_and_dedup_keep_last(self, store):
        rows = ce.parse_feed_items(_FEED_HTML, _TS)
        assert ce.write_qa(rows) == 2
        # Same feed_id re-pulled, now answered → CORRECTS, never duplicates.
        later = ce.parse_feed_items(_FEED_HTML_UNANSWERED, "2026-07-26T12:00:00+00:00")
        later[0]["answer"] = "补充回复"
        assert ce.write_qa(later) == 0
        stored = ce.load_qa()
        assert len(stored) == 2
        assert stored[stored["feed_id"] == "1756552"].iloc[0]["answer"] == "补充回复"

    def test_empty_write(self, store):
        assert ce.write_qa([]) == 0

    def test_columns_are_canonical(self, store):
        ce.write_qa(ce.parse_feed_items(_FEED_HTML, _TS))
        stored = pd.read_parquet(ce._qa_path())
        for col in ce._QA_COLUMNS:
            assert col in stored.columns, f"missing column: {col}"


# --------------------------------------------------------------------------- #
# cursor + universe
# --------------------------------------------------------------------------- #

class TestCursorAndUniverse:
    def test_wraparound(self):
        order = [f"{600000 + i}" for i in range(50)]
        shard, pos = ce.next_shard(order, 40, 40)
        assert len(shard) == 40 and pos == 30
        assert shard[:10] == order[40:] and shard[10:] == order[:30]

    def test_universe_reads_the_ss_half_only(self, tmp_path, monkeypatch):
        site = tmp_path / "site"
        (site / "factordata").mkdir(parents=True)
        (site / "factordata" / "china_setups.json").write_text(json.dumps({"buy": [
            {"ticker": "601963.SS"}, {"ticker": "600362.SS"}, {"ticker": "002595.SZ"},
        ]}))
        monkeypatch.setattr(config, "site_dir", lambda: site)
        assert ce.board_universe() == ["600362", "601963"]

    def test_absent_universe_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "site_dir", lambda: tmp_path / "nope")
        assert ce.board_universe() == []


# --------------------------------------------------------------------------- #
# uid-map policy
# --------------------------------------------------------------------------- #

def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class TestMapNeedsBuild:
    def test_no_map_at_all(self):
        assert ce.map_needs_build({"complete": False, "map": {}}, ["600000"]) is True

    def test_complete_map_covering_the_shard(self):
        state = {"complete": True, "map": {"600000": "65"},
                 "resolved_at": _iso_days_ago(400)}
        assert ce.map_needs_build(state, ["600000"]) is False

    def test_missing_name_but_fresh_map_is_a_coverage_null(self):
        state = {"complete": True, "map": {"600000": "65"},
                 "resolved_at": _iso_days_ago(3)}
        assert ce.map_needs_build(state, ["600000", "600004"]) is False

    def test_missing_name_and_stale_map_rebuilds(self):
        state = {"complete": True, "map": {"600000": "65"},
                 "resolved_at": _iso_days_ago(45)}
        assert ce.map_needs_build(state, ["600000", "600004"]) is True

    def test_missing_resolved_at_rebuilds(self):
        state = {"complete": True, "map": {"600000": "65"}, "resolved_at": ""}
        assert ce.map_needs_build(state, ["600004"]) is True


def _big_page(page: int, n: int = 300) -> dict[str, str]:
    """n synthetic (code, uid) pairs unique to ``page`` — the completeness gate
    (``_MIN_MAP_CODES``) needs realistically-sized directory pages."""
    base = 600000 + page * 1000
    return {str(base + i): str(page * 10000 + i) for i in range(n)}


class TestBuildUidMap:
    def test_full_build_stops_on_the_first_empty_page(self, store, monkeypatch):
        pages = {1: _big_page(1), 2: _big_page(2), 3: {}}
        monkeypatch.setattr(ce, "_fetch_company_page", lambda s, p: pages.get(p, {}))
        monkeypatch.setattr(ce, "_pace", lambda: None)
        state = ce.build_uid_map(None, ce._map_state(), ce._clock())
        assert state["complete"] is True
        assert len(state["map"]) == 600
        assert state["next_page"] == 1
        assert state["resolved_at"]

    def test_truncated_build_resumes_instead_of_claiming_completion(
            self, store, monkeypatch):
        pages = {1: _big_page(1), 2: _big_page(2), 3: {}}
        monkeypatch.setattr(ce, "_fetch_company_page", lambda s, p: pages.get(p, {}))
        monkeypatch.setattr(ce, "_pace", lambda: None)
        # In budget for page 1, over budget before page 2.
        ticks = iter([0.0] + [ce._BUDGET_S + 1.0] * 20)
        monkeypatch.setattr(ce, "_clock", lambda: next(ticks))
        state = ce.build_uid_map(None, ce._map_state(), 0.0)
        assert state["complete"] is False        # a partial map is NEVER 'complete'
        assert state["next_page"] == 2           # resumes exactly where it stopped
        assert len(state["map"]) == 300
        # Tomorrow: resume from page 2 and finish.
        monkeypatch.setattr(ce, "_clock", lambda: 0.0)
        state = ce.build_uid_map(None, ce._map_state(), 0.0)
        assert state["complete"] is True
        assert len(state["map"]) == 600

    def test_empty_first_page_never_stamps_complete(self, store, monkeypatch):
        # F4: a blank/shape-drifted page 1 on a from-scratch crawl is AMBIGUOUS —
        # complete must stay False and the same page must be retried tomorrow,
        # else an empty map freezes as final for the whole 30-day age window.
        monkeypatch.setattr(ce, "_fetch_company_page", lambda s, p: {})
        monkeypatch.setattr(ce, "_pace", lambda: None)
        state = ce.build_uid_map(None, ce._map_state(), ce._clock())
        assert state["complete"] is False
        assert state["map"] == {}
        assert state["next_page"] == 1
        assert not state["resolved_at"]

    def test_below_floor_map_never_stamps_complete(self, store, monkeypatch):
        # F4: a "finished" crawl holding fewer than _MIN_MAP_CODES codes is a parse
        # failure, not a small directory (the live venue is ~2,312 codes).
        pages = {1: {"600000": "65"}, 2: {}}
        monkeypatch.setattr(ce, "_fetch_company_page", lambda s, p: pages.get(p, {}))
        monkeypatch.setattr(ce, "_pace", lambda: None)
        state = ce.build_uid_map(None, ce._map_state(), ce._clock())
        assert state["complete"] is False
        assert not state["resolved_at"]

    def test_transport_failure_mid_crawl_persists_partial_progress(
            self, store, monkeypatch):
        # F5: pages fetched before the failure are KEPT and next_page lands on the
        # failed page — a flaky host still makes nightly progress.
        def flaky(session, page):
            if page >= 3:
                raise IOError("connection reset")
            return _big_page(page)

        monkeypatch.setattr(ce, "_fetch_company_page", flaky)
        monkeypatch.setattr(ce, "_pace", lambda: None)
        state = ce.build_uid_map(None, ce._map_state(), ce._clock())
        assert state["complete"] is False
        assert len(state["map"]) == 600           # pages 1-2 preserved
        assert state["next_page"] == 3            # resumes on the failed page
        on_disk = ce._load_json(ce._uid_map_path())
        assert len(on_disk["map"]) == 600         # persisted, not just returned

    def test_from_scratch_page_one_transport_failure_raises(self, store, monkeypatch):
        # F5: nothing fetched, nothing to save — the breaker should see this one.
        monkeypatch.setattr(ce, "_fetch_company_page",
                            lambda s, p: (_ for _ in ()).throw(IOError("refused")))
        monkeypatch.setattr(ce, "_pace", lambda: None)
        with pytest.raises(IOError):
            ce.build_uid_map(None, ce._map_state(), ce._clock())


# --------------------------------------------------------------------------- #
# refresh()
# --------------------------------------------------------------------------- #

def _wire(monkeypatch, order, *, feeds=None, clock=None):
    calls = {"feeds": [], "pages": []}
    monkeypatch.setattr(ce, "board_universe", lambda: order)
    monkeypatch.setattr(ce, "_pace", lambda: None)

    def _feed(session, uid, fetched_at, code=""):
        calls["feeds"].append(uid)
        rows = (feeds or (lambda u: ce.parse_feed_items(_FEED_HTML, fetched_at)))(uid)
        return rows, False    # (rows, drift_flag) — the F9/S1 contract

    def _page(session, page):
        calls["pages"].append(page)
        return {"600000": "65", "600004": "92"} if page == 1 else {}

    monkeypatch.setattr(ce, "_fetch_feed", _feed)
    monkeypatch.setattr(ce, "_fetch_company_page", _page)
    if clock is not None:
        monkeypatch.setattr(ce, "_clock", clock)
    return calls


def _seed_map(mapping: dict[str, str], age_days: float = 1.0) -> None:
    ce._save_json(ce._uid_map_path(), {
        "map": mapping, "complete": True, "next_page": 1,
        "resolved_at": _iso_days_ago(age_days),
    })


class TestRefresh:
    def test_empty_universe_is_a_zero_row_night(self, store, monkeypatch):
        monkeypatch.setattr(ce, "board_universe", lambda: [])
        s = ce.refresh()
        assert s["universe"] == 0 and s["shard"] == 0 and s["map_built"] == 0

    def test_map_build_night_skips_every_feed_pull(self, store, monkeypatch):
        calls = _wire(monkeypatch, ["600000", "600004"])
        s = ce.refresh()
        assert calls["feeds"] == []               # feeds deliberately not pulled
        assert calls["pages"] == [1, 2]
        assert s["map_built"] == 1 and s["shard"] == 0 and s["n_new"] == 0
        assert ce._uid_map_path().exists()

    def test_normal_night_pulls_the_shard(self, store, monkeypatch):
        _seed_map({"600000": "65", "600004": "92"})
        calls = _wire(monkeypatch, ["600000", "600004"])
        s = ce.refresh()
        assert calls["feeds"] == ["65", "92"]
        assert s["map_built"] == 0 and s["shard"] == 2
        assert s["n_new"] == 2                    # both uids return the same 2 feed ids
        assert ce.load_cursor(["600000", "600004"]) == 0   # full wrap

    def test_unmapped_name_is_a_coverage_null(self, store, monkeypatch):
        _seed_map({"600000": "65"})
        calls = _wire(monkeypatch, ["600000", "600004"])
        s = ce.refresh()
        assert calls["feeds"] == ["65"]
        assert s["n_failed"] == 0                 # a null is not a failure
        assert s["n_nulls"] == 1                  # …but it IS visible in the ledger (F6)

    def test_time_guard_persists_the_cursor_at_the_true_position(self, store, monkeypatch):
        order = [f"{600000 + i}" for i in range(50)]
        _seed_map({c: str(i + 1) for i, c in enumerate(order)})
        ticks = iter([0.0, 1.0, 2.0] + [ce._BUDGET_S + 1.0] * 60)
        calls = _wire(monkeypatch, order, clock=lambda: next(ticks))
        s = ce.refresh()
        assert len(calls["feeds"]) == 2
        assert s["shard"] == 40
        assert ce.load_cursor(order) == 2

    def test_empty_feed_day_is_a_success(self, store, monkeypatch):
        _seed_map({"600000": "65"})
        _wire(monkeypatch, ["600000"], feeds=lambda uid: [])
        s = ce.refresh()
        assert s["n_new"] == 0 and s["n_fetched"] == 0 and s["n_failed"] == 0

    def test_one_bad_name_never_sinks_the_night(self, store, monkeypatch):
        _seed_map({"600000": "65", "600004": "92"})

        def flaky(uid):
            if uid == "65":
                raise IOError("HTTP 502")
            return ce.parse_feed_items(_FEED_HTML, _TS)

        _wire(monkeypatch, ["600000", "600004"], feeds=flaky)
        s = ce.refresh()
        assert s["n_failed"] == 1 and s["n_fetched"] == 2

    def test_total_transport_failure_raises_for_the_breaker(self, store, monkeypatch):
        _seed_map({"600000": "65", "600004": "92"})

        def dead(uid):
            raise IOError("connection refused")

        _wire(monkeypatch, ["600000", "600004"], feeds=dead)
        with pytest.raises(RuntimeError, match="every attempted name failed"):
            ce.refresh()

    def test_map_build_transport_failure_raises(self, store, monkeypatch):
        _wire(monkeypatch, ["600000"])
        monkeypatch.setattr(ce, "_fetch_company_page",
                            lambda s, p: (_ for _ in ()).throw(IOError("refused")))
        with pytest.raises(RuntimeError, match="uid-map build failed"):
            ce.refresh()


# --------------------------------------------------------------------------- #
# empty-feed byte rule + adapter sentinel
# --------------------------------------------------------------------------- #

class TestFetchFeedByteRule:
    def test_short_body_is_an_empty_feed_not_a_failure(self, store, monkeypatch):
        class _R:
            text = "<html></html>"

        monkeypatch.setattr(ce, "_post", lambda *a, **k: _R())
        assert ce._fetch_feed(None, "65", _TS) == ([], False)

    def test_full_body_parses(self, store, monkeypatch):
        class _R:
            text = _FEED_HTML

        monkeypatch.setattr(ce, "_post", lambda *a, **k: _R())
        rows, drift = ce._fetch_feed(None, "65", _TS, code="600000")
        assert len(rows) == 2 and drift is False

    def test_long_body_parsing_to_nothing_is_the_drift_tripwire(self, store, monkeypatch):
        # S1: a body over the empty-page floor that parses to ZERO items means the
        # markup moved — flagged as drift (folded into n_nulls), never silent.
        class _R:
            text = "<html>" + "x" * (ce._EMPTY_FEED_BYTES + 100) + "</html>"

        monkeypatch.setattr(ce, "_post", lambda *a, **k: _R())
        assert ce._fetch_feed(None, "65", _TS, code="600000") == ([], True)


class TestAdapter:
    def test_sentinel_carries_map_built_and_a_tz_naive_index(self, store, monkeypatch):
        monkeypatch.setattr(ce, "refresh", lambda: {
            "n_new": 0, "n_fetched": 72, "n_failed": 0, "n_nulls": 0, "universe": 60,
            "shard": 0, "map_built": 1})
        sentinel = ce.ChinaEInteractionAdapter().fetch()["refresh"]
        assert list(sentinel.columns) == [
            "n_new", "n_fetched", "n_failed", "n_nulls", "universe", "shard", "map_built"]
        assert sentinel["map_built"].iloc[0] == 1.0
        for ts in sentinel.index:
            assert ts.tzinfo is None, "tz-aware index breaks store.upsert combine_first"

    def test_adapter_is_asia_lane(self):
        a = ce.ChinaEInteractionAdapter()
        assert a.group.startswith("china")
        assert a.stale_after_days == 4
