"""Dataset contracts + the static lineage DAG (Data OS §D5/§D9) — ``lib/dataos/registry.py``.

Two halves, both load-bearing:

* the SYNTHETIC half proves each violation class is actually detected (a validator
  that returns ``[]`` for everything passes a "the real registry is clean" test
  perfectly);
* the REAL half proves the committed ``config/dataset_registry.yml`` is clean and
  says only true things — a registry that lists a dataset which does not exist is
  worse than no registry, because the next session builds against it.

No ``data/`` read: the registry is a config file, and the stores it DESCRIBES are
never opened here.

Run: .venv/bin/python -m pytest tests/test_dataos_registry.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.dataos.price import is_ambiguous
from lib.dataos.registry import (
    REGISTRY_PATH,
    ConflictPolicy,
    DatasetContract,
    DatasetStatus,
    Layer,
    Registry,
    RegistryError,
    load_registry,
    validate_registry,
)
from lib.dataos.temporal import TemporalProfile

ROOT = Path(__file__).resolve().parent.parent


def contract(dataset_id: str, **overrides) -> DatasetContract:
    """A minimal VALID contract, so a test can introduce exactly one defect."""
    base = {
        "dataset_id": dataset_id,
        "layer": "L1",
        "status": "PRODUCED",
        "owner": "macro-dashboard",
        "producer": "collectors/example.py",
        "storage": "data/example/{ticker}.parquet",
        "format": "parquet",
        "grain": ["ticker", "date"],
        "temporal_profile": "BARS",
        "version": "1.0.0",
    }
    base.update(overrides)
    return DatasetContract.from_mapping(base)


# ── the real, committed registry ─────────────────────────────────────────────
def test_the_registry_path_is_resolved_against_the_repo_not_the_cwd() -> None:
    """The nightly, the CI packs and a developer shell all run from different
    directories; a cwd-relative default is a config file that silently is not there."""
    assert REGISTRY_PATH == ROOT / "config" / "dataset_registry.yml"
    assert REGISTRY_PATH.is_file()


def test_the_committed_registry_loads_and_has_no_violations() -> None:
    violations = validate_registry(load_registry())
    assert violations == [], "\n".join(violations)


def test_the_committed_registry_carries_the_nine_seeded_datasets() -> None:
    """Nine, not seven: V4-D2B1 (2026-08-19) added ``reference.issuer_master`` and
    ``reference.issuer_migrations`` — same producer (``scripts/build_security_master.py``),
    same reference plane as ``reference.security_master``."""
    registry = load_registry()
    assert set(registry.ids()) == {
        "equity.bars.daily.stocks",
        "equity.bars.daily.yahoo",
        "equity.bars.daily.massive",
        "macro.fred.observations",
        "macro.fred.vintages",
        "reference.security_master",
        "reference.vendor_aliases",
        "reference.issuer_master",
        "reference.issuer_migrations",
    }
    assert len(registry) == 9


def test_nothing_unproduced_is_marked_produced() -> None:
    """The honesty rule: a row claiming a store that does not exist is a trap.

    The two identity rows were PROPOSED for exactly one day (DOS-1.0) and were promoted
    by DOS-1.1, which shipped the producer and committed the artifacts.  A promotion is
    only honest if the row names a REAL producer and a REAL path, so this pins the
    strings; the on-disk half of gate G1 — the path exists, the producer file exists —
    is asserted by ``tests/test_dataos_security_master.py``, which runs in a lane that
    has ``data/``.  It deliberately does NOT live here: every suite in the
    ``dataos-foundation`` job is a pure unit test that never opens ``data/``, so it
    behaves identically on a full checkout and in that thin lane.
    """
    registry = load_registry()
    for dataset_id in ("reference.security_master", "reference.vendor_aliases"):
        contract = registry.get(dataset_id)
        assert contract.status is DatasetStatus.PRODUCED
        assert contract.producer == "scripts/build_security_master.py"
        assert contract.storage.startswith("data/reference/")
        assert contract.storage.endswith(".parquet")
    for dataset_id in ("equity.bars.daily.stocks", "macro.fred.vintages"):
        assert registry.get(dataset_id).status is DatasetStatus.PRODUCED


def test_every_enum_valued_field_in_the_real_registry_coerced_to_an_enum() -> None:
    for c in load_registry().all():
        assert isinstance(c.layer, Layer), c.dataset_id
        assert isinstance(c.status, DatasetStatus), c.dataset_id
        assert isinstance(c.temporal_profile, TemporalProfile), c.dataset_id
        assert isinstance(c.conflict_policy, ConflictPolicy), c.dataset_id


def test_the_measured_price_bases_reach_the_registry_schema() -> None:
    """§D4's measurement is only useful if a reader can find it without grepping."""
    registry = load_registry()
    assert registry.get("equity.bars.daily.stocks").schema["close"]["basis"] == "tradj"
    assert registry.get("equity.bars.daily.yahoo").schema["close"]["basis"] == "tradj"
    assert registry.get("equity.bars.daily.yahoo").schema["close_price"]["basis"] == "sadj"
    assert registry.get("equity.bars.daily.massive").schema["close"]["basis"] == "raw"


