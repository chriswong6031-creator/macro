from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from scripts.research.temporal_scale.session_bars import (
    BarGridSpec,
    SessionBarsError,
    SessionInterval,
    build_session_bars,
    generate_phase_variants,
)


def minute_rows(day: str, start: str, end: str, timezone: str = "America/New_York") -> pd.DataFrame:
    zone = ZoneInfo(timezone)
    first = datetime.fromisoformat(f"{day}T{start}").replace(tzinfo=zone)
    last = datetime.fromisoformat(f"{day}T{end}").replace(tzinfo=zone)
    values = []
    cursor = first
    index = 0
    while cursor < last:
        open_ms = int(cursor.timestamp() * 1000)
        close_ms = int((cursor + timedelta(minutes=1)).timestamp() * 1000)
        values.append({"open_ms": open_ms, "close_ms": close_ms, "open": float(index), "high": float(index + 2), "low": float(index - 1), "close": float(index + 1), "volume": 1.0})
        cursor += timedelta(minutes=1)
        index += 1
    return pd.DataFrame(values)


def elapsed_minute_rows(start: datetime, end: datetime) -> pd.DataFrame:
    """Create one-minute evidence by advancing UTC elapsed time, including DST folds."""
    first = start.astimezone(timezone.utc)
    last = end.astimezone(timezone.utc)
    values = []
    cursor = first
    index = 0
    while cursor < last:
        open_ms = int(cursor.timestamp() * 1000)
        close_ms = int((cursor + timedelta(minutes=1)).timestamp() * 1000)
        values.append({"open_ms": open_ms, "close_ms": close_ms, "open": float(index), "high": float(index + 2), "low": float(index - 1), "close": float(index + 1), "volume": 1.0})
        cursor += timedelta(minutes=1)
        index += 1
    return pd.DataFrame(values)


def test_public_session_bar_types_are_available() -> None:
    assert issubclass(SessionBarsError, ValueError)
    assert SessionInterval("09:30", "16:00", "regular").label == "regular"
    grid = BarGridSpec("rth-240", "America/New_York", 240, 0, (SessionInterval("09:30", "16:00", "regular"),), False, 0)
    assert grid.grid_id == "rth-240"
    assert grid.validate() is None


def test_wmt_extended_12h_has_clipped_residual_and_semantic_receipts() -> None:
    rows = minute_rows("2026-08-31", "04:00", "20:00")
    grid = BarGridSpec("wmt-extended-720-p0", "America/New_York", 720, 0, (SessionInterval("04:00", "20:00", "extended"),), False, 0)

    bars, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)

    assert [receipt.effective_minutes for receipt in receipts] == [720, 240]
    assert [receipt.clipped for receipt in receipts] == [False, True]
    assert [receipt.bar_index for receipt in receipts] == [receipt.open_ms // 60_000 for receipt in receipts]
    assert bars[["open", "high", "low", "close", "volume"]].to_dict("records") == [
        {"open": 0.0, "high": 721.0, "low": -1.0, "close": 720.0, "volume": 720.0},
        {"open": 720.0, "high": 961.0, "low": 719.0, "close": 960.0, "volume": 240.0},
    ]


def test_rth_early_close_clips_only_bucket_and_never_guesses_activity() -> None:
    rows = minute_rows("2026-11-27", "09:30", "13:00")
    grid = BarGridSpec("rth-240", "America/New_York", 240, 0, (SessionInterval("09:30", "13:00", "regular"),), False, 4)

    _, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)

    assert [receipt.effective_minutes for receipt in receipts] == [210]
    assert receipts[0].clipped is True
    assert receipts[0].traded_minutes is None
    assert receipts[0].trade_count is None
    assert receipts[0].realized_variance is None
    assert receipts[0].known_at_ms == receipts[0].close_ms + 4 * 60_000


def test_phase_leading_partial_conserves_interval_and_prefix_ids_are_stable() -> None:
    rows = minute_rows("2026-08-31", "09:30", "16:00")
    grid = BarGridSpec("rth-240-p30", "America/New_York", 240, 30, (SessionInterval("09:30", "16:00", "regular"),), False, 0)

    _, full = build_session_bars(rows, recipe_id="wmt", grid=grid)
    _, suffix = build_session_bars(rows.iloc[5:].reset_index(drop=True), recipe_id="wmt", grid=grid)

    assert [item.effective_minutes for item in full] == [30, 240, 120]
    assert sum(item.effective_minutes for item in full) == 390
    assert [item.bar_index for item in suffix] == [item.bar_index for item in full]
    assert [item.open_ms for item in suffix] == [item.open_ms for item in full]
    assert all(item.clipped for item in (full[0], full[-1]))


