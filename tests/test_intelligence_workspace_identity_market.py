from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.intelligence_workspace.contracts import CanonicalEntity, EntityRequest, ResolutionRequest
from engine.intelligence_workspace.entity import (
    DataOSIdentityNormalizer,
    IdentityResolutionError,
    current_symbol_resolver,
    load_current_symbol_map,
)
from engine.intelligence_workspace.registry import load_registry
from engine.intelligence_workspace.resolver import (
    DatapointResolver,
    RequestContext,
    RequestValidationError,
)
from engine.intelligence_workspace.adapters.quote import QuoteAdapter
from engine.intelligence_workspace.adapters.technicals import TechnicalsAdapter


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _write_identity_root(
    root: Path,
    *,
    security_rows: list[dict] | None = None,
    alias_rows: list[dict] | None = None,
    industry_ids: tuple[str, ...] = ("Software",),
) -> Path:
    reference = root / "data/reference"
    reference.mkdir(parents=True)
    security_rows = security_rows or [
        {
            "security_id": "SEC:US-XNAS-AAPL",
            "issuer_id": "ISS:US-XNAS-AAPL",
            "issuer_state": "RESOLVED",
            "listing_key": "US-XNAS-AAPL",
            "security_state": None,
            "superseded_by": None,
        },
        {
            "security_id": "SEC:US-XNYS-MMC",
            "issuer_id": "ISS:US-XNYS-MMC",
            "issuer_state": "RESOLVED",
            "listing_key": "US-XNYS-MMC",
            "security_state": None,
            "superseded_by": None,
        },
    ]
    alias_rows = alias_rows or [
        {"vendor": "store", "vendor_symbol": "AAPL", "security_id": "SEC:US-XNAS-AAPL", "valid_from": None, "valid_to": None},
        {"vendor": "yahoo_fetch", "vendor_symbol": "AAPL", "security_id": "SEC:US-XNAS-AAPL", "valid_from": None, "valid_to": None},
        {"vendor": "store", "vendor_symbol": "MRSH", "security_id": "SEC:US-XNYS-MMC", "valid_from": None, "valid_to": None},
        {"vendor": "yahoo_fetch", "vendor_symbol": "MRSH", "security_id": "SEC:US-XNYS-MMC", "valid_from": None, "valid_to": None},
    ]
    pd.DataFrame(security_rows).to_parquet(reference / "security_master.parquet", index=False)
    pd.DataFrame(alias_rows).to_parquet(reference / "vendor_aliases.parquet", index=False)
    stage = root / "data/stage_analysis"
    stage.mkdir(parents=True)
    (stage / "industry_ranks.json").write_text(
        json.dumps(
            {
                "schema": "stage_industry_ranks.v1",
                "regions": {
                    "USA": [
                        {"industry_id": industry_id, "industry_name": industry_id}
                        for industry_id in industry_ids
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def _context() -> RequestContext:
    return RequestContext(generated_at=NOW, requested_as_of=None)


def _request(fields: tuple[str, ...]) -> ResolutionRequest:
    return ResolutionRequest(
        entities=(EntityRequest("security", id="SEC:US-XNAS-AAPL"),),
        field_ids=fields,
        audience="internal",
        consumer_use="query",
    )


def test_current_alias_and_explicit_sec_are_canonical_without_ticker_fallback(tmp_path):
    root = _write_identity_root(tmp_path)
    normalizer = DataOSIdentityNormalizer(root, today=lambda: date(2026, 8, 23))
    alias, explicit = normalizer.normalize_many(
        [
            EntityRequest("security", symbol="mrsh"),
            EntityRequest("security", id="SEC:US-XNAS-AAPL"),
        ]
    )
    assert alias.id == "SEC:US-XNYS-MMC"
    assert alias.alias_interpretation == "current_alias_only"
    assert explicit.id == "SEC:US-XNAS-AAPL"
    assert explicit.alias_interpretation is None

    with pytest.raises(IdentityResolutionError, match="unknown"):
        normalizer.normalize_many([EntityRequest("security", symbol="MMC")])
    with pytest.raises(IdentityResolutionError, match="malformed"):
        normalizer.normalize_many([EntityRequest("security", id="AAPL")])
    with pytest.raises(IdentityResolutionError, match="unknown canonical"):
        normalizer.normalize_many([EntityRequest("security", id="SEC:US-XNAS-MSFT")])


@pytest.mark.parametrize(
    "edge",
    [
        {"type": "security", "id": "SEC:CN-XSHG-600519"},
        {"type": "security", "symbol": "600519.SS"},
    ],
)
def test_non_us_explicit_or_current_alias_fails_before_market_adapter_io(tmp_path, edge):
    security_rows = [
        {
            "security_id": "SEC:US-XNAS-AAPL",
            "issuer_id": "ISS:US-XNAS-AAPL",
            "issuer_state": "RESOLVED",
            "listing_key": "US-XNAS-AAPL",
            "security_state": None,
            "superseded_by": None,
        },
        {
            "security_id": "SEC:CN-XSHG-600519",
            "issuer_id": "ISS:CN-XSHG-600519",
            "issuer_state": "RESOLVED",
            "listing_key": "CN-XSHG-600519",
            "security_state": None,
            "superseded_by": None,
        },
    ]
    alias_rows = [
        {
            "vendor": "store",
            "vendor_symbol": "AAPL",
            "security_id": "SEC:US-XNAS-AAPL",
            "valid_from": None,
            "valid_to": None,
        },
        {
            "vendor": "yahoo_fetch",
            "vendor_symbol": "AAPL",
            "security_id": "SEC:US-XNAS-AAPL",
            "valid_from": None,
            "valid_to": None,
        },
        {
            "vendor": "store",
            "vendor_symbol": "600519.SS",
            "security_id": "SEC:CN-XSHG-600519",
            "valid_from": None,
            "valid_to": None,
        },
    ]
    root = _write_identity_root(
        tmp_path,
        security_rows=security_rows,
        alias_rows=alias_rows,
    )

    class NeverAdapter:
        def __init__(self):
            self.calls = 0

        def resolve_many(self, *_args):
            self.calls += 1
            return {}

    quote = NeverAdapter()
    technicals = NeverAdapter()
    resolver = DatapointResolver(
        identity_normalizer=DataOSIdentityNormalizer(
            root, today=lambda: date(2026, 8, 23)
        ),
        adapters={"quote": quote, "technicals": technicals},
        clock=lambda: NOW,
    )
    with pytest.raises(RequestValidationError, match="outside frozen us_equity"):
        resolver.resolve(
            {
                "entities": [edge],
                "field_ids": ["market.price.last", "market.return.3m"],
                "audience": "internal",
                "consumer_use": "query",
            }
        )
    assert quote.calls == 0
    assert technicals.calls == 0


def test_ambiguous_alias_table_fails_closed(tmp_path):
    aliases = [
        {"vendor": "store", "vendor_symbol": "AAPL", "security_id": "SEC:US-XNAS-AAPL", "valid_from": None, "valid_to": None},
        {"vendor": "store", "vendor_symbol": "AAPL", "security_id": "SEC:US-XNYS-MMC", "valid_from": None, "valid_to": None},
    ]
    root = _write_identity_root(tmp_path, alias_rows=aliases)
    with pytest.raises(IdentityResolutionError, match="ambiguous alias table"):
        DataOSIdentityNormalizer(root).normalize_many([EntityRequest("security", symbol="AAPL")])


@pytest.mark.parametrize(
    "security_state,superseded_by,expected",
    [
        ("SUPERSEDED_DUPLICATE_MINT", "SEC:US-XNAS-AAPL", "superseded"),
        ("RETIRED", None, "retired"),
    ],
)
def test_terminal_security_state_is_preserved_without_redirect(tmp_path, security_state, superseded_by, expected):
    rows = [
        {
            "security_id": "SEC:US-XNAS-AAPL",
            "issuer_id": "ISS:US-XNAS-AAPL",
            "issuer_state": "RESOLVED",
            "listing_key": "US-XNAS-AAPL",
            "security_state": None,
            "superseded_by": None,
        },
        {
            "security_id": "SEC:US-XNYS-MMC",
            "issuer_id": "ISS:US-XNYS-MMC",
            "issuer_state": "RESOLVED",
            "listing_key": "US-XNYS-MMC",
            "security_state": security_state,
            "superseded_by": superseded_by,
        },
    ]
    root = _write_identity_root(tmp_path, security_rows=rows)
    entity = DataOSIdentityNormalizer(root).normalize_many(
        [EntityRequest("security", id="SEC:US-XNYS-MMC")]
    )[0]
    assert entity.id == "SEC:US-XNYS-MMC"
    assert entity.state == expected


def test_industry_identity_must_exist_in_current_stage_usa_view(tmp_path):
    root = _write_identity_root(tmp_path, industry_ids=("Software", "Banks"))
    normalizer = DataOSIdentityNormalizer(root)
    entity = normalizer.normalize_many([EntityRequest("industry", id="Software")])[0]
    assert entity == CanonicalEntity("industry", "Software", "us_industry")
    with pytest.raises(IdentityResolutionError, match="not present"):
        normalizer.normalize_many([EntityRequest("industry", id="Free form guess")])


def test_reverse_current_symbol_uses_exact_vendor_space_and_no_sec_parse(tmp_path):
    root = _write_identity_root(tmp_path)
    store = load_current_symbol_map(root, "store", on=date(2026, 8, 23))
    assert store["SEC:US-XNYS-MMC"] == "MRSH"
    resolver = current_symbol_resolver(root, "yahoo_fetch", on=date(2026, 8, 23))
    assert resolver(CanonicalEntity("security", "SEC:US-XNYS-MMC", "us_equity")) == "MRSH"
    assert resolver(CanonicalEntity("security", "SEC:US-XNAS-MSFT", "us_equity")) is None


def test_quote_adapter_batches_symbols_once_and_preserves_owner_clocks():
    registry = load_registry()
    spec = registry.field("market.price.last")
    entities = (
        CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity"),
        CanonicalEntity("security", "SEC:US-XNAS-MSFT", "us_equity"),
    )
    symbols = {entities[0].id: "AAPL", entities[1].id: "MSFT"}
    calls = []

    def quote_owner(requested, terminal_data_dir, terminal_hub_url, root):
        calls.append(tuple(requested))
        return {
            "AAPL": {"price": 227.5, "as_of": "2026-08-23T15:00:00Z", "source": "terminal_hub", "delayed_min": 15},
            "MSFT": {"price": 515.0, "as_of": "2026-08-23T15:00:01Z", "source": "terminal_hub"},
        }

    adapter = QuoteAdapter(
        symbol_resolver=lambda entity: symbols.get(entity.id),
        quote_resolver=quote_owner,
    )
    result = adapter.resolve_many(entities, (spec,), _request((spec.field_id,)), _context())
    assert calls == [("AAPL", "MSFT")]
    aapl = result[("security", entities[0].id, spec.field_id)]
    assert aapl.value == 227.5 and aapl.unit == "USD"
    assert aapl.as_of == "2026-08-23T15:00:00Z"
    assert aapl.source["source_id"] == "terminal_hub"
    assert aapl.quality == {"state": "degraded", "issues": ("quote_delayed_15m",)}


def test_quote_adapter_unknown_reverse_symbol_is_typed_owner_missing():
    spec = load_registry().field("market.price.last")
    entity = CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity")
    called = False

    def should_not_call(*_args):
        nonlocal called
        called = True
        return {}

    adapter = QuoteAdapter(symbol_resolver=lambda _entity: None, quote_resolver=should_not_call)
    result = adapter.resolve_many((entity,), (spec,), _request((spec.field_id,)), _context())
    assert result[("security", entity.id, spec.field_id)].reason_code == "owner_missing"
    assert not called


def test_old_manifest_quote_clock_does_not_synthesize_freshness(tmp_path):
    root = _write_identity_root(tmp_path)

    def old_manifest_quote(symbols, *_args):
        return {
            "AAPL": {
                "price": 100.0,
                "as_of": "2020-01-01",
                "source": "manifest",
                "delayed_min": 15,
            }
        }

    resolver = DatapointResolver(
        identity_normalizer=DataOSIdentityNormalizer(
            root, today=lambda: date(2026, 8, 23)
        ),
        adapters={
            "quote": QuoteAdapter(root=root, quote_resolver=old_manifest_quote),
        },
        clock=lambda: NOW,
    )
    envelope = resolver.resolve(
        {
            "entities": [{"type": "security", "symbol": "AAPL"}],
            "field_ids": ["market.price.last"],
            "audience": "internal",
            "consumer_use": "query",
        }
    )[0]
    assert envelope["status"] == "available"
    assert envelope["value"] == 100.0
    assert envelope["as_of"] == "2020-01-01"
    assert envelope["freshness"] == {"state": "unknown", "policy": "owner_native"}
    assert envelope["quality"] == {
        "state": "degraded",
        "issues": ["quote_delayed_15m"],
    }
    assert envelope["source"]["delay"] == "delayed_15m"


def test_technicals_reads_owner_values_once_for_three_fields_and_never_recomputes(tmp_path):
    stockdata = tmp_path / "site/stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(
        json.dumps(
            {
                "asof": "2026-08-22",
                "tech": {"ret_1m": 0.0, "ret_3m": 15.0, "ret_12m": -7.5},
            }
        ),
        encoding="utf-8",
    )
    registry = load_registry()
    entity = CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity")
    context = _context()
    adapter = TechnicalsAdapter(root=tmp_path, symbol_resolver=lambda _entity: "AAPL")
    field_ids = ("market.return.1m", "market.return.3m", "market.return.12m")
    specs = tuple(registry.field(field_id) for field_id in field_ids)
    rows = adapter.resolve_many((entity,), specs, _request(field_ids), context)
    values = {}
    for field_id in field_ids:
        row = rows[("security", entity.id, field_id)]
        values[field_id] = row.value
        assert row.as_of == "2026-08-22"
        assert row.source["dataset_id"] is None
        assert "adjustment vintage not asserted" in row.provenance["basis"]
    assert values == {
        "market.return.1m": 0.0,
        "market.return.3m": 15.0,
        "market.return.12m": -7.5,
    }
    assert context.source_loads == {"technicals:owner_record:SEC:US-XNAS-AAPL": 1}


def test_technicals_stale_and_missing_owner_states_are_typed(tmp_path):
    stockdata = tmp_path / "site/stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(
        json.dumps(
            {
                "asof": "2026-08-01",
                "feed_stale": {"behind_days": 22, "lib_asof": "2026-08-01"},
                "tech": {"ret_3m": 99.0},
            }
        ),
        encoding="utf-8",
    )
    spec = load_registry().field("market.return.3m")
    aapl = CanonicalEntity("security", "SEC:US-XNAS-AAPL", "us_equity")
    msft = CanonicalEntity("security", "SEC:US-XNAS-MSFT", "us_equity")
    symbols = {aapl.id: "AAPL", msft.id: "MSFT"}
    rows = TechnicalsAdapter(root=tmp_path, symbol_resolver=lambda e: symbols[e.id]).resolve_many(
        (aapl, msft), (spec,), _request((spec.field_id,)), _context()
    )
    stale = rows[("security", aapl.id, spec.field_id)]
    missing = rows[("security", msft.id, spec.field_id)]
    assert stale.status == "stale" and stale.reason_code == "owner_stale" and stale.value is None
    assert stale.as_of == "2026-08-01"
    assert missing.status == "unavailable" and missing.reason_code == "owner_missing"


def test_market_adapters_refuse_wrong_entity_type():
    industry = CanonicalEntity("industry", "Software", "us_industry")
    registry = load_registry()
    with pytest.raises(ValueError, match="security"):
        QuoteAdapter(symbol_resolver=lambda _entity: "SOFTWARE").resolve_many(
            (industry,), (registry.field("market.price.last"),), _request(("market.price.last",)), _context()
        )
    with pytest.raises(ValueError, match="security"):
        TechnicalsAdapter(symbol_resolver=lambda _entity: "SOFTWARE").resolve_many(
            (industry,), (registry.field("market.return.3m"),), _request(("market.return.3m",)), _context()
        )


def test_real_resolver_dispatches_quote_and_three_technical_fields_as_owner_batches(tmp_path):
    root = _write_identity_root(tmp_path)
    stockdata = root / "site/stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(
        json.dumps(
            {
                "asof": "2026-08-22",
                "tech": {"ret_1m": 1.25, "ret_3m": 15.0, "ret_12m": 27.5},
            }
        ),
        encoding="utf-8",
    )
    quote_calls = []

    def quote_owner(symbols, terminal_data_dir, terminal_hub_url, owner_root):
        quote_calls.append(tuple(symbols))
        assert owner_root == root
        return {
            "AAPL": {
                "price": 227.5,
                "as_of": "2026-08-23T15:00:00Z",
                "source": "terminal_hub",
            }
        }

    resolver = DatapointResolver(
        identity_normalizer=DataOSIdentityNormalizer(root, today=lambda: date(2026, 8, 23)),
        adapters={
            "quote": QuoteAdapter(root=root, quote_resolver=quote_owner),
            "technicals": TechnicalsAdapter(root=root),
        },
        clock=lambda: NOW,
    )
    field_ids = (
        "market.price.last",
        "market.return.1m",
        "market.return.3m",
        "market.return.12m",
    )
    envelopes = resolver.resolve(
        {
            "entities": [{"type": "security", "symbol": "AAPL"}],
            "field_ids": field_ids,
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    assert quote_calls == [("AAPL",)]
    assert [envelope["field_id"] for envelope in envelopes] == list(field_ids)
    assert [envelope["value"] for envelope in envelopes] == [227.5, 1.25, 15.0, 27.5]
    assert all(envelope["entity"]["id"] == "SEC:US-XNAS-AAPL" for envelope in envelopes)
    assert all(envelope["status"] == "available" for envelope in envelopes)
    assert all(len(envelope["registry_digest"]) == 64 for envelope in envelopes)
    assert all(len(envelope["fact_fingerprint"]) == 64 for envelope in envelopes)
    assert envelopes[0]["source"]["owner"] == "neuralweb_quote_owner"
    assert all(
        envelope["source"]["owner"] == "stock_technicals"
        for envelope in envelopes[1:]
    )
    assert [envelope["provenance"]["owner_field_key"] for envelope in envelopes] == [
        "last", "ret_1m", "ret_3m", "ret_12m"
    ]
