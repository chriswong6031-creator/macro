"""Read the frozen quote owner waterfall once for a security batch."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from engine.quote_resolution import resolve_quotes

from ..contracts import AdapterResult, CanonicalEntity
from ..entity import REPO_ROOT, load_current_symbol_map
from .base import unavailable


class QuoteAdapter:
    def __init__(
        self,
        *,
        root: str | Path = REPO_ROOT,
        terminal_data_dir: str | Path = "/opt/terminal/terminal/public/data",
        terminal_hub_url: str = "http://127.0.0.1:3100",
        symbol_resolver: Callable[[CanonicalEntity], str | None] | None = None,
        quote_resolver: Callable[..., Mapping[str, Mapping[str, Any]]] = resolve_quotes,
    ) -> None:
        self.root = Path(root)
        self.terminal_data_dir = Path(terminal_data_dir)
        self.terminal_hub_url = terminal_hub_url
        self.symbol_resolver = symbol_resolver
        self.quote_resolver = quote_resolver

    def _symbols(self, entities: Sequence[CanonicalEntity], context: Any) -> dict[str, str | None]:
        if self.symbol_resolver is not None:
            return {entity.id: self.symbol_resolver(entity) for entity in entities}
        aliases = context.memoize(
            "dataos:current_symbols:yahoo_fetch",
            lambda: load_current_symbol_map(self.root, "yahoo_fetch"),
        )
        return {entity.id: aliases.get(entity.id) for entity in entities}

    def resolve_many(self, canonical_entities, field_specs, request, context):
        if len(field_specs) != 1 or field_specs[0].owner_field_key != "last" or any(
            entity.type != "security" for entity in canonical_entities
        ):
            raise ValueError("QuoteAdapter accepts only security/last")
        field_spec = field_specs[0]
        by_entity = self._symbols(canonical_entities, context)
        requested = tuple(symbol for symbol in by_entity.values() if symbol)
        rows = (
            context.memoize(
                "quote:owner_batch:" + ",".join(requested),
                lambda: self.quote_resolver(
                    requested,
                    self.terminal_data_dir,
                    self.terminal_hub_url,
                    self.root,
                ),
            )
            if requested
            else {}
        )
        out = {}
        for entity in canonical_entities:
            key = (entity.type, entity.id, field_spec.field_id)
            symbol = by_entity[entity.id]
            if symbol is None:
                out[key] = unavailable(
                    field_spec,
                    reason_code="owner_missing",
                    source_id="quote_resolution",
                    owner="neuralweb_quote_owner",
                )
                continue
            row = rows.get(symbol) if isinstance(rows, Mapping) else None
            if not isinstance(row, Mapping) or row.get("available") is False or row.get("price") is None:
                out[key] = unavailable(
                    field_spec,
                    reason_code="owner_unavailable",
                    source_id="quote_resolution",
                    owner="neuralweb_quote_owner",
                )
                continue
            delay = row.get("delayed_min")
            source = str(row.get("source") or "quote_resolution")
            as_of = row.get("as_of")
            issues = [f"quote_delayed_{int(delay)}m"] if isinstance(delay, (int, float)) and delay > 0 else []
            source_payload = {
                "source_id": source,
                "owner": "neuralweb_quote_owner",
                "license_class": "market_data_internal",
                "dataset_id": None,
                "delay": f"delayed_{int(delay)}m" if issues else None,
            }
            out[key] = AdapterResult(
                value=row["price"],
                status="available",
                reason_code=None,
                unit="USD",
                observed_at=as_of,
                effective_at=as_of,
                as_of=as_of,
                # A source clock is evidence of observation time, not an owner
                # freshness verdict.  The frozen quote waterfall exposes no
                # explicit health assertion, so W1-A must remain unknown here.
                freshness={"state": "unknown", "policy": "owner_native"},
                quality={"state": "degraded" if issues else "ok", "issues": issues},
                source=source_payload,
                provenance={
                    "kind": "owner_direct",
                    "owner_field_key": field_spec.owner_field_key,
                    "basis": "canonical quote owner live-to-snapshot waterfall",
                },
            )
        return out