def test_missing_minutes_are_not_filled_and_include_empty_never_invents_ohlcv() -> None:
    rows = minute_rows("2026-08-31", "09:30", "13:30").iloc[:30]
    grid = BarGridSpec("rth-240", "America/New_York", 240, 0, (SessionInterval("09:30", "13:30", "regular"),), True, 0)

    bars, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)

    assert len(receipts) == 1
    assert receipts[0].empty_interval is False
    assert receipts[0].traded_minutes is None
    assert bars.iloc[0].volume == 30.0


def test_final_provisional_is_quarantined_but_interior_provisional_rejects() -> None:
    rows = minute_rows("2026-08-31", "09:30", "09:35")
    rows["is_confirmed"] = [True, True, True, True, False]
    grid = BarGridSpec("rth-5", "America/New_York", 5, 0, (SessionInterval("09:30", "09:35", "regular"),), False, 0)

    bars, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert len(bars) == len(receipts) == 1
    assert bars.iloc[0].volume == 4.0
    assert bars.attrs["excluded_provisional_count"] == 1
    assert bars.attrs["excluded_provisional_open_ms"] == (int(rows.iloc[-1].open_ms),)
    assert len(bars.attrs["excluded_provisional_row_sha256"]) == 64
    rows.loc[1, "is_confirmed"] = False
    with pytest.raises(SessionBarsError, match="interior provisional"):
        build_session_bars(rows, recipe_id="wmt", grid=grid)

    relabeled = minute_rows("2026-08-31", "09:30", "09:35")
    relabeled.index = [2, 3, 4, 5, 6]
    relabeled["is_confirmed"] = [True, True, False, True, True]
    with pytest.raises(SessionBarsError, match="interior provisional"):
        build_session_bars(relabeled, recipe_id="wmt", grid=grid)


def test_confirmation_accepts_only_boolean_or_exact_zero_one() -> None:
    rows = minute_rows("2026-08-31", "09:30", "09:33")
    rows["TG_is_confirmed"] = [1, 1, 0]
    grid = BarGridSpec("rth-3", "America/New_York", 3, 0, (SessionInterval("09:30", "09:33", "regular"),), False, 0)
    bars, _ = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert bars.iloc[0].volume == 2.0
    rows.loc[2, "TG_is_confirmed"] = 2
    with pytest.raises(SessionBarsError, match="exact 0/1"):
        build_session_bars(rows, recipe_id="wmt", grid=grid)

    confirmed = minute_rows("2026-08-31", "09:30", "09:33")
    confirmed.index = [7, 7, 7]
    bars, _ = build_session_bars(confirmed, recipe_id="wmt", grid=grid)
    assert bars.iloc[0].volume == 3.0


def test_dst_and_unresolvable_civil_endpoints_fail_closed() -> None:
    rows = minute_rows("2026-11-02", "09:30", "10:30")
    grid = BarGridSpec("rth-60", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    _, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert receipts[0].effective_minutes == 60
    bad = BarGridSpec("bad", "America/New_York", 60, 0, (SessionInterval("02:00", "03:00", "bad"),), False, 0)
    spring_rows = minute_rows("2026-03-08", "03:00", "04:00")
    with pytest.raises(SessionBarsError, match="nonexistent|ambiguous"):
        build_session_bars(spring_rows, recipe_id="wmt", grid=bad)


@pytest.mark.parametrize(
    ("start", "end", "expected_first_close", "expected_elapsed"),
    [
        (
            datetime(2026, 3, 7, 18, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 3, 8, 17, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc),
            1320,
        ),
        (
            datetime(2026, 10, 31, 18, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 11, 1, 17, 0, tzinfo=ZoneInfo("America/New_York")),
            datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),
            1440,
        ),
    ],
)
def test_dst_overnight_buckets_advance_exact_utc_elapsed_minutes(
    start: datetime,
    end: datetime,
    expected_first_close: datetime,
    expected_elapsed: int,
) -> None:
    rows = elapsed_minute_rows(start, end)
    grid = BarGridSpec("dst-overnight-480", "America/New_York", 480, 0, (SessionInterval("18:00", "17:00", "globex"),), False, 0)

    _, receipts = build_session_bars(rows, recipe_id="silver-clock-control", grid=grid)

    assert receipts[0].close_ms == int(expected_first_close.timestamp() * 1000)
    assert receipts[0].effective_minutes == 480
    assert sum(item.effective_minutes for item in receipts) == expected_elapsed
    projected = datetime.fromtimestamp(receipts[0].close_ms / 1000, ZoneInfo("America/New_York"))
    if start.month == 10:
        assert projected.hour == 1 and projected.fold == 1
    else:
        assert projected.hour == 3


