"""Hermetic tests for the bulk historical minute-bar plane.

No network, no token, no live store.  Every vendor response is synthesized.

HERMETIC IN DATA, NOT IN TIME (repo law): every date here is derived from the frozen
``ANCHOR_YEAR`` / ``ANCHOR_SESSIONS`` constants, never from ``date.today()``, so the
suite cannot start failing because the calendar moved.  Run under ``TZ=UTC``; the
plane stamps bars in Asia/Shanghai explicitly, so a UTC runner must produce identical
digests to a Shanghai one — ``test_utc_runner_produces_shanghai_stamps`` pins that.
"""

from __future__ import annotations

import json
import subprocess
import sys
import sysconfig
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from collectors import tushare_addons as addons
from collectors import tushare_client as tc
from collectors import tushare_minutes_plane as plane
from scripts import backfill_tushare_minutes as cli

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "cn_tushare_minutes_manifest.v1.schema.json"

# ---- Frozen clock constants: the whole suite hangs off these, never off "now". ----
ANCHOR_YEAR = 2024
ANCHOR_FIRST_SESSION = date(ANCHOR_YEAR, 1, 2)
TICKER = "600519.SS"
VENDOR_TICKER = "600519.SH"
OTHER_TICKER = "000001.SZ"
OBSERVED_AT = datetime(ANCHOR_YEAR, 6, 1, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------


def make_sessions(count: int, *, start: date = ANCHOR_FIRST_SESSION) -> list[date]:
    """``count`` weekday sessions from a frozen anchor — a synthetic exchange clock."""
    sessions: list[date] = []
    cursor = start
    while len(sessions) < count:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    return sessions


def make_calendar(
    sessions: list[date], *, source: str = "synthetic"
) -> plane.SessionCalendar:
    return plane.SessionCalendar(
        sessions=tuple(sessions),
        source=source,
        source_path=None,
        source_sha256=None,
        nonclaims=("synthetic_test_clock",),
    )


def make_universe(
    tickers: list[str], *, years: dict[str, set[int]] | None = None
) -> plane.Universe:
    return plane.Universe(
        tickers=tuple(tickers),
        source="synthetic",
        source_path=None,
        source_sha256=None,
        event_years={t: frozenset(v) for t, v in (years or {}).items()},
    )


def minute_rows(
    session: date,
    *,
    ticker: str = VENDOR_TICKER,
    bars: int = 3,
    zero_volume_at: int | None = None,
    price_scale: int = 1,
) -> list[dict[str, object]]:
    """Synthetic 1-min bars starting 09:31, each 0.01 CNY above the last."""
    rows: list[dict[str, object]] = []
    for index in range(bars):
        clock = (
            datetime.combine(session, time(9, 31)) + timedelta(minutes=index)
        ).strftime("%Y-%m-%d %H:%M:%S")
        base = (1000 + index) * price_scale
        low, high = base, base + 2
        zero = index == zero_volume_at
        rows.append(
            {
                "ts_code": ticker,
                "trade_time": clock,
                "open": f"{base / 100:.2f}",
                "close": f"{(base + 1) / 100:.2f}",
                "high": f"{high / 100:.2f}",
                "low": f"{low / 100:.2f}",
                "vol": 0 if zero else 1000 + index,
                "amount": 0 if zero else float(base * 10),
            }
        )
    if zero_volume_at is not None:
        # A zero-volume bar is a STALE carry-forward: flat OHLC, not a range.
        row = rows[zero_volume_at]
        flat = row["open"]
        row.update({"close": flat, "high": flat, "low": flat})
    return rows


def minute_frame(*args: object, **kwargs: object) -> pd.DataFrame:
    return pd.DataFrame(
        minute_rows(*args, **kwargs), columns=list(plane.BASE_VENDOR_FIELDS)
    )


def normalized(session: date, **kwargs: object) -> list[dict[str, object]]:
    return plane.normalize_minute_rows(
        minute_frame(session, **kwargs),
        ticker=TICKER,
        frequency="1min",
        year=session.year,
    )


def install(
    root: Path, records: list[dict[str, object]], *, source_hash: str = "ab" * 32
) -> plane.PartitionResult:
    return plane.install_partition(
        root=root,
        frequency="1min",
        ticker=TICKER,
        year=ANCHOR_YEAR,
        records=records,
        chunks=[{"api_name": "stk_mins", "ts_code": VENDOR_TICKER}],
        calendar_receipt={"source": "synthetic"},
        tp0_probe={"receipt_path": "synthetic"},
        governor_receipt={"calls_per_minute": 240},
        source_rows_hash=source_hash,
        observed_at=OBSERVED_AT,
    )


@pytest.fixture
def tp0_probe_root(tmp_path: Path) -> Path:
    """A minimal Lane-A ``stk_mins`` probe receipt that witnesses access."""
    root = tmp_path / "addons"
    directory = (
        root
        / "stk_mins"
        / "by_frequency=1min"
        / f"by_trade_date={ANCHOR_FIRST_SESSION.isoformat()}"
        / f"by_scope=ticker-{TICKER}"
    )
    directory.mkdir(parents=True)
    payload = {
        "receipt_sha256": "ef" * 32,
        "endpoint_contract": {
            "contract_sha256": plane.BASE_ENDPOINT_CONTRACT.contract_hash
        },
        "access_observation_receipt": {
            "observation": "access_observed_at_request_time",
            "observed_at_asia_shanghai": OBSERVED_AT.isoformat(),
        },
    }
    (directory / "receipt.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


# --------------------------------------------------------------------------------------
# Drift pins — this plane extends two other modules; it must not fork them silently
# --------------------------------------------------------------------------------------


def test_price_tick_constants_match_the_spine() -> None:
    spine = pytest.importorskip("collectors.china_tushare_spine")
    assert plane.A_SHARE_PRICE_TICK == spine.A_SHARE_PRICE_TICK
    assert plane.A_SHARE_PRICE_SCALE == spine.A_SHARE_PRICE_SCALE


@pytest.mark.parametrize(
    "clock",
    [
        time(9, 30),
        time(10, 0),
        time(11, 30),
        time(13, 0),
        time(15, 0),
        time(15, 5),
        time(15, 30),
    ],
)
def test_session_segment_matches_the_addons_pilot(clock: time) -> None:
    assert plane.classify_session_segment(clock) == addons._minute_session_segment(
        clock
    )


@pytest.mark.parametrize("clock", [time(9, 29), time(12, 0), time(15, 1), time(15, 31)])
def test_off_clock_minute_is_refused(clock: time) -> None:
    with pytest.raises(plane.MinutesPlaneIntegrityError):
        plane.classify_session_segment(clock)


def test_base_endpoint_contract_is_the_addons_contract() -> None:
    assert plane.BASE_ENDPOINT_CONTRACT is addons.ENDPOINTS["stk_mins"]
    assert plane.MAX_ROWS_PER_RESPONSE == 8_000
    assert plane.BASE_VENDOR_FIELDS == addons.ENDPOINTS["stk_mins"].vendor_fields
    # The partition schema is a declared SUPERSET, never a rewrite.
    base_names = [f.name for f in addons.ENDPOINTS["stk_mins"].output_schema]
    plane_names = [f.name for f in plane.PARTITION_FIELDS]
    assert plane_names[: len(base_names)] == base_names


def test_effective_rate_is_floored_by_the_shared_clients_own_throttle() -> None:
    """240/min is the governor ceiling; the client's 0.35s throttle is the real floor."""
    budget = plane.rate_budget_receipt()
    expected = 60.0 / tc._THROTTLE.get("stk_mins", tc._DEFAULT_THROTTLE)
    assert budget["client_floor_calls_per_minute"] == pytest.approx(expected, abs=1e-4)
    assert budget["effective_calls_per_minute"] == pytest.approx(
        min(plane.RATE_CEILING_CALLS_PER_MINUTE, expected), abs=1e-4
    )
    assert budget["effective_calls_per_minute"] <= plane.RATE_CEILING_CALLS_PER_MINUTE


# --------------------------------------------------------------------------------------
# Chunk planning math
# --------------------------------------------------------------------------------------


def test_row_budget_never_exceeds_the_documented_cap() -> None:
    for frequency in plane.ALLOWED_FREQUENCIES:
        per_session = plane.max_bars_per_session(frequency)
        per_chunk = plane.sessions_per_chunk(frequency)
        assert per_chunk * per_session <= plane.MAX_ROWS_PER_RESPONSE
        # ...and one more session WOULD exceed it: the split is tight, not lazy.
        assert (per_chunk + 1) * per_session > plane.MAX_ROWS_PER_RESPONSE


def test_one_minute_chunk_is_29_sessions() -> None:
    assert plane.max_bars_per_session("1min") == 268
    assert plane.sessions_per_chunk("1min") == 29


def test_chunk_boundaries_split_exactly_at_the_cap() -> None:
    per_chunk = plane.sessions_per_chunk("1min")
    sessions = make_sessions(per_chunk * 2 + 1)
    calendar = make_calendar(sessions)
    plan = plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=calendar,
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=Path("/nonexistent"),
    )
    (partition,) = plan.partitions
    assert [chunk.session_count for chunk in partition.chunks] == [
        per_chunk,
        per_chunk,
        1,
    ]
    assert partition.chunks[0].start_date == sessions[0]
    assert partition.chunks[0].end_date == sessions[per_chunk - 1]
    assert partition.chunks[1].start_date == sessions[per_chunk]
    assert plan.call_count == 3
    assert all(
        chunk.projected_max_rows <= plane.MAX_ROWS_PER_RESPONSE
        for chunk in partition.chunks
    )


def test_years_never_share_a_chunk() -> None:
    sessions = make_sessions(3) + make_sessions(3, start=date(ANCHOR_YEAR + 1, 1, 2))
    plan = plane.plan_backfill(
        universe=make_universe(
            [TICKER], years={TICKER: {ANCHOR_YEAR, ANCHOR_YEAR + 1}}
        ),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=Path("/nonexistent"),
    )
    assert {p.year for p in plan.partitions} == {ANCHOR_YEAR, ANCHOR_YEAR + 1}
    for partition in plan.partitions:
        for chunk in partition.chunks:
            assert chunk.start_date.year == chunk.end_date.year == partition.year


def test_holiday_empty_range_plans_zero_calls() -> None:
    """A requested window containing no sessions must cost nothing, not one empty call."""
    sessions = make_sessions(5)
    gap_start = sessions[-1] + timedelta(days=1)
    plan = plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=gap_start,
        end=gap_start + timedelta(days=6),
        store_root=Path("/nonexistent"),
    )
    assert plan.partitions == ()
    assert plan.call_count == 0


