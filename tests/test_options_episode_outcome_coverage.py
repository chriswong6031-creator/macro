"""The unlabelled-H+60 census: it must split the hole by REMEDY, not just count it.

WHAT THIS PINS.  ``derive_h60_outcome`` returns non-persisted ``pending`` dicts,
and the prereg forbids appending them, so an episode that never resolves never
appears in ``outcomes_h60.jsonl`` at all.  Measured 2026-08-13: 237 of 1,206
episodes had no row.  Nothing bounded or alerted on that.

WHY A CLASSIFIER AND NOT A COUNTER.  The 237 are two populations with opposite
remedies — 223 whose ticker has no admissible price source at all (fixable only
by collecting it) and 14 whose ticker is demonstrably labellable and which are
pending on cadence alignment (protected by the prereg line "no cadence-dependent
condition is frozen as terminal").  A single percentage hides both.  These tests
pin the split, the evidence rules that produce it, and the declared bounds.

THE TRAP THAT MOTIVATES THE EVIDENCE RULE.  A terminal-incomplete row proves
nothing about a price source: both of its reasons are pure clock facts derived
without reading a single bar.  ASTS, SNOW, ARM and DDOG each carry terminal rows
and zero complete rows, and all four are in the structural gap.  Counting
terminal rows as evidence would silently move them into the accepted-forever
class — the exact misclassification that would ratify a fixable defect.

Run: python3 -m pytest tests/test_options_episode_outcome_coverage.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.options_episode_coverage import (  # noqa: E402
    CENSUS_SCHEMA,
    FAIL_MATURED_UNLABELLED_SHARE,
    IMMATURE_CLASS,
    SOURCE_DEPENDENT_CLASS,
    STRUCTURAL_GAP_CLASS,
    WARN_MATURED_UNLABELLED_SHARE,
    WARN_SOURCE_DEPENDENT_SHARE,
    CoverageCensusError,
    build_coverage_census,
    classify_unlabelled_episode,
    labellable_tickers,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def _episode(episode_id: str, ticker: str, *, available: datetime,
             session: str = "2026-08-12") -> dict:
    return {
        "episode_id": episode_id,
        "ticker": ticker,
        "session_date": session,
        "available_at": available.isoformat().replace("+00:00", "Z"),
    }


def _outcome(episode_id: str, status: str = "complete",
             reason: str | None = None) -> dict:
    row = {"episode_id": episode_id, "status": status}
    if reason is not None:
        row["reason"] = reason
    return row


def _matured(hours: int = 4) -> datetime:
    return NOW - timedelta(hours=hours)


# --- classification --------------------------------------------------------

def test_immature_episode_is_not_a_hole() -> None:
    """An episode inside its own H+60 clock is expected, never a defect."""
    episode = _episode("e1", "AAA", available=NOW - timedelta(minutes=30))
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable=set(),
    ) == IMMATURE_CLASS


def test_exact_horizon_boundary_is_matured() -> None:
    """At exactly H+60 the clock HAS elapsed; > not >= would leak a hole."""
    episode = _episode("e1", "AAA", available=NOW - timedelta(minutes=60))
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable=set(),
    ) != IMMATURE_CLASS


def test_labellable_ticker_is_source_dependent_not_structural() -> None:
    episode = _episode("e1", "AMD", available=_matured())
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable={"AMD"},
    ) == SOURCE_DEPENDENT_CLASS


def test_never_labelled_ticker_is_structural() -> None:
    episode = _episode("e1", "SMCI", available=_matured())
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable={"AMD"},
    ) == STRUCTURAL_GAP_CLASS


def test_price_source_ground_truth_overrides_ledger_inference() -> None:
    """A ticker with a real parquet+receipt pair is covered even with no label yet.

    Ledger inference is a fallback, not the answer: a newly collected ticker has
    a source before it has its first complete row, and calling that a structural
    gap would put a working lane on the defect list.
    """
    episode = _episode("e1", "NEWCO", available=_matured())
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable=set(), priced_tickers={"NEWCO"},
    ) == SOURCE_DEPENDENT_CLASS
    assert classify_unlabelled_episode(
        episode, now=NOW, labellable={"NEWCO"}, priced_tickers=set(),
    ) == STRUCTURAL_GAP_CLASS


def test_terminal_incomplete_rows_are_not_price_source_evidence() -> None:
    """The ASTS/SNOW/ARM/DDOG trap: clock-terminal rows consume no price bars."""
    episodes = [_episode("e1", "ASTS", available=_matured())]
    outcomes = [_outcome("e1", "incomplete", "decision_after_session_close")]
    by_id = {e["episode_id"]: e for e in episodes}
    assert labellable_tickers(outcomes, by_id) == set()

    episodes.append(_episode("e2", "ASTS", available=_matured()))
    by_id = {e["episode_id"]: e for e in episodes}
    census = build_coverage_census(episodes, outcomes, now=NOW)
    assert census["classes"][STRUCTURAL_GAP_CLASS] == 1
    assert census["classes"][SOURCE_DEPENDENT_CLASS] == 0


def test_complete_row_makes_the_ticker_labellable() -> None:
    episodes = [_episode("e1", "AMD", available=_matured())]
    by_id = {e["episode_id"]: e for e in episodes}
    assert labellable_tickers([_outcome("e1")], by_id) == {"AMD"}


def test_orphan_outcome_does_not_invent_a_labellable_ticker() -> None:
    """An outcome whose episode is absent cannot vouch for any ticker."""
    assert labellable_tickers([_outcome("ghost")], {}) == set()


# --- census shape ----------------------------------------------------------

def test_census_counts_and_shares_use_the_matured_denominator() -> None:
    """Immature episodes must not dilute the share the tripwire reads."""
    episodes = [
        _episode("m1", "AMD", available=_matured()),
        _episode("m2", "SMCI", available=_matured()),
        _episode("young", "SMCI", available=NOW - timedelta(minutes=5)),
    ]
    census = build_coverage_census(episodes, [_outcome("m1")], now=NOW)
    assert census["schema"] == CENSUS_SCHEMA
    assert census["totals"]["episodes"] == 3
    assert census["totals"]["matured"] == 2
    assert census["totals"]["matured_unlabelled"] == 1
    assert census["classes"][IMMATURE_CLASS] == 1
    # 1 of 2 matured, not 1 of 3 episodes.
    assert census["shares"]["matured_unlabelled_share"] == pytest.approx(0.5)


def test_census_reports_evidence_mode() -> None:
    episodes = [_episode("e1", "AMD", available=_matured())]
    assert build_coverage_census(
        episodes, [], now=NOW,
    )["evidence_mode"] == "ledger_inference"
    assert build_coverage_census(
        episodes, [], now=NOW, priced_tickers={"AMD"},
    )["evidence_mode"] == "price_source"


def test_census_names_the_structural_gap_tickers_with_sessions() -> None:
    episodes = [
        _episode("a", "SMCI", available=_matured(), session="2026-08-11"),
        _episode("b", "SMCI", available=_matured(), session="2026-08-12"),
        _episode("c", "LITE", available=_matured(), session="2026-08-12"),
    ]
    census = build_coverage_census(episodes, [], now=NOW)
    gaps = {item["ticker"]: item for item in census["structural_gap_tickers"]}
    assert gaps["SMCI"]["episodes"] == 2
    assert gaps["SMCI"]["sessions"] == ["2026-08-11", "2026-08-12"]
    assert gaps["LITE"]["episodes"] == 1
    # Ranked by exposure so the biggest hole reads first.
    assert census["structural_gap_tickers"][0]["ticker"] == "SMCI"


def test_census_is_bounded_and_declares_its_truncation() -> None:
    """A census that silently elides rows reads as 'covered everything'."""
    episodes = [
        _episode(f"e{i}", f"T{i:03d}", available=_matured()) for i in range(10)
    ]
    census = build_coverage_census(episodes, [], now=NOW, max_tickers=3)
    assert len(census["structural_gap_tickers"]) == 3
    assert census["truncated"]["structural_gap_tickers"] == 7
    assert census["bounds"]["max_census_tickers"] == 3


def test_empty_estate_does_not_divide_by_zero() -> None:
    census = build_coverage_census([], [], now=NOW)
    assert census["shares"]["matured_unlabelled_share"] == 0.0
    assert census["tripwires"] == []
    assert census["ok"] is True


def test_naive_now_is_rejected() -> None:
    with pytest.raises(CoverageCensusError):
        build_coverage_census([], [], now=datetime(2026, 8, 13, 12, 0))


def test_malformed_episode_is_rejected_not_skipped() -> None:
    with pytest.raises(CoverageCensusError):
        build_coverage_census([{"ticker": "AMD"}], [], now=NOW)
    with pytest.raises(CoverageCensusError):
        build_coverage_census(
            [{"episode_id": "e1", "ticker": "AMD", "available_at": "not-a-time"}],
            [], now=NOW,
        )


# --- declared bounds -------------------------------------------------------

def test_warn_threshold_fires_below_the_fail_threshold() -> None:
    """A known, disclosed defect warns; it must not red the lane reporting it."""
    # 2 unlabelled of 10 matured = 20%: above warn (10%), below fail (30%).  The
    # two holes are STRUCTURAL on purpose — routing them to the accepted class
    # instead would breach its much tighter 10% fail bound and escalate to an
    # error, which is a different tripwire than the one under test.
    episodes = [_episode(f"e{i}", "AMD", available=_matured()) for i in range(8)]
    episodes += [_episode(f"g{i}", "SMCI", available=_matured()) for i in range(2)]
    outcomes = [_outcome(f"e{i}") for i in range(8)]
    census = build_coverage_census(episodes, outcomes, now=NOW)
    wire = next(w for w in census["tripwires"] if w["id"] == "matured_unlabelled_share")
    assert wire["level"] == "warning"
    assert census["ok"] is True


def test_fail_threshold_escalates_to_error_and_clears_ok() -> None:
    # 6 unlabelled of 10 matured = 60%, above the 30% fail bound.
    episodes = [_episode(f"e{i}", "AMD", available=_matured()) for i in range(10)]
    outcomes = [_outcome(f"e{i}") for i in range(4)]
    census = build_coverage_census(episodes, outcomes, now=NOW)
    wire = next(w for w in census["tripwires"] if w["id"] == "matured_unlabelled_share")
    assert wire["level"] == "error"
    assert census["ok"] is False


def test_accepted_class_carries_its_own_tighter_bound() -> None:
    """The source-dependent class is the one the adjudication accepts forever,
    so growth in it is the signal the acceptance is no longer safe."""
    assert WARN_SOURCE_DEPENDENT_SHARE < WARN_MATURED_UNLABELLED_SHARE
    # 1 of 10 matured is source-dependent = 10%, over the 3% bound.
    episodes = [_episode(f"e{i}", "AMD", available=_matured()) for i in range(10)]
    outcomes = [_outcome(f"e{i}") for i in range(9)]
    census = build_coverage_census(episodes, outcomes, now=NOW)
    assert census["classes"][SOURCE_DEPENDENT_CLASS] == 1
    assert any(w["id"] == "source_dependent_share" for w in census["tripwires"])


def test_structural_gap_always_fires_when_any_ticker_is_uncovered() -> None:
    """One uncovered ticker is a defect regardless of how small its share is."""
    episodes = [_episode(f"e{i}", "AMD", available=_matured()) for i in range(99)]
    episodes.append(_episode("gap", "SMCI", available=_matured()))
    outcomes = [_outcome(f"e{i}") for i in range(99)]
    census = build_coverage_census(episodes, outcomes, now=NOW)
    assert census["shares"]["matured_unlabelled_share"] == pytest.approx(0.01)
    wire = next(
        w for w in census["tripwires"] if w["id"] == "structural_price_source_gap"
    )
    assert wire["level"] == "warning"
    # Below the 10% warn bound, so the share tripwire alone would have stayed
    # silent while an entire ticker was permanently unlabellable.
    assert not any(w["id"] == "matured_unlabelled_share" for w in census["tripwires"])


def test_thresholds_are_ordered() -> None:
    assert WARN_MATURED_UNLABELLED_SHARE < FAIL_MATURED_UNLABELLED_SHARE


# --- the CLI shell ---------------------------------------------------------

def test_cli_emits_line_start_annotations(tmp_path, capsys, monkeypatch) -> None:
    """House law: a GitHub annotation must START the line or GitHub drops it."""
    from scripts import audit_options_episode_outcome_coverage as audit

    ledger = tmp_path / "options_signal_episode"
    ledger.mkdir(parents=True)
    episodes = [_episode(f"e{i}", "SMCI", available=_matured()) for i in range(4)]
    (ledger / "episodes.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in episodes), encoding="utf-8",
    )
    (ledger / "outcomes_h60.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(tmp_path / "absent"))

    assert audit.main(["--data-dir", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    annotations = [line for line in lines if "::warning" in line or "::error" in line]
    assert annotations, "expected at least one tripwire annotation"
    for line in annotations:
        assert line.startswith("::"), f"annotation does not start the line: {line!r}"


def test_cli_strict_exits_nonzero_only_on_error_level(tmp_path, monkeypatch) -> None:
    from scripts import audit_options_episode_outcome_coverage as audit

    ledger = tmp_path / "options_signal_episode"
    ledger.mkdir(parents=True)
    episodes = [_episode(f"e{i}", "SMCI", available=_matured()) for i in range(4)]
    (ledger / "episodes.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in episodes), encoding="utf-8",
    )
    (ledger / "outcomes_h60.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(tmp_path / "absent"))

    # 100% unlabelled is over the fail bound.
    assert audit.main(["--data-dir", str(tmp_path), "--strict"]) == 1
    # Non-fatal by default: a disclosed defect must not red its own reporter.
    assert audit.main(["--data-dir", str(tmp_path)]) == 0


def test_cli_writes_a_bounded_census_artifact(tmp_path, monkeypatch) -> None:
    from scripts import audit_options_episode_outcome_coverage as audit

    ledger = tmp_path / "options_signal_episode"
    ledger.mkdir(parents=True)
    (ledger / "episodes.jsonl").write_text(
        json.dumps(_episode("e1", "SMCI", available=_matured())) + "\n",
        encoding="utf-8",
    )
    (ledger / "outcomes_h60.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(tmp_path / "absent"))

    out = tmp_path / "census.json"
    assert audit.main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    census = json.loads(out.read_text())
    assert census["schema"] == CENSUS_SCHEMA
    assert census["structural_gap_tickers"][0]["ticker"] == "SMCI"


def test_cli_rejects_a_torn_ledger(tmp_path, monkeypatch) -> None:
    """This audit exists to surface a hidden hole; it must not create one."""
    from scripts import audit_options_episode_outcome_coverage as audit

    ledger = tmp_path / "options_signal_episode"
    ledger.mkdir(parents=True)
    (ledger / "episodes.jsonl").write_text(
        json.dumps(_episode("e1", "SMCI", available=_matured())),  # no newline
        encoding="utf-8",
    )
    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(tmp_path / "absent"))
    with pytest.raises(SystemExit):
        audit.main(["--data-dir", str(tmp_path)])


def test_cli_missing_ledger_is_an_empty_estate(tmp_path, monkeypatch) -> None:
    from scripts import audit_options_episode_outcome_coverage as audit

    monkeypatch.setenv("MACRO_INTRADAY_DIR", str(tmp_path / "absent"))
    assert audit.main(["--data-dir", str(tmp_path)]) == 0


def test_priced_tickers_requires_the_receipt_sidecar(tmp_path) -> None:
    """A parquet without its causal receipt is inadmissible to the builder, so
    it must not count as coverage here either."""
    from scripts import audit_options_episode_outcome_coverage as audit

    root = tmp_path / "intraday"
    root.mkdir()
    (root / "BARE.parquet").write_bytes(b"")
    (root / "PAIRED.parquet").write_bytes(b"")
    (root / "PAIRED.parquet.receipt.json").write_text("{}", encoding="utf-8")
    assert audit._priced_tickers(root) == {"PAIRED"}


def test_absent_intraday_cache_falls_back_to_ledger_inference(tmp_path) -> None:
    """CI and sparse worktrees have no cache; reporting every ticker as
    uncovered there would be a false census, not a conservative one."""
    from scripts import audit_options_episode_outcome_coverage as audit

    assert audit._priced_tickers(tmp_path / "absent") is None
