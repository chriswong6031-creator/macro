"""Pure, deterministic projections for Company Theme Exposure."""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

import yaml

from engine.company_intelligence.contracts import ContractError, iso_timestamp, parse_date, safe_ticker, validate_context, validate_manifest as validate_company_manifest
from .contracts import (
    AUTHORITY, EXPOSURE_SCHEMA, MANIFEST_SCHEMA, bytes_sha256, canonical_json_bytes,
    canonical_json_sha256, company_filename, validate_exposure, validate_manifest,
)


THEME_STATE_MAX_AGE_DAYS = 5


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return parse_date(value, field="date")
    except ContractError:
        return None


def _theme_state_receipt(payload: Mapping[str, Any] | None, *, as_of: date) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(payload, Mapping):
        return {"status": "missing", "as_of": None, "sha256": None}, ["theme_state_missing"]
    stamp = _as_date(payload.get("as_of"))
    # ``stale_legs`` is an explicit producer admission. Do not turn it into
    # narrative; it is a freshness gate for the entire descriptive receipt.
    valid_schema = payload.get("schema") == "neuralweb.theme_state.v1"
    if not valid_schema or stamp is None:
        return {"status": "missing", "as_of": None, "sha256": None}, ["theme_state_invalid"]
    receipt = {"status": "fresh", "as_of": stamp.isoformat(), "sha256": canonical_json_sha256(payload)}
    if (as_of - stamp).days > THEME_STATE_MAX_AGE_DAYS or payload.get("stale_legs"):
        receipt["status"] = "stale"
        return receipt, ["theme_state_stale"]
    return receipt, []


def _active_membership(membership: Mapping[str, Any]) -> dict[str, set[str]]:
    """Return ticker → active basket IDs; removed members are never carried forward."""
    baskets = membership.get("baskets")
    if not isinstance(baskets, Mapping):
        raise ContractError("membership.baskets must be an object")
    result: dict[str, set[str]] = {}
    for basket_id, raw_basket in baskets.items():
        if not isinstance(basket_id, str) or not isinstance(raw_basket, Mapping):
            raise ContractError("membership basket invalid")
        members = raw_basket.get("members")
        if not isinstance(members, list):
            raise ContractError(f"membership {basket_id} members invalid")
        for member in members:
            if not isinstance(member, Mapping) or member.get("removed") is not None:
                continue
            try:
                ticker = safe_ticker(member.get("ticker"))
            except ContractError as exc:
                raise ContractError(f"membership {basket_id} member ticker invalid") from exc
            result.setdefault(ticker, set()).add(basket_id)
    return result


