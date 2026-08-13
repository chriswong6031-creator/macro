"""Quality validators + annotation emission (Data OS §D8) — ``lib/dataos/quality.py``.

Every validator here is tested FAIL-THEN-PASS: a checker that returns findings for
everything and a checker that returns findings for nothing both pass a one-sided
test, and only one of those is a guard.  So each family gets a pathological input
that MUST be flagged and a clean input that MUST NOT be.

Two properties get their own tests because both have already shipped dead in this
repo in some form:

* ``check_validity_ohlc`` must SKIP a row with a null leg rather than raise —
  ``data/stocks`` has no ``open`` column at all (§D4), so a validator demanding four
  legs would fail on every row of a real store and be switched off within a day;
* ``emit_annotations`` must print at column 0 with ``flush`` — a logger's prefixing
  format pushes ``::`` off column 0, GitHub drops the annotation, and the alarm looks
  right in review while producing nothing (shipped dead five times: #3487, #3515,
  #3562, #3563, #3570).

Pure unit tests; ``now`` is injected everywhere and nothing reads ``data/``.

Run: .venv/bin/python -m pytest tests/test_dataos_quality.py -q
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lib.dataos.quality import (
    CheckFamily,
    Finding,
    Severity,
    annotation_line,
    check_completeness,
    check_freshness,
    check_referential,
    check_temporal_integrity,
    check_uniqueness,
    check_validity_ohlc,
    emit_annotations,
)
from lib.dataos.temporal import TemporalProfile

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
NAN = float("nan")

CLEAN_BAR = {"ticker": "NVDA", "date": "2024-06-03", "open": 114.0, "high": 116.0,
             "low": 113.5, "close": 114.8, "volume": 1_000_000}
IMPOSSIBLE_BAR = {"ticker": "NVDA", "date": "2024-06-04", "open": 114.0, "high": 110.0,
                  "low": 113.5, "close": 114.8, "volume": 1_000_000}


# ── the vocabulary ───────────────────────────────────────────────────────────
def test_the_nine_families_and_four_severities_are_exactly_the_spec_sets() -> None:
    assert {f.value for f in CheckFamily} == {
        "completeness", "freshness", "uniqueness", "validity", "continuity",
        "distribution", "cross_source_reconciliation", "referential_integrity",
        "temporal_integrity",
    }
    assert {s.value for s in Severity} == {"INFO", "WARN", "DEGRADED", "BLOCK"}


# ── validity: the OHLC fail-then-pass pair ───────────────────────────────────
def test_check_validity_ohlc_flags_the_pathological_row_and_passes_the_clean_one() -> None:
    assert check_validity_ohlc([CLEAN_BAR]) == []

    findings = check_validity_ohlc([IMPOSSIBLE_BAR], dataset_id="equity.bars.daily.stocks")
    assert findings, "a high below the low is an impossible bar and must be flagged"
    assert any("high 110.0 < low 113.5" in f.message for f in findings)
    assert all(f.family is CheckFamily.VALIDITY for f in findings)
    assert all(f.dataset_id == "equity.bars.daily.stocks" for f in findings)


def test_check_validity_ohlc_catches_a_high_below_low() -> None:
    findings = check_validity_ohlc([{"high": 1.0, "low": 2.0}])
    assert len(findings) == 1
    assert findings[0].evidence == {"row_index": 0, "high": 1.0, "low": 2.0}


@pytest.mark.parametrize(
    "row",
    [
        {"high": 10.0, "low": 5.0, "close": 11.0},   # close above high
        {"high": 10.0, "low": 5.0, "open": 4.0},     # open below low
        {"high": 10.0, "low": 5.0, "volume": -1},    # negative volume
    ],
)
def test_each_ohlc_invariant_is_actually_enforced(row: dict) -> None:
    assert check_validity_ohlc([row])


@pytest.mark.parametrize("missing", ["open", "high", "low", "close", "volume"])
def test_a_row_with_a_none_field_is_skipped_not_flagged_and_never_raises(missing: str) -> None:
    """``data/stocks`` has no ``open`` column at all — a validator that demanded four
    legs would fail on every row of a real store."""
    row = dict(CLEAN_BAR)
    row[missing] = None
    assert check_validity_ohlc([row]) == []


@pytest.mark.parametrize("missing", ["open", "high", "low", "close", "volume"])
def test_a_row_with_an_absent_field_is_skipped_too(missing: str) -> None:
    row = {k: v for k, v in CLEAN_BAR.items() if k != missing}
    assert check_validity_ohlc([row]) == []


def test_a_nan_leg_is_skipped_rather_than_compared() -> None:
    """NaN comparisons are all False, so an un-skipped NaN is a SILENT pass — worse
    than a crash.  Skipping it explicitly makes it a null question, not a validity one."""
    assert check_validity_ohlc([{**CLEAN_BAR, "high": NAN}]) == []
    assert check_validity_ohlc([{**CLEAN_BAR, "low": NAN, "high": NAN}]) == []


def test_a_null_leg_does_not_mask_a_real_defect_elsewhere_in_the_same_row() -> None:
    findings = check_validity_ohlc([{"open": None, "high": 1.0, "low": 2.0}])
    assert len(findings) == 1


def test_severity_is_the_callers_decision() -> None:
    findings = check_validity_ohlc([IMPOSSIBLE_BAR], severity=Severity.WARN)
    assert findings and all(f.severity is Severity.WARN for f in findings)


# ── uniqueness ───────────────────────────────────────────────────────────────
def test_check_uniqueness_flags_a_duplicated_grain_key_and_passes_a_clean_frame() -> None:
    rows = [
        {"ticker": "NVDA", "date": "2024-06-03"},
        {"ticker": "NVDA", "date": "2024-06-04"},
    ]
    assert check_uniqueness(rows, ["ticker", "date"]) == []

    dupes = rows + [{"ticker": "NVDA", "date": "2024-06-03", "close": 1.0}]
    findings = check_uniqueness(dupes, ["ticker", "date"])
    assert len(findings) == 1
    assert findings[0].family is CheckFamily.UNIQUENESS
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].evidence["count"] == 2


def test_uniqueness_reports_each_offending_key_once_not_once_per_row() -> None:
    rows = [{"id": "a"}] * 3 + [{"id": "b"}] * 2
    findings = check_uniqueness(rows, ["id"])
    assert len(findings) == 2
    assert [f.evidence["count"] for f in findings] == [3, 2]


def test_an_empty_frame_is_unique() -> None:
    assert check_uniqueness([], ["ticker"]) == []


# ── freshness ────────────────────────────────────────────────────────────────
def test_check_freshness_passes_inside_the_sla_and_flags_outside_it() -> None:
    inside = datetime(2026, 8, 12, 4, 0, tzinfo=timezone.utc)     # 8h old
    assert check_freshness(inside, sla_hours=26, now=NOW) == []

    outside = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)    # 56h old
    findings = check_freshness(outside, sla_hours=26, now=NOW, dataset_id="macro.fred.observations")
    assert len(findings) == 1
    assert findings[0].family is CheckFamily.FRESHNESS
    assert findings[0].evidence["age_hours"] == pytest.approx(56.0)


def test_freshness_is_pure_and_reads_the_injected_clock_not_the_wall_clock() -> None:
    ts = "2026-08-12T11:00:00+00:00"
    assert check_freshness(ts, sla_hours=2, now=NOW) == []
    assert check_freshness(ts, sla_hours=0.5, now=NOW)


def test_an_empty_dataset_is_a_freshness_failure_with_an_unbounded_age() -> None:
    """``age_hours: None`` deliberately, not a magic number a consumer could average."""
    findings = check_freshness(None, sla_hours=26, now=NOW)
    assert len(findings) == 1
    assert findings[0].evidence["age_hours"] is None


# ── completeness ─────────────────────────────────────────────────────────────
def test_check_completeness_distinguishes_absent_from_null() -> None:
    rows = [
        {"ticker": "NVDA", "close": 1.0},
        {"ticker": "AMD", "close": None},
        {"ticker": "INTC"},
    ]
    findings = check_completeness(rows, ["ticker", "close"])
    assert len(findings) == 2
    assert findings[0].evidence == {"row_index": 1, "key": "close", "present": True}
    assert findings[1].evidence == {"row_index": 2, "key": "close", "present": False}


def test_a_complete_frame_produces_nothing() -> None:
    assert check_completeness([{"a": 1, "b": 2}], ["a", "b"]) == []


# ── referential integrity ────────────────────────────────────────────────────
def test_check_referential_flags_a_member_the_master_does_not_carry() -> None:
    """The MMC incident from the other side: a basket of 19 whose price store answers
    for 18, with nothing anywhere comparing the two."""
    known = {"SEC:US-XNYS-MMC", "SEC:US-XNAS-FISV"}
    rows = [{"security_id": "SEC:US-XNYS-MMC"}, {"security_id": "SEC:US-XNYS-GHOST"}]
    findings = check_referential(rows, "security_id", known)
    assert len(findings) == 1
    assert findings[0].family is CheckFamily.REFERENTIAL
    assert findings[0].evidence["value"] == "SEC:US-XNYS-GHOST"

    assert check_referential(rows[:1], "security_id", known) == []


def test_a_null_id_is_a_completeness_question_not_a_referential_one() -> None:
    assert check_referential([{"security_id": None}], "security_id", {"SEC:X"}) == []


# ── temporal integrity ───────────────────────────────────────────────────────
def test_a_known_at_in_the_future_is_flagged() -> None:
    rows = [{"published_at": "2026-08-20T00:00:00+00:00", "ingested_at": "2026-08-20T01:00:00+00:00"}]
    findings = check_temporal_integrity(rows, TemporalProfile.REVISABLE_RELEASE, now=NOW)
    assert len(findings) == 1
    assert "FUTURE" in findings[0].message
    assert findings[0].family is CheckFamily.TEMPORAL_INTEGRITY


def test_a_known_at_in_the_past_is_clean() -> None:
    rows = [{"published_at": "2026-08-10T00:00:00+00:00"}]
    assert check_temporal_integrity(rows, TemporalProfile.REVISABLE_RELEASE, now=NOW) == []


def test_effective_at_before_period_end_is_flagged() -> None:
    """Information cannot become applicable before the interval it describes closed."""
    rows = [{
        "ingested_at": "2026-07-02T00:00:00+00:00",
        "effective_at": "2026-06-15T00:00:00+00:00",
        "period_end": "2026-06-30T00:00:00+00:00",
    }]
    findings = check_temporal_integrity(rows, TemporalProfile.SNAPSHOT_SERIES, now=NOW)
    assert len(findings) == 1
    assert "precedes period_end" in findings[0].message


def test_effective_at_on_or_after_period_end_is_clean() -> None:
    rows = [{
        "ingested_at": "2026-07-02T00:00:00+00:00",
        "effective_at": "2026-06-30T00:00:00+00:00",
        "period_end": "2026-06-30T00:00:00+00:00",
    }]
    assert check_temporal_integrity(rows, TemporalProfile.SNAPSHOT_SERIES, now=NOW) == []


def test_a_row_whose_known_at_is_unanswerable_becomes_a_finding_not_a_crash() -> None:
    """A checker that dies on row 3 tells you nothing about rows 4..n."""
    rows = [{"value": 1.0}, {"published_at": "2026-08-10T00:00:00+00:00"}]
    findings = check_temporal_integrity(rows, TemporalProfile.REVISABLE_RELEASE, now=NOW)
    assert len(findings) == 1
    assert findings[0].evidence["row_index"] == 0
    assert "unanswerable" in findings[0].message


def test_now_is_keyword_only_and_has_no_default_so_the_check_stays_pure() -> None:
    with pytest.raises(TypeError):
        check_temporal_integrity([], TemporalProfile.BARS)      # type: ignore[call-arg]


# ── annotations ──────────────────────────────────────────────────────────────
ANNOTATION_CASES = [
    (Severity.INFO, "::notice"),
    (Severity.WARN, "::warning"),
    (Severity.DEGRADED, "::warning"),
    (Severity.BLOCK, "::error"),
]


@pytest.mark.parametrize("severity, prefix", ANNOTATION_CASES)
def test_each_severity_maps_to_a_github_annotation_level(severity, prefix) -> None:
    line = annotation_line(Finding(CheckFamily.VALIDITY, severity, "ds", "boom", {}))
    assert line.startswith(prefix)
    assert "title=validity-" in line


def test_emit_annotations_writes_at_column_zero_and_flushes(capsys) -> None:
    """A logger's prefixing format pushes ``::`` off column 0 and GitHub drops the
    annotation entirely — the failure guarded by tests/test_gh_annotation_line_start.py."""
    findings = check_validity_ohlc([IMPOSSIBLE_BAR], dataset_id="equity.bars.daily.stocks")
    count = emit_annotations(findings)
    out = capsys.readouterr().out.splitlines()

    assert count == len(findings) == len(out)
    for line in out:
        assert line.startswith("::"), f"annotation not at column 0: {line!r}"
        assert "::error title=validity-block::" in line
        assert "equity.bars.daily.stocks" in line


def test_an_annotation_is_a_single_line_even_when_the_message_wraps() -> None:
    """A multi-line annotation body silently truncates in the Actions summary."""
    finding = Finding(CheckFamily.FRESHNESS, Severity.DEGRADED, "ds",
                      "a message\nthat wrapped\n   across lines", {})
    line = annotation_line(finding)
    assert "\n" not in line
    assert "a message that wrapped across lines" in line


def test_emitting_nothing_prints_nothing(capsys) -> None:
    assert emit_annotations([]) == 0
    assert capsys.readouterr().out == ""
