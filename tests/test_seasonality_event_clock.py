"""Tests for the dark, pure, fail-closed event-clock adapter.

Every fixture in ``tests/fixtures/seasonality/event_clock/`` is synthetic and
non-publishable, and the corpus is asserted to be so below.  No test here
introduces an issuer map: the one accept path is exercised by injecting an
obviously synthetic resolver, and the same rows are re-read with the shipped
default to prove the default refuses them.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
import random
import re

import pytest

from engine.seasonality import contracts
from engine.seasonality.event_clock import (
    EVENT_CLOCK_READ_SCHEMA,
    EXPECTED_PROJECTION_CONTRACT,
    EXPECTED_PROJECTION_SCHEMA_VERSION,
    FORBIDDEN_AUTHORITY_FIELDS,
    MAX_NATIVE_ID_CHARS,
    MAX_PROJECTION_BYTES,
    MAX_PROJECTION_DEPTH,
    MAX_REVISION_INDEX,
    MAX_SOURCE_TEXT_CHARS,
    QUARANTINE_REASON_CODES,
    canonical_projection_bytes,
    derive_event_id,
    read_event_projection,
    resolve_issuer_unavailable,
)
from engine.seasonality.event_clock import _ROW_REQUIRED_KEYS

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "seasonality" / "event_clock"
MODULE_SOURCE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "engine" / "seasonality" / "event_clock.py"
)

SYNTHETIC_ISSUER = "SYNTHETIC_ISSUER_0001"


def synthetic_resolver(row):
    """An obviously fake identity authority — never a real ticker map.

    It resolves every row to one constant string that could not be mistaken for
    an issuer identifier.  The point of the accept-path tests is the temporal
    and authority machinery, not identity, and wiring a real map here is what
    would quietly turn a test fixture into a production shortcut.
    """
    assert isinstance(row, dict)
    return SYNTHETIC_ISSUER


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def read(name: str, **kwargs):
    kwargs.setdefault("resolve_issuer", synthetic_resolver)
    return read_event_projection(load(name), **kwargs)


def reasons(result) -> list[str]:
    return [entry["reason_code"] for entry in result["quarantined"]]


def repack(envelope: dict) -> bytes:
    """Re-sign a mutated envelope so a test can target one field at a time."""
    payload = {key: value for key, value in envelope.items() if key != "packet_hash"}
    payload["packet_hash"] = __import__("hashlib").sha256(
        canonical_projection_bytes(payload)
    ).hexdigest()
    return json.dumps(payload).encode("utf-8")


def envelope_of(name: str) -> dict:
    return json.loads(load(name).decode("utf-8"))


# ---------------------------------------------------------------------------
# the fixture corpus itself
# ---------------------------------------------------------------------------


def test_fixture_corpus_is_marked_synthetic_and_unpublishable():
    files = sorted(FIXTURES.glob("*.json"))
    assert files, "the adversarial fixture corpus is missing"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("fixture_only") is True, path.name
        assert payload.get("publishable") is False, path.name


def test_every_required_adversarial_case_has_a_named_fixture():
    required = {
        "null_publication_time.json",
        "future_effective_date.json",
        "after_hours_effective_time.json",
        "month_precision.json",
        "quarter_precision.json",
        "year_precision.json",
        "range_precision.json",
        "scheduled_window.json",
        "unparsed_published_value.json",
        "correction_revision.json",
        "conflicting_revisions.json",
        "unresolved_issuer.json",
        "duplicate_event.json",
        "corrupt_source_hash.json",
        "unknown_schema_version.json",
        "unknown_contract_id.json",
        "stale_generation.json",
        "path_traversal_source_uri.json",
        "oversized_payload.json",
        "replay_determinism_pair_a.json",
        "replay_determinism_pair_b.json",
        "success_identity_resolved.json",
    }
    present = {path.name for path in FIXTURES.glob("*.json")}
    assert required <= present, sorted(required - present)


# ---------------------------------------------------------------------------
# purity / determinism
# ---------------------------------------------------------------------------


def test_module_source_contains_no_impure_calls():
    source = MODULE_SOURCE_PATH.read_text(encoding="utf-8")
    banned = (
        ".now(",
        "utcnow",
        "time.time",
        "import time",
        "monotonic",
        "perf_counter",
        "time_ns",
        "random",
        "uuid",
        "os.environ",
        "getenv",
        "open(",
        "Path(",
        "pathlib",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "subprocess",
        "secrets",
        "input(",
    )
    offenders = [token for token in banned if token in source]
    assert offenders == [], f"event_clock.py is not pure: {offenders}"


#: Call targets that read a clock, an address, or an entropy source.  The
#: substring sweep above only catches the spellings someone remembered; this
#: set is checked against the parsed call graph, where a name cannot hide
#: behind a different prefix.
IMPURE_CALL_NAMES = frozenset(
    {
        "now",
        "today",
        "utcnow",
        "fromtimestamp",
        "utcfromtimestamp",
        "time",
        "time_ns",
        "monotonic",
        "monotonic_ns",
        "perf_counter",
        "perf_counter_ns",
        "process_time",
        "id",
        "hash",
        "open",
        "getenv",
        "urandom",
        "token_hex",
        "token_bytes",
    }
)


def test_module_makes_no_impure_call_anywhere_in_its_parsed_call_graph():
    """An AST sweep, because the substring blacklist above is evadable.

    ``datetime.today()`` is a real wall-clock read that the banned-token tuple
    never mentioned: dropping it into this module left the suite green.  Names
    are read off the parsed tree here, so a clock call cannot be smuggled in
    under a spelling nobody thought to enumerate — and ``id``/``hash`` are
    included because either one turns a pure reader nondeterministic across
    processes.
    """
    tree = ast.parse(MODULE_SOURCE_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name in IMPURE_CALL_NAMES:
            offenders.append(f"{name}() at line {node.lineno}")
    assert offenders == [], f"event_clock.py is not pure: {offenders}"


def test_module_imports_are_stdlib_or_the_frozen_sibling_contract():
    source = MODULE_SOURCE_PATH.read_text(encoding="utf-8")
    lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    allowed_stdlib = {"hashlib", "json", "re", "datetime", "typing", "__future__"}
    for line in lines:
        module = line.split()[1]
        assert module in allowed_stdlib or module == ".contracts", line


def test_replay_on_identical_bytes_is_byte_identical():
    payload = load("mixed_batch.json")
    first = read_event_projection(payload, resolve_issuer=synthetic_resolver)
    second = read_event_projection(payload, resolve_issuer=synthetic_resolver)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_replay_pair_agrees_across_two_serialisations():
    """Two byte-different serialisations of one envelope read the same.

    ``generation.content_hash`` is a digest of the injected *bytes* by design,
    so it is the one field allowed to differ; everything the reader concluded
    must not.
    """
    a = read("replay_determinism_pair_a.json")
    b = read("replay_determinism_pair_b.json")
    assert load("replay_determinism_pair_a.json") != load("replay_determinism_pair_b.json")
    assert a["generation"]["content_hash"] != b["generation"]["content_hash"]
    for result in (a, b):
        result["generation"] = {
            key: value for key, value in result["generation"].items() if key != "content_hash"
        }
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_row_order_does_not_change_the_accepted_set():
    envelope = envelope_of("mixed_batch.json")
    straight = read_event_projection(load("mixed_batch.json"), resolve_issuer=synthetic_resolver)

    shuffler = random.Random(20260806)
    rows = list(envelope["rows"])
    shuffler.shuffle(rows)
    assert rows != envelope["rows"]
    envelope["rows"] = rows
    shuffled = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)

    def content_hashes(result):
        return sorted(contracts.event_v2_content_hash(event) for event in result["accepted"])

    assert content_hashes(straight) == content_hashes(shuffled)
    assert straight["counts"] == shuffled["counts"]
    # The ledger still points at real positions, which necessarily moved.
    assert sorted(reasons(straight)) == sorted(reasons(shuffled))
    assert [entry["row_index"] for entry in straight["quarantined"]] != [
        entry["row_index"] for entry in shuffled["quarantined"]
    ]


def test_event_ids_survive_a_shuffle():
    envelope = envelope_of("mixed_batch.json")
    straight = [event["event_id"] for event in read("mixed_batch.json")["accepted"]]
    envelope["rows"] = list(reversed(envelope["rows"]))
    reversed_result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert [event["event_id"] for event in reversed_result["accepted"]] == straight


# ---------------------------------------------------------------------------
# conservation
# ---------------------------------------------------------------------------


def test_conservation_invariant_holds_on_a_mixed_batch():
    result = read("mixed_batch.json")
    counts = result["counts"]
    assert counts["input_rows"] == 6
    assert counts["accepted"] == 2
    assert counts["quarantined"] == 4
    assert counts["accepted"] + counts["quarantined"] == counts["input_rows"]
    assert len(result["accepted"]) == counts["accepted"]
    assert len(result["quarantined"]) == counts["quarantined"]


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_conservation_invariant_holds_on_every_fixture(path):
    """Conservation against the *file*, not against the result's own arithmetic.

    Reading ``input_rows`` out of the result and comparing it to the other two
    numbers in the same dict is a tautology: a reader that dropped rows and
    then recomputed ``input_rows`` from the survivors passes it.  The count in
    the payload is the independent witness, so it is the one used here.
    """
    kwargs = {"resolve_issuer": synthetic_resolver}
    if path.name == "oversized_payload.json":
        kwargs["max_bytes"] = 512
        rows_in_payload = 0  # refused before parsing, so the rows are unknown
    else:
        declared = json.loads(path.read_text(encoding="utf-8")).get("rows")
        rows_in_payload = len(declared) if isinstance(declared, list) else 0
    result = read_event_projection(path.read_bytes(), **kwargs)
    counts = result["counts"]
    entries = result["quarantined"]
    envelope_refusal = bool(entries) and all(entry["row_index"] is None for entry in entries)
    if envelope_refusal:
        # A whole-envelope refusal reads no rows at all, and says so with
        # exactly one ledger entry — not zero, and not a scattering of them.
        # ``input_rows`` still names how many facts went unread.
        assert counts == {"input_rows": rows_in_payload, "accepted": 0, "quarantined": 1}
    else:
        assert counts["input_rows"] == rows_in_payload
        assert counts["accepted"] + counts["quarantined"] == counts["input_rows"]
    assert len(result["accepted"]) == counts["accepted"]
    assert len(result["quarantined"]) == counts["quarantined"]


# ---------------------------------------------------------------------------
# the default resolver refuses everything
# ---------------------------------------------------------------------------


def test_default_resolver_returns_none():
    assert resolve_issuer_unavailable({"source_native_id": "NCT00000001"}) is None


def test_default_resolver_quarantines_the_same_row_the_injected_one_accepts():
    accepted = read("unresolved_issuer.json")
    assert accepted["counts"]["accepted"] == 1

    refused = read_event_projection(load("unresolved_issuer.json"))
    assert refused["counts"]["accepted"] == 0
    assert refused["counts"]["quarantined"] == 1
    assert reasons(refused) == ["unresolved_issuer"]
    assert refused["quarantined"][0]["source_native_id"] == "NCT00000001"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_default_resolver_accepts_nothing_anywhere(path):
    """The shipped default reads no row from any fixture, ever."""
    result = read_event_projection(path.read_bytes())
    assert result["accepted"] == []
    assert result["counts"]["accepted"] == 0


def test_issuer_is_never_inferred_from_a_ticker_or_sponsor():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["ticker"] = "SYNTH"
    envelope["rows"][0]["context"]["sponsor"] = "Synthetic Sponsor Inc"
    result = read_event_projection(repack(envelope))
    assert reasons(result) == ["unresolved_issuer"]

    accepted = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert accepted["accepted"][0]["issuer_id"] == SYNTHETIC_ISSUER


# ---------------------------------------------------------------------------
# field mapping
# ---------------------------------------------------------------------------


def test_known_at_takes_transaction_from_not_knowledge_cutoff():
    envelope = envelope_of("success_identity_resolved.json")
    row = envelope["rows"][0]
    assert row["transaction_from"] != row["knowledge_cutoff"]
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    event = result["accepted"][0]
    assert event["known_at"] == row["transaction_from"]
    assert event["known_at"] != row["knowledge_cutoff"]
    assert row["knowledge_cutoff"] not in json.dumps(event)


def test_knowledge_cutoff_is_never_a_source_for_known_at_in_the_module_source():
    """Pin the mapping in the source, not only in one fixture's output.

    The output assertion above can be satisfied by a reader that happens to
    prefer ``transaction_from`` when both are present.  This one pins the code:
    ``known_at`` is fed by ``transaction_from`` verbatim, and the module never
    reads ``knowledge_cutoff`` as a value at all.
    """
    source = MODULE_SOURCE_PATH.read_text(encoding="utf-8")
    # Two positive anchors, because the raw value is now captured into a local
    # *before* the injected resolver runs and used from there: the capture must
    # read ``transaction_from``, and the build must read the capture.  A mutant
    # has to keep both and still cannot reach ``knowledge_cutoff``, which the
    # negative greps below forbid outright.
    assert 'transaction_from_raw = payload.get("transaction_from")' in source
    assert "known_at=transaction_from_raw," in source
    for expression in (
        'payload["knowledge_cutoff"]',
        'payload.get("knowledge_cutoff")',
        'row["knowledge_cutoff"]',
        'row.get("knowledge_cutoff")',
        "knowledge_cutoff",
    ):
        assert expression not in source, expression


def test_ingested_at_takes_retrieved_at():
    envelope = envelope_of("success_identity_resolved.json")
    row = envelope["rows"][0]
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"][0]["ingested_at"] == row["retrieved_at"]


def test_source_hash_carries_the_sha256_prefix():
    event = read("success_identity_resolved.json")["accepted"][0]
    assert event["source_hash"] == "sha256:" + "a" * 64


def test_source_attribution_supplies_class_and_url():
    envelope = envelope_of("success_identity_resolved.json")
    attribution = envelope["rows"][0]["source_attribution"]
    event = read("success_identity_resolved.json")["accepted"][0]
    assert event["source_class"] == attribution["source_class"]
    assert event["source_url"] == attribution["source_url"]


def test_missing_source_attribution_quarantines_rather_than_defaulting():
    result = read("missing_source_attribution.json")
    assert reasons(result) == ["missing_source_attribution"]
    assert result["accepted"] == []


# ---------------------------------------------------------------------------
# temporal honesty
# ---------------------------------------------------------------------------


def test_exact_date_becomes_a_day_span_not_a_midnight():
    event = read("success_identity_resolved.json")["accepted"][0]
    effective = event["source_effective"]
    assert effective["precision"] == "exact_date"
    assert effective["bound_rule"] == "day_span"
    assert effective["lower_bound"].startswith("2025-11-14T00:00:00")
    assert effective["upper_bound"].startswith("2025-11-14T23:59:59.999999")
    assert event["date_precision"] == "exact_date"


def test_exact_instant_stays_an_instant():
    event = read("after_hours_effective_time.json")["accepted"][0]
    effective = event["source_effective"]
    assert effective["precision"] == "exact_time"
    assert effective["bound_rule"] == "exact_instant"
    assert effective["lower_bound"] == effective["upper_bound"]
    assert effective["original_value"] == "2025-11-14 8:05 PM ET"


@pytest.mark.parametrize(
    "fixture,precision,bound_rule,lower,upper",
    [
        (
            "month_precision.json",
            "month",
            "month_span",
            "2026-03-01T00:00:00",
            "2026-03-31T23:59:59.999999",
        ),
        (
            "quarter_precision.json",
            "quarter",
            "quarter_span",
            "2026-07-01T00:00:00",
            "2026-09-30T23:59:59.999999",
        ),
        # Year was the untested third partial precision: replacing this branch
        # with a midnight instant — the exact defect month/quarter are pinned
        # against, one precision over — used to leave the suite green.
        (
            "year_precision.json",
            "year",
            "year_span",
            "2026-01-01T00:00:00",
            "2026-12-31T23:59:59.999999",
        ),
    ],
)
def test_partial_precision_never_gains_a_fabricated_time(
    fixture, precision, bound_rule, lower, upper
):
    event = read(fixture)["accepted"][0]
    effective = event["source_effective"]
    assert effective["precision"] == precision
    assert effective["bound_rule"] == bound_rule
    assert effective["lower_bound"].startswith(lower)
    assert effective["upper_bound"].startswith(upper)
    assert event["date_precision"] == precision
    # No midpoint anywhere: the span's ends are the only instants recorded.
    assert set(effective) == {
        "available",
        "unavailable_reason",
        "original_value",
        "precision",
        "lower_bound",
        "upper_bound",
        "source_timezone",
        "bound_rule",
    }


def test_range_precision_preserves_the_declared_window():
    event = read("range_precision.json")["accepted"][0]
    effective = event["source_effective"]
    assert effective["precision"] == "range"
    assert effective["bound_rule"] == "source_declared_range"
    assert effective["original_value"] == "first half of 2026"
    assert effective["lower_bound"] != effective["upper_bound"]


def test_future_effective_date_is_accepted_not_treated_as_leakage():
    result = read("future_effective_date.json")
    assert result["counts"]["accepted"] == 1
    assert result["accepted"][0]["source_effective"]["lower_bound"].startswith("2031-03-19")


def test_null_publication_time_stays_explicitly_unavailable():
    result = read("null_publication_time.json")
    event = result["accepted"][0]
    published = event["source_published"]
    assert published["available"] is False
    assert published["bound_rule"] == "unavailable"
    assert published["lower_bound"] is None and published["upper_bound"] is None
    assert published["unavailable_reason"] == "source_did_not_state_publication_time"
    # The system clocks are still exact, so anti-leakage is still enforceable.
    assert event["known_at"] >= event["ingested_at"]
    assert contracts.event_v2_pit_leakage_is_checkable(event) is False


def test_no_usable_effective_bound_is_quarantined_not_accepted():
    result = read("no_usable_effective_bound.json")
    assert result["accepted"] == []
    assert reasons(result) == ["no_usable_effective_bound"]
    assert result["quarantined"][0]["field"] == "source_effective"


def test_timestamp_ordering_violation_is_named_as_such():
    result = read("timestamp_ordering_violation.json")
    assert reasons(result) == ["timestamp_ordering_violation"]
    assert result["accepted"] == []
    assert result["quarantined"][0]["field"] == "transaction_from"


def test_a_source_published_lower_bound_after_retrieval_is_leakage():
    """The second anti-leakage ordering, which no fixture reached.

    Only the ``known_at < ingested_at`` branch had coverage, so deleting either
    of the other two left a green suite and shipped silent lookahead: a row
    claiming the source published it *after* we fetched it means one of the two
    clocks is fabricated.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_published"] = {
        "kind": "exact_time",
        "value": "2026-01-01T00:00:00Z",
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["timestamp_ordering_violation"]
    assert result["quarantined"][0]["field"] == "retrieved_at"


