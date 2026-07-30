"""Tests for collectors/china_irm.py — 互动易 (SZSE) investor-Q&A collector.

Pure/offline surface only — NO network. Fixtures are the REAL responses captured
from irm.cninfo.com.cn on 2026-07-25 (trimmed to a few items, values byte-faithful),
so a vendor schema drift breaks a test instead of silently emptying the store.

Covers:
  - org-id resolution picks the entry whose stockCode matches (multi-candidate list)
  - Q&A row mapping from the real /company/question rows (ids, epoch→ISO, answered)
  - dedup keep-LAST on index_id (a later pull carrying the answer CORRECTS the row)
  - cursor rotation + wraparound
  - velocity row shape + the never-zero-fill rule
  - the wall-clock guard stops mid-shard and persists the cursor at the true position
  - empty universe / empty day handling

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) so no tracked
parquet is ever dirtied.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_irm as ci  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# REAL captured fixtures (irm.cninfo.com.cn, 2026-07-25)
# --------------------------------------------------------------------------- #

# POST /newircs/company/question?...&stockcode=000001&orgId=gssz0000001 — 3 of 3 rows.
_QUESTION_PAGE = json.loads("""
{
    "pageNo": 1, "pageSize": 3, "total": 13, "totalPage": 5, "count": true,
    "rows": [
        {
            "indexId": "2309409449541922816", "contentType": 1, "trade": ["金融业"],
            "mainContent": "平安银行通过多少年努力才能让业务结构中非息收入占比达到40%-50%？管理层有何中长期规划，同时持续提升ROE到15%以上有何考量和具体措施请在中报中详细解读一下",
            "boardType": ["012002"], "pubDate": 1783586644000, "stockCode": "000001",
            "companyShortName": "平安银行", "pubClient": "4", "attachedId": null,
            "attachedContent": null, "attachedAuthor": null, "attachedPubDate": null,
            "updateDate": 1783746928000, "qaStatus": "0"
        },
        {
            "indexId": "2305988121434378240", "contentType": 1, "trade": ["金融业"],
            "mainContent": "贵行2024年7月启动总行办公地点统筹管理以来，公开报道涉及零售业务及科技部门。请问：1）上述核心部门人员工作地点调整是否已基本完成？",
            "boardType": ["012002"], "pubDate": 1783188350000, "stockCode": "000001",
            "companyShortName": "平安银行", "pubClient": "2", "attachedId": null,
            "attachedContent": null, "attachedAuthor": null, "attachedPubDate": null,
            "updateDate": 1783477441000, "qaStatus": "0"
        },
        {
            "indexId": "2288573137116577792", "contentType": 11, "trade": ["金融业"],
            "mainContent": "贵行2024年7月宣布上海职场回迁深圳计划。请问截至目前，该计划涉及的人员变动情况如何？请董秘明确答复。",
            "boardType": ["012002"], "pubDate": 1781160979000, "stockCode": "000001",
            "companyShortName": "平安银行", "pubClient": "2",
            "attachedId": "2304985890815856640",
            "attachedContent": "您好。本行为加强管理，控制风险，强化协同，提升效率，近期在进行总行办公地点统筹管理，涉及到少量员工工作地点的变化调整。感谢您的关注。",
            "attachedAuthor": "平安银行", "attachedPubDate": null,
            "updateDate": 1783071693000, "qaStatus": "0"
        }
    ]
}
""")

# POST /newircs/index/search — page-1 envelope, 2 of 3 results kept.
_SEARCH_PAGE = json.loads("""
{
    "pageNo": 1, "pageSize": 3, "totalRecord": 94789, "totalPage": 31597, "count": true,
    "results": [
        {
            "esId": "11_2265575064801062912", "indexId": "2265575064801062912",
            "mainContent": "公司最近推出的联名款我感觉不错。以后会往IP联名这个方向走么。",
            "stockCode": "000858", "secid": "gssz0000858", "companyShortName": "五 粮 液",
            "pubDate": "1778483651000", "updateDate": "1785035942000", "qaStatus": 2
        },
        {
            "esId": "11_2266672395508936704", "indexId": "2266672395508936704",
            "mainContent": "请问公司二季度经营情况如何？", "stockCode": "000858",
            "secid": "gssz0000858", "companyShortName": "五 粮 液",
            "pubDate": "1778745285000", "updateDate": "1785035942000", "qaStatus": 2
        }
    ]
}
""")

# POST /newircs/index/queryKeyboardInfo — the fuzzy keyboard search: '000001' returns
# neighbours too, which is exactly why pick_org_id must match on stockCode.
_KEYBOARD_PAYLOAD = {
    "data": [
        {"stockCode": "000011", "shortName": "深物业A", "pinyin": "swya",
         "stockType": "A", "secid": "gssz0000011"},
        {"stockCode": "000001", "shortName": "平安银行", "pinyin": "payh",
         "stockType": "A", "secid": "gssz0000001"},
        {"stockCode": "000021", "shortName": "深科技", "pinyin": "skj",
         "stockType": "A", "secid": "gssz0000021"},
    ]
}

_TS = "2026-07-25T12:00:00+00:00"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Redirect every collector store/sidecar into tmp_path."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# org-id resolution
# --------------------------------------------------------------------------- #

class TestPickOrgId:
    def test_picks_the_exact_stock_code(self):
        assert ci.pick_org_id(_KEYBOARD_PAYLOAD, "000001") == "gssz0000001"

    def test_never_takes_the_fuzzy_first_hit(self):
        # The first entry is 000011; a first-hit implementation would pin the wrong tape.
        assert ci.pick_org_id(_KEYBOARD_PAYLOAD, "000001") != "gssz0000011"

    def test_no_match_is_a_coverage_null_not_a_crash(self):
        assert ci.pick_org_id(_KEYBOARD_PAYLOAD, "999999") == ""

    def test_empty_and_malformed_payloads(self):
        assert ci.pick_org_id({}, "000001") == ""
        assert ci.pick_org_id({"data": None}, "000001") == ""
        assert ci.pick_org_id({"data": ["not-a-dict"]}, "000001") == ""


# --------------------------------------------------------------------------- #
# Q&A row parsing (real fixture values)
# --------------------------------------------------------------------------- #

class TestParseQuestionRow:
    def test_unanswered_row(self):
        row = ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)
        assert row["index_id"] == "2309409449541922816"
        assert row["code"] == "000001"
        assert row["name"] == "平安银行"
        assert row["question"].startswith("平安银行通过多少年努力")
        assert row["answer"] == ""
        assert row["answered"] is False
        assert row["a_ts"] == ""
        assert row["q_ts"] == "2026-07-09T16:44:04+08:00"
        assert row["update_ts"] == "2026-07-11T13:15:28+08:00"
        assert row["industry"] == "金融业"
        assert row["source"] == "4"
        assert row["qa_status"] == "0"
        assert row["fetched_at"] == _TS

    def test_answered_row_keeps_the_company_reply(self):
        row = ci.parse_question_row(_QUESTION_PAGE["rows"][2], _TS)
        assert row["index_id"] == "2288573137116577792"
        assert row["answered"] is True
        assert row["answer"].startswith("您好。本行为加强管理")
        assert row["q_ts"] == "2026-06-11T14:56:19+08:00"
        # The vendor leaves attachedPubDate null even on answered rows — '' not a guess.
        assert row["a_ts"] == ""

    def test_qa_status_zero_survives_as_text(self):
        # `raw.get(...) or ''` would blank an integer 0; the vendor mixes "0" and 2.
        row = ci.parse_question_row({"indexId": "x", "qaStatus": 0, "pubClient": 0}, _TS)
        assert row["qa_status"] == "0"
        assert row["source"] == "0"

    def test_missing_fields_degrade_without_crashing(self):
        row = ci.parse_question_row({}, _TS)
        assert row["index_id"] == ""
        assert row["answered"] is False
        assert row["q_ts"] == ""
        assert row["industry"] == ""

    def test_whole_page_maps_to_three_rows(self):
        rows = [ci.parse_question_row(r, _TS) for r in _QUESTION_PAGE["rows"]]
        assert len(rows) == 3
        assert [r["answered"] for r in rows] == [False, False, True]


# --------------------------------------------------------------------------- #
# velocity
# --------------------------------------------------------------------------- #

class TestParseVelocity:
    def test_row_shape_from_the_real_envelope(self):
        row = ci.parse_velocity(_SEARCH_PAGE, _TS)
        assert row == {
            "date": "2026-07-25",
            "total_record": 94789,
            "max_pub_ts_page1": "2026-05-14T15:54:45+08:00",
            "asof": _TS,
        }

    def test_missing_total_record_is_a_gap_not_a_zero(self):
        # A fabricated 0 would read as "nobody asked anything today" — a different claim.
        assert ci.parse_velocity({"results": []}, _TS) is None
        assert ci.parse_velocity({"totalRecord": "not-a-number"}, _TS) is None

    def test_empty_results_still_records_the_total(self):
        row = ci.parse_velocity({"totalRecord": 7, "results": []}, _TS)
        assert row["total_record"] == 7
        assert row["max_pub_ts_page1"] == ""

    def test_write_velocity_skips_none(self, store):
        assert ci.write_velocity(None) == 0
        assert not ci._velocity_path().exists()

    def test_velocity_dedups_on_date_keep_last(self, store):
        ci.write_velocity({"date": "2026-07-25", "total_record": 10,
                           "max_pub_ts_page1": "", "asof": "a"})
        ci.write_velocity({"date": "2026-07-25", "total_record": 12,
                           "max_pub_ts_page1": "", "asof": "b"})
        df = ci.load_velocity()
        assert len(df) == 1
        assert int(df.iloc[0]["total_record"]) == 12


# --------------------------------------------------------------------------- #
# store: append-only + dedup keep-LAST
# --------------------------------------------------------------------------- #

class TestQaStore:
    def test_empty_write_is_zero(self, store):
        assert ci.write_qa([]) == 0

    def test_new_rows_land(self, store):
        rows = [ci.parse_question_row(r, _TS) for r in _QUESTION_PAGE["rows"]]
        assert ci.write_qa(rows) == 3
        assert len(ci.load_qa()) == 3

    def test_same_day_answer_update_corrects_keep_last(self, store):
        first = ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)
        ci.write_qa([first])
        # Same indexId re-fetched later, now carrying the company's answer.
        answered = dict(_QUESTION_PAGE["rows"][0])
        answered["attachedContent"] = "感谢关注，本行将在中报中详细披露。"
        second = ci.parse_question_row(answered, "2026-07-26T12:00:00+00:00")
        assert ci.write_qa([second]) == 0          # a correction is not a new row
        stored = ci.load_qa()
        assert len(stored) == 1                     # never duplicated
        assert stored.iloc[0]["answered"]           # and the answer landed
        assert stored.iloc[0]["answer"].startswith("感谢关注")

    def test_history_is_never_rewritten(self, store):
        ci.write_qa([ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)])
        ci.write_qa([ci.parse_question_row(_QUESTION_PAGE["rows"][1], _TS)])
        assert sorted(ci.load_qa()["index_id"]) == sorted(
            ["2309409449541922816", "2305988121434378240"])

    def test_columns_are_canonical(self, store):
        ci.write_qa([ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)])
        stored = pd.read_parquet(ci._qa_path())
        for col in ci._QA_COLUMNS:
            assert col in stored.columns, f"missing column: {col}"

    def test_load_returns_schema_when_absent(self, store):
        df = ci.load_qa()
        assert df.empty
        assert list(df.columns) == list(ci._QA_COLUMNS)

    def test_corrupt_store_aborts_the_append_untouched(self, store):
        # F1: a present-but-unreadable parquet must ABORT the append. The old
        # behaviour read it as an EMPTY store and replaced the whole accrued tape
        # with tonight's rows — silent destruction of the PIT history.
        ci.write_qa([ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)])
        corrupt = b"PAR1 this is not a parquet file"
        ci._qa_path().write_bytes(corrupt)
        rows = [ci.parse_question_row(r, _TS) for r in _QUESTION_PAGE["rows"]]
        assert ci.write_qa(rows) == 0
        assert ci._qa_path().read_bytes() == corrupt   # left for manual recovery

    def test_write_is_atomic_no_tmp_residue(self, store):
        # F1: the tmp+os.replace path leaves no sibling temp files behind.
        rows = [ci.parse_question_row(r, _TS) for r in _QUESTION_PAGE["rows"]]
        assert ci.write_qa(rows) == 3
        leftovers = [p for p in ci._qa_path().parent.iterdir()
                     if p.name != ci._qa_path().name and p.suffix != ".json"]
        assert leftovers == []

    def test_first_seen_survives_a_keep_last_correction(self, store):
        # F8: fetched_at advances on every correction; first_seen never moves.
        first = ci.parse_question_row(_QUESTION_PAGE["rows"][0], _TS)
        ci.write_qa([first])
        answered = dict(_QUESTION_PAGE["rows"][0])
        answered["attachedContent"] = "已回复。"
        later = "2026-08-30T12:00:00+00:00"
        ci.write_qa([ci.parse_question_row(answered, later)])
        stored = ci.load_qa()
        assert len(stored) == 1
        assert stored.iloc[0]["fetched_at"] == later      # last observed
        assert stored.iloc[0]["first_seen"] == _TS        # first observed, preserved

    def test_fixture_pages_are_newest_first(self):
        # S7: the single-page pageNum=1 pull relies on the venue serving newest-
        # first; an ASC flip upstream would silently freeze every name's tape at
        # its oldest 100 questions. Pin the assumption to the captured fixture.
        pub = [int(r["pubDate"]) for r in _QUESTION_PAGE["rows"]]
        assert pub == sorted(pub, reverse=True) and len(set(pub)) == len(pub)


# --------------------------------------------------------------------------- #
# cursor rotation
# --------------------------------------------------------------------------- #

class TestCursor:
    def test_plain_shard(self):
        order = [f"{i:06d}" for i in range(100)]
        shard, pos = ci.next_shard(order, 0, 40)
        assert shard == order[:40]
        assert pos == 40

    def test_wraparound(self):
        # 50 names, pos 40, size 40 → 10 tail names + 30 head names, next pos 30.
        order = [f"{i:06d}" for i in range(50)]
        shard, pos = ci.next_shard(order, 40, 40)
        assert len(shard) == 40
        assert shard[:10] == order[40:50]
        assert shard[10:] == order[:30]
        assert pos == 30

    def test_universe_smaller_than_the_shard(self):
        order = ["000001", "000002"]
        shard, pos = ci.next_shard(order, 1, 40)
        assert sorted(shard) == order
        assert pos == 1

    def test_empty_universe(self):
        assert ci.next_shard([], 7, 40) == ([], 0)

    def test_cursor_round_trip(self, store):
        order = [f"{i:06d}" for i in range(50)]
        ci.save_cursor(order, 30)
        assert ci.load_cursor(order) == 30
        state = json.loads(ci._cursor_path().read_text())
        assert state["order"] == order and state["updated"]

    def test_position_is_clamped_when_the_universe_shrinks(self, store):
        ci.save_cursor([f"{i:06d}" for i in range(50)], 47)
        assert ci.load_cursor([f"{i:06d}" for i in range(10)]) == 7

    def test_missing_cursor_starts_at_zero(self, store):
        assert ci.load_cursor(["000001"]) == 0


# --------------------------------------------------------------------------- #
# universe reader
# --------------------------------------------------------------------------- #

class TestBoardUniverse:
    def test_reads_the_sz_half_only(self, tmp_path, monkeypatch):
        site = tmp_path / "site"
        (site / "factordata").mkdir(parents=True)
        (site / "factordata" / "china_setups.json").write_text(json.dumps({
            "schema_version": "2.0.0",
            "buy": [{"ticker": "002595.SZ"}],
            "more_actionable": [{"ticker": "000034.SZ"}],
            "late_or_unfillable": [{"ticker": "300001.SZ"}],
            "forming": [{"ticker": "301002.SZ"}],
            # Compatibility watch is the union of depth lanes and must not be
            # treated as a separate v2 source.
            "watch": [{"ticker": "399999.SZ"}],
        }))
        monkeypatch.setattr(config, "site_dir", lambda: site)
        assert ci.board_universe() == ["000034", "002595", "300001", "301002"]

    def test_absent_file_is_an_empty_universe_not_a_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "site_dir", lambda: tmp_path / "nope")
        assert ci.board_universe() == []

    def test_corrupt_file_is_an_empty_universe_not_a_crash(self, tmp_path, monkeypatch):
        site = tmp_path / "site"
        (site / "factordata").mkdir(parents=True)
        (site / "factordata" / "china_setups.json").write_text("{not json")
        monkeypatch.setattr(config, "site_dir", lambda: site)
        assert ci.board_universe() == []


# --------------------------------------------------------------------------- #
# refresh(): time budget, cursor persistence, empty day
# --------------------------------------------------------------------------- #

def _wire(monkeypatch, order, *, clock=None, questions=None, keyboard=None,
          velocity=None):
    """Stub every network + sleep surface of refresh(); return the call log."""
    calls = {"questions": [], "keyboard": [], "velocity": 0}
    monkeypatch.setattr(ci, "board_universe", lambda: order)
    monkeypatch.setattr(ci, "_pace", lambda: None)

    def _keyboard(session, code):
        calls["keyboard"].append(code)
        return (keyboard or (lambda c: f"gssz{c}"))(code)

    def _questions(session, code, org_id):
        calls["questions"].append(code)
        return (questions or (lambda c: list(_QUESTION_PAGE["rows"])))(code)

    def _velocity(session):
        calls["velocity"] += 1
        return velocity if velocity is not None else _SEARCH_PAGE

    monkeypatch.setattr(ci, "_resolve_org_id", _keyboard)
    monkeypatch.setattr(ci, "_fetch_questions", _questions)
    monkeypatch.setattr(ci, "_fetch_velocity", _velocity)
    if clock is not None:
        monkeypatch.setattr(ci, "_clock", clock)
    return calls


class TestRefresh:
    def test_empty_universe_is_a_zero_row_night(self, store, monkeypatch):
        monkeypatch.setattr(ci, "board_universe", lambda: [])
        s = ci.refresh()
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                     "universe": 0, "shard": 0}

    def test_happy_path_shards_and_advances_the_cursor(self, store, monkeypatch):
        order = [f"{i:06d}" for i in range(50)]
        calls = _wire(monkeypatch, order)
        s = ci.refresh()
        assert calls["questions"] == order[:40]
        assert s["universe"] == 50 and s["shard"] == 40
        assert s["n_fetched"] == 40 * 3
        assert ci.load_cursor(order) == 40
        assert calls["velocity"] == 1
        assert len(ci.load_velocity()) == 1

    def test_org_ids_are_cached_across_nights(self, store, monkeypatch):
        order = ["000001", "000002"]
        calls = _wire(monkeypatch, order)
        ci.refresh()
        assert calls["keyboard"] == order          # resolved on night 1
        calls["keyboard"].clear()
        ci.refresh()
        assert calls["keyboard"] == []             # cache hit on night 2
        assert set(json.loads(ci._org_ids_path().read_text())) == {"000001", "000002"}

    def test_unresolved_name_is_a_logged_coverage_null(self, store, monkeypatch):
        order = ["000001", "000002"]
        _wire(monkeypatch, order, keyboard=lambda c: "" if c == "000002" else f"gssz{c}")
        s = ci.refresh()
        assert s["n_failed"] == 0                  # a null is not a failure
        assert s["n_fetched"] == 3                 # only 000001 produced rows
        assert s["n_nulls"] == 1                   # …and the null is LEDGERED (F6)
        assert ci.load_cursor(order) == 0          # both names consumed → full wrap

    def test_keyless_rows_are_dropped_at_the_parse_site(self, store, monkeypatch):
        # F7: an empty indexId is the dedup key — keyless rows would collapse into
        # ONE stored row. They are skipped, counted, and surfaced via n_nulls.
        keyless = dict(_QUESTION_PAGE["rows"][1])
        keyless["indexId"] = None
        keyless2 = dict(_QUESTION_PAGE["rows"][2])
        keyless2["indexId"] = ""
        _wire(monkeypatch, ["000001"],
              questions=lambda c: [_QUESTION_PAGE["rows"][0], keyless, keyless2])
        s = ci.refresh()
        assert s["n_fetched"] == 1                 # only the keyed row survived
        assert s["n_nulls"] == 2                   # both keyless rows counted
        assert len(ci.load_qa()) == 1

    def test_time_guard_stops_mid_shard_and_persists_the_true_position(
            self, store, monkeypatch):
        order = [f"{i:06d}" for i in range(50)]
        # Budget-exceeding clock after 3 names: t0, then 3 in-budget ticks, then over.
        ticks = iter([0.0, 1.0, 2.0, 3.0] + [ci._BUDGET_S + 1.0] * 50)
        calls = _wire(monkeypatch, order, clock=lambda: next(ticks))
        s = ci.refresh()
        assert calls["questions"] == order[:3]
        assert s["shard"] == 40                    # the shard was 40 names…
        assert s["n_fetched"] == 9                 # …but only 3 were pulled
        assert ci.load_cursor(order) == 3          # cursor persisted at the TRUE stop

    def test_guard_before_the_first_name_leaves_the_cursor_untouched(
            self, store, monkeypatch):
        order = [f"{i:06d}" for i in range(50)]
        ticks = iter([0.0] + [ci._BUDGET_S + 1.0] * 60)
        calls = _wire(monkeypatch, order, clock=lambda: next(ticks))
        ci.refresh()
        assert calls["questions"] == []
        assert ci.load_cursor(order) == 0

    def test_zero_row_day_is_a_success(self, store, monkeypatch):
        order = ["000001"]
        _wire(monkeypatch, order, questions=lambda c: [])
        s = ci.refresh()
        assert s["n_new"] == 0 and s["n_fetched"] == 0 and s["n_failed"] == 0

    def test_one_bad_name_never_sinks_the_night(self, store, monkeypatch):
        order = ["000001", "000002"]

        def flaky(code):
            if code == "000001":
                raise IOError("HTTP 502")
            return list(_QUESTION_PAGE["rows"])

        _wire(monkeypatch, order, questions=flaky)
        s = ci.refresh()
        assert s["n_failed"] == 1
        assert s["n_fetched"] == 3

    def test_total_transport_failure_raises_for_the_breaker(self, store, monkeypatch):
        order = ["000001", "000002"]

        def dead(code):
            raise IOError("connection refused")

        _wire(monkeypatch, order, questions=dead,
              velocity=None)
        monkeypatch.setattr(ci, "_fetch_velocity",
                            lambda s: (_ for _ in ()).throw(IOError("refused")))
        with pytest.raises(RuntimeError, match="every leg failed"):
            ci.refresh()

    def test_velocity_failure_alone_does_not_raise(self, store, monkeypatch):
        order = ["000001"]
        _wire(monkeypatch, order)
        monkeypatch.setattr(ci, "_fetch_velocity",
                            lambda s: (_ for _ in ()).throw(IOError("refused")))
        s = ci.refresh()
        assert s["n_fetched"] == 3
        assert ci.load_velocity().empty


# --------------------------------------------------------------------------- #
# adapter sentinel
# --------------------------------------------------------------------------- #

class TestAdapter:
    def test_sentinel_is_a_coverage_frame_with_a_tz_naive_index(self, store, monkeypatch):
        monkeypatch.setattr(ci, "refresh", lambda: {
            "n_new": 2, "n_fetched": 9, "n_failed": 1, "n_nulls": 1,
            "universe": 50, "shard": 40})
        frames = ci.ChinaIrmAdapter().fetch()
        sentinel = frames["refresh"]
        assert list(sentinel.columns) == [
            "n_new", "n_fetched", "n_failed", "n_nulls", "universe", "shard"]
        assert sentinel["n_failed"].iloc[0] == 1.0
        for ts in sentinel.index:
            assert ts.tzinfo is None, "tz-aware index breaks store.upsert combine_first"
        assert len(pd.to_datetime(sentinel.index)) == 1

    def test_adapter_is_asia_lane_and_context_tier(self):
        a = ci.ChinaIrmAdapter()
        assert a.group.startswith("china")
        assert a.stale_after_days == 4