def test_every_ambiguous_price_column_declares_the_canonical_name_it_renames_to() -> None:
    """The V1 migration in one invariant: 132 files keep reading `close`, and the
    basis stops being a guess.

    Scoped to the PRICE stores on purpose — §D4's law is the price naming law.
    ``macro.fred.observations`` also stores a column called ``value``, which is
    ambiguous in the unit sense but has no adjustment basis to declare, and demanding
    a `basis:` there would be a fabricated fact.
    """
    registry = load_registry()
    price_datasets = [c for c in registry.all() if c.dataset_id.startswith("equity.bars.")]
    assert price_datasets, "the price stores are what this invariant is about"
    checked = 0
    for c in price_datasets:
        for column, spec in c.schema.items():
            if not is_ambiguous(column):
                continue
            assert spec.get("basis"), f"{c.dataset_id}:{column} has no measured basis"
            assert spec.get("renames_to"), f"{c.dataset_id}:{column} has no canonical name"
            assert spec["renames_to"] == f"{column.split('_')[0]}_{spec['basis']}"
            checked += 1
    assert checked == 4, "the four measured NVDA columns of §D4"


def test_the_real_dag_edges_and_reverse_edges_agree() -> None:
    """The one real edge in the seed: the alias table joins on the security master."""
    registry = load_registry()
    assert ("reference.security_master", "reference.vendor_aliases") in registry.dag()
    assert registry.inputs_of("reference.vendor_aliases") == ("reference.security_master",)
    # V4-D2B1 (2026-08-19) added two more consumers of the same producer's other
    # outputs — reference.issuer_master and reference.issuer_migrations both declare
    # inputs: [reference.security_master] alongside reference.vendor_aliases.
    assert registry.consumers_of("reference.security_master") == (
        "reference.vendor_aliases", "reference.issuer_master", "reference.issuer_migrations",
    )
    assert registry.consumers_of("equity.bars.daily.stocks") == ()


def test_the_two_fred_stores_are_siblings_and_declare_no_edge_between_them() -> None:
    """A FALSE lineage edge is worse than a missing one, and this one shipped.

    ``macro.fred.vintages`` used to declare ``inputs: [macro.fred.observations]``. It
    does not read it: ``collectors/fred.py::_vintage_series`` takes its series list
    from ``config.yml`` / ``DEFAULT_VINTAGE_SERIES``, and ``_fetch_vintage_one``
    calls the ALFRED realtime endpoint directly. The two are L1 SIBLINGS off one
    vendor API with no producer/consumer relationship at all.

    What the false edge would have cost: a lineage query asks
    ``consumers_of('macro.fred.observations')``, gets the vintage store, and an
    operator chasing a bad row in ``data/fred/CPIAUCSL.parquet`` concludes the
    point-in-time store is contaminated — it never touched that file. The reverse is
    worse: a rebuild plan orders observations before vintages and reports the vintage
    refresh as "covered" by a backfill that did nothing for it.
    """
    registry = load_registry()
    assert registry.inputs_of("macro.fred.vintages") == ()
    assert registry.consumers_of("macro.fred.observations") == ()
    assert ("macro.fred.observations", "macro.fred.vintages") not in registry.dag()