def _crosswalk_index(crosswalk: Mapping[str, Any], membership: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Validate the canonical mapping and return basket ID → compact theme label."""
    if not isinstance(crosswalk.get("version"), int) or not isinstance(crosswalk.get("themes"), list):
        raise ContractError("theme crosswalk invalid")
    known_baskets = membership.get("baskets")
    if not isinstance(known_baskets, Mapping):
        raise ContractError("membership.baskets must be an object")
    index: dict[str, dict[str, str]] = {}
    theme_ids: set[str] = set()
    for raw in crosswalk["themes"]:
        if not isinstance(raw, Mapping):
            raise ContractError("theme crosswalk theme invalid")
        theme_id = raw.get("id")
        names = (raw.get("name_en"), raw.get("name_zh"))
        baskets = raw.get("basket_ids")
        if (
            not isinstance(theme_id, str)
            or not theme_id
            or theme_id in theme_ids
            or raw.get("foresight_id") != theme_id
        ):
            raise ContractError("theme crosswalk ID invalid or duplicate")
        if not all(isinstance(name, str) and name for name in names) or not isinstance(baskets, list):
            raise ContractError("theme crosswalk theme fields invalid")
        theme_ids.add(theme_id)
        for basket_id in baskets:
            if not isinstance(basket_id, str) or basket_id not in known_baskets:
                raise ContractError(f"theme crosswalk mapped basket invalid: {basket_id!r}")
            if basket_id in index:
                raise ContractError(f"theme crosswalk basket mapped twice: {basket_id}")
            index[basket_id] = {"theme_id": theme_id, "name_en": names[0], "name_zh": names[1]}
    unmapped = crosswalk.get("unmapped_baskets")
    if not isinstance(unmapped, list):
        raise ContractError("theme crosswalk unmapped_baskets invalid")
    explicit_unmapped: set[str] = set()
    for raw in unmapped:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str) or not raw.get("reason"):
            raise ContractError("theme crosswalk unmapped basket invalid")
        basket_id = raw["id"]
        if basket_id not in known_baskets or basket_id in explicit_unmapped or basket_id in index:
            raise ContractError("theme crosswalk unmapped basket invalid or overlapping")
        explicit_unmapped.add(basket_id)
    # The crosswalk declares whether an existing basket is intentionally out of
    # scope.  A newly added basket must make an explicit editorial choice.
    unaccounted = set(known_baskets) - set(index) - explicit_unmapped
    if unaccounted:
        raise ContractError(f"theme crosswalk does not account for baskets: {sorted(unaccounted)}")
    return index


def build_exposures(
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    company_manifest: Mapping[str, Any],
    membership: Mapping[str, Any],
    crosswalk: Mapping[str, Any],
    theme_state: Mapping[str, Any] | None,
    as_of: str | date | None = None,
) -> dict[str, dict[str, Any]]:
    """Project active curated membership through the canonical crosswalk.

    No event text, scores, recommendation, stage, or inferred relationship is
    copied from the source planes.  ``latest_event_*`` are identity receipts
    only, proving the exact Company Intelligence event the sidecar was built
    beside.
    """
    validate_company_manifest(company_manifest)
    ci_generation = str(company_manifest["generation_id"])
    marker_sha = canonical_json_sha256(company_manifest)
    run_date = _as_date(as_of) if as_of is not None else _as_date(company_manifest.get("generated_at"))
    if run_date is None:
        raise ContractError("as_of or company intelligence generated_at required")
    current_by_ticker = _active_membership(membership)
    theme_by_basket = _crosswalk_index(crosswalk, membership)
    state_receipt, warnings = _theme_state_receipt(theme_state, as_of=run_date)
    exposures: dict[str, dict[str, Any]] = {}
    for ticker in sorted(contexts):
        context = contexts[ticker]
        validate_context(context)
        if safe_ticker(ticker) != safe_ticker(context["company"]["ticker"]):
            raise ContractError("context ticker key mismatch")
        if context.get("generation_id") != ci_generation:
            raise ContractError("context does not match pinned company intelligence generation")
        active = current_by_ticker.get(ticker, set())
        items = [
            {**theme_by_basket[basket], "basket_id": basket}
            for basket in active
            if basket in theme_by_basket
        ]
        items.sort(key=lambda value: (value["theme_id"], value["basket_id"]))
        latest = context.get("latest_event")
        if latest is not None and not isinstance(latest, Mapping):
            raise ContractError("context latest event invalid")
        exposure = {
            "schema": EXPOSURE_SCHEMA,
            "authority": AUTHORITY,
            "generated_at": str(company_manifest["generated_at"]),
            "generation_id": "0" * 24,
            "status": "partial" if warnings else "ready",
            "company": {"ticker": ticker},
            "company_intelligence": {
                "generation_id": ci_generation,
                "context_sha256": canonical_json_sha256(context),
                "latest_event_id": latest.get("event_id") if latest else None,
                "latest_event_call_date": latest.get("call_date") if latest else None,
            },
            "exposures": items,
            "theme_state": state_receipt,
            "warnings": warnings,
        }
        exposures[ticker] = exposure
    return exposures


def build_bundle(
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    company_manifest: Mapping[str, Any],
    membership: Mapping[str, Any],
    crosswalk: Mapping[str, Any],
    theme_state: Mapping[str, Any] | None,
    as_of: str | date | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    exposures = build_exposures(
        contexts, company_manifest=company_manifest, membership=membership,
        crosswalk=crosswalk, theme_state=theme_state, as_of=as_of,
    )
    run_date = _as_date(as_of) if as_of is not None else _as_date(company_manifest.get("generated_at"))
    assert run_date is not None
    state_receipt, warnings = _theme_state_receipt(theme_state, as_of=run_date)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generation_id": "0" * 24,
        "generated_at": str(company_manifest["generated_at"]),
        "company_count": len(exposures),
        "exposure_count": sum(len(item["exposures"]) for item in exposures.values()),
        "source": {
            "company_intelligence": {
                "generation_id": str(company_manifest["generation_id"]),
                "sha256": canonical_json_sha256(company_manifest),
            },
            "membership": {"sha256": canonical_json_sha256(membership)},
            "crosswalk": {"sha256": canonical_json_sha256(crosswalk)},
            "theme_state": state_receipt,
            "builder": "company_theme_exposure.v1",
        },
        "files": {},
        "status": "empty" if not exposures else ("partial" if warnings else "ready"),
        "warnings": warnings,
    }
    identity = {
        "contexts": {ticker: exposures[ticker] for ticker in sorted(exposures)},
        "manifest": {key: value for key, value in manifest.items() if key not in {"generation_id", "files"}},
    }
    generation_id = canonical_json_sha256(identity)[:24]
    manifest["generation_id"] = generation_id
    for exposure in exposures.values():
        exposure["generation_id"] = generation_id
        validate_exposure(exposure)
    validate_manifest(manifest, allow_unmaterialized_files=True)
    return exposures, manifest


def load_company_generation(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load and prove marker → immutable manifest → per-company contexts."""
    try:
        marker = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"company intelligence manifest unavailable: {exc}") from exc
    if not isinstance(marker, dict):
        raise ContractError("company intelligence manifest invalid")
    validate_company_manifest(marker)
    generation = root / "generations" / str(marker["generation_id"])
    try:
        immutable = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"company intelligence immutable manifest unavailable: {exc}") from exc
    if not isinstance(immutable, dict) or canonical_json_bytes(marker) != canonical_json_bytes(immutable):
        raise ContractError("company intelligence marker/immutable manifest mismatch")
    contexts: dict[str, dict[str, Any]] = {}
    for relative, receipt in sorted(marker.get("files", {}).items()):
        if not isinstance(relative, str) or not isinstance(receipt, Mapping):
            raise ContractError("company intelligence file receipt invalid")
        path = generation / relative
        if not path.is_file() or path.stat().st_size != receipt.get("bytes") or bytes_sha256(path) != receipt.get("sha256"):
            raise ContractError(f"company intelligence immutable object mismatch: {relative}")
        try:
            context = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"company intelligence context invalid: {relative}") from exc
        validate_context(context)
        ticker = safe_ticker(context["company"]["ticker"])
        if relative != company_filename(ticker) or ticker in contexts:
            raise ContractError("company intelligence context filename/ticker mismatch")
        contexts[ticker] = context
    return contexts, marker


