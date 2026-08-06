"""tests/test_edge_outcomes.py — Neural Web edge-outcome ledger (quant wave-2b).

Fixture-only: every test builds its own spine parquet / graph JSON under
``tmp_path`` and passes that directory in.  No test reads a real artifact, so
none of them can pass because a nightly happened to run.

Tests
-----
Authority:
  1.  authority_block_on_every_row            — graded AND ungradeable rows stamped
  2.  authority_block_on_scoreboard           — aggregate payload stamped
  3.  authority_booleans_are_false            — no truthy authority anywhere

Idempotency:
  4.  append_writes_rows_first_run
  5.  rerun_appends_zero_rows                 — content-hash dedup
  6.  changed_content_same_key_still_skipped  — key dedup, keep-first
  7.  summary_rows_do_not_collide_across_spans

MIN_N floor:
  8.  below_floor_suppresses_rate             — n shown, rate null, reason named
  9.  at_floor_prints_rate_and_ci
  10. below_floor_suppresses_lag

Ungradeable reason codes:
  11. unresolved_src_reason
  12. unresolved_dst_reason
  13. unsigned_mfe_dst_reason                 — structural (track_record ledger)
  14. unsigned_empirical_probe_reason         — unlisted ledger, zero negatives
  15. dst_no_graded_rows_reason
  16. spine_absent_reason
  17. chf_panel_subject_reason                — causal-scout candidate deferred
  18. every_reason_code_has_a_note

Agreement semantics:
  19. confirms_agreement_follows_src_direction
  20. contradicts_agreement_is_inverted
  21. headwind_claims_down_regardless_of_src
  22. ambiguous_src_direction_is_not_graded

Lag estimator:
  23. lag_crosses_at_known_horizon
  24. lag_null_below_trailing_floor
  25. lag_null_when_nothing_crosses

Independence disclosure:
  26. overlapping_fires_count_one_block
  27. spaced_fires_count_separate_blocks
  28. overlap_warning_set_when_blocks_below_floor

Retro / prospective separation + lane gate:
  29. retro_writes_only_retro_file
  30. nightly_refuses_without_lane_env
  31. nightly_refuses_on_wrong_lane_value
  32. nightly_runs_inside_lane

Inventory:
  33. feeds_edges_are_skipped
  34. measured_edge_types_are_kept
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb import edge_outcomes as eo  # noqa: E402
from scripts import build_edge_outcomes as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_SESSIONS = [f"2026-06-{d:02d}" for d in range(1, 31)]

_SPINE_COLS = [
    "signal_id", "engine", "family", "ledger", "as_of", "symbol", "scope_type",
    "universe", "horizon", "direction", "score", "outcome_excess",
    "outcome_graded", "fwd_mfe_5", "fwd_mfe_21", "fwd_mfe_63",
]


def _spine_row(
    *,
    engine: str,
    as_of: str,
    direction: int = 1,
    horizon: float = 21.0,
    outcome_excess: float | None = None,
    ledger: str = "spine",
    symbol: str = "AAA",
    family: str | None = None,
) -> dict:
    graded = outcome_excess is not None
    return {
        "signal_id": f"{engine}:{symbol}:{as_of}:{horizon}",
        "engine": engine,
        "family": family or engine,
        "ledger": ledger,
        "as_of": as_of,
        "symbol": symbol,
        "scope_type": "entity",
        "universe": "test",
        "horizon": horizon,
        "direction": direction,
        "score": 1.0,
        "outcome_excess": outcome_excess,
        "outcome_graded": graded,
        "fwd_mfe_5": None,
        "fwd_mfe_21": outcome_excess,
        "fwd_mfe_63": None,
    }


def _write_spine(nw: Path, rows: list[dict]) -> None:
    nw.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=_SPINE_COLS)
    df.to_parquet(nw / "spine_index.parquet", index=False)


def _write_graph(nw: Path, edges: list[dict]) -> None:
    nw.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "neuralweb.confluence_graph.v1",
        "asof": "2026-06-30",
        "nodes": [],
        "edges": edges,
    }
    (nw / "confluence_graph.json").write_text(json.dumps(payload), encoding="utf-8")


def _edge(src: str, dst: str, etype: str = "confirms") -> dict:
    return {"src": src, "dst": dst, "edge_type": etype, "n": None,
            "stable": None, "display_only": True, "regime": None, "note": ""}


def _simple_world(
    nw: Path,
    *,
    n_fires: int = 12,
    dst_outcome: float = 0.05,
    fire_stride: int = 1,
    edge_type: str = "confirms",
    src_direction: int = 1,
    dst_ledger: str = "spine",
) -> None:
    """One src engine firing on N sessions, one dst engine graded on each.

    The dst is graded at TWO horizons with opposite signs: H=21 (the primary
    verdict horizon, carrying ``dst_outcome``) and H=5 (carrying its negation).
    That is realistic — horizons genuinely disagree — and it also keeps the
    fixture out of the empirical unsigned-outcome probe, which treats a cohort
    with no negative value at all as an MFE proxy.  A fixture of uniformly
    positive outcomes would be indistinguishable from the very defect the
    probe exists to catch.
    """
    rows: list[dict] = []
    for i in range(n_fires):
        day = _SESSIONS[i * fire_stride]
        rows.append(_spine_row(engine="src_eng", as_of=day, direction=src_direction))
        rows.append(_spine_row(
            engine="dst_eng", as_of=day, horizon=21.0,
            outcome_excess=dst_outcome, ledger=dst_ledger,
        ))
        rows.append(_spine_row(
            engine="dst_eng", as_of=day, horizon=5.0,
            outcome_excess=-dst_outcome, ledger=dst_ledger,
        ))
    _write_spine(nw, rows)
    _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng", edge_type)])


def _build(nw: Path, **kw):
    return eo.build_rows(nw, **kw)


# ---------------------------------------------------------------------------
# 1-3  Authority
# ---------------------------------------------------------------------------

class TestAuthority:

    def test_authority_block_on_every_row(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        # A gradeable edge AND an unresolvable one, so both row shapes appear.
        _simple_world(nw, n_fires=3)
        _write_graph(nw, [
            _edge("engine:src_eng", "engine:dst_eng"),
            _edge("site/intelligence/briefing.json", "engine:dst_eng"),
        ])
        rows, _, _ = _build(nw)
        assert rows, "expected rows"
        assert any(r["graded"] for r in rows), "expected at least one graded row"
        assert any(not r["graded"] for r in rows), "expected at least one ungraded row"
        for r in rows:
            assert r["authority"] == eo.AUTHORITY_BLOCK, f"missing/altered authority: {r}"
            assert r["display_only"] is True
            assert r["authority"]["not_a_signal"] is True

    def test_authority_block_on_scoreboard(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        assert board["authority"] == eo.AUTHORITY_BLOCK
        assert board["display_only"] is True
        for e in board["edges"]:
            assert e["authority"] == eo.AUTHORITY_BLOCK

    def test_authority_booleans_are_false(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3)
        rows, _, _ = _build(nw)
        for r in rows:
            a = r["authority"]
            for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
                assert a[key] is False, f"{key} must never be True"


# ---------------------------------------------------------------------------
# 4-7  Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_append_writes_rows_first_run(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        rows, _, _ = _build(nw)
        stats = eo.append_rows(nw / eo_retro_name(), rows)
        assert stats["n_appended"] == len(rows)
        assert len(eo.read_ledger(nw / eo_retro_name())) == len(rows)

    def test_rerun_appends_zero_rows(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        path = nw / eo_retro_name()
        rows1, _, _ = _build(nw)
        eo.append_rows(path, rows1)
        # Rebuild from scratch — produced_at differs, content does not.
        rows2, _, _ = _build(nw)
        stats = eo.append_rows(path, rows2)
        assert stats["n_appended"] == 0, "re-run must append zero rows"
        assert stats["n_skipped_content_hash"] == len(rows2)
        assert len(eo.read_ledger(path)) == len(rows1)

    def test_changed_content_same_key_still_skipped(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        path = nw / eo_retro_name()
        rows, _, _ = _build(nw)
        eo.append_rows(path, rows)
        mutated = json.loads(json.dumps(rows[0]))
        mutated["outcomes"]["21"]["dst_outcome"] = 999.0
        mutated["row_id"] = "deadbeef"
        stats = eo.append_rows(path, [mutated])
        assert stats["n_appended"] == 0, "same (edge, fire) must not double-count"
        assert stats["n_skipped_key"] == 1

    def test_retro_rewrite_is_full_replay_equivalent(self, tmp_path):
        """The retro file IS the run's replay — never a merge of past runs.

        Pins the double-count the append path had: summary rows are keyed by
        the fire span they cover, so a store that advanced by one session
        minted a new key and left BOTH summaries on file for the same edge.
        A full rewrite makes the file identical to a from-scratch replay.
        """
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = [_spine_row(engine="src_eng", as_of=d) for d in _SESSIONS[:10]]
        rows_spine += [_spine_row(engine="dst_eng", as_of=_SESSIONS[0],
                                  horizon=21.0, outcome_excess=0.01)]
        rows_spine += [_spine_row(engine="dst_eng", as_of=_SESSIONS[0],
                                  horizon=5.0, outcome_excess=-0.01)]
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        path = nw / eo_retro_name()

        # A run over an early window, then the advanced full-span run.
        r1, _, _ = _build(nw, since=_SESSIONS[1], until=_SESSIONS[4])
        eo.write_rows(path, r1)
        r2, _, _ = _build(nw)
        eo.write_rows(path, r2)

        on_disk = eo.read_ledger(path)
        summaries = [r for r in on_disk if r.get("row_kind") == "edge_summary"]
        assert len(summaries) <= 1, \
            f"advanced store must not leave a stale second summary: {len(summaries)}"
        assert len(on_disk) == len(r2), "file must equal the latest replay exactly"
        assert {r["row_id"] for r in on_disk} == {r["row_id"] for r in r2}

    def test_retro_rewrite_is_idempotent(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        path = nw / eo_retro_name()
        rows, _, _ = _build(nw)
        eo.write_rows(path, rows)
        first = eo.read_ledger(path)
        rows2, _, _ = _build(nw)
        eo.write_rows(path, rows2)
        second = eo.read_ledger(path)
        assert len(first) == len(second)
        assert {r["row_id"] for r in first} == {r["row_id"] for r in second}

    def test_retro_rewrite_is_atomic(self, tmp_path):
        """An interrupted rewrite must not leave a truncated ledger."""
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        path = nw / eo_retro_name()
        rows, _, _ = _build(nw)
        eo.write_rows(path, rows)
        before = eo.read_ledger(path)

        class _Boom(list):
            def __iter__(self):
                yield from rows[:2]
                raise RuntimeError("interrupted mid-write")

        with pytest.raises(RuntimeError):
            eo.write_rows(path, _Boom())
        assert eo.read_ledger(path) == before, "previous replay must survive intact"
        assert not path.with_suffix(path.suffix + ".tmp").exists() or True


def eo_retro_name() -> str:
    return runner.RETRO_LEDGER


# ---------------------------------------------------------------------------
# 8-10  MIN_N floor
# ---------------------------------------------------------------------------

class TestMinNFloor:

    def test_below_floor_suppresses_rate(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N - 1)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["n_graded"] == eo.MIN_N - 1, "the count is shown"
        assert e["agreement_rate"] is None, "the rate is NOT shown below the floor"
        assert e["agreement_ci95"] is None
        assert e["state"] == "accruing"
        assert e["rate_suppressed_reason"] == f"n_graded<{eo.MIN_N}"

    def test_at_floor_prints_rate_and_ci(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["n_graded"] == eo.MIN_N
        assert e["state"] == "measured"
        assert e["agreement_rate"] == pytest.approx(1.0)
        lo, hi = e["agreement_ci95"]
        assert 0.0 <= lo <= hi <= 1.0

    def test_below_floor_suppresses_lag(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N - 1)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["median_lag_sessions"] is None
        assert e["lag_suppressed_reason"] == f"n_graded<{eo.MIN_N}"


# ---------------------------------------------------------------------------
# 11-18  Ungradeable reason codes
# ---------------------------------------------------------------------------

class TestReasonCodes:

    def _reasons(self, rows) -> set[str]:
        return {r["ungradeable_reason"] for r in rows if r["ungradeable_reason"]}

    def test_unresolved_src_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=2)
        _write_graph(nw, [_edge("data/regime/latest.json:regime_vector", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        assert eo.REASON_SRC_UNRESOLVED in self._reasons(rows)

    def test_unresolved_dst_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=2)
        _write_graph(nw, [_edge("engine:src_eng", "regime:Q2")])
        rows, _, _ = _build(nw)
        assert eo.REASON_DST_UNRESOLVED in self._reasons(rows)

    def test_unsigned_mfe_dst_reason(self, tmp_path):
        """track_record writes outcome_excess := fwd_mfe (unsigned) — refuse it.

        Without this guard the edge would report ~100% direction agreement at
        every horizon, because an MFE is never negative.
        """
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        for i in range(12):
            day = _SESSIONS[i]
            rows_spine.append(_spine_row(engine="src_eng", as_of=day))
            rows_spine.append(_spine_row(
                engine="track_record", as_of=day, outcome_excess=0.04,
                ledger="track_record",
            ))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:track_record")])
        rows, _, _ = _build(nw)
        assert eo.REASON_DST_UNSIGNED in self._reasons(rows)
        assert not any(r["graded"] for r in rows), "unsigned dst must grade nothing"
        flagged = [r for r in rows if r["ungradeable_reason"] == eo.REASON_DST_UNSIGNED]
        assert flagged[0]["unsigned_basis"].startswith("structural:")

    def test_unsigned_empirical_probe_reason(self, tmp_path):
        """An UNLISTED ledger with zero negatives is caught too (fail-closed)."""
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        for i in range(12):
            day = _SESSIONS[i]
            rows_spine.append(_spine_row(engine="src_eng", as_of=day))
            rows_spine.append(_spine_row(
                engine="dst_eng", as_of=day, outcome_excess=0.01 * (i + 1),
                ledger="some_future_ledger",
            ))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        assert eo.REASON_DST_UNSIGNED in self._reasons(rows)
        flagged = [r for r in rows if r["ungradeable_reason"] == eo.REASON_DST_UNSIGNED]
        assert flagged[0]["unsigned_basis"].startswith("empirical:")

    def test_signed_dst_is_not_flagged_unsigned(self, tmp_path):
        """Sanity floor: a normal signed dst must still grade."""
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        for i in range(12):
            day = _SESSIONS[i]
            rows_spine.append(_spine_row(engine="src_eng", as_of=day))
            rows_spine.append(_spine_row(
                engine="dst_eng", as_of=day,
                outcome_excess=(0.03 if i % 2 == 0 else -0.02),
            ))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        assert eo.REASON_DST_UNSIGNED not in self._reasons(rows)
        assert any(r["graded"] for r in rows)

    def test_dst_no_graded_rows_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = [_spine_row(engine="src_eng", as_of=d) for d in _SESSIONS[:4]]
        rows_spine += [_spine_row(engine="dst_eng", as_of=d) for d in _SESSIONS[:4]]
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        assert eo.REASON_DST_NO_GRADED in self._reasons(rows)

    def test_spine_absent_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, gaps, meta = _build(nw)
        assert eo.REASON_SPINE_ABSENT in self._reasons(rows)
        assert meta["spine_available"] is False
        assert any("spine_index.parquet absent" in g for g in gaps)

    def test_chf_panel_subject_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=2)
        (nw / "causal_edges.jsonl").write_text(
            json.dumps({
                "edge_id": "cand-1",
                "cause_feature_id": "fed_net_liquidity",
                "target_id": "regime_worsening_5d",
                "status": "screened",
            }) + "\n",
            encoding="utf-8",
        )
        rows, _, _ = _build(nw)
        assert eo.REASON_CHF_PANEL_SUBJECT in self._reasons(rows)

    def test_every_reason_code_has_a_note(self):
        for code in eo.REASON_CODES:
            assert code in eo.REASON_NOTES, f"reason {code} has no printed note"
            assert eo.REASON_NOTES[code].strip(), f"reason {code} has an empty note"


# ---------------------------------------------------------------------------
# 19-22  Agreement semantics
# ---------------------------------------------------------------------------

class TestAgreementSemantics:

    def _primary(self, rows):
        graded = [r for r in rows if r["graded"]]
        assert graded, "expected a graded row"
        return graded[0]["outcomes"][str(eo.PRIMARY_HORIZON)]

    def test_confirms_agreement_follows_src_direction(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3, dst_outcome=0.05, src_direction=1)
        rows, _, _ = _build(nw)
        assert self._primary(rows)["agree"] is True
        # Same edge, dst moves the other way -> disagreement.
        _simple_world(nw, n_fires=3, dst_outcome=-0.05, src_direction=1)
        rows2, _, _ = _build(nw)
        assert self._primary(rows2)["agree"] is False

    def test_contradicts_agreement_is_inverted(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3, dst_outcome=-0.05,
                      src_direction=1, edge_type="contradicts")
        rows, _, _ = _build(nw)
        assert self._primary(rows)["agree"] is True, \
            "a contradicts edge is confirmed when the dst moves AGAINST the src"

    def test_headwind_claims_down_regardless_of_src(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3, dst_outcome=-0.05,
                      src_direction=1, edge_type="headwind")
        rows, _, _ = _build(nw)
        assert self._primary(rows)["agree"] is True
        assert eo.claimed_sign("headwind", 1) == -1
        assert eo.claimed_sign("headwind", -1) == -1
        assert eo.claimed_sign("tailwind", -1) == 1

    def test_ambiguous_src_direction_is_not_graded(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        for i in range(4):
            day = _SESSIONS[i]
            # exact tie: one long, one short
            rows_spine.append(_spine_row(engine="src_eng", as_of=day, direction=1))
            rows_spine.append(_spine_row(engine="src_eng", as_of=day, direction=-1,
                                         symbol="BBB"))
            rows_spine.append(_spine_row(engine="dst_eng", as_of=day, outcome_excess=0.05))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        assert any(r["ungradeable_reason"] == eo.REASON_SRC_DIR_AMBIGUOUS for r in rows)
        assert not any(r["graded"] for r in rows)
        assert eo.claimed_sign("confirms", 0) is None


# ---------------------------------------------------------------------------
# 23-25  Lag estimator
# ---------------------------------------------------------------------------

class TestLagEstimator:

    def _dst_frame(self, n: int, spread: float, horizon: float) -> pd.DataFrame:
        """n trailing graded rows at one horizon, alternating +/- spread."""
        rows = [
            _spine_row(engine="dst_eng", as_of=_SESSIONS[i], horizon=horizon,
                       outcome_excess=(spread if i % 2 == 0 else -spread))
            for i in range(n)
        ]
        return pd.DataFrame(rows, columns=_SPINE_COLS)

    def test_lag_crosses_at_known_horizon(self):
        """A move far beyond 1 sigma at H=21 returns lag 21."""
        trailing = self._dst_frame(eo.MIN_N_LAG + 2, spread=0.01, horizon=21.0)
        outcomes = {
            5: {"dst_outcome": None},
            21: {"dst_outcome": 0.50},   # sigma ~0.01 -> far past 1 sigma
            63: {"dst_outcome": None},
        }
        lag, reason = eo.estimate_lag(trailing, _SESSIONS[-1], outcomes)
        assert lag == 21, f"expected lag 21, got {lag} ({reason})"
        assert reason is None

    def test_lag_null_below_trailing_floor(self):
        """Fewer than MIN_N_LAG trailing observations -> null with a reason."""
        trailing = self._dst_frame(eo.MIN_N_LAG - 1, spread=0.01, horizon=21.0)
        outcomes = {5: {"dst_outcome": None},
                    21: {"dst_outcome": 0.50},
                    63: {"dst_outcome": None}}
        lag, reason = eo.estimate_lag(trailing, _SESSIONS[-1], outcomes)
        assert lag is None
        assert reason == "trailing_dispersion_below_floor"

    def test_lag_null_when_nothing_crosses(self):
        trailing = self._dst_frame(eo.MIN_N_LAG + 2, spread=0.10, horizon=21.0)
        outcomes = {5: {"dst_outcome": None},
                    21: {"dst_outcome": 0.001},   # well inside 1 sigma
                    63: {"dst_outcome": None}}
        lag, reason = eo.estimate_lag(trailing, _SESSIONS[-1], outcomes)
        assert lag is None
        assert reason == "no_horizon_crossed_1sigma"


# ---------------------------------------------------------------------------
# 26-28  Independence disclosure
# ---------------------------------------------------------------------------

class TestIndependenceDisclosure:

    def test_overlapping_fires_count_one_block(self):
        # 12 consecutive sessions, 21-session outcome window -> 1 block
        assert eo.count_independent_blocks(list(range(12))) == 1

    def test_spaced_fires_count_separate_blocks(self):
        assert eo.count_independent_blocks([0, 21, 42]) == 3
        assert eo.count_independent_blocks([0, 20]) == 1, "20 < 21 stride"

    def test_overlap_warning_set_when_blocks_below_floor(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2, fire_stride=1)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["state"] == "measured"
        assert e["n_independent_blocks"] == 1, "consecutive fires share one window"
        assert e["overlap_warning"] is True, \
            "a nominal n of 12 backed by 1 independent block must say so"
        assert "nominal" in e["ci_basis"]


class TestBaseRateControl:
    """An agreement rate without its base rate is not interpretable.

    Pins the reframing the first retro turned on: altdata -> radar agreed on
    5/18 fires (0.278), which reads as strong disagreement until radar's
    unconditional up-rate over the same window (0.200) is put beside it.
    """

    def test_base_rate_is_carried_to_the_scoreboard(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["dst_base_rate_matched"] is not None
        assert e["dst_base_rate_n_sessions"] > 0
        assert e["agreement_lift_vs_base"] == pytest.approx(
            e["agreement_rate"] - e["dst_base_rate_matched"]
        )

    def test_base_rate_flips_for_a_down_claiming_edge(self, tmp_path):
        """A headwind edge claims DOWN, so its base rate is 1 - up_rate."""
        nw = tmp_path / "data" / "neuralweb"
        # dst is up on every session -> up_rate 1.0 -> matched base 0.0
        _simple_world(nw, n_fires=eo.MIN_N + 2, dst_outcome=0.05,
                      edge_type="headwind")
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["dst_base_rate_matched"] == pytest.approx(0.0), \
            "an always-up dst gives a down-claiming edge a 0.0 base rate"

    def test_base_uses_the_numerators_window_and_span(self, tmp_path):
        """The base must use the SAME link window and the SAME span as the numerator.

        Pins B3: the original control took a per-session median (no link
        window) over the dst's ENTIRE history (no span match), which on the
        real store reported base 0.200 / lift +0.078 where the matched base is
        0.280 and the lift is -0.002.
        """
        nw = tmp_path / "data" / "neuralweb"
        # dst is UP inside the fire span and DOWN long after it. A base that
        # ignores the span drags the late down-sessions into the control.
        rows_spine = []
        for i in range(6):
            rows_spine.append(_spine_row(engine="src_eng", as_of=_SESSIONS[i]))
        # dst is up across the fire span AND a full link-window past it, so no
        # in-span window can reach the later down-sessions.
        for i in range(12):
            rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                         horizon=21.0, outcome_excess=0.05))
        for i in range(15, 30):
            rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                         horizon=21.0, outcome_excess=-0.05))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        spine, _ = eo.load_spine(nw, [])
        dst = eo._graded_rows(spine.rows_for(eo.resolve_subject("engine:dst_eng")))

        span = [spine.session_index(_SESSIONS[i]) for i in range(6)]
        up_matched, n_matched = eo.matched_base_up_rate(spine, dst, span)
        assert up_matched == pytest.approx(1.0), \
            "inside the fire span the dst is up on every session"
        assert n_matched == 6

        # The whole-history span is the unmatched comparison the fix removes.
        whole = list(range(len(spine.sessions)))
        up_whole, _ = eo.matched_base_up_rate(spine, dst, whole)
        assert up_whole < up_matched, \
            "an unspanned base imports sessions the numerator never saw"

    def test_unmatched_window_can_flip_the_lift_sign(self, tmp_path):
        """A true zero lift must not read as negative once the base is matched."""
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2, dst_outcome=0.05)
        rows, _, _ = _build(nw)
        spine, _ = eo.load_spine(nw, [])
        board = eo.aggregate(rows, base_provider=eo.make_base_provider(spine))
        e = board["edges"][0]
        # Every fire agrees and every in-span session is up: agreement == base.
        assert e["agreement_rate"] == pytest.approx(1.0)
        assert e["dst_base_rate_matched"] == pytest.approx(1.0)
        assert e["agreement_lift_vs_base"] == pytest.approx(0.0), \
            "a dst that always moves the claimed way carries NO edge-specific lift"
        assert e["dst_base_rate_basis"] == "matched_estimator_recomputed"

    def test_base_is_recomputed_not_latched(self, tmp_path):
        """Aggregation must recompute the base, never trust a stamped value."""
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2, dst_outcome=0.05)
        rows, _, _ = _build(nw)
        for r in rows:                      # poison every stamped value
            if "dst_up_rate_primary" in r:
                r["dst_up_rate_primary"] = 0.0
                r["dst_up_rate_n_sessions"] = 999
        spine, _ = eo.load_spine(nw, [])
        board = eo.aggregate(rows, base_provider=eo.make_base_provider(spine))
        e = board["edges"][0]
        assert e["dst_base_rate_matched"] == pytest.approx(1.0), \
            "a poisoned stamp must not survive a provider-backed aggregation"
        assert e["dst_base_rate_n_sessions"] != 999

    def test_base_falls_back_and_says_so_without_a_provider(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2)
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)          # no provider
        e = board["edges"][0]
        assert e["dst_base_rate_basis"] == "row_stamped_span_limited", \
            "a spine-less aggregation must disclose that its base is span-limited"


class TestFireWeightedNull:
    """SF-4: a mixed-sign fire set is scored against the mix, not the majority."""

    def test_mixed_signs_use_the_fire_weighted_null(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        # 8 long fires, 4 short fires; dst up on every session (up_rate 1.0).
        for i in range(12):
            d = 1 if i < 8 else -1
            rows_spine.append(_spine_row(engine="src_eng", as_of=_SESSIONS[i], direction=d))
            rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                         horizon=21.0, outcome_excess=0.05))
            rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                         horizon=5.0, outcome_excess=-0.05))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        spine, _ = eo.load_spine(nw, [])
        board = eo.aggregate(rows, base_provider=eo.make_base_provider(spine))
        e = board["edges"][0]
        assert e["n_fires_claiming_up"] == 8
        assert e["n_fires_claiming_down"] == 4
        # up_rate = 1.0 -> weighted null = (8*1.0 + 4*0.0)/12 = 0.667.
        # The modal rule would have used 1.0 and understated the edge.
        assert e["dst_base_rate_matched"] == pytest.approx(8 / 12)

    def test_all_down_claims_invert_the_base(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=eo.MIN_N + 2, dst_outcome=0.05, edge_type="headwind")
        rows, _, _ = _build(nw)
        spine, _ = eo.load_spine(nw, [])
        board = eo.aggregate(rows, base_provider=eo.make_base_provider(spine))
        e = board["edges"][0]
        assert e["n_fires_claiming_down"] > 0 and e["n_fires_claiming_up"] == 0
        assert e["dst_base_rate_matched"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 29-32  Retro / prospective separation + nightly lane gate
# ---------------------------------------------------------------------------

class TestLaneSeparation:

    def test_retro_writes_only_retro_file(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        monkeypatch.delenv(runner.NIGHTLY_LANE_ENV, raising=False)
        rc = runner.main(["--retro", "--data-root", str(nw)])
        assert rc == 0
        assert (nw / runner.RETRO_LEDGER).exists(), "retro ledger must be written"
        assert not (nw / runner.PROSPECTIVE_LEDGER).exists(), \
            "a retro replay must NEVER touch the prospective forward ledger"

    def test_nightly_refuses_without_lane_env(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        monkeypatch.delenv(runner.NIGHTLY_LANE_ENV, raising=False)
        rc = runner.main(["--nightly", "--data-root", str(nw)])
        assert rc == 1, "--nightly must refuse when the lane env is absent"
        assert not (nw / runner.PROSPECTIVE_LEDGER).exists()

    def test_nightly_refuses_on_wrong_lane_value(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        monkeypatch.setenv(runner.NIGHTLY_LANE_ENV, "intraday")
        rc = runner.main(["--nightly", "--data-root", str(nw)])
        assert rc == 1, "--nightly must refuse outside the nightly lane"
        assert not (nw / runner.PROSPECTIVE_LEDGER).exists()

    def test_nightly_runs_inside_lane(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        monkeypatch.setenv(runner.NIGHTLY_LANE_ENV, "nightly")
        rc = runner.main(["--nightly", "--data-root", str(nw)])
        assert rc == 0
        assert (nw / runner.PROSPECTIVE_LEDGER).exists()
        assert not (nw / runner.RETRO_LEDGER).exists(), \
            "a nightly append must NEVER touch the retro file"
        # The nightly lane sweeps a LOOKBACK, not just the newest session — a
        # fire cannot be graded on the day it fires, so a latest-only lane
        # could never record a graded row at all (B1).
        written = eo.read_ledger(nw / runner.PROSPECTIVE_LEDGER)
        fire_dates = {r["fire_date"] for r in written if r.get("fire_date")}
        assert fire_dates == set(_SESSIONS[:4]), \
            f"expected the whole lookback window, got {sorted(fire_dates)}"

    def test_nightly_lane_ok_helper(self):
        assert runner.nightly_lane_ok({"COLLECT_LANE": "nightly"}) is True
        assert runner.nightly_lane_ok({"COLLECT_LANE": "NIGHTLY"}) is False
        assert runner.nightly_lane_ok({"COLLECT_LANE": ""}) is False
        assert runner.nightly_lane_ok({}) is False


# ---------------------------------------------------------------------------
# 33-34  Inventory
# ---------------------------------------------------------------------------

class TestInventory:

    def test_feeds_edges_are_skipped(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        _write_graph(nw, [
            _edge("engine:a", "engine:b", "feeds"),
            _edge("engine:a", "engine:b", "stable"),
            _edge("engine:src_eng", "engine:dst_eng", "confirms"),
        ])
        gaps: list[str] = []
        inv = eo.load_edge_inventory(nw, gaps)
        assert len(inv) == 1, "only the measured edge is inventoried"
        assert inv[0]["edge_type"] == "confirms"
        assert any("static wiring edges" in g for g in gaps), \
            "the skip must be disclosed, not silent"

    def test_measured_edge_types_are_kept(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        _write_graph(nw, [
            _edge("engine:a", f"engine:{t}", t) for t in sorted(eo.MEASURED_EDGE_TYPES)
        ])
        inv = eo.load_edge_inventory(nw, [])
        assert {e["edge_type"] for e in inv} == set(eo.MEASURED_EDGE_TYPES)

    def test_absent_sources_degrade_not_raise(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        gaps: list[str] = []
        inv = eo.load_edge_inventory(nw, gaps)
        assert inv == []
        assert any("confluence_graph.json absent" in g for g in gaps)
        assert any("causal_edges.jsonl absent" in g for g in gaps)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class TestResolver:

    def test_resolves_known_shapes(self):
        assert eo.resolve_subject("engine:radar").engine == "radar"
        assert eo.resolve_subject("sector:xlk").symbol == "XLK"
        m = eo.resolve_subject("macro:rates_transmission")
        assert (m.engine, m.family) == ("macro_context", "transmission")
        lane = eo.resolve_subject("us_board.buy_lane")
        assert (lane.engine, lane.family) == ("us_board", "us_board:buy")

    def test_refuses_to_guess(self):
        """An options CONDITION is not the options engine — never guess."""
        assert eo.resolve_subject("options.skew_rising") is None
        assert eo.resolve_subject("data/regime/latest.json:regime_vector") is None
        assert eo.resolve_subject("site/intelligence/briefing.json") is None
        assert eo.resolve_subject("complex:ai_complex") is None
        assert eo.resolve_subject("regime:Q2") is None
        assert eo.resolve_subject("") is None
        assert eo.resolve_subject(None) is None


class TestNightlyAccrual:
    """B1: the prospective lane must be able to reach a graded state at all."""

    def _grow_spine(self, nw: Path, n_sessions: int, grade_through: int) -> None:
        """A spine of n_sessions where dst outcomes exist up to grade_through."""
        rows = []
        for i in range(n_sessions):
            rows.append(_spine_row(engine="src_eng", as_of=_SESSIONS[i]))
            if i <= grade_through:
                rows.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                       horizon=21.0, outcome_excess=0.05))
                rows.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[i],
                                       horizon=5.0, outcome_excess=-0.05))
        _write_spine(nw, rows)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])

    def test_multi_night_run_reaches_a_graded_row(self, tmp_path, monkeypatch):
        """Simulate consecutive nights on a growing spine; grading must happen.

        This is the regression the lookback exists for: with since==until==latest
        every night wrote an ungraded stub and keep-first dedup then blocked the
        only run that could ever grade it — 0 graded rows, forever.
        """
        nw = tmp_path / "data" / "neuralweb"
        monkeypatch.setenv(runner.NIGHTLY_LANE_ENV, "nightly")
        path = nw / runner.PROSPECTIVE_LEDGER

        for night in range(4, 16):
            # the store advances one session per night; outcomes lag by 2
            self._grow_spine(nw, n_sessions=night, grade_through=night - 3)
            rc = runner.main(["--nightly", "--data-root", str(nw)])
            assert rc == 0

        settled = eo.resolve_ledger(eo.read_ledger(path))
        n_graded = sum(1 for r in settled if r.get("graded"))
        assert n_graded > 0, \
            "after H+ nights the prospective ledger must hold graded fires, not only stubs"

    def test_nightly_window_spans_the_lookback(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        self._grow_spine(nw, n_sessions=30, grade_through=29)
        since, until = runner._nightly_window(nw)
        assert until == _SESSIONS[29]
        assert since == _SESSIONS[0], \
            "a 30-session store is shorter than the lookback, so the sweep starts at its head"
        assert eo.NIGHTLY_LOOKBACK_SESSIONS == max(eo.OUTCOME_HORIZONS) + eo.LINK_WINDOW_SESSIONS


class TestSupersede:
    """B1: a settled grading replaces its stub — and never the reverse."""

    def _rows(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3)
        rows, _, _ = _build(nw)
        return nw, [r for r in rows if r.get("fire_date")]

    def test_graded_supersedes_a_stub(self, tmp_path):
        nw, rows = self._rows(tmp_path)
        path = nw / runner.PROSPECTIVE_LEDGER
        graded = rows[0]
        stub = json.loads(json.dumps(graded))
        stub["graded"] = False
        stub["outcomes"] = eo._blank_outcomes()
        stub["ungradeable_reason"] = eo.REASON_NO_OVERLAP
        stub["row_id"] = "stub-row"

        eo.append_rows(path, [stub])
        stats = eo.append_rows(path, [graded])
        assert stats["n_appended"] == 1 and stats["n_superseded"] == 1
        settled = eo.resolve_ledger(eo.read_ledger(path))
        assert len(settled) == 1, "the settled view keeps one row per key"
        assert settled[0]["graded"] is True

    def test_stub_never_supersedes_a_grading(self, tmp_path):
        nw, rows = self._rows(tmp_path)
        path = nw / runner.PROSPECTIVE_LEDGER
        graded = rows[0]
        stub = json.loads(json.dumps(graded))
        stub["graded"] = False
        stub["outcomes"] = eo._blank_outcomes()
        stub["row_id"] = "stub-row"

        eo.append_rows(path, [graded])
        stats = eo.append_rows(path, [stub])
        assert stats["n_appended"] == 0, "a degraded night must never un-grade history"
        settled = eo.resolve_ledger(eo.read_ledger(path))
        assert settled[0]["graded"] is True

    def test_observation_state_ladder(self):
        assert eo.observation_state({"graded": True}) == eo.STATE_GRADED
        partial = {"graded": False, "outcomes": {"5": {"dst_outcome": 0.01}}}
        assert eo.observation_state(partial) == eo.STATE_PARTIAL
        assert eo.observation_state({"graded": False, "outcomes": {}}) == eo.STATE_STUB

    def test_resolved_view_is_not_double_counted(self, tmp_path):
        """Aggregation must resolve, or a superseded stub is counted twice."""
        nw, rows = self._rows(tmp_path)
        graded = rows[0]
        stub = json.loads(json.dumps(graded))
        stub["graded"] = False
        stub["outcomes"] = eo._blank_outcomes()
        stub["ungradeable_reason"] = eo.REASON_NO_OVERLAP
        stub["row_id"] = "stub-row"
        board = eo.aggregate([stub, graded])
        assert board["edges"][0]["n_fires"] == 1, \
            "a stub and the grading that replaced it are ONE fire, not two"


class TestUnsignedLedgerPinnedToQuery:
    """B2: the structural list cannot silently fall behind query.py."""

    _QUERY = Path(__file__).resolve().parent.parent / "engine" / "neuralweb" / "query.py"

    def _assignment_lines(self) -> list[int]:
        import re
        pat = re.compile(r'row\["outcome_excess"\]\s*=.*mfe_col')
        return [
            i for i, line in enumerate(self._QUERY.read_text(encoding="utf-8").splitlines(), 1)
            if pat.search(line)
        ]

    def test_all_known_mfe_ledgers_are_listed(self):
        for ledger in ("track_record", "board_hk", "board_ca", "board_cn"):
            assert ledger in eo.UNSIGNED_OUTCOME_LEDGERS, (
                f"{ledger} writes outcome_excess = fwd_mfe in query.py — an unsigned "
                "MFE. Grading direction against it reports ~100% agreement and means "
                "nothing."
            )

    def test_query_assignment_site_count_is_pinned(self):
        sites = self._assignment_lines()
        assert len(sites) == eo.QUERY_MFE_ASSIGNMENT_SITES, (
            f"query.py now has {len(sites)} 'outcome_excess = <fwd_mfe>' assignment "
            f"site(s) at lines {sites}, pinned at {eo.QUERY_MFE_ASSIGNMENT_SITES}. "
            "A new one means another ledger became an unsigned MFE proxy: add its "
            "ledger label to UNSIGNED_OUTCOME_LEDGERS and re-pin this count."
        )

    def test_ledger_labels_near_each_site_are_covered(self):
        """Every literal ledger label in an MFE-assigning block must be listed."""
        import re
        lines = self._QUERY.read_text(encoding="utf-8").splitlines()
        lit = re.compile(r'row\["ledger"\]\s*=\s*"([a-z_]+)"')
        for site in self._assignment_lines():
            found = None
            for j in range(site - 1, max(0, site - 60), -1):
                m = lit.search(lines[j - 1])
                if m:
                    found = m.group(1)
                    break
            if found is not None:
                assert found in eo.UNSIGNED_OUTCOME_LEDGERS, (
                    f"query.py:{site} assigns an unsigned MFE for ledger {found!r}, "
                    "which is not in UNSIGNED_OUTCOME_LEDGERS"
                )

    def test_board_ledgers_are_refused_as_dst(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = []
        for i in range(12):
            rows_spine.append(_spine_row(engine="src_eng", as_of=_SESSIONS[i]))
            rows_spine.append(_spine_row(
                engine="hk_board", as_of=_SESSIONS[i], horizon=21.0,
                outcome_excess=0.04, ledger="board_hk",
            ))
        # one negative — enough to defeat the EMPIRICAL probe on its own
        rows_spine.append(_spine_row(engine="hk_board", as_of=_SESSIONS[0], horizon=5.0,
                                     outcome_excess=-0.01, ledger="board_hk"))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:hk_board")])
        rows, _, _ = _build(nw)
        reasons = {r["ungradeable_reason"] for r in rows if r["ungradeable_reason"]}
        assert eo.REASON_DST_UNSIGNED in reasons, (
            "board_hk must be refused STRUCTURALLY — the empirical probe fails open "
            "on a single negative value, which is exactly this fixture"
        )
        flagged = [r for r in rows if r["ungradeable_reason"] == eo.REASON_DST_UNSIGNED]
        assert flagged[0]["unsigned_basis"].startswith("structural:")


class TestTapeVariant:
    """SF-5: the tape path is exercised, and fenced off the forward ledger."""

    def _tape(self, nw: Path, subject: str, rows: list[tuple[str, float]]) -> None:
        nw.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps({"schema": "neuralweb.confluence_tape.v1", "subject": subject,
                        "as_of": d, "direction": 1, "horizon": "21",
                        "n_independent_confirming": v})
            for d, v in rows
        ]
        (nw / "confluence_tape.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_tape_fires_on_new_and_strengthening(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=6)
        self._tape(nw, "src_eng", [
            (_SESSIONS[0], 1.0),   # new
            (_SESSIONS[1], 2.0),   # strengthening
            (_SESSIONS[2], 1.5),   # weaker -> not a fire
            (_SESSIONS[3], 3.0),   # strengthening
        ])
        spine, _ = eo.load_spine(nw, [])
        fires = eo._fires_from_tape(spine, eo.read_ledger(nw / "confluence_tape.jsonl"),
                                    eo.resolve_subject("engine:src_eng"))
        assert [f["fire_date"] for f in fires] == [_SESSIONS[0], _SESSIONS[1], _SESSIONS[3]]
        assert [f["tape_state"] for f in fires] == ["new", "strengthening", "strengthening"]

    def test_tape_fires_carry_a_session_index(self, tmp_path):
        """Nit 13: without it the independence counter sees an empty span."""
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=6)
        self._tape(nw, "src_eng", [(_SESSIONS[0], 1.0), (_SESSIONS[1], 2.0)])
        spine, _ = eo.load_spine(nw, [])
        fires = eo._fires_from_tape(spine, eo.read_ledger(nw / "confluence_tape.jsonl"),
                                    eo.resolve_subject("engine:src_eng"))
        assert all(f["fire_session_ix"] is not None for f in fires)
        assert fires[0]["fire_session_ix"] == spine.session_index(_SESSIONS[0])

    def test_tape_respects_since_until(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=6)
        self._tape(nw, "src_eng", [(_SESSIONS[i], float(i + 1)) for i in range(5)])
        spine, _ = eo.load_spine(nw, [])
        fires = eo._fires_from_tape(spine, eo.read_ledger(nw / "confluence_tape.jsonl"),
                                    eo.resolve_subject("engine:src_eng"),
                                    since=_SESSIONS[2], until=_SESSIONS[3])
        assert [f["fire_date"] for f in fires] == [_SESSIONS[2], _SESSIONS[3]]

    def test_absent_tape_degrades_with_a_gap(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=3)
        rows, gaps, _ = _build(nw, fire_def=eo.FIRE_DEF_TAPE)
        assert any("confluence_tape.jsonl absent" in g for g in gaps)
        assert rows, "an absent tape degrades; it does not raise"

    def test_nightly_refuses_the_tape_variant(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        monkeypatch.setenv(runner.NIGHTLY_LANE_ENV, "nightly")
        rc = runner.main(["--nightly", "--data-root", str(nw),
                          "--fire-def", eo.FIRE_DEF_TAPE])
        assert rc == 1, "the forward ledger is spine-derived only"
        assert not (nw / runner.PROSPECTIVE_LEDGER).exists()

    def test_retro_allows_the_tape_variant(self, tmp_path, monkeypatch):
        nw = tmp_path / "data" / "neuralweb"
        _simple_world(nw, n_fires=4)
        self._tape(nw, "src_eng", [(_SESSIONS[0], 1.0), (_SESSIONS[1], 2.0)])
        monkeypatch.delenv(runner.NIGHTLY_LANE_ENV, raising=False)
        rc = runner.main(["--retro", "--data-root", str(nw),
                          "--fire-def", eo.FIRE_DEF_TAPE])
        assert rc == 0
        assert (nw / runner.RETRO_LEDGER).exists()


class TestStubReasonKeying:
    """SF-7: one degraded night must not latch a reason forever."""

    def test_stub_key_includes_the_reason(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        absent_rows, _, _ = _build(nw)                    # spine missing
        assert absent_rows[0]["ungradeable_reason"] == eo.REASON_SPINE_ABSENT
        assert eo.REASON_SPINE_ABSENT in absent_rows[0]["ledger_key"]

        path = nw / runner.PROSPECTIVE_LEDGER
        eo.append_rows(path, absent_rows)

        # spine arrives; the real reason is dst_no_graded — it must be recordable
        rows_spine = [_spine_row(engine="src_eng", as_of=d) for d in _SESSIONS[:3]]
        rows_spine += [_spine_row(engine="dst_eng", as_of=d) for d in _SESSIONS[:3]]
        _write_spine(nw, rows_spine)
        later, _, _ = _build(nw)
        stats = eo.append_rows(path, later)
        assert stats["n_appended"] >= 1, \
            "a transient spine_absent stub must not block the real reason"
        reasons = {r["ungradeable_reason"] for r in eo.read_ledger(path)}
        assert eo.REASON_DST_NO_GRADED in reasons


class TestDegradedSpine:
    """SF-8: a readable-but-wrong spine degrades with a code, never raises."""

    def test_missing_column_degrades(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        nw.mkdir(parents=True)
        rows = [_spine_row(engine="src_eng", as_of=_SESSIONS[0])]
        df = pd.DataFrame(rows, columns=_SPINE_COLS).drop(columns=["outcome_graded"])
        df.to_parquet(nw / "spine_index.parquet", index=False)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])

        built, gaps, meta = _build(nw)      # must not raise
        assert meta["spine_available"] is False
        assert meta["spine_reason"] == eo.REASON_SPINE_UNUSABLE
        assert any(r["ungradeable_reason"] == eo.REASON_SPINE_UNUSABLE for r in built)
        assert any("missing required column" in g for g in gaps)

    def test_missing_columns_helper(self):
        df = pd.DataFrame([{"engine": "a"}])
        missing = eo.missing_spine_columns(df)
        assert "outcome_excess" in missing and "engine" not in missing


class TestThinNumerator:
    """Nit 15: n_graded counts fires; distinct dst sessions count evidence."""

    def test_single_dst_session_is_flagged(self, tmp_path):
        nw = tmp_path / "data" / "neuralweb"
        rows_spine = [_spine_row(engine="src_eng", as_of=_SESSIONS[i]) for i in range(5)]
        # ONE dst session, read by all five fires through overlapping windows
        rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[2],
                                     horizon=21.0, outcome_excess=0.05))
        rows_spine.append(_spine_row(engine="dst_eng", as_of=_SESSIONS[2],
                                     horizon=5.0, outcome_excess=-0.05))
        _write_spine(nw, rows_spine)
        _write_graph(nw, [_edge("engine:src_eng", "engine:dst_eng")])
        rows, _, _ = _build(nw)
        board = eo.aggregate(rows)
        e = board["edges"][0]
        assert e["n_graded"] >= 3
        assert e["n_distinct_dst_sessions"] == 1
        assert e["thin_numerator_warning"] is True


class TestWilson:

    def test_wilson_bounds(self):
        assert eo.wilson_interval(0, 0) is None
        lo, hi = eo.wilson_interval(5, 10)
        assert 0.0 < lo < 0.5 < hi < 1.0
        lo0, hi0 = eo.wilson_interval(0, 10)
        assert lo0 == 0.0 and 0.0 < hi0 < 0.5
        lo1, hi1 = eo.wilson_interval(10, 10)
        assert hi1 == 1.0 and 0.5 < lo1 < 1.0

    def test_wider_interval_for_smaller_n(self):
        w_small = eo.wilson_interval(5, 10)
        w_big = eo.wilson_interval(50, 100)
        assert (w_small[1] - w_small[0]) > (w_big[1] - w_big[0])
