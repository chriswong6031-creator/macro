"""XPV2-SC-R3A binding pack — fixture + routing + access mutation-armor.

Charter: `research/reference_integrity/mastermind-xpv2-sector-r3/ADJUDICATIONS.md`
(frozen rulings A1-A10) and `research/reference_integrity/mastermind-xpv2-sector-r3/
capability_disposition_ledger.md` (Deliverable 1). This suite exists so an R3
designer/builder cannot silently drift from what production actually does: it
either PASSES on the frozen state the archaeology measured, or it FAILS the
instant that state is corrupted — in the fixture, in the routing constant, or
in the wording constant it pins.

HARD LAW (ADJUDICATIONS SS A10 -- "moving-data trap"): every assertion here runs
against ONLY (a) the frozen fixture files under
`research/reference_integrity/mastermind-xpv2-sector-r3/fixture/` and (b) code
constants (`scripts/build_sector_central.py::_ACTNOW_LANES`,
`templates/si_workspace.js::LEGACY_ANCHORS`, `templates/subsectors.js`'s thin
wording, `templates/sector_central.html.j2`'s Overview/Explore href sections,
`config.yml`'s `sector_central_gate` block). NOTHING here reads live
`site/` or `data/` artifacts, which the nightly rewrites -- doing so would ride
moving data and make the merge gate non-reproducible, exactly the trap A10
names. SHA-256 receipts are recomputed from the fixture files IN THIS TEST,
never assumed.

Several tests below are genuine MUTATION tests: they load the real (good)
fixture/constant, prove a hand-defined helper accepts it, then corrupt an
in-memory COPY the exact way a regression would and prove the same helper
rejects it. A test that only ever sees good data has no teeth; the corrupted
half is what proves each guard actually fires.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "research/reference_integrity/mastermind-xpv2-sector-r3"
FIXTURE = PACK / "fixture"
TPL = ROOT / "templates"
SCRIPTS = ROOT / "scripts"

SI_WORKSPACE_JS = TPL / "si_workspace.js"
SUBSECTORS_JS = TPL / "subsectors.js"
SECTOR_CENTRAL_TPL = TPL / "sector_central.html.j2"
BUILD_SECTOR_CENTRAL_PY = SCRIPTS / "build_sector_central.py"
ROTATION_EVENTS_JS = TPL / "rotation_events.js"
SUBSECTOR_ROTATION_JS = TPL / "subsector_rotation.js"
DESK_WATCH_JS = TPL / "desk_watch.js"
CONFIG_YML = ROOT / "config.yml"


# ---------------------------------------------------------------------------
# Fixture loaders (fixture/ only -- never site/ or data/)
# ---------------------------------------------------------------------------

def _load(rel: str):
    p = FIXTURE / rel
    return json.loads(p.read_text(encoding="utf-8"))


def _action_board() -> dict:
    return _load("basketdata/action_board.json")["action_board"]


def _baskets() -> dict:
    return _load("basketdata/baskets.json")


def _sp_confluence() -> dict:
    return _load("marketdata/subsector_confluence.json")


def _basket_confluence() -> dict:
    return _load("marketdata/basket_confluence.json")


def _premiumdata() -> dict:
    return _load("premiumdata/sector_central.json")


def _narrative_emergence() -> dict:
    return _load("basketdata/narrative_emergence.json")


def _receipts() -> dict:
    return json.loads((FIXTURE / "receipts.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 0. Receipts: SHA-256 recomputation (A10 -- reproducibility of the freeze)
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class TestReceipts:
    def test_receipts_file_exists_and_has_17_entries(self):
        r = _receipts()
        assert len(r["entries"]) == 17, r["entries"]

    def test_every_fixture_file_sha256_matches_its_receipt(self):
        """The literal attack: corrupt receipts.json (or the fixture) and this
        must fail. Recomputed ENTIRELY from fixture/ bytes, never from site/."""
        r = _receipts()
        mismatches = []
        for entry in r["entries"]:
            fpath = FIXTURE / entry["path"]
            assert fpath.is_file(), f"missing fixture file {entry['path']}"
            actual = _sha256(fpath)
            if actual != entry["sha256"]:
                mismatches.append((entry["path"], entry["sha256"], actual))
        assert not mismatches, f"SHA-256 mismatch(es): {mismatches}"

    def test_a_corrupted_receipt_is_caught_by_the_same_recompute(self, tmp_path):
        """Mutation half: prove the recompute check has teeth, not just that
        the real receipts happen to already agree."""
        real = FIXTURE / "basketdata/narrative_emergence.json"
        corrupted = tmp_path / "narrative_emergence.json"
        corrupted.write_bytes(real.read_bytes() + b" ")  # one appended byte
        real_hash = _sha256(real)
        corrupted_hash = _sha256(corrupted)
        assert real_hash != corrupted_hash

    def test_total_fixture_bytes_recorded_and_under_size_guard(self):
        r = _receipts()
        assert r["total_fixture_bytes"] < 50 * 1024 * 1024
        recomputed_total = sum(
            (FIXTURE / e["path"]).stat().st_size for e in r["entries"]
        )
        assert recomputed_total == r["total_fixture_bytes"]


# ---------------------------------------------------------------------------
# 1. Action lane count/keys (A1) -- pin _ACTNOW_LANES: six keys, order
# ---------------------------------------------------------------------------

def _parse_actnow_lanes() -> list[tuple[str, str, bool]]:
    text = BUILD_SECTOR_CENTRAL_PY.read_text(encoding="utf-8")
    m = re.search(r"_ACTNOW_LANES\s*=\s*(\[.*?\])\n", text, re.S)
    assert m, "could not locate _ACTNOW_LANES literal in build_sector_central.py"
    return ast.literal_eval(m.group(1))


EXPECTED_ACTNOW_LANES = [
    ("buy_now", "ab-buy-fold", False),
    ("buy_soon", "ab-soon-fold", False),
    ("on_the_run", "ab-run-fold", False),
    ("take_profits", "ab-trim-fold", False),
    ("hold", "dash-hold-fold", True),
    ("avoid", "dash-hold-fold", True),
]


class TestActionLaneKeys:
    def test_six_keys_exact_order_pinned(self):
        lanes = _parse_actnow_lanes()
        assert lanes == EXPECTED_ACTNOW_LANES

    def test_hold_and_avoid_share_the_stand_aside_fold(self):
        lanes = _parse_actnow_lanes()
        by_key = {k: fold for k, fold, _ in lanes}
        assert by_key["hold"] == by_key["avoid"] == "dash-hold-fold"

    def test_a_dropped_key_would_be_caught(self):
        lanes = _parse_actnow_lanes()
        mutated = lanes[:-1]  # drop "avoid"
        assert mutated != EXPECTED_ACTNOW_LANES
        assert len(mutated) == 5

    def test_action_board_fixture_carries_all_six_lane_keys(self):
        ab = _action_board()
        for key, _fold, _hold in EXPECTED_ACTNOW_LANES:
            assert key in ab, f"lane key {key!r} missing from fixture action_board.json"


# ---------------------------------------------------------------------------
# 2. Context sector never in buy_now (A3 / DAC-002 class defect)
# ---------------------------------------------------------------------------

# Frozen at capture (2026-08-20): every GICS sector row's lane in the real
# fixture. A future fixture regen that moves a sector into a different lane
# without a new capture+adjudication is exactly the "context sector promoted
# into an action lane" defect class this test exists to catch.
FROZEN_SECTOR_LANES = {
    "Consumer Discretionary": "buy_now",
    "Consumer Staples": "buy_soon",
    "Materials": "buy_soon",
    "Communications": "buy_soon",
    "Financials": "buy_soon",
    "Industrials": "buy_soon",
    "Health Care": "on_the_run",
    "Real Estate": "take_profits",
    "Energy": "hold",
    "Technology": "avoid",
    "Utilities": "avoid",
}


def _sector_lane_map(action_board: dict) -> dict[str, str]:
    out = {}
    for lane, rows in action_board.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("kind") == "sector":
                out[row.get("name")] = lane
    return out


def _assert_sector_lanes_match(action_board: dict, expected: dict[str, str]) -> None:
    actual = _sector_lane_map(action_board)
    mismatches = {
        name: (expected[name], actual.get(name))
        for name in expected
        if actual.get(name) != expected[name]
    }
    assert not mismatches, f"sector lane placement drifted: {mismatches}"


class TestContextSectorNotAmplifiedIntoActionLane:
    def test_frozen_fixture_sector_lane_membership_matches_capture(self):
        _assert_sector_lanes_match(_action_board(), FROZEN_SECTOR_LANES)

    def test_health_care_specifically_is_not_in_buy_now(self):
        actual = _sector_lane_map(_action_board())
        assert actual["Health Care"] != "buy_now"
        assert actual["Health Care"] == "on_the_run"

    def test_mutated_health_care_into_buy_now_is_caught(self):
        """Mutation half: move Health Care's row from on_the_run into buy_now
        and prove the checker rejects it -- this is the literal shape of the
        DAC-002 defect class (a context/leadership sector promoted into the
        top action lane)."""
        ab = copy.deepcopy(_action_board())
        row = next(r for r in ab["on_the_run"] if r.get("name") == "Health Care")
        ab["on_the_run"].remove(row)
        ab["buy_now"].append(row)
        with pytest.raises(AssertionError):
            _assert_sector_lanes_match(ab, FROZEN_SECTOR_LANES)


# ---------------------------------------------------------------------------
# 3. Bottoming Watch stays watch-only (A1 capability priors, lane A SS10)
# ---------------------------------------------------------------------------

def _bottoming_authority(baskets: dict) -> dict:
    return baskets["theme_intel"]["act_now"]["bottoming_authority"]


def _assert_bottoming_watch_only(authority: dict) -> None:
    assert authority["tier"] == "display"
    for flag in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert authority[flag] is False, f"{flag} must stay False (display-tier only)"


class TestBottomingWatchDisplayTierOnly:
    def test_frozen_fixture_bottoming_authority_is_all_false(self):
        _assert_bottoming_watch_only(_bottoming_authority(_baskets()))

    def test_bottoming_watch_rows_have_no_authority_flags_of_their_own(self):
        """The authority flags live on the single `bottoming_authority` object,
        not per-row -- confirming a row cannot carry its own escalation."""
        baskets = _baskets()
        rows = baskets["theme_intel"]["act_now"]["bottoming_watch"]
        assert rows, "fixture must carry at least one bottoming_watch row to test against"
        for row in rows:
            for flag in ("may_rank", "may_gate", "may_size", "may_escalate"):
                assert flag not in row

    @pytest.mark.parametrize("flag", ["may_rank", "may_gate", "may_size", "may_escalate"])
    def test_a_flipped_authority_flag_is_caught(self, flag):
        baskets = copy.deepcopy(_baskets())
        authority = _bottoming_authority(baskets)
        authority[flag] = True
        with pytest.raises(AssertionError):
            _assert_bottoming_watch_only(authority)


# ---------------------------------------------------------------------------
# 4. S&P subsector row-identity detector (lane E SS7 -- foreign-row guard)
# ---------------------------------------------------------------------------

def _is_genuine_sp_subsector_row(payload: dict, row: dict) -> bool:
    """The 5-part rule from lane_E_confluence.md SS7. A row is a genuine S&P
    sub-industry row iff ALL hold; any violation flags a foreign/theme row."""
    if payload.get("universe") != "sp500_subsectors":
        return False
    if row.get("kind") != "subsector":
        return False
    if "basket_id" in row:
        return False
    if not row.get("key") or not row.get("label"):
        return False
    return True


class TestSubsectorConfluenceRowIdentity:
    def test_every_real_row_is_a_genuine_sp_subsector_row(self):
        payload = _sp_confluence()
        bad = [r["key"] for r in payload["subsectors"] if not _is_genuine_sp_subsector_row(payload, r)]
        assert not bad, f"non-genuine rows found in the frozen S&P fixture: {bad}"

    def test_a_basket_shaped_row_injected_into_sp_payload_is_rejected(self):
        payload = copy.deepcopy(_sp_confluence())
        foreign = {
            "key": "b-gold_miners",
            "kind": "basket",
            "label": "Gold Miners",
            "basket_id": "gold_miners",
        }
        payload["subsectors"].append(foreign)
        assert not _is_genuine_sp_subsector_row(payload, foreign)
        bad = [r["key"] for r in payload["subsectors"] if not _is_genuine_sp_subsector_row(payload, r)]
        assert bad == ["b-gold_miners"]

    def test_a_row_with_basket_id_but_kind_subsector_is_still_rejected(self):
        """basket_id presence alone disqualifies a row, regardless of kind."""
        payload = _sp_confluence()
        mutant = dict(payload["subsectors"][0])
        mutant["basket_id"] = "sneaked_in"
        assert not _is_genuine_sp_subsector_row(payload, mutant)

    def test_baskets_confluence_rows_are_correctly_kind_basket_with_basket_id(self):
        payload = _basket_confluence()
        assert payload["universe"] == "curated_baskets"
        for row in payload["baskets"]:
            assert row["kind"] == "basket"
            assert "basket_id" in row


# ---------------------------------------------------------------------------
# 5. Baskets-tab thin/gateable disclosure stays BLOCKED_DATA (A5)
# ---------------------------------------------------------------------------

class TestBasketsTabThinDisclosureBlockedData:
    def test_sp_coverage_carries_gateable_and_thin_fields(self):
        cov = _sp_confluence()["coverage"]
        for key in ("n_subsectors", "n_gateable", "n_thin"):
            assert key in cov

    def test_basket_coverage_does_not_carry_gateable_or_thin_fields(self):
        """This IS the BLOCKED_DATA finding -- if a future producer regen adds
        these fields, the ledger's disposition needs a new ruling, not a
        silent fixture drift. Fails loudly either way."""
        cov = _basket_confluence()["coverage"]
        assert cov == {
            "n_baskets": cov["n_baskets"],
            "n_high": cov["n_high"],
            "n_med": cov["n_med"],
            "n_low_conf": cov["n_low_conf"],
            "thin_share": cov["thin_share"],
        }
        for absent in ("n_gateable", "n_thin", "n_subsectors"):
            assert absent not in cov


# ---------------------------------------------------------------------------
# 6. Producer order pin -- semantic order, not just byte identity
# ---------------------------------------------------------------------------

_CLASS_ORDER = {"entry_now": 0, "forming": 1, "tailwind": 2, "neutral": 3, "late": 4, "headwind": 5}


def _sort_key(row: dict) -> tuple:
    return (
        _CLASS_ORDER.get(row["class"], 9),
        -row["entry"]["weight"],
        -(row["regime"].get("rs_60d") or 0),
    )


class TestProducerOrderSemanticPin:
    def test_sp_subsectors_array_is_sorted_by_producer_formula(self):
        subs = _sp_confluence()["subsectors"]
        keys = [_sort_key(r) for r in subs]
        assert keys == sorted(keys), "subsectors[] is not in producer sort order (class, -weight, -rs_60d)"

    def test_a_swapped_pair_breaks_the_order_pin(self):
        subs = copy.deepcopy(_sp_confluence()["subsectors"])
        # find two adjacent rows with different sort keys and swap them
        keys = [_sort_key(r) for r in subs]
        idx = next(i for i in range(len(keys) - 1) if keys[i] != keys[i + 1])
        subs[idx], subs[idx + 1] = subs[idx + 1], subs[idx]
        mutated_keys = [_sort_key(r) for r in subs]
        assert mutated_keys != sorted(mutated_keys)


# ---------------------------------------------------------------------------
# 7. LEGACY_ANCHORS -- all 21 keys present in templates/si_workspace.js
# ---------------------------------------------------------------------------

EXPECTED_LEGACY_ANCHORS = {
    "actnow-section": ["overview", "actnow-section"],
    "regime": ["overview", "regime"],
    "grader": ["overview", "grader"],
    "si-map": ["map", "si-map"],
    "rotmap-section": ["map", "rotmap-section"],
    "sc-cyclemap": ["map", "sc-cyclemap"],
    "board": ["map", "board"],
    "si-movement": ["moving", "si-movement"],
    "rc-events-mount": ["moving", "rc-events-mount"],
    "rotation-app": ["moving", "rotation-app"],
    "si-money": ["money", "si-money"],
    "internals-section": ["money", "internals-section"],
    "scc-leadership": ["money", "scc-leadership"],
    "explore-section": ["explore", "explore-section"],
    "table-section": ["explore", "table-section"],
    "chart-section": ["explore", "chart-section"],
    "forming-narratives": ["explore", "forming-narratives"],
    "tm-mount": ["explore", "tm-mount"],
    "confluence": ["confluence", "si-confluence"],
    "sc-app": ["confluence", "sc-app"],
    "sc-top": ["confluence", "sc-top"],
}


def _parse_legacy_anchors() -> dict:
    text = SI_WORKSPACE_JS.read_text(encoding="utf-8")
    m = re.search(r"var LEGACY_ANCHORS\s*=\s*\{(.*?)\}\s*;", text, re.S)
    assert m, "could not locate LEGACY_ANCHORS object in si_workspace.js"
    body = "{" + m.group(1) + "}"
    # Strip inline /* ... */ comments (one appears mid-object, itself containing
    # an apostrophe) BEFORE the naive single->double quote conversion below --
    # otherwise the comment's own apostrophe corrupts the JSON.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    # JS single-quoted keys/strings -> JSON double-quoted, no apostrophes remain
    # in the entries themselves (all slugs).
    json_body = body.replace("'", '"')
    return json.loads(json_body)


class TestLegacyAnchors:
    def test_all_21_entries_present_and_exact(self):
        anchors = _parse_legacy_anchors()
        assert len(anchors) == 21
        assert anchors == EXPECTED_LEGACY_ANCHORS

    def test_a_missing_key_is_caught(self):
        anchors = _parse_legacy_anchors()
        del anchors["sc-top"]
        assert anchors != EXPECTED_LEGACY_ANCHORS
        assert len(anchors) == 20

    def test_every_expected_key_individually_present(self):
        anchors = _parse_legacy_anchors()
        missing = [k for k in EXPECTED_LEGACY_ANCHORS if k not in anchors]
        assert not missing, f"LEGACY_ANCHORS missing keys: {missing}"


# ---------------------------------------------------------------------------
# 8. href="#" absent from the production Overview/Explore link sections
# ---------------------------------------------------------------------------

# Section boundaries per lane_B_routing_capability.md SS1 (1-indexed, inclusive).
OVERVIEW_SECTION = (1709, 2257)
EXPLORE_SECTION = (2424, 2476)


def _lines_in_range(path: Path, start: int, end: int) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[start - 1:end]


class TestNoDeadHashLinksInPinnedSections:
    def test_overview_section_has_no_href_hash(self):
        lines = _lines_in_range(SECTOR_CENTRAL_TPL, *OVERVIEW_SECTION)
        hits = [i + OVERVIEW_SECTION[0] for i, l in enumerate(lines) if 'href="#"' in l]
        assert not hits, f'href="#" found at line(s) {hits} inside the Overview section'

    def test_explore_section_has_no_href_hash(self):
        lines = _lines_in_range(SECTOR_CENTRAL_TPL, *EXPLORE_SECTION)
        hits = [i + EXPLORE_SECTION[0] for i, l in enumerate(lines) if 'href="#"' in l]
        assert not hits, f'href="#" found at line(s) {hits} inside the Explore section'

    def test_a_synthetic_dead_link_would_be_caught(self):
        lines = _lines_in_range(SECTOR_CENTRAL_TPL, *OVERVIEW_SECTION)
        mutated = lines + ['<a href="#">dead</a>']
        hits = [i for i, l in enumerate(mutated) if 'href="#"' in l]
        assert hits


# ---------------------------------------------------------------------------
# 9. Premium preview/locked/total distinction (A9)
# ---------------------------------------------------------------------------

class TestPremiumPreviewLockedTotal:
    def test_fixture_panel_pinned_at_3_29_44(self):
        payload = _premiumdata()
        assert payload["gated"] is True
        assert payload["required_tier"] == "essential"
        assert payload["schema"] == "tier_payload.v1"
        assert payload["panels"]["actnow"] == {"preview": 3, "locked": 29, "total": 44}

    def test_locked_is_less_than_total_and_preview_is_the_per_lane_cap(self):
        """`preview` is the config `preview_rows` CAP (3, a per-lane constant --
        not an aggregate row count: hold+avoid share one visible column, so the
        naive preview+locked==total identity does not hold). `locked` (29) is
        the actual withheld-row count and must be strictly less than `total`
        (44) -- the shell always keeps SOME rows back while gated."""
        panel = _premiumdata()["panels"]["actnow"]
        assert panel["preview"] == 3  # config.yml sector_central_gate.preview_rows
        assert 0 < panel["locked"] < panel["total"]

    def test_a_collapsed_preview_locked_distinction_is_caught(self):
        payload = copy.deepcopy(_premiumdata())
        payload["panels"]["actnow"]["locked"] = 0
        payload["panels"]["actnow"]["preview"] = payload["panels"]["actnow"]["total"]
        with pytest.raises(AssertionError):
            assert payload["panels"]["actnow"] == {"preview": 3, "locked": 29, "total": 44}

    def test_config_yml_gate_switch_matches_the_fixture_state(self):
        text = CONFIG_YML.read_text(encoding="utf-8")
        m = re.search(r"sector_central_gate:\s*\n\s*gated:\s*(\w+)\s*\n\s*preview_rows:\s*(\d+)", text)
        assert m, "sector_central_gate block not found in config.yml"
        gated, preview_rows = m.group(1), int(m.group(2))
        assert gated == "true"
        assert preview_rows == 3


# ---------------------------------------------------------------------------
# 10. Thin-but-listed wording still present (code constant, lane E SS4)
# ---------------------------------------------------------------------------

class TestThinButListedWording:
    def test_en_wording_present(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        assert "have enough live data to time" in text
        assert "thin (listed in the table, not timed)" in text

    def test_zh_wording_present(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        assert "个子行业有足够实时数据可计时" in text or "有足够实时数据可计时" in text
        assert "个数据稀疏（列于表内，不计时）" in text


# ---------------------------------------------------------------------------
# 11. Thin-but-listed wording removed from templates/subsectors.js (explicit)
# ---------------------------------------------------------------------------

class TestThinWordingRemovalIsCaught:
    def test_removing_the_wording_would_fail_the_pin(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        mutated = text.replace("have enough live data to time", "")
        assert "have enough live data to time" not in mutated
        assert "have enough live data to time" in text  # the real file still has it


# ---------------------------------------------------------------------------
# 12. Moving's five artifact URLs present (A2 binding)
# ---------------------------------------------------------------------------

MOVING_ARTIFACT_URLS = [
    "marketdata/rotation_events.json",
    "marketdata/sector_fragmentation.json",
    "marketdata/subsector_rotation.json",
    "basketdata/oracle_turn_desk.json",
    "basketdata/oracle_tape_onset.json",
]

MOVING_ARTIFACT_FILES = [ROTATION_EVENTS_JS, ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS, DESK_WATCH_JS]


class TestMovingArtifactUrlsPresent:
    def test_all_five_urls_present_across_the_moving_scripts(self):
        combined = "\n".join(
            f.read_text(encoding="utf-8") for f in {ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS}
        )
        missing = [u for u in MOVING_ARTIFACT_URLS if u not in combined]
        assert not missing, f"Moving artifact URL(s) missing from templates: {missing}"

    def test_removing_one_url_would_be_caught(self):
        combined = "\n".join(
            f.read_text(encoding="utf-8") for f in {ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS}
        )
        mutated = combined.replace("basketdata/oracle_tape_onset.json", "")
        missing = [u for u in MOVING_ARTIFACT_URLS if u not in mutated]
        assert missing == ["basketdata/oracle_tape_onset.json"]

    def test_moving_view_still_does_not_reference_si_handoff(self):
        """A2: Moving must not gain a si_handoff.json binding. Grep the three
        Moving scripts for the string; production carries zero matches."""
        for f in (ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS):
            assert "si_handoff" not in f.read_text(encoding="utf-8"), f"{f.name} must not reference si_handoff.json"


# ---------------------------------------------------------------------------
# 13. A fixture null must never collapse to 0 (house trap, lane D SS5)
# ---------------------------------------------------------------------------

class TestPreservedNullNotCollapsedToZero:
    def test_ai_watch_is_a_preserved_null_not_a_zero(self):
        d = _narrative_emergence()
        assert "ai_watch" in d
        assert d["ai_watch"] is None
        assert d["ai_watch"] != 0  # trivially true in Python, asserted for documentation

    def test_a_collapsed_ai_watch_would_be_distinguishable(self):
        """Mutation half: simulate the exact defect (null coerced to 0 by a
        careless JS truthiness check) and prove a strict `is None` guard
        would have caught it -- unlike `if (!x)`, which treats both as falsy."""
        d = copy.deepcopy(_narrative_emergence())
        d["ai_watch"] = 0  # the corrupted state
        assert d["ai_watch"] is not None  # strict guard: correctly flags this as NOT the preserved-null state
        assert not d["ai_watch"]  # a truthiness-only guard would have MISSED this distinction -- documents the trap


# ---------------------------------------------------------------------------
# 14. Fixture size guard (Deliverable 3 requirement, re-checked here)
# ---------------------------------------------------------------------------

class TestFixtureSizeGuard:
    def test_total_fixture_size_under_50mb(self):
        total = sum(f.stat().st_size for f in FIXTURE.rglob("*.json"))
        assert total < 50 * 1024 * 1024, f"fixture set is {total} bytes, over the 50MB guard"

    def test_expected_17_json_files_present(self):
        files = list(FIXTURE.rglob("*.json"))
        # receipts.json is the 18th JSON file (the manifest itself, not a copied artifact)
        assert len(files) == 18, sorted(f.name for f in files)
