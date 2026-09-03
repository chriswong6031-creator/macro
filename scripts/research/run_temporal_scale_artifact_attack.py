#!/usr/bin/env python3
"""Reproducible, local-only coordinator for temporal-scale W1A evidence."""
from __future__ import annotations

import argparse
import hashlib
import platform
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from engine.trial_ledger import DEFAULT_PATH  # noqa: E402
from scripts.research.temporal_scale.artifact_attack import (  # noqa: E402
    ArtifactAttackError,
    default_artifact_grid,
    run_artifact_attack,
)
from scripts.research.temporal_scale.chart_export import ExportError, load_chart_export  # noqa: E402
from scripts.research.temporal_scale.contracts import (  # noqa: E402
    ARTIFACT_ATTACK_SCHEMA,
    ArtifactAttackResult,
    ChartRecipe,
    ContractError,
    LowerGrainRecipe,
    atomic_write_json,
    strict_json_dumps,
)
from scripts.research.temporal_scale.kernel_memory import (  # noqa: E402
    KernelMemoryError,
    canonical_kernel_signature,
)
from scripts.research.temporal_scale.parity import (  # noqa: E402
    ParityError,
    compare_indicator_parity,
)


_OPERATION_KEY = "temporal-grain-gakd-artifact-attack-r1-20260903-sol-001"
_TRIAL_FAMILY = "temporal_grain_gakd_r1"
_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_trade": False,
    "may_modify_prophet": False,
}