def test_event_years_scope_skips_years_the_ticker_has_no_events_in() -> None:
    sessions = make_sessions(3) + make_sessions(3, start=date(ANCHOR_YEAR + 1, 1, 2))
    universe = make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}})
    kwargs = {
        "universe": universe,
        "calendar": make_calendar(sessions),
        "frequency": "1min",
        "start": sessions[0],
        "end": sessions[-1],
        "store_root": Path("/nonexistent"),
    }
    scoped = plane.plan_backfill(year_scope="event-years", **kwargs)
    every = plane.plan_backfill(year_scope="all-years", **kwargs)
    assert {p.year for p in scoped.partitions} == {ANCHOR_YEAR}
    assert {p.year for p in every.partitions} == {ANCHOR_YEAR, ANCHOR_YEAR + 1}
    assert scoped.all_years_call_count == every.call_count > scoped.call_count


def test_inverted_range_and_unknown_frequency_are_held() -> None:
    universe = make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}})
    calendar = make_calendar(make_sessions(3))
    with pytest.raises(plane.MinutesPlaneHeld):
        plane.plan_backfill(
            universe=universe,
            calendar=calendar,
            frequency="1min",
            start=date(ANCHOR_YEAR, 3, 1),
            end=date(ANCHOR_YEAR, 1, 1),
            store_root=Path("/nonexistent"),
        )
    with pytest.raises(plane.MinutesPlaneHeld):
        plane.plan_backfill(
            universe=universe,
            calendar=calendar,
            frequency="2min",
            start=date(ANCHOR_YEAR, 1, 1),
            end=date(ANCHOR_YEAR, 3, 1),
            store_root=Path("/nonexistent"),
        )