def test_no_contract_declares_a_code_path_where_a_dataset_id_belongs() -> None:
    """``inputs`` is the DAG; a function path in it is not an edge, it is a lie.

    ``validate_registry`` already rejects an unknown ``inputs`` reference, so the
    only way a ``collectors/fred.py::as_of_series``-shaped value survives is in a
    field that is NOT the graph — which is why code-level readers are declared under
    ``code_consumers`` and never under ``inputs``/``consumers``.
    """
    for c in load_registry().all():
        for src in c.inputs:
            assert "::" not in src and "/" not in src, f"{c.dataset_id}: inputs {src!r}"


def test_code_consumers_and_the_graph_reverse_edge_are_two_different_notions() -> None:
    """One field, two meanings, is how a lineage answer becomes untrustworthy.

    ``consumers_of()`` returns DATASET_IDS derived from the ``inputs`` graph — a
    fact, not a hand-maintained list. The functions that READ a store are a different
    thing entirely and live in ``code_consumers``. They were both called "consumers"
    once, and a caller could not tell which answer it was holding.
    """
    registry = load_registry()
    vintages = registry.get("macro.fred.vintages")
    assert vintages.code_consumers == (
        "collectors/fred.py::as_of_series",
        "collectors/fred.py::initial_release",
    )
    assert registry.consumers_of("macro.fred.vintages") == ()


def test_get_returns_none_for_an_unknown_id_rather_than_raising() -> None:
    assert load_registry().get("no.such.dataset") is None


