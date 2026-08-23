"""Dynamic subscriber projection for owner-governed Theme Graph structure."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.intelligence_workspace.contracts import (
    AdapterResult,
    CanonicalEntity,
    RightsDecision,
)
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import RequestContext


class ThemeRightsProjector:
    """Re-read every represented source family's current rights on every projection."""

    def __init__(
        self,
        *,
        family_resolver: Callable[[object], str | None] | None = None,
        assert_allowed: Callable[[str], Any] | None = None,
    ) -> None:
        self._family_resolver = family_resolver
        self._assert_allowed = assert_allowed

    def __call__(
        self,
        spec: FieldSpec,
        result: AdapterResult,
        entity: CanonicalEntity,
        context: RequestContext,
    ) -> RightsDecision:
        del entity, context
        if spec.rights_policy != "owner_dynamic" or result.status != "available":
            return RightsDecision(True)
        if not isinstance(result.value, (list, tuple)):
            return RightsDecision(False)

        from engine.theme_graph import rights

        family_resolver = self._family_resolver or rights.family_for_node_id
        assert_allowed = self._assert_allowed or rights.assert_public_emission_allowed

        families: set[str] = set()
        for node_id in result.value:
            try:
                family = family_resolver(node_id)
            except Exception:
                return RightsDecision(False)
            if not family:
                return RightsDecision(False)
            families.add(str(family))

        try:
            for family in sorted(families):
                assert_allowed(family)
        except Exception:
            return RightsDecision(False)
        return RightsDecision(True)


def project_theme_rights(
    spec: FieldSpec,
    result: AdapterResult,
    entity: CanonicalEntity,
    context: RequestContext,
) -> RightsDecision:
    """Default resolver callback; intentionally creates no cached rights decision."""
    return ThemeRightsProjector()(spec, result, entity, context)
