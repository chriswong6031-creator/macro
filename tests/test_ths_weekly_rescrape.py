"""The weekly 同花顺 re-scrape: receipts, complete-or-fail promotion, PIT ingest.

WHAT WAS BROKEN (and what these pins protect)
---------------------------------------------
``collectors/china_ths_concepts.py`` and ``scripts/seed_china_ths_baskets.py``
appeared in ZERO workflows, so ``data/baskets_china_ths/membership.json`` froze
on 2026-06-30 and the PIT store held two snapshots eight days apart — while
``build_baskets_china_ths --snapshot`` ran green ~35 nights in a row, dedup-
skipping every one because its input never moved.  ``scripts/scrape_ths_weekly.py``
is the missing producer.

The load-bearing rule it adds is COMPLETE-OR-FAIL at the RUN level.  The
collector already refuses to record a PARTIAL member list for one board; the
identical hazard one level up had nothing enforcing it, and it is worse, because
``seed_china_ths_baskets`` enumerates its auto-imported taxonomy from the NEWEST
side-car's keys alone (line 373) — so a side-car missing 173 of 373 boards does
not merely under-report those boards, it deletes their baskets.  Hence: scrape
into staging, promote only when every board resolved.

The last class here is the reason the SEED step is deliberately NOT wired in this
wave: two producers write two different document shapes into one directory, and
which of them wrote last silently decides whether a re-seed preserves the
taxonomy or empties it.  That is pinned rather than fixed — see
``TestSeederShapeCollision``.

Fixture-only: nothing here reads live ``data/`` and nothing pins a live count.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from collectors import china_ths_concepts as ths
from engine import basket_membership_pit as pit
from lib import config
from scripts import scrape_ths_weekly as weekly

CONTRACT = (Path(__file__).resolve().parents[1] / "contracts" / "baskets_china_ths"
            / "scrape_receipt.v1.schema.json")

AS_OF = "2026-08-15"
BOARDS = ("人工智能", "人形机器人", "白酒概念")


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point config.data_dir() at a scratch tree (the house fixture idiom).

    ``scripts.scrape_ths_weekly`` and ``engine.basket_membership_pit`` both do
    ``from lib import config``, so patching the attribute on the module object
    redirects both the driver and the store it feeds.
    """
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


def _members(board: str) -> list[dict]:
    return [{"ticker": f"60{i}{len(board)}00.SS", "name": f"{board}-{i}"} for i in range(3)]


def _install_collector(monkeypatch, *, resolvable, boards=BOARDS):
    """Stub the network collector with one that honours its real contract.

    Faithful to the two properties the driver depends on: progress is persisted
    into ``snap_dir`` after every board (so a killed pass costs only its own
    remaining work), and ``resume=True`` merges what is already staged.
    ``resolvable`` may be a set (static) or a callable taking the pass number, so
    a test can make the taxonomy fill in across cool-down passes.
    """
    calls: list[list[str]] = []

    def fake_snapshot(names, as_of=None, resume=True, snap_dir=None):
        calls.append(list(names))
        p = Path(snap_dir) / f"{as_of}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        out: dict = {}
        if resume and p.exists():
            out = json.loads(p.read_text(encoding="utf-8"))
        ok = resolvable(len(calls)) if callable(resolvable) else resolvable
        for n in names:
            if n in ok:
                out[n] = _members(n)
        p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out

    monkeypatch.setattr(ths, "concept_code_map", lambda force=False: {b: str(i) for i, b in enumerate(boards)})
    monkeypatch.setattr(ths, "snapshot", fake_snapshot)
    return calls


def _run(**kw):
    kw.setdefault("as_of", AS_OF)
    kw.setdefault("cooldown_seconds", 0.0)
    kw.setdefault("budget_minutes", 60.0)
    return weekly.run(**kw)


def _receipt(as_of: str = AS_OF) -> dict:
    return json.loads(weekly.receipt_path(as_of).read_text(encoding="utf-8"))


def _validate(receipt: dict) -> None:
    """The receipt must satisfy its committed contract, not merely 'look right'."""
    import jsonschema

    jsonschema.validate(receipt, json.loads(CONTRACT.read_text(encoding="utf-8")))


# ===========================================================================
# 1. complete-or-fail: what a partial attempt may and may not leave behind
# ===========================================================================

