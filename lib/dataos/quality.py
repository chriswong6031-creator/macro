"""Quality — nine check families, four severities (Data OS §D8).

WHY THIS FILE EXISTS.  The house's existing detectors are excellent and each sees
exactly one thing: ``detect_stale_series`` is frame-grain (one live column keeps a
dead frame "fresh" — china_connect hid the death of ``net``/``buy``/``sell`` for ~2
years behind a still-ticking ``turnover``), ``detect_dark_columns`` fixed that at the
column grain, and the circuit breaker covers reachability.  None of them can answer
"is this dataset internally consistent", "is it complete against a universe", or "does
it claim to have known something before it could have".  This module is the missing
row of that table, expressed as PURE functions so a check is a unit test, not a
nightly.

FAMILIES: completeness · freshness · uniqueness · validity · continuity ·
distribution · cross-source reconciliation · referential integrity · temporal
integrity.

SEVERITIES: ``INFO`` (record) · ``WARN`` (annotate) · ``DEGRADED`` (serve, with a
user-visible degradation state) · ``BLOCK`` (refuse to publish).  Severity is
declared by the caller, not inferred here: the same missing row is INFO on a research
scratch table and BLOCK on a published tape, and only the contract knows which.

EVERY VALIDATOR IS PURE.  List-of-dicts in, :class:`Finding` list out; ``now`` is
INJECTED, never read from the wall clock (mirroring ``detect_dark_columns``, whose
docstring records the same rule and the same reason: the caller owns the clock, and a
test can pin it).  No pandas at import — these run in the thin CI lanes.

ANNOTATIONS ARE BARE PRINTS.  :func:`emit_annotations` prints at column 0 with
``flush=True`` and never touches a logger.  Every builder here configures logging with
a prefixing format, so ``log.warning("::warning …")`` emits ``WARNING ::warning …``,
GitHub only parses a workflow command when ``::`` sits at column 0, and the alarm
silently disappears.  That shipped dead five separate times (#3487, #3515, #3562,
#3563, #3570) before #3587 swept 69 sites and added
``tests/test_gh_annotation_line_start.py``.  ``flush`` is load-bearing: stdout is
block-buffered when piped in CI.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from lib.dataos.temporal import Clock, TemporalProfile, known_at, utc

__all__ = [
    "Severity",
    "CheckFamily",
    "Finding",
    "check_uniqueness",
    "check_validity_ohlc",
    "check_freshness",
    "check_completeness",
    "check_referential",
    "check_temporal_integrity",
    "annotation_line",
    "emit_annotations",
]


class Severity(Enum):
    """What a finding obliges the pipeline to DO (§D8)."""

    INFO = "INFO"           # record it
    WARN = "WARN"           # annotate the run
    DEGRADED = "DEGRADED"   # serve, with a user-visible degradation state
    BLOCK = "BLOCK"         # refuse to publish


class CheckFamily(Enum):
    """The nine families of §D8."""

    COMPLETENESS = "completeness"
    FRESHNESS = "freshness"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    CONTINUITY = "continuity"
    DISTRIBUTION = "distribution"
    CROSS_SOURCE = "cross_source_reconciliation"
    REFERENTIAL = "referential_integrity"
    TEMPORAL_INTEGRITY = "temporal_integrity"


@dataclass(frozen=True)
class Finding:
    """One quality defect, with the EVIDENCE that proves it.

    ``evidence`` is a mapping and not prose because a finding whose proof is only in
    its message cannot be re-checked, deduplicated, or counted.  ``message`` says what
    a human should do; ``evidence`` says what the checker actually saw.
    """

    family: CheckFamily
    severity: Severity
    dataset_id: str
    message: str
    evidence: dict = field(default_factory=dict)


def _finding(family, severity, dataset_id, message, evidence) -> Finding:
    return Finding(family=family, severity=severity, dataset_id=dataset_id,
                   message=message, evidence=evidence)


def _key(row: Mapping, key_cols: Sequence[str]) -> tuple:
    return tuple(row.get(c) for c in key_cols)


def check_uniqueness(
    rows: Iterable[Mapping],
    key_cols: Sequence[str],
    *,
    dataset_id: str = "",
    severity: Severity = Severity.BLOCK,
) -> list[Finding]:
    """Every ``key_cols`` tuple must appear at most once.

    ``BLOCK`` by default: a duplicated grain key silently multiplies whatever a
    consumer sums, and there is no downstream check that can see it.
    """
    counts: dict[tuple, int] = {}
    order: list[tuple] = []
    for row in rows:
        k = _key(row, key_cols)
        if k not in counts:
            order.append(k)
        counts[k] = counts.get(k, 0) + 1
    findings = []
    for k in order:
        if counts[k] > 1:
            findings.append(_finding(
                CheckFamily.UNIQUENESS, severity, dataset_id,
                f"duplicate grain key {dict(zip(key_cols, k))} appears {counts[k]}x — "
                "anything a consumer sums over this grain is multiplied",
                {"key_cols": list(key_cols), "key": list(k), "count": counts[k]},
            ))
    return findings


_OHLC_FIELDS = ("open", "high", "low", "close")


def _num(value) -> float | None:
    """A comparable number, or ``None`` for anything that is not one.

    ``None`` and ``NaN`` are SKIPPED rather than raised on: a missing leg is a
    completeness/null question (``lib/dataos/nulls.py``) and answering it here would
    turn every gap into a spurious validity failure — which is how a validator gets
    turned off.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return None if math.isnan(f) else f
    return None


