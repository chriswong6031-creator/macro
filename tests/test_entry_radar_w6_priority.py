"""Live Entry Radar W6 — RP1 Research Priority adversarial battery."""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import detectors as dt
from engine.entry_radar import live_eval as le
from engine.entry_radar import research_priority as rp
from engine.entry_radar.c5_adapter import C5_DETECTOR_ID, c5_spec_hash
from engine.entry_radar.challengers import c1_spec_hash, c2_spec_hash, c4_spec_hash
from engine.entry_radar.four_hour import c3_spec_hash
from engine.entry_radar.g0_adapter import G0_DETECTOR_ID, g0_spec_hash
from tests.test_entry_radar_w4_live import et_now, one_pass, quote_book, recovery_tape
from tests.test_entry_radar_w4_pack import NEXT_SESSION, build

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / "engine" / "entry_radar"
NOW = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
COMPUTED = rp.iso(NOW)

PINNED_SPEC_HASHES = {
    "G0": ("9be89a8acc8b905c", g0_spec_hash),
    "C1": ("f0bbd6cf3a6e2339", c1_spec_hash),
    "C2": ("d8ba60a25cfa7400", c2_spec_hash),
    "C3": ("d54dc1e55c4261c8", c3_spec_hash),
    "C4": ("dce21ac680233ee2", c4_spec_hash),
    "C5": ("13dec66345a0376c", c5_spec_hash),
}


def _closes(*, last: float, n: int = 180, step: float = 0.2) -> list[float]:
    start = last - step * (n - 1)
    return [start + step * i for i in range(n)]


def _ep(ticker: str, detector: str, *, closes=None, last=100.0, k=12.0,
        variant=None, state="CANDIDATE", extra=None, measures=None,
        availability="confirmed", history_freshness="confirmed",
        name_state="evaluated", name_reasons=(), atr=2.0, sampled=None,
        low=None, d=18.0, hist=-0.05, **kwargs) -> rp.EpisodeInput:
    series = list(closes) if closes is not None else _closes(last=last)
    sampled_close = last if sampled is None else sampled
    running_low = last * 0.94 if low is None else low
    meas = measures if measures is not None else rp.measures_from_history(
        series, atr=atr, sampled_close=sampled_close,
        running_sampled_low=running_low, k=k, d=d, hist=hist)
    if extra:
        meas = dict(meas)
        meas.update(extra)
    return rp.EpisodeInput(
        ticker=ticker, detector_id=detector, variant=variant, state=state,
        first_armed_at=kwargs.get("first_armed_at", "2026-08-17T14:00:00Z"),
        candidate_at=kwargs.get("candidate_at", "2026-08-17T14:00:00Z"),
        last_observed_at=kwargs.get("last_observed_at", "2026-08-17T14:55:00Z"),
        known_at=kwargs.get("known_at", "2026-08-17T14:55:00Z"),
        availability=availability, history_freshness=history_freshness,
        name_state=name_state, name_reasons=tuple(name_reasons),
        evidence_refs=("pack:abc",), pack_hash="abc",
        measures=meas, extra=dict(kwargs.get("blob") or {}),
    )


def _board(episodes, *, cycle_state="live"):
    return rp.assign(episodes, computed_at=COMPUTED, cycle_state=cycle_state)


def _ranked(board):
    return [e for e in board["episodes"] if e["abstention"] is None]


def test_same_frozen_input_twice_is_byte_identical():
    eps = [_ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=110),
           _ep("BBB", "C2_1D_TURN@1", last=90, variant="c2a_kd_cross")]
    a = json.dumps(_board(eps), sort_keys=True, default=str)
    b = json.dumps(_board(eps), sort_keys=True, default=str)
    assert a == b


def test_input_order_does_not_change_priority_or_ordinal():
    eps = [_ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=120),
           _ep("BBB", "C1_1D_LIVE_WASHOUT@1", last=80),
           _ep("CCC", "C2_1D_TURN@1", last=100, variant="c2a_kd_cross")]
    forward = _ranked(_board(eps))
    backward = _ranked(_board(list(reversed(eps))))

    def key(e):
        return (e["ticker"], e["detector_id"], e.get("variant") or "")

    assert {key(e): (e["priority_value"], e["priority_index"], e["ordinal"]) for e in forward} == \
        {key(e): (e["priority_value"], e["priority_index"], e["ordinal"]) for e in backward}


