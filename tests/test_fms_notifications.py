"""Merge-binding adversarial battery for the D6-B1 FMS congressional-
notification vertical.

Freeze T1-T14 (``research/defense_intelligence/DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md``
§16) plus the D6-B1 packet battery B1-B11
(``research/defense_intelligence/DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md``
§11). B12-B14 (EN/ZH template copy, page-weight fence, anonymous API/site
boundary) belong to packet 2 (page/API/workflow wiring) and are out of scope
here.

Every fixture under ``tests/fixtures/fms/`` is real receipted bytes (see
``tests/fixtures/fms/FIXTURE_PROVENANCE.json``) — no synthetic HTML/FR text.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from collectors import fms_notifications as fms
from collectors import fms_notifications_live as live
from engine.government_revenue import fms_cases, metrics
from engine.research_vault.r2_store import LocalStore

FIXTURES = Path(__file__).parent / "fixtures" / "fms"
SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "contracts" / "government_revenue" / "government_fms_case.v1.schema.json"
)
RECEIPT_AT = "2026-08-26T00:00:00Z"


# ---------------------------------------------------------------------------
# Shared fixture-loading helpers
# ---------------------------------------------------------------------------


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_graph(graph: dict) -> None:
    jsonschema.validate(instance=graph, schema=_schema())


def _read_bytes(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def _make_observation(
    *, case_key: str, source_surface: str, kind: str, source_url: str,
    content: bytes, fields: dict, publisher: str = "test-publisher",
    transport: str = "cli", parser_version: str = "test-parser.v1",
    known_at: str = RECEIPT_AT, version: int = 1,
) -> dict:
    receipt = fms.build_receipt(
        source_url=source_url, final_url=source_url, content=content,
        publisher=publisher, transport=transport, content_type="text/html",
        http_status=200, observed_at=known_at,
        extractor_version="test-extractor.v1", parser_version=parser_version,
        r2_object_key=None,
    )
    return fms.build_observation(
        case_key=case_key, source_surface=source_surface, kind=kind,
        receipt=receipt, known_at=known_at, version=version, fields=fields,
    )


def _state_observation(name: str, url: str, *, fallback: bool = False) -> dict:
    content = _read_bytes(f"state/{name}.html")
    fields = fms.parse_state_article(content.decode("utf-8"), source_url=url)
    case_key = (
        fms.case_key_fallback(url)
        if fallback
        else fms.case_key_for_transmittal(fields["transmittal_number"])
    )
    return _make_observation(
        case_key=case_key, source_surface="state", kind="listing_article",
        source_url=url, content=content, fields=fields,
    )


def _dsca_observation(name: str, url: str) -> dict:
    content = _read_bytes(f"dsca/{name}.html")
    fields = fms.parse_dsca_article(content.decode("utf-8", errors="replace"), source_url=url)
    case_key = fms.case_key_for_transmittal(fields["transmittal_number"])
    return _make_observation(
        case_key=case_key, source_surface="dsca", kind="listing_article",
        source_url=url, content=content, fields=fields,
    )


def _fr_observation(doc: str, url: str) -> dict | None:
    content = _read_bytes(f"fr/{doc}.txt")
    fields = fms.parse_fr_document(content.decode("utf-8"), source_url=url)
    if fields["classification"] != "original":
        return None
    case_key = fms.case_key_for_transmittal(fields["transmittal_number"])
    return _make_observation(
        case_key=case_key, source_surface="federal_register", kind="fr_raw_text",
        source_url=url, content=content, fields=fields,
    )


def _fr_correction_observation(doc: str, url: str) -> dict:
    content = _read_bytes(f"fr/{doc}.txt")
    text = content.decode("utf-8")
    classification = fms.classify_fr_document(text)
    assert classification["classification"] == "correction"
    year, seq = classification["bracket"].split("-", 1)
    target = fms.normalize_transmittal(year, seq)
    case_key = fms.case_key_for_transmittal(target)
    return _make_observation(
        case_key=case_key, source_surface="federal_register", kind="fr_correction",
        source_url=url, content=content, fields={"bracket": classification["bracket"]},
    )


def _base_graph_kwargs(**overrides) -> dict:
    kwargs = dict(
        as_of="2026-08-25",
        scope_delivered_from="2026-01-01",
        scope_delivered_through="2026-08-25",
        fr_publication_from="2026-01-01",
        fr_publication_through="2026-08-25",
        fr_denominator_transmittals=[],
        fr_docs_scanned=267,
        fr_amendments_excluded=1,
        fr_corrections=1,
        fr_out_of_scope_originals=0,
        fr_status="ok",
        state_listing_pages=7,
        state_qualifying_articles=54,
        state_status="ok",
        dsca_articles_staged=14,
        dsca_status="ok",
        history_disclosure="In-scope 2026 DSCA articles + the 26-13 certification PDF only.",
        generated_at="2026-08-26T00:00:00Z",
    )
    kwargs.update(overrides)
    return kwargs


def _full_observation_set() -> list[dict]:
    """The seven-transmittal population used across most positive tests."""
    return [
        _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/"),
        _dsca_observation("dsca-4399552", "https://www.dsca.mil/x/25-105/"),
        _state_observation(
            "sweden-m142-high-mobility-artillery-rocket-systems",
            "https://www.state.gov/x/sweden-m142/",
        ),
        _state_observation(
            "kuwait-lower-tier-air-and-missile-defense-sensor-radars",
            "https://www.state.gov/x/kuwait-lower-tier/",
        ),
        _state_observation(
            "australia-f-a-18f-ea-18g-growler-aircraft-training",
            "https://www.state.gov/x/australia-growler/",
        ),
        _state_observation(
            "singapore-hellfire-missiles", "https://www.state.gov/x/singapore-hellfire/",
            fallback=True,
        ),
        _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278"),  # 26-23 Jordan
        _fr_observation("2026-09109", "https://www.federalregister.gov/d/2026-09109"),  # 26-28 Japan
        _fr_observation("2026-07237", "https://www.federalregister.gov/d/2026-07237"),  # 26-27 Sweden join
        _fr_observation("2026-09003", "https://www.federalregister.gov/d/2026-09003"),  # 26-24 Singapore
    ]


def _full_graph() -> dict:
    observations = _full_observation_set()
    return fms_cases.build_fms_case_graph(
        observations=observations,
        **_base_graph_kwargs(fr_denominator_transmittals=["26-23", "26-28", "26-27", "26-24"]),
    )


def _case(graph: dict, case_key: str) -> dict:
    for case in graph["cases"]:
        if case["case_key"] == case_key:
            return case
    raise AssertionError(f"case {case_key!r} not found in graph")


def _capture_build_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the kwargs ``run_fms_acquisition`` calls ``build_fms_case_graph``
    with, while still running the real function underneath (spec §11b.13:
    T6/T14 must bind ``state_pm_bureau``'s typed status directly rather than
    inferring it from ``rc`` alone -- and a scenario whose FR denominator is
    empty never gets far enough to WRITE a graph, so the only way to observe
    the State branch's own typed status is to intercept the call).
    """
    captured: dict = {}
    original = fms_cases.build_fms_case_graph

    def _capturing(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(live.fms_cases, "build_fms_case_graph", _capturing)
    return captured


# ---------------------------------------------------------------------------
# Contract sweep: every schema file in contracts/ parses as valid JSON Schema,
# and the FMS graph the full fixture population produces validates clean.
# ---------------------------------------------------------------------------


def test_contract_schemas_all_parse_as_valid_json_schema() -> None:
    contracts_dir = Path(__file__).parent.parent / "contracts"
    checked = 0
    for schema_path in contracts_dir.rglob("*.schema.json"):
        value = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(value)
        checked += 1
    assert checked > 10  # sanity: we actually swept a real population


def test_fms_case_schema_validates_the_full_fixture_population() -> None:
    graph = _full_graph()
    _validate_graph(graph)
    assert graph["contract"] == "government_fms_case.v1"
    assert re_fullmatch_content_id(graph["content_id"])


def re_fullmatch_content_id(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"grfms1-[a-f0-9]{24}", value))


# ---------------------------------------------------------------------------
# Canary assertions (mission "NOT DONE UNLESS")
# ---------------------------------------------------------------------------