def test_a_complete_scrape_promotes_a_side_car_and_a_valid_receipt(data_root, monkeypatch):
    _install_collector(monkeypatch, resolvable=set(BOARDS))
    assert _run() == 0

    promoted = weekly.snapshot_path(AS_OF)
    assert promoted.exists(), "a complete scrape must promote its dated side-car"
    assert not weekly.staging_path(AS_OF).exists(), "staging must be consumed by the promotion"
    assert set(json.loads(promoted.read_text(encoding="utf-8"))) == set(BOARDS)

    r = _receipt()
    _validate(r)
    assert r["complete"] is True
    assert r["truncated"] == []
    assert r["concepts_fetched"] == r["concepts_attempted"] == len(BOARDS)
    assert r["members_total"] == 3 * len(BOARDS)
    assert r["promoted"] is True


def test_a_partial_scrape_leaves_a_receipt_and_no_side_car(data_root, monkeypatch):
    """THE law (masterplan G0.4). A truncated dump in snapshots/ is not 'less data' —
    the seeder reads the newest side-car as the authoritative board list, so the boards
    it never reached read as boards that no longer exist."""
    _install_collector(monkeypatch, resolvable={BOARDS[0]})
    assert _run(max_passes=1) == 0

    assert not weekly.snapshot_path(AS_OF).exists(), (
        "a partial scrape promoted a side-car — the seeder would read the 2 unscraped "
        "boards as vanished and delete their baskets")
    staged = weekly.staging_path(AS_OF)
    assert staged.exists(), "partial progress must survive for the next attempt on this date"
    assert set(json.loads(staged.read_text(encoding="utf-8"))) == {BOARDS[0]}

    r = _receipt()
    _validate(r)
    assert r["complete"] is False
    assert r["truncated"] == sorted(BOARDS[1:]), "the receipt must NAME what it could not page"
    assert r["promoted"] is False
    assert r["concepts_fetched"] == 1


def test_a_partial_attempt_can_never_report_itself_promoted(data_root, monkeypatch):
    """The receipt builder forces promoted=False on an incomplete run even when the
    caller says otherwise, so the artifact cannot claim a side-car that does not exist."""
    _install_collector(monkeypatch, resolvable=set())
    r = weekly.build_receipt(
        as_of=AS_OF, started_at="2026-08-15T00:00:00Z", finished_at="2026-08-15T00:01:00Z",
        names=list(BOARDS), result={BOARDS[0]: _members(BOARDS[0])}, passes=1,
        budget_minutes=1.0, budget_exhausted=False, promoted=True, pit_rows_added=0)
    _validate(r)
    assert r["complete"] is False and r["promoted"] is False


def test_a_resumed_attempt_completes_what_the_first_pass_left(data_root, monkeypatch):
    """Two runs on the same date: the second resumes staging rather than restarting,
    and promotion happens only once the taxonomy is whole."""
    _install_collector(monkeypatch, resolvable={BOARDS[0]})
    _run(max_passes=1)
    assert not weekly.snapshot_path(AS_OF).exists()

    calls = _install_collector(monkeypatch, resolvable=set(BOARDS))
    _run(max_passes=1)
    assert calls[0] == list(BOARDS[1:]), (
        "the resumed attempt re-scraped an already-resolved board — staging was ignored")
    assert weekly.snapshot_path(AS_OF).exists()
    assert _receipt()["complete"] is True


def test_cool_down_passes_fill_the_taxonomy_in(data_root, monkeypatch):
    """THS throttles bursts, so the collector stops early and documents 'run it a few
    times across cool-downs'. The driver automates exactly that, inside one attempt."""
    calls = _install_collector(monkeypatch, resolvable=lambda n: set(BOARDS[:n]))
    _run(max_passes=4)
    assert len(calls) == 3, f"expected one pass per unresolved board, got {len(calls)}"
    assert _receipt()["passes"] == 3
    assert weekly.snapshot_path(AS_OF).exists()


def test_an_already_promoted_date_is_a_no_op(data_root, monkeypatch):
    calls = _install_collector(monkeypatch, resolvable=set(BOARDS))
    _run()
    before = weekly.snapshot_path(AS_OF).read_bytes()
    calls.clear()
    assert _run() == 0
    assert calls == [], "a promoted date must not be re-scraped"
    assert weekly.snapshot_path(AS_OF).read_bytes() == before


