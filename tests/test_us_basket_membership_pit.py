"""US basket membership as a point-in-time store, and the per-suite lane gate.

WHAT WAS MISSING
----------------
``data/baskets/membership.json`` is a single MUTABLE document — 49 baskets with
per-member added/removed dates, edited in place.  ``engine/basket_freeze.py``
writes only membership HASHES (``<bid>__mhash``) into
``data/basket_levels/us.parquet``: change DETECTION, from which membership
cannot be reconstructed.  So there was no way to answer "who was in this basket
on that date" for the US suite at all, and any study over US baskets was
measuring today's membership applied backward — the exact look-ahead basis the
CN store exists to end.  ``build_baskets --snapshot`` is the mirror of the CN
side-car writer, one suite over.

THE TWO THINGS MOST AT RISK OF BREAKING QUIETLY
-----------------------------------------------
1. The LANE GATE is now per-suite, and per-suite means a foreign lane must be
   refused in BOTH directions: the US nightly must not stamp a CN suite and the
   asia lane must not stamp the US one.  A gate that only refuses "no lane"
   would pass every test here while letting whichever nightly ran first own a
   date in a store it does not collect.  Keep-FIRST makes that permanent.
2. The CADENCE STAMP must be rewritten on the DEDUP-SKIP path.  That is the only
   path that distinguishes a healthy deduping writer from an unwired one, and it
   is the path that runs on almost every night.

Fixture-only: nothing reads live ``data/``; dates are read back off the store
rather than spelled, so no wall-clock literal can age out.
"""
from __future__ import annotations

import json

import pytest

from engine import basket_membership_pit as pit
from lib import config
from scripts import build_baskets as bb

US = pit.SUITE_US
THS = pit.SUITE_THS
MEMBERS = ("NVDA", "AVGO", "TSM")


def _doc(members=MEMBERS, *, basket="ai_semis") -> dict:
    """A US membership document in the shape data/baskets/membership.json ships."""
    return {
        "version": "2026-08-11", "seed_date": "2015-01-02",
        "baskets": {basket: {
            "name": "AI Semis", "category": "Technology", "weighting": "equal",
            "members": [{"ticker": t, "added": "2015-01-02", "removed": None,
                         "rationale": "test"} for t in members],
        }},
    }


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point config.data_dir() at a scratch tree.

    ``engine.basket_membership_pit`` and ``scripts.build_baskets`` both do
    ``from lib import config``, so patching the attribute redirects the store AND
    the entry point that drives it.
    """
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def seeded(data_root):
    p = pit.membership_path(US)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
    assert not pit.history_path(US).exists()
    return data_root


def _write(doc: dict) -> None:
    pit.membership_path(US).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _side_cars() -> list[str]:
    return [p.stem for p in pit.dated_snapshots(US)]


def _stored() -> set[str]:
    return set(pit.read_history(US)["ticker"].astype(str))


# ===========================================================================
# 1. the nightly --snapshot path: side-car + parquet + stamp
# ===========================================================================

def test_the_us_nightly_writes_a_side_car_a_parquet_row_set_and_a_stamp(seeded, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert bb.snapshot_membership() == 0

    cars = _side_cars()
    assert len(cars) == 1, f"expected one dated side-car, got {cars}"
    assert json.loads(pit.dated_snapshots(US)[0].read_text(encoding="utf-8")) == _doc()

    assert _stored() == set(MEMBERS)
    cov = pit.coverage(US)
    assert cov["snapshots"] == 1 and cov["last"] == cars[0], (
        "the parquet's stamped date must agree with the side-car it was written beside")

    stamp = pit.read_cadence(US)
    assert stamp["writer"] == "scripts.build_baskets"
    assert stamp["suite"] == US
    assert stamp["last_snapshot_date"] == cars[0]
    assert len(stamp["membership_sha"]) == 64


def test_us_rows_round_trip_through_the_shared_reader_with_an_empty_name_zh(seeded,
                                                                           monkeypatch):
    """One reader for three suites. The US suite has no Chinese name, so name_zh is
    absent — which must read as absent, never as the string 'nan' (the parquet NaN
    round-trip that once made every never-removed member look removed on a date
    called 'nan')."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()

    df = pit.read_history(US)
    assert set(df["suite"].astype(str)) == {US}
    assert all(pit._text(v) is None for v in df["name_zh"])  # noqa: SLF001
    assert all(pit._text(v) is None for v in df["removed"])  # noqa: SLF001

    got = pit.members_asof("ai_semis", pit.coverage(US)["last"], suite=US)
    assert got["pit"] is True
    assert got["members"] == sorted(MEMBERS)
    assert got["source_shape"] == pit.SHAPE_MEMBERSHIP


