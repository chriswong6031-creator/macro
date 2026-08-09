from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import cn_limit_alpha_ledger as ledger


def _calendar_file(tmp_path: Path) -> Path:
    path = (
        tmp_path
        / "data"
        / "cn_limit_alpha"
        / "reference"
        / "cn_exchange_calendar_2026.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "cn_exchange_calendar.v1",
                "year": 2026,
                "markets": ["SSE", "SZSE"],
                "weekends_closed": True,
                "closed_ranges": [
                    ["2026-01-01", "2026-01-03", "New Year"],
                    ["2026-02-15", "2026-02-23", "Spring Festival"],
                    ["2026-04-04", "2026-04-06", "Qingming Festival"],
                    ["2026-05-01", "2026-05-05", "Labour Day"],
                    ["2026-06-19", "2026-06-21", "Dragon Boat Festival"],
                    ["2026-09-25", "2026-09-27", "Mid-Autumn Festival"],
                    ["2026-10-01", "2026-10-07", "National Day"],
                ],
                "source_urls": [
                    "https://www.sse.com.cn/disclosure/announcement/general/example.shtml",
                    "https://investor.szse.cn/disclosure/notice/general/example.html",
                ],
                "source_notice_dates": ["2025-12-22", "2025-12-22"],
                "scope_note": "test fixture mirroring official 2026 closure ranges",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame(dates: list[str], opens: list[float], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": opens,
            "close": closes,
            "high": np.maximum(opens, closes),
            "low": np.minimum(opens, closes),
            "volume": [1000.0] * len(dates),
        },
        index=pd.to_datetime(dates),
    )


def _probability(
    ticker: str,
    *,
    model: str = "fixture-model:O1",
    selected: bool = True,
) -> dict[str, object]:
    return {
        "signal_date": "2026-08-07",
        "ticker": ticker,
        "model_version": model,
        "limit_definition": ledger.LIMIT_DEFINITION,
        "entry_rule": ledger.ENTRY_RULE,
        "entry_session": "2026-08-10",
        "selection_state": "selected_top20" if selected else "not_selected_no_fire",
    }


def test_calendar_exact_successor_and_fail_closed_year(tmp_path):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    assert calendar.next_session(date(2026, 8, 7)) == date(2026, 8, 10)
    assert calendar.next_session(date(2026, 9, 24)) == date(2026, 9, 28)
    assert calendar.offset(date(2026, 8, 10), 5) == date(2026, 8, 17)
    with pytest.raises(ledger.IntegrityError, match="attested only for 2026"):
        calendar.is_session(date(2027, 1, 4))
    with pytest.raises(ledger.IntegrityError, match="outside attested"):
        calendar.next_session(date(2026, 12, 31))


def test_canonical_shanghai_alias_and_board():
    assert ledger.canonical_ticker("600519.sh") == "600519.SS"
    assert ledger.canonical_ticker("600519.SS") == "600519.SS"
    assert ledger.board_from_ticker("688001.SH") == "star"
    assert ledger.board_from_ticker("300001.SZ") == "chinext"
    assert "entry_session" not in ledger.PROBABILITY_KEY


def test_frozen_packet_hashes_and_declared_model_versions():
    packet = ledger.load_frozen_packet()
    assert set(packet.model_versions) == set(packet.models)
    assert all(
        version.endswith(f":{model}")
        for model, version in packet.model_versions.items()
    )
    zero_features = {name: 0.0 for name in ledger.FEATURE_NAMES}
    scores = {
        name: ledger.score_frozen_model(packet, name, zero_features)
        for name in packet.models
    }
    assert all(0.0 < score < 1.0 for score in scores.values())


def test_frozen_model_hash_mutation_is_refused(tmp_path):
    receipt = json.loads(ledger.DEFAULT_RECEIPT_PATH.read_text(encoding="utf-8"))
    receipt["models"]["O1_five_axis"]["beta"][0] += 0.01
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ledger.IntegrityError, match="frozen model hash"):
        ledger.load_frozen_packet(path)


