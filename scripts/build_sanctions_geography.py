"""Build the official OFAC sanctions-geography projection and static desk.

This is an explicit build command, not a scheduler. It writes one bounded
first-load consumer, projection-bound detail shards, and the paired static
presentation assets.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from collectors.ofac_sanctions import (  # noqa: E402
    SourceIntegrityError,
    SourceUnavailableError,
    acquire_bundle,
)
from engine.ofac_sanctions import (  # noqa: E402
    ProjectionBoundsError,
    SourceShapeError,
    build_projection,
    canonical_json_bytes,
)


DATA_NAME = "sanctions-geography-data.json"
SHARD_DIR_NAME = "sanctions-geography-entries"
PAGE_NAME = "sanctions-geography.html"
ASSET_MAP = {
    "sanctions_geography.css": "sanctions-geography.css",
    "sanctions_geography.js": "sanctions-geography.js",
}
BOUNDARY_NAME = "world-110m.json"
NATURAL_EARTH_RIGHTS_URL = "https://www.naturalearthdata.com/about/terms-of-use/"


class BuildUnavailableError(RuntimeError):
    """The builder cannot truthfully produce or retain a projection."""


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _write_if_changed(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == body:
        return
    temp = _temp_sibling(path)
    try:
        temp.write_bytes(body)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    body = source.read_bytes()
    _write_if_changed(destination, body)


def _load_previous(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildUnavailableError(f"last-good machine consumer is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "mastermind.sanctions_geography.v1":
        raise BuildUnavailableError("last-good machine consumer has an unrecognized schema")
    if isinstance(value.get("entries"), list):
        return value

    manifest = value.get("entry_shards")
    if not isinstance(manifest, dict):
        raise BuildUnavailableError("last-good machine consumer has no entry corpus or shard manifest")
    by_geo = manifest.get("by_geo")
    unresolved = manifest.get("unresolved")
    if not isinstance(by_geo, dict) or not isinstance(unresolved, dict):
        raise BuildUnavailableError("last-good shard manifest is malformed")

    records: dict[str, dict[str, Any]] = {}
    expected_records = [*by_geo.items(), ("unresolved", unresolved)]
    for geo_id, record in expected_records:
        if not isinstance(record, dict):
            raise BuildUnavailableError("last-good shard manifest record is malformed")
        if geo_id != "unresolved" and not re.fullmatch(r"[0-9]{3}", str(geo_id)):
            raise BuildUnavailableError("last-good shard identity is not canonical")
        expected_name = "unresolved.json" if geo_id == "unresolved" else f"{geo_id}.json"
        expected_rel = f"{SHARD_DIR_NAME}/{expected_name}"
        if record.get("path") != expected_rel:
            raise BuildUnavailableError("last-good shard path is not canonical")
        shard_path = path.parent / SHARD_DIR_NAME / expected_name
        try:
            body = shard_path.read_bytes()
        except OSError as exc:
            raise BuildUnavailableError(f"last-good shard unavailable: {expected_name}") from exc
        if len(body) != record.get("bytes"):
            raise BuildUnavailableError(f"last-good shard byte count mismatch: {expected_name}")
        if hashlib.sha256(body).hexdigest() != record.get("sha256"):
            raise BuildUnavailableError(f"last-good shard SHA-256 mismatch: {expected_name}")
        try:
            shard = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BuildUnavailableError(f"last-good shard JSON invalid: {expected_name}") from exc
        if (
            not isinstance(shard, dict)
            or shard.get("schema_version") != value.get("schema_version")
            or shard.get("parser_revision") != value.get("parser_revision")
            or shard.get("projection_id") != value.get("projection_id")
            or shard.get("source_identity") != value.get("source_identity")
            or shard.get("geo_id") != geo_id
            or not isinstance(shard.get("entries"), list)
        ):
            raise BuildUnavailableError(f"last-good shard identity mismatch: {expected_name}")
        if len(shard["entries"]) != record.get("entries"):
            raise BuildUnavailableError(f"last-good shard entry count mismatch: {expected_name}")
        for entry in shard["entries"]:
            if not isinstance(entry, dict) or not entry.get("uid"):
                raise BuildUnavailableError(f"last-good shard entry malformed: {expected_name}")
            uid = str(entry["uid"])
            known = records.get(uid)
            if known is not None and known.get("source_fingerprint") != entry.get("source_fingerprint"):
                raise BuildUnavailableError(f"last-good shard entry conflict: UID {uid}")
            records.setdefault(uid, entry)
    value["entries"] = sorted(
        records.values(),
        key=lambda row: (0, int(row["uid"])) if str(row["uid"]).isdigit() else (1, str(row["uid"])),
    )
    return value


def _projection_artifacts(projection: Mapping[str, Any]) -> tuple[bytes, dict[str, bytes]]:
    """Return the lightweight consumer and deterministic projection-bound shards."""

    entries = projection.get("entries")
    if not isinstance(entries, list):
        raise BuildUnavailableError("projection entry corpus is unavailable")
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    unresolved: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("uid"):
            raise BuildUnavailableError("projection entry is malformed")
        uid = str(entry["uid"])
        resolved_ids = {
            str(address.get("geo_id"))
            for address in entry.get("addresses", [])
            if isinstance(address, Mapping) and address.get("geo_id")
        }
        if not resolved_ids:
            unresolved[uid] = entry
        if any(
            isinstance(address, Mapping) and not address.get("geo_id")
            for address in entry.get("addresses", [])
        ):
            unresolved[uid] = entry
        for geo_id in resolved_ids:
            if not re.fullmatch(r"[0-9]{3}", geo_id):
                raise BuildUnavailableError(f"non-canonical geometry shard id: {geo_id!r}")
            grouped.setdefault(geo_id, {})[uid] = entry

    shard_bodies: dict[str, bytes] = {}
    manifest_by_geo: dict[str, dict[str, Any]] = {}
    for geo_id in sorted(grouped):
        shard = {
            "schema_version": projection.get("schema_version"),
            "parser_revision": projection.get("parser_revision"),
            "projection_id": projection.get("projection_id"),
            "source_identity": projection.get("source_identity"),
            "geo_id": geo_id,
            "entries": [grouped[geo_id][uid] for uid in sorted(grouped[geo_id], key=lambda v: (0, int(v)) if v.isdigit() else (1, v))],
        }
        body = canonical_json_bytes(shard)
        name = f"{geo_id}.json"
        shard_bodies[name] = body
        manifest_by_geo[geo_id] = {
            "path": f"{SHARD_DIR_NAME}/{name}",
            "sha256": hashlib.sha256(body).hexdigest(),
            "entries": len(shard["entries"]),
            "bytes": len(body),
        }

    unresolved_shard = {
        "schema_version": projection.get("schema_version"),
        "parser_revision": projection.get("parser_revision"),
        "projection_id": projection.get("projection_id"),
        "source_identity": projection.get("source_identity"),
        "geo_id": "unresolved",
        "entries": [unresolved[uid] for uid in sorted(unresolved, key=lambda v: (0, int(v)) if v.isdigit() else (1, v))],
    }
    unresolved_body = canonical_json_bytes(unresolved_shard)
    shard_bodies["unresolved.json"] = unresolved_body

    consumer = copy.deepcopy(dict(projection))
    consumer.pop("entries", None)
    consumer["entry_shards"] = {
        "initial_requests": 0,
        "selection_request_limit": 1,
        "by_geo": manifest_by_geo,
        "unresolved": {
            "path": f"{SHARD_DIR_NAME}/unresolved.json",
            "sha256": hashlib.sha256(unresolved_body).hexdigest(),
            "entries": len(unresolved_shard["entries"]),
            "bytes": len(unresolved_body),
        },
    }
    return canonical_json_bytes(consumer), shard_bodies


def _write_projection_artifacts(root: Path, projection: Mapping[str, Any]) -> Path:
    site = root / "site"
    output = site / DATA_NAME
    consumer_body, shard_bodies = _projection_artifacts(projection)
    shard_dir = site / SHARD_DIR_NAME
    shard_dir.mkdir(parents=True, exist_ok=True)
    for name, body in shard_bodies.items():
        _write_if_changed(shard_dir / name, body)
    for stale in sorted(shard_dir.glob("*.json")):
        if stale.name not in shard_bodies:
            stale.unlink()
    _write_if_changed(output, consumer_body)
    return output


def build_data(
    *,
    root: Path,
    bundle: Mapping[str, Any],
    as_of: str,
    expected_boundary_sha256: str | None = None,
) -> Path:
    """Project an already-acquired bundle and atomically write the JSON consumer."""

    root = root.resolve()
    site = root / "site"
    boundary_path = site / BOUNDARY_NAME
    try:
        boundary_bytes = boundary_path.read_bytes()
        topology = json.loads(boundary_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildUnavailableError(f"boundary asset unavailable or invalid: {exc}") from exc
    boundary_sha = hashlib.sha256(boundary_bytes).hexdigest()
    if expected_boundary_sha256 and boundary_sha != expected_boundary_sha256:
        raise BuildUnavailableError(
            f"boundary SHA-256 mismatch: expected={expected_boundary_sha256} actual={boundary_sha}"
        )

    output = site / DATA_NAME
    previous = _load_previous(output)
    delta_documents = [
        (row["payload"], row["receipt"])
        for row in bundle.get("delta_documents", [])
    ]
    projection = build_projection(
        current_xml=bundle["current_xml"],
        current_receipt=bundle["current_receipt"],
        schema_receipts=list(bundle.get("schema_receipts", [])),
        catalog_receipts=list(bundle.get("catalog_receipts", [])),
        delta_documents=delta_documents,
        topology=topology,
        boundary_receipt={
            "source_key": "natural_earth_world_110m_existing_asset",
            "asset": f"site/{BOUNDARY_NAME}",
            "raw_sha256": boundary_sha,
            "actual_bytes": len(boundary_bytes),
            "rights": "public_domain",
            "rights_url": NATURAL_EARTH_RIGHTS_URL,
        },
        previous=previous,
        as_of=as_of,
    )
    return _write_projection_artifacts(root, projection)


def degraded_projection(
    last_good: Mapping[str, Any] | None,
    *,
    state: str,
    error_code: str,
) -> dict[str, Any]:
    """Retain last-good facts while making acquisition/parser failure explicit."""

    if last_good is None:
        raise BuildUnavailableError("official source failed and no last-good projection exists")
    if state not in {"SOURCE_UNAVAILABLE", "PARSER_SHAPE_CHANGED"}:
        raise ValueError(f"unrecognized degraded source state: {state}")
    value = copy.deepcopy(dict(last_good))
    value["source_state"] = state
    value["degraded"] = {
        "state": state,
        "error_code": error_code,
        "last_good_projection_id": last_good.get("projection_id"),
        "facts_retained_from_last_good": True,
    }
    return value


def render(root: Path, projection: Mapping[str, Any]) -> Path:
    """Render the shell and exact CSS/JS companions from governed templates."""

    root = root.resolve()
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
        undefined=StrictUndefined,
    )
    html = env.get_template("sanctions_geography.html.j2").render(
        active_section="research",
        active_page="sanctions_geography",
        source_state=projection.get("source_state"),
        projection_id=projection.get("projection_id"),
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    from lib.pages import write_page  # noqa: PLC0415

    page = site / PAGE_NAME
    temp = _temp_sibling(page)
    try:
        write_page(temp, html)
        os.replace(temp, page)
    finally:
        temp.unlink(missing_ok=True)
    for source_name, site_name in ASSET_MAP.items():
        _atomic_copy(root / "templates" / source_name, site / site_name)
    return page


def build(
    *,
    root: Path = _ROOT,
    bundle: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    delta_days: int = 30,
) -> tuple[Path, Path]:
    """Acquire, project, and render; preserve last-good facts on a typed outage."""

    root = root.resolve()
    now = now or datetime.now(timezone.utc)
    as_of = now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output = root / "site" / DATA_NAME
    previous = _load_previous(output)
    try:
        acquired = bundle if bundle is not None else acquire_bundle(now=now, delta_days=delta_days)
        output = build_data(root=root, bundle=acquired, as_of=as_of)
        projection = _load_previous(output)
        assert projection is not None
    except (SourceShapeError, ProjectionBoundsError) as exc:
        projection = degraded_projection(
            previous,
            state="PARSER_SHAPE_CHANGED",
            error_code=f"{type(exc).__name__}:{str(exc)[:160]}",
        )
        _write_projection_artifacts(root, projection)
    except (SourceIntegrityError, SourceUnavailableError, OSError) as exc:
        projection = degraded_projection(
            previous,
            state="SOURCE_UNAVAILABLE",
            error_code=f"{type(exc).__name__}:{str(exc)[:160]}",
        )
        _write_projection_artifacts(root, projection)
    # A data-only success could advance the projection while leaving the page
    # and exact CSS/JS companions on a different build. There is one build path:
    # every accepted projection refreshes its presentation before returning.
    page = render(root, projection)
    return output, page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--delta-days", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        output, page = build(root=args.root, delta_days=args.delta_days)
    except Exception as exc:  # noqa: BLE001 — one typed CI annotation for the explicit build command
        print(f"::error title=sanctions_geography::build failed ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(f"wrote {output}")
    print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