class TestCanaries:
    def test_canary_a_26_13_dsca_value(self) -> None:
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-13")
        assert case["estimated_notification_value"] == 9_000_000_000
        assert case["customer_country"] == "Kingdom of Saudi Arabia"
        assert case["stage"] == "congressional_notification"
        assert case["later_stages"] == "stage_not_observed"
        assert case["clocks"]["official_notification_date"] == {
            "value": "2026-01-30", "provenance": "dsca_body_dateline",
        }

    def test_recovery_case_26_23_fr_only(self) -> None:
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-23")
        assert case["source_coverage"]["classification"] == "fr_only"
        assert case["source_coverage"]["web_presence"] is False
        assert case["estimated_notification_value"] == 280_000_000
        assert case["clocks"]["official_notification_date"] == {
            "value": "2026-02-26", "provenance": "fr_delivered_to_congress",
        }
        assert case["capability_title"] is None  # never synthesized (T-battery, spec §4)

    def test_joined_case_26_27_sweden(self) -> None:
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-27")
        assert case["source_coverage"]["classification"] == "state_and_fr"
        assert case["estimated_notification_value"] == 930_000_000
        assert case["clocks"]["official_notification_date"] == {
            "value": "2026-03-10", "provenance": "fr_delivered_to_congress",
        }
        assert case["clocks"]["official_web_publication_date"] == {
            "value": "2026-03-10", "provenance": "state_header_date",
        }
        assert case["contractors"] == [{
            "name_as_printed": "Lockheed Martin",
            "location_as_printed": "Grand Prairie, Texas",
            "identity_state": "not_reviewed", "issuer_ref": None,
        }]


# ---------------------------------------------------------------------------
# Freeze T1-T14
# ---------------------------------------------------------------------------


