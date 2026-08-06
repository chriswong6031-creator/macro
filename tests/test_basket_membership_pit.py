"""PIT membership history for the CN basket suites (engine.basket_membership_pit).

CN Prophet masterplan §2.12 calls back-applied basket membership the weakest joint
of the relay program: the 12-month ignition study ran on ONE snapshot applied
backward, and the two real PIT snapshots differ by 7.7% of member-slots in 8 days.
So these pin the four properties that make the store worth trusting —

  1. KEEP-FIRST: a stamped snapshot_date is immutable. A re-run on the same day —
     even one whose membership.json has since changed — can never rewrite it.
  2. ASOF: the membership in force at date D is the newest snapshot ≤ D, with the
     source's own added/removed dates applied WITHIN it.
  3. THE BASIS FLAG: an answer that predates coverage is the current membership
     applied backward — the exact look-ahead this store exists to end — and it
     says so via ``pit=False``. A silent fallback would be worse than no store.
  4. THE POPULATION FLAG: the two real side-cars are DIFFERENT shapes (raw vendor
     concept dump vs seeded membership), so ``source_shape`` rides along and a
     cross-boundary read says what it is measuring.

Plus the lane gate: a render lane writes nothing (house law — nightly/asia is the
sole advancer of data/).
"""
from __future__ import annotations

import json

import pytest

from engine import basket_membership_pit as pit
from lib import config

THS = pit.SUITE_THS
CURATED = pit.SUITE_CURATED


def _doc(baskets: dict) -> dict:
    """A membership document in the shape both suites actually ship."""
    return {
        "version": 1, "seed_date": "2021-06-15", "curated": False,
        "baskets": {
            bid: {
                "name": bid.upper(), "name_zh": bid, "category": "theme",
                "members": members,
            }
            for bid, members in baskets.items()
        },
    }


def _m(ticker: str, added: str | None = "2021-06-15", removed: str | None = None) -> dict:
    return {"ticker": ticker, "added": added, "removed": removed,
            "name_zh": f"zh-{ticker}", "rationale": "test"}


def _write_membership(root, suite: str, doc: dict) -> None:
    p = root / suite / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point config.data_dir() at a scratch tree (the house fixture idiom)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. keep-first
# ---------------------------------------------------------------------------

def test_same_day_rerun_never_duplicates(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("300474.SZ"), _m("688981.SS")]}))
    first = pit.append_snapshot(THS, asof="2026-07-08")
    assert first["written"] and first["rows_added"] == 2

    again = pit.append_snapshot(THS, asof="2026-07-08")
    assert again["written"] is False
    assert again["reason"] == "date already stamped"
    df = pit.read_history(THS)
    assert len(df) == 2
    assert set(df["snapshot_date"]) == {"2026-07-08"}


def test_keep_first_wins_over_a_later_write_on_a_stamped_row(data_root):
    """The immutability that makes the store a RECORD rather than a cache.

    A stamped (snapshot_date, basket_id, ticker) row is never rewritten — a PIT
    store whose past can be edited answers yesterday's question with today's
    answer, which is the look-ahead bug in a costume.  The public writer refuses a
    stamped DATE outright (see the same-day test); this pins the merge rule
    underneath it, so the guarantee does not depend on that one guard.
    """
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("300474.SZ", removed=None)]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    # Force the append path directly (bypassing the date guard) with a MUTATED
    # version of the very same row.
    pit._append_rows(THS, pit._rows_from_doc(  # noqa: SLF001 — pinning the merge rule
        _doc({"ths_ai": [_m("300474.SZ", removed="2026-07-01")]}), "2026-07-08", THS))
    df = pit.read_history(THS)
    assert len(df) == 1, "the key must not admit a second row for the same slot"
    assert pit._text(df.iloc[0]["removed"]) is None  # noqa: SLF001 — the original survives
    assert pit.members_asof("ths_ai", "2026-07-08", suite=THS)["members"] == ["300474.SZ"]


