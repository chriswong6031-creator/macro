#!/usr/bin/env python3
"""Fail closed when the public Government Revenue projection drifts.

The serialized Government Revenue lane owns canonical evidence under
``data/government_revenue``. Generic render lanes may restyle/re-stamp the
public page, but they must never publish an older JSON twin, a full-payload
HTML regression, or a shell whose bundle identity differs from canonical
workspace bytes. The independently generation-bound dossier artifact is held
to the same byte-identical canonical/public-twin boundary.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from scripts import build_government_revenue


_ROOT = Path(__file__).resolve().parents[1]
_RAW_HTML_BUDGET_BYTES = build_government_revenue.RAW_HTML_BUDGET_BYTES
_BUNDLE_RE = re.compile(r"grw2-[a-f0-9]{24}")
_SHELL_RE = re.compile(
    r'<script id="gov-data" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_REQUIRED_MARKERS = (
    'id="gov-workspace"',
    'id="queueList"',
    'id="inspectorPane"',
    'id="evidenceDrawer"',
    'id="gov-data"',
)


class ProjectionDriftError(ValueError):
    """The public projection is not the governed canonical generation."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectionDriftError(f"{label} must be a JSON object")
    return value


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectionDriftError(f"{label} is unavailable or invalid: {path}") from exc
    return raw, _object(parsed, label)