def test_latest_complete_session_rejects_partial_tail(tmp_path):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    common = ["2026-08-05", "2026-08-06", "2026-08-07"]
    frames = {
        "600519.SS": _frame(
            common + ["2026-08-10"], [10, 10, 10, 10], [10, 10, 10, 10]
        ),
        "000001.SZ": _frame(
            common + ["2026-08-10"], [10, 10, 10, 10], [10, 10, 10, 10]
        ),
        "000002.SZ": _frame(common, [10, 10, 10], [10, 10, 10]),
    }
    held = ledger.discover_latest_complete_session(
        frames, calendar, minimum_names=1, support_ratio=0.80
    )
    assert held.day == date(2026, 8, 7)
    assert held.minimum_required_support == 3
    advanced = ledger.discover_latest_complete_session(
        frames, calendar, minimum_names=1, support_ratio=0.66
    )
    assert advanced.day == date(2026, 8, 10)


def test_bootstrap_gate_idempotence_and_no_fabricated_grades(tmp_path, monkeypatch):
    calendar_path = _calendar_file(tmp_path)
    ledger_root = tmp_path / "ledger"
    monkeypatch.delenv("CN_LANE", raising=False)
    with pytest.raises(ledger.IntegrityError, match="CN_LANE=asia"):
        ledger.advance_forward_ledger(
            calendar_path=calendar_path,
            ledger_root=ledger_root,
            bootstrap_only=True,
        )
    assert not ledger_root.exists()

    monkeypatch.setenv("CN_LANE", "asia")
    first = ledger.advance_forward_ledger(
        calendar_path=calendar_path,
        ledger_root=ledger_root,
        bootstrap_only=True,
    )
    part = ledger_root / "probabilities" / "2026-08" / "2026-08-07.parquet"
    assert first.probability_rows_written == 5352
    assert first.grade_rows_written == 0
    assert part.exists()
    assert not (ledger_root / "grades").exists()
    first_hash = _hash(part)
    rows = ledger.read_partition(part, ledger.PROBABILITY_SCHEMA)
    packet = ledger.load_frozen_packet()
    assert len(rows) == 5352
    assert {row["model_version"] for row in rows} == set(packet.model_versions.values())

    second = ledger.advance_forward_ledger(
        calendar_path=calendar_path,
        ledger_root=ledger_root,
        bootstrap_only=True,
    )
    assert second.probability_rows_written == 0
    assert second.partitions_written == ()
    assert _hash(part) == first_hash


def test_bootstrap_keep_first_probability_contradiction(tmp_path, monkeypatch):
    calendar_path = _calendar_file(tmp_path)
    ledger_root = tmp_path / "ledger"
    monkeypatch.setenv("CN_LANE", "asia")
    ledger.advance_forward_ledger(
        calendar_path=calendar_path,
        ledger_root=ledger_root,
        bootstrap_only=True,
    )
    part = ledger_root / "probabilities" / "2026-08" / "2026-08-07.parquet"
    before = _hash(part)
    lines = ledger.DEFAULT_SEED_PATH.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["probability"] += 0.000001
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    mutated_seed = tmp_path / "mutated.jsonl"
    mutated_seed.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ledger.IntegrityError, match="keep-first"):
        ledger.advance_forward_ledger(
            seed_path=mutated_seed,
            calendar_path=calendar_path,
            ledger_root=ledger_root,
            bootstrap_only=True,
        )
    assert _hash(part) == before


