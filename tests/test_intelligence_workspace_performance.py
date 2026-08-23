from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import pandas as pd

from engine.intelligence_workspace.adapters.company_intelligence import CompanyIntelligenceAdapter
from engine.intelligence_workspace.adapters.earnings import EarningsCalendarAdapter
from engine.intelligence_workspace.adapters.industry import IndustryAdapter
from engine.intelligence_workspace.adapters.quote import QuoteAdapter
from engine.intelligence_workspace.adapters.stage import StageAdapter
from engine.intelligence_workspace.adapters.technicals import TechnicalsAdapter
from engine.intelligence_workspace.adapters.theme import ThemeAdapter
from engine.intelligence_workspace.contracts import canonical_json_bytes
from engine.intelligence_workspace.entity import DataOSIdentityNormalizer
from engine.intelligence_workspace.projection import ThemeRightsProjector
from engine.intelligence_workspace.registry import (
    DEFAULT_REGISTRY_PATH,
    REGISTRY_SCHEMA_PATH,
    clear_registry_cache,
    load_registry,
)
from engine.intelligence_workspace.resolver import (
    DatapointResolver,
    VALUE_SCHEMA_PATH,
    _value_validator,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
SECURITY_FIELDS = (
    "market.price.last",
    "market.return.1m",
    "market.return.3m",
    "market.return.12m",
    "stage.current",
    "stage.weeks_in_stage",
    "security.industry_member.rs_percentile",
    "earnings.next_date",
    "earnings.latest.eps_growth_pct",
    "earnings.latest.revenue_growth_pct",
    "theme.local.memberships",
)
INDUSTRY_FIELDS = ("industry.rank.percentile",)
REPRESENTATIVE_FIELDS = (
    "market.price.last",
    "market.return.1m",
    "market.return.3m",
    "market.return.12m",
)


@dataclass
class Counters:
    quote_batches: int = 0
    quote_symbols: int = 0
    shared_store_symbol_maps: int = 0
    stage_documents: int = 0
    industry_rank_documents: int = 0
    industry_member_documents: int = 0
    earnings_frames: int = 0
    company_reads: Counter = field(default_factory=Counter)
    theme_identity_views: int = 0
    theme_edge_views: int = 0
    theme_meta_views: int = 0
    path_reads: Counter = field(default_factory=Counter)
    parquet_reads: Counter = field(default_factory=Counter)

    def snapshot(self) -> dict:
        return {
            "quote_batches": self.quote_batches,
            "quote_symbols": self.quote_symbols,
            "shared_store_symbol_maps": self.shared_store_symbol_maps,
            "stage_documents": self.stage_documents,
            "industry_rank_documents": self.industry_rank_documents,
            "industry_member_documents": self.industry_member_documents,
            "earnings_frames": self.earnings_frames,
            "company_reads": dict(self.company_reads),
            "theme_identity_views": self.theme_identity_views,
            "theme_edge_views": self.theme_edge_views,
            "theme_meta_views": self.theme_meta_views,
            "path_reads": dict(self.path_reads),
            "parquet_reads": dict(self.parquet_reads),
        }


def _delta(before: dict, after: dict) -> dict:
    out = {}
    for key, value in after.items():
        prior = before[key]
        if isinstance(value, dict):
            keys = set(value) | set(prior)
            out[key] = {name: value.get(name, 0) - prior.get(name, 0) for name in sorted(keys)}
        else:
            out[key] = value - prior
    return out


def _measure(call):
    wall_start = perf_counter_ns()
    cpu_start = process_time_ns()
    value = call()
    return value, {
        "wall_ms": round((perf_counter_ns() - wall_start) / 1_000_000, 6),
        "cpu_ms": round((process_time_ns() - cpu_start) / 1_000_000, 6),
    }


def _fixture_world(root: Path, n_securities: int = 20):
    symbols = ["AAPL"] + [f"T{i:03d}" for i in range(1, n_securities)]
    ids = [f"SEC:US-XNAS-{symbol}" for symbol in symbols]
    symbol_by_id = dict(zip(ids, symbols, strict=True))

    reference = root / "data/reference"
    reference.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "security_id": security_id,
                "issuer_id": f"ISS:{security_id.removeprefix('SEC:')}",
                "issuer_state": "RESOLVED",
                "listing_key": security_id.removeprefix("SEC:"),
                "country": "US",
                "mic": "XNAS",
                "security_state": None,
                "superseded_by": None,
            }
            for security_id in ids
        ]
    ).to_parquet(reference / "security_master.parquet", index=False)
    pd.DataFrame(
        [
            {
                "vendor": vendor,
                "vendor_symbol": symbol,
                "security_id": security_id,
                "valid_from": None,
                "valid_to": None,
            }
            for vendor in ("store", "yahoo_fetch")
            for security_id, symbol in symbol_by_id.items()
        ]
    ).to_parquet(reference / "vendor_aliases.parquet", index=False)

    stockdata = root / "site/stockdata"
    stockdata.mkdir(parents=True)
    for index, symbol in enumerate(symbols):
        (stockdata / f"{symbol}.json").write_text(
            json.dumps(
                {
                    "asof": "2026-08-22",
                    "tech": {
                        "ret_1m": float(index),
                        "ret_3m": float(index + 15),
                        "ret_12m": float(index + 30),
                    },
                }
            ),
            encoding="utf-8",
        )

    stage_dir = root / "data/stage_analysis"
    stage_dir.mkdir(parents=True)
    (stage_dir / "screener.json").write_text(
        json.dumps(
            {
                "schema": "stage_screener.v1",
                "asof": "2026-08-22",
                "built": "2026-08-23T01:00:00Z",
                "stage_week_end": "2026-08-21",
                "rows": [
                    {
                        "source": "live",
                        "ticker": symbol,
                        "stage": 2,
                        "weeks_in_stage": index + 1,
                        "stage_current": True,
                        "stage_source_asof": "2026-08-21",
                        "stage_week_end": "2026-08-21",
                    }
                    for index, symbol in enumerate(symbols)
                ],
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "industry_ranks.json").write_text(
        json.dumps(
            {
                "schema": "stage_industry_ranks.v1",
                "status": "ready",
                "asof": "2026-08-22",
                "built": "2026-08-23T01:00:00Z",
                "coverage": {
                    "status": "ready",
                    "freshness": {"status": "current"},
                },
                "regions": {
                    "USA": [
                        {
                            "industry_id": "Software",
                            "industry_name": "Software",
                            "industry_percentile": 87.5,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "industry_name_pctile.json").write_text(
        json.dumps(
            {
                "schema": "stage_industry_name_pctile.v1",
                "status": "ready",
                "asof": "2026-08-22",
                "built": "2026-08-23T01:00:00Z",
                "percentiles": {symbol: float(50 + index) for index, symbol in enumerate(symbols)},
            }
        ),
        encoding="utf-8",
    )
    return symbols, ids, symbol_by_id


def _semantic(envelopes):
    return {
        (envelope["entity"]["id"], envelope["field_id"]): {
            key: value
            for key, value in envelope.items()
            if key not in {"generated_at"}
        }
        for envelope in envelopes
    }


def test_w1a_batch_and_performance_receipt(tmp_path, monkeypatch):
    symbols, ids, symbol_by_id = _fixture_world(tmp_path)
    counters = Counters()

    original_read_text = Path.read_text

    def counted_read_text(path, *args, **kwargs):
        counters.path_reads[str(path)] += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)
    original_read_parquet = pd.read_parquet

    def counted_read_parquet(path, *args, **kwargs):
        counters.parquet_reads[str(path)] += 1
        return original_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", counted_read_parquet)

    original_stage_load = StageAdapter._load_document

    def counted_stage_load(adapter):
        counters.stage_documents += 1
        return original_stage_load(adapter)

    monkeypatch.setattr(StageAdapter, "_load_document", counted_stage_load)
    original_industry_load = IndustryAdapter._load_json

    def counted_industry_load(path, required_key):
        if required_key == "regions":
            counters.industry_rank_documents += 1
        elif required_key == "percentiles":
            counters.industry_member_documents += 1
        return original_industry_load(path, required_key)

    monkeypatch.setattr(IndustryAdapter, "_load_json", staticmethod(counted_industry_load))

    store_map = dict(symbol_by_id)

    def shared_store_map():
        counters.shared_store_symbol_maps += 1
        return store_map

    earnings_frame = pd.DataFrame(
        [
            {"ticker": symbol, "next_date": "2026-10-29", "as_of": "2026-08-22"}
            for symbol in symbols
        ]
    )

    def load_earnings():
        counters.earnings_frames += 1
        return earnings_frame

    def read_company(params):
        ticker = params["ticker"]
        counters.company_reads[ticker] += 1
        return {
            "available": True,
            "status": "ready",
            "latest_event": {
                "call_date": "2026-07-31",
                "metrics": {"eps_growth_pct": 12.5, "revenue_growth_pct": 7.25},
                "field_lineage": {
                    "metrics": {
                        "eps_growth_pct": "earnings_history",
                        "revenue_growth_pct": "score_overlay",
                    }
                },
            },
        }

    identities = [
        {
            "graph_kind": "company",
            "resolution_state": "RESOLVED",
            "security_id": security_id,
            "node_id": f"company:{symbol.lower()}",
        }
        for security_id, symbol in symbol_by_id.items()
    ]
    edges = [
        {
            "type": "MEMBER_OF",
            "src": f"company:{symbol.lower()}",
            "dst": "ltheme:finviz:ai",
            "valid_from": "2026-01-01",
            "valid_to": None,
        }
        for symbol in symbols
    ]

    def load_theme_identity():
        counters.theme_identity_views += 1
        return identities

    def load_theme_edges():
        counters.theme_edge_views += 1
        return edges

    def load_theme_meta():
        counters.theme_meta_views += 1
        return {"computed_at": "2026-08-23T01:00:00Z", "belief_time": "2026-08-22"}

    def quote_owner(requested, terminal_data_dir, terminal_hub_url, root):
        del terminal_data_dir, terminal_hub_url, root
        counters.quote_batches += 1
        counters.quote_symbols += len(requested)
        return {
            symbol: {
                "price": float(100 + symbols.index(symbol)),
                "as_of": "2026-08-23T11:59:00Z",
                "source": "terminal_hub",
            }
            for symbol in requested
        }

    adapters = {
        "quote": QuoteAdapter(
            root=tmp_path,
            symbol_resolver=lambda entity: symbol_by_id.get(entity.id),
            quote_resolver=quote_owner,
        ),
        "technicals": TechnicalsAdapter(
            root=tmp_path,
            symbol_resolver=lambda entity: symbol_by_id.get(entity.id),
        ),
        "stage": StageAdapter(
            repo_root=tmp_path,
            vendor="store",
            symbol_map_loader=shared_store_map,
        ),
        "industry": IndustryAdapter(
            repo_root=tmp_path,
            vendor="store",
            symbol_map_loader=shared_store_map,
        ),
        "earnings_calendar": EarningsCalendarAdapter(
            repo_root=tmp_path,
            vendor="store",
            symbol_map_loader=shared_store_map,
            dataframe_loader=load_earnings,
            staleness_assessor=lambda frame, today: {"stale": 0, "should_warn": False},
        ),
        "company_intelligence": CompanyIntelligenceAdapter(
            repo_root=tmp_path,
            vendor="store",
            symbol_map_loader=shared_store_map,
            reader=read_company,
        ),
        "theme": ThemeAdapter(
            identity_loader=load_theme_identity,
            edge_loader=load_theme_edges,
            meta_loader=load_theme_meta,
        ),
    }

    clear_registry_cache()
    registry_before = counters.snapshot()
    registry, cold_registry = _measure(load_registry)
    registry_after_cold = counters.snapshot()
    cached_registry, warm_registry = _measure(load_registry)
    registry_after_warm = counters.snapshot()
    cold_registry["source_loads"] = _delta(registry_before, registry_after_cold)
    warm_registry["source_loads"] = _delta(registry_after_cold, registry_after_warm)
    assert cached_registry is registry
    assert cold_registry["source_loads"]["path_reads"][
        str(DEFAULT_REGISTRY_PATH)
    ] == 1
    assert cold_registry["source_loads"]["path_reads"][
        str(REGISTRY_SCHEMA_PATH)
    ] == 1
    assert not any(warm_registry["source_loads"]["path_reads"].values())
    assert registry.limits == {
        "max_fields": 12,
        "max_entities": 250,
        "max_cells": 2000,
        "max_request_cost": 8000,
    }
    resolver = DatapointResolver(
        registry=registry,
        identity_normalizer=DataOSIdentityNormalizer(tmp_path, today=lambda: date(2026, 8, 23)),
        adapters=adapters,
        rights_projector=ThemeRightsProjector(
            family_resolver=lambda node_id: "finviz_themes",
            assert_allowed=lambda family: None,
        ),
        clock=lambda: NOW,
    )

    def resolve(request):
        before = counters.snapshot()
        envelopes, timing = _measure(lambda: resolver.resolve(request))
        timing.update(
            {
                "cells": len(envelopes),
                "output_bytes": len(canonical_json_bytes(list(envelopes))),
                "source_loads": _delta(before, counters.snapshot()),
            }
        )
        return envelopes, timing

    _value_validator.cache_clear()
    schema_reads_before = counters.path_reads[str(VALUE_SCHEMA_PATH)]
    one, one_metric = resolve(
        {
            "entities": [{"type": "security", "symbol": "AAPL"}],
            "field_ids": ["market.price.last"],
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    assert len(one) == 1 and one[0]["value"] == 100.0
    assert counters.path_reads[str(VALUE_SCHEMA_PATH)] - schema_reads_before == 1

    all_security, all_security_metric = resolve(
        {
            "entities": [{"type": "security", "symbol": "AAPL"}],
            "field_ids": list(SECURITY_FIELDS),
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    assert len(all_security) == 11
    assert counters.path_reads[str(VALUE_SCHEMA_PATH)] - schema_reads_before == 1
    all_loads = all_security_metric["source_loads"]
    assert all_loads["quote_batches"] == 1
    assert all_loads["quote_symbols"] == 1
    assert all_loads["shared_store_symbol_maps"] == 1
    assert all_loads["stage_documents"] == 1
    assert all_loads["industry_rank_documents"] == 0
    assert all_loads["industry_member_documents"] == 1
    assert all_loads["earnings_frames"] == 1
    assert all_loads["company_reads"] == {"AAPL": 1}
    assert all_loads["theme_identity_views"] == 1
    assert all_loads["theme_edge_views"] == 1
    assert all_loads["theme_meta_views"] == 1
    assert all_loads["path_reads"][str(tmp_path / "site/stockdata/AAPL.json")] == 1
    assert all_loads["path_reads"][str(tmp_path / "data/stage_analysis/screener.json")] == 1
    assert all_loads["path_reads"][str(tmp_path / "data/stage_analysis/industry_name_pctile.json")] == 1
    assert all_loads["parquet_reads"] == {
        str(tmp_path / "data/reference/security_master.parquet"): 1,
        str(tmp_path / "data/reference/vendor_aliases.parquet"): 1,
    }

    industry, industry_metric = resolve(
        {
            "entities": [{"type": "industry", "id": "Software"}],
            "field_ids": list(INDUSTRY_FIELDS),
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    assert len(industry) == 1 and industry[0]["value"] == 87.5
    assert industry_metric["source_loads"]["industry_rank_documents"] == 1
    assert industry_metric["source_loads"]["industry_member_documents"] == 0
    assert industry_metric["source_loads"]["path_reads"][
        str(tmp_path / "data/stage_analysis/industry_ranks.json")
    ] == 2  # identity admission + industry owner fact, each once

    representative_entities = [
        {"type": "security", "id": security_id} for security_id in ids
    ]
    representative, representative_metric = resolve(
        {
            "entities": representative_entities,
            "field_ids": list(REPRESENTATIVE_FIELDS),
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    assert len(representative) == len(ids) * len(REPRESENTATIVE_FIELDS) == 80
    representative_loads = representative_metric["source_loads"]
    assert representative_loads["quote_batches"] == 1
    assert representative_loads["quote_symbols"] == len(ids)
    assert representative_loads["parquet_reads"] == {
        str(tmp_path / "data/reference/security_master.parquet"): 1,
        str(tmp_path / "data/reference/vendor_aliases.parquet"): 1,
    }
    technical_reads = {
        path: count
        for path, count in representative_loads["path_reads"].items()
        if "/site/stockdata/" in path
    }
    assert len(technical_reads) == len(ids)
    assert set(technical_reads.values()) == {1}
    assert counters.path_reads[str(VALUE_SCHEMA_PATH)] - schema_reads_before == 1

    combined, _combined_metric = resolve(
        {
            "entities": [
                {"type": "security", "id": ids[0]},
                {"type": "security", "id": ids[1]},
            ],
            "field_ids": list(REPRESENTATIVE_FIELDS),
            "audience": "internal",
            "consumer_use": "query",
        }
    )
    partitioned = []
    for security_id in ids[:2]:
        part, _part_metric = resolve(
            {
                "entities": [{"type": "security", "id": security_id}],
                "field_ids": list(REPRESENTATIVE_FIELDS),
                "audience": "internal",
                "consumer_use": "query",
            }
        )
        partitioned.extend(part)
    assert _semantic(combined) == _semantic(partitioned)

    receipt = {
        "registry": {"cold": cold_registry, "cached": warm_registry},
        "one_field_one_security": one_metric,
        "eleven_security_fields_one_security": all_security_metric,
        "one_industry_field_one_industry": industry_metric,
        "twelve_field_manifest_as_applicable": {
            "cells": all_security_metric["cells"] + industry_metric["cells"],
            "output_bytes": all_security_metric["output_bytes"] + industry_metric["output_bytes"],
            "wall_ms": round(all_security_metric["wall_ms"] + industry_metric["wall_ms"], 6),
            "cpu_ms": round(all_security_metric["cpu_ms"] + industry_metric["cpu_ms"], 6),
        },
        "representative_20_security_4_field_batch": representative_metric,
        "limits": dict(registry.limits),
        "schema_reads_cold_then_warm": {"cold": 1, "warm_additional": 0},
        "partition_semantic_equivalence": True,
    }
    print("W1A_PERFORMANCE_RECEIPT=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