def test_an_actual_lower_bound_after_known_at_is_leakage():
    """The third ordering: the event cannot have happened after we knew it."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["actual"] = {"kind": "exact_time", "value": "2026-01-01T00:00:00Z"}
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["timestamp_ordering_violation"]
    assert result["quarantined"][0]["field"] == "actual"


def test_a_scheduled_window_survives_into_the_accepted_event():
    """``scheduled_window`` is null in every other fixture, so the branch that
    builds it could be replaced with ``None`` unnoticed — dropping a contract
    field the reader claims to carry, past a validator that accepts ``None``."""
    event = read("scheduled_window.json")["accepted"][0]
    window = event["scheduled_window"]
    assert window is not None
    assert window["precision"] == "month"
    assert window["bound_rule"] == "month_span"
    assert window["original_value"] == "March 2026 window"
    assert window["lower_bound"].startswith("2026-03-01T00:00:00")
    assert window["upper_bound"].startswith("2026-03-31T23:59:59.999999")
    # The event's own clock is untouched by the window it carries.
    assert event["date_precision"] == "exact_date"


def test_an_unparsed_publication_time_keeps_the_words_it_could_not_read():
    """``kind: unparsed`` had no fixture: the source said something we could not
    interpret, and the words are the fact.  Collapsing that branch to
    ``unavailable`` — losing the text and flipping ``available`` — used to pass.
    """
    event = read("unparsed_published_value.json")["accepted"][0]
    published = event["source_published"]
    assert published["available"] is True
    assert published["bound_rule"] == "unparsed"
    assert published["original_value"] == "posted some time before the committee met"
    assert published["lower_bound"] is None and published["upper_bound"] is None


def test_an_unparsed_effective_value_has_no_clock_to_sit_on():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {
        "kind": "unparsed",
        "original_value": "when the committee next meets",
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["no_usable_effective_bound"]


# ---------------------------------------------------------------------------
# allowlists
# ---------------------------------------------------------------------------


def test_unknown_event_type_never_collapses_to_other():
    result = read("unknown_event_type.json")
    assert reasons(result) == ["unknown_event_type"]
    assert result["accepted"] == []
    assert "other" not in json.dumps(result["quarantined"])


def test_unknown_status_never_defaults_to_active():
    result = read("unknown_status.json")
    assert reasons(result) == ["unknown_status"]
    assert result["accepted"] == []
    envelope = envelope_of("unknown_status.json")
    assert envelope["rows"][0]["status"] == "active"


def test_accepted_types_and_statuses_come_from_the_frozen_allowlists():
    for name in ("success_identity_resolved.json", "correction_revision.json"):
        event = read(name)["accepted"][0]
        assert event["event_type"] in contracts.EVENT_TYPE_ALLOWLIST_V2
        assert event["status"] in contracts.EVENT_STATUS_ALLOWLIST_V2


def test_corrupt_source_hash_quarantines():
    result = read("corrupt_source_hash.json")
    assert reasons(result) == ["corrupt_source_hash"]


def test_bare_digest_without_the_prefix_is_corrupt_not_repaired():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["canonical_content_sha256"] = "a" * 64
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["corrupt_source_hash"]


# ---------------------------------------------------------------------------
# DNR:KILL-PHASE3-START-WEIGHT
# ---------------------------------------------------------------------------


def test_phase3_trial_start_carries_no_score_weight_rank_or_severity():
    envelope = envelope_of("trial_start_phase3_context.json")
    assert envelope["rows"][0]["context"]["phase"] == "PHASE3"
    assert envelope["rows"][0]["event_type"] == "trial_start"

    result = read("trial_start_phase3_context.json")
    event = result["accepted"][0]
    assert event["event_type"] == "trial_start"
    assert FORBIDDEN_AUTHORITY_FIELDS.isdisjoint(set(event))
    for field in ("score", "weight", "rank", "priority", "severity"):
        assert field not in event
    # Nor does the phase reach the payload at all — it is context, not a leg.
    assert "PHASE3" not in json.dumps(event)


def test_certainty_is_never_manufactured_from_registry_fields():
    event = read("trial_start_phase3_context.json")["accepted"][0]
    assert event["certainty"] is None

    envelope = envelope_of("trial_start_phase3_context.json")
    envelope["rows"][0]["certainty"] = 0.4
    supplied = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert supplied["accepted"][0]["certainty"] == pytest.approx(0.4)


def test_no_accepted_event_anywhere_carries_an_authority_shaped_field():
    for path in sorted(FIXTURES.glob("*.json")):
        result = read_event_projection(path.read_bytes(), resolve_issuer=synthetic_resolver)
        for event in result["accepted"]:
            assert FORBIDDEN_AUTHORITY_FIELDS.isdisjoint(set(event)), path.name


# ---------------------------------------------------------------------------
# event_id derivation
# ---------------------------------------------------------------------------


def test_event_id_is_derived_from_source_identity_and_revision():
    expected = derive_event_id(
        source_native_id="NCT00000001",
        event_type="pdufa_date",
        revision_id="rev_NCT00000001_0",
        revision_index=0,
    )
    event = read("success_identity_resolved.json")["accepted"][0]
    assert event["event_id"] == expected
    assert re.fullmatch(r"bpev_[0-9a-f]{40}", event["event_id"])


def test_event_id_changes_with_revision_identity_only():
    base = dict(
        source_native_id="NCT00000001",
        event_type="pdufa_date",
        revision_id="rev_0",
        revision_index=0,
    )
    assert derive_event_id(**base) == derive_event_id(**base)
    assert derive_event_id(**{**base, "revision_index": 1}) != derive_event_id(**base)
    assert derive_event_id(**{**base, "revision_id": "rev_1"}) != derive_event_id(**base)
    assert derive_event_id(**{**base, "event_type": "readout"}) != derive_event_id(**base)
    assert derive_event_id(**{**base, "source_native_id": "NCT9"}) != derive_event_id(**base)


def test_event_id_does_not_move_when_a_ticker_is_added_to_the_row():
    envelope = envelope_of("success_identity_resolved.json")
    before = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    envelope["rows"][0]["ticker"] = "SYNTH"
    after = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert before["accepted"][0]["event_id"] == after["accepted"][0]["event_id"]


def test_correction_revision_is_a_distinct_event_that_supersedes():
    event = read("correction_revision.json")["accepted"][0]
    assert event["revision"] == {
        "revision_id": "rev_NCT00000001_1",
        "revision_index": 1,
        "supersedes": "rev_NCT00000001_0",
    }
    original = read("success_identity_resolved.json")["accepted"][0]
    assert event["event_id"] != original["event_id"]


# ---------------------------------------------------------------------------
# collisions
# ---------------------------------------------------------------------------


def test_identical_duplicates_keep_one_copy_and_explain_the_other():
    result = read("duplicate_event.json")
    assert result["counts"] == {"input_rows": 2, "accepted": 1, "quarantined": 1}
    assert reasons(result) == ["duplicate_event_id"]
    assert result["quarantined"][0]["row_index"] == 1
    assert result["quarantined"][0]["source_native_id"] == "NCT00000001"


def test_conflicting_revisions_quarantine_every_member_of_the_group():
    result = read("conflicting_revisions.json")
    assert result["counts"] == {"input_rows": 2, "accepted": 0, "quarantined": 2}
    assert reasons(result) == ["contradictory_revision", "contradictory_revision"]
    assert {entry["row_index"] for entry in result["quarantined"]} == {0, 1}


def test_conflicting_revisions_resolve_the_same_way_when_reversed():
    envelope = envelope_of("conflicting_revisions.json")
    envelope["rows"] = list(reversed(envelope["rows"]))
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["contradictory_revision", "contradictory_revision"]


def test_the_ledger_is_ordered_by_row_even_when_a_collision_is_appended_late():
    """Collision quarantines are appended after every row refusal, so insertion
    order diverges from row order the moment a batch has both.  No fixture has
    both, and the shuffle test sorts the reasons before comparing, so replacing
    the sort with plain insertion order used to survive."""
    envelope = envelope_of("duplicate_event.json")
    trailing = copy.deepcopy(envelope["rows"][0])
    trailing["event_type"] = "not_an_event_type"
    envelope["rows"].append(trailing)
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    entries = [(entry["row_index"], entry["reason_code"]) for entry in result["quarantined"]]
    assert entries == [(1, "duplicate_event_id"), (2, "unknown_event_type")]
    indices = [entry["row_index"] for entry in result["quarantined"]]
    assert indices == sorted(indices)


def test_one_event_id_with_conflicting_content_quarantines_both():
    envelope = envelope_of("duplicate_event.json")
    envelope["rows"][1]["status"] = "delayed"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["contradictory_revision", "contradictory_revision"]


# ---------------------------------------------------------------------------
# envelope-level refusal
# ---------------------------------------------------------------------------


def assert_envelope_refusal(result, reason_code, *, unread_rows=0):
    assert result["schema"] == EVENT_CLOCK_READ_SCHEMA
    assert result["accepted"] == []
    assert result["counts"] == {"input_rows": unread_rows, "accepted": 0, "quarantined": 1}
    assert reasons(result) == [reason_code]
    assert result["quarantined"][0]["row_index"] is None
    assert result["quarantined"][0]["source_native_id"] is None
    assert result["generation"]["generation_id"] is None
    assert result["generation"]["content_hash"].startswith("sha256:")


def test_unknown_contract_id_is_refused_wholesale():
    assert_envelope_refusal(
        read("unknown_contract_id.json"), "unknown_envelope_contract", unread_rows=1
    )


def test_unknown_schema_version_is_refused_wholesale():
    assert_envelope_refusal(
        read("unknown_schema_version.json"), "unknown_schema_version", unread_rows=1
    )


def test_envelope_hash_mismatch_is_refused_wholesale():
    assert_envelope_refusal(
        read("envelope_hash_mismatch.json"), "envelope_hash_mismatch", unread_rows=1
    )


def test_an_envelope_refusal_reports_how_many_rows_went_unread():
    """A refusal has a size, and the ledger has to state it.

    ``input_rows: 0`` on a packet that carried seven rows is the reading a
    downstream coverage metric turns into "0 of 0 — nothing lost".  The count
    below is the one number that distinguishes a dropped row from a dropped
    truckload.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"] = [copy.deepcopy(envelope["rows"][0]) for _ in range(7)]
    envelope["contract_id"] = "someone_elses_projection.v1"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert_envelope_refusal(result, "unknown_envelope_contract", unread_rows=7)
    assert result["counts"]["input_rows"] == 7


