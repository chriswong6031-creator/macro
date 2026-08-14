"""The evidence-family registry is enforced by this file, not by prose.

WHAT IS PINNED.  `research/prophet_fusion/families.yml` is the LAW for the Prophet US
Conditional Intelligence Fusion arena (masterplan §5.1/§5.2; PIT verdicts §4.1/§4.2;
staleness/abstention §7 O6; PIT join law §9.1).  The masterplan's §5.1 table is its prose
view.  Every claim below exists because prose alone has already failed at least once
somewhere in this estate:

  * ONE-COLUMN-ONE-FAMILY.  Families are the unit of anti-double-count budgeting at every
    arena rung C1-C5 (§10.6).  A column living in two families is a free second vote, which
    is exactly the failure the family construct exists to prevent — so uniqueness is a test
    over the file, never a rule in a document.  The four single-home RULINGS (`ext_z`->F2,
    relay->F3, theme heat->F3, turnover->F5) are additionally pinned BY NAME, because a
    generic uniqueness test passes just as happily after someone moves `ext_z` to F8.

  * NO PHANTOM COLUMNS.  A registry that names a column the store does not have is worse
    than an incomplete one: the harness silently reads nothing and the family scores a
    clean null.  Every `columns:` entry of a wired member must exist in the candidates
    store's real parquet schema.

  * ANTI-AUTHORITY-CREEP.  The `authority:` block is all-false and must stay all-false.
    This artifact ranks nothing, sizes nothing, gates nothing, originates nothing,
    escalates nothing.  Flipping a boolean here is a doctrine amendment, not a refactor.

  * PIT STATUS IS LOAD-BEARING.  `snapshot_not_pit` members (short interest, forensics)
    are HARD-REFUSED in backtest frames (§4.2 flags 2 and 4).  If the registry stops
    marking them, a backtest reads today's snapshot into 2026-06 rows and the leakage is
    invisible — it looks like signal.

Run: python3 -m pytest tests/test_prophet_fusion_families.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "research" / "prophet_fusion" / "families.yml"
CANDIDATES_PARQUET = ROOT / "data" / "us_prophet_rank" / "candidates" / "2026-08.parquet"
LEDGER_PARQUET = ROOT / "data" / "us_board_ledger" / "retro_grades.parquet"

#: PR-1b `wired_from` dating.  A member's `columns:` are checked against the schema of
#: the store(s) it declares, defaulting to the candidates store — the original rule,
#: unchanged, for every member that declares nothing.  This NARROWS the check per member
#: rather than widening it globally: without it, a member wired from the graded-board
#: frame had no green state at all (claim the column -> phantom-column red; omit it ->
#: the column is unhomed and the harness refuses it as an unregistered feature).
STORE_PARQUETS = {
    "candidates": CANDIDATES_PARQUET,
    "us_board_ledger/retro_grades.parquet": LEDGER_PARQUET,
}
DEFAULT_STORE = "candidates"

PIT_STATUSES = {"pit", "forward_only", "snapshot_not_pit"}
NULL_SEMANTICS = {"unmeasured", "measured_negative", "not_applicable"}
EXPECTED_FAMILIES = [
    "F1_TECHNICAL_CONFLUENCE",
    "F2_MOMENTUM_EXTENSION",
    "F3_THEME_STRUCTURE",
    "F4_CATALYST_EVENT",
    "F5_FLOW_POSITIONING",
    "F6_MACRO_REGIME",
    "F7_QUALITY_FUNDAMENTAL",
    "F8_ATTENTION_CROWDING",
]

# Column-bearing fields on a member.  Every one of these names a candidates-store column
# and therefore enters the uniqueness pool.
COLUMN_LIST_FIELDS = ("columns", "timestamp_columns", "research_side_columns")
COLUMN_SCALAR_FIELDS = ("missingness_field", "basis_field", "reason_field")


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def store_schema() -> set[str]:
    """Real column names from the candidates store.

    Skips (never silently passes) when the parquet is not materialized — session
    worktrees are sparse by default, and a vacuously-green schema test is exactly the
    thing this file exists to prevent.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    if not CANDIDATES_PARQUET.exists():
        pytest.skip(f"candidates store not materialized at {CANDIDATES_PARQUET}")
    return set(pq.ParquetFile(CANDIDATES_PARQUET).schema_arrow.names)


