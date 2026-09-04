"""Build the official OFAC sanctions-geography projection and static desk.

This is an explicit build command, not a scheduler. It writes one bounded
machine consumer plus the paired static presentation assets.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
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
    SourceShapeError,
    build_projection,
    canonical_json_bytes,
)


DATA_NAME = "sanctions-geography-data.json"
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
    return value


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
    _write_if_changed(output, canonical_json_bytes(projection))
    return output


def degraded_projection(
    last_good: Mapping[str, Any] | None,
    *,
    state: str,
    error_code: str,
) -> dict[str, Any]:
    """Retain last-good facts while making acquisition/parser failure explicit."""

    if last_good is None:
        raise BuildUnavailableError("official source failed and no last-good projection exists")
    if state not in {"UNAVAILABLE", "PARSER_SHAPE_CHANGED"}:
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
    data_only: bool = False,
) -> tuple[Path, Path | None]:
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
    except SourceShapeError as exc:
        projection = degraded_projection(
            previous,
            state="PARSER_SHAPE_CHANGED",
            error_code=f"{type(exc).__name__}:{str(exc)[:160]}",
        )
        _write_if_changed(output, canonical_json_bytes(projection))
    except (SourceIntegrityError, SourceUnavailableError, OSError) as exc:
        projection = degraded_projection(
            previous,
            state="UNAVAILABLE",
            error_code=f"{type(exc).__name__}:{str(exc)[:160]}",
        )
        _write_if_changed(output, canonical_json_bytes(projection))
    page = None if data_only else render(root, projection)
    return output, page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--delta-days", type=int, default=30)
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        output, page = build(root=args.root, delta_days=args.delta_days, data_only=args.data_only)
    except Exception as exc:  # noqa: BLE001 — one typed CI annotation for the explicit build command
        print(f"::error title=sanctions_geography::build failed ({type(exc).__name__}: {exc})", flush=True)
        return 1
    print(f"wrote {output}")
    if page:
        print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
