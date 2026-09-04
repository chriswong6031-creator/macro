"""Atomic builder + manifest for Macro & Monetary workspace snapshots (F01 / R1A).

Reads the owner artifact, composes the ``liquidity_regime`` / US snapshot, seals
and validates it against the closed contract, and publishes atomically:

    <out_root>/workspaces/liquidity_regime/US/latest.json
    <out_root>/workspaces/manifest.json

The suite manifest carries the generation identity plus, per published
workspace, the content hash, byte size, availability state, minimum client
contract, and build state. The workspace body is written FIRST (tmp + os.replace)
and the manifest LAST. That ordering bounds the failure window to one
direction only: a concurrent reader can observe an OLD manifest paired with a
NEWER body on disk (the manifest's declared content_sha256 then differs from
the body's actual digest), but never the reverse -- os.replace of the body
always completes before the manifest write begins, so a manifest can never
name a body that is not yet on disk.

This is a property AVAILABLE to a validating reader, not a guarantee this repo
enforces end-to-end today: no consumer shipped in R1A cross-checks the
manifest's declared content_sha256 against the body it names before using it
(``consumer.py`` only self-validates a body's own embedded digest against
itself; it never opens the manifest at all). A reader that wants torn-
generation safety must read the manifest, then the body, then recompute and
compare the body's digest against the manifest's declared content_sha256
itself -- R1B is expected to implement that validating reader.

Pure projection: no owner path is mutated, no mutable service state is created.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from engine.market_os.macro_workspaces import (
    business_activity,
    contract,
    financial_conditions,
    growth,
    inflation,
    labor,
    liquidity_regime,
    monetary_policy,
    registry,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_ROOT = ROOT / "site" / "macrodata"
DEFAULT_REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"
DEFAULT_INFLATION_INTEL = ROOT / "data" / "release_forecast" / "inflation_intelligence.json"
DEFAULT_RATES_COMMAND = ROOT / "data" / "rates_command" / "latest.json"
DEFAULT_INTL_RISK = ROOT / "data" / "intl_risk" / "latest.json"
MIN_CLIENT_CONTRACT = f"{contract.CONTRACT_ID}@{contract.CONTRACT_VERSION}"


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_json_or_empty(path: Path) -> dict:
    """Missing/unreadable owner artifact -> {} so the composer emits its own
    typed SOURCE_FAILED states instead of the builder crashing. A malformed
    (present but non-JSON) artifact still raises: silence there would launder
    corruption into 'source absent'."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


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


def _compose_workspace(workspace_id: str, *, regime_latest: dict,
                       inflation_intel: dict, rates_command: dict,
                       intl_risk: dict, built_at: str,
                       prior_snapshot: dict | None,
                       code_version: str | None) -> dict:
    """Route one BUILT workspace to its composer with its owner-native inputs.

    Every composer degrades typed (SOURCE_FAILED / ABSENT) when its owner block
    is missing; the builder never fabricates an input.
    """
    if workspace_id == "liquidity_regime":
        return liquidity_regime.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "growth_real_economy":
        return growth.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "business_activity":
        return business_activity.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "labor_markets":
        return labor.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "financial_conditions":
        return financial_conditions.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "inflation_system":
        return inflation.compose(
            inflation_intel, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "monetary_policy":
        return monetary_policy.compose(
            rates_command,
            (intl_risk.get("cb_desk") or {}),
            (regime_latest.get("rate_inflation_transmission") or {}),
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    raise ValueError(f"no builder route for workspace id: {workspace_id!r}")


def build_all(*, out_root: Path | str = DEFAULT_OUT_ROOT,
              regime_latest_path: Path | str = DEFAULT_REGIME_LATEST,
              inflation_intel_path: Path | str = DEFAULT_INFLATION_INTEL,
              rates_command_path: Path | str = DEFAULT_RATES_COMMAND,
              intl_risk_path: Path | str = DEFAULT_INTL_RISK,
              built_at: str, code_version: str | None = None,
              prior_snapshot_path: Path | str | None = None,
              write: bool = True) -> dict:
    """Build every ``BUILT`` workspace (registry-driven) for region US.

    All workspace bodies are written FIRST (each tmp + os.replace), then ONE
    combined manifest covering every published workspace is written LAST — the
    same one-directional torn-generation bound documented in the module
    docstring, now suite-wide. ``prior_snapshot_path`` applies only to
    liquidity_regime (R1A compatibility); other workspaces WARMUP on first
    print and pick up their own priors once a publication history exists.
    """
    regime_latest = _load_json(Path(regime_latest_path))
    inflation_intel = _load_json_or_empty(Path(inflation_intel_path))
    rates_command = _load_json_or_empty(Path(rates_command_path))
    intl_risk = _load_json_or_empty(Path(intl_risk_path))

    out = Path(out_root)
    manifest_entries: dict[str, dict] = {}
    receipts: dict[str, dict] = {}
    pending_bodies: list[tuple[Path, bytes]] = []

    for wid in registry.built_ids():
        prior = None
        if wid == "liquidity_regime" and prior_snapshot_path:
            prior = _load_json(Path(prior_snapshot_path))
        else:
            # Self-prior: the previously published artifact, when present and
            # loadable, is this build's prior print (WARMUP otherwise).
            prior_path = out / "workspaces" / wid / "US" / "latest.json"
            if prior_path.exists():
                try:
                    prior = _load_json(prior_path)
                except Exception:
                    prior = None

        body = _compose_workspace(
            wid, regime_latest=regime_latest, inflation_intel=inflation_intel,
            rates_command=rates_command, intl_risk=intl_risk, built_at=built_at,
            prior_snapshot=prior, code_version=code_version)
        snapshot = contract.finalize(body)
        contract.validate(snapshot)

        payload = _snapshot_bytes(snapshot)
        digest = snapshot["generation"]["content_sha256"]
        workspace_rel = Path("workspaces") / wid / "US" / "latest.json"
        ws_path = out / workspace_rel

        manifest_entries[f"{wid}/US"] = {
            "workspace": wid,
            "region": "US",
            "path": str(workspace_rel).replace(os.sep, "/"),
            "content_sha256": digest,
            "bytes": len(payload),
            "availability_state": snapshot["availability"]["state"],
            "headline_state": snapshot["headline"]["state_id"],
            "build_state": registry.entry(wid)["build_state"],
            "generation_id": snapshot["generation"]["generation_id"],
            "built_at": built_at,
        }
        receipts[f"{wid}/US"] = {
            "snapshot": snapshot,
            "digest": digest,
            "bytes": len(payload),
            "paths": {"workspace": str(ws_path) if write else None, "manifest": None},
        }
        pending_bodies.append((ws_path, payload))

    manifest = {
        "schema": "mastermind.macro_workspace_manifest.v1",
        "generated_at": built_at,
        "min_client_contract": MIN_CLIENT_CONTRACT,
        "workspaces": manifest_entries,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = out / "workspaces" / "manifest.json"

    if write:
        for ws_path, payload in pending_bodies:   # every body first ...
            _atomic_write_bytes(ws_path, payload)
        _atomic_write_bytes(manifest_path, manifest_bytes)  # ... manifest last
        for key in receipts:
            receipts[key]["paths"]["manifest"] = str(manifest_path)

    receipts["_manifest"] = {"manifest": manifest, "path": str(manifest_path) if write else None}
    return receipts