@pytest.fixture(scope="module")
def store_schemas() -> dict[str, set[str]]:
    """Real column names per declared store, for `wired_from` resolution.

    Same skip law as :func:`store_schema`: a store that is not materialized is SKIPPED,
    never silently treated as containing everything.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    out: dict[str, set[str]] = {}
    for key, path in STORE_PARQUETS.items():
        if not path.exists():
            pytest.skip(f"store {key} not materialized at {path}")
        out[key] = set(pq.ParquetFile(path).schema_arrow.names)
    return out


def _wired_from(member: dict) -> list[str]:
    """The store(s) a member's columns are validated against. Default: candidates."""
    declared = member.get("wired_from")
    if not declared:
        return [DEFAULT_STORE]
    if isinstance(declared, str):
        return [declared]
    return [str(item) for item in declared]


def _members(registry: dict):
    """Yield (family_key, member_dict) for every member in the registry."""
    for fam_key, fam in registry["families"].items():
        for member in fam["members"]:
            yield fam_key, member


def _member_columns(member: dict) -> list[str]:
    """Every candidates-store column name a member claims, across all column fields."""
    out: list[str] = []
    for field in COLUMN_LIST_FIELDS:
        out.extend(member.get(field) or [])
    for field in COLUMN_SCALAR_FIELDS:
        value = member.get(field)
        if value:
            out.append(value)
    return out


def _find(registry: dict, family_key: str, member_name: str) -> dict:
    for fam_key, member in _members(registry):
        if fam_key == family_key and member["name"] == member_name:
            return member
    raise AssertionError(f"member {family_key}.{member_name} is missing from the registry")


# ---------------------------------------------------------------------------
# 1. shape, schema string, anti-authority-creep pin
# ---------------------------------------------------------------------------

class TestRegistryShape:
    def test_registry_file_exists(self):
        assert REGISTRY_PATH.is_file(), f"missing registry at {REGISTRY_PATH}"

    def test_yaml_parses_to_a_mapping(self, registry):
        assert isinstance(registry, dict)

    def test_schema_string_is_exact(self, registry):
        # Consumers dispatch on this string; a silent bump orphans every reader.
        assert registry["schema"] == "prophet_fusion.families.v1"

    def test_authority_block_is_all_false(self, registry):
        # The anti-authority-creep pin. All five, explicitly, by name.
        authority = registry["authority"]
        expected = {
            "can_rank": False,
            "can_size": False,
            "can_gate": False,
            "can_originate_signal": False,
            "can_escalate": False,
        }
        assert authority == expected, (
            "the family registry carries NO authority; flipping any of these is a "
            "doctrine amendment, not a refactor"
        )

    def test_exactly_the_eight_masterplan_families(self, registry):
        assert list(registry["families"]) == EXPECTED_FAMILIES

    def test_every_family_has_members(self, registry):
        for key, fam in registry["families"].items():
            assert fam["members"], f"{key} has no members"

    def test_member_names_are_unique_within_a_family(self, registry):
        for key, fam in registry["families"].items():
            names = [m["name"] for m in fam["members"]]
            assert len(names) == len(set(names)), f"{key} has duplicate member names"


# ---------------------------------------------------------------------------
# 2. ONE COLUMN, ONE FAMILY — the B3 law
# ---------------------------------------------------------------------------

