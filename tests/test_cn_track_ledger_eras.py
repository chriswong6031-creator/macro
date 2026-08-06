"""CN track-record ERA CONTINUITY (Prophet Learning Loop §3 / gate G5).

The CN board's definition changed on 2026-07-30. `emit_cn_track_ledger` filtered
episodes to the live `board_definition`, so a record built over ~1,082 graded board rows
collapsed to the 15 rows carrying the new stamp and the desk's visible history went to
zero — the last pre-change publish showed 348 matured episodes at 66.7%, the next showed
n=0 `accruing`.

The fix these tests pin has two halves, and BOTH have to hold:

  1. the prior era is graded again and published as `prior_record` — same scorer, same
     horizon, same exit rule, so the two records are comparable;
  2. no row is ever pooled across the boundary. The two boards selected their names by
     different rules, so a union measures neither
     (memory `us-board-definition-change-2026-06-25`).

Section 3 pins the OTHER half of "no row is ever lost": the split originally
recognised exactly two stamps, so a row carrying any third value matched neither mask
and vanished from the artifact silently. Unknown stamps now get their own labelled
`extra_records` block plus a line-start ``::warning``.

The era-split arithmetic runs against the REAL committed parquet — no price data
needed, so it cannot be skipped into vacuity — while the emit-shape assertions run on
synthetic prices so they are deterministic and fast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_china_library as bcl  # noqa: E402
from engine import china_board_rank  # noqa: E402 — the LIVE stamp's producer
from engine import china_standout_track as cst  # noqa: E402 — the watch cohorts' producer

BOARD_PARQUET = ROOT / "data" / "china_standout_track" / "board.parquet"


# ===========================================================================
# 1. era split arithmetic — against the real committed store
# ===========================================================================
@pytest.fixture(scope="module")
def board():
    return pd.read_parquet(BOARD_PARQUET)


@pytest.mark.skipif(not BOARD_PARQUET.exists(), reason="CN board store not present")
class TestRealStoreEraSplit:
    def test_the_store_still_holds_the_pre_change_history(self, board):
        """The rows the reset hid are still on disk — this was never a data loss."""
        assert len(board) > 1000
        assert "board_definition" in board.columns

    def test_the_known_cohorts_partition_the_store_exactly(self, board):
        """Eras + adjudicated cohorts cover every row; an UNREGISTERED stamp fails here.

        2026-08-04: the reversal_watch shelf (#4393) wrote its first rows under
        `cn_reversal_watch_v1` and this tripwire fired exactly as designed.

        2026-08-06: it fired again — and this time the drift was IN THE GUARD. #4509
        moved the engine to cn_prophet_v3 while this test still spelled "cn_prophet_v2"
        by hand, so the 24 live v3 rows plus the 8 cn_prophet_v2_shadow challenger rows
        matched no mask at all. A guard that re-spells a producer's constant cannot
        catch that producer moving. Every mask below now reads its stamps from the
        module that emits them.
        """
        raw = board["board_definition"]
        stamps = raw.astype(str)
        prior = raw.map(bcl._cn_is_legacy_stamp)
        # LIVE stamp — from engine.china_board_rank, never re-spelled here.
        current = stamps == china_board_rank.BOARD_DEFINITION
        # CLOSED former headline eras — historical facts, see the constant's comment.
        superseded = stamps.isin(bcl._CN_SUPERSEDED_ERA_STAMPS)
        # Parallel watch/measurement cohorts — from engine.china_standout_track.
        shelf = stamps.isin(cst.WATCH_DEFINITIONS)

        counts = (prior.astype(int) + current.astype(int)
                  + superseded.astype(int) + shelf.astype(int))
        assert (counts <= 1).all(), \
            "a row landed in TWO cohorts: " + str(sorted(set(stamps[counts > 1])))
        assert int(counts.sum()) == len(board), \
            ("a row landed in NO known cohort — a new stamp needs adjudication: "
             + str(sorted(set(stamps[counts == 0]))))
        assert int(prior.sum()) > 0

    def test_the_partition_and_the_nightly_alarm_can_never_disagree(self, board):
        """The set this test accepts IS the set the emitter's ::warning gate accepts.

        Split them and one of two silent failures follows: a stamp accepted here but
        not there alarms every night for an expected state until the alarm rots into
        noise, and a stamp accepted there but not here hides an unadjudicated cohort
        behind a green test.
        """
        known = bcl._cn_known_cohort_stamps()
        unadjudicated = {s for s in set(board["board_definition"].astype(str))
                         if not bcl._cn_is_legacy_stamp(s) and s not in known}
        assert unadjudicated == set(), unadjudicated

    def test_the_headline_eras_do_not_overlap_in_time(self, board):
        """Headline eras are SEQUENTIAL: legacy → each superseded stamp → live.

        Watch/shelf cohorts are deliberately excluded: they run in PARALLEL with the
        live board by design — cn_prophet_v2_shadow writes on the SAME dates as
        cn_prophet_v3, which is the entire point of the v3-vs-v2 race — so a global
        ordering claim over every stamp would be false. _CN_SUPERSEDED_ERA_STAMPS is
        ordered oldest-first, which is what makes this chain meaningful.
        """
        raw = board["board_definition"]
        stamps = raw.astype(str)
        d = board["date"].astype(str)
        chain = ([d[raw.map(bcl._cn_is_legacy_stamp)]]
                 + [d[stamps == s] for s in bcl._CN_SUPERSEDED_ERA_STAMPS]
                 + [d[stamps == china_board_rank.BOARD_DEFINITION]])
        chain = [c for c in chain if not c.empty]
        assert len(chain) >= 2, "need at least two populated eras to test ordering"
        for older, newer in zip(chain, chain[1:]):
            assert older.max() < newer.min(), (older.max(), newer.min())

    def test_legacy_stamp_recognises_every_pre_version_spelling(self):
        for value in (None, float("nan"), "", "  ", "legacy", "NaN", "None", "<NA>"):
            assert bcl._cn_is_legacy_stamp(value) is True, value
        for value in ("cn_prophet_v2", "cn_prophet_v3", "v1"):
            assert bcl._cn_is_legacy_stamp(value) is False, value


# ===========================================================================
# 2. emit shape — synthetic prices, deterministic
# ===========================================================================
def _ohlc(idx, closes):
    """High/low straddle the close so _t1_fill never reads a locked-limit bar."""
    return pd.DataFrame(
        {"open": list(closes), "high": [c * 1.01 for c in closes],
         "low": [c * 0.99 for c in closes], "close": list(closes)},
        index=idx,
    )


_JUNE = pd.to_datetime([f"2026-06-{d:02d}" for d in range(1, 30)])
_JULY = pd.to_datetime([f"2026-07-{d:02d}" for d in range(20, 32)])


def _price_frame(ticker: str):
    if ticker == "600519.SS":                      # prior era, rises
        return _ohlc(_JUNE, [100.0 + i * 2 for i in range(len(_JUNE))])
    if ticker == "300750.SZ":                      # prior era, falls
        return _ohlc(_JUNE, [200.0 - i * 1.5 for i in range(len(_JUNE))])
    if ticker == "601318.SS":                      # current era, still early
        return _ohlc(_JULY, [40.0 + i * 0.1 for i in range(len(_JULY))])
    if ticker == "000001.SZ":                      # UNRECOGNISED stamp's era
        return _ohlc(_JUNE, [50.0 + i * 0.8 for i in range(len(_JUNE))])
    return None


def _bench():
    idx = _JUNE.append(_JULY)
    return pd.Series([3000.0 + i for i in range(len(idx))], index=idx)


def _store(tmp_path: Path) -> Path:
    d = tmp_path / "china_standout_track"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "board.parquet"
    pd.DataFrame([
        {"date": "2026-06-01", "ticker": "600519.SS", "board_rank": 1, "tier": "T1",
         "board_definition": None},
        {"date": "2026-06-01", "ticker": "300750.SZ", "board_rank": 2, "tier": "T2",
         "board_definition": "legacy"},
        {"date": "2026-07-20", "ticker": "601318.SS", "board_rank": 1, "tier": "T1",
         "board_definition": "cn_prophet_v2"},
    ]).to_parquet(p, index=False)
    return p


@pytest.fixture()
def emitted(monkeypatch, tmp_path):
    from engine import china_standout_track as cst
    p = _store(tmp_path)
    monkeypatch.setattr(cst, "_store_path", lambda: p)
    monkeypatch.setattr(cst, "_price_frame", _price_frame)
    monkeypatch.setattr(cst, "_bench_close", _bench)
    site = tmp_path / "site"
    (site / "factordata").mkdir(parents=True)
    assert bcl.emit_cn_track_ledger(site, None, [],
                                    board_definition="cn_prophet_v2",
                                    asof="2026-07-31") is True
    return json.loads((site / "factordata" / "cn_track_ledger.json").read_text())


class TestEmitTwoEras:
    def test_the_current_block_is_unchanged_for_existing_consumers(self, emitted):
        # The template reads meta.board_definition; the popup reads schema/summary/rows.
        assert emitted["schema"] == "track_ledger/v1"
        assert emitted["market"] == "CN"
        assert emitted["meta"]["grain"] == "episode"
        assert emitted["meta"]["board_definition"] == "cn_prophet_v2"
        assert emitted["summary"]["board_definition"] == "cn_prophet_v2"
        assert {r["t"] for r in emitted["rows"]} == {"601318.SS"}

    def test_prior_record_is_present_and_labelled_in_both_languages(self, emitted):
        pr = emitted["prior_record"]
        assert pr["board_definition"] == bcl._CN_PRIOR_ERA_ID != "cn_prophet_v2"
        assert pr["label_en"] and pr["label_zh"]
        assert pr["label_en"] != pr["label_zh"]
        assert "previous board definition" in pr["label_en"]
        assert "上一版" in pr["label_zh"]
        assert (pr["date_from"], pr["date_to"]) == ("2026-06-01", "2026-06-01")

    def test_both_legacy_spellings_land_in_the_prior_era(self, emitted):
        # null AND the literal string 'legacy' are the same era.
        assert {r["t"] for r in emitted["prior_record"]["rows"]} == \
            {"600519.SS", "300750.SZ"}

    def test_no_row_is_pooled_across_the_boundary(self, emitted):
        cur = {(r["t"], r["d"]) for r in emitted["rows"]}
        prior = {(r["t"], r["d"]) for r in emitted["prior_record"]["rows"]}
        assert cur and prior
        assert cur & prior == set()

    def test_the_prior_era_carries_a_matured_summary(self, emitted):
        s = emitted["prior_record"]["summary"]
        assert s["n_matured"] > 0
        assert s["metric"] == "excess"
        assert s["horizon"] == bcl._CN_HORIZON
        assert s["win_pct"] is not None

    def test_the_two_summaries_use_the_same_scorer_settings(self, emitted):
        cur, prior = emitted["summary"], emitted["prior_record"]["summary"]
        assert cur["metric"] == prior["metric"]
        assert cur["horizon"] == prior["horizon"]
        assert emitted["meta"]["exit_rule"] == emitted["prior_record"]["meta"]["exit_rule"]

    def test_prior_rows_use_the_same_row_shape(self, emitted):
        from engine import track_ledger as tl
        for r in emitted["prior_record"]["rows"]:
            assert set(r) == set(emitted["rows"][0])
            assert r["st"] in tl.STATUS_VOCAB
            assert set(r["fl"]).issubset(set(tl.FLAG_VOCAB))

    def test_prior_rows_are_newest_first_and_capped_like_the_live_block(self, emitted):
        from engine import track_ledger as tl
        pr = emitted["prior_record"]
        dates = [r["d"] for r in pr["rows"]]
        assert dates == sorted(dates, reverse=True)
        assert len(pr["rows"]) <= tl.MAX_ROWS
        assert pr["meta"]["truncated"] == max(0, pr["meta"]["n_total"] - len(pr["rows"]))

    def test_the_pooling_ban_is_written_into_the_artifact(self, emitted):
        meta = emitted["prior_record"]["meta"]
        assert "never be added together" in meta["pooling_note_en"]
        assert meta["pooling_note_zh"] and meta["pooling_note_zh"] != meta["pooling_note_en"]
        assert meta["closed"] is True

    def test_prior_state_comes_from_its_own_sample(self, emitted):
        # 2 matured episodes on 1 board day cannot carry a headline.
        assert emitted["prior_record"]["state"] == "accruing"

    def test_no_prior_block_when_the_store_has_only_current_rows(
        self, monkeypatch, tmp_path
    ):
        from engine import china_standout_track as cst
        p = _store(tmp_path)
        board = pd.read_parquet(p)
        board["board_definition"] = "cn_prophet_v2"
        board.to_parquet(p, index=False)
        monkeypatch.setattr(cst, "_store_path", lambda: p)
        monkeypatch.setattr(cst, "_price_frame", _price_frame)
        monkeypatch.setattr(cst, "_bench_close", _bench)
        site = tmp_path / "site2"
        (site / "factordata").mkdir(parents=True)
        assert bcl.emit_cn_track_ledger(site, None, [],
                                        board_definition="cn_prophet_v2") is True
        doc = json.loads((site / "factordata" / "cn_track_ledger.json").read_text())
        assert "prior_record" not in doc

    def test_a_legacy_current_definition_never_double_counts(
        self, monkeypatch, tmp_path
    ):
        """With no versioned board yet, every row is the CURRENT record and there is no
        prior era — emitting one would publish the same episodes twice."""
        from engine import china_standout_track as cst
        p = _store(tmp_path)
        board = pd.read_parquet(p)
        board["board_definition"] = None
        board.to_parquet(p, index=False)
        monkeypatch.setattr(cst, "_store_path", lambda: p)
        monkeypatch.setattr(cst, "_price_frame", _price_frame)
        monkeypatch.setattr(cst, "_bench_close", _bench)
        site = tmp_path / "site3"
        (site / "factordata").mkdir(parents=True)
        assert bcl.emit_cn_track_ledger(site, None, [],
                                        board_definition="legacy") is True
        doc = json.loads((site / "factordata" / "cn_track_ledger.json").read_text())
        assert "prior_record" not in doc


# ===========================================================================
# 3. a stamp the split does not recognise is NEVER dropped
# ===========================================================================
# The split matched exactly two masks — the live stamp and the pre-version
# spellings — and `bdf_all` rows that matched neither simply fell out of the
# artifact. The store kept them, the desk stopped counting them, and nothing in the
# JSON or the Actions log said so. That is the silent-data-loss shape: a number
# quietly built on fewer rows than the store holds.
def _store_three_eras(tmp_path: Path) -> Path:
    """current + pre-version + one stamp this build has never heard of."""
    d = tmp_path / "china_standout_track"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "board.parquet"
    pd.DataFrame([
        {"date": "2026-06-01", "ticker": "600519.SS", "board_rank": 1, "tier": "T1",
         "board_definition": None},                       # pre-version era
        {"date": "2026-06-15", "ticker": "000001.SZ", "board_rank": 1, "tier": "T1",
         "board_definition": "cn_prophet_v1"},            # UNRECOGNISED
        {"date": "2026-07-20", "ticker": "601318.SS", "board_rank": 1, "tier": "T1",
         "board_definition": "cn_prophet_v2"},            # live era
    ]).to_parquet(p, index=False)
    return p


@pytest.fixture()
def three_eras(monkeypatch, tmp_path, capsys):
    """(doc, stdout) — stdout is captured so the annotation's COLUMN can be asserted."""
    from engine import china_standout_track as cst
    p = _store_three_eras(tmp_path)
    monkeypatch.setattr(cst, "_store_path", lambda: p)
    monkeypatch.setattr(cst, "_price_frame", _price_frame)
    monkeypatch.setattr(cst, "_bench_close", _bench)
    site = tmp_path / "site_three"
    (site / "factordata").mkdir(parents=True)
    assert bcl.emit_cn_track_ledger(site, None, [],
                                    board_definition="cn_prophet_v2",
                                    asof="2026-07-31") is True
    out = capsys.readouterr().out
    return json.loads((site / "factordata" / "cn_track_ledger.json").read_text()), out


class TestUnknownStampIsNeverDropped:
    def test_all_three_stamps_produce_an_era(self, three_eras):
        doc, _ = three_eras
        assert {r["t"] for r in doc["rows"]} == {"601318.SS"}
        assert {r["t"] for r in doc["prior_record"]["rows"]} == {"600519.SS"}
        extra = doc["extra_records"]
        assert len(extra) == 1
        assert {r["t"] for r in extra[0]["rows"]} == {"000001.SZ"}

    def test_no_store_row_is_lost(self, three_eras):
        """The count that actually pins the bug: every stored row reaches SOME era."""
        doc, _ = three_eras
        published = (len(doc["rows"])
                     + doc["prior_record"]["meta"]["n_total"]
                     + sum(e["meta"]["n_total"] for e in doc["extra_records"]))
        assert published == 3

    def test_an_adjudicated_shelf_gets_the_block_but_not_the_alarm(
        self, monkeypatch, tmp_path, capsys
    ):
        """A KNOWN shelf stamp publishes exactly like an unknown one — its own labelled
        extra_records block, never pooled — but must NOT trip the unknown-stamp
        warning: a nightly alarm for an expected state trains readers to ignore the
        alarm that matters (the fixture two tests up proves the unknown path still
        warns, so the pair pins the gate in both directions)."""
        from engine import china_standout_track as cst
        d = tmp_path / "china_standout_track"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "board.parquet"
        pd.DataFrame([
            {"date": "2026-06-01", "ticker": "600519.SS", "board_rank": 1, "tier": "T1",
             "board_definition": None},
            {"date": "2026-06-15", "ticker": "000001.SZ", "board_rank": 1, "tier": "T1",
             "board_definition": "cn_reversal_watch_v1"},   # ADJUDICATED shelf (matured date)
            {"date": "2026-07-20", "ticker": "601318.SS", "board_rank": 1, "tier": "T1",
             "board_definition": "cn_prophet_v2"},
        ]).to_parquet(p, index=False)
        monkeypatch.setattr(cst, "_store_path", lambda: p)
        monkeypatch.setattr(cst, "_price_frame", _price_frame)
        monkeypatch.setattr(cst, "_bench_close", _bench)
        site = tmp_path / "site_shelf"
        (site / "factordata").mkdir(parents=True)
        assert bcl.emit_cn_track_ledger(site, None, [],
                                        board_definition="cn_prophet_v2",
                                        asof="2026-07-31") is True
        out = capsys.readouterr().out
        doc = json.loads((site / "factordata" / "cn_track_ledger.json").read_text())
        extra = doc["extra_records"]
        assert len(extra) == 1
        assert {r["t"] for r in extra[0]["rows"]} == {"000001.SZ"}
        assert "cn-track-unknown-board-definition" not in out

    def test_the_unknown_era_is_labelled_by_its_stamp_value(self, three_eras):
        doc, _ = three_eras
        block = doc["extra_records"][0]
        assert block["board_definition"] == "cn_prophet_v1"
        assert block["summary"]["board_definition"] == "cn_prophet_v1"
        assert "cn_prophet_v1" in block["label_en"]
        assert "cn_prophet_v1" in block["label_zh"]
        assert block["label_en"] != block["label_zh"]
        # It is NOT relabelled as the known prior era — that would claim an ordering
        # this build does not have.
        assert block["board_definition"] != bcl._CN_PRIOR_ERA_ID
        assert (block["date_from"], block["date_to"]) == ("2026-06-15", "2026-06-15")

    def test_the_unknown_era_uses_the_same_block_shape_and_scorer(self, three_eras):
        doc, _ = three_eras
        block, prior = doc["extra_records"][0], doc["prior_record"]
        assert set(block) == set(prior)
        assert set(block["meta"]) == set(prior["meta"])
        assert block["summary"]["metric"] == doc["summary"]["metric"] == "excess"
        assert block["summary"]["horizon"] == doc["summary"]["horizon"] == bcl._CN_HORIZON
        assert block["meta"]["exit_rule"] == doc["meta"]["exit_rule"]
        assert "never be added together" in block["meta"]["pooling_note_en"]
        # An unrecognised stamp cannot be declared closed — nothing here knows
        # whether a lane is still writing it.
        assert block["meta"]["closed"] is False
        assert prior["meta"]["closed"] is True

    def test_the_three_eras_are_never_pooled(self, three_eras):
        doc, _ = three_eras
        live = {(r["t"], r["d"]) for r in doc["rows"]}
        prior = {(r["t"], r["d"]) for r in doc["prior_record"]["rows"]}
        extra = {(r["t"], r["d"]) for r in doc["extra_records"][0]["rows"]}
        assert live and prior and extra
        assert live & prior == set() and live & extra == set() and prior & extra == set()

    def test_the_warning_names_the_stamp_and_starts_its_line(self, three_eras):
        """Column 0 is the whole point: GitHub only parses '::' at line start, and
        every builder here logs through a prefixing formatter, so an annotation sent
        via log.* runs clean and produces NOTHING in the Actions summary."""
        _, out = three_eras
        hits = [ln for ln in out.splitlines()
                if ln.startswith("::") and "cn_prophet_v1" in ln]
        assert hits, (
            "no line-start annotation named the unrecognised stamp; captured stdout:\n"
            + out)
        line = hits[0]
        assert line.startswith("::warning title=")
        assert "cn-track-unknown-board-definition" in line
        assert "cn_prophet_v2" in line, "the annotation must also name the LIVE stamp"

    def test_a_store_with_no_unknown_stamp_emits_neither_block_nor_warning(
        self, emitted, capsys
    ):
        """The guard must stay quiet on the normal two-era store, or the annotation
        becomes noise nobody reads."""
        assert "extra_records" not in emitted
        assert "cn-track-unknown-board-definition" not in capsys.readouterr().out


class TestEraSpan:
    """m18b: each language carried the year on ONE end only — EN on the close, ZH on
    the open. Inside a single year that reads fine; across a year boundary it dates the
    far end to the wrong year in BOTH languages. The emitter is the live path, not the
    template: `_track_record_dlg.html.j2` splits label_en/label_zh on ' · ' and prints
    this span verbatim, and its own cross-year branch only runs when no label shipped.
    """

    def test_a_span_inside_one_year_keeps_the_terse_form(self):
        # byte-for-byte unchanged — this string is user-visible on china.html.
        assert bcl._cn_era_span("2026-06-30", "2026-07-29") == \
            ("Jun 30 – Jul 29 2026", "2026年6月30日–7月29日")

    def test_a_span_across_new_year_prints_both_years(self):
        en, zh = bcl._cn_era_span("2025-11-03", "2026-02-12")
        assert en == "Nov 3 2025 – Feb 12 2026"
        assert zh == "2025年11月3日–2026年2月12日"

    def test_the_cross_year_fix_reaches_the_joined_label_the_dialog_reads(self):
        """The dialog prints label_*.split(' · ')[1:], so the fix only lands if the
        JOINED label carries it — a span-level fix that never reached the label would
        leave the live page wrong with the unit test green."""
        en, zh = bcl._cn_era_label("2025-11-03", "2026-02-12")
        assert en.split(" · ", 1)[1] == "Nov 3 2025 – Feb 12 2026"
        assert zh.split(" · ", 1)[1] == "2025年11月3日–2026年2月12日"


class TestEraLabel:
    def test_unknown_label_names_the_stamp_in_both_languages(self):
        en, zh = bcl._cn_unknown_era_label("cn_prophet_v9", "2026-06-30", "2026-07-29")
        assert en == "other board definition · cn_prophet_v9 · Jun 30 – Jul 29 2026"
        assert zh == "其他选股口径 · cn_prophet_v9 · 2026年6月30日–7月29日"

    def test_unknown_label_degrades_without_dates_but_keeps_the_stamp(self):
        en, zh = bcl._cn_unknown_era_label("cn_prophet_v9", None, None)
        assert "cn_prophet_v9" in en and "cn_prophet_v9" in zh
        assert en != zh

    def test_label_is_derived_from_the_span_not_hard_coded(self):
        en, zh = bcl._cn_era_label("2026-06-30", "2026-07-29")
        assert en == "previous board definition · Jun 30 – Jul 29 2026"
        assert zh == "上一版选股口径 · 2026年6月30日–7月29日"

    def test_label_degrades_without_dates(self):
        en, zh = bcl._cn_era_label(None, None)
        assert en and zh and en != zh
