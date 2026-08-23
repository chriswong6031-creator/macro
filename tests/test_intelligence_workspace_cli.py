from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json

from engine.intelligence_workspace.contracts import (
    AdapterResult,
    CanonicalEntity,
    RightsDecision,
)
from engine.intelligence_workspace.resolver import DatapointResolver
from engine.intelligence_workspace.runtime import EXACT_ADAPTER_IDS, build_runtime
from engine.intelligence_workspace.adapters.company_intelligence import CompanyIntelligenceAdapter
from engine.intelligence_workspace.adapters.earnings import EarningsCalendarAdapter
from engine.intelligence_workspace.adapters.industry import IndustryAdapter
from engine.intelligence_workspace.adapters.quote import QuoteAdapter
from engine.intelligence_workspace.adapters.stage import StageAdapter
from engine.intelligence_workspace.adapters.technicals import TechnicalsAdapter
from engine.intelligence_workspace.adapters.theme import ThemeAdapter
from engine.intelligence_workspace.entity import DataOSIdentityNormalizer
from engine.intelligence_workspace.projection import ThemeRightsProjector
from scripts.resolve_datapoints import main


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


class CaptureResolver:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def resolve(self, request):
        self.requests.append(request)
        return tuple(self.result)


def _run(argv, resolver):
    stdout, stderr = StringIO(), StringIO()
    code = main(argv, resolver_factory=lambda: resolver, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_cli_emits_canonical_deterministic_json_and_preserves_symbol_request():
    result = [
        {
            "z": 2,
            "a": 1,
            "status": "available",
            "field_id": "market.price.last",
        }
    ]
    resolver = CaptureResolver(result)
    argv = [
        "--symbol", "aapl",
        "--field", "market.price.last",
        "--audience", "internal",
        "--consumer-use", "query",
    ]
    first = _run(argv, resolver)
    second = _run(argv, resolver)
    assert first[0] == second[0] == 0
    assert first[1] == second[1] == '[{"a":1,"field_id":"market.price.last","status":"available","z":2}]\n'
    assert first[2] == second[2] == ""
    assert resolver.requests[0] == {
        "entities": [{"type": "security", "symbol": "aapl"}],
        "field_ids": ["market.price.last"],
        "audience": "internal",
        "consumer_use": "query",
    }


def test_cli_supports_only_explicit_security_or_industry_identity_forms():
    resolver = CaptureResolver([])
    code, _, _ = _run(
        ["--security-id", "SEC:US-XNAS-AAPL", "--field", "stage.current"], resolver
    )
    assert code == 0
    assert resolver.requests[-1]["entities"] == [
        {"type": "security", "id": "SEC:US-XNAS-AAPL"}
    ]

    code, _, _ = _run(
        ["--industry-id", "Software", "--field", "industry.rank.percentile"], resolver
    )
    assert code == 0
    assert resolver.requests[-1]["entities"] == [
        {"type": "industry", "id": "Software"}
    ]


def test_cli_unknown_field_bad_audience_and_path_or_import_knobs_fail_before_factory():
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        return CaptureResolver([])

    for argv in (
        ["--symbol", "AAPL", "--field", "made.up.field"],
        ["--symbol", "AAPL", "--field", "market.price.last", "--audience", "public"],
        ["--symbol", "AAPL", "--field", "market.price.last", "--path", "/tmp/x"],
        ["--symbol", "AAPL", "--field", "market.price.last", "--adapter-import", "evil.mod"],
    ):
        stdout, stderr = StringIO(), StringIO()
        code = main(argv, resolver_factory=factory, stdout=stdout, stderr=stderr)
        assert code == 2
        assert stdout.getvalue() == ""
        assert json.loads(stderr.getvalue())["error"]["type"] == "CliUsageError"
    assert factory_calls == 0


def test_cli_future_cutoff_is_nonzero_before_identity_or_owner_io():
    class Identity:
        calls = 0

        def normalize_many(self, entities):
            self.calls += 1
            return [CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity")]

    class Owner:
        calls = 0

        def resolve_many(self, entities, specs, request, context):
            self.calls += 1
            return {}

    identity, owner = Identity(), Owner()
    resolver = DatapointResolver(
        identity_normalizer=identity,
        adapters={"quote": owner},
        clock=lambda: NOW,
    )
    code, stdout, stderr = _run(
        [
            "--symbol", "AAPL",
            "--field", "market.price.last",
            "--requested-as-of", "2026-08-24T00:00:00Z",
        ],
        resolver,
    )
    assert code == 2 and stdout == ""
    assert "future" in json.loads(stderr)["error"]["message"]
    assert identity.calls == 0 and owner.calls == 0


def test_cli_owner_absence_is_typed_success():
    resolver = CaptureResolver(
        [
            {
                "schema": "datapoint_value.v1",
                "field_id": "market.price.last",
                "status": "unavailable",
                "reason_code": "owner_missing",
                "value": None,
            }
        ]
    )
    code, stdout, stderr = _run(
        ["--symbol", "UNKNOWN", "--field", "market.price.last"], resolver
    )
    assert code == 0 and stderr == ""
    assert json.loads(stdout)[0]["reason_code"] == "owner_missing"


def test_cli_subscriber_uses_real_projection_and_cannot_leak_blocked_theme_value():
    class Identity:
        def normalize_many(self, entities):
            return [
                CanonicalEntity(
                    "security",
                    "SEC:US-XNAS-AAPL",
                    "us_equity",
                    alias_interpretation="current_alias_only",
                )
            ]

    class ThemeOwner:
        def resolve_many(self, entities, specs, request, context):
            spec = specs[0]
            return {
                ("security", entities[0].id, spec.field_id): AdapterResult(
                    value=["ltheme:finviz:ai"],
                    status="available",
                    reason_code=None,
                    unit="entity_refs",
                    observed_at="2026-08-22",
                    effective_at="2026-08-22",
                    as_of="2026-08-22",
                    freshness={"state": "fresh", "policy": "owner_native"},
                    quality={"state": "ok", "issues": []},
                    source={
                        "source_id": "theme_graph.current_memberships",
                        "owner": "theme_graph",
                        "license_class": "internal_only",
                        "dataset_id": None,
                        "source_family": "finviz_themes",
                    },
                    provenance={
                        "kind": "owner_relation",
                        "owner_field_key": "local_memberships",
                        "relationship": "MEMBER_OF",
                        "basis": "direct_source_relation",
                        "owner_artifact": "/private/theme/store",
                    },
                    rights_context={"source_families": ["finviz_themes"]},
                )
            }

    resolver = DatapointResolver(
        identity_normalizer=Identity(),
        adapters={"theme": ThemeOwner()},
        rights_projector=lambda *_: RightsDecision(False),
        clock=lambda: NOW,
    )
    code, stdout, stderr = _run(
        [
            "--symbol", "AAPL",
            "--field", "theme.local.memberships",
            "--audience", "subscriber",
            "--consumer-use", "query",
        ],
        resolver,
    )
    assert code == 0 and stderr == ""
    envelope = json.loads(stdout)[0]
    assert envelope["status"] == "rights_blocked"
    assert envelope["value"] is None
    assert "/private/theme/store" not in stdout


def test_runtime_composes_exact_static_owner_map_and_dynamic_theme_rights(tmp_path):
    runtime = build_runtime(
        repo_root=tmp_path,
        terminal_data_dir=tmp_path / "terminal",
        terminal_hub_url="http://127.0.0.1:3999",
    )
    assert tuple(runtime.adapters) == EXACT_ADAPTER_IDS == (
        "quote",
        "technicals",
        "stage",
        "industry",
        "earnings_calendar",
        "company_intelligence",
        "theme",
    )
    expected_types = {
        "quote": QuoteAdapter,
        "technicals": TechnicalsAdapter,
        "stage": StageAdapter,
        "industry": IndustryAdapter,
        "earnings_calendar": EarningsCalendarAdapter,
        "company_intelligence": CompanyIntelligenceAdapter,
        "theme": ThemeAdapter,
    }
    assert {key: type(value) for key, value in runtime.adapters.items()} == expected_types
    assert isinstance(runtime.identity_normalizer, DataOSIdentityNormalizer)
    assert runtime.identity_normalizer.root == tmp_path
    assert isinstance(runtime.rights_projector, ThemeRightsProjector)
    assert runtime.adapters["quote"].terminal_data_dir == tmp_path / "terminal"
    assert runtime.adapters["quote"].terminal_hub_url == "http://127.0.0.1:3999"
    assert runtime.adapters["stage"].vendor == "store"
    assert runtime.adapters["industry"].vendor == "store"
    assert runtime.adapters["earnings_calendar"].vendor == "store"
    assert runtime.adapters["company_intelligence"].vendor == "store"


def test_runtime_uses_existing_terminal_environment_convention(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_DATA_DIR", str(tmp_path / "env-terminal"))
    monkeypatch.setenv("TERMINAL_HUB_URL", "http://127.0.0.1:4888")
    runtime = build_runtime(repo_root=tmp_path)
    quote = runtime.adapters["quote"]
    assert quote.terminal_data_dir == tmp_path / "env-terminal"
    assert quote.terminal_hub_url == "http://127.0.0.1:4888"
