"""Hostile tests for the private W1B.3B technical actual-output store."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory_technical_observation as technical
from engine.neuralweb import market_memory_technical_store as store

ROOT = Path(__file__).resolve().parents[1]
STORE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/technicals_actual_output_store.v1.schema.json"
)
CAPTURE_SCHEMA_PATH = (
    ROOT
    / "contracts/market_memory/technicals_actual_output_capture_receipt.v1.schema.json"
)
MANIFEST_MODIFIED = "Mon, 10 Aug 2026 01:37:37 GMT"
SPY_MODIFIED = "Mon, 10 Aug 2026 01:32:56 GMT"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _git_blob_oid(body: bytes) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    return hashlib.sha1(framed).hexdigest()


def _sessions(*, end: date = date(2026, 8, 7), count: int = 41) -> list[date]:
    output: list[date] = []
    cursor = end
    while len(output) < count:
        if technical.is_frozen_v1_xnys_session(cursor):
            output.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(output))


def _frame(*, end: date = date(2026, 8, 7)) -> pd.DataFrame:
    dates = _sessions(end=end)
    closes = [float(100 + index) for index in range(len(dates))]
    return pd.DataFrame(
        {
            "open": [value - 0.25 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": pd.Series(
                [1_000_000 + index for index in range(len(dates))],
                dtype="int64",
            ).array,
            "transactions": pd.Series(
                [10_000 + index for index in range(len(dates))],
                dtype="int64",
            ).array,
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=True)
    return buffer.getvalue()


def _manifest(frame: pd.DataFrame) -> dict[str, object]:
    first = frame.index[0].date()
    last = frame.index[-1].date()
    gaps = [
        (current.date() - previous.date()).days
        for previous, current in zip(frame.index, frame.index[1:])
    ]
    tickers = [f"T{index:03d}.parquet" for index in range(99)] + ["SPY.parquet"]
    files = sorted([*tickers, "_backfill_state.json"])
    return {
        "dir": "massive_stock_day",
        "count": len(files),
        "files": files,
        "store": {
            "store": "massive_stock_day",
            "n_tickers": len(tickers),
            "latest_date": last.isoformat(),
            "updated_at": "2026-08-10T01:35:00.000000+00:00",
            "coverage": {
                "first_day": first.isoformat(),
                "last_day": last.isoformat(),
                "n_processed_days": len(frame),
                "max_missing_run_weekdays": 0,
                "max_missing_run_weekdays_recent": 0,
                "recent_window_bdays": 90,
                "missing_sample": [],
            },
            "anchor": {
                "ticker": "SPY",
                "first": first.isoformat(),
                "last": last.isoformat(),
                "n_rows": len(frame),
                "max_gap_calendar_days": max(gaps),
            },
        },
    }


def _response(
    *,
    url: str,
    body: bytes,
    content_type: str,
    last_modified: str,
    head: bool = False,
) -> technical.HttpResponse:
    return technical.HttpResponse(
        status=200,
        url=url,
        headers=(
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("ETag", f'"{hashlib.md5(body).hexdigest()}"'),
            ("Last-Modified", last_modified),
        ),
        body=b"" if head else body,
    )


def _responses(
    *,
    frame: pd.DataFrame | None = None,
    manifest_modified: str = MANIFEST_MODIFIED,
    spy_modified: str = SPY_MODIFIED,
) -> list[technical.HttpResponse]:
    source_frame = _frame() if frame is None else frame
    spy_body = _parquet_bytes(source_frame)
    manifest_body = _canonical(_manifest(source_frame))
    manifest_response = _response(
        url=technical.MANIFEST_URL,
        body=manifest_body,
        content_type="application/json",
        last_modified=manifest_modified,
    )
    spy_head = _response(
        url=technical.SPY_PARQUET_URL,
        body=spy_body,
        content_type="application/octet-stream",
        last_modified=spy_modified,
        head=True,
    )
    return [
        manifest_response,
        spy_head,
        replace(spy_head, body=spy_body),
        spy_head,
        manifest_response,
    ]


class _Fetcher:
    def __init__(self, responses: list[technical.HttpResponse]) -> None:
        self.responses = list(responses)

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str]
    ) -> technical.HttpResponse:
        del method, url, headers
        if not self.responses:
            raise AssertionError("unexpected technical source request")
        return self.responses.pop(0)


def _pinned_sources(
    *, pinned_commit: str = "1" * 40
) -> technical.PinnedTechnicalSources:
    bodies = {
        "canary_identity_config": (
            ROOT / "config/market_memory_canary.v1.json"
        ).read_bytes(),
        "xnys_calendar_module": (ROOT / "lib/nyse_calendar.py").read_bytes(),
        "massive_entitlement_record": (
            ROOT / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
        ).read_bytes(),
        "technical_price_basis_contract": (
            ROOT / "config/market_memory_technical_price_basis.v1.json"
        ).read_bytes(),
    }
    return technical.PinnedTechnicalSources(
        pinned_commit=pinned_commit,
        canary_config_body=bodies["canary_identity_config"],
        calendar_module_body=bodies["xnys_calendar_module"],
        license_record_body=bodies["massive_entitlement_record"],
        price_basis_contract_body=bodies["technical_price_basis_contract"],
        git_blob_oids=tuple(
            (role, _git_blob_oid(body)) for role, body in bodies.items()
        ),
    )


def _bundle(
    *,
    frame: pd.DataFrame | None = None,
    manifest_modified: str = MANIFEST_MODIFIED,
    spy_modified: str = SPY_MODIFIED,
    pinned_commit: str = "1" * 40,
) -> technical.TechnicalSnapshotBundle:
    fetcher = _Fetcher(
        _responses(
            frame=frame,
            manifest_modified=manifest_modified,
            spy_modified=spy_modified,
        )
    )
    fetched = technical.fetch_current_spy_daily_inputs(fetcher=fetcher)
    assert fetcher.responses == []
    return technical.project_current_spy_raw_close_ratio(
        technical.PinnedTechnicalInputs(
            fetched=fetched,
            pinned_sources=_pinned_sources(pinned_commit=pinned_commit),
        )
    )


def _clock(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    return lambda: parsed.astimezone(timezone.utc)


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed_at: str = "2026-08-10T02:00:00Z",
    candidate: technical.TechnicalSnapshotBundle | None = None,
) -> tuple[Path, store.StoredTechnicalActualOutput]:
    root = tmp_path / "technicals-v1"
    monkeypatch.setattr(store, "_utc_now", _clock(observed_at))
    stored = store.capture_technical_actual_output(
        root,
        bundle=_bundle() if candidate is None else candidate,
    )
    return root, stored


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value))


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_capture_is_private_exact_context_only_and_schema_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    manifest = _read_json(root / "store_manifest.json")
    receipt = stored.capture_receipt
    store_schema = json.loads(STORE_SCHEMA_PATH.read_text(encoding="utf-8"))
    capture_schema = json.loads(CAPTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(store_schema)
    Draft202012Validator.check_schema(capture_schema)
    Draft202012Validator(store_schema).validate(manifest)
    Draft202012Validator(capture_schema).validate(receipt)

    assert manifest["profile"] == store.STORE_PROFILE
    assert receipt["actual_output_capture"] is True
    assert receipt["clocks"] == {
        "first_observed_at": "2026-08-10T02:00:00Z",
        "available_at": "2026-08-10T02:00:00Z",
    }
    assert receipt["freshness"] == {
        "policy": ("r2_manifest_26h_prior_xnys_0200z_finality_max_one_lag.v1"),
        "observed_utc_date": "2026-08-10",
        "manifest_last_modified": MANIFEST_MODIFIED,
        "manifest_age_seconds": 1343,
        "manifest_max_age_seconds": 93600,
        "latest_completed_session": "2026-08-07",
        "previous_completed_session": "2026-08-06",
        "latest_completed_via": "prior_session_after_0200z_finality_buffer",
        "latest_completed_not_before": "2026-08-08T02:00:00Z",
        "accepted_session": "2026-08-07",
        "session_lag": 0,
        "accepted_via": "latest_completed_session",
    }
    assert set(receipt["source_bodies"]) == {
        "publish_manifest",
        "spy_daily_parquet",
        "canary_identity_config",
        "xnys_calendar_module",
        "massive_entitlement_record",
        "technical_price_basis_contract",
    }
    assert receipt["source_bodies"]["massive_entitlement_record"]["repo_path"] == (
        "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
    )
    price_basis_ref = receipt["source_bodies"]["technical_price_basis_contract"]
    assert price_basis_ref["repo_path"] == (
        "config/market_memory_technical_price_basis.v1.json"
    )
    assert price_basis_ref["sha256"] == (
        "ce0244d9c18e3fdcb621c7ced6e3700cb8cb43ff0952b355b82d0542ed6b1be9"
    )
    for value in (manifest, receipt):
        assert value["authority"]["context_only"] is True
        assert value["authority"]["proposal_weight"] == 0
        assert all(
            value["authority"][field] is False
            for field in (
                "may_rank",
                "may_gate",
                "may_size",
                "may_escalate",
                "may_trade",
                "may_originate",
                "may_select_options_candidate",
                "may_execute",
                "may_write_options_episode",
                "may_append_outcome",
                "may_train_prophet",
            )
        )
        assert value["evidence_policy"]["raw_unadjusted_close_ratio"] is True
        assert value["evidence_policy"]["provider_price_basis_contract_bound"] is True
        assert value["evidence_policy"]["basis_authenticated_by_shape"] is False
        assert value["evidence_policy"]["economic_return"] is False
        assert value["evidence_policy"]["training_eligible"] is False
        assert value["evidence_policy"]["promotion_eligible"] is False
    assert stored.bundle.feature_object["price_basis"]["raw_unadjusted"] is True
    assert stored.bundle.feature_object["price_basis"]["economic_return"] is False
    assert (
        stored.bundle.feature_object["price_basis"][
            "regular_session_close_authenticated"
        ]
        is False
    )
    assert len(list((root / "source_bodies").glob("*/*.bin"))) == 6
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(
        path.stat().st_mode & 0o777 == 0o600
        for path in root.rglob("*")
        if path.is_file()
    )


def test_schema_and_runtime_reject_unknown_authority_and_transport_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    manifest = _read_json(root / "store_manifest.json")
    receipt = stored.capture_receipt
    store_validator = Draft202012Validator(
        json.loads(STORE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    capture_validator = Draft202012Validator(
        json.loads(CAPTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )

    manifest_mutant = copy.deepcopy(manifest)
    manifest_mutant["authority"]["may_gate"] = True
    with pytest.raises(ValidationError):
        store_validator.validate(manifest_mutant)

    for mutate in (
        "unknown",
        "authority",
        "transport",
        "license",
        "config_digest",
        "calendar_digest",
        "license_digest",
        "basis_digest",
    ):
        mutant = copy.deepcopy(receipt)
        if mutate == "unknown":
            mutant["future_label"] = "forbidden"
        elif mutate == "authority":
            mutant["authority"]["may_train_prophet"] = True
        elif mutate == "transport":
            mutant["source_bodies"]["publish_manifest"]["url"] = "https://example.com/x"
        elif mutate == "license":
            mutant["source_bodies"]["massive_entitlement_record"]["repo_path"] = (
                "README.md"
            )
        elif mutate.endswith("_digest"):
            role = {
                "config_digest": "canary_identity_config",
                "calendar_digest": "xnys_calendar_module",
                "license_digest": "massive_entitlement_record",
                "basis_digest": "technical_price_basis_contract",
            }[mutate]
            digest = "f" * 64
            mutant["source_bodies"][role]["sha256"] = digest
            mutant["source_bodies"][role]["object_key"] = (
                f"source_bodies/{digest[:2]}/{digest}.bin"
            )
            mutant["capture_id"] = store._content_id(
                "mmactualcapture_", mutant, field="capture_id"
            )
        with pytest.raises(ValidationError):
            capture_validator.validate(mutant)
        with pytest.raises(store.MarketMemoryTechnicalStoreError):
            store._validate_receipt(mutant, store_id=receipt["store_id"])


def test_root_guard_rejects_broad_public_wrong_profile_and_symlinks(
    tmp_path: Path,
) -> None:
    for candidate in (
        Path("/"),
        Path.home(),
        tmp_path / "actual-output",
        tmp_path / "public" / "technicals-v1",
    ):
        with pytest.raises(store.MarketMemoryTechnicalStoreError):
            store.validate_technical_actual_output_store_root(candidate)

    target = tmp_path / "safe" / "technicals-v1"
    target.mkdir(parents=True, mode=0o700)
    linked = tmp_path / "technicals-v1"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryTechnicalStoreError, match="cannot be symlinks"
    ):
        store.validate_technical_actual_output_store_root(linked)

    real_parent = tmp_path / "real-parent"
    (real_parent / "technicals-v1").mkdir(parents=True, mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryTechnicalStoreError, match="cannot be symlinks"
    ):
        store.validate_technical_actual_output_store_root(
            linked_parent / "technicals-v1"
        )

    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(
        store.MarketMemoryTechnicalStoreError,
        match="repository or its descendants",
    ):
        store.validate_technical_actual_output_store_root(
            repository / "private" / "technicals-v1",
            repository_root=repository,
        )

    exposed = tmp_path / "exposed" / "technicals-v1"
    exposed.mkdir(parents=True, mode=0o755)
    exposed.chmod(0o755)
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="group or world"):
        store.validate_technical_actual_output_store_root(exposed)

    local_default = store.default_technical_actual_output_store_root(ROOT)
    assert local_default.name == "technicals-v1"
    assert ROOT not in local_default.parents


def test_invalid_bundle_fails_before_root_creation_or_clock_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _bundle()
    attacked = replace(
        candidate,
        feature_object_bytes=candidate.feature_object_bytes + b"\n",
    )

    def forbidden_clock() -> datetime:
        raise AssertionError("clock sampled before detached validation")

    monkeypatch.setattr(store, "_utc_now", forbidden_clock)
    root = tmp_path / "technicals-v1"
    with pytest.raises(
        store.MarketMemoryTechnicalCaptureError, match="detached validation"
    ):
        store.capture_technical_actual_output(root, bundle=attacked)
    assert not root.exists()


@pytest.mark.parametrize(
    ("end", "observed_at", "lag", "accepted_via"),
    [
        (date(2026, 8, 7), "2026-08-10T02:00:00Z", 0, "latest_completed_session"),
        (date(2026, 8, 6), "2026-08-10T02:00:00Z", 1, "one_completed_session_lag"),
    ],
)
def test_freshness_accepts_prior_latest_and_one_lag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    end: date,
    observed_at: str,
    lag: int,
    accepted_via: str,
) -> None:
    candidate = _bundle(frame=_frame(end=end))
    _root, stored = _capture(
        tmp_path / end.isoformat(),
        monkeypatch,
        observed_at=observed_at,
        candidate=candidate,
    )
    assert stored.capture_receipt["freshness"]["session_lag"] == lag
    assert stored.capture_receipt["freshness"]["accepted_via"] == accepted_via


@pytest.mark.parametrize(
    ("end", "observed_at", "modified", "latest", "not_before"),
    [
        (
            date(2026, 1, 2),
            "2026-01-06T00:53:00Z",
            "Tue, 06 Jan 2026 00:30:00 GMT",
            "2026-01-02",
            "2026-01-03T02:00:00Z",
        ),
        (
            date(2026, 1, 8),
            "2026-01-10T00:53:00Z",
            "Sat, 10 Jan 2026 00:30:00 GMT",
            "2026-01-08",
            "2026-01-09T02:00:00Z",
        ),
        (
            date(2026, 1, 5),
            "2026-01-06T02:00:00Z",
            "Tue, 06 Jan 2026 01:30:00 GMT",
            "2026-01-05",
            "2026-01-06T02:00:00Z",
        ),
    ],
)
def test_full_market_day_finality_buffer_steps_back_before_0200z(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    end: date,
    observed_at: str,
    modified: str,
    latest: str,
    not_before: str,
) -> None:
    candidate = _bundle(
        frame=_frame(end=end),
        manifest_modified=modified,
        spy_modified=modified,
    )
    _root, stored = _capture(
        tmp_path / observed_at.replace(":", "-"),
        monkeypatch,
        observed_at=observed_at,
        candidate=candidate,
    )
    freshness = stored.capture_receipt["freshness"]
    assert freshness["latest_completed_session"] == latest
    assert freshness["latest_completed_not_before"] == not_before
    assert freshness["session_lag"] == 0


@pytest.mark.parametrize(
    ("candidate", "observed_at", "message"),
    [
        (
            _bundle(frame=_frame(end=date(2026, 8, 5))),
            "2026-08-10T02:00:00Z",
            "one-completed-session",
        ),
        (
            _bundle(frame=_frame(end=date(2026, 8, 10))),
            "2026-08-10T23:59:59Z",
            "one-completed-session",
        ),
        (
            _bundle(
                frame=_frame(end=date(2026, 1, 5)),
                manifest_modified="Tue, 06 Jan 2026 00:30:00 GMT",
                spy_modified="Tue, 06 Jan 2026 00:30:00 GMT",
            ),
            "2026-01-06T00:53:00Z",
            "one-completed-session",
        ),
        (
            _bundle(
                frame=_frame(end=date(2026, 1, 9)),
                manifest_modified="Sat, 10 Jan 2026 00:30:00 GMT",
                spy_modified="Sat, 10 Jan 2026 00:30:00 GMT",
            ),
            "2026-01-10T00:53:00Z",
            "one-completed-session",
        ),
        (
            _bundle(
                manifest_modified="Mon, 10 Aug 2026 02:00:01 GMT",
                spy_modified="Mon, 10 Aug 2026 02:00:01 GMT",
            ),
            "2026-08-10T02:00:00Z",
            "newer than",
        ),
        (
            _bundle(
                manifest_modified="Sat, 08 Aug 2026 00:00:00 GMT",
                spy_modified="Sat, 08 Aug 2026 00:00:00 GMT",
            ),
            "2026-08-10T02:00:00Z",
            "26-hour",
        ),
    ],
)
def test_freshness_rejects_stale_future_manifest_or_session_without_capture_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate: technical.TechnicalSnapshotBundle,
    observed_at: str,
    message: str,
) -> None:
    root = tmp_path / message.replace(" ", "-") / "technicals-v1"
    monkeypatch.setattr(store, "_utc_now", _clock(observed_at))
    with pytest.raises(store.MarketMemoryTechnicalCaptureError, match=message):
        store.capture_technical_actual_output(root, bundle=candidate)
    assert not (root / "prepared").exists()
    assert not (root / "source_bodies").exists()
    assert store.load_technical_actual_output_generation(root)["captures"] == []


def test_manifest_exact_26_hour_boundary_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _bundle(
        manifest_modified="Sun, 09 Aug 2026 00:00:00 GMT",
        spy_modified="Sun, 09 Aug 2026 00:00:00 GMT",
    )
    _root, stored = _capture(
        tmp_path,
        monkeypatch,
        observed_at="2026-08-10T02:00:00Z",
        candidate=candidate,
    )
    assert stored.capture_receipt["freshness"]["manifest_age_seconds"] == 93600


def test_prepared_is_first_capture_write_and_crash_retry_reuses_clock_days_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "technicals-v1"
    candidate = _bundle()
    store.initialize_technical_actual_output_store(root)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T02:00:00Z"))
    original_write = store._write_json_create_once

    def fail_after_raw_cas(*args: object, **kwargs: object) -> bool:
        if kwargs.get("label") != "technical source observation":
            return original_write(*args, **kwargs)
        assert len(list((root / "prepared").glob("*/*.json"))) == 1
        assert len(list((root / "source_bodies").glob("*/*.bin"))) == 6
        assert not (root / "source_observations").exists()
        raise store.MarketMemoryTechnicalStoreError("injected raw CAS crash")

    monkeypatch.setattr(store, "_write_json_create_once", fail_after_raw_cas)
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="injected"):
        store.capture_technical_actual_output(root, bundle=candidate)
    prepared_path = next((root / "prepared").glob("*/*.json"))
    prepared_before = prepared_path.read_bytes()
    assert store.load_technical_actual_output_generation(root)["captures"] == []

    retry_clock_reads = 0

    def forbidden_later_clock() -> datetime:
        nonlocal retry_clock_reads
        retry_clock_reads += 1
        return datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(store, "_write_json_create_once", original_write)
    monkeypatch.setattr(store, "_utc_now", forbidden_later_clock)
    stored = store.capture_technical_actual_output(root, bundle=candidate)
    assert retry_clock_reads == 0
    assert prepared_path.read_bytes() == prepared_before
    assert stored.capture_receipt["clocks"]["first_observed_at"] == (
        "2026-08-10T02:00:00Z"
    )


def test_generation_is_durable_before_head_and_retry_completes_same_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "technicals-v1"
    candidate = _bundle()
    empty = store.initialize_technical_actual_output_store(root)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T02:00:00Z"))
    original_replace = store._replace_head

    def fail_head(_root: Path, _head: object) -> None:
        assert len(list((root / "source_bodies").glob("*/*.bin"))) == 6
        assert len(list((root / "generations").glob("*/*.json"))) == 2
        raise store.MarketMemoryTechnicalStoreError("injected HEAD crash")

    monkeypatch.setattr(store, "_replace_head", fail_head)
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="HEAD crash"):
        store.capture_technical_actual_output(root, bundle=candidate)
    assert (
        store.load_technical_actual_output_generation(root)["generation_id"]
        == empty["generation_id"]
    )

    monkeypatch.setattr(store, "_replace_head", original_replace)

    def no_resample() -> datetime:
        raise AssertionError("sealed prepared retry sampled a new clock")

    monkeypatch.setattr(store, "_utc_now", no_resample)
    stored = store.capture_technical_actual_output(root, bundle=candidate)
    assert stored.generation_id != empty["generation_id"]
    assert len(store.load_technical_actual_output_generation(root)["captures"]) == 1


def test_code_only_commit_is_idempotent_while_active_retry_rechecks_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, first = _capture(tmp_path, monkeypatch)
    before = _tree(root)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T03:00:00Z"))
    second = store.capture_technical_actual_output(
        root,
        bundle=_bundle(pinned_commit="2" * 40),
    )
    assert second.capture_receipt == first.capture_receipt
    assert second.generation_id == first.generation_id
    assert _tree(root) == before

    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-11T04:00:00Z"))
    with pytest.raises(store.MarketMemoryTechnicalCaptureError):
        store.capture_technical_actual_output(root, bundle=_bundle())
    assert _tree(root) == before


def test_same_session_changed_spy_bytes_append_revision_and_pin_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "technicals-v1"
    clocks = iter(
        [
            datetime(2026, 8, 10, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 10, 2, 1, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(store, "_utc_now", lambda: next(clocks))
    first = store.capture_technical_actual_output(root, bundle=_bundle())
    revised_frame = _frame()
    revised_frame.iloc[-1, revised_frame.columns.get_loc("close")] += 1.0
    revised_frame.iloc[-1, revised_frame.columns.get_loc("high")] += 1.0
    second = store.capture_technical_actual_output(
        root,
        bundle=_bundle(frame=revised_frame),
    )

    assert second.capture_receipt["session"] == first.capture_receipt["session"]
    assert second.capture_receipt["revision_id"] != first.capture_receipt["revision_id"]
    assert second.capture_receipt["capture_id"] != first.capture_receipt["capture_id"]
    assert len(store.load_technical_actual_output_generation(root)["captures"]) == 2
    pinned = store.load_technical_actual_output_generation(
        root, generation_id=first.generation_id
    )
    assert len(pinned["captures"]) == 1
    with pytest.raises(
        store.MarketMemoryTechnicalStoreError, match="absent or ambiguous"
    ):
        store.load_technical_actual_output_capture(
            root,
            capture_id=second.capture_receipt["capture_id"],
            generation_id=first.generation_id,
        )


@pytest.mark.parametrize(
    "target",
    [
        "raw",
        "source",
        "feature",
        "prepared",
        "receipt",
        "generation",
        "head",
        "feature_symlink",
    ],
)
def test_every_stored_layer_tamper_or_symlink_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, stored = _capture(tmp_path / target, monkeypatch)
    receipt = stored.capture_receipt
    capture_id = receipt["capture_id"]
    if target == "raw":
        path = root / receipt["source_bodies"]["publish_manifest"]["object_key"]
        body = bytearray(path.read_bytes())
        body[-1] ^= 1
        path.write_bytes(body)
    elif target == "source":
        path = root / receipt["source_observation"]["object_key"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "feature":
        path = root / receipt["feature_object"]["object_key"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "prepared":
        path = root / receipt["prepared_object_key"]
        value = _read_json(path)
        value["available_at"] = "2026-08-10T02:00:01Z"
        _write_canonical(path, value)
    elif target == "receipt":
        path = next((root / "capture_receipts").glob("*/*.json"))
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "generation":
        path = next(
            path
            for path in (root / "generations").glob("*/*.json")
            if path.name == f"{stored.generation_id}.json"
        )
        value = _read_json(path)
        value["captures"][0]["receipt_sha256"] = "f" * 64
        _write_canonical(path, value)
    elif target == "head":
        path = root / "HEAD.json"
        value = _read_json(path)
        value["future"] = True
        _write_canonical(path, value)
    elif target == "feature_symlink":
        path = root / receipt["feature_object"]["object_key"]
        backup = tmp_path / target / "feature-backup.json"
        backup.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(backup)
    else:  # pragma: no cover
        raise AssertionError(target)

    with pytest.raises(store.MarketMemoryTechnicalStoreError):
        store.load_technical_actual_output_capture(root, capture_id=capture_id)


def test_explicit_generation_identity_and_receipt_byte_bound_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    generation = store.load_technical_actual_output_generation(root)
    fake_id = "mmactualgeneration_" + "f" * 64
    fake_path = root / "generations" / "ff" / f"{fake_id}.json"
    fake_path.parent.mkdir(parents=True)
    _write_canonical(fake_path, generation)
    with pytest.raises(store.MarketMemoryTechnicalStoreError):
        store.load_technical_actual_output_generation(root, generation_id=fake_id)

    receipt_path = next((root / "capture_receipts").glob("*/*.json"))
    receipt_path.write_bytes(b"{" + b" " * (store._MAX_RECEIPT_BYTES + 1) + b"}")
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="safe size bound"):
        store.load_technical_actual_output_capture(
            root,
            capture_id=stored.capture_receipt["capture_id"],
        )


def test_public_pin_reads_published_ancestor_and_rejects_crash_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    current = store.pin_technical_actual_output_generation(root)
    state = store._load_state(root)
    genesis_id = state.generation["previous_generation_id"]
    assert genesis_id is not None
    genesis = store.pin_technical_actual_output_generation(
        root, generation_id=genesis_id
    )
    assert genesis.captures == ()
    assert current.generation_id == stored.generation_id

    orphan = store._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=current.generation_id,
        captures=[row.as_dict() for row in current.captures],
    )
    orphan_body = store._canonical_bytes(orphan)
    store._write_json_create_once(
        root,
        store._generation_path(root, orphan["generation_id"]),
        orphan_body,
        label="test technical crash orphan",
        limit=store._MAX_GENERATION_BYTES,
    )
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="not published"):
        store.pin_technical_actual_output_generation(
            root, generation_id=orphan["generation_id"]
        )


@pytest.mark.parametrize("broken", ["nonempty_genesis", "missing_ancestor"])
def test_public_pin_requires_full_chain_to_empty_genesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    state = store._load_state(root)
    previous = None if broken == "nonempty_genesis" else "mmactualgeneration_" + "f" * 64
    forged = store._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=previous,
        captures=[dict(row) for row in state.generation["captures"]],
    )
    body = store._canonical_bytes(forged)
    store._write_json_create_once(
        root,
        store._generation_path(root, forged["generation_id"]),
        body,
        label="test broken technical ancestry",
        limit=store._MAX_GENERATION_BYTES,
    )
    store._replace_head(root, store._new_head(forged, body=body))
    message = "empty genesis" if broken == "nonempty_genesis" else "unavailable"
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match=message):
        store.pin_technical_actual_output_generation(root)
    assert stored.capture_receipt["capture_id"] == forged["captures"][0]["capture_id"]


def test_public_pin_rejects_valid_content_addressed_ancestor_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _stored = _capture(tmp_path, monkeypatch)
    state = store._load_state(root)
    genesis_id = state.generation["previous_generation_id"]
    assert genesis_id is not None
    rewritten_entry = copy.deepcopy(state.generation["captures"][0])
    rewritten_entry["receipt_sha256"] = "f" * 64
    forged_older = store._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=genesis_id,
        captures=[rewritten_entry],
    )
    forged_older_body = store._canonical_bytes(forged_older)
    store._write_json_create_once(
        root,
        store._generation_path(root, forged_older["generation_id"]),
        forged_older_body,
        label="test rewritten technical ancestor",
        limit=store._MAX_GENERATION_BYTES,
    )
    extra_entry = copy.deepcopy(state.generation["captures"][0])
    extra_entry["capture_id"] = "mmactualcapture_" + "e" * 64
    extra_entry["revision_id"] = "mmtechrev_" + "e" * 64
    extra_entry["source_observation_id"] = "mmtechsrc_" + "e" * 64
    extra_entry["snapshot_id"] = "mmtechsnap_" + "e" * 64
    extra_entry["first_observed_at"] = "2026-08-10T02:01:00Z"
    extra_entry["receipt_sha256"] = "e" * 64
    forged_newer = store._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=forged_older["generation_id"],
        captures=[dict(state.generation["captures"][0]), extra_entry],
    )
    forged_newer_body = store._canonical_bytes(forged_newer)
    store._write_json_create_once(
        root,
        store._generation_path(root, forged_newer["generation_id"]),
        forged_newer_body,
        label="test technical rewrite head",
        limit=store._MAX_GENERATION_BYTES,
    )
    store._replace_head(root, store._new_head(forged_newer, body=forged_newer_body))
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="rewrites"):
        store.pin_technical_actual_output_generation(root)


def test_generation_orders_variable_fraction_utc_by_instant_then_capture_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _stored = _capture(tmp_path, monkeypatch)
    state = store._load_state(root)
    base = dict(state.generation["captures"][0])

    def entry(suffix: str, observed_at: str) -> dict[str, str]:
        row = copy.deepcopy(base)
        row.update(
            {
                "capture_id": "mmactualcapture_" + suffix * 64,
                "revision_id": "mmtechrev_" + suffix * 64,
                "source_observation_id": "mmtechsrc_" + suffix * 64,
                "snapshot_id": "mmtechsnap_" + suffix * 64,
                "first_observed_at": observed_at,
                "receipt_sha256": suffix * 64,
            }
        )
        return row

    exact = entry("2", "2026-08-10T04:00:00Z")
    exact_tie = entry("1", "2026-08-10T04:00:00Z")
    later = entry("3", "2026-08-10T04:00:00.100000Z")
    generation = store._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=state.generation["generation_id"],
        captures=[later, exact, exact_tie],
    )
    assert [row["capture_id"] for row in generation["captures"]] == [
        exact_tie["capture_id"],
        exact["capture_id"],
        later["capture_id"],
    ]
    assert store._validate_generation(
        generation, store_id=state.manifest["store_id"]
    ) == generation

    forged = copy.deepcopy(generation)
    forged["captures"] = [later, exact_tie, exact]
    forged["generation_id"] = store._content_id(
        "mmactualgeneration_", forged, field="generation_id"
    )
    with pytest.raises(store.MarketMemoryTechnicalStoreError, match="canonical"):
        store._validate_generation(forged, store_id=state.manifest["store_id"])