def validate_projection(root: Path = _ROOT) -> dict[str, Any]:
    """Validate canonical/public twins and the compact first-paint shell."""

    root = root.resolve()
    canonical_dir = root / "data" / "government_revenue"
    public_dir = root / "site" / "government-revenue-data"
    html_path = root / "site" / "government_revenue.html"

    canonical_latest_raw, canonical_latest = _read_json(
        canonical_dir / "latest.json", "canonical latest"
    )
    canonical_workspace_raw, canonical_workspace = _read_json(
        canonical_dir / "workspace.json", "canonical workspace"
    )
    public_latest_raw, _public_latest = _read_json(
        public_dir / "latest.json", "public latest twin"
    )
    public_workspace_raw, public_workspace = _read_json(
        public_dir / "workspace.json", "public workspace twin"
    )
    canonical_dossier_raw, canonical_dossier = _read_json(
        canonical_dir / "dossiers.json", "canonical dossier"
    )
    public_dossier_raw, _public_dossier = _read_json(
        public_dir / "dossiers.json", "public dossier twin"
    )

    try:
        build_government_revenue._validate_payload(canonical_latest)
    except ValueError as exc:
        raise ProjectionDriftError("canonical latest schema is invalid") from exc
    try:
        recipient_coverage = build_government_revenue._validate_recipient_activation(
            root,
            canonical_latest,
        )
    except ValueError as exc:
        raise ProjectionDriftError("canonical recipient activation is invalid") from exc
    if recipient_coverage is not None:
        coverage_path = (
            canonical_dir
            / build_government_revenue.RECIPIENT_RESOLUTION_COVERAGE_FILENAME
        )
        coverage_raw, committed_coverage = _read_json(
            coverage_path,
            "canonical recipient resolution coverage",
        )
        if build_government_revenue._canonical_json(committed_coverage).encode(
            "utf-8"
        ) != coverage_raw:
            raise ProjectionDriftError(
                "canonical recipient resolution coverage bytes are non-canonical"
            )
        if build_government_revenue._canonical_json(committed_coverage) != (
            build_government_revenue._canonical_json(recipient_coverage)
        ):
            raise ProjectionDriftError(
                "canonical recipient resolution coverage differs from embedded award-event freshness"
            )

    if public_latest_raw != canonical_latest_raw:
        raise ProjectionDriftError("public latest twin differs from canonical latest bytes")
    if public_workspace_raw != canonical_workspace_raw:
        raise ProjectionDriftError(
            "public workspace twin differs from canonical workspace bytes"
        )
    if public_dossier_raw != canonical_dossier_raw:
        raise ProjectionDriftError(
            "public dossier twin differs from canonical dossier bytes"
        )
    try:
        build_government_revenue._validate_dossier_payload(canonical_dossier)
    except ValueError as exc:
        raise ProjectionDriftError("canonical dossier schema is invalid") from exc
    if build_government_revenue._canonical_json(canonical_dossier).encode("utf-8") != (
        canonical_dossier_raw
    ):
        raise ProjectionDriftError("canonical dossier bytes are non-canonical")

    embedded_workspace = _object(
        canonical_latest.get("procurement_workspace"),
        "canonical latest procurement_workspace",
    )
    if build_government_revenue._canonical_json(embedded_workspace) != (
        build_government_revenue._canonical_json(canonical_workspace)
    ):
        raise ProjectionDriftError(
            "canonical latest embeds a different workspace generation"
        )

    bundle_id = canonical_workspace.get("bundle_id")
    if not isinstance(bundle_id, str) or not _BUNDLE_RE.fullmatch(bundle_id):
        raise ProjectionDriftError("canonical workspace bundle_id is invalid")
    if bundle_id != build_government_revenue._workspace_bundle_id(canonical_workspace):
        raise ProjectionDriftError("canonical workspace bundle_id is not content-derived")
    if public_workspace.get("bundle_id") != bundle_id:
        raise ProjectionDriftError("public workspace bundle_id differs from canonical")

    try:
        html_raw = html_path.read_bytes()
        html = html_raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectionDriftError(f"public HTML is unavailable or invalid: {html_path}") from exc
    if len(html_raw) > _RAW_HTML_BUDGET_BYTES:
        raise ProjectionDriftError(
            f"public HTML exceeds {_RAW_HTML_BUDGET_BYTES} bytes: {len(html_raw)}"
        )
    missing = [marker for marker in _REQUIRED_MARKERS if marker not in html]
    if missing:
        raise ProjectionDriftError(
            "public HTML is missing governed workspace markers: " + ", ".join(missing)
        )
    shell_match = _SHELL_RE.search(html)
    if shell_match is None:
        raise ProjectionDriftError("public HTML compact shell is missing")
    try:
        shell = _object(
            json.loads(shell_match.group(1).replace(r"<\/", "</")),
            "public HTML compact shell",
        )
    except json.JSONDecodeError as exc:
        raise ProjectionDriftError("public HTML compact shell is invalid JSON") from exc
    shell_workspace = _object(
        shell.get("procurement_workspace"),
        "public HTML procurement_workspace",
    )
    if shell_workspace.get("bundle_id") != bundle_id:
        raise ProjectionDriftError(
            "public HTML workspace bundle_id differs from canonical"
        )
    if (
        shell_workspace.get("schema_version") != "government_procurement_workspace.v2"
        or shell_workspace.get("event_contract") != "government_procurement_event.v2"
    ):
        raise ProjectionDriftError("public HTML workspace schema is invalid")

    expected_shell = build_government_revenue._display_payload(canonical_latest)
    if build_government_revenue._canonical_json(shell) != (
        build_government_revenue._canonical_json(expected_shell)
    ):
        raise ProjectionDriftError(
            "public HTML compact shell differs semantically from canonical latest"
        )

    return {
        "bundle_id": bundle_id,
        "html_bytes": len(html_raw),
        "events": len(canonical_workspace.get("events") or []),
        "dossier_content_id": canonical_dossier.get("content_id"),
        "dossier_awards": len(canonical_dossier.get("awards") or []),
        "recipient_graph_id": (
            recipient_coverage.get("resolution_graph", {}).get("graph_id")
            if recipient_coverage is not None
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the public Government Revenue projection"
    )
    parser.add_argument("--root", default=str(_ROOT))
    args = parser.parse_args(argv)
    try:
        result = validate_projection(Path(args.root))
    except ProjectionDriftError as exc:
        print(f"government revenue projection FAILED: {exc}")
        return 1
    print(
        "government revenue projection OK — "
        f"bundle={result['bundle_id']} html={result['html_bytes']}B "
        f"events={result['events']} dossier={result['dossier_content_id']} "
        f"awards={result['dossier_awards']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
