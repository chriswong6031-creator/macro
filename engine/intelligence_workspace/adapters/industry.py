"""Read-only adapter for the two distinct Stage-industry percentile facts."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from engine.intelligence_workspace.contracts import AdapterResult, CanonicalEntity
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import OwnerResolutionRequest, RequestContext


REPO_ROOT = Path(__file__).resolve().parents[3]


class IndustryAdapter:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        vendor: str = "store",
        symbol_map_loader: Callable[[], Mapping[str, str]] | None = None,
        industry_key_resolver: Callable[[CanonicalEntity], tuple[str, str] | None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.vendor = str(vendor)
        self.rank_path = self.repo_root / "data/stage_analysis/industry_ranks.json"
        self.member_path = self.repo_root / "data/stage_analysis/industry_name_pctile.json"
        self._injected_symbol_map_loader = symbol_map_loader
        self.industry_key_resolver = industry_key_resolver or (
            lambda entity: ("USA", entity.id)
        )

    def _load_symbol_map(self) -> Mapping[str, str]:
        if self._injected_symbol_map_loader is not None:
            return self._injected_symbol_map_loader()
        from engine.intelligence_workspace.entity import load_current_symbol_map

        return load_current_symbol_map(self.repo_root, self.vendor)

    @staticmethod
    def _load_json(path: Path, required_key: str) -> tuple[Mapping[str, Any] | None, str | None]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "industry_artifact_unavailable"
        if not isinstance(payload, Mapping) or not isinstance(payload.get(required_key), Mapping):
            return None, "industry_artifact_invalid"
        return payload, None

    @staticmethod
    def _result(
        spec: FieldSpec,
        *,
        source_id: str,
        artifact: Path,
        value: Any,
        status: str,
        reason: str | None,
        freshness: str,
        quality: str,
        issues: list[str],
        observed_at: Any,
        effective_at: Any,
        as_of: Any,
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
                "source_id": source_id,
                "owner": "stage_industry",
                "license_class": "internal_derived",
                "dataset_id": None,
                "artifact_id": f"data/stage_analysis/{artifact.name}",
            },
            provenance={
                "kind": "owner_derived",
                "owner_field_key": spec.owner_field_key,
                "formula_version": "stage_industry.owner_published",
                "basis": "owner_comparison_set",
                "owner_artifact": str(artifact),
            },
        )

    @staticmethod
    def _health(document: Mapping[str, Any]) -> tuple[str, str, str, list[str]]:
        status = str(document.get("status") or "").strip().lower()
        coverage = document.get("coverage")
        coverage = coverage if isinstance(coverage, Mapping) else {}
        coverage_status = str(coverage.get("status") or "").strip().lower()
        freshness = coverage.get("freshness")
        freshness = freshness if isinstance(freshness, Mapping) else {}
        freshness_status = str(freshness.get("status") or "").strip().lower()
        if freshness_status == "stale":
            return "stale", "stale", "degraded", ["industry_owner_stale"]
        if status == "ready" and coverage_status == "ready" and freshness_status == "current":
            return "available", "fresh", "ok", []
        return "unavailable", "unknown", "degraded", ["industry_owner_degraded"]

    def resolve_many(
        self,
        canonical_entities: Sequence[CanonicalEntity],
        field_specs: Sequence[FieldSpec],
        request: OwnerResolutionRequest,
        context: RequestContext,
    ) -> Mapping[tuple[str, str], AdapterResult]:
        del request
        need_rank = any(spec.owner_field_key == "industry_rank_percentile" for spec in field_specs)
        need_member = any(spec.owner_field_key == "member_rs_percentile" for spec in field_specs)
        rank_doc: Mapping[str, Any] | None = None
        rank_issue: str | None = None
        member_doc: Mapping[str, Any] | None = None
        member_issue: str | None = None
        if need_rank:
            rank_doc, rank_issue = context.memoize(
                f"w1a:industry:ranks:{self.rank_path}",
                lambda: self._load_json(self.rank_path, "regions"),
            )
        if need_member:
            member_doc, member_issue = context.memoize(
                f"w1a:industry:members:{self.member_path}",
                lambda: self._load_json(self.member_path, "percentiles"),
            )

        symbol_map: Mapping[str, str] | None = None
        if need_member:
            try:
                loaded = context.memoize(
                    f"identity:current-symbol-map:{self.vendor}", self._load_symbol_map
                )
                symbol_map = loaded if isinstance(loaded, Mapping) else None
            except Exception:
                symbol_map = None

        out: dict[tuple[str, str], AdapterResult] = {}
        for entity in canonical_entities:
            for spec in field_specs:
                is_rank = spec.owner_field_key == "industry_rank_percentile"
                document = rank_doc if is_rank else member_doc
                issue = rank_issue if is_rank else member_issue
                artifact = self.rank_path if is_rank else self.member_path
                source_id = (
                    "stage_industry.industry_ranks"
                    if is_rank else "stage_industry.industry_name_pctile"
                )
                common = {
                    "source_id": source_id,
                    "artifact": artifact,
                    "observed_at": document.get("built") if document else None,
                    "effective_at": document.get("asof") if document else None,
                    "as_of": document.get("asof") if document else None,
                }
                if issue or document is None:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_unavailable",
                        freshness="unknown", quality="unknown",
                        issues=[issue or "industry_artifact_unavailable"], **common,
                    )
                else:
                    owner_state, freshness, quality, issues = self._health(document)
                    if owner_state == "stale":
                        result = self._result(
                            spec, value=None, status="stale", reason="owner_stale",
                            freshness=freshness, quality=quality, issues=issues, **common,
                        )
                    elif owner_state == "unavailable":
                        result = self._result(
                            spec, value=None, status="unavailable", reason="owner_degraded",
                            freshness=freshness, quality=quality, issues=issues, **common,
                        )
                    elif is_rank:
                        try:
                            key = self.industry_key_resolver(entity)
                        except Exception:
                            key = None
                        matches: list[Mapping[str, Any]] = []
                        if key is not None:
                            region, industry_id = str(key[0]), str(key[1])
                            region_rows = document["regions"].get(region)
                            if isinstance(region_rows, list):
                                matches = [
                                    row for row in region_rows
                                    if isinstance(row, Mapping)
                                    and str(row.get("industry_id")) == industry_id
                                ]
                        if len(matches) != 1:
                            result = self._result(
                                spec, value=None, status="unavailable",
                                reason="owner_missing" if not matches else "owner_degraded",
                                freshness="unknown", quality="unknown" if not matches else "degraded",
                                issues=["industry_rank_missing" if not matches else "industry_rank_ambiguous"],
                                **common,
                            )
                        else:
                            result = self._result(
                                spec, value=matches[0].get("industry_percentile"),
                                status="available", reason=None, freshness=freshness,
                                quality=quality, issues=issues, **common,
                            )
                    else:
                        symbol = str(symbol_map.get(entity.id) or "").strip().upper() if symbol_map else ""
                        percentiles = document["percentiles"]
                        if not symbol or symbol not in percentiles:
                            result = self._result(
                                spec, value=None, status="unavailable", reason="owner_missing",
                                freshness="unknown", quality="unknown",
                                issues=["industry_member_percentile_missing"], **common,
                            )
                        else:
                            result = self._result(
                                spec, value=percentiles[symbol], status="available", reason=None,
                                freshness=freshness, quality=quality, issues=issues, **common,
                            )
                out[(entity.id, spec.field_id)] = result
        return out