def test_an_empty_taxonomy_is_not_vacuously_complete(data_root, monkeypatch):
    """A dead concept map (akshare down AND no disk cache) must not promote an empty
    side-car, which would read as EVERY board vanishing at once."""
    monkeypatch.setattr(ths, "concept_code_map", lambda force=False: {})
    assert _run() == 0
    assert not weekly.snapshot_path(AS_OF).exists()
    r = _receipt()
    _validate(r)
    assert r["complete"] is False and r["concepts_attempted"] == 0


# ===========================================================================
# 2. the promoted side-car reaches the queryable PIT parquet — idempotently
# ===========================================================================

def _membership_doc() -> dict:
    """A live membership.json whose ths_concept map is what lets the raw dump resolve."""
    return {"version": "2026-06-30", "baskets": {
        f"thsc{i}": {"name": b, "name_zh": b, "ths_concept": b, "members": []}
        for i, b in enumerate(BOARDS)}}


def test_a_promoted_side_car_reaches_the_parquet_and_re_running_adds_nothing(
        data_root, monkeypatch):
    """Gate 4. The store is append-only and keep-FIRST per
    (snapshot_date, basket_id, ticker), so the ingest may run in the scrape job AND
    again in tonight's --snapshot step without duplicating a row."""
    (data_root / pit.SUITE_THS).mkdir(parents=True, exist_ok=True)
    pit.membership_path(pit.SUITE_THS).write_text(
        json.dumps(_membership_doc(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CN_LANE", "asia")
    _install_collector(monkeypatch, resolvable=set(BOARDS))
    _run()

    df = pit.read_history(pit.SUITE_THS)
    assert not df.empty
    assert set(df["snapshot_date"].astype(str)) == {AS_OF}
    assert set(df["source_shape"].astype(str)) == {pit.SHAPE_CONCEPT_DUMP}, (
        "a raw vendor dump must be labelled as one — its concept→basket map is today's")
    first = len(df)

    for _ in range(2):
        pit.backfill_from_json_snapshots(pit.SUITE_THS, lane="asia")
    assert len(pit.read_history(pit.SUITE_THS)) == first, "re-ingest duplicated rows"
    assert _receipt()["pit_rows_added"] == first


def test_the_scrape_lane_gate_is_fail_closed(data_root, monkeypatch):
    """A hand-run promotes the side-car (evidence is never withheld) but appends
    NOTHING to the parquet: keep-FIRST means whoever stamps a date owns it forever."""
    (data_root / pit.SUITE_THS).mkdir(parents=True, exist_ok=True)
    pit.membership_path(pit.SUITE_THS).write_text(
        json.dumps(_membership_doc(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.delenv("CN_LANE", raising=False)
    _install_collector(monkeypatch, resolvable=set(BOARDS))
    _run()

    assert weekly.snapshot_path(AS_OF).exists()
    assert not pit.history_path(pit.SUITE_THS).exists(), (
        "the PIT store was advanced outside the asia lane")
    assert _receipt()["pit_rows_added"] == 0

    # WITNESS: the identical fixture DOES append once the lane is named.
    monkeypatch.setenv("CN_LANE", "asia")
    assert pit.backfill_from_json_snapshots(pit.SUITE_THS, lane="asia")["rows_added"] > 0


# ===========================================================================
# 3. WHY THE SEED STEP IS NOT WIRED — the shape collision, pinned not fixed
# ===========================================================================

class TestSeederShapeCollision:
    """Two producers write two document SHAPES into one directory, and the seeder
    treats whichever wrote last as the authoritative current board list.

      * ``scripts/scrape_ths_weekly.py`` promotes the RAW vendor dump
        ``{concept_name: [{ticker, name}]}``.
      * ``scripts/build_baskets_china_ths.py --snapshot`` (line 79, ``dest.write_bytes(raw)``)
        byte-copies ``membership.json`` — an entirely different shape, keyed by
        basket_id under a top-level ``baskets`` key — into the SAME directory,
        every night that membership changes.

    ``seed_china_ths_baskets._all_snapshots`` (line 247) reads every file in that
    directory as a raw dump, and the auto-import loop (line 373) enumerates
    ``snaps[-1][1].keys()``.  So on any run where the newest side-car is the
    membership-doc copy, that enumeration yields ``version``/``seed_date``/``baskets``
    — none of which is a THS concept — ``n_auto`` is 0, and EVERY auto-imported
    ``thsc*`` basket disappears from membership.json.

    That is an identity instability under the wave's own gate (c): vanished
    concepts are not handled without collateral loss.  So W1a ships the scrape,
    the receipts and the tripwire — the raw PIT side-cars accrue and the
    motivating defect is fixed — and leaves the seed unwired.  These tests pin the
    instability so the follow-up has a failing-shaped witness to work against.
    """

    @staticmethod
    def _seed():
        from scripts import seed_china_ths_baskets as seed
        return seed

    @staticmethod
    def _snap_dir(root: Path) -> Path:
        d = root / pit.SUITE_THS / "snapshots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_the_membership_doc_side_car_empties_the_auto_import_enumeration(self, data_root):
        seed = self._seed()
        d = self._snap_dir(data_root)
        (d / "2026-06-30.json").write_text(
            json.dumps({b: _members(b) for b in BOARDS}, ensure_ascii=False), encoding="utf-8")
        (d / "2026-07-08.json").write_text(
            json.dumps(_membership_doc(), ensure_ascii=False), encoding="utf-8")

        snaps = seed._all_snapshots()  # noqa: SLF001 — the enumeration under test
        assert [date for date, _doc in snaps] == ["2026-06-30", "2026-07-08"]
        newest = snaps[-1][1]
        assert set(newest) & set(BOARDS) == set(), (
            "the membership-doc side-car has stopped being read as a membership doc — "
            "if the seeder now understands both shapes, re-run the wiring decision")
        assert "baskets" in newest, "the newest side-car is the membership-doc shape"

        # WITNESS: with a RAW dump newest, the same enumeration yields the concepts.
        (d / "2026-08-15.json").write_text(
            json.dumps({b: _members(b) for b in BOARDS}, ensure_ascii=False), encoding="utf-8")
        assert set(seed._all_snapshots()[-1][1]) == set(BOARDS)  # noqa: SLF001

    def test_a_membership_doc_newest_freezes_every_curated_theme(self, data_root):
        """The curated half degrades differently but no less wrongly: with the newest
        side-car unreadable as a board list, `latest_trustworthy` is False, so NO
        removal is ever honoured and the theme silently stops tracking THS at all."""
        seed = self._seed()
        d = self._snap_dir(data_root)
        (d / "2026-06-30.json").write_text(
            json.dumps({BOARDS[0]: _members(BOARDS[0])}, ensure_ascii=False), encoding="utf-8")
        (d / "2026-07-08.json").write_text(
            json.dumps(_membership_doc(), ensure_ascii=False), encoding="utf-8")

        snaps = seed._all_snapshots()  # noqa: SLF001
        universe = {m["ticker"] for m in _members(BOARDS[0])}
        members, _missing = seed._pit_members(  # noqa: SLF001
            BOARDS[0], snaps, universe, lambda _t, fallback: fallback)
        assert members, "the curated theme lost its members entirely"
        assert all(m["removed"] is None for m in members), (
            "a removal was fabricated from a side-car that is not a board list")

    def test_the_cadence_stamp_is_not_read_as_a_snapshot(self, data_root):
        """`_cadence.json` shares the snapshots dir, and `_` sorts AFTER every digit in
        ASCII — so under the old `*.json` glob it would have resolved as the NEWEST
        snapshot and become the authoritative board list. Date-shaped globs only."""
        seed = self._seed()
        d = self._snap_dir(data_root)
        (d / "2026-06-30.json").write_text(
            json.dumps({b: _members(b) for b in BOARDS}, ensure_ascii=False), encoding="utf-8")
        (d / pit.CADENCE_FILE).write_text(
            json.dumps({"checked_at": "2026-08-15T00:00:00Z"}), encoding="utf-8")

        assert sorted(p.name for p in d.glob("*.json"))[-1] == pit.CADENCE_FILE, (
            "the ASCII-ordering hazard this test guards has moved — re-derive it")
        snaps = seed._all_snapshots()  # noqa: SLF001
        assert [date for date, _doc in snaps] == ["2026-06-30"]
        assert set(snaps[-1][1]) == set(BOARDS)
        assert [p.name for p in pit.dated_snapshots(pit.SUITE_THS)] == ["2026-06-30.json"]
