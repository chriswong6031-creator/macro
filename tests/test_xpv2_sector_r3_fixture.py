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
constants -- either read as source text (`scripts/build_sector_central.py::_ACTNOW_LANES`,
`templates/si_workspace.js::LEGACY_ANCHORS`, `templates/subsectors.js`'s thin
wording, `templates/sector_central.html.j2`'s staleness guard and href
inventory, `config.yml`'s `sector_central_gate` block) or imported as code
(`scripts.build_sector_central.split_actnow`, a pure function of its
arguments -- importing it does not read or write `site/`/`data/`). NOTHING
here reads live `site/` or `data/` artifacts, which the nightly rewrites --
doing so would ride moving data and make the merge gate non-reproducible,
exactly the trap A10 names. SHA-256 receipts are recomputed from the fixture
files IN THIS TEST, never assumed.

Every mutation test below shares its checker/helper function with the
corresponding "real state" test -- the same function is proven to (a) accept
the real, good input and (b) reject a corrupted in-memory copy of it. A test
that only ever sees good data has no teeth; the corrupted half is what
proves the guard actually fires. Tests that only restate a Python-semantics
fact (list slicing, string containment, `0 is not None`) without invoking a
project-defined checker were removed in the 2026-08-20 adversarial-review
pass -- see git history for the ones that were cut or rewritten.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_sector_central import split_actnow  # noqa: E402

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


def _receipts_mismatches(receipts: dict) -> list[tuple[str, str, str]]:
    """The checker both the real-state and mutation tests share: recompute
    every entry's SHA-256 from the fixture bytes and report any entry whose
    stored hash does not match. Correction/UNREPRESENTED.md has no `site/`
    source but still carries a `sha256`/`size_bytes` receipt and is checked
    identically."""
    mismatches = []
    for entry in receipts["entries"]:
        fpath = FIXTURE / entry["path"]
        if not fpath.is_file():
            mismatches.append((entry["path"], entry["sha256"], "<file missing>"))
            continue
        actual = _sha256(fpath)
        if actual != entry["sha256"]:
            mismatches.append((entry["path"], entry["sha256"], actual))
    return mismatches


class TestReceipts:
    def test_receipts_file_exists_and_has_18_entries(self):
        r = _receipts()
        assert len(r["entries"]) == 18, r["entries"]  # 17 producer copies + correction/UNREPRESENTED.md (B4)

    def test_every_fixture_file_sha256_matches_its_receipt(self):
        """The literal attack: corrupt receipts.json (or the fixture) and this
        must fail. Recomputed ENTIRELY from fixture/ bytes, never from site/."""
        assert not _receipts_mismatches(_receipts())

    def test_a_corrupted_fixture_file_is_caught_by_the_same_checker(self, tmp_path, monkeypatch):
        """Mutation half: run the REAL checker (`_receipts_mismatches`) against
        a receipts set whose stored hash for one entry has been tampered with,
        and prove it reports exactly that entry -- not just that two ad-hoc
        hashes happen to differ."""
        r = copy.deepcopy(_receipts())
        r["entries"][0]["sha256"] = "0" * 64  # tamper with the FIRST entry's stored hash
        mismatches = _receipts_mismatches(r)
        assert len(mismatches) == 1
        assert mismatches[0][0] == r["entries"][0]["path"]

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

def _parse_actnow_lanes_from_text(text: str) -> list[tuple[str, str, bool]]:
    m = re.search(r"_ACTNOW_LANES\s*=\s*(\[.*?\])\n", text, re.S)
    assert m, "could not locate _ACTNOW_LANES literal"
    return ast.literal_eval(m.group(1))


def _parse_actnow_lanes() -> list[tuple[str, str, bool]]:
    return _parse_actnow_lanes_from_text(BUILD_SECTOR_CENTRAL_PY.read_text(encoding="utf-8"))


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

    def test_a_dropped_key_in_source_text_is_caught_by_the_real_parser(self):
        """Mutation half: mutate the SOURCE TEXT (not an already-parsed list)
        and run it back through the real parser, proving the parser -- not
        just a Python list comparison -- notices the missing key."""
        real_text = BUILD_SECTOR_CENTRAL_PY.read_text(encoding="utf-8")
        mutated_text = real_text.replace('    ("avoid", "dash-hold-fold", True),\n', "")
        mutated_lanes = _parse_actnow_lanes_from_text(mutated_text)
        assert mutated_lanes != EXPECTED_ACTNOW_LANES
        assert len(mutated_lanes) == 5
        assert "avoid" not in [k for k, _, _ in mutated_lanes]

    def test_action_board_fixture_carries_all_six_lane_keys(self):
        ab = _action_board()
        for key, _fold, _hold in EXPECTED_ACTNOW_LANES:
            assert key in ab, f"lane key {key!r} missing from fixture action_board.json"


# ---------------------------------------------------------------------------
# 2. Context sector never amplified into an action lane (A3 / DAC-002 class)
# ---------------------------------------------------------------------------

# Frozen at capture (2026-08-20): every GICS sector row's lane in the real
# fixture. A future fixture regen that moves a sector into a different lane,
# duplicates one across lanes, or gains an unrecognized sector name without a
# new capture+adjudication is exactly the "context sector promoted into an
# action lane" defect class this test exists to catch.
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
    """Builds name -> lane for every kind=="sector" row. Raises loudly (not
    silently overwrites) if the same sector name appears in more than one
    lane -- a row belongs in exactly one lane, and last-write-wins would let
    a duplicate-into-buy_now mutation survive undetected (B2)."""
    out: dict[str, str] = {}
    for lane, rows in action_board.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("kind") == "sector":
                name = row.get("name")
                if name in out:
                    raise AssertionError(
                        f"sector {name!r} appears in more than one lane: "
                        f"{out[name]!r} and {lane!r} -- a sector row must be "
                        f"placed in exactly one lane"
                    )
                out[name] = lane
    return out


def _assert_sector_lanes_match(action_board: dict, expected: dict[str, str]) -> None:
    """Bidirectional equality: every EXPECTED sector must be at its frozen
    lane (catches a moved/duplicated row), AND no ACTUAL sector row may be
    unaccounted for in `expected` (catches an entirely NEW sector row
    injected into any lane, e.g. buy_now) (B2)."""
    actual = _sector_lane_map(action_board)
    mismatched = {
        name: (expected[name], actual.get(name))
        for name in expected
        if actual.get(name) != expected[name]
    }
    unexpected = {name: lane for name, lane in actual.items() if name not in expected}
    problems = {}
    if mismatched:
        problems["mismatched"] = mismatched
    if unexpected:
        problems["unexpected_sector_rows"] = unexpected
    assert not problems, f"sector lane placement drifted: {problems}"


class TestContextSectorNotAmplifiedIntoActionLane:
    def test_frozen_fixture_sector_lane_membership_matches_capture(self):
        _assert_sector_lanes_match(_action_board(), FROZEN_SECTOR_LANES)

    def test_health_care_specifically_is_not_in_buy_now(self):
        actual = _sector_lane_map(_action_board())
        assert actual["Health Care"] != "buy_now"
        assert actual["Health Care"] == "on_the_run"

    def test_health_care_moved_into_buy_now_is_caught(self):
        """Mutation half 1/3: MOVE Health Care's row from on_the_run into
        buy_now -- the literal shape of the DAC-002 defect class (a
        context/leadership sector promoted into the top action lane)."""
        ab = copy.deepcopy(_action_board())
        row = next(r for r in ab["on_the_run"] if r.get("name") == "Health Care")
        ab["on_the_run"].remove(row)
        ab["buy_now"].append(row)
        with pytest.raises(AssertionError):
            _assert_sector_lanes_match(ab, FROZEN_SECTOR_LANES)

    def test_health_care_duplicated_into_buy_now_while_staying_in_on_the_run_is_caught(self):
        """Mutation half 2/3 (B2): DUPLICATE Health Care's row into buy_now
        while LEAVING the original in on_the_run. The pre-fix `_sector_lane_map`
        was last-lane-wins on dict assignment, so this exact mutation used to
        survive silently -- `_sector_lane_map` itself must now raise."""
        ab = copy.deepcopy(_action_board())
        hc = next(r for r in ab["on_the_run"] if r.get("name") == "Health Care")
        ab["buy_now"].append(copy.deepcopy(hc))
        with pytest.raises(AssertionError, match="more than one lane"):
            _sector_lane_map(ab)
        with pytest.raises(AssertionError):
            _assert_sector_lanes_match(ab, FROZEN_SECTOR_LANES)

    def test_a_brand_new_sector_row_injected_into_buy_now_is_caught(self):
        """Mutation half 3/3 (B2): inject an entirely NEW sector row (not one
        of the 11 frozen GICS sectors) directly into buy_now. The pre-fix
        `_assert_sector_lanes_match` only iterated `expected` keys, so a
        surprise row with no matching expected entry used to survive
        silently -- the `unexpected_sector_rows` check now catches it."""
        ab = copy.deepcopy(_action_board())
        fake = {"kind": "sector", "name": "Fake Sector", "ticker": "XFAKE"}
        ab["buy_now"].append(fake)
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

def _frozen_sp_keys(payload: dict) -> dict[str, str]:
    """The closed set of the 65 frozen S&P subsector row keys -> sector, as a
    module-level-derivable freeze off the real fixture. This is the piece B1
    found missing: the original checker only asserted `kind`/`basket_id`/
    `universe`, which a THEME row re-stamped `kind="subsector"` with no
    `basket_id` would sail through untouched (rules 1/2/4 of lane_E SS7, but
    never rule 3 -- traceability to the real S&P sub-industry taxonomy). A
    genuine row must additionally be a MEMBER of this closed set, at its
    recorded sector."""
    return {row["key"]: row["sector"] for row in payload["subsectors"]}


def _is_genuine_sp_subsector_row(payload: dict, row: dict, frozen_keys: dict[str, str]) -> bool:
    """The 5-part rule from lane_E_confluence.md SS7, rule 3 now enforced via
    closed-set membership against `frozen_keys` rather than a truthy-string
    check: a row is a genuine S&P sub-industry row iff (1) the payload's own
    `universe` is `sp500_subsectors`, (2) `kind=="subsector"`, (3) it carries
    no `basket_id`, AND (4) its `key` is a member of the frozen 65-key set
    with a MATCHING `sector` -- closing the gap where a foreign row stamped
    `kind="subsector"` with an invented key and no `basket_id` would
    otherwise pass."""
    if payload.get("universe") != "sp500_subsectors":
        return False
    if row.get("kind") != "subsector":
        return False
    if "basket_id" in row:
        return False
    key = row.get("key")
    if key not in frozen_keys:
        return False
    if frozen_keys[key] != row.get("sector"):
        return False
    return True


class TestSubsectorConfluenceRowIdentity:
    def test_every_real_row_is_a_genuine_sp_subsector_row(self):
        payload = _sp_confluence()
        frozen_keys = _frozen_sp_keys(payload)
        bad = [
            r["key"] for r in payload["subsectors"]
            if not _is_genuine_sp_subsector_row(payload, r, frozen_keys)
        ]
        assert not bad, f"non-genuine rows found in the frozen S&P fixture: {bad}"

    def test_a_basket_shaped_row_injected_into_sp_payload_is_rejected(self):
        payload = copy.deepcopy(_sp_confluence())
        frozen_keys = _frozen_sp_keys(payload)  # frozen BEFORE the mutation below
        foreign = {
            "key": "b-gold_miners",
            "kind": "basket",
            "label": "Gold Miners",
            "basket_id": "gold_miners",
            "sector": "Materials",
        }
        payload["subsectors"].append(foreign)
        assert not _is_genuine_sp_subsector_row(payload, foreign, frozen_keys)

    def test_a_row_with_basket_id_but_kind_subsector_is_still_rejected(self):
        """basket_id presence alone disqualifies a row, regardless of kind."""
        payload = _sp_confluence()
        frozen_keys = _frozen_sp_keys(payload)
        mutant = dict(payload["subsectors"][0])
        mutant["basket_id"] = "sneaked_in"
        assert not _is_genuine_sp_subsector_row(payload, mutant, frozen_keys)

    def test_a_theme_row_stamped_kind_subsector_with_no_basket_id_is_rejected(self):
        """B1's exact reviewer mutation: a THEME row re-stamped `kind="subsector"`
        with NO `basket_id` -- the class the pre-fix checker (rules 1/2/4 only)
        let through, because it never checked closed-set membership. Proves
        the fix: `key not in frozen_keys` now catches it even though `kind`
        and `basket_id` both look genuine."""
        payload = copy.deepcopy(_sp_confluence())
        frozen_keys = _frozen_sp_keys(payload)  # frozen BEFORE the mutation below
        foreign = {
            "key": "ai-agents",
            "kind": "subsector",
            "label": "AI Agents",
            "class": "entry_now",
            "sector": "Technology",
        }
        assert "ai-agents" not in frozen_keys, "test fixture assumption broke: ai-agents must not be a real S&P key"
        payload["subsectors"].append(foreign)
        assert not _is_genuine_sp_subsector_row(payload, foreign, frozen_keys), (
            "a theme row stamped kind='subsector' with no basket_id must still be "
            "rejected via closed-set membership (B1)"
        )

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
        for absent in ("n_gateable", "n_thin", "n_subsectors"):
            assert absent not in cov


# ---------------------------------------------------------------------------
# 6. Producer order pin -- semantic order, not just byte identity
# ---------------------------------------------------------------------------

# Faithful transcription of the producer's OWN sort formula
# (engine/subsector_confluence.py:398-399); the `or 0` on rs_60d is
# deliberate -- it is what the producer itself does, not a test simplification.
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


def _parse_legacy_anchors_from_text(text: str) -> dict:
    m = re.search(r"var LEGACY_ANCHORS\s*=\s*\{(.*?)\}\s*;", text, re.S)
    assert m, "could not locate LEGACY_ANCHORS object"
    body = "{" + m.group(1) + "}"
    # Strip inline /* ... */ comments (one appears mid-object, itself containing
    # an apostrophe) BEFORE the naive single->double quote conversion below --
    # otherwise the comment's own apostrophe corrupts the JSON.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    json_body = body.replace("'", '"')
    # Tolerate a trailing comma before the closing brace (valid in JS object
    # literals, not in JSON) -- lets the mutation test below drop the LAST
    # key without independently having to strip its own trailing comma.
    json_body = re.sub(r",(\s*\})\s*$", r"\1", json_body.strip())
    return json.loads(json_body)


def _parse_legacy_anchors() -> dict:
    return _parse_legacy_anchors_from_text(SI_WORKSPACE_JS.read_text(encoding="utf-8"))


class TestLegacyAnchors:
    def test_all_21_entries_present_and_exact(self):
        anchors = _parse_legacy_anchors()
        assert len(anchors) == 21
        assert anchors == EXPECTED_LEGACY_ANCHORS

    def test_a_missing_key_in_source_text_is_caught_by_the_real_parser(self):
        """Mutation half: remove sc-top's SOURCE-TEXT line and re-run the real
        parser, proving the parser (not a dict-diff on an already-parsed
        object) notices the missing key."""
        real_text = SI_WORKSPACE_JS.read_text(encoding="utf-8")
        mutated_text = real_text.replace("  'sc-top':['confluence','sc-top']\n", "")
        mutated_anchors = _parse_legacy_anchors_from_text(mutated_text)
        assert mutated_anchors != EXPECTED_LEGACY_ANCHORS
        assert len(mutated_anchors) == 20
        assert "sc-top" not in mutated_anchors

    def test_every_expected_key_individually_present(self):
        anchors = _parse_legacy_anchors()
        missing = [k for k in EXPECTED_LEGACY_ANCHORS if k not in anchors]
        assert not missing, f"LEGACY_ANCHORS missing keys: {missing}"


# ---------------------------------------------------------------------------
# 8. href="#" absent from the WHOLE production template (S1: strictly
#    stronger than a line-range scan -- zero matches today, whole-file is a
#    superset of the Overview/Explore windows) + one real pinned destination
#    per view from routing_contract.md's inventory
# ---------------------------------------------------------------------------

def _href_hash_hits(text: str) -> list[int]:
    """Checker shared by the real-state and mutation tests: 1-indexed line
    numbers where a literal href="#" appears."""
    return [i + 1 for i, line in enumerate(text.splitlines()) if 'href="#"' in line]


class TestNoDeadHashLinksAnywhereInTemplate:
    def test_whole_template_has_no_href_hash(self):
        """S1: scan the ENTIRE template, not just the Overview/Explore line
        windows -- zero matches today, so the whole-file scan is strictly
        stronger than (a superset of) the two narrower windows it replaces."""
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        hits = _href_hash_hits(text)
        assert not hits, f'href="#" found at line(s) {hits}'

    def test_a_synthetic_dead_link_anywhere_in_the_file_is_caught(self):
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        mutated = text + '\n<a href="#">dead</a>\n'
        hits = _href_hash_hits(mutated)
        assert hits


class TestOneRealDestinationPerView:
    """S1: beyond "no dead links," pin one genuinely real destination string
    per view from routing_contract.md's working-destination inventory (SS7)
    -- these are the load-bearing hrefs a redesign is most likely to
    accidentally drop while refactoring."""

    def test_overview_playbook_link(self):
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        assert 'href="allocation.html"' in text

    def test_explore_table_row_navigates_to_basket_prefix(self):
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        assert "'basket/'+id+'.html'" in text or '"basket/"+id+".html"' in text or "location.href='basket/'" in text

    def test_money_view_stock_destination_pattern_present_in_heatmap_js(self):
        heatmap_js = TPL / "heatmap.js"
        text = heatmap_js.read_text(encoding="utf-8")
        assert "stock.html#" in text

    def test_confluence_stock_destination_pattern_present_in_subsectors_js(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        assert "stock.html#" in text


# ---------------------------------------------------------------------------
# 9. Premium preview/locked/total distinction (A9) -- S3: recomputed from
#    the REAL split_actnow code, not just asserted as a hand-typed literal
# ---------------------------------------------------------------------------

FROZEN_ACTNOW_PANEL = {"preview": 3, "locked": 29, "total": 44}


def _assert_premium_panel_pinned(panel: dict) -> None:
    assert panel == FROZEN_ACTNOW_PANEL


class TestPremiumPreviewLockedTotal:
    def test_fixture_panel_pinned_at_3_29_44(self):
        payload = _premiumdata()
        assert payload["gated"] is True
        assert payload["required_tier"] == "essential"
        assert payload["schema"] == "tier_payload.v1"
        _assert_premium_panel_pinned(payload["panels"]["actnow"])

    def test_split_actnow_recomputes_the_same_panel_from_the_fixture_action_board(self):
        """S3: import the REAL `split_actnow` from `scripts.build_sector_central`
        (a pure function -- no site/data I/O) and recompute the withheld-count
        split from `fixture/basketdata/action_board.json` fresh. Asserting
        equality against BOTH the frozen literal and the fixture premiumdata
        panel means a future regression in split_actnow's own math (not just
        a hand-edited premiumdata fixture) fails this test too."""
        pgate, locked = split_actnow(_action_board(), preview=3, gated=True)
        assert pgate is not None, "split_actnow returned no pgate against a gated board with withheld rows"
        _assert_premium_panel_pinned(pgate["actnow"])
        assert pgate["actnow"] == _premiumdata()["panels"]["actnow"]
        assert len(locked) > 0

    def test_split_actnow_returns_no_count_object_when_ungated(self):
        """N1's corrected invariant, code-bound: with `gated=False` (or an
        ungated board), `split_actnow` returns `(None, [])` -- there is no
        count object AT ALL, not a zeroed-out one."""
        pgate, locked = split_actnow(_action_board(), preview=3, gated=False)
        assert pgate is None
        assert locked == []

    def test_a_collapsed_preview_locked_distinction_is_caught(self):
        mutated_panel = {"preview": 44, "locked": 0, "total": 44}
        with pytest.raises(AssertionError):
            _assert_premium_panel_pinned(mutated_panel)

    def test_config_yml_gate_switch_matches_the_fixture_state(self):
        text = CONFIG_YML.read_text(encoding="utf-8")
        m = re.search(r"sector_central_gate:\s*\n\s*gated:\s*(\w+)\s*\n\s*preview_rows:\s*(\d+)", text)
        assert m, "sector_central_gate block not found in config.yml"
        gated, preview_rows = m.group(1), int(m.group(2))
        assert gated == "true"
        assert preview_rows == 3


# ---------------------------------------------------------------------------
# 10. Thin-but-listed wording -- present today, and its removal is caught
#     (code constant, lane E SS4; the "removal" mutation is folded into the
#     same class per S5 -- one checker, two directions)
# ---------------------------------------------------------------------------

_THIN_WORDING_EN_FRAGMENTS = ("have enough live data to time", "thin (listed in the table, not timed)")
_THIN_WORDING_ZH_FRAGMENTS = ("有足够实时数据可计时", "个数据稀疏（列于表内，不计时）")


def _missing_thin_wording_fragments(text: str) -> list[str]:
    return [f for f in (_THIN_WORDING_EN_FRAGMENTS + _THIN_WORDING_ZH_FRAGMENTS) if f not in text]


class TestThinButListedWording:
    def test_en_and_zh_wording_present(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        assert not _missing_thin_wording_fragments(text)

    def test_removing_the_en_wording_is_caught_by_the_same_checker(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        mutated = text.replace("have enough live data to time", "")
        missing = _missing_thin_wording_fragments(mutated)
        assert "have enough live data to time" in missing


# ---------------------------------------------------------------------------
# 11. Moving's five artifact URLs -- exact-SET assertion (S2), not
#     presence-only: extract every quoted marketdata/*.json and
#     basketdata/*.json literal from the three Moving scripts and assert
#     set-equality with the five canonical artifacts.
# ---------------------------------------------------------------------------

CANONICAL_MOVING_ARTIFACTS = {
    "marketdata/rotation_events.json",
    "marketdata/sector_fragmentation.json",
    "marketdata/subsector_rotation.json",
    "basketdata/oracle_turn_desk.json",
    "basketdata/oracle_tape_onset.json",
}

_ARTIFACT_URL_RE = re.compile(r"['\"]((?:marketdata|basketdata)/[a-zA-Z0-9_]+\.json)['\"]")


def _extract_artifact_urls(text: str) -> set[str]:
    return set(_ARTIFACT_URL_RE.findall(text))


def _moving_scripts_text() -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in (ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS))


class TestMovingArtifactUrlsExactSet:
    def test_moving_scripts_reference_exactly_the_five_canonical_artifacts(self):
        """S2: exact-SET assertion, not presence-only -- this also catches a
        SIXTH artifact appearing (scope creep / a stray reference the
        binding matrix does not know about), not just one disappearing."""
        found = _extract_artifact_urls(_moving_scripts_text())
        assert found == CANONICAL_MOVING_ARTIFACTS, (
            f"missing={CANONICAL_MOVING_ARTIFACTS - found} unexpected={found - CANONICAL_MOVING_ARTIFACTS}"
        )

    def test_removing_one_url_breaks_the_set_equality(self):
        mutated_text = _moving_scripts_text().replace("basketdata/oracle_tape_onset.json", "")
        found = _extract_artifact_urls(mutated_text)
        assert found != CANONICAL_MOVING_ARTIFACTS
        assert CANONICAL_MOVING_ARTIFACTS - found == {"basketdata/oracle_tape_onset.json"}

    def test_adding_a_sixth_artifact_url_also_breaks_the_set_equality(self):
        mutated_text = _moving_scripts_text() + "\n'basketdata/a_sixth_artifact.json'\n"
        found = _extract_artifact_urls(mutated_text)
        assert found != CANONICAL_MOVING_ARTIFACTS
        assert found - CANONICAL_MOVING_ARTIFACTS == {"basketdata/a_sixth_artifact.json"}

    def test_moving_view_still_does_not_reference_si_handoff(self):
        """A2: Moving must not gain a si_handoff.json binding. Grep the three
        Moving scripts for the string; production carries zero matches."""
        for f in (ROTATION_EVENTS_JS, SUBSECTOR_ROTATION_JS, DESK_WATCH_JS):
            assert "si_handoff" not in f.read_text(encoding="utf-8"), f"{f.name} must not reference si_handoff.json"


# ---------------------------------------------------------------------------
# 12. A fixture null must never collapse to 0 (house trap, lane D SS5).
#     Docstring reworded per the adversarial review: this pins the
#     CAPTURE-TIME state (ai_watch happened to be null on 2026-08-20), not a
#     structural guarantee that it is always null.
# ---------------------------------------------------------------------------

class TestPreservedNullAtCaptureTime:
    def test_ai_watch_is_a_preserved_null_at_capture_time_not_a_zero(self):
        """Pins the CAPTURE-TIME state: on 2026-08-20 the gated AI desk had
        not run, so `ai_watch` was `None` in the live payload, and the
        fixture copy preserves that `None` rather than collapsing it to `0`
        or dropping the key. A future capture could legitimately observe a
        non-null `ai_watch` string -- this test is not a claim that the
        field must always be null, only that null (when it occurs) survives
        the copy pipeline as `None`, never `0`."""
        d = _narrative_emergence()
        assert "ai_watch" in d
        assert d["ai_watch"] is None


# ---------------------------------------------------------------------------
# 13. Fixture size guard (Deliverable 3 requirement, re-checked here) + the
#     B4 correction-entry accounting (17 producer JSON artifacts, 1 authored
#     correction doc, 19 total files under fixture/ including receipts.json)
# ---------------------------------------------------------------------------

class TestFixtureSizeGuard:
    def test_total_fixture_size_under_50mb(self):
        total = sum(f.stat().st_size for f in FIXTURE.rglob("*") if f.is_file())
        assert total < 50 * 1024 * 1024, f"fixture set is {total} bytes, over the 50MB guard"

    def test_17_producer_json_artifacts_plus_receipts_json_present(self):
        json_files = list(FIXTURE.rglob("*.json"))
        # 17 producer-copied artifacts + receipts.json itself = 18 .json files.
        # correction/UNREPRESENTED.md is a .md, not counted by this glob.
        assert len(json_files) == 18, sorted(f.name for f in json_files)

    def test_correction_doc_present_and_counted_in_receipts(self):
        doc = FIXTURE / "correction" / "UNREPRESENTED.md"
        assert doc.is_file()
        r = _receipts()
        paths = {e["path"] for e in r["entries"]}
        assert "correction/UNREPRESENTED.md" in paths

    def test_total_files_under_fixture_is_20(self):
        """17 producer JSON + receipts.json + PROVENANCE.md + correction/UNREPRESENTED.md."""
        all_files = [f for f in FIXTURE.rglob("*") if f.is_file()]
        assert len(all_files) == 20, sorted(f.name for f in all_files)


# ---------------------------------------------------------------------------
# 14. B3: Overview absolute-clock stale guard is code-bound-pinned, and
#     Confluence's ABSENCE of any staleness threshold is pinned alongside it
#     (ADJUDICATIONS SS A6: "Overview stale guard fails open on malformed
#     as_of_utc" / "Confluence staleness: no enforcement exists").
# ---------------------------------------------------------------------------

# Whitespace-tolerant, otherwise exact: widening the 12h threshold, dropping
# the isFinite guard, or deleting the guard line all fail this regex.
_STALE_GUARD_RE = re.compile(
    r"isFinite\s*\(\s*builtMs\s*\)\s*&&\s*\(\s*Date\.now\(\)\s*-\s*builtMs\s*\)\s*>\s*12\s*\*\s*3600e3"
)


class TestOverviewStaleGuardCodeBound:
    def test_exact_guard_expression_present(self):
        """ADJUDICATIONS SS A6: 'Overview stale guard fails open on malformed
        as_of_utc' (sector_central.html.j2:1799-1800) -- pin the literal
        expression so widening the 12h window, dropping the `isFinite`
        short-circuit, or deleting the guard entirely all fail loudly."""
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        assert _STALE_GUARD_RE.search(text), "Overview's stale-guard expression not found verbatim"

    def test_widening_the_threshold_is_caught(self):
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        mutated = text.replace("12*3600e3", "24*3600e3")
        assert not _STALE_GUARD_RE.search(mutated)

    def test_dropping_isfinite_is_caught(self):
        text = SECTOR_CENTRAL_TPL.read_text(encoding="utf-8")
        mutated = text.replace(
            "isFinite(builtMs)&&(Date.now()-builtMs)>12*3600e3",
            "(Date.now()-builtMs)>12*3600e3",
        )
        assert not _STALE_GUARD_RE.search(mutated)


class TestConfluenceHasNoStalenessThreshold:
    def test_confluence_payloads_carry_as_of_and_ticks_but_no_threshold_field(self):
        """ADJUDICATIONS SS A6: 'Confluence staleness: no enforcement exists —
        only a baked relative ticks delta and a plain as_of string, zero
        threshold logic.' Confirm the fixture payload shape matches: as_of
        present, at least one entry.ticks present, both plain data fields."""
        payload = _sp_confluence()
        assert "as_of" in payload
        subs = payload["subsectors"]
        assert any("ticks" in s.get("entry", {}) for s in subs)

    def test_subsectors_js_contains_no_date_now_staleness_comparison(self):
        """The other half of the same ruling: subsectors.js has NO
        `Date.now()`/`Date.parse()`-based comparison anywhere -- Confluence's
        staleness is genuinely unenforced, not just differently coded."""
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        assert "Date.now(" not in text
        assert "Date.parse(" not in text

    def test_adding_a_date_now_comparison_would_be_caught(self):
        text = SUBSECTORS_JS.read_text(encoding="utf-8")
        mutated = text + "\nvar stale = (Date.now() - builtMs) > 12*3600e3;\n"
        assert "Date.now(" in mutated  # documents that the guard above would now fire
