"""Crosswalk v3 — the CN column family, added ADDITIVELY (masterplan §4.3, gate G0.9).

``config/theme_crosswalk.yml`` is TIL's live vocabulary and is read by a dozen nightly
consumers. GMI extends it IN PLACE and must never fork it into vocabulary N+1, so the
v3 columns are constrained twice over:

* every v2 field must still be present on every row, with the v2 row set unchanged and
  the v2 top-level blocks intact — the byte-level proof ran against HEAD in the wave PR;
  what this suite pins is that a later edit cannot quietly DROP one of them;
* the three new columns must be well-formed and self-consistent: theme_node_id agrees
  with the row's own id, THS codes are digit strings and unique per row, and the CN
  basket ids are plausible basket keys.

Deliberately format-and-consistency only: nothing here reads ``data/`` (a mapping is not
made true by a basket happening to exist in this checkout, and a sparse checkout carries
no membership documents at all), and nothing pins a live count beyond the 18 canonical
themes that `tests/test_thematic_state.py` already owns.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CROSSWALK = ROOT / "config" / "theme_crosswalk.yml"

#: Present on every row since v2. A v3 edit may ADD, never remove.
V2_ROW_FIELDS = ("id", "name_en", "name_zh", "foresight_id", "primary_basket_id",
                 "basket_ids", "subsector_keys", "citrini_basket_ids", "note")
V3_ROW_FIELDS = ("theme_node_id", "ths_concept_ids", "cn_basket_ids")

DOC = yaml.safe_load(CROSSWALK.read_text(encoding="utf-8"))
THEMES = DOC["themes"]

BASKET_ID_RE = re.compile(r"^[a-z0-9_]+$")


# ---------------------------------------------------------------------------
# Additivity
# ---------------------------------------------------------------------------

def test_the_version_is_bumped_and_the_changelog_records_the_wave():
    assert DOC["version"] == 3
    text = CROSSWALK.read_text(encoding="utf-8")
    assert "GMI W1b" in text and "additive only" in text


@pytest.mark.parametrize("field", V2_ROW_FIELDS)
def test_every_row_still_carries_every_v2_field(field):
    missing = [r.get("id", "?") for r in THEMES if field not in r]
    assert not missing, f"v3 dropped {field!r} from {missing}"


def test_the_v2_top_level_blocks_survive():
    assert DOC["date"] and DOC["note"]
    assert isinstance(DOC["unmapped_baskets"], list) and DOC["unmapped_baskets"]
    for row in DOC["unmapped_baskets"]:
        assert row.get("id") and row.get("reason")


def test_the_row_set_is_the_canonical_eighteen_and_ids_are_unique():
    ids = [r["id"] for r in THEMES]
    assert len(ids) == len(set(ids)) == 18
    assert all(r["foresight_id"] for r in THEMES)


def test_citrini_stays_empty_until_the_definitions_are_committed():
    """Operator ruling 2026-08-11: the FEEDS are closed forever, the column may now be
    filled from the in-hand DEFINITIONS — but a mapping to a definition that lives only
    in someone's inbox is not citable, so it stays empty until they land in the repo."""
    assert all(r["citrini_basket_ids"] == [] for r in THEMES)


# ---------------------------------------------------------------------------
# The three new columns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", V3_ROW_FIELDS)
def test_every_row_carries_every_v3_field(field):
    missing = [r.get("id", "?") for r in THEMES if field not in r]
    assert not missing, f"{field!r} missing from {missing}"


def test_theme_node_id_is_the_join_key_and_agrees_with_the_row_id():
    """It joins this file to data/theme_graph/nodes.parquet. A node id that disagreed
    with its own row would join the graph to the wrong theme silently."""
    seen = set()
    for row in THEMES:
        node_id = row["theme_node_id"]
        assert node_id == f"theme:{row['id']}", row["id"]
        assert node_id not in seen
        seen.add(node_id)


def test_ths_concept_ids_are_unique_digit_strings():
    """YAML strings, not integers: THS codes are opaque identifiers and a leading zero
    must survive the round-trip. Duplicates within a row would double an edge."""
    for row in THEMES:
        codes = row["ths_concept_ids"]
        assert isinstance(codes, list), row["id"]
        for code in codes:
            assert isinstance(code, str), f"{row['id']}: {code!r} is not a string"
            assert code.isdigit(), f"{row['id']}: {code!r} is not a digit string"
        assert len(codes) == len(set(codes)), f"{row['id']} repeats a THS code"


def test_no_ths_code_is_claimed_by_two_themes():
    """One board expresses one canonical theme here. A code in two rows would make the
    deterministic join emit two EXPRESSES edges from the same basket."""
    owner: dict[str, str] = {}
    for row in THEMES:
        for code in row["ths_concept_ids"]:
            assert code not in owner, f"{code} claimed by both {owner[code]} and {row['id']}"
            owner[code] = row["id"]
    assert len(owner) >= 1


def test_cn_basket_ids_are_well_formed_and_unique():
    for row in THEMES:
        ids = row["cn_basket_ids"]
        assert isinstance(ids, list), row["id"]
        for bid in ids:
            assert isinstance(bid, str) and BASKET_ID_RE.match(bid), f"{row['id']}: {bid!r}"
            assert bid.startswith("cn_"), f"{row['id']}: {bid!r} is not a CN basket key"
        assert len(ids) == len(set(ids))


def test_at_least_one_row_maps_each_new_column():
    """A file where every new column is empty would satisfy every format rule above and
    mean nothing."""
    assert any(r["ths_concept_ids"] for r in THEMES)
    assert any(r["cn_basket_ids"] for r in THEMES)


# ---------------------------------------------------------------------------
# The CN policy block
# ---------------------------------------------------------------------------

def test_the_cn_concepts_block_declares_its_source_and_its_honest_nulls():
    block = DOC["cn_concepts"]
    assert block["source"] == "data/baskets_china_ths/concept_map.json"
    assert block["source_asof_field"] == "asof"
    for key in ("mapped_note", "unmapped_note", "ai_applications_note", "authority_note"):
        assert block[key].strip(), key


def test_the_unmapped_concepts_are_not_enumerated_in_this_file():
    """The W1a weekly re-scrape means the taxonomy moves; a static list here would be
    stale within a week and would then read as a coverage claim that is no longer true.
    The living count is printed nightly in data/theme_graph/_meta.json instead."""
    block = DOC["cn_concepts"]
    assert "ths_unmapped_concept_count" in block["unmapped_note"]
    assert not any(isinstance(v, list) for v in block.values()), (
        "the policy block must stay prose + pointers — no enumerated concept list")
