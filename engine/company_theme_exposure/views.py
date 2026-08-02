"""Pure, deterministic projections for Company Theme Exposure."""
from __future__ import annotations

from datetime import date
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


def _theme_state_receipt(
    payload: Mapping[str, Any] | None,
    *,
    as_of: date,
    canonical_theme_ids: set[str],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(payload, Mapping):
        return {"status": "missing", "as_of": None, "sha256": None}, ["theme_state_missing"]
    stamp = _as_date(payload.get("as_of"))
    # ``stale_legs`` is an explicit producer admission. Do not turn it into
    # narrative; it is a freshness gate for the entire descriptive receipt.
    source_hash = canonical_json_sha256(payload)
    themes = payload.get("themes")
    theme_ids = [item.get("theme_id") for item in themes] if isinstance(themes, list) and all(isinstance(item, Mapping) for item in themes) else []
    authority = payload.get("authority")
    structurally_complete = (
        isinstance(themes, list)
        and bool(themes)
        and isinstance(payload.get("n_themes"), int)
        and payload["n_themes"] == len(themes)
        and len(theme_ids) == len(set(theme_ids))
        and set(theme_ids) == canonical_theme_ids
        and isinstance(authority, Mapping)
        and authority.get("is_context_only") is True
    )
    valid_schema = payload.get("schema") == "neuralweb.theme_state.v1"
    if not valid_schema or stamp is None or not structurally_complete or stamp > as_of:
        return {
            "status": "invalid", "as_of": stamp.isoformat() if stamp else None, "sha256": source_hash,
        }, ["theme_state_invalid"]
    receipt = {"status": "fresh", "as_of": stamp.isoformat(), "sha256": source_hash}
    if (as_of - stamp).days > THEME_STATE_MAX_AGE_DAYS or payload.get("stale_legs"):
        receipt["status"] = "stale"
        return receipt, ["theme_state_stale"]
    return receipt, []


def _active_membership(membership: Mapping[str, Any], *, as_of: date) -> dict[str, set[str]]:
    """Return current ticker → basket IDs; malformed history fails closed.

    Membership is a point-in-time curated roster.  A removed row is validated
    before exclusion, so a bad historical row cannot silently alter coverage.
    """
    baskets = membership.get("baskets")
    if not isinstance(baskets, Mapping):
        raise ContractError("membership.baskets must be an object")
    result: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for basket_id, raw_basket in baskets.items():
        if not isinstance(basket_id, str) or not isinstance(raw_basket, Mapping):
            raise ContractError("membership basket invalid")
        members = raw_basket.get("members")
        if not isinstance(members, list):
            raise ContractError(f"membership {basket_id} members invalid")
        for member in members:
            if not isinstance(member, Mapping):
                raise ContractError(f"membership {basket_id} member invalid")
            try:
                ticker = safe_ticker(member.get("ticker"))
            except ContractError as exc:
                raise ContractError(f"membership {basket_id} member ticker invalid") from exc
            added = _as_date(member.get("added"))
            removed_raw = member.get("removed")
            removed = _as_date(removed_raw) if removed_raw is not None else None
            if added is None or (removed_raw is not None and removed is None) or (removed is not None and removed < added):
                raise ContractError(f"membership {basket_id} member dates invalid")
            identity = (basket_id, ticker)
            if identity in seen:
                raise ContractError(f"membership duplicate active identity: {basket_id}/{ticker}")
            seen.add(identity)
            if added > as_of or (removed is not None and removed <= as_of):
                continue
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
            note = str(raw.get("note") or "").lower()
            proxy_terms = ("closest", "no dedicated", "broader", "parent", "supply chain", "fuel supply", "covers")
            qualifier = "proxy" if any(term in note for term in proxy_terms) else ("direct" if "direct" in note else "curated")
            index[basket_id] = {
                "theme_id": theme_id,
                "name_en": names[0],
                "name_zh": names[1],
                # A source-methodology qualifier, never an asserted company
                # relationship. It prevents a curated proxy basket from
                # presenting as a literal business exposure.
                "mapping_qualifier": qualifier,
            }
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


def _canonical_theme_ids(crosswalk: Mapping[str, Any]) -> set[str]:
    return {str(raw["id"]) for raw in crosswalk["themes"] if isinstance(raw, Mapping)}


def _coverage(active: set[str], theme_by_basket: Mapping[str, Mapping[str, str]]) -> dict[str, int | str]:
    mapped = len(active & set(theme_by_basket))
    unmapped = len(active) - mapped
    status = (
        "no_active_membership" if not active else
        "mapped" if mapped == len(active) else
        "unmapped_only" if unmapped == len(active) else
        "mixed"
    )
    return {
        "status": status,
        "active_basket_count": len(active),
        "mapped_basket_count": mapped,
        "unmapped_basket_count": unmapped,
    }


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
    current_by_ticker = _active_membership(membership, as_of=run_date)
    theme_by_basket = _crosswalk_index(crosswalk, membership)
    state_receipt, state_warnings = _theme_state_receipt(
        theme_state, as_of=run_date, canonical_theme_ids=_canonical_theme_ids(crosswalk),
    )
    exposures: dict[str, dict[str, Any]] = {}
    for ticker in sorted(contexts):
        context = contexts[ticker]
        validate_context(context)
        if safe_ticker(ticker) != safe_ticker(context["company"]["ticker"]):
            raise ContractError("context ticker key mismatch")
        if context.get("generation_id") != ci_generation:
            raise ContractError("context does not match pinned company intelligence generation")
        active = current_by_ticker.get(ticker, set())
        coverage = _coverage(active, theme_by_basket)
        items = [
            {**theme_by_basket[basket], "basket_id": basket}
            for basket in active
            if basket in theme_by_basket
        ]
        items.sort(key=lambda value: (value["theme_id"], value["basket_id"]))
        warnings = sorted({*state_warnings, *( ["active_membership_unmapped"] if coverage["unmapped_basket_count"] else [])})
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
            "coverage": coverage,
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
    current_by_ticker = _active_membership(membership, as_of=run_date)
    theme_by_basket = _crosswalk_index(crosswalk, membership)
    state_receipt, state_warnings = _theme_state_receipt(
        theme_state, as_of=run_date, canonical_theme_ids=_canonical_theme_ids(crosswalk),
    )
    active_sets = list(current_by_ticker.values())
    active_membership_count = sum(len(items) for items in active_sets)
    mapped_membership_count = sum(len(items & set(theme_by_basket)) for items in active_sets)
    unmapped_membership_count = active_membership_count - mapped_membership_count
    coverage = {
        "active_membership_count": active_membership_count,
        "mapped_membership_count": mapped_membership_count,
        "unmapped_membership_count": unmapped_membership_count,
        "active_member_ticker_count": len(current_by_ticker),
        "unmapped_only_ticker_count": sum(1 for items in active_sets if items and not (items & set(theme_by_basket))),
        "active_member_tickers_without_company_context": len(set(current_by_ticker) - set(contexts)),
    }
    warnings = sorted({*state_warnings, *( ["active_memberships_unmapped"] if unmapped_membership_count else [])})
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generation_id": "0" * 24,
        "generated_at": str(company_manifest["generated_at"]),
        "company_count": len(exposures),
        "exposure_count": sum(len(item["exposures"]) for item in exposures.values()),
        "coverage": coverage,
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
    generation_id = derive_generation_id(exposures, manifest)
    manifest["generation_id"] = generation_id
    for exposure in exposures.values():
        exposure["generation_id"] = generation_id
        validate_exposure(exposure)
    validate_manifest(manifest, allow_unmaterialized_files=True)
    return exposures, manifest


def derive_generation_id(exposures: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> str:
    """Derive the immutable address from final semantic object content.

    IDs themselves and byte receipts are deliberately normalised out of the
    preimage.  This prevents circular hashing while still binding every other
    exposure field and every semantic manifest field to the address.
    """
    normalised: dict[str, dict[str, Any]] = {}
    for ticker in sorted(exposures):
        value = json.loads(json.dumps(exposures[ticker], ensure_ascii=False))
        value["generation_id"] = "0" * 24
        normalised[ticker] = value
    manifest_value = json.loads(json.dumps(manifest, ensure_ascii=False))
    manifest_value["generation_id"] = "0" * 24
    manifest_value["files"] = {}
    return canonical_json_sha256({"contexts": normalised, "manifest": manifest_value})[:24]


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
    # Validate map key ↔ payload ticker before deriving the address. This turns
    # a swapped file into a specific failure, rather than allowing a later hash
    # mismatch to obscure a serious address/content bug.
    for ticker in sorted(exposures):
        exposure = dict(exposures[ticker])
        validate_exposure(exposure)
        if safe_ticker(ticker) != safe_ticker(exposure["company"]["ticker"]):
            raise ContractError("exposure filename ticker does not match payload company ticker")
    generation_id = derive_generation_id(exposures, manifest)
    if manifest["generation_id"] != generation_id:
        raise ContractError("generation_id does not bind final exposure/manifest content")
    generation = out_dir / "generations" / generation_id
    file_receipts: dict[str, dict[str, Any]] = {}
    for ticker in sorted(exposures):
        exposure = dict(exposures[ticker])
        if exposure["generation_id"] != generation_id:
            raise ContractError("exposure generation_id does not bind final content")
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