class TestOneColumnOneFamily:
    def test_no_column_appears_in_two_families(self, registry):
        """The core law. A shared column is a free second vote at every rung C1-C5."""
        homes: dict[str, list[str]] = {}
        frame_keys = set(registry["frame_keys"])
        for fam_key, member in _members(registry):
            for column in _member_columns(member):
                if column in frame_keys:
                    continue  # join keys are shared by construction, never features
                homes.setdefault(column, []).append(f"{fam_key}.{member['name']}")

        duplicated = {c: h for c, h in homes.items() if len(h) > 1}
        assert not duplicated, f"columns homed more than once: {duplicated}"

    def test_availability_fields_that_are_store_columns_are_also_uniquely_homed(
        self, registry, store_schema
    ):
        """`options__as_of` is a real column; it must not double as someone's feature.

        Availability fields that are NOT store columns (`filing_date`, `ReportDate`,
        `available_date`) are per-store key NAMES and may legitimately repeat across
        members sourced from different stores — so they are excluded here.
        """
        frame_keys = set(registry["frame_keys"])
        homes: dict[str, list[str]] = {}
        for fam_key, member in _members(registry):
            label = f"{fam_key}.{member['name']}"
            for column in _member_columns(member):
                homes.setdefault(column, []).append(label)
            availability = member.get("availability_field")
            if availability in store_schema and availability not in frame_keys:
                homes.setdefault(availability, []).append(label)

        duplicated = {c: h for c, h in homes.items() if len(h) > 1 and c not in frame_keys}
        assert not duplicated, f"store columns homed more than once: {duplicated}"

    def test_frame_keys_strata_and_baseline_are_not_family_features(self, registry):
        """Join keys, era strata and the champion's own score are never evidence.

        §7 era hygiene: era stamps enter as STRATA (as features they are row-constant per
        night and inherit F6's cross-sectional degeneracy).  The champion's score legs are
        arena BASELINES — ingesting them as features re-fits the champion instead of
        beating it.
        """
        reserved = (
            set(registry["frame_keys"])
            | set(registry["frame_identity"])
            | set(registry["strata"]["columns"])
            | set(registry["champion_baseline"]["columns"])
        )
        for entry in registry["excluded_columns"]:
            reserved |= set(entry["columns"])

        offenders = {}
        for fam_key, member in _members(registry):
            clash = sorted(set(_member_columns(member)) & reserved)
            if clash:
                offenders[f"{fam_key}.{member['name']}"] = clash
        assert not offenders, f"reserved columns claimed as family features: {offenders}"

    def test_planned_columns_do_not_collide_with_real_or_planned_columns(
        self, registry, store_schema
    ):
        """An unwired member must not reserve a name that already means something else."""
        seen: dict[str, str] = {}
        for fam_key, member in _members(registry):
            label = f"{fam_key}.{member['name']}"
            for column in member.get("planned_columns") or []:
                assert column not in store_schema, (
                    f"{label} lists {column!r} as planned, but it already exists in the "
                    f"store — it is wired and must be declared as a real column"
                )
                assert column not in seen, (
                    f"{column!r} planned by both {seen[column]} and {label}"
                )
                seen[column] = label


# ---------------------------------------------------------------------------
# 3. per-member and per-family field law
# ---------------------------------------------------------------------------

class TestFieldLaw:
    def test_every_member_declares_a_pit_status_in_the_enum(self, registry):
        for fam_key, member in _members(registry):
            status = member.get("pit_status")
            assert status in PIT_STATUSES, (
                f"{fam_key}.{member['name']} has pit_status={status!r}, "
                f"not one of {sorted(PIT_STATUSES)}"
            )

    def test_every_member_declares_null_semantics_in_the_enum(self, registry):
        # Null is UNMEASURED, never false/zero. Which KIND of null decides whether the
        # member counts against its family's coverage floor.
        for fam_key, member in _members(registry):
            semantics = member.get("null_semantics")
            assert semantics in NULL_SEMANTICS, (
                f"{fam_key}.{member['name']} has null_semantics={semantics!r}, "
                f"not one of {sorted(NULL_SEMANTICS)}"
            )

    def test_every_member_names_a_source(self, registry):
        for fam_key, member in _members(registry):
            assert (member.get("source") or "").strip(), (
                f"{fam_key}.{member['name']} names no producer"
            )

    def test_every_member_carries_an_availability_field_key(self, registry):
        """Present on every member — `null` is a declaration, not an omission."""
        for fam_key, member in _members(registry):
            assert "availability_field" in member, (
                f"{fam_key}.{member['name']} omits availability_field; §9.1 requires the "
                f"store's OWN timestamp, or an explicit null"
            )

    def test_a_member_with_no_availability_field_is_forward_only(self, registry):
        """§9.1: a store with no availability field is forward-accrual-only, never
        lag-approximated. Derived statutory lags are FORBIDDEN as join keys."""
        for fam_key, member in _members(registry):
            if member.get("availability_field") is None:
                assert member["pit_status"] == "forward_only", (
                    f"{fam_key}.{member['name']} has no availability field but claims "
                    f"pit_status={member['pit_status']!r} — nothing can PIT-join it"
                )

    def test_coverage_floor_is_a_share_in_the_half_open_unit_interval(self, registry):
        for key, fam in registry["families"].items():
            floor = fam["coverage_floor"]
            assert isinstance(floor, (int, float)), f"{key} coverage_floor is not numeric"
            assert 0 < floor <= 1, f"{key} coverage_floor={floor} is not in (0, 1]"

    def test_family_max_staleness_is_at_least_one_session(self, registry):
        for key, fam in registry["families"].items():
            staleness = fam["max_staleness_sessions"]
            assert isinstance(staleness, int) and staleness >= 1, (
                f"{key} max_staleness_sessions={staleness!r}; a bound below one session "
                f"means the family can never be read"
            )

    def test_member_staleness_overrides_are_at_least_one_session(self, registry):
        for fam_key, member in _members(registry):
            if "max_staleness_sessions" in member:
                staleness = member["max_staleness_sessions"]
                assert isinstance(staleness, int) and staleness >= 1, (
                    f"{fam_key}.{member['name']} max_staleness_sessions={staleness!r}"
                )

    def test_every_family_has_at_least_one_coverage_probe(self, registry):
        """`coverage_floor` is unreadable without saying what is being covered."""
        for key, fam in registry["families"].items():
            probes = [m["name"] for m in fam["members"] if m.get("coverage_probe")]
            assert probes, f"{key} declares a coverage_floor but no coverage_probe member"

    def test_coverage_probes_are_unmeasured_null_members(self, registry):
        """A probe whose null means 'no event fired' would abstain a live channel."""
        for fam_key, member in _members(registry):
            if member.get("coverage_probe"):
                assert member["null_semantics"] == "unmeasured", (
                    f"{fam_key}.{member['name']} is a coverage probe but its null means "
                    f"{member['null_semantics']!r} — sparsity would read as darkness"
                )