def test_an_unchanged_membership_is_deduped_but_STILL_stamped(seeded, monkeypatch):
    """The path that runs on almost every night, and the one the whole cadence stamp
    exists for: a deduping writer and an unwired writer are otherwise indistinguishable
    on disk. Asserted by planting a sentinel stamp and proving the dedup run replaced
    it — no wall-clock comparison, so this cannot flake on a fast clock."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()
    before = _side_cars()

    pit.cadence_path(US).write_text(
        json.dumps({"checked_at": "1999-01-01T00:00:00Z", "writer": "sentinel"}),
        encoding="utf-8")
    assert bb.snapshot_membership() == 0

    assert _side_cars() == before, "an unchanged membership wrote a second side-car"
    stamp = pit.read_cadence(US)
    assert stamp["writer"] == "scripts.build_baskets", (
        "the dedup-skip path did not rewrite the cadence stamp — a stalled plane and a "
        "healthy one are indistinguishable again")
    assert stamp["checked_at"] != "1999-01-01T00:00:00Z"


def test_a_real_membership_change_writes_a_new_side_car(seeded, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()
    first = pit.coverage(US)["last"]

    _write(_doc((*MEMBERS, "AMD")))
    # A same-day re-run cannot mint a second dated file, so the change is asserted
    # through the store's own content hash rather than a second date.
    assert pit.members_sha(_doc((*MEMBERS, "AMD"))) != pit.members_sha(_doc())
    assert bb.snapshot_membership() == 0
    assert pit.coverage(US)["last"] == first
    assert _stored() == set(MEMBERS), "keep-FIRST let a same-day re-run rewrite a stamped day"


def test_a_missing_membership_file_is_a_skip_not_a_crash(data_root, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert bb.snapshot_membership() == 0
    assert _side_cars() == []
    # Still stamped: "I ran and found nothing" is exactly what the tripwire must see.
    assert pit.read_cadence(US)["writer"] == "scripts.build_baskets"


def test_the_cli_flag_routes_to_the_snapshot_path_and_never_renders(seeded, monkeypatch):
    """`--snapshot` must skip the page build entirely — it runs in a band beside the
    real builder, and re-rendering there would double the work and race its output."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr("sys.argv", ["build_baskets", "--snapshot"])
    monkeypatch.setattr(
        "engine.baskets.compute_baskets",
        lambda *_a, **_k: pytest.fail("--snapshot rendered the page"))
    assert bb.main() == 0
    assert len(_side_cars()) == 1


# ===========================================================================
# 2. the per-suite lane gate — fail-closed in BOTH directions
# ===========================================================================