def test_ticker_permutation_preserves_rank_relationships():
    shared = dict(last=105.0, k=11.0)
    orig = {e["ticker"]: e["ordinal"] for e in _ranked(_board([
        _ep("NVDA", "C1_1D_LIVE_WASHOUT@1", **shared),
        _ep("TSLA", "C1_1D_LIVE_WASHOUT@1", last=70.0, k=8.0),
    ]))}
    perm = {e["ticker"]: e["ordinal"] for e in _ranked(_board([
        _ep("XXXX", "C1_1D_LIVE_WASHOUT@1", **shared),
        _ep("YYYY", "C1_1D_LIVE_WASHOUT@1", last=70.0, k=8.0),
    ]))}
    assert orig["NVDA"] == perm["XXXX"]
    assert orig["TSLA"] == perm["YYYY"]


def test_identical_measures_share_an_ordinal_regardless_of_ticker():
    ranked = _ranked(_board([
        _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100.0, k=12.0),
        _ep("ZZZ", "C1_1D_LIVE_WASHOUT@1", last=100.0, k=12.0),
    ]))
    assert ranked[0]["ordinal"] == ranked[1]["ordinal"]
    assert ranked[0]["priority_index"] == ranked[1]["priority_index"]
    assert ranked[0]["priority_value"] == ranked[1]["priority_value"]


def test_ordinal_is_competition_rank_of_canonical_priority_value():
    """UI rounding is presentation.  Ordinal uses the same canonical value."""
    eps = [
        _ep(f"T{i:02d}", "C1_1D_LIVE_WASHOUT@1",
            last=80.0 + i, hist=-0.50 + 0.05 * i)
        for i in range(11)
    ]
    ranked = _ranked(_board(eps))
    by_ticker = {e["ticker"]: e for e in ranked}
    unique = sorted(by_ticker)
    values = [by_ticker[t]["priority_value"] for t in unique]
    expected = rp._competition_ordinals(values)
    for ticker, ordinal in zip(unique, expected):
        row = by_ticker[ticker]
        assert row["ordinal"] == ordinal
        assert row["priority_index"] == round(row["priority_value"])
    buckets: dict[int, list[dict]] = {}
    for ticker in unique:
        row = by_ticker[ticker]
        buckets.setdefault(row["priority_index"], []).append(row)
    for rows in buckets.values():
        for left, right in zip(rows, rows[1:]):
            if left["priority_value"] != right["priority_value"]:
                assert left["ordinal"] != right["ordinal"]


def test_positive_affine_transform_of_a_submeasure_does_not_move_priority():
    """Percentile-then-combine is unit-invariant.  No outcome table consulted."""
    def make(xform):
        return [
            _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=120.0, hist=xform(-0.05)),
            _ep("BBB", "C1_1D_LIVE_WASHOUT@1", last=90.0, hist=xform(0.20)),
            _ep("CCC", "C1_1D_LIVE_WASHOUT@1", last=100.0, hist=xform(-0.40)),
        ]

    def payload(rows):
        return {e["ticker"]: (e["ordinal"], e["priority_value"], e["priority_index"])
                for e in rows}

    base = payload(_ranked(_board(make(lambda h: h))))
    scaled = payload(_ranked(_board(make(lambda h: 1000.0 * h + 3.0))))
    assert base == scaled


def test_clone_variants_do_not_inflate_the_name_snapshot_population():
    """Reference population is unique tickers.  Extra C2 clones stay extra rows."""
    wash_c1 = _ep("WASH", "C1_1D_LIVE_WASHOUT@1", last=110.0)
    wash_c2a = _ep("WASH", "C2_1D_TURN@1", last=110.0, variant="c2a_kd_cross")
    wash_clone = _ep("WASH", "C2_1D_TURN@1", last=110.0, variant="c2a_clone")
    other = _ep("OTHER", "C1_1D_LIVE_WASHOUT@1", last=80.0)
    thin = _board([wash_c1, wash_c2a, other])
    fat = _board([wash_c1, wash_c2a, wash_clone, other])
    assert thin["population_n"] == 2
    assert fat["population_n"] == 2

    def snapshot(board, ticker):
        rows = [e for e in _ranked(board) if e["ticker"] == ticker]
        values = {e["priority_value"] for e in rows}
        ordinals = {e["ordinal"] for e in rows}
        assert len(values) == 1 and len(ordinals) == 1
        return next(iter(values)), next(iter(ordinals))

    assert snapshot(thin, "OTHER") == snapshot(fat, "OTHER")
    assert snapshot(thin, "WASH") == snapshot(fat, "WASH")
    fat_keys = {(e["ticker"], e["detector_id"], e.get("variant"))
                for e in _ranked(fat)}
    assert ("WASH", "C2_1D_TURN@1", "c2a_kd_cross") in fat_keys
    assert ("WASH", "C2_1D_TURN@1", "c2a_clone") in fat_keys
    assert len(_ranked(fat)) == len(_ranked(thin)) + 1