def load_json(path: Path, *, required: bool = True) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if not required:
            return None
        raise ContractError(f"JSON input unavailable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON input must be an object: {path}")
    return payload


def load_crosswalk(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"crosswalk unavailable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError("crosswalk must be an object")
    return payload


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(body)
        temp = Path(handle.name)
    temp.replace(path)


def write_generation(out_dir: Path, exposures: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> Path:
    """Write immutable sidecars then immutable manifest, then the sole marker."""
    validate_manifest(manifest, allow_unmaterialized_files=True)
    generation_id = str(manifest["generation_id"])
    generation = out_dir / "generations" / generation_id
    file_receipts: dict[str, dict[str, Any]] = {}
    for ticker in sorted(exposures):
        exposure = dict(exposures[ticker])
        validate_exposure(exposure)
        relative = company_filename(ticker)
        body = canonical_json_bytes(exposure)
        path = generation / relative
        if path.exists() and path.read_bytes() != body:
            raise ContractError(f"immutable generation collision: {path}")
        if not path.exists():
            _atomic_write(path, body)
        file_receipts[relative] = {"sha256": sha256(body).hexdigest(), "bytes": len(body)}
    final = dict(manifest)
    final["files"] = file_receipts
    validate_manifest(final)
    manifest_body = canonical_json_bytes(final)
    immutable = generation / "manifest.json"
    if immutable.exists() and immutable.read_bytes() != manifest_body:
        raise ContractError(f"immutable generation collision: {immutable}")
    if not immutable.exists():
        _atomic_write(immutable, manifest_body)
    _atomic_write(out_dir / "manifest.json", manifest_body)
    return generation
