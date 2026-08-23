from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
import inspect
import json
from pathlib import Path
import subprocess

import pytest

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    EvidenceFoundationError,
    combined_violations,
    compute_reference_id,
    load_vocabulary,
    render_owner_pointer,
    validate_reference,
)
from scripts.worktree_sparse import missing_dirs


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "evidence_foundation"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence_foundation"
SCHEMA_PATH = CONTRACT_DIR / "reference.v1.schema.json"
VOCABULARY_PATH = CONTRACT_DIR / "vocabulary.v1.json"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


EXPECTED_OWNER_BINDINGS = {
    "theme_graph.evidence": {
        "identity": ("evidence_id",),
        "clocks": {
            "published_at": ("source_published", ("date",)),
            "effective_at": ("world_valid", ("date",)),
            "computed_at": ("belief_or_build", ("datetime",)),
        },
        "reader": ("engine.theme_graph.store.read_evidence", "collection"),
    },
    "theme_graph.edge_belief": {
        "identity": ("edge_id", "belief_time"),
        "clocks": {
            "valid_from": ("world_valid", ("date",)),
            "valid_to": ("world_valid", ("date",)),
            "evidence_time": ("source_published", ("date",)),
            "belief_time": ("belief_or_build", ("date",)),
            "computed_at": ("belief_or_build", ("datetime",)),
        },
        "reader": ("engine.theme_graph.store.read_edges", "collection"),
    },
    "fif.raw_occurrence": {
        "identity": ("occurrence_id",),
        "clocks": {
            "clocks.accepted_at": ("source_published", ("datetime",)),
            "clocks.recorded_at": ("system_recorded", ("datetime",)),
            "clocks.mapping_available_at": ("knowable", ("datetime",)),
            "clocks.computed_at": ("belief_or_build", ("datetime",)),
            "clocks.published_at": ("belief_or_build", ("datetime",)),
        },
        "reader": ("engine.fundamental_forensics.raw_ledger.RawFactLedger.by_id", "direct"),
    },
    "fif.packet": {
        "identity": ("packet_id",),
        "clocks": {
            "query.source_event_cutoff": ("source_published", ("datetime",)),
            "query.system_recorded_cutoff": ("system_recorded", ("datetime",)),
            "governance.governance_recorded_at": ("system_recorded", ("datetime",)),
            "built_at": ("belief_or_build", ("datetime",)),
        },
        "reader": (
            "engine.fundamental_forensics.financial_intelligence_packet.validate_packet_semantics",
            "parser",
        ),
    },
    "earnings.workspace_generation": {
        "identity": ("generation_id", "event_id"),
        "clocks": {
            "lifecycle.source_available_at": ("knowable", ("datetime",)),
            "lifecycle.observed_at": ("observed", ("datetime",)),
            "generated_at": ("belief_or_build", ("datetime",)),
        },
        "reader": (
            "engine.company_intelligence.event_workspace.validate_event_workspace",
            "parser",
        ),
    },
    "institutional_13f.raw_receipt": {
        "identity": ("filer_cik", "accession", "receipt_id"),
        "clocks": {
            "clocks.report_period": ("world_valid", ("date",)),
            "clocks.accepted_at": ("source_published", ("datetime",)),
            "clocks.retained_at": ("system_recorded", ("datetime",)),
        },
        "reader": (
            "engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes",
            "parser",
        ),
    },
    "institutional_13f.catalog_generation": {
        "identity": ("report_period", "generation_id"),
        "clocks": {
            "clocks.report_period": ("world_valid", ("date",)),
            "clocks.source_cutoff_at": ("knowable", ("datetime",)),
            "clocks.published_at": ("belief_or_build", ("datetime",)),
        },
        "reader": ("engine.institutional_census.catalog.load_catalog_generation", "direct"),
    },
    "govrev.event.v2": {
        "identity": ("event_id",),
        "clocks": {
            "change.effective_at": ("world_valid", ("date", "datetime")),
            "change.known_at": ("knowable", ("datetime",)),
            "change.first_seen_at": ("knowable", ("datetime",)),
            "change.last_seen_at": ("knowable", ("datetime",)),
        },
        "reader": ("engine.government_revenue.workspace._validated_award_events", "collection"),
    },
    "biocatalyst.current_source_snapshot": {
        "identity": ("nct_id", "source_snapshot_id"),
        "clocks": {
            "source_effective_at": ("world_valid", ("date", "datetime")),
            "source_published_at": ("source_published", ("date", "datetime")),
            "source_dataset_timestamp_raw": ("source_published", ("datetime",)),
            "source_last_update_posted_at": ("source_published", ("date", "datetime")),
            "retrieved_at": ("observed", ("datetime",)),
            "first_seen_at": ("knowable", ("datetime",)),
            "valid_from": ("world_valid", ("date", "datetime")),
            "valid_to": ("world_valid", ("date", "datetime")),
            "transaction_from": ("system_recorded", ("datetime",)),
            "transaction_to": ("system_recorded", ("datetime",)),
        },
        "reader": ("engine.sector_intelligence.validate_contract", "parser"),
    },
    "biocatalyst.history_source_snapshot": {
        "identity": ("nct_id", "source_version", "source_snapshot_id"),
        "clocks": {
            "source_submitted_at": ("source_published", ("date",)),
            "source_last_update_submit_qc_at": ("source_published", ("date",)),
            "retrieved_at": ("observed", ("datetime",)),
            "transaction_from": ("system_recorded", ("datetime",)),
            "transaction_to": ("system_recorded", ("datetime",)),
        },
        "reader": ("engine.sector_intelligence.validate_contract", "parser"),
    },
    "txi.episode_transition": {
        "identity": ("chain", "rev", "episode_id", "transition", "hop", "asof"),
        "clocks": {"asof": ("belief_or_build", ("date",))},
        "reader": ("engine.transmission_chains._read_ledger", "collection"),
    },
    "qledger.claim": {
        "identity": ("claim_id",),
        "clocks": {
            "asof": ("belief_or_build", ("date",)),
            "vector_asof": ("belief_or_build", ("date",)),
            "timestamp": ("system_recorded", ("datetime",)),
            "check_by": ("review_due", ("date",)),
        },
        "reader": ("engine.qledger.load_claims", "collection"),
    },
    "market_memory.outcome_record": {
        "identity": ("outcome_record_id",),
        "clocks": {
            "effective_at": ("world_valid", ("datetime",)),
            "source_available_at": ("knowable", ("datetime",)),
            "known_at": ("knowable", ("datetime",)),
            "observed_at": ("observed", ("datetime",)),
            "recorded_at": ("system_recorded", ("datetime",)),
        },
        "reader": ("engine.neuralweb.market_memory_forward_store.load_record", "direct"),
    },
}