def test_rows_not_a_list_is_refused_wholesale():
    assert_envelope_refusal(read("rows_not_a_list.json"), "rows_not_a_list")


def test_oversized_payload_is_refused_before_parsing():
    result = read("oversized_payload.json", max_bytes=512)
    assert_envelope_refusal(result, "oversized_payload")
    assert read("oversized_payload.json")["counts"]["input_rows"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"not json at all",
        b"[1, 2, 3]",
        b'"a bare string"',
        b"\xff\xfe\x00",
        b'{"contract_id": "biocatalyst_seasonality_event_projection.v1",',
    ],
)
def test_hostile_bytes_produce_a_structured_refusal_not_a_traceback(payload):
    result = read_event_projection(payload, resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert len(result["quarantined"]) == 1
    assert result["quarantined"][0]["reason_code"] in {
        "envelope_unparseable",
        "unknown_envelope_contract",
    }


def test_envelope_missing_generation_metadata_is_refused():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["generation_id"] = "run_2026"
    assert_envelope_refusal(
        read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver),
        "envelope_unparseable",
        unread_rows=1,
    )


def test_altered_hash_scope_is_refused():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["hash_scope"] = "whole_payload"
    assert_envelope_refusal(
        read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver),
        "envelope_hash_mismatch",
        unread_rows=1,
    )