# ---------------------------------------------------------------------------
# 4. no phantom columns — the registry may never claim what the store lacks
# ---------------------------------------------------------------------------

class TestColumnsExistInTheStore:
    def test_every_claimed_column_exists_in_a_declared_store_schema(
        self, registry, store_schemas
    ):
        """A phantom column reads as a clean null, which is indistinguishable from a
        measured null. Unwired members carry no `columns:` and are exempt by construction.

        PR-1b: the schema a column is checked against is the one the member declares in
        `wired_from` (default = the candidates store, i.e. the original rule). A
        dual-wired member satisfies the check when EACH column is real in AT LEAST ONE
        of the stores it names — never "in some store somewhere".
        """
        missing: dict[str, list[str]] = {}
        for fam_key, member in _members(registry):
            claimed = _member_columns(member)
            if not claimed:
                continue
            stores = _wired_from(member)
            unknown = [s for s in stores if s not in store_schemas]
            assert not unknown, (
                f"{fam_key}.{member['name']} declares wired_from {unknown}, which is not "
                f"in the registry's wired_from_stores block — an unknown store cannot be "
                f"checked and is never assumed to contain the column"
            )
            allowed: set[str] = set()
            for store in stores:
                allowed |= store_schemas[store]
            absent = sorted(c for c in claimed if c not in allowed)
            if absent:
                missing[f"{fam_key}.{member['name']}"] = absent
        assert not missing, f"registry claims columns no declared store has: {missing}"

    def test_wired_from_stores_are_declared_in_the_registry(self, registry):
        """Every store the test knows must be declared in the file, and vice versa —
        so the two cannot drift apart silently."""
        declared = set(registry["wired_from_stores"])
        assert declared == set(STORE_PARQUETS), (
            f"registry declares stores {sorted(declared)} but this test resolves "
            f"{sorted(STORE_PARQUETS)}"
        )
        defaults = [k for k, v in registry["wired_from_stores"].items()
                    if v.get("default")]
        assert defaults == [DEFAULT_STORE], (
            f"exactly one store may be the default; found {defaults}"
        )

    def test_ledger_wired_members_declare_the_ledger_availability_stamp(self, registry):
        """§9.1: a PIT join uses the store's OWN availability field.

        The graded-board ledger's is `as_of` — the frozen board's publication stamp.
        A ledger-wired member must name it, either as its `availability_field` (when the
        ledger is its only wiring) or as `ledger_availability_field` (when it is
        dual-wired and its primary availability field belongs to the other store).
        """
        ledger = "us_board_ledger/retro_grades.parquet"
        stamp = registry["wired_from_stores"][ledger]["availability_field"]
        for fam_key, member in _members(registry):
            if ledger not in _wired_from(member):
                continue
            fields = {member.get("availability_field"),
                      member.get("ledger_availability_field")}
            assert stamp in fields, (
                f"{fam_key}.{member['name']} is wired from the ledger but names no "
                f"{stamp!r} availability stamp — a PIT join with no availability field "
                f"is a lag approximation in disguise (§9.1)"
            )

    def test_unwired_members_claim_no_real_columns(self, registry):
        for fam_key, member in _members(registry):
            if member.get("wired", True) is False:
                assert not member.get("columns"), (
                    f"{fam_key}.{member['name']} is wired:false but lists columns"
                )
                assert member.get("planned_columns"), (
                    f"{fam_key}.{member['name']} is wired:false and plans nothing — an "
                    f"unwired member with no planned columns records no intent"
                )

    def test_wired_members_reach_the_store_somehow(self, registry):
        """A wired member must claim a column or an explicit absence flag.

        `insider_panel` is the shape this allows on purpose: the dim is wired and its
        panel is starved, so the store ships only `insider__absent` / `insider__reason`
        and no scalar. That is a real wired-but-dark member, not a typo.
        """
        for fam_key, member in _members(registry):
            if member.get("wired", True) is not False:
                assert _member_columns(member), (
                    f"{fam_key}.{member['name']} is wired but names no store column"
                )

    def test_registry_still_accounts_for_the_pinned_store_schema(
        self, registry, store_schema
    ):
        """Orphan guard: the count of accounted columns may grow, never shrink.

        The store self-heals forward by schema union, so NEW columns must not red this
        file (§13 adds telemetry columns within days). What must red it is someone
        deleting a member and orphaning the columns it homed.
        """
        pin = registry["store_schema_pin"]
        accounted = set(registry["frame_keys"]) | set(registry["frame_identity"])
        accounted |= set(registry["strata"]["columns"])
        accounted |= set(registry["champion_baseline"]["columns"])
        for entry in registry["excluded_columns"]:
            accounted |= set(entry["columns"])
        for _fam_key, member in _members(registry):
            accounted |= set(_member_columns(member))
            availability = member.get("availability_field")
            if availability in store_schema:
                accounted.add(availability)

        accounted &= store_schema
        assert len(accounted) >= pin["n_columns"], (
            f"registry accounts for {len(accounted)} store columns, below the pinned "
            f"{pin['n_columns']} as of {pin['stamp']} — a member was deleted and its "
            f"columns are now unhomed"
        )


