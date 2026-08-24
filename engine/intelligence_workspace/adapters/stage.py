"""Read-only adapter over the owner-published Stage screener artifact."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from engine.intelligence_workspace.contracts import AdapterResult, CanonicalEntity
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import OwnerResolutionRequest, RequestContext


REPO_ROOT = Path(__file__).resolve().parents[3]


class StageAdapter:
    """Resolve Stage facts without re-running the Weinstein classifier."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        vendor: str = "store",
        symbol_map_loader: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.vendor = str(vendor)
        self.path = self.repo_root / "data/stage_analysis/screener.json"
        self._injected_symbol_map_loader = symbol_map_loader

    def _load_symbol_map(self) -> Mapping[str, str]:
        if self._injected_symbol_map_loader is not None:
            return self._injected_symbol_map_loader()
        from engine.intelligence_workspace.entity import load_current_symbol_map

        return load_current_symbol_map(self.repo_root, self.vendor)

    def _load_document(self) -> tuple[Mapping[str, Any] | None, str | None]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "stage_artifact_unavailable"
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rows"), list):
            return None, "stage_artifact_invalid"
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
        observed_at: Any,
        effective_at: Any,
        as_of: Any,
        artifact: Path,
    ) -> AdapterResult:
        return AdapterResult(
            value=value,
            status=status,
            reason_code=reason,
            unit=spec.unit,
            observed_at=observed_at,
            effective_at=effective_at,
            as_of=as_of,
            freshness={"state": freshness, "policy": "owner_native"},
            quality={"state": quality, "issues": issues},
            source={
                "source_id": "stage_analysis.screener",
                "owner": "stage_analysis",
                "license_class": "internal_derived",
                "dataset_id": None,
                "artifact_id": "data/stage_analysis/screener.json",
            },
            provenance={
                "kind": "owner_derived",
                "owner_field_key": spec.owner_field_key,
                "formula_version": "weinstein_stage.owner_published",
                "basis": "owner_classification",
                "owner_artifact": str(artifact),
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
        document, load_issue = context.memoize(
            f"w1a:stage:screener:{self.path}", self._load_document
        )
        try:
            symbol_map = context.memoize(
                f"identity:current-symbol-map:{self.vendor}", self._load_symbol_map
            )
        except Exception:
            symbol_map = None
        if not isinstance(symbol_map, Mapping):
            symbol_map = None

        rows_by_symbol: dict[str, list[Mapping[str, Any]]] = {}
        if document is not None:
            for raw in document["rows"]:
                if not isinstance(raw, Mapping) or raw.get("source") != "live":
                    continue
                ticker = str(raw.get("ticker") or "").strip().upper()
                if ticker:
                    rows_by_symbol.setdefault(ticker, []).append(raw)

        out: dict[tuple[str, str], AdapterResult] = {}
        for entity in canonical_entities:
            symbol = str(symbol_map.get(entity.id) or "").strip().upper() if symbol_map else ""
            matches = rows_by_symbol.get(symbol, []) if symbol else []
            for spec in field_specs:
                common = {
                    "observed_at": document.get("built") if document else None,
                    "effective_at": document.get("stage_week_end") if document else None,
                    "as_of": document.get("asof") if document else None,
                    "artifact": self.path,
                }
                if load_issue:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_unavailable",
                        freshness="unknown", quality="unknown", issues=[load_issue], **common,
                    )
                elif not symbol:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_missing",
                        freshness="unknown", quality="unknown", issues=["symbol_mapping_missing"], **common,
                    )
                elif len(matches) != 1:
                    issue = "stage_row_missing" if not matches else "stage_row_ambiguous"
                    result = self._result(
                        spec, value=None, status="unavailable",
                        reason="owner_missing" if not matches else "owner_degraded",
                        freshness="unknown", quality="unknown" if not matches else "degraded",
                        issues=[issue], **common,
                    )
                else:
                    row = matches[0]
                    row_common = {
                        "observed_at": row.get("stage_source_asof") or document.get("built"),
                        "effective_at": row.get("stage_week_end") or document.get("stage_week_end"),
                        "as_of": document.get("asof"),
                        "artifact": self.path,
                    }
                    if row.get("retired") is True:
                        result = self._result(
                            spec, value=None, status="unavailable", reason="retired_entity",
                            freshness="not_applicable", quality="unknown",
                            issues=["retired_entity"], **row_common,
                        )
                    elif row.get("stage_current") is False:
                        result = self._result(
                            spec, value=None, status="stale", reason="owner_stale",
                            freshness="stale", quality="degraded",
                            issues=["stage_row_stale"], **row_common,
                        )
                    elif row.get("stage_current") is not True:
                        result = self._result(
                            spec, value=None, status="unknown", reason="owner_degraded",
                            freshness="unknown", quality="degraded",
                            issues=["stage_current_unknown"], **row_common,
                        )
                    else:
                        stage = row.get("stage")
                        if stage in (None, 0):
                            result = self._result(
                                spec, value=None, status="not_applicable", reason="not_applicable",
                                freshness="not_applicable", quality="ok",
                                issues=[], **row_common,
                            )
                        elif (
                            not isinstance(stage, int)
                            or isinstance(stage, bool)
                            or stage not in {1, 2, 3, 4}
                        ):
                            result = self._result(
                                spec, value=None, status="unavailable", reason="owner_degraded",
                                freshness="unknown", quality="degraded",
                                issues=["stage_value_invalid"], **row_common,
                            )
                        else:
                            value = stage if spec.owner_field_key == "stage" else row.get("weeks_in_stage")
                            if (
                                not isinstance(value, int)
                                or isinstance(value, bool)
                                or (spec.owner_field_key == "weeks_in_stage" and value < 0)
                            ):
                                result = self._result(
                                    spec, value=None, status="unavailable", reason="owner_degraded",
                                    freshness="unknown", quality="degraded",
                                    issues=["stage_value_invalid"], **row_common,
                                )
                            else:
                                result = self._result(
                                    spec, value=value, status="available", reason=None,
                                    freshness="fresh", quality="ok", issues=[], **row_common,
                                )
                out[(entity.id, spec.field_id)] = result
        return out