def test_conflicting_g0_c2_snapshot_cannot_silently_pick_lexicographic_first():
    """Same-ticker G0/C2 with divergent hist fail closed.  C2 is lex-first.

    Old snapshot law sorted by (detector_id, variant) and took the first,
    so C2_1D_TURN@1 would silently become NVDA's canonical measures.
    """
    g0 = _ep("NVDA", "G0_GREY_DOT@1", last=110.0, hist=0.40)
    c2 = _ep("NVDA", "C2_1D_TURN@1", last=110.0, hist=-0.40,
             variant="c2a_kd_cross")
    other = _ep("OTHER", "C1_1D_LIVE_WASHOUT@1", last=80.0)
    assert c2.detector_id < g0.detector_id
    solo = _ranked(_board([other]))[0]
    for order in ([g0, c2, other], [c2, g0, other], [other, c2, g0]):
        board = _board(order)
        nvda = [e for e in board["episodes"] if e["ticker"] == "NVDA"]
        assert {e["detector_id"] for e in nvda} == {
            "G0_GREY_DOT@1", "C2_1D_TURN@1"}
        assert all(e["abstention"] == "snapshot_conflict" for e in nvda)
        assert all(e["priority_value"] is None and e["ordinal"] is None
                   and e["priority_index"] is None for e in nvda)
        ranked = _ranked(board)
        assert [e["ticker"] for e in ranked] == ["OTHER"]
        assert board["population_n"] == 1
        assert ranked[0]["priority_value"] == solo["priority_value"]
        assert ranked[0]["ordinal"] == 1


def test_outcome_injection_does_not_move_priority():
    base = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100)
    poisoned = _ep(
        "AAA", "C1_1D_LIVE_WASHOUT@1", last=100,
        extra={"mfe": 9e9, "mae": -9e9, "win_rate": 1.0, "false_start_rate": 0.0,
               "forward_return": 12.4, "q5_earliness": 13.43,
               "w5_outcome": "PASS_SHAPED"},
        blob={"future_return": 99, "profitability": 1},
    )
    a = _ranked(_board([base]))[0]
    b = _ranked(_board([poisoned]))[0]
    assert a["priority_index"] == b["priority_index"]
    dumped = json.dumps(b)
    assert "PASS_SHAPED" not in dumped
    assert "13.43" not in dumped


def test_hotness_does_not_raise_priority():
    cold = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100)
    hot = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100,
              extra={"hotness": 99, "hot_tier": 1, "rel_volume": 40})
    assert _ranked(_board([cold]))[0]["priority_index"] == \
        _ranked(_board([hot]))[0]["priority_index"]


def test_lobe_count_does_not_add_points():
    none = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100)
    badges = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100,
                 extra={"lobe_count": 5, "OPTIONS": 1, "DARK_POOL": 1,
                        "ETF_FLOW": 1, "THEME": 1, "SMART_MONEY": 1})
    assert _ranked(_board([none]))[0]["priority_index"] == \
        _ranked(_board([badges]))[0]["priority_index"]


def test_c4_depth_is_not_score_authority():
    shallow = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100)
    deep = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100,
               extra={"recovery_count": 2, "mtf_depth": 0.9, "c4_k": 1.0,
                      "washout_depth": -0.55})
    assert _ranked(_board([shallow]))[0]["priority_index"] == \
        _ranked(_board([deep]))[0]["priority_index"]


def test_g0_q5_earliness_is_not_a_bonus():
    board = _ranked(_board([
        _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100),
        _ep("AAA", "G0_GREY_DOT@1", last=100,
            extra={"q5_gap_sessions": 13.43, "earliness": 13.43}),
    ]))
    by_det = {e["detector_id"]: e["priority_index"] for e in board}
    assert by_det["C1_1D_LIVE_WASHOUT@1"] == by_det["G0_GREY_DOT@1"]


