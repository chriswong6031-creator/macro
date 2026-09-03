"""Strict, zero-authority contracts for temporal-scale research."""

from .contracts import (
    ArtifactAttackResult,
    ArtifactTest,
    BarReceipt,
    ChartRecipe,
    ContractError,
    EXPORT_PRECISION_INSUFFICIENT,
    KernelSignature,
    REQUIRED_EXPORT_COLUMNS,
    atomic_write_json,
    strict_json_dumps,
)

__all__ = [
    "ArtifactAttackResult",
    "ArtifactTest",
    "BarReceipt",
    "ChartRecipe",
    "ContractError",
    "EXPORT_PRECISION_INSUFFICIENT",
    "KernelSignature",
    "REQUIRED_EXPORT_COLUMNS",
    "atomic_write_json",
    "strict_json_dumps",
]