# --------------------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------------------


def _plan_against(root: Path, sessions: list[date]) -> plane.BackfillPlan:
    return plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=root,
        manifest=plane.read_manifest(root),
    )


def test_replanning_skips_a_fetched_clean_partition_exactly(tmp_path: Path) -> None:
    root = tmp_path / "store"
    sessions = make_sessions(3)
    before = _plan_against(root, sessions)
    assert before.call_count == 1 and before.partitions[0].status == "planned"

    records = normalized(sessions[0])
    result = install(root, records)
    plane.write_manifest(
        root,
        [
            plane.coverage_row(
                frequency="1min",
                ticker=TICKER,
                year=ANCHOR_YEAR,
                status="fetched",
                request_sha256=before.partitions[0].request_sha256,
                chunk_count=1,
                planned_session_count=3,
                partition_path_value=result.partition_path,
                row_count=result.row_count,
            )
        ],
        generated_at=OBSERVED_AT,
    )

    after = _plan_against(root, sessions)
    assert after.partitions[0].status == "skipped_fetched_clean"
    assert after.call_count == 0


def test_ledger_fetched_without_a_partition_on_disk_is_replanned(
    tmp_path: Path,
) -> None:
    """A ledger row is a claim; the store is the evidence.  The store wins."""
    root = tmp_path / "store"
    sessions = make_sessions(3)
    plane.write_manifest(
        root,
        [
            plane.coverage_row(
                frequency="1min",
                ticker=TICKER,
                year=ANCHOR_YEAR,
                status="fetched",
                request_sha256="00" * 32,
                chunk_count=1,
                planned_session_count=3,
                partition_path_value=str(root / "missing"),
                row_count=99,
            )
        ],
        generated_at=OBSERVED_AT,
    )
    assert _plan_against(root, sessions).partitions[0].status == "planned"


def test_recorded_contradiction_blocks_rather_than_silently_refetching(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    sessions = make_sessions(3)
    plane.write_manifest(
        root,
        [
            plane.coverage_row(
                frequency="1min",
                ticker=TICKER,
                year=ANCHOR_YEAR,
                status="contradiction",
                request_sha256="00" * 32,
                chunk_count=1,
                planned_session_count=3,
                partition_path_value=str(root / "p"),
                contradiction_reason="vendor revised rows",
            )
        ],
        generated_at=OBSERVED_AT,
    )
    plan = _plan_against(root, sessions)
    assert plan.partitions[0].status == "blocked_contradiction"
    assert plan.call_count == 0


# --------------------------------------------------------------------------------------
# Keep-first store
# --------------------------------------------------------------------------------------


def test_identical_rerun_is_a_byte_preserving_no_op(tmp_path: Path) -> None:
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION)
    first = install(root, records)
    assert first.status == "written"
    parquet = Path(first.partition_path) / "part.parquet"
    before = parquet.read_bytes()

    second = install(root, records)
    assert second.status == "unchanged"
    assert second.receipt_hash == first.receipt_hash
    assert parquet.read_bytes() == before