def test_unchanged_membership_is_content_deduped(data_root):
    """A calendar day that adds nothing is not stamped — and the PIT read is
    unaffected, because 'newest snapshot ≤ D' already covers a quiet stretch."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("300474.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    later = pit.append_snapshot(THS, asof="2026-07-20")
    assert later["written"] is False
    assert "unchanged" in (later["reason"] or "")
    assert set(pit.read_history(THS)["snapshot_date"]) == {"2026-07-08"}
    # The quiet day still resolves — to the snapshot in force.
    got = pit.members_asof("ths_ai", "2026-07-20", suite=THS)
    assert got["pit"] is True and got["snapshot_date"] == "2026-07-08"


def test_a_reordered_membership_file_is_not_a_new_snapshot(data_root):
    """members_sha describes the MEMBERSHIP, not the file's byte layout."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ"), _m("B.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("B.SZ"), _m("A.SZ")]}))
    res = pit.append_snapshot(THS, asof="2026-07-09")
    assert res["written"] is False and "unchanged" in (res["reason"] or "")


def test_a_real_membership_change_is_stamped(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ"), _m("B.SZ", added="2026-07-09")]}))
    res = pit.append_snapshot(THS, asof="2026-07-09")
    assert res["written"] and res["rows_added"] == 2
    assert sorted(set(pit.read_history(THS)["snapshot_date"])) == ["2026-07-08", "2026-07-09"]


# ---------------------------------------------------------------------------
# 2. asof semantics
# ---------------------------------------------------------------------------

def test_asof_resolves_to_the_newest_snapshot_at_or_before_the_date(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-01")
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ"), _m("B.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")

    early = pit.members_asof("ths_ai", "2026-07-07", suite=THS)
    assert early["pit"] is True
    assert early["snapshot_date"] == "2026-07-01"
    assert early["members"] == ["A.SZ"], "the 07-08 addition must not leak backward"

    on_the_day = pit.members_asof("ths_ai", "2026-07-08", suite=THS)
    assert on_the_day["snapshot_date"] == "2026-07-08"
    assert on_the_day["members"] == ["A.SZ", "B.SZ"]

    later = pit.members_asof("ths_ai", "2026-09-01", suite=THS)
    assert later["snapshot_date"] == "2026-07-08" and later["pit"] is True


def test_added_and_removed_dates_apply_within_the_resolved_snapshot(data_root):
    """A read BETWEEN snapshots is correct, not merely nearest-neighbour — the
    curated suite carries real added/removed dates and they are the finer clock."""
    _write_membership(data_root, CURATED, _doc({"cn_semis": [
        _m("688981.SS", added="2021-06-15"),
        _m("300474.SZ", added="2026-07-20"),                    # joins later
        _m("000001.SZ", added="2021-06-15", removed="2026-07-05"),  # already gone
    ]}))
    pit.append_snapshot(CURATED, asof="2026-07-01")

    got = pit.members_asof("cn_semis", "2026-07-10", suite=CURATED)
    assert got["pit"] is True
    assert got["members"] == ["688981.SS"], got

    got = pit.members_asof("cn_semis", "2026-07-25", suite=CURATED)
    assert got["members"] == ["300474.SZ", "688981.SS"]


def test_both_suites_share_one_reader_contract(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    _write_membership(data_root, CURATED, _doc({"cn_semis": [_m("B.SS")]}))
    res = pit.append_all(asof="2026-07-08", lane="asia")
    assert res[THS]["snapshot"]["written"] and res[CURATED]["snapshot"]["written"]
    assert pit.members_asof("ths_ai", "2026-07-08", suite=THS)["members"] == ["A.SZ"]
    assert pit.members_asof("cn_semis", "2026-07-08", suite=CURATED)["members"] == ["B.SS"]
    assert pit.coverage(CURATED)["snapshots"] == 1


# ---------------------------------------------------------------------------
# 3. the basis flag (the load-bearing half)
# ---------------------------------------------------------------------------

def test_a_date_before_coverage_falls_back_and_says_so(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ"), _m("B.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")

    got = pit.members_asof("ths_ai", "2025-01-01", suite=THS)
    assert got["pit"] is False, "an uncovered date is NEVER reported as point-in-time"
    assert got["basis"] == "current_membership"
    assert got["snapshot_date"] is None
    assert got["members"] == ["A.SZ", "B.SZ"]           # useful, but flagged
    assert "predates coverage" in got["note"]
    assert "look-ahead" in got["note"]


def test_no_history_at_all_still_answers_and_still_flags(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    got = pit.members_asof("ths_ai", "2026-07-08", suite=THS)
    assert got["pit"] is False and got["members"] == ["A.SZ"]
    assert "no PIT history yet" in got["note"]


def test_unknown_basket_is_not_reported_as_an_authoritative_empty(data_root):
    """An empty member list with pit=True would read as 'this basket was empty
    that day'. A typo must not be able to say that."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    got = pit.members_asof("ths_nonexistent", "2026-07-08", suite=THS)
    assert got["members"] == []
    assert got["pit"] is False
    assert got["basis"] == "unknown_basket"


def test_a_basket_that_postdates_the_snapshot_is_pit_and_explains_itself(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")],
                                            "ths_new": [_m("C.SZ")]}))
    got = pit.members_asof("ths_new", "2026-07-08", suite=THS)
    assert got["pit"] is True and got["members"] == []
    assert "not present in the 2026-07-08 snapshot" in got["note"]


# ---------------------------------------------------------------------------
# 4. lane discipline + fail-soft
# ---------------------------------------------------------------------------

def test_a_render_lane_writes_nothing(data_root):
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    res = pit.append_snapshot(THS, asof="2026-07-08", lane="render")
    assert res["written"] is False and res["reason"] == "lane=render"
    assert not pit.history_path(THS).exists()


def test_backfill_seeds_from_the_dated_json_side_cars_and_is_idempotent(data_root):
    """The 2026-06-30 / 2026-07-08 pair already on disk is the program's only real
    PIT evidence; reading it in is what lets the store answer from night one."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ"), _m("B.SZ")]}))
    snaps = data_root / THS / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    (snaps / "2026-06-30.json").write_text(
        json.dumps(_doc({"ths_ai": [_m("A.SZ")]})), encoding="utf-8")
    (snaps / "2026-07-08.json").write_text(
        json.dumps(_doc({"ths_ai": [_m("A.SZ"), _m("B.SZ")]})), encoding="utf-8")

    res = pit.backfill_from_json_snapshots(THS)
    assert res["dates"] == ["2026-06-30", "2026-07-08"]
    assert res["rows_added"] == 3
    assert pit.members_asof("ths_ai", "2026-07-01", suite=THS)["members"] == ["A.SZ"]

    again = pit.backfill_from_json_snapshots(THS)
    assert again["rows_added"] == 0 and again["reason"] == "already covered"