def test_lifecycle_fields_are_not_mutated_by_ranking():
    ep = _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100, state="ARMED",
             first_armed_at="stamp-A", candidate_at=None)
    before = (ep.state, ep.first_armed_at, ep.candidate_at)
    _board([ep])
    assert (ep.state, ep.first_armed_at, ep.candidate_at) == before


def test_multi_expert_same_ticker_stays_three_observations():
    board = _board([
        _ep("NVDA", "G0_GREY_DOT@1", last=110),
        _ep("NVDA", "C2_1D_TURN@1", last=110, variant="c2a_kd_cross"),
        _ep("NVDA", "C5_BOTTOM_WATCH@1", last=110),
    ])
    ranked = _ranked(board)
    keys = {(e["ticker"], e["detector_id"], e.get("variant")) for e in ranked}
    assert len(keys) == 3
    assert board["population_n"] == 1
    values = {e["priority_value"] for e in ranked}
    ordinals = {e["ordinal"] for e in ranked}
    assert len(values) == 1 and len(ordinals) == 1


def test_stale_is_unrankable_not_a_low_score():
    board = _board([
        _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=130),
        _ep("BBB", "C1_1D_LIVE_WASHOUT@1", last=130, availability="stale"),
    ])
    assert [e["ticker"] for e in _ranked(board)] == ["AAA"]
    bbb = next(e for e in board["episodes"] if e["ticker"] == "BBB")
    assert bbb["abstention"] == "stale_observation"
    assert bbb["priority_index"] is None


def test_missing_measures_are_not_silent_zeros():
    row = _board([_ep("AAA", "C1_1D_LIVE_WASHOUT@1", closes=[10.0, 10.1], k=None,
                      hist=None, sampled=None, low=None, atr=None)])["episodes"][0]
    assert row["abstention"] == "insufficient_coverage"
    assert row["priority_index"] is None
    structural = next(c for c in row["components"] if c["key"] == "structural_quality")
    assert "ret_20" in structural["unavailable"]


def test_unavailable_name_is_named_abstention():
    row = _board([_ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100, name_state="unavailable",
                      name_reasons=("basis_mismatch",))])["episodes"][0]
    assert row["abstention"] == "basis_mismatch"


def test_cycle_refusal_unranks_everyone():
    board = _board([
        _ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=120),
        _ep("BBB", "C1_1D_LIVE_WASHOUT@1", last=80),
    ], cycle_state="stale_pack")
    assert board["population_n"] == 0
    assert all(e["abstention"] == "cycle_refused" for e in board["episodes"])


def test_probability_language_is_rejected():
    board = _board([_ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=100)])
    assert board["status"] == "ACCRUING"
    assert rp.presentation_violations(board) == []


def test_no_llm_call_in_the_ranking_path():
    for name in ("research_priority.py", "live_eval.py"):
        tree = ast.parse((RADAR_DIR / name).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".")[0])
        for token in ("openai", "anthropic", "httpx", "requests", "litellm"):
            assert token not in imported, (name, token)


def test_existing_detector_spec_hashes_are_unchanged():
    for name, (expected, fn) in PINNED_SPEC_HASHES.items():
        assert fn() == expected, name


def test_priority_decomposes_into_named_inputs():
    row = _ranked(_board([_ep("AAA", "C1_1D_LIVE_WASHOUT@1", last=110)]))[0]
    keys = {c["key"] for c in row["components"]}
    assert keys == {name for name, _ in rp.DIMENSIONS}
    structural = next(c for c in row["components"] if c["key"] == "structural_quality")
    assert "ret_60" in structural["inputs"]
    assert row["policy_version"] == "RP1"


def test_deeper_drawdown_alone_does_not_win():
    board = _ranked(_board([
        _ep("LEAD", "C1_1D_LIVE_WASHOUT@1", last=150.0, k=18.0),
        _ep("WRECK", "C1_1D_LIVE_WASHOUT@1",
            closes=_closes(last=40.0, n=180, step=-0.5), k=2.0),
    ]))
    by = {e["ticker"]: e["ordinal"] for e in board}
    assert by["LEAD"] <= by["WRECK"]