def test_revised_vendor_rows_raise_and_never_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "store"
    first = install(root, normalized(ANCHOR_FIRST_SESSION))
    parquet = Path(first.partition_path) / "part.parquet"
    original = parquet.read_bytes()

    revised = normalized(ANCHOR_FIRST_SESSION, price_scale=2)
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="REVISED"):
        install(root, revised)
    assert parquet.read_bytes() == original


def test_changed_pre_normalization_rows_raise_even_when_normalized_rows_match(
    tmp_path: Path,
) -> None:
    """Same normalized output from a different vendor payload is still a revision."""
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION)
    install(root, records, source_hash="ab" * 32)
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="pre-normalization"):
        install(root, records, source_hash="cd" * 32)


def test_partial_bundle_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "store"
    result = install(root, normalized(ANCHOR_FIRST_SESSION))
    (Path(result.partition_path) / "receipt.json").unlink()
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="partial"):
        install(root, normalized(ANCHOR_FIRST_SESSION))


def test_partition_layout_prefixes_only_the_columns_that_collide() -> None:
    path = plane.partition_path(
        Path("/store"), frequency="1min", ticker=TICKER, year=ANCHOR_YEAR
    )
    assert path.parts[-3:] == ("by_frequency=1min", f"by_ticker={TICKER}", "year=2024")
    columns = {f.name for f in plane.PARTITION_FIELDS}
    assert {"frequency", "ticker"} <= columns
    assert "year" not in columns


# --------------------------------------------------------------------------------------
# Schema round-trip
# --------------------------------------------------------------------------------------


def test_partition_round_trips_through_parquet(tmp_path: Path) -> None:
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION, bars=4, zero_volume_at=2)
    result = install(root, records)
    reloaded = plane.read_partition_records(Path(result.partition_path))
    assert reloaded == records
    assert plane.canonical_hash(reloaded) == result.data_hash
    verified = plane.verify_partition_bundle(
        Path(result.partition_path),
        identity=plane.partition_identity(
            frequency="1min", ticker=TICKER, year=ANCHOR_YEAR
        ),
    )
    assert verified == records


def test_arrow_schema_pins_the_base_contract_digest() -> None:
    schema = plane.arrow_schema()
    metadata = {key.decode(): value.decode() for key, value in schema.metadata.items()}
    assert (
        metadata["base_contract_sha256"] == plane.BASE_ENDPOINT_CONTRACT.contract_hash
    )
    assert metadata["partition_schema_version"] == plane.PARTITION_SCHEMA_VERSION
    assert schema.field("open_cents").type == "int64"
    assert schema.field("trade_time_utc").type == "string"


def test_manifest_validates_against_the_versioned_contract(tmp_path: Path) -> None:
    root = tmp_path / "store"
    result = install(root, normalized(ANCHOR_FIRST_SESSION))
    manifest = plane.write_manifest(
        root,
        [
            plane.coverage_row(
                frequency="1min",
                ticker=TICKER,
                year=ANCHOR_YEAR,
                status="fetched",
                request_sha256="11" * 32,
                chunk_count=1,
                planned_session_count=1,
                partition_path_value=result.partition_path,
                row_count=result.row_count,
                receipt_sha256=result.receipt_hash,
                observed_at_utc=OBSERVED_AT.isoformat(),
            )
        ],
        generated_at=OBSERVED_AT,
    )
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)

    ledger = plane.read_manifest(root)
    assert list(ledger.columns) == list(plane.COVERAGE_COLUMNS)
    row_schema = {**schema["$defs"]["coverageRow"], "$defs": schema["$defs"]}
    for row in json.loads(ledger.to_json(orient="records")):
        jsonschema.validate(row, row_schema)


def test_manifest_refuses_duplicate_partition_keys(tmp_path: Path) -> None:
    duplicate = plane.coverage_row(
        frequency="1min",
        ticker=TICKER,
        year=ANCHOR_YEAR,
        status="planned",
        request_sha256="11" * 32,
        chunk_count=1,
        planned_session_count=1,
        partition_path_value="p",
    )
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="duplicate"):
        plane.write_manifest(tmp_path, [duplicate, dict(duplicate)])


# --------------------------------------------------------------------------------------
# Normalization: zero volume, truncation, off-tick prices, clocks
# --------------------------------------------------------------------------------------


def test_zero_volume_bar_is_retained_and_classified() -> None:
    records = normalized(ANCHOR_FIRST_SESSION, bars=3, zero_volume_at=1)
    assert len(records) == 3, "a zero-volume bar must never be dropped"
    assert [r["bar_class"] for r in records] == [
        plane.BAR_CLASS_TRADED,
        plane.BAR_CLASS_ZERO_VOLUME_FLAT,
        plane.BAR_CLASS_TRADED,
    ]
    stale = records[1]
    assert stale["open_cents"] == stale["close_cents"] == stale["high_cents"]
    assert stale["volume"] == 0.0


