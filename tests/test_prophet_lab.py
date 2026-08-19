"""Contract tests for the Prophet Operator Lab projection (engine/prophet_lab).

Fixture-based: no live Radar output, no live Prophet index, no network. Every
test reads ``tests/fixtures/prophet_lab/**`` through the same injectable
``LabRoots`` the API router uses, so these tests exercise the exact read
path production traffic would.

Fixture layout (see tests/fixtures/prophet_lab/):
* ``radar_spool/live_flow/entry_radar_events/2026-08-18/`` — two
  ``entry_radar.events/v1`` envelopes: one at ``pass_ts=09:30Z`` (BEFORE the
  observation baseline -> retrospective_seed), one at ``pass_ts=14:00Z``
  (INSIDE the baseline window -> live_forward).
* ``observation_baseline.json`` — baseline window ``13:00Z..21:00Z``.
* ``prophet_index/index.json`` — plans for BBB (live, entry_date 2026-08-20),
  EEE (watch, no entry_date), and CCC (carries a published ``board_read``
  block, used to test the enrichment fallback when the library misses).
* ``stockdata/`` — library records for AAA, BBB, EEE only (CCC and DDD are
  deliberately absent, to exercise the fallback and null-with-health-note
  paths respectively).

Ticker map (by fixture design):
  AAA  G0 only, retrospective (09:30 pass)
  BBB  C1 only, live_forward (14:00 pass), NONTERMINAL episode in the ledger
  CCC  C2a only, live_forward, enrichment via published board_read fallback
  DDD  all six C2 variants, live_forward, enrichment unavailable everywhere
  EEE  C2a (retrospective, 09:30) AND G0 (live_forward, 14:00) -> the
       g0/c2a intersection board's one populated row, mixed observation class
  FFF  C3 only -> must never appear on lab-all-early-v1
  GGG  C5 only -> must never appear on lab-all-early-v1
  HHH  C1 only, but its episode is TERMINAL (RESOLVED) -> excluded from
       lab-c1-v1 and lab-all-early-v1
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from engine.entry_radar.live_ledger import LiveEpisode, LiveEpisodeLedger
from engine.prophet_lab import LabRoots, build_lab_response
from engine.prophet_lab import boards as boards_mod
from engine.prophet_lab import observation as obs_mod
from engine.prophet_lab import sources as sources_mod
from engine.prophet_lab.contracts import (
    ALL_FALSE_AUTHORITY,
    BOARD_ALL_EARLY,
    BOARD_C1,
    BOARD_C2A,
    BOARD_C2_VARIANTS,
    BOARD_G0,
    BOARD_G0_C2A_INTERSECTION,
    BOARD_IDS,
    C1_DETECTOR_ID,
    C2_SUBTYPES,
    OBSERVATION_LIVE_FORWARD,
    OBSERVATION_RETROSPECTIVE_SEED,
    SCHEMA_LAB_BOARD,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prophet_lab"


def _write_ledger(state_dir: Path) -> None:
    """A minimal, VALID live episode ledger: BBB nonterminal, HHH terminal.

    Built through the real ``LiveEpisode``/``LiveEpisodeLedger`` classes (not
    hand-written JSON) so construction itself enforces every §13 validation
    rule — a byte-correct fixture rather than a guess at the schema.
    """
    ledger = LiveEpisodeLedger(state_dir)
    ledger._episodes["ep-bbb-c1"] = LiveEpisode(  # noqa: SLF001 — fixture setup
        episode_id="ep-bbb-c1", ticker="BBB", detector_id=C1_DETECTOR_ID,
        detector_version=1, detector_spec_hash="fixture-hash",
        state="ARMED", market_session="2026-08-18",
        evidence_refs=("evt-c1-bbb-1",),
    )
    ledger._episodes["ep-hhh-c1"] = LiveEpisode(  # noqa: SLF001 — fixture setup
        episode_id="ep-hhh-c1", ticker="HHH", detector_id=C1_DETECTOR_ID,
        detector_version=1, detector_spec_hash="fixture-hash",
        state="RESOLVED", market_session="2026-08-17",
        evidence_refs=("evt-c1-hhh-1",),
    )
    ledger.save()


@pytest.fixture()
def roots(tmp_path: Path) -> LabRoots:
    state_dir = tmp_path / "radar_state"
    _write_ledger(state_dir)
    return LabRoots(
        radar_spool_dir=FIXTURES / "radar_spool",
        radar_state_dir=state_dir,
        prophet_index_path=FIXTURES / "prophet_index" / "index.json",
        enrichment_library_root=FIXTURES / "stockdata",
        observation_baseline_path=FIXTURES / "observation_baseline.json",
    )


@pytest.fixture()
def roots_no_baseline(roots: LabRoots) -> LabRoots:
    return replace(roots, observation_baseline_path=None)


# ---------------------------------------------------------------------------
# response envelope
# ---------------------------------------------------------------------------
def test_schema_and_all_false_authority_block(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    assert payload["schema"] == SCHEMA_LAB_BOARD
    assert payload["authority"] == ALL_FALSE_AUTHORITY
    assert all(v is False for v in payload["authority"].values())
    assert set(payload["boards"]) == set(BOARD_IDS)


def test_missing_roots_degrade_to_empty_boards_not_errors() -> None:
    payload = build_lab_response(LabRoots())
    assert payload["schema"] == SCHEMA_LAB_BOARD
    for rows in payload["boards"].values():
        assert rows == []
    assert payload["health"]["observation_baseline_present"] is False
    assert payload["health"]["prophet_index_readable"] is False


# ---------------------------------------------------------------------------
# the six boards
# ---------------------------------------------------------------------------
def test_g0_board_is_exact_g0_grey_dot(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_G0]
    assert {row["ticker"] for row in rows} == {"AAA", "EEE"}
    for row in rows:
        assert row["detector_id"] == "G0_GREY_DOT@1"


def test_c1_board_only_current_nonterminal_episode(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_C1]
    # HHH fired C1 too, but its episode is RESOLVED (terminal) -> excluded.
    assert {row["ticker"] for row in rows} == {"BBB"}
    assert rows[0]["detector_id"] == "C1_1D_LIVE_WASHOUT@1"


def test_c2a_board_is_exactly_the_c2a_subtype(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_C2A]
    assert {row["ticker"] for row in rows} == {"EEE", "CCC", "DDD"}
    for row in rows:
        assert row["detector_id"] == "C2_1D_TURN@1"
        assert row["subtype"] == "c2a_kd_cross"


def test_c2_variants_board_preserves_all_six_subtypes_separately(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_C2_VARIANTS]
    ddd_subtypes = {row["subtype"] for row in rows if row["ticker"] == "DDD"}
    assert ddd_subtypes == set(C2_SUBTYPES)
    # Each variant is its own row/expert -- never merged into one generic "C2".
    assert len([r for r in rows if r["ticker"] == "DDD"]) == 6


def test_intersection_board_is_display_only_and_mints_nothing(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_G0_C2A_INTERSECTION]
    # Only EEE carries both a G0 event and a c2a event.
    assert {row["ticker"] for row in rows} == {"EEE"}
    row = rows[0]
    assert row["detector_id"] is None  # LAB-0 §3: "view detector_id = null"
    assert row["event_id"] is None
    assert row["subtype"] is None
    expert_ids = {(e["detector_id"], e["event_id"]) for e in row["experts"]}
    assert expert_ids == {
        ("G0_GREY_DOT@1", "evt-g0-eee-1"),
        ("C2_1D_TURN@1", "evt-c2a-eee-1"),
    }


def test_intersection_board_excludes_a_ticker_with_only_one_side(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    tickers = {row["ticker"] for row in payload["boards"][BOARD_G0_C2A_INTERSECTION]}
    assert "AAA" not in tickers  # G0 only, no c2a
    assert "CCC" not in tickers  # c2a only, no G0


def test_all_early_board_excludes_c3_and_c5(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    tickers = {row["ticker"] for row in payload["boards"][BOARD_ALL_EARLY]}
    assert "FFF" not in tickers  # C3_1D_4H_RECOVERY@1
    assert "GGG" not in tickers  # C5_BOTTOM_WATCH@1
    assert tickers == {"AAA", "BBB", "CCC", "DDD", "EEE"}


def test_all_early_board_excludes_terminal_c1_episode(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    tickers = {row["ticker"] for row in payload["boards"][BOARD_ALL_EARLY]}
    assert "HHH" not in tickers


def test_all_early_board_one_ticker_card_can_carry_multiple_experts(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = {row["ticker"]: row for row in payload["boards"][BOARD_ALL_EARLY]}
    eee = rows["EEE"]
    assert len(eee["experts"]) == 2
    assert {e["detector_id"] for e in eee["experts"]} == {"G0_GREY_DOT@1", "C2_1D_TURN@1"}
    assert eee["detector_id"] is None


# ---------------------------------------------------------------------------
# observation-class honesty (LAB-0 §4)
# ---------------------------------------------------------------------------
def test_pre_baseline_event_is_retrospective_seed(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    aaa = g0_rows["AAA"]
    assert aaa["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
    assert aaa["evidence_eligible"] is False
    assert aaa["prophet_comparison"]["measured_lab_to_prophet_lead_days"] is None


def test_post_baseline_event_is_live_forward(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    bbb = c1_rows["BBB"]
    assert bbb["observation_class"] == OBSERVATION_LIVE_FORWARD
    assert bbb["evidence_eligible"] is True


def test_absent_baseline_forces_every_row_retrospective(roots_no_baseline: LabRoots) -> None:
    payload = build_lab_response(roots_no_baseline)
    saw_any_row = False
    for rows in payload["boards"].values():
        for row in rows:
            saw_any_row = True
            assert row["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
            assert row["evidence_eligible"] is False
            assert row["prophet_comparison"]["measured_lab_to_prophet_lead_days"] is None
            for expert in row["experts"]:
                assert expert["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
                assert expert["evidence_eligible"] is False
    assert saw_any_row, "fixture must produce at least one row for this assertion to mean anything"


def test_live_forward_row_carries_a_measured_lead(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    bbb = c1_rows["BBB"]
    # Lab first saw BBB 2026-08-18 (14:00 pass); Prophet's entry_date is
    # 2026-08-20 -> the Lab led Prophet by 2 days.
    assert bbb["prophet_comparison"]["measured_lab_to_prophet_lead_days"] == 2


def test_null_signal_known_ts_is_preserved_never_reconstructed(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    expert = g0_rows["AAA"]["experts"][0]
    assert expert["signal_known_ts"] is None
    assert expert["sort_basis"] == "signal_ts"


def test_signal_known_ts_used_as_sort_basis_when_supplied(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    expert = c1_rows["BBB"]["experts"][0]
    assert expert["signal_known_ts"] == "2026-08-18T14:00:05Z"
    assert expert["sort_basis"] == "signal_known_ts"
    assert expert["sort_ts"] == "2026-08-18T14:00:05Z"


# ---------------------------------------------------------------------------
# expert identity preservation
# ---------------------------------------------------------------------------
def test_experts_preserve_exact_detector_event_subtype_identity(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    for row in payload["boards"][BOARD_C2_VARIANTS]:
        expert = row["experts"][0]
        assert expert["detector_id"] == row["detector_id"]
        assert expert["event_id"] == row["event_id"]
        assert expert["subtype"] == row["subtype"]


# ---------------------------------------------------------------------------
# enrichment: library -> published board_read fallback -> null + health note
# ---------------------------------------------------------------------------
def test_enrichment_precedence(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    by_ticker: dict[str, dict] = {}
    for rows in payload["boards"].values():
        for row in rows:
            by_ticker.setdefault(row["ticker"], row)
    assert by_ticker["BBB"]["name"] == "Bbb Industries"  # library hit
    assert by_ticker["CCC"]["name"] == "Ccc Corp (published fallback)"  # index fallback
    assert by_ticker["CCC"]["spark"] is None  # published spark was blocked_data
    assert by_ticker["DDD"]["name"] is None  # neither source reaches DDD
    assert by_ticker["DDD"]["sector"] is None
    assert by_ticker["DDD"]["spark"] is None


# ---------------------------------------------------------------------------
# health block
# ---------------------------------------------------------------------------
def test_health_block_reports_source_availability(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    health = payload["health"]
    assert health["radar_spool_readable"] is True
    assert health["radar_envelopes_read"] == 2
    assert health["radar_events_seen"] == 14
    assert health["radar_episode_ledger_readable"] is True
    assert health["prophet_index_readable"] is True
    assert health["prophet_plans_indexed"] == 3
    assert health["enrichment_library_available"] is True
    assert health["observation_baseline_present"] is True


# ---------------------------------------------------------------------------
# sources.py unit tests
# ---------------------------------------------------------------------------
def test_read_radar_envelopes_skips_malformed_and_off_schema_files(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    good_dir = spool / "live_flow" / "entry_radar_events" / "2026-08-18"
    good_dir.mkdir(parents=True)
    (good_dir / "ok.json").write_text(
        '{"schema": "entry_radar.events/v1", "pass_ts": "2026-08-18T10:00:00Z", '
        '"pass_id": "p", "pack": {}, "transitions": [], "events": [], "health": {}}',
        encoding="utf-8",
    )
    (good_dir / "torn.json").write_text("{not json", encoding="utf-8")
    (good_dir / "off_schema.json").write_text('{"schema": "some.other/v1"}', encoding="utf-8")
    envelopes = sources_mod.read_radar_envelopes(spool)
    assert len(envelopes) == 1
    assert envelopes[0]["pass_ts"] == "2026-08-18T10:00:00Z"


def test_extract_events_first_observed_is_the_earliest_pass_ts() -> None:
    envelopes = [
        {"pass_ts": "2026-08-18T14:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
        {"pass_ts": "2026-08-18T09:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
        {"pass_ts": "2026-08-18T20:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
    ]
    events, first_observed = sources_mod.extract_events(envelopes)
    assert len(events) == 1  # deduped by event_id
    assert first_observed["e1"] == "2026-08-18T09:00:00Z"


def test_read_observation_baseline_absent_file_returns_none(tmp_path: Path) -> None:
    assert sources_mod.read_observation_baseline(tmp_path / "nope.json") is None
    assert sources_mod.read_observation_baseline(None) is None


def test_read_observation_baseline_requires_baseline_started_at(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text('{"schema": "prophet_lab.observation_baseline/v1"}', encoding="utf-8")
    assert sources_mod.read_observation_baseline(path) is None


def test_read_live_episodes_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert sources_mod.read_live_episodes(tmp_path / "absent") == []
    assert sources_mod.read_live_episodes(None) == []


# ---------------------------------------------------------------------------
# observation.py unit tests
# ---------------------------------------------------------------------------
def test_classify_observation_no_baseline_is_always_seed() -> None:
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-18T14:00:00Z"}, baseline=None,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_before_window_is_seed() -> None:
    baseline = {"baseline_started_at": "2026-08-18T13:00:00Z"}
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-18T09:00:00Z"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_after_continuous_through_is_seed() -> None:
    baseline = {
        "baseline_started_at": "2026-08-18T13:00:00Z",
        "continuous_through": "2026-08-18T15:00:00Z",
    }
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-18T20:00:00Z"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_inside_window_is_live_forward() -> None:
    baseline = {
        "baseline_started_at": "2026-08-18T13:00:00Z",
        "continuous_through": "2026-08-18T21:00:00Z",
    }
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-18T14:00:00Z"}, baseline=baseline,
    ) == OBSERVATION_LIVE_FORWARD


def test_measured_lead_days_none_for_seed() -> None:
    assert obs_mod.measured_lead_days(
        OBSERVATION_RETROSPECTIVE_SEED,
        first_observed_at="2026-08-18", prophet_anchor_at="2026-08-20",
    ) is None


def test_measured_lead_days_none_when_a_timestamp_is_missing() -> None:
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD, first_observed_at=None, prophet_anchor_at="2026-08-20",
    ) is None
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD, first_observed_at="2026-08-18", prophet_anchor_at=None,
    ) is None


def test_measured_lead_days_computes_a_signed_day_count() -> None:
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD,
        first_observed_at="2026-08-18T14:00:00Z", prophet_anchor_at="2026-08-20",
    ) == 2