class CliError(ValueError):
    """The requested local evidence operation is unsafe or malformed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-recipe", "parity", "attack"):
        child = subcommands.add_parser(name)
        child.add_argument("--recipe", type=Path, required=True)
        child.add_argument("--csv", type=Path, required=True)
        child.add_argument("--output-dir", type=Path, required=True)
        child.add_argument("--ledger-path", type=Path)
        child.add_argument("--lower-grain-csv", type=Path)
        child.add_argument("--lower-grain-recipe", type=Path)
        child.add_argument("--observation-ms", type=int)
    return parser


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except (OSError, TypeError, ValueError) as exc:
        raise CliError(f"cannot hash input: {path}") from exc


def _json_hash(value: object) -> str:
    return _sha256_bytes(strict_json_dumps(value).encode("utf-8"))


def _git_head() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def _close(loaded: object) -> pd.Series:
    frame = loaded.frame  # type: ignore[attr-defined]
    return pd.Series(
        frame["TG_close"].to_numpy(dtype=float),
        index=pd.Index(frame["TG_time_open_ms"].tolist(), dtype="int64", name="TG_time_open_ms"),
        dtype=float,
        name="TG_close",
    )


def _safe_ledger_path(args: argparse.Namespace) -> Path:
    ledger = args.ledger_path or (args.output_dir / "trial_ledger.jsonl")
    try:
        if ledger.resolve() == DEFAULT_PATH.resolve():
            raise CliError("production TrialLedger path is prohibited")
    except CliError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CliError("ledger path is invalid") from exc
    return ledger


def _write_objects(output_dir: Path, objects: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for filename, value in objects.items():
        path = output_dir / filename
        atomic_write_json(path, value)
        hashes[filename] = _sha256_path(path)
    return hashes


def _manifest(
    args: argparse.Namespace,
    *,
    input_hashes: Mapping[str, str],
    output_hashes: Mapping[str, str],
    ledger_path: Path,
    csv_loaded: bool,
    status: str,
    ledger_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "mastermind.temporal_artifact_attack_run_manifest.v1",
        "operation_key": _OPERATION_KEY,
        "command": list(sys.argv),
        "subcommand": args.command,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git_head": _git_head(),
        "input_sha256": dict(input_hashes),
        "output_sha256": dict(output_hashes),
        "ledger_path": str(ledger_path),
        "ledger_sha256": ledger_sha256,
        "observation_ms": args.observation_ms,
        "csv_loaded": csv_loaded,
        "network_used": False,
        "production_ledger_used": False,
        "status": status,
    }


def _unresolved_result(recipe: ChartRecipe) -> tuple[dict[str, Any], ArtifactAttackResult]:
    frozen_grid = {
        "status": "UNRESOLVED_DATA",
        "reason": "INCOMPLETE_RECIPE",
        "missing_fields": list(recipe.missing_fields),
    }
    grid_hash = _json_hash(frozen_grid)
    receipt = _json_hash({
        "recipe_id": recipe.recipe_id,
        "missing_fields": list(recipe.missing_fields),
        "status": "UNRESOLVED_DATA",
    })
    result = ArtifactAttackResult(
        schema_version=ARTIFACT_ATTACK_SCHEMA,
        operation_key=_OPERATION_KEY,
        recipes=(recipe.recipe_id,),
        frozen_grid_hash=grid_hash,
        trial_family=_TRIAL_FAMILY,
        tests=(),
        parity={"status": "UNRESOLVED_DATA"},
        mechanical_status="UNRESOLVED_DATA",
        final_mechanism_classification=None,
        mechanical_receipts=(receipt,),
        observed_indicator_reproduction={"status": "UNRESOLVED_DATA"},
        observed_indicator_reproduction_receipts=(receipt,),
        owner_probe_control={"status": "UNRESOLVED_DATA"},
        owner_probe_control_receipts=(receipt,),
        authority=dict(_AUTHORITY),
    )
    return frozen_grid, result


def _write_incomplete(
    args: argparse.Namespace,
    *,
    recipe: ChartRecipe,
    ledger_path: Path,
    recipe_hash: str,
) -> int:
    frozen_grid, result = _unresolved_result(recipe)
    objects = {
        "normalized_recipe.json": recipe.to_dict(),
        "bar_receipts.json": {"status": "UNRESOLVED_DATA", "receipts": []},
        "kernel_signature.json": {"status": "UNRESOLVED_DATA"},
        "parity_receipt.json": {"status": "UNRESOLVED_DATA"},
        "frozen_grid.json": frozen_grid,
        "artifact_attack_result.json": result.to_dict(),
    }
    hashes = _write_objects(args.output_dir, objects)
    manifest = _manifest(
        args,
        input_hashes={"recipe": recipe_hash},
        output_hashes=hashes,
        ledger_path=ledger_path,
        csv_loaded=False,
        status="UNRESOLVED_DATA",
    )
    atomic_write_json(args.output_dir / "run_manifest.json", manifest)
    print("UNRESOLVED_DATA:INCOMPLETE_RECIPE")
    return 0


def _read_lower(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError, ValueError) as exc:
        raise CliError("lower-grain CSV cannot be loaded") from exc


def _run(args: argparse.Namespace) -> int:
    if args.observation_ms is not None and args.observation_ms < 0:
        raise CliError("observation-ms must be nonnegative")
    ledger_path = _safe_ledger_path(args)
    recipe_hash = _sha256_path(args.recipe)
    try:
        recipe = ChartRecipe.from_json(args.recipe)
    except (ContractError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise CliError(f"recipe validation failed: {exc}") from exc
    if recipe.capture_status == "incomplete":
        return _write_incomplete(
            args, recipe=recipe, ledger_path=ledger_path, recipe_hash=recipe_hash,
        )

    try:
        loaded = load_chart_export(args.recipe, args.csv)
    except ExportError as exc:
        raise CliError(f"chart export validation failed: {exc}") from exc
    input_hashes = {"recipe": recipe_hash, "csv": loaded.csv_sha256}
    grid = default_artifact_grid(loaded.recipe)
    print(f"FROZEN_GRID_SHA256={grid.sha256()}")
    parity = compare_indicator_parity(loaded, tolerance=1e-10)
    kernel = canonical_kernel_signature(_close(loaded))
    objects: dict[str, Mapping[str, Any]] = {
        "normalized_recipe.json": loaded.recipe.to_dict(),
        "bar_receipts.json": {"receipts": [receipt.to_dict() for receipt in loaded.receipts]},
        "kernel_signature.json": kernel.to_dict(),
        "parity_receipt.json": parity.to_dict(),
        "frozen_grid.json": {"grid": grid.to_dict(), "sha256": grid.sha256()},
    }

    result: ArtifactAttackResult | None = None
    if args.command == "attack":
        lower = None
        lower_recipe = None
        lower_csv_sha256 = None
        if args.lower_grain_csv is not None:
            lower_csv_sha256 = _sha256_path(args.lower_grain_csv)
            input_hashes["lower_grain_csv"] = lower_csv_sha256
            lower = _read_lower(args.lower_grain_csv)
        if args.lower_grain_recipe is not None:
            input_hashes["lower_grain_recipe"] = _sha256_path(args.lower_grain_recipe)
            try:
                lower_recipe = LowerGrainRecipe.from_json(args.lower_grain_recipe)
            except (ContractError, OSError, UnicodeError, TypeError, ValueError) as exc:
                raise CliError(f"lower-grain recipe validation failed: {exc}") from exc
            objects["normalized_lower_grain_recipe.json"] = lower_recipe.to_dict()
        result = run_artifact_attack(
            loaded,
            lower_grain_rows=lower,
            lower_grain_recipe=lower_recipe,
            lower_grain_csv_sha256=lower_csv_sha256,
            grid=grid,
            ledger_path=ledger_path,
        )
        objects["artifact_attack_result.json"] = result.to_dict()

    output_hashes = _write_objects(args.output_dir, objects)
    ledger_hash = _sha256_path(ledger_path) if result is not None and ledger_path.is_file() else None
    status = result.mechanical_status if result is not None else parity.status
    manifest = _manifest(
        args,
        input_hashes=input_hashes,
        output_hashes=output_hashes,
        ledger_path=ledger_path,
        csv_loaded=True,
        status=status,
        ledger_sha256=ledger_hash,
    )
    atomic_write_json(args.output_dir / "run_manifest.json", manifest)
    if parity.status != "PASS" and args.command != "attack":
        print("PARITY_FAIL", file=sys.stderr)
        return 2
    print(status)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (ArtifactAttackError, CliError, ContractError, KernelMemoryError, ParityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