@pytest.mark.parametrize(
    ("volume", "amount", "flat", "expected"),
    [
        (100.0, 1000.0, False, plane.BAR_CLASS_TRADED),
        (0.0, 0.0, True, plane.BAR_CLASS_ZERO_VOLUME_FLAT),
        (0.0, 0.0, False, plane.BAR_CLASS_ZERO_VOLUME_INCONSISTENT),
        (0.0, 5.0, True, plane.BAR_CLASS_ZERO_VOLUME_INCONSISTENT),
        (100.0, 0.0, False, plane.BAR_CLASS_VOLUME_WITHOUT_AMOUNT),
    ],
)
def test_bar_classification_table(
    volume: float, amount: float, flat: bool, expected: str
) -> None:
    high = 1000 if flat else 1002
    assert (
        plane.classify_bar(
            volume=volume,
            amount=amount,
            open_cents=1000,
            high_cents=high,
            low_cents=1000,
            close_cents=1000,
        )
        == expected
    )


def test_negative_volume_is_refused() -> None:
    with pytest.raises(plane.MinutesPlaneIntegrityError):
        plane.classify_bar(
            volume=-1.0,
            amount=0.0,
            open_cents=1,
            high_cents=1,
            low_cents=1,
            close_cents=1,
        )


def test_off_tick_price_is_refused_not_rounded() -> None:
    frame = minute_frame(ANCHOR_FIRST_SESSION, bars=1)
    frame.loc[0, "open"] = "10.005"
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="quote tick"):
        plane.normalize_minute_rows(
            frame, ticker=TICKER, frequency="1min", year=ANCHOR_YEAR
        )


def test_exact_decimal_prices_survive_a_float_hostile_value() -> None:
    """0.07 + 0.01 style values must not drift; parsing goes through text."""
    assert plane.quote_price_cents("1234.07", field_name="open") == 123407
    assert plane.quote_price_cents(1234.07, field_name="open") == 123407


def test_row_at_the_documented_cap_is_treated_as_truncated() -> None:
    chunk = plane.ChunkPlan(
        frequency="1min",
        ticker=TICKER,
        year=ANCHOR_YEAR,
        chunk_index=0,
        start_date=ANCHOR_FIRST_SESSION,
        end_date=ANCHOR_FIRST_SESSION,
        session_count=1,
        projected_max_rows=268,
    )
    capped = pd.DataFrame(
        [minute_rows(ANCHOR_FIRST_SESSION, bars=1)[0]] * plane.MAX_ROWS_PER_RESPONSE,
        columns=list(plane.BASE_VENDOR_FIELDS),
    )
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="TRUNCATED"):
        plane._fetch_chunk(
            chunk,
            query=lambda *a, **k: capped,
            governor=plane.RateGovernor(clock=lambda: 0.0, sleeper=lambda _: None),
        )


def test_row_from_another_ticker_or_year_is_refused() -> None:
    frame = minute_frame(ANCHOR_FIRST_SESSION, bars=1, ticker="000001.SZ")
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="ticker"):
        plane.normalize_minute_rows(
            frame, ticker=TICKER, frequency="1min", year=ANCHOR_YEAR
        )
    frame = minute_frame(ANCHOR_FIRST_SESSION, bars=1)
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="partition year"):
        plane.normalize_minute_rows(
            frame, ticker=TICKER, frequency="1min", year=ANCHOR_YEAR + 1
        )


def test_utc_runner_produces_shanghai_stamps() -> None:
    """CI runs UTC; a naive vendor stamp must still land on the Shanghai clock."""
    records = normalized(ANCHOR_FIRST_SESSION, bars=1)
    assert records[0]["trade_time"].startswith(
        f"{ANCHOR_FIRST_SESSION.isoformat()}T09:31"
    )
    assert records[0]["trade_time"].endswith("+08:00")
    assert records[0]["trade_time_utc"].startswith(
        f"{ANCHOR_FIRST_SESSION.isoformat()}T01:31"
    )
    assert records[0]["session_segment"] == plane.SESSION_SEGMENT_REGULAR


# --------------------------------------------------------------------------------------
# Rate governor
# --------------------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_governor_paces_exactly_at_the_ceiling() -> None:
    clock = FakeClock()
    governor = plane.RateGovernor(240, clock=clock, sleeper=clock.sleep)
    for _ in range(240):
        assert governor.acquire() == 0.0, "the first window must never sleep"
    assert clock.now == 0.0
    assert governor.acquire() == pytest.approx(60.0)
    assert clock.now == pytest.approx(60.0)
    assert governor.total_calls == 241