def check_validity_ohlc(
    rows: Iterable[Mapping],
    *,
    dataset_id: str = "",
    severity: Severity = Severity.BLOCK,
) -> list[Finding]:
    """A bar must be internally possible: high >= low, high >= open/close,
    low <= open/close, volume >= 0.

    Rows where a field is absent or null are SKIPPED, not flagged and not raised on
    — ``data/stocks`` has no ``open`` column at all (§D4), so a validator that
    demanded four legs would fail on every row of a real store and be disabled within
    a day.
    """
    findings: list[Finding] = []
    for i, row in enumerate(rows):
        vals = {f: _num(row.get(f)) for f in _OHLC_FIELDS}
        high, low, opn, close = vals["high"], vals["low"], vals["open"], vals["close"]
        if high is not None and low is not None and high < low:
            findings.append(_finding(
                CheckFamily.VALIDITY, severity, dataset_id,
                f"row {i}: high {high} < low {low} — the bar is impossible",
                {"row_index": i, "high": high, "low": low},
            ))
        for name, value in (("open", opn), ("close", close)):
            if high is not None and value is not None and value > high:
                findings.append(_finding(
                    CheckFamily.VALIDITY, severity, dataset_id,
                    f"row {i}: {name} {value} > high {high}",
                    {"row_index": i, "field": name, "value": value, "high": high},
                ))
            if low is not None and value is not None and value < low:
                findings.append(_finding(
                    CheckFamily.VALIDITY, severity, dataset_id,
                    f"row {i}: {name} {value} < low {low}",
                    {"row_index": i, "field": name, "value": value, "low": low},
                ))
        volume = _num(row.get("volume"))
        if volume is not None and volume < 0:
            findings.append(_finding(
                CheckFamily.VALIDITY, severity, dataset_id,
                f"row {i}: volume {volume} is negative",
                {"row_index": i, "volume": volume},
            ))
    return findings


def check_freshness(
    newest_ts: datetime | str | None,
    sla_hours: float,
    now: datetime | str,
    *,
    dataset_id: str = "",
    severity: Severity = Severity.DEGRADED,
) -> list[Finding]:
    """Is the newest observation inside the dataset's freshness SLA?

    ``now`` is injected so the check is pure and a test can pin it.  A ``None``
    newest observation is an EMPTY dataset, which is a freshness failure with an
    unbounded age — deliberately reported as ``age_hours: None`` rather than a magic
    number a consumer could average or sort as if it were a real age
    (same rule as ``detect_dark_columns``).
    """
    now_utc = utc(now)
    if newest_ts is None:
        return [_finding(
            CheckFamily.FRESHNESS, severity, dataset_id,
            f"dataset has no observation at all (SLA {sla_hours}h)",
            {"age_hours": None, "sla_hours": sla_hours, "as_of": now_utc.isoformat()},
        )]
    newest = utc(newest_ts)
    age_hours = (now_utc - newest).total_seconds() / 3600.0
    if age_hours > sla_hours:
        return [_finding(
            CheckFamily.FRESHNESS, severity, dataset_id,
            f"newest observation {newest.isoformat()} is {age_hours:.1f}h old, past its "
            f"{sla_hours}h SLA",
            {"age_hours": round(age_hours, 3), "sla_hours": sla_hours,
             "newest": newest.isoformat(), "as_of": now_utc.isoformat()},
        )]
    return []


def check_completeness(
    rows: Iterable[Mapping],
    expected_keys: Iterable[str],
    *,
    dataset_id: str = "",
    severity: Severity = Severity.WARN,
) -> list[Finding]:
    """Every row must carry every expected key, non-null.

    Row-grain completeness: a key that is absent and a key that is present-but-null
    are the SAME defect to a consumer (both arrive as ``None``), so both are reported
    — with ``present`` in the evidence, because the repair differs (fix the writer vs
    fix the source).
    """
    wanted = tuple(expected_keys)
    findings: list[Finding] = []
    for i, row in enumerate(rows):
        for key in wanted:
            present = key in row
            if present and row.get(key) is not None:
                continue
            findings.append(_finding(
                CheckFamily.COMPLETENESS, severity, dataset_id,
                f"row {i}: {key!r} is " + ("null" if present else "absent"),
                {"row_index": i, "key": key, "present": present},
            ))
    return findings