@pytest.mark.parametrize(
    ("day", "start", "end", "nominal", "phase", "expected"),
    [
        ("2026-08-31", "04:00", "20:00", 720, 180, [180, 720, 60]),
        ("2026-08-31", "18:00", "17:00", 720, 120, [120, 720, 540]),
    ],
)
def test_hostile_phase_grids_conserve_every_open_minute_and_source_increment(
    day: str,
    start: str,
    end: str,
    nominal: int,
    phase: int,
    expected: list[int],
) -> None:
    zone = ZoneInfo("America/New_York")
    local_start = datetime.fromisoformat(f"{day}T{start}").replace(tzinfo=zone)
    local_end = datetime.fromisoformat(f"{day}T{end}").replace(tzinfo=zone)
    if end <= start:
        local_end += timedelta(days=1)
    rows = elapsed_minute_rows(local_start, local_end)
    rows["traded_minutes"] = 1
    rows["trade_count"] = 2
    grid = BarGridSpec(f"hostile-p{phase}", zone.key, nominal, phase, (SessionInterval(start, end, "extended"),), False, 0)

    bars, receipts = build_session_bars(rows, recipe_id="phase-control", grid=grid)

    assert [item.effective_minutes for item in receipts] == expected
    assert receipts[0].open_ms == int(local_start.timestamp() * 1000)
    assert receipts[-1].close_ms == int(local_end.timestamp() * 1000)
    assert all(left.close_ms == right.open_ms for left, right in zip(receipts, receipts[1:]))
    assert sum(item.effective_minutes for item in receipts) == len(rows)
    assert sum(item.volume or 0 for item in receipts) == len(rows)
    assert sum(item.traded_minutes or 0 for item in receipts) == len(rows)
    assert sum(item.trade_count or 0 for item in receipts) == 2 * len(rows)
    assert bars.volume.sum() == len(rows)


def test_two_overnight_sessions_never_cross_maintenance_or_double_allocate() -> None:
    zone = ZoneInfo("America/New_York")
    first = elapsed_minute_rows(
        datetime(2026, 8, 31, 18, 0, tzinfo=zone),
        datetime(2026, 9, 1, 17, 0, tzinfo=zone),
    )
    second = elapsed_minute_rows(
        datetime(2026, 9, 1, 18, 0, tzinfo=zone),
        datetime(2026, 9, 2, 17, 0, tzinfo=zone),
    )
    rows = pd.concat((first, second), ignore_index=True)
    grid = BarGridSpec("globex-p120", zone.key, 720, 120, (SessionInterval("18:00", "17:00", "globex"),), False, 0)

    bars, receipts = build_session_bars(rows, recipe_id="silver-clock-control", grid=grid)

    assert [item.effective_minutes for item in receipts] == [120, 720, 540] * 2
    assert bars.volume.sum() == len(rows) == sum(item.volume or 0 for item in receipts)
    maintenance = (
        int(datetime(2026, 9, 1, 17, 0, tzinfo=zone).timestamp() * 1000),
        int(datetime(2026, 9, 1, 18, 0, tzinfo=zone).timestamp() * 1000),
    )
    assert all(item.close_ms <= maintenance[0] or item.open_ms >= maintenance[1] for item in receipts)


def test_receipt_hash_binds_interval_semantics_and_full_grid_configuration() -> None:
    rows = minute_rows("2026-08-31", "09:30", "10:30")
    regular = BarGridSpec("same-id", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    extended = BarGridSpec("same-id", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "extended"),), False, 0)
    _, regular_receipts = build_session_bars(rows, recipe_id="wmt", grid=regular)
    _, extended_receipts = build_session_bars(rows, recipe_id="wmt", grid=extended)
    assert regular_receipts[0].source_row_sha256 != extended_receipts[0].source_row_sha256

    wider_inventory = BarGridSpec(
        "same-id",
        "America/New_York",
        60,
        0,
        (
            SessionInterval("04:00", "05:00", "premarket"),
            SessionInterval("09:30", "10:30", "regular"),
        ),
        False,
        0,
    )
    _, wider_receipts = build_session_bars(rows, recipe_id="wmt", grid=wider_inventory)
    assert regular_receipts[0].source_row_sha256 != wider_receipts[-1].source_row_sha256