# ── loader failure modes ─────────────────────────────────────────────────────
def test_a_missing_registry_file_raises_with_the_path(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yml")


def test_a_registry_without_a_datasets_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "registry.yml"
    path.write_text("schema: dataset_registry.v1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="no `datasets:` key"):
        load_registry(path)


def test_a_datasets_key_that_is_not_a_list_raises(tmp_path: Path) -> None:
    path = tmp_path / "registry.yml"
    path.write_text("datasets:\n  a: 1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="must be a list"):
        load_registry(path)


def test_a_round_trip_through_yaml_preserves_the_contract(tmp_path: Path) -> None:
    path = tmp_path / "registry.yml"
    path.write_text(
        "datasets:\n"
        "  - dataset_id: a.b.c\n"
        "    layer: L2\n"
        "    status: PROPOSED\n"
        "    owner: me\n"
        "    producer: none\n"
        "    storage: data/x\n"
        "    format: parquet\n"
        "    grain: [id]\n"
        "    temporal_profile: SNAPSHOT_SERIES\n"
        "    version: \"0.1.0\"\n"
        "    identity: {id_column: security_id, id_type: SEC}\n"
        "    freshness_sla_hours: 26\n"
        "    schema:\n"
        "      close_tradj: {dtype: float64}\n",
        encoding="utf-8",
    )
    c = load_registry(path).get("a.b.c")
    assert c.layer is Layer.L2_CANONICAL
    assert c.temporal_profile is TemporalProfile.SNAPSHOT_SERIES
    assert c.id_column == "security_id" and c.id_type == "SEC"
    assert c.freshness_sla_hours == 26.0
    assert c.grain == ("id",)
    assert validate_registry(load_registry(path)) == []


# ── each violation class, proved detectable ──────────────────────────────────
def test_a_cyclic_input_graph_is_reported_as_a_cycle() -> None:
    """The synthetic registry the spec asks for: A -> B -> C -> A."""
    cyclic = Registry([
        contract("a", inputs=["c"]),
        contract("b", inputs=["a"]),
        contract("c", inputs=["b"]),
    ])
    violations = validate_registry(cyclic)
    cycles = [v for v in violations if v.startswith("cycle in dependency DAG")]
    assert len(cycles) == 1, violations
    assert {"a", "b", "c"} <= set(cycles[0].replace("->", " ").split())


def test_a_self_edge_is_a_cycle_too() -> None:
    violations = validate_registry(Registry([contract("a", inputs=["a"])]))
    assert any(v.startswith("cycle in dependency DAG") for v in violations)


def test_an_acyclic_diamond_is_not_reported_as_a_cycle() -> None:
    """A shared upstream is normal lineage, not a loop — the guard must not cry wolf."""
    diamond = Registry([
        contract("src"),
        contract("left", inputs=["src"]),
        contract("right", inputs=["src"]),
        contract("sink", inputs=["left", "right"]),
    ])
    assert validate_registry(diamond) == []


def test_an_unknown_input_dataset_id_is_reported() -> None:
    violations = validate_registry(Registry([contract("a", inputs=["ghost.dataset"])]))
    assert any("ghost.dataset" in v and "not a dataset_id" in v for v in violations)


def test_a_duplicate_dataset_id_is_reported_even_though_the_index_hides_it() -> None:
    violations = validate_registry(Registry([contract("a"), contract("a")]))
    assert any(v.startswith("duplicate dataset_id") for v in violations)


@pytest.mark.parametrize("missing", ["owner", "producer", "storage", "format", "version"])
def test_a_missing_required_field_is_reported_by_name(missing: str) -> None:
    violations = validate_registry(Registry([contract("a", **{missing: ""})]))
    assert any(f"missing required field {missing!r}" in v for v in violations)


def test_an_empty_grain_is_a_missing_required_field() -> None:
    violations = validate_registry(Registry([contract("a", grain=[])]))
    assert any("missing required field 'grain'" in v for v in violations)


def test_a_temporal_profile_outside_the_enum_is_reported_not_raised() -> None:
    """Reported rather than exploding at load: one bad row must not take the whole
    catalog down with it."""
    c = contract("a", temporal_profile="WHENEVER")
    assert c.temporal_profile == "WHENEVER"
    violations = validate_registry(Registry([c]))
    assert any("temporal_profile" in v and "WHENEVER" in v for v in violations)


@pytest.mark.parametrize(
    "field, value, needle",
    [("layer", "L9", "layer"),
     ("status", "MAYBE", "status"),
     ("conflict_policy", "WHATEVER", "conflict_policy")],
)
def test_other_closed_vocabularies_are_reported_too(field, value, needle) -> None:
    violations = validate_registry(Registry([contract("a", **{field: value})]))
    assert any(needle in v and value in v for v in violations)


def test_an_ambiguous_price_column_on_an_l2_dataset_is_reported() -> None:
    """§D4's naming law binds at the CANONICAL layer."""
    violations = validate_registry(Registry([
        contract("a", layer="L2", schema={"close": {"dtype": "float64"}}),
    ]))
    assert any("ambiguous price name" in v for v in violations)


def test_the_same_ambiguous_column_is_tolerated_on_an_l1_vendor_shaped_store() -> None:
    """L1 is vendor-shaped by definition — ``data/yahoo`` really does store `close`.
    Flagging it there would make the guard unfixable and therefore ignored."""
    assert validate_registry(Registry([
        contract("a", layer="L1", schema={"close": {"dtype": "float64"}}),
    ])) == []


def test_a_canonical_column_on_an_l2_dataset_is_clean() -> None:
    assert validate_registry(Registry([
        contract("a", layer="L2", schema={"close_tradj": {"dtype": "float64"}}),
    ])) == []


def test_validate_registry_returns_and_never_exits() -> None:
    """Severity is the caller's decision; a validator that calls sys.exit is unusable
    to both a test and a catalog builder."""
    out = validate_registry(Registry([contract("a", owner="")]))
    assert isinstance(out, list) and all(isinstance(v, str) for v in out)