def test_dynamic_advance_refuses_stale_st_membership_before_any_write(
    tmp_path, monkeypatch
):
    calendar_path = _calendar_file(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _frame(
        ["2026-08-07", "2026-08-10"],
        [10.0, 10.1],
        [10.0, 10.1],
    ).to_parquet(raw_dir / "600519.SS.parquet")
    st_path = tmp_path / "st.parquet"
    pd.DataFrame([{"ticker": "600000.SS", "asof": "2026-08-07"}]).to_parquet(
        st_path, index=False
    )
    ledger_root = tmp_path / "ledger"
    monkeypatch.setenv("CN_LANE", "asia")
    with pytest.raises(ledger.IntegrityError, match="not point-in-time attested"):
        ledger.advance_forward_ledger(
            raw_dir=raw_dir,
            st_path=st_path,
            calendar_path=calendar_path,
            ledger_root=ledger_root,
            minimum_support_names=1,
            support_ratio=1.0,
        )
    assert not ledger_root.exists()


def test_event_grades_full_population_execution_selected_only_and_unfilled_null(
    tmp_path,
):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    probabilities = [
        _probability("000001.SZ", selected=True),
        _probability("000002.SZ", selected=True),
        _probability("000003.SZ", selected=False),
    ]
    frames = {
        "000001.SZ": _frame(
            ["2026-08-07", "2026-08-10", "2026-08-11"],
            [10.0, 10.0, 10.5],
            [10.0, 11.0, 10.5],
        ),
        "000002.SZ": _frame(
            ["2026-08-07", "2026-08-10", "2026-08-11"],
            [10.0, 11.0, 10.7],
            [10.0, 11.0, 10.7],
        ),
        "000003.SZ": _frame(
            ["2026-08-07", "2026-08-11"],
            [10.0, 10.0],
            [10.0, 10.0],
        ),
    }
    grades = ledger.build_due_grades(
        probabilities, [], frames, calendar, date(2026, 8, 11)
    )
    events = [row for row in grades if row["grade_kind"] == "event"]
    executions = [row for row in grades if row["grade_kind"] == "execution_return"]
    assert len(events) == 3
    assert {row["ticker"] for row in events} == {"000001.SZ", "000002.SZ", "000003.SZ"}
    assert all(row["graded_at"] == "2026-08-11T15:00:00+08:00" for row in grades)
    assert all(
        len(row["source_hash"]) == 64
        and set(row["source_hash"]).issubset(set("0123456789abcdef"))
        for row in grades
    )
    assert len(executions) == 2
    assert all(row["horizon"] == "H1_next_open" for row in executions)
    queue = next(row for row in executions if row["ticker"] == "000002.SZ")
    assert queue["entry_fill_state"] == "queue_required_no_fill"
    assert queue["gross_return"] is None
    assert queue["net_return_bps_grid"] is None
    assert queue["book_contribution_return"] == 0.0
    missing_event = next(row for row in events if row["ticker"] == "000003.SZ")
    assert missing_event["event_state"] == "missing_halted_non_event"

    grade_part = tmp_path / "grades" / "2026-08" / "2026-08-11.parquet"
    ledger._atomic_write_partition(grade_part, grades, ledger.GRADE_SCHEMA)
    round_trip = ledger.read_partition(grade_part, ledger.GRADE_SCHEMA)
    assert ledger.canonical_hash(round_trip) == ledger.canonical_hash(grades)


def test_delayed_event_grade_uses_processing_day_but_entry_fill_clock(tmp_path):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    probability = _probability("000001.SZ", selected=False)
    frame = _frame(
        ["2026-08-07", "2026-08-10", "2026-08-11"],
        [10.0, 10.0, 10.1],
        [10.0, 10.2, 10.1],
    )
    grades = ledger.build_due_grades(
        [probability], [], {"000001.SZ": frame}, calendar, date(2026, 8, 11)
    )
    assert len(grades) == 1
    grade = grades[0]
    assert grade["graded_at"] == "2026-08-11T15:00:00+08:00"
    assert grade["grade_observed_session"] == "2026-08-11"
    assert grade["fill_decided_at"] == "2026-08-10T09:30:00+08:00"


def test_grade_recompute_keeps_first_and_refuses_changed_source(tmp_path):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    probability = _probability("000001.SZ", selected=True)
    original = {
        "000001.SZ": _frame(
            ["2026-08-07", "2026-08-10", "2026-08-11"],
            [10.0, 10.0, 10.5],
            [10.0, 11.0, 10.5],
        )
    }
    existing = ledger.build_due_grades(
        [probability], [], original, calendar, date(2026, 8, 11)
    )
    # Processing-night metadata is keep-first evidence, while the processing
    # session itself is not market-source provenance. A later identical run is
    # therefore a true no-op rather than a timestamp mutation.
    assert (
        ledger.build_due_grades(
            [probability], existing, original, calendar, date(2026, 8, 12)
        )
        == []
    )
    assert {row["grade_observed_session"] for row in existing} == {"2026-08-11"}

    revised_frame = original["000001.SZ"].copy()
    # This raw revision does not change the return or any terminal state.  The
    # grade provenance digest alone must still make the keep-first conflict loud.
    revised_frame.loc[pd.Timestamp("2026-08-11"), "high"] = 10.9
    revised = {"000001.SZ": revised_frame}
    with pytest.raises(ledger.IntegrityError, match="keep-first grade contradiction"):
        ledger.build_due_grades(
            [probability], existing, revised, calendar, date(2026, 8, 11)
        )

    malformed = [dict(row) for row in existing]
    malformed[0]["source_hash"] = "not-a-digest"
    with pytest.raises(ledger.IntegrityError, match="source_hash"):
        ledger.build_due_grades(
            [probability], malformed, original, calendar, date(2026, 8, 11)
        )


def test_exact_session_no_hop_and_lower_limit_carry(tmp_path):
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    no_hop = _probability("000001.SZ")
    no_hop_frame = _frame(
        ["2026-08-07", "2026-08-10", "2026-08-12", "2026-08-13"],
        [10.0, 10.0, 10.1, 10.2],
        [10.0, 10.0, 10.1, 10.2],
    )
    grade = ledger.build_execution_grade(
        no_hop,
        {"000001.SZ": no_hop_frame},
        calendar,
        date(2026, 8, 13),
        3,
    )
    assert grade is not None
    assert grade["exit_state"] == "missing_intermediate_session_no_hop"
    assert grade["gross_return"] is None
    assert grade["book_contribution_return"] == 0.0

    carry_probability = _probability("000002.SZ")
    carry_frame = _frame(
        ["2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"],
        [10.0, 10.0, 9.0, 8.1, 8.2],
        [10.0, 10.0, 9.0, 8.1, 8.2],
    )
    carried = ledger.build_execution_grade(
        carry_probability,
        {"000002.SZ": carry_frame},
        calendar,
        date(2026, 8, 13),
        1,
    )
    assert carried is not None
    assert carried["exit_state"] == "resolved_after_lower_limit_carry"
    assert carried["realized_exit_session"] == "2026-08-13"
    assert carried["gross_return"] == pytest.approx(-0.18)


def test_synthetic_latest_population_scores_all_receipt_models(tmp_path):
    packet = ledger.load_frozen_packet()
    calendar = ledger.load_exchange_calendar(_calendar_file(tmp_path))
    dates = pd.bdate_range(end="2026-08-07", periods=270)
    base = np.linspace(9.0, 10.0, len(dates))
    volume = 1_000_000.0 + (np.arange(len(dates)) % 23) * 10_000.0
    frame = pd.DataFrame(
        {
            "open": base * 0.999,
            "close": base,
            "high": base * 1.01,
            "low": base * 0.99,
            "volume": volume,
        },
        index=dates,
    )
    population = ledger.build_latest_eligible_population(
        {"600000.SH": frame}, date(2026, 8, 7), packet, set()
    )
    assert [row.ticker for row in population] == ["600000.SS"]
    rows = ledger.build_probability_snapshot(
        population,
        date(2026, 8, 7),
        calendar.next_session(date(2026, 8, 7)),
        packet,
        calendar,
        st_snapshot_hash="0" * 64,
    )
    assert len(rows) == 3
    assert {row["model_version"] for row in rows} == set(packet.model_versions.values())
    assert all(row["selection_rank"] == 1 for row in rows)
    assert all(row["authority"] == ledger.AUTHORITY for row in rows)


def test_workflow_wiring_is_between_library_and_pick_lab_and_step_local():
    workflow = (ledger.ROOT / ".github" / "workflows" / "asia-close.yml").read_text(
        encoding="utf-8"
    )
    rebuild = workflow.index("rebuild China/HK stock-search libraries")
    limit_alpha = workflow.index("CN limit-alpha forward ledger — probability + grade")
    pick_lab = workflow.index("CN Pick Lab — fire books")
    assert rebuild < limit_alpha < pick_lab
    segment = workflow[limit_alpha:pick_lab]
    assert "CN_LANE: asia" in segment
    assert "python -m scripts.advance_cn_limit_alpha_ledger" in segment
    assert "exit 0" in segment


def test_production_module_does_not_import_analysis_pinned_runner():
    source = Path(ledger.__file__).read_text(encoding="utf-8")
    assert "research.cn_limit_alpha_sol.onset_wave1" not in source
    assert "from research" not in source