def test_absent_declared_interval_and_omitted_empty_bucket_still_disclose_missing_time() -> None:
    rows = minute_rows("2026-08-31", "09:30", "10:30")
    intervals = (
        SessionInterval("04:00", "05:00", "premarket"),
        SessionInterval("09:30", "10:30", "regular"),
    )
    explicit = BarGridSpec("two-intervals", "America/New_York", 60, 0, intervals, True, 0)
    _, explicit_receipts = build_session_bars(rows, recipe_id="wmt", grid=explicit)
    assert len(explicit_receipts) == 2
    assert explicit_receipts[0].empty_interval is True
    assert explicit_receipts[0].session_flags["premarket"] is True
    omitted = BarGridSpec("two-intervals", "America/New_York", 60, 0, intervals, False, 0)
    bars, omitted_receipts = build_session_bars(rows, recipe_id="wmt", grid=omitted)
    assert len(omitted_receipts) == 1
    assert bars.attrs["missing_minutes"] == 60


def test_null_optional_activity_remains_unavailable_and_partial_evidence_is_not_summed() -> None:
    rows = minute_rows("2026-08-31", "09:30", "09:32")
    rows["traded_minutes"] = [None, None]
    rows["trade_count"] = [5, None]
    rows["realized_variance"] = [None, None]
    grid = BarGridSpec("rth", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    _, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert receipts[0].traded_minutes is None
    assert receipts[0].trade_count is None
    assert receipts[0].realized_variance is None

    for field, values in (
        ("traded_minutes", [-2, None]),
        ("trade_count", [1.5, None]),
        ("realized_variance", [-1.0, None]),
    ):
        malformed = minute_rows("2026-08-31", "09:30", "09:32")
        malformed[field] = values
        with pytest.raises(SessionBarsError, match="actual"):
            build_session_bars(malformed, recipe_id="wmt", grid=grid)


def test_public_api_totalizes_malformed_inputs_and_validates_empty_schema() -> None:
    grid = BarGridSpec("rth", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    with pytest.raises(SessionBarsError):
        build_session_bars(pd.DataFrame(), recipe_id="wmt", grid=grid)
    valid_empty = pd.DataFrame(columns=("open_ms", "close_ms", "open", "high", "low", "close", "volume"))
    bars, receipts = build_session_bars(valid_empty, recipe_id="wmt", grid=grid)
    assert bars.empty and receipts == ()
    with pytest.raises(SessionBarsError):
        build_session_bars(minute_rows("2026-08-31", "09:30", "09:31"), recipe_id="   ", grid=grid)

    huge = minute_rows("2026-08-31", "09:30", "09:31")
    huge["open_ms"] = huge["open_ms"].astype(object)
    huge.loc[0, "open_ms"] = 10**400
    with pytest.raises(SessionBarsError):
        build_session_bars(huge, recipe_id="wmt", grid=grid)

    out_of_range = minute_rows("2026-08-31", "09:30", "09:31")
    out_of_range.loc[0, "open_ms"] = 2**63 - 2
    out_of_range.loc[0, "close_ms"] = 2**63 - 1
    with pytest.raises(SessionBarsError):
        build_session_bars(out_of_range, recipe_id="wmt", grid=grid)

    overflowing = minute_rows("2026-08-31", "09:30", "09:32")
    overflowing["volume"] = [1e308, 1e308]
    with pytest.raises(SessionBarsError):
        build_session_bars(overflowing, recipe_id="wmt", grid=grid)

    class ExplodingPhases:
        def __iter__(self):
            raise RuntimeError("adversarial iterator")

    with pytest.raises(SessionBarsError):
        generate_phase_variants(grid, ExplodingPhases())
    with pytest.raises(SessionBarsError, match="IANA"):
        BarGridSpec("bad-zone", "../etc/passwd", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)


def test_phase_variants_are_deterministic_and_closed_intervals_stay_separate() -> None:
    base = BarGridSpec("overnight", "America/New_York", 240, 0, (SessionInterval("18:00", "17:00", "globex"),), False, 0)
    assert [item.grid_id for item in generate_phase_variants(base, [5, 0, 5])] == ["overnight-p0", "overnight-p5"]
    with pytest.raises(SessionBarsError):
        generate_phase_variants(base, [240])


def test_rejects_overlapping_grammar_and_nonmonotone_or_duplicate_input() -> None:
    with pytest.raises(SessionBarsError, match="overlap|duplicate"):
        BarGridSpec("bad", "America/New_York", 60, 0, (SessionInterval("09:30", "12:00", "regular"), SessionInterval("11:00", "16:00", "regular")), False, 0)
    rows = minute_rows("2026-08-31", "09:30", "09:32")
    grid = BarGridSpec("rth", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    with pytest.raises(SessionBarsError, match="monotone"):
        build_session_bars(rows.iloc[::-1], recipe_id="wmt", grid=grid)
    duplicate = pd.concat([rows, rows.iloc[[0]]], ignore_index=True)
    with pytest.raises(SessionBarsError, match="duplicate"):
        build_session_bars(duplicate, recipe_id="wmt", grid=grid)


def test_receipt_flags_coverage_and_genuinely_empty_bucket_are_semantic() -> None:
    rows = minute_rows("2026-08-31", "09:30", "10:30")
    grid = BarGridSpec("rth", "America/New_York", 60, 0, (SessionInterval("09:30", "11:30", "regular"),), True, 0)
    bars, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert len(bars) == 1 and len(receipts) == 2
    assert receipts[0].session_flags == {"premarket": False, "market": True, "postmarket": False, "first_session_bar": True, "last_session_bar": False, "first_regular_bar": True, "last_regular_bar": False}
    assert receipts[1].empty_interval and receipts[1].session_flags["last_regular_bar"]
    assert bars.attrs["missing_minutes"] == 60
    assert bars.attrs["excluded_provisional_count"] == 0


def test_invalid_actual_evidence_and_outside_rows_fail_closed() -> None:
    rows = minute_rows("2026-08-31", "09:30", "09:32")
    rows["traded_minutes"] = [1, "bad"]
    grid = BarGridSpec("rth", "America/New_York", 60, 0, (SessionInterval("09:30", "10:30", "regular"),), False, 0)
    with pytest.raises(SessionBarsError, match="actual"):
        build_session_bars(rows, recipe_id="wmt", grid=grid)
    outside = minute_rows("2026-08-31", "08:00", "08:01")
    with pytest.raises(SessionBarsError, match="outside"):
        build_session_bars(outside, recipe_id="wmt", grid=grid)


_FORBIDDEN_ROOTS = {"requests", "urllib", "http", "httpx", "socket", "subprocess", "ftplib"}
_FORBIDDEN_CALLS = {
    "open", "write", "write_text", "write_bytes", "to_csv", "unlink", "remove", "rename",
    "touch", "mkdir", "makedirs", "rmdir", "rmtree", "move", "system", "popen",
}


def _effect_guard_violations(source: str) -> set[str]:
    tree = ast.parse(source)
    violations: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                aliases[alias.asname or root] = alias.name
                if root in _FORBIDDEN_ROOTS:
                    violations.add(root)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0].lower()
            if root in _FORBIDDEN_ROOTS:
                violations.add(root)
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"

    def dotted(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = dotted(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Call):
            return dotted(node.func)
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = dotted(node.func).lower()
            root = target.split(".", 1)[0]
            leaf = target.rsplit(".", 1)[-1]
            if root in _FORBIDDEN_ROOTS:
                violations.add(root)
            if leaf in _FORBIDDEN_CALLS:
                violations.add(leaf)
            if target in {"os.replace", "pathlib.Path.replace", "shutil.move"}:
                violations.add(leaf)
    return violations


def test_module_has_no_effectful_loading_or_network_surface() -> None:
    assert _effect_guard_violations("from socket import create_connection as c\nc(('x', 1))")
    assert _effect_guard_violations("import os as x\nx.replace('a', 'b')")
    assert _effect_guard_violations("from pathlib import Path\nPath('x').write_text('x')")
    assert _effect_guard_violations("open('x', 'w')")
    source = open("scripts/research/temporal_scale/session_bars.py", encoding="utf-8").read()
    assert _effect_guard_violations(source) == set()


def test_rth_shape_and_complete_session_prefix_invariance() -> None:
    one = minute_rows("2026-08-31", "09:30", "16:00")
    grid = BarGridSpec("rth-240", "America/New_York", 240, 0, (SessionInterval("09:30", "16:00", "regular"),), False, 0)
    _, rth = build_session_bars(one, recipe_id="wmt", grid=grid)
    assert [item.effective_minutes for item in rth] == [240, 150]
    sessions = []
    for day in range(25, 31):
        sessions.append(minute_rows(f"2026-08-{day:02d}", "09:30", "16:00"))
    full = pd.concat(sessions, ignore_index=True)
    _, all_receipts = build_session_bars(full, recipe_id="wmt", grid=grid)
    for drop in (1, 2, 5):
        _, suffix = build_session_bars(pd.concat(sessions[drop:], ignore_index=True), recipe_id="wmt", grid=grid)
        assert [item.to_dict() for item in suffix] == [item.to_dict() for item in all_receipts[drop * 2:]]