def test_a_tampered_row_breaks_the_envelope_hash():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["status"] = "occurred"
    payload = json.dumps(envelope).encode("utf-8")  # packet_hash left stale on purpose
    assert_envelope_refusal(
        read_event_projection(payload, resolve_issuer=synthetic_resolver),
        "envelope_hash_mismatch",
        unread_rows=1,
    )


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("packet_id", None, "envelope_unparseable"),
        ("coverage_epoch_id", "   ", "envelope_unparseable"),
        ("coverage_epoch_id", 7, "envelope_unparseable"),
        ("last_complete_run_ref", "run_2026", "envelope_unparseable"),
        ("last_complete_run_ref", 7, "envelope_unparseable"),
    ],
)
def test_envelope_metadata_validators_each_refuse(key, value, reason):
    """One case per envelope validator that no fixture reaches.

    ``packet_id`` in particular is validated *nowhere else*: the required-key
    sweep is its only gate, and deleting that sweep left the suite green.
    """
    envelope = envelope_of("success_identity_resolved.json")
    if value is None:
        envelope.pop(key)
    else:
        envelope[key] = value
    assert_envelope_refusal(
        read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver),
        reason,
        unread_rows=1,
    )


@pytest.mark.parametrize("field", ["generation_id", "last_complete_run_ref"])
def test_a_run_reference_with_a_trailing_newline_is_not_a_run_reference(field):
    """``$`` matches before a trailing newline; ``fullmatch`` is the fix.

    ``re.match(r"^ctgov_run_\\w+$", "ctgov_run_x\\n")`` succeeds, so the
    smuggled newline used to land verbatim in ``generation.generation_id``.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope[field] = envelope[field] + "\n"
    assert_envelope_refusal(
        read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver),
        "envelope_unparseable",
        unread_rows=1,
    )


# ---------------------------------------------------------------------------
# row-level refusals
# ---------------------------------------------------------------------------


def test_row_that_is_not_an_object_is_quarantined_with_a_null_native_id():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"].append("a bare string masquerading as a row")
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["counts"] == {"input_rows": 2, "accepted": 1, "quarantined": 1}
    entry = result["quarantined"][0]
    assert entry["reason_code"] == "row_not_an_object"
    assert entry["source_native_id"] is None


def test_missing_transaction_from_has_its_own_reason_code():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0].pop("transaction_from")
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["missing_transaction_from"]
    assert result["quarantined"][0]["field"] == "transaction_from"


def test_unparsable_timestamp_is_named():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["transaction_from"] = "sometime last spring"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["unparsable_timestamp"]


def test_naive_timestamp_without_a_zone_is_refused():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["retrieved_at"] = "2025-06-02T12:30:00"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["unparsable_timestamp"]


def test_stale_generation_row_is_quarantined():
    result = read("stale_generation.json")
    assert reasons(result) == ["stale_generation"]
    assert result["quarantined"][0]["field"] == "generation_ref"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/synthetic/../../../etc/passwd",
        "file:///etc/passwd",
        "https://example.invalid/%2e%2e/%2e%2e/secret",
        "..\\..\\windows\\system32",
    ],
)
def test_path_traversal_in_a_source_uri_is_refused(url):
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"]["source_url"] = url
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["path_traversal_attempt"]
    assert result["accepted"] == []


def test_path_traversal_fixture_matches_the_parametrised_case():
    result = read("path_traversal_source_uri.json")
    assert reasons(result) == ["path_traversal_attempt"]


def test_unknown_temporal_kind_is_unparsable_not_guessed():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {"kind": "sometime_soon"}
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["unparsable_timestamp"]


def test_a_range_without_a_declared_original_value_is_refused():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {
        "kind": "range",
        "lower": "2026-01-01T00:00:00Z",
        "upper": "2026-06-30T00:00:00Z",
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["unparsable_timestamp"]


@pytest.mark.parametrize(
    "key", sorted(set(_ROW_REQUIRED_KEYS) - {"transaction_from"})
)
def test_every_required_row_key_has_its_own_refusal(key):
    """The whole ``missing_required_field`` sweep could be deleted unnoticed.

    Only ``transaction_from`` had a test, and it exits through the *earlier*
    dedicated branch, so the sweep itself was never triggered by anything.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0].pop(key)
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    expected = "missing_source_attribution" if key == "source_attribution" else (
        "missing_required_field"
    )
    assert reasons(result) == [expected], key