# ---------------------------------------------------------------------------
# 5. PIT integrity — the flags a backtest harness reads before it may join
# ---------------------------------------------------------------------------

class TestPitIntegrityFlags:
    def test_short_interest_is_marked_snapshot_not_pit(self, registry):
        """§4.2 flag 2: `context_api._short_int_dim` IGNORES the query date and returns
        the CURRENT snapshot; the history file is never read. Any historical use is
        leakage BY CONSTRUCTION."""
        member = _find(registry, "F5_FLOW_POSITIONING", "short_interest")
        assert member["pit_status"] == "snapshot_not_pit"
        assert all(c.startswith("short_int__") for c in member["columns"])

    def test_forensics_is_marked_snapshot_not_pit(self, registry):
        """§4.1: the store REFUSES dates before its `generated_at` — backtestable never."""
        member = _find(registry, "F7_QUALITY_FUNDAMENTAL", "forensics_scalars")
        assert member["pit_status"] == "snapshot_not_pit"
        assert all(c.startswith("forensics__") for c in member["columns"])

    def test_every_snapshot_not_pit_column_is_prefixed_short_int_or_forensics(self, registry):
        """The converse direction: exactly these two dims, so a harness that refuses on
        prefix and a harness that refuses on `pit_status` agree."""
        for fam_key, member in _members(registry):
            if member["pit_status"] != "snapshot_not_pit":
                continue
            for column in _member_columns(member):
                assert column.startswith(("short_int__", "forensics__")), (
                    f"{fam_key}.{member['name']} marks {column!r} snapshot_not_pit; if a "
                    f"third snapshot-only dim has appeared, widen §4.2 and this test "
                    f"together"
                )

    def test_insider_is_pit_but_flagged_serving_dead(self, registry):
        """§4.2 flag 3: PIT-correct by construction (`filing_date`), but the panel
        collector stopped at 2026q1 — `insider__absent` reads TRUE on every board row."""
        member = _find(registry, "F5_FLOW_POSITIONING", "insider_panel")
        assert member["pit_status"] == "pit"
        assert member["serving_dead"] is True
        assert member["availability_field"] == "filing_date"
        assert member["missingness_field"] == "insider__absent"

    def test_attention_and_factor_are_forward_only_and_host_only(self, registry):
        """§4.2 flag 4: a CI-run or clone-run study silently sees zero coverage, so these
        must never masquerade as a measured null."""
        for family_key, member_name in (
            ("F8_ATTENTION_CROWDING", "attention"),
            ("F6_MACRO_REGIME", "factor_dispersion_state"),
        ):
            member = _find(registry, family_key, member_name)
            assert member["pit_status"] == "forward_only", member_name
            assert member["host_only"] is True, member_name

    def test_hub_members_are_forward_only(self, registry):
        """Hub state is snapshot-only with no history trail (§13.3)."""
        member = _find(registry, "F3_THEME_STRUCTURE", "hub_theme_leg")
        assert member["pit_status"] == "forward_only"
        assert member.get("wired", True) is False

    def test_options_is_pit_and_carries_the_era_break(self, registry):
        """The 2026-08-07 chain-store boundary; §7 forbids pooled inference across it
        without disclosure."""
        member = _find(registry, "F5_FLOW_POSITIONING", "options_state")
        assert member["pit_status"] == "pit"
        assert str(member["era_break"]) == "2026-08-07"

    def test_congress_and_13f_are_pit_but_unwired(self, registry):
        """RICH raw with correct PIT pairs, ZERO consumers — the largest unwired evidence
        mass in the estate (§4.2 flag 9). Join on disclosure availability, never on
        transaction date and never on a derived statutory lag (§9.1)."""
        congress = _find(registry, "F5_FLOW_POSITIONING", "congress_trades")
        assert congress["pit_status"] == "pit"
        assert congress["wired"] is False
        assert congress["availability_field"] == "ReportDate"

        thirteen_f = _find(registry, "F5_FLOW_POSITIONING", "smart_money_13f")
        assert thirteen_f["pit_status"] == "pit"
        assert thirteen_f["wired"] is False
        assert thirteen_f["availability_field"] == "available_date"

    def test_availability_fields_come_from_the_declared_vocabulary(self, registry, store_schema):
        """§9.1 names the lawful availability anchors. Anything else is a derived lag in
        disguise."""
        # `as_of` added in PR-1b: it is the graded-board ledger's OWN publication stamp
        # (the frozen board payload's date), which is precisely what §9.1 asks a PIT
        # join to key on. It is NOT a derived lag — the row was published that night.
        allowed = {"filing_date", "available_date", "ReportDate", "fetch_date",
                   "as_of", None}
        for fam_key, member in _members(registry):
            availability = member.get("availability_field")
            assert availability in allowed or availability in store_schema, (
                f"{fam_key}.{member['name']} joins on {availability!r}, which is neither a "
                f"candidates-store column nor a declared upstream availability key"
            )