class TestFreezeKillTests:
    def test_t1_stage_is_never_labeled_a_completed_sale(self) -> None:
        graph = _full_graph()
        forbidden = ("awarded", "sale completed", "signed loa", "implemented case")
        blob = json.dumps(graph).casefold()
        for word in forbidden:
            assert word not in blob
        for case in graph["cases"]:
            assert case["stage"] == "congressional_notification"
            assert case["later_stages"] == "stage_not_observed"

    def test_t2_value_never_labeled_award_obligation_backlog_revenue_cash(self) -> None:
        graph = _full_graph()
        for case in graph["cases"]:
            assert set(case) == {
                "case_key", "transmittal_number", "identity_basis", "case_identity_state",
                "aliases", "customer_country", "capability_title", "source_item_enumeration",
                "stage", "later_stages", "advancement_condition", "estimated_notification_value",
                "currency", "source_caveat", "value_provenance", "contractors", "contractor_note",
                "program_links", "clocks", "source_coverage", "observations", "case_state",
            }
        # A mutation that bolts on an aggregate-flavored field is rejected by
        # the contract's additionalProperties:false at the case level.
        mutated = copy.deepcopy(graph)
        mutated["cases"][0]["award_value_usd"] = mutated["cases"][0]["estimated_notification_value"]
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(mutated)

    def test_t3_no_review_period_arithmetic_ever_advances_stage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Real proof: the case-level stage function takes NO time input at
        # all, so it cannot compute elapsed-time/review-period arithmetic —
        # rebuild the hostile canary (~7 months elapsed at freeze time) and
        # confirm its stage is untouched.
        graph = _full_graph()
        canary = _case(graph, "fms:transmittal:26-13")
        assert canary["stage"] == "congressional_notification"

        # Negative proof: monkeypatch the stage function to a buggy
        # elapsed-time implementation and show the resulting case fails
        # contract validation (stage is a `const`, spec §4/§16 T3).
        def _buggy_elapsed_time_stage(observations):
            return "loa_offered"  # simulates "review period elapsed -> advance"

        monkeypatch.setattr(fms_cases, "_stage_for_case", _buggy_elapsed_time_stage)
        mutated_graph = _full_graph()
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(mutated_graph)

    def test_t4_no_ticker_minted_from_contractor_prose(self) -> None:
        graph = _full_graph()
        for case in graph["cases"]:
            for contractor in case["contractors"]:
                assert contractor["identity_state"] == "not_reviewed"
                assert contractor["issuer_ref"] is None
        # Mutation: a contractor claiming a reviewed issuer_ref fails the
        # contract's const/null requirements.
        mutated = copy.deepcopy(graph)
        for case in mutated["cases"]:
            if case["contractors"]:
                case["contractors"][0]["identity_state"] = "reviewed"
                case["contractors"][0]["issuer_ref"] = "NASDAQ:LMT"
                break
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(mutated)

    def test_t5_no_string_similarity_reviewed_program_link(self) -> None:
        graph = _full_graph()
        for case in graph["cases"]:
            assert case["program_links"] == [fms_cases.PROGRAM_LINK_NOT_REVIEWED]
        mutated = copy.deepcopy(graph)
        mutated["cases"][0]["program_links"] = [{
            "state": "reviewed", "reason_code": None,
            "program_id": "acq-program:patriot-pac3",
            "program_case_link_id": "prog-case:aaaaaaaaaaaa",
            "ontology_graph_id": "program-ontology:v1",
        }]
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(mutated)

    def test_t6_state_fetch_failure_is_typed_source_unavailable_never_stale_as_current(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _RaisingSession:
            def get(self, url, **kwargs):
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage")
                raise AssertionError(f"unexpected fetch in this test: {url}")

        # DSCA staged replay comes from the real committed bytes; FR from a
        # local fixture-backed fake session so the test never hits the network.
        class _FrOnlySession(_RaisingSession):
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({"results": []})
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage")
                raise AssertionError(f"unexpected fetch: {url}")

        captured = _capture_build_kwargs(monkeypatch)
        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_FrOnlySession(),
            observed_at=RECEIPT_AT,
            staged_dir=Path("data/government_revenue/fms_staged_objects").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        # FR sweep found zero docs -> denominator empty -> coverage gate
        # refuses regardless of the State failure; the key assertion binds
        # `state_pm_bureau`'s typed status DIRECTLY (spec §11b.13) -- the
        # State branch must record "unavailable", never "ok", regardless of
        # whether the overall run goes on to publish or refuse.
        assert rc == 1
        assert captured["state_status"] == "unavailable"
        assert captured["state_status"] != "ok"
        graph_path = tmp_path / "data" / "government_revenue" / "fms_case_graph.json"
        assert not graph_path.exists()  # refused publish leaves nothing written

    def test_t7_non_official_transport_is_refused(self) -> None:
        with pytest.raises(live.FmsFetchRefused):
            live.fetch_official_resource(
                "https://www.google.com/search?q=arms+sale",
                allowed_hosts=(live.STATE_HOST,),
            )

    def test_t8_changed_bytes_append_a_version_never_mutate_predecessor(self) -> None:
        content = b"content-a"
        content2 = b"content-b"
        receipt1 = fms.build_receipt(
            source_url="https://www.state.gov/x/", final_url="https://www.state.gov/x/",
            content=content, publisher="p", transport="cli", content_type="text/html",
            http_status=200, observed_at="2026-01-01T00:00:00Z",
            extractor_version="e.v1", parser_version="p.v1", r2_object_key=None,
        )
        obs1 = fms.build_observation(
            case_key="fms:transmittal:26-27", source_surface="state", kind="listing_article",
            receipt=receipt1, known_at="2026-01-01T00:00:00Z", version=1, fields={"v": 1},
        )
        receipt2 = fms.build_receipt(
            source_url="https://www.state.gov/x/", final_url="https://www.state.gov/x/",
            content=content2, publisher="p", transport="cli", content_type="text/html",
            http_status=200, observed_at="2026-02-01T00:00:00Z",
            extractor_version="e.v1", parser_version="p.v1", r2_object_key=None,
        )
        obs2 = fms.build_observation(
            case_key="fms:transmittal:26-27", source_surface="state", kind="listing_article",
            receipt=receipt2, known_at="2026-02-01T00:00:00Z", version=1, fields={"v": 2},
        )
        merged = fms.append_observation_versions([obs1], [obs2])
        assert len(merged) == 2
        assert merged[0]["response_sha256"] == receipt1["response_sha256"]
        assert merged[0]["fields"] == {"v": 1}  # predecessor preserved verbatim
        assert merged[1]["response_sha256"] == receipt2["response_sha256"]
        assert merged[1]["version"] == 2

    def test_t9_fallback_identity_never_silently_replaced_or_backdated(self) -> None:
        fallback_key = fms.case_key_fallback("https://www.state.gov/x/singapore-hellfire/")
        record = fms.apply_identity_supersession(
            fallback_case_key=fallback_key, transmittal="26-24", at="2026-09-01T00:00:00Z",
        )
        assert record["fallback_case_key"] == fallback_key  # never rewritten
        assert record["new_case_key"] == "fms:transmittal:26-24"
        assert record["recorded_at"] == "2026-09-01T00:00:00+00:00"  # never backdated

        # Guard: the source key must actually BE a fallback key — a
        # transmittal-keyed case can never be "superseded" this way.
        with pytest.raises(ValueError):
            fms.apply_identity_supersession(
                fallback_case_key="fms:transmittal:26-24", transmittal="26-24", at="2026-09-01T00:00:00Z",
            )

    def test_t10_missing_value_is_null_never_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Real proof: after the amended value grammar (spec §5), all 46/46
        # State corpus articles + 14/14 staged DSCA articles carry a
        # parseable value (verified by full-corpus survey below) — so the
        # "genuinely absent" real-fixture example the original packet used
        # (Kuwait) no longer applies; absence is instead proven at the
        # grammar level directly, which is what "genuinely absent -> null"
        # actually means (spec §5: "Genuinely absent -> null").
        no_value_text = "This notice describes a proposed sale with no stated dollar figure anywhere."
        value, conflicted = fms._extract_value_with_conflict(no_value_text)
        assert value is None
        assert conflicted is False

        # Negative proof: monkeypatch parse_money_amount to coerce to 0 and
        # show the contract's `"minimum": 1` guard refuses the resulting case.
        def _coerce_to_zero(raw, unit):
            return 0

        monkeypatch.setattr(fms, "parse_money_amount", _coerce_to_zero)
        content2 = _read_bytes("state/sweden-m142-high-mobility-artillery-rocket-systems.html")
        mutated_fields = fms.parse_state_article(
            content2.decode("utf-8"), source_url="https://www.state.gov/x/sweden/",
        )
        assert mutated_fields["estimated_notification_value"] == 0  # the injected bug
        obs = _make_observation(
            case_key="fms:transmittal:26-27", source_surface="state", kind="listing_article",
            source_url="https://www.state.gov/x/sweden/", content=content2, fields=mutated_fields,
        )
        graph = fms_cases.build_fms_case_graph(
            observations=[obs], **_base_graph_kwargs(fr_denominator_transmittals=["26-27"]),
        )
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(graph)

    def test_t11_one_transmittal_two_surfaces_produces_one_case(self) -> None:
        graph = _full_graph()
        keys = [c["case_key"] for c in graph["cases"]]
        assert keys.count("fms:transmittal:26-27") == 1  # State + FR
        joined = _case(graph, "fms:transmittal:26-27")
        assert {o["source_surface"] for o in joined["observations"]} == {"state", "federal_register"}

    def test_t12_never_emits_a_procurement_event_v2_row(self) -> None:
        graph = _full_graph()
        blob = json.dumps(graph)
        assert "government_procurement_event.v2" not in blob
        assert "award_change" not in blob
        assert "listed_company_impacts" not in blob

    def test_t13_no_cross_case_aggregate_of_notification_value_anywhere(self) -> None:
        graph = _full_graph()
        assert "coverage" in graph and "reconciliation" in graph["coverage"]
        # The coverage/reconciliation block carries only counts, never a
        # dollar total; grep for any key name that would smuggle one in.
        blob = json.dumps(graph["coverage"])
        for forbidden in ("total_value", "sum_value", "aggregate_value", "pipeline_value"):
            assert forbidden not in blob

        # Negative proof: bolt a cross-case total onto the graph and show the
        # top-level contract (additionalProperties:false) refuses it.
        mutated = copy.deepcopy(graph)
        mutated["total_estimated_notification_value"] = sum(
            c["estimated_notification_value"] or 0 for c in graph["cases"]
        )
        with pytest.raises(jsonschema.ValidationError):
            _validate_graph(mutated)

    def test_t14_listing_fetch_failure_never_becomes_empty_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FailingStateSession:
            def get(self, url, **kwargs):
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage")
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({"results": []})
                raise AssertionError(f"unexpected fetch: {url}")

        captured = _capture_build_kwargs(monkeypatch)
        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_FailingStateSession(),
            observed_at=RECEIPT_AT,
            staged_dir=Path("data/government_revenue/fms_staged_objects").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 1  # FR denominator empty -> refused; never publishes a
        # zero-row "current" graph.
        # Direct proof (spec §11b.13, §11b.6): the State branch's own typed
        # status is "unavailable", never "ok" -- a listing fetch failure can
        # never encode as the empty_valid ok+0 state.
        assert captured["state_status"] == "unavailable"
        assert captured["state_status"] != "ok"


class _JsonResponse:
    """Minimal fake ``requests.Response`` for FR API index tests."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# D6-B1 battery B1-B11
# ---------------------------------------------------------------------------


class TestD6B1Battery:
    def test_b1_26_23_jordan_fr_only_recovery_case(self) -> None:
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-23")
        assert case["source_coverage"]["classification"] == "fr_only"
        assert case["clocks"]["official_notification_date"]["value"] == "2026-02-26"
        assert case["customer_country"] == "Government of Jordan"
        assert case["estimated_notification_value"] == 280_000_000
        assert case["source_coverage"]["web_presence"] is False
        assert case["capability_title"] is None

    def test_b2_26_28_japan_present_despite_no_state_corpus_entry(self) -> None:
        # There is no State article for 26-28 anywhere in this fixture
        # corpus or the real corpus (post-migration doesn't cover it) —
        # removing the (nonexistent) State observation cannot remove this
        # case: it is minted purely from the FR original.
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-28")
        assert case["source_coverage"]["classification"] == "fr_only"
        assert case["estimated_notification_value"] == 340_000_000
        assert case["clocks"]["official_notification_date"]["value"] == "2026-03-24"

    def test_b3_26_27_sweden_join_official_dates_and_contractor(self) -> None:
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-27")
        assert case["clocks"]["official_notification_date"] == {
            "value": "2026-03-10", "provenance": "fr_delivered_to_congress",
        }
        assert case["clocks"]["official_web_publication_date"] == {
            "value": "2026-03-10", "provenance": "state_header_date",
        }
        assert case["estimated_notification_value"] == 930_000_000
        assert case["contractors"][0]["name_as_printed"] == "Lockheed Martin"
        assert case["contractors"][0]["location_as_printed"] == "Grand Prairie, Texas"
        assert case["contractors"][0]["identity_state"] == "not_reviewed"

    def test_b4_duplicate_across_dsca_and_fr_families_is_one_case_two_observations(self) -> None:
        observations = [
            _dsca_observation("dsca-4399552", "https://www.dsca.mil/x/25-105/"),
        ]
        fr_obs = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")
        # Reuse the Jordan FR doc's grammar shape but re-key it as 25-105 to
        # simulate an FR original covering the SAME transmittal as the DSCA
        # article, proving the join collapses to one case (T11 sharpened to
        # three families, spec B4). We build a synthetic-but-grammar-real FR
        # observation bound to case_key 25-105 directly from the real 25-105
        # DSCA content's own transmittal, using the real FR Jordan bytes only
        # as a distinct-content stand-in (content identity is irrelevant to
        # the case-join assertion under test).
        content = _read_bytes("fr/2026-07278.txt")
        case_key = fms.case_key_for_transmittal("25-105")
        synthetic_fr_obs = _make_observation(
            case_key=case_key, source_surface="federal_register", kind="fr_raw_text",
            source_url="https://www.federalregister.gov/d/synthetic-25-105",
            content=content, fields={"transmittal_number": "25-105", "customer_country": "Government of Ukraine"},
        )
        observations.append(synthetic_fr_obs)
        graph = fms_cases.build_fms_case_graph(
            observations=observations, **_base_graph_kwargs(fr_denominator_transmittals=["25-105"]),
        )
        assert len(graph["cases"]) == 1
        case = graph["cases"][0]
        assert case["case_key"] == "fms:transmittal:25-105"
        assert case["source_coverage"]["classification"] == "dsca_and_fr"
        assert len(case["observations"]) == 2

    def test_b5_fr_publication_lag_never_becomes_a_clock(self) -> None:
        # FR doc 2026-09109 (26-28) publishes 2026-05-07 but the delivered
        # date is 2026-03-24 — the clock must be the delivered date, and the
        # FR document's own publication date must never appear as a clock
        # value anywhere on the case.
        graph = _full_graph()
        case = _case(graph, "fms:transmittal:26-28")
        assert case["clocks"]["official_notification_date"]["value"] == "2026-03-24"
        blob = json.dumps(case["clocks"])
        assert "2026-05-07" not in blob

    def test_b6_state_unavailable_still_publishes_fr_dsca_truth(self, tmp_path: Path) -> None:
        calls: list[str] = []

        class _FrOkStateDownSession:
            def get(self, url, **kwargs):
                calls.append(url)
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage")
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [{
                            "document_number": "2026-07278",
                            "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                        }],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_FrOkStateDownSession(),
            observed_at=RECEIPT_AT,
            staged_dir=Path("data/government_revenue/fms_staged_objects").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0  # FR/DSCA denominator is non-empty and fully built -> publishes
        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        assert graph["coverage"]["sources"]["state_pm_bureau"]["status"] == "unavailable"
        assert graph["coverage"]["sources"]["federal_register"]["status"] == "ok"
        assert any(c["transmittal_number"] == "26-23" for c in graph["cases"])

    def test_b7_zero_or_unreconciled_denominator_refuses_to_publish(self) -> None:
        # (a) zero-doc FR sweep -> refuse
        with pytest.raises(fms_cases.FmsCoverageRefused):
            fms_cases.build_fms_case_graph(
                observations=[], **_base_graph_kwargs(fr_denominator_transmittals=[]),
            )
        # (b) a denominator transmittal with no built case -> refuse
        observations = [_dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")]
        with pytest.raises(fms_cases.FmsCoverageRefused):
            fms_cases.build_fms_case_graph(
                observations=observations,
                **_base_graph_kwargs(fr_denominator_transmittals=["26-13", "99-999"]),
            )
        # (c) FR status not ok -> refuse even with a nonempty denominator
        with pytest.raises(fms_cases.FmsCoverageRefused):
            fms_cases.build_fms_case_graph(
                observations=observations,
                **_base_graph_kwargs(fr_denominator_transmittals=["26-13"], fr_status="unavailable"),
            )
        # positive control: same inputs, denominator satisfied, FR ok -> publishes
        graph = fms_cases.build_fms_case_graph(
            observations=observations, **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        assert graph["coverage"]["reconciliation"]["denominator_unbuilt"] == []

    def test_b8_amendment_never_mints_or_touches_a_case_correction_attaches_only(self) -> None:
        text = _read_bytes("fr/2026-11403.txt").decode("utf-8")
        classification = fms.classify_fr_document(text)
        assert classification["classification"] == "amendment"
        assert classification["bracket"] == "26-1C"
        parsed = fms.parse_fr_document(text, source_url="https://www.federalregister.gov/d/2026-11403")
        assert parsed["transmittal_number"] is None  # never assigned a case identity
        assert parsed.get("estimated_notification_value") is None or "estimated_notification_value" not in parsed

        # Correction attaches to an EXISTING case by exact transmittal, never mints.
        observations = [_dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")]
        correction_url = "https://www.federalregister.gov/d/synthetic-26-13-correction"
        content = _read_bytes("fr/2026-00029.txt")
        correction_obs = _make_observation(
            case_key="fms:transmittal:26-13", source_surface="federal_register",
            kind="fr_correction", source_url=correction_url, content=content,
            fields={"bracket": "26-13"},
        )
        observations.append(correction_obs)
        graph = fms_cases.build_fms_case_graph(
            observations=observations, **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        case = _case(graph, "fms:transmittal:26-13")
        assert case["case_state"] == "corrected"
        assert len(case["observations"]) == 2

        # An orphan correction (no matching primary observation) never mints
        # a case of its own — combine it with an unrelated real case so the
        # coverage gate is satisfiable, and assert the orphan's key is absent.
        orphan_correction = _fr_correction_observation(
            "2026-00029", "https://www.federalregister.gov/d/2026-00029",
        )
        real_case_obs = _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")
        orphan_graph = fms_cases.build_fms_case_graph(
            observations=[real_case_obs, orphan_correction],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        assert [c["case_key"] for c in orphan_graph["cases"]] == ["fms:transmittal:26-13"]
        assert orphan_correction["case_key"] == "fms:transmittal:24-48"

    def test_b9_fallback_recovery_collision_flags_both_conflicted_never_merged(self) -> None:
        observations = [
            _state_observation(
                "singapore-hellfire-missiles", "https://www.state.gov/x/singapore-hellfire/",
                fallback=True,
            ),
            _fr_observation("2026-09003", "https://www.federalregister.gov/d/2026-09003"),  # 26-24 Singapore
        ]
        graph = fms_cases.build_fms_case_graph(
            observations=observations, **_base_graph_kwargs(fr_denominator_transmittals=["26-24"]),
        )
        assert len(graph["cases"]) == 2  # never auto-merged
        fallback_case = next(c for c in graph["cases"] if c["identity_basis"] == "url_fallback")
        recovery_case = next(c for c in graph["cases"] if c["case_key"] == "fms:transmittal:26-24")
        assert fallback_case["case_identity_state"] == "conflicted"
        assert recovery_case["case_identity_state"] == "conflicted"
        assert fallback_case["case_state"] == "conflicted"
        assert recovery_case["case_state"] == "conflicted"

    def test_b10_staged_replay_refuses_on_sha_mismatch(self, tmp_path: Path) -> None:
        import shutil

        bad_dir = tmp_path / "staged"
        bad_dir.mkdir()
        shutil.copy(FIXTURES / "dsca" / "manifest.json", bad_dir / "manifest.json")
        shutil.copy(FIXTURES / "dsca" / "dsca-4394629.html", bad_dir / "dsca-4394629.html")
        shutil.copy(FIXTURES / "dsca" / "dsca-4399552.html", bad_dir / "dsca-4399552.html")
        tampered = bad_dir / "dsca-4394629.html"
        tampered.write_bytes(tampered.read_bytes() + b"TAMPERED")

        with pytest.raises(live.FmsStagedIntegrityFailed):
            live.replay_staged_dsca_objects(bad_dir, store=None, observed_at=RECEIPT_AT)

    def test_b10b_certification_pdf_replay_emits_observation_on_26_13_case(self) -> None:
        """Canary A's certification PDF (freeze R3) must flow through the
        same staged-replay discipline as the articles and land as a
        ``certification_pdf`` observation on ``fms:transmittal:26-13``."""
        staged = FIXTURES / "dsca"
        manifest = live.load_staged_dsca_manifest(staged)
        cert_manifest = manifest["certification_pdf"]

        cert_receipt = live.replay_staged_certification_pdf(staged, store=None, observed_at=RECEIPT_AT)
        assert cert_receipt["response_sha256"] == "c7e3bcadda94f4f9014bd9eac70827f57bc1e60fe67c20a273074732a8af9c55"
        assert cert_receipt["transport"] == "browser_in_page_fetch_staged"
        assert cert_receipt["content_type"] == "application/pdf"

        cert_transmittal = fms.normalize_transmittal(*cert_manifest["transmittal"].split("-", 1))
        assert cert_transmittal == "26-13"
        cert_case_key = fms.case_key_for_transmittal(cert_transmittal)
        pdf_obs = fms.build_observation(
            case_key=cert_case_key, source_surface="dsca", kind="certification_pdf",
            receipt=cert_receipt, known_at=RECEIPT_AT, version=1,
            fields={"transmittal_number": cert_transmittal},
        )

        # Attach alongside the real 26-13 article observation and confirm the
        # engine groups both onto ONE case via case_key (never a separate
        # plane) -- this is the "verify the engine attaches it" check.
        article_obs = _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")
        assert article_obs["case_key"] == cert_case_key
        graph = fms_cases.build_fms_case_graph(
            observations=[article_obs, pdf_obs],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        case = _case(graph, "fms:transmittal:26-13")
        kinds = {o["kind"] for o in case["observations"]}
        assert kinds == {"listing_article", "certification_pdf"}
        pdf_row = next(o for o in case["observations"] if o["kind"] == "certification_pdf")
        assert pdf_row["response_sha256"] == "c7e3bcadda94f4f9014bd9eac70827f57bc1e60fe67c20a273074732a8af9c55"
        assert pdf_row["source_surface"] == "dsca"
        assert pdf_row["transport"] == "browser_in_page_fetch_staged"

    def test_b10c_tampered_certification_pdf_is_refused(self, tmp_path: Path) -> None:
        import shutil

        bad_dir = tmp_path / "staged"
        bad_dir.mkdir()
        shutil.copy(FIXTURES / "dsca" / "manifest.json", bad_dir / "manifest.json")
        shutil.copy(FIXTURES / "dsca" / "saudi-arabia-26-13-cn.pdf", bad_dir / "saudi-arabia-26-13-cn.pdf")
        tampered = bad_dir / "saudi-arabia-26-13-cn.pdf"
        tampered.write_bytes(tampered.read_bytes() + b"TAMPERED")

        with pytest.raises(live.FmsStagedIntegrityFailed):
            live.replay_staged_certification_pdf(bad_dir, store=None, observed_at=RECEIPT_AT)

    def test_b10d_acquisition_orchestration_replays_certification_pdf(self, tmp_path: Path) -> None:
        """End-to-end: run_fms_acquisition's DSCA branch must include the
        certification_pdf replay (the exact regression packet-2 review found
        — the PDF was fetched/staged but never replayed into the triad)."""

        class _FrOnlySession:
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [{
                            "document_number": "2026-07278",
                            "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                        }],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage (irrelevant here)")
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_FrOnlySession(),
            observed_at=RECEIPT_AT,
            staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0
        observations_path = tmp_path / "data" / "government_revenue" / "fms_observations.jsonl"
        rows = [json.loads(line) for line in observations_path.read_text().splitlines() if line.strip()]
        pdf_rows = [r for r in rows if r["kind"] == "certification_pdf"]
        assert len(pdf_rows) == 1
        assert pdf_rows[0]["case_key"] == "fms:transmittal:26-13"
        assert pdf_rows[0]["response_sha256"] == "c7e3bcadda94f4f9014bd9eac70827f57bc1e60fe67c20a273074732a8af9c55"
        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        case_26_13 = next(c for c in graph["cases"] if c["case_key"] == "fms:transmittal:26-13")
        assert "certification_pdf" in {o["kind"] for o in case_26_13["observations"]}

    def test_b11_r2_readback_mutation_is_refused(self, tmp_path: Path) -> None:
        class _CorruptingStore(LocalStore):
            def get_bytes_strict_bounded(self, key, *args, **kwargs):
                real = super().get_bytes_strict_bounded(key, *args, **kwargs)
                return (real or b"") + b"corrupted"

        store = _CorruptingStore(tmp_path / "store")
        with pytest.raises(live.FmsStoreReadbackFailed):
            live.put_and_verify_object(store, b"%PDF-1.4 fixture content", ext="pdf")

    @pytest.mark.needs_full_checkout("data")
    def test_b10_real_staged_manifest_bytes_pass_integrity(self) -> None:
        """End-to-end integrity check against the REAL committed staged
        bytes (not the sparse-safe test fixture copy)."""
        staged = Path("data/government_revenue/fms_staged_objects")
        receipts = live.replay_staged_dsca_objects(staged, store=None, observed_at=RECEIPT_AT)
        assert len(receipts) == 14
        pdf_receipt = live.replay_staged_certification_pdf(staged, store=None, observed_at=RECEIPT_AT)
        assert pdf_receipt["response_sha256"] == "c7e3bcadda94f4f9014bd9eac70827f57bc1e60fe67c20a273074732a8af9c55"


class _TextResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self._content = content
        self.status_code = status_code
        self.url = None
        self.headers = {"Content-Type": "text/plain"}

    def iter_content(self, chunk_size: int):
        yield self._content

    def close(self):
        pass


class _HtmlResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self._content = content
        self.status_code = status_code
        self.url = None
        self.headers = {"Content-Type": "text/html"}

    def iter_content(self, chunk_size: int):
        yield self._content

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Parse-survey invariants (spec §5 grammar classes)
# ---------------------------------------------------------------------------


class TestParseSurveyInvariants:
    def test_state_value_grammar_classes(self) -> None:
        # Amended spec §5 grammar, five receipted sentence classes; four of
        # the five occur verbatim in this packet's real fixtures (the fifth,
        # "estimated total cost is up to", is a direct grammar-regex
        # assertion below — no fixture in this packet's corpus happens to
        # carry it, though the full 46-article survey confirms 46/46
        # non-null under this grammar).
        cases = {
            # "estimated total cost is"
            "sweden-m142-high-mobility-artillery-rocket-systems": 930_000_000,
            "australia-f-a-18f-ea-18g-growler-aircraft-training": 250_000_000,
            "singapore-hellfire-missiles": 22_300_000,  # decimal million
            # "for an estimated cost of"
            "kuwait-lower-tier-air-and-missile-defense-sensor-radars": 8_000_000_000,
            # "The estimated cost is"
            "new-zealand-mk-54-torpedoes": 69_000_000,
            # "The total estimated cost is"
            "tunisia-border-security-project-phase-iii": 95_000_000,
        }
        for name, expected in cases.items():
            content = _read_bytes(f"state/{name}.html")
            fields = fms.parse_state_article(content.decode("utf-8"), source_url="https://www.state.gov/x/")
            assert fields["estimated_notification_value"] == expected, name
            assert fields["value_conflicted"] is False, name

    def test_state_value_grammar_up_to_class(self) -> None:
        # "estimated total cost is up to" — not present in this packet's
        # committed fixtures; direct grammar-regex assertion (the full
        # census documents this as one of the five receipted classes).
        text_up_to = "The estimated total cost is up to $1.2 billion for this potential sale."
        value, conflicted = fms._extract_value_with_conflict(text_up_to)
        assert value == 1_200_000_000
        assert conflicted is False

    def test_state_value_grammar_multiple_distinct_values_conflict(self) -> None:
        text = (
            "The estimated total cost is $250 million. "
            "Elsewhere the estimated cost is $300 million for the same notice."
        )
        value, conflicted = fms._extract_value_with_conflict(text)
        assert value is None
        assert conflicted is True

        # Same amount printed twice (e.g. header + body) is NOT a conflict.
        text_repeated = "The estimated total cost is $930 million. ... The estimated total cost is $930 million."
        value, conflicted = fms._extract_value_with_conflict(text_repeated)
        assert value == 930_000_000
        assert conflicted is False

    def test_state_contractor_grammar_classes(self) -> None:
        content = _read_bytes("state/sweden-m142-high-mobility-artillery-rocket-systems.html")
        fields = fms.parse_state_article(content.decode("utf-8"), source_url="https://www.state.gov/x/")
        assert fields["contractors"][0]["location_as_printed"] == "Grand Prairie, Texas"

        content = _read_bytes("state/australia-f-a-18f-ea-18g-growler-aircraft-training.html")
        fields = fms.parse_state_article(content.decode("utf-8"), source_url="https://www.state.gov/x/")
        assert fields["contractors"] == []
        assert fields["contractor_note"] == "There is no principal contractor associated with this potential sale."

    def test_state_contractor_grammar_multi_entry_and_for_this_effort_and_silent_absent(self) -> None:
        # Multi-entry list (";"-separated) — regex-grammar unit test (spec §5
        # LIST split on ";" / ", and "); not present in this packet's four
        # committed fixtures.
        multi = "The principal contractors for this effort will be Boeing, located in Seattle, WA; Raytheon, located in Tucson, AZ."
        contractors, note = fms._extract_contractors(multi)
        assert note is None
        assert [c["name_as_printed"] for c in contractors] == ["Boeing", "Raytheon"]
        assert contractors[0]["location_as_printed"] == "Seattle, WA"
        assert contractors[1]["location_as_printed"] == "Tucson, AZ"

        # Silent-absent: no contractor sentence AND no explicit-none sentence
        # at all — must fail closed to empty list + null note (never guessed).
        silent = "This proposed sale will improve the recipient's capability. No further contractor detail is printed."
        contractors, note = fms._extract_contractors(silent)
        assert contractors == []
        assert note is None

    def test_singapore_state_article_has_no_transmittal_uses_fallback_identity(self) -> None:
        content = _read_bytes("state/singapore-hellfire-missiles.html")
        fields = fms.parse_state_article(content.decode("utf-8"), source_url="https://www.state.gov/x/singapore/")
        assert fields["transmittal_number"] is None
        key = fms.case_key_fallback("https://www.state.gov/x/singapore/")
        assert key.startswith("fms:urlpath:")

    def test_country_precedence_rung1_title_prefix_wins_over_determination_sentence(self) -> None:
        # Sweden's determination sentence prints "Government of Sweden", but
        # rung (1) — the h1 title prefix, "Sweden" — takes precedence and is
        # NOT the honorific-qualified form (spec §5 amended precedence).
        content = _read_bytes("state/sweden-m142-high-mobility-artillery-rocket-systems.html")
        fields = fms.parse_state_article(content.decode("utf-8"), source_url="https://www.state.gov/x/sweden/")
        assert fields["customer_country"] == "Sweden"
        assert fms.split_title_country_prefix(fields["title"]) == "Sweden"

    def test_country_precedence_rung1_applies_to_dsca_too(self) -> None:
        content = _read_bytes("dsca/dsca-4394629.html")
        fields = fms.parse_dsca_article(content.decode("utf-8", errors="replace"), source_url="https://www.dsca.mil/x/")
        assert fields["customer_country"] == "Kingdom of Saudi Arabia"  # h1 already carries the honorific

    def test_country_precedence_rung2_fr_purchaser_for_fr_only_cases(self) -> None:
        # fr_only cases have no h1 title at all -> rung (1) is inapplicable;
        # the case-building layer sources customer_country from the FR
        # join's "(i) Prospective Purchaser" (rung 2) directly.
        text = _read_bytes("fr/2026-07278.txt").decode("utf-8")
        fields = fms.parse_fr_document(text, source_url="https://www.federalregister.gov/d/2026-07278")
        assert fields["customer_country"] == "Government of Jordan"

    def test_country_precedence_rung3_determination_sentence_fallback(self) -> None:
        # A title with no dash separator at all (rung 1 fails closed to
        # None) must fall through to the determination-sentence grammar
        # (rung 3), never straight to null while rung 3 evidence exists.
        assert fms.split_title_country_prefix("Untitled Notice With No Separator") is None
        body = (
            "The U.S. Department of State has made a determination approving a "
            "possible Foreign Military Sale to the Government of Peru to buy "
            "spare parts and related equipment."
        )
        country = fms._resolve_web_country("Untitled Notice With No Separator", body)
        assert country == "Government of Peru"

    def test_country_precedence_rung4_null_when_no_evidence_at_all(self) -> None:
        assert fms._resolve_web_country(None, "no determination sentence here") is None

    def test_country_precedence_dash_variant_em_dash_and_ascii_hyphen(self) -> None:
        # The real corpus is 60/60 en-dash (" – "); these are direct
        # grammar-regex assertions proving the other two frozen dash
        # separator forms also split correctly — no fixture in this
        # packet's corpus happens to use them.
        assert fms.split_title_country_prefix("Poland — F-16 Sustainment") == "Poland"
        assert fms.split_title_country_prefix("Chile - AH-1Z Viper Helicopters") == "Chile"
        # An in-word hyphen with no surrounding whitespace must NOT split.
        assert fms.split_title_country_prefix("F/A-18F Super Hornet Spares") is None

    def test_country_precedence_mis_key_guard_tolerates_honorific_difference(self) -> None:
        # "Sweden" (title-prefix) and "Government of Sweden" (FR purchaser)
        # are the SAME country and must never trip the mis-key guard.
        assert fms.check_mis_key("Sweden", "Government of Sweden") is False
        assert fms.check_mis_key("Kingdom of Saudi Arabia", "Kingdom of Saudi Arabia") is False
        # A genuinely different country DOES trip it.
        assert fms.check_mis_key("Sweden", "Government of Norway") is True

    def test_fallback_collision_tolerates_honorific_difference(self) -> None:
        # Census instance (spec §2): FR 26-24 "Government of Singapore" <->
        # singapore-hellfire-missiles title-prefix "Singapore".
        assert fms.fallback_collision("Singapore", "Government of Singapore") is True
        assert fms.fallback_collision("Singapore", "Government of Malaysia") is False

    def test_dsca_caveat_present_on_both_staged_fixture_articles(self) -> None:
        for name in ("dsca-4394629", "dsca-4399552"):
            content = _read_bytes(f"dsca/{name}.html")
            fields = fms.parse_dsca_article(content.decode("utf-8", errors="replace"), source_url="https://www.dsca.mil/x/")
            assert fields["source_caveat"] is not None
            assert "highest estimated quantity" in fields["source_caveat"]

    def test_fr_amendment_exclusion_including_phantom_26_0_trap(self) -> None:
        assert fms.classify_fr_bracket("26-0") == "original"  # NOT phantom by itself...
        assert fms.classify_fr_bracket("26-0G") == "amendment"  # ...but the letter suffix IS
        assert fms.classify_fr_bracket("0M-25") == "amendment"
        assert fms.classify_fr_bracket("26-13") == "original"

    def test_fr_correction_docs_never_in_denominator(self) -> None:
        text = _read_bytes("fr/2026-00029.txt").decode("utf-8")
        classification = fms.classify_fr_document(text)
        assert classification["classification"] == "correction"
        # A correction never contributes a transmittal_number for the
        # denominator (only "original" classifications do, per parse_fr_document).
        parsed = fms.parse_fr_document(text, source_url="https://www.federalregister.gov/d/2026-00029")
        assert parsed.get("transmittal_number") is None

    def test_unicode_dash_variants_normalize_identically(self) -> None:
        variants = [
            "Transmittal No. 26-27", "Transmittal No. 26‐27", "Transmittal #26‑27",
        ]
        for text in variants:
            info = fms.detect_transmittals(text)
            assert info["transmittals"] == ["26-27"], text

    def test_multiple_distinct_transmittals_conflict(self) -> None:
        info = fms.detect_transmittals("Transmittal No. 26-27 ... Transmittal No. 26-99")
        assert info["conflicted"] is True
        assert set(info["transmittals"]) == {"26-27", "26-99"}


# ---------------------------------------------------------------------------
# §11b post-red-team amendments (B3, M4-M10, L12-L17)
# ---------------------------------------------------------------------------


class TestPostRedTeamAmendments:
    def test_b3_receipt_idempotence_two_run_is_a_genuine_no_op(self, tmp_path: Path) -> None:
        """spec §11b.3: a re-run over UNCHANGED bytes appends ZERO new
        receipt rows. The receipt's own identity folds ``observed_at``
        (always fresh per run), so without consulting the timestamp-free
        ``receipt_is_duplicate`` predicate before appending, every re-run
        doubles the receipts plane regardless of the wire (review measured
        16 -> 32 against this exact real staged/FR corpus shape)."""

        class _FrOkSession:
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [{
                            "document_number": "2026-07278",
                            "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                        }],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                if "state.gov" in url:
                    raise ConnectionError("irrelevant to this test")
                raise AssertionError(f"unexpected fetch: {url}")

        base_kwargs = dict(
            root=tmp_path, store=None, session=_FrOkSession(),
            staged_dir=Path("data/government_revenue/fms_staged_objects").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        receipts_path = tmp_path / "data" / "government_revenue" / "fms_collection_receipts.jsonl"
        observations_path = tmp_path / "data" / "government_revenue" / "fms_observations.jsonl"

        rc1 = live.run_fms_acquisition(observed_at=RECEIPT_AT, **base_kwargs)
        assert rc1 == 0
        first_receipts = len(receipts_path.read_text().splitlines())
        first_observations = len(observations_path.read_text().splitlines())
        # 14 real staged DSCA articles + 1 certification PDF + 1 FR original.
        assert first_receipts == 16

        # Second run: SAME bytes, a LATER observed_at (the realistic re-run
        # shape -- only the wall-clock timestamp changes).
        rc2 = live.run_fms_acquisition(observed_at="2026-08-27T00:00:00Z", **base_kwargs)
        assert rc2 == 0
        second_receipts = len(receipts_path.read_text().splitlines())
        second_observations = len(observations_path.read_text().splitlines())
        assert second_receipts == first_receipts == 16  # 16 -> 16, never 16 -> 32
        assert second_observations == first_observations  # observations plane already no-oped

    def test_m5_empty_valid_only_when_listing_fetch_and_parse_succeeded(self, tmp_path: Path) -> None:
        """spec §11b.6: ``state_pm_bureau.status`` may be ``ok`` with
        ``qualifying_articles: 0`` ONLY when the listing fetch+parse
        succeeded; a fetch failure with zero rows must be ``unavailable``,
        never ``ok``."""
        empty_listing_html = b"<html><body>No releases posted this month.</body></html>"

        class _EmptyButOkListingSession:
            def get(self, url, **kwargs):
                if "state.gov" in url:
                    return _HtmlResponse(empty_listing_html)
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [{
                            "document_number": "2026-07278",
                            "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                        }],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_EmptyButOkListingSession(),
            observed_at=RECEIPT_AT, staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0
        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        state_source = graph["coverage"]["sources"]["state_pm_bureau"]
        assert state_source["status"] == "ok"
        assert state_source["qualifying_articles"] == 0

        class _FailingListingSession:
            def get(self, url, **kwargs):
                if "state.gov" in url:
                    raise ConnectionError("simulated State outage")
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [{
                            "document_number": "2026-07278",
                            "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                        }],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                raise AssertionError(f"unexpected fetch: {url}")

        rc2 = live.run_fms_acquisition(
            root=tmp_path / "second", store=None, session=_FailingListingSession(),
            observed_at=RECEIPT_AT, staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc2 == 0
        graph2 = json.loads((tmp_path / "second" / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        state_source2 = graph2["coverage"]["sources"]["state_pm_bureau"]
        assert state_source2["status"] == "unavailable"
        assert state_source2["qualifying_articles"] == 0

    def test_m6_correction_with_letter_suffixed_bracket_is_excluded_not_crashed(self, tmp_path: Path) -> None:
        """spec §11b.9: a correction doc whose OWN bracket fails the numeric
        original grammar (``26-1C``, ``0M-25`` family) is excluded with a
        typed reason exactly like an amendment notice -- never an uncaught
        ``ValueError`` from ``normalize_transmittal`` crashing acquisition."""
        synthetic_text = (
            "[Public Notice: 0000]\n"
            "[Transmittal No. 26-1C]\n"
            "DEPARTMENT OF STATE\n"
            "ACTION: Arms sales notice; correction\n\n"
            "SUMMARY: This corrects a previously published amendment notice.\n"
        ).encode("utf-8")

        class _LetterSuffixCorrectionSession:
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [
                            {
                                "document_number": "2026-07278",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                            },
                            {
                                "document_number": "2026-99999",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-99999.txt",
                            },
                        ],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                if "2026-99999.txt" in url:
                    return _TextResponse(synthetic_text)
                if "state.gov" in url:
                    raise ConnectionError("irrelevant to this test")
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_LetterSuffixCorrectionSession(),
            observed_at=RECEIPT_AT, staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0  # never crashes; denominator satisfied by the real 26-23 original
        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        assert graph["coverage"]["sources"]["federal_register"]["amendments_excluded"] == 1
        assert not any(c["transmittal_number"] == "26-1C" for c in graph["cases"])

    def test_m8_state_sweep_hitting_max_pages_cap_with_entries_present_is_typed_failure(self) -> None:
        """spec §11b.4: reaching the page cap while the last page STILL had
        entries can never be confirmed complete -- typed failure, never a
        silent partial-coverage "ok"."""
        qualifying_html = (
            '<li class="collection-result">'
            '<p class="collection-result__date">Foreign Military Sales: Congressional Notification</p>'
            '<a href="https://www.state.gov/x/still-more/" class="collection-result__link">Still More – Widget</a>'
            '</li>'
        ).encode("utf-8")

        class _AlwaysQualifyingSession:
            def get(self, url, **kwargs):
                return _HtmlResponse(qualifying_html)

        with pytest.raises(live.FmsFetchRefused):
            live.sweep_state_qualifying_articles(session=_AlwaysQualifyingSession(), max_pages=2)

    def test_m8_case_outside_the_population_window_is_excluded_from_the_graph(self) -> None:
        """spec §11b.4: a case whose population clock falls outside
        [2026-01-01, as_of] is excluded from the graph entirely."""
        out_of_window_case_key = fms.case_key_for_transmittal("30-2")
        out_of_window_obs = _make_observation(
            case_key=out_of_window_case_key, source_surface="state", kind="listing_article",
            source_url="https://www.state.gov/x/30-2/", content=b"state-out-of-window",
            fields={
                "transmittal_number": "30-2", "identity_conflicted": False, "value_conflicted": False,
                "customer_country": "Testland", "title": "Testland – Old Widget",
                "official_web_publication_date": "2025-11-01",  # before the 2026-01-01 population start
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        in_window_obs = _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")
        graph = fms_cases.build_fms_case_graph(
            observations=[out_of_window_obs, in_window_obs],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        case_keys = {c["case_key"] for c in graph["cases"]}
        assert "fms:transmittal:26-13" in case_keys
        assert out_of_window_case_key not in case_keys

    def test_m10_freshness_is_worst_of_fr_and_state_status(self, tmp_path: Path) -> None:
        """spec §11b.7: ``_fms_freshness`` reports the WORST-of the FR and
        State source statuses (via census freshness.py's ``_STATUS_RANK``),
        never FR alone -- a State-side ``partial`` used to be invisible."""
        import shutil

        graph = _full_graph()
        graph["coverage"]["sources"]["state_pm_bureau"]["status"] = "partial"
        graph["content_id"] = fms_cases.fms_case_graph_content_id(graph)

        contracts_dir = tmp_path / "contracts" / "government_revenue"
        contracts_dir.mkdir(parents=True)
        shutil.copy(SCHEMA_PATH, contracts_dir / "government_fms_case.v1.schema.json")
        data_dir = tmp_path / "data" / "government_revenue"
        data_dir.mkdir(parents=True)
        (data_dir / "fms_case_graph.json").write_text(json.dumps(graph), encoding="utf-8")

        result = metrics._fms_freshness(tmp_path)
        assert result is not None
        assert result["status"] == "partial"  # FR alone is "ok" here

    def test_l14_case_key_normalizes_leading_zero_before_minting(self) -> None:
        assert fms.case_key_for_transmittal("26-013") == fms.case_key_for_transmittal("26-13")
        assert fms.case_key_for_transmittal("26-013") == "fms:transmittal:26-13"

    def test_l15_mis_keyed_surfaces_produce_conflicted_case_identity(self) -> None:
        """Case-graph-level proof (spec §11b.13): two surfaces disagreeing
        materially on ``customer_country`` under one transmittal must yield
        ``case_identity_state: conflicted`` in the BUILT graph, not merely
        in the isolated ``check_mis_key`` unit."""
        case_key = fms.case_key_for_transmittal("31-7")
        state_obs = _make_observation(
            case_key=case_key, source_surface="state", kind="listing_article",
            source_url="https://www.state.gov/x/31-7/", content=b"state-mk",
            fields={
                "transmittal_number": "31-7", "identity_conflicted": False, "value_conflicted": False,
                "customer_country": "Norway", "title": "Norway – Widget C",
                "official_web_publication_date": "2026-03-01",
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        dsca_obs = _make_observation(
            case_key=case_key, source_surface="dsca", kind="listing_article",
            source_url="https://www.dsca.mil/x/31-7/", content=b"dsca-mk",
            fields={
                "transmittal_number": "31-7", "identity_conflicted": False,
                "customer_country": "Denmark", "title": "Denmark – Widget C",
                "official_notification_date": "2026-03-03", "official_web_publication_date": None,
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        filler = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")
        graph = fms_cases.build_fms_case_graph(
            observations=[state_obs, dsca_obs, filler],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-23"]),
        )
        case = _case(graph, case_key)
        assert case["case_identity_state"] == "conflicted"

    def test_l16_state_plus_dsca_without_fr_is_multi_surface(self) -> None:
        case_key = fms.case_key_for_transmittal("30-1")
        dsca_obs = _make_observation(
            case_key=case_key, source_surface="dsca", kind="listing_article",
            source_url="https://www.dsca.mil/x/30-1/", content=b"dsca-multi",
            fields={
                "transmittal_number": "30-1", "identity_conflicted": False,
                "customer_country": "Testland", "title": "Testland – Widget A",
                "official_notification_date": "2026-02-01", "official_web_publication_date": None,
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        state_obs = _make_observation(
            case_key=case_key, source_surface="state", kind="listing_article",
            source_url="https://www.state.gov/x/30-1/", content=b"state-multi",
            fields={
                "transmittal_number": "30-1", "identity_conflicted": False, "value_conflicted": False,
                "customer_country": "Testland", "title": "Testland – Widget A",
                "official_web_publication_date": "2026-02-05",
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        filler = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")
        graph = fms_cases.build_fms_case_graph(
            observations=[dsca_obs, state_obs, filler],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-23"]),
        )
        case = _case(graph, case_key)
        assert case["source_coverage"]["classification"] == "multi_surface"
        assert set(case["source_coverage"]["surfaces"]) == {"state", "dsca"}

    def test_l16_state_dsca_and_fr_all_three_is_multi_surface(self) -> None:
        case_key = fms.case_key_for_transmittal("26-23")
        fr_obs = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")
        dsca_obs = _make_observation(
            case_key=case_key, source_surface="dsca", kind="listing_article",
            source_url="https://www.dsca.mil/x/26-23/", content=b"dsca-triple",
            fields={
                "transmittal_number": "26-23", "identity_conflicted": False,
                "customer_country": "Government of Jordan", "title": "Jordan – Widget B",
                "official_notification_date": "2026-02-20", "official_web_publication_date": None,
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        state_obs = _make_observation(
            case_key=case_key, source_surface="state", kind="listing_article",
            source_url="https://www.state.gov/x/26-23/", content=b"state-triple",
            fields={
                "transmittal_number": "26-23", "identity_conflicted": False, "value_conflicted": False,
                "customer_country": "Government of Jordan", "title": "Jordan – Widget B",
                "official_web_publication_date": "2026-02-22",
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        graph = fms_cases.build_fms_case_graph(
            observations=[fr_obs, dsca_obs, state_obs],
            **_base_graph_kwargs(fr_denominator_transmittals=["26-23"]),
        )
        case = _case(graph, case_key)
        assert case["source_coverage"]["classification"] == "multi_surface"
        assert set(case["source_coverage"]["surfaces"]) == {"state", "dsca", "federal_register"}

    def test_l17_graph_known_at_is_the_max_observation_known_at(self) -> None:
        case_key = fms.case_key_for_transmittal("26-13")
        earlier = _make_observation(
            case_key=case_key, source_surface="dsca", kind="listing_article",
            source_url="https://www.dsca.mil/x/26-13/", content=b"dsca-known-at-v1",
            known_at="2026-01-30T00:00:00Z",
            fields={
                "transmittal_number": "26-13", "identity_conflicted": False,
                "customer_country": "Kingdom of Saudi Arabia", "title": "Saudi Arabia – Widget",
                "official_notification_date": "2026-01-30", "official_web_publication_date": None,
                "estimated_notification_value": None, "value_provenance": None,
                "source_caveat": None, "contractors": [], "contractor_note": None,
            },
        )
        later = _make_observation(
            case_key=case_key, source_surface="dsca", kind="certification_pdf",
            source_url="https://www.dsca.mil/x/26-13-cert/", content=b"dsca-known-at-v2",
            known_at="2026-08-20T00:00:00Z", fields={"transmittal_number": "26-13"},
        )
        graph = fms_cases.build_fms_case_graph(
            observations=[earlier, later], **_base_graph_kwargs(fr_denominator_transmittals=["26-13"]),
        )
        assert graph["known_at"] == "2026-08-20T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Production defect (run 32940175991): the FR denominator and the engine's
# population filter must share ONE membership predicate (spec §2, originals
# DELIVERED in the window) -- the first real main dispatch found 123 FR-lag
# originals (delivered before 2026-01-01 but published inside the FR API
# query window) in the denominator with no built case, refusing every run.
# ---------------------------------------------------------------------------


class TestFrLagDenominatorPredicate:
    def test_fr_lag_original_delivered_before_window_excluded_from_denominator(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        """An FR original PUBLISHED in the query window but DELIVERED
        2025-12-20 (before the 2026-01-01 population start) must never
        enter the denominator or mint an observation/receipt -- exactly
        the FR-lag class the production run found (26-5/26-10/26-11 style,
        delivered Dec 2025)."""
        out_of_scope_text = (
            "[Transmittal No. 26-5]\n"
            "DEPARTMENT OF STATE\n"
            "ACTION: Arms sales notice.\n\n"
            "(viii) Date Report Delivered to Congress: December 20, 2025\n"
        ).encode("utf-8")

        class _FrLagSession:
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [
                            {
                                "document_number": "2026-07278",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                            },
                            {
                                "document_number": "2026-00005",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-00005.txt",
                            },
                        ],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                if "2026-00005.txt" in url:
                    return _TextResponse(out_of_scope_text)
                if "state.gov" in url:
                    raise ConnectionError("irrelevant to this test")
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_FrLagSession(),
            observed_at=RECEIPT_AT, staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0  # denominator satisfied by the real 26-23 original; never refuses
        captured = capsys.readouterr()
        assert "::warning title=fms-fr-original-out-of-scope::" in captured.out

        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        fr_source = graph["coverage"]["sources"]["federal_register"]
        assert fr_source["out_of_scope_originals"] == 1
        assert not any(c["transmittal_number"] == "26-5" for c in graph["cases"])

        observations_path = tmp_path / "data" / "government_revenue" / "fms_observations.jsonl"
        rows = [json.loads(line) for line in observations_path.read_text().splitlines() if line.strip()]
        assert not any(r["case_key"] == "fms:transmittal:26-5" for r in rows)
        receipts_path = tmp_path / "data" / "government_revenue" / "fms_collection_receipts.jsonl"
        receipt_rows = [json.loads(line) for line in receipts_path.read_text().splitlines() if line.strip()]
        assert not any(r["source_url"].endswith("2026-00005.txt") for r in receipt_rows)

    def test_fr_original_with_no_parseable_delivered_date_is_excluded_fail_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        """An original with no parseable delivered-to-Congress date cannot
        prove population-window membership -- fail closed: excluded,
        counted, never mints, and warns with its own distinct title."""
        no_delivered_text = (
            "[Transmittal No. 26-6]\n"
            "DEPARTMENT OF STATE\n"
            "ACTION: Arms sales notice.\n\n"
            "SUMMARY: no delivered-date line is printed anywhere in this notice.\n"
        ).encode("utf-8")

        class _NoDeliveredSession:
            def get(self, url, **kwargs):
                if "federalregister.gov" in url and "documents.json" in url:
                    return _JsonResponse({
                        "results": [
                            {
                                "document_number": "2026-07278",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-07278.txt",
                            },
                            {
                                "document_number": "2026-00006",
                                "raw_text_url": "https://www.federalregister.gov/documents/full_text/text/2026/x/2026-00006.txt",
                            },
                        ],
                    })
                if "2026-07278.txt" in url:
                    return _TextResponse(_read_bytes("fr/2026-07278.txt"))
                if "2026-00006.txt" in url:
                    return _TextResponse(no_delivered_text)
                if "state.gov" in url:
                    raise ConnectionError("irrelevant to this test")
                raise AssertionError(f"unexpected fetch: {url}")

        rc = live.run_fms_acquisition(
            root=tmp_path, store=None, session=_NoDeliveredSession(),
            observed_at=RECEIPT_AT, staged_dir=(FIXTURES / "dsca").resolve(),
            publication_from="2026-01-01", publication_through="2026-08-25",
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "::warning title=fms-fr-original-no-delivered-date::" in captured.out

        graph = json.loads((tmp_path / "data" / "government_revenue" / "fms_case_graph.json").read_text())
        fr_source = graph["coverage"]["sources"]["federal_register"]
        assert fr_source["out_of_scope_originals"] == 1
        assert not any(c["transmittal_number"] == "26-6" for c in graph["cases"])

    def test_reconciliation_gate_reconciles_when_denominator_and_population_filter_share_the_predicate(
        self,
    ) -> None:
        """Positive control (B7 family, spec §2): a denominator that
        correctly EXCLUDES an FR-lag original (the collector's own new
        behavior) reconciles cleanly against the population-filtered
        cases -- proving the two now share one membership predicate."""
        in_scope_case = _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")
        filler_fr = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")  # 26-23
        graph = fms_cases.build_fms_case_graph(
            observations=[in_scope_case, filler_fr],
            **_base_graph_kwargs(
                # The FR-lag original (e.g. 26-5, delivered 2025-12-20) is
                # correctly OMITTED from the denominator -- exactly what
                # the fixed live collector now does before ever reaching
                # this function.
                fr_denominator_transmittals=["26-23"],
                fr_out_of_scope_originals=1,
            ),
        )
        assert graph["coverage"]["reconciliation"]["denominator_unbuilt"] == []
        assert graph["coverage"]["sources"]["federal_register"]["out_of_scope_originals"] == 1

    def test_reconciliation_gate_still_refuses_if_denominator_disagrees_with_the_population_filter(
        self,
    ) -> None:
        """Negative control reproducing the ORIGINAL production defect
        (run 32940175991) at the engine level: if a caller naively
        included an FR-lag original's transmittal in the denominator
        anyway, the population filter (applied independently of the
        denominator) still drops its case -- denominator_unbuilt is
        non-empty and the gate correctly refuses. This is the exact
        failure mode the collector-side fix (this file's session) now
        prevents by never adding such a transmittal in the first place."""
        in_scope_case = _dsca_observation("dsca-4394629", "https://www.dsca.mil/x/26-13/")
        filler_fr = _fr_observation("2026-07278", "https://www.federalregister.gov/d/2026-07278")  # 26-23
        out_of_window_fr_obs = _make_observation(
            case_key=fms.case_key_for_transmittal("26-5"), source_surface="federal_register",
            kind="fr_raw_text", source_url="https://www.federalregister.gov/d/2026-00005",
            content=b"fr-lag-negative-control",
            fields={
                "transmittal_number": "26-5", "official_notification_date": "2025-12-20",
                "customer_country": "Testland",
            },
        )
        with pytest.raises(fms_cases.FmsCoverageRefused):
            fms_cases.build_fms_case_graph(
                observations=[in_scope_case, filler_fr, out_of_window_fr_obs],
                **_base_graph_kwargs(fr_denominator_transmittals=["26-23", "26-5"]),
            )