EXPECTED_COVERAGE_REPLAY = {
    "theme_graph.evidence": (
        ["append_only_bitemporal"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "theme_graph.edge_belief": (
        ["append_only_bitemporal"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "fif.raw_occurrence": (
        ["record_history_complete"],
        {
            "live": ["owner_native"],
            "historical_replay": ["owner_native"],
            "retrospective_research": ["owner_native"],
        },
    ),
    "fif.packet": (
        ["source_release_snapshot_only"],
        {
            "live": ["owner_native"],
            "historical_replay": ["owner_native"],
            "retrospective_research": ["owner_native"],
        },
    ),
    "earnings.workspace_generation": (
        ["immutable_generation"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "institutional_13f.raw_receipt": (
        ["source_release_snapshot_only"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "institutional_13f.catalog_generation": (
        ["immutable_generation"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "govrev.event.v2": (
        ["partial"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "biocatalyst.current_source_snapshot": (
        ["current_only"],
        {"live": ["owner_native"]},
    ),
    "biocatalyst.history_source_snapshot": (
        ["record_history_complete"],
        {
            "live": ["owner_native"],
            "historical_replay": ["owner_native"],
            "retrospective_research": ["owner_native"],
        },
    ),
    "txi.episode_transition": (
        ["prospective_only"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
    "qledger.claim": (["prospective_only"], {"live": ["owner_native"]}),
    "market_memory.outcome_record": (
        ["prospective_only"],
        {"live": ["owner_native"], "historical_replay": ["owner_native"]},
    ),
}

EXPECTED_NATIVE_IDENTITY_GRAMMARS = {
    "theme_graph.evidence": {
        "evidence_id": {"kind": "regex", "pattern": "^ev:[a-f0-9]{16}$"},
    },
    "theme_graph.edge_belief": {
        "edge_id": {
            "kind": "regex",
            "pattern": "^(member_of|expresses|same_as|translates_to|parent_of|related|supplies|enables|bottleneck_of|benefits_from|catalyst_of|tracks|hedges):[^\\r\\n]+->[^\\r\\n]+@[0-9]{4}-[0-9]{2}-[0-9]{2}$",
        },
        "belief_time": {"kind": "date"},
    },
    "fif.raw_occurrence": {
        "occurrence_id": {"kind": "regex", "pattern": "^rawfact_[a-f0-9]{64}$"},
    },
    "fif.packet": {
        "packet_id": {"kind": "regex", "pattern": "^fip_[a-f0-9]{24}$"},
    },
    "earnings.workspace_generation": {
        "generation_id": {"kind": "regex", "pattern": "^[0-9a-f]{24,64}$"},
        "event_id": {
            "kind": "regex",
            "pattern": r"^evt_cik\d{10}_\d{4}(?:q[1-4]|fy)_[a-z0-9]+$",
        },
    },
    "institutional_13f.raw_receipt": {
        "filer_cik": {"kind": "regex", "pattern": "^[0-9]{10}$"},
        "accession": {
            "kind": "regex",
            "pattern": "^[0-9]{10}-[0-9]{2}-[0-9]{6}$",
        },
        "receipt_id": {"kind": "regex", "pattern": "^i13fraw_[a-f0-9]{64}$"},
    },
    "institutional_13f.catalog_generation": {
        "report_period": {"kind": "date"},
        "generation_id": {"kind": "regex", "pattern": "^i13fgen_[a-f0-9]{64}$"},
    },
    "govrev.event.v2": {
        "event_id": {
            "kind": "regex",
            "pattern": "^gov(?:ws|opp|awd)-[a-zA-Z0-9_-]+$",
        },
    },
    "biocatalyst.current_source_snapshot": {
        "nct_id": {"kind": "regex", "pattern": "^NCT[0-9]{8}$"},
        "source_snapshot_id": {
            "kind": "regex",
            "pattern": "^ctgov_snapshot_[a-zA-Z0-9_-]+$",
        },
    },
    "biocatalyst.history_source_snapshot": {
        "nct_id": {"kind": "regex", "pattern": "^NCT[0-9]{8}$"},
        "source_version": {
            "kind": "integer_range",
            "minimum": 0,
        },
        "source_snapshot_id": {
            "kind": "regex",
            "pattern": "^ctgov_history_snapshot_[A-Za-z0-9_-]+$",
        },
    },
    "txi.episode_transition": {
        "chain": {
            "kind": "regex",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$",
        },
        "rev": {"kind": "integer_range", "minimum": 0},
        "episode_id": {
            "kind": "regex",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,255}@r[0-9]+:[0-9]{4}-[0-9]{2}-[0-9]{2}$",
        },
        "transition": {
            "kind": "enum",
            "values": ["arming", "propagating", "expressed", "failed", "expired"],
        },
        "hop": {"kind": "integer_range", "minimum": 0},
        "asof": {"kind": "date"},
    },
    "qledger.claim": {
        "claim_id": {"kind": "regex", "pattern": "^[a-f0-9]{16}$"},
    },
    "market_memory.outcome_record": {
        "outcome_record_id": {
            "kind": "regex",
            "pattern": "^mmoutcome_[a-f0-9]{64}$",
        },
    },
}

VALID_NATIVE_IDENTITIES = {
    "theme_graph.evidence": {"evidence_id": "ev:" + "a" * 16},
    "theme_graph.edge_belief": {
        "edge_id": "member_of:co:us:AAPL->basket:baskets:demo@2026-08-23",
        "belief_time": "2026-08-23",
    },
    "fif.raw_occurrence": {"occurrence_id": "rawfact_" + "a" * 64},
    "fif.packet": {"packet_id": "fip_" + "a" * 24},
    "earnings.workspace_generation": {
        "generation_id": "a" * 24,
        "event_id": "evt_cik0000320193_2026q3_results",
    },
    "institutional_13f.raw_receipt": {
        "filer_cik": "0000320193",
        "accession": "0000320193-26-000001",
        "receipt_id": "i13fraw_" + "a" * 64,
    },
    "institutional_13f.catalog_generation": {
        "report_period": "2026-06-30",
        "generation_id": "i13fgen_" + "a" * 64,
    },
    "govrev.event.v2": {"event_id": "govawd-fixture"},
    "biocatalyst.current_source_snapshot": {
        "nct_id": "NCT00000001",
        "source_snapshot_id": "ctgov_snapshot_fixture",
    },
    "biocatalyst.history_source_snapshot": {
        "nct_id": "NCT00000001",
        "source_version": 1,
        "source_snapshot_id": "ctgov_history_snapshot_fixture",
    },
    "txi.episode_transition": {
        "chain": "supply",
        "rev": 1,
        "episode_id": "supply@r1:2026-08-23",
        "transition": "arming",
        "hop": 1,
        "asof": "2026-08-23",
    },
    "qledger.claim": {"claim_id": "a" * 16},
    "market_memory.outcome_record": {"outcome_record_id": "mmoutcome_" + "a" * 64},
}

ALTERNATE_FIRST_IDENTITY_VALUE = {
    "theme_graph.evidence": "ev:" + "b" * 16,
    "theme_graph.edge_belief": "member_of:co:us:MSFT->basket:baskets:demo@2026-08-23",
    "fif.raw_occurrence": "rawfact_" + "b" * 64,
    "fif.packet": "fip_" + "b" * 24,
    "earnings.workspace_generation": "b" * 24,
    "institutional_13f.raw_receipt": "0001067983",
    "institutional_13f.catalog_generation": "2026-03-31",
    "govrev.event.v2": "govawd-fixture-other",
    "biocatalyst.current_source_snapshot": "NCT00000002",
    "biocatalyst.history_source_snapshot": "NCT00000002",
    "txi.episode_transition": "other_chain",
    "qledger.claim": "b" * 16,
    "market_memory.outcome_record": "mmoutcome_" + "b" * 64,
}

VALID_SUBJECT_VALUES = {
    "cik": "0000320193",
    "issuer_id": "cik:0000320193",
    "security_id": "xnas:AAPL",
    "listing_key": "US-XNAS-AAPL",
    "award_key": "award-fixture",
    "notice_id": "notice-fixture",
    "nct": "NCT00000001",
    "theme_node": "co:us:AAPL",
    "chain_id": "supply",
    "claim_id": "a" * 16,
    "accession": "0000320193-26-000001",
    "mm_subject": "xnas:AAPL",
    "institutional_manager_cik": "0000320193",
    "cusip": "037833100",
}


def _expected_clock_bindings(
    values: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, dict[str, object]]:
    return {
        field: {"class": clock_class, "grains": list(grains)}
        for field, (clock_class, grains) in values.items()
    }


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return _json(SCHEMA_PATH)


@pytest.fixture(scope="module")
def vocabulary() -> dict:
    return load_vocabulary(VOCABULARY_PATH)


def _with_id(payload: dict) -> dict:
    payload["reference_id"] = compute_reference_id(payload)
    return payload


def _fixture(name: str) -> dict:
    return _json(FIXTURE_DIR / name)


def _owner_reference(name: str, owner: dict, clock_classes: list[str]) -> dict:
    identity = deepcopy(VALID_NATIVE_IDENTITIES[name])
    subject_key_type = owner["subject_key_types"][0]
    payload = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "reference_id": "",
        "object_class": owner["object_classes"][0],
        "owner_store": name,
        "native_identity": identity,
        "native_schema": owner["native_schemas"][0],
        "native_digest": {"state": "unknown", "sha256": None},
        "coverage_class": owner["coverage_classes"][0],
        "subject": {
            "key_type": subject_key_type,
            "key": VALID_SUBJECT_VALUES[subject_key_type],
        },
        "secondary_subjects": [],
        "clocks": [
            {
                "class": binding["class"],
                "field": field,
                "value_state": "unknown",
                "value": None,
                "grain": binding["grains"][0],
            }
            for field, binding in owner["clock_bindings"].items()
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": owner["reader"],
            "owner_reader_kind": owner["reader_kind"],
            "pointer": render_owner_pointer(owner, identity),
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none",
            "predecessor_reference_ids": [],
            "clock_field": None,
            "chronology_state": "not_applicable",
            "append_only": True,
            "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live",
            "cutoffs": {
                clock_class: {"state": "unknown", "value": None, "grain": "date"}
                for clock_class in clock_classes
            },
            "code_revision": None,
            "input_digest": None,
            "vintage_state": owner["replay_capabilities"]["live"][0],
        },
        "authority": dict(ALL_FALSE_AUTHORITY),
    }
    return _with_id(payload)


def _resolve_reader(path: str) -> object:
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        module_name = ".".join(parts[:split])
        try:
            value: object = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(f"{exc.name}."):
                raise
            continue
        for attribute in parts[split:]:
            value = getattr(value, attribute)
        return value
    raise AssertionError(f"reader module is not importable: {path}")


def test_contract_and_vocabulary_are_frozen_v1(schema: dict, vocabulary: dict) -> None:
    assert schema["properties"]["schema"]["const"] == "evidence_foundation.reference.v1"
    assert schema["properties"]["version"]["const"] == "1.0.0"
    assert vocabulary["schema"] == "evidence_foundation.vocabulary.v1"
    assert vocabulary["version"] == "1.0.0"
    assert len(vocabulary["owner_stores"]) == 13
    assert set(vocabulary["owner_stores"]) == set(EXPECTED_OWNER_BINDINGS)
    assert "reference.security_master" not in vocabulary["owner_stores"]
    assert "earnings.company_event" not in vocabulary["owner_stores"]
    assert "txi.episode_transition" in vocabulary["owner_stores"]
    assert "ticker_store_key" not in vocabulary["subject_key_types"]
    assert "ticker_store_key" in vocabulary["excluded_identity_types"]


def test_every_owner_has_an_exact_schema_identity_clock_and_pointer_binding(
    vocabulary: dict,
) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        assert set(owner["native_identity_types"]) == set(owner["native_identity_fields"]), name
        assert set(owner["native_identity_grammars"]) == set(owner["native_identity_fields"]), name
        assert owner["native_schemas"] and owner["clock_bindings"], name
        assert "synapse_asof_field" in owner, name
        reference = _owner_reference(name, owner, vocabulary["clock_classes"])
        assert validate_reference(reference) == reference
        identity = reference["native_identity"]
        first_field = owner["native_identity_fields"][0]
        alternate = dict(identity)
        alternate[first_field] = ALTERNATE_FIRST_IDENTITY_VALUE[name]
        rows = (identity, alternate)
        pointer = render_owner_pointer(owner, identity)
        assert pointer != render_owner_pointer(owner, alternate), name
        assert [row for row in rows if render_owner_pointer(owner, row) == pointer] == [identity]


def test_vocabulary_refuses_missing_schema_identity_type_clock_and_synapse_bindings(
    vocabulary: dict, tmp_path: Path
) -> None:
    cases = (
        ("native_schemas", "vocabulary_owner_native_schemas_invalid"),
        ("native_identity_types", "vocabulary_owner_identity_types_invalid"),
        ("native_identity_grammars", "vocabulary_owner_identity_grammars_invalid"),
        ("coverage_classes", "vocabulary_owner_coverage_classes_invalid"),
        ("replay_capabilities", "vocabulary_owner_replay_capabilities_invalid"),
        ("clock_bindings", "vocabulary_owner_clocks_missing"),
        ("synapse_asof_field", "vocabulary_synapse_asof_unspecified"),
    )
    for field, code in cases:
        hostile = deepcopy(vocabulary)
        del hostile["owner_stores"]["qledger.claim"][field]
        path = tmp_path / f"missing-{field}.json"
        path.write_text(json.dumps(hostile), encoding="utf-8")
        with pytest.raises(EvidenceFoundationError, match=code):
            load_vocabulary(path)

    unbound = deepcopy(vocabulary)
    unbound["owner_stores"]["qledger.claim"]["synapse_asof_field"] = "invented_at"
    path = tmp_path / "unbound.json"
    path.write_text(json.dumps(unbound), encoding="utf-8")
    with pytest.raises(EvidenceFoundationError, match="vocabulary_synapse_asof_unbound"):
        load_vocabulary(path)


def test_every_owner_reader_symbol_is_callable_and_kind_is_honest(vocabulary: dict) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        assert callable(_resolve_reader(owner["reader"])), name
        assert owner["reader_kind"] in {"direct", "collection", "parser"}, name
    assert vocabulary["owner_stores"]["fif.packet"]["reader_kind"] == "parser"
    assert vocabulary["owner_stores"]["biocatalyst.current_source_snapshot"]["reader_kind"] == "parser"
    assert vocabulary["owner_stores"]["earnings.workspace_generation"]["reader_kind"] == "parser"


def test_dataos_security_master_is_deferred_without_a_native_row_reader(
    vocabulary: dict,
) -> None:
    from lib.dataos.identity import IssuerMaster

    assert "reference.security_master" not in vocabulary["owner_stores"]
    assert "NO I/O" in (IssuerMaster.__doc__ or "")
    assert IssuerMaster().issuer_of_security("SEC:US-XNAS-AAPL") is None
    assert IssuerMaster().rows == ()


def test_owner_vocabulary_is_bound_to_current_source_contracts(vocabulary: dict) -> None:
    from engine.company_intelligence.event_workspace import (
        WORKSPACE_KEYS,
        WORKSPACE_SCHEMA,
        _EVENT_ID_RE,
        _GENERATION_RE,
    )
    from engine.fundamental_forensics.financial_intelligence_packet import PACKET_SCHEMA
    from engine.fundamental_forensics.financial_intelligence_packet import readdress_packet
    from engine.fundamental_forensics.raw_ledger import (
        RAW_LEDGER_SCHEMA,
        TemporalClocks,
        stable_id,
    )
    from engine.government_revenue.workspace import EVENT_CONTRACT
    from engine.institutional_census.models import (
        CATALOG_MANIFEST_SCHEMA,
        RAW_RECEIPT_SCHEMA,
        CatalogClocks,
        EvidenceClocks,
        catalog_manifest_key,
        raw_receipt_key,
    )
    from engine.neuralweb.market_memory_forward_store import (
        _ID_PATTERN_BY_KIND,
        _SCHEMA_BY_KIND,
    )
    from engine.transmission_chains import STATE_LABELS
    from engine.qledger import _claim_id
    from engine.theme_graph.materialize import edge_id_for, evidence_id_for
    from engine.theme_graph.store import EDGE_COLUMNS, EDGE_KEY, EVIDENCE_COLUMNS, EVIDENCE_KEY

    owners = vocabulary["owner_stores"]
    govrev_schema = _json(
        ROOT / "contracts/government_revenue/government_procurement_event.v2.schema.json"
    )
    assert set(owners) == set(EXPECTED_OWNER_BINDINGS)
    for name, expected in EXPECTED_OWNER_BINDINGS.items():
        owner = owners[name]
        assert owner["native_identity_fields"] == list(expected["identity"]), name
        assert owner["clock_bindings"] == _expected_clock_bindings(expected["clocks"]), name
        assert (owner["reader"], owner["reader_kind"]) == expected["reader"], name
        expected_coverage, expected_replay = EXPECTED_COVERAGE_REPLAY[name]
        assert owner["coverage_classes"] == expected_coverage, name
        assert owner["replay_capabilities"] == expected_replay, name
        assert owner["native_identity_grammars"] == EXPECTED_NATIVE_IDENTITY_GRAMMARS[name]

    assert owners["theme_graph.evidence"]["native_identity_fields"] == list(EVIDENCE_KEY)
    assert owners["theme_graph.edge_belief"]["native_identity_fields"] == list(EDGE_KEY)
    assert evidence_id_for("operator_curation", "fixture", "2026-08-23").startswith("ev:")
    assert edge_id_for(
        "MEMBER_OF", "co:us:AAPL", "basket:baskets:demo", "2026-08-23"
    ) == VALID_NATIVE_IDENTITIES["theme_graph.edge_belief"]["edge_id"]
    assert set(owners["theme_graph.evidence"]["clock_bindings"]) == {
        "published_at", "effective_at", "computed_at"
    } <= set(EVIDENCE_COLUMNS)
    assert set(owners["theme_graph.edge_belief"]["clock_bindings"]) == {
        "valid_from", "valid_to", "evidence_time", "belief_time", "computed_at"
    } <= set(EDGE_COLUMNS)
    assert owners["fif.raw_occurrence"]["native_schemas"] == [f"{RAW_LEDGER_SCHEMA}#RawFactOccurrence"]
    assert stable_id("rawfact", {"fixture": True}).startswith("rawfact_")
    assert set(owners["fif.raw_occurrence"]["clock_bindings"]) == {
        f"clocks.{field}" for field in TemporalClocks.__dataclass_fields__
    }
    assert owners["fif.packet"]["native_schemas"] == [PACKET_SCHEMA]
    assert readdress_packet({"fixture": True})["packet_id"].startswith("fip_")
    assert owners["earnings.workspace_generation"]["native_schemas"] == [WORKSPACE_SCHEMA]
    assert {"event_id", "generation_id", "generated_at", "lifecycle"} <= set(WORKSPACE_KEYS)
    earnings_grammars = owners["earnings.workspace_generation"]["native_identity_grammars"]
    assert earnings_grammars["generation_id"]["pattern"] == _GENERATION_RE.pattern
    assert earnings_grammars["event_id"]["pattern"] == _EVENT_ID_RE.pattern
    assert owners["institutional_13f.raw_receipt"]["native_schemas"] == [RAW_RECEIPT_SCHEMA]
    assert owners["institutional_13f.catalog_generation"]["native_schemas"] == [CATALOG_MANIFEST_SCHEMA]
    assert set(owners["institutional_13f.raw_receipt"]["clock_bindings"]) == {
        f"clocks.{field}" for field in EvidenceClocks.__dataclass_fields__
    }
    assert set(owners["institutional_13f.catalog_generation"]["clock_bindings"]) == {
        f"clocks.{field}" for field in CatalogClocks.__dataclass_fields__
    }
    raw_receipt_key(**VALID_NATIVE_IDENTITIES["institutional_13f.raw_receipt"])
    catalog_manifest_key(**VALID_NATIVE_IDENTITIES["institutional_13f.catalog_generation"])
    assert owners["govrev.event.v2"]["native_schemas"] == [EVENT_CONTRACT]
    assert owners["govrev.event.v2"]["native_identity_grammars"]["event_id"][
        "pattern"
    ] == govrev_schema["properties"]["event_id"]["pattern"]
    assert set(owners["govrev.event.v2"]["clock_bindings"]) == {
        f"change.{field}"
        for field in govrev_schema["$defs"]["change"]["required"]
        if field.endswith("_at")
    }
    assert owners["market_memory.outcome_record"]["native_schemas"] == [_SCHEMA_BY_KIND["outcome"]]
    assert _ID_PATTERN_BY_KIND["outcome"].fullmatch(
        VALID_NATIVE_IDENTITIES["market_memory.outcome_record"]["outcome_record_id"]
    )
    assert len(_claim_id("desk", "2026-08-23", "AAPL", 21, 1)) == 16
    assert owners["txi.episode_transition"]["native_identity_grammars"]["transition"][
        "values"
    ] == [state for state in STATE_LABELS if state != "dormant"]


def test_biocatalyst_current_and_history_bind_real_wire_fields(vocabulary: dict) -> None:
    current_schema = _json(ROOT / "contracts/biocatalyst/trial_source_snapshot.v1.schema.json")
    history_schema = _json(ROOT / "contracts/biocatalyst/trial_history_source_snapshot.v1.schema.json")
    current = vocabulary["owner_stores"]["biocatalyst.current_source_snapshot"]
    history = vocabulary["owner_stores"]["biocatalyst.history_source_snapshot"]
    assert current["native_identity_fields"] == ["nct_id", "source_snapshot_id"]
    assert history["native_identity_fields"] == ["nct_id", "source_version", "source_snapshot_id"]
    assert history["native_identity_types"]["source_version"] == "integer"
    current_clock_fields = set(EXPECTED_OWNER_BINDINGS["biocatalyst.current_source_snapshot"]["clocks"])
    history_clock_fields = set(EXPECTED_OWNER_BINDINGS["biocatalyst.history_source_snapshot"]["clocks"])
    current_source_clock_fields = {
        field
        for field in current_schema["required"]
        if field.endswith(("_at", "_from", "_to", "_timestamp_raw"))
    }
    history_source_clock_fields = {
        field
        for field in history_schema["required"]
        if field.endswith(("_at", "_from", "_to", "_timestamp_raw"))
    }
    assert set(current["native_identity_fields"]) == {"nct_id", "source_snapshot_id"}
    assert set(current["clock_bindings"]) == current_clock_fields == current_source_clock_fields
    assert current["native_identity_grammars"]["nct_id"]["pattern"] == current_schema[
        "$defs"
    ]["nctId"]["pattern"]
    assert current["native_identity_grammars"]["source_snapshot_id"]["pattern"] == (
        current_schema["properties"]["source_snapshot_id"]["pattern"]
    )
    assert current["coverage_classes"] == [
        current_schema["properties"]["coverage_class"]["const"]
    ]
    assert set(history["native_identity_fields"]) == {"nct_id", "source_version", "source_snapshot_id"}
    assert set(history["clock_bindings"]) == history_clock_fields == history_source_clock_fields
    assert history["native_identity_grammars"]["nct_id"]["pattern"] == history_schema[
        "$defs"
    ]["nctId"]["pattern"]
    assert history["native_identity_grammars"]["source_snapshot_id"]["pattern"] == (
        history_schema["properties"]["source_snapshot_id"]["pattern"]
    )
    assert history["native_identity_grammars"]["source_version"]["minimum"] == (
        history_schema["properties"]["source_version"]["minimum"]
    )
    assert history["coverage_classes"] == [
        history_schema["properties"]["coverage_class"]["const"]
    ]


def test_txi_full_native_key_prevents_episode_aliasing(vocabulary: dict) -> None:
    from engine.transmission_chains import _ledger_key

    owner = vocabulary["owner_stores"]["txi.episode_transition"]
    row_a = {
        "chain": "supply",
        "rev": 1,
        "episode_id": "supply@r1:2026-08-23",
        "transition": "arming",
        "hop": 1,
        "asof": "2026-08-23",
    }
    row_b = {**row_a, "transition": "propagating", "hop": 2}
    assert row_a["episode_id"] == row_b["episode_id"]
    assert _ledger_key(row_a) != _ledger_key(row_b)
    assert tuple(owner["native_identity_fields"]) == ("chain", "rev", "episode_id", "transition", "hop", "asof")
    assert render_owner_pointer(owner, row_a) != render_owner_pointer(owner, row_b)
    assert [row for row in (row_a, row_b) if _ledger_key(row) == _ledger_key(row_a)] == [row_a]


def test_earnings_parser_proves_native_object_identity(vocabulary: dict) -> None:
    from engine.company_intelligence.event_workspace import validate_event_workspace

    owner = vocabulary["owner_stores"]["earnings.workspace_generation"]
    first = {"generation_id": "a" * 24, "event_id": "evt_cik0000320193_2026q3_results"}
    second = {"generation_id": "b" * 24, "event_id": first["event_id"]}
    assert render_owner_pointer(owner, first) != render_owner_pointer(owner, second)
    reference = _fixture("earnings_workspace_valid.json")
    native_identity = reference["native_identity"]
    workspace = {
        "schema": "event_workspace.v1",
        "event_id": native_identity["event_id"],
        "aliases": [],
        "issuer": {},
        "fiscal_period": {},
        "lifecycle": {},
        "completeness": {},
        "facts": [],
        "deltas": [],
        "guidance": [],
        "claims": [],
        "sources": [],
        "warnings": [],
        "generation_id": native_identity["generation_id"],
        "generated_at": "2026-07-30T20:31:00Z",
        "authority": "context_only",
        "prophet_flags": {
            "may_rank": False,
            "may_size": False,
            "may_gate": False,
            "prophet_authority": False,
        },
        "claim_citations_pending": False,
        "qa_exchanges": [],
    }
    assert validate_event_workspace(workspace) is None
    assert {
        "generation_id": workspace["generation_id"],
        "event_id": workspace["event_id"],
    } == native_identity
    assert reference["provenance"]["owner_reader"] == (
        "engine.company_intelligence.event_workspace.validate_event_workspace"
    )
    assert reference["provenance"]["owner_reader_kind"] == "parser"
    assert reference["provenance"]["pointer"] == render_owner_pointer(owner, native_identity)


def test_fixture_manifest_is_complete_and_byte_receipted() -> None:
    manifest = _json(MANIFEST_PATH)
    assert manifest["schema"] == "evidence_foundation.fixture_manifest.v1"
    assert len(manifest["fixtures"]) == 8
    assert len({row["file"] for row in manifest["fixtures"]}) == 8
    for row in manifest["fixtures"]:
        payload = (FIXTURE_DIR / row["file"]).read_bytes()
        assert payload.endswith(b"\n")
        assert len(payload) == row["size_bytes"]
        assert sha256(payload).hexdigest() == row["sha256"]


EXPECTED_VIOLATIONS = {
    "duplicate_corroboration_hostile.json": {"relation_0_independence_not_declarative:source_independence"},
    "replay_lookahead_hostile.json": {"replay_lookahead:clocks.accepted_at", "replay_lookahead:clocks.recorded_at"},
    "authority_leak_hostile.json": {"authority_leak"},
}


def test_all_golden_fixtures_use_the_combined_fail_closed_validator(vocabulary: dict) -> None:
    for row in _json(MANIFEST_PATH)["fixtures"]:
        payload = _fixture(row["file"])
        violations = set(combined_violations(payload))
        assert payload["reference_id"] == compute_reference_id(payload), row["file"]
        if row["expected"] == "valid":
            assert validate_reference(payload) == payload
            assert not violations
        else:
            assert EXPECTED_VIOLATIONS[row["file"]] <= violations
            with pytest.raises(EvidenceFoundationError):
                validate_reference(payload)


def test_every_owner_native_schema_and_clock_is_required_exactly_once(vocabulary: dict) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        valid = _owner_reference(name, owner, vocabulary["clock_classes"])
        bad_schema = deepcopy(valid)
        bad_schema["native_schema"] = "invented.schema"
        _with_id(bad_schema)
        assert "native_schema_not_owned" in combined_violations(bad_schema)
        missing_schema = deepcopy(valid)
        del missing_schema["native_schema"]
        _with_id(missing_schema)
        assert combined_violations(missing_schema)
        for field in owner["clock_bindings"]:
            missing = deepcopy(valid)
            missing["clocks"] = [clock for clock in missing["clocks"] if clock["field"] != field]
            _with_id(missing)
            assert f"clock_field_missing:{field}" in combined_violations(missing)
            duplicate = deepcopy(valid)
            duplicate["clocks"].append(deepcopy(next(clock for clock in duplicate["clocks"] if clock["field"] == field)))
            _with_id(duplicate)
            assert f"clock_field_duplicate:{field}" in combined_violations(duplicate)


def test_native_identity_types_and_pointer_are_fail_closed(vocabulary: dict) -> None:
    owner = vocabulary["owner_stores"]["txi.episode_transition"]
    valid = _owner_reference("txi.episode_transition", owner, vocabulary["clock_classes"])
    wrong_type = deepcopy(valid)
    wrong_type["native_identity"]["hop"] = "1"
    wrong_type["provenance"]["pointer"] = owner["pointer_template"].format(
        **wrong_type["native_identity"]
    )
    _with_id(wrong_type)
    assert "native_identity_type_mismatch:hop" in combined_violations(wrong_type)
    wrong_pointer = deepcopy(valid)
    wrong_pointer["provenance"]["pointer"] += "-alias"
    _with_id(wrong_pointer)
    assert "owner_pointer_mismatch" in combined_violations(wrong_pointer)


@pytest.mark.parametrize(
    ("owner_name", "field", "hostile_value"),
    [
        ("theme_graph.evidence", "evidence_id", "evidence-A"),
        ("theme_graph.edge_belief", "edge_id", "bad-edge"),
        ("theme_graph.edge_belief", "belief_time", "2026-02-30"),
        ("fif.raw_occurrence", "occurrence_id", "rawfact_short"),
        ("fif.packet", "packet_id", "fip_not-native"),
        ("earnings.workspace_generation", "generation_id", "generation-A"),
        ("earnings.workspace_generation", "event_id", "AAPL"),
        ("institutional_13f.raw_receipt", "filer_cik", "AAPL"),
        ("institutional_13f.raw_receipt", "accession", "0000320193"),
        ("institutional_13f.raw_receipt", "receipt_id", "i13fraw_short"),
        ("institutional_13f.catalog_generation", "report_period", "2026-02-30"),
        ("institutional_13f.catalog_generation", "generation_id", "i13fgen_short"),
        ("govrev.event.v2", "event_id", "IRDM"),
        ("biocatalyst.current_source_snapshot", "nct_id", "MRNA"),
        ("biocatalyst.current_source_snapshot", "source_snapshot_id", "snapshot-A"),
        ("biocatalyst.history_source_snapshot", "nct_id", "MRNA"),
        ("biocatalyst.history_source_snapshot", "source_version", -1),
        (
            "biocatalyst.history_source_snapshot",
            "source_snapshot_id",
            "history-snapshot-A",
        ),
        ("txi.episode_transition", "chain", "chain with spaces"),
        ("txi.episode_transition", "rev", -1),
        ("txi.episode_transition", "episode_id", "episode-1"),
        ("txi.episode_transition", "transition", "ARMED"),
        ("txi.episode_transition", "hop", -1),
        ("txi.episode_transition", "asof", "2026-02-30"),
        ("qledger.claim", "claim_id", "claim-A"),
        ("market_memory.outcome_record", "outcome_record_id", "outcome-A"),
    ],
)
def test_every_owner_native_identity_value_grammar_is_fail_closed_after_rehash(
    owner_name: str,
    field: str,
    hostile_value: str | int,
    vocabulary: dict,
) -> None:
    owner = vocabulary["owner_stores"][owner_name]
    hostile = _owner_reference(owner_name, owner, vocabulary["clock_classes"])
    hostile["native_identity"][field] = hostile_value
    hostile["provenance"]["pointer"] = owner["pointer_template"].format(
        **hostile["native_identity"]
    )
    _with_id(hostile)
    expected = f"native_identity_value_invalid:{field}"
    assert expected in combined_violations(hostile)
    with pytest.raises(EvidenceFoundationError, match=expected):
        validate_reference(hostile)


def test_subject_cik_rejects_ticker_after_pointer_and_reference_id_recompute(
    vocabulary: dict,
) -> None:
    owner = vocabulary["owner_stores"]["earnings.workspace_generation"]
    hostile = _owner_reference(
        "earnings.workspace_generation", owner, vocabulary["clock_classes"]
    )
    hostile["subject"]["key"] = "AAPL"
    hostile["provenance"]["pointer"] = render_owner_pointer(
        owner, hostile["native_identity"]
    )
    _with_id(hostile)
    assert "subject_0_key_invalid:cik" in combined_violations(hostile)
    with pytest.raises(EvidenceFoundationError, match="subject_0_key_invalid:cik"):
        validate_reference(hostile)


def test_public_validation_api_cannot_trust_attacker_vocabulary_rebinding(
    vocabulary: dict,
) -> None:
    owner = vocabulary["owner_stores"]["earnings.workspace_generation"]
    hostile = _owner_reference(
        "earnings.workspace_generation", owner, vocabulary["clock_classes"]
    )
    hostile["native_schema"] = "attacker.schema"
    hostile["provenance"]["owner_reader"] = "attacker.read"
    _with_id(hostile)
    attacker_vocabulary = deepcopy(vocabulary)
    attacker_owner = attacker_vocabulary["owner_stores"]["earnings.workspace_generation"]
    attacker_owner["native_schemas"] = ["attacker.schema"]
    attacker_owner["reader"] = "attacker.read"

    assert "vocabulary" not in inspect.signature(combined_violations).parameters
    assert "vocabulary" not in inspect.signature(validate_reference).parameters
    with pytest.raises(TypeError):
        combined_violations(hostile, vocabulary=attacker_vocabulary)  # type: ignore[call-arg]
    violations = set(combined_violations(hostile))
    assert {"native_schema_not_owned", "owner_reader_mismatch"} <= violations
    with pytest.raises(EvidenceFoundationError):
        validate_reference(hostile)


def test_biocatalyst_coverage_and_replay_capabilities_cannot_masquerade(
    vocabulary: dict,
) -> None:
    current_owner = vocabulary["owner_stores"]["biocatalyst.current_source_snapshot"]
    current = _owner_reference(
        "biocatalyst.current_source_snapshot",
        current_owner,
        vocabulary["clock_classes"],
    )
    current["coverage_class"] = "record_history_complete"
    current["replay"].update(
        mode="historical_replay",
        code_revision="fixture-code",
        input_digest="5" * 64,
        vintage_state="owner_native",
    )
    _with_id(current)
    current_violations = set(combined_violations(current))
    assert {"coverage_class_not_owned", "replay_mode_not_owned"} <= current_violations
    with pytest.raises(EvidenceFoundationError):
        validate_reference(current)

    history_owner = vocabulary["owner_stores"]["biocatalyst.history_source_snapshot"]
    history = _owner_reference(
        "biocatalyst.history_source_snapshot",
        history_owner,
        vocabulary["clock_classes"],
    )
    history["coverage_class"] = "current_only"
    _with_id(history)
    assert "coverage_class_not_owned" in combined_violations(history)
    with pytest.raises(EvidenceFoundationError, match="coverage_class_not_owned"):
        validate_reference(history)


def test_duplicate_hostile_is_independence_only_and_not_fixed_by_disabling_effect(vocabulary: dict) -> None:
    hostile = _fixture("duplicate_corroboration_hostile.json")
    relation = hostile["relations"][0]
    assert relation["automatic_effect"] is False and relation["deterministic_key"] is None
    violations = set(combined_violations(hostile))
    assert "relation_0_independence_not_declarative:source_independence" in violations
    assert not {code for code in violations if "automatic" in code}


def _automatic_relation(reference: dict) -> dict:
    reference["relations"] = [{
        "target_reference_id": "efr_" + "1" * 64,
        "type": "exact_duplicate",
        "automatic_effect": True,
        "deterministic_key": "x",
        "independence": {
            axis: {"state": "not_assessed", "assessment": "declarative_unverified", "basis": "dedup identity does not assert independent evidence"}
            for axis in ("source_independence", "information_novelty", "mechanism_independence")
        },
    }]
    return _with_id(reference)


def test_v1_rejects_automatic_effect_even_for_exact_duplicate_with_arbitrary_key(
    schema: dict, vocabulary: dict
) -> None:
    relation_schema = schema["$defs"]["relation"]["properties"]
    assert relation_schema["automatic_effect"] == {"const": False}
    assert relation_schema["deterministic_key"] == {"type": "null"}
    valid = _owner_reference("theme_graph.evidence", vocabulary["owner_stores"]["theme_graph.evidence"], vocabulary["clock_classes"])
    hostile = _automatic_relation(valid)
    violations = set(combined_violations(hostile))
    assert "relation_0_automatic_effect_forbidden_v1" in violations
    assert "relation_0_deterministic_key_forbidden_v1" in violations
    assert any(code == "json_schema:relations.0.automatic_effect:const" for code in violations)
    assert any(code == "json_schema:relations.0.deterministic_key:type" for code in violations)


def test_correction_relations_equal_predecessors_with_the_right_kind(vocabulary: dict) -> None:
    valid = _fixture("correction_append_valid.json")
    assert validate_reference(valid) == valid
    assert valid["correction"]["chronology_state"] == "owner_clock_order_not_verified"
    cases = (
        (lambda value: value["relations"].clear(), "correction_relation_missing_target"),
        (lambda value: value["relations"][0].update(target_reference_id="efr_" + "3" * 64), "correction_relation_missing_target"),
        (lambda value: value["relations"][0].update(type="corrects"), "correction_relation_wrong_kind"),
        (lambda value: value["relations"].append({**deepcopy(value["relations"][0]), "target_reference_id": "efr_" + "4" * 64}), "correction_relation_extra_target"),
    )
    for mutate, expected in cases:
        hostile = deepcopy(valid)
        mutate(hostile)
        _with_id(hostile)
        assert expected in combined_violations(hostile)
    no_chronology = deepcopy(valid)
    del no_chronology["correction"]["chronology_state"]
    _with_id(no_chronology)
    assert combined_violations(no_chronology)


def test_replay_refuses_lookahead_and_distinguishes_recomputation(vocabulary: dict) -> None:
    valid = _fixture("replay_valid.json")
    hostile = _fixture("replay_lookahead_hostile.json")
    assert validate_reference(valid) == valid
    violations = set(combined_violations(hostile))
    assert "replay_lookahead:clocks.accepted_at" in violations
    assert "replay_lookahead:clocks.recorded_at" in violations
    mislabeled = deepcopy(valid)
    mislabeled["replay"]["vintage_state"] = "current_rule_recomputation"
    _with_id(mislabeled)
    assert "recomputation_mislabeled_replay" in combined_violations(mislabeled)


@pytest.mark.parametrize("field", ["clocks.accepted_at", "clocks.recorded_at"])
def test_historical_fif_replay_rejects_unknown_required_clocks(
    field: str, vocabulary: dict
) -> None:
    replay = _fixture("replay_valid.json")
    clock = next(item for item in replay["clocks"] if item["field"] == field)
    clock.update(value_state="unknown", value=None)
    _with_id(replay)
    assert (
        f"historical_replay_fif_clock_unknown:{field}"
        in combined_violations(replay)
    )


def test_historical_replay_rejects_unavailable_vintage(vocabulary: dict) -> None:
    replay = _fixture("replay_valid.json")
    replay["replay"]["vintage_state"] = "unavailable"
    _with_id(replay)
    assert "historical_replay_vintage_unavailable" in combined_violations(replay)


@pytest.mark.parametrize(
    ("owner_name", "field", "grain", "clock_value", "cutoff_value"),
    [
        (
            "institutional_13f.raw_receipt",
            "clocks.accepted_at",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "govrev.event.v2",
            "change.first_seen_at",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "govrev.event.v2",
            "change.last_seen_at",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "biocatalyst.current_source_snapshot",
            "first_seen_at",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "biocatalyst.current_source_snapshot",
            "source_dataset_timestamp_raw",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "biocatalyst.current_source_snapshot",
            "source_last_update_posted_at",
            "date",
            "2026-08-02",
            "2026-08-01",
        ),
        (
            "biocatalyst.current_source_snapshot",
            "valid_to",
            "date",
            "2026-08-02",
            "2026-08-01",
        ),
        (
            "biocatalyst.current_source_snapshot",
            "transaction_to",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
        (
            "biocatalyst.history_source_snapshot",
            "transaction_to",
            "datetime",
            "2026-08-02T00:00:00Z",
            "2026-08-01T23:59:59Z",
        ),
    ],
)
def test_source_backed_13f_govrev_and_biocatalyst_clocks_kill_cutoff_inversion(
    owner_name: str,
    field: str,
    grain: str,
    clock_value: str,
    cutoff_value: str,
    vocabulary: dict,
) -> None:
    owner = vocabulary["owner_stores"][owner_name]
    reference = _owner_reference(owner_name, owner, vocabulary["clock_classes"])
    clock = next(item for item in reference["clocks"] if item["field"] == field)
    clock.update(value_state="known", value=clock_value, grain=grain)
    reference["replay"].update(
        mode="historical_replay",
        code_revision="fixture-code",
        input_digest="5" * 64,
        vintage_state="owner_native",
    )
    reference["replay"]["cutoffs"][clock["class"]] = {
        "state": "known",
        "value": cutoff_value,
        "grain": grain,
    }
    _with_id(reference)
    assert f"replay_lookahead:{field}" in combined_violations(reference)


@pytest.mark.parametrize("clock_class", ["world_valid", "source_published", "knowable", "observed", "system_recorded", "belief_or_build", "review_due"])
def test_every_known_replay_cutoff_is_parsed_even_when_unused(clock_class: str, vocabulary: dict) -> None:
    valid = _fixture("fif_packet_valid.json")
    valid["replay"]["cutoffs"][clock_class] = {"state": "known", "value": "2026-02-31", "grain": "date"}
    _with_id(valid)
    assert f"replay_cutoff_invalid:{clock_class}" in combined_violations(valid)


def test_same_day_date_datetime_comparisons_are_ambiguous_symmetrically(vocabulary: dict) -> None:
    datetime_clock = _fixture("replay_valid.json")
    datetime_clock["replay"]["cutoffs"]["source_published"] = {"state": "known", "value": "2026-07-30", "grain": "date"}
    _with_id(datetime_clock)
    assert "replay_grain_ambiguous:clocks.accepted_at" in combined_violations(datetime_clock)
    owner = vocabulary["owner_stores"]["theme_graph.evidence"]
    date_clock = _owner_reference("theme_graph.evidence", owner, vocabulary["clock_classes"])
    published = next(clock for clock in date_clock["clocks"] if clock["field"] == "published_at")
    published.update(value_state="known", value="2026-07-30")
    date_clock["replay"].update(mode="historical_replay", code_revision="fixture-code", input_digest="5" * 64, vintage_state="owner_native")
    date_clock["replay"]["cutoffs"]["source_published"] = {"state": "known", "value": "2026-07-30T23:59:59Z", "grain": "datetime"}
    _with_id(date_clock)
    assert "replay_grain_ambiguous:published_at" in combined_violations(date_clock)


def test_typed_missingness_and_authority_never_default_up(vocabulary: dict) -> None:
    payload = _fixture("typed_missingness_valid.json")
    assert validate_reference(payload) == payload
    assert payload["missingness"] == {"state": "absent", "reason": "unsupported", "zero_substituted": False}
    zero = deepcopy(payload)
    zero["missingness"]["zero_substituted"] = True
    _with_id(zero)
    assert "missingness_zero_substitution" in combined_violations(zero)
    leak = _fixture("authority_leak_hostile.json")
    assert "authority_leak" in combined_violations(leak)
    absent = _fixture("fif_packet_valid.json")
    del absent["authority"]
    _with_id(absent)
    assert "authority_not_materialized" in combined_violations(absent)


def test_combined_validator_rejects_embedded_owner_body(vocabulary: dict) -> None:
    payload = _fixture("fif_packet_valid.json")
    payload["body"] = {"copied_owner_truth": True}
    _with_id(payload)
    violations = combined_violations(payload)
    assert any(code.startswith("json_schema:$:additionalProperties") for code in violations)
    with pytest.raises(EvidenceFoundationError):
        validate_reference(payload)


def test_reference_id_is_deterministic_and_has_no_join_write_clock() -> None:
    payload = _fixture("fif_packet_valid.json")
    assert compute_reference_id(payload) == payload["reference_id"]
    replayed = json.loads(json.dumps(payload, sort_keys=False))
    assert compute_reference_id(replayed) == payload["reference_id"]
    assert "join_recorded_at" not in payload and "join_as_of" not in payload


def test_k1_changed_file_inventory_creates_no_physical_mesh_store() -> None:
    assert isinstance(missing_dirs(ROOT), list)  # observed, never used as absence proof
    commands = (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        changed.update(result.stdout.splitlines())
    forbidden_prefixes = ("data/evidence_mesh/", "data/evidence_foundation/", "engine/evidence_mesh/")
    assert not [path for path in sorted(changed) if any(path.startswith(prefix) for prefix in forbidden_prefixes)]