def test_governor_sustains_the_ceiling_over_two_windows() -> None:
    clock = FakeClock()
    governor = plane.RateGovernor(60, clock=clock, sleeper=clock.sleep)
    for _ in range(180):
        governor.acquire()
    # 180 calls at 60/min cannot finish before 2 full windows have elapsed.
    assert clock.now >= 120.0
    assert governor.total_calls == 180


def test_governor_refuses_a_ceiling_above_the_plane_or_the_pool() -> None:
    with pytest.raises(plane.MinutesPlaneHeld, match="plane_ceiling"):
        plane.RateGovernor(241)
    with pytest.raises(plane.MinutesPlaneHeld, match="premium_pool"):
        plane.RateGovernor(301)
    with pytest.raises(plane.MinutesPlaneHeld):
        plane.RateGovernor(0)


def test_wall_clock_estimate_uses_the_effective_rate_not_the_ceiling() -> None:
    estimate = plane.wall_clock_estimate(1_000)
    effective = float(estimate["effective_calls_per_minute"])
    assert estimate["pacing_floor_seconds"] == pytest.approx(1_000 / effective * 60.0)
    assert "UNMEASURED" in str(estimate["nonclaim"])


# --------------------------------------------------------------------------------------
# Reconciliation gate
# --------------------------------------------------------------------------------------


def daily_reference_from(records: list[dict[str, object]]) -> pd.DataFrame:
    """A synthetic NOMINAL daily bar that agrees with a minute tape by construction."""
    aggregate = plane.aggregate_regular_window(records)
    assert aggregate is not None
    return pd.DataFrame(
        [
            {
                "trade_date": records[0]["trade_date"],
                "ticker": records[0]["ticker"],
                "open_cents": aggregate["open_cents"],
                "high_cents": aggregate["high_cents"],
                "low_cents": aggregate["low_cents"],
                "close_cents": aggregate["close_cents"],
                "volume_lots": aggregate["volume_shares"] / plane.SHARES_PER_LOT,
                "amount_cny_thousands": aggregate["amount_cny"]
                / plane.CNY_PER_AMOUNT_UNIT,
            }
        ]
    )


def test_reconciliation_passes_on_a_coherent_store(tmp_path: Path) -> None:
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION, bars=4)
    install(root, records)
    report = plane.run_reconciliation_gate(root, daily=daily_reference_from(records))
    assert report["status"] == "executed"
    assert report["passed"] is True
    assert report["failure_count"] == 0
    assert report["sample_size_checked"] == 1


@pytest.mark.parametrize(
    ("corruption", "expected_check"),
    [
        ({"close_cents": 999_999}, "close_exact"),
        ({"high_cents": 1}, "high_within"),
        ({"low_cents": 999_999}, "low_within"),
        ({"volume_lots": 0.01}, "volume_within"),
        ({"amount_cny_thousands": 0.001}, "amount_within"),
    ],
)
def test_reconciliation_catches_a_corrupted_daily_reference(
    tmp_path: Path, corruption: dict[str, object], expected_check: str
) -> None:
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION, bars=4)
    install(root, records)
    daily = daily_reference_from(records)
    for column, value in corruption.items():
        daily.loc[0, column] = value
    report = plane.run_reconciliation_gate(root, daily=daily)
    assert report["passed"] is False
    assert report["failure_count"] == 1
    assert expected_check in report["failures"][0]["failed_checks"]


def test_reconciliation_catches_a_scaled_minute_tape(tmp_path: Path) -> None:
    """The classic corruption: a minute tape at the wrong price scale."""
    root = tmp_path / "store"
    honest = normalized(ANCHOR_FIRST_SESSION, bars=4)
    daily = daily_reference_from(honest)
    install(root, normalized(ANCHOR_FIRST_SESSION, bars=4, price_scale=10))
    report = plane.run_reconciliation_gate(root, daily=daily)
    assert report["passed"] is False
    assert "high_within" in report["failures"][0]["failed_checks"]


def test_open_mismatch_is_reported_but_never_fails_the_gate() -> None:
    """Auction stamping is an unpinned vendor convention; it must not manufacture reds."""
    aggregate = {
        "open_cents": 1000,
        "close_cents": 1010,
        "high_cents": 1020,
        "low_cents": 990,
        "volume_shares": 1000.0,
        "amount_cny": 10_000.0,
        "bar_count": 4,
    }
    daily = {
        "open_cents": 995,
        "close_cents": 1010,
        "high_cents": 1020,
        "low_cents": 990,
        "volume_lots": 20.0,
        "amount_cny_thousands": 20.0,
    }
    outcome = plane.reconcile_session(aggregate, daily)
    assert outcome["passed"] is True
    assert outcome["reported_checks"]["open_exact"] is False


