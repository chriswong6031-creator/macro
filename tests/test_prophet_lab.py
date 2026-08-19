"""Contract tests for the Prophet Operator Lab projection (engine/prophet_lab).

Fixture-based: no live Radar output, no live Prophet index, no network. Every
test reads ``tests/fixtures/prophet_lab/**`` through the same injectable
``LabRoots`` the API router uses, so these tests exercise the exact read
path production traffic would.

Fixture layout (see tests/fixtures/prophet_lab/):
* ``radar_spool/live_flow/lab_events/2026-08-18/`` — two ``entry_radar.events/v1``
  envelopes: one at ``pass_ts=09:30Z`` (BEFORE the observation baseline ->
  retrospective_seed), one at ``pass_ts=14:00Z`` (INSIDE the baseline window
  -> live_forward). The fixture SUBDIRECTORY name is deliberately NOT
  ``entry_radar_events`` (Radar's own real spool-key segment,
  ``engine.entry_radar.live_ledger.EVENT_SPOOL_PREFIX``) — this reader takes
  an injectable root and never depends on that literal segment name (see
  ``test_reader_honors_the_real_event_spool_prefix_shape`` below, which
  proves that independently, from an UNTRACKED tmp_path so it never collides
  with ``test_entry_radar_w1.py::test_radar_owns_only_its_declared_paths``'s
  path-substring census of TRACKED files).
* ``observation_baseline.json`` — baseline window ``13:00Z..21:00Z``.
* ``prophet_index/index.json`` — plans for BBB (live, entry_date 2026-08-20),
  EEE (watch, entry_date 2026-08-19), CCC (TWO non-closed rows — the newer
  carries a board_read block with every field blocked_data, the older
  carries a usable one, pinning review N5: the enrichment fallback must not
  stop at the first row), and AAA (one CLOSED plan only, pinning review B1).
* ``stockdata/`` — library records for AAA, BBB, EEE only (CCC and DDD are
  deliberately absent, to exercise the fallback and null-with-health-note
  paths respectively).

Ticker map (by fixture design):
  AAA  G0 only, retrospective (09:30 pass). Prophet-side: ONE closed plan
       only -> membership:false, prior_plan populated (review B1).
  BBB  C1 only, live_forward (14:00 pass), NONTERMINAL episode in the ledger.
       Prophet entry_date 2026-08-20 postdates the Lab's 2026-08-18
       observation -> a positive measured lead.
  CCC  C2a only, live_forward. TWO non-closed Prophet plans; enrichment must
       skip the newer's blocked board_read and use the older's (review N5).
  DDD  all six C2 variants, live_forward, enrichment unavailable everywhere,
       no Prophet plan at all.
  EEE  C2a (retrospective, 09:30) AND G0 (live_forward, 14:00) -> the
       g0/c2a intersection board's one populated row, MIXED observation
       class (review B3). Prophet entry_date 2026-08-19 postdates the G0
       expert's observation -> a positive lead attributed to that expert.
  FFF  C3 only -> must never appear on lab-all-early-v1 (or any other board).
  GGG  C5 only -> must never appear on lab-all-early-v1 (or any other board).
  HHH  C1 only, but its episode is TERMINAL (RESOLVED) -> excluded from
       lab-c1-v1 and lab-all-early-v1.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from engine.entry_radar.entry_events import build_radar_native_event
from engine.entry_radar.live_ledger import (
    SCHEMA_ENTRY_RADAR_EVENTS,
    LiveEpisode,
    LiveEpisodeLedger,
)
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
    C3_DETECTOR_ID,
    C5_DETECTOR_ID,
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


@pytest.fixture()
def roots_no_ledger(roots: LabRoots, tmp_path: Path) -> LabRoots:
    """S5: an UNCONFIGURED episode ledger — must read as unavailable, not empty."""
    return replace(roots, radar_state_dir=tmp_path / "does-not-exist")


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


def test_board_definitions_are_included_in_the_payload(roots: LabRoots) -> None:
    # N3: kept, rather than dropped as a dead export — the frozen board
    # definitions ship on every response so an operator/UI never has to
    # cross-reference the doc to know what a board id means.
    payload = build_lab_response(roots)
    assert set(payload["board_definitions"]) == set(BOARD_IDS)
    assert "G0_GREY_DOT@1" in payload["board_definitions"][BOARD_G0]


# ---------------------------------------------------------------------------
# generation block (review B2)
# ---------------------------------------------------------------------------
def test_generation_block_reports_latest_pass_and_pack(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    generation = payload["generation"]
    assert generation["generated_at"]  # server clock, non-empty
    assert generation["latest_pass_ts"] == "2026-08-18T14:00:00Z"  # newer of the two envelopes
    assert generation["pack_as_of"] == "2026-08-18"
    assert generation["pack_hash"] == "fixture-pack-hash-2"
    assert generation["baseline_started_at"] == "2026-08-18T13:00:00Z"
    assert generation["baseline_coverage_verified"] is True


def test_generation_block_with_no_spool_reports_nothing_read() -> None:
    payload = build_lab_response(LabRoots())
    generation = payload["generation"]
    assert generation["latest_pass_ts"] is None
    assert generation["pack_as_of"] is None
    assert generation["pack_hash"] is None
    assert generation["baseline_coverage_verified"] is False


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


# review S8: C3/C5 must never leak into ANY of the four single-family boards
# either, not merely the union — a fixture that carries C3/C5 events at all
# (FFF, GGG) makes this a real assertion rather than a tautology.
@pytest.mark.parametrize(
    "board_id", [BOARD_G0, BOARD_C1, BOARD_C2A, BOARD_C2_VARIANTS],
)
def test_c3_and_c5_absent_from_every_single_family_board(roots: LabRoots, board_id: str) -> None:
    payload = build_lab_response(roots)
    for row in payload["boards"][board_id]:
        assert row["ticker"] not in {"FFF", "GGG"}
        for expert in row["experts"]:
            assert expert["detector_id"] not in {C3_DETECTOR_ID, C5_DETECTOR_ID}


def test_c3_and_c5_absent_from_multi_family_boards_too(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    for board_id in (BOARD_G0_C2A_INTERSECTION, BOARD_ALL_EARLY):
        for row in payload["boards"][board_id]:
            assert row["ticker"] not in {"FFF", "GGG"}


# review S8: default sort is newest-first, asserted explicitly (not merely
# implied by other tests reading a single row).
def test_default_sort_is_newest_first(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = payload["boards"][BOARD_C2_VARIANTS]
    ddd_rows = [r for r in rows if r["ticker"] == "DDD"]
    sort_values = [r["sort_ts"] for r in ddd_rows]
    assert sort_values == sorted(sort_values, reverse=True)
    # c2f (14:08) was minted after c2a (14:03) in the fixture -> it must lead.
    assert ddd_rows[0]["subtype"] == "c2f_rebound_atr"
    assert ddd_rows[-1]["subtype"] == "c2a_kd_cross"


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
    assert payload["generation"]["baseline_coverage_verified"] is False


def test_live_forward_row_carries_a_measured_lead(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    bbb = c1_rows["BBB"]
    # Lab first saw BBB 2026-08-18 (14:00 pass); Prophet's entry_date is
    # 2026-08-20 -> the Lab led Prophet by 2 days.
    comparison = bbb["prophet_comparison"]
    assert comparison["measured_lab_to_prophet_lead_days"] == 2
    assert comparison["measured_from_event_id"] == "evt-c1-bbb-1"


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
# review B1 — prophet_comparison is CURRENT membership only
# ---------------------------------------------------------------------------
def test_closed_only_plan_history_reports_no_membership(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    comparison = g0_rows["AAA"]["prophet_comparison"]
    assert comparison["membership"] is False
    assert comparison["lifecycle"] is None
    assert comparison["measured_lab_to_prophet_lead_days"] is None
    assert comparison["measured_from_event_id"] is None
    prior = comparison["prior_plan"]
    assert prior is not None
    assert prior["closed"] is True
    assert prior["lifecycle"] == "closed"
    assert prior["entry_date"] == "2026-08-02"
    assert "measured_lab_to_prophet_lead_days" not in prior  # never a lead against history


def test_open_membership_reports_no_prior_plan(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    comparison = c1_rows["BBB"]["prophet_comparison"]
    assert comparison["membership"] is True
    assert comparison["prior_plan"] is None


def test_no_plan_at_all_reports_no_membership_and_no_prior(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    variants = {row["ticker"]: row for row in payload["boards"][BOARD_C2_VARIANTS]}
    comparison = variants["DDD"]["prophet_comparison"]
    assert comparison["membership"] is False
    assert comparison["prior_plan"] is None


# ---------------------------------------------------------------------------
# review N5 — enrichment fallback consults every non-closed row, not just the first
# ---------------------------------------------------------------------------
def test_enrichment_fallback_does_not_stop_at_first_blocked_row(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c2a_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C2A]}
    ccc = c2a_rows["CCC"]
    # plan-ccc-2 (sorted first) carries an all-blocked_data board_read; only
    # plan-ccc-1 (sorted second) has usable data. The OLD code broke on the
    # first row regardless of whether it resolved anything.
    assert ccc["name"] == "Ccc Corp (published fallback)"
    assert ccc["sector"] == "Industrials"


# ---------------------------------------------------------------------------
# review B3 — multi-expert card attribution (EEE: mixed observation class)
# ---------------------------------------------------------------------------
def test_mixed_card_row_class_promoted_and_flagged(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    for board_id in (BOARD_G0_C2A_INTERSECTION, BOARD_ALL_EARLY):
        rows = {row["ticker"]: row for row in payload["boards"][board_id]}
        eee = rows["EEE"]
        assert eee["observation_class"] == OBSERVATION_LIVE_FORWARD  # promoted
        assert eee["observation_class_mixed"] is True
        assert eee["evidence_eligible"] is True  # promoted value


def test_mixed_card_per_expert_classes_are_preserved(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0_C2A_INTERSECTION]}
    by_detector = {e["detector_id"]: e for e in rows["EEE"]["experts"]}
    assert by_detector["G0_GREY_DOT@1"]["observation_class"] == OBSERVATION_LIVE_FORWARD
    assert by_detector["G0_GREY_DOT@1"]["evidence_eligible"] is True
    assert by_detector["C2_1D_TURN@1"]["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
    assert by_detector["C2_1D_TURN@1"]["evidence_eligible"] is False


def test_mixed_card_lead_is_attributed_to_the_live_forward_expert(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0_C2A_INTERSECTION]}
    comparison = rows["EEE"]["prophet_comparison"]
    # EEE's Prophet entry_date is 2026-08-19; the G0 expert (live_forward,
    # first observed 2026-08-18) is the only eligible anchor -> lead=1,
    # attributed to that event specifically, never to the seed C2a event.
    assert comparison["measured_lab_to_prophet_lead_days"] == 1
    assert comparison["measured_from_event_id"] == "evt-g0-eee-1"


def test_single_expert_row_is_never_flagged_mixed(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    for row in payload["boards"][BOARD_G0]:
        assert row["observation_class_mixed"] is False


# ---------------------------------------------------------------------------
# review round 2, S1 — _live_forward_lead_anchor picks the TRUE earliest
# instant, not the lexicographically-first first_observed_at string
# ---------------------------------------------------------------------------
def test_live_forward_lead_anchor_picks_the_true_earliest_instant() -> None:
    """The exact executed-failure scenario named in the review.

    Expert A's ``first_observed_at`` string sorts FIRST lexicographically
    ('19' < '20'), but expert B names the TRUE earlier instant
    (2026-08-20T00:30:00Z < 2026-08-20T01:00:00Z). The old
    ``candidates.sort(key=lambda pair: pair[0])`` (a raw string sort) would
    have picked A -- fabricating a lead anchored to the wrong event.
    """
    expert_a = {
        "observation_class": OBSERVATION_LIVE_FORWARD,
        "first_observed_at": "2026-08-19T20:00:00-05:00",  # = 2026-08-20T01:00:00Z
        "event_id": "evt-a",
    }
    expert_b = {
        "observation_class": OBSERVATION_LIVE_FORWARD,
        "first_observed_at": "2026-08-20T00:30:00Z",  # the TRUE earlier instant
        "event_id": "evt-b",
    }
    assert expert_a["first_observed_at"] < expert_b["first_observed_at"], (
        "sanity: A's string sorts first lexicographically -- this is the bug"
    )
    anchor_raw, anchor_event_id = boards_mod._live_forward_lead_anchor(  # noqa: SLF001
        [expert_a, expert_b],
    )
    assert anchor_event_id == "evt-b"
    assert anchor_raw == "2026-08-20T00:30:00Z"


def test_live_forward_lead_anchor_defensively_excludes_unparseable_entries() -> None:
    expert_bad = {
        "observation_class": OBSERVATION_LIVE_FORWARD,
        "first_observed_at": "not-a-timestamp",
        "event_id": "evt-bad",
    }
    expert_good = {
        "observation_class": OBSERVATION_LIVE_FORWARD,
        "first_observed_at": "2026-08-20T00:30:00Z",
        "event_id": "evt-good",
    }
    anchor_raw, anchor_event_id = boards_mod._live_forward_lead_anchor(  # noqa: SLF001
        [expert_bad, expert_good],
    )
    assert anchor_event_id == "evt-good"
    assert anchor_raw == "2026-08-20T00:30:00Z"


def test_live_forward_lead_anchor_no_candidates_returns_none_pair() -> None:
    seed_only = {
        "observation_class": OBSERVATION_RETROSPECTIVE_SEED,
        "first_observed_at": "2026-08-20T00:30:00Z",
        "event_id": "evt-seed",
    }
    assert boards_mod._live_forward_lead_anchor([seed_only]) == (None, None)  # noqa: SLF001


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
# review S6 — a spark, when present, is a resolved value, never a dangling ref
# ---------------------------------------------------------------------------
def test_spark_is_never_a_dangling_reference(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    seen_a_resolved_spark = False
    for rows in payload["boards"].values():
        for row in rows:
            spark = row["spark"]
            if spark is None:
                continue
            seen_a_resolved_spark = True
            assert "board_read_sparks.json#" not in spark
            assert spark.strip().startswith("<svg")
    assert seen_a_resolved_spark, "fixture must exercise at least one resolved spark"


def test_spark_resolves_for_bbb_from_the_library(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    assert c1_rows["BBB"]["spark"] == (
        "<svg viewBox=\"0 0 10 10\"><path d=\"M0 5 L10 5\"/></svg>"
    )


# ---------------------------------------------------------------------------
# review S5 — per-board availability, distinct from genuinely empty
# ---------------------------------------------------------------------------
def test_c1_board_availability_when_ledger_configured(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    assert payload["board_availability"][BOARD_C1]["available"] is True
    assert payload["board_availability"][BOARD_ALL_EARLY]["components"]["c1"]["available"] is True


def test_c1_board_reports_unavailable_when_ledger_is_unconfigured(
    roots_no_ledger: LabRoots,
) -> None:
    payload = build_lab_response(roots_no_ledger)
    # Genuinely unavailable, not "nothing nonterminal" -- and the rows list
    # is STILL empty either way, which is exactly why the flag must exist.
    assert payload["boards"][BOARD_C1] == []
    availability = payload["board_availability"][BOARD_C1]
    assert availability["available"] is False
    assert availability["reason"]
    all_early_c1 = payload["board_availability"][BOARD_ALL_EARLY]["components"]["c1"]
    assert all_early_c1["available"] is False


def test_other_boards_report_available_even_when_empty() -> None:
    # An empty spool is "nothing to show", never "unavailable" for the
    # non-episode-backed boards -- there is no ambiguity to disclose there.
    payload = build_lab_response(LabRoots())
    for board_id in (BOARD_G0, BOARD_C2A, BOARD_C2_VARIANTS, BOARD_G0_C2A_INTERSECTION):
        assert payload["board_availability"][board_id]["available"] is True


# ---------------------------------------------------------------------------
# review S1 — baseline coverage must fail CLOSED (both directions)
# ---------------------------------------------------------------------------
def test_coverage_verified_when_spool_reaches_back_to_baseline_start(roots: LabRoots) -> None:
    # Direction 1: earliest envelope (09:30) is BEFORE baseline_started_at
    # (13:00) -> coverage verified, per-event classification applies.
    payload = build_lab_response(roots)
    assert payload["generation"]["baseline_coverage_verified"] is True
    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    assert g0_rows["EEE"]["observation_class"] == OBSERVATION_LIVE_FORWARD


def test_coverage_not_verified_when_spool_has_a_gap(roots: LabRoots, tmp_path: Path) -> None:
    # Direction 2: point the spool at ONLY the 14:00 envelope (which
    # POSTDATES baseline_started_at=13:00 -- there is no evidence the spool
    # reaches back to the claimed start) -> coverage NOT verified, and every
    # row -- even the ones inside the nominal window -- degrades to
    # retrospective_seed.
    gapped_spool = tmp_path / "gapped_spool"
    late_dir = gapped_spool / "live_flow" / "lab_events" / "2026-08-18"
    late_dir.mkdir(parents=True)
    source = (
        FIXTURES / "radar_spool" / "live_flow" / "lab_events" / "2026-08-18"
        / "pass-140000-lab-pack.json"
    )
    (late_dir / "pass-140000-lab-pack.json").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8",
    )
    gapped_roots = replace(roots, radar_spool_dir=gapped_spool)
    payload = build_lab_response(gapped_roots)
    assert payload["generation"]["baseline_coverage_verified"] is False
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    # BBB's own event (14:00) is INSIDE the nominal window, but the coverage
    # gap forces it to retrospective_seed anyway -- fail closed.
    assert c1_rows["BBB"]["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
    assert c1_rows["BBB"]["evidence_eligible"] is False


def test_baseline_coverage_verified_helper_unit(roots: LabRoots) -> None:
    baseline = {"baseline_started_at": "2026-08-18T13:00:00Z"}
    assert sources_mod.baseline_coverage_verified(
        [{"pass_ts": "2026-08-18T09:00:00Z"}], baseline,
    ) is True
    assert sources_mod.baseline_coverage_verified(
        [{"pass_ts": "2026-08-18T14:00:00Z"}], baseline,
    ) is False
    assert sources_mod.baseline_coverage_verified([], baseline) is False
    assert sources_mod.baseline_coverage_verified(
        [{"pass_ts": "2026-08-18T09:00:00Z"}], None,
    ) is False


# ---------------------------------------------------------------------------
# day-2 temporal correctness amendment — baseline_coverage_verified adversarial
# cases
# ---------------------------------------------------------------------------
def test_baseline_coverage_verified_equal_instant_different_offsets() -> None:
    # The spool's earliest envelope and baseline_started_at name the SAME
    # instant via different offset forms -- must verify True either way
    # (inclusive "at or before").
    baseline_z = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    baseline_offset = {"baseline_started_at": "2026-08-19T06:00:00-04:00"}
    envelopes_z = [{"pass_ts": "2026-08-19T10:00:00Z"}]
    envelopes_offset = [{"pass_ts": "2026-08-19T06:00:00-04:00"}]
    assert sources_mod.baseline_coverage_verified(envelopes_z, baseline_z) is True
    assert sources_mod.baseline_coverage_verified(envelopes_z, baseline_offset) is True
    assert sources_mod.baseline_coverage_verified(envelopes_offset, baseline_z) is True
    assert sources_mod.baseline_coverage_verified(envelopes_offset, baseline_offset) is True


def test_baseline_coverage_verified_naive_baseline_started_at_fails_closed() -> None:
    baseline = {"baseline_started_at": "2026-08-19T10:00:00"}  # naive
    assert sources_mod.baseline_coverage_verified(
        [{"pass_ts": "2026-08-19T09:00:00Z"}], baseline,
    ) is False


def test_baseline_coverage_verified_naive_envelope_pass_ts_fails_closed() -> None:
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    assert sources_mod.baseline_coverage_verified(
        [{"pass_ts": "2026-08-19T09:00:00"}], baseline,  # naive -- unparseable here
    ) is False


def test_baseline_coverage_verified_true_when_evidence_reaches_further_back() -> None:
    """The mirror-positive case, pinned alongside the regression below.

    baseline_started_at = "2026-08-19T09:00:00-04:00" (13:00 UTC). The
    spool's only envelope pass_ts = "2026-08-19T10:00:00Z" (10:00 UTC) --
    BEFORE the claimed start (10:00 < 13:00 UTC), i.e. the spool's evidence
    reaches back FURTHER than the operator claims -- genuinely verified.
    """
    baseline = {"baseline_started_at": "2026-08-19T09:00:00-04:00"}
    envelopes = [{"pass_ts": "2026-08-19T10:00:00Z"}]
    assert sources_mod.baseline_coverage_verified(envelopes, baseline) is True


def test_baseline_coverage_verified_regression_lexicographic_bug() -> None:
    """The DANGEROUS direction: old code would have said "verified" when it wasn't.

    baseline_started_at = "2026-08-19T10:00:00Z" (10:00 UTC). The spool's
    only envelope pass_ts = "2026-08-19T09:00:00-04:00" (13:00 UTC) --
    actually AFTER the baseline start, so there IS a real gap (the spool's
    earliest evidence postdates the claimed start) and coverage must be
    UNVERIFIED.

    The OLD code compared the raw strings: ``"2026-08-19T09:00:00-04:00" <=
    "2026-08-19T10:00:00Z"`` is TRUE ('09' < '10'), so the old code would
    have WRONGLY reported coverage as verified -- exactly the false-positive
    direction that lets every row falsely promote to live_forward. The new
    instant-based compare correctly reports False.
    """
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    envelopes = [{"pass_ts": "2026-08-19T09:00:00-04:00"}]
    # Sanity check the bug is real: the raw strings compare the wrong way.
    assert envelopes[0]["pass_ts"] <= baseline["baseline_started_at"]
    assert sources_mod.baseline_coverage_verified(envelopes, baseline) is False


# ---------------------------------------------------------------------------
# health block (review S4/S7/S2-cheap)
# ---------------------------------------------------------------------------
def test_health_block_reports_source_availability(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    health = payload["health"]
    assert health["radar_spool_configured"] is True
    assert health["radar_spool_readable"] is True
    assert health["radar_envelopes_read"] == 2
    assert health["radar_envelopes_skipped"] == 0
    assert health["radar_events_seen"] == 14
    assert health["radar_episode_ledger_available"] is True
    assert health["prophet_index_readable"] is True
    assert health["prophet_plans_indexed"] == 5
    assert health["enrichment_library_available"] is True
    assert health["observation_baseline_present"] is True
    assert health["observation_baseline_coverage_verified"] is True


def test_health_block_surfaces_skipped_envelopes_not_just_a_zero(
    roots: LabRoots, tmp_path: Path,
) -> None:
    # review S7: a schema-drifted spool must be VISIBLE as skipped, not
    # silently collapse into "0 envelopes read, looks clean".
    drifted_spool = tmp_path / "drifted"
    day_dir = drifted_spool / "live_flow" / "entry_radar_events" / "2026-08-19"
    day_dir.mkdir(parents=True)
    (day_dir / "future-schema.json").write_text(
        '{"schema": "entry_radar.events/v2", "pass_ts": "2026-08-19T09:00:00Z"}',
        encoding="utf-8",
    )
    drifted_roots = replace(roots, radar_spool_dir=drifted_spool)
    payload = build_lab_response(drifted_roots)
    health = payload["health"]
    assert health["radar_spool_readable"] is True
    assert health["radar_envelopes_read"] == 0
    assert health["radar_envelopes_skipped"] == 1


def test_health_block_names_the_spool_source(roots: LabRoots) -> None:
    payload = build_lab_response(roots)
    # The `roots` fixture supplies radar_spool_dir directly (not via an env
    # ladder), so LabRoots' own default label is what surfaces here; the
    # env-ladder labelling itself is covered at the app.prophet_lab layer.
    assert payload["health"]["radar_spool_source"] == "unconfigured"


def test_c1_availability_unreadable_reason_when_state_dir_is_a_file(
    roots: LabRoots, tmp_path: Path,
) -> None:
    not_a_dir = tmp_path / "not_a_dir"
    not_a_dir.write_text("nope", encoding="utf-8")
    broken_roots = replace(roots, radar_state_dir=not_a_dir)
    payload = build_lab_response(broken_roots)
    availability = payload["board_availability"][BOARD_C1]
    assert availability["available"] is False
    assert availability["reason"] == "state_dir_absent"


# ---------------------------------------------------------------------------
# review N1 — deterministic sort key (mixed timestamp shapes)
# ---------------------------------------------------------------------------
def test_sort_key_orders_across_mixed_iso8601_shapes() -> None:
    # 'Z' suffix, explicit +00:00 offset, and a bare date must all compare
    # correctly against each other through ONE parsed clock, never a raw
    # string compare (which "2026-08-18T09:00:00+00:00" < "2026-08-18T09Z"
    # would get wrong lexically).
    rows = [
        {"ticker": "A", "sort_ts": "2026-08-18T09:00:00+00:00"},
        {"ticker": "B", "sort_ts": "2026-08-19T00:00:00Z"},
        {"ticker": "C", "sort_ts": "2026-08-17"},
        {"ticker": "D", "sort_ts": ""},
    ]
    ordered = boards_mod._sort_rows_newest_first(list(rows))  # noqa: SLF001
    assert [row["ticker"] for row in ordered] == ["B", "A", "C", "D"]


def test_sort_key_unparseable_timestamp_sorts_last() -> None:
    rows = [
        {"ticker": "GOOD", "sort_ts": "2026-08-18T09:00:00Z"},
        {"ticker": "BAD", "sort_ts": "not-a-timestamp"},
    ]
    ordered = boards_mod._sort_rows_newest_first(list(rows))  # noqa: SLF001
    assert [row["ticker"] for row in ordered] == ["GOOD", "BAD"]


# ---------------------------------------------------------------------------
# review N2 — baseline marker schema validation
# ---------------------------------------------------------------------------
def test_baseline_wrong_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema": "some.other.schema/v1", "baseline_started_at": "2026-08-18T13:00:00Z"}',
        encoding="utf-8",
    )
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is None
    assert result.error == "schema_mismatch"


def test_baseline_missing_schema_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text('{"baseline_started_at": "2026-08-18T13:00:00Z"}', encoding="utf-8")
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is None
    assert result.error == "schema_mismatch"


def test_baseline_correct_schema_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema": "prophet_lab.observation_baseline/v1", '
        '"baseline_started_at": "2026-08-18T13:00:00Z"}',
        encoding="utf-8",
    )
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is not None
    assert result.error is None


# ---------------------------------------------------------------------------
# review round 2, S4 — malformed marker distinguishable from absent by NAME
# ---------------------------------------------------------------------------
def test_baseline_naive_started_at_is_rejected_with_a_named_reason(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema": "prophet_lab.observation_baseline/v1", '
        '"baseline_started_at": "2026-08-18T13:00:00"}',  # naive -- no UTC offset
        encoding="utf-8",
    )
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is None
    assert result.error == "naive_or_unparseable_started_at"


def test_baseline_garbage_started_at_is_rejected_with_a_named_reason(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema": "prophet_lab.observation_baseline/v1", '
        '"baseline_started_at": "not-a-timestamp"}',
        encoding="utf-8",
    )
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is None
    assert result.error == "naive_or_unparseable_started_at"


def test_baseline_error_surfaces_in_the_health_block(tmp_path: Path, roots: LabRoots) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        '{"schema": "prophet_lab.observation_baseline/v1", '
        '"baseline_started_at": "2026-08-18T13:00:00"}',  # naive
        encoding="utf-8",
    )
    broken_roots = replace(roots, observation_baseline_path=path)
    payload = build_lab_response(broken_roots)
    assert payload["health"]["observation_baseline_present"] is False
    assert payload["health"]["observation_baseline_error"] == "naive_or_unparseable_started_at"


def test_baseline_unconfigured_has_no_error_in_the_health_block() -> None:
    # A simply-absent baseline is NOT an error -- it is the fail-honest
    # starting state (LAB-0 §4) -- so no `observation_baseline_error` key at
    # all, distinguishing "not set up" from "set up but broken".
    payload = build_lab_response(LabRoots())
    assert "observation_baseline_error" not in payload["health"]


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
    result = sources_mod.read_radar_envelopes(spool)
    assert result.configured is True
    assert result.dir_exists is True
    assert result.readable is True
    assert len(result.envelopes) == 1
    assert result.envelopes[0]["pass_ts"] == "2026-08-18T10:00:00Z"
    assert result.files_seen == 3
    assert result.envelopes_skipped == 2


def test_reader_honors_the_real_event_spool_prefix_shape(tmp_path: Path) -> None:
    """The reader is shape-agnostic, but must still work under Radar's REAL prefix.

    ``tests/fixtures/prophet_lab/radar_spool/**`` deliberately does NOT reuse
    Radar's own ``EVENT_SPOOL_PREFIX`` path segment as a fixture subdirectory
    name — a COMMITTED path containing the substring ``entry_radar`` trips
    ``tests/test_entry_radar_w1.py::test_radar_owns_only_its_declared_paths``'s
    census of tracked files outside the §16 owned-path set, which this
    package (an intentional, injectable-root READER of Radar's output, not a
    Radar-owned module) is not on. That guard only scans ``git ls-files``, so
    it is blind to anything under pytest's ``tmp_path`` — this test proves,
    from exactly such an untracked location, that :func:`sources_mod.read_radar_envelopes`
    reads correctly when pointed at a spool laid out with Radar's REAL prefix
    constant, not just the renamed fixture shape the rest of this module uses.
    """
    from engine.entry_radar.live_ledger import EVENT_SPOOL_PREFIX

    spool = tmp_path / "real_shape_spool"
    real_dir = spool / EVENT_SPOOL_PREFIX / "2026-08-18"
    real_dir.mkdir(parents=True)
    (real_dir / "10-00-00-entry_radar_pack.json").write_text(
        '{"schema": "entry_radar.events/v1", "pass_ts": "2026-08-18T10:00:00Z", '
        '"pass_id": "entry_radar_pack", "pack": {}, "transitions": [], '
        '"events": [], "health": {}}',
        encoding="utf-8",
    )
    result = sources_mod.read_radar_envelopes(spool)
    assert len(result.envelopes) == 1
    assert result.envelopes[0]["pass_ts"] == "2026-08-18T10:00:00Z"


def test_read_radar_envelopes_unconfigured_vs_absent_dir(tmp_path: Path) -> None:
    unconfigured = sources_mod.read_radar_envelopes(None)
    assert unconfigured.configured is False
    assert unconfigured.dir_exists is False
    assert unconfigured.readable is False

    absent = sources_mod.read_radar_envelopes(tmp_path / "nope")
    assert absent.configured is True
    assert absent.dir_exists is False
    assert absent.readable is False


def test_extract_events_first_observed_is_the_earliest_pass_ts() -> None:
    envelopes = [
        {"pass_ts": "2026-08-18T14:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
        {"pass_ts": "2026-08-18T09:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
        {"pass_ts": "2026-08-18T20:00:00Z", "events": [{"event_id": "e1", "ticker": "X"}]},
    ]
    events, first_observed = sources_mod.extract_events(envelopes)
    assert len(events) == 1  # deduped by event_id
    assert first_observed["e1"] == "2026-08-18T09:00:00Z"


def test_extract_events_mixed_offset_regression_and_classification() -> None:
    """Review round 2, S3 — the exact regression scenario, end to end.

    Two envelopes carry the SAME event_id at different, both-legal offset
    forms: ``09:00:00-04:00`` (= 13:00 UTC) and ``10:00:00Z`` (= 10:00 UTC).
    The TRUE earliest observation is the ``10:00:00Z`` envelope (10:00 UTC <
    13:00 UTC). A raw-string ``min()`` would instead pick the ``-04:00`` form
    as "earliest" ('09' < '10' lexicographically) -- which actually names the
    LATER instant.

    With ``baseline_started_at=2026-08-19T12:00:00Z``: the TRUE earliest
    (10:00 UTC) PREDATES the baseline start -> ``retrospective_seed`` is the
    honest answer (this observation happened before continuous coverage
    began). The buggy "earliest" (13:00 UTC, from the -04:00 form) would have
    been AFTER the baseline start -> incorrectly ``live_forward``.
    """
    envelope_a = {
        "pass_ts": "2026-08-19T09:00:00-04:00",  # = 13:00 UTC -- the buggy "earliest"
        "events": [{"event_id": "e1", "ticker": "X"}],
    }
    envelope_b = {
        "pass_ts": "2026-08-19T10:00:00Z",  # = 10:00 UTC -- the TRUE earliest
        "events": [{"event_id": "e1", "ticker": "X"}],
    }
    events, first_observed = sources_mod.extract_events([envelope_a, envelope_b])
    assert len(events) == 1
    assert first_observed["e1"] == "2026-08-19T10:00:00Z"

    # Regression proof: a raw-string min() over the same two pass_ts values
    # picks the WRONG one -- this is exactly what "a revert would flip it"
    # means. If extract_events were reverted to `pass_ts < first_observed[...]`
    # (a raw string compare), the assertion above would fail.
    raw_min = min(envelope_a["pass_ts"], envelope_b["pass_ts"])
    assert raw_min == envelope_a["pass_ts"], "sanity: the buggy compare picks envelope_a"
    assert raw_min != first_observed["e1"], "the fix picks a DIFFERENT (correct) answer"

    baseline = {"baseline_started_at": "2026-08-19T12:00:00Z"}
    classification = obs_mod.classify_observation(
        "e1", first_observed_at=first_observed, baseline=baseline,
    )
    assert classification == OBSERVATION_RETROSPECTIVE_SEED


def test_latest_envelope_picks_the_greatest_pass_ts() -> None:
    envelopes = [
        {"pass_ts": "2026-08-18T09:00:00Z", "pack": {"pack_hash": "old"}},
        {"pass_ts": "2026-08-18T14:00:00Z", "pack": {"pack_hash": "new"}},
    ]
    latest = sources_mod.latest_envelope(envelopes)
    assert latest["pack"]["pack_hash"] == "new"
    assert sources_mod.latest_envelope([]) is None


def test_earliest_pass_ts_of_empty_set_is_none() -> None:
    assert sources_mod.earliest_pass_ts([]) is None


def test_earliest_pass_ts_is_wired_through_earliest_instant_string() -> None:
    # Review round 2, N1: earliest_pass_ts is no longer its own re-implemented
    # scan -- it delegates to timeparse.earliest_instant_string, so this
    # exercises the mixed-offset regression through the sources.py entry
    # point too, not just the low-level helper directly.
    envelopes = [
        {"pass_ts": "2026-08-19T09:00:00-04:00"},  # = 13:00 UTC
        {"pass_ts": "2026-08-19T10:00:00Z"},        # = 10:00 UTC -- the TRUE earliest
    ]
    assert sources_mod.earliest_pass_ts(envelopes) == "2026-08-19T10:00:00Z"


def test_read_observation_baseline_absent_file_returns_none(tmp_path: Path) -> None:
    absent = sources_mod.read_observation_baseline(tmp_path / "nope.json")
    assert absent.baseline is None
    assert absent.error is None  # absent is not an error -- see S4 tests above
    unconfigured = sources_mod.read_observation_baseline(None)
    assert unconfigured.baseline is None
    assert unconfigured.error is None


def test_read_observation_baseline_requires_baseline_started_at(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text('{"schema": "prophet_lab.observation_baseline/v1"}', encoding="utf-8")
    result = sources_mod.read_observation_baseline(path)
    assert result.baseline is None
    assert result.error == "missing_baseline_started_at"


def test_read_live_episodes_missing_dir_returns_unavailable(tmp_path: Path) -> None:
    absent = sources_mod.read_live_episodes(tmp_path / "absent")
    assert absent.available is False
    assert absent.episodes == []

    unconfigured = sources_mod.read_live_episodes(None)
    assert unconfigured.configured is False
    assert unconfigured.available is False


def test_read_live_episodes_no_ledger_file_is_available_and_empty(tmp_path: Path) -> None:
    # A state dir that exists but has never written episodes.json is a
    # legitimate, AVAILABLE, empty ledger -- distinct from a missing/
    # misconfigured state_dir (review S5's own distinction, one layer down).
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    result = sources_mod.read_live_episodes(state_dir)
    assert result.available is True
    assert result.episodes == []


def test_read_live_episodes_reads_the_real_ledger_file_shape(tmp_path: Path) -> None:
    """Hand-parsed episodes.json (review ci-pack-10) round-trips a REAL ledger.

    Builds the file through the actual ``LiveEpisode``/``LiveEpisodeLedger``
    classes (as ``_write_ledger`` does elsewhere in this module) so this test
    proves the hand-rolled reader in ``sources.read_live_episodes`` correctly
    reads the byte-real production format, not a reader's own guess at it.
    """
    ledger = LiveEpisodeLedger(tmp_path / "state")
    ledger._episodes["ep-x"] = LiveEpisode(  # noqa: SLF001 — fixture setup
        episode_id="ep-x", ticker="XXX", detector_id=C1_DETECTOR_ID,
        detector_version=1, detector_spec_hash="hash", state="TURNING",
        market_session="2026-08-18",
    )
    ledger._episodes["ep-y"] = LiveEpisode(  # noqa: SLF001 — fixture setup
        episode_id="ep-y", ticker="YYY", detector_id=C1_DETECTOR_ID,
        detector_version=1, detector_spec_hash="hash", state="EXPIRED",
        market_session="2026-08-17",
    )
    ledger.save()

    result = sources_mod.read_live_episodes(tmp_path / "state")
    assert result.available is True
    by_ticker = {e.ticker: e for e in result.episodes}
    assert by_ticker["XXX"].detector_id == C1_DETECTOR_ID
    assert by_ticker["XXX"].terminal is False  # TURNING is nonterminal
    assert by_ticker["YYY"].terminal is True   # EXPIRED is terminal


def test_read_live_episodes_skips_malformed_rows(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "episodes.json").write_text(
        '{"schema": "entry_radar.live_ledger/v1", "episodes": ['
        '{"episode_id": "e1", "ticker": "AAA", "detector_id": "C1_1D_LIVE_WASHOUT@1", '
        '"state": "ARMED"}, '
        '{"episode_id": "e2", "ticker": "BBB"}, '
        '"not_an_object"'
        ']}',
        encoding="utf-8",
    )
    result = sources_mod.read_live_episodes(state_dir)
    assert result.available is True
    assert len(result.episodes) == 1
    assert result.episodes[0].episode_id == "e1"


# ---------------------------------------------------------------------------
# review ci-pack-10 — the Lab must never import the Radar detector stack
# ---------------------------------------------------------------------------
def test_sources_module_never_imports_the_radar_detector_stack() -> None:
    """AST-level pin: no ``import``/``from`` in sources.py names entry_radar.

    Measured 2026-08-19: a single (even lazy, function-level) import of
    ``engine.entry_radar.live_ledger`` pulled ~150 unrelated engine/*.py
    files into the transitive closure of every CI job that reaches
    ``engine.prophet_lab`` (Radar's own challengers/detectors fan-out into
    the US board/stock-scoring engine subsystem) -- a real, measured cost
    that has nothing to do with what this package actually needs (three
    plain fields off an episode record). This test is an AST walk, not a
    runtime import, so it catches the edge whether it is module-level or
    buried inside a function.
    """
    import ast

    source_path = Path(sources_mod.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "entry_radar" in node.module:
            offenders.append(node.module)
        elif isinstance(node, ast.Import):
            offenders.extend(a.name for a in node.names if "entry_radar" in a.name)
    assert not offenders, offenders


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


# ---------------------------------------------------------------------------
# day-2 temporal correctness amendment — classify_observation adversarial
# cases (instant comparison, never lexicographic string comparison)
# ---------------------------------------------------------------------------
def test_classify_observation_equal_instant_different_offsets_at_lower_boundary() -> None:
    # "2026-08-19T10:00:00Z" and "2026-08-19T06:00:00-04:00" name the SAME
    # instant. An observation exactly AT baseline_started_at (inclusive lower
    # bound) must classify identically regardless of which offset form either
    # side happens to use.
    baseline_z = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    baseline_offset = {"baseline_started_at": "2026-08-19T06:00:00-04:00"}
    observed_z = {"e1": "2026-08-19T10:00:00Z"}
    observed_offset = {"e1": "2026-08-19T06:00:00-04:00"}
    results = {
        obs_mod.classify_observation("e1", first_observed_at=observed_z, baseline=baseline_z),
        obs_mod.classify_observation("e1", first_observed_at=observed_z, baseline=baseline_offset),
        obs_mod.classify_observation("e1", first_observed_at=observed_offset, baseline=baseline_z),
        obs_mod.classify_observation("e1", first_observed_at=observed_offset, baseline=baseline_offset),
    }
    assert results == {OBSERVATION_LIVE_FORWARD}


@pytest.mark.parametrize(
    "observed_ts",
    [
        "2026-08-19T09:59:59Z",
        "2026-08-19T09:59:59+00:00",
        "2026-08-19T05:59:59-04:00",
        "2026-08-19T17:59:59+08:00",
    ],
)
def test_classify_observation_before_baseline_across_offset_forms(observed_ts: str) -> None:
    # All four forms name 09:59:59 UTC -- one second before a 10:00:00 UTC
    # baseline start, regardless of offset notation.
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": observed_ts}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


@pytest.mark.parametrize(
    "observed_ts",
    [
        "2026-08-19T10:00:01Z",
        "2026-08-19T10:00:01+00:00",
        "2026-08-19T06:00:01-04:00",
        "2026-08-19T18:00:01+08:00",
    ],
)
def test_classify_observation_after_baseline_across_offset_forms(observed_ts: str) -> None:
    # All four forms name 10:00:01 UTC -- one second after a 10:00:00 UTC
    # baseline start, with no continuous_through upper bound.
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": observed_ts}, baseline=baseline,
    ) == OBSERVATION_LIVE_FORWARD


def test_classify_observation_naive_observed_at_fails_closed_to_seed() -> None:
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-19T10:30:00"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED  # naive -- no UTC offset -- reject, don't guess


def test_classify_observation_naive_baseline_started_at_fails_closed_to_seed() -> None:
    baseline = {"baseline_started_at": "2026-08-19T10:00:00"}  # naive
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-19T10:30:00Z"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_unparseable_continuous_through_fails_closed_to_seed() -> None:
    # continuous_through IS present but garbage -- must reject, never silently
    # treat as "no upper bound" (that would be a promotion, not a rejection).
    baseline = {
        "baseline_started_at": "2026-08-19T10:00:00Z",
        "continuous_through": "not-a-timestamp",
    }
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "2026-08-19T10:30:00Z"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_unparseable_observed_at_fails_closed_to_seed() -> None:
    baseline = {"baseline_started_at": "2026-08-19T10:00:00Z"}
    assert obs_mod.classify_observation(
        "e1", first_observed_at={"e1": "garbage-not-a-timestamp"}, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


def test_classify_observation_regression_lexicographic_bug_would_have_wrongly_promoted() -> None:
    """THE regression case: the old lexicographic compare's dangerous direction.

    baseline_started_at = "2026-08-19T09:00:00-04:00" (13:00 UTC).
    observed             = "2026-08-19T10:00:00Z"      (10:00 UTC) -- BEFORE
    the true baseline start (10:00 < 13:00), so the honest answer is
    retrospective_seed.

    The OLD code compared ``observed_at < started_at`` as raw strings:
    ``"2026-08-19T10:00:00Z" < "2026-08-19T09:00:00-04:00"`` is FALSE
    ('1' > '0' at the hour digit), so the old lower-bound rejection branch
    would NEVER have fired -- it would have (wrongly) let this event proceed
    toward live_forward, exactly the "incorrectly promoting retrospective
    seed evidence" failure the day-2 mandate names. The new instant-based
    compare correctly rejects it.
    """
    baseline = {"baseline_started_at": "2026-08-19T09:00:00-04:00"}
    observed = {"e1": "2026-08-19T10:00:00Z"}
    # Sanity check the bug is real: the raw strings compare backwards.
    assert not (observed["e1"] < baseline["baseline_started_at"])
    assert obs_mod.classify_observation(
        "e1", first_observed_at=observed, baseline=baseline,
    ) == OBSERVATION_RETROSPECTIVE_SEED


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


def test_measured_lead_days_uses_utc_date_not_offset_local_date() -> None:
    """Review round 2, S2 regression pin.

    The LAB side used to slice ``[:10]`` off the raw string, reading the
    OFFSET-LOCAL calendar date. ``"2026-08-19T20:00:00-05:00"`` is
    ``2026-08-20T01:00:00Z`` -- the TRUE UTC date is the 20th, not the 19th a
    ``[:10]`` slice reads. The Prophet side legitimately stays a bare-date
    slice (see ``measured_lead_days``'s own docstring for the asymmetry).
    """
    raw = "2026-08-19T20:00:00-05:00"
    assert raw[:10] == "2026-08-19", "sanity: the old buggy slice reads the 19th"
    lead = obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD,
        first_observed_at=raw,  # true UTC date = 2026-08-20
        prophet_anchor_at="2026-08-21",
    )
    # True UTC lab date = 2026-08-20 -> lead = 1. The old buggy slice would
    # have read lab_date=2026-08-19 -> lead = 2 (WRONG, off by one day).
    assert lead == 1


def test_measured_lead_days_naive_first_observed_at_returns_none() -> None:
    # first_observed_at is contracted to always be a full spool instant; a
    # naive value reaching here fails closed the same as an unparseable one.
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD,
        first_observed_at="2026-08-19T20:00:00",  # naive
        prophet_anchor_at="2026-08-21",
    ) is None


# review B1: never a negative/zero lead — an anchor that does not POSTDATE
# the Lab's observation is a different fact entirely, not "behind by N days".
def test_measured_lead_days_none_when_anchor_does_not_postdate_observation() -> None:
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD,
        first_observed_at="2026-08-18T14:00:00Z", prophet_anchor_at="2026-08-10",
    ) is None
    assert obs_mod.measured_lead_days(
        OBSERVATION_LIVE_FORWARD,
        first_observed_at="2026-08-18T14:00:00Z", prophet_anchor_at="2026-08-18",
    ) is None  # same-day is not a lead either


# ---------------------------------------------------------------------------
# review S8 — a fixture event built from a REAL EntryEvent, full field width
# ---------------------------------------------------------------------------
def test_full_width_entry_event_round_trips_through_the_reader(
    roots: LabRoots, tmp_path: Path,
) -> None:
    """One event built via the real ``EntryEvent``/``build_radar_native_event``
    constructor (all 21 ``EVENT_FIELDS``, auto-derived ``event_id`` and
    provenance included) rather than a hand-trimmed dict, wrapped in a real
    envelope, and read back through :func:`engine.prophet_lab.sources.read_radar_envelopes`
    + :func:`engine.prophet_lab.boards.build_c1_board` — pinning that the
    reader tolerates the FULL record shape, not just the subset this test
    module's other hand-authored fixtures happen to populate.
    """
    event = build_radar_native_event(
        detector_id=C1_DETECTOR_ID,
        detector_spec_hash="full-width-fixture-hash",
        ticker="III",
        family="radar_1d_live_washout",
        subtype="live_k_lt_20",
        signal_ts="2026-08-18T14:30:00Z",
        market_session="2026-08-18",
        bar_state="confirmed",
        finality_basis="test_fixture_full_width",
        signal_known_ts="2026-08-18T14:30:05Z",
    )
    event_dict = event.to_dict()
    assert len(event_dict) == 21  # full EVENT_FIELDS width, nothing trimmed

    envelope = {
        "schema": SCHEMA_ENTRY_RADAR_EVENTS,
        "pass_ts": "2026-08-18T14:30:00Z",
        "pass_id": "entry_radar_pack",
        "pack": {"as_of": "2026-08-18", "pack_hash": "full-width-pack-hash"},
        "transitions": [],
        "events": [event_dict],
        "health": {},
    }
    spool_dir = tmp_path / "full_width_spool" / "live_flow" / "entry_radar_events" / "2026-08-18"
    spool_dir.mkdir(parents=True)
    import json as _json  # noqa: PLC0415 — fixture-local, avoids a module-level import just for this

    (spool_dir / "pass-143000-entry_radar_pack.json").write_text(
        _json.dumps(envelope), encoding="utf-8",
    )

    ledger = LiveEpisodeLedger(tmp_path / "full_width_state")
    ledger._episodes["ep-iii-c1"] = LiveEpisode(  # noqa: SLF001 — fixture setup
        episode_id="ep-iii-c1", ticker="III", detector_id=C1_DETECTOR_ID,
        detector_version=1, detector_spec_hash="full-width-fixture-hash",
        state="ARMED", market_session="2026-08-18",
        evidence_refs=(event_dict["event_id"],),
    )
    ledger.save()

    full_width_roots = replace(
        roots,
        radar_spool_dir=tmp_path / "full_width_spool",
        radar_state_dir=tmp_path / "full_width_state",
    )
    payload = build_lab_response(full_width_roots)
    c1_rows = {row["ticker"]: row for row in payload["boards"][BOARD_C1]}
    assert "III" in c1_rows
    expert = c1_rows["III"]["experts"][0]
    assert expert["event_id"] == event_dict["event_id"]
    assert expert["signal_known_ts"] == "2026-08-18T14:30:05Z"
