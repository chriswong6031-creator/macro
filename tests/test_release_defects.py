from engine.release_defects import (
    canonical_scored_rows,
    evaluation_status,
    matching_defect_ids,
)

NOTICES = [
    {
        "id": "DN-X",
        "evaluation_excluded": True,
        "selector": {
            "row_types": ["scored"],
            "release_types": ["cpi_headline"],
            "models": ["champion", "v3_factor"],
            "frozen_asof_range": ["2026-07-07", "2026-07-13"],
        },
    },
    {
        "id": "PROSE-ONLY",
        "evaluation_excluded": False,
        "selector": {"release_types": ["cpi_headline"]},
    },
]


def test_matching_uses_frozen_projection_date_and_champion_alias() -> None:
    row = {
        "row_type": "scored",
        "release": "cpi_headline",
        "model": None,
        "asof_night": "2026-07-14",
        "frozen_asof_night": "2026-07-13",
    }
    assert matching_defect_ids(row, NOTICES) == ["DN-X"]
    assert evaluation_status(row, NOTICES)["eligible"] is False


def test_nonmatching_model_and_prose_notice_do_not_exclude() -> None:
    row = {
        "row_type": "scored",
        "release": "cpi_headline",
        "model": "cpi_bridge",
        "frozen_asof_night": "2026-07-13",
    }
    assert matching_defect_ids(row, NOTICES) == []


def test_target_epoch_selector_and_missing_actual_source() -> None:
    notices = [
        {
            "id": "TARGET",
            "evaluation_excluded": True,
            "selector": {
                "target_epochs": ["legacy_v0"],
                "actual_source_missing": True,
            },
        }
    ]
    base = {"row_type": "scored", "target_epoch": "legacy_v0"}
    assert matching_defect_ids(base, notices) == ["TARGET"]
    assert matching_defect_ids({**base, "actual_source": "official_release"}, notices) == []


def test_official_receipt_supersedes_production_shaped_legacy_score() -> None:
    legacy = {
        "row_type": "scored",
        "release": "nfp",
        "period": "2026-07",
        "model": None,
        "frozen_asof_night": "2026-08-06",
        "actual": -126.0,
    }
    official = {
        **legacy,
        "frozen_prediction_id": "NFP:2026-07:first:2026-08-06:v1",
        "actual": 57.0,
        "actual_basis": "official_published_metric",
        "actual_receipt_id": "official_actual:nfp-july",
    }
    assert canonical_scored_rows([legacy, official]) == [official]


def test_same_value_official_receipt_still_upgrades_legacy_provenance() -> None:
    legacy = {
        "row_type": "scored",
        "release": "claims",
        "period": "2026-08-06",
        "model": None,
        "frozen_asof_night": "2026-08-05",
        "actual": 199.0,
    }
    official = {
        **legacy,
        "actual_basis": "official_published_metric",
        "actual_receipt_id": "official_actual:claims-aug6",
    }
    assert canonical_scored_rows([legacy, official]) == [official]


def test_incomplete_legacy_identities_are_not_silently_collapsed() -> None:
    rows = [
        {"row_type": "scored", "release": "cpi_headline", "actual": 0.2},
        {"row_type": "scored", "release": "cpi_headline", "actual": 0.3},
    ]
    assert canonical_scored_rows(rows) == rows