def test_post_close_rows_are_excluded_from_the_daily_aggregate() -> None:
    session = ANCHOR_FIRST_SESSION
    frame = pd.DataFrame(
        minute_rows(session, bars=2)
        + [
            {
                "ts_code": VENDOR_TICKER,
                "trade_time": f"{session.isoformat()} 15:10:00",
                "open": "99.00",
                "close": "99.00",
                "high": "99.00",
                "low": "99.00",
                "vol": 500,
                "amount": 49_500.0,
            }
        ],
        columns=list(plane.BASE_VENDOR_FIELDS),
    )
    records = plane.normalize_minute_rows(
        frame, ticker=TICKER, frequency="1min", year=session.year
    )
    assert records[-1]["session_segment"] == plane.SESSION_SEGMENT_POST_CLOSE
    aggregate = plane.aggregate_regular_window(records)
    assert aggregate is not None
    assert aggregate["bar_count"] == 2
    assert aggregate["high_cents"] < 9_900


def test_absent_daily_plane_is_unavailable_not_a_pass(tmp_path: Path) -> None:
    root = tmp_path / "store"
    install(root, normalized(ANCHOR_FIRST_SESSION))
    report = plane.run_reconciliation_gate(root, daily=None)
    assert report["status"] == "unavailable_no_daily_reference_plane"
    assert report["passed"] is None


def test_adjusted_daily_reference_is_refused_as_a_basis(tmp_path: Path) -> None:
    """china_stocks_raw is split-adjusted and is a FORBIDDEN reconciliation basis."""
    store = tmp_path / "spine"
    partition = store / "daily" / f"year={ANCHOR_YEAR}" / "month=01"
    partition.mkdir(parents=True)
    frame = daily_reference_from(normalized(ANCHOR_FIRST_SESSION))
    frame["price_source_basis"] = "china_stocks_raw"
    frame.to_parquet(partition / "part.parquet")
    with pytest.raises(plane.MinutesPlaneIntegrityError, match="FORBIDDEN"):
        plane.load_daily_reference(store)


def test_verify_store_reports_ledger_drift(tmp_path: Path) -> None:
    root = tmp_path / "store"
    records = normalized(ANCHOR_FIRST_SESSION, bars=4)
    install(root, records)
    report = plane.verify_store(root, daily=daily_reference_from(records))
    assert report["partitions_missing_from_ledger"] == [f"1min/{TICKER}/{ANCHOR_YEAR}"]
    assert report["passed"] is False


def test_verify_store_detects_tampered_parquet_bytes(tmp_path: Path) -> None:
    root = tmp_path / "store"
    result = install(root, normalized(ANCHOR_FIRST_SESSION))
    parquet = Path(result.partition_path) / "part.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"tamper")
    report = plane.verify_store(root, daily=None)
    assert report["receipt_failures"]
    assert "parquet bytes" in report["receipt_failures"][0]["error"]


# --------------------------------------------------------------------------------------
# Execution gate
# --------------------------------------------------------------------------------------


def test_tp0_probe_receipt_is_required_before_any_backfill(tmp_path: Path) -> None:
    with pytest.raises(
        plane.MinutesPlaneHeld, match="tp0_stk_mins_probe_receipt_absent"
    ):
        plane.require_tp0_probe_receipt(tmp_path / "empty")


def test_tp0_probe_without_an_access_witness_is_refused(tmp_path: Path) -> None:
    directory = (
        tmp_path
        / "stk_mins"
        / "by_frequency=1min"
        / "by_trade_date=2026-08-07"
        / f"by_scope=ticker-{TICKER}"
    )
    directory.mkdir(parents=True)
    (directory / "receipt.json").write_text(
        json.dumps({"access_observation_receipt": {"observation": "held"}}),
        encoding="utf-8",
    )
    with pytest.raises(plane.MinutesPlaneHeld, match="does_not_witness_access"):
        plane.require_tp0_probe_receipt(tmp_path)


def test_tp0_probe_receipt_reports_contract_agreement(tp0_probe_root: Path) -> None:
    reference = plane.require_tp0_probe_receipt(tp0_probe_root)
    assert reference["contract_agrees"] is True
    assert reference["plane_base_contract_sha256"] == (
        plane.BASE_ENDPOINT_CONTRACT.contract_hash
    )


def test_execute_enforces_tp0_even_when_the_caller_skipped_it(tmp_path: Path) -> None:
    sessions = make_sessions(2)
    empty_plan = plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=tmp_path / "store",
    )
    with pytest.raises(plane.MinutesPlaneHeld):
        plane.execute_backfill(empty_plan, store_root=tmp_path / "store")


def test_execute_writes_a_partition_and_a_ledger_row(
    tmp_path: Path, tp0_probe_root: Path
) -> None:
    root = tmp_path / "store"
    sessions = make_sessions(2)
    backfill = plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=root,
    )
    calls: list[dict[str, object]] = []

    def fake_query(api_name: str, fields: str = "", **params: object) -> pd.DataFrame:
        calls.append({"api_name": api_name, **params})
        return pd.concat(
            [minute_frame(session, bars=2) for session in sessions], ignore_index=True
        )

    clock = FakeClock()
    result = plane.execute_backfill(
        backfill,
        store_root=root,
        addons_root=tp0_probe_root,
        query=fake_query,
        governor=plane.RateGovernor(240, clock=clock, sleeper=clock.sleep),
    )
    assert result["status"] == "executed"
    assert len(calls) == 1
    assert calls[0]["ts_code"] == VENDOR_TICKER and calls[0]["freq"] == "1min"

    ledger = plane.read_manifest(root)
    assert len(ledger) == 1
    row = ledger.to_dict(orient="records")[0]
    assert row["status"] == "fetched"
    assert row["row_count"] == 4
    assert row["observed_session_count"] == 2
    assert plane._partition_is_on_disk(
        root, frequency="1min", ticker=TICKER, year=ANCHOR_YEAR
    )

    replan = plane.plan_backfill(
        universe=make_universe([TICKER], years={TICKER: {ANCHOR_YEAR}}),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=root,
        manifest=plane.read_manifest(root),
    )
    assert replan.call_count == 0