# ---------------------------------------------------------------------------
# 6. F6 is row-constant — router only, never a cross-sectional ranker
# ---------------------------------------------------------------------------

class TestRowConstantMarker:
    def test_every_f6_member_is_marked_not_cross_sectional(self, registry):
        """§5.1 F6: row-constant per night, cross-sectionally DEGENERATE BY CONSTRUCTION.
        Lawful only as router / interaction axes (§10.2)."""
        for member in registry["families"]["F6_MACRO_REGIME"]["members"]:
            assert member.get("cross_sectional") is False, (
                f"F6 member {member['name']} is not marked cross_sectional: false — one "
                f"value for every name cannot rank names"
            )

    def test_the_row_constant_marker_is_exclusive_to_f6(self, registry):
        for fam_key, member in _members(registry):
            if fam_key == "F6_MACRO_REGIME":
                continue
            assert "cross_sectional" not in member or member["cross_sectional"] is True, (
                f"{fam_key}.{member['name']} claims row-constancy outside F6; a "
                f"row-constant member in a ranking family is a silent no-op"
            )


# ---------------------------------------------------------------------------
# 7. §5.2 composite decomposition — the composites the harness must refuse
# ---------------------------------------------------------------------------

class TestForbiddenComposites:
    def test_forbidden_composites_is_non_empty(self, registry):
        assert registry["forbidden_composites"]

    def test_every_forbidden_composite_declares_decompose_to_routes(self, registry):
        family_keys = set(registry["families"])
        for entry in registry["forbidden_composites"]:
            name = entry["composite"]
            routes = entry.get("decompose_to")
            assert routes, f"{name} is forbidden but names no decomposition"
            for route in routes:
                assert route.get("input"), f"{name} has a route with no input"
                assert route["family"] in family_keys, (
                    f"{name} routes {route['input']!r} to unknown family {route['family']!r}"
                )

    def test_every_forbidden_composite_states_its_reason(self, registry):
        for entry in registry["forbidden_composites"]:
            assert (entry.get("reason") or "").strip(), (
                f"{entry['composite']} is forbidden with no rationale — a fence nobody can "
                f"audit is a fence nobody will keep"
            )

    def test_the_named_composites_are_all_present(self, registry):
        """The §5.2 list, by name. A generic 'non-empty' test passes after a deletion."""
        named = {e["composite"] for e in registry["forbidden_composites"]}
        for required in (
            "opportunity_score",       # Intelligence Hub
            "composite_conviction",    # Intelligence Hub
            "conviction",              # engine/stock_score.py
            "composite_z",             # engine/stock_score.py
            "setup",                   # engine/setups.py
            "potential_score",         # engine/name_score.py, the G2 baseline
        ):
            assert required in named, f"{required} is no longer refused as a raw feature"

    def test_no_forbidden_composite_is_also_a_registered_column(self, registry):
        """A composite that leaks in as a member column is a composite that was not
        refused."""
        forbidden = {e["composite"] for e in registry["forbidden_composites"]}
        for fam_key, member in _members(registry):
            claimed = set(_member_columns(member)) | set(member.get("planned_columns") or [])
            clash = sorted(claimed & forbidden)
            assert not clash, f"{fam_key}.{member['name']} ingests forbidden composite(s) {clash}"

    def test_the_momentum_leg_route_carries_the_dedup_constraint(self, registry):
        """rho = 0.984 against residual alpha: the leg IS alpha under a new name. Routing
        it to F2 without the dedup is the double-count the whole registry exists to stop."""
        for entry in registry["forbidden_composites"]:
            for route in entry["decompose_to"]:
                if route["input"] == "momentum_leg":
                    assert "0.984" in (route.get("constraint") or ""), (
                        f"{entry['composite']}'s momentum leg routes to F2 with no dedup "
                        f"constraint"
                    )