@pytest.fixture(scope="module")
def pack():
    return build()


def _live_quotes(pack):
    now = et_now(32)
    return now, quote_book(pack, multiple=0.97, ts=now - timedelta(minutes=2))


def _recovery_name(pack, ticker: str = "WASH") -> le.NameResult:
    """Production C1/C2 path on the W4 recovery tape — the LIVE-10 shape."""
    daily = le.pack_daily_history(pack, ticker)
    builder = le.IncrementalObservationBuilder(
        ticker=ticker, daily=daily, session=NEXT_SESSION)
    path = builder.observations(recovery_tape(pack, ticker))
    c1 = ch.run_c1(path)
    c2 = ch.run_c2(path, c1.episode)
    return le.NameResult(
        ticker=ticker, state="evaluated", observations=tuple(path),
        runs=(c1, c2))


def _planted_c1(pack, ticker: str) -> le.NameResult:
    """A developing C1 row on a name whose recovery tape did not arm.

    Used for stale / unavailable / nightly-seam cases where the detector
    correctly did not fire, so the ranking seam still has an episode to score.
    """
    daily = le.pack_daily_history(pack, ticker)
    builder = le.IncrementalObservationBuilder(
        ticker=ticker, daily=daily, session=NEXT_SESSION)
    path = builder.observations(recovery_tape(pack, ticker))
    episode = ch.DetectorEpisode(ticker=ticker, detector_id=ch.C1_DETECTOR_ID)
    stamp = path[-1].observed_at if path else "2026-08-17T14:00:00Z"
    episode.first_armed_at = stamp
    episode.last_observed_at = stamp
    episode.state = dt.DetectorState.ARMED
    run = ch.C1Run(readings=(), episodes=(episode,), events=())
    return le.NameResult(
        ticker=ticker, state="evaluated", observations=tuple(path),
        runs=(run,))


def _priority_board(pack, names, *, health=None):
    # Recovery-tape observations run to the session close. Bind computed_at
    # at that close so the pass clock is not earlier than known_at.
    return le._research_priority_board(
        now=et_now(390), session=NEXT_SESSION, pack=pack,
        results=list(names), health=health or {"state": "live"})


def test_live_payload_carries_accruing_research_priority(tmp_path, pack):
    now, quotes = _live_quotes(pack)
    result = one_pass(pack, quotes, now=now, state_dir=tmp_path)
    board = result.payload["research_priority"]
    assert board["schema"] == rp.SCHEMA
    assert board["status"] == "ACCRUING"
    assert board["policy_version"] == "RP1"
    assert rp.presentation_violations(board) == []
    assert le.forward_knowledge_keys(result.payload) == []


def test_live_priority_does_not_write_the_ledger(tmp_path, pack):
    now, quotes = _live_quotes(pack)
    result = one_pass(pack, quotes, now=now, state_dir=tmp_path)
    if result.delta is not None:
        for episode in result.delta.episodes:
            assert episode.get("research_priority") is None
            assert episode.get("detector_score") is None
            assert episode.get("opportunity_score") is None


def test_live_pass_is_deterministic_with_priority_attached(tmp_path, pack):
    now, quotes = _live_quotes(pack)
    first = one_pass(pack, quotes, now=now, state_dir=tmp_path)
    second = one_pass(pack, quotes, now=now, state_dir=tmp_path)
    assert le.stable_content(first.payload) == le.stable_content(second.payload)
    assert first.payload["research_priority"]["episodes"] == \
        second.payload["research_priority"]["episodes"]


def test_recovery_tape_produces_rankable_c1_and_c2_rows(pack):
    wash = _recovery_name(pack, "WASH")
    board = _priority_board(pack, [wash])
    ranked = _ranked(board)
    assert ranked, "WASH recovery tape must produce rankable developing episodes"
    families = {e["detector_id"] for e in ranked}
    assert ch.C1_DETECTOR_ID in families
    assert ch.C2_DETECTOR_ID in families
    keys = {(e["ticker"], e["detector_id"], e.get("variant")) for e in ranked}
    assert len(keys) == len(ranked)
    assert board["population_n"] == 1
    assert len(ranked) > board["population_n"]
    assert len({e["priority_value"] for e in ranked}) == 1
    assert all(e["status"] == "ACCRUING" for e in ranked)
    assert all(e["policy_version"] == "RP1" for e in ranked)
    assert all(e["components"] for e in ranked)
    twice = _priority_board(pack, [wash])
    assert json.dumps(board, sort_keys=True, default=str) == \
        json.dumps(twice, sort_keys=True, default=str)
    assert rp.presentation_violations(board) == []
    assert le.forward_knowledge_keys({"research_priority": board}) == []


