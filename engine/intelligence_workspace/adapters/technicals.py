"""Read owner-published technical returns; never recompute return formulas."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..contracts import AdapterResult, CanonicalEntity
from ..entity import REPO_ROOT, load_current_symbol_map
from .base import read_json_once, safe_artifact_symbol, unavailable


_OWNER_KEYS = frozenset({"ret_1m", "ret_3m", "ret_12m"})


class TechnicalsAdapter:
    def __init__(
        self,
        *,
        root: str | Path = REPO_ROOT,
        symbol_resolver: Callable[[CanonicalEntity], str | None] | None = None,
    ) -> None:
        self.root = Path(root)
        self.symbol_resolver = symbol_resolver

    def _symbols(self, entities: Sequence[CanonicalEntity], context: Any) -> dict[str, str | None]:
        if self.symbol_resolver is not None:
            return {entity.id: self.symbol_resolver(entity) for entity in entities}
        aliases = context.memoize(
            "dataos:current_symbols:store",
            lambda: load_current_symbol_map(self.root, "store"),
        )
        return {entity.id: aliases.get(entity.id) for entity in entities}

    def resolve_many(self, canonical_entities, field_specs, request, context):
        if not field_specs or any(spec.owner_field_key not in _OWNER_KEYS for spec in field_specs) or any(
            entity.type != "security" for entity in canonical_entities
        ):
            raise ValueError("TechnicalsAdapter accepts only security return owner fields")
        if len({spec.field_id for spec in field_specs}) != len(field_specs):
            raise ValueError("TechnicalsAdapter refuses duplicate field specs")
        by_entity = self._symbols(canonical_entities, context)
        out = {}
        for entity in canonical_entities:
            raw_symbol = by_entity[entity.id]
            if raw_symbol is None:
                for field_spec in field_specs:
                    out[(entity.type, entity.id, field_spec.field_id)] = unavailable(
                        field_spec,
                        reason_code="owner_missing",
                        source_id="stock_technicals.owner_snapshot",
                        owner="stock_technicals",
                    )
                continue
            symbol = safe_artifact_symbol(raw_symbol)
            relative = f"site/stockdata/{symbol}.json"
            row = read_json_once(
                context,
                f"technicals:owner_record:{entity.id}",
                self.root / relative,
            )
            if row is None:
                for field_spec in field_specs:
                    out[(entity.type, entity.id, field_spec.field_id)] = unavailable(
                        field_spec,
                        reason_code="owner_missing",
                        source_id="stock_technicals.owner_snapshot",
                        owner="stock_technicals",
                        artifact_id=relative,
                    )
                continue
            as_of = row.get("asof")
            stale = bool(row.get("feed_stale"))
            if stale:
                for field_spec in field_specs:
                    out[(entity.type, entity.id, field_spec.field_id)] = unavailable(
                        field_spec,
                        reason_code="owner_stale",
                        source_id="stock_technicals.owner_snapshot",
                        owner="stock_technicals",
                        as_of=as_of,
                        freshness_state="stale",
                        quality_state="degraded",
                        issues=["technical_feed_stale"],
                        artifact_id=relative,
                    )
                continue
            tech = row.get("tech") if isinstance(row.get("tech"), dict) else {}
            for field_spec in field_specs:
                key = (entity.type, entity.id, field_spec.field_id)
                value = tech.get(field_spec.owner_field_key)
                if value is None:
                    out[key] = unavailable(
                        field_spec,
                        reason_code="value_missing",
                        source_id="stock_technicals.owner_snapshot",
                        owner="stock_technicals",
                        as_of=as_of,
                        artifact_id=relative,
                    )
                    continue
                out[key] = AdapterResult(
                    value=value,
                    status="available",
                    reason_code=None,
                    unit="percent",
                    observed_at=as_of,
                    effective_at=as_of,
                    as_of=as_of,
                    freshness={"state": "fresh" if as_of else "unknown", "policy": "owner_native"},
                    quality={"state": "ok", "issues": []},
                    source={
                        "source_id": "stock_technicals.owner_snapshot",
                        "owner": "stock_technicals",
                        "license_class": "internal_derived",
                        "dataset_id": None,
                        "artifact_id": relative,
                    },
                    provenance={
                        "kind": "owner_derived",
                        "owner_field_key": field_spec.owner_field_key,
                        "basis": "owner-published current technical value; adjustment vintage not asserted",
                        "owner_artifact": relative,
                    },
                )
        return out