def test_a_negative_revision_index_is_refused():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["revision"]["revision_index"] = -3
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["missing_required_field"]


def test_an_absurd_revision_index_is_refused_before_it_reaches_the_event_id():
    """A revision counter is small.  ``10**30`` is a producer defect or a probe,
    and it used to sail into ``derive_event_id`` and the revision key."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["revision"]["revision_index"] = MAX_REVISION_INDEX + 1
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["missing_required_field"]
    assert result["quarantined"][0]["field"] == "revision.revision_index"


@pytest.mark.parametrize("value", [7, [], {}, True])
def test_a_non_string_supersedes_is_refused(value):
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["revision"]["supersedes"] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["missing_required_field"]


@pytest.mark.parametrize("value", ["0.8", [], {}, "high"])
def test_a_non_numeric_certainty_is_refused_rather_than_coerced(value):
    """Removing this validator does worse than mislabel: a string reaches
    ``float(certainty)`` and raises a bare ``ValueError`` out of a function
    documented as never raising on bad input."""
    envelope = envelope_of("trial_start_phase3_context.json")
    envelope["rows"][0]["certainty"] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["missing_required_field"]


@pytest.mark.parametrize(
    "attribution",
    [
        {"source_class": "", "source_url": "https://example.invalid/x"},
        {"source_class": "   ", "source_url": "https://example.invalid/x"},
        {"source_class": "regulatory_registry", "source_url": ""},
        {"source_class": "regulatory_registry", "source_url": "   "},
        {"source_url": "https://example.invalid/x"},
        {"source_class": "regulatory_registry"},
    ],
)
def test_blank_source_attribution_is_refused_rather_than_defaulted(attribution):
    """Present-but-empty was untested, and three separate weakenings survived:
    defaulting ``source_class`` to ``"unknown_source"``, defaulting
    ``source_url`` to ``"about:blank"``, and dropping ``.strip()`` so that
    ``"   "`` became a valid value everywhere in the module."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"] = attribution
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["missing_source_attribution"]


