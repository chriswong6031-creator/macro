"""Read-only adapter over the equity earnings owner's canonical parquet."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from engine.intelligence_workspace.contracts import AdapterResult, CanonicalEntity
from engine.intelligence_workspace.registry import FieldSpec
from engine.intelligence_workspace.resolver import OwnerResolutionRequest, RequestContext


REPO_ROOT = Path(__file__).resolve().parents[3]


class EarningsCalendarAdapter:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        vendor: str = "store",
        symbol_map_loader: Callable[[], Mapping[str, str]] | None = None,
        dataframe_loader: Callable[[], Any] | None = None,
        staleness_assessor: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.vendor = str(vendor)
        self.path = self.repo_root / "data/earnings/earnings.parquet"
        self._injected_symbol_map_loader = symbol_map_loader
        self._injected_dataframe_loader = dataframe_loader
        self._injected_staleness_assessor = staleness_assessor

    def _load_symbol_map(self) -> Mapping[str, str]:
        if self._injected_symbol_map_loader is not None:
            return self._injected_symbol_map_loader()
        from engine.intelligence_workspace.entity import load_current_symbol_map

        return load_current_symbol_map(self.repo_root, self.vendor)

    def _load_dataframe(self) -> tuple[Any | None, str | None]:
        try:
            if self._injected_dataframe_loader is not None:
                frame = self._injected_dataframe_loader()
            else:
                import pandas as pd

                frame = pd.read_parquet(self.path)
        except Exception:
            return None, "earnings_artifact_unavailable"
        if frame is None or not hasattr(frame, "columns"):
            return None, "earnings_artifact_invalid"
        return frame, None

    def _assess_staleness(self, frame: Any, *, today: date) -> Mapping[str, Any]:
        if self._injected_staleness_assessor is not None:
            return self._injected_staleness_assessor(frame, today=today)
        from collectors.equity_earnings import assess_staleness

        return assess_staleness(frame, today=today)

    @staticmethod
    def _date_value(value: Any) -> str | None:
        if value is None:
            return None
        try:
            import pandas as pd

            if pd.isna(value):
                return None
            if isinstance(value, pd.Timestamp):
                return value.date().isoformat()
        except (ImportError, TypeError, ValueError):
            pass
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        return text or None

    @staticmethod
    def _clock_value(value: Any) -> Any:
        if value is None:
            return None
        try:
            import pandas as pd

            if pd.isna(value):
                return None
            if isinstance(value, pd.Timestamp):
                return value.to_pydatetime()
        except (ImportError, TypeError, ValueError):
            pass
        return value

    def _result(
        self,
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
                "source_id": "equity_earnings.next_date",
                "owner": "equity_earnings",
                "license_class": "internal_derived",
                "dataset_id": None,
                "artifact_id": "data/earnings/earnings.parquet",
            },
            provenance={
                "kind": "owner_direct",
                "owner_field_key": spec.owner_field_key,
                "basis": "owner_native",
                "owner_artifact": str(self.path),
            },
        )

    @staticmethod
    def _rows_for_symbol(frame: Any, symbol: str) -> Any:
        import pandas as pd

        if "ticker" in frame.columns:
            return frame[frame["ticker"].astype(str).str.upper() == symbol]
        index_values = pd.Index(frame.index).astype(str).str.upper()
        return frame[index_values == symbol]

    def resolve_many(
        self,
        canonical_entities: Sequence[CanonicalEntity],
        field_specs: Sequence[FieldSpec],
        request: OwnerResolutionRequest,
        context: RequestContext,
    ) -> Mapping[tuple[str, str], AdapterResult]:
        del request
        frame, load_issue = context.memoize(
            f"w1a:earnings:calendar:{self.path}", self._load_dataframe
        )
        try:
            loaded_symbols = context.memoize(
                f"identity:current-symbol-map:{self.vendor}", self._load_symbol_map
            )
            symbol_map = loaded_symbols if isinstance(loaded_symbols, Mapping) else None
        except Exception:
            symbol_map = None

        out: dict[tuple[str, str], AdapterResult] = {}
        for entity in canonical_entities:
            symbol = str(symbol_map.get(entity.id) or "").strip().upper() if symbol_map else ""
            rows = self._rows_for_symbol(frame, symbol) if frame is not None and symbol else None
            for spec in field_specs:
                if load_issue:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_unavailable",
                        freshness="unknown", quality="unknown", issues=[load_issue],
                        observed_at=None, effective_at=None, as_of=None,
                    )
                elif not symbol or rows is None or len(rows) == 0:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_missing",
                        freshness="unknown", quality="unknown", issues=["earnings_row_missing"],
                        observed_at=None, effective_at=None, as_of=None,
                    )
                elif len(rows) != 1:
                    result = self._result(
                        spec, value=None, status="unavailable", reason="owner_degraded",
                        freshness="unknown", quality="degraded", issues=["earnings_row_ambiguous"],
                        observed_at=None, effective_at=None, as_of=None,
                    )
                else:
                    row = rows.iloc[0]
                    row_as_of = self._clock_value(row.get("as_of"))
                    next_date = self._date_value(row.get("next_date"))
                    try:
                        health = self._assess_staleness(rows, today=context.generated_at.date())
                        if not isinstance(health, Mapping):
                            raise TypeError("owner staleness result is not a mapping")
                        stale_count = int(health.get("stale") or 0)
                    except Exception:  # noqa: BLE001 - owner health failure is typed below
                        health = None
                        stale_count = 0
                    if health is None:
                        result = self._result(
                            spec, value=None, status="unavailable", reason="owner_degraded",
                            freshness="unknown", quality="degraded",
                            issues=["earnings_staleness_unavailable"],
                            observed_at=row_as_of, effective_at=next_date, as_of=row_as_of,
                        )
                    elif stale_count > 0:
                        result = self._result(
                            spec, value=None, status="stale", reason="owner_stale",
                            freshness="stale", quality="degraded", issues=["earnings_row_stale"],
                            observed_at=row_as_of, effective_at=next_date, as_of=row_as_of,
                        )
                    elif next_date is None:
                        result = self._result(
                            spec, value=None, status="unknown", reason="value_missing",
                            freshness="fresh", quality="ok", issues=[],
                            observed_at=row_as_of, effective_at=None, as_of=row_as_of,
                        )
                    else:
                        result = self._result(
                            spec, value=next_date, status="available", reason=None,
                            freshness="fresh", quality="ok", issues=[],
                            observed_at=row_as_of, effective_at=next_date, as_of=row_as_of,
                        )
                out[(entity.id, spec.field_id)] = result
        return out