def test_live_multi_expert_rows_are_not_collapsed(pack):
    wash = _recovery_name(pack, "WASH")
    vshape = _recovery_name(pack, "VSHAPE")
    vshape = le.NameResult(
        ticker="VSHAPE", state="evaluated",
        observations=vshape.observations, runs=(),
        lanes={"nightly": {"g0": {
            "condition_met": True,
            "observed_at": vshape.observations[-1].observed_at,
        }, "c5": {
            "condition_met": True,
            "observed_at": vshape.observations[-1].observed_at,
        }}})
    board = _priority_board(pack, [wash, vshape])
    ranked = _ranked(board)
    keys = {(e["ticker"], e["detector_id"], e.get("variant")) for e in ranked}
    assert len(keys) == len(ranked)
    assert board["population_n"] == 2
    assert len(ranked) > 2
    assert any(e["ticker"] == "WASH" and e["detector_id"] == ch.C1_DETECTOR_ID
               for e in ranked)
    assert any(e["ticker"] == "WASH" and e["detector_id"] == ch.C2_DETECTOR_ID
               for e in ranked)
    assert any(e["ticker"] == "VSHAPE" and e["detector_id"] == G0_DETECTOR_ID
               for e in ranked)
    assert any(e["ticker"] == "VSHAPE" and e["detector_id"] == C5_DETECTOR_ID
               for e in ranked)


def test_stale_pack_name_is_unrankable_through_the_live_seam(pack):
    board = _priority_board(pack, [_planted_c1(pack, "STALE")])
    row = board["episodes"][0]
    assert row["abstention"] == "stale_observation"
    assert row["priority_index"] is None
    assert row["ordinal"] is None
    assert board["population_n"] == 0


def test_unavailable_observation_is_named_abstention_through_the_live_seam(pack):
    board = _priority_board(pack, [_planted_c1(pack, "SHORT")])
    row = board["episodes"][0]
    assert row["abstention"] == "unavailable_observation"
    assert row["priority_index"] is None


def test_degraded_health_from_other_names_does_not_unrank(pack):
    wash = _recovery_name(pack, "WASH")
    live = _priority_board(pack, [wash], health={"state": "live"})
    degraded = _priority_board(pack, [wash], health={"state": "degraded"})
    assert _ranked(live)
    assert [e["ordinal"] for e in _ranked(live)] == \
        [e["ordinal"] for e in _ranked(degraded)]
    assert [e["priority_index"] for e in _ranked(live)] == \
        [e["priority_index"] for e in _ranked(degraded)]


def test_research_priority_module_has_no_data_or_network_literals():
    tree = ast.parse((RADAR_DIR / "research_priority.py").read_text(encoding="utf-8"))
    blobs = [node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert not any(b.startswith("data/") or "://" in b for b in blobs)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    for token in ("socket", "urllib", "httpx", "requests"):
        assert token not in imported


def test_c3_live_seam_projects_priority_onto_the_c3_expert(tmp_path):
    from engine.entry_radar.four_hour import C3_DETECTOR_ID
    from tests.test_entry_radar_w4_c3_reader import (
        Recorder, late_wash_pack, reader_for, run_live_pass,
    )

    pack = late_wash_pack()
    result = run_live_pass(pack, tmp_path, reader=reader_for(Recorder(), tmp_path))
    board = result.payload["research_priority"]
    rows = [e for e in board["episodes"] if e.get("detector_id") == C3_DETECTOR_ID]
    assert rows, "C3 live seam must emit a C3 research_priority row"
    row = rows[0]
    assert row["ticker"] == "LATEWASH"
    assert row["policy_version"] == "RP1"
    assert row["status"] == "ACCRUING"
    if row["abstention"] is None:
        assert row["priority_value"] is not None
        assert row["ordinal"] is not None
        assert row["priority_index"] == round(row["priority_value"])
    assert rp.presentation_violations(board) == []
    assert le.forward_knowledge_keys({"research_priority": board}) == []
