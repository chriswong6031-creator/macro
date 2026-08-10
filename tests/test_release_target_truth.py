from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.release_target_truth import (
    PERCENT_TARGET_SERIES,
    ReleaseTargetTruthError,
    default_vintage_path,
    load_full_vintage_parquets,
    reconstruct_release_target,
    round_published_1dp,
)
from scripts.collect_release_target_vintages import collect_release_target_vintages


def _frame(series: str, rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series": series,
                "period": period,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "value": value,
                "source_output_type": 2,
            }
            for period, realtime_start, realtime_end, value in rows
        ]
    )


def test_annual_revision_discontinuity_uses_prior_level_from_same_release_vintage():
    # December's first-published 100.0 is revised to 110.0 in the same vintage
    # that first publishes January at 111.1.  The canonical print proxy is 1.0%,
    # not the bogus 11.1% obtained by comparing cross-vintage first values.
    vintages = _frame(
        "CPIAUCSL",
        [
            ("2024-12-01", "2025-01-15", "2025-02-11", 100.0),
            ("2024-12-01", "2025-02-12", "9999-12-31", 110.0),
            ("2025-01-01", "2025-02-12", "9999-12-31", 111.1),
        ],
    )

    result = reconstruct_release_target(
        vintages,
        series_id="CPIAUCSL",
        period="2025-01",
        as_of="2025-02-12",
    )

    assert result["status"] == "ok"
    assert result["release_date"] == "2025-02-12"
    assert result["as_of"] == "2025-02-12"
    assert result["current_level"] == 111.1
    assert result["prior_level_same_vintage"] == 110.0
    assert result["latent_change"] == pytest.approx(1.0)
    assert result["published_proxy_1dp"] == 1.0
    assert result["published_proxy"] != pytest.approx(11.1)
    assert result["cross_vintage_fallback_used"] is False
    assert result["published_proxy_is_official_release"] is False
    assert result["provenance"]["prior_vintage"] == {
        "period": "2024-12-01",
        "realtime_start": "2025-02-12",
        "realtime_end": "9999-12-31",
        "value": 110.0,
    }


@pytest.mark.parametrize("series_id", PERCENT_TARGET_SERIES)
def test_all_price_targets_emit_latent_and_explicit_one_decimal_proxy(series_id: str):
    vintages = _frame(
        series_id,
        [
            ("2025-03-01", "2025-05-01", "9999-12-31", 200.0),
            ("2025-04-01", "2025-05-01", "9999-12-31", 200.6),
        ],
    )

    result = reconstruct_release_target(
        vintages,
        series_id=series_id,
        period="2025-04",
        release_date="2025-05-01",
    )

    assert result["status"] == "ok"
    assert result["target_kind"] == "percent_mom"
    assert result["latent_change"] == pytest.approx(0.3)
    assert result["published_proxy_1dp"] == 0.3
    assert result["payroll_change_thousands"] is None
    assert result["unit"] == "percent"


def test_payems_emits_exact_plus_57_thousand_from_release_vintage():
    vintages = _frame(
        "PAYEMS",
        [
            ("2024-12-01", "2025-01-10", "2025-02-06", 158_900.0),
            ("2024-12-01", "2025-02-07", "9999-12-31", 159_000.0),
            ("2025-01-01", "2025-02-07", "9999-12-31", 159_057.0),
        ],
    )

    result = reconstruct_release_target(
        vintages,
        series_id="PAYEMS",
        period="2025-01",
        release_date="2025-02-07",
        as_of="2025-02-07",
    )

    assert result["status"] == "ok"
    assert result["target_kind"] == "payroll_change"
    assert result["latent_change"] == 57.0
    assert result["published_proxy"] == 57.0
    assert result["published_proxy_1dp"] is None
    assert result["payroll_change_thousands"] == 57.0
    assert result["unit"] == "thousands"
    assert result["prior_level_same_vintage"] == 159_000.0
    assert result["provenance"]["release_date"] == "2025-02-07"


def test_missing_same_vintage_prior_is_explicitly_unavailable_without_fallback():
    vintages = _frame(
        "CPILFESL",
        [
            ("2025-03-01", "2025-04-10", "2025-05-10", 100.0),
            # No prior-period value is active on the May 13 current release.
            ("2025-04-01", "2025-05-13", "9999-12-31", 100.4),
        ],
    )

    result = reconstruct_release_target(
        vintages,
        series_id="CPILFESL",
        period="2025-04",
        release_date="2025-05-13",
    )

    assert result == {
        "schema": "release_target_truth.v1",
        "status": "unavailable",
        "reason": "prior_same_vintage_value_missing",
        "series_id": "CPILFESL",
        "target_id": "cpi_core_mom",
        "period": "2025-04",
        "prior_period": "2025-03",
        "release_date": "2025-05-13",
        "as_of": "2025-05-13",
        "release_selection": "explicit",
        "basis": "same_release_vintage",
        "cross_vintage_fallback_used": False,
    }


