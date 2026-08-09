from engine.release_defects import evaluation_status, matching_defect_ids

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
