"""Read-only adapter for Company Intelligence latest-event growth metrics."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from engine.intelligence_workspace.contracts import AdapterResult, CanonicalEntity
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import OwnerResolutionRequest, RequestContext


REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEAGE = frozenset({"earnings_history", "score_overlay"})
_READER_REF = "engine.neuralweb.company_intelligence_reader.read_company_intelligence"


class CompanyIntelligenceAdapter:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        vendor: str = "store",
        symbol_map_loader: Callable[[], Mapping[str, str]] | None = None,
        reader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.vendor = str(vendor)
        self._injected_symbol_map_loader = symbol_map_loader
        self._injected_reader = reader

    def _load_symbol_map(self) -> Mapping[str, str]:
        if self._injected_symbol_map_loader is not None:
            return self._injected_symbol_map_loader()
        from engine.intelligence_workspace.entity import load_current_symbol_map

        return load_current_symbol_map(self.repo_root, self.vendor)

    def _read(self, ticker: str) -> tuple[Mapping[str, Any] | None, str | None]:
        try:
            if self._injected_reader is not None:
                payload = self._injected_reader({"ticker": ticker, "limit": 1})
            else:
                from engine.neuralweb.company_intelligence_reader import read_company_intelligence

                payload = read_company_intelligence({"ticker": ticker, "limit": 1})
        except Exception:
            return None, "company_intelligence_reader_failed"
        if not isinstance(payload, Mapping):
            return None, "company_intelligence_reader_invalid"
        return payload, None

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
        call_date: Any,
        lineage: str | None = None,
    ) -> AdapterResult:
        return AdapterResult(
            value=value,
            status=status,
            reason_code=reason,
            unit=spec.unit,
            observed_at=call_date,
            effective_at=call_date,
            as_of=call_date,
            freshness={"state": freshness, "policy": "owner_native"},
            quality={"state": quality, "issues": issues},
            source={
                "source_id": "company_intelligence.latest_event",
                "owner": "company_intelligence",
                "license_class": "internal_derived",
                "dataset_id": None,
            },
            provenance={
                "kind": "owner_derived",
                "owner_field_key": spec.owner_field_key,
                "field_lineage": lineage,
                "basis": "owner_event_metric",
                "owner_artifact": _READER_REF,
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
        try:
            loaded_symbols = context.memoize(
                f"identity:current-symbol-map:{self.vendor}", self._load_symbol_map
            )
            symbol_map = loaded_symbols if isinstance(loaded_symbols, Mapping) else None
        except Exception:
            symbol_map = None

        out: dict[tuple[str, str], AdapterResult] = {}
        for entity in canonical_entities:
            ticker = str(symbol_map.get(entity.id) or "").strip().upper() if symbol_map else ""
            payload: Mapping[str, Any] | None = None
            issue: str | None = None
            if ticker:
                payload, issue = context.memoize(
                    f"w1a:company-intelligence:{ticker}", lambda ticker=ticker: self._read(ticker)
                )
            for spec in field_specs:
                if not ticker:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_missing",
                        freshness="unknown", quality="unknown", issues=["symbol_mapping_missing"],
                        call_date=None,
                    )
                elif issue or payload is None:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_unavailable",
                        freshness="unknown", quality="unknown",
                        issues=[issue or "company_intelligence_reader_failed"], call_date=None,
                    )
                elif payload.get("available") is not True:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_missing",
                        freshness="unknown", quality="unknown",
                        issues=["company_intelligence_not_covered"], call_date=None,
                    )
                else:
                    owner_status = str(payload.get("status") or "").strip().lower()
                    event = payload.get("latest_event")
                    if owner_status == "not_covered" or not isinstance(event, Mapping):
                        result = self._result(
                            spec, value=None, status="unavailable", reason="owner_missing",
                            freshness="unknown", quality="unknown",
                            issues=["company_intelligence_event_missing"], call_date=None,
                        )
                    else:
                        call_date = event.get("call_date")
                        metrics = event.get("metrics") if isinstance(event.get("metrics"), Mapping) else {}
                        field_lineage = event.get("field_lineage")
                        lineage_map = (
                            field_lineage.get("metrics")
                            if isinstance(field_lineage, Mapping)
                            and isinstance(field_lineage.get("metrics"), Mapping)
                            else {}
                        )
                        value = metrics.get(spec.owner_field_key)
                        lineage = lineage_map.get(spec.owner_field_key)
                        if owner_status == "stale":
                            result = self._result(
                                spec, value=None, status="stale", reason="owner_stale",
                                freshness="stale", quality="degraded",
                                issues=["company_intelligence_stale"], call_date=call_date,
                                lineage=lineage if isinstance(lineage, str) else None,
                            )
                        elif owner_status not in {"ready", "partial"}:
                            result = self._result(
                                spec, value=None, status="unavailable", reason="owner_degraded",
                                freshness="unknown", quality="degraded",
                                issues=["company_intelligence_status_unknown"], call_date=call_date,
                            )
                        elif value is None:
                            result = self._result(
                                spec, value=None, status="unknown", reason="value_missing",
                                freshness="unknown" if owner_status == "partial" else "fresh",
                                quality="degraded" if owner_status == "partial" else "ok",
                                issues=["company_intelligence_partial"] if owner_status == "partial" else [],
                                call_date=call_date,
                                lineage=lineage if isinstance(lineage, str) else None,
                            )
                        elif lineage not in _LINEAGE or call_date is None:
                            result = self._result(
                                spec, value=None, status="unavailable", reason="owner_degraded",
                                freshness="unknown", quality="degraded",
                                issues=[
                                    "company_intelligence_lineage_invalid"
                                    if lineage not in _LINEAGE else "company_intelligence_event_clock_missing"
                                ],
                                call_date=call_date,
                            )
                        else:
                            result = self._result(
                                spec, value=value, status="available", reason=None,
                                freshness="unknown" if owner_status == "partial" else "fresh",
                                quality="degraded" if owner_status == "partial" else "ok",
                                issues=["company_intelligence_partial"] if owner_status == "partial" else [],
                                call_date=call_date, lineage=str(lineage),
                            )
                out[(entity.id, spec.field_id)] = result
        return out
