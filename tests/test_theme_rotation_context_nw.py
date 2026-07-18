"""Tests for theme_context.v1 Neural Web integration.

Covers:
1. _compose_theme_rotation: synthetic artifact -> cleaned block with display_only True
2. _compose_theme_rotation: absent artifact -> null dict with display_only True, no raise
3. brief_context._block_theme_rotation: present / absent paths
4. _MACRO_DROP_ORDER membership assertion
5. mastermind_context._summarize_theme_rotation: smoke test (present / absent ws)
6. _LOBE_TO_ARTIFACT_IDS entry for theme_rotation
7. China artifact present -> 'china' sub-dict cleaned + display_only preserved at top level
8. China artifact absent -> 'china' is None and US fields unchanged
9. brief_context china path: china sub-block present / absent
10. mastermind_context china path: china sub-block present / absent

All tests use tmp_path; no real market data is read from disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


# ---------------------------------------------------------------------------
# Minimal synthetic theme_context.v1 artifact fixture
# ---------------------------------------------------------------------------

_THEME_CTX_FIXTURE: dict = {
    "schema": "theme_context.v1",
    "as_of": "2026-07-17",
    "region": "us",
    "display_only": True,
    "leadership": {
        "state": "strain",
        "days_in_state": 3,
        "stance_en": "Leadership under strain — watch, don't chase.",
        "stance_zh": "领涨承压——观望，勿追高。",
        "trailing_leader": {
            "id": "memory_storage",
            "name": "Memory / Storage",
            "name_zh": "内存/存储",
            "alloc_rank": 1,
            "health": "broken",
            "breadth": 0.0,
            "r10": -0.127,
            "val_state": "fading",
            "label": "deteriorating",
            "reco": "avoid",
            "desk_score": 41,
        },
        "challenger": {
            "id": "cybersecurity",
            "name": "Cybersecurity",
            "name_zh": "网络安全",
            "margin": 1.065,
        },
        "strength": [
            {
                "id": "cybersecurity",
                "name": "Cybersecurity",
                "name_zh": "网络安全",
                "desk_score": 72,
                "health": "confirmed",
                "breadth": 0.80,
                "r10": 0.047,
                "category": "Software",
            },
            {
                "id": "cloud_infra",
                "name": "Cloud Infrastructure",
                "name_zh": "云基础设施",
                "desk_score": 68,
                "health": "confirmed",
                "breadth": 0.75,
                "r10": 0.038,
                "category": "Software",
            },
        ],
        "breaking": [
            {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "breadth": 0.0,
                "r10": -0.127,
            }
        ],
    },
    "migration": {
        "absorbing": [
            {"category": "Healthcare", "avg_breadth": 0.79, "avg_r10": -0.025, "n": 3}
        ],
        "bleeding": [
            {"category": "Semiconductors", "avg_breadth": 0.07, "avg_r10": -0.104, "n": 3}
        ],
        "note_en": "Capital moving from Semiconductors into Healthcare.",
        "note_zh": "资金从半导体流向医疗保健。",
    },
    "alignment": {
        "sector_rotation_agrees": True,
        "note_en": "Rotation events confirm theme leadership shift.",
        "note_zh": "轮动事件确认主题领涨切换。",
    },
    "themes": {
        "memory_storage": {
            "label": "deteriorating",
            "reco": "avoid",
            "score": 41,
            "rank": 1,
            "alloc_rank": 1,
            "health": "broken",
            "breadth": 0.0,
            "r10": -0.127,
            "val_state": "fading",
            "days_in_label": 5,
            "score_delta_5d": -8,
        }
    },
    "state_changes": {
        "leadership_state": {
            "current": "strain",
            "prev": "steady",
            "changed_on": "2026-07-14",
            "days_in_state": 3,
        }
    },
    "prev_asof": "2026-07-16",
}


# ---------------------------------------------------------------------------
# 1. _compose_theme_rotation: artifact present → cleaned block, display_only True
# ---------------------------------------------------------------------------

def test_compose_theme_rotation_present(tmp_path: Path):
    """Synthetic artifact -> compose returns cleaned block with display_only True."""
    from engine.neuralweb.world_state import _compose_theme_rotation

    tc_path = tmp_path / "site" / "basketdata" / "theme_context.json"
    _write_json(tc_path, _THEME_CTX_FIXTURE)

    block = _compose_theme_rotation(root=tmp_path)

    assert block["display_only"] is True
    assert block["as_of"] == "2026-07-17"
    assert block["leadership_state"] == "strain"
    assert block["days_in_state"] == 3
    assert block["stance_en"] == "Leadership under strain — watch, don't chase."
    assert block["stance_zh"] == "领涨承压——观望，勿追高。"

    # Trailing leader compact fields
    tl = block["trailing_leader"]
    assert tl is not None
    assert tl["id"] == "memory_storage"
    assert tl["health"] == "broken"
    assert tl["breadth"] == 0.0
    assert tl["r10"] == pytest.approx(-0.127)

    # Strength: id+name only, max 4
    strength = block["strength"]
    assert isinstance(strength, list)
    assert len(strength) == 2
    assert strength[0]["id"] == "cybersecurity"
    assert strength[0]["name"] == "Cybersecurity"
    # Should NOT carry desk_score / breadth (raw artifact fields not in compact spec)
    assert "desk_score" not in strength[0]
    assert "breadth" not in strength[0]

    # Migration categories
    migration = block["migration"]
    assert migration is not None
    assert migration["absorbing"][0]["category"] == "Healthcare"
    assert migration["bleeding"][0]["category"] == "Semiconductors"

    # Alignment
    alignment = block["alignment"]
    assert alignment is not None
    assert alignment["sector_rotation_agrees"] is True

    # State changes
    sc = block["state_changes"]
    assert sc is not None
    assert "leadership_state" in sc
    assert sc["leadership_state"]["current"] == "strain"


# ---------------------------------------------------------------------------
# 2. _compose_theme_rotation: absent artifact → null dict, display_only True, no raise
# ---------------------------------------------------------------------------

def test_compose_theme_rotation_absent(tmp_path: Path):
    """Absent artifact -> null dict with display_only True, no raise."""
    from engine.neuralweb.world_state import _compose_theme_rotation

    # Do NOT write any file at site/basketdata/theme_context.json
    block = _compose_theme_rotation(root=tmp_path)

    assert block["display_only"] is True
    assert block["leadership_state"] is None
    assert block["as_of"] is None
    assert block["trailing_leader"] is None
    assert block["strength"] is None
    assert block["migration"] is None
    assert block["alignment"] is None
    assert block["state_changes"] is None


# ---------------------------------------------------------------------------
# 3. _block_theme_rotation: present path
# ---------------------------------------------------------------------------

def test_block_theme_rotation_present():
    """Block returns non-None with correct fields when ws contains theme_rotation."""
    from engine.neuralweb.brief_context import _block_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "leadership_state": "strain",
            "days_in_state": 3,
            "stance_en": "Leadership under strain — watch, don't chase.",
            "stance_zh": "领涨承压——观望，勿追高。",
            "as_of": "2026-07-17",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [
                {"id": "cybersecurity", "name": "Cybersecurity"},
                {"id": "cloud_infra", "name": "Cloud Infrastructure"},
            ],
            "migration": {
                "absorbing": [{"category": "Healthcare", "avg_breadth": 0.79}],
                "bleeding": [{"category": "Semiconductors", "avg_breadth": 0.07}],
            },
            "alignment": {"sector_rotation_agrees": True},
            "state_changes": None,
        }
    }

    block = _block_theme_rotation(ws)

    assert block is not None
    assert block["display_only"] is True
    assert block["is_context_only"] is True
    assert block["leadership_state"] == "strain"
    assert block["stance_en"] == "Leadership under strain — watch, don't chase."
    assert block["days_in_state"] == 3
    tl = block["trailing_leader"]
    assert tl is not None
    assert tl["health"] == "broken"
    assert block["strength_names"] == ["Cybersecurity", "Cloud Infrastructure"]
    assert block["migration_absorbing"] == ["Healthcare"]
    assert block["migration_bleeding"] == ["Semiconductors"]
    assert block["sector_rotation_agrees"] is True
    assert "_tape_family" in block


# ---------------------------------------------------------------------------
# 4. _block_theme_rotation: absent / null path → None
# ---------------------------------------------------------------------------

def test_block_theme_rotation_absent():
    """Returns None when ws is None."""
    from engine.neuralweb.brief_context import _block_theme_rotation
    assert _block_theme_rotation(None) is None


def test_block_theme_rotation_ws_missing_key():
    """Returns None when ws lacks theme_rotation key."""
    from engine.neuralweb.brief_context import _block_theme_rotation
    assert _block_theme_rotation({}) is None


def test_block_theme_rotation_all_null():
    """Returns None when all key fields are null/absent."""
    from engine.neuralweb.brief_context import _block_theme_rotation
    ws = {
        "theme_rotation": {
            "display_only": True,
            "leadership_state": None,
            "stance_en": None,
            "as_of": None,
        }
    }
    assert _block_theme_rotation(ws) is None


# ---------------------------------------------------------------------------
# 5. _MACRO_DROP_ORDER membership: theme_rotation in list and placed after
#    cross_asset_context (drops just above it, i.e., second in the list)
# ---------------------------------------------------------------------------

def test_macro_drop_order_membership():
    """theme_rotation appears in _MACRO_DROP_ORDER after cross_asset_context."""
    from engine.neuralweb.brief_context import _MACRO_DROP_ORDER

    assert "theme_rotation" in _MACRO_DROP_ORDER

    # cross_asset_context drops first (lowest priority = index 0)
    # theme_rotation must come after it in the list (higher index)
    idx_ca = _MACRO_DROP_ORDER.index("cross_asset_context")
    idx_tr = _MACRO_DROP_ORDER.index("theme_rotation")
    assert idx_tr > idx_ca, (
        "theme_rotation should appear after cross_asset_context in _MACRO_DROP_ORDER "
        "(cross_asset_context drops first; theme_rotation next)"
    )


# ---------------------------------------------------------------------------
# 6. _summarize_theme_rotation: smoke test (present ws)
# ---------------------------------------------------------------------------

def test_summarize_theme_rotation_present(tmp_path: Path):
    """Summarizer returns a non-empty lobe dict when world_state.theme_rotation is present."""
    from engine.neuralweb.mastermind_context import _summarize_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "as_of": "2026-07-17",
            "leadership_state": "strain",
            "days_in_state": 3,
            "stance_en": "Leadership under strain — watch, don't chase.",
            "stance_zh": "领涨承压——观望，勿追高。",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [{"id": "cybersecurity", "name": "Cybersecurity"}],
            "migration": {
                "absorbing": [{"category": "Healthcare", "avg_breadth": 0.79}],
                "bleeding": [{"category": "Semiconductors", "avg_breadth": 0.07}],
            },
            "alignment": {"sector_rotation_agrees": True},
            "state_changes": {
                "leadership_state": {
                    "current": "strain",
                    "prev": "steady",
                    "changed_on": "2026-07-14",
                    "days_in_state": 3,
                }
            },
        }
    }
    ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
    _write_json(ws_path, ws)

    lobe, gap = _summarize_theme_rotation(tmp_path)

    assert gap is None
    assert lobe["display_only"] is True
    assert lobe["is_context_only"] is True
    assert lobe["leadership_state"] == "strain"
    assert lobe["trailing_leader_id"] == "memory_storage"
    assert lobe["trailing_leader_health"] == "broken"
    assert lobe["strength_names"] == ["Cybersecurity"]
    assert lobe["migration_absorbing"] == ["Healthcare"]
    assert lobe["migration_bleeding"] == ["Semiconductors"]
    assert lobe["sector_rotation_agrees"] is True
    assert "validated" not in str(lobe), "The word 'validated' must not appear in lobe output"


# ---------------------------------------------------------------------------
# 7. _summarize_theme_rotation: absent world_state → empty dict, gap note
# ---------------------------------------------------------------------------

def test_summarize_theme_rotation_absent_ws(tmp_path: Path):
    """Absent world_state -> empty lobe + gap note, no raise."""
    from engine.neuralweb.mastermind_context import _summarize_theme_rotation

    # Don't write world_state.json
    lobe, gap = _summarize_theme_rotation(tmp_path)

    assert lobe == {}
    assert gap is not None
    assert "absent" in gap.lower() or "unreadable" in gap.lower()


def test_summarize_theme_rotation_missing_sub_block(tmp_path: Path):
    """World state present but theme_rotation key missing -> empty lobe + gap note."""
    from engine.neuralweb.mastermind_context import _summarize_theme_rotation

    ws = {"verdict": {"asof": "2026-07-17"}}
    ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
    _write_json(ws_path, ws)

    lobe, gap = _summarize_theme_rotation(tmp_path)

    assert lobe == {}
    assert gap is not None


# ---------------------------------------------------------------------------
# 8. _LOBE_TO_ARTIFACT_IDS entry
# ---------------------------------------------------------------------------

def test_lobe_to_artifact_ids_entry():
    """theme_rotation has the correct artifact ID registered."""
    from engine.neuralweb.mastermind_context import _LOBE_TO_ARTIFACT_IDS, LOBE_SUMMARIZERS

    assert "theme_rotation" in _LOBE_TO_ARTIFACT_IDS
    assert "theme-context-latest" in _LOBE_TO_ARTIFACT_IDS["theme_rotation"]
    assert "theme_rotation" in LOBE_SUMMARIZERS


# ---------------------------------------------------------------------------
# China sub-dict fixtures
# ---------------------------------------------------------------------------

_THEME_CTX_CN_FIXTURE: dict = {
    "schema": "theme_context.v1",
    "as_of": "2026-07-17",
    "region": "china",
    "display_only": True,
    "leadership": {
        "state": "rotating",
        "days_in_state": 2,
        "stance_en": "Rotation under way — favour the fresh leaders, not the old one.",
        "stance_zh": "轮动进行中——关注新领涨主题，勿追旧龙头。",
        "trailing_leader": {
            "id": "new_energy",
            "name": "New Energy",
            "name_zh": "新能源",
            "alloc_rank": 1,
            "health": "broken",
            "breadth": 0.15,
            "r10": -0.08,
            "val_state": None,
        },
        "strength": [
            {
                "id": "tech_ai",
                "name": "Technology & AI",
                "name_zh": "科技与AI",
                "desk_score": 65,
                "health": "confirmed",
                "breadth": 0.72,
                "r10": 0.035,
                "category": "Technology & AI",
            }
        ],
        "breaking": [],
    },
    "migration": {
        "absorbing": [
            {"category": "Advanced Manufacturing", "avg_breadth": 0.68, "avg_r10": 0.02, "n": 2}
        ],
        "bleeding": [
            {"category": "New Energy & Autos", "avg_breadth": 0.12, "avg_r10": -0.07, "n": 2}
        ],
        "note_en": "Capital moving from New Energy into Advanced Manufacturing.",
        "note_zh": "资金从新能源流向先进制造。",
    },
    "alignment": {
        "sector_rotation_agrees": False,
        "note_en": "No active rotation events confirm theme shift.",
        "note_zh": "暂无轮动事件确认主题切换。",
    },
    "themes": {},
    "state_changes": {},
    "prev_asof": "2026-07-16",
}


# ---------------------------------------------------------------------------
# 9. China artifact present → 'china' sub-dict cleaned + display_only preserved
# ---------------------------------------------------------------------------

def test_compose_theme_rotation_china_present(tmp_path: Path):
    """CN artifact present -> 'china' sub-dict in block; US fields unchanged; display_only True."""
    from engine.neuralweb.world_state import _compose_theme_rotation

    # Write US artifact
    tc_path = tmp_path / "site" / "basketdata" / "theme_context.json"
    _write_json(tc_path, _THEME_CTX_FIXTURE)
    # Write CN artifact
    cn_path = tmp_path / "site" / "basketdata" / "theme_context_cn.json"
    _write_json(cn_path, _THEME_CTX_CN_FIXTURE)

    block = _compose_theme_rotation(root=tmp_path)

    # US flat keys preserved byte-for-byte
    assert block["display_only"] is True
    assert block["as_of"] == "2026-07-17"
    assert block["leadership_state"] == "strain"

    # China sub-dict present and cleaned
    cn = block["china"]
    assert cn is not None
    assert cn["display_only"] is True
    assert cn["leadership_state"] == "rotating"
    assert cn["stance_en"] == "Rotation under way — favour the fresh leaders, not the old one."
    assert cn["stance_zh"] == "轮动进行中——关注新领涨主题，勿追旧龙头。"
    assert cn["as_of"] == "2026-07-17"

    # Trailing leader compact
    cn_tl = cn["trailing_leader"]
    assert cn_tl is not None
    assert cn_tl["id"] == "new_energy"
    assert cn_tl["health"] == "broken"
    assert cn_tl["breadth"] == pytest.approx(0.15)

    # Strength: id+name only
    assert cn["strength"] is not None
    assert cn["strength"][0]["id"] == "tech_ai"
    assert cn["strength"][0]["name"] == "Technology & AI"
    assert "desk_score" not in cn["strength"][0]

    # Migration
    cn_mig = cn["migration"]
    assert cn_mig is not None
    assert cn_mig["absorbing"][0]["category"] == "Advanced Manufacturing"
    assert cn_mig["bleeding"][0]["category"] == "New Energy & Autos"

    # Alignment
    assert cn["alignment"]["sector_rotation_agrees"] is False


# ---------------------------------------------------------------------------
# 10. China artifact absent → 'china' is None; US fields unchanged
# ---------------------------------------------------------------------------

def test_compose_theme_rotation_china_absent(tmp_path: Path):
    """CN artifact absent -> 'china' is None; US fields byte-stable."""
    from engine.neuralweb.world_state import _compose_theme_rotation

    # Write only US artifact; no CN file
    tc_path = tmp_path / "site" / "basketdata" / "theme_context.json"
    _write_json(tc_path, _THEME_CTX_FIXTURE)

    block = _compose_theme_rotation(root=tmp_path)

    assert block["china"] is None
    # US fields unaffected
    assert block["leadership_state"] == "strain"
    assert block["display_only"] is True
    assert block["as_of"] == "2026-07-17"


def test_compose_theme_rotation_both_absent(tmp_path: Path):
    """Both US and CN artifacts absent -> null_out with china: None."""
    from engine.neuralweb.world_state import _compose_theme_rotation

    block = _compose_theme_rotation(root=tmp_path)

    assert block["display_only"] is True
    assert block["leadership_state"] is None
    assert block["china"] is None


# ---------------------------------------------------------------------------
# 11. brief_context china path: sub-block present
# ---------------------------------------------------------------------------

def test_block_theme_rotation_china_present():
    """China sub-block present in ws -> returned in brief block."""
    from engine.neuralweb.brief_context import _block_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "leadership_state": "strain",
            "days_in_state": 3,
            "stance_en": "Leadership under strain — watch, don't chase.",
            "stance_zh": "领涨承压——观望，勿追高。",
            "as_of": "2026-07-17",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [{"id": "cybersecurity", "name": "Cybersecurity"}],
            "migration": {
                "absorbing": [{"category": "Healthcare", "avg_breadth": 0.79}],
                "bleeding": [{"category": "Semiconductors", "avg_breadth": 0.07}],
            },
            "alignment": {"sector_rotation_agrees": True},
            "state_changes": None,
            "china": {
                "leadership_state": "rotating",
                "stance_en": "Rotation under way — favour the fresh leaders, not the old one.",
                "stance_zh": "轮动进行中——关注新领涨主题，勿追旧龙头。",
                "as_of": "2026-07-17",
                "trailing_leader": {
                    "id": "new_energy",
                    "name": "New Energy",
                    "health": "broken",
                    "breadth": 0.15,
                    "r10": -0.08,
                },
                "strength": [{"id": "tech_ai", "name": "Technology & AI"}],
                "migration": {
                    "absorbing": [{"category": "Advanced Manufacturing", "avg_breadth": 0.68}],
                    "bleeding": [{"category": "New Energy & Autos", "avg_breadth": 0.12}],
                },
                "alignment": {"sector_rotation_agrees": False},
                "display_only": True,
            },
        }
    }

    block = _block_theme_rotation(ws)
    assert block is not None
    assert block["display_only"] is True

    cn = block["china"]
    assert cn is not None
    assert cn["leadership_state"] == "rotating"
    assert cn["stance_en"] == "Rotation under way — favour the fresh leaders, not the old one."
    assert cn["trailing_leader"]["id"] == "new_energy"
    assert cn["strength_names"] == ["Technology & AI"]
    assert cn["migration_absorbing"] == ["Advanced Manufacturing"]
    assert cn["migration_bleeding"] == ["New Energy & Autos"]
    assert cn["sector_rotation_agrees"] is False


def test_block_theme_rotation_china_absent():
    """China key absent in ws.theme_rotation -> china: None in block."""
    from engine.neuralweb.brief_context import _block_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "leadership_state": "strain",
            "stance_en": "Leadership under strain — watch, don't chase.",
            "as_of": "2026-07-17",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [],
            "migration": {},
            "alignment": {},
            # No 'china' key
        }
    }

    block = _block_theme_rotation(ws)
    assert block is not None
    assert block["china"] is None


# ---------------------------------------------------------------------------
# 12. mastermind_context china path: sub-block present / absent
# ---------------------------------------------------------------------------

def test_summarize_theme_rotation_china_present(tmp_path: Path):
    """China sub-block in world_state -> lobe['china'] non-None."""
    from engine.neuralweb.mastermind_context import _summarize_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "as_of": "2026-07-17",
            "leadership_state": "strain",
            "days_in_state": 3,
            "stance_en": "Leadership under strain — watch, don't chase.",
            "stance_zh": "领涨承压——观望，勿追高。",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [{"id": "cybersecurity", "name": "Cybersecurity"}],
            "migration": {
                "absorbing": [{"category": "Healthcare", "avg_breadth": 0.79}],
                "bleeding": [{"category": "Semiconductors", "avg_breadth": 0.07}],
            },
            "alignment": {"sector_rotation_agrees": True},
            "state_changes": None,
            "china": {
                "leadership_state": "rotating",
                "stance_en": "Rotation under way — favour the fresh leaders, not the old one.",
                "stance_zh": "轮动进行中——关注新领涨主题，勿追旧龙头。",
                "as_of": "2026-07-17",
                "trailing_leader": {
                    "id": "new_energy",
                    "name": "New Energy",
                    "health": "broken",
                    "breadth": 0.15,
                    "r10": -0.08,
                },
                "strength": [{"id": "tech_ai", "name": "Technology & AI"}],
                "migration": {
                    "absorbing": [{"category": "Advanced Manufacturing", "avg_breadth": 0.68}],
                    "bleeding": [{"category": "New Energy & Autos", "avg_breadth": 0.12}],
                },
                "alignment": {"sector_rotation_agrees": False},
                "display_only": True,
            },
        }
    }
    ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
    _write_json(ws_path, ws)

    lobe, gap = _summarize_theme_rotation(tmp_path)

    assert gap is None
    assert lobe["display_only"] is True
    # US fields intact
    assert lobe["leadership_state"] == "strain"
    assert lobe["trailing_leader_id"] == "memory_storage"

    cn = lobe["china"]
    assert cn is not None
    assert cn["leadership_state"] == "rotating"
    assert cn["trailing_leader_id"] == "new_energy"
    assert cn["trailing_leader_health"] == "broken"
    assert cn["strength_names"] == ["Technology & AI"]
    assert cn["migration_absorbing"] == ["Advanced Manufacturing"]
    assert cn["migration_bleeding"] == ["New Energy & Autos"]
    assert cn["sector_rotation_agrees"] is False
    assert "validated" not in str(lobe)


def test_summarize_theme_rotation_china_absent(tmp_path: Path):
    """No china key in world_state.theme_rotation -> lobe['china'] is None."""
    from engine.neuralweb.mastermind_context import _summarize_theme_rotation

    ws = {
        "theme_rotation": {
            "display_only": True,
            "as_of": "2026-07-17",
            "leadership_state": "strain",
            "stance_en": "Leadership under strain — watch, don't chase.",
            "trailing_leader": {
                "id": "memory_storage",
                "name": "Memory / Storage",
                "health": "broken",
                "breadth": 0.0,
                "r10": -0.127,
            },
            "strength": [],
            "migration": {},
            "alignment": {},
            # No 'china' key
        }
    }
    ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
    _write_json(ws_path, ws)

    lobe, gap = _summarize_theme_rotation(tmp_path)

    assert gap is None
    assert lobe["china"] is None
    # US fields unaffected
    assert lobe["leadership_state"] == "strain"
    assert lobe["display_only"] is True