# ---------------------------------------------------------------------------
# 8. the single-home rulings, pinned BY NAME
# ---------------------------------------------------------------------------

class TestSingleHomeRulings:
    """§5.1's binding amendments. Generic uniqueness passes after someone moves `ext_z`
    to F8; these do not."""

    def _families_owning(self, registry, predicate) -> set[str]:
        return {
            fam_key
            for fam_key, member in _members(registry)
            for column in _member_columns(member)
            if predicate(column)
        }

    def test_ext_z_lives_only_in_f2(self, registry):
        owners = self._families_owning(registry, lambda c: c == "ext_z")
        assert owners == {"F2_MOMENTUM_EXTENSION"}, (
            f"ext_z is homed in {owners}; §5.1 amendment: F2 ONLY — F8's crowding read of "
            f"extension enters as an F2-orthogonalized derivative, never a second membership"
        )

    def test_relay_columns_live_only_in_f3(self, registry):
        owners = self._families_owning(registry, lambda c: c.startswith("relay_"))
        assert owners == {"F3_THEME_STRUCTURE"}, (
            f"relay columns are homed in {owners}; §5.1 amendment: F3 ONLY — relay's "
            f"price-derivation is provenance, not membership"
        )

    def test_theme_heat_rank_lives_only_in_f3(self, registry):
        owners = self._families_owning(registry, lambda c: c == "theme_heat_rank")
        assert owners == {"F3_THEME_STRUCTURE"}, (
            f"theme_heat_rank is homed in {owners}; §5.1 amendment: F3 ONLY — the S-C "
            f"crowding hypothesis on it is a §10.7 registered interaction, not an F8 member"
        )

    def test_turnover_columns_live_only_in_f5(self, registry):
        """RESOLVED IN THE REGISTRY: §5.1 listed 'turnover percentile' under F5 and
        'turnover tail' under F8 — a double home the amendments did not adjudicate. Ruled
        by the amendments' own rule: single home in F5, F8's tail read enters as an
        F5-orthogonalized derivative."""
        owners = self._families_owning(
            registry, lambda c: c.startswith("turnover_") or c == "mdv20_usd"
        )
        assert owners == {"F5_FLOW_POSITIONING"}, (
            f"turnover/liquidity columns are homed in {owners}; ruling: F5 ONLY"
        )

    def test_each_ruling_is_recorded_on_the_member_it_binds(self, registry):
        """The ruling text travels with the data, so a reader of the YAML cannot miss it."""
        for family_key, member_name in (
            ("F2_MOMENTUM_EXTENSION", "extension_z"),
            ("F3_THEME_STRUCTURE", "theme_heat"),
            ("F3_THEME_STRUCTURE", "relay_window"),
            ("F5_FLOW_POSITIONING", "turnover_liquidity"),
        ):
            member = _find(registry, family_key, member_name)
            assert (member.get("single_home_ruling") or "").strip(), (
                f"{family_key}.{member_name} carries no single_home_ruling text"
            )


