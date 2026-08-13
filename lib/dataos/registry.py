"""Dataset contracts + the static lineage DAG (Data OS §D5, §D9).

WHY THIS FILE EXISTS.  The house already owns the right contract primitive:
``collectors/base.py::ColumnContract``, born from china_connect/northbound hiding the
death of ``net``/``buy``/``sell`` for ~2 years behind a still-live ``turnover``
column — frame-grain freshness could not see it, so the contract moved down to the
COLUMN.  That primitive is per-adapter and per-column.  What is missing is the tier
above it: nothing anywhere declares what a DATASET is, who produces it, which clocks
it carries, which basis its price columns are on, or what reads it.  So every new
session re-derives all of that by grepping, and every consumer's assumption lives
only in the consumer.

This module is that tier, and it deliberately introduces NO new store (§D9).
Lineage is three pieces, two of which already exist:

1. every dataset has a stable ``dataset_id`` declaring ``inputs: [dataset_id]``,
   giving a static dependency DAG with no runtime instrumentation
   (:meth:`Registry.dag`);
2. every produced artifact writes a receipt — already the house idiom
   (``contracts/*_receipt.schema.json``);
3. a lineage query is "walk the DAG, read the receipts".

STATUS IS PART OF THE CONTRACT.  A registry that lists a dataset which does not exist
is worse than no registry: the next session builds against it.  Anything not yet
produced is ``status: PROPOSED`` and says so in its own row.

:func:`validate_registry` RETURNS violations and neither prints nor exits.  Severity
is the caller's decision — a test may fail on any violation while a catalog builder
may want to render them — and a validator that calls ``sys.exit`` cannot be used by
either.

STDLIB ONLY AT IMPORT TIME.  ``yaml`` is imported inside :func:`load_registry`, so a
lane that only needs the vocabulary (the enums, :class:`DatasetContract`) pays
nothing for a dependency it will not use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lib.dataos import price
from lib.dataos.temporal import TemporalProfile

__all__ = [
    "RegistryError",
    "Layer",
    "DatasetStatus",
    "ConflictPolicy",
    "DatasetContract",
    "Registry",
    "REGISTRY_PATH",
    "load_registry",
    "validate_registry",
]

#: Resolved against THIS FILE, never the cwd — the nightly, the CI packs and a
#: developer shell all run from different directories, and a cwd-relative default is
#: a config file that silently is not there.
REGISTRY_PATH: Path = Path(__file__).resolve().parents[2] / "config" / "dataset_registry.yml"


class RegistryError(ValueError):
    """The registry file itself is unreadable or structurally wrong."""


class Layer(Enum):
    """The five layers of §D1.  ``L2`` is where the price-basis law lives.

    Law: **derived data must never masquerade as source.**  In-repo precedent that
    this is a real, expensive failure — ``DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT``
    stop-shipped an entire CN limit-alpha program because a vendor-*adjusted* price
    was used where the exchange's *raw print* was the only lawful input.
    """

    L0_SOURCE = "L0"
    L1_NORMALIZED = "L1"
    L2_CANONICAL = "L2"
    L3_DERIVED = "L3"
    L4_INTELLIGENCE = "L4"


class DatasetStatus(Enum):
    """Does this dataset EXIST?  A registry that lies about this is a trap."""

    PRODUCED = "PRODUCED"      # the store exists and a producer writes it today
    PROPOSED = "PROPOSED"      # declared here, not yet produced by anything
    RETIRED = "RETIRED"        # was produced; kept so its consumers stay explainable


class ConflictPolicy(Enum):
    """Multi-vendor conflict resolution (§D7).

    ``DISCREPANT_MAJOR`` on a canonical field quarantines the value, serves last-good
    and opens an incident — it never silently picks whichever API answered last.
    """

    PRIMARY_ONLY = "PRIMARY_ONLY"
    FALLBACK = "FALLBACK"
    DOMAIN_AUTHORITY = "DOMAIN_AUTHORITY"
    CROSS_VALIDATE = "CROSS_VALIDATE"
    COMPOSITE = "COMPOSITE"


#: Fields that must be non-empty on every contract.  Deliberately short: a required
#: field nobody can fill honestly gets filled dishonestly.
REQUIRED_FIELDS: tuple[str, ...] = (
    "dataset_id", "layer", "owner", "producer", "storage", "format",
    "grain", "temporal_profile", "version", "status",
)


@dataclass(frozen=True)
class DatasetContract:
    """What one dataset owes its consumers (§D5).

    ``layer``/``status``/``conflict_policy``/``temporal_profile`` hold the coerced
    enum when the YAML value is recognised and the RAW STRING when it is not — so an
    unknown ``temporal_profile`` reaches :func:`validate_registry` as a reportable
    violation instead of exploding at load time and taking the whole catalog with it.
    """

    dataset_id: str
    layer: Layer | str
    owner: str
    producer: str
    storage: str
    format: str
    grain: tuple[str, ...]
    temporal_profile: TemporalProfile | str
    version: str
    status: DatasetStatus | str
    id_column: str = ""
    id_type: str = ""
    schema: dict[str, dict[str, Any]] = field(default_factory=dict)
    timezone: str = ""
    frequency: str = ""
    adjustment: str = ""
    vendor: str = ""
    endpoint: str = ""
    conflict_policy: ConflictPolicy | str = ConflictPolicy.PRIMARY_ONLY
    freshness_sla_hours: float | None = None
    quality_checks: tuple[str, ...] = ()
    #: Functions/modules that READ this store, as code paths — prose, for a human
    #: chasing a change's blast radius.  Deliberately NOT named ``consumers``: that
    #: word already means the reverse edge of the lineage graph
    #: (:meth:`Registry.consumers_of`, which answers in dataset_ids), and one name for
    #: two different answers is how a lineage query stops being trustworthy.
    code_consumers: tuple[str, ...] = ()
    #: dataset_ids ONLY.  This IS the DAG; a code path here is not an edge.
    inputs: tuple[str, ...] = ()
    licensing: str = ""
    supersedes: str = ""
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DatasetContract":
        """Build from one YAML mapping, coercing enums LENIENTLY (see class docstring)."""
        if not isinstance(data, dict):
            raise RegistryError(f"dataset entry must be a mapping, got {type(data).__name__}")
        identity = data.get("identity") or {}
        if not isinstance(identity, dict):
            raise RegistryError(
                f"{data.get('dataset_id')!r}: identity: must be a mapping of "
                "id_column/id_type"
            )
        schema = data.get("schema") or {}
        if not isinstance(schema, dict):
            raise RegistryError(f"{data.get('dataset_id')!r}: schema: must be a mapping")
        sla = data.get("freshness_sla_hours")
        return cls(
            dataset_id=str(data.get("dataset_id") or ""),
            layer=_coerce(Layer, data.get("layer")),
            owner=str(data.get("owner") or ""),
            producer=str(data.get("producer") or ""),
            storage=str(data.get("storage") or ""),
            format=str(data.get("format") or ""),
            grain=_as_tuple(data.get("grain")),
            temporal_profile=_coerce(TemporalProfile, data.get("temporal_profile")),
            version=str(data.get("version") or ""),
            status=_coerce(DatasetStatus, data.get("status")),
            id_column=str(identity.get("id_column") or ""),
            id_type=str(identity.get("id_type") or ""),
            schema={str(k): dict(v or {}) for k, v in schema.items()},
            timezone=str(data.get("timezone") or ""),
            frequency=str(data.get("frequency") or ""),
            adjustment=str(data.get("adjustment") or ""),
            vendor=str(data.get("vendor") or ""),
            endpoint=str(data.get("endpoint") or ""),
            # A dataset that names no policy has exactly one vendor, which IS
            # PRIMARY_ONLY — defaulting it here keeps a single-vendor row from
            # having to recite a decision nobody made.
            conflict_policy=_coerce(
                ConflictPolicy,
                data.get("conflict_policy") or ConflictPolicy.PRIMARY_ONLY.value,
            ),
            freshness_sla_hours=float(sla) if sla is not None else None,
            quality_checks=_as_tuple(data.get("quality_checks")),
            code_consumers=_as_tuple(data.get("code_consumers")),
            inputs=_as_tuple(data.get("inputs")),
            licensing=str(data.get("licensing") or ""),
            supersedes=str(data.get("supersedes") or ""),
            notes=str(data.get("notes") or ""),
        )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _coerce(enum_cls, value):
    """Enum member when the value is recognised, else the raw string (or ``""``)."""
    if value is None:
        return ""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).strip())
    except ValueError:
        return str(value)


class Registry:
    """An ordered collection of :class:`DatasetContract`, indexed by ``dataset_id``.

    The ORDERED tuple is retained rather than only the index, because a duplicate
    ``dataset_id`` disappears into a dict and duplicate detection is one of the
    violations :func:`validate_registry` owes the caller.
    """

    __slots__ = ("_contracts", "_by_id")

    def __init__(self, contracts) -> None:
        self._contracts: tuple[DatasetContract, ...] = tuple(contracts)
        self._by_id: dict[str, DatasetContract] = {c.dataset_id: c for c in self._contracts}

    def __len__(self) -> int:
        return len(self._contracts)

    def __iter__(self):
        return iter(self._contracts)

    def all(self) -> tuple[DatasetContract, ...]:
        """Every contract, in file order."""
        return self._contracts

    def get(self, dataset_id: str) -> DatasetContract | None:
        """One contract by id, or ``None``.  Last wins on a duplicate id."""
        return self._by_id.get(dataset_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(c.dataset_id for c in self._contracts)

    def duplicate_ids(self) -> tuple[str, ...]:
        seen: set[str] = set()
        dupes: list[str] = []
        for c in self._contracts:
            if c.dataset_id in seen and c.dataset_id not in dupes:
                dupes.append(c.dataset_id)
            seen.add(c.dataset_id)
        return tuple(dupes)

    def inputs_of(self, dataset_id: str) -> tuple[str, ...]:
        """The dataset_ids this dataset reads (declared, not observed)."""
        contract = self.get(dataset_id)
        return contract.inputs if contract else ()

    def consumers_of(self, dataset_id: str) -> tuple[str, ...]:
        """The dataset_ids that declare this one as an input — the reverse edge.

        Derived from ``inputs`` rather than from each contract's ``code_consumers``
        prose field on purpose: the reverse edge must be a FACT of the graph, and a
        hand-maintained consumer list is exactly the thing that rots first.  The two
        answer different questions — dataset_ids here, code paths there — and they are
        kept under different names because they were once both called "consumers" and
        a caller could not tell which one it was holding.
        """
        return tuple(c.dataset_id for c in self._contracts if dataset_id in c.inputs)

    def dag(self) -> tuple[tuple[str, str], ...]:
        """Dependency edges as ``(input_id, dataset_id)`` — flows in the data direction."""
        return tuple(
            (src, c.dataset_id) for c in self._contracts for src in c.inputs
        )


def load_registry(path: str | Path | None = None) -> Registry:
    """Read ``config/dataset_registry.yml`` (or *path*) into a :class:`Registry`."""
    import yaml  # lazy: keeps the vocabulary importable in a lane without pyyaml

    target = Path(path) if path is not None else REGISTRY_PATH
    if not target.exists():
        raise RegistryError(f"dataset registry not found at {target}")
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RegistryError(f"{target}: top level must be a mapping, got {type(payload).__name__}")
    datasets = payload.get("datasets")
    if datasets is None:
        raise RegistryError(f"{target}: no `datasets:` key")
    if not isinstance(datasets, list):
        raise RegistryError(f"{target}: `datasets:` must be a list, got {type(datasets).__name__}")
    return Registry(DatasetContract.from_mapping(entry) for entry in datasets)


def validate_registry(registry: Registry) -> list[str]:
    """Human-readable violations, most structural first.  Returns; never prints or exits.

    Detects: duplicate ``dataset_id``; missing required field; unknown ``inputs``
    reference; ``temporal_profile`` outside the closed vocabulary; an ambiguous price
    column name on an L2/CANONICAL dataset (§D4's naming law, which binds at the
    canonical layer); and a cycle in the dependency DAG.
    """
    violations: list[str] = []
    known_ids = set(registry.ids())

    for dupe in registry.duplicate_ids():
        violations.append(f"duplicate dataset_id: {dupe!r} appears more than once")

    for contract in registry.all():
        label = contract.dataset_id or "<unnamed dataset>"
        for name in REQUIRED_FIELDS:
            value = getattr(contract, name, None)
            if value in (None, "", ()):
                violations.append(f"{label}: missing required field {name!r}")
        if not isinstance(contract.temporal_profile, TemporalProfile):
            violations.append(
                f"{label}: temporal_profile {contract.temporal_profile!r} is not one of "
                f"({', '.join(p.value for p in TemporalProfile)})"
            )
        if not isinstance(contract.layer, Layer):
            violations.append(
                f"{label}: layer {contract.layer!r} is not one of "
                f"({', '.join(lay.value for lay in Layer)})"
            )
        if not isinstance(contract.status, DatasetStatus):
            violations.append(
                f"{label}: status {contract.status!r} is not one of "
                f"({', '.join(s.value for s in DatasetStatus)})"
            )
        if not isinstance(contract.conflict_policy, ConflictPolicy):
            violations.append(
                f"{label}: conflict_policy {contract.conflict_policy!r} is not one of "
                f"({', '.join(c.value for c in ConflictPolicy)})"
            )
        for src in contract.inputs:
            if src not in known_ids:
                violations.append(
                    f"{label}: declares input {src!r}, which is not a dataset_id in this registry"
                )
        if contract.layer is Layer.L2_CANONICAL:
            for column in contract.schema:
                if price.is_ambiguous(column):
                    violations.append(
                        f"{label}: column {column!r} is an ambiguous price name on an "
                        "L2/CANONICAL dataset — §D4 requires {field}_{basis} "
                        f"(e.g. {price.canonical_column('close', 'tradj')})"
                    )

    violations.extend(_cycles(registry))
    return violations


def _cycles(registry: Registry) -> list[str]:
    """Every dependency cycle, reported once per cycle as a readable path."""
    edges: dict[str, tuple[str, ...]] = {
        c.dataset_id: tuple(s for s in c.inputs if registry.get(s) is not None)
        for c in registry.all()
    }
    found: list[str] = []
    seen_cycles: set[frozenset[str]] = set()
    state: dict[str, int] = {}   # 0 = visiting, 1 = done

    def walk(node: str, path: list[str]) -> None:
        state[node] = 0
        path.append(node)
        for src in edges.get(node, ()):
            if state.get(src) == 0:
                cycle = path[path.index(src):] + [src]
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    found.append("cycle in dependency DAG: " + " -> ".join(cycle))
            elif src not in state:
                walk(src, path)
        path.pop()
        state[node] = 1

    for dataset_id in edges:
        if dataset_id not in state:
            walk(dataset_id, [])
    return found