def test_a_missing_membership_file_is_a_skip_not_a_crash(data_root):
    res = pit.append_snapshot(THS, asof="2026-07-08")
    assert res["written"] is False
    assert "missing" in (res["reason"] or "")
    assert pit.coverage(THS)["snapshots"] == 0


def test_parquet_nan_round_trip_does_not_fake_a_removal(data_root):
    """str(nan) is the truthy string 'nan'. If the null check came after the
    stringify, every never-removed member would read as removed."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ", removed=None)]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    row = pit.read_history(THS).iloc[0]
    assert pit._text(row["removed"]) is None      # noqa: SLF001 — the exact defect
    assert pit.members_asof("ths_ai", "2026-07-08", suite=THS)["members"] == ["A.SZ"]


# ---------------------------------------------------------------------------
# 5. two side-car shapes — the population boundary must be visible
# ---------------------------------------------------------------------------
#
# The real 2026-06-30 side-car is the RAW vendor concept dump (~9,069 slots,
# keyed by the Chinese board name); 2026-07-08 is a membership.json copy (~3,532
# slots, the seeded/capped subset). Reading only the second would drop half the
# program's PIT evidence; reading both without saying which is which invites a
# ~61% "drift" number that is mostly the seeding cap.


def _concept_dump(concepts: dict) -> dict:
    """The raw THS shape: {concept_name_zh: [{ticker, name}, ...]}."""
    return {c: [{"ticker": t, "name": f"zh-{t}"} for t in tickers]
            for c, tickers in concepts.items()}


def _ths_membership(mapping: dict) -> dict:
    """A membership doc whose baskets carry ths_concept (the join key)."""
    doc = _doc({bid: [_m(t) for t in tickers]
                for bid, (_concept, tickers) in mapping.items()})
    for bid, (concept, _tickers) in mapping.items():
        doc["baskets"][bid]["ths_concept"] = concept
    return doc


def test_the_raw_concept_dump_side_car_is_read_not_silently_dropped(data_root):
    _write_membership(data_root, THS, _ths_membership({"ths_ai": ("人工智能", ["A.SZ"])}))
    snaps = data_root / THS / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    (snaps / "2026-06-30.json").write_text(
        json.dumps(_concept_dump({"人工智能": ["A.SZ", "B.SZ", "C.SZ"],
                                  "未追踪概念": ["Z.SZ"]}), ensure_ascii=False),
        encoding="utf-8")
    (snaps / "2026-07-08.json").write_text(
        json.dumps(_ths_membership({"ths_ai": ("人工智能", ["A.SZ"])})), encoding="utf-8")

    res = pit.backfill_from_json_snapshots(THS)
    assert res["dates"] == ["2026-06-30", "2026-07-08"]
    assert res["unparsed"] == []
    df = pit.read_history(THS)
    assert set(df[df.snapshot_date == "2026-06-30"]["source_shape"]) == {"ths_concept_dump"}
    assert set(df[df.snapshot_date == "2026-07-08"]["source_shape"]) == {"membership"}
    # An untracked concept contributes nothing — we can only place a member in a
    # basket we actually carry.
    assert "Z.SZ" not in set(df["ticker"])


def test_reading_across_the_shape_boundary_says_so(data_root):
    """The caveat travels with the answer, exactly like the pit flag."""
    _write_membership(data_root, THS, _ths_membership({"ths_ai": ("人工智能", ["A.SZ"])}))
    snaps = data_root / THS / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    (snaps / "2026-06-30.json").write_text(
        json.dumps(_concept_dump({"人工智能": ["A.SZ", "B.SZ", "C.SZ"]}), ensure_ascii=False),
        encoding="utf-8")
    (snaps / "2026-07-08.json").write_text(
        json.dumps(_ths_membership({"ths_ai": ("人工智能", ["A.SZ"])})), encoding="utf-8")
    pit.backfill_from_json_snapshots(THS)

    old = pit.members_asof("ths_ai", "2026-07-01", suite=THS)
    assert old["pit"] is True and old["snapshot_date"] == "2026-06-30"
    assert old["members"] == ["A.SZ", "B.SZ", "C.SZ"]
    assert old["source_shape"] == "ths_concept_dump"
    assert "seeding cap" in old["note"]

    new = pit.members_asof("ths_ai", "2026-07-08", suite=THS)
    assert new["source_shape"] == "membership"
    assert new["note"] == "", "the store's own newest shape needs no caveat"


def test_an_unreadable_dated_side_car_is_reported_never_silently_skipped(data_root):
    """A hole in the record must be visible. A store that quietly covers less
    than it appears to is worse than one that covers nothing."""
    _write_membership(data_root, THS, _ths_membership({"ths_ai": ("人工智能", ["A.SZ"])}))
    snaps = data_root / THS / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    (snaps / "2026-06-30.json").write_text(json.dumps({"unexpected": "shape"}),
                                           encoding="utf-8")
    (snaps / "2026-07-08.json").write_text(
        json.dumps(_ths_membership({"ths_ai": ("人工智能", ["A.SZ"])})), encoding="utf-8")

    res = pit.backfill_from_json_snapshots(THS)
    assert res["unparsed"] == ["2026-06-30.json"]
    assert res["dates"] == ["2026-07-08"]
    assert set(pit.read_history(THS)["snapshot_date"]) == {"2026-07-08"}


def test_a_company_rename_is_not_a_membership_change(data_root):
    """members_sha excludes name_zh: the vendor renaming a company must not
    stamp a snapshot that has no membership news in it."""
    _write_membership(data_root, THS, _doc({"ths_ai": [_m("A.SZ")]}))
    pit.append_snapshot(THS, asof="2026-07-08")
    doc = _doc({"ths_ai": [_m("A.SZ")]})
    doc["baskets"]["ths_ai"]["members"][0]["name_zh"] = "改名了"
    _write_membership(data_root, THS, doc)
    res = pit.append_snapshot(THS, asof="2026-07-09")
    assert res["written"] is False and "unchanged" in (res["reason"] or "")