# ---------------------------------------------------------------------------
# hostile input never leaves as a traceback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["event_type", "status"])
@pytest.mark.parametrize("value", [{}, [], {"a": 1}, [1, 2]])
def test_a_non_scalar_allowlisted_field_is_refused_not_raised(field, value):
    """``{} in frozenset`` raises ``TypeError: unhashable type``.

    That traceback escaped the row loop, which catches only ``_RowRefusal``, so
    one malformed row in a correctly-signed packet destroyed every other row in
    it — no ledger, no counts, nothing to triage.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0][field] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == [
        "unknown_event_type" if field == "event_type" else "unknown_status"
    ]


@pytest.mark.parametrize("value", [{}, [], 7])
def test_a_non_scalar_temporal_kind_is_refused_not_raised(value):
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {"kind": value}
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["unparsable_timestamp"]


def test_one_poison_row_does_not_take_the_batch_down_with_it():
    """The blast radius is the point: the packet is well-formed and correctly
    signed, and one hostile row must cost exactly one row."""
    envelope = envelope_of("success_identity_resolved.json")
    good = envelope["rows"][0]
    rows = []
    for index in range(5):
        row = copy.deepcopy(good)
        row["source_native_id"] = f"NCT0000000{index}"
        row["revision"] = dict(row["revision"], revision_id=f"rev_{index}")
        rows.append(row)
    poison = copy.deepcopy(good)
    poison["event_type"] = {}
    rows.append(poison)
    envelope["rows"] = rows
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["counts"] == {"input_rows": 6, "accepted": 5, "quarantined": 1}
    assert reasons(result) == ["unknown_event_type"]


def test_a_nesting_bomb_is_refused_before_it_can_blow_the_stack():
    """20 KB of nested arrays — half a percent of the byte ceiling — used to
    raise ``RecursionError`` out of ``json.loads``.  The byte ceiling is a
    length gate and says nothing about depth."""
    payload = b'{"contract_id": ' + b"[" * 20000 + b"]" * 20000 + b"}"
    assert len(payload) < MAX_PROJECTION_BYTES
    result = read_event_projection(payload, resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["envelope_unparseable"]
    assert "nests" in result["quarantined"][0]["detail"]


def test_a_payload_at_the_depth_ceiling_still_reads():
    """The guard refuses depth bombs, not legitimate structure: a real envelope
    nests about six levels, and the ceiling must not be under it."""
    envelope = envelope_of("success_identity_resolved.json")
    nested = "leaf"
    for _ in range(MAX_PROJECTION_DEPTH - 5):
        nested = [nested]
    envelope["rows"][0]["context"]["nested"] = nested
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["counts"]["accepted"] == 1


def test_a_bracket_inside_a_string_is_not_counted_as_structure():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["context"]["note"] = "[" * 200 + "]" * 200
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["counts"]["accepted"] == 1


def test_canonical_projection_bytes_converts_a_depth_error_into_a_contract_error():
    deep = "leaf"
    for _ in range(20000):
        deep = [deep]
    with pytest.raises(contracts.ContractError):
        canonical_projection_bytes(deep)


# ---------------------------------------------------------------------------
# the injected identity authority is a boundary, not a trusted collaborator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolver",
    [
        lambda row: "",
        lambda row: "   ",
        lambda row: 123,
        lambda row: {"issuer_id": "SYNTH"},
        lambda row: ["SYNTH"],
        lambda row: True,
    ],
    ids=["empty", "whitespace", "int", "dict", "list", "bool"],
)
def test_a_malformed_resolver_return_never_becomes_an_issuer(resolver):
    """``resolve_issuer`` is the module's one injected authority, and the whole
    "no identity by inference" ceiling rests on the check of what it returns.
    Weakening that check to ``if issuer_id is None`` used to survive."""
    result = read_event_projection(
        load("success_identity_resolved.json"), resolve_issuer=resolver
    )
    assert result["accepted"] == []
    assert reasons(result) == ["unresolved_issuer"]


@pytest.mark.parametrize(
    "exc",
    [RuntimeError("identity service is down"), KeyError("nope"), TimeoutError()],
    ids=["runtime", "key", "timeout"],
)
def test_a_raising_resolver_quarantines_its_row_instead_of_the_batch(exc):
    """A real identity service times out and 500s.  There is no reason for that
    to convert N-1 readable rows into a traceback."""

    def failing(row):
        raise exc

    envelope = envelope_of("success_identity_resolved.json")
    second = copy.deepcopy(envelope["rows"][0])
    second["source_native_id"] = "NCT00000002"
    envelope["rows"].append(second)
    result = read_event_projection(repack(envelope), resolve_issuer=failing)
    assert result["counts"] == {"input_rows": 2, "accepted": 0, "quarantined": 2}
    assert reasons(result) == ["unresolved_issuer", "unresolved_issuer"]
    assert type(exc).__name__ in result["quarantined"][0]["detail"]


def test_a_resolver_cannot_rewrite_the_point_in_time_clocks_it_is_shown():
    """The resolver runs mid-row, and ``known_at`` used to be re-read from the
    live dict afterwards — so a mutation landed in the accepted event's PIT
    clocks, past the ordering checks and past the verified packet hash."""
    seen = {}

    def meddling(row):
        seen["type"] = type(row)
        row["transaction_from"] = "2099-01-01T00:00:00Z"
        row["retrieved_at"] = "2099-01-01T00:00:00Z"
        row["source_attribution"]["source_url"] = "https://evil.invalid/"
        return SYNTHETIC_ISSUER

    envelope = envelope_of("success_identity_resolved.json")
    original = envelope["rows"][0]
    result = read_event_projection(repack(envelope), resolve_issuer=meddling)
    event = result["accepted"][0]
    assert event["known_at"] == original["transaction_from"]
    assert event["ingested_at"] == original["retrieved_at"]
    assert event["source_url"] == original["source_attribution"]["source_url"]
    assert "2099" not in json.dumps(result)
    # The resolver still gets a plain dict, so a governed service written
    # against the documented signature keeps working.
    assert seen["type"] is dict


def test_a_resolver_cannot_rename_the_row_in_the_quarantine_ledger():
    """The ledger echo reads the row object itself, after the resolver has run.

    Handing the live dict to the injected authority let a resolver decide which
    source record the ledger blames — the quarantine entry would carry an id the
    signed payload never contained.
    """

    def meddling(row):
        row["source_native_id"] = "NCT99999999_INJECTED"
        return None

    result = read_event_projection(
        load("success_identity_resolved.json"), resolve_issuer=meddling
    )
    assert reasons(result) == ["unresolved_issuer"]
    assert result["quarantined"][0]["source_native_id"] == "NCT00000001"
    assert "INJECTED" not in json.dumps(result)


def test_the_resolver_is_only_asked_about_rows_the_reader_could_accept():
    """An ordering violation is named as one even under the shipped default:
    the row's own failures are decided before an external authority is called.
    """
    asked = []

    def counting(row):
        asked.append(row.get("source_native_id"))
        return None

    result = read_event_projection(load("timestamp_ordering_violation.json"), resolve_issuer=counting)
    assert reasons(result) == ["timestamp_ordering_violation"]
    assert asked == []


# ---------------------------------------------------------------------------
# hostile source text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/%2e%2e%2f%2e%2e%2fsecret",
        "https://example.invalid/..%2f..%2fetc/passwd",
        "https://example.invalid/..%252f..%252fetc",
        "https://example.invalid/..\u2044..\u2044etc",
        "https://example.invalid/..\uff0f..\uff0fetc",
    ],
)
def test_an_encoded_or_lookalike_traversal_is_still_a_traversal(url):
    """The marker list is a substring denylist, and a substring denylist that is
    not normalised first is defeated by the first person who reads it."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"]["source_url"] = url
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["path_traversal_attempt"]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(document.cookie)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "/etc/passwd",
        "\\\\attacker\\share",
        "about:blank",
        "ftp://example.invalid/x",
    ],
)
def test_a_source_url_that_is_not_an_http_resource_is_not_an_attribution(url):
    """Denylisting hostile schemes never converges — ``/etc/passwd`` has no
    dots and no scheme at all — so the field is an allowlist."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"]["source_url"] = url
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["path_traversal_attempt"]


@pytest.mark.parametrize(
    "attribution_extra",
    [
        {"source_class_note": "../../etc/passwd"},
        {"meta": {"path": "../../etc/passwd"}},
        {"notes": ["fine", "../../etc/passwd"]},
        {"notes": [{"deeper": "..\\..\\windows"}]},
    ],
)
def test_a_traversal_anywhere_in_the_attribution_is_refused(attribution_extra):
    """The scan returned on the first non-string value, so anything nested was
    never inspected, and only ``source_url`` had a test at all."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"].update(attribution_extra)
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["path_traversal_attempt"]