def check_referential(
    rows: Iterable[Mapping],
    id_col: str,
    known_ids: Iterable[str],
    *,
    dataset_id: str = "",
    severity: Severity = Severity.BLOCK,
) -> list[Finding]:
    """Every ``id_col`` value must exist in *known_ids* (the master).

    This is the check that would have caught the MMC incident from the other side:
    a basket declaring 19 members while the price store answers for 18 is a dangling
    reference, and today nothing anywhere compares the two.
    """
    universe = set(known_ids)
    findings: list[Finding] = []
    for i, row in enumerate(rows):
        value = row.get(id_col)
        if value is None or value in universe:
            continue
        findings.append(_finding(
            CheckFamily.REFERENTIAL, severity, dataset_id,
            f"row {i}: {id_col}={value!r} is not in the known id universe "
            f"({len(universe)} ids)",
            {"row_index": i, "id_col": id_col, "value": value},
        ))
    return findings


def check_temporal_integrity(
    rows: Iterable[Mapping],
    profile: TemporalProfile,
    *,
    now: datetime | str,
    dataset_id: str = "",
    severity: Severity = Severity.BLOCK,
) -> list[Finding]:
    """Clocks must be physically possible.

    Two invariants, both of which a silent violation of makes a backtest LOOK better:

    * ``known_at`` may not be in the future relative to the injected *now* — a row
      that claims it will be knowable tomorrow is either a clock bug or a leak.
    * ``effective_at`` may not precede ``period_end`` where both exist — information
      cannot become applicable before the interval it describes has closed.

    ``now`` is keyword-only and has NO default: a default would read the wall clock
    and make the function impure, and an impure quality check cannot be a unit test.
    Rows the profile cannot answer ``known_at`` for are reported as findings rather
    than raising, because a checker that dies on row 3 tells you nothing about rows
    4..n.
    """
    now_utc = utc(now)
    findings: list[Finding] = []
    for i, row in enumerate(rows):
        try:
            k = known_at(row, profile)
        except Exception as exc:  # noqa: BLE001 — a bad row is a finding, not a crash
            findings.append(_finding(
                CheckFamily.TEMPORAL_INTEGRITY, severity, dataset_id,
                f"row {i}: known_at is unanswerable — {exc}",
                {"row_index": i, "profile": profile.value if hasattr(profile, "value") else str(profile)},
            ))
        else:
            if k > now_utc:
                findings.append(_finding(
                    CheckFamily.TEMPORAL_INTEGRITY, severity, dataset_id,
                    f"row {i}: known_at {k.isoformat()} is in the FUTURE relative to "
                    f"{now_utc.isoformat()}",
                    {"row_index": i, "known_at": k.isoformat(), "now": now_utc.isoformat()},
                ))
        effective = row.get(Clock.EFFECTIVE_AT.value)
        period_end = row.get(Clock.PERIOD_END.value)
        if effective is not None and period_end is not None:
            try:
                eff, end = utc(effective), utc(period_end)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                findings.append(_finding(
                    CheckFamily.TEMPORAL_INTEGRITY, severity, dataset_id,
                    f"row {i}: effective_at/period_end are not usable timestamps — {exc}",
                    {"row_index": i},
                ))
                continue
            if eff < end:
                findings.append(_finding(
                    CheckFamily.TEMPORAL_INTEGRITY, severity, dataset_id,
                    f"row {i}: effective_at {eff.isoformat()} precedes period_end "
                    f"{end.isoformat()} — information cannot apply before its interval closed",
                    {"row_index": i, "effective_at": eff.isoformat(),
                     "period_end": end.isoformat()},
                ))
    return findings


_ANNOTATION_LEVEL: dict[Severity, str] = {
    Severity.INFO: "notice",
    Severity.WARN: "warning",
    Severity.DEGRADED: "warning",
    Severity.BLOCK: "error",
}


def annotation_line(finding: Finding) -> str:
    """Render one finding as a SINGLE GitHub Actions annotation line.

    The caller MUST emit this with a bare ``print(..., flush=True)`` — see
    :func:`emit_annotations` and this module's docstring for what happens otherwise.
    """
    level = _ANNOTATION_LEVEL.get(finding.severity, "warning")
    slug = f"{finding.family.value}-{finding.severity.value.lower()}"
    where = f"{finding.dataset_id}: " if finding.dataset_id else ""
    message = " ".join(str(finding.message).split())
    return f"::{level} title={slug}::{where}{message}"


def emit_annotations(findings: Iterable[Finding]) -> int:
    """Print one GitHub annotation per finding; return how many were emitted.

    BARE print, never ``log.*``: a logger's prefixing format pushes ``::`` off column
    0 and GitHub drops the annotation entirely.  ``flush`` is load-bearing — stdout is
    block-buffered when piped in CI.
    """
    count = 0
    for finding in findings:
        print(annotation_line(finding), flush=True)
        count += 1
    return count