def test_execute_records_a_bad_partition_and_keeps_going(
    tmp_path: Path, tp0_probe_root: Path
) -> None:
    """One poisoned ticker-year must not abort a multi-hour backfill, nor vanish."""
    root = tmp_path / "store"
    sessions = make_sessions(2)
    backfill = plane.plan_backfill(
        universe=make_universe(
            [TICKER, OTHER_TICKER],
            years={TICKER: {ANCHOR_YEAR}, OTHER_TICKER: {ANCHOR_YEAR}},
        ),
        calendar=make_calendar(sessions),
        frequency="1min",
        start=sessions[0],
        end=sessions[-1],
        store_root=root,
    )

    def fake_query(api_name: str, fields: str = "", **params: object) -> pd.DataFrame:
        vendor = str(params["ts_code"])
        frame = minute_frame(sessions[0], bars=2, ticker=vendor)
        if vendor == OTHER_TICKER:
            frame.loc[0, "open"] = "10.005"  # off-tick: poisons this partition only
        return frame

    clock = FakeClock()
    plane.execute_backfill(
        backfill,
        store_root=root,
        addons_root=tp0_probe_root,
        query=fake_query,
        governor=plane.RateGovernor(240, clock=clock, sleeper=clock.sleep),
    )
    ledger = plane.read_manifest(root).set_index("ticker")
    assert ledger.loc[TICKER, "status"] == "fetched"
    assert ledger.loc[OTHER_TICKER, "status"] == "contradiction"
    assert "quote tick" in str(ledger.loc[OTHER_TICKER, "contradiction_reason"])
    assert not plane._partition_is_on_disk(
        root, frequency="1min", ticker=OTHER_TICKER, year=ANCHOR_YEAR
    )


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def test_cli_plan_is_offline_and_emits_the_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def exploding_query(*args: object, **kwargs: object) -> None:
        raise AssertionError("plan mode must never call the vendor")

    monkeypatch.setattr(tc, "query", exploding_query)
    universe_file = tmp_path / "universe.txt"
    universe_file.write_text(f"# comment\n{TICKER}\n\n", encoding="utf-8")
    catalog = tmp_path / "limit_events.parquet"
    pd.DataFrame(
        {
            "date": [pd.Timestamp(day) for day in make_sessions(40)],
            "ticker": [TICKER] * 40,
        }
    ).to_parquet(catalog)

    assert (
        cli.main(
            [
                "--plan",
                "--universe",
                "file",
                "--universe-file",
                str(universe_file),
                "--frequency",
                "1min",
                "--year-scope",
                "all-years",
                "--session-source",
                "event-catalog",
                "--event-catalog",
                str(catalog),
                "--start",
                ANCHOR_FIRST_SESSION.isoformat(),
                "--end",
                f"{ANCHOR_YEAR}-12-31",
                "--store-root",
                str(tmp_path / "store"),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "planned_no_network_no_write"
    assert payload["call_count"] == 2  # 40 sessions -> 29 + 11
    assert payload["wall_clock"]["effective_calls_per_minute"] > 0
    assert not (tmp_path / "store").exists(), "plan mode must not write"


def test_cli_execute_holds_on_the_tp0_sequencing_law(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(
            [
                "--execute",
                "--store-root",
                str(tmp_path / "store"),
                "--addons-root",
                str(tmp_path / "no-probes"),
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["reason_code"]
        == "tp0_stk_mins_probe_receipt_absent_backfill_is_sequenced"
    )
    assert "TP-0" in payload["sequencing_law"]


def test_cli_spine_universe_is_explicitly_deferred(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            ["--plan", "--universe", "spine", "--store-root", str(tmp_path / "store")]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["reason_code"]
        == "spine_full_a_universe_is_deferred_see_takeover_lane_b"
    )


def test_cli_module_entrypoint_runs_without_a_token() -> None:
    """A keyless invocation must produce usage text, never a traceback."""
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(ROOT)}
    if sys.platform.startswith("linux"):
        library_dir = Path(str(sysconfig.get_config_var("LIBDIR"))).resolve()
        library_name = str(sysconfig.get_config_var("LDLIBRARY"))
        assert (library_dir / library_name).is_file()
        environment["LD_LIBRARY_PATH"] = str(library_dir)
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.backfill_tushare_minutes", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0
    assert "--verify" in completed.stdout