@pytest.mark.parametrize(
    "value", ["../../etc/passwd", "NCT/../../secret", "..%2f..%2fetc"]
)
def test_a_traversal_in_the_source_record_id_is_refused(value):
    """The id travels like an attribution: it reaches ``derive_event_id`` and is
    echoed into the ledger, and no registry identifier contains a path."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_native_id"] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["path_traversal_attempt"]


def test_a_traversal_shaped_issuer_from_the_resolver_is_refused():
    result = read_event_projection(
        load("success_identity_resolved.json"), resolve_issuer=lambda row: "../../etc/passwd"
    )
    assert result["accepted"] == []
    assert reasons(result) == ["path_traversal_attempt"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_native_id", "NCT\x00000001"),
        ("source_native_id", "NCT\u202e10000000"),
        ("source_native_id", "NCT" + "0" * MAX_NATIVE_ID_CHARS),
    ],
    ids=["nul", "rtl-override", "unbounded"],
)
def test_hostile_source_text_is_refused_and_not_echoed_into_the_ledger(field, value):
    """The quarantine ledger is an operator-facing surface.  A NUL byte, a
    right-to-left override, and a megabyte of padding all used to be accepted
    into ``event_id`` *and* repeated verbatim into the ledger."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0][field] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["unsafe_source_text"]
    assert value not in json.dumps(result)
    assert result["quarantined"][0]["source_native_id"] is None


def test_hostile_text_is_withheld_from_the_ledger_even_on_an_unrelated_refusal():
    """The ledger echo reads the raw row, so it needs its own check: this row
    fails for a different reason entirely and must still not carry the id."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_native_id"] = "NCT\u202e0001"
    envelope["rows"][0]["event_type"] = "not_an_event_type"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["unknown_event_type"]
    assert result["quarantined"][0]["source_native_id"] is None


@pytest.mark.parametrize(
    "value",
    ["reg\u202eistry", "regi\x00stry", "r" * (MAX_SOURCE_TEXT_CHARS + 1)],
    ids=["rtl-override", "nul", "unbounded"],
)
def test_hostile_source_class_text_is_refused(value):
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_attribution"]["source_class"] = value
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["unsafe_source_text"]


def test_a_hostile_issuer_from_the_resolver_is_refused_too():
    """The injected authority is not exempt from the ledger's own hygiene."""
    for hostile in ("IS\x00SUER", "../../etc/passwd\x00", "I" * (MAX_NATIVE_ID_CHARS + 1)):
        result = read_event_projection(
            load("success_identity_resolved.json"), resolve_issuer=lambda row, v=hostile: v
        )
        assert result["accepted"] == [], hostile
        assert reasons(result) == ["unsafe_source_text"], hostile


