"""Atomic builder + manifest for Macro & Monetary workspace snapshots (F01 / R1A).

Reads the owner artifact, composes the ``liquidity_regime`` / US snapshot, seals
and validates it against the closed contract, and publishes atomically:

    <out_root>/workspaces/liquidity_regime/US/latest.json
    <out_root>/workspaces/manifest.json

The suite manifest carries the generation identity plus, per published
workspace, the content hash, byte size, availability state, minimum client
contract, and build state. The workspace body is written FIRST (tmp + os.replace)
and the manifest LAST, so a reader that validates manifest -> workspace hash
before rendering never sees a manifest describing a body that is not yet on disk.

Pure projection: no owner path is mutated, no mutable service state is created.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from engine.market_os.macro_workspaces import contract, liquidity_regime, registry

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_ROOT = ROOT / "site" / "macrodata"
DEFAULT_REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"
MIN_CLIENT_CONTRACT = f"{contract.CONTRACT_ID}@{contract.CONTRACT_VERSION}"


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_write_bytes(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return len(data)


def _snapshot_bytes(snapshot: Mapping[str, Any]) -> bytes:
    # Human-diffable published form (indented). The digest is computed from the
    # canonical form inside contract.py and is independent of this layout.
    return (json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def build_liquidity_regime(
    *,
    regime_latest_path: Path | str = DEFAULT_REGIME_LATEST,
    out_root: Path | str = DEFAULT_OUT_ROOT,
    built_at: str,
    prior_snapshot_path: Path | str | None = None,
    code_version: str | None = None,
    write: bool = True,
) -> dict:
    """Compose, seal, validate, and (optionally) publish the US liquidity-regime
    snapshot. Returns a receipt dict with the sealed snapshot, digest, byte size,
    manifest, and written paths (paths are None when ``write`` is False)."""
    regime_latest = _load_json(Path(regime_latest_path))
    prior = _load_json(Path(prior_snapshot_path)) if prior_snapshot_path else None

    body = liquidity_regime.compose(
        regime_latest, built_at=built_at, prior_snapshot=prior, code_version=code_version
    )
    snapshot = contract.finalize(body)
    contract.validate(snapshot)  # raises ContractError on any violation

    payload = _snapshot_bytes(snapshot)
    digest = snapshot["generation"]["content_sha256"]
    entry = registry.entry("liquidity_regime")

    workspace_rel = Path("workspaces") / "liquidity_regime" / "US" / "latest.json"
    manifest_rel = Path("workspaces") / "manifest.json"
    ws_path = Path(out_root) / workspace_rel
    manifest_path = Path(out_root) / manifest_rel

    manifest = {
        "schema": "mastermind.macro_workspace_manifest.v1",
        "generated_at": built_at,
        "min_client_contract": MIN_CLIENT_CONTRACT,
        "workspaces": {
            "liquidity_regime/US": {
                "workspace": "liquidity_regime",
                "region": "US",
                "path": str(workspace_rel).replace(os.sep, "/"),
                "content_sha256": digest,
                "bytes": len(payload),
                "availability_state": snapshot["availability"]["state"],
                "headline_state": snapshot["headline"]["state_id"],
                "build_state": entry["build_state"],
                "generation_id": snapshot["generation"]["generation_id"],
                "built_at": built_at,
            }
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

    written = {"workspace": None, "manifest": None}
    if write:
        _atomic_write_bytes(ws_path, payload)          # body first ...
        _atomic_write_bytes(manifest_path, manifest_bytes)  # ... manifest last
        written = {"workspace": str(ws_path), "manifest": str(manifest_path)}

    return {
        "snapshot": snapshot,
        "digest": digest,
        "bytes": len(payload),
        "manifest": manifest,
        "paths": written,
    }


def build_all(*, out_root: Path | str = DEFAULT_OUT_ROOT,
              regime_latest_path: Path | str = DEFAULT_REGIME_LATEST,
              built_at: str, code_version: str | None = None,
              prior_snapshot_path: Path | str | None = None,
              write: bool = True) -> dict:
    """Build every ``BUILT`` workspace. R1A: liquidity_regime / US only."""
    receipts = {
        "liquidity_regime/US": build_liquidity_regime(
            regime_latest_path=regime_latest_path, out_root=out_root, built_at=built_at,
            prior_snapshot_path=prior_snapshot_path, code_version=code_version, write=write,
        )
    }
    return receipts