def test_as_of_before_release_cannot_observe_target():
    vintages = _frame(
        "PCEPI",
        [
            ("2025-03-01", "2025-05-30", "9999-12-31", 100.0),
            ("2025-04-01", "2025-05-30", "9999-12-31", 100.2),
        ],
    )

    result = reconstruct_release_target(
        vintages,
        series_id="PCEPI",
        period="2025-04",
        release_date="2025-05-30",
        as_of="2025-05-29",
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == "release_not_available_by_as_of"
    assert result["cross_vintage_fallback_used"] is False


def test_conventional_one_decimal_rounding_is_half_up():
    assert round_published_1dp(0.25) == 0.3
    assert round_published_1dp(-0.25) == -0.3


def test_loader_requires_and_validates_output_type_marker(tmp_path: Path):
    path = tmp_path / "CPIAUCSL_all_vintages.parquet"
    invalid = _frame(
        "CPIAUCSL",
        [
            ("2025-01-01", "2025-02-12", "9999-12-31", 100.0),
        ],
    )
    invalid["source_output_type"] = 4
    invalid.to_parquet(path, index=False)

    with pytest.raises(ReleaseTargetTruthError, match="must be exactly 2"):
        load_full_vintage_parquets(path)

    unmarked = invalid.drop(columns="source_output_type")
    unmarked.to_parquet(path, index=False)
    with pytest.raises(ReleaseTargetTruthError, match="no source_output_type marker"):
        load_full_vintage_parquets(path)


def test_loader_combines_canonical_series_parquets(tmp_path: Path):
    paths = []
    for series_id in ("CPIAUCSL", "PAYEMS"):
        path = tmp_path / f"{series_id}.parquet"
        _frame(
            series_id,
            [("2025-01-01", "2025-02-01", "9999-12-31", 100.0)],
        ).to_parquet(path, index=False)
        paths.append(path)

    loaded = load_full_vintage_parquets(paths)

    assert set(loaded["series"]) == {"CPIAUCSL", "PAYEMS"}
    assert set(loaded["source_output_type"]) == {2}


def test_collector_fails_open_without_key_and_never_calls_fetcher(tmp_path: Path):
    def forbidden_fetcher(**_kwargs):
        raise AssertionError("fetcher must not run without a key")

    receipt = collect_release_target_vintages(
        repo_root=tmp_path,
        series_ids=["CPIAUCSL"],
        api_key="",
        fetcher=forbidden_fetcher,
    )

    assert receipt["status"] == "skipped"
    assert receipt["reason"] == "missing_fred_api_key"
    assert not (tmp_path / "data").exists()


def test_collector_requests_output_type_2_and_writes_self_identifying_store(
    tmp_path: Path,
):
    calls = []

    def fake_fetcher(**kwargs):
        calls.append(kwargs)
        return _frame(
            "PAYEMS",
            [
                ("2024-12-01", "2025-02-07", "9999-12-31", 159_000.0),
                ("2025-01-01", "2025-02-07", "9999-12-31", 159_057.0),
            ],
        ).drop(columns=["series", "source_output_type"])

    receipt = collect_release_target_vintages(
        repo_root=tmp_path,
        series_ids=["PAYEMS"],
        api_key="test-key",
        fetcher=fake_fetcher,
    )

    assert receipt["status"] == "ok"
    assert calls == [
        {
            "series_id": "PAYEMS",
            "output_type": 2,
            "realtime_start": "1997-01-01",
            "api_key": "test-key",
        }
    ]
    output = default_vintage_path(tmp_path, "PAYEMS")
    stored = pd.read_parquet(output)
    output_bytes = output.read_bytes()
    manifest = json.loads(
        (tmp_path / "data/fred_vintage/release_targets/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["schema"] == "release_target_vintage_collection.v1"
    assert manifest["integrity_profile"] == "release_target_artifact_sha256_bytes.v1"
    assert manifest["completed_at"] >= manifest["collected_at"]
    assert manifest["series"]["PAYEMS"]["artifact_bytes"] == len(output_bytes)
    assert (
        manifest["series"]["PAYEMS"]["artifact_sha256"]
        == hashlib.sha256(output_bytes).hexdigest()
    )
    assert set(stored["series"]) == {"PAYEMS"}
    assert set(stored["source_output_type"]) == {2}
    reconstructed = reconstruct_release_target(
        stored,
        series_id="PAYEMS",
        period="2025-01",
        release_date="2025-02-07",
    )
    assert reconstructed["payroll_change_thousands"] == 57.0


def test_conflicting_duplicate_vintage_values_are_rejected():
    vintages = _frame(
        "PPIFIS",
        [
            ("2025-01-01", "2025-02-13", "9999-12-31", 100.0),
            ("2025-01-01", "2025-02-13", "9999-12-31", 101.0),
        ],
    )

    with pytest.raises(ReleaseTargetTruthError, match="conflicting values"):
        reconstruct_release_target(
            vintages,
            series_id="PPIFIS",
            period="2025-01",
            release_date="2025-02-13",
        )