def test_a_source_hash_with_a_trailing_newline_is_corrupt_not_a_contract_error():
    """``$`` matches before a trailing newline, so this used to pass the gate and
    die inside the contract as a generic ``contract_error`` — the wrong reason
    code for the operator who has to go and look at the producer."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["canonical_content_sha256"] = "sha256:" + "a" * 64 + "\n"
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert reasons(result) == ["corrupt_source_hash"]


@pytest.mark.parametrize(
    "zone", ["../../etc/passwd", "/etc/passwd", "Not A Zone", "America/New_York\n"]
)
def test_a_hostile_timezone_is_a_refusal_and_never_a_traceback(zone):
    """What this pins is the *outcome*, and two guards can each deliver it.

    ``_IANA_ZONE_PATTERN`` and the ``ContractError`` conversion in
    ``_build_temporal`` are mutually redundant here: drop the pattern and these
    strings reach ``ZoneInfo`` (which refuses absolute and ``..`` keys itself)
    and come back as the same ``unparsable_timestamp``; drop the conversion and
    the pattern refuses them first.  So neither mutation alone is visible to
    this test, and that is stated rather than hidden — dropping *both* makes it
    fail with a ``ContractError`` traceback out of a reader documented as never
    raising on input.  The pattern is kept for reach, not for output: a
    payload-controlled string should not arrive at a path-resolving API at all.
    """
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {
        "kind": "exact_date",
        "value": "2025-11-14",
        "timezone": zone,
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["unparsable_timestamp"]


def test_a_real_iana_zone_still_reads():
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {
        "kind": "exact_date",
        "value": "2025-11-14",
        "timezone": "America/New_York",
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["counts"]["accepted"] == 1
    assert result["accepted"][0]["source_effective"]["source_timezone"] == "America/New_York"


def test_an_explicitly_empty_original_value_is_not_replaced_by_the_machine_value():
    """``original or value`` silently substituted the ISO string for a source
    that asserted nothing.  The source's empty assertion is refused instead."""
    envelope = envelope_of("success_identity_resolved.json")
    envelope["rows"][0]["source_effective"] = {
        "kind": "exact_time",
        "value": "2025-11-14T20:05:00Z",
        "original_value": "",
    }
    result = read_event_projection(repack(envelope), resolve_issuer=synthetic_resolver)
    assert result["accepted"] == []
    assert reasons(result) == ["unparsable_timestamp"]


# ---------------------------------------------------------------------------
# result shape / ledger vocabulary
# ---------------------------------------------------------------------------


def test_result_shape_is_the_declared_schema():
    result = read("mixed_batch.json")
    assert set(result) == {
        "schema",
        "accepted",
        "quarantined",
        "counts",
        "generation",
        "fixture_only",
    }
    assert result["schema"] == EVENT_CLOCK_READ_SCHEMA
    assert set(result["counts"]) == {"input_rows", "accepted", "quarantined"}
    assert set(result["generation"]) == {
        "generation_id",
        "coverage_epoch_id",
        "content_hash",
        "last_complete_run_ref",
    }
    assert result["generation"]["generation_id"] == "ctgov_run_synthetic_2026_08_06"
    assert result["generation"]["content_hash"].startswith("sha256:")


def test_every_quarantine_row_uses_the_closed_vocabulary_and_shape():
    for path in sorted(FIXTURES.glob("*.json")):
        result = read_event_projection(path.read_bytes(), resolve_issuer=synthetic_resolver)
        for entry in result["quarantined"]:
            assert set(entry) == {
                "row_index",
                "source_native_id",
                "reason_code",
                "field",
                "detail",
            }
            assert entry["reason_code"] in QUARANTINE_REASON_CODES
            assert isinstance(entry["detail"], str) and entry["detail"].strip()
            assert entry["row_index"] is None or isinstance(entry["row_index"], int)


def test_reason_code_allowlist_is_exactly_the_governed_set():
    assert QUARANTINE_REASON_CODES == frozenset(
        {
            "unknown_envelope_contract",
            "unknown_schema_version",
            "envelope_hash_mismatch",
            "envelope_unparseable",
            "oversized_payload",
            "rows_not_a_list",
            "row_not_an_object",
            "missing_required_field",
            "unknown_event_type",
            "unknown_status",
            "unresolved_issuer",
            "missing_transaction_from",
            "unparsable_timestamp",
            "timestamp_ordering_violation",
            "no_usable_effective_bound",
            "duplicate_event_id",
            "contradictory_revision",
            "corrupt_source_hash",
            "missing_source_attribution",
            "stale_generation",
            "path_traversal_attempt",
            "unsafe_source_text",
            "contract_error",
        }
    )


def test_fixture_only_marker_cannot_be_laundered_off_by_the_caller():
    result = read_event_projection(
        load("success_identity_resolved.json"),
        resolve_issuer=synthetic_resolver,
        fixture_only=False,
    )
    assert result["fixture_only"] is True


def test_fixture_only_flag_is_echoed_for_an_unmarked_payload():
    envelope = envelope_of("success_identity_resolved.json")
    envelope.pop("fixture_only")
    payload = repack(envelope)
    assert read_event_projection(payload, resolve_issuer=synthetic_resolver)["fixture_only"] is False
    assert (
        read_event_projection(payload, resolve_issuer=synthetic_resolver, fixture_only=True)[
            "fixture_only"
        ]
        is True
    )


def test_accepted_events_validate_against_the_frozen_v2_contract():
    for path in sorted(FIXTURES.glob("*.json")):
        result = read_event_projection(path.read_bytes(), resolve_issuer=synthetic_resolver)
        for event in result["accepted"]:
            assert event["schema"] == contracts.BIOTEMPORAL_EVENT_V2_SCHEMA
            contracts.validate_bitemporal_event_v2(event)
            assert contracts.event_v2_content_hash(event).startswith("sha256:")


def test_result_is_json_serialisable_and_stable():
    result = read("mixed_batch.json")
    text = json.dumps(result, sort_keys=True)
    assert json.loads(text) == json.loads(json.dumps(copy.deepcopy(result), sort_keys=True))


# ---------------------------------------------------------------------------
# programming errors still raise
# ---------------------------------------------------------------------------


def test_non_bytes_input_is_a_programming_error():
    with pytest.raises(contracts.ContractError):
        read_event_projection({"contract_id": EXPECTED_PROJECTION_CONTRACT})


def test_non_positive_max_bytes_is_a_programming_error():
    with pytest.raises(contracts.ContractError):
        read_event_projection(load("success_identity_resolved.json"), max_bytes=0)


def test_the_package_re_exports_are_the_same_objects_as_the_module_s():
    """``engine/seasonality/__init__.py`` grew five re-exports that nothing
    imported, so deleting the block would not have failed anything."""
    import engine.seasonality as package
    from engine.seasonality import event_clock

    for name in (
        "EVENT_CLOCK_READ_SCHEMA",
        "EXPECTED_PROJECTION_CONTRACT",
        "QUARANTINE_REASON_CODES",
        "read_event_projection",
        "resolve_issuer_unavailable",
    ):
        assert name in package.__all__, name
        assert getattr(package, name) is getattr(event_clock, name), name
    assert package.resolve_issuer_unavailable({"source_native_id": "NCT00000001"}) is None


def test_module_constants_are_the_declared_consumer_expectation():
    assert EXPECTED_PROJECTION_CONTRACT == "biocatalyst_seasonality_event_projection.v1"
    assert EXPECTED_PROJECTION_SCHEMA_VERSION == "1.0.0"
    assert MAX_PROJECTION_BYTES == 4 * 1024 * 1024
    source = MODULE_SOURCE_PATH.read_text(encoding="utf-8")
    assert "CONSUMER'S" in source
    assert "not a ratified producer contract" in source