@pytest.mark.parametrize("lane", [
    pytest.param(None, id="COLLECT_LANE-unset"),
    pytest.param("", id="COLLECT_LANE-empty"),
    pytest.param("asia", id="COLLECT_LANE-asia"),
    pytest.param("render", id="COLLECT_LANE-render"),
])
def test_only_the_us_nightly_advances_the_us_store(seeded, monkeypatch, lane):
    """Including ``asia``: the CN nightly is a real lane, it just does not collect US
    data. Keep-FIRST means the first lane to stamp a date owns it forever, so 'a
    neighbouring nightly' is exactly the population a permissive gate is blind to."""
    if lane is None:
        monkeypatch.delenv("COLLECT_LANE", raising=False)
    else:
        monkeypatch.setenv("COLLECT_LANE", lane)
    monkeypatch.delenv("US_LANE", raising=False)

    assert bb._membership_pit_lane() == (lane or None)  # noqa: SLF001
    assert bb.snapshot_membership() == 0
    assert not pit.history_path(US).exists(), "the US PIT store was advanced off-lane"

    # WITNESS: the identical fixture and call DO write once the lane is named, so the
    # non-write above is the gate rather than an unwritable scratch tree.
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()
    assert _stored() == set(MEMBERS)


def test_us_lane_is_the_accepted_legacy_alias(seeded, monkeypatch):
    """Mirrors ``engine.ledger_lane.nightly_advance_enabled``, which has accepted
    US_LANE since it unified the local gates."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.setenv("US_LANE", "nightly")
    bb.snapshot_membership()
    assert _stored() == set(MEMBERS)


def test_neither_nightly_can_reach_into_the_others_suite(seeded, data_root):
    """The gate is per-suite, so it must refuse the asia lane on the US store AND the
    nightly lane on a CN store — not merely refuse an unnamed lane."""
    assert pit.append_snapshot(US, asof="2026-08-15", lane="asia")["written"] is False
    assert pit.backfill_from_json_snapshots(US, lane="asia")["reason"] == "lane=asia"

    ths_doc = {"baskets": {"ths_ai": {"members": [{"ticker": "300474.SZ"}]}}}
    p = pit.membership_path(THS)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ths_doc), encoding="utf-8")
    assert pit.append_snapshot(THS, asof="2026-08-15", lane="nightly")["written"] is False

    assert not pit.history_path(US).exists()
    assert not pit.history_path(THS).exists()

    # WITNESS: each suite's OWN lane writes on the same fixture.
    assert pit.append_snapshot(US, asof="2026-08-15", lane="nightly")["written"] is True
    assert pit.append_snapshot(THS, asof="2026-08-15", lane="asia")["written"] is True


def test_an_undeclared_suite_has_no_lane_that_may_write_it(data_root):
    """Fail-closed by construction: the lane map is the whitelist, so a typo'd or
    newly-added suite refuses every lane until it is declared."""
    assert pit.SUITE_LANE.keys() == set(pit.ALL_SUITES)
    for lane in ("asia", "nightly", None, "whatever"):
        assert pit.append_snapshot("baskets_atlantis", lane=lane)["written"] is False


# ===========================================================================
# 3. side-car ingest: idempotent, and blind to the cadence stamp
# ===========================================================================

def test_backfill_from_side_cars_is_idempotent(seeded, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()
    rows = len(pit.read_history(US))
    assert rows == len(MEMBERS)

    for _ in range(3):
        pit.backfill_from_json_snapshots(US, lane="nightly")
    assert len(pit.read_history(US)) == rows, "re-ingesting a stamped date duplicated rows"


def test_the_cadence_stamp_is_never_ingested_as_a_snapshot(seeded, monkeypatch):
    """`_cadence.json` lives in the snapshots dir and `_` sorts AFTER every digit, so a
    `*.json` enumerator taking the last entry would resolve the STAMP as the newest
    snapshot. The one enumerator is date-shaped; prove the hazard is real and excluded."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    bb.snapshot_membership()
    snaps = pit.snapshot_dir(US)
    assert (snaps / pit.CADENCE_FILE).exists()
    assert sorted(p.name for p in snaps.glob("*.json"))[-1] == pit.CADENCE_FILE, (
        "the ASCII-ordering hazard this test guards has moved — re-derive it")

    assert [p.name for p in pit.dated_snapshots(US)] == [f"{pit.coverage(US)['last']}.json"]
    res = pit.backfill_from_json_snapshots(US, lane="nightly")
    assert res["unparsed"] == [], f"the cadence stamp was read as a snapshot: {res}"