# ---------------------------------------------------------------------------
# 9. semantics block — the null-vs-zero law, stated once and machine-readable
# ---------------------------------------------------------------------------

class TestSemanticsBlock:
    def test_semantics_block_states_the_three_laws(self, registry):
        semantics = registry["semantics"]
        for key in (
            "null_is_not_zero",
            "missingness_is_first_class",
            "abstention_is_not_a_zero_vote",
        ):
            assert (semantics.get(key) or "").strip(), f"semantics.{key} is empty"

    def test_null_semantics_enum_matches_the_values_members_use(self, registry):
        declared = set(registry["semantics"]["null_semantics_enum"])
        assert declared == NULL_SEMANTICS
        used = {m["null_semantics"] for _f, m in _members(registry)}
        assert used <= declared, f"members use undeclared null semantics: {used - declared}"

    def test_every_declared_null_semantic_has_a_written_meaning(self, registry):
        meanings = registry["semantics"]["null_semantics_meaning"]
        for value in registry["semantics"]["null_semantics_enum"]:
            assert (meanings.get(value) or "").strip(), f"no meaning written for {value!r}"

    def test_coverage_and_staleness_are_defined_not_merely_declared(self, registry):
        semantics = registry["semantics"]
        assert (semantics.get("coverage_definition") or "").strip()
        assert (semantics.get("staleness_definition") or "").strip()

    def test_unregistered_columns_are_refused_not_guessed(self, registry):
        assert registry["semantics"]["unregistered_column_policy"] == "refuse"


# ---------------------------------------------------------------------------
# 10. redundancy edges — the priors an "N families agree" claim is audited against
# ---------------------------------------------------------------------------

class TestKnownRedundancyEdges:
    def test_edges_are_non_empty_and_each_cites_a_source(self, registry):
        edges = registry["known_redundancy_edges"]
        assert edges
        for edge in edges:
            assert len(edge["pair"]) == 2, f"edge {edge} is not a pair"
            assert (edge.get("source") or "").strip(), f"edge {edge['pair']} cites no source"
            assert (edge.get("relation") or "").strip()
            assert (edge.get("consequence") or "").strip(), (
                f"edge {edge['pair']} states no consequence — a measured overlap that "
                f"changes nothing is trivia"
            )

    def test_the_documented_pairs_are_all_present(self, registry):
        """The four §5.1/§5.2 receipts, by content. These are the priors PR-2 re-measures."""
        blob = yaml.safe_dump(registry["known_redundancy_edges"])
        assert "0.984" in blob, "the alpha <-> composite momentum leg edge is gone"
        assert "+0.37" in blob, "the total_return <-> alpha edge is gone"
        assert "blowoff" in blob, "the blowoff <-> ext_z price-derivation edge is gone"
        assert "hub_theme_leg" in blob, "the hub-feeders <-> F1-F4 overlap edge is gone"


class TestLabelOnlyStores:
    """The outcome stores are labels, never features (masterplan §7).

    This class is the mechanism the zero-authority fence's allowlist entry for
    scripts/prophet_fusion_labels.py cites: the registry DECLARES the grades
    stores label-only, and this suite reds if any family member ever claims one
    of their columns as evidence.  Deleting the declaration reds here too, so
    the fence's rationale cannot silently rot.
    """

    def test_the_declaration_exists_and_names_both_outcome_stores(self, registry):
        stores = registry.get("label_only_stores")
        assert stores, "label_only_stores must exist — the fence allowlist cites it"
        paths = {entry["store"] for entry in stores}
        assert "data/us_prophet_rank/grades/" in paths
        assert "data/us_board_ledger/retro_grades.parquet" in paths
        for entry in stores:
            assert entry.get("label_only_columns"), (
                f"{entry['store']} declares no label_only_columns — an empty "
                "declaration guards nothing")

    def test_no_family_member_claims_an_outcome_column_as_evidence(self, registry):
        label_cols = {
            col
            for entry in registry.get("label_only_stores", ())
            for col in entry.get("label_only_columns", ())
        }
        assert label_cols
        offenders = []
        for fam_key, fam in registry["families"].items():
            for member in fam.get("members", ()):
                for field in ("columns", "planned_columns"):
                    for col in member.get(field) or ():
                        if col in label_cols:
                            offenders.append(f"{fam_key}.{member['name']}.{field}:{col}")
        assert not offenders, (
            "outcome columns are LABELS, never features — leakage by construction. "
            f"Offenders: {offenders}")
