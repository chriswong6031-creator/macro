"""Bitemporal source-fact ledger contracts."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import localcontext
from hashlib import sha256

import pytest

import engine.fundamental_forensics.raw_ledger as raw_ledger_module
from engine.fundamental_forensics.raw_ledger import (
    AvailabilityStatus,
    canonical_json,
    decimal_text,
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    RawFactOccurrence,
    ReplayClock,
    SourceIdentity,
    TemporalClocks,
    VintagePolicy,
    make_raw_fact,
    not_evaluable,
)


def _fact(
    *,
    accession: str = "0001",
    body: str = "a" * 64,
    value: str = "100",
    accepted_at: str | None = "2025-02-01T12:00:00Z",
    recorded_at: str = "2025-02-02T12:00:00Z",
    mapping_available_at: str | None = None,
    computed_at: str | None = None,
    published_at: str | None = None,
    event_type: FactEventType = FactEventType.FILED,
    revision_of: str | None = None,
    member: str = "us-gaap:ConsolidationItemsMember",
    source_span: tuple[int, int] = (20, 23),
    decimals: str | None = None,
    precision: str | None = None,
    is_nil: bool = False,
    dimensions_known: bool = True,
    source_occurrence_key: str | None = None,
    occurrence_id: str | None = None,
    context_entity_identifier: str = "0000320193",
):
    return make_raw_fact(
        source=SourceIdentity(
            source="sec-edgar",
            entity_id="0000320193",
            accession=accession,
            document_id="aapl-10k.htm",
            body_sha256=body,
            source_url="https://www.sec.gov/Archives/example",
        ),
        concept_qname="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context=FactContext(
            context_id="ctx-current",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=context_entity_identifier,
            start="2024-01-01",
            end="2024-12-31",
            explicit_dimensions={"us-gaap:StatementBusinessSegmentsAxis": member},
            typed_dimensions={"example:ContractAxis": "<example:contract>all</example:contract>"},
        ),
        unit=FactUnit("usd", ["iso4217:USD"]),
        dimensions_known=dimensions_known,
        source_occurrence_key=source_occurrence_key,
        raw_token=None if is_nil else value,
        parsed_value=None if is_nil else value,
        is_nil=is_nil,
        source_span=source_span,
        decimals=decimals,
        precision=precision,
        accepted_at=accepted_at,
        recorded_at=recorded_at,
        mapping_available_at=mapping_available_at,
        computed_at=computed_at,
        published_at=published_at,
        event_type=event_type,
        revision_of=revision_of,
        occurrence_id=occurrence_id,
    )


def test_raw_occurrence_retains_context_unit_dimensions_source_and_all_clocks() -> None:
    fact = _fact(
        mapping_available_at="2025-02-03T12:00:00Z",
        computed_at="2025-02-04T12:00:00Z",
        published_at="2025-02-05T12:00:00Z",
    )

    assert fact.context.context_id == "ctx-current"  # document-local identity survives
    assert fact.context.semantic_key.startswith("context_")
    assert fact.unit and fact.unit.measures == ("iso4217:USD",)
    assert dict(fact.context.explicit_dimensions) == {
        "us-gaap:StatementBusinessSegmentsAxis": "us-gaap:ConsolidationItemsMember"
    }
    assert dict(fact.context.typed_dimensions) == {
        "example:ContractAxis": "<example:contract>all</example:contract>"
    }
    assert fact.source.accession == "0001"
    assert fact.parsed_value == "100"
    assert fact.accepted_at.isoformat().endswith("+00:00")
    assert fact.recorded_at.isoformat().endswith("+00:00")
    assert fact.mapping_available_at.isoformat().endswith("+00:00")
    assert fact.computed_at.isoformat().endswith("+00:00")
    assert fact.published_at.isoformat().endswith("+00:00")
    assert fact.clocks.system_ready_at == fact.published_at
    assert fact.to_dict()["source_span"] == [20, 23]
    assert fact.to_dict()["dimensions_known"] is True


def test_dimension_knowledge_is_serialized_and_changes_occurrence_identity() -> None:
    known = _fact(dimensions_known=True)
    unknown = _fact(dimensions_known=False)

    assert known.dimensions_known is True
    assert unknown.dimensions_known is False
    assert unknown.to_dict()["dimensions_known"] is False
    assert known.occurrence_id != unknown.occurrence_id
    assert known.logical_key == unknown.logical_key
    assert known.duplicate_group_key != unknown.duplicate_group_key


def test_occurrence_identity_binds_system_availability_clocks() -> None:
    first = _fact(recorded_at="2025-02-02T12:00:00Z")
    later_retained = _fact(recorded_at="2025-02-03T12:00:00Z")

    assert first.occurrence_id != later_retained.occurrence_id


def test_source_occurrence_key_discriminates_exact_rows_and_supplied_id_is_validated() -> None:
    first = _fact(source_occurrence_key="source-row:0")
    exact_repeat = _fact(source_occurrence_key="source-row:0")
    second = _fact(source_occurrence_key="source-row:1")

    assert first.occurrence_id == exact_repeat.occurrence_id
    assert first.occurrence_id != second.occurrence_id
    assert first.duplicate_group_key == second.duplicate_group_key
    assert first.to_dict()["source_occurrence_key"] == "source-row:0"
    assert (
        _fact(
            source_occurrence_key="source-row:0",
            occurrence_id=first.occurrence_id,
        ).occurrence_id
        == first.occurrence_id
    )
    with pytest.raises(ValueError, match="canonical occurrence identity"):
        _fact(source_occurrence_key="source-row:0", occurrence_id="forged")


def test_raw_occurrence_requires_source_and_context_entity_equality() -> None:
    with pytest.raises(ValueError, match="source entity_id"):
        _fact(context_entity_identifier="0000000001")


@pytest.mark.parametrize(
    "value",
    [
        "1e100000",
        "1e-100000",
        "1" * 100_001,
    ],
)
def test_decimal_canonicalization_bounds_source_and_fixed_point_expansion(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="bounded length"):
        decimal_text(value)


def test_source_identity_is_immutable_and_logical_key_excludes_value_and_document_vintage() -> None:
    original = _fact(accession="0001", body="a" * 64, value="100")
    recast = _fact(accession="0002", body="b" * 64, value="110")

    assert original.occurrence_id != recast.occurrence_id
    assert original.logical_key == recast.logical_key
    with pytest.raises(Exception):
        original.source.accession = "mutated"  # frozen canonical source identity


@pytest.mark.parametrize("digest", ["not-a-sha256", "A" * 64, "a" * 63])
def test_source_identity_requires_canonical_sha256(digest: str) -> None:
    with pytest.raises(ValueError, match="lowercase 64-hex"):
        SourceIdentity("sec-edgar", "0000320193", "0001", "doc.htm", digest)


def test_fact_unit_rejects_scalar_string_measures() -> None:
    with pytest.raises(TypeError, match="tuple or list"):
        FactUnit("usd", "iso4217:USD")
    with pytest.raises(TypeError, match="denominator measures"):
        FactUnit("usd-per-share", ["iso4217:USD"], "xbrli:shares")


def test_raw_identity_and_clock_text_inputs_have_hard_bounds() -> None:
    with pytest.raises(ValueError, match="bounded text length"):
        SourceIdentity(
            "x" * (raw_ledger_module.MAX_TEXT_CHARS + 1),
            "0000320193",
            "0001",
            "doc.htm",
            "a" * 64,
        )
    with pytest.raises(ValueError, match="bounded text length"):
        raw_ledger_module.parse_utc(
            "2" * (raw_ledger_module.MAX_UTC_TEXT_CHARS + 1),
            field_name="hostile_clock",
        )


def test_raw_occurrence_identity_fields_are_bounded_and_boolean_typed() -> None:
    fact = _fact()
    def mutate(**changes):
        return replace(fact, occurrence_id=None, **changes)

    assert mutate(raw_token="  source lexical form  ").raw_token == "  source lexical form  "

    with pytest.raises(ValueError, match="raw_token exceeds bounded text length"):
        mutate(raw_token="x" * (raw_ledger_module.MAX_RAW_TOKEN_BYTES + 1))
    with pytest.raises(ValueError, match="xml_lang exceeds bounded text length"):
        mutate(xml_lang="x" * (raw_ledger_module.MAX_TEXT_CHARS + 1))
    with pytest.raises(ValueError, match="inline_format exceeds bounded text length"):
        mutate(inline_format="x" * (raw_ledger_module.MAX_TEXT_CHARS + 1))
    with pytest.raises(TypeError, match="is_nil must be a boolean"):
        mutate(is_nil=1)
    with pytest.raises(TypeError, match="hidden must be a boolean"):
        mutate(hidden=1)
    with pytest.raises(ValueError, match="inline_scale must be an integer"):
        mutate(inline_scale=True)
    with pytest.raises(ValueError, match="inline_scale magnitude"):
        mutate(
            inline_scale=raw_ledger_module.MAX_XBRL_ACCURACY_MAGNITUDE + 1,
        )


def test_context_and_unit_inputs_are_bounded_without_rejecting_normal_typed_xml() -> None:
    def context(**kwargs):
        return FactContext(
            "ctx",
            "scheme",
            "entity",
            instant="2024-12-31",
            **kwargs,
        )

    def infinite_dimensions():
        index = 0
        while True:
            yield (f"axis-{index}", "member")
            index += 1

    class HostileItems(dict):
        def items(self):
            raise RuntimeError("hostile mapping items")

    class HostileNestedMember(dict):
        def items(self):
            raise RuntimeError("hostile nested mapping items")

    with pytest.raises(ValueError, match="bounded dimension pair count"):
        context(explicit_dimensions=infinite_dimensions())
    with pytest.raises(ValueError, match="iterable"):
        context(explicit_dimensions=HostileItems())
    with pytest.raises(ValueError, match="member mapping is not iterable"):
        context(typed_dimensions={"example:Axis": HostileNestedMember()})

    at_limit = context(
        explicit_dimensions=[
            (f"axis-{index}", f"member-{index}")
            for index in range(raw_ledger_module.MAX_DIMENSION_PAIRS)
        ]
    )
    assert len(at_limit.explicit_dimensions) == raw_ledger_module.MAX_DIMENSION_PAIRS
    with pytest.raises(ValueError, match="bounded dimension pair count"):
        context(
            explicit_dimensions=[
                (f"axis-{index}", f"member-{index}")
                for index in range(raw_ledger_module.MAX_DIMENSION_PAIRS + 1)
            ]
        )

    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="contains a cycle"):
        context(typed_dimensions={"example:Axis": cyclic})
    with pytest.raises(ValueError, match="bounded serialized size"):
        context(
            typed_dimensions={
                "example:Axis": {"payload": "x" * (raw_ledger_module.MAX_TYPED_DIMENSION_MEMBER_BYTES + 1)}
            }
        )

    typed_xml = "<example:member>" + ("x" * 8_192) + "</example:member>"
    preserved = context(typed_dimensions={"example:Axis": typed_xml})
    assert dict(preserved.typed_dimensions) == {"example:Axis": typed_xml}

    with pytest.raises(ValueError, match="bounded measure count"):
        FactUnit("too-many", [f"u:{index}" for index in range(raw_ledger_module.MAX_UNIT_MEASURES + 1)])

    class LyingInfiniteList(list):
        def __len__(self):
            return 0

        def __iter__(self):
            while True:
                yield "u:hostile"

    with pytest.raises(ValueError, match="bounded measure count"):
        FactUnit("hostile", LyingInfiniteList())


def test_context_validation_refuses_ambiguous_period_and_dimension_identity() -> None:
    with pytest.raises(ValueError, match="either instant or duration"):
        FactContext(
            "bad",
            "scheme",
            "entity",
            instant="2024-12-31",
            start="2024-01-01",
            end="2024-12-31",
        )
    with pytest.raises(ValueError, match="duplicate axis"):
        FactContext(
            "bad",
            "scheme",
            "entity",
            instant="2024-12-31",
            explicit_dimensions=[("axis", "a"), ("axis", "b")],
        )
    with pytest.raises(ValueError, match="both explicit and typed"):
        FactContext(
            "bad",
            "scheme",
            "entity",
            instant="2024-12-31",
            explicit_dimensions={"axis": "a"},
            typed_dimensions={"axis": "<a/>"},
        )


def test_clock_validation_rejects_naive_and_impossible_system_order() -> None:
    with pytest.raises(ValueError, match="timezone"):
        TemporalClocks(recorded_at="2025-02-02T12:00:00")
    with pytest.raises(ValueError, match="accepted_at cannot be after"):
        TemporalClocks(
            accepted_at="2025-02-03T12:00:00Z",
            recorded_at="2025-02-02T12:00:00Z",
        )
    with pytest.raises(ValueError, match="computed_at cannot precede"):
        TemporalClocks(
            accepted_at="2025-02-01T12:00:00Z",
            recorded_at="2025-02-02T12:00:00Z",
            mapping_available_at="2025-02-04T12:00:00Z",
            computed_at="2025-02-03T12:00:00Z",
        )


def test_revisions_append_without_overwriting_and_must_point_to_parent() -> None:
    original = _fact(accession="0001", value="100")
    amendment = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger().append(original)
    amended_ledger = ledger.append(amendment)

    assert ledger.events == (original,)
    assert amended_ledger.events == (original, amendment)
    assert amended_ledger.revision_chain(amendment.occurrence_id) == (original, amendment)
    with pytest.raises(ValueError, match="already exists"):
        amended_ledger.append(amendment)
    with pytest.raises(ValueError, match="must be appended after parent"):
        RawFactLedger((amendment,))


def test_extend_materializes_and_validates_one_immutable_batch(monkeypatch) -> None:
    original = _fact(accession="0001", value="100")
    amendment = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    base = RawFactLedger()
    original_validator = RawFactLedger.__post_init__
    validations = 0

    def counted_validator(self):
        nonlocal validations
        validations += 1
        original_validator(self)

    monkeypatch.setattr(RawFactLedger, "__post_init__", counted_validator)
    ledger = base.extend(item for item in (original, amendment))

    assert ledger.events == (original, amendment)
    assert validations == 1
    assert ledger.extend(()) is ledger
    with pytest.raises(ValueError, match="duplicate occurrence_id"):
        ledger.extend((amendment,))


def test_constructor_freezes_generator_once_and_bounds_hostile_iterables(
    monkeypatch,
) -> None:
    original = _fact(accession="0001", value="100")
    amendment = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger(item for item in (original, amendment))
    assert ledger.events == (original, amendment)

    class HostileIterable:
        def __iter__(self):
            raise RuntimeError("hostile iterator acquisition")

    with pytest.raises(TypeError, match="must be an iterable"):
        RawFactLedger(HostileIterable())

    monkeypatch.setattr(raw_ledger_module, "HARD_MAX_RAW_LEDGER_EVENTS", 2)

    def infinite_events():
        while True:
            yield original

    with pytest.raises(ValueError, match="exceeds bounded event count 2"):
        RawFactLedger(infinite_events())


def test_constructor_validates_long_revision_chain_in_one_parent_pass(
    monkeypatch,
) -> None:
    events = [_fact(accession="0000", body="0" * 64, value="100")]
    for index in range(1, 400):
        events.append(
            _fact(
                accession=f"{index:04d}",
                body=f"{index:064x}",
                value=str(100 + index),
                event_type=FactEventType.AMENDMENT,
                revision_of=events[-1].occurrence_id,
            )
        )

    revision_reads = 0

    def tracked_revision_of(self):
        nonlocal revision_reads
        revision_reads += 1
        return self.__dict__["revision_of"]

    monkeypatch.setattr(
        RawFactOccurrence,
        "revision_of",
        property(tracked_revision_of),
        raising=False,
    )
    ledger = RawFactLedger(tuple(events))

    assert ledger.events == tuple(events)
    assert revision_reads == len(events)


def test_revision_cannot_claim_a_different_economic_identity() -> None:
    original = _fact(accession="0001", value="100")
    wrong_dimension_revision = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
        member="us-gaap:EuropeSegmentMember",
    )
    with pytest.raises(ValueError, match="preserve its economic logical_key"):
        RawFactLedger((original, wrong_dimension_revision))


def test_revision_source_clock_cannot_precede_parent_but_backfill_recording_can() -> None:
    original = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-04-01T12:00:00Z",
    )
    impossible_revision = _fact(
        accession="0002",
        body="f" * 64,
        value="110",
        accepted_at="2025-02-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )

    with pytest.raises(ValueError, match="accepted_at cannot precede a known ancestor"):
        RawFactLedger((original, impossible_revision))

    legitimate_backfill = _fact(
        accession="0003",
        body="b" * 64,
        value="120",
        accepted_at="2025-03-15T12:00:00Z",
        recorded_at="2025-03-16T12:00:00Z",
        event_type=FactEventType.COMPARATIVE_RECAST,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, legitimate_backfill))
    before_parent = ledger.select_first_system_known(
        original.logical_key, as_of="2025-03-20T00:00:00Z"
    )
    absent = RawFactLedger().select_first_system_known(
        original.logical_key,
        as_of="2025-03-20T00:00:00Z",
    )
    after_parent = ledger.select_first_system_known(
        original.logical_key,
        as_of="2025-04-02T00:00:00Z",
    )
    latest_after_parent = ledger.select_latest(
        original.logical_key,
        as_of="2025-04-02T00:00:00Z",
        clock="system",
    )

    assert before_parent.to_dict() == absent.to_dict()
    assert before_parent.candidate_occurrence_ids == ()
    assert after_parent.occurrence is legitimate_backfill
    assert latest_after_parent.occurrence is legitimate_backfill


def test_source_replay_requires_a_fully_dated_revision_lineage() -> None:
    root = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-02-01T12:00:00Z",
    )
    undated_middle = _fact(
        accession="0002",
        body="e" * 64,
        value="110",
        accepted_at=None,
        recorded_at="2025-02-02T12:00:00Z",
        event_type=FactEventType.AMENDMENT,
        revision_of=root.occurrence_id,
    )
    leaf = _fact(
        accession="0003",
        body="f" * 64,
        value="120",
        accepted_at="2025-01-15T12:00:00Z",
        recorded_at="2025-02-03T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=undated_middle.occurrence_id,
    )
    ledger = RawFactLedger((root, undated_middle, leaf))

    source = ledger.select_latest(
        root.logical_key,
        as_of="2025-01-20T00:00:00Z",
        clock="source_event",
    )
    system = ledger.select_latest(
        root.logical_key,
        as_of="2025-02-04T00:00:00Z",
        clock="system",
    )
    assert source.status is AvailabilityStatus.AVAILABLE
    assert source.occurrence is root
    assert system.status is AvailabilityStatus.AVAILABLE
    assert system.occurrence is leaf

    impossible_leaf = _fact(
        accession="0004",
        body="d" * 64,
        value="130",
        accepted_at="2024-12-15T12:00:00Z",
        recorded_at="2025-02-04T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=undated_middle.occurrence_id,
    )
    with pytest.raises(ValueError, match="accepted_at cannot precede a known ancestor"):
        RawFactLedger((root, undated_middle, impossible_leaf))


def test_original_latest_and_as_of_are_all_cutoff_bounded_on_source_clock() -> None:
    original = _fact(accession="0001", value="100")
    recast = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.COMPARATIVE_RECAST,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, recast))

    before_recast = ledger.select(
        original.logical_key,
        as_of="2025-02-15T00:00:00Z",
        clock=ReplayClock.SOURCE_EVENT,
        policy=VintagePolicy.AS_OF,
    )
    latest = ledger.select(
        original.logical_key,
        as_of="2025-04-01T00:00:00Z",
        clock="source_event",
        policy="latest",
    )
    original_view = ledger.select(
        original.logical_key,
        as_of="2025-04-01T00:00:00Z",
        clock="source_event",
        policy="original",
    )

    assert before_recast.occurrence is original
    assert latest.occurrence is recast
    assert original_view.occurrence is original


def test_system_view_never_leaks_source_revision_before_mapping_compute_publish() -> None:
    original = _fact(accession="0001", value="100")
    recast = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        mapping_available_at="2025-04-01T12:00:00Z",
        computed_at="2025-04-02T12:00:00Z",
        published_at="2025-04-03T12:00:00Z",
        event_type=FactEventType.COMPARATIVE_RECAST,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, recast))

    source = ledger.select(
        original.logical_key,
        as_of="2025-03-15T00:00:00Z",
        clock="source_event",
        policy="as_of",
    )
    system_before = ledger.select(
        original.logical_key,
        as_of="2025-03-15T00:00:00Z",
        clock="system",
        policy="as_of",
    )
    system_after = ledger.select(
        original.logical_key,
        as_of="2025-04-04T00:00:00Z",
        clock="system",
        policy="latest",
    )

    assert source.occurrence is recast
    assert system_before.occurrence is original
    assert system_after.occurrence is recast


def test_undated_source_is_opaque_for_source_replay_but_system_usable() -> None:
    fact = _fact(accepted_at=None, recorded_at="2025-02-02T12:00:00Z")
    ledger = RawFactLedger((fact,))

    source = ledger.select(fact.logical_key, as_of="2025-03-01T00:00:00Z", clock="source_event")
    system = ledger.select(fact.logical_key, as_of="2025-03-01T00:00:00Z", clock="system")

    assert source.status is AvailabilityStatus.NOT_AVAILABLE
    assert source.to_dict() == RawFactLedger().select(
        fact.logical_key,
        as_of="2025-03-01T00:00:00Z",
        clock="source_event",
    ).to_dict()
    assert system.status is AvailabilityStatus.AVAILABLE
    assert system.occurrence is fact


def test_not_evaluable_is_a_first_class_result_not_a_missing_numeric_value() -> None:
    outcome = not_evaluable(
        clock="system",
        policy="as_of",
        as_of="2025-03-01T00:00:00Z",
        logical_key="test-key",
        reason="inconsistent duplicate facts",
        candidate_occurrence_ids=("one", "two"),
    )

    assert outcome.status is AvailabilityStatus.NOT_EVALUABLE
    assert outcome.occurrence is None
    assert outcome.reason == "inconsistent duplicate facts"
    assert outcome.to_dict()["candidate_occurrence_ids"] == ["one", "two"]


def test_linear_same_time_revision_uses_lineage_depth_not_hash_order() -> None:
    original = _fact(accession="0001", body="a" * 64, value="100")
    recast = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, recast))
    selected = ledger.select(original.logical_key, as_of="2025-03-01T00:00:00Z")

    assert selected.occurrence is recast
    assert selected.as_of == datetime(2025, 3, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("policy", ["as_of", "source_original"])
def test_equal_precedence_unlinked_roots_are_ambiguous(policy: str) -> None:
    first = _fact(accession="0001", body="a" * 64, value="100")
    second = _fact(accession="0002", body="b" * 64, value="110")
    selected = RawFactLedger((first, second)).select(
        first.logical_key,
        as_of="2025-03-01T00:00:00Z",
        policy=policy,
    )

    assert selected.status is AvailabilityStatus.NOT_EVALUABLE
    assert "equal semantic precedence" in selected.reason
    assert set(selected.candidate_occurrence_ids) == {
        first.occurrence_id,
        second.occurrence_id,
    }


def test_equal_precedence_sibling_revisions_are_ambiguous() -> None:
    root = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-01-02T12:00:00Z",
    )
    first = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-02-01T12:00:00Z",
        recorded_at="2025-02-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=root.occurrence_id,
    )
    second = _fact(
        accession="0003",
        body="c" * 64,
        value="120",
        accepted_at="2025-02-01T12:00:00Z",
        recorded_at="2025-02-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=root.occurrence_id,
    )
    selected = RawFactLedger((root, first, second)).select_latest(
        root.logical_key,
        as_of="2025-03-01T00:00:00Z",
    )

    assert selected.status is AvailabilityStatus.NOT_EVALUABLE
    assert set(selected.candidate_occurrence_ids) == {
        first.occurrence_id,
        second.occurrence_id,
    }


def test_equal_precedence_revision_and_withdrawal_are_ambiguous() -> None:
    root = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-01-02T12:00:00Z",
    )
    revision = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-02-01T12:00:00Z",
        recorded_at="2025-02-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=root.occurrence_id,
    )
    withdrawal = _fact(
        accession="0003",
        body="c" * 64,
        value="0",
        is_nil=True,
        accepted_at="2025-02-01T12:00:00Z",
        recorded_at="2025-02-02T12:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=root.occurrence_id,
    )
    selected = RawFactLedger((root, revision, withdrawal)).select_latest(
        root.logical_key,
        as_of="2025-03-01T00:00:00Z",
    )

    assert selected.status is AvailabilityStatus.NOT_EVALUABLE
    assert set(selected.candidate_occurrence_ids) == {
        revision.occurrence_id,
        withdrawal.occurrence_id,
    }


def test_selection_candidate_ids_include_only_replay_eligible_occurrences() -> None:
    root = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-01-02T12:00:00Z",
    )
    future = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=root.occurrence_id,
    )
    undated = _fact(
        accession="0003",
        body="c" * 64,
        value="90",
        accepted_at=None,
        recorded_at="2025-01-03T12:00:00Z",
    )
    ledger = RawFactLedger((root, future, undated))

    selected = ledger.select_latest(
        root.logical_key,
        as_of="2025-02-01T00:00:00Z",
        clock="source_event",
    )
    before_everything = ledger.select_latest(
        root.logical_key,
        as_of="2024-12-01T00:00:00Z",
        clock="source_event",
    )

    assert selected.occurrence is root
    assert selected.candidate_occurrence_ids == (root.occurrence_id,)
    assert before_everything.status is AvailabilityStatus.NOT_AVAILABLE
    assert before_everything.candidate_occurrence_ids == ()


@pytest.mark.parametrize("clock", ["source_event", "system"])
def test_source_original_does_not_reveal_future_root_multiplicity(clock: str) -> None:
    first = _fact(
        accession="0001",
        body="a" * 64,
        value="100",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
    )
    second = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
    )
    one_future_root = RawFactLedger((first,)).select(
        first.logical_key,
        as_of="2025-02-01T00:00:00Z",
        clock=clock,
        policy="source_original",
    )
    two_future_roots = RawFactLedger((first, second)).select(
        first.logical_key,
        as_of="2025-02-01T00:00:00Z",
        clock=clock,
        policy="source_original",
    )
    absent = RawFactLedger().select(
        first.logical_key,
        as_of="2025-02-01T00:00:00Z",
        clock=clock,
        policy="source_original",
    )

    assert one_future_root.to_dict() == two_future_roots.to_dict() == absent.to_dict()
    assert one_future_root.candidate_occurrence_ids == ()


def test_conflicting_duplicate_occurrences_are_not_evaluable_but_precision_equivalents_are() -> None:
    first = _fact(accession="0001", body="d" * 64, value="100", source_span=(5, 8))
    conflicting = _fact(accession="0001", body="d" * 64, value="999", source_span=(50, 53))
    conflict = RawFactLedger((first, conflicting)).select(
        first.logical_key,
        as_of="2025-03-01T00:00:00Z",
    )

    rounded_first = _fact(
        accession="0002", body="e" * 64, value="100", decimals="0", source_span=(50, 53)
    )
    rounded_second = _fact(
        accession="0002", body="e" * 64, value="101", decimals="0", source_span=(5, 8)
    )
    rounded = RawFactLedger((rounded_first, rounded_second)).select(
        rounded_first.logical_key,
        as_of="2025-03-01T00:00:00Z",
    )
    precision_first = _fact(
        accession="0003", body="c" * 64, value="100", precision="2", source_span=(5, 8)
    )
    precision_second = _fact(
        accession="0003", body="c" * 64, value="101", precision="2", source_span=(50, 53)
    )
    precision = RawFactLedger((precision_first, precision_second)).select(
        precision_first.logical_key,
        as_of="2025-03-01T00:00:00Z",
    )

    assert conflict.status is AvailabilityStatus.NOT_EVALUABLE
    assert "conflicting duplicate" in conflict.reason
    assert rounded.status is AvailabilityStatus.AVAILABLE
    assert rounded.occurrence is rounded_second  # earliest source span, not insertion order/value
    assert precision.status is AvailabilityStatus.AVAILABLE


def test_duplicate_agreement_uses_a_fixed_decimal_context_and_linear_intervals(
    monkeypatch,
) -> None:
    first = _fact(
        accession="0001",
        body="d" * 64,
        value="100",
        decimals="100",
        source_span=(1, 2),
        source_occurrence_key="row-0",
    )
    second = _fact(
        accession="0001",
        body="d" * 64,
        value="100",
        decimals="100",
        source_span=(3, 4),
        source_occurrence_key="row-1",
    )
    with localcontext() as ambient:
        ambient.prec = 1
        ambient.Emin = -10
        ambient.Emax = 10
        selected = RawFactLedger((first, second)).select(
            first.logical_key,
            as_of="2025-03-01T00:00:00Z",
        )
    assert selected.status is AvailabilityStatus.AVAILABLE
    assert str(raw_ledger_module._rounding_tolerance(first)) == "5E-101"

    facts = tuple(
        _fact(
            accession="0002",
            body="e" * 64,
            value="100",
            decimals="0",
            source_span=(index, index + 1),
            source_occurrence_key=f"duplicate-{index}",
        )
        for index in range(500)
    )
    original_interval = raw_ledger_module._duplicate_interval
    interval_calls = 0

    def counted_interval(item):
        nonlocal interval_calls
        interval_calls += 1
        return original_interval(item)

    monkeypatch.setattr(raw_ledger_module, "_duplicate_interval", counted_interval)
    assert raw_ledger_module._duplicates_agree(facts) is True
    assert interval_calls == len(facts)


def test_select_all_reuses_the_frozen_logical_key_index(monkeypatch) -> None:
    count = 300
    events = tuple(
        _fact(
            accession=f"{index:04d}",
            body=f"{index:064x}",
            value=str(index + 1),
            member=f"example:Member{index}",
            source_occurrence_key=f"row-{index}",
        )
        for index in range(count)
    )
    original_logical_key = RawFactOccurrence.logical_key
    logical_key_reads = 0

    def counted_logical_key(self):
        nonlocal logical_key_reads
        logical_key_reads += 1
        return original_logical_key.fget(self)

    monkeypatch.setattr(
        RawFactOccurrence,
        "logical_key",
        property(counted_logical_key),
    )
    ledger = RawFactLedger(events)
    logical_key_reads = 0

    selected = ledger.select_all(as_of="2025-03-01T00:00:00Z")

    assert len(selected) == count
    assert all(item.status is AvailabilityStatus.AVAILABLE for item in selected)
    # select_all may inspect each supplied key, but must never re-scan every
    # event once per logical key.
    assert logical_key_reads <= count * 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decimals", "999999999999999999999", "decimals magnitude"),
        ("decimals", "-999999999999999999999", "decimals magnitude"),
        ("precision", "999999999999999999999", "positive bounded"),
    ],
)
def test_xbrl_accuracy_metadata_is_bounded_before_decimal_arithmetic(
    field: str, value: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _fact(**{field: value})


def test_withdrawn_tombstone_is_not_available_while_history_is_preserved() -> None:
    original = _fact(accession="0001", value="100")
    withdrawn = _fact(
        accession="0002",
        body="0" * 64,
        value="0",
        is_nil=True,
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, withdrawn))
    selected = ledger.select(original.logical_key, as_of="2025-04-01T00:00:00Z")

    assert ledger.events == (original, withdrawn)
    assert selected.status is AvailabilityStatus.NOT_AVAILABLE
    assert "withdrawn" in selected.reason


def test_system_batch_ties_preserve_revision_and_withdrawal_order() -> None:
    shared_system_clocks = {
        "recorded_at": "2025-04-01T12:00:00Z",
        "mapping_available_at": "2025-04-01T12:00:00Z",
        "computed_at": "2025-04-02T12:00:00Z",
        "published_at": "2025-04-03T12:00:00Z",
    }
    original = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        **shared_system_clocks,
    )
    restatement = _fact(
        accession="0002",
        body="f" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
        **shared_system_clocks,
    )
    revised = RawFactLedger((original, restatement)).select_latest(
        original.logical_key,
        as_of="2025-04-04T00:00:00Z",
        clock="system",
    )
    assert revised.status is AvailabilityStatus.AVAILABLE
    assert revised.occurrence is restatement

    withdrawn = _fact(
        accession="0003",
        body="0" * 64,
        value="0",
        is_nil=True,
        accepted_at="2025-03-15T12:00:00Z",
        event_type=FactEventType.WITHDRAWN,
        revision_of=restatement.occurrence_id,
        **shared_system_clocks,
    )
    tombstoned = RawFactLedger((original, restatement, withdrawn)).select_latest(
        original.logical_key,
        as_of="2025-04-04T00:00:00Z",
        clock="system",
    )
    assert tombstoned.status is AvailabilityStatus.NOT_AVAILABLE
    assert "withdrawn" in tombstoned.reason


def test_system_batch_ties_use_recorded_time_for_first_known_and_undated_sources() -> None:
    common_late_clocks = {
        "mapping_available_at": "2025-04-01T12:00:00Z",
        "computed_at": "2025-04-02T12:00:00Z",
        "published_at": "2025-04-03T12:00:00Z",
    }
    backfilled_root = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-04-01T12:00:00Z",
        **common_late_clocks,
    )
    retained_first = _fact(
        accession="0002",
        body="f" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.COMPARATIVE_RECAST,
        revision_of=backfilled_root.occurrence_id,
        **common_late_clocks,
    )
    dated_ledger = RawFactLedger((backfilled_root, retained_first))
    first = dated_ledger.select_first_system_known(
        backfilled_root.logical_key, as_of="2025-04-04T00:00:00Z"
    )
    latest = dated_ledger.select_latest(
        backfilled_root.logical_key,
        as_of="2025-04-04T00:00:00Z",
        clock="system",
    )
    assert first.occurrence is retained_first
    assert latest.occurrence is retained_first

    root = _fact(
        accession="0003",
        body="d" * 64,
        value="200",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-01-02T12:00:00Z",
        **common_late_clocks,
    )
    undated_correction = _fact(
        accession="0004",
        body="e" * 64,
        value="210",
        accepted_at=None,
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.PARSER_CORRECTION,
        revision_of=root.occurrence_id,
        **common_late_clocks,
    )
    undated_ledger = RawFactLedger((root, undated_correction))
    assert undated_ledger.select_first_system_known(
        root.logical_key, as_of="2025-04-04T00:00:00Z"
    ).occurrence is root
    assert undated_ledger.select_latest(
        root.logical_key, as_of="2025-04-04T00:00:00Z", clock="system"
    ).occurrence is undated_correction


def test_source_original_and_first_system_known_are_explicitly_different_policies() -> None:
    original = _fact(
        accession="0001",
        value="100",
        accepted_at="2025-01-01T12:00:00Z",
        recorded_at="2025-04-01T12:00:00Z",
    )
    recast = _fact(
        accession="0002",
        body="f" * 64,
        value="110",
        accepted_at="2025-03-01T12:00:00Z",
        recorded_at="2025-03-02T12:00:00Z",
        event_type=FactEventType.COMPARATIVE_RECAST,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, recast))

    source_original = ledger.select(
        original.logical_key,
        as_of="2025-05-01T00:00:00Z",
        clock="system",
        policy="source_original",
    )
    legacy_original = ledger.select(
        original.logical_key,
        as_of="2025-05-01T00:00:00Z",
        clock="system",
        policy="original",
    )
    first_system = ledger.select_first_system_known(
        original.logical_key,
        as_of="2025-05-01T00:00:00Z",
    )
    source_original_before_retention = ledger.select(
        original.logical_key,
        as_of="2025-03-15T00:00:00Z",
        clock="system",
        policy="source_original",
    )
    invalid_clock = ledger.select(
        original.logical_key,
        as_of="2025-05-01T00:00:00Z",
        clock="source_event",
        policy="first_system_known",
    )

    assert source_original.occurrence is original
    assert source_original_before_retention.status is AvailabilityStatus.NOT_AVAILABLE
    assert legacy_original.occurrence is original
    assert source_original.policy is VintagePolicy.SOURCE_ORIGINAL
    assert first_system.occurrence is recast
    assert first_system.policy is VintagePolicy.FIRST_SYSTEM_KNOWN
    assert invalid_clock.status is AvailabilityStatus.NOT_EVALUABLE


def test_source_vintage_uses_system_only_as_visibility_gate_and_keeps_future_backfills_opaque() -> None:
    visible_root = _fact(
        accession="0001",
        body="a" * 64,
        value="100",
        accepted_at="2021-01-01T12:00:00Z",
        recorded_at="2025-01-02T12:00:00Z",
    )
    hidden_older_root = _fact(
        accession="0002",
        body="b" * 64,
        value="90",
        accepted_at="2020-01-01T12:00:00Z",
        recorded_at="2026-01-02T12:00:00Z",
    )
    hidden_future_revision = _fact(
        accession="0003",
        body="c" * 64,
        value="105",
        accepted_at="2022-01-01T12:00:00Z",
        recorded_at="2026-01-03T12:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=visible_root.occurrence_id,
    )
    cutoff = "2025-06-01T00:00:00Z"
    before = RawFactLedger((visible_root,)).select_original(
        visible_root.logical_key,
        as_of=cutoff,
        clock="system",
    )
    after = RawFactLedger(
        (visible_root, hidden_older_root, hidden_future_revision)
    ).select_original(
        visible_root.logical_key,
        as_of=cutoff,
        clock="system",
    )
    before_payload = before.to_dict()
    after_payload = after.to_dict()

    assert before.occurrence is visible_root
    assert after.occurrence is visible_root
    assert before.occurrence.parsed_value == after.occurrence.parsed_value == "100"
    assert before.occurrence.occurrence_id == after.occurrence.occurrence_id
    assert before.candidate_occurrence_ids == after.candidate_occurrence_ids
    assert after_payload == before_payload
    assert sha256(canonical_json(after_payload).encode("utf-8")).hexdigest() == sha256(
        canonical_json(before_payload).encode("utf-8")
    ).hexdigest()
    # Source-event replay deliberately reconstructs SEC event history rather
    # than system knowledge, so the retained historical source root is now
    # source-visible despite its later recording clock.
    source_event = RawFactLedger(
        (visible_root, hidden_older_root, hidden_future_revision)
    ).select_original(
        visible_root.logical_key,
        as_of=cutoff,
        clock="source_event",
    )
    assert source_event.occurrence is hidden_older_root


@pytest.mark.parametrize("policy", [VintagePolicy.LATEST, VintagePolicy.AS_OF])
def test_system_latest_and_as_of_keep_source_vintage_order_after_visibility_gating(
    policy: VintagePolicy,
) -> None:
    older_source_retained_late = _fact(
        accession="0001",
        body="a" * 64,
        value="100",
        accepted_at="2024-01-01T12:00:00Z",
        recorded_at="2025-05-01T12:00:00Z",
    )
    newer_source_retained_earlier = _fact(
        accession="0002",
        body="b" * 64,
        value="110",
        accepted_at="2024-03-01T12:00:00Z",
        recorded_at="2024-03-02T12:00:00Z",
    )
    selected = RawFactLedger(
        (older_source_retained_late, newer_source_retained_earlier)
    ).select(
        older_source_retained_late.logical_key,
        as_of="2025-06-01T00:00:00Z",
        clock="system",
        policy=policy,
    )

    assert selected.status is AvailabilityStatus.AVAILABLE
    assert selected.occurrence is newer_source_retained_earlier


def test_rejects_binary_floats_numeric_facts_without_units_and_nondeterministic_set_identity() -> None:
    with pytest.raises(ValueError, match="binary float"):
        decimal_text(0.1 + 0.2)
    with pytest.raises(ValueError, match="numeric facts require a unit"):
        make_raw_fact(
            source=SourceIdentity("sec", "0000320193", "0001", "doc", "a" * 64),
            concept_qname="us-gaap:Revenue",
            context=FactContext("ctx", "cik", "0000320193", instant="2024-12-31"),
            raw_token="100",
            parsed_value="100",
            accepted_at="2025-02-01T12:00:00Z",
            recorded_at="2025-02-02T12:00:00Z",
        )
    left = canonical_json({"members": {"gamma", "alpha", "beta"}})
    right = canonical_json({"members": {"beta", "gamma", "alpha"}})

    assert left == right == '{"members":["alpha","beta","gamma"]}'
