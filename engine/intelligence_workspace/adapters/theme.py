"""Read-only projection of direct current Theme Graph local memberships."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from engine.intelligence_workspace.contracts import AdapterResult, CanonicalEntity
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import OwnerResolutionRequest, RequestContext


_IDENTITY_READER = "engine.theme_graph.store.read_identity_resolution(latest=True)"
_EDGE_READER = "engine.theme_graph.store.read_edges(latest_belief=True)"
_META_READER = "engine.theme_graph.store.read_meta()"


def _records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        raise TypeError("owner view is absent")
    if hasattr(value, "to_dict"):
        rows = value.to_dict("records")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = list(value)
    else:
        raise TypeError("owner view is not tabular")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("owner view contains a non-record row")
    return rows


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        null = pd.isna(value)
        return bool(null)
    except (ImportError, TypeError, ValueError):
        return False


def _date(value: Any) -> date | None:
    if _is_null(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


class ThemeAdapter:
    """Map canonical SEC ids through the current identity sidecar to direct edges."""

    def __init__(
        self,
        *,
        identity_loader: Callable[[], Any] | None = None,
        edge_loader: Callable[[], Any] | None = None,
        meta_loader: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        self._injected_identity_loader = identity_loader
        self._injected_edge_loader = edge_loader
        self._injected_meta_loader = meta_loader

    def _load_identity(self) -> Any:
        if self._injected_identity_loader is not None:
            return self._injected_identity_loader()
        from engine.theme_graph.store import read_identity_resolution

        return read_identity_resolution(latest=True)

    def _load_edges(self) -> Any:
        if self._injected_edge_loader is not None:
            return self._injected_edge_loader()
        from engine.theme_graph.store import read_edges

        return read_edges(latest_belief=True)

    def _load_meta(self) -> Mapping[str, Any]:
        if self._injected_meta_loader is not None:
            return self._injected_meta_loader()
        from engine.theme_graph.store import read_meta

        return read_meta()

    @staticmethod
    def _result(
        spec: FieldSpec,
        *,
        value: Any,
        status: str,
        reason: str | None,
        freshness: str,
        quality: str,
        issues: list[str],
        computed_at: Any,
        belief_time: Any,
    ) -> AdapterResult:
        return AdapterResult(
            value=value,
            status=status,
            reason_code=reason,
            unit=spec.unit,
            observed_at=computed_at,
            effective_at=belief_time,
            as_of=belief_time,
            freshness={"state": freshness, "policy": "owner_native"},
            quality={"state": quality, "issues": issues},
            source={
                "source_id": "theme_graph.local_memberships",
                "owner": "theme_graph",
                "license_class": "owner_dynamic",
                "dataset_id": None,
                "artifact_id": "data/theme_graph current view",
            },
            provenance={
                "kind": "owner_relation",
                "owner_field_key": spec.owner_field_key,
                "basis": "direct_source_relation",
                "relationship": "MEMBER_OF",
                "owner_artifact": f"{_IDENTITY_READER}; {_EDGE_READER}; {_META_READER}",
            },
        )

    def resolve_many(
        self,
        canonical_entities: Sequence[CanonicalEntity],
        field_specs: Sequence[FieldSpec],
        request: OwnerResolutionRequest,
        context: RequestContext,
    ) -> Mapping[tuple[str, str], AdapterResult]:
        del request
        issue: str | None = None
        identities: list[Mapping[str, Any]] = []
        edges: list[Mapping[str, Any]] = []
        meta: Mapping[str, Any] = {}
        try:
            identities = _records(
                context.memoize("w1a:theme:identity-current", self._load_identity)
            )
            edges = _records(context.memoize("w1a:theme:edges-current", self._load_edges))
            loaded_meta = context.memoize("w1a:theme:meta-current", self._load_meta)
            if not isinstance(loaded_meta, Mapping):
                raise TypeError("owner meta is not an object")
            meta = loaded_meta
            if not meta.get("computed_at") or not meta.get("belief_time"):
                raise ValueError("owner meta clocks are absent")
        except Exception:
            issue = "theme_owner_view_unavailable"

        out: dict[tuple[str, str], AdapterResult] = {}
        today = context.generated_at.date()
        for entity in canonical_entities:
            for spec in field_specs:
                if issue:
                    result = self._result(
                        spec,
                        value=None,
                        status="unavailable",
                        reason="owner_unavailable",
                        freshness="unknown",
                        quality="unknown",
                        issues=[issue],
                        computed_at=meta.get("computed_at"),
                        belief_time=meta.get("belief_time"),
                    )
                    out[(entity.id, spec.field_id)] = result
                    continue

                resolved_rows = [
                    row
                    for row in identities
                    if str(row.get("graph_kind") or "") == "company"
                    and str(row.get("resolution_state") or "") == "RESOLVED"
                    and str(row.get("security_id") or "") == entity.id
                ]
                source_nodes = {
                    str(row.get("node_id") or "").strip()
                    for row in resolved_rows
                    if str(row.get("node_id") or "").strip()
                }
                if not resolved_rows:
                    result = self._result(
                        spec,
                        value=None,
                        status="unavailable",
                        reason="owner_missing",
                        freshness="unknown",
                        quality="unknown",
                        issues=["theme_identity_mapping_missing"],
                        computed_at=meta.get("computed_at"),
                        belief_time=meta.get("belief_time"),
                    )
                    out[(entity.id, spec.field_id)] = result
                    continue
                if len(source_nodes) != len(resolved_rows):
                    result = self._result(
                        spec,
                        value=None,
                        status="unavailable",
                        reason="owner_degraded",
                        freshness="unknown",
                        quality="degraded",
                        issues=["theme_identity_mapping_invalid"],
                        computed_at=meta.get("computed_at"),
                        belief_time=meta.get("belief_time"),
                    )
                    out[(entity.id, spec.field_id)] = result
                    continue
                memberships: set[str] = set()
                invalid_interval = False
                for edge in edges:
                    if (
                        str(edge.get("type") or "") != "MEMBER_OF"
                        or str(edge.get("src") or "") not in source_nodes
                        or not str(edge.get("dst") or "").startswith("ltheme:")
                    ):
                        continue
                    try:
                        valid_from = _date(edge.get("valid_from"))
                        valid_to = _date(edge.get("valid_to"))
                    except (TypeError, ValueError):
                        invalid_interval = True
                        break
                    if valid_from is None or (valid_to is not None and valid_to < valid_from):
                        invalid_interval = True
                        break
                    if valid_from <= today and (valid_to is None or valid_to > today):
                        memberships.add(str(edge["dst"]))

                if invalid_interval:
                    result = self._result(
                        spec,
                        value=None,
                        status="unavailable",
                        reason="owner_degraded",
                        freshness="unknown",
                        quality="degraded",
                        issues=["theme_membership_interval_invalid"],
                        computed_at=meta.get("computed_at"),
                        belief_time=meta.get("belief_time"),
                    )
                else:
                    result = self._result(
                        spec,
                        value=sorted(memberships),
                        status="available",
                        reason=None,
                        freshness="unknown",
                        quality="ok",
                        issues=[],
                        computed_at=meta.get("computed_at"),
                        belief_time=meta.get("belief_time"),
                    )
                out[(entity.id, spec.field_id)] = result
        return out
